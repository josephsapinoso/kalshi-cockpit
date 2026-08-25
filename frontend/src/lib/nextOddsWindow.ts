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
 * is `window_status`'s `next_call_ms`, computed through `firing_for_slot` — the
 * same predicate the loop spends credits with ("one predicate, two callers",
 * backend/odds/timing.py). A next-window time derived any other way would
 * eventually disagree with the scheduler, and the screen is the side that gets
 * believed.
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
 * How long `odds_sweep_log` may go unwritten before the loop is called stopped.
 *
 * Not the heartbeat's 30 minutes (`.github/workflows/heartbeat.yml`), and the
 * gap is deliberate: that threshold answers "should this wake Joe", this one
 * answers "may this screen promise a price in the next minute". Every pass that
 * looks at odds writes a row whatever it decides, and the observed live cadence
 * is a quote pass every ~18s, so a gap of minutes is already far outside normal
 * operation. Three minutes is ten missed passes -- loose enough that a slow full
 * pass cannot trip it, tight enough that it fires well inside the 15 minutes the
 * desk sat blank on 2026-08-25.
 *
 * **This bounds a sentence, never a spend.** Nothing downstream refuses, retries
 * or buys on it; the only consequence of being wrong is which words render.
 */
export const LOOP_STALL_MS = 180_000;

/** The four `/api/window` fields the reading needs; structurally satisfied
 *  by `ActionableWindow`. `null` for the whole object means the timetable
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
  const lastLook = facts.last_look_ms;
  if (lastLook !== null && lastLook !== undefined) {
    const silentMs = facts.now_ms - lastLook;
    if (silentMs > LOOP_STALL_MS) {
      return {
        kind: "loop_stalled",
        sentence:
          "The recording loop has not looked at odds for " +
          `${Math.floor(silentMs / 60_000)} minutes. It normally looks every ` +
          "few seconds, so nothing is going to re-buy these lines until it " +
          "starts again — the prices will keep ageing until then. This is a " +
          "fault in the tool, not a quiet night.",
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
  return {
    kind: "nothing_to_schedule",
    sentence:
      "No odds window is scheduled — no upcoming kickoff is near enough for " +
      "the planner to open a pre-game window for. A tap below is the only " +
      "path to a fresh read.",
  };
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
