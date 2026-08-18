/**
 * Which team a ticket is actually betting on, in words.
 *
 * **The defect this exists for.** `rec.team` is `m.yes_side_team`
 * (`backend/api/routes.py:2949`) — *always* the YES-side team, whatever side is
 * being bought. `backend/runner.py:1278` generates a row for both sides of every
 * moneyline (`for side in ("yes", "no")`), and its own comment says why buying
 * NO is buying the opponent. So on a NO row the ticket's heading is the name of
 * the team the bet pays out *against*, and the only correction on screen is a
 * small uppercase `NO` pill in the meta row beneath it.
 *
 * A pill reads as a tag. This function produces the sentence that reads as a
 * negation.
 *
 * **Why a predicate rather than a ternary in the JSX.** A substring test passes
 * unchanged on a mapping that has been exactly inverted, and inverted is
 * precisely the failure mode here — the wrong answer is the *other team's name*,
 * which looks entirely plausible on screen. `tests/test_bet_direction.py` runs
 * this function under node against both sides so the mapping is executed rather
 * than read. Same reasoning as `sweepTone.ts`.
 *
 * **What it deliberately does not say.** Not "pays if they win". `team` is
 * non-null only where the market carries a `yes_side_team`, and this module has
 * no way to know whether that market is a game winner, a spread or a total —
 * `market_type` is on the row in the database and is not in the payload
 * (verified against `/api/board` on the demo instance: absent). "Against" is
 * true for every market where the YES side resolves for that team; "pays if they
 * lose" would not be. The payout sentence needs a field that does not exist yet.
 *
 * **Props get nothing, on purpose.** `yes_side_team` is NULL on a prop, so the
 * heading falls back to a raw ticker and this returns `null` rather than
 * inventing a subject. Opaque is not the same as wrong, and the repo convention
 * is that unreadable resolves to nothing and the caller refuses rather than
 * substitutes. Naming the player and the line needs `market_title`, which
 * `routes.py` selects at `:694`, `:888` and `:1040` and never emits.
 */

/** The words to build the sentence from, or `null` when there is no subject. */
export type BetDirection = {
  /** `"on"` for a YES row, `"against"` for a NO row. */
  preposition: "on" | "against";
  /** The YES-side team name, exactly as the server sent it. */
  team: string;
};

/**
 * The direction of the bet, or `null` when the row cannot support the sentence.
 *
 * `null` on: a missing or blank team (props), and any `side` that is not
 * recognisably yes or no. **An unrecognised side must never fall through to
 * "on"** — that is the inverted mapping this module exists to prevent, and
 * silence is the safe answer where the direction is unknown.
 */
export function betDirection(rec: {
  side: string | null | undefined;
  team: string | null | undefined;
}): BetDirection | null {
  const team = typeof rec.team === "string" ? rec.team.trim() : "";
  if (team.length === 0) return null;

  const side = typeof rec.side === "string" ? rec.side.trim().toLowerCase() : "";
  if (side === "yes") return { preposition: "on", team };
  if (side === "no") return { preposition: "against", team };
  return null;
}
