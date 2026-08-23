import Link from "next/link";

import { SHELL_WIDTH } from "@/lib/shell";
import { tickerLabel } from "@/lib/tickerLabel";
import NotTonight from "@/components/NotTonight";
import OpenPositions from "@/components/OpenPositions";
import Term from "@/components/Term";
import {
  DISPLAY_TIME_ZONE,
  fetchBets,
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
 * - **This is the mirror, not the account.** Open positions are structurally
 *   absent (a settlement exists only after the venue settles), and anything
 *   settled before the poller existed or while it was down is missing. The
 *   page says so in words rather than presenting itself as complete.
 * - **No opinion.** Nothing here scores, grades, or advises; the estimate
 *   log stays embargoed (the study stopped without result) and this page
 *   never touches it. It is a bank statement, not a report card.
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
        <p className="mt-3 max-w-[65ch] text-lg text-muted">
          Every settled position the recorder has mirrored from your Kalshi
          account, newest first — the venue&rsquo;s own numbers, read back to
          you.
        </p>
      </header>

      <div className="rounded-2xl border bg-card p-5">
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
        {/* The denominator the per-bet CLV numbers never had (B5): most
            hand-bet tickers refuse structurally (no discovery row, no
            close read), and without this line 35 rows saying "close not
            read yet" and 35 rows saying the bets were bad would read the
            same at a glance. Counts only — no average, no hit rate. */}
        {record.clv_coverage && (
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            <Term k="clv">CLV</Term> scored on {record.clv_coverage.scored} of{" "}
            {record.total} — the rest refused (no readable close yet, or no
            entry time). Unmeasured is not the same as bad; each row below
            says which it is.
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
        <p className="mt-2 max-w-[65ch] text-xs text-muted">
          This is the recorder&rsquo;s mirror, not your account: open positions
          are not here (a settlement exists only after the venue settles), and
          anything settled before the recorder started on Aug 18 is missing.
          Fees are the venue&rsquo;s own, already subtracted.
        </p>
      </div>

      {/* What is at risk right now (B3), above the settled list: the settled
          record alone hides the money currently on the table. Unsigned,
          never summed with the net strip above. */}
      <div className="mt-4 max-w-[65ch]">
        <OpenPositions block={record.open_positions} />
      </div>

      {record.bets.length === 0 ? (
        <p className="mt-8 max-w-[65ch] text-sm text-muted">
          Nothing has settled since the recorder started watching. When a
          position you hold settles, it appears here on the next poll.
        </p>
      ) : (
        <>
          <h2 className="mt-10 text-sm font-semibold uppercase tracking-widest text-muted">
            Settled positions
          </h2>
          <ul className="mt-4 divide-y border-t">
            {record.bets.map((bet, index) => (
              <BetRow key={`${bet.ticker}-${bet.settled_ms}-${index}`} bet={bet} />
            ))}
          </ul>
          {record.returned < record.total && (
            <p className="mt-3 max-w-[65ch] text-xs text-muted">
              Showing the most recent {record.returned} of {record.total} —
              the net strip above still covers all {record.total}.
            </p>
          )}
        </>
      )}
    </Shell>
  );
}

/**
 * One settled position. The result word and the net are the row's facts;
 * the ticker links to the market screen, which knows how to say what the
 * market was. A refused net renders "—" with the reason class in the words
 * above — never a zero, and never a hidden row.
 */
/**
 * Words for a refused per-bet CLV, in place of the number. No reason ever
 * substitutes a value -- `bet.clv_display` stays null and this is the only
 * thing rendered instead.
 */
const CLV_REFUSAL_WORDS: Record<string, string> = {
  no_closing_line: "close not read yet",
  unreadable_close: "close unreadable",
  entry_time_unknown: "entry time unknown",
  entry_after_close: "entered after close",
};

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
          <span
            className={`mt-0.5 block text-xs ${
              bet.clv_tenths !== null && bet.clv_tenths < 0
                ? "text-negative"
                : "text-muted"
            }`}
          >
            {clvWords}
          </span>
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

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${SHELL_WIDTH} px-4 py-12 sm:px-6 sm:py-16 xl:px-8`}>
      {children}
    </div>
  );
}
