"""Schema and store-layer tests.

The schema is a contract about what numbers mean. These tests assert the parts
of that contract that are enforceable in SQL or at the boundary — price ranges,
the derived-ask identity, and the version guard that stops us reading a v1
database with v2 assumptions.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from backend.store import db


@pytest.fixture
def conn(tmp_path):
    """A fresh database per test, in tmp_path. Never touches real data."""
    connection = db.init_db(tmp_path / "test.db")
    yield connection
    connection.close()


class TestSchemaApplication:
    def test_schema_applies_cleanly(self, conn):
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        expected = {
            "meta",
            "kalshi_series",
            "kalshi_events",
            "kalshi_markets",
            "kalshi_quotes",
            "closing_lines",
            "odds_snapshots",
            "api_credits",
            "event_links",
            "unmatched_events",
            "fair_prices",
            "model_ratings",
            "strategy_configs",
            "recommendations",
            "orders",
            "fills",
            "settlements",
            "lessons",
        }
        assert expected <= tables

    def test_schema_is_idempotent(self, tmp_path):
        path = tmp_path / "twice.db"
        db.init_db(path).close()
        db.init_db(path).close()  # must not raise

    def test_foreign_keys_are_enforced(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO kalshi_quotes (ticker, observed_ms, source) "
                "VALUES ('NO-SUCH-MARKET', 1, 'ws')"
            )


class TestSchemaVersionGuard:
    """Reading across schema versions is refused, not attempted.

    v1 of the previous project stored whole cents where v2 stored tenths.
    Reading one as the other divides every price by ten, silently, in the
    direction that makes everything look cheap.
    """

    def test_opening_a_matching_version_succeeds(self, tmp_path):
        path = tmp_path / "ok.db"
        db.init_db(path).close()
        db.open_db(path).close()

    def test_opening_a_mismatched_version_is_refused(self, tmp_path):
        path = tmp_path / "old.db"
        conn = db.init_db(path)
        conn.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
        conn.commit()
        conn.close()

        with pytest.raises(db.SchemaVersionMismatch):
            db.open_db(path)

    def test_opening_a_versionless_database_is_refused(self, tmp_path):
        path = tmp_path / "foreign.db"
        raw = sqlite3.connect(path)
        raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT, updated_ms INT)")
        raw.commit()
        raw.close()

        with pytest.raises(db.SchemaVersionMismatch):
            db.open_db(path)


class TestPriceConstraints:
    """Prices are integer tenths in 0..1000. The database refuses anything else."""

    def _seed_market(self, conn):
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
            "VALUES ('MKT', 0, 0)"
        )

    def test_accepts_a_valid_tenths_price(self, conn):
        self._seed_market(conn)
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, source, yes_bid_tenths) "
            "VALUES ('MKT', 1, 'ws', 241)"
        )

    @pytest.mark.parametrize("bad", [-1, 1001, 5000])
    def test_rejects_out_of_range_prices(self, conn, bad):
        self._seed_market(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO kalshi_quotes (ticker, observed_ms, source, yes_bid_tenths) "
                "VALUES ('MKT', 1, 'ws', ?)",
                (bad,),
            )

    def test_null_price_is_allowed_because_unreadable_is_not_zero(self, conn):
        """A missing bid means nobody is quoting, which is not a price of zero."""
        self._seed_market(conn)
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, source, yes_bid_tenths) "
            "VALUES ('MKT', 1, 'ws', NULL)"
        )
        row = conn.execute("SELECT yes_bid_tenths FROM kalshi_quotes").fetchone()
        assert row["yes_bid_tenths"] is None


class TestDerivedAsks:
    """The identity every EV calculation depends on."""

    def test_yes_ask_is_the_complement_of_the_no_bid(self):
        assert db.derive_yes_ask(520) == 480

    def test_no_ask_is_the_complement_of_the_yes_bid(self):
        assert db.derive_no_ask(450) == 550

    def test_absent_counterparty_bid_yields_no_ask_not_zero(self):
        """Nobody offering to sell is not the same as selling for free."""
        assert db.derive_yes_ask(None) is None
        assert db.derive_no_ask(None) is None

    def test_ask_for_side_reads_the_opposing_bid(self):
        row = {"yes_bid_tenths": 450, "no_bid_tenths": 520}
        assert db.ask_for_side(row, "yes") == 480
        assert db.ask_for_side(row, "no") == 550

    def test_ask_is_worse_than_bid_so_the_mid_would_understate_cost(self):
        row = {"yes_bid_tenths": 450, "no_bid_tenths": 520}
        yes_ask = db.ask_for_side(row, "yes")
        mid = (row["yes_bid_tenths"] + yes_ask) / 2
        assert yes_ask > mid  # pricing off the mid understates by 1.5c here

    def test_unknown_side_raises_rather_than_guessing(self):
        with pytest.raises(ValueError):
            db.ask_for_side({"yes_bid_tenths": 1, "no_bid_tenths": 1}, "maybe")


class TestCrossThreadConnections:
    """sqlite3 binds a connection to its creating thread. FastAPI does not.

    A sync dependency and a sync path operation run on **two different**
    threadpool workers, so a connection opened in `get_conn` is used from
    another thread. That failed ~60% of requests on the deployed demo while
    `/api/health` -- which reaches the backend through Next's rewrite proxy and
    never touches the dependency -- stayed 100% green.

    It did not reproduce locally: an idle threadpool tends to hand out the same
    worker twice, so the whole suite passed over it. What surfaced it was a
    deployed instance with a 30-second health check running alongside traffic.
    """

    def _query_in_another_thread(self, conn):
        """Run a query on a thread that did not create the connection."""
        result: dict = {}

        def work():
            try:
                conn.execute("SELECT 1").fetchone()
                result["ok"] = True
            except Exception as exc:            # noqa: BLE001
                result["error"] = exc

        t = threading.Thread(target=work)
        t.start()
        t.join()
        return result

    def test_the_guard_is_on_by_default(self, tmp_path):
        """Left on deliberately: for a genuinely shared connection it is real
        protection, and disabling it globally turns a loud error into a silent
        race in the writer paths."""
        conn = db.init_db(tmp_path / "a.db")
        result = self._query_in_another_thread(conn)
        assert isinstance(result.get("error"), sqlite3.ProgrammingError)
        conn.close()

    def test_cross_thread_opt_in_allows_the_fastapi_pattern(self, tmp_path):
        db.init_db(tmp_path / "b.db").close()
        conn = db.open_db(tmp_path / "b.db", read_only=True, cross_thread=True)
        result = self._query_in_another_thread(conn)
        assert result.get("ok"), f"cross-thread read failed: {result.get('error')}"
        conn.close()

    def test_the_api_dependency_opens_a_cross_thread_connection(
        self, tmp_path, monkeypatch
    ):
        """The regression, asserted where it can actually fail.

        The obvious test -- hammer `TestClient` from a thread pool and expect
        200s -- **passes with the fix removed**, so it is decoration.
        `TestClient` drives the app through a single anyio portal and does not
        reproduce the worker-to-worker hop that a real uvicorn server makes
        between a sync dependency and a sync path operation. It was written,
        seen to pass against the reverted fix, and deleted.

        This asserts the property directly instead: the connection the API opens
        per request must be usable from a thread other than the one that opened
        it. It fails the moment `cross_thread=True` is dropped.
        """
        from fastapi.testclient import TestClient

        from backend.api.routes import create_app
        from backend.config import AppConfig
        from backend.seed_demo import seed_all

        path = tmp_path / "api.db"
        seed_all(path)

        opened: list[dict] = []
        real_open_db = db.open_db

        def spy(*args, **kwargs):
            opened.append(kwargs)
            return real_open_db(*args, **kwargs)

        monkeypatch.setattr(db, "open_db", spy)

        client = TestClient(create_app(AppConfig(instance_mode="demo", db_path=path)))
        assert client.get("/api/board").status_code == 200

        assert opened, "the request opened no connection"
        assert all(kw.get("cross_thread") for kw in opened), (
            "the API opened a thread-bound connection; FastAPI runs the sync "
            "dependency and the sync endpoint on different threadpool workers, "
            "so this raises sqlite3.ProgrammingError on real traffic"
        )
