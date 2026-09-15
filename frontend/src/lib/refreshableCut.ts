/**
 * The refresh panel follows the league chip — Joe, 2026-09-15.
 *
 * The chip (`FilterBar`, decision-map #15) cuts the rows on the list
 * screens, and until this file the "Refresh the odds" card beneath them
 * ignored it: with NFL selected, the card still listed every MLB game with
 * a prop tap and nothing NFL, which reads as "no NFL props exist" rather
 * than "no NFL game is inside the card's 24-hour horizon". The rows and the
 * card answer different questions (what is stored vs. what a tap can buy),
 * but a screen cut to one league that offers to spend on another is a
 * screen with two different ideas of which league it is showing.
 *
 * Pure, and executed under node by `tests/test_refreshable_cut.py`, because
 * the interesting case — the chosen league has nothing inside the horizon —
 * must be told apart from "nothing at all inside the horizon", and a
 * substring assertion on the panel cannot tell those two states apart.
 */

export type RefreshableCut<S extends { sport_key: string }> =
  /** No chip, or the chip's league has fixtures: draw these. */
  | { kind: "listed"; sports: S[] }
  /** The desk stores nothing inside the horizon for any league. */
  | { kind: "nothing_stored" }
  /**
   * The chip names a league with no fixture inside the horizon while other
   * leagues have some. Not the same as `nothing_stored`: the way out is to
   * clear the chip, and the card must say that rather than "no slate".
   */
  | { kind: "league_outside_horizon"; league: string; others: number };

export function cutRefreshable<S extends { sport_key: string }>(
  sports: readonly S[],
  league: string | null,
): RefreshableCut<S> {
  if (sports.length === 0) return { kind: "nothing_stored" };
  if (league === null) return { kind: "listed", sports: [...sports] };
  const kept = sports.filter((s) => s.sport_key === league);
  if (kept.length === 0) {
    return { kind: "league_outside_horizon", league, others: sports.length };
  }
  return { kind: "listed", sports: kept };
}
