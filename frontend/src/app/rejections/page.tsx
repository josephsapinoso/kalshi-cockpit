import Link from "next/link";
import { fetchSuppression } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Which check is killing everything.
 *
 * `/api/suppression` has been served since the engine was built and consumed by
 * nothing. With 0 actionable rows across ~200 decisions, "which rule refused
 * them" is the most valuable diagnostic the system has — a rule that fires on
 * nearly every candidate is either miscalibrated or is catching a real upstream
 * problem, and both are findings that change what gets built next.
 *
 * **The shape here is the route's, read before it was typed**, not guessed:
 * `{"counts": {reason: n}}`, already sorted descending server-side, with a row
 * that failed several checks counted once under each. So the values sum to more
 * than the number of rejected rows. That is correct and is stated on the page
 * rather than normalised away — the alternative is a percentage column that
 * does not add to 100 and no explanation of why.
 */

/**
 * What each code means, and what it would take to move it.
 *
 * Every check name in `backend/core/suppression.py` must have an entry here.
 * That is asserted by `tests/test_suppression_screen.py` rather than left to
 * whoever adds the next rule: a code with no explanation renders as a bare
 * identifier, which is exactly the state this screen exists to end.
 */
const EXPLAINED: Record<string, string> = {
  suspicious_edge:
    "The edge was larger than the ceiling, so it is treated as a bug rather than a bet. On the pinned record this is the largest block left once stale odds are set aside — 66 rows spanning 5.9c to 36c, at a venue that prices to about 2c — and a number that size is far more likely to be a pricing error than free money.",
  edge_within_method_noise:
    "The edge survived fees but not the disagreement between the four devig methods. It cannot be told apart from an artefact of which method was chosen.",
  stale_kalshi_quote:
    "The Kalshi price behind the row was older than the quote limit when the row was judged. The order endpoint re-reads the price anyway, so this bounds what gets recorded, not what can be bought.",
  stale_odds:
    "The sportsbook consensus behind the fair value had aged out. Nothing refreshes that but spending one of the day's odds credits, so this one is a budget symptom rather than a market one. Read the age carefully: it is measured from the odds aggregator's own timestamp, which is when it last scraped the book — not when the book last moved its line. A book that has not repriced in hours reads as fresh here.",
  insufficient_depth:
    "Fewer contracts were resting at the ask than the sizer wanted to buy. Filling would have left a remainder resting at a price nobody is taking.",
  wide_market:
    "The books disagreed with each other by more than the consensus is allowed to span. A wide market means the fair value is a guess with a wide error bar, and the edge being hunted is smaller than that bar.",
  too_few_books:
    "Not enough independent books quoted the market to form a consensus at all. One book cannot disagree with itself, so there is no width to measure and no evidence the line is right.",
  commence_skew:
    "The Kalshi market and the sportsbook fixture disagreed about when the game starts by more than the tolerance. Kalshi's occurrence_datetime runs three hours late as a rule, and anything beyond that is a suspected mislink — the wrong game.",
  no_commence_time:
    "There was no start time to compare, so the two sides could not be confirmed to be the same fixture at all. Refused rather than assumed: two different games sharing a team pair produce an edge out of nothing.",
  no_depth:
    "No size was quoted at the ask. That is unknown depth, not zero depth, and the two are refused for different reasons — this one means the book could not be read.",
  no_market_width:
    "Fewer than two books contributed to the consensus, so their disagreement could not be measured. Distinct from a wide market on purpose: 'the books disagree' and 'there was no second book to disagree with' call for different fixes, and a missing measurement used to arrive as a perfect 0.0 and pass this check most easily of all.",
  inconsistent_consensus_metadata:
    "The consensus reported a book count and a market width that cannot both be true — a measured width with fewer than two books, or no width with two or more. This should never fire. It exists because 'too few books' and 'no market width' happen to describe the same rows today only while the book-count threshold is two, and nothing in the code ties those two facts together. If you are seeing this, the consensus producer is broken, not the market.",
};

/**
 * The engine's whole check vocabulary, read off `EXPLAINED` rather than
 * declared a second time.
 *
 * `tests/test_suppression_screen.py` pins `EXPLAINED`'s keys to the `Check(...)`
 * names in `backend/core/suppression.py` in **both** directions — every rule
 * needs a sentence, and no sentence may name a rule that no longer exists. So
 * these keys are exactly `ALL_CHECK_NAMES`, and a literal list here would be a
 * second copy with nothing pinning it: the one that silently falls behind.
 */
const ALL_CHECKS = Object.keys(EXPLAINED);

/**
 * **A zero that means "could not fire" is not the same zero as "did not fire",
 * and this page shipped them under one badge.**
 *
 * The previous version of this screen badged all six never-fired checks
 * identically and printed one paragraph saying the three cases — correctly
 * quiet, unreachable, or fed an input that passes every threshold — could not
 * be told apart. That refusal was honest when it was written. It is no longer
 * true: an audit of the pinned record
 * (`docs/measurements/2026-08-10-clean-shortfall-pull.json`, 1,564 rows) has
 * since answered four of the six, and rendering an answered question
 * identically to an open one is worse than refusing both.
 *
 * It is also the exact error ADR 0021 §S10 is criticised for — pooling a "could
 * not fire" zero with genuinely-quiet zeros — reproduced on a screen. So the
 * two kinds of silence are now separated here, with the reason and its citation
 * attached to each, and the count of *genuinely* quiet guards is what the
 * header reports.
 *
 * **The classification is a fact about a pinned pull, not a live computation.**
 * It cannot update itself. That is why `classify` treats a non-zero count on
 * anything listed here as a *stale classification* and says so loudly, rather
 * than letting a sentence that says "this cannot fire" sit beside evidence that
 * it just did.
 */
const COULD_NOT_FIRE: Record<string, string> = {
  stale_kalshi_quote:
    "Could not fire: the input is a constant. `kalshi_quote_age_ms` is 0 on 1,564 of 1,564 recorded rows, so the age never approaches the limit and the comparison has never had anything to decide. Recorded in ADR 0021 §7.6.",
  no_commence_time:
    "Could not fire: unreachable in production. `link_discovered_events` (`backend/runner.py:446`) inserts a link only when the match succeeded, and `backend/match/linker.py:288-292` always sets an integer commence skew on a successful match — so a linked row with no start time cannot be constructed. Note this one rests on the code alone: no document in this repo names it, and this sentence is the first place it is written down.",
  commence_skew:
    "Could not fire: the guard's limit equals the matcher's own tolerance. `max_commence_skew_ms` (`backend/core/suppression.py:61`) is exactly `DEFAULT_COMMENCE_TOLERANCE_MS` (`backend/match/linker.py:75`), the linker admits only candidates inside that tolerance (`backend/match/linker.py:250-253`) and then records that same difference as the skew (`:291`). Anything the guard would refuse was already refused upstream. The tolerance is never overridden — `link_event` has one caller, `backend/runner.py:436-443`, which passes no tolerance argument.",
  inconsistent_consensus_metadata:
    "Could not fire: it was never deployed. The commit that added it (`c4bca6b`) also writes `suppression_checks` into the strategy-config payload (`backend/runner.py:577`), and `ensure_strategy_config` (`backend/engine.py:342-376`) mints a new version whenever that payload changes — yet the record holds only versions 1 and 2. Note the proof is the record, not the commit clock: `flyctl deploy` builds from the working directory, so commit times cannot bound what is running. See `tasks/NEXT.md`, 2026-08-11.",
};

/**
 * The two guards that really are quiet — each with the denominator that makes
 * the silence mean something.
 *
 * A zero with no denominator beside it is unreadable: it is the same glyph
 * whether the rule was evaluated on 1,564 rows and refused none, or was never
 * evaluated at all. These two were evaluated, and that is the whole difference
 * between this list and the one above.
 */
const DID_NOT_FIRE: Record<string, string> = {
  wide_market:
    "Did not fire, on a live denominator: evaluated on 1,334 rows and not one consensus spanned more than the 6-point limit. This is a guard that has been asked the question and kept answering no.",
  no_depth:
    "Did not fire, on a live denominator: `depth_at_ask` is non-null on all 1,564 rows, ranging from 0.01 to 1,364,323. The book has always been readable, which is exactly what this rule tests for.",
};

type Status =
  | { kind: "fired" }
  | { kind: "could_not_fire"; reason: string }
  | { kind: "did_not_fire"; reason: string }
  | { kind: "unclassified" }
  | { kind: "classification_stale"; reason: string };

/**
 * Which of the four states a row is in.
 *
 * `unclassified` is a real answer and not a gap to be tidied away: a check that
 * has refused nothing and is on neither list above is the original open
 * question, and the page still has to say so rather than guess. A new rule
 * added tomorrow lands here by default, which is the safe direction.
 */
function classify(name: string, count: number): Status {
  const couldNot = COULD_NOT_FIRE[name];
  const didNot = DID_NOT_FIRE[name];
  if (count > 0) {
    if (couldNot !== undefined) {
      return {
        kind: "classification_stale",
        reason:
          "This rule is recorded below as one that could not fire, and it has now fired. The recorded reason is derived from a pinned pull and is therefore out of date — trust this count, not that sentence, and re-derive the classification.",
      };
    }
    return { kind: "fired" };
  }
  if (couldNot !== undefined) return { kind: "could_not_fire", reason: couldNot };
  if (didNot !== undefined) return { kind: "did_not_fire", reason: didNot };
  return { kind: "unclassified" };
}

/**
 * One badge per state, and no two of them alike.
 *
 * The wording is the load-bearing part: "could not fire" and "did not fire"
 * differ by one word in English and by everything in meaning, so they are also
 * separated by weight and by the border — a muted dashed outline for the zeros
 * that carry no information, a solid one for the zeros that do. A fired rule
 * gets no badge; its count is the statement.
 */
const BADGE: Record<Status["kind"], { label: string; className: string } | null> =
  {
    fired: null,
    could_not_fire: {
      label: "could not fire",
      className: "border border-dashed text-muted",
    },
    did_not_fire: {
      label: "did not fire",
      className: "border text-muted",
    },
    unclassified: {
      label: "silent, unexplained",
      className: "border text-foreground",
    },
    classification_stale: {
      label: "classification stale",
      className: "border border-accent font-bold text-accent",
    },
  };

export default async function RejectionsPage() {
  let suppression;
  try {
    suppression = await fetchSuppression();
  } catch {
    return (
      <Shell>
        <p className="text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  // **The payload carries only codes that fired.** `suppression_summary` groups
  // over rows with a reason, so a check that refused nothing has no key at all —
  // and this page iterated the payload, so the rules that caught nothing were
  // invisible on the one screen whose entire job is saying which check refused
  // everything. Six of the twelve have never fired on the record, and none of
  // them could be seen here.
  //
  // That is the more alarming half of the diagnostic, not the boring half. A
  // guard that has never fired is an assumption, not a guard — and the four
  // states it can be in are now separated above rather than pooled under one
  // badge. Four of the six cannot fire at all; two are quiet with a live
  // denominator; a rule on neither list is the open question the page started
  // with, and still says so.
  //
  // Zero-filled from the vocabulary, never from the payload, and the two lists
  // are kept apart rather than merged and re-sorted: `fired` arrives already
  // sorted descending server-side and that order is the finding, while the
  // silent ones have no order to preserve and are listed alphabetically so the
  // page does not reshuffle between loads.
  const fired = Object.entries(suppression.counts);
  const firedNames = new Set(fired.map(([name]) => name));
  const silent = ALL_CHECKS.filter((name) => !firedNames.has(name)).sort();
  const entries: [string, number][] = [
    ...fired,
    ...silent.map((name): [string, number] => [name, 0]),
  ];
  const total = fired.reduce((sum, [, n]) => sum + n, 0);
  const largest = fired.length > 0 ? fired[0][1] : 0;

  // The header counters are computed off `classify`, not off the maps, so the
  // number beside "Genuinely quiet" cannot drift from the badge on the row.
  const statuses = entries.map(([name, count]) => classify(name, count));
  const countOf = (kind: Status["kind"]) =>
    statuses.filter((s) => s.kind === kind).length;

  return (
    <Shell>
      <header className="mb-8">
        <h1 className="display text-4xl sm:text-5xl">Rejections</h1>
        <p className="mt-3 max-w-xl text-lg text-muted">
          Which check is refusing everything. A rule that fires on nearly every
          candidate is either miscalibrated or catching a real upstream problem,
          and both are findings.
        </p>
      </header>

      {/* The banner no longer replaces the list. Twelve rules that have each
          refused nothing is a different statement from "no data", and the old
          early return rendered them identically — as an empty screen. */}
      {total === 0 && (
        <div className="mb-8 rounded-2xl border bg-card p-7">
          <h2 className="text-xl font-bold tracking-tight">
            Nothing has been rejected
          </h2>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted">
            No candidate has failed a check yet. That is not the same as no
            candidates: a row with no edge is the normal answer and is never
            logged as a rejection, because on any real slate it would be most of
            them and would bury every genuine diagnostic underneath it. Every
            rule is still listed below, at zero.
          </p>
        </div>
      )}

      <div className="mb-8 flex flex-wrap items-baseline gap-x-6 gap-y-2 border-y py-4">
        <Stat label="Rules that fired" value={fired.length} />
        <Stat label="Refusals counted" value={total} accent />
        <Stat label="Largest single rule" value={largest} />
        {/* The split this page shipped without. "Never fired: 6" read as six
            working guards; four of the six were never in a position to fire,
            so the honest count of guards that have been asked the question and
            answered no is two. Pooling them is the ADR 0021 §S10 error. */}
        <Stat label="Could not fire" value={countOf("could_not_fire")} />
        <Stat label="Genuinely quiet" value={countOf("did_not_fire")} />
        <Stat label="Silent, unexplained" value={countOf("unclassified")} />
      </div>

      {/* The bar is scaled against the largest rule, not against the total.
          A row can fail several checks and is counted under each, so the
          counts do not partition anything and a share-of-total bar would be
          a proportion of a number that means nothing. */}
      <ol className="divide-y border-t">
        {entries.map(([reason, count]) => {
          // Zero and absent are the same state here, and deliberately so:
          // the server omits a code precisely when it counted zero, and the
          // page asks for the whole record rather than a window, so there is
          // no "quiet lately" to confuse this with. See the footer.
          const status = classify(reason, count);
          const neverFired = count === 0;
          // `classification_stale` is louder than a fired row on purpose: it
          // means the page is carrying a sentence the data has contradicted.
          const alarming = status.kind === "classification_stale";
          const badge = BADGE[status.kind];
          return (
            <li key={reason} className="py-5">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span
                  className={`min-w-0 break-all font-mono text-sm font-semibold ${
                    neverFired ? "text-muted" : ""
                  }`}
                >
                  {reason}
                </span>
                {badge && (
                  <span
                    className={`rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-widest ${badge.className}`}
                  >
                    {badge.label}
                  </span>
                )}
                <span
                  className={`tabular ml-auto text-sm font-bold ${
                    alarming
                      ? "text-accent"
                      : neverFired
                        ? "text-muted"
                        : "text-accent"
                  }`}
                >
                  {count}
                </span>
              </div>
              {/* No bar on a rule that could not fire. A 0%-wide bar is the
                  same picture as "evaluated 1,334 times and refused none",
                  and drawing both is how the two zeros got conflated in the
                  first place. */}
              {status.kind !== "could_not_fire" && (
                <div className="mt-2 h-1.5 overflow-hidden rounded-full border">
                  <div
                    className="h-full bg-accent"
                    style={{
                      width: `${largest > 0 ? (count / largest) * 100 : 0}%`,
                    }}
                  />
                </div>
              )}
              <p className="mt-2 text-sm leading-relaxed text-muted">
                {EXPLAINED[reason] ??
                  "No explanation is recorded for this code yet. It is shown verbatim rather than dropped — an unexplained rule firing is still a rule firing."}
              </p>

              {status.kind === "could_not_fire" && (
                <p className="mt-2 border-l-2 py-1 pl-3 text-sm leading-relaxed text-muted">
                  <span className="font-semibold text-foreground">
                    This zero is not evidence of anything.
                  </span>{" "}
                  {status.reason}
                </p>
              )}

              {status.kind === "did_not_fire" && (
                <p className="mt-2 border-l-2 py-1 pl-3 text-sm leading-relaxed text-muted">
                  <span className="font-semibold text-foreground">
                    This zero was earned.
                  </span>{" "}
                  {status.reason}{" "}
                  <span className="italic">
                    It still is not proof the threshold is right — only that the
                    rule ran and said no.
                  </span>
                </p>
              )}

              {status.kind === "unclassified" && (
                <p className="mt-2 border-l-2 py-1 pl-3 text-sm leading-relaxed text-muted">
                  <span className="font-semibold text-foreground">
                    This rule has refused nothing, and nobody has worked out
                    why.
                  </span>{" "}
                  That is not the same as working. It may be correctly quiet, it
                  may be unreachable because something upstream already drops
                  every row it would catch, or its input may be arriving as a
                  value that passes the threshold every time — which is exactly
                  what <span className="font-mono text-xs">no_market_width</span>{" "}
                  was built to end. A guard that has never fired is an
                  assumption, not a guard, and the three cases are worth telling
                  apart before this one is trusted.
                </p>
              )}

              {status.kind === "classification_stale" && (
                <p className="mt-2 border-l-2 py-1 pl-3 text-sm leading-relaxed text-muted">
                  <span className="font-semibold text-foreground">
                    The recorded classification is out of date.
                  </span>{" "}
                  {status.reason}
                </p>
              )}
            </li>
          );
        })}
      </ol>

      <p className="mt-8 border-t pt-6 text-sm leading-relaxed text-muted">
        <span className="font-semibold text-foreground">
          These counts do not add up to the number of rejected rows, and
          should not.
        </span>{" "}
        A candidate that fails three checks is counted once under each, so{" "}
        {/* `{" "}` explicitly, not a newline before the word. JSX trims a
            text node that begins with a line break, and this rendered
            "5refusals" -- the same defect `tasks/lessons.md` records as
            "15minutes". No check in this repo sees it; only the screenshot
            does. */}
        <span className="tabular">{total}</span>{" "}
        refusals can come from fewer rows than that. And rows with no edge at all never appear
        here: &ldquo;there is no bet&rdquo; is the ordinary answer, not a
        rejection, and logging it would drown every real diagnostic. The{" "}
        <Link href="/" className="underline">
          Board
        </Link>{" "}
        shows those separately.
      </p>

      <p className="mt-4 text-sm leading-relaxed text-muted">
        <span className="font-semibold text-foreground">
          A zero here means never, not lately.
        </span>{" "}
        This page asks <span className="font-mono text-xs">/api/suppression</span>{" "}
        for the whole record rather than a recent window, so a rule badged{" "}
        <span className="font-mono text-xs">did not fire</span> has refused
        nothing across every row the system has ever judged — not merely nothing
        today. If a window is ever passed, that badge stops meaning this and the
        wording has to change with it.
      </p>

      <p className="mt-4 text-sm leading-relaxed text-muted">
        <span className="font-semibold text-foreground">
          Two of these zeros are measurements. Four are not.
        </span>{" "}
        A rule badged{" "}
        <span className="font-mono text-xs">could not fire</span> was never in a
        position to refuse anything — its input is a constant, its branch is
        unreachable, its limit is enforced upstream, or the code was not
        deployed — so counting it among the working guards inflates the number
        of things standing between a bad row and an order. That pooling is the
        criticism ADR 0021 §S10 carries, and this screen made the same mistake
        until it was split.{" "}
        <span className="font-semibold text-foreground">
          Those four reasons are read off a pinned pull
        </span>{" "}
        (
        <span className="font-mono text-xs">
          docs/measurements/2026-08-10-clean-shortfall-pull.json
        </span>
        , 1,564 rows) and are not recomputed on every load, so they age. If one
        of them ever does fire, the row says{" "}
        <span className="font-mono text-xs">classification stale</span> and the
        count is to be believed over the sentence.
      </p>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-3xl px-6 py-12 sm:py-16">{children}</div>;
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div
        className={`tabular mt-1 text-2xl font-extrabold tracking-tight ${
          accent ? "text-accent" : "text-foreground"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
