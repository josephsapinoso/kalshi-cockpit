/**
 * Wire types for the single-order and manual-order paths.
 *
 * Types only (#262, ADR 0191 sec 2.5): `import type` and nothing at runtime, and
 * never an import from `api.ts`. `api.ts` re-exports every name here.
 */

import type { WriteResult } from "../transport";
import type { GateCondition } from "./signal";

/** The 423 body. `conditions` is the gate's own list, not a re-derivation. */
export type LockedDetail = {
  message?: string;
  reason?: string;
  conditions?: GateCondition[];
};

export type ManualMarketSide = {
  ask_tenths: number | null;
  ask_display: string | null;
  depth_at_ask: number | null;
  /**
   * The venue's charge on ONE contract at this side's ask, in integer
   * tenths, rounded up (ticket #39). The ticket multiplies it by the typed
   * count and formats; it never prices a fee itself -- the fee curve is the
   * server's (`serialise.py`, beside `total_cost_dollars`), and a copy here
   * would be two money calculations one refresh apart. `null` when there is
   * no ask or the fee is unreadable, never `0`.
   */
  fee_per_contract_tenths: number | null;
  /**
   * The venue's charge on one contract at 50c -- the peak of the fee
   * curve, so a bound on the fee at any price. The ticket prices the
   * button off it when the max price is raised above the ask, because
   * the receipt prices the worst case at the sent limit. `null` with
   * the fee.
   */
  fee_ceiling_per_contract_tenths: number | null;
  /**
   * How often a bet at this ask has to win to come out even, fee included,
   * as a fraction. Served, not divided out here, so 50c reads 51.75% and not
   * the rounded tenth's 51.8%. `null` with the fee.
   */
  breakeven_probability: number | null;
  authorised_contracts: number | null;
  /**
   * WHICH bound produced `authorised_contracts`, so the ticket can name it.
   *
   * No ceiling of the desk's own is in that number since 2026-09-08 (ADR 0112
   * Amendment 1) -- it is the structural ceiling, the depth resting at the ask
   * and what the market's exchange shard can pay for, which are the three
   * bounds `POST /api/manual-orders` applies to size.
   *
   * The distinction is not decoration: waiting for the book to thicken and
   * moving money between Kalshi shards are different remedies, and a screen
   * that does not say which one it hit sends the reader to fix the wrong
   * thing.
   */
  authorised_binding:
    | "structural"
    | "depth"
    | "shard"
    | "price_grid"
    | "shard_unreadable"
    | "no_ask"
    | "no_price_grid";
};

export type ManualMarket = {
  ticker: string;
  /** When the server read the book. The ticket ages it on a tick and offers
   *  a re-read (ticket #40); nothing on the ticket is gated on it. */
  observed_ms: number;
  reachable: boolean;
  unreachable_reason: string | null;
  /**
   * The sportsbook's kickoff for this market, or `null` when the ticker is
   * unlinked, unrecorded or a combination (ticket #42). `null` renders
   * nothing -- never "not started", which an unknown does not establish.
   */
  commence_ms: number | null;
  sides: { yes: ManualMarketSide; no: ManualMarketSide };
  /**
   * The exchange shard this market settles on, and what that shard holds.
   *
   * Kalshi keeps collateral per shard and will not move it to pay for an
   * order, so the account total is the wrong number and a bet can be
   * unpayable while the account is funded. `authorised_binding: "shard"`
   * says that bound bit; these are the figures that make it actionable.
   *
   * Every field is `null` when the shard could not be read. An unreadable
   * balance is not a zero one -- `0` is a real balance, and rendering it
   * would tell Joe his money is gone.
   */
  shard: {
    index: number | null;
    available_tenths: number | null;
    available_display: string | null;
  };
  price_grid: string | null;
  caps: {
    derived: boolean;
    max_position_dollars: number | null;
    max_exposure_dollars: number | null;
  };
  cooloff_until_ms: number | null;
  lockout_until_ms: number | null;
  dry_run: boolean;
  /** The path's own size ceiling, served rather than hardcoded here — a
   *  second definition of a constant that exists to be raised deliberately
   *  would be a constant kept in sync by memory (ADR 0063). */
  max_contracts: number;
  /** A `KXMVE` combination market (ADR 0073). */
  is_combo: boolean;
  /** The sentence a combo order must carry, in the server's own words. */
  combo_note: string | null;
};

export type ManualOrderPlaced = {
  status: string;
  dry_run: boolean;
  manual_order_id: number;
  client_order_id: string;
  ticker: string;
  side: string;
  contracts: number;
  limit_price_display: string;
  max_price_display: string;
  worst_case_cost_display: string;
  kalshi_order_id: string | null;
  error_text: string | null;
  cooloff_until_ms: number;
  note: string;
  replayed: boolean;
};

export type ManualOrderResult = WriteResult<ManualOrderPlaced>;
