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
 */

export type Tone = "calm" | "warn" | "alarm";

/** Two full passes with nothing recorded. The loop is not running. */
export const LOOK_SILENT_MS = 2 * 900_000;

/**
 * Exactly the fields the verdict depends on — a deliberate subset of
 * `ActionableWindow`, so a test can state a whole world in six numbers and so
 * this function cannot quietly start reading something else.
 */
export type SweepFacts = {
  now_ms: number;
  last_look_ms: number | null;
  last_look_outcome: string | null;
  last_sweep_ms: number | null;
  budget_day_start_ms: number;
  first_window_open_ms: number | null;
};

export function sweepTone(w: SweepFacts): Tone {
  // Never looked. Amber and not calm: an empty trace rendered as a dash is the
  // calm-looking version of the outage itself.
  if (w.last_look_ms === null) return "warn";

  // The loop is gone. Louder than anything below it.
  if (w.now_ms - w.last_look_ms > LOOK_SILENT_MS) return "alarm";

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
