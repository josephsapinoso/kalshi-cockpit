/**
 * Game-event helpers shared by `/game/<event>` and `/market/<ticker>` (#389).
 *
 * The slate has its own copy of `gameEventOf`; a page must not import from
 * `app/slate`, so the market page's link to its game reads from here.
 */

/** The game event ticker for a game-series market ticker, else `null`.
 *  `KXNFLGAME-26SEP13ATLPIT-ATL` -> `KXNFLGAME-26SEP13ATLPIT`. Only a GAME
 *  series names the game itself; a spread or prop ticker's suffix is the
 *  same fixture but its prefix is not the game series', so it does not guess
 *  one. */
export function gameEventOf(ticker: string): string | null {
  const match = /^(KX[A-Z0-9]*GAME-[A-Z0-9]+)-[A-Z0-9]+$/.exec(ticker);
  return match ? match[1] : null;
}

/**
 * The header line of a game: `San Diego @ Houston · MLB · Tue 5:01 PM`.
 * Each part is present only when the listing could say it; with no title the
 * result's `title` is `null` and the caller falls back to the ticker, never
 * a guess.
 */
export function gameHeaderParts(
  title: string | null,
  league: string | null,
  kickoff: string | null,
): { title: string | null; rest: string[] } {
  const rest = [league, kickoff].filter(
    (part): part is string => part !== null && part !== "",
  );
  return { title: title && title !== "" ? title : null, rest };
}
