# 0006 — In-play betting is out of scope

**Status: REJECTED** by Joe, 2026-08-08. Proposed the same day.

Evidence and full measurements: `docs/adr/0006-in-play-evidence.md`.

## What the rejection does and does not mean

**The measurements are not rejected.** Nothing below was disputed. What was
declined is the *decision* — closing in-play as a product direction on the
strength of one day's numbers. The question stays open.

**The guards stay on.** This matters more than the rest of this file, because
"reject the ADR" is one careless reading away from the opposite:

- `runner`'s `dropped_game_started` **stays a drop.**
- The order path's refusal of a started game **stays.**
- **No in-play row may enter the evidence record.**

None of those three was introduced by this ADR. They predate it, they were added
for a reason this ADR did not invent — a stored pre-game consensus differenced
against a price that has absorbed two innings is two different questions
subtracted from each other — and rejecting a proposal to make them permanent
policy does not remove them. Reopening the scope means *designing* the in-play
regime, starting with the closing-line substitute; it does not mean letting rows
in first and telling the two populations apart afterwards. That is the failure
`tasks/lessons.md` names as "two populations in one record, told apart by
dispersion".

**What would have to be true to accept this later**, or to refute it: see
"What would reopen this" at the end. The costs measured here are the bar, and
the honest summary is that Joe's instinct about the *product* was right — the
liquidity is real and it is where the volume is. The obstacle measured was our
ability to see it in time, on a free odds tier, which is a fact about our data
budget rather than about the market.

## Context

Joseph asked whether this tool should bet games in progress: *"in Kalshi you can
still bet on games during the half and quarters."* The runner currently drops
every started game (`dropped_game_started`, 36 of 104 rows on one live pass).
That drop was made because a stored pre-game consensus differenced against a
Kalshi price that has absorbed two innings is two questions subtracted from each
other — a defect in *this* tool, and not a verdict on the market.

Four questions had to be answered before anything could be built. All four were
answered on 2026-08-08 with read-only `GET`s against the live exchange and web
research. The Odds API was not called; its budget is shared with the live
instance.

### 1. Kalshi keeps the game market open, *and* lists period markets

Confirmed on both. Game markets carry `can_close_early: true` and
`early_close_condition: "This market will close and expire after a winner is
declared"`; four MLB markets closed 2h29m–3h04m after first pitch, not at it.
**Twenty of twenty games measured had a two-sided quote in every minute after
the true start.** Separate period series exist alongside them and settle
mid-game — `KXWNBA1HWINNER`, `KXWNBA2HWINNER`, `KXMLBF5`, `KXMLBRFI` and the
soccer `*1H*` families. `tests/fixtures/sports_coverage.json`, already in the
repo, lists 225 sports series of which **46 are period or partial-game markets**.

**In-play is also where the volume is**: contracts per minute rise 7.7× (MLB)
and 14.7× (WNBA) once the game starts, and 98% of in-play minutes trade against
92–94% pre-game. The product is real, liquid, and larger than the pre-game
market this tool watches. The reason to decline is not that there is nothing
there.

### 2. The odds side cannot follow at this bankroll

The Odds API charges `markets × regions` per call per sport, and refreshes
in-play featured markets every **40 seconds** — a floor no subscription tier
buys under. One league, thirteen hours of live coverage, at the current
`h2h,spreads,totals × us,eu` configuration:

    13h × 90 calls/h × 6 credits = 7,020 credits/day = 210,600/month

That is **439× `ODDS_DAILY_CREDIT_BUDGET=16`**, and at 540 credits an hour it
consumes the free tier's entire 500-credit month in 56 minutes. Priced against the published
tiers, a real slate needs the **5M plan at $119/month**; $59/month buys one
league with no spreads and no totals.

Against `BANKROLL_DOLLARS=1000` and a 0.38-percentage-point headroom, $119/month
requires **$31,316 of monthly notional** — 313 max-size positions, ~10 a day —
to break even *on the data bill alone*, and only if the full theoretical
headroom is captured with zero slippage. Question 4 measures the slippage.

### 3. Nothing replaces the closing line without becoming a different statistic

CLV anchors on one instant per game. In-play has none, and every candidate
substitute changes what is being measured:

- **Settlement price** is win-rate measurement. `clv.py` exists specifically to
  avoid needing ~1,000 observations; this puts the variance back and makes
  `LIVE_GATE_MIN_SCORED_RECOMMENDATIONS=300` a threshold for the wrong quantity.
- **End-of-period price** is undefined for the game market, and for a bet late
  in a period it collapses into settlement.
- **Price at entry + Δ** is the closest in form, and is precisely the statistic
  that stale-quote picking optimises — recorded in `tasks/lessons.md` as
  measured and refuted at ~400ms.

The machinery is hard-wired to kickoff in four places: `closing_lines` is
`UNIQUE (ticker, horizon_hours)` and updates on conflict, so thirty in-play rows
on one ticker silently collapse to one; `scoring.markets_awaiting_scoring` and
`fetch_closing_line` both key off `true_commence`; `score_recommendations`
refuses rows created after the observed line, which is every in-play row;
`horizons_agree` interprets movement between horizons as convergence, which is
what a live market does by definition.

And `gate.clustered_clv` pools by suppression and size, **not by regime**, so
in-play and pre-game rows would share the `actionable` bucket carrying two
different statistics — `tasks/lessons.md`, "two populations in one record, told
apart by dispersion", with the guard that caught it last time removed.

### 4. The edge is not plausibly there — by a factor of 3.5 to 6

Fourteen MLB and six WNBA games, 1-minute candlesticks, 2026-08-07/08. The check
was designed to be cheap and to produce a reportable number in either direction:
compare the **cost of participating** against the **headroom**, using only free
Kalshi data — no bets, no orders, no odds credits.

| | pre-game | in-play |
|---|---|---|
| half-spread, mean (MLB / WNBA) | 0.50c / 0.50c | 0.75c / 0.89c |
| \|Δmid\| per minute, mean (MLB / WNBA) | 0.00c / 0.01c | 1.63c / 2.31c |
| minutes moving ≥1c (MLB / WNBA) | 0.2% / 0.9% | 48.5% / 50.1% |

**Extra crossing cost** is 0.25c (MLB) and 0.39c (WNBA) — 66% and 103% of the
headroom, spent before any view is expressed. **Drift over the odds side's
40-second floor** interpolates to 1.09–1.33c (MLB) and 1.54–1.89c (WNBA).

    total cost 1.34c – 2.28c   against   0.38c of headroom

Both leagues agree in direction and magnitude. Stated plainly: `MAX_ODDS_AGE_S`
tolerates fifteen minutes pre-game because the mid moves ≥1c on 0.2% of pre-game
minutes; in-play it moves ≥1c on half of them. **Fifteen minutes of pre-game
staleness costs less than forty seconds of in-play staleness.**

This is the same shape as the stale-quote result already in `tasks/lessons.md`.
There the edge lived at ~400ms and a 60–180s detector could not reach it. Here
it lives inside 40s and the data supplier cannot deliver faster. The money is on
the other side of a latency gap this project does not own.

## Decision

**In-play betting is out of scope.** Two independent reasons, either sufficient:

1. **Cost.** The measured cost of participating in-play (wider crossing plus
   unavoidable data staleness) is 3.5× to 6× the fee headroom the tool exists to
   capture. This is arithmetic, not a forecast.
2. **Budget.** Following the market at all requires The Odds API's $119/month
   tier, which needs $31,316 of monthly notional against a $1,000 bankroll
   before it breaks even.

Consequently:

- `runner`'s `dropped_game_started` **stays**, and it stays as a drop rather
  than a suppression. A suppression entry says "we considered this and rejected
  it"; we should not be considering it.
- The order path's refusal of a started game **stays**.
- **No in-play row may enter the evidence record.** Not behind a flag, not
  labelled, not suppressed — dropped, and counted.
- No period-market series (`KX*1H*`, `KXMLBF5`, …) is added to discovery.
- **Maker is not refuted, it is unreachable.** At the 50.44% maker break-even
  the headroom is 1.94 points, which exceeds the measured MLB cost. But a
  resting order in a market that moves ≥1c half of all minutes is being
  adversely selected, and this repo has no cancel path at all — plain GTC limit,
  no `time_in_force`. That door is closed by missing infrastructure, and should
  be recorded as such rather than as a measurement.

### What would reopen this

All three, not any one:

1. A data source that delivers a devigged in-play consensus with an age well
   under 40 seconds, priced against the bankroll.
2. A substitute for the closing line that is chosen and argued *before* any row
   is recorded — plus a regime column on `recommendations`, `closing_lines`
   keyed per recommendation rather than per `(ticker, horizon)`, and a gate that
   reports the two regimes separately and never pools them.
3. A cancel path, if the reopening is on the maker side.

## Consequences

The tool stays pre-game, and the ~0.38 points it hunts stay the only thing it
hunts. It declines the most liquid corner of the venue, deliberately and with
the number written down.

The cost of being wrong is bounded and visible: if a cheaper low-latency
consensus appears, the reopening test is item 1 above and it is a day's work,
because the Kalshi side of the measurement is already done and recorded here.

The cost of having been right is the more important one. The four in-play
questions were asked because 36 of 104 recorded rows on one live pass were
games in progress, and 22 of those 36 passed every suppression rule and entered
the evidence record looking like ordinary no-edge observations. Deciding this
question closes the only remaining reason anyone would be tempted to remove that
drop "just to see".

**What this ADR does not establish.** It does not establish that no in-play edge
exists — only that this tool's data supply chain cannot reach one. The
measurement is twenty games across two leagues on a single night, and it
measures drift in Kalshi's own mid rather than in a sportsbook consensus. That
substitution is conservative in direction (books suspend markets in-play and are
likely slower than Kalshi, which would make the error larger) but it was not
tested, because The Odds API was deliberately not called.
