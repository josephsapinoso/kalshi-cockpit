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
        {/* Ticket #9's ratified Gate lede (Joe, 2026-08-27), verbatim. The
            sentence it replaced -- "the tool has to demonstrate an edge before
            it is allowed to act on one" -- was pre-ADR-0038 framing: the hunt
            is closed, the edge was measured and it was negative, and nothing
            here is waiting to be earned. The gate is the live-trading
            interlock on the engine path and is never lowered (ADR 0038 §3).
            No count or status figure is baked into this string, on purpose:
            the live number renders in the Conditions list below, and a
            figure written here would go stale the next time the runner
            wrote a row. */}
        <p className="mt-3 max-w-xl text-lg text-muted">
          The lock on this tool ever placing a bet by itself — which it has
          never done, and the code that would send an order is switched off
          behind the lock as well. The bets you place by hand go through a
          different door with its own limits, and this lock never touches
          them.
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
        {/* The scope sentences, and they have been wrong in BOTH directions.
            ADR 0064 §3 fixed the first: each cap names its channel, and the
            daily-loss switch names its new source, because the old blanket
            sentence ("they do not see, and cannot stop, bets you place
            yourself") stopped being accurate the day the switch was rewired
            to `venue_settlements`.

            The second was live from 2026-08-26 to 2026-08-29 and was worse,
            because a test was pinning it. This screen said "the only act any
            of these caps can stop is this tool's next order: a bet you place
            yourself in the Kalshi app fires no check before it happens", and
            called this tool's channel "one that has never carried one". Both
            halves went stale the day `MANUAL_ORDERS_ARE_DRY_RUNS` was set to
            False (ADR 0073): the Buy button on a market page sends a REAL
            immediate-or-cancel order, and the route runs a dozen server-side
            refusals before it leaves (backend/api/routes.py, the numbered
            list on `place_manual_order`).

            THE DISTINCTION THAT MUST SURVIVE EVERY REWRITE OF THIS COPY:
            arming the Buy button did not arm the engine, and the 300-game
            count on this page never covered hand bets and never will.
            `gate.py` does not read `manual_orders` -- that separation is the
            whole reason ADR 0063 built a second table and a second constant.
            So the true sentence is not "the gate now covers hand bets"; it
            is "hand bets are guarded by something else, named here".

            Scope sentences that outlive their wiring are how the last hole
            stayed open, so tests/test_scope_sentences.py pins these words to
            the wiring -- pointed, since 2026-08-29, at what is true. */}
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Each cap has a channel, and which door you use decides what can stop
          you. The per-bet, position and{" "}
          <Term k="exposure">exposure</Term> caps bind every order this tool
          sends, and two things here can send one. The automated engine never
          has: it is still in dry run — it writes down the order it would have
          placed and sends nothing — and the 300-game count below is the
          interlock holding it there. That count is a reading, not a plan: the
          interlock is never lowered or bypassed, and nothing on this desk
          waits for it to open.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          The Buy button on a market page is the other, and since 26 August
          2026 it sends real orders — one contract at a time, at your tap.
          The 300-game count does not cover it, by design: this gate never
          looks at your hand bets, so arming that button did not arm the
          engine. What guards it instead is a dozen checks the server runs
          before the order leaves, none of them waivable from the phone — the
          desk lockout, the ten-minute cool-off after your last order, the
          daily-loss switch, the caps above (all derived from the balance the
          venue reports, never a number you type), a refusal if the ask has
          moved above the price you agreed to, a check that enough contracts
          are really resting at that ask, and a refusal if you already hold
          this market. Any one of them stops the order.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          The daily-loss switch draws its number from the venue&rsquo;s
          settled record — every bet however placed, hand bets included,
          refused when the mirror is stale — so your hand losses count
          against the line. What nothing here can stop is the third door: a
          bet you place yourself in the Kalshi app fires no check before it
          happens, and the record sees it only after the venue settles it.
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
