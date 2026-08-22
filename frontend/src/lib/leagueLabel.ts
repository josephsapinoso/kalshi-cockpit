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
 */

const LEAGUES: Record<string, string> = {
  baseball_mlb: "MLB",
  basketball_wnba: "WNBA",
  basketball_nba: "NBA",
  americanfootball_nfl: "NFL",
  americanfootball_ncaaf: "NCAA football",
  icehockey_nhl: "NHL",
};

export function leagueLabel(sportKey: string): string {
  return LEAGUES[sportKey] ?? sportKey;
}
