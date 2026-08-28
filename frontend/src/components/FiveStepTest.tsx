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
    name: "Write your number before you look.",
    body: (
      <>
        Open Log, tap the market, and type your{" "}
        <Term k="p_yes">P(YES)</Term> &mdash; your honest percent chance that
        market ends YES &mdash; before you open Kalshi. Not after. Not
        &ldquo;I&rsquo;ll remember what I thought.&rdquo; The moment you see
        the <Term k="ask">ask</Term>, your number quietly becomes the
        ask&rsquo;s number; that pull is called anchoring and it happens to
        everyone, which is exactly why the form asks whether you had already
        opened Kalshi and records your answer either way. Answer that one
        honestly: a &ldquo;yes&rdquo; still counts, it just gets labelled.
        This is the one habit that converts your betting from an evening out
        into evidence.
      </>
    ),
    cost:
      "The bet still happens, but it can never be scored — a number " +
      "remembered after the fact is just the price wearing your handwriting.",
    drill:
      "For a week, log five estimates a day on games you have no intention " +
      "of betting. Cheap reps, no money at risk, and the number you type " +
      "stops flinching.",
  },
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
        a discount on your losses, not a reason to bet). Now compare that bar
        to the <Term k="p_yes">P(YES)</Term> you wrote in step 1. On a NO
        bet, do the same arithmetic with 100 minus your number against the
        NO ask.
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
  {
    name: "Bet two dollars.",
    body: (
      <>
        The <Term k="stake">stake</Term> is $2. Not $2 unless it&rsquo;s a
        lock, not $5 to get even, not $1 because you&rsquo;re unsure &mdash;
        $2, every time, and if a bet isn&rsquo;t worth $2 it isn&rsquo;t
        worth the tap. A fixed stake is what makes the whole record readable:
        the moment size moves with how you feel, a good month tells you your
        feelings were good rather than your numbers, and you can no longer
        tell those apart. It also keeps the study alive. At $2 the chance of
        ever hitting the $100 lifetime stop is about 3.6%; at $5 it is about
        46%. The size is not a judgement call you get to make in the moment
        &mdash; it was made once, in advance, by someone calmer.
      </>
    ),
    cost:
      "Vary the size and you lose two things at once: the bankroll, to the " +
      "biggest bet, and any ability to tell whether the small ones were " +
      "any good.",
    drill:
      "Next time you want to bet more than $2, place the $2 and write down " +
      "what the extra would have been. Add that column up at the end of " +
      "the month and look at what it would have done.",
  },
  {
    name: "Know what would make you stop.",
    body: (
      <>
        Two rules are already written down, so know them before the bet
        rather than during it: $100 of cumulative{" "}
        <Term k="realised_loss">realised loss</Term> since the study opened
        ends this permanently, and the strip at the top of Log shows how much
        of it is spent. Running low on balance is not the stop &mdash; that
        is a top-up; the $100 is the stop. Then know what the scoreboard is
        not: tonight&rsquo;s win or loss is almost entirely luck, and a good
        week proves nothing whatsoever. Professionals score themselves on{" "}
        <Term k="clv">CLV</Term> &mdash; did their price beat the closing
        price. Yours is the same idea one clock earlier: your number against
        the price at the instant you typed it. You do not get to see it until
        the study ends, on purpose, because peeking would change the numbers
        you type.
      </>
    ),
    cost:
      "With no stopping rule fixed in advance, the rule you will actually " +
      "use is your mood — and your mood is at its most confident " +
      "immediately after a win.",
    drill:
      "Before each session, say the number you'd walk away at. Say it to " +
      "someone, or type it. A rule you only thought about is a rule you " +
      "will renegotiate at 11pm.",
  },
];

export default function FiveStepTest() {
  return (
    <section className="mb-12">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
        The five-step test
      </h2>
      <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted">
        This tool was built to find an edge on Kalshi, and it did not find
        one &mdash; that result is the honest product, and it is on this
        page. So these five steps are not a way to win money; they are the
        whole difference between a $2 bet you learn something from and a $2
        bet that merely happens to you. Run them in order, every time. It
        takes about twenty seconds, and the only optional step is the bet.
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
    </section>
  );
}
