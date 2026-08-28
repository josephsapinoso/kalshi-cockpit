"use client";

/**
 * Tonight's commitment and the "not tonight" note, on the deciding screen
 * (2026-08-21 partner ruling, docs/reviews/2026-08-21-items-2-3-ruling.md).
 *
 * The honesty rules, all load-bearing:
 *
 * - **Unsigned.** Count of markets and dollars staked since the day roll —
 *   never a net, never a direction. A signed running P&L here is the chase
 *   trigger this repo has deleted twice; the signed record lives on /bets,
 *   after settlement.
 * - **Stale refuses.** The fills mirror runs on the 5-minute cadence; if it
 *   has not been read for 30 minutes the strip says "not read since HH:MM",
 *   never 0 — "no bets tonight" off a stale mirror is a false negative in
 *   the flattering direction, on the screen whose purpose is to interrupt.
 * - **The lockout is a note, not a wall.** The banner does not hide the
 *   slate and has no "show anyway" (a show-anyway is a disengage in a
 *   costume). It states the release time and admits it cannot stop a bet
 *   in the Kalshi app. No engagement counter — a tally reads as a score.
 * - **No confirm step on the button** — the moment of clarity is brief,
 *   and a dialog gives the impulse a veto (the estimate form's argument,
 *   kept).
 */

import { useState } from "react";

import {
  DISPLAY_TIME_ZONE,
  engageLockout,
  type TonightActivity,
} from "@/lib/api";

function clock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function TonightStrip({
  tonight,
}: {
  tonight: TonightActivity;
}) {
  const [tappedUntil, setTappedUntil] = useState<number | null>(null);
  const [locking, setLocking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lockedUntil =
    tappedUntil !== null
      ? tappedUntil
      : tonight.lockout_until_ms !== null &&
          tonight.lockout_until_ms > Date.now()
        ? tonight.lockout_until_ms
        : null;

  const notTonight = () => {
    setLocking(true);
    setError(null);
    engageLockout()
      .then((result) => setTappedUntil(result.until_ms))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "lockout failed"),
      )
      .finally(() => setLocking(false));
  };

  const stale = tonight.bets === null;

  return (
    <div className="mt-4">
      {lockedUntil !== null ? (
        <section className="rounded-2xl border border-edge bg-card p-4">
          <div className="text-xs font-semibold uppercase tracking-widest text-muted">
            Not tonight — your call, earlier
          </div>
          <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted">
            You said not tonight. The slate stays visible — this note opens
            again at {clock(lockedUntil)}. It cannot stop a bet placed in the
            Kalshi app: nothing fires before a hand bet, and the venue&rsquo;s
            settled record shows it only afterwards. It is here because the
            you that wrote it was thinking clearly.
          </p>
        </section>
      ) : (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="text-sm">
            {stale ? (
              <span className="text-muted">
                Tonight&rsquo;s bets: not read
                {tonight.as_of_ms !== null
                  ? ` since ${clock(tonight.as_of_ms)}`
                  : " yet"}{" "}
                — the mirror is behind, which is not the same as no bets.
              </span>
            ) : tonight.bets === 0 ? (
              <span className="text-muted">
                Nothing staked tonight, as of {clock(tonight.as_of_ms!)}.
              </span>
            ) : (
              <span>
                <span className="font-semibold tabular">
                  {tonight.bets} {tonight.bets === 1 ? "market" : "markets"} ·{" "}
                  {tonight.staked_display} staked
                </span>
                <span className="text-muted"> tonight, your own fills</span>
              </span>
            )}
          </p>
          <button
            onClick={notTonight}
            disabled={locking}
            className="rounded-full border border-border px-3 py-1 text-xs text-muted transition-colors hover:border-accent-2/60 hover:text-accent-2"
          >
            {locking ? "Locking…" : "Not tonight"}
          </button>
        </div>
      )}
      {error && (
        <p className="mt-1 text-xs text-negative" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
