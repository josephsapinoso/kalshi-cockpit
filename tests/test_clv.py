"""CLV scoring tests.

CLV is the signal the live gate turns on, so two things must hold: the sign
convention has to be right for both sides, and *every* recommendation has to be
scored -- including suppressed ones, because that is what makes 300
observations reachable without 300 wagers.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    """Read against a real capture, not a hand-written dict.

    The previous tests asserted `{"yes_bid": {"close": 48}}` -- a shape Kalshi
    has never sent. The real field is `close_dollars`, a dollar string, so
    `parse_candlestick` returned `None` for both sides of every candlestick it
    ever saw. The caller correctly treats unreadable as unreadable, so this
    surfaced on the live instance as `clv_lines_stored: 20,
    unreadable_quotes: 20, scored: 0` -- closing lines fetched, none usable, and
    the CLV counter pinned at zero while every other stage reported success.

    Test and code were written from the same wrong mental model in the same
    sitting, so the suite went green over it. Third occurrence of this exact
    failure in this project, in the one module the whole measurement rests on.
    """

    @pytest.fixture(scope="class")
    def captured(self):
        path = (
            Path(__file__).parent / "fixtures" / "candlesticks_mlb.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_capture_is_real_and_has_the_shape_we_parse(self, captured):
        """Guard the fixture, so a truncated re-capture fails loudly."""
        markets = captured["markets"]
        assert len(markets) >= 3
        candles = [c for m in markets.values() for c in m["candlesticks"]]
        assert len(candles) >= 40
        assert all("yes_bid" in c and "yes_ask" in c for c in candles)

    def test_the_field_is_close_dollars_not_close(self, captured):
        """The bug, stated as a property of the wire rather than of the parser.

        If this ever fails, Kalshi renamed the field and `parse_candlestick`
        needs recapturing -- not patching from memory.
        """
        candle = next(
            c for m in captured["markets"].values() for c in m["candlesticks"]
        )
        assert "close_dollars" in candle["yes_bid"]
        assert "close" not in candle["yes_bid"]

    def test_every_captured_candle_parses(self, captured):
        """The assertion that would have caught it. Not one of them parsed."""
        parsed = unreadable = 0
        for market in captured["markets"].values():
            for candle in market["candlesticks"]:
                bid, ask = parse_candlestick(candle)
                if bid is None or ask is None:
                    unreadable += 1
                else:
                    assert 0 <= bid <= PRICE_MAX and 0 <= ask <= PRICE_MAX
                    assert ask >= bid, "ask below bid in a real book"
                    parsed += 1
        assert parsed > 0, "no captured candle produced a readable quote"
        assert unreadable == 0, f"{unreadable} of {parsed + unreadable} unreadable"

    def test_a_readable_candle_yields_a_usable_mid(self, captured):
        """What the scorer actually needs, end to end."""
        candle = next(
            c for m in captured["markets"].values() for c in m["candlesticks"]
        )
        bid, ask = parse_candlestick(candle)
        line = ClosingLine("MKT", 1.0, NOW, bid, ask)
        assert line.mid_tenths is not None
        assert bid <= line.mid_tenths <= ask

    def test_a_missing_side_returns_none_not_zero(self):
        """A settled loser genuinely trades at 0, so a substituted zero is
        indistinguishable from real data."""
        bid, ask = parse_candlestick(
            {"yes_bid": {"close_dollars": None}, "yes_ask": {}}
        )
        assert bid is None and ask is None

    def test_a_malformed_candle_returns_none(self):
        assert parse_candlestick({}) == (None, None)

    def test_the_old_key_is_not_silently_accepted(self):
        """No fallback to `close`.

        A silent second-guess is how the original error survived. If Kalshi
        renames the field again, the caller must see unreadable quotes and
        investigate rather than get a number from a key nobody verified.
        """
        assert parse_candlestick({"yes_bid": {"close": 48}, "yes_ask": {"close": 52}}) == (
            None,
            None,
        )


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


class TestTheHorizonIsRecordedWithTheScore:
    """Found by disabling: dropping `clv_horizon_hours` from the UPDATE left the
    whole suite green.

    Every fixture in this repo sets the column itself, so nothing exercised the
    production writer — the classic "the test does not reach the guard" case
    rather than an unreachable one. Without it `clv_tenths` is a bare number and
    the gate, which counts only rows at the current primary horizon, silently
    sees none of what scoring produces.
    """

    def test_scoring_stamps_the_horizon_it_used(self, conn):
        add_recommendation(conn, ask=480)
        store_closing_line(
            conn, ClosingLine("MKT", 1.0, NOW, yes_bid_tenths=510, yes_ask_tenths=530)
        )
        assert score_recommendations(conn, horizon_hours=1.0, scored_ms=NOW)["scored"] == 1

        row = conn.execute(
            "SELECT clv_horizon_hours FROM recommendations"
        ).fetchone()
        assert row["clv_horizon_hours"] == 1.0

    def test_it_stamps_zero_rather_than_leaving_it_null(self, conn):
        """The primary horizon is 0.0, which is falsy.

        A writer that skipped the column on a falsy value would leave every
        production row NULL and invisible to the gate, while this class's other
        test — which uses 1.0 — went on passing.
        """
        add_recommendation(conn, ask=480)
        store_closing_line(
            conn, ClosingLine("MKT", 0.0, NOW, yes_bid_tenths=510, yes_ask_tenths=530)
        )
        assert score_recommendations(conn, horizon_hours=0.0, scored_ms=NOW)["scored"] == 1

        row = conn.execute(
            "SELECT clv_horizon_hours FROM recommendations"
        ).fetchone()
        assert row["clv_horizon_hours"] == 0.0
        assert row["clv_horizon_hours"] is not None
