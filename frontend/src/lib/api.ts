/**
 * Backend types and fetchers.
 *
 * Prices arrive as integer tenths of a cent *and* as pre-rendered display
 * strings. The frontend uses the display string and never re-derives a price
 * from the float -- doing arithmetic on money in two places is how the two
 * places drift apart.
 */

/**
 * All four devig readings for the side bought, plus the one that was used.
 *
 * **Present only on `/api/ledger`**, which is the one route that joins
 * `fair_prices` through `recommendations.fair_price_id`. The Board and the
 * market detail select from `recommendations` alone and omit these keys
 * entirely rather than sending them as `null` — a `null` there would be
 * indistinguishable from a join that ran and found nothing.
 *
 * `fair_probability` is `p_conservative`: the **lowest** reading across
 * methods for the side being bought. That is a deliberate downward bias on
 * fair value, and a downward bias mechanically produces `edge <= 0` — so with
 * only that one column, no consumer can separate "Kalshi is sharp" from "we
 * chose a low fair". These four are what make that question answerable.
 *
 * Each is independently nullable: a devig method that could not be solved
 * resolves to `null`, never `0`, because `0` is a legitimate probability.
 */
export type DevigMethods = {
  p_multiplicative: number | null;
  p_additive: number | null;
  p_power: number | null;
  p_shin: number | null;
  /** Should equal `fair_probability` exactly. Sent so the join can be checked. */
  p_conservative: number | null;
};

/**
 * How much consensus produced the fair value, and whose.
 *
 * **Present only on `/api/ledger`**, on the same join and the same
 * present-or-absent rule as `DevigMethods`. The Board and the market detail
 * omit these keys entirely.
 *
 * These answer what the four devig readings cannot. `book_count` is how many
 * books survived sharp-book anchoring, so the standing worry that this tool
 * compares Kalshi only against references as sharp as Kalshi (ADR 0021 §7.2) is
 * checkable from the record instead of from a fixture captured on a different
 * day. `books_used` names *which* books — "three books agreed" means something
 * different when the three are two exchanges and Pinnacle.
 */
export type ConsensusProvenance = {
  /**
   * Disagreement between the best and worst surviving book, in probability
   * points.
   *
   * **`null` is a real state, not a gap.** One book cannot disagree with
   * itself, so there is no width to report — and `0` is simultaneously a
   * legitimate reading, two books quoting identically. Never coalesce the two.
   */
  market_width: number | null;
  /**
   * Books kept after sharp anchoring. `NOT NULL` in the database, so a `null`
   * here means the join missed — which is what disambiguates a `null`
   * `market_width` above.
   */
  book_count: number | null;
  /** Which books. `null` if the join missed or the column is unreadable, never `[]`. */
  books_used: string[] | null;
  /**
   * Whether sharp anchoring actually bound on this row.
   *
   * The anchoring is `selected = sharp or usable`, so `false` means **no sharp
   * book quoted** and the fair value came from the full book set — a wide
   * consensus wearing a sharp consensus's name. `book_count` cannot reveal
   * this: three sharp books and three soft ones both read `3`.
   *
   * `null` means the join missed. The column is `NOT NULL` in the database.
   */
  anchored_on_sharp: boolean | null;
};

export type Recommendation = Partial<DevigMethods> &
  Partial<ConsensusProvenance> & {
  id: number;
  ticker: string;
  created_ms: number;
  strategy_config_version: number;
  side: string;
  team: string | null;
  event_title: string | null;
  commence_ms: number | null;
  ask_tenths: number;
  ask_display: string;
  ask_dollars: number;
  fair_probability: number;
  /**
   * The fair value with a **cent** suffix. Do not render it.
   *
   * A fair value is a probability; `53.8c` sitting immediately left of a real
   * ask at the same type size is the one place a left-to-right scan reads the
   * wrong number as what you pay. Kept in the type because the payload still
   * carries it and a script may read it — `fair_percent_display` is the one
   * that goes on screen.
   *
   * @deprecated Render `fair_percent_display`.
   */
  fair_display: string;
  /** The same number as `53.8%`, off the same integer tenths. */
  fair_percent_display: string;
  edge_tenths: number;
  edge_cents: number;
  fee_predicted: number;
  ev_net_dollars: number;
  /** Ask times size. What the contracts cost, before the fee. */
  stake_dollars: number;
  /** Stake plus fee: what actually leaves the account, and the loss if wrong. */
  total_cost_dollars: number;
  /**
   * One standard deviation of this position's outcome, in dollars.
   *
   * `contracts * sqrt(p(1-p))` — a contract settles at $1 or $0, so its payoff
   * spread is exactly $1, and the fee is deterministic and adds no variance.
   * Zero on an unsized row, which is a real answer rather than a missing one.
   */
  sd_dollars: number;
  /** The run length `losing_run_probability` is computed for. */
  losing_run_bets: number;
  /**
   * How often that many bets of this shape end down, with the edge entirely
   * real. **`null` when there is no position** — there is no run to lose, and
   * a number there would be a claim nothing measured.
   */
  losing_run_probability: number | null;
  suggested_contracts: number;
  /**
   * The same decision sized at the **fixed reference bankroll**, which is what
   * the gate's `actionable` counter reads — not what you may buy. At the
   * deployed bankroll these differ, and a row can be counted as evidence while
   * `suggested_contracts` is zero. Do not render it as a size to buy.
   *
   * `null` only on a pre-schema-v6 row that escaped the backfill, which is a
   * different state from "no bet here".
   */
  reference_contracts: number | null;
  kelly_fraction: number;
  kalshi_quote_age_ms: number;
  odds_age_ms: number;
  depth_at_ask: number | null;
  suppressed_reason: string | null;
  reason_text: string;
  clv_tenths: number | null;
  /**
   * Which anchor `clv_tenths` was measured against. `null` when unscored.
   *
   * Never pool two values of this. The legacy `1` rows are scored against a
   * weaker benchmark than the current `0`, so mixing them flatters the result;
   * the gate counts only the primary horizon for exactly that reason.
   *
   * **`0` is a real horizon.** Nothing may test this for truthiness.
   */
  clv_horizon_hours: number | null;
  /**
   * The ages as they are *now*, sent only by the Board.
   *
   * `kalshi_quote_age_ms` and `odds_age_ms` above are the ages at the moment
   * the row was written and never move, which is right on the Ledger — there
   * they are a historical fact about the observation — and dangerously wrong
   * on the Board, where a row from three hours ago still reads "quote 3s ago".
   */
  quote_age_now_ms?: number | null;
  odds_age_now_ms?: number | null;
  /**
   * The server would still accept an order for this row, at this instant.
   *
   * That is the **odds** clock alone. The order endpoint re-reads the Kalshi
   * quote inside the request, so a recorded quote past its thirty-second limit
   * no longer stops an order — it only means the price below is not the price
   * you would pay. Nothing refreshes the sportsbook consensus but a credit, so
   * that is the limit which actually ends a row's life.
   */
  actionable?: boolean;
  /**
   * Whether the ask shown on the card is inside the Kalshi quote limit.
   *
   * `actionable && !price_is_current` is a real state and the most common one
   * mid-window: the bet is live, and the number on the card is a memory. The
   * card must say so rather than rendering a size and a cost as though they
   * were a quote.
   */
  price_is_current?: boolean;
  /**
   * Whether `quote_age_now_ms` is measured from a **re-derivation** rather than
   * from when the row was written.
   *
   * A quote pass re-reads Kalshi every fifteen seconds while the window is open
   * and stamps rows whose ask and fair value have not moved, instead of
   * recording a duplicate. So a live row's quote age is usually the age of the
   * last confirmation. "Quoted 3s ago" and "re-checked 3s ago" are different
   * claims and the card says which one it is showing.
   */
  freshness_confirmed?: boolean;
  freshness_measured_from_ms?: number | null;
};

export type Board = {
  /** Sized, and the server would still accept it. A claim about this instant. */
  surfaced: Recommendation[];
  /** Sized, and the consensus has aged out. Returned rather than dropped. */
  expired: Recommendation[];
  suppressed: Recommendation[];
  /**
   * The rest of the slate: candidates with no edge at all.
   *
   * Sent under the same flag as `suppressed`, and empty without it. Mispricing
   * is a factor, not a filter — with zero actionable across ~200 decisions the
   * rows that did not survive are the only content the Board has.
   */
  no_edge: Recommendation[];
  counts: {
    surfaced: number;
    expired: number;
    suppressed: number;
    no_edge: number;
    /** Of `surfaced`, how many show a price older than the quote limit. */
    price_stale?: number;
  };
  /** The limits the server judged against, so the page cannot state its own. */
  staleness: { max_kalshi_quote_age_s: number; max_odds_age_s: number };
  /**
   * **Which rows these are, and which rows they are not.**
   *
   * The Board used to select `ORDER BY suggested_contracts DESC, edge_tenths
   * DESC LIMIT 100` over the whole table with no clock in it — and with
   * `suggested_contracts` 0 on essentially every row ever written, that is the
   * hundred largest apparent edges in the history of the database, drawn as
   * today's slate with no date on any of them. Selection is now on the clock;
   * this block is what stops the four lists above being read as more than they
   * are.
   *
   * `anchor_ms === null` (nothing ever recorded) and `is_current === false` (a
   * slate, but not this hour's) are different states and must not render the
   * same way.
   */
  slate: {
    /** When this instance last decided anything. `null` if it never has. */
    anchor_ms: number | null;
    /** How old that is. The number that says slate or souvenir. */
    age_ms: number | null;
    since_ms: number | null;
    window_ms: number;
    is_current: boolean;
    /** The window before `limit`, and what survived it. */
    in_window: number;
    returned: number;
    /**
     * Rows inside the window by the stored timestamp and outside it by the age
     * that was actually measured, so counted in `in_window` and listed nowhere.
     *
     * Its own number rather than part of `truncated`, because `LIMIT` and the
     * server's second freshness reading drop rows for unrelated reasons. Until
     * this existed those rows set nothing and the page printed nothing.
     */
    off_basis: number;
    /** `in_window > returned`. Both kinds of drop, not just the `LIMIT`. */
    truncated: boolean;
    /** The record deliberately left off — what the old query ranked and showed. */
    recorded_total: number;
    /**
     * Rows in the **whole table** the strategy would have bet: the gate's own
     * `suppressed_reason IS NULL AND reference_contracts > 0`, not this slate's.
     *
     * The Board's counts are correctly windowed now, and that windowing took
     * away its one statement about the record — "Bettable now: 0" reads as a
     * quiet half-hour when the actual finding is zero across the life of the
     * database. Nothing else in this payload can reconstruct it.
     */
    actionable_total: number;
    older_than_window: number;
  };
  note: string;
};

export type GateCondition = { name: string; met: boolean; detail: string };
export type Gate = {
  open: boolean;
  conditions: GateCondition[];
  /** Every unmet condition, not just the first — the distance from open is the useful part. */
  reason: string;
  bankroll_dollars: number;
  /**
   * How many rows fell into each population over the **whole table**, at every
   * horizon — not the scored subset the conditions read.
   *
   * `counts.actionable` is the gate's binding quantity: a suppressed or
   * zero-sized row can never increment the 300-game floor however well the CLV
   * machinery works downstream. It is sized at the fixed reference bankroll,
   * so it does not move when the deposit does.
   */
  populations: {
    since_ms: number;
    counts: Record<string, number>;
    predicates: Record<string, string>;
    note: string;
  };
  note: string;
};

/**
 * What the order endpoint sends back when it accepts.
 *
 * **Every field is optional and unknown keys are preserved**, deliberately. The
 * response is being extended (an `order_id` for the persisted row, a
 * `resulting_exposure_dollars`), and a ticket that threw on a field it had not
 * been told about would break the one screen a person uses to bet, at the
 * moment the backend improves. So the sheet renders what it recognises, renders
 * anything else generically, and never assumes a key is there.
 *
 * The price appears as `limit_price_dollars` in the extended shape and as
 * `limit_price_cents` in the current one. Both are rendered in their own unit.
 * Converting between them here would be exactly the arithmetic this frontend is
 * not allowed to do -- see the module docstring on `LiveBoard`.
 */
export type OrderQuote = {
  recorded_ask_display?: string;
  live_ask_display?: string;
  moved_tenths?: number;
  age_ms?: number;
  depth_at_ask?: number | null;
  authorised_contracts?: number;
  resized_contracts?: number;
  binding_constraint?: string;
  note?: string;
  [key: string]: unknown;
};

export type OrderPlaced = {
  status?: string;
  dry_run?: boolean;
  client_order_id?: string;
  /** Present once the endpoint persists the row. Absent until then. */
  order_id?: number | string | null;
  ticker?: string;
  side?: string;
  book_side?: string;
  contracts?: number;
  limit_price_dollars?: number;
  limit_price_cents?: number;
  fill_price_tenths?: number;
  fill_price_display?: string;
  price_grid?: string;
  worst_case_cost_dollars?: number;
  /** Present once orders are written. Rendered when it is, omitted when not. */
  resulting_exposure_dollars?: number;
  quote?: OrderQuote;
  request_body?: Record<string, unknown>;
  note?: string;
  [key: string]: unknown;
};

/** The 423 body. `conditions` is the gate's own list, not a re-derivation. */
export type LockedDetail = {
  message?: string;
  reason?: string;
  conditions?: GateCondition[];
};

/**
 * `status: 0` means the request never reached the server.
 *
 * Given its own value rather than folded into 503, because they call for
 * different sentences: one says the exchange could not be read, the other says
 * this phone could not be heard. Telling a person on a train that Kalshi is
 * down when their signal dropped sends them looking in the wrong place.
 */
export type OrderResult =
  | { ok: true; status: number; value: OrderPlaced }
  | { ok: false; status: number; detail: unknown };

/**
 * Ask the server to place an order. The client sends a recommendation id and a
 * size and nothing else: the ticker, side and price are read server-side from
 * the recommendation, so a stale or tampered client cannot buy a different
 * market or a better price than the one on record. The size is a *proposal* --
 * the endpoint clamps it down against what the engine authorised, what the
 * sizer allows at the live price, and the order cap.
 *
 * 423 is the locked gate and carries the unmet conditions as a structured body.
 */
/**
 * A key identifying one *intent* to order, not one request.
 *
 * `crypto.randomUUID` needs a secure context, which every browser reaching the
 * live cockpit has (it is HTTPS-only) — but not every one reaching a `http://`
 * dev origin, where it is `undefined` and would throw. The fallback is not
 * cryptographic and does not need to be: this value is a database key, never a
 * secret, and it only has to be unlikely to repeat within one session.
 *
 * The charset is deliberately narrow. The server accepts `[A-Za-z0-9_-]{8,64}`
 * and echoes the key back in refusals, so anything wider would be a string
 * from the client rendered on a screen.
 */
export function newIntentKey(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return uuid.replace(/-/g, "");
  return `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

/**
 * `idempotencyKey` identifies the intent, so the same value must be sent by
 * every attempt at one order — a double-tap, or a retry after a lost response.
 * The server answers a repeat with the first attempt's outcome instead of
 * placing a second order. A fresh key per attempt protects nothing.
 */
export async function placeOrder(
  recommendationId: number,
  contracts: number,
  idempotencyKey: string,
  token?: string,
): Promise<OrderResult> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/api/orders`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: "no-store",
      body: JSON.stringify({
        recommendation_id: recommendationId,
        contracts,
        idempotency_key: idempotencyKey,
      }),
    });
  } catch (error) {
    // A thrown fetch is not a refusal and must not render as one. Nothing was
    // decided, so nothing can be reported about the order -- only about the
    // connection.
    return {
      ok: false,
      status: 0,
      detail: `The request did not reach the cockpit (${
        error instanceof Error ? error.message : "network error"
      }). Nothing was sent to the exchange.`,
    };
  }

  // A body that is not JSON is itself information -- a proxy error page, a
  // login redirect. Keep the status and say the body was unreadable rather
  // than swallowing it into an empty object that renders as a blank refusal.
  const body: unknown = await response.json().catch(() => null);
  if (response.ok) {
    return { ok: true, status: response.status, value: (body ?? {}) as OrderPlaced };
  }
  const detail =
    body && typeof body === "object" && "detail" in body
      ? (body as { detail: unknown }).detail
      : (body ??
        `HTTP ${response.status}, and the body was not readable as JSON.`);
  return { ok: false, status: response.status, detail };
}

/** Whether a refusal body is the gate's structured one rather than a string. */
export function isLockedDetail(detail: unknown): detail is LockedDetail {
  return (
    typeof detail === "object" &&
    detail !== null &&
    !Array.isArray(detail) &&
    ("conditions" in detail || "message" in detail)
  );
}

/**
 * A refusal body as text, whatever shape it arrived in.
 *
 * Three shapes reach here and all three are real: FastAPI's plain string, the
 * list of dicts pydantic produces when the request body itself is invalid, and
 * an object. The endpoint's plain-language strings are the useful output and
 * are passed through untouched -- there are a dozen distinct refusals and each
 * one explains itself better than a generic sentence could.
 */
export function refusalText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object") {
          const item = entry as { loc?: unknown[]; msg?: string };
          const field = Array.isArray(item.loc)
            ? item.loc.filter((p) => p !== "body").join(".")
            : "";
          return field && item.msg ? `${field}: ${item.msg}` : (item.msg ?? "");
        }
        return String(entry);
      })
      .filter(Boolean)
      .join("\n");
  }
  if (detail && typeof detail === "object") {
    const message = (detail as LockedDetail).message;
    if (typeof message === "string") return message;
    return JSON.stringify(detail);
  }
  return "The server refused and gave no reason, which is itself a defect.";
}

export type Ledger = {
  rows: Recommendation[];
  /** Independent games scored, which is what the gate counts. Not row count. */
  clv_scored: number;
  /** Raw recommendation rows behind those games, kept visible beside them. */
  clv_scored_rows: number;
  clv_required: number;
  gate_open: boolean;
  /** Rows in the whole table. Compare with `returned` to tell a slice from it. */
  total: number;
  /** How many rows `rows` actually holds. */
  returned: number;
  /** The `LIMIT` that was applied. */
  limit: number;
  /**
   * The `OFFSET` that was applied. Echoed because `total`, `returned` and
   * `limit` cannot tell "I fetched every page" from "I fetched page 0 twice".
   */
  offset: number;
  /**
   * The snapshot pin in force, or `null` for an unpinned read.
   *
   * A multi-page pull **must** pass `newest_id` back as `max_id`. The route
   * sorts newest-first, so a row written during the pull lands on page 0 and
   * shifts every later page — and on live one `created_ms` carries 84 rows,
   * so a single sweep landing mid-pull duplicates a quarter of the result and
   * drops rows that were there the whole time, with `returned` and `total`
   * still adding up.
   */
  max_id: number | null;
  /**
   * The newest `id` in the table, not in the page. Pass it back as `max_id`
   * to pin a snapshot. Under a pin, `newest_id > max_id` says rows arrived
   * during the pull and were correctly excluded.
   */
  newest_id: number | null;
  /**
   * The whole table counted by `clv_horizon_hours`, keyed as strings — `"0"`,
   * `"1"`, `"unscored"`. Over the table rather than the returned window,
   * because the legacy rows are the oldest and the window is newest-first.
   */
  horizons: Record<string, number>;
  /** The anchor the gate counts. Everything else is record, not evidence. */
  primary_horizon_hours: number;
};

/**
 * Where to reach the API, which differs by execution context.
 *
 * These pages are React Server Components, so `fetch` runs on the Node side
 * where there is no page origin -- a relative `/api/board` has nothing to
 * resolve against and throws. The `rewrites()` rule in next.config only
 * applies to requests the *browser* makes to Next, so it does not help here
 * either. Server-side therefore needs an absolute URL to the Python backend;
 * client-side keeps the relative path so the browser never sees a second
 * origin (and never needs CORS or a token in front-end code).
 */
const BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  (typeof window === "undefined"
    ? (process.env.API_ORIGIN ?? "http://127.0.0.1:8000")
    : "");

async function get<T>(path: string): Promise<T> {
  // `no-store`: this is live market data. A cached board showing a stale price
  // as fresh is precisely the failure the staleness contract exists to prevent.
  const response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

/** One dbt mart, plus the state it is in. */
export type Panel = {
  name: string;
  /**
   * `unavailable` is not `empty`. A mart missing from the warehouse is unknown;
   * a mart that built and produced no rows is a real, reportable result. The
   * dashboard renders them differently on purpose -- collapsing the two is how
   * an unbuilt warehouse comes to read as "nothing to worry about".
   */
  status: "ok" | "empty" | "unavailable";
  rows: Record<string, string | number | boolean | null>[];
  note: string | null;
};

export type Dashboards = {
  warehouse_built_ms: number;
  freshness_note: string;
  missing_required_marts: string[];
  panels: Record<string, Panel>;
  headlines: string[];
};

export type ParlayLeg = {
  label: string;
  probability: number;
  event_key: string;
  league: string;
  commence_ms: number;
};

export type ParlayValuation = {
  fair_probability: number;
  naive_probability: number;
  independence_error_points: number;
  fair_american: number;
  offered_american: number;
  hold: number;
  ev_per_dollar: number;
  is_positive_ev: boolean;
  correlation_was_supplied: boolean;
  verdict: string;
  kalshi_alternative: {
    total_cost_dollars: number;
    total_fee_dollars: number;
    fee_share_of_stake: number;
    expected_value_dollars: number;
    note: string;
  };
};

export const fetchDashboards = () => get<Dashboards>("/api/dashboards");

/**
 * Price a parlay. Same-game legs come back as a 422 carrying the refusal text,
 * which the Builder shows verbatim -- the explanation is the useful output.
 */
export async function priceParlay(
  legs: ParlayLeg[],
  offeredAmerican: number,
  overrides: { a: string; b: string; rho: number }[] = [],
): Promise<{ ok: true; value: ParlayValuation } | { ok: false; refusal: string }> {
  const response = await fetch(`${BASE}/api/builder/parlay`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({
      legs,
      offered_american: offeredAmerican,
      correlation_overrides: overrides,
    }),
  });
  if (response.ok) {
    return { ok: true, value: (await response.json()) as ParlayValuation };
  }
  const body = await response.json().catch(() => ({}));
  return { ok: false, refusal: String(body.detail ?? `HTTP ${response.status}`) };
}

/**
 * Whether a pick could be acted on right now, and when the next chance is.
 *
 * The odds budget affords two sweeps a day and each one makes the slate
 * bettable for fifteen minutes, so for roughly 23.5 hours out of 24 every row
 * on the Board is a row nobody can act on. Without this, an empty Board, a
 * Board of expired rows, and a Board during the window all look the same.
 *
 * `is_open` is a claim about *freshness only*. It never means there is
 * something to bet — most windows open onto an empty Board, which is the
 * expected result of the whole premise.
 */
/**
 * One planned odds sweep, exactly as `odds.timing.SweepSlot` serialises it.
 *
 * `fire_from_ms`/`fire_until_ms` bound when the sweep may fire;
 * `anchor_commence_ms` is the first kickoff of the cluster it is aimed at, and
 * the window is planned to close before it. `games_covered` is how many
 * fixtures that one sweep makes priceable — the reason the planner picks this
 * slot over another, since a sweep costs the same whether it covers one game or
 * thirteen.
 */
export type PlannedSlot = {
  sport_key: string;
  fire_from_ms: number;
  fire_until_ms: number;
  anchor_commence_ms: number;
  games_covered: number;
};

export type ActionableWindow = {
  now_ms: number;
  is_open: boolean;
  seconds_remaining: number | null;
  open_until_ms: number | null;
  /** Counted, not averaged: a slate can be half stale, and that is a real state. */
  fixtures_upcoming: number;
  fixtures_fresh: number;
  max_odds_age_s: number;
  last_sweep_ms: number | null;
  last_sweep_sport: string | null;
  /**
   * The last time a pass decided *anything* about odds, and what it decided.
   *
   * Not the same question as `last_sweep_ms`, which is the last sweep that was
   * **served**. Every full pass writes a row whatever it concludes, so:
   *
   *   fresh look, fresh sweep   the loop is running and spending
   *   fresh look, stale sweep   the loop is running and declining, every pass
   *   stale look, stale sweep   the loop is not running at all
   *
   * Those need opposite responses and were one observation until `odds_sweep_log`
   * existed. The middle row is the state that ran 17 hours unnoticed on
   * 2026-08-09/10, so the gap between the two is rendered rather than left for a
   * reader to subtract.
   *
   * `null` means this database has never recorded a pass looking, which after a
   * fresh deploy is the true state and is **not** the same as "it looked and
   * found nothing". The banner says so instead of drawing a calm dash.
   */
  last_look_ms: number | null;
  last_look_outcome: string | null;
  last_look_detail: string | null;
  /**
   * When the next `/odds` call is wanted — **not** when the next slot opens.
   *
   * Since the rolling refresh a slot buys odds every `refresh_interval_s` for
   * as long as it is due, so a slot mid-window has an opening time in the past.
   * Publishing that would put a stale time on the one readout a human uses to
   * decide when to look. The server computes this through the same predicate
   * the loop fires on, so the page cannot disagree with it.
   */
  next_sweep_ms: number | null;
  /** How often an open window re-buys its odds. Derived from `max_odds_age_s`. */
  refresh_interval_s: number;
  next_sweep_sport: string | null;
  next_sweep_games: number | null;
  next_sweep_reason: string | null;
  /**
   * Every sweep the planner intends for the rest of the budget day.
   *
   * `next_sweep_*` above is this list's first entry, flattened. The array has
   * been on the wire since `ActionableWindow.to_dict` was written and was
   * undeclared here until 2026-08-16, so the UI could show the next chance and
   * nothing beyond it — which is the wrong shape for the question a human
   * actually asks, which is "when should I open this today".
   *
   * Chronological. Bounded by `sweeps_remaining_today`, so it shortens as the
   * budget is spent and is **empty** both when the credits are gone and when no
   * fixture is near enough to schedule against. Those are different states and
   * the list alone cannot tell them apart; read `sweeps_remaining_today` beside
   * it.
   *
   * A slot is a permission to fire within `[fire_from_ms, fire_until_ms]`, not
   * a firing. Nothing here promises the sweep happens.
   */
  slots_planned: PlannedSlot[];
  sweeps_remaining_today: number;
  spent_today: number;
  daily_budget: number;
  budget_day_start_ms: number;
  /**
   * When this budget day's **first sweep window** opens. `null` means none does.
   *
   * It sits beside `budget_day_start_ms` because the two are different clocks
   * and comparing against the wrong one is what made the sweep banner fire every
   * morning. The boundary above is a *credits-accounting* time (10:00Z); a sweep
   * window is *kickoff-derived*, opening 75 minutes before the first pitch of a
   * cluster. Between the two there is no window in which to spend, so "nothing
   * has swept since the day opened" is arithmetic there, not an observation.
   * Measured on the live record it held on 6 of 6 budget days sampled, for
   * 6.5–10.8 hours each.
   *
   * Computed from `day_start_ms` rather than from now, so a window that opened
   * and **closed** earlier today still counts — that is the 17-hour incident
   * shape, and forgetting it is the one way this field could make the banner
   * calm over a real outage.
   *
   * `null` is "no window opens today", never "unknown", and it is not on its own
   * reassurance: a loop that is not running at all shows up as `last_look_ms`
   * going stale, which is a different field and a louder tone.
   */
  first_window_open_ms: number | null;
  note: string;
};

export const fetchWindow = () => get<ActionableWindow>("/api/window");

export const fetchBoard = (includeSuppressed = false) =>
  get<Board>(`/api/board?include_suppressed=${includeSuppressed}`);

export const fetchLedger = () => get<Ledger>("/api/ledger");

export const fetchGate = () => get<Gate>("/api/gate");

/**
 * What the product's own conclusion is worth, measured.
 *
 * `beta` is tenths of realised closing-line value per tenth of claimed edge --
 * the registered decision-bearing statistic of the whole project. Until ADR
 * 0039 it appeared **zero times in this directory**: the cockpit stated a
 * conclusion about whether the consensus signal works and stated its measured
 * worth nowhere, because the only way to produce the number was a laptop
 * running a script against an ssh dump.
 *
 * **The shape is deliberately hostile to reading the effect alone.** There is
 * no top-level `beta_hat`. It lives inside `estimate`, which is `null` unless a
 * fit actually happened, and which carries `se_cluster`, `n_clusters` and both
 * interval limits or none of them. A renderer physically cannot show the point
 * estimate on its own, which is the one-number habit the always-valid
 * multiplier exists to defeat.
 */
export type Signal = {
  /** When the backend computed this. It is cached; render the age. */
  computed_ms: number;
  cache_ttl_ms: number;
  /** `false` on the demo instance, whose seeded history has no quotes to join. */
  available: boolean;
  /** Why there is no estimate. Present exactly when `estimate` is null. */
  refusal: string | null;
  /**
   * The registered string, never a paraphrase. `UNRESOLVED` is a real answer
   * and **may not be rendered as "no signal"** -- the registration forbids
   * declaring below 300 clusters. `REFUSED` is different again: it means no
   * look happened at all.
   */
  verdict: "SIGNAL" | "BUG, NOT SIGNAL" | "NO SIGNAL" | "UNRESOLVED" | "REFUSED";
  /** Whether the cluster floor permits a declaring verdict at all. */
  may_declare: boolean;
  population: {
    rows: number;
    clusters: number;
    clusters_to_declare: number;
    clusters_remaining: number;
    p1: number;
    p1_floor: number;
    p1_passed: boolean;
    matched: number;
    quote_mismatch: number;
    no_quote: number;
    disclosure_required: boolean;
  };
  estimate: {
    /** Comes first because reading the effect first is how a small cell gets believed. */
    smallest_resolvable_beta: number;
    beta_hat: number;
    se_cluster: number;
    n_clusters: number;
    n_rows: number;
    interval_lower: number;
    interval_upper: number;
    multiplier: number;
  } | null;
  /**
   * Diagnostic only. The per-group view can downgrade a verdict and can never
   * create one, and `market_type` is not a registered cut -- it is here because
   * the repo rule requires the parts beside any aggregate, and this pooled
   * figure is not homogeneous.
   */
  by_market_type: {
    name: string;
    rows: number;
    share: number;
    clusters: number | null;
    beta_hat: number | null;
    refusal: string | null;
  }[];
  registration: string;
  note: string;
};

export const fetchSignal = () => get<Signal>("/api/signal");

/**
 * How often each suppression rule fired.
 *
 * The shape is the route's, read before it was typed: `{"counts": {reason: n}}`,
 * already sorted by count descending server-side, with a row failing several
 * checks counted once under each. So the values sum to more than the number of
 * rejected rows, and that is correct rather than a bug to normalise away.
 */
export type Suppression = { counts: Record<string, number> };

export const fetchSuppression = (sinceMs = 0) =>
  get<Suppression>(`/api/suppression?since_ms=${sinceMs}`);

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

/**
 * One row of the Slate: a recommendation plus the factors already on the record.
 *
 * **None of these factors has been scored against an outcome**, none of them
 * enters `suggested_contracts`, and the server combines them into nothing. The
 * screen must not present any of them as an edge or blend them into a rating —
 * that would be a model, and it would need its own ADR.
 */
export type SlateRowData = Recommendation & {
  /** 24h contract volume on the Kalshi market. Capacity, not price. */
  volume_24h: number | null;
  open_interest: number | null;
  /**
   * Change in the derived ask over `drift_window_ms`, in tenths. Positive means
   * the price you would pay has risen. `null` when fewer than two quotes exist
   * in the window — never 0, which would assert the price held steady.
   */
  kalshi_drift_tenths: number | null;
  books: BookDistribution | null;
};

export type Slate = {
  /** One flat list in kickoff order. No bucketing by verdict — that is the
   *  point: edge is a column here, not a gate. */
  rows: SlateRowData[];
  counts: {
    returned: number;
    /** Rows a book distribution could be computed for. Its own number because
     *  "no book disagreed" and "no book price stored" render identically. */
    with_book_distribution: number;
    surfaced: number;
  };
  staleness: { max_kalshi_quote_age_s: number; max_odds_age_s: number };
  slate: Board["slate"];
  drift_window_ms: number;
  note: string;
};

export const fetchSlate = () => get<Slate>("/api/slate");

export const fetchHealth = () =>
  get<{
    instance_mode: string;
    execution_available: boolean;
    /**
     * Whether `/api/stream/quotes` will do anything on this instance.
     *
     * The Board opens the stream only when this is true. A browser's
     * `EventSource` retries a failing endpoint on its own, forever and
     * silently, so pointing it at the demo — which holds no Kalshi credentials
     * — would be a permanent reconnect loop nobody could see.
     */
    live_quotes_available?: boolean;
  }>("/api/health");

/**
 * Whether a row failed a named suppression rule.
 *
 * **`suppressed_reason` is a comma-joined list, not one code.**
 * `SuppressionResult.reason` joins every failed check with `,`
 * (`backend/core/suppression.py`), and `engine.py` can write a
 * `sizing:{constraint}` code into the same column. So a row reads
 * `suspicious_edge,wide_market` as often as it reads one word, and an equality
 * test against the whole string silently misses every row that broke more than
 * one rule — which is the row most worth shouting about.
 */
export function hasSuppression(
  rec: Pick<Recommendation, "suppressed_reason">,
  code: string,
): boolean {
  if (!rec.suppressed_reason) return false;
  return rec.suppressed_reason.split(",").some((part) => part.trim() === code);
}

/**
 * What the edge number on a row *means*, which is not the sign of a subtraction.
 *
 * The Board rendered `+24.4c` in `text-positive` on `edge_cents > 0` alone,
 * with no reference to whether the row had been refused — so a row reading
 * `REJECTED … suspicious_edge` painted the largest apparent edge in the room in
 * the colour that means take this, and put the code identifying it as a defect
 * in small grey monospace beside it. On a phone at a glance that row was the
 * most attractive thing on the page.
 *
 * `CLAUDE.md` rule 1 is that **a large apparent edge is a bug until proven
 * otherwise**. Colour is a claim about whether a number is money, so the
 * suppression state is consulted *before* the sign and the sign is only ever
 * reached on a row nothing refused:
 *
 *   suspect   `suspicious_edge` fired. The code that means the data is broken,
 *             and the one whose rows sort to the top of any edge ranking. It
 *             gets the loudest treatment on the row, not the quietest.
 *   refused   some other rule fired. Caution, never money — the number is a
 *             record of what the arithmetic said, not an offer.
 *   positive  nothing refused it and the edge survives fees.
 *   negative  nothing refused it and there is no edge.
 *
 * Shared rather than written per screen because a suppressed row reaches the
 * eye down more than one path — the Board's slate rows and the Ledger — and a
 * second copy of this rule is a second chance to render green over a defect.
 */
export type EdgeTone = "suspect" | "refused" | "positive" | "negative";

export function edgeTone(
  rec: Pick<Recommendation, "edge_cents" | "suppressed_reason">,
): EdgeTone {
  if (hasSuppression(rec, "suspicious_edge")) return "suspect";
  if (rec.suppressed_reason) return "refused";
  return rec.edge_cents > 0 ? "positive" : "negative";
}

/**
 * The tone as classes. `suspect` is a filled chip rather than coloured text:
 * the point is that the figure stops reading as a figure.
 */
export const EDGE_TONE_CLASS: Record<EdgeTone, string> = {
  suspect: "rounded bg-accent-soft px-1.5 py-0.5 font-extrabold text-negative",
  refused: "text-accent-2",
  positive: "text-positive",
  negative: "text-negative",
};

/**
 * A cue that survives the colour being invisible.
 *
 * Roughly one man in twelve cannot separate the two hues this palette uses for
 * good and bad, and `--negative` is the same red as `--accent` — so a rule
 * carried by colour alone is carried by nothing for those readers, and the
 * whole defect this tone exists to fix would render exactly as before.
 */
export const EDGE_TONE_MARK: Record<EdgeTone, string> = {
  suspect: "⚠ ",
  refused: "",
  positive: "",
  negative: "",
};

/** Freshness band for a quote age. Drives colour, so the eye reads it. */
export function freshness(ageMs: number, limitMs: number) {
  if (ageMs <= limitMs * 0.5) return "fresh" as const;
  if (ageMs <= limitMs) return "aging" as const;
  return "stale" as const;
}

export function formatAge(ms: number): string {
  if (ms < 1000) return "just now";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`;
  return `${(ms / 3_600_000).toFixed(1)}h ago`;
}

/**
 * The same duration as a *length* rather than a point in time.
 *
 * "quote 40s ago" reads correctly in a metadata row and "this price is 40s ago"
 * does not. Two functions rather than one with a flag, because the difference is
 * grammatical and shows up only when the string is read in a sentence — which
 * is exactly where nothing automated in this repo would catch it.
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return "under a second";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  return `${(ms / 3_600_000).toFixed(1)}h`;
}

/**
 * The one timezone every human-facing clock on this product renders in.
 *
 * **Pinned to a zone, not left to the device, and that is the point.** These
 * used to pass `undefined` as the locale, which renders in whatever the browser
 * says -- so the same slot read 16:51 on the phone, 19:51 on a laptop borrowed
 * in another zone, and something else again in a screenshot pasted into a chat.
 * A schedule whose times depend on which screen is reading it cannot be quoted,
 * compared against a previous session, or acted on with any confidence.
 *
 * `America/Los_Angeles`, not a fixed -8 offset, so the switch to and from
 * daylight saving is handled by the platform rather than by us being wrong for
 * eight months of the year. In August this renders PDT; the label is drawn from
 * the same formatter, so it says PDT rather than claiming PST.
 *
 * **The record stays UTC.** Every millisecond on the wire, in the database and
 * in `docs/measurements` is UTC, and none of that changes -- this is a display
 * decision at the last possible moment. The mixing that let a three-hour offset
 * hide for eleven build steps was in *stored* and *compared* values, not in
 * what a phone prints.
 */
export const DISPLAY_TIME_ZONE = "America/Los_Angeles";

/** `PDT` / `PST`, drawn from the formatter so it cannot claim the wrong one. */
export function displayZoneLabel(ms: number = Date.now()): string {
  const part = new Intl.DateTimeFormat("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    timeZoneName: "short",
  })
    .formatToParts(new Date(ms))
    .find((p) => p.type === "timeZoneName");
  return part?.value ?? "PT";
}

/** A clock time, for a moment the user has to act at rather than react to. */
export function formatClock(ms: number | null): string {
  if (!ms) return "";
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "in 12m" / "in 3h 20m". Used for a future instant; `formatAge` is the past. */
export function formatUntil(ms: number): string {
  if (ms <= 0) return "now";
  const minutes = Math.round(ms / 60_000);
  if (minutes < 1) return "in under a minute";
  if (minutes < 60) return `in ${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `in ${hours}h ${minutes % 60}m`;
}

export function formatKickoff(ms: number | null): string {
  if (!ms) return "";
  return new Date(ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** One strategy version, and the evidence recorded while it was in force. */
export type ConfigVersion = {
  version: number;
  created_ms: number;
  effective_from_ms: number;
  effective_to_ms: number | null;
  is_current: boolean;
  approved_by_user: boolean;
  rationale: string;
  config: Record<string, unknown> | null;
  recommendations: number;
  markets: number;
  unsuppressed: number;
  actionable: number;
  clv_scored: number;
  /**
   * A version with too few rows to say anything. Rendered as a caveat rather
   * than used as a filter: a starved version is itself a finding, because it
   * shortened every neighbouring version's sample too.
   */
  has_enough_to_say_anything: boolean;
  changed_from_previous: Record<string, { from: unknown; to: unknown }>;
};

export type Lesson = {
  id: number;
  created_ms: number;
  title: string;
  body: string;
  evidence: Record<string, unknown> | null;
  sample_size: number | null;
  proposed_config_diff: Record<string, unknown> | null;
  /**
   * Three states. `null` is "nobody has decided" and `false` is "rejected" --
   * collapsing them would turn every proposal awaiting a human into one a
   * human refused.
   */
  accepted_by_user: boolean | null;
};

export type Playbook = {
  config_versions: ConfigVersion[];
  current_version: number | null;
  lessons: Lesson[];
  proposals_awaiting_approval: Lesson[];
  /**
   * The distinction this screen must not collapse. `lessons` has exactly one
   * writer and nothing that runs calls it, so an empty list means the agent is
   * unwired -- not that the record contains nothing worth learning.
   */
  historian_has_run: boolean;
  note: string;
  min_rows_to_mean_anything: number;
};

export const fetchPlaybook = () => get<Playbook>("/api/playbook");

/** What `POST /api/odds/refresh` answers with. */
export type OddsRefreshResult = {
  accepted: boolean;
  detail: string;
  estimated_credits: number;
  retry_after_ms: number;
};

/**
 * Ask the runner to buy fresh sportsbook odds now.
 *
 * **The answer is `accepted`, never `refreshed`.** The API process opens the
 * database read-only and is not the process holding the odds client, so it
 * writes a request the chain runner picks up on its ~15s cadence. A button that
 * said "refreshed" on a 202 would be reporting a call that has not been made
 * and may still be refused on budget.
 *
 * A refusal — cooldown, the day's slice for taps, the odds budget — comes back
 * as HTTP 200 with `accepted: false` and the reason in words. That is
 * deliberate: those are normal answers to a reasonable tap, and a 4xx would
 * have the UI render one as a fault.
 *
 * `oddsEventId` is what makes it expensive. Omitted, this buys the sport's team
 * lines. Supplied, it also buys that one fixture's player props, which is
 * billed per market key per region.
 *
 * **No token parameter, unlike `placeOrder`.** The browser cannot have one, and
 * the request goes through a Next route handler that holds it. Relative URL
 * rather than `BASE` for the same reason: this path exists only on the Next
 * origin, and `BASE` points at the Python backend when rendered server-side.
 */
export async function refreshOdds(
  sportKey: string,
  oddsEventId: string | null,
): Promise<OddsRefreshResult> {
  let response: Response;
  try {
    // `/refresh-odds`, not `/api/odds/refresh`. The browser has no bearer token
    // -- by design, see `lib/session.ts` -- so the Next route handler at that
    // path adds it server-side. It also explains what that widens.
    response = await fetch(`/refresh-odds`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({
        sport_key: sportKey,
        odds_event_id: oddsEventId,
      }),
    });
  } catch (error) {
    return {
      accepted: false,
      detail: `The request did not reach the cockpit (${
        error instanceof Error ? error.message : "network error"
      }). No credits were spent.`,
      estimated_credits: 0,
      retry_after_ms: 0,
    };
  }

  const body: unknown = await response.json().catch(() => null);
  if (
    response.ok &&
    body &&
    typeof body === "object" &&
    "accepted" in body
  ) {
    return body as OddsRefreshResult;
  }
  // 401, 403, or a proxy page. Not a refusal from the endpoint, so it must not
  // be rendered as one -- and above all it must not read as "no odds available".
  const detail =
    body && typeof body === "object" && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : `HTTP ${response.status}, and the body was not readable as JSON.`;
  return {
    accepted: false,
    detail,
    estimated_credits: 0,
    retry_after_ms: 0,
  };
}

/** One upcoming fixture a refresh may name, as the books see it. */
export type RefreshableFixture = {
  odds_event_id: string;
  commence_ms: number;
  /** `Away at Home`, from the books' own team names. */
  title: string;
};

export type RefreshableSport = {
  sport_key: string;
  /** Credits one team-lines refresh costs, from the deployed config. */
  team_credits: number;
  /** Credits one fixture's props cost — including the team call that finds it. */
  prop_credits: number;
  fixtures: RefreshableFixture[];
};

export type Refreshable = {
  sports: RefreshableSport[];
  manual_daily_credits: number;
  cooldown_ms: number;
  note: string;
};

/**
 * What the refresh button may buy, and what each purchase costs.
 *
 * Its own route rather than fields on the Slate or the Board. Those payloads
 * are pinned by four tests that stop anything on them becoming a composite, and
 * a fixture list keyed for *spending* has no business travelling beside rows
 * keyed for *reading*.
 */
export const fetchRefreshable = () => get<Refreshable>("/api/odds/refreshable");

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

export const searchEstimateMarkets = (q: string) =>
  get<{ markets: EstimateMarket[] }>(
    `/api/estimates/markets?q=${encodeURIComponent(q)}`,
  );

export const fetchRecentEstimates = () =>
  get<{ estimates: RecentEstimate[] }>("/api/estimates/recent");

/** What `POST /log-estimate` answers with. Quote-free by construction. */
export type EstimateLogged = {
  id: number;
  ticker: string;
  stated_probability_bp: number;
  estimate_server_ms: number;
};

/**
 * Log one estimate, through the Next route handler that holds the bearer
 * token server-side (the `/refresh-odds` pattern: the browser proves session,
 * the server supplies authority).
 */
export async function logEstimate(body: {
  ticker: string;
  stated_probability_bp: number;
  had_already_opened_kalshi: 0 | 1;
  estimate_client_ms: number;
}): Promise<EstimateLogged> {
  const response = await fetch(`/log-estimate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload.detail === "string"
        ? payload.detail
        : `logging failed (${response.status})`;
    throw new Error(detail);
  }
  return payload as EstimateLogged;
}

/** Flag an estimate as mistyped. Append-only; nothing is edited in place. */
export async function reviseEstimate(id: number, reason: string): Promise<void> {
  const response = await fetch(`/revise-estimate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({ id, reason }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      payload && typeof payload.detail === "string"
        ? payload.detail
        : `revision failed (${response.status})`;
    throw new Error(detail);
  }
}
