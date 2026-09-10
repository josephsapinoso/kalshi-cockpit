import { SHELL_WIDTH } from "@/lib/shell";
import {
  ApiError,
  fetchParlays,
  fetchRefreshable,
  fetchWindow,
  readListFilter,
  type ParlayHorizon,
} from "@/lib/api";
import FilterBar from "@/components/FilterBar";
import WindowPicker from "@/components/WindowPicker";
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
  searchParams: Promise<{
    league?: string;
    within_hours?: string;
    horizon?: string;
  }>;
}) {
  const params = await searchParams;
  // The #15 cut, from the URL to the request unvalidated: the server is the
  // one validator, and its refusal is drawn below as its own fact.
  const filter = readListFilter(params);
  // **Also unvalidated here, for the same reason.** An unknown window is a
  // 422 from the server with its own sentence, which the catch below already
  // renders. Validating client-side would be a second spelling of the list
  // of windows, and the one that goes stale.
  const horizon = (params.horizon ?? null) as ParlayHorizon | null;
  let ladder;
  try {
    ladder = await fetchParlays(filter, horizon);
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

            Ticket #9's ratified Parlays lede (Joe, 2026-08-27), verbatim,
            with `ladder.notes.chance` still appended. It adds the fact the
            old sentence omitted and a novice most needs: a card is enter-only
            -- no YES bid on 40 of 40 combination books this repo has read
            (`parlays.py`, ADR 0012 §5) -- so once bought hardly anyone is
            bidding to buy it back. No availability claim, deliberately (#9
            records why).

            **"nobody" became "hardly anyone" on 2026-09-10, and the change is
            correctness rather than wording.** Two `KXMVECROSSCATEGORY-SHARD1`
            books were read carrying resting YES bids ($10 at 0.0980 and $10 at
            0.0570), so the universal is false; one counterexample ends it.
            Joe ratifies wording and this sentence is still his, but a
            ratified sentence does not get to stay false on the screen while
            the answer is pending, which is CLAUDE.md's
            fix-and-copy-ship-together rule. **He was asked on 2026-09-10 and
            kept it:** given "hardly anyone" in place, the two shard-1 books
            behind the change, and two alternatives, he re-ratified this
            wording. It is his approved copy in full again, not a correctness
            patch awaiting an answer. Everything else in
            #9's sentence is untouched, and the replacement still makes no
            availability claim and implies no rate: how OFTEN a bid is there
            is what Arm D measures on 2026-09-13.
          */}
          {/*
            **This sentence is RATIFIED and is restored here after being
            edited by mistake (2026-09-06).** The window became a control and
            "tonight's games" stopped being unconditionally true, so it was
            rewritten to render the payload's own words --
            `tests/test_tab_ledes.py` went red, which is exactly what it is
            for: this is Joe's approved copy (2026-08-27), and changing it is
            his call, not a side effect of shipping a feature.

            The honest resolution is not to edit it but to say, next to the
            cards, when it no longer applies -- `WindowPicker` renders that
            line whenever the window is not tonight. If the wider windows
            become the common case, the lede needs RE-RATIFYING rather than
            quietly rewording.
          */}
          <Term k="parlay">Parlay</Term> cards cut from tonight&rsquo;s games,
          one pick per game, shown at the{" "}
          <Term k="fair_value">fair value</Term> the sportsbooks&rsquo; chances
          imply rather than at what Kalshi charges — a card pays only if every
          pick on it wins, and once you own one hardly anyone is bidding to buy
          it back.{" "}
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
      {/*
        BELOW the cut, not above it. The cut narrows the pool and the window
        sets its outer bound, so reading top-to-bottom is "which games, then
        how far ahead" -- and the window's sentence lands immediately above
        the cards it describes.
      */}
      <WindowPicker window={ladder.window} filter={filter} />
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
