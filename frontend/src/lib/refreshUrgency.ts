/**
 * When does the refresh panel deserve the top of the landing screen?
 *
 * The 2026-08-22 review measured the first game row at ~1,700px from the top
 * — below the fold at 390 AND 1440 — with the refresh apparatus and the
 * signal strip above it accounting for most of that. The ruling: games above
 * the fold; the panel earns the top slot only when it can actually fix
 * something the reader is about to misread. That is exactly one situation —
 * rows whose consensus is past the odds staleness limit (or a slate that is
 * not current at all), because a slate greyed out by the clock is unreadable
 * until the refresh is used. A fresh slate puts the panel below the rows.
 *
 * Pure function, node-tested (`tests/test_refresh_urgency.py` runs it the
 * way `test_suppression_gloss.py` runs the gloss), because a substring
 * assertion cannot tell this from its inversion.
 *
 * What this does not establish: nothing about whether a refresh is
 * affordable (the panel itself renders the budget) and nothing about quote
 * staleness — the Kalshi quote refreshes on its own clock and no tap here
 * changes it.
 */

/** The two facts the decision reads off each row, already on the wire. */
export type RefreshUrgencyRow = {
  odds_age_now_ms?: number | null;
  suppressed_reason: string | null;
};

/**
 * True when the panel belongs ABOVE the rows: some row's consensus is past
 * the staleness limit, or the slate itself is not current. `null`/absent
 * ages make no claim — a missing clock is not a stale clock — but a row the
 * engine already refused as `stale_odds` counts even if the age is missing,
 * because the refusal is itself the evidence.
 */
export function refreshIsUrgent(
  rows: RefreshUrgencyRow[],
  maxOddsAgeMs: number,
  slateIsCurrent: boolean,
): boolean {
  if (!slateIsCurrent) return true;
  return rows.some(
    (row) =>
      (typeof row.odds_age_now_ms === "number" &&
        row.odds_age_now_ms > maxOddsAgeMs) ||
      row.suppressed_reason === "stale_odds",
  );
}
