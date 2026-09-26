"""`POST /api/parlays/check` -- price a parlay someone else built (#166).

Joe tails a friend's parlays: 82 of his 142 settled parlays were never priced
on this desk because he copied them from someone who built them elsewhere
(#164, #165). This module takes pasted text -- a kalshi.com link or a bare
`KXMVE...` ticker -- reads the combination's legs straight off the venue (the
minted market already exists; nothing here mints one), prices each leg and
the conservative joint from the desk's own consensus, reads the book, and
writes one `parlay_lookups` row keyed to that ticker under `card_key =
"outside"` -- so `/bets` (#161, #163), Ask the Market and Take It all see it
without being changed themselves.

**Reuse, not a parallel implementation.** The leg read is `mve_legs`
(`backend/kalshi/rfq.py`), the same function `hedge.adopt_venue_combo` (#148)
uses for a combination bought outside the desk; the per-leg chance is the
same `candidate_pool` / `ladder_candidates` scan the ladder itself runs, with
`eligible_events` cleared to `None` -- a minted ticker already proves Kalshi
will combine its legs, so the venue-combinability filter would only ever
throw away a leg this function has independent proof is fine; the joint is
`core.ladder.joint_for`, the same function `price_card_on_kalshi` calls; the
book read and the derived-ask identity are `OrderBook`, the same class every
other price on this desk goes through; and the row is `parlays._record_lookup`,
the one writer of `parlay_lookups`.

**Never mints, never spends.** The ticket already exists on the venue by the
time a friend has shared it, so there is no `lookup_combo` call and no
`allow_market_creation` -- the one difference from `price_card_on_kalshi`,
which mints (or finds) the combination its own card names. No agent, no
scout, no odds fetch: everything this function reads is already in the
database or on the one venue call each of `GET /markets/{ticker}` and the
order book.

**A leg the pool cannot answer for is `chance: null` with a named reason,
never `0.0`.** CLAUDE.md's rule ("unreadable resolves to `None`, never `0`")
applies here exactly as it does to `unusable_reason`: a friend's parlay can
easily carry a leg this desk has no consensus for (a prop, a league the odds
feed does not carry, a market that has gone stale) and the screen must say
so in words, not a number that reads as "impossible".
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Sequence

from backend.core.correlation import CorrelationRefused
from backend.core.ladder import CandidateLeg, Leg, joint_for, unusable_reason
from backend.core.parlay import ParlayQuote, value_parlay
from backend.kalshi.orderbook import OrderBook
from backend.kalshi.rfq import RfqRefused, mve_legs
from backend.parlays import (
    HORIZON_LADDER,
    NOTES,
    LookupRefused,
    _commence_ms_for_tickers,
    _cost_per_contract,
    _record_lookup,
    candidate_pool,
    horizon_end_ms,
    ladder_candidates,
)

logger = logging.getLogger(__name__)

#: The row's own identity in `parlay_lookups.card_key`. Never reused by a
#: registered card (`core.ladder.CARD_SHAPES`) -- this parlay was not built
#: by this desk, so it does not share a recipe's key.
CARD_KEY = "outside"

#: `HORIZONS`/`HORIZON_LADDER` run narrowest-first (`parlays.py`), so the last
#: entry is the widest window this desk carries. A friend's parlay was built
#: on ITS OWN clock, not this desk's "tonight" -- the widest window is the
#: only one that does not refuse a leg for a reason that has nothing to do
#: with whether the desk can price it.
WIDEST_HORIZON = HORIZON_LADDER[-1]

#: The first `KXMVE...` token in pasted text, case-insensitive. Deliberately
#: does not assume a URL shape -- Joe's own answer (2026-09-25) named a
#: kalshi.com link as the near-term case and a screenshot as later, and no
#: sample link was in hand to anchor a stricter pattern against. A ticker
#: embedded in a URL's path still matches; the scan simply stops at the first
#: character outside the class, which excludes `/`, `?` and `=`.
_TICKER_PATTERN = re.compile(r"KXMVE[A-Za-z0-9._-]+", re.IGNORECASE)

#: Reasons a leg absent from the candidate pool cannot be priced, spelled the
#: same way `resolve_requested_legs` (`parlays.py:2810`) tells Joe about a
#: drifted leg on his own card -- reused, not re-derived, so the two screens
#: cannot describe the same fact in two words.
REASON_GAME_STARTED = "game_started"
REASON_OUTSIDE_WINDOW = "outside_window"
REASON_NOT_SERVED = "not_served"


def extract_ticker(text: str) -> Optional[str]:
    """The first `KXMVE...` token in `text`, upper-cased, or `None`.

    `None` means refuse before any venue call and before any row -- there is
    no ticker to look anything up about.
    """
    match = _TICKER_PATTERN.search(text or "")
    if match is None:
        return None
    return match.group(0).upper()


def _percent_display(p: Optional[float]) -> Optional[str]:
    """A probability as a percentage that never rounds a small reading to
    "0%".

    `parlays._percent` (`core.prices.format_probability`) rounds to the
    nearest tenth of a cent, so a reading of 0.0004 (0.04%) prints "0%" --
    exactly the failure `bets/page.tsx`'s `chancePercent` was written to
    fix for `chance_when_priced` (lessons 2026-09-25). That fix lives in the
    frontend only; this is the same four-band rule for the two percentages
    this module renders (`chance_display`, `conservative_percent_display`),
    so a longshot leg in a friend's parlay does not read as "no chance" on
    the one screen whose whole job is to say what a chance actually is.
    """
    if p is None:
        return None
    pct = p * 100.0
    if pct >= 10:
        return f"{round(pct)}%"
    if pct >= 1:
        return f"{pct:.1f}%"
    if pct >= 0.01:
        return f"{pct:.2f}%"
    return "under 0.01%"


def _leg_label(ticker: str, side: str, titles: dict) -> str:
    """`kalshi_markets.title` when this instance has seen the market, else
    the bare ticker, prefixed `"NO -- "` on a NO leg.

    The same convention `hedge.adopt_venue_combo` (#148) uses for a leg with
    no upstream sportsbook-phrased label to fall back on -- a friend's parlay
    has none either, by construction: no card of this desk's own ever chose
    a phrasing for it.
    """
    base = titles.get(ticker) or ticker
    return f"NO -- {base}" if side == "no" else base


def _titles_for(conn, tickers: Sequence[str]) -> dict:
    """`{ticker: title}` for every leg this instance has ingested, silently
    omitting one it has not -- the caller falls back to the ticker."""
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    out: dict = {}
    for row in conn.execute(
        f"SELECT ticker, title FROM kalshi_markets WHERE ticker IN ({placeholders})",
        tuple(tickers),
    ):
        if row["title"]:
            out[str(row["ticker"])] = str(row["title"])
    return out


def _missing_leg_reason(
    commence_ms: Optional[int], *, now_ms: int, horizon: str
) -> str:
    """Why a leg absent from the candidate pool cannot be priced -- the same
    three-way split `resolve_requested_legs` makes for a drifted leg on the
    desk's own card, reused rather than re-derived (`parlays.py:2900-2932`).
    """
    if commence_ms is not None and commence_ms <= now_ms:
        return REASON_GAME_STARTED
    if commence_ms is not None and commence_ms > horizon_end_ms(now_ms, horizon):
        return REASON_OUTSIDE_WINDOW
    return REASON_NOT_SERVED


async def check_parlay_text(
    conn,
    *,
    text: str,
    now_ms: int,
    api,
    max_odds_age_ms: int,
    horizon: str = WIDEST_HORIZON,
    max_kalshi_quote_age_ms: Optional[int] = None,
) -> dict:
    """Read a pasted combination's legs off Kalshi and price it. See module
    docstring for the pipeline and what is deliberately not spent.

    Raises `LookupRefused` for every refusal that writes no row (no ticker in
    the text, an unreadable market, a leg with no readable side) and for the
    one refusal that writes a row first (the order book could not be read --
    the market exists on the venue by this point, so the failure is recorded
    with the ticker before the caller is told).
    """
    ticker = extract_ticker(text)
    if ticker is None:
        raise LookupRefused(
            422,
            "paste the Kalshi link or the KXMVE... ticker for the parlay "
            "you want checked. Nothing was read.",
        )

    try:
        market_payload = await api.get(f"/markets/{ticker}")
    except Exception as exc:  # noqa: BLE001 -- transport; no row, nothing read
        raise LookupRefused(
            502,
            f"Kalshi's market for {ticker} could not be read ({exc}). "
            "Nothing was created.",
        ) from exc

    try:
        collection_ticker, venue_legs = mve_legs(market_payload)
    except RfqRefused as exc:
        raise LookupRefused(
            422,
            f"Kalshi's market for {ticker} carries no legs to check: {exc}. "
            "Nothing was created.",
        ) from exc

    # **A leg whose side is neither `yes` nor `no` is refused by name,
    # before anything is priced** -- the same rule `hedge.adopt_venue_combo`
    # states for the identical shape: guessing `"yes"` would misdescribe a
    # real NO leg, and KXMVE combos carry them routinely.
    for leg in venue_legs:
        side = leg.get("side")
        if side not in ("yes", "no"):
            raise LookupRefused(
                422,
                f"Kalshi's market for {ticker} names a leg "
                f"({leg.get('market_ticker')!r}) with no readable side "
                f"({side!r}). Nothing was created.",
            )

    leg_tickers = [
        str(leg["market_ticker"]) for leg in venue_legs if leg.get("market_ticker")
    ]
    titles = _titles_for(conn, leg_tickers)

    # **`eligible_events` cleared to `None`.** A minted ticker already proves
    # the venue will combine these legs -- that is what "it exists" means --
    # so `combo_eligible_events`'s cache would only ever throw away a leg this
    # function has independent, stronger proof is fine to price.
    pool = candidate_pool(conn, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms)
    pool = pool._replace(eligible_events=None)
    candidates, _excluded = ladder_candidates(
        conn,
        now_ms=now_ms,
        max_odds_age_ms=max_odds_age_ms,
        horizon=horizon,
        pool=pool,
    )
    by_key = {
        (c.kalshi_event_ticker, c.kalshi_market_ticker, c.side): c for c in candidates
    }

    missing_tickers = [
        str(leg["market_ticker"])
        for leg in venue_legs
        if (
            str(leg.get("event_ticker")),
            str(leg.get("market_ticker")),
            str(leg.get("side")),
        )
        not in by_key
    ]
    kickoffs = _commence_ms_for_tickers(conn, missing_tickers)

    response_legs: list[dict] = []
    usable: list[CandidateLeg] = []
    any_unusable = False
    leg_details: dict[tuple, dict] = {}
    legs_pairs: list[tuple] = []

    for leg in venue_legs:
        event_ticker = str(leg.get("event_ticker"))
        market_ticker = str(leg["market_ticker"])
        side = str(leg.get("side"))
        legs_pairs.append((event_ticker, market_ticker))

        candidate = by_key.get((event_ticker, market_ticker, side))
        chance: Optional[float] = None
        unknown_reason: Optional[str] = None
        commence_ms: Optional[int] = None

        if candidate is None:
            # **Absent from the pool is never a chance, and never a zero.**
            # `chance` already starts `None` above; restated here, on its own
            # line, because this is the one branch CLAUDE.md's rule
            # ("unreadable resolves to `None`, never `0`") is actually about
            # -- a leg this desk has no consensus for is not "0% likely", it
            # is "unknown", and the two must never render the same.
            chance = None
            any_unusable = True
            commence_ms = kickoffs.get(market_ticker)
            unknown_reason = _missing_leg_reason(
                commence_ms, now_ms=now_ms, horizon=horizon
            )
        else:
            commence_ms = candidate.commence_ms
            reason_code = unusable_reason(candidate, max_odds_age_ms=max_odds_age_ms)
            if reason_code is not None:
                any_unusable = True
                unknown_reason = reason_code
            else:
                chance = candidate.p_conservative
                usable.append(candidate)

        label = _leg_label(market_ticker, side, titles)
        response_legs.append(
            {
                "market_ticker": market_ticker,
                "side": side,
                "label": label,
                "commence_ms": commence_ms,
                "chance": chance,
                "chance_display": _percent_display(chance),
                "unknown_reason": unknown_reason,
            }
        )
        leg_details[(event_ticker, market_ticker)] = {
            "side": side,
            "label": label,
            "commence_ms": commence_ms,
        }

    fair_joint: Optional[float] = None
    no_joint_reason: Optional[str] = None
    if any_unusable:
        no_joint_reason = "unknown_leg"
    else:
        odds_event_ids = {c.odds_event_id for c in usable}
        if len(odds_event_ids) != len(usable):
            no_joint_reason = "same_game"
        else:
            try:
                joint = joint_for(usable)
            except CorrelationRefused:
                # Structurally unreachable given the same-game check just
                # above -- kept anyway, the same defensive posture
                # `price_card_on_kalshi` inherits from `resolve_requested_
                # legs` refusing a same-game pair before `joint_for` is ever
                # called.
                no_joint_reason = "same_game"
            else:
                fair_joint = joint.conservative

    try:
        book_payload = await api.orderbook(ticker, depth=10)
        book = OrderBook(ticker=ticker)
        book.apply_snapshot(book_payload, None, now_ms)
    except Exception as exc:  # noqa: BLE001 -- recorded WITH the ticker, then worded
        _record_lookup(
            conn,
            now_ms=now_ms,
            card_key=CARD_KEY,
            stake_cents=0,
            legs=legs_pairs,
            status="error",
            collection_ticker=collection_ticker,
            minted=ticker,
            error=f"orderbook: {exc}",
            leg_details=leg_details,
        )
        raise LookupRefused(
            502,
            f"Kalshi's order book for {ticker} could not be read ({exc}). "
            "Nothing is priced; the combination exists and can be looked at "
            "in the Kalshi app.",
        ) from exc

    ask_tenths = book.best_yes_ask
    depth = book.depth_at_ask("yes") if ask_tenths is not None else None
    status = "priced" if ask_tenths is not None else "book_empty"

    hold: Optional[float] = None
    if status == "priced" and fair_joint is not None:
        valuation = value_parlay(
            ParlayQuote(
                legs=tuple(
                    Leg(
                        label=c.kalshi_market_ticker,
                        probability=c.p_conservative,
                        event_key=c.odds_event_id,
                        league=c.league,
                        commence_ms=c.commence_ms,
                    )
                    for c in usable
                ),
                offered_decimal=1000.0 / ask_tenths,
            )
        )
        hold = valuation.hold

    _record_lookup(
        conn,
        now_ms=now_ms,
        card_key=CARD_KEY,
        stake_cents=0,
        legs=legs_pairs,
        status=status,
        collection_ticker=collection_ticker,
        minted=ticker,
        no_bid_tenths=book.best_no_bid if status == "priced" else None,
        ask_tenths=ask_tenths if status == "priced" else None,
        depth=depth,
        fair_joint=fair_joint,
        hold=hold,
        leg_details=leg_details,
    )

    quoted: Optional[dict] = None
    if status == "priced":
        quoted = {
            "ask_display": _cost_per_contract(ask_tenths),
            "depth_display": (
                None
                if depth is None
                else f"about {depth:g} contracts resting at that price"
            ),
            "quoted_ms": now_ms,
            "quote_max_age_ms": max_kalshi_quote_age_ms,
        }
        words = (
            "Read off Kalshi's own order book for this combination. This "
            "parlay was not built on this desk, so a leg outside its own "
            "coverage reads as unknown rather than a chance."
        )
    else:
        # **Kalshi's own words for an empty combo book, verbatim from
        # `price_card_on_kalshi`** (ADR 0164): a combination's book is empty
        # by design between RFQs, and this is the exact sentence that stopped
        # telling Joe an empty book meant nobody would sell.
        words = (
            "Kalshi created the market, and nothing is resting in its "
            "public order book -- which is the normal state of a "
            "combination, not a sign that nobody will sell it. A "
            "combination is priced by asking: market makers quote you "
            "privately, and their prices never appear in the book. "
            "Re-reading the book will keep saying this, so ask instead."
        )

    return {
        "status": status,
        "minted_market_ticker": ticker,
        "legs": response_legs,
        "fair": {
            "conservative": fair_joint,
            "conservative_percent_display": _percent_display(fair_joint),
            "fair_cost_display": (
                _cost_per_contract(fair_joint * 1000)
                if fair_joint is not None
                else None
            ),
            "no_joint_reason": no_joint_reason,
        },
        "quoted": quoted,
        "hold_display": f"{hold * 100:.1f}%" if hold is not None else None,
        "words": words,
        "notes": {"unquoted": NOTES["unquoted"], "fee": NOTES["fee"]},
    }
