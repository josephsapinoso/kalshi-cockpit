"use client";

/**
 * The leg scout's TAKE/PASS, in plain words, beside a leg Joe is about to
 * buy (#151, ADR 0186).
 *
 * **Advisory, and this file is where that is enforced, not the backend.**
 * It takes no callback, imports no ticket or buy component, and disables
 * nothing -- `tests/test_leg_verdicts_ui.py` pins all three, because the one
 * thing this seat is not allowed to become is a second gate. Joe's own
 * words: *"I just want to know if the scouts would make the bet or not"* --
 * an opinion to weigh, never a block. He can buy straight through a PASS.
 *
 * **TAKE is never green.** PASS means the seat found a specific, current
 * reason to avoid this side; that is worth a warning colour. TAKE means it
 * found no such reason, which is the *absence* of an objection, not a
 * prediction that the bet wins -- painting it "go" green would claim more
 * than the seat is allowed to say. Both render at the same size; only PASS
 * gets a colour.
 *
 * **This reads, it never asks.** Only `fetchLegVerdicts` (a `GET`, spends
 * nothing) is called here. The two triggers that can make the seat actually
 * RUN -- a "Price on Kalshi" tap and opening "Bet these legs one by one" --
 * live in `PriceOnKalshi.tsx` and `ParlayCards.tsx`, and call
 * `requestLegVerdicts` themselves. This component does not know whether it
 * was rendered after one of those fired; it just polls for whatever the
 * server has.
 *
 * Polls every `POLL_MS` while any leg reads `pending`, and gives up after
 * `POLL_STOP_AFTER_MS` -- a card left open on a phone that never comes back
 * must not poll forever.
 */

import { useEffect, useState } from "react";

import { fetchLegVerdicts, formatAge } from "@/lib/api";
import type { LegVerdict, LegVerdictInput } from "@/lib/api";
import Term from "@/components/Term";

const POLL_MS = 5_000;
const POLL_STOP_AFTER_MS = 3 * 60 * 1000;
// After a trigger fires, a leg can read `none` for a moment: the POST that
// writes its `running` row may land after this component's first GET. Keep
// polling through `none` for this long after a request, or the line would
// stop at "nobody has asked yet" while the seat is running.
const NONE_GRACE_MS = 30_000;

export default function LegVerdicts({
  legs,
  requestedAtMs = null,
}: {
  legs: LegVerdictInput[];
  // When the caller last fired `requestLegVerdicts` for these legs, or null.
  // A change restarts the poll: the component can mount long before the
  // request (inside a closed <details>, on page load), and a poll that
  // already stopped on `none` would never see the verdict arrive.
  requestedAtMs?: number | null;
}) {
  const [rows, setRows] = useState<LegVerdict[]>([]);
  const [error, setError] = useState<string | null>(null);
  // A stable string key for the effect below -- `legs` is a fresh array on
  // every render of the caller, and re-running the poll loop on every
  // render would restart the 3-minute clock forever.
  const legsKey = legs.map((leg) => `${leg.ticker}:${leg.side}`).join(",");

  useEffect(() => {
    if (legs.length === 0) {
      setRows([]);
      setError(null);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    const startedMs = Date.now();

    const read = async () => {
      const result = await fetchLegVerdicts(legs);
      if (cancelled) return;
      setRows(result.legs);
      setError(result.error);
      const justAsked =
        requestedAtMs !== null && Date.now() - requestedAtMs < NONE_GRACE_MS;
      const stillWaiting = result.legs.some(
        (leg) => leg.state === "pending" || (justAsked && leg.state === "none"),
      );
      if (!stillWaiting && timer) {
        clearInterval(timer);
        timer = null;
      }
    };

    void read();
    timer = setInterval(() => {
      if (Date.now() - startedMs > POLL_STOP_AFTER_MS) {
        if (timer) clearInterval(timer);
        timer = null;
        return;
      }
      void read();
    }, POLL_MS);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
    // `legs` itself is deliberately not a dependency -- `legsKey` is its
    // stable stand-in, for the reason above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [legsKey, requestedAtMs]);

  if (legs.length === 0) return null;

  return (
    <div className="mt-2 space-y-1 border-t border-border pt-2">
      <p className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">
        Scouts&rsquo; read &mdash; <Term k="advisory">advisory</Term>, not a
        prediction
      </p>
      {error && <p className="text-xs text-muted">{error}</p>}
      {rows.map((row) => (
        <LegVerdictLine key={`${row.ticker}:${row.side}`} row={row} />
      ))}
    </div>
  );
}

function LegVerdictLine({ row }: { row: LegVerdict }) {
  if (row.state === "pending") {
    return (
      <p className="text-xs text-muted">Scouts are reading this leg&hellip;</p>
    );
  }
  if (row.state === "refused" || row.state === "none") {
    return (
      <p className="text-xs text-muted">
        No scout read: {row.refusal_reason ?? "nobody has asked yet"}
      </p>
    );
  }
  // `cached` -- a complete verdict.
  const isPass = row.verdict === "pass";
  return (
    <p className="text-xs leading-snug">
      {/* Never `text-positive` -- see the module docstring. PASS gets the
          warning colour; TAKE stays plain ink. */}
      <span className={isPass ? "font-semibold text-accent-2" : "font-semibold"}>
        {isPass ? "PASS" : "TAKE"}
      </span>{" "}
      <span className="text-muted">{row.reason}</span>
      {row.ask_display_at_verdict !== null && (
        <span className="text-muted"> &middot; at {row.ask_display_at_verdict}</span>
      )}
      {row.age_ms !== null && (
        <span className="text-muted"> &middot; {formatAge(row.age_ms)}</span>
      )}
    </p>
  );
}
