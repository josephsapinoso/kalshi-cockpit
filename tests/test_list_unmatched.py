"""`scripts/list_unmatched.py` reads the queue without being able to touch it.

The `unmatched_items` queue had a writer (`backend/match/linker.py`) and no
reader anywhere in the repo -- the fifth built-but-never-called instance. These
tests pin the reader that closes that gap: the output carries the columns an
alias entry needs, the connection is physically read-only, and an empty queue
says so in words rather than printing nothing.

Seeded through `db.init_db` and `record_unmatched` deliberately -- the real
schema and the real writer -- so a schema or writer change that breaks the
reader breaks these tests rather than a hand-mocked copy of the table.

What these tests do NOT establish
---------------------------------
- **Not that the deployed database is readable by this script.** They run
  against a temp db at the current schema; a live db at an older version
  refuses (by design), and only running the script against it proves which.
- **Not that the listed items are actionable.** The reader shows the queue;
  whether an alias entry actually resolves an item is the linker's business.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.match.linker import record_unmatched
from backend.store import db
from scripts.list_unmatched import ELISION, connect_readonly, main

NOW = 1_787_000_000_000  # 2026-08-17T20:53:20Z
_MS_PER_DAY = 24 * 60 * 60 * 1000


@pytest.fixture()
def db_path(tmp_path):
    """A real database at the current schema, not a hand-built subset."""
    path = tmp_path / "cockpit.db"
    conn = db.init_db(path)
    conn.close()
    return path


def seed(path, *, ms=NOW, side="kalshi", identifier="KXNCAAFGAME-26AUG30ILSTOSU",
         league="NCAAF", detail="Illinois State vs Ohio State",
         reason="no_counterpart", times=1):
    conn = db.connect(path)
    try:
        for i in range(times):
            record_unmatched(
                conn, observed_ms=ms + i * 15_000, side=side,
                identifier=identifier, league=league, detail=detail,
                reason=reason,
            )
    finally:
        conn.close()


class TestOutputCarriesTheWorkItem:
    def test_the_columns_an_alias_entry_needs_are_all_present(
        self, db_path, capsys
    ):
        seed(db_path)

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        for needed in (
            "kalshi",                          # side
            "NCAAF",                           # league
            "KXNCAAFGAME-26AUG30ILSTOSU",      # identifier
            "Illinois State vs Ohio State",    # detail: the names as seen
            "no_counterpart",                  # reason
            "seen_count", "first_seen", "last_seen",
        ):
            assert needed in out

    def test_repeat_sightings_are_one_line_carrying_their_count(
        self, db_path, capsys
    ):
        seed(db_path, times=7)

        main(["--db", str(db_path)])
        out = capsys.readouterr().out
        item_lines = [
            line for line in out.splitlines()
            if "KXNCAAFGAME-26AUG30ILSTOSU" in line
        ]
        assert len(item_lines) == 1
        assert "7" in item_lines[0]
        assert "1 unmatched items" in out

    def test_first_and_last_seen_render_as_dates_not_epoch_ms(
        self, db_path, capsys
    ):
        seed(db_path, ms=NOW)
        seed(db_path, ms=NOW + 9 * _MS_PER_DAY)

        main(["--db", str(db_path)])
        out = capsys.readouterr().out
        assert "2026-08-17" in out    # first seen
        assert "2026-08-26" in out    # last seen
        assert str(NOW) not in out

    def test_a_null_league_and_detail_render_without_crashing(
        self, db_path, capsys
    ):
        seed(db_path, league=None, detail=None)

        assert main(["--db", str(db_path)]) == 0
        assert "KXNCAAFGAME-26AUG30ILSTOSU" in capsys.readouterr().out


class TestTheInstrumentCannotWrite:
    def test_a_write_on_the_scripts_connection_is_refused_by_sqlite(
        self, db_path
    ):
        """The pin on read-only, enforced below Python.

        Verified by mutation: with `connect_readonly` switched to a plain
        `sqlite3.connect`, the INSERT succeeds and this test fails.
        """
        conn = connect_readonly(str(db_path))
        try:
            with pytest.raises(
                sqlite3.OperationalError, match="readonly database"
            ):
                conn.execute(
                    "INSERT INTO unmatched_items (first_seen_ms, last_seen_ms,"
                    " side, identifier, reason) VALUES (1, 1, 'kalshi', 'X',"
                    " 'r')"
                )
        finally:
            conn.close()

    def test_running_the_script_leaves_the_queue_row_count_unchanged(
        self, db_path, capsys
    ):
        seed(db_path, times=3)

        main(["--db", str(db_path)])
        capsys.readouterr()

        conn = db.connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*), MAX(seen_count) FROM unmatched_items"
            ).fetchone()
        finally:
            conn.close()
        assert tuple(count) == (1, 3)


class TestEmptyIsSaidNotShown:
    def test_an_empty_queue_prints_zero_unmatched_items_in_words(
        self, db_path, capsys
    ):
        assert main(["--db", str(db_path)]) == 0
        assert "0 unmatched items" in capsys.readouterr().out

    def test_a_missing_database_refuses_instead_of_reporting_zero(
        self, tmp_path, capsys
    ):
        """Unreadable must never print the same thing as empty."""
        missing = tmp_path / "nowhere.db"

        assert main(["--db", str(missing)]) == 2
        captured = capsys.readouterr()
        assert "unmatched items" not in captured.out
        assert "cannot read" in captured.err


class TestTheLeagueCutIsEchoedWhereverItCounts:
    """`--league` narrows the rows; every count that results says so.

    Added 2026-09-07, when the live queue got an instrument for the first time.
    The queue carries every league at once, so the question asked of it is
    always about one -- and a cut that is not echoed turns "no rows for this
    league" into "the queue is empty". Those need opposite responses: the first
    is a spelling to check, the second is a linker that resolved everything.

    The filter is an exact, case-sensitive match on the competition string as
    the linker saw it, and it reaches SQL as a bound parameter, never as text.
    """

    def test_only_the_named_league_is_listed(self, db_path, capsys):
        seed(db_path, league="Pro Football", identifier="KXNFLGAME-26SEP09NESEA")
        seed(db_path, league="MLB", identifier="KXMLBGAME-26SEP07LADSFG")

        assert main(["--db", str(db_path), "--league", "Pro Football"]) == 0
        out = capsys.readouterr().out
        assert "KXNFLGAME-26SEP09NESEA" in out
        assert "KXMLBGAME-26SEP07LADSFG" not in out
        assert "1 unmatched items for league 'Pro Football'" in out

    def test_without_the_flag_every_league_is_listed_as_before(
        self, db_path, capsys
    ):
        """The default is byte-for-byte the reading this script gave before."""
        seed(db_path, league="Pro Football", identifier="KXNFLGAME-26SEP09NESEA")
        seed(db_path, league="MLB", identifier="KXMLBGAME-26SEP07LADSFG")

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        assert "KXNFLGAME-26SEP09NESEA" in out
        assert "KXMLBGAME-26SEP07LADSFG" in out
        assert "2 unmatched items in" in out
        assert "for league" not in out

    def test_a_league_with_no_rows_does_not_read_as_an_empty_queue(
        self, db_path, capsys
    ):
        """The one that matters: 250 baseball rows and a typo'd league name
        must not print the sentence that means the linker resolved everything.
        """
        seed(db_path, league="MLB", identifier="KXMLBGAME-26SEP07LADSFG")

        assert main(["--db", str(db_path), "--league", "pro football"]) == 0
        out = capsys.readouterr().out
        assert "0 unmatched items for league 'pro football'" in out
        assert "exact match, not a prefix" in out
        assert "resolved everything it saw" not in out

    def test_the_match_is_exact_rather_than_a_prefix(self, db_path, capsys):
        """`Pro Football Preseason` is a different competition, and the
        pre-flight checked for exactly that string being absent.
        """
        seed(
            db_path,
            league="Pro Football Preseason",
            identifier="KXNFLPRE-26AUG14NESEA",
        )

        assert main(["--db", str(db_path), "--league", "Pro Football"]) == 0
        out = capsys.readouterr().out
        assert "KXNFLPRE-26AUG14NESEA" not in out
        assert "0 unmatched items for league 'Pro Football'" in out

    def test_a_league_name_carrying_sql_is_matched_as_text(
        self, db_path, capsys
    ):
        """Bound parameter, not interpolation. A vacuous pass is impossible
        here because the control row must survive: if the string were spliced
        into the WHERE clause, `' OR 1=1 --` would list the MLB row.
        """
        seed(db_path, league="MLB", identifier="KXMLBGAME-26SEP07LADSFG")

        assert main(["--db", str(db_path), "--league", "' OR 1=1 --"]) == 0
        out = capsys.readouterr().out
        assert "KXMLBGAME-26SEP07LADSFG" not in out
        assert "0 unmatched items" in out


class TestAFixedRowGoesStaleRatherThanDisappearing:
    """The reading the 2026-09-07 NFL plan got backwards, pinned in a test.

    Nothing sets `resolved = 1` and nothing deletes on success -- `linker.py`
    only upserts. So a work item that stops failing keeps its row, frozen at
    the `last_seen_ms` of the last pass that failed on it, until retention
    prunes it seven days later. The count does not fall when a link lands;
    `last_seen` stops moving. A plan that watches the count reads a successful
    fix as a failure for a week.
    """

    def test_the_count_does_not_fall_when_an_item_stops_being_seen(
        self, db_path, capsys
    ):
        seed(db_path, identifier="FIXED-ONE", times=1)
        seed(db_path, identifier="STILL-FAILING", times=1)

        # A later pass re-derives only one of them, exactly as the linker does.
        seed(db_path, ms=NOW + _MS_PER_DAY, identifier="STILL-FAILING", times=1)

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        assert "2 unmatched items in" in out, (
            "the fixed item's row must survive; if this ever reads 1, "
            "something now deletes or resolves rows and the staleness "
            "reading in this script's docstring is obsolete"
        )

    def test_the_still_failing_item_sorts_above_the_fixed_one(
        self, db_path, capsys
    ):
        """`ORDER BY last_seen_ms DESC` IS the reading, not a presentation
        choice: it is what puts the live failures where a reader looks first.
        """
        seed(db_path, identifier="FIXED-ONE", times=1)
        seed(db_path, ms=NOW + _MS_PER_DAY, identifier="STILL-FAILING", times=1)

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        assert out.index("STILL-FAILING") < out.index("FIXED-ONE")

    def test_the_two_carry_different_last_seen_stamps(self, db_path, capsys):
        """Without this the ordering above is unreadable: the reader separates
        them by the printed stamp, so the stamp has to differ on the page and
        not merely in the column it is sorted by.
        """
        seed(db_path, identifier="FIXED-ONE", times=1)
        seed(db_path, ms=NOW + _MS_PER_DAY, identifier="STILL-FAILING", times=1)

        assert main(["--db", str(db_path)]) == 0
        lines = capsys.readouterr().out.splitlines()
        failing = next(ln for ln in lines if "STILL-FAILING" in ln)
        fixed = next(ln for ln in lines if "FIXED-ONE" in ln)
        assert "2026-08-18" in failing
        assert "2026-08-17" in fixed


class TestOneWideCellDoesNotWidenEveryRow:
    """A column table takes its width from its worst cell.

    ADDED 2026-09-07, from the first run of this script against the live queue,
    which returned **75.8 KB for 66 rows**: lines of 1,300 to 2,249 characters
    on a queue whose longest real name is "Las Vegas vs Miami". One
    `KXNFLTEAMTOTAL` row's `detail` is the whole points ladder joined by
    " vs " -- 2,100 characters of "LA Rams over 3.5 points scored vs LA Rams
    over 7.5 points scored vs ..." -- and every other row was padded to it.

    That is not cosmetic for an instrument read over `flyctl ssh` at 03:40Z to
    decide whether a link landed: the reading is the `last_seen` column, and it
    was 2,000 characters to the right of where anyone would look.
    """

    LADDER = " vs ".join(
        f"LA Rams over {n}.5 points scored" for n in range(3, 60)
    )

    def test_a_wide_cell_is_cut_and_the_row_stays_readable(
        self, db_path, capsys
    ):
        seed(db_path, identifier="KXNFLTEAMTOTAL-26SEP10SFLAR", detail=self.LADDER)

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        assert max(len(ln) for ln in out.splitlines()) < 300, (
            "one pathological cell is still setting the table width"
        )

    def test_the_neighbouring_rows_are_not_padded_to_the_wide_one(
        self, db_path, capsys
    ):
        """The actual harm: a short row made unreadable by a long one."""
        seed(db_path, identifier="KXNFLGAME-26SEP13MIALV", detail="Las Vegas vs Miami")
        seed(db_path, identifier="KXNFLTEAMTOTAL-26SEP10SFLAR", detail=self.LADDER)

        assert main(["--db", str(db_path)]) == 0
        line = next(
            ln for ln in capsys.readouterr().out.splitlines()
            if "KXNFLGAME-26SEP13MIALV" in ln
        )
        assert len(line) < 300

    def test_the_cut_is_counted_rather_than_silent(self, db_path, capsys):
        """An instrument that quietly drops text teaches its reader to trust a
        complete-looking row. Same rule as the `--league` echo."""
        seed(db_path, identifier="KXNFLTEAMTOTAL-26SEP10SFLAR", detail=self.LADDER)

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        assert "1 cell(s) cut to 80 chars" in out
        assert "--full shows them whole" in out

    def test_an_elided_cell_is_marked_where_it_was_cut(self, db_path, capsys):
        seed(db_path, identifier="KXNFLTEAMTOTAL-26SEP10SFLAR", detail=self.LADDER)

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        assert ELISION in out
        assert "LA Rams over 3.5 points scored" in out, (
            "the head of the cell must survive; a cut that keeps nothing is "
            "a dropped column"
        )

    def test_nothing_is_cut_or_announced_when_nothing_is_wide(
        self, db_path, capsys
    ):
        """The vacuity guard. Without it every assertion above passes on a
        renderer that announces a cut it never made."""
        seed(db_path, detail="Illinois State vs Ohio State")

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        assert "cut to" not in out
        assert ELISION not in out

    def test_full_restores_the_whole_cell(self, db_path, capsys):
        """The escape hatch, and the reason eliding by default is safe."""
        seed(db_path, identifier="KXNFLTEAMTOTAL-26SEP10SFLAR", detail=self.LADDER)

        assert main(["--db", str(db_path), "--full"]) == 0
        out = capsys.readouterr().out
        assert self.LADDER in out
        assert "cut to" not in out

    def test_the_reading_column_is_not_the_one_pushed_off_the_page(
        self, db_path, capsys
    ):
        """`last_seen` is what a reader came for -- it is how a linked row is
        told from a failing one -- and `detail` sits to its left. Pin that the
        stamp lands inside a width a terminal shows.
        """
        seed(db_path, identifier="KXNFLTEAMTOTAL-26SEP10SFLAR", detail=self.LADDER)

        assert main(["--db", str(db_path)]) == 0
        line = next(
            ln for ln in capsys.readouterr().out.splitlines()
            if "KXNFLTEAMTOTAL" in ln
        )
        assert line.index("2026-08-17") < 250
