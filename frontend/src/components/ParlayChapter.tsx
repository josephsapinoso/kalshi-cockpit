import Term from "@/components/Term";

/**
 * The Playbook's parlay chapter (#328, part of #320). Joe asked to be taught,
 * and combinations are nearly all of what he bets, yet the five steps say
 * nothing about them. Behind a tap, below the five steps; the one-line
 * version of this is the cost line at the moment of buying
 * (`lib/parlayCost.ts`).
 *
 * Static text, deliberately, like `FiveStepTest`: no screen number is quoted
 * live. Every figure below is arithmetic on a price or a dated measurement
 * named where it appears.
 *
 * **What it refuses.** No sentence claims a factor predicts anything, calls a
 * price cheap or good or an edge, or ranks anything (ADR 0071, ADR 0189
 * section 5). Counts, prices and arithmetic only. The craft paragraph draws
 * on the public record of professional betting (Wong, Sharp Sports Betting)
 * and speaks for no one.
 */
export default function ParlayChapter() {
  return (
    <details className="mb-10 rounded-2xl border border-edge bg-card p-6">
      <summary className="cursor-pointer text-sm font-semibold uppercase tracking-widest text-muted">
        Parlays: what the price is telling you
      </summary>

      <ol className="mt-4 space-y-4 text-sm leading-relaxed text-muted">
        <li>
          <span className="font-semibold text-foreground">
            The price is the chance.
          </span>{" "}
          A <Term k="parlay">parlay</Term> priced at 12 cents wins about 1
          time in 8 if the <Term k="maker">makers</Term> are right; one priced
          at 5 cents, about 1 in 20. No pick inside the card changes that
          much: the price already folds all of them in.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            Adding a <Term k="leg">leg</Term> multiplies.
          </span>{" "}
          Three 80% legs land together 51% of the time; six land 26% of the
          time (<Term k="joint_chance">the chance every leg hits</Term>). A
          90% &ldquo;safe&rdquo; leg still loses the whole card 1 time in 10,
          and adds only about 11% more payout.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            The <Term k="fee">fee</Term> is charged once, at the card&rsquo;s
            price.
          </span>{" "}
          It is the coefficient times (1 minus the price), taken as a{" "}
          <Term k="fee_share">share of your stake</Term>: about 6.65% at 5
          cents, 5.25% at 25 cents, 3.5% at 50 cents (the 2026-08-18 fee
          look). The same picks bought as <Term k="single">singles</Term> pay
          about half that share, because each leg is charged at its own
          price. Baseball fills have been charged about half of that usual rate.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            Makers quote privately and differ.
          </span>{" "}
          Asking sends a <Term k="rfq">request for a quote</Term>; each{" "}
          <Term k="maker_quote">quote</Term> is one maker&rsquo;s price. On
          the two recorded asks the makers sat 3.8 cents and 36.6 cents
          apart. Only the best quote is the price, and the desk lists every
          one.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            Selling back exists, and it usually costs.
          </span>{" "}
          On 2026-09-17 every bid on the three combinations this desk held
          sat below what had been paid. What you paid is a{" "}
          <Term k="sunk_cost">sunk cost</Term>; only the bid now against
          holding to the result matters.
        </li>
        <li>
          <span className="font-semibold text-foreground">
            The scoreboard is on Your bets.
          </span>{" "}
          &ldquo;Expected vs won&rdquo; adds up each bet&rsquo;s price as a
          chance (<Term k="expected_wins">expected to win</Term>) beside what
          actually won, with a <Term k="plausible_range">range</Term>. It
          shows counts and no verdict, and says &ldquo;too few&rdquo; below 5
          expected on each side.
        </li>
      </ol>

      <h3 className="mt-6 text-xs font-semibold uppercase tracking-widest text-muted">
        The craft
      </h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted">
        <li>
          A parlay multiplies whatever you know about each pick, and it
          multiplies the cost. Choose the fewest legs that express the
          opinion.
        </li>
        <li>No opinion on a leg? Leave it off the card.</li>
        <li>
          Ask the makers every time, before taking the book&rsquo;s price.
        </li>
        <li>
          The drill: before opening a card, say its chance out loud. Then
          check the line under the price.
        </li>
      </ul>
    </details>
  );
}
