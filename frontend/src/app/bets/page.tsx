import Link from "next/link";

import { SHELL_WIDTH } from "@/lib/shell";
import { tickerLabel } from "@/lib/tickerLabel";
import NotTonight from "@/components/NotTonight";
import RecordChart from "@/components/RecordChart";
import OpenPositions from "@/components/OpenPositions";
import Term from "@/components/Term";
import {
  DISPLAY_TIME_ZONE,
  fetchBets,
  type BetKind,
  type BetsRecord,
  type BetsSection,
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

  return (
    <Shell>
      <header className="mb-8">
        <h1 className="display text-4xl sm:text-5xl">Your bets</h1>
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

      <div className="rounded-2xl border border-edge bg-card p-5">
        <div className="text-xs font-semibold uppercase tracking-widest text-muted">
          <Term k="net">Net</Term>, over the whole mirrored record
        </div>
        <p className="mt-2 max-w-[65ch]">
          <span
            className={`display text-3xl ${
              totals.net_tenths < 0 ? "text-negative" : "text-positive"
            }`}
          >
            {totals.net_display}
          </span>
          <span className="ml-3 font-mono text-sm text-muted">
            <Term k="wl">
              {totals.wins}W / {totals.losses}L
            </Term>{" "}
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
        <Link href="/hedge" className="underline decoration-dotted">
          Record it on the hedging screen
        </Link>{" "}
        and the desk will watch its legs while the games run.
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
        <ul className="mt-4 divide-y border-t">
          {record.bets.map((bet, index) =>
            bet.kind === section.kind ? (
              <BetRow
                key={`${bet.ticker}-${bet.settled_ms}-${index}`}
                bet={bet}
              />
            ) : null,
          )}
        </ul>
      )}
    </section>
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
 * One settled position. The result word and the net are the row's facts;
 * the ticker links to the market screen, which knows how to say what the
 * market was. A refused net renders "—" with the reason class in the words
 * above — never a zero, and never a hidden row. The CLV line is drawn for a
 * single game only: a combination market has no close to be read, and the
 * absence of a line says so better than any words would.
 */
function BetRow({ bet }: { bet: SettledBet }) {
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
  return (
    <li>
      <Link
        href={`/market/${encodeURIComponent(bet.ticker)}`}
        className="flex items-baseline gap-3 py-4 transition-colors hover:bg-accent-soft"
      >
        <span className="min-w-0 flex-1">
          {/* tickerLabel keeps the TAIL — CSS truncate cuts the right end,
              which on a combo shard is the only identifying part, so every
              combo row rendered identically (2026-08-22 review). The full
              ticker stays in title= for hover and copy. */}
          <span
            className="block truncate font-mono text-sm font-semibold"
            title={bet.ticker}
          >
            {tickerLabel(bet.ticker)}
          </span>
          <span className="mt-0.5 block text-xs text-muted">
            {contracts} × {bet.side.toUpperCase()} at{" "}
            {bet.entry_price_display} · settled {settled}
          </span>
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
