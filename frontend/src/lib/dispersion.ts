/**
 * Where the number came from: the geometry of the method-dispersion strip.
 *
 * **The strip answers one question — "the row says 60.2%, on what?" — and it
 * must not answer a different one.** So the word *fair* appears nowhere in the
 * labels this module produces. Every point on the strip is a reading, and the
 * screen names whose reading it is.
 *
 * ## The two rows are different populations, and that is the whole subtlety
 *
 * A first draft would put the four devig readings and the book spread on one
 * axis and call the picture consistent. They are not the same measurement:
 *
 * - **The book spread** (`BookDistribution`, `backend/slate.py:139`) devigs
 *   **every usable book** separately, takes the *worst of the four methods* for
 *   each one, and reports the min / median / max of those per-book numbers.
 *   **No sharp anchoring** — that is deliberate, so a reader can see where the
 *   anchored consensus sits inside the full field.
 * - **The four method readings** (`fair_prices.p_*`,
 *   `backend/core/devig.py:258`) average **one method at a time** across the
 *   *anchored* selection — sharp books only, where any quoted.
 *
 * So a method reading can legitimately sit **outside** the book range, and on
 * the seeded demo one does: `p_power` lands above `max_book_probability`. That
 * is not a bug and must not be clamped away. It happens because an average over
 * a subset is not bounded by the min-of-methods over the superset. The strip
 * therefore takes its axis from **every** point it draws, and says so when the
 * two book counts differ.
 *
 * **And the direction is systematic, which is why the screen labels the bar
 * "worst method each".** Every point in the bar is a *minimum* over four
 * methods; every mark is *one* of those four, averaged. So a mark is
 * structurally at or above the anchored book's own position in the bar, and on
 * most seeded rows all four sit above `max_book_probability`. A reader shown
 * this without the label concludes "the consensus is higher than every book" —
 * a claim about the market. It is a fact about the statistic.
 *
 * ## What this module does not establish
 *
 * Nothing about whether the consensus is *right*. It places numbers the record
 * already holds on a shared axis. No point here has been scored against an
 * outcome, and the strip computes no composite — that would be a model, and it
 * would need its own ADR.
 */

/** The per-book distribution, unanchored. Shape of `BookDistribution`. */
export type DispersionBooks = {
  book_count: number;
  min_book_probability: number | null;
  median_book_probability: number | null;
  max_book_probability: number | null;
};

/**
 * The four anchored consensus readings plus the one the money path used.
 *
 * **Every field is optional as well as nullable, and the two mean different
 * things.** `null` is a method that could not be solved — `p_shin` is a real
 * NULL on some rows. *Absent* means the route never joined `fair_prices` at
 * all: the Board and the market detail select from `recommendations` alone and
 * omit these keys rather than sending nulls, precisely so a consumer can tell
 * "the join ran and found nothing" from "the join never ran". Both cases
 * produce no mark, but conflating them in the type would let a caller pass a
 * Board row and get a strip drawn over four absences.
 */
export type DispersionMethods = {
  p_multiplicative?: number | null;
  p_additive?: number | null;
  p_power?: number | null;
  p_shin?: number | null;
  p_conservative?: number | null;
};

export type DispersionInput = {
  books: DispersionBooks | null;
  methods: DispersionMethods | null;
  /** Kalshi's derived ask as a probability. `null` when unreadable. */
  kalshiProbability: number | null;
  /**
   * `fair_prices.book_count` — how many books survived **anchoring**. Compared
   * against `books.book_count` (all usable books) to decide whether the two
   * rows describe the same field or two different ones.
   */
  anchoredBookCount: number | null;
};

export type DispersionMark = {
  /** `multiplicative` | `additive` | `power` | `shin` — the method's own name. */
  key: string;
  label: string;
  probability: number;
  /** Position along the axis, 0..1. */
  x: number;
  /**
   * True for the reading the money path actually used — the lowest of the
   * four. Marked rather than re-derived on the screen: `p_conservative` is the
   * column the sizer read, and recomputing `Math.min` here would be a second
   * definition that could disagree with it.
   */
  used: boolean;
};

export type Dispersion = {
  /** Axis ends, already padded. */
  domain: { lo: number; hi: number };
  /** The four method readings that were solvable, ascending. */
  marks: DispersionMark[];
  /** The unanchored per-book spread, `null` when it could not be measured. */
  bookSpan: {
    loX: number;
    hiX: number;
    medianX: number | null;
    lo: number;
    hi: number;
    count: number;
  } | null;
  /**
   * Kalshi's ask, `null` when unreadable.
   *
   * **`x` is `null` whenever the ask falls outside the axis, and the axis is
   * not stretched to hold it.** The ask is not an input to the fair value —
   * the strip's whole subject is where *that number* came from, and the brief
   * for it reads "min book → four devig methods → max book". Including the ask
   * in the domain was the first draft and it destroyed the picture on exactly
   * the rows worth looking at: the seeded `suspicious_edge` row asks 34.0%
   * against readings spanning 60.03–60.45%, so a linear axis over all of them
   * squashes four readings 0.4 points apart into a single pixel. A 26-point
   * gap to Kalshi is already the loudest number on the row; it does not need
   * to eat the resolution of the one thing this strip exists to show.
   *
   * Drawn when it happens to land inside, because then it is free information
   * and costs nothing. Never clamped to an edge — a marker pinned to the end
   * of a scale it is not on is a drawing that lies.
   */
  kalshi: { x: number | null; probability: number } | null;
  /**
   * Why the two rows may not be comparable, or `null` when they are drawn from
   * the same number of books. Rendered verbatim; never suppressed because it is
   * long.
   */
  caveat: string | null;
};

const METHOD_LABELS: ReadonlyArray<readonly [keyof DispersionMethods, string]> = [
  ["p_multiplicative", "multiplicative"],
  ["p_additive", "additive"],
  ["p_power", "power"],
  ["p_shin", "shin"],
];

/**
 * Lay every reading out on one axis, or return `null` when there is nothing
 * honest to draw.
 *
 * `null` — not an empty strip — when fewer than two distinct numbers exist. A
 * strip with one point on it looks like agreement, which is the opposite of
 * what it would mean: one point is one reading, and the question the strip
 * exists to answer is *how far apart are they*.
 */
export function dispersion(input: DispersionInput): Dispersion | null {
  const marks: Array<Omit<DispersionMark, "x">> = [];
  const methods = input.methods;
  if (methods) {
    for (const [key, label] of METHOD_LABELS) {
      const value = methods[key];
      // `null` is a method that could not be solved -- `p_shin` is genuinely
      // NULL on some rows. Absent from the strip, never plotted as 0, which is
      // a legitimate probability and would drag the axis to the floor.
      if (typeof value !== "number") continue;
      marks.push({
        key: label,
        label,
        probability: value,
        used:
          typeof methods.p_conservative === "number" &&
          Math.abs(value - methods.p_conservative) < 1e-12,
      });
    }
  }

  const books = input.books;
  const bookLo = books?.min_book_probability ?? null;
  const bookHi = books?.max_book_probability ?? null;
  const hasSpan = typeof bookLo === "number" && typeof bookHi === "number";

  // **The ask is deliberately not in here.** See `Dispersion.kalshi`: it is not
  // an input to the number this strip explains, and on any row with a real edge
  // it is far enough away to collapse the four readings into one pixel.
  const values: number[] = marks.map((m) => m.probability);
  if (hasSpan) values.push(bookLo as number, bookHi as number);

  const distinct = new Set(values.map((v) => v.toFixed(9)));
  if (values.length < 2 || distinct.size < 2) return null;

  const rawLo = Math.min(...values);
  const rawHi = Math.max(...values);
  // A tenth of the span as padding at each end, so a point sitting exactly at
  // an extreme is still drawn as a mark rather than half-clipped by the edge.
  const pad = (rawHi - rawLo) * 0.1;
  const lo = rawLo - pad;
  const hi = rawHi + pad;
  const at = (v: number) => (v - lo) / (hi - lo);

  const placed = marks
    .map((m) => ({ ...m, x: at(m.probability) }))
    .sort((a, b) => a.probability - b.probability);

  const usable = books?.book_count ?? null;
  const anchored = input.anchoredBookCount;
  // Stated only when the two counts are both readable and disagree. "Unknown"
  // is not "the same": a missing count means the comparison could not be made,
  // and silence there would read as the reassuring case.
  //
  // **Kept to one clause on purpose.** The first version ran to two sentences
  // and rendered on ten of eleven seeded rows, because a one-book anchored
  // consensus against a five-book field is the *normal* case rather than the
  // exception. Two sentences repeated ten times down a page is not emphasis,
  // it is wallpaper -- and the screen already explains the mechanism once, in
  // its own footer.
  const caveat =
    typeof usable === "number" &&
    typeof anchored === "number" &&
    usable !== anchored
      ? `bar spans ${usable} books · readings averaged over the ${anchored} that survived anchoring`
      : typeof usable !== "number" || typeof anchored !== "number"
        ? "book counts unreadable · whether these cover the same books is unknown"
        : null;

  return {
    domain: { lo, hi },
    marks: placed,
    bookSpan: hasSpan
      ? {
          lo: bookLo as number,
          hi: bookHi as number,
          loX: at(bookLo as number),
          hiX: at(bookHi as number),
          medianX:
            typeof books?.median_book_probability === "number"
              ? at(books.median_book_probability)
              : null,
          count: usable ?? 0,
        }
      : null,
    kalshi:
      typeof input.kalshiProbability === "number"
        ? {
            probability: input.kalshiProbability,
            // Inside the axis or nowhere. `at()` happily returns 1.4 for a
            // point past the right end, and a caller multiplying that by 100%
            // would draw the marker outside its own container -- visible as
            // "the ask is at the far edge", which is a different claim from
            // "the ask is off this scale entirely".
            x:
              input.kalshiProbability >= lo && input.kalshiProbability <= hi
                ? at(input.kalshiProbability)
                : null,
          }
        : null,
    caveat,
  };
}

/**
 * Probability as a percentage, e.g. `60.23%`.
 *
 * **Two decimals, and one was wrong.** The whole subject of this strip is a
 * disagreement that is routinely a tenth of a point wide: on the seeded slate a
 * row drew three visibly distinct marks whose legend read `47.4%`, `47.4%`,
 * `47.4%` — three positions and one number, which looks like the picture is
 * broken rather than like the labels are coarse. A legend must resolve whatever
 * the drawing resolves.
 *
 * Not more than two, either. These are consensus averages over a handful of
 * books; a third decimal would be precision the inputs do not carry.
 */
export function asPercent(probability: number): string {
  return `${(probability * 100).toFixed(2)}%`;
}
