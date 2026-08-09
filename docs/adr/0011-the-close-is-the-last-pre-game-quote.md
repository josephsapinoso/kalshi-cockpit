# 0011 — The close is the last pre-game quote

**Status:** accepted, 2026-08-09

Fixes the top item in `tasks/NEXT.md`: the gate's 300-game counter cannot reach
one, and the reason is arithmetic rather than a shortage of data.

## Context

CLV is the only evidence this project trusts. The gate that arms real money has
two conditions and both read it. `analysis/clv.py` opens by saying why: telling a
52% win rate from 50% takes about a thousand bets, whether you beat the price
takes 200–300, and that is the difference between a measurable question and an
unmeasurable one.

On 2026-08-09 the live instance reported, on consecutive passes:

    rows_joined: 228   scored: 0   skipped_entry_after_close: 228
    rows_joined: 249   scored: 0   skipped_entry_after_close: 249

Not a shortage of markets, and not a transient. Four independently reasonable
numbers compose into a rule that no row can satisfy:

| Quantity | Where | Instant |
|---|---|---|
| Sweep fires no later than | `timing.py`, `fire_until = anchor - max_odds_age_ms` | kickoff − 15 min |
| Sweep fires no earlier than | `fire_from = fire_until - due_window_ms` | kickoff − 45 min |
| Closing line targeted at | `scoring.py`, `commence - horizon_hours` | kickoff − 60 min |
| ...and the candle window looks **back** | `WINDOW_MINUTES = 15` | up to kickoff − 75 min |
| Scoring requires | `clv.py`, `r.created_ms <= c.observed_ms` | entry before the close |

A recommendation cannot exist before the odds sweep that priced it, so the
earliest any row exists is **kickoff − 45 min**. The line it is scored against is
observed at **kickoff − 60 to − 75 min**. `created_ms <= observed_ms` is false
for every row the scheduled path produces, on every slate, forever.

**Each of the four is defensible alone.** The 15-minute sweep lead is one whole
`max_odds_age_ms`, chosen so a pick surfaced at the very end of the window is
still a pre-game bet. The 30-minute due window is wider than the loop interval,
so a slot cannot be stepped over. The entry-before-close rule stops a row being
scored against a price that did not exist when the decision was taken. Only the
horizon is undefended: `DEFAULT_HORIZON_HOURS = 1.0` has no stated reasoning
anywhere in the repo.

**Three things make this worse than an ordinary bug.**

*The module documents the collision and draws the wrong conclusion from it.*
`clv.py` says, in the section introducing the rule: *"The runner records right up
to kickoff and the 1h line is read an hour before it, so without this rule every
late recommendation would be scored against a price that did not exist."* That is
exactly right, and it treats "late" as a subset. After `odds/timing.py` landed,
every recommendation is late. The cost was even stated — *"the scored sample
skews early"* — where the true cost is that the scored sample is empty.

*It was introduced by a correct fix.* An earlier run scored 34 rows. Before
`odds/timing.py`, sweeps fired at whatever moment the budget first allowed after
the day rolled, so some rows happened to land more than an hour before kickoff
and scored by accident. Scheduling the sweeps — the change that made the tool
actionable at all, ADR-adjacent work nobody would undo — removed the accident.
**The tool became usable and its evidence layer stopped recording, in the same
commit.**

*Every counter reads healthy.* `rows_joined` is 249, not zero.
`skipped_entry_after_close` was added deliberately so this case would be
visible, and it was visible, on every pass, for two days. Nobody multiplied it
out. This is `two-limits-on-one-quantity` on the one number the entire go-live
decision rests on.

## The thing the horizon was getting wrong, beyond scoreability

A longer horizon does not merely exclude rows. **It flatters.**

A market gets sharper as the event approaches. Beating the price six hours out
is easy and says almost nothing; beating the last pre-game price is the claim
worth making, and is what "closing line value" means everywhere the term is
used. So the current setting had the direction of caution inverted: it scored
against a *less* informed benchmark, and had it ever produced numbers they would
have been optimistic.

That settles which way to move. Per the reasoning in ADR 0005, a change to a
money guard should make it harder to pass, and shortening the horizon does.

## Decision

### 1. The primary horizon is 0 — the last quote at or before kickoff

`DEFAULT_HORIZON_HOURS = 0.0`. The candle window already ends at the target and
reaches 15 minutes back, so this reads *the most recent quote in the final
quarter-hour before the game*, which is the closing line in the ordinary sense
of the phrase.

Why zero rather than a small positive number. With target `kickoff − h`, the
observation lands in `[kickoff − h − 15min, kickoff − h]`, so a row at time `c`
scores only when `c <= kickoff − h − 15min` in the worst case. Entries occupy
`[kickoff − 45min, kickoff]`. So `h` must be **under 30 minutes** for even the
earliest row to score reliably, and every minute added to `h` discards the rows
created in that minute. `h = 0` maximises the scoreable fraction *and* is the
truest close. There is no trade-off between the two here, which is unusual
enough to be worth saying out loud.

**It stays pre-game.** `observed_ms <= kickoff` by construction. The anchor is
the **sportsbook's** `commence_ms`, never Kalshi's `occurrence_datetime`, which
runs exactly three hours late — using the wrong clock here would read a quote
two hours into the game and produce a strong, entirely fake CLV signal. The
residual risk is a game starting *earlier* than scheduled, which does not
happen in scheduled US sports; delays push the start later, which makes the
reading more pre-game, not less.

**Rows created in the final fifteen minutes still go unscored**, and that cost is
real and stated rather than buried. It is a much smaller exclusion than the
current total one, and it is the honest residue of a rule that should not be
relaxed: a row must not be scored against a price older than the decision.

### 2. The control horizon becomes 1.0h

Was 6.0h. The pair exists so `horizons_agree` can catch convergence — if a
finding evaporates when the anchor moves, it was drift. A one-hour separation is
enough to detect that, and it has two properties six hours does not: markets
this project prices reliably have quotes an hour out, and **1.0h is the horizon
the existing scored rows already used**, so the record already contains control
data rather than needing a season to accumulate it.

### 3. Recommendations record the horizon they were scored at — schema v5

`recommendations` gains `clv_horizon_hours`. Today `clv_tenths` is a bare number
with nothing saying which anchor produced it, so changing the primary horizon
would leave the column a **silent mixture** of two regimes — the exact failure
`scoring.py` already refuses one level up, where it deliberately scores only the
primary horizon so `clv_tenths` cannot mix.

Backfilled to `1.0` wherever `clv_scored_ms IS NOT NULL`, which is exact rather
than assumed: the scoring pass has only ever scored at `DEFAULT_HORIZON_HOURS`
and that constant has only ever been 1.0.

The gate reads only rows scored at the **current** primary horizon. A future
change to the horizon therefore invalidates evidence loudly — the counter drops
— instead of quietly blending two measurements.

### 4. The rows already scored at 1.0h are returned to the queue

`clv_tenths` and `clv_scored_ms` are cleared for those ~34 rows in the same
migration, so they re-enter scoring at the new primary horizon.

This mutates the evidence record, so it needs justifying rather than doing
quietly. Nothing is destroyed: their `closing_lines` rows at 1.0h are untouched,
that horizon is now the control, and the operation is reversible from them. The
alternative — leaving them — puts control-horizon values in the primary column
for 34 rows, which is precisely the silent mixture decision 3 exists to prevent.
Correctness beats salvaging 34 observations against a floor of 300.

**The 249 currently-unscored rows become scoreable retroactively**, which is the
one piece of good news here. How many actually recover depends on Kalshi's
candlestick retention, which this project has not measured — a market whose
candles have aged out returns `None` and is counted as `candles_missing`, not
substituted. Expect partial recovery and do not plan on it.

### 5. The composition is asserted, not left to two comments

A test computes the earliest instant a recommendation can exist —
`max_odds_age_ms + due_window_ms` before kickoff — and fails if the primary
horizon plus `WINDOW_MINUTES` reaches back past it. That is the multiplication
nobody performed, written down where CI performs it.

It is deliberately expressed as a relationship between the four constants rather
than as `assert horizon == 0.0`. Pinning the value would pass while someone
widened the due window and reintroduced the same collision from the other side.

## Consequences

- The gate's counter starts moving for the first time. It will still read a
  small number against 300 for a long while, and that is the honest state.
- CLV numbers from before this change and after it are not comparable, and the
  new column is what says so.
- Scoring now depends on candlesticks close to kickoff, which is the busiest
  part of a market's life. If `candles_missing` climbs, that is the thing to
  look at.
- `horizons_agree` compares 0h against 1h. A gap between them is now
  interpretable as pre-game drift over the final hour, which is a more useful
  reading than the 1h-vs-6h version and is worth watching in its own right.

## What this does not establish

That any edge exists. This restores the ability to *measure*, nothing more — and
it lowers the benchmark's generosity, so if a positive CLV survives at the 0h
horizon it means more than the same number would have meant at 1h. Equally, a
result that was going to look good against an hour-old price may now look like
nothing. That is the point of the change.
