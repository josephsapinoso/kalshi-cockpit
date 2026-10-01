/**
 * Wire types for market detail, line shop, charts and estimates.
 *
 * Types only (#262, ADR 0191 sec 2.5): `import type` and nothing at runtime, and
 * never an import from `api.ts`. `api.ts` re-exports every name here.
 */

import type { Gauntlet } from "./scout";
import type { TrustScore } from "./signal";
import type { TonightActivity } from "./slate";

/**
 * Where Kalshi's ask sits among the books' own devigged fair values.
 *
 * **Every field can be `null`, and `null` never means zero.** A fixture with no
 * stored book prices and a fixture where every book was unusable are different
 * states, and `percentile: 0` would read as "Kalshi is the cheapest venue
 * here" — the flattering misreading of a measurement that never ran.
 *
 * **The comparison is deliberately unfair to Kalshi.** `kalshi_probability`
 * comes from the *ask*, so it carries half a spread; the book numbers are
 * devigged fair values with the vig removed. A book therefore looks cheaper
 * than Kalshi by roughly half a spread even where the two agree exactly, so
 * `books_below` over-counts. That direction is chosen: the reading this
 * supports is "Kalshi may be the sharp side", and a bias making Kalshi look
 * worse cannot manufacture it.
 */
export type BookDistribution = {
  kalshi_probability: number;
  /** Usable books, i.e. the size of the distribution — not `fair_prices`. */
  book_count: number;
  books_below: number;
  /** Dropped before or during the devig. A distribution over 2 of 21 books
   *  is a different object from one over 21, so this is never folded away. */
  books_unusable: number;
  median_book_probability: number | null;
  min_book_probability: number | null;
  max_book_probability: number | null;
  /** Fraction of usable books priced below Kalshi's ask. `null` if none were. */
  percentile: number | null;
};

export type LineShopLeg = {
  ticker: string;
  side: "yes" | "no";
  team: string | null;
  ask_tenths: number;
  ask_display: string;
  depth: number;
  all_in_tenths_per_contract: number;
};

export type LineShopData = {
  cheaper: LineShopLeg;
  current: LineShopLeg;
  saving_tenths_per_contract: number;
  fee_reference_contracts: number;
  read_ms: number;
  copy: string;
};

/**
 * The calibration bet log (registration 2026-08-17, as amended).
 *
 * Deliberately price-free types. The backend captures the market's book at
 * estimate time for the anchoring tripwires and never serialises it into any
 * payload below -- a quote key appearing here would mean the embargo broke.
 */
export type EstimateMarket = {
  ticker: string;
  title: string | null;
  player_name: string | null;
  event_ticker: string | null;
  event_title: string | null;
  close_ms: number | null;
};

export type RecentEstimate = {
  id: number;
  ticker: string;
  /** P(YES) in basis points: 6250 renders as 62.50%. */
  stated_probability_bp: number;
  estimate_server_ms: number;
  had_already_opened_kalshi: number | null;
  stated_probability_is_revised: number;
};

/**
 * The money arm's position: realised loss since the study opened, against
 * the $100 stop. Summed over the venue's own settlement record — never the
 * estimate log — which is why showing it breaks no embargo (A7). Nulls mean
 * "cannot read the record right now", which is a state, not a zero.
 */
export type StudyStop = {
  /**
   * The registration's terminal state (Amendment 2, 2026-08-20):
   * "stopped_without_result" — Joe stopped the study; nothing was scored.
   * Distinct from `stopped`, the $100 money arm, which never fired.
   */
  study_state: string;
  /** When the owner stopped the study, epoch ms. */
  stopped_by_owner_ms: number;
  loss_dollars: number | null;
  ceiling_dollars: number;
  stopped: boolean | null;
  /** When the self-lockout releases (next 10:00Z), or null if none is live. */
  lockout_until_ms: number | null;
};

/** What `POST /log-estimate` answers with. Quote-free by construction. */
export type EstimateLogged = {
  id: number;
  ticker: string;
  stated_probability_bp: number;
  estimate_server_ms: number;
};

/** One drawable bar of a market's price history. Prices in tenths of a cent;
 *  every field independently nullable — a candle in which nothing traded is a
 *  gap on the chart, never a bar invented at zero. */
export type ChartCandle = {
  t_ms: number;
  open_tenths: number | null;
  high_tenths: number | null;
  low_tenths: number | null;
  close_tenths: number | null;
  yes_bid_close_tenths: number | null;
  yes_ask_close_tenths: number | null;
  volume: number | null;
};

export type MarketCandles = {
  ticker: string;
  title: string | null;
  range: "1d" | "1w" | "1m" | "all";
  period_minutes: number;
  candles: ChartCandle[];
  dropped_unreadable: number;
};

export type MarketDetail = {
  /**
   * The books' raw implied probabilities SUMMED, before devigging.
   *
   * A market quoted with no margin sums to 1.0; anything above is the
   * bookmaker's cut, and that excess is exactly what the four devig methods
   * remove. `null` when unrecorded — never 1.0, which would assert a
   * margin-free book.
   */
  overround?: number | null;
  ticker: string;
  event_title: string | null;
  team: string | null;
  home_team: string | null;
  away_team: string | null;
  league: string | null;
  commence_ms: number | null;
  close_ms: number | null;
  market_status: string | null;
  ask_display: string;
  ask_dollars: number;
  quote_age_now_ms?: number | null;
  price_is_current?: boolean;
  volume_24h: number | null;
  open_interest: number | null;
  // The desk's consensus facts (ADR 0068). All optional: a deployed backend
  // one version behind omits them and the panels render honest absences.
  // **`breakeven_win_rate` is deliberately NOT here**: fair% and break-even
  // never share a screen block — their difference IS the measured-negative
  // edge (the fleet-convening identity).
  side?: string;
  /**
   * The team this row's own side pays on (`fair_prices.outcome_name`), so
   * the header can say which side the served row prices. Optional for a
   * backend one version behind; `null` when the row has no fair price.
   */
  side_outcome?: string | null;
  fair_probability?: number | null;
  fair_percent_display?: string | null;
  suppressed_reason?: string | null;
  reason_text?: string | null;
  anchored_on_sharp?: boolean | null;
  book_count?: number | null;
  books_used?: string[] | null;
  market_width?: number | null;
  p_multiplicative?: number | null;
  p_additive?: number | null;
  p_power?: number | null;
  p_shin?: number | null;
  p_conservative?: number | null;
  books?: BookDistribution | null;
  kalshi_drift_tenths?: number | null;
  drift_window_ms?: number;
  gauntlet?: Gauntlet;
  /**
   * The sweet spot for this market (ADR 0090), identical to the value the
   * slate row for the same ticker carries — both routes call one scorer, so
   * one tap cannot change the number. Optional for a backend one version
   * behind; `null` when the server had nothing honest to score.
   */
  trust?: TrustScore | null;
  /**
   * Tonight's commitment and the "not tonight" release -- the slate's own
   * block, served here too (#45) so the game screen, where the ticket is,
   * carries the control Games and Picks both have. One helper, one day
   * roll, one lockout table. Optional for a backend one version behind.
   */
  tonight?: TonightActivity | null;
};
