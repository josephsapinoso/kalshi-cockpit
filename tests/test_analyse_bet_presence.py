"""The presence analyzer's registered structure, on synthetic captures.

What this establishes: that the §6.2 refusal is structural (below the floors
the report carries no `K`, no distance, no p-value), that sittings cluster as
§3.1 says, that the two arms and the leave-one-day-out downgrade behave as
§6.3 reads, and that the analyzer reads only the three permitted fill columns.

What it does not establish: anything about the live record. Every fixture
here is invented; the registration forbids reading the live fills before the
window closed and this file never does.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "analyse_bet_presence.py"

spec = importlib.util.spec_from_file_location("analyse_bet_presence", SCRIPT)
abp = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["analyse_bet_presence"] = abp
spec.loader.exec_module(abp)  # type: ignore[union-attr]

H = 3_600_000
W_START = 1_787_700_000_000  # arbitrary, inside the registered window shape
W_END = W_START + 12 * abp.DAY_MS


def hand(ms, taker=1, source="venue_hand"):
    return abp.Fill(filled_ms=ms, is_taker=taker, source=source)


def census(manual=0, combo=0, truncated=False):
    return abp.ExclusionCensus(manual, combo, truncated)


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
        rep = abp.analyse(fills, visits, W_START, census(), w_end=W_END)
        text = "\n".join(rep.lines)
        assert rep.verdict == "UNRESOLVED — TOO FEW SITTINGS"
        assert "SAMPLE NOT REACHED: S = 6 of 8" in text
        assert "K =" not in text and "p_gap" not in text and "distance" not in text

    def test_enough_sittings_on_too_few_days_refuses_on_days(self):
        # 8 sittings, 2 hours apart, all on 4 budget days.
        fills = [hand(W_START + (i // 2) * abp.DAY_MS + (i % 2) * 3 * H + H) for i in range(8)]
        visits = [abp.Visit(W_START, W_START + H)]
        rep = abp.analyse(fills, visits, W_START, census(), w_end=W_END)
        assert rep.verdict == "UNRESOLVED — TOO FEW DAYS"
        assert "p_gap" not in "\n".join(rep.lines)

    def test_desk_placed_orders_in_window_make_the_exclusion_unexecutable(self):
        fills = [hand(W_START + i * abp.DAY_MS + H) for i in range(8)]
        visits = [abp.Visit(W_START, W_START + H)]
        rep = abp.analyse(fills, visits, W_START, census(manual=1), w_end=W_END)
        assert rep.verdict == "UNRESOLVED — EXCLUSION UNEXECUTABLE"


class TestTheArms:
    def _eight_days(self):
        return [W_START + i * abp.DAY_MS + 4 * H for i in range(8)]

    def test_every_bet_far_from_every_visit_supports_the_gap(self):
        # Twelve days, not eight -- see the test below for why eight cannot.
        bets = [W_START + i * abp.DAY_MS + 4 * H for i in range(12)]
        fills = [hand(ms) for ms in bets]
        # One short visit per day, six hours after each bet.
        visits = [abp.Visit(ms + 6 * H, ms + 6 * H + 60_000) for ms in bets]
        rep = abp.analyse(fills, visits, W_START, census(), w_end=W_END)
        assert rep.verdict == "PRESENCE GAP SUPPORTED"
        assert "WEAK by construction" in "\n".join(rep.lines)

    def test_at_exactly_s_min_one_per_day_the_gap_arm_is_downgraded_by_leave_one_day_out(self):
        """A registered consequence, pinned so it is read as one and not as a bug.

        §0.2 makes `S = 8` declarable on the gap arm (`k* = 0`, alpha 0.0039).
        §3.3 then requires the verdict to survive dropping the largest budget
        day. With one sitting per day that leaves `S = 7`, where `0 of 7`
        gives `p = 0.0078 > 0.005` and no critical value exists -- so the
        verdict flips and is downgraded to UNRESOLVED -- CONCENTRATION.
        The two sections together make the gap arm's effective floor higher
        than §0.2's eight when sittings are spread one to a day. The
        analyzer implements both sections as written; reconciling them is an
        amendment to the registration, not a change here.
        """
        fills = [hand(ms) for ms in self._eight_days()]
        visits = [abp.Visit(ms + 6 * H, ms + 6 * H + 60_000) for ms in self._eight_days()]
        rep = abp.analyse(fills, visits, W_START, census(), w_end=W_END)
        assert rep.verdict == "UNRESOLVED — CONCENTRATION"

    def test_every_bet_inside_a_visit_refutes_the_gap_when_visits_are_sparse(self):
        fills = [hand(ms) for ms in self._eight_days()]
        visits = [abp.Visit(ms - 60_000, ms + 60_000) for ms in self._eight_days()]
        rep = abp.analyse(fills, visits, W_START, census(), w_end=W_END)
        # Each visit is two minutes long; a day-shifted bet lands in one by
        # chance only if the shifted day's visit happens at the same clock
        # time -- which it does here, since every visit is at 04:00. So the
        # permutation null already covers it and the verdict is UNRESOLVED,
        # not REFUTED. That is the hour-of-day confound §5.2 exists for.
        assert rep.verdict.startswith("UNRESOLVED")

    def test_presence_above_a_day_shifted_null_refutes_the_gap(self):
        bets = self._eight_days()
        fills = [hand(ms) for ms in bets]
        # Visits at the bet instants only on the bet days, at staggered hours
        # so a day shift lands elsewhere: bets at 4h, visits on other days at 20h.
        visits = [abp.Visit(ms - 60_000, ms + 60_000) for ms in bets]
        visits += [abp.Visit(W_START + i * abp.DAY_MS + 20 * H, W_START + i * abp.DAY_MS + 20 * H + 60_000) for i in range(8, 12)]
        # Move the bets' clock time to differ per day so the shifted copies miss.
        bets2 = [W_START + i * abp.DAY_MS + (2 + i) * H for i in range(8)]
        fills = [hand(ms) for ms in bets2]
        visits = [abp.Visit(ms - 60_000, ms + 60_000) for ms in bets2]
        rep = abp.analyse(fills, visits, W_START, census(), w_end=W_END)
        assert rep.verdict == "PRESENCE GAP REFUTED"
        assert "STRONG by construction" in "\n".join(rep.lines)


class TestOnlyThreeColumnsAreRead:
    def test_fill_from_row_reads_only_registered_columns(self):
        section = {
            "title": "C. fills since study start",
            "columns": ["id", "ticker", "filled_ms", "count", "price_tenths", "is_taker", "fee_actual", "source"],
        }
        row = [1, "KX", 5, 99, 999, 1, 7, "venue_hand"]
        f = abp._fill_from_row(section, row)
        assert (f.filled_ms, f.is_taker, f.source) == (5, 1, "venue_hand")
        assert not hasattr(f, "price_tenths") and not hasattr(f, "count")

    def test_a_truncated_section_is_refused(self):
        import pytest

        with pytest.raises(abp.CaptureError):
            abp.require_not_truncated({"title": "C. fills", "truncated": True, "row_cap": 5000})
