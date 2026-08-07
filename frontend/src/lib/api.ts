/**
 * Backend types and fetchers.
 *
 * Prices arrive as integer tenths of a cent *and* as pre-rendered display
 * strings. The frontend uses the display string and never re-derives a price
 * from the float -- doing arithmetic on money in two places is how the two
 * places drift apart.
 */

export type Recommendation = {
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
  fair_display: string;
  edge_tenths: number;
  edge_cents: number;
  fee_predicted: number;
  ev_net_dollars: number;
  suggested_contracts: number;
  kelly_fraction: number;
  kalshi_quote_age_ms: number;
  odds_age_ms: number;
  depth_at_ask: number | null;
  suppressed_reason: string | null;
  reason_text: string;
  clv_tenths: number | null;
};

export type Board = {
  surfaced: Recommendation[];
  suppressed: Recommendation[];
  counts: { surfaced: number; suppressed: number; no_edge: number };
  note: string;
};

export type GateCondition = { name: string; met: boolean; detail: string };
export type Gate = {
  open: boolean;
  conditions: GateCondition[];
  /** Every unmet condition, not just the first — the distance from open is the useful part. */
  reason: string;
  bankroll_dollars: number;
  note: string;
};

/**
 * Ask the server to place an order. The client sends a recommendation id and a
 * size and nothing else: the ticker, side and price are read server-side from
 * the recommendation, so a stale or tampered client cannot buy a different
 * market or a better price than the one on record.
 *
 * 423 is the locked gate and carries the unmet conditions.
 */
export async function placeOrder(
  recommendationId: number,
  contracts: number,
  token?: string,
): Promise<
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; status: number; detail: unknown }
> {
  const response = await fetch(`${BASE}/api/orders`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
    body: JSON.stringify({
      recommendation_id: recommendationId,
      contracts,
    }),
  });
  if (response.ok) return { ok: true, value: await response.json() };
  const body = await response.json().catch(() => ({}));
  return { ok: false, status: response.status, detail: body.detail };
}

export type Ledger = {
  rows: Recommendation[];
  /** Independent games scored, which is what the gate counts. Not row count. */
  clv_scored: number;
  /** Raw recommendation rows behind those games, kept visible beside them. */
  clv_scored_rows: number;
  clv_required: number;
  gate_open: boolean;
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

export const fetchBoard = (includeSuppressed = false) =>
  get<Board>(`/api/board?include_suppressed=${includeSuppressed}`);

export const fetchLedger = () => get<Ledger>("/api/ledger");

export const fetchGate = () => get<Gate>("/api/gate");

export const fetchHealth = () =>
  get<{ instance_mode: string; execution_available: boolean }>("/api/health");

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

export function formatKickoff(ms: number | null): string {
  if (!ms) return "";
  return new Date(ms).toLocaleString(undefined, {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}
