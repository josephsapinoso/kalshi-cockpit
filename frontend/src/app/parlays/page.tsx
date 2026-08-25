import { SHELL_WIDTH } from "@/lib/shell";
import { fetchParlays, fetchRefreshable, fetchWindow } from "@/lib/api";
import ParlayCards from "@/components/ParlayCards";
import Term from "@/components/Term";

export const dynamic = "force-dynamic";

/**
 * The parlay desk (ADR 0070). Joe asked for this screen by name, from his
 * cousin-in-law's winning slip: a ladder of three cards — Safe, Middle,
 * Lottery — built from the same devigged consensus the slate reads, one leg
 * per game, priced at FAIR value.
 *
 * This page is a betting-desk feature (ADR 0062), not an edge claim: no
 * breakeven, EV, or size appears anywhere on it, and the server's own
 * caveat sentences (fair-vs-quoted, enter-only, unverified fee) render
 * verbatim. Kalshi's actual price for a card exists only once the combo is
 * built — the lookup slice adds that comparison; until then the cards say
 * plainly that fair value is not a quote.
 */
export default async function ParlaysPage() {
  let ladder;
  try {
    ladder = await fetchParlays();
  } catch {
    return (
      <Shell>
        <p className="max-w-[65ch] text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  // The timetable, caught to `null` rather than thrown — the slate's pattern
  // at `app/slate/page.tsx`. The ladder is this page's subject and these two
  // only annotate it, so a timetable that will not answer must degrade to the
  // page as it rendered before this block existed, never take it down.
  // `readNextWindow(null)` is written for exactly this and refuses in words.
  const actionable = await fetchWindow().catch(() => null);
  const refreshable = await fetchRefreshable().catch(() => null);

  return (
    <Shell>
      <header className="mb-8">
        <h1 className="display text-4xl sm:text-5xl">Parlay desk</h1>
        <p className="mt-3 max-w-[65ch] text-sm leading-relaxed text-muted">
          Three <Term k="parlay">parlay</Term> cards from tonight&rsquo;s
          slate, one pick per game, each shown at its{" "}
          <Term k="fair_value">fair value</Term>. {ladder.notes.chance}
        </p>
      </header>
      <ParlayCards
        ladder={ladder}
        actionable={actionable}
        refreshable={refreshable}
      />
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${SHELL_WIDTH} px-4 py-12 sm:px-6 sm:py-16 xl:px-8`}>
      {children}
    </div>
  );
}
