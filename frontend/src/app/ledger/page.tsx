import { fetchLedger, formatAge } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Every recommendation, surfaced or not.
 *
 * This is the evidence base rather than a history of bets: each row is scored
 * on closing-line value whether or not money was placed on it, which is what
 * makes three hundred scored observations reachable without three hundred
 * wagers.
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
        <h1 className="display text-4xl sm:text-5xl">Ledger</h1>
        <p className="mt-3 max-w-xl text-lg text-muted">
          Every candidate the engine judged, kept with its reasoning. Scored on
          closing-line value whether or not it was bet.
        </p>
      </header>

      <div className="mb-10 rounded-2xl border bg-card p-6">
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted">
            Scored on CLV
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
          {ledger.gate_open
            ? "The gate is open."
            : "The gate stays locked until this clears and the record survives the noise guard."}
        </p>
      </div>

      <div className="divide-y border-t">
        {ledger.rows.map((rec) => (
          <div
            key={rec.id}
            className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-4"
          >
            <span className="font-mono text-xs text-muted">
              {formatAge(Date.now() - rec.created_ms)}
            </span>
            <span className="font-semibold tracking-tight">
              {rec.team ?? rec.ticker}
            </span>
            <span className="tabular text-sm text-muted">
              {rec.fair_display} fair / {rec.ask_display} ask
            </span>
            <span
              className={`tabular text-sm font-semibold ${
                rec.edge_cents > 0 ? "text-positive" : "text-negative"
              }`}
            >
              {rec.edge_cents > 0 ? "+" : ""}
              {rec.edge_cents.toFixed(1)}c
            </span>
            {rec.suggested_contracts > 0 ? (
              <span className="rounded-full bg-accent-soft px-3 py-0.5 font-mono text-xs text-accent">
                buy {rec.suggested_contracts}
              </span>
            ) : rec.suppressed_reason ? (
              <span className="font-mono text-xs text-muted">
                {rec.suppressed_reason}
              </span>
            ) : (
              <span className="font-mono text-xs text-muted">no edge</span>
            )}
          </div>
        ))}
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-3xl px-6 py-12 sm:py-16">{children}</div>;
}
