import Term from "@/components/Term";

/**
 * The five-step pre-bet test, authored by the sharp-bettor reviewer
 * (2026-08-18) after the definition had been referenced in three session
 * entries without ever being written down.
 *
 * Static content, deliberately: nothing here reads the database, so no step
 * can drift into an interim aggregate over the estimate log (registration
 * §0.2). If this ever moves into `backend/playbook.py`, it must stay
 * constant text — a step that quotes a live count is an embargo leak wearing
 * an educational face.
 *
 * What the author refused to include, recorded so nobody "completes" it
 * later: line shopping, best-number chasing, and beat-the-move execution.
 * Those steps only pay when an edge exists, this project measured that none
 * does (ADR 0038), and teaching them here would teach that the shopping is
 * the point. The point is the record.
 */

type Step = {
  name: string;
  body: React.ReactNode;
  cost: string;
  drill: string;
};

const STEPS: Step[] = [
  {
    name: "Say what you know that the price doesn't.",
    body: (
      <>
        Out loud, one sentence, before you bet: what do I know that the
        person selling to me does not? A price is not something the venue
        made up. It is where people risking their own money stopped
        disagreeing, and it already contains the injury news, the weather,
        the starting lineup and the podcast take. Usually the honest answer
        is &ldquo;nothing&rdquo; &mdash; and that is a complete, professional
        answer. This project went hunting for a durable{" "}
        <Term k="edge">edge</Term> across every corner it could reach and
        measured that there wasn&rsquo;t one. Bet anyway if you enjoy it;
        just name it correctly while you do: entertainment, with a good
        record attached.
      </>
    ),
    cost:
      "This is how a hobby hardens into a conviction — you start believing " +
      "a screen is telling you something, and no number on this site has " +
      "ever been shown to predict anything.",
    drill:
      "Write the sentence down before you tap. If it needs the word " +
      "“feel” or “due”, you have found nothing — log " +
      "the estimate anyway and skip the bet.",
  },
  {
    name: "Price it at the ask, then add the fee.",
    body: (
      <>
        The only number that matters is the <Term k="ask">ask</Term> &mdash;
        what actually leaves your account right now &mdash; never the mid,
        and never the price you saw ten minutes ago; check the{" "}
        <Term k="quote_age">quote age</Term>, because an hours-old quote is
        history, not an offer. Then add Kalshi&rsquo;s{" "}
        <Term k="fee">fee</Term>, which is biggest near a coin flip: about
        1.75c per contract at 50c, so a $2 bet there costs roughly 7c to
        place. That moves the bar. At a 50c ask you must be right about
        51.75% of the time simply to break even (a sportsbook at &minus;110
        needs 52.38%, which is the whole of Kalshi&rsquo;s advantage &mdash;
        a discount on your losses, not a reason to bet). On a NO bet, do the same arithmetic against the NO ask.
      </>
    ),
    cost:
      "You will take a run of bets you scored in your head as coin flips, " +
      "every one of them quietly a few cents worse than a coin flip.",
    drill:
      "Before you look, guess the ask to the nearest 5c. Being able to " +
      "price a game from your own number, then check, is the skill; the " +
      "screen is just the answer key.",
  },
];

export default function FiveStepTest() {
  return (
    <section className="mb-12">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
        The pre-bet steps
      </h2>
      <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted">
        This tool was built to find an edge on Kalshi, and it did not find
        one &mdash; that result is the honest product, and it is on this
        page. So these steps are not a way to win money; they are the
        whole difference between a bet you learn something from and a bet
        that merely happens to you. Run them in order, every time. It
        takes about twenty seconds.
      </p>
      <ol className="mt-6 space-y-5">
        {STEPS.map((step, index) => (
          <li key={step.name} className="rounded-2xl border border-edge bg-card p-5">
            <div className="flex items-baseline gap-3">
              <span className="font-mono text-sm font-semibold text-accent">
                {index + 1}
              </span>
              <h3 className="font-semibold tracking-tight">{step.name}</h3>
            </div>
            <p className="mt-2 text-sm leading-relaxed">{step.body}</p>
            <p className="mt-3 text-xs leading-relaxed text-muted">
              <strong className="text-foreground">Skip it and:</strong>{" "}
              {step.cost}
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              <strong className="text-foreground">Drill:</strong> {step.drill}
            </p>
          </li>
        ))}
      </ol>
      {/* Joe's answer (C) to #239, 2026-09-30: no fixed stop rule, and the
          Playbook says so rather than inventing one. The fixed two-dollar
          stake and the hundred-dollar lifetime stop this page taught until
          then were never his rules. */}
      <p className="mt-6 max-w-xl text-sm leading-relaxed text-muted">
        <strong className="text-foreground">Stop rule:</strong> you have not
        set one, so this page does not pretend you have. The desk sets no
        <Term k="stake">stake</Term> size and no loss limit for you. If you decide on one, it goes
        here.
      </p>
    </section>
  );
}
