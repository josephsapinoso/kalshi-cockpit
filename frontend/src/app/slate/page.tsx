import {
  DISPLAY_TIME_ZONE,
  fetchSignal,
  fetchSlate,
  fetchWindow,
} from "@/lib/api";
import type {
  ActionableWindow,
  Signal,
  Slate,
  SlateRowData,
} from "@/lib/api";
import { EDGE_TONE_CLASS, EDGE_TONE_MARK, edgeTone } from "@/lib/api";
import Link from "next/link";

import CrewBubble from "@/components/CrewBubble";
import Term from "@/components/Term";
import RefreshOddsPanel from "@/components/RefreshOddsPanel";
import SignalStrip from "@/components/SignalStrip";

export const dynamic = "force-dynamic";

/**
 * The whole slate, with edge as a column rather than a gate.
 *
 * The Board splits tonight on one question — did this clear the fee against a
 * devigged sharp consensus? — and the answer has been "no" on every row this
 * instance has ever written. ADR 0021 records that refutation; its §7.2 records
 * the most plausible reason, which is that the consensus is anchored on
 * `SHARP_BOOKS`, so the comparison is Kalshi against the only references
 * plausibly as sharp as Kalshi. A screen that shows only that verdict cannot
 * show anything else about a night's games.
 *
 * The `sharp-bettor` review of 2026-08-09 led with exactly this — *"edge versus
 * fee is being used as a filter where it should be a sort"* — and records Joe
 * making the same point independently that day. This is that screen.
 *
 * **Nothing here is a pick.** Every column is a fact already bought and stored,
 * none has been scored against an outcome, and the server combines them into
 * nothing. There is no composite, no rating, and no ordering by anything but
 * kickoff — because a ranking *is* a weighting, and a weighting of unscored
 * factors is a model that would need its own ADR and a pre-registration.
 *
 * **Nothing here is tappable into an order.** Same reasoning as `SlateRow`: a
 * screen that opened a ticket would suggest these factors bear on what is
 * bettable. They do not. `POST /api/orders` re-derives sizing, staleness and
 * risk server-side and does not read this route at all.
 */

export default async function SlatePage() {
  let data: Slate;
  // Allowed to fail on its own, as on the Board. `beta` is context for the
  // rows and not a precondition of them, and `SignalStrip` renders nothing
  // rather than a placeholder that could be misread as a measured zero.
  let signal: Signal | null = null;
  // Same treatment: the timetable is context for the refresh panel, never a
  // precondition of the slate.
  let actionable: ActionableWindow | null = null;
  try {
    data = await fetchSlate();
    signal = await fetchSignal().catch(() => null);
    actionable = await fetchWindow().catch(() => null);
  } catch {
    return (
      <Shell>
        <h1 className="text-2xl font-extrabold tracking-tight">Slate</h1>
        <p className="mt-4 text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  const { rows, counts, slate } = data;

  return (
    <Shell>
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Slate</h1>
        <p className="mt-2 max-w-prose text-sm text-muted">
          Everything on the record for tonight, with the edge as one column.
          {/* The sentence that stops every other column reading as a signal.
              Taken from the payload rather than written here, so the server and
              the screen cannot come to disagree about what this page claims. */}{" "}
          {data.note}
        </p>
      </header>

      {/* **Two book counts, and they mean different things.** The distribution
          spans every usable book; `fair_prices.book_count` is what survived the
          sharp anchoring. Where those differ, the gap *is* ADR 0021 §7.2 — the
          consensus the edge was computed against is narrower than the market. */}
      <dl className="mt-8 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        <Stat label="On the slate" value={counts.returned} />
        <Stat label="Bettable" value={counts.surfaced} />
        <Stat label="With book spread" value={counts.with_book_distribution} />
        <Stat label="Actionable, ever" value={slate.actionable_total} />
      </dl>

      {/* Placed above the rows, not below them. A slate greyed out by the
          clock is unreadable until this is used, so it has to be visible
          without scrolling past the thing it fixes. */}
      <RefreshOddsPanel actionable={actionable} />

      {!slate.is_current && slate.anchor_ms !== null && (
        <p className="mt-6 max-w-[65ch] rounded-lg border border-accent-2/70 bg-card p-3 text-sm text-accent-2">
          This is the last slate recorded, not a current one. The recorder has
          not decided anything for{" "}
          {Math.round((slate.age_ms ?? 0) / 60_000)} minutes.
        </p>
      )}

      {/* Above the rows, because it is what the edge column is worth. The
          header sentence already stops the other columns reading as signals;
          this one says what happened when the edge column itself was measured
          against Kalshi's own close. */}
      <div className="mt-6">
        <SignalStrip signal={signal} now={Date.now()} />
      </div>

      {rows.length === 0 ? (
        <p className="mt-8 max-w-[65ch] text-muted">
          Nothing recorded in the current window. An empty slate is a real state
          — it is not the same as every candidate being refused.
        </p>
      ) : (
        <ul className="mt-8 divide-y divide-border">
          {rows.map((row) => (
            <li key={row.id}>
              <Row
                row={row}
                driftWindowMs={data.drift_window_ms}
                maxQuoteAgeMs={data.staleness.max_kalshi_quote_age_s * 1000}
              />
            </li>
          ))}
        </ul>
      )}

      {slate.truncated && (
        <p className="mt-6 max-w-[65ch] text-xs text-muted">
          {slate.in_window} rows are in the window and {slate.returned} are shown
          {slate.off_basis > 0
            ? `; ${slate.off_basis} were dropped by the second freshness reading`
            : ""}
          .
        </p>
      )}

      <footer className="mt-10 max-w-[65ch] space-y-3 border-t border-border pt-6 text-xs text-muted">
        <p>
          <strong className="text-foreground">
            Where Kalshi sits is measured against you.
          </strong>{" "}
          Kalshi&rsquo;s number is the <em>ask</em> — the price that would leave
          your account, carrying half the spread. Each book&rsquo;s number is a
          devigged fair value with the margin removed. So a book looks cheaper
          than Kalshi by about half a spread even where the two agree exactly,
          and &ldquo;books under&rdquo; over-counts. That bias is deliberate: it
          cannot manufacture the reading that Kalshi is the sharp side.
        </p>
        <p>
          <strong className="text-foreground">The books do not move here.</strong>{" "}
          A fixture is swept once or twice a day, so there is no book-side line
          movement to show — two samples cannot tell a move from the absence of
          one. Drift is Kalshi&rsquo;s own price, which is quoted every few
          seconds.
        </p>
        <p>
          None of these factors has been scored against an outcome. The
          scoreboard is still closing-line value against Kalshi&rsquo;s own
          close, and none of this is that yet.
        </p>
      </footer>
    </Shell>
  );
}

/**
 * One line per row, at phone width.
 *
 * The `sharp-bettor` review measured the Board at one card per screen at 390px
 * and called it the worst thing about the product: comparison across the slate
 * is the job, and you cannot compare two things you cannot see at once.
 */
function Row({
  row,
  driftWindowMs,
  maxQuoteAgeMs,
}: {
  row: SlateRowData;
  driftWindowMs: number;
  maxQuoteAgeMs: number;
}) {
  const tone = edgeTone(row);

  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3 xl:grid xl:grid-cols-[3rem_minmax(0,1fr)_5.5rem_5rem_8rem_6.5rem_11rem_6rem_7rem_6.5rem_2.5rem] xl:gap-x-4 xl:items-baseline">
      <span className="tabular w-12 shrink-0 font-mono text-xs text-muted">
        {kickoff(row.commence_ms)}
      </span>
      {/* The name opens the market's price-history chart. A plain link,
          not a button: history is safe to browse, and the chart page says
          itself that the tradeable number is the ask on this row. */}
      <Link
        href={`/market/${encodeURIComponent(row.ticker)}`}
        className="min-w-0 font-semibold tracking-tight hover:underline"
      >
        {row.team ?? row.ticker}
      </Link>
      <span className="tabular text-sm text-muted">
        {row.ask_display} <Term k="ask">ask</Term>
      </span>

      <span className={`tabular text-sm font-semibold ${EDGE_TONE_CLASS[tone]}`}>
        {EDGE_TONE_MARK[tone]}
        {row.edge_cents > 0 ? "+" : ""}
        {row.edge_cents.toFixed(1)}c
      </span>

      <Books row={row} />
      <Drift tenths={row.kalshi_drift_tenths} windowMs={driftWindowMs} />
      <Capacity row={row} />
      <QuoteAge ageMs={row.quote_age_now_ms} maxMs={maxQuoteAgeMs} />
      {/* xl-only, like the CrewBubble below: two more wrapped fragments per
          row would cost the phone a line each, and the phone row already
          carries the suppression code in full. */}
      <span className="hidden xl:inline">
        <Anchor anchored={row.anchored_on_sharp} />
      </span>
      <span className="hidden xl:inline">
        <Width width={row.market_width} edgeCents={row.edge_cents} />
      </span>

      {/* **Desktop only, and nothing is lost by that.** The bubble opens on
          hover, which a phone does not have — and at 390px it wrapped onto a
          line of its own, so eleven rows paid eleven lines for an affordance
          that could not be used. Every fact inside it is already a column on
          this row: the Skeptic reads back `suppressed_reason`, which renders
          below in full. */}
      <span className="ml-auto hidden shrink-0 sm:inline-flex">
        <CrewBubble row={row} />
      </span>

      {row.suppressed_reason && (
        <span className="w-full break-words font-mono text-xs text-accent xl:col-span-full">
          {row.suppressed_reason}
        </span>
      )}
    </div>
  );
}

/**
 * Kalshi&rsquo;s place in the book distribution.
 *
 * `null` renders as an em dash and never as a zero. &ldquo;No book was under
 * Kalshi&rdquo; and &ldquo;no book price was stored&rdquo; are different facts
 * and would otherwise render identically — this repo&rsquo;s recurring *zero
 * that means no measurement*.
 */
function Books({ row }: { row: SlateRowData }) {
  const books = row.books;
  if (!books || books.book_count === 0) {
    return (
      <span className="tabular text-xs text-muted" title="No usable book prices stored for this fixture.">
        books —
      </span>
    );
  }
  return (
    <span
      className="tabular text-xs text-muted"
      title={`${books.books_below} of ${books.book_count} usable books price this side below Kalshi's ask. Book figures are devigged; Kalshi's is an ask.`}
    >
      {books.books_below}/{books.book_count} books under
    </span>
  );
}

/** "12s" / "3m" / "2h" -- rounded to the unit a glance can use. */
function formatAge(ms: number): string {
  if (ms < 90_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 90 * 60_000) return `${Math.round(ms / 60_000)}m`;
  return `${Math.round(ms / 3_600_000)}h`;
}

/**
 * How old this row's Kalshi quote is, right now.
 *
 * The ask column reads as "the price" and on a finished evening it is hours
 * of history; the recorded-at ages never move, so without this chip a row
 * from three hours ago still looks current. Amber past the server's own
 * 30-second freshness limit -- the same clock the order endpoint enforces,
 * so the chip and a refusal can never disagree about what "stale" means.
 * `null` renders as an em dash, never as zero seconds: "no reading" and
 * "read just now" are different facts.
 */
function QuoteAge({
  ageMs,
  maxMs,
}: {
  ageMs: number | null | undefined;
  maxMs: number;
}) {
  if (ageMs === null || ageMs === undefined || ageMs < 0) {
    return (
      <span className="tabular text-xs text-muted">
        <Term k="quote_age">quote</Term> —
      </span>
    );
  }
  const stale = ageMs > maxMs;
  return (
    <span
      className={`tabular text-xs ${stale ? "text-accent" : "text-muted"}`}
    >
      <Term k="quote_age">quote</Term> {formatAge(ageMs)}
    </span>
  );
}

function Drift({
  tenths,
  windowMs,
}: {
  tenths: number | null;
  windowMs: number;
}) {
  if (tenths === null) {
    return (
      <span
        className="tabular text-xs text-muted"
        title="Fewer than two Kalshi quotes stored in the window. Not the same as the price holding steady."
      >
        drift —
      </span>
    );
  }
  const minutes = Math.round(windowMs / 60_000);
  return (
    <span
      className="tabular text-xs text-muted"
      title={`Change in the price you would pay over the last ${minutes} minutes.`}
    >
      {tenths > 0 ? "+" : ""}
      {(tenths / 10).toFixed(1)}c/{minutes}m
    </span>
  );
}

/**
 * What could actually be got down.
 *
 * `sharp-bettor` calls capacity the binding constraint on a winning bettor, and
 * no screen in this product has ever shown it. `depth_at_ask` is contracts
 * available at the price on the row; volume and open interest are the market.
 */
function Capacity({ row }: { row: SlateRowData }) {
  const depth = row.depth_at_ask;
  const oi = row.open_interest;
  if (depth === null && oi === null) {
    return <span className="tabular text-xs text-muted">size —</span>;
  }
  return (
    <span
      className="tabular text-xs text-muted"
      title="Contracts resting at this ask, and the market's open interest. Availability is not fillability — both are stored quotes."
    >
      {depth === null ? "—" : Math.round(depth)} @ask
      {oi === null ? "" : ` · ${Math.round(oi).toLocaleString()} OI`}
    </span>
  );
}

/**
 * Whether sharp anchoring actually bound on this row.
 *
 * The most consequential unrendered field in the product until now: the devig
 * is `selected = sharp or usable`, so `false` means **no sharp book quoted**
 * and the fair value silently fell back to the full soft-book set — a wide
 * consensus wearing a sharp consensus's name. Every actionable row in the
 * whole record (all three of them) has this at `false`, which is why it gets
 * the warning ink rather than a muted footnote. `null` means the join missed
 * — an em dash, never a default.
 */
function Anchor({ anchored }: { anchored: boolean | null | undefined }) {
  if (anchored === null || anchored === undefined) {
    return <span className="tabular text-xs text-muted">anchor —</span>;
  }
  if (anchored) {
    return (
      <span
        className="tabular text-xs text-muted"
        title="A sharp book quoted this market; the consensus is anchored on it."
      >
        sharp-anchored
      </span>
    );
  }
  return (
    <span
      className="text-xs font-semibold text-accent-2"
      title="No sharp book quoted this market, so the fair value fell back to the full soft-book set. The edge is measured against a wide consensus, not a sharp one."
    >
      soft fallback
    </span>
  );
}

/**
 * The books' own disagreement, beside the edge it bounds.
 *
 * In points, same unit as the edge, so the comparison is one glance: a width
 * larger than the edge means the books disagree with each other by more than
 * they disagree with Kalshi, and the edge is inside the consensus's error
 * bar. Warning ink exactly then — arithmetic, not judgement. `null` renders
 * as an em dash: one book cannot disagree with itself, and `0.0` is a real
 * measured value two identical quotes legitimately produce.
 */
function Width({
  width,
  edgeCents,
}: {
  width: number | null | undefined;
  edgeCents: number;
}) {
  if (width === null || width === undefined) {
    return <span className="tabular text-xs text-muted">width —</span>;
  }
  const points = width * 100;
  const drowns = points > Math.abs(edgeCents);
  return (
    <span
      className={`tabular text-xs ${drowns ? "text-accent-2" : "text-muted"}`}
      title={`The devigged books disagree with each other by ${points.toFixed(1)} points on this outcome.${drowns ? " That exceeds the edge, so the edge is inside the consensus's own error bar." : ""}`}
    >
      width {points.toFixed(1)}c
    </span>
  );
}


/**
 * Pacific, like every other human-facing clock here. See `DISPLAY_TIME_ZONE`.
 *
 * This rendered UTC until 2026-08-16, on the argument that "every other clock
 * on this product is UTC and mixing them is how a three-hour offset went
 * unnoticed for eleven build steps". The lesson was real and the conclusion was
 * too broad: that offset hid in *stored and compared* values -- Kalshi's
 * `occurrence_datetime` against the sportsbook's `commence_ms` -- and no
 * display format could have caused or prevented it. What the UTC rendering did
 * cause was a first pitch printed as 22:41 to a reader in California, who has
 * to subtract seven in his head every time.
 *
 * 24-hour, unlike `formatClock`, because this sits in a dense table where a
 * fixed-width column is worth more than an am/pm that a kickoff list does not
 * need.
 */
function kickoff(ms: number | null): string {
  if (ms === null) return "--:--";
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function Shell({ children }: { children: React.ReactNode }) {
  /* `max-w-3xl` below xl — the phone-first page, unchanged. From xl the slate
     is the screen that earns the desktop tier most: nine facts per row that
     wrap into ragged lines at 768px become one aligned line each. The prose
     on this page keeps its own `ch`/`max-w-prose` caps — the shell widens the
     data, never the sentences (ADR 0047). */
  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-12 sm:py-16 xl:max-w-[84rem] xl:px-8 2xl:max-w-[96rem]">
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  /* No accent variant, for the Board's reason: `--accent` is byte-identical
     to `--negative` in every theme block, so an emphasised count rendered as
     a loss. A count is a fact, not a verdict. */
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div className="tabular mt-1 text-2xl font-semibold tracking-tight">
        {value}
      </div>
    </div>
  );
}
