"""The recorder's hottest read must be a seek, not a scan of a growing table.

`engine.persist_if_changed` runs ONCE PER CANDIDATE, every pass:

    SELECT id, entry_ask_tenths, fair_probability FROM recommendations
    WHERE ticker = ? AND side = ? ORDER BY created_ms DESC, id DESC LIMIT 1

Until 2026-08-26 there was no index on `(ticker, side)`. The planner answered
`SCAN recommendations` **and** `USE TEMP B-TREE FOR ORDER BY` — a full scan
plus a temporary sort, roughly 350 times a pass, against a table that grows and
is never trimmed.

MEASURED ON LIVE, 2026-08-26
----------------------------
    leg_price_persist_ms   26,000-40,000 for 290 fair prices and 4 rows
                           (~97ms per row)
    quote passes           35-74s against a 15-SECOND cadence
    /api/window            0.32s -> 17.8s
    /api/slate             0.38s -> 24.6s
    /api/parlays           past Next's 30s proxy timeout, returning 500

Three processes share one vCPU, so a recorder that cannot finish inside its own
cadence starves every API route. The site being slow was this.

**Football was the trigger, not the cause.** The cost is rows x candidates;
NCAAF roughly doubled the candidates and pushed a long-standing quadratic from
tolerable into pathological.

WHY THIS TEST READS THE PLAN AND NOT THE INDEX LIST
---------------------------------------------------
Asserting `idx_recs_ticker_side` exists would pass while the planner ignored
it — a covering index the query cannot use is indistinguishable from no index,
and that is exactly the failure being fixed. `EXPLAIN QUERY PLAN` is the only
thing that answers "is this a seek".

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That live got faster.** The plan is a precondition. The re-read has to
  happen on the box, and it has to be **split by whether a pass is running** —
  the caveat that made the original baseline misleading when it was taken in a
  quiet window and reported as "warm".
- **That the shared vCPU is now sufficient.** Removing a quadratic is not the
  same as having headroom.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from backend.store import db

HOT_QUERY = (
    "SELECT id, entry_ask_tenths, fair_probability FROM recommendations "
    "WHERE ticker = ? AND side = ? ORDER BY created_ms DESC, id DESC LIMIT 1"
)


@pytest.fixture
def conn():
    c = db.init_db(os.path.join(tempfile.mkdtemp(), "plan.db"))
    yield c
    c.close()


def plan(conn, sql: str, params=()) -> list[str]:
    return [r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


class TestThePersistLookupIsASeek:
    def test_it_does_not_scan_the_table(self, conn):
        steps = plan(conn, HOT_QUERY, ("KXTEST-A", "yes"))
        assert not any(s.startswith("SCAN recommendations") for s in steps), (
            f"the recorder's per-candidate read is a full scan: {steps}"
        )

    def test_it_uses_an_index_on_ticker_and_side(self, conn):
        steps = plan(conn, HOT_QUERY, ("KXTEST-A", "yes"))
        assert any("USING INDEX" in s for s in steps), steps
        assert any("ticker=?" in s and "side=?" in s for s in steps), (
            f"the index is not being used for BOTH predicates: {steps}"
        )

    def test_the_order_by_needs_no_temporary_sort(self, conn):
        """The trailing columns are what remove it.

        An index on `(ticker, side)` alone still satisfies the WHERE and then
        sorts — which on this query is the more expensive half, because it
        materialises every row for that ticker before taking one.
        """
        steps = plan(conn, HOT_QUERY, ("KXTEST-A", "yes"))
        assert not any("TEMP B-TREE" in s for s in steps), (
            f"the ORDER BY still builds a temporary sort: {steps}"
        )

    def test_the_index_is_declared_in_the_schema_not_only_in_a_migration(self):
        """It has to reach the LIVE volume, which is an existing database.

        `init_db` runs `migrate` and then applies `schema.sql` unconditionally,
        so a `CREATE INDEX IF NOT EXISTS` there lands on an existing volume at
        the next boot — the same path `desk_attention`'s index took at v21. An
        index added only to a migration step would never reach a database
        already past that version.
        """
        from pathlib import Path

        schema = (
            Path(__file__).resolve().parents[1] / "backend" / "store" / "schema.sql"
        ).read_text(encoding="utf-8")
        assert "idx_recs_ticker_side" in schema
        assert "CREATE INDEX IF NOT EXISTS idx_recs_ticker_side" in schema


class TestTheOtherRecommendationsIndexesStillWork:
    """The new index must not have displaced the ones already relied on."""

    def test_the_created_ms_ordering_is_still_indexed(self, conn):
        steps = plan(
            conn,
            "SELECT id FROM recommendations ORDER BY created_ms DESC LIMIT 50",
        )
        assert not any("TEMP B-TREE" in s for s in steps), steps

    def test_the_unscored_partial_index_still_applies(self, conn):
        steps = plan(
            conn,
            "SELECT id FROM recommendations WHERE clv_scored_ms IS NULL LIMIT 10",
        )
        assert any("idx_recs_unscored" in s for s in steps), steps
