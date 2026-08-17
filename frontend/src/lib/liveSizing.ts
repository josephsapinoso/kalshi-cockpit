/**
 * Whether a Board row is still offering a size, and what to say when it is not.
 *
 * **The defect this exists to fix.** `LiveBoard` merges a streamed quote over
 * the recorded row and overwrites `suggested_contracts` with `quote.contracts`
 * (`LiveBoard.tsx`). `backend/live.py` computes that with the same
 * `size_position` the order endpoint uses, so when the price moves against the
 * row mid-stream it can legitimately become **0** -- deliberately, per its own
 * docstring: *"the card stops offering a size the server would refuse."*
 *
 * What the merge does **not** overwrite is everything derived from the old
 * size: `total_cost_dollars`, `stake_dollars`, `fee_predicted`, `ev_net_dollars`,
 * `sd_dollars`, and `reason_text`. So the card lost its cost block to a
 * `suggested_contracts > 0` guard, kept a `reason_text` still reading
 * *"Sized at 14."*, and stayed wrapped in `TicketTrigger` -- tappable, opening a
 * ticket for a size the server has already decided to refuse.
 *
 * That is this repo's named failure in the dangerous direction: a screen
 * offering a row the server will refuse. `CLAUDE.md` states the rule as *"never
 * trust that the UI disabled a button"*; the server-side re-validation is
 * intact and would reject the order, so nothing could actually be bought. The
 * cost is a tap, a 422, and -- worse -- a card that reads as live and sized
 * when it is neither.
 *
 * **Why a module and not an inline ternary.** Every other frontend guard here
 * asserts on source text, which passes unchanged against a predicate that has
 * been exactly inverted. A wrong verdict is precisely this defect, so the
 * verdict is extracted where a test can *execute* it -- the same reasoning, and
 * the same shape, as `sweepTone.ts`. Plain TypeScript, no React import, so
 * `node` can call the shipped function directly.
 *
 * **The predicate is `<= 0`, not `=== 0`.** Unreadable resolves to refusing,
 * never to offering: a negative or `NaN` size is not a size, and the safe
 * answer to "should this be tappable" is no. `NaN <= 0` is `false`, so it is
 * tested for explicitly rather than trusted to the comparison.
 *
 * What this establishes: the mapping from a row's size to whether it may be
 * offered. What it does **not** establish: that `LiveBoard` actually calls it
 * (`tests/test_live_unsized_row.py` pins that edge separately), that the copy
 * is accurate, or that `backend/live.py` zeroes the size correctly -- that is
 * `tests/test_live.py`.
 */

export type SizingState = "sized" | "unsized";

export interface SizingVerdict {
  state: SizingState;
  /** Whether the card may be wrapped in a ticket trigger. */
  offerable: boolean;
  /**
   * What to show in place of `reason_text`, which is stale whenever the size
   * was overwritten by the feed. `null` when the recorded reason still holds.
   */
  note: string | null;
}

const SIZED: SizingVerdict = { state: "sized", offerable: true, note: null };

export function liveSizing(row: {
  suggested_contracts: number;
  /** This row's price arrived over the live feed rather than from the record. */
  live?: boolean;
}): SizingVerdict {
  const contracts = row.suggested_contracts;

  if (typeof contracts !== "number" || Number.isNaN(contracts) || contracts <= 0) {
    return {
      state: "unsized",
      offerable: false,
      note: row.live
        ? // Says what happened and what it means, in that order. Not "error",
          // because nothing failed -- the feed did its job.
          "The price moved. This is no longer sized at this ask, so there is nothing to take."
        : // A row served by /api/board is in `surfaced` only when
          // `suggested_contracts > 0` (`routes.py`), so this branch is
          // unreachable from the server today. It is written rather than
          // omitted because the guard must not depend on that staying true --
          // an unsized row is un-offerable however it got here.
          "Not sized at this ask, so there is nothing to take.",
    };
  }

  return SIZED;
}
