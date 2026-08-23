"use client";

/**
 * One game's screen: the desk first, the venue's facts, the chart on request.
 *
 * Rebuilt 2026-08-21 to the partner's direction after Joe asked for the page
 * to be "more useful". The ruling that shaped it: **render the venue's facts,
 * never the tool's opinion.** Ask, quote age, market status, start time —
 * those are what you transact against. Fair, edge, EV, size — the refuted
 * consensus signal (ADR 0038) — do not appear on a single-game page, which is
 * the screen with the least context to hold such a number honestly.
 *
 * Order matters: the scout desk renders first because the ui-designer
 * measured the old layout and found the briefing's headline started below the
 * fold at every width — Joe read a wall of words partly because it was the
 * first content he reached. The chart lives in a closed <details>; its
 * "history, not a quote" caveat moves into the summary line, because
 * collapsing the chart must not hide the sentence that exists precisely
 * because charts imply prices.
 *
 * The clock everywhere here is the linked sportsbook fixture's, served by
 * `/api/market/{ticker}` — never `kalshi_events.commence_ms`, which is the
 * expected *end* (~3h late on game series, ADR 0006).
 *
 * Two boundaries carried over from the old page, both deliberate:
 * - **History, not a quote.** The chart is Kalshi's candlesticks; the ask in
 *   the quote strip is refused outright once its age exceeds the staleness
 *   limit, rather than greyed — a single-game page has no fresher list beside
 *   it to give a stale number the lie.
 * - **Nothing here touches the calibration study.** No estimate flow, no
 *   study-scoped aggregate; the study is stopped and pointing at it would be
 *   misdirection.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import {
  DISPLAY_TIME_ZONE,
  fetchMarketCandles,
  fetchMarketDetail,
  type MarketCandles,
  type MarketDetail,
} from "@/lib/api";
import ManualTicket from "@/components/ManualTicket";
import PassControl from "@/components/PassControl";
import PriceChart from "@/components/PriceChart";
import ScoutDesk from "@/components/ScoutDesk";
import Term from "@/components/Term";
import { SHELL_WIDTH } from "@/lib/shell";
import { kalshiMarketUrl } from "@/lib/kalshiLink";
import { leagueLabel } from "@/lib/leagueLabel";

const RANGES = [
  { key: "1d", label: "Today" },
  { key: "all", label: "All" },
] as const;
type Range = (typeof RANGES)[number]["key"];

function clock(ms: number): string {
  return new Date(ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function agoWord(ms: number): string {
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)}h`;
  return `${Math.round(ms / 86_400_000)}d`;
}

/** Where this market is in its life, from the venue's own fields. A settled
 * market must not render like a live one: "this market closed 14 hours ago"
 * is a complete answer to "should I bet this". */
function statusLine(detail: MarketDetail, now: number): string {
  const status = (detail.market_status ?? "").toLowerCase();
  if (status === "finalized" || status === "settled") {
    return "Settled — this market has paid out. Nothing here is buyable.";
  }
  if (detail.close_ms !== null && detail.close_ms <= now) {
    return `Closed ${agoWord(now - detail.close_ms)} ago — no longer buyable.`;
  }
  if (detail.commence_ms !== null) {
    return detail.commence_ms > now
      ? `Starts ${clock(detail.commence_ms)}`
      : `Started ${clock(detail.commence_ms)} — likely in play or finished.`;
  }
  return "Start time unknown — no linked sportsbook fixture.";
}

function QuoteStrip({
  detail,
  now,
  kalshiUrl,
}: {
  detail: MarketDetail;
  now: number;
  kalshiUrl: string;
}) {
  const status = (detail.market_status ?? "").toLowerCase();
  const dead =
    status === "finalized" ||
    status === "settled" ||
    (detail.close_ms !== null && detail.close_ms <= now);
  if (dead) return null;

  const age = detail.quote_age_now_ms;
  // Refused outright, not greyed: a stale ask on a page with no fresher rows
  // beside it reads as a price, and it is not one.
  if (detail.price_is_current !== true || age === null || age === undefined) {
    return (
      <div className="mt-3 rounded-xl border border-dashed border-border-strong px-3 py-2 text-sm text-muted">
        <p className="max-w-[65ch]">
          The recorded ask is{" "}
          {age !== null && age !== undefined
            ? `${agoWord(age)} old`
            : "of unknown age"}
          {" "}— not a price you can transact on. The live book is{" "}
          <a
            href={kalshiUrl}
            target="_blank"
            rel="noreferrer"
            className="font-semibold underline"
          >
            on Kalshi ↗
          </a>
          .
        </p>
      </div>
    );
  }
  // No size step at any width: the ask never exceeds body size, because a
  // page whose hero is a price says "buy" (the convening's rule for the
  // record).
  return (
    <div className="mt-3 rounded-xl border px-3 py-2 text-sm">
      <p className="max-w-[65ch]">
        <span className="font-semibold tabular">
          Ask ${detail.ask_dollars.toFixed(2)}
        </span>
        <span className="text-muted">
          {" "}per YES <Term k="contract">contract</Term> · quote checked{" "}
          {agoWord(age)} ago
        </span>
      </p>
    </div>
  );
}

export default function MarketPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker);
  const [range, setRange] = useState<Range>("all");
  const [data, setData] = useState<MarketCandles | null>(null);
  const [detail, setDetail] = useState<MarketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchMarketCandles(ticker, range)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err) => {
        if (!cancelled) {
          setData(null);
          setError(err instanceof Error ? err.message : "unavailable");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, range]);

  useEffect(() => {
    let cancelled = false;
    setNow(Date.now());
    fetchMarketDetail(ticker)
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      // The chart and the desk stand on their own; a missing detail row is
      // "the runner never priced this", not a page error.
      .catch(() => {
        if (!cancelled) setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  // Three header states, drawn apart (2026-08-22 review, A8): this page
  // rendered the literal string "Market" for loading AND for
  // nothing-found, which are opposite claims — one asks for patience, the
  // other answers the question.
  const stillLoading = loading || detailLoading;
  const nothingFound = !stillLoading && detail === null && data === null;
  const matchup =
    detail?.home_team && detail?.away_team
      ? `${detail.away_team} @ ${detail.home_team}`
      : (data?.title ??
        detail?.event_title ??
        (stillLoading ? "Loading…" : ticker));
  const kalshiUrl = kalshiMarketUrl(ticker);
  const league = detail?.league ? leagueLabel(detail.league) : null;

  const totalVolume = data
    ? data.candles.reduce((sum, c) => sum + (c.volume ?? 0), 0)
    : 0;

  return (
    <main className={`${SHELL_WIDTH} px-4 py-8 sm:px-6 sm:py-12 xl:px-8`}>
      <header className="mb-4">
        <h1 className="display text-3xl sm:text-4xl xl:text-5xl">{matchup}</h1>
        {detail?.team && (
          <p className="mt-1 max-w-[65ch] text-sm font-semibold">
            YES = {detail.team}
            <span className="ml-2 font-normal text-muted">
              this contract pays $1 if the {detail.team} win
            </span>
          </p>
        )}
        <p className="mt-1 max-w-[65ch] text-sm text-muted">
          {league && <span>{league} · </span>}
          {detail ? statusLine(detail, now) : ""}
        </p>
        {nothingFound && (
          <p className="mt-2 max-w-[65ch] text-sm text-muted">
            Nothing is recorded here for this ticker — the recorder never
            priced it, which is not the same as the market not existing.
          </p>
        )}
        {/* The escape hatch this app never had (A7): scheme verified in a
            browser 2026-08-22, built in lib/kalshiLink.ts. External link on
            purpose — it leaves the cockpit and says so. */}
        <p className="mt-2 max-w-[65ch] text-sm">
          <a
            href={kalshiUrl}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-accent underline"
          >
            Open on Kalshi ↗
          </a>
        </p>
        {detail && <QuoteStrip detail={detail} now={now} kalshiUrl={kalshiUrl} />}
      </header>

      {/* The desk first: the reason this page exists is what the scouts know
          about THIS game, and it must start above the fold at every width. */}
      <ScoutDesk ticker={ticker} />

      {/* The manual ticket (ADR 0063/0065): below the desk's facts, above
          the history. It self-reports its own unreachable states (demo, flag
          off, lockout, cool-off) in words, so mounting it unconditionally is
          honest on every instance. */}
      <ManualTicket ticker={ticker} />

      {/* The calm alternative (ADR 0066): a quiet row below the ticket's
          card, deliberately NOT styled as its sibling — passing must read as
          stepping back from the decision, not as the decision's other
          button. It records and does not hide; the facts above stay put. */}
      <PassControl ticker={ticker} />

      <p className="mt-2 max-w-[65ch] font-mono text-xs text-muted">{ticker}</p>

      <details className="mt-6 rounded-2xl border bg-card px-4 py-3 sm:px-6">
        <summary className="cursor-pointer text-sm font-semibold">
          Price history
          <span className="ml-2 font-normal text-muted">
            — history, not a quote; the price you&rsquo;d pay is the{" "}
            <Term k="ask">ask</Term>
          </span>
        </summary>
        <div className="mt-4">
          <div className="mb-4 flex gap-1">
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => setRange(r.key)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold uppercase ${
                  range === r.key ? "bg-accent text-white" : "border text-muted"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {loading ? (
            <p className="mx-auto max-w-[65ch] py-16 text-center text-sm text-muted">
              Loading&hellip;
            </p>
          ) : error ? (
            <p className="mx-auto max-w-[65ch] py-16 text-center text-sm text-muted">{error}</p>
          ) : data ? (
            <>
              {/* YES only: NO is 1000 - YES by arithmetic, so a second line
                  halves the vertical resolution to restate the first. */}
              <PriceChart candles={data.candles} view="line" yesOnly />
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs text-muted">
                <span>
                  <Term k="volume">volume</Term> in window:{" "}
                  <span className="tabular">
                    {totalVolume.toLocaleString("en-US", {
                      maximumFractionDigits: 0,
                    })}
                  </span>
                  {/* Honest coverage: a bar with no trades is a gap, and a
                      footer that only counts unparseable bars reassures while
                      half the chart is missing. */}
                  <span className="ml-2 tabular">
                    ·{" "}
                    {data.candles.filter((c) => c.close_tenths !== null).length}{" "}
                    of {data.candles.length} bars traded
                  </span>
                  {data.dropped_unreadable > 0 && (
                    <span className="ml-2">
                      ({data.dropped_unreadable} unreadable, dropped)
                    </span>
                  )}
                </span>
              </div>
            </>
          ) : null}
        </div>
      </details>
    </main>
  );
}
