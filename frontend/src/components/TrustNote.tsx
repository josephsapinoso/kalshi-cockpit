/**
 * The sweet spot: how much a number on this screen deserves to be acted on.
 *
 * **One component, three surfaces.** Joe chose the parlay card, the slate row
 * and the market screen on 2026-08-31 (ADR 0090); the card shipped first and
 * this file is the extraction that let the other two have it without a second
 * drawing. The same reasoning as `DispersionStrip variant="chart"`: the
 * honesty properties below are only guaranteed while there is one
 * implementation of them.
 *
 * **Evidence quality, never bet quality.** The score counts checks the desk
 * already refuses on; it is not scored against an outcome and contains no edge
 * term. That exclusion is arithmetic rather than taste — `beta = -0.141` with
 * every interval below the registered 0.40 threshold, so a composite carrying
 * the consensus-vs-Kalshi gap would rank the *least* trustworthy rows highest.
 *
 * Four properties this component exists to keep, each with the failure it
 * prevents:
 *
 * - **The denominator is `known`, not `total`.** Scoring against `total`
 *   counts a check nobody ran as a miss, which punishes a row for a look that
 *   never happened.
 * - **The unknowns are counted, and counted INSIDE the score's own styled
 *   span.** `total - known` is how many checks nobody ran. Hiding it makes the
 *   least-examined row look like the best one — the `market_width = 0.0`
 *   failure `suppression.py` records. Putting it *after* the span is the
 *   2026-08-31 typography defect: `EVIDENCE 7/7 CHECKS · 1 not checked` reads
 *   as a perfect score with a footnote, and a reader stops at 7/7.
 * - **Every failure is named, never just the first.** Choosing which one to
 *   show would be the importance weight `core/trust.py` refuses to invent.
 * - **No colour and no ordering.** The palette's red means *lose* (ADR 0081)
 *   and a failing evidence check is not a loss; ADR 0071 §2.5 bars ranking by
 *   a per-row fact.
 *
 * `size` changes the type scale and nothing else. `compact` is the parlay
 * card's, where six legs share one card; `panel` is for a screen that gives
 * this its own block. The caveat stays inside the score span in both — the
 * one property a size prop could plausibly break, and the one the tests pin
 * on both values.
 *
 * The clean-row sentence says "here", not "on this leg", and that is the
 * extraction's one wording change: the same words now sit on a parlay leg, a
 * slate row and a market screen, and a noun true of one of them is a lie on
 * the other two.
 */

import type { TrustScore } from "@/lib/api";

export default function TrustNote({
  trust,
  size = "compact",
}: {
  trust: TrustScore | null | undefined;
  size?: "compact" | "panel";
}) {
  if (!trust) return null;
  const unknown = trust.total - trust.known;
  const failures = trust.checks.filter((c) => c.state === "fail");
  const scale = size === "panel" ? "text-xs" : "text-[0.6rem]";
  // **The prose sets its own size rather than inheriting one.** On the parlay
  // card the failure list sat inside an `11px` list item and looked right; the
  // first slate row put the identical element in a row with no size class, and
  // it rendered at body size — the loudest text on a row whose every other
  // caption is `text-xs`. A component whose weight depends on where it is
  // hosted has no consistent typography, and this component's honesty rules
  // are rules about what a reader actually sees (the 2026-08-31 lesson).
  //
  // `text-[11px]` is exactly what the card was already rendering, so extracting
  // this changed nothing there.
  const prose = size === "panel" ? "text-xs" : "text-[11px] leading-relaxed";
  // **`break-words`, and it is load-bearing rather than defensive.** The
  // failure list embeds `suppressed_reason` verbatim, and that is often
  // several codes joined by commas with no spaces —
  // `stale_odds,too_few_books,no_market_width,edge_within_method_spread` — so
  // it reaches a line-breaker as ONE token with no break opportunity in it.
  //
  // Measured on live at a true 390px viewport, 2026-08-31: this span ran to
  // `scrollWidth` 404 inside a 327px column and pushed the whole document to
  // 428 against a 390 viewport, so the slate scrolled sideways on a phone.
  // It is data-dependent — an identical read an hour earlier measured a clean
  // 375, because no row on the slate then carried a long multi-code reason.
  return (
    <span className={`block break-words text-muted ${prose}`}>
      {/*
        **The unknown count sits INSIDE the styled span, not after it, and that
        is the whole point of this element.** Shipped 2026-08-31 with the count
        outside it, which rendered as

            EVIDENCE 7/7 CHECKS · 1 not checked

        — a loud perfect score with a lowercase footnote. The words were right
        and the typography subordinated them, which defeated the rule by a
        route no wording test could see: a reader stops at 7/7. Caught by
        looking at the live screen, which is the only thing that would have.

        Same register, one phrase, so the gap cannot be skimmed past.
      */}
      <span className={`font-mono ${scale} uppercase tracking-wide`}>
        evidence {trust.passed}/{trust.known} checks
        {unknown > 0 && <> · {unknown} not checked</>}
      </span>
      {failures.length > 0 && (
        <span className="block">
          {failures.map((f) => f.detail).join("; ")}.
        </span>
      )}
      {failures.length === 0 && unknown === 0 && (
        <span className="block">
          Every check the desk can run here passed. That is about the
          evidence, not about whether the bet wins.
        </span>
      )}
    </span>
  );
}
