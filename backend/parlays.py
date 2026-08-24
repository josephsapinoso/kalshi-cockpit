"""Read ladder candidates for the parlay desk, and word its payload (ADR 0070).

The desk sells three cards a day — Safe, Middle, Lottery — built from the same
devigged consensus the slate reads, one leg per game, priced at FAIR value.
Kalshi's actual quote for a combination exists only after a lookup mints the
market, so everything here is the consensus side of the comparison; the quoted
side arrives via the lookup path and is labelled as Kalshi's, never blended.

WHAT THIS MODULE DOES NOT ESTABLISH
-----------------------------------
- **That a card is a good bet.** The fair joint is what the books' consensus
  implies; the venue's combination product is enter-only on every book this
  repo has ever read, and its fee model is unverified. Those sentences travel
  in the payload verbatim.
- **An edge.** No breakeven, no EV, no size appears in any payload built here
  (pinned by `tests/test_parlays_api.py`'s key-walk). ADR 0038's closed hunt
  and the gate are untouched: nothing here writes `recommendations` or feeds
  `gate.py`.

Money strings render server-side, per `lib/api.ts`'s no-arithmetic rule: the
stake picker is a set of preset stakes each priced here, not a client-side
calculator.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.core.ladder import (
    Card,
    CandidateLeg,
    Ladder,
    build_ladder,
)
from backend.kalshi.spreads import parse_spread_subtitle
from backend.match.linker import load_aliases, resolve_outcome

logger = logging.getLogger(__name__)

#: Preset stakes, in cents. Served pre-priced so the client never does money
#: arithmetic; $5 is the default the cousin-style ticket is framed at.
STAKE_PRESETS_CENTS: tuple[int, ...] = (100, 500, 1000, 2000)
DEFAULT_STAKE_CENTS = 500

#: A market whose status says the venue is done with it cannot be a leg.
_TERMINAL_STATUSES = frozenset({"closed", "settled", "finalized", "determined"})

NOTES: dict[str, str] = {
    "chance": (
        "Chance every leg hits, by the books' consensus — not an edge. A "
        "parlay multiplies chances down: six 65% legs land together about "
        "8% of the time."
    ),
    "fair_value": (
        "Costs shown are FAIR value — what the combination is worth if "
        "Kalshi charged exactly the consensus chance. Kalshi's own price "
        "for a combo exists only once it is built in the app, and it will "
        "differ."
    ),
    "enter_only": (
        "Kalshi combos are enter-only in every order book this tool has "
        "ever read (40 of 40): you can buy in, but nobody is bidding to "
        "buy you out. Plan to hold to settlement."
    ),
    "fee": (
        "Kalshi's combo fee model is unverified. Every combo fill ever "
        "measured here charged at least 0.070 x contracts x price x "
        "(1 - price), and some charged slightly more."
    ),
}


def _live_age_ms(row, *, now_ms: int) -> Optional[int]:
    """The consensus's LIVE age: time since devig plus its stalest input.

    `None` when `oldest_book_age_ms` was never recorded (pre-v20 row) — the
    age is unmeasurable and the ladder refuses the leg, never ages it zero.
    """
    oldest = row["oldest_book_age_ms"]
    if oldest is None:
        return None
    return (now_ms - row["computed_ms"]) + oldest


def ladder_candidates(
    conn, *, now_ms: int
) -> tuple[list[CandidateLeg], dict[str, int]]:
    """Every buyable YES side with a fresh-enough-to-consider consensus.

    Pre-game only, by the sportsbook's clock (`MIN(odds_snapshots.commence_ms)`
    per fixture — the scorer's own definition; Kalshi's `commence_ms` runs
    three hours late and is never read here). Freshest `fair_prices` row per
    (link, market, outcome, point). Freshness itself is judged in
    `build_ladder`; this function only refuses what can never be a leg.
    """
    rows = conn.execute(
        """
        SELECT f.computed_ms, f.market, f.outcome_name, f.outcome_point,
               f.p_multiplicative, f.p_additive, f.p_power, f.p_shin,
               f.p_conservative, f.oldest_book_age_ms, f.link_id,
               l.kalshi_event_ticker, l.odds_event_id, l.league,
               o.commence_ms, o.home_team, o.away_team,
               e.title AS event_title
        FROM fair_prices f
        JOIN event_links l ON l.id = f.link_id
        JOIN kalshi_events e ON e.event_ticker = l.kalshi_event_ticker
        JOIN (
            SELECT odds_event_id, MIN(commence_ms) AS commence_ms,
                   home_team, away_team
            FROM odds_snapshots GROUP BY odds_event_id
        ) o ON o.odds_event_id = l.odds_event_id
        WHERE f.market IN ('h2h', 'spreads')
          AND o.commence_ms IS NOT NULL AND o.commence_ms > ?
        ORDER BY f.computed_ms DESC
        """,
        (now_ms,),
    ).fetchall()

    excluded: dict[str, int] = {}

    def count(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    # Freshest row per identity. The rows arrive newest-first, so first wins.
    freshest: dict[tuple, object] = {}
    for row in rows:
        key = (row["link_id"], row["market"], row["outcome_name"], row["outcome_point"])
        freshest.setdefault(key, row)

    # The book's outcome names per link — what `resolve_outcome` matches
    # a Kalshi side against. Spread rows' outcomes are the same two teams,
    # so one list per link serves both market kinds.
    outcomes_by_link: dict[int, list[str]] = {}
    for (link_id, _market, outcome, _), _row in freshest.items():
        if outcome not in outcomes_by_link.setdefault(link_id, []):
            outcomes_by_link[link_id].append(outcome)

    # Kalshi's buyable markets per linked event: moneylines on the game
    # event, spread rungs on the spread event (each links separately).
    markets_by_event: dict[str, list] = {}
    for row in freshest.values():
        event_ticker = row["kalshi_event_ticker"]
        if event_ticker in markets_by_event:
            continue
        markets_by_event[event_ticker] = conn.execute(
            "SELECT ticker, yes_side_team, market_type, strike, status "
            "FROM kalshi_markets WHERE event_ticker = ? "
            "AND market_type IN ('moneyline', 'spread') "
            "AND yes_side_team IS NOT NULL",
            (event_ticker,),
        ).fetchall()

    alias_cache: dict[str, object] = {}
    candidates: list[CandidateLeg] = []
    for (link_id, market, outcome, point), row in freshest.items():
        league = row["league"]
        if league not in alias_cache:
            alias_cache[league] = load_aliases(league)
        aliases = alias_cache[league]

        # Which Kalshi market's YES is this outcome?
        #
        # A spread combo leg must be a BUYABLE YES side, and Kalshi only
        # sells the favorite's cover ("T wins by over S" = the book's
        # (T, -S)); the +S side is that market's NO, not a leg. So spread
        # rows with a positive point are structurally not candidates —
        # skipped without a count, the way a NO-side h2h row never enters
        # `outcomes_by_link` as a pick.
        matched = None
        label = f"{outcome} to win"
        if market == "spreads":
            point_val = float(point) if point is not None else None
            if point_val is None or point_val >= 0:
                continue
            for m in markets_by_event.get(row["kalshi_event_ticker"], []):
                if m["market_type"] != "spread" or m["strike"] is None:
                    continue
                if float(m["strike"]) != -point_val:
                    continue
                parsed = parse_spread_subtitle(m["yes_side_team"])
                if parsed is None:
                    continue
                resolved = resolve_outcome(
                    parsed[0], outcomes_by_link.get(link_id, []), aliases
                )
                if resolved == outcome:
                    matched = m
                    # The subtitle verbatim — Kalshi's own phrasing is the
                    # clearest label a rung has ("St. Louis wins by over
                    # 1.5 runs").
                    label = m["yes_side_team"]
                    break
        else:
            for m in markets_by_event.get(row["kalshi_event_ticker"], []):
                if m["market_type"] != "moneyline":
                    continue
                resolved = resolve_outcome(
                    m["yes_side_team"], outcomes_by_link.get(link_id, []), aliases
                )
                if resolved == outcome:
                    matched = m
                    break
        if matched is None:
            count("no_kalshi_market")
            continue
        if (matched["status"] or "").lower() in _TERMINAL_STATUSES:
            count("market_closed")
            continue

        title = row["event_title"] or (
            f"{row['away_team']} @ {row['home_team']}"
            if row["away_team"] and row["home_team"]
            else row["kalshi_event_ticker"]
        )
        candidates.append(
            CandidateLeg(
                label=label,
                event_title=title,
                kalshi_event_ticker=row["kalshi_event_ticker"],
                kalshi_market_ticker=matched["ticker"],
                odds_event_id=row["odds_event_id"],
                league=league,
                commence_ms=row["commence_ms"],
                market=market,
                team=outcome,
                point=point,
                p_conservative=row["p_conservative"],
                p_by_method={
                    "multiplicative": row["p_multiplicative"],
                    "additive": row["p_additive"],
                    "power": row["p_power"],
                    "shin": row["p_shin"],
                },
                odds_age_now_ms=_live_age_ms(row, now_ms=now_ms),
            )
        )

    return candidates, excluded


# ---------------------------------------------------------------------------
# Serialisation -- every display string is worded here, server-side.
# ---------------------------------------------------------------------------


def _percent(p: float) -> str:
    return f"{p * 100:.1f}%"


def _dollars(cents: float) -> str:
    dollars = cents / 100.0
    if dollars >= 100:
        return f"${dollars:,.0f}"
    return f"${dollars:,.2f}"


def _stake_row(stake_cents: int, joint: float) -> dict:
    """What a stake buys at FAIR value: `contracts = stake / fair_cost`,
    each contract settling $1 — the venue's own combo mechanics."""
    contracts = stake_cents / (joint * 100.0)
    return {
        "stake_cents": stake_cents,
        "stake_display": _dollars(stake_cents),
        "contracts_display": (
            f"~{contracts:,.0f}" if contracts >= 10 else f"~{contracts:.1f}"
        ),
        "payout_display": _dollars(contracts * 100.0),
        "is_default": stake_cents == DEFAULT_STAKE_CENTS,
    }


def _serialise_leg(leg: CandidateLeg) -> dict:
    return {
        "ticker": leg.kalshi_market_ticker,
        "event_title": leg.event_title,
        "team": leg.team,
        "label": leg.label,
        "league": leg.league,
        "commence_ms": leg.commence_ms,
        "market": leg.market,
        "point": leg.point,
        "fair_percent_display": _percent(leg.p_conservative),
    }


def _serialise_card(card: Card) -> dict:
    if card.not_built_reason is not None:
        return {
            "key": card.key,
            "title": card.title,
            "legs": [],
            "not_built_reason": card.not_built_reason,
            "joint": None,
            "at_stakes": [],
        }

    joint = card.joint
    assert joint is not None  # Card.__post_init__ guarantees it
    low, high = joint.method_range
    return {
        "key": card.key,
        "title": card.title,
        "legs": [_serialise_leg(leg) for leg in card.legs],
        "not_built_reason": None,
        "joint": {
            # The headline is the CONSERVATIVE joint: each leg at the lowest
            # of four devig methods, compounded. The range beside it is the
            # same joint under each single method -- the honest band.
            "conservative_percent_display": _percent(joint.conservative),
            "method_range_display": (
                f"{_percent(low)}–{_percent(high)}"
                if low is not None and high is not None
                else None
            ),
            "fair_cost_display": (
                f"{joint.conservative * 100:.1f}c per $1 contract"
            ),
            "correlation_note": (
                "Same-night games move together a little; the headline "
                "already charges for that "
                f"({joint.independence_error_points:+.2f} points vs "
                "treating the legs as independent)."
            ),
        },
        "at_stakes": [
            _stake_row(cents, joint.conservative) for cents in STAKE_PRESETS_CENTS
        ],
    }


def serialise_ladder(ladder: Ladder, *, generated_ms: int) -> dict:
    return {
        "generated_ms": generated_ms,
        "cards": [_serialise_card(card) for card in ladder.cards],
        "excluded": ladder.excluded,
        "notes": dict(NOTES),
    }


def build_ladder_payload(conn, *, now_ms: int, max_odds_age_ms: int) -> dict:
    candidates, excluded = ladder_candidates(conn, now_ms=now_ms)
    ladder = build_ladder(candidates, max_odds_age_ms=max_odds_age_ms)
    merged = dict(ladder.excluded)
    for reason, n in excluded.items():
        merged[reason] = merged.get(reason, 0) + n
    return serialise_ladder(
        Ladder(cards=ladder.cards, excluded=merged), generated_ms=now_ms
    )
