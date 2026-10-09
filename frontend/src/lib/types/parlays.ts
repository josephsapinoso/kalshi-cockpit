/**
 * Wire types for parlays: cards, lookups, RFQ, game legs, leg verdicts and game-script cards.
 *
 * Types only (#262, ADR 0191 sec 2.5): `import type` and nothing at runtime, and
 * never an import from `api.ts`. `api.ts` re-exports every name here.
 */

import type { ListFilterEcho, TrustScore } from "./signal";

/** One leg of a parlay card: a game's YES side at its consensus chance. */
/**
 * One leg, with the provenance behind its number.
 *
 * Until 2026-08-26 this carried `fair_percent_display` and nothing else — one
 * number standing in for three separate choices (which devig method, which
 * books, how far the field spreads) on a screen that offers money decisions.
 * The slate row has shown all three since ADR 0051.
 *
 * **Every added field is nullable and `null` never means zero.** An ask of 0
 * is a free contract on an empty book, a book count of 0 is "no consensus",
 * and neither is what "we could not read it" means. Render an em-dash.
 */
export type ParlayCardLeg = {
  ticker: string;
  event_ticker: string;
  event_title: string;
  /** The team whose YES this is. `null` on a player prop and on a total,
   *  which have no team -- the card draws `event_title` under those. */
  team: string | null;
  /** The player, on a prop leg only. Never a stand-in for `team`. */
  player: string | null;
  label: string;
  league: string;
  commence_ms: number;
  market: string;
  point: number | null;
  /** Which side of `ticker` this leg buys: "no" is the Under of a total or
   *  prop, the NO of Kalshi's Over market. Echoed back on the lookup tap. */
  side: "yes" | "no";
  fair_percent_display: string;
  /** Kalshi's derived ask. `null` when the book is one-sided — no price to pay. */
  ask_display: string | null;
  depth_at_ask: number | null;
  quote_age_ms: number | null;
  /** How far the four devig readings sit apart. `null` on fewer than two. */
  method_spread_display: string | null;
  /** Books surviving ANCHORING, often far fewer than quoted. */
  book_count: number | null;
  books_used: string[];
  market_width_display: string | null;
  /**
   * **Not a quality mark.** A sharp anchor selects at most three books, so it
   * is a thinner fair value rather than a better one (CLAUDE.md). Word it
   * neutrally or not at all.
   */
  anchored_on_sharp: boolean | null;
  odds_age_ms: number | null;
  /**
   * `checked` — a recommendation row exists and its verdict stands.
   * `not_on_this_path` — a spread leg; ADR 0070 keeps spread rows off the
   *   recommendations path, so the checks did not run and never will.
   * `absent` — a moneyline the engine has not priced.
   *
   * The third value exists because rendering `not_on_this_path` as a blank
   * would read as "the checks passed", which is the flattering misreading of
   * a measurement that never happened.
   */
  skeptic: "checked" | "not_on_this_path" | "absent";
  suppressed_reason: string | null;
  /**
   * The sweet spot: how much this number deserves to be acted on.
   *
   * **Evidence quality, never bet quality.** Joe chose trust over edge on
   * 2026-08-31, and the reason is measured rather than stylistic: the
   * consensus-vs-Kalshi gap has `beta = -0.141`, so a score containing it
   * would rank the least trustworthy rows highest.
   *
   * **All three counts travel and the screen must use them.** `passed/total`
   * alone hides how many checks nobody ran; `passed/known` alone hides that
   * those checks exist. `total - known` is the number of unknowns, and an
   * unknown is never a pass.
   *
   * `null` when the caller supplied no thresholds — a score computed against
   * defaults would be a second definition of limits that live in config.
   */
  trust: TrustScore | null;
  /**
   * The four devig readings plus the one the card took, for `DispersionStrip`.
   *
   * **Every key is present; an unsolved method is `null`.** `dispersion.ts`
   * gives absent and `null` different meanings — absent means the route never
   * joined `fair_prices`, `null` means the join ran and that method did not
   * solve. A parlay leg always comes from `fair_prices`, so nothing here is
   * ever absent, and a consumer can rely on that.
   *
   * Shaped to match `DispersionMethods` exactly so it passes through
   * untouched. A rename on either side draws an empty strip with no error.
   */
  methods: {
    p_multiplicative: number | null;
    p_additive: number | null;
    p_power: number | null;
    p_shin: number | null;
    p_conservative: number | null;
  };
  /**
   * Kalshi's derived ask as a probability. `null` when unreadable, never 0 —
   * a 0 ask is a free contract and a real price.
   *
   * Drawn as a neutral tick and nothing more: ADR 0071 §2.5 permits the two
   * prices side by side, and forbids a direction on this one.
   */
  ask_probability: number | null;
  /**
   * What the scout desk knows about this leg's GAME.
   *
   * Joe's ruling, 2026-08-30: the Scout gates eligibility and flags, and
   * **never moves the price**. Nothing here is an input to any number on the
   * card, and ADR 0071 §2.5 forbids ranking by it — a flag may be shown on a
   * leg and must never sort one.
   *
   * `absent` is the ordinary case, not a fault. `AGENT_MAX_SEARCHES_PER_DAY`
   * allows five convenings a day, so most legs will never have been scouted.
   *
   * `briefing` — the desk is out now.
   * `briefed` — it filed something.
   * `filed_nothing` — it looked and had nothing to say. Not the same as
   *   `absent`, which means nobody looked.
   * `refused` — a ceiling turned it away. Not information about the game.
   * `failed` — it died, or filed content that will not parse.
   */
  scout:
    | "briefed"
    | "filed_nothing"
    | "briefing"
    | "refused"
    | "failed"
    | "absent";
  scout_headline: string | null;
  /** Board tiles that are NOT `clear` — findings AND gaps. See `ScoutFlags`. */
  scout_flags: { category: string; state: string; note: string }[];
  scout_age_ms: number | null;
  /** The market ticker the briefing was filed against, for a link to it. */
  scout_ticker: string | null;
  /**
   * Each team's rest before this game (#201). A per-row fact: never sorted,
   * filtered or ranked by. `null` when the game could not be identified;
   * optional so older fixtures still type.
   */
  rest?: LegRest | null;
};

/** One team's rest. Every field is `null` when no previous game is on record. */
export type TeamRest = {
  team: string | null;
  days_rest: number | null;
  /** Nightly leagues (basketball, hockey) only; `null` elsewhere. */
  back_to_back: boolean | null;
  /** NFL / NCAAF only; `null` elsewhere. */
  short_week: boolean | null;
};

/** Both teams of the leg's game. A prop leg shows both: the player's team is not on the leg. */
export type LegRest = { home: TeamRest; away: TeamRest };

/**
 * The chance the first N legs ALL land, for N = 1..legs.
 *
 * The plain product, not the card's headline. The headline joint adds a small
 * same-day correlation nudge through a seeded copula; the difference is
 * `independence_error_points`, stated in `correlation_note`. Re-running the
 * copula at every prefix would be six more 200,000-sample runs per card for a
 * difference in hundredths of a point.
 */
export type ParlayPrefix = {
  legs: number;
  /** For plotting. The display string beside it is what gets printed. */
  chance: number;
  chance_percent_display: string;
};

/** One preset stake, fully priced server-side (the no-arithmetic rule). */
export type ParlayStake = {
  stake_cents: number;
  stake_display: string;
  contracts_display: string;
  payout_display: string;
  is_default: boolean;
};

export type ParlayCardJoint = {
  /** Chance at each prefix, for the difficulty chart. */
  prefixes: ParlayPrefix[];
  conservative_percent_display: string;
  /** The raw joint, 0-1. The bid field's reference price comes from this. */
  conservative: number;
  method_range_display: string | null;
  /**
   * The break-even price in American odds — what a sportsbook must offer to
   * match the consensus (ADR 0085). `null` when the joint is not a
   * probability. Break-even, not a target: at exactly this number the bet is
   * fair and its expected profit is zero.
   */
  price_to_beat_display: string | null;
  fair_cost_display: string;
  correlation_note: string;
};

/**
 * The card-level scouting rollup (ticket #110, ADR 0088): what the desk
 * already knows about this card's legs' games, built server-side from the
 * legs' own `scout`/`scout_flags`/`scout_age_ms` fields — zero new queries,
 * zero credits.
 *
 * **Nothing here is an input to any number on the card, and nothing here
 * may order anything** — the same ADR 0071 §2.5 rule that governs a single
 * leg's scout fields applies to this rollup with the same force.
 */
export type ParlayCardScouting = {
  legs_total: number;
  /** Legs whose game is `briefed` or `filed_nothing` — the desk LOOKED. */
  legs_briefed: number;
  /**
   * Labels of legs whose game is `absent`, `refused`, or `failed` —
   * "nobody looked", never "nothing found" (ADR 0088).
   */
  legs_dark: string[];
  /** Labels of legs whose game the desk is briefing RIGHT NOW. */
  legs_out: string[];
  /** The oldest of the BRIEFED legs' ages, or `null` when none are briefed. */
  oldest_briefing_age_ms: number | null;
  /** Union of non-`clear` tile categories across the briefed legs, sorted. */
  flag_categories: string[];
  /** The server-worded summary — render this, not a client-built sentence. */
  words: string;
};

/** One rung of the ladder. Either `legs` is populated or `not_built_reason` says why not. */
export type ParlayCardData = {
  key: string;
  title: string;
  /** One server-worded line saying which cut of the pool this card is. */
  what_it_is: string;
  legs: ParlayCardLeg[];
  not_built_reason: string | null;
  joint: ParlayCardJoint | null;
  at_stakes: ParlayStake[];
  /** `null` on an unbuilt card — nothing was built, so nothing was looked at. */
  scouting: ParlayCardScouting | null;
};

/**
 * The parlay desk's ladder (ADR 0070). Everything is FAIR value — what the
 * combination is worth by the books' consensus — never Kalshi's own quote,
 * which exists only once the combo is built. The four `notes` sentences are
 * the payload's own honesty copy and render verbatim.
 */
/**
 * The server's echo of the window it used. Rendered verbatim: every
 * `not_built_reason` and every exclusion count is relative to THIS window,
 * so a label the screen derived itself could print "tonight" over
 * tomorrow's numbers.
 */
export type ParlayWindow = {
  key: ParlayHorizon;
  words: string;
  ends_ms: number;
  choices: { key: ParlayHorizon; words: string }[];
  /**
   * Present only when the SERVER widened the window because the reader named
   * none and the narrower one built no card at all. Absent when the reader
   * picked the window himself, and absent when `tonight` built something.
   *
   * The distinction matters on screen: a window the desk chose has to say so,
   * or the reader reads tomorrow's cards as the ones he asked for. Never
   * derived here — a client that inferred "widened" from `key !== "tonight"`
   * would also flag every window the reader deliberately picked.
   */
  widened_from?: ParlayHorizon;
  /** The server's sentence for why, including that it cannot settle tonight. */
  widened_words?: string;
};

export type ParlayLadder = {
  generated_ms: number;
  window?: ParlayWindow;
  cards: ParlayCardData[];
  excluded: Record<string, number>;
  /**
   * Present only when EVERY widening window built nothing (#279): what the
   * widest window tried left out, so the screen can say why instead of
   * "the slate has 0". `stale_consensus` is that window's stale-side count.
   */
  all_windows_empty?: {
    widest_key: string;
    widest_words: string;
    excluded: Record<string, number>;
    stale_consensus: number;
  };
  notes: {
    chance: string;
    fair_value: string;
    unquoted: string;
    /** What a "Price on Kalshi" tap has actually returned, as a lifetime
     *  rate. One overall figure, never per card: per-card counts are 2-30
     *  and would read as an ordering (ADR 0156). */
    tap_outcome: string;
    fee: string;
  };
  /** The #15 cut, echoed. Absent when the pool was not cut. */
  filter?: ListFilterEcho;
};

/**
 * The kickoff window the cards are built from (2026-09-06).
 *
 * **Not a filter.** `ListFilter` only NARROWS the pool; this moves its upper
 * bound, which is why it is a separate parameter rather than another field
 * on the cut. `null` means "say nothing" and the server applies its own
 * default -- the screen never spells the default itself, so there is one
 * place it can change.
 */
export type ParlayHorizon = "tonight" | "tomorrow" | "48h";

/** What "Price on Kalshi" came back with. Strings are server-worded. */
export type ParlayLookupResult =
  | {
      status: "priced";
      minted_market_ticker: string;
      quoted: {
        ask_display: string;
        depth_display: string | null;
        /**
         * What the stake buys, BOUNDED BY WHAT IS RESTING. `contracts` and
         * `payout` are null when the book's depth is unreadable — a payout
         * you may not be able to buy is not a payout, and on an enter-only
         * market a lone stale bid manufactures a large one (CLAUDE.md rule
         * 1). `depth_note` says why, whenever there is something to say.
         */
        at_stake: {
          stake_display: string;
          contracts_display: string | null;
          cost_display: string | null;
          payout_display: string | null;
          depth_note: string | null;
        };
        /**
         * When this book was read, epoch ms. Every other price surface on the
         * desk has carried a clock since ADR 0092 (`quote_age_now_ms`,
         * `price_is_current`); this one did not, and it is the only one that
         * has been transacted through.
         *
         * **What goes stale is the VERDICT, not the price paid.** The buy
         * route re-fetches Kalshi at the tap and builds the order at that
         * live ask, so an old read here cannot cause a surprising fill — it
         * causes a surprising refusal, or a fill inside a generous ceiling
         * whose EV was never what this said.
         */
        quoted_ms: number;
        /**
         * How old a quote may be and still count as current, from the server's
         * own `MAX_KALSHI_QUOTE_AGE_S`. Carried rather than duplicated here:
         * two surfaces holding their own copy is how they drift into
         * disagreeing about the same book. `null` when the server named none,
         * and then the age is shown and nothing is marked.
         */
        quote_max_age_ms: number | null;
      };
      fair: {
        conservative_percent_display: string;
        fair_cost_display: string;
      };
      hold_display: string;
      verdict: string;
      /**
       * The fee coefficient the Take-it button's all-in cost uses (#334).
       * Absent on an older payload; then the cost line derives `k` from a
       * served quote or leaves the fee clauses out.
       */
      fee_coefficient?: number | null;
      notes: { unquoted: string; fee: string };
    }
  | { status: "book_empty"; minted_market_ticker: string; words: string }
  | { status: "no_collection"; words: string }
  /**
   * The legs are real Kalshi markets that Kalshi will not COMBINE — they
   * appear in no combination collection. A different refusal from
   * `no_collection`, which means no collection would take the card's shape at
   * all; this one names the individual games, because "five of your six games
   * cannot be parlayed here" is actionable and "invalid parameters" is not.
   */
  | {
      status: "legs_not_combinable";
      words: string;
      absent_event_tickers: string[];
    };

/**
 * Price one card's combination on Kalshi (ADR 0070). Goes through the
 * `/parlay-lookup` route handler so the bearer token stays server-side.
 * The tap mints a real market on the exchange (no money moves); refusals
 * come back as words, rendered verbatim.
 *
 * **Never throws** — `refreshOdds`'s pattern, for the same reason. This
 * function's caller renders a single button that unmounts while the request
 * is in flight, so a rejected promise leaves the card saying "Asking
 * Kalshi…" with nothing to tap. Both failure shapes are covered: the fetch
 * itself (no connection) and an unreadable body on the ok path (a proxy
 * page with a 200). A dropped connection is NOT the same as nothing
 * happening — the POST may have reached Kalshi and minted the market — so
 * the words say so rather than inviting a blind retry.
 */
/** One maker's private offer on a combination, as `/api/parlays/rfq` sends it. */
export type ComboRfqQuote = {
  quote_id: string;
  /**
   * What one contract of YES costs, in integer tenths of a cent. DERIVED
   * server-side as the complement of the maker's NO bid, because Kalshi
   * publishes bids and a resting NO bid IS the ask you buy at.
   */
  yes_ask_tenths: number;
  no_bid_tenths: number;
  contracts: number | null;
  /** Rendered server-side, through the ONE price renderer. */
  ask_display: string;
  /**
   * What leaves the account if this quote is taken, in integer tenths of a
   * cent, **fee included** — the contracts plus Kalshi's combination taker
   * fee, which is charged on top of them.
   *
   * Null when the size could not be read. A quote with no size has an
   * unknown cost, and the button says nothing rather than printing the
   * contracts alone, which would be a smaller and friendlier wrong number.
   */
  all_in_tenths: number | null;
  /** The same figure as dollars, through the ONE dollar renderer. */
  all_in_display: string | null;
  /** The fee alone, so the screen can say what the difference is made of. */
  fee_tenths: number | null;
};

export type ComboRfqResult = {
  /**
   * Three outcomes, not two.
   *
   * `priced_too_finely` means makers DID answer and every price was finer
   * than a tenth of a cent -- the hundredth-cent region combinations quote
   * near 0c and 100c. The desk refuses such a price rather than rounding it
   * onto the money path, so there is a real price that this screen is not
   * showing, and the Kalshi app will show it. It used to arrive as
   * `no_quotes`, which rendered as "nobody quoted this combination" (#73).
   */
  status: "quoted" | "no_quotes" | "priced_too_finely";
  /**
   * How many distinct makers were dropped on price precision.
   *
   * Counted by quote id across the whole poll loop, not per read: the same
   * refused quote comes back on every poll, so a per-read count would say
   * six makers answered when one did.
   */
  refused_too_fine: number;
  /**
   * The refused quotes' own prices, cheapest first (#291, Joe's (A) to
   * #273): the venue's exact decimal and its cents display. Shown, never
   * takeable -- no quote id is served, so nothing can be accepted from it.
   */
  refused_too_fine_quotes?: {
    yes_ask_dollars: string;
    ask_display: string;
    contracts: number | null;
  }[];
  rfq_id: string;
  market_ticker: string;
  /**
   * What the VENUE was actually asked for -- not always what Joe typed.
   *
   * `create_rfq` reuses an open RFQ whenever its target is at least the one
   * wanted, and this desk holds RFQs open so the accept stays reachable. So
   * asking at $1.00 and then at $5.00 returns the $1.00 request, with quotes
   * sized for $1.00. This field used to report the typed figure (#72).
   */
  target_cost_dollars: string;
  /**
   * What Joe typed. Equal to the above in the ordinary case.
   *
   * When they differ, the venue was never asked at the larger number and
   * `words` leads with a sentence saying so -- said only on the divergence,
   * because a warning that is always on is one that gets skipped.
   */
  target_cost_requested: string;
  fair: { conservative: number | null };
  /** The same fair value as a string, or null when it was unreadable. */
  fair_display: string | null;
  /**
   * What the PUBLIC order book said at the same instant, or null.
   *
   * Null is the expected value and means the book carried no ask -- the
   * normal resting state of a combination, not a fault. It is the number
   * that made this desk tell Joe a combination could not be bought.
   */
  book_yes_ask_tenths: number | null;
  /**
   * The same number rendered, or null when the book was empty.
   *
   * Shown BESIDE the maker's quote, never instead of it: measured
   * 2026-09-17, the public book beat the RFQ on two of three held
   * combinations and the RFQ was the only price on the third. A desk
   * reading one surface sometimes reports no price when there is one, and
   * sometimes takes the worse of two.
   */
  book_ask_display: string | null;
  /**
   * When these prices were captured, in epoch milliseconds.
   *
   * A maker has about **three seconds** to stand behind a quote on a
   * combination, against thirty elsewhere. A price with no age on it is a
   * price the reader cannot tell is dead.
   */
  asked_ms: number;
  quotes: ComboRfqQuote[];
  words: string;
  /**
   * Whether taking a quote will actually spend.
   *
   * False while the accept path is unarmed. Surfaced WITH the price rather
   * than discovered after the tap, so the button can say what it does
   * before it is pressed.
   */
  accepts_are_armed: boolean;
};

/**
 * Ask the makers what this combination costs.
 *
 * **This is how a combination is actually priced.** `lookupParlay` above
 * reads the public order book, which for a combination is empty by design
 * between requests -- so it reported "nothing is resting" on markets that
 * were being quoted all day. This fires a real Request for Quote.
 *
 * **No money moves.** Only accepting a quote binds the requester, and there
 * is no accept path. The request is deliberately tiny: the backend reads the
 * legs, the collection and the fair value from the ticker's own recorded
 * lookup, so this call cannot talk it into pricing something else.
 */
export type ComboRfqAcceptResult = {
  /** The venue's own quote status: `confirmed`, `executed`, `cancelled`, or
   *  `unknown` when the outcome could not be observed. */
  status: string;
  /** True only when the venue said so. Never inferred from a 204. */
  filled: boolean;
  /** True while the accept path is unarmed — nothing reached Kalshi. */
  dry_run: boolean;
  rfq_id: string;
  quote_id: string;
  accepted_side: string;
  expected_ask_tenths: number | null;
  expected_ask_display: string | null;
  words: string;
};

/**
 * One leg of a parlay someone else built, as `POST /api/parlays/check`
 * reads it off the pasted link or ticker.
 *
 * **`chance` is `null`, never `0`, when the desk has no reading for this
 * leg** — a prop, another sport, anything the consensus does not cover. `0`
 * is a legitimate chance; `null` is the honest "cannot tell you" (CLAUDE.md
 * rule: unreadable resolves to `None`, never `0`). `unknown_reason` names
 * why, when the server has a name for it.
 */
export type CheckedParlayLeg = {
  market_ticker: string;
  side: "yes" | "no";
  label: string;
  commence_ms: number | null;
  /** Each team's rest before this game (#201); `null` when unidentified. */
  rest?: LegRest | null;
  /** Probability in [0, 1]. `null` means no desk reading — see above. */
  chance: number | null;
  chance_display: string | null;
  /** Plain words for Joe; `unknown_reason_code` keeps the machine code. */
  unknown_reason: string | null;
  unknown_reason_code: string | null;
  /**
   * Where the chance came from (#303): the books' main line, or their other
   * lines at this leg's exact number. `null` when there is no chance.
   */
  line_source: "main" | "alternate" | null;
  /** The books an `alternate` chance was read from; `null` otherwise. */
  alt_books_used: string[] | null;
  /**
   * Whether the singles screen would call this price a probable bug (#325).
   * `unknown` means the desk has no price for the leg at all, which is never
   * the same as `clean`.
   */
  probable_bug_status: "bug" | "clean" | "unknown";
  /** Plain words, present only when `probable_bug_status` is `bug`. */
  probable_bug_reason: string | null;
};

/** One game whose other lines a check asked to buy (#303). */
export type CheckedParlayAltBuy = {
  odds_event_id: string;
  accepted: boolean;
  /** The inbox's own words, accepted or refused. */
  detail: string;
  estimated_credits: number;
  retry_after_ms: number;
};

/** What `POST /api/parlays/check` came back with (issue #167). */
export type CheckedParlayResult = {
  status: "priced" | "book_empty";
  minted_market_ticker: string;
  /**
   * Whether "Ask the market" can work on this combination: true only on
   * Kalshi's combinations shard (`exchange_index == 1`, which the RFQ path
   * hard-codes) while the market is `active`. #166 round 2.
   */
  rfq_available: boolean;
  rfq_unavailable_reason: string | null;
  /** The Take-it path's fee coefficient (#334); see the lookup type. */
  fee_coefficient?: number | null;
  legs: CheckedParlayLeg[];
  alt_buys: CheckedParlayAltBuy[];
  /** How cards from a friend have done so far (#325): one fixed line. */
  friend_source_line: string | null;
  fair: {
    /** Probability in [0, 1]. `null` when `no_joint_reason` is set. */
    conservative: number | null;
    conservative_percent_display: string | null;
    fair_cost_display: string | null;
    /**
     * Why there is no joint chance, when there is none. `"unknown_leg"`
     * means at least one leg has `chance === null`; `"same_game"` means the
     * desk refuses to price a same-game combination at all. `null` means
     * the joint fields above are populated.
     */
    no_joint_reason: "unknown_leg" | "same_game" | null;
  };
  quoted: {
    ask_display: string;
    depth_display: string | null;
    quoted_ms: number;
    quote_max_age_ms: number | null;
  } | null;
  hold_display: string | null;
  words: string;
  notes: { unquoted: string; fee: string };
};

/**
 * One side of one leg on the same-game builder (#202): the desk's own
 * consensus chance, or `null` with a worded reason. `null` is never 0 -- most
 * props, first-half and quarter markets, team totals and touchdown scorers
 * have no desk reading, and they are shown, not hidden.
 */
export type GameLegSide = {
  chance: number | null;
  chance_display: string | null;
  unknown_reason: string | null;
  unknown_reason_code: string | null;
};

export type GameLeg = {
  market_ticker: string;
  event_ticker: string;
  series: string;
  kind: string;
  /** Kalshi's own title for the market, verbatim. */
  title: string;
  yes_label: string | null;
  no_label: string | null;
  strike: number | null;
  player: string | null;
  allowed_sides: ("yes" | "no")[];
  /** How many legs Kalshi lets one combination take from this event; `null`
   *  when it names no limit (props). */
  size_max: number | null;
  one_per_event: boolean;
  sides: Partial<Record<"yes" | "no", GameLegSide>>;
  /** Each team's rest before this game (#293): a fact per leg, never sorted
   *  or filtered by. `null` when the game could not be identified. */
  rest?: LegRest | null;
};

export type GameLegGroup = {
  series: string;
  kind: string;
  label: string;
  one_per_event: boolean;
  legs: GameLeg[];
};

/**
 * `GET /api/game/{event}/legs`. **The groups arrive in a fixed order that is
 * never a function of any chance or price (ADR 0071), and no combined chance
 * exists anywhere in this shape** -- the desk has no model of how same-game
 * legs move together.
 */
export type GameLegs = {
  game_event_ticker: string;
  fixture: string;
  collection_ticker: string;
  /** A market on the game itself, so the page can mount the scout desk. */
  game_market_ticker: string | null;
  /** Kalshi's own name for the game, the desk's kickoff and the odds feed's
   *  sport key (#293); each `null`/absent when the desk cannot say. */
  game_title?: string | null;
  kickoff_ms?: number | null;
  sport_key?: string | null;
  groups: GameLegGroup[];
  leg_count: number;
  unreadable_events: { event_ticker: string; words: string }[];
  skipped_events: number;
  now_ms: number;
};

export type GameMintResult = {
  status: "minted" | "no_collection";
  minted_market_ticker?: string;
  words: string;
};

export type ComboBidResult = {
  status: "resting" | "filled" | "partially_filled" | "rejected" | "dry_run";
  order_row_id: number;
  kalshi_order_id?: string | null;
  ticker: string;
  exchange_index: number;
  contracts: number;
  price_tenths: number;
  words: string;
};

export type ComboBid = {
  id: number;
  ticker: string;
  card_key: string;
  status: string;
  contracts: number;
  price_display: string;
  committed_display: string;
  placed_ms: number;
  cancel_after_ms: number | null;
  dry_run: boolean;
  note: string | null;
};

/**
 * The leg scout's TAKE/PASS on one side of one parlay leg (#151, ADR 0186).
 *
 * **Advisory only, and that is enforced above this file, not in it.**
 * `<LegVerdicts>` (`components/LegVerdicts.tsx`) is the one renderer, takes
 * no callback and disables nothing -- these two functions only move bytes.
 *
 * `state` is the server's own read of where this leg's verdict stands:
 *
 *   `cached`  — a complete verdict already exists and is fresh enough to
 *               show; `verdict` and `reason` are set.
 *   `pending` — a verdict is being written right now (this request or an
 *               earlier one); poll again.
 *   `refused` — the budget or the shard turned the request away;
 *               `refusal_reason` says why. Not information about the leg.
 *   `none`    — nobody has asked about this leg, or a `GET` reader found no
 *               row at all. `refusal_reason` carries the server's sentence
 *               either way, so the two cases render identically on screen.
 */
export type LegVerdictState = "cached" | "pending" | "refused" | "none";

export type LegVerdict = {
  ticker: string;
  side: "yes" | "no";
  state: LegVerdictState;
  id: number | null;
  verdict: "take" | "pass" | null;
  reason: string | null;
  /** The ask, in words, AT THE TIME the seat looked -- never re-derived
   *  here, and never re-read for a live price (that is a different call). */
  ask_display_at_verdict: string | null;
  age_ms: number | null;
  refusal_reason: string | null;
};

export type LegVerdictsResult = {
  legs: LegVerdict[];
  /**
   * `null` on success. Set on any failure to reach or read the server,
   * including the 503 the backend sends while the seat is switched off --
   * that case is always worded exactly `"Scouts are off"`, which is the
   * only sentence `<LegVerdicts>` is allowed to render for it.
   */
  error: string | null;
};

/** One leg identified for a verdict request: what side of what ticker. */
export type LegVerdictInput = { ticker: string; side: "yes" | "no" };

export type LegVerdictTrigger =
  | "price_tap"
  | "leg_buys_open"
  | "card_button"
  | "check_button";

/**
 * One leg of a game-script card (#216), with Kalshi's own single-leg ask read
 * by the server when the card was fetched. `ask_tenths` is `null` with
 * `ask_unread_reason` in words when the book could not be read -- never 0.
 * **There is no combined figure in this shape and none may be added**
 * (ADR 0189): each ask is one leg's, and the makers' quote prices the link.
 */
export type GameScriptLeg = {
  market_ticker: string;
  event_ticker: string;
  side: "yes" | "no";
  title: string;
  side_label: string | null;
  ask_tenths: number | null;
  ask_display: string | null;
  ask_unread_reason: string | null;
  /** When the ask above was read, or `null` when no book read succeeded. */
  read_ms: number | null;
  /** Contracts resting at that ask now; `null` when unread. */
  size_now: number | null;
  /** Each team's rest before this game (#293); a fact, never ranked by. */
  rest?: LegRest | null;
  /**
   * The books' chance this leg wins (#312), read now through the game page's
   * lookup; `null` with `books_chance_reason` in words when the desk has no
   * usable consensus for it. One leg's own figure: never combined, never
   * sorted, filtered or coloured by.
   */
  books_chance?: number | null;
  books_chance_display?: string | null;
  books_chance_reason?: string | null;
  /**
   * This leg's listed ask when the card was written (#283), or `null` on a
   * card built before it was kept. Per leg: nothing here is combined.
   */
  at_build: {
    ask_tenths: number | null;
    ask_display: string | null;
    size: number | null;
    read_ms: number | null;
  } | null;
};

export type GameScriptCard = {
  id: number;
  game_event_ticker: string;
  sport_key: string;
  kickoff_ms: number;
  built_ms: number;
  status: "built" | "skipped" | "refused_budget" | "refused_invalid";
  story: string | null;
  drop_if: string | null;
  reason: string | null;
  combo_ticker: string | null;
  /** Empty on anything but a built card. */
  legs: GameScriptLeg[];
  /** Win legs left off because the same team's cover already includes them. */
  dropped_legs: { market_ticker: string; event_ticker: string; side: string }[];
  /** The sentence a game with no built card carries; `null` on a built one. */
  no_card_line: string | null;
  /** The sport's own sentence about when lineups are confirmed (#284). */
  inactives_line: string;
  /** Pages the scout read, or `null` on a card built before sources were kept. */
  sources: { url: string; published: string }[] | null;
  /** What has to happen in the game for every leg to win; `null` on older cards. */
  ticket_needs: string | null;
  /**
   * The T-2h drop-if re-check (#289), only on a game Joe opened. `null`
   * until it has run. `not_found` means one search did not find the drop-if
   * news; it never confirms the card.
   */
  recheck_ms?: number | null;
  recheck_status?: "triggered" | "not_found" | "unknown" | "refused_budget" | null;
  recheck_note?: string | null;
  recheck_source?: { url: string; published: string } | null;
  /** Kalshi's own name for the game, or `null` when discovery has none. */
  game_title: string | null;
};

/**
 * `GET /api/game-cards`. **The cards arrive in kickoff order and this file
 * never re-sorts them** (ADR 0071); skipped and refused games are in the list
 * with their reason in `no_card_line`.
 */
export type GameScriptCards = { now_ms: number; cards: GameScriptCard[] };
