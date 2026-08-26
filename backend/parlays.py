"""Read ladder candidates for the parlay desk, and word its payload (ADR 0070).

The desk sells six cards — six cuts of ONE pool of devigged consensus legs,
one leg per game, priced at FAIR value. `core.ladder.CARD_SHAPES` owns which
cuts exist; nothing here knows how many there are.
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

import json
import logging
from typing import Optional, Sequence

from backend.core.correlation import Leg
from backend.core.ladder import (
    Card,
    CandidateLeg,
    Ladder,
    build_ladder,
)
from backend.core.parlay import ParlayQuote, value_parlay
from backend.core.prices import format_price, format_probability
from backend.kalshi.combos import ComboScope, fetch_collections, lookup_combo
from backend.kalshi.orderbook import OrderBook
from backend.kalshi.spreads import (
    parse_spread_subtitle,
    spread_book_point,
    spread_margin_agrees,
)
from backend.match.linker import load_aliases, resolve_outcome
from backend.store.db import ask_for_side

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


#: How far back `ladder_candidates` reads `fair_prices` at all.
#:
#: `fair_prices` is never pruned and passed ~6.9M rows by 2026-08-24, and this
#: query is paid twice per lookup tap (once for the ladder, once to re-derive
#: the card server-side). Every row older than this is discarded downstream
#: anyway: `build_ladder` refuses a leg whose consensus is staler than
#: `max_odds_age_ms` (deployed in minutes), and the pre-game bound already
#: excludes anything whose game has started. So this floor changes no output,
#: it only stops the scan reading the whole history to throw it away.
#:
#: **Deliberately far looser than the freshness rule** -- a day, against a
#: staleness limit measured in minutes. A floor tight enough to be load-
#: bearing would be a second staleness rule in a second place, and this repo
#: has already been bitten by one quantity with two limits. If the deployed
#: `max_odds_age_ms` ever exceeds this, the floor becomes the binding rule and
#: legs vanish silently -- so the two are compared at call time and the wider
#: of them wins.
_CANDIDATE_SCAN_FLOOR_MS = 24 * 3_600_000


def ladder_candidates(
    conn, *, now_ms: int, max_odds_age_ms: Optional[int] = None
) -> tuple[list[CandidateLeg], dict[str, int]]:
    """Every buyable YES side with a fresh-enough-to-consider consensus.

    Pre-game only, by the sportsbook's clock (`MIN(odds_snapshots.commence_ms)`
    per fixture — the scorer's own definition; Kalshi's `commence_ms` runs
    three hours late and is never read here). Freshest `fair_prices` row per
    (link, market, outcome, point). Freshness itself is judged in
    `build_ladder`; this function only refuses what can never be a leg.

    `max_odds_age_ms` is not a filter here — it only widens the scan floor so
    the query can never be tighter than the freshness rule the caller will
    apply. Pass the same value you pass `build_ladder`.
    """
    horizon_ms = max(_CANDIDATE_SCAN_FLOOR_MS, max_odds_age_ms or 0)
    rows = conn.execute(
        """
        SELECT f.computed_ms, f.market, f.outcome_name, f.outcome_point,
               f.p_multiplicative, f.p_additive, f.p_power, f.p_shin,
               f.p_conservative, f.oldest_book_age_ms, f.link_id,
               f.market_width, f.book_count, f.books_used, f.anchored_on_sharp,
               l.kalshi_event_ticker, l.odds_event_id,
               o.commence_ms, o.home_team, o.away_team, o.sport_key,
               e.title AS event_title
        FROM fair_prices f
        JOIN event_links l ON l.id = f.link_id
        JOIN kalshi_events e ON e.event_ticker = l.kalshi_event_ticker
        JOIN (
            SELECT odds_event_id, MIN(commence_ms) AS commence_ms,
                   home_team, away_team, sport_key
            FROM odds_snapshots GROUP BY odds_event_id
        ) o ON o.odds_event_id = l.odds_event_id
        WHERE f.market IN ('h2h', 'spreads')
          AND f.computed_ms >= ?
          AND o.commence_ms IS NOT NULL AND o.commence_ms > ?
        ORDER BY f.computed_ms DESC
        """,
        (now_ms - horizon_ms, now_ms),
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
        # **`odds_snapshots.sport_key`, not `event_links.league`.** They are
        # different vocabularies for the same partition and only one of them
        # names an alias file.
        #
        # `event_links.league` holds Kalshi's `product_metadata.competition`
        # verbatim -- measured on this repo's own database: 'Pro Baseball',
        # 'Pro Basketball (W)', 'Pro Football'. The alias files are named for
        # The Odds API's sport keys: `baseball_mlb.yaml`,
        # `americanfootball_nfl.yaml`. So `load_aliases("Pro Baseball")` looked
        # for a file that has never existed, and `load_aliases` returns an
        # EMPTY `TeamAliases` for a missing file rather than raising -- by
        # design, because most leagues need no overrides.
        #
        # The two together mean **the parlay ladder ran with zero team aliases
        # from the day it was built**, silently, on a screen that offers money
        # decisions. The linker itself was always correct
        # (`runner.py` loads aliases from `event.sport_key`); only this reader
        # was wrong, which is why nothing upstream noticed.
        #
        # The same string is what the client renders, so this also stops a leg
        # reading "Pro Baseball" where the rest of the app says "MLB":
        # `frontend/src/lib/leagueLabel.ts` keys on sport keys and renders an
        # unknown key verbatim.
        league = row["sport_key"]
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
                parsed = parse_spread_subtitle(m["yes_side_team"])
                if parsed is None:
                    continue
                # The subtitle's own margin, cross-checked against
                # `floor_strike`, then converted to the book's point through
                # the ONE identity (`spreads.spread_book_point`). Reading the
                # strike alone -- what this did until 2026-08-24 -- skips the
                # cross-check the runner performs, so a market whose subtitle
                # had drifted away from its strike could still match a fair
                # row that was priced from the subtitle.
                if not spread_margin_agrees(parsed[1], m["strike"]):
                    count("spread_margin_disagrees")
                    continue
                if spread_book_point(parsed[1]) != point_val:
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
                market_width=row["market_width"],
                book_count=row["book_count"],
                books_used_json=row["books_used"],
                anchored_on_sharp=bool(row["anchored_on_sharp"]),
            )
        )

    return candidates, excluded


# ---------------------------------------------------------------------------
# Serialisation -- every display string is worded here, server-side.
# ---------------------------------------------------------------------------


def _percent(p: float) -> str:
    """A probability as a percentage, through the ONE renderer.

    Was `f"{p * 100:.1f}%"` until 2026-08-24. `core.prices.format_probability`
    exists precisely because that expression rounds off the float while every
    other surface in the product rounds off the stored integer tenths, so the
    same fair value could print `53.9%` here and `53.8c` two screens away with
    nothing to say which had moved. Its own docstring names this failure.
    """
    return format_probability(p)


def _cost_per_contract(tenths: float) -> str:
    """`15` -> `"1.5c per $1 contract"`, through the ONE price renderer.

    The suffix is the parlay desk's own: a combination contract settles at $1
    like any other, and saying so is what stops `1.5c` reading as the price of
    the whole ticket.
    """
    return f"{format_price(tenths)} per $1 contract"


def _dollars(cents: float) -> str:
    dollars = cents / 100.0
    # Cents kept up to $1,000 — the cousin's slip reads "$333.33", and a
    # payout rounded to "$333" beside a "$4.99" cost mixes two precisions
    # in one sentence. Above that the cents are noise.
    if dollars >= 1_000:
        return f"${dollars:,.0f}"
    return f"${dollars:,.2f}"


def _stake_row(stake_cents: int, joint: float) -> dict:
    """What a stake buys at FAIR value: `contracts = stake / fair_cost`,
    each contract settling $1 — the venue's own combo mechanics."""
    contracts = stake_cents / (joint * 100.0)
    return {
        "stake_cents": stake_cents,
        "stake_display": _dollars(stake_cents),
        "contracts_display": _contracts_display(contracts),
        "payout_display": _dollars(contracts * 100.0),
        "is_default": stake_cents == DEFAULT_STAKE_CENTS,
    }


def _contracts_display(contracts: float) -> str:
    return f"~{contracts:,.0f}" if contracts >= 10 else f"~{contracts:.1f}"


def _at_stake(
    stake_cents: int, *, ask_tenths: int, depth: Optional[float]
) -> dict:
    """What a stake buys at Kalshi's QUOTED ask -- bounded by what is resting.

    **This is CLAUDE.md rule 1 applied to a payout.** `stake / ask` alone
    rendered "$5.00 -> ~333 contracts -> $333.33" on a book with about
    eighteen contracts resting: 315 of those 333 do not exist. On an
    enter-only market a lone stale NO bid at 1.5c produces exactly the giant
    apparent number the rule says to suppress, and putting it in the payout
    slot is the most flattering place it could possibly go.

    So the payout is computed off `min(wanted, depth)`, and when the stake is
    capped the words say by how much. Nothing here is an edge or an EV: cost
    and payout are what the venue would charge and pay, which is the same
    pair the fair-value side of the card already states.

    **`depth is None` is not reachable from `price_card_on_kalshi` today**,
    and the branch is kept anyway. `OrderBook.depth_at_ask` reads the same
    dict `best_no_bid` maxes over and `_parse_levels` drops any level with
    `quantity <= 0`, so a derived ask always has a positive size behind it —
    the two cannot disagree. That is an invariant of a *sibling module*,
    though, not of this function's signature: `depth` is typed `Optional`
    because `depth_at_ask` returns `Optional`, and a caller honouring that
    type must not get a payout invented for it. Unreadable resolves to a
    refusal, never to a number (`tasks/lessons.md`). Covered by a direct unit
    call rather than a route test, because the route genuinely cannot produce
    it — see `tests/test_parlay_lookup.py`.
    """
    row: dict = {"stake_display": _dollars(stake_cents)}
    wanted = stake_cents / (ask_tenths / 10.0)
    if depth is None:
        row["contracts_display"] = None
        row["cost_display"] = None
        row["payout_display"] = None
        row["depth_note"] = (
            "Kalshi's book does not say how many contracts are resting at "
            "that price, so there is no way to say what this stake would "
            "actually fill. No payout is shown rather than one you may not "
            "be able to buy."
        )
        return row

    fillable = min(wanted, float(depth))
    row["contracts_display"] = _contracts_display(fillable)
    row["cost_display"] = _dollars(fillable * ask_tenths / 10.0)
    row["payout_display"] = _dollars(fillable * 100.0)
    row["depth_note"] = (
        None if fillable >= wanted
        else (
            f"Only {_contracts_display(float(depth))} contracts are resting "
            f"at that price, so {row['stake_display']} cannot all be spent "
            f"here -- {row['cost_display']} of it buys the book out. The rest "
            "has nothing to buy unless someone else offers."
        )
    )
    return row


def _method_spread_points(leg: CandidateLeg) -> Optional[float]:
    """How far the four devig readings sit apart, in percentage points.

    The same figure `DispersionStrip` shows as its always-visible summary, and
    for the same reason: it bounds how seriously any single reading deserves to
    be taken. `None` on fewer than two solvable readings -- one reading is not
    perfect agreement, it is one reading.
    """
    values = [v for v in leg.p_by_method.values() if v is not None]
    if len(values) < 2:
        return None
    return (max(values) - min(values)) * 100


def _serialise_leg(leg: CandidateLeg, facts: Optional[dict] = None) -> dict:
    """One leg, with the provenance behind its number.

    Until 2026-08-26 this returned the fair percent and nothing else -- one
    number standing in for three separate choices (which devig method, which
    books, how far the field spreads) on a screen that offers money decisions.
    The slate row has carried all three since ADR 0051; the parlay card had
    none of them.

    **Fair beside COST is lawful here and nowhere else** (ADR 0070 s2.3): a
    parlay's hold is the product being displayed. The two render in unlike
    units on purpose -- ask through `format_price` (`34.2c`), fair through
    `format_probability` (`60.2%`) -- because `core/prices.py:130-143` records
    that a fair value set in the same type as a real ask is the one place a
    left-to-right scan reads the wrong number as the thing you pay.

    **No edge, EV, breakeven or size appears here**, and
    `tests/test_parlays_api.py` walks the keys to keep it that way.
    """
    facts = facts or dict(_NO_FACTS)
    # A spread leg has no `recommendations` row by construction, so "no
    # verdict" means the checks did not run rather than that they passed.
    skeptic = facts["skeptic"]
    if skeptic == "absent" and leg.market == "spreads":
        skeptic = "not_on_this_path"
    return {
        "ticker": leg.kalshi_market_ticker,
        # The lookup tap echoes both tickers back, so the server can refuse
        # a card the slate has drifted away from.
        "event_ticker": leg.kalshi_event_ticker,
        "event_title": leg.event_title,
        "team": leg.team,
        "label": leg.label,
        "league": leg.league,
        "commence_ms": leg.commence_ms,
        "market": leg.market,
        "point": leg.point,
        "fair_percent_display": _percent(leg.p_conservative),
        # --- What Kalshi charges, beside what the consensus says it is worth.
        "ask_display": facts["ask_display"],
        "depth_at_ask": facts["depth_at_ask"],
        "quote_age_ms": facts["quote_age_ms"],
        # --- Where the fair number came from.
        "method_spread_display": (
            f"{_method_spread_points(leg):.1f} pts"
            if _method_spread_points(leg) is not None
            else None
        ),
        "book_count": leg.book_count,
        "books_used": json.loads(leg.books_used_json or "[]"),
        "market_width_display": (
            f"{leg.market_width * 100:.1f} pts"
            if leg.market_width is not None
            else None
        ),
        # Neutral wording is the caller's job, and the reason is arithmetic:
        # a sharp anchor selects AT MOST THREE books, so it is a thinner fair
        # value rather than a better one (CLAUDE.md).
        "anchored_on_sharp": leg.anchored_on_sharp,
        "odds_age_ms": leg.odds_age_now_ms,
        # --- What the twelve mechanical checks said, or why they are silent.
        "skeptic": skeptic,
        "suppressed_reason": facts["suppressed_reason"],
    }


def _serialise_card(card: Card, facts: Optional[dict] = None) -> dict:
    if card.not_built_reason is not None:
        return {
            "key": card.key,
            "title": card.title,
            # On an unbuilt card too: six cards on one screen, and a card
            # the reader cannot name is worse than one they can.
            "what_it_is": card.what_it_is,
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
        "what_it_is": card.what_it_is,
        "legs": [
            _serialise_leg(leg, (facts or {}).get(leg.kalshi_market_ticker))
            for leg in card.legs
        ],
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
            "fair_cost_display": _cost_per_contract(joint.conservative * 1000),
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


#: What a leg's desk facts look like when nothing could be read. Every field
#: absent rather than zeroed -- an ask of 0 is a free contract and a book count
#: of 0 is "no consensus", and neither is what "we did not look" means.
_NO_FACTS: dict = {
    "ask_tenths": None,
    "ask_display": None,
    "depth_at_ask": None,
    "quote_age_ms": None,
    "skeptic": "absent",
    "suppressed_reason": None,
}


def leg_facts(conn, tickers: Sequence[str], *, now_ms: int) -> dict[str, dict]:
    """Kalshi's own price and the skeptic's verdict, for the SELECTED legs.

    **Two queries for the whole ladder, and the scope is the design.** These
    facts are attached after `build_ladder` has chosen its legs -- at most six
    per card across six cards, deduped to roughly fifteen tickers -- not to the
    ~200 candidates the pool holds. Enriching the pool would put a per-row read
    on a path that already runs every pass, which is the N+1 shape
    `/api/slate` is separately being cured of.

    The ask is DERIVED (`1000 - best NO bid`) through `ask_for_side`, the one
    definition in this codebase, so an empty book resolves to `None` rather
    than to the endpoint. A leg whose book is one-sided has no price you could
    pay, and saying so is the point.

    `skeptic` is three-valued, and the third value is why this is not a
    boolean:

        checked            a `recommendations` row exists; its verdict stands
        not_on_this_path   a SPREAD leg. ADR 0070 keeps spread rows off the
                           recommendations path entirely ("Fair rows only, no
                           recommendations", `runner.py`), so the checks did
                           not run and never will on this row
        absent             a moneyline the engine has not priced

    Rendering `not_on_this_path` as a blank would read as "the checks passed",
    which is the flattering misreading of a measurement that never happened.
    """
    if not tickers:
        return {}
    unique = sorted(set(tickers))
    placeholders = ",".join("?" * len(unique))

    quotes = {
        row["ticker"]: row
        for row in conn.execute(
            f"""
            SELECT ticker, observed_ms, confirmed_ms, yes_bid_tenths,
                   no_bid_tenths, no_bid_qty
            FROM (
              SELECT ticker, observed_ms, confirmed_ms, yes_bid_tenths,
                     no_bid_tenths, no_bid_qty,
                     ROW_NUMBER() OVER (
                       PARTITION BY ticker ORDER BY observed_ms DESC
                     ) AS rn
              FROM kalshi_quotes
              WHERE ticker IN ({placeholders})
            ) WHERE rn = 1
            """,
            unique,
        ).fetchall()
    }

    suppressed = {
        row["ticker"]: row["suppressed_reason"]
        for row in conn.execute(
            f"""
            SELECT ticker, suppressed_reason FROM (
              SELECT ticker, suppressed_reason,
                     ROW_NUMBER() OVER (
                       PARTITION BY ticker ORDER BY created_ms DESC
                     ) AS rn
              FROM recommendations
              WHERE ticker IN ({placeholders}) AND side = 'yes'
            ) WHERE rn = 1
            """,
            unique,
        ).fetchall()
    }

    out: dict[str, dict] = {}
    for ticker in unique:
        facts = dict(_NO_FACTS)
        quote = quotes.get(ticker)
        if quote is not None:
            ask = ask_for_side(quote, "yes")
            facts["ask_tenths"] = ask
            facts["ask_display"] = format_price(ask) if ask is not None else None
            facts["depth_at_ask"] = quote["no_bid_qty"]
            # `confirmed_ms` when present: a quote re-observed and unchanged is
            # current, not stale, and ADR 0055 only writes a row when it moves.
            seen = quote["confirmed_ms"] or quote["observed_ms"]
            facts["quote_age_ms"] = max(0, now_ms - seen) if seen else None
        if ticker in suppressed:
            facts["skeptic"] = "checked"
            facts["suppressed_reason"] = suppressed[ticker]
        out[ticker] = facts
    return out


def serialise_ladder(
    ladder: Ladder, *, generated_ms: int, facts: Optional[dict] = None
) -> dict:
    return {
        "generated_ms": generated_ms,
        "cards": [_serialise_card(card, facts) for card in ladder.cards],
        "excluded": ladder.excluded,
        "notes": dict(NOTES),
    }


# ---------------------------------------------------------------------------
# "Price on Kalshi" -- the lookup path (ADR 0070, Slice C).
# ---------------------------------------------------------------------------


class LookupRefused(Exception):
    """A lookup that must not proceed, with the HTTP status and the words."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


#: Collections that accept arbitrary sports legs, tried in order when no
#: enumerated collection covers the card's exact events. The 2026-08-23
#: capture posted NFL legs to `KXMVESPORTSMULTIGAMEEXTENDED-R` and Kalshi
#: minted the market under a `KXMVECROSSCATEGORY` shard, so prefix matching
#: is the honest granularity here.
_FALLBACK_COLLECTION_PREFIXES = (
    "KXMVESPORTSMULTIGAMEEXTENDED",
    "KXMVECROSSCATEGORY",
)

#: `fetch_collections` walks up to 25 pages; a per-tap fetch would spend
#: seconds and rate budget on a list that changes rarely. Cached in-process
#: for an hour -- module state, same lifetime as the API process.
_COLLECTIONS_TTL_MS = 3_600_000
_collections_cache: dict = {"at_ms": 0, "items": None}


def invalidate_collections_cache() -> None:
    """Drop the cached collection list.

    Called when a lookup fails against a collection this cache named. The
    `-R` suffix on collection tickers ROTATES (NEXT.md, 2026-08-23) and the
    fallback is prefix-matched rather than pinned, so a rotation turns every
    tap into a 502 against a ticker that no longer exists -- for up to an
    hour, with no recovery short of restarting the process. A failure is the
    only evidence available that the list has moved, so it is what clears it.
    """
    _collections_cache["items"] = None
    _collections_cache["at_ms"] = 0


async def _collections(api, *, now_ms: int):
    """The collection list, cached. Raises `LookupRefused` when it cannot.

    **An empty result is never cached.** `fetch_collections` returning `[]` is
    indistinguishable at this layer from a transient walk failure, and caching
    it hands the screen "Kalshi lists no combination collection" -- a confident
    statement about the venue -- for the full hour. Unreadable resolves to a
    refusal, never to a fact (`tasks/lessons.md`).
    """
    cache = _collections_cache
    if (
        cache["items"] is not None
        and now_ms - cache["at_ms"] <= _COLLECTIONS_TTL_MS
    ):
        return cache["items"]
    try:
        items = await fetch_collections(api)
    except Exception as exc:  # noqa: BLE001 -- every transport failure is one refusal
        # A cold-cache failure used to escape this function and leave FastAPI
        # to render a bare 500, with no `parlay_lookups` row -- the caller
        # cannot record what it never learned about. Now it is the same shape
        # as every other refusal on this path.
        raise LookupRefused(
            502,
            "Kalshi's list of combination collections could not be read "
            f"({exc}). Nothing was created.",
        ) from exc
    if items:
        cache["items"] = items
        cache["at_ms"] = now_ms
    return items


def _choose_collection(collections, leg_event_tickers: set[str]):
    """The collection to mint under: exact coverage first, then the
    catch-all sports collections by prefix, else nothing (refused in words)."""
    eligible = [
        c for c in collections
        if c.scope in (ComboScope.MULTI_GAME, ComboScope.CROSS_SPORT,
                       ComboScope.CROSS_CATEGORY)
    ]
    covering = [
        c for c in eligible
        if leg_event_tickers <= {leg.event_ticker for leg in c.legs}
    ]
    if covering:
        return min(covering, key=lambda c: (len(c.legs), c.collection_ticker))
    for prefix in _FALLBACK_COLLECTION_PREFIXES:
        matches = sorted(
            (c for c in eligible if c.collection_ticker.startswith(prefix)),
            key=lambda c: c.collection_ticker,
        )
        if matches:
            return matches[0]
    return None


def _record_lookup(conn, *, now_ms, card_key, stake_cents, legs, status,
                   collection_ticker=None, minted=None, no_bid_tenths=None,
                   ask_tenths=None, depth=None, fair_joint=None, hold=None,
                   error=None) -> None:
    """Every lookup is recorded, every outcome -- it minted a real market."""
    conn.execute(
        "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
        "selected_legs, collection_ticker, status, minted_market_ticker, "
        "book_no_bid_tenths, derived_yes_ask_tenths, book_depth, "
        "fair_joint_conservative, hold, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            now_ms, card_key, stake_cents,
            json.dumps([
                {"event_ticker": e, "market_ticker": m} for e, m in legs
            ]),
            collection_ticker, status, minted, no_bid_tenths, ask_tenths,
            depth, fair_joint, hold, error,
        ),
    )
    conn.commit()


async def price_card_on_kalshi(
    conn,
    *,
    card_key: str,
    stake_cents: int,
    requested_legs: Sequence[tuple[str, str]],
    now_ms: int,
    max_odds_age_ms: int,
    api,
) -> dict:
    """Mint (or find) the card's combo on Kalshi and price it off its book.

    The card is re-derived server-side and must match what the client saw --
    a lookup mints a real market, so it must price the card the user tapped,
    not whatever the slate has drifted to. The quoted cost comes from the
    minted market's ORDER BOOK (derived YES ask = 1000 - best resting NO
    bid), never the `/markets` list row (ADR 0012, E2/E3: leg echo, list-vs-
    book skew to 30.5c). An empty book is an honest refusal, not a price --
    and the 2026-08-23 capture shows a freshly minted combo's book IS empty
    on both sides, so that refusal is the expected first answer.

    No fee-net EV anywhere (ADR 0046): the hold is fee-free arithmetic
    (`1 - fair x offered decimal`) and the fee sentence travels beside it.
    """
    candidates, _ = ladder_candidates(
        conn, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms
    )
    ladder = build_ladder(
        candidates, max_odds_age_ms=max_odds_age_ms, now_ms=now_ms
    )
    card = next((c for c in ladder.cards if c.key == card_key), None)
    if card is None:
        raise LookupRefused(404, f"no card named {card_key!r}")
    if card.not_built_reason is not None:
        raise LookupRefused(
            409, f"the {card.title} card is not built right now: "
                 f"{card.not_built_reason}"
        )

    served = {(l.kalshi_event_ticker, l.kalshi_market_ticker) for l in card.legs}
    requested = set(requested_legs)
    if served != requested:
        raise LookupRefused(
            409,
            "the slate has moved since this card was served -- its legs are "
            "no longer the ones you saw. Refresh the page and look again "
            "before pricing.",
        )

    # `sorted`, not `list`: `served` is a set, so its iteration order varies
    # by hash seed across processes. That order is what goes on the wire to
    # Kalshi and into `selected_legs`, which makes the audit table's rows
    # incomparable between restarts for no reason at all.
    legs = sorted(served)
    try:
        collections = await _collections(api, now_ms=now_ms)
    except LookupRefused as exc:
        # Recorded, then re-raised unchanged. The audit table's docstring
        # promises a row for every outcome, and a failure to read the
        # collection list is an outcome.
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error", error=exc.detail,
        )
        raise
    collection = _choose_collection(
        collections, {event for event, _ in served}
    )
    if collection is None:
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="no_collection",
        )
        return {
            "status": "no_collection",
            "words": (
                "Kalshi lists no combination collection that accepts these "
                "legs right now. Nothing was created."
            ),
        }

    try:
        response = await lookup_combo(
            api, collection.collection_ticker, legs,
            side="yes", allow_market_creation=True,
        )
    except Exception as exc:  # noqa: BLE001 -- recorded, then re-raised as words
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error",
            collection_ticker=collection.collection_ticker, error=str(exc),
        )
        # The collection ticker we just posted to is the most likely thing
        # that was wrong -- the `-R` suffix rotates and the fallback is
        # prefix-matched. Without this, one rotation means an hour of 502s.
        invalidate_collections_cache()
        raise LookupRefused(
            502, f"Kalshi refused the combination: {exc}"
        ) from exc

    minted = response.get("market_ticker") or (
        (response.get("market") or {}).get("ticker")
    )
    if not minted:
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error",
            collection_ticker=collection.collection_ticker,
            error=f"no market_ticker in response keys {sorted(response)}",
        )
        raise LookupRefused(
            502, "Kalshi answered without naming the minted market."
        )

    # Inside its own try: the market is ALREADY MINTED by the time this runs,
    # so an httpx timeout / 429 / 5xx here loses a real ticker off the audit
    # table -- the one outcome where a missing row costs something, because
    # nothing else in this repo records that the combination now exists.
    try:
        book_payload = await api.orderbook(minted, depth=10)
        book = OrderBook(ticker=minted)
        book.apply_snapshot(book_payload, None, now_ms)
    except Exception as exc:  # noqa: BLE001 -- recorded WITH the ticker, then worded
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error",
            collection_ticker=collection.collection_ticker, minted=minted,
            error=f"orderbook after mint: {exc}",
        )
        raise LookupRefused(
            502,
            f"Kalshi created the market ({minted}) but its order book could "
            f"not be read ({exc}). Nothing is priced; the combination exists "
            "and can be looked at in the Kalshi app.",
        ) from exc

    joint = card.joint
    assert joint is not None
    # The derived-ask identity, through the ONE implementation. `1000 -
    # best_no_bid` was written out by hand here; `OrderBook.best_yes_ask` is
    # the same arithmetic via `complement`, and the venue's most-repeated
    # correction does not need a second copy.
    best_no_bid = book.best_no_bid
    ask_tenths = book.best_yes_ask

    if ask_tenths is None:
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="book_empty",
            collection_ticker=collection.collection_ticker, minted=minted,
            fair_joint=joint.conservative,
        )
        return {
            "status": "book_empty",
            "minted_market_ticker": minted,
            "words": (
                "Kalshi created the market, but nothing is resting in its "
                "book -- no one is offering to sell this combination, so "
                "there is no price you could actually pay right now. Every "
                "freshly minted combo book this tool has read looked exactly "
                "like this; the app may show a number, but a number nobody "
                "will trade at is not a cost. Try again shortly, or build it "
                "in the Kalshi app and compare its quote to the fair value "
                "on the card."
            ),
        }

    depth = book.depth_at_ask("yes")
    valuation = value_parlay(
        ParlayQuote(
            legs=tuple(
                Leg(
                    label=l.kalshi_market_ticker,
                    probability=l.p_conservative,
                    event_key=l.odds_event_id,
                    league=l.league,
                    commence_ms=l.commence_ms,
                )
                for l in card.legs
            ),
            offered_decimal=1000.0 / ask_tenths,
        )
    )
    _record_lookup(
        conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
        legs=legs, status="priced",
        collection_ticker=collection.collection_ticker, minted=minted,
        no_bid_tenths=best_no_bid, ask_tenths=ask_tenths, depth=depth,
        fair_joint=joint.conservative, hold=valuation.hold,
    )

    return {
        "status": "priced",
        "minted_market_ticker": minted,
        "quoted": {
            # Derived from the book, stated so the screen can say so: the
            # ask is the complement of the best resting NO bid.
            "ask_display": _cost_per_contract(ask_tenths),
            "depth_display": (
                None if depth is None
                else f"about {depth:g} contracts resting at that price"
            ),
            "at_stake": _at_stake(stake_cents, ask_tenths=ask_tenths, depth=depth),
        },
        "fair": {
            "conservative_percent_display": _percent(joint.conservative),
            "fair_cost_display": _cost_per_contract(joint.conservative * 1000),
        },
        "hold_display": f"{valuation.hold * 100:.1f}%",
        "verdict": valuation.verdict,
        "notes": {
            "enter_only": NOTES["enter_only"],
            "fee": NOTES["fee"],
        },
    }


def build_ladder_payload(conn, *, now_ms: int, max_odds_age_ms: int) -> dict:
    candidates, excluded = ladder_candidates(
        conn, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms
    )
    ladder = build_ladder(
        candidates, max_odds_age_ms=max_odds_age_ms, now_ms=now_ms
    )
    merged = dict(ladder.excluded)
    for reason, n in excluded.items():
        merged[reason] = merged.get(reason, 0) + n
    # The selected legs, not the candidate pool: at most six per card across
    # six cards, deduped. `leg_facts` is two queries for the whole ladder.
    selected = [
        leg.kalshi_market_ticker for card in ladder.cards for leg in card.legs
    ]
    return serialise_ladder(
        Ladder(cards=ladder.cards, excluded=merged),
        generated_ms=now_ms,
        facts=leg_facts(conn, selected, now_ms=now_ms),
    )
