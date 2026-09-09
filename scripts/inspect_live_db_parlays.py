"""The parlay desk and the combination markets it touches.

Queries: `parlay-candidates-timing`, `parlay-lookups-tail`,
`combo-bids-tail`.

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

from inspect_live_db_common import (
    Section,
    _derive_iso,
    _fetch,
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
               p_conservative, oldest_book_age_ms, link_id,
               market_width, book_count, books_used, anchored_on_sharp,
               kalshi_event_ticker, odds_event_id,
               commence_ms, home_team, away_team, sport_key,
               event_title
        FROM (
        SELECT f.computed_ms, f.market, f.outcome_name, f.outcome_point,
               f.outcome_description,
               f.p_multiplicative, f.p_additive, f.p_power, f.p_shin,
               f.p_conservative, f.oldest_book_age_ms, f.link_id,
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
        WHERE f.market IN ('h2h', 'spreads', 'pitcher_strikeouts',
                          'batter_total_bases', 'batter_hits',
                          'batter_home_runs', 'batter_rbis')
          AND f.computed_ms >= ?
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
    rows = conn.execute(_SQL_PARLAY_CANDIDATES, (floor_ms, now_ms)).fetchall()
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
        (floor_ms, now_ms),
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
# **What this emits from `parlay_positions`: nothing.** The table appears only
# inside a `NOT EXISTS`, so every row this query prints is a row for which the
# position does NOT exist. It cannot print a position, a count of positions,
# or a rate over them.
_SQL_COMBO_POSITION_GAPS = (
    "SELECT m.id AS manual_order_id, m.submitted_ms, m.ticker, "
    "       m.count AS contracts_ordered, m.status, "
    "       (SELECT v.contracts FROM venue_positions v "
    "         WHERE v.ticker = m.ticker ORDER BY v.id DESC LIMIT 1) "
    "         AS venue_contracts_latest, "
    "       (SELECT v.polled_ms FROM venue_positions v "
    "         WHERE v.ticker = m.ticker ORDER BY v.id DESC LIMIT 1) "
    "         AS venue_polled_ms, "
    "       CASE WHEN NOT EXISTS (SELECT 1 FROM venue_positions v "
    "                              WHERE v.ticker = m.ticker) "
    "            THEN 'never seen at venue' "
    "            WHEN (SELECT v.contracts FROM venue_positions v "
    "                   WHERE v.ticker = m.ticker ORDER BY v.id DESC LIMIT 1) "
    "                 > 0 "
    "            THEN 'OPEN AT VENUE -- UNWATCHED' "
    "            ELSE 'closed at venue' END AS exposure "
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
    gaps = _derive_iso(gaps, "venue_polled_ms", "venue_polled_iso")

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
