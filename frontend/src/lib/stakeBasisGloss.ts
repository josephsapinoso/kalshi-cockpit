/**
 * Plain English for the one ticket whose stake is NOT Kalshi's own number.
 *
 * **The asymmetry is the decision** (issue #53, answered A by Joe on
 * 2026-09-16). ADR 0160 made `/api/hedge` resolve every open position's stake
 * at read time: where Kalshi reported a fill price for the order behind the
 * ticket, the stake is that price times the count the venue reported
 * (`stake_basis: "venue_fill"`); everywhere else the figure recorded with the
 * position stands (`stake_basis: "as_recorded"`) and `stake_basis_reason`
 * names which refusal applied. A `venue_fill` ticket renders **nothing** from
 * this module. An `as_recorded` ticket renders **one line naming its own
 * reason**.
 *
 * Joe's stated principle, and the reason it is this way round: *a warning
 * that fires only on the good case reads as a check that passed*. So the
 * words go on the LESS certain ticket. The inverse failure is the
 * `ParlayCards` defect fixed on 2026-09-15 — a note that rendered only when
 * `anchored_on_sharp === true` and said nothing at all when no sharp book
 * backed the leg — and neither direction of it is allowed here.
 *
 * **A reason this build has never heard of still renders a line**, which is
 * the one place this deliberately parts company with
 * `suppressionGloss.ts`'s "unknown code glosses to null". There the code
 * itself is rendered beside the sentence, so a null gloss loses nothing; here
 * the sentence is the only thing on the screen, so a null would put the
 * unknown reason and the good case on the same blank row. The fallback says
 * what is certain — this stake was not checked against Kalshi's own record —
 * and carries the unknown code verbatim, which is the deploy-skew fact worth
 * seeing.
 *
 * **The sentences are short on purpose.** They render in small type under a
 * money figure, on a phone, while a game is running. The full statement of
 * any of these refusals is `backend/hedge.py`'s `stake_basis_for` and ADR
 * 0160 §3; this is the headline.
 *
 * **Every reason `stake_basis_for` can return must have an entry**, and
 * `tests/test_the_hedge_card_names_the_fallback_reason.py` pins the two
 * vocabularies against each other in both directions: a refusal with no
 * sentence renders as a bare code, and a sentence naming a refusal the
 * backend can no longer produce is a claim about a system that is gone.
 */

/** `stake_basis` on a position whose stake IS Kalshi's own average fill
 * price times the count it reported. Nothing from this module renders. */
export const STAKE_BASIS_VENUE_FILL = "venue_fill";

/**
 * `stake_basis` on a position `POST /api/hedge/positions/adopt` wrote (#148)
 * — a KXMVE combination the venue already showed held, put under watch in
 * one tap. Kalshi's own number, like `venue_fill`, but a DIFFERENT Kalshi
 * number: `market_exposure_dollars` for the holding, never itself checked
 * against a fill (there is no order and no RFQ acceptance behind an adopted
 * row to check it against). Renders its own line always — unlike
 * `venue_fill`, silence here would claim a fill-level check that never ran.
 */
export const STAKE_BASIS_VENUE_EXPOSURE = "venue_exposure";

/** The one line a `venue_exposure` ticket always carries. Not in
 * `STAKE_BASIS_GLOSS`: that map is `stake_basis_for`'s AS-RECORDED refusal
 * vocabulary (pinned 1:1 against it by `tests/test_the_hedge_card_names_
 * the_fallback_reason.py`), and `venue_exposure` is a second GOOD-ish case
 * beside `venue_fill`, not a refusal — it says whose number the stake is,
 * not that a lookup failed. */
export const STAKE_BASIS_VENUE_EXPOSURE_NOTE =
  "Adopted from Kalshi's own reported holding — the stake above is Kalshi's reported position cost (market exposure), inferred and fee-exclusive, not a measured fill.";

/**
 * One line per named refusal, in Joe's language rather than the enum's.
 *
 * The shared half of every Kalshi sentence — "the price the desk sent" —
 * is the same phrase the screen's own caveat (`notes.upper_bound`) uses for
 * it, so the ticket and the note beneath it name one thing once. It is
 * spelled out in full on `no_venue_price`, which is the reason most tickets
 * on this screen carry: seven of the thirteen real orders predate the
 * columns Kalshi's own price is read from.
 */
export const STAKE_BASIS_GLOSS: Record<string, string> = {
  not_a_kalshi_combo:
    "A sportsbook slip — there was never a Kalshi order behind it, so the stake above is the figure you typed in.",
  hand_recorded_position:
    "You recorded this one by hand, so the stake above is the figure you typed in — not Kalshi's record of what it charged.",
  no_order_row:
    "No Kalshi order matches this ticket, so the stake above is the price recorded with it, not Kalshi's own record of the fill.",
  rfq_accept:
    "You bought this by taking a maker's quote, which places no ordinary Kalshi order — the stake above is the price you accepted times the size quoted, before fees.",
  rfq_fill_unmatched:
    "You took a maker's quote for this, and Kalshi's own record of the fill did not name this bet — the stake above is the price you accepted times the size quoted.",
  ambiguous_order_rows:
    "More than one Kalshi order matches this ticket, so which fill it was cannot be read — the stake above is the price recorded with it.",
  side_convention_unresolved:
    "This was a NO order, and which side Kalshi quotes its fill price on has never been established here — the stake above is the price the desk sent, not a guess.",
  no_venue_price:
    "This bet predates the record we keep of what Kalshi charged (kept since 11 Sep 2026), so the stake above is the price the desk asked to pay when the order went out.",
  no_venue_fill_count:
    "Kalshi's record of this order does not say how many contracts filled, so the stake above is the price the desk sent.",
  venue_fill_count_unusable:
    "Kalshi's record of this order reports a fill count that cannot be a holding — zero or less — so the stake above is the price the desk sent.",
  fractional_venue_fill_count:
    "Kalshi's record of this order reports part of a contract, which a stake cannot be rebuilt from, so the stake above is the price the desk sent.",
  contract_count_disagrees:
    "The Kalshi order found for this ticket is for a different number of contracts, so it is some other bet — the stake above is the price the desk sent.",
};

/**
 * What is said when the reason is missing or is one this build predates.
 *
 * It claims only the thing that is true in every such case, and it is said
 * rather than left blank: blank is what a `venue_fill` ticket looks like.
 */
export const STAKE_BASIS_UNNAMED =
  "This stake has not been checked against Kalshi's own record of the fill, so it is the price recorded when the bet was placed.";

/**
 * The one line a held ticket's stake carries, or `null` when it carries none.
 *
 * `null` means exactly one thing — the stake IS Kalshi's own number, so there
 * is nothing to caveat. Every other input, including a `stake_basis` that is
 * missing altogether, returns a sentence: a payload built by something other
 * than `hedge.build_payload` does not know whose price its stake is, and "not
 * known" must never render as the good case (the house rule — unreadable
 * resolves to nothing plausible, and here the plausible thing is silence).
 */
export function stakeBasisNote(
  basis: string | null | undefined,
  reason: string | null | undefined,
): string | null {
  if (basis === STAKE_BASIS_VENUE_FILL) return null;
  if (basis === STAKE_BASIS_VENUE_EXPOSURE) return STAKE_BASIS_VENUE_EXPOSURE_NOTE;
  const code = typeof reason === "string" ? reason.trim() : "";
  const gloss = code ? STAKE_BASIS_GLOSS[code] : undefined;
  if (gloss) return gloss;
  return code ? `${STAKE_BASIS_UNNAMED} (${code})` : STAKE_BASIS_UNNAMED;
}
