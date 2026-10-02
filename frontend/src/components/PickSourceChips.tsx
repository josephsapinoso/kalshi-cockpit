"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { setPickSource, type PickSourcesBlock } from "@/lib/api";

/**
 * "Where did this pick come from?" -- one row of chips per bet (v63, Joe
 * 2026-10-02). A tap stores his word for the ticker; tapping the chosen
 * chip again clears it. Nothing is stored without a tap: a suggestion (a
 * card stamp or a preset label, the only two the record can prove) is drawn
 * dashed and stays a suggestion until he taps it.
 *
 * The chips are in the server's fixed order, never sorted by any result.
 * A ticket with no ticker (a hand-recorded sportsbook slip) gets no chips.
 */
export default function PickSourceChips({
  ticker,
  block,
}: {
  ticker: string | null | undefined;
  block: PickSourcesBlock | undefined;
}) {
  const router = useRouter();
  const [chosen, setChosen] = useState<string | null>(
    ticker && block ? (block.tagged[ticker] ?? null) : null,
  );
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  if (!ticker || !block) return null;
  const suggested = chosen === null ? (block.suggested[ticker] ?? null) : null;

  async function tap(key: string) {
    if (!ticker) return;
    const next = chosen === key ? null : key;
    setBusy(true);
    setRefused(null);
    const answer = await setPickSource(ticker, next);
    setBusy(false);
    if (!answer.ok) {
      setRefused(answer.detail);
      return;
    }
    setChosen(next);
    router.refresh();
  }

  return (
    <div className="mt-2 text-xs">
      <span className="text-muted">
        {chosen === null ? "Where did this pick come from?" : "Pick from:"}
      </span>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {block.options.map((option) => {
          const on = chosen === option.key;
          const hint = suggested === option.key;
          return (
            <button
              key={option.key}
              type="button"
              disabled={busy}
              aria-pressed={on}
              onClick={() => tap(option.key)}
              className={`min-h-7 rounded-full border px-2.5 disabled:opacity-50 ${
                on
                  ? "border-foreground font-semibold"
                  : hint
                    ? "border-dashed border-foreground text-muted"
                    : "border-border text-muted"
              }`}
            >
              {option.label}
              {hint ? " ?" : ""}
            </button>
          );
        })}
      </div>
      {suggested !== null && (
        <p className="mt-1 text-[11px] text-muted">
          The dashed one is what the desk&rsquo;s own record shows. Tap it to
          confirm.
        </p>
      )}
      {refused && <p className="mt-1 text-[11px] text-muted">{refused}</p>}
    </div>
  );
}
