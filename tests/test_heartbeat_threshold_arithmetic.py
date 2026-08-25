"""The off-box alarm's 30-minute threshold, checked against the real cadence.

`.github/workflows/heartbeat.yml` is the only watchdog that is not inside the
box it watches, and nothing executes it in CI. Its threshold is a number in a
shell comparison, justified by a comment doing arithmetic over constants that
live in `backend/scheduler.py`. Those constants can move; the comment cannot
follow them.

**The comment was wrong once already.** Until 2026-08-25 it justified 30 minutes
as "two missed full passes", on the grounds that quote passes run "far more
often". That second clause stopped being true when ADR 0071 SS2.6 made the odds
feed follow attention: the 15s cadence runs only while the odds window is open,
and a quiet night keeps it shut. The number survived the correction because the
number never depended on that clause -- but nothing was checking, and a reader
who trusted the stated reason would have concluded a 20-minute gap was
impossible.

So this pins the property the threshold actually needs: **it must sit clear of
the longest sleep a HEALTHY loop can take**, whatever that sleep currently is.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the workflow runs, or that Discord receives anything.** Nothing here
  executes YAML. `workflow_dispatch` with `force_alarm` is how the delivery path
  is proved, and that is a human action.
- **That 30 minutes is the right number.** It pins that the number is not
  *absurd* -- clear of one healthy sleep, and not so wide it sleeps through a
  real outage. Where exactly it sits between those is a judgement.
- **That the recorder heartbeat is written on every pass.** That is
  `tests/test_quote_change_log.py`; this file assumes it, and says so.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.scheduler import JITTER

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "heartbeat.yml"

#: The deployed `--interval`, i.e. `Tempo.slow_interval_s`. `run_loop.py`
#: defaults it and `fly.live.toml` does not override it.
SLOW_INTERVAL_S = 900.0


def _threshold_ms() -> int:
    source = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r'\[ "\$\{age\}" -gt (\d+) \]', source)
    assert match, (
        "the age comparison is not in heartbeat.yml in the shape this test "
        "reads. If the check was rewritten, rewrite this test with it -- do "
        "not delete it, the arithmetic is the point"
    )
    return int(match.group(1))


class TestTheThresholdClearsAHealthySleep:
    def test_the_workflow_still_carries_a_threshold(self):
        """Vacuity guard: every assertion below is over this number."""
        assert _threshold_ms() > 0

    def test_it_sits_above_the_longest_healthy_gap(self):
        """The load-bearing claim.

        A healthy shut-window loop sleeps `slow_interval` jittered up to
        `+JITTER`, and stamps the recorder heartbeat on every pass. So the
        largest age it can reach without anything being wrong is
        `900 * 1.15 = 1035s`. A threshold at or below that alarms on a healthy
        night, and an alarm that cries wolf is worse than none -- it is how the
        2026-08-25 gap was read as a wedge on sight.

        Mutation observed red: set the workflow's threshold to 1000000.
        """
        longest_healthy_ms = SLOW_INTERVAL_S * (1.0 + JITTER) * 1000
        assert _threshold_ms() > longest_healthy_ms, (
            f"the alarm fires at {_threshold_ms() / 60000:.1f} min but a "
            f"healthy loop can be quiet for {longest_healthy_ms / 60000:.1f} "
            f"min, so it would alarm on a working system"
        )

    def test_it_leaves_real_margin_rather_than_scraping_past(self):
        """One healthy sleep plus a slow pass must not reach it either.

        A full pass has been observed at 68.8s on live inside an open window.
        Margin of a whole extra interval is what stops one slow pass on top of
        one long sleep from alarming.
        """
        assert _threshold_ms() >= SLOW_INTERVAL_S * (1.0 + JITTER) * 1000 * 1.5

    def test_it_does_not_sleep_through_a_real_outage(self):
        """The other side of the trade, so this is not a one-way ratchet.

        Past about four missed passes the record is meaningfully behind and the
        Board is showing prices nobody is updating. A threshold that wide is not
        a monitor.
        """
        assert _threshold_ms() <= SLOW_INTERVAL_S * 4 * 1000


class TestTheStatedReasonMatchesTheDeployedSystem:
    def test_the_comment_no_longer_claims_quote_passes_run_far_more_often(self):
        """Corrected 2026-08-25: true only while the odds window is open.

        The claim is what made the threshold look better-justified than it was.
        """
        source = WORKFLOW.read_text(encoding="utf-8")
        assert "passes far more often, so two missed full passes" not in source

    def test_the_alarm_does_not_assert_a_cause_it_cannot_observe(self):
        """It used to say "It is alive and stuck".

        At least three states share this signature -- a wedged pass, a run of
        failing passes, and a restart the record has not caught up with -- and
        the check distinguishes none of them. Naming one sends the reader to
        one place. See `tests/test_loop_failures_are_recorded.py` for the
        instrument that does separate them.
        """
        source = WORKFLOW.read_text(encoding="utf-8")
        assert "It is alive and stuck, which is the state" not in source

    def test_it_still_says_the_recorder_has_stopped(self):
        """Vacuity guard: the two absences above must not be satisfied by the
        alarm having been deleted."""
        source = WORKFLOW.read_text(encoding="utf-8")
        assert "The recorder has stopped" in source
        assert "verdict=stalled" in source
