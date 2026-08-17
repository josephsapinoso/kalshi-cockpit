# The Odds API run rate — every recorded row predates the configuration that is running

**Taken:** 2026-08-17, ~19:20Z, live box `kalshi-cockpit`, `/data/cockpit.db`
**Source:** all 111 rows of `api_credits`, read via
`scripts/inspect_live_db.py credits-tail -n 200` (mode `ro`). Not a sample.
**Deployed sha at read time:** `b0bd2ec238dd310f0f2dcf00f9f9925d9e489aa0`, from
`/api/health` on both instances.

**Headline: the forward run rate is UNMEASURED, and this document exists mainly
to say so.** Three configuration changes landed on 2026-08-16 and every one of
the 111 recorded rows was written before they took effect. Any run rate computed
from this table describes a machine that is no longer running.

---

## 1. What the table actually contains

Bucketed on the **10:00Z budget-day boundary** (`backend/config.py:217`,
`budget_day_start_utc_hour = 10`), not the calendar date. The distinction is not
cosmetic: an earlier draft of this measurement used calendar dates and moved the
two decisive days by up to 40 credits.

| budget day (10:00Z) | sweep calls @6 | prop calls @20 | total |
|---|---:|---:|---:|
| 2026-08-07 | 4 = 24 | 0 | 24 |
| 2026-08-08 | 3 = 18 | 0 | 18 |
| 2026-08-09 | 9 = 54 | 0 | 54 |
| 2026-08-10 | 6 = 36 | 0 | 36 |
| 2026-08-11 | 4 = 24 | 0 | 24 |
| 2026-08-12 | 7 = 42 | 0 | 42 |
| 2026-08-13 | 8 = 48 | 0 | 48 |
| 2026-08-14 | 8 = 48 | 0 | 48 |
| **2026-08-15** | 5 = 30 | 18 = 360 | **390** |
| **2026-08-16** | 26 = 156 | 13 = 260 | **416** |
| 2026-08-17 | 0 as of 19:20Z | 0 | 0 |

Cross-checked against the instrument rather than only against my own arithmetic:
`credits-day --date 20260815` returns **23 rows / 390** and `--date 20260816`
returns **39 rows / 416**, matching this table exactly. **`credits-day` has no
boundary defect** — it defaults `--day-start-hour` to the same constant
(`inspect_live_db.py:117`). The error was in the draft that bypassed it.

Two prices, and they are far apart:

- `/sports/{sport}/odds` — the team sweep — **6 credits**, 80 calls all-time.
- `/sports/{sport}/events/{id}/odds` — per-event **props** — **20 credits**,
  31 calls, first **2026-08-15T19:41:53Z**, last **2026-08-16T17:06:36Z**.

---

## 2. Why none of it projects — three changes, all deployed, all after the data

Each verified as an ancestor of the deployed `b0bd2ec`, and the resulting values
read back off the live machine's own environment (`env | grep ^ODDS_`) rather
than from `fly.live.toml`:

| commit | change | effect on cost |
|---|---|---|
| `4600f87` (08-16 16:55Z) | daily cap 400 → 600 | ceiling only |
| `83432c1` (08-16 19:01Z) | `ODDS_BUY_PROPS_ON_SCHEDULE=false` (ADR 0032) | the 20-credit calls **stop** |
| `d4afa53` (08-16 23:33Z) | `ODDS_MARKETS` 3 markets → `"h2h"` | a sweep goes **6 → 2** credits |

Live machine now reports `ODDS_MARKETS=h2h`, `ODDS_REGIONS=us,eu`,
`ODDS_BUY_PROPS_ON_SCHEDULE=false`, `ODDS_DAILY_CREDIT_BUDGET=600`,
`ODDS_MONTHLY_CREDIT_BUDGET=13000`.

**The last recorded sweep (2026-08-16T22:59:23Z) cost 6, i.e. it ran under the
three-market config, 34 minutes before `d4afa53` was even committed.** The last
prop call predates the props-off commit. So `n = 0` rows exist under the running
configuration.

`sweep_cost = max(1, len(markets) * len(regions))` (`backend/odds/budget.py:66-68`)
gives **1 × 2 = 2** at the deployed values. Applied to 2026-08-16's shape, the
same day would cost `26 × 2 = 52` instead of 416 — an **8× reduction**.
**That is arithmetic and it is not published as a rate.** This repo's own rule is
that a ceiling is not a spend; a formula is not one either.

---

## 3. Two days is not a run rate, and neither of them was clean

Even confined to the configuration it describes, the 08-15/08-16 pair cannot
carry a projection:

- **2026-08-15 hit its ceiling.** The cap was 400 that day and the day spent
  390, with refusals recorded — `.env.example:45-48` documents that the first
  live prop sweep spent 384 in a single pass and *"refused every remaining odds
  sweep that day, team sweeps included."* `CreditBudget.refusal_reason`
  (`budget.py:178-225`) refuses **pre-call**, so the day reports the cap, not
  demand. True demand was higher by an unmeasured amount.
- **2026-08-16 spans both a cap change and the prop shutdown.**
- **Both are weekend MLB slates** — Saturday and Sunday in mid-August, the
  fullest of the week. Prop cost is linear in fixture count, so this is n = 2
  drawn entirely from the top of the distribution.
- **The parts do not agree.** Sweep leg 30 → 156 (up 5×); prop leg 360 → 260
  (down 28%). The pooled totals (390, 416) matched **by cancellation**. An
  earlier draft cited that agreement as evidence the mean was safe. It was the
  opposite.

---

## 4. What survives, and it is enough for the invoice question

**At the deployed daily ceiling of 600, enforced pre-call, the 18,896 credits
remaining on 2026-08-16 cannot be exhausted before 2026-09-17.**

18,896 ÷ 600 = 31.5 days. This claim needs no run rate, no configuration
assumption, and no renewal date — it covers both candidate renewals (a 09-09
anniversary and a 09-01 calendar reset) with eight days of margin.

**The renewal date is recorded nowhere in this repository.** 2026-09-09 is a
guess: purchase date plus an assumed monthly anniversary. `setup_odds_key.sh:216`
records `EXPECTED_TIER=20000` and nothing about a cycle; the provider sends
`x-requests-remaining` and `x-requests-used` and no reset header.
**It is measurable, not guessable** — `remaining_reported` jumps back to 20,000
on the first call after the cycle rolls, and `api_credits` stores that header on
every row. One `credits-tail` read in September dates it exactly.

Note for whoever relies on the monthly guard: `ODDS_MONTHLY_CREDIT_BUDGET`
(13,000) is on the **calendar** month (`_utc_month_start_ms`), while the tier, if
it is an anniversary plan, is not. There is a window each cycle where our guard
is fresh and the tier's allowance is not. It does not bite today only because the
daily cap binds first.

---

## 5. Two figures in the record, checked rather than assumed

- **`fly.live.toml:156` / ADR 0032 §2 — "the measured day was 338 = 266 opening
  + 72 refresh". This is CORRECT and is not contradicted.** It was flagged as
  irreconcilable with a 416-credit day; it is not, because the sentence says
  **"one cluster"** and means it. 266 opening (1 sweep + 13 prop fixtures) + 72
  refresh tail = 338 for that cluster; the day's other 13 sweep calls add 78;
  338 + 78 = **416**. It reconciles exactly. **No correction is owed and this
  paragraph exists so it is not reopened.**
- **`tasks/NEXT.md:399-400` — "Seven days, ~158/day, on pace for ~24% of the
  tier".** Arithmetically fine when written (1,104 ÷ 7). It is a backward-looking
  average spanning the pre-prop days *and* the prop days, so it describes no
  configuration that ever ran continuously — and none that runs now. Same defect
  as the 412/day figure this document was originally written to publish.

---

## 6. `used_reported` vs our tally — unreconciled, and not by 4

`MAX(used_reported)` is 1,104 and `SUM(cost)` is 1,100, which looks like
agreement to within 4. **It is not comparable across the whole table**: the
2026-08-07/08 rows sit on the old free tier (`remaining + used = 500`), which has
its own counter. Free-tier recorded spend is 12 + 24 = 36, so paid-tier recorded
spend is 1,064 against a paid-tier `used_reported` of 1,104 — an unexplained
**~40 credits**, not 4.

**What that implies is real and should not be lost:** there is at least one
spender of this key that `api_credits` does not see. `CreditBudget.record` is
written only from `client.py:324`/`:404`, so any operator CLI using the key from
a laptop — `scripts/probe_prop_dispersion.py` is the obvious candidate — spends
unmetered. **"Cannot be exhausted at the ceiling" is therefore a claim about the
Fly box, not about the key.** Which script accounts for the 40 is a hypothesis
here, not a finding.

---

## 7. What this does not establish

- **Nothing about the forward rate.** `n = 0` under the running configuration.
  The first measurable window opens 2026-08-17T20:50Z.
- **Nothing about whether the spend is worth it.** That is the invoice question
  and it is Joe's. This document is the run rate only.
- **Nothing about demand on 2026-08-15**, which the cap censored.
- **Nothing about the renewal date**, which is unsourced.
- **Nothing from a manual tap.** All 111 rows carry `trigger` NULL under the
  real predicate `COALESCE(trigger, '') != 'manual'`. The on-demand path has
  never fired in production, all-time.
