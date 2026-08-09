import type { Recommendation } from "@/lib/api";

/**
 * One candidate, as a line rather than a card.
 *
 * The Board used to render everything as a card and show only what survived
 * every check, which on a slate of ~200 decisions with 0 actionable is a blank
 * page. Mispricing is a factor, not a filter: the rows that were rejected are
 * the only content there is, and a card each makes them unscannable.
 *
 * **This relaxes nothing.** These rows carry `suggested_contracts === 0`, the
 * suppression reasons are the server's, and the order endpoint re-derives every
 * decision inside the request. What changed is what is *visible*, not what is
 * bettable — which is why nothing here is tappable and nothing here shows a
 * size or a cost. A rejected row that opened an order ticket would suggest the
 * decision is reversible from this screen; it is not.
 */

export type SlateState = "expired" | "rejected" | "no-edge";

const CHIP: Record<SlateState, { label: string; className: string }> = {
  expired: {
    label: "EXPIRED",
    className: "border-accent-2/50 bg-card text-accent-2",
  },
  rejected: {
    // Named, not implied. A dimmed row reads as a rendering accident; a word
    // reads as a decision, and the reason beside it says whose.
    label: "REJECTED",
    className: "border-accent/50 bg-accent-soft text-accent",
  },
  "no-edge": {
    label: "NO EDGE",
    className: "text-muted",
  },
};

/**
 * Why this row is not bettable, in the fewest words that are still true.
 *
 * The suppression codes are the server's vocabulary and are shown verbatim —
 * they are what `/api/suppression` counts and what a miscalibrated rule shows
 * up as. Translating them here would give the same rule two names.
 */
function stateOf(rec: Recommendation, fallback: SlateState): SlateState {
  if (rec.suppressed_reason) return "rejected";
  return fallback;
}

export default function SlateRow({
  rec,
  state,
  oddsLimitMs,
}: {
  rec: Recommendation;
  /** What this row is when it carries no suppression reason of its own. */
  state: SlateState;
  oddsLimitMs: number;
}) {
  const resolved = stateOf(rec, state);
  const chip = CHIP[resolved];
  const positive = rec.edge_cents > 0;

  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3">
      <span
        className={`shrink-0 rounded-full border px-2 py-0.5 font-mono text-[0.65rem] font-bold tracking-widest ${chip.className}`}
      >
        {chip.label}
      </span>
      <span className="min-w-0 font-semibold tracking-tight">
        {rec.team ?? rec.ticker}
      </span>
      {/* Fair value as a percentage and the ask as a price, so the two cannot
          be read as the same kind of number. */}
      <span className="tabular text-sm text-muted">
        {rec.fair_percent_display} fair / {rec.ask_display} ask
      </span>
      <span
        className={`tabular text-sm font-semibold ${
          positive ? "text-positive" : "text-negative"
        }`}
      >
        {positive ? "+" : ""}
        {rec.edge_cents.toFixed(1)}c
      </span>
      <span className="ml-auto min-w-0 break-words font-mono text-xs text-muted">
        {resolved === "rejected"
          ? rec.suppressed_reason
          : resolved === "expired"
            ? `consensus past ${Math.round(oddsLimitMs / 60_000)}m`
            : "no edge after fees"}
      </span>
    </div>
  );
}
