"""`leg_price_ms` is split into four phases, and all four are always reported.

**What this establishes.** That a pass reports `leg_price_setup_ms`,
`leg_price_link_ms`, `leg_price_judge_ms` and `leg_price_persist_ms`; that they
are reported at zero rather than omitted; that `run_pricing_pass` actually
assigns them; that they account for `leg_price_ms` rather than leaving work
untimed; and that the review-and-persist cost lands on `persist` and not on
`judge`.

**What it does not.** It does not establish that any phase is fast, or that
these four names are the right cut -- a phase could dominate for a reason none
of them captures. It measures wall clock, so on a contended box a phase reads
slow because the process was descheduled, which is the honest number for "why
is the box unresponsive" and the wrong one for "how much CPU did this need".
And it drives an empty slate, so it says nothing about how any phase scales
with the number of events.

**Why it exists.** On 2026-08-19 `leg_price_ms` became the entire quote pass --
12-20s of a 17-32s pass against a 15s cadence -- and one total cannot say which
part moved. That is the same argument that produced the outer `leg_*` timings a
day earlier, after three sessions each guessed a different leg and each was
wrong. Applied one level down.

The `persist` boundary is the one that would mislead if drawn differently:
`review` leaves the process for Anthropic, so a slow fleet must not read as slow
arithmetic.
"""

from __future__ import annotations

import inspect
import time

from backend import runner
from backend.runner import PassCounts, run_pricing_pass
from backend.store import db

SUB_LEGS = (
    "leg_price_setup_ms",
    "leg_price_link_ms",
    "leg_price_judge_ms",
    "leg_price_persist_ms",
)


def _empty_pass(tmp_path, name="sub_legs.db"):
    conn = db.init_db(tmp_path / name)
    try:
        return run_pricing_pass(conn, [], now=1_787_000_000_000)
    finally:
        conn.close()


class TestEveryPhaseIsReportedEvenWhenZero:
    """Absence and zero need opposite responses, so zero must be printed.

    A missing key means the phase was never timed; a zero means it ran and is
    not the problem. `as_dict` filters falsy values unless the key is in
    `ALWAYS_REPORT`, and the skeptic fields were already lost to exactly that
    filter, in exactly this state.
    """

    def test_a_pass_that_did_nothing_still_names_all_four(self) -> None:
        reported = PassCounts().as_dict()
        for leg in SUB_LEGS:
            assert leg in reported, (
                f"`{leg}` vanishes from a pass line at zero, so 'this phase is "
                "fast' cannot be told from 'this phase was never timed'"
            )
            assert reported[leg] == 0

    def test_the_total_is_still_reported_beside_the_parts(self) -> None:
        """Reporting parts and dropping the whole makes the sum uncheckable.

        A log line is the only place these are ever read, so the check that the
        parts account for the whole has to be possible from the line itself.
        """
        assert "leg_price_ms" in PassCounts().as_dict()

    def test_a_timed_phase_reports_its_own_number(self) -> None:
        counts = PassCounts()
        for i, leg in enumerate(SUB_LEGS, start=1):
            setattr(counts, leg, i * 100)
        reported = counts.as_dict()
        assert [reported[leg] for leg in SUB_LEGS] == [100, 200, 300, 400]


class TestTheCodeActuallyFillsThemIn:
    """Fields existing is not the same as the pass assigning them.

    Without this, the guards above pass against four permanently-zero columns
    that look exactly like four fast phases.
    """

    def test_the_pricing_pass_assigns_every_phase(self) -> None:
        source = inspect.getsource(runner.run_pricing_pass)
        for leg in SUB_LEGS:
            assert f".{leg} =" in source, (
                f"`run_pricing_pass` no longer records `{leg}`; the column "
                "will read 0 forever and be mistaken for a fast phase"
            )

    def test_a_real_pass_returns_an_object_carrying_every_phase(
        self, tmp_path
    ) -> None:
        """The half source inspection cannot reach: the pass actually runs.

        Deliberately weak, and the weakness is recorded rather than dressed
        up. An earlier version of this test claimed to catch the phases being
        assigned to the wrong object -- it does not, and cannot, because
        `_review_and_persist` mutates and returns the *same* `PassCounts` it
        was given, so `priced is counts` and both spellings are identical.
        Disabling the assignment and watching this stay green is how that was
        found.

        What it does establish is that `run_pricing_pass` completes against a
        real database and hands back an object carrying all four names -- which
        is what makes the sum check below meaningful rather than vacuous.
        """
        counts = _empty_pass(tmp_path)
        for leg in SUB_LEGS:
            assert hasattr(counts, leg), leg
        assert counts.leg_price_ms >= 0


class TestThePhasesAccountForTheWhole:
    def test_phases_sum_to_the_total(self, tmp_path) -> None:
        """Catches a new phase added without a timer.

        New work between two existing boundaries would otherwise be attributed
        to whichever neighbour happens to enclose it, or fall outside all four
        and be silently missing from the split -- which is the failure this
        whole file exists to prevent, one level up.
        """
        counts = _empty_pass(tmp_path)
        parts = sum(getattr(counts, leg) for leg in SUB_LEGS)
        # Slack for four independent int() truncations plus the handful of
        # assignments between the last boundary and the outer stop.
        assert parts <= counts.leg_price_ms + 8, (
            f"phases sum to {parts}ms, more than the {counts.leg_price_ms}ms "
            "total -- the boundaries overlap"
        )
        assert parts >= counts.leg_price_ms - 8, (
            f"phases sum to {parts}ms but the total is {counts.leg_price_ms}ms "
            "-- some work in run_pricing_pass is outside every timer"
        )

    def test_a_slow_persist_lands_on_persist_and_not_on_judge(
        self, tmp_path, monkeypatch
    ) -> None:
        """The boundary that would send the next session to the wrong place.

        `_review_and_persist` is where the Anthropic round trip happens. If its
        cost were inside `judge`, a slow fleet would read as slow devigging.
        Verified by making it slow and watching which phase moves -- not by
        reading where the timer is written.
        """
        real = runner._review_and_persist

        def slow(*args, **kwargs):
            time.sleep(0.25)
            return real(*args, **kwargs)

        monkeypatch.setattr(runner, "_review_and_persist", slow)
        counts = _empty_pass(tmp_path, name="slow_persist.db")

        assert counts.leg_price_persist_ms >= 250, (
            f"a 250ms review-and-persist landed as "
            f"{counts.leg_price_persist_ms}ms on persist"
        )
        assert counts.leg_price_judge_ms < 250, (
            f"judge absorbed the persist cost ({counts.leg_price_judge_ms}ms), "
            "so a slow Skeptic will read as slow arithmetic"
        )
        assert counts.leg_price_ms >= 250
