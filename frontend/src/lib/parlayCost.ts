/**
 * The buy-sheet cost line (#328): one sentence that restates the price in
 * plain words, at the moment of buying.
 *
 *   "{n} legs. Wins about 1 in {round(1000 / price_tenths)}. Fee is
 *    {k * (1 - P)}% of stake. The same picks as singles: {sum k p(1-p) /
 *    sum p}%."
 *
 * **The price restated, nothing more.** `P` is the price on screen (the best
 * maker quote, or the book's ask) and `1 in N` is just `1000 / price_tenths`:
 * a 12c card is 1 in 8 if the makers are right. It says nothing about any
 * factor predicting anything, calls no price cheap or good, and ranks
 * nothing (ADR 0071, ADR 0189 section 5).
 *
 * **`k`, the fee coefficient, is never a literal here.** It is the served
 * `fee_coefficient` (#334) when the payload carries one, else it comes from a
 * served quote: the fee and contract cost the Take-it button already shows,
 * so `k = fee / (contract cost * (1 - P))`. With neither there is no `k`,
 * and the fee and singles clauses are absent rather than guessed.
 * The singles clause uses the SAME `k` as the card (ADR 0058 reserves the
 * measured baseball figure for record-writing code).
 * **On a card with a baseball leg the singles clause is withheld** (Joe,
 * #339, 2026-10-09): nine baseball singles fills were charged about half the
 * applied rate (k ~ 0.035), so the shared `k` would overstate the singles' fee
 * about 2x and flatter the parlay. It shows nothing until the split is explained.
 *
 * Money is integer tenths of a cent throughout; a missing figure is `null`
 * and a clause that needs it is left out.
 */

import { createContext } from "react";

/** What the card around an ask knows about its legs. Absent outside a card. */
export type ParlayLegsInfo = {
  legCount: number;
  /** Each leg's Kalshi ask in tenths of a cent; `null` where unreadable. */
  legAsksTenths: (number | null)[] | null;
  /** The served `fee_coefficient` (#334), where the payload carried one. */
  feeCoefficient?: number | null;
};

export const ParlayLegsContext = createContext<ParlayLegsInfo | null>(null);

/** "34.2c" -> 342. Only the desk's own ask renderer's shape; else `null`. */
export function tenthsFromDisplay(display: string | null): number | null {
  if (display === null) return null;
  const match = /^(\d+(?:\.\d+)?)c$/.exec(display.trim());
  if (match === null) return null;
  const tenths = Math.round(Number(match[1]) * 10);
  return tenths > 0 && tenths < 1000 ? tenths : null;
}

/** Kalshi's baseball series all start KXMLB (KXMLBGAME, KXMLBTOTAL, ...). */
const BASEBALL_SERIES_PREFIX = "KXMLB";

/**
 * The leg asks the singles clause may use: `null` (clause withheld) when any
 * leg is baseball (#339), else each leg's ask, `null` where unreadable.
 */
export function singlesLegAsks(
  legs: { ticker: string; ask_display: string | null }[],
): (number | null)[] | null {
  if (
    legs.some((leg) =>
      leg.ticker.toUpperCase().startsWith(BASEBALL_SERIES_PREFIX),
    )
  ) {
    return null;
  }
  return legs.map((leg) => tenthsFromDisplay(leg.ask_display));
}

/** Wins about 1 in N: the price restated. `null` on an unreadable price. */
export function oneIn(priceTenths: number | null): number | null {
  if (priceTenths === null || !(priceTenths > 0) || priceTenths >= 1000) {
    return null;
  }
  return Math.round(1000 / priceTenths);
}

/**
 * The coefficient implied by one served quote: its fee over its contract
 * cost, divided back by (1 - P). `null` when either figure is unreadable.
 */
export function coefficientFromQuote(
  feeTenths: number | null,
  allInTenths: number | null,
  priceTenths: number,
): number | null {
  if (feeTenths === null || allInTenths === null) return null;
  const contractsCost = allInTenths - feeTenths;
  if (!(contractsCost > 0) || !(priceTenths > 0) || priceTenths >= 1000) {
    return null;
  }
  return feeTenths / (contractsCost * (1 - priceTenths / 1000));
}

/** Fee as a percent of stake: k * (1 - P), charged once at the card's price. */
export function feeSharePercent(
  k: number | null,
  priceTenths: number | null,
): number | null {
  if (k === null || priceTenths === null) return null;
  if (!(priceTenths > 0) || priceTenths >= 1000) return null;
  return k * (1 - priceTenths / 1000) * 100;
}

/**
 * The same picks bought as singles: sum k p (1 - p) over sum p, as a
 * percent. `null` if any leg's ask is unreadable (a partial sum would
 * understate the stake) or `k` is unknown.
 */
export function singlesFeeSharePercent(
  k: number | null,
  legAsksTenths: (number | null)[] | null,
): number | null {
  if (k === null || legAsksTenths === null || legAsksTenths.length === 0) {
    return null;
  }
  let fee = 0;
  let stake = 0;
  for (const tenths of legAsksTenths) {
    if (tenths === null || !(tenths > 0) || tenths >= 1000) return null;
    const p = tenths / 1000;
    fee += k * p * (1 - p);
    stake += p;
  }
  return (fee / stake) * 100;
}

/**
 * The coefficient to use: the SERVED one (`fee_coefficient`, the constant the
 * Take-it button's all-in cost charges, #334) when it is a usable number,
 * else the one a quote implies, else `null` (the fee clauses are left out).
 */
export function resolveCoefficient(
  served: number | null | undefined,
  fromQuote: number | null,
): number | null {
  if (typeof served === "number" && Number.isFinite(served) && served > 0) {
    return served;
  }
  return fromQuote;
}

export type CostLine = {
  legs: number | null;
  oneIn: number;
  feePercent: string | null;
  singlesPercent: string | null;
};

const onePlace = (percent: number) => percent.toFixed(1);

/** The line's parts, or `null` when the price is null (no line at all). */
export function costLine(input: {
  legCount: number | null;
  priceTenths: number | null;
  coefficient: number | null;
  legAsksTenths: (number | null)[] | null;
}): CostLine | null {
  const n = oneIn(input.priceTenths);
  if (n === null) return null;
  const fee = feeSharePercent(input.coefficient, input.priceTenths);
  const singles = singlesFeeSharePercent(
    input.coefficient,
    input.legAsksTenths,
  );
  return {
    legs: input.legCount,
    oneIn: n,
    feePercent: fee === null ? null : onePlace(fee),
    singlesPercent: singles === null ? null : onePlace(singles),
  };
}
