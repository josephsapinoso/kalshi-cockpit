/**
 * Wire types for the slate, board, exposure and odds-refresh screens.
 *
 * Types only (#262, ADR 0191 sec 2.5): `import type` and nothing at runtime, and
 * never an import from `api.ts`. `api.ts` re-exports every name here.
 */

import type { BookDistribution, LineShopData } from "./market";
import type { ListFilterEcho, Recommendation, TrustScore } from "./signal";

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
  /**
   * Counted by the gate, unbuyable at the deposit (ticket #25, Joe's 25C).
   *
   * No suppression reason, `reference_contracts > 0` — the gate's own
   * `actionable` test at the fixed $1,000 reference profile (ADR 0015 §3) —
   * and `suggested_contracts === 0`, because quarter-Kelly at the observed
   * balance buys none. Every row the gate has ever counted actionable had
   * this shape and was filed under `no_edge`, captioned "no edge after fees",
   * two inches below a headline counting it. Same flag as `suppressed` and
   * `no_edge`; empty without it. Nothing here is bettable, and a row that
   * sizes to a contract after a top-up leaves this list for `surfaced` on its
   * own.
   */
  sized_to_zero: Recommendation[];
  counts: {
    surfaced: number;
    expired: number;
    suppressed: number;
    sized_to_zero: number;
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
    /**
     * The bankroll `reference_contracts` and `actionable_total` are sized at
     * (`REFERENCE_BANKROLL_DOLLARS`, ADR 0015 §3). Read off the server so the
     * SIZED TO ZERO caption prints the figure the gate uses, not a literal.
     */
    reference_bankroll_dollars: number;
    older_than_window: number;
  };
  note: string;
};

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
   * decide when to look.
   *
   * **The comment here used to claim the page could not disagree with the
   * loop, and on 2026-08-28 at 04:38Z it did** — the panel said "the next
   * scheduled sweep is now" in the same minute the loop logged its refusal of
   * that exact sweep. The guarantee was true of the slot schedule and false of
   * the budget: the attention slice is checked *after* the desk predicate has
   * said a call is wanted, so this field answered "is a call wanted?" and the
   * screen rendered it as "is a call coming?". Ticket #35.
   *
   * What is true now: the server applies the slice as well, so a time here is
   * one the loop can serve, and when the slice is spent the desk contributes
   * nothing to it. That makes `null` ambiguous on its own — read
   * `attention_slice_spent`, `next_desk_buy_ms` and `floor_next_buy_ms` beside
   * it before writing a sentence about why nothing is coming.
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
  /**
   * Credits spent today on **attention-triggered** sweeps, and the ceiling
   * they are measured against (`ODDS_ATTENTION_DAILY_CREDITS`, 300 of the
   * day's 700 on live).
   *
   * A separate pool from `spent_today`/`daily_budget`. The odds feed follows
   * attention over an hourly floor (ADR 0071 §2.6); this slice is what a page
   * left open is allowed to spend, and the floor is deliberately not charged
   * to it.
   */
  attention_credits_spent: number;
  attention_daily_credits: number;
  /**
   * When today's attention slice ran out, or `null` if it has not.
   *
   * The `called_ms` of the buy that took the pool to its ceiling. `null` is
   * also the honest answer on a day the slice is spent with nothing ever
   * bought under the trigger, so the copy must degrade to a sentence with no
   * time in it rather than rendering an epoch.
   */
  attention_slice_spent_at_ms: number | null;
  /** Whether the slice can no longer fund one more sweep. */
  attention_slice_spent: boolean;
  /** Whether a heartbeat has landed inside the TTL — i.e. someone is looking. */
  desk_is_attended: boolean;
  /**
   * When the **desk trigger** will next actually buy, at the cadence holding
   * right now. `null` means it wants nothing at all.
   *
   * **The awkward part was retired on 2026-08-29 and the retraction is worth
   * more than the fact.** This comment used to say attention *replaces* the
   * hourly floor rather than adding to it — every upcoming sport wanted on the
   * ten-minute cadence, every one refused once the slice was spent, no
   * fall-through — so past the slice, keeping the page open was what
   * suppressed the buying and closing it was what let the floor resume. The
   * loop now demotes the sport to the floor's own cadence instead of skipping
   * it, so this field carries an hourly time in the state where it used to
   * carry `null`. What must never appear here again is the *ten-minute*
   * answer while the slice is spent: that is the ticket #35 defect, a screen
   * promising a buy the loop has already refused.
   */
  next_desk_buy_ms: number | null;
  /**
   * When the **hourly floor** next wants a buy, ignoring the slice the floor
   * is never charged to.
   *
   * A **lookahead** rather than a snapshot, which is what makes it a separate
   * field from `next_desk_buy_ms`: a sport enters the floor's twelve-hour
   * horizon at `kickoff - 12h`, so at 04:38Z with an 18:20Z kickoff this reads
   * ~06:20Z while the desk wants nothing at all. That is the sentence the
   * 2026-08-28 screen could not write. `null` means no stored fixture ever
   * brings the floor round, which is a different state again.
   *
   * It used to be the "once you stop looking" answer and is not any more —
   * the floor runs while the page is open. Copy that reads this field must
   * not make going away a condition of it.
   */
  floor_next_buy_ms: number | null;
  /**
   * How long the recording loop sleeps between full passes when nothing
   * wakes it — `RUNNER_INTERVAL_S` as the entrypoint passes it, 900s on live.
   *
   * Published so a silence in `last_look_ms` is judged against the cadence
   * that produced it. Until 2026-09-03 `nextOddsWindow.ts` called the loop
   * stalled after a hardcoded 180s, a number written when the observed
   * cadence was a pass every ~18s — the FAST cadence, which runs only while
   * a window is open. Idle, the loop sleeps this long, so on 8 of 26
   * measured cold opens the screen called a sleeping loop a fault and
   * switched off the self-heal thirteen seconds before the buy it was
   * waiting for landed.
   *
   * `null` means the interval could not be read. A reader given `null` may
   * not call the loop stalled on `last_look_ms` alone — unknown is not a
   * number, and least of all is it `0`.
   */
  loop_idle_interval_ms: number | null;
  note: string;
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
  /**
   * How often a taker at this ask must win to break even, fee included —
   * `breakeven_win_rate(ask, 1)` on the server, never recomputed here (the
   * fee curve stays in one implementation). **Deliberately unaccompanied:**
   * `edge_tenths` is exactly `1000 × (fair − this)`, so a screen that puts
   * the consensus fair value beside it hands the reader the measured-negative
   * edge by subtraction. `null` when the ask is not a tradeable price.
   */
  breakeven_win_rate: number | null;
  /**
   * The sweet spot for this row (ADR 0090). Optional because a deployed
   * backend one version behind omits the key entirely; `null` when the server
   * had nothing honest to score — see `TrustScore`.
   */
  trust?: TrustScore | null;
  /**
   * Same opinion, cheaper way round (#245): present only when the other route
   * is cheaper after fees. A fact on the row, never a sort key (ADR 0071).
   */
  line_shop?: LineShopData | null;
};

/**
 * One entry in the "who's likely to win tonight" block (ADR 0067): the side
 * the devigged consensus makes the favorite, ranked server-side by
 * `fair_probability` alone — one stored, unscored column, a sort and never a
 * composite. **No breakeven, edge, or size field exists here**, structurally:
 * fair% beside break-even hands the reader the measured-negative edge by
 * subtraction (the fleet-convening identity), so the two never share a block.
 * `ask_display` is null when the stored quote is no longer current — a price,
 * never a souvenir.
 */
export type SlatePick = {
  ticker: string;
  event_title: string | null;
  team: string | null;
  /** Sport key of the linked fixture; optional for a backend one version behind. */
  league?: string | null;
  side: string;
  commence_ms: number | null;
  fair_percent_display: string | null;
  ask_display: string | null;
  /**
   * How old the recorded Kalshi quote is, on the server's clock at the
   * request (`_live_ages`). Served whether or not `ask_display` survived, so
   * a row whose ask was withheld can say how stale it is and what to do
   * about it (#47). `null` is an unreadable clock and renders as nothing --
   * never "0 min". Optional for a backend one version behind.
   */
  quote_age_now_ms?: number | null;
  /**
   * How long ago the game started, on the server's clock; `null` when the
   * fixture is unknown or still ahead (#42, the Picks half). A fact the row
   * wears, never a sort key: the order is `fair_probability` alone
   * (ADR 0067). Optional for a backend one version behind.
   */
  started_ago_ms?: number | null;
  anchored_on_sharp: boolean | null;
};

export type SlatePicks = {
  ranked: SlatePick[];
  /** Games counted out by name — "no pick" and "no measurement" are
   *  different facts. */
  not_ranked: {
    stale_consensus: number;
    favorite_unpriced: number;
    /** Distinct player-prop MARKETS in the window, never ranked here
     *  (ticket #23): a prop shares its game's fixture id and would otherwise
     *  be printed as the game's likely winner under the player's name.
     *  Optional for a backend one version behind. */
    props_excluded?: number;
  };
  /** The chance≠edge sentence, rendered verbatim so the server and the
   *  screen cannot disagree about what this block claims. */
  note: string;
};

export type Slate = {
  /** One flat list in kickoff order. No bucketing by verdict — that is the
   *  point: edge is a column here, not a gate. */
  rows: SlateRowData[];
  /** The #15 cut, echoed. Absent when the list was not cut. */
  filter?: ListFilterEcho;
  /** Optional because a deployed backend one version behind omits it. */
  picks?: SlatePicks | null;
  /**
   * The venue's own reading of Joe's money: cash and the value sitting in
   * open positions, **separately and never summed** — a sum would sign a
   * P&L, and a signed P&L on the screen where bets are decided is the chase
   * trigger the tilt review refused.
   *
   * The caps are derived server-side, at request time, from the observed
   * balance (ADR 0045) and arrive as display strings — this file's rule:
   * no money arithmetic in the frontend. `caps_basis` is never omitted:
   * it carries either the balance the caps were derived from or the
   * refusal words ("balance unobserved") the screen must render instead
   * of rendering nothing. `deposit_for_50c_display` is the server-computed
   * deposit arithmetic ("one contract at 50c needs a $5.00 balance").
   * `null` money only from a backend one version behind.
   */
  money: {
    observed_ms: number | null;
    cash_tenths: number | null;
    cash_display: string | null;
    open_positions_tenths: number | null;
    /** @deprecated render `daily_line_display`; kept for older readers. */
    daily_line_dollars: number | null;
    daily_line_display: string | null;
    per_bet_cap_display: string | null;
    exposure_cap_display: string | null;
    deposit_for_50c_display: string;
    caps_basis: {
      balance_display: string | null;
      observed_ms: number | null;
      refusal: string | null;
    };
  } | null;
  counts: {
    returned: number;
    /** Rows a book distribution could be computed for. Its own number because
     *  "no book disagreed" and "no book price stored" render identically. */
    with_book_distribution: number;
    surfaced: number;
  };
  /**
   * Tonight's commitment (2026-08-21 ruling): unsigned count and stake from
   * the fills mirror since the day roll, a SIBLING of `money` because
   * `money`'s contract is about never summing. `bets`/`staked_*` are null —
   * never 0 — when the mirror is stale (`as_of_ms` old or absent). Optional
   * because a deployed backend one version behind omits the key entirely.
   */
  tonight?: TonightActivity | null;
  /** A sibling of `money` for `tonight`'s reason: `money`'s contract is
   *  about never summing cash and positions. See `OpenPositionsBlock`. */
  open_positions?: OpenPositionsBlock | null;
  staleness: { max_kalshi_quote_age_s: number; max_odds_age_s: number };
  slate: Board["slate"];
  drift_window_ms: number;
  note: string;
};

export type TonightActivity = {
  day_start_ms: number;
  as_of_ms: number | null;
  bets: number | null;
  staked_tenths: number | null;
  staked_display: string | null;
  lockout_until_ms: number | null;
};

/**
 * What is open at the venue right now — the largest hole of the 2026-08-22
 * review (nothing showed what was at risk on any screen). Served on the
 * slate and on /bets from the only two things the mirror carries:
 *
 * - `count` is the positions poll's row count, **counted and never
 *   parsed** (the per-row wire shape has never been observed), on the
 *   12-hour mirror clock — stale refuses to null with `count_as_of_ms`
 *   kept so the screen renders "not read since".
 * - `value_*` is the venue's own `portfolio_value` (5-minute cadence),
 *   whose unit is pinned only at zero — any non-zero value refuses with
 *   its reason in `value_refusal`, server-rendered words.
 *
 * **The two stamps are not interchangeable.** `count_as_of_ms` is the
 * mirror's clock, and because the mirror's first cycle runs at process
 * start and no container here lives twelve hours, it is in practice the
 * container's boot time. `value_as_of_ms` is minutes fresh. Each figure is
 * stamped with its own read (`lib/openPositionsStamps.ts`) — until
 * 2026-08-29 the dollars-at-risk figure wore the count's boot clock.
 *
 * `*_age_ms` is each read's age against the same server `now_ms` the
 * staleness bounds use, so the screen never subtracts a server millisecond
 * from a browser one. Optional: a deployed backend one version behind omits
 * them, and the clock alone still renders.
 *
 * - `staked_*` is what Joe asked /bets to say (21A): the money on the
 *   positions open now, unsigned. **It is refused, in server-rendered words
 *   (`staked_refusal`), and the words say why** -- the fills mirror does not
 *   record buy against sell, and a settled position the mirror missed would
 *   read as still open, so no honest figure exists in the record today. Null,
 *   never $0.00, until the poller stores what would pin it
 *   (`backend/bets.py::open_positions`). Optional because a deployed backend
 *   one version behind omits the keys.
 *
 * NO live P&L, no mark-to-market, never summed with cash (TonightStrip's
 * unsigned rule). Optional because a deployed backend one version behind
 * omits the key entirely.
 */
export type OpenPositionsBlock = {
  count: number | null;
  count_as_of_ms: number | null;
  count_age_ms?: number | null;
  value_tenths: number | null;
  value_display: string | null;
  value_as_of_ms: number | null;
  value_age_ms?: number | null;
  value_refusal: string | null;
  staked_tenths?: number | null;
  staked_display?: string | null;
  staked_refusal?: string | null;
};

/**
 * `GET /api/exposure` — how deep Joe already is, and nothing else.
 *
 * **A separate route from `/api/bets` on purpose.** `/api/bets` serves the
 * same `open_positions` block, and also 200 settled rows, the pass summary
 * and the lockout clock. `<ManualTicket>` opens this on seven surfaces, beside
 * a live Kalshi book read, so the buy button waits on the cheapest possible
 * read (`backend/api/routers/ledger.py`).
 *
 * `open_positions` is the same `OpenPositionsBlock` the slate and /bets carry,
 * passed through unshaped. `as_of_ms` is the server clock its `*_age_ms`
 * fields were subtracted against — no browser millisecond is ever subtracted
 * from a server one.
 */
export type Exposure = {
  as_of_ms: number;
  open_positions: OpenPositionsBlock;
};

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
 *   refused   some other rule fired, or the sizer left the row at zero
 *             contracts. Caution, never money — the number is a record of
 *             what the arithmetic said, not an offer.
 *   positive  nothing refused it, the edge survives fees, and the size is
 *             at least one contract.
 *   negative  nothing refused it and there is no edge.
 *
 * Shared rather than written per screen because a suppressed row reaches the
 * eye down more than one path — the Board's slate rows and Evidence — and a
 * second copy of this rule is a second chance to render green over a defect.
 */
export type EdgeTone = "suspect" | "refused" | "positive" | "negative";

/** What `POST /api/odds/refresh` answers with. */
export type OddsRefreshResult = {
  accepted: boolean;
  detail: string;
  estimated_credits: number;
  retry_after_ms: number;
};

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
  /** Credits one fixture's props cost — including the team call that finds
   * it. `null` when this desk has no prop markets for the sport (#37): the
   * server refuses such a tap, so there is no price to show. */
  prop_credits: number | null;
  /** Whether a prop tap on this sport can buy anything. The only prop keys
   * the desk requests are baseball markets. */
  prop_markets_available: boolean;
  fixtures: RefreshableFixture[];
};

/**
 * A league with no fixture inside the card's 24-hour horizon, and the first
 * one it has stored past it. Absent (not null) for a league with nothing
 * stored at all, and absent for a league that is in `sports` -- the card
 * lists that league's taps instead.
 */
export type RefreshableBeyondHorizon = {
  sport_key: string;
  odds_event_id: string;
  commence_ms: number;
  /** When this fixture enters the tap list: kickoff less the horizon. */
  enters_ms: number;
  title: string;
};

export type Refreshable = {
  sports: RefreshableSport[];
  beyond_horizon: RefreshableBeyondHorizon[];
  manual_daily_credits: number;
  /** What today's taps have already reserved against that ceiling. Counted at
      accept time, served or not, so it can only overstate — the safe error. */
  manual_credits_spent_today: number;
  /** The whole day's metered budget beside the taps' slice of it. */
  day_credits_spent: number;
  day_credits_budget: number;
  day_credits_remaining: number;
  cooldown_ms: number;
  note: string;
};
