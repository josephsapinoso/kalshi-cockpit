"""#126 -- a refused convening leaves a trace in the schema.

What these tests establish
--------------------------
That each of the watcher's five decision paths writes exactly one row per
(budget day, outcome, detail), that a second cycle reaching the same outcome
increments `cycle_count` rather than inserting again, and that the recorder can
never fail the decision it is recording.

What they do NOT establish
--------------------------
- **Nothing about live.** Every row here is seeded; no live reading is implied
  by any of it. The first real row is whatever the deployed watcher writes.
- **Nothing about spend.** `agent_calls` is the meter. These tests never assert
  a token or call count, because this table records decisions, not cost.
- **Nothing about the tap path.** `routers/scout.py`'s 429 is deliberately not
  recorded here (Joe saw that refusal on his screen); no test pretends it is.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend import scout_watch
from backend.store import db
from backend.store.scout_watch_log import (
    CONVENED,
    KEYLESS,
    NO_CANDIDATE,
    OUTCOMES,
    REFUSED_ALLOWANCE,
    REFUSED_BUDGET,
    read_watch_log,
    record_watch_outcome,
)

from tests.test_scout_watch import (  # noqa: F401  -- reused harness
    CONFIG,
    NOW_MS,
    DeskStubClient,
    _add_briefing,
    _add_scoutable_fixture,
    _init_db,
    _ladder_payload,
)

DAY_MS = 86_400_000


def _rows(path):
    conn = db.connect(path)
    try:
        return [dict(r) for r in read_watch_log(conn, days=30)]
    finally:
        conn.close()


async def _one_cycle(path, monkeypatch, *, config_factory, **kwargs):
    """Run exactly one watcher cycle against a ladder holding one leg."""
    monkeypatch.setattr(
        scout_watch, "build_ladder_payload",
        lambda *a, **k: _ladder_payload(("KXA", "EVA", NOW_MS + 1_000_000)),
    )

    async def sleep(_seconds):
        pass

    opts = dict(
        refresh_hours=0, max_per_day=3, reserve_taps=0, enabled=True,
        sleep=sleep, clock=lambda: NOW_MS / 1000, max_cycles=1,
    )
    opts.update(kwargs)
    await scout_watch.watch_scouts_forever(
        path, config_factory, lambda cfg: DeskStubClient(), **opts
    )


class TestEachDecisionLeavesExactlyOneRow:
    """The four silences the log stream used to swallow, and the convening."""

    async def test_the_allowance_brake_is_recorded_with_the_ceiling_that_bound(
        self, tmp_path, monkeypatch
    ):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            _add_scoutable_fixture(
                conn, ticker="KXA", event_ticker="EVA", odds_event_id="odds-a",
                home="B", away="A", link_id=1,
            )
            _add_briefing(
                conn, ticker="KXA", status="complete", requested_ms=NOW_MS - 1000
            )
        finally:
            conn.close()

        await _one_cycle(
            path, monkeypatch, config_factory=lambda: CONFIG, max_per_day=1
        )

        rows = _rows(path)
        assert len(rows) == 1, rows
        assert rows[0]["outcome"] == REFUSED_ALLOWANCE
        # The ceiling that bound is named IN the detail, verbatim -- the whole
        # point of the table. A row that merely says "refused" would not have
        # answered #118's question.
        assert "SCOUT_AUTO_MAX_CONVENINGS_PER_DAY" in rows[0]["detail"]
        assert "1 of 1" in rows[0]["detail"]

    async def test_the_keyless_state_is_recorded_and_is_not_a_refusal(
        self, tmp_path, monkeypatch
    ):
        path = _init_db(tmp_path)

        await _one_cycle(path, monkeypatch, config_factory=lambda: None)

        rows = _rows(path)
        assert len(rows) == 1, rows
        # Distinct from every refusal: no ceiling bound, the desk does not
        # exist here. Folding it into refused_budget would report a budget
        # problem on an instance with no budget.
        assert rows[0]["outcome"] == KEYLESS
        assert rows[0]["outcome"] not in (REFUSED_ALLOWANCE, REFUSED_BUDGET)

    async def test_a_quiet_ladder_is_recorded_as_no_candidate(
        self, tmp_path, monkeypatch
    ):
        path = _init_db(tmp_path)
        # No scoutable fixture seeded, so nothing on the ladder resolves.
        await _one_cycle(path, monkeypatch, config_factory=lambda: CONFIG)

        rows = _rows(path)
        assert len(rows) == 1, rows
        assert rows[0]["outcome"] == NO_CANDIDATE

    async def test_a_convening_is_recorded_and_names_the_fixture(
        self, tmp_path, monkeypatch
    ):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            _add_scoutable_fixture(
                conn, ticker="KXA", event_ticker="EVA", odds_event_id="odds-a",
                home="B", away="A", link_id=1,
            )
        finally:
            conn.close()

        await _one_cycle(path, monkeypatch, config_factory=lambda: CONFIG)

        rows = _rows(path)
        convened = [r for r in rows if r["outcome"] == CONVENED]
        assert len(convened) == 1, rows
        assert "KXA" in convened[0]["detail"]


class TestOneRowPerWorkItemNotOnePerCycle:
    """ADR 0056's shape. The watcher wakes every 600s; a bound ceiling refuses
    ~144 times a day, and a row per cycle would be noise on the box #58 is
    about."""

    async def test_a_second_refusal_increments_rather_than_inserting(
        self, tmp_path, monkeypatch
    ):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            _add_scoutable_fixture(
                conn, ticker="KXA", event_ticker="EVA", odds_event_id="odds-a",
                home="B", away="A", link_id=1,
            )
            _add_briefing(
                conn, ticker="KXA", status="complete", requested_ms=NOW_MS - 1000
            )
        finally:
            conn.close()

        for _ in range(3):
            await _one_cycle(
                path, monkeypatch, config_factory=lambda: CONFIG, max_per_day=1
            )

        rows = _rows(path)
        assert len(rows) == 1, rows
        assert rows[0]["cycle_count"] == 3
        # first_ms and last_ms are a PAIR on purpose: a reader who collapses
        # them cannot tell a ceiling that bound once from one that bound all
        # evening, which is the difference between a brake working and a
        # brake stuck.
        assert rows[0]["first_ms"] <= rows[0]["last_ms"]

    def test_a_new_budget_day_gets_its_own_row(self, tmp_path):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            for day in (0, DAY_MS):
                record_watch_outcome(
                    conn,
                    budget_day_ms=day,
                    now_ms=day + 5,
                    outcome=REFUSED_BUDGET,
                    detail="500000 of 500000 Anthropic tokens already recorded today",
                )
            rows = [dict(r) for r in read_watch_log(conn, days=30)]
        finally:
            conn.close()

        assert len(rows) == 2, rows
        assert {r["budget_day_ms"] for r in rows} == {0, DAY_MS}
        assert all(r["cycle_count"] == 1 for r in rows)

    def test_a_late_cycle_cannot_drag_last_ms_below_first_ms(self, tmp_path):
        """`last_ms = MAX(...)`, not a bare assignment.

        Cycles are not guaranteed to arrive in clock order -- a retry or a
        clock step is enough. A bare assignment would move `last_ms` backwards
        past `first_ms` and trip the table's own CHECK on a write that is
        merely out of order.
        """
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            record_watch_outcome(
                conn, budget_day_ms=0, now_ms=9_000,
                outcome=NO_CANDIDATE, detail="quiet",
            )
            record_watch_outcome(
                conn, budget_day_ms=0, now_ms=1_000,   # earlier than the first
                outcome=NO_CANDIDATE, detail="quiet",
            )
            rows = [dict(r) for r in read_watch_log(conn, days=30)]
        finally:
            conn.close()

        assert len(rows) == 1, rows
        assert rows[0]["first_ms"] == 9_000
        assert rows[0]["last_ms"] == 9_000
        assert rows[0]["cycle_count"] == 2


class TestTheRecorderCannotFailTheDecision:
    """A refusal is already the safe path. A raising recorder would turn a
    cheap no-op into a crash loop on the watcher the unattended spend runs
    through."""

    def test_a_broken_table_does_not_raise(self, tmp_path):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            conn.execute("DROP TABLE scout_watch_log")
            conn.commit()
            # Must not raise. The decision stands; only its trace is lost.
            record_watch_outcome(
                conn, budget_day_ms=0, now_ms=1,
                outcome=REFUSED_BUDGET, detail="anything",
            )
        finally:
            conn.close()

    def test_an_unknown_outcome_never_reaches_the_database(self, caplog):
        """The recorder refuses BEFORE touching the connection, and says so.

        **Asserting only "no row was written" would be decoration**, and this
        was measured rather than assumed: with the guard deleted, the table's
        own CHECK rejects the insert and the broad `except` swallows it, so an
        empty table is the outcome either way and the test stayed green. What
        the guard actually changes is that the database is never touched and
        the reason is logged at ERROR instead of appearing as a swallowed
        traceback -- so that is what this pins.

        An outcome the vocabulary cannot name means a new decision path was
        added upstream without a word for it, which is this table's whole
        subject. It must be loud.
        """

        class RefusesToBeTouched:
            def execute(self, *a, **k):                   # pragma: no cover
                raise AssertionError(
                    "the guard let an unknown outcome reach the database"
                )

            def commit(self):                             # pragma: no cover
                raise AssertionError("the guard let a commit through")

        with caplog.at_level("ERROR"):
            record_watch_outcome(
                RefusesToBeTouched(), budget_day_ms=0, now_ms=1,
                outcome="something_new", detail="x",
            )

        assert any(
            r.levelname == "ERROR" and "unknown outcome" in r.getMessage()
            for r in caplog.records
        ), [r.getMessage() for r in caplog.records]

    def test_every_named_outcome_is_accepted_by_the_check(self, tmp_path):
        """The module's vocabulary and the table's CHECK agree, in both
        directions -- the drift `test_inspect_live_db_modules` exists to catch
        for the query registries, applied to this pair."""
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            for i, outcome in enumerate(OUTCOMES):
                record_watch_outcome(
                    conn, budget_day_ms=0, now_ms=i,
                    outcome=outcome, detail=f"detail {i}",
                )
            rows = [dict(r) for r in read_watch_log(conn, days=30)]
        finally:
            conn.close()
        assert {r["outcome"] for r in rows} == set(OUTCOMES)


class TestTheTableIsOnTheLiveVolumeToo:
    def test_the_migration_creates_it_on_a_database_that_predates_it(
        self, tmp_path
    ):
        """`schema.sql` is applied with CREATE TABLE IF NOT EXISTS and so does
        nothing at all to a volume that already exists. The v53 step is the
        other half, and without it the live box would carry the code and not
        the table."""
        path = tmp_path / "old.db"
        conn = db.init_db(path)
        # Undo v53 the way the other migration tests build an "old" database:
        # run the step's own `undo_statements`, then wind the stamp back. The
        # version lives in `meta`, not `PRAGMA user_version`.
        for statement in db._MIGRATIONS[53].undo_statements:
            conn.execute(statement)
        conn.execute(
            "UPDATE meta SET value = '52' WHERE key = 'schema_version'"
        )
        conn.commit()
        conn.close()

        # Refused before migrating, exactly as the API would refuse it on boot.
        with pytest.raises(db.SchemaVersionMismatch):
            db.open_db(path)

        conn = db.init_db(path)
        try:
            assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
            names = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            indexes = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
        finally:
            conn.close()

        assert "scout_watch_log" in names
        assert "idx_scout_watch_log_item" in indexes
        assert "idx_scout_watch_log_day" in indexes


class TestTheUniqueKeyIsRealRatherThanDecorative:
    def test_the_index_refuses_a_duplicate_insert(self, tmp_path):
        """`detail` is NOT NULL for this reason: SQLite treats NULLs in a
        unique index as distinct, so a nullable `detail` would let every cycle
        insert afresh -- the exact behaviour the upsert exists to prevent,
        surviving behind an index that claims to prevent it (the COALESCE
        lesson from `idx_unmatched_item`)."""
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            args = (0, 1, 1, 1, NO_CANDIDATE, "quiet")
            sql = (
                "INSERT INTO scout_watch_log (budget_day_ms, first_ms, "
                "last_ms, cycle_count, outcome, detail) VALUES (?, ?, ?, ?, ?, ?)"
            )
            conn.execute(sql, args)
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql, args)
        finally:
            conn.close()
