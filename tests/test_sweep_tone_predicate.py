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

**Since 2026-09-03 it has one import** -- `loopStallAfterMs` from
`./nextOddsWindow`, the refresh panel's own derivation of the stall threshold,
so the strip and the panel judge a silence by one rule instead of two (ADR 0102
§5, Amendment 1). Node's type stripping does not resolve an extensionless
relative specifier, so the driver registers a resolve hook that retries with
`.ts`. The hook is test scaffolding, not a shim over the code under test: it
changes which file a specifier finds, never what the file says.

What this establishes: that `sweepTone` maps seven inputs to the intended tone,
that the `refused` clause changes the answer, and that the silence threshold is
the loop's published cadence and not a literal. What it does **not** establish:
that `WindowBanner.tsx` calls it (`tests/test_window_schedule.py` covers that
edge), that the copy beside a tone is accurate, or that the backend computes
`first_window_open_ms` or `loop_idle_interval_ms` correctly -- that is
`tests/test_window_schedule.py`, `tests/test_watcher_decides_from_fresh_facts.py`
and the timing tests. Separate claims, separate places.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "frontend" / "src" / "lib"
TONE_TS = LIB / "sweepTone.ts"
WINDOW_TS = LIB / "nextOddsWindow.ts"

#: The clause the two mutations below excise, written once.
#:
#: It was two inline string literals until v21 gave `sweepTone` a second outcome
#: to check and the clause went multi-line — at which point both mutations
#: stopped matching and silently... did not, because each asserts
#: `mutated != source` first. That assertion is why this is a rename and not an
#: outage: a mutation test whose mutation no longer applies is a test that
#: passes for free, and these two say so out loud rather than trusting the
#: `.replace` to have done something.
REFUSED_CLAUSE = (
    '  if (w.last_look_outcome === "refused" || '
    'w.last_look_outcome === "failed") {\n    return "warn";\n  }\n'
)

#: The one line in `sweepTone.ts` that turns the published cadence into a
#: threshold. The mutations that restore the retired literal, and the ones that
#: fold an unknown cadence into a boolean, rewrite this line and the one after
#: it -- so if either moves, the `assert ... in source` guards say so instead
#: of the mutation quietly not applying.
DERIVATION_LINE = "  const stallAfterMs = loopStallAfterMs(w);\n"
UNKNOWN_CADENCE_LINE = "  if (stallAfterMs === null) return null;\n"

#: `RUNNER_INTERVAL_S` as the deployed entrypoint pins it, in ms. The value the
#: retired literal hardcoded; here it is a fixture's *belief about the server*,
#: stated per fixture, which is the whole difference.
IDLE_INTERVAL_MS = 900_000

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
#
# Every fixture states `loop_idle_interval_ms`, because since 2026-09-03 the
# verdict reads it. The deployed value is 900s and that is what these carry;
# the fixtures further down vary it, which is the point of publishing it.

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
    "loop_idle_interval_ms": IDLE_INTERVAL_MS,
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
    "loop_idle_interval_ms": IDLE_INTERVAL_MS,
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
    "loop_idle_interval_ms": IDLE_INTERVAL_MS,
}

#: **The outage day.** v21, 2026-08-25. Identical to the refused day except
#: that the odds API is the one saying no: the call went out, came back 401, and
#: `_SERVED_SWEEP` no longer counts it, so `last_sweep_ms` stays on yesterday.
#:
#: This state was **unreachable before v21 and rendered calm the moment it
#: became reachable.** A failed call used to write an `api_credits` row that
#: satisfied `_SERVED_SWEEP`, so `last_sweep_ms` moved to now and the third
#: clause returned calm through the outage. Fixing that in the backend moved the
#: failure into this predicate rather than removing it.
FAILED_BEFORE_THE_WINDOW = {
    "now_ms": ms("2026-08-17T17:35:04Z"),
    "last_look_ms": ms("2026-08-17T17:34:04Z"),
    "last_look_outcome": "failed",
    "last_sweep_ms": YESTERDAY_SWEEP,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
    "loop_idle_interval_ms": IDLE_INTERVAL_MS,
}

SWEPT_TODAY = {
    "now_ms": ms("2026-08-17T21:10:00Z"),
    "last_look_ms": ms("2026-08-17T21:05:00Z"),
    "last_look_outcome": "served",
    "last_sweep_ms": ms("2026-08-17T20:51:00Z"),
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
    "loop_idle_interval_ms": IDLE_INTERVAL_MS,
}

#: 95 minutes of silence against a 15-minute cadence: past two idle intervals
#: (`LOOP_STALL_IDLE_INTERVALS * loop_idle_interval_ms` = 1800s), and past the
#: 1635s worst case a healthy loop permits itself. Not "> 2 x 900s" -- the 900
#: is this fixture's belief about the server, stated in the field, not a
#: constant the predicate knows.
LOOP_STOPPED = {
    "now_ms": ms("2026-08-17T17:35:04Z"),
    "last_look_ms": ms("2026-08-17T16:00:00Z"),
    "last_look_outcome": "skipped",
    "last_sweep_ms": YESTERDAY_SWEEP,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
    "loop_idle_interval_ms": IDLE_INTERVAL_MS,
}

NEVER_LOOKED = {
    "now_ms": ms("2026-08-17T17:35:04Z"),
    "last_look_ms": None,
    "last_look_outcome": None,
    "last_sweep_ms": None,
    "budget_day_start_ms": DAY_START,
    "first_window_open_ms": FIRST_WINDOW,
    "loop_idle_interval_ms": IDLE_INTERVAL_MS,
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
    "loop_idle_interval_ms": IDLE_INTERVAL_MS,
}

# --- The cadence is a fact, and these fixtures move it -----------------------

#: **A loop that sleeps five minutes and has been silent for twelve.** Two of
#: its own intervals is 600s; 700s of silence is a missed pass. Under the
#: retired literal (1800s) this read as a loop merely asleep -- the strip would
#: have waited half an hour to call a fault it could see at ten minutes.
STOPPED_AT_A_FIVE_MINUTE_CADENCE = {
    **LOOP_STOPPED,
    "last_look_ms": ms("2026-08-17T17:35:04Z") - 700_000,
    "loop_idle_interval_ms": 300_000,
}

#: **A loop that sleeps an hour and last looked 35 minutes ago.** Inside one
#: interval: asleep, not stopped. Under the retired literal 2100s > 1800s and
#: this rendered red -- a healthy loop called dead because the reader had
#: decided for itself how often the loop looks.
ASLEEP_AT_AN_HOURLY_CADENCE = {
    **SWEPT_TODAY,
    "last_look_ms": ms("2026-08-17T21:10:00Z") - 35 * 60_000,
    "loop_idle_interval_ms": 3_600_000,
}

#: **One sleep late.** Twenty minutes of silence against a 15-minute cadence:
#: past one interval, inside two, and inside the 1635s a healthy loop permits
#: itself (worst-case jitter plus a pass at its deadline). Asleep, not stopped.
#: This is the fixture that pins the multiplier on the strip -- under
#: `LOOP_STALL_IDLE_INTERVALS = 1` it goes red.
ONE_SLEEP_LATE = {
    **SWEPT_TODAY,
    "last_look_ms": ms("2026-08-17T21:10:00Z") - 20 * 60_000,
}

#: **The cadence could not be read, and the loop looks healthy otherwise.**
#: `RUNNER_INTERVAL_S` set to something that does not parse; the server
#: publishes `null` rather than a guess. The day's sweep has run and the last
#: look is five minutes old -- every spending clause says calm.
CADENCE_UNKNOWN_AND_SWEPT = {
    **SWEPT_TODAY,
    "loop_idle_interval_ms": None,
}

#: **The cadence could not be read, and the loop has been silent 95 minutes.**
#: The alarm cannot fire (ADR 0102: no silence is a stall on an unknown
#: cadence) and the fall-through would say calm -- the day's sweep ran at
#: 20:51 -- over a loop that may well be dead. This is the fixture that decides
#: what "unknown" resolves to on the strip.
CADENCE_UNKNOWN_AND_LONG_SILENT = {
    **SWEPT_TODAY,
    "now_ms": ms("2026-08-17T22:26:00Z"),
    "last_look_ms": ms("2026-08-17T20:51:00Z"),
    "loop_idle_interval_ms": None,
}


# ---------------------------------------------------------------------------
# Running the real function
# ---------------------------------------------------------------------------

_DRIVER = """
import {{ sweepTone }} from "{module}";
const facts = JSON.parse(process.argv[2]);
console.log(JSON.stringify({{ tone: sweepTone(facts) }}));
"""

#: Node strips types but does not resolve `./nextOddsWindow` to
#: `./nextOddsWindow.ts`; the bundler does, and the repo's imports are written
#: for the bundler. This retries an extensionless relative specifier with `.ts`
#: appended, and nothing else -- an absolute or bare specifier, or one that
#: already names an extension, is left to fail exactly as node would fail it.
_HOOK = """
import { registerHooks } from "node:module";
registerHooks({
  resolve(specifier, context, nextResolve) {
    try {
      return nextResolve(specifier, context);
    } catch (e) {
      const relative = specifier.startsWith("./") || specifier.startsWith("../");
      const bare = !/\\.[cm]?[jt]sx?$/.test(specifier);
      if (e && e.code === "ERR_MODULE_NOT_FOUND" && relative && bare) {
        return nextResolve(specifier + ".ts", context);
      }
      throw e;
    }
  },
});
"""


def tone_of(facts: dict, *, source: str | None = None, tmp_path=None) -> str:
    """Call the shipped `sweepTone` with `facts` and return its verdict.

    `source` substitutes a mutated copy of the module, which is how the
    disabling checks below prove a clause is load-bearing. The module's one
    dependency is copied beside it unmodified, so a mutation is a mutation of
    `sweepTone.ts` alone.
    """
    if source is None:
        module_dir = TONE_TS.parent
    else:
        module_dir = tmp_path
        (module_dir / "sweepTone.ts").write_text(source, encoding="utf-8")
        shutil.copy(WINDOW_TS, module_dir / "nextOddsWindow.ts")
    module = "./sweepTone.ts"

    driver = module_dir / "_tone_driver.mjs"
    hook = module_dir / "_tone_hook.mjs"
    driver.write_text(_DRIVER.format(module=module), encoding="utf-8")
    hook.write_text(_HOOK, encoding="utf-8")
    try:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                "--import",
                hook.resolve().as_uri(),
                str(driver),
                json.dumps(facts),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(module_dir),
        )
    finally:
        driver.unlink(missing_ok=True)
        hook.unlink(missing_ok=True)

    assert out.returncode == 0, (
        f"node failed running the predicate:\n{out.stdout}\n{out.stderr}"
    )
    return json.loads(out.stdout.strip())["tone"]


def _without_comments(ts: str) -> str:
    """TypeScript source with `/* */` and `//` comments removed, so a pin on
    what the code *does* is not satisfied or defeated by prose about what it
    used to do."""
    ts = re.sub(r"/\*.*?\*/", "", ts, flags=re.S)
    return re.sub(r"//[^\n]*", "", ts)


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


class TestAnUpstreamOutageIsNeverCalm:
    """v21's new outcome, and the reason it needed a branch of its own.

    The backend fix — a failed call no longer satisfies `_SERVED_SWEEP` — is
    what makes this state reachable. Before it, an outage was calm because the
    failed call had moved `last_sweep_ms`. After it, the outage falls through to
    the window clause instead, and on a morning with no window yet open that
    clause returns calm. Same silence, new route to it.
    """

    def test_a_failed_sweep_before_the_first_window_warns(self):
        """Mutation observed red: remove `|| w.last_look_outcome === "failed"`
        from `sweepTone` — this returns "calm" while the odds API is down."""
        assert tone_of(FAILED_BEFORE_THE_WINDOW) == "warn"

    def test_failed_and_quiet_morning_differ_only_in_the_outcome(self):
        """The same isolation the refused day gets: if these two states differ
        in any other field, the verdict could be coming from somewhere else."""
        differing = {
            k
            for k in QUIET_MORNING
            if QUIET_MORNING[k] != FAILED_BEFORE_THE_WINDOW[k]
        }
        assert differing == {"last_look_outcome"}, differing

    def test_failed_is_not_louder_than_a_dead_loop(self):
        """`alarm` means the loop itself stopped. Here the loop is alive and
        being refused by someone else, which is a different repair — waiting or
        rotating a key, not restarting a machine. Keeping the tiers distinct is
        what stops `alarm` from becoming the tone everything wears."""
        assert tone_of(FAILED_BEFORE_THE_WINDOW) != "alarm"


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


class TestTheSilenceThresholdIsTheLoopsOwnCadence:
    """ADR 0102 §5, Amendment 1: the strip reads `loop_idle_interval_ms`.

    Until 2026-09-03 `sweepTone.ts` said `LOOK_SILENT_MS = 2 * 900_000`. The
    rule (two idle intervals) was the refresh panel's rule reached
    independently; the 900 was the loop's cadence written into the reader.
    A threshold that names "normal" must be derived from the thing's actual
    cadence, published by the side that owns it -- `tasks/lessons.md`, "one
    predicate, two spellings". These fixtures move the cadence and watch the
    verdict move with it, which a literal cannot do.
    """

    def test_a_five_minute_loop_silent_for_twelve_is_an_alarm(self):
        """700s against a 300s cadence is a missed pass. Under the retired
        literal this waited until 1800s -- half an hour blind on a loop that
        should have written a row every five minutes."""
        assert tone_of(STOPPED_AT_A_FIVE_MINUTE_CADENCE) == "alarm"

    def test_an_hourly_loop_silent_for_thirty_five_minutes_is_asleep(self):
        """2100s against a 3600s cadence is one sleep. Under the retired
        literal (1800s) this was red: a healthy loop called dead because the
        reader had its own opinion of how often the loop looks."""
        assert tone_of(ASLEEP_AT_AN_HOURLY_CADENCE) != "alarm"
        assert tone_of(ASLEEP_AT_AN_HOURLY_CADENCE) == "calm"

    def test_one_sleep_late_is_asleep_not_stopped(self):
        """1200s against a 900s cadence. ADR 0102 §2.1: one sleep at worst-case
        jitter plus one pass at its deadline is 1635s, so silence inside two
        intervals can be a late pass and silence past two cannot. Mutation
        observed red: `LOOP_STALL_IDLE_INTERVALS = 1` in `nextOddsWindow.ts`."""
        assert tone_of(ONE_SLEEP_LATE) == "calm"
        assert tone_of(LOOP_STOPPED) == "alarm"

    def test_the_fast_fixture_differs_from_the_stopped_loop_only_in_cadence_and_age(
        self,
    ):
        differing = {
            k for k in LOOP_STOPPED if LOOP_STOPPED[k] != STOPPED_AT_A_FIVE_MINUTE_CADENCE[k]
        }
        assert differing == {"last_look_ms", "loop_idle_interval_ms"}, differing

    def test_the_slow_fixture_differs_from_a_swept_day_only_in_cadence_and_age(
        self,
    ):
        differing = {
            k for k in SWEPT_TODAY if SWEPT_TODAY[k] != ASLEEP_AT_AN_HOURLY_CADENCE[k]
        }
        assert differing == {"last_look_ms", "loop_idle_interval_ms"}, differing

    def test_the_predicate_contains_no_number_of_seconds(self):
        """The literal is gone from the code, not just renamed. Comments are
        stripped first: the module's own history names `2 * 900_000` and that
        sentence must be allowed to stay."""
        code = _without_comments(TONE_TS.read_text(encoding="utf-8"))
        assert "LOOK_SILENT_MS" not in code
        assert not re.search(r"\b900_?000\b|\b1_?800_?000\b|\b900\b", code), (
            "sweepTone.ts has grown a number of seconds again; the cadence is "
            "the server's fact and the threshold is loopStallAfterMs's"
        )
        assert "loopStallAfterMs(w)" in code


class TestAnUnknownCadenceIsAmber:
    """`loop_idle_interval_ms: null` -- the server could not read the cadence.

    ADR 0102's rule is that no silence is a stall on an unknown cadence, so the
    alarm may not fire. The strip's own rule is that a liveness guard may be
    noisy and may not be silent, so it may not fall through to calm either --
    every clause below the alarm is about spending, and a loop that swept at
    20:51 and died at 21:00 satisfies "the day's sweeps have run" until
    tomorrow. Unknown therefore resolves to `warn`, on its own branch, and
    `WindowBanner` names the variable that could not be read. That is the
    decision `sweepTone.ts` documents; these pin it from both sides.
    """

    def test_a_healthy_looking_loop_under_an_unknown_cadence_is_not_calm(self):
        """The strip cannot vouch for liveness, so it does not."""
        assert tone_of(CADENCE_UNKNOWN_AND_SWEPT) == "warn"

    def test_a_long_silence_under_an_unknown_cadence_is_not_an_alarm(self):
        """ADR 0102: unreadable resolves to a refusal to claim, not to 900."""
        assert tone_of(CADENCE_UNKNOWN_AND_LONG_SILENT) != "alarm"

    def test_a_long_silence_under_an_unknown_cadence_is_not_calm_either(self):
        """The fall-through would say calm here -- the day's sweep ran -- over a
        loop 95 minutes silent. Amber is the refusal to say either."""
        assert tone_of(CADENCE_UNKNOWN_AND_LONG_SILENT) == "warn"

    def test_the_two_unknown_fixtures_bracket_the_known_verdicts(self):
        """With the cadence known, the same two states are calm and alarm
        respectively; setting it to `null` collapses both to warn. That is the
        shape of "the strip stopped judging", asserted rather than described."""
        assert tone_of({**CADENCE_UNKNOWN_AND_SWEPT, "loop_idle_interval_ms": IDLE_INTERVAL_MS}) == "calm"
        assert (
            tone_of({**CADENCE_UNKNOWN_AND_LONG_SILENT, "loop_idle_interval_ms": IDLE_INTERVAL_MS})
            == "alarm"
        )


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
        """The banner asks `loopIsSilent` and derives nothing itself.

        Two definitions of one threshold is how the copy a reader sees and the
        tone they see drift apart while both tests stay green. Before
        2026-09-03 the banner imported `LOOK_SILENT_MS` and compared against
        it -- one constant, two comparisons. Now the *predicate* is shared, so
        the banner may not name the retired constant, may not carry a number
        of seconds, and may not re-derive the threshold from
        `LOOP_STALL_IDLE_INTERVALS` or `loopStallAfterMs` on its own: the one
        liveness question it is allowed to ask is `loopIsSilent(w)`.
        """
        code = _without_comments(self.BANNER.read_text(encoding="utf-8"))
        assert "const LOOK_SILENT_MS" not in code
        assert "LOOK_SILENT_MS" not in code
        assert "LOOP_STALL_IDLE_INTERVALS" not in code
        assert "loopStallAfterMs" not in code
        assert not re.search(r"\b900_?000\b|\b1_?800_?000\b", code)
        assert "loopIsSilent(w)" in code

    def test_the_banner_has_words_for_an_unknown_cadence(self):
        """`loopIsSilent` returns three values and the banner must not fold the
        third into either of the others -- that is the "unknown is not 0" rule
        with a rendering half. It names the variable, so the amber is a repair
        instruction and not a mood."""
        code = _without_comments(self.BANNER.read_text(encoding="utf-8"))
        assert "silent === null" in code
        assert "RUNNER_INTERVAL_S" in code

    def test_the_server_sends_the_fields_the_predicate_reads(self):
        """The one end that source-reading the frontend cannot cover.

        Everything above passes if `ActionableWindow.to_dict` stops emitting
        `first_window_open_ms` tomorrow: the field arrives `undefined`, the
        `!== null` test is true, `now_ms >= undefined` is false, and the strip
        renders permanently calm — a silent failure that looks like a legitimate
        quiet day. Exactly the shape this lane exists to remove. Since
        2026-09-03 the same holds of `loop_idle_interval_ms`: dropped, it
        arrives `undefined`, `loopStallAfterMs` returns `null`, and every
        strip on every deploy goes amber for a cadence the server does know.
        """
        timing = (REPO / "backend" / "odds" / "timing.py").read_text(
            encoding="utf-8"
        )
        assert '"first_window_open_ms": self.first_window_open_ms' in timing
        assert '"loop_idle_interval_ms": self.loop_idle_interval_ms' in timing

    def test_the_type_declares_them_so_a_dropped_field_breaks_the_build(self):
        api = (REPO / "frontend" / "src" / "lib" / "api.ts").read_text(
            encoding="utf-8"
        )
        assert "first_window_open_ms: number | null;" in api
        assert "loop_idle_interval_ms: number | null;" in api


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
        mutated = source.replace(REFUSED_CLAUSE, "")
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
        window_clause = (
            "  if (w.first_window_open_ms !== null && "
            'w.now_ms >= w.first_window_open_ms) {\n    return "warn";\n  }'
        )
        assert REFUSED_CLAUSE in source and window_clause in source
        mutated = source.replace(REFUSED_CLAUSE, "").replace(
            window_clause,
            "  if (w.first_window_open_ms === null || "
            'w.now_ms < w.first_window_open_ms) {\n    return "calm";\n  }\n'
            + REFUSED_CLAUSE,
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

    def test_restoring_the_literal_misjudges_every_cadence_that_is_not_900s(
        self, tmp_path
    ):
        """Mutation: put `2 * 900_000` back where the derivation is.

        The retired predicate, reconstructed. It must read the five-minute loop
        that missed a pass as merely asleep and the hourly loop mid-sleep as
        dead -- wrong in both directions, because it has an opinion about the
        cadence and the cadence is not its to have. Every 900s fixture above
        stays exactly where it was under the mutation, which is why the
        original fixture set could never have caught this.
        """
        source = TONE_TS.read_text(encoding="utf-8")
        assert DERIVATION_LINE in source, "the derivation moved; update this test"
        mutated = source.replace(
            DERIVATION_LINE, "  const stallAfterMs = 2 * 900_000;\n"
        )
        assert mutated != source, "the mutation did not apply; update this test"
        assert (
            tone_of(STOPPED_AT_A_FIVE_MINUTE_CADENCE, source=mutated, tmp_path=tmp_path)
            != "alarm"
        )
        assert (
            tone_of(ASLEEP_AT_AN_HOURLY_CADENCE, source=mutated, tmp_path=tmp_path)
            == "alarm"
        )
        # The control: the deployed cadence is indistinguishable under the
        # mutation, so a fixture set that only ever said 900 proves nothing.
        assert tone_of(LOOP_STOPPED, source=mutated, tmp_path=tmp_path) == "alarm"
        assert tone_of(SWEPT_TODAY, source=mutated, tmp_path=tmp_path) == "calm"

    def test_folding_an_unknown_cadence_into_alive_renders_a_dead_loop_calm(
        self, tmp_path
    ):
        """Mutation: `return null` -> `return false` on the unknown-cadence line.

        The natural shortcut -- "no threshold, so not silent" -- and it is the
        silent failure the amber branch exists to refuse: the day's sweep ran,
        so the fall-through says calm over 95 minutes of silence.
        """
        source = TONE_TS.read_text(encoding="utf-8")
        assert UNKNOWN_CADENCE_LINE in source, "the line moved; update this test"
        mutated = source.replace(
            UNKNOWN_CADENCE_LINE, "  if (stallAfterMs === null) return false;\n"
        )
        assert mutated != source, "the mutation did not apply; update this test"
        assert (
            tone_of(CADENCE_UNKNOWN_AND_LONG_SILENT, source=mutated, tmp_path=tmp_path)
            == "calm"
        )

    def test_folding_an_unknown_cadence_into_silent_alarms_on_a_healthy_loop(
        self, tmp_path
    ):
        """Mutation: `return null` -> `return true` on the same line.

        The other shortcut, and ADR 0102's named defect: a loop five minutes
        into a sleep called dead because the reader could not learn how long
        the sleep is.
        """
        source = TONE_TS.read_text(encoding="utf-8")
        mutated = source.replace(
            UNKNOWN_CADENCE_LINE, "  if (stallAfterMs === null) return true;\n"
        )
        assert mutated != source, "the mutation did not apply; update this test"
        assert (
            tone_of(CADENCE_UNKNOWN_AND_SWEPT, source=mutated, tmp_path=tmp_path)
            == "alarm"
        )
