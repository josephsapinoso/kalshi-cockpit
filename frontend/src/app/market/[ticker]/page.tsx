"use client";

/**
 * One market's price history — the screen Joe asked for by screenshot:
 * Kalshi's own app view, on the cockpit. Line view shows both sides; the
 * candlestick toggle shows the trader's OHLC bars; 1D/1W/1M/ALL ranges.
 *
 * Two boundaries, both deliberate:
 * - **History, not a quote.** The chart is drawn from Kalshi's candlesticks;
 *   the price anyone can transact at is the ask, on the slate. Said in the
 *   footer of the chart, not left to be inferred.
 * - **Nothing here touches the calibration study.** This page renders public
 *   market history only — never `bet_estimates`' captured quotes, never any
 *   study-scoped aggregate. Logging an estimate first, before browsing a
 *   price, remains the study's whole discipline; this page does not link
 *   into the estimate flow for exactly that reason.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import {
  DISPLAY_TIME_ZONE,
  fetchMarketCandles,
  type MarketCandles,
} from "@/lib/api";
import PriceChart from "@/components/PriceChart";
import Term from "@/components/Term";

const RANGES = ["1d", "1w", "1m", "all"] as const;
type Range = (typeof RANGES)[number];

export default function MarketPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker);
  const [range, setRange] = useState<Range>("1w");
  const [view, setView] = useState<"line" | "candles">("line");
  const [data, setData] = useState<MarketCandles | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

  const totalVolume = data
    ? data.candles.reduce((sum, c) => sum + (c.volume ?? 0), 0)
    : 0;
  const span =
    data && data.candles.length > 0
      ? {
          from: data.candles[0].t_ms,
          to: data.candles[data.candles.length - 1].t_ms,
        }
      : null;

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <header className="mb-6">
        <h1 className="display text-3xl sm:text-4xl">
          {data?.title ?? "Market"}
        </h1>
        <p className="mt-1 font-mono text-xs text-muted">{ticker}</p>
      </header>

      <section className="rounded-2xl border bg-card p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-1">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold uppercase ${
                  range === r ? "bg-accent text-white" : "border text-muted"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => setView("line")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                view === "line" ? "bg-accent text-white" : "border text-muted"
              }`}
            >
              Line
            </button>
            <button
              onClick={() => setView("candles")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                view === "candles" ? "bg-accent text-white" : "border text-muted"
              }`}
            >
              Candles
            </button>
          </div>
        </div>

        {loading ? (
          <p className="py-16 text-center text-sm text-muted">Loading&hellip;</p>
        ) : error ? (
          <p className="py-16 text-center text-sm text-muted">{error}</p>
        ) : data ? (
          <>
            <PriceChart candles={data.candles} view={view} />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs text-muted">
              <span>
                <Term k="volume">volume</Term> in window:{" "}
                <span className="tabular">
                  {totalVolume.toLocaleString("en-US", {
                    maximumFractionDigits: 0,
                  })}
                </span>
                {data.dropped_unreadable > 0 && (
                  <span className="ml-2">
                    ({data.dropped_unreadable} unreadable bars dropped)
                  </span>
                )}
              </span>
              {span && (
                <span className="tabular">
                  {new Date(span.from).toLocaleDateString("en-US", {
                    timeZone: DISPLAY_TIME_ZONE,
                    month: "short",
                    day: "numeric",
                  })}
                  {" – "}
                  {new Date(span.to).toLocaleDateString("en-US", {
                    timeZone: DISPLAY_TIME_ZONE,
                    month: "short",
                    day: "numeric",
                  })}
                </span>
              )}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted">
              History, not a quote: these are Kalshi&rsquo;s{" "}
              <Term k="candlestick">candlestick</Term> records of the traded
              price. The price you would actually pay right now is the{" "}
              <Term k="ask">ask</Term>, on the Slate.
            </p>
          </>
        ) : null}
      </section>
    </main>
  );
}
