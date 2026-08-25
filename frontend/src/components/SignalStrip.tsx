import type { Signal } from "@/lib/api";
import { formatAge } from "@/lib/api";
import Hint from "@/components/Hint";

/**
 * What everything below this strip is worth, stated where the cards are read.
 *
 * The defect: this product asserted a conclusion — that the consensus-only
 * signal does not work — and published the measurement behind it **nowhere**.
 * `beta` appeared zero times in `frontend/src`. A reader could look at a full
 * Board of prices and edges with no way to learn that the number generating
 * them has been measured and came back negative.
 *
 * Three rules govern what this may say, and each of them is a rule the record
 * has already been wrong about at least once:
 *
 * 1. **`UNRESOLVED` may not be rendered as "no signal".** The registration
 *    forbids declaring below 300 clusters and that look has not been taken.
 *    CLAUDE.md's "for planning, treat it as settled" is an instruction about
 *    roadmaps, not a verdict, and this strip is not a roadmap.
 * 2. **`beta_hat` never appears without `se_cluster`, `G` and the interval.**
 *    The API makes that structurally hard — there is no top-level `beta_hat`
 *    to read — and this component does not undo it.
 * 3. **The smallest resolvable effect is shown before the effect.** At
 *    `G = 199` it is larger than the estimate, which is the entire content of
 *    UNRESOLVED: the test cannot yet resolve what it measured. Leading with
 *    `-0.14` invites reading a precision that is not there.
 *
 * It is deliberately quiet. This is context for the cards, not a card.
 */
export default function SignalStrip({
  signal,
  now,
}: {
  signal: Signal | null;
  now: number;
}) {
  // Fetched with `.catch(() => null)` upstream: the strip is context for the
  // Board, not a precondition of it. Losing it must not turn a page full of
  // prices into an error, and rendering a placeholder that looks like a
  // measured zero would be worse than rendering nothing.
  if (!signal) return null;

  if (!signal.available) {
    return (
      <section className="rounded-2xl border bg-card px-5 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Signal test
          </span>
          <span className="font-mono text-sm text-muted">not computable here</span>
        </div>
        <p className="mt-1.5 max-w-[65ch] text-sm leading-relaxed text-muted">
          {/*
            This is the demo instance's normal state, and saying so plainly
            matters more than it looks. The seeded history has no book quotes
            to join, so the registered half-spread control is missing on every
            row and the precondition refuses. A screen that instead reported
            the cluster count would publish `G = 420` — a *larger* number than
            the live record's — off a database with no signal in it.
          */}
          No look was taken: {signal.refusal ?? "the population failed a precondition."}{" "}
          A refusal is not a result, and it is not a small effect.
        </p>
      </section>
    );
  }

  const e = signal.estimate!;
  const {
    clusters,
    clusters_to_declare,
    clusters_remaining,
    rows,
    modal_config_applied,
    modal_config_version,
    non_modal_rows_excluded,
  } = signal.population;

  return (
    <section className="rounded-2xl border bg-card">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 pt-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">
          Signal test
        </span>
        <span className="font-mono text-sm font-semibold">{signal.verdict}</span>
        <span className="tabular text-sm text-muted">
          {clusters} of {clusters_to_declare} games
        </span>
        <span className="ml-auto tabular text-xs text-muted">
          measured {formatAge(now - signal.computed_ms)}
        </span>
      </div>

      <p className="mt-1.5 max-w-[65ch] px-5 text-sm leading-relaxed text-muted">
        {signal.may_declare ? (
          <>
            The record has reached the registered floor of {clusters_to_declare}{" "}
            games, so this verdict is a declaring one. It was fixed in advance in{" "}
            <code className="rounded bg-accent-soft px-1 py-0.5 font-mono text-xs text-accent">
              {signal.registration}
            </code>
            .
          </>
        ) : (
          <>
            {/*
              The exact wording is load-bearing. "Not yet resolved" and "no
              signal" are different answers and the registration permits only
              the first below the floor.
            */}
            <strong className="font-semibold text-foreground">Not yet resolved</strong> —
            and that is not the same as no signal. The registration forbids
            declaring either way below {clusters_to_declare} games;{" "}
            {clusters_remaining} to go. Every interval measured so far sits below
            the threshold, but the rule says wait, so the screen says wait.
          </>
        )}
      </p>

      {/*
        WHICH population the count is on, whenever it is not the whole record.

        Added 2026-08-25. This screen displayed "NO SIGNAL — 311 of 300 games"
        on 2026-08-24, and the 311 was a fit pooled across four strategy config
        versions; the registered primary was 216, below the floor. The count and
        the floor were both honest and the sentence between them was not,
        because nothing on the page said which games were being counted. A
        number compared against a threshold has to name its population.
      */}
      {modal_config_applied && (
        <p className="mt-1 max-w-[65ch] px-5 text-xs leading-relaxed text-muted">
          Counting <strong className="font-semibold text-foreground">
            strategy version {String(modal_config_version)}
          </strong>{" "}
          only. The registration runs the primary on the most common version
          alone when the record holds more than one, so {non_modal_rows_excluded}{" "}
          rows written under earlier versions are excluded from this figure —
          a mixture of strategies is not one strategy measured for longer.
        </p>
      )}

      <dl className="mt-0 flex flex-wrap gap-x-6 gap-y-2 border-t px-5 py-3 font-mono text-xs text-muted">
        {/*
          Resolving power before the estimate. Reading the effect first is how
          a small cell gets believed, and this cell cannot resolve its own
          point estimate.
        */}
        <Stat
          label="smallest resolvable"
          value={fmt(e.smallest_resolvable_beta)}
          title="The smallest beta this many clusters could distinguish from zero. Printed before the estimate on purpose."
        />
        <Stat label="beta" value={fmt(e.beta_hat)} title="Tenths of realised closing-line value per tenth of claimed edge." />
        <Stat label="se" value={e.se_cluster.toFixed(4)} title="Cluster-robust. The classical error understates this by roughly 2.6x here." />
        <Stat
          label="interval"
          value={`[${fmt(e.interval_lower)}, ${fmt(e.interval_upper)}]`}
          title="Always-valid, so it holds however many times it is looked at."
        />
        <Stat label="rows" value={rows.toLocaleString()} title="Recommendations in the registered population." />
      </dl>

      {/*
        A pooled number is not a finding until the parts agree. These two do not
        agree closely (-0.08 against -0.52 on the current record), which is
        exactly why the repo rule requires them beside the aggregate rather than
        behind a link.
      */}
      {signal.by_market_type.length > 1 && (
        <dl className="flex flex-wrap gap-x-6 gap-y-2 border-t px-5 py-3 font-mono text-xs text-muted">
          <span className="font-sans text-muted">by market type, diagnostic only:</span>
          {signal.by_market_type.map((arm) => (
            <Stat
              key={arm.name}
              label={arm.name}
              value={
                arm.beta_hat === null
                  ? "refused"
                  : `${fmt(arm.beta_hat)} · ${arm.clusters}g · ${(arm.share * 100).toFixed(0)}%`
              }
              title="market_type is not a registered cut. This view can downgrade a verdict and can never create one."
            />
          ))}
        </dl>
      )}
    </section>
  );
}

/** Signed, four places. The sign is the whole story and must never be dropped. */
function fmt(n: number): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(4)}`;
}

function Stat({
  label,
  value,
  title,
}: {
  label: string;
  value: string;
  title: string;
}) {
  /* The explanation opens on tap, not only on hover (2026-08-22 review,
     A6): these six statistics carried their caveats in title= attributes,
     which a phone cannot open at all. Hint keeps hover as the desktop
     shortcut and gives every reader the tap. */
  return (
    <div className="flex items-baseline gap-1.5">
      <dt>
        <Hint hint={title}>{label}</Hint>
      </dt>
      <dd className="tabular font-semibold text-foreground">{value}</dd>
    </div>
  );
}
