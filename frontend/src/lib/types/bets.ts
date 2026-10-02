/**
 * Wire types for the settled-bets record.
 *
 * Types only (#262, ADR 0191 sec 2.5): `import type` and nothing at runtime, and
 * never an import from `api.ts`. `api.ts` re-exports every name here.
 */

import type { OpenPositionsBlock } from "./slate";

/**
 * Joe's own settled bets (`/bets`): the venue's settlement mirror read back
 * to its owner. `net_tenths`/`net_display` are null on a row that cannot
 * carry the registered formula (a void, an unreadable price or fee) -- a
 * refusal, never $0.00 -- and `totals` covers the WHOLE table while `bets`
 * is a window, with `uncomputable` counting what the sum excludes.
 */
/**
 * Which kind of bet a settled position was, by ticker (21A). `combo` is the
 * venue's multi-leg market (`KXMVE*`); everything else is `single`. Decided
 * server-side by the one prefix check the repo has
 * (`estimates.classify_ticker`) -- the page groups by this and never
 * re-derives it from the ticker string.
 */
export type BetKind = "single" | "combo";

/**
 * #287: expected wins at the prices paid, what happened, and a range. All
 * computed by the server from entry prices; the page renders these and never
 * re-derives one. `too_few` means expected wins or expected losses is under
 * 5, and the range is then null.
 */
export type ExpectedBlock = {
  n: number;
  won: number;
  expected: number;
  too_few: boolean;
  range_low: number | null;
  range_high: number | null;
};

export type BetsKindSummary = {
  wins: number;
  losses: number;
  computable: number;
  /** The single-game floor (30); null for combinations. */
  floor: number | null;
  /** True below the floor: counts only, `expected` is null. */
  counts_only: boolean;
  excluded_from_expected: number;
  expected:
    | (ExpectedBlock & { buckets: (ExpectedBlock & { label: string })[] })
    | null;
};

export type SettledBet = {
  ticker: string;
  event_ticker: string | null;
  kind: BetKind;
  side: "yes" | "no";
  contracts: number;
  entry_price_tenths: number | null;
  entry_price_display: string;
  fee_cost_tenths: number | null;
  market_result: string | null;
  won: boolean | null;
  net_tenths: number | null;
  net_display: string | null;
  settled_ms: number;
  position_first_seen_ms: number | null;
  is_taker: number | null;
  n_fills_in_position: number | null;
  // Per-bet closing-line value, read on request against Kalshi's own close
  // (2026-08-22). `clv_refusal_reason` is set only when `clv_tenths` is
  // null: "no_closing_line" (most hand bets -- no discovery row, no matcher
  // link, or the game hasn't been scored yet), "unreadable_close",
  // "entry_time_unknown", or "entry_after_close" -- or "combo_unscorable"
  // on a combination bet, which has no close to be read (combos are excluded
  // from discovery) and renders NO CLV words at all rather than "close not
  // read yet". No average or hit rate is computed anywhere -- per-bet only,
  // until n >= 30.
  clv_tenths: number | null;
  clv_display: string | null;
  clv_refusal_reason: string | null;
  close_mid_tenths: number | null;
  close_display: string | null;
  // #161: the desk's own consensus chance for a combo at the moment Joe
  // priced it -- `parlay_lookups.fair_joint_conservative` from the latest
  // `status = 'priced'` lookup requested at or before the position's first
  // fill. A per-row FACT (ADR 0071), never a score or a verdict; there is
  // no aggregate of it anywhere in this repo and there must never be one.
  // A single carries all three keys as `null`, same as a combo with no
  // qualifying lookup -- `chance_refusal_reason` says which refusal:
  // `no_fill_row` (no `fills` row for the ticker) or `not_priced_on_desk`
  // (no priced lookup at or before the fill, including a single always-null
  // row, which the page renders as neither reason -- see `BetRow`).
  chance_when_priced: number | null;
  chance_priced_before_fill_ms: number | null;
  chance_refusal_reason: "no_fill_row" | "not_priced_on_desk" | null;
  // #168: true when the outside-parlay check (#166, `parlay_lookups
  // .card_key = 'outside'`) looked at this parlay at or before the fill and
  // could not produce a whole-parlay chance (a leg with no desk reading, or
  // two legs on one game) -- AND no reading with a real chance exists. A
  // reading with a chance always wins, so this is only ever `true` beside
  // `chance_when_priced === null` and `chance_refusal_reason ===
  // "not_priced_on_desk"`. It carries no chance itself and is never counted
  // toward `chance_carried`. A single always carries `false`, never `null`
  // -- it is a plain fact ("was this ticker checked and refused a joint"),
  // not one of the three chance fields above.
  checked_without_chance: boolean;
  // #254: a combination's legs in words, in leg order, from the recorded
  // position or the lookup that minted it. `null` when ANY leg is unreadable
  // (never a partial list) and always `null` on a single -- the row then says
  // "Combination bet". Optional: a backend one version behind omits the key.
  legs?: { label: string; side: "yes" | "no" }[] | null;
  // #254: Kalshi's own title for a single's market, from discovery; `null`
  // when discovery holds none, and always `null` on a combination.
  market_title?: string | null;
};

/**
 * One kind's share of the whole record (21A): its count and its net SUM,
 * over the WHOLE table like `totals`. A sum beside the pooled sum is the
 * per-group view the measurement rules ask for; a per-kind rate would be the
 * banned aggregate and is not served.
 */
export type BetsSection = {
  total: number;
  net_tenths: number;
  net_display: string;
  computable: number;
  uncomputable: number;
  // #161: a whole-table COUNT of rows in this kind whose
  // `chance_when_priced` is not null -- never a sum or an average of the
  // values it counts. Present on both kinds for a uniform shape; only the
  // combo section is ever non-zero, since a single carries no chance.
  chance_carried: number;
};

export type BetsRecord = {
  bets: SettledBet[];
  total: number;
  returned: number;
  /** `MIN(settled_ms)` over the mirror, or null when it is empty. The
   *  record states its own first day from this and from nothing typed into
   *  the page. */
  first_settled_ms: number | null;
  /** Single games and combination bets, each with its own count and sum.
   *  `single.total + combo.total === total`. */
  sections: Record<BetKind, BetsSection>;
  /** #287: wins and losses per kind, never pooled, and the expected line. */
  summary?: Record<BetKind, BetsKindSummary>;
  totals: {
    net_tenths: number;
    net_display: string;
    computable: number;
    uncomputable: number;
    wins: number;
    losses: number;
  };
  /** What is at risk right now, beside the settled record. Optional because
   *  a deployed backend one version behind omits the key. */
  open_positions?: OpenPositionsBlock;
  /**
   * "CLV scored on N of {denominator}" — counts only, over the WHOLE table
   * like `totals`, and since 21A over the SINGLE-GAME rows only: a combo has
   * no close to be scored against, so `population` names the cut and
   * `denominator` is the singles count. `refusals` counts the unscored
   * singles by reason so unmeasured never renders identically to bad. No
   * CLV *value* is ever combined (the no-aggregate constraint stands until
   * n >= 30).
   */
  clv_coverage?: {
    population: BetKind;
    denominator: number;
    scored: number;
    refusals: Record<string, number>;
  };
  /** When the "not tonight" lockout releases, or null. Same source as the
   *  slate's tonight block — one table, one clock, two screens. */
  lockout_until_ms?: number | null;
  /**
   * The pass record's headline numbers (slice B6): how many deliberate
   * "no"s, and since when. A floor, not a census — only taps are recorded.
   * Passes are never scored, never rated; this is a count and nothing may
   * grade it. `first_ms` null means none recorded yet, rendered as words.
   */
  passes?: {
    total: number;
    first_ms: number | null;
  };
};
