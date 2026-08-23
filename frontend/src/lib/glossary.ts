/**
 * The site's plain-language glossary, in one place.
 *
 * Joe's standing instruction (2026-08-18): he is not a professional gambler
 * and every betting or statistics term the site uses must teach itself —
 * "educate me on this stuff", as tooltips. `<Term k="...">` renders any of
 * these as a tap-to-open definition. Add future terms HERE, not inline in a
 * page, so the same word never gets two explanations.
 *
 * House style for a definition: one or two short sentences, plain words, a
 * tiny example, no further jargon (or the jargon gets its own entry). These
 * render in a popover about 260px wide on a phone — keep them under ~45 words.
 */

export type GlossaryEntry = {
  /** The word as it should read in running text. */
  label: string;
  definition: string;
};

export const GLOSSARY = {
  p_yes: {
    label: "P(YES)",
    definition:
      "Your gut number for how likely this market ends YES, as a percent. " +
      "A coin flip is 50. It is always the chance of YES — not of “your " +
      "side”. Think YES only happens 30% of the time? Type 30; that low " +
      "number is itself the case for betting NO.",
  },
  quote_age: {
    label: "quote age",
    definition:
      "How long ago this market’s Kalshi price was last read. A quote from " +
      "40 seconds ago is usually still the real price; one from two hours " +
      "ago is history — the ask shown may not be what you’d actually pay.",
  },
  stale: {
    label: "stale",
    definition:
      "Too old to compare, not bad. Kalshi’s price moves second to second " +
      "while sportsbook lines are bought in scheduled windows; once the book " +
      "side ages past the freshness limit, the comparison is refused until " +
      "the odds are re-bought. The game and the price are both still real.",
  },
  realised_loss: {
    label: "realised loss",
    definition:
      "Money actually gone on bets that have finished — wins minus what " +
      "they cost, fees included. A bet still open doesn’t count yet. If " +
      "you staked $5, got $4 back, and paid 20¢ in fees, your realised " +
      "loss is $1.20.",
  },
  ask: {
    label: "ask",
    definition:
      "The price you would actually pay to buy right now — the sticker " +
      "price. There is also a “mid” (an average of buy and sell), " +
      "but nobody gets to pay the mid, so every judgement here uses the ask.",
  },
  breakeven: {
    label: "break-even",
    definition:
      "How often a bet at this price has to win for you to come out even, " +
      "with Kalshi's fee already counted. Pay 50c and you need about 51.75% " +
      "— not 50% — because the fee eats the difference. If you don't " +
      "honestly think it wins more often than this number, pass.",
  },
  fee: {
    label: "fee",
    definition:
      "Kalshi's cut, charged on each trade. Biggest near a coin flip " +
      "(about 1.75 cents per dollar at 50c) and smaller toward the " +
      "extremes. It is why “barely better than a coin flip” still " +
      "loses money.",
  },
  edge: {
    label: "edge",
    definition:
      "How much better than the price your estimate says the bet is, after " +
      "the fee. Positive edge means “if my number is right, this is " +
      "underpriced”. A huge edge is usually a mistake somewhere, not a " +
      "gift.",
  },
  stake: {
    label: "stake",
    // No dollar figure may ever appear in this definition. The previous
    // version instructed "$2, every time" — written when that was the plan,
    // still rendering after ADR 0045 derived the real cap at 26c on a $2.56
    // balance. A glossary that gives a number gives an order; the caps
    // screen owns the numbers. Pinned by test_glossary_coverage.py.
    definition:
      "The money put on one bet. Keep it a small fixed fraction of your " +
      "bankroll — the caps on this site compute yours from your actual " +
      "balance. Changing the stake because of the last result is how " +
      "bankrolls die.",
  },
  clv: {
    label: "CLV",
    definition:
      "Closing-line value: was your price better than the final price just " +
      "before the game started? Tonight's win or loss is mostly luck; " +
      "beating the close again and again is the real sign a bettor knows " +
      "something.",
  },
  ev: {
    label: "expected value",
    definition:
      "The average result if this exact bet were repeated many times. " +
      "+$0.10 expected on a $2 bet means that, on average, such bets earn " +
      "ten cents — any single one still just wins or loses.",
  },
  sd: {
    label: "swing",
    definition:
      "How far one normal result lands from the average — one standard " +
      "deviation. A $2 bet with a $1 swing routinely finishes a dollar " +
      "richer or poorer than expected. Bigger swing, bumpier ride.",
  },
  // `drift` and `candlestick` were removed 2026-08-22: the Drift chip
  // teaches in place with the row's own numbers (components/Hint.tsx), and
  // the candles view left the chart in the 2026-08-21 rebuild. A definition
  // nobody can reach is a plan, not a feature (test_glossary_coverage.py's
  // orphan rule).
  contract: {
    label: "contract",
    definition:
      "One unit of a Kalshi bet. A YES contract pays $1 if the market ends " +
      "YES, $0 if not. Buy at the ask: pay 40¢ and you either collect $1 " +
      "(minus fees) or lose the 40¢.",
  },
  consensus: {
    label: "consensus fair",
    definition:
      "What the sportsbooks together imply this outcome is really worth — " +
      "their margins removed, then combined. The tool's best estimate of a " +
      "true price. An estimate, not a fact: the books can all be wrong " +
      "together.",
  },
  devig: {
    label: "devig",
    definition:
      "Removing a bookmaker's built-in margin from its odds. A book prices " +
      "both sides so the chances add past 100% — that overage is its cut " +
      "(the vig). Devigging scales it out so the numbers read as honest " +
      "probabilities.",
  },
  settled: {
    label: "settled",
    definition:
      "Finished and paid out. A settled market's result is known: winning " +
      "contracts paid $1, losing ones $0, and the money has already moved " +
      "in your account.",
  },
  bankroll: {
    label: "bankroll",
    definition:
      "The money set aside for betting — here, the cash actually in your " +
      "Kalshi account. Every cap on this site is a fraction of it, so a " +
      "small bankroll means small bets, on purpose.",
  },
  depth: {
    label: "depth",
    definition:
      "How many contracts are actually available at this ask right now. " +
      "Depth 3 means you can buy 3 at that price; wanting more moves the " +
      "price against you.",
  },
  exposure: {
    label: "exposure",
    definition:
      "The total you could lose if every bet you have open lost, fees " +
      "included. The exposure cap bounds that total, so one bad night " +
      "cannot take the whole bankroll.",
  },
  kelly: {
    label: "quarter-Kelly",
    definition:
      "Kelly is a formula that sizes a bet by how big your edge is; " +
      "betting a quarter of what it says is deliberate caution — because " +
      "the edge estimate is usually the shaky part.",
  },
  fill: {
    label: "fill",
    definition:
      "An order actually matching — the moment your buy found a seller. " +
      "The fill price is what you truly paid, and it can differ from the " +
      "ask you were looking at.",
  },
  wl: {
    label: "W / L",
    definition:
      "Wins and losses, counted per settled bet. 7W / 32L means 7 settled " +
      "winners against 32 losers. A record this size is mostly luck either " +
      "way — which is what CLV exists to see past.",
  },
  net: {
    label: "net",
    definition:
      "What you are up or down after everything: payouts minus what the " +
      "bets cost minus fees. Here it covers only settled bets the recorder " +
      "has mirrored — open positions are not counted.",
  },
  volume: {
    label: "volume",
    definition:
      "How much money has traded in this market. Thin volume means few " +
      "people are trading it: prices move on tiny orders and getting out " +
      "of a position can be hard.",
  },
  favorite: {
    label: "favorite",
    definition:
      "The side the books' combined odds say is more likely to win — " +
      "chance above 50%. Being the favorite says nothing about the bet " +
      "being profitable: the price already charges for the chance.",
  },
  priced_in: {
    label: "priced in",
    definition:
      "Already reflected in the price. When news is priced in — a scratched " +
      "starter, tonight's wind — the line moved before you saw it, so " +
      "knowing it gains you nothing. Only news newer than the line can " +
      "matter.",
  },
  consensus_chance: {
    label: "chance to win",
    definition:
      "The books' combined, margin-removed estimate of how often this side " +
      "wins. 71% means: of 100 games like this, about 71. It is the best " +
      "estimate available — and the price usually charges exactly for it.",
  },
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
