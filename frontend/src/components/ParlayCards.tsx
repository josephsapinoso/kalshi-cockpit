import Link from "next/link";

import { DISPLAY_TIME_ZONE } from "@/lib/api";
import type { ParlayCardData, ParlayLadder } from "@/lib/api";
import Term from "@/components/Term";

/**
 * The ladder: three parlay cards at fair value (ADR 0070).
 *
 * Renders what the server worded and adds nothing to it. Honesty rules,
 * each load-bearing:
 *
 * - **Every money string arrives pre-rendered.** The stake row is a set of
 *   presets the server already priced; this component does no arithmetic
 *   (the `lib/api.ts` rule) — a stake it did not receive is a stake it
 *   cannot show.
 * - **The four caveat sentences render verbatim from the payload** — the
 *   fair-vs-quoted distinction, the enter-only warning, and the unverified
 *   fee are the server's claims, so the server's words carry them.
 * - **No `bg-accent`.** Red means money moves; nothing on this screen
 *   transacts (the lookup button arrives with the lookup slice and will be
 *   the one red thing here).
 * - **A card that could not be built says why, in words**, in the same slot
 *   it would have rendered — an absent card and an unbuildable card are
 *   different facts.
 * - **Nothing behind a reveal** (ADR 0068): every leg, band, and caveat is
 *   fully present.
 */
export default function ParlayCards({ ladder }: { ladder: ParlayLadder }) {
  return (
    <div className="space-y-8">
      <div className="grid gap-6 lg:grid-cols-3">
        {ladder.cards.map((card) => (
          <Card key={card.key} card={card} />
        ))}
      </div>
      <Excluded excluded={ladder.excluded} />
      <section className="max-w-[65ch] space-y-2 text-xs leading-snug text-muted">
        <p>{ladder.notes.fair_value}</p>
        <p>{ladder.notes.enter_only}</p>
        <p>{ladder.notes.fee}</p>
      </section>
    </div>
  );
}

function Card({ card }: { card: ParlayCardData }) {
  return (
    <section
      aria-label={`${card.title} card`}
      className="flex flex-col rounded-lg border border-border p-4"
    >
      <header className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-widest">
          {card.title}
        </h2>
        {card.joint && (
          <span className="tabular text-lg font-semibold">
            {card.joint.conservative_percent_display}
          </span>
        )}
      </header>

      {card.not_built_reason !== null ? (
        <p className="mt-3 text-sm text-muted">
          Not built tonight: {card.not_built_reason}.
        </p>
      ) : (
        <>
          <p className="mt-1 text-xs text-muted">
            <Term k="joint_chance">joint chance</Term> that every{" "}
            <Term k="leg">leg</Term> hits
            {card.joint?.method_range_display && (
              <>
                {" "}
                <span className="tabular">
                  (methods span {card.joint.method_range_display})
                </span>
              </>
            )}
          </p>
          <ol className="mt-3 flex-1 divide-y divide-border">
            {card.legs.map((leg) => (
              <li
                key={leg.ticker}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-1.5"
              >
                <span className="tabular w-11 shrink-0 font-mono text-[11px] text-muted">
                  {kickoff(leg.commence_ms)}
                </span>
                <Link
                  href={`/market/${encodeURIComponent(leg.ticker)}`}
                  className="min-w-0 truncate text-sm font-semibold tracking-tight hover:underline"
                >
                  {leg.label}
                </Link>
                <span className="tabular text-xs text-muted">
                  {leg.fair_percent_display}
                </span>
              </li>
            ))}
          </ol>
          {card.joint && (
            <p className="mt-2 text-xs text-muted">
              <Term k="fair_value">Fair value</Term>:{" "}
              <span className="tabular">{card.joint.fair_cost_display}</span>.{" "}
              {card.joint.correlation_note}
            </p>
          )}
          <Stakes card={card} />
        </>
      )}
    </section>
  );
}

function Stakes({ card }: { card: ParlayCardData }) {
  if (card.at_stakes.length === 0) return null;
  return (
    <div className="mt-3 border-t border-border pt-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted">
        At fair value, a stake would buy
      </h3>
      <ul className="mt-1 space-y-0.5">
        {card.at_stakes.map((stake) => (
          <li
            key={stake.stake_cents}
            className={`tabular flex justify-between text-xs ${
              stake.is_default ? "font-semibold" : "text-muted"
            }`}
          >
            <span>{stake.stake_display}</span>
            <span>
              {stake.contracts_display} contracts → {stake.payout_display} if
              all hit
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Excluded({ excluded }: { excluded: Record<string, number> }) {
  const entries = Object.entries(excluded).filter(([, n]) => n > 0);
  if (entries.length === 0) return null;
  return (
    <p className="max-w-[65ch] text-xs leading-snug text-muted">
      Left out:{" "}
      {entries
        .map(([reason, n]) => `${n} ${EXCLUSION_WORDS[reason] ?? reason}`)
        .join("; ")}
      .
    </p>
  );
}

/** Server reason codes, in words a non-professional reads cold. */
const EXCLUSION_WORDS: Record<string, string> = {
  stale_consensus: "sides whose consensus is too old to trust",
  age_unmeasurable: "sides whose consensus age was never recorded",
  not_a_probability: "sides without a usable chance",
  no_kalshi_market: "sides with no matching Kalshi market",
  market_closed: "sides whose Kalshi market is already closed",
};

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
