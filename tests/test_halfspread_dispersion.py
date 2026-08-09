"""Pins for `scripts/measure_halfspread_dispersion.py`.

The script exists to answer one question -- how much does the Kalshi half-spread
*vary* on the population the CLV signal test scores -- and it answers it with a
number that is almost zero. A near-zero answer is the easiest kind to produce by
accident: a reader that cannot represent a wide spread, a filter that removes
every non-constant bar, or an `n` that counts one market's 180 minutes as 180
observations all give the same flattering shape.

So these tests are aimed at the ways the zero could be fake, not at the
arithmetic:

- the tick floor is read from `price_ranges`, so "constant" can be told apart
  from "censored";
- the half-spread comes from the derived ask, and a payload whose published ask
  disagrees is **flagged**, not quietly averaged;
- every candlestick bar is either kept or counted as a drop, so the filter
  cannot silently discard the wide ones;
- `n` collapses to markets and to games, and duplicating the record `k` times
  leaves the per-game distribution bit-identical -- the old
  one-observation-recorded-thirty-times bug stated as an invariant;
- the selection bound really is a bound: no reweighting of the observed values
  beats it, checked by brute force rather than by algebra.

Wire-format assertions load `tests/fixtures/candlesticks_pregame_mlb.json` and
`tests/fixtures/events_sports_nested.json`, both captured from the live API.
Nothing here is hand-constructed except deliberate mutations of a captured
payload, which is how the failure branches get reached at all.

What these tests do NOT establish
---------------------------------
That the measured number is right. They establish that the harness would have
reported a wide spread had it seen one, and that its `n` means what it says.
Whether the exchange actually quotes one tick pre-game is a fact about the
exchange, and only the live run answers it.
"""

from __future__ import annotations

import copy
import random

import pytest

from conftest import load_fixture
from scripts.measure_halfspread_dispersion import (
    analyse,
    candlestick_rows,
    describe,
    percentile,
    read_live_market,
    selection_bound,
    tick_tenths,
    true_start_ms,
)

CANDLE_FIXTURE = "candlesticks_pregame_mlb.json"


@pytest.fixture
def captured():
    return load_fixture(CANDLE_FIXTURE)


@pytest.fixture
def captured_market(captured):
    return copy.deepcopy(captured["market"])


class StubClient:
    """Returns one captured payload, so the bar filter can be tested offline."""

    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.calls: list[str] = []

    def get(self, url, params=None):
        self.calls.append(url)
        return self

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _rows_from(payload, market, *, start_ms, window_minutes=180):
    drops: dict[str, int] = {}
    drops.setdefault("bars_seen", 0)
    counter = _Counter(drops)
    rows, outcome = candlestick_rows(
        StubClient(payload),
        series="KXMLBGAME",
        market=market,
        event_ticker="EVT",
        league="Pro Baseball",
        market_type="moneyline",
        start_ms=start_ms,
        window_minutes=window_minutes,
        drops=counter,
    )
    return rows, outcome, counter


class _Counter(dict):
    """`defaultdict(int)` without importing one into the test's namespace."""

    def __missing__(self, key):
        return 0


class TestTheTickFloorIsReadFromPriceRanges:
    """A constant spread is only a finding if the floor is known."""

    def test_a_captured_game_market_reports_a_ten_tenth_step(self, captured_market):
        assert tick_tenths(captured_market) == 10
        # The label agrees today, and is deliberately not what was read.
        assert captured_market["price_level_structure"] == "linear_cent"

    def test_the_label_is_not_consulted(self, captured_market):
        captured_market["price_level_structure"] = "something_kalshi_invents_later"
        assert tick_tenths(captured_market) == 10

    def test_a_half_cent_grid_reports_five_tenths(self, captured_market):
        captured_market["price_ranges"] = [
            {"start": "0.0000", "end": "1.0000", "step": "0.0050"}
        ]
        assert tick_tenths(captured_market) == 5

    def test_a_grid_finer_than_a_tenth_returns_none_never_zero(self, captured_market):
        captured_market["price_ranges"] = [
            {"start": "0.0000", "end": "1.0000", "step": "0.00001"}
        ]
        assert tick_tenths(captured_market) is None

    def test_a_market_with_no_bands_returns_none(self, captured_market):
        captured_market.pop("price_ranges", None)
        assert tick_tenths(captured_market) is None


class TestTheStartTimeIsInferredOnlyWhenTheFieldsAgree:
    """ADR 0006: `occurrence_datetime` is the expected END on a game market."""

    def test_a_game_market_starts_three_hours_before_its_expected_end(
        self, captured, captured_market
    ):
        assert (
            captured_market["occurrence_datetime"]
            == captured_market["expected_expiration_time"]
        )
        assert true_start_ms(captured_market) == captured["true_start_ms"]

    def test_a_series_whose_occurrence_is_not_the_end_is_taken_at_face_value(
        self, captured_market
    ):
        # `KXMLBF5`'s occurrence sits two hours BEYOND its expected expiration.
        # Subtracting a game length there produced a start time after the market
        # had already closed (ADR 0006 §1), so the subtraction must not fire.
        captured_market["expected_expiration_time"] = "2026-08-09T18:00:00Z"
        captured_market["occurrence_datetime"] = "2026-08-09T20:00:00Z"
        # 2026-08-09T20:00:00Z taken as-is. Had the subtraction fired it would
        # be 17:00Z, 1786294800000 -- a different number, which is the point.
        assert true_start_ms(captured_market) == 1786305600000

    def test_a_market_with_no_occurrence_returns_none(self, captured_market):
        captured_market["occurrence_datetime"] = None
        assert true_start_ms(captured_market) is None


class TestTheHalfSpreadComesFromTheDerivedAsk:
    """`yes_ask = 1000 - no_bid`, and a payload that disagrees is flagged."""

    def _read(self, market):
        return read_live_market(
            market,
            event={"event_ticker": "EVT"},
            league="Pro Baseball",
            market_type="moneyline",
            in_scope=True,
            series="KXMLBGAME",
            now_ms=0,
        )

    def test_the_captured_market_satisfies_the_identity(self, captured_market):
        row = self._read(captured_market)
        assert row["identity_checked"] is True
        assert row["identity_ok"] is True
        assert row["half_spread_tenths"] == (
            row["yes_ask_tenths"] - row["yes_bid_tenths"]
        ) / 2

    def test_a_published_ask_that_disagrees_is_flagged_not_averaged(
        self, captured_market
    ):
        # The whole half-spread column rests on this identity. If Kalshi ever
        # stops publishing a derivable ask, the run must say so rather than
        # keep reporting a plausible number.
        captured_market["yes_ask_dollars"] = "0.9900"
        row = self._read(captured_market)
        assert row["identity_checked"] is True
        assert row["identity_ok"] is False

    def test_a_missing_ask_field_is_unchecked_not_a_violation(self, captured_market):
        captured_market.pop("yes_ask_dollars", None)
        row = self._read(captured_market)
        assert row["identity_checked"] is False

    def test_a_zero_no_bid_is_readable_but_not_two_sided(self, captured_market):
        # Nobody is offering YES at any price, so the derived ask of $1.00 is a
        # fiction. It must be visible as such rather than entering the
        # distribution as a real 100c quote.
        captured_market["no_bid_dollars"] = "0.0000"
        row = self._read(captured_market)
        assert row is not None
        assert row["two_sided"] is False
        assert row["yes_ask_tenths"] == 1000

    def test_an_unreadable_bid_returns_none_never_zero(self, captured_market):
        captured_market["yes_bid_dollars"] = "not a price"
        assert self._read(captured_market) is None


class TestEveryCandlestickBarIsKeptOrCounted:
    """A filter that silently drops the wide bars produces this script's answer."""

    def test_the_captured_window_parses_and_every_bar_is_accounted_for(
        self, captured, captured_market
    ):
        payload = captured["candlesticks_response"]
        rows, outcome, drops = _rows_from(
            payload, captured_market, start_ms=captured["true_start_ms"]
        )
        assert outcome == "ok"
        assert rows, "the captured pre-game window parsed to nothing"
        dropped = (
            drops["dropped_missing_side"]
            + drops["dropped_no_yes_bid"]
            + drops["dropped_no_no_bid"]
            + drops["dropped_crossed_or_locked"]
        )
        assert drops["bars_seen"] == len(payload["candlesticks"])
        assert len(rows) + dropped == drops["bars_seen"]

    def test_a_bar_with_no_no_bid_is_dropped_not_read_as_a_hundred_cent_spread(
        self, captured, captured_market
    ):
        payload = copy.deepcopy(captured["candlesticks_response"])
        payload["candlesticks"][0]["yes_ask"]["close_dollars"] = "1.0000"
        rows, _, drops = _rows_from(
            payload, captured_market, start_ms=captured["true_start_ms"]
        )
        assert drops["dropped_no_no_bid"] == 1
        assert all(r["yes_ask_tenths"] < 1000 for r in rows)

    def test_a_bar_with_no_yes_bid_is_dropped(self, captured, captured_market):
        payload = copy.deepcopy(captured["candlesticks_response"])
        payload["candlesticks"][0]["yes_bid"]["close_dollars"] = "0.0000"
        rows, _, drops = _rows_from(
            payload, captured_market, start_ms=captured["true_start_ms"]
        )
        assert drops["dropped_no_yes_bid"] == 1

    def test_a_wide_bar_is_kept_and_counted_as_wide(self, captured, captured_market):
        # The load-bearing one. If this bar came back at one tick, or vanished,
        # the script's near-zero dispersion would be an artefact of its own
        # reader and the whole write-up would be void.
        payload = copy.deepcopy(captured["candlesticks_response"])
        bar = payload["candlesticks"][0]
        bid = bar["yes_bid"]["close_dollars"]
        bar["yes_ask"]["close_dollars"] = f"{float(bid) + 0.07:.4f}"
        rows, _, drops = _rows_from(
            payload, captured_market, start_ms=captured["true_start_ms"]
        )
        assert drops["kept_wider_than_one_tick"] == 1
        assert max(r["half_spread_tenths"] for r in rows) == 35.0

    def test_an_empty_response_is_no_bars_not_a_zero_spread(self, captured_market):
        rows, outcome, _ = _rows_from(
            {"candlesticks": []}, captured_market, start_ms=0
        )
        assert outcome == "no_bars"
        assert rows == []


class TestNIsCountedInUnitsThatAreIndependent:
    """One observation recorded thirty times is one observation."""

    def _rows(self, half_spreads, *, ticker="T", event="E"):
        return [
            {
                "ticker": ticker,
                "event_ticker": event,
                "league": "Pro Baseball",
                "market_type": "moneyline",
                "structure": "linear_cent",
                "tick_tenths": 10,
                "yes_bid_tenths": 500,
                "yes_ask_tenths": 500 + int(2 * value),
                "spread_tenths": int(2 * value),
                "half_spread_tenths": float(value),
                "two_sided": True,
                "identity_checked": False,
                "identity_ok": False,
                "minutes_to_start": 30.0,
            }
            for value in half_spreads
        ]

    def test_one_market_polled_many_times_is_one_market(self):
        result = analyse(self._rows([5.0] * 180))
        assert result["n_observations"] == 180
        assert result["n_markets"] == 1
        assert result["n_games"] == 1

    def test_two_sides_of_one_game_are_one_game(self):
        rows = self._rows([5.0] * 10, ticker="A") + self._rows([10.0] * 10, ticker="B")
        result = analyse(rows)
        assert result["n_markets"] == 2
        assert result["n_games"] == 1

    def test_duplicating_the_record_leaves_the_per_game_view_unchanged(self):
        rows = (
            self._rows([5.0, 5.0, 10.0], ticker="A", event="E1")
            + self._rows([5.0, 15.0], ticker="B", event="E2")
        )
        once = analyse(rows)
        thrice = analyse(rows * 3)
        assert thrice["per_game"] == once["per_game"]
        assert thrice["per_market"] == once["per_market"]
        # And the naive count does move, which is what makes the pin meaningful.
        assert thrice["n_observations"] == 3 * once["n_observations"]

    def test_a_market_that_blows_out_for_one_minute_does_not_move_its_own_level(self):
        # Median per market, not mean: one bad minute is a percentile, not a
        # level.
        rows = self._rows([5.0] * 179 + [500.0])
        assert analyse(rows)["per_market"]["max"] == 5.0
        assert analyse(rows)["overall"]["max"] == 500.0


class TestPercentilesUseNearestRank:
    def test_p100_is_the_max(self):
        assert percentile([1.0, 2.0, 3.0], 100) == 3.0

    def test_p99_on_a_small_sample_is_the_max_not_an_interpolation(self):
        assert percentile([1.0, 2.0, 3.0], 99) == 3.0

    def test_p50_of_an_even_sample_does_not_average_the_middle_pair(self):
        assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0

    def test_an_empty_sample_returns_none_never_zero(self):
        assert percentile([], 50) is None
        assert describe([]) == {"n": 0}

    def test_a_constant_sample_reports_one_distinct_value(self):
        stats = describe([5.0] * 100)
        assert stats["sd"] == 0.0
        assert stats["distinct"] == 1


class TestTheSelectionBoundCannotBeBeatenByAnyCut:
    """The bound is what stands in for the cut this harness may not measure."""

    def test_the_worst_case_sd_is_half_the_range(self):
        bound = selection_bound([5.0] * 999 + [10.0])
        assert bound["worst_case_sd"] == pytest.approx(2.5)
        assert bound["support"] == [5.0, 10.0]
        assert bound["observed_wide_fraction"] == pytest.approx(0.001)

    def test_no_random_reweighting_beats_the_bound(self):
        # Brute force rather than algebra: a bound argued for in prose is a
        # bound nobody checked. Every subset of the observed support, at every
        # mixing proportion, must come in under it.
        import statistics

        values = [5.0] * 999 + [10.0]
        bound = selection_bound(values)
        rng = random.Random(20260809)
        for _ in range(400):
            wide = rng.randint(0, 200)
            sample = [5.0] * (200 - wide) + [10.0] * wide
            if len(sample) < 2:
                continue
            assert statistics.pstdev(sample) <= bound["worst_case_sd"] + 1e-9

    def test_a_constant_population_bounds_the_slope_at_zero(self):
        bound = selection_bound([5.0] * 500)
        assert bound["worst_case_sd"] == 0.0
        assert bound["worst_case_slope_by_sd_edge"]["10"] == 0.0

    def test_the_bound_is_reported_on_the_analysis(self):
        rows = [
            {
                "ticker": f"T{i}",
                "event_ticker": f"E{i}",
                "league": "Pro Baseball",
                "market_type": "moneyline",
                "structure": "linear_cent",
                "tick_tenths": 10,
                "yes_bid_tenths": 500,
                "yes_ask_tenths": 510,
                "spread_tenths": 10,
                "half_spread_tenths": 5.0,
                "two_sided": True,
                "identity_checked": False,
                "identity_ok": False,
                "minutes_to_start": 30.0,
            }
            for i in range(10)
        ]
        assert analyse(rows)["selection_bound"]["worst_case_sd"] == 0.0
