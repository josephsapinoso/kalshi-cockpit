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
behind without a migration step; that the venue's strings are stored verbatim
and the derived columns are NULL -- never 0 -- when a value will not parse;
that a successful poll writes its full row set under the poll's own stamp and
the count in `poll_log.row_count` is untouched; that the writer bounds its own
table; that `bets.open_positions` serves the count and the staked figure from
ONE read with ONE stamp, refuses on a stale poll with the clock kept, refuses
rather than partially sums when a row is unreadable, and serves an
empty-but-fresh snapshot as count 0 and $0.00; that `gate.py` cannot see the
table; and that the capture script no longer overwrites an observation.

What it does NOT establish
--------------------------
Whether `market_exposure_dollars` includes fees; anything about
`event_positions`; how the venue's `count_filter` treats a row that flips to
zero mid-session; that the screen renders the figure (lane A2). And nothing
here reads the live database: every row is synthetic in the observed shape.
"""

from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from backend import bets, portfolio_poll
from backend.portfolio_poll import (
    VENUE_POSITIONS_RETENTION_MS,
    parse_position,
    poll_positions,
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


def _poll(conn, *, polled_ms: int, row_count=0, ok: bool = True) -> int:
    """A `poll_log` row for the positions endpoint; returns its id."""
    cursor = conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
        "VALUES (?, 'positions', ?, ?)",
        (polled_ms, 1 if ok else 0, row_count),
    )
    conn.commit()
    return int(cursor.lastrowid)


class TestTheSchemaCarriesTheMirror:
    def test_a_fresh_database_has_the_table(self, conn):
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "venue_positions" in names

    def test_the_previous_version_gains_it_without_a_migration_step(
        self, tmp_path
    ):
        """v33 is tableless: `init_db` applies `schema.sql` with `CREATE TABLE
        IF NOT EXISTS` on every open, so the live volume gains the table on
        its next boot and no `_MIGRATIONS` entry exists to get wrong. The
        version is read from `SCHEMA_VERSION` rather than typed, for the
        reason `test_hedge_positions` records: a hand-written number starts
        asserting about a version two steps back the moment another lane
        adds a table."""
        path = tmp_path / "previous.db"
        connection = db.init_db(path)
        connection.execute("DROP TABLE venue_positions")
        db._set_meta(connection, "schema_version", str(db.SCHEMA_VERSION - 1))
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
            assert db.get_meta(reopened, "schema_version") == str(
                db.SCHEMA_VERSION
            )
        finally:
            reopened.close()

    def test_v33_is_declared_tableless(self):
        assert 33 in db._TABLELESS_VERSIONS
        assert 33 not in db._MIGRATIONS

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

    def test_an_unreadable_quantity_leaves_count_and_side_none(self):
        parsed = parse_position(dict(OBSERVED_POSITION_ROW, position_fp="lots"))
        assert parsed.contracts is None
        assert parsed.side is None
        assert parsed.position_fp == "lots"
        # The exposure is its own field and still parses.
        assert parsed.exposure_tenths == 7642

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

    def test_a_poll_row_with_no_mirror_rows_refuses_naming_both_numbers(
        self, conn
    ):
        """The shape of a `poll_log` row written before v33: the count is
        there and the rows are not. Served count, refused money, and the
        words say 3 and 0 so the mismatch is legible."""
        _poll(conn, polled_ms=NOW_MS - 10_000, row_count=3)

        block = bets.open_positions(conn, now_ms=NOW_MS)

        assert block["count"] == 3
        assert block["staked_tenths"] is None
        assert block["staked_refusal"] == bets.STAKED_MIRROR_MISMATCH.format(
            count=3, rows=0
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
        Keyed by id, the newer poll's empty mirror is a mismatch, in words."""
        await _mirror(conn, [OBSERVED_POSITION_ROW], at_ms=NOW_MS - 120_000)
        _poll(conn, polled_ms=NOW_MS - 10_000, row_count=1)  # no rows under it

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


class TestTheInterlockCannotSeeThisRecord:
    def test_gate_never_reads_venue_positions(self):
        """What Joe holds is his discretion, not evidence. The same boundary
        `manual_orders`, `parlay_positions` and `combo_orders` carry, pinned
        the same way: over the source of `backend/gate.py`, so a future join
        fails loudly rather than by convention."""
        source = (ROOT / "backend" / "gate.py").read_text(encoding="utf-8")
        assert "venue_positions" not in source
