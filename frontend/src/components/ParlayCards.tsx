import Link from "next/link";

import { DISPLAY_TIME_ZONE, formatAge, formatDuration } from "@/lib/api";
import type {
  ActionableWindow,
  ParlayCardData,
  ParlayLadder,
  Refreshable,
} from "@/lib/api";
import LeagueTag from "@/components/LeagueTag";
import PriceOnKalshi from "@/components/PriceOnKalshi";
import RefreshWhenPriced from "@/components/RefreshWhenPriced";
import StaleOddsExit from "@/components/StaleOddsExit";
import Term from "@/components/Term";

/**
 * The ladder: six parlay cards at fair value (ADR 0070).
 *
 * Six CUTS of one pool, not six products built separately — the server's
 * `CARD_SHAPES` owns which cuts exist and this component renders however
 * many arrive. Each carries a `what_it_is` line, because six cards on one
 * screen cannot be told apart from their legs alone.
 *
 * Renders what the server worded and adds nothing to it. Honesty rules,
 * each load-bearing:
 *
 * - **Every money string arrives pre-rendered.** The stake row is a set of
 *   presets the server already priced; this component does no arithmetic
 *   (the `lib/api.ts` rule) — a stake it did not receive is a stake it
 *   cannot show.
 * - **The four caveat sentences render verbatim from the payload** — the
 *   fair-vs-quoted distinction, the enter-only warning, and the unverified
 *   fee are the server's claims, so the server's words carry them.
 * - **`bg-accent` appears exactly once per card** — the "Price on Kalshi"
 *   button in `PriceOnKalshi.tsx`, the screen's one money-adjacent action.
 *   Nothing informational wears red.
 * - **A card that could not be built says why, in words**, in the same slot
 *   it would have rendered — an absent card and an unbuildable card are
 *   different facts.
 * - **And when the reason is the clock, the page says so beside the cards.**
 *   `not_built_reason` counts *fresh* games, so a stale slate renders "needs 2
 *   fresh games and the slate has 0" — which Joe read on 2026-08-25 as "there
 *   is nothing on tonight" while twenty fixtures sat upcoming and the recording
 *   loop was wedged. The card sentence is right and incomplete; `Freshness`
 *   supplies the half it cannot see, off `/api/window`.
 * - **Nothing behind a reveal** (ADR 0068): every leg, band, and caveat is
 *   fully present.
 */
export default function ParlayCards({
  ladder,
  actionable = null,
  refreshable = null,
}: {
  ladder: ParlayLadder;
  /** `/api/window`, or `null` when the timetable did not answer. */
  actionable?: ActionableWindow | null;
  refreshable?: Refreshable | null;
}) {
  return (
    <div className="space-y-8">
      <div className="grid gap-6 lg:grid-cols-3">
        {ladder.cards.map((card) => (
          <Card key={card.key} card={card} />
        ))}
      </div>
      <Freshness
        ladder={ladder}
        actionable={actionable}
        refreshable={refreshable}
      />
      <Excluded excluded={ladder.excluded} />
      <section className="max-w-[65ch] space-y-2 text-xs leading-snug text-muted">
        <p>{ladder.notes.fair_value}</p>
        <p>{ladder.notes.enter_only}</p>
        <p>{ladder.notes.fee}</p>
      </section>
    </div>
  );
}

function Card({ card }: { card: ParlayCardData }) {
  return (
    <section
      aria-label={`${card.title} card`}
      className="flex flex-col rounded-lg border border-border p-4"
    >
      <header className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-widest">
          {card.title}
        </h2>
        {card.joint && (
          <span className="tabular text-lg font-semibold">
            {card.joint.conservative_percent_display}
          </span>
        )}
      </header>
      {/*
        Above the built/unbuilt fork, so an unbuilt card still says what it
        would have been. Server-worded like every other string here.
      */}
      <p className="mt-1 text-xs leading-snug text-muted">{card.what_it_is}</p>

      {card.not_built_reason !== null ? (
        <p className="mt-3 text-sm text-muted">
          Not built right now: {card.not_built_reason}.
        </p>
      ) : (
        <>
          <p className="mt-1 text-xs text-muted">
            <Term k="joint_chance">joint chance</Term> that every{" "}
            <Term k="leg">leg</Term> hits
            {card.joint?.method_range_display && (
              <>
                {" "}
                <span className="tabular">
                  (methods span {card.joint.method_range_display})
                </span>
              </>
            )}
          </p>
          <ol className="mt-3 flex-1 divide-y divide-border">
            {card.legs.map((leg) => (
              <li
                key={leg.ticker}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-1.5"
              >
                <span className="tabular w-11 shrink-0 font-mono text-[11px] text-muted">
                  {kickoff(leg.commence_ms)}
                </span>
                <LeagueTag league={leg.league} />
                <Link
                  href={`/market/${encodeURIComponent(leg.ticker)}`}
                  className="min-w-0 truncate text-sm font-semibold tracking-tight hover:underline"
                >
                  {leg.label}
                </Link>
                <span className="tabular text-xs text-muted">
                  {leg.fair_percent_display}
                </span>
              </li>
            ))}
          </ol>
          {card.joint && (
            <p className="mt-2 text-xs text-muted">
              <Term k="fair_value">Fair value</Term>:{" "}
              <span className="tabular">{card.joint.fair_cost_display}</span>.{" "}
              {card.joint.correlation_note}
            </p>
          )}
          <Stakes card={card} />
          <PriceOnKalshi card={card} />
        </>
      )}
    </section>
  );
}

/**
 * What a stake would buy IF the combination priced at fair value.
 *
 * **Drawn as an estimate, deliberately, and never as the card's loudest
 * number** (ADR 0071 section 2.8). These figures are honest -- nothing has
 * been quoted when this renders -- but they are also the *larger* pair and
 * they arrive *first*, and a reader trusts the first number they saw. The
 * quoted line in `PriceOnKalshi` is bounded by resting depth
 * (`backend/parlays.py:385`, `min(wanted, depth)`); this one cannot be,
 * because no book has been consulted, so it is systematically the more
 * flattering of the two.
 *
 * So: muted throughout, no bold on the default row, and an inset rule that
 * marks the whole block as provisional. The one thing NOT done is hiding or
 * removing the number -- a card that cannot say what a stake buys is not a
 * card, and CLAUDE.md rule 1 is about suppressing an apparent *edge*, not an
 * arithmetic consequence of a fair value the card already states.
 */
function Stakes({ card }: { card: ParlayCardData }) {
  if (card.at_stakes.length === 0) return null;
  return (
    <div className="mt-3 border-t border-border pt-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted">
        If it priced at fair value — an estimate, not a quote
      </h3>
      <ul className="mt-1 space-y-0.5 border-l-2 border-border pl-2">
        {card.at_stakes.map((stake) => (
          <li
            key={stake.stake_cents}
            className="tabular flex justify-between text-xs italic text-muted"
          >
            <span>{stake.stake_display}</span>
            <span>
              {stake.contracts_display} contracts → {stake.payout_display} if
              all hit
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-[11px] leading-snug text-muted">
        Nobody has offered this price. Ask Kalshi below for the real one — it
        is usually worse, and it is capped by how many contracts are actually
        resting, which this estimate is not.
      </p>
    </div>
  );
}

/**
 * Why the desk is empty, when the reason is the clock rather than the slate.
 *
 * **This block exists because the screen misled its owner.** At 09:58 PT on
 * 2026-08-25 all three cards read "needs N fresh games and the slate has 0".
 * There were twenty upcoming fixtures and sixty-five matched sides; the
 * recording loop had wedged for fifteen minutes, the last odds sweep had aged
 * past `MAX_ODDS_AGE_S`, and every side was refused as `stale_consensus`. Both
 * halves of that are facts the page already had access to and never said.
 *
 * **Gated on a card actually failing, not on any stale side.** A full desk
 * routinely carries a handful of stale sides — six, with all three cards built,
 * on the afternoon this was written — and a warning that fires on a working
 * screen is a warning the reader learns to skip. The trigger is the conjunction:
 * the clock cost the reader a card.
 *
 * **It adds no number of its own.** Everything here is a field of
 * `ActionableWindow` put into a sentence; the exit line, the next-window time
 * and the tap are `StaleOddsExit`, the same component the slate renders beside
 * its own stale count. Two screens wording one fact two ways is the failure this
 * reuses its way out of.
 *
 * `actionable === null` still renders: the ladder's own counts are enough to say
 * the reason is the clock, and `StaleOddsExit` refuses the timetable half in
 * words. A block that vanished when `/api/window` was down would go missing in
 * exactly the outage it explains.
 */
function Freshness({
  ladder,
  actionable,
  refreshable,
}: {
  ladder: ParlayLadder;
  actionable: ActionableWindow | null;
  refreshable: Refreshable | null;
}) {
  const stale = ladder.excluded.stale_consensus ?? 0;
  const unbuilt = ladder.cards.filter(
    (card) => card.not_built_reason !== null,
  ).length;
  if (stale === 0 || unbuilt === 0) return null;

  // Both halves or neither: the sentence below reads "bought Xm ago, limit is
  // Y" and half of it is not a sentence. `!` is avoided deliberately — a
  // non-null assertion here would be the compiler being told what this block
  // cannot actually prove.
  const clock =
    actionable !== null && actionable.last_sweep_ms !== null
      ? {
          age_ms: actionable.now_ms - actionable.last_sweep_ms,
          limit_ms: actionable.max_odds_age_s * 1000,
        }
      : null;

  return (
    <section
      aria-label="Why the desk is empty"
      className="max-w-[65ch] space-y-2 rounded-lg border border-border p-4"
    >
      <p className="text-sm leading-snug">
        {unbuilt === ladder.cards.length ? "No card" : "A card"} could be built,
        and the reason is the clock rather than the schedule.{" "}
        {actionable ? (
          <>
            There {actionable.fixtures_upcoming === 1 ? "is" : "are"}{" "}
            <span className="font-semibold">{actionable.fixtures_upcoming}</span>{" "}
            game{actionable.fixtures_upcoming === 1 ? "" : "s"} still to come,
            and{" "}
            <span className="font-semibold">{actionable.fixtures_fresh}</span> of
            them {actionable.fixtures_fresh === 1 ? "has" : "have"} a
            sportsbook price fresh enough to compare against.
          </>
        ) : (
          <>
            The slate is not empty — {stale} side{stale === 1 ? "" : "s"} were
            dropped for age alone.
          </>
        )}
      </p>
      <p className="text-xs leading-snug text-muted">
        {clock === null ? (
          <>
            How long ago the lines were last bought could not be read, so this
            page cannot say how far past the limit they are.
          </>
        ) : (
          <>
            The lines were last bought{" "}
            <span className="font-semibold text-foreground">
              {formatAge(clock.age_ms)}
            </span>
            , and a card may only use a price under{" "}
            {formatDuration(clock.limit_ms)} old — so all {stale} candidate side
            {stale === 1 ? " was" : "s were"} refused on age. Nothing is wrong
            with the games; the comparison is what expired.
          </>
        )}
      </p>
      <StaleOddsExit actionable={actionable} refreshable={refreshable} />
      {/*
        Below the exit, not above it. The exit is what the reader can DO; this
        is what the page is doing on its own, and a line that says "sit still,
        it is handled" placed above the controls would read as a reason not to
        use them. The tap is still the faster path and stays the prominent one.

        Only with a timetable to compare against: the watcher's whole trigger is
        `fixtures_fresh` rising above what this render saw, and without a
        baseline its first successful poll would look like a change and refresh
        the page for nothing.
      */}
      {actionable && (
        <RefreshWhenPriced renderedFresh={actionable.fixtures_fresh} />
      )}
    </section>
  );
}

function Excluded({ excluded }: { excluded: Record<string, number> }) {
  const entries = Object.entries(excluded).filter(([, n]) => n > 0);
  if (entries.length === 0) return null;
  return (
    <p className="max-w-[65ch] text-xs leading-snug text-muted">
      Left out:{" "}
      {entries
        .map(([reason, n]) => `${n} ${EXCLUSION_WORDS[reason] ?? reason}`)
        .join("; ")}
      .
    </p>
  );
}

/** Server reason codes, in words a non-professional reads cold. */
const EXCLUSION_WORDS: Record<string, string> = {
  stale_consensus: "sides whose consensus is too old to trust",
  age_unmeasurable: "sides whose consensus age was never recorded",
  not_a_probability: "sides without a usable chance",
  no_kalshi_market: "sides with no matching Kalshi market",
  market_closed: "sides whose Kalshi market is already closed",
};

/** Pacific, matching the slate rows' kickoff column. */
function kickoff(ms: number | null): string {
  if (ms === null) return "--:--";
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
