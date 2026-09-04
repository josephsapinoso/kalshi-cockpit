/**
 * The sweep strip's tone decision, as one pure function.
 *
 * **Extracted so it can be executed by a test rather than read by one.** The
 * rest of this repo guards `.tsx` from Python by asserting on source text
 * (`tests/test_window_schedule.py`, `tests/test_demo_fidelity.py`), because
 * there is no JavaScript test runner here. That works for "does the component
 * read this field" and is worth nothing for "does this predicate reach the right
 * verdict" -- a substring assertion passes on a predicate that is exactly
 * inverted. This module is plain TypeScript with no React import so `node` can
 * run it directly (v24 strips types natively), which is what
 * `tests/test_sweep_tone_predicate.py` does with real recorded states.
 *
 * Its one import is `./nextOddsWindow`, which is itself dependency-free, so
 * the pair still runs under node. Node's type stripping does not resolve an
 * extensionless relative specifier, so the test registers a resolve hook that
 * appends `.ts`; the shipped source keeps the repo's import convention.
 *
 * The copy stays in the component. Only the verdict lives here.
 *
 * ## Why the verdict has four branches and not two
 *
 * The strip exists because a loop that *looks* and never *spends* ran 17 hours
 * unnoticed, and from the Board that state is indistinguishable from a quiet
 * market. The original predicate was:
 *
 *     swept since `budget_day_start_ms`  ->  calm, else warn
 *
 * which fires every morning by arithmetic. `budget_day_start_ms` is a
 * credits-accounting boundary (10:00Z); sweep windows are kickoff-derived,
 * opening 75 minutes before the first pitch of a cluster. Between the two there
 * is no window in which to spend. Measured on the live record, that gap held on
 * 6 of 6 budget days sampled (2026-08-12 .. 2026-08-17) for 6.5-10.8 hours each.
 *
 * So amber now needs a window to have existed. But the naive version of that --
 * "no window open yet, therefore calm" -- introduces a worse bug than it
 * removes, and `refused` is why. See `sweepTone` itself.
 *
 * ## Why the silence threshold is derived and not written here
 *
 * Until 2026-09-03 this file carried `LOOK_SILENT_MS = 2 * 900_000`: the same
 * two-idle-intervals rule `nextOddsWindow.ts` applies, reached independently,
 * with the loop's cadence hardcoded as a second spelling (ADR 0102 §5). The
 * cadence is a fact the server owns -- `RUNNER_INTERVAL_S` as the entrypoint
 * reads it, published on `/api/window` as `loop_idle_interval_ms` -- and a
 * threshold that names "normal" must be derived from that fact by the reader,
 * never asserted by it. So `loopIsSilent` below calls `loopStallAfterMs`, the
 * refresh panel's own derivation, and this file contains no number of seconds.
 */

import { loopStallAfterMs } from "./nextOddsWindow";

export type Tone = "calm" | "warn" | "alarm";

/**
 * Exactly the fields the verdict depends on — a deliberate subset of
 * `ActionableWindow`, so a test can state a whole world in seven values and so
 * this function cannot quietly start reading something else.
 */
export type SweepFacts = {
  now_ms: number;
  last_look_ms: number | null;
  last_look_outcome: string | null;
  last_sweep_ms: number | null;
  budget_day_start_ms: number;
  first_window_open_ms: number | null;
  /**
   * `window_status().loop_idle_interval_ms`: how long the loop sleeps between
   * full passes when nothing wakes it. Required here, unlike on
   * `NextWindowFacts`, so a fixture has to say what it believes about the
   * cadence rather than inherit a default; `null` is "the server could not
   * read it", and see `loopIsSilent` for what that resolves to.
   */
  loop_idle_interval_ms: number | null;
};

/**
 * Is the recording loop gone? `true` when `last_look_ms` is older than two of
 * the loop's own idle intervals, `false` when it is inside them, and `null`
 * when the cadence is not known and so no silence can be judged.
 *
 * **Shared by the verdict and the copy.** `WindowBanner` chooses its headline
 * with this and `sweepTone` chooses its tone with it, so the words and the
 * colour cannot disagree about whether the loop is alive: one predicate, one
 * spelling, evaluated on the same facts.
 *
 * `null` is not folded into either boolean. Folding it into `false` renders
 * a dead loop calm for as long as the cadence stays unreadable; folding it
 * into `true` calls every loop dead the moment `RUNNER_INTERVAL_S` is
 * misconfigured. ADR 0102's rule -- unreadable resolves to a refusal to
 * claim, not to 180 and not to 900 -- means the caller has to decide what a
 * refusal to claim looks like on its own surface. `sweepTone` says amber.
 */
export function loopIsSilent(
  w: Pick<SweepFacts, "now_ms" | "last_look_ms" | "loop_idle_interval_ms">,
): boolean | null {
  if (w.last_look_ms === null) return null;
  const stallAfterMs = loopStallAfterMs(w);
  if (stallAfterMs === null) return null;
  return w.now_ms - w.last_look_ms > stallAfterMs;
}

export function sweepTone(w: SweepFacts): Tone {
  // Never looked. Amber and not calm: an empty trace rendered as a dash is the
  // calm-looking version of the outage itself.
  if (w.last_look_ms === null) return "warn";

  const silent = loopIsSilent(w);

  // The loop is gone. Louder than anything below it.
  if (silent === true) return "alarm";

  // **The cadence is unknown, and that is amber -- never alarm, never calm.**
  // ADR 0102 forbids calling the loop stalled on a cadence the server could
  // not read, so `alarm` cannot fire here; that much is the panel's rule
  // applied to the strip. What the strip adds is that it may not fall through
  // to `calm` either. Every branch below this one is about *spending*, and a
  // loop that swept at 20:51 and died at 21:00 would satisfy "the day's sweeps
  // have run" until tomorrow -- the exact silence this strip exists to make
  // visible, with the only clause that could see it switched off. So the
  // liveness test being unavailable is itself the finding: the strip is blind
  // to the one question it is for, and blind is amber for the same reason
  // "never looked" is. The component names the cause (`RUNNER_INTERVAL_S`
  // unreadable) so the amber is a repair instruction rather than a mood.
  //
  // Not a silent failure, then, on either side: a dead loop under an unknown
  // cadence renders amber rather than calm, and a healthy loop under an
  // unknown cadence renders amber rather than red -- and in both cases the
  // headline says which fact is missing. On live the entrypoint pins the
  // variable with a default, so this branch fires only when someone has set
  // it to something that does not parse.
  if (silent === null) return "warn";

  // The day's sweeps have run. A sweep from before the boundary was not paid
  // for out of today's allowance and does not count.
  if (w.last_sweep_ms !== null && w.last_sweep_ms >= w.budget_day_start_ms) {
    return "calm";
  }

  // **This must never be gated behind the window test**, which is a weaker
  // requirement than the order it appears in and is the one that actually
  // matters. `slots_for_sport` is unfiltered by budget -- it says so in its own
  // docstring -- so a day whose credits were exhausted at 14:00Z still computes
  // a first window at 20:50Z. Write the window test as an early
  // `if (no window yet) return "calm"` and that day renders calm over a recorder
  // that is dead until tomorrow: a false negative on the exact failure this
  // strip exists to catch, traded for the false positive being removed. Strictly
  // worse. A liveness guard may be noisy; it may not be silent.
  //
  // Swapping these two lines is harmless, because both return "warn" and the
  // question is a disjunction. That was asserted here as a load-bearing ordering
  // until a mutation test refused to go red and proved it was not.
  // `tests/test_sweep_tone_predicate.py` mutates to the early-return shape
  // instead, which is the form that really does break.
  //
  // `failed` joins it in v21 (2026-08-25) and the omission would have been the
  // same class of bug this branch exists for. Before v21 an upstream 401 wrote
  // an `api_credits` row that counted as a served sweep, so the `last_sweep_ms`
  // test three lines up returned **calm** through an outage. Fixing that in the
  // backend moves the failure here rather than removing it: a `failed` look now
  // leaves `last_sweep_ms` unmoved, falls past `refused`, and — if no window has
  // opened yet — reaches the final `return "calm"`. The recorder would be dead
  // and the strip would be quiet, which is the 17-hour shape with a new cause.
  //
  // `warn` and not `alarm`: `alarm` means the loop itself is gone, and here the
  // loop is alive and being refused by someone else. Same tier as `refused`,
  // for the same reason — we asked and got no odds.
  if (w.last_look_outcome === "refused" || w.last_look_outcome === "failed") {
    return "warn";
  }

  // Nothing swept, and there was a window in which it could have been. This is
  // the 17-hour shape.
  if (w.first_window_open_ms !== null && w.now_ms >= w.first_window_open_ms) {
    return "warn";
  }

  // Nothing swept, and no window has opened yet -- or none opens today at all.
  // There is no moment today at which this is news. The component still renders
  // the strip and names when the first window opens; it just does not shout.
  return "calm";
}
