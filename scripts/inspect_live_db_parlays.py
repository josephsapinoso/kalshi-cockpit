"""The parlay desk and the combination markets it touches.

Queries: `parlay-candidates-timing`, `parlay-lookups-tail`,
`combo-bids-tail`, `combo-position-gaps`, `combo-position-orphans`,
`ladder-fixtures`, `scout-briefings`, `scout-watch-log`, `agent-spend`,
`game-script-card-stamps`, `game-script-card-rechecks`,
`game-script-card-refusals`, `parlay-lookup-errors`, `own-open-rfqs`,
`combo-markup`.

The candidate scan timed and EXPLAINed on the live database, the "Price on
Kalshi" taps that minted a combination market -- the only record anywhere
that a given `KXMVE` market exists on the exchange -- and the resting bids
the desk has placed on one, with the auto-cancel deadline the screen
promises. No P&L, no outcome, no verdict in any of the three.

`_SQL_PARLAY_CANDIDATES` is a second copy of `backend.parlays.CANDIDATE_SQL`,
duplicated because this family imports nothing from `backend`, and pinned
byte-identical by `tests/test_inspect_live_db.py`.

**Every SQL string in this module is a constant.** This module is imported by
`inspect_live_db.py`, is never run directly, and inherits every disclaimer in
that file's docstring.
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from inspect_live_db_common import (
    Section,
    _MS_PER_DAY,
    _derive_iso,
    _fetch,
    _iso,
    _window_section,
)


# ---------------------------------------------------------------------------
# The parlay desk's candidate scan: where its 30 seconds go.
# ---------------------------------------------------------------------------
#
# **Measured on live 2026-08-30, after the WAL fix and on a healthy box:**
# `/api/board` answered in ~2s over the loopback and `/api/parlays` did not
# answer inside `fetch_live_route`'s 30s timeout, twice. The copula is not the
# cost -- timed at 0.09s for three legs and 0.15s for six on a dev box, so
# under a second for the whole ladder -- which leaves this statement.
#
# **The SQL is a COPY, held byte-identical by a test**, on the same terms as
# `_ACTIONABLE_PREDICATE` above and for the same reason: this script imports
# nothing from `backend`, because `python /app/scripts/...` puts `/app/scripts`
# on `sys.path` and not `/app`. A plan measured for a statement nobody runs is
# worse than no plan, so `tests/test_inspect_live_db.py` compares this string
# to `backend.parlays.CANDIDATE_SQL` and goes red the day they diverge.
_SQL_PARLAY_CANDIDATES = """
        SELECT computed_ms, market, outcome_name, outcome_point,
               outcome_description,
               p_multiplicative, p_additive, p_power, p_shin,
               p_conservative, oldest_book_age_ms,
               confirmed_ms, confirmed_oldest_book_age_ms, link_id,
               market_width, book_count, books_used, anchored_on_sharp,
               kalshi_event_ticker, odds_event_id,
               commence_ms, home_team, away_team, sport_key,
               event_title
        FROM (
        SELECT f.computed_ms, f.market, f.outcome_name, f.outcome_point,
               f.outcome_description,
               f.p_multiplicative, f.p_additive, f.p_power, f.p_shin,
               f.p_conservative, f.oldest_book_age_ms,
               -- **ADR 0133.** `_live_age_ms` COALESCEs each of these onto
               -- the frozen pair beside it -- NULL means "never
               -- re-confirmed", true of every row before v36 and of a row
               -- whose payload has only ever appeared once since.
               f.confirmed_ms, f.confirmed_oldest_book_age_ms, f.link_id,
               f.market_width, f.book_count, f.books_used, f.anchored_on_sharp,
               l.kalshi_event_ticker, l.odds_event_id,
               o.commence_ms, o.home_team, o.away_team, o.sport_key,
               e.title AS event_title,
               -- **The freshest row per identity, chosen in SQL.** This used
               -- to be done in Python, below, after `fetchall()` had brought
               -- the whole 24-hour window into the process: 463,866 rows and
               -- ~557 MB on a 2 GB box that sits at ~1.03 GB at rest, for a
               -- result the dedup then reduced to a few thousand. Repeated
               -- visits OOM-killed uvicorn, and because `entrypoint.sh` uses
               -- `wait -n`, killing that child tore down the container and
               -- restarted the recorder too -- so opening one tab took the
               -- whole site down. Measured at about 91 seconds of outage.
               --
               -- The partition is byte-for-byte the Python key, INCLUDING
               -- `outcome_description`. That column is NULL on team markets
               -- and load-bearing on props, where `outcome_name` is only
               -- "Over"/"Under": without it two pitchers in one game quoted
               -- at the same rung collapse onto one row. SQL `PARTITION BY`
               -- groups NULLs together, which is what a Python dict key of
               -- `None` does, so the two agree on exactly this point.
               --
               -- `f.rowid` breaks ties. The Python `setdefault` kept whichever
               -- row SQLite happened to return first among equal
               -- `computed_ms`, which was arbitrary but not random; this is
               -- arbitrary and STABLE, so two calls a millisecond apart cannot
               -- offer different legs for the same rung.
               ROW_NUMBER() OVER (
                   PARTITION BY f.link_id, f.market, f.outcome_name,
                                f.outcome_description, f.outcome_point
                   ORDER BY f.computed_ms DESC, f.rowid DESC
               ) AS rn
        FROM fair_prices f
        JOIN event_links l ON l.id = f.link_id
        JOIN kalshi_events e ON e.event_ticker = l.kalshi_event_ticker
        JOIN (
            SELECT odds_event_id, MIN(commence_ms) AS commence_ms,
                   home_team, away_team, sport_key
            FROM odds_snapshots
            -- **Restricted to LINKED events, and this cannot change the
            -- answer.** The outer query inner-joins on `l.odds_event_id`, so
            -- an event absent from `event_links` was going to be discarded
            -- anyway -- the subquery was grouping the entire history of the
            -- table to build rows it then threw away.
            --
            -- Measured 2026-08-26: without it the plan reads
            -- `SCAN odds_snapshots` on every request, and `/api/parlays`
            -- answered in 15s while every other route was sub-second. With it,
            -- plus `idx_odds_event_commence`, the plan is
            -- `SEARCH odds_snapshots (odds_event_id=?)`.
            --
            -- **Deliberately NOT filtered on `commence_ms` here**, which would
            -- be the obvious way to cut it further. `MIN(commence_ms)` is the
            -- fixture's earliest recorded start, and filtering rows before
            -- taking the MIN would let a RESCHEDULED fixture through whose
            -- true earliest start is in the past. Rare, and a silent wrong
            -- answer is worse than a slower right one.
            WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)
            GROUP BY odds_event_id
        ) o ON o.odds_event_id = l.odds_event_id
        WHERE f.market IN ('h2h', 'spreads', 'totals', 'pitcher_strikeouts', 'batter_total_bases', 'batter_hits', 'batter_home_runs', 'batter_rbis', 'player_pass_yds', 'player_reception_yds', 'player_rush_yds')
          -- **Either stamp, since the ladder-scan-keys-on-the-confirmed-
          -- stamp fix.** `computed_ms` freezes at first appearance (ADR
          -- 0133) and only `confirmed_ms` moves on a row that keeps getting
          -- re-derived unchanged, so a predicate on `computed_ms` alone can
          -- miss a row that is fresh right now. `confirmed_ms >=
          -- computed_ms` whenever it is set, so this OR is exactly
          -- `COALESCE(confirmed_ms, computed_ms) >= ?` -- not an
          -- approximation of it -- while staying sargable: each arm seeks
          -- its own index, `idx_fair_market_computed` for the first and the
          -- PARTIAL `idx_fair_market_confirmed` for the second, and SQLite
          -- runs the pair as `MULTI-INDEX OR` rather than falling back to a
          -- scan the way a COALESCE in the predicate would.
          AND (f.computed_ms >= ? OR f.confirmed_ms >= ?)
          AND o.commence_ms IS NOT NULL AND o.commence_ms > ?
        )
        WHERE rn = 1
        ORDER BY computed_ms DESC
        """

#: The two halves, timed separately. The outer statement is the whole scan; the
#: subquery is the `odds_snapshots` GROUP BY that has no time filter at all --
#: deliberately, so a rescheduled fixture cannot be missed -- and therefore
#: grows with the entire history of the table rather than with tonight's slate.
_SQL_PARLAY_COMMENCE_SUBQUERY = (
    "SELECT odds_event_id, MIN(commence_ms) AS commence_ms "
    "FROM odds_snapshots "
    "WHERE odds_event_id IN (SELECT odds_event_id FROM event_links) "
    "GROUP BY odds_event_id"
)

_SQL_PARLAY_ROW_CENSUS = (
    "SELECT (SELECT COUNT(*) FROM fair_prices) AS fair_prices_rows, "
    "       (SELECT COUNT(*) FROM fair_prices WHERE computed_ms >= :floor) "
    "           AS fair_prices_in_scan_window, "
    "       (SELECT COUNT(*) FROM odds_snapshots) AS odds_snapshots_rows, "
    "       (SELECT COUNT(*) FROM event_links) AS event_links_rows"
)


def _q_parlay_candidates_timing(conn: sqlite3.Connection, args) -> list[Section]:
    """Time the parlay candidate scan and print its query plan.

    Four sections: a row census of what the scan reads over, the wall time of
    the whole statement, the wall time of the `odds_snapshots` GROUP BY on its
    own, and `EXPLAIN QUERY PLAN` for the whole statement.

    What this does not establish
    ----------------------------
    - **Not what a request costs.** This is one statement on an idle-ish
      connection with its own page cache. The route opens a fresh read-only
      connection per request, adds `leg_facts`, the per-event market fetches
      and the copulas, and competes with the recorder's writer. A fast reading
      here does not clear the route.
    - **Not a stable number.** The page cache makes the second run of anything
      faster than the first, and the run order below is fixed rather than
      randomised, so the subquery is measured warm after the outer statement
      has already touched the same table. Read the two as a floor.
    - **Nothing about the fix.** A plan naming a SCAN is not a verdict that an
      index is the answer; some scans are the cheapest available reading.
    """
    now_ms = int(time.time() * 1000)
    # **The deployed window, not the historical one.** This was `now - 24h`
    # when the query was written, which is what the route then used; the route
    # now derives its floor as 8x `max_odds_age_ms` (2 hours at the deployed
    # `MAX_ODDS_AGE_S`). An instrument left on the old width would keep
    # reporting the cost of a scan nobody runs -- and would read as evidence
    # that the fix did nothing.
    floor_ms = now_ms - 2 * 3_600_000
    census = _fetch(
        conn, _SQL_PARLAY_ROW_CENSUS, {"floor": floor_ms},
        title="what the candidate scan reads over",
        cap=args.limit,
    )

    started = time.perf_counter()
    rows = conn.execute(
        _SQL_PARLAY_CANDIDATES, (floor_ms, floor_ms, now_ms)
    ).fetchall()
    whole_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    sub = conn.execute(_SQL_PARLAY_COMMENCE_SUBQUERY).fetchall()
    sub_ms = (time.perf_counter() - started) * 1000.0

    timings = Section(
        title="wall time, this connection, in this order",
        columns=("statement", "rows", "ms"),
        rows=[
            ("whole candidate scan", len(rows), round(whole_ms, 1)),
            ("odds_snapshots MIN(commence_ms) GROUP BY", len(sub),
             round(sub_ms, 1)),
        ],
    )

    plan = _fetch(
        conn, "EXPLAIN QUERY PLAN " + _SQL_PARLAY_CANDIDATES,
        (floor_ms, floor_ms, now_ms),
        title="EXPLAIN QUERY PLAN: whole candidate scan",
        cap=args.limit,
    )
    return [census, timings, plan]


# ---------------------------------------------------------------------------
# What the "Price on Kalshi" taps actually minted.
# ---------------------------------------------------------------------------
#
# Every tap writes a `parlay_lookups` row whatever the outcome, and the
# `minted_market_ticker` on it is the ONLY record that a combination market now
# exists on the exchange -- nothing else in this repo stores one. That makes
# this the lookup path's audit trail and the only way to name a real KXMVE
# market from outside the venue.
#
# **Prices, not verdicts.** The row carries what the book said and what the
# card's fair value was; it carries no P&L, no CLV and no outcome, and this
# query adds none.
_SQL_PARLAY_LOOKUPS_TAIL = (
    "SELECT id, requested_ms, card_key, stake_cents, status, "
    "       collection_ticker, minted_market_ticker, book_no_bid_tenths, "
    "       derived_yes_ask_tenths, book_depth, fair_joint_conservative, "
    "       hold, collection_unverified, error, selected_legs "
    "FROM parlay_lookups ORDER BY id DESC"
)


def _q_parlay_lookups_tail(conn: sqlite3.Connection, args) -> list[Section]:
    """The last N "Price on Kalshi" taps, newest first, with their tickers.

    What this does not establish
    ----------------------------
    - **Not that a minted market still trades.** A ticker here was created at
      `requested_ms`; whether it is open, settled or empty now is a question
      for the venue, not for this table.
    - **Nothing about whether a tap was a good idea.** `hold` is fee-free
      arithmetic against a fair value the same row records, and ADR 0046 keeps
      the combination fee model unverified. No row here is a verdict.
    - **Not a complete census of markets this account created.** It records
      what THIS instance minted through the desk. Anything built by hand in
      the Kalshi app is absent by construction.
    """
    tail = _fetch(
        conn, _SQL_PARLAY_LOOKUPS_TAIL, (),
        title=f"parlay_lookups: last {args.tail} taps, newest first",
        cap=min(args.tail, args.limit),
        requested=args.tail,
    )
    return [_derive_iso(tail, "requested_ms", "requested_iso")]


# ---------------------------------------------------------------------------
# The resting bids the desk has placed (ADR 0084).
# ---------------------------------------------------------------------------
#
# **The only order shape in this database that can still be working.** Every
# other real order this project has sent was immediate-or-cancel: filled or
# dead, and finished by the time its row was written. A combination has no
# resting YES bid on any book this repo has read, so the desk becomes the offer
# and that offer outlives the request.
#
# `cancel_after_ms` is the load-bearing column and the reason this query
# exists. It is the earliest leg's kickoff, and `backend/bid_watch.py`
# withdraws the bid when it passes. A NULL there means the bid will NEVER be
# withdrawn automatically -- the screen promises it will be, so a null is a
# broken promise rather than a missing convenience.
#
# No P&L, no outcome, no verdict: prices and clocks only.
_SQL_COMBO_BIDS_TAIL = (
    "SELECT id, placed_ms, card_key, ticker, status, exchange_index, "
    "       count, limit_price_tenths, "
    "       (count * limit_price_tenths) AS committed_tenths, "
    "       cancel_after_ms, "
    "       CASE WHEN cancel_after_ms IS NULL THEN 'NEVER -- no deadline' "
    "            ELSE 'set' END AS auto_cancel, "
    "       kalshi_order_id, dry_run, cancelled_ms, cancel_reduced_by, "
    "       cancel_reason, error_text "
    "FROM combo_orders ORDER BY id DESC"
)


def _q_combo_bids_tail(conn: sqlite3.Connection, args) -> list[Section]:
    """The last N resting bids, newest first, with their auto-cancel deadlines.

    What this does not establish
    ----------------------------
    - **Not whether a bid is still resting AT THE VENUE.** This is the desk's
      record. A bid filled, cancelled or expired on Kalshi since it was written
      shows here as whatever the desk last learned. `/portfolio/orders` is the
      authority; this is what the desk believes.
    - **Not that the deadline was enforced.** `auto_cancel = set` means a
      deadline exists, not that a loop read it. `cancelled_ms` with
      `cancel_reason` naming the first leg is the evidence that it ran.
    - **Nothing about profit.** A resting bid has no outcome and this query
      reports none.
    """
    tail = _fetch(
        conn, _SQL_COMBO_BIDS_TAIL, (),
        title=f"combo_orders: last {args.tail} bids, newest first",
        cap=min(args.tail, args.limit),
        requested=args.tail,
    )
    for col, iso in (
        ("placed_ms", "placed_iso"),
        ("cancel_after_ms", "cancel_after_iso"),
        ("cancelled_ms", "cancelled_iso"),
    ):
        tail = _derive_iso(tail, col, iso)
    return [tail]


# ---------------------------------------------------------------------------
# Combinations the desk bought and nothing is watching (ADR 0125).
# ---------------------------------------------------------------------------
#
# **The detector for a write that is designed to fail silently.**
# `_record_combo_position` runs inside a `try/except Exception` that swallows
# every failure and logs it (`backend/api/routes.py`, "Never into the order
# path"). That is the correct design -- bookkeeping must never turn a purchase
# that already spent money into a 500 -- but it means the row that puts a
# combination under `/hedge`'s watch can fail to appear and nothing raises.
# A walk of `manual_orders` against `parlay_positions` is the only detector
# that failure mode has.
#
# It also catches the gap this query was written for: a fill that landed
# BEFORE the wiring deployed. `manual_orders` id=4 filled 2026-09-09 15:11:56Z
# and the wiring deployed 15:56:45Z, so a live position existed with the exit
# screen never having heard of it. That is not a defect in the wiring; it is
# the class of thing only a reconciler finds.
#
# **Both money-spending statuses, not just `filled`.** `partially_filled`
# bought contracts too, and ADR 0125 watches a part-fill at the size the VENUE
# reports rather than the size requested. A reconciler that looked only at
# `filled` would report health over a real half-position.
#
# `unrecognised_response` is reported SEPARATELY and is not counted as a gap:
# the route's own note says such an order MAY have been placed. "We do not
# know whether money moved" and "money moved and nothing is watching it" are
# different states, and collapsing them would let the uncertain one hide
# inside the certain one.
#
# **A position closes by VANISHING, so `exposure` asks the latest poll.**
# `venue_positions` is an append-only poll record: while a position is held it
# reappears every cycle, and when it settles it simply stops being written.
# Reading the newest row FOR THAT TICKER therefore reports whatever was true
# the last time it existed -- which for a settled position is "4 contracts,
# open". The first version of this query did exactly that and called two
# positions that settled on 2026-09-08 `OPEN AT VENUE -- UNWATCHED`, which is
# silence read as exposure, in a column written to detect silence read as
# health. So the test is membership of the most recent SUCCESSFUL `positions`
# poll, not the most recent row bearing the ticker. `contracts_when_last_seen`
# is named for what it is, and `venue_polled_ms` says when: neither is evidence
# of a holding now.
#
# **What this emits from `parlay_positions`: nothing.** The table appears only
# inside a `NOT EXISTS`, so every row this query prints is a row for which the
# position does NOT exist. It cannot print a position, a count of positions,
# or a rate over them.
_SQL_COMBO_POSITION_GAPS = (
    "SELECT m.id AS manual_order_id, m.submitted_ms, m.ticker, "
    "       m.count AS contracts_ordered, m.status, "
    "       (SELECT v.contracts FROM venue_positions v "
    "         WHERE v.ticker = m.ticker ORDER BY v.id DESC LIMIT 1) "
    "         AS contracts_when_last_seen, "
    "       (SELECT v.polled_ms FROM venue_positions v "
    "         WHERE v.ticker = m.ticker ORDER BY v.id DESC LIMIT 1) "
    "         AS venue_polled_ms, "
    "       CASE WHEN (SELECT MAX(id) FROM poll_log "
    "                   WHERE endpoint = 'positions' AND ok = 1) IS NULL "
    "            THEN 'no successful positions poll -- unknown' "
    "            WHEN NOT EXISTS (SELECT 1 FROM venue_positions v "
    "                              WHERE v.ticker = m.ticker) "
    "            THEN 'never seen at venue' "
    "            WHEN EXISTS (SELECT 1 FROM venue_positions v "
    "                          WHERE v.ticker = m.ticker "
    "                            AND v.poll_log_id = (SELECT MAX(id) "
    "                                FROM poll_log WHERE endpoint = 'positions' "
    "                                  AND ok = 1) "
    "                            AND v.contracts > 0) "
    "            THEN 'OPEN AT VENUE -- UNWATCHED' "
    "            ELSE 'gone from the latest positions poll -- closed' "
    "       END AS exposure "
    "FROM manual_orders m "
    "WHERE m.ticker LIKE 'KXMVE%' "
    "  AND m.dry_run = 0 "
    "  AND m.status IN ('filled', 'partially_filled') "
    "  AND NOT EXISTS (SELECT 1 FROM parlay_positions p "
    "                   WHERE p.combo_ticker = m.ticker) "
    "ORDER BY m.submitted_ms DESC"
)

# The orders that spent money only MAYBE. Same shape, no `NOT EXISTS`: an
# `unrecognised_response` is unresolved regardless of what any table holds,
# and the answer is at the venue rather than here.
_SQL_COMBO_ORDERS_UNRESOLVED = (
    "SELECT m.id AS manual_order_id, m.submitted_ms, m.ticker, "
    "       m.count AS contracts_ordered, m.status, m.error_text, "
    "       (SELECT v.contracts FROM venue_positions v "
    "         WHERE v.ticker = m.ticker ORDER BY v.id DESC LIMIT 1) "
    "         AS venue_contracts_latest "
    "FROM manual_orders m "
    "WHERE m.ticker LIKE 'KXMVE%' "
    "  AND m.dry_run = 0 "
    "  AND m.status = 'unrecognised_response' "
    "ORDER BY m.submitted_ms DESC"
)


def _q_combo_position_gaps(conn: sqlite3.Connection, args) -> list[Section]:
    """Combinations bought with real money that no `parlay_positions` row watches.

    A `KXMVE` combination is enter-only -- `yes_dollars` empty on 40 of 40
    books this repo has read -- so hedging a leg is the only exit it has, and
    `/hedge` can only watch what `parlay_positions` holds. A row here is a
    position with no exit screen. `exposure = OPEN AT VENUE -- UNWATCHED` is
    the operational alarm; the others are history.

    What this does not establish
    ----------------------------
    - **Not the registered adoption statistic, and it cannot be turned into
      it.** `docs/measurements/2026-09-08-parlay-positions-check-amendment-registration.md`
      measures `R / G` over *sittings*, where `R` counts sittings in which a
      `parlay_positions` row with `source = 'kalshi_combo'` was created. This
      query emits no `parlay_positions` row, no count of them and no
      denominator of sittings. It reports the complement -- orders with no
      position -- and reports it per order, not per sitting. **It carries no
      verdict on that registration and may not be cited in one.** The §8 read
      is a single read on or after 2026-09-15 by that registration's own
      script; this is not it and must never be recorded as it.
    - **Not that a listed position is still open.** `venue_contracts_latest`
      is the last poll this database saw, and `venue_polled_ms` says when.
      Kalshi is the authority; this is what the desk last learned.
    - **Not that an absent row means the write failed.** A fill that predates
      the ADR 0125 deploy never had a writer at all, which is a gap in the
      calendar rather than a fault in the code. The `submitted_ms` is what
      separates the two, and only a human holding the deploy time can do it.
    - **Nothing about profit, outcome or whether any bet was a good idea.**
      No P&L, no settlement, no CLV, no typed estimate. Prices and clocks
      only, on the same terms as every other query in this module.
    """
    gaps = _fetch(
        conn, _SQL_COMBO_POSITION_GAPS, (),
        title=(
            "manual_orders: real combination fills with NO parlay_positions "
            "row -- /hedge cannot see these "
            "[operational only: carries NO verdict on the 2026-09-08 "
            "parlay-positions registration and is NOT its section 8 read]"
        ),
        cap=args.limit,
    )
    gaps = _derive_iso(gaps, "submitted_ms", "submitted_iso")
    gaps = _derive_iso(gaps, "venue_polled_ms", "venue_last_seen_iso")

    unresolved = _fetch(
        conn, _SQL_COMBO_ORDERS_UNRESOLVED, (),
        title=(
            "manual_orders: real combination orders whose fate is UNKNOWN "
            "(unrecognised_response) -- check the Kalshi app, not this table "
            "[operational only: carries NO verdict on the 2026-09-08 "
            "parlay-positions registration and is NOT its section 8 read]"
        ),
        cap=args.limit,
    )
    unresolved = _derive_iso(unresolved, "submitted_ms", "submitted_iso")
    return [gaps, unresolved]


# ---------------------------------------------------------------------------
# The inverse: positions with no order behind them (2026-09-17).
# ---------------------------------------------------------------------------
#
# `combo-position-gaps` above answers "a real fill with nobody watching it".
# Nothing answered the other direction -- "a watched position with no fill
# traceable behind it" -- and live carries exactly that shape: read
# 2026-09-17 ~00:40Z, 16 `manual_orders` rows against 17 open
# `parlay_positions`. Ids 1-2's orders have no position (the gaps query
# above); ids 11-15 are open positions with `combo_ticker` and `placed_ms`
# both NULL.
#
# **That NULL pair is a DESIGNED state here, and this query must not blur it
# with a real defect.** `hedge.record_position` (`backend/hedge.py:350`) has
# two callers: `POST /api/hedge/positions` (`routers/hedge.py:73`), where Joe
# types a ticket by hand and both join columns default to `None` -- every
# `source = 'sportsbook'` row is shaped like this ALWAYS, because a
# sportsbook slip has no Kalshi ticker to record, and a `kalshi_combo` row
# can be too, if he logged a combination bought outside this desk's order
# path -- and `_record_combo_position` (`backend/api/routes.py`, the fill
# path), which always sets both together. So `combo_ticker IS NULL` is
# reported as the expected, harmless case, in its own section; a position
# that DOES carry a ticker and still joins to no order is the one worth an
# eyebrow, and it gets a section of its own rather than a mixed list a
# reader has to re-triage by eye.
#
# The join mirrors `_SQL_COMBO_POSITION_GAPS`'s own: ticker equality only, no
# status or `dry_run` filter on the `manual_orders` side, because the
# question here is whether an order ROW exists at all, not whether it filled.
_SQL_POSITIONS_HAND_RECORDED = (
    "SELECT p.id AS position_id, p.created_ms, p.source, p.label, "
    "       p.stake_tenths, p.status "
    "FROM parlay_positions p "
    "WHERE p.status = 'open' "
    "  AND p.combo_ticker IS NULL "
    "ORDER BY p.created_ms DESC"
)

# `combo_ticker IS NOT NULL` and still no `manual_orders` row names it.
# **Not proof of a defect on its own** -- `POST /api/hedge/positions` accepts
# a caller-supplied `combo_ticker` (`request.combo_ticker`, `routers/hedge.py`),
# so a hand-typed ticket that happens to name a real minted market is
# indistinguishable here from a fill whose position-writer lost the row. This
# section is the alarm nothing else raises; it is not a verdict on which of
# the two happened.
_SQL_POSITIONS_TICKETED_ORPHAN = (
    "SELECT p.id AS position_id, p.created_ms, p.source, p.label, "
    "       p.stake_tenths, p.placed_ms, p.status, p.combo_ticker "
    "FROM parlay_positions p "
    "WHERE p.status = 'open' "
    "  AND p.combo_ticker IS NOT NULL "
    "  AND NOT EXISTS (SELECT 1 FROM manual_orders m "
    "                   WHERE m.ticker = p.combo_ticker) "
    "ORDER BY p.created_ms DESC"
)


def _q_combo_position_orphans(conn: sqlite3.Connection, args) -> list[Section]:
    """Open `parlay_positions` rows with no `manual_orders` row behind them.

    The inverse of `combo-position-gaps`: that query finds a real fill with
    no position watching it; this one finds a watched position with no order
    row traceable behind it. Two sections, because the two ways
    `combo_ticker` can fail to join are not the same fact:

    - **hand-recorded** (`combo_ticker IS NULL`) is the ordinary shape of a
      `POST /api/hedge/positions` entry -- every `source = 'sportsbook'` row
      is like this always, since a sportsbook slip has no Kalshi ticker, and
      a `kalshi_combo` row can be too, if Joe logged a combination he bought
      without going through this desk's order path. Expected, not a defect.
    - **ticketed** (`combo_ticker IS NOT NULL` and still no matching order)
      is the one worth attention: either `_record_combo_position`'s write
      genuinely never reached the table it targets, or Joe hand-typed a
      `combo_ticker` on a `POST /api/hedge/positions` call that names a real
      market but was never routed through `/api/manual-orders`. This query
      cannot tell those apart -- see below.

    What this does not establish
    ----------------------------
    - **Not that a "ticketed" row is a lost write.** `POST
      /api/hedge/positions` takes a caller-supplied `combo_ticker`
      (`routers/hedge.py`), so a hand-typed ticket naming a real minted
      market is indistinguishable here from a fill whose position-writer
      failed. Only reading `manual_orders` for that exact ticker by hand, or
      asking Joe how the row was entered, resolves it.
    - **Not whether a position is still open at the venue.** `status = 'open'`
      is this table's own belief, never re-polled here.
    - **Nothing about profit, outcome, or whether logging a position by hand
      instead of through the order path was the right call.**
    - **Not a count, a rate, or anything comparable across a run.** Bounded
      by `--limit` like every query in this module; a truncated section says
      so rather than pretending the population was smaller.
    """
    hand_recorded = _fetch(
        conn, _SQL_POSITIONS_HAND_RECORDED, (),
        title=(
            "parlay_positions: OPEN, no combo_ticker -- hand-recorded, "
            "expected to have no manual_orders row"
        ),
        cap=args.limit,
    )
    hand_recorded = _derive_iso(hand_recorded, "created_ms", "created_iso")

    ticketed_orphan = _fetch(
        conn, _SQL_POSITIONS_TICKETED_ORPHAN, (),
        title=(
            "parlay_positions: OPEN, HAS a combo_ticker, and NO manual_orders "
            "row names it -- either a lost write or a hand-typed ticket; "
            "this query cannot tell which"
        ),
        cap=args.limit,
    )
    ticketed_orphan = _derive_iso(ticketed_orphan, "created_ms", "created_iso")
    ticketed_orphan = _derive_iso(ticketed_orphan, "placed_ms", "placed_iso")
    return [hand_recorded, ticketed_orphan]


# ---------------------------------------------------------------------------
# ladder-fixtures: a series, not one reading, for the auto-convener's floor.
# ---------------------------------------------------------------------------
#
# One reading exists (2026-09-20T22:03Z, `/api/parlays`): 21 leg slots across
# 9 distinct fixtures. A single instant cannot say whether that is a typical
# night or an outlier, so this counts the same quantity -- fixtures with a
# usable leg -- across the last several budget days.

#: Team markets only. `POOL_MARKETS` in `backend/parlays.py` also admits prop
#: markets, but the prop keys are PER SPORT (`MLB_PROP_BASE_MARKETS`,
#: `NFL_PROP_BASE_MARKETS`, ...) and this family imports nothing from
#: `backend`, so there is no single literal list to copy without it going
#: stale the day a sport's prop keys change. Team markets are the stable
#: subset every sport in the pool shares. **This under-counts** relative to
#: the ladder's true pool whenever a prop-only fixture would have qualified.
_LADDER_FIXTURES_MARKETS: tuple[str, ...] = ("h2h", "spreads", "totals")
_LADDER_FIXTURES_MARKETS_SQL = ", ".join(f"'{m}'" for m in _LADDER_FIXTURES_MARKETS)

#: The freshness window applied AT the cutoff, milliseconds. Matches the
#: deployed `MAX_ODDS_AGE_S = 900` (`fly.live.toml`, `.env.example`) --
#: duplicated here for the same reason `_LADDER_FIXTURES_MARKETS` is a
#: duplicate rather than an import, and just as liable to drift the day that
#: value changes on live.
_LADDER_FIXTURES_FRESH_MS = 900_000

#: The fixed reference clock this query stands in for "tonight ending".
#: `backend/parlays.py`'s real tonight window is `end_of_desk_day_ms` --
#: `zoneinfo`, `America/Los_Angeles`, a 4am local rollover, DST-aware -- and
#: reproducing that here would need `backend.parlays` imported, which this
#: family never does. 22:00Z is a fixed stand-in Joe's evening slate is
#: normally still live at (~2-3pm Pacific depending on DST), chosen so the
#: reading lands inside the slate rather than after it, but it is NOT the
#: real boundary: a west-coast night game still building its consensus at
#: 22:00Z is invisible to this query even though it is inside `tonight`, and
#: a fixture whose ONLY fresh leg arrived after 22:00Z is missed entirely.
_LADDER_FIXTURES_CUTOFF_UTC_HOUR = 22

#: `--days` default, matching the ticket's "last 7 days".
_LADDER_FIXTURES_DEFAULT_DAYS = 7

#: A ceiling on `--days` independent of `--limit`: each day is its own
#: bounded index seek (cheap), but nothing stops a caller typing `--days
#: 5000` and turning a cheap query into 5000 of them. `--limit` bounds ROWS
#: RETURNED, not arms of the UNION built before the cap is ever applied, so
#: this is the guard that actually bounds the work done.
_LADDER_FIXTURES_MAX_DAYS = 60


def _ladder_fixture_days(now_ms: int, n_days: int) -> list[tuple[str, int, int]]:
    """`(budget_day, window_start_ms, cutoff_ms)` for the last `n_days` UTC
    calendar days, oldest first. `cutoff_ms` is exactly
    `_LADDER_FIXTURES_CUTOFF_UTC_HOUR`:00:00Z on that calendar date;
    `window_start_ms` is `_LADDER_FIXTURES_FRESH_MS` before it. The most
    recent day is `now_ms`'s own UTC calendar date, even if `now_ms` is
    before 22:00Z that day -- so a query run at noon includes a "today" row
    whose window is still in the future and will read 0 fixtures, which is
    correct: nothing can be fresh at an instant that has not happened yet.
    """
    today = datetime.fromtimestamp(now_ms / 1000, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    out: list[tuple[str, int, int]] = []
    for i in range(n_days - 1, -1, -1):
        day = today - timedelta(days=i)
        cutoff = day.replace(hour=_LADDER_FIXTURES_CUTOFF_UTC_HOUR)
        cutoff_ms = int(cutoff.timestamp() * 1000)
        out.append(
            (day.strftime("%Y-%m-%d"), cutoff_ms - _LADDER_FIXTURES_FRESH_MS, cutoff_ms)
        )
    return out


def _sql_ladder_fixtures(n_days: int) -> str:
    """One `SELECT` per day, `UNION ALL`ed, each independently bounded.

    **Deliberately NOT a `GROUP BY` over `fair_prices`.** A single query
    spanning all `n_days` on one wide `computed_ms` range (the shape
    `fair-prices-by-market` uses, classified `WALKS_THE_FILE`) would scan
    every row in a multi-day window. Each arm here instead seeks
    `idx_fair_market_computed(market, computed_ms DESC)` for a single ~15
    minute (`_LADDER_FIXTURES_FRESH_MS`) slice per market per day -- the same
    index `CANDIDATE_SQL`'s `computed_ms >= ?` arm relies on
    (`backend/store/schema.sql`) -- so the whole statement reads a bounded
    handful of rows regardless of how far `--since`/`--days` reaches back.
    Every caller-supplied value is a bound parameter; the market literals and
    day count are baked in at build time from constants, never from `args`.
    """
    arms = []
    for i in range(n_days):
        arms.append(
            f"SELECT :day{i}_label AS budget_day, :day{i}_cutoff AS cutoff_ms, "
            "COUNT(DISTINCT l.odds_event_id) AS fixtures "
            "FROM fair_prices f JOIN event_links l ON l.id = f.link_id "
            f"WHERE f.market IN ({_LADDER_FIXTURES_MARKETS_SQL}) "
            f"AND f.computed_ms >= :day{i}_start AND f.computed_ms <= :day{i}_cutoff"
        )
    return " UNION ALL ".join(arms) + " ORDER BY cutoff_ms"


def _q_ladder_fixtures(conn: sqlite3.Connection, args) -> list[Section]:
    """Distinct fixtures with a usable leg, one row per budget day, --days back.

    A "usable leg" here means: a `fair_prices` row on a TEAM market (`h2h`,
    `spreads`, `totals` -- see `_LADDER_FIXTURES_MARKETS`) whose `computed_ms`
    falls in the `_LADDER_FIXTURES_FRESH_MS` window immediately before a
    fixed `_LADDER_FIXTURES_CUTOFF_UTC_HOUR`:00Z instant that day. `fixtures`
    is `COUNT(DISTINCT odds_event_id)` -- so two legs on one game (a
    moneyline and a spread both fresh at the cutoff) count as **one**
    fixture, matching `_best_per_game`'s one-leg-per-game grouping in
    `backend/core/ladder.py`.

    What this approximates, and how
    --------------------------------
    - **"Fresh at 22:00Z that day"** stands in for `_fresh()`
      (`backend/core/ladder.py`), which compares a leg's LIVE age
      (`(now - computed_ms) + oldest_book_age_ms`) against the deployed
      `max_odds_age_ms`. This query instead checks only `computed_ms` against
      a fixed window ending at the cutoff -- it ignores `oldest_book_age_ms`,
      `confirmed_ms` (ADR 0133's re-confirmation stamp, which `CANDIDATE_SQL`
      also checks and this does not), and every suppression, gate, or
      `usable_legs`/`unusable_reason` rule downstream of the pool.
    - **22:00Z is a FIXED UTC hour, not `tonight`.** The real tonight window
      (`end_of_desk_day_ms`, `backend/parlays.py`) is the next 4am
      `America/Los_Angeles`, DST-aware and moving with `now`. This query
      cannot reproduce that without importing `backend`, which this family
      never does (module docstring). See `_LADDER_FIXTURES_CUTOFF_UTC_HOUR`
      for what that mismatch can hide or invent.
    - **Team markets only.** Prop markets are excluded --
      `_LADDER_FIXTURES_MARKETS`' comment says why -- so a slate carrying
      only prop-market legs for a fixture undercounts it as absent.
    - **No commence-time bound at all.** Unlike `_pool_for`, this does not
      check that the fixture's kickoff falls before the tonight horizon, or
      even that the game hasn't started. A fixture whose only fresh leg is
      for a game already in progress, or one kicking off next week, is
      counted the same as one actually reachable by a `tonight` card.
    - **No de-duplication beyond `odds_event_id`.** It does not check that
      the fixture is `combo_eligible`, that Kalshi would accept it in a
      combination, or that it survived `_best_per_game`'s tie-break --
      only that a fresh row existed for it.

    So a day's `fixtures` count is best read as a loose UPPER BOUND on how
    many fixtures a `tonight` ladder could have drawn from that evening, not
    the number the ladder actually built cards from.
    """
    requested_days = getattr(args, "days", None)
    n_days = min(
        max(1, requested_days or _LADDER_FIXTURES_DEFAULT_DAYS),
        _LADDER_FIXTURES_MAX_DAYS,
    )
    now_ms = int(time.time() * 1000)
    days = _ladder_fixture_days(now_ms, n_days)
    params: dict = {}
    for i, (label, window_start_ms, cutoff_ms) in enumerate(days):
        params[f"day{i}_label"] = label
        params[f"day{i}_start"] = window_start_ms
        params[f"day{i}_cutoff"] = cutoff_ms
    section = _fetch(
        conn,
        _sql_ladder_fixtures(n_days),
        params,
        title=(
            f"ladder-fixtures: distinct odds_event_id with a fresh team-"
            f"market leg at {_LADDER_FIXTURES_CUTOFF_UTC_HOUR}:00Z, last "
            f"{n_days} day(s) -- an approximation, see docstring"
        ),
        cap=args.limit,
        requested=n_days,
    )
    section = _derive_iso(section, "cutoff_ms", "cutoff_iso")
    return [section]


# ---------------------------------------------------------------------------
# scout-briefings: unattended convenings vs Joe's taps, by budget day (#125).
# ---------------------------------------------------------------------------
#
# **Lives here, not with the parlay desk, because this module was the lane's
# assignment** (#125's "Lane owns" names `inspect_live_db.py` and
# `inspect_live_db_parlays.py`, not a ninth domain module). The table it
# reads has nothing to do with combinations; see the query's own docstring,
# not this module's, for what it answers.
#
# `scout_briefings.trigger` (v51, `backend/store/schema.sql`) is 'tap' for
# Joe hitting the game screen and 'auto' for `backend/scout_watch.py`
# convening unattended on tonight's ladder (ADR 0180). Before this ticket,
# grep over `scripts/` found ZERO readers of the table at all -- `/api/scout`
# serves the last 50 rows but never selects `trigger`
# (`backend/api/routers/scout.py:325-330`), so no served surface could tell
# an unattended convening from a tapped one, which is the entire purpose of
# the column.
_SQL_SCOUT_BRIEFINGS_BY_DAY = (
    "SELECT strftime('%Y%m%d', (requested_ms - :offset_ms) / 1000, "
    "         'unixepoch') AS budget_day, "
    "       SUM(CASE WHEN trigger = 'auto' THEN 1 ELSE 0 END) AS auto_count, "
    "       SUM(CASE WHEN trigger = 'tap' THEN 1 ELSE 0 END) AS tap_count "
    "FROM scout_briefings WHERE requested_ms >= :since_ms "
    "GROUP BY budget_day ORDER BY budget_day DESC"
)

#: The status breakdown WITHIN each trigger, per budget day -- a separate
#: grain from section A on purpose. Collapsing this into A would mean either
#: a status-keyed column per trigger (six columns that grow the day a status
#: is added) or losing the split entirely; a narrow (day, trigger, status)
#: table stays correct as the status vocabulary changes and section A stays
#: the two-column read the ticket asked for.
_SQL_SCOUT_BRIEFINGS_STATUS = (
    "SELECT strftime('%Y%m%d', (requested_ms - :offset_ms) / 1000, "
    "         'unixepoch') AS budget_day, "
    "       trigger, status, COUNT(*) AS n "
    "FROM scout_briefings WHERE requested_ms >= :since_ms "
    "GROUP BY budget_day, trigger, status "
    "ORDER BY budget_day DESC, trigger, status"
)

#: `refusal_reason` verbatim, never parsed into a category -- the ticket's own
#: instruction. **This is NOT the ceiling that refuses a convening before it
#: starts** -- see `_q_scout_briefings`'s docstring for why that refusal
#: cannot reach this table at all; this section is only the narrower case
#: where a convening that had already started (and so already has a row) was
#: then marked refused from inside the run.
_SQL_SCOUT_BRIEFINGS_REFUSALS = (
    "SELECT strftime('%Y%m%d', (requested_ms - :offset_ms) / 1000, "
    "         'unixepoch') AS budget_day, "
    "       trigger, ticker, requested_ms, refusal_reason "
    "FROM scout_briefings "
    "WHERE refusal_reason IS NOT NULL AND requested_ms >= :since_ms "
    "ORDER BY requested_ms DESC"
)

#: `--days` default: the ticket does not name one, so this matches every
#: other budget-day query in the family (`credits-by-sport`,
#: `visit-freshness`).
_SCOUT_BRIEFINGS_DEFAULT_DAYS = 7

#: A ceiling on `--days` independent of `--limit`, same reasoning as
#: `_LADDER_FIXTURES_MAX_DAYS` just above: `--limit` bounds rows returned,
#: not how far back `WHERE requested_ms >= :since_ms` reaches, so this is the
#: guard that actually bounds the read. `scout_briefings` is a small table
#: (11 rows at 2026-09-21T17:55Z per the ticket's own count), so 60 days is
#: generous rather than tight.
_SCOUT_BRIEFINGS_MAX_DAYS = 60


def _q_scout_briefings(conn: sqlite3.Connection, args) -> list[Section]:
    """Unattended convenings vs Joe's taps, separated, per agent-budget day.

    Three sections, all keyed by budget day (`--day-start-hour`, default
    matches `configured_day_start_utc_hour()` -- the same variable
    `AgentBudget.day_start_ms` reads, so this grouping IS the agent budget
    day the ticket asks for, not a calendar day):

    A. `auto_count` and `tap_count` as two separate columns. **Never a total,
       never a ratio** -- the ticket is explicit that the two counts must stay
       apart, because collapsing them would erase the one distinction v51
       exists to draw.
    B. The `status` breakdown (`complete`/`partial`/`failed`/`refused`/
       `running`) within each (budget_day, trigger) pair.
    C. Every row carrying a `refusal_reason`, printed VERBATIM -- not parsed
       into a category, per the ticket.

    What this does not establish
    -----------------------------
    **`refusal_reason` (section C) cannot report the ceilings that refuse a
    convening before it starts, and this query does not imply that it does.**
    Checked against the writers, 2026-09-21:

    - `backend/scout_watch.py:152` (`SCOUT_AUTO_MAX_CONVENINGS_PER_DAY`) and
      `:167` (`AgentBudget.refusal_reason` -- calls/tokens/searches) both
      `logger.info(...)` and `return` BEFORE the `INSERT` at `:200`.
    - The tap path raises `HTTPException(429)` at
      `backend/api/routers/scout.py:277`, also before its `INSERT` at `:278`.
    - A row reaches `status = 'refused'` ONLY via
      `backend/agents/scout_desk.py:441` -> the `UPDATE` at
      `backend/api/routers/scout.py:189` -- i.e. only for a refusal that
      happens INSIDE a desk run that had already started and so already has a
      row to update.

    So the pre-flight refusal count is structurally ZERO in this table, on
    both triggers. **This query does not invent a proxy for it**: it does not
    count gaps in the day sequence, does not infer a refusal from a missing
    day, and does not emit a zero that could be read as "none were refused"
    for the pre-flight case -- an absent pre-flight refusal is unreadable
    here, not zero, and this docstring is where that stays written down
    rather than left to a reader's inference. Recording the pre-flight
    ceilings is #126's job (the unattended-spend path this ticket is
    forbidden from touching), not this query's.

    Also not established: **completeness.** A day with no rows in any
    section is a day nothing convened, on either trigger -- this query
    cannot tell that apart from a day the recorder itself was down, the same
    caveat `credits-day` states for `api_credits`.
    """
    requested_days = getattr(args, "days", None)
    n_days = min(
        max(1, requested_days or _SCOUT_BRIEFINGS_DEFAULT_DAYS),
        _SCOUT_BRIEFINGS_MAX_DAYS,
    )
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - n_days * _MS_PER_DAY
    params = {"offset_ms": args.day_start_hour * 3_600_000, "since_ms": since_ms}
    by_day = _fetch(
        conn,
        _SQL_SCOUT_BRIEFINGS_BY_DAY,
        params,
        title="A. auto_count and tap_count per budget day (never summed, "
              "never a ratio), newest day first",
        cap=args.limit,
    )
    status = _fetch(
        conn,
        _SQL_SCOUT_BRIEFINGS_STATUS,
        params,
        title="B. status breakdown within each (budget_day, trigger)",
        cap=args.limit,
    )
    refusals = _fetch(
        conn,
        _SQL_SCOUT_BRIEFINGS_REFUSALS,
        params,
        title="C. refusal_reason verbatim, where present -- does NOT cover "
              "a pre-flight refusal, see docstring",
        cap=args.limit,
    )
    refusals = _derive_iso(refusals, "requested_ms", "requested_iso")
    return [
        _window_section(
            f"scout-briefings window (budget day starts "
            f"{args.day_start_hour:02d}:00Z, last {n_days} day(s))",
            since_ms,
            None,
        ),
        by_day,
        status,
        refusals,
    ]


#: `scout_watch_log` gains at most a handful of rows a day by construction --
#: one per (budget day, outcome, detail), never one per 600-second cycle (ADR
#: 0056's shape, see `backend/store/scout_watch_log.py`). So the same generous
#: ceiling as `scout-briefings` above is still nowhere near a large read.
_SCOUT_WATCH_LOG_DEFAULT_DAYS = 7
_SCOUT_WATCH_LOG_MAX_DAYS = 60

#: Ordered `budget_day DESC, first_ms ASC` -- the day leads, and within a day
#: the FIRST thing that happened leads. That ordering is the answer to "which
#: ceiling bound first", which is the question this table exists for, so it is
#: not a display preference and must not be changed to `last_ms` or to
#: `cycle_count DESC` for readability.
_SQL_SCOUT_WATCH_LOG = """
SELECT
    strftime('%Y%m%d', (budget_day_ms + :offset_ms) / 1000, 'unixepoch')
        AS budget_day,
    outcome,
    cycle_count,
    first_ms,
    last_ms,
    detail
FROM scout_watch_log
WHERE budget_day_ms >= :since_ms
ORDER BY budget_day_ms DESC, first_ms ASC
"""


def _q_scout_watch_log(conn: sqlite3.Connection, args) -> list[Section]:
    """What the unattended scout watcher DECIDED, including deciding nothing.

    The other half of `scout-briefings`. That query reads the table of
    convenings that HAPPENED; this one reads the decisions that did not
    produce one -- which, before schema v53, were written nowhere at all.

    **This is the query that answers "which ceiling bound, and when".** Rows
    are ordered `budget_day DESC, first_ms ASC`, so within a day the first row
    is the first thing that happened. `cycle_count` separates a ceiling that
    bound once from one that bound every cycle until the day rolled -- the
    difference between a brake working and a brake stuck -- which a
    first-occurrence-only table could not express.

    `detail` is printed VERBATIM and is not parsed into a category here. For
    `refused_budget` it is `AgentBudget.refusal_reason`'s own sentence, naming
    the ceiling and both numbers; re-deriving which ceiling that was would be
    a second implementation of that ladder, which `backend/agents/budget.py`
    argues against for itself.

    What this does NOT establish
    ----------------------------
    - **Nothing before 2026-09-21.** The table was created by schema v53 and
      there is no backfill, because every earlier refusal went only to a log
      stream that drops lines. **An empty or short history here is missing
      instrumentation, not a quiet watcher**, and the two must not be read as
      the same thing.
    - **Nothing about spend.** `agent_calls` is the meter. `refused_budget`
      says a token or call or search ceiling refused; it does not say what any
      convening cost.
    - **Nothing about Joe's taps.** A tap refused over a ceiling raises 429 at
      `backend/api/routers/scout.py:277` and is deliberately not recorded --
      he saw that refusal on his own screen at the time. So a day with
      `refused_budget` rows here does NOT bound how often he was turned away.
    - **Nothing about completeness.** `record_watch_outcome` swallows its own
      write failures so it can never fail the decision it records, which means
      this table can undercount. It cannot overcount, and it cannot misname
      which ceiling bound.
    """
    requested_days = getattr(args, "days", None)
    n_days = min(
        max(1, requested_days or _SCOUT_WATCH_LOG_DEFAULT_DAYS),
        _SCOUT_WATCH_LOG_MAX_DAYS,
    )
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - n_days * _MS_PER_DAY
    rows = _fetch(
        conn,
        _SQL_SCOUT_WATCH_LOG,
        {"offset_ms": args.day_start_hour * 3_600_000, "since_ms": since_ms},
        title="Watch decisions per budget day, earliest-first within a day "
              "-- the first row of a day is what bound first",
        cap=args.limit,
    )
    rows = _derive_iso(rows, "first_ms", "first_iso")
    rows = _derive_iso(rows, "last_ms", "last_iso")
    return [
        _window_section(
            f"scout-watch-log window (budget day starts "
            f"{args.day_start_hour:02d}:00Z, last {n_days} day(s))",
            since_ms,
            None,
        ),
        rows,
    ]


# ---------------------------------------------------------------------------
# #137: which call crossed which AGENT_MAX_* ceiling, and when.
# ---------------------------------------------------------------------------
#
# **Why this is CHEAP, argued before the query exists.** `agent_calls`
# (`backend/store/schema.sql:1387`) carries `CREATE INDEX IF NOT EXISTS
# idx_agent_calls_time ON agent_calls(called_ms DESC)` (`schema.sql:1410`) --
# an index the ticket that opened this ticket believed did not exist; it does,
# and this argument rests on the schema as read, not on the ticket's premise.
# `WHERE called_ms >= :since_ms` is a bounded seek that walks that index from
# `:since_ms` forward, not a scan of the whole table: the index does not
# COVER the query (`agent`, `model`, `verdict`, `input_tokens`,
# `output_tokens`, `web_searches` all live off the index), so each matching
# row costs one rowid lookup beside the seek -- but the number of lookups is
# bounded by `--days` (`_AGENT_SPEND_MAX_DAYS` below), the same shape
# `credits-by-sport` and `ladder-fixtures` already argue CHEAP for a
# non-covering seek on a bounded window. The read's cost scales with the
# ANSWER (rows in the window) and not with the table's lifetime size --
# `tasks/lessons.md` 2026-09-18 ("a read's cost should scale with its
# ANSWER") is the rule this argument follows, and `db-sizes`'s `dbstat` walk
# is the shape this query is built to avoid. The window function that builds
# the running sums (`SUM(...) OVER w`) operates only on the rows the WHERE
# clause already admitted, so it adds no further scan.
_AGENT_SPEND_DEFAULT_DAYS = 7
_AGENT_SPEND_MAX_DAYS = 60

#: Ordered `budget_day DESC, called_ms ASC` -- the day leads, and within a day
#: calls are earliest-first so the running totals build up in the order they
#: actually happened. The window function's own `ORDER BY` (inside `w`) is
#: what makes each row's `*_running` column a true prefix sum; the outer
#: `ORDER BY` only controls display order and does not need to match it, but
#: here it does, deliberately, because the row where a ceiling first crossed
#: is easiest to spot when the display walks forward in time too.
_SQL_AGENT_SPEND = """
WITH days AS (
    SELECT
        id,
        called_ms,
        agent,
        model,
        verdict,
        input_tokens,
        output_tokens,
        web_searches,
        strftime('%Y%m%d', (called_ms - :offset_ms) / 1000, 'unixepoch')
            AS budget_day
    FROM agent_calls
    WHERE called_ms >= :since_ms
)
SELECT
    budget_day,
    called_ms,
    id,
    agent,
    model,
    verdict,
    input_tokens,
    output_tokens,
    web_searches,
    COUNT(*) OVER w AS calls_running,
    COALESCE(SUM(input_tokens) OVER w, 0)
        + COALESCE(SUM(output_tokens) OVER w, 0) AS tokens_running,
    COALESCE(SUM(web_searches) OVER w, 0) AS web_searches_running,
    SUM(
        CASE
            WHEN input_tokens IS NULL OR output_tokens IS NULL
                 OR web_searches IS NULL
            THEN 1 ELSE 0
        END
    ) OVER w AS unmetered_running
FROM days
WINDOW w AS (
    PARTITION BY budget_day
    ORDER BY called_ms ASC, id ASC
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY budget_day DESC, called_ms ASC, id ASC
"""


def _q_agent_spend(conn: sqlite3.Connection, args) -> list[Section]:
    """Cumulative token/call/search totals per budget day, one row per call.

    Written for #137: #118's reading of budget day `20260922` came back
    outcome D -- NOT SEPARABLE -- because the allowance refused from
    13:00:13Z and by T1 both the token ceiling (630,719 of 500,000) and the
    search ceiling (30 > 24) had already been crossed, but nothing committed
    said WHEN either crossed. This query is the instrument: it prints the
    running total at every call, in the same order the calls happened, so
    the row where a running total first reaches an `AGENT_MAX_*` ceiling is
    the answer -- read beside `scout-watch-log`'s `refused_allowance.first_ms`
    for the pass that saw it.

    Reproduces the exact arithmetic `backend/agents/budget.py:state` uses to
    gate a call, so a reading here means what the gate meant when it fired:
    `calls_running` is `COUNT(*)`, every call counts and none is ever
    unmetered; `tokens_running` is `COALESCE(SUM(input_tokens), 0) +
    COALESCE(SUM(output_tokens), 0)`; `web_searches_running` is
    `COALESCE(SUM(web_searches), 0)`.

    **A NULL `input_tokens`/`output_tokens`/`web_searches` row is unmetered,
    never 0.** `settle` writes all three together from one usage report
    (`backend/agents/budget.py:415-425`) or leaves all three NULL when the
    response never arrived -- a reserve with no settle, a network death, a
    crash. `SUM(...) OVER w` already skips a NULL rather than adding it as
    zero (that is what makes the running sum correct across an unmetered
    row), but a reader cannot tell "nothing was spent" from "spend here is
    unknown" from the sum alone -- so `unmetered_running` is printed on every
    row beside both sums: the cumulative count of calls in this budget day,
    up to and including this one, where any of the three columns is NULL. It
    checks all three with OR rather than trusting the invariant that they are
    always written together, so a row that somehow breaks that invariant
    still gets counted rather than silently trusted.

    What this does NOT establish
    ----------------------------
    - **Nothing about WHICH ceiling refused.** `refusal_reason` in
      `backend/agents/budget.py` decides that from the same three totals at
      call time; this query does not re-derive the decision, only the totals
      it was made from -- re-implementing the ladder here would be a second
      copy that could drift from the real one, the same reason
      `scout-watch-log` prints `detail` verbatim rather than parsing it.
    - **Nothing before whenever `agent_calls` itself starts.** There is no
      earlier record to backfill from; an empty or short history here is
      missing rows, not a quiet fleet.
    - **Nothing about Joe's own taps that were refused before an INSERT.**
      Same caveat `scout-watch-log` states: a pre-flight refusal never
      reaches this table's source table either.
    - **A reading taken with this instrument is a new look**, per
      `docs/measurements/2026-09-21-preregistration-unattended-scouting-
      first-reading.md` §5 ("Multiplicity and looks"), and needs its own
      successor registration before it can answer #127.
    """
    requested_days = getattr(args, "days", None)
    n_days = min(
        max(1, requested_days or _AGENT_SPEND_DEFAULT_DAYS),
        _AGENT_SPEND_MAX_DAYS,
    )
    # The window starts on a budget-day boundary, never mid-day: a running
    # sum over a day whose first hours were cut off is a partial total that
    # reads as the whole one. `called_ms - offset` (not `+`) labels a raw
    # call with the day it was charged to -- `scout-watch-log` adds the
    # offset because its column is already a day START, and this one is not.
    offset_ms = args.day_start_hour * 3_600_000
    now_ms = int(time.time() * 1000)
    today_start_ms = now_ms - ((now_ms - offset_ms) % _MS_PER_DAY)
    since_ms = today_start_ms - (n_days - 1) * _MS_PER_DAY
    rows = _fetch(
        conn,
        _SQL_AGENT_SPEND,
        {"offset_ms": offset_ms, "since_ms": since_ms},
        title="Running totals per call, earliest-first within a budget day "
              "-- the row where a *_running column first crosses an "
              "AGENT_MAX_* ceiling is when it bound",
        cap=args.limit,
    )
    rows = _derive_iso(rows, "called_ms", "called_iso")
    return [
        _window_section(
            f"agent-spend window (budget day starts "
            f"{args.day_start_hour:02d}:00Z, last {n_days} day(s))",
            since_ms,
            None,
        ),
        rows,
    ]


# ---------------------------------------------------------------------------
# Three bounded reads for the parlay desk (#286, town hall 2026-10-02).
# ---------------------------------------------------------------------------
#
# Each scans only the NEWEST `args.limit` rows of its table by an indexed
# order (primary key or `idx_combo_rfqs_time`), through a subquery, so the
# cost is the row cap and never the table. The window is printed beside the
# answer: a count over "the newest 2000 rows" and a count over "all rows" read
# the same and are not, so every result says how many rows it looked at.
#
# The venue's cap on simultaneously open RFQs. A copy of
# `backend.kalshi.rfq.MAX_OPEN_RFQS`, held by a test, because this family
# imports nothing from `backend`.
_VENUE_MAX_OPEN_RFQS = 100
# How `combo_rfqs.error_text` starts on a create whose outcome is unknown
# (#318). A copy of `backend.combo_rfq.UNKNOWN_CREATE_PREFIX`, held by a test.
_UNKNOWN_CREATE_PREFIX = "unknown: "

_SQL_GAME_SCRIPT_CARD_STAMPS = (
    "SELECT status, COUNT(*) AS cards, "
    "       SUM(combo_ticker IS NOT NULL) AS combo_stamped "
    "FROM (SELECT status, combo_ticker FROM game_script_cards "
    "      ORDER BY id DESC LIMIT ?) "
    "GROUP BY status ORDER BY status"
)
_SQL_GAME_SCRIPT_CARD_WINDOW = (
    "SELECT COUNT(*) AS rows_scanned, MIN(built_ms) AS oldest_built_ms, "
    "       MAX(built_ms) AS newest_built_ms "
    "FROM (SELECT built_ms FROM game_script_cards ORDER BY id DESC LIMIT ?)"
)


def _q_game_script_card_stamps(conn: sqlite3.Connection, args) -> list[Section]:
    """`game_script_cards` counted by `status`, beside how many carry a
    `combo_ticker`, over the newest `args.limit` rows.

    `combo_ticker` is stamped when Joe bets a card (`game_builder.py` UPDATEs
    it), so `built` against `combo_stamped` on the `built` row is built cards
    against cards he took. At most four rows (one per status).

    What this does not establish
    -----------------------------
    - **Not a take rate.** `combo_stamped` is a stamp on a row, not a fill: a
      stamped card may have been priced, asked about or abandoned, and a
      combination built from a card's legs by hand stamps nothing.
    - **Not the whole table when `rows_scanned` equals the cap.** The window
      is the newest rows by `id`; older cards are not counted, and the
      window's `oldest_built_ms` says how far back it reaches.
    - **No per-sport, per-game or per-day split, and no cost.** Spend is
      `agent-spend`'s.
    """
    stamps = _fetch(
        conn, _SQL_GAME_SCRIPT_CARD_STAMPS, (args.limit,),
        title="game_script_cards: status x combo_ticker stamped, newest window",
        cap=args.limit,
    )
    window = _fetch(
        conn, _SQL_GAME_SCRIPT_CARD_WINDOW, (args.limit,),
        title="game_script_cards: the window those counts cover",
        cap=args.limit,
    )
    window = _derive_iso(window, "oldest_built_ms", "oldest_built_iso")
    window = _derive_iso(window, "newest_built_ms", "newest_built_iso")
    return [stamps, window]


_SQL_GAME_SCRIPT_CARD_RECHECKS = (
    "SELECT status, COALESCE(recheck_status, '(NULL)') AS recheck_status, "
    "       COUNT(*) AS cards, "
    "       COALESCE(SUM(drop_if IS NOT NULL AND TRIM(drop_if) <> ''), 0) "
    "         AS with_drop_if, "
    "       COALESCE(SUM(combo_ticker IS NOT NULL), 0) AS combo_stamped "
    "FROM (SELECT status, recheck_status, drop_if, combo_ticker "
    "      FROM game_script_cards "
    "      WHERE kickoff_ms <= ? ORDER BY id DESC LIMIT ?) "
    "GROUP BY status, COALESCE(recheck_status, '(NULL)') "
    "ORDER BY status, recheck_status"
)


def _q_game_script_card_rechecks(conn: sqlite3.Connection, args) -> list[Section]:
    """`game_script_cards` whose kickoff has passed, counted by `status` x
    `recheck_status`, over the newest `args.limit` such rows by `id`.

    "Kickoff has passed" is `kickoff_ms <= now`, the card's own column
    (schema v59). A NULL `recheck_status` is its own group, labelled
    `(NULL)` (the column CHECK allows no such literal), never folded into
    another; `with_drop_if` counts the cards in each group carrying a
    non-empty `drop_if`, and `combo_stamped` the ones Joe minted
    (`combo_ticker` set) -- a re-check is owed on those, so a minted card in
    the `(NULL)` group is one the re-check never reached. Counts only, no
    ticker, no game.

    What this does not establish
    -----------------------------
    - **Not whether a re-check was owed.** The T-2h re-check runs only for a
      game Joe opened or minted (v62), so a NULL on a `built` card is "never
      re-checked", not necessarily a bug; this counts, it does not judge.
    - **`not_found` is not a confirmation** of the card, and `unknown` is the
      default for an unclear answer.
    - **Only the newest window of past-kickoff cards**; older ones are not
      counted. At most `status` x five groups out.
    """
    now_ms = int(time.time() * 1000)
    return [_fetch(
        conn, _SQL_GAME_SCRIPT_CARD_RECHECKS, (now_ms, args.limit),
        title="game_script_cards past kickoff: status x recheck_status "
        "(NULL named), newest window",
        cap=args.limit,
    )]


_SQL_GAME_SCRIPT_CARD_REFUSALS = (
    "SELECT status, reason, COUNT(*) AS cards, "
    "       MAX(built_ms) AS last_seen_ms "
    "FROM (SELECT status, reason, built_ms FROM game_script_cards "
    "      ORDER BY id DESC LIMIT ?) "
    "WHERE status IN ('refused_budget', 'refused_invalid') "
    "GROUP BY status, reason ORDER BY cards DESC, last_seen_ms DESC"
)


def _q_game_script_card_refusals(conn: sqlite3.Connection, args) -> list[Section]:
    """Refused `game_script_cards` by (status, reason) text, over the newest
    `args.limit` cards, top `-n` pairs by count.

    `reason` is `budget.refusal_reason()`'s or `validate_card()`'s own words
    (`backend/agents/game_script.py`), verbatim. A budget reason embeds the
    day's running counts, so those rows tend to be one group each; the
    invalid ones name the rule that refused the card.

    What this does not establish
    -----------------------------
    - **Not a rate, and not distinct games.** A refused card is retried on a
      later pass (the dedupe asks for `built`/`skipped` only), so one game
      can contribute many rows.
    - **Not what a refusal cost.** A `refused_invalid` card was refused after
      the model call; its spend is in `agent_calls`, not here.
    - **Only the newest window.**
    """
    top = _fetch(
        conn, _SQL_GAME_SCRIPT_CARD_REFUSALS, (args.limit,),
        title=f"game_script_cards: top {args.tail} refusal reasons by count",
        cap=min(args.tail, args.limit), requested=args.tail,
    )
    return [_derive_iso(top, "last_seen_ms", "last_seen_iso")]


_SQL_GAME_SCRIPT_LATEST_PROMPT = (
    "SELECT id, built_ms, status, sport_key, drop_if, reason "
    "FROM (SELECT * FROM game_script_cards ORDER BY id DESC LIMIT ?) "
    "WHERE prompt_version = (SELECT prompt_version FROM game_script_cards "
    "      WHERE prompt_version IS NOT NULL ORDER BY id DESC LIMIT 1) "
    "ORDER BY id DESC"
)


def _q_game_script_latest_prompt(conn: sqlite3.Connection, args) -> list[Section]:
    """The newest `-n` cards written under the newest `prompt_version`,
    within the newest `args.limit` cards: status, `drop_if` and `reason`
    verbatim (#310, reading prompt v4's first cards).

    `drop_if` is the seat's own sentence about the game -- no account data.

    What this does not establish
    -----------------------------
    - **Whether a `drop_if` is checkable.** That is a reader's judgement on
      the printed text; this prints it.
    - **Not a refusal rate.** A refused card is retried, so one game can
      contribute several rows; `game-script-card-refusals` groups reasons.
    - **Cards built while search was failing look the same as any other.**
      Read `agent-tool-errors` beside it.
    """
    rows = _fetch(
        conn, _SQL_GAME_SCRIPT_LATEST_PROMPT, (args.limit,),
        title=f"game_script_cards: newest {args.tail} under the newest prompt_version",
        cap=min(args.tail, args.limit), requested=args.tail,
    )
    return [_derive_iso(rows, "built_ms", "built_iso")]


_SQL_AGENT_TOOL_ERRORS = (
    "SELECT agent, tool_error_codes, COUNT(*) AS calls, "
    "       MAX(called_ms) AS last_seen_ms "
    "FROM (SELECT agent, tool_error_codes, called_ms FROM agent_calls "
    "      ORDER BY id DESC LIMIT ?) "
    "GROUP BY agent, tool_error_codes ORDER BY calls DESC, last_seen_ms DESC"
)


def _q_agent_tool_errors(conn: sqlite3.Connection, args) -> list[Section]:
    """`agent_calls` by (agent, tool_error_codes) over the newest
    `args.limit` calls, top `-n` pairs by count (#316, schema v64).

    `tool_error_codes` is a JSON object of `<block type>:<error_code>` ->
    count, verbatim: `{}` means the response was read and held no error
    block, NULL means no response arrived or the call predates v64. NULL is
    printed as its own group, never folded into `{}`.

    What this does not establish
    -----------------------------
    - **Not a rate.** Groups are calls, not searches or games; a call's row
      can carry several codes.
    - **Not a schema-mismatch's codes.** When the reply fails the output
      schema the SDK raises before returning the response, so those calls
      settle NULL here whatever their searches did.
    - **Only the newest window.**
    """
    top = _fetch(
        conn, _SQL_AGENT_TOOL_ERRORS, (args.limit,),
        title=f"agent_calls: top {args.tail} (agent, tool_error_codes) by count",
        cap=min(args.tail, args.limit), requested=args.tail,
    )
    return [_derive_iso(top, "last_seen_ms", "last_seen_iso")]


_SQL_PARLAY_LOOKUP_ERRORS = (
    "SELECT status, error, COUNT(*) AS lookups, "
    "       MAX(requested_ms) AS last_seen_ms "
    "FROM (SELECT status, error, requested_ms FROM parlay_lookups "
    "      ORDER BY id DESC LIMIT ?) "
    "WHERE error IS NOT NULL "
    "GROUP BY status, error ORDER BY lookups DESC, last_seen_ms DESC"
)
_SQL_PARLAY_LOOKUP_WINDOW = (
    "SELECT COUNT(*) AS rows_scanned, "
    "       COALESCE(SUM(error IS NOT NULL), 0) AS with_error, "
    "       MIN(requested_ms) AS oldest_requested_ms "
    "FROM (SELECT error, requested_ms FROM parlay_lookups "
    "      ORDER BY id DESC LIMIT ?)"
)


def _q_parlay_lookup_errors(conn: sqlite3.Connection, args) -> list[Section]:
    """`parlay_lookups.error` texts by count, newest `args.limit` lookups,
    top `-n` distinct (status, error) pairs by count.

    The `error` column holds the refusal's or the venue's own words, verbatim
    and never parsed into a category (`scout_watch_log.detail`'s rule); a
    message that embeds a ticker or a leg makes every row its own group.

    What this does not establish
    -----------------------------
    - **Not a rate.** `lookups` is a count in a window; the window's
      `rows_scanned` and `with_error` are printed so the share is checkable,
      and nothing here divides them.
    - **Not why.** An `error` is what was recorded, not a diagnosis, and a
      `refused` row is the desk stopping a tap before any venue call
      (schema v38), not a venue refusal.
    - **Only the newest window**, and only taps that wrote a row.
    """
    top = _fetch(
        conn, _SQL_PARLAY_LOOKUP_ERRORS, (args.limit,),
        title=f"parlay_lookups: top {args.tail} error texts by count",
        cap=min(args.tail, args.limit), requested=args.tail,
    )
    window = _fetch(
        conn, _SQL_PARLAY_LOOKUP_WINDOW, (args.limit,),
        title="parlay_lookups: the window those counts cover",
        cap=args.limit,
    )
    return [
        _derive_iso(top, "last_seen_ms", "last_seen_iso"),
        _derive_iso(window, "oldest_requested_ms", "oldest_requested_iso"),
    ]


_SQL_OWN_OPEN_RFQS = (
    "SELECT COUNT(*) AS rows_scanned, "
    "       COALESCE(SUM(is_open), 0) AS open_rows, "
    f"       {_VENUE_MAX_OPEN_RFQS} AS venue_cap, "
    f"       {_VENUE_MAX_OPEN_RFQS} - COALESCE(SUM(is_open), 0) AS headroom, "
    "       MIN(CASE WHEN is_open = 1 THEN requested_ms END) AS oldest_open_ms, "
    "       MAX(CASE WHEN is_open = 1 THEN requested_ms END) AS newest_open_ms, "
    "       COALESCE(SUM(is_unknown), 0) AS possibly_open "
    "FROM (SELECT requested_ms, "
    "             (deleted_ms IS NULL AND status != 'error') AS is_open, "
    "             (status = 'error' AND substr(error_text, 1, "
    f"{len(_UNKNOWN_CREATE_PREFIX)}) = '{_UNKNOWN_CREATE_PREFIX}') "
    "AS is_unknown "
    "      FROM combo_rfqs ORDER BY requested_ms DESC, id DESC LIMIT ?)"
)


def _q_own_open_rfqs(conn: sqlite3.Connection, args) -> list[Section]:
    """Our `combo_rfqs` rows never marked deleted, against the venue's cap of
    100 simultaneously open RFQs, over the newest `args.limit` rows.

    A row counts as open when `deleted_ms IS NULL` and `status != 'error'`
    (an `error` row is a failed create that never stood). One row out.

    `possibly_open` (#318) counts the `error` rows whose create outcome is
    UNKNOWN -- a timeout, 5xx or id-less 2xx, where Kalshi may hold a live
    RFQ of ours that we cannot name. Kept apart from `open_rows`, never
    added to it: whether any of them stood is exactly what is not known.

    What this does not establish
    -----------------------------
    - **Not what the venue holds.** This is the desk's own bookkeeping: an
      RFQ that expired or was withdrawn elsewhere keeps `deleted_ms` NULL
      here, so `open_rows` can overcount and `headroom` can understate. The
      venue's `GET /communications/rfqs?user_filter=self` is the only count of
      what is actually open, and nothing here calls it.
    - **Not RFQs made outside the desk**, or a second process's.
    - **Only the newest window**; `rows_scanned` equal to the cap means older
      rows were not looked at and could add open ones.
    """
    section = _fetch(
        conn, _SQL_OWN_OPEN_RFQS, (args.limit,),
        title="combo_rfqs: our rows not marked deleted vs the venue cap",
        cap=1,
    )
    section = _derive_iso(section, "oldest_open_ms", "oldest_open_iso")
    return [_derive_iso(section, "newest_open_ms", "newest_open_iso")]


# ---------------------------------------------------------------------------
# combo-markup: the makers' markup over the desk's fair, by leg count (#327).
# ---------------------------------------------------------------------------
#
# **Spec: `docs/measurements/2026-10-08-preregistration-combo-markup-by-leg-count.md`.**
# That file fixes the unit, the filters, the statistics, the cells, the floors
# and the looks; every constant below is copied from it and none was tuned.
# Where this module could not do what it says, the deviation is listed in the
# `combo_markup` docstring under "Deviations", not left implicit.
#
# **The one number this module prints that the registration calls a verdict
# is gated twice**: by the floor (an unmet floor prints no test, only counts)
# and by the registered cutoff (`--cutoff`, default Look A). It is NOT a
# running figure and must never be wired to a route, a push or a log line
# (registration section 6, "No running figure, anywhere").

#: Look A's cutoff, registration section 7. `--cutoff` overrides it for look B.
_CM_LOOK_A_CUTOFF = "2026-10-08T00:00:00Z"
_CM_FLOOR_ASKS = 20
_CM_FLOOR_DAYS = 10
_CM_FAIR_AGE_MS = 30 * 60 * 1000
_CM_ALPHA = 0.0125
_CM_BOOT_RESAMPLES = 10_000
_CM_BOOT_SEED = 20261008
_CM_BOOT_TAIL = 0.00125  # 99.75% two-sided
_CM_RECON_FLOOR = 0.80
_CM_REPRO_TOLERANCE = 0.05
_CM_PLANNING_SIGMA_R = 0.10
#: How far back a lookup is searched for (rule 7). Bounded so the read walks
#: `idx_parlay_lookups_time` over a day, never the table; `parlay_lookups` has
#: no index on `minted_market_ticker`. A lookup older than this counts as "not
#: found", which only matters to the no-age-limit variant (rule 8 is 30 min).
_CM_LOOKUP_LOOKBACK_MS = 24 * 3600 * 1000
#: How far back a `fair_prices` row may have been computed and still be "the
#: one in force". `computed_ms` freezes at first appearance (ADR 0133) and the
#: ladder scan has seen rows up to eight days before kickoff, so 9 days.
_CM_FAIR_LOOKBACK_MS = 9 * 24 * 3600 * 1000
_CM_LEG_LEVELS = (2, 3, 4, 5, 6)
_CM_BANDS = (
    (0, 100, "[0,100)"),
    (100, 250, "[100,250)"),
    (250, 500, "[250,500)"),
    (500, 1001, "[500,1000]"),
)
_CM_HOUR_MS = 3600 * 1000

#: A copy of the literal market list inside `_SQL_PARLAY_CANDIDATES` (which is
#: itself pinned to `backend.parlays.CANDIDATE_SQL`); a test pins this one to
#: that one. The ladder's `else` arm treats any unknown market as a moneyline,
#: so the as-of read must filter exactly as the live scan does.
_CM_POOL_MARKETS_SQL = (
    "('h2h', 'spreads', 'totals', 'pitcher_strikeouts', 'batter_total_bases', "
    "'batter_hits', 'batter_home_runs', 'batter_rbis', 'player_pass_yds', "
    "'player_reception_yds', 'player_rush_yds')"
)

_SQL_CM_ASKS = (
    "SELECT id, rfq_id, requested_ms, card_key, ticker, selected_legs, "
    "       target_cost_dollars, contracts_requested, fair_joint, "
    "       book_yes_ask_tenths, quote_count, refused_too_fine, status, purpose "
    "FROM combo_rfqs WHERE requested_ms < ? "
    "ORDER BY requested_ms DESC, id DESC"
)
_SQL_CM_QUOTES = (
    "SELECT yes_ask_tenths, captured_ms FROM combo_rfq_quotes WHERE rfq_id = ?"
)
_SQL_CM_LOOKUP = (
    "SELECT id, requested_ms, fair_joint_conservative FROM parlay_lookups "
    "WHERE minted_market_ticker = ? AND requested_ms <= ? AND requested_ms >= ? "
    "ORDER BY requested_ms DESC, id DESC LIMIT 1"
)
_SQL_CM_EVENT = (
    "SELECT e.commence_ms AS commence_ms, s.league AS league "
    "FROM kalshi_events e LEFT JOIN kalshi_series s "
    "ON s.series_ticker = e.series_ticker WHERE e.event_ticker = ?"
)
#: **The true start (registration amendment, 2026-10-08).** The odds fixture's
#: start reached through `event_links` (UNIQUE on kalshi_event_ticker,
#: odds_event_id) and `odds_fixtures` (PRIMARY KEY odds_event_id), MIN over
#: links. `kalshi_events.commence_ms` runs three hours late and is read only
#: to count how many asks change band, never as a start.
_SQL_CM_TRUE_START = (
    "SELECT MIN(f.commence_ms) AS commence_ms, COUNT(f.commence_ms) AS fixtures "
    "FROM event_links l LEFT JOIN odds_fixtures f "
    "ON f.odds_event_id = l.odds_event_id "
    "WHERE l.kalshi_event_ticker = ?"
)
_SQL_CM_LINKS = (
    "SELECT l.id AS link_id, l.kalshi_event_ticker AS kalshi_event_ticker, "
    "       l.odds_event_id AS odds_event_id, e.title AS event_title "
    "FROM event_links l JOIN kalshi_events e "
    "ON e.event_ticker = l.kalshi_event_ticker "
    "WHERE l.kalshi_event_ticker = ?"
)
_SQL_CM_SPORT = "SELECT sport_key FROM odds_snapshots WHERE odds_event_id = ? LIMIT 1"
_SQL_CM_MARKETS = (
    "SELECT ticker, title, yes_side_team, player_name, market_type, "
    "strike, status "
    "FROM kalshi_markets WHERE event_ticker = ? "
    "AND ("
    "  (market_type IN ('moneyline', 'spread', 'total') "
    "   AND yes_side_team IS NOT NULL)"
    "  OR (market_type = 'prop' AND player_name IS NOT NULL "
    "      AND strike IS NOT NULL)"
    ")"
)
#: **The as-of read.** The freshest row per identity that existed at the
#: lookup's `requested_ms`, keyed by link and bounded below by the lookback.
#: `INDEXED BY idx_fair_link` makes a planner that prefers
#: `idx_fair_market_computed` fail loudly instead of walking the market's
#: whole history; `tests/test_inspect_live_db_parlays.py` pins the plan, and
#: the `computed_ms <=` bound is what the pin goes red without.
_SQL_CM_FAIR_ASOF = (
    "SELECT computed_ms, market, outcome_name, outcome_point, "
    "       outcome_description, p_multiplicative, p_additive, p_power, p_shin, "
    "       p_conservative, oldest_book_age_ms, confirmed_ms, "
    "       confirmed_oldest_book_age_ms, link_id, market_width, book_count, "
    "       books_used, anchored_on_sharp "
    "FROM ("
    "  SELECT f.*, ROW_NUMBER() OVER ("
    "           PARTITION BY f.market, f.outcome_name, f.outcome_description, "
    "                        f.outcome_point "
    "           ORDER BY f.computed_ms DESC, f.id DESC) AS rn "
    "  FROM fair_prices f INDEXED BY idx_fair_link "
    "  WHERE f.link_id = ? AND f.computed_ms <= ? AND f.computed_ms > ? "
    f"   AND f.market IN {_CM_POOL_MARKETS_SQL}"
    ") WHERE rn = 1"
)


# --- pure helpers: time, quantiles, OLS, t ----------------------------------


def _cm_nth_sunday(year: int, month: int, n: int) -> int:
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    return 1 + (6 - first.weekday()) % 7 + 7 * (n - 1)


def _cm_eastern_day(ms: int) -> str:
    """The US Eastern calendar day of an instant, with the US DST rule
    (second Sunday of March 02:00 local to first Sunday of November 02:00
    local) applied by hand: `zoneinfo` needs a tz database the box may lack.
    """
    utc = datetime.fromtimestamp(ms / 1000, timezone.utc)
    start = datetime(
        utc.year, 3, _cm_nth_sunday(utc.year, 3, 2), 7, tzinfo=timezone.utc
    )
    end = datetime(
        utc.year, 11, _cm_nth_sunday(utc.year, 11, 1), 6, tzinfo=timezone.utc
    )
    offset = timedelta(hours=-4 if start <= utc < end else -5)
    return (utc + offset).date().isoformat()


def _cm_q(values: list[float], q: float) -> Optional[float]:
    """Linear-interpolation quantile (inclusive, type 7). None on empty."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _cm_median(values: list[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _cm_round(x: Optional[float], nd: int = 4) -> Optional[float]:
    return None if x is None else round(x, nd)


def _cm_betacf(a: float, b: float, x: float) -> float:
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def _cm_betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _cm_betacf(a, b, x) / a
    return 1.0 - front * _cm_betacf(b, a, 1.0 - x) / b


def _cm_t_cdf(t: float, df: float) -> float:
    x = df / (df + t * t)
    tail = 0.5 * _cm_betainc(df / 2.0, 0.5, x)
    return 1.0 - tail if t > 0 else tail


def _cm_t_crit(g_days: int, alpha: float = _CM_ALPHA) -> Optional[float]:
    """One-sided upper `alpha` quantile of t on `G - 1` df (None if G < 2)."""
    if g_days < 2:
        return None
    df = g_days - 1
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if 1.0 - _cm_t_cdf(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _cm_invert(m: list[list[float]]) -> Optional[list[list[float]]]:
    k = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(k)] for i, row in enumerate(m)]
    for col in range(k):
        piv = max(range(col, k), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None
        a[col], a[piv] = a[piv], a[col]
        p = a[col][col]
        a[col] = [v / p for v in a[col]]
        for r in range(k):
            if r != col:
                f = a[r][col]
                a[r] = [v - f * w for v, w in zip(a[r], a[col])]
    return [row[k:] for row in a]


def _cm_ols_cr1(xs: list[list[float]], ys: list[float], clusters: list[str]):
    """OLS with the CR1 cluster-robust covariance.

    Returns `(beta, se, G, n)`; `se` is None when fewer than two clusters or
    `n <= k` (the small-sample factor is undefined), `beta` is None when the
    design is singular. CR1 = G/(G-1) * (n-1)/(n-k) * (X'X)^-1 M (X'X)^-1,
    M the sum over clusters of (X_g'u_g)(X_g'u_g)'.
    """
    n, k = len(ys), len(xs[0]) if xs else 0
    g_days = len(set(clusters))
    if n == 0:
        return None, None, g_days, n
    xtx = [[sum(x[a] * x[b] for x in xs) for b in range(k)] for a in range(k)]
    inv = _cm_invert(xtx)
    if inv is None:
        return None, None, g_days, n
    xty = [sum(x[a] * y for x, y in zip(xs, ys)) for a in range(k)]
    beta = [sum(inv[a][b] * xty[b] for b in range(k)) for a in range(k)]
    if g_days < 2 or n <= k:
        return beta, None, g_days, n
    scores: dict[str, list[float]] = {}
    for x, y, c in zip(xs, ys, clusters):
        u = y - sum(beta[a] * x[a] for a in range(k))
        s = scores.setdefault(c, [0.0] * k)
        for a in range(k):
            s[a] += x[a] * u
    meat = [[sum(s[a] * s[b] for s in scores.values()) for b in range(k)] for a in range(k)]
    scale = (g_days / (g_days - 1.0)) * ((n - 1.0) / (n - k))
    # V = scale * inv * meat * inv
    tmp = [[sum(inv[a][c] * meat[c][b] for c in range(k)) for b in range(k)] for a in range(k)]
    se = []
    for a in range(k):
        v = scale * sum(tmp[a][c] * inv[c][a] for c in range(k))
        se.append(math.sqrt(v) if v > 0 else None)
    return beta, se, g_days, n


# --- the per-ask record -----------------------------------------------------


@dataclass
class _CmAsk:
    ask_id: int
    requested_ms: int
    day: str
    ticker: str
    card_key: Optional[str]
    legs: int
    b: Optional[int] = None
    fair: Optional[float] = None
    f_tenths: Optional[float] = None
    r_f: Optional[float] = None
    pct_f: Optional[float] = None
    tenths_markup: Optional[float] = None
    band: Optional[str] = None
    quotes_asks: list = field(default_factory=list)
    single_read: bool = True
    lookup_ms: Optional[int] = None
    prov_ok: bool = False
    age_ok: bool = False
    g_tenths: Optional[float] = None
    r_g: Optional[float] = None
    pct_g: Optional[float] = None
    recon_reason: Optional[str] = None
    hours_to_first: Optional[float] = None
    first_unknown: bool = True
    kalshi_clock_hours: Optional[float] = None
    size_cut: str = "size unknown"
    leagues: Optional[tuple] = None
    refused_too_fine: Optional[int] = None
    book_ask: Optional[int] = None


def _cm_band(b: int) -> Optional[str]:
    for lo, hi, label in _CM_BANDS:
        if lo <= b < hi:
            return label
    return None


def _cm_leg_count(selected_legs: str) -> Optional[int]:
    try:
        legs = json.loads(selected_legs)
    except (TypeError, ValueError):
        return None
    return len(legs) if isinstance(legs, list) else None


def _cm_level(legs: int) -> int:
    return min(legs, 6)


def _cm_size_cut(target: Optional[str], contracts: Optional[int]) -> str:
    if contracts is not None:
        return "sized by contracts_requested"
    try:
        d = float(target) if target is not None else None
    except ValueError:
        d = None
    if d is None:
        return "size unknown"
    if d <= 1:
        return "up to $1"
    if d <= 5:
        return "over $1 to $5"
    if d <= 20:
        return "over $5 to $20"
    return "over $20"


def _cm_hours_cut(hours: Optional[float], unknown: bool) -> str:
    if unknown or hours is None:
        return "unknown"
    if hours < 0:
        return "already started"
    if hours < 2:
        return "[0,2h)"
    if hours < 6:
        return "[2h,6h)"
    if hours < 24:
        return "[6h,24h)"
    return "24h or more"


# --- the generous fair g: rebuilt through the ladder's own mapping ----------


def _cm_load_ladder():
    """`backend.parlays` and `backend.core.ladder`, or `(None, reason)`.

    Imported lazily and only here. The family imports nothing from `backend`
    at module load (`python /app/scripts/...` does not put `/app` on the
    path), so this adds the repo root to the path for the one call that needs
    the ladder's own leg-to-row mapping (registration section 4: "reuse the
    ladder's own mapping ... not write a second one").
    """
    try:
        try:
            from backend import parlays as parlays_mod
        except ImportError:
            root = str(Path(__file__).resolve().parent.parent)
            if root not in sys.path:
                sys.path.insert(0, root)
            from backend import parlays as parlays_mod
        return parlays_mod, None
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        return None, f"{type(exc).__name__}: {exc}"


class _CmReconstructor:
    """Rebuilds `g` for one ask: every leg at its most generous devig method."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.parlays, self.unavailable = _cm_load_ladder()
        self._links: dict[str, Any] = {}
        self._markets: dict[str, list] = {}
        self.fair_reads = 0

    def _link(self, event_ticker: str):
        if event_ticker not in self._links:
            row = self.conn.execute(_SQL_CM_LINKS, (event_ticker,)).fetchone()
            sport = None
            if row is not None:
                s = self.conn.execute(_SQL_CM_SPORT, (row[2],)).fetchone()
                sport = s[0] if s else None
            self._links[event_ticker] = (row, sport)
        return self._links[event_ticker]

    def reconstruct(self, legs: list[dict], asof_ms: int, f_prob: float):
        """`(g_prob, None)` or `(None, reason)`."""
        if self.parlays is None:
            return None, "ladder_unavailable"
        freshest: dict = {}
        events: list[str] = []
        for leg in legs:
            et = leg.get("event_ticker") if isinstance(leg, dict) else None
            if not et:
                return None, "leg_unreadable"
            if et not in events:
                events.append(et)
        for et in events:
            link, sport = self._link(et)
            if link is None:
                return None, "no_event_link"
            if et not in self._markets:
                self._markets[et] = self.conn.execute(
                    _SQL_CM_MARKETS, (et,)
                ).fetchall()
            self.fair_reads += 1
            for r in self.conn.execute(
                _SQL_CM_FAIR_ASOF,
                (link[0], asof_ms, asof_ms - _CM_FAIR_LOOKBACK_MS),
            ).fetchall():
                row = {
                    "computed_ms": r[0], "market": r[1], "outcome_name": r[2],
                    "outcome_point": r[3], "outcome_description": r[4],
                    "p_multiplicative": r[5], "p_additive": r[6],
                    "p_power": r[7], "p_shin": r[8], "p_conservative": r[9],
                    "oldest_book_age_ms": r[10], "confirmed_ms": r[11],
                    "confirmed_oldest_book_age_ms": r[12], "link_id": r[13],
                    "market_width": r[14], "book_count": r[15],
                    "books_used": r[16], "anchored_on_sharp": r[17],
                    "kalshi_event_ticker": link[1], "odds_event_id": link[2],
                    "event_title": link[3], "commence_ms": None,
                    "home_team": None, "away_team": None, "sport_key": sport,
                }
                key = (r[13], r[1], r[2], r[4], r[3])
                freshest.setdefault(key, row)
        outcomes_by_link: dict[int, list[str]] = {}
        for (link_id, market, outcome, _d, _p), _row in freshest.items():
            if market in ("h2h", "spreads"):
                if outcome not in outcomes_by_link.setdefault(link_id, []):
                    outcomes_by_link[link_id].append(outcome)
        pool = self.parlays.CandidatePool(
            freshest=freshest,
            outcomes_by_link=outcomes_by_link,
            markets_by_event={et: self._markets[et] for et in events},
            eligible_events=None,
            now_ms=asof_ms,
            max_odds_age_ms=None,
        )
        cands, _excluded = self.parlays.ladder_candidates(
            self.conn, now_ms=asof_ms, max_odds_age_ms=None, horizon="48h",
            pool=pool,
        )
        by_key = {
            (c.kalshi_event_ticker, c.kalshi_market_ticker, c.side): c
            for c in cands
        }
        prod_lo, prod_ratio = 1.0, 1.0
        for leg in legs:
            side = leg.get("side") or "yes"
            c = by_key.get(
                (leg.get("event_ticker"), leg.get("market_ticker"), side)
            )
            if c is None:
                return None, "leg_has_no_fair_row"
            hi = [v for v in c.p_by_method.values() if v is not None]
            if not hi or not c.p_conservative or c.p_conservative <= 0:
                return None, "no_method_columns"
            prod_lo *= c.p_conservative
            prod_ratio *= max(hi) / c.p_conservative
        if f_prob <= 0 or prod_lo <= 0:
            return None, "reproduction_failed"
        if abs(math.log(prod_lo / f_prob)) > _CM_REPRO_TOLERANCE:
            return None, "reproduction_failed"
        return f_prob * prod_ratio, None


# --- collection: DB rows to asks and counts ---------------------------------


@dataclass
class _CmCollected:
    scanned: int = 0
    truncated: bool = False
    status_by_level: dict = field(default_factory=dict)
    fair_null_by_card: dict = field(default_factory=dict)
    asks: list = field(default_factory=list)  # passes 1-5 + extras, any flags
    disp_asks: list = field(default_factory=list)  # (level|None, has_fair, [asks])
    quotes_read: int = 0
    lookups_read: int = 0
    recon_unavailable: Optional[str] = None
    multi_ticker_asks: int = 0
    multi_ticker_tickers: int = 0
    fair_reads: int = 0
    funnel_after_6: int = 0
    final: list = field(default_factory=list)
    everyone: list = field(default_factory=list)
    removed: dict = field(default_factory=dict)


def _cm_parse_cutoff(value: Optional[str]) -> int:
    text = value or _CM_LOOK_A_CUTOFF
    if text.isdigit():
        return int(text)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"--cutoff {text!r} is neither epoch milliseconds nor ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _cm_collect(conn: sqlite3.Connection, args, cutoff_ms: int) -> _CmCollected:
    out = _CmCollected()
    section = _fetch(
        conn, _SQL_CM_ASKS, (cutoff_ms,),
        title="asks", cap=args.limit, requested=args.limit,
    )
    rows = section.rows
    out.scanned = len(rows)
    out.truncated = section.truncated

    removed = {k: 0 for k in (
        "2 purpose", "3 status", "4 fair NULL", "5 fair outside (0,1)",
        "6 single-read", "7 provenance", "8 fair age",
        "9 no best ask / not positive", "10 legs unreadable or fewer than 2",
    )}
    for row in rows:
        (ask_id, rfq_id, req_ms, card_key, ticker, legs_json, target, contracts,
         fair, book_ask, _qc, refused, status, purpose) = row
        n_legs = _cm_leg_count(legs_json)
        lvl = "unreadable" if n_legs is None else _cm_level(n_legs)
        if purpose not in (None, "buy"):
            removed["2 purpose"] += 1
            continue
        if status != "quoted":
            removed["3 status"] += 1
            d = out.status_by_level.setdefault(status, {})
            d[lvl] = d.get(lvl, 0) + 1
            continue
        d = out.status_by_level.setdefault("quoted", {})
        d[lvl] = d.get(lvl, 0) + 1
        qrows = conn.execute(_SQL_CM_QUOTES, (rfq_id,)).fetchall()
        out.quotes_read += len(qrows)
        single = all(q[1] == req_ms for q in qrows)
        asks_q = [q[0] for q in qrows if q[0] is not None]
        has_fair = fair is not None
        out.disp_asks.append((
            None if n_legs is None else n_legs, has_fair, single, asks_q,
        ))
        ask = _CmAsk(
            ask_id=ask_id, requested_ms=req_ms, day=_cm_eastern_day(req_ms),
            ticker=ticker, card_key=card_key,
            legs=n_legs if n_legs is not None else -1,
            quotes_asks=asks_q, single_read=single,
            refused_too_fine=refused, book_ask=book_ask,
            size_cut=_cm_size_cut(target, contracts),
        )
        ask.fair = fair
        if not has_fair:
            removed["4 fair NULL"] += 1
            k = card_key if card_key is not None else "NULL"
            out.fair_null_by_card[k] = out.fair_null_by_card.get(k, 0) + 1
            continue
        if not (0 < fair < 1):
            removed["5 fair outside (0,1)"] += 1
            continue
        ask.f_tenths = fair * 1000.0
        out.asks.append((ask, legs_json))

    # Rules 6-8 and the extras are applied to the survivors of 1-5, in order,
    # but their FLAGS are all kept so the registered variants (rule 6 put
    # back, no age limit) read the same rows.
    recon = _CmReconstructor(conn)
    out.recon_unavailable = recon.unavailable
    survivors: list = []
    for ask, legs_json in out.asks:
        lk = conn.execute(
            _SQL_CM_LOOKUP,
            (ask.ticker, ask.requested_ms, ask.requested_ms - _CM_LOOKUP_LOOKBACK_MS),
        ).fetchone()
        out.lookups_read += 1
        if lk is not None:
            ask.lookup_ms = lk[1]
            ask.prov_ok = (
                lk[2] is not None and abs(lk[2] - ask.fair) < 1e-12
            )
            ask.age_ok = (ask.requested_ms - lk[1]) <= _CM_FAIR_AGE_MS
        if not ask.single_read:
            removed["6 single-read"] += 1
            continue
        survivors.append((ask, legs_json))
    out.funnel_after_6 = len(survivors)
    kept: list = []
    for ask, legs_json in survivors:
        if not ask.prov_ok:
            removed["7 provenance"] += 1
            continue
        if not ask.age_ok:
            removed["8 fair age"] += 1
            continue
        kept.append((ask, legs_json))

    final: list = []
    for ask, legs_json in kept:
        if not ask.quotes_asks or min(ask.quotes_asks) <= 0:
            removed["9 no best ask / not positive"] += 1
            continue
        if ask.legs < 2:
            removed["10 legs unreadable or fewer than 2"] += 1
            continue
        final.append(ask)

    # Fill the derived fields for EVERY ask that passed 1-5 and has a legs
    # count and a best ask, so the variants can reuse them; mark the primary.
    everyone = []
    for ask, legs_json in out.asks:
        if not ask.quotes_asks or min(ask.quotes_asks) <= 0 or ask.legs < 2:
            continue
        ask.b = min(ask.quotes_asks)
        ask.r_f = math.log(ask.b / ask.f_tenths)
        ask.pct_f = 100.0 * (ask.b - ask.f_tenths) / ask.f_tenths
        ask.tenths_markup = ask.b - ask.f_tenths
        ask.band = _cm_band(ask.b)
        everyone.append((ask, legs_json))
    # Secondary facts (event commence, league) and g, per ask.
    for ask, legs_json in everyone:
        legs = json.loads(legs_json)
        commences, leagues, unknown = [], [], False
        kalshi_clock, kalshi_clock_unknown = [], False
        for leg in legs:
            ev = conn.execute(
                _SQL_CM_EVENT, (leg.get("event_ticker") if isinstance(leg, dict) else None,)
            ).fetchone()
            ts = conn.execute(
                _SQL_CM_TRUE_START,
                (leg.get("event_ticker") if isinstance(leg, dict) else None,),
            ).fetchone()
            if ts is None or ts[0] is None or not ts[1]:
                unknown = True  # any unlinked leg: unknown, never guessed
            else:
                commences.append(ts[0])
            if ev is not None and ev[0] is not None:
                kalshi_clock.append(ev[0])
            else:
                kalshi_clock_unknown = True
            leagues.append(ev[1] if ev is not None else None)
        ask.first_unknown = unknown or not commences
        if not ask.first_unknown:
            ask.hours_to_first = (min(commences) - ask.requested_ms) / _CM_HOUR_MS
        if kalshi_clock and not kalshi_clock_unknown:
            ask.kalshi_clock_hours = (
                (min(kalshi_clock) - ask.requested_ms) / _CM_HOUR_MS
            )
        ask.leagues = tuple(sorted({l for l in leagues if l is not None})) if all(
            l is not None for l in leagues
        ) else None
        if ask.lookup_ms is None:
            ask.recon_reason = "no_lookup"
            continue
        g_prob, why = recon.reconstruct(legs, ask.lookup_ms, ask.fair)
        if g_prob is None:
            ask.recon_reason = why
        else:
            ask.g_tenths = g_prob * 1000.0
            ask.r_g = math.log(ask.b / ask.g_tenths)
            ask.pct_g = 100.0 * (ask.b - ask.g_tenths) / ask.g_tenths
    out.fair_reads = recon.fair_reads
    out.final = final
    out.everyone = [a for a, _ in everyone]
    out.removed = removed
    counts: dict[str, int] = {}
    for a in final:
        counts[a.ticker] = counts.get(a.ticker, 0) + 1
    out.multi_ticker_tickers = sum(1 for c in counts.values() if c > 1)
    out.multi_ticker_asks = sum(c for c in counts.values() if c > 1)
    return out


# --- analysis ---------------------------------------------------------------


def _cm_days(asks) -> int:
    return len({a.day for a in asks})


def _cm_floor(asks) -> bool:
    return len(asks) >= _CM_FLOOR_ASKS and _cm_days(asks) >= _CM_FLOOR_DAYS


def _cm_largest_day(asks) -> tuple[Optional[str], Optional[float]]:
    if not asks:
        return None, None
    counts: dict[str, int] = {}
    for a in asks:
        counts[a.day] = counts.get(a.day, 0) + 1
    day = max(sorted(counts), key=lambda d: counts[d])
    return day, counts[day] / len(asks)


def _cm_fit(asks, use_g: bool, p2: bool = False):
    """`(coef, se, G, n)` of the coefficient of interest.

    P1: `r ~ 1 + L`, coefficient of interest `L`. P2: `r ~ 1 + under6 + L`,
    coefficient of interest the indicator.
    """
    sel = [a for a in asks if (a.r_g if use_g else a.r_f) is not None]
    if p2:
        xs = [[1.0, 1.0 if a.hours_to_first < 6 else 0.0, float(_cm_level(a.legs))]
              for a in sel]
    else:
        xs = [[1.0, float(_cm_level(a.legs))] for a in sel]
    ys = [a.r_g if use_g else a.r_f for a in sel]
    beta, se, g_days, n = _cm_ols_cr1(xs, ys, [a.day for a in sel])
    idx = 1
    if beta is None:
        return None, None, g_days, n
    return beta[idx], (se[idx] if se else None), g_days, n


def _cm_slope_point(asks, use_g: bool) -> Optional[float]:
    sel = [a for a in asks if (a.r_g if use_g else a.r_f) is not None]
    if len({_cm_level(a.legs) for a in sel}) < 2:
        return None
    beta, _se, _g, _n = _cm_ols_cr1(
        [[1.0, float(_cm_level(a.legs))] for a in sel],
        [a.r_g if use_g else a.r_f for a in sel],
        [a.day for a in sel],
    )
    return None if beta is None else beta[1]


def _cm_boot_interval(asks, attr: str) -> tuple[Optional[float], Optional[float]]:
    """Day-cluster bootstrap of the median of `attr`: 10,000 resamples, seed
    20261008, 99.75% percentile interval. Not a test."""
    by_day: dict[str, list[float]] = {}
    for a in asks:
        v = getattr(a, attr)
        if v is not None:
            by_day.setdefault(a.day, []).append(v)
    days = sorted(by_day)
    if len(days) < 2:
        return None, None
    rng = random.Random(_CM_BOOT_SEED)
    meds = []
    for _ in range(_CM_BOOT_RESAMPLES):
        pool: list[float] = []
        for d in rng.choices(days, k=len(days)):
            pool.extend(by_day[d])
        meds.append(statistics.median(pool))
    meds.sort()
    return _cm_q(meds, _CM_BOOT_TAIL), _cm_q(meds, 1.0 - _CM_BOOT_TAIL)


def _cm_describe(label_cols: tuple, asks, *, interval: bool) -> tuple:
    f_vals = [a.pct_f for a in asks]
    g_asks = [a for a in asks if a.pct_g is not None]
    g_vals = [a.pct_g for a in g_asks]
    row = label_cols + (
        len(asks), _cm_days(asks),
        _cm_round(_cm_median([a.tenths_markup for a in asks]), 2),
        _cm_round(_cm_median(f_vals), 2),
        _cm_round(_cm_q(f_vals, 0.25), 2), _cm_round(_cm_q(f_vals, 0.75), 2),
        len(g_asks),
        _cm_round(_cm_median(g_vals), 2),
        _cm_round(_cm_q(g_vals, 0.25), 2), _cm_round(_cm_q(g_vals, 0.75), 2),
    )
    if interval:
        if _cm_floor(asks):
            lo, hi = _cm_boot_interval(asks, "pct_f")
            row += (_cm_round(lo, 2), _cm_round(hi, 2))
        else:
            row += ("below floor", "below floor")
        if _cm_floor(g_asks):
            lo, hi = _cm_boot_interval(g_asks, "pct_g")
            row += (_cm_round(lo, 2), _cm_round(hi, 2))
        else:
            row += ("below floor", "below floor")
    return row


_CM_DESC_COLS = (
    "n", "days", "median_markup_tenths", "median_pct_f", "q1_pct_f",
    "q3_pct_f", "n_g", "median_pct_g", "q1_pct_g", "q3_pct_g",
)
_CM_INT_COLS = ("ci_lo_pct_f", "ci_hi_pct_f", "ci_lo_pct_g", "ci_hi_pct_g")


def _cm_p1_outcome(bc, bg, drop_day_bg, refused0_bg, t_c, recon_ok):
    """The registered P1 outcome word, checked in the registered order.

    `bc`/`bg` are `(coef, se)`; the `*_bg` points are coefficients only.
    """
    def t_of(fit):
        coef, se = fit
        return None if coef is None or not se else coef / se

    tc = t_of(bc)
    tg = t_of(bg) if recon_ok else None
    if tc is not None and tc >= t_c:
        if (tg is not None and tg >= t_c
                and drop_day_bg is not None and drop_day_bg > 0
                and refused0_bg is not None and refused0_bg > 0):
            return "MAKERS CHARGE MORE PER LEG"
        return "GROWTH NOT SEPARATED FROM THE DESK'S OWN FAIR"
    if tc is not None and tc <= -t_c:
        return "REVERSED"
    return "UNRESOLVED"


def _cm_p2_outcome(kc, kg, drop_day_kg, t_c, recon_ok):
    def t_of(fit):
        coef, se = fit
        return None if coef is None or not se else coef / se

    tc = t_of(kc)
    tg = t_of(kg) if recon_ok else None
    if tc is None or tg is None:
        return "UNRESOLVED"
    if tc <= -t_c and tg <= -t_c and drop_day_kg is not None and drop_day_kg < 0:
        return "TIGHTER INSIDE 6 HOURS"
    if tc >= t_c and tg >= t_c and drop_day_kg is not None and drop_day_kg > 0:
        return "WIDER INSIDE 6 HOURS"
    return "UNRESOLVED"


def _cm_sections(col: _CmCollected, cutoff_ms: int, args) -> list[Section]:
    sections: list[Section] = []
    pop = col.final
    {a.ask_id for a in pop}

    sections.append(Section(
        title="combo-markup: window (registration: 2026-10-08-preregistration-"
              "combo-markup-by-leg-count.md)",
        columns=("cutoff_ms", "cutoff_iso", "asks_scanned", "limit",
                 "truncated_at_limit", "quote_rows_read", "lookup_reads",
                 "fair_as_of_reads", "ladder_import"),
        rows=[(cutoff_ms, _iso(cutoff_ms), col.scanned, args.limit,
               col.truncated, col.quotes_read, col.lookups_read,
               col.fair_reads, col.recon_unavailable or "ok")],
    ))

    remaining = col.scanned
    rows = [("1 requested_ms before cutoff", 0, remaining)]
    removed = col.removed
    for key in ("2 purpose", "3 status", "4 fair NULL", "5 fair outside (0,1)",
                "6 single-read", "7 provenance", "8 fair age",
                "9 no best ask / not positive",
                "10 legs unreadable or fewer than 2"):
        remaining -= removed[key]
        rows.append((key, removed[key], remaining))
    sections.append(Section(
        title="Exclusion funnel (registration section 2 order; steps 9-10 are "
              "guards the registration does not name -- see Deviations)",
        columns=("step", "removed", "remaining"), rows=rows,
    ))

    lv = lambda k: str(k)  # noqa: E731
    status_rows = []
    for status in sorted(col.status_by_level):
        d = col.status_by_level[status]
        for lvl in sorted(d, key=lv):
            status_rows.append((status, lvl, d[lvl]))
    sections.append(Section(
        title="Status of buy-side asks, by leg count (6 = 6+): counts, not rates",
        columns=("status", "leg_count", "asks"), rows=status_rows,
    ))
    sections.append(Section(
        title="Quoted asks with fair_joint NULL, by card_key (same-game or an "
              "unpriceable leg); these still enter dispersion",
        columns=("card_key", "asks"),
        rows=sorted(col.fair_null_by_card.items()),
    ))

    passed_1_5 = col.scanned - sum(
        removed[k] for k in ("2 purpose", "3 status", "4 fair NULL",
                             "5 fair outside (0,1)")
    )
    r6 = removed["6 single-read"]
    sections.append(Section(
        title="Rule 6: single-read against re-asked (rule 6 is not provably "
              "independent of the outcome; if the share removed exceeds 20% "
              "the result's first paragraph says so)",
        columns=("passed_rules_1_to_5", "single_read", "re_asked_removed",
                 "share_removed", "over_20_pct"),
        rows=[(passed_1_5, passed_1_5 - r6, r6,
               _cm_round(r6 / passed_1_5, 4) if passed_1_5 else None,
               (r6 / passed_1_5 > 0.20) if passed_1_5 else None)],
    ))

    day, share = _cm_largest_day(pop)
    r_vals = [a.r_f for a in pop]
    lvls = [float(_cm_level(a.legs)) for a in pop]
    sections.append(Section(
        title="Markup population (primary)",
        columns=("n", "G_days", "largest_day", "largest_day_share",
                 "tickers_asked_more_than_once", "asks_on_those_tickers",
                 "share_of_asks_on_repeat_tickers", "observed_sigma_r",
                 "planning_sigma_r", "sd_leg_count"),
        rows=[(len(pop), _cm_days(pop), day, _cm_round(share, 4),
               col.multi_ticker_tickers, col.multi_ticker_asks,
               _cm_round(col.multi_ticker_asks / len(pop), 4) if pop else None,
               _cm_round(statistics.stdev(r_vals), 4) if len(pop) > 1 else None,
               _CM_PLANNING_SIGMA_R,
               _cm_round(statistics.stdev(lvls), 4) if len(pop) > 1 else None)],
    ))

    # Reconstruction of g.
    recon_rows = []
    for lvl in _CM_LEG_LEVELS:
        grp = [a for a in pop if _cm_level(a.legs) == lvl]
        ok = [a for a in grp if a.g_tenths is not None]
        recon_rows.append((lvl, len(grp), len(ok),
                           _cm_round(len(ok) / len(grp), 4) if grp else None))
    ok_all = [a for a in pop if a.g_tenths is not None]
    recon_rows.append(("all", len(pop), len(ok_all),
                       _cm_round(len(ok_all) / len(pop), 4) if pop else None))
    sections.append(Section(
        title="g reconstructed from fair_prices as of the lookup (a "
              "reconstruction, not a stored value), by leg count",
        columns=("leg_count", "asks", "reconstructed", "share"),
        rows=recon_rows,
    ))
    reasons: dict[str, int] = {}
    for a in pop:
        if a.g_tenths is None:
            reasons[a.recon_reason or "unknown"] = reasons.get(
                a.recon_reason or "unknown", 0) + 1
    sections.append(Section(
        title="Why asks were not reconstructed (alternate-line legs carry no "
              "per-method values and fall under leg_has_no_fair_row)",
        columns=("reason", "asks"), rows=sorted(reasons.items()),
    ))
    recon_ok = bool(pop) and len(ok_all) / len(pop) >= _CM_RECON_FLOOR

    # The 20 cells.
    cell_rows = []
    for lvl in _CM_LEG_LEVELS:
        for lo, hi, label in _CM_BANDS:
            grp = [a for a in pop if _cm_level(a.legs) == lvl and a.band == label]
            cell_rows.append(_cm_describe((lvl, label), grp, interval=True))
    sections.append(Section(
        title="Cells: leg count x best-quote price band (never tested; "
              "intervals only at the floor of 20 asks on 10 days)",
        columns=("leg_count", "price_band") + _CM_DESC_COLS + _CM_INT_COLS,
        rows=cell_rows,
    ))

    # Floors.
    level_floor = {
        lvl: _cm_floor([a for a in pop if _cm_level(a.legs) == lvl])
        for lvl in _CM_LEG_LEVELS
    }
    p1_evaluable = sum(level_floor.values()) >= 2
    p2_pop = [a for a in pop
              if not a.first_unknown and a.hours_to_first is not None
              and a.hours_to_first >= 0]
    arm_under = [a for a in p2_pop if a.hours_to_first < 6]
    arm_over = [a for a in p2_pop if a.hours_to_first >= 6]
    p2_evaluable = _cm_floor(arm_under) and _cm_floor(arm_over)
    sections.append(Section(
        title="Floors (20 asks on 10 days): P1 needs two leg-count levels, "
              "P2 needs each arm; any g test also needs 80% reconstructed",
        columns=("item", "asks", "days", "meets_floor"),
        rows=[(f"leg_count {lvl}",
               len([a for a in pop if _cm_level(a.legs) == lvl]),
               _cm_days([a for a in pop if _cm_level(a.legs) == lvl]),
               level_floor[lvl]) for lvl in _CM_LEG_LEVELS]
        + [("P2 arm under 6h", len(arm_under), _cm_days(arm_under), _cm_floor(arm_under)),
           ("P2 arm 6h or more", len(arm_over), _cm_days(arm_over), _cm_floor(arm_over)),
           ("P1 evaluable", len(pop), _cm_days(pop), p1_evaluable),
           ("P2 evaluable", len(p2_pop), _cm_days(p2_pop), p2_evaluable),
           ("g reconstructed share >= 80%", len(ok_all), _cm_days(ok_all), recon_ok)],
    ))

    # Variants (point estimates, printed beside the primary).
    def fit_row(name, asks, p2=False):
        out = []
        for use_g in (False, True):
            coef, se, g_days, n = _cm_fit(asks, use_g, p2=p2)
            tt = coef / se if coef is not None and se else None
            out.append((name, "g" if use_g else "f", n, g_days,
                        _cm_round(coef, 5), _cm_round(se, 5), _cm_round(tt, 3)))
        return out

    big_day, _share = _cm_largest_day(pop)
    no_age = [a for a in col.everyone if a.single_read and a.prov_ok]
    with_r6 = [a for a in col.everyone if a.prov_ok and a.age_ok]
    variant_rows = []
    variant_rows += fit_row("P1 primary", pop)
    variant_rows += fit_row("P1 largest day dropped", [a for a in pop if a.day != big_day])
    variant_rows += fit_row("P1 refused_too_fine = 0",
                            [a for a in pop if a.refused_too_fine == 0])
    variant_rows += fit_row("P1 rule 6 rows put back", with_r6)
    variant_rows += fit_row("P1 no fair-age limit", no_age)
    sections.append(Section(
        title="P1: OLS slope of r on leg count (6+ coded 6), CR1 by Eastern "
              "day, against f and against g (variants are point estimates)",
        columns=("fit", "against", "n", "G_days", "beta", "se_cr1", "t"),
        rows=variant_rows,
    ))
    p2_variant_rows = []
    p2_variant_rows += fit_row("P2 primary", p2_pop, p2=True)
    p2_variant_rows += fit_row("P2 largest day dropped",
                               [a for a in p2_pop if a.day != big_day], p2=True)
    p2_variant_rows += fit_row("P2 rule 6 rows put back",
                               [a for a in with_r6 if not a.first_unknown
                                and a.hours_to_first is not None
                                and a.hours_to_first >= 0], p2=True)
    p2_variant_rows += fit_row("P2 no fair-age limit",
                               [a for a in no_age if not a.first_unknown
                                and a.hours_to_first is not None
                                and a.hours_to_first >= 0], p2=True)
    sections.append(Section(
        title="P2: coefficient on 'earliest leg starts under 6h' with leg "
              "count as a linear control, CR1 by day (variants are points)",
        columns=("fit", "against", "n", "G_days", "kappa", "se_cr1", "t"),
        rows=p2_variant_rows,
    ))
    unknown_start = sum(1 for a in pop if a.first_unknown)
    already_started = sum(
        1 for a in pop
        if not a.first_unknown and a.hours_to_first is not None
        and a.hours_to_first < 0
    )
    band_changed = sum(
        1 for a in pop
        if _cm_hours_cut(a.hours_to_first, a.first_unknown)
        != _cm_hours_cut(a.kalshi_clock_hours, a.kalshi_clock_hours is None)
    )
    sections.append(Section(
        title="P2 asks left out: start from the odds fixture via event_links "
              "(MIN over links; any unlinked leg = unknown, never guessed); "
              "band_changed counts asks whose hours-to-first band differs "
              "from the Kalshi-clock source (kalshi_events.commence_ms, "
              "three hours late)",
        columns=("p2_unknown_start", "already_started", "band_changed_vs_kalshi_clock"),
        rows=[(unknown_start, already_started, band_changed)],
    ))

    # Leave-one-day-out for the primary P1.
    loo = []
    for d in sorted({a.day for a in pop}):
        rest = [a for a in pop if a.day != d]
        cc, cs, cg, cn = _cm_fit(rest, False)
        gc, gs, gg, gn = _cm_fit(rest, True)
        loo.append((d, sum(1 for a in pop if a.day == d), cn,
                    _cm_round(cc, 5), _cm_round(cc / cs if cc is not None and cs else None, 3),
                    gn, _cm_round(gc, 5),
                    _cm_round(gc / gs if gc is not None and gs else None, 3)))
    sections.append(Section(
        title="Primary P1, leave one Eastern day out",
        columns=("day_dropped", "asks_on_day", "n_f", "beta_c", "t_c",
                 "n_g", "beta_g", "t_g"),
        rows=loo,
    ))

    # Secondary slopes (points only).
    sec = []
    for name, keyfn in (
        ("card_key", lambda a: a.card_key or "NULL"),
        ("price_band", lambda a: a.band),
        ("league_mix", lambda a: ("more than one" if a.leagues and len(a.leagues) > 1
                                   else "one league" if a.leagues else "unknown")),
    ):
        for val in sorted({str(keyfn(a)) for a in pop}):
            grp = [a for a in pop if str(keyfn(a)) == val]
            sec.append((name, val, len(grp), _cm_days(grp),
                        _cm_round(_cm_slope_point(grp, False), 5),
                        len([a for a in grp if a.r_g is not None]),
                        _cm_round(_cm_slope_point(grp, True), 5)))
    sections.append(Section(
        title="P1 slope per card_key, price band and league mix (point "
              "estimates, never tested)",
        columns=("cut", "level", "n", "days", "beta_c_point", "n_g", "beta_g_point"),
        rows=sec,
    ))

    # The four tests.
    t_c = _cm_t_crit(_cm_days(pop))
    test_rows: list = []
    if p1_evaluable and t_c is not None:
        bc = _cm_fit(pop, False)[:2]
        bg = _cm_fit(pop, True)[:2]
        drop_bg = _cm_fit([a for a in pop if a.day != big_day], True)[0]
        ref0_bg = _cm_fit([a for a in pop if a.refused_too_fine == 0], True)[0]
        tc = bc[0] / bc[1] if bc[0] is not None and bc[1] else None
        tg = bg[0] / bg[1] if bg[0] is not None and bg[1] else None
        test_rows.append(("P1 up (beta_c and beta_g >= +t_crit)",
                          bool(tc is not None and tc >= t_c and recon_ok
                               and tg is not None and tg >= t_c)))
        test_rows.append(("P1 down (beta_c <= -t_crit)",
                          bool(tc is not None and tc <= -t_c)))
        outcome1 = _cm_p1_outcome(bc, bg, drop_bg, ref0_bg, t_c, recon_ok)
        sections.append(Section(
            title="P1 outcome (registered words; UNRESOLVED may not be "
                  "written as 'makers do not charge more for more legs')",
            columns=("t_crit_G_minus_1", "G_days", "outcome"),
            rows=[(_cm_round(t_c, 4), _cm_days(pop), outcome1)],
        ))
    else:
        sections.append(Section(
            title="P1 outcome", columns=("outcome",),
            rows=[("FLOOR NOT MET: no test run (look B owed if this is look A)",)],
        ))
    t_c2 = _cm_t_crit(_cm_days(p2_pop))
    if p2_evaluable and t_c2 is not None:
        kc = _cm_fit(p2_pop, False, p2=True)[:2]
        kg = _cm_fit(p2_pop, True, p2=True)[:2]
        drop_kg = _cm_fit([a for a in p2_pop if a.day != big_day], True, p2=True)[0]
        tkc = kc[0] / kc[1] if kc[0] is not None and kc[1] else None
        tkg = kg[0] / kg[1] if kg[0] is not None and kg[1] else None
        test_rows.append(("P2 tighter (both kappa <= -t_crit)",
                          bool(tkc is not None and tkg is not None and recon_ok
                               and tkc <= -t_c2 and tkg <= -t_c2)))
        test_rows.append(("P2 wider (both kappa >= +t_crit)",
                          bool(tkc is not None and tkg is not None and recon_ok
                               and tkc >= t_c2 and tkg >= t_c2)))
        sections.append(Section(
            title="P2 outcome", columns=("t_crit_G_minus_1", "G_days", "outcome"),
            rows=[(_cm_round(t_c2, 4), _cm_days(p2_pop),
                   _cm_p2_outcome(kc, kg, drop_kg, t_c2, recon_ok))],
        ))
    else:
        sections.append(Section(
            title="P2 outcome", columns=("outcome",),
            rows=[("FLOOR NOT MET: no test run (look B owed if this is look A)",)],
        ))
    sections.append(Section(
        title="The four registered one-sided tests at 0.0125 each (family "
              "alpha 0.05); only those whose floor holds are listed",
        columns=("test", "passes"), rows=test_rows,
    ))

    # Secondary cuts.
    sec_rows = []
    cuts = (
        ("hours_to_first_game", lambda a: _cm_hours_cut(a.hours_to_first, a.first_unknown)),
        ("target_size", lambda a: a.size_cut),
        ("league_mix", lambda a: ("more than one league" if a.leagues and len(a.leagues) > 1
                                   else "one league" if a.leagues else "unknown")),
        ("one_league_by_league", lambda a: (a.leagues[0] if a.leagues and len(a.leagues) == 1 else None)),
        ("card_key", lambda a: a.card_key or "NULL"),
    )
    for name, keyfn in cuts:
        for val in sorted({keyfn(a) for a in pop if keyfn(a) is not None}):
            grp = [a for a in pop if keyfn(a) == val]
            sec_rows.append(_cm_describe((name, val), grp, interval=False))
    sections.append(Section(
        title="Secondary cuts (descriptive: n, days, median and IQR; no "
              "interval, no test)",
        columns=("cut", "level") + _CM_DESC_COLS, rows=sec_rows,
    ))

    # Book beside the quote.
    book_rows = []
    for lvl in _CM_LEG_LEVELS:
        grp = [a for a in pop if _cm_level(a.legs) == lvl]
        have = [a for a in grp if a.book_ask is not None]
        book_rows.append((lvl, len(grp), len(have),
                          sum(1 for a in have if a.book_ask <= a.b)))
    sections.append(Section(
        title="The order book's own ask beside the best quote (counts only)",
        columns=("leg_count", "asks", "book_ask_non_null", "book_at_or_below_best_quote"),
        rows=book_rows,
    ))

    # Dispersion: rules 1, 2, 3 and 6 only, fair or not.
    disp = [d for d in col.disp_asks if d[2] and d[0] is not None]
    count_rows = []
    for k in (0, 1, 2):
        count_rows.append((str(k), sum(1 for d in disp if len(d[3]) == k)))
    count_rows.append(("3 or more", sum(1 for d in disp if len(d[3]) >= 3)))
    sections.append(Section(
        title="Dispersion population (rules 1,2,3,6; fair or no fair): asks "
              "by stored quotes carrying a yes_ask",
        columns=("stored_quotes", "asks"), rows=count_rows,
    ))
    two_plus = [d for d in disp if len(d[3]) >= 2]
    disp_rows = []
    groups = [("all", lambda d: True)]
    groups += [(f"leg_count {lvl}", (lambda lvl: lambda d: _cm_level(d[0]) == lvl)(lvl))
               for lvl in _CM_LEG_LEVELS]
    groups += [("cross-game (fair present)", lambda d: d[1]),
               ("no fair (same-game or unpriceable)", lambda d: not d[1])]
    for name, pred in groups:
        grp = [d for d in two_plus if pred(d)]
        spreads = [max(d[3]) - min(d[3]) for d in grp]
        pcts = [100.0 * (max(d[3]) - min(d[3])) / min(d[3]) for d in grp if min(d[3]) > 0]
        disp_rows.append((name, len(grp),
                          _cm_round(_cm_median(spreads), 2),
                          _cm_round(_cm_q(spreads, 0.25), 2),
                          _cm_round(_cm_q(spreads, 0.75), 2),
                          _cm_round(_cm_median(pcts), 2),
                          _cm_round(_cm_q(pcts, 0.25), 2),
                          _cm_round(_cm_q(pcts, 0.75), 2)))
    sections.append(Section(
        title="Dispersion, worst minus best among an ask's stored yes_asks "
              "(asks with two or more quotes; no test, no interval)",
        columns=("group", "asks", "median_tenths", "q1_tenths", "q3_tenths",
                 "median_pct_of_best", "q1_pct", "q3_pct"),
        rows=disp_rows,
    ))
    return sections


def _q_combo_markup(conn: sqlite3.Connection, args) -> list[Section]:
    """The makers' markup over the desk's fair on a combination, by leg count
    (#327; spec: `docs/measurements/2026-10-08-preregistration-combo-markup-by-
    leg-count.md`, whose decision rule this prints and nothing more).

    **Row bound.** `combo_rfqs` is walked once, newest first, through
    `--limit` (`idx_combo_rfqs_time`, rows before `--cutoff`); the default
    cutoff is Look A's, 2026-10-08T00:00:00Z. `combo_rfq_quotes` is read per
    ask by `idx_combo_rfq_quotes_rfq`. `parlay_lookups` is read per ask on
    `idx_parlay_lookups_time` inside a 24 hour window (the table has no
    ticker index). `fair_prices` is read per leg-event by `idx_fair_link`,
    bounded by the lookup's `requested_ms` and a nine day floor, and is never
    scanned (`INDEXED BY` makes any other plan an error; a test pins it).

    **What this does not establish** is registration section 10, which the
    result document quotes verbatim: not markup against the truth (`f` is the
    minimum-of-four joint and grows pessimistic with every leg; `g` is the
    other end of the band, reconstructed, not stored); not the fair at the
    instant of the ask (frozen at lookup, up to 30 minutes earlier); not
    Kalshi's combination market, only this desk's self-selected asks; not
    other sizes; not what is paid (before the taker fee); not every maker;
    nothing about same-game combinations; nothing about outcomes or edge;
    not causal; not "ask again". It reads no settlement and no fill.

    **No running figure.** Run it once per registered look. Wiring this to a
    route, a push or a log line spends the registration (section 6).

    Deviations from the registration, where it could not be followed exactly:
    (1) steps 9-10 of the funnel (no representable best ask, fewer than two
    legs or an unreadable `selected_legs`) are guards the registration does
    not name; (2) the lookup is searched for within 24 hours and the as-of
    `fair_prices` row within nine days; (3) the largest day dropped in a g
    fit is the largest day of the primary population; (4) an alternate-line
    leg is not told apart from any other leg with no fair row and both count
    as `leg_has_no_fair_row`; (5) `g` is rebuilt by calling the ladder's own
    `ladder_candidates` over a pool built as of the lookup, which requires
    `backend` to import; if it cannot, every ask is `ladder_unavailable` and
    no g test can pass; (6) kickoff, as amended: the registration's
    `kalshi_events.commence_ms` is a clock three hours late, so hours to
    first game and the P2 indicator use the odds fixture's start reached
    through `event_links` and `odds_fixtures` (MIN over links, earliest over
    the ask's legs). Any unlinked leg makes the ask `unknown` and out of P2
    (`p2_unknown_start`); the Kalshi clock is read only to count band changes.
    """
    cutoff_ms = _cm_parse_cutoff(getattr(args, "cutoff", None))
    col = _cm_collect(conn, args, cutoff_ms)
    return _cm_sections(col, cutoff_ms, args)
