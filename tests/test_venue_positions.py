"""The venue's open positions are mirrored, not counted and discarded.

Until schema v33 `portfolio_poll.poll_positions` fetched every open position
from `/portfolio/positions`, wrote `len(rows)` into `poll_log.row_count`, and
threw the rows away. The desk could say "Open now: 3 positions" and could not
say what those three had cost: `bets.open_positions` served an unconditional
refusal where the money figure belonged (ADR 0101 section 2.3, its third
reason -- "the venue's own per-position figure is not stored").

The per-row shape was captured on the production account on 2026-08-30
(`tests/test_rest.py::OBSERVED_POSITION_ROW`: real field names and types,
synthetic values), which is the ordering rule from `tasks/lessons.md`
satisfied. Every wire-shape test below builds on that row and never on a
hand-invented one.

What this establishes
---------------------
That the table exists on a fresh database and lands on a volume one version
behind together with the `poll_log.mirrored` marker, which is a column step;
that the venue's strings are stored verbatim and the derived columns are NULL
-- never 0 -- when a value will not parse, or when the exposure exceeds $1 a
contract (the scale tripwire that stands in for a unit nobody has measured);
that a successful poll writes its full row set under the poll's own stamp,
marks that poll, and leaves the count in `poll_log.row_count` untouched; that
the writer bounds its own table; that `bets.open_positions` serves the count
and the staked figure from ONE read with ONE stamp, selects only a poll that
KEPT its rows -- so the hand-bet path's bare `poll_log` stamp, a live second
writer, can neither displace that read nor darken the figure -- refuses on a
stale poll with the clock kept, refuses rather than partially sums when a row
is unreadable, and serves an empty-but-fresh snapshot as count 0 and $0.00;
that `gate.py` cannot see the table; and that the capture script no longer
overwrites an observation.

What it does NOT establish
--------------------------
The unit of `market_exposure_dollars` (the tripwire bounds a scale error; it
measures nothing); whether the field includes fees; anything about
`event_positions`; how the venue's `count_filter` treats a row that flips to
zero mid-session; that the screen renders the figure (lane A2); and that the
hand-bet route keeps its own rows -- it does not, that edit is `routes.py`'s
and deferred, and the tests below reproduce its write through the same
`log_poll_attempt` it calls rather than through the route. Nothing here reads
the live database: every row is synthetic in the observed shape.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from backend import bets, portfolio_poll
from backend.portfolio_poll import (
    VENUE_POSITIONS_RETENTION_MS,
    log_poll_attempt,
    parse_position,
    poll_positions,
    store_positions_snapshot,
)
from backend.store import db
from tests.test_rest import OBSERVED_POSITION_ROW

ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    """`positions()` only -- the one endpoint under test here."""

    def __init__(self, positions=None, *, fail: bool = False):
        self._positions = positions if positions is not None else []
        self._fail = fail

    async def positions(self):
        if self._fail:
            raise RuntimeError("boom positions")
        return self._positions


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "positions.db")
    yield c
    c.close()


def _poll(
    conn, *, polled_ms: int, row_count=0, ok: bool = True, mirrored=None
) -> int:
    """A `poll_log` row for the positions endpoint; returns its id.

    `mirrored` is NULL by default -- the shape of every row written before
    v33 and of the hand-bet path's stamp -- and 1 only when a test wants the
    hand-edited shape of a marked poll with rows missing under it."""
    cursor = conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count, mirrored) "
        "VALUES (?, 'positions', ?, ?, ?)",
        (polled_ms, 1 if ok else 0, row_count, mirrored),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _columns(conn, table: str) -> set:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


class TestTheSchemaCarriesTheMirror:
    def test_a_fresh_database_has_the_table_and_the_marker(self, conn):
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "venue_positions" in names
        assert "mirrored" in _columns(conn, "poll_log")

    def test_the_previous_version_gains_both_on_its_next_boot(self, tmp_path):
        """The table needs no step: `init_db` applies `schema.sql` with
        `CREATE TABLE IF NOT EXISTS` on every open. The marker column does,
        because `poll_log` already holds rows on the live volume and the file
        alone would never reach them -- so v33 is a `_MIGRATIONS` entry, and
        this test winds a database back to the version before it (table
        dropped, column dropped, stamp decremented) and reopens.

        **The version is 32, typed, and that is a correction made 2026-09-05.**
        It read `SCHEMA_VERSION - 1`, citing `test_hedge_positions`' reason
        for doing the same -- but the two tests make different claims and only
        one of them survives the relative form. That one asserts a **tableless**
        version: `CREATE TABLE IF NOT EXISTS` in `schema.sql` reaches an older
        database on any open, so its claim holds from every prior version and
        `SCHEMA_VERSION - 1` is as good as any. This one asserts a **column
        step**: `poll_log.mirrored` exists only because migration 33 runs, and
        winding back to `SCHEMA_VERSION - 1` stops meaning "before v33" the
        moment a v34 exists -- which it now does. It went red on that addition,
        having silently retargeted to a migration whose effects it does not
        assert.

        So: a test about a specific migration pins that migration's own
        predecessor. A relative version is only safe for a claim that is true
        of every version."""
        path = tmp_path / "previous.db"
        connection = db.init_db(path)
        connection.execute("DROP TABLE venue_positions")
        connection.execute("ALTER TABLE poll_log DROP COLUMN mirrored")
        db._set_meta(connection, "schema_version", "32")
        connection.commit()
        connection.close()

        reopened = db.init_db(path)
        try:
            names = {
                row[0]
                for row in reopened.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert "venue_positions" in names
            assert "mirrored" in _columns(reopened, "poll_log")
            assert db.get_meta(reopened, "schema_version") == str(
                db.SCHEMA_VERSION
            )
        finally:
            reopened.close()

    def test_v33_is_a_column_step_for_the_marker_not_a_tableless_version(self):
        """It adds a table AND a column; a version is one kind or the other,
        and a column on a table holding live rows makes it a step."""
        assert 33 not in db._TABLELESS_VERSIONS
        assert db._MIGRATIONS[33].columns == (
            ("poll_log", "mirrored", "INTEGER CHECK (mirrored IS NULL OR mirrored = 1)"),
        )
        assert db._MIGRATIONS[33].statements == ()
        assert db._MIGRATIONS[33].indexes == ()

    def test_the_marker_has_one_spelling(self, conn):
        """1 or NULL. A 0 would be a second spelling of "not mirrored" and
        the reader's `mirrored = 1` would treat it the same -- which is
        exactly how a second spelling survives unnoticed. The CHECK refuses
        it at the write."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO poll_log (polled_ms, endpoint, ok, mirrored) "
                "VALUES (1, 'positions', 1, 0)"
            )
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, mirrored) "
            "VALUES (1, 'positions', 1, 1)"
        )
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, mirrored) "
            "VALUES (1, 'positions', 1, NULL)"
        )

    def test_a_row_must_name_the_poll_it_came_from(self, conn):
        """One stamp: a mirror row that points at no `poll_log` row could be
        read beside a count it did not come from. `PRAGMA foreign_keys = ON`
        is what makes the REFERENCES clause bind."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO venue_positions (poll_log_id, polled_ms, ticker) "
                "VALUES (999, 1, 'KXT')"
            )

    @pytest.mark.parametrize(
        "column, value",
        [("exposure_tenths", -1), ("contracts", -0.5), ("side", "'maybe'")],
    )
    def test_the_derived_columns_refuse_what_they_cannot_mean(
        self, conn, column, value
    ):
        """Exposure at cost is money in and cannot be negative; a quantity
        is unsigned once the side is split off; a side is yes or no. The
        parser leaves each NULL when unreadable, and the CHECK is what stops a
        different writer from storing a value the reader would sum."""
        poll_id = _poll(conn, polled_ms=1)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO venue_positions (poll_log_id, polled_ms, {column}) "
                f"VALUES (?, 1, {value})",
                (poll_id,),
            )


class TestTheObservedRowParsesIntoNamedUnits:
    """Every row here is `OBSERVED_POSITION_ROW` or a one-field variation of
    it -- the 2026-08-30 capture's field names and types, never a shape
    invented for the test."""

    def test_the_observed_row_lands_verbatim_with_its_units_named(self):
        parsed = parse_position(OBSERVED_POSITION_ROW)
        assert parsed.ticker == "KXMLBGAME-26AUG30TEST-AAA"
        assert parsed.exchange_index == 1
        # Verbatim: the wire strings, character for character.
        assert parsed.position_fp == "22.88"
        assert parsed.market_exposure_dollars == "7.641920"
        assert parsed.total_traded_dollars == "7.641920"
        assert parsed.fees_paid_dollars == "0.070000"
        assert parsed.realized_pnl_dollars == "0.000000"
        assert parsed.last_updated_ts == "2026-08-30T02:01:05.541282Z"
        # Derived: "7.641920" dollars is 7641.92 tenths -> 7642 on the grid.
        assert parsed.exposure_tenths == 7642
        assert parsed.contracts == pytest.approx(22.88)
        assert parsed.side == "yes"

    def test_exposure_rounds_to_the_tenth_grid_half_up(self):
        """Fractional contracts make sub-tenth exposures real. The rounding
        is the wallet's one rule (`dollars_to_tenths`, ROUND_HALF_UP), so a
        half-tenth goes up and the column is within +-0.05 tenths of the
        exact figure -- never a whole cent off."""
        exact_half = dict(OBSERVED_POSITION_ROW, market_exposure_dollars="0.000500")
        assert parse_position(exact_half).exposure_tenths == 1
        just_under = dict(OBSERVED_POSITION_ROW, market_exposure_dollars="0.000499")
        assert parse_position(just_under).exposure_tenths == 0

    def test_a_no_side_position_keeps_its_sign_as_the_side(self):
        """`position_fp` negative is a NO holding per the venue's convention;
        the magnitude is the count. A parser that dropped the sign would
        record a short as a long."""
        short = dict(OBSERVED_POSITION_ROW, position_fp="-3.50")
        parsed = parse_position(short)
        assert parsed.side == "no"
        assert parsed.contracts == pytest.approx(3.5)
        assert parsed.position_fp == "-3.50"

    def test_the_quantity_is_decimal_never_int(self):
        """`int("22.88")` raises and `int(22.88)` truncates; the parser goes
        through `parse_position_fp`, which is Decimal. Pinned by the value a
        truncation would produce."""
        assert parse_position(OBSERVED_POSITION_ROW).contracts != 22
        assert Decimal(str(parse_position(OBSERVED_POSITION_ROW).contracts)) == (
            Decimal("22.88")
        )

    @pytest.mark.parametrize(
        "junk", [None, "", "not money", "nan", "Infinity", True, {"a": 1}]
    )
    def test_an_unreadable_exposure_is_none_never_zero(self, junk):
        parsed = parse_position(
            dict(OBSERVED_POSITION_ROW, market_exposure_dollars=junk)
        )
        assert parsed.exposure_tenths is None
        # And the rest of the row is untouched by one bad field.
        assert parsed.ticker == OBSERVED_POSITION_ROW["ticker"]
        assert parsed.contracts == pytest.approx(22.88)

    def test_a_negative_exposure_is_refused_not_absoluted(self):
        """Whether the venue signs a NO-side exposure has never been
        observed. `abs()` would be a guess wearing a number; the column is
        NULL and the verbatim text keeps the sign for the day it is pinned."""
        parsed = parse_position(
            dict(OBSERVED_POSITION_ROW, market_exposure_dollars="-7.641920")
        )
        assert parsed.exposure_tenths is None
        assert parsed.market_exposure_dollars == "-7.641920"

    def test_an_exposure_above_a_dollar_a_contract_is_a_scale_error_not_a_stake(
        self,
    ):
        """The unit of `market_exposure_dollars` is inferred from its suffix
        and has never been measured against a known position. The tripwire
        that stands in: a contract cannot cost more than $1, so the exposure
        cannot exceed the contract count in dollars. A cents-with-decimals
        field on the observed row would read 764.192000 -- 764192 tenths
        against a ceiling of 22880 -- and without this the strip would
        render the stake at 100x. Refused to None, never scaled down, the
        text kept, the reason named."""
        cents_scaled = dict(
            OBSERVED_POSITION_ROW, market_exposure_dollars="764.192000"
        )
        parsed = parse_position(cents_scaled)
        assert parsed.exposure_tenths is None
        assert parsed.market_exposure_dollars == "764.192000"
        assert parsed.contracts == pytest.approx(22.88)
        assert "exceeds $1 a contract" in parsed.exposure_refusal
        assert "22880" in parsed.exposure_refusal, "the ceiling is named"
        # And the observed row itself is inside the bound, with no reason.
        assert parse_position(OBSERVED_POSITION_ROW).exposure_refusal is None

    def test_exactly_a_dollar_a_contract_is_inside_the_bound(self):
        """The bound is `<=`, and both sides go through the same
        `dollars_to_tenths`, so the two roundings are one rounding: a true
        $1 a contract lands equal and is not refused. The tripwire catches a
        scale error; it cannot tell cost from a payout at exactly $1, and
        does not claim to."""
        at_the_edge = dict(
            OBSERVED_POSITION_ROW, market_exposure_dollars="22.880000"
        )
        assert parse_position(at_the_edge).exposure_tenths == 22880
        assert parse_position(at_the_edge).exposure_refusal is None
        # "22.880100" is 22880.1 tenths and rounds back onto the ceiling;
        # one whole tenth over is "22.881000" -> 22881 > 22880.
        one_tenth_over = dict(
            OBSERVED_POSITION_ROW, market_exposure_dollars="22.881000"
        )
        assert parse_position(one_tenth_over).exposure_tenths is None
        assert parse_position(
            dict(OBSERVED_POSITION_ROW, market_exposure_dollars="22.880100")
        ).exposure_tenths == 22880, "sub-tenth over the edge rounds onto it"

    def test_the_ceiling_shares_the_exposures_rounding_at_the_grid_edge(self):
        """A fractional position of 0.0005 contracts: the ceiling rounds
        half-up to 1 tenth exactly as an exposure of "0.000500" does, so an
        exposure equal to the position's worth is not refused by a rounding
        asymmetry, and one that rounds to 2 tenths is."""
        tiny = dict(
            OBSERVED_POSITION_ROW,
            position_fp="0.0005",
            market_exposure_dollars="0.000500",
        )
        assert parse_position(tiny).exposure_tenths == 1
        assert parse_position(tiny).exposure_refusal is None
        over = dict(tiny, market_exposure_dollars="0.001500")
        assert parse_position(over).exposure_tenths is None

    def test_a_no_side_row_is_bounded_by_its_magnitude(self):
        """The sign is the side; the bound is on the count, which is the
        magnitude. A short 3.50 contracts can have cost at most $3.50."""
        short = dict(
            OBSERVED_POSITION_ROW,
            position_fp="-3.50",
            market_exposure_dollars="3.500000",
        )
        assert parse_position(short).exposure_tenths == 3500
        over = dict(short, market_exposure_dollars="3.501000")
        assert parse_position(over).exposure_tenths is None
        assert parse_position(over).side == "no"

    def test_a_plain_parse_failure_names_itself_too(self):
        parsed = parse_position(
            dict(OBSERVED_POSITION_ROW, market_exposure_dollars="seven")
        )
        assert parsed.exposure_tenths is None
        assert "did not parse" in parsed.exposure_refusal

    def test_an_unreadable_quantity_leaves_count_and_side_none(self):
        parsed = parse_position(dict(OBSERVED_POSITION_ROW, position_fp="lots"))
        assert parsed.contracts is None
        assert parsed.side is None
        assert parsed.position_fp == "lots"
        # The exposure is its own field and still parses. With no readable
        # quantity there is no ceiling to state, so the tripwire does not
        # fire -- it bounds a scale error, it does not invent a bound.
        assert parsed.exposure_tenths == 7642
        assert parsed.exposure_refusal is None

    def test_a_zero_quantity_has_no_side(self):
        parsed = parse_position(dict(OBSERVED_POSITION_ROW, position_fp="0.00"))
        assert parsed.contracts == 0.0
        assert parsed.side is None

    def test_a_non_string_wire_value_is_kept_as_its_json(self):
        """Verbatim means the venue's representation survives whatever type
        it arrives in: an integer, a bool and an object are all recoverable
        from their JSON, and `None` stays `None` rather than the text 'null'."""
        parsed = parse_position(
            dict(OBSERVED_POSITION_ROW, position_fp=3, last_updated_ts=None)
        )
        assert parsed.position_fp == "3"
        assert parsed.contracts == 3.0
        assert parsed.last_updated_ts is None

    def test_exchange_index_is_an_integer_or_nothing(self):
        assert parse_position(dict(OBSERVED_POSITION_ROW, exchange_index="1")).exchange_index is None
        assert parse_position(dict(OBSERVED_POSITION_ROW, exchange_index=True)).exchange_index is None
        assert parse_position(OBSERVED_POSITION_ROW).exchange_index == 1


class TestThePollerStoresWhatItCounts:
    async def test_a_successful_poll_writes_every_row_under_its_own_stamp(
        self, conn
    ):
        second = dict(OBSERVED_POSITION_ROW, ticker="KXMLBGAME-26AUG30TEST-BBB")
        summary = await poll_positions(
            conn, FakeClient([OBSERVED_POSITION_ROW, second]), now_ms=4_242
        )
        conn.commit()

        assert summary == {"seen": 2, "stored": 2, "exposure_unreadable": 0}
        log = conn.execute(
            "SELECT id, ok, row_count FROM poll_log WHERE endpoint = 'positions'"
        ).fetchone()
        assert (log["ok"], log["row_count"]) == (1, 2), (
            "poll_log.row_count is still written, unchanged, from len(rows)"
        )
        rows = conn.execute(
            "SELECT poll_log_id, polled_ms, ticker, exposure_tenths, "
            "position_fp, side FROM venue_positions ORDER BY id"
        ).fetchall()
        assert [tuple(r) for r in rows] == [
            (log["id"], 4_242, "KXMLBGAME-26AUG30TEST-AAA", 7642, "22.88", "yes"),
            (log["id"], 4_242, "KXMLBGAME-26AUG30TEST-BBB", 7642, "22.88", "yes"),
        ]

    async def test_a_failed_poll_leaves_the_previous_snapshot_as_the_newest(
        self, conn
    ):
        await poll_positions(conn, FakeClient([OBSERVED_POSITION_ROW]), now_ms=1)
        conn.commit()
        result = await poll_positions(conn, FakeClient(fail=True), now_ms=2)
        conn.commit()

        assert str(result).startswith("FAILED:")
        assert conn.execute(
            "SELECT COUNT(*) FROM venue_positions"
        ).fetchone()[0] == 1
        failed = conn.execute(
            "SELECT ok, row_count FROM poll_log WHERE polled_ms = 2"
        ).fetchone()
        assert (failed["ok"], failed["row_count"]) == (0, None)

    async def test_an_empty_list_is_a_snapshot_with_no_rows_not_no_snapshot(
        self, conn
    ):
        """Zero open positions is a real state (the 2026-09-05 capture found
        exactly that) and must be distinguishable from a poll that never
        happened: the `poll_log` row says 0 and the mirror has nothing under
        it, which the reader serves as count 0 and $0.00."""
        summary = await poll_positions(conn, FakeClient([]), now_ms=7)
        conn.commit()
        assert summary == {"seen": 0, "stored": 0, "exposure_unreadable": 0}
        assert conn.execute(
            "SELECT row_count FROM poll_log WHERE endpoint = 'positions'"
        ).fetchone()[0] == 0

    async def test_an_unreadable_row_is_stored_with_its_text_and_a_null(
        self, conn, caplog
    ):
        """Refuse the figure, keep the record, say so. Never 0."""
        bad = dict(OBSERVED_POSITION_ROW, market_exposure_dollars="seven")
        with caplog.at_level(logging.WARNING, logger="backend.portfolio_poll"):
            summary = await poll_positions(conn, FakeClient([bad]), now_ms=9)
        conn.commit()

        assert summary == {"seen": 1, "stored": 1, "exposure_unreadable": 1}
        row = conn.execute(
            "SELECT market_exposure_dollars, exposure_tenths FROM venue_positions"
        ).fetchone()
        assert tuple(row) == ("seven", None)
        assert any(
            "did not parse" in rec.getMessage() for rec in caplog.records
        ), "an unreadable exposure must be logged, not silently NULLed"

    async def test_a_scale_tripped_row_is_stored_logged_and_refused_downstream(
        self, conn, caplog
    ):
        """The tripwire's whole path: the writer keeps the text, NULLs the
        derived column, counts it under `exposure_unreadable`, logs the
        parser's own reason rather than "did not parse" for a value that
        parsed fine -- and the reader refuses the sum in words, never 100x."""
        cents_scaled = dict(
            OBSERVED_POSITION_ROW, market_exposure_dollars="764.192000"
        )
        with caplog.at_level(logging.WARNING, logger="backend.portfolio_poll"):
            summary = await poll_positions(
                conn, FakeClient([cents_scaled]), now_ms=NOW_MS - 10_000
            )
        conn.commit()

        assert summary == {"seen": 1, "stored": 1, "exposure_unreadable": 1}
        row = conn.execute(
            "SELECT market_exposure_dollars, exposure_tenths, contracts "
            "FROM venue_positions"
        ).fetchone()
        assert tuple(row) == ("764.192000", None, pytest.approx(22.88))
        assert any(
            "exceeds $1 a contract" in rec.getMessage() for rec in caplog.records
        ), "the log names the scale tripwire, not a parse failure"

        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert block["count"] == 1
        assert block["staked_tenths"] is None
        assert block["staked_refusal"] == bets.STAKED_ROW_UNREADABLE

    async def test_the_writer_bounds_its_own_table(self, conn):
        """Rows older than the retention window go in the same transaction as
        the snapshot that displaces them; the newest snapshot never does."""
        old = 1_000
        await poll_positions(conn, FakeClient([OBSERVED_POSITION_ROW]), now_ms=old)
        conn.commit()
        inside = old + VENUE_POSITIONS_RETENTION_MS - 1
        await poll_positions(
            conn, FakeClient([OBSERVED_POSITION_ROW]), now_ms=inside
        )
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM venue_positions"
        ).fetchone()[0] == 2, "inside the window nothing is deleted"

        past = old + VENUE_POSITIONS_RETENTION_MS + 1
        await poll_positions(conn, FakeClient([OBSERVED_POSITION_ROW]), now_ms=past)
        conn.commit()
        stamps = [
            r[0] for r in conn.execute(
                "SELECT polled_ms FROM venue_positions ORDER BY polled_ms"
            )
        ]
        assert stamps == [inside, past], (
            "the row past the window is gone; the two inside it stay"
        )

    async def test_the_poller_writes_but_does_not_commit(self, conn):
        """The seam `poll_portfolio` and the fast branch depend on: the
        caller commits, so a positions write is inside the caller's
        transaction and a rollback takes the mirror rows with the log row."""
        await poll_positions(conn, FakeClient([OBSERVED_POSITION_ROW]), now_ms=3)
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM venue_positions").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM poll_log WHERE endpoint = 'positions'"
        ).fetchone()[0] == 0

    async def test_the_never_captured_warning_is_gone(self, conn, caplog):
        """Until v33 a successful poll with rows logged *"the per-row shape
        has never been captured"* -- false since 2026-08-30. Pinned absent
        over the log AND the source, so the sentence cannot come back as a
        comment either."""
        with caplog.at_level(logging.WARNING, logger="backend.portfolio_poll"):
            await poll_positions(
                conn, FakeClient([OBSERVED_POSITION_ROW]), now_ms=1
            )
        assert not [r for r in caplog.records if "never" in r.getMessage()]
        source = (ROOT / "backend" / "portfolio_poll.py").read_text(
            encoding="utf-8"
        )
        assert "has never been captured" not in source
        assert "capture_fills_fixture.py-style" not in source

    def test_the_retention_window_serves_the_only_reader(self):
        """The reader takes the newest poll and refuses past 30 minutes; the
        window must exceed that bound or a fresh snapshot could be pruned
        from under it. Read from the constants, not typed."""
        from backend.bets import TONIGHT_STALE_AFTER_MS

        assert VENUE_POSITIONS_RETENTION_MS > TONIGHT_STALE_AFTER_MS
        assert VENUE_POSITIONS_RETENTION_MS == 7 * 24 * 3600 * 1000
        assert portfolio_poll.VENUE_POSITIONS_RETENTION_MS is VENUE_POSITIONS_RETENTION_MS


NOW_MS = 1_786_651_200_000  # 2026-08-09T20:00:00Z, arbitrary but on-hour
EXPOSURE_TENTHS = 7642  # "7.641920" dollars on the tenth grid


async def _mirror(conn, rows, *, at_ms: int):
    """Populate through the REAL writer, so the reader is tested against what
    the poller actually stores rather than against rows typed to match it."""
    await poll_positions(conn, FakeClient(rows), now_ms=at_ms)
    conn.commit()


class TestTheReaderServesOneReadWithOneStamp:
    """`bets.open_positions` after v33: the count is still `poll_log.row_count`
    and the staked figure is the sum of `exposure_tenths` over the rows
    stamped with that same poll -- one read, one stamp (`count_as_of_ms`).

    Every refusal is words; a refused figure is `None` and never 0.
    """

    async def test_a_fresh_snapshot_serves_count_and_staked_together(self, conn):
        second = dict(OBSERVED_POSITION_ROW, ticker="KXMLBGAME-26AUG30TEST-BBB")
        await _mirror(conn, [OBSERVED_POSITION_ROW, second], at_ms=NOW_MS - 240_000)

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] == 2
        assert block["staked_tenths"] == 2 * EXPOSURE_TENTHS
        assert block["staked_display"] == "$15.28"
        assert block["staked_refusal"] is None
        assert block["count_as_of_ms"] == NOW_MS - 240_000
        assert block["count_age_ms"] == 240_000
        assert "staked_as_of_ms" not in block, (
            "one read, one stamp: the staked figure wears count_as_of_ms"
        )

    async def test_a_stale_snapshot_refuses_both_and_keeps_the_clock(self, conn):
        stale = NOW_MS - bets.TONIGHT_STALE_AFTER_MS - 60_000
        await _mirror(conn, [OBSERVED_POSITION_ROW], at_ms=stale)

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] is None
        assert block["staked_tenths"] is None
        assert block["staked_display"] is None
        assert block["staked_refusal"] == bets.STAKED_NOT_READ
        assert block["count_as_of_ms"] == stale, "the clock stays for 'since'"

    async def test_an_empty_but_fresh_snapshot_is_zero_and_zero(self, conn):
        """Both from the same successful read seconds ago: the venue said it
        holds nothing and the count says the same in the same breath. This
        is not the `$0.00`-beside-a-non-zero-count false negative the
        component guards against; the count is 0 too."""
        await _mirror(conn, [], at_ms=NOW_MS - 10_000)

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] == 0
        assert block["staked_tenths"] == 0
        assert block["staked_display"] == "$0.00"
        assert block["staked_refusal"] is None

    async def test_one_unreadable_row_refuses_the_whole_figure_not_a_partial(
        self, conn
    ):
        """A sum over the readable rows is a false low. The count is still
        served -- it is readable and from the same read -- and the money
        figure refuses in words. Never the other row's 7642."""
        bad = dict(OBSERVED_POSITION_ROW, market_exposure_dollars="seven")
        await _mirror(conn, [OBSERVED_POSITION_ROW, bad], at_ms=NOW_MS - 10_000)

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] == 2
        assert block["staked_tenths"] is None
        assert block["staked_display"] is None
        assert block["staked_refusal"] == bets.STAKED_ROW_UNREADABLE

    async def test_a_marked_poll_missing_rows_refuses_naming_both_numbers(
        self, conn
    ):
        """The mismatch is an integrity refusal now: a poll that says it kept
        its rows and holds fewer than it counted. Built by deleting one row
        from under a real snapshot -- the only way to reach it since the
        marker, because the writer marks and writes in one transaction. The
        count is served (it is readable and from that read); the money
        refuses with both numbers so the mismatch is legible."""
        second = dict(OBSERVED_POSITION_ROW, ticker="KXMLBGAME-26AUG30TEST-BBB")
        third = dict(OBSERVED_POSITION_ROW, ticker="KXMLBGAME-26AUG30TEST-CCC")
        await _mirror(
            conn, [OBSERVED_POSITION_ROW, second, third], at_ms=NOW_MS - 10_000
        )
        conn.execute(
            "DELETE FROM venue_positions WHERE ticker = 'KXMLBGAME-26AUG30TEST-CCC'"
        )
        conn.commit()

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] == 3
        assert block["staked_tenths"] is None
        assert block["staked_refusal"] == bets.STAKED_MIRROR_MISMATCH.format(
            count=3, rows=2
        )

    def test_never_polled_refuses_in_words_with_no_clock(self, conn):
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert block["count"] is None
        assert block["count_as_of_ms"] is None
        assert block["staked_tenths"] is None
        assert block["staked_refusal"] == bets.STAKED_NEVER_POLLED

    def test_a_failed_poll_alone_is_never_polled(self, conn):
        _poll(conn, polled_ms=NOW_MS - 10_000, row_count=None, ok=False)
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert block["count"] is None
        assert block["staked_refusal"] == bets.STAKED_NEVER_POLLED

    async def test_a_failed_newer_poll_leaves_the_last_good_snapshot_serving(
        self, conn
    ):
        """The failure leaves its `poll_log` row and no mirror rows; the
        reader takes the newest SUCCESSFUL poll and its own rows, so count
        and staked still agree and still wear that poll's stamp."""
        good = NOW_MS - 300_000
        await _mirror(conn, [OBSERVED_POSITION_ROW], at_ms=good)
        await poll_positions(conn, FakeClient(fail=True), now_ms=NOW_MS - 10_000)
        conn.commit()

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] == 1
        assert block["staked_tenths"] == EXPOSURE_TENTHS
        assert block["count_as_of_ms"] == good

    async def test_the_money_comes_from_the_same_poll_as_the_count(self, conn):
        """Two snapshots, different sizes. The figure must be the newer
        poll's sum over the newer poll's rows -- never the older rows, never
        all rows. Pinned by numbers that differ under every wrong join."""
        cheap = dict(OBSERVED_POSITION_ROW, market_exposure_dollars="1.000000")
        await _mirror(conn, [cheap], at_ms=NOW_MS - 600_000)
        await _mirror(
            conn,
            [OBSERVED_POSITION_ROW,
             dict(OBSERVED_POSITION_ROW, ticker="KXMLBGAME-26AUG30TEST-BBB")],
            at_ms=NOW_MS - 60_000,
        )

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] == 2
        assert block["staked_tenths"] == 2 * EXPOSURE_TENTHS
        assert block["staked_tenths"] != 1000, "not the older snapshot"
        assert block["staked_tenths"] != 1000 + 2 * EXPOSURE_TENTHS, (
            "not every row ever mirrored"
        )
        assert block["count_as_of_ms"] == NOW_MS - 60_000

    async def test_rows_are_keyed_by_the_poll_id_never_by_the_newest_rows(
        self, conn
    ):
        """A join on "the newest rows in the mirror" would serve an older
        snapshot under a newer poll's stamp whenever the newest poll has no
        rows of its own -- a money figure wearing a clock it did not come
        from, the exact lie `test_open_positions_stamp.py` was written for.
        The newer poll here is MARKED and empty -- a writer that set the mark
        without the rows -- so the reader must select it; keyed by id, its
        empty mirror is a mismatch, in words, and never the older 7642."""
        await _mirror(conn, [OBSERVED_POSITION_ROW], at_ms=NOW_MS - 120_000)
        _poll(conn, polled_ms=NOW_MS - 10_000, row_count=1, mirrored=1)

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count_as_of_ms"] == NOW_MS - 10_000
        assert block["staked_tenths"] is None, (
            "the older snapshot's 7642 must not be served under the newer stamp"
        )
        assert block["staked_refusal"] == bets.STAKED_MIRROR_MISMATCH.format(
            count=1, rows=0
        )

    async def test_the_value_keeps_its_own_stamp_and_is_untouched(self, conn):
        """`value_*` is exactly what it was: its own read, its own clock, its
        own refusals. A shared cadence is not a shared read."""
        await _mirror(conn, [OBSERVED_POSITION_ROW], at_ms=NOW_MS - 240_000)
        conn.execute(
            "INSERT INTO venue_balance_snapshots "
            "(observed_ms, balance_tenths, portfolio_value_tenths) "
            "VALUES (?, 2560, 0)",
            (NOW_MS - 90_000,),
        )
        conn.commit()

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["value_tenths"] == 0
        assert block["value_display"] == "$0.00"
        assert block["value_as_of_ms"] == NOW_MS - 90_000
        assert block["value_as_of_ms"] != block["count_as_of_ms"]
        assert block["staked_tenths"] == EXPOSURE_TENTHS

    async def test_the_payload_keys_are_the_frontend_contract_unchanged(
        self, conn
    ):
        await _mirror(conn, [OBSERVED_POSITION_ROW], at_ms=NOW_MS - 1_000)
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert set(block) == {
            "count", "count_as_of_ms", "count_age_ms", "value_tenths",
            "value_display", "value_as_of_ms", "value_age_ms",
            "value_refusal", "staked_tenths", "staked_display",
            "staked_refusal",
        }


class TestTheMarkerSaysWhichReadKeptItsRows:
    """`poll_log.mirrored` (v33). `poll_log` has two writers of positions
    reads: `poll_positions`, which keeps the rows, and
    `backend/api/routes.py::_stamp_positions_read`, the hand-bet path's own
    read on every `POST /api/manual-orders`, which logs through the same
    `log_poll_attempt` with a real `row_count` and keeps nothing. Before the
    marker the reader took the newest successful positions poll, found the
    route's stamp with N counted and 0 rows, and refused the money figure for
    up to five minutes after every hand bet -- silent when nothing was held
    (0 = 0), firing exactly in the state the figure exists for. An empty
    snapshot and an unmirrored stamp are both zero rows; only a marker tells
    them apart.

    The route's write is reproduced here through the same function it calls,
    with the same arguments, so the interaction is tested without the route:
    the route is `routes.py`'s and its own fix (keep the rows through
    `store_positions_snapshot`) was deferred to the integrator.

    Mutations run, red and restored byte-identical: `AND mirrored = 1`
    removed from the reader's selection -- the bare-stamp test fails with the
    mismatch refusal it was written to forbid, and the one-stamp-or-none test
    fails with the stamp's count served; the `UPDATE poll_log SET mirrored`
    removed from the writer -- every served-figure test in this file fails
    with `STAKED_NOT_MIRRORED`.
    """

    def test_log_poll_attempt_never_sets_the_mark(self, conn):
        """Exactly the route's write: `log_poll_attempt` with the positions
        endpoint, ok, and a real count. The mark is the snapshot writer's to
        set, after the rows, so a caller that logs a read has not claimed to
        have kept anything."""
        poll_id = log_poll_attempt(
            conn, now_ms=NOW_MS - 60_000, endpoint="positions", ok=True,
            row_count=2,
        )
        conn.commit()
        row = conn.execute(
            "SELECT mirrored, row_count FROM poll_log WHERE id = ?", (poll_id,)
        ).fetchone()
        assert tuple(row) == (None, 2)

    def test_the_snapshot_writer_marks_the_poll_even_when_it_is_empty(
        self, conn
    ):
        """Zero rows kept is a snapshot (the 2026-09-05 state of the live
        account); zero rows never kept is not. The mark is what separates
        them, so it must be set on an empty write too."""
        poll_id = log_poll_attempt(
            conn, now_ms=NOW_MS - 60_000, endpoint="positions", ok=True,
            row_count=0,
        )
        summary = store_positions_snapshot(
            conn, poll_log_id=poll_id, now_ms=NOW_MS - 60_000, rows=[]
        )
        conn.commit()
        assert summary == {"seen": 0, "stored": 0, "exposure_unreadable": 0}
        assert conn.execute(
            "SELECT mirrored FROM poll_log WHERE id = ?", (poll_id,)
        ).fetchone()[0] == 1

    async def test_the_hand_bet_paths_bare_stamp_does_not_darken_the_figure(
        self, conn
    ):
        """The finding, reproduced. The poller keeps two rows at T; sixty
        seconds later the hand-bet route stamps its own read (same function,
        same endpoint, same count -- pre-order, so the count is the poller's
        count). Before the marker the reader served "Open now: 2" beside
        "the poll counted 2 positions and the mirror holds 0 rows". Now it
        serves the poller's figure under the poller's stamp."""
        second = dict(OBSERVED_POSITION_ROW, ticker="KXMLBGAME-26AUG30TEST-BBB")
        await _mirror(conn, [OBSERVED_POSITION_ROW, second], at_ms=NOW_MS - 120_000)
        log_poll_attempt(
            conn, now_ms=NOW_MS - 60_000, endpoint="positions", ok=True,
            row_count=2,
        )
        conn.commit()

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] == 2
        assert block["staked_tenths"] == 2 * EXPOSURE_TENTHS
        assert block["staked_display"] == "$15.28"
        assert block["staked_refusal"] is None
        assert block["count_as_of_ms"] == NOW_MS - 120_000, (
            "the stamp is the read the rows came from, not the newer bare one"
        )

    async def test_the_count_and_the_money_wear_one_stamp_or_none(self, conn):
        """A bare stamp whose count DIFFERS from the poller's (a position
        settled between the two reads, say) is not served either: serving
        its 3 beside the poller's $15.28 would be two reads on one line,
        the divergence `test_open_positions_stamp.py` forbids. The poller's
        2 and $15.28 are served together, and the 3 waits for the poll that
        keeps its rows."""
        second = dict(OBSERVED_POSITION_ROW, ticker="KXMLBGAME-26AUG30TEST-BBB")
        await _mirror(conn, [OBSERVED_POSITION_ROW, second], at_ms=NOW_MS - 120_000)
        log_poll_attempt(
            conn, now_ms=NOW_MS - 60_000, endpoint="positions", ok=True,
            row_count=3,
        )
        conn.commit()

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert (block["count"], block["staked_tenths"]) == (2, 2 * EXPOSURE_TENTHS)
        assert block["count_as_of_ms"] == NOW_MS - 120_000

    def test_only_bare_stamps_refuse_as_not_mirrored_with_no_clock(self, conn):
        """A database whose every positions row is a bare stamp -- the
        minutes after v33 deploys, or a hand bet before the poller's first
        cycle. Neither figure is served off a bare row, so there is no clock
        to serve, and the words say a read was logged without its rows
        rather than that the venue was never asked."""
        log_poll_attempt(
            conn, now_ms=NOW_MS - 60_000, endpoint="positions", ok=True,
            row_count=2,
        )
        conn.commit()

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] is None
        assert block["count_as_of_ms"] is None
        assert block["count_age_ms"] is None
        assert block["staked_tenths"] is None
        assert block["staked_refusal"] == bets.STAKED_NOT_MIRRORED

    async def test_a_stale_snapshot_is_not_rescued_by_a_fresh_bare_stamp(
        self, conn
    ):
        """The poller has been down 40 minutes; Joe just bet by hand, so the
        route's stamp is 60 seconds old. The stamp must not make the dead
        poller's snapshot look fresh: the reader refuses on the SNAPSHOT's
        clock, which is the honest one."""
        stale = NOW_MS - bets.TONIGHT_STALE_AFTER_MS - 600_000
        await _mirror(conn, [OBSERVED_POSITION_ROW], at_ms=stale)
        log_poll_attempt(
            conn, now_ms=NOW_MS - 60_000, endpoint="positions", ok=True,
            row_count=1,
        )
        conn.commit()

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] is None
        assert block["count_as_of_ms"] == stale
        assert block["staked_refusal"] == bets.STAKED_NOT_READ

    def test_the_reader_selects_on_the_mark_by_name(self):
        """The source pin behind the executed ones: the selection names the
        marker, so a future rewrite of the query cannot drop it and pass on
        a database with no bare stamps in it."""
        source = (ROOT / "backend" / "bets.py").read_text(encoding="utf-8")
        assert "AND mirrored = 1" in source


class TestTheInterlockCannotSeeThisRecord:
    def test_gate_never_reads_venue_positions(self):
        """What Joe holds is his discretion, not evidence. The same boundary
        `manual_orders`, `parlay_positions` and `combo_orders` carry, pinned
        the same way: over the source of `backend/gate.py`, so a future join
        fails loudly rather than by convention."""
        source = (ROOT / "backend" / "gate.py").read_text(encoding="utf-8")
        assert "venue_positions" not in source


@pytest.fixture(scope="module")
def capture_script():
    """`scripts/capture_positions_fixture.py`, imported the way
    `test_capture_fills_fixture.py` imports its sibling. Importing it reaches
    no network; only `capture()` does, and every test here stubs the client."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import capture_positions_fixture as module

    return module


class _FrozenDatetime(datetime):
    """`datetime.now()` pinned to an instant the test chooses, advancing one
    second per call -- so a stamp taken once per run and a stamp taken per
    write produce different filenames, and the test can tell them apart."""

    _at: datetime
    _calls: int = 0

    @classmethod
    def start(cls, at: datetime) -> None:
        cls._at, cls._calls = at, 0

    @classmethod
    def now(cls, tz=None):
        value = cls._at + timedelta(seconds=cls._calls)
        cls._calls += 1
        return value if tz is None else value.astimezone(tz)


class TestTheCaptureScriptKeepsEveryObservation:
    """`scripts/capture_positions_fixture.py` wrote two FIXED filenames, and
    the 2026-09-05 run (exit 4: envelope confirmed, zero rows) overwrote the
    2026-08-30 capture -- the only observation of the per-row shape this
    account had produced. Every run now writes its own stamped pair, and a
    second run leaves the first one's files exactly as they were.

    What this does NOT establish: anything about the venue. The client is a
    stub returning an envelope built on `OBSERVED_POSITION_ROW`; the JSON the
    script writes around it is what is under test.

    Mutations run, red and restored byte-identical: `capture_path` returning
    the old fixed name (the two-runs and the stamped-pair tests red);
    `run_at` taken once per `_write` call (the shared-stamp assertion red
    when the clock moves between the two writes); the old `OUT_BARE`
    constant reinstated (the source pin red).
    """

    def test_a_filename_carries_the_kind_and_a_utc_second_stamp(
        self, capture_script
    ):
        at = datetime(2026, 9, 5, 4, 12, 33, 500_000, tzinfo=timezone.utc)
        path = capture_script.capture_path("bare", at)
        assert path.parent == capture_script.CAPTURES
        assert path.name == "portfolio_positions_bare_20260905T041233Z.json"
        assert capture_script.capture_path("count_filter", at).name == (
            "portfolio_positions_count_filter_20260905T041233Z.json"
        )

    def test_the_stamp_is_utc_whatever_zone_the_clock_is_in(self, capture_script):
        """A stamp in local time would sort two captures a day apart into
        the wrong order across a zone change; UTC is the one ordering."""
        eastern = timezone(timedelta(hours=-4))
        local = datetime(2026, 9, 5, 0, 12, 33, tzinfo=eastern)
        assert capture_script.capture_path("bare", local).name.endswith(
            "_20260905T041233Z.json"
        )

    def test_the_captures_directory_is_still_the_gitignored_one(
        self, capture_script
    ):
        """`data/` is ignored wholesale (`.gitignore`); a stamped filename
        must not have moved the output somewhere a push would publish."""
        assert capture_script.CAPTURES == ROOT / "data" / "captures"
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert "data/" in ignored

    def _stub_venue(self, capture_script, monkeypatch, tmp_path, envelope):
        class FakeApi:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, path, **params):
                return json.loads(json.dumps(envelope))

        class FakeConfig:
            @staticmethod
            def load():
                return object()

        monkeypatch.setattr(capture_script, "KalshiConfig", FakeConfig)
        monkeypatch.setattr(
            capture_script, "KalshiRestClient", lambda config: FakeApi()
        )
        monkeypatch.setattr(capture_script, "CAPTURES", tmp_path)
        monkeypatch.setattr(capture_script, "configure_logging", lambda: None)
        monkeypatch.setattr(capture_script, "datetime", _FrozenDatetime)

    async def test_a_run_writes_a_stamped_pair_and_the_envelope_verbatim(
        self, capture_script, tmp_path, monkeypatch
    ):
        envelope = {
            "cursor": "",
            "event_positions": [],
            "market_positions": [OBSERVED_POSITION_ROW],
        }
        self._stub_venue(capture_script, monkeypatch, tmp_path, envelope)
        _FrozenDatetime.start(datetime(2026, 8, 30, 2, 1, 5, tzinfo=timezone.utc))

        code = await capture_script.capture()

        assert code == capture_script.EXIT_OK
        names = sorted(p.name for p in tmp_path.iterdir())
        assert names == [
            "portfolio_positions_bare_20260830T020105Z.json",
            "portfolio_positions_count_filter_20260830T020105Z.json",
        ], "one stamp per run, taken as the run begins -- not one per write"
        written = json.loads((tmp_path / names[0]).read_text(encoding="utf-8"))
        assert written["payload"] == envelope, "verbatim, not redacted"
        assert written["record_count"] == 1
        assert written["params"] == {}
        filtered = json.loads((tmp_path / names[1]).read_text(encoding="utf-8"))
        assert filtered["params"] == {"count_filter": "position"}

    async def test_a_second_run_leaves_the_first_capture_untouched(
        self, capture_script, tmp_path, monkeypatch
    ):
        """The defect itself: the 2026-09-05 run destroyed the 2026-08-30
        one. Two runs, the second empty, and the first pair's bytes are
        exactly what they were."""
        with_rows = {
            "cursor": "",
            "event_positions": [],
            "market_positions": [OBSERVED_POSITION_ROW],
        }
        self._stub_venue(capture_script, monkeypatch, tmp_path, with_rows)
        _FrozenDatetime.start(datetime(2026, 8, 30, 2, 1, 5, tzinfo=timezone.utc))
        assert await capture_script.capture() == capture_script.EXIT_OK
        first = {
            p.name: p.read_bytes() for p in tmp_path.iterdir()
        }
        assert len(first) == 2

        empty = {"cursor": "", "event_positions": [], "market_positions": []}
        self._stub_venue(capture_script, monkeypatch, tmp_path, empty)
        _FrozenDatetime.start(datetime(2026, 9, 5, 4, 12, 33, tzinfo=timezone.utc))
        assert await capture_script.capture() == capture_script.EXIT_EMPTY

        after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        assert len(after) == 4
        for name, content in first.items():
            assert after[name] == content, f"{name} was rewritten by the next run"
        assert re.fullmatch(
            r"portfolio_positions_bare_\d{8}T\d{6}Z\.json",
            "portfolio_positions_bare_20260905T041233Z.json",
        )
        assert "portfolio_positions_bare_20260905T041233Z.json" in after

    def test_no_fixed_capture_filename_survives_in_the_code(self, capture_script):
        """The docstring may name the old files as history; the code may
        not. Every `_write` call takes its path from `capture_path`, read
        off the AST so a multi-line call cannot hide from a line grep."""
        import ast

        source = Path(capture_script.__file__).read_text(encoding="utf-8")
        assert "OUT_BARE" not in source
        assert "OUT_FILTERED" not in source
        tree = ast.parse(source)
        writes = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_write"
        ]
        assert len(writes) == 2, "one bare write and one filtered write"
        for call in writes:
            first = call.args[0]
            assert (
                isinstance(first, ast.Call)
                and isinstance(first.func, ast.Name)
                and first.func.id == "capture_path"
            ), ast.unparse(call)
