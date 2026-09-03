/**
 * The odds feed's sport keys, in the words a bettor uses.
 *
 * `baseball_mlb` is the vendor's identifier and rendered verbatim on the
 * refresh panel and the window timetable — vendor vocabulary on a screen
 * built for a novice (2026-08-22 review, A5). The map covers the keys this
 * deployment can actually carry (`ODDS_MARKETS` and the seasonal scope);
 * an unknown key renders AS ITSELF, never a guess — inventing a league name
 * for a key this build has not met is the unreadable-resolves-to-a-value
 * defect wearing a friendly face.
 *
 * **Two vocabularies reach this function, and until 2026-09-03 it knew one.**
 * `/api/board` and `/api/slate` fill a row's `league` from
 * `event_links.league`, which holds Kalshi's `product_metadata.competition`
 * verbatim -- "Pro Baseball", "Pro Basketball (W)" -- while the #15 filter
 * chip and the parlay legs carry The Odds API's sport key for the same
 * partition. So a Games row read "PRO BASEBALL" under a chip that said "MLB"
 * (noted at the #15 merge, ticket-less). The competition strings below are
 * Kalshi's own spelling, copied from `IN_SCOPE_LEAGUES` in
 * `backend/kalshi/discovery.py`; `tests/test_league_label.py` pins the two
 * maps equal so a league added on one side cannot render as a vendor string
 * on the other. The unknown-renders-as-itself rule is unchanged.
 */

const LEAGUES: Record<string, string> = {
  baseball_mlb: "MLB",
  basketball_wnba: "WNBA",
  basketball_nba: "NBA",
  americanfootball_nfl: "NFL",
  americanfootball_ncaaf: "NCAA football",
  icehockey_nhl: "NHL",
};

/** Kalshi's `competition` strings, exactly as Kalshi spells them, to the
 *  sport key `LEAGUES` is keyed on. Do not tidy these strings (see
 *  `discovery.py`: "Womens Pro Basketball" was guessed once and the league
 *  vanished from the Board). */
const KALSHI_COMPETITIONS: Record<string, string> = {
  "Pro Baseball": "baseball_mlb",
  "Pro Football": "americanfootball_nfl",
  "NCAA Football": "americanfootball_ncaaf",
  "Pro Basketball (M)": "basketball_nba",
  "Pro Basketball (W)": "basketball_wnba",
  "Pro Hockey": "icehockey_nhl",
};

export function leagueLabel(sportKeyOrCompetition: string): string {
  const key = KALSHI_COMPETITIONS[sportKeyOrCompetition] ?? sportKeyOrCompetition;
  return LEAGUES[key] ?? sportKeyOrCompetition;
}
