/**
 * The HUD's two spend gauges: how much of today's scout allowance and odds
 * credits are already used, read before Joe taps "ask the scouts about
 * every leg" and burns whatever is left in one pass (#172).
 *
 * Plain TypeScript, no React import, for the same reason as
 * `windowChip.ts` and `sweepTone.ts`: the real shipped function is executed
 * by `node` from a pytest (`tests/test_hud_gauges.py`) rather than
 * substring-read, because a test that reads the source cannot tell an
 * exactly-inverted predicate from a correct one.
 *
 * **A gauge never carries a threshold colour.** A full gauge is a state, not
 * an alarm — there is no verdict, edge or rank behind either number (ADR
 * 0071 §2.5) — so the only output here is a fraction (for `Segments`, cyan
 * at every level) and a label naming which cap it is. Red and amber belong
 * to callers that never exist for this feature.
 *
 * **Unreadable resolves to "no number", never to 0%.** `spend: null` (the
 * demo, no Anthropic account configured), a missing field, a non-finite
 * field, or a budget of zero or less are all the same fact from a caller's
 * point of view: there is nothing safe to divide. A gauge that rendered 0%
 * for "the fleet isn't configured" would read as "plenty of budget left",
 * which is the opposite of true. `fraction: null` is that state; every
 * renderer must show "—" and an unlit bar for it, never a lit one.
 */

/** A gauge: a fraction for the bar (or `null` if unreadable) and the label
 * that names what is being measured. */
export type Gauge = {
  fraction: number | null;
  label: string;
};

const UNREADABLE: Gauge = { fraction: null, label: "—" };

function isReadableNonNegative(n: unknown): n is number {
  return typeof n === "number" && Number.isFinite(n) && n >= 0;
}

function isReadableBudget(n: unknown): n is number {
  return typeof n === "number" && Number.isFinite(n) && n > 0;
}

function pct(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

/** Exactly the fields `scoutGauge` reads off `ScoutOverview.spend`
 * (`lib/api.ts`) — a subset on purpose, so a test states the whole world in
 * six numbers. Every field is typed loosely (`unknown`-shaped via optional
 * `number`) because the point of this function is validating a payload that
 * might not hold what its type says it does. */
export type ScoutSpendFacts = {
  calls_today?: number | null;
  calls_daily_budget?: number | null;
  searches_today?: number | null;
  searches_daily_budget?: number | null;
  tokens_today?: number | null;
  tokens_daily_budget?: number | null;
} | null;

type Cap = { name: string; used: unknown; budget: unknown };

/**
 * The scout gauge: whichever of the three metered caps (tokens, searches,
 * calls) is closest to being used up, per rule 1 of #172. The three bind
 * within ~15% of each other on the recorded day that motivated this ticket,
 * so a tokens-only gauge would read "plenty left" while searches were
 * nearly gone — the max, not any single cap, is the honest reading.
 */
export function scoutGauge(spend: ScoutSpendFacts): Gauge {
  if (!spend) return UNREADABLE;
  const caps: Cap[] = [
    { name: "tokens", used: spend.tokens_today, budget: spend.tokens_daily_budget },
    { name: "searches", used: spend.searches_today, budget: spend.searches_daily_budget },
    { name: "calls", used: spend.calls_today, budget: spend.calls_daily_budget },
  ];
  for (const cap of caps) {
    if (!isReadableNonNegative(cap.used) || !isReadableBudget(cap.budget)) {
      return UNREADABLE;
    }
  }
  let bestName = caps[0].name;
  let bestFraction = -Infinity;
  for (const cap of caps) {
    const fraction = (cap.used as number) / (cap.budget as number);
    if (fraction > bestFraction) {
      bestFraction = fraction;
      bestName = cap.name;
    }
  }
  return { fraction: bestFraction, label: `${bestName} ${pct(bestFraction)}` };
}

/** Exactly the fields `oddsGauge` reads off `ActionableWindow`
 * (`lib/api.ts`) — `spent_today` and `daily_budget` are the 700-credit-a-day
 * ceiling, never `attention_daily_credits` (the 300 slice, a different pool
 * per rule 2 of #172). */
export type OddsSpendFacts = {
  spent_today?: number | null;
  daily_budget?: number | null;
} | null;

/** The odds gauge: `spent_today / daily_budget`, the 700 cap that actually
 * stops the feed for the day — not the 300-credit attention slice, which is
 * a ceiling within the day, not the day's own. */
export function oddsGauge(window: OddsSpendFacts): Gauge {
  if (!window) return UNREADABLE;
  if (
    !isReadableNonNegative(window.spent_today) ||
    !isReadableBudget(window.daily_budget)
  ) {
    return UNREADABLE;
  }
  const fraction = (window.spent_today as number) / (window.daily_budget as number);
  return { fraction, label: `odds ${pct(fraction)}` };
}
