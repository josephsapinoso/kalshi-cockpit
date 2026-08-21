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
export default function DispersionStrip(props: DispersionInput) {
  const d = dispersion(props);
  if (!d) return null;

  const spreadPoints = (d.domain.hi - d.domain.lo) * 100;
  const methodProbabilities = d.marks.map((m) => m.probability);
  const methodLo = Math.min(...methodProbabilities);
  const methodHi = Math.max(...methodProbabilities);

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
