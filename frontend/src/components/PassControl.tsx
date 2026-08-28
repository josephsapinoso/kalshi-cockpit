"use client";

/**
 * The per-market "Pass", on the game screen where the deciding happens
 * (ADR 0066). `POST /api/desk/pass` existed, was tested, and had no caller;
 * the record could show every bet Joe placed and no market he walked away
 * from. This is the caller.
 *
 * The honesty rules, all inherited and all load-bearing:
 *
 * - **No confirm step** — TonightStrip's rule, kept: the moment of clarity
 *   is brief, and a dialog gives the impulse a veto. A pass is the safe
 *   direction; nothing here needs a second look.
 * - **The reason is optional and stays collapsed.** Passing without a
 *   reason is one tap; a required reason is a toll on the correct boring
 *   action (the `DeskPassRequest` docstring's argument, kept).
 * - **Records, does not hide.** On success the control says "Passed" and
 *   disables — the market's facts stay on screen, because a pass is a
 *   decision about tonight, not a verdict on the market. It blocks nothing:
 *   the ticket above still works, and so does the Kalshi app.
 * - **Visually secondary to everything money-red.** The quiet bordered pill
 *   (TonightStrip's), never `bg-accent-fill` — a filled control claims the
 *   page (ADR 0061 §3, as amended by ADR 0081), and a
 *   pass is the calm alternative, not a rival call to action.
 *
 * Idempotence is UI state, not a DB constraint: the table is append-only
 * with no dedupe, so this component disables after success rather than
 * trusting the server to collapse re-taps.
 */

import { useState } from "react";

import { recordPass } from "@/lib/api";
import Hint from "@/components/Hint";

export default function PassControl({ ticker }: { ticker: string }) {
  const [passed, setPassed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reason, setReason] = useState("");

  const pass = () => {
    setPending(true);
    setError(null);
    recordPass(ticker, reason.trim() || undefined)
      .then((result) => {
        if (result.recorded) {
          setPassed(true);
        } else {
          setError(result.detail);
        }
      })
      .finally(() => setPending(false));
  };

  return (
    <div className="mt-4">
      {passed ? (
        <p className="text-sm text-muted">
          Passed — recorded. The market stays on screen; a pass is a decision,
          not a curtain.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <button
            onClick={pass}
            disabled={pending}
            className="min-h-11 rounded-full border border-border px-4 py-1 text-xs text-muted transition-colors hover:border-accent-2/60 hover:text-accent-2"
          >
            {pending ? "Recording…" : "Pass on this market"}
          </button>
          <Hint
            hint="Recording a pass writes one line: you looked at this market and chose not to bet it. It blocks nothing — not the ticket above, not the Kalshi app — and it is never scored or graded."
            className="text-xs text-muted"
          >
            records a decision; blocks nothing
          </Hint>
          {!reasonOpen && (
            <button
              onClick={() => setReasonOpen(true)}
              className="text-xs text-muted underline decoration-dotted"
            >
              add a reason (optional)
            </button>
          )}
        </div>
      )}
      {reasonOpen && !passed && (
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          maxLength={500}
          placeholder="why — for your own record, never graded"
          autoComplete="off"
          className="mt-2 w-full max-w-sm rounded-xl border bg-background px-3 py-2 text-sm"
        />
      )}
      {error && (
        <p className="mt-1 text-xs text-negative" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
