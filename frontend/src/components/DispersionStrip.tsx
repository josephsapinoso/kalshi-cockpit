import { asPercent, dispersion } from "@/lib/dispersion";
import type { DispersionInput } from "@/lib/dispersion";

/**
 * The books' disagreement, as a range behind a tap.
 *
 * Until 2026-08-21 this drew an axis: the book span as a bar, the four devig
 * readings as marks with the one the sizer used inked taller, and Kalshi's
 * ask as a dashed line among them. The partner's betting-desk ruling
 * (docs/reviews/2026-08-21-items-2-3-ruling.md, re-affirming the standing
 * "strip the landing screen" item) took all three claims off the landing
 * screen:
 *
 * - **No direction.** Drawing the ask against the readings renders "Kalshi
 *   is low/high here" — the tool's opinion of an edge, which ADR 0062 ruled
 *   is a feature and not a determiner. The ask itself is already on the row
 *   as the price; where it sits relative to anyone's reading is the
 *   reader's own judgement to make.
 * - **No `used` mark.** Inking the reading the sizer picked re-renders the
 *   discredited point estimate one layer down.
 * - **A range, not a figure.** What survives is the honest fact the strip
 *   always carried: how much the readings disagree among themselves, in
 *   points — which is exactly the number that bounds how seriously any
 *   single reading deserves to be taken.
 *
 * Behind a `<details>` tap because a per-row drawing was density the row no
 * longer earns; the summary line still shows the spread in points on every
 * width, so the phone reader ADR 0052 argued for still sees the magnitude
 * without a tap — what moved behind the tap is the breakdown, not the fact.
 *
 * Still refuses to render at all on fewer than two distinct readings (one
 * point reading as perfect agreement is the opposite of "only one could be
 * read"), still never says the word the row reserves for its own chosen
 * number, and the bar's population is still labelled — the books' span
 * plots each book's worst reading, which is a fact about the statistic and
 * not about the market.
 */
/**
 * Where the number came from, drawn on one axis.
 *
 * **This restores an axis that was deliberately deleted on 2026-08-21, and it
 * restores it on ONE surface.** That ruling's item is named "strip the landing
 * screen", and it took three claims off the slate row: the ask drawn against
 * the readings, the `used` mark, and a point figure. ADR 0068 puts the desk
 * fully present on `/market/[ticker]`, and ADR 0071 s2.2 makes price
 * transparency that screen's entire job -- so the chart lives there and the
 * slate row keeps its one honest line.
 *
 * What the chart does NOT restore, so the ruling survives where it should:
 *
 * - **No `used` mark.** Inking the reading the sizer picked re-renders the
 *   discredited point estimate one layer down. All four are drawn alike; the
 *   caption says the lowest is the one taken.
 * - **No direction on the ask.** It is a neutral tick with its own label --
 *   no colour, no arrow, no cheap/expensive wording. That is the two prices
 *   side by side ADR 0071 s2.5 permits, not the "Kalshi is low here" verdict
 *   the ruling removed.
 * - **The ask is never clamped onto the scale.** `dispersion()` returns
 *   `x: null` when it falls outside, and the axis is NOT stretched to hold it
 *   -- a 26-point gap would squash four readings 0.4 points apart into one
 *   pixel. Off-scale is said in words. A marker pinned to the end of a scale
 *   it is not on is a drawing that lies.
 */
const CW = 320;
const CH = 58;
const CPAD = { left: 6, right: 6, top: 14, bottom: 16 };
const CPW = CW - CPAD.left - CPAD.right;

export default function DispersionStrip(
  props: DispersionInput & { variant?: "strip" | "chart" },
) {
  const d = dispersion(props);
  if (!d) return null;

  const spreadPoints = (d.domain.hi - d.domain.lo) * 100;
  const methodProbabilities = d.marks.map((m) => m.probability);
  const methodLo = Math.min(...methodProbabilities);
  const methodHi = Math.max(...methodProbabilities);

  if (props.variant === "chart") {
    const at = (x: number) => CPAD.left + x * CPW;
    const mid = CPAD.top + (CH - CPAD.top - CPAD.bottom) / 2;
    return (
      <figure className="w-full max-w-[22rem]">
        <figcaption className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">
          where the number came from
        </figcaption>
        <svg
          viewBox={`0 0 ${CW} ${CH}`}
          className="mt-1 w-full text-foreground"
          role="img"
          aria-label={
            `Devig readings ${asPercent(methodLo)} to ${asPercent(methodHi)}` +
            (d.bookSpan
              ? `; ${d.bookSpan.count} books span ${asPercent(d.bookSpan.lo)} to ${asPercent(d.bookSpan.hi)}`
              : "") +
            (d.kalshi ? `; Kalshi asks ${asPercent(d.kalshi.probability)}` : "")
          }
        >
          {/* The books' own span: a recessive rail the readings sit on. */}
          {d.bookSpan && (
            <>
              <line
                x1={at(d.bookSpan.loX)}
                y1={mid}
                x2={at(d.bookSpan.hiX)}
                y2={mid}
                stroke="var(--border-strong)"
                strokeWidth="2"
                strokeLinecap="round"
              />
              {d.bookSpan.medianX !== null && (
                <circle
                  cx={at(d.bookSpan.medianX)}
                  cy={mid}
                  r="2.5"
                  fill="var(--border-strong)"
                />
              )}
            </>
          )}

          {/* The four devig readings. Drawn alike -- no `used` mark. */}
          {d.marks.map((m) => (
            <line
              key={m.key}
              x1={at(m.x)}
              y1={mid - 7}
              x2={at(m.x)}
              y2={mid + 7}
              stroke="currentColor"
              strokeWidth="2"
            />
          ))}

          {/* Kalshi's ask: a neutral tick, drawn only when it is on scale. */}
          {d.kalshi && d.kalshi.x !== null && (
            <>
              <line
                x1={at(d.kalshi.x)}
                y1={mid - 12}
                x2={at(d.kalshi.x)}
                y2={mid + 12}
                stroke="var(--muted)"
                strokeWidth="1"
                strokeDasharray="2 2"
              />
              <text
                x={at(d.kalshi.x)}
                y={CH - 4}
                textAnchor="middle"
                className="fill-[var(--muted)] font-mono text-[9px]"
              >
                Kalshi
              </text>
            </>
          )}
        </svg>
        <p className="mt-1 max-w-[65ch] text-[0.65rem] text-muted">
          Four devig readings (tall ticks) across {asPercent(methodLo)} –{" "}
          {asPercent(methodHi)}; the row uses the lowest.
          {d.bookSpan && (
            <>
              {" "}
              The rail is {d.bookSpan.count} books, worst method each.
            </>
          )}
          {d.kalshi && d.kalshi.x === null && (
            <> Kalshi&apos;s ask is off this scale.</>
          )}
          {d.caveat && <> {d.caveat}</>}
        </p>
      </figure>
    );
  }

  return (
    <details className="w-full max-w-[34rem] xl:col-span-full">
      <summary className="cursor-pointer list-none font-mono text-[0.65rem] uppercase tracking-widest text-muted">
        readings disagree by {spreadPoints.toFixed(1)} pts
        <span className="ml-1 normal-case tracking-normal">— tap for the ranges</span>
      </summary>
      <div className="mt-1 space-y-0.5 text-[0.65rem] text-muted">
        {d.marks.length > 0 && (
          <p className="max-w-[65ch]">
            The four devig readings span {asPercent(methodLo)} –{" "}
            {asPercent(methodHi)}. No single one of them is the number; the
            spread is the error bar they share.
          </p>
        )}
        {d.bookSpan && (
          <p className="max-w-[65ch]">
            {d.bookSpan.count} books span {asPercent(d.bookSpan.lo)} –{" "}
            {asPercent(d.bookSpan.hi)}, worst method each.
          </p>
        )}
        {d.caveat && <p className="max-w-[65ch]">{d.caveat}</p>}
      </div>
    </details>
  );
}
