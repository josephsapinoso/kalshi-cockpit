import { SHELL_WIDTH } from "@/lib/shell";
import { fetchHedge } from "@/lib/api";
import HedgePositions from "@/components/HedgePositions";
import RecordParlay from "@/components/RecordParlay";
import Term from "@/components/Term";

export const dynamic = "force-dynamic";

/**
 * Tickets Joe holds, and what hedging one would do (ADR 0078).
 *
 * The one screen in the product that reads a market **while the game is
 * running**, because that is the only time a hedge is wanted. It writes no
 * `recommendations` row, so ADR 0006's evidence guard is untouched, and it
 * spends nothing: Kalshi reads are unmetered and no model is fitted — the
 * venue's live price already carries the score and the inning.
 *
 * **What it will and will not claim.** With one leg live and the rest already
 * won, hedging has a dollar answer that is true whichever way the last leg
 * goes, and the screen states it. With several legs live it has none, and the
 * screen says so instead of approximating one. Neither case says the price
 * will get worse if he waits — that is the market's own number and nothing in
 * this repo beats it (ADR 0071 §2.5, `beta = -0.141`).
 *
 * **No nav slot.** The six-link budget is load-bearing at 390px (ADR 0073);
 * this is reached from /bets, where what he holds already lives, and from the
 * link in the alert itself.
 */
export default async function HedgePage() {
  let screen;
  try {
    screen = await fetchHedge();
  } catch {
    return (
      <Shell>
        <p className="max-w-[65ch] text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="mb-2">
        <h1 className="display text-4xl sm:text-5xl">Hedging</h1>
        <p className="mt-3 max-w-[65ch] text-sm leading-relaxed text-muted">
          Tickets you hold, priced against what the other side costs on Kalshi
          right now. When one <Term k="leg">leg</Term> is left and the rest
          have won, a <Term k="hedge">hedge</Term> has an exact answer — a{" "}
          <Term k="lock">lock</Term>. Before that it can only{" "}
          <Term k="derisk">de-risk</Term>.
        </p>
        <p className="mt-2 max-w-[65ch] text-xs leading-relaxed text-muted">
          {screen.notes.not_advice}
        </p>
        <p className="mt-1 max-w-[65ch] text-xs leading-relaxed text-muted">
          {screen.notes.no_button}
        </p>
      </header>

      <HedgePositions positions={screen.positions} notes={screen.notes} />
      <RecordParlay />
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${SHELL_WIDTH} px-4 py-12 sm:px-6 sm:py-16 xl:px-8`}>
      {children}
    </div>
  );
}
