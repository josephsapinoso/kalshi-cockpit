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
    combo_entry_fee_tenths,
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
    # Keyed `upper_bound` for the wire's sake (`api.ts`, `discord.py` and
    # three test files read the key); the sentence stopped claiming one on
    # 2026-09-11. Four terms sit on the figure and they do not share a sign
    # -- the untested settlement charge (H4) pushes the true number down;
    # the sent-vs-charged stake (ADR 0143 §4), the flat 0.070 hedge fee and
    # the 0.071 entry-fee coefficient (ADR 0145, which put the entry fee
    # into the sunk stake) push it up -- so it is an estimate, and neither
    # a ceiling nor a floor. Wording per the measurement-skeptic's audit,
    # 2026-09-11, amended for ADR 0145.
    "upper_bound": (
        "Every figure here charges the fee on this hedge, and on a Kalshi "
        "combo it also subtracts the fee you already paid to enter the "
        "ticket, at the measured combo rate — which has run about a percent "
        "above what Kalshi charged on every fill seen. It assumes Kalshi "
        "charges nothing when the market pays out, which is unverified. The "
        "stake it subtracts is the price the desk sent, not the price Kalshi "
        "charged. Treat it as an estimate good to roughly a cent a contract, "
        "not a guaranteed amount."
    ),
    "not_advice": (
        "This is what a hedge would lock in at the price showing right now. "
        "It is not a claim that the price will get worse, or that taking it "
        "beats holding — the hedge price is the market's own number and "
        "nothing here beats it."
    ),
    # "capped at one contract" was true until ADR 0112 (2026-09-08) took the
    # caps off; the live limits are the venue-shaped 500 / 250 in
    # `store/manual_orders.py`. The sentence now claims only what is so.
    "no_button": (
        "Place the hedge in the Kalshi app. This screen shows the size and "
        "the price; it has no buy button of its own and places nothing."
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


def entry_fee_tenths(position: Mapping[str, Any]) -> Optional[int]:
    """The fee sunk on entering this ticket, or `None` when there is none to
    model: a sportsbook slip prices its vig into the odds Joe typed, so
    charging a fee on top would double-count it. ADR 0145."""
    if str(position["source"]) != "kalshi_combo":
        return None
    return combo_entry_fee_tenths(
        int(position["stake_tenths"]), int(position["return_tenths"])
    )


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
# Coverage -- what the venue holds that the record does not, and vice versa
# --------------------------------------------------------------------------
#
# ADR 0136. Read off live
# 2026-09-10: the newest `positions` poll held one open KXMVE combination
# bought in the Kalshi app, and `/hedge` had never heard of it -- the entry
# path this ADR extends (ADR 0125) writes `parlay_positions` only when the
# fill came through the desk. These functions supply the two facts that keep
# a hole like that from reading as "nothing is happening": what the venue
# holds that this record does not, and whether a ticket this record holds is
# still at the venue at all. Neither closes a position or ranks one; ADR
# 0071 §2.5 and Decision 4's "no ranking" apply here exactly as they do to
# the rest of this module.


def _latest_ok_positions_poll(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """The newest `positions` poll that both succeeded AND kept its rows.

    `bets.open_positions` established this exact selector (`ok = 1 AND
    mirrored = 1`) and the reason for the second clause: `poll_log` has a
    second writer, `routes.py::_stamp_positions_read`, which logs a real
    `row_count` on every hand bet but keeps no rows under it. `ok = 1` alone
    would sometimes select that bare stamp, find zero `venue_positions` rows
    under it, and read as "the venue holds nothing" for as long as five
    minutes after every bet -- the false negative in the flattering
    direction this module's whole design refuses. `mirrored = 1` keeps that
    stamp out of the selection, the same way it keeps it out of
    `bets.open_positions`.

    `None` when there has never been a poll of this shape -- coverage is then
    genuinely unknown, and callers must say so rather than reporting an empty
    venue.
    """
    return conn.execute(
        "SELECT id, polled_ms FROM poll_log "
        "WHERE endpoint = 'positions' AND ok = 1 AND mirrored = 1 "
        "ORDER BY polled_ms DESC, id DESC LIMIT 1"
    ).fetchone()


def venue_position_tickers(
    conn: sqlite3.Connection,
) -> tuple[Optional[set[str]], Optional[int]]:
    """Every ticker the LATEST COMPLETE positions poll saw held, and when.

    `venue_positions` is append-only and per-poll: a position still open is
    rewritten every cycle under a fresh `poll_log_id`, and a position that
    closed simply stops being written under later ones -- it is never marked
    closed in place. So membership can only be asked of ONE poll, the newest
    complete one, never of "the newest row seen for this ticker" (which
    would answer a ticker last seen three polls ago as still open, the exact
    shape of bug `scripts/inspect_live_db_parlays.py`'s `_q_combo_position_gaps`
    was written to surface on the entry side).

    Returns `(None, None)` when there has never been a complete poll --
    coverage is unknown, not "the venue holds nothing" -- and otherwise the
    set of tickers plus that poll's `polled_ms`.
    """
    poll = _latest_ok_positions_poll(conn)
    if poll is None:
        return None, None
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM venue_positions "
        "WHERE poll_log_id = ? AND ticker IS NOT NULL",
        (int(poll["id"]),),
    ).fetchall()
    return {str(row["ticker"]) for row in rows}, int(poll["polled_ms"])


def unrecorded_at_venue(conn: sqlite3.Connection) -> list[dict]:
    """KXMVE combinations the latest complete poll holds that no OPEN
    `parlay_positions` row is watching.

    **Combinations only.** `ticker LIKE 'KXMVE%'` is deliberate: a single
    Kalshi market is not a parlay, this screen watches parlays, and a bare
    single held outside the desk has no hedge story -- there is no other leg
    to reshape. Widening this to every venue ticker would be a different
    screen answering a different question.

    A ticker already claimed by an OPEN position is not listed even if that
    position's `combo_ticker` came from a different source than the fill
    being observed now -- the identity is the ticker, and a closed position
    that reused one (Kalshi does not reuse tickers, but this repo does not
    assume it) would be a second bug, not this one's to hide.

    Returns `[]`, never a claim of coverage, when there has been no complete
    poll -- see `venue_position_tickers`.
    """
    poll = _latest_ok_positions_poll(conn)
    if poll is None:
        return []
    open_combo_tickers = {
        str(row["combo_ticker"])
        for row in conn.execute(
            "SELECT combo_ticker FROM parlay_positions "
            "WHERE status = 'open' AND combo_ticker IS NOT NULL"
        )
    }
    rows = conn.execute(
        "SELECT ticker, contracts, exposure_tenths FROM venue_positions "
        "WHERE poll_log_id = ? AND ticker LIKE 'KXMVE%' "
        "ORDER BY ticker",
        (int(poll["id"]),),
    ).fetchall()
    polled_ms = int(poll["polled_ms"])
    return [
        {
            "ticker": str(row["ticker"]),
            "contracts": row["contracts"],
            "exposure_display": format_dollars(row["exposure_tenths"]),
            "last_seen_ms": polled_ms,
        }
        for row in rows
        if str(row["ticker"]) not in open_combo_tickers
    ]


def combo_settlements(
    conn: sqlite3.Connection, tickers: Sequence[str]
) -> dict[str, dict]:
    """The venue's own settlement of each ticker in `tickers`, batched.

    **Found reading live 2026-09-10/2026-10-09.** A `KXMVE` combination can
    settle (`venue_settlements`, `market_result = 'no'`) while its leg
    markets have not -- `kalshi_markets.result` stayed NULL on all three legs
    of a settled combo, because the venue processes a combination market on
    its own clock rather than waiting for every leg market to resolve
    individually. `resolve_from_venue` reads only `kalshi_markets.result`, so
    it cannot see this, and neither can `venue_position_tickers` -- a settled
    position also stops appearing in the positions poll, the same as one that
    was simply closed, so absence-from-poll cannot tell "settled" from
    "closed some other way" either. The combo's own settlement is the one
    fact that says which.

    `market_result` is returned **verbatim**, never mapped here: 'yes' and
    'no' are what has been observed, but nothing here assumes those are the
    only spellings the venue uses, and inventing a third would be a guess.

    Batched over every open position's `combo_ticker` in one query, on the
    same reasoning `read_books` gives for staying sequential the other
    direction: this table is not the venue, so there is no rate limit to
    respect and no reason to serialise it.
    """
    wanted = {str(t) for t in tickers if t}
    if not wanted:
        return {}
    placeholders = ",".join("?" for _ in wanted)
    rows = conn.execute(
        f"SELECT ticker, market_result, settled_ms FROM venue_settlements "
        f"WHERE ticker IN ({placeholders}) "
        f"ORDER BY settled_ms DESC, id DESC",
        tuple(wanted),
    ).fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        ticker = str(row["ticker"])
        if ticker in result:
            # Already holding the newest for this ticker -- the ORDER BY put
            # it first, and a second row is an older settlement attempt.
            continue
        result[ticker] = {
            "market_result": row["market_result"],
            "settled_ms": int(row["settled_ms"]),
        }
    return result


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
    # The sunk stake is what left the account: the contracts at their price
    # PLUS the taker fee the venue charged on entry, which `stake_tenths`
    # does not carry (`routes._record_combo_position` writes price times
    # contracts). Left out, every branch of every rung reads too high by
    # the fee -- ~17 tenths a contract at 41c, the size of the smallest
    # floors `Lock.is_guaranteed_profit` fires on. ADR 0145. A sportsbook
    # slip has no separate fee: its vig is inside the price already typed.
    stake = int(position["stake_tenths"]) + (entry_fee_tenths(position) or 0)
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


def _at_venue(
    position: Mapping[str, Any], venue_tickers: Optional[set[str]]
) -> Optional[bool]:
    """Whether this position's own market is in the latest complete poll.

    `None` -- never `True` or `False` -- in the two states where the question
    has no answer: a sportsbook slip has no `combo_ticker` and cannot be "at
    the venue" in the first place, and with no complete poll yet coverage
    itself is unknown. Only a `combo_ticker` present and a poll to check it
    against yields a real `True`/`False`.
    """
    combo_ticker = position["combo_ticker"]
    if not combo_ticker or venue_tickers is None:
        return None
    return str(combo_ticker) in venue_tickers


def serialise_position(
    position: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
    books: Mapping[str, MarketBook],
    assessment: Assessment,
    *,
    now_ms: int,
    venue_tickers: Optional[set[str]] = None,
    venue_settlement: Optional[Mapping[str, Any]] = None,
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
        # The entry fee the arithmetic sinks beside the stake (ADR 0145), or
        # `None` on a sportsbook slip. Shown so the screen's stake line and
        # the lock figure reconcile: the lock is net of BOTH numbers.
        "entry_fee_display": (
            format_dollars(fee)
            if (fee := entry_fee_tenths(position)) is not None
            else None
        ),
        "return_display": format_dollars(int(position["return_tenths"])),
        "state": assessment.state,
        "state_detail": assessment.detail,
        "bankroll_known": assessment.bankroll_known,
        "pending_legs": assessment.pending_legs,
        # `True`/`False` only when there is both a ticket to check and a
        # complete poll to check it against; `None` otherwise. Never
        # auto-closes anything -- see `close_position`, tapped by Joe.
        "at_venue": _at_venue(position, venue_tickers),
        # The venue's own settlement of the COMBO market, verbatim, or `None`
        # when unsettled. Distinct from `at_venue`: a combo can settle before
        # its leg markets do, so this can be non-null while every leg below
        # still reads `pending` -- which leg lost is not knowable from this
        # alone, and nothing here marks one.
        "venue_settlement": dict(venue_settlement) if venue_settlement else None,
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

    Also carries the two coverage facts ADR 0136 (the hedge screen says
    what it cannot see) adds: `unrecorded_at_venue` (combinations the venue
    holds that this record does not) and, per position, `at_venue` and
    `venue_settlement` (whether and how this record's own ticket is still
    there). Neither is used to close or reorder anything here.
    """
    positions = open_positions(conn)
    books = await read_books(
        watched_tickers(conn), now_ms=now_ms, fetch_quote=fetch_quote
    )
    venue_tickers, venue_poll_ms = venue_position_tickers(conn)
    settlements = combo_settlements(
        conn, [p["combo_ticker"] for p in positions if p["combo_ticker"]]
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
        combo_ticker = position["combo_ticker"]
        rows.append(
            serialise_position(
                position,
                legs,
                books,
                assessment,
                now_ms=now_ms,
                venue_tickers=venue_tickers,
                venue_settlement=(
                    settlements.get(str(combo_ticker)) if combo_ticker else None
                ),
            )
        )
    return {
        "as_of_ms": now_ms,
        "positions": rows,
        "notes": dict(NOTES),
        "unrecorded_at_venue": unrecorded_at_venue(conn),
        "venue_poll_ms": venue_poll_ms,
        # Rides along so the screen can dim a leg's price past the same bound
        # the assessment itself refuses a stale quote at -- one number, not a
        # second guess of it hardcoded into a component.
        "max_quote_age_ms": max_quote_age_ms,
    }
