"use client";

import { useEffect, useState } from "react";

import { cancelComboBid, fetchComboBids } from "@/lib/api";
import type { ComboBid } from "@/lib/api";

/**
 * Every bid standing on the exchange, and the button that takes one back.
 *
 * ADR 0084. **This panel is not a convenience, it is the other half of the
 * control that places a bid.** A resting bid is the first order shape in this
 * app that outlives its request: it can be taken minutes or hours later, while
 * the page is closed and Joe is somewhere else. An interface that can create
 * one and cannot show or withdraw it is an interface that loses money quietly.
 *
 * **Absent when there are none, rather than an empty box.** A permanent "no
 * resting bids" panel is a line of furniture that trains the eye to skip the
 * space — which is exactly where a live one will appear.
 *
 * The status word is the venue's, and `note` beside it is the desk's: "resting"
 * reads to most people as "working towards a fill", and on a combination
 * nobody has ever been observed bidding on, that is the wrong impression to
 * leave standing.
 */
export default function RestingBids() {
  const [bids, setBids] = useState<ComboBid[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [said, setSaid] = useState<string | null>(null);

  const load = async () => {
    const result = await fetchComboBids().catch(() => null);
    setBids(result?.bids ?? []);
  };

  useEffect(() => {
    void load();
    // A standing offer can be taken while this page is open, so the panel
    // re-reads. Thirty seconds: slow enough not to matter against a desk the
    // odds feed refreshes every ten minutes, fast enough that a fill does not
    // sit unseen for the length of a game.
    const timer = setInterval(() => void load(), 30_000);
    return () => clearInterval(timer);
  }, []);

  if (!bids || bids.length === 0) return null;

  const withdraw = async (bid: ComboBid) => {
    setBusy(bid.id);
    const result = await cancelComboBid(bid.id);
    setSaid(result.ok ? result.words : result.refusal);
    setBusy(null);
    await load();
  };

  return (
    <section
      aria-label="Resting bids"
      className="mb-6 rounded border border-border p-4"
    >
      <h2 className="text-sm font-semibold">Your buy orders on the exchange</h2>
      <p className="mt-1 text-xs leading-snug text-muted">
        These are <strong>buy</strong> orders waiting for a seller, not
        positions you hold. Each fills only if someone sells to you at your
        price, and on a combination nobody has ever been observed doing so.
        Each is withdrawn automatically when its first game starts.
      </p>

      <ul className="mt-3 space-y-3">
        {bids.map((bid) => (
          <li key={bid.id} className="border-t border-border pt-3 text-sm">
            <p className="font-semibold">
              {bid.card_key} · {bid.contracts} at{" "}
              <span className="tabular">{bid.price_display}</span> ·{" "}
              <span className="tabular">{bid.committed_display}</span> committed
            </p>
            <p className="text-xs text-muted">
              {bid.status}
              {bid.note ? ` — ${bid.note}` : ""}
              {bid.dry_run ? " (dry run: nothing was sent)" : ""}
            </p>
            <p className="break-all text-[11px] text-muted">{bid.ticker}</p>
            <button
              onClick={() => withdraw(bid)}
              disabled={busy === bid.id}
              className="mt-2 min-h-[44px] rounded border border-border px-3 text-sm font-semibold disabled:opacity-40"
            >
              {busy === bid.id ? "Cancelling…" : "Cancel this order"}
            </button>
          </li>
        ))}
      </ul>

      {said && <p className="mt-3 text-sm">{said}</p>}
    </section>
  );
}
