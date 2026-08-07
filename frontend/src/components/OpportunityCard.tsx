import type { Recommendation } from "@/lib/api";
import { formatAge, formatKickoff, freshness } from "@/lib/api";

const MAX_QUOTE_AGE_MS = 30_000;

/**
 * One opportunity, as a card.
 *
 * Card rather than table row on purpose: this is used on a phone, and a
 * seven-column table at 390px is unreadable. The card puts the one comparison
 * that matters -- fair versus what you pay -- at the top in large type, and
 * relegates the machinery below it.
 */
export default function OpportunityCard({
  rec,
  suppressed = false,
}: {
  rec: Recommendation;
  suppressed?: boolean;
}) {
  const band = freshness(rec.kalshi_quote_age_ms, MAX_QUOTE_AGE_MS);
  const positive = rec.edge_cents > 0;

  return (
    <article
      className={`animate-in rounded-2xl border bg-card p-5 transition-all sm:p-6 ${
        suppressed ? "opacity-70" : "hover:-translate-y-1 hover:border-accent"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-lg font-bold tracking-tight">
            {rec.team ?? rec.ticker}
          </h3>
          <p className="mt-0.5 truncate text-sm text-muted">
            {rec.event_title ?? rec.ticker}
          </p>
        </div>
        {rec.commence_ms && (
          <span className="shrink-0 rounded-full bg-accent-soft px-3 py-1 font-mono text-xs text-accent">
            {formatKickoff(rec.commence_ms)}
          </span>
        )}
      </div>

      {/* The comparison that decides the bet, given the most visual weight. */}
      <div className="mt-5 grid grid-cols-3 gap-3 border-t pt-4">
        <Figure label="Consensus fair" value={rec.fair_display} />
        <Figure label="Kalshi asks" value={rec.ask_display} />
        <Figure
          label="Edge, net of fees"
          value={`${positive ? "+" : ""}${rec.edge_cents.toFixed(1)}c`}
          tone={positive ? "positive" : "negative"}
        />
      </div>

      {rec.suggested_contracts > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t pt-4">
          <Figure label="Buy" value={`${rec.suggested_contracts}`} />
          <Figure label="Cost" value={`$${(rec.ask_dollars * rec.suggested_contracts).toFixed(2)}`} />
          <Figure label="Fee" value={`$${rec.fee_predicted.toFixed(2)}`} />
          <Figure
            label="Expected"
            value={`${rec.ev_net_dollars >= 0 ? "+" : ""}$${rec.ev_net_dollars.toFixed(2)}`}
            tone={rec.ev_net_dollars >= 0 ? "positive" : "negative"}
          />
        </div>
      )}

      <p className="mt-4 text-sm leading-relaxed text-muted">{rec.reason_text}</p>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-3 font-mono text-xs text-muted">
        <span className={`freshness-${band}`}>
          quote {formatAge(rec.kalshi_quote_age_ms)}
        </span>
        <span>books {formatAge(rec.odds_age_ms)}</span>
        {rec.depth_at_ask !== null && <span>depth {rec.depth_at_ask.toFixed(0)}</span>}
        <span className="ml-auto">cfg v{rec.strategy_config_version}</span>
      </div>

      {suppressed && rec.suppressed_reason && (
        <div className="mt-3 rounded-lg border border-accent/40 bg-accent-soft px-3 py-2">
          <span className="font-mono text-xs text-accent">
            {rec.suppressed_reason}
          </span>
        </div>
      )}
    </article>
  );
}

function Figure({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative";
}) {
  const colour =
    tone === "positive"
      ? "text-positive"
      : tone === "negative"
        ? "text-negative"
        : "text-foreground";
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div className={`tabular mt-1 text-xl font-bold tracking-tight ${colour}`}>
        {value}
      </div>
    </div>
  );
}
