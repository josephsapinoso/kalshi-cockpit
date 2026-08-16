"use client";

import { useCallback, useState } from "react";

import { refreshOdds } from "@/lib/api";
import type { OddsRefreshResult } from "@/lib/api";

/**
 * Buy fresh sportsbook odds now, because a person is looking at the screen.
 *
 * **The problem this solves is a clock, not a price.** The API re-checks the
 * stored consensus against *now* on every read, so every row goes grey
 * `MAX_ODDS_AGE_S` after the sweep that priced it. The rolling refresh
 * (ADR 0030) holds that open across a planned kickoff cluster -- the hour
 * before first pitch -- and nothing else. Open the cockpit two hours out and
 * the whole slate is struck through on a timer, with the games and the prices
 * both perfectly real.
 *
 * **What it does not do, said on the button itself.** It buys a *fresh price*.
 * It does not make a row bettable, and it cannot produce an edge that was not
 * there: `actionable` has been 0 for the life of this record across every
 * market type. A button labelled "find a bet" would be the most misleading
 * element on the page, which is the same reason `WindowSchedule` says
 * *priceable* and never *bettable*.
 *
 * **Every answer is rendered, including every refusal.** A cooldown, the day's
 * slice for taps and the odds budget all come back as prose from the server and
 * are shown verbatim. Inventing a friendlier sentence here would mean two
 * places deciding what a refusal means, and the screen is the one that gets
 * believed.
 *
 * **The credit cost is on the button before it is spent**, because the two
 * variants differ by more than 4x -- team lines are one call, one fixture's
 * player props are billed per market key per region on top of it.
 */
export default function RefreshOddsButton({
  sportKey,
  oddsEventId = null,
  label,
  credits,
  className = "",
}: {
  sportKey: string;
  /** `null` buys team lines. A fixture id also buys that game's player props. */
  oddsEventId?: string | null;
  label: string;
  /**
   * What a tap is expected to cost, from the server's own arithmetic.
   *
   * Passed in rather than computed here: it is `markets x regions` over the
   * *deployed* lists, and a number this component derived would be a second
   * implementation that silently stops matching the bill.
   */
  credits: number;
  className?: string;
}) {
  const [phase, setPhase] = useState<"idle" | "sending" | "answered">("idle");
  const [result, setResult] = useState<OddsRefreshResult | null>(null);

  const tap = useCallback(async () => {
    setPhase("sending");
    setResult(null);
    const answer = await refreshOdds(sportKey, oddsEventId);
    setResult(answer);
    setPhase("answered");
  }, [sportKey, oddsEventId]);

  return (
    <div className={className}>
      <button
        type="button"
        onClick={tap}
        disabled={phase === "sending"}
        className="rounded-lg border px-3 py-2 text-sm font-semibold disabled:opacity-50"
      >
        {phase === "sending" ? "Buying…" : label}
        <span className="ml-2 font-normal text-muted">
          {credits} credit{credits === 1 ? "" : "s"}
        </span>
      </button>

      {phase === "answered" && result ? (
        <p
          className="mt-2 text-sm"
          // `polite`, so a refusal is announced without interrupting whatever
          // the reader was on. Nothing here is urgent -- no money moved.
          aria-live="polite"
        >
          {/* The server's words, unedited. See the component docstring. */}
          {result.detail}
          {result.accepted ? (
            <>
              {" "}
              {/* Reload rather than a poll: the board is a server component and
                  the runner writes on a ~15s cadence, so there is nothing to
                  subscribe to and a spinner would be pretending. */}
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="underline underline-offset-2"
              >
                Reload the board
              </button>{" "}
              in about 15 seconds.
            </>
          ) : null}
        </p>
      ) : null}

      <p className="mt-1 text-xs text-muted">
        Buys a fresh price. It does not make a row bettable — no row on this
        instance has ever cleared the fee.
      </p>
    </div>
  );
}
