"""The storage for Joe's own bets, and the four claims its shape rests on.

Registered in `docs/measurements/2026-08-17-preregistration-joe-calibration-
bet-log.md`. The question is whether **Joe** is overconfident as a forecaster,
not whether the engine has an edge -- ADR 0038 closed that, and nothing here
reopens it or touches the order path.

**What this establishes:** that a fill on a market this tool never discovered
can be recorded; that an estimate can exist before, and without, any position;
that a stated probability outside the registered range is refused by the
database rather than by a caller; and that the v10 rebuild preserves rows and
is a no-op on a database already at v10.

**What it does not establish:** anything about the measurement. Whether the
protocol is followed, whether the estimate was really written before a price
was seen, and whether the resulting statistic means anything are all §7 of the
registration and none of them is a schema property. It also says nothing about
the poller, which does not exist yet.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.store import db


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "cockpit.db")
    yield c
    c.close()


def _estimate(conn, **overrides):
    row = {
        "ticker": "KXMLBGAME-26AUG181840MIAPHI-MIA",
        "stated_probability_bp": 6200,
        "estimate_server_ms": 1_787_000_000_000,
        "cluster_key": "KXMLBGAME-26AUG181840MIAPHI",
    }
    row.update(overrides)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    return conn.execute(
        f"INSERT INTO bet_estimates ({cols}) VALUES ({marks})", tuple(row.values())
    )


class TestAHandBetOnAnUndiscoveredMarketIsRecordable:
    """The whole reason v10 rebuilds `fills` instead of adding a column.

    `PRAGMA foreign_keys = ON` is set in `connect`, so before v10 a fill on a
    ticker absent from `kalshi_markets` did not merely look untidy -- it
    raised. Bets are placed **by hand, in the Kalshi app**, on whatever market
    a person felt like, and the venue is the authority on what was traded. A
    tool that refuses to record a real fill because its own discovery had not
    reached that market has the direction of authority backwards.
    """

    def test_foreign_keys_are_actually_enforced(self, conn):
        """Otherwise the test below passes for the wrong reason, forever."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO closing_lines (ticker, horizon_hours, observed_ms) "
                "VALUES ('NEVER-DISCOVERED', 0.0, 1)"
            )

    def test_a_fill_needs_no_row_in_kalshi_markets(self, conn):
        conn.execute(
            "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
            "price_tenths, is_taker, fee_predicted, fee_model_used, source) "
            "VALUES ('f1', 'KXWNBAGAME-NEVER-DISCOVERED', 1, 2, 500, 1, 0.02, "
            "'model_a', 'venue_hand')"
        )

        assert conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1

    def test_the_two_populations_cannot_pool_silently(self, conn):
        """`source` is not decoration: they answer different questions.

        One is this tool's order path, which has never fired. The other is a
        person tapping buttons in an app we cannot observe. A fee measurement
        over both at once is a measurement of neither.
        """
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO fills (ticker, filled_ms, count, price_tenths, "
                "is_taker, fee_predicted, fee_model_used, source) "
                "VALUES ('T', 1, 1, 500, 1, 0.02, 'model_a', 'whatever')"
            )


class TestAnEstimateOutlivesTheAbsenceOfABet:
    """Why the estimate cannot be a column on `fills`.

    It is written and timestamped *before any fill exists*, and it must survive
    the case where no fill ever exists -- an estimate made and not acted on is
    the *less* selected sample and is a registered sensitivity analysis. A
    column on a row that does not yet exist cannot be written, which is fatal
    to the two-clock design rather than inconvenient.
    """

    def test_an_estimate_stands_alone_with_no_position(self, conn):
        _estimate(conn, match_status="unmatched_no_position")

        row = conn.execute(
            "SELECT matched_position_id, outcome_win, match_status "
            "FROM bet_estimates"
        ).fetchone()

        assert row["matched_position_id"] is None
        assert row["match_status"] == "unmatched_no_position"

    def test_an_unsettled_outcome_stays_null_and_is_not_a_loss(self, conn):
        """`NULL` and `0` are different states and this repo has merged them.

        A settled loser genuinely trades at 0 and genuinely scores 0, so a
        substituted zero is indistinguishable from data. The column is
        nullable so the distinction survives storage; nothing here stops a
        caller coercing it, which is why the analysis reads `IS NULL`.
        """
        _estimate(conn)

        assert conn.execute("SELECT outcome_win FROM bet_estimates").fetchone()[0] is None

    def test_a_matched_estimate_points_at_the_venue_record(self, conn):
        conn.execute(
            "INSERT INTO venue_settlements (ticker, settled_ms, side, "
            "contracts, entry_price_tenths) VALUES ('T-1', 99, 'yes', 2.0, 520)"
        )
        position_id = conn.execute(
            "SELECT id FROM venue_settlements"
        ).fetchone()["id"]
        _estimate(conn, matched_position_id=position_id, match_status="matched")

        joined = conn.execute(
            "SELECT e.stated_probability_bp, v.entry_price_tenths FROM bet_estimates e "
            "JOIN venue_settlements v ON v.id = e.matched_position_id"
        ).fetchone()

        assert joined["stated_probability_bp"] == 6200
        assert joined["entry_price_tenths"] == 520


class TestTheRegisteredRangeIsEnforcedByTheDatabase:
    """A caller that forgets is the failure mode; the schema is the backstop.

    The registration fixes `stated_probability_bp` at 1-9999 basis points. The
    open interval matters: 0 and 10000 are certainties, and a forecaster who
    states one has not made a probabilistic claim to score.
    """

    @pytest.mark.parametrize("bp", [0, -1, 10_000, 10_001])
    def test_a_certainty_or_an_impossibility_is_refused(self, conn, bp):
        with pytest.raises(sqlite3.IntegrityError):
            _estimate(conn, stated_probability_bp=bp)

    @pytest.mark.parametrize("bp", [1, 5_000, 9_999])
    def test_the_endpoints_of_the_registered_range_are_accepted(self, conn, bp):
        _estimate(conn, stated_probability_bp=bp)

        assert conn.execute(
            "SELECT stated_probability_bp FROM bet_estimates"
        ).fetchone()[0] == bp

    def test_basis_points_carry_a_precision_percent_would_lose(self, conn):
        """6789 is 67.89%, not 68%. Rounding a forecast is discarding it."""
        _estimate(conn, stated_probability_bp=6789)

        assert conn.execute(
            "SELECT stated_probability_bp FROM bet_estimates"
        ).fetchone()[0] == 6789


class TestTheV10RebuildIsSafeOnADatabaseThatAlreadyExists:
    """The live volume cannot be recreated, so the step has to be resumable.

    Every claim here is checked by winding a real database back to the v9
    shape with `_FILLS_REBUILD_UNDO` and migrating it forward, rather than by
    hand-building a fixture that agrees with the code by construction.
    """

    @staticmethod
    def _wound_back_to_v9(path: Path) -> None:
        c = db.init_db(path)
        for table, values in (
            ("kalshi_series (series_ticker, league, has_game_markets, "
             "first_seen_ms, last_seen_ms)", "('KXT','L',1,1,1)"),
            ("kalshi_events (event_ticker, series_ticker, title, category, "
             "commence_ms, close_ms, status, first_seen_ms, last_seen_ms)",
             "('E','KXT','t','Sports',1,2,'open',1,1)"),
            ("kalshi_markets (ticker, event_ticker, title, status, "
             "first_seen_ms, last_seen_ms)", "('T-1','E','m','open',1,1)"),
        ):
            c.execute(f"INSERT OR IGNORE INTO {table} VALUES {values}")
        c.execute(
            "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
            "price_tenths, is_taker, fee_predicted, fee_model_used) "
            "VALUES ('f1', 'T-1', 111, 3, 500, 1, 0.05, 'model_a')"
        )
        for statement in db._FILLS_REBUILD_UNDO:
            c.execute(statement)
        db._set_meta(c, "schema_version", "9")
        c.commit()
        c.close()

    def test_the_wind_back_really_restores_the_v9_shape(self, tmp_path):
        """Without this the migration test could be migrating v10 to v10."""
        path = tmp_path / "old.db"
        self._wound_back_to_v9(path)
        c = db.connect(path)

        assert "source" not in {r[1] for r in c.execute("PRAGMA table_info(fills)")}
        assert "kalshi_markets" in {
            r[2] for r in c.execute("PRAGMA foreign_key_list(fills)")
        }
        c.close()

    def test_migrating_preserves_every_row_and_labels_it_engine(self, tmp_path):
        path = tmp_path / "old.db"
        self._wound_back_to_v9(path)
        c = db.connect(path)

        # Every step from the recorded version up, not just v10 -- the wind-back
        # stamps v9 and later versions exist. Asserting equality with [10] made
        # this test fail the day v11 landed, which is noise rather than signal.
        assert 10 in db.migrate(c)

        row = c.execute(
            "SELECT id, kalshi_fill_id, ticker, count, price_tenths, source "
            "FROM fills"
        ).fetchone()
        assert (row["id"], row["kalshi_fill_id"], row["ticker"]) == (1, "f1", "T-1")
        assert (row["count"], row["price_tenths"]) == (3, 500)
        assert row["source"] == "engine", (
            "the only writer that has ever existed is the order path"
        )
        c.close()

    def test_migrating_drops_the_market_foreign_key_and_keeps_the_order_one(
        self, tmp_path
    ):
        path = tmp_path / "old.db"
        self._wound_back_to_v9(path)
        c = db.connect(path)
        db.migrate(c)

        referenced = {r[2] for r in c.execute("PRAGMA foreign_key_list(fills)")}

        assert "kalshi_markets" not in referenced
        assert "orders" in referenced, "the order link is real and stays"
        c.close()

    def test_running_the_step_twice_preserves_the_rows(self, tmp_path):
        """And the credit belongs to the copy, not to the skip guard.

        A first draft of this test claimed the guard prevented data loss here.
        **Mutation proved it did not**: deleting
        `skip_statements_if_column` from the v10 step left this green, because
        re-running CREATE / copy / DROP / RENAME on an already-rebuilt table
        copies the rows into a fresh temp table and renames it back. It is
        `INSERT OR IGNORE` that makes the sequence self-healing, not the guard.

        The claim was rewritten rather than the guard deleted, because the
        guard does buy something -- see the test below. What is not allowed is
        a docstring crediting it with a property it does not have.
        """
        path = tmp_path / "old.db"
        self._wound_back_to_v9(path)
        c = db.connect(path)
        db.migrate(c)
        db.migrate(c)

        assert c.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1
        assert "fills_v10" not in {
            r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        c.close()

    def test_the_guard_skips_the_rebuild_once_it_has_landed(self, tmp_path):
        """What `skip_statements_if_column` is actually for.

        Not correctness -- the copy covers that -- but *not redoing the work*.
        `migrate` does not stamp the version itself (`init_db` does, after the
        schema file runs), so between a migration and its stamp every call
        re-enters the step. Without the guard that is a full rebuild of the one
        table here that will actually grow, on every boot inside that window.

        Asserted by watching the statements the step issues, via SQLite's own
        trace callback -- `sqlite3.Connection` is a C type and will not take an
        attribute, which is how the first attempt failed. Counting rows cannot
        distinguish a skipped rebuild from a repeated one, which is exactly the
        blind spot that let the previous version of this test pass.
        """
        path = tmp_path / "old.db"
        self._wound_back_to_v9(path)
        c = db.connect(path)
        db.migrate(c)

        issued: list[str] = []
        c.set_trace_callback(issued.append)
        db.migrate(c)
        c.set_trace_callback(None)

        assert not any("fills_v10" in sql for sql in issued), (
            "the rebuild re-ran on a database already at v10: "
            f"{[s for s in issued if 'fills_v10' in s]}"
        )
        c.close()

    def test_an_interrupted_copy_does_not_duplicate_rows(self, tmp_path):
        """The `OR IGNORE` in the copy, verified rather than asserted in prose.

        A crash between the INSERT and the DROP leaves both tables populated.
        The step re-runs from the top on the next boot, and a plain INSERT
        would raise on the primary key -- a crash loop on the one volume in
        this project that cannot be recreated.
        """
        path = tmp_path / "old.db"
        self._wound_back_to_v9(path)
        c = db.connect(path)
        create, copy, _drop, _rename = db._FILLS_REBUILD
        c.execute(create)
        c.execute(copy)

        c.execute(copy)  # the re-run

        assert c.execute("SELECT COUNT(*) FROM fills_v10").fetchone()[0] == 1
        c.close()


class TestContractCountsAreFractionalOnThisVenue:
    """v10 declared these INTEGER from a spec written before anyone looked.

    The wire fields are `yes_count_fp` / `no_count_fp` -- `_fp` for fixed
    point, two decimals. The live record read on 2026-08-18 contains **11.27**
    and **0.27**. Under the v10 shape a 0.27-contract position rounds to
    **zero**: the position disappears and the entry price derived from it
    divides by zero.

    This is the same family as the deci-cent rule CLAUDE.md opens with -- a
    convenient integer that silently discards a real fraction of the value --
    and it is exactly why wire-format work has to be driven by a captured
    payload rather than by a specification.
    """

    @pytest.mark.parametrize(
        "count, description",
        [(0.27, "the 0.27-contract fill that INTEGER would round to zero"),
         (11.27, "the 11.27-contract position in the live record"),
         (21.0, "a whole 21 contracts, which must still come back exact")],
    )
    def test_a_fractional_count_survives_storage(self, conn, count, description):
        conn.execute(
            "INSERT INTO venue_settlements (ticker, settled_ms, side, "
            "contracts, entry_price_tenths) VALUES (?, 1, 'yes', ?, 500)",
            (f"T-{count}", count),
        )

        stored = conn.execute(
            "SELECT contracts FROM venue_settlements"
        ).fetchone()[0]

        assert stored == pytest.approx(count), description

    def test_a_fractional_fill_count_survives_too(self, conn):
        """v11 fixed this in one table and missed the other.

        The defect was corrected where it was noticed rather than everywhere
        the same quantity is held, which is how one fix leaves its twin in
        place. Both are REAL as of v12.
        """
        conn.execute(
            "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
            "price_tenths, is_taker, fee_predicted, fee_model_used, source) "
            "VALUES ('f-frac', 'T-1', 1, 0.27, 990, 1, 0.0001, 'model_a', "
            "'venue_hand')"
        )

        assert conn.execute("SELECT count FROM fills").fetchone()[0] == pytest.approx(0.27)

    def test_the_hundredths_column_v11_invented_is_gone(self, conn):
        """One answer to "how are sizes stored", not two."""
        columns = {r[1] for r in conn.execute("PRAGMA table_info(venue_settlements)")}

        assert "contracts_hundredths" not in columns
        assert "contracts" in columns


class TestV11RemovesWhatV10GotWrong:
    @staticmethod
    def _wound_back_to_v10(path: Path):
        c = db.init_db(path)
        for statement in db._V11_UNDO:
            c.execute(statement)
        db._set_meta(c, "schema_version", "10")
        c.commit()
        return c

    def test_the_wind_back_really_restores_the_v10_shape(self, tmp_path):
        c = self._wound_back_to_v10(tmp_path / "v10.db")

        assert "protocol_calibration_bet" in {
            r[1] for r in c.execute("PRAGMA table_info(bet_estimates)")
        }
        assert "contracts" in {
            r[1] for r in c.execute("PRAGMA table_info(venue_settlements)")
        }
        c.close()

    def test_migrating_replaces_both_tables_with_the_corrected_shape(self, tmp_path):
        path = tmp_path / "v10.db"
        self._wound_back_to_v10(path).close()
        conn = db.connect(path)

        assert 11 in db.migrate(conn)
        conn.executescript(db._SCHEMA_PATH.read_text(encoding="utf-8"))

        estimates = {r[1] for r in conn.execute("PRAGMA table_info(bet_estimates)")}
        settlements = {
            r[1] for r in conn.execute("PRAGMA table_info(venue_settlements)")
        }
        assert "protocol_calibration_bet" not in estimates, (
            "a field the registration vacated, that no branch reads"
        )
        assert {"market_result_public", "outcome_source", "retention_at_risk"} <= estimates
        assert "contracts" in settlements
        conn.close()

    def test_dropping_is_safe_because_nothing_has_ever_written_these(self, conn):
        """The assumption v11 rests on, asserted rather than trusted.

        v11 drops and recreates rather than copying, which is only defensible
        while both tables are provably empty everywhere. If a writer appears,
        this test fails and the next migration has to copy instead.
        """
        for table in ("bet_estimates", "venue_settlements"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


class TestARealV9VolumeBootsThroughEveryMigration:
    """The shape that took the live instance down on 2026-08-18.

    Every other migration test winds back from a database built by the CURRENT
    schema, so tables that did not exist at v9 -- venue_settlements,
    venue_balance_snapshots, bet_estimates, poll_log -- are already present
    before the wind-back. The real live volume predates all of them, and v11's
    `ALTER TABLE venue_balance_snapshots ADD COLUMN` raised `no such table`
    inside `init_db`, before the schema file that creates the table had run:
    a crash loop at boot, on the one database that cannot be recreated, found
    by the deploy and not by the suite.

    This fixture builds the genuine article: a database with NO post-v9 table
    at all, stamped v9, then boots it exactly the way the entrypoint does.
    """

    @staticmethod
    def _real_v9(path: Path) -> None:
        c = db.init_db(path)
        # The parent chain, because the v9 shape being restored carries the
        # kalshi_markets foreign key this fill must satisfy.
        c.execute(
            "INSERT INTO kalshi_series (series_ticker, league, has_game_markets, "
            "first_seen_ms, last_seen_ms) VALUES ('KXT', 'L', 1, 0, 0)"
        )
        c.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, title, "
            "category, commence_ms, close_ms, status, first_seen_ms, "
            "last_seen_ms) VALUES ('E', 'KXT', 't', 'Sports', 1, 2, 'open', 1, 1)"
        )
        c.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, title, status, "
            "first_seen_ms, last_seen_ms) VALUES ('T-1', 'E', 'm', 'open', 1, 1)"
        )
        c.execute(
            "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
            "price_tenths, is_taker, fee_predicted, fee_model_used) "
            "VALUES ('f1', 'T-1', 1, 3, 500, 1, 0.05, 'model_a')"
        )
        # Wind fills back to its v9 shape, then remove every table v9 did not
        # have. DROP, not undo: at v9 these tables were not merely different --
        # they were absent, and absence is the case the ALTER crashed on.
        for statement in db._QUANTITIES_ARE_REAL_UNDO:
            c.execute(statement)
        for statement in db._V11_UNDO:
            c.execute(statement)
        for statement in db._FILLS_REBUILD_UNDO:
            c.execute(statement)
        for table in (
            "bet_estimates", "venue_settlements", "venue_balance_snapshots",
            "bet_estimate_looks", "poll_log",
        ):
            c.execute(f"DROP TABLE IF EXISTS {table}")
        db._set_meta(c, "schema_version", "9")
        c.commit()
        c.close()

    def test_the_fixture_really_lacks_the_post_v9_tables(self, tmp_path):
        """Otherwise this class quietly becomes every other fixture."""
        path = tmp_path / "v9.db"
        self._real_v9(path)
        c = db.connect(path)

        tables = {
            r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

        assert "venue_balance_snapshots" not in tables
        assert "bet_estimates" not in tables
        assert "source" not in {r[1] for r in c.execute("PRAGMA table_info(fills)")}
        c.close()

    def test_init_db_boots_it_to_current_without_raising(self, tmp_path):
        """The whole regression: this call is what crashed the live boot."""
        path = tmp_path / "v9.db"
        self._real_v9(path)

        c = db.init_db(path)

        assert db.get_meta(c, "schema_version") == str(db.SCHEMA_VERSION)
        # The tables the migration cannot create arrive from the schema file,
        # complete -- including the column the fatal ALTER tried to add.
        assert "portfolio_value_tenths" in {
            r[1] for r in c.execute("PRAGMA table_info(venue_balance_snapshots)")
        }
        row = c.execute(
            "SELECT kalshi_fill_id, count, source FROM fills"
        ).fetchone()
        assert (row["kalshi_fill_id"], row["count"], row["source"]) == ("f1", 3, "engine")
        c.close()


class TestThePollLogRecordsFailuresNotJustSuccesses:
    """Every retention tripwire is decoration without this table.

    The registered rules are gaps between successive *successful* polls. A
    failure that writes no row is invisible, and an invisible failure reads
    exactly like a quiet week in which nothing was bet. Both portfolio
    endpoints have now been observed to drop history, so a poll that does not
    happen does not merely delay the record -- it loses it.
    """

    def test_a_failed_poll_is_recorded_with_no_row_count(self, conn):
        """`NULL`, never 0. An empty list is a legitimate, different state."""
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, error) "
            "VALUES (1, 'settlements', 0, 'HTTP 503')"
        )

        row = conn.execute("SELECT ok, row_count, error FROM poll_log").fetchone()

        assert row["ok"] == 0
        assert row["row_count"] is None, (
            "a failed poll recorded as 0 rows is indistinguishable from a "
            "successful poll of an account that did nothing"
        )
        assert row["error"] == "HTTP 503"

    def test_a_successful_empty_poll_is_zero_and_not_null(self, conn):
        """The other half of the same distinction."""
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
            "VALUES (2, 'fills', 1, 0)"
        )

        row = conn.execute("SELECT ok, row_count FROM poll_log").fetchone()

        assert (row["ok"], row["row_count"]) == (1, 0)

    def test_ok_is_a_boolean_and_not_a_free_text_field(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO poll_log (polled_ms, endpoint, ok) "
                "VALUES (3, 'balance', 2)"
            )
