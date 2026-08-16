"""`scripts/inspect_live_db.py`: the only reader that runs against the money box.

The module shipped inert. Its authoring lane died on a session limit with the
code complete and not one assertion in it ever seen to go red, so `__main__`
printed a refusal and exited 3. This file is what lifts that refusal, and it is
therefore held to the standard the refusal named: **every claim below was
observed red under a named mutation of the code it pins.** The mutation is
written beside the test so a future edit can re-run it in one line rather than
trusting this sentence.

WHERE THE DATABASE COMES FROM
-----------------------------
`backend/store/schema.sql` is executed verbatim against a `tmp_path` file. Not
one `CREATE TABLE` is written here, because the failure being guarded against is
a whitelisted query naming a column the live database does not have -- and a
hand-written schema that agreed with the query would hide exactly that. The
schema puts the file in WAL mode, which is the same mode `/data/cockpit.db`
runs in, so `mode=ro` is exercised against the journalling the live box uses.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the live database's contents.** Every row here was inserted by
  this file. A green suite says the queries are well-formed against the schema
  and the guards fire; it says nothing about what `/data/cockpit.db` holds, and
  no test here has ever seen that file.
- **Nothing about the whitelist being sufficient.** These tests pin that the
  nine named queries run and mean what they say. `kalshi_quotes` is no longer
  among the tables the whitelist cannot reach -- `kalshi-quotes-band` reaches it
  -- but `fair_prices` and `recommendations` as a population rather than as a
  `--pin` subquery still are. A green suite is not evidence that a question can
  be answered.
- **Nothing about the ssh convention.** The rule that `flyctl ssh console` may
  only invoke a committed script by path is a convention the agent keeps and Joe
  audits. No test can enforce it, and none here tries.
- **Nothing about read-only being sufficient protection.** `mode=ro` stops a
  write. It does not stop a badly-shaped read from dumping the record into a
  transcript; that is what the row cap is for, and the cap is a policy this file
  pins rather than a property SQLite enforces.
- **Nothing about causation, completeness, or the correctness of any value.**
  The module's own docstring disclaims all three, and these tests inherit those
  limits unchanged rather than quietly widening them.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from scripts.inspect_live_db import (
    DEFAULT_ROW_CAP,
    QUERIES,
    _ACTIONABLE_PREDICATE,
    _SQL_ACTIONABLE_FAIR,
    _SQL_ACTIONABLE_ROWS,
    Section,
    UnknownQuery,
    _QW_BAND_HI,
    _QW_BAND_HOLE,
    _QW_BAND_LO,
    _QW_MIN_EVENTS,
    _QW_PREGAME_OFFSET_MS,
    _QW_SERIES_ORDER,
    _QW_WINDOW_END_MS,
    _QW_WINDOW_START_MS,
    _day_bounds,
    _derive_iso,
    _fetch,
    _iso,
    _q_kalshi_quotes_band,
    _q_prop_rungs,
    _qw_verdict,
    connect_readonly,
    main,
    render_json,
    render_text,
    resolve_query,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "store" / "schema.sql"

# The budget day every credits test uses. Bounds are derived from the module's
# own `_day_bounds` rather than restated, so a test can never disagree with the
# code about where the day starts -- it can only disagree about half-openness,
# which is the thing being asserted.
DAY = "20260810"
DAY_START_HOUR = 10


def _bounds() -> tuple[int, int]:
    return _day_bounds(DAY, DAY_START_HOUR)


@pytest.fixture
def empty_db(tmp_path) -> Path:
    """A database built by executing the real `schema.sql`, with no rows.

    Named `cockpit.db` to match the live volume, because the repo root also
    holds a `kalshi.db` scratch file and the two names have been confused.
    """
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def live_db(empty_db) -> Path:
    """The schema-built database with a small, deliberately shaped population.

    Three series, two events, three markets, and three recommendations whose
    ids (10, 20, 30) are spaced so a `--pin` can fall between them. The
    `api_credits` rows sit on the budget-day boundary on purpose: one before the
    window, one exactly at the start, one inside, one at the last millisecond,
    and one exactly at the end -- so a `<` that became a `<=` changes the count.
    """
    start_ms, end_ms = _bounds()
    conn = sqlite3.connect(empty_db)
    conn.executescript(
        """
        INSERT INTO kalshi_series (series_ticker, league, first_seen_ms, last_seen_ms)
        VALUES ('KXWNBAGAME', 'wnba', 1, 1),
               ('KXMLBGAME',  'mlb',  1, 1),
               ('KXNFLGAME',  NULL,   1, 1);

        INSERT INTO kalshi_events
            (event_ticker, series_ticker, commence_ms, close_ms, status,
             first_seen_ms, last_seen_ms)
        VALUES ('E1', 'KXWNBAGAME', 1000, 2000, 'settled', 1, 1),
               ('E2', 'KXMLBGAME',  3000, 4000, 'open',    1, 1);

        INSERT INTO kalshi_markets
            (ticker, event_ticker, series_ticker, yes_side_team, market_type,
             status, result, first_seen_ms, last_seen_ms)
        VALUES ('T1', 'E1', 'KXWNBAGAME', 'LIB', 'moneyline', 'finalized', 'yes', 1, 1),
               ('T2', 'E1', 'KXWNBAGAME', 'ACE', 'moneyline', 'finalized', 'no',  1, 1),
               ('T3', 'E2', 'KXMLBGAME',  'NYY', 'moneyline', 'active',    NULL,  1, 1);

        INSERT INTO closing_lines
            (ticker, horizon_hours, observed_ms, yes_bid_tenths, yes_ask_tenths)
        VALUES ('T1', 1.0, 900, 400, 420),
               ('T1', 2.0, 800, 390, 410),
               ('T2', 1.0, 900, 570, 590),
               ('T3', 1.0, 2900, 480, 500);

        INSERT INTO strategy_configs
            (version, created_ms, effective_from_ms, config_json, rationale)
        VALUES (1, 1, 1, '{}', 'seed');

        INSERT INTO recommendations
            (id, created_ms, strategy_config_version, ticker, side,
             entry_ask_tenths, fair_probability, edge_tenths, fee_predicted,
             ev_net_dollars, kelly_fraction, suggested_contracts,
             kalshi_quote_age_ms, odds_age_ms, reason_text)
        VALUES (10, 1, 1, 'T1', 'yes', 420, 0.45, 3.0, 0.01, 0.02, 0.01, 0, 100, 100, 'a'),
               (20, 2, 1, 'T2', 'no',  590, 0.44, 2.0, 0.01, 0.01, 0.01, 0, 100, 100, 'b'),
               (30, 3, 1, 'T3', 'yes', 500, 0.52, 1.0, 0.01, 0.01, 0.01, 0, 100, 100, 'c');

        INSERT INTO odds_sweep_log (pass_ms, sport_key, outcome, detail, quotes_stored)
        VALUES (10, 'baseball_mlb', 'served',  'window open', 12),
               (20, 'baseball_mlb', 'refused', 'daily ceiling', NULL),
               (30, NULL,           'skipped', 'no slate',      NULL);
        """
    )
    conn.executemany(
        "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost, "
        "remaining_reported, used_reported) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (start_ms - 1, "/odds", "baseball_mlb", 2, 400, 100),
            (start_ms, "/odds", "baseball_mlb", 2, 398, 102),
            (start_ms + 5_000, "/odds", "basketball_wnba", 4, 394, 106),
            (end_ms - 1, "/odds", "baseball_mlb", 2, 392, 108),
            (end_ms, "/odds", "baseball_mlb", 2, 390, 110),
        ],
    )
    conn.commit()
    conn.close()
    return empty_db


@pytest.fixture
def ro(live_db):
    conn = connect_readonly(str(live_db))
    yield conn
    conn.close()


def _section(rows: list[tuple], columns: tuple[str, ...] = ("a",)) -> Section:
    return Section(title="t", columns=columns, rows=rows)


def _run_json(capsys, argv: list[str]) -> dict[str, Any]:
    """Run `main` with `--json` and return the parsed payload.

    Parsed rather than substring-matched: `"3 rows" in out` passes on a
    timestamp that happens to contain the digits, which is the kind of
    assertion that stays green under the mutation it exists to catch.
    """
    rc = main([*argv, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    return payload


def _named(payload: dict[str, Any], fragment: str) -> dict[str, Any]:
    matches = [s for s in payload["sections"] if fragment in s["title"]]
    assert len(matches) == 1, f"{fragment!r} matched {len(matches)} sections"
    return matches[0]


class TestTheConnectionRefusesAWrite:
    """`mode=ro` is the property that makes this file reviewable once.

    Mutation: `connect_readonly` -> `f"file:{db_path}?mode=rwc"`.
    """

    def test_an_insert_through_the_inspectors_connection_is_refused(self, ro):
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            ro.execute(
                "INSERT INTO kalshi_series (series_ticker, first_seen_ms, "
                "last_seen_ms) VALUES ('X', 1, 1)"
            )

    def test_an_update_through_the_inspectors_connection_is_refused(self, ro):
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            ro.execute("UPDATE kalshi_series SET league = 'nba'")

    def test_a_delete_through_the_inspectors_connection_is_refused(self, ro):
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            ro.execute("DELETE FROM api_credits")

    def test_the_refused_write_left_the_row_count_unchanged(self, live_db, ro):
        """Not just an exception -- nothing landed.

        A raise that still wrote would be worse than no guard, because the
        exception would read as protection.
        """
        with pytest.raises(sqlite3.OperationalError):
            ro.execute(
                "INSERT INTO kalshi_series (series_ticker, first_seen_ms, "
                "last_seen_ms) VALUES ('X', 1, 1)"
            )
        after = sqlite3.connect(live_db)
        try:
            assert after.execute("SELECT COUNT(*) FROM kalshi_series").fetchone()[0] == 3
        finally:
            after.close()

    def test_a_read_still_works(self, ro):
        """The guard must refuse writes, not everything.

        A connection that refused reads too would pass every assertion above
        and be useless, which is the shape of a guard that cannot be
        distinguished from a broken feature.
        """
        assert ro.execute("SELECT COUNT(*) FROM kalshi_series").fetchone()[0] == 3

    def test_a_missing_database_is_not_created(self, tmp_path):
        """`mode=ro` refuses to conjure the file, so a typo'd `--db` is loud."""
        missing = tmp_path / "not_here.db"
        with pytest.raises(sqlite3.OperationalError):
            connect_readonly(str(missing))
        assert not missing.exists()

    def test_main_exits_3_when_the_database_cannot_be_opened(self, tmp_path, capsys):
        rc = main(["series", "--db", str(tmp_path / "not_here.db")])
        assert rc == 3
        assert "cannot open" in capsys.readouterr().err


class TestAnUnknownQueryIsRejected:
    """A typo'd name must not read as "nothing to report".

    Mutation: `resolve_query` -> `return QUERIES.get(name)`.
    """

    def test_resolve_query_raises_for_a_name_not_on_the_whitelist(self):
        with pytest.raises(UnknownQuery):
            resolve_query("credits_tail")

    def test_a_table_name_is_not_a_query_name(self):
        """The whitelist is closed: the caller chooses a name, never a table."""
        with pytest.raises(UnknownQuery):
            resolve_query("api_credits")

    def test_the_rejection_names_the_known_queries(self):
        with pytest.raises(UnknownQuery) as exc:
            resolve_query("creditstail")
        message = str(exc.value)
        assert "creditstail" in message
        for name in QUERIES:
            assert name in message

    def test_main_returns_2_and_says_so_on_stderr(self, live_db, capsys):
        rc = main(["credits_tail", "--db", str(live_db)])
        captured = capsys.readouterr()
        assert rc == 2
        assert "unknown query" in captured.err

    def test_main_prints_nothing_to_stdout_for_an_unknown_query(self, live_db, capsys):
        """Empty stdout plus exit 0 is the exact failure mode being prevented.

        stdout must be empty *and* the return code non-zero. Either alone would
        let a typo read as a clean run with no rows.
        """
        rc = main(["credits_tail", "--db", str(live_db)])
        assert capsys.readouterr().out == ""
        assert rc != 0

    def test_the_rejection_happens_on_the_only_path_a_caller_has(self, live_db):
        """Not `argparse(choices=...)`, which would make `resolve_query` dead code.

        argparse would exit via `SystemExit(2)`; `main` returns 2. The
        difference is what says the whitelist lookup is reachable in production.
        """
        assert main(["credits_tail", "--db", str(live_db)]) == 2


class TestTheRowCapTruncatesAndSaysSo:
    """A silent trim turns "there are 40,000" into "there are 2,000".

    Mutations: `_fetch` `effective + 1` -> `effective`; `len(rows) > effective`
    -> `>=`; and dropping `and effective == cap`.
    """

    def test_the_result_is_trimmed_to_the_cap(self, live_db, capsys):
        payload = _run_json(
            capsys, ["series", "--db", str(live_db), "--limit", "2"]
        )
        section = _named(payload, "kalshi_series")
        assert section["row_count"] == 2
        assert len(section["rows"]) == 2
        assert section["truncated"] is True

    def test_truncation_is_reported_on_the_section(self, ro):
        section = _fetch(
            ro,
            "SELECT series_ticker FROM kalshi_series ORDER BY series_ticker",
            (),
            title="t",
            cap=2,
        )
        assert section.row_count == 2
        assert section.truncated is True
        assert section.cap == 2

    def test_a_result_exactly_at_the_cap_is_not_truncated(self, ro):
        """The +1 probe. Three rows under a cap of three is complete, not trimmed.

        This is the boundary a `>=` would break, and the direction it breaks in
        -- claiming more rows exist than do -- is the one that sends a reader
        looking for data that is not there.
        """
        section = _fetch(
            ro,
            "SELECT series_ticker FROM kalshi_series ORDER BY series_ticker",
            (),
            title="t",
            cap=3,
        )
        assert section.row_count == 3
        assert section.truncated is False

    def test_a_result_under_the_cap_is_not_truncated(self, ro):
        section = _fetch(
            ro,
            "SELECT series_ticker FROM kalshi_series ORDER BY series_ticker",
            (),
            title="t",
            cap=10,
        )
        assert section.row_count == 3
        assert section.truncated is False

    def test_the_querys_own_n_binding_is_not_truncation(self, ro):
        """`credits-tail -n 2` returning 2 of 5 rows is the caller getting what
        they asked for, not the hard cap biting."""
        section = _fetch(
            ro,
            "SELECT called_ms FROM api_credits ORDER BY called_ms DESC",
            (),
            title="t",
            cap=2000,
            requested=2,
        )
        assert section.row_count == 2
        assert section.truncated is False

    def test_the_hard_cap_still_bites_under_a_larger_requested_n(self, ro):
        section = _fetch(
            ro,
            "SELECT called_ms FROM api_credits ORDER BY called_ms DESC",
            (),
            title="t",
            cap=2,
            requested=5,
        )
        assert section.row_count == 2
        assert section.truncated is True

    def test_a_named_parameter_query_also_honours_the_cap(self, live_db, capsys):
        """The dict branch binds the cap by name. A single `LIMIT ?` suffix
        would raise `ProgrammingError` here rather than truncate.

        Mutation: `_fetch` -> `suffix = " LIMIT ?"` unconditionally.
        """
        payload = _run_json(
            capsys,
            ["results-for-pull", "--db", str(live_db), "--pin", "30", "--limit", "2"],
        )
        section = _named(payload, "kalshi_markets")
        assert section["row_count"] == 2
        assert section["truncated"] is True

    def test_the_text_render_names_the_cap_that_bound(self):
        section = Section(
            title="t", columns=("a",), rows=[(1,)], truncated=True, cap=7
        )
        out = render_text("q", "/data/cockpit.db", [section])
        assert "TRUNCATED" in out
        assert "7" in out

    def test_the_json_render_carries_truncated_and_the_cap(self):
        section = Section(
            title="t", columns=("a",), rows=[(1,)], truncated=True, cap=7
        )
        out = render_json("q", "/data/cockpit.db", [section])
        assert '"truncated": true' in out
        assert '"row_cap": 7' in out

    def test_an_untruncated_section_does_not_claim_truncation(self):
        out = render_text("q", "/data/cockpit.db", [_section([(1,)])])
        assert "TRUNCATED" not in out


class TestAZeroRowResultSaysZeroRows:
    """An empty region of a transcript reads as success. Absence gets words.

    Mutation: delete the `out.append("0 rows")` branch in `render_text`.
    """

    def test_the_text_render_prints_an_explicit_zero_rows_line(self):
        out = render_text("q", "/data/cockpit.db", [_section([])])
        assert "0 rows" in out

    def test_the_zero_rows_line_follows_its_title(self):
        """Not an empty block. The title must not be the last thing said."""
        out = render_text("q", "/data/cockpit.db", [_section([])]).splitlines()
        title_at = out.index("t")
        assert "0 rows" in out[title_at:]

    def test_an_empty_section_renders_more_than_a_heading(self):
        empty = render_text("q", "/data/cockpit.db", [_section([])])
        heading_only = "\n".join(["# q  (/data/cockpit.db)", "", "t", "-"])
        assert empty.strip() != heading_only.strip()
        assert "0 rows" in empty

    def test_the_json_render_carries_row_count_zero_and_empty_true(self):
        out = render_json("q", "/data/cockpit.db", [_section([])])
        assert '"row_count": 0' in out
        assert '"empty": true' in out

    def test_a_populated_section_is_not_reported_empty(self):
        out = render_json("q", "/data/cockpit.db", [_section([(1,)])])
        assert '"empty": false' in out

    def test_an_empty_query_result_says_zero_rows_end_to_end(self, empty_db, capsys):
        """Against the schema with no rows -- the state the live box was in for
        `odds_sweep_log` before the table started being written."""
        assert main(["sweep-log", "--db", str(empty_db)]) == 0
        assert "0 rows" in capsys.readouterr().out.splitlines()


class TestBothRenderersStateTheRowCount:
    """`row_count` is carried on the Section so neither renderer can omit it.

    Mutations: delete `out.append(f"{section.row_count} {noun}")` in
    `render_text`; set `"empty": False` unconditionally in `render_json`.
    """

    def test_the_text_render_states_the_count_of_a_populated_section(self):
        out = render_text("q", "/data/cockpit.db", [_section([(1,), (2,), (3,)])])
        assert "3 rows" in out.splitlines()

    def test_one_row_is_singular(self):
        out = render_text("q", "/data/cockpit.db", [_section([(1,)])])
        assert "1 row" in out
        assert "1 rows" not in out

    def test_the_json_render_states_the_count_of_every_section(self):
        out = render_json(
            "q",
            "/data/cockpit.db",
            [_section([(1,), (2,)]), _section([])],
        )
        assert '"row_count": 2' in out
        assert '"row_count": 0' in out

    def test_null_is_printed_as_null_not_as_blank(self):
        """An empty cell is a value; absence is not. `kalshi_series.league` is
        NULL until mapped and must not render as an empty string."""
        out = render_text("q", "/data/cockpit.db", [_section([(None,)])])
        assert "NULL" in out


class TestAMissingTimestampIsNotTheEpoch:
    """`None` in, `None` out. 1970 rendered for an absent stamp is a fabricated
    observation.

    Mutation: `_iso` -> `if ms is None: ms = 0`.
    """

    def test_iso_of_none_is_none(self):
        assert _iso(None) is None

    def test_iso_of_zero_is_the_epoch(self):
        """Zero is a real instant and must keep its rendering. Without this,
        `if not ms` would pass the test above while erasing a genuine value."""
        assert _iso(0) == "1970-01-01T00:00:00Z"

    def test_iso_renders_utc_with_a_z(self):
        """UTC, and stamped `Z` rather than `+00:00`.

        A stamp rendered in the machine's local zone is the failure
        `schema.sql` records at length: the previous project's `.replace(
        tzinfo=None)` made every "seconds to close" wrong by the local offset,
        and on this laptop (UTC-7) an offset-naive render would read 03:00.
        """
        assert _iso(1_786_356_000_000) == "2026-08-10T10:00:00Z"

    def test_a_null_ms_column_derives_a_null_iso(self):
        section = _derive_iso(
            Section(title="t", columns=("pass_ms",), rows=[(None,), (0,)]),
            "pass_ms",
            "pass_iso",
        )
        assert section.columns == ("pass_ms", "pass_iso")
        assert section.rows[0] == (None, None)
        assert section.rows[1] == (0, "1970-01-01T00:00:00Z")

    def test_deriving_from_a_column_that_is_not_there_raises(self):
        """A renamed column must break loudly rather than silently drop the ISO
        view -- an absent second view of a stamp reads as an absent stamp.

        Mutation: `_derive_iso` -> `return section` instead of raising.
        """
        with pytest.raises(KeyError):
            _derive_iso(_section([(1,)]), "called_ms", "called_iso")


class TestThePinRestrictsThePopulation:
    """`--pin` makes the population byte-identical to the committed pull.

    Mutation: `_PINNED_TICKERS` -> `WHERE (id <= :pin OR 1 = 1)`.
    """

    def test_markets_below_the_pin_only(self, live_db, capsys):
        assert main(["results-for-pull", "--db", str(live_db), "--pin", "20"]) == 0
        out = capsys.readouterr().out
        assert "T1" in out and "T2" in out
        assert "T3" not in out
        assert "2 rows" in out.splitlines()

    def test_raising_the_pin_admits_the_later_row(self, live_db, capsys):
        assert main(["results-for-pull", "--db", str(live_db), "--pin", "30"]) == 0
        out = capsys.readouterr().out
        assert "T3" in out
        assert "3 rows" in out.splitlines()

    def test_events_are_reached_only_through_pinned_markets(self, live_db, capsys):
        assert main(["events-for-pull", "--db", str(live_db), "--pin", "20"]) == 0
        out = capsys.readouterr().out
        assert "E1" in out
        assert "E2" not in out

    def test_closing_lines_are_restricted_by_the_same_pin(self, live_db, capsys):
        assert main(["closing-lines-for-pull", "--db", str(live_db), "--pin", "20"]) == 0
        out = capsys.readouterr().out
        assert "3 rows" in out.splitlines()
        assert "T3" not in out

    def test_a_pin_below_every_row_yields_zero_rows_not_everything(self, live_db, capsys):
        """The direction that matters: an over-restrictive pin must under-report,
        never fall open."""
        assert main(["results-for-pull", "--db", str(live_db), "--pin", "1"]) == 0
        assert "0 rows" in capsys.readouterr().out.splitlines()


class TestTheBudgetDayWindowIsHalfOpen:
    """[start, end). A row at exactly `end_ms` belongs to the next day.

    Mutation: `_SQL_CREDITS_DAY_ROWS` -> `called_ms <= ?`.
    """

    def test_the_day_starts_at_the_configured_hour(self):
        start_ms, end_ms = _bounds()
        assert _iso(start_ms) == "2026-08-10T10:00:00Z"
        assert end_ms - start_ms == 86_400_000

    def test_the_boundary_rows_are_included_and_excluded_correctly(
        self, live_db, capsys
    ):
        """Five seeded rows straddle the window; exactly three are inside.

        The `called_ms` values are asserted, not just the count: a window
        shifted by a whole day would also return three rows from a differently
        shaped table, and this one is shaped to make that indistinguishable
        unless the values are named.
        """
        start_ms, end_ms = _bounds()
        payload = _run_json(
            capsys,
            [
                "credits-day",
                "--db",
                str(live_db),
                "--date",
                DAY,
                "--day-start-hour",
                str(DAY_START_HOUR),
            ],
        )
        section = _named(payload, "budget day 2026")
        called = [row[0] for row in section["rows"]]
        assert called == [start_ms, start_ms + 5_000, end_ms - 1]

    def test_the_summed_cost_covers_the_same_three_rows(self, live_db, capsys):
        """2 + 4 + 2. Each excluded neighbour also costs 2, so an inclusive end
        reads 10 and an inclusive-both boundary reads 12."""
        payload = _run_json(
            capsys,
            [
                "credits-day",
                "--db",
                str(live_db),
                "--date",
                DAY,
                "--day-start-hour",
                str(DAY_START_HOUR),
            ],
        )
        totals = _named(payload, "row count and summed cost")
        assert totals["columns"] == ["rows_in_day", "total_cost"]
        assert totals["rows"] == [[3, 8]]

    def test_the_window_actually_used_is_printed(self, live_db, capsys):
        """The reader must be able to check the window without re-deriving it.

        Mutation: `_q_credits_day` -> `_window_section(..., start_ms, None)`.
        """
        start_ms, end_ms = _bounds()
        payload = _run_json(
            capsys, ["credits-day", "--db", str(live_db), "--date", DAY]
        )
        window = _named(payload, "budget day window")
        assert window["columns"] == ["start_ms", "start_iso", "end_ms", "end_iso"]
        assert window["rows"] == [
            [start_ms, _iso(start_ms), end_ms, _iso(end_ms)]
        ]

    def test_credits_day_refuses_without_a_date_rather_than_guessing_today(
        self, live_db, capsys
    ):
        """A guessed date answers a different question silently.

        Mutation: `_q_credits_day` -> default `args.date` to today.
        """
        rc = main(["credits-day", "--db", str(live_db)])
        captured = capsys.readouterr()
        assert rc == 2
        assert "--date" in captured.err
        assert captured.out == ""

    def test_a_malformed_date_is_refused(self, live_db, capsys):
        rc = main(["credits-day", "--db", str(live_db), "--date", "2026-08-10"])
        assert rc == 2
        assert "YYYYMMDD" in capsys.readouterr().err


class TestEveryWhitelistedQueryRunsAgainstTheRealSchema:
    """The queries name columns the live database has.

    Mutation: rename any column in any `_SQL_*` constant (e.g. `league` ->
    `leagues` in `_SQL_SERIES`).
    """

    @pytest.mark.parametrize("name", sorted(QUERIES))
    def test_the_query_runs_and_exits_zero(self, name, live_db, capsys):
        rc = main([name, "--db", str(live_db), "--date", DAY, "--json"])
        capsys.readouterr()
        assert rc == 0

    @pytest.mark.parametrize("name", sorted(QUERIES))
    def test_every_section_states_its_row_count_even_when_empty(
        self, name, empty_db, capsys
    ):
        """One count line per section, on an empty database.

        Stated as an equality against the section count from the JSON render
        rather than as `"0 rows" in out`, because a substring check passes as
        long as *one* section says it. The equality is what makes dropping the
        empty branch -- or the populated one -- go red.
        """
        rc_json = main([name, "--db", str(empty_db), "--date", DAY, "--json"])
        payload = json.loads(capsys.readouterr().out)
        rc_text = main([name, "--db", str(empty_db), "--date", DAY])
        text = capsys.readouterr().out
        assert rc_json == 0 and rc_text == 0
        counted = [
            line for line in text.splitlines() if re.fullmatch(r"\d+ rows?", line)
        ]
        assert len(counted) == len(payload["sections"])

    def test_every_query_has_a_description(self):
        for name, defn in QUERIES.items():
            assert defn.description.strip(), name


class TestTheScriptIsRunnable:
    """The refusal block is gone, and it was the tests above that removed it."""

    def test_the_module_carries_no_unverified_refusal(self):
        import scripts.inspect_live_db as mod

        assert not hasattr(mod, "_UNVERIFIED")

    def test_a_successful_run_returns_zero_and_prints_the_query_and_db(
        self, live_db, capsys
    ):
        assert main(["series", "--db", str(live_db)]) == 0
        out = capsys.readouterr().out
        assert "# series" in out
        assert str(live_db) in out


# ---------------------------------------------------------------------------
# Q-W: `kalshi-quotes-band`
#
# What these tests establish: the band, its hole at 300, the depth column, the
# 3-hour pre-game offset, the window's half-openness, both activation bars and
# the series substitution order behave exactly as the registration fixes them.
#
# What they do NOT establish, and no local test can: whether a WNBA market was
# actually reachable in that band. That is a fact about the live database and is
# only readable after a deploy.
# ---------------------------------------------------------------------------

# True start sits 7h after the window opens, so a quote stamped at the window's
# own start is comfortably pre-game and the offset can be probed at its edge.
QW_COMMENCE_MS = _QW_WINDOW_START_MS + 10 * 60 * 60 * 1000
QW_TRUE_START_MS = QW_COMMENCE_MS - _QW_PREGAME_OFFSET_MS

# Asks are stated as asks; the no-side bid that produces them is derived here so
# no test hand-computes the identity and gets it backwards.
IN_BAND_ASK = 350


def _no_bid_for(ask: int) -> int:
    return 1000 - ask


class _Args:
    """The argparse attributes the handlers under test read off the namespace.

    `odds_event_id` defaults to `None` here for the same reason the flag
    defaults to `None` in the parser: `prop-rungs` unfiltered means every
    fixture, and a test that had to pass the filter explicitly would never
    exercise the unfiltered path the live run actually takes.
    """

    def __init__(self, limit: int, odds_event_id: Any = None) -> None:
        self.limit = limit
        self.odds_event_id = odds_event_id


def _qw_db(tmp_path, quotes, events=(("E1", "KXWNBAGAME", QW_COMMENCE_MS),)):
    """Build a schema-real database holding exactly the quotes given.

    `quotes` is a list of `(event_ticker, observed_ms, ask, no_bid_qty)`, and
    optionally a 5th element overriding `yes_bid_qty` -- present so a test can
    put depth on the WRONG column and watch the query refuse it.
    """
    path = tmp_path / "cockpit.db"
    # Rebuilt from empty every call. `tmp_path` is per-test, not per-call, and a
    # test that scores several populations in a loop would otherwise accumulate
    # them -- so a row rejected on the third pass would still be counted from
    # the first, and the band tests would all read as passes.
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    for series in sorted({"KXWNBAGAME", "KXWNBASPREAD", "KXWNBATOTAL"}):
        conn.execute(
            "INSERT INTO kalshi_series (series_ticker, league, first_seen_ms, "
            "last_seen_ms) VALUES (?, 'wnba', 1, 1)",
            (series,),
        )
    for event_ticker, series, commence_ms in events:
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, "
            "commence_ms, close_ms, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, ?, NULL, 'open', 1, 1)",
            (event_ticker, series, commence_ms),
        )
    seen: set[str] = set()
    for i, quote in enumerate(quotes):
        event_ticker, observed_ms, ask, no_bid_qty = quote[:4]
        yes_bid_qty = quote[4] if len(quote) > 4 else 500.0
        ticker = f"{event_ticker}-M{i}"
        series = next(s for e, s, _ in events if e == event_ticker)
        if ticker not in seen:
            conn.execute(
                "INSERT INTO kalshi_markets (ticker, event_ticker, "
                "series_ticker, market_type, status, first_seen_ms, "
                "last_seen_ms) VALUES (?, ?, ?, 'moneyline', 'active', 1, 1)",
                (ticker, event_ticker, series),
            )
            seen.add(ticker)
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, seq, source, "
            "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
            "VALUES (?, ?, NULL, 'rest', 100, ?, ?, ?)",
            (ticker, observed_ms, yes_bid_qty, _no_bid_for(ask), no_bid_qty),
        )
    conn.commit()
    conn.close()
    return path


def _qw_score(tmp_path, quotes, series="KXWNBAGAME", events=None):
    """Score one series against Q-W over a purpose-built database."""
    path = (
        _qw_db(tmp_path, quotes)
        if events is None
        else _qw_db(tmp_path, quotes, events)
    )
    conn = connect_readonly(str(path))
    try:
        return _qw_verdict(conn, series)
    finally:
        conn.close()


def _blank_out(path, column):
    """NULL one quote column, to probe an absence the fixture cannot express."""
    conn = sqlite3.connect(path)
    conn.execute(f"UPDATE kalshi_quotes SET {column} = NULL")
    conn.commit()
    conn.close()


def _slate(n_events, n_instants, bad_instants=()):
    """`n_events` events each quoting in band at every one of `n_instants`.

    An instant listed in `bad_instants` still carries quotes -- out of band, so
    the instant stays in the pre-game denominator. An instant that vanished from
    the denominator entirely would make a failing share look like a passing one,
    which is the arithmetic the 80% bar turns on.
    """
    quotes = []
    for e in range(n_events):
        for i in range(n_instants):
            observed = _QW_WINDOW_START_MS + i * 60_000
            ask = _QW_BAND_LO - 1 if i in bad_instants else IN_BAND_ASK
            quotes.append((f"E{e}", observed, ask, 5.0))
    events = tuple((f"E{e}", "KXWNBAGAME", QW_COMMENCE_MS) for e in range(n_events))
    return quotes, events


class TestTheBandIsClosedAndHasAHoleAt300:
    """The registration's band is `270 <= ask <= 390, excluding exactly 300`.

    Mutations seen red: the `<>` at the hole dropped; `>=`/`<=` at either bound
    narrowed to `>`/`<`; the bounds applied to the raw `no_bid_tenths` instead
    of the derived ask.
    """

    def test_an_ask_at_exactly_the_hole_does_not_qualify(self, tmp_path):
        v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS, _QW_BAND_HOLE, 5.0)])
        assert v.pregame_instants == 1
        assert v.qualifying_instants == 0

    def test_one_tenth_either_side_of_the_hole_does_qualify(self, tmp_path):
        for ask in (_QW_BAND_HOLE - 1, _QW_BAND_HOLE + 1):
            v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS, ask, 5.0)])
            assert v.qualifying_instants == 1, ask

    def test_both_bounds_are_inclusive(self, tmp_path):
        for ask in (_QW_BAND_LO, _QW_BAND_HI):
            v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS, ask, 5.0)])
            assert v.qualifying_instants == 1, ask

    def test_one_tenth_outside_either_bound_does_not_qualify(self, tmp_path):
        for ask in (_QW_BAND_LO - 1, _QW_BAND_HI + 1):
            v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS, ask, 5.0)])
            assert v.qualifying_instants == 0, ask

    def test_the_band_is_applied_to_the_derived_ask_not_the_stored_bid(
        self, tmp_path
    ):
        # ask 350 is in band; the `no_bid_tenths` that produces it is 650, which
        # is outside it. A query that banded the stored column would invert.
        assert _no_bid_for(IN_BAND_ASK) > _QW_BAND_HI
        v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS, IN_BAND_ASK, 5.0)])
        assert v.qualifying_instants == 1

    def test_a_null_no_bid_is_not_readable_as_an_ask_of_1000(self, tmp_path):
        path = _qw_db(tmp_path, [("E1", _QW_WINDOW_START_MS, IN_BAND_ASK, 5.0)])
        _blank_out(path, "no_bid_tenths")
        conn = connect_readonly(str(path))
        try:
            assert _qw_verdict(conn, "KXWNBAGAME").qualifying_instants == 0
        finally:
            conn.close()


class TestDepthIsReadFromTheOpposingBid:
    """`no_bid_qty` holds `yes_ask_size` (`runner.py:1030-1037`).

    This is the trap in the whole query and it is silent: `yes_bid_qty` is
    populated on essentially every row, so a query reading depth off it passes
    almost everything. Mutation seen red: `_QW_DEPTH` switched to
    `q.yes_bid_qty` -- the first test below stays green, the second goes red.
    """

    def test_depth_below_one_at_a_banded_ask_does_not_qualify(self, tmp_path):
        v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS, IN_BAND_ASK, 0.0)])
        assert v.pregame_instants == 1
        assert v.qualifying_instants == 0

    def test_depth_on_the_yes_side_does_not_rescue_an_empty_no_side(self, tmp_path):
        v = _qw_score(
            tmp_path, [("E1", _QW_WINDOW_START_MS, IN_BAND_ASK, 0.0, 900.0)]
        )
        assert v.qualifying_instants == 0

    def test_exactly_one_contract_qualifies(self, tmp_path):
        v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS, IN_BAND_ASK, 1.0)])
        assert v.qualifying_instants == 1

    def test_a_null_depth_does_not_qualify(self, tmp_path):
        path = _qw_db(tmp_path, [("E1", _QW_WINDOW_START_MS, IN_BAND_ASK, 5.0)])
        _blank_out(path, "no_bid_qty")
        conn = connect_readonly(str(path))
        try:
            assert _qw_verdict(conn, "KXWNBAGAME").qualifying_instants == 0
        finally:
            conn.close()


class TestPreGameIsStrictlyBeforeCommenceMinusThreeHours:
    """ADR 0006: `occurrence_datetime` runs 3h late and `commence_ms` is raw.

    Mutations seen red: the offset dropped to 0; its sign flipped; `<` widened
    to `<=` at the true start.

    One mutation SURVIVED and is recorded rather than pruned. Deleting the
    `AND e.commence_ms IS NOT NULL` clause leaves the suite green, because it is
    semantically equivalent: `observed_ms < NULL - offset` evaluates to NULL,
    and SQL's three-valued logic already drops the row from the WHERE. So
    `test_an_event_with_no_commence_ms_contributes_nothing` below establishes
    the BEHAVIOUR -- an event with no determinable start contributes nothing --
    but cannot establish which of the two mechanisms produced it. The clause
    stays as documentation and as cover against a later rewrite that wraps the
    comparison in a COALESCE, where the equivalence would stop holding.
    """

    def test_one_millisecond_before_true_start_is_pre_game(self, tmp_path):
        v = _qw_score(tmp_path, [("E1", QW_TRUE_START_MS - 1, IN_BAND_ASK, 5.0)])
        assert v.pregame_instants == 1
        assert v.qualifying_instants == 1

    def test_true_start_itself_is_not_pre_game(self, tmp_path):
        v = _qw_score(tmp_path, [("E1", QW_TRUE_START_MS, IN_BAND_ASK, 5.0)])
        assert v.pregame_instants == 0

    def test_the_offset_is_three_hours_not_zero(self, tmp_path):
        # Between the true start and `commence_ms` itself: pre-game under a
        # dropped offset, in-play under the registered one.
        assert _QW_PREGAME_OFFSET_MS == 3 * 60 * 60 * 1000
        v = _qw_score(tmp_path, [("E1", QW_COMMENCE_MS - 1, IN_BAND_ASK, 5.0)])
        assert v.pregame_instants == 0

    def test_an_event_with_no_commence_ms_contributes_nothing(self, tmp_path):
        v = _qw_score(
            tmp_path,
            [("E1", _QW_WINDOW_START_MS, IN_BAND_ASK, 5.0)],
            events=(("E1", "KXWNBAGAME", None),),
        )
        assert v.pregame_instants == 0
        assert v.instant_pct is None


class TestTheWindowIsHalfOpen:
    """Four whole game-days, `[2026-08-07T00:00Z, 2026-08-11T00:00Z)`.

    Mutations seen red: `>=` at the start narrowed to `>`; `<` at the end
    widened to `<=`.
    """

    LATE_COMMENCE = _QW_WINDOW_END_MS + _QW_PREGAME_OFFSET_MS + 1

    def test_the_first_millisecond_is_inside(self, tmp_path):
        v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS, IN_BAND_ASK, 5.0)])
        assert v.qualifying_instants == 1

    def test_one_millisecond_before_the_start_is_outside(self, tmp_path):
        v = _qw_score(tmp_path, [("E1", _QW_WINDOW_START_MS - 1, IN_BAND_ASK, 5.0)])
        assert v.pregame_instants == 0

    def test_the_last_millisecond_is_inside(self, tmp_path):
        v = _qw_score(
            tmp_path,
            [("E1", _QW_WINDOW_END_MS - 1, IN_BAND_ASK, 5.0)],
            events=(("E1", "KXWNBAGAME", self.LATE_COMMENCE),),
        )
        assert v.qualifying_instants == 1

    def test_the_end_bound_itself_is_outside(self, tmp_path):
        v = _qw_score(
            tmp_path,
            [("E1", _QW_WINDOW_END_MS, IN_BAND_ASK, 5.0)],
            events=(("E1", "KXWNBAGAME", self.LATE_COMMENCE),),
        )
        assert v.pregame_instants == 0


class TestBothActivationBarsMustBeMet:
    """`W` activates iff >= 80% of pre-game instants AND >= 8 distinct events.

    Mutations seen red: `>=` at either bar softened to `>`; the two conditions
    joined by `or`; the percentage computed against qualifying instants rather
    than pre-game ones.
    """

    def test_eighty_percent_exactly_meets_the_share_bar(self, tmp_path):
        quotes, events = _slate(_QW_MIN_EVENTS, 5, bad_instants=(4,))
        v = _qw_score(tmp_path, quotes, events=events)
        assert (v.qualifying_instants, v.pregame_instants) == (4, 5)
        assert v.instant_pct == 80.0
        assert v.activates

    def test_seventy_five_percent_does_not(self, tmp_path):
        quotes, events = _slate(_QW_MIN_EVENTS, 4, bad_instants=(3,))
        v = _qw_score(tmp_path, quotes, events=events)
        assert v.instant_pct == 75.0
        assert not v.activates
        assert "instant share" in v.note

    def test_eight_events_meets_the_event_bar(self, tmp_path):
        quotes, events = _slate(_QW_MIN_EVENTS, 3)
        v = _qw_score(tmp_path, quotes, events=events)
        assert v.qualifying_events == _QW_MIN_EVENTS
        assert v.activates

    def test_seven_events_does_not_even_at_full_coverage(self, tmp_path):
        quotes, events = _slate(_QW_MIN_EVENTS - 1, 3)
        v = _qw_score(tmp_path, quotes, events=events)
        assert v.instant_pct == 100.0
        assert not v.activates
        assert "events <" in v.note

    def test_an_instant_counts_once_however_many_markets_qualify(self, tmp_path):
        quotes, events = _slate(_QW_MIN_EVENTS, 2)
        v = _qw_score(tmp_path, quotes, events=events)
        assert v.pregame_instants == 2
        assert v.qualifying_instants == 2


class TestNoPreGameInstantsIsNotAFailedBar:
    """A zero meaning "could not fire" must not read as "fired and missed".

    The repo has published one of those already (`c4bca6b`). Mutation seen red:
    the `pregame == 0` branch deleted so `instant_pct` fell through to `0.0`.
    """

    def test_the_percentage_is_none_rather_than_zero(self, tmp_path):
        assert _qw_score(tmp_path, []).instant_pct is None

    def test_it_does_not_activate(self, tmp_path):
        assert not _qw_score(tmp_path, []).activates

    def test_the_note_says_it_could_not_fire(self, tmp_path):
        assert "could not fire" in _qw_score(tmp_path, []).note


class TestTheSeriesSubstitutionOrderIsFixed:
    """`KXWNBAGAME -> KXWNBASPREAD -> KXWNBATOTAL`, first pass wins.

    Mutations seen red: the tuple reordered; the `break` on activation removed
    so a later series overwrote an earlier pass; only the deciding series
    reported instead of every one attempted.
    """

    def _verdict(self, tmp_path, quotes, events):
        path = _qw_db(tmp_path, quotes, events)
        conn = connect_readonly(str(path))
        try:
            sections = _q_kalshi_quotes_band(conn, _Args(limit=2000))
        finally:
            conn.close()
        return next(s for s in sections if "Q-W verdict" in s.title)

    def test_the_registered_order_is_exactly_these_three(self):
        assert _QW_SERIES_ORDER == ("KXWNBAGAME", "KXWNBASPREAD", "KXWNBATOTAL")

    def test_it_stops_at_the_first_series_that_activates(self, tmp_path):
        quotes, events = _slate(_QW_MIN_EVENTS, 3)
        verdict = self._verdict(tmp_path, quotes, events)
        assert [r[0] for r in verdict.rows] == ["KXWNBAGAME"]
        assert "ACTIVATES" in verdict.title

    def test_a_failing_first_series_falls_through_to_the_next(self, tmp_path):
        quotes, events = _slate(_QW_MIN_EVENTS, 3)
        events = tuple((e, "KXWNBASPREAD", c) for e, _, c in events)
        verdict = self._verdict(tmp_path, quotes, events)
        assert [r[0] for r in verdict.rows] == ["KXWNBAGAME", "KXWNBASPREAD"]
        assert verdict.rows[-1][-2] == 1

    def test_every_series_is_reported_when_none_passes(self, tmp_path):
        verdict = self._verdict(
            tmp_path, [], (("E1", "KXWNBAGAME", QW_COMMENCE_MS),)
        )
        assert [r[0] for r in verdict.rows] == list(_QW_SERIES_ORDER)
        assert "IS NOT REGISTERED" in verdict.title


class TestQWIsReachableThroughTheCommandLine:
    """The query has to be on the whitelist, not merely defined.

    Failure #12 in this repo was a 481-line instrument imported by nothing.
    """

    def test_it_is_on_the_whitelist(self):
        assert resolve_query("kalshi-quotes-band") is QUERIES["kalshi-quotes-band"]

    def test_an_end_to_end_run_publishes_the_window_and_the_verdict(
        self, tmp_path, capsys
    ):
        quotes, events = _slate(_QW_MIN_EVENTS, 3)
        path = _qw_db(tmp_path, quotes, events)
        payload = _run_json(capsys, ["kalshi-quotes-band", "--db", str(path)])
        window = _named(payload, "Q-W window")
        assert window["rows"][0][0] == _QW_WINDOW_START_MS
        assert window["rows"][0][2] == _QW_WINDOW_END_MS
        assert _named(payload, "Q-W verdict")["rows"][0][0] == "KXWNBAGAME"

    def test_the_parts_are_published_beside_the_aggregate(self, tmp_path, capsys):
        quotes, events = _slate(_QW_MIN_EVENTS, 3)
        path = _qw_db(tmp_path, quotes, events)
        payload = _run_json(capsys, ["kalshi-quotes-band", "--db", str(path)])
        assert len(_named(payload, "every pre-game polling instant")["rows"]) == 3
        assert (
            len(_named(payload, "distinct events contributing")["rows"])
            == _QW_MIN_EVENTS
        )

    def test_a_database_with_no_wnba_quotes_reports_every_series_as_unmeasured(
        self, live_db, capsys
    ):
        payload = _run_json(capsys, ["kalshi-quotes-band", "--db", str(live_db)])
        verdict = _named(payload, "Q-W verdict")
        assert [r[0] for r in verdict["rows"]] == list(_QW_SERIES_ORDER)
        assert all(r[3] is None for r in verdict["rows"])

    def test_a_zero_row_cap_does_not_take_the_verdict_out_with_it(
        self, tmp_path, capsys
    ):
        # `--limit 0` empties every capped section. The verdict is computed from
        # its own single-row aggregate for exactly this reason, so it must still
        # be there and still be right.
        quotes, events = _slate(_QW_MIN_EVENTS, 3)
        path = _qw_db(tmp_path, quotes, events)
        payload = _run_json(
            capsys, ["kalshi-quotes-band", "--db", str(path), "--limit", "0"]
        )
        verdict = _named(payload, "Q-W verdict")
        assert verdict["rows"][0][0] == "KXWNBAGAME"
        assert verdict["rows"][0][3] == 100.0


class TestTheEventSectionReportsWhatQWDoesNotFilterOn:
    """Two residuals the venue review named, printed rather than filtered.

    Neither may become a filter: both would be new registered thresholds, and
    this query is not licensed to invent one. Mutations seen red: each column
    dropped from `_SQL_QW_EVENTS`.
    """

    def _events_section(self, tmp_path, quotes, events):
        path = _qw_db(tmp_path, quotes, events)
        conn = connect_readonly(str(path))
        try:
            sections = _q_kalshi_quotes_band(conn, _Args(limit=2000))
        finally:
            conn.close()
        return next(s for s in sections if "distinct events contributing" in s.title)

    def test_how_far_ahead_each_fixture_was_is_published(self, tmp_path):
        # Q-W puts no lower bound on this, so a game ten days out counts toward
        # the 80% on equal footing with one tipping tonight. A reader has to be
        # able to see that without decoding ticker strings by hand.
        quotes, events = _slate(_QW_MIN_EVENTS, 2)
        section = self._events_section(tmp_path, quotes, events)
        for column in (
            "occurrence_ms",
            "occurrence_iso",
            "true_start_ms",
            "true_start_iso",
        ):
            assert column in section.columns, column
        assert section.rows[0][section.columns.index("occurrence_ms")] == (
            QW_COMMENCE_MS
        )

    def test_the_published_start_is_the_true_start_not_the_stored_stamp(
        self, tmp_path
    ):
        """`commence_ms` holds raw `occurrence_datetime` -- the expected END.

        A column labelled as tip-off carrying it is three hours late, and the
        first published draft of this query's output was. Mutation seen red:
        `true_start_ms` emitted without subtracting the offset.
        """
        quotes, events = _slate(_QW_MIN_EVENTS, 2)
        section = self._events_section(tmp_path, quotes, events)
        raw = section.rows[0][section.columns.index("occurrence_ms")]
        true_start = section.rows[0][section.columns.index("true_start_ms")]
        assert raw - true_start == _QW_PREGAME_OFFSET_MS
        assert true_start == QW_TRUE_START_MS
        # And the two must not be the same column wearing two names.
        assert raw != true_start

    def test_a_non_linear_cent_market_is_counted_not_silently_included(
        self, tmp_path
    ):
        # A half-cent ask inside the band rounds DOWN into the excluded hole
        # when a limit is placed, so it would read as reachable and be
        # untakeable. Expected 0 on this population; measured, not assumed.
        quotes, events = _slate(_QW_MIN_EVENTS, 1)
        path = _qw_db(tmp_path, quotes, events)
        conn = sqlite3.connect(path)
        conn.execute(
            "UPDATE kalshi_markets SET price_structure = "
            "'center_half_edge_half_cent'"
        )
        conn.commit()
        conn.close()
        ro_conn = connect_readonly(str(path))
        try:
            sections = _q_kalshi_quotes_band(ro_conn, _Args(limit=2000))
        finally:
            ro_conn.close()
        section = next(
            s for s in sections if "distinct events contributing" in s.title
        )
        idx = section.columns.index("non_linear_cent_quotes")
        assert section.rows[0][idx] == 1

    def test_an_unknown_price_structure_counts_toward_attention(self, tmp_path):
        # NULL is not evidence of `linear_cent`. It resolves toward the column
        # that gets looked at, never toward "fine".
        quotes, events = _slate(_QW_MIN_EVENTS, 1)
        section = self._events_section(tmp_path, quotes, events)
        idx = section.columns.index("non_linear_cent_quotes")
        assert section.rows[0][idx] == 1

    def test_a_linear_cent_market_does_not_count(self, tmp_path):
        quotes, events = _slate(_QW_MIN_EVENTS, 1)
        path = _qw_db(tmp_path, quotes, events)
        conn = sqlite3.connect(path)
        conn.execute("UPDATE kalshi_markets SET price_structure = 'linear_cent'")
        conn.commit()
        conn.close()
        ro_conn = connect_readonly(str(path))
        try:
            sections = _q_kalshi_quotes_band(ro_conn, _Args(limit=2000))
        finally:
            ro_conn.close()
        section = next(
            s for s in sections if "distinct events contributing" in s.title
        )
        idx = section.columns.index("non_linear_cent_quotes")
        assert section.rows[0][idx] == 0


# ---------------------------------------------------------------------------
# `prop-rungs`: the raw dump behind
# `docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md`.
#
# Every claim below is about SHAPE, not about any number. The registration puts
# all arithmetic in `scripts/analyze_prop_onesided.py` precisely so this script
# stays a reader, and these tests inherit that split: they pin what the rows
# are, never what they mean.
# ---------------------------------------------------------------------------


def _prop_db(tmp_path, rows: list[tuple]) -> Path:
    """A schema-built database holding only `odds_snapshots` prop rows.

    `rows` are `(fetched_ms, odds_event_id, bookmaker, market, outcome_name,
    outcome_description, outcome_point, price_decimal)`. Everything else on the
    table is NOT NULL filler, held constant so no test here can accidentally be
    about the team columns.
    """
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.executemany(
        "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
        "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
        "outcome_name, outcome_description, outcome_point, price_decimal) "
        "VALUES (?, ?, 'baseball_mlb', ?, 9, 'H', 'A', ?, ?, ?, ?, ?, ?)",
        [
            (fetched, fetched, event, book, market, side, player, point, price)
            for (fetched, event, book, market, side, player, point, price) in rows
        ],
    )
    conn.commit()
    conn.close()
    return path


def _rungs(path: Path, event=None, limit: int = 2000) -> Section:
    conn = connect_readonly(str(path))
    try:
        sections = _q_prop_rungs(conn, _Args(limit=limit, odds_event_id=event))
    finally:
        conn.close()
    assert len(sections) == 1
    return sections[0]


def _as_dicts(section: Section) -> list[dict[str, Any]]:
    return [dict(zip(section.columns, row)) for row in section.rows]


class TestTheTwoSidesOfARungBecomeOneRow:
    """Over and Under of one rung pivot into one row, not two.

    Mutation: drop `is_alternate` or `outcome_point` from `_SQL_PROP_RUNGS`'s
    `GROUP BY`, or replace the `MAX(CASE ...)` pivot with `p.price_decimal`.
    """

    def test_one_row_carries_both_prices(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "draftkings", "batter_hits", "Over", "A Judge", 1.5, 1.9),
                (100, "EV1", "draftkings", "batter_hits", "Under", "A Judge", 1.5, 2.0),
            ],
        )
        rows = _as_dicts(_rungs(path))
        assert len(rows) == 1
        assert rows[0]["over_price"] == 1.9
        assert rows[0]["under_price"] == 2.0
        assert rows[0]["quote_rows"] == 2

    def test_a_one_sided_rung_carries_a_null_under_not_a_zero(self, tmp_path):
        """The whole population this registration exists for.

        `None`, never `0.0`: a book that did not quote the Under has not quoted
        an infinitely long price, and this repo's rule that unreadable resolves
        to `None` is what keeps the analyzer refusing rather than substituting.
        """
        path = _prop_db(
            tmp_path,
            [
                (
                    100,
                    "EV1",
                    "fanduel",
                    "batter_hits_alternate",
                    "Over",
                    "A Judge",
                    2.5,
                    3.4,
                ),
            ],
        )
        rows = _as_dicts(_rungs(path))
        assert len(rows) == 1
        assert rows[0]["under_price"] is None
        assert rows[0]["over_price"] == 3.4

    def test_two_points_are_two_rungs(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.9),
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 2.5, 3.4),
            ],
        )
        assert len(_rungs(path).rows) == 2


class TestTheAlternateFeedFoldsButStaysDistinguishable:
    """`base_market` folds `_alternate`; `is_alternate` keeps the feeds apart.

    Both halves are load-bearing and they pull in opposite directions. The fold
    is what lets a book's primary overround be found for the same
    `(book, player, base_market)` as its alternate rungs -- §4.2 of the
    registration. The flag is what stops a primary rung and an alternate rung
    at the same point from merging into one, which would destroy the held-out
    validation set the whole measurement runs on.

    Mutation: drop the `substr(p.market, -10)` fold, or drop `is_alternate`
    from the `GROUP BY`.
    """

    def test_the_alternate_suffix_is_stripped_from_base_market(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (
                    100,
                    "EV1",
                    "fanduel",
                    "pitcher_strikeouts_alternate",
                    "Over",
                    "C Holmes",
                    7.5,
                    2.2,
                ),
            ],
        )
        row = _as_dicts(_rungs(path))[0]
        assert row["base_market"] == "pitcher_strikeouts"
        assert row["is_alternate"] == 1

    def test_a_primary_market_is_not_flagged_alternate(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (
                    100,
                    "EV1",
                    "fanduel",
                    "pitcher_strikeouts",
                    "Over",
                    "C Holmes",
                    5.5,
                    1.8,
                ),
            ],
        )
        row = _as_dicts(_rungs(path))[0]
        assert row["base_market"] == "pitcher_strikeouts"
        assert row["is_alternate"] == 0

    def test_the_same_point_on_both_feeds_stays_two_rows(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (
                    100,
                    "EV1",
                    "fanduel",
                    "pitcher_strikeouts",
                    "Over",
                    "C Holmes",
                    5.5,
                    1.8,
                ),
                (
                    100,
                    "EV1",
                    "fanduel",
                    "pitcher_strikeouts_alternate",
                    "Over",
                    "C Holmes",
                    5.5,
                    1.9,
                ),
            ],
        )
        rows = _as_dicts(_rungs(path))
        assert len(rows) == 2
        assert {r["is_alternate"] for r in rows} == {0, 1}
        assert {r["base_market"] for r in rows} == {"pitcher_strikeouts"}


class TestOnlyTheLatestSweepPerFixtureIsRead:
    """Mixing sweeps pairs a fresh price with an old one and calls it margin.

    The same rule `prop_quotes_for_event` follows, for the same reason. The
    per-fixture `MAX` rather than a global one is the part that matters: two
    fixtures swept at different times must each contribute their own latest.

    Mutation: change `latest`'s `GROUP BY odds_event_id` to a bare
    `SELECT MAX(fetched_ms)` over the whole table.
    """

    def test_an_older_sweep_of_the_same_fixture_is_absent(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.5),
                (200, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.9),
            ],
        )
        rows = _as_dicts(_rungs(path))
        assert len(rows) == 1
        assert rows[0]["over_price"] == 1.9
        assert rows[0]["fetched_ms"] == 200

    def test_each_fixture_keeps_its_own_latest(self, tmp_path):
        """EV2's only sweep is older than EV1's, and survives anyway."""
        path = _prop_db(
            tmp_path,
            [
                (100, "EV2", "fanduel", "batter_hits", "Over", "G Torres", 0.5, 1.4),
                (300, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.9),
            ],
        )
        rows = _as_dicts(_rungs(path))
        assert {r["odds_event_id"] for r in rows} == {"EV1", "EV2"}


class TestTheFixtureFilterNarrowsWithoutMovingTheSweep:
    """`--odds-event-id` restricts output; unfiltered still means everything.

    Mutations: drop the `p.odds_event_id = :event` half of the predicate (the
    filtered test goes red) or drop the `:event IS NULL OR` half (the
    unfiltered test goes red). Both halves are needed and each is pinned by a
    different test.

    **A mutation this class deliberately does NOT claim to catch:** moving the
    predicate into the `prop` CTE. It looks dangerous -- `latest` would then be
    computed over a filtered population -- but `latest` groups by
    `odds_event_id`, so no surviving fixture's maximum can move. It is a
    refactor, not a defect, and saying otherwise here would be a mutation
    nobody could ever see go red.
    """

    def test_a_filtered_run_returns_only_that_fixture(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.9),
                (100, "EV2", "fanduel", "batter_hits", "Over", "G Torres", 0.5, 1.4),
            ],
        )
        rows = _as_dicts(_rungs(path, event="EV1"))
        assert [r["odds_event_id"] for r in rows] == ["EV1"]

    def test_the_unfiltered_run_returns_both(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.9),
                (100, "EV2", "fanduel", "batter_hits", "Over", "G Torres", 0.5, 1.4),
            ],
        )
        assert len(_rungs(path).rows) == 2

    def test_a_fixture_that_is_not_there_returns_zero_rows_not_everything(
        self, tmp_path
    ):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.9),
            ],
        )
        assert _rungs(path, event="NOPE").row_count == 0

    def test_the_title_names_the_scope_it_ran_at(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.9),
            ],
        )
        assert "EV1" in _rungs(path, event="EV1").title
        assert "all fixtures" in _rungs(path).title


class TestTheExclusionsAreLeftForTheAnalyzerToCount:
    """§3 makes these exclusions *counted*. A row never emitted cannot be.

    This is the test most likely to be "fixed" by a future reader who sees that
    a price of 1.0 is obviously garbage and filters it at the source. It is
    garbage, and it must still arrive, because the registration requires the
    count of it to be reported.

    Mutation: add `AND p.price_decimal > 1.0` to `_SQL_PROP_RUNGS`.
    """

    def test_a_price_at_or_below_one_still_reaches_the_dump(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.0),
            ],
        )
        rows = _as_dicts(_rungs(path))
        assert len(rows) == 1
        assert rows[0]["over_price"] == 1.0

    def test_a_duplicated_side_is_visible_rather_than_averaged(self, tmp_path):
        """`quote_rows` is how §3's "same side twice" exclusion is detectable.

        Two Over rows for one rung give `quote_rows == 3` alongside a single
        Under, so the analyzer can drop the rung as a finding about the store.
        Without the column the duplicate is silently absorbed by `MAX`.
        """
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 1.9),
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", 1.5, 2.1),
                (100, "EV1", "fanduel", "batter_hits", "Under", "A Judge", 1.5, 2.0),
            ],
        )
        rows = _as_dicts(_rungs(path))
        assert len(rows) == 1
        assert rows[0]["quote_rows"] == 3

    def test_a_rung_with_no_point_is_dropped(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", None, 1.9),
            ],
        )
        assert _rungs(path).row_count == 0

    def test_an_outcome_that_is_neither_side_is_dropped(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Yes", "A Judge", 1.5, 1.9),
            ],
        )
        assert _rungs(path).row_count == 0


class TestTeamMarketsCannotLeakIntoThePropDump:
    """`outcome_description IS NOT NULL` is the schema's own discriminator.

    Selecting on it rather than on a hardcoded list of the ten prop market keys
    is what keeps this query from drifting out of step with `PROP_MARKETS` --
    the same argument `prop-bookmakers` makes.

    Mutation: drop the `outcome_description IS NOT NULL` predicate.
    """

    def test_an_h2h_row_is_not_a_rung(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "h2h", "Over", None, 1.5, 1.9),
            ],
        )
        assert _rungs(path).row_count == 0

    def test_a_totals_row_with_a_point_is_still_not_a_rung(self, tmp_path):
        """`totals` has Over/Under AND a point. Only the player separates it."""
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "totals", "Over", None, 8.5, 1.9),
                (100, "EV1", "fanduel", "totals", "Under", None, 8.5, 2.0),
            ],
        )
        assert _rungs(path).row_count == 0


class TestTheDumpTruncatesLoudly:
    """A prefix of the record must never read as the record.

    The live prop population is several times the default cap, so this path is
    the expected one rather than an edge case, and `analyze_prop_onesided.py`
    refuses a truncated dump on the strength of this flag.

    Mutation: `truncated=False` in `_fetch`'s `Section`.
    """

    def test_a_capped_dump_says_it_was_capped(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", p, 1.9)
                for p in (0.5, 1.5, 2.5)
            ],
        )
        section = _rungs(path, limit=2)
        assert section.row_count == 2
        assert section.truncated is True

    def test_a_dump_inside_the_cap_does_not_claim_truncation(self, tmp_path):
        path = _prop_db(
            tmp_path,
            [
                (100, "EV1", "fanduel", "batter_hits", "Over", "A Judge", p, 1.9)
                for p in (0.5, 1.5, 2.5)
            ],
        )
        assert _rungs(path, limit=3).truncated is False


def _clv_db(tmp_path, rows):
    """A database shaped like one ball game priced across several Kalshi series.

    `rows` is a list of `(series, event_ticker, odds_event_id, market_type)`.
    Everything else -- the recommendation's horizon, its scored stamp, its
    population -- is fixed, because this fixture exists to vary exactly one
    thing: how many Kalshi events sit on how many sportsbook fixtures.
    """
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 1, 1, '{}', 'seed')"
    )
    for i, (series, event, odds_event, market_type) in enumerate(rows):
        ticker = f"{event}-M{i}"
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
            "first_seen_ms, last_seen_ms) VALUES (?, 'mlb', 1, 1)",
            (series,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, "
            "commence_ms, close_ms, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, 1000, 2000, 'open', 1, 1)",
            (event, series),
        )
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
            "market_type, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, ?, ?, 'active', 1, 1)",
            (ticker, event, series, market_type),
        )
        conn.execute(
            "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
            "odds_event_id, league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, ?, 'mlb', 'test', 0, 1)",
            (event, odds_event),
        )
        link_id = conn.execute(
            "SELECT id FROM event_links WHERE kalshi_event_ticker = ?", (event,)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO recommendations (created_ms, ticker, "
            "strategy_config_version, side, entry_ask_tenths, fair_probability, "
            "edge_tenths, fee_predicted, ev_net_dollars, suggested_contracts, "
            "reference_contracts, kelly_fraction, kalshi_quote_age_ms, "
            "odds_age_ms, reason_text, link_id, clv_tenths, clv_scored_ms, "
            "clv_horizon_hours) VALUES (?, ?, 1, 'yes', 500, 0.5, 1.0, 0.01, "
            "0.01, 20, 20, 0.02, 100, 100, 'test', ?, 15.0, 999, 0.0)",
            (i, ticker, link_id),
        )
    conn.commit()
    conn.close()
    return path


def _clv_section_d(path):
    """Section D, by-population, as a dict of column -> value for its one row."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        sections = QUERIES["clv-coverage"].run(
            conn, argparse.Namespace(limit=DEFAULT_ROW_CAP)
        )
    finally:
        conn.close()
    section = next(s for s in sections if s.title.startswith("D. the gate"))
    assert section.row_count == 1, section.rows
    return dict(zip(section.columns, section.rows[0]))


class TestClvCoverageCanDetectTheClusterInflationItExistsToMeasure:
    """An instrument that cannot report the defect is decoration.

    `TestEveryWhitelistedQueryRunsAgainstTheRealSchema` already proves this
    query executes. Executing is not detecting: a section D that returned
    `clusters_now == clusters_by_game` on every input would pass that test and
    measure nothing. These vary the input and require the two columns to move
    apart, which is the whole reason the query was written (ADR 0029).
    """

    def test_one_game_across_four_series_reports_four_clusters_and_one_game(
        self, tmp_path
    ):
        """The shape Kalshi actually returns for a fully-priced ball game."""
        path = _clv_db(
            tmp_path,
            [
                ("KXMLBGAME", "KXMLBGAME-COLSTL", "ODDS-COLSTL", "moneyline"),
                ("KXMLBSPREAD", "KXMLBSPREAD-COLSTL", "ODDS-COLSTL", "spread"),
                ("KXMLBTOTAL", "KXMLBTOTAL-COLSTL", "ODDS-COLSTL", "total"),
                ("KXMLBKS", "KXMLBKS-COLSTL", "ODDS-COLSTL", "prop"),
            ],
        )
        row = _clv_section_d(path)
        assert row["rows_counted"] == 4
        assert row["clusters_now"] == 4, "the key the gate used until ADR 0029"
        assert row["clusters_by_game"] == 1, "and there is one ball game"
        assert row["unlinked_rows"] == 0

    def test_genuinely_separate_games_do_not_report_inflation(self, tmp_path):
        """The other side of the anchor.

        A section D that always showed a gap would be as useless as one that
        never did -- it would make every record look defective. Two real games
        must report the two columns equal.
        """
        path = _clv_db(
            tmp_path,
            [
                ("KXMLBGAME", "KXMLBGAME-A", "ODDS-A", "moneyline"),
                ("KXMLBGAME", "KXMLBGAME-B", "ODDS-B", "moneyline"),
            ],
        )
        row = _clv_section_d(path)
        assert row["clusters_now"] == row["clusters_by_game"] == 2

    def test_a_row_with_no_link_is_reported_rather_than_dropped(self, tmp_path):
        """An unlinked row must be visible, not silently absent.

        Section D's `clusters_by_game` falls back to a namespaced ticker, so an
        unlinked row still forms a cluster and is counted in `unlinked_rows`.
        Dropping it would understate the record and flatter the comparison.
        """
        path = _clv_db(
            tmp_path,
            [("KXMLBGAME", "KXMLBGAME-A", "ODDS-A", "moneyline")],
        )
        conn = sqlite3.connect(path)
        conn.execute("UPDATE recommendations SET link_id = NULL")
        conn.commit()
        conn.close()

        row = _clv_section_d(path)
        assert row["rows_counted"] == 1, "still counted"
        assert row["unlinked_rows"] == 1, "and flagged as unlinked"


class TestSectionDReproducesTheGateRatherThanResemblingIt:
    """`clusters_by_game` must equal what the gate itself computes.

    Section D is the instrument ADR 0029 §4 names as the only thing licensed to
    quantify the live effect. Until this test existed, its fidelity to
    `gate.clustered_clv` rested on someone reading two SQL strings side by side
    and agreeing they matched -- including a horizon constant that is
    **restated** here (`_CLV_GATE_HORIZON_HOURS`) rather than imported from
    `analysis.clv`. A restated constant is a guard only if something compares
    the two.

    Mutation: drop the `'event:'` tier from `_CLV_CLUSTER_SELECT`, or change
    `_CLV_GATE_HORIZON_HOURS`.
    """

    def _both(self, path):
        from backend import gate

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            sections = QUERIES["clv-coverage"].run(
                conn, argparse.Namespace(limit=DEFAULT_ROW_CAP)
            )
            pooled = next(s for s in sections if s.title.startswith("D. pooled"))
            row = dict(zip(pooled.columns, pooled.rows[0]))
            return row, gate.clustered_clv(conn)
        finally:
            conn.close()

    def test_the_pooled_cluster_count_equals_the_gates_own(self, tmp_path):
        path = _clv_db(
            tmp_path,
            [
                ("KXMLBGAME", "KXMLBGAME-COLSTL", "ODDS-COLSTL", "moneyline"),
                ("KXMLBKS", "KXMLBKS-COLSTL", "ODDS-COLSTL", "prop"),
                ("KXMLBGAME", "KXMLBGAME-NYYBOS", "ODDS-NYYBOS", "moneyline"),
            ],
        )
        row, stats = self._both(path)
        assert row["clusters_by_game"] == stats.n_clusters == 2
        assert row["rows_counted"] == stats.n_rows == 3

    def test_it_still_matches_when_rows_fall_to_the_event_tier(self, tmp_path):
        """The tier most likely to drift, because only the gate has three.

        An unlinked row with a live `event_ticker` groups under `event:` in the
        gate. A diagnostic that skipped that tier would split those rows by
        market ticker and report MORE clusters than the gate has -- reading as
        though the record were more inflated than it is.
        """
        path = _clv_db(
            tmp_path,
            [
                ("KXMLBGAME", "KXMLBGAME-Z", "ODDS-Z", "moneyline"),
                ("KXMLBGAME", "KXMLBGAME-Z", "ODDS-Z", "moneyline"),
            ],
        )
        conn = sqlite3.connect(path)
        conn.execute("UPDATE recommendations SET link_id = NULL")
        conn.commit()
        conn.close()

        row, stats = self._both(path)
        assert row["clusters_by_game"] == stats.n_clusters == 1
        assert row["unlinked_rows"] == stats.unclustered_rows == 2

    def test_section_g_flags_two_events_of_one_series_on_one_fixture(self, tmp_path):
        """The shape that would mean the fix merged two real games.

        `same_series_extra` must be 0 for a prop ladder and non-zero for two
        `KXMLBGAME` events sharing a fixture. Without this the instrument
        cannot tell a correct collapse from an over-collapse, which is the one
        direction section E does not check.
        """
        path = _clv_db(
            tmp_path,
            [
                ("KXMLBGAME", "KXMLBGAME-A", "ODDS-A", "moneyline"),
                ("KXMLBKS", "KXMLBKS-A", "ODDS-A", "prop"),
                ("KXMLBGAME", "KXMLBGAME-B1", "ODDS-B", "moneyline"),
                ("KXMLBGAME", "KXMLBGAME-B2", "ODDS-B", "moneyline"),
            ],
        )
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            sections = QUERIES["clv-coverage"].run(
                conn, argparse.Namespace(limit=DEFAULT_ROW_CAP)
            )
        finally:
            conn.close()
        section = next(s for s in sections if s.title.startswith("G."))
        by_key = {
            dict(zip(section.columns, r))["game_key"]: dict(zip(section.columns, r))
            for r in section.rows
        }
        assert by_key["game:ODDS-A"]["same_series_extra"] == 0, "a prop ladder is fine"
        assert by_key["game:ODDS-B"]["same_series_extra"] == 1, (
            "two KXMLBGAME events on one fixture must be flagged"
        )


# ---------------------------------------------------------------------------
# actionable-audit
# ---------------------------------------------------------------------------


def _actionable_db(tmp_path, recs: list[tuple]) -> Path:
    """A database holding one fair price and a caller-shaped set of rows.

    `recs` is `(id, suppressed_reason, reference_contracts, suggested_contracts)`
    so a test can vary only the two columns the population predicate reads and
    leave every other value fixed.
    """
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.executescript(
        """
        INSERT INTO kalshi_series (series_ticker, league, first_seen_ms, last_seen_ms)
        VALUES ('KXMLBGAME', 'mlb', 1, 1);

        INSERT INTO kalshi_events
            (event_ticker, series_ticker, commence_ms, close_ms, status,
             first_seen_ms, last_seen_ms)
        VALUES ('E1', 'KXMLBGAME', 1000, 2000, 'open', 1, 1);

        INSERT INTO kalshi_markets
            (ticker, event_ticker, series_ticker, yes_side_team, market_type,
             status, first_seen_ms, last_seen_ms)
        VALUES ('T1', 'E1', 'KXMLBGAME', 'NYM', 'moneyline', 'active', 1, 1);

        INSERT INTO strategy_configs
            (version, created_ms, effective_from_ms, config_json, rationale)
        VALUES (1, 1, 1, '{}', 'seed');

        INSERT INTO event_links
            (id, kalshi_event_ticker, odds_event_id, league, method,
             commence_skew_ms, linked_ms)
        VALUES (1, 'E1', 'OE1', 'mlb', 'exact_alias_pair', 0, 1);

        INSERT INTO fair_prices
            (id, computed_ms, link_id, market, outcome_name, p_multiplicative,
             p_additive, p_power, p_shin, p_conservative, overround,
             market_width, book_count, books_used, anchored_on_sharp)
        VALUES (7, 1234, 1, 'h2h', 'New York Mets', 0.61, 0.60, 0.605, 0.598,
                0.598, 1.04, 0.02, 5, '["pinnacle"]', 1);
        """
    )
    conn.executemany(
        "INSERT INTO recommendations "
        "(id, created_ms, strategy_config_version, ticker, fair_price_id, side, "
        " entry_ask_tenths, fair_probability, edge_tenths, fee_predicted, "
        " ev_net_dollars, kelly_fraction, suggested_contracts, "
        " reference_contracts, kalshi_quote_age_ms, odds_age_ms, "
        " suppressed_reason, reason_text) "
        "VALUES (?, ?, 1, 'T1', 7, 'yes', 550, 0.598, 12.0, 0.02, 0.3, 0.01, "
        "        ?, ?, 5000, 60000, ?, 'r')",
        [(rid, rid, sug, ref, reason) for rid, reason, ref, sug in recs],
    )
    conn.commit()
    conn.close()
    return path


def _audit(path: Path) -> list[Section]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return QUERIES["actionable-audit"].run(
            conn, argparse.Namespace(limit=DEFAULT_ROW_CAP)
        )
    finally:
        conn.close()


class TestTheAuditPopulationIsTheGatesOwn:
    """The predicate is a copy, so a test has to hold it in place.

    Mutation: change either string alone. This script cannot import `gate` --
    it runs by path on the live box with only its own directory on `sys.path`
    -- so nothing but this assertion stops the inspector from reporting a
    population the gate has stopped using.
    """

    def test_the_predicate_is_byte_identical_to_the_gates(self):
        from backend.gate import POPULATIONS

        assert _ACTIONABLE_PREDICATE == POPULATIONS["actionable"]

    def test_both_sections_use_it(self):
        assert _ACTIONABLE_PREDICATE in _SQL_ACTIONABLE_ROWS
        assert _ACTIONABLE_PREDICATE in _SQL_ACTIONABLE_FAIR


class TestOnlyRowsTheStrategyWouldHaveBetAppear:
    """A suppressed row and a zero-sized row are not evidence of a bet.

    Mutation: drop either half of the predicate. Dropping the suppression half
    admits 91; dropping the size half admits 92 and 93 -- and 93 is the one
    that matters, because a NULL `reference_contracts` must fall out rather
    than compare true.
    """

    def test_the_three_non_bets_are_excluded(self, tmp_path):
        path = _actionable_db(
            tmp_path,
            [
                (90, None, 4, 4),  # the only bet
                (91, "stale_odds", 4, 4),  # suppressed
                (92, None, 0, 0),  # sized to zero
                (93, None, None, 0),  # unreadable size
            ],
        )
        decision, provenance = _audit(path)
        assert [r[0] for r in decision.rows] == [90]
        assert [r[0] for r in provenance.rows] == [90]

    def test_the_size_at_both_bankrolls_is_printed_separately(self, tmp_path):
        """A row can be evidence at the reference bankroll and unbuyable now.

        Mutation: print only one of the columns. `reference_contracts = 3`
        with `suggested_contracts = 0` is exactly the live shape at the $100
        deposit, and collapsing them reads as a bet the operator could place.
        """
        path = _actionable_db(tmp_path, [(90, None, 3, 0)])
        decision, _ = _audit(path)
        row = dict(zip(decision.columns, decision.rows[0]))
        assert row["reference_contracts"] == 3
        assert row["suggested_contracts"] == 0

    def test_all_four_devig_readings_survive_to_the_output(self, tmp_path):
        """The spread between the methods is the noise floor the edge clears.

        Mutation: drop any `p_*` column. With only `p_conservative` printed
        there is no way to tell a real edge from method disagreement, which is
        rule 2 of this repo.
        """
        path = _actionable_db(tmp_path, [(90, None, 4, 4)])
        _, provenance = _audit(path)
        row = dict(zip(provenance.columns, provenance.rows[0]))
        assert row["p_multiplicative"] == 0.61
        assert row["p_additive"] == 0.60
        assert row["p_power"] == 0.605
        assert row["p_shin"] == 0.598
        assert row["book_count"] == 5
        assert row["anchored_on_sharp"] == 1
        assert row["market_width"] == 0.02

    def test_a_never_confirmed_row_reports_none_not_the_epoch(self, tmp_path):
        """`last_confirmed_ms` is NULL until a row is re-derived.

        Mutation: render it as 0. The audit's whole timing question is whether
        a row was confirmed after a deploy, and `1970-01-01` reads as "long
        before" rather than "never".
        """
        path = _actionable_db(tmp_path, [(90, None, 4, 4)])
        decision, _ = _audit(path)
        row = dict(zip(decision.columns, decision.rows[0]))
        assert row["last_confirmed_ms"] is None
        assert row["last_confirmed_iso"] is None
        assert row["created_iso"] == _iso(90)

    def test_an_empty_population_is_two_empty_sections_not_one(self, tmp_path):
        """Zero actionable rows is the expected state and must still print B.

        Mutation: return early when A is empty. A reader who sees one section
        cannot tell "no rows" from "the provenance join failed".
        """
        path = _actionable_db(tmp_path, [(91, "stale_odds", 4, 4)])
        sections = _audit(path)
        assert len(sections) == 2
        assert [s.row_count for s in sections] == [0, 0]
