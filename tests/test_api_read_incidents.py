"""`api_read_incidents` -- schema v42, ADR 0151: a slow API read leaves a row.

**What this establishes:** the API's read-budget 503 and the recording loop's
failed loopback health probe each write a durable row naming the route, the
elapsed time and the exception class; the writer never raises, even against a
path that cannot be opened; the alert the loop raises carries the probe's own
words instead of the constant "health probe failed"; and the inspector can
read the table back.

**What it does not establish:** why a read was slow. Three hits on
2026-09-15 blanked the Games screen inside heavy write passes and the log had
already lost them; this table is what makes the next one a measurement, not
the measurement itself.

Every guard was verified by disabling it and watching the test go red; the
mutations are named on each class.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import httpx
import pytest

from backend.api import routes
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.notify.alerts import Alerter
from backend.seed_demo import seed_all
from backend.store import db

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_loop  # noqa: E402
from inspect_live_db import QUERIES  # noqa: E402
from tests.test_alerts import NOW, FakeNotifier  # noqa: E402
from tests.test_api_read_budget import _InterruptedConnection, get  # noqa: E402


def _rows(path: Path) -> list[tuple]:
    conn = sqlite3.connect(str(path))
    try:
        return [
            tuple(r)
            for r in conn.execute(
                "SELECT kind, method, path, elapsed_ms, error, budget_ms "
                "FROM api_read_incidents ORDER BY id"
            )
        ]
    finally:
        conn.close()


class TestTheWriterNeverRaises:
    """Mutation seen red: the `except Exception` around the insert removed --
    the bad-path test then raises `OperationalError` instead of returning
    False."""

    def test_a_row_lands_and_reads_back(self, tmp_path):
        path = tmp_path / "t.db"
        db.init_db(path).close()
        ok = db.record_api_read_incident(
            path,
            kind=db.API_INCIDENT_READ_BUDGET,
            method="GET",
            path="/api/slate?days=2",
            elapsed_ms=27300,
            error="OperationalError: interrupted",
            budget_ms=25000,
            seen_ms=1_700_000_000_000,
        )
        assert ok is True
        conn = db.init_db(path)
        try:
            rows = [tuple(r) for r in db.api_read_incidents_since(conn, since_ms=0)]
        finally:
            conn.close()
        assert rows == [
            (
                1_700_000_000_000, "read_budget", "GET", "/api/slate?days=2",
                27300, "OperationalError: interrupted", 25000,
            )
        ]

    def test_an_unopenable_path_returns_false_and_logs_every_field(
        self, tmp_path, caplog
    ):
        """The incident happens because the database is contended; the writer
        must survive being refused, and the log line must carry the row so
        the refusal is not a second silence."""
        with caplog.at_level("WARNING", logger="backend.store.db"):
            ok = db.record_api_read_incident(
                tmp_path / "missing" / "nested" / "t.db",
                kind=db.API_INCIDENT_HEALTH_PROBE,
                method="GET",
                path="http://127.0.0.1:8000/api/health",
                elapsed_ms=2003,
                error="ReadTimeout: timed out",
            )
        assert ok is False
        line = " ".join(r.getMessage() for r in caplog.records)
        assert "could not be written" in line
        assert "ReadTimeout: timed out" in line and "2003" in line

    def test_the_kind_is_constrained(self, tmp_path):
        path = tmp_path / "t.db"
        db.init_db(path).close()
        # A CHECK on the column, not a Python guard: the inspector groups by
        # this value and a free-text kind would silently split the count.
        assert db.record_api_read_incident(
            path, kind="something_else", method=None, path=None,
            elapsed_ms=None, error="x",
        ) is False
        assert _rows(path) == []


class TestTheReadBudget503LeavesARow:
    """Mutation seen red: the `run_in_threadpool(db.record_api_read_incident,
    ...)` call deleted from `_sqlite_operational_error`."""

    @pytest.fixture
    def budget_app(self, tmp_path_factory, monkeypatch):
        path = tmp_path_factory.mktemp("read-incident-api") / "demo.db"
        seed_all(path)

        def fake_open_db(
            db_path, *, read_only=False, cross_thread=False, statement_budget_ms=None
        ):
            return _InterruptedConnection()

        # The incident writer opens its own sqlite3 connection, so the
        # monkeypatch on `open_db` starves the route and not the record.
        monkeypatch.setattr(routes.db, "open_db", fake_open_db)
        app = create_app(
            AppConfig(instance_mode="demo", db_path=path, api_read_budget_ms=1)
        )
        return app, path

    async def test_the_row_names_the_route_the_elapsed_and_the_budget(self, budget_app):
        app, path = budget_app
        resp = await get(app, "/api/window?days=2")
        assert resp.status_code == 503
        rows = _rows(path)
        assert len(rows) == 1, rows
        kind, method, route, elapsed_ms, error, budget_ms = rows[0]
        assert (kind, method, route, budget_ms) == (
            "read_budget", "GET", "/api/window?days=2", 1
        )
        assert isinstance(elapsed_ms, int) and elapsed_ms >= 0
        assert error.startswith("OperationalError: interrupted")


class _TimingOutClient:
    async def get(self, url, *, timeout):
        raise httpx.ReadTimeout("timed out", request=None)


class _RefusingClient:
    async def get(self, url, *, timeout):
        raise httpx.ConnectError("connection refused", request=None)


class _HealthyClient:
    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"live_quotes_available": True}

    async def get(self, url, *, timeout):
        return self._Response()


class TestTheLoopsProbeRecordsItsFailureClass:
    """Mutation seen red: `_record_probe_failure` made a no-op; and
    separately `detail` returned as the constant "health probe failed"."""

    async def test_a_timeout_and_a_refusal_are_told_apart(self, tmp_path):
        path = tmp_path / "t.db"
        db.init_db(path).close()

        slow = await run_loop.probe_hub_running(_TimingOutClient(), db_path=str(path))
        dead = await run_loop.probe_hub_running(_RefusingClient(), db_path=str(path))

        assert slow.hub_running is None and dead.hub_running is None
        assert "ReadTimeout" in slow.detail and "after " in slow.detail
        assert "ConnectError" in dead.detail
        kinds_and_errors = [(k, e.split(":")[0]) for k, _, _, _, e, _ in _rows(path)]
        assert kinds_and_errors == [
            ("health_probe", "ReadTimeout"), ("health_probe", "ConnectError")
        ]
        budgets = {b for *_, b in _rows(path)}
        assert budgets == {int(run_loop.HEALTH_TIMEOUT_S * 1000)}

    async def test_a_healthy_probe_writes_nothing(self, tmp_path):
        path = tmp_path / "t.db"
        db.init_db(path).close()
        probe = await run_loop.probe_hub_running(_HealthyClient(), db_path=str(path))
        assert probe == run_loop.ProbeResult(True, None)
        assert _rows(path) == []

    async def test_no_db_path_means_no_row_and_still_an_answer(self):
        probe = await run_loop.probe_hub_running(_TimingOutClient())
        assert probe.hub_running is None
        assert "ReadTimeout" in probe.detail


class TestTheAlertCarriesTheProbesWords:
    """Mutation seen red: `detail=probe_detail or "health probe failed"`
    reverted to the constant."""

    @pytest.fixture
    def conn(self, tmp_path):
        conn = db.init_db(tmp_path / "alerts.db")
        yield conn
        conn.close()

    async def test_the_notification_row_says_which_class_failed(self, conn):
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_feed(
            now_ms=NOW,
            hub_running=None,
            markets_priced=12,
            probe_detail="health probe failed: ReadTimeout: timed out after 2003ms",
        )
        assert [kind for kind, _ in notifier.failures] == ["Cockpit API unreachable"]
        row = conn.execute(
            "SELECT * FROM notifications ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        flat = " ".join(str(v) for v in tuple(row))
        assert "ReadTimeout" in flat and "2003ms" in flat

    async def test_without_a_probe_detail_the_old_constant_still_stands(self, conn):
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_feed(
            now_ms=NOW, hub_running=None, markets_priced=12
        )
        row = conn.execute(
            "SELECT * FROM notifications ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert "health probe failed" in " ".join(str(v) for v in tuple(row))


class TestTheInspectorReadsItBack:
    def test_read_incidents_lists_the_rows_and_counts_per_kind(self, tmp_path):
        path = tmp_path / "t.db"
        db.init_db(path).close()
        db.record_api_read_incident(
            path, kind="read_budget", method="GET", path="/api/slate",
            elapsed_ms=25100, error="OperationalError: interrupted",
            budget_ms=25000, seen_ms=1_700_000_000_000,
        )
        db.record_api_read_incident(
            path, kind="health_probe", method="GET", path="/api/health",
            elapsed_ms=2003, error="ReadTimeout: timed out", budget_ms=2000,
            seen_ms=1_700_000_060_000,
        )

        class Args:
            tail = 5
            limit = 2000

        conn = sqlite3.connect(str(path))
        try:
            sections = QUERIES["read-incidents"].run(conn, Args())
        finally:
            conn.close()
        tail, by_kind = sections
        assert tail.row_count == 2
        assert tail.rows[0][tail.columns.index("path")] == "/api/health"
        assert "seen_iso" in tail.columns
        counts = {r[by_kind.columns.index("kind")]: r[by_kind.columns.index("n")] for r in by_kind.rows}
        assert counts == {"read_budget": 1, "health_probe": 1}
