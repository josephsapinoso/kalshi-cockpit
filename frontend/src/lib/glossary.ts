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
  realised_loss: {
    label: "realised loss",
    definition:
      "Money actually gone on bets that have finished — wins minus what " +
      "they cost, fees included. A bet still open doesn’t count yet. If " +
      "you staked $5, got $4 back, and paid 20¢ in fees, your realised " +
      "loss is $1.20.",
  },
  basis_points: {
    label: "basis points",
    definition:
      "Hundredths of a percent, so the record can hold 62.50% as the whole " +
      "number 6250. You type the percent; the fine print just shows how it " +
      "is stored.",
  },
  ask: {
    label: "ask",
    definition:
      "The price you would actually pay to buy right now — the sticker " +
      "price. There is also a “mid” (an average of buy and sell), " +
      "but nobody gets to pay the mid, so every judgement here uses the ask.",
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
    definition:
      "The money put on one bet. Yours is $2, every time, win or lose. " +
      "Changing the stake because of the last result is how bankrolls die.",
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
  drift: {
    label: "drift",
    definition:
      "How the Kalshi price has moved recently, and which way. If it " +
      "already moved toward your side, part of your idea is spent — you " +
      "would be paying for news the price has absorbed.",
  },
  candlestick: {
    label: "candlestick",
    definition:
      "One bar per time slice showing four prices: where it opened, the " +
      "highest and lowest it traded, and where it closed. A filled-in hour " +
      "of trading at a glance; the line view shows only the closes.",
  },
  volume: {
    label: "volume",
    definition:
      "How much money has traded in this market. Thin volume means few " +
      "people are trading it: prices move on tiny orders and getting out " +
      "of a position can be hard.",
  },
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
