"use client";

import type { MarketDetail } from "@/lib/api";
import DispersionStrip from "@/components/DispersionStrip";
import FairValueSteps from "@/components/FairValueSteps";
import Term from "@/components/Term";

/**
 * The consensus, fully present on the game's screen (ADR 0068).
 *
 * This panel renders the books' side of the comparison — the devigged
 * consensus chance, which books produced it, how much they disagree, and
 * how Kalshi's own tape has moved — and the standing explanation Joe asked
 * for of why the tool computes no sport factors of its own.
 *
 * ADR 0068 supersedes, on the owner's word, the 2026-08-21 ruling that fair
 * never appears on a single-game page. What it does NOT supersede:
 * **break-even never renders beside fair%** — their difference is exactly
 * the measured-negative edge (`edge_tenths = 1000 × (fair − breakeven)`),
 * so this panel must never grow a break-even, edge, or EV figure. The
 * payload does not even carry `breakeven_win_rate` for this screen.
 *
 * `fair_probability` is side-denominated: on a NO-side row it is the chance
 * the YES team *loses*. The sentence names the side explicitly rather than
 * letting a chance sit beside the wrong team name.
 */
export default function ConsensusPanel({ detail }: { detail: MarketDetail }) {
  const hasFair =
    typeof detail.fair_probability === "number" &&
    detail.fair_percent_display != null;
  return (
    <section id="consensus" className="mt-6 rounded-2xl border bg-card p-4 sm:p-6 xl:p-8">
      <h2 className="text-lg font-semibold xl:text-xl">The consensus</h2>

      {!hasFair ? (
        <p className="mt-2 max-w-[65ch] text-sm text-muted">
          No consensus is stored for this market — the record never joined a
          devigged fair value to it. That is an absence, not a verdict.
        </p>
      ) : (
        <>
          <p className="mt-2 max-w-[65ch] text-sm">
            <span className="tabular text-2xl font-semibold">
              {detail.fair_percent_display}
            </span>{" "}
            <span className="text-muted">
              — the books&rsquo;{" "}
              <Term k="consensus_chance">chance to win</Term>
              {detail.team && detail.side === "yes" && (
                <> for the {detail.team}</>
              )}
              {detail.team && detail.side === "no" && (
                <>
                  {" "}
                  that the {detail.team} <em>don&rsquo;t</em> win (this row
                  prices the NO side)
                </>
              )}
              , their margins removed (<Term k="devig">devigged</Term>) and
              the worst of four methods taken.
            </span>
          </p>

          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            {detail.anchored_on_sharp === true &&
              detail.books_used &&
              detail.books_used.length > 0 && (
                <>
                  Anchored on the sharp books: {detail.books_used.join(", ")}.{" "}
                </>
              )}
            {detail.anchored_on_sharp === false && (
              <>
                No sharp book quoted this market — the fair value fell back
                to the full soft-book set, a wider and weaker consensus.{" "}
              </>
            )}
            {typeof detail.market_width === "number" && (
              <>
                The anchored books disagree with each other by{" "}
                {(detail.market_width * 100).toFixed(1)} points — the
                consensus&rsquo;s own error bar.
              </>
            )}
          </p>

          <FairValueSteps detail={detail} />

          <div className="mt-3">
            <DispersionStrip
              /* Present, not behind a reveal: ADR 0068 puts the desk's five
                 areas fully on this screen, and this is the Consensus area's
                 own provenance. The slate row keeps the text-only variant. */
              variant="chart"
              books={detail.books ?? null}
              methods={detail}
              kalshiProbability={
                typeof detail.ask_dollars === "number"
                  ? detail.ask_dollars
                  : null
              }
              anchoredBookCount={detail.book_count ?? null}
            />
          </div>

          {typeof detail.kalshi_drift_tenths === "number" &&
            typeof detail.drift_window_ms === "number" && (
              <p className="mt-2 max-w-[65ch] text-xs text-muted">
                Kalshi&rsquo;s own price has moved{" "}
                {detail.kalshi_drift_tenths > 0 ? "+" : ""}
                {(detail.kalshi_drift_tenths / 10).toFixed(1)}c in the last{" "}
                {Math.round(detail.drift_window_ms / 60_000)} minutes.
              </p>
            )}
        </>
      )}

      {/* The standing explainer (ADR 0068, Joe's ask: "why isn't that
          explained in the site?"). Static product copy stating a documented
          conclusion (ADR 0036/0037), pinned by source-grep test. */}
      <p className="mt-4 max-w-[65ch] border-t pt-3 text-sm leading-relaxed text-muted">
        Starting pitchers, bullpens, weather, umpires, lineups — the sharp
        books have already <Term k="priced_in">priced them in</Term> to this
        line, and Kalshi tracks those books to within about a tenth of a
        cent. That is why this tool computes none of them itself: recomputing
        what the line already contains adds noise, not information — measured
        twice on this project&rsquo;s own models. What can matter is news
        newer than the line, and hunting that is the scouts&rsquo; whole job.
      </p>
    </section>
  );
}
