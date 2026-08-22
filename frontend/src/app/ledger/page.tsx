import {
  EDGE_TONE_CLASS,
  EDGE_TONE_MARK,
  edgeTone,
  fetchLedger,
  formatAge,
} from "@/lib/api";

import { glossSentence } from "@/lib/suppressionGloss";
import { tickerLabel } from "@/lib/tickerLabel";
import Term from "@/components/Term";

export const dynamic = "force-dynamic";

/**
 * Every recommendation, surfaced or not.
 *
 * This is the evidence base rather than a history of bets: each row is scored
 * on closing-line value whether or not money was placed on it, which is what
 * makes three hundred scored observations reachable without three hundred
 * wagers.
 *
 * **Named "Evidence" in the nav, not "Ledger", since 2026-08-22.** `/bets`
 * shipped 2026-08-21 as Joe's own settled-bet record, which is what "ledger"
 * means to a reader outside this codebase; keeping this page's old name
 * would have put two different things behind the one word a beginner reaches
 * for first. Route and function names (`/ledger`, `fetchLedger`) are
 * unchanged, matching the pattern `/board` already set under "Picks" --
 * only the visible name moved.
 *
 * **Colour is a claim, not the sign of a subtraction.** This screen lists every
 * recommendation the database holds — suppressed rows included, since a refused
 * row is the evidence — and it coloured the edge on `rec.edge_cents > 0` alone.
 * That is the Board's defect one screen over, and worse here: the Board shows a
 * windowed slate, this page shows the whole record, so every `suspicious_edge`
 * row ever written rendered in the colour that means take this. The tone now
 * comes from `edgeTone`, the same call the Board's `SlateRow` makes, because a
 * second copy of the rule is a second chance to paint green over a defect.
 */
export default async function LedgerPage() {
  let ledger;
  try {
    ledger = await fetchLedger();
  } catch {
    return (
      <Shell>
        <p className="text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  const progress = Math.min(100, (ledger.clv_scored / ledger.clv_required) * 100);

  return (
    <Shell>
      <header className="mb-8">
        <h1 className="display text-4xl sm:text-5xl">Evidence</h1>
        <p className="mt-3 max-w-xl text-lg text-muted">
          Every candidate the engine judged, kept with its reasoning. Scored on
          closing-line value whether or not it was bet.
        </p>
      </header>

      <div className="mb-10 rounded-2xl border bg-card p-6">
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted">
            Independent games scored on <Term k="clv">CLV</Term>
          </span>
          <span className="tabular text-sm text-muted">
            {ledger.clv_scored} / {ledger.clv_required}
          </span>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full border">
          <div
            className="h-full bg-accent transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="mt-3 text-sm text-muted">
          Counted in games, not rows. The engine writes a fresh row every pass,
          but all of a game&rsquo;s rows score against one closing line, so they
          are one observation recorded many times &mdash;{" "}
          <span className="tabular">{ledger.clv_scored_rows}</span> rows here.
        </p>
        <p className="mt-2 text-sm text-muted">
          {ledger.gate_open
            ? "The gate is open."
            : "The gate stays locked until this clears and the record survives the noise guard."}
        </p>
      </div>

      <div className="divide-y border-t">
        {ledger.rows.map((rec) => {
          /**
           * **Not `edge_cents > 0`.** That is the sign of a subtraction; this
           * is a claim about whether the number is money. See `edgeTone`.
           */
          const tone = edgeTone(rec);
          return (
            <div
              key={rec.id}
              className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-4"
            >
              <span className="font-mono text-xs text-muted">
                {formatAge(Date.now() - rec.created_ms)}
              </span>
              <span className="font-semibold tracking-tight" title={rec.ticker}>
                {rec.team ?? tickerLabel(rec.ticker)}
              </span>
              {/* Fair value as a percentage, ask as a price. Rendering both
                  with a `c` suffix put a probability and a price side by side in
                  the same unit, and only one of them is money. */}
              <span className="tabular text-sm text-muted">
                {rec.fair_percent_display} fair / {rec.ask_display} ask
              </span>
              <span
                className={`tabular text-sm font-semibold ${EDGE_TONE_CLASS[tone]}`}
              >
                {EDGE_TONE_MARK[tone]}
                {rec.edge_cents > 0 ? "+" : ""}
                {rec.edge_cents.toFixed(1)}c
              </span>
              {rec.suggested_contracts > 0 ? (
                <span className="rounded-full bg-accent-soft px-3 py-0.5 font-mono text-xs text-accent">
                  buy {rec.suggested_contracts}
                </span>
              ) : rec.suppressed_reason ? (
                /* Code then caption, the same order as everywhere else. The
                   code is the engine's name for the rule; the sentence is for
                   a reader who has not memorised twelve identifiers. See
                   `frontend/src/lib/suppressionGloss.ts` for why it is never a
                   replacement. */
                <span className="flex flex-col items-end gap-0.5 text-right">
                  <span className="font-mono text-xs text-muted">
                    {rec.suppressed_reason}
                  </span>
                  {glossSentence(rec.suppressed_reason) && (
                    <span className="max-w-[28ch] text-xs leading-snug text-muted">
                      {glossSentence(rec.suppressed_reason)}
                    </span>
                  )}
                </span>
              ) : (
                <span className="font-mono text-xs text-muted">no edge</span>
              )}
              {/* **The score, on the scoreboard.** `clv_tenths` has been
                  serialised at `routes.py` since the evidence layer was built
                  and rendered nowhere, so this page showed the progress bar
                  towards 300 scored games and never the result of scoring any
                  of them.

                  `null` is *unscored*, which is most rows and is not a zero:
                  a game whose closing line has not been recorded yet has no
                  CLV, and printing 0.0c there would be the flattering reading
                  of an absence. Said in words rather than left blank, because a
                  blank cell reads as "nothing happened". */}
              <span className="ml-auto shrink-0 font-mono text-xs">
                {rec.clv_tenths === null ? (
                  <span className="text-muted">clv —</span>
                ) : (
                  <span
                    className={
                      rec.clv_tenths > 0 ? "text-positive" : "text-negative"
                    }
                  >
                    clv {rec.clv_tenths > 0 ? "+" : ""}
                    {(rec.clv_tenths / 10).toFixed(1)}c
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>

      {/* One permanent sentence, once, where CLV is. Not a tooltip: there is
          no hover on a phone, and a tap target here would compete with
          nothing useful. */}
      <p className="mt-8 border-t pt-6 text-sm leading-relaxed text-muted">
        <span className="font-semibold text-foreground">
          CLV is the only scoreboard that works at this volume.
        </span>{" "}
        It asks whether the price you were offered beat Kalshi&rsquo;s own
        closing line — the last price before the game starts, when everyone who
        is going to bet has bet. Positive CLV means you were early to a move.
        Profit and loss needs roughly 2,500 settled bets to say anything at
        all; CLV says it in a few hundred, which is why the gate counts these
        and not dollars.
      </p>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-3xl px-6 py-12 sm:py-16">{children}</div>;
}
