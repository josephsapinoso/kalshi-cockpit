/**
 * Plain English for what the public order book says a held combination
 * could be sold back for right now (#95).
 *
 * FIVE STATES THAT MUST NEVER COLLAPSE INTO EACH OTHER — the review that
 * rewrote #95's body twice named the collapse (a failed read rendering as
 * "nothing resting") the critical defect (D1), so this module keeps them as
 * one switch with one branch per state and refuses a default case that
 * would fold an unrecognised state into a plausible-looking one.
 *
 * READ THIS FIRST — the claim these sentences must not make. Resting
 * combination YES bids HAVE been observed at the venue (2026-09-17: 5.10c /
 * 38,709 deep, 0.32c / 24,900 deep — `docs/measurements/
 * 2026-09-17-combinations-can-be-exited.md`). What does not exist is a
 * committed capture of one in this repo. Four frequency clauses about
 * combination liquidity have been written into this codebase and withdrawn;
 * the fourth was this ticket's own previous draft. So none of the sentences
 * below say how OFTEN a bid rests, how RARE one is, or that "there is no
 * exit" — Joe ruled on this twice (#60, #64): say what an exit costs, never
 * how often it exists. The only pointer allowed is the one that carries no
 * rate: makers can be asked directly on the Parlays page.
 *
 * WHAT THIS DOES NOT ESTABLISH
 * -----------------------------
 * - That the price shown is good, or that accepting it would fill. It is
 *   the public book's own best bid, read once, at the timestamp shown.
 * - Anything about the RFQ path. Asking a maker is a different action, at a
 *   different price, on a different screen (`POST /api/parlays/rfq`).
 * - That "not applicable" is temporary or permanent for a given ticket — a
 *   hand-recorded slip will never gain a ticker; a reader being unwired is
 *   a deploy fact this module cannot see.
 */

import { DISPLAY_TIME_ZONE } from "./api";

export type ComboBookState = "bid" | "empty" | "unpriced_interest" | "unreadable";

export type ComboBook = {
  state: ComboBookState;
  observed_ms: number;
  price_display: string | null;
  size: number | null;
};

/**
 * How stale a combo-book read is, at second precision — the same grain
 * `describeQuoteAge` in `HedgePositions.tsx` uses for a leg's own quote,
 * because both answer "how much has changed since this number was read".
 */
function describeAge(ms: number): string {
  const deltaMs = Date.now() - ms;
  const seconds = Math.floor(Math.max(0, deltaMs) / 1000);
  if (seconds < 1) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

function stampedAt(observedMs: number): string {
  const time = new Date(observedMs).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  });
  return `Public book at ${time} (${describeAge(observedMs)})`;
}

/**
 * One sentence per state, or `null` for "not applicable" (the fifth state,
 * which is silence — the row says nothing at all). `combo_book_reason` is
 * accepted but never rendered: it is a deploy/data fact for someone reading
 * the API response, not a sentence Joe needs on a phone mid-game.
 */
export function comboBookNote(
  comboBook: ComboBook | null,
  comboBookReason?: string | null,
): string | null {
  if (comboBook === null) return null;
  const stamp = stampedAt(comboBook.observed_ms);
  switch (comboBook.state) {
    case "bid": {
      const sizeClause =
        comboBook.size !== null
          ? `, ${Math.round(comboBook.size).toLocaleString("en-US")} contracts.`
          : ".";
      return `${stamp}: best bid to buy this back ${comboBook.price_display} per contract${sizeClause}`;
    }
    case "empty":
      return `${stamp}: nothing resting on the buy-back side.`;
    case "unpriced_interest":
      return `${stamp}: someone is resting here at a price finer than this screen can show.`;
    case "unreadable":
      return `${stamp}: could not be read.`;
    default: {
      // Exhaustiveness guard: a sixth state added to the wire without a
      // sentence here fails to compile rather than falling through to a
      // plausible-looking default.
      const neverState: never = comboBook.state;
      throw new Error(`comboBookNote: unhandled state ${String(neverState)}`);
    }
  }
}

/** The one pointer allowed beside a combo-book line — carries no rate. */
export const COMBO_BOOK_ASK_POINTER =
  "You can also ask makers for a price on the Parlays page.";
