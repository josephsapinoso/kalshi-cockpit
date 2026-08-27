# ADR 0074 — The desk watches what Joe holds, and a hedge alert says only what it measured

- **Status:** Accepted
- **Date:** 2026-08-26
- **Supersedes:** nothing. Extends ADR 0071 (what the desk is for), ADR 0070
  (the parlay desk), ADR 0072 (the channel), ADR 0063 (the separate hand path).

## Context

Joe's ask, verbatim: *"if I have a 6-leg parlay and one of them is not doing
well, I'd like to have an alert surface to me with high confidence that I should
hedge a bet right away… if there is any AI or ML that needs to be done, make it
independent of consuming tokens."*

His example is a baseball game: he holds Cincinnati to win, San Francisco lead by
two in the bottom of the sixth, and he wants to know when to bet the Giants
separately.

Four choices were put to him and answered in his own words (AskUserQuestion,
2026-08-26): **both** Kalshi combos and sportsbook slips; **LOCK pushes to the
phone and DE-RISK stays a screen row**; **Kalshi is the only hedge venue
priced**; and **build the vertical slice** rather than take a research spike
first.

## Decision 1 — this is a desk feature, not a reopening of the hunt

ADR 0038 closed the hunt: every quadrant this instance can reach has answered,
and no roadmap may depend on finding an edge. A hedge alert does not reopen it,
and the reason is that **a hedge makes no claim about mispricing at all.** It
takes the venue's price as given and reports what buying at it does to a position
that already exists.

ADR 0071 settled what the desk is for: *a personal betting desk first*, whose
job at the moment of a bet is **price transparency** — what Kalshi charges
against what the thing is worth. A ticket Joe already holds, going bad in the
sixth inning, is precisely that moment.

**And there is a hole this closes that nothing else can.** `parlays.NOTES`
carries the sentence the desk shows on every card: *"Kalshi combos are enter-only
in every order book this tool has ever read (40 of 40): you can buy in, but
nobody is bidding to buy you out. Plan to hold to settlement."* If Joe buys a
card off `/parlays`, **hedging a leg market is the only exit that exists.** The
desk currently sells a position and offers no way out of it.

## Decision 2 — the alert states the arithmetic and refuses the timing question

Two questions look like one and are not.

**What hedging locks in is certain.** With every other leg already won, one leg
live, a ticket returning `W` against a stake `S`, and `n` contracts of the
opposite side bought at the derived ask `q`:

    the leg wins    W - S - C(n)
    the leg loses   n x $1 - S - C(n)        C(n) = n*q + fee

They are equal at `n = W` and the guaranteed profit is `W - S - W*q - fee`.
There is no probability in that sentence. It is algebra on a price you can see.

**Whether the price will improve is not answerable here.** The hedge price is
the market's own number; `beta = -0.141` (ADR 0034) says the consensus signal
runs the wrong way, and ADR 0037 established that our own model's error exceeds
its disagreement with Kalshi. So the alert reports what is available and never
what is coming.

This is ADR 0072 Decision 1 applied one layer out: *alert text may contain only
nouns traceable to a field the check actually read.* A LOCK push names a dollar
figure, a contract count and a price. It does not say "hedge now".

**LOCK pushes; DE-RISK does not.** With more than one leg live, hedging one of
them locks *nothing* — it reshapes a distribution. That is worth showing on a
screen and is not worth a phone buzzing, because the phone would be buzzing for
a number the tool cannot stand behind. Joe chose this split.

## Decision 3 — the live Kalshi price replaces a win-probability model, and no MLB feed is read

Joe asked for no token spend. The answer is stronger than a budget: **nothing
here needs a model at all.**

A hedge needs how likely the leg still is and what the other side costs. The
Kalshi in-play ask is both. "San Francisco lead by two in the bottom of the
sixth" is exactly *why* the Cincinnati contract sits at 20c — the score, the
inning and the base state are already in the price, put there by people with
more information than this repo can lawfully obtain. Unlike a fitted win
probability it is also the number the hedge transacts at, so there is no
translation step to be wrong in.

Consequences, all of them in the cheap direction:

- **No Anthropic call on any path.** The runner already makes none
  (`review_retired` refuses every row, `backend/agents/review.py:387`).
- **No Odds API credit.** Kalshi reads are unmetered. Nothing here touches
  `ODDS_ATTENTION_DAILY_CREDITS`, and the attention ceiling is unchanged.
- **No MLBAM.** ADR 0035 §2 authorises exactly two schedule endpoints and says
  in terms that *"there is no case for 5-minute polling and it is forbidden
  here."* A per-game live feed is outside what that ADR decided, and reopening
  it would need its own. It is not needed.

**Kalshi already keeps the data.** ADR 0006's evidence: game markets stay open
through the game, and *"twenty of twenty games measured had a two-sided quote in
every minute after the true start."* `store_quotes_from_discovery` applies no
commence filter, so `kalshi_quotes` has been accumulating in-play prices for the
life of the project with nothing reading them.

## Decision 4 — this touches no evidence and no interlock

- **No `recommendations` row is written.** `runner`'s `dropped_game_started`
  drop stays exactly as ADR 0006 left it; no in-play row enters the evidence
  record, and no in-play consensus is bought.
- **`gate.py` reads neither new table**, for the same reason it never reads
  `manual_orders` (ADR 0063): a hedge is Joe's discretion and must not move the
  live-trading interlock's counters. Enforced by the table boundary — *a table
  is a boundary; a column is a convention* — and pinned by a test over
  `gate.py`'s source.
- **No ranking.** ADR 0071 §2.5 forbids ranking by the consensus-vs-Kalshi gap.
  Nothing here computes that gap at all; positions are listed in the order they
  were recorded.

## Decision 5 — rule 1 applies to the book, and deliberately not to the size of the lock

CLAUDE.md rule 1: a large apparent edge is a bug until proven otherwise. The
obvious reading — suppress a lock that is large relative to the stake — is
**wrong here, and the plan that proposed it was corrected before the code.**

A $4.99 ticket returning $333.33 with one leg left at an even-money hedge locks
about $172, which is 34x the stake and entirely real. That is simply what
hedging a longshot parlay looks like, and it is the exact case the feature
exists for. A lock-to-stake suppression would silence the feature at its most
useful.

The invariant that catches a genuine bug is one that cannot be true of any real
book: **both sides quoting for a dollar or less together.** That is free money,
which no book offers, so it is read as a crossed or stale book and refused. The
absence of a lock-to-stake rule is asserted by a test, so a future session that
adds one goes red and has to come back here.

Seven refusals, each returning a reason and never a number: `no_ask` (nothing
resting — and note the derived-ask trap, `1000 - 0 = 1000`, which this repo has
now fixed at three call sites and therefore tests at the boundary over the whole
0..1000 grid), `no_depth`, `stale_quote`, `market_closed`, `crossed_book`, and
`unreadable_ticket` (a misplaced decimal point in a typed payout), and
`fee_unreadable` -- unreachable through the front door, reached in tests by
monkeypatching the fee, and kept because the alternative to a refusal there
is a cost with no fee in it.

## Decision 6 — the figure is an upper bound, and the full hedge is usually unaffordable

Two honesty constraints ride on every number the screen shows.

**H4 is untested.** ADR 0027: whether Kalshi charges a settlement fee on top of
the entry fee is unresolved. Every figure here charges the entry fee only, so a
locked amount is an **upper bound**, and the screen says so rather than
implying an exactness it does not have.

**A $100 bankroll cannot hedge a $333 payout.** `n = W` contracts against the
deployed caps is out of reach for most real tickets. The module reports the
equalising rung anyway — "the full hedge is $150 and you have $100" is the
useful sentence, and hiding the rung leaves no way to say it — and computes
`is_guaranteed_profit` from the **reachable** rung, bounded by depth and by the
caller's cap. A lock you cannot buy is not a lock, and the alert fires on the
one you can.

## Decision 6b — an unread balance is not a balance of zero

Found during the build, and it changes what the alert can fire on.

The affordability cap comes from `latest_balance_tenths`, which answers `None`
whenever the newest five-minute poll could not read the venue's figure. Folding
that into a cap of **0** would make every hedge unaffordable and silence the
alert for exactly as long as the mirror was behind — this repo's own *unreadable
must never resolve to zero* rule, applied to a budget instead of a price, and it
would fail in the direction that looks like nothing is happening.

So an unread balance falls back to what the **book** allows, and
`bankroll_known: false` travels with it. The screen renders that as "your
balance could not be read", never as a number to act on. `affordable_contracts`
returns the count and that flag together, so a caller cannot take one without
the other.

The cost per contract in that division includes the fee **at one contract**,
which rounds up harder than the fee at `n` does. Conservative in the direction
that matters: the failure being bounded is being told you can afford a hedge you
cannot.

## Decision 7 — the ratchet, because a dedupe key is not a threshold

`notifications UNIQUE (kind, key)` never repeats a key. That is right for a
parlay card, whose identity is fixed, and wrong for a lock whose value moves
every minute of a game.

The key is `hedge_lock:{position_id}:{step}`, where `step` is the reachable
floor divided down to a registered increment. The first lock worth having
buzzes; a materially better one buzzes again; noise around a level does not.
Monotone, restart-safe, and no timestamp comparison — the properties ADR 0072
Decision 3 chose the card key for.

`MAX_HEDGE_PUSHES_PER_DAY` bounds the day regardless, because ADR 0072 Decision
4's lesson holds here too: **a dedupe key bounds repetition and never volume.**

## Decision 8 — the tool shows the hedge and does not place it

`MANUAL_ORDER_MAX_CONTRACTS = 1` with a 10-minute `COOLOFF_MS` and no override
(ADR 0073). A 30-contract hedge through the manual path would take five hours,
so **there is no hedge button.** The screen deep-links the Kalshi market and Joe
places it in the app.

Raising that cap is a money decision that belongs to him and wants its own ADR.
It deliberately does not ride along inside a feature about display, which is how
a per-bet limit gets relaxed by accident.

## Decision 9 — a fixture is derived from the ticker, because a held parlay CAN be same-game

Found by driving the real venue, and not by any test.

`/parlays` takes at most one leg per fixture, so `CorrelationRefused` is
structurally unreachable from card construction (ADR 0070 §2). **A ticket Joe
already holds has no such property** — he can hold whatever a book sold him,
including two legs of one game.

The first live drive picked Boston-to-win and Miami-to-win from the same MLB
fixture — **a pair that cannot both happen** — and the desk priced them as
independent and returned a joint probability. `assess` keys same-game detection
on `event_ticker`, the entry form takes a bare market ticker, and nothing filled
the gap: the two sides of one fixture have different *market* tickers, so they
looked unrelated.

Kalshi game tickers are `SERIES-EVENT-SIDE`, so the first two segments are the
fixture — the same structural read `lib/kalshiLink.ts` makes, verified in a
browser on 2026-08-22. It is applied only to a ticker with exactly three
segments; anything else derives nothing, because **a wrong fixture key merges
two real games and refuses a legitimate joint**, which is the worse error.

The fixture is filled in at record time *and* re-derived on read, and the second
one is not redundant: a row written by anything other than `record_position`
carries no fixture, and a mutation removing the read-side derivation stayed
GREEN until a test wrote a row the way something else would.

`core.correlation` then raises on the pair and the joint is withheld with its
own words. The per-leg prices still render. ADR 0012 §5 is why nothing is
invented: this repo has no measured same-game correlation, and a mutually
exclusive pair is where inventing one is most wrong.

## Measured by running it, against the venue's own book

The suite did not find the defect above. Driving the stack did, which is the
pattern `tasks/lessons.md` keeps recording.

Two legs on `KXMLBGAME-26AUG261840BOSMIA`, a $5.00 ticket returning $100.00,
hedged at the **derived** NO ask of 80c:

    100 contracts    cost $81.12 (fee $1.12)
    leg wins         $13.88
    leg loses        $13.88
    ratchet key      hedge_lock:1:2

**Both branches equal to the cent**, which is the identity the whole feature
rests on, arrived at from a real book rather than a fixture. With both legs live
the same ticket reported `chance_display: "--"`, `notional_value_display: "--"`
and the correlation refusal verbatim — no invented number anywhere.

## What the build changed about this ADR

Two decisions above were **written before the code and corrected by it**, and
both are recorded rather than quietly amended:

1. **The plan proposed suppressing a lock that was large relative to the
   stake.** Decision 5 is the correction. The suppression would have silenced
   the feature at its most useful, and the invariant that catches a real bug is
   the crossed book instead.
2. **The plan passed an affordability cap as a contract count.** The caller
   cannot compute one without the ask, and the ask is chosen inside. Decision 6b
   is the correction, and it surfaced the unread-balance question that a count
   would have hidden.

**Forty-five mutations were observed red** across `core/hedge.py` (15),
`hedge.py` (16) and the alert path (14). **Six stayed GREEN on the first
pass, and the split is itself the finding:** three were real holes, one was a
vacuous test, and **two were the harness patching the wrong function** --
`parlay_cards` and `hedge_locks` share the lines `if key is None:` /
`continue`, and `replace(old, new, 1)` takes the first. A GREEN mutation is a
claim about the harness before it is a claim about the test.

The three real holes, each closed by a test rather than by weakening an
assertion:

- the return-above-stake guard was unobservable through its reason code alone,
  because the odds floor catches the same input. The test now asserts the
  **sentence**, which is what that comparison uniquely produces.
- nothing distinguished `floor(W)` from `ceil(W)` as the equalising size, so
  dropping half the search passed.
- nothing exercised a de-risk whose live legs had no readable price, so the
  branch that explains a missing joint could be deleted in silence.

And the vacuous one: the watcher's failure guard was tested against an empty
database, so `anything_in_progress` was False, the cycle body never ran, and
the `try/except` under test was never entered.

## Consequences

- Schema v23: `parlay_positions` and `parlay_position_legs`. Both are pure new
  tables, so `CREATE TABLE IF NOT EXISTS` covers an existing volume as well as a
  fresh one — the same property ADR 0072 verified for `loop_failures` — with a
  `_MIGRATIONS` entry for the version bump.
- One more `notifications.kind`. No migration; `kind` is free text.
- A new watcher task in `scripts/run_loop.py` beside `poll_portfolio_forever`,
  **not** work added to the quote pass. ADR 0072 Decision 5 is the precedent:
  "pure" is a claim about effects, not about cost, and the 8s
  `QUOTE_PASS_DURATION_BUDGET_S` already runs ~4.2s live.
- No new nav slot. The six-link budget is load-bearing at 390px (ADR 0073); the
  screen is reached from `/bets` and from the alert's own link.

## What this does not establish

- **That hedging is profitable.** It is a variance decision. A guaranteed $172
  is guaranteed; nothing here says taking it beats holding the ticket.
- **That now is the best moment.** No measurement in this repo supports a timing
  claim, and none is made.
- **That the guarantee is exact.** H4 again.
- **That a leg Joe marks as won actually won.** A sportsbook leg has no Kalshi
  ticker and cannot be resolved from the venue, so `resolved_source = 'manual'`
  is his word and is recorded as his word.
