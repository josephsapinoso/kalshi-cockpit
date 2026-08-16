import { DISPLAY_TIME_ZONE, fetchSlate } from "@/lib/api";
import type { Slate, SlateRowData } from "@/lib/api";
import { EDGE_TONE_CLASS, EDGE_TONE_MARK, edgeTone } from "@/lib/api";
import CrewBubble from "@/components/CrewBubble";

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
  try {
    data = await fetchSlate();
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
        <Stat label="Bettable" value={counts.surfaced} accent />
        <Stat label="With book spread" value={counts.with_book_distribution} />
        <Stat
          label="Actionable, ever"
          value={slate.actionable_total}
          accent={slate.actionable_total > 0}
        />
      </dl>

      {!slate.is_current && slate.anchor_ms !== null && (
        <p className="mt-6 rounded-lg border border-accent-2/50 bg-card p-3 text-sm text-accent-2">
          This is the last slate recorded, not a current one. The recorder has
          not decided anything for{" "}
          {Math.round((slate.age_ms ?? 0) / 60_000)} minutes.
        </p>
      )}

      {rows.length === 0 ? (
        <p className="mt-8 text-muted">
          Nothing recorded in the current window. An empty slate is a real state
          — it is not the same as every candidate being refused.
        </p>
      ) : (
        <ul className="mt-8 divide-y divide-border">
          {rows.map((row) => (
            <li key={row.id}>
              <Row row={row} driftWindowMs={data.drift_window_ms} />
            </li>
          ))}
        </ul>
      )}

      {slate.truncated && (
        <p className="mt-6 text-xs text-muted">
          {slate.in_window} rows are in the window and {slate.returned} are shown
          {slate.off_basis > 0
            ? `; ${slate.off_basis} were dropped by the second freshness reading`
            : ""}
          .
        </p>
      )}

      <footer className="mt-10 space-y-3 border-t border-border pt-6 text-xs text-muted">
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
}: {
  row: SlateRowData;
  driftWindowMs: number;
}) {
  const tone = edgeTone(row);

  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3">
      <span className="tabular w-12 shrink-0 font-mono text-xs text-muted">
        {kickoff(row.commence_ms)}
      </span>
      <span className="min-w-0 font-semibold tracking-tight">
        {row.team ?? row.ticker}
      </span>
      <span className="tabular text-sm text-muted">{row.ask_display} ask</span>

      <span className={`tabular text-sm font-semibold ${EDGE_TONE_CLASS[tone]}`}>
        {EDGE_TONE_MARK[tone]}
        {row.edge_cents > 0 ? "+" : ""}
        {row.edge_cents.toFixed(1)}c
      </span>

      <Books row={row} />
      <Drift tenths={row.kalshi_drift_tenths} windowMs={driftWindowMs} />
      <Capacity row={row} />

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
        <span className="w-full break-words font-mono text-xs text-accent">
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
  return <div className="mx-auto max-w-3xl px-6 py-12 sm:py-16">{children}</div>;
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div
        className={`tabular mt-1 text-2xl font-extrabold tracking-tight ${
          accent ? "text-accent" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}
