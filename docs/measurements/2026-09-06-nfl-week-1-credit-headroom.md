# Does the odds-feed credit budget survive NFL Week 1?

**Taken 2026-09-06.** Read against live (`kalshi-cockpit`, `/data/cockpit.db`,
deploy `7c701ae`, machine version 221) at ~17:38–17:44Z. NFL opens Wednesday
2026-09-09; Week 1 runs to Monday 2026-09-14.

**Verdict: yes, with room. The month is not the constraint — the day is.**

The projected September total is **~13,300 credits against the 18,000 monthly
self-cap** (~26% headroom) and against the paid 20,000 tier. To breach 18,000
the remaining 24.3 days would have to average **663.5 credits/day**, which is
higher than any day ever recorded (max 564, under a design since replaced) and
sits at 95% of the 700 daily cap. **No change to
`ODDS_MONTHLY_CREDIT_BUDGET` is required or recommended.**

What the measurement moved instead: the binding ceiling is
`ODDS_DAILY_CREDIT_BUDGET = 700`, the projected peak day is **540–620**, and
when the daily cap binds it is not a throttle — `decide_sweeps` returns
`fire=()` and **every sport stops for the rest of the budget day**
(`backend/odds/timing.py:1835`).

---

## 1. Does The Odds API's billing period align with our UTC calendar month?

**Yes. Observed directly at the 2026-09-01 boundary, correct to one call.**

`backend/odds/budget.py:63` (`_utc_month_start_ms`) and
`scripts/inspect_live_db.py:1664` (`_month_start_ms`) both assume the meter
rolls at 00:00:00Z on day 1. Two consecutive `api_credits` rows on live:

```
2026-09-01T00:00:44Z  baseball_mlb  cost=4  used=5016  rem=14984
2026-09-01T00:10:50Z  baseball_mlb  cost=4  used=4     rem=19996
```

The server's `x-requests-used` counter reset between those two calls — inside
the first eleven minutes of the calendar month. August's final value (5,012 at
2026-08-31, then 5,016) is the whole month's spend; it returns to 4 immediately
after.

The corroborating check is the drift. At the time of reading, our
September-to-date tally was **1,896** and the server's `used_reported` was
**1,892** — a difference of exactly **4, one call**: the 00:00:44Z sweep, which
we bill to September and they billed to August. Drift is 0.2% and fully
explained. `remaining_reported` will therefore **not** bind before our own
guard: our cap (18,000) is stricter than the plan (20,000), and the two
counters agree, so the ordering in `refusal_reason`
(`backend/odds/budget.py:175-223`) is safe as written.

One other counter discontinuity exists and is **not** a period roll:

```
2026-08-08T21:30:41Z  used=96  rem=428
2026-08-09T05:36:44Z  used=6   rem=19994
```

`remaining` jumped 428 → 19,994. That is the 500 → 20,000 tier purchase of
2026-08-09, distinguishable from a roll precisely because the allowance moved.

## 2. Per-day spend now, and what NFL adds

Every call on live since 2026-08-24 is the same shape — there is no prop or
historical spend in the window:

```
/sports/baseball_mlb/odds            h2h,spreads  us,eu  cost=4  n=682
/sports/basketball_wnba/odds         h2h,spreads  us,eu  cost=4  n=301
/sports/americanfootball_ncaaf/odds  h2h,spreads  us,eu  cost=4  n=280
```

### September to date, per budget day (10:00Z boundary), per trigger

| budget day | floor+schedule | attention | total | sports |
|---|---:|---:|---:|---:|
| 20260901 | 172 | 24 | 196 | 2 |
| 20260902 | 216 | 112 | 328 | 2 |
| 20260903 | 316 | 32 | 348 | 2 |
| 20260904 | 356 | 0 | 356 | 2 |
| 20260905 | 484 | 12 | **496** | 2 |
| 20260906 (partial, 7.7h) | 116 | 0 | 116 | 2 |
| **total** | **1,660** | **180** | **1,840** | |

August's three-sport days, for comparison: 20260827 **508**, 20260828 480,
20260829 472, 20260830 372. The highest day in the record's whole life is
20260824 at **564**, under the fixed `ODDS_DESK_WINDOW_UTC` since unset.

### Largest contributors (CLAUDE.md: a pooled number is not a finding until the parts agree)

- **By sport:** MLB **1,116 of 1,840 = 60.7%**; NCAAF 724 = 39.3%.
- **By day:** 20260905 (NCAAF Saturday) **496 of 1,840 = 27.0%**.
- **By trigger:** floor+schedule **1,660 of 1,840 = 90.2%**; attention 180 = **9.8%**.

The trigger split is the one that changes the picture. **Attention is a tenth
of the bill.** `ODDS_ATTENTION_DAILY_CREDITS = 300` — the cap everyone reasons
about — is not what governs spend. The floor-and-schedule path is, and the
kickoff-window branch inside it is capped by nothing except the 700 daily
total.

### The cadence ceiling, measured

**No sport ever exceeds 6 calls in an hour** anywhere in the record — the
10-minute refresh interval, hit exactly. So the hard per-sport arithmetic is
**24 credits/hour, 576 credits/day at full 24h saturation**. The busiest hour
ever recorded outside the retired props era is 2026-08-27T17Z at 18 calls / 72
credits = three sports each at the ceiling.

### The NFL Sunday projection — this is a projection, not an observation

`americanfootball_nfl` appears **zero times** in `api_credits`. Nothing about
NFL load has been measured. The estimate is anchored on the closest empirical
analog and bounded above by the cadence ceiling.

The analog is NCAAF Saturday **20260905: 74 calls / 296 credits**, spanning
23.0h (10:05:49Z → next-day 09:08:26Z), at the 6/hour ceiling in six of those
hours. A 13-game NFL Sunday is *more* clustered than an NCAAF Saturday, not
less — three kickoff blocks (~17:00Z, ~20:05–20:25Z, ~00:20Z) rather than a
continuous noon-to-midnight rolling slate — so window-hours should be
comparable or fewer, in the region of 12 near-continuous hours:

```
NFL Sunday, projected   ~12h x 6 calls x 4 credits  ~=  288      (ceiling 576)
MLB, observed range                                     200-240
NCAAF Sunday floor                                       50-96
                                                        -------
projected peak budget day                               540-620   vs cap 700
```

### Month projection

```
month to date (server, 2026-09-06T17:38Z)              1,892
elapsed                                                5.735 days
remaining in September                                24.265 days

trailing 5 full budget days, mean                        344.8 /day
baseline carry-forward, no NFL      344.8 x 24.265  =   8,367   -> month 10,263
NFL added (3 Sundays ~288; ~7 Thu/Mon/Wed ~150;
           ~14 floor-only days ~60)                 ~=  3,000   -> month ~13,300
pessimistic flat 500/day            500 x 24.265    =  12,133   -> month  14,029

breach threshold for 18,000  (18,000 - 1,896) / 24.265 =  663.5 /day
```

663.5/day exceeds every day ever observed and is 95% of the daily cap. **The
month fails only if essentially every remaining day runs at the daily
ceiling.**

Two forces work in opposite directions and roughly offset: MLB's regular season
ends **2026-09-27**, removing the single largest contributor (60.7%) just as
NFL ramps; and WNBA — last bought 20260830 — may return for playoffs as a
fourth concurrent sport.

### The risk that is real, and it is the daily cap

A day carrying NFL + MLB + NCAAF + WNBA simultaneously projects to roughly
**770**, past 700. The record has never held more than **three** concurrent
sports, so this is extrapolation. It matters more than a monthly overrun would,
because the daily refusal is global rather than per-sport
(`backend/odds/timing.py:1835`):

```python
if remaining == 0:
    return SweepDecision(
        fire=(),
        ...
```

`fly.live.toml` already records this shape happening once, in the other
direction: *"an NCAAF Saturday (12.5 open hours) landing on an MLB evening:
630-700 credits against this file's 600 daily cap ... NCAAF would have spent
the day and taken MLB's evening down with it."*

## 3. Is `spreads` buying anything at all?

**Yes. A consumer exists, it is production-wired, and it is running right now.**
The "drop spreads and halve the bill for free" lever is closed.

Runtime confirmation, from live at 2026-09-06T17:44Z:

```
fair_prices by market
  h2h                  n=4,001,628   last=2026-09-06T17:44:34Z
  spreads              n=3,558,522   last=2026-09-06T17:44:34Z
  batter_hits          n=   25,914   last=2026-08-16T19:42:49Z
  ...
```

3.56M spread fair prices, most recent one computed within a minute of the read.
This is not a code path that exists on paper.

The trace, end to end:

| step | file:line | what happens |
|---|---|---|
| parse | `backend/odds/client.py:567` | `if market_key not in PRICEABLE_MARKETS` — an allowlist that **includes** `spreads` (`client.py:95`, `:181`) |
| store | `backend/odds/client.py:659` | `INSERT INTO odds_snapshots (... market ... outcome_point ...)` |
| group | `backend/runner.py:791` `spread_quotes_for_event` | `WHERE ... market = 'spreads'`; admits a book only if two-sided and `pointA == -pointB` |
| devig | `backend/runner.py:1212` | `consensus_devig(...)` inside `_price_spread_event` (`runner.py:1124`) |
| persist | `backend/runner.py:1219-1226` | `write_fair_price(..., market="spreads", outcome_points=...)` |
| production caller | `backend/runner.py:2018-2032` | `if event.market_type == MARKET_TYPE_SPREAD: _price_spread_event(...)` |
| read back | `backend/parlays.py:422` | `_LADDER_SQL`: `WHERE f.market IN ('h2h', 'spreads', ...)` |
| leg build | `backend/parlays.py:626-657` | `elif market == "spreads":` — matches the fair row's point to a Kalshi spread subtitle |
| card | `backend/core/ladder.py:131`, `:490` | `TEAM_MARKETS_ONLY = frozenset({"h2h", "spreads"})`; `prefer_spreads=True` on the "Long ladder" recipe |
| screen | `/api/parlays` → `frontend/src/components/ParlayCards.tsx` | rendered; also pushed to Discord as the daily card |

The premise that motivated the question is a **stale comment, and the file says
so itself**. `fly.live.toml:434-446` contains *"Nor could they be used if
something wanted to... `match/linker.py:281` refuses any Kalshi event whose
side-set is not exactly 2, so KXNFLSPREAD (25 sides) ... rejected on every
pass."* That paragraph is retained 2026-08-16 history and is explicitly
overturned eighteen lines above it, at `fly.live.toml:416`: **"CORRECTED
2026-08-23 (ADR 0070): spreads are back, deliberately."**

The 2-sides filter (`backend/match/linker.py:342-346`) genuinely still exists,
but **no longer applies to spread events**: `backend/runner.py:1328-1335`
splits them out before linking and routes them to
`link_prop_event(..., method=SPREAD_LINK_METHOD)`, which inherits the game's
link by fixture segment rather than matching sides.

`totals` remains correctly excluded on both ends — KXNFLTOTAL/KXMLBTOTAL still
hit the `!= 2` refusal, and `totals` is not in `ODDS_MARKETS`. The 41,292
`totals` rows in `odds_snapshots` are dead history, last written 2026-08-16.

**No configuration change was made.** Dropping `spreads` would halve every
sweep and would break the parlay desk's spread rungs — `prefer_spreads` would
become a silent no-op and the "Long ladder" card's stated identity would be
false on screen. Whether the parlay cards *earn* their credits is a different
question, governed by ADR 0038, and is not what this measures.

---

## What this does not establish

- **That the billing period is a calendar month rather than an anniversary
  that happens to fall on the 1st.** Exactly **one** period roll exists in the
  record: the `api_credits` table begins 2026-08-07, so there was no Jul→Aug
  boundary to observe. n = 1. The next boundary (2026-10-01) either confirms it
  or refutes it; the plan was bought 2026-08-09, so an anniversary rule would
  reset on **2026-10-09** and the two are separable in eight days of October.
- **Anything measured about NFL load.** `americanfootball_nfl` has never
  appeared in `api_credits`. The 288-credit Sunday is an inference from the
  NCAAF Saturday analog plus an assumed count of open window-hours. The
  *ceiling* (576/sport/day) is arithmetic and is safe; the point estimate is
  not.
- **Behaviour at four or more concurrent sports.** The record's maximum is
  three (20260825–20260829). The ~770 four-sport figure is extrapolation.
- **The true attention share.** Per CLAUDE.md (2026-09-03), `trigger =
  'attention'` is a **lower bound** — a kickoff-window slot can satisfy the
  cadence before the attention branch runs, stamping the row NULL. So
  attention's 9.8% is an under-count and floor+schedule's 90.2% is a
  corresponding over-attribution. The direction is known; the magnitude is not.
- **That nothing else spends the key.** `kalshi-cockpit-demo` exists (suspended
  at the time of reading) and its database was not read. The 4-credit agreement
  between our tally and the server's `used` over 1,896 credits is strong
  evidence that no second consumer is drawing on the plan, but it was inferred,
  not checked directly.
- **That spread rungs are worth their credits.** Only that they are computed,
  stored and rendered. ADR 0038 governs the value question.
- **Nothing about completeness of `api_credits`.** This counts rows the
  recorder wrote; a call made and not recorded is invisible to it. The server's
  `used_reported` is the independent check, and it agrees.

## Instruments used

`scripts/inspect_live_db.py credits-month`, `credits-tail`, `sweep-log` on the
deployed copy, plus read-only ad-hoc SQL against
`file:/data/cockpit.db?mode=ro` for the per-day × trigger × sport breakdowns,
the reset detector and the hourly cadence histogram. Those four are not
available as inspector subcommands; the requirement has been written up for the
lane splitting that script rather than added here.
