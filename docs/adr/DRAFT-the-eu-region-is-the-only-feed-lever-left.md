# The `eu` region is the only feed lever left, and it is not to be pulled before 2026-09-28

**Status:** proposed, 2026-09-07. Written three days before the NFL season
opens, so that October does not re-derive the three decisions it records.

> Drafted without an ordinal, per `docs/adr/README.md`. The number is taken in
> the merge commit, after `git fetch`, as the last thing before the push.

## Context

Joe asked on 2026-09-06 to combine player props and totals with game legs
on the parlay desk. Kalshi already permits it: its per-week NFL collections
carry ten market families a game (`KXNFLTOTAL`, `KXNFLFIRSTTD`,
`KXNFLRECYDS` and the rest — `tasks/NEXT.md`, 2026-09-06 fifth entry). The
blocker is not the venue. It is what the odds feed buys.

Every odds call costs `sweep_cost = max(1, len(markets) * len(regions))`
credits (`backend/odds/budget.py:66-68`). Live runs
`ODDS_MARKETS = "h2h,spreads"` (`fly.live.toml:486`) against
`ODDS_REGIONS = "us,eu"` (`fly.live.toml:437`), so every call is **4**
credits, out of `ODDS_DAILY_CREDIT_BUDGET = "700"` (`fly.live.toml:252`).
That cost is charged whether or not any leg needs the extra market: a market
key multiplies every call, every sport, every day.

The record this decision rests on is
`docs/measurements/2026-09-06-nfl-week-1-credit-headroom.md`, §2 and
Amendment 1:

```
September to date, per budget day (10:00Z boundary):
  20260901 Tue  196     20260904 Fri  356
  20260902 Wed  328     20260905 Sat  496   <- the largest observed day, two sports
  20260903 Thu  348     20260906 Sun  116 (partial, 7.7h)
mechanism share of September's 476 served sweeps (odds_sweep_log.detail):
  kickoff window  319   67.0%
  hourly floor    107   22.5%
  desk open        50   10.5%
Simulated NFL Sunday 09-13:  ~486 expected, ~786 arithmetic ceiling, truncated at 700
```

When the 700 binds, `decide_sweeps` returns `fire=()` and **every sport
stops** until the next 10:00Z boundary (`backend/odds/timing.py:1924-1934`,
the `remaining == 0` return). The cap is a truncation of the whole day, not a
throttle on the sport that overspent.

## Decision

Three things are decided here. Two are refusals and one is a dated option.

### 1. Player props are killed, not deferred

Per-player market keys are one key *per player per market family*, so the
multiplier is not 1.5× but whatever the roster is. It is refused outright
rather than priced, for two reasons that do not depend on the number:

- The in-house substitute is already refuted. ADR 0037 measured, on 255
  settled `KXMLBHR 1+` markets, a model-vs-Kalshi disagreement of sd **3.72
  points** against the model's own error of **4.04** — every apparent edge is
  our own noise (`CLAUDE.md`, "Do not rebuild these"). Modelling props to
  fill the gap the feed leaves is not open.
- Buying the books' prop lines is a different proposition from modelling
  them, and only that one *could* be open — but it multiplies every call by
  the roster, on a feed whose largest observed day is already 71% of the cap
  at two sports. There is no arithmetic under which it fits beside NFL.

Do not price player props together with totals. They are separate buys of
different orders of magnitude, and the earlier entry that lumped them was
corrected the same day (`tasks/NEXT.md`, 2026-09-06 sixth entry).

### 2. Totals are refused this season under `us,eu`

Adding `totals` makes every call `3 × 2 = 6` credits: **+50% on every call,
every sport, forever**. Against the record:

```
largest observed day (two sports)   496
x 1.5                               744   > 700
```

A day the desk has *already had* would have crossed the cap with totals on,
and it would have crossed it before NFL added a single sweep. On the cap
binding, every sport stops — so buying totals means turning the desk off on
NFL Sunday. No correction to the published bound changes this: item 1 was
never gated on the 2026-09-06 bound correction, whatever the previous entry's
ordering implied.

The settled reason not to show a totals leg the feed cannot devig was decided
hours earlier in the opposite context and applies unchanged: *"a live leg
arrives with no fair value at all and the only number left is Kalshi's own. A
card comparing Kalshi to Kalshi shows a cost while implying a judgement it is
not making."* A `KXNFLTOTAL` leg without `totals` in the feed is that object
exactly.

### 3. The one lever: drop `eu`, dated 2026-09-28

`h2h,spreads,totals × us` = **3 credits — cheaper than today's 4.** It is the
only configuration that admits totals without raising the per-call cost. It is
**refused until 2026-09-28**, on two preconditions:

1. MLB's regular season has ended (2026-09-27), so the sport that has carried
   the whole CLV record leaves scope before its fair values change shape.
2. NFL Weeks 1–3 have supplied a **measured** four-sport budget day. The
   record has never held more than three concurrent sports; the 09-13 figure
   above is a simulation, and a lever that lowers the cost of every call is
   worth pulling against a measured day, not a projected one.

It is refused *this* week because it changes the book composition of every
fair value the desk shows, three days before the largest slate it has ever
seen. A change to what "fair" means is not a change to make blind on opening
weekend.

## What must be measured before the lever is pulled

**Dropping `eu` removes the sharp anchor, and that is a finding of this draft
rather than a detail.** The sharp set is
`SHARP_BOOKS = {"pinnacle", "betfair_ex_eu", "betfair_ex_uk", "matchbook"}`
(`backend/runner.py:152`). None of those is a `us`-region book on The Odds
API. Under today's `us,eu` the live sharp set is Pinnacle and Betfair EU;
under `us` alone it is empty. `consensus_devig` selects
`selected = sharp or usable` (`backend/core/devig.py:289`) — a sharp anchor
narrows the fair value to at most three books — and sharp anchoring was
**73.0%** of the pinned record (1,141 of 1,564, ADR 0021 §8, via
`CLAUDE.md`). So the lever as stated trades every sharp-anchored fair value
for a soft-book consensus in exchange for totals. That may still be the right
trade. It is not one to take without the numbers:

- Per sport, the share of `fair_prices` rows whose `anchored_on_sharp` is
  true, and the `usable` book count with and without the `eu` books. Which
  books does dropping `eu` actually remove, and how many rows go from a sharp
  anchor to a soft consensus?
- The devig-method spread (the worst-of-four rule, CLAUDE.md rule 2) on the
  same rows under both book sets. If the spread widens past the fee bar, the
  lever costs more than the credit it saves.
- Whether The Odds API's `uk` region carries Pinnacle or the Betfair
  exchanges at a cost that keeps the call at 3 — that is, whether the sharp
  anchor can be kept by swapping regions rather than dropping one. Not
  assumed either way; read `/v4/sports/{key}/odds?regions=uk` once and count.
- The measured four-sport day from precondition 2, read by trigger with
  `scripts/inspect_live_db.py credits-day --date …`.

Nothing here moves a config value. `fly.live.toml` is integrator-only
(`docs/adr/README.md`, "Lane ownership") and this draft touches it nowhere.

## Two things this draft records so they are not re-derived

### `sorted(fixtures)` is left alone, for five reasons, with a gate

The floor loop serves sports `for sport_key in sorted(fixtures)`
(`backend/odds/timing.py:2242`), and the 2026-09-06 simulation noted that
under a binding cap football is served and MLB/WNBA starve — `sorted()` for
determinism, not a chosen priority. The partner reviewed it on 2026-09-07 and
it stays as it is:

1. **The stated victim is the flattering reason.** "MLB is the CLV
   population" is not live: ADR 0038 closed the hunt, `G_eff` is 1.81 on the
   committed data, and the declaring look needs ~52,052 nominal games against
   a stopping rule that ends 2027-02-15 (`CLAUDE.md`).
2. **The victim is also wrong.** The key order is `americanfootball_ncaaf` <
   `americanfootball_nfl` < `baseball_mlb` < `basketball_nba` <
   `basketball_wnba` < `icehockey_nhl` (`backend/kalshi/discovery.py:235-242`).
   MLB leaves scope on 2026-09-27; `icehockey_nhl` sorts last **permanently**
   from October. A sort-key fix for MLB would be obsolete in three weeks and
   would then quietly starve hockey instead.
3. **The blast radius is one pass, not a day.** `remaining` is
   `state.remaining_today // cost` (`timing.py:1907`) — the whole day's
   credits, not a per-pass quota — so `len(firing) >= remaining`
   (`timing.py:2243`) and `cost > credits_left` (`timing.py:2301`) bite only
   in the pass that empties the day. Every pass after that returns `fire=()`
   for everyone, symmetrically.
4. **The recurring order-dependence is milder than "starve".** What actually
   moves inside the loop is the attention slice
   (`timing.py:2265-2269`, and the comment at `:2252-2256` says so): the
   sport that empties the slice is served at the attended cadence and the
   next one down drops to the **hourly floor** — stale by an hour, not dark
   — and since 2026-08-29 that is a fall-through, not a skip.
5. **Neither ceiling has bound this way.** The 700 daily cap never has; the
   attention slice bound on one of nine observed budget days (20260827).

**Gate:** `credits-day` by trigger on 2026-09-13 and 2026-09-20. If the 700
binds on a real NFL Sunday this goes live — **and the fix is still not a sort
key.** The spender is the kickoff-window loop (`timing.py:2068` onward, 67.0%
of September's served sweeps), whose only gate is `credits_left` itself.
Reorder `sorted()` and one bound relaxes while the unallocated window loop
binds next in silence, symptom unchanged. The fix would be a per-sport
reservation taken off the top of the day, which is a design change with its
own ADR.

### The `exchange_index` item is killed, and the reason it was open was wrong

`tasks/NEXT.md` carried it as: the single/manual order path sends no
`exchange_index` while `combo_bids.py` "does it correctly". The create body
carries no shard on **either** path. `OrderRequest.to_api_dict()` sends
`ticker`, `client_order_id`, `side`, `count`, `price`, `time_in_force` and
`self_trade_prevention_type` (`backend/kalshi/orders.py:336-344`);
`combo_bids` posts exactly that dict to `/portfolio/events/orders`
(`backend/combo_bids.py:209-211`). What `combo_bids` does right is *around*
the create: it reads the shard off the mint response, scopes the balance
check to it (`combo_bids.py:148-151`, `api.balance(exchange_index=…)`), and
persists it so the cancel can route.

The manual route is shard-unaware end to end, and its affordability cap reads
`db.latest_balance_tenths(conn)` (`backend/api/routes.py:3290`), filled by
`portfolio_poll.py:839`'s `client.balance()` with no argument — the pooled
total that `rest.py:636-650` warns "a caller deciding whether an order can be
paid for must read the shard the MARKET is on, never the total." That is a
real gap on an armed real-money route.

It is killed anyway, on three facts:

- All 420 markets in both captured NFL fixtures carry `exchange_index: 0`,
  and shard 0 is what omission gives. Wednesday is unaffected.
- Baseball is where it would misroute, baseball's shard 3 is unfunded
  (`user_not_found`, 2026-08-30) so the order fails either way, and baseball
  leaves scope on 2026-09-27.
- The route has placed **0 of 27** real bets in eleven days
  (`docs/measurements/2026-09-04-presence-at-the-moment-of-a-bet-result.md`).
  ~50 lines plus a schema column, on a path nobody uses, for a sport that is
  leaving.

Record the finding; do not build it. If the manual route is ever used on a
non-zero shard, this section is where the work starts.

## Consequences

- `ODDS_MARKETS` and `ODDS_REGIONS` do not change before 2026-09-28, and
  the change on that date is a decision to be taken against the measurements
  above, not a scheduled edit.
- No totals leg and no prop leg reaches a parlay card this season, and the
  card's copy must not imply otherwise. `TEAM_MARKETS_ONLY = {"h2h",
  "spreads"}` (`backend/core/ladder.py:131`) stays as the one visible edit
  per card that admitting a market class would need.
- The `sorted()` question has a gate and a named non-fix. A session that
  reads a cap binding on 09-13 does not reach for the sort key.
- The `exchange_index` gap is on the record with its reachability, so the
  next reader does not rediscover it as urgent.

## What this does not decide

Whether dropping `eu` is *correct* — only that it is the one lever whose
arithmetic fits, and what has to be measured before anyone finds out. It does
not decide the per-sport reservation the gate might call for. It does not
reopen the hunt: a totals fair value, if one is ever bought, is shown on a row
and never ranked by (ADR 0071).
