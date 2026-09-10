"""The API read-connection budget: `store.db.connect(statement_budget_ms=...)`
and the 503 it produces at the route layer.

**What this establishes:** a SQLite statement on a budgeted connection is
aborted once wall-clock time passes the budget, and the app-level exception
handler turns that abort into a 503 naming the cause rather than a bare 500.
**What it does not establish:** which specific query caused the incident this
guards against (four routes 500ing at Next's 30s rewrite-proxy timeout,
uvicorn OOM-killed at 1.88 GB) -- that is a separate lane's fix. See
`docs/adr/0135-an-abandoned-request-stops-executing.md`.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import httpx
import pytest

from backend.api import routes
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.seed_demo import seed_all
from backend.store import db as db_module

RECURSIVE_CTE = (
    "WITH RECURSIVE c(x) AS ("
    "SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 50000000"
    ") SELECT count(*) FROM c"
)


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


class TestBudgetedConnectionAbortsALongStatement:
    def test_it_raises_operational_error_within_about_a_second(self, tmp_path):
        """The mutation this guards: delete the `set_progress_handler` call in
        `store.db.connect` and this test stops observing an abort -- the
        recursive CTE either completes (slowly) or the thread join times out,
        either of which fails the assertions below rather than hanging the
        suite forever."""
        path = tmp_path / "budget.db"
        db_module.init_db(path).close()

        # `cross_thread=True` for the same reason `routes.get_conn` needs it:
        # the connection is created on this thread and driven from the worker
        # thread below, which is exactly the "created here, used there" case
        # the flag exists for -- not concurrent use, sequential use from a
        # different thread. See `store.db.connect`'s docstring.
        conn = db_module.connect(path, cross_thread=True, statement_budget_ms=50)
        outcome: dict[str, object] = {}

        def run() -> None:
            try:
                conn.execute(RECURSIVE_CTE)
                outcome["result"] = "completed"
            except sqlite3.OperationalError as exc:
                outcome["result"] = "interrupted"
                outcome["error"] = str(exc)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout=5.0)

        assert not worker.is_alive(), (
            "the recursive CTE did not return within 5s of a 50ms budget -- "
            "the progress handler is not aborting it"
        )
        assert outcome.get("result") == "interrupted", outcome
        assert "interrupted" in outcome["error"]
        conn.close()


class TestAnUnbudgetedConnectionIsUnaffected:
    def test_a_short_statement_completes_normally(self, tmp_path):
        path = tmp_path / "nobudget.db"
        db_module.init_db(path).close()
        conn = db_module.connect(path)
        row = conn.execute("SELECT 1").fetchone()
        assert row[0] == 1
        conn.close()

    def test_open_db_without_a_budget_also_completes(self, tmp_path):
        path = tmp_path / "nobudget-open.db"
        db_module.init_db(path).close()
        conn = db_module.open_db(path, read_only=True)
        row = conn.execute("SELECT 1").fetchone()
        assert row[0] == 1
        conn.close()


class _InterruptedConnection:
    """Stands in for a real `sqlite3.Connection` whose progress handler has
    already fired. Every entry point a caller might use to touch the
    database raises the same `OperationalError` the real handler raises, so
    the route-level test below exercises the app's exception handler without
    depending on timing to reliably blow a 1ms budget."""

    row_factory = None

    def execute(self, *args, **kwargs):
        raise sqlite3.OperationalError("interrupted")

    def executemany(self, *args, **kwargs):
        raise sqlite3.OperationalError("interrupted")

    def executescript(self, *args, **kwargs):
        raise sqlite3.OperationalError("interrupted")

    def cursor(self):
        raise sqlite3.OperationalError("interrupted")

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


class TestTheRouteAnswersAReadBudgetWith503:
    """The mutation this guards: delete the `@app.exception_handler
    (sqlite3.OperationalError)` registration in `create_app` and this test
    goes red -- the interrupted statement then falls through to a bare 500
    with no `read_budget_exceeded` body."""

    @pytest.fixture
    def budget_app(self, tmp_path_factory, monkeypatch):
        path = tmp_path_factory.mktemp("read-budget-api") / "demo.db"
        seed_all(path)

        def fake_open_db(
            db_path, *, read_only=False, cross_thread=False, statement_budget_ms=None
        ):
            # A real 1ms budget on real seeded data is not a reliable trigger
            # -- most seeded queries finish inside 1ms regardless. Standing in
            # for "the budget already fired" is what the ADR's monkeypatch
            # option is for.
            return _InterruptedConnection()

        monkeypatch.setattr(routes.db, "open_db", fake_open_db)
        return create_app(
            AppConfig(instance_mode="demo", db_path=path, api_read_budget_ms=1)
        )

    async def test_interrupted_statement_answers_503(self, budget_app):
        resp = await get(budget_app, "/api/window")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "read_budget_exceeded"
        assert body["budget_ms"] == 1
        assert "read budget" in body["detail"]

    async def test_other_operational_errors_are_not_reported_as_budget_hits(
        self, tmp_path_factory, monkeypatch
    ):
        """The handler's `"interrupted" not in str(exc)` branch re-raises
        anything else with this exception type, so a locked-database or
        malformed-statement bug still shows up as a 500, not a
        `read_budget_exceeded` false positive."""
        path = tmp_path_factory.mktemp("read-budget-other") / "demo.db"
        seed_all(path)

        class _LockedConnection(_InterruptedConnection):
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("database is locked")

        def fake_open_db(
            db_path, *, read_only=False, cross_thread=False, statement_budget_ms=None
        ):
            return _LockedConnection()

        monkeypatch.setattr(routes.db, "open_db", fake_open_db)
        app = create_app(
            AppConfig(instance_mode="demo", db_path=path, api_read_budget_ms=1)
        )
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/window")
        assert resp.status_code == 500
        assert "read_budget_exceeded" not in resp.text


class TestEnvExampleNamesTheBudget:
    def test_api_read_budget_ms_is_in_the_contract(self):
        contract = Path(__file__).resolve().parents[1] / ".env.example"
        text = contract.read_text(encoding="utf-8")
        assert "API_READ_BUDGET_MS" in text
