"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { fetchWindow } from "@/lib/api";

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
 * **It stops.** Five minutes, matching `DEFAULT_ATTENTION_TTL_MS` — the window
 * in which the heartbeat that caused this page to be watched is still buying
 * sweeps. Past that, nothing has landed and something is wrong; a poller that
 * ran until the tab closed would be a background request loop nobody asked
 * for. It says it has stopped rather than going quiet, because a silent
 * watcher and a broken one look identical.
 *
 * **Hidden tabs do not poll, and that is a correctness argument rather than a
 * courtesy.** `Nav.tsx` gates its heartbeat on `document.visibilityState`, so a
 * backgrounded tab is sending none — which means no sweep is coming for it, so
 * a poll could only ever confirm that. It resumes on `visibilitychange`, which
 * is also the moment the heartbeat resumes.
 *
 * WHAT THIS DOES NOT ESTABLISH
 * ----------------------------
 * - **That a refresh produces cards.** More fresh fixtures may still be fewer
 *   than a card's minimum. The page re-renders and says so again, with the new
 *   count; the watcher then starts over against that count.
 * - **That anything is bettable.** It re-prices a comparison. `actionable` has
 *   effectively been 0 for the life of this record.
 */

/** How often to ask. The sweep lands ~10s after a cold open, so this catches
 *  it on the first or second try; faster would mostly ask before the answer
 *  could have changed. */
const POLL_MS = 10_000;

/** `attention.DEFAULT_ATTENTION_TTL_MS`. Past the window in which the
 *  heartbeat is still buying sweeps, waiting is not waiting for anything. */
const GIVE_UP_MS = 300_000;

export default function RefreshWhenPriced({
  renderedFresh,
}: {
  /** `ActionableWindow.fixtures_fresh` as the server saw it for this render. */
  renderedFresh: number;
}) {
  const router = useRouter();
  const [stopped, setStopped] = useState(false);
  // Bumped by "Check again", so the button restarts the watch as well as
  // re-rendering. Without it a refresh that changed nothing leaves the deps
  // identical, the effect does not re-run, and the button reads as a control
  // that half works.
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval>;
    const startedAt = Date.now();
    const stop = () => {
      cancelled = true;
      clearInterval(timer);
      setStopped(true);
    };

    const look = async () => {
      if (cancelled) return;
      // Checked before the visibility gate, so a tab that spent the whole
      // budget in the background comes back to "stopped" rather than to a
      // watcher that quietly restarts its five minutes on every return.
      if (Date.now() - startedAt > GIVE_UP_MS) {
        stop();
        return;
      }
      if (document.visibilityState !== "visible") return;
      let fresh: number;
      try {
        fresh = (await fetchWindow()).fixtures_fresh;
      } catch {
        // A timetable that will not answer is not "nothing landed" — it is a
        // question that could not be asked. Keep waiting; the next tick may
        // get an answer, and the budget above still bounds the whole thing.
        return;
      }
      if (cancelled || fresh <= renderedFresh) return;
      // `router.refresh()` rather than `location.reload()`: it re-runs the
      // server component in place, so the page does not blank, the scroll
      // position survives, and a reader mid-sentence in the caveats is not
      // thrown back to the top.
      router.refresh();
    };

    setStopped(false);
    timer = setInterval(look, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void look();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // `renderedFresh` restarts the watch after a refresh that did not produce
    // a card: the new baseline is the count the new render actually saw.
  }, [renderedFresh, router, generation]);

  return (
    <p className="text-xs leading-snug text-muted" aria-live="polite">
      {stopped ? (
        <>
          No new prices arrived in five minutes, so this page has stopped
          watching for them.{" "}
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
          .
        </>
      ) : (
        <>
          Watching for the next price — this page will update itself when one
          lands, without you reloading it.
        </>
      )}
    </p>
  );
}
