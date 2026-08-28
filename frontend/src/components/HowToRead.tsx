/**
 * Four sentences, always on screen.
 *
 * A beginner asked for tooltips and this is the answer instead, for two
 * reasons. There is no hover on a phone, so a tooltip becomes a tap target —
 * sitting inside a row whose own tap target opens an order screen. And the
 * things that trip someone up here are not vocabulary, they are decision rules
 * that run against instinct: nobody guesses that the break-even is 52 rather
 * than 50, or that the biggest number on the board is the one being withheld.
 * A definition on hover cannot say either of those.
 *
 * Four, and no more. A permanent block earns its place by being read once and
 * remembered; a wall of them gets scrolled past like a cookie banner.
 */
export default function HowToRead() {
  return (
    <section className="mb-8 rounded-2xl border border-edge bg-card p-5 sm:p-6">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
        How to read this board
      </h2>
      <ul className="mt-4 max-w-[65ch] space-y-3 text-sm leading-relaxed text-muted">
        <li>
          <span className="font-semibold text-foreground">
            You need to be right 52 times in 100 here, not 50.
          </span>{" "}
          A coin flip loses money on this venue, because the exchange takes a
          fee on the winning side. Kalshi&rsquo;s fee is lower than a
          sportsbook&rsquo;s — 51.75% against 52.38% — and that 0.63-point gap
          is the entire advantage this tool was built to hunt. Every edge on
          this page is already net of the fee.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            That hunt is finished, and it found nothing.
          </span>{" "}
          The 0.63 points are real but they are a <em>discount, not a signal</em>
          — a cheaper venue multiplies an edge, it cannot create one. This tool
          spent its life looking for the edge to multiply and measured every
          place it could reach. The answer was no. The rows below are what the
          engine proposes; the record says the engine&rsquo;s proposals do not
          predict where Kalshi closes.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            The price is the one in cents. The percentage is not a price.
          </span>{" "}
          &ldquo;Consensus fair 53.8%&rdquo; is how often the sportsbooks think
          this happens; &ldquo;Kalshi asks 50.3c&rdquo; is what a contract costs.
          Buying at 50.3c something that happens 53.8% of the time is the whole
          trade — and it is worth about three cents, not three dollars.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            The biggest edge on the board is deliberately held back.
          </span>{" "}
          Anything above roughly four cents is treated as a bug until proven
          otherwise, because the spread between the four devigging methods alone
          is larger than the advantage being hunted. Rows marked{" "}
          <span className="font-mono text-xs">REJECTED</span> below say which
          check refused them. A rule that fires constantly is a finding about
          the rule, which is why they are shown rather than hidden.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            The swing is far larger than the edge, every time.
          </span>{" "}
          A bet worth twenty-six cents in expectation still moves seven or eight
          dollars either way when it settles. Ten bets like that end the week
          down almost half the time <em>with the edge completely real</em>, so a
          losing week is not evidence the tool is broken and is not a reason to
          bet bigger.
        </li>
      </ul>
    </section>
  );
}
