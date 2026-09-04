/**
 * The exit beside the stale count: when does the next scheduled odds window
 * open, and is this row's refusal actually a staleness refusal?
 *
 * **Why this exists.** The slate's refusal disclosure renders `stale_odds × N`
 * and, until 2026-08-22, nothing else — which reads as "N bad bets" with
 * nothing to do about it. What it actually means is N *unpriced* rows: the
 * sportsbook side of the comparison is past `MAX_ODDS_AGE_S`, i.e. the screen
 * is being read outside an odds window (backend/odds/timing.py plans those
 * windows against kickoff clusters; ADR 0030 holds them open). Staleness is a
 * validity check, never a weighted factor — the fix is an exit (a time, and a
 * tap), not a softer gate.
 *
 * **The facts come from `/api/window`, never re-planned here.** `next_sweep_ms`
 * is `window_status`'s `next_call_ms`. A next-window time derived any other way
 * would eventually disagree with the scheduler, and the screen is the side that
 * gets believed.
 *
 * **That field used to carry a guarantee it could not keep, and the retraction
 * is why this module has a `slice_spent` branch.** The claim was that the page
 * could not disagree with the loop, because both went through `firing_for_slot`.
 * True of the slot schedule, false of the budget: the attention slice is checked
 * *after* the desk predicate has said a call is wanted, so the field answered
 * "is a call wanted?" while the screen rendered "is a call coming?". They agree
 * on every night the slice has credits and diverge on the nights it does not,
 * and on 2026-08-28 at 04:38Z the panel promised a sweep in the same minute the
 * loop logged its refusal of that exact sweep. The server now applies the slice
 * too, so a *time* in the field is servable — but `null` became ambiguous in
 * the process, and reading it without `attention_slice_spent` beside it is what
 * produces the next wrong sentence. Ticket #35.
 *
 * **Every branch is honest or it is words.** No scheduled window → a sentence
 * saying which of the two reasons holds (budget spent vs nothing to plan
 * against), never a fake time. Timetable unreadable → a refusal in words,
 * never 0, never a blank (the repo's unreadable-resolves-to-None rule).
 *
 * **A wanted buy is not a promised buy, and that distinction was bought with an
 * incident.** `due_now` used to say the runner's next pass serves it "usually
 * within a minute". On 2026-08-25 the recording loop wedged for 15.5 minutes
 * (passes every ~18s up to 16:49:33Z, then nothing until 17:05:07Z, confirmed
 * off `recorder.last_write_ms` rather than the log). `next_sweep_ms <= now_ms`
 * was true for that whole stretch and no pass came, so the screen promised a
 * price every time it was read and was wrong every time. `last_look_ms` is the
 * fact that separates the two -- `/api/window` has published it since
 * `odds_sweep_log` existed, and `ActionableWindow`'s own comment names the
 * three-state table (fresh look + stale sweep = declining; stale look = not
 * running at all). So the stall is read BEFORE `due_now`, and the sentence says
 * the recorder has stopped instead of naming a minute.
 *
 * **"Is the loop alive" and "is a buy coming because this page is open" are
 * two questions, and for a week this module answered both with one number.**
 * The stall threshold was a hardcoded 180s, written when the observed cadence
 * was a pass every ~18s. That is the FAST cadence, which runs only while a
 * window is open; idle, the loop sleeps `RUNNER_INTERVAL_S` (median 926.8s
 * full-to-full across 6,066 live passes). So on a cold open after a quiet
 * hour `last_look_ms` was routinely 180s+ old, this module called the loop
 * stalled, the snapshot predicate the pages computed from that reading came
 * back false, and `RefreshWhenPriced` switched itself off with *"It will not
 * change by itself until you reload it"* -- while the page's own heartbeat
 * woke the loop within five seconds and the buy landed a median ~3s after
 * that. Measured on live 2026-09-03: of 26 visits, 8 opened with the last
 * look over 180s old, all 8 had nothing fresh at open, and 0 of the 11 opens
 * that DID have fresh fixtures were called stalled -- 53% of the cold opens
 * lost the watcher, and the watcher exists for cold opens. The exhibit is
 * 2026-09-02T13:28Z: a 13s visit, buy at +0.6s, 0 -> 150 fresh fixtures,
 * screen said it would not change.
 *
 * The root cause was in that predicate's inputs, not its logic: it was
 * computed on the SERVER RENDER, from a snapshot taken before the page's
 * heartbeat existed -- asking whether a buy is scheduled using facts that
 * predate the thing that schedules the buy. So, since 2026-09-03:
 *
 * - `readNextWindow`'s stall branch judges a silence against the loop's OWN
 *   idle cadence, which `/api/window` now publishes as
 *   `loop_idle_interval_ms`. A quiet idle loop is never a fault. See
 *   `LOOP_STALL_IDLE_INTERVALS` for what "stalled" means on that clock, and
 *   for what it cannot see.
 * - `readWatch` is the watcher's own predicate, evaluated CLIENT-SIDE on
 *   fresh facts at every poll. It has a second, much tighter stall test that
 *   the server render cannot have: a page that is visible is heartbeating,
 *   a heartbeat wakes the loop within `DEFAULT_WAKE_POLL_S`, and a woken
 *   pass writes a look -- so silence spanning `WATCHED_STALL_MS` of
 *   continuous visibility is a real stall, on a clock the 2026-08-25 wedge
 *   would have tripped at three minutes.
 *
 * **The snapshot predicate itself was deleted on 2026-09-04**, and the reason
 * is worth more than the function was. ADR 0102 Amendment 1 left it exported
 * with a docstring saying it was test-only, because the class that pinned it
 * lived in another lane's file. That made its only reader a test asserting it
 * still existed -- decoration by this repo's own testing rule (disable the
 * guard and watch the test fail; a green run proved only that the export was
 * still there), and `tests/test_has_callers.py`'s stated end state for an
 * exported symbol whose every caller is a test. The name is now pinned absent
 * from `frontend/src` and `tests/` by
 * `tests/test_watcher_decides_from_fresh_facts.py`, so it cannot come back as
 * a second spelling of a question `readWatch` already answers -- one
 * predicate with two spellings being the whole shape of ticket #35.
 *
 * Pure and dependency-free so `tests/test_stale_exit.py` can execute it with
 * node the way `test_refresh_urgency.py` executes the urgency read — a
 * substring assertion cannot tell a branch from its inversion.
 *
 * WHAT THIS DOES NOT ESTABLISH: that the window, when it opens, contains
 * anything bettable. It re-prices the comparison; it does not change what the
 * comparison has ever said (`actionable` has effectively been 0 for the life
 * of the record).
 */

/**
 * How many of the loop's own idle intervals `odds_sweep_log` may go unwritten
 * before the loop is called stopped, on the slow clock.
 *
 * Two, and the two is arithmetic rather than taste. `run_forever` sleeps
 * `interval * (1 + JITTER)` at worst (JITTER is 0.15 in `scheduler.py`) and
 * then runs a pass bounded by `DEFAULT_PASS_DEADLINE_S` (600s); the look row
 * is written inside the pass. So the longest a healthy idle loop can go
 * between looks is `1.15 * I + 600s`, which at the deployed I = 900s is 1635s
 * -- inside two intervals (1800s). Silence past two intervals therefore means
 * at least one whole pass was missed outright, under the worst case the loop
 * permits itself. `tests/test_watcher_decides_from_fresh_facts.py` pins that
 * inequality against the Python constants rather than trusting this comment.
 *
 * **What this clock cannot see, stated so nobody trusts it for more.** A loop
 * that wedges mid-window looks, from `last_look_ms` alone, exactly like a
 * loop asleep between passes until two idle intervals have passed. The
 * 2026-08-25 wedge (15.5 min) is below that. The tighter clock is
 * `readWatch`'s: a page that is visible is waking the loop, so silence while
 * visible is a stall on a three-minute clock. This constant serves the slow
 * clock, which is the only one a server render has.
 *
 * **This bounds a sentence, never a spend.** Nothing downstream refuses, retries
 * or buys on it; the only consequence of being wrong is which words render.
 */
export const LOOP_STALL_IDLE_INTERVALS = 2;

/**
 * How often `Nav.tsx` stamps `desk_attention` while a page is visible. One
 * spelling, imported there, because `WATCHED_STALL_MS` below is derived from
 * it and a derivation from a number written twice is a derivation from
 * whichever copy drifted last.
 */
export const HEARTBEAT_INTERVAL_MS = 60_000;

/**
 * How long a VISIBLE page may go without the loop looking before the watcher
 * calls the loop stalled -- the fast clock.
 *
 * A visible page heartbeats every `HEARTBEAT_INTERVAL_MS`; `ArrivalWatch`
 * consumes each heartbeat as one wake, `sleep_until` notices within
 * `DEFAULT_WAKE_POLL_S` (5s), and the woken pass writes a look row after
 * discovery (~3-15s). So while a page is visible the loop looks at least
 * once per heartbeat interval plus wake plus discovery -- ~80s -- and up to
 * ~107s if the heartbeat lands mid-way through a long full pass (measured
 * 50-87s on 2026-08-19). Three heartbeat intervals is three consecutive wakes
 * with no look, with ~70s of slack over the worst healthy gap. Sixty seconds
 * -- the obvious number -- would call a healthy loop stalled whenever the
 * page's first look happened to land early and the next heartbeat had not
 * yet fired, which is most of the time.
 *
 * **Both clocks are durations, deliberately.** `visible_for_ms` is the
 * browser's, `now_ms - last_look_ms` is the server's, and comparing a
 * browser timestamp to a server one would put clock skew into the verdict.
 * "Silent for at least as long as we have been visibly asking, and we have
 * been asking for three intervals" needs no shared epoch.
 */
export const WATCHED_STALL_MS = 3 * HEARTBEAT_INTERVAL_MS;

/**
 * How long after a page becomes visible its `/api/window` reads may still
 * describe the desk WITHOUT this page in it.
 *
 * The heartbeat is a POST from `Nav.tsx` on mount; the watcher's first poll
 * is a GET at the same instant, and the two race. Until the stamp commits,
 * `desk_is_attended` is false and `next_sweep_ms` is the idle floor's answer
 * -- which for a fixture 13 hours out is *nothing*, while the page's own
 * presence will have it bought on the ten-minute cadence within seconds.
 * That is the server-render defect this module was rebuilt around, and a
 * client-side poll that took the first answer at face value would repeat it
 * with fresher facts. So a "nothing is coming" reading is not final while
 * the facts say nobody is looking and the page has only just started to.
 * Fifteen seconds is three leading-edge polls -- well past a POST's latency
 * and short enough that a heartbeat which never lands is reported inside the
 * visit rather than after it.
 */
export const HEARTBEAT_SETTLE_MS = 15_000;

/** The `/api/window` fields the reading needs; structurally satisfied by
 *  `ActionableWindow`. `null` for the whole object means the timetable
 *  fetch failed — a different state from "no window is scheduled". */
export type NextWindowFacts = {
  now_ms: number;
  /** `window_status().next_call_ms`: when the next `/odds` call is wanted. */
  next_sweep_ms: number | null;
  /** Whole team-sweeps the day's remaining credits still afford. */
  sweeps_remaining_today: number;
  /**
   * `window_status().last_look_ms`: when a pass last decided anything about
   * odds, served or declined.
   *
   * **Optional, and `null` is not `0`.** A caller that has not been updated
   * omits it and gets exactly the readings it got before; a database that has
   * never recorded a pass publishes `null`, which is "unknown", not "stopped".
   * Unreadable resolves to a refusal to claim, never to a stall
   * (`tasks/lessons.md`).
   */
  last_look_ms?: number | null;
  /**
   * `window_status().attention_slice_spent`: the attention slice can no
   * longer fund one more sweep.
   *
   * **Optional for the same reason `last_look_ms` is** — a caller that has
   * not been updated omits it and gets exactly the reading it got before.
   * `undefined` is "this caller does not know", never "the slice has
   * credits", so the branch below cannot fire on an absent field.
   */
  attention_slice_spent?: boolean;
  /**
   * `window_status().floor_next_buy_ms`: when the hourly floor next wants a
   * buy, computed as though nobody were looking.
   *
   * A **lookahead**, not a snapshot: a sport enters the floor's twelve-hour
   * horizon at `kickoff - 12h`, so at 04:38Z against an 18:20Z kickoff this
   * is ~06:20Z while the desk wants nothing at all. `null` means no stored
   * fixture ever brings the floor round, which is a third state again.
   */
  floor_next_buy_ms?: number | null;
  /**
   * `window_status().attention_slice_spent_at_ms`: when today's allowance ran
   * out. Optional and `null`-tolerant for the same reason as the fields
   * above — a caller that omits it gets a sentence with no time in it, which
   * is complete on its own.
   */
  attention_slice_spent_at_ms?: number | null;
  /**
   * `window_status().loop_idle_interval_ms`: how long the loop sleeps between
   * full passes when nothing wakes it (`RUNNER_INTERVAL_S`, 900s on live).
   *
   * **The stall branch reads this or does not fire.** A silence can only be
   * judged against the cadence that produced it; a caller that omits the
   * field, or a server that could not read the interval, gets no stall
   * sentence rather than one computed against a guessed number. Unknown is
   * not `0` and it is not 900 either.
   */
  loop_idle_interval_ms?: number | null;
  /**
   * `window_status().desk_is_attended`: whether a heartbeat has landed inside
   * the TTL. Read by `readWatch` to tell facts that predate this page's own
   * heartbeat from facts that include it -- the difference between "the idle
   * desk wants nothing" and "the desk you are looking at wants nothing".
   * Optional so every caller written before it existed reads as it did.
   */
  desk_is_attended?: boolean;
};

export type NextWindowReading =
  /** The timetable could not be read. Words, never a guessed time. */
  | { kind: "unknown"; sentence: string }
  /** A buy is wanted right now — the runner's next pass serves it. */
  | { kind: "due_now"; sentence: string }
  /** A buy is wanted and nothing is running to serve it. Words, never a
   *  minute: the pass that would deliver it has stopped writing. */
  | { kind: "loop_stalled"; sentence: string }
  /** A real future time. The caller formats it (DISPLAY_TIME_ZONE); this
   *  module holds no clock rendering so node can run it bare. */
  | { kind: "scheduled"; open_ms: number; now_ms: number }
  /** No window remains because the day's odds budget is spent. */
  | { kind: "budget_spent"; sentence: string }
  /**
   * The day's credits remain but the **attention slice** is spent, so the
   * ten-minute refresh that runs while this page is open has stopped and the
   * slow hourly floor is what re-prices the slate from here.
   *
   * **The reading survived a change of meaning on 2026-08-29 and the field
   * name did not keep up.** Until then a spent slice meant nothing was bought
   * at all while anyone was looking -- attention *replaced* the floor, so
   * keeping the page open was what suppressed the buying. The loop now falls
   * through to the floor's own cadence instead of skipping the sport, so this
   * state is "slower", not "off", and `floor_resumes_ms` is a lookahead to the
   * floor's next buy rather than a promise contingent on going away. The name
   * is kept because it is the field it reads (`floor_next_buy_ms`); the copy
   * is what had to change.
   *
   * `floor_resumes_ms` is `null` when the floor wants nothing either. The
   * caller formats it; `sentence` is complete and clock-free without it, so a
   * caller that renders only the sentence is still telling the truth.
   */
  | {
      kind: "slice_spent";
      floor_resumes_ms: number | null;
      /** When the allowance ran out. The caller formats it; `sentence` never
       *  contains it, so a caller that ignores it still reads correctly. */
      spent_at_ms: number | null;
      now_ms: number;
      sentence: string;
    }
  /** Credits remain but no upcoming kickoff is near enough to plan a
   *  pre-game sweep for. */
  | { kind: "nothing_to_schedule"; sentence: string };

export function readNextWindow(
  facts: NextWindowFacts | null,
): NextWindowReading {
  if (facts === null) {
    return {
      kind: "unknown",
      sentence:
        "When the next odds window opens could not be read — the sweep " +
        "timetable did not answer. That is a gap in the readout, not a " +
        "statement that no window is coming.",
    };
  }
  // Before `due_now`, not after, and the order is the whole point. Both
  // conditions were true together for fifteen minutes on 2026-08-25; whichever
  // is checked first is the sentence the reader gets, and only one of them was
  // true. A stalled loop does not serve a due buy.
  //
  // **Judged against the loop's own idle cadence, never a constant.** The
  // constant this replaces was 180s and the idle cadence is 900s, so for a
  // week every quiet quarter-hour read as a fault (see the module docstring
  // for the 8-of-26 measurement). With the cadence unknown there is no
  // judgement to make: `null`/`undefined` here means the caller cannot say
  // what "too long" is, and a sentence that says "fault" on a guess is the
  // defect in a new spelling.
  const stallAfterMs = loopStallAfterMs(facts);
  const lastLook = facts.last_look_ms;
  if (lastLook !== null && lastLook !== undefined && stallAfterMs !== null) {
    const silentMs = facts.now_ms - lastLook;
    if (silentMs > stallAfterMs) {
      return {
        kind: "loop_stalled",
        sentence:
          "The recording loop has not looked at odds for " +
          `${Math.floor(silentMs / 60_000)} minutes. Left alone it looks ` +
          `about every ${Math.round((facts.loop_idle_interval_ms as number) / 60_000)} ` +
          "minutes, so at least one whole pass has been missed and nothing " +
          "is going to re-buy these lines until it starts again — the prices " +
          "will keep ageing until then. This is a fault in the tool, not a " +
          "quiet night.",
      };
    }
  }
  if (facts.next_sweep_ms !== null) {
    if (facts.next_sweep_ms <= facts.now_ms) {
      return {
        kind: "due_now",
        sentence:
          "An odds buy is due right now — the runner's next pass serves it, " +
          "usually within a minute.",
      };
    }
    return {
      kind: "scheduled",
      open_ms: facts.next_sweep_ms,
      now_ms: facts.now_ms,
    };
  }
  if (facts.sweeps_remaining_today <= 0) {
    return {
      kind: "budget_spent",
      sentence:
        "No further odds window is scheduled — the day's odds budget is " +
        "spent, so nothing re-buys these lines before the budget day rolls " +
        "over.",
    };
  }
  // **Before `nothing_to_schedule`, and this ordering is the fix.** Half one
  // made `next_sweep_ms` budget-aware, so past the slice it is `null` — and a
  // null used to fall through `budget_spent` (whose test is whole-day-derived
  // and reads ~123 remaining on exactly the nights the slice is gone) into
  // "no upcoming kickoff is near enough", which is **false whenever a kickoff
  // is inside the twelve-hour horizon**. One lie replaced by another. Ticket
  // #35; flagged as a deploy-safety hazard by half one's own commit.
  //
  // **After `budget_spent`, deliberately.** If the whole day's 700 is gone the
  // floor cannot buy either, so that sentence is the stronger true one and
  // must win. The slice branch describes the narrower state: the day can still
  // afford sweeps, and only the attended-refresh allowance is exhausted.
  if (facts.attention_slice_spent === true) {
    const floorResumes = facts.floor_next_buy_ms ?? null;
    return {
      kind: "slice_spent",
      floor_resumes_ms: floorResumes,
      spent_at_ms: facts.attention_slice_spent_at_ms ?? null,
      now_ms: facts.now_ms,
      // **Never "a tap is the only path".** ADR 0071 §2.1 — the desk does
      // not manufacture action. Both reviews on #35 rejected the ticket's own
      // "tap, 150 credits are sitting there": a fresh price for a game half a
      // day out is a fraction of a cent of EV on a one-contract stake, and the
      // floor buys it for nothing. The panel's job here is to **withdraw a
      // false reason to wait**, not to supply a reason to spend.
      //
      // **"Once you stop looking" is gone, and that phrasing was the whole
      // reason to touch this branch.** It was true while attention replaced
      // the floor: past the slice, having the page open switched the buying
      // off, and closing it switched the floor back on five minutes later.
      // The loop now falls through to the floor while the page is open
      // (2026-08-29), so the sentence would be a reassurance that had outlived
      // its condition — worse than the bug, because a reader who acts on it
      // closes a screen they wanted open.
      sentence:
        floorResumes === null
          ? "Today's fast refreshing is done — the desk re-prices every few " +
            "minutes while you watch, until it reaches the day's allowance, " +
            "and it has. It keeps buying on the slow hourly floor from here, " +
            "but no stored fixture is close enough for that to want one yet."
          : "Today's fast refreshing is done — the desk re-prices every few " +
            "minutes while you watch, until it reaches the day's allowance, " +
            "and it has. The slow hourly buy carries the slate from here, " +
            "whether or not you are looking.",
    };
  }
  return {
    kind: "nothing_to_schedule",
    sentence:
      "No odds window is scheduled — no upcoming kickoff is near enough for " +
      "the planner to open a pre-game window for. A tap below is the only " +
      "path to a fresh read.",
  };
}

/**
 * The slow clock's threshold: how long `last_look_ms` may be silent before the
 * loop is called stopped, or `null` when the cadence is not known.
 *
 * `null` for a missing, `null`, or non-positive interval alike. A zero would
 * make every look a stall and a negative would make none; both are the shape
 * of "unreadable resolved to a number", which is the one thing this module's
 * conventions forbid.
 *
 * **The one spelling of the slow clock, and the parameter type is why.** It
 * takes only the field it reads so that `sweepTone.ts` -- the Board strip's
 * verdict, which has its own narrower facts type -- can call it rather than
 * carry `2 * 900_000` as a literal, which it did until 2026-09-03 (ADR 0102
 * §5, Amendment 1). Two derivations of "how long is too long" is how the
 * refresh panel and the sweep strip would come to disagree about whether the
 * same loop is alive.
 */
export function loopStallAfterMs(
  facts: Pick<NextWindowFacts, "loop_idle_interval_ms">,
): number | null {
  const interval = facts.loop_idle_interval_ms;
  if (interval === null || interval === undefined || interval <= 0) return null;
  return LOOP_STALL_IDLE_INTERVALS * interval;
}

/** What the watcher knows about its own situation that the facts do not. */
export type WatchContext = {
  /**
   * How long this page has been CONTINUOUSLY visible, in ms -- reset to zero
   * every time the tab is hidden, because a hidden tab sends no heartbeats
   * and a loop nobody is waking is allowed to sleep.
   */
  visible_for_ms: number;
  /**
   * How long the watcher will keep polling before it gives up, in ms. A buy
   * due after that is a buy the watcher will never see land, so it is not a
   * reason to watch.
   */
  watch_remaining_ms: number;
};

export type WatchVerdict =
  /** Keep polling. A buy is due inside the watch, or the facts are too young
   *  to say it is not. */
  | { kind: "watch"; because: "buy_inside_window" | "facts_predate_heartbeat" }
  /** The loop is not looking. Words, never a minute -- the pass that would
   *  deliver a price has stopped writing. */
  | { kind: "loop_stalled"; sentence: string }
  /**
   * Nothing is due inside the watch. `next_buy_ms` is the next automatic buy
   * if one is known (the caller formats it; the sentence is complete without
   * it), `null` when nothing is scheduled at all.
   */
  | {
      kind: "nothing_due";
      sentence: string;
      next_buy_ms: number | null;
      now_ms: number;
    };

/**
 * Should the page keep watching for a price, given FRESH facts and what the
 * watcher knows about itself?
 *
 * **Evaluated client-side, on every poll, and that is the whole repair.** The
 * predicate it replaces was evaluated once, on the server, from facts older
 * than the page's own heartbeat (see the module docstring). Two questions are
 * asked here in order, and they are different questions:
 *
 * 1. **Is the loop alive?** Two clocks. The fast one is this function's own:
 *    a visible page is waking the loop every `HEARTBEAT_INTERVAL_MS`, so a
 *    silence in `last_look_ms` that spans `WATCHED_STALL_MS` of continuous
 *    visibility is three wakes with no look -- a stall, on a clock the
 *    2026-08-25 wedge trips at three minutes. The slow one is
 *    `readNextWindow`'s, against the idle cadence, for a loop that has been
 *    dead since before the page opened. Either says stalled, this does.
 *
 * 2. **Is a buy coming inside the watch?** From `readNextWindow` over the
 *    same fresh facts, with the horizon `now + watch_remaining_ms`:
 *    - `due_now` -- yes.
 *    - `scheduled` -- yes if `open_ms` is inside the horizon. A buy at +50
 *      minutes is real and is not a reason to poll for five.
 *    - `slice_spent` -- yes if `floor_resumes_ms` is inside the horizon. The
 *      floor buys while the page is open (2026-08-29), so a floor buy due
 *      in two minutes is a buy this watcher will see land; "the slice is
 *      spent" used to switch the watcher off regardless, which was the
 *      off-switch ticket #35's own fix left in place.
 *    - `budget_spent` -- no. Nothing can buy.
 *    - `nothing_to_schedule` -- no, ONCE the facts include this page. See
 *      below.
 *
 * **The settle rule.** `desk_is_attended === false` with the page visible for
 * under `HEARTBEAT_SETTLE_MS` means the facts were read before this page's
 * heartbeat landed: `next_sweep_ms` is the idle floor's answer and the
 * attended cadence has not been asked. `desk_wants`' attended branch has no
 * twelve-hour horizon -- while a page is open every stored fixture is bought
 * on the ten-minute cadence -- so a fixture 13 hours out reads as "nothing
 * to schedule" idle and as "due now" attended. A "nothing is coming" verdict
 * from pre-heartbeat facts is therefore deferred, never taken; the next poll
 * has the heartbeat in it. `slice_spent` and `budget_spent` are not deferred,
 * because a heartbeat changes neither. A caller that omits `desk_is_attended`
 * gets no deferral, which is the reading it got before the field existed.
 *
 * The stall test is not deferred either, in the other direction: its clock
 * only starts counting at `WATCHED_STALL_MS` of visibility, which is long
 * past the settle window.
 */
export function readWatch(
  facts: NextWindowFacts,
  ctx: WatchContext,
): WatchVerdict {
  const lastLook = facts.last_look_ms;
  if (
    lastLook !== null &&
    lastLook !== undefined &&
    ctx.visible_for_ms >= WATCHED_STALL_MS &&
    facts.now_ms - lastLook >= WATCHED_STALL_MS
  ) {
    return {
      kind: "loop_stalled",
      sentence:
        "The recording loop has not looked at odds for " +
        `${Math.floor((facts.now_ms - lastLook) / 60_000)} minutes, and this ` +
        "page has been open and waking it for " +
        `${Math.floor(ctx.visible_for_ms / 60_000)} — it should have looked ` +
        "within seconds of that. Nothing is going to re-buy these lines " +
        "until it starts again. This is a fault in the tool, not a quiet " +
        "night.",
    };
  }
  const reading = readNextWindow(facts);
  if (reading.kind === "loop_stalled") {
    return { kind: "loop_stalled", sentence: reading.sentence };
  }
  const horizonMs = facts.now_ms + ctx.watch_remaining_ms;
  const factsPredateHeartbeat =
    facts.desk_is_attended === false && ctx.visible_for_ms < HEARTBEAT_SETTLE_MS;
  const notWatching =
    " This page is not watching for one and will not change by itself " +
    "until you reload it.";
  switch (reading.kind) {
    case "due_now":
      return { kind: "watch", because: "buy_inside_window" };
    case "scheduled":
      if (reading.open_ms <= horizonMs) {
        return { kind: "watch", because: "buy_inside_window" };
      }
      if (factsPredateHeartbeat) {
        return { kind: "watch", because: "facts_predate_heartbeat" };
      }
      return {
        kind: "nothing_due",
        next_buy_ms: reading.open_ms,
        now_ms: facts.now_ms,
        sentence:
          "No new price is due in the next few minutes — the next automatic " +
          "buy is later." +
          notWatching,
      };
    case "slice_spent":
      if (
        reading.floor_resumes_ms !== null &&
        reading.floor_resumes_ms <= horizonMs
      ) {
        return { kind: "watch", because: "buy_inside_window" };
      }
      return {
        kind: "nothing_due",
        next_buy_ms: reading.floor_resumes_ms,
        now_ms: facts.now_ms,
        sentence: reading.sentence + notWatching,
      };
    case "budget_spent":
      return {
        kind: "nothing_due",
        next_buy_ms: null,
        now_ms: facts.now_ms,
        sentence: reading.sentence + notWatching,
      };
    case "nothing_to_schedule":
      if (factsPredateHeartbeat) {
        return { kind: "watch", because: "facts_predate_heartbeat" };
      }
      return {
        kind: "nothing_due",
        next_buy_ms: null,
        now_ms: facts.now_ms,
        sentence:
          "No upcoming game is stored near enough for the desk to buy a " +
          "price for." +
          notWatching,
      };
    case "unknown":
      // Unreachable with non-null facts -- `readNextWindow` returns `unknown`
      // only for a null argument -- but the union says it can happen, and a
      // switch that lies to the type-checker is how a new reading slips past
      // this function unhandled. Not a verdict either way: keep asking.
      return { kind: "watch", because: "facts_predate_heartbeat" };
  }
}

/**
 * Whether a row's refusal includes the staleness check.
 *
 * `suppressed_reason` is a **comma-joined composite** of every check that
 * failed (`backend/analysis/joint_bound.py:280` is the note that keeps being
 * re-learned), so this splits on commas and compares whole codes. A substring
 * read is the trap being avoided: `.includes("stale")` would also match
 * `stale_kalshi_quote`, which is the *Kalshi* clock — a refusal no odds
 * refresh can fix, and offering one for it would be a button that lies.
 */
export function isStaleOddsReason(
  reason: string | null | undefined,
): boolean {
  if (!reason) return false;
  return reason.split(",").some((code) => code.trim() === "stale_odds");
}

/** The two fields the cold-screen read needs off a slate row. */
export type ColdScreenRow = {
  odds_age_now_ms?: number | null;
  suppressed_reason: string | null;
};

/**
 * Is this screen unusable *because of the clock*, rather than merely carrying
 * some stale rows?
 *
 * **A different question from `refreshIsUrgent`, and the difference is `some`
 * versus `every`.** That one decides whether the refresh panel deserves the
 * top of the page, and one stale row is enough to justify offering the fix.
 * This one gates `RefreshWhenPriced`, which re-renders the page under whoever
 * is reading it — and a working slate with one stale row must never do that.
 * The reader is mid-sentence on a game; the correct behaviour is to leave them
 * alone.
 *
 * So: **nothing here is usable, and fresh prices could change that.** Every row
 * carries a refusal, and at least one of those refusals is the clock. That is
 * the slate's version of the parlay desk's conjunction (a card failed AND sides
 * were dropped for age) — the screen cost the reader its whole answer, and a
 * sweep is what would give it back.
 *
 * **An empty slate is not this state, and it falls out rather than being
 * guarded.** `every` over an empty array is vacuously true, so an explicit
 * `rows.length === 0` check reads like a guard and changes no answer -- the
 * `some` below returns false on its own. It was written, mutated, observed
 * green, and removed: this repo's rule is that a guard which survives its own
 * deletion is decoration. The behaviour is still the intended one and is
 * asserted, and the page already says why in its own words -- nothing recorded
 * is a real result and is not the same as every candidate being refused.
 *
 * Staleness is read from the refusal through `isStaleOddsReason` — whole code,
 * never a substring, because `stale_kalshi_quote` is the *Kalshi* clock and no
 * odds sweep can fix it. The age is accepted as evidence too, for a row past
 * the limit that the engine has not refused for it.
 *
 * **Here rather than beside `refreshIsUrgent`, which is the sibling it
 * contrasts with.** It needs `isStaleOddsReason`, and both modules state in
 * their own docstrings that they are dependency-free so node can execute
 * them bare. Importing across would quietly retract that from both; copying
 * the split-and-compare would be the second implementation the whole-code
 * rule exists to prevent. Living next to the function it needs costs
 * neither.
 */
export function slateIsUnpricedByTheClock(
  rows: ColdScreenRow[],
  maxOddsAgeMs: number,
): boolean {
  if (!rows.every((row) => row.suppressed_reason)) return false;
  return rows.some(
    (row) =>
      isStaleOddsReason(row.suppressed_reason) ||
      (typeof row.odds_age_now_ms === "number" &&
        row.odds_age_now_ms > maxOddsAgeMs),
  );
}
