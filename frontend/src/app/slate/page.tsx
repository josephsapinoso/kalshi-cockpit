import {
  DISPLAY_TIME_ZONE,
  fetchRefreshable,
  fetchSignal,
  fetchSlate,
  fetchWindow,
  formatClock,
} from "@/lib/api";
import type {
  ActionableWindow,
  Refreshable,
  Signal,
  Slate,
  SlateRowData,
} from "@/lib/api";
import { glossSentence } from "@/lib/suppressionGloss";
import {
  anAutomaticBuyIsComing,
  isStaleOddsReason,
  slateIsUnpricedByTheClock,
} from "@/lib/nextOddsWindow";
import { refreshIsUrgent } from "@/lib/refreshUrgency";
import Link from "next/link";

import CrewBubble from "@/components/CrewBubble";
import DispersionStrip from "@/components/DispersionStrip";
import ManualTicket from "@/components/ManualTicket";
import MarketSearch from "@/components/MarketSearch";
import LeagueTag from "@/components/LeagueTag";
import GoodChancePicks from "@/components/GoodChancePicks";
import Hint from "@/components/Hint";
import OpenPositions from "@/components/OpenPositions";
import Term from "@/components/Term";
import RefreshOddsPanel from "@/components/RefreshOddsPanel";
import RefreshWhenPriced from "@/components/RefreshWhenPriced";
import StaleOddsExit from "@/components/StaleOddsExit";
import SignalStrip from "@/components/SignalStrip";
import TonightStrip from "@/components/TonightStrip";

export const dynamic = "force-dynamic";

/**
 * The whole slate. The edge is not on it, since 2026-08-21.
 *
 * The point-estimate column (`+2.3c` with tone and mark) came off on the
 * partner's betting-desk ruling (docs/reviews/2026-08-21-items-2-3-ruling.md,
 * re-affirming the standing "strip the landing screen" item, under ADR 0062:
 * the edge-finder is a feature, not a determiner, and Joe's own words were
 * "I don't care about 1-2 cent diffs"). The Board (/board, one tap away) is
 * where the edge-finder lives and still renders it; this screen keeps the
 * facts a bettor transacts against -- ask, break-even, books, freshness --
 * and the record's own caveats.
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
 * **The rows are not picks.** Every column is a fact already bought and
 * stored, none has been scored against an outcome, and the server combines
 * them into nothing. The rows order by kickoff and nothing else.
 *
 * **The picks block above them IS a ranking, and ADR 0067 is why that is
 * allowed** (2026-08-23, Joe's direction: "I just want to see what are
 * good-chance picks"). It sorts on ONE stored, unscored column —
 * `fair_probability` — which is a sort, not a weighting; the line this
 * amends stays drawn where it was: any composite of two or more factors
 * remains forbidden (ADR 0021 §9), and fair% never shares a block with
 * break-even (the subtraction identity).
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
  // What a tap could buy, for the stale-count exit in the refusal
  // disclosure. `null` means the read failed and the disclosure says so in
  // words — never a button with an unnamed cost.
  let refreshable: Refreshable | null = null;
  try {
    data = await fetchSlate();
    signal = await fetchSignal().catch(() => null);
    actionable = await fetchWindow().catch(() => null);
    refreshable = await fetchRefreshable().catch(() => null);
  } catch {
    return (
      <Shell>
        <h1 className="text-2xl font-extrabold tracking-tight">Games</h1>
        <p className="mt-4 text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  const { rows, counts, slate } = data;

  return (
    <Shell>
      <header>
        {/* "Games", matching its own nav label since 2026-08-22 (A5): the
            nav said Games, the heading said Slate, and the footer used to
            say a third thing — one screen, one name. "Slate" survives as
            the route alias and the API vocabulary, which readers of code
            meet with the map in hand. */}
        <h1 className="text-2xl font-extrabold tracking-tight">Games</h1>
        <p className="mt-2 max-w-prose text-sm text-muted">
          Everything on the record for tonight — the facts you would transact
          against, not a verdict.
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
          review refused. Every figure below is a server-rendered display
          string (lib/api.ts's no-arithmetic rule) — including the caps,
          which the server derives from the observed balance at request
          time (ADR 0045). An unobserved balance renders its refusal in
          words; this block never silently renders nothing, which is
          exactly how the old "your daily-loss line is $X" fragment
          disappeared from live for a week. */}
      {data.money && (
        <div className="mt-4 space-y-1 text-sm">
          <p>
            <span className="font-semibold tabular">
              {data.money.cash_display === null
                ? "Cash unread"
                : `${data.money.cash_display} in the account.`}
            </span>
            {data.money.per_bet_cap_display !== null && (
              <span className="text-muted">
                {" "}
                Your cap is {data.money.per_bet_cap_display} a bet — under one
                contract on anything above {data.money.per_bet_cap_display}.
              </span>
            )}
          </p>
          {data.money.per_bet_cap_display !== null ? (
            <p className="text-xs text-muted">
              At most {data.money.exposure_cap_display} at risk at once; the
              day stops at {data.money.daily_line_display} down. One contract
              at 50c needs a {data.money.deposit_for_50c_display} balance to
              stay inside the cap.
            </p>
          ) : (
            <p className="text-xs text-accent-2">
              No caps can be derived —{" "}
              {data.money.caps_basis.refusal ?? "balance unobserved"}. One
              contract at 50c would need a{" "}
              {data.money.deposit_for_50c_display} balance to stay inside the
              cap.
            </p>
          )}
          {/* What is at risk right now (B3): a sibling of the money line,
              never summed with it. The component owns the refusal words. */}
          <OpenPositions block={data.open_positions} />
        </div>
      )}

      {/* Tonight's commitment + the "not tonight" note, beside the money line
          on the deciding screen (2026-08-21 ruling). Unsigned by contract —
          the signed record is /bets, after settlement. */}
      {data.tonight && <TonightStrip tonight={data.tonight} />}

      {/* Two stats, down from four (2026-08-22 review): the first game row
          sat ~1,700px from the top — below the fold on the phone AND the
          desktop — and "With book spread" / "Actionable, ever" are apparatus
          a bettor cannot act on tonight. On the slate + Bettable answer the
          two questions a glance actually asks: how many games, and did
          anything clear the bar. */}
      <dl className="mt-8 grid grid-cols-2 gap-x-6 gap-y-4">
        <Stat label="On the slate" value={counts.returned} />
        <Stat label="Bettable" value={counts.surfaced} />
      </dl>

      {/* The panel takes the top slot only when it can fix what the reader
          is about to misread — stale consensus, or a slate that is not
          current (lib/refreshUrgency.ts, node-tested). A fresh slate puts
          the games first and the panel below them: the 2026-08-22 review's
          ruling, superseding the unconditional "above the rows" placement.
          The urgency read and the rows' own staleness ink share the same
          odds-age limit, so the panel cannot jump above rows that all render
          fresh. */}
      {refreshIsUrgent(
        rows,
        data.staleness.max_odds_age_s * 1000,
        slate.is_current,
      ) && <RefreshOddsPanel actionable={actionable} />}

      {/* Who's likely to win tonight (ADR 0067) — above the rows, below the
          urgent-refresh slot, so a stale slate still leads with its fix. */}
      <GoodChancePicks picks={data.picks} />

      {/* The parlay desk (ADR 0070) sits one tap from the picks it is built
          from. A plain link, deliberately: no card preview, no percentage,
          no accent — the desk's own screen carries the caveats that make its
          numbers honest, and a teaser here would carry the numbers without
          them. */}
      {data.picks && data.picks.ranked.length > 0 && (
        <p className="mt-3 text-sm">
          <Link href="/parlays" className="font-semibold hover:underline">
            Parlay desk →
          </Link>{" "}
          <span className="text-muted">
            tonight&rsquo;s picks as combo cards, at fair value.
          </span>
        </p>
      )}

      {!slate.is_current && slate.anchor_ms !== null && (
        <p className="mt-6 max-w-[65ch] rounded-lg border border-accent-2/70 bg-card p-3 text-sm text-accent-2">
          This is the last slate recorded, not a current one. The recorder has
          not decided anything for{" "}
          {Math.round((slate.age_ms ?? 0) / 60_000)} minutes.
        </p>
      )}

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

      {/*
        Above the refusal disclosure, not inside it. `StaleOddsExit` lives in a
        collapsed `<details>`, and a page that re-renders itself while the only
        explanation is folded away is a page that moves for no stated reason.

        Gated on the whole screen being unpriced, never on `refreshIsUrgent` --
        that predicate is `some` and fires on one stale row, which is a working
        slate the reader is in the middle of. See `slateIsUnpricedByTheClock`.
      */}
      {actionable &&
        slateIsUnpricedByTheClock(
          rows,
          data.staleness.max_odds_age_s * 1000,
        ) && (
          <div className="mt-8 max-w-[65ch]">
            <RefreshWhenPriced
              renderedFresh={actionable.fixtures_fresh}
              automaticBuyIsComing={anAutomaticBuyIsComing(actionable)}
            />
          </div>
        )}

      <RefusalSummary
        rows={rows}
        actionable={actionable}
        refreshable={refreshable}
      />

      {/* Below the rows when nothing is stale — the same panel, demoted, so
          a fresh slate leads with games (2026-08-22 review). */}
      {!refreshIsUrgent(
        rows,
        data.staleness.max_odds_age_s * 1000,
        slate.is_current,
      ) && <RefreshOddsPanel actionable={actionable} />}

      {/* The way in to a market no row here carries — a prop ladder rung the
          recorder never priced, a series this instance does not walk.
          Closed, and below the rows: it reaches further than anything else
          on the screen, which is exactly why it does not sit open beside
          tonight's games. No new nav slot; `Nav.tsx` budgets six links and
          their order is load-bearing at 390px. */}
      <MarketSearch />

      {/* Below the rows since 2026-08-22 (it sat above them): what the
          edge-finder was worth when it was measured against Kalshi's own
          close. It stays on the page even though the edge column is gone —
          it is the reason the column is gone — but a measurement's
          post-mortem does not outrank tonight's games. */}
      <div className="mt-8">
        <SignalStrip signal={signal} now={Date.now()} />
      </div>

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
          your account, carrying half the spread. Each book&rsquo;s number is a{" "}
          <Term k="devig">devigged</Term> fair value with the margin removed. So
          a book looks cheaper
          than Kalshi by about half a spread even where the two agree exactly,
          and &ldquo;books under&rdquo; over-counts. That bias is deliberate: it
          cannot manufacture the reading that Kalshi is the sharp side.
        </p>
        {/* **The row shows two numbers whose difference is not profit, so the
            screen has to say so.** Added 2026-08-24 with the ask/fair swap
            (ADR 0071 §2.2). Under the desk's job — price transparency — the
            honest failure mode of putting a cost beside a worth is that a
            reader subtracts them and reads the remainder as money. Two things
            stand between that subtraction and the truth, and both belong
            here rather than on the row: the fee, and the fact that this
            project measured the remainder and it did not pay.

            No per-row figure, no sign, no colour. This is prose, and
            `breakeven_win_rate` deliberately does not appear on this page —
            fair beside break-even reconstitutes the edge exactly. */}
        <p>
          <strong className="text-foreground">
            The gap between those two numbers is not profit.
          </strong>{" "}
          A fee sits between them: pay 50c and the bet has to win about{" "}
          <Term k="breakeven">51.75%</Term> of the time before you are even, not
          50%. So a fair value a little above the ask is the normal state of a
          working market, not an opportunity. And this project spent months
          measuring whether the remainder pays after the fee —{" "}
          <Term k="clv">it does not</Term>, on every test it could run. The two
          numbers are here so you can see what you are paying for, which is a
          different thing from a reason to bet.
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
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3 xl:grid xl:grid-cols-[3rem_minmax(0,1fr)_5.5rem_5rem_8rem_6.5rem_11rem_6rem_7rem_6.5rem_2.5rem] xl:gap-x-4 xl:items-baseline">
      <span className="tabular w-12 shrink-0 font-mono text-xs text-muted">
        {kickoff(row.commence_ms)}
      </span>
      {/* The name opens the market's price-history chart. A plain link,
          not a button: history is safe to browse, and the chart page says
          itself that the tradeable number is the ask on this row.

          The league tag shares the name's grid cell rather than taking one
          of its own: the xl template names eleven columns, and a twelfth
          child would shift every column after it by one. */}
      <span className="flex min-w-0 items-baseline gap-2">
        <LeagueTag league={row.league} />
        <Link
          href={`/market/${encodeURIComponent(row.ticker)}`}
          className="min-w-0 truncate font-semibold tracking-tight hover:underline"
        >
          {row.team ?? row.ticker}
        </Link>
      </span>
      <span className="tabular text-sm text-muted">
        {row.ask_display} <Term k="ask">ask</Term>
      </span>

      {/* **What it is worth, beside what it costs** (ADR 0071 §2.2, Joe's
          answer 2026-08-24). This track held `breakeven_win_rate` until then,
          on fleet convening item 6, and the two cannot share the row:
          `edge_tenths` is exactly 1000 × (fair − break-even), so rendering
          both hands the reader the measured-negative edge by subtraction.
          The swap is the whole change — one of them, never both.

          Fair won because break-even is the ask with the fee added, not a
          third fact, while fair is the only one of the three that says
          something the row does not already carry. Ask stays a price and
          fair stays a probability, deliberately: their difference is NOT the
          edge, because the fee is missing from it. Precedent is
          `ConsensusPanel.tsx`, which renders fair% and is forbidden
          break-even by `tests/test_desk_panels.py:94` for this same reason.

          Two plain numbers. No sign, no arrow, no tone class — the 2026-08-21
          ruling took the *claim* off this screen, not the facts, and a
          comparison is only drawn if we draw it.

          **Unconditional, and that is a fix.** The old span rendered only
          when `breakeven_win_rate !== null`, so on a row with no tradeable
          price every column from `Books` rightward shifted one track left at
          xl. `fair_percent_display` is server-rendered and already carries
          `--` for an unreadable fair value, so the cell is always present.
          It also ends the one piece of client-side arithmetic on this row
          (`* 100).toFixed(1)`), which is the drift `format_probability`
          exists to prevent. */}
      {/* The visible word is "fair", not "consensus fair": the xl track is
          5rem and the longer label wrapped to three lines on every row. The
          full phrase is in the glossary popover, and `SlateRow.tsx` on the
          Board already says `{fair} fair / {ask} ask` — one vocabulary
          across both screens. */}
      <span className="tabular text-sm text-muted">
        {row.fair_percent_display ?? "--"} <Term k="consensus">fair</Term>
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
        <Width width={row.market_width} />
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
        <span className="w-full break-words font-mono text-xs text-accent-2 xl:col-span-full">
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

      {/* The hand-bet door (ADR 0063), last on the row so the facts are read
          before the control. `priceAlreadyVisible` because this row prints
          the ask three tracks left of here — ADR 0071 §2.2 puts it there on
          purpose, so the ticket admits the anchor rather than pretending to
          hide it. The engine's own door is not here and never was: this row
          has always carried `suggested_contracts === 0`. */}
      <span className="w-full xl:col-span-full">
        <ManualTicket
          ticker={row.ticker}
          variant="inline"
          priceAlreadyVisible
          openLabel="Bet this by hand"
          note="This is your own bet. It is recorded apart from the engine's record and never counts toward the gate."
        />
      </span>
    </div>
  );
}

/**
 * The old `/rejections` screen, folded to a disclosure (2026-08-22 review;
 * Joe approved the fold). That page grouped `suppressed_reason` across the
 * slate — a strict aggregate of what every row above already shows — so it
 * cost a footer slot to render a projection of this screen. The counts are
 * computed from the rows actually rendered here, which keeps the two views
 * incapable of disagreeing; the caption under each code is the same
 * `glossSentence` the rows use (plain English under the code, never instead
 * of it — ADR 0050). A code this build has no sentence for still renders,
 * with its count: the count is the diagnostic, the caption is a courtesy.
 *
 * **The `stale_odds` count carries an exit, not just a caption** (2026-08-22,
 * Joe's report: "stale_odds × 33" read as 33 bad bets with nothing to do
 * about it). Those rows are *unpriced* — the sportsbook side of the
 * comparison is past the odds limit, i.e. the screen is being read outside a
 * scheduled odds window — so beside the count go the two things a reader can
 * actually use: when the next window opens (from the scheduler's own
 * planning, via `/api/window`), and the existing one-tap refresh with its
 * credit cost named before the tap. Staleness stays a validity check, never
 * a weighted factor: the exit is a fresh read, not a softer bar.
 */
function RefusalSummary({
  rows,
  actionable,
  refreshable,
}: {
  rows: SlateRowData[];
  actionable: ActionableWindow | null;
  refreshable: Refreshable | null;
}) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    if (row.suppressed_reason) {
      counts.set(
        row.suppressed_reason,
        (counts.get(row.suppressed_reason) ?? 0) + 1,
      );
    }
  }
  if (counts.size === 0) return null;
  const ordered = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  // Beside the *first* stale entry only. Two composite reasons can both
  // include `stale_odds`, and one screen must not offer the same spend
  // twice — the tap is one exit, however many entries name the rule.
  const staleReason = ordered
    .map(([reason]) => reason)
    .find((reason) => isStaleOddsReason(reason));
  return (
    <details className="mt-8">
      <summary className="cursor-pointer text-sm font-semibold text-muted">
        Why rows were refused tonight — {ordered.length}{" "}
        {ordered.length === 1 ? "rule" : "rules"}, counted
      </summary>
      <ul className="mt-3 space-y-2 border-l pl-4">
        {ordered.map(([reason, count]) => (
          <li key={reason}>
            <span className="font-mono text-xs text-accent-2">{reason}</span>
            <span className="tabular ml-2 text-xs text-muted">× {count}</span>
            {glossSentence(reason) && (
              <span className="block max-w-[65ch] text-xs leading-snug text-muted">
                {glossSentence(reason)}
              </span>
            )}
            {/* Split-and-compare, never a substring: `stale_kalshi_quote`
                is the *Kalshi* clock, which no odds refresh can fix, and a
                button offered for it would be a button that lies. */}
            {reason === staleReason && (
              <StaleOddsExit
                actionable={actionable}
                refreshable={refreshable}
              />
            )}
          </li>
        ))}
      </ul>
    </details>
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
      <Hint
        hint="No usable book prices stored for this fixture."
        className="tabular text-xs text-muted"
      >
        books —
      </Hint>
    );
  }
  return (
    <Hint
      hint={`${books.books_below} of ${books.book_count} usable books price this side below Kalshi's ask. Book figures are devigged — the bookmaker's margin removed — while Kalshi's is an ask, so "under" over-counts by about half a spread.`}
      className="tabular text-xs text-muted"
    >
      {books.books_below}/{books.book_count} books under
    </Hint>
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
      className={`tabular text-xs ${stale ? "text-negative" : "text-muted"}`}
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
    line = `Kalshi has moved ${cents > 0 ? "+" : ""}${cents.toFixed(1)}c since the books were read — this row's readings compare prices from different moments.`;
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
      <Hint
        hint="Fewer than two Kalshi quotes stored in the window. Not the same as the price holding steady."
        className="tabular text-xs text-muted"
      >
        drift —
      </Hint>
    );
  }
  const minutes = Math.round(windowMs / 60_000);
  return (
    <Hint
      hint={`Change in the price you would pay over the last ${minutes} minutes.`}
      className="tabular text-xs text-muted"
    >
      {tenths > 0 ? "+" : ""}
      {(tenths / 10).toFixed(1)}c/{minutes}m
    </Hint>
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
    <Hint
      hint="Contracts resting at this ask, and the market's open interest (how many contracts are held open in this market). Availability is not fillability — both are stored quotes."
      className="tabular text-xs text-muted"
    >
      {depth === null ? "—" : Math.round(depth)} @ask
      {oi === null ? "" : ` · ${Math.round(oi).toLocaleString()} OI`}
    </Hint>
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
      <Hint
        hint="A sharp book — one whose prices professionals treat as the reference — quoted this market, and the consensus is anchored on it."
        className="tabular text-xs text-muted"
      >
        sharp-anchored
      </Hint>
    );
  }
  // The most consequential caveat in the product — all three actionable rows
  // ever written were soft fallbacks — and until 2026-08-22 its meaning
  // lived only in a title= attribute a phone cannot open (A6).
  return (
    <Hint
      hint="No sharp book quoted this market, so the fair value silently fell back to the full soft-book set — a wide consensus wearing a sharp consensus's name. Every actionable row this record has ever produced was one of these."
      className="text-xs font-semibold text-accent-2"
    >
      soft fallback
    </Hint>
  );
}

/**
 * The books' own disagreement, in points.
 *
 * Until 2026-08-21 this compared itself against the edge and wore warning
 * ink when it drowned it. With the edge off this screen (the ruling in the
 * module docstring) the comparison has nothing shown to compare against, so
 * the width stands alone as the consensus's own error bar. `null` renders
 * as an em dash: one book cannot disagree with itself, and `0.0` is a real
 * measured value two identical quotes legitimately produce.
 */
function Width({ width }: { width: number | null | undefined }) {
  if (width === null || width === undefined) {
    return <span className="tabular text-xs text-muted">width —</span>;
  }
  const points = width * 100;
  return (
    <Hint
      hint={`The devigged books disagree with each other by ${points.toFixed(1)} points on this outcome — the consensus's own error bar.`}
      className="tabular text-xs text-muted"
    >
      width {points.toFixed(1)}c
    </Hint>
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
