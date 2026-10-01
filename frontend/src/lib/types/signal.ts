/**
 * Wire types for the recommendation, signal and gate screens.
 *
 * Types only (#262, ADR 0191 sec 2.5): `import type` and nothing at runtime, and
 * never an import from `api.ts`. `api.ts` re-exports every name here.
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

  /**
   * The Odds API market family the consensus was built from: `h2h`,
   * `spreads`, `totals`, or a prop key.
   *
   * Present so a screen can report the anchor base rate per (league, family).
   * Per league alone would pool populations that disagree — measured on live
   * 2026-09-16, NCAAF `h2h` anchored on a sharp book about 84% of the time
   * and NCAAF `spreads` about 30%.
   *
   * `null` means the join missed, and a row with a null family must be
   * counted as unknown rather than filed under any family.
   */
  consensus_market: string | null;
};

/**
 * The sweet spot: how much a number deserves to be acted on (ADR 0090).
 *
 * **Evidence quality, never bet quality.** Joe chose trust over edge on
 * 2026-08-31, and the reason is measured rather than stylistic: the
 * consensus-vs-Kalshi gap has `beta = -0.141`, so a score containing it would
 * rank the least trustworthy rows highest.
 *
 * **All three counts travel and the screen must use them.** `passed/total`
 * alone hides how many checks nobody ran; `passed/known` alone hides that
 * those checks exist. `total - known` is the number of unknowns, and an
 * unknown is never a pass. `components/TrustNote.tsx` is the one renderer —
 * three surfaces now carry this and a second drawing of it would be a second
 * set of honesty properties to keep in step.
 *
 * `null` when the server could not score honestly: no thresholds supplied (a
 * score against defaults would be a second definition of limits that live in
 * config), or the `fair_prices` join found nothing to read.
 */
export type TrustScore = {
  passed: number;
  known: number;
  total: number;
  checks: {
    name: string;
    state: "pass" | "fail" | "unknown";
    detail: string;
  }[];
};

export type Recommendation = Partial<DevigMethods> &
  Partial<ConsensusProvenance> & {
  id: number;
  ticker: string;
  created_ms: number;
  strategy_config_version: number;
  side: string;
  /**
   * The YES-side team, on BOTH rows of a market -- `kalshi_markets.
   * yes_side_team`. On a NO row this is the opponent of the side priced.
   * `null` on a prop or a total. Never print it as a NO row's name; see
   * `side_outcome` and `lib/rowSubject.ts` (ticket #6).
   */
  team: string | null;
  /**
   * The team (or "Over"/"Under") this row's OWN side pays on --
   * `fair_prices.outcome_name` on the row's `fair_price_id`, which the runner
   * binds per side. Optional: emitted by every route through `_serialise`
   * since 2026-09-02, so a backend one version behind omits it; `null` when
   * the route did not join `fair_prices` (the ledger) or the row has none.
   * Never falls back to `team` on a NO row -- that is the defect.
   */
  side_outcome?: string | null;
  event_title: string | null;
  /**
   * The odds feed's sport key for the linked fixture (`baseball_mlb`),
   * rendered through `leagueLabel`. Optional: sent by `/api/slate` and
   * `/api/board` since 2026-08-24; `null` on an unlinked row — render
   * nothing, never a guess.
   */
  league?: string | null;
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
   * the row was written and never move, which is right on Evidence (`/ledger`)
   * — there they are a historical fact about the observation — and dangerously
   * wrong on the Board, where a row from three hours ago still reads "quote 3s
   * ago".
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

export type GateCondition = { name: string; met: boolean; detail: string };

export type Gate = {
  open: boolean;
  conditions: GateCondition[];
  /** Every unmet condition, not just the first — the distance from open is the useful part. */
  reason: string;
  /** Derived from the venue's observed balance; null when never observed. */
  bankroll_dollars: number | null;
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

export type Ledger = {
  rows: Recommendation[];
  /**
   * Independent ACTIONABLE games scored on CLV: the gate's own population
   * (`clustered_clv(conn, "actionable")`), so this equals the Gate screen's
   * count. Not a row count, and not every scored game (#230).
   */
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
 * The two cuts a list screen may make (#15, Joe's option A): one league, by
 * the odds feed's sport key, and a kickoff window in hours. Both are sent as
 * query parameters the server validates -- `backend/list_filters.py` owns
 * the vocabulary, refuses an unknown value with a 422, and this file never
 * pre-validates so that a typo in the URL reaches the one validator rather
 * than being quietly dropped into "the whole list".
 *
 * **No third cut may be added here** without naming which of ADR 0071
 * section 2.5's two rules it does not break: a gap may be shown, never
 * ranked or cut by. There is no sort parameter, and there will not be one.
 */
export type ListFilter = {
  league: string | null;
  /** Sent verbatim: the server, not this file, decides what is an integer. */
  withinHours: string | null;
};

/**
 * The server's echo of the cut it applied -- present on `/api/slate` and
 * `/api/parlays` ONLY when a cut was applied; an unfiltered payload is
 * byte-identical to the pre-#15 one. `hidden` is how many rows (slate) or
 * candidate legs (ladder) the cut removed, so a short list under a filter
 * reads as cut rather than as a quiet night. The kickoff bounds are the
 * server's own milliseconds.
 */
export type ListFilterEcho = {
  league: string | null;
  within_hours: number | null;
  kickoff_from_ms: number | null;
  kickoff_until_ms: number | null;
  hidden: number;
};

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
   * declaring below 713 clusters (Amendment 2 section B4, which raised the
   * floor from 300 on 2026-08-29). `REFUSED` is different again: it means no
   * look happened at all.
   */
  verdict: "SIGNAL" | "BUG, NOT SIGNAL" | "NO SIGNAL" | "UNRESOLVED" | "REFUSED";
  /**
   * What section 6 returned on the pooled fit alone, before section A4's
   * leave-one-group-out downgrade. When it differs from `verdict`, a
   * pre-registered group's removal flipped the claim and the parts disagree.
   */
  section6_verdict: string;
  /** The group that caused the downgrade, named in A4's own words. */
  downgraded_by: string | null;
  /** Whether a declaring verdict stands: the cluster floor is met AND no
   * section A4 downgrade fired (#227). */
  may_declare: boolean;
  /** Amendment 2 section B6(5)'s sd ratchet check. `null` when nothing was
   * measured, never `false` in its place. */
  sigma_exceeds_ratchet: boolean | null;
  /** True once section 7's stopping rule has fired: the verdict is no longer
   * recomputed. */
  frozen: boolean;
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
    /**
     * Whether §P4/§7 narrowed the primary to one `strategy_config_version`.
     *
     * When true, `clusters` counts only that version's games — which is the
     * number the 300-game floor governs. It matters on the screen because the
     * two counts land on opposite sides of that floor: on 2026-08-25 the record
     * was 216 primary against 311 pooled, and the pooled one is what this
     * endpoint used to serve. A reader shown `clusters` without this flag
     * cannot tell which population the verdict is on.
     */
    modal_config_applied: boolean;
    modal_config_version: number | string | null;
    non_modal_rows_excluded: number;
    strategy_config_versions: Record<string, number>;
  };
  estimate: {
    /** Comes first because reading the effect first is how a small cell gets believed. */
    smallest_resolvable_beta: number;
    beta_hat: number;
    se_cluster: number;
    n_clusters: number;
    /**
     * Effective clusters -- Kish's count over the per-cluster leverage on
     * `beta`. **A reportable, never a threshold** (Amendment 2 section B7). It
     * sits inside `estimate` so a screen cannot render `n_clusters` without it:
     * on 2026-08-25 `G = 311` was **4.26** effective clusters, one WNBA game
     * carrying 43.8% of the leverage alone, and the screen that declared
     * NO SIGNAL on that count had no way to say so.
     *
     * `null` means the regressor has no residual variance -- not zero, and not
     * `n_clusters`.
     */
    g_eff: number | null;
    /** The biggest single game's share of the leverage. `null` if unreadable. */
    largest_cluster_leverage_share: number | null;
    n_rows: number;
    interval_lower: number;
    interval_upper: number;
    multiplier: number;
  } | null;
  /**
   * Section A4's leave-one-group-out table. Descriptive: it can turn SIGNAL or
   * NO SIGNAL into UNRESOLVED and can never raise a verdict, and no row here is
   * a finding. `one_group_result` marks an untestable group carrying more than
   * half the leverage, which A4 requires the write-up to state in those words.
   */
  a4_groups: {
    name: string;
    rows: number;
    clusters: number;
    leverage_share: number | null;
    clusters_remaining: number;
    testable: boolean;
    beta_hat: number | null;
    interval_upper: number | null;
    refusal: string | null;
    one_group_result: boolean;
  }[];
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

/**
 * How often each suppression rule fired.
 *
 * The shape is the route's, read before it was typed: `{"counts": {reason: n}}`,
 * already sorted by count descending server-side, with a row failing several
 * checks counted once under each. So the values sum to more than the number of
 * rejected rows, and that is correct rather than a bug to normalise away.
 */
export type Suppression = { counts: Record<string, number> };

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
