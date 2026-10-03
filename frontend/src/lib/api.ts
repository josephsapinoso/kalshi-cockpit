/**
 * Backend types and fetchers.
 *
 * Prices arrive as integer tenths of a cent *and* as pre-rendered display
 * strings. The frontend uses the display string and never re-derives a price
 * from the float -- doing arithmetic on money in two places is how the two
 * places drift apart.
 */

import {
  networkMessage,
  postJson,
  refusalText,
  type WriteResult,
} from "./transport";

// `refusalText` lives in the transport (ADR 0191); it is re-exported so every
// existing import of it from `@/lib/api` keeps working.
export { refusalText };
export type { WriteResult };

// The wire types live one file per area in `./types/` (#262, ADR 0191 sec 2.5);
// api.ts imports what its fetchers use and re-exports every name, so no import
// elsewhere changes.
import type {
  ConfigVersion,
  ConsensusProvenance,
  Dashboards,
  DevigMethods,
  Gate,
  GateCondition,
  Ledger,
  ListFilter,
  ListFilterEcho,
  Panel,
  Recommendation,
  Signal,
  Suppression,
  TrustScore,
} from "./types/signal";
import type {
  ActionableWindow,
  Board,
  EdgeTone,
  Exposure,
  OddsRefreshResult,
  OpenPositionsBlock,
  PlannedSlot,
  Refreshable,
  RefreshableBeyondHorizon,
  RefreshableFixture,
  RefreshableSport,
  Slate,
  SlatePick,
  SlatePicks,
  SlateRowData,
  TonightActivity,
} from "./types/slate";
import type {
  BookDistribution,
  ChartCandle,
  EstimateLogged,
  EstimateMarket,
  LineShopData,
  LineShopLeg,
  MarketCandles,
  MarketDetail,
  RecentEstimate,
  StudyStop,
} from "./types/market";
import type {
  LockedDetail,
  ManualMarket,
  ManualMarketSide,
  ManualOrderPlaced,
  ManualOrderResult,
  OrderPlaced,
  OrderQuote,
  OrderResult,
} from "./types/orders";
import type {
  CheckedParlayLeg,
  CheckedParlayResult,
  ComboBid,
  ComboBidResult,
  ComboRfqAcceptResult,
  ComboRfqQuote,
  ComboRfqResult,
  GameLeg,
  GameLegGroup,
  GameLegSide,
  GameLegs,
  GameMintResult,
  GameScriptCard,
  GameScriptCards,
  GameScriptLeg,
  LegRest,
  LegVerdict,
  LegVerdictInput,
  LegVerdictState,
  LegVerdictTrigger,
  LegVerdictsResult,
  ParlayCardData,
  ParlayCardJoint,
  ParlayCardLeg,
  ParlayCardScouting,
  ParlayHorizon,
  ParlayLadder,
  ParlayLeg,
  ParlayLookupResult,
  ParlayPrefix,
  ParlayStake,
  ParlayValuation,
  ParlayWindow,
  TeamRest,
} from "./types/parlays";
import type {
  HedgeBlock,
  HedgeRefusal,
  HedgeRung,
  HedgeScreen,
  HedgeSellQuote,
  HeldLeg,
  HeldLegInput,
  HeldPosition,
  HeldPositionInput,
  UnrecordedAtVenue,
  VenueSettlement,
} from "./types/hedge";
import type {
  BetKind,
  BetsRecord,
  BetsSection,
  ExpectedBlock,
  SettledBet,
} from "./types/bets";
import type {
  BoardTile,
  DeskBriefing,
  Gauntlet,
  Lesson,
  Playbook,
  RecordPassResult,
  ScoutBriefingState,
  ScoutFinding,
  ScoutOverview,
  ScoutOverviewRow,
  ScoutSpend,
  ScoutStaffNote,
  ScoutStaffReport,
  SendDeskResult,
  SharpTake,
} from "./types/scout";
export type {
  ConfigVersion,
  ConsensusProvenance,
  Dashboards,
  DevigMethods,
  Gate,
  GateCondition,
  Ledger,
  ListFilter,
  ListFilterEcho,
  Panel,
  Recommendation,
  Signal,
  Suppression,
  TrustScore,
} from "./types/signal";
export type {
  ActionableWindow,
  Board,
  EdgeTone,
  Exposure,
  OddsRefreshResult,
  OpenPositionsBlock,
  PlannedSlot,
  Refreshable,
  RefreshableBeyondHorizon,
  RefreshableFixture,
  RefreshableSport,
  Slate,
  SlatePick,
  SlatePicks,
  SlateRowData,
  TonightActivity,
} from "./types/slate";
export type {
  BookDistribution,
  ChartCandle,
  EstimateLogged,
  EstimateMarket,
  LineShopData,
  LineShopLeg,
  MarketCandles,
  MarketDetail,
  RecentEstimate,
  StudyStop,
} from "./types/market";
export type {
  LockedDetail,
  ManualMarket,
  ManualMarketSide,
  ManualOrderPlaced,
  ManualOrderResult,
  OrderPlaced,
  OrderQuote,
  OrderResult,
} from "./types/orders";
export type {
  CheckedParlayLeg,
  CheckedParlayResult,
  ComboBid,
  ComboBidResult,
  ComboRfqAcceptResult,
  ComboRfqQuote,
  ComboRfqResult,
  GameLeg,
  GameLegGroup,
  GameLegSide,
  GameLegs,
  GameMintResult,
  GameScriptCard,
  GameScriptCards,
  GameScriptLeg,
  LegRest,
  LegVerdict,
  LegVerdictInput,
  LegVerdictState,
  LegVerdictTrigger,
  LegVerdictsResult,
  ParlayCardData,
  ParlayCardJoint,
  ParlayCardLeg,
  ParlayCardScouting,
  ParlayHorizon,
  ParlayLadder,
  ParlayLeg,
  ParlayLookupResult,
  ParlayPrefix,
  ParlayStake,
  ParlayValuation,
  ParlayWindow,
  TeamRest,
} from "./types/parlays";
export type {
  HedgeBlock,
  HedgeRefusal,
  HedgeRung,
  HedgeScreen,
  HedgeSellQuote,
  HeldLeg,
  HeldLegInput,
  HeldPosition,
  HeldPositionInput,
  HeldConflict,
  HeldConflicts,
  UnrecordedAtVenue,
  VenueSettlement,
} from "./types/hedge";
export type {
  BetKind,
  BetsKindSummary,
  BetsRecord,
  BetsSection,
  BySourceBlock,
  ExpectedBlock,
  PickSourceKey,
  PickSourcesBlock,
  SettledBet,
} from "./types/bets";
export type {
  BoardTile,
  DeskBriefing,
  Gauntlet,
  Lesson,
  Playbook,
  RecordPassResult,
  ScoutBriefingState,
  ScoutFinding,
  ScoutOverview,
  ScoutOverviewRow,
  ScoutSpend,
  ScoutStaffNote,
  ScoutStaffReport,
  SendDeskResult,
  SharpTake,
} from "./types/scout";

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
  // A lost reply is UNKNOWN, not "nothing happened" (ADR 0191 section 2.3):
  // a connection can drop after the cockpit has already sent the order on, so
  // neither sentence below may claim nothing was sent. The engine path is dry
  // today (ORDERS_ARE_DRY_RUNS); the words are written for the day it is not.
  // A 2xx that cannot be read is unreadable too, never a placed order.
  return postJson<OrderPlaced>({
    path: `${BASE}/api/orders`,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: {
      recommendation_id: recommendationId,
      contracts,
      idempotency_key: idempotencyKey,
    },
    noReply: (error) =>
      `The order's answer never arrived (${networkMessage(error)}). It may ` +
      "have reached the exchange -- check the Kalshi app before trying again.",
    unreadable: (status) =>
      `HTTP ${status}, and the answer was not readable. The order may have ` +
      "reached the exchange -- check the Kalshi app before trying again.",
    noDetail: (status) => `HTTP ${status}, and the refusal carried no reason.`,
  });
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

/**
 * A non-2xx answer, with its status kept. Every page catches `get` failures
 * as "backend unreachable"; a 422 on a list cut (#15) is not that, it is
 * "the backend refused the value in the URL", and a page that cannot tell
 * the two apart prints the wrong sentence for one of them.
 */
export class ApiError extends Error {
  readonly status: number;
  constructor(path: string, status: number) {
    super(`${path} returned ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

async function get<T>(path: string): Promise<T> {
  // `no-store`: this is live market data. A cached board showing a stale price
  // as fresh is precisely the failure the staleness contract exists to prevent.
  const response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(path, response.status);
  }
  return response.json() as Promise<T>;
}

export const NO_FILTER: ListFilter = { league: null, withinHours: null };

/** Read the cut out of a page's `searchParams`. Absent is `null`; an empty
 *  string is a VALUE, and the server refuses it -- see `ListFilter`. */
export function readListFilter(params: {
  league?: string | string[];
  within_hours?: string | string[];
}): ListFilter {
  const first = (v: string | string[] | undefined): string | null =>
    v === undefined ? null : Array.isArray(v) ? (v[0] ?? null) : v;
  return { league: first(params.league), withinHours: first(params.within_hours) };
}

/** `?league=...&within_hours=...`, or "" when nothing is cut -- the same
 *  string on a `Link` and on the fetch, so the URL and the request agree. */
export function listFilterQuery(filter: ListFilter): string {
  const qs = new URLSearchParams();
  if (filter.league !== null) qs.set("league", filter.league);
  if (filter.withinHours !== null) qs.set("within_hours", filter.withinHours);
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export const fetchDashboards = () => get<Dashboards>("/api/dashboards");

/**
 * Price a parlay. Same-game legs come back as a 422 carrying the refusal text,
 * which the Builder shows verbatim -- the explanation is the useful output.
 */
export async function priceParlay(
  legs: ParlayLeg[],
  offeredAmerican: number,
  overrides: { a: string; b: string; rho: number }[] = [],
): Promise<WriteResult<ParlayValuation>> {
  return postJson<ParlayValuation>({
    path: `${BASE}/api/builder/parlay`,
    body: {
      legs,
      offered_american: offeredAmerican,
      correlation_overrides: overrides,
    },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "Nothing was priced.",
    unreadable: (status) =>
      `HTTP ${status}, and the body was not readable as JSON.`,
  });
}

export const fetchParlays = (
  filter: ListFilter = NO_FILTER,
  horizon: ParlayHorizon | null = null,
) => {
  const cut = listFilterQuery(filter);
  const query =
    horizon === null
      ? cut
      : cut
        ? `${cut}&horizon=${horizon}`
        : `?horizon=${horizon}`;
  return get<ParlayLadder>(`/api/parlays${query}`);
};

/**
 * Take a quote. **This is the one call in this file that spends money.**
 *
 * The second tap of B = (ii): no price and no side are sent, because Joe has
 * already seen this exact quote and the server reads the price from its own
 * record of it. Nothing the browser sends can change what is bought.
 *
 * A failure here is an **unknown**, not a refusal — the acceptance may have
 * reached Kalshi, and an RFQ acceptance carries no idempotency key, so
 * nothing retries it.
 */
export async function acceptComboQuote(
  rfqId: string,
  quoteId: string,
): Promise<WriteResult<ComboRfqAcceptResult>> {
  // This call SPENDS. Nothing on it retries, ever (ADR 0164/0165), and a lost
  // or unreadable answer is UNKNOWN: the acceptance may have executed.
  const unreadable = () =>
    "The answer came back in a shape this screen cannot read. Check the " +
    "Kalshi app rather than trusting anything shown here.";
  return postJson<ComboRfqAcceptResult>({
    path: "/parlay-rfq-accept",
    body: { rfq_id: rfqId, quote_id: quoteId },
    shape: (body) => !!body && typeof body === "object" && "status" in body,
    noReply: (error) =>
      `The acceptance did not complete (${networkMessage(error)}). It may ` +
      "still have reached Kalshi — this desk will not send it again. " +
      "Check the Kalshi app before tapping anything else.",
    unreadable,
    noDetail: unreadable,
  });
}

export async function askMarketToPrice(
  marketTicker: string,
  targetCostDollars: string,
): Promise<WriteResult<ComboRfqResult>> {
  return postJson<ComboRfqResult>({
    path: "/parlay-rfq",
    body: {
      market_ticker: marketTicker,
      target_cost_dollars: targetCostDollars,
    },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "Nothing was bought and nothing is resting -- asking for a price " +
      "never commits you to anything.",
    unreadable: () =>
      "The answer came back in a shape this screen cannot read. Nothing " +
      "is shown rather than a price that might be wrong.",
    shape: (b) => typeof b === "object" && b !== null && "status" in b,
  });
}

export async function lookupParlay(
  cardKey: string,
  stakeCents: number,
  legs: { event_ticker: string; market_ticker: string; side: "yes" | "no" }[],
  horizon?: ParlayHorizon,
): Promise<WriteResult<ParlayLookupResult>> {
  return postJson<ParlayLookupResult>({
    path: "/parlay-lookup",
    body: {
      card_key: cardKey,
      stake_cents: stakeCents,
      legs,
      // **The window the card was BUILT under, not a client guess.**
      // Until 2026-09-10 this call never sent one, so the backend always
      // priced against `tonight` regardless of which window
      // `GET /api/parlays` used to build the card -- every leg beyond
      // tonight on a card built under `tomorrow` or `48h` was refused by
      // a lookup that could not tell "started" from "not tonight" (item 0,
      // `docs/adr/0138-a-lookup-prices-the-window-the-card-was-built-
      // in.md`). `undefined` is omitted by `JSON.stringify` rather than
      // sent as `null`, so an old caller that never passes `horizon`
      // still gets the server's own `tonight` default.
      ...(horizon ? { horizon } : {}),
    },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "No money moves either way, but the combination may already have " +
      "been created on Kalshi — check the app before tapping again.",
    unreadable: () =>
      "Kalshi's answer came back in a shape this screen cannot read. " +
      "Nothing is shown rather than a number that might be wrong.",
    shape: (b) => typeof b === "object" && b !== null && "status" in b,
  });
}

/** Read one game's legs. Throws with the backend's own words on a refusal. */
export async function fetchGameLegs(eventTicker: string): Promise<GameLegs> {
  const response = await fetch(
    `${BASE}/api/game/${encodeURIComponent(eventTicker)}/legs`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      payload && typeof payload.detail === "string"
        ? payload.detail
        : `the game builder returned ${response.status}`;
    throw new Error(detail);
  }
  return response.json() as Promise<GameLegs>;
}

/**
 * Mint the ticked legs as one combination, through the `/game-mint` route
 * handler so the bearer token stays server-side. Creates a real market on
 * Kalshi (no money moves). **Never throws**, and a dropped connection is
 * NOT the same as nothing happening: the POST may have reached Kalshi.
 */
export async function mintGameCombo(
  eventTicker: string,
  legs: { market_ticker: string; event_ticker: string; side: "yes" | "no" }[],
): Promise<WriteResult<GameMintResult>> {
  return postJson<GameMintResult>({
    path: "/game-mint",
    body: { event_ticker: eventTicker, legs },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "No money moves either way, but the combination may already have " +
      "been created on Kalshi — check the app before tapping again.",
    unreadable: () =>
      "Kalshi's answer came back in a shape this screen cannot read. " +
      "The combination may exist; check the Kalshi app.",
    shape: (b) => typeof b === "object" && b !== null && "status" in b,
  });
}

/**
 * Check a parlay someone else built (issue #165/#167): Joe pastes a
 * kalshi.com link or a KXMVE ticker and this reads back each leg's desk
 * chance, the joint chance, the fair price and the book's ask.
 *
 * Goes through the `/parlay-check` route handler so the bearer token stays
 * server-side, same as `lookupParlay` above. **Never throws** — same reason:
 * this function's caller renders a single button that must not be left
 * stranded mid-request.
 */
export async function checkParlay(
  text: string,
): Promise<WriteResult<CheckedParlayResult>> {
  return postJson<CheckedParlayResult>({
    path: "/parlay-check",
    body: { text },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "Nothing was checked.",
    unreadable: () =>
      "Kalshi's answer came back in a shape this screen cannot read. " +
      "Nothing is shown rather than a number that might be wrong.",
    shape: (b) => typeof b === "object" && b !== null && "status" in b,
  });
}

export const fetchWindow = () => get<ActionableWindow>("/api/window");

export const fetchBoard = (includeSuppressed = false) =>
  get<Board>(`/api/board?include_suppressed=${includeSuppressed}`);

export const fetchLedger = () => get<Ledger>("/api/ledger");

export const fetchGate = () => get<Gate>("/api/gate");

export const fetchSignal = () => get<Signal>("/api/signal");

export const fetchSuppression = (sinceMs = 0) =>
  get<Suppression>(`/api/suppression?since_ms=${sinceMs}`);

/** Reads, and never gates. A thrown fetch or a non-2xx is rendered as a
 *  refusal beside the buy button (`exposureUnreadable`), never as a reason to
 *  disable it — ADR 0112 removed all five brakes and this adds no sixth. */
export const fetchExposure = () => get<Exposure>("/api/exposure");

export const fetchSlate = (filter: ListFilter = NO_FILTER) =>
  get<Slate>(`/api/slate${listFilterQuery(filter)}`);

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

export function edgeTone(
  rec: Pick<
    Recommendation,
    "edge_cents" | "suppressed_reason" | "suggested_contracts"
  >,
): EdgeTone {
  if (hasSuppression(rec, "suspicious_edge")) return "suspect";
  if (rec.suppressed_reason) return "refused";
  // Unbettable is unbettable whichever rule said so. A row the sizer left at
  // zero contracts has no suppression code, but its number is still not money
  // — below ~$250 of bankroll quarter-Kelly sizes under one contract across
  // the whole band, so this is the modal row, not a corner case. Reading the
  // sign before reading the size painted those rows green.
  if (rec.suggested_contracts === 0) return "refused";
  return rec.edge_cents > 0 ? "positive" : "negative";
}

/**
 * The tone as classes. `suspect` is a filled chip rather than coloured text:
 * the point is that the figure stops reading as a figure.
 */
export const EDGE_TONE_CLASS: Record<EdgeTone, string> = {
  suspect: "rounded bg-negative-soft px-1.5 py-0.5 font-extrabold text-negative",
  refused: "text-accent-2",
  positive: "text-positive",
  negative: "text-negative",
};

/**
 * A cue that survives the colour being invisible.
 *
 * Roughly one man in twelve cannot separate the two hues this palette uses for
 * good and bad, so a rule carried by colour alone is carried by nothing for
 * those readers and the whole defect this tone exists to fix would render
 * exactly as before.
 *
 * This used to add "and `--negative` is the same red as `--accent`". ADR 0081
 * separated them and the mark stays anyway: the second reason was never the
 * load-bearing one, and a cue that survives the colour being invisible is not
 * made unnecessary by the colour becoming clearer.
 */
export const EDGE_TONE_MARK: Record<EdgeTone, string> = {
  suspect: "⚠ ",
  refused: "",
  positive: "",
  negative: "",
};

// The formatters live in `./format` (ADR 0191 follow-up, #261); re-exported so every
// existing import from `@/lib/api` keeps working.
export {
  DISPLAY_TIME_ZONE,
  displayZoneLabel,
  formatAge,
  formatClock,
  formatDuration,
  formatKickoff,
  formatUntil,
  freshness,
} from "./format";

export const fetchPlaybook = () => get<Playbook>("/api/playbook");

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
  // `/refresh-odds`, not `/api/odds/refresh`. The browser has no bearer token
  // -- by design, see `lib/session.ts` -- so the Next route handler at that
  // path adds it server-side. It also explains what that widens.
  const unreadable = (status: number) =>
    `HTTP ${status}, and the body was not readable as JSON.`;
  const result = await postJson<OddsRefreshResult>({
    path: `/refresh-odds`,
    body: {
      sport_key: sportKey,
      odds_event_id: oddsEventId,
    },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "No credits were spent.",
    unreadable,
    noDetail: unreadable,
    shape: (b) => typeof b === "object" && b !== null && "accepted" in b,
  });
  if (result.ok) return result.value;
  // 401, 403, or a proxy page. Not a refusal from the endpoint, so it must not
  // be rendered as one -- and above all it must not read as "no odds available".
  return {
    accepted: false,
    detail: result.refusal,
    estimated_credits: 0,
    retry_after_ms: 0,
  };
}

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
 * Find a market to hand-bet that no screen surfaced.
 *
 * Reuses `EstimateMarket` because the payload is the same rows from the
 * same price-free SELECT: `/api/manual/search` delegates to
 * `estimates.search_markets`, whose query carries no quote column at all.
 * That used to be what let a search screen exist without breaking ADR 0065's
 * masking; the ticket stopped asking for a probability on 2026-09-09, and
 * what the price-free SELECT buys now is that this list cannot show an ask
 * with no age and no currency judgement beside it.
 *
 * **This replaced `searchEstimateMarkets`, which had no caller.** The
 * standalone `/estimate` form retired with ADR 0065 and took its search box
 * with it; the fetcher outlived the screen. Repointed rather than
 * duplicated.
 */
export const searchManualMarkets = (q: string) =>
  get<{ markets: EstimateMarket[]; query: string }>(
    `/api/manual/search?q=${encodeURIComponent(q)}`,
  );

export const fetchRecentEstimates = () =>
  get<{ estimates: RecentEstimate[] }>("/api/estimates/recent");

export const fetchStudyStop = () => get<StudyStop>("/api/estimates/stop");

/**
 * One tap of "not tonight": lock the estimate log until the next day roll.
 * No parameters and no cancel — the release is the clock. The backend owns
 * both the 423 and the release instant; this only carries the tap.
 */
export async function engageLockout(): Promise<WriteResult<{ until_ms: number }>> {
  return postJson<{ until_ms: number }>({
    path: `/lockout`,
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "The lockout may not be on -- tap again.",
    unreadable: (status) => `lockout failed (${status})`,
  });
}

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
}): Promise<WriteResult<EstimateLogged>> {
  return postJson<EstimateLogged>({
    path: `/log-estimate`,
    body,
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "The estimate may not have been logged -- check the recent list before logging it again.",
    unreadable: (status) => `logging failed (${status})`,
  });
}

/** Flag an estimate as mistyped. Append-only; nothing is edited in place. */
export async function reviseEstimate(
  id: number,
  reason: string,
): Promise<WriteResult<null>> {
  return postJson<null>({
    path: `/revise-estimate`,
    body: { id, reason },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "The revision may not have been recorded -- check the recent list before revising again.",
    unreadable: (status) => `revision failed (${status})`,
    tolerateEmptyBody: true,
  });
}

/**
 * Kalshi's own candlesticks for one market, shaped for the chart. History,
 * not a quote: nothing from this payload may feed a sizing or order decision
 * — the price you would actually pay is the ask, on the slate.
 */
export async function fetchMarketCandles(
  ticker: string,
  range: MarketCandles["range"],
): Promise<MarketCandles> {
  const response = await fetch(
    `${BASE}/api/market/${encodeURIComponent(ticker)}/candles?range=${range}`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      payload && typeof payload.detail === "string"
        ? payload.detail
        : `price history returned ${response.status}`;
    throw new Error(detail);
  }
  return response.json() as Promise<MarketCandles>;
}

export async function fetchScoutBriefing(
  ticker: string,
): Promise<ScoutBriefingState> {
  const response = await fetch(
    `${BASE}/api/scout/${encodeURIComponent(ticker)}`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      payload && typeof payload.detail === "string"
        ? payload.detail
        : `the scout desk returned ${response.status}`;
    throw new Error(detail);
  }
  return response.json() as Promise<ScoutBriefingState>;
}

/**
 * Send the desk, via the `/scout-desk` Next route handler -- the browser
 * deliberately holds no bearer token (`lib/session.ts`), so the handler adds
 * it server-side, exactly as `/refresh-odds` does for odds credits.
 */
export async function sendScoutDesk(ticker: string): Promise<SendDeskResult> {
  const result = await postJson<unknown>({
    path: `/scout-desk`,
    body: { ticker },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "Nothing was spent.",
    unreadable: (status) => `HTTP ${status}`,
    tolerateEmptyBody: true,
  });
  if (result.ok) {
    const body = result.value;
    const id =
      body && typeof body === "object" && "id" in body
        ? Number((body as { id: unknown }).id)
        : 0;
    return { accepted: true, id };
  }
  return { accepted: false, status: result.status, detail: result.refusal };
}

/**
 * Record one deliberate pass on a market, via the `/pass` Next route handler
 * -- the browser deliberately holds no bearer token (`lib/session.ts`), so
 * the handler adds it server-side, exactly as `/scout-desk` does.
 *
 * No-throw by design (the `sendScoutDesk` shape): the caller renders the
 * refusal as words, and a pass that fails must say so rather than silently
 * looking recorded.
 */
export async function recordPass(
  ticker: string,
  reason?: string,
): Promise<RecordPassResult> {
  const result = await postJson<unknown>({
    path: `/pass`,
    body: reason && reason.trim().length > 0 ? { ticker, reason } : { ticker },
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "Nothing was recorded.",
    unreadable: (status) => `HTTP ${status}`,
    tolerateEmptyBody: true,
  });
  if (result.ok) {
    const body = result.value;
    const id =
      body && typeof body === "object" && "id" in body
        ? Number((body as { id: unknown }).id)
        : 0;
    return { recorded: true, id };
  }
  return { recorded: false, status: result.status, detail: result.refusal };
}

/**
 * Tell the backend someone has the desk open.
 *
 * The odds feed follows this instead of a clock (ADR 0071 §2.6). Called from
 * `Nav.tsx` once a minute and on `visibilitychange`, and **only while the tab
 * is visible** — that check lives at the call site, not here, because it is
 * about whether to beat at all rather than about how.
 *
 * **Returns nothing and reports nothing.** Every other writer in this module
 * hands back a `{recorded, detail}` shape so a component can say what did not
 * happen. Here there is no component and nothing for a reader to do: a missed
 * heartbeat costs one delayed sweep, the next tick retries a minute later, and
 * an error in the chrome of every page would be noise about a request the
 * reader never made. It no longer throws on a transport failure (the transport returns it), and
 * `Nav.tsx` swallows that deliberately.
 *
 * **The body carries the path and nothing else** (v34, question E, Joe
 * 2026-09-05). The stamp's TIME is still the server's `now_ms` and is still
 * never sent -- that refusal is about a value the server acts on, and a path
 * is only recorded. `desk_attention` could previously say the desk was open
 * and not what it was open FOR, so a dwell figure could not be split by
 * screen.
 *
 * `window.location.pathname` deliberately, not `href`: the query string is
 * the row's subject (a ticker), not the screen, and the server drops it
 * anyway. Callers pass it in rather than this reading `window` itself, so the
 * function stays callable from a test and from a non-browser context.
 */
export async function recordAttention(path?: string): Promise<void> {
  await postJson<unknown>({
    path: `/desk-attention`,
    body: path ? { path } : {},
    noReply: () => "The heartbeat did not reach the cockpit.",
    unreadable: (status) => `HTTP ${status}`,
    tolerateEmptyBody: true,
  });
}

/** `null` when the record has no row for this ticker — a market the runner
 * never priced still gets its history page, just without the venue facts. */
export async function fetchMarketDetail(
  ticker: string,
): Promise<MarketDetail | null> {
  const response = await fetch(
    `${BASE}/api/market/${encodeURIComponent(ticker)}`,
    { cache: "no-store" },
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`market detail returned ${response.status}`);
  }
  return response.json() as Promise<MarketDetail>;
}

export async function fetchScoutOverview(): Promise<ScoutOverview> {
  const response = await fetch(`${BASE}/api/scout`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`the scout desk overview returned ${response.status}`);
  }
  return response.json() as Promise<ScoutOverview>;
}

export async function fetchBets(): Promise<BetsRecord> {
  const response = await fetch(`${BASE}/api/bets`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`the bets record returned ${response.status}`);
  }
  return response.json() as Promise<BetsRecord>;
}

// -- the manual order path (ADR 0063) ---------------------------------------

/** The venue's live facts for any ticker — the manual ticket's read. */
export async function fetchManualMarket(ticker: string): Promise<ManualMarket> {
  const response = await fetch(
    `${BASE}/api/manual/market/${encodeURIComponent(ticker)}`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body
        ? refusalText((body as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return response.json() as Promise<ManualMarket>;
}

/**
 * Place a manual order. Same result discipline as `placeOrder`: a thrown
 * fetch is a connection report, never a refusal, and the server's own
 * refusal sentences pass through verbatim — every one explains itself
 * better than a generic sentence could.
 */
export async function placeManualOrder(
  body: {
    ticker: string;
    side: "yes" | "no";
    contracts: number;
    max_price_tenths: number;
    idempotency_key: string;
    /** Required on a combination ticker; the route 422s without it. */
    combo_acknowledged?: boolean;
  },
): Promise<ManualOrderResult> {
  // **No token parameter since 2026-09-08.** This posts to the same-origin
  // `/manual-order` route handler, which proves session by cookie and adds
  // the bearer server-side -- the pattern `/parlay-bid` and `/refresh-odds`
  // already used. The browser deliberately holds no bearer token
  // (`lib/session.ts`), and Joe removed the typed one
  // (`docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` section 1).
  //
  // This is the ARMED path. A lost or unreadable reply is UNKNOWN (ADR 0191
  // section 2.3): the order may have filled. Until 2026-10-01 the no-reply
  // sentence said "Nothing was sent to the exchange", which a connection
  // dropped after the cockpit forwarded the order would have made false.
  return postJson<ManualOrderPlaced>({
    path: "/manual-order",
    body,
    noReply: (error) =>
      `The order's answer never arrived (${networkMessage(error)}). It may ` +
      "have reached Kalshi and filled -- check the Kalshi app before tapping " +
      "again.",
    unreadable: (status) =>
      `HTTP ${status}, and the answer was not readable. The order may have ` +
      "reached Kalshi and filled -- check the Kalshi app before tapping again.",
    noDetail: (status) => `HTTP ${status}, and the refusal carried no reason.`,
  });
}

// -- held parlays and their hedges (ADR 0078) --------------------------------

/**
 * The ONE "is this bet still live" predicate (#250). Live = a leg still
 * pending AND the venue has not settled the combination. `/bets`'s Open
 * heading, `HedgePositions`' live/settled partition and Nav's badge all call
 * this; nothing else may spell the two terms out.
 */
export function isLive(
  position: Pick<HeldPosition, "pending_legs" | "venue_settlement">,
): boolean {
  return position.pending_legs > 0 && position.venue_settlement === null;
}

export async function fetchHedge(): Promise<HedgeScreen> {
  return get<HedgeScreen>("/api/hedge");
}

/**
 * Every one of these posts to a Next route handler, never to `/api/` directly:
 * the handler holds `APP_AUTH_TOKEN` and the browser deliberately does not.
 * A refusal comes back with the backend's own sentence in `detail`, which the
 * screen renders verbatim.
 */
async function postHedge(
  path: string,
  body: unknown,
): Promise<{ ok: true; body: unknown } | { ok: false; detail: string }> {
  // The transport turns a refusal into words with `refusalText`, which
  // handles the three shapes that reach here -- FastAPI's plain string, the
  // list of dicts pydantic produces when the body itself is invalid, and an
  // object -- and an empty hedge form hits pydantic before it reaches any of
  // the backend's own checks, so the list case is the common one rather than
  // the exotic one.
  const refused = (status: number) =>
    `The cockpit refused that (${status}). Nothing changed.`;
  const result = await postJson<unknown>({
    path,
    body,
    noReply: () => "The cockpit did not answer. Nothing changed.",
    unreadable: refused,
    noDetail: refused,
    tolerateEmptyBody: true,
  });
  if (!result.ok) return { ok: false, detail: result.refusal };
  return { ok: true, body: result.value };
}

/**
 * v63: Joe's tag for where a pick came from, one ticker at a time; `null`
 * clears it. Writes `pick_sources` only -- no order, RFQ or hedge path.
 */
export function setPickSource(ticker: string, source: string | null) {
  return postHedge("/pick-source", { ticker, source });
}

export function recordHeldPosition(input: HeldPositionInput) {
  return postHedge("/hedge-position", input);
}

export function resolveHeldLeg(legId: number, outcome: "won" | "lost" | "void") {
  return postHedge("/hedge-resolve", { leg_id: legId, outcome });
}

export function closeHeldPosition(
  positionId: number,
  status: "settled" | "closed" | "void",
) {
  return postHedge("/hedge-close", { position_id: positionId, status });
}

export async function askWhatMakersWouldPay(
  positionId: number,
): Promise<{ ok: true; value: HedgeSellQuote } | { ok: false; detail: string }> {
  const answer = await postHedge("/hedge-sell-quote", { position_id: positionId });
  if (!answer.ok) return answer;
  const body = answer.body;
  if (body && typeof body === "object" && "status" in body && "words" in body) {
    return { ok: true, value: body as HedgeSellQuote };
  }
  return {
    ok: false,
    detail: "The cockpit answered in a shape this screen does not know. Nothing was sold.",
  };
}

/**
 * Putting a KXMVE combination the venue already shows held under `/hedge`'s
 * watch, in one tap (#148).
 *
 * `unrecorded_at_venue` names these; `VenueCoverageBanner` reads its
 * `ticker` field straight off that row and sends nothing else -- contracts,
 * exposure and the legs all come from the backend's own read of the venue,
 * never from here.
 */
export async function adoptVenueCombo(
  ticker: string,
): Promise<{ ok: true; value: { position_id: number } } | { ok: false; detail: string }> {
  const answer = await postHedge("/hedge-adopt", { ticker });
  if (!answer.ok) return answer;
  const body = answer.body;
  if (body && typeof body === "object" && "position_id" in body) {
    return { ok: true, value: body as { position_id: number } };
  }
  return {
    ok: false,
    detail: "The cockpit answered in a shape this screen does not know. Nothing was adopted.",
  };
}

// -- resting bids on a combination (ADR 0084) --------------------------------
//
// **A different verb from every other buy control in this app.** Everywhere
// else, buying means taking an offer that is already there. A combination has
// no offer to take -- 40 of 40 books this tool has read carried no resting YES
// bid -- so this places one and waits. The types keep that distinction visible
// rather than calling it a purchase.

export const fetchComboBids = () =>
  get<{ generated_ms: number; bids: ComboBid[] }>("/api/parlays/bids");

/**
 * Rest a bid on a card's combination.
 *
 * Never throws: a throw here would strand the card's only control mid-tap.
 * The refusal string is the server's own words wherever there are any -- the
 * backend knows which exchange shard is short and where to fix it, and this
 * layer would only make that vaguer.
 */
export async function placeComboBid(input: {
  cardKey: string;
  legs: { event_ticker: string; market_ticker: string }[];
  priceTenths: number;
  stakeCents: number;
}): Promise<WriteResult<ComboBidResult>> {
  // **Not "nothing happened".** The request may have reached the exchange
  // and left a bid standing; telling him otherwise is how he places a
  // second one. The bid path is disarmed (ADR 0115); the words are kept for
  // the day it is re-armed.
  return postJson<ComboBidResult>({
    path: "/parlay-bid",
    body: {
      card_key: input.cardKey,
      legs: input.legs,
      price_tenths: input.priceTenths,
      stake_cents: input.stakeCents,
      combo_acknowledged: true,
    },
    shape: (body) => !!body && typeof body === "object" && "status" in body,
    noReply: (error) =>
      `The request did not reach the cockpit (${networkMessage(error)}). ` +
      "The bid may still have been placed — check the resting bids " +
      "panel and the Kalshi app before trying again.",
    unreadable: (status) =>
      `The cockpit's answer about the bid was not readable (HTTP ${status}). ` +
      "The bid may still have been placed — check the resting bids " +
      "panel and the Kalshi app before trying again.",
    noDetail: (status) => `The cockpit refused the bid (HTTP ${status}).`,
  });
}

/** Take a resting bid back. Same no-throw contract as placing one. */
export async function cancelComboBid(
  bidId: number,
): Promise<{ ok: true; words: string } | { ok: false; refusal: string }> {
  const result = await postJson<{ words: unknown }>({
    path: "/parlay-bid-cancel",
    body: { bid_id: bidId },
    shape: (body) => !!body && typeof body === "object" && "words" in body,
    noReply: (error) =>
      `The cancel did not reach the cockpit (${networkMessage(error)}). ` +
      "The bid may still be resting — check the Kalshi app.",
    unreadable: (status) =>
      `The cancel's answer was not readable (HTTP ${status}). The bid may ` +
      "still be resting — check the Kalshi app.",
    noDetail: (status) => `The cancel was refused (HTTP ${status}).`,
  });
  return result.ok
    ? { ok: true, words: String(result.value.words) }
    : { ok: false, refusal: result.refusal };
}

const LEG_VERDICT_MAX_LEGS = 8;

function legVerdictBody(body: unknown): LegVerdictsResult | null {
  if (
    !body ||
    typeof body !== "object" ||
    !Array.isArray((body as { legs?: unknown }).legs)
  ) {
    return null;
  }
  return { legs: (body as { legs: LegVerdict[] }).legs, error: null };
}

const UNREADABLE_LEG_VERDICTS =
  "The scouts' answer came back in a shape this screen cannot read.";

/**
 * Legs of `ticker` that bet against a ticket already held. A plain read that
 * spends nothing. **Never throws**: an unreadable answer is `null`, and the
 * screen then says nothing rather than "no clash".
 */
export async function fetchHeldConflicts(
  ticker: string,
): Promise<import("./types/hedge").HeldConflicts | null> {
  try {
    const response = await fetch(
      `${BASE}/api/held-conflicts?ticker=${encodeURIComponent(ticker)}`,
      { cache: "no-store" },
    );
    if (!response.ok) return null;
    const body = (await response.json()) as unknown;
    if (
      body &&
      typeof body === "object" &&
      Array.isArray((body as { conflicts?: unknown }).conflicts)
    ) {
      return body as import("./types/hedge").HeldConflicts;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Read whatever verdicts already exist for these legs. Spends nothing --
 * this is a plain `GET`, never the call that asks a seat to run.
 *
 * **Never throws.** A failed read renders "no scout read" beside the leg,
 * which is honest; a thrown promise would strand whatever called this with
 * nothing to show at all.
 */
export async function fetchLegVerdicts(
  legs: LegVerdictInput[],
): Promise<LegVerdictsResult> {
  if (legs.length === 0) return { legs: [], error: null };
  const qs = new URLSearchParams();
  for (const leg of legs.slice(0, LEG_VERDICT_MAX_LEGS)) {
    qs.append("leg", `${leg.ticker}:${leg.side}`);
  }
  let response: Response;
  try {
    response = await fetch(`${BASE}/api/leg-verdicts?${qs.toString()}`, {
      cache: "no-store",
    });
  } catch (error) {
    return {
      legs: [],
      error: `The scouts' read could not be reached (${
        error instanceof Error ? error.message : "network error"
      }).`,
    };
  }
  if (response.status === 503) return { legs: [], error: "Scouts are off" };
  if (!response.ok) {
    return { legs: [], error: `HTTP ${response.status}` };
  }
  const body: unknown = await response.json().catch(() => null);
  return legVerdictBody(body) ?? { legs: [], error: UNREADABLE_LEG_VERDICTS };
}

/**
 * Ask the leg scout to look at these legs, firing a verdict for any that has
 * none cached. Goes through the `/leg-verdicts` Next route handler so the
 * bearer token stays server-side -- same reasoning as `/scout-desk`, because
 * this spends metered Anthropic calls inside the shared `AgentBudget`.
 *
 * Fired from exactly three places, all trigger handlers
 * (`PriceOnKalshi.tsx`'s `tap`, `ParlayCards.tsx`'s `LegBuys` toggle and its
 * `AskTheScouts` button, the `card_button` trigger, which the page-level
 * `AskAllTheScouts` button also sends once per card) --
 * `tests/test_leg_verdicts_ui.py` pins that nothing else calls this, so a
 * mount effect or a re-render cannot spend on its own.
 *
 * **Never throws**, and never sends a price -- the server reads the ask
 * itself at request time so a stale or tampered client cannot shape the
 * question the seat answers.
 *
 * **The caller must keep the resolved result, not discard it (#155).** A
 * refused leg (budget spent, game started, no quote) writes no row by
 * design, so `<LegVerdicts>`'s GET poll alone would read `none` for it and
 * the panel would say "nobody has asked yet" about a leg the server just
 * explained. Each of the three callers now passes this promise's result to
 * `<LegVerdicts>` as `posted`, which overlays a posted `refused` row onto a
 * `none` GET row for the same leg.
 */
export async function requestLegVerdicts(
  legs: LegVerdictInput[],
  trigger: LegVerdictTrigger,
  cardKey: string | null,
): Promise<LegVerdictsResult> {
  if (legs.length === 0) return { legs: [], error: null };
  const sent = legs
    .slice(0, LEG_VERDICT_MAX_LEGS)
    .map((leg) => ({ ticker: leg.ticker, side: leg.side }));
  const result = await postJson<unknown>({
    path: "/leg-verdicts",
    body: { trigger, card_key: cardKey, legs: sent },
    noReply: (error) =>
      `The scouts could not be reached (${networkMessage(error)}). ` +
      "Nothing was sent.",
    unreadable: () => UNREADABLE_LEG_VERDICTS,
  });
  if (!result.ok) {
    if (result.status === 503) return { legs: [], error: "Scouts are off" };
    return { legs: [], error: result.refusal };
  }
  return (
    legVerdictBody(result.value) ?? { legs: [], error: UNREADABLE_LEG_VERDICTS }
  );
}

/** Read the stored cards: one game's, or every upcoming game's. */
export async function fetchGameCards(
  gameEventTicker?: string,
): Promise<GameScriptCards> {
  const query = gameEventTicker
    ? `?game_event_ticker=${encodeURIComponent(gameEventTicker)}`
    : "";
  const response = await fetch(`${BASE}/api/game-cards${query}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`the card list returned ${response.status}`);
  }
  return response.json() as Promise<GameScriptCards>;
}

/** How long one card build may take before the screen stops waiting. It does
 *  not stop the server: a build in flight still lands as a stored row. */
export const BUILD_CARD_WAIT_MS = 150_000;

/**
 * Build one game's card now, through the `/game-card` route handler so the
 * bearer token stays server-side. One metered model call; it can take about a
 * minute. **Never throws and never retries**: a timeout says the card may
 * still be building, because the build keeps going on the server.
 */
export async function buildGameCard(
  eventTicker: string,
): Promise<{ ok: true; reused: boolean } | { ok: false; refusal: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), BUILD_CARD_WAIT_MS);
  const answered = (status: number) =>
    `The card build answered HTTP ${status}.`;
  let result: WriteResult<unknown>;
  try {
    result = await postJson<unknown>({
      path: "/game-card",
      body: { event_ticker: eventTicker },
      signal: controller.signal,
      noReply: (error) => {
        const timedOut =
          error instanceof DOMException && error.name === "AbortError";
        return timedOut
          ? "The card is taking longer than this screen will wait. It may " +
              "still be building: reload the game in a minute before tapping again."
          : "The request did not reach the cockpit. The card may still be " +
              "building: reload the game before tapping again.";
      },
      unreadable: answered,
      noDetail: answered,
      tolerateEmptyBody: true,
    });
  } finally {
    clearTimeout(timer);
  }
  if (!result.ok) return { ok: false, refusal: result.refusal };
  const body = result.value;
  const reused =
    !!body && typeof body === "object" && (body as { reused?: unknown }).reused === true;
  return { ok: true, reused };
}
