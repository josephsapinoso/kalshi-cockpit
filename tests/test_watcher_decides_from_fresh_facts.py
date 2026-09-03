"""The cold-open watcher decides from fresh facts, on two clocks, not from a
snapshot older than its own heartbeat.

The defect, measured on live 2026-09-03. `RefreshWhenPriced` was gated on
`anAutomaticBuyIsComing(actionable)` computed on the SERVER RENDER. That
reading called the loop stalled when `last_look_ms` was over a hardcoded 180s
-- a number written for the fast cadence (a pass every ~18s while a window is
open) and applied to the idle one (`RUNNER_INTERVAL_S` = 900s; median 926.8s
full-to-full across 6,066 live passes). So on a cold open after a quiet hour
the snapshot said "stalled", the watcher returned before setting a timer, and
the screen said *"It will not change by itself until you reload it"* -- while
the page's own heartbeat woke the loop within 5s and the buy landed ~3s later.
Of 26 visits, 8 opened with the last look over 180s old; all 8 were cold; 0 of
the 11 opens with fresh fixtures were called stalled. 53% of cold opens lost
the watcher, and the watcher exists for cold opens.

Two questions were being answered with one number. "Is the loop alive" is a
question about a cadence, and the cadence is now published
(`loop_idle_interval_ms`). "Is a buy coming because this page is open" is a
question the render cannot answer -- the heartbeat that schedules the buy does
not exist yet -- so the watcher asks it of fresh facts on every poll
(`readWatch`), with a stall test of its own on a clock the render cannot have:
a visible page is waking the loop every minute, so silence spanning three
minutes of continuous visibility is a real stall.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the effect running.** No React runner here; the pure
  predicate is executed with node and the component is pinned at source.
  Whether the timers fire and whether `router.refresh()` re-renders are
  browser behaviours.
- **Nothing about the loop waking.** `test_scheduler.py` and
  `test_desk_follows_attention.py` own `sleep_until` and `ArrivalWatch`; this
  file takes the ~5s wake as given and pins only that the watcher's constants
  are consistent with it.
- **Nothing about the heartbeat reaching the server.** `readWatch`'s fast
  clock assumes a visible page is waking the loop. If `recordAttention` fails
  silently, three minutes of silence reads as a stall on a loop nobody woke.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.odds import attention
from backend.odds.timing import (
    ENTRYPOINT_RUNNER_INTERVAL_S,
    loop_idle_interval_ms_from_env,
    window_status,
)
from backend.odds.budget import CreditBudget
from backend.scheduler import DEFAULT_PASS_DEADLINE_S, DEFAULT_WAKE_POLL_S, JITTER
from backend.store import db

REPO = Path(__file__).resolve().parents[1]
LIB_TS = REPO / "frontend" / "src" / "lib" / "nextOddsWindow.ts"
WATCHER = REPO / "frontend" / "src" / "components" / "RefreshWhenPriced.tsx"
NAV = REPO / "frontend" / "src" / "components" / "Nav.tsx"
API_TS = REPO / "frontend" / "src" / "lib" / "api.ts"
ENTRYPOINT = REPO / "docker" / "entrypoint.sh"
ENV_EXAMPLE = REPO / ".env.example"

NODE = shutil.which("node")
requires_node = pytest.mark.skipif(NODE is None, reason="node is not on PATH")

MIN = 60_000
HOUR = 3_600_000
NOW = 10_000_000
IDLE_MS = ENTRYPOINT_RUNNER_INTERVAL_S * 1000
#: `RefreshWhenPriced.GIVE_UP_MS`, as the remaining watch at mount.
WATCH_MS = 300_000

_DRIVER = """
import { readWatch } from "./nextOddsWindow.ts";
const args = JSON.parse(process.argv[2]);
console.log(JSON.stringify(readWatch(args.facts, args.ctx)));
"""


def _code(path: Path) -> str:
    """Source with every comment stripped, so an "absent" pin is not satisfied
    by the comment that explains the absence."""
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"//[^\n]*", "", source)


def _ts_const(path: Path, name: str) -> float:
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"^(?:export )?const {name} = ([^;]+);", source, re.M)
    assert match, f"{name} is no longer a module constant in {path.name}"
    expr = match.group(1)
    # The derived constants are written as products of named ones; resolve
    # the names first, then drop the digit-group underscores of the literals.
    for other in sorted(set(re.findall(r"[A-Z][A-Z_]+", expr)), key=len, reverse=True):
        expr = expr.replace(other, str(_ts_const(path, other)))
    expr = re.sub(r"(?<=\d)_(?=\d)", "", expr)
    return float(eval(expr))  # noqa: S307 -- arithmetic over pinned literals


def watch(facts: dict, *, visible_for_ms: int, watch_remaining_ms: int = WATCH_MS):
    driver = LIB_TS.parent / "_watch_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    payload = {
        "facts": facts,
        "ctx": {
            "visible_for_ms": visible_for_ms,
            "watch_remaining_ms": watch_remaining_ms,
        },
    }
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(payload)],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
            cwd=str(LIB_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


def facts(
    *,
    next_sweep_ms=None,
    last_look_ms=NOW - 15 * MIN,
    attended=False,
    slice_spent=False,
    floor_next_buy_ms=None,
    sweeps_remaining_today=100,
    loop_idle_interval_ms=IDLE_MS,
):
    """The idle desk as `/api/window` describes it on a cold open: the last
    look one sleep ago, nobody attended, the cadence published."""
    return {
        "now_ms": NOW,
        "next_sweep_ms": next_sweep_ms,
        "sweeps_remaining_today": sweeps_remaining_today,
        "last_look_ms": last_look_ms,
        "attention_slice_spent": slice_spent,
        "floor_next_buy_ms": floor_next_buy_ms,
        "loop_idle_interval_ms": loop_idle_interval_ms,
        "desk_is_attended": attended,
    }


@requires_node
class TestTheColdOpenIsNotAStall:
    """The exhibit: 2026-09-02T13:28Z, 13s visit, buy at +0.6s, 0 -> 150 fresh
    fixtures, screen said it would not change."""

    def test_an_idle_loop_is_watched_not_declared_dead(self):
        """Last look fifteen minutes ago, page open two seconds, a due buy.
        The old gate returned `loop_stalled` here and set no timer. Mutation
        observed red: judge the silence against a 180s constant again."""
        verdict = watch(facts(next_sweep_ms=NOW, attended=True), visible_for_ms=2_000)
        assert verdict["kind"] == "watch"

    def test_the_idle_floors_nothing_is_not_final_before_the_heartbeat_lands(self):
        """`desk_wants`' attended branch has no twelve-hour horizon, so a
        fixture 13h out is "nothing to schedule" to the idle desk and "due
        now" to the attended one. Facts read before this page's heartbeat
        committed say the first; taking that as final is the server-render
        defect with fresher facts. Mutation observed red: drop the settle
        rule and this returns `nothing_due`."""
        verdict = watch(facts(attended=False), visible_for_ms=2_000)
        assert verdict == {"kind": "watch", "because": "facts_predate_heartbeat"}

    def test_the_same_reading_is_final_once_the_page_has_been_asking(self):
        """Past the settle window with the facts still saying nobody is
        looking, the heartbeat has had its chance; the reading stands."""
        verdict = watch(facts(attended=False), visible_for_ms=20_000)
        assert verdict["kind"] == "nothing_due"
        assert verdict["next_buy_ms"] is None
        assert "not watching" in verdict["sentence"]

    def test_the_same_reading_is_final_at_once_when_the_facts_include_the_page(self):
        """`desk_is_attended` true means the attended cadence has been asked
        and still wants nothing: no stored fixture at all. Final immediately."""
        verdict = watch(facts(attended=True), visible_for_ms=2_000)
        assert verdict["kind"] == "nothing_due"

    def test_a_scheduled_buy_beyond_the_watch_is_deferred_before_the_heartbeat(self):
        """The floor's `+50 min` answer may become the attended cadence's `now`
        once the stamp lands. Deferred, not taken."""
        far = NOW + 50 * MIN
        early = watch(facts(next_sweep_ms=far, attended=False), visible_for_ms=2_000)
        settled = watch(facts(next_sweep_ms=far, attended=True), visible_for_ms=2_000)
        assert early["kind"] == "watch"
        assert settled["kind"] == "nothing_due"
        assert settled["next_buy_ms"] == far


@requires_node
class TestABuyInsideTheWatchIsWatchedWhateverScheduledIt:
    def test_a_due_buy_is_watched(self):
        assert watch(facts(next_sweep_ms=NOW, attended=True), visible_for_ms=2_000)["kind"] == "watch"

    def test_a_scheduled_buy_inside_the_watch_is_watched(self):
        verdict = watch(facts(next_sweep_ms=NOW + 2 * MIN, attended=True), visible_for_ms=2_000)
        assert verdict == {"kind": "watch", "because": "buy_inside_window"}

    def test_a_scheduled_buy_after_the_watch_would_end_is_not(self):
        """A buy at +50 minutes is real and is not a reason to poll for five.
        Mutation observed red: watch on any future time."""
        verdict = watch(facts(next_sweep_ms=NOW + 50 * MIN, attended=True), visible_for_ms=2_000)
        assert verdict["kind"] == "nothing_due"

    def test_a_floor_buy_inside_the_watch_is_watched_past_the_slice(self):
        """Off-switch (a) of the ticket. The floor buys while the page is open
        (2026-08-29), so a spent slice with the floor due in two minutes is a
        buy this watcher will see land. The old gate read `slice_spent` as
        "nothing is coming" regardless. Mutation observed red: return
        `nothing_due` for every `slice_spent` reading."""
        verdict = watch(
            facts(slice_spent=True, floor_next_buy_ms=NOW + 2 * MIN, attended=True),
            visible_for_ms=2_000,
        )
        assert verdict == {"kind": "watch", "because": "buy_inside_window"}

    def test_a_floor_buy_after_the_watch_is_reported_with_its_time(self):
        verdict = watch(
            facts(slice_spent=True, floor_next_buy_ms=NOW + 40 * MIN, attended=True),
            visible_for_ms=2_000,
        )
        assert verdict["kind"] == "nothing_due"
        assert verdict["next_buy_ms"] == NOW + 40 * MIN
        assert "stop looking" not in verdict["sentence"]

    def test_a_spent_slice_is_not_deferred_for_the_heartbeat(self):
        """A heartbeat cannot un-spend the slice, so the pre-heartbeat rule
        does not apply here -- deferring would poll for a buy that cannot
        come on the attended cadence."""
        verdict = watch(facts(slice_spent=True, attended=False), visible_for_ms=2_000)
        assert verdict["kind"] == "nothing_due"

    def test_a_spent_day_is_final_at_once(self):
        verdict = watch(
            facts(sweeps_remaining_today=0, attended=False), visible_for_ms=2_000
        )
        assert verdict["kind"] == "nothing_due"
        assert "budget" in verdict["sentence"]

    def test_no_nothing_due_sentence_smuggles_a_clock_in(self):
        """`next_buy_ms` is for the caller to format through DISPLAY_TIME_ZONE;
        a digit pair in the sentence would be a second, unzoned clock."""
        for f in (
            facts(next_sweep_ms=NOW + 50 * MIN, attended=True),
            facts(slice_spent=True, floor_next_buy_ms=NOW + 40 * MIN),
            facts(sweeps_remaining_today=0),
            facts(attended=True),
        ):
            sentence = watch(f, visible_for_ms=2_000)["sentence"]
            assert not re.search(r"\d{1,2}:\d{2}", sentence), sentence


@requires_node
class TestTheFastClockSeesAStallTheSlowOneCannot:
    """A visible page heartbeats every minute; each heartbeat wakes the loop
    within ~5s; a woken pass writes a look. Silence spanning three minutes of
    continuous visibility is three wakes with no look."""

    def test_silence_across_three_visible_minutes_is_a_stall(self):
        """Mutation observed red: drop the visible-time clause and this fires
        on every idle cold open; drop the silence clause and it fires on a
        healthy loop that looked a minute ago."""
        verdict = watch(
            facts(next_sweep_ms=NOW, attended=True, last_look_ms=NOW - 200_000),
            visible_for_ms=200_000,
        )
        assert verdict["kind"] == "loop_stalled"
        assert "fault in the tool" in verdict["sentence"]

    def test_a_long_silence_on_a_page_just_opened_is_the_idle_loop(self):
        """The 8-of-26 case, stated on the fast clock: 900s of silence at
        visible 30s is a loop asleep, and the heartbeat is about to wake it."""
        verdict = watch(
            facts(next_sweep_ms=NOW, attended=True, last_look_ms=NOW - IDLE_MS),
            visible_for_ms=30_000,
        )
        assert verdict["kind"] == "watch"

    def test_a_loop_that_looked_since_the_page_opened_is_alive(self):
        verdict = watch(
            facts(next_sweep_ms=NOW, attended=True, last_look_ms=NOW - 100_000),
            visible_for_ms=200_000,
        )
        assert verdict["kind"] == "watch"

    def test_the_slow_clock_still_fires_on_a_loop_dead_since_before_the_open(self):
        """Two idle intervals of silence is a stall whoever is looking; the
        fast clock has not started counting at two seconds visible."""
        verdict = watch(
            facts(next_sweep_ms=NOW, attended=True, last_look_ms=NOW - 2 * HOUR),
            visible_for_ms=2_000,
        )
        assert verdict["kind"] == "loop_stalled"

    def test_a_never_looked_database_is_not_stalled_on_either_clock(self):
        verdict = watch(
            facts(next_sweep_ms=NOW, attended=True, last_look_ms=None),
            visible_for_ms=200_000,
        )
        assert verdict["kind"] == "watch"

    def test_the_stall_sentence_carries_no_clock_time(self):
        verdict = watch(
            facts(next_sweep_ms=NOW, attended=True, last_look_ms=NOW - 200_000),
            visible_for_ms=200_000,
        )
        assert not re.search(r"\d{1,2}:\d{2}", verdict["sentence"])


class TestTheConstantsAgreeAcrossTwoLanguages:
    def test_two_idle_intervals_is_at_least_one_whole_missed_pass(self):
        """The slow clock's derivation, as an inequality over the Python
        constants it cites: one sleep at worst-case jitter plus one pass at
        its deadline must fit inside the threshold, so silence past it means
        a pass was missed outright. Mutation observed red: set
        `LOOP_STALL_IDLE_INTERVALS = 1`."""
        intervals = _ts_const(LIB_TS, "LOOP_STALL_IDLE_INTERVALS")
        interval_s = ENTRYPOINT_RUNNER_INTERVAL_S
        worst_healthy_gap_s = interval_s * (1 + JITTER) + DEFAULT_PASS_DEADLINE_S
        assert intervals * interval_s >= worst_healthy_gap_s

    def test_the_fast_clock_is_three_heartbeats(self):
        """Not one: the first look after a heartbeat can land early and the
        next heartbeat is a minute away, and a long full pass can push a look
        ~107s past the heartbeat that woke it. Three is two missed wakes of
        slack over the worst healthy gap. Mutation observed red: set it to
        `HEARTBEAT_INTERVAL_MS`."""
        heartbeat = _ts_const(LIB_TS, "HEARTBEAT_INTERVAL_MS")
        stall = _ts_const(LIB_TS, "WATCHED_STALL_MS")
        assert stall == 3 * heartbeat
        assert stall > 107_000

    def test_the_settle_window_sits_between_the_polls_and_the_stall(self):
        settle = _ts_const(LIB_TS, "HEARTBEAT_SETTLE_MS")
        assert settle >= 2 * _ts_const(WATCHER, "LEADING_POLL_MS")
        assert settle < _ts_const(LIB_TS, "WATCHED_STALL_MS")

    def test_the_leading_edge_polls_at_least_as_often_as_the_loop_checks_for_us(self):
        """The loop notices a heartbeat within `DEFAULT_WAKE_POLL_S`; a poll
        slower than that would miss the buy on visits shorter than a tick."""
        assert _ts_const(WATCHER, "LEADING_POLL_MS") <= DEFAULT_WAKE_POLL_S * 1000
        assert _ts_const(WATCHER, "LEADING_EDGE_MS") >= 20_000

    def test_giving_up_still_matches_the_attention_ttl(self):
        assert _ts_const(WATCHER, "GIVE_UP_MS") == attention.DEFAULT_ATTENTION_TTL_MS

    def test_the_entrypoint_default_is_the_one_the_api_assumes(self):
        """`docker/entrypoint.sh` passes `${RUNNER_INTERVAL_S:-900}` to the
        loop; the API reads the same variable with the same default. One
        source, two readers -- pinned so the second spelling cannot drift.
        Mutation observed red: change either number."""
        entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
        match = re.search(r"--interval \"\$\{RUNNER_INTERVAL_S:-(\d+)\}\"", entrypoint)
        assert match, "the entrypoint no longer defaults RUNNER_INTERVAL_S inline"
        assert int(match.group(1)) == ENTRYPOINT_RUNNER_INTERVAL_S
        contract = re.search(r"^RUNNER_INTERVAL_S=(\d+)$", ENV_EXAMPLE.read_text(encoding="utf-8"), re.M)
        assert contract and int(contract.group(1)) == ENTRYPOINT_RUNNER_INTERVAL_S


class TestTheServerPublishesTheCadence:
    def test_unset_reads_as_the_entrypoints_default(self):
        assert loop_idle_interval_ms_from_env({}) == ENTRYPOINT_RUNNER_INTERVAL_S * 1000
        assert loop_idle_interval_ms_from_env({"RUNNER_INTERVAL_S": "  "}) == 900_000

    def test_a_set_value_is_read_in_seconds(self):
        assert loop_idle_interval_ms_from_env({"RUNNER_INTERVAL_S": "300"}) == 300_000

    def test_unreadable_resolves_to_none_never_zero(self):
        """A `0` would make every look a stall. Mutation observed red: return
        0 on ValueError."""
        for raw in ("abc", "0", "-5"):
            assert loop_idle_interval_ms_from_env({"RUNNER_INTERVAL_S": raw}) is None

    def test_window_status_carries_it_and_defaults_to_unknown(self, tmp_path):
        conn = db.init_db(tmp_path / "w.db")
        try:
            budget = CreditBudget(conn, daily_budget=700)
            common = dict(budget=budget, now_ms=NOW, max_odds_age_ms=900_000, sweep_cost=4)
            assert window_status(conn, **common).to_dict()["loop_idle_interval_ms"] is None
            published = window_status(conn, loop_idle_interval_ms=900_000, **common)
            assert published.to_dict()["loop_idle_interval_ms"] == 900_000
        finally:
            conn.close()

    def test_the_route_passes_the_environment_reading(self):
        source = (REPO / "backend" / "api" / "routes.py").read_text(encoding="utf-8")
        assert "loop_idle_interval_ms=loop_idle_interval_ms_from_env()" in source

    def test_the_wire_type_declares_it(self):
        assert "loop_idle_interval_ms: number | null;" in API_TS.read_text(encoding="utf-8")


class TestTheComponentIsWiredToTheNewPredicate:
    def test_the_first_poll_is_on_mount_and_there_is_no_interval(self):
        """Visits of 4, 5, 7 and 13 seconds could not reach a `setInterval`'s
        first ten-second tick though the data healed under them. Mutation
        observed red: remove `void look();` from the effect body."""
        code = re.sub(r"\s+", " ", _code(WATCHER))
        # The mount-time call specifically: `void look();` also runs from the
        # visibilitychange handler, and a pin on the bare string survived the
        # mount call's deletion (observed 2026-09-03, first mutation round).
        assert 'setPhase({ kind: "checking" }); void look();' in code
        assert "setInterval" not in code

    def test_the_deprecated_prop_is_declared_and_never_read(self):
        """`ParlayCards` still passes `automaticBuyIsComing`, so the type keeps
        it; nothing in the body may consult it, or the off-switch is back."""
        code = _code(WATCHER)
        assert code.count("automaticBuyIsComing") == 1
        assert "automaticBuyIsComing?: boolean" in code

    def test_every_terminal_state_has_words(self):
        flat = re.sub(r"\s+", " ", WATCHER.read_text(encoding="utf-8"))
        for phrase in (
            "Checking whether a new price is on its way",
            "Watching for the next price",
            "stopped watching for them",
            "did not answer while this page was watching",
            "Check again",
        ):
            assert phrase in flat, phrase

    def test_the_visible_clock_restarts_on_return_not_resumes(self):
        """A hidden tab sends no heartbeats, so a loop nobody woke is allowed
        to have slept; the stall clock must start over when the tab returns."""
        code = _code(WATCHER)
        assert "visibleSince = null" in code
        assert "visibleSince = Date.now()" in code


class TestTheNavChipPollIsGatedLikeTheHeartbeat:
    def test_the_chip_does_not_fetch_in_a_hidden_tab(self):
        """Item 5 of the ticket. The heartbeat at the bottom of `Nav.tsx` was
        gated on `visibilityState`; the chip poll above it was not, and ran
        once a minute for a chip nobody could see. Mutation observed red:
        remove the guard from `load`."""
        code = _code(NAV)
        load = code.split("const load = () => {", 1)[1].split("};", 1)[0]
        assert 'document.visibilityState !== "visible"' in load
        assert 'addEventListener("visibilitychange", load)' in code

    def test_both_intervals_are_the_one_heartbeat_constant(self):
        """`WATCHED_STALL_MS` is derived from the heartbeat interval, so the
        interval is imported into `Nav.tsx` rather than retyped there."""
        code = _code(NAV)
        assert "HEARTBEAT_INTERVAL_MS" in code
        assert "60_000" not in code
        assert code.count("setInterval(beat, HEARTBEAT_INTERVAL_MS)") == 1
        assert code.count("setInterval(load, HEARTBEAT_INTERVAL_MS)") == 1
