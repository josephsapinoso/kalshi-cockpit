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
import PriceChart from "@/components/PriceChart";
import ScoutDesk from "@/components/ScoutDesk";
import Term from "@/components/Term";

const RANGES = [
  { key: "1d", label: "Today" },
  { key: "all", label: "All" },
] as const;
type Range = (typeof RANGES)[number]["key"];

/** The handful of sport keys this repo actually sweeps; anything else renders
 * raw rather than guessed at. */
const LEAGUE_LABELS: Record<string, string> = {
  baseball_mlb: "MLB",
  basketball_nba: "NBA",
  basketball_wnba: "WNBA",
  americanfootball_nfl: "NFL",
  icehockey_nhl: "NHL",
};

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

function QuoteStrip({ detail, now }: { detail: MarketDetail; now: number }) {
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
      <p className="mt-3 rounded-xl border border-dashed border-border-strong px-3 py-2 text-sm text-muted">
        The recorded ask is{" "}
        {age !== null && age !== undefined ? `${agoWord(age)} old` : "of unknown age"}
        {" "}— not a price you can transact on. The live book is on Kalshi.
      </p>
    );
  }
  return (
    <p className="mt-3 rounded-xl border px-3 py-2 text-sm">
      <span className="font-semibold tabular">
        Ask ${detail.ask_dollars.toFixed(2)}
      </span>
      <span className="text-muted">
        {" "}per YES contract · quote checked {agoWord(age)} ago
      </span>
    </p>
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
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const matchup =
    detail?.home_team && detail?.away_team
      ? `${detail.away_team} @ ${detail.home_team}`
      : (data?.title ?? detail?.event_title ?? "Market");
  const league = detail?.league
    ? (LEAGUE_LABELS[detail.league] ?? detail.league)
    : null;

  const totalVolume = data
    ? data.candles.reduce((sum, c) => sum + (c.volume ?? 0), 0)
    : 0;

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <header className="mb-4">
        <h1 className="display text-3xl sm:text-4xl">{matchup}</h1>
        {detail?.team && (
          <p className="mt-1 text-sm font-semibold">
            YES = {detail.team}
            <span className="ml-2 font-normal text-muted">
              this contract pays $1 if the {detail.team} win
            </span>
          </p>
        )}
        <p className="mt-1 text-sm text-muted">
          {league && <span>{league} · </span>}
          {detail ? statusLine(detail, now) : ""}
        </p>
        {detail && <QuoteStrip detail={detail} now={now} />}
        <p className="mt-1 font-mono text-xs text-muted">{ticker}</p>
      </header>

      {/* The desk first: the reason this page exists is what the scouts know
          about THIS game, and it must start above the fold at every width. */}
      <ScoutDesk ticker={ticker} />

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
            <p className="py-16 text-center text-sm text-muted">
              Loading&hellip;
            </p>
          ) : error ? (
            <p className="py-16 text-center text-sm text-muted">{error}</p>
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
