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
 *
 * **A refused leg writes no row, and `posted` is how that refusal still
 * reaches the screen (#155).** All three triggers now keep the
 * `LegVerdictsResult` their own `requestLegVerdicts` call resolves to,
 * instead of firing it with `void` and throwing the answer away, and pass it
 * in here. `overlayPosted` below lays a posted `refused` row over a GET row
 * that still reads `none` for the same `ticker:side` -- and only `none`: a
 * GET row already reading `pending`/`cached`/`complete`/`refused` is newer
 * truth than the POST that started it, and wins untouched. So "nobody has
 * asked yet" is reachable for a leg only when no posted refusal named it.
 * A posted network/5xx/off-seat `error` renders as its own line and never
 * folds into that fallback sentence either.
 */

import { useEffect, useState } from "react";

import { fetchLegVerdicts, formatAge } from "@/lib/api";
import type { LegVerdict, LegVerdictInput, LegVerdictsResult } from "@/lib/api";
import Term from "@/components/Term";

/**
 * Overlay a trigger's own POST result onto the poll's rows. See the module
 * docstring for why: a refused leg writes no row, so left alone the GET
 * poll would read `none` for it and the panel would claim nobody asked.
 */
function overlayPosted(
  rows: LegVerdict[],
  posted: LegVerdictsResult | null | undefined,
): LegVerdict[] {
  if (!posted || posted.legs.length === 0) return rows;
  const byKey = new Map(
    posted.legs.map((row) => [`${row.ticker}:${row.side}`, row] as const),
  );
  return rows.map((row) => {
    if (row.state !== "none") return row;
    const overlay = byKey.get(`${row.ticker}:${row.side}`);
    return overlay && overlay.state === "refused" ? overlay : row;
  });
}

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
  hideUnasked = false,
  posted = null,
}: {
  legs: LegVerdictInput[];
  // When the caller last fired `requestLegVerdicts` for these legs, or null.
  // A change restarts the poll: the component can mount long before the
  // request (inside a closed <details>, on page load), and a poll that
  // already stopped on `none` would never see the verdict arrive.
  requestedAtMs?: number | null;
  // The card-level view (the "Ask the scouts" button) shows only legs that
  // have a read. Before any tap, a card full of "nobody has asked yet" lines
  // would be noise.
  hideUnasked?: boolean;
  // The caller's own trigger's POST result (#155) -- kept, not discarded,
  // so a refused leg's reason reaches this panel even though a refusal
  // writes no row for the GET poll below to find. See `overlayPosted`.
  posted?: LegVerdictsResult | null;
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
  const merged = overlayPosted(rows, posted);
  // A posted network/5xx/off-seat error is the trigger's own failure and
  // takes precedence over whatever the last GET happened to read -- and,
  // per the module docstring, it renders as its own line and never as
  // "nobody has asked yet".
  const postedError = posted?.error ?? null;
  const shown =
    hideUnasked && requestedAtMs === null
      ? merged.filter((row) => row.state !== "none")
      : merged;
  if (hideUnasked && shown.length === 0 && !error && !postedError) return null;

  return (
    <div className="mt-2 space-y-1 border-t border-border pt-2">
      <p className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">
        Scouts&rsquo; read &mdash; <Term k="advisory">advisory</Term>, not a
        prediction
      </p>
      {(postedError ?? error) && (
        <p className="text-xs text-muted">{postedError ?? error}</p>
      )}
      {shown.map((row) => (
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
