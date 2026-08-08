import type { Recommendation } from "@/lib/api";
import { formatAge, formatKickoff, freshness } from "@/lib/api";

const MAX_QUOTE_AGE_MS = 30_000;
const MAX_ODDS_AGE_MS = 900_000;

/**
 * One opportunity, as a card.
 *
 * Card rather than table row on purpose: this is used on a phone, and a
 * seven-column table at 390px is unreadable. The card puts the one comparison
 * that matters -- fair versus what you pay -- at the top in large type, and
 * relegates the machinery below it.
 *
 * **Ages shown are the current ones where the server sent them.** The stored
 * `kalshi_quote_age_ms` is the age at the moment the row was written and never
 * moves, so a three-hour-old row rendered from it reads "quote 3s ago" -- a
 * number that is true about the past and a lie about the page.
 */
export default function OpportunityCard({
  rec,
  suppressed = false,
  expired = false,
  quoteLimitMs = MAX_QUOTE_AGE_MS,
  oddsLimitMs = MAX_ODDS_AGE_MS,
}: {
  rec: Recommendation;
  suppressed?: boolean;
  expired?: boolean;
  quoteLimitMs?: number;
  oddsLimitMs?: number;
}) {
  const quoteAge = rec.quote_age_now_ms ?? rec.kalshi_quote_age_ms;
  const oddsAge = rec.odds_age_now_ms ?? rec.odds_age_ms;
  const band = freshness(quoteAge, quoteLimitMs);
  const positive = rec.edge_cents > 0;
  // Which of the two limits is what makes a row unbettable, and it is no longer
  // always the quote. A quote pass re-checks the Kalshi price every fifteen
  // seconds; nothing refreshes the sportsbook consensus but a credit.
  const quoteExpired = quoteAge > quoteLimitMs;

  return (
    <article
      className={`animate-in rounded-2xl border bg-card p-5 transition-all sm:p-6 ${
        suppressed || expired
          ? "opacity-70"
          : "hover:-translate-y-1 hover:border-accent"
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

      {/* The size is what makes an expired row dangerous to render plainly:
          "Buy 15" beside a price the server will refuse. Struck through and
          labelled rather than hidden -- the row is still evidence. */}
      {rec.suggested_contracts > 0 && (
        <div
          className={`mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t pt-4 ${
            expired ? "line-through decoration-1 opacity-60" : ""
          }`}
        >
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
        {/* "re-checked" rather than "quote" once a quote pass has re-derived
            this row: the number is then the age of the last confirmation, not
            of the original observation, and those are different claims. */}
        <span className={`freshness-${band}`}>
          {rec.freshness_confirmed ? "re-checked" : "quote"} {formatAge(quoteAge)}
        </span>
        <span>books {formatAge(oddsAge)}</span>
        {rec.depth_at_ask !== null && <span>depth {rec.depth_at_ask.toFixed(0)}</span>}
        <span className="ml-auto">cfg v{rec.strategy_config_version}</span>
      </div>

      {expired && (
        <div className="mt-3 rounded-lg border px-3 py-2 text-xs leading-relaxed text-muted">
          {/* Name the limit that actually failed. This used to say "the quote"
              unconditionally, which was true when both clocks advanced
              together. They do not any more: a quote pass re-checks the Kalshi
              price every fifteen seconds while the sportsbook consensus keeps
              ageing, so most expired rows now expire on the books -- and the
              old wording rendered "quote 3s, past the 30s limit", which is not
              a sentence a reader can act on. */}
          Not bettable now — the{" "}
          {quoteExpired ? "quote behind it" : "sportsbook consensus behind it"} is{" "}
          <span className="font-mono">
            {formatAge(quoteExpired ? quoteAge : oddsAge)}
          </span>
          , past the{" "}
          <span className="font-mono">
            {/* Seconds for the quote, minutes for the books. "28m ago, past the
                900s limit" makes the reader convert units to see how far past
                it is, on a page built to be read in a few seconds. */}
            {quoteExpired
              ? `${Math.round(quoteLimitMs / 1000)}s`
              : `${Math.round(oddsLimitMs / 60_000)}m`}
          </span>{" "}
          limit. The order endpoint refuses it independently of this page.
        </div>
      )}

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
