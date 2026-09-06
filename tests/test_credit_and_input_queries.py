"""The four queries a lane had to run as ad-hoc SQL, made whitelisted.

`credits-reset`, `credits-by-sport`, `credits-rate` and
`fair-prices-by-market` were added on 2026-09-06. Three of them are about the
odds bill and one is about whether a bought input is read; all four were run
over `flyctl ssh console` as hand-written SQL first, which is the "smuggle
the code in with the question" drift `scripts/inspect_live_db.py` exists to
replace.

**`credits-reset` is a correctness fix, not a convenience.** `credits-month`
reports MIN/MAX over the UTC calendar month, and the vendor's billing period
is not the calendar month -- so the window straddles a reset and its MAX can
describe a period that has ended. A reported max `used_reported` of 5,016 was
nearly read as month-to-date consumption. Nothing looked; now something does.

WHERE THE DATABASE COMES FROM
-----------------------------
`backend/store/schema.sql`, executed verbatim into a `tmp_path` file. No
`CREATE TABLE` is written here on purpose: the failure being guarded against
is a whitelisted query naming a column the live database does not have, and a
hand-written schema that agreed with the query would hide exactly that.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the live database.** Every row below was inserted here. A
  green suite says the SQL is well-formed against the shipped schema and the
  thresholds behave; it says nothing about what `/data/cockpit.db` holds.
- **Nothing about a reset having a cause.** The queries report rows either
  side of a drop. Distinguishing a billing roll from a tier purchase is a
  reading a human does from the two columns, and these tests pin that both
  columns are present, not that the reading is right.
- **Nothing about the vendor's billing period.** Its boundaries are not in
  this database at all.

MUTATIONS OBSERVED RED (2026-09-06), each restored immediately after:
- `test_a_drop_smaller_than_the_rows_own_cost_is_not_a_reset`: changed the
  threshold in `_SQL_CREDITS_RESET` from `> cost` to `> 0`, so the jitter row
  was reported as a reset.
- `test_a_reset_straddling_an_unreadable_row_is_still_found`: removed the
  `used_reported IS NOT NULL` filter, so the NULL row broke the pairing and
  a real 17-credit drop across it went unreported.
- `test_the_budget_day_boundary_is_the_flag_not_midnight`: changed the day
  offset from `--day-start-hour` to a hard-coded 0, so the 03:00Z call moved
  into the following day.
- `test_a_market_bought_and_never_consumed_shows_in_A_and_not_B`: pointed
  section B at `odds_snapshots` too, so both sections agreed and the query
  could no longer answer its own question.

**One guard was written, found green under its own mutation, and replaced.**
The NULL test above began as "a NULL cannot MANUFACTURE a drop" and stayed
green with the filter removed: SQL's three-valued logic already makes
`10 - NULL > 4` unknown, so the assertion was decoration for a property the
engine gave away free. The direction that the filter actually buys is the
opposite one -- an unreadable row must not HIDE a reset by breaking the chain
across it -- and that is what is asserted now. Recorded rather than quietly
rewritten, because a guard that passes under its own mutation is the exact
failure this repo's testing rule exists to catch, and it was caught by
following the rule rather than by noticing.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from scripts.inspect_live_db import QUERIES, main

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "store" / "schema.sql"

HOUR_MS = 3_600_000
DAY_START_HOUR = 10

#: 2026-08-27T10:00:00Z -- the start of budget day 20260827 at the default
#: boundary. Pinned rather than derived from the clock, because every row
#: below is placed relative to a boundary and a moving base would move the
#: boundary with it.
DAY_START_MS = 1_787_824_800_000


def _iso_check(ms: int) -> str:
    import datetime as _dt

    return (
        _dt.datetime.fromtimestamp(ms / 1000, _dt.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


@pytest.fixture
def db(tmp_path) -> Path:
    """The real schema with a deliberately shaped credit and price record."""
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    # api_credits, in call order. `used_reported` climbs, then falls hard
    # (a period roll), then jitters backwards by less than the row's cost.
    #
    #   (called_ms, endpoint, sport_key, cost, used_reported, remaining_reported)
    rows = [
        (DAY_START_MS + 1 * HOUR_MS, "/odds", "baseball_mlb", 4, 5000, 4996),
        (DAY_START_MS + 2 * HOUR_MS, "/odds", "baseball_mlb", 4, 5004, 4992),
        # The roll: used falls by 5,000, remaining jumps back to the tier.
        (DAY_START_MS + 3 * HOUR_MS, "/odds", "baseball_mlb", 4, 4, 19996),
        # Jitter: used falls by 2, which is below this row's own cost of 4.
        (DAY_START_MS + 4 * HOUR_MS, "/odds", "baseball_mlb", 4, 2, 19994),
        (DAY_START_MS + 5 * HOUR_MS, "/odds", "americanfootball_nfl", 6, 10,
         19990),
        # 03:00Z the NEXT calendar day, which is still budget day 20260827.
        (DAY_START_MS + 17 * HOUR_MS, "/odds", "americanfootball_nfl", 6, 17,
         19983),
    ]
    for called_ms, endpoint, sport, cost, used, remaining in rows:
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, markets,"
            " regions, cost, remaining_reported, used_reported)"
            " VALUES (?, ?, ?, 'h2h', 'us', ?, ?, ?)",
            (called_ms, endpoint, sport, cost, remaining, used),
        )
    # A row whose headers were unreadable. It must not pair with anything.
    conn.execute(
        "INSERT INTO api_credits (called_ms, endpoint, sport_key, markets,"
        " regions, cost, remaining_reported, used_reported)"
        " VALUES (?, '/odds', 'baseball_mlb', 'h2h', 'us', 4, NULL, NULL)",
        (DAY_START_MS + 6 * HOUR_MS,),
    )

    # A SECOND reset, with an unreadable row sitting inside it. This is what
    # the `used_reported IS NOT NULL` filter is actually for: skipping the
    # NULL closes the chain across it and the drop is still seen. Leave the
    # NULL in the chain and the pairing breaks in both directions, so a real
    # billing roll goes unreported -- silently, which on a query about money
    # is the worst of the available failures.
    for called_ms, used, remaining in (
        (DAY_START_MS + 12 * HOUR_MS, 20, 19980),
        (DAY_START_MS + 13 * HOUR_MS, None, None),
        (DAY_START_MS + 14 * HOUR_MS, 3, 19997),
    ):
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, markets,"
            " regions, cost, remaining_reported, used_reported)"
            " VALUES (?, '/odds', 'baseball_mlb', 'h2h', 'us', 4, ?, ?)",
            (called_ms, remaining, used),
        )

    # Six calls inside one clock hour for one sport: the cadence ceiling.
    for i in range(6):
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, markets,"
            " regions, cost, remaining_reported, used_reported)"
            " VALUES (?, '/odds', 'basketball_wnba', 'h2h', 'us', 2, ?, ?)",
            (DAY_START_MS + 8 * HOUR_MS + i * 600_000, 19989 - i, 11 + i),
        )

    # The bought/consumed pair. `spreads` is bought and never consumed.
    # Foreign keys are ON in `schema.sql`, so the parent rows are real ones.
    conn.execute(
        "INSERT INTO kalshi_series (series_ticker, title, league,"
        " first_seen_ms, last_seen_ms) VALUES ('KXMLB', 'MLB', 'mlb', ?, ?)",
        (DAY_START_MS, DAY_START_MS),
    )
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, series_ticker, title,"
        " first_seen_ms, last_seen_ms) VALUES ('KX', 'KXMLB', 'a game', ?, ?)",
        (DAY_START_MS, DAY_START_MS),
    )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id,"
        " league, method, commence_skew_ms, linked_ms)"
        " VALUES (1, 'KX', 'oe1', 'baseball_mlb', 'exact_alias_pair', 0, ?)",
        (DAY_START_MS,),
    )
    for market in ("h2h", "h2h", "spreads", "spreads", "spreads"):
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id,"
            " commence_ms, home_team, away_team, bookmaker, market,"
            " outcome_name, price_decimal)"
            " VALUES (?, 'baseball_mlb', 'oe1', ?, 'H', 'A', 'pinnacle', ?,"
            " 'H', 1.9)",
            (DAY_START_MS, DAY_START_MS + HOUR_MS, market),
        )
    conn.execute(
        "INSERT INTO fair_prices (computed_ms, link_id, market, outcome_name,"
        " p_conservative, book_count, books_used)"
        " VALUES (?, 1, 'h2h', 'H', 0.5, 3, '[]')",
        (DAY_START_MS + 60_000,),
    )
    conn.commit()
    conn.close()
    return path


def _run(capsys, argv: list[str]) -> dict[str, Any]:
    rc = main([*argv, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    return payload


def _section(payload: dict[str, Any], fragment: str) -> dict[str, Any]:
    matches = [s for s in payload["sections"] if fragment in s["title"]]
    assert len(matches) == 1, (
        f"expected one section matching {fragment!r}, got "
        f"{[s['title'] for s in payload['sections']]}"
    )
    return matches[0]


def _col(section: dict[str, Any], name: str) -> list[Any]:
    idx = section["columns"].index(name)
    return [row[idx] for row in section["rows"]]


class TestTheQueriesAreOnTheWhitelist:
    @pytest.mark.parametrize(
        "name",
        ["credits-reset", "credits-by-sport", "credits-rate",
         "fair-prices-by-market"],
    )
    def test_the_query_is_registered_with_a_description(self, name):
        assert name in QUERIES
        assert QUERIES[name].description.strip()

    @pytest.mark.parametrize(
        "name",
        ["credits-reset", "credits-by-sport", "credits-rate",
         "fair-prices-by-market"],
    )
    def test_the_query_runs_against_the_shipped_schema(self, db, capsys, name):
        """Executed against `schema.sql`, never a hand-written table.

        This is the assertion that catches a column the live database does
        not have -- here, rather than at an ssh prompt at 3am.
        """
        payload = _run(capsys, [name, "--db", str(db)])
        assert payload["sections"]

    @pytest.mark.parametrize(
        "name",
        ["credits-reset", "credits-by-sport", "credits-rate",
         "fair-prices-by-market"],
    )
    def test_the_query_runs_on_an_empty_database(self, tmp_path, capsys, name):
        """Zero rows must be a clean zero, not a crash and not a blank block."""
        path = tmp_path / "cockpit.db"
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()
        payload = _run(capsys, [name, "--db", str(path)])
        assert all(s["empty"] or s["row_count"] > 0 for s in payload["sections"])


class TestCreditsReset:
    def test_the_period_roll_is_reported_with_both_clocks(self, db, capsys):
        payload = _run(capsys, ["credits-reset", "--db", str(db)])
        section = _section(payload, "A. consecutive rows")

        drops = _col(section, "used_dropped_by")
        assert 5000 in drops, section["rows"]
        i = drops.index(5000)
        assert _col(section, "remaining_jumped_by")[i] == 15004
        assert _col(section, "prev_called_iso")[i] == _iso_check(
            DAY_START_MS + 2 * HOUR_MS
        )
        assert _col(section, "called_iso")[i] == _iso_check(
            DAY_START_MS + 3 * HOUR_MS
        )

    def test_a_drop_smaller_than_the_rows_own_cost_is_not_a_reset(
        self, db, capsys
    ):
        """The jitter row falls by 2 against a cost of 4 and must not appear.

        Two of our calls in flight can return headers in the other order. A
        `> 0` threshold would report that as a billing event.
        """
        payload = _run(capsys, ["credits-reset", "--db", str(db)])
        section = _section(payload, "A. consecutive rows")
        assert 2 not in _col(section, "used_dropped_by")

    def test_a_reset_straddling_an_unreadable_row_is_still_found(
        self, db, capsys
    ):
        """What the `used_reported IS NOT NULL` filter is actually for.

        The first version of this test asserted that a NULL cannot
        MANUFACTURE a drop, and it passed with the filter removed -- SQL's
        three-valued logic already makes `10 - NULL > 4` unknown, so the
        assertion was decoration. The real property is the other direction:
        an unreadable row sitting inside a genuine reset must not HIDE it.
        Leave the NULL in the chain and it breaks the pairing on both sides,
        and a billing roll goes unreported.

        Here `used_reported` runs 20, NULL, 3 across three consecutive rows.
        Skipping the NULL pairs 20 with 3 and reports the drop of 17.
        """
        payload = _run(capsys, ["credits-reset", "--db", str(db)])
        section = _section(payload, "A. consecutive rows")

        drops = _col(section, "used_dropped_by")
        assert 17 in drops, section["rows"]
        i = drops.index(17)
        assert _col(section, "prev_called_iso")[i] == _iso_check(
            DAY_START_MS + 12 * HOUR_MS
        )
        assert _col(section, "called_iso")[i] == _iso_check(
            DAY_START_MS + 14 * HOUR_MS
        )
        # And still no NULL anywhere in the reported pairs.
        assert None not in _col(section, "used_reported")
        assert None not in _col(section, "prev_used_reported")

    def test_only_the_two_real_resets_are_reported(self, db, capsys):
        """The jitter row and the NULL row must not add rows of their own."""
        payload = _run(capsys, ["credits-reset", "--db", str(db)])
        section = _section(payload, "A. consecutive rows")
        assert sorted(_col(section, "used_dropped_by")) == [17, 5000]

    def test_the_coverage_section_makes_an_empty_result_readable(
        self, db, capsys
    ):
        """"No reset happened" and "no header was readable" must differ."""
        payload = _run(capsys, ["credits-reset", "--db", str(db)])
        coverage = _section(payload, "B. coverage")
        assert _col(coverage, "used_null") == [2]
        assert _col(coverage, "rows_total") == [16]


class TestCreditsBySport:
    def test_the_budget_day_boundary_is_the_flag_not_midnight(self, db, capsys):
        """A 03:00Z call belongs to the previous budget day at a 10:00Z start.

        This is the whole reason the boundary exists: a late West Coast game
        shares a bucket with the rest of its night.
        """
        payload = _run(
            capsys,
            ["credits-by-sport", "--db", str(db), "--since", "20260827"],
        )
        section = _section(payload, "A. cost per budget day per sport")
        assert set(_col(section, "budget_day")) == {"20260827"}

    def test_the_parts_are_printed_beside_the_day_total(self, db, capsys):
        """CLAUDE.md forbids a pooled number without its largest contributor."""
        payload = _run(
            capsys,
            ["credits-by-sport", "--db", str(db), "--since", "20260827"],
        )
        days = _section(payload, "B. day totals")
        assert days["row_count"] == 1
        assert "top_sport" in days["columns"]
        assert "top_sport_cost" in days["columns"]
        assert "day_cost" in days["columns"]

    def test_no_share_is_computed(self, db, capsys):
        """The division is the reader's; a ratio would be a derived quantity."""
        payload = _run(
            capsys,
            ["credits-by-sport", "--db", str(db), "--since", "20260827"],
        )
        for section in payload["sections"]:
            for column in section["columns"]:
                assert "share" not in column and "pct" not in column, column

    def test_since_excludes_earlier_days(self, db, capsys):
        payload = _run(
            capsys,
            ["credits-by-sport", "--db", str(db), "--since", "20260901"],
        )
        section = _section(payload, "A. cost per budget day per sport")
        assert section["row_count"] == 0


class TestCreditsRate:
    def test_the_ten_minute_cadence_reads_as_six_calls_in_an_hour(
        self, db, capsys
    ):
        """The ceiling this query exists to expose."""
        payload = _run(
            capsys, ["credits-rate", "--db", str(db), "--since", "20260827"]
        )
        peak = _section(payload, "B. busiest hour")
        idx = peak["columns"].index("sport_key")
        wnba = [r for r in peak["rows"] if r[idx] == "basketball_wnba"]
        assert len(wnba) == 1
        assert wnba[0][peak["columns"].index("peak_calls_in_an_hour")] == 6

    def test_hours_are_utc_clock_hours_not_budget_days(self, db, capsys):
        """A rate measured across a boundary that moves with a flag is not one."""
        payload = _run(
            capsys, ["credits-rate", "--db", str(db), "--since", "20260827"]
        )
        section = _section(payload, "A. calls per UTC hour")
        for label in _col(section, "hour_utc"):
            assert label.endswith(":00Z") and "T" in label

    def test_no_mean_is_reported(self, db, capsys):
        """The denominator would be hours with no row, which are invisible."""
        payload = _run(
            capsys, ["credits-rate", "--db", str(db), "--since", "20260827"]
        )
        for section in payload["sections"]:
            for column in section["columns"]:
                assert "mean" not in column and "avg" not in column, column


class TestFairPricesByMarket:
    def test_a_market_bought_and_never_consumed_shows_in_A_and_not_B(
        self, db, capsys
    ):
        """The question the query was written for, in one assertion.

        `spreads` has three `odds_snapshots` rows and no `fair_prices` row:
        an input the feed was paid for and nothing read.
        """
        payload = _run(capsys, ["fair-prices-by-market", "--db", str(db)])
        bought = _section(payload, "A. BOUGHT")
        consumed = _section(payload, "B. CONSUMED")

        assert set(_col(bought, "market")) == {"h2h", "spreads"}
        assert set(_col(consumed, "market")) == {"h2h"}

    def test_both_sections_carry_their_own_clock(self, db, capsys):
        """A large count whose newest row is weeks old is a dead path.

        Without `last_iso` on both sides the query reports that as healthy.
        """
        payload = _run(capsys, ["fair-prices-by-market", "--db", str(db)])
        for fragment in ("A. BOUGHT", "B. CONSUMED"):
            section = _section(payload, fragment)
            assert "first_iso" in section["columns"]
            assert "last_iso" in section["columns"]

    def test_no_ratio_between_the_sections_is_printed(self, db, capsys):
        """Their row grains differ, so a ratio would invent a quantity."""
        payload = _run(capsys, ["fair-prices-by-market", "--db", str(db)])
        for section in payload["sections"]:
            for column in section["columns"]:
                assert "share" not in column and "ratio" not in column, column
