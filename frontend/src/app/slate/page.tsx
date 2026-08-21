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
import { glossSentence } from "@/lib/suppressionGloss";
import Link from "next/link";

import CrewBubble from "@/components/CrewBubble";
import DispersionStrip from "@/components/DispersionStrip";
import Term from "@/components/Term";
import RefreshOddsPanel from "@/components/RefreshOddsPanel";
import SignalStrip from "@/components/SignalStrip";
import TonightStrip from "@/components/TonightStrip";

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

      {/* His actual money, where he decides (fleet convening item 5; A7 rules
          this outside the study embargo). **Cash and open positions render
          separately and are never summed** — a sum is a signed P&L, and a
          signed P&L on the deciding screen is the chase trigger the tilt
          review refused. The only denominator on this line is the daily-loss
          cap Joe set himself; the $100 study ceiling must not appear here,
          because "cash against $100" reads as budget remaining. */}
      {data.money && (
        <p className="mt-4 text-sm">
          <span className="font-semibold tabular">
            {data.money.cash_tenths === null
              ? "Cash unread"
              : `$${(data.money.cash_tenths / 1000).toFixed(2)} cash`}
          </span>
          {data.money.open_positions_tenths !== null && (
            <span className="tabular text-muted">
              {" "}
              · ${(data.money.open_positions_tenths / 1000).toFixed(2)} sitting
              in open positions
            </span>
          )}
          {data.money.daily_line_dollars !== null && (
            <span className="text-muted">
              {" "}
              · your daily-loss line is $
              {data.money.daily_line_dollars.toFixed(2)}
            </span>
          )}
        </p>
      )}

      {/* Tonight's commitment + the "not tonight" note, beside the money line
          on the deciding screen (2026-08-21 ruling). Unsigned by contract —
          the signed record is /bets, after settlement. */}
      {data.tonight && <TonightStrip tonight={data.tonight} />}

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
                maxOddsAgeMs={data.staleness.max_odds_age_s * 1000}
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
  maxOddsAgeMs,
}: {
  row: SlateRowData;
  driftWindowMs: number;
  maxQuoteAgeMs: number;
  maxOddsAgeMs: number;
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

      {/* The number that makes the price a decision (fleet convening item 6):
          how often this bet must win, fee included, computed by the same
          `breakeven_win_rate` the order path uses. **The consensus fair value
          is deliberately NOT on this row** — `edge_tenths` is exactly
          1000 × (fair − break-even), so rendering both hands the reader the
          measured-negative edge by subtraction. The edge column stands; the
          fair number does not co-render. */}
      {row.breakeven_win_rate !== null && (
        <span className="tabular text-sm text-muted">
          {(row.breakeven_win_rate * 100).toFixed(1)}%{" "}
          <Term k="breakeven">to break even</Term>
        </span>
      )}

      <span className={`tabular text-sm font-semibold ${EDGE_TONE_CLASS[tone]}`}>
        {EDGE_TONE_MARK[tone]}
        {row.edge_cents > 0 ? "+" : ""}
        {row.edge_cents.toFixed(1)}c
      </span>

      <Books row={row} />
      <Drift tenths={row.kalshi_drift_tenths} windowMs={driftWindowMs} />
      <Capacity row={row} />
      <QuoteAge ageMs={row.quote_age_now_ms} maxMs={maxQuoteAgeMs} />
      {/* On every width since 2026-08-20 (fleet convening item 4). This is
          the most consequential caveat in the product — all three actionable
          rows ever written were soft fallbacks — and it was desktop-only on a
          tool operated from a phone. It costs the phone row a short fragment;
          that price was the finding, not an oversight to re-hide. */}
      <Anchor anchored={row.anchored_on_sharp} />
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

      {/* The status line: the single most urgent clock-or-tape fact on this
          row, in words, on every width (fleet convening item 4). Priority is
          registered in the convening record: staleness, then old consensus,
          then the tape — and the suppression code below is the bar, which
          keeps the fourth rung where it already renders. **This is a
          selection, not a composite** (ADR 0021 §9): one line voices one
          fact from one source; choosing WHICH fact by fixed priority weighs
          nothing against anything. */}
      <StatusLine
        row={row}
        maxQuoteAgeMs={maxQuoteAgeMs}
        maxOddsAgeMs={maxOddsAgeMs}
      />

      {row.suppressed_reason && (
        <span className="w-full break-words font-mono text-xs text-accent xl:col-span-full">
          {row.suppressed_reason}
        </span>
      )}

      {/* Plain English under the code, never instead of it. The code above is
          the engine's own name for the rule and is what `/rejections` groups
          by; this is a caption on it, for a reader who has not memorised
          twelve identifiers. Absent when the server sent a code this build
          does not know — see `frontend/src/lib/suppressionGloss.ts`. */}
      {glossSentence(row.suppressed_reason) && (
        <span className="w-full break-words text-xs leading-snug text-muted xl:col-span-full">
          {glossSentence(row.suppressed_reason)}
        </span>
      )}

      {/* **Every width, including the phone.** This shipped `xl:`-only on
          2026-08-19 under ADR 0047's rule that everything below 1280px stays
          byte-identical, with the cost of overriding that stated and the
          decision handed to Joe. He took it the same day: he reads this screen
          on a phone, and an explanation that only exists on a monitor explains
          nothing to the person who owns the account. ADR 0052.

          The rule it overrides was about *density* -- not adding rows of
          columns to a hand-held screen -- and this is not a column. It is the
          one thing on the row that says where its own number came from: this
          line reads `fair` once, and that number is the lowest of four devig
          readings averaged over an anchored subset of the books. Three
          choices, none of them on any screen before this. */}
      <span className="w-full xl:col-span-full">
        <DispersionStrip
          books={row.books}
          methods={row}
          kalshiProbability={
            typeof row.ask_tenths === "number" ? row.ask_tenths / 1000 : null
          }
          anchoredBookCount={row.book_count ?? null}
        />
      </span>
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

/**
 * One warning in words, or nothing.
 *
 * The columns above carry every number; this line exists because a phone
 * reader meeting a greyed-out row needs the *reason* without decoding four
 * ages. It voices exactly one fact, by fixed priority:
 *
 *   1. the Kalshi quote is past the staleness limit  — the ask may be gone
 *   2. the consensus is past the odds limit          — the row cannot be
 *      actionable until the books are re-bought (the button above the list)
 *   3. the tape has moved ≥ 1.0c in the drift window — the price being
 *      compared is not the price that was compared
 *
 * Rendering nothing is the fourth state and it is deliberate: a status line
 * that always says something becomes furniture, and the suppression code
 * below already voices the bar. The 1.0c drift threshold is a display choice
 * (when to speak, never what to compute) — the Drift column shows the exact
 * figure at any size.
 *
 * `odds_age_now_ms` is optional on the wire; absent means the server did not
 * compute it, and no clock claim is made from a missing clock.
 */
function StatusLine({
  row,
  maxQuoteAgeMs,
  maxOddsAgeMs,
}: {
  row: SlateRowData;
  maxQuoteAgeMs: number;
  maxOddsAgeMs: number;
}) {
  let line: string | null = null;
  if (
    row.quote_age_now_ms !== null &&
    row.quote_age_now_ms !== undefined &&
    row.quote_age_now_ms > maxQuoteAgeMs
  ) {
    line = `Kalshi quote is ${Math.round((row.quote_age_now_ms ?? 0) / 1000)}s old — past the ${Math.round(maxQuoteAgeMs / 1000)}s limit, so the ask shown may already be gone.`;
  } else if (
    row.odds_age_now_ms !== null &&
    row.odds_age_now_ms !== undefined &&
    row.odds_age_now_ms > maxOddsAgeMs
  ) {
    line = `Books last read ${Math.round((row.odds_age_now_ms ?? 0) / 60_000)} min ago — past the ${Math.round(maxOddsAgeMs / 60_000)} min limit. Not actionable until the odds are refreshed.`;
  } else if (
    row.kalshi_drift_tenths !== null &&
    Math.abs(row.kalshi_drift_tenths) >= 10
  ) {
    const cents = row.kalshi_drift_tenths / 10;
    line = `Kalshi has moved ${cents > 0 ? "+" : ""}${cents.toFixed(1)}c since the books were read — the edge shown compares prices from different moments.`;
  }
  if (line === null) {
    return null;
  }
  return (
    <span className="w-full break-words text-xs leading-snug text-accent-2 xl:col-span-full">
      {line}
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
