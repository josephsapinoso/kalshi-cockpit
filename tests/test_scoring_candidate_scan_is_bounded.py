"""`markets_awaiting_scoring`'s two `MIN(commence_ms)` subqueries are bounded.

**What this establishes.** `backend/scoring.py`'s candidate query has two
copies of `SELECT odds_event_id, MIN(commence_ms) ... FROM odds_snapshots
GROUP BY odds_event_id`, one per branch of a `UNION` -- and until this ticket
(#87) neither carried a `WHERE`, so the planner had to aggregate every row of
`odds_snapshots` (every event this tool has ever seen, not just the ones
`event_links`/`recommendations`/`venue_settlements` actually reference)
before the outer joins narrowed anything. `idx_odds_event_commence` --
`(odds_event_id, commence_ms)`, see `tests/test_odds_event_commence_index.py`
-- already exists and is shaped correctly for this query; what was missing
was a predicate telling the planner which groups to look at. The fix adds
`WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)` to both
subqueries -- the same bound `backend/parlays.py:689` and
`backend/store/fair_price_downsample.py:276` already use for the identical
shape.

**Why bounding to `event_links` changes nothing about the answer.** Both
subqueries are only ever joined *through* `event_links.odds_event_id`
(`o.odds_event_id = l.odds_event_id`), so a row whose `odds_event_id` is not
in `event_links` was already unreachable from the outer query -- the WHERE
only tells the planner what the join already guaranteed. `TestItAnswersTheSame`
is the oracle proof of that, and `TestMinCommenceSemanticsSurvive` pins that
the MIN-per-fixture value itself is unchanged, because eleven readers depend
on that column meaning "the earliest snapshot's commence time" (NEXT.md 35th
session, Still-open item 5).

**Why a plan assertion is the right guard, not a stopwatch.** Same argument
as `tests/test_candidate_scan_plan.py`: a timing on a shared machine is a
flake, and the property being bought is the shape (SEARCH, not SCAN), which
is deterministic given ANALYZE'd statistics on a seeded database. The seed
below builds `NOISE_EVENTS` unlinked `odds_event_id`s (each with several
snapshot rows, no `event_links` row) alongside a handful of linked ones, so
an unbounded `GROUP BY` has real volume to aggregate and a bounded one does
not touch it at all.

**What this does not establish.** Nothing about live magnitude or latency --
that is ticket #88's job, not this one's. This file only pins the query
*shape* and that the *answer* did not change.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.scoring import markets_awaiting_scoring
from backend.store import db as store

NOW = 1_788_000_000_000
HOUR_MS = 3_600_000

#: Number of odds_event_ids that exist but are never linked -- the volume an
#: unbounded GROUP BY would have to aggregate that a bounded one skips.
N_NOISE_EVENTS = 40
N_SNAPSHOTS_PER_NOISE_EVENT = 20

# The two-subquery UNION exactly as it read before ticket #87 (no WHERE on
# either subquery), retyped as a literal on purpose: it no longer exists in
# the source to be read from, and it is the ORACLE the bounded rewrite must
# match. Copied verbatim in shape from `backend/scoring.py`'s prior text.
OLD_UNBOUNDED_SQL = """
SELECT DISTINCT r.ticker,
       m.series_ticker,
       o.commence_ms AS true_commence_ms
FROM recommendations r
JOIN event_links l   ON l.id = r.link_id
JOIN kalshi_markets m ON m.ticker = r.ticker
JOIN (
    SELECT odds_event_id, MIN(commence_ms) AS commence_ms
    FROM odds_snapshots GROUP BY odds_event_id
) o ON o.odds_event_id = l.odds_event_id
WHERE r.clv_scored_ms IS NULL
  AND m.series_ticker IS NOT NULL

UNION

SELECT DISTINCT v.ticker,
       m.series_ticker,
       o.commence_ms AS true_commence_ms
FROM venue_settlements v
JOIN kalshi_markets m ON m.ticker = v.ticker
JOIN event_links l   ON l.kalshi_event_ticker = m.event_ticker
JOIN (
    SELECT odds_event_id, MIN(commence_ms) AS commence_ms
    FROM odds_snapshots GROUP BY odds_event_id
) o ON o.odds_event_id = l.odds_event_id
WHERE m.series_ticker IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM closing_lines c WHERE c.ticker = v.ticker
  )
"""

INDEX = "idx_odds_event_commence"


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "scoring_scan.db")
    yield c
    c.close()


def _insert_noise(conn) -> None:
    """`N_NOISE_EVENTS` odds_event_ids with real volume, never linked.

    Unreachable from the outer query either way (the join runs through
    `event_links`), but they give an unbounded `GROUP BY` something real to
    aggregate, which is the whole point of the plan assertion below.
    """
    rows = []
    for e in range(N_NOISE_EVENTS):
        eid = "noise-%d" % e
        for i in range(N_SNAPSHOTS_PER_NOISE_EVENT):
            rows.append(
                (
                    NOW - i * 1_000, NOW - i * 1_000, "baseball_mlb", eid,
                    NOW - HOUR_MS - i * 60_000, "H%d" % e, "A%d" % e,
                    "book%d" % (i % 5), "h2h" if i % 2 else "spreads",
                    "H%d" % e, None, None, 1.9,
                )
            )
    conn.executemany(
        "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
        "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
        "outcome_name, outcome_description, outcome_point, price_decimal) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def _seed_linked_recommendation(
    conn, *, suffix: str, true_commence_ms: int, extra_commence_ms=()
) -> None:
    """One linked, unscored recommendation -- the first branch of the UNION.

    `extra_commence_ms` inserts additional snapshot rows at the SAME
    `odds_event_id` with different `commence_ms` values, so
    `TestMinCommenceSemanticsSurvive` can pin that the returned value is the
    MIN across the fixture's rows, not merely the one row a naive fixture
    would have.
    """
    event_ticker = "EVT-%s" % suffix
    odds_event_id = "odds-%s" % suffix
    ticker = "KXMLBGAME-%s" % suffix
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
        "has_game_markets, first_seen_ms, last_seen_ms) "
        "VALUES ('KXMLBGAME','Pro Baseball',1,?,?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, "
        "title, category, commence_ms, status, first_seen_ms, last_seen_ms) "
        "VALUES (?,'KXMLBGAME','A vs B','Sports',?,'open',?,?)",
        (event_ticker, true_commence_ms + 3 * HOUR_MS, NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
        "series_ticker, first_seen_ms, last_seen_ms) VALUES (?,?,'KXMLBGAME',?,?)",
        (ticker, event_ticker, NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
        "odds_event_id, league, method, commence_skew_ms, linked_ms) "
        "VALUES (?,?,'Pro Baseball','exact_alias_pair',?,?)",
        (event_ticker, odds_event_id, -3 * HOUR_MS, NOW),
    )
    link_id = conn.execute(
        "SELECT id FROM event_links WHERE odds_event_id = ?", (odds_event_id,)
    ).fetchone()["id"]

    for commence_ms in (true_commence_ms,) + tuple(extra_commence_ms):
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
            "sport_key, odds_event_id, commence_ms, home_team, away_team, "
            "bookmaker, market, outcome_name, price_decimal) "
            "VALUES (?,?,'baseball_mlb',?,?,'B','A','pinnacle','h2h','A',2.0)",
            (NOW, NOW, odds_event_id, commence_ms),
        )

    conn.execute(
        "INSERT OR IGNORE INTO strategy_configs (version, created_ms, "
        "effective_from_ms, config_json, rationale, approved_by_user) "
        "VALUES (1,?,?,'{}','test',0)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, link_id, side, entry_ask_tenths, fair_probability, "
        "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
        "suggested_contracts, kalshi_quote_age_ms, odds_age_ms, reason_text) "
        "VALUES (?,1,?,?,?,480,0.5,1.0,0.1,0.1,0.01,0,1000,1000,'t')",
        (true_commence_ms - 2 * HOUR_MS, ticker, link_id, "yes"),
    )
    conn.commit()


def _seed_linked_venue_settlement(conn, *, suffix: str, true_commence_ms: int) -> None:
    """One linked, unscored hand-bet settlement -- the second UNION branch."""
    event_ticker = "EVT-%s" % suffix
    odds_event_id = "odds-%s" % suffix
    ticker = "KXMLBGAME-%s" % suffix
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
        "has_game_markets, first_seen_ms, last_seen_ms) "
        "VALUES ('KXMLBGAME','Pro Baseball',1,?,?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, "
        "title, category, commence_ms, status, first_seen_ms, last_seen_ms) "
        "VALUES (?,'KXMLBGAME','C vs D','Sports',?,'open',?,?)",
        (event_ticker, true_commence_ms + 3 * HOUR_MS, NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
        "series_ticker, first_seen_ms, last_seen_ms) VALUES (?,?,'KXMLBGAME',?,?)",
        (ticker, event_ticker, NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
        "odds_event_id, league, method, commence_skew_ms, linked_ms) "
        "VALUES (?,?,'Pro Baseball','exact_alias_pair',?,?)",
        (event_ticker, odds_event_id, -3 * HOUR_MS, NOW),
    )
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
        "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
        "outcome_name, price_decimal) "
        "VALUES (?,?,'baseball_mlb',?,?,'D','C','pinnacle','h2h','C',2.0)",
        (NOW, NOW, odds_event_id, true_commence_ms),
    )
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths) "
        "VALUES (?,?,?,?,?,?,?)",
        (ticker, event_ticker, "yes", true_commence_ms + HOUR_MS, "yes", 1.0, 50),
    )
    conn.commit()


def _seed(conn) -> dict[str, int]:
    _insert_noise(conn)
    reco_commence = NOW - 5 * HOUR_MS
    _seed_linked_recommendation(
        conn, suffix="reco1", true_commence_ms=reco_commence,
        extra_commence_ms=(reco_commence + 45 * 60_000, reco_commence + 90 * 60_000),
    )
    settlement_commence = NOW - 6 * HOUR_MS
    _seed_linked_venue_settlement(
        conn, suffix="settle1", true_commence_ms=settlement_commence,
    )
    return {"reco1": reco_commence, "settle1": settlement_commence}


def _plan_for_the_live_query(conn: sqlite3.Connection) -> str:
    """The EXPLAIN QUERY PLAN of the EXACT statement `markets_awaiting_scoring`
    issues, captured via `set_trace_callback` so there is no risk of the test
    retyping a statement the function does not actually run (the drift
    `tasks/lessons.md` warns about, and the reason
    `tests/test_candidate_scan_plan.py` pins its SQL by name instead)."""
    captured: list[str] = []
    conn.set_trace_callback(captured.append)
    try:
        markets_awaiting_scoring(conn, now=NOW)
    finally:
        conn.set_trace_callback(None)

    stmt = next(s for s in captured if "FROM odds_snapshots" in s)
    rows = conn.execute("EXPLAIN QUERY PLAN " + stmt).fetchall()
    return " | ".join(r[3] for r in rows)


class TestTheSubqueryIsBoundedToTheEventsInPlay:
    def test_the_plan_does_not_scan_the_whole_index(self, conn):
        """Mutation observed red: drop the `WHERE odds_event_id IN (SELECT
        odds_event_id FROM event_links)` predicate from both subqueries in
        `backend/scoring.py` -- the plan reverts to a bare
        `SCAN odds_snapshots` (or a full index scan) that aggregates all
        `N_NOISE_EVENTS * N_SNAPSHOTS_PER_NOISE_EVENT` noise rows."""
        _seed(conn)
        conn.execute("ANALYZE")
        conn.commit()

        plan = _plan_for_the_live_query(conn)

        assert INDEX in plan, (
            f"the planner is not using {INDEX} to bound the subquery; "
            f"plan was: {plan}"
        )
        assert "SCAN odds_snapshots" not in plan, plan

    def test_it_answers_what_the_unbounded_statement_answered(self, conn):
        """The oracle. `OLD_UNBOUNDED_SQL` is the pre-#87 text, retyped as a
        literal. The bounded rewrite must return the identical row set over a
        seeded database where several dozen odds_event_ids exist and only a
        couple are linked.

        Mutation observed red: re-widen the bound to something that changes
        the answer (e.g. filter on a different table) -- the row sets would
        diverge; the bound this ticket adds does not, because both subqueries
        are only ever reached through `event_links` in the outer joins
        regardless of their own WHERE clause."""
        _seed(conn)
        conn.execute("ANALYZE")
        conn.commit()

        old_rows = {
            (r["ticker"], r["series_ticker"], int(r["true_commence_ms"]))
            for r in conn.execute(OLD_UNBOUNDED_SQL)
        }
        new_rows = {
            (r["ticker"], r["series_ticker"], r["true_commence_ms"])
            for r in markets_awaiting_scoring(conn, now=NOW)
        }

        assert old_rows, "the oracle answered nothing; the seed is wrong"
        assert new_rows == old_rows


class TestMinCommenceSemanticsSurvive:
    """Eleven readers depend on this column meaning the EARLIEST snapshot's
    commence time per fixture (NEXT.md 35th session, Still-open item 5). The
    bound must not change which row within a group wins the MIN."""

    def test_the_recommendation_branch_reports_the_earliest_snapshot(self, conn):
        commences = _seed(conn)
        conn.execute("ANALYZE")
        conn.commit()

        rows = markets_awaiting_scoring(conn, now=NOW)
        reco = next(r for r in rows if r["ticker"] == "KXMLBGAME-reco1")

        assert reco["true_commence_ms"] == commences["reco1"], (
            "the returned commence time is not the MIN across the fixture's "
            "snapshot rows"
        )
