/**
 * A readable label for a Kalshi ticker, truncating the series and never the
 * tail.
 *
 * `/bets` rendered `KXMVECROSSCATEGORY-SHARD1-S20266AE347C36E7-E497F938E16`
 * as a `truncate` heading — and CSS truncation cuts the RIGHT end, which is
 * the only identifying part, so every combo row rendered identically
 * (2026-08-22 review, A5). This is the pure inverse: keep the tail, elide
 * the middle, and never touch a ticker short enough to read whole.
 *
 * Display only. The full ticker stays in the DOM (`title=` at the call
 * sites) and in every payload; nothing parses this label back.
 */

/** Longest ticker rendered untouched. Chosen to clear every game ticker in
 * the record (`KXMLBGAME-26AUG221805STLPHI-PHI` is 31 chars) so only the
 * combo shards elide. */
const MAX_WHOLE = 34;

/** How much tail always survives — the segment that identifies the row. */
const TAIL = 16;

export function tickerLabel(ticker: string): string {
  if (ticker.length <= MAX_WHOLE) return ticker;
  const head = ticker.slice(0, MAX_WHOLE - TAIL - 1);
  const tail = ticker.slice(-TAIL);
  return `${head}…${tail}`;
}
