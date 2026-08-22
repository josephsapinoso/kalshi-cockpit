/**
 * The deep link to a market on kalshi.com — the escape hatch the app never
 * had (2026-08-22 review, A7: the market screen literally rendered "The
 * live book is on Kalshi" with nothing to tap).
 *
 * The scheme was VERIFIED in a browser on 2026-08-22, not guessed: opening
 * an MLB game landed on
 *
 *   https://kalshi.com/markets/kxmlbgame/professional-baseball-game/kxmlbgame-26aug221610wshmia
 *
 * i.e. /markets/{series}/{slug}/{event}, all lower-case — and the middle
 * slug is ARBITRARY: navigating with a wrong slug canonicalises to the real
 * one. So the cockpit builds {series}/game/{event} from the ticker alone.
 *
 * Game tickers are SERIES-EVENT-SIDE (`KXMLBGAME-26AUG221610WSHMIA-MIA`),
 * so exactly three segments deep-link to the event page. Anything else —
 * KXMVE combo shards, tickers with no hyphen — falls back to the markets
 * index rather than guessing a URL that lands somewhere wrong; a fallback
 * that admits it is one beats a deep link that lies.
 */

export function kalshiMarketUrl(ticker: string): string {
  const segments = ticker.split("-");
  if (segments.length === 3) {
    const series = segments[0].toLowerCase();
    const event = `${segments[0]}-${segments[1]}`.toLowerCase();
    return `https://kalshi.com/markets/${series}/game/${event}`;
  }
  return "https://kalshi.com/markets";
}
