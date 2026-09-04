"""The presence analyzer's registered structure, on synthetic captures.

What this establishes: that the §6.2 refusal is structural (below the floors
the report carries no `K`, no distance, no p-value), that sittings cluster as
§3.1 says, that the two arms and the leave-one-day-out downgrade behave as
§6.3 reads, that Amendment 1's exclusion (E0–E5) runs on the order side and
before the floor, and that the analyzer reads only the permitted fill columns.

What it does not establish: anything about the live record. Every fixture
here is invented; the registration forbids reading the live fills before the
window closed and this file never does.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "analyse_bet_presence.py"

spec = importlib.util.spec_from_file_location("analyse_bet_presence", SCRIPT)
abp = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["analyse_bet_presence"] = abp
spec.loader.exec_module(abp)  # type: ignore[union-attr]

H = 3_600_000
W_START = 1_787_700_000_000  # arbitrary, inside the registered window shape
W_END = W_START + 12 * abp.DAY_MS


def hand(ms, taker=1, source="venue_hand", ticker="T-SINGLE"):
    return abp.Fill(filled_ms=ms, is_taker=taker, source=source, ticker=ticker)


def order(placed_ms, status="cancelled", reduced_by=1.0, count=1.0, ticker="T-COMBO",
          cancelled_ms=1, dry_run=0):
    return abp.DeskOrder(
        placed_ms=placed_ms, dry_run=dry_run, status=status,
        cancelled_ms=cancelled_ms if status == "cancelled" else None,
        cancel_reduced_by=reduced_by, count=count, ticker=ticker,
    )


def inputs(manual=0, orders=(), manual_tickers=None, truncated=False, whole=True):
    return abp.ExclusionInputs(
        manual_real_rows=manual, manual_tickers=manual_tickers,
        combo_orders=list(orders), combo_tail_truncated=truncated,
        combo_tail_whole_table=whole,
    )


def eight_days():
    return [W_START + i * abp.DAY_MS + 4 * H for i in range(8)]


class TestSittingsAreTheUnit:
    def test_fills_within_the_gap_are_one_sitting(self):
        runs = abp.sittings([0, 10 * 60_000, 50 * 60_000, 3 * H])
        assert [len(r) for r in runs] == [3, 1]

    def test_a_gap_of_exactly_the_threshold_does_not_split(self):
        assert len(abp.sittings([0, abp.SITTING_GAP_MS])) == 1

    def test_budget_day_boundary_is_ten_z(self):
        nine59 = 1_788_000_000_000 // abp.DAY_MS * abp.DAY_MS + 9 * H + 59 * 60_000
        ten = nine59 + 60_000
        assert abp.budget_day(nine59) + 1 == abp.budget_day(ten)


class TestTheRefusalIsStructural:
    def test_below_s_min_no_k_or_pvalue_is_printed(self):
        fills = [hand(W_START + i * abp.DAY_MS + H) for i in range(6)]
        visits = [abp.Visit(W_START + i * abp.DAY_MS, W_START + i * abp.DAY_MS + 2 * H) for i in range(6)]
        rep = abp.analyse(fills, visits, W_START, inputs(), w_end=W_END)
        text = "\n".join(rep.lines)
        assert rep.verdict == "UNRESOLVED — TOO FEW SITTINGS"
        assert "SAMPLE NOT REACHED: S = 6 of 8" in text
        assert "K =" not in text and "p_gap" not in text and "distance" not in text

    def test_enough_sittings_on_too_few_days_refuses_on_days(self):
        fills = [hand(W_START + (i // 2) * abp.DAY_MS + (i % 2) * 3 * H + H) for i in range(8)]
        visits = [abp.Visit(W_START, W_START + H)]
        rep = abp.analyse(fills, visits, W_START, inputs(), w_end=W_END)
        assert rep.verdict == "UNRESOLVED — TOO FEW DAYS"
        assert "p_gap" not in "\n".join(rep.lines)


class TestTheExclusionRunsOnTheOrderSideFirst:
    """Amendment 1, E0–E5."""

    def test_a_capture_before_w_end_is_refused_under_e0(self):
        fills = [hand(ms) for ms in eight_days()]
        visits = [abp.Visit(W_START, W_START + H)]
        rep = abp.analyse(fills, visits, W_START, inputs(), w_end=W_END,
                          captured_ms=[W_END - 1, W_END, W_END, W_END])
        assert rep.verdict == abp.UNRESOLVED_EXCLUSION
        assert "E0" in "\n".join(rep.lines)

    def test_a_partial_combo_tail_is_refused_under_e0(self):
        rep = abp.analyse([], [abp.Visit(W_START, W_START + H)], W_START,
                          inputs(whole=False), w_end=W_END)
        assert rep.verdict == abp.UNRESOLVED_EXCLUSION

    def test_manual_rows_without_section_e_refuse_under_e1(self):
        rep = abp.analyse([], [abp.Visit(W_START, W_START + H)], W_START,
                          inputs(manual=1, manual_tickers=None), w_end=W_END)
        assert rep.verdict == abp.UNRESOLVED_EXCLUSION

    def test_a_fully_withdrawn_order_is_cleared_by_the_venue_and_excludes_nothing(self):
        ex = abp.execute_exclusion(inputs(orders=[order(W_START + H)]), W_END)
        assert (ex.n_desk_orders, ex.n_cleared_by_venue, ex.n_residual, ex.n_tickers) == (1, 1, 0, 0)

    def test_a_partial_cancel_is_residual_and_attributed_by_ticker(self):
        ex = abp.execute_exclusion(inputs(orders=[order(W_START + H, reduced_by=0.5, count=1.0)]), W_END)
        assert (ex.n_cleared_by_venue, ex.n_residual, ex.n_tickers) == (0, 1, 1)

    def test_a_resting_order_is_residual(self):
        ex = abp.execute_exclusion(inputs(orders=[order(W_START + H, status="resting", reduced_by=None)]), W_END)
        assert (ex.n_cleared_by_venue, ex.n_residual) == (0, 1)

    def test_an_order_placed_before_w_start_still_counts_if_before_w_end(self):
        ex = abp.execute_exclusion(inputs(orders=[order(W_START - 3 * abp.DAY_MS, status="resting", reduced_by=None)]), W_END)
        assert ex.n_desk_orders == 1

    def test_dry_runs_and_orders_after_w_end_are_not_desk_orders(self):
        ex = abp.execute_exclusion(
            inputs(orders=[order(W_START + H, dry_run=1), order(W_END + 1, status="resting", reduced_by=None)]),
            W_END,
        )
        assert ex.n_desk_orders == 0

    def test_excluded_fills_are_removed_before_sittings_form_and_the_floor_is_evaluated(self):
        """E5. Eight hand fills on eight days; one of them is on a residual
        order's ticker. After exclusion S = 7 and the floor refuses --
        the exclusion came first. Mutation observed red: classify without the
        ticker set (S stays 8 and the arms run)."""
        bets = eight_days()
        fills = [hand(ms) for ms in bets[:-1]] + [hand(bets[-1], ticker="T-COMBO")]
        visits = [abp.Visit(ms + 6 * H, ms + 6 * H + 60_000) for ms in bets]
        resting = order(W_START + H, status="resting", reduced_by=None, ticker="T-COMBO")
        rep = abp.analyse(fills, visits, W_START, inputs(orders=[resting]), w_end=W_END)
        text = "\n".join(rep.lines)
        assert "EXCLUDED-BY-TICKER fills     1" in text
        assert rep.verdict == "UNRESOLVED — TOO FEW SITTINGS"
        assert "T-COMBO" not in text  # §B.3: no ticker string is ever printed


class TestTheArms:
    def test_every_bet_far_from_every_visit_supports_the_gap(self):
        # Twelve days, not eight -- see the test below for why eight cannot.
        bets = [W_START + i * abp.DAY_MS + 4 * H for i in range(12)]
        fills = [hand(ms) for ms in bets]
        visits = [abp.Visit(ms + 6 * H, ms + 6 * H + 60_000) for ms in bets]
        rep = abp.analyse(fills, visits, W_START, inputs(), w_end=W_END)
        assert rep.verdict == "PRESENCE GAP SUPPORTED"
        assert "WEAK by construction" in "\n".join(rep.lines)

    def test_at_exactly_s_min_one_per_day_the_gap_arm_is_downgraded_by_leave_one_day_out(self):
        """A registered consequence, pinned so it is read as one and not as a bug.

        §0.2 makes `S = 8` declarable on the gap arm (`k* = 0`, alpha 0.0039).
        §3.3 then requires the verdict to survive dropping the largest budget
        day. With one sitting per day that leaves `S = 7`, where `0 of 7`
        gives `p = 0.0078 > 0.005` and no critical value exists -- so the
        verdict flips and is downgraded to UNRESOLVED -- CONCENTRATION.
        The analyzer implements both sections as written; reconciling them is
        an amendment to the registration, not a change here.
        """
        fills = [hand(ms) for ms in eight_days()]
        visits = [abp.Visit(ms + 6 * H, ms + 6 * H + 60_000) for ms in eight_days()]
        rep = abp.analyse(fills, visits, W_START, inputs(), w_end=W_END)
        assert rep.verdict == "UNRESOLVED — CONCENTRATION"

    def test_a_tie_for_largest_day_drops_every_tied_day_and_downgrades_if_any_flips(self):
        """The audit's B1 on the 2026-09-04 look: two days tied at 3 sittings,
        `max(per_day, key=per_day.get)` returned the first by insertion order,
        and dropping the OTHER tied day did not clear. The registration says
        "the largest-contributing budget day"; when that is a set, every
        member is dropped in turn. Mutation observed red: restore the single
        `max()` tie-break (the fixture is built so the first tied day in
        insertion order clears and the second does not).

        Built on the gap arm, where the tails are exact. Twelve sittings on
        eight days; exactly one sitting is desk-present (day 0, 04:00). A
        visit sits at 04:00 on every day, so the day-shift null lands that
        sitting in a visit on every draw and the presence arm never clears.
        Full: K = 1 of 12, p_gap = 0.0032 -> SUPPORTED. Day 0 and day 8 tie
        at three sittings. Drop day 0 (which holds the present one): 0 of 9,
        p_gap = 0.0020, still SUPPORTED. Drop day 8: 1 of 9, p_gap = 0.0195,
        not SUPPORTED -- the verdict flips, and the downgrade must fire. The
        insertion-order tie-break drops day 0 only and would not see it.
        """
        day0 = [W_START + 4 * H, W_START + 6 * H, W_START + 8 * H]
        day8 = [W_START + 8 * abp.DAY_MS + h * H for h in (5, 7, 9)]
        singles = [W_START + i * abp.DAY_MS + 12 * H + i * H for i in range(1, 7)]
        bets = day0 + day8 + singles
        fills = [hand(ms) for ms in bets]
        visits = [
            abp.Visit(W_START + d * abp.DAY_MS + 4 * H - 60_000, W_START + d * abp.DAY_MS + 4 * H + 60_000)
            for d in range(12)
        ]
        rep = abp.analyse(fills, visits, W_START, inputs(), w_end=W_END)
        text = "\n".join(rep.lines)
        assert "K = 1 of 12" in text
        assert "2 days tie for largest" in text
        assert text.count("leave-one-day-out (drop day") == 2
        assert rep.verdict == "UNRESOLVED — CONCENTRATION"

    def test_every_bet_inside_a_visit_at_the_same_clock_time_is_not_refuted(self):
        """The hour-of-day confound §5.2 exists for: visits at the same clock
        time every day make a day-shifted bet land in one by chance."""
        bets = eight_days()
        fills = [hand(ms) for ms in bets]
        visits = [abp.Visit(ms - 60_000, ms + 60_000) for ms in bets]
        rep = abp.analyse(fills, visits, W_START, inputs(), w_end=W_END)
        assert rep.verdict.startswith("UNRESOLVED")

    def test_presence_above_a_day_shifted_null_refutes_the_gap(self):
        bets = [W_START + i * abp.DAY_MS + (2 + i) * H for i in range(8)]
        fills = [hand(ms) for ms in bets]
        visits = [abp.Visit(ms - 60_000, ms + 60_000) for ms in bets]
        rep = abp.analyse(fills, visits, W_START, inputs(), w_end=W_END)
        assert rep.verdict == "PRESENCE GAP REFUTED"
        assert "STRONG by construction" in "\n".join(rep.lines)


class TestOnlyPermittedColumnsAreRead:
    def test_fill_from_row_reads_only_registered_columns(self):
        section = {
            "title": "C. fills since study start",
            "columns": ["id", "ticker", "filled_ms", "count", "price_tenths", "is_taker", "fee_actual", "source"],
        }
        row = [1, "KX", 5, 99, 999, 1, 7, "venue_hand"]
        f = abp._fill_from_row(section, row)
        assert (f.filled_ms, f.is_taker, f.source, f.ticker) == (5, 1, "venue_hand", "KX")
        assert not hasattr(f, "price_tenths") and not hasattr(f, "count")

    def test_a_truncated_section_is_refused(self):
        with pytest.raises(abp.CaptureError):
            abp.require_not_truncated({"title": "C. fills", "truncated": True, "row_cap": 5000})
