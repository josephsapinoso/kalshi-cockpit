"use client";

import { useEffect, useState } from "react";

import { fetchHeldConflicts, type HeldConflicts } from "@/lib/api";

/**
 * "You already hold the other side" -- shown above Ask the market (Joe,
 * 2026-10-03). It warns and never blocks: a bet on the other side can be
 * deliberate (a hedge is exactly that), and nothing on a spend path reads
 * it. Only exact clashes are named (`backend/held_conflicts.py`); when the
 * desk finds none, or cannot read the combination, it says nothing rather
 * than "no clash", because a clash between different market families is
 * never checked.
 */
export default function HeldConflictsNote({
  ticker,
  side,
}: {
  ticker: string;
  /** Set by the manual-order ticket: check this one market and side. Absent
   *  means `ticker` is a combination (Ask the market). */
  side?: "yes" | "no";
}) {
  const [answer, setAnswer] = useState<HeldConflicts | null>(null);
  useEffect(() => {
    let live = true;
    fetchHeldConflicts(ticker, side).then((value) => {
      if (live) setAnswer(value);
    });
    return () => {
      live = false;
    };
  }, [ticker, side]);
  if (!answer || answer.conflicts.length === 0) return null;
  return (
    <div
      role="status"
      className="mb-2 max-w-[65ch] rounded-lg border border-accent-2/50 bg-accent-2-soft px-3 py-2 text-xs leading-relaxed text-accent-2"
    >
      <p className="font-semibold">
        {answer.conflicts.every((c) => c.kind === "same_side")
          ? "You already hold this on a ticket."
          : "This bets against a ticket you already hold."}
      </p>
      <ul className="mt-1 space-y-1">
        {answer.conflicts.map((c, i) => (
          <li key={`${c.position_id}-${i}`}>
            &ldquo;{c.leg_label}&rdquo;{" "}
            {c.kind === "opposite_side"
              ? "is the other side of"
              : c.kind === "same_side"
                ? "is the same side you already hold in"
                : "cannot win alongside"}{" "}
            &ldquo;{c.held_label}&rdquo; on ticket #{c.position_id}.{" "}
            {c.kind === "same_side"
              ? "You would hold it twice, and each pays its own fee."
              : "At most one of the two can win, and each pays its own fee."}
          </li>
        ))}
      </ul>
    </div>
  );
}
