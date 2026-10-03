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
export default function HeldConflictsNote({ ticker }: { ticker: string }) {
  const [answer, setAnswer] = useState<HeldConflicts | null>(null);
  useEffect(() => {
    let live = true;
    fetchHeldConflicts(ticker).then((value) => {
      if (live) setAnswer(value);
    });
    return () => {
      live = false;
    };
  }, [ticker]);
  if (!answer || answer.conflicts.length === 0) return null;
  return (
    <div
      role="status"
      className="mb-2 max-w-[65ch] rounded-lg border border-accent-2/50 bg-accent-2-soft px-3 py-2 text-xs leading-relaxed text-accent-2"
    >
      <p className="font-semibold">
        This bets against a ticket you already hold.
      </p>
      <ul className="mt-1 space-y-1">
        {answer.conflicts.map((c, i) => (
          <li key={`${c.position_id}-${i}`}>
            &ldquo;{c.leg_label}&rdquo;{" "}
            {c.kind === "opposite_side"
              ? "is the other side of"
              : "cannot win alongside"}{" "}
            &ldquo;{c.held_label}&rdquo; on ticket #{c.position_id}. At most
            one of the two can win, and each pays its own fee.
          </li>
        ))}
      </ul>
    </div>
  );
}
