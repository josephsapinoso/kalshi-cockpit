import { fetchGate } from "@/lib/api";
import Term from "@/components/Term";

export const dynamic = "force-dynamic";

/**
 * Plain headlines for the gate's condition names — the suppressionGloss
 * treatment this screen never adopted (2026-08-22 review, A5): the headline
 * is for the reader, the engine's own name stays as the caption, so the
 * vocabulary the backend logs in is still on the screen a bug report quotes.
 * An unknown name renders as itself — a condition this build has not met
 * gets no invented headline.
 */
const CONDITION_HEADLINES: Record<string, string> = {
  scored_recommendations: "Enough scored games to mean something",
  clv_survives_noise_guard: "The record beats random chance",
  fee_model_verified: "The fee model matches real fills",
  config_enabled: "The live-trading switch is on",
  data_fresh: "The data is fresh at this moment",
};

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
          gate.open ? "border-positive/50" : "border-accent-2/60"
        } bg-card`}
      >
        <div className="text-xs font-semibold uppercase tracking-widest text-muted">
          Status
        </div>
        <div
          className={`display mt-2 text-3xl ${
            gate.open ? "text-positive" : "text-accent-2"
          }`}
        >
          {gate.open ? "Open" : "Locked"}
        </div>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          <Term k="bankroll">Bankroll</Term>{" "}
          {gate.bankroll_dollars === null
            ? "unobserved (no balance snapshot yet)"
            : `$${gate.bankroll_dollars.toFixed(2)}`}
          , from the venue&rsquo;s own balance record.{" "}
          <Term k="kelly">Quarter-Kelly</Term> sizing with per-bet,
          per-position and total-<Term k="exposure">exposure</Term> caps, plus
          a daily-loss kill switch fed by the venue&rsquo;s settled record,
          refused when stale.
        </p>
        {/* The scope sentence, rewritten per ADR 0064 §3: each cap names its
            channel, and the daily-loss switch names its new source. The old
            blanket sentence ("they do not see, and cannot stop, bets you
            place yourself") stopped being accurate the day the switch was
            rewired to `venue_settlements` -- hand losses DO count against
            the line now; what has not changed is that the only act any cap
            can stop is this tool's own next order. Scope sentences that
            outlive their wiring are how the last hole stayed open (the
            switch read an empty table for two months while this screen
            advertised it), so tests/test_scope_sentences.py pins these
            words to the wiring. */}
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Each cap has a channel. The per-bet, position and{" "}
          <Term k="exposure">exposure</Term> caps bind orders placed through
          this tool — a channel that has never carried one. The daily-loss
          switch draws its number from the venue&rsquo;s settled record —
          every bet however placed, hand bets included, refused when the
          mirror is stale — so your hand losses count against the line. But
          the only act any of these caps can stop is this tool&rsquo;s next
          order: a bet you place yourself in the Kalshi app fires no check
          before it happens, and the record sees it only after the venue
          settles it.
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
                  : "bg-accent-2-soft text-accent-2"
              }`}
            >
              {condition.met ? "✓" : "—"}
            </span>
            <div>
              <div className="text-sm font-semibold">
                {CONDITION_HEADLINES[condition.name] ?? condition.name}
              </div>
              {CONDITION_HEADLINES[condition.name] && (
                <div className="font-mono text-xs text-muted">
                  {condition.name}
                </div>
              )}
              <div className="mt-1 max-w-[65ch] text-sm text-muted">
                {condition.detail}
              </div>
            </div>
          </li>
        ))}
      </ul>

      <div className="mt-10 rounded-2xl border border-edge bg-card p-6">
        <h3 className="text-lg font-bold tracking-tight">
          Why 300, and not fifty
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          <Term k="clv">Closing-line value</Term> is the fastest honest signal
          available &mdash; far
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
