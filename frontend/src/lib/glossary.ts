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
  rfq: {
    label: "request for quote",
    definition:
      "How a combination is priced on Kalshi: you ask, and market makers " +
      "send back private prices. That is why a combo's " +
      "order book usually looks empty — nobody rests a price there, they " +
      "answer when asked. Asking costs nothing.",
  },
  maker: {
    label: "market maker",
    definition:
      "A firm that quotes you a price when you ask. Their prices can " +
      "differ — on the first combination " +
      "this desk priced, three makers came back 3.8c apart on the same " +
      "contract, so the best one is worth reading.",
  },
  maker_quote: {
    label: "quote",
    definition:
      "One maker's price for the whole size you asked for. It is " +
      "all-or-nothing: you take it at that size or not at all. Quotes " +
      "vanish when the request is deleted; how long one otherwise lives " +
      "is unmeasured, so an old quote on screen is a price that was " +
      "offered, not one known to be standing.",
  },
  implied_chance: {
    label: "this price says",
    definition:
      "The price read as a chance. A 5c ticket is the market saying " +
      "it wins about 5 times in 100. Paying more than that only " +
      "makes sense if you believe it is likelier than the market " +
      "does.",
  },
  one_in: {
    label: "wins about 1 in",
    definition:
      "How many tickets like this it takes to expect one win. At 1 " +
      "in 20, losing 40 in a row happens about one time in eight — " +
      "a normal run, not bad luck.",
  },
  books_joint: {
    label: "the books multiply to",
    definition:
      "The sportsbooks' consensus chance that every leg wins, as a " +
      "price. Paying above it means paying the makers a markup on " +
      "top of the books' own number. It is a price to compare " +
      "against, not a prediction.",
  },
  quote_spread: {
    label: "quote spread",
    definition:
      "How far apart the makers' quotes are, best to worst. A wide " +
      "gap means asking again a few minutes later can get a better " +
      "price. Asking commits you to nothing.",
  },
  shard: {
    label: "shard",
    definition:
      "Kalshi keeps the money for combinations in a separate pot from the " +
      "money for single bets. Cash in one does not pay for the other, so " +
      "a combination can be unaffordable while your account total looks " +
      "fine.",
  },
  parlay: {
    label: "parlay",
    definition:
      "One ticket that only pays if every pick on it wins. Kalshi calls " +
      "these combos. Chances multiply down fast: six picks that each win " +
      "65% of the time land together about 8% of the time — which is why " +
      "the payout is large.",
  },
  leg: {
    label: "leg",
    definition:
      "One pick inside a parlay. A 6-leg ticket has six picks, and " +
      "every single one must win for the ticket to pay. Lose one " +
      "leg, lose the whole stake. Each extra leg multiplies the " +
      "odds against you.",
  },
  days_rest: {
    label: "days of rest",
    definition:
      "Full days a team sat out between its last game and this one. " +
      "Played Monday night, plays Wednesday night: 1 day of rest. " +
      "0 means it played the day before. Tired legs are one reason a " +
      "team can play worse; it is a fact, not a prediction.",
  },
  back_to_back: {
    label: "back-to-back",
    definition:
      "A team playing two games on consecutive days, like Friday night " +
      "then Saturday night. Common in basketball and hockey. It shows " +
      "which teams are on short rest, and says nothing about who wins.",
  },
  short_week: {
    label: "short week",
    definition:
      "Football teams normally play once a week. A short week means " +
      "fewer than six days since the last game, like a Thursday game " +
      "after a Sunday one. Less time to recover and prepare.",
  },
  joint_chance: {
    label: "joint chance",
    definition:
      "The chance that ALL the legs win together. Roughly the legs " +
      "multiplied: 70% × 60% ≈ 42%. Games on the same night nudge each " +
      "other slightly, so the number here is computed with that link " +
      "included, not by bare multiplication.",
  },
  chance_when_priced: {
    label: "desk's chance when priced",
    definition:
      "What the desk's sportsbook consensus said this pick or parlay would win, " +
      "at the moment you priced it — not the true chance, and not a " +
      "grade of the bet. Same computation as \"joint chance\": the legs " +
      "multiplied, with a small nudge for same-night games.",
  },
  hedge: {
    label: "hedge",
    definition:
      "Betting the other side of something you already have money on, to " +
      "cut what you can lose. You hold Cincinnati; Cincinnati are losing; " +
      "you buy San Francisco separately so one of the two pays.",
  },
  lock: {
    label: "lock",
    definition:
      "A hedge big enough that you end up with about the same amount " +
      "either way the last leg goes, possible only once every other leg " +
      "has won. The figure shown is an estimate: its fees and stake are " +
      "not exactly what Kalshi charged, and the differences run both ways.",
  },
  derisk: {
    label: "de-risk",
    definition:
      "Hedging while more than one leg is still live. It cuts the swing " +
      "but guarantees nothing: the ticket can still lose on a leg you did " +
      "not hedge.",
  },
  hold: {
    label: "hold",
    definition:
      "The seller’s margin baked into a price: how far the cost sits above " +
      "fair value. A 40% chance sold at 50¢ is a 20% hold — pay $1.00 for " +
      "80¢ of chance. Parlays usually carry the biggest hold of any bet.",
  },
  alt_line: {
    label: "other line",
    definition:
      "A sportsbook posts one main spread and one main total for a game, " +
      "plus a ladder of other numbers at different prices. If the main " +
      "spread is BYU −5.5, “BYU wins by over 6.5” is one of the other " +
      "lines. Fewer books post each one, so a chance read from them rests " +
      "on fewer opinions.",
  },
  fair_value: {
    label: "fair value",
    definition:
      "What a bet is worth if the price exactly matched its chance: a 40% " +
      "chance is worth 40¢ on a $1 payout. Any price above fair value is " +
      "the seller’s margin. The cards here show fair value; Kalshi’s own " +
      "price will differ.",
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
      "How often a bet at this price must win to break even, fee counted. " +
      "At 50c the desk assumes you need about 51.75%, not 50%; measured on " +
      "baseball it is about 50.9%. Whether Kalshi also charges a fee when a " +
      "bet pays out is unchecked. Don't think it wins more often? Pass.",
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
      "The money put on one bet. Keep it a small fixed fraction of " +
      "your bankroll, the same on every ticket. Changing the stake " +
      "because of the last result, or because a ticket is cheap, is " +
      "how bankrolls die.",
  },
  unit: {
    label: "unit",
    definition:
      "A fixed small share of your bankroll, put on every bet " +
      "regardless of its price or your last result. Professionals " +
      "size in units so one long shot cannot empty a week. The " +
      "share is yours to choose.",
  },
  clv: {
    label: "CLV",
    definition:
      "Closing-line value: your price against the final price just " +
      "before the game started. −0.5c means you paid half a cent " +
      "more than the close. Tonight's result is mostly luck; " +
      "beating the close again and again is the real sign a bettor " +
      "knows something.",
  },
  // `sd` (swing) was removed 2026-09-16 with the two figures that were the
  // only things rendering it. Issue #48, answered A: the swing and the
  // run-length sentence beside it were both computed from the
  // consensus-vs-Kalshi gap, which this repo has measured twice and both
  // times below the no-signal threshold, so the pair of them offered
  // variance as the only way to lose. Deleted rather than parked: the
  // orphan rule below is use-it-or-delete-it.
  // `tests/test_no_priced_surface_claims_the_edge_is_real.py` keeps it gone.
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
  books: {
    label: "the books",
    definition:
      "The sportsbooks — the betting companies that set their own odds. " +
      "Here, what they together say each leg is worth, with their margins " +
      "removed. Multiplied across the legs, that is what the books say the " +
      "whole parlay is worth: 70% × 60% ≈ 42%.",
  },
  sharp_book: {
    label: "sharp book",
    definition:
      "A sportsbook that takes big bets from professionals and moves its " +
      "price first — Pinnacle and Matchbook here. Their prices are the " +
      "reference. When none of them quoted the exact line you are looking " +
      "at, the fair value falls back to the recreational books, which is a " +
      "wider and weaker consensus wearing the same name.",
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
      "The money set aside for betting — here, the cash actually in " +
      "your Kalshi account. Size every bet as a small fixed share " +
      "of it, so one losing run cannot end the week.",
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
      "included. Hold two $20 bets and you are $40 exposed. Nothing caps " +
      "it on a bet you place by hand — that is why the ticket shows it.",
  },
  "exchange-shard": {
    label: "exchange shard",
    definition:
      "Kalshi does not keep your money in one pot. It splits it across " +
      "numbered wallets it calls exchange indexes, and every market settles " +
      "on exactly one of them. The venue will not move money between " +
      "wallets to pay for an order, so a $1 deposit sitting in the wrong " +
      "wallet cannot buy a 25¢ contract in another — the account total says " +
      "you can afford it and the order is still refused. Kalshi's own app " +
      "shifts the money for you as you bet there; it does not do that for " +
      "orders sent by a tool like this one. You move it yourself on Kalshi's " +
      "account page, and the control to do so appears only while balance " +
      "management is switched off there — while Kalshi manages the balance " +
      "for you the page shows the wallets and no way to move between them.",
  },
  kelly: {
    label: "quarter-Kelly",
    definition:
      "Kelly is a formula that sizes a bet by how big your edge is; " +
      "betting a quarter of what it says is deliberate caution — because " +
      "the edge estimate is usually the shaky part.",
  },
  expected_wins: {
    label: "expected to win",
    definition:
      "A price is a chance: a combo bought at 25 cents is priced as a 1-in-4 " +
      "shot. Add those chances up across your bets and you get how many " +
      "should have won if the prices were fair. 40 bets at 25 cents: about 10.",
  },
  plausible_range: {
    label: "range",
    definition:
      "Wins bounce, like heads in 40 coin flips. The range is where " +
      "the win count lands 19 times in 20 at fair prices: 10 expected reads " +
      "4 to 16. The range treats each bet as separate. Bets that share " +
      "a leg or a game win or lose together, so the real range is wider.",
  },
  too_few: {
    label: "too few to judge",
    definition:
      "Not enough expected wins or losses in this cell to tell luck " +
      "from a pattern — under five on either side. The counts are " +
      "shown; a rate would mislead. Read it again when the cell has " +
      "grown.",
  },
  stake_weighted: {
    label: "where the money went",
    definition:
      "Winning as often as the prices expected can still lose " +
      "money, if the biggest stakes sat on the longest shots. " +
      "Staked and net beside each row show where the money actually " +
      "went.",
  },
  longshot: {
    label: "long shot",
    definition:
      "A low-priced ticket — here, under 10c. Across betting " +
      "markets long shots return less per dollar than favourites, " +
      "and the fee is a bigger share of a small price. Fun to hold, " +
      "costly to hold often.",
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
  moneyline: {
    label: "moneyline",
    definition:
      "Just picking who wins the game — no handicap and no score line, " +
      "unlike a spread or a total. On Kalshi it is the “will this team " +
      "win” market, and the price alone carries how likely that is.",
  },
  spread: {
    label: "spread",
    definition:
      "A handicap that turns an uneven game into a near coin flip. " +
      "“Rams −3.5” means the Rams must win by 4 or more for " +
      "that side to hit — win by 3 and it misses even though the Rams won " +
      "the game.",
  },
  total: {
    label: "total",
    definition:
      "The combined score of both teams. An over/under bet is whether it " +
      "lands above or below a line the book sets — “over 47.5” hits at 48 " +
      "or more. The line is placed so either side is close to a coin flip, " +
      "which is why totals rarely carry a big favorite.",
  },
  player_prop: {
    label: "player prop",
    definition:
      "A bet on one player's number rather than the game's result — " +
      "rushing yards, strikeouts, total bases. “Henry over 74.5 rushing " +
      "yards” hits at 75 or more, whoever wins. On Kalshi each rung is its " +
      "own market: 75+ yards is one, 100+ is another.",
  },
  line: {
    label: "line",
    definition:
      "The number a total or prop is measured against — the 47.5 in “over " +
      "47.5”. The half-point means it cannot land exactly on the line, so " +
      "the bet cannot tie. On a Kalshi rung the line is the strike in its " +
      "title.",
  },
  key_number: {
    label: "key number",
    definition:
      "A margin football games land on far more often than its neighbours " +
      "— 3 and 7 most, then 6, 10, 14 — so a half point across one is " +
      "worth more than elsewhere. “On 3” is a line of exactly 3; " +
      "“crosses 3” is 2.5 or 3.5.",
  },
  consensus_chance: {
    label: "chance to win",
    definition:
      "The books' combined, margin-removed estimate of how often this side " +
      "wins. 71% means: of 100 games like this, about 71. It is the desk's best " +
      "estimate — and the price usually charges exactly for it.",
  },
  scout_desk: {
    label: "scout desk",
    definition:
      "An AI crew that reads news on one game — injuries, lineups, weather " +
      "— when you send it. It costs real money per game, so most games are " +
      "never sent. “Dark” means nobody has sent it, not that nothing was " +
      "found — it never moves a price.",
  },
  advisory: {
    label: "advisory",
    definition:
      "An opinion to weigh, not an instruction. The scouts' take-or-pass " +
      "read is advisory: it never disables a button, never stops a bet, " +
      "and you can buy right through a PASS if you still want to.",
  },
  same_game_parlay: {
    label: "same-game parlay",
    definition:
      "A parlay whose legs all come from one game: the winner, a margin " +
      "and a player's yards, say. The legs move together (a blowout " +
      "changes several at once), so their chances cannot just be " +
      "multiplied. The makers' quote prices that link in.",
  },
  correlation: {
    label: "correlation",
    definition:
      "Legs that tend to win or lose together — a team covering and " +
      "the game going over, say. The makers who quote your " +
      "combination charge for that link. The desk does not compute " +
      "it.",
  },
  betting_splits: {
    label: "splits & line movement",
    definition:
      "What share of the money is on each side versus the tickets — the " +
      "two can differ when a few big bettors outweigh many small ones — " +
      "and how far the line has moved. Usually already priced in by the " +
      "time you see it.",
  },
  game_script_card: {
    label: "game-script card",
    definition:
      "A short story for each game and the same-game picks that fit it. " +
      "For example, \"a slow, low-scoring game\", with the news that " +
      "would kill it. The desk writes it from who is playing, rest and " +
      "matchups. It is an opinion with sources, not a price.",
  },
  drop_if: {
    label: "drop it if",
    definition:
      "The specific news that should make you skip the card: a starter " +
      "ruled out, say. The card's story rests on that fact holding, so " +
      "when it stops holding, the card stops making sense.",
  },
  inactives: {
    label: "inactives",
    definition:
      "The list of players a team declares out for the game, released " +
      "about 90 minutes before kickoff. A card is built a day earlier, " +
      "so it cannot know them. Check the list before you bet.",
  },
  single: {
    label: "single",
    definition:
      "One bet on one pick, paid on its own. Three singles are three " +
      "separate bets that win or lose independently; a parlay of the same " +
      "three is one bet that pays only if all three win.",
  },
  fee_share: {
    label: "fee share",
    definition:
      "The fee as a slice of what you stake. A 5c card pays about 6.7% " +
      "of its stake in fee; a 50c card about 3.5%. The same fee formula " +
      "takes a bigger bite of a small price.",
  },
  sunk_cost: {
    label: "sunk cost",
    definition:
      "Money already spent that selling or holding cannot bring back. " +
      "What you paid for a card is sunk: the only question left is " +
      "whether a bid now is worth more to you than waiting for the " +
      "result.",
  },
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
