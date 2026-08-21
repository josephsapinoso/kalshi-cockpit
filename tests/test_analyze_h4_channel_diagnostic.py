"""A17's diagnostic analyzer: every verdict branch and every exclusion made
to fire on synthetic payloads, before any real pull exists.

What this does not establish: anything about the real record. These payloads
are synthetic by design (the pull is operator data and never committed); the
claims tested are the registered rules' shapes -- half-open span containment,
the tau boundaries, the +/-24h neighbourhood, and that a zero denominator is
UNTESTED rather than BLIND.
"""

from __future__ import annotations

import pytest

from scripts.analyze_h4_channel_diagnostic import TruncatedPull, analyze

T0 = 1_787_100_000_000
MIN = 60_000
HOUR = 3_600_000


def _section(letter: str, columns: list[str], rows: list[tuple]) -> dict:
    return {
        "title": f"{letter}. synthetic",
        "columns": columns,
        "rows": rows,
        "truncated": False,
    }


def _payload(snapshots, settlements, polls=()) -> dict:
    """snapshots: (observed_ms, balance_tenths); settlements:
    (id, ticker, side, contracts, market_result, settled_ms);
    polls: (polled_ms, ok)."""
    return {
        "sections": [
            _section("B", ["observed_ms", "balance_tenths",
                           "portfolio_value_tenths"],
                     [(ms, bal, None) for ms, bal in snapshots]),
            _section("D", ["polled_ms", "ok", "row_count", "error"],
                     [(ms, ok, None, None) for ms, ok in polls]),
            _section("E", ["id", "ticker", "side", "contracts",
                           "entry_price_tenths", "fee_cost_tenths",
                           "market_result", "settled_ms"],
                     [(i, t, s, c, None, None, r, ms)
                      for i, t, s, c, r, ms in settlements]),
        ]
    }


def _winner(id=1, contracts=5.0, settled=T0 + 5 * MIN, ticker="KXW"):
    return (id, ticker, "yes", contracts, "yes", settled)


class TestVerdictBranches:
    def test_a_credit_landing_in_its_own_span_is_strict(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_000)],
            [_winner(contracts=5.0)],
        ))
        assert out["verdict"] == "CARRIES CREDITS (STRICT)"
        assert out["eligible_winner_count"] == 1
        w = out["winners"][0]
        assert w["p_i"] == 5_000 and w["hit_strict"] and w["hit_wide"]

    def test_a_credit_in_a_neighbouring_span_is_wide_with_lead_lag(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 10_000),
             (T0 + 20 * MIN, 15_000)],
            [_winner(contracts=5.0)],
        ))
        assert out["verdict"] == "CARRIES CREDITS (WIDE)"
        w = out["winners"][0]
        assert not w["hit_strict"] and w["hit_wide"]
        assert w["wide_hits"][0]["lead_lag_ms_hi"] == 15 * MIN

    def test_no_matching_delta_anywhere_is_blind(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 10_100)],
            [_winner(contracts=5.0)],
        ))
        assert out["verdict"] == "BLIND"
        assert out["eligible_winner_count"] == 1

    def test_zero_covered_winners_is_untested_never_blind(self):
        """A17.5: absence of winners is not evidence of blindness --
        mutation observed red: drop the empty-denominator branch and the
        verdict falls through to BLIND."""
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 10_000)],
            [(1, "KXL", "yes", 5.0, "no", T0 + 5 * MIN)],   # a loser
        ))
        assert out["verdict"] == "UNTESTED (no covered winner)"
        assert out["eligible_winner_count"] == 0


class TestTheRegisteredBoundaries:
    def test_strict_tolerance_is_inclusive_at_tau(self):
        """tau_j = 1 + n_win = 2; a residual of exactly 2 tenths is a hit
        and 3 is not. Mutation observed red: <= tau to < tau."""
        hit = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_002)], [_winner()],
        ))
        miss = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_003)], [_winner()],
        ))
        assert hit["winners"][0]["hit_strict"]
        assert not miss["winners"][0]["hit_strict"]

    def test_the_wide_neighbourhood_ends_at_24h(self):
        """A pair whose far endpoint sits past +/-24h of the settlement is
        not scanned. Mutation observed red: widen the constant."""
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 10_000),
             (T0 + 5 * MIN + 24 * HOUR + 1, 15_000)],
            [_winner(contracts=5.0)],
        ))
        assert out["verdict"] == "BLIND"
        assert out["winners"][0]["wide_deltas_scanned"] == 1

    def test_span_containment_is_half_open(self):
        """(s_j, s_j+1]: a settlement exactly at a span's lower endpoint
        belongs to the PREVIOUS pair; one at the upper endpoint is inside.
        Mutation observed red: either < flipped."""
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_000),
             (T0 + 20 * MIN, 15_000)],
            [_winner(settled=T0 + 10 * MIN)],   # == first span's upper end
        ))
        w = out["winners"][0]
        assert w["span_index"] == 0 and w["hit_strict"]

    def test_a_settlement_at_the_first_snapshot_instant_is_uncovered(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_000)],
            [_winner(settled=T0)],
        ))
        assert out["exclusion_counts"]["D3"] == 1
        assert out["verdict"] == "UNTESTED (no covered winner)"


class TestExclusionsAreCountedNotVotes:
    def test_pre_coverage_and_post_coverage_settlements_are_d3(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 10_000)],
            [_winner(id=1, settled=T0 - HOUR),
             _winner(id=2, settled=T0 + HOUR)],
        ))
        assert out["exclusion_counts"]["D3"] == 2

    def test_a_failed_poll_inside_the_span_is_d4_and_outside_is_not(self):
        inside = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_000)],
            [_winner()],
            polls=[(T0 + 5 * MIN, 0)],
        ))
        outside = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_000)],
            [_winner()],
            polls=[(T0 + 11 * MIN, 0)],
        ))
        assert inside["exclusion_counts"]["D4"] == 1
        assert inside["verdict"] == "UNTESTED (no covered winner)"
        assert outside["exclusion_counts"]["D4"] == 0
        assert outside["verdict"] == "CARRIES CREDITS (STRICT)"

    def test_a_failed_poll_at_the_span_endpoint_instant_is_still_d4(self):
        """The module docstring's explicit interpretation: D4 reads the
        CLOSED interval [s_j, s_j+1]. Mutation observed red: open either
        end of the interval."""
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_000)],
            [_winner()],
            polls=[(T0, 0)],
        ))
        assert out["exclusion_counts"]["D4"] == 1

    def test_a_null_result_is_d1_and_a_loser_is_d2(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 10_000)],
            [(1, "KXV", "yes", 5.0, None, T0 + 5 * MIN),
             (2, "KXL", "no", 5.0, "yes", T0 + 5 * MIN)],
        ))
        assert out["exclusion_counts"]["D1"] == 1
        assert out["exclusion_counts"]["D2"] == 1


class TestSpanArithmetic:
    def test_two_winners_in_one_span_sum_into_p_j_and_widen_tau(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 18_003)],
            [_winner(id=1, contracts=5.0),
             _winner(id=2, contracts=3.0, settled=T0 + 6 * MIN)],
        ))
        w = out["winners"][0]
        assert w["p_j"] == 8_000 and w["tau_j"] == 3
        # residual 3 == tau 3: still a hit, because tau grew with n_win.
        assert out["verdict"] == "CARRIES CREDITS (STRICT)"

    def test_losers_never_enter_p_j(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_000)],
            [_winner(contracts=5.0),
             (9, "KXL", "yes", 100.0, "no", T0 + 6 * MIN)],
        ))
        assert out["winners"][0]["p_j"] == 5_000

    def test_empty_spans_are_counted_as_coverage_only(self):
        out = analyze(_payload(
            [(T0, 10_000), (T0 + 10 * MIN, 15_000),
             (T0 + 20 * MIN, 15_000)],
            [_winner()],
        ))
        assert out["total_adjacent_pairs"] == 2
        assert out["coverage_only_pairs"] == 1


class TestARefusedPullIsNotALook:
    def test_a_truncated_section_refuses_outright(self):
        payload = _payload([(T0, 10_000), (T0 + 10 * MIN, 15_000)],
                           [_winner()])
        payload["sections"][2]["truncated"] = True
        with pytest.raises(TruncatedPull):
            analyze(payload)
