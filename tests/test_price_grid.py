"""The set of limit prices a market accepts, and how a price moves onto it.

What is pinned by captured bytes and what is not
-----------------------------------------------
The **shape** of `price_ranges` — an array of `{start, end, step}` fixed-point
dollar strings — is pinned by real captures: `price_grids.json` (every distinct
grid across 1,426 live game markets), plus the same field in both
`events_sports_nested.json` and `market_single.json`, which is what catches a
rename in one endpoint and not the other.

The **sub-cent band values** are not captured, and this file says so rather than
implying otherwise. Every game market on the day of capture was `linear_cent`,
the one grid on which snapping is a no-op, so testing only against real bytes
would exercise nothing. The sub-cent grids below are transcribed from Kalshi's
published price-level-structure table (`docs.kalshi.com/getting_started/
fixed_point_migration`) and are labelled `_SPEC_` for that reason. That is a
weaker guarantee than a capture and it is the strongest one available today; if
a sub-cent game market appears, `scripts/capture_price_grids.py` will record it
and these can be replaced with bytes.

This distinction is the point of `tasks/lessons.md`, "the WebSocket path was
dead and 611 tests said otherwise": hand-written payloads test the parser
against the author's belief about the wire, not against the wire.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.kalshi.grid import (
    DOWN,
    UP,
    GridUnavailable,
    PriceGrid,
    parse_price_grid,
    read_price_grid,
)

FIXTURES = Path(__file__).parent / "fixtures"

# Transcribed from Kalshi's published table. NOT captured -- see the docstring.
_SPEC_HALF_CENT = [{"start": "0.0000", "end": "1.0000", "step": "0.0050"}]
_SPEC_TAPERED_DECI = [
    {"start": "0.0000", "end": "0.1000", "step": "0.0010"},
    {"start": "0.1000", "end": "0.9000", "step": "0.0100"},
    {"start": "0.9000", "end": "1.0000", "step": "0.0010"},
]
_SPEC_CENTI = [{"start": "0.0000", "end": "1.0000", "step": "0.0001"}]

WHOLE_CENT = [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}]


def half_cent() -> PriceGrid:
    return parse_price_grid(_SPEC_HALF_CENT, structure="center_half_edge_half_cent")


def whole_cent() -> PriceGrid:
    return parse_price_grid(WHOLE_CENT, structure="linear_cent")


class TestTheCaptureItself:
    """Assert something about the capture, so a re-scoped one fails loudly.

    Per `tasks/lessons.md`: a fixture-backed test whose fixture silently shrank
    is a test that quietly stops testing anything.
    """

    def setup_method(self):
        self.payload = json.loads(
            (FIXTURES / "price_grids.json").read_text(encoding="utf-8")
        )

    def test_the_capture_covers_a_real_slate(self):
        assert self.payload["game_markets_seen"] >= 500
        assert self.payload["grids"]

    def test_every_captured_grid_parses(self):
        for grid in self.payload["grids"]:
            parsed = parse_price_grid(
                grid["price_ranges"], structure=grid["price_level_structure"]
            )
            assert parsed.bands

    def test_whole_cents_are_on_every_captured_grid(self):
        """Kalshi: 'whole-cent prices are valid in every structure.'

        This is why the old whole-cent flooring was never *rejected* -- and
        therefore why it was invisible. The property is worth asserting because
        it is the reason the bug could not announce itself.
        """
        for grid in self.payload["grids"]:
            parsed = parse_price_grid(grid["price_ranges"])
            for cents in (1, 25, 50, 99):
                assert parsed.is_on_grid(cents * 10)

    def test_todays_slate_is_whole_cent_and_that_is_recorded_not_assumed(self):
        """The measured fact, asserted so a future capture that changes it is
        visible rather than silently widening the risk.

        This does **not** license "sub-cent game markets do not exist" -- that
        is the `KXMVE` mistake in `tasks/lessons.md`, where a true measurement
        about one thing was promoted into a claim about another.
        """
        assert set(self.payload["structure_counts"]) == {"linear_cent"}


class TestBothEndpointsCarryTheGrid:
    """A rename in one endpoint and not the other must fail a test.

    `/events?with_nested_markets=true` feeds the recorder and
    `/markets/{ticker}` feeds the order-time refresh. The order path snaps
    against whichever one answered, so the two agreeing is load-bearing.
    """

    def test_the_nested_and_single_payloads_agree(self):
        payload = json.loads(
            (FIXTURES / "market_single.json").read_text(encoding="utf-8")
        )
        nested = payload["nested"]
        single = payload["single"]["market"]
        assert read_price_grid(nested) == read_price_grid(single)
        assert read_price_grid(nested) is not None

    def test_the_events_capture_carries_it_too(self):
        events = json.loads(
            (FIXTURES / "events_sports_nested.json").read_text(encoding="utf-8")
        )
        markets = [m for e in events for m in (e.get("markets") or [])]
        assert markets
        assert all(read_price_grid(m) is not None for m in markets)


class TestParsingRefusesRatherThanDefaulting:
    """There is no default grid. Every failure refuses.

    A default of whole cents would restore the exact bug this module removes,
    and would do it silently on the day Kalshi renames the field.
    """

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            [],
            "linear_cent",
            [{"start": "0.0000", "end": "1.0000"}],           # no step
            [{"start": "0.0000", "step": "0.0100"}],           # no end
            [{"start": "x", "end": "1.0000", "step": "0.0100"}],
            [{"start": "0.0000", "end": "1.0000", "step": "0"}],
            [{"start": "1.0000", "end": "0.0000", "step": "0.0100"}],
            ["not-an-object"],
        ],
    )
    def test_an_unusable_grid_raises(self, raw):
        with pytest.raises(GridUnavailable):
            parse_price_grid(raw)

    def test_the_absent_field_says_what_it_would_have_cost(self):
        with pytest.raises(GridUnavailable) as exc:
            parse_price_grid(None)
        assert "never fills" in str(exc.value)

    def test_read_price_grid_returns_none_at_the_ingest_boundary(self):
        """Parsers return Optional; callers refuse. One malformed band must not
        abort a walk of 1,400 markets, and the order path refuses on the None."""
        assert read_price_grid({"ticker": "T"}) is None
        assert read_price_grid({"ticker": "T", "price_ranges": []}) is None


class TestSnappingDirection:
    """A bid snaps down and an ask snaps up -- always away from paying more."""

    def test_a_bid_never_moves_up(self):
        assert half_cent().snap_tenths(503, DOWN) == 500

    def test_an_ask_never_moves_down(self):
        assert half_cent().snap_tenths(503, UP) == 505

    def test_a_price_already_on_the_grid_is_untouched_in_both_directions(self):
        """The definitional anchor: 50.5c is a legal half-cent price, so
        neither direction may move it.

        Chosen because it is the single input where the old whole-cent flooring
        and the new snapper give **different** answers -- 500 against 505. An
        anchor that both implementations satisfy is decorative
        (`tasks/lessons.md`, "four audits, one failure shape").
        """
        grid = half_cent()
        assert grid.snap_tenths(505, DOWN) == 505
        assert grid.snap_tenths(505, UP) == 505

    def test_on_a_whole_cent_grid_the_snapper_reproduces_the_old_behaviour(self):
        """The migration must be a no-op where it should be.

        1,426 of 1,426 live game markets are `linear_cent`, so this is what
        actually runs today, and a change in it would be a regression rather
        than a fix.
        """
        grid = whole_cent()
        assert grid.snap_tenths(509, DOWN) == 500
        assert grid.snap_tenths(501, UP) == 510
        assert grid.snap_tenths(500, DOWN) == 500
        assert grid.snap_tenths(500, UP) == 500

    def test_an_unknown_direction_is_refused(self):
        with pytest.raises(GridUnavailable):
            whole_cent().snap_tenths(500, "sideways")


class TestTaperedGrids:
    """Bands with different steps, which is where a single-band snapper breaks."""

    def setup_method(self):
        self.grid = parse_price_grid(
            _SPEC_TAPERED_DECI, structure="tapered_deci_cent"
        )

    def test_the_fine_band_below_ten_cents_is_used(self):
        assert self.grid.snap_tenths(53, DOWN) == 53
        assert self.grid.snap_tenths(53, UP) == 53

    def test_the_coarse_middle_band_rounds_to_whole_cents(self):
        assert self.grid.snap_tenths(505, DOWN) == 500
        assert self.grid.snap_tenths(505, UP) == 510

    def test_the_fine_band_above_ninety_cents_is_used(self):
        assert self.grid.snap_tenths(953, DOWN) == 953
        assert self.grid.snap_tenths(953, UP) == 953

    def test_a_price_between_bands_crosses_to_the_next_band(self):
        """101 tenths sits inside the coarse band, whose points are whole cents.

        Snapping up must reach 110, not stay at 101 by borrowing the fine
        band's step from the band below -- the failure a per-band loop that
        forgets to check `contains` produces.
        """
        assert self.grid.snap_tenths(101, UP) == 110
        assert self.grid.snap_tenths(101, DOWN) == 100

    def test_the_band_boundary_itself_is_on_the_grid(self):
        assert self.grid.is_on_grid(100)
        assert self.grid.snap_tenths(100, UP) == 100
        assert self.grid.snap_tenths(100, DOWN) == 100

    def test_a_band_whose_end_is_not_a_whole_step_stops_at_its_end(self):
        """The case that makes `PriceBand.ceil`'s bound load-bearing.

        Every band Kalshi publishes today is an exact number of steps wide, so
        on real data this branch never fires — which is precisely why it needs a
        test that does fire it. A band running to 10.5c in whole cents has no
        grid point at 11c, and snapping up from 10.1c must fall through to the
        next band rather than inventing 11c inside this one.

        Without the bound this returns 110 from the first band and the assertion
        below still passes by coincidence; the second one does not.
        """
        ragged = parse_price_grid([
            {"start": "0.0000", "end": "0.1050", "step": "0.0100"},
            {"start": "0.2000", "end": "0.9000", "step": "0.0500"},
        ])
        assert ragged.snap_tenths(101, UP) == 200
        assert not ragged.is_on_grid(110)


class TestOffGridPricesRefuseRatherThanClamp:
    def test_a_price_above_every_band_has_no_ask_point(self):
        grid = parse_price_grid(
            [{"start": "0.1000", "end": "0.9000", "step": "0.0100"}]
        )
        with pytest.raises(GridUnavailable) as exc:
            grid.snap_tenths(950, UP)
        assert "clamping" in str(exc.value)

    def test_a_price_below_every_band_has_no_bid_point(self):
        grid = parse_price_grid(
            [{"start": "0.1000", "end": "0.9000", "step": "0.0100"}]
        )
        with pytest.raises(GridUnavailable):
            grid.snap_tenths(50, DOWN)


class TestAGridFinerThanOurUnitIsRefused:
    """`center_centi_edge_centi_cent` ticks at $0.0001 -- a tenth of this
    project's smallest representable price.

    Combo (multivariate) markets use it. Nothing here trades them yet, and if
    something does, a price we cannot name must not be silently replaced by a
    different one.
    """

    def test_a_tenth_valued_price_still_snaps_to_itself(self):
        """Every tenth is a multiple of $0.0001, so the fine grid accepts it."""
        grid = parse_price_grid(_SPEC_CENTI)
        assert grid.snap_tenths(505, DOWN) == 505
        assert grid.snap_tenths(505, UP) == 505

    def test_a_grid_point_off_our_unit_refuses_instead_of_rounding(self):
        # A band starting half a tenth off the whole-tenth lattice.
        grid = parse_price_grid(
            [{"start": "0.5005", "end": "0.6000", "step": "0.0100"}]
        )
        with pytest.raises(GridUnavailable) as exc:
            grid.snap_tenths(510, UP)
        assert "finer than the tenth-of-a-cent" in str(exc.value)
