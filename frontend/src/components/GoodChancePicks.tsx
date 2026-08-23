import Link from "next/link";

import { DISPLAY_TIME_ZONE } from "@/lib/api";
import type { SlatePicks } from "@/lib/api";
import Term from "@/components/Term";

/**
 * Who's likely to win tonight (ADR 0067).
 *
 * The block that answers Joe's actual question — "what are good-chance
 * picks" — which is a different question from the one the Board asks. The
 * Board asks whether Kalshi is *mispriced*, and the measured answer is
 * almost always no; this asks which side the books' consensus makes the
 * favorite, which has an answer every night. The server ranks by
 * `fair_probability` alone (one stored, unscored column — a sort, never a
 * composite) and this component renders the ranking without adding to it.
 *
 * Honesty constraints, each load-bearing:
 *
 * - **The chance≠edge note renders verbatim from the payload**, so the
 *   server and the screen cannot disagree about what this block claims.
 * - **No break-even, edge, or size figure appears here** — fair% beside
 *   break-even hands the reader the measured-negative edge by subtraction
 *   (the fleet-convening identity). The rows below this block carry
 *   break-even; the two never share a block.
 * - **Nothing here is tappable into an order.** Each entry links to the
 *   game's own screen and nowhere else. No `bg-accent` (red = money), no
 *   urgency ink, no count of how many picks "hit" — a favorites list must
 *   not become a chase surface.
 * - Games the server could not rank are counted in words — "no pick" and
 *   "no measurement" are different facts.
 */
export default function GoodChancePicks({
  picks,
}: {
  picks: SlatePicks | null | undefined;
}) {
  if (!picks) return null;
  const { ranked, not_ranked } = picks;
  const skipped = not_ranked.stale_consensus + not_ranked.favorite_unpriced;
  if (ranked.length === 0 && skipped === 0) return null;
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
        Likely winners tonight
      </h2>
      <p className="mt-1 max-w-prose text-xs leading-snug text-muted">
        Each game&rsquo;s <Term k="favorite">favorite</Term> by the
        books&rsquo; <Term k="consensus_chance">chance to win</Term>. {picks.note}
      </p>
      {ranked.length > 0 && (
        <ol className="mt-3 divide-y divide-border">
          {ranked.map((pick) => (
            <li
              key={pick.ticker}
              className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2"
            >
              <span className="tabular w-12 shrink-0 font-mono text-xs text-muted">
                {kickoff(pick.commence_ms)}
              </span>
              <Link
                href={`/market/${encodeURIComponent(pick.ticker)}`}
                className="min-w-0 truncate font-semibold tracking-tight hover:underline"
              >
                {pick.team ?? pick.ticker}
              </Link>
              <span className="tabular text-sm font-semibold">
                {pick.fair_percent_display ?? "—"}
              </span>
              <span className="tabular text-xs text-muted">
                {pick.ask_display === null
                  ? "ask not current"
                  : `${pick.ask_display} ask`}
              </span>
              {pick.anchored_on_sharp === false && (
                <span className="text-xs text-accent-2">soft fallback</span>
              )}
              {pick.event_title && (
                <span className="min-w-0 truncate text-xs text-muted">
                  {pick.event_title}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
      {skipped > 0 && (
        <p className="mt-2 max-w-prose text-xs leading-snug text-muted">
          {not_ranked.stale_consensus > 0 &&
            `${not_ranked.stale_consensus} game${
              not_ranked.stale_consensus === 1 ? "" : "s"
            } not ranked: the consensus is too old to speak. `}
          {not_ranked.favorite_unpriced > 0 &&
            `${not_ranked.favorite_unpriced} game${
              not_ranked.favorite_unpriced === 1 ? "" : "s"
            } not ranked: no fresh price on the favorite's side.`}
        </p>
      )}
      <p className="mt-2 max-w-prose text-xs leading-snug text-muted">
        The chance shown is the same consensus the sharp books quote — every
        public factor is already <Term k="priced_in">priced in</Term>. The
        game&rsquo;s own screen has the desk&rsquo;s full read.
      </p>
    </section>
  );
}

/** Pacific, matching the slate rows' kickoff column. */
function kickoff(ms: number | null): string {
  if (ms === null) return "--:--";
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
