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
   * The day's credits remain but the **attention slice** is spent, so
   * nothing is bought automatically while this page is open.
   *
   * `floor_resumes_ms` is when the hourly floor would buy once nobody is
   * looking, or `null` when it wants nothing either. The caller formats it;
   * `sentence` is complete and clock-free without it, so a caller that
   * renders only the sentence is still telling the truth.
   */
  | {
      kind: "slice_spent";
      floor_resumes_ms: number | null;
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
      now_ms: facts.now_ms,
      // **Never "a tap is the only path".** ADR 0071 §2.1 — the desk does
      // not manufacture action. Both reviews on #35 rejected the ticket's own
      // "tap, 150 credits are sitting there": a fresh price for a game half a
      // day out is a fraction of a cent of EV on a one-contract stake, and the
      // floor buys it for nothing. The panel's job here is to **withdraw a
      // false reason to wait**, not to supply a reason to spend.
      sentence:
        floorResumes === null
          ? "Today's automatic buying is done — the desk buys by itself " +
            "until it reaches the day's allowance, and it has. Nothing " +
            "further is bought automatically while this page is open, and " +
            "no stored fixture is close enough for the slow hourly buy to " +
            "want one either."
          : "Today's automatic buying is done — the desk buys by itself " +
            "until it reaches the day's allowance, and it has. Nothing " +
            "further is bought automatically while this page is open; the " +
            "slow hourly buy resumes once you stop looking.",
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
 * Is the scheduler going to buy a price without being asked?
 *
 * **Exported rather than spelled at each call site**, because there are two of
 * them and the whole shape of ticket #35 was one predicate with two spellings
 * that drifted apart. `RefreshWhenPriced` gates its poll on this: watching for
 * a price nobody is going to buy produces a five-minute "no new prices
 * arrived" on a night when nothing was wrong.
 *
 * **`due_now` counts and `loop_stalled` does not**, which is the ordering
 * `readNextWindow` already establishes — a buy that is wanted while the
 * recording loop has stopped writing is not a buy that is coming. `unknown`
 * does not count either: a timetable that would not answer is not evidence a
 * sweep is on its way, and the caller's fallback is to say so rather than to
 * wait on it.
 */
export function anAutomaticBuyIsComing(
  facts: NextWindowFacts | null,
): boolean {
  const kind = readNextWindow(facts).kind;
  return kind === "due_now" || kind === "scheduled";
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
