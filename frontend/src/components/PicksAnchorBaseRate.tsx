import type { SlatePick } from "@/lib/api";
import { leagueLabel } from "@/lib/leagueLabel";
import Term from "@/components/Term";

/**
 * How often a sharp book was behind the prices on the PICKS screen.
 *
 * Joe's answer `54A`, 2026-09-17, to ticket #54. `AnchorBaseRate` already
 * does this on the Games slate; a previous session filed "put it on Picks
 * too" as decided-in-principle and it was not — Joe had answered about
 * Games, and Picks is a different population. #54 asked him, and he chose
 * option A: put it on Picks, grouped by league, and say `moneyline` out
 * loud.
 *
 * **Why this is a second component and not a prop on the first.** The Games
 * block groups per (league, market family) on purpose: NCAAF `h2h` anchors
 * about 84% of the time and NCAAF `spreads` about 30%, so one number over
 * both describes neither (CLAUDE.md, "a pooled number is not a finding
 * until the parts agree"). **On Picks there is only ever one market family.**
 * The ranking loop takes the moneyline favourite of each game — it excludes
 * player props by name (`routes.py`, ticket #23) and the only other
 * recommendation-writing arm in the runner is the moneyline one, because
 * `_price_spread_event` and `_price_totals_event` deliberately write
 * `fair_prices` and no `recommendations` row (ADR 0070). So the Games
 * grouping, applied here, would collapse to per-league — which is exactly
 * the pooling the evidence argued against. Reusing the component with a
 * flag would have hidden that: the two screens group differently because
 * they hold different populations, and one file each says so.
 *
 * **Naming `moneyline` is the honest part, not decoration.** An unqualified
 * "MLB — 7 of 11" on a screen the reader cannot tell is moneyline-only reads
 * as a statement about MLB, and this desk's spreads and totals anchor far
 * less often than its moneylines. The word is what bounds the claim to the
 * rows it counted. `tests/test_anchor_base_rate.py` pins it.
 *
 * **No `consensus_market` field was added to the picks payload, and that is
 * a decision.** Every row here is `h2h` by construction (above), so the
 * field would arrive constant on every row of every response — a payload
 * key that can only ever say one thing. The constancy is pinned by a test
 * over the two producers instead, so the day a spread rung starts writing a
 * recommendation the test names this file rather than the screen quietly
 * lying about what it counted.
 *
 * **No total line, deliberately.** `tests/test_picks_screen.py` forbids a
 * headline counting how many picks ranked — "a number that rises when there
 * is more to bet on is a number the screen is not allowed to grow" (#8).
 * A per-league denominator is the fraction's own denominator and cannot be
 * dropped without turning a count into a rate; a sum across leagues would
 * be that forbidden headline wearing this block's clothes. It is also the
 * pooled number this block exists to refuse. So: one line per league, and
 * nothing that adds them up.
 *
 * The three properties the Games block is held to hold here unchanged:
 * counts and never a percentage, every league listed including the fully
 * anchored ones (a check that only speaks on bad news reads as a check that
 * passed — the `ParlayCards.tsx` defect), and `null` counted apart rather
 * than folded into "no sharp book" (CLAUDE.md: unreadable resolves to
 * `None`, never `0`). Nothing here sorts, scores, filters or suppresses a
 * pick: a per-row fact is transparency, an ordering is a claim (ADR 0071).
 *
 * **There is no closing paragraph, and the Games one must not be copied.**
 * That sentence explains that spreads and totals can only anchor on
 * Pinnacle or Matchbook and that each book quotes one main line per game,
 * so a Kalshi rung at a different number often has no sharp quote to match.
 * That mechanism does not operate on a moneyline: there is one moneyline per
 * game and a sharp book either quoted it or did not. Writing a replacement
 * would mean asserting what a low count MEANS on `h2h`, and this repo has
 * not measured that — so the block prints the counts and stops. The
 * `sharp_book` glossary entry already carries what the fallback is.
 */

/** One league's worth of the moneyline picks currently on screen. */
type LeagueBucket = {
  league: string | null;
  anchored: number;
  unanchored: number;
  unknown: number;
};

/**
 * Group the ranked picks by league, in the order they first appear.
 *
 * Insertion order rather than sorted, for the same reason the Games block
 * keeps it: the lines then read down the page in the order the picks do,
 * and no arrangement of them implies a ranking.
 */
export function bucketPicksByLeague(
  picks: readonly SlatePick[],
): LeagueBucket[] {
  const buckets = new Map<string, LeagueBucket>();
  for (const pick of picks) {
    const league = pick.league ?? null;
    const key = league ?? "?";
    let bucket = buckets.get(key);
    if (bucket === undefined) {
      bucket = { league, anchored: 0, unanchored: 0, unknown: 0 };
      buckets.set(key, bucket);
    }
    // Three states, branched separately. `anchored_on_sharp` is `null` when
    // the fair-price join missed, which is a different fact from "no sharp
    // book" -- a truthiness test would fold the first into the second and
    // report a measured absence where nothing was read.
    if (pick.anchored_on_sharp === true) bucket.anchored += 1;
    else if (pick.anchored_on_sharp === false) bucket.unanchored += 1;
    else bucket.unknown += 1;
  }
  return [...buckets.values()];
}

function LeagueLine({ bucket }: { bucket: LeagueBucket }) {
  const known = bucket.anchored + bucket.unanchored;
  const label =
    bucket.league === null ? "Unknown league" : leagueLabel(bucket.league);

  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="text-xs text-muted">{label}</span>
      {known === 0 ? (
        /* No fraction at all rather than "0 of 0": a denominator of zero is
           not a rate, and printing one would invent a quantity. */
        <span className="tabular text-xs text-accent-2">
          anchor unreadable on {bucket.unknown} moneyline{" "}
          {bucket.unknown === 1 ? "pick" : "picks"}
        </span>
      ) : (
        <span
          className={
            bucket.anchored === known
              ? "tabular text-xs text-muted"
              : "tabular text-xs text-accent-2"
          }
        >
          {bucket.anchored} of {known} moneyline{" "}
          {known === 1 ? "pick had" : "picks had"} a sharp book behind the
          price
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

export default function PicksAnchorBaseRate({
  ranked,
}: {
  ranked: readonly SlatePick[];
}) {
  const buckets = bucketPicksByLeague(ranked);
  if (buckets.length === 0) return null;

  return (
    <section className="mt-8 rounded-lg border border-edge bg-card p-3">
      <h2 className="text-xs font-medium text-muted">
        <Term k="sharp_book">Sharp book</Term> behind these{" "}
        <Term k="moneyline">moneyline</Term> picks
      </h2>
      <ul className="mt-2 space-y-1">
        {buckets.map((bucket) => (
          <LeagueLine key={bucket.league ?? "?"} bucket={bucket} />
        ))}
      </ul>
    </section>
  );
}
