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
  eight named queries run and mean what they say. Four live questions currently
  ride on this script and at least three of them need tables the whitelist does
  not touch (`kalshi_quotes`, `fair_prices`, and `recommendations` as a
  population rather than as a `--pin` subquery). A green suite is not evidence
  that a question can be answered.
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

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from scripts.inspect_live_db import (
    QUERIES,
    Section,
    UnknownQuery,
    _day_bounds,
    _derive_iso,
    _fetch,
    _iso,
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
