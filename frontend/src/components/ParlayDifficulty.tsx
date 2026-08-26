/**
 * How a parlay's chance collapses as legs are added.
 *
 * The picture behind a sentence the payload already carries verbatim
 * (`parlays.NOTES["chance"]`): *"A parlay multiplies chances down: six 65% legs
 * land together about 8% of the time."* This draws that for THIS card's own
 * legs, in the ladder's own order, rather than illustrating it with invented
 * numbers.
 *
 * FORM, and why it is this one
 * ---------------------------
 * The data's job is change over a count, so: one line, one axis, x = legs
 * included, y = chance they all land.
 *
 * **There is deliberately no payout series, and it is barred twice over.** A
 * second y-scale is the single most common charting mistake and is never
 * correct; and "chance falls while payout rises" is an expected-value claim,
 * which `/api/parlays` carries none of by construction (ADR 0038, ADR 0070) and
 * `tests/test_parlays_api.py` walks the payload keys to keep it that way.
 *
 * **One series, so no legend** — the heading names it. Values are labelled
 * selectively (first and last only); a number on every point is noise.
 *
 * COLOUR
 * ------
 * None. Every mark is an ink token — `currentColor` for the line, `--muted`
 * for the axis, `--border` for the baseline — exactly as `PriceChart.tsx`
 * does. This repo's `--accent` is the same red as `--negative` in both themes
 * and `tests/test_palette_contrast.py` already forbids a stat wearing it, so a
 * coloured series here would read as a verdict on a number that is not one.
 * Identity comes from position and shape.
 *
 * HONESTY
 * -------
 * - **The curve is the plain product of the leg chances**, which is what the
 *   server sends. The card's headline is the correlation-adjusted joint, and
 *   the two differ by `independence_error_points` — a figure the payload
 *   already computes and which is stated under the chart rather than hidden.
 *   Re-running the copula at every prefix would be six more 200,000-sample
 *   Monte-Carlo runs per card for a difference measured in hundredths of a
 *   point.
 * - **The y-axis starts at zero**, because the subject is how far the number
 *   falls. A fitted axis would flatten exactly the collapse this exists to
 *   show — the opposite of `PriceChart`'s reasoning, where the subject is
 *   movement within a narrow band.
 * - **A card with one leg draws nothing.** One point is not a collapse.
 */

import type { ParlayPrefix } from "@/lib/api";

const W = 320;
const H = 132;
const PAD = { top: 10, right: 40, bottom: 22, left: 8 };
const PW = W - PAD.left - PAD.right;
const PH = H - PAD.top - PAD.bottom;

export default function ParlayDifficulty({
  prefixes,
  independenceNote,
}: {
  prefixes: ParlayPrefix[];
  independenceNote: string | null;
}) {
  // One point is one leg, and a single point cannot show a collapse.
  if (prefixes.length < 2) return null;

  const top = prefixes[0].chance;
  if (!(top > 0)) return null;

  const x = (i: number) =>
    PAD.left + (prefixes.length === 1 ? 0 : (i / (prefixes.length - 1)) * PW);
  // Zero-based on purpose: the subject is the size of the fall.
  const y = (p: number) => PAD.top + PH - (p / top) * PH;

  const path = prefixes
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(p.chance).toFixed(1)}`)
    .join(" ");

  const last = prefixes[prefixes.length - 1];

  return (
    <figure className="mt-3">
      <figcaption className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">
        every leg you add multiplies the chance down
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="mt-1 w-full max-w-[22rem] text-foreground"
        role="img"
        aria-label={
          `Chance all legs land, by number of legs: ` +
          prefixes
            .map((p) => `${p.legs} leg${p.legs === 1 ? "" : "s"} ${p.chance_percent_display}`)
            .join(", ")
        }
      >
        {/* Baseline only. A grid would out-weigh two dozen pixels of data. */}
        <line
          x1={PAD.left}
          y1={PAD.top + PH}
          x2={PAD.left + PW}
          y2={PAD.top + PH}
          stroke="var(--border)"
          strokeWidth="1"
        />
        <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
        {prefixes.map((p, i) => (
          <circle
            key={p.legs}
            cx={x(i)}
            cy={y(p.chance)}
            r="4"
            fill="currentColor"
            /* A 2px surface ring, so a dot that lands on the line stays legible. */
            stroke="var(--card)"
            strokeWidth="2"
          />
        ))}

        {/* Selective direct labels: the two ends carry the story. */}
        <text
          x={x(0)}
          y={y(prefixes[0].chance) - 8}
          className="fill-current font-mono text-[10px]"
        >
          {prefixes[0].chance_percent_display}
        </text>
        <text
          x={PAD.left + PW + 4}
          y={y(last.chance) + 3}
          className="fill-current font-mono text-[10px]"
        >
          {last.chance_percent_display}
        </text>

        {prefixes.map((p, i) => (
          <text
            key={p.legs}
            x={x(i)}
            y={H - 6}
            textAnchor="middle"
            className="fill-[var(--muted)] font-mono text-[9px]"
          >
            {p.legs}
          </text>
        ))}
        <text
          x={PAD.left + PW / 2}
          y={H - 6}
          textAnchor="middle"
          className="fill-[var(--muted)] font-mono text-[9px]"
          opacity="0"
        >
          legs
        </text>
      </svg>
      <p className="mt-1 text-[11px] text-muted">
        Legs included, left to right. {independenceNote}
      </p>
    </figure>
  );
}
