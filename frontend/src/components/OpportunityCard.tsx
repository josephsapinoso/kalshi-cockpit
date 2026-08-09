import type { Recommendation } from "@/lib/api";
import { formatAge, formatDuration, formatKickoff, freshness } from "@/lib/api";

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
  live = false,
  direction,
  quoteLimitMs = MAX_QUOTE_AGE_MS,
  oddsLimitMs = MAX_ODDS_AGE_MS,
}: {
  rec: Recommendation;
  suppressed?: boolean;
  expired?: boolean;
  /** This row's price arrived over the live feed rather than from the record. */
  live?: boolean;
  /** Which way the ask last moved, for a non-colour cue alongside the flash. */
  direction?: "up" | "down";
  quoteLimitMs?: number;
  oddsLimitMs?: number;
}) {
  const quoteAge = rec.quote_age_now_ms ?? rec.kalshi_quote_age_ms;
  const oddsAge = rec.odds_age_now_ms ?? rec.odds_age_ms;
  const band = freshness(quoteAge, quoteLimitMs);
  const positive = rec.edge_cents > 0;
  // A stale quote is no longer what makes a row unbettable. The order endpoint
  // re-reads the Kalshi price inside the request, so what a stale quote means
  // is that the ask, size and cost below are a memory -- and the order will be
  // priced and sized against whatever comes back instead.
  const priceStale = rec.price_is_current === false;

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

      {/* The comparison that decides the bet, given the most visual weight.
          Two columns until the card is wide enough for three, and the edge
          spans the full width below them -- which reads as the conclusion of
          the two prices above it rather than as a third price.

          Three columns at 320px put "CONSENSUS" in a 69px cell when the word
          needs 86, and `grid-cols-N` is `repeat(N, minmax(0, 1fr))`, so the
          column shrank below its own content instead of widening the grid.
          Nothing overflowed: the label simply painted over the one beside it
          and the Board read "CONSENSUSKALSHI". `scrollWidth` was identical to
          a correct layout's throughout, which is why every check passed.
          The breakpoint is `lg`, not `sm`, and that is measured rather than
          chosen: the Board goes two-up at `sm`, so a card at 640px is *
          narrower* than one at 430px and three columns overlap again there. */}
      <div className="mt-5 grid grid-cols-2 gap-3 border-t pt-4 lg:grid-cols-3">
        {/* A percentage, not a price. `fair_display` renders the same number
            as `53.8c`, and it sat here immediately left of the real ask at the
            same type size -- the one place a left-to-right scan reads the
            wrong number as what you pay. The unit is the whole fix: 53.8% and
            50.3c cannot be confused for each other the way 53.8c and 50.3c
            can. */}
        <Figure label="Consensus fair" value={rec.fair_percent_display} />
        <Figure
          // The arrow carries the direction as well as the colour flash. Roughly
          // one man in twelve cannot separate the two hues, and a ticker whose
          // only signal is red-versus-green tells them nothing.
          label={live ? "Kalshi asks · live" : "Kalshi asks"}
          value={
            direction
              ? `${rec.ask_display} ${direction === "up" ? "▲" : "▼"}`
              : rec.ask_display
          }
        />
        <Figure
          label="Edge, net of fees"
          value={`${positive ? "+" : ""}${rec.edge_cents.toFixed(1)}c`}
          tone={positive ? "positive" : "negative"}
          className="col-span-2 lg:col-span-1"
        />
      </div>

      {/* The size is what makes an expired row dangerous to render plainly:
          "Buy 15" beside a price the server will refuse. Struck through and
          labelled rather than hidden -- the row is still evidence.

          A *stale-priced* row is not struck through, because it is still
          bettable. It is dimmed instead, and the note below says the numbers
          will be re-derived. Striking it through would repeat the mistake this
          card was built to fix, one state over: telling the reader they cannot
          have something the server will sell them. */}
      {rec.suggested_contracts > 0 && (
        <div
          className={`mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t pt-4 ${
            expired
              ? "line-through decoration-1 opacity-60"
              : priceStale
                ? "opacity-70"
                : ""
          }`}
        >
          <Figure label="Buy" value={`${rec.suggested_contracts}`} />
          {/* The headline figure is the fee-inclusive one, and the stake and
              the fee move below it into the small print.
              `COST` used to be the stake alone with `FEE` beside it and no
              total anywhere on the card -- an understatement of 3.6% at 50c
              and 10% at 10c, against 0.38 points of total headroom. Both
              numbers come off the payload; nothing here adds them. */}
          <Figure
            label="Total cost"
            value={`$${rec.total_cost_dollars.toFixed(2)}`}
          />
          <Figure
            label="Expected"
            value={`${rec.ev_net_dollars >= 0 ? "+" : ""}$${rec.ev_net_dollars.toFixed(2)}`}
            tone={rec.ev_net_dollars >= 0 ? "positive" : "negative"}
          />
          {/* What happens when it is wrong, which nothing on this card said.
              One standard deviation of the position, computed on the server
              from the same fair probability the edge came from. */}
          <Figure label="Swing, 1 SD" value={`$${rec.sd_dollars.toFixed(2)}`} />
        </div>
      )}

      {rec.suggested_contracts > 0 && (
        <p className="mt-2 text-xs leading-relaxed text-muted">
          <span className="font-mono">${rec.stake_dollars.toFixed(2)}</span> for
          the contracts and{" "}
          <span className="font-mono">${rec.fee_predicted.toFixed(2)}</span> in
          fees. All of it is lost if this settles the other way.
          {rec.losing_run_probability !== null && (
            <>
              {" "}
              The swing is{" "}
              <span className="font-mono">
                {(rec.sd_dollars / Math.max(1e-9, Math.abs(rec.ev_net_dollars))).toFixed(0)}
              </span>
              × the expected value, so {rec.losing_run_bets} bets this shape end
              down{" "}
              <span className="font-mono">
                {Math.round(rec.losing_run_probability * 100)}%
              </span>{" "}
              of the time — with the edge completely real.
            </>
          )}
        </p>
      )}

      <p className="mt-4 text-sm leading-relaxed text-muted">{rec.reason_text}</p>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-3 font-mono text-xs text-muted">
        {/* "re-checked" rather than "quote" once a quote pass has re-derived
            this row: the number is then the age of the last confirmation, not
            of the original observation, and those are different claims. */}
        <span className={`freshness-${band}`}>
          {live
            ? "streaming"
            : rec.freshness_confirmed
              ? "re-checked"
              : "quote"}{" "}
          {formatAge(quoteAge)}
        </span>
        <span>books {formatAge(oddsAge)}</span>
        {rec.depth_at_ask !== null && <span>depth {rec.depth_at_ask.toFixed(0)}</span>}
        <span className="ml-auto">cfg v{rec.strategy_config_version}</span>
      </div>

      {expired && (
        <div className="mt-3 rounded-lg border px-3 py-2 text-xs leading-relaxed text-muted">
          {/* One cause now, and it is the one nothing on this page can fix.
              This said "the quote" unconditionally when both clocks advanced
              together, then named whichever had run out. Neither survives the
              order-time refresh: a stale quote no longer expires anything, so
              a row here has outlived its sportsbook consensus, and only a
              credit brings that back. */}
          Not bettable now — the sportsbook consensus behind it is{" "}
          <span className="font-mono">{formatDuration(oddsAge)}</span> old, past
          the{" "}
          {/* Minutes, not "900s": a reader should not have to convert units to
              see how far past a limit something is. */}
          <span className="font-mono">
            {Math.round(oddsLimitMs / 60_000)}m
          </span>{" "}
          limit, and nothing but one of the day&apos;s odds credits refreshes
          it. The order endpoint refuses it independently of this page.
        </div>
      )}

      {!expired && !suppressed && priceStale && (
        <div className="mt-3 rounded-lg border px-3 py-2 text-xs leading-relaxed text-muted">
          {/* Still bettable, and the numbers above are a memory. Saying so is
              the whole point: the alternative is a card that reads as a live
              quote and an order that comes back at a different price and size,
              which looks like the server disagreeing with the page. */}
          Still bettable — but this price was read{" "}
          <span className="font-mono">{formatAge(quoteAge)}</span>, past the{" "}
          <span className="font-mono">
            {Math.round(quoteLimitMs / 1000)}s
          </span>{" "}
          quote limit. Ordering re-reads Kalshi first and sizes against
          whatever it says then, so expect the ask, the size and the cost above
          to move.
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
  className,
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative";
  /** Grid placement, for the one figure that spans its row. */
  className?: string;
}) {
  const colour =
    tone === "positive"
      ? "text-positive"
      : tone === "negative"
        ? "text-negative"
        : "text-foreground";
  return (
    <div className={className}>
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div className={`tabular mt-1 text-xl font-bold tracking-tight ${colour}`}>
        {value}
      </div>
    </div>
  );
}
