import { SHELL_WIDTH } from "@/lib/shell";
import {
  ApiError,
  fetchParlays,
  fetchRefreshable,
  fetchWindow,
  readListFilter,
} from "@/lib/api";
import FilterBar from "@/components/FilterBar";
import ParlayCards from "@/components/ParlayCards";
import Term from "@/components/Term";

export const dynamic = "force-dynamic";

/**
 * The parlay desk (ADR 0070). Joe asked for this screen by name, from his
 * cousin-in-law's winning slip. Six cards now, and they are six CUTS of one
 * pool rather than six products: the same devigged consensus the slate
 * reads, one leg per game, priced at FAIR value, ranked or filtered six
 * ways. `backend/core/ladder.py` owns which cuts exist.
 *
 * **None of them ranks by the consensus-vs-Kalshi gap, and none may** (ADR
 * 0071 section 2.5). Every ordering here is by probability or by the clock.
 *
 * This page is a betting-desk feature (ADR 0062), not an edge claim: no
 * breakeven, EV, or size appears anywhere on it, and the server's own
 * caveat sentences (fair-vs-quoted, enter-only, unverified fee) render
 * verbatim. Kalshi's actual price for a card exists only once the combo is
 * built — the lookup slice adds that comparison; until then the cards say
 * plainly that fair value is not a quote.
 */
export default async function ParlaysPage({
  searchParams,
}: {
  searchParams: Promise<{ league?: string; within_hours?: string }>;
}) {
  // The #15 cut, from the URL to the request unvalidated: the server is the
  // one validator, and its refusal is drawn below as its own fact.
  const filter = readListFilter(await searchParams);
  let ladder;
  try {
    ladder = await fetchParlays(filter);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      return (
        <Shell>
          <h1 className="display text-4xl sm:text-5xl">Parlay desk</h1>
          <FilterBar pathname="/parlays" filter={filter} />
          <p className="mt-6 max-w-[65ch] text-sm text-accent-2">
            That cut is not one this desk carries: the league or the window in
            the address was refused, so no cards are drawn rather than the
            whole desk under a heading that says it was cut.
          </p>
        </Shell>
      );
    }
    return (
      <Shell>
        <p className="max-w-[65ch] text-muted">Backend unreachable.</p>
      </Shell>
    );
  }
  const hidden = ladder.filter?.hidden ?? 0;

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
          {/*
            No count in this sentence, deliberately. It said "Three" until
            2026-08-26 and the ladder had grown to six — a number in prose is
            a second definition of `CARD_SHAPES`, kept in sync by memory, and
            memory is what let it go stale. Each card names its own cut.
          */}
          <Term k="parlay">Parlay</Term> cards from tonight&rsquo;s slate —
          the same pool of games cut several ways, one pick per game, each
          shown at its <Term k="fair_value">fair value</Term>.{" "}
          {ladder.notes.chance}
        </p>
      </header>
      {/* The #15 cut, on the pool the six cards are built from. The count is
          candidate sides the cut removed, as the server counts them -- not
          the engine's own refusals, which `ParlayCards` still lists by
          reason beneath the cards. A one-game cut builds no card and every
          card says so in its own words. */}
      <FilterBar
        pathname="/parlays"
        filter={filter}
        note={
          hidden > 0
            ? `${hidden} ${hidden === 1 ? "side" : "sides"} left out of the pool by this cut.`
            : null
        }
      />
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
