"use client";

/**
 * The market's price history, drawn in plain SVG — no chart library.
 *
 * Two views. **Line** mirrors Kalshi's own app: both sides over time, YES and
 * NO summing to 100, each labelled with its latest percent at the right edge.
 * **Candles** is the trader's view of the YES price alone: one bar per time
 * slice carrying open/high/low/close, filled by direction.
 *
 * Honesty rules, and they are why some pixels are missing on purpose:
 * - A candle whose price is unreadable is a **gap**, never a bar at zero — a
 *   settled loser genuinely trades at 0, so a zero drawn for "unknown" would
 *   be indistinguishable from data.
 * - This is **history, not a quote**. Nothing here is a price anyone can
 *   transact at now; the tradeable number is the ask, on the slate. The page
 *   says so under the chart rather than leaving it to be inferred.
 *
 * The y-domain fits the data with headroom instead of pinning 0–100: a
 * moneyline living between 30 and 70 drawn on the full axis is a flat line,
 * and a flat line reads as "nothing happened", which is a claim.
 */

import { useMemo } from "react";

import type { ChartCandle } from "@/lib/api";

const W = 360;
const H = 220;
const PAD = { top: 12, right: 46, bottom: 20, left: 8 };
const PW = W - PAD.left - PAD.right;
const PH = H - PAD.top - PAD.bottom;

type Span = { lo: number; hi: number };

function fitDomain(values: number[]): Span {
  if (values.length === 0) return { lo: 0, hi: 1000 };
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  const headroom = Math.max((hi - lo) * 0.15, 20);
  lo = Math.max(0, lo - headroom);
  hi = Math.min(1000, hi + headroom);
  if (hi - lo < 40) {
    const mid = (hi + lo) / 2;
    lo = Math.max(0, mid - 20);
    hi = Math.min(1000, mid + 20);
  }
  return { lo, hi };
}

function pct(tenths: number): string {
  // One decimal, trimmed when whole: ~25% of Kalshi markets tick in
  // deci-cents, and the one screen entirely about price must not round the
  // tick away.
  return `${(tenths / 10).toFixed(1).replace(/\.0$/, "")}%`;
}

/**
 * Collapse candles into at most `buckets` OHLC bars.
 *
 * A day at 1-minute intervals is 1,440 bars in ~280px — every bar a
 * sub-pixel sliver, and 43 of 46 real fixture candles have high == low, so
 * the un-bucketed view is a smear that reads as volatility. Aggregation is
 * the standard OHLC identity: first open, last close, extreme high/low,
 * summed volume; bars whose members all lack a price stay gaps.
 */
function resample(candles: ChartCandle[], buckets: number): ChartCandle[] {
  if (candles.length <= buckets) return candles;
  const size = Math.ceil(candles.length / buckets);
  const out: ChartCandle[] = [];
  for (let i = 0; i < candles.length; i += size) {
    const group = candles.slice(i, i + size);
    const priced = group.filter((c) => c.close_tenths !== null);
    const highs = group
      .map((c) => c.high_tenths)
      .filter((v): v is number => v !== null);
    const lows = group
      .map((c) => c.low_tenths)
      .filter((v): v is number => v !== null);
    const volumes = group
      .map((c) => c.volume)
      .filter((v): v is number => v !== null);
    out.push({
      t_ms: group[group.length - 1].t_ms,
      open_tenths: priced.length > 0 ? priced[0].open_tenths : null,
      close_tenths:
        priced.length > 0 ? priced[priced.length - 1].close_tenths : null,
      high_tenths: highs.length > 0 ? Math.max(...highs) : null,
      low_tenths: lows.length > 0 ? Math.min(...lows) : null,
      yes_bid_close_tenths: null,
      yes_ask_close_tenths: null,
      volume: volumes.length > 0 ? volumes.reduce((a, b) => a + b, 0) : null,
    });
  }
  return out;
}

export default function PriceChart({
  candles,
  view,
}: {
  candles: ChartCandle[];
  view: "line" | "candles";
}) {
  const drawn = useMemo(() => {
    const source = view === "candles" ? resample(candles, 48) : candles;
    const usable = source.filter((c) => c.close_tenths !== null);
    if (usable.length === 0) return null;

    const t0 = usable[0].t_ms;
    const t1 = usable[usable.length - 1].t_ms;
    const x = (t: number) =>
      PAD.left + (t1 === t0 ? PW / 2 : ((t - t0) / (t1 - t0)) * PW);

    const yesValues = usable.map((c) => c.close_tenths as number);
    const domain =
      view === "line"
        ? // Both lines share one axis, so the domain must hold YES and its
          // complement or one of the two runs off the plot.
          fitDomain([...yesValues, ...yesValues.map((v) => 1000 - v)])
        : fitDomain(
            usable.flatMap((c) =>
              [c.low_tenths, c.high_tenths, c.close_tenths].filter(
                (v): v is number => v !== null,
              ),
            ),
          );
    const y = (v: number) =>
      PAD.top + PH - ((v - domain.lo) / (domain.hi - domain.lo)) * PH;

    const path = (series: number[]) =>
      usable
        .map(
          (c, i) =>
            `${i === 0 ? "M" : "L"}${x(c.t_ms).toFixed(1)},${y(series[i]).toFixed(1)}`,
        )
        .join(" ");

    const gridLevels = [0.25, 0.5, 0.75].map(
      (f) => domain.lo + (domain.hi - domain.lo) * f,
    );
    const last = usable[usable.length - 1];
    return { usable, x, y, path, gridLevels, last, yesValues };
  }, [candles, view]);

  if (!drawn) {
    return (
      <p className="py-16 text-center text-sm text-muted">
        No readable prices in this window.
      </p>
    );
  }

  const { usable, x, y, path, gridLevels, last, yesValues } = drawn;
  const lastYes = last.close_tenths as number;
  const barWidth = Math.max(1.5, (PW / usable.length) * 0.6);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      role="img"
      aria-label="price history"
    >
      {gridLevels.map((level) => (
        <g key={level}>
          <line
            x1={PAD.left}
            x2={PAD.left + PW}
            y1={y(level)}
            y2={y(level)}
            stroke="currentColor"
            className="text-muted"
            strokeOpacity={0.15}
          />
          <text
            x={W - PAD.right + 4}
            y={y(level) + 3}
            className="fill-current text-muted"
            fontSize="8"
          >
            {pct(level)}
          </text>
        </g>
      ))}

      {view === "line" ? (
        <>
          <path
            d={path(yesValues)}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            className="text-positive"
          />
          <path
            d={path(yesValues.map((v) => 1000 - v))}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            className="text-negative"
          />
          <text
            x={W - PAD.right + 4}
            y={y(lastYes) + 3}
            className="fill-current text-positive"
            fontSize="9"
            fontWeight="700"
          >
            Y {pct(lastYes)}
          </text>
          <text
            x={W - PAD.right + 4}
            y={y(1000 - lastYes) + 3}
            className="fill-current text-negative"
            fontSize="9"
            fontWeight="700"
          >
            N {pct(1000 - lastYes)}
          </text>
        </>
      ) : (
        usable.map((c) => {
          const { open_tenths: o, high_tenths: h, low_tenths: l } = c;
          const close = c.close_tenths as number;
          // A bar needs all four prices; anything less draws as a gap.
          if (o === null || h === null || l === null) return null;
          const up = close >= o;
          const cx = x(c.t_ms);
          const top = y(Math.max(o, close));
          const bodyH = Math.max(1, Math.abs(y(o) - y(close)));
          return (
            <g
              key={c.t_ms}
              className={up ? "text-positive" : "text-negative"}
            >
              <line
                x1={cx}
                x2={cx}
                y1={y(h)}
                y2={y(l)}
                stroke="currentColor"
                strokeWidth="1"
              />
              <rect
                x={cx - barWidth / 2}
                y={top}
                width={barWidth}
                height={bodyH}
                fill="currentColor"
              />
            </g>
          );
        })
      )}
    </svg>
  );
}
