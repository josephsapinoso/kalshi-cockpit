"""The multiplication nobody performed.

Four constants, each defensible alone, composed into a rule no row could
satisfy. The live instance joined 249 recommendations against closing lines and
scored **zero** — on every pass, for two days, while every counter read healthy.
`docs/adr/0011` has the full account.

    sweep fires no earlier than  kickoff - (max_odds_age_ms + due_window_ms)
    closing line observed at     kickoff - (horizon + WINDOW_MINUTES) .. -horizon
    scoring requires             created_ms <= observed_ms

A recommendation cannot exist before the odds sweep that priced it, so the
**earliest** entry is `kickoff - (max_odds_age_ms + due_window_ms)`. The
**earliest** observation is `kickoff - horizon - WINDOW_MINUTES`. If the second
is earlier than the first, nothing can ever be scored.

This file is the composition, written where CI performs it.

Why it is expressed as a relationship and not as `assert horizon == 0.0`:
pinning the value passes while someone widens the due window and rebuilds the
identical collision from the other side. The failure was never that the horizon
was 1.0 — it was that four numbers were chosen in four modules and no module
held more than one of them. Related: `tasks/lessons.md`,
"two limits on one quantity".
"""

from __future__ import annotations

from backend.analysis.clv import CONTROL_HORIZON_HOURS, DEFAULT_HORIZON_HOURS
from backend.config import StalenessConfig
from backend.odds.timing import DUE_WINDOW_MS
from backend.scoring import WINDOW_MINUTES

_MS_PER_MIN = 60_000


def _earliest_entry_ms_before_kickoff() -> int:
    """How long before kickoff the first recommendation can possibly exist.

    A row needs stored odds, odds come from a sweep, and `plan_sweeps` fires no
    earlier than one freshness window plus the due window before kickoff.
    """
    return StalenessConfig().max_odds_age_s * 1000 + DUE_WINDOW_MS


def _earliest_observation_ms_before_kickoff(horizon_hours: float) -> int:
    """How long before kickoff the closing line can possibly be observed.

    `fetch_closing_line` asks for a window *ending* at `commence - horizon` and
    reaching `WINDOW_MINUTES` back, then takes the last candle in it. So the
    observation can sit a full window earlier than the horizon nominally says --
    the detail that makes a 30-minute horizon behave like a 45-minute one.
    """
    return int(horizon_hours * 3_600_000) + WINDOW_MINUTES * _MS_PER_MIN


class TestTheHorizonAndTheSweepCanBothHold:
    def test_the_primary_horizon_leaves_room_for_a_recommendation_to_exist(self):
        entry = _earliest_entry_ms_before_kickoff()
        observation = _earliest_observation_ms_before_kickoff(DEFAULT_HORIZON_HOURS)

        assert observation < entry, (
            f"the closing line can be observed {observation / _MS_PER_MIN:.0f} "
            f"min before kickoff, and the earliest a recommendation can exist "
            f"is {entry / _MS_PER_MIN:.0f} min before kickoff. Every row would "
            f"be skipped as entry-after-close and the gate's counter could "
            f"never leave zero. Either shorten the primary horizon, or move "
            f"the sweep earlier and accept the lost actionable window."
        )

    def test_the_old_settings_are_pinned_as_the_failure_they_were(self):
        """The regression, stated as an input rather than as history.

        A 1.0h horizon against today's sweep timing is unscoreable. Asserting it
        here means the test is known to be capable of failing — a composition
        check that has only ever seen a passing input has not been shown to
        detect anything.
        """
        entry = _earliest_entry_ms_before_kickoff()
        assert _earliest_observation_ms_before_kickoff(1.0) > entry

    def test_the_control_horizon_is_further_out_than_the_primary(self):
        """Otherwise `horizons_agree` compares a horizon with itself.

        It returns a number either way, and the number would be zero drift —
        which reads as "the finding survived a second horizon", the strongest
        result the check can produce, from having made no comparison at all.
        """
        assert CONTROL_HORIZON_HOURS > DEFAULT_HORIZON_HOURS

    def test_the_control_horizon_is_allowed_to_be_unscoreable(self):
        """Stated so nobody "fixes" it later.

        The control exists for `horizons_agree`, which compares mean CLV across
        two sets of stored `closing_lines`. It does not need rows scored into
        `clv_tenths`, so it is under no obligation to satisfy the composition
        above — and at 1.0h it does not.
        """
        assert _earliest_observation_ms_before_kickoff(CONTROL_HORIZON_HOURS) > (
            _earliest_entry_ms_before_kickoff()
        )


class TestTheHorizonIsNeverTestedForTruth:
    def test_zero_is_a_real_horizon_and_must_not_be_read_as_absent(self):
        """`0.0` is falsy, and it is the primary horizon now.

        This repo already has a lesson about a zero that meant "no measurement"
        passing every threshold. Here the polarity is reversed: the zero is the
        *legitimate* value, and any `if horizon:` guard would silently treat the
        closing line as unconfigured and fall back to something else.
        """
        assert DEFAULT_HORIZON_HOURS == 0.0
        assert not DEFAULT_HORIZON_HOURS      # falsy -- which is the hazard

    def test_no_module_branches_on_the_horizon_being_truthy(self):
        """Grepped rather than reasoned about, because the hazard is a one-liner
        anyone could add and nothing else would catch."""
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        hazard = re.compile(r"\bif +(not +)?horizon(_hours)? *[:)]")
        offenders = []
        for path in (root / "backend").rglob("*.py"):
            for lineno, line in enumerate(
                path.read_text("utf-8").splitlines(), start=1
            ):
                if hazard.search(line):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
        assert not offenders, (
            "a falsy check on the horizon, which is 0.0: " + "; ".join(offenders)
        )
