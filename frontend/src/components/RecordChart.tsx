import type { SettledBet } from "@/lib/api";

/**
 * Money in and out, cumulatively, in settlement order.
 *
 * WHAT THIS IS ALLOWED TO BE
 * --------------------------
 * A **fact**: this is what happened to the money. Nothing here is scored
 * against a benchmark, fitted, or annualised.
 *
 * WHAT IT IS NOT ALLOWED TO BECOME, and the rule is not mine
 * ----------------------------------------------------------
 * `docs/reviews/2026-08-21-items-2-3-ruling.md` re-scoped "CLV on his own
 * bets" to *"per-bet rows only — your price, Kalshi's close, the difference —
 * **no average, no hit rate** until n >= 30 with the per-group view beside
 * it."* `backend/bets.py` carries the same sentence in its own docstring and
 * computes none.
 *
 * So: no trend line, no win rate, no "you beat the close X% of the time", and
 * no CLV series. A fitted line through a dozen settlements is a claim about
 * skill that the record cannot support, and it is the most ego-loaded quantity
 * in the product.
 *
 * THE HONESTY THAT COSTS SOMETHING
 * --------------------------------
 * **A cumulative total cannot step over a row it could not compute.**
 * `net_tenths` is `null` when the venue's record does not support the
 * registered settlement formula. Skipping such a row would silently assert it
 * was worth zero; carrying the previous value forward would assert nothing
 * changed. Both are claims.
 *
 * What is true instead: after the first uncomputable settlement, every later
 * point is a **lower bound**, not a value. The line is drawn dashed from that
 * point on and the caption says so, rather than the chart looking exact when
 * it is not.
 *
 * COLOUR
 * ------
 * The line is ink. `--positive`/`--negative` are reserved for polarity and a
 * cumulative balance has none at a point — it is one series, and colouring it
 * by whether it is currently above zero would repaint history every time a bet
 * settles. Only the zero rule is drawn, in `--border`.
 */

const W = 320;
const H = 120;
const PAD = { top: 10, right: 46, bottom: 16, left: 8 };
const PW = W - PAD.left - PAD.right;
const PH = H - PAD.top - PAD.bottom;

type Point = { x: number; cumulative: number; exact: boolean };

export function cumulative(bets: SettledBet[]): {
  points: Point[];
  uncomputable: number;
} {
  // Settlement order, oldest first: the payload arrives newest-first.
  const ordered = [...bets]
    .filter((b) => typeof b.settled_ms === "number")
    .sort((a, b) => (a.settled_ms as number) - (b.settled_ms as number));

  const points: Point[] = [];
  let running = 0;
  let exact = true;
  let uncomputable = 0;

  for (const bet of ordered) {
    if (typeof bet.net_tenths !== "number") {
      // Not zero, not skipped: from here on the total is a floor.
      uncomputable += 1;
      exact = false;
      continue;
    }
    running += bet.net_tenths;
    points.push({ x: points.length, cumulative: running, exact });
  }
  return { points, uncomputable };
}

function dollars(tenths: number): string {
  const sign = tenths < 0 ? "-" : "";
  return `${sign}$${(Math.abs(tenths) / 1000).toFixed(2)}`;
}

export default function RecordChart({ bets }: { bets: SettledBet[] }) {
  const { points, uncomputable } = cumulative(bets);

  // Two settled bets is the least that can show a direction. One point is a
  // dot, and a dot drawn as a chart implies a trend it cannot have.
  if (points.length < 2) return null;

  const values = points.map((p) => p.cumulative);
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const span = hi - lo || 1;

  const x = (i: number) => PAD.left + (i / (points.length - 1)) * PW;
  const y = (v: number) => PAD.top + PH - ((v - lo) / span) * PH;

  // One path while every point is exact, a second dashed one after the first
  // uncomputable settlement. They share the boundary point so the line does
  // not break visually — only its certainty changes.
  const firstApprox = points.findIndex((p) => !p.exact);
  const exactPoints = firstApprox === -1 ? points : points.slice(0, firstApprox);
  const boundPoints = firstApprox === -1 ? [] : points.slice(Math.max(0, firstApprox - 1));

  const draw = (pts: Point[]) =>
    pts
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.x).toFixed(1)} ${y(p.cumulative).toFixed(1)}`)
      .join(" ");

  const last = points[points.length - 1];

  return (
    <figure className="mt-4">
      <figcaption className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">
        money in and out, settlement by settlement
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="mt-1 w-full max-w-[24rem] text-foreground"
        role="img"
        aria-label={
          `Cumulative net over ${points.length} settled bets, ending ` +
          `${dollars(last.cumulative)}${last.exact ? "" : " or better"}.`
        }
      >
        {/* Zero. The only reference a money line needs. */}
        <line
          x1={PAD.left}
          y1={y(0)}
          x2={PAD.left + PW}
          y2={y(0)}
          stroke="var(--border)"
          strokeWidth="1"
        />
        {exactPoints.length > 1 && (
          <path d={draw(exactPoints)} fill="none" stroke="currentColor" strokeWidth="2" />
        )}
        {boundPoints.length > 1 && (
          <path
            d={draw(boundPoints)}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeDasharray="3 3"
          />
        )}
        <text
          x={PAD.left + PW + 4}
          y={y(last.cumulative) + 3}
          className="fill-current font-mono text-[10px]"
        >
          {dollars(last.cumulative)}
        </text>
      </svg>
      <p className="mt-1 max-w-[65ch] text-[11px] text-muted">
        {points.length} settled bet{points.length === 1 ? "" : "s"}, oldest
        first.
        {uncomputable > 0 && (
          <>
            {" "}
            {uncomputable} settlement{uncomputable === 1 ? "" : "s"} could not
            be computed from the venue&rsquo;s record, so the dashed part is a
            floor rather than a figure.
          </>
        )}
      </p>
    </figure>
  );
}
