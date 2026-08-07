"""Price representation tests.

Two failure modes matter here and both are silent:

1. Losing sub-cent precision. Roughly a quarter of Kalshi markets tick in
   deci-cents, and half a cent is an eighth of a typical edge.
2. An unreadable value resolving to zero instead of None. A price that
   silently became 0 is a free contract in the risk model.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.core import prices


class TestParsing:
    """Kalshi sends dollar strings; we store integer tenths of a cent."""

    @pytest.mark.parametrize(
        "wire_value,expected_tenths",
        [
            ("0.2400", 240),
            ("0.2410", 241),  # deci-cent tick
            ("0.0010", 1),  # the smallest tradeable increment
            ("0.9620", 962),  # top of the observed live range
            ("1.0000", 1000),
            ("0.0000", 0),
        ],
    )
    def test_parses_kalshi_dollar_strings(self, wire_value, expected_tenths):
        assert prices.dollars_to_tenths(wire_value) == expected_tenths

    def test_round_trips_every_tenth_without_drift(self):
        """The claim float parsing gets right only by luck. Decimal guarantees it."""
        for tenths in range(0, prices.PRICE_MAX + 1):
            wire = f"{Decimal(tenths) / Decimal(1000):.4f}"
            assert prices.dollars_to_tenths(wire) == tenths

    def test_accepts_float_and_decimal_input(self):
        assert prices.dollars_to_tenths(0.24) == 240
        assert prices.dollars_to_tenths(Decimal("0.241")) == 241


class TestUnreadableNeverBecomesZero:
    """From tasks/lessons.md: clamp what you trust, refuse what you're validating.

    Zero is a legitimate price (a settled loser), so a parser that returns 0 on
    garbage is indistinguishable from one that read a real settled market. The
    only safe sentinel is None, and the caller has to handle it.
    """

    @pytest.mark.parametrize("garbage", [None, "", "n/a", "abc", "0.24.1", []])
    def test_unparseable_price_returns_none_not_zero(self, garbage):
        assert prices.dollars_to_tenths(garbage) is None

    @pytest.mark.parametrize("garbage", [None, "", "n/a", "abc", []])
    def test_unparseable_quantity_returns_none_not_zero(self, garbage):
        assert prices.parse_quantity(garbage) is None


class TestQuantities:
    """Kalshi returns fractional sizes -- 42 of 152 sampled levels were fractional."""

    def test_quantities_are_floats_not_ints(self):
        assert prices.parse_quantity("17.38") == pytest.approx(17.38)
        assert prices.parse_quantity("0.41") == pytest.approx(0.41)

    def test_negative_quantities_parse(self):
        """Deltas can be negative; only snapshot levels are non-negative."""
        assert prices.parse_quantity("-5.0") == pytest.approx(-5.0)


class TestComplement:
    """YES ask = complement(best NO bid). Load-bearing for every EV calculation."""

    def test_yes_and_no_sum_to_one_dollar(self):
        for tenths in (1, 240, 500, 962, 999):
            assert tenths + prices.complement(tenths) == prices.PRICE_MAX

    def test_complement_is_its_own_inverse(self):
        for tenths in (1, 240, 500, 999):
            assert prices.complement(prices.complement(tenths)) == tenths

    def test_derived_ask_is_worse_than_the_bid_in_a_spread_market(self):
        """Sanity check on the identity that stops us pricing off the mid.

        With a 45c YES bid and a 52c NO bid, the YES ask is 48c -- you buy
        higher than you could sell. Pricing off the 46.5c mid would understate
        the cost of every position by 1.5c.
        """
        yes_bid, no_bid = 450, 520
        yes_ask = prices.complement(no_bid)
        assert yes_ask == 480
        assert yes_ask > yes_bid


class TestValidity:
    """0 and 1000 are settled outcomes, not quotes."""

    @pytest.mark.parametrize("tenths", [1, 240, 500, 999])
    def test_tradeable_prices_are_valid(self, tenths):
        assert prices.is_valid_price(tenths)

    @pytest.mark.parametrize("tenths", [0, 1000, -1, 1001, None])
    def test_settled_and_out_of_range_prices_are_invalid(self, tenths):
        assert not prices.is_valid_price(tenths)


class TestFormatting:
    @pytest.mark.parametrize(
        "tenths,rendered",
        [(240, "24c"), (241, "24.1c"), (1, "0.1c"), (1000, "100c"), (None, "--")],
    )
    def test_renders_whole_cents_without_a_decimal_point(self, tenths, rendered):
        assert prices.format_price(tenths) == rendered


class TestProbabilityBridge:
    """A contract's fair price in dollars is its probability.

    This is the join between the devig/model layer and the price layer, so a
    drift here would show up as a systematic edge that isn't there.
    """

    def test_probability_round_trips(self):
        for tenths in (1, 240, 500, 750, 999):
            p = prices.tenths_to_probability(tenths)
            assert prices.probability_to_tenths(p) == tenths

    def test_clamps_out_of_range_probabilities(self):
        assert prices.probability_to_tenths(-0.5) == 0
        assert prices.probability_to_tenths(1.5) == prices.PRICE_MAX

    def test_a_fifty_percent_chance_prices_at_fifty_cents(self):
        assert prices.probability_to_tenths(0.5) == 500


class TestTheParserKeepsItsPromise:
    """`dollars_to_tenths` is documented as returning None on bad input.

    It raised on three: `Decimal("nan")` and `Decimal("Infinity")` *construct
    successfully*, so the `except` never fired and the failure surfaced later at
    `int()` or `quantize` — `ValueError` for one, `InvalidOperation` for the
    others. A parser documented as never raising, raising three different
    exceptions from inside a snapshot loop, is worse than one that made no
    promise: the caller wrote no handler because the docstring said none was
    needed.
    """

    @pytest.mark.parametrize("value", ["nan", "NaN", "Infinity", "-Infinity", "1e400"])
    def test_non_finite_input_returns_none(self, value):
        assert prices.dollars_to_tenths(value) is None

    def test_a_negative_price_returns_none(self):
        """A price is a probability in dollars and cannot be below zero.

        `"-0.50"` used to parse cleanly to -500 tenths and flow into the risk
        path as a real price. Refused rather than clamped: this is a value being
        validated, not one being trusted.
        """
        assert prices.dollars_to_tenths("-0.50") is None
        assert prices.dollars_to_tenths(-0.01) is None

    def test_zero_is_still_a_legitimate_price(self):
        """The discriminating case. A settled loser genuinely trades at 0, so
        rejecting it would reintroduce the failure this module is built around
        — 'unreadable' and 'worthless' must stay distinguishable."""
        assert prices.dollars_to_tenths("0") == 0
        assert prices.dollars_to_tenths("0.0000") == 0

    def test_ordinary_prices_are_unaffected(self):
        assert prices.dollars_to_tenths("0.4500") == 450
        assert prices.dollars_to_tenths("1.0000") == 1000


class TestOrderbookAndPriceValidityAgree:
    """`orderbook` accepted `0 <= p <= 1000` while `is_valid_price` is strict.

    The same number was therefore tradeable in one module and not in another. 0
    and 1000 are settled outcomes: a resting bid at either is a contract someone
    gives away or sells for a certain dollar, and neither belongs in a live book.
    """

    @pytest.mark.parametrize("tenths", [0, 1000])
    def test_settled_prices_are_not_valid_quotes(self, tenths):
        assert not prices.is_valid_price(tenths)

    @pytest.mark.parametrize("tenths", [1, 500, 999])
    def test_real_quotes_are_valid(self, tenths):
        assert prices.is_valid_price(tenths)
