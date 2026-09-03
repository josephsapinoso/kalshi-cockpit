"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { fetchWindow, formatClock } from "@/lib/api";
import { readWatch } from "@/lib/nextOddsWindow";
import type { WatchVerdict } from "@/lib/nextOddsWindow";

/**
 * Re-render the page when prices land that could change what it says.
 *
 * **The gap this closes, and why it only became closable today.** Opening the
 * desk cold stamps `desk_attention`; since `scheduler.sleep_until` the loop
 * wakes on that within five seconds and sweeps a few seconds later, so fresh
 * prices arrive about ten to fifteen seconds after the page renders. The page
 * is a server component and knew none of it. Joe read a blank desk at 09:58 on
 * 2026-08-25 and the honest instruction was "wait, then reload" — which is a
 * thing to remember to do while looking at a screen that says nothing is on.
 *
 * `RefreshOddsButton` still offers a manual reload after a tap, and its comment
 * says a poll would be "pretending" because there was nothing to subscribe to.
 * That was true when a sweep could be fifteen minutes away and the page had no
 * way to tell a coming one from none. It is not true now: `/api/window`
 * publishes `fixtures_fresh`, the loop wakes in seconds, and this watches a
 * number rather than guessing at a clock.
 *
 * **The trigger is `fixtures_fresh` rising above what the server rendered
 * with, and nothing else.** Not "a sweep happened" — a sweep that refreshed
 * fixtures which were already fresh changes no answer on this page, and
 * re-rendering for it would be a flicker with nothing behind it. Not a timer:
 * a page that reloads on a schedule is a page that reloads while you are
 * reading it. The count going up is exactly "there is now more to say than
 * when this was drawn".
 *
 * **It decides for itself, from fresh facts, on every poll — and until
 * 2026-09-03 it did not.** The pages computed `anAutomaticBuyIsComing` on the
 * SERVER RENDER and passed it in, and this component returned before setting
 * a timer when it was false. The server render happens before this page's
 * heartbeat exists, so that answer described the idle desk: on a cold open
 * after a quiet hour `last_look_ms` was over the old 180s stall constant (the
 * idle cadence is 900s), the snapshot said "stalled", and the watcher switched
 * itself off with *"It will not change by itself until you reload it"* — 0.6s
 * before the buy its own heartbeat had triggered landed, on the 13-second
 * visit of 2026-09-02T13:28Z. Live, 8 of 26 visits opened that way and all 8
 * were cold; not one open with fresh fixtures was called stalled. The
 * off-switch fired on exactly the opens the watcher exists for.
 *
 * So the only thing the server render hands in now is the baseline count.
 * Whether a buy is coming, and whether the loop is alive, are `readWatch`'s
 * answers over the facts each poll returns — facts that, after the first few
 * seconds, include this page's own heartbeat. `nextOddsWindow.ts` carries the
 * reasoning; this file carries the timers.
 *
 * **It polls on a leading edge.** Immediately on mount, then every
 * `LEADING_POLL_MS` for the first `LEADING_EDGE_MS`, then `POLL_MS`. The buy a
 * cold open triggers lands a median ~3s after the loop wakes, and observed
 * visits of 4, 5, 7 and 13 seconds could not reach a `setInterval`'s first
 * 10-second tick though the data had healed under them. The first poll fires
 * before any timer exists.
 *
 * **It stops, and says which way.** Five minutes, matching
 * `DEFAULT_ATTENTION_TTL_MS`: a poller that ran until the tab closed would be
 * a background request loop nobody asked for. If it was watching a due buy
 * that never landed it says so — that is a real disappointment, not a
 * manufactured one, because the watch only continues while `readWatch` says
 * a buy is inside it. If the timetable never answered it says THAT, rather
 * than "no new prices arrived", which would blame the recorder for the API
 * being down. And when `readWatch` says nothing is due, or that the loop is
 * stalled, it stops early and renders the verdict's own sentence, with a
 * button that restarts the watch. A silent watcher and a broken one look
 * identical, so every terminal state has words.
 *
 * **Hidden tabs do not poll, and that is a correctness argument rather than a
 * courtesy.** `Nav.tsx` gates its heartbeat on `document.visibilityState`, so a
 * backgrounded tab is sending none — which means no sweep is coming for it, so
 * a poll could only ever confirm that. It resumes on `visibilitychange`, which
 * is also the moment the heartbeat resumes; the visible-time clock that
 * `readWatch`'s stall test reads restarts there too, because a loop nobody
 * was waking is allowed to have slept.
 *
 * WHAT THIS DOES NOT ESTABLISH
 * ----------------------------
 * - **That a refresh produces cards.** More fresh fixtures may still be fewer
 *   than a card's minimum. The page re-renders and says so again, with the new
 *   count; the watcher then starts over against that count.
 * - **That anything is bettable.** It re-prices a comparison. `actionable` has
 *   effectively been 0 for the life of this record.
 * - **That the heartbeat reached the server.** `readWatch`'s stall test
 *   assumes a visible page is waking the loop; if `recordAttention` is failing
 *   silently, three minutes of silence reads as a stall when it is an idle
 *   loop nobody woke. The give-up sentence had the same exposure before.
 */

/** The steady cadence, once the leading edge is over. Faster would mostly ask
 *  before the answer could have changed. */
const POLL_MS = 10_000;

/** The leading-edge cadence. The loop checks for a heartbeat every
 *  `DEFAULT_WAKE_POLL_S` (5s) and the buy lands ~3s after it wakes, so the
 *  first answer is usually inside the first ten seconds; asking every three
 *  catches it on the tick after it lands rather than up to ten seconds
 *  later, on visits that are often shorter than that. */
const LEADING_POLL_MS = 3_000;

/** How long the leading edge lasts. The cold-open buy has landed, or has
 *  failed to, well inside this; past it the steady cadence is enough. */
const LEADING_EDGE_MS = 30_000;

/** `attention.DEFAULT_ATTENTION_TTL_MS`. A bound on how long one page load may
 *  keep asking, not a claim about when the heartbeat stops. */
const GIVE_UP_MS = 300_000;

type Phase =
  /** First paint, before the first poll has answered. */
  | { kind: "checking" }
  /** `readWatch` said a buy is inside the watch, or is too early to rule out. */
  | { kind: "watching" }
  /** `readWatch` returned a terminal verdict; the watch stopped early. */
  | { kind: "verdict"; verdict: Exclude<WatchVerdict, { kind: "watch" }> }
  /** Five minutes of watching a due buy, and nothing landed. */
  | { kind: "gave_up" }
  /** Five minutes, and `/api/window` never once answered. */
  | { kind: "unreadable" };

export default function RefreshWhenPriced({
  renderedFresh,
}: {
  /** `ActionableWindow.fixtures_fresh` as the server saw it for this render. */
  renderedFresh: number;
  /**
   * @deprecated Not read. Until 2026-09-03 this was `anAutomaticBuyIsComing`
   * over the server render's snapshot and it gated the whole watch; the
   * snapshot predates the page's own heartbeat, so it switched the watcher
   * off on the cold opens it exists for (see the docstring). The watcher now
   * decides from fresh facts on every poll. The prop survives in the type so
   * `ParlayCards`, which still passes it, compiles until its own lane drops
   * it; `tests/test_watcher_decides_from_fresh_facts.py` pins that nothing in
   * this file reads it.
   */
  automaticBuyIsComing?: boolean;
}) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>({ kind: "checking" });
  // Bumped by "Check again", so the button restarts the watch as well as
  // re-rendering. Without it a refresh that changed nothing leaves the deps
  // identical, the effect does not re-run, and the button reads as a control
  // that half works.
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight = false;
    let answered = false;
    // The count this watch last refreshed the page for. `router.refresh()`
    // re-runs the server component, which hands back a new `renderedFresh`
    // and re-runs this effect against it; until that lands, a second poll
    // seeing the same higher count must not refresh again.
    let refreshedFor = renderedFresh;
    const startedAt = Date.now();
    // The visible-time clock `readWatch`'s stall test reads. `null` while
    // hidden; restarted, not resumed, on every return to visible.
    let visibleSince: number | null =
      document.visibilityState === "visible" ? startedAt : null;

    const schedule = () => {
      if (cancelled) return;
      clearTimeout(timer);
      const elapsed = Date.now() - startedAt;
      timer = setTimeout(
        look,
        elapsed < LEADING_EDGE_MS ? LEADING_POLL_MS : POLL_MS,
      );
    };

    const look = async () => {
      if (cancelled || inFlight) return;
      const now = Date.now();
      // Checked before the visibility gate, so a tab that spent the whole
      // budget in the background comes back to a terminal state rather than
      // to a watcher that quietly restarts its five minutes on every return.
      if (now - startedAt > GIVE_UP_MS) {
        setPhase({ kind: answered ? "gave_up" : "unreadable" });
        return;
      }
      if (document.visibilityState !== "visible") {
        visibleSince = null;
        // No timer while hidden: `onVisibility` restarts the watch.
        return;
      }
      if (visibleSince === null) visibleSince = now;
      inFlight = true;
      let facts;
      try {
        facts = await fetchWindow();
      } catch {
        // A timetable that will not answer is not "nothing landed" — it is a
        // question that could not be asked. Keep asking; the budget above
        // still bounds the whole thing, and `unreadable` is what it ends in
        // if no answer ever comes.
        inFlight = false;
        schedule();
        return;
      }
      inFlight = false;
      if (cancelled) return;
      answered = true;
      if (facts.fixtures_fresh > refreshedFor) {
        refreshedFor = facts.fixtures_fresh;
        // `router.refresh()` rather than `location.reload()`: it re-runs the
        // server component in place, so the page does not blank, the scroll
        // position survives, and a reader mid-sentence in the caveats is not
        // thrown back to the top.
        router.refresh();
        schedule();
        return;
      }
      const after = Date.now();
      const verdict = readWatch(facts, {
        visible_for_ms: visibleSince === null ? 0 : after - visibleSince,
        watch_remaining_ms: Math.max(0, GIVE_UP_MS - (after - startedAt)),
      });
      if (verdict.kind === "watch") {
        setPhase({ kind: "watching" });
        schedule();
        return;
      }
      setPhase({ kind: "verdict", verdict });
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        visibleSince = Date.now();
        void look();
      } else {
        visibleSince = null;
        clearTimeout(timer);
      }
    };

    setPhase({ kind: "checking" });
    // The leading edge: the first poll is now, not in ten seconds.
    void look();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // `renderedFresh` restarts the watch after a refresh that did not produce
    // a card: the new baseline is the count the new render actually saw.
  }, [renderedFresh, router, generation]);

  const checkAgain = (
    <button
      type="button"
      onClick={() => {
        setGeneration((n) => n + 1);
        router.refresh();
      }}
      className="underline underline-offset-2"
    >
      Check again
    </button>
  );

  if (phase.kind === "verdict" && phase.verdict.kind === "loop_stalled") {
    // A fault, in the fault ink the refresh panel uses for the same state.
    return (
      <p className="text-xs leading-snug text-accent-2" aria-live="polite">
        {phase.verdict.sentence} {checkAgain}.
      </p>
    );
  }
  // Spelled out rather than left to the `else` below: the type-checker does
  // not carry the early return above into the JSX, and the only verdict that
  // can reach the final branch is this one.
  const nothingDue =
    phase.kind === "verdict" && phase.verdict.kind === "nothing_due"
      ? phase.verdict
      : null;

  return (
    <p className="text-xs leading-snug text-muted" aria-live="polite">
      {phase.kind === "checking" ? (
        <>Checking whether a new price is on its way…</>
      ) : phase.kind === "watching" ? (
        <>
          Watching for the next price — this page will update itself when one
          lands, without you reloading it.
        </>
      ) : phase.kind === "gave_up" ? (
        <>
          No new prices arrived in five minutes, so this page has stopped
          watching for them. {checkAgain}.
        </>
      ) : phase.kind === "unreadable" ? (
        <>
          The sweep timetable did not answer while this page was watching, so
          it could not tell whether a price was coming. {checkAgain}.
        </>
      ) : nothingDue !== null ? (
        <>
          {nothingDue.sentence}
          {nothingDue.next_buy_ms !== null && (
            <>
              {" "}
              The next automatic buy is at{" "}
              {formatClock(nothingDue.next_buy_ms)}.
            </>
          )}{" "}
          {checkAgain}.
        </>
      ) : null}
    </p>
  );
}
