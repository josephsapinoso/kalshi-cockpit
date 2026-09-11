/**
 * The words for "how deep am I already?", rendered beside the buy button.
 *
 * **Why this is a module and not JSX inside `ManualTicket.tsx`.** The rule it
 * enforces is the one this repo has a standing convention about — *unreadable
 * resolves to `None`, never `0`* — and the failure mode is a branch that
 * quietly substitutes a number for a refusal. A substring test over a 700-line
 * client component cannot see which branch a sentence sits in, and rendering
 * that component means driving a fetch and three hooks. Kept React-free and
 * pure, the branch table runs under node against the real server payload
 * (`tests/test_manual_ticket_exposure.py`), which is exactly the shape
 * `openPositionsStamps.ts` already takes and for the same reason.
 *
 * **It informs and it never blocks.** ADR 0112 removed all five brakes from
 * the hand-bet path on Joe's word; a refusal here, or a large figure here,
 * changes no button and disables nothing. `PriceOnKalshi.tsx`'s `QuoteAge`
 * block is the posture being matched — relabel, never gate. Nothing this
 * module returns is a predicate, which is why it returns words and a flag
 * about *readability*, and never a number a caller could compare.
 *
 * **No arithmetic on money, here or anywhere near here.** `staked_display` is
 * rendered server-side from integer tenths of a cent (`backend/bets.py`); this
 * file passes the string through and never divides by 1000. Ages are the
 * server's own subtraction against the same `now_ms` its staleness bounds use.
 *
 * What this does NOT establish: that the mirror behind the figure is complete
 * (a position opened while the poller was down is simply absent, and no
 * freshness stamp can say so), or that the venue's exposure unit means what
 * its suffix says — both are `open_positions`' own caveats and neither is
 * repaired by wording.
 */
import { countStamp, describeAge, type Stamp } from "./openPositionsStamps";
import type { OpenPositionsBlock } from "@/lib/api";

export type ExposureWords = {
  /**
   * The fact: a money figure with what it is on, or the server's own reason
   * it cannot be said. Never both, and never a `$` on a refusal.
   *
   * **What it is on lives INSIDE this string on purpose.** `OpenPositions.tsx`
   * learned it the expensive way: `/slate` printed a bold "$X staked" twice,
   * seven lines apart, for two different numbers — money on open positions,
   * and money committed since the day roll — and the muted qualifiers that
   * distinguished them were not what the eye took. The caller renders this
   * whole string emphasised, so the number never appears without its noun.
   */
  headline: string;
  /**
   * The caveat, rendered quietly beside the fact. `null` where there is none.
   * Never carries part of the fact — anything the reader must not miss goes
   * in `headline`.
   */
  qualifier: string | null;
  /**
   * Which read produced it and how old, or `null` when there is no read to
   * name. A figure whose read has no clock is shown with no clock rather than
   * with a borrowed one.
   */
  stamp: string | null;
  /**
   * True when no money figure could be read. The caller renders this as a
   * caution, never as `$0.00` — which would report "nothing at risk" off a
   * dead poller, the false negative in the flattering direction.
   */
  refused: boolean;
};

/** The sentence every refusal ends with. A refusal that stops at the cause
 *  reads as a technicality; this says what it means for the tap about to
 *  happen. */
const NOT_NOTHING = "That is not the same as nothing at risk.";

export function exposureWords(
  block: OpenPositionsBlock,
  timeZone: string,
): ExposureWords {
  // The COUNT's clock, never the value's. The two ride one cadence and are
  // two reads; `openPositionsStamps.ts` exists because one borrowed the
  // other's stamp and the borrowed one was the container's boot time. The
  // staked figure is selected by the very poll whose `row_count` is the
  // count (`backend/bets.py`), so this clock is the staked figure's own.
  const stamp = stampText(countStamp(block), timeZone);

  if (typeof block.staked_display === "string") {
    // Fresh, readable, and the venue holds nothing: say that in words rather
    // than printing "$0.00 staked", which is two spellings of nothing and
    // reads as a figure that failed.
    if (block.count === 0) {
      return {
        headline: "You have nothing open at the venue right now.",
        qualifier: null,
        stamp,
        refused: false,
      };
    }
    const positions =
      block.count === null
        ? "what is still open"
        : `${block.count} open ${block.count === 1 ? "position" : "positions"}`;
    return {
      headline: `You already have ${block.staked_display} staked on ${positions}`,
      qualifier: "your own money in, not what it is worth now.",
      stamp,
      refused: false,
    };
  }

  // Everything below is a refusal, and each one renders the SERVER's sentence.
  // `backend/bets.py` words five of them with care — "no positions poll has
  // succeeded yet" is a different fact from "not read in the last 30 minutes"
  // — and a screen that replaces them with one guess of its own is worse than
  // silence, because a guess reads as knowledge.
  if (typeof block.staked_refusal === "string") {
    const known =
      block.count === null
        ? "What you already have on"
        : `${block.count} ${block.count === 1 ? "position" : "positions"} are open, and what you have on them`;
    return {
      headline: `${known} could not be read — ${block.staked_refusal}. ${NOT_NOTHING}`,
      qualifier: null,
      stamp,
      refused: true,
    };
  }

  // Neither key present. Unreachable from `/api/exposure`, which always sends
  // both, and reachable from a deployed backend one version behind — so it
  // refuses rather than rendering nothing. Silence at a buy button is read as
  // "nothing", and nothing is the one thing this has not established.
  return {
    headline: `What you already have on could not be read — this backend does not report it. ${NOT_NOTHING}`,
    qualifier: null,
    stamp: null,
    refused: true,
  };
}

/**
 * What the ticket says when the route itself did not answer — a thrown fetch,
 * a non-2xx, a backend that has never heard of the path. Kept here, beside the
 * other refusals, so there is one place where "could not be read" is worded
 * and one rule about how it ends.
 */
export function exposureUnreadable(reason: string): ExposureWords {
  return {
    headline: `What you already have on could not be read — ${reason} ${NOT_NOTHING}`,
    qualifier: null,
    stamp: null,
    refused: true,
  };
}

/** "counted 7:47 AM, 3m ago" — the clock, and how stale it is. `null` when
 *  there is no read behind the figure: a stamp invented at render time would
 *  be a second lie in the same place. */
function stampText(s: Stamp | null, timeZone: string): string | null {
  if (s === null) return null;
  const at = new Date(s.asOfMs).toLocaleTimeString("en-US", {
    timeZone,
    hour: "numeric",
    minute: "2-digit",
  });
  const age = describeAge(s.ageMs);
  return age === null ? `counted ${at}` : `counted ${at}, ${age}`;
}
