import type { SlateRowData } from "@/lib/api";
import { leagueLabel } from "@/lib/leagueLabel";
import Term from "@/components/Term";

/**
 * How often a sharp book was actually behind the prices on this screen.
 *
 * Joe's answer, 2026-09-16, to a question three sessions old: option A, show
 * the base rate up top.
 *
 * **Why the per-row marker was not enough.** Every price surface already says
 * when no sharp book backed a row (`tests/test_soft_fallback_is_shown_on_
 * every_price_surface.py`). But on NCAAF `spreads` and `totals` that warning
 * fires on about seven rows in ten, and a caveat that fires on most rows stops
 * being read. The row tells you about the row; nothing told you the odds of
 * seeing the warning before you started. This does.
 *
 * **It is a count, not a ranking, and that is deliberate.** CLAUDE.md: a
 * per-row fact is transparency, an ordering is a claim. Nothing here reorders
 * the slate, scores a row, or suppresses one — it reports what is already on
 * the screen, grouped. ADR 0071 §"price transparency".
 *
 * **Every group is listed, including the good ones.** Rendering only the
 * thinly-anchored groups would make this a warning that fires on bad news and
 * stays quiet otherwise, which is the exact defect `ParlayCards.tsx` carried
 * until 2026-09-16: a check that only speaks up when something is wrong reads
 * as a check that passed. `tests/test_anchor_base_rate.py` pins it.
 *
 * **Unknown is its own column, never folded into either side.** The flag is
 * `null` when the fair-price join missed, which is a different fact from "no
 * sharp book" — CLAUDE.md, unreadable resolves to `None`, never `0`. A group
 * whose rows are all unknown reports that and no fraction.
 */

/** One (league, market family) bucket of the rows currently on screen. */
type Bucket = {
  key: string;
  league: string | null;
  market: string | null;
  anchored: number;
  unanchored: number;
  unknown: number;
};

/**
 * The market family, in Joe's words rather than the Odds API's.
 *
 * Unrecognised keys pass through unchanged: a prop key like
 * `batter_home_runs` is more informative spelled out than mapped to a guess,
 * and a family this desk has not seen before must not be silently renamed.
 */
function marketLabel(market: string | null): string {
  if (market === null) return "unknown market";
  if (market === "h2h") return "moneyline";
  if (market === "spreads") return "spread";
  if (market === "totals") return "total";
  return market;
}

/**
 * Group the displayed rows, in the order they first appear.
 *
 * Insertion order rather than sorted: the buckets then read down the page in
 * the same order the rows do, and no arrangement of them implies a ranking.
 */
export function bucketRows(rows: readonly SlateRowData[]): Bucket[] {
  const buckets = new Map<string, Bucket>();
  for (const row of rows) {
    const league = row.league ?? null;
    const market = row.consensus_market ?? null;
    // A separator that cannot appear in either value, written as an
    // ESCAPE rather than a literal control character: a raw NUL in the
    // source is invisible in every editor and diff, and one got in here
    // once already.
    const key = `${league ?? "?"}\u241F${market ?? "?"}`;
    let bucket = buckets.get(key);
    if (bucket === undefined) {
      bucket = { key, league, market, anchored: 0, unanchored: 0, unknown: 0 };
      buckets.set(key, bucket);
    }
    if (row.anchored_on_sharp === true) bucket.anchored += 1;
    else if (row.anchored_on_sharp === false) bucket.unanchored += 1;
    else bucket.unknown += 1;
  }
  return [...buckets.values()];
}

function BucketLine({ bucket }: { bucket: Bucket }) {
  const known = bucket.anchored + bucket.unanchored;
  const label = `${
    bucket.league === null ? "Unknown league" : leagueLabel(bucket.league)
  } · ${marketLabel(bucket.market)}`;

  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="text-xs text-muted">{label}</span>
      {known === 0 ? (
        /* No fraction at all rather than "0 of 0": a denominator of zero is
           not a rate, and printing one would invent a quantity. */
        <span className="tabular text-xs text-accent-2">
          anchor unreadable on {bucket.unknown}{" "}
          {bucket.unknown === 1 ? "row" : "rows"}
        </span>
      ) : (
        <span
          className={
            bucket.anchored === known
              ? "tabular text-xs text-muted"
              : "tabular text-xs text-accent-2"
          }
        >
          {bucket.anchored} of {known}{" "}
          {known === 1 ? "row has" : "rows have"} a sharp book behind the price
        </span>
      )}
      {known > 0 && bucket.unknown > 0 && (
        <span className="tabular text-xs text-muted">
          ({bucket.unknown} unreadable)
        </span>
      )}
    </li>
  );
}

export default function AnchorBaseRate({ rows }: { rows: readonly SlateRowData[] }) {
  const buckets = bucketRows(rows);
  if (buckets.length === 0) return null;

  return (
    <section className="mt-8 rounded-lg border border-border bg-card p-3">
      <h2 className="text-xs font-medium text-muted">
        <Term k="sharp_book">Sharp book</Term> behind these prices
      </h2>
      <ul className="mt-2 space-y-1">
        {buckets.map((bucket) => (
          <BucketLine key={bucket.key} bucket={bucket} />
        ))}
      </ul>
      {/* The sentence that makes the counts mean something. Without it a
          reader has to know that spreads and totals can only ever anchor on
          two books, which is a fact about `SHARP_BOOKS` in `runner.py` and not
          about tonight. */}
      <p className="mt-2 max-w-[65ch] text-xs text-muted">
        Spreads and totals can only ever anchor on Pinnacle or Matchbook, and
        each book quotes one main line per game — so a Kalshi line at a
        different number often has no sharp quote to match. A low count here is
        usually the shape of the market, not a fault.
      </p>
    </section>
  );
}
