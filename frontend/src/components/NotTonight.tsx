"use client";

/**
 * The one-tap "not tonight", beside /bets' net strip (slice B5) — the
 * biggest red number in the product is where the impulse to chase lives,
 * and until now the control existed only on the slate.
 *
 * This is TonightStrip's exact mechanism, deliberately: the same
 * `engageLockout()` POST through the Next `/lockout` handler (session
 * cookie in, bearer token out) to `/api/desk/lockout`, and the same
 * **no-confirm rule** — "a dialog gives the impulse a veto". No duration
 * picker, no disengage; the release is the day roll and the locked state
 * renders it. Tapping twice is idempotent server-side.
 */

import { useState } from "react";

import { DISPLAY_TIME_ZONE, engageLockout } from "@/lib/api";

function clock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function NotTonight({
  lockoutUntilMs,
}: {
  lockoutUntilMs: number | null;
}) {
  const [tappedUntil, setTappedUntil] = useState<number | null>(null);
  const [locking, setLocking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lockedUntil =
    tappedUntil !== null
      ? tappedUntil
      : lockoutUntilMs !== null && lockoutUntilMs > Date.now()
        ? lockoutUntilMs
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

  return (
    <div className="mt-3">
      {lockedUntil !== null ? (
        <p className="text-xs text-muted">
          Not tonight — your call, earlier. It opens again at{" "}
          {clock(lockedUntil)}.
        </p>
      ) : (
        <button
          onClick={notTonight}
          disabled={locking}
          className="rounded-full border border-border px-3 py-1 text-xs text-muted transition-colors hover:border-accent-2/60 hover:text-accent-2"
        >
          {locking ? "Locking…" : "Not tonight"}
        </button>
      )}
      {error && (
        <p className="mt-1 text-xs text-negative" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
