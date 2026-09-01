"""The `fair_prices` downsample: what it keeps, and that it is the registered rule.

The most important test here is
`test_the_sql_is_section_s1_of_the_registration_byte_for_byte`. Every other
test in this file describes behaviour; that one is what makes the behaviour
*binding*, because the whole point of a pre-registration is that the rule cannot
be edited after the byte figures land. If the module's query and the document's
query can drift, nothing was registered.

Second is `TestTheFlagsRefuse`. This module deletes rows from the largest table
in the system and the shipped state is that it deletes none, so "off by default"
is a claim that has to be tested rather than commented.

What these tests do NOT establish
---------------------------------
- **Nothing about how many rows the rule would free on live.** The fixtures here
  are hand-built and tiny. The only permitted source of that figure is a dry run
  against the live database, and the registration says so.
- **Nothing about the query plan.** These tables have single-digit row counts,
  so a plan that scans is indistinguishable from one that seeks. The armed path
  ranks three window functions over the whole table and its cost on a 646 MB
  table is unmeasured here.
- **Nothing about whether deleting rows frees filesystem bytes.** That is the
  registration's section 9.4 and no test can settle it.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from backend.analysis.clv import CONTROL_HORIZON_HOURS, DEFAULT_HORIZON_HOURS
from backend.config import FairPriceDownsampleConfig
from backend.store import db, fair_price_downsample as fpd, volume

REGISTRATION = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "measurements"
    / "2026-09-01-preregistration-fair-prices-downsample.md"
)

HOUR = 3_600_000
DAY = 24 * HOUR
NOW = 1_756_742_400_000  # 2026-09-01T16:00:00Z


# ---------------------------------------------------------------------------
# Fixtures: one linked fixture, one identity, rows placed by hand.
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "downsample.db")
    yield c
    c.close()


def seed_fixture(
    conn,
    *,
    event_ticker: str = "KXMLBGAME-A",
    odds_event_id: str = "game-a",
    commence_ms: int = NOW - 30 * DAY,
    with_closing_line: bool = True,
    with_odds: bool = True,
) -> int:
    """One Kalshi event, its market, its link, its fixture start. Returns link_id."""
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, 'A at B', 0, 0)",
        (event_ticker,),
    )
    ticker = f"{event_ticker}-YES"
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
        "yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, 'A', 'moneyline', 'active', 0, 0)",
        (ticker, event_ticker),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, 'Pro Baseball', 'exact_alias_pair', 0, 0)",
        (event_ticker, odds_event_id),
    )
    if with_odds:
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
            "commence_ms, home_team, away_team, bookmaker, market, "
            "outcome_name, price_decimal) VALUES (?, 'baseball_mlb', ?, ?, "
            "'A', 'B', 'pinnacle', 'h2h', 'A', 1.6)",
            (commence_ms - DAY, odds_event_id, commence_ms),
        )
    if with_closing_line:
        conn.execute(
            "INSERT INTO closing_lines (ticker, horizon_hours, observed_ms, "
            "yes_bid_tenths, yes_ask_tenths) VALUES (?, 0.0, ?, 500, 510)",
            (ticker, commence_ms),
        )
    conn.commit()
    return conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = ?",
        (event_ticker,),
    ).fetchone()[0]


def add_fair_price(
    conn,
    *,
    link_id: int,
    computed_ms: int,
    outcome_name: str = "A",
    outcome_description=None,
    market: str = "h2h",
) -> int:
    cursor = conn.execute(
        "INSERT INTO fair_prices (computed_ms, link_id, market, outcome_name, "
        "outcome_description, p_conservative, book_count, books_used, "
        "anchored_on_sharp) VALUES (?, ?, ?, ?, ?, 0.5, 3, '[]', 0)",
        (computed_ms, link_id, market, outcome_name, outcome_description),
    )
    conn.commit()
    return cursor.lastrowid


def add_recommendation(conn, *, fair_price_id: int, ticker: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO strategy_configs (version, created_ms, "
        "effective_from_ms, config_json, rationale) "
        "VALUES (1, ?, ?, '{}', 'test')",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
        "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
        "kalshi_quote_age_ms, odds_age_ms, reason_text, fair_price_id) "
        "VALUES (?, 1, ?, 'yes', 500, 0.5, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, "
        "'No edge.', ?)",
        (NOW, ticker, fair_price_id),
    )
    conn.commit()


def eligible_ids(conn, *, now: int = NOW, retention_days: int = 14) -> set[int]:
    rows = conn.execute(
        fpd.deletable_subquery(),
        {"now_ms": now, "retention_days": retention_days},
    ).fetchall()
    return {row[0] for row in rows}


# ---------------------------------------------------------------------------
# The rule is the registered rule.
# ---------------------------------------------------------------------------


class TestTheQueryIsTheRegisteredOne:
    def test_the_sql_is_section_s1_of_the_registration_byte_for_byte(self):
        """Without this, nothing was pre-registered.

        The document is the authority: *"The implementation is checked against
        this query, not this query against the implementation."*
        """
        blocks = re.findall(
            r"```sql\n(.*?)\n```", REGISTRATION.read_text(encoding="utf-8"), re.S
        )
        assert blocks, "no fenced SQL block in the registration"
        assert fpd.REGISTERED_DELETABLE_SQL.strip() == blocks[-1].strip()

    def test_only_a_trailing_semicolon_is_stripped_to_nest_it(self):
        assert fpd.REGISTERED_DELETABLE_SQL.strip().endswith(";")
        assert not fpd.deletable_subquery().endswith(";")
        assert fpd.deletable_subquery() == fpd.REGISTERED_DELETABLE_SQL.rstrip()[:-1]

    def test_the_registered_horizons_are_the_ones_the_query_enumerates(self):
        """Two spellings of the anchor set would delete the anchor row.

        S1 spells the horizons as a literal set *so that adding one is a
        visible edit*; the module imports them from `analysis/clv.py`. This is
        the join between the two, and without it a change to `clv.py` would
        silently stop protecting the row the registered h2 reading is defined
        as.
        """
        assert fpd.CLOSING_LINE_HORIZONS_HOURS == (
            DEFAULT_HORIZON_HOURS,
            CONTROL_HORIZON_HOURS,
        )
        anchor = fpd.REGISTERED_DELETABLE_SQL.split("anchor_survivor AS (")[1]
        anchor = anchor.split("identity_newest")[0]
        for hours in fpd.CLOSING_LINE_HORIZONS_HOURS:
            assert f"SELECT {hours:.1f} AS h" in anchor, hours
        # And no others: a third horizon in the SQL that the module does not
        # know about would be an anchor nothing in code protects.
        assert anchor.count(" AS h") == len(fpd.CLOSING_LINE_HORIZONS_HOURS)

    def test_the_registered_constants_match_the_document(self):
        text = REGISTRATION.read_text(encoding="utf-8")
        assert fpd.REGISTERED_RETENTION_DAYS == 14
        assert "322,800,000" in text
        assert fpd.ARMING_THRESHOLD_BYTES == 322_800_000
        assert fpd.FAIR_PRICE_FAMILY_BYTES == 899_887_104
        assert fpd.T_MECH_THRESHOLD == 0.90
        assert fpd.P5_MAX_NO_COMMENCE_FRACTION == 0.10
        assert fpd.SENSITIVITY_RETENTION_DAYS == (7, 21, 28, 60)

    def test_the_threshold_is_two_days_of_runway_at_the_measured_rate(self):
        assert round(fpd.ARMING_THRESHOLD_BYTES / 161_400_000, 2) == 2.00


# ---------------------------------------------------------------------------
# Each condition keeps a row. Any single failure keeps it.
# ---------------------------------------------------------------------------


class TestEveryConditionKeepsARow:
    def test_a_row_inside_the_retention_window_is_kept(self, conn):
        """D1. Fourteen days is a 168x margin on the longest bounded reader."""
        link = seed_fixture(conn)
        recent = add_fair_price(conn, link_id=link, computed_ms=NOW - 2 * DAY)
        add_fair_price(conn, link_id=link, computed_ms=NOW - 2 * DAY - HOUR)
        assert recent not in eligible_ids(conn)
        assert eligible_ids(conn) == set()

    def test_a_row_a_recommendation_points_at_is_kept(self, conn):
        """D2. `/api/ledger` dereferences `fair_price_id` over the whole history."""
        link = seed_fixture(conn)
        old = NOW - 40 * DAY
        first = add_fair_price(conn, link_id=link, computed_ms=old)
        add_fair_price(conn, link_id=link, computed_ms=old + HOUR)
        add_fair_price(conn, link_id=link, computed_ms=old + 2 * HOUR)
        assert first in eligible_ids(conn)
        add_recommendation(conn, fair_price_id=first, ticker="KXMLBGAME-A-YES")
        assert first not in eligible_ids(conn)

    def test_every_row_of_a_market_with_no_closing_line_is_kept(self, conn):
        """D3. A market not yet scored keeps its whole record.

        This is what stops the rule from taking out a scoring read without
        changing any visible symptom.
        """
        link = seed_fixture(conn, with_closing_line=False)
        old = NOW - 40 * DAY
        for offset in range(6):
            add_fair_price(conn, link_id=link, computed_ms=old + offset * HOUR)
        assert eligible_ids(conn) == set()

    def test_the_newest_row_of_each_utc_day_is_kept(self, conn):
        """D4. This is the downsample: the series thins, it does not end."""
        link = seed_fixture(conn)
        # Two whole UTC days, four rows each, all older than the window and all
        # long after commence so no anchor claims them.
        day_one = NOW - 40 * DAY
        day_one -= day_one % DAY
        survivors, culled = [], []
        for day in (day_one, day_one + DAY):
            ids = [
                add_fair_price(conn, link_id=link, computed_ms=day + n * HOUR)
                for n in (1, 5, 9, 13)
            ]
            survivors.append(ids[-1])
            culled.extend(ids[:-1])
        eligible = eligible_ids(conn)
        for kept in survivors:
            assert kept not in eligible
        # The newest row overall is kept by D6 as well as D4; the rest of the
        # earlier day's rows go.
        assert set(culled) & eligible

    def test_the_last_row_before_each_registered_horizon_is_kept(self, conn):
        """D5. Both anchors, and they are different rows.

        Horizon 1.0 anchors an hour earlier than horizon 0.0, so a rule that
        implemented only the primary would delete the control's anchor and
        nothing would notice until someone ran the registered h2 reading.
        """
        commence = NOW - 40 * DAY
        link = seed_fixture(conn, commence_ms=commence)
        # Rows every 15 minutes across the last two hours before commence.
        ids = {}
        for minutes in range(120, -1, -15):
            ids[minutes] = add_fair_price(
                conn, link_id=link, computed_ms=commence - minutes * 60_000
            )
        # Plenty of later rows so D4/D6 do not do this test's work for it.
        for n in range(1, 6):
            add_fair_price(conn, link_id=link, computed_ms=commence + n * DAY)
        eligible = eligible_ids(conn)
        assert ids[0] not in eligible, "the horizon-0.0 anchor was deleted"
        assert ids[60] not in eligible, "the horizon-1.0 anchor was deleted"
        # And the rule is still doing something: the 15-minute rows between the
        # two anchors are not anchors and are not day survivors.
        assert ids[45] in eligible

    def test_the_newest_row_for_an_identity_is_never_deleted(self, conn):
        """D6. No identity can be emptied, at any age."""
        link = seed_fixture(conn)
        old = NOW - 400 * DAY
        ids = [
            add_fair_price(conn, link_id=link, computed_ms=old + n * HOUR)
            for n in range(5)
        ]
        eligible = eligible_ids(conn)
        assert ids[-1] not in eligible
        assert conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0] > len(
            eligible
        )

    def test_a_row_whose_link_is_orphaned_is_kept_explicitly(self, conn):
        """The `LEFT JOIN` is deliberate: keep by rule, not by falling out.

        The foreign key makes an orphan unreachable through normal writes, so
        it is forced here with the constraint off. That is the point: the state
        is not reachable *today*, and S1 keeps such a row **explicitly**
        (`kalshi_event_ticker IS NOT NULL`) rather than relying on an inner join
        to drop it -- because a later schema change that relaxed the constraint
        would otherwise turn a keep into a delete with nothing to notice it.

        **Two mechanisms keep it and the assertion covers both**, because
        behaviour alone cannot separate them: an orphan's
        `kalshi_event_ticker` is NULL, so D3's `IN (SELECT ...)` is NULL and the
        row is ineligible even with the explicit guard deleted. Removing the
        guard is therefore invisible to any row-level assertion -- which is
        exactly the state in which a later edit to D3 removes the last
        protection and nothing goes red. So the clause is asserted present in
        the registered text as well.
        """
        link = seed_fixture(conn)
        old = NOW - 40 * DAY
        conn.execute("PRAGMA foreign_keys = OFF")
        orphan = add_fair_price(conn, link_id=link + 999, computed_ms=old)
        conn.execute("PRAGMA foreign_keys = ON")
        for n in range(4):
            add_fair_price(conn, link_id=link, computed_ms=old + n * HOUR)
        assert orphan not in eligible_ids(conn)
        assert (
            "WHERE b.kalshi_event_ticker IS NOT NULL"
            in fpd.REGISTERED_DELETABLE_SQL
        )

    def test_a_row_with_no_computable_commence_is_kept_and_counted_by_p5(self, conn):
        """An unreadable anchor resolves to KEEP, never to DELETE.

        And P5 reports the fraction, because a keep set dominated by a join
        failure is indistinguishable from one produced by the registered rule.
        """
        link = seed_fixture(conn, with_odds=False)
        old = NOW - 40 * DAY
        for n in range(6):
            add_fair_price(conn, link_id=link, computed_ms=old + n * HOUR)
        report = fpd.plan(conn, now=NOW)
        assert report.p5_no_commence_fraction == 1.0
        assert report.p5_no_commence_fraction > fpd.P5_MAX_NO_COMMENCE_FRACTION

    def test_two_props_at_the_same_rung_are_different_identities(self, conn):
        """`outcome_description` is load-bearing and is in the partition.

        Without it, two pitchers in one game quoted at the same rung collapse
        onto one identity and one of them loses its day survivor.

        **`commence_ms` is set before the rows on purpose.** With the fixture's
        default start the anchor CTE -- whose partition also carries
        `outcome_description` -- keeps both pitchers' newest rows, and the test
        passes while saying nothing about D4. Placing the rows after commence
        takes D5 out of it, so D4 and D6 are the only things that can keep them.
        """
        link = seed_fixture(conn, commence_ms=NOW - 60 * DAY)
        old = NOW - 40 * DAY
        newest = {}
        for player in ("Holmes", "Skenes"):
            for n in range(4):
                newest[player] = add_fair_price(
                    conn,
                    link_id=link,
                    computed_ms=old + n * HOUR,
                    market="pitcher_strikeouts",
                    outcome_name="Over",
                    outcome_description=player,
                )
        eligible = eligible_ids(conn)
        for player, row_id in newest.items():
            assert row_id not in eligible, player


# ---------------------------------------------------------------------------
# Off by default is a claim, so it is tested.
# ---------------------------------------------------------------------------


def _populate_one_identity_many_times(conn, *, n: int, days: int = 1):
    """`n` observations of ONE identity, spread over `days` whole UTC days.

    This is the registration's premise built literally: the runner writes many
    `fair_prices` rows per market per day and every registered analysis reads
    one. D4 keeps the newest row per identity per UTC day, so it must keep
    exactly `days` rows and remove the other `n - days`.

    Timestamps are floored to a UTC midnight so the day count is exact rather
    than incidental -- `_populate` above spaces rows an hour apart from an
    unaligned base, which straddles a day boundary or not depending on when
    `NOW` happens to fall, and a fixture whose day count is accidental cannot
    anchor a per-day statistic.
    """
    link = seed_fixture(conn)
    day0 = ((NOW - 40 * DAY) // DAY) * DAY
    per_day = n // days
    assert per_day >= 2, "need at least two rows a day for a survivor to matter"
    written = 0
    for day in range(days):
        count = per_day if day < days - 1 else n - written
        for i in range(count):
            # Spread inside the day, never touching either boundary.
            offset = HOUR + (i * (22 * HOUR)) // max(count, 1)
            add_fair_price(conn, link_id=link, computed_ms=day0 + day * DAY + offset)
        written += count
    assert written == n
    return link


def _populate(conn):
    link = seed_fixture(conn)
    old = NOW - 40 * DAY
    for n in range(8):
        add_fair_price(conn, link_id=link, computed_ms=old + n * HOUR)
    return conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]


class TestTheFlagsRefuse:
    def test_the_shipped_default_deletes_nothing(self, conn):
        before = _populate(conn)
        assert fpd.run(conn, now=NOW, config=FairPriceDownsampleConfig()) == 0
        assert conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0] == before

    def test_enabled_but_dry_deletes_nothing(self, conn):
        before = _populate(conn)
        config = FairPriceDownsampleConfig(enabled=True, dry_run=True)
        assert fpd.run(conn, now=NOW, config=config) == 0
        assert conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0] == before

    def test_the_dry_run_says_what_it_would_have_done(self, conn, caplog):
        _populate(conn)
        config = FairPriceDownsampleConfig(enabled=True, dry_run=True)
        with caplog.at_level("INFO"):
            fpd.run(conn, now=NOW, config=config)
        assert "DRY RUN" in caplog.text
        assert "nothing was deleted" in caplog.text

    def test_only_enabled_and_not_dry_removes_a_row(self, conn):
        before = _populate(conn)
        config = FairPriceDownsampleConfig(enabled=True, dry_run=False)
        removed = fpd.run(conn, now=NOW, config=config)
        assert removed > 0
        after = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]
        assert after == before - removed

    def test_an_armed_run_removes_exactly_the_planned_set(self, conn):
        _populate(conn)
        planned = eligible_ids(conn)
        config = FairPriceDownsampleConfig(enabled=True, dry_run=False)
        fpd.run(conn, now=NOW, config=config)
        surviving = {
            row[0] for row in conn.execute("SELECT id FROM fair_prices").fetchall()
        }
        assert planned & surviving == set()

    def test_deletes_is_false_unless_both_flags_agree(self):
        assert FairPriceDownsampleConfig().deletes is False
        assert FairPriceDownsampleConfig(enabled=True).deletes is False
        assert (
            FairPriceDownsampleConfig(enabled=False, dry_run=False).deletes is False
        )
        assert FairPriceDownsampleConfig(enabled=True, dry_run=False).deletes is True


# ---------------------------------------------------------------------------
# The report refuses to invent numbers.
# ---------------------------------------------------------------------------


class TestTheReportRefusesToInventNumbers:
    def test_an_empty_table_reports_none_rather_than_zero(self, conn):
        report = fpd.plan(conn, now=NOW)
        assert report.total_rows == 0
        assert report.eligible_row_fraction is None
        assert report.estimated_freed_bytes is None
        assert report.t_mech is None
        assert report.p5_no_commence_fraction is None

    def test_the_largest_contributor_share_is_reported_beside_the_pool(self, conn):
        _populate(conn)
        report = fpd.plan(conn, now=NOW)
        assert report.per_link
        assert report.largest_link_share == 1.0

    def test_each_condition_reports_what_it_keeps_individually(self, conn):
        _populate(conn)
        report = fpd.plan(conn, now=NOW)
        for key in (
            "kept_by_d1_age",
            "kept_by_d2_referenced",
            "kept_by_d3_unscored",
            "kept_by_d4_day_survivor",
            "kept_by_d5_anchor",
            "kept_by_d6_newest",
            "kept_orphan_link",
        ):
            assert key in report.per_condition

    def test_the_sensitivity_sweep_can_never_carry_an_arming_verdict(self, conn):
        _populate(conn)
        for days in fpd.SENSITIVITY_RETENTION_DAYS:
            report = fpd.plan(conn, now=NOW, retention_days=days)
            assert report.is_registered_value is False
            assert report.verdict == "SENSITIVITY - DELETES NOTHING - CANNOT ARM"

    def test_the_registered_value_is_the_only_one_that_can_arm(self, conn):
        _populate(conn)
        report = fpd.plan(conn, now=NOW, retention_days=14)
        assert report.is_registered_value is True
        assert report.verdict != "SENSITIVITY - DELETES NOTHING - CANNOT ARM"


class TestTheVerdictFollowsTheRegisteredRule:
    def _plan(self, **kwargs):
        base = dict(
            total_rows=1_000_000,
            eligible_rows=900_000,
            eligible_row_fraction=0.9,
            estimated_freed_bytes=809_898_393,
            d123_rows=950_000,
            t_mech=0.95,
            p5_no_commence_fraction=0.0,
            per_condition={},
            per_link=(),
            closing_lines_rows=10,
            scored_event_tickers=5,
            cutoff_ms=0,
            retention_days=14,
            horizons_hours=(0.0, 1.0),
            is_registered_value=True,
        )
        base.update(kwargs)
        return fpd.DownsamplePlan(**base)

    def test_a_healthy_plan_is_eligible_to_propose_arming(self):
        assert self._plan().verdict == "ELIGIBLE TO PROPOSE ARMING"

    def test_below_the_threshold_is_not_worth_arming(self):
        assert (
            self._plan(estimated_freed_bytes=fpd.ARMING_THRESHOLD_BYTES - 1).verdict
            == "NOT WORTH ARMING"
        )

    def test_t_mech_under_ninety_percent_refutes_the_premise(self):
        assert self._plan(t_mech=0.89).verdict == "PREMISE REFUTED"

    def test_an_unmeasurable_t_mech_refutes_rather_than_passes(self):
        """`None` is not a pass. It is the absence of the check."""
        assert self._plan(t_mech=None).verdict == "PREMISE REFUTED"

    def test_an_unmeasurable_byte_estimate_does_not_arm(self):
        assert (
            self._plan(estimated_freed_bytes=None).verdict == "NOT WORTH ARMING"
        )


# ---------------------------------------------------------------------------
# The disk alarm may never fire this.
# ---------------------------------------------------------------------------


class TestTheDryRunHarness:
    """The instrument, on a synthetic fixture.

    **No number produced here is quotable.** The fixture is hand-built and
    tiny; the registration names the live dry run as the only permitted source
    of the bytes figure. What these establish is that the harness prints the
    registered things in the registered order, and refuses when a prerequisite
    fails.
    """

    def test_it_cannot_delete_because_sqlite_refuses(self, tmp_path):
        """P6, enforced rather than promised."""
        import sqlite3

        path = tmp_path / "ro.db"
        c = db.init_db(path)
        c.close()
        ro = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("DELETE FROM fair_prices")
        ro.close()

    def test_the_prerequisites_are_printed_before_any_count(self, conn):
        from scripts import dry_run_fair_price_downsample as harness

        _populate(conn)
        _plan, lines = harness.report(conn, now=NOW, retention_days=14)
        text = "\n".join(lines)
        for name in ("P1", "P2", "P3", "P4", "P5", "P6"):
            assert name in text
        assert text.index("P6") < text.index("total_rows")
        assert text.index("total_rows") < text.index("ESTIMATE")

    def test_a_failed_prerequisite_voids_the_verdict_in_the_output(self, conn):
        """P3 is the one this fixture trips, and it is the informative case.

        An empty `closing_lines` makes D3 keep every row, so the dry run reports
        0 eligible -- and 0 from an empty join is not a finding about the age
        distribution. Reporting it as one is the failure P3 exists to catch.
        """
        from scripts import dry_run_fair_price_downsample as harness

        link = seed_fixture(conn, with_closing_line=False)
        old = NOW - 40 * DAY
        for n in range(8):
            add_fair_price(conn, link_id=link, computed_ms=old + n * HOUR)
        _plan, lines = harness.report(conn, now=NOW, retention_days=14)
        text = "\n".join(lines)
        assert "P3 closing_lines resolves           NO" in text
        assert "VOID" in text

    def test_the_estimate_carries_its_assumption_on_the_same_line(self, conn):
        from scripts import dry_run_fair_price_downsample as harness

        _populate(conn)
        _plan, lines = harness.report(conn, now=NOW, retention_days=14)
        estimate_line = next(ln for ln in lines if "ESTIMATE" in ln)
        assert "uniform bytes/row" in estimate_line

    def test_an_unknown_fraction_prints_unknown_not_zero(self):
        from scripts import dry_run_fair_price_downsample as harness

        assert harness._pct(None) == "UNKNOWN"
        assert harness._pct(0.0) == "0.00%"

    def test_section_nine_is_reproduced_from_the_registration(self, conn):
        from scripts import dry_run_fair_price_downsample as harness

        _populate(conn)
        _plan, lines = harness.report(conn, now=NOW, retention_days=14)
        text = "\n".join(lines)
        assert "sub-daily resolution, ever again" in text
        assert "not found]" not in text


class TestTMechIsComputedFromRowsAndNotFromAConstructor:
    """The deciding statistic, computed by `plan()` against actual rows.

    **Every other `t_mech` assertion in this file hand-sets the field on a
    `DownsamplePlan(...)` and asserts the `verdict` property.** Not one of them
    ran `plan()` over data and checked the number that came out, so the
    direction of the statistic was verified by nothing -- and it was backwards.

    `t_mech` was `day_survivors / d123_rows`. A day survivor is the row D4
    **keeps** (§4: the deletable condition is "It is *not* the newest row for
    its identity within its own UTC day"), so the field held the KEEP fraction
    while its own docstring, the harness label `of those, removed by D4`, and
    `verdict`'s `< T_MECH_THRESHOLD` comparison all read it as the REMOVE
    fraction.

    On the 2026-09-01 deciding run that printed **1.32%** against a 90% floor
    and returned `PREMISE REFUTED`. The true removal rate was **98.68%**, which
    passes. The premise was corroborated and reported as refuted.

    The run's own output already contradicted it without needing the code:
    eligibility *requires* failing D4, so `eligible_rows / d123_rows` is a lower
    bound on the removal rate, and that was 151,642/155,248 = **97.68%**. D4
    cannot remove 1.32% of a population 97.68% of which is already marked
    deletable. One division would have caught it.
    """

    def test_a_table_that_is_the_premise_returns_a_high_removal_rate(self, conn):
        """Build the premise exactly and read the statistic back.

        One identity observed many times inside a single UTC day, aged past the
        window, unreferenced, with its event scored. D4 should keep exactly one
        row per identity-day and remove the rest -- so `t_mech` must be high,
        and the verdict must not be PREMISE REFUTED.
        """
        n = 100
        _populate_one_identity_many_times(conn, n=n, days=1)

        plan = fpd.plan(conn, now=NOW, retention_days=14)

        assert plan.d123_rows == n, (
            f"fixture did not land in the D1&D2&D3 population: "
            f"d123_rows={plan.d123_rows}, expected {n}"
        )
        assert plan.t_mech is not None
        # One survivor per identity-day out of n, so removal is (n-1)/n.
        assert plan.t_mech == pytest.approx((n - 1) / n), (
            f"t_mech={plan.t_mech!r}; if this is ~{1/n} the statistic is "
            "inverted -- it is reporting the fraction D4 KEEPS"
        )
        assert plan.t_mech >= fpd.T_MECH_THRESHOLD
        assert plan.verdict != "PREMISE REFUTED"

    def test_the_removal_rate_is_the_complement_of_the_survivor_count(self, conn):
        """Ties the statistic to the count it is derived from, in both spans.

        Two UTC days means two survivors, so removal is `(n-2)/n` rather than
        `(n-1)/n`. A test with a single day cannot tell a complement from an
        off-by-one.
        """
        n = 60
        _populate_one_identity_many_times(conn, n=n, days=2)

        plan = fpd.plan(conn, now=NOW, retention_days=14)
        survivors = plan.per_condition["kept_by_d4_day_survivor"]

        assert survivors == 2, f"expected one survivor per UTC day, got {survivors}"
        assert plan.t_mech == pytest.approx(1.0 - survivors / plan.d123_rows)
        assert plan.t_mech == pytest.approx((n - 2) / n)

    def test_the_eligible_fraction_is_a_lower_bound_on_the_removal_rate(self, conn):
        """The internal-consistency check that would have caught the inversion.

        Eligibility requires failing D4, so every eligible row is one D4
        removes. `eligible_rows / d123_rows` can therefore never exceed
        `t_mech`. Under the inverted statistic this relation broke by a factor
        of ~74 on live and nobody computed it.
        """
        _populate_one_identity_many_times(conn, n=100, days=1)

        plan = fpd.plan(conn, now=NOW, retention_days=14)

        assert plan.d123_rows > 0
        lower_bound = plan.eligible_rows / plan.d123_rows
        assert plan.t_mech >= lower_bound - 1e-9, (
            f"t_mech={plan.t_mech} is below eligible/d123={lower_bound}, which "
            "is arithmetically impossible: eligibility requires failing D4"
        )


class TestP6ChecksTheConnectionItWasHanded:
    """Amendment 1 sectionA4/sectionA7 to the registration, 2026-09-01.

    The deciding run answered **P6 = NO** with `before` 3,786,454 and `after`
    3,786,848 -- the live recorder inserting 394 rows while the report ran. The
    registered condition was `before == after`, which tested a **race**: a
    report finishing between two recorder commits answers YES, one straddling a
    commit answers NO, and neither says anything about whether the instrument
    deleted a row. A check that passes for no reason is not redeemed by also
    failing for no reason, and the passing case is the more dangerous because
    nobody audits a YES.

    The amended condition is "no row was **removed**" plus a probe that the
    connection actually refuses writes -- `mode=ro` is set in `main()`, but
    `report()` accepts any connection and the fixtures above hand it a
    **writable** one, so a prerequisite reading a constant in a different
    function was not checking the object it had.
    """

    def test_the_probe_says_no_on_a_writable_connection(self, conn):
        from scripts import dry_run_fair_price_downsample as harness

        assert harness.probe_readonly(conn) is False

    def test_the_probe_says_yes_on_a_readonly_connection(self, tmp_path):
        import sqlite3

        from scripts import dry_run_fair_price_downsample as harness

        path = tmp_path / "ro.db"
        c = db.init_db(path)
        c.close()
        ro = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            assert harness.probe_readonly(ro) is True
        finally:
            ro.close()

    def test_the_probe_deletes_nothing_when_the_connection_allows_it(self, conn):
        """The probe runs against the LIVE database, so it must be a no-op.

        `DELETE ... WHERE 0` matches no row by construction. If it ever became
        an unguarded `DELETE`, this is the test that notices -- and it is the
        whole reason the probe is a matched-nothing delete rather than an
        insert-and-rollback.
        """
        from scripts import dry_run_fair_price_downsample as harness

        _populate(conn)
        before = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]
        assert before > 0, "fixture is empty; this test would pass vacuously"
        harness.probe_readonly(conn)
        after = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]
        assert after == before

    def test_an_insert_during_the_run_no_longer_fails_p6(self, conn):
        """The exact shape that voided the deciding run.

        Rows *appearing* between the two counts are the recorder doing its job.
        Under the registered `==` this answered NO; under the amended condition
        it answers YES, and the delta is reported rather than gated on.
        """
        from scripts import dry_run_fair_price_downsample as harness

        _populate(conn)
        _plan, lines = harness.report(conn, now=NOW, retention_days=14)
        text = "\n".join(lines)
        p6 = next(line for line in lines if "P6" in line)
        assert "delta" in p6, "the delta is a required reportable"
        # The fixture is static, so the delta is 0 and P6 must pass on it.
        assert "YES" in p6, text

    def test_p6_fails_when_a_row_is_actually_removed(self, conn):
        """The condition must still be able to answer NO in its own direction."""
        from scripts import dry_run_fair_price_downsample as harness

        _populate(conn)
        before = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]

        real_plan = fpd.plan

        def plan_then_delete(c, **kwargs):
            result = real_plan(c, **kwargs)
            c.execute(
                "DELETE FROM fair_prices WHERE id = (SELECT MIN(id) FROM fair_prices)"
            )
            return result

        fpd.plan = plan_then_delete
        try:
            _plan, lines = harness.report(conn, now=NOW, retention_days=14)
        finally:
            fpd.plan = real_plan

        after = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]
        assert after == before - 1, "the mutation did not remove a row"
        p6 = next(line for line in lines if "P6" in line)
        assert "NO" in p6, p6

    def test_a_writable_connection_fails_p6_when_readonly_is_expected(self, conn):
        """sectionA7's case: the live path asserts read-only, the fixture path does not.

        `main()` passes `expect_readonly=True`; the tests above do not, which is
        what keeps the count half exercised on a writable fixture without the
        probe failing them.
        """
        from scripts import dry_run_fair_price_downsample as harness

        _populate(conn)
        _plan, lines = harness.report(
            conn, now=NOW, retention_days=14, expect_readonly=True
        )
        p6 = next(line for line in lines if "P6" in line)
        assert "NO" in p6, p6
        assert "refuses writes: NO" in p6, p6


class TestTheDiskAlarmCannotFireTheDeletion:
    """An automatic deletion fired by a disk alarm is a guard that goes off at
    the worst possible moment. Both directions are asserted, because either one
    alone leaves the wiring one import away."""

    def test_the_downsample_does_not_import_the_volume_alarm(self):
        body = inspect.getsource(fpd).split('"""', 2)[2]
        assert "import volume" not in body
        assert "store.volume" not in body
        assert "free_bytes" not in body

    def test_the_volume_alarm_does_not_import_the_downsample(self):
        body = inspect.getsource(volume).split('"""', 2)[2]
        assert "fair_price_downsample" not in body
        assert "DELETE" not in body
