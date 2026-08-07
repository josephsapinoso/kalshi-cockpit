import { fetchDashboards, formatAge, type Panel } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * The measurement screen, backed by the dbt marts.
 *
 * Two ordering decisions carry the whole point of this page:
 *
 * **Multiple comparisons goes first.** It is the single row that says how many
 * tests produced the findings below it. Reading a two-sigma bucket without it is
 * exactly how ten cells and one lucky hit become "we found something" — which
 * this project has already done once, on data generated with no edge at all.
 *
 * **Verdict strings are rendered verbatim and are never converted to numbers.**
 * The marts emit `(noise)` and "insufficient sample: 36 of 300" as *text*
 * precisely so a chart cannot be drawn through them. Reformatting those into a
 * plottable value here would undo the guard in the one place it is easiest to
 * undo it.
 *
 * **Suppressing a cell means suppressing what reconstructs it.** This page
 * previously claimed the line above while rendering `implied` and `actual` on
 * every calibration row — and `gap = actual - implied`, so the suppressed
 * finding sat one subtraction away in two adjacent columns. On the seeded demo
 * that read `73.0c | 46 | 73.0% | 52.2% | (noise)`, which hands the reader the
 * 20.8-point result the guard exists to withhold. A guard that hides the
 * conclusion and prints its inputs has not hidden anything.
 *
 * So censoring happens in the mart, not here: `actual_display`, `pnl_display`,
 * `beat_close_display` and `clv_display` arrive already reduced to `(noise)`
 * when the cell cannot support a finding. The raw columns still exist for
 * analysis; the presentation layer simply never receives an uncensored result.
 * `implied_probability` and `n` stay raw because neither is a result — one is
 * the price paid, the other the sample size, and both are true regardless of
 * what happened.
 */
export default async function DashboardsPage() {
  let data;
  try {
    data = await fetchDashboards();
  } catch (error) {
    return (
      <Shell>
        <Header />
        <div className="rounded-2xl border bg-card p-6">
          <p className="font-semibold">The warehouse has not been built.</p>
          <p className="mt-3 text-sm text-muted">
            This screen reads dbt marts over the Parquet lake, so it needs both
            steps:
          </p>
          <pre className="mt-4 overflow-x-auto rounded-xl border bg-background p-4 font-mono text-xs">
            python -m backend.store.publish{"\n"}
            cd warehouse &amp;&amp; dbt build
          </pre>
          <p className="mt-4 text-sm text-muted">
            An empty dashboard would read as &ldquo;nothing to report&rdquo;. This
            is a different thing, so it says so.
          </p>
          <p className="mt-2 font-mono text-xs text-muted">
            {error instanceof Error ? error.message : "unknown error"}
          </p>
        </div>
      </Shell>
    );
  }

  const panels = data.panels;

  return (
    <Shell>
      <Header />

      <div className="mb-8 rounded-2xl border bg-card p-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted">
          Read this first
        </p>
        <Verdicts panel={panels["mart_multiple_comparisons"]} />
        <p className="mt-4 text-sm text-muted">
          Roughly one cell in twenty clears two standard errors by chance. A
          finding only means something once it beats the count of tests that
          produced it.
        </p>
      </div>

      <PanelBlock
        title="Closing-line value"
        subtitle="The primary signal, by the price actually paid. CLV needs 200–300 bets before it says anything at all."
        panel={panels["mart_clv_by_bucket"]}
        columns={[
          { key: "price_bucket_cents", label: "Bucket", format: (v) => `${v}c` },
          { key: "n", label: "n" },
          // The pre-censored column, not `beat_close_rate`. Rendering the raw
          // rate beside "insufficient sample: 36 of 300" showed the result
          // while the verdict said there wasn't one.
          { key: "beat_close_display", label: "Beat close", mono: true },
          { key: "verdict", label: "Verdict", wide: true },
        ]}
      />

      <PanelBlock
        title="Calibration"
        subtitle="Did things priced at X% happen X% of the time? A model can win often and still be badly calibrated, which produces sizing that is wrong in a direction P&L cannot show."
        panel={panels["mart_calibration"]}
        columns={[
          { key: "price_bucket_cents", label: "Bucket", format: (v) => `${v}c` },
          { key: "n", label: "n" },
          // Implied is the price paid -- a known input, not a result -- so it
          // is shown raw. Actual is the outcome, and `actual - implied` IS the
          // gap, so it comes from the censored column. Rendering both operands
          // beside a `(noise)` cell handed the reader the finding to
          // reconstruct by subtraction.
          { key: "implied_probability", label: "Implied", format: pct },
          { key: "actual_display", label: "Actual", mono: true },
          { key: "gap_display", label: "Gap", mono: true },
        ]}
      />

      <PanelBlock
        title="Suppression audit"
        subtitle="Did each rule reject bets that would have lost? A rule whose rejections beat the close is too tight, and that is a finding about the rule."
        panel={panels["mart_suppression_audit"]}
        columns={[
          { key: "rule_name", label: "Rule", mono: true },
          { key: "n_rejected", label: "Rejected" },
          { key: "verdict", label: "Verdict", wide: true },
        ]}
      />

      <PanelBlock
        title="Fee reconciliation"
        subtitle="Predicted fee against what Kalshi actually charged. A mismatch is stop-the-line: every EV figure in the system is wrong by an unknown amount until it is fixed."
        panel={panels["mart_fee_reconciliation"]}
        emptyNote="No fills yet, so the fee model is still an unresolved hedge. It charges the most expensive plausible model until real fills settle it."
        columns={[
          { key: "price_bucket_cents", label: "Bucket", format: (v) => `${v}c` },
          { key: "n_fills", label: "Fills" },
          { key: "mean_predicted", label: "Predicted", mono: true },
          { key: "mean_actual", label: "Actual", mono: true },
          { key: "verdict", label: "Verdict", wide: true },
        ]}
      />

      <p className="mt-10 border-t pt-6 text-sm text-muted">
        Built {formatAge(Date.now() - data.warehouse_built_ms)}.{" "}
        {data.freshness_note}
      </p>
    </Shell>
  );
}

type Column = {
  key: string;
  label: string;
  mono?: boolean;
  wide?: boolean;
  format?: (value: string | number | boolean | null) => string;
};

const pct = (v: string | number | boolean | null) =>
  typeof v === "number" ? `${(v * 100).toFixed(1)}%` : String(v ?? "—");

function PanelBlock({
  title,
  subtitle,
  panel,
  columns,
  emptyNote,
}: {
  title: string;
  subtitle: string;
  panel: Panel | undefined;
  columns: Column[];
  emptyNote?: string;
}) {
  return (
    <section className="mb-10">
      <h2 className="display text-2xl">{title}</h2>
      <p className="mt-2 max-w-2xl text-sm text-muted">{subtitle}</p>

      {!panel || panel.status === "unavailable" ? (
        <div className="mt-4 rounded-2xl border bg-card p-6 text-sm text-muted">
          Unavailable — not unknown to be empty, but genuinely unknown.{" "}
          {panel?.note}
        </div>
      ) : panel.status === "empty" ? (
        <div className="mt-4 rounded-2xl border bg-card p-6 text-sm text-muted">
          {emptyNote ?? panel.note}
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <div className="min-w-full divide-y border-t">
            <div className="hidden gap-4 py-2 text-xs font-semibold uppercase tracking-widest text-muted sm:flex">
              {columns.map((c) => (
                <span key={c.key} className={c.wide ? "flex-1" : "w-24 shrink-0"}>
                  {c.label}
                </span>
              ))}
            </div>
            {panel.rows.map((row, i) => (
              <div
                key={i}
                className="flex flex-col gap-1 py-3 sm:flex-row sm:gap-4"
              >
                {columns.map((c) => {
                  const raw = row[c.key];
                  const text = c.format ? c.format(raw) : String(raw ?? "—");
                  return (
                    <span
                      key={c.key}
                      className={[
                        c.wide ? "flex-1" : "w-24 shrink-0",
                        c.mono || !c.wide ? "font-mono text-sm" : "text-sm",
                        // `(noise)` is muted deliberately: it is the absence of
                        // a result, and it should not draw the eye like one.
                        text === "(noise)" ? "text-muted" : "",
                      ].join(" ")}
                    >
                      <span className="mr-2 text-xs text-muted sm:hidden">
                        {c.label}
                      </span>
                      {text}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function Verdicts({ panel }: { panel: Panel | undefined }) {
  if (!panel || panel.status !== "ok" || panel.rows.length === 0) {
    return (
      <p className="mt-2 text-sm text-muted">
        No powered tests yet — nothing below has been qualified.
      </p>
    );
  }
  return (
    <>
      {panel.rows.map((row, i) => (
        <p key={i} className="mt-2 text-lg leading-snug">
          {String(row.verdict ?? "")}
        </p>
      ))}
    </>
  );
}

function Header() {
  return (
    <header className="mb-8">
      <h1 className="display text-4xl sm:text-5xl">Dashboards</h1>
      <p className="mt-3 max-w-xl text-lg text-muted">
        What the record does and does not establish. Cells that cannot clear the
        noise guard say <span className="font-mono">(noise)</span> rather than
        showing a number — a number there gets read as a result whatever caveat
        sits beside it.
      </p>
    </header>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-4xl px-6 py-12 sm:py-16">{children}</div>;
}
