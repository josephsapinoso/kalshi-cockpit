"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  closeHeldPosition,
  DISPLAY_TIME_ZONE,
  resolveHeldLeg,
  type HedgeBlock,
  type HedgeRung,
  type HeldLeg,
  type HeldPosition,
  type UnrecordedAtVenue,
} from "@/lib/api";
import { kalshiMarketUrl } from "@/lib/kalshiLink";
import { stakeBasisNote } from "@/lib/stakeBasisGloss";
import { comboBookNote, COMBO_BOOK_ASK_POINTER } from "@/lib/comboBookGloss";
import Term from "@/components/Term";

/**
 * How old a Kalshi quote or a venue positions read is, at second precision.
 *
 * `describeAge` in `lib/openPositionsStamps.ts` answers the same question at
 * minute precision, which is right for a figure that moves every five
 * minutes and wrong here: `MAX_KALSHI_QUOTE_AGE_S` is 30 seconds, so a quote
 * halfway to stale would read "just now" under that formatter and the whole
 * point of showing the age -- letting Joe see a price about to be refused
 * before the refusal fires -- would be lost.
 */
function describeQuoteAge(ms: number | null | undefined): string | null {
  if (ms === null || ms === undefined || ms < 0) return null;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 1) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

/**
 * What Joe holds, and what hedging it would do (ADR 0078).
 *
 * Two states render completely differently and that is the whole design:
 *
 * **One leg live, every other already won** — carries a dollar figure for
 * what a hedge would come to either way. It is arithmetic on two observed
 * numbers, and it is an ESTIMATE: four terms of mixed sign sit on it
 * (CLAUDE.md, E1–E4), so the screen says "about $X either way — an
 * estimate" and sets the size of the largest measured term beside the
 * number, at the number's size. Issue #43, answer A (Joe, 2026-09-16): until
 * then the heading called the figure a lock and the caption promised it
 * either way the leg went, and both phrases are on the killed-claims list
 * in `tests/test_hedge_positions.py` now.
 *
 * **A de-risk** — several legs live — carries no such figure and never
 * pretends to. Both branches are shown so the shape of the choice is visible,
 * and the payload does not even have a `guaranteed` field to render as false.
 *
 * **There is no buy button, deliberately.** The screen gives the size, the
 * price and a link into the Kalshi app, and Joe places it there; the manual
 * door is for singles and combos he chose himself, not for a hedge sized by
 * this screen. (This paragraph carried a one-contract cap on the door until
 * 2026-09-16, wrapped so the killed-claims guard could not see it; ADR 0112
 * took every cap off on 2026-09-08.)
 *
 * **Live-first is a fact, not a ranking (#130).** Whether a position still
 * has a pending leg is a fact about the world -- ADR 0071 §2.5's rule is
 * that the consensus-vs-Kalshi *gap* is shown per row and never ranked by;
 * it says nothing about grouping on a fact like this one. Positions are
 * partitioned into a live group (a pending leg AND no venue settlement,
 * #132) rendered first and a settled group collapsed behind a counted,
 * tap-to-open summary, so the settled rows do not bury the rows that
 * matter. What the settled group holds: positions whose legs have all
 * resolved but whose combination the venue has NOT yet settled, plus
 * hand-recorded slips, which the venue cannot see. A combination the venue
 * HAS settled leaves `/api/hedge` on the watcher's next cycle
 * (`close_settled_combinations`, ADR 0181, Joe's (A) to #131) -- until
 * 2026-09-22 this comment said the group "only grows (nothing here
 * auto-closes a position)", which was true then. A hand-recorded slip
 * leaves once one of its legs has lost (`close_dead_hand_recorded`, #143,
 * Joe's (A) to #142); otherwise closing one is still Joe's own tap,
 * `close_position`. **Record order is kept
 * inside each group** -- the partition reorders nothing on its own.
 */
export default function HedgePositions({
  positions,
  notes,
  unrecordedAtVenue = [],
  venuePollMs = null,
  asOfMs,
  maxQuoteAgeMs = 30_000,
}: {
  positions: HeldPosition[];
  notes: Record<string, string>;
  /** Kalshi combinations the venue holds that nothing here watches (ADR
   * 0136-the-hedge-screen-says-what-it-cannot-see). */
  unrecordedAtVenue?: UnrecordedAtVenue[];
  venuePollMs?: number | null;
  asOfMs: number;
  maxQuoteAgeMs?: number;
}) {
  return (
    <div className="mt-6 flex flex-col gap-4">
      <VenueCoverageBanner unrecorded={unrecordedAtVenue} />
      {positions.length === 0 ? (
        <p className="text-sm text-muted">
          No tickets recorded. Add one below and the desk will watch its legs
          while the games run.
        </p>
      ) : (
        <PositionGroups
          positions={positions}
          notes={notes}
          venuePollMs={venuePollMs}
          asOfMs={asOfMs}
          maxQuoteAgeMs={maxQuoteAgeMs}
        />
      )}
    </div>
  );
}

/**
 * The live-first partition (#130, extended #132). A position is LIVE only
 * when BOTH a leg still reads `pending` AND the venue itself has not
 * settled the combination (`venue_settlement === null`) -- one predicate,
 * named once as `isLive`, matching the same two facts `build_payload`'s
 * combo-book guard now checks (`backend/hedge.py:1958`): a combo can settle
 * at the venue before its leg markets do (`backend/hedge.py:1201`), so
 * `pending_legs` alone can say "live" for a ticket the venue has already
 * closed out. `venue_settlement` is `null` for a hand-recorded slip with no
 * `combo_ticker` (nothing to check) as well as for a genuinely open
 * combination, so it never falsely excludes a single or a sportsbook bet
 * from the live group.
 *
 * The settled group is the COMPLEMENT of `isLive`, not a second hand-written
 * condition -- `!isLive(p)` -- so the two groups are exhaustive and disjoint
 * BY CONSTRUCTION: there is no way to write a position that satisfies
 * neither (the defect the first #132 body would have shipped, editing only
 * the live side and leaving a venue-settled, legs-pending position matching
 * neither filter and vanishing from the screen entirely).
 *
 * Both groups are rendered from the SAME `positions` array and every
 * position renders exactly once. Record order is kept inside each group --
 * the partition reorders nothing on its own.
 */
function PositionGroups({
  positions,
  notes,
  venuePollMs,
  asOfMs,
  maxQuoteAgeMs,
}: {
  positions: HeldPosition[];
  notes: Record<string, string>;
  venuePollMs: number | null;
  asOfMs: number;
  maxQuoteAgeMs: number;
}) {
  const isLive = (position: HeldPosition) =>
    position.pending_legs > 0 && position.venue_settlement === null;
  const pending = positions.filter(isLive);
  const settled = positions.filter((position) => !isLive(position));

  return (
    <>
      {pending.length > 0
        ? pending.map((position) => (
            <Position
              key={position.id}
              position={position}
              notes={notes}
              venuePollMs={venuePollMs}
              asOfMs={asOfMs}
              maxQuoteAgeMs={maxQuoteAgeMs}
            />
          ))
        : settled.length > 0 && (
            <p className="text-sm text-muted">Nothing live right now.</p>
          )}
      {settled.length > 0 && (
        <details className="rounded-lg border border-border">
          <summary className="cursor-pointer p-3 text-sm text-muted">
            {settled.length} settled ticket{settled.length === 1 ? "" : "s"}
          </summary>
          <div className="flex flex-col gap-4 p-3 pt-0">
            {settled.map((position) => (
              <Position
                key={position.id}
                position={position}
                notes={notes}
                venuePollMs={venuePollMs}
                asOfMs={asOfMs}
                maxQuoteAgeMs={maxQuoteAgeMs}
              />
            ))}
          </div>
        </details>
      )}
    </>
  );
}

/**
 * What the venue holds that this record does not.
 *
 * **Record order, one colour, no red** — the coordinator's own wording, and
 * deliberately: this is a coverage fact, not an alarm, and ADR 0071 §2.5's
 * "a per-row fact is transparency; an ordering is a claim" applies to the
 * list here exactly as it does to the positions above.
 */
function VenueCoverageBanner({ unrecorded }: { unrecorded: UnrecordedAtVenue[] }) {
  if (unrecorded.length === 0) return null;
  const plural = unrecorded.length === 1 ? "" : "s";
  const verb = unrecorded.length === 1 ? "is" : "are";
  return (
    <div className="rounded-lg border border-border p-3 text-sm" role="status">
      <p>
        {unrecorded.length} Kalshi combination{plural} at the venue {verb} not
        recorded here:
      </p>
      <ul className="mt-1.5 flex flex-col gap-0.5 text-xs">
        {unrecorded.map((row) => (
          <li key={row.ticker} className="tabular">
            {row.ticker} &middot; {row.contracts ?? "--"} contracts &middot;{" "}
            {row.exposure_display}
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-xs text-muted">
        <a href="#record-parlay" className="underline decoration-dotted">
          Record it below
        </a>{" "}
        to watch it.
      </p>
    </div>
  );
}

function Position({
  position,
  notes,
  venuePollMs,
  asOfMs,
  maxQuoteAgeMs,
}: {
  position: HeldPosition;
  notes: Record<string, string>;
  venuePollMs: number | null;
  asOfMs: number;
  maxQuoteAgeMs: number;
}) {
  return (
    <section
      aria-label={`${position.label} ticket`}
      className="flex flex-col rounded-lg border border-border p-4"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-widest">
          {position.label}
        </h2>
        <span className="tabular text-sm text-muted">
          {position.stake_display}
          {position.entry_fee_display
            ? ` + ${position.entry_fee_display} fee`
            : ""}{" "}
          &rarr; {position.return_display}
        </span>
      </header>
      <StakeBasisLine position={position} />
      <p className="mt-1 text-xs leading-snug text-muted">
        {position.source === "kalshi_combo" ? "Kalshi combo" : "Sportsbook"}
        {position.book ? ` · ${position.book}` : ""} ·{" "}
        {position.state_detail}
      </p>
      <VenueStatusLine
        position={position}
        venuePollMs={venuePollMs}
        asOfMs={asOfMs}
      />
      <ComboBookLine position={position} />

      <ol className="mt-3 divide-y divide-border">
        {position.legs.map((leg) => (
          <Leg key={leg.id} leg={leg} maxQuoteAgeMs={maxQuoteAgeMs} />
        ))}
      </ol>

      <Hedge block={position.hedge} position={position} notes={notes} />

      <Close position={position} />
    </section>
  );
}

/**
 * One small line under the stake, on the ticket whose stake is NOT Kalshi's
 * own number — and nothing at all on the ticket whose stake is.
 *
 * Issue #53, answered A by Joe on 2026-09-16. ADR 0160 resolves each open
 * position's stake at read time and serves `stake_basis` beside it;
 * `lib/stakeBasisGloss.ts` turns the refusal that applied into a sentence.
 *
 * **The condition is the note's presence, never the basis's value**, and that
 * is the whole guard. Rendering on `stake_basis === "as_recorded"` would put
 * an unresolved ticket (`null`) on the same blank row as a checked one, which
 * is the `ParlayCards` defect of 2026-09-15 in its other direction — there a
 * note rendered only when `anchored_on_sharp === true` and a leg with no
 * sharp book behind it said nothing. `stakeBasisNote` returns `null` for
 * exactly one input and the component asks it rather than deciding again.
 */
function StakeBasisLine({ position }: { position: HeldPosition }) {
  const note = stakeBasisNote(
    position.stake_basis,
    position.stake_basis_reason,
  );
  if (!note) return null;
  return <p className="mt-1 text-xs leading-snug text-muted">{note}</p>;
}

/**
 * The two dead-ticket facts, in precedence order.
 *
 * A settlement from the venue is definitive and comes first: which leg lost
 * is not knowable from it alone (leg markets can finalize later, or Joe
 * marks them), so nothing here touches a leg's own `outcome` — only the
 * words say more than the legs below currently do. Absence from the latest
 * positions poll is the weaker fact — a position also stops appearing there
 * when it is simply closed some other way — and is shown only when there is
 * no settlement to say more.
 */
function VenueStatusLine({
  position,
  venuePollMs,
  asOfMs,
}: {
  position: HeldPosition;
  venuePollMs: number | null;
  asOfMs: number;
}) {
  if (position.venue_settlement) {
    const { market_result, settled_ms } = position.venue_settlement;
    const outcome =
      market_result === "yes" ? "won" : market_result === "no" ? "lost" : (market_result ?? "unknown");
    const date = new Date(settled_ms).toLocaleDateString("en-US", {
      timeZone: DISPLAY_TIME_ZONE,
      year: "numeric",
      month: "short",
      day: "numeric",
    });
    return (
      <p className="mt-1 text-xs text-muted">
        Settled at the venue: {outcome} on {date}.
      </p>
    );
  }
  if (position.at_venue === false) {
    const age =
      venuePollMs !== null ? describeQuoteAge(asOfMs - venuePollMs) : null;
    return (
      <p className="mt-1 text-xs text-muted">
        This ticket is no longer at the venue
        {age ? ` (last positions read ${age})` : ""}.
      </p>
    );
  }
  return null;
}

/**
 * What the public order book says this combination could be sold back for
 * right now (#95) -- its own block, deliberately NOT next to `stake_display`
 * above: `parlay_positions` has no contracts column, so a price beside a
 * total stake invites dividing one by the other with no denominator on the
 * wire (review D5). Renders nothing at all -- not a sentence, silence -- on
 * a sportsbook slip and on any ticket this build cannot read a combo book
 * for; `comboBookNote` owns that decision, the same split
 * `stakeBasisNote`/`StakeBasisLine` already uses for `stake_basis`.
 */
function ComboBookLine({ position }: { position: HeldPosition }) {
  const note = comboBookNote(position.combo_book, position.combo_book_reason);
  if (!note) return null;
  return (
    <p className="mt-1 text-xs leading-snug text-muted">
      {note}{" "}
      {position.source === "kalshi_combo" && (
        <span className="text-muted">{COMBO_BOOK_ASK_POINTER}</span>
      )}
    </p>
  );
}

/** One leg: what it is, what the venue says it is worth now, and how it settled. */
function Leg({ leg, maxQuoteAgeMs }: { leg: HeldLeg; maxQuoteAgeMs: number }) {
  const age = describeQuoteAge(leg.quote_age_ms);
  const stale = leg.quote_age_ms !== null && leg.quote_age_ms > maxQuoteAgeMs;
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-1.5">
      {/*
        One colour for every outcome, deliberately. Colour in this product
        makes claims — green is "we found something" — and "this leg lost" is
        a fact the WORD already carries. A red leg would read as an alarm on a
        screen whose whole job is to be calm about money already at risk.
      */}
      <span className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-muted">
        {leg.outcome === "pending" ? "live" : leg.outcome}
      </span>
      <span className="flex-1 text-sm">
        {leg.label}
        {leg.is_hedge_leg && (
          <span className="ml-2 text-[11px] uppercase tracking-wide text-muted">
            hedge here
          </span>
        )}
        {/*
          The game, under the label. A total's label is Kalshi's subtitle
          ("Under 8.5 runs scored") and names no teams, so a recorded totals
          parlay read as three identical lines (2026-09-15). Absent on a leg
          recorded before schema v43 or typed by hand -- then the label
          stands alone, never a game guessed from the ticker. The ": Total
          Runs" suffix is the market kind, dropped as on the parlay card.
        */}
        {leg.event_title !== null && (
          <span className="block text-[11px] text-muted" data-testid="held-leg-game">
            {leg.event_title.replace(/:\s*Total(?:\s+\w+)?$/i, "").trim()}
          </span>
        )}
      </span>
      {/*
        A percentage or "--". Never 0%: an absent bid and a leg nobody wants
        are different facts, and the payload keeps them apart. Dimmed, never
        hidden, once its quote is older than the same bound a hedge quote
        would be refused at -- the price is still what was last seen, and
        saying so plainly is better than pretending it did not move.
      */}
      <span
        className={`tabular text-sm ${stale ? "text-muted opacity-60" : ""}`}
      >
        {leg.chance_display}
        {age && (
          <span className="ml-1 text-[10px] font-normal text-muted">
            {age}
          </span>
        )}
      </span>
      {leg.outcome === "pending" ? (
        <LegControls leg={leg} />
      ) : (
        <span className="w-full text-[11px] text-muted">
          {leg.resolved_source === "venue"
            ? "settled by the exchange"
            : "marked by you"}
        </span>
      )}
    </li>
  );
}

/**
 * Marking a leg the exchange cannot settle.
 *
 * Required rather than convenient: a sportsbook leg has no Kalshi ticker, so
 * `kalshi_markets.result` can never reach it, and without this the lock case
 * is unreachable for exactly the slips this feature was asked for. The screen
 * says afterwards which source settled the leg, because the two are not
 * equally good evidence.
 */
function LegControls({ leg }: { leg: HeldLeg }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  async function mark(outcome: "won" | "lost" | "void") {
    setBusy(true);
    setRefused(null);
    const answer = await resolveHeldLeg(leg.id, outcome);
    setBusy(false);
    if (!answer.ok) {
      setRefused(answer.detail);
      return;
    }
    router.refresh();
  }

  return (
    <span className="flex w-full flex-wrap items-center gap-2 pt-1">
      {(["won", "lost", "void"] as const).map((outcome) => (
        <button
          key={outcome}
          type="button"
          disabled={busy}
          onClick={() => mark(outcome)}
          className="min-h-9 rounded border border-border px-3 text-[11px] uppercase tracking-wide disabled:opacity-50"
        >
          {outcome}
        </button>
      ))}
      {leg.ticker && (
        <a
          href={kalshiMarketUrl(leg.ticker)}
          target="_blank"
          rel="noreferrer"
          className="min-h-9 self-center text-[11px] underline decoration-dotted"
        >
          open on Kalshi
        </a>
      )}
      {refused && (
        <span className="w-full text-[11px] text-muted">{refused}</span>
      )}
    </span>
  );
}

function Hedge({
  block,
  position,
  notes,
}: {
  block: HedgeBlock | null;
  position: HeldPosition;
  notes: Record<string, string>;
}) {
  // `null` and a refusal are different answers. A ticket whose legs have all
  // won has nothing to hedge; a ticket whose hedge market has an empty book
  // has something we could not price. Collapsing them would make "nothing to
  // do" and "we could not look" the same empty card.
  if (block === null) return null;

  if (block.refusal) {
    return (
      <p className="mt-3 rounded border border-border p-3 text-sm text-muted">
        No hedge price: {block.refusal.detail}
      </p>
    );
  }

  if (block.kind === "derisk") {
    return (
      <div className="mt-3 rounded border border-border p-3">
        <h3 className="text-xs font-semibold uppercase tracking-widest">
          <Term k="derisk">de-risk</Term> only
        </h3>
        <p className="mt-1 text-xs leading-snug text-muted">{notes.derisk}</p>
        <p className="mt-2 text-sm">
          Venue&rsquo;s implied chance this ticket still wins:{" "}
          <span className="tabular">{block.chance_display}</span>
          {block.notional_value_display &&
            block.notional_value_display !== "--" && (
              <>
                {" "}
                &middot; worth about{" "}
                <span className="tabular">
                  {block.notional_value_display}
                </span>{" "}
                on paper
              </>
            )}
        </p>
        {block.chance_refusal && (
          <p className="mt-1 text-xs text-muted">
            {block.chance_refusal.detail}
          </p>
        )}
        <Ladder block={block} position={position} />
      </div>
    );
  }

  return (
    <div className="mt-3 rounded border border-border p-3">
      {/* The payload field is still named `guaranteed` -- it is the alert
          predicate's name (`Lock.is_guaranteed_profit`) and `notify/alerts.py`,
          `notify/discord.py` and the tests read it. The figure it flags is
          rendered as "about $X either way -- an estimate", and that is not a
          mismatch to fix: the name means "the best fillable rung comes out
          ahead in both branches", and the figure is an estimate of by how
          much. Issue #43, answer A. */}
      <EstimateHeadline
        figure={
          block.guaranteed && block.guaranteed_display
            ? block.guaranteed_display
            : null
        }
        grain={block.uncertainty_display ?? null}
      />
      {block.full_hedge_is_out_of_reach && block.equalising && (
        <p className="mt-1 text-xs text-muted">
          The full hedge is {block.equalising.contracts} contracts costing{" "}
          <span className="tabular">{block.equalising.cost_display}</span>
          {position.bankroll_known
            ? " — more than your balance covers."
            : " — and your balance could not be read, so nothing here is capped by it."}
        </p>
      )}
      <p className="mt-1 text-xs leading-snug text-muted">{notes.upper_bound}</p>
      <Ladder block={block} position={position} />
    </div>
  );
}

/**
 * The figure, called what it is.
 *
 * "about $X either way — an estimate", then the size of the largest measured
 * error term on THIS ticket (`grain`, rendered server-side; see
 * `hedge.estimate_grain`), in the same element and at the same type size as
 * the number. Joe's answer A to issue #43 asked for exactly that: not "lock",
 * not "whichever way", and the uncertainty beside the number rather than in
 * smaller type underneath. `tests/test_hedge_headline_calls_the_figure_an_estimate.py`
 * reads this function's source and refuses the old words.
 *
 * With no fillable size that comes out ahead there is no figure, and the
 * sentence says so without promising one.
 */
function EstimateHeadline({
  figure,
  grain,
}: {
  figure: string | null;
  grain: string | null;
}) {
  return (
    <>
      <h3 className="text-xs font-semibold uppercase tracking-widest">
        one leg left
      </h3>
      {figure ? (
        <p className="mt-1 text-lg leading-snug tabular">
          <span className="font-semibold">about {figure} either way</span>
          {" "}&mdash; an estimate{grain ? `: ${grain}` : ""}
        </p>
      ) : (
        <p className="mt-1 text-sm text-muted">
          No size you could buy right now comes out ahead either way.
        </p>
      )}
    </>
  );
}

/**
 * The sizes, with both branches beside each.
 *
 * A partial hedge is the realistic move on a small bankroll, so "all or
 * nothing" would hide the choice actually available. Every figure is a string
 * the server rendered; this component does no money arithmetic.
 */
function Ladder({
  block,
  position,
}: {
  block: HedgeBlock;
  position: HeldPosition;
}) {
  const ladder = block.ladder ?? [];
  if (ladder.length === 0) return null;

  return (
    <>
      <p className="mt-3 text-xs text-muted">
        Buy {block.side?.toUpperCase()} at{" "}
        <span className="tabular">{block.ask_display}</span>
        {block.depth_at_ask !== null && block.depth_at_ask !== undefined && (
          <> &middot; {Math.floor(block.depth_at_ask)} resting</>
        )}
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted">
            <tr className="text-left">
              <th className="py-1 pr-3 font-normal">contracts</th>
              <th className="py-1 pr-3 font-normal">costs</th>
              <th className="py-1 pr-3 font-normal">if the leg wins</th>
              <th className="py-1 pr-3 font-normal">if it loses</th>
              <th className="py-1 font-normal">worst case</th>
            </tr>
          </thead>
          <tbody>
            {ladder.map((rung) => (
              <Rung key={rung.contracts} rung={rung} position={position} />
            ))}
          </tbody>
        </table>
      </div>
      {block.ticker && (
        <p className="mt-2 text-xs text-muted">
          {/* No buy control: see this component's docstring. */}
          <a
            href={kalshiMarketUrl(block.ticker)}
            target="_blank"
            rel="noreferrer"
            className="underline decoration-dotted"
          >
            Place it on Kalshi
          </a>
        </p>
      )}
    </>
  );
}

function Rung({
  rung,
  position,
}: {
  rung: HedgeRung;
  position: HeldPosition;
}) {
  // A rung you cannot fill or cannot pay for is shown rather than hidden --
  // "the full hedge is 100 contracts and 40 are resting" is the useful
  // sentence -- but it is dimmed so it does not read as available.
  const reachable = rung.fillable && rung.affordable;
  return (
    <tr className={reachable ? "" : "text-muted opacity-60"}>
      <td className="tabular py-1 pr-3">{rung.contracts}</td>
      <td className="tabular py-1 pr-3">{rung.cost_display}</td>
      <td className="tabular py-1 pr-3">{rung.if_leg_wins_display}</td>
      <td className="tabular py-1 pr-3">{rung.if_leg_loses_display}</td>
      <td className="tabular py-1">
        {rung.floor_display}
        {!rung.fillable && (
          <span className="ml-1 text-[10px] uppercase">not resting</span>
        )}
        {rung.fillable && !rung.affordable && position.bankroll_known && (
          <span className="ml-1 text-[10px] uppercase">over balance</span>
        )}
      </td>
    </tr>
  );
}

function Close({ position }: { position: HeldPosition }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  async function close() {
    setBusy(true);
    setRefused(null);
    const answer = await closeHeldPosition(position.id, "settled");
    setBusy(false);
    if (!answer.ok) {
      setRefused(answer.detail);
      return;
    }
    router.refresh();
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={busy}
        onClick={close}
        className="min-h-9 rounded border border-border px-3 text-[11px] uppercase tracking-wide disabled:opacity-50"
      >
        done with this ticket
      </button>
      <span className="text-[11px] text-muted">
        Stops watching it. Nothing is deleted.
      </span>
      {refused && <span className="w-full text-[11px] text-muted">{refused}</span>}
    </div>
  );
}
