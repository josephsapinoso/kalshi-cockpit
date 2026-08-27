"""Held parlays: what Joe is on the hook for, and what a hedge would do to it.

ADR 0078. `core/hedge.py` owns the arithmetic and touches nothing; this module
owns the record, the live book, and the words. The split is the one
`core/ladder.py` and `parlays.py` already use, for the same reason: a pure
function is testable against a hand calculation, and a function that reads a
database is not.

Three facts this module supplies that the arithmetic cannot
-----------------------------------------------------------
**Which legs are still alive.** A lock exists only when every other leg has
already WON, and that is a fact about the world rather than about a price. Two
sources, kept distinguishable because they are not equally good: the venue's own
`kalshi_markets.result`, and Joe's word. A sportsbook leg has no ticker, so his
word is the only source available for it, and every surface says which one was
used.

**Which side to buy.** The hedge is the opposite side of the leg on the same
market. A YES leg is hedged by buying NO, at the derived NO ask, with the size
resting behind it -- never at a mid, and never at the leg's own ask.

**What it costs in words.** Money strings are rendered here, server-side, for
the `lib/api.ts` rule: the client does no money arithmetic, so the screen and
the Discord embed cannot drift from each other by a rounding step.

What this module refuses to do
------------------------------
- **Write a `recommendations` row.** Nothing here enters the evidence record.
  `runner`'s `dropped_game_started` drop is untouched (ADR 0006) and no in-play
  consensus is bought.
- **Rank positions.** They are listed in the order they were recorded. ADR 0071
  §2.5 forbids ranking by the consensus-vs-Kalshi gap, and this module does not
  compute that gap at all.
- **Say whether to hedge.** It reports what is available. ADR 0078 Decision 2.

What this module does NOT establish
-----------------------------------
- That a hand-marked leg actually won. `resolved_source = 'manual'` is Joe's
  word, recorded as his word.
- That the record is complete. A ticket he did not type in is invisible here,
  and that is the whole failure mode of an operator-entered record.
- That a quote could be filled at size. Depth is read off the book and reported;
  nothing models the next level down.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Union

from .core.correlation import Leg
from .core.hedge import (
    Derisk,
    HedgeQuote,
    Lock,
    Refusal,
    UNREADABLE_TICKET,
    derisk,
    hedge_lock,
    ticket_refusal,
)
from .core.fees import calculate_fee
from .core.prices import (
    format_dollars,
    format_price,
    format_probability,
    is_valid_price,
    tenths_to_probability,
)
from .store.db import derive_no_ask, derive_yes_ask

logger = logging.getLogger(__name__)

#: What state a held ticket is in. One vocabulary, shared by the screen, the
#: watcher and the tests, so a typo cannot invent a sixth state that renders
#: as an empty card.
STATE_LOCK = "lock"
STATE_DERISK = "derisk"
STATE_DEAD = "dead"
STATE_WON = "won"
STATE_VOID_LEG = "void_leg"
STATE_NOT_HEDGEABLE = "not_hedgeable"

STATES = (
    STATE_LOCK,
    STATE_DERISK,
    STATE_DEAD,
    STATE_WON,
    STATE_VOID_LEG,
    STATE_NOT_HEDGEABLE,
)

#: The sentences every hedge surface carries, verbatim, exactly as
#: `parlays.NOTES` does. They travel to Discord unchanged (ADR 0072 Decision 3),
#: so a caveat cannot be dropped by the transport that needs it most.
NOTES: dict[str, str] = {
    "upper_bound": (
        "Every figure charges the entry fee only. Whether Kalshi also charges "
        "at settlement is unverified here, so a locked amount is a ceiling — "
        "the real number can only be smaller."
    ),
    "not_advice": (
        "This is what a hedge would lock in at the price showing right now. "
        "It is not a claim that the price will get worse, or that taking it "
        "beats holding — the hedge price is the market's own number and "
        "nothing here beats it."
    ),
    "no_button": (
        "Place the hedge in the Kalshi app. This screen shows the size and "
        "the price; the cockpit's own bet door is capped at one contract, "
        "which a hedge is not."
    ),
    "derisk": (
        "More than one leg is still live, so a hedge on one of them locks "
        "NOTHING. It changes the shape of what can happen, and both branches "
        "are shown so you can see how."
    ),
}


class PositionRefused(ValueError):
    """A ticket that cannot be recorded, carrying the reason as data."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.detail)
        self.refusal = refusal


@dataclass(frozen=True)
class MarketBook:
    """One market's two published bids, as observed. Asks are derived.

    A deliberate re-statement of the three fields `core/hedge.py` needs, rather
    than passing a `LiveQuote` down: the arithmetic module must stay free of
    every import that reaches the network, and a narrow record is what keeps
    the test for it hand-writable.
    """

    ticker: str
    yes_bid_tenths: Optional[int]
    no_bid_tenths: Optional[int]
    yes_ask_size: Optional[float]
    no_ask_size: Optional[float]
    status: Optional[str]
    observed_ms: int

    @classmethod
    def from_live_quote(cls, quote) -> "MarketBook":
        market = quote.market
        return cls(
            ticker=quote.ticker,
            yes_bid_tenths=market.yes_bid_tenths,
            no_bid_tenths=market.no_bid_tenths,
            yes_ask_size=market.yes_ask_size,
            no_ask_size=market.no_ask_size,
            status=quote.status,
            observed_ms=quote.observed_ms,
        )


def event_ticker_for(ticker: Optional[str]) -> Optional[str]:
    """The fixture a market ticker belongs to, from the ticker alone.

    **Found by driving the real venue, 2026-08-26.** A ticket recorded with two
    legs of the *same game* -- Boston to win and Miami to win, which cannot both
    happen -- was priced as two independent legs and handed back a joint
    probability. `assess` keys same-game detection on `event_ticker`, the form
    accepts a bare Kalshi ticker, and nothing filled the gap: two sides of one
    fixture have different market tickers, so they looked unrelated.

    Kalshi game tickers are `SERIES-EVENT-SIDE`
    (`KXMLBGAME-26AUG261840BOSMIA-BOS`), so the first two segments are the
    fixture. That is the same structural read `frontend/src/lib/kalshiLink.ts`
    makes, verified in a browser on 2026-08-22, and it is applied only to a
    ticker with exactly three segments — anything else returns `None` rather
    than guessing, because a wrong fixture key would *merge* two real games and
    refuse a legitimate joint.

    `core.correlation` then raises `CorrelationRefused` on the pair, which is
    the right answer: this repo has no measured same-game correlation
    (ADR 0012 §5), and a mutually exclusive pair is the case where inventing
    one is most wrong.
    """
    if not ticker:
        return None
    segments = ticker.strip().upper().split("-")
    if len(segments) != 3:
        return None
    return f"{segments[0]}-{segments[1]}"


def hedge_side(leg_side: str) -> str:
    """The side you buy to hedge a leg. One expression, one place to be wrong."""
    if leg_side == "yes":
        return "no"
    if leg_side == "no":
        return "yes"
    raise ValueError(f"side must be 'yes' or 'no', got {leg_side!r}")


def _ask_and_depth(book: MarketBook, side: str) -> tuple[Optional[int], Optional[float]]:
    """The derived ask for `side` and the size resting behind it.

    Both come from the same record read at the same instant. `derive_*_ask`
    already refuses an absent bid -- an empty side arrives from the venue as
    `0.0000`, and `1000 - 0` is a settled outcome wearing a price's clothes --
    so this returns `None` rather than a number the caller has to re-check.
    """
    if side == "yes":
        return derive_yes_ask(book.no_bid_tenths), book.yes_ask_size
    if side == "no":
        return derive_no_ask(book.yes_bid_tenths), book.no_ask_size
    raise ValueError(f"side must be 'yes' or 'no', got {side!r}")


def quote_for_hedge(leg_side: str, book: MarketBook) -> HedgeQuote:
    """The book on the side that hedges `leg_side`.

    `leg_ask_tenths` rides along so the crossed-book test has both sides to
    compare. It is never priced against and never displayed as a cost.
    """
    buy = hedge_side(leg_side)
    ask, depth = _ask_and_depth(book, buy)
    leg_ask, _ = _ask_and_depth(book, leg_side)
    return HedgeQuote(
        ticker=book.ticker,
        side=buy,
        ask_tenths=ask,
        depth_at_ask=depth,
        observed_ms=book.observed_ms,
        status=book.status,
        leg_ask_tenths=leg_ask,
    )


def leg_probability(leg_side: str, book: MarketBook) -> Optional[float]:
    """What the venue's own BID says this leg is worth, as a probability.

    The bid rather than the ask or the mid, and the reason is that this number
    values a position rather than pricing a purchase: the bid is what somebody
    will actually pay, which is the conservative side and the only transactable
    one. The mid is not a price anyone will trade at, which is the mistake
    `store.db.ask_for_side`'s docstring records costing the previous project
    $4.92 a market.

    `None` when the bid is not a tradeable level. Callers refuse; nobody
    substitutes a half.
    """
    bid = book.yes_bid_tenths if leg_side == "yes" else book.no_bid_tenths
    if not is_valid_price(bid):
        return None
    return tenths_to_probability(bid)


def affordable_contracts(
    spendable_tenths: Optional[int],
    ask_tenths: Optional[int],
    *,
    depth_contracts: int,
) -> tuple[int, bool]:
    """How many hedge contracts the observed balance covers, and whether it was read.

    **An unknown balance is not a balance of zero, and that distinction is the
    whole reason this returns two values.** `latest_balance_tenths` answers
    `None` whenever the newest poll could not read the venue's figure, which is
    a routine five-minute outage rather than an empty account. Folding that into
    a cap of 0 would make every hedge unaffordable and silence the alert for
    exactly as long as the mirror was behind -- this repo's own "unreadable
    must never resolve to zero" rule, applied to a budget instead of a price.

    So an unread balance falls back to what the BOOK allows, and the second
    value says the cap is not real. The screen renders that as "we could not
    read your balance", never as a number Joe might act on.

    Cost per contract includes the fee at one contract, which rounds up harder
    than the fee at `n` does -- conservative in the direction that matters,
    because the failure this bounds is being told you can afford a hedge you
    cannot.
    """
    if spendable_tenths is None or not is_valid_price(ask_tenths):
        return depth_contracts, False
    fee = calculate_fee(int(ask_tenths), 1)
    if fee is None:
        return depth_contracts, False
    per_contract = int(ask_tenths) + int(math.ceil(fee * 1000 - 1e-9))
    if per_contract <= 0:
        return depth_contracts, False
    return max(0, int(spendable_tenths) // per_contract), True


# --------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------


def record_position(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    source: str,
    label: str,
    stake_tenths: int,
    return_tenths: int,
    legs: Sequence[Mapping[str, Any]],
    book: Optional[str] = None,
    placed_ms: Optional[int] = None,
    combo_ticker: Optional[str] = None,
    parlay_lookup_id: Optional[int] = None,
    note: Optional[str] = None,
) -> int:
    """Record a ticket Joe holds. Returns its id, or raises `PositionRefused`.

    The ticket arithmetic is validated HERE, at entry, and not only at alert
    time -- a misplaced decimal point can still be corrected while he is typing
    it, and cannot be corrected in the sixth inning.
    """
    refusal = ticket_refusal(stake_tenths, return_tenths)
    if refusal is not None:
        raise PositionRefused(refusal)
    if not legs:
        raise PositionRefused(
            Refusal(UNREADABLE_TICKET, "A parlay needs at least one leg.")
        )
    if not label.strip():
        raise PositionRefused(
            Refusal(UNREADABLE_TICKET, "A ticket needs a name you will recognise.")
        )

    cursor = conn.execute(
        """
        INSERT INTO parlay_positions (
            created_ms, source, book, label, stake_tenths, return_tenths,
            placed_ms, status, combo_ticker, parlay_lookup_id, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
        """,
        (
            now_ms,
            source,
            book,
            label.strip(),
            int(stake_tenths),
            int(return_tenths),
            placed_ms,
            combo_ticker,
            parlay_lookup_id,
            note,
        ),
    )
    position_id = int(cursor.lastrowid)
    for index, leg in enumerate(legs):
        conn.execute(
            """
            INSERT INTO parlay_position_legs (
                position_id, leg_index, ticker, side, label, event_ticker,
                league, commence_ms, outcome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                position_id,
                index,
                (leg.get("ticker") or None),
                leg["side"],
                leg["label"],
                # Derived when the caller did not supply one: the form takes a
                # bare market ticker, and without the fixture two legs of one
                # game read as unrelated.
                leg.get("event_ticker") or event_ticker_for(leg.get("ticker")),
                leg.get("league"),
                leg.get("commence_ms"),
            ),
        )
    conn.commit()
    return position_id


def open_positions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM parlay_positions WHERE status = 'open' "
            "ORDER BY created_ms DESC"
        )
    )


def legs_for(conn: sqlite3.Connection, position_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM parlay_position_legs WHERE position_id = ? "
            "ORDER BY leg_index",
            (position_id,),
        )
    )


def resolve_leg(
    conn: sqlite3.Connection,
    *,
    leg_id: int,
    outcome: str,
    now_ms: int,
    source: str,
) -> bool:
    """Mark one leg. Returns whether a row moved.

    **Only a pending leg moves.** A settled leg is a fact, and letting a second
    write flip it would make a lock computed an hour ago unreproducible from the
    record -- which is exactly the property that makes a record worth keeping.
    """
    if outcome not in ("won", "lost", "void"):
        raise ValueError(f"outcome must be won/lost/void, got {outcome!r}")
    if source not in ("venue", "manual"):
        raise ValueError(f"source must be venue/manual, got {source!r}")
    cursor = conn.execute(
        """
        UPDATE parlay_position_legs
           SET outcome = ?, resolved_ms = ?, resolved_source = ?
         WHERE id = ? AND outcome = 'pending'
        """,
        (outcome, now_ms, source, leg_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def resolve_from_venue(conn: sqlite3.Connection, *, now_ms: int) -> int:
    """Settle every pending leg whose market the venue has already called.

    Reads `kalshi_markets.result`, which `market_results.py` writes on the full
    pass. A leg with no ticker is structurally unreachable here, which is the
    sportsbook case and why the hand-marking route exists.

    A `result` this function does not recognise -- an empty string, a void, a
    value nobody has seen -- leaves the leg pending. **Unreadable resolves to
    nothing, never to a loss**: marking a leg lost on an unparsed field would
    kill a live ticket on the screen and silence its alerts.
    """
    rows = list(
        conn.execute(
            """
            SELECT l.id AS leg_id, l.side AS side, m.result AS result
              FROM parlay_position_legs l
              JOIN parlay_positions p ON p.id = l.position_id
              JOIN kalshi_markets  m ON m.ticker = l.ticker
             WHERE l.outcome = 'pending'
               AND p.status = 'open'
               AND l.ticker IS NOT NULL
               AND m.result IS NOT NULL
               AND m.result != ''
            """
        )
    )
    moved = 0
    for row in rows:
        result = str(row["result"]).strip().lower()
        if result not in ("yes", "no"):
            continue
        outcome = "won" if result == row["side"] else "lost"
        if resolve_leg(
            conn, leg_id=row["leg_id"], outcome=outcome, now_ms=now_ms, source="venue"
        ):
            moved += 1
    return moved


def close_position(
    conn: sqlite3.Connection, *, position_id: int, now_ms: int, status: str
) -> bool:
    if status not in ("settled", "closed", "void"):
        raise ValueError(f"status must be settled/closed/void, got {status!r}")
    cursor = conn.execute(
        "UPDATE parlay_positions SET status = ?, closed_ms = ? "
        "WHERE id = ? AND status = 'open'",
        (status, now_ms, position_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def watched_tickers(conn: sqlite3.Connection) -> list[str]:
    """Every Kalshi ticker an open position still has a pending leg on.

    The watcher's whole subscription list, and the only thing it reads the
    database for. Bounded by the number of open positions, which is bounded by
    how many tickets one person holds.
    """
    return [
        str(row["ticker"])
        for row in conn.execute(
            """
            SELECT DISTINCT l.ticker AS ticker
              FROM parlay_position_legs l
              JOIN parlay_positions p ON p.id = l.position_id
             WHERE p.status = 'open'
               AND l.outcome = 'pending'
               AND l.ticker IS NOT NULL
            """
        )
    ]


# --------------------------------------------------------------------------
# The assessment
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Assessment:
    """One held ticket, as of one instant.

    `state` is from `STATES`. `outcome` is a `Lock`, a `Derisk`, a `Refusal` or
    `None` -- and `None` is a real answer, not a missing one: a ticket whose
    every leg has already won has nothing to hedge.
    """

    position_id: int
    state: str
    hedge_leg_id: Optional[int]
    outcome: Union[Lock, Derisk, Refusal, None]
    pending_legs: int
    detail: str
    #: Whether the affordability cap came from a balance that was actually
    #: read. False means the cap is the book's depth standing in for one, and
    #: every surface must say so rather than presenting it as a limit.
    bankroll_known: bool = False


def assess(
    position: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
    books: Mapping[str, MarketBook],
    *,
    now_ms: int,
    max_quote_age_ms: int,
    spendable_tenths: Optional[int],
) -> Assessment:
    """What state this ticket is in, and what hedging its weakest leg would do.

    The leg chosen is the pending one the venue currently prices LOWEST -- the
    one in most trouble, which is the question Joe asked. Ordering a ticket's
    own legs by the venue's own price is not the consensus-vs-Kalshi gap ADR
    0071 §2.5 forbids ranking by; no such gap is computed anywhere in this
    module.
    """
    position_id = int(position["id"])
    stake = int(position["stake_tenths"])
    payout = int(position["return_tenths"])

    if any(leg["outcome"] == "lost" for leg in legs):
        return Assessment(
            position_id,
            STATE_DEAD,
            None,
            None,
            0,
            "A leg has lost, so this ticket cannot win. Nothing left to hedge.",
        )
    if any(leg["outcome"] == "void" for leg in legs):
        return Assessment(
            position_id,
            STATE_VOID_LEG,
            None,
            None,
            0,
            "A leg was voided. A voided leg usually re-prices the whole ticket "
            "and this tool has no way to know the new payout, so it will not "
            "guess one — re-record the ticket with the figures the book gave "
            "you.",
        )

    pending = [leg for leg in legs if leg["outcome"] == "pending"]
    if not pending:
        return Assessment(
            position_id,
            STATE_WON,
            None,
            None,
            0,
            "Every leg has won. There is nothing to hedge — the ticket is "
            "waiting to be paid.",
        )

    hedgeable = [
        leg
        for leg in pending
        if leg["ticker"] and str(leg["ticker"]) in books
    ]
    if not hedgeable:
        return Assessment(
            position_id,
            STATE_NOT_HEDGEABLE,
            None,
            None,
            len(pending),
            "No live leg has a Kalshi market this tool can read, so there is "
            "no hedge to price.",
        )

    def price_of(leg) -> float:
        book = books[str(leg["ticker"])]
        probability = leg_probability(str(leg["side"]), book)
        # An unreadable bid sorts LAST rather than first. A leg nobody is
        # bidding on looks like the weakest one and is actually the one we
        # know least about, and picking it would hedge on the strength of a
        # missing number.
        return 2.0 if probability is None else probability

    weakest = min(hedgeable, key=lambda leg: (price_of(leg), int(leg["leg_index"])))
    book = books[str(weakest["ticker"])]
    quote = quote_for_hedge(str(weakest["side"]), book)
    depth = (
        int(quote.depth_at_ask) if quote.depth_at_ask is not None else 0
    )
    affordable, bankroll_known = affordable_contracts(
        spendable_tenths, quote.ask_tenths, depth_contracts=depth
    )

    if len(pending) == 1:
        outcome = hedge_lock(
            stake_tenths=stake,
            return_tenths=payout,
            quote=quote,
            now_ms=now_ms,
            max_quote_age_ms=max_quote_age_ms,
            affordable_contracts=affordable,
        )
        detail = (
            "One leg left and every other has won, so a hedge here has a "
            "known answer whichever way it goes."
        )
        state = STATE_LOCK
    else:
        live: list[Leg] = []
        for leg in pending:
            ticker = str(leg["ticker"]) if leg["ticker"] else None
            probability = (
                leg_probability(str(leg["side"]), books[ticker])
                if ticker and ticker in books
                else None
            )
            if probability is None:
                live = []
                break
            live.append(
                Leg(
                    label=str(leg["label"]),
                    probability=probability,
                    event_key=str(
                        leg["event_ticker"]
                        or event_ticker_for(leg["ticker"])
                        or leg["ticker"]
                        or leg["id"]
                    ),
                    league=str(leg["league"] or "unknown"),
                    # A leg with no recorded kickoff is treated as today's.
                    # `classify` reads this only to separate same-day from
                    # unrelated, and the nudges are 0.05 / 0.02 -- so the
                    # error is at most a fraction of a point on the joint,
                    # in the direction that RAISES it (positive correlation
                    # makes legs likelier to land together). Stated rather
                    # than called conservative, because it is not.
                    commence_ms=int(leg["commence_ms"] or now_ms),
                )
            )
        outcome = derisk(
            stake_tenths=stake,
            return_tenths=payout,
            quote=quote,
            live_legs=live,
            now_ms=now_ms,
            max_quote_age_ms=max_quote_age_ms,
            affordable_contracts=affordable,
        )
        detail = NOTES["derisk"]
        state = STATE_DERISK

    return Assessment(
        position_id=position_id,
        state=state,
        hedge_leg_id=int(weakest["id"]),
        outcome=outcome,
        pending_legs=len(pending),
        detail=detail,
        bankroll_known=bankroll_known,
    )


# --------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------
#
# Rendered server-side, every money string included, for the `lib/api.ts` rule:
# the client does no money arithmetic, so the screen and the Discord embed
# cannot drift from each other by a rounding step. ADR 0072 Decision 3 made the
# same choice for the parlay card and gave the reason -- an embed that formats
# its own floats disagrees with the screen within a week.


def _rung_payload(rung) -> dict:
    return {
        "contracts": rung.contracts,
        "cost_display": format_dollars(rung.cost_tenths),
        "fee_display": format_dollars(rung.fee_tenths),
        "if_leg_wins_display": format_dollars(rung.if_leg_wins_tenths),
        "if_leg_loses_display": format_dollars(rung.if_leg_loses_tenths),
        "floor_display": format_dollars(rung.floor_tenths),
        # The raw figure, for `notify.alerts.hedge_key`'s ratchet ALONE.
        #
        # It is the one number in this payload that is not a rendered string,
        # and it is here because the alternative is worse: a ratchet keyed on
        # `floor_display` would re-announce a lock every time a rounding step
        # moved the last cent, and re-keying it in the notifier would put a
        # second definition of the same quantity one module away.
        #
        # **The client must not compute with it**, and cannot by accident:
        # `HedgeRung` in `frontend/src/lib/api.ts` does not declare the field,
        # so a component that reached for it would fail `tsc`.
        "floor_tenths": rung.floor_tenths,
        "floor_is_a_gain": rung.floor_tenths > 0,
        "fillable": rung.fillable,
        "affordable": rung.affordable,
    }


def _hedge_payload(assessment: Assessment) -> Optional[dict]:
    """The hedge block, or `None` when the ticket has nothing to hedge.

    `None` and a refusal are different answers and both are rendered: a ticket
    whose legs have all won has no hedge, and a ticket whose hedge market has
    an empty book has one that cannot be priced. Collapsing them would make
    "nothing to do" and "we could not look" the same empty card.
    """
    outcome = assessment.outcome
    if outcome is None:
        return None
    if isinstance(outcome, Refusal):
        return {"refusal": outcome.as_dict()}

    quote = outcome.quote
    block = {
        "refusal": None,
        "ticker": quote.ticker,
        "side": quote.side,
        "ask_display": format_price(quote.ask_tenths),
        "depth_at_ask": quote.depth_at_ask,
        "ladder": [_rung_payload(r) for r in outcome.ladder],
    }
    if isinstance(outcome, Lock):
        block.update(
            {
                "kind": STATE_LOCK,
                "equalising": _rung_payload(outcome.equalising),
                "best_available": (
                    _rung_payload(outcome.best_available)
                    if outcome.best_available is not None
                    else None
                ),
                "guaranteed": outcome.is_guaranteed_profit,
                "guaranteed_display": (
                    format_dollars(outcome.best_available.floor_tenths)
                    if outcome.best_available is not None
                    else None
                ),
                "full_hedge_is_out_of_reach": (
                    outcome.best_available is None
                    or outcome.best_available.contracts
                    < outcome.equalising.contracts
                ),
            }
        )
    else:
        block.update(
            {
                "kind": STATE_DERISK,
                # No `guaranteed` key at all, rather than `guaranteed: false`.
                # A ticket with several legs live does not have a guarantee
                # that happens to be absent; it has no guarantee to have, and
                # a false flag invites a screen to render "not guaranteed"
                # beside a number as though one were coming.
                "live_legs": outcome.live_legs,
                "chance_display": format_probability(outcome.joint_probability),
                "notional_value_display": format_dollars(
                    outcome.notional_value_tenths
                ),
                "chance_refusal": (
                    outcome.joint_refusal.as_dict()
                    if outcome.joint_refusal is not None
                    else None
                ),
            }
        )
    return block


def _leg_payload(
    leg: Mapping[str, Any],
    books: Mapping[str, MarketBook],
    *,
    hedge_leg_id: Optional[int],
    now_ms: int,
) -> dict:
    ticker = str(leg["ticker"]) if leg["ticker"] else None
    book = books.get(ticker) if ticker else None
    probability = (
        leg_probability(str(leg["side"]), book) if book is not None else None
    )
    return {
        "id": int(leg["id"]),
        "index": int(leg["leg_index"]),
        "label": str(leg["label"]),
        "ticker": ticker,
        "side": str(leg["side"]),
        "league": leg["league"],
        "commence_ms": leg["commence_ms"],
        "outcome": str(leg["outcome"]),
        "resolved_ms": leg["resolved_ms"],
        "resolved_source": leg["resolved_source"],
        # The venue's own bid, as a percentage. Absent -- never 0% -- when
        # nobody is bidding or the leg has no market at all.
        "chance_display": format_probability(probability),
        "quote_age_ms": (
            max(0, now_ms - book.observed_ms) if book is not None else None
        ),
        "priceable": book is not None,
        "is_hedge_leg": hedge_leg_id is not None and int(leg["id"]) == hedge_leg_id,
    }


def serialise_position(
    position: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
    books: Mapping[str, MarketBook],
    assessment: Assessment,
    *,
    now_ms: int,
) -> dict:
    """One held ticket as the screen and the notifier both read it."""
    return {
        "id": int(position["id"]),
        "label": str(position["label"]),
        "source": str(position["source"]),
        "book": position["book"],
        "created_ms": int(position["created_ms"]),
        "placed_ms": position["placed_ms"],
        "combo_ticker": position["combo_ticker"],
        "stake_display": format_dollars(int(position["stake_tenths"])),
        "return_display": format_dollars(int(position["return_tenths"])),
        "state": assessment.state,
        "state_detail": assessment.detail,
        "bankroll_known": assessment.bankroll_known,
        "pending_legs": assessment.pending_legs,
        "legs": [
            _leg_payload(
                leg, books, hedge_leg_id=assessment.hedge_leg_id, now_ms=now_ms
            )
            for leg in legs
        ],
        "hedge": _hedge_payload(assessment),
    }


async def read_books(
    tickers: Sequence[str], *, now_ms: int, fetch_quote
) -> dict[str, MarketBook]:
    """Read every watched market's book, tolerating the ones that refuse.

    A ticker that cannot be read is simply **absent** from the result, and
    every downstream surface treats an absent book as "not priceable" with
    words. It is not represented by an empty book, because an empty book is a
    real and different state -- nobody is resting -- and the two would then
    render identically.

    Sequential rather than gathered: the watched set is bounded by how many
    tickets one person holds, and a burst of concurrent reads against the
    venue buys nothing measurable while making a rate limit reachable.
    """
    books: dict[str, MarketBook] = {}
    for ticker in tickers:
        try:
            quote = await fetch_quote(ticker, observed_ms=now_ms)
        except Exception as exc:                                # noqa: BLE001
            # Every failure -- transport, status, credentials -- is the same
            # answer here: this leg has no price this pass. `QuoteUnavailable`
            # already collapses the first three (`kalshi/quotes.py`), and the
            # fourth is a config error on an instance holding no credentials.
            logger.info("no live book for %s: %s", ticker, exc)
            continue
        books[ticker] = MarketBook.from_live_quote(quote)
    return books


async def build_payload(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    max_quote_age_ms: int,
    spendable_tenths: Optional[int],
    fetch_quote,
) -> dict:
    """Every open ticket, its legs' live prices, and what a hedge would do.

    Positions come back in the order they were recorded. **No ordering here is
    a judgement** -- ADR 0071 §2.5 forbids ranking by the consensus-vs-Kalshi
    gap, and this module does not compute that gap at all.
    """
    positions = open_positions(conn)
    books = await read_books(
        watched_tickers(conn), now_ms=now_ms, fetch_quote=fetch_quote
    )
    rows = []
    for position in positions:
        legs = legs_for(conn, int(position["id"]))
        assessment = assess(
            position,
            legs,
            books,
            now_ms=now_ms,
            max_quote_age_ms=max_quote_age_ms,
            spendable_tenths=spendable_tenths,
        )
        rows.append(
            serialise_position(position, legs, books, assessment, now_ms=now_ms)
        )
    return {
        "as_of_ms": now_ms,
        "positions": rows,
        "notes": dict(NOTES),
    }
