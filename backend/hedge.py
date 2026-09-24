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
- **That a `venue_fill` stake is the whole of what the venue charged.** It is
  the venue's average fill price times the count it reported, and nothing
  else: the fee on that entry is still `combo_entry_fee_tenths`' modelled
  number at 0.071 (ADR 0145), not `manual_orders.venue_avg_fee_dollars`,
  which nothing here reads. The figure remains an estimate pinned in neither
  direction, with at least four error terms; this closes none of them and
  narrows only the stake's own price.
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
    SETTLEMENT_TENTHS,
    UNREADABLE_TICKET,
    combo_entry_fee_tenths,
    derisk,
    hedge_lock,
    ticket_refusal,
)
from .core.fees import calculate_fee
from .kalshi.orderbook import OrderBook
from .kalshi.rfq import QUOTE_FILLED_STATUSES, RfqRefused, mve_legs
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

#: The five states a held combination's public-book buy-back can be in
#: (#95). They never collapse into each other -- that is the whole point of
#: the ticket, and the review that rewrote this ticket twice named the
#: collapse (read-failed rendering as nothing-resting) the critical defect.
#:
#: `combo_book["state"]` carries the first four; the fifth, "not
#: applicable", is `combo_book is None` with `combo_book_reason` naming why
#: -- the wire pattern `stake_basis`/`stake_basis_reason` already uses two
#: fields up. A `None` here is not a missing case; it is a DESIGNED state
#: with two distinct causes (see `COMBO_BOOK_REASON_*`), and the screen
#: renders nothing at all for it -- not "could not be read", which would
#: claim a read was attempted, and not "nothing resting", which would claim
#: an empty book was actually seen.
COMBO_BOOK_BID = "bid"
COMBO_BOOK_EMPTY = "empty"
COMBO_BOOK_UNPRICED_INTEREST = "unpriced_interest"
COMBO_BOOK_UNREADABLE = "unreadable"

#: Why `combo_book` is `None`. Both are designed states, not errors.
COMBO_BOOK_REASON_NO_TICKET = "no_ticket"
COMBO_BOOK_REASON_NO_READER_WIRED = "no_reader_wired"
#: Every leg has resolved, so there is nothing left to sell into and no
#: venue read is spent (#128 review, defect 1). `open_positions` means
#: unclosed bookkeeping, not a live game -- 41 rows were "open" on
#: 2026-09-21 with every game settled -- so without this gate `/api/hedge`
#: would read the venue once per settled row on every page load, on the one
#: screen wanted mid-game, under a 30s proxy ceiling.
COMBO_BOOK_REASON_NOTHING_PENDING = "nothing_pending"

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
    #
    # It ended "good to roughly a cent a contract" until 2026-09-16. The
    # registered census of 2026-09-15 (`docs/measurements/2026-09-15-recorded-
    # fill-vs-venue-charge-census-result.md`) read the sent price against
    # the venue's on the twelve joined hand-bet fills and found one 22
    # tenths a contract off, so "a cent" was flattering. The sentence now
    # carries the counts -- eleven at zero, one at 2.2c -- and says what they
    # are not: a rate, or anything about the next fill (§6.2, §6.3 of the
    # result). Issue #43, answered A by Joe 2026-09-16.
    #
    # The stake clause was an unconditional claim that the figure subtracts
    # the SENT price until 2026-09-16, and issue #49 (answered A the same
    # day) falsified it: `stake_bases` now reads the stake at the venue's
    # own fill price wherever the venue gave one. A caveat that names a
    # condition is falsified by fixing the condition, so this sentence ships
    # in the commit that fixes it -- otherwise the screen tells him the
    # figure carries an error it no longer carries. The condition that
    # remains is real and is named: a bet placed before schema v40
    # (2026-09-11) has no venue price on its row.
    "upper_bound": (
        "Every figure here charges the fee on this hedge, and on a Kalshi "
        "combo it also subtracts the fee you already paid to enter the "
        "ticket, at the measured combo rate — which has run about a percent "
        "above what Kalshi charged on every fill seen. It assumes Kalshi "
        "charges nothing when the market pays out, which is unverified. The "
        "stake it subtracts is Kalshi's own fill price where the venue "
        "reported one, and the price the desk sent where it did not — a bet "
        "placed before 2026-09-11 has no price from the venue on record. "
        "Read against each other on 2026-09-15, the two matched on eleven of "
        "the twelve hand-bet fills and were 2.2 cents a contract apart on "
        "the twelfth — twelve fills of one kind of ticket, not a rate, and "
        "nothing about the next fill. It is an estimate, not a guaranteed "
        "amount."
    ),
    # "would lock in" until 2026-09-16 (issue #43): the same word the
    # headline lost, on the screen's header and in both embeds' footers.
    "not_advice": (
        "This is what a hedge would come to at the price showing right now. "
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
    scout_states = _scout_states_at_bet(
        conn, [leg.get("ticker") for leg in legs], now_ms=now_ms
    )
    for index, leg in enumerate(legs):
        conn.execute(
            """
            INSERT INTO parlay_position_legs (
                position_id, leg_index, ticker, side, label, event_ticker,
                league, commence_ms, event_title, outcome, scout_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
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
                # The game, from the lookup blob (`leg_details_for`). `None`
                # on a hand-typed slip; the screen then prints the label
                # alone rather than a title derived from a ticker.
                leg.get("event_title") or None,
                scout_states.get(leg.get("ticker") or ""),
            ),
        )
    conn.commit()
    return position_id


def _scout_states_at_bet(
    conn: sqlite3.Connection, tickers: Sequence[Optional[str]], *, now_ms: int
) -> dict[str, str]:
    """What the scout desk knew about each leg's game, right now, keyed by
    the leg's market ticker. Schema v52, ADR 0180 §3.5.

    Read through `parlays.scouting_facts` -- the one fixture join every
    screen uses -- so the value recorded here is the value the card showed
    at the moment of the bet, not a second derivation that could disagree
    with it. A leg with no ticker (a hand-typed slip) has no game to look up
    and is left out, so it records NULL.

    **Nothing here may raise into the writer.** `record_position` sits on the
    armed order path (`routes._record_combo_position`) and the RFQ accept, and
    a bookkeeping lookup failing must not turn a purchase that already
    happened into an error that says nothing happened. A failure records
    NULL -- "not recorded" -- which the column's comment says is its meaning,
    and is logged so the gap is visible rather than silent.

    Imported inside the function: `parlays` is a large module this one does
    not otherwise depend on, and pulling it in at import time would make the
    hedge screen's "no model, no tokens, no credits" assertion harder to read
    off the module header.
    """
    wanted = [t for t in tickers if t]
    if not wanted:
        return {}
    try:
        from .parlays import scouting_facts

        facts = scouting_facts(conn, wanted, now_ms=now_ms)
    except Exception:                                        # noqa: BLE001
        logger.exception("scout state at bet time could not be read; recording NULL")
        return {}
    return {
        ticker: str(one["scout"])
        for ticker, one in facts.items()
        if isinstance(one.get("scout"), str)
    }


def entry_fee_tenths(position: Mapping[str, Any]) -> Optional[int]:
    """The fee sunk on entering this ticket, or `None` when there is none to
    model: a sportsbook slip prices its vig into the odds Joe typed, so
    charging a fee on top would double-count it. ADR 0145."""
    if str(position["source"]) != "kalshi_combo":
        return None
    return combo_entry_fee_tenths(
        int(position["stake_tenths"]), int(position["return_tenths"])
    )


# --------------------------------------------------------------------------
# The stake basis: whose price the sunk stake is
# --------------------------------------------------------------------------
#
# **Two prices exist for every hand bet and they are not the same number.**
# `manual_orders.limit_price_tenths` is the ask the desk SENT, written at
# intent time before anything filled; `manual_orders.venue_avg_fill_price_
# tenths` (schema v40, ADR 0143) is what Kalshi said it charged. Until Joe
# answered ticket #49 nothing that runs read the second one: the only
# readers in the tree were the spent registered census and its tests, and
# `parlay_positions.stake_tenths` -- the number every rung, every entry fee
# and the screen's stake line are computed from -- was the sent price times
# the contract count.
#
# The census (`docs/measurements/2026-09-15-recorded-fill-vs-venue-charge-
# census-result.md`) found the two equal on 11 of 12 joined rows and apart
# by 22 tenths a contract on the twelfth, with the sent price ABOVE the
# venue's. n is 12, every row is one stratum (`S1`/`KXMVE`) and every order
# is `side = yes`; that look is spent and nothing here generalises from it.
# It is the reason the correction is small in the rows seen so far and not a
# reason to skip it.
#
# **The resolution is at READ time and the written row is never rewritten.**
# ADR 0145 set the precedent in `assess` itself: the entry fee is sunk beside
# the stake when the screen is built, not written into `stake_tenths`. Three
# further reasons here:
#
# - `POST /api/manual-orders` is the ARMED path. A correction that runs
#   there is a change to code that sends real money; one that runs on the
#   read is not, and this one buys nothing that the read cannot do.
# - `parlay_positions` has no column for the marker and no `manual_order_id`
#   to join on, so recording the basis at write time needs a schema version.
#   Derived here, the join IS the marker.
# - The ten rows already open keep their stored `stake_tenths` byte for
#   byte. Nothing backfills, so nothing has to be unwound; deleting this
#   block restores the previous figures exactly.

#: The stake is the venue's own average fill price times the contract count.
STAKE_BASIS_VENUE_FILL = "venue_fill"
#: The stake is `parlay_positions.stake_tenths` as written -- the sent price
#: for a combination bought through the desk, Joe's typed figure for a slip.
STAKE_BASIS_AS_RECORDED = "as_recorded"
#: The stake is the venue's own `market_exposure_dollars` for a position
#: `adopt_venue_combo` (#148) wrote -- Kalshi's own reported cost of the
#: holding, but never itself checked against a fill: an adopted row has no
#: `manual_orders` row and no RFQ acceptance behind it by construction, so
#: none of E2's "sent price vs. venue charge" machinery has anything to
#: compare it to. Deliberately its own basis rather than a third
#: `STAKE_BASIS_AS_RECORDED` reason: `as_recorded` means "the figure Joe (or
#: the desk) typed, unchecked", and an adopted stake was never typed at all
#: -- it is Kalshi's own number from the moment it was written.
STAKE_BASIS_VENUE_EXPOSURE = "venue_exposure"

#: Prefixes `parlay_positions.note` on a row `adopt_venue_combo` writes.
#: There is no schema column for "this row was adopted" and this ticket must
#: not add one -- the marker IS the column, the same reasoning `_order_key`
#: gives for deriving ADR 0160's join rather than storing it. Safe as an
#: internal-only discriminator because nothing serialises `parlay_positions.
#: note` to the screen (grep confirms no `position["note"]` read anywhere in
#: `build_payload`'s output) -- Joe never sees this text, only what
#: `STAKE_BASIS_VENUE_EXPOSURE`'s own note renders in its place.
ADOPTED_NOTE_MARKER = "[adopted-from-venue-positions]"


def _is_adopted_position(position: Mapping[str, Any]) -> bool:
    """Whether `position` is a row `adopt_venue_combo` wrote, read off the
    marker `note` carries rather than off `source` (a third `source` value
    would silently stop `_order_key`'s `== "kalshi_combo"` check, the
    frontend's sell-quote gate and the combo-book gate from recognising an
    adopted combination as the same kind of thing a bought one is, all of
    which an adopted position should still get). `note` is a real
    `parlay_positions` column, present on every row `SELECT *` returns."""
    note = position["note"]
    return isinstance(note, str) and note.startswith(ADOPTED_NOTE_MARKER)


@dataclass(frozen=True)
class StakeBasis:
    """What a position's sunk stake is, and whose number it came from.

    `reason` is `None` on `venue_fill` and names the refusal otherwise. It is
    a vocabulary rather than prose because the caller that most needs it is a
    future audit, and a fact behind a parser is not queryable -- the same rule
    `schema.sql` states over `parlay_position_legs`.

    **`stake_tenths` is never smaller than it has to be by guesswork.** Every
    branch below that cannot read the venue's price falls back to the number
    already on the row; none substitutes a zero, and none averages the two.
    """

    stake_tenths: int
    basis: str
    reason: Optional[str] = None


def _order_key(position: Mapping[str, Any]) -> Optional[tuple[str, int]]:
    """`(combo_ticker, placed_ms)` for a combination bought through the desk,
    or `None` for anything that cannot have an order row behind it.

    Both halves come from one request: the route takes `submitted_ms` once,
    writes it on the `manual_orders` row and passes the same variable to
    `_record_combo_position` as `placed_ms`. The ticker alone would not do --
    the same combination can be bought twice.

    **`None` is also the marker for a ticket Joe recorded by hand**, derived
    rather than stored (issue #56, answered A on 2026-09-17). `record_position`
    has three callers and only one of them leaves both columns empty: the
    order path sets both, the RFQ accept path sets both (issue #69), and
    `POST /api/hedge/positions` takes them from the request -- and the form
    behind it sends neither. So a combination he typed in has no key, and no
    lookup over `manual_orders` is possible at all. That is a different fact
    from a key that WAS formed and matched nothing, and `stake_basis_for`
    names the two separately rather than sharing one sentence between them.

    **A formed key does not promise a row exists to find.** The RFQ path
    forms one and there is no `manual_orders` row behind it by construction;
    `stake_basis_for` separates that from a genuine gap with `rfq_accept`,
    which is the same split issue #56 bought, applied to a second path.

    It is derived here rather than stamped on the row for ADR 0160's own
    reason: the marker IS the join, so a column for it would buy a schema
    version and nothing else.
    """
    if str(position["source"]) != "kalshi_combo":
        return None
    if not position["combo_ticker"] or position["placed_ms"] is None:
        return None
    return (str(position["combo_ticker"]), int(position["placed_ms"]))


def _rfq_stake_basis(
    position: Mapping[str, Any],
    rfq_fill: Optional[Mapping[str, Any]],
    recorded: int,
) -> StakeBasis:
    """The stake for a position bought by taking a maker's quote.

    Three states, and the first two are different facts that must not share a
    word (issue #74, ADR 0178):

    - **`rfq_accept`** -- the venue was never asked. Every acceptance written
      before schema v50, and any whose fill read could not be recorded. The
      stake is the quote's ask times its size, which is what ADR 0169 wrote.
    - **`rfq_fill_unmatched`** -- the venue WAS asked and its answer cannot be
      used for this position: it reported nothing under the combination's
      ticker, or reported a count that does not rebuild the holding stored
      with it. `combo_rfq_quotes.venue_fill_outcome` says which; this screen
      says only that the check ran and did not land, because the seven
      outcomes behind it are a measurement and not a vocabulary for a phone.
    - **`venue_fill`** -- Kalshi's own count and average price, proved against
      the holding by the same identity the order path uses.

    The count must reproduce `return_tenths` exactly. `_record_accepted_position`
    writes `return_tenths = contracts * 1000` from the same number, so a
    disagreement means the row in hand is about some other holding -- the
    `contract_count_disagrees` proof, applied to a second path.
    """
    if rfq_fill is None or rfq_fill["venue_fill_read_ms"] is None:
        return StakeBasis(recorded, STAKE_BASIS_AS_RECORDED, "rfq_accept")
    count = rfq_fill["venue_fill_count"]
    price = rfq_fill["venue_avg_fill_price_tenths"]
    if count is None or price is None:
        return StakeBasis(recorded, STAKE_BASIS_AS_RECORDED, "rfq_fill_unmatched")
    count = float(count)
    if not math.isfinite(count) or count <= 0:
        return StakeBasis(recorded, STAKE_BASIS_AS_RECORDED, "rfq_fill_unmatched")
    exact_return = count * SETTLEMENT_TENTHS
    if abs(exact_return - int(position["return_tenths"])) > 1e-6:
        return StakeBasis(recorded, STAKE_BASIS_AS_RECORDED, "rfq_fill_unmatched")
    return StakeBasis(
        int(round(count * int(price))), STAKE_BASIS_VENUE_FILL, None
    )


def stake_basis_for(
    position: Mapping[str, Any],
    order: Optional[Mapping[str, Any]],
    *,
    rfq_accepted: bool = False,
    rfq_fill: Optional[Mapping[str, Any]] = None,
) -> StakeBasis:
    """Which price this position's stake should be read at.

    `order` is the `manual_orders` row that created it, or `None` when no
    single row could be identified. Every refusal below returns the recorded
    stake with a named reason; **`venue_fill` is returned only when the
    venue's number is readable AND provably about this position.**

    The guards, and why each exists:

    - **`not_a_kalshi_combo`** -- a sportsbook slip has no order row and no
      venue price; the stake is the figure Joe typed and always was.
    - **`hand_recorded_position`** -- a Kalshi combination Joe typed into
      `/hedge` himself rather than buying through the desk. `_order_key`
      cannot be formed, so no order was ever looked for and nothing is
      missing; the stake is the figure he typed. Split out of `no_order_row`
      by issue #56 (answered A, 2026-09-17), because five of his seventeen
      open positions were being told a search had come up empty when no
      search had run -- and a genuine gap could not be seen among them.
    - **`rfq_accept` / `rfq_fill_unmatched`** -- bought by taking a maker's
      quote on an RFQ, which writes a position and no `manual_orders` row at
      all (issue #69). The key IS formed, so this would otherwise report
      `no_order_row` -- a bookkeeping gap -- on a path that is working exactly
      as designed. Since schema v50 the accept path DOES read
      `/portfolio/fills`, so such a position can reach `venue_fill` like any
      other; `_rfq_stake_basis` decides, and the two refusals it can return
      separate "the venue was never asked" from "the venue was asked and did
      not answer for this combination". That sentence said *what Kalshi
      charged is not read on this path* until issue #74.
    - **`no_order_row` / `ambiguous_order_rows`** -- the join key is
      `(combo_ticker, placed_ms)`, and `placed_ms` is the same
      `submitted_ms` the route wrote on the order in the same request
      (`routes.py`, `_write_manual_intent` and `_record_combo_position` take
      one variable). **Both mean the key WAS formed and the lookup DID run**:
      zero matches or more than one means the link is unreadable, and an
      unreadable link resolves to the recorded number, never to a plausible
      one. A position with no key at all is the bullet above, not this one --
      that distinction is the whole of issue #56.
    - **`side_convention_unresolved`** -- `limit_price_tenths` is our side's
      price (`OrderRequest.fill_price_tenths` reflects a NO onto the YES
      book); `venue_avg_fill_price_tenths` is `average_fill_price` verbatim,
      with no reflection applied. On a `side = 'yes'` order the two are one
      convention. On a `side = 'no'` order which book the venue quoted has
      never been established -- the census's A4.3 rule was written for it and
      never exercised, because all thirteen real orders are YES. Reading the
      venue's number there could halve or double the stake, so it is refused
      until something settles it, not guessed.
    - **`no_venue_price` / `no_venue_fill_count`** -- a pre-v40 row, or a row
      whose outcome write failed. The columns say the venue told us
      nothing, which is not the same as a price of zero.
    - **`venue_fill_count_unusable`** -- a count that is present and cannot
      be a holding: zero (an IOC that matched no one), negative, or not
      finite. Distinct from the two above, because a column that answered
      and a column that stayed silent are different facts.
    - **`fractional_venue_fill_count`** -- the route refuses to record a
      position at a truncated size (ADR 0151); this refuses to re-price one
      at a size it cannot reproduce, for the same reason and in the same
      direction.
    - **`contract_count_disagrees`** -- the proof that the joined order is
      the order behind THIS position. `_record_combo_position` writes
      `return_tenths = contracts * 1000` from the same fill count the venue
      reported, so `int(venue_fill_count) * 1000` must equal the stored
      return. When it does not, the row found is about some other holding
      and the count the stake would be multiplied by is not this position's.

    **The venue's fee is deliberately not read.** `venue_avg_fee_dollars` is
    on the same row and stays out: it is REAL dollars, its rounding onto
    integer tenths is undecided, and deciding it here would be a money
    change made in passing. The entry fee stays `combo_entry_fee_tenths`'s
    modelled number (ADR 0145), charged at 0.071 on the stake this function
    returns.
    """
    recorded = int(position["stake_tenths"])
    if _is_adopted_position(position):
        # Checked before `_order_key` even runs: an adopted row is never
        # bought through the desk, so it has no `manual_orders` row and no
        # RFQ acceptance to look for by construction -- the same reason
        # `hand_recorded_position` exists, but a different fact, because the
        # stake here is not a figure Joe typed. It is Kalshi's own reported
        # cost of the holding at adopt time.
        return StakeBasis(recorded, STAKE_BASIS_VENUE_EXPOSURE, "adopted_from_positions")
    if str(position["source"]) != "kalshi_combo":
        return StakeBasis(recorded, STAKE_BASIS_AS_RECORDED, "not_a_kalshi_combo")
    if order is None:
        # Which of the three: a key that could not be formed means no lookup
        # ever ran; a key formed on the RFQ path has nothing to find by
        # construction; a key formed on the order path and matching nothing is
        # a gap in the books. One sentence for all of them hides the gap among
        # the designed states, which is the defect issue #56 fixed once.
        if _order_key(position) is None:
            return StakeBasis(
                recorded, STAKE_BASIS_AS_RECORDED, "hand_recorded_position"
            )
        if rfq_accepted:
            return _rfq_stake_basis(position, rfq_fill, recorded)
        return StakeBasis(recorded, STAKE_BASIS_AS_RECORDED, "no_order_row")
    if str(order["side"]) != "yes":
        return StakeBasis(
            recorded, STAKE_BASIS_AS_RECORDED, "side_convention_unresolved"
        )
    price = order["venue_avg_fill_price_tenths"]
    if price is None:
        return StakeBasis(recorded, STAKE_BASIS_AS_RECORDED, "no_venue_price")
    count = order["venue_fill_count"]
    if count is None:
        return StakeBasis(recorded, STAKE_BASIS_AS_RECORDED, "no_venue_fill_count")
    count = float(count)
    if not math.isfinite(count) or count <= 0:
        return StakeBasis(
            recorded, STAKE_BASIS_AS_RECORDED, "venue_fill_count_unusable"
        )
    if count != int(count):
        return StakeBasis(
            recorded, STAKE_BASIS_AS_RECORDED, "fractional_venue_fill_count"
        )
    contracts = int(count)
    if contracts * SETTLEMENT_TENTHS != int(position["return_tenths"]):
        return StakeBasis(
            recorded, STAKE_BASIS_AS_RECORDED, "contract_count_disagrees"
        )
    return StakeBasis(contracts * int(price), STAKE_BASIS_VENUE_FILL, None)


#: More than one `manual_orders` row answered to a position's join key. A
#: distinct value from `None` (no row at all) because the two are different
#: facts and the screen's reason vocabulary names them separately.
_AMBIGUOUS = object()


def stake_bases(
    conn: sqlite3.Connection, positions: Sequence[Mapping[str, Any]]
) -> dict[int, StakeBasis]:
    """`stake_basis_for` over a screenful of positions, in one bounded read.

    The read is bounded twice -- by the open positions' own tickers and by
    their own `placed_ms` -- so it can never widen into a scan of the order
    history as `manual_orders` grows. There is no index on that table today
    and it held thirteen real rows on 2026-09-15; if it ever grows enough for
    the scan to matter, an index is the fix and a version bump is its price.

    A row that cannot be joined is simply absent from the order map, and
    `stake_basis_for` returns the recorded stake with `no_order_row` -- or
    with `hand_recorded_position`, when the position had no key to look one
    up by, or with `rfq_accept`, when an executed RFQ acceptance answers the
    same key and there was never a `manual_orders` row to find. This function
    raises nothing: a bookkeeping read must not be able to take the hedge
    screen down.

    **The second read is bounded by the same two lists as the first**, so
    adding it cannot turn this into a scan of the quote history as
    `combo_rfq_quotes` grows -- the same discipline the order read is held
    to, and the reason `/api/hedge` is not on the list of routes that walk a
    table (ADR 0167, 0168).
    """
    bases: dict[int, StakeBasis] = {}
    wanted = {k for k in (_order_key(p) for p in positions) if k is not None}
    orders: dict[tuple[str, int], Any] = {}
    if wanted:
        tickers = sorted({t for t, _ in wanted})
        stamps = sorted({ms for _, ms in wanted})
        try:
            rows = conn.execute(
                "SELECT ticker, submitted_ms, side, venue_fill_count, "
                "venue_avg_fill_price_tenths FROM manual_orders "
                "WHERE dry_run = 0 "
                f"AND ticker IN ({','.join('?' * len(tickers))}) "
                f"AND submitted_ms IN ({','.join('?' * len(stamps))})",
                (*tickers, *stamps),
            ).fetchall()
        except sqlite3.Error:
            logger.exception(
                "the manual-order rows behind the open positions could not be "
                "read; every stake falls back to the figure recorded with it."
            )
            rows = []
        for row in rows:
            key = (str(row["ticker"]), int(row["submitted_ms"]))
            if key not in wanted:
                continue
            # A second row on the same key makes the link unreadable. The
            # sentinel says so rather than letting the last row win, which is
            # how a stake gets built on some other bet's fill.
            orders[key] = _AMBIGUOUS if key in orders else row
    # Which of those keys an executed RFQ acceptance answers. Empty is the
    # common case and costs one bounded read; it is read even when every key
    # found an order, because a position answering both would be a fact worth
    # seeing rather than one to resolve by ordering.
    accepted: dict[tuple[str, int], Any] = {}
    if wanted:
        marks = ",".join("?" * len(QUOTE_FILLED_STATUSES))
        try:
            quote_rows = conn.execute(
                "SELECT r.ticker AS ticker, q.accepted_ms AS accepted_ms, "
                "       q.venue_fill_read_ms AS venue_fill_read_ms, "
                "       q.venue_fill_count AS venue_fill_count, "
                "       q.venue_avg_fill_price_tenths "
                "           AS venue_avg_fill_price_tenths "
                "FROM combo_rfq_quotes q "
                "JOIN combo_rfqs r ON r.rfq_id = q.rfq_id "
                "WHERE q.accept_dry_run = 0 "
                f"AND q.outcome_status IN ({marks}) "
                f"AND r.ticker IN ({','.join('?' * len(tickers))}) "
                f"AND q.accepted_ms IN ({','.join('?' * len(stamps))})",
                (*QUOTE_FILLED_STATUSES, *tickers, *stamps),
            ).fetchall()
        except sqlite3.Error:
            logger.exception(
                "the RFQ acceptances behind the open positions could not be "
                "read; a position bought that way reports no_order_row, which "
                "understates it as a gap rather than overstating its stake."
            )
            quote_rows = []
        for row in quote_rows:
            key = (str(row["ticker"]), int(row["accepted_ms"]))
            # **Not a guard, and it is written down as one.** Mutating this
            # filter away leaves the suite green, because the SQL is already
            # bounded by the same two lists and a key that matches no open
            # position is never looked up below. It mirrors the order read's
            # identical line so the two halves of this function read the
            # same; the real claim -- that one acceptance explains ONE
            # position and not the screenful -- is the loop below and IS
            # tested (`test_a_position_with_no_acceptance_keeps_its_own_reason`).
            if key in wanted:
                # Last row wins is wrong here for the same reason it is wrong
                # on the order read, so it is not done: a second acceptance
                # answering one position's key is refused by the same
                # `_AMBIGUOUS` shape.
                accepted[key] = _AMBIGUOUS if key in accepted else row

    for position in positions:
        key = _order_key(position)
        order = orders.get(key) if key is not None else None
        if order is _AMBIGUOUS:
            bases[int(position["id"])] = StakeBasis(
                int(position["stake_tenths"]),
                STAKE_BASIS_AS_RECORDED,
                "ambiguous_order_rows",
            )
            continue
        fill = accepted.get(key) if key is not None else None
        if fill is _AMBIGUOUS:
            bases[int(position["id"])] = StakeBasis(
                int(position["stake_tenths"]),
                STAKE_BASIS_AS_RECORDED,
                "rfq_fill_unmatched",
            )
            continue
        bases[int(position["id"])] = stake_basis_for(
            position,
            order,
            rfq_accepted=key is not None and key in accepted,
            rfq_fill=fill,
        )
    return bases


def _optional(position: Mapping[str, Any], key: str) -> Any:
    """A field that exists only on a mapping `position_at_basis` built.

    `None` on a raw `parlay_positions` row, which is the truth about it: that
    row was never resolved against an order, so nothing here knows whose
    price its stake is. It is not a claim that the stake is the venue's.
    """
    if isinstance(position, sqlite3.Row):
        return position[key] if key in position.keys() else None
    try:
        return position[key]
    except (KeyError, IndexError):
        return None


def position_at_basis(
    position: Mapping[str, Any], basis: StakeBasis
) -> dict[str, Any]:
    """The position row with its stake read at `basis`, for everything
    downstream.

    A plain dict rather than a second parameter threaded through `assess`,
    `entry_fee_tenths` and `serialise_position`: those three must agree about
    what the stake is, and three ways of being told is three ways to drift.
    The swap is not silent -- `stake_basis` and `stake_basis_reason` travel in
    the same mapping and out to `/api/hedge`, so a reader can always tell
    which number the figures were built on.
    """
    resolved = dict(position)
    resolved["stake_tenths"] = int(basis.stake_tenths)
    resolved["stake_basis"] = basis.basis
    resolved["stake_basis_reason"] = basis.reason
    return resolved


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
    conn: sqlite3.Connection,
    *,
    position_id: int,
    now_ms: int,
    status: str,
    source: str,
    reason: str | None = None,
) -> bool:
    """Move one open ticket off `open`, saying who did it.

    `source` is required and is the row's provenance (`closed_source`):
    `'manual'` is Joe's tap, `'venue'` is `close_settled_combinations`. The
    same two words, and the same shape, as `resolve_leg` one table down --
    one writer with a required argument rather than a sibling function, so
    the `status = 'open'` guard and the `rowcount` contract exist once and
    cannot drift apart. A missing `source` is a `TypeError` at the call
    site, never a silent NULL: NULL on this column means "closed before the
    column existed" and nothing written today may look like that.

    `reason` (`closed_reason`, v55) is set only when the desk closed the row
    on its own for a reason other than the venue's settlement: `'lost_leg'`
    is `close_dead_hand_recorded`. A tap and the venue pass leave it NULL.
    """
    if status not in ("settled", "closed", "void"):
        raise ValueError(f"status must be settled/closed/void, got {status!r}")
    if source not in ("venue", "manual"):
        raise ValueError(f"source must be venue/manual, got {source!r}")
    if reason not in (None, "lost_leg"):
        raise ValueError(f"reason must be None or lost_leg, got {reason!r}")
    cursor = conn.execute(
        "UPDATE parlay_positions SET status = ?, closed_ms = ?, "
        "closed_source = ?, closed_reason = ? "
        "WHERE id = ? AND status = 'open'",
        (status, now_ms, source, reason, position_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def close_settled_combinations(
    conn: sqlite3.Connection, *, now_ms: int
) -> list[int]:
    """Close every open combination the venue has already settled.

    Joe's (A) to #131 (2026-09-22, ADR 0181, amending ADR 0136's "why no
    auto-close"): once Kalshi reports the settlement of a combination he
    holds, the record should say what the venue says, without waiting for
    his tap. The trigger is **the venue's own settlement of the combination
    market** -- a `venue_settlements` row on the position's `combo_ticker`,
    read through the same `combo_settlements` lookup the screen uses, so the
    record and the screen cannot disagree about which rows are settled. It
    is deliberately narrower than the screen's `nothing_pending` predicate:
    every leg having resolved does NOT close a row (option (B), offered and
    not chosen), because the legs are the desk's own reading and the venue's
    settlement is the venue's.

    What this does not do, and does not establish:

    - It never touches a hand-recorded slip. Those carry no `combo_ticker`
      (`record_position` defaults it to `None` for the hand-typed route), so
      the venue cannot see them and the join cannot reach them. Disjoint by
      construction, not by a second filter. Since #143 (Joe's (A) to #142)
      such a slip closes by `close_dead_hand_recorded` once a leg has lost,
      or by his tap -- never by this pass.
    - It never marks a leg. A combination's `market_result` says nothing
      about which leg lost (ADR 0136, reason 2, which stands); legs keep
      resolving from `kalshi_markets.result` or by hand.
    - It never deletes. `status` moves to `'settled'` -- Joe's word in #131,
      already in the table's CHECK -- with `closed_ms = now_ms` (when the
      record closed, not when the venue settled; the venue's `settled_ms`
      and `market_result` are already served on the row by the same join)
      and `closed_source = 'venue'`.
    - A closed row is not displayed anywhere: `open_positions` is the only
      reader of `status`, so the first pass after this ships empties the
      settled group on `/hedge`. Joe chose (A) knowing that.

    Returns the ids it closed, in record order. Runs on the watcher's cycle
    (`hedge_watch.watch_hedges_forever`), before the "anything live" gate,
    because that gate is false exactly when every leg has resolved -- the
    common state of a settled combination -- and a pass behind it would
    only close settled rows while some OTHER ticket was live.
    """
    positions = [
        row for row in open_positions(conn) if row["combo_ticker"] is not None
    ]
    if not positions:
        return []
    settlements = combo_settlements(
        conn, [str(row["combo_ticker"]) for row in positions]
    )
    closed: list[int] = []
    for row in positions:
        settlement = settlements.get(str(row["combo_ticker"]))
        if settlement is None:
            continue
        if close_position(
            conn,
            position_id=int(row["id"]),
            now_ms=now_ms,
            status="settled",
            source="venue",
        ):
            logger.info(
                "hedge: position %s closed by the venue's settlement of %s "
                "(market_result=%r, settled_ms=%s)",
                row["id"],
                row["combo_ticker"],
                settlement["market_result"],
                settlement["settled_ms"],
            )
            closed.append(int(row["id"]))
    return closed


def close_dead_hand_recorded(
    conn: sqlite3.Connection, *, now_ms: int
) -> list[int]:
    """Close every open hand-recorded slip one of whose legs has lost.

    Joe's (A) to #142 (2026-09-23, #143, amending ADR 0181): a parlay with a
    lost leg cannot win -- `assess` already calls it `STATE_DEAD` -- and a
    slip typed in by hand has no venue settlement that would ever close it,
    so before this it sat on `/hedge` until he tapped it. The row moves to
    `status = 'settled'` with `closed_reason = 'lost_leg'`, and
    `closed_source` names who resolved the losing leg: `'venue'` if any lost
    leg was resolved from Kalshi's market result, otherwise `'manual'` (he
    marked it). A tap on the row itself leaves `closed_reason` NULL, so the
    two stay distinguishable.

    What this does not do:

    - It never touches an order-linked combination (`combo_ticker` set).
      Those still close only on the venue's own settlement
      (`close_settled_combinations`; option (B) to #131 is still not chosen
      for them), because the venue will settle them and the record should
      say what the venue says.
    - A `void` leg closes nothing (`STATE_VOID_LEG` is still live).
    - It never marks a leg and never deletes a row.
    """
    rows = conn.execute(
        "SELECT p.id AS id, "
        "MAX(CASE WHEN l.resolved_source = 'venue' THEN 1 ELSE 0 END) AS by_venue "
        "FROM parlay_positions p "
        "JOIN parlay_position_legs l ON l.position_id = p.id "
        "WHERE p.status = 'open' AND p.combo_ticker IS NULL "
        "AND l.outcome = 'lost' "
        "GROUP BY p.id ORDER BY p.id"
    ).fetchall()
    closed: list[int] = []
    for row in rows:
        source = "venue" if row["by_venue"] else "manual"
        if close_position(
            conn,
            position_id=int(row["id"]),
            now_ms=now_ms,
            status="settled",
            source=source,
            reason="lost_leg",
        ):
            logger.info(
                "hedge: hand-recorded position %s closed by the desk: a leg "
                "has lost (resolved by %s)",
                row["id"],
                source,
            )
            closed.append(int(row["id"]))
    return closed


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


async def adopt_venue_combo(
    conn: sqlite3.Connection,
    *,
    api: Any,
    ticker: str,
    now_ms: int,
) -> int:
    """Put a KXMVE combination `unrecorded_at_venue` names under `/hedge`'s
    watch, in one tap. #148.

    `unrecorded_at_venue` (above) tells Joe "Record it below" for a
    combination the venue holds that no open `parlay_positions` row is
    watching -- but `RecordParlay.tsx` has no combination-ticker field, so
    that instruction could not be followed. This is the tap that follows it.

    **Everything about the row comes from the venue's OWN read, never from
    a request beyond the ticker.** Contracts and `exposure_tenths` are the
    LATEST COMPLETE `positions` poll's own numbers for this ticker
    (`_latest_ok_positions_poll`, the same selector `unrecorded_at_venue`
    uses) -- never a fresh venue call, so the size adopted is the size the
    screen just showed, not a second read that could disagree with it. The
    legs come from the venue's own market, `GET /markets/{ticker}` read
    through `mve_legs` (`backend/kalshi/rfq.py`) -- the fixture this desk's
    own tests read that shape from is `tests/fixtures/combo_lookup_response.
    json`, the RFQ lookup response, accepted through the same `{"market":
    ...}` envelope `GET /markets/{ticker}` answers with (pinned against
    `market_single.json`'s `single` key) -- the same source
    `backend/combo_rfq.py`'s sell-quote path (#96) uses for an RFQ-accepted
    position that recorded no lookup -- an adopted position is exactly that
    shape, one tap earlier.

    Refusals, each named, none of them reaching the venue except the last two:

    - `ticker` is not `KXMVE*` -- this screen watches combinations only,
      the same restriction `unrecorded_at_venue`'s own `LIKE 'KXMVE%'` states.
    - there has been no complete `positions` poll, or this ticker is not
      among its rows -- coverage is unknown or the venue does not (or no
      longer) shows it held.
    - the poll's own `side` for this ticker is not `'yes'` -- **a NO holding
      is refused, never adopted as YES.** `portfolio_poll.parse_position`
      stores every holding's size as `abs(position_fp)` with `side` carrying
      the sign, so reading `contracts`/`exposure_tenths` alone cannot tell a
      NO position from a YES one of the same size -- adopting it blind would
      silently buy the opposite side of what Joe holds. ADR 0160 already
      refuses rather than guesses on a `side = 'no'` order
      (`stake_basis_for`'s `side_convention_unresolved`); this is the same
      rule at the adopt boundary, where the cost of guessing wrong is a
      position that says the opposite of what is actually held.
    - an OPEN `parlay_positions` row already claims this ticker -- adopting
      again would double the exposure this desk believes it is watching.
      Checked twice: once here, cheaply, before any venue call, and once
      more immediately before the write (see below) -- a second request for
      the same ticker can race this one across the `await` in between, and
      only the second check closes that window.
    - the venue's market for this ticker carries no `mve_selected_legs`, or
      one of its legs names no readable `side` -- `mve_legs` raises
      `RfqRefused` for the first; the second is checked here, because a leg
      whose side is neither `'yes'` nor `'no'` is not a leg this desk knows
      how to price or label, and guessing `'yes'` (the pre-review shape of
      this function) would misdescribe a real NO leg -- KXMVE combos carry
      them routinely (`tests/fixtures/combo_priced_markets.json`, e.g.
      `KXWNBASPREAD-26AUG09LVNY-NY13` at `side: "no"`).

    `stake_tenths` is the venue's own `exposure_tenths` -- Kalshi's own
    `market_exposure_dollars` for the holding, **inferred to be the amount
    paid, fee-exclusive, and never itself measured against a fill**: an
    adopted row has no `manual_orders` row and no RFQ acceptance behind it
    by construction, so the E2 census's "sent price vs. venue charge" check
    (`stake_basis_for`, `estimate_grain`) has nothing to compare it to, and
    what `market_exposure_dollars` becomes after a PARTIAL sell of the same
    holding has never been read on this instance. `return_tenths` is
    `contracts * 1000` (one dollar a contract, per CLAUDE.md's
    tenths-of-a-cent convention), rounded to the nearest tenth:
    `venue_positions.contracts` is a fractional holding (`position_fp`), not
    the integer count an order-path fill carries.

    Each leg's label is `kalshi_markets.title` where this instance's own
    market ingest has seen that leg's market, prefixed `"NO -- "` when the
    leg's own side is `'no'` -- the order path (`routes.py::
    _record_combo_position`, `parlays.leg_details_for`) has no convention
    for this because every leg it has ever recorded carries a label already
    chosen to describe the side bought, and an adopted leg has no such
    upstream choice behind it. Falls back to the bare ticker, prefixed the
    same way, where no title is on file -- the same "degrade to the ticker,
    never invent a title" rule `parlays.legs_for_position` states for
    `labels_are_tickers`. The overall position label is the comma-joined leg
    labels when every leg has a title on file, and the bare ticker otherwise.

    Raises `parlays.LookupRefused` on every refusal above, carrying the
    HTTP status the route answers with. Imported locally, the same reason
    `_scout_states_at_bet` above gives: `parlays` is a large module this one
    otherwise avoids pulling in at import time.
    """
    from .parlays import LookupRefused

    if not ticker.startswith("KXMVE"):
        raise LookupRefused(
            422,
            f"{ticker!r} is not a KXMVE combination ticker, and this desk "
            "only adopts combinations. Nothing was adopted.",
        )

    poll = _latest_ok_positions_poll(conn)
    if poll is None:
        raise LookupRefused(
            404,
            "There has never been a complete read of Kalshi's positions on "
            "this instance, so nothing is known to adopt. Nothing was "
            "adopted.",
        )
    venue_row = conn.execute(
        "SELECT contracts, exposure_tenths, side FROM venue_positions "
        "WHERE poll_log_id = ? AND ticker = ?",
        (int(poll["id"]), ticker),
    ).fetchone()
    if venue_row is None:
        raise LookupRefused(
            404,
            f"Kalshi's latest positions read does not show {ticker} held. "
            "Nothing was adopted.",
        )
    if venue_row["side"] != "yes":
        raise LookupRefused(
            422,
            f"Kalshi shows {ticker} held on the {venue_row['side'] or 'unknown'} "
            "side, and this desk only adopts a YES holding -- reflecting a "
            "NO holding onto a YES position has never been established "
            "(ADR 0160). Nothing was adopted.",
        )
    if venue_row["contracts"] is None or venue_row["exposure_tenths"] is None:
        raise LookupRefused(
            502,
            f"Kalshi's read of {ticker} could not be priced (contracts or "
            "exposure was unreadable). Nothing was adopted.",
        )

    already_open = conn.execute(
        "SELECT 1 FROM parlay_positions WHERE status = 'open' "
        "AND combo_ticker = ?",
        (ticker,),
    ).fetchone()
    if already_open is not None:
        raise LookupRefused(
            409,
            f"{ticker} is already watched by an open position on this "
            "desk. Nothing was adopted.",
        )

    try:
        market_payload = await api.get(f"/markets/{ticker}")
    except Exception as exc:  # noqa: BLE001 -- transport; nothing was adopted
        raise LookupRefused(
            502,
            f"Kalshi's market for {ticker} could not be read ({exc}). "
            "Nothing was adopted.",
        ) from exc
    try:
        _collection, venue_legs = mve_legs(market_payload)
    except RfqRefused as exc:
        raise LookupRefused(
            422,
            f"Kalshi's market for {ticker} carries no legs to watch: "
            f"{exc}. Nothing was adopted.",
        ) from exc

    leg_tickers = [
        str(leg["market_ticker"])
        for leg in venue_legs
        if leg.get("market_ticker")
    ]
    titles: dict[str, str] = {}
    if leg_tickers:
        placeholders = ",".join("?" for _ in leg_tickers)
        for row in conn.execute(
            f"SELECT ticker, title FROM kalshi_markets "
            f"WHERE ticker IN ({placeholders})",
            tuple(leg_tickers),
        ):
            if row["title"]:
                titles[str(row["ticker"])] = str(row["title"])

    legs: list[dict] = []
    every_leg_titled = True
    for leg in venue_legs:
        leg_ticker = leg.get("market_ticker")
        leg_side = leg.get("side")
        if leg_side not in ("yes", "no"):
            raise LookupRefused(
                422,
                f"Kalshi's market for {ticker} names a leg "
                f"({leg_ticker!r}) with no readable side ({leg_side!r}). "
                "Nothing was adopted.",
            )
        title = titles.get(str(leg_ticker)) if leg_ticker else None
        if title is None:
            every_leg_titled = False
            base_label = leg_ticker
        else:
            base_label = title
        label = f"NO -- {base_label}" if leg_side == "no" else base_label
        legs.append(
            {
                "ticker": leg_ticker,
                "event_ticker": leg.get("event_ticker"),
                "side": leg_side,
                "label": label,
            }
        )
    if legs and every_leg_titled:
        position_label = ", ".join(leg["label"] for leg in legs)
    else:
        position_label = ticker

    contracts = float(venue_row["contracts"])
    return_tenths = int(round(contracts * 1000))
    stake_tenths = int(venue_row["exposure_tenths"])

    note = (
        f"{ADOPTED_NOTE_MARKER} Recorded automatically from Kalshi's own "
        "positions read -- adopted, not bought through this desk. A "
        "combination can be sold back, though selling back may cost more "
        "than holding it to the outcome; a hedge is the exit the desk "
        "watches, not the only one that exists."
    )

    # **The race this closes.** The already-open check above ran before the
    # `await` on the venue's market -- cheap, and enough to short-circuit
    # the common case -- but a second request for the same ticker can start
    # during that await and finish first. `BEGIN IMMEDIATE` takes the write
    # lock before the recheck runs, so a concurrent writer blocks here
    # rather than interleaving with it; `record_position`'s own `commit()`
    # closes this same transaction, Python's sqlite3 module tracking one
    # open transaction per connection regardless of whether it was opened by
    # this explicit `BEGIN` or by the first write statement inside it.
    conn.execute("BEGIN IMMEDIATE")
    still_open = conn.execute(
        "SELECT 1 FROM parlay_positions WHERE status = 'open' "
        "AND combo_ticker = ?",
        (ticker,),
    ).fetchone()
    if still_open is not None:
        conn.rollback()
        raise LookupRefused(
            409,
            f"{ticker} is already watched by an open position on this "
            "desk -- another request adopted it first. Nothing was "
            "adopted.",
        )
    try:
        return record_position(
            conn,
            now_ms=now_ms,
            source="kalshi_combo",
            label=position_label,
            stake_tenths=stake_tenths,
            return_tenths=return_tenths,
            legs=legs,
            combo_ticker=ticker,
            note=note,
        )
    except PositionRefused as exc:
        conn.rollback()
        raise LookupRefused(422, exc.refusal.detail) from exc
    except BaseException:
        # Anything else (a CHECK constraint, a locked file) must not leave
        # the write lock `BEGIN IMMEDIATE` took held on this connection.
        conn.rollback()
        raise


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
    # PLUS the taker fee the venue charged on entry, which the stored
    # `stake_tenths` does not carry -- `routes._record_combo_position` writes
    # a price times a count and no fee. Left out, every branch of every rung
    # reads too high by the fee -- ~17 tenths a contract at 41c, the size of
    # the smallest floors `Lock.is_guaranteed_profit` fires on. ADR 0145. A
    # sportsbook slip has no separate fee: its vig is inside the price
    # already typed.
    #
    # **Which price the stake itself is at was decided by the caller**, not
    # here: `build_payload` runs `stake_bases` and hands this a mapping whose
    # `stake_tenths` is the venue's own fill price where that was readable
    # and the recorded figure otherwise, with `stake_basis` beside it saying
    # which. A mapping that never went through `position_at_basis` -- a raw
    # row, in a test -- reads exactly as it did before, the number as stored.
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
            "One leg left and every other has won, so a hedge here has an "
            "answer either way — an estimate, not an exact one."
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


#: E2 as the registered census of 2026-09-15 found it: on the twelve
#: hand-bet fills that carried a venue price, the price the desk sent was
#: the venue's on eleven and 22 tenths a contract above it on one. Counts,
#: not a rate -- twelve rows, one stratum (`KXMVE` shard 1, every order
#: YES), and nothing about the next fill. The result doc (§5) and CLAUDE.md
#: carry the same three numbers; change them there and here together.
E2_CENSUS_ROWS = 12
E2_CENSUS_ROWS_AT_ZERO = 11
E2_CENSUS_MAX_TENTHS_PER_CONTRACT = 22

_WORDS = {11: "eleven", 12: "twelve"}


def estimate_grain(position: Mapping[str, Any], outcome: Lock) -> Optional[str]:
    """The size of the largest MEASURED error term on this ticket's figure,
    in dollars for this ticket, as one sentence the screen sets beside the
    number at the number's own size. Issue #43, answer A.

    **Not a combined error bar, and not a bound.** Four terms sit on the
    figure (CLAUDE.md, E1-E4) and they do not share a sign, so no single
    number is the figure's uncertainty and none is offered. What can be said
    honestly per position is what one term would come to HERE if it ran as
    observed, and which term that is depends on the ticket:

    - **A Kalshi combo whose stake is still the price the desk sent**
      carries E2, the sent-versus-charged stake: the census observed it at
      22 tenths a contract on one of twelve rows and zero on the other
      eleven, and it is the largest measured term (the result doc, §5).
      `return_tenths` is `contracts * 1000` on a recorded combo
      (`routes._record_combo_position`), so the contract count is read back
      from it and the observed gap is dollarised for this ticket. A return
      that is not a whole number of contracts was typed by hand and the
      count is unreadable; the sentence then carries the per-contract figure
      and no dollar figure, rather than a rounded one.
    - **A Kalshi combo whose stake is the venue's own fill price**
      (`stake_basis == STAKE_BASIS_VENUE_FILL`) does not carry E2 at all:
      the figure was built on what Kalshi charged, so quoting the gap
      between the sent price and the charge would name an error that is not
      on this ticket. It falls through to E4 with the slips, which is then
      its largest measured term. **This branch and the stake basis ship
      together** -- a caveat naming a condition is falsified by fixing the
      condition, and the fix and the copy go in one commit or the screen
      lies in between.
    - **A Kalshi combo `adopt_venue_combo` (#148) wrote**
      (`stake_basis == STAKE_BASIS_VENUE_EXPOSURE`) does not carry E2
      either, for a related but distinct reason: E2 names the gap between
      the price the DESK sent and what Kalshi charged, and an adopted row
      never had a price the desk sent -- there is no order and no RFQ
      acceptance behind it. Quoting E2 on it would describe a sent price
      that never existed. It falls through to E4 with the slips, same as a
      `venue_fill` combo. `stakeBasisNote` (`frontend/src/lib/
      stakeBasisGloss.ts`) carries the caveat this term would have named --
      that the stake is inferred and never itself measured against a fill.
    - **A sportsbook slip** has no sent price -- the stake is what Joe typed
      -- so E2 is not a term on it. Its measured term is E4, the hedge fee
      charged at the flat 0.070 where nine baseball fills pinned k at half
      that (ADR 0028). The fee the rung already charges is named in dollars.

    `None` when there is no figure to set it beside (`best_available` is
    `None`) -- the screen shows no number then and owes no grain for one.
    The words to refuse (ceiling, floor, conservative, at least, can only be
    smaller/larger) are refused by `tests/test_hedge_positions.py`.
    """
    rung = outcome.best_available
    if rung is None:
        return None
    if (
        str(position["source"]) == "kalshi_combo"
        and _optional(position, "stake_basis")
        not in (STAKE_BASIS_VENUE_FILL, STAKE_BASIS_VENUE_EXPOSURE)
    ):
        return_tenths = int(position["return_tenths"])
        observed = (
            f"one of {_WORDS[E2_CENSUS_ROWS]} fills read was "
            f"{E2_CENSUS_MAX_TENTHS_PER_CONTRACT / 10:g}c a contract off the "
            f"price the desk sent and {_WORDS[E2_CENSUS_ROWS_AT_ZERO]} matched it"
        )
        if return_tenths <= 0 or return_tenths % 1000 != 0:
            return observed
        contracts = return_tenths // 1000
        gap = format_dollars(E2_CENSUS_MAX_TENTHS_PER_CONTRACT * contracts)
        return f"{observed}; on this ticket's {contracts} contracts that is {gap}"
    return (
        f"the hedge fee here, {format_dollars(rung.fee_tenths)}, is the flat "
        "rate; the nine baseball fills measured paid half that rate"
    )


def _hedge_payload(
    assessment: Assessment, position: Mapping[str, Any]
) -> Optional[dict]:
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
                # `guaranteed` is the alert predicate's name (`Lock.
                # is_guaranteed_profit`; `notify/alerts.py`, `notify/discord.py`
                # and the tests read it) and it survived issue #43 for that
                # blast radius. The screen renders the figure it flags as
                # "about $X either way — an estimate", never as guaranteed.
                "guaranteed": outcome.is_guaranteed_profit,
                "guaranteed_display": (
                    format_dollars(outcome.best_available.floor_tenths)
                    if outcome.best_available is not None
                    else None
                ),
                # Rendered beside the figure at the figure's size. See
                # `estimate_grain` for what it is and is not.
                "uncertainty_display": estimate_grain(position, outcome),
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
        # The game, as Kalshi titles it. `None` on rows recorded before v43
        # and on a hand-typed slip; the screen prints the label alone then.
        "event_title": leg["event_title"],
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


async def combo_book_state(
    combo_ticker: Optional[str],
    *,
    read_combo_book,
    now_ms: int,
) -> tuple[Optional[dict], Optional[str]]:
    """What the public order book says a held combination could be sold back
    for right now -- five states, and they never collapse (#95, D1/D2 of the
    2026-09-21 review).

    Returns `(combo_book, combo_book_reason)`; exactly one of them carries
    information on any given call:

    - `combo_book` is a dict with `state` in `{bid, empty, unpriced_interest,
      unreadable}` and `combo_book_reason` is `None` -- a read was attempted,
      because there was a ticket to read and a reader to read it with.
    - `combo_book` is `None` and `combo_book_reason` names why no read was
      even attempted: `no_ticket` (`combo_ticker` is `None` -- a
      hand-recorded slip, `hand_recorded_position`, ADR 0160 Amendment 2) or
      `no_reader_wired` (`read_combo_book` is `None`, which is every caller
      of `build_payload` until main wires the real reader in #128 --
      including the demo deploy, where `combo_api()` holds no key).

    A read attempted and a read that FAILED are not the same state either.
    `read_books` (leg quotes, above) intentionally drops a failed ticker from
    its dict -- fine there, because that dict's absence already has one
    meaning. Reused here it would make "the read 403'd" and "nobody is
    bidding" the same pixel, which review D1 named the critical defect this
    ticket exists to fix -- so failures are caught here, not upstream, and
    rendered as `unreadable`, an explicit state of their own.

    `OrderBook.apply_snapshot`'s `dollars_to_tenths_exact` path REFUSES a
    price finer than a tenth of a cent rather than rounding it up (#106); such
    a level is `has_unpriced_interest("yes")`, not a rounded `bid` -- the
    house rule against a floor in the display path (CLAUDE.md, "unreadable
    resolves to `None`, never `0`") applies to a price this desk cannot show,
    not only to one it cannot read at all.
    """
    if combo_ticker is None:
        return None, COMBO_BOOK_REASON_NO_TICKET
    if read_combo_book is None:
        return None, COMBO_BOOK_REASON_NO_READER_WIRED
    try:
        payload = await read_combo_book(str(combo_ticker))
        book = OrderBook(str(combo_ticker))
        book.apply_snapshot(payload, seq=None, observed_ms=now_ms)
    except Exception as exc:                                    # noqa: BLE001
        # Transport, a malformed envelope (`MalformedOrderbookResponse`), an
        # unparseable level (`MalformedBookMessage`) -- every one of them
        # means the same thing on the wire: this read failed. That is the
        # state, not an absence.
        logger.info("combo book read failed for %s: %s", combo_ticker, exc)
        return {
            "state": COMBO_BOOK_UNREADABLE,
            "observed_ms": now_ms,
            "price_display": None,
            "size": None,
        }, None
    best = book.best_yes_bid
    if best is not None:
        return {
            "state": COMBO_BOOK_BID,
            "observed_ms": book.updated_ms,
            "price_display": format_price(best),
            "size": book.yes_bids.get(best),
        }, None
    if book.has_unpriced_interest("yes"):
        return {
            "state": COMBO_BOOK_UNPRICED_INTEREST,
            "observed_ms": book.updated_ms,
            "price_display": None,
            "size": None,
        }, None
    return {
        "state": COMBO_BOOK_EMPTY,
        "observed_ms": book.updated_ms,
        "price_display": None,
        "size": None,
    }, None


def serialise_position(
    position: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
    books: Mapping[str, MarketBook],
    assessment: Assessment,
    *,
    now_ms: int,
    venue_tickers: Optional[set[str]] = None,
    venue_settlement: Optional[Mapping[str, Any]] = None,
    combo_book: Optional[dict] = None,
    combo_book_reason: Optional[str] = None,
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
        # WHOSE price that stake is. `venue_fill` means Kalshi's own average
        # fill price times the contract count it reported; `as_recorded`
        # means the figure stored with the position -- the ask the desk sent,
        # or Joe's typed stake on a slip -- and `stake_basis_reason` names
        # why the venue's number could not be used. Two prices exist for
        # every hand bet (ADR 0143 §4, and the ticket Joe closed with it) and
        # a stake that does not say which one it is cannot be audited.
        # `None` on a mapping that never went through `position_at_basis`.
        "stake_basis": _optional(position, "stake_basis"),
        "stake_basis_reason": _optional(position, "stake_basis_reason"),
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
        # complete poll to check it against; `None` otherwise. This field
        # closes nothing: absence from a poll is not a settlement (ADR 0136,
        # reason 1). What DOES close a combination's row is the venue's own
        # settlement, on the watcher's cycle (`close_settled_combinations`,
        # ADR 0181); a hand-recorded slip is still closed only by Joe's tap.
        "at_venue": _at_venue(position, venue_tickers),
        # The venue's own settlement of the COMBO market, verbatim, or `None`
        # when unsettled. Distinct from `at_venue`: a combo can settle before
        # its leg markets do, so this can be non-null while every leg below
        # still reads `pending` -- which leg lost is not knowable from this
        # alone, and nothing here marks one.
        "venue_settlement": dict(venue_settlement) if venue_settlement else None,
        # What the public book says this combination could be sold back for
        # right now, or `None` with `combo_book_reason` naming why no read
        # was attempted (#95). Absent entirely from every position recorded
        # before this ticket's caller passes them -- `combo_book_state`'s
        # docstring is the source of truth for the five states.
        "combo_book": dict(combo_book) if combo_book else None,
        "combo_book_reason": combo_book_reason,
        "legs": [
            _leg_payload(
                leg, books, hedge_leg_id=assessment.hedge_leg_id, now_ms=now_ms
            )
            for leg in legs
        ],
        "hedge": _hedge_payload(assessment, position),
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
    read_combo_book=None,
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

    `read_combo_book` is keyword-only, defaulted to `None`, and DECIDED here
    (#95) rather than by whoever calls this: `ticker -> awaitable[dict]`,
    matching `KalshiRestClient.orderbook`'s shape exactly so main can pass
    the bound method straight through with no wrapper. With `None` -- every
    caller today -- every `kalshi_combo` position's `combo_book` renders the
    "not applicable" state with reason `no_reader_wired`; nothing 503s and
    nothing lies. **This module does not wire it.** Main wires the real
    reader separately, at `backend/api/routes.py:2079` (`hedge_router.
    register()`) and `scripts/run_loop.py:1136`, in #128 -- deliberately kept
    out of this lane's diff so a keyless demo instance (`combo_api()` raises
    `ConfigError` there) never has `/api/hedge` fail on this field's account.

    Deliberately NOT routed through `read_books`, and NOT added to
    `hedge_watch`'s 8-second quote-pass budget: a combination book is a
    different read at a different cadence, and merging the two would put an
    unauthenticated route's combo-book reads on the same clock leg quotes
    already spend (review D1/D8).

    Since #128 wired a real reader, three bounds sit on the reads this makes
    and they are decided HERE, not by the reader: a combination whose legs
    have all resolved is never read, NOR is one the venue has already
    settled even while its legs still read `pending` (both collapse to
    `nothing_pending`, a third "not applicable" reason beside `no_ticket`
    and `no_reader_wired` -- there is nothing left to sell into either way,
    and the venue's own settlement is authoritative over a leg-resolution
    pass that can lag it by up to one runner cycle, #132); and two positions
    on one `combo_ticker` share one read. The reader itself carries the
    per-read timeout (`routes.py:COMBO_BOOK_READ_TIMEOUT_S`).
    """
    # The sunk stake is read at the venue's own fill price where the venue
    # gave one and the link to it is provable, and at the figure recorded
    # with the position otherwise. Resolved once, here, so `assess`,
    # `entry_fee_tenths` and the screen's stake line cannot disagree about
    # which number they are on. Nothing is written back.
    stored = open_positions(conn)
    bases = stake_bases(conn, stored)
    positions = [
        position_at_basis(p, bases[int(p["id"])]) for p in stored
    ]
    books = await read_books(
        watched_tickers(conn), now_ms=now_ms, fetch_quote=fetch_quote
    )
    venue_tickers, venue_poll_ms = venue_position_tickers(conn)
    settlements = combo_settlements(
        conn, [p["combo_ticker"] for p in positions if p["combo_ticker"]]
    )
    rows = []
    # One venue read per DISTINCT combination per call, and none for a
    # combination whose legs have all resolved. The leg reads above already
    # run on that predicate (`watched_tickers`: DISTINCT, `outcome =
    # 'pending'`); the combo read is held to the same one so the two
    # populations on this route cannot drift apart (#128 review, defect 1).
    combo_books: dict[str, tuple[Optional[dict], Optional[str]]] = {}
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
        # Nothing left to sell into either when every leg has resolved OR
        # when the venue has already settled this combination itself, even
        # if a leg still reads `pending` -- the leg-resolution pass can lag
        # the venue's own settlement by up to one runner cycle (#132). Same
        # reason either way; the settlement read is the same dict already
        # built above, so this costs no extra lookup.
        if combo_ticker is not None and (
            assessment.pending_legs == 0
            or settlements.get(str(combo_ticker)) is not None
        ):
            combo_book, combo_book_reason = (
                None, COMBO_BOOK_REASON_NOTHING_PENDING
            )
        elif combo_ticker is not None and str(combo_ticker) in combo_books:
            combo_book, combo_book_reason = combo_books[str(combo_ticker)]
        else:
            combo_book, combo_book_reason = await combo_book_state(
                combo_ticker, read_combo_book=read_combo_book, now_ms=now_ms
            )
            if combo_ticker is not None:
                combo_books[str(combo_ticker)] = (combo_book, combo_book_reason)
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
                combo_book=combo_book,
                combo_book_reason=combo_book_reason,
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
