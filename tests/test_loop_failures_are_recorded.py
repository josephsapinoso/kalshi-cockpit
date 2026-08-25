"""A failed recording pass leaves a durable row; a wedged one leaves nothing.

**Why this exists.** On 2026-08-25 the heartbeat alarmed: 35 minutes with no
quote write. `odds_sweep_log` later showed a **2,678-second hole** ending
20:51:02Z, where every other gap that day was a single jittered slow interval
(842-1,001s against a 1,035s ceiling). So two or three passes never finished --
and *which* could not be established. `LoopState.consecutive_failures` and
`last_error` live in memory, the container had restarted at 21:00:43Z, and its
logs went with it. A run of failing passes and one wedged pass need different
fixes and produced identical evidence.

`loop_failures` is the column that separates them, and the separation is the
whole design: rows are written **only** on the failure path, so across a silent
stretch rows mean "failing" and no rows mean "never came back to raise".

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **That a wedged pass is detected.** Nothing here times out a pass;
  `run_forever` still awaits `do_pass()` bare. This makes a wedge *legible*
  after the fact, not survivable.
- **That the alarm fires correctly.** `.github/workflows/heartbeat.yml` is not
  executed by any test; its threshold arithmetic is asserted in
  `tests/test_heartbeat_threshold_arithmetic.py`.
- **That the loop dies at the right count.** `MAX_CONSECUTIVE_FAILURES` is
  pinned in `tests/test_scheduler.py::TestItDiesLoudly`.
"""

from __future__ import annotations

import pytest

from backend import scheduler
from backend.scheduler import LoopState, run_forever
from backend.store import db

NOW = 1_787_680_800_000


@pytest.fixture()
def conn(tmp_path):
    c = db.init_db(tmp_path / "failures.db")
    yield c
    c.close()


async def _noop_sleep(_seconds: float) -> None:
    return None


class TestTheRecordSurvivesTheProcess:
    def test_a_failure_is_written_and_read_back(self, conn):
        db.record_loop_failure(
            conn, failed_ms=NOW, pass_number=7, consecutive_failures=2,
            error="TimeoutError: kalshi", pass_kind="full",
        )
        rows = db.loop_failures_since(conn, since_ms=0)
        assert len(rows) == 1
        assert dict(rows[0]) == {
            "failed_ms": NOW, "pass_number": 7, "consecutive_failures": 2,
            "pass_kind": "full", "error": "TimeoutError: kalshi",
        }

    def test_it_commits_rather_than_riding_the_callers_transaction(
        self, conn, tmp_path
    ):
        """The case this exists for is a process that does not get to commit.

        Mutation observed red: drop the `conn.commit()` in
        `db.record_loop_failure`.
        """
        db.record_loop_failure(
            conn, failed_ms=NOW, pass_number=1, consecutive_failures=1,
            error="boom",
        )
        other = db.open_db(tmp_path / "failures.db", read_only=True)
        try:
            assert len(db.loop_failures_since(other, since_ms=0)) == 1, (
                "a second connection cannot see the row, so it was never "
                "committed -- and an uncommitted failure record is not a record"
            )
        finally:
            other.close()

    def test_the_pass_kind_is_nullable_rather_than_guessed(self, conn):
        """A failure before the kind was chosen is a real state.

        Recording it as `full` would invent the one fact the row exists to
        carry.
        """
        db.record_loop_failure(
            conn, failed_ms=NOW, pass_number=1, consecutive_failures=1,
            error="boom",
        )
        assert db.loop_failures_since(conn, since_ms=0)[0]["pass_kind"] is None

    def test_an_unknown_pass_kind_is_refused_by_the_database(self, conn):
        """Mutation observed red: drop the CHECK from `schema.sql`."""
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            db.record_loop_failure(
                conn, failed_ms=NOW, pass_number=1, consecutive_failures=1,
                error="boom", pass_kind="sideways",
            )

    def test_failures_read_forwards(self, conn):
        """A run of failures is read oldest-first, because it tells a story."""
        for n, stamp in enumerate((NOW + 2000, NOW, NOW + 1000), start=1):
            db.record_loop_failure(
                conn, failed_ms=stamp, pass_number=n, consecutive_failures=n,
                error="boom",
            )
        stamps = [r["failed_ms"] for r in db.loop_failures_since(conn, since_ms=0)]
        assert stamps == [NOW, NOW + 1000, NOW + 2000]

    def test_the_window_excludes_what_precedes_it(self, conn):
        db.record_loop_failure(
            conn, failed_ms=NOW - 1, pass_number=1, consecutive_failures=1,
            error="before",
        )
        db.record_loop_failure(
            conn, failed_ms=NOW, pass_number=2, consecutive_failures=2,
            error="at the boundary",
        )
        rows = db.loop_failures_since(conn, since_ms=NOW)
        assert [r["error"] for r in rows] == ["at the boundary"], (
            "`since_ms` is inclusive; a boundary that dropped the row on it "
            "would silently shorten every window a reader asks for"
        )


class TestSilenceIsTheEvidence:
    """The property the whole design rests on: success writes nothing here."""

    async def test_a_loop_that_never_fails_records_nothing(self, conn):
        """Mutation observed red: add a `record_loop_failure` call to
        `run_forever`'s `else` branch.

        If success wrote rows too, "no rows across a gap" would stop meaning
        "the pass never came back" and the table would answer nothing.
        """
        calls: list[tuple] = []

        async def ok():
            return None

        await run_forever(
            ok, interval_s=1.0, max_passes=3, sleep=_noop_sleep,
            on_failure=lambda state, exc: calls.append((state, exc)),
        )
        assert calls == []
        assert db.loop_failures_since(conn, since_ms=0) == []


class TestTheHookSeesWhatItShouldRecord:
    async def test_it_is_called_after_the_counter_is_updated(self):
        """Mutation observed red: move the `on_failure` call above
        `state.consecutive_failures += 1` in `run_forever`.

        A hook that ran first would record every failure as the zeroth, which
        is the one number that makes a run of them legible.
        """
        seen: list[int] = []

        async def always_fails():
            raise RuntimeError("nope")

        state = LoopState()
        with pytest.raises(scheduler.LoopFailed):
            await run_forever(
                always_fails, interval_s=1.0, state=state, sleep=_noop_sleep,
                on_failure=lambda s, _e: seen.append(s.consecutive_failures),
            )
        assert seen == [1, 2, 3, 4, 5]

    async def test_it_is_handed_the_exception_that_was_raised(self):
        caught: list[BaseException] = []
        boom = RuntimeError("kalshi timed out")

        async def always_fails():
            raise boom

        with pytest.raises(scheduler.LoopFailed):
            await run_forever(
                always_fails, interval_s=1.0, sleep=_noop_sleep,
                on_failure=lambda _s, e: caught.append(e),
            )
        assert caught[0] is boom

    async def test_no_hook_leaves_the_loop_exactly_as_it_was(self):
        """The parameter is opt-in; every existing caller is untouched."""
        state = LoopState()

        async def always_fails():
            raise RuntimeError("nope")

        with pytest.raises(scheduler.LoopFailed):
            await run_forever(
                always_fails, interval_s=1.0, state=state, sleep=_noop_sleep,
            )
        assert state.consecutive_failures == 5

    async def test_a_raising_hook_does_not_end_the_loop(self):
        """Mutation observed red: remove the try/except around `on_failure`.

        The hook runs on the path where something has already gone wrong.
        Trading a recording loop for a bookkeeping error is the wrong
        direction -- the same argument `sleep_until` makes about `wake_when`.
        """
        succeeded: list[int] = []

        async def fails_once_then_works():
            if not succeeded:
                succeeded.append(1)
                raise RuntimeError("first pass")
            return None

        def bad_hook(_s, _e):
            raise ValueError("the recorder itself is broken")

        state = LoopState()
        await run_forever(
            fails_once_then_works, interval_s=1.0, state=state, max_passes=3,
            sleep=_noop_sleep, on_failure=bad_hook,
        )
        assert state.passes_succeeded == 2, (
            "a hook that raised took the loop down with it"
        )


class TestTheLoopWiresItUp:
    """`run_loop.main()` has no caller but `__main__`, so the wiring itself is
    asserted by reading the source. The behaviour is proved above."""

    @staticmethod
    def _source() -> str:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        return (root / "scripts" / "run_loop.py").read_text(encoding="utf-8")

    def test_the_loop_hands_run_forever_a_failure_hook(self):
        assert "on_failure=record_failure" in self._source()
        assert "def record_failure(" in self._source()

    def test_the_hook_persists_rather_than_logging(self):
        source = self._source()
        block = source[source.index("def record_failure("):]
        block = block[: block.index("def take_refresh_requests(")]
        assert "db.record_loop_failure(" in block, (
            "a hook that only logged would die with the container, which is "
            "the exact failure that made 2026-08-25 undiagnosable"
        )

    def test_the_error_text_comes_off_the_loop_state(self):
        """So the durable row and `LoopState.last_error` cannot disagree."""
        source = self._source()
        block = source[source.index("def record_failure("):]
        block = block[: block.index("def take_refresh_requests(")]
        assert "loop_state.last_error" in block

    def test_the_pass_kind_is_published_for_it(self):
        source = self._source()
        assert "in_flight_kind[0] = kind" in source
        assert "pass_kind=in_flight_kind[0]" in source
