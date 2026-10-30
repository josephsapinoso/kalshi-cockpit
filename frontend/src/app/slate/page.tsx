import {
  ApiError,
  fetchRefreshable,
  fetchSignal,
  fetchSlate,
  fetchWindow,
  formatClock,
  readListFilter,
} from "@/lib/api";
import type {
  ActionableWindow,
  Refreshable,
  Signal,
  Slate,
  SlateRowData,
} from "@/lib/api";
import { glossSentence, whyRefusedHref } from "@/lib/suppressionGloss";
import { rowSubject } from "@/lib/rowSubject";
import {
  isStaleOddsReason,
  slateIsUnpricedByTheClock,
} from "@/lib/nextOddsWindow";
import { refreshIsUrgent } from "@/lib/refreshUrgency";
import { formatAgeShort, formatKickoff } from "@/lib/format";
import Link from "next/link";

import AnchorBaseRate from "@/components/AnchorBaseRate";
import CrewBubble from "@/components/CrewBubble";
import DispersionStrip from "@/components/DispersionStrip";
import FilterBar from "@/components/FilterBar";
import ManualTicket from "@/components/ManualTicket";
import MarketSearch from "@/components/MarketSearch";
import LeagueTag from "@/components/LeagueTag";
import LineShopHint from "@/components/LineShopHint";
import Hint from "@/components/Hint";
import OpenPositions from "@/components/OpenPositions";
import Term from "@/components/Term";
import RefreshOddsPanel from "@/components/RefreshOddsPanel";
import PageTitle from "@/components/PageTitle";
import RefreshWhenPriced from "@/components/RefreshWhenPriced";
import StaleOddsExit from "@/components/StaleOddsExit";
import TonightStrip from "@/components/TonightStrip";
import TrustNote from "@/components/TrustNote";
import RecordParlay from "@/components/RecordParlay";

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

export default async function SlatePage({
  searchParams,
}: {
  searchParams: Promise<{ league?: string; within_hours?: string }>;
}) {
  // The #15 cut, straight from the URL to the request. Not validated here:
  // the server is the one validator, and a value it refuses renders its
  // refusal below rather than the whole list under chips saying it was cut.
  const filter = readListFilter(await searchParams);
  let data: Slate;
  // Allowed to fail on its own, as on the Board. `beta` is context for the
  // rows and not a precondition of them, and the signal line renders nothing
  // rather than a placeholder that could be misread as a measured zero.
  let signal: Signal | null = null;
  // Same treatment: the timetable is context for the refresh panel, never a
  // precondition of the slate.
  let actionable: ActionableWindow | null = null;
  // What a tap could buy, for the stale-count exit in the refusal
  // disclosure. `null` means the read failed and the disclosure says so in
  // words — never a button with an unnamed cost.
  let refreshable: Refreshable | null = null;
  // The three secondary reads are independent of the slate and of each
  // other -- start them alongside the primary fetch rather than after it,
  // so this page costs its slowest call, not the sum. Each keeps its own
  // `.catch(() => null)`: a failed secondary read degrades in words.
  const signalPromise = fetchSignal().catch(() => null);
  const actionablePromise = fetchWindow().catch(() => null);
  const refreshablePromise = fetchRefreshable().catch(() => null);
  try {
    data = await fetchSlate(filter);
    signal = await signalPromise;
    actionable = await actionablePromise;
    refreshable = await refreshablePromise;
  } catch (error) {
    // A 422 is the server refusing the cut in the URL -- a different fact
    // from an unreachable backend, and drawn as one: the bar stays, at its
    // "show everything" state, so the way out is one tap.
    if (error instanceof ApiError && error.status === 422) {
      return (
        <Shell>
          <PageTitle>Games</PageTitle>
          <FilterBar pathname="/slate" filter={filter} />
          <p className="mt-6 max-w-prose text-sm text-accent-2">
            That cut is not one this desk carries: the league or the window in
            the address was refused, so nothing is drawn rather than the
            whole list under a heading that says it was cut.
          </p>
        </Shell>
      );
    }
    return (
      <Shell>
        <PageTitle>Games</PageTitle>
        <p className="mt-4 text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  const { rows, slate } = data;
  const sharedEvidence = sharedEvidenceDetails(rows);
  const hidden = data.filter?.hidden ?? 0;

  return (
    <Shell>
      <header>
        {/* "Games", matching its own nav label since 2026-08-22 (A5): the
            nav said Games, the heading said Slate, and the footer used to
            say a third thing — one screen, one name. "Slate" survives as
            the route alias and the API vocabulary, which readers of code
            meet with the map in hand. */}
        <PageTitle>Games</PageTitle>
        {/* Ticket #9's ratified Games lede (Joe, 2026-08-27). The sentence it
            replaced -- "Everything on the record for tonight" -- over-claimed
            twice: the list is capped at 100 rows against ~350 in-window, and
            the window is the recorder's last half-hour, not tonight. One
            clause departs from #9's text on a newer ruling: #9 wrote "the
            named rule behind each one the desk refused", and Joe's 29A
            ratification (2026-09-03) of the Refusals footer blurb found that
            two rows in three in the live window were refused by the fee bar
            with no rule named, so the refusal clause here takes the same
            "a named check, or the fee bar" shape rather than the universal
            reading 29A refused. */}
        <p className="mt-2 max-w-prose text-sm text-muted">
          The long list, one line per side of a market the desk priced in its
          last half-hour of recording: what Kalshi charges for it, how likely
          the sportsbooks think it is, and the reason behind each one the desk
          refused — a named check, or the fee bar — with your balance and the
          caps it sets at the top.
        </p>
        {/* The server's note used to follow this sentence here; Joe's A1 to
            #385 (2026-10-13) moved it into "How to read this" below, so a
            phone opens about eight lines closer to the first game. */}
      </header>

      {/* The #15 cut: league and kickoff window, under the nav and above
          everything the cut applies to. The count of what it removed comes
          from the server's echo, so a two-row list under "MLB" reads as cut
          rather than as a quiet night. */}
      <FilterBar
        pathname="/slate"
        filter={filter}
        note={
          hidden > 0
            ? `${hidden} ${hidden === 1 ? "row" : "rows"} hidden by this cut.`
            : null
        }
      />

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
          </p>
          {data.money.cash_tenths !== null && data.money.cash_tenths < 500 && (
            <p className="text-xs text-muted">
              You cannot place a bet until you top up; one contract at
              50c needs a {data.money.deposit_for_50c_display} balance.
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
      <dl className="mt-8 grid grid-cols-1 gap-x-6 gap-y-4">
        {/* "Showing N of M", not a bare N: the list is cut at the server's
            LIMIT, so a bare 100 read as the size of the slate when 611 rows
            were in the window. `in_window` is the count before the cut and
            `returned` is what is drawn -- both already served. */}
        <Stat
          label="Showing"
          value={`${slate.returned} of ${Math.max(slate.in_window, slate.returned)}`}
        />
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
      ) && <RefreshOddsPanel actionable={actionable} filter={filter} pathname="/slate" compact />}

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
        <>
          {sharedEvidence.length > 0 && (
            <p className="mt-8 max-w-[65ch] text-xs text-muted">
              On every game below: {sharedEvidence.join("; ")}.
            </p>
          )}
          <ul className="mt-8 divide-y divide-border">
            {rows.map((row) => (
              <li key={row.id}>
                <Row
                  row={row}
                  driftWindowMs={data.drift_window_ms}
                  maxQuoteAgeMs={data.staleness.max_kalshi_quote_age_s * 1000}
                  maxOddsAgeMs={data.staleness.max_odds_age_s * 1000}
                  sharedEvidence={sharedEvidence}
                />
              </li>
            ))}
          </ul>
        </>
      )}

      {/*
        Above the refusal disclosure, not inside it. `StaleOddsExit` lives in a
        collapsed `<details>`, and a page that re-renders itself while the only
        explanation is folded away is a page that moves for no stated reason.

        Gated on the whole screen being unpriced, never on `refreshIsUrgent` --
        that predicate is `some` and fires on one stale row, which is a working
        slate the reader is in the middle of. See `slateIsUnpricedByTheClock`.

        The render hands over the baseline count and nothing else. It used to
        pass a snapshot answer to "is a buy coming" as well, computed from
        facts older than the page's own heartbeat -- so on a cold open after a
        quiet hour it said no buy was coming and switched the watcher off
        seconds before the buy landed. The watcher asks `readWatch` against
        fresh facts on every poll instead, and the snapshot predicate was
        deleted on 2026-09-04 with the last thing that named it.
      */}
      {actionable &&
        slateIsUnpricedByTheClock(
          rows,
          data.staleness.max_odds_age_s * 1000,
        ) && (
          <div className="mt-8 max-w-[65ch]">
            <RefreshWhenPriced renderedFresh={actionable.fixtures_fresh} />
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
      ) && <RefreshOddsPanel actionable={actionable} filter={filter} pathname="/slate" />}

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
      {/* One line, not the box (Joe's B1 to #385, 2026-10-13): the verdict
          word exactly as the server states it -- UNRESOLVED is never
          rendered as "no signal" -- and a link to the full box, which moved
          to Gate. The caveat beside the rows that show the gap stays where
          it is; only the statistics moved. Nothing renders when the read
          failed, as before. */}
      {signal && (
        <p className="mt-8 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Signal test
          </span>
          <span className="font-mono font-semibold">
            {signal.available ? signal.verdict : "the registered test ended UNRESOLVED on 2026-10-01"}
          </span>
          <Link href="/gate#signal-test" className="text-muted hover:underline">
            details on Gate &rarr;
          </Link>
        </p>
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

      {/* **One disclosure for all the explaining (#344).** The sharp-book
          base rate, the "Bet this by hand" note and the four footer
          paragraphs used to sit above and below the rows, so a phone opened
          on ~2.5 screens of prose before the first game. Every sentence
          keeps its exact words; only the position moved. Collapsed: the
          rows are what a glance is for. */}
      <details className="mt-10 max-w-[65ch] border-t border-border pt-6 text-xs text-muted">
        <summary className="cursor-pointer text-sm font-semibold text-muted">
          How to read this
        </summary>
        <div className="mt-4 space-y-3">
        {/* The sentence that stops every other column reading as a signal.
            Taken from the payload rather than written here, so the server and
            the screen cannot come to disagree about what this page claims.
            It sat in the header after #9's lede until Joe's A1 to #385
            (2026-10-13); its words are unchanged, only its position moved. */}
        <p>{data.note}</p>
        {/* Was above the rows (Joe's option A, 2026-09-16: a caveat read
            seven times stops being read). Folded here by #344 so a phone
            opens on games; the per-row marker still says it row by row. */}
        {rows.length > 0 && <AnchorBaseRate rows={rows} />}
        <p>
          &ldquo;Bet this by hand&rdquo; on any row above is your own bet. It
          is recorded apart from the engine&rsquo;s record and never counts
          toward the gate. The ticket reads Kalshi&rsquo;s live book and shows
          you the ask you would pay; nothing is sent until you confirm.
        </p>
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
          A fee sits between them: pay 50c and the bet has to win more than
          50% before you are even &mdash; about{" "}
          <Term k="breakeven">51.75%</Term> at the fee rate this desk assumes;
          baseball fills have been charged less (about 50.9%), and whether
          Kalshi charges anything at payout is unchecked. So a fair value a little above the ask is the normal state of a
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
        </div>
      </details>
      {/*
        **A bet placed somewhere else is invisible to this desk, and Joe asked
        for it on this screen** (2026-09-06). His sportsbook bets never reach
        `fills`, which is the hole ADR 0078 exists for and the reason the
        2026-09-04 census could only count Kalshi taker hand fills. The form
        was reachable from `/hedge` alone; it is now on the four screens he
        actually bets from, collapsed, so it costs one line until it is
        wanted.

        It opens empty here — this screen has no single ticket to fill it
        from. The parlay desk's copy of it arrives prefilled from the card.
      */}
      <RecordParlay
        summary="Record a bet you placed"
        blurb="Already paid for a bet the desk cannot see? Record it and it will price the legs against Kalshi while the games run."
      />
    </Shell>
  );
}

/** The game event ticker for a game-series market ticker, else `null`.
 *  `KXNFLGAME-26SEP13ATLPIT-ATL` -> `KXNFLGAME-26SEP13ATLPIT`. The href is
 *  built inline at the link so `test_every_screen_is_reachable` can see it. */
function gameEventOf(ticker: string): string | null {
  const match = /^(KX[A-Z0-9]*GAME-[A-Z0-9]+)-[A-Z0-9]+$/.exec(ticker);
  return match ? match[1] : null;
}

const PRICE_CLASS = "tabular text-sm";

/** Mirror of `backend/parlays.py` `PROBABLE_BUG_CODES` (J2, #403 (A)): a row
 *  whose `suppressed_reason` names one of these has a fair value the desk
 *  itself calls a probable bug. tests/test_palette_contrast.py compares the
 *  two lists, so they cannot drift. */
const PROBABLE_BUG_CODES = new Set([
  "suspicious_edge",
  "too_few_books",
  "no_market_width",
]);

function fairIsUntrusted(reason: string | null | undefined): boolean {
  return (reason ?? "")
    .split(",")
    .some((code) => PROBABLE_BUG_CODES.has(code.trim()));
}

/** `core/trust.py` age checks; the Games row voices these in its quote chip. */
const AGE_CHECK_NAMES = new Set(["consensus_fresh", "quote_fresh"]);

/**
 * Evidence failures every visible row carries (#386), said once above the list
 * instead of on each row. Needs two or more rows and a readable score on all
 * of them; the match is on the check's own detail text, so a failure whose
 * wording differs by row (different numbers) is never called shared.
 */
function sharedEvidenceDetails(rows: SlateRowData[]): string[] {
  if (rows.length < 2) return [];
  let shared: string[] | null = null;
  for (const r of rows) {
    if (!r.trust) return [];
    const mine = r.trust.checks
      .filter((c) => c.state === "fail" && !AGE_CHECK_NAMES.has(c.name))
      .map((c) => c.detail);
    shared = shared === null ? mine : shared.filter((d) => mine.includes(d));
  }
  return Array.from(new Set(shared ?? []));
}

/** The row's evidence line, minus the failures the list states once above. */
function RowEvidence({
  trust,
  shared,
}: {
  trust: SlateRowData["trust"];
  shared: string[];
}) {
  if (!trust) return null;
  // TrustNote drops the shared details from its failure list but still counts
  // them, so a row left with only shared failures never reads "all passed".
  return (
    <TrustNote trust={trust} size="panel" hideAgeChecks hideDetails={shared} />
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
  sharedEvidence,
}: {
  row: SlateRowData;
  driftWindowMs: number;
  maxQuoteAgeMs: number;
  maxOddsAgeMs: number;
  sharedEvidence: string[];
}) {
  // The team this row's own side pays on, and how it is bought. `row.team`
  // is the YES-side team on both rows of a market, so printing it here named
  // the opponent on every NO row -- ticket #6; see `lib/rowSubject.ts`.
  const subject = rowSubject(row);
  // **A card, not a table row (#386).** Line 1 is who and when, line 2 is
  // what it costs and what it is worth at equal weight, the refusal code
  // stays visible, and the actions sit INSIDE the card above its divider.
  // Every diagnostic (books, size, drift, width, the readings strip, the
  // evidence line) is behind the one `Details` disclosure.
  return (
    <div className="rounded-lg border border-border bg-card p-3 xl:flex xl:flex-wrap xl:items-baseline xl:gap-x-4 xl:gap-y-1">
      {/* One line at xl (#7): time, league, team, ask, fair, ages, code, then
          the actions on the right. The two wrappers are `display: contents` at
          xl so every item sits in the card's one flex line; below xl they are
          the phone's stacked lines. Wraps, never truncates. */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 xl:contents">
        <span className="tabular w-24 shrink-0 font-mono text-xs text-muted">
          {row.commence_ms ? formatKickoff(row.commence_ms) : "--:--"}
        </span>
        <LeagueTag league={row.league} />
        {/* Wraps, never truncates (#386): a clipped name is a different team. */}
        <Link
          href={`/market/${encodeURIComponent(row.ticker)}`}
          className="min-w-0 break-words font-semibold tracking-tight hover:underline"
        >
          {subject.name}
        </Link>
        {subject.how && (
          <span className="shrink-0 font-mono text-[0.65rem] text-muted">
            {subject.how}
          </span>
        )}
      </div>

      {/* Ask and fair at equal size. Ask is in foreground ink; fair is
          brightened only together with its age (the oldest book line behind
          it), and dimmed with a reason when its refusal code is a probable
          bug (J2). Never a break-even beside fair (ADR 0071 section 2.2). */}
      <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1 xl:contents">
        <span className={`${PRICE_CLASS} text-foreground`}>
          {row.ask_display} <Term k="ask">ask</Term>
        </span>
        <FairSpan row={row} />
        <QuoteAge ageMs={row.quote_age_now_ms} maxMs={maxQuoteAgeMs} />
        <Anchor anchored={row.anchored_on_sharp} />
      </div>

      <StatusLine row={row} maxOddsAgeMs={maxOddsAgeMs} />
      <LineShopHint hint={row.line_shop} />

      {/* The code, verbatim, and where it is explained (#16A, #31). */}
      {row.suppressed_reason && (
        <span className="mt-1 flex w-full flex-wrap items-baseline gap-x-2 xl:mt-0 xl:w-auto">
          <span className="min-w-0 break-words font-mono text-xs text-accent-2">
            {row.suppressed_reason}
          </span>
          <Link
            href={whyRefusedHref(row.ticker)}
            aria-label="Why this was refused, on the game screen"
            className="shrink-0 text-xs text-muted underline"
          >
            why &rarr;
          </Link>
        </span>
      )}

      {/* The actions, inside the card and above its divider. */}
      <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-2 xl:ml-auto xl:mt-0 xl:shrink-0">
        <ManualTicket
          ticker={row.ticker}
          variant="inline"
          openLabel="Bet this by hand"
          closedNote={false}
        />
        {gameEventOf(row.ticker) && (
          <span>
            <Link
              href={`/game/${encodeURIComponent(gameEventOf(row.ticker) as string)}`}
              className="text-xs text-accent underline"
            >
              Build a same-game parlay &rarr;
            </Link>
          </span>
        )}
      </div>

      <details className="mt-3 border-t border-border pt-2 xl:w-full">
        <summary className="cursor-pointer text-xs font-semibold text-muted">
          Details
        </summary>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Books row={row} />
          <Capacity row={row} />
          <Drift tenths={row.kalshi_drift_tenths} windowMs={driftWindowMs} />
          <Width width={row.market_width} />
        </div>
        <div className="mt-2 space-y-2">
          <DispersionStrip
            books={row.books}
            methods={row}
            kalshiProbability={
              typeof row.ask_tenths === "number" ? row.ask_tenths / 1000 : null
            }
            anchoredBookCount={row.book_count ?? null}
          />
          <RowEvidence trust={row.trust} shared={sharedEvidence} />
        </div>
      </details>
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
 * `glossSentence` the game screen uses (plain English under the code, never
 * instead of it — ADR 0050; since #16 the rows above carry the code and a
 * `why →` link to that screen, and this disclosure is the one place on the
 * slate the sentence still renders). A code this build has no sentence for still renders,
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
            {/* **`break-words`, and it is not decoration.** A
                `suppressed_reason` is often several codes joined by commas
                with no spaces —
                `stale_odds,too_few_books,no_market_width,...` — which is one
                unbreakable token to a line-breaker. Without this the footer
                pushed the whole page's `scrollWidth` to 428 at a 390px
                viewport, so the SLATE SCROLLED SIDEWAYS on a phone. Measured
                on live 2026-08-31 while verifying something else; it is
                data-dependent, so it appears only on nights when a row
                carries a long multi-code reason.

                The row-level span at the top of this file has carried
                `w-full break-words` since it was written and does not
                overflow — this is the same fix, and the two are now
                consistent. */}
            <span className="break-words font-mono text-xs text-accent-2">
              {reason}
            </span>
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
// BOOKS-UNDER-FIGURE-START (tests/test_books_under_matches_evidence_line.py
// lifts this function by these markers and runs it; keep it import-free.)
/**
 * The "x/N books under" figure, or `null` when it cannot be printed honestly.
 *
 * #353. `books.book_count` counts every book that quoted the outcome;
 * the row's `book_count` is `fair_prices.book_count`, the books that survived
 * anchoring -- the number the evidence line (`TrustNote`, `core/trust.py`)
 * prints as "N book(s)". The two are different sets: a seeded row read
 * "0/5 books under" beside "1 book(s), need 2". `books_below` is computed
 * over the first set only and the payload carries no per-book list that would
 * let us recompute it over the second, so the figure may print only when both
 * counts are known and equal. Unknown anchored count also withholds it: with
 * nothing to compare against, agreement cannot be shown.
 */
function booksUnderFigure(
  books: { book_count: number; books_below: number } | null | undefined,
  anchoredBookCount: number | null | undefined,
): string | null {
  if (!books || books.book_count === 0) return null;
  if (typeof anchoredBookCount !== "number") return null;
  if (anchoredBookCount !== books.book_count) return null;
  return `${books.books_below}/${books.book_count} books under`;
}
// BOOKS-UNDER-FIGURE-END

/**
 * The fair value, always with the age of the books behind it.
 *
 * `odds_age_now_ms` is `(now - computed_ms) + oldest_book_age_ms`
 * (`core/ladder.py`): the oldest book line's own age, not the age of our read.
 * Missing age renders no age text and the fair stays muted: brightening a
 * number whose age is unknown would be the thing this chip exists to prevent.
 * A probable-bug code dims it regardless and says why.
 */
function FairSpan({ row }: { row: SlateRowData }) {
  const untrusted = fairIsUntrusted(row.suppressed_reason);
  const age = row.odds_age_now_ms;
  const hasAge = typeof age === "number" && age >= 0;
  const ink = hasAge && !untrusted ? "text-foreground" : "text-muted";
  return (
    <span className={`${PRICE_CLASS} ${ink}`}>
      {row.fair_percent_display ?? "--"} <Term k="consensus">fair</Term>
      {hasAge && (
        <span className="ml-1 text-xs text-muted">
          &middot; oldest book line {formatAgeShort(age)}
        </span>
      )}
      {untrusted && (
        <>
          {" "}
          <Link
            href={whyRefusedHref(row.ticker)}
            className="text-xs text-accent-2 underline"
          >
            fair not trusted &mdash; why &rarr;
          </Link>
        </>
      )}
    </span>
  );
}

function Books({ row }: { row: SlateRowData }) {
  // The figure counts the anchored books when the fair price was anchored
  // (#375, Joe's A to #373); `row.books` stays the unanchored distribution
  // the strip below and Willy read (ADR 0021 §7.2). An anchored row whose
  // anchored object is missing falls back to `row.books`, whose count then
  // disagrees with the anchored count and prints "books —" (#353).
  const books = row.books_anchored ?? row.books;
  const figure = booksUnderFigure(books, row.book_count);
  if (books && books.book_count > 0 && figure === null) {
    // Usable books exist but they are not the books behind the fair value
    // (or the anchored count is unreadable). Say nothing numeric rather than
    // a denominator the evidence line contradicts; the dispersion strip
    // below states both counts.
    return (
      <Hint
        hint="The books that quoted this outcome are not the books the fair value was averaged over, so no books-under count is shown. The strip below says how many of each."
        className="tabular text-xs text-muted"
      >
        books —
      </Hint>
    );
  }
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
      {figure}
    </Hint>
  );
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
  // One format (`47s`, `6m`, `2h`). Neutral ink under the limit; past it the
  // caution ochre with the limit named, never red (#10, #32, #386).
  return (
    <span
      className={`tabular text-xs ${stale ? "text-accent-2" : "text-muted"}`}
    >
      <Term k="quote_age">quote</Term> {formatAgeShort(ageMs)}
      {stale && <> · limit {formatAgeShort(maxMs)}</>}
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
 *   1. the consensus is past the odds limit          — the row cannot be
 *      actionable until the books are re-bought (the button above the list)
 *   2. (removed, #344) the Kalshi quote past its limit. The red age chip and
 *      the evidence line under the row already say it; a third sentence made
 *      each stale row say it three times.
 *   3. the tape has moved ≥ 1.0c in the drift window — the price being
 *      compared is not the price that was compared
 *
 * **The first two were the other way round until 2026-08-31, and the order is
 * not a matter of taste — it is `_live_ages`' own rule.** `actionable` is the
 * ODDS clock and only the odds clock: the order endpoint re-reads the Kalshi
 * quote inside the request (`kalshi/quotes.py`), so a recorded quote past its
 * thirty-second limit no longer stops an order. It means the price on the row
 * is a memory, not that the row is dead. **Nothing refreshes the sportsbook
 * consensus but a credit, so that is the limit which actually ends a row's
 * life.**
 *
 * Both are stale on most rows outside a window, so the old order voiced the
 * *less* binding of the two on exactly the rows where the difference matters.
 * Seen on live 2026-08-31: a row whose consensus was **2042s past a 900s
 * limit** printed only "Kalshi quote is 134s old", and nothing on the row said
 * the thing a reader could act on — re-buy the odds. Reading a live screen is
 * what found it; the priority had been stated in this docstring since it was
 * written and never checked against the rule it was serving.
 *
 * This stays a SELECTION, not a composite (ADR 0021 §9): one line voices one
 * fact from one source, and choosing which by fixed priority weighs nothing
 * against anything. What changed is which fact, not how many.
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
  maxOddsAgeMs,
}: {
  row: SlateRowData;
  maxOddsAgeMs: number;
}) {
  let line: string | null = null;
  // The odds clock FIRST: it is the one that decides `actionable`, and it is
  // the one with an action attached (re-buy the books). See the note above.
  if (
    row.odds_age_now_ms !== null &&
    row.odds_age_now_ms !== undefined &&
    row.odds_age_now_ms > maxOddsAgeMs
  ) {
    line = `Oldest book line ${Math.round((row.odds_age_now_ms ?? 0) / 60_000)} min old — past the ${Math.round(maxOddsAgeMs / 60_000)} min limit. Not actionable until the odds are refreshed.`;
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
    return null;
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
 *
 * **`ms` is the sportsbook's start, not Kalshi's.** Until 2026-08-29 the route
 * behind this column selected `kalshi_events.commence_ms` -- `occurrence_
 * datetime` raw, about three hours late on game series -- so this table printed
 * a 19:05 first pitch as 22:05 while `/market/[ticker]` printed it correctly.
 * Nothing is corrected here: `--:--` means the row has no linked fixture and
 * therefore no trustworthy kickoff, which is a blank on purpose. Ticket #26.
 */
function Stat({ label, value }: { label: string; value: number | string }) {
  /* The HUD's lit readout (#174, Joe's #173 (A)): the same "glow" text-shadow
     and indigo ink `ui.tsx`'s `Stat` draws with `readout` set, on the two
     headline numbers this screen leads with. Not the shared component
     itself -- `tests/test_palette_contrast.py`'s
     `TestTheNeutralCountIsNotPaintedAsAVerdict` reads a local `function
     Stat(` out of this file's own source and is outside this ticket's
     `Lane owns` list, so the function stays local and only its look
     changes.

     A count is a fact, not a verdict, which is why the readout takes the
     indigo rather than the loss colour: whether a Stat may wear the indigo
     at all was ticket #33, Joe chose yes (2026-09-02), the build was then
     killed as not earning (NEXT.md, 2026-09-03), and `board/page.tsx`'s Stat
     (the other page this same reason is read from) still renders it plain
     -- so the two screens now differ on purpose, not by drift. */
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div className="tabular glow text-3xl font-semibold leading-tight text-accent">
        {value}
      </div>
    </div>
  );
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
