import Link from "next/link";

import { SHELL_WIDTH } from "@/lib/shell";
import { tickerLabel } from "@/lib/tickerLabel";
import NotTonight from "@/components/NotTonight";
import RecordChart from "@/components/RecordChart";
import OpenPositions from "@/components/OpenPositions";
import Term from "@/components/Term";
import type { BetsKindSummary } from "@/lib/types/bets";
import RecordParlay from "@/components/RecordParlay";
import HedgePositions from "@/components/HedgePositions";
import PickSourceChips from "@/components/PickSourceChips";
import {
  DISPLAY_TIME_ZONE,
  fetchBets,
  fetchHedge,
  formatDuration,
  isLive,
  type BetKind,
  type BetsRecord,
  type BetsSection,
  type BySourceBlock,
  type PickSourcesBlock,
  type SettledBet,
} from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Joe's own record (2026-08-21, betting-desk item 1 — the partner ranked it
 * first because the poller has mirrored `venue_settlements` since 2026-08-18
 * and the tool never once read it back to its owner).
 *
 * Honesty rules, each load-bearing:
 *
 * - **The net strip covers the whole table**, and says how many rows its sum
 *   excludes. A row that cannot carry the registered formula (a void, an
 *   unreadable price or fee) renders "—", never $0.00.
 * - **Two kinds, two sections (ticket #21, Joe's 21A, 2026-09-03).** A
 *   combination bet and a single game are not the same kind of bet, and on
 *   the live record the combos are the majority. Each section heads itself
 *   with its own count and its own net sum — the per-group view beside the
 *   pooled one — and the kind is the server's (`bet.kind`), never re-derived
 *   here from the ticker string. The combination section renders no CLV
 *   words at all: a combo has no close to be scored against, and fifty rows
 *   of "close not read yet" would say the close was late rather than absent.
 * - **This is the mirror, not the account.** Open positions are structurally
 *   absent (a settlement exists only after the venue settles — so an
 *   unsettled combination bet is not here either), and the mirror is not
 *   complete: the venue's endpoint drops history. The page states its own
 *   first day from `first_settled_ms` and types no date of its own.
 * - **No opinion.** Nothing here scores, grades, or advises; the estimate
 *   log stays embargoed (the study stopped without result) and this page
 *   never touches it. No average, win rate, hit rate, streak or trend line
 *   anywhere, for either section or the whole, until thirty scored bets
 *   exist with the per-group view beside them. It is a bank statement, not
 *   a report card.
 */
export default async function BetsPage() {
  let record;
  try {
    record = await fetchBets();
  } catch {
    return (
      <Shell>
        <p className="max-w-[65ch] text-muted">Backend unreachable.</p>
      </Shell>
    );
  }
  const { totals } = record;
  // The open section's data is the same fetch /hedge made (#240): no new
  // route and no new arithmetic. A failed read is its own state, never a
  // count of zero -- "0 open" off an unreadable answer would be a claim.
  let hedge: Awaited<ReturnType<typeof fetchHedge>> | null = null;
  try {
    hedge = await fetchHedge();
  } catch {
    hedge = null;
  }
  // Live = a leg still pending AND the venue has not settled the combination;
  // the same predicate HedgePositions partitions on and Nav's badge counts.
  const openCount =
    hedge === null
      ? null
      : hedge.positions.filter(isLive).length;

  return (
    <Shell>
      <header className="mb-8">
        {/* Quieter than the net figure below (#248): the page's name is not
            its news. The h1 steps down to 2xl/3xl; the net readout is
            3xl/4xl, so the money is the largest type on the screen. */}
        <h1 className="display text-2xl sm:text-3xl">Your bets</h1>
        {/* Decisions as the unit (B6): counting only bets placed made
            betting the sole recordable act. The pass count is a floor —
            only taps are recorded — and passes are never scored or rated;
            this line may never grow a "right to pass" grade. */}
        {record.passes && (
          <p className="mt-3 max-w-[65ch] text-sm">
            <span className="font-semibold tabular">
              {record.total} {record.total === 1 ? "bet" : "bets"} ·{" "}
              {record.passes.total}{" "}
              {record.passes.total === 1 ? "pass" : "passes"}
            </span>
            <span className="text-muted">
              {record.passes.first_ms !== null
                ? ` since ${sinceDate(record.passes.first_ms)} — a pass is a decision too.`
                : " — a pass is a decision too; none recorded yet."}
            </span>
          </p>
        )}
        {/* Ticket #9's ratified "Your bets" lede (Joe, 2026-08-27), verbatim.
            "Every bet the desk has SEEN settle" rather than "every bet that
            has settled": `backend/bets.py` records that rows settled while
            the poller was down are absent too, not only rows before
            2026-08-18. "However you placed it" kills the worst misreading --
            that this scores the desk's picks -- and is literally true, since
            the only source is `venue_settlements LEFT JOIN closing_lines`.
            CLV is described, not named, so `tests/test_glossary_coverage.py`'s
            `\bCLV\b` rule is not triggered here. */}
        <p className="mt-3 max-w-[65ch] text-lg text-muted">
          Your own record, read back from your Kalshi account: every bet the
          desk has seen <Term k="settled">settle</Term> since it started
          watching — however you placed it — what each one won or lost after
          the venue&rsquo;s fees, what they add up to, and, on the ones where
          it can be checked, whether you paid better than Kalshi&rsquo;s own
          last price before the game started.
        </p>
      </header>

      {/*
        **Open (N), first on the page (#240, Joe's 234 A, 2026-09-30).** What
        he still holds is what a bet screen is opened for; /hedge used to be
        a footer link to it and now redirects here (`/bets#open`). It renders
        `HedgePositions` off `fetchHedge`, unchanged -- every figure and every
        caveat on those cards is that component's, and this page adds no
        arithmetic of its own. N counts live positions only (a pending leg and
        no venue settlement); settled-but-unclosed tickets stay in the
        component's own collapsed group. An unreadable answer says so rather
        than printing 0.
      */}
      <section id="open" className="mb-10 scroll-mt-24">
        <h2 className="display text-2xl sm:text-3xl">
          Open{openCount === null ? "" : ` (${openCount})`}
          {openCount === null ? null : (
            <span className="ml-2 text-sm font-normal text-muted">
              {openCount === 1 ? "ticket" : "tickets"} on the desk
            </span>
          )}
        </h2>
        {hedge === null ? (
          <p className="mt-3 max-w-[65ch] text-sm text-muted">
            What you hold could not be read right now. That is not the same as
            holding nothing.
          </p>
        ) : (
          <>
            <p className="mt-3 max-w-[65ch] text-sm leading-relaxed text-muted">
              Tickets you hold, priced against what the other side costs on
              Kalshi right now. When one <Term k="leg">leg</Term> is left and
              the rest have won, a <Term k="hedge">hedge</Term> can pay the
              same whichever way it goes &mdash; a <Term k="lock">lock</Term>.
              Before that it can only <Term k="derisk">de-risk</Term>.
            </p>
            <p className="mt-2 max-w-[65ch] text-xs leading-relaxed text-muted">
              {hedge.notes.not_advice}
            </p>
            <p className="mt-1 max-w-[65ch] text-xs leading-relaxed text-muted">
              {hedge.notes.no_button}
            </p>
            <HedgePositions
              positions={hedge.positions}
              notes={hedge.notes}
              unrecordedAtVenue={hedge.unrecorded_at_venue}
              venuePollMs={hedge.venue_poll_ms}
              asOfMs={hedge.as_of_ms}
              maxQuoteAgeMs={hedge.max_quote_age_ms}
              pickSources={record.pick_sources}
            />
          </>
        )}
      </section>

      <div className="hud rounded-2xl border border-edge bg-card p-5">
        <div className="text-xs font-semibold uppercase tracking-widest text-muted">
          <Term k="net">Net</Term>, over the whole mirrored record
        </div>
        <p className="mt-2 max-w-[65ch]">
          {/* NOT the HUD's lit readout, on Joe's word (2026-09-27). #176
              shipped this figure with `glow` and he took it off: the readout
              is for neutral counts (Games' "On the slate"), and this is a
              win/loss verdict on his own money -- glowing it made his
              biggest loss the brightest thing on the page and spent the red
              that is meant to stay scarce. Nor the readout's indigo ink,
              which would erase won vs. lost. Plain, in its own colour. */}
          <span
            className={`display text-3xl sm:text-4xl ${
              totals.net_tenths < 0 ? "text-negative" : "text-positive"
            }`}
          >
            {totals.net_display}
          </span>
          <span className="ml-3 font-mono text-sm text-muted">
            over {totals.computable} <Term k="settled">settled</Term>
          </span>
        </p>
        {/* The denominator the per-bet CLV numbers never had (B5), and since
            21A it is the single-game count: a combination bet has no close
            to be scored against, so counting it among the refusals reported
            "scored on 1 of 77" for a record in which 50 rows were never
            scorable. Counts only — no average, no hit rate. */}
        {record.clv_coverage && (
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            <Term k="clv">CLV</Term> scored on {record.clv_coverage.scored} of{" "}
            {record.clv_coverage.denominator} single-game{" "}
            {record.clv_coverage.denominator === 1 ? "bet" : "bets"} — the
            rest refused (no readable close yet, or no entry time). Unmeasured
            is not the same as bad; each single-game row below says which it
            is. Combination bets have no close to score against and are not
            counted here.
          </p>
        )}
        {/* The one-tap lockout, beside the biggest red number in the
            product. Same POST, same no-confirm rule as TonightStrip. */}
        <NotTonight lockoutUntilMs={record.lockout_until_ms ?? null} />
        {totals.uncomputable > 0 && (
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            {totals.uncomputable}{" "}
            {totals.uncomputable === 1 ? "row" : "rows"} could not carry the
            settlement formula (a void, or an unreadable price or fee) and{" "}
            {totals.uncomputable === 1 ? "is" : "are"} excluded from the net —
            shown below as &ldquo;—&rdquo;, never counted as $0.00.
          </p>
        )}
        <MirrorNotAccount firstSettledMs={record.first_settled_ms} />
      </div>

      {/* What is at risk right now (B3), above the settled list: the settled
          record alone hides the money currently on the table. Unsigned,
          never summed with the net strip above. */}
      <div className="mt-4 max-w-[65ch]">
        <OpenPositions block={record.open_positions} />
      </div>

      {/* The record as a picture, above the rows it is made of. A fact --
          what happened to the money -- and deliberately not a verdict: no
          trend line, no hit rate, no CLV series. The 2026-08-21 ruling caps
          "CLV on his own bets" at per-bet rows until n >= 30. Drawn over the
          whole window, both kinds: the money left one account. */}
      <RecordChart bets={record.bets} />

      {/*
        The way in to the hedge screen (ADR 0078). Here rather than in the nav:
        the six-link budget is load-bearing at 390px (ADR 0073), and what he
        holds already lives on this page — a ticket the venue cannot see is the
        same subject as the positions above it.
      */}
      <p className="mt-4 max-w-[65ch] text-sm text-muted">
        A parlay you placed somewhere else is invisible here.{" "}
        <Link href="#open" className="underline decoration-dotted">
          Record it below
        </Link>{" "}
        and the desk will watch its legs while the games run; it then appears
        under Open above.
      </p>

      {record.bets.length === 0 ? (
        <p className="mt-8 max-w-[65ch] text-sm text-muted">
          Nothing has settled since the recorder started watching. When a
          position you hold settles, it appears here on the next poll.
        </p>
      ) : (
        <>
          {SECTIONS.map((section) => (
            <BetSection
              key={section.kind}
              section={section}
              block={record.sections[section.kind]}
              record={record}
            />
          ))}
          {record.returned < record.total && (
            <p className="mt-3 max-w-[65ch] text-xs text-muted">
              Showing the most recent {record.returned} of {record.total} —
              the net strip and the section counts above still cover all{" "}
              {record.total}.
            </p>
          )}
        </>
      )}
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

/**
 * The two kinds, in reading order: single games first because that is where
 * CLV lives, combination bets second. The words are the screen's; the kind
 * itself is the server's.
 */
const SECTIONS: readonly {
  kind: BetKind;
  title: string;
  one: string;
  many: string;
}[] = [
  { kind: "single", title: "Single games", one: "bet", many: "bets" },
  {
    kind: "combo",
    title: "Combination bets",
    one: "combo",
    many: "combos",
  },
];

/**
 * One kind's list under its own heading: the whole-table count and net sum
 * for that kind, then its rows from the served window. The heading's numbers
 * are the server's whole-table figures, never a count of the rows below, so
 * a windowed list cannot wear the label of a claim about the record (the
 * /api/ledger lesson, applied per section).
 */
function BetSection({
  section,
  block,
  record,
}: {
  section: (typeof SECTIONS)[number];
  block: BetsSection;
  record: BetsRecord;
}) {
  const anyShown = record.bets.some((bet) => bet.kind === section.kind);
  return (
    <section className="mt-10">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
        {section.kind === "combo" ? (
          <Term k="parlay">{section.title}</Term>
        ) : (
          section.title
        )}{" "}
        · <span className="tabular">{block.total}</span>
      </h2>
      {/* The section's own sum — a per-group view beside the pooled strip,
          which the measurement rules ask for. A sum, and only a sum: no
          rate of any kind may join it. */}
      {block.total > 0 && (
        <p className="mt-1 max-w-[65ch] font-mono text-xs text-muted">
          <Term k="net">net</Term>{" "}
          <span
            className={
              block.net_tenths < 0 ? "text-negative" : "text-positive"
            }
          >
            {block.net_display}
          </span>{" "}
          over {block.computable} <Term k="settled">settled</Term>
          {block.uncomputable > 0
            ? ` · ${block.uncomputable} excluded as uncomputable`
            : ""}
        </p>
      )}
      {/* #287: wins and losses for THIS kind, and under combinations the
          expected line. Every figure is the server's; nothing is pooled
          across the two sections and nothing is divided here. */}
      <KindSummary
        kind={section.kind}
        summary={record.summary?.[section.kind]}
      />
      <BySource kind={section.kind} blocks={record.by_source?.[section.kind]} />
      {/* #161: how many of this kind carry the desk's chance at the moment
          it was priced -- a whole-table COUNT, never a rate. Combo only:
          a single carries no chance at all, so the sentence would always
          read "0 of N" and say nothing. */}
      {section.kind === "combo" && block.total > 0 && (
        <p className="mt-1 max-w-[65ch] text-xs text-muted">
          <span className="tabular">{block.chance_carried}</span> of{" "}
          <span className="tabular">{block.total}</span> carry the{" "}
          <Term k="chance_when_priced">desk&rsquo;s chance</Term>
        </p>
      )}
      {block.total === 0 ? (
        <p className="mt-3 max-w-[65ch] text-sm text-muted">
          No {section.many} have settled in the mirrored record.
        </p>
      ) : !anyShown ? (
        <p className="mt-3 max-w-[65ch] text-sm text-muted">
          None among the most recent {record.returned} — the count above
          still covers the whole record.
        </p>
      ) : (
        <div className="mt-4">
          {groupByDay(
            record.bets.filter((bet) => bet.kind === section.kind),
          ).map((group) => (
            <div key={group.key} className="mt-5 first:mt-0">
              <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">
                {group.heading}
              </h3>
              <ul className="mt-2 divide-y border-t">
                {group.bets.map((bet, index) => (
                  <BetRow
                    key={`${bet.ticker}-${bet.settled_ms}-${index}`}
                    bet={bet}
                    pickSources={record.pick_sources}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * #287 (Joe answered #272 A): one kind's wins and losses, and the line
 * "at the prices you paid, about N were expected to win; K did" with its
 * range and its price buckets behind a tap. The expected figure is the
 * prices paid read as chances; it says nothing about skill and carries no
 * return figure. A cell the server marks `too_few` gets no range. A single
 * game below the floor gets counts only (`counts_only`).
 */
function KindSummary({
  kind,
  summary,
}: {
  kind: BetKind;
  summary: BetsKindSummary | undefined;
}) {
  if (!summary || summary.computable === 0) return null;
  const counts = (
    <p className="mt-1 max-w-[65ch] font-mono text-xs text-muted">
      <Term k="wl">
        {summary.wins}W / {summary.losses}L
      </Term>
      {summary.counts_only && summary.floor !== null
        ? ` · counts only until ${summary.floor} settled`
        : ""}
    </p>
  );
  const expected = summary.expected;
  if (!expected) return counts;
  return (
    <>
      {counts}
      <p className="mt-1 max-w-[65ch] text-sm">
        At the prices you paid, about{" "}
        <Term k="expected_wins">
          <span className="tabular">{expected.expected}</span> were expected to
          win
        </Term>
        ; <span className="tabular">{expected.won}</span> did.{" "}
        {expected.too_few ? (
          <span className="text-muted">
            Too few {kind === "combo" ? "combos" : "bets"} to put a{" "}
            <Term k="plausible_range">range</Term> on it yet.
          </span>
        ) : (
          <span className="text-muted">
            The <Term k="plausible_range">range</Term> is{" "}
            <span className="tabular">{expected.range_low}</span> to{" "}
            <span className="tabular">{expected.range_high}</span>.
          </span>
        )}
      </p>
      {summary.excluded_from_expected > 0 && (
        <p className="mt-1 max-w-[65ch] text-xs text-muted">
          {summary.excluded_from_expected} settled without a readable price and
          {" "}left out of this line.
        </p>
      )}
      <details className="mt-1 max-w-[65ch] text-xs text-muted">
        <summary className="cursor-pointer">By price paid</summary>
        <ul className="mt-1 space-y-1 font-mono">
          {expected.buckets.map((bucket) => (
            <li key={bucket.label}>
              {bucket.label}: {bucket.n} {bucket.n === 1 ? "bet" : "bets"},
              about {bucket.expected} expected, {bucket.won} won
              {bucket.too_few
                ? " — too few to judge"
                : ` — range ${bucket.range_low} to ${bucket.range_high}`}
            </li>
          ))}
        </ul>
        <p className="mt-1 max-w-prose">
          Each price is read as a chance, so the expected figure says nothing
          about skill and nothing about money.
        </p>
      </details>
    </>
  );
}

/**
 * v63 (Joe, 2026-10-02): the same wins/losses and expected line, split by
 * where he says each pick came from. Rows in the server's FIXED order
 * (card, verdict, preset, chat, friend, own, then untagged) and never sorted
 * by any result -- an ordering is a claim (ADR 0071). A source whose
 * expected wins or losses is under 5 gets no range, the kinds' own rule.
 * Collapsed: it is a record to look back on, not a headline.
 */
function BySource({
  kind,
  blocks,
}: {
  kind: BetKind;
  blocks: BySourceBlock[] | undefined;
}) {
  if (!blocks || blocks.length === 0) return null;
  const noun = kind === "combo" ? "combos" : "bets";
  return (
    <details className="mt-1 max-w-[65ch] text-xs text-muted">
      <summary className="cursor-pointer">By where the pick came from</summary>
      <ul className="mt-1 space-y-1 font-mono">
        {blocks.map((block) => (
          <li key={block.source}>
            {block.label}: {block.wins}W / {block.losses}L
            {block.expected === null
              ? " · counts only"
              : ` · about ${block.expected.expected} expected to win`}
            {block.expected === null
              ? ""
              : block.expected.too_few
                ? ` — too few ${noun} to judge`
                : ` — range ${block.expected.range_low} to ${block.expected.range_high}`}
          </li>
        ))}
      </ul>
      <p className="mt-1 max-w-prose">
        Tag each bet below with where the pick came from. Each price is read
        as a chance, so this says how a source&rsquo;s picks did against the
        prices you paid, not whether the source is any good. It needs about
        five expected wins and five expected losses before it can say even
        that.
      </p>
    </details>
  );
}

/**
 * The page's completeness sentence, with the record's first day read from
 * the data. Until 21A this line said "before the recorder started on Aug
 * 18", typed into the page — and the live mirror's first settlement is a
 * week earlier than that, because the settlements endpoint carried some
 * history back when the poller first read it. A date typed here is a claim
 * the page cannot keep; the server's `MIN(settled_ms)` is one it can.
 */
function MirrorNotAccount({
  firstSettledMs,
}: {
  firstSettledMs: number | null;
}) {
  return (
    <p className="mt-2 max-w-[65ch] text-xs text-muted">
      This is the recorder&rsquo;s mirror, not your account. Open positions
      are not here (a settlement exists only after the venue settles), so a
      combination bet that has not settled yet is not here either. The mirror
      is not complete:{" "}
      {firstSettledMs !== null
        ? `its earliest settlement is ${firstDay(firstSettledMs)}, and`
        : "nothing has been mirrored yet, and"}{" "}
      the venue&rsquo;s settlements endpoint drops history, so anything it
      dropped before the recorder read it is missing. Fees are the
      venue&rsquo;s own, already subtracted.
    </p>
  );
}

/**
 * Words for a refused per-bet CLV, in place of the number. No reason ever
 * substitutes a value -- `bet.clv_display` stays null and this is the only
 * thing rendered instead. `combo_unscorable` has no entry on purpose: a
 * combination row draws no CLV line at all (see `BetRow`).
 */
const CLV_REFUSAL_WORDS: Record<string, string> = {
  no_closing_line: "close not read yet",
  unreadable_close: "close unreadable",
  entry_time_unknown: "entry time unknown",
  entry_after_close: "entered after close",
};

/**
 * Words for a refused `chance_when_priced` (#161), in place of the number.
 * No reason ever substitutes a value or a "0%" -- `bet.chance_when_priced`
 * stays null and this is the only thing rendered instead. A single's row
 * (always both null) maps to nothing here, since `BetRow` only reads this
 * for a combo.
 */
/**
 * The desk's chance as a percent that never rounds a real reading to "0%".
 * Joe's longshot combinations are priced at a tenth of a cent, and the first
 * live render printed "Desk's chance when you priced it: 0%" for one --
 * which reads as "no chance", the one thing the number did not say. Whole
 * points from 10%, finer below, and a floor that says "under".
 */
function chancePercent(p: number): string {
  const pct = p * 100;
  if (pct >= 10) return `${Math.round(pct)}%`;
  if (pct >= 1) return `${pct.toFixed(1)}%`;
  if (pct >= 0.01) return `${pct.toFixed(2)}%`;
  return "under 0.01%";
}

const CHANCE_REFUSAL_WORDS: Record<string, string> = {
  no_fill_row: "— no fill on record",
  not_priced_on_desk: "— not priced on the desk",
};

// #168: the outside-parlay check (#166) can write a reading that looked at
// the parlay and still could not produce one number for the whole thing --
// a leg with no desk reading, or two legs on one game. That parlay WAS
// checked, so "not priced on the desk" would be false for it; this sentence
// replaces the generic refusal words only when `checked_without_chance` is
// true, never alongside a real `chance_when_priced` (a chance always wins).
const CHECKED_WITHOUT_CHANCE_WORDS =
  "— checked on the desk, no chance for the whole parlay";

/**
 * Settled rows grouped under the day they settled (#248), in the display
 * zone like every other clock here. The server sends newest first and this
 * keeps that order: a new group opens whenever the day changes, so the
 * grouping never reorders a row and never merges two separate days.
 */
function groupByDay(
  bets: SettledBet[],
): { key: string; heading: string; bets: SettledBet[] }[] {
  const groups: { key: string; heading: string; bets: SettledBet[] }[] = [];
  for (const bet of bets) {
    const at = new Date(bet.settled_ms);
    const key = at.toLocaleDateString("en-CA", { timeZone: DISPLAY_TIME_ZONE });
    const last = groups[groups.length - 1];
    if (last !== undefined && last.key === key) {
      last.bets.push(bet);
      continue;
    }
    groups.push({
      key,
      heading: at.toLocaleDateString("en-US", {
        timeZone: DISPLAY_TIME_ZONE,
        weekday: "short",
        month: "short",
        day: "numeric",
      }),
      bets: [bet],
    });
  }
  return groups;
}

/**
 * What the bet WAS, in words, for the row's first line (#248). The payload
 * carries no leg list and no team names -- only `ticker`, `kind` and `side`
 * -- so this reads only what the ticker states outright and refuses the
 * rest: a moneyline ticker `KX<SPORT>GAME-<date><time><AAA><BBB>-<PICK>`
 * names the two sides and the pick; a combination shard names nothing, so it
 * says it is a combination; anything unparsed says "Single game bet". Never
 * a guessed team: a code that does not fit falls through to the plain words.
 * The ticker stays on the row as small print (`BetRow`).
 */
const GAME_TICKER =
  /^KX[A-Z]+GAME-\d{2}[A-Z]{3}\d{2}\d{4}([A-Z]{3})([A-Z]{3})-([A-Z]{3})$/;

/**
 * #294: each leg's own result, as the server serves it (`result` is null when
 * the desk has not read that leg's market). Declared here because the shared
 * `SettledBet` type is outside this lane. Every leg renders through ONE
 * element with ONE style: no losing-leg highlight, no tally by bet type.
 */
type LegWithResult = NonNullable<SettledBet["legs"]>[number];

function legResultWord(result: LegWithResult["result"]): string {
  return result === "won"
    ? "won"
    : result === "lost"
      ? "lost"
      : result === "void"
        ? "void"
        : "result not read";
}

function betLead(bet: SettledBet): string {
  // #254: a combination leads with its legs when the server could read
  // them all; one unreadable leg and `legs` is null, so the words stay.
  if (bet.kind === "combo" && bet.legs && bet.legs.length > 0) {
    return bet.legs.map((leg) => leg.label).join(" + ");
  }
  if (bet.kind === "combo") return "Combination bet";
  const m = GAME_TICKER.exec(bet.ticker);
  if (m === null || (m[3] !== m[1] && m[3] !== m[2])) {
    return bet.market_title
      ? `${bet.market_title} · ${bet.side === "no" ? "NO" : "YES"}`
      : "Single game bet";
  }
  return `${m[1]} vs ${m[2]} \u00b7 ${bet.side === "no" ? "against" : "on"} ${m[3]}`;
}

/**
 * One settled position. The result word and the net are the row's facts;
 * the ticker links to the market screen, which knows how to say what the
 * market was. A refused net renders "—" with the reason class in the words
 * above — never a zero, and never a hidden row. The CLV line is drawn for a
 * single game only: a combination market has no close to be read, and the
 * absence of a line says so better than any words would.
 */
function BetRow({
  bet,
  pickSources,
}: {
  bet: SettledBet;
  pickSources: PickSourcesBlock | undefined;
}) {
  const settled = new Date(bet.settled_ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
  const contracts = Number.isInteger(bet.contracts)
    ? bet.contracts.toString()
    : bet.contracts.toFixed(2);
  const result =
    bet.won === null ? "unresolved" : bet.won ? "won" : "lost";
  // JSX rather than a template string so "CLV" can carry its definition —
  // this row is the one place the record and CLV meet (2026-08-22, A4).
  const clvWords =
    bet.clv_display !== null ? (
      <>
        close {bet.close_display} · <Term k="clv">CLV</Term> {bet.clv_display}
      </>
    ) : (
      (CLV_REFUSAL_WORDS[bet.clv_refusal_reason ?? ""] ?? "close unknown")
    );
  // #161: the desk's own consensus chance at the moment this combo was
  // priced, with how long before the fill that reading was taken. Never a
  // substituted "0%" — a missing chance renders the refusal words instead,
  // pulled straight from the server's named reason.
  const chanceWords =
    bet.chance_when_priced !== null ? (
      <>
        <Term k="chance_when_priced">Desk&rsquo;s chance</Term> when you
        priced it: {chancePercent(bet.chance_when_priced)}
        {bet.chance_priced_before_fill_ms !== null
          ? ` · ${formatDuration(bet.chance_priced_before_fill_ms)} before you bought`
          : ""}
      </>
    ) : bet.checked_without_chance ? (
      CHECKED_WITHOUT_CHANCE_WORDS
    ) : (
      CHANCE_REFUSAL_WORDS[bet.chance_refusal_reason ?? ""] ?? null
    );
  return (
    <li>
      <Link
        href={`/market/${encodeURIComponent(bet.ticker)}`}
        className="flex items-baseline gap-3 py-4 transition-colors hover:bg-accent-soft"
      >
        <span className="min-w-0 flex-1">
          {/* The row leads with what the bet was, in words (#248); the
              ticker is small print beneath it. */}
          <span className="block text-sm font-semibold">{betLead(bet)}</span>
          <span className="mt-0.5 block text-xs text-muted">
            {contracts} × {bet.side.toUpperCase()} at{" "}
            {bet.entry_price_display} · settled {settled}
          </span>
          {/* tickerLabel keeps the TAIL — CSS truncate cuts the right end,
              which on a combo shard is the only identifying part, so every
              combo row rendered identically (2026-08-22 review). The full
              ticker stays in title= for hover and copy. */}
          <span
            className="mt-0.5 block truncate font-mono text-[11px] text-muted"
            title={bet.ticker}
          >
            {tickerLabel(bet.ticker)}
          </span>
          {bet.kind === "combo" && bet.legs && bet.legs.length > 0 && (
            <span className="mt-1 block text-xs text-muted" data-leg-results>
              {bet.legs.map((leg, i) => (
                <span key={i} className="block" data-leg-result>
                  {leg.label} · {legResultWord(leg.result)}
                </span>
              ))}
            </span>
          )}
          {bet.kind === "single" && (
            <span
              className={`mt-0.5 block text-xs ${
                bet.clv_tenths !== null && bet.clv_tenths < 0
                  ? "text-negative"
                  : "text-muted"
              }`}
            >
              {clvWords}
            </span>
          )}
          {bet.kind === "combo" && chanceWords !== null && (
            <span className="mt-0.5 block text-xs text-muted">
              {chanceWords}
            </span>
          )}
        </span>
        <span className="shrink-0 text-right">
          <span
            className={`block font-mono text-sm font-semibold ${
              bet.net_tenths === null
                ? "text-muted"
                : bet.net_tenths < 0
                  ? "text-negative"
                  : "text-positive"
            }`}
          >
            {bet.net_display ?? "—"}
          </span>
          <span className="mt-0.5 block text-xs text-muted">{result}</span>
        </span>
      </Link>
      {/* Outside the link: a tap here tags the bet, it does not open it. */}
      <div className="pb-3">
        <PickSourceChips ticker={bet.ticker} block={pickSources} />
      </div>
    </li>
  );
}

/** The headline's since-date (month and day), in the display zone like
 *  every other human-facing clock here. */
function sinceDate(ms: number): string {
  return new Date(ms).toLocaleDateString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
  });
}

/** The record's first day, with the year: a first day is a claim about
 *  history and the year is part of it. */
function firstDay(ms: number): string {
  return new Date(ms).toLocaleDateString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${SHELL_WIDTH} px-4 py-12 sm:px-6 sm:py-16 xl:px-8`}>
      {children}
    </div>
  );
}
