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
    "The edge was larger than the ceiling, so it is treated as a bug rather than a bet. The spread between the four devigging methods alone is bigger than the fee advantage being hunted, so a large number here is far more likely to be a pricing error than free money.",
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

  const entries = Object.entries(suppression.counts);
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  const largest = entries.length > 0 ? entries[0][1] : 0;

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

      {entries.length === 0 ? (
        <div className="rounded-2xl border bg-card p-7">
          <h2 className="text-xl font-bold tracking-tight">
            Nothing has been rejected
          </h2>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted">
            No candidate has failed a check yet. That is not the same as no
            candidates: a row with no edge is the normal answer and is never
            logged as a rejection, because on any real slate it would be most of
            them and would bury every genuine diagnostic underneath it.
          </p>
        </div>
      ) : (
        <>
          <div className="mb-8 flex flex-wrap items-baseline gap-x-6 gap-y-2 border-y py-4">
            <Stat label="Rules that fired" value={entries.length} />
            <Stat label="Refusals counted" value={total} accent />
            <Stat label="Largest single rule" value={largest} />
          </div>

          {/* The bar is scaled against the largest rule, not against the total.
              A row can fail several checks and is counted under each, so the
              counts do not partition anything and a share-of-total bar would be
              a proportion of a number that means nothing. */}
          <ol className="divide-y border-t">
            {entries.map(([reason, count]) => (
              <li key={reason} className="py-5">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="min-w-0 break-all font-mono text-sm font-semibold">
                    {reason}
                  </span>
                  <span className="tabular ml-auto text-sm font-bold text-accent">
                    {count}
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full border">
                  <div
                    className="h-full bg-accent"
                    style={{
                      width: `${largest > 0 ? (count / largest) * 100 : 0}%`,
                    }}
                  />
                </div>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  {EXPLAINED[reason] ??
                    "No explanation is recorded for this code yet. It is shown verbatim rather than dropped — an unexplained rule firing is still a rule firing."}
                </p>
              </li>
            ))}
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
        </>
      )}
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
