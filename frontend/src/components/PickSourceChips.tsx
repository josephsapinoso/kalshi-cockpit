"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import Term from "@/components/Term";
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
  const [name, setName] = useState<string | null>(
    ticker && block ? (block.tailed_from?.[ticker] ?? null) : null,
  );
  const [typed, setTyped] = useState("");
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
    // A new tag starts with no name; a name belongs to a tailed pick only.
    setName(null);
    router.refresh();
  }

  // ADR 0193 Amendment 1: who a tailed pick came from. Tapping the shown
  // name again clears it; the backend trims, limits and refuses in words.
  async function saveName(next: string | null) {
    if (!ticker) return;
    setBusy(true);
    setRefused(null);
    const answer = await setPickSource(ticker, "friend", next);
    setBusy(false);
    if (!answer.ok) {
      setRefused(answer.detail);
      return;
    }
    setName(next ? next.trim() || null : null);
    setTyped("");
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
      {chosen === "friend" && (
        <div className="mt-2" data-tailed-from>
          <span className="text-muted">
            <Term k="tail">Tailed</Term> from
            {name ? `: ${name}` : " (optional):"}
          </span>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {(block.tailed_names ?? []).map((known) => {
              const on = name !== null && name.toLowerCase() === known.toLowerCase();
              return (
                <button
                  key={known}
                  type="button"
                  disabled={busy}
                  aria-pressed={on}
                  onClick={() => saveName(on ? null : known)}
                  className={`min-h-7 rounded-full border px-2.5 disabled:opacity-50 ${
                    on ? "border-foreground font-semibold" : "border-border text-muted"
                  }`}
                >
                  {known}
                </button>
              );
            })}
            <input
              type="text"
              value={typed}
              maxLength={40}
              disabled={busy}
              onChange={(event) => setTyped(event.target.value)}
              placeholder="A new name"
              aria-label="A new name for who this pick came from"
              className="min-h-7 w-32 rounded border border-border bg-transparent px-2"
            />
            <button
              type="button"
              disabled={busy || typed.trim() === ""}
              onClick={() => saveName(typed.trim())}
              className="min-h-7 rounded-full border border-border px-2.5 text-muted disabled:opacity-50"
            >
              Save name
            </button>
          </div>
        </div>
      )}
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
