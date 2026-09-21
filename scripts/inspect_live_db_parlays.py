"""The parlay desk and the combination markets it touches.

Queries: `parlay-candidates-timing`, `parlay-lookups-tail`,
`combo-bids-tail`, `combo-position-gaps`, `combo-position-orphans`,
`ladder-fixtures`, `scout-briefings`.

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

import sqlite3
import time
from datetime import datetime, timedelta, timezone

from inspect_live_db_common import (
    Section,
    _MS_PER_DAY,
    _derive_iso,
    _fetch,
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
