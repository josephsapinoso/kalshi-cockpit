"""`/api/signal`'s stale-while-revalidate cache (#187).

A cache miss on the registered CLV-signal join costs 3.1-13.8s
(`docs/measurements/2026-09-17-the-signal-cache-miss-is-the-desks-worst-
latency.md`), and `/board` and `/slate` block on this route in their server
components. This file pins that once a report exists, no request pays that
cost again -- a stale read is served at once, with its own `computed_ms`,
and at most one background recompute runs off the request path.

WHAT THESE TESTS DO NOT ESTABLISH
----------------------------------
- **Nothing about the registered `beta` statistic itself.** `test_clv_signal.py`
  owns that; `SQL_CLV_SIGNAL_PULL` is untouched here and every report used
  below comes from the real, unmodified `report_from_connection`.
- **Nothing about the frontend's rendering of `computed_ms`.** Only that the
  route serves a stale value promptly and with the correct number attached.

Each test resets `status._signal_cache` and `status._signal_refresh_in_flight`
before and after, because both are module-level state shared with every other
test in the process -- the same reason `test_clv_signal.py` clears
`_signal_cache` around its own route tests.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.api.routers import status
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.seed_demo import seed_all
from backend.store import db as db_module

DB_TOKEN = "test-token"


def _wait_until(condition, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


@pytest.fixture
def seeded_db(tmp_path):
    path = tmp_path / "live.db"
    seed_all(path)
    return path


@pytest.fixture
def real_report(seeded_db):
    """A genuine `SignalReport`, computed once with the real, unpatched
    `report_from_connection` -- never hand-built, for the same reason
    `test_clv_signal.py` refuses hand-constructed fixtures for the wire
    format: a fake report can't show a wiring bug the real one would."""
    conn = db_module.open_db(seeded_db, read_only=True, cross_thread=True)
    try:
        return status.report_from_connection(conn)
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _reset_signal_cache_state():
    status._signal_cache.clear()
    status._signal_refresh_in_flight = False
    yield
    status._signal_cache.clear()
    status._signal_refresh_in_flight = False


def _stale_computed_ms() -> int:
    return db_module.now_ms() - status.SIGNAL_CACHE_TTL_MS - 1_000


def _client(seeded_db) -> TestClient:
    app = create_app(
        AppConfig(instance_mode="live", auth_token=DB_TOKEN, db_path=seeded_db)
    )
    return TestClient(app)


class TestAStaleReportIsServedWithoutWaiting:
    def test_a_stale_report_is_served_without_waiting_for_the_recompute(
        self, seeded_db, real_report, monkeypatch
    ):
        """With the cached report older than the TTL and the recompute
        patched to block, the route must return the OLD report and its OLD
        `computed_ms` promptly -- not after the recompute finishes.

        Mutation observed red: make the stale branch of
        `_cached_signal_report` call `report_from_connection(conn)` (or await
        the background refresh) instead of returning the cached report and
        firing the refresh off to the side -- `elapsed` then grows past the
        block's own 2s ceiling and the assertion below fails.
        """
        stale_computed_ms = _stale_computed_ms()
        status._signal_cache["report"] = real_report
        status._signal_cache["computed_ms"] = stale_computed_ms

        release = threading.Event()

        def _blocking_recompute(conn):
            release.wait(timeout=2)
            return real_report

        monkeypatch.setattr(status, "report_from_connection", _blocking_recompute)

        with _client(seeded_db) as client:
            start = time.monotonic()
            resp = client.get("/api/signal")
            elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 1.0, (
            f"the route waited {elapsed:.2f}s on a recompute patched to block "
            "for up to 2s -- it should have served the stale report at once"
        )
        assert resp.json()["computed_ms"] == stale_computed_ms

        release.set()
        assert _wait_until(lambda: not status._signal_refresh_in_flight), (
            "the background refresh never finished after being released"
        )


class TestConcurrentStaleReadsStartOneRefresh:
    def test_concurrent_stale_reads_start_one_refresh(
        self, seeded_db, real_report, monkeypatch
    ):
        """Two stale reads arriving together must trigger exactly one
        recompute, not one each.

        Mutation observed red: drop the check-and-set under
        `_signal_refresh_lock` in `_maybe_start_background_signal_refresh`
        (always start a thread) -- `call_count` becomes 2.
        """
        stale_computed_ms = _stale_computed_ms()
        status._signal_cache["report"] = real_report
        status._signal_cache["computed_ms"] = stale_computed_ms

        call_count = 0
        count_lock = threading.Lock()
        release = threading.Event()

        def _counting_recompute(conn):
            nonlocal call_count
            with count_lock:
                call_count += 1
            release.wait(timeout=2)
            return real_report

        monkeypatch.setattr(status, "report_from_connection", _counting_recompute)

        with _client(seeded_db) as client:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(client.get, "/api/signal") for _ in range(2)
                ]
                responses = [f.result(timeout=5) for f in futures]

            assert all(r.status_code == 200 for r in responses)
            assert all(
                r.json()["computed_ms"] == stale_computed_ms for r in responses
            ), "both concurrent reads must see the stale report, not a partial one"

            assert _wait_until(lambda: call_count >= 1)
            # give a wrongly-unguarded implementation a chance to have
            # started a second thread before we check the count.
            time.sleep(0.1)
            assert call_count == 1

            release.set()
            assert _wait_until(lambda: not status._signal_refresh_in_flight)


class TestTheFirstReadWithNoReportStillComputesInline:
    def test_the_first_read_with_no_report_still_computes_inline(
        self, seeded_db, real_report, monkeypatch
    ):
        """There is nothing to serve stale on the very first read, so it must
        compute inline -- the response itself carries the fresh report, not a
        placeholder waiting on a background thread.

        Mutation observed red: make the "nothing cached" branch of
        `_cached_signal_report` also defer to
        `_maybe_start_background_signal_refresh` and return early -- the
        route would then answer in well under the recompute's own 0.3s sleep,
        and `elapsed >= 0.3` would fail.
        """
        assert status._signal_cache.get("report") is None

        def _slow_recompute(conn):
            time.sleep(0.3)
            return real_report

        monkeypatch.setattr(status, "report_from_connection", _slow_recompute)

        with _client(seeded_db) as client:
            start = time.monotonic()
            resp = client.get("/api/signal")
            elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed >= 0.3, (
            "a first read with nothing cached must compute inline and wait "
            "for it, not return before the recompute finished"
        )
        assert status._signal_cache.get("report") is not None
        assert status._signal_refresh_in_flight is False


class TestAFailedRefreshKeepsTheLastReport:
    def test_a_failed_refresh_keeps_the_last_report(
        self, seeded_db, real_report, monkeypatch, caplog
    ):
        """A background recompute that raises must be logged, and must leave
        the last good report exactly as it was -- never cache the failure as
        if it were a result. The next stale read must retry, not be stuck
        serving a report that never updates.

        Mutation observed red: in `_run_background_signal_refresh`, write
        `_signal_cache["report"]`/`["computed_ms"]` unconditionally (even
        when `report_from_connection` raised) -- `computed_ms` would then
        change to a fresh timestamp attached to no real report, or the
        `except` branch's `logger.warning` call is removed and `caplog`
        finds nothing.
        """
        stale_computed_ms = _stale_computed_ms()
        status._signal_cache["report"] = real_report
        status._signal_cache["computed_ms"] = stale_computed_ms

        def _failing_recompute(conn):
            raise RuntimeError("synthetic recompute failure")

        monkeypatch.setattr(status, "report_from_connection", _failing_recompute)

        with caplog.at_level(logging.WARNING, logger=status.logger.name):
            with _client(seeded_db) as client:
                resp = client.get("/api/signal")
                assert resp.status_code == 200
                assert resp.json()["computed_ms"] == stale_computed_ms

                assert _wait_until(lambda: not status._signal_refresh_in_flight)

        assert status._signal_cache["report"] is real_report
        assert status._signal_cache["computed_ms"] == stale_computed_ms, (
            "a failed refresh must not move computed_ms -- that would claim "
            "a recompute happened when it didn't"
        )
        assert any(
            "refresh failed" in record.message for record in caplog.records
        ), "a failed background refresh must be logged"

        # The next stale read retries rather than being wedged on a
        # permanently-failing cache entry.
        monkeypatch.setattr(
            status, "report_from_connection", lambda conn: real_report
        )
        with _client(seeded_db) as client:
            resp = client.get("/api/signal")
            assert resp.json()["computed_ms"] == stale_computed_ms  # still stale
            assert _wait_until(
                lambda: status._signal_cache["computed_ms"] != stale_computed_ms
            ), "a stale read after a failed refresh must retry, not give up"


class TestTheRefreshDoesNotUseTheRequestConnection:
    def test_the_refresh_does_not_use_the_request_connection(
        self, seeded_db, real_report, monkeypatch
    ):
        """`get_conn` (`backend/api/routes.py`) closes the request's
        connection when the response ends. The background refresh must open
        its own connection (`db.open_db`, same as `_notification_health` and
        `_recorder_health`) rather than closing over the request's -- so a
        refresh that tried to read the request's connection after that close
        would raise and be caught as a failed refresh, and `computed_ms`
        would never move.

        A small delay is spliced into the real `report_from_connection`
        (still calling straight through to it, against the real seeded
        database -- nothing about the query itself is faked) so the
        background read cannot win a race against the request finishing and
        `get_conn`'s `finally: conn.close()` running. Without the delay this
        mutation is a coin flip: `cross_thread=True` means a background
        thread reusing the request's connection does not error just for
        being on a different thread, only for reading it after it is
        actually closed, and closing loses that race often enough that the
        guard would look verified when it was not.

        Mutation observed red: have `_maybe_start_background_signal_refresh`
        (or the thread it starts) close over and reuse the route's own
        `conn` parameter instead of opening a fresh one from `db_path` --
        the background thread then reads a connection `get_conn`'s `finally`
        already closed, `report_from_connection` raises
        `sqlite3.ProgrammingError`, the refresh is logged as failed, and
        `computed_ms` never advances past `stale_computed_ms`.
        """
        stale_computed_ms = _stale_computed_ms()
        status._signal_cache["report"] = real_report
        status._signal_cache["computed_ms"] = stale_computed_ms

        real_report_from_connection = status.report_from_connection

        def _delayed_report_from_connection(conn):
            time.sleep(0.2)
            return real_report_from_connection(conn)

        monkeypatch.setattr(
            status, "report_from_connection", _delayed_report_from_connection
        )

        with _client(seeded_db) as client:
            resp = client.get("/api/signal")
            assert resp.status_code == 200
            # By the time the response has come back, the route's own
            # `get_conn` dependency has already closed its per-request
            # connection (`finally: conn.close()` in routes.py) -- well
            # before the delayed read above even starts.
            assert _wait_until(
                lambda: status._signal_cache["computed_ms"] != stale_computed_ms,
                timeout=5,
            ), (
                "the background refresh never completed -- it likely tried "
                "to read the request's already-closed connection"
            )

        assert status._signal_cache["computed_ms"] != stale_computed_ms
        assert status._signal_cache["report"] is not None
