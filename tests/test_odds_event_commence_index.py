"""`idx_odds_event_commence` exists, and the reason it exists is written down.

WHY THIS EXISTS
---------------
This index was added on 2026-08-26 and removed the same hour, on the reasoning
that it "changed no plan": with it, `SEARCH ... USING INDEX
idx_odds_event_commence`; without it, `SEARCH ... USING INDEX idx_odds_event`.
Identical shape.

Both observations were correct. The conclusion was not. **EXPLAIN QUERY PLAN
reports the access method, never how many rows the method touches.** The
candidate scan's subquery takes `MIN(commence_ms)` per event; under
`idx_odds_event` — `(odds_event_id, market, fetched_ms DESC)` — `commence_ms`
is not in the index, so the minimum can only be found by reading every row of
the group and fetching the column from the table. About 1,400 rows per event on
live. With `commence_ms` as the second column the minimum is the first entry
and the search stops.

Measured on live 2026-09-10, via `inspect_live_db.py parlay-candidates-timing`:

    whole candidate scan                        73,526 ms   (494 rows)
    odds_snapshots MIN(commence_ms) GROUP BY    26,719 ms   (703 rows)
    fair_prices rows inside the scan window            848  of 10,112,298

848 rows in the window and 73 seconds to return them, while `/api/parlays`
answered 503 `read_budget_exceeded` at 25 s in front of Joe.

So this file guards two different things, and the second is the one that
actually prevents the repeat: the index, and the *recorded reason* for it. An
index whose justification has been deleted is one somebody removes again on the
same argument as last time.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about the live win.** The local number is 503.9 ms -> 167.5 ms at
  live's shape, warm and CPU-bound; live is I/O-bound against a 5.19 GB file.
  The mechanism points the same way but the magnitude is not transferable, and
  the post-deploy timing is the only thing that settles it.
- **Nothing about the cold-start 503.** A cold container has no page cache and
  that is a separate problem (`tasks/NEXT.md`).
- **It does not test that the query planner uses the index** on any particular
  database. `TestThePlannerPrefersIt` builds a small one and checks; a planner
  choice on a 3.7M-row table is not a property a unit test can pin.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from backend.store import db as store

REPO = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = REPO / "backend" / "store" / "schema.sql"
DB_PY = REPO / "backend" / "store" / "db.py"

INDEX = "idx_odds_event_commence"

#: The subquery from `CANDIDATE_SQL`, verbatim in shape.
SUB = """
SELECT odds_event_id, MIN(commence_ms) AS commence_ms,
       home_team, away_team, sport_key
FROM odds_snapshots
WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)
GROUP BY odds_event_id
"""


@pytest.fixture
def fresh(tmp_path):
    conn = store.init_db(tmp_path / "idx.db")
    yield conn
    conn.close()


class TestTheIndexIsThere:
    def test_a_fresh_database_has_it(self, fresh):
        names = {
            r[0]
            for r in fresh.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='odds_snapshots'"
            )
        }
        assert INDEX in names

    def test_it_leads_with_the_event_and_then_the_stamp(self, fresh):
        """Order is the whole point: `commence_ms` second is what lets the MIN
        stop at the first entry. Reversed, it would be useless here."""
        cols = [
            r[2]
            for r in fresh.execute("PRAGMA index_info(%s)" % INDEX)
        ]
        assert cols == ["odds_event_id", "commence_ms"]

    def test_schema_sql_declares_it(self):
        src = SCHEMA.read_text(encoding="utf-8")
        assert (
            "CREATE INDEX IF NOT EXISTS idx_odds_event_commence "
            "ON odds_snapshots(odds_event_id, commence_ms);" in src
        )

    def test_a_migration_declares_it_by_name(self):
        """`schema.sql` cannot reach an existing volume without a version bump
        that something checks. `migrate_db.py` verifies, by name, only the
        indexes a declared step names."""
        step = store._MIGRATIONS[39]
        assert INDEX in step.indexes
        assert any(INDEX in s for s in step.statements)

    def test_the_schema_version_covers_the_step(self):
        assert store.SCHEMA_VERSION >= 39


class TestTheReasonSurvivesInTheSource:
    """The guard that actually prevents the repeat.

    The index was removed once already, by someone reasoning correctly from
    `EXPLAIN QUERY PLAN`. If the measurement that overturns that reasoning is
    ever deleted, the same argument is available again and it looks sound.
    """

    def test_the_schema_records_that_plan_shape_is_not_cost(self):
        src = SCHEMA.read_text(encoding="utf-8")
        assert "never the number of rows" in src
        assert "removed the same hour" in src, (
            "the history of this index was deleted; without it the 2026-08-26 "
            "argument for removing it reads as sound"
        )

    def test_the_schema_records_the_live_measurement(self):
        src = SCHEMA.read_text(encoding="utf-8")
        for figure in ("73,526 ms", "26,719 ms", "848"):
            assert figure in src, f"the live measurement lost {figure}"

    def test_the_schema_records_the_cost_it_is_paying(self):
        """The write-amplification objection was right and is being paid, not
        dismissed. A benefit recorded without its cost is half an argument."""
        src = SCHEMA.read_text(encoding="utf-8")
        assert "190 MB" in src
        assert "write-amplification objection stands" in src


class TestThePlannerPrefersIt:
    def test_the_subquery_seeks_on_the_new_index(self, tmp_path):
        """A small database, so this is about planner preference and not about
        speed. The live magnitude is not a unit-testable property."""
        path = tmp_path / "plan.db"
        conn = store.init_db(path)
        for e in range(40):
            eid = "evt%d" % e
            conn.execute(
                "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
                "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
                ("KX%d" % e, "game %d" % e),
            )
            conn.execute(
                "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
                "odds_event_id, league, method, commence_skew_ms, linked_ms) "
                "VALUES (?, ?, 'Pro Baseball', 'test', 0, 0)",
                ("KX%d" % e, eid),
            )
            for i in range(30):
                conn.execute(
                    "INSERT INTO odds_snapshots (odds_event_id, sport_key, "
                    "commence_ms, home_team, away_team, bookmaker, market, "
                    "fetched_ms, outcome_name, price_decimal) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        eid,
                        "baseball_mlb",
                        1_789_000_000_000 + i * 60_000,
                        "H%d" % e,
                        "A%d" % e,
                        "book%d" % (i % 5),
                        "h2h" if i % 2 else "spreads",
                        1_789_000_000_000 + i * 1_000,
                        "H%d" % e,
                        1.9,
                    ),
                )
        conn.commit()
        conn.execute("ANALYZE")
        plan = " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + SUB))
        conn.close()
        assert INDEX in plan, (
            f"the planner is not using {INDEX} for the MIN(commence_ms) "
            f"subquery; plan was: {plan}"
        )


def test_the_index_does_not_replace_the_one_it_sits_beside():
    """`idx_odds_event` carries `market` and `fetched_ms` and serves the
    latest-price reads. This is an addition, never a substitution."""
    src = SCHEMA.read_text(encoding="utf-8")
    assert (
        "CREATE INDEX IF NOT EXISTS idx_odds_event ON odds_snapshots"
        "(odds_event_id, market, fetched_ms DESC);" in src
    )
