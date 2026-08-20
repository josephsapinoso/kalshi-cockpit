"""`unmatched_events` holds one row per work item, not one per sighting.

ADR 0056. The linker re-derives the same match failures every pass and used to
append every derivation, so the table grew without the work list changing. On
live, 2026-08-19: **743,428 rows carrying 1,356 distinct items** -- a 548:1
duplication -- with the eight worst items appearing 2,477 times each, one reason
apiece, and `resolved` set on none of the 743,428.

What these tests do NOT establish
---------------------------------
- **Not that the queue gets worked.** `resolved` has never been set by anything
  and no code path sets it; a readable queue is a precondition for working one,
  not evidence that anyone does.
- **Not a latency claim.** `record_unmatched` was 8,162ms in one `link slow`
  line on a memory-starved box, and every number taken from that box describes
  the starvation rather than the code (see the correction at the foot of
  `docs/measurements/2026-08-19-the-prune-loses-to-the-writer.md`). Fewer rows
  behind a smaller index should cost less; that is a prediction, and the pass
  line's `record_unmatched` timing is where it gets checked.
- **Not that the `COUNT(*)` in the collapse equals the real sighting count.**
  It equals the number of rows the table happened to be holding, which
  retention has already trimmed. `seen_count` is exact only from v14 forward,
  and the migration's first value is a floor.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.match.linker import record_unmatched
from backend.store import db, retention

_MS_PER_DAY = 24 * 60 * 60 * 1000
NOW = 1_787_000_000_000


@pytest.fixture()
def conn(tmp_path):
    """A real database at the current schema, not a hand-built subset.

    Built through `init_db` deliberately: the constraint under test is an index
    declared in `schema.sql`, and a fixture that creates its own table is free
    to omit it and pass.
    """
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def sight(conn, *, ms, identifier="KXNFLGAME-26SEP13DALNYG", league=None,
          detail=None, reason="no_counterpart", side="kalshi"):
    record_unmatched(
        conn, observed_ms=ms, side=side, identifier=identifier,
        league=league, detail=detail, reason=reason,
    )


def rows(conn):
    return conn.execute(
        "SELECT first_seen_ms, last_seen_ms, seen_count, identifier, league, "
        "detail, reason FROM unmatched_items ORDER BY id"
    ).fetchall()


class TestASightingIsNotARow:
    def test_seeing_the_same_item_again_does_not_add_a_row(self, conn):
        for i in range(2_477):
            sight(conn, ms=NOW + i * 15_000)

        assert len(rows(conn)) == 1

    def test_the_count_is_the_number_of_sightings(self, conn):
        for i in range(5):
            sight(conn, ms=NOW + i * 15_000)

        assert rows(conn)[0]["seen_count"] == 5

    def test_first_seen_is_written_once_and_never_moves(self, conn):
        """The column that says how long this has been failing.

        A later sighting overwriting it would make every item look new on every
        pass, which is the append-only shape's blindness restated in one row.
        """
        sight(conn, ms=NOW)
        sight(conn, ms=NOW + 9 * _MS_PER_DAY)

        assert rows(conn)[0]["first_seen_ms"] == NOW

    def test_last_seen_moves_to_the_newest_sighting(self, conn):
        sight(conn, ms=NOW)
        sight(conn, ms=NOW + 9 * _MS_PER_DAY)

        assert rows(conn)[0]["last_seen_ms"] == NOW + 9 * _MS_PER_DAY


class TestNullsCollapseToo:
    """The case a bare unique index would silently exempt.

    SQLite treats NULLs as distinct in a UNIQUE index, so `(side, identifier,
    league, detail, reason)` over nullable `league` and `detail` would let a
    NULL-league item insert afresh every pass -- the exact behaviour ADR 0056
    removes, surviving behind an index that reads as though it prevents it.
    `record_unmatched`'s conflict target restates the index's `COALESCE`, and
    these are the tests that would notice either half being dropped.
    """

    def test_a_null_league_collapses(self, conn):
        for i in range(3):
            sight(conn, ms=NOW + i, league=None, detail="Dallas vs New York")

        assert len(rows(conn)) == 1
        assert rows(conn)[0]["seen_count"] == 3

    def test_a_null_detail_collapses(self, conn):
        for i in range(3):
            sight(conn, ms=NOW + i, league="Pro Football", detail=None)

        assert len(rows(conn)) == 1

    def test_both_null_collapses(self, conn):
        for i in range(3):
            sight(conn, ms=NOW + i, league=None, detail=None)

        assert len(rows(conn)) == 1

    def test_a_null_league_is_not_the_same_item_as_an_empty_one(self, conn):
        """`COALESCE(league, '')` maps NULL onto the empty string, so these DO
        collide.

        Asserted rather than left implicit, because it is the one place the
        collapse is lossy and a reader should meet it here rather than discover
        it. Neither value is written by the linker -- `event.league` is a name
        or `None` -- so nothing real depends on telling them apart.
        """
        sight(conn, ms=NOW, league=None)
        sight(conn, ms=NOW + 1, league="")

        assert len(rows(conn)) == 1


class TestTheIdentityIsTheWholeWorkItem:
    """Each component of the key separates items, so none can be dropped.

    A key missing a component collapses two distinct pieces of work into one and
    loses the second's reason -- which is the field a person reads to decide
    which alias to add.
    """

    @pytest.mark.parametrize(
        "field,other",
        [
            ("identifier", "KXNFLGAME-26SEP13GBMIN"),
            ("league", "NCAA Football"),
            ("detail", "Green Bay vs Minnesota"),
            ("reason", "ambiguous: 2 fixtures match the same team pair"),
            ("side", "odds"),
        ],
    )
    def test_a_different_value_is_a_different_item(self, conn, field, other):
        base = dict(league="Pro Football", detail="Dallas vs New York")
        sight(conn, ms=NOW, **base)
        sight(conn, ms=NOW + 1, **{**base, field: other})

        assert len(rows(conn)) == 2


class TestTheIndexIsTheGuard:
    def test_the_schema_refuses_a_duplicate_row(self, conn):
        """Duplication is impossible, not merely unlikely.

        `record_unmatched` is the only writer today. This asserts the table
        would refuse a second one that forgot to upsert, rather than trusting
        that no such writer is ever added.
        """
        sight(conn, ms=NOW, league=None, detail=None)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO unmatched_items (first_seen_ms, last_seen_ms, "
                "side, identifier, league, detail, reason) "
                "VALUES (?, ?, 'kalshi', 'KXNFLGAME-26SEP13DALNYG', NULL, "
                "NULL, 'no_counterpart')",
                (NOW, NOW),
            )


class TestRetentionForgetsItemsNotSightings:
    def test_an_item_still_being_seen_is_never_pruned(self, conn):
        """First seen a month ago, seen this pass. That is open work.

        Pruning on `first_seen_ms` would delete it and the next pass would
        insert it again with `seen_count` back to 1 -- so a month-long failure
        would present as new, forever, while `unmatched_pruned` reported a
        healthy number.
        """
        sight(conn, ms=NOW - 30 * _MS_PER_DAY)
        sight(conn, ms=NOW)

        removed = retention.prune_unmatched(conn, now=NOW)

        assert removed == 0
        assert len(rows(conn)) == 1

    def test_an_item_nobody_has_seen_for_a_week_is_pruned(self, conn):
        sight(conn, ms=NOW - 30 * _MS_PER_DAY)

        removed = retention.prune_unmatched(conn, now=NOW)

        assert removed == 1
        assert rows(conn) == []


# ---------------------------------------------------------------------------
# The old table, and how it goes away.
# ---------------------------------------------------------------------------
#
# `unmatched_events` is the pre-ADR-0056 append-only log. Nothing writes it any
# more. It is drained by `prune_legacy_unmatched` and dropped once empty,
# because collapsing or dropping it at boot was measured against live and costs
# 229s + 218s -- a multi-minute outage on the one volume that cannot be
# recreated. These tests are what make the drain safe to leave running
# unattended for the days it takes.


LEGACY_DDL = """
CREATE TABLE unmatched_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_ms INTEGER NOT NULL,
    side TEXT NOT NULL,
    identifier TEXT NOT NULL,
    league TEXT,
    detail TEXT,
    reason TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0
);
"""


def seed_legacy(conn, n):
    """The old shape, as the live volume still holds it."""
    conn.executescript(LEGACY_DDL)
    conn.executemany(
        "INSERT INTO unmatched_events (observed_ms, side, identifier, league, "
        "detail, reason) VALUES (?, 'kalshi', 'KX1', NULL, NULL, 'x')",
        [(NOW + i,) for i in range(n)],
    )
    conn.commit()


def legacy_exists(conn):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='unmatched_events'"
    ).fetchone() is not None


class TestTheLegacyTableIsDrainedNotMigrated:
    def test_a_fresh_database_has_no_legacy_table_at_all(self, conn):
        """It is gone from `schema.sql`, so nothing recreates it.

        Leaving it declared would give every new database an empty table that
        nothing writes and nothing reads -- dead schema that the next reader
        has to work out the status of.
        """
        assert not legacy_exists(conn)

    def test_draining_a_database_that_never_had_one_is_not_an_error(self, conn):
        """The common case, forever, once live has finished draining.

        A missing table must be a quiet zero rather than an exception: this
        runs inside the pass, and a raise here stops the recorder.
        """
        assert retention.prune_legacy_unmatched(conn) == 0

    def test_rows_are_removed(self, conn):
        seed_legacy(conn, 50)

        assert retention.prune_legacy_unmatched(conn) == 50

    def test_the_table_is_dropped_once_it_is_empty(self, conn):
        """Dropping 181,154 pages costs 218s; dropping one costs nothing.

        The drop is deferred to exactly the moment it is free, which is the
        whole reason this is a drain and not a migration.
        """
        seed_legacy(conn, 50)

        retention.prune_legacy_unmatched(conn)

        assert not legacy_exists(conn)

    def test_the_table_survives_a_partial_drain(self, conn, monkeypatch):
        """A budget that runs out must not drop a table with rows still in it.

        Dropping early would discard the backlog rather than drain it, and the
        prune would report a healthy number while doing it.

        `DELETE_BATCH` is shrunk because the real 20,000 clears any fixture
        small enough to write in a test in one batch -- so the first draft of
        this test could not be partial and passed for the wrong reason. The
        live backlog is 788,944 rows against that batch size, which is 40
        batches, so a partial drain is the *normal* case there and the
        untested one here.
        """
        monkeypatch.setattr(retention, "DELETE_BATCH", 10)
        seed_legacy(conn, 50)

        retention.prune_legacy_unmatched(conn, budget_s=-1.0)

        assert legacy_exists(conn)
        assert conn.execute(
            "SELECT COUNT(*) FROM unmatched_events"
        ).fetchone()[0] == 40

    def test_a_partial_drain_finishes_over_later_calls(self, conn, monkeypatch):
        """Several passes, not one. That is the design, so it is asserted."""
        monkeypatch.setattr(retention, "DELETE_BATCH", 10)
        seed_legacy(conn, 50)

        for _ in range(5):
            retention.prune_legacy_unmatched(conn, budget_s=-1.0)

        assert not legacy_exists(conn)

    def test_draining_the_legacy_table_leaves_the_live_one_alone(self, conn):
        """Two tables with similar names and opposite lifecycles.

        `unmatched_items` is steady state and `unmatched_events` is a backlog
        being emptied; a drain that took the wrong one would silently erase the
        work queue every full pass.
        """
        sight(conn, ms=NOW)
        seed_legacy(conn, 10)

        retention.prune_legacy_unmatched(conn)

        assert len(rows(conn)) == 1

    def test_the_pass_counts_the_backlog_separately(self, conn):
        """Summed into `unmatched_deleted`, a draining backlog would read as
        the steady-state rule misbehaving."""
        sight(conn, ms=NOW - 30 * _MS_PER_DAY)
        seed_legacy(conn, 10)

        result = retention.prune(conn, now=NOW)

        assert result.unmatched_deleted == 1
        assert result.legacy_unmatched_deleted == 10
        assert result.total == 11
