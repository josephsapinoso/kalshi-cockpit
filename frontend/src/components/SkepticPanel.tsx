"use client";

import type { Gauntlet, MarketDetail } from "@/lib/api";
import { DISPLAY_TIME_ZONE } from "@/lib/api";
import { glossSuppression } from "@/lib/suppressionGloss";

/**
 * The Skeptic, fully present on the game's screen (ADR 0068) — and free.
 *
 * This panel IS the skeptic: the pipeline's twelve mechanical checks, each
 * with its verdict for this row, rendered code-verbatim with the gloss as a
 * caption beneath (ADR 0050: a label and a caption, never a translation).
 * The scheduled LLM Skeptic is retired (ADR 0062) — it burned a whole day's
 * API budget re-reviewing four rows — and nothing here calls a model or
 * spends anything.
 *
 * Honesty rules:
 * - **Refused first, then passed; `not_taken` is a muted footnote.** "Ran
 *   and passed" and "never ran" are different facts and must not collapse.
 * - **The as-of caption always renders.** The verdicts are facts about the
 *   moment the row was judged, not about now.
 * - **Unknown codes surface.** A newer server's rule renders as its bare
 *   code rather than silently vanishing — deploy skew is a fact worth
 *   seeing.
 */
export default function SkepticPanel({ detail }: { detail: MarketDetail }) {
  const gauntlet: Gauntlet | undefined = detail.gauntlet;
  return (
    <section id="skeptic" className="mt-6 rounded-2xl border border-edge bg-card p-4 sm:p-6 xl:p-8">
      <h2 className="text-lg font-semibold xl:text-xl">The skeptic</h2>
      <p className="mt-1 max-w-[65ch] text-sm text-muted">
        Twelve mechanical checks — no model, no spend. A rule of this house:
        a large apparent edge is a bug until proven otherwise, and these are
        the rules that catch the bugs.
      </p>

      {!gauntlet ? (
        <p className="mt-3 max-w-[65ch] text-sm text-muted">
          No verdicts served — this backend predates the skeptic board, or
          the record has no judged row for this market.
        </p>
      ) : (
        <>
          <VerdictList gauntlet={gauntlet} />
          {detail.reason_text && (
            <p className="mt-3 max-w-[65ch] text-sm text-muted">
              {detail.reason_text}
            </p>
          )}
          <p className="mt-3 max-w-[65ch] border-t pt-2 text-xs text-muted">
            Verdicts as of{" "}
            {gauntlet.judged_ms != null
              ? when(gauntlet.judged_ms)
              : "an unknown time"}{" "}
            — facts about when this row was judged, not about this moment.
          </p>
        </>
      )}
    </section>
  );
}

function VerdictList({ gauntlet }: { gauntlet: Gauntlet }) {
  const refused = gauntlet.checks.filter((c) => c.verdict === "refused");
  const passed = gauntlet.checks.filter((c) => c.verdict === "passed");
  const notTaken = gauntlet.checks.filter((c) => c.verdict === "not_taken");
  return (
    <div className="mt-3 space-y-3">
      {refused.length > 0 && (
        <ul className="space-y-2">
          {refused.map((check) => (
            <li key={check.code}>
              <span className="font-mono text-xs font-semibold text-accent-2">
                ✕ {check.code}
              </span>
              <Caption code={check.code} />
            </li>
          ))}
        </ul>
      )}
      {gauntlet.sizing.map((code) => (
        <p key={code}>
          <span className="font-mono text-xs font-semibold text-accent-2">
            ✕ {code}
          </span>
          <Caption code={code} />
        </p>
      ))}
      {gauntlet.unknown.map((code) => (
        <p key={code}>
          <span className="font-mono text-xs font-semibold text-accent-2">
            ✕ {code}
          </span>
          <span className="block max-w-[65ch] text-xs text-muted">
            a rule this build does not know — the server is newer than this
            screen
          </span>
        </p>
      ))}
      {refused.length === 0 &&
        gauntlet.sizing.length === 0 &&
        gauntlet.unknown.length === 0 && (
          <p className="max-w-[65ch] text-sm">
            Nothing refused — every check that ran, passed.
          </p>
        )}
      {passed.length > 0 && (
        <ul className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
          {passed.map((check) => (
            <li key={check.code} className="font-mono text-xs text-muted">
              ✓ {check.code}
            </li>
          ))}
        </ul>
      )}
      {notTaken.length > 0 && (
        <p className="max-w-[65ch] text-xs text-muted">
          Not taken (their sibling check ran instead):{" "}
          <span className="font-mono">
            {notTaken.map((c) => c.code).join(", ")}
          </span>
        </p>
      )}
    </div>
  );
}

/** The gloss beneath the code — a caption, never a replacement (ADR 0050).
 * Unknown codes caption nothing; the mono code above stays complete. */
function Caption({ code }: { code: string }) {
  const gloss = glossSuppression(code)[0]?.gloss ?? null;
  if (!gloss) return null;
  return (
    <span className="block max-w-[65ch] text-xs leading-snug text-muted">
      {gloss}
    </span>
  );
}

function when(ms: number): string {
  return new Date(ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
