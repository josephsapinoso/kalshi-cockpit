/**
 * Does the game screen actually show an ask right now?
 *
 * **One predicate, one spelling.** The quote strip on `/market/[ticker]`
 * decides between three outcomes, and this file is where that decision lives
 * so it cannot be spelled a second time. This repo has recorded the same
 * shape four times — one predicate with two spellings, and the screen
 * believing the wrong one — and every instance was the second spelling
 * drifting from the first. **The strip is the authority on whether the strip
 * shows a price.** Re-deriving that anywhere else reopens the defect the next
 * time the refusal grows a condition.
 *
 * **`askIsVisible` was removed 2026-09-09 with its only caller.** It existed
 * to feed the hand-bet ticket's `priceAlreadyVisible` flag — which of two
 * masked-ask wordings to render — and the mask went with the P(YES) field
 * (ADR DRAFT-the-ticket-stops-asking-for-a-probability, superseding ADR 0065
 * §2). Ticket #24's fix is not undone by that: it required the flag to be
 * DERIVED from this function rather than asserted, and the way a flag with no
 * reader satisfies that requirement is by not existing. What is left is the
 * strip, reading its own verdict. Do not reintroduce a named `=== "ask"`
 * wrapper without a caller.
 *
 * Plain TypeScript with no React import and no dependency on `lib/api`, so
 * `tests/test_quote_visibility.py` can execute the shipped function under
 * node rather than asserting on its source text. A substring test passes
 * unchanged on a predicate that has been exactly inverted, and an inverted
 * predicate here is the whole defect.
 *
 * What this does NOT decide: whether a quote *ought* to count as current.
 * `price_is_current` and `quote_age_now_ms` are the server's judgement
 * (`backend/api/routers/` builds them); this file only reads them. If the
 * staleness rule changes, it changes there and this predicate follows for
 * free — which is the point of it existing.
 */

/**
 * The fields the verdict needs, and no more.
 *
 * Structural rather than an import of `MarketDetail`: that type carries ~40
 * fields and pulls `lib/api` behind it, which would make this module
 * unexecutable under node's type stripping for the sake of documentation a
 * comment does better. `MarketDetail` satisfies this shape, and `tsc` proves
 * it at every call site.
 */
export type QuotableDetail = {
  market_status: string | null;
  close_ms: number | null;
  quote_age_now_ms?: number | null;
  price_is_current?: boolean;
};

/**
 * The quote strip's three outcomes, named.
 *
 * - `"ask"` — a current ask is printed. The only value on which the strip
 *   may show a number at all.
 * - `"stale"` — the market is live but the recorded ask is not transactable,
 *   so the strip refuses it outright in words. **Refused, not greyed**: a
 *   stale ask on a page with no fresher rows beside it reads as a price.
 * - `"absent"` — nothing is rendered at all: either the recorder never priced
 *   this ticker (no detail row) or the market is finalized, settled, or past
 *   its close.
 *
 * `"stale"` and `"absent"` are kept apart because the strip renders
 * differently for each, even though the ticket treats them the same. Collapsing
 * them here would push the distinction back into the component and give the
 * predicate two spellings again.
 */
export type QuoteVisibility = "ask" | "stale" | "absent";

/** What the quote strip will render for this detail, at this instant. */
export function quoteVisibility(
  detail: QuotableDetail | null | undefined,
  now: number,
): QuoteVisibility {
  // No row at all: the page renders "the recorder never priced this ticker"
  // and mounts no strip. Undefined and null are the same fact here — the
  // caller has nothing — and neither may read as a price.
  if (detail === null || detail === undefined) return "absent";

  const status = (detail.market_status ?? "").toLowerCase();
  const dead =
    status === "finalized" ||
    status === "settled" ||
    (detail.close_ms !== null && detail.close_ms <= now);
  if (dead) return "absent";

  // `price_is_current !== true` rather than `=== false`: the field is optional,
  // and a backend one version behind omits it. An absent judgement is not a
  // judgement of "current" — unreadable resolves to a refusal, never to the
  // permissive branch.
  if (detail.price_is_current !== true) return "stale";

  // The age is what the strip prints beside the ask ("quote checked N ago").
  // Without it there is no honest way to render the ask line, so the strip
  // refuses on this alone even when the server called the price current.
  const age = detail.quote_age_now_ms;
  if (age === null || age === undefined) return "stale";

  return "ask";
}
