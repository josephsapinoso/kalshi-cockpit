import { asPercent, dispersion } from "@/lib/dispersion";
import type { DispersionInput } from "@/lib/dispersion";

/**
 * Where the number came from.
 *
 * A row says `60.2% fair`. That number is the **lowest** of four devig methods,
 * averaged over whichever books survived sharp anchoring — three separate
 * choices, none of which the screen has ever shown. This draws them: the spread
 * across books, the four method readings, and Kalshi's ask, on one axis.
 *
 * **The word "fair" does not appear here, deliberately.** Everything on the
 * strip is a *reading*, and the labels name whose. `fair` is what the row calls
 * the one number it picked; using it again for the inputs would suggest the
 * four readings are four fair values and the row chose among equals. It did
 * not — it took the lowest on purpose, and the strip's job is to make that
 * visible rather than to re-describe it.
 *
 * **Nothing here is scored and nothing here is an edge.** Same standing
 * constraint as every other factor on the Slate: no point below has been tested
 * against an outcome, none enters `suggested_contracts`, and this component
 * combines them into nothing.
 *
 * **The two rows are different populations** — see `lib/dispersion.ts`. A
 * method reading can sit outside the book spread, and does on the demo. The
 * caveat line says so whenever the two book counts differ; it is rendered
 * verbatim and is never dropped for width.
 *
 * Geometry lives in `@/lib/dispersion` so node can execute it directly
 * (`tests/test_dispersion_strip.py`) — a screenshot cannot tell an axis that is
 * right from one that is inverted.
 */
export default function DispersionStrip(props: DispersionInput) {
  const d = dispersion(props);

  // `null` when fewer than two distinct readings exist. Rendering an empty
  // strip would be worse than rendering nothing: one point looks like four
  // methods agreeing perfectly, which is the opposite of "we could only read
  // one of them".
  if (!d) return null;

  return (
    /* **Capped, not full-bleed.** At `xl:col-span-full` on a 2560px monitor
       the axis was ~2,700px wide for a range that is often half a probability
       point, which reads as a chart of something enormous. A fixed measure
       keeps the strip a *figure* -- roughly the width of the prose above it --
       and keeps four readings 0.4 points apart visibly distinct without
       claiming the gaps are large. */
    <div className="w-full max-w-[34rem] space-y-1 xl:col-span-full">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">
          where the number came from
        </span>
        <span className="tabular text-[0.65rem] text-muted">
          {asPercent(d.domain.lo)} – {asPercent(d.domain.hi)}
        </span>
      </div>

      <div className="relative h-9">
        {/* The books' own range, as a bar. Drawn first so the method marks sit
            on top of it -- the point of the picture is where the four readings
            fall relative to the field, and a bar painted over a mark hides
            exactly the case worth seeing. */}
        {d.bookSpan && (
          <div
            className="absolute top-3 h-1.5 rounded-full bg-border"
            style={{
              left: `${d.bookSpan.loX * 100}%`,
              width: `${Math.max(0, d.bookSpan.hiX - d.bookSpan.loX) * 100}%`,
            }}
            title={`${d.bookSpan.count} books, ${asPercent(d.bookSpan.lo)} to ${asPercent(d.bookSpan.hi)}`}
          />
        )}
        {d.bookSpan?.medianX !== null && d.bookSpan && (
          <div
            className="absolute top-2 h-3.5 w-px bg-muted"
            style={{ left: `${(d.bookSpan.medianX ?? 0) * 100}%` }}
            title="median book"
          />
        )}

        {/* The four readings. The one the sizer used is taller and inked; the
            other three are muted. Not colour-coded by method -- a palette here
            would imply a ranking among them, and the only ranking that exists
            is "lowest", which is already shown by position. */}
        {d.marks.map((m) => (
          <div
            key={m.key}
            className={`absolute ${
              m.used ? "top-0 h-9 w-0.5 bg-foreground" : "top-1.5 h-6 w-px bg-muted"
            }`}
            style={{ left: `${m.x * 100}%` }}
            title={`${m.label}${m.used ? " (used)" : ""}: ${asPercent(m.probability)}`}
          />
        ))}

        {/* Kalshi's ask, **only when it lands on this axis**. Dashed, so it
            reads as a different kind of thing from the readings -- it is the
            price you would pay, not an opinion about the outcome. The axis is
            never stretched to include it (see `lib/dispersion.ts`), so on a
            row with a real edge this is simply absent and the legend says
            where the ask is instead. */}
        {d.kalshi?.x !== null && d.kalshi && (
          <div
            className="absolute top-0 h-9 border-l border-dashed border-accent"
            style={{ left: `${(d.kalshi.x ?? 0) * 100}%` }}
            title={`Kalshi ask: ${asPercent(d.kalshi.probability)}`}
          />
        )}
      </div>

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[0.65rem] text-muted">
        {/* **"worst method each" is not a detail, it is the reason the marks
            usually sit above the bar.** The bar plots each book's *lowest* of
            the four readings (`backend/slate.py:191`); the marks plot one
            method at a time, averaged. So a mark is structurally ≥ the anchored
            book's own position, and on the seeded slate all four land above
            `max_book_probability` on most rows. Without this label a reader
            concludes "the consensus is higher than every book", which is a
            claim about the market — it is a fact about the statistic. */}
        {d.bookSpan && (
          <span>
            <span className="inline-block h-1 w-3 rounded-full bg-border align-middle" />{" "}
            {d.bookSpan.count} books, worst method each
          </span>
        )}
        {d.marks.map((m) => (
          <span key={m.key} className={m.used ? "font-semibold text-foreground" : ""}>
            {m.label} {asPercent(m.probability)}
            {m.used ? " · used" : ""}
          </span>
        ))}
        {d.kalshi && (
          <span className="text-accent">
            Kalshi ask {asPercent(d.kalshi.probability)}
            {/* Said rather than drawn at the edge. A reader who does not see
                the dashed line needs to know it is off the scale, not assume
                the ask was unreadable. */}
            {d.kalshi.x === null ? " · off this scale" : ""}
          </span>
        )}
      </div>

      {d.caveat && (
        <p className="max-w-[70ch] text-[0.65rem] leading-snug text-muted">
          {d.caveat}
        </p>
      )}
    </div>
  );
}
