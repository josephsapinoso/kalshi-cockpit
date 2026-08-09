"""Schema and store-layer tests.

The schema is a contract about what numbers mean. These tests assert the parts
of that contract that are enforceable in SQL or at the boundary — price ranges,
the derived-ask identity, and the version guard that stops us reading a v1
database with v2 assumptions.
"""

from __future__ import annotations

import sqlite3
import threading
import time

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


class TestMigration:
    """The live volume holds a database that predates the current schema.

    `schema.sql` is applied with `CREATE TABLE IF NOT EXISTS`, so a column added
    to the file is invisible to every database already on disk -- and the one on
    disk carries the evidence record, which is the single thing in this project
    that cannot be recreated. So the migration has to be tested against a real
    v1 database with real rows in it, not against a fresh one.
    """

    def _migrated_columns(self) -> list[tuple[str, str]]:
        """Every `(table, column)` any migration adds, in application order.

        Read from `_MIGRATIONS` rather than listed here, so a new version is
        covered by these tests the moment it is written. The previous form
        hardcoded v2 and the `recommendations` table, so v3 -- which adds two
        columns and an index to `orders` -- was migrated by code that four
        tests claimed to cover and none of them touched.
        """
        return [
            (table, column)
            for version in sorted(db._MIGRATIONS)
            for table, column, _ in db._MIGRATIONS[version].columns
        ]

    def _v1_database(self, tmp_path, *, rows=1):
        """A database at the earliest version, with every later addition removed.

        Built by dropping the columns rather than by keeping an old schema file
        around, so it cannot drift away from what v1 actually was: every other
        column comes from the current schema, and only the later additions
        differ.

        Indexes are dropped first because SQLite refuses to drop a column an
        index refers to -- which is itself the check that the fixture really is
        undoing everything the migration does, rather than quietly leaving the
        index behind on a "v1" database that never had one.
        """
        path = tmp_path / "v1.db"
        conn = db.init_db(path)
        added = self._migrated_columns()
        for version in sorted(db._MIGRATIONS):
            for name in db._MIGRATIONS[version].indexes:
                conn.execute(f"DROP INDEX IF EXISTS {name}")
            for statement in db._MIGRATIONS[version].undo_statements:
                conn.execute(statement)
        for table, column in added:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
            "config_json, rationale, approved_by_user) VALUES (1, 0, 0, '{}', '', 0)"
        )
        conn.execute(
            "INSERT INTO kalshi_series (series_ticker, league, has_game_markets, "
            "first_seen_ms, last_seen_ms) VALUES ('S', 'L', 1, 0, 0)"
        )
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, title, "
            "category, first_seen_ms, last_seen_ms) "
            "VALUES ('E', 'S', 't', 'Sports', 0, 0)"
        )
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
            "first_seen_ms, last_seen_ms) VALUES ('T', 'E', 'S', 0, 0)"
        )
        for i in range(rows):
            conn.execute(
                "INSERT INTO recommendations (created_ms, strategy_config_version, "
                "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
                "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
                "kalshi_quote_age_ms, odds_age_ms, reason_text) "
                "VALUES (?, 1, 'T', 'yes', 503, 0.55, 20.0, 0.1, 0.5, 0.02, 0, "
                "1000, 60000, 'kept')",
                (1_000 + i,),
            )
        # An order too, because v3 migrates `orders` and a fixture that only
        # holds recommendations would let a migration drop that table's rows
        # without any test noticing.
        for i in range(rows):
            conn.execute(
                "INSERT INTO orders (client_order_id, submitted_ms, ticker, side, "
                "action, order_type, count, limit_price_tenths, status, "
                "request_body_json, dry_run) "
                "VALUES (?, 0, 'T', 'yes', 'buy', 'limit', 1, 500, 'dry_run', "
                "'{}', 1)",
                (f"kept-{i}",),
            )
        conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
        conn.commit()
        conn.close()
        return path, added

    def test_a_v1_database_is_refused_until_it_is_migrated(self, tmp_path):
        """The refusal is the point: the API opens read-only and cannot migrate.

        This is why `entrypoint.sh` runs the migration before uvicorn starts.
        """
        path, _ = self._v1_database(tmp_path)
        with pytest.raises(db.SchemaVersionMismatch):
            db.open_db(path)

    def test_migrating_adds_the_columns_and_keeps_every_row(self, tmp_path):
        path, added = self._v1_database(tmp_path, rows=3)

        conn = db.init_db(path)
        assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
        for table, column in added:
            assert column in db._columns(conn, table)

        kept = conn.execute(
            "SELECT COUNT(*) n FROM recommendations WHERE reason_text = 'kept'"
        ).fetchone()
        assert kept["n"] == 3, "the record was not preserved across the migration"
        orders_kept = conn.execute("SELECT COUNT(*) n FROM orders").fetchone()
        assert orders_kept["n"] == 3, "the orders were not preserved"
        # New columns are NULL on old rows, which is exactly what `live_ages`
        # reads as "never re-derived" and falls back to `created_ms` for.
        null = conn.execute(
            "SELECT COUNT(*) n FROM recommendations WHERE last_confirmed_ms IS NULL"
        ).fetchone()
        assert null["n"] == 3
        conn.close()

        db.open_db(path).close()

    def test_migrating_twice_changes_nothing(self, tmp_path):
        """`entrypoint.sh` runs this on every boot."""
        path, _ = self._v1_database(tmp_path)
        db.init_db(path).close()

        conn = db.init_db(path)
        assert db.migrate(conn) == [], "a second run tried to migrate again"
        conn.close()

    def test_an_interrupted_migration_resumes(self, tmp_path):
        """A crash between the last ALTER and the version stamp must be survivable.

        `ALTER TABLE ADD COLUMN` raises on a column that already exists, so a
        version-gated migration with no per-step check would leave a database
        that can never be opened again -- and that database is the record.
        """
        path, added = self._v1_database(tmp_path)
        conn = db.connect(path)
        # Half-applied: the first column landed, then the process died.
        table, column = added[0]
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} INTEGER")
        conn.commit()
        conn.close()

        conn = db.init_db(path)
        for table, column in added:
            assert column in db._columns(conn, table)
        assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
        conn.close()

    def _seed_scored_recommendation(self, conn):
        """One recommendation carrying a score taken at the old 1.0h horizon."""
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
            "VALUES ('T', 0, 0)"
        )
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale, approved_by_user) "
            "VALUES (1, 0, 0, '{}', '', 0)"
        )
        line = conn.execute(
            "INSERT INTO closing_lines (ticker, horizon_hours, observed_ms, "
            "yes_bid_tenths, yes_ask_tenths) VALUES ('T', 1.0, 100, 510, 530)"
        )
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
            "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
            "kalshi_quote_age_ms, odds_age_ms, reason_text, clv_tenths, "
            "clv_scored_ms, closing_line_id, clv_horizon_hours) "
            "VALUES (0, 1, 'T', 'yes', 480, 0.55, 20.0, 0.1, 0.5, 0.02, 10, "
            "1000, 60000, 'seeded', 40.0, 999, ?, 1.0)",
            (line.lastrowid,),
        )
        conn.commit()

    def _seed_order(self, conn):
        """One market and one order, so a settlement row has something to point at.

        Plain `INSERT`, never `INSERT OR IGNORE`: `OR IGNORE` suppresses every
        constraint failure on the statement, including the `NOT NULL` that says
        the fixture is incomplete. That is how this file's gate helper inserted
        nothing at all for the life of the project while every `LEFT JOIN`
        silently matched zero rows.
        """
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
            "VALUES ('T', 0, 0)"
        )
        conn.execute(
            "INSERT INTO orders (client_order_id, submitted_ms, ticker, side, "
            "action, order_type, count, limit_price_tenths, status, "
            "request_body_json, dry_run) "
            "VALUES ('c1', 0, 'T', 'yes', 'buy', 'limit', 3, 500, 'dry_run', "
            "'{}', 1)"
        )

    def test_v5_tags_the_old_scores_and_leaves_them_intact(self, tmp_path):
        """The migration's UPDATE, which nothing exercised.

        Found by disabling: replacing v5's statements with `()` left the whole
        store suite green.

        **This asserts the opposite of its first version.** That one cleared the
        old scores so they would re-score at the new primary horizon, which ADR
        0011 originally specified. Keeping them is the better answer and the one
        Joe chose: the gate already filters on `clv_horizon_hours`, so a row
        tagged 1.0 is excluded from the primary count without touching it.
        Clearing bought nothing the filter was not already providing, at the
        cost of mutating the one record in this project that cannot be
        recreated.
        """
        path = tmp_path / "v4scored.db"
        conn = db.init_db(path)
        self._seed_scored_recommendation(conn)

        # Wind back to a genuine v4: the column did not exist there.
        conn.execute("ALTER TABLE recommendations DROP COLUMN clv_horizon_hours")
        conn.execute("UPDATE meta SET value = '4' WHERE key = 'schema_version'")
        conn.commit()

        assert 5 in db.migrate(conn)

        row = conn.execute(
            "SELECT clv_tenths, clv_scored_ms, closing_line_id, "
            "clv_horizon_hours FROM recommendations"
        ).fetchone()
        assert row["clv_tenths"] == 40.0, "the migration destroyed a score"
        assert row["clv_scored_ms"] == 999
        assert row["closing_line_id"] is not None
        assert row["clv_horizon_hours"] == 1.0, (
            "an untagged score is indistinguishable from one taken at the "
            "current horizon, which is the mixture the column exists to stop"
        )
        conn.close()

    def test_a_kept_score_does_not_count_toward_the_gate(self, tmp_path):
        """Keeping the row is only safe because the gate excludes it.

        The two halves are in different modules -- the migration writes the tag,
        `gate.clustered_clv` filters on it -- and nothing links them, so the
        safety of decision 4 rests entirely on this. If the gate ever stops
        filtering, these rows silently rejoin the primary-horizon average at a
        different anchor.
        """
        from backend.gate import clustered_clv

        conn = db.init_db(tmp_path / "kept.db")
        self._seed_scored_recommendation(conn)

        assert clustered_clv(conn).n_rows == 0, (
            "a 1.0h score counted toward a gate measuring the 0.0h horizon"
        )
        conn.close()

    def test_columns_run_before_statements(self, tmp_path):
        """v3's index is over a column v3 itself adds, so the order is load-bearing.

        Asserted against v3 by name rather than swept over every step, and that
        narrowness is deliberate. The sweeping version of this test read
        *"every statement raises on a v1 database"* and broke on the first step
        whose statements are not an index over a new column -- v4 rebuilds a
        table, and `CREATE TABLE IF NOT EXISTS` raises on nothing. Widening the
        assertion to keep it passing would have meant asserting something true
        of no step in particular. See `two-limits-on-one-quantity`: a test that
        covers one property and reads as though it covers a class.
        """
        path, _ = self._v1_database(tmp_path)
        conn = db.connect(path)
        for statement in db._MIGRATIONS[3].statements:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(statement)
        conn.close()

    def test_every_statement_step_survives_being_run_twice(self, tmp_path):
        """A step interrupted after its statements re-runs them from the top.

        The version stamp is written only after the whole step succeeds, so
        every statement has to be safe to replay. Columns are guarded by reading
        `PRAGMA table_info`; a statement carries its own `IF NOT EXISTS`, or --
        where it cannot, as with v4's rebuild -- the step declares a column whose
        presence means it has already run.
        """
        path, _ = self._v1_database(tmp_path)
        db.init_db(path).close()
        conn = db.init_db(path)
        assert db.migrate(conn) == []

        for version in sorted(db._MIGRATIONS):
            step = db._MIGRATIONS[version]
            if any(
                column in db._columns(conn, table)
                for table, column in step.skip_statements_if_column
            ):
                # `migrate` would skip these, so replaying them by hand would
                # test something the runtime never does -- and for a rebuild it
                # would drop the table the migration just built.
                continue
            for statement in step.statements:
                conn.execute(statement)
        conn.close()

    def test_the_rebuild_is_skipped_once_it_has_landed(self, tmp_path):
        """The crash point a rebuild is not naturally idempotent at.

        Create-drop-rename replays safely at every interruption except after
        full success, where it would recreate the empty temp table and then drop
        the real one. The guard is what covers that, and the way to see it is to
        run the migration twice over a database holding a row.
        """
        conn = db.init_db(tmp_path / "v4.db")
        self._seed_order(conn)
        conn.execute(
            "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
            "contracts, pnl_cents, dry_run) VALUES (1, 'T', 1, 'yes', 3, 120, 1)"
        )
        conn.commit()

        # Wind the stamp back so v4 is eligible to run again, which is exactly
        # what a crash between the last statement and the stamp leaves behind.
        conn.execute("UPDATE meta SET value = '3' WHERE key = 'schema_version'")
        conn.commit()
        # `in`, not `==`: winding back to v3 re-runs every later step, so this
        # list grows with each new version. Asserting equality would make every
        # future migration turn this test red for a reason unrelated to what it
        # checks -- which is that v4's rebuild does not fire twice.
        assert 4 in db.migrate(conn)

        rows = conn.execute("SELECT COUNT(*) AS n FROM settlements").fetchone()
        assert rows["n"] == 1, "the rebuild ran again and dropped the real table"
        conn.close()

    def test_a_fresh_database_is_built_at_the_current_version(self, tmp_path):
        """No migration runs on a new file -- the schema file already has them.

        Running one would try to add columns `schema.sql` had just declared.
        """
        path = tmp_path / "fresh.db"
        conn = db.init_db(path)
        assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
        for table, column in self._migrated_columns():
            assert column in db._columns(conn, table)
        assert db.migrate(conn) == []
        conn.close()

    @pytest.mark.parametrize("version", sorted(db._MIGRATIONS))
    def test_each_single_step_runs_on_a_database_one_version_behind(
        self, tmp_path, version
    ):
        """Every step, from the version immediately before it.

        The fixture above builds a **v1** database, so it exercises 1 -> N as
        one sweep. That is not the transition a deployed volume makes: the live
        database is at v2 and will run v3 **alone**, against a schema that
        already has v2's columns. Nothing covered that, and it is the only
        migration path production will ever take.

        The distinction is not academic. A step that happens to work as part of
        a full sweep can fail on its own -- an `ALTER` whose table was created
        by an earlier step, an index over a column a previous version added --
        and the sweep is the case tests naturally reach for, because it is the
        one a fresh fixture produces.

        Parametrised over the migration table so a v4 is covered the day it is
        written rather than the day someone remembers.
        """
        path = tmp_path / f"v{version - 1}.db"
        connection = db.init_db(path)
        # Undo this version and everything after it, leaving the ones before.
        for later in sorted(db._MIGRATIONS):
            if later < version:
                continue
            for name in db._MIGRATIONS[later].indexes:
                connection.execute(f"DROP INDEX IF EXISTS {name}")
            for statement in db._MIGRATIONS[later].undo_statements:
                connection.execute(statement)
            for table, column, _ in db._MIGRATIONS[later].columns:
                connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(version - 1),),
        )
        connection.commit()
        connection.close()

        # Refused before, exactly as the API would refuse it on boot.
        with pytest.raises(db.SchemaVersionMismatch):
            db.open_db(path)

        connection = db.init_db(path)
        try:
            assert db.get_meta(connection, "schema_version") == str(db.SCHEMA_VERSION)
            for table, column in self._migrated_columns():
                assert column in db._columns(connection, table), (
                    f"{table}.{column} missing after migrating from "
                    f"v{version - 1}"
                )
        finally:
            connection.close()

        # And openable afterwards, which is what the deployed API does next.
        db.open_db(path).close()

    def test_the_schema_file_and_the_migrations_agree(self, tmp_path):
        """Every migrated column must also be in `schema.sql`.

        Otherwise a fresh database and a migrated one differ, and the difference
        shows up only on whichever of the two nobody develops against. That is
        the same shape as two implementations of one rule.
        """
        conn = db.init_db(tmp_path / "agree.db")
        for table, column in self._migrated_columns():
            assert column in db._columns(conn, table), (
                f"{table}.{column} is migrated onto old databases but missing "
                f"from schema.sql, so a fresh database would never have it"
            )
        # Indexes too, and for the sharper version of the same reason: a unique
        # index present on migrated databases and absent from `schema.sql`
        # means the constraint holds on the live volume and not on any
        # development one, so the duplicate it exists to stop is unreachable
        # exactly where anyone would try to reproduce it.
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        for version in sorted(db._MIGRATIONS):
            for index in db._MIGRATIONS[version].indexes:
                assert index in names, (
                    f"{index} is created by migration v{version} and is not in "
                    f"schema.sql, so a fresh database would never have it"
                )
        conn.close()


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


class TestASecondWriterWaitsInsteadOfFailing:
    """A blocked writer must wait, because there are now two of them.

    The order endpoint writes from the API process while the runner holds the
    write lock in bursts recording a pass. An order landing inside a burst must
    not fail outright: it would read as a defect in the order path rather than
    as contention, and it arrives after thirteen checks and a Kalshi round trip.

    **What this pins is a choice, not an invention.** CPython's `sqlite3`
    already defaults `timeout` to 5 seconds, so the first attempt at this --
    `PRAGMA busy_timeout = 5000` on every connection -- set the value the
    driver had already set and was a no-op. The test passed. It passed with the
    pragma deleted too, which is the only reason anyone looked.

    So `connect` passes `timeout=` explicitly and this asserts the behaviour it
    buys. Disable it by setting `BUSY_TIMEOUT_MS = 0`, which is the one edit
    that can actually remove the property.
    """

    def test_a_blocked_writer_waits(self, tmp_path):
        path = tmp_path / "contended.db"
        db.init_db(path).close()

        holder = db.connect(path)
        holder.execute("BEGIN IMMEDIATE")
        holder.execute(
            "INSERT INTO meta (key, value, updated_ms) VALUES ('a', 'b', 0)"
        )

        waiting = db.connect(path)
        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            # Still fails -- the holder never commits -- but only after
            # waiting. A zero timeout returns in microseconds.
            waiting.execute("BEGIN IMMEDIATE")
        waited_ms = (time.monotonic() - started) * 1000

        assert waited_ms > db.BUSY_TIMEOUT_MS * 0.5, (
            f"gave up after {waited_ms:.0f}ms against a "
            f"{db.BUSY_TIMEOUT_MS}ms timeout -- the second writer is not waiting"
        )
        holder.rollback()
        holder.close()
        waiting.close()

    def test_a_reader_gets_it_too(self, tmp_path):
        """WAL lets a reader run alongside a writer, but not alongside a
        checkpoint, so the read-only handle the API uses needs it as well."""
        path = tmp_path / "ro.db"
        db.init_db(path).close()
        conn = db.connect(path, read_only=True)
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS
        conn.close()


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
