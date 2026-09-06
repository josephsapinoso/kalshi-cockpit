# NFL Week 1 credit headroom: the month is bounded safe, the day is not settled

**Taken 2026-09-06**, against live (`kalshi-cockpit`, `/data/cockpit.db`, deploy
`7c701ae`, machine version 221) at 17:38–18:02Z.

**Re-read after the first NFL Sunday (2026-09-13/14), or after the first
four-sport budget day, whichever comes first.** The 2026 NFL season opens
Wednesday 2026-09-09 and Week 1 closes Monday 2026-09-14; this document is
written before any NFL odds call has ever been made, and the first Sunday is
what converts its central projection into an observation.

---

## The verdict, and it is a bound rather than a forecast

**The paid 20,000-credit September tier cannot be exhausted, and this is
arithmetic rather than estimation.** At the read, September-to-date was 1,896
credits with 24.265 days remaining. `ODDS_DAILY_CREDIT_BUDGET = 700` is
enforced **before** each call (`backend/odds/client.py:343`) and again as a
global planner stop (`backend/odds/timing.py:1835`), so the maximum possible
September total is:

```
1,896 + 700 x 24.265  =  18,881   <  20,000
```

Every remaining day could pin the daily cap and the plan still holds. The
**18,000 self-cap** is the only ceiling reachable at all, and reaching it needs
the remaining 24.265 days to average **663.7/day — 94.8% of the cap**.

**This conclusion does not rest on any projection below.** It is insensitive to
every defect in the base period, to the NFL analog, and to the trend: none of
them can move a day past the cap that truncates it. The projections are
published because they say where inside the bound we probably sit, not because
the verdict needs them.

**Recommendation: do not raise `ODDS_MONTHLY_CREDIT_BUDGET`.** Not because
18,000 is comfortable, but because the gap to 20,000 is **not spare capacity** —
`fly.live.toml:254-263` records it as a deliberate reserve for historical
pulls, which cost 10x per call: *"The gap to 20,000 is deliberate headroom for
that work ... narrowed to ~2,000 — a deliberate trade."* Spending the reserve
to buy headroom we can show is not needed would be paying twice.

### Sensitivity: September total against a flat forward rate

No point estimate is published. The reader picks the row.

| forward rate | where it comes from | Sept total | vs 18,000 | vs 20,000 |
|---:|---|---:|---|---|
| 307 | trailing 5 days, largest dropped | 9,345 | under | under |
| 458 | August's four three-sport days | 13,009 | under | under |
| 496 | the single largest day in the base | 13,931 | under | under |
| 620 | top of my own projected NFL-Sunday peak | 16,940 | under | under |
| **663.7** | **breach threshold for 18,000** | **18,000** | **at** | under |
| 700 | the daily cap, every remaining day | 18,881 | **over by 881** | under |

Even a September in which *every* remaining day equals the worst day this
document projects (620) lands **1,060 under** the self-cap.

### What a breach would actually cost, since the two differ sharply

- **Daily (700):** `decide_sweeps` returns `fire=()` — **every sport stops**,
  not just the one that overspent (`backend/odds/timing.py:1835`). Resets at the
  next 10:00Z budget-day boundary, so it is bounded to under 24 hours.
- **Monthly (18,000):** `refusal_reason` refuses at `backend/odds/client.py:343`
  on every call for every sport, and the condition is month-scoped — it persists
  until 00:00Z on the 1st. **That is days-to-weeks of a dark slate**, and it is
  the more expensive failure even though it is much the less likely one.

---

## 1. Does The Odds API's billing period align with our UTC calendar month?

**Yes, observed directly — and the safety of the guard does not depend on it.**

`backend/odds/budget.py:60` (`_utc_month_start_ms`) and
`scripts/inspect_live_db.py:1664` (`_month_start_ms`) both roll at 00:00:00Z on
day 1. Two consecutive live rows:

```
2026-09-01T00:00:44Z  baseball_mlb  cost=4  used=5016  rem=14984
2026-09-01T00:10:50Z  baseball_mlb  cost=4  used=4     rem=19996
```

The server's `x-requests-used` counter reset inside the first eleven minutes of
the calendar month.

**The anniversary hypothesis is already refuted, not merely untested.** The plan
was bought 2026-08-09, so a purchase-anniversary rule predicts a reset on
2026-09-09. A reset was observed on 2026-09-01. What remains open is only an
anniversary of some *earlier* event that happens to fall on a 1st — which is
operationally indistinguishable from a calendar month, forever. (An earlier
draft of this document proposed an October test for the anniversary rule. That
test was already answered by the September observation and has been removed.)

**Why the n=1 does not matter anyway, and this is a code fact rather than an
inference.** `refusal_reason` (`backend/odds/budget.py:178-225`) checks the
server's own `remaining_reported` **first**, ahead of both our ceilings. If our
month boundary ever disagreed with theirs, theirs is still the outermost guard —
it is the one that stops answering. Alignment is reassuring for *reconciliation*;
it is not what makes the refusal ordering safe.

### The drift, promoted from an inference to a result

Our September tally was **1,896**; the server's `used_reported` was **1,892** —
a difference of exactly **4, one call**: the 00:00:44Z sweep, which we bill to
September and they billed to August.

**This rules out a second consumer on the API key.** A second consumer could
only push the server's count *above* ours; ours is above theirs, by exactly the
one call the boundary explains. `kalshi-cockpit-demo` (suspended at the read)
therefore is not drawing on the plan.

### The other counter discontinuity is a tier change, not a roll

```
2026-08-08T21:30:41Z  used=96  rem=404   (sum 500)
2026-08-09T05:36:44Z  used=6   rem=19994 (sum 20,000)
```

The allowance itself moved, which is what distinguishes a purchase from a
period roll. The free tier was **500**, confirmed on every co-occurring pair
(2026-08-07: 60+440 and 66+434; 2026-08-08: 72+428 and 96+404 — all exactly
500). A reading that pairs the day's `MAX(used)` with its `MAX(remaining)` gets
524 and looks like a contradiction; those two values are from different rows.
That is the same MIN/MAX-straddling trap that made `credits-month` report a
September max of 5,016 — see §4.

## 2. Per-day spend, and what NFL adds

Every call on live since 2026-08-24 is one shape — no prop or historical spend
in the window:

```
/sports/baseball_mlb/odds            h2h,spreads  us,eu  cost=4  n=682
/sports/basketball_wnba/odds         h2h,spreads  us,eu  cost=4  n=301
/sports/americanfootball_ncaaf/odds  h2h,spreads  us,eu  cost=4  n=280
```

### September to date, per budget day (10:00Z boundary), per trigger

| budget day | weekday | tagged NULL | `attention` | total | sports |
|---|---|---:|---:|---:|---:|
| 20260901 | Tue | 172 | 24 | 196 | 2 |
| 20260902 | Wed | 216 | 112 | 328 | 2 |
| 20260903 | Thu | 316 | 32 | 348 | 2 |
| 20260904 | Fri | 356 | 0 | 356 | 2 |
| 20260905 | Sat | 484 | 12 | **496** | 2 |
| 20260906 (partial, 7.7h) | Sun | 116 | 0 | 116 | 2 |
| **total** | | **1,660** | **180** | **1,840** | |

**Reconciliation, because 1,840 and 1,896 will otherwise read as an
inconsistency.** They measure different windows. The budget day rolls at
10:00Z, so the 14 calls between 2026-09-01T00:00Z and 10:00Z (56 credits) fall
in budget day **20260831** while the calendar month counts them in September:
`1,840 + 56 = 1,896`. Verified directly, and again at a re-read twenty minutes
later: `1,848 + 56 = 1,904`.

### The base period excludes the days NFL is played — state this first

**The five full days above are Tuesday to Saturday. There are zero Sundays and
zero Mondays in the base.** The only Sunday in the record is 20260906, the
partial day, correctly excluded from any mean because it was 7.7 hours old at
the read.

NFL is a **Thursday/Sunday/Monday** product. So the base period omits precisely
the weekday cells the projection is about, and no amount of care with the
trailing mean repairs that. This is the single largest weakness in §2 and it is
why §2 does not carry the verdict.

### Largest contributors (CLAUDE.md: a pooled number is not a finding until the parts agree)

- **By sport:** MLB **1,116 of 1,840 = 60.7%**; NCAAF 724 = 39.3%.
- **By day:** 20260905 (NCAAF Saturday) **496 of 1,840 = 27.0%**.

### The trigger column pools mechanisms, so use the sweep log instead

`backend/runner.py:2420` stamps the trigger only when it is `MANUAL` or
`ATTENTION`:

```python
stamp = firing.trigger if firing.trigger in (MANUAL, ATTENTION) else None
```

Everything else — `SCHEDULED`, `REFRESH`, `BOOTSTRAP`, `DESK`, and unstamped
planner firings — lands as NULL. `backend/odds/timing.py:346-355` says so of
`DESK` in as many words: *"Stamped NULL in `api_credits` like every planner
firing."* **`api_credits` cannot separate the kickoff-window branch from the
hourly floor by construction**, and an earlier draft of this document claimed it
could.

`odds_sweep_log.detail` can. September's 476 served sweeps:

| mechanism | detail phrase | n | share |
|---|---|---:|---:|
| kickoff window | `N game(s) from HH:MMZ, sweeping 75-15 min before first kickoff` | 319 | **67.0%** |
| hourly floor | `nobody is looking; the hourly floor keeps the slate from going a whole day stale` | 107 | 22.5% |
| desk open | `someone has the desk open; re-buying so the slate is priced while it is being read` | 50 | 10.5% |

(319 + 107 + 50 = 476, matching the September `api_credits` row count exactly.)

**So the kickoff-window branch really is the dominant mechanism at 67%** — now
measured rather than inferred from a NULL pool — and it is capped by nothing
except the 700 daily total.

### Attention: attribution versus incrementality

Two different questions, and only one of them has a clean answer.

- **As attribution**, the 9.8% attention-tagged share is a **lower bound**, and
  worse than a naive caveat suggests: `DESK` fall-throughs are NULL too. The
  sweep log quantifies the gap — 50 desk-open served sweeps against 45
  attention-tagged calls, so the tag misses about **one in ten**.
- **The statement that needs no assumption about the tag** is sitting in the
  table above: **the highest attention-tagged day in September is 112 against a
  300-credit slice.** `ODDS_ATTENTION_DAILY_CREDITS` never bound on this
  population. Whatever the tag mis-attributes, the slice cannot have been the
  binding constraint, because it was never reached.

### The trend check, which I owed and which comes back reassuring

The base is monotone increasing — 196, 328, 348, 356, 496 — and OLS on it gives
a slope of **+62.8/day**, predicting 533 for the next day. Carrying a flat mean
(344.8) forward from a rising series is the estimator that understates, so the
check matters.

**It is weekly seasonality, not a secular rise.** The base runs Tuesday to
Saturday and climbs into the NCAAF Saturday peak; it is one cycle of a weekly
shape, not five draws from a trending process. The falsifier is the next day:
20260906 (Sunday) ran 116 credits in 7.7 hours, which pro-rates to **~362/day**
— near the flat mean of 344.8 and nowhere near the trend's 533. The trend is an
artifact of where the window was cut.

### The NFL Sunday projection — this is a projection, and it is the weakest thing here

**`americanfootball_nfl` has never been swept: 0 rows in `api_credits`, 0 rows
in `odds_sweep_log`.** Nothing about NFL load has been measured.

Measured ceiling, which *is* solid: **no sport ever exceeds 6 calls in an hour**
anywhere in the record — the 10-minute refresh interval, hit exactly. So a sport
is bounded at 24 credits/hour, **576/day at 24h saturation**.

The analog is NCAAF Saturday 20260905: **74 calls / 296 credits**, spanning
23.0h, at the 6/hour ceiling in six of them. An NFL Sunday is *more* clustered
(three kickoff blocks near 17:00Z, 20:05–20:25Z and 00:20Z, rather than a
continuous noon-to-midnight slate), so window-hours should be comparable or
fewer — call it ~12 near-continuous hours:

```
NFL Sunday, projected   ~12h x 6 calls x 4 credits  ~=  288      (hard ceiling 576)
MLB, observed range                                     200-240
NCAAF Sunday floor                                       50-96
                                                        -------
projected peak budget day                               540-620   vs cap 700
```

### Cold start is unmodelled, and 09-09 is exactly what triggers it

The model above is a **steady-cadence model for an established sport**. NFL on
2026-09-09 is a brand-new sport key on this instance, and
`backend/runner.py:3221-3227` documents a path built for that case:

> *"`decide_sweeps` has a **second** bootstrap path — a sport with no stored
> fixtures at all — which is also gated on this flag and stamps
> `trigger=BOOTSTRAP`, and `attention_credits_spent_today` counts only
> `ATTENTION`. That path is bounded by (1) and (2) above and by the daily
> budget, not by the slice."*

Two properties matter: it is **not** bounded by the attention slice, and a
failing sweep never enters `last_sweeps`, so it retries **once per heartbeat**
(~60s) until one succeeds. The first NFL day therefore carries a spend term this
document does not model. It is bounded by the daily cap — so the §0 verdict
still holds — but the 540–620 peak estimate does not account for it and could be
low on 09-09 specifically.

### The risk that is actually open: four concurrent sports

A day carrying NFL + MLB + NCAAF + WNBA projects to roughly **770, above the 700
cap**. The record has never held more than **three** concurrent sports
(20260825–20260829), so this is extrapolation past anything observed.

**I am not offering "higher than any day ever recorded" as reassurance, and an
earlier draft did.** The historical maxima — 564 on 20260824 under the retired
fixed desk window, 508 under the current design — were both set at two or three
concurrent sports. Sport count is what drives spend. A bound established at
three sports does not bound a four-sport day, and quoting it beside a 770
four-sport projection was self-contradicting.

Offsetting, and genuinely: **MLB's regular season ends 2026-09-27**, removing
the largest single contributor (60.7%) as NFL ramps.

## 3. Is `spreads` buying anything at all?

**Yes. A consumer exists, is production-wired, and was running at the moment of
the read.** The "drop spreads and halve the bill for free" lever is closed.

```
fair_prices by market
  h2h                  n=4,001,628   last=2026-09-06T17:44:34Z
  spreads              n=3,558,522   last=2026-09-06T17:44:34Z
  batter_hits          n=   25,914   last=2026-08-16T19:42:49Z
  ...
```

3.56M spread fair prices, the most recent computed within a minute of the read.

| step | file:line | what happens |
|---|---|---|
| parse | `backend/odds/client.py:567` | `if market_key not in PRICEABLE_MARKETS` — an allowlist that **includes** `spreads` (`client.py:95`, `:181`) |
| store | `backend/odds/client.py:659` | `INSERT INTO odds_snapshots (... market ... outcome_point ...)` |
| group | `backend/runner.py:791` | `spread_quotes_for_event`: `WHERE ... market = 'spreads'`, two-sided and `pointA == -pointB` |
| devig | `backend/runner.py:1212` | `consensus_devig(...)` inside `_price_spread_event` (`runner.py:1124`) |
| persist | `backend/runner.py:1219-1226` | `write_fair_price(..., market="spreads", outcome_points=...)` |
| caller | `backend/runner.py:2018-2032` | `if event.market_type == MARKET_TYPE_SPREAD: _price_spread_event(...)` |
| read back | `backend/parlays.py:422` | `_LADDER_SQL`: `WHERE f.market IN ('h2h', 'spreads', ...)` |
| leg build | `backend/parlays.py:626-657` | `elif market == "spreads":` — matches the fair row's point to a Kalshi spread subtitle |
| card | `backend/core/ladder.py:131`, `:490` | `TEAM_MARKETS_ONLY = frozenset({"h2h", "spreads"})`; `prefer_spreads=True` |
| screen | `/api/parlays` → `frontend/src/components/ParlayCards.tsx` | rendered; also pushed to Discord |

**The premise that motivated the question is a stale comment, and the file says
so itself.** `fly.live.toml:434-446` contains *"Nor could they be used if
something wanted to... KXNFLSPREAD (25 sides) ... rejected on every pass."* That
is retained 2026-08-16 history, overturned eighteen lines above it at
`fly.live.toml:416`: **"CORRECTED 2026-08-23 (ADR 0070): spreads are back,
deliberately."**

The 2-sides filter (`backend/match/linker.py:342-346`) still exists but no
longer applies to spread events: `backend/runner.py:1328-1335` splits them out
and routes them to `link_prop_event(..., method=SPREAD_LINK_METHOD)`, which
inherits the game's link by fixture segment. `totals` remains correctly excluded
at both ends; the 41,292 `totals` rows in `odds_snapshots` are dead history,
last written 2026-08-16.

**No configuration change was made.**

## 4. Reproducing this

`scripts/inspect_live_db.py credits-month | credits-tail | sweep-log` on the
deployed copy, plus read-only ad-hoc SQL against
`file:/data/cockpit.db?mode=ro`. **No inspector subcommand was added** — that
file is being split in a parallel lane, and the four query specs from this work
were handed to it rather than committed here.

**A warning about `credits-month`, which nearly produced a wrong answer.** It
reports `MIN`/`MAX` of `used_reported` over the calendar month. Across a meter
reset those aggregates straddle the discontinuity: September's `max_used` reads
**5,016**, which is August's final total and describes no live state at all. The
same trap makes the free tier look like 524. Always locate the reset before
reading the extremes.

```sql
-- per budget day (10:00Z) x trigger
SELECT strftime('%Y%m%d', (called_ms - 36000000)/1000, 'unixepoch') AS bd,
       COALESCE(trigger,'(null)') AS trg, COUNT(*) n, SUM(cost) cost
FROM api_credits GROUP BY bd, trg ORDER BY bd, trg;

-- per budget day x sport
SELECT strftime('%Y%m%d', (called_ms - 36000000)/1000, 'unixepoch') AS bd,
       COALESCE(sport_key,'(none)') AS sk, COUNT(*) n, SUM(cost) cost
FROM api_credits GROUP BY bd, sk ORDER BY bd, sk;

-- meter resets: any row whose used_reported fell below its predecessor.
-- Rows sharing a timestamp are concurrent in-flight responses arriving out of
-- order, not resets -- require the drop to exceed the row's own cost.
SELECT called_ms, used_reported, remaining_reported FROM api_credits
WHERE used_reported IS NOT NULL ORDER BY called_ms;

-- cadence ceiling: calls per hour per sport (never exceeds 6)
SELECT strftime('%Y-%m-%dT%H', called_ms/1000, 'unixepoch') AS h,
       sport_key, COUNT(*) n
FROM api_credits GROUP BY h, sport_key ORDER BY n DESC;

-- mechanism split, which api_credits.trigger cannot give
SELECT detail, COUNT(*) n FROM odds_sweep_log
WHERE outcome='served' AND pass_ms >= 1788220800000
GROUP BY detail ORDER BY n DESC;

-- is a bought market key actually consumed at runtime?
SELECT market, COUNT(*), MAX(computed_ms) FROM fair_prices GROUP BY market;

-- the 1,840 / 1,896 reconciliation
SELECT COUNT(*), SUM(cost) FROM api_credits
WHERE called_ms >= 1788220800000 AND called_ms < 1788256800000;  -- expect 14 / 56
```

---

## What this does not establish

- **Anything measured about NFL load.** Zero NFL rows exist in either table. The
  288-credit Sunday is an inference from an NCAAF Saturday plus an assumed count
  of open window-hours, on a base period containing **no Sundays and no
  Mondays** — the very weekdays NFL is played. The *ceiling* (576/sport/day) is
  arithmetic and holds; the point estimate is not evidence.
- **Cold-start spend.** The `BOOTSTRAP` path (`backend/runner.py:3221-3227`) is
  unmodelled, is not bounded by the attention slice, and retries per heartbeat
  while sweeps fail. 2026-09-09 is exactly the condition that triggers it.
- **Behaviour at four or more concurrent sports.** The record's maximum is
  three. The ~770 figure is extrapolation, and it is the live question this
  document does **not** answer.
- **That the billing period is a calendar month rather than an anniversary
  landing on a 1st.** One roll exists in the record (`api_credits` begins
  2026-08-07). The purchase-anniversary rule is refuted; a coincidental one is
  not, and is unfalsifiable in practice. It also does not matter — see §1.
- **The true attention share.** The tag is a lower bound and misses roughly one
  desk-open sweep in ten. What survives is the slice's own non-binding: 112 max
  against 300.
- **That spread rungs are worth their credits.** Only that they are computed,
  stored and rendered. ADR 0038 governs the value question.
- **Completeness of `api_credits`.** It counts rows the recorder wrote; an
  unrecorded call is invisible to it. The server's `used_reported` is the
  independent check, and it agrees to one call.

---

## Addendum, 2026-09-06 19:03Z — the spreads finding re-taken on the committed instrument

The audit of this document's first draft raised, as defect 10, that none of its
readings were reproducible: the commit added one markdown file and no
instrument, so a mistake in any query was undiscoverable. That is now closed
for the reading it mattered most for.

`fair-prices-by-market` shipped in the inspector split the same day and was run
against live from the deployed image, after `c9739cc7` was on the box:

    flyctl ssh console -a kalshi-cockpit \
      -C "python /app/scripts/inspect_live_db.py fair-prices-by-market"

    B. CONSUMED -- fair_prices by market
    market              rows_n     links  first_iso                    last_iso
    h2h                 4,021,226    577  2026-08-07T19:33:27Z         2026-09-06T19:03:37Z
    spreads             3,578,118    314  2026-08-24T03:30:28Z         2026-09-06T19:03:37Z
    batter_hits            25,914     17  2026-08-15T19:41:53Z         2026-08-16T19:42:49Z
    ... 4 further prop markets, all last computed 2026-08-16

**The `spreads` conclusion holds and is now stronger in three ways than when
this document first made it.** It was taken with a different tool, by a
different reader, from the deployed image rather than an ad-hoc SQL session;
the count had grown from 3,558,522 to 3,578,118 in the interval, which is the
consumption continuing rather than a static table; and `last_iso` is the same
instant as `h2h`'s, so spreads is devigged on the same pass as the market
nobody doubts.

**`first_iso` is the corroboration worth keeping.** The earliest `spreads` row
is 2026-08-24T03:30Z. ADR 0070 re-enabled spreads on 2026-08-23. The table
starts when the decision says it should, which is not something an ad-hoc
`COUNT(*)` could have shown.

**And the instrument found the case it was written for, in its first live
run.** Section A reports `totals` bought -- 41,292 rows across 23 books --
with `last_ms` of 2026-08-16T22:59Z. Section B has no `totals` row at all. A
market present in A and absent from B is an input bought and read by nothing,
which is precisely what `fly.live.toml` claims of `totals` (*"`totals` stay
off: no consumer"*) and precisely what the same file wrongly claimed of
`spreads` in the retained 2026-08-16 paragraph this document had to overturn.
The check that would have settled that paragraph in thirty seconds did not
exist until today.

**What the addendum does not establish.** Reachability is still the weakest of
the four claims the subcommand's own docstring separates: a `fair_prices` row
means a fair value was computed, not that it reached a recommendation, survived
suppression, or was any good. Nothing here says buying `spreads` is *worth* 2
credits a sweep -- only that the input is consumed, which is what closes the
"drop it for free" lever and nothing more.

**One reading trap, recorded because it cost a wrong conclusion for ten
minutes.** The first run of this command was piped through `head`, which cut
the output between section A and section B's data rows. Section B rendered its
title and column header and nothing else, and was briefly read as "`fair_prices`
is empty on live" -- against a table holding 7,680,002 rows. A truncated
section looks exactly like an empty one, because the header prints before the
rows do. Read the trailing `N rows` line: section A's was present, section B's
was not, and that was the tell.
