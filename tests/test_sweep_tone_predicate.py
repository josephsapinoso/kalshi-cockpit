"""The sweep strip's verdict, executed rather than read.

**Why this file runs `node` instead of asserting on source text.** Every other
guard this repo has over the frontend (`tests/test_window_schedule.py`,
`tests/test_demo_fidelity.py`) reads the `.tsx` as a string and asserts a
substring is present, because there is no JavaScript test runner here. That is
the right tool for *"does the component read this field"* and it is worth nothing
for *"does this predicate reach the right verdict"*: a substring assertion passes
unchanged on a predicate that has been exactly inverted. The defect this lane
fixes was a wrong verdict, not a missing field, so a source-text test could not
have caught it and cannot prove it fixed.

`frontend/src/lib/sweepTone.ts` is therefore plain TypeScript with no React
import, and node v24 strips types natively, so the real shipped function can be
called with real recorded states.

What this establishes: that `sweepTone` maps six inputs to the intended tone, and
that the `refused` clause changes the answer. What it does **not** establish:
that `WindowBanner.tsx` calls it (`tests/test_window_schedule.py` covers that
edge), that the copy beside a tone is accurate, or that the backend computes
`first_window_open_ms` correctly -- that is `tests/test_window_schedule.py` and
the timing tests. Three separate claims, three separate places.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TONE_TS = REPO / "frontend" / "src" / "lib" / "sweepTone.ts"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: this guard is real "
        "where node exists (CI and both dev machines) and a missing runtime is "
        "an environment fact, not a pending failure."
    ),
)


def ms(iso: str) -> int:
    """Epoch ms from a UTC ISO string, so fixtures read as times not integers."""
    return int(
        dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000
    )


# ---------------------------------------------------------------------------
# The recorded states
# ---------------------------------------------------------------------------
# These are not invented. F1 and F3 are built from rows read off the live
# database on 2026-08-17 (`api_credits`, `odds_sweep_log`); the budget day
# boundary is the deployed 10:00Z and the window time is the one the scheduler
# itself wrote into `odds_sweep_log.detail` that morning:
#
#   667  2026-08-17T17:34:04Z  skipped
#        "no sweep: next slot is baseball_mlb at 20:50Z-21:50Z for 7 game(s)
#         from 22:05Z, sweeping 75-15 min before first kickoff"

DAY_START = ms("2026-08-17T10:00:00Z")      # budget day boundary, deployed value
FIRST_WINDOW = ms("2026-08-17T20:50:00Z")   # first slot opens, from the log above
YESTERDAY_SWEEP = ms("2026-08-16T22:59:23Z")  # last served sweep, api_credits


#: **The false positive.** Today's actual live state at 17:35Z: the loop is
#: looking every ~15 minutes and correctly declining, because the day's first
#: window does not open for another three hours. The old predicate rendered this
#: amber -- "the loop is alive and declining" -- and did so on 6 of 6 budget days
#: sampled, for 6.5 to 10.8 hours each.
QUIET_MORNING = {
    "now_ms": ms("2026-08-17T17:35:04Z"),
    "last_look_ms": ms("2026-08-17T17:34:04Z"),
    "last_look_outcome": "skipped",
    "last_sweep_ms": YESTERDAY_SWEEP,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
}

#: **The true positive.** The 17-hour incident shape: the loop is alive and
#: looking, a window has opened, and nothing has swept through it. This is the
#: failure the strip exists to catch and the one the fix must not silence.
WINDOW_OPENED_AND_NOTHING_SWEPT = {
    "now_ms": ms("2026-08-17T23:50:00Z"),
    "last_look_ms": ms("2026-08-17T23:45:00Z"),
    "last_look_outcome": "skipped",
    "last_sweep_ms": YESTERDAY_SWEEP,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
}

#: **The refused day.** Credits exhausted before the first window ever opens.
#: `slots_for_sport` is unfiltered by budget, so the schedule still says 20:50Z
#: and "no window has opened yet" is true -- while the recorder is in fact dead
#: until tomorrow. Two such rows exist in the live `odds_sweep_log`.
REFUSED_BEFORE_THE_WINDOW = {
    "now_ms": ms("2026-08-17T17:35:04Z"),
    "last_look_ms": ms("2026-08-17T17:34:04Z"),
    "last_look_outcome": "refused",
    "last_sweep_ms": YESTERDAY_SWEEP,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
}

SWEPT_TODAY = {
    "now_ms": ms("2026-08-17T21:10:00Z"),
    "last_look_ms": ms("2026-08-17T21:05:00Z"),
    "last_look_outcome": "served",
    "last_sweep_ms": ms("2026-08-17T20:51:00Z"),
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
}

LOOP_STOPPED = {
    "now_ms": ms("2026-08-17T17:35:04Z"),
    "last_look_ms": ms("2026-08-17T16:00:00Z"),  # > 2 x 900s
    "last_look_outcome": "skipped",
    "last_sweep_ms": YESTERDAY_SWEEP,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
}

NEVER_LOOKED = {
    "now_ms": ms("2026-08-17T17:35:04Z"),
    "last_look_ms": None,
    "last_look_outcome": None,
    "last_sweep_ms": None,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
}

#: No fixture is near enough to schedule against, so no window opens at all.
#: Distinct from "not yet" and the component says so, but the tone is the same:
#: there is no moment today at which declining to sweep would be news.
NO_WINDOW_TODAY = {
    "now_ms": ms("2026-08-17T17:35:04Z"),
    "last_look_ms": ms("2026-08-17T17:34:04Z"),
    "last_look_outcome": "skipped",
    "last_sweep_ms": YESTERDAY_SWEEP,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": None,
}


# ---------------------------------------------------------------------------
# Running the real function
# ---------------------------------------------------------------------------

_DRIVER = """
import {{ sweepTone }} from "{module}";
const facts = JSON.parse(process.argv[2]);
console.log(JSON.stringify({{ tone: sweepTone(facts) }}));
"""


def tone_of(facts: dict, *, source: str | None = None, tmp_path=None) -> str:
    """Call the shipped `sweepTone` with `facts` and return its verdict.

    `source` substitutes a mutated copy of the module, which is how the
    disabling checks below prove a clause is load-bearing.
    """
    if source is None:
        module_dir = TONE_TS.parent
        module = "./sweepTone.ts"
    else:
        module_dir = tmp_path
        (module_dir / "sweepTone.ts").write_text(source, encoding="utf-8")
        module = "./sweepTone.ts"

    driver = module_dir / "_tone_driver.mjs"
    driver.write_text(_DRIVER.format(module=module), encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(facts)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(module_dir),
        )
    finally:
        driver.unlink(missing_ok=True)

    assert out.returncode == 0, (
        f"node failed running the predicate:\n{out.stdout}\n{out.stderr}"
    )
    return json.loads(out.stdout.strip())["tone"]


class TestThePairThatDecidesTheFix:
    """The two states the fix must tell apart. If it cannot, it is not a fix."""

    def test_a_quiet_morning_before_the_first_window_is_not_a_warning(self):
        """The false positive, and it is today's real state.

        Nothing has swept since the budget day opened at 10:00Z -- true, and
        meaningless, because the first window does not open until 20:50Z. There
        was no window in which to spend. Rendering this amber for ~11 hours is
        what trains a reader to ignore the strip on the day it is true.
        """
        assert tone_of(QUIET_MORNING) != "warn"
        assert tone_of(QUIET_MORNING) == "calm"

    def test_a_window_that_opened_with_nothing_swept_still_warns(self):
        """The true positive. This is the 17-hour incident and it must survive.

        Same loop, same absent sweep, same budget day -- the *only* thing that
        changed from the fixture above is that a window has now opened. If this
        renders calm the fix has silenced the failure it was built around, and
        the correct action is to abandon the lane rather than ship it.
        """
        assert tone_of(WINDOW_OPENED_AND_NOTHING_SWEPT) == "warn"

    def test_the_two_differ_only_in_whether_a_window_had_opened(self):
        """The pair is a controlled comparison, not two unrelated worlds.

        Asserted rather than trusted: if a future edit makes these fixtures
        differ on a second axis, the test above stops being evidence about the
        window clause while still passing.
        """
        differing = {
            k
            for k in QUIET_MORNING
            if QUIET_MORNING[k] != WINDOW_OPENED_AND_NOTHING_SWEPT[k]
        }
        assert differing == {"now_ms", "last_look_ms"}, differing


class TestABudgetRefusalIsNeverCalm:
    """A day the budget killed must warn, window or no window."""

    def test_refused_before_the_first_window_warns(self):
        """Credits gone at 17:35Z, first window still three hours out.

        `slots_for_sport` is unfiltered by budget and says so in its own
        docstring, so the schedule still promises a 20:50Z window that will never
        be served. Every other clause in the predicate reads this as the quiet
        morning above.
        """
        assert tone_of(REFUSED_BEFORE_THE_WINDOW) == "warn"

    def test_refused_and_quiet_morning_differ_only_in_the_outcome(self):
        differing = {
            k
            for k in QUIET_MORNING
            if QUIET_MORNING[k] != REFUSED_BEFORE_THE_WINDOW[k]
        }
        assert differing == {"last_look_outcome"}, differing


class TestTheRemainingStatesAreUnchanged:
    """The fix must not move any verdict it was not aimed at."""

    def test_a_sweep_today_is_calm(self):
        assert tone_of(SWEPT_TODAY) == "calm"

    def test_a_stopped_loop_is_an_alarm(self):
        assert tone_of(LOOP_STOPPED) == "alarm"

    def test_having_never_looked_warns(self):
        assert tone_of(NEVER_LOOKED) == "warn"

    def test_a_day_with_no_window_at_all_is_calm(self):
        """`None` is "no window opens today", and nothing is owed on such a day.

        It is not read as reassurance on its own: a loop that is not running
        shows up as `last_look_ms` going stale, which the alarm above covers.
        """
        assert tone_of(NO_WINDOW_TODAY) == "calm"


class TestTheVerdictIsActuallyTheOneOnScreen:
    """Extracting a predicate to make it testable can orphan it.

    Every assertion above would pass unchanged if `WindowBanner.tsx` kept its own
    inline copy of the tone logic and never imported this module — the tests
    would be green and the screen would be running different code. That is this
    repo's named defect (`tests/test_has_callers.py`, and four modules that were
    complete, tested and invoked by nothing), reproduced by a refactor done for
    good reasons. So the edge is pinned here.
    """

    BANNER = REPO / "frontend" / "src" / "components" / "WindowBanner.tsx"

    def test_the_banner_imports_the_predicate(self):
        src = self.BANNER.read_text(encoding="utf-8")
        assert "sweepTone" in src
        assert "@/lib/sweepTone" in src

    def test_the_banner_assigns_its_tone_from_the_predicate(self):
        """Importing it is not using it. The assignment is the edge."""
        src = self.BANNER.read_text(encoding="utf-8")
        assert "sweepTone(w)" in src

    def test_the_banner_declares_no_second_copy_of_the_threshold(self):
        """`LOOK_SILENT_MS` is imported, not redeclared.

        Two definitions of one threshold is how the copy a reader sees and the
        tone they see drift apart while both tests stay green.
        """
        src = self.BANNER.read_text(encoding="utf-8")
        assert "const LOOK_SILENT_MS" not in src

    def test_the_server_sends_the_field_the_predicate_reads(self):
        """The one end that source-reading the frontend cannot cover.

        Everything above passes if `ActionableWindow.to_dict` stops emitting
        `first_window_open_ms` tomorrow: the field arrives `undefined`, the
        `!== null` test is true, `now_ms >= undefined` is false, and the strip
        renders permanently calm — a silent failure that looks like a legitimate
        quiet day. Exactly the shape this lane exists to remove.
        """
        timing = (REPO / "backend" / "odds" / "timing.py").read_text(
            encoding="utf-8"
        )
        assert '"first_window_open_ms": self.first_window_open_ms' in timing

    def test_the_type_declares_it_so_a_dropped_field_breaks_the_build(self):
        api = (REPO / "frontend" / "src" / "lib" / "api.ts").read_text(
            encoding="utf-8"
        )
        assert "first_window_open_ms: number | null;" in api


class TestTheGuardsAreReal:
    """Every clause disabled by a named mutation, and watched to fail.

    Per CLAUDE.md: a guard is verified by disabling it and watching the test go
    red. A clause that can be deleted with the suite still green is decoration.
    """

    def test_deleting_the_window_clause_restores_the_false_positive(
        self, tmp_path
    ):
        """Mutation: drop the `first_window_open_ms` test, i.e. the old predicate.

        This is the bug, reconstructed. It must make the quiet morning amber
        again -- if it does not, the clause is not what fixed it and the
        measurement above is being credited to the wrong change.
        """
        source = TONE_TS.read_text(encoding="utf-8")
        window_clause = (
            "  if (w.first_window_open_ms !== null && "
            'w.now_ms >= w.first_window_open_ms) {\n    return "warn";\n  }'
        )
        assert window_clause in source, "the clause moved; update this test"
        mutated = source.replace(window_clause, '  return "warn";')
        assert mutated != source, "the mutation did not apply; update this test"
        assert (
            tone_of(QUIET_MORNING, source=mutated, tmp_path=tmp_path) == "warn"
        )

    def test_deleting_the_refused_clause_makes_a_dead_day_look_calm(
        self, tmp_path
    ):
        """Mutation: drop the `refused` test.

        The slot-time-only version of this fix. It renders a recorder that is
        dead until tomorrow as calm -- a false negative on the failure the strip
        exists to catch, in exchange for the false positive it removes. Strictly
        worse than the bug. This test is why the clause is not optional.
        """
        source = TONE_TS.read_text(encoding="utf-8")
        mutated = source.replace(
            '  if (w.last_look_outcome === "refused") return "warn";\n', ""
        )
        assert mutated != source, "the mutation did not apply; update this test"
        assert (
            tone_of(REFUSED_BEFORE_THE_WINDOW, source=mutated, tmp_path=tmp_path)
            == "calm"
        )

    def test_gating_the_refused_clause_behind_an_early_window_return_breaks_it(
        self, tmp_path
    ):
        """Mutation: rewrite the window test as an early `return "calm"`.

        **This test exists because the obvious version of it does not work, and
        the difference is worth keeping.** The first draft asserted that placing
        the `refused` clause *after* the window clause would break it. It does
        not: both branches return `"warn"` and the question is a disjunction, so
        swapping the two lines changes nothing. The mutation refused to go red
        and the claim in `sweepTone.ts` was corrected rather than the test
        weakened.

        What genuinely breaks is *gating* -- an early return on "no window yet",
        which is the natural way to write this fix and exactly the shape the
        slot-time-only version would have had. The refused day never reaches its
        own clause. That is the failure mode, and this is the mutation that
        reproduces it.
        """
        source = TONE_TS.read_text(encoding="utf-8")
        refused_line = '  if (w.last_look_outcome === "refused") return "warn";\n'
        window_clause = (
            "  if (w.first_window_open_ms !== null && "
            'w.now_ms >= w.first_window_open_ms) {\n    return "warn";\n  }'
        )
        assert refused_line in source and window_clause in source
        mutated = source.replace(refused_line, "").replace(
            window_clause,
            "  if (w.first_window_open_ms === null || "
            'w.now_ms < w.first_window_open_ms) {\n    return "calm";\n  }\n'
            + refused_line,
        )
        assert mutated != source, "the mutation did not apply; update this test"
        assert (
            tone_of(REFUSED_BEFORE_THE_WINDOW, source=mutated, tmp_path=tmp_path)
            == "calm"
        )
        # And the quiet morning still reads calm under the mutation, so the two
        # designs are separated by the refused day alone -- which is why that day
        # had to be a fixture rather than an argument.
        assert (
            tone_of(QUIET_MORNING, source=mutated, tmp_path=tmp_path) == "calm"
        )
