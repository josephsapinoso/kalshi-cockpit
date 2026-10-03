/**
 * Wire types for the hedge screen and held positions.
 *
 * Types only (#262, ADR 0191 sec 2.5): `import type` and nothing at runtime, and
 * never an import from `api.ts`. `api.ts` re-exports every name here.
 */

/**
 * One leg of a ticket Joe holds, with the venue's live view of it.
 *
 * `chance_display` is a percentage or `"--"`. It comes from the venue's own
 * BID — what somebody will actually pay — and never from a mid. `"--"` means
 * nobody is bidding or the leg has no Kalshi market at all; it never means 0%.
 */
export type HeldLeg = {
  id: number;
  index: number;
  label: string;
  ticker: string | null;
  side: "yes" | "no";
  league: string | null;
  commence_ms: number | null;
  /** The game, as Kalshi titles the event. `null` on a leg recorded before
   *  schema v43 or typed by hand; the row then shows the label alone. */
  event_title: string | null;
  outcome: "pending" | "won" | "lost" | "void";
  resolved_ms: number | null;
  /** `venue` is the exchange's own result; `manual` is Joe's word. */
  resolved_source: "venue" | "manual" | null;
  chance_display: string;
  quote_age_ms: number | null;
  priceable: boolean;
  is_hedge_leg: boolean;
};

/** One hedge size, fully costed. Every money field is a rendered string. */
export type HedgeRung = {
  contracts: number;
  cost_display: string;
  fee_display: string;
  if_leg_wins_display: string;
  if_leg_loses_display: string;
  floor_display: string;
  floor_is_a_gain: boolean;
  fillable: boolean;
  affordable: boolean;
};

export type HedgeRefusal = { reason: string; detail: string };

/**
 * What hedging would do, or why it cannot be priced.
 *
 * `kind` separates the two states that must never render alike: a `lock` has
 * a figure for what a hedge comes to either way — an estimate, four terms of
 * mixed sign sit on it — and a `derisk` has none; it carries no `guaranteed`
 * field at all, rather than a false one. (`lock` is the wire name of the
 * state and the alert predicate; the screen does not use the word.)
 */
export type HedgeBlock = {
  refusal: HedgeRefusal | null;
  kind?: "lock" | "derisk";
  ticker?: string;
  side?: "yes" | "no";
  ask_display?: string;
  depth_at_ask?: number | null;
  ladder?: HedgeRung[];
  // lock only
  equalising?: HedgeRung;
  best_available?: HedgeRung | null;
  guaranteed?: boolean;
  guaranteed_display?: string | null;
  /** The largest measured error term on this ticket's figure, in dollars for
   * this ticket, as one sentence (`hedge.estimate_grain`). Rendered beside the
   * figure at the figure's size; never computed with. `null` when there is
   * no figure to set it beside. */
  uncertainty_display?: string | null;
  full_hedge_is_out_of_reach?: boolean;
  // derisk only
  live_legs?: number;
  chance_display?: string;
  notional_value_display?: string;
  chance_refusal?: HedgeRefusal | null;
};

/**
 * What the venue itself said happened to the position's own (combo) market —
 * distinct from every leg's own `outcome`. A `KXMVE` combination can settle
 * before its leg markets do, so this can be non-null while every leg below
 * still reads `pending`; nothing here marks a leg won or lost.
 */
export type VenueSettlement = {
  /** Verbatim from the venue. Observed values are "yes" and "no", but this
   * is not assumed to be the only two. */
  market_result: string | null;
  settled_ms: number;
};

export type HeldPosition = {
  id: number;
  label: string;
  source: "kalshi_combo" | "sportsbook";
  book: string | null;
  created_ms: number;
  placed_ms: number | null;
  combo_ticker: string | null;
  stake_display: string;
  /**
   * WHOSE price `stake_display` is (ADR 0160). `"venue_fill"` means Kalshi's
   * own average fill price times the count the venue reported;
   * `"as_recorded"` means the figure stored with the position — the price the
   * desk sent, or Joe's typed stake on a sportsbook slip. `null` only on a
   * payload that never went through `hedge.build_payload`, and it is NOT a
   * `"venue_fill"`: the card treats an absent basis as unchecked.
   *
   * `"venue_exposure"` (#148) is a position `adopt_venue_combo` wrote: the
   * stake is Kalshi's own `market_exposure_dollars` for the holding, but —
   * unlike `"venue_fill"` — never itself checked against a fill, because an
   * adopted row has no order and no RFQ acceptance behind it to check it
   * against. It renders its own caveat rather than staying silent like
   * `"venue_fill"`.
   *
   * Declared here as of issue #53 (Joe, 2026-09-16), which reversed ADR 0160
   * §5 — that section left both fields off this file on the `floor_tenths`
   * precedent, because nothing rendered them. `HedgePositions.tsx` now does.
   */
  stake_basis: "venue_fill" | "as_recorded" | "venue_exposure" | null;
  /**
   * Which refusal sent the stake back to the recorded figure; `null` on a
   * `"venue_fill"`. `string` rather than a union of the nine names on
   * purpose: a server running a reason this build predates is a real state,
   * and `lib/stakeBasisGloss.ts` renders it verbatim rather than hiding it.
   */
  stake_basis_reason: string | null;
  /** The entry fee the hedge arithmetic sinks beside the stake on a Kalshi
   * combo (ADR 0145); `null` on a sportsbook slip, whose vig is in its
   * price. Rendered, never computed with. */
  entry_fee_display: string | null;
  return_display: string;
  state: "lock" | "derisk" | "dead" | "won" | "void_leg" | "not_hedgeable";
  state_detail: string;
  /** False means the affordability cap is the book's depth standing in for a
   * balance nobody could read — never a limit to act on. */
  bankroll_known: boolean;
  pending_legs: number;
  /** Whether this ticket's own market is in the latest complete venue
   * positions poll. `null` means the question has no answer: either this is
   * a sportsbook slip (no `combo_ticker`), or there has never been a
   * complete poll to check against — neither is a `false`. This field closes
   * nothing (absence from a poll is not a settlement); the venue's own
   * settlement does close a combination, on the watcher's pass (ADR 0181),
   * and a hand-recorded slip is still closed only by Joe's tap. */
  at_venue: boolean | null;
  /** The venue's own settlement of this ticket's own market, or `null` when
   * unsettled (or not a combination at all). */
  venue_settlement: VenueSettlement | null;
  /**
   * What the public order book says this combination could be sold back for
   * right now (#95). Five states that must never collapse into each other:
   * `null` means "not applicable" and the row says nothing about the public
   * book at all — `combo_book_reason` names why (`no_ticket`: a
   * hand-recorded slip has no ticker to read; `no_reader_wired`: this
   * instance's `/api/hedge` was built with no combo-book reader — true of
   * every deploy until #128). A non-null block's `state` carries the other
   * four: `"bid"` (a priced YES level rests — `price_display` and `size`
   * are set), `"empty"` (a read succeeded and nothing rests), `"unpriced_
   * interest"` (a level rests finer than a tenth of a cent, per #106 — no
   * showable price), `"unreadable"` (the read or the parse failed).
   *
   * `price_display` and `size` are `null` on every state but `"bid"` —
   * never `0`, which is a legitimate settled price (`format_price(0)` ===
   * `"0c"`).
   */
  combo_book: {
    state: "bid" | "empty" | "unpriced_interest" | "unreadable";
    observed_ms: number;
    price_display: string | null;
    size: number | null;
  } | null;
  /** Set only when `combo_book` is `null`; names which of the three designed
   * "not applicable" causes applied. `nothing_pending` is the third (#130,
   * extended #132, `backend/hedge.py:1958`): either every leg on this
   * ticket has already resolved, OR the venue has already settled the
   * combination itself even while a leg still reads `pending` (a combo can
   * settle at the venue before its leg markets do, `backend/hedge.py:1201`
   * -- checked against the same `venue_settlements` read this field's own
   * `venue_settlement` comes from). Either way there is nothing left to
   * sell out of. Since ADR 0181 a venue-settled combination leaves the
   * open list on the watcher's next pass, so this reason now mostly marks
   * the lag between the venue's settlement and that pass, plus rows whose
   * legs resolved before the venue settled the combination (re-read
   * `/api/hedge` for the split; a count here would decay, ADR 0162). It is distinct from `no_ticket` and
   * `no_reader_wired`, which are both about whether a read could even be
   * attempted. */
  combo_book_reason: "no_ticket" | "no_reader_wired" | "nothing_pending" | null;
  legs: HeldLeg[];
  /** `null` means there is nothing to hedge, which is not the same as a
   * refusal — that arrives as a block whose `refusal` is set. */
  hedge: HedgeBlock | null;
};

/** A Kalshi combination the venue holds that no open `HeldPosition` is
 * watching — bought outside the desk (the Kalshi app), so ADR 0125's writer
 * never saw the fill. Singles are out of scope here: a bare market has no
 * other leg to reshape and so no hedge story. */
/**
 * A leg of a combination about to be bought that bets against a ticket
 * already held (`backend/held_conflicts.py`): the same market on the other
 * side, or another team to win the same full game. Exact clashes only.
 */
export type HeldConflict = {
  kind: "opposite_side" | "other_winner";
  leg_label: string;
  held_label: string;
  position_id: number;
  position_label: string;
};

/** `checked: false` means the desk could not read this combination's legs
 *  -- not that nothing clashes. */
export type HeldConflicts = {
  checked: boolean;
  conflicts: HeldConflict[];
};

export type UnrecordedAtVenue = {
  ticker: string;
  contracts: number | null;
  exposure_display: string;
  last_seen_ms: number;
};

export type HedgeScreen = {
  as_of_ms: number;
  positions: HeldPosition[];
  notes: Record<string, string>;
  /** Combinations the venue holds that nothing here is watching. `[]` is a
   * real answer only when `venue_poll_ms` is non-null; with no complete poll
   * yet this is `[]` too, but that means "unknown", not "confirmed none". */
  unrecorded_at_venue: UnrecordedAtVenue[];
  /** When the venue positions poll this coverage read is based on last
   * completed, or `null` when there has never been one. */
  venue_poll_ms: number | null;
  /** The same staleness bound a hedge quote is refused past — for dimming a
   * leg's price on the screen at the same threshold, rather than a second
   * hardcoded guess of it. */
  max_quote_age_ms: number;
};

export type HeldLegInput = {
  ticker?: string | null;
  side: "yes" | "no";
  label: string;
  event_ticker?: string | null;
  league?: string | null;
  commence_ms?: number | null;
};

export type HeldPositionInput = {
  source: "kalshi_combo" | "sportsbook";
  label: string;
  stake_cents: number;
  return_cents: number;
  legs: HeldLegInput[];
  book?: string | null;
  note?: string | null;
  combo_ticker?: string | null;
};

/**
 * What makers said they would pay for a held combination, asked once (#96).
 *
 * The RFQ half of Joe's (A) to #63 -- read-only; the desk does not sell. The
 * request was withdrawn before this arrived, so nothing here can be taken.
 */
export type HedgeSellQuote = {
  /**
   * `bid`: one or more makers named a price to buy it back. `bid_too_finely`:
   * makers bid only in hundredths of a cent, which the desk refuses to round.
   * `no_bid`: nobody bid in the few seconds the desk listened.
   */
  status: "bid" | "bid_too_finely" | "no_bid";
  position_id: number;
  market_ticker: string;
  /** The venue's holding, verbatim, and the floored size actually asked. */
  held_fp: string;
  asked_fp: string;
  asked_ms: number;
  makers_answered: number;
  refused_bid_too_fine: number;
  /** Rendered server-side through the ONE price renderer; null with no bid. */
  best_bid_display: string | null;
  best_bid_tenths: number | null;
  bids: {
    quote_id: string;
    yes_bid_tenths: number;
    bid_display: string;
    /** Contracts behind that bid; null when the maker did not say. */
    contracts: number | null;
  }[];
  /** The server's own sentence, rendered verbatim. */
  words: string;
};
