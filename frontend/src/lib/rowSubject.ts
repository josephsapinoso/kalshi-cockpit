/**
 * The name a slate row prints, and how that row is bought.
 *
 * **The defect this exists for (ticket #6).** `rec.team` is
 * `kalshi_markets.yes_side_team` on *both* rows of a market -- the YES-side
 * team whatever side the row prices -- and the Games row printed it as the
 * row's name with no side beside it. The runner writes a row for each side of
 * every moneyline, so on a NO row the name was the opponent of the team the
 * bet pays on; and with both sides present on 98.9% of tickers in the window
 * the screen draws from, the same name stood on two adjacent rows with
 * different asks and nothing to tell them apart.
 *
 * **What the name is now.** `rec.side_outcome` is `fair_prices.outcome_name`
 * on the row's own `fair_price_id`, which `backend/runner.py` binds per side
 * (YES to the market's outcome, NO to the other one) -- a recorded fact about
 * that side, read from the server, never derived here. The one thing this
 * module chooses is *which* recorded name to print:
 *
 * - a YES row on a team market keeps printing `team`, exactly as before, so
 *   the rows that were already right do not change spelling (`yes_side_team`
 *   is alias-normalised; `outcome_name` is the odds feed's spelling, and the
 *   two have not been checked against each other);
 * - a NO row on a team market prints `side_outcome` -- the team NO buys --
 *   with `NO on {team}` beside it, because the reader also needs to know
 *   which Kalshi market to tap NO on;
 * - a row with no `team` (a prop or a total, where `yes_side_team` is NULL)
 *   keeps the ticker as its name, since the ticker carries the player and the
 *   line, and puts `side_outcome` ("Over", "Under", a player) in the tag. The
 *   row *is* about a side of a total, so "Under" is the honest word there,
 *   and it is why the outcome may never overwrite `team`.
 *
 * **Refuses rather than guesses.** A NO row with no `side_outcome` prints its
 * ticker, never `team` -- `team` on a NO row is the exact wrong answer this
 * module ends, and a plausible team name is worse than an opaque ticker. An
 * unreadable `side` prints the ticker with no tag, the same silence
 * `betDirection.ts` keeps for the same reason: an inverted mapping produces
 * the other team's name in a perfectly ordinary-looking row.
 *
 * Executed under node by `tests/test_row_subject.py` against both sides,
 * rather than read, because the failure mode looks correct on screen.
 */

export type RowSubject = {
  /** What the row prints as its name. Never empty. */
  name: string;
  /**
   * How the row is bought, for the small tag beside the name: `"YES"`,
   * `"NO on {team}"`, `"YES · Over"`, ... `null` when `side` is unreadable.
   */
  how: string | null;
};

function clean(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length === 0 ? null : trimmed;
}

export function rowSubject(rec: {
  ticker: string;
  side: string | null | undefined;
  team: string | null | undefined;
  side_outcome?: string | null;
}): RowSubject {
  const team = clean(rec.team);
  const outcome = clean(rec.side_outcome);
  const side = typeof rec.side === "string" ? rec.side.trim().toLowerCase() : "";

  if (side === "yes") {
    if (team !== null) return { name: team, how: "YES" };
    return { name: rec.ticker, how: outcome ? `YES · ${outcome}` : "YES" };
  }
  if (side === "no") {
    if (team !== null) {
      return { name: outcome ?? rec.ticker, how: `NO on ${team}` };
    }
    return { name: rec.ticker, how: outcome ? `NO · ${outcome}` : "NO" };
  }
  return { name: rec.ticker, how: null };
}
