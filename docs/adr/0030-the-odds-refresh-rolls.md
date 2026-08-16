# 0030 — The odds refresh rolls, and the fast cadence carries it

**Date:** 2026-08-16
**Status:** Accepted.
**Owns:** the rolling odds refresh — `refresh_interval_ms`, `firing_for_slot`,
`SweepSlot.calls_remaining`, `DUE_WINDOW_MS = 60min`, and the odds leg on
`run_quote_pass`. Also owns the decoupling of `SLATE_WINDOW_MS` from
`DUE_WINDOW_MS`, and the display timezone pin.
**Does not touch** `MAX_ODDS_AGE_S`, which stays at 900. It does not relax a
single threshold, and that is the point of the whole change.
**Related:** ADR 0004 (two polling cadences), whose arithmetic this extends;
ADR 0025, whose subject — what `stale_odds` actually means — this does not
re-open.

---

## 1. The question that started it

> *"A lot of the reject reasons say stale odds. They're always going to be stale
> technically, right, since the odds are constantly streaming. So shouldn't it
> (a) be more forgiving and (b) update just as live as the Kalshi tickers?"*

Both halves are worth answering separately, because one of them is right and the
other is a trap.

## 2. (a) More forgiving: no, and the reason is arithmetic

`stale_odds` does not mean "the line moved". `odds_age_ms` is measured from The
Odds API's `last_update`, which is a **scrape** stamp — 320 of 320 book/event
pairs quoting more than one priceable market carry one identical stamp across
every market, and FanDuel reports the same second for fifteen different games.
The guard measures *how old our copy is*, not how stale the price is.

So loosening it does not make the odds newer. It permits betting against a copy
bought forty minutes ago, on the hope the line has not moved. Against a measured
cost headroom of **0.63 points — itself an upper bound pending H4** (ADR 0027) —
a line drifting one point inside that window consumes the entire edge twice
over. Forgiveness here does not find edges; it manufactures them. This is rule 1
of the three: *a large apparent edge is a bug until proven otherwise.*

**The threshold was never the defect.**

## 3. (b) As live as Kalshi: the right instinct, aimed at the wrong number

Kalshi's side already is live — websocket, 30s limit, `run_quote_pass` every
15s. The sportsbook side was not, and the reason had stopped being true:

| | Old | Now |
|---|---|---|
| Buys per kickoff cluster | 1 | one per `refresh_interval_ms` while the slot is due |
| Window open per cluster | `max_odds_age_ms` = 15 min | `DUE_WINDOW_MS` = 60 min, continuous |
| Bound by | the scheduler | the credit budget, as it should be |

**What a cluster costs, measured rather than projected.** A 13-game MLB cluster
on the live instance: 6 for the team sweep, 260 for props (13 x 20, once), and 6
per refresh for the rest of the window — **302 credits**, against 266 before.
The refresh is **+36, a 13% increase**; props are 86% of the bill and were
already the binding constraint. At the 600/day cap that is 2 clusters a day,
which is what it was before this change; raising the cap from 400 to 600 is what
bought the second one. **The screen is now open for 60 minutes per cluster
instead of 15, at a 13% higher price** — and if more clusters a day are wanted,
the lever is props, not this.

`stale_odds` was **256 of 265 suppressions in 24h** on the live instance. The
cause was that nothing re-bought. A cluster got one call, the window shut fifteen
minutes later, and every row priced afterwards was suppressed with the games
still an hour out.

**The budget stopped being the constraint on 2026-08-09.** The 20K tier lifted
the daily cap to 400 against a 6-credit sweep; `fly.live.toml` sets no prop
markets, so the deployed spend was a handful of calls a day against 400. The
scheduler was rationing a resource that was no longer scarce.

## 4. Why the refresh could not ride the full pass

This is the load-bearing arithmetic and it is why a metered call now sits on the
cheap cadence.

A refresh is only *considered* when a pass runs, so the worst-case age of stored
odds is `refresh_interval_ms + one pass interval`:

- On the **900s full cadence**: `600 + 900 = 1500s` against a 900s limit. Stale
  for two thirds of every cycle — the state being fixed, reproduced.
- On the **15s quote cadence**: `600 + 15 = 615s`, comfortably inside 900s.

Running the full pass at 15s instead would fetch candlesticks for every started
game 240 times an hour, which is what split the cadences in the first place
(ADR 0004).

`refresh_interval_ms` is **derived** as `max_odds_age_ms * 2 // 3`, never written
down beside it. Two constants for one quantity drift, and the tighter one wins in
silence — the exact failure ADR 0004 records for `MAX_ODDS_AGE_S` against the
Kalshi limit.

## 5. What bounds the spend

Not the cadence. The pass asks on every 15s tick and `decide_sweeps` answers
"not yet" on all but one in forty. Three guards, each tested by disabling it:

1. **`refresh_interval_ms`** paces the calls, read back from `api_credits` — not
   process memory — so a restart mid-window cannot double-buy.
2. **`allow_bootstrap=False` on the quote pass.** A bootstrap has no slot and so
   no interval to pace it; its only cap is one attempt per sport per day, which
   on a 15s cadence exhausts the day's sports within minutes of a restart.
   Bootstrap belongs on the full pass and is not time-critical by construction.
3. **Props ride the opening call only.** They are billed per event per market key
   per region — 20 credits an event — so re-buying them each refresh would
   multiply the largest line item in the file by the refresh count.

   **This guard is load-bearing today, not hypothetical, and the first draft of
   this ADR said the opposite.** It read "the live config sets no prop markets
   today, so this changes nothing that currently runs". That was inferred from
   `fly.live.toml` carrying no `PROP` variable, and it is wrong: the prop market
   keys come from `prop_market_keys()` in code, not from the environment, so
   props are on by default and always have been. Measured on the live instance
   immediately after this deployed (2026-08-16, budget day 10:00Z):

   ```
   /sports/baseball_mlb/odds                  1 call     6 credits
   /sports/baseball_mlb/events/<13 fixtures>  13 calls  260 credits
   TODAY TOTAL                                          266 of 600
   ```

   Without this guard, each of the six refreshes in a sixty-minute window would
   have re-bought that 260 — **1,560 extra credits in one window**, against a
   600/day cap and a 13,000/month one. The change would have drained the month
   in a day. The lesson is the repo's own: *grep for the caller before believing
   a config value describes behaviour.* An absent environment variable means the
   default applies, not that the feature is off.

### 5.1 The reservation refuses to *start*, not to *continue*

`SweepSlot.calls_remaining` prices the tail so the planner reserves the whole
window it authorises — the same principle as the prop tail. But the affordability
**gate** is one call, not the tail, and the asymmetry is deliberate:

- Each call independently buys a usable `max_odds_age_ms`. A slot held for twenty
  of its sixty minutes is strictly better than a slot not opened, and "not
  opened" is the all-day state this change ends.
- The prop tail refuses instead because it is a 20x multiplier discovered at
  spend time that can empty the day in one pass. A refresh tail is 6 credits
  paced ten minutes apart and drains gradually, which `remaining == 0` catches.

A window opened short says so in `sweep_decision` rather than shutting quietly.

## 6. Consequences taken deliberately

**`SLATE_WINDOW_MS` is no longer an alias of `DUE_WINDOW_MS`.** The alias was
sound while the two wanted the same number and stopped being sound the moment
`DUE_WINDOW_MS` became the length of the open window: widening the sweep schedule
would have silently widened how far back the Board calls a row "current". It is
now pinned at 30 min with an import-time assertion that it stays inside
`DUE_WINDOW_MS`, so it inherits the worst-case-gap check `run_loop` already runs
at startup rather than growing a second, unchecked one.

**The 1.0h CLV control horizon is now exactly at the boundary.** Widening
`DUE_WINDOW_MS` moved the earliest possible entry from 45 to 75 minutes before
kickoff, and a 1.0h horizon observes its closing line at `60 + WINDOW_MINUTES` =
75. They coincide to the minute. Equality is still unscoreable — `entry` is the
earliest *conceivable* moment a row can exist, and every row not written in that
instant is entered after the close — but it is a boundary, not a margin.
`tests/test_clv_horizon_composition.py` now asserts `>=` and says so.
**Raising `DUE_WINDOW_MS` again makes 1.0h scoreable and silently invalidates
that pinning.**

**A quote pass can now spend money, which it could not before.** Its docstring
used to say so proudly. The claim narrowed rather than vanished: a pass handed no
odds client still cannot spend, which is what keeps every test, script and demo
caller unable to spend by accident.

**A residual hazard, named.** A transport failure records no credit, so the
pacer reads "never swept" and the next pass retries — on a 15s cadence rather
than 900s. It is bounded by `MAX_CONSECUTIVE_FAILURES`, which takes the container
down loudly, and by `budget.refusal_reason` before every call. It is not bounded
by the refresh interval. If this ever bites, the fix is to pace on recorded
*attempts* rather than recorded *serves*, which means reading last-attempt from
`odds_sweep_log`; it is not built now because the failure counter already turns
the loop off.

## 7. What this does not establish

**That anything will be bettable.** The window is a precondition, not a finding.
Most windows will open onto an empty Board — that is the expected result of the
premise, and `actionable` has been zero for the life of the project. What changes
is that a zero Board now means *the consensus said no*, rather than *nobody
looked*. Those need opposite responses and were indistinguishable until now.

**That the fee headroom is real.** Untouched. See ADR 0027 and H4.

**That `stale_odds` is semantically correct.** Untouched. See ADR 0025 — this
change makes the guard fire far less often without altering what it means.

## 8. Also in this change: one timezone for every clock

Unrelated to the refresh, requested in the same session, recorded here rather
than in an ADR of its own because it is a display decision with no strategy
consequence.

The site rendered times three ways at once: `formatClock`/`formatKickoff` passed
`undefined` as the locale (the *device's* zone), `slate/page.tsx` printed
`getUTCHours()`, and `playbook/page.tsx` printed `toISOString()`. The same
instant read 16:51 on the phone and 23:51 on the page beside it, with nothing
saying which.

All human-facing clocks now render through `DISPLAY_TIME_ZONE =
"America/Los_Angeles"` — a named IANA zone, not a fixed offset, so daylight
saving is the platform's problem — and the zone label is drawn from the same
formatter, so it says PDT when it is PDT. `tests/test_display_timezone.py` pins
it.

**The stored record is unchanged and remains UTC everywhere.** The three-hour
`occurrence_datetime` defect this repo has already paid for lived in *stored and
compared* values; no display format could have caused or prevented it, and the
"never mix clocks" lesson was over-applied to a label a human reads.
