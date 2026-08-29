"use client";

/**
 * The calibration bet log's RECORD. The entry form is retired (ADR 0065,
 * 2026-08-22).
 *
 * Joe stopped the study on 2026-08-20 (Amendment 2, stopped without result),
 * and for two days this page kept a working form feeding a stopped study —
 * quiet misdirection with a banner on top. What retires the form for good is
 * that the typed P(YES) moved to where the bet is: the manual ticket asks for
 * it BEFORE revealing the price (ADR 0065) and the route refuses without it,
 * so every hand bet placed through the portal carries the number that was in
 * Joe's head first.
 *
 * **IT IS RECORDED. NOTHING READS IT BACK.** This comment said until
 * 2026-08-29 that the ticket is "where `bet_clv` gives it a consumer", and
 * that was never true: `bet_clv` (backend/bets.py:120) scores
 * `entry_price_tenths` against the closing mid and does not touch
 * `p_yes_bp`. Grep the tree -- `p_yes_bp` is written into `manual_orders`
 * and there is no SELECT on the column anywhere, only the idempotency
 * replay's `SELECT *`, which drops it. So the honest claim is about
 * CAPTURE, not consumption: the estimate is now taken under the conditions
 * that would make it worth scoring later -- typed blind, beside the order
 * it belongs to, on the bets that actually happen -- and no code scores it
 * today. Do not write a consumer back into this comment before one exists
 * in the tree; a registration that has not been accepted is not a consumer.
 *
 * This page keeps what was already typed:
 *
 * - **The entries are write-once and stay readable.** The revision path
 *   ("Mistyped?") remains — flagging is the record's only repair mechanism,
 *   and removing it would strand a fat-fingered row as fact forever.
 * - **No price appears on this screen, ever.** Unchanged from the form era:
 *   the embargoed captures stay embargoed (ADR 0044), and the record renders
 *   what was typed, never what the server captured beside it.
 */

import { useEffect, useState } from "react";

import {
  DISPLAY_TIME_ZONE,
  fetchRecentEstimates,
  fetchStudyStop,
  reviseEstimate,
  type RecentEstimate,
  type StudyStop,
} from "@/lib/api";

/** 6250 bp -> "62.50%". Rendering only; the record keeps the integer. */
function bpToPercent(bp: number): string {
  return `${(bp / 100).toFixed(2)}%`;
}

export default function EstimatePage() {
  const [recent, setRecent] = useState<RecentEstimate[]>([]);
  const [revising, setRevising] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [stop, setStop] = useState<StudyStop | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRecent = () =>
    fetchRecentEstimates()
      .then((payload) => setRecent(payload.estimates))
      .catch(() => setRecent([]));

  useEffect(() => {
    loadRecent();
    fetchStudyStop()
      .then(setStop)
      .catch(() => setStop(null));
  }, []);

  const flagRevised = async (id: number) => {
    const text = reason.trim();
    if (!text) return;
    try {
      await reviseEstimate(id, text);
      setRevising(null);
      setReason("");
      loadRecent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revision failed.");
    }
  };

  return (
    <main className="mx-auto w-full max-w-xl px-4 py-8">
      <header className="mb-6">
        <h1 className="display text-4xl">Estimates</h1>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted">
          The stopped study&rsquo;s record — every P(YES) that was typed while
          the log was open, exactly as typed. The form is retired: since the
          2026-08-22 review, the place to state a probability is the ticket,
          which asks before it shows you a price.
        </p>
      </header>

      {stop !== null && stop.study_state === "stopped_without_result" && (
        <section className="mb-6 rounded-2xl border border-edge bg-card p-5">
          <div className="text-xs font-semibold uppercase tracking-widest text-muted">
            Study stopped
          </div>
          <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted">
            You closed the calibration study on{" "}
            {new Date(stop.stopped_by_owner_ms).toLocaleDateString("en-US", {
              timeZone: DISPLAY_TIME_ZONE,
              month: "long",
              day: "numeric",
            })}
            , without a result. Nothing here was ever scored, and nothing will
            be — starting again would be a fresh study, not a resume.
          </p>
        </section>
      )}

      {error && (
        <p className="mb-4 rounded-xl border border-negative/50 bg-negative/10 px-4 py-3 text-sm text-negative">
          {error}
        </p>
      )}

      {recent.length === 0 ? (
        <p className="max-w-[65ch] text-sm text-muted">
          Nothing was logged while the study ran, or the record can&rsquo;t be
          read right now — an empty list here does not distinguish the two.
        </p>
      ) : (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
            Entries
          </h2>
          <ul className="mt-3 space-y-2">
            {recent.map((entry) => (
              <li key={entry.id} className="rounded-xl border border-edge bg-card px-4 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted">
                    {entry.ticker}
                  </span>
                  <span className="text-sm font-semibold">
                    {bpToPercent(entry.stated_probability_bp)}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between gap-3">
                  <span className="text-xs text-muted">
                    {new Date(entry.estimate_server_ms).toLocaleString("en-US", {
                      timeZone: DISPLAY_TIME_ZONE,
                    })}
                    {entry.stated_probability_is_revised === 1 && (
                      <span className="ml-2 font-semibold text-negative">
                        revised &mdash; excluded
                      </span>
                    )}
                  </span>
                  {entry.stated_probability_is_revised === 0 &&
                    (revising === entry.id ? (
                      <span className="flex items-center gap-2">
                        <input
                          value={reason}
                          onChange={(event) => setReason(event.target.value)}
                          placeholder="why?"
                          autoComplete="off"
                          className="w-28 rounded-lg border bg-background px-2 py-1 text-xs"
                        />
                        <button
                          onClick={() => flagRevised(entry.id)}
                          disabled={reason.trim().length === 0}
                          className="text-xs font-semibold text-negative disabled:opacity-40"
                        >
                          Flag
                        </button>
                        <button
                          onClick={() => {
                            setRevising(null);
                            setReason("");
                          }}
                          className="text-xs text-muted"
                        >
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setRevising(entry.id)}
                        className="text-xs text-muted underline"
                      >
                        Mistyped?
                      </button>
                    ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
