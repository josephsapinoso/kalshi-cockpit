import { fetchGate } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Why execution is locked.
 *
 * The gate defaults to closed and this page exists so that "closed" is never
 * mysterious. Each unmet condition states the specific number that has to
 * move, because a refusal without a reason is not actionable.
 */
export default async function GatePage() {
  let gate;
  try {
    gate = await fetchGate();
  } catch {
    return (
      <Shell>
        <p className="text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="mb-10">
        <h1 className="display text-4xl sm:text-5xl">Live gate</h1>
        <p className="mt-3 max-w-xl text-lg text-muted">
          Order placement stays locked until the paper record earns it. This is
          the whole safeguard: the tool has to demonstrate an edge before it is
          allowed to act on one.
        </p>
      </header>

      <div
        className={`mb-10 rounded-2xl border p-6 ${
          gate.open ? "border-positive/50" : "border-accent/50"
        } bg-card`}
      >
        <div className="text-xs font-semibold uppercase tracking-widest text-muted">
          Status
        </div>
        <div
          className={`display mt-2 text-3xl ${
            gate.open ? "text-positive" : "text-accent"
          }`}
        >
          {gate.open ? "Open" : "Locked"}
        </div>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Bankroll{" "}
          {gate.bankroll_dollars === null
            ? "unobserved (no balance snapshot yet)"
            : `$${gate.bankroll_dollars.toFixed(2)}`}
          , from the venue&rsquo;s own balance record. Quarter-Kelly sizing
          with per-bet, per-position and total-exposure caps, plus a daily-loss
          kill switch.
        </p>
        {/* Structural, not copy: `settlements.order_id` is NOT NULL and
            references `orders(id)`, so every cap above is evaluated against
            orders this tool placed -- and it has never placed one. A hand bet
            in the Kalshi app is invisible to all of it, and a screen that
            advertises a kill switch without saying so is advertising
            protection Joe does not have. Fleet convening item 2,
            docs/reviews/2026-08-20-fleet-convening.md. */}
        <p className="mt-3 text-sm leading-relaxed text-muted">
          These caps govern orders this tool would place. They do not see, and
          cannot stop, bets you place yourself in the Kalshi app.
        </p>
      </div>

      <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
        Conditions
      </h2>
      <ul className="mt-6 divide-y border-t">
        {gate.conditions.map((condition) => (
          <li key={condition.name} className="flex items-start gap-4 py-5">
            <span
              className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold ${
                condition.met
                  ? "bg-positive/15 text-positive"
                  : "bg-accent-soft text-accent"
              }`}
            >
              {condition.met ? "✓" : "—"}
            </span>
            <div>
              <div className="font-mono text-sm font-semibold">
                {condition.name}
              </div>
              <div className="mt-1 text-sm text-muted">{condition.detail}</div>
            </div>
          </li>
        ))}
      </ul>

      <div className="mt-10 rounded-2xl border bg-card p-6">
        <h3 className="text-lg font-bold tracking-tight">
          Why 300, and not fifty
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Closing-line value is the fastest honest signal available &mdash; far
          faster than win rate, which needs on the order of a thousand bets to
          separate 52% from 50%. But &ldquo;faster&rdquo; still means hundreds:
          practitioner consensus puts the floor at 200&ndash;300 bets, with
          500&ndash;1,000 before CLV predicts much. Every recommendation is
          scored whether or not it was bet, which is what makes that reachable
          without wagering three hundred times.
        </p>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-3xl px-6 py-12 sm:py-16">{children}</div>;
}
