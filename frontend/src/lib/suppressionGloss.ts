/**
 * Plain English beside a suppression code — never instead of it.
 *
 * **The prior decision this amends, and why it survives.** `SlateRow`'s
 * docstring refused a translation on the grounds that "translating them here
 * would give the same rule two names". That argument is correct and is kept:
 * the code is still rendered, verbatim, in the same monospace it always was.
 * It is what `/api/suppression` counts, what `/rejections` groups by, and what
 * a miscalibrated rule shows up as — a reader who sees `suspicious_edge` on a
 * row and `suspicious_edge` at the top of the Rejections screen is looking at
 * one name for one rule, and that is worth more than brevity.
 *
 * What was never true is that the code alone tells a beginner anything. It
 * names the rule; it does not say what happened. So the gloss is **additive**:
 * code first, sentence after. Two names would be a replacement. This is a
 * label and a caption.
 *
 * **The sentences are short on purpose, and are not the ones on `/rejections`.**
 * That screen is a diagnostic read at a desk and its explanations run to a
 * paragraph each, with the counts and the citations that make them checkable.
 * This one renders on a row on a phone, beside an edge and a price, where a
 * paragraph would push the numbers off the screen. Where the two disagree in
 * detail, `/rejections` is the fuller statement — this is the headline.
 *
 * **Every code in `backend/core/suppression.py` must have an entry**, and
 * `tests/test_suppression_gloss.py` pins the two vocabularies in both
 * directions: a rule with no sentence renders as a bare identifier, which is
 * the state the gloss exists to end, and a sentence naming a rule that no
 * longer exists is a claim about a system that is gone.
 */
const GLOSS: Record<string, string> = {
  suspicious_edge: "edge too big to believe — treated as a bug, not a bet",
  edge_within_method_noise:
    "edge is smaller than the disagreement between the four devig methods",
  stale_kalshi_quote: "Kalshi's price was too old when this was judged",
  stale_odds: "the sportsbook lines had aged out — needs an odds refresh",
  insufficient_depth: "fewer contracts resting at the ask than the bet needs",
  wide_market: "the books disagree with each other by more than the edge",
  too_few_books: "too few sportsbooks quoted it to form a consensus",
  commence_skew: "start times disagree — likely the wrong game matched",
  no_commence_time: "no start time, so the two sides can't be confirmed as one game",
  no_depth: "no size quoted at the ask — the book could not be read",
  no_market_width: "only one book, so their disagreement can't be measured",
  inconsistent_consensus_metadata:
    "the consensus contradicts itself — a producer bug, not a market",
};

/**
 * The **second** vocabulary in the same column, which is easy to miss.
 *
 * `backend/engine.py:255` writes `sizing:{binding_constraint}` into
 * `suppressed_reason` when the sizer refused and no check had already fired.
 * So a row on the Slate can read `sizing:bankroll_unobserved` — a string that
 * is not in `ALL_CHECK_NAMES` and never will be. These are not suppression
 * checks; they are the sizer declining to compute a size, and the difference
 * matters to a reader: a check says *this bet is bad*, a sizer refusal says
 * *I could not work out how much*.
 *
 * Only the refusing constraints are listed. `kelly`, `no_edge`,
 * `max_position_dollars`, `max_exposure_dollars`, `max_order_contracts` and
 * `stake_below_one_contract` all *clamp* rather than refuse
 * (`backend/core/sizing.py`: they set `constraint` on a `SizingResult` whose
 * `refused` is false), and the `sizing:` prefix is written only when
 * `sizing.refused`. A gloss for a code that cannot reach the column would be a
 * sentence about a state that does not occur.
 *
 * The asymmetry is deliberate and is the repo's own rule — *clamp what you
 * trust; refuse what you're validating* — so the wording says "could not read"
 * rather than "was too small" wherever the input was unreadable.
 */
const SIZING_GLOSS: Record<string, string> = {
  refused: "the sizer refused this one — no size could be computed",
  bankroll_unobserved:
    "no observed account balance to size against — the bankroll is not derived",
  exposure_unreadable:
    "couldn't read how much is already at risk, so no size is safe to compute",
  position_unreadable:
    "couldn't read what's already held on this market, so the per-market cap can't apply",
  daily_pnl_unreadable:
    "couldn't read today's profit and loss, so the daily loss limit can't apply",
  max_daily_loss_dollars:
    "the daily loss limit is hit — the kill switch is on and no price changes that",
};

export type GlossedCode = {
  /** The engine's own name for the rule, rendered verbatim. */
  code: string;
  /**
   * The sentence, or `null` for a code this build has never heard of.
   *
   * **Null, not a placeholder sentence.** An unknown code means the server is
   * running a rule this frontend predates — a deploy-skew fact worth seeing —
   * and inventing wording for it would hide exactly that. The house rule
   * applies: unreadable resolves to nothing, never to something plausible.
   */
  gloss: string | null;
};

/**
 * Split a `suppressed_reason` into its codes and their sentences.
 *
 * **The field is a comma-joined composite** of every check that failed, not a
 * single code — `backend/analysis/joint_bound.py:280` is the note that keeps
 * having to be re-learned, and a `.includes()` on the whole string matches
 * substrings across the boundary. Splitting on `,` is the only safe read; no
 * code contains a comma, and they all contain underscores.
 *
 * Empty, whitespace and `null` all return `[]` — a row with no reason is not a
 * row with an unknown reason, and the caller renders nothing for it.
 */
export function glossSuppression(reason: string | null | undefined): GlossedCode[] {
  if (!reason) return [];
  return reason
    .split(",")
    .map((code) => code.trim())
    .filter((code) => code.length > 0)
    .map((code) => ({ code, gloss: glossOne(code) }));
}

/** One code to one sentence, across both vocabularies. `null` when unknown. */
function glossOne(code: string): string | null {
  if (code.startsWith("sizing:")) {
    return SIZING_GLOSS[code.slice("sizing:".length)] ?? null;
  }
  return GLOSS[code] ?? null;
}

/**
 * One line for a whole `suppressed_reason`, for places with room for a
 * sentence but not a list.
 *
 * Joined with "; " rather than ", " deliberately: the codes themselves are
 * comma-joined, so a comma between sentences reads as another code.
 * Unknown codes contribute nothing here — they are still visible as codes.
 */
export function glossSentence(reason: string | null | undefined): string | null {
  const parts = glossSuppression(reason)
    .map((g) => g.gloss)
    .filter((g): g is string => g !== null);
  return parts.length > 0 ? parts.join("; ") : null;
}
