"""Schema and store-layer tests.

The schema is a contract about what numbers mean. These tests assert the parts
of that contract that are enforceable in SQL or at the boundary — price ranges,
the derived-ask identity, and the version guard that stops us reading a v1
database with v2 assumptions.
"""

from __future__ import annotations

import sqlite3

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
