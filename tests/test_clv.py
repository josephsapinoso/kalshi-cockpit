"""CLV scoring tests.

CLV is the signal the live gate turns on, so two things must hold: the sign
convention has to be right for both sides, and *every* recommendation has to be
scored -- including suppressed ones, because that is what makes 300
observations reachable without 300 wagers.
"""

from __future__ import annotations

import pytest

from backend.analysis.clv import (
    ClosingLine,
    clv_tenths,
    horizons_agree,
    load_observations,
    parse_candlestick,
    score_recommendations,
    store_closing_line,
)
from backend.core.prices import PRICE_MAX
from backend.store import db

NOW = 1_754_800_000_000


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "clv.db")
    c.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    c.execute(
        "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('MKT', 0, 0)"
    )
    c.commit()
    yield c
    c.close()


def add_recommendation(
    conn, *, ask=480, side="yes", suppressed=None, contracts=10, created_ms=NOW
):
    """Insert a recommendation. `created_ms` defaults to `NOW`.

    Closing lines in these tests are also observed at `NOW`, so the default sits
    exactly on the `created_ms <= observed_ms` boundary — which is deliberate:
    it pins the inclusive end of the rule, and it is why every pre-existing test
    kept passing when that rule was added.
    """
    cursor = conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, ticker, "
        "side, entry_ask_tenths, fair_probability, edge_tenths, fee_predicted, "
        "ev_net_dollars, kelly_fraction, suggested_contracts, kalshi_quote_age_ms, "
        "odds_age_ms, suppressed_reason, reason_text) "
        "VALUES (?, 1, 'MKT', ?, ?, 0.5, 10.0, 0.1, 0.5, 0.02, ?, 1000, 1000, ?, 'x')",
        (created_ms, side, ask, contracts, suppressed),
    )
    conn.commit()
    return cursor.lastrowid


class TestSignConvention:
    """Getting this backwards would invert the entire measurement."""

    def test_a_yes_buy_beats_the_close_when_the_market_rises(self):
        """Bought at 48c, closed at 52c: the market moved toward you."""
        assert clv_tenths(480, 520, "yes") == pytest.approx(40)

    def test_a_yes_buy_loses_to_the_close_when_the_market_falls(self):
        assert clv_tenths(480, 440, "yes") == pytest.approx(-40)

    def test_a_no_buy_is_worth_the_complement_of_the_close(self):
        """`entry_ask_tenths` is the price paid for the side TAKEN, and
        `closing_mid_tenths` is a YES mid. So a NO position is worth
        `1000 - close`, and its CLV is that minus what it cost.

        This test previously asserted `clv_tenths(480, 520, "no") == -40`,
        matching a `entry - close` implementation. Both were wrong by
        `1000 - 2*entry` -- up to a dollar. A NO bought at 48c on a market
        closing at 52c YES is worth exactly 48c: zero CLV, not -4c.
        """
        assert clv_tenths(480, 520, "no") == pytest.approx(0)

    def test_a_no_buy_beats_the_close_when_the_yes_price_falls(self):
        # NO at 48c, YES closes at 44c -> NO worth 56c -> +8c.
        assert clv_tenths(480, 440, "no") == pytest.approx(80)

    def test_a_no_buy_loses_when_the_yes_price_rises(self):
        # NO at 48c, YES closes at 60c -> NO worth 40c -> -8c.
        assert clv_tenths(480, 600, "no") == pytest.approx(-80)

    def test_both_sides_of_a_fairly_priced_market_score_zero(self):
        """The anchor that discriminates. If YES and NO are both bought at the
        price the market closes at, neither beat it -- and only the correct
        convention gives zero for both. The old `entry - close` form scored
        +30 on the NO side here while the YES side scored 0.

        A test at 50c cannot catch this, because the error term
        `1000 - 2*entry` vanishes at exactly 50c.
        """
        close = 650
        assert clv_tenths(close, close, "yes") == pytest.approx(0)
        assert clv_tenths(PRICE_MAX - close, close, "no") == pytest.approx(0)

    def test_the_two_sides_are_not_mirror_images_of_each_other(self):
        """Buying YES at 48c and NO at 48c are different bets on the same
        market, not opposite ones -- both are wagers that their own side is
        underpriced, and both can beat the close."""
        assert clv_tenths(480, 440, "yes") < 0
        assert clv_tenths(480, 440, "no") > 0

    def test_an_unknown_side_raises(self):
        with pytest.raises(ValueError):
            clv_tenths(480, 520, "maybe")


class TestCandlestickParsing:
    def test_whole_cent_closes_convert_to_tenths(self):
        bid, ask = parse_candlestick({"yes_bid": {"close": 48}, "yes_ask": {"close": 52}})
        assert (bid, ask) == (480, 520)

    def test_a_missing_side_returns_none_not_zero(self):
        """A settled loser genuinely trades at 0, so a substituted zero is
        indistinguishable from real data."""
        bid, ask = parse_candlestick({"yes_bid": {"close": None}, "yes_ask": {}})
        assert bid is None and ask is None

    def test_a_malformed_candle_returns_none(self):
        assert parse_candlestick({}) == (None, None)


class TestScoring:
    def test_scores_a_recommendation_against_the_close(self, conn):
        add_recommendation(conn, ask=480)
        store_closing_line(
            conn, ClosingLine("MKT", 1.0, NOW, yes_bid_tenths=510, yes_ask_tenths=530)
        )
        counts = score_recommendations(conn, horizon_hours=1.0, scored_ms=NOW)
        assert counts["scored"] == 1

        row = conn.execute("SELECT clv_tenths FROM recommendations").fetchone()
        assert row["clv_tenths"] == pytest.approx(40.0)  # mid 520 - ask 480

    def test_suppressed_recommendations_are_scored_too(self, conn):
        """The whole reason 300 observations is reachable without 300 wagers.

        It also makes suppression rules auditable: if rows rejected for
        `wide_market` had good CLV, that rule is costing money.
        """
        add_recommendation(conn, suppressed="wide_market", contracts=0)
        store_closing_line(
            conn, ClosingLine("MKT", 1.0, NOW, yes_bid_tenths=510, yes_ask_tenths=530)
        )
        assert score_recommendations(conn, horizon_hours=1.0)["scored"] == 1

    def test_scoring_is_not_repeated(self, conn):
        add_recommendation(conn)
        store_closing_line(
            conn, ClosingLine("MKT", 1.0, NOW, yes_bid_tenths=510, yes_ask_tenths=530)
        )
        score_recommendations(conn, horizon_hours=1.0)
        assert score_recommendations(conn, horizon_hours=1.0)["scored"] == 0

    def test_an_unreadable_close_is_skipped_not_scored_as_zero(self, conn):
        add_recommendation(conn)
        store_closing_line(
            conn, ClosingLine("MKT", 1.0, NOW, yes_bid_tenths=None, yes_ask_tenths=None)
        )
        counts = score_recommendations(conn, horizon_hours=1.0)
        assert counts["scored"] == 0
        assert counts["skipped_no_mid"] == 1

    def test_storing_a_closing_line_is_idempotent_per_horizon(self, conn):
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 500, 520))
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW + 1, 505, 525))
        rows = conn.execute("SELECT * FROM closing_lines").fetchall()
        assert len(rows) == 1
        assert rows[0]["yes_bid_tenths"] == 505


class TestHorizonComparison:
    """If the result moves between horizons, it was convergence, not edge."""

    def test_reports_agreement_when_both_horizons_match(self, conn):
        add_recommendation(conn, ask=480)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 510, 530))
        store_closing_line(conn, ClosingLine("MKT", 6.0, NOW, 508, 528))
        result = horizons_agree(conn, primary=1.0, control=6.0)
        assert result["consistent"]

    def test_flags_a_result_that_moves_between_horizons(self, conn):
        add_recommendation(conn, ask=480)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 510, 530))
        store_closing_line(conn, ClosingLine("MKT", 6.0, NOW, 400, 420))
        result = horizons_agree(conn, primary=1.0, control=6.0)
        assert not result["consistent"]
        assert "convergence" in result["note"]

    def test_returns_none_when_a_horizon_has_no_data(self, conn):
        """An honest 'cannot tell' rather than a fabricated comparison."""
        add_recommendation(conn)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 510, 530))
        assert horizons_agree(conn, primary=1.0, control=6.0) is None


class TestLoadingForAnalysis:
    def test_loads_scored_rows_as_observations(self, conn):
        add_recommendation(conn, ask=480)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 510, 530))
        score_recommendations(conn, horizon_hours=1.0)

        observations = load_observations(conn)
        assert len(observations) == 1
        assert observations[0].entry_ask_tenths == 480
        assert observations[0].clv_tenths == pytest.approx(40.0)

    def test_unscored_rows_are_excluded(self, conn):
        add_recommendation(conn)
        assert load_observations(conn) == []

    def test_can_group_by_suppression_reason(self, conn):
        """So a rule can be audited: did the rows it rejected have good CLV?"""
        add_recommendation(conn, suppressed="wide_market", contracts=0)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 510, 530))
        score_recommendations(conn, horizon_hours=1.0)

        observations = load_observations(conn, group_by="suppressed")
        assert observations[0].group == "wide_market"


class TestTheEntryMustPrecedeTheClose:
    """A recommendation cannot be scored against a price that predated it.

    The closing line is read at `commence - horizon` and the runner records
    right up to kickoff, so at a 1h horizon every recommendation made in the
    final hour would be scored against a quote observed before the decision
    existed. Whether that flatters or punishes depends entirely on which way the
    market drifted in between — so it injects drift straight into the
    measurement built to detect edge.

    This is live-data contamination, not a hypothetical: the deployed runner
    writes rows at 15-minute intervals right up to commence.
    """

    def test_a_recommendation_made_after_the_close_is_not_scored(self, conn):
        add_recommendation(conn, ask=480, created_ms=NOW + 60_000)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 500, 520))

        counts = score_recommendations(conn, horizon_hours=1.0)

        assert counts["scored"] == 0
        assert counts["skipped_entry_after_close"] == 1
        row = conn.execute("SELECT clv_tenths FROM recommendations").fetchone()
        assert row["clv_tenths"] is None, "scored against a price that predated it"

    def test_a_recommendation_made_before_the_close_is_scored(self, conn):
        add_recommendation(conn, ask=480, created_ms=NOW - 60_000)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 500, 520))

        counts = score_recommendations(conn, horizon_hours=1.0)

        assert counts["scored"] == 1
        assert counts["skipped_entry_after_close"] == 0

    def test_the_boundary_is_inclusive(self, conn):
        """Created at exactly the observation instant is scoreable.

        Fixed by definition rather than by taste: the quote existed at that
        moment, so there is nothing anachronistic about comparing against it.
        A strict `<` would silently drop every row whose timestamps happened to
        coincide — which, with a runner and a scorer that share one clock, is
        not a rare case.
        """
        add_recommendation(conn, ask=480, created_ms=NOW)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 500, 520))

        assert score_recommendations(conn, horizon_hours=1.0)["scored"] == 1

    def test_the_exclusion_is_reported_not_silent(self, conn):
        """A dropped observation must be countable.

        Silently excluding late rows would shrink the sample toward early
        recommendations with nothing saying so, and the gate counts what it is
        given.
        """
        for offset in (-60_000, +60_000, +120_000):
            add_recommendation(conn, ask=480, created_ms=NOW + offset)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 500, 520))

        counts = score_recommendations(conn, horizon_hours=1.0)
        assert (counts["scored"], counts["skipped_entry_after_close"]) == (1, 2)

    def test_a_late_row_stays_unscored_and_available(self, conn):
        """Excluded at this horizon, not consumed.

        `clv_scored_ms` must stay NULL so the row remains a candidate for a
        shorter horizon rather than being burned.
        """
        rec_id = add_recommendation(conn, ask=480, created_ms=NOW + 60_000)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 500, 520))
        score_recommendations(conn, horizon_hours=1.0)

        row = conn.execute(
            "SELECT clv_scored_ms, closing_line_id FROM recommendations WHERE id = ?",
            (rec_id,),
        ).fetchone()
        assert row["clv_scored_ms"] is None
        assert row["closing_line_id"] is None

    def test_horizons_agree_applies_the_same_rule(self, conn):
        """It matters more there: the 6h line is observed five hours earlier.

        Without the rule the two horizons would compare different populations —
        the longer one excluding more late rows — so part of the measured
        "drift" would just be a change in which rows were counted.
        """
        add_recommendation(conn, ask=480, created_ms=NOW + 60_000)
        store_closing_line(conn, ClosingLine("MKT", 1.0, NOW, 510, 530))
        store_closing_line(conn, ClosingLine("MKT", 6.0, NOW, 508, 528))

        assert horizons_agree(conn, primary=1.0, control=6.0) is None, (
            "a row created after both observations was still compared"
        )
