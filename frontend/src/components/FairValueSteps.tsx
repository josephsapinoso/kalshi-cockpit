import { asPercent } from "@/lib/dispersion";
import type { MarketDetail } from "@/lib/api";
import Term from "@/components/Term";

/**
 * How the books' prices became this row's number, in four steps, with THIS
 * game's own figures.
 *
 * FORM, and why it is not a chart
 * ------------------------------
 * The data's job here is to explain a *sequence*, not to compare magnitudes,
 * so the honest form is a stepped figure rather than a plot. The one thing
 * that genuinely is a magnitude — the bookmaker's margin — gets the only bar
 * on the page, because that is the step a beginner cannot otherwise see.
 * The dispersion chart beside this one draws the *spread* of the results; this
 * draws the *route* to them, and they are deliberately different pictures.
 *
 * THE NUMBER THAT MAKES IT TEACHABLE
 * ----------------------------------
 * `overround` — the books' raw implied probabilities summed — has been stored
 * since the beginning and served by nothing. It is the whole lesson: two sides
 * of a market quoted at 54% and 51% sum to 105%, and a probability cannot do
 * that. The extra five points are the house's cut, and devigging is the
 * arithmetic that removes them. Without this number, "devigged" is a word a
 * beginner has to take on trust.
 *
 * HONESTY
 * -------
 * - **A step whose number is missing says so and still draws.** The sequence
 *   is the lesson; a stage silently omitted would teach a pipeline that has
 *   one fewer step than the real one.
 * - **No colour.** A coloured margin bar would read as a verdict on a market
 *   that is simply priced the way every book prices one. This line used to
 *   give a second reason — that `--accent` was the same red as `--negative` —
 *   and that has been false since ADR 0081 (commit `7bdcb11`, 2026-08-28)
 *   made `--accent` indigo and left `--negative` the only red. The first
 *   reason is the one that survives, and it is why this chart stays ink:
 *   ticket #33 (Joe, 2026-09-02) ruled the four chart components keep
 *   refusing colour because a mark on a chart is a claim, whatever hue the
 *   accent happens to be. `tests/test_fair_value_steps.py` pins the refusal.
 * - **The margin bar is drawn to scale against the 100% baseline**, so a 2%
 *   book and a 9% book look different. It is never drawn from zero — the
 *   subject is the excess, not the total.
 */

const W = 300;
const BAR_H = 10;

export default function FairValueSteps({ detail }: { detail: MarketDetail }) {
  const overround = typeof detail.overround === "number" ? detail.overround : null;
  const methods = [
    detail.p_multiplicative,
    detail.p_additive,
    detail.p_power,
    detail.p_shin,
  ].filter((v): v is number => typeof v === "number");

  // Nothing to teach without at least the destination.
  if (typeof detail.fair_probability !== "number" && methods.length === 0) {
    return null;
  }

  // The excess over a margin-free book, in points. Clamped only for DRAWING
  // width; the printed number is always the measured one.
  const marginPoints = overround === null ? null : (overround - 1) * 100;
  const barFrac =
    marginPoints === null ? 0 : Math.max(0, Math.min(1, marginPoints / 10));

  return (
    <figure className="mt-3 w-full max-w-[22rem]">
      <figcaption className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">
        how the books&rsquo; prices became this number
      </figcaption>

      <ol className="mt-2 space-y-2 text-[0.7rem] leading-snug">
        <li>
          <span className="font-semibold">1. The books quote both sides.</span>{" "}
          <span className="text-muted">
            {overround === null ? (
              <>Their prices are not recorded for this row.</>
            ) : (
              <>
                Added up, their chances come to{" "}
                <span className="tabular">{(overround * 100).toFixed(1)}%</span>
                {" — not 100%."}
              </>
            )}
          </span>
        </li>

        {marginPoints !== null && (
          <li>
            <span className="font-semibold">
              2. The excess is the house&rsquo;s cut.
            </span>{" "}
            <span className="text-muted">
              <span className="tabular">{marginPoints.toFixed(1)} points</span>{" "}
              above a market with no margin in it.
            </span>
            <svg
              viewBox={`0 0 ${W} ${BAR_H + 4}`}
              className="mt-1 w-full text-foreground"
              role="img"
              aria-label={`Bookmaker margin ${marginPoints.toFixed(1)} points`}
            >
              {/* The 100% baseline: where a margin-free book would end. */}
              <line
                x1="0"
                y1="1"
                x2="0"
                y2={BAR_H + 3}
                stroke="var(--border-strong)"
                strokeWidth="1"
              />
              <rect
                x="0"
                y="2"
                width={Math.max(2, barFrac * W)}
                height={BAR_H}
                rx="3"
                fill="currentColor"
                opacity="0.28"
              />
            </svg>
          </li>
        )}

        <li>
          <span className="font-semibold">
            {marginPoints === null ? "2." : "3."} Take it back out (
            <Term k="devig">devig</Term>).
          </span>{" "}
          <span className="text-muted">
            {methods.length >= 2 ? (
              <>
                Four ways of doing that disagree:{" "}
                <span className="tabular">
                  {asPercent(Math.min(...methods))} –{" "}
                  {asPercent(Math.max(...methods))}
                </span>
                .
              </>
            ) : (
              <>Only one method could be solved on this row.</>
            )}
          </span>
        </li>

        <li>
          <span className="font-semibold">
            {marginPoints === null ? "3." : "4."} Use the least flattering.
          </span>{" "}
          <span className="text-muted">
            {typeof detail.fair_probability === "number" ? (
              <>
                This row takes{" "}
                <span className="tabular">
                  {asPercent(detail.fair_probability)}
                </span>
                , the lowest of them — so a number cannot look good here
                purely because of which method happened to be used.
              </>
            ) : (
              <>No fair value was recorded for this row.</>
            )}
          </span>
        </li>
      </ol>
    </figure>
  );
}
