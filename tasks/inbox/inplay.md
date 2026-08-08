# Lane: in-play research

Answers `tasks/NEXT.md` section 3, **"Is in-play betting viable?"**. Four
questions, answered cheapest-first. Question 1 is a yes and questions 2 and 4
are each independently decisive noes, so question 3 is answered as design work
rather than as a blocker.

**Verdict: out of scope until the odds budget changes — and the budget is the
smaller of the two obstacles.** Draft ADR: `docs/adr/0006-in-play-scope.md`.

Everything below was measured with read-only `GET`s against the live Kalshi API
on 2026-08-08 between 06:04Z and 06:08Z, plus web research on The Odds API. **No
POST of any kind was issued, and The Odds API was not called** — its budget is
shared with the live instance.

---

## 1. Does Kalshi keep the game market open in-play, or list separate period markets?

**Both.** Joseph is right, and it is more than he claimed.

### The game market stays open through the game

Four `KXMLBGAME` markets from the night of 2026-08-07, read back off
`/events?status=settled` with nested markets:

| ticker | true start | `close_time` | open for |
|---|---|---|---|
| `KXMLBGAME-26AUG072215DETSF-DET` | 02:15Z | 04:44:28Z | 2h29m |
| `KXMLBGAME-26AUG072145TBSEA-TB` | 01:45Z | 04:24:28Z | 2h39m |
| `KXMLBGAME-26AUG072140LADAZ-LAD` | 01:40Z | 04:27:39Z | 2h48m |
| `KXMLBGAME-26AUG072140HOUSD-HOU` | 01:40Z | 04:44:29Z | 3h04m |

Every one carries `can_close_early: true` and
`early_close_condition: "This market will close and expire after a winner is
declared."` The market does not close at first pitch; it closes when the game
ends, and the ragged close times are the games themselves running long or short.

The same two fields are in `tests/fixtures/market_single.json`, captured
2026-08-08 and already in the repo. (Its `close_time` also sits two days past
kickoff, but that one is the 48-hour postponement allowance spelled out in its
own `rules_secondary`, not an in-play statement — the tell in that fixture is
`early_close_condition`, not the date.)

Confirmed on the tape rather than from the fields: **20 of 20 games measured
(14 MLB, 6 WNBA) had a two-sided quote in every single minute after the true
start.** Not one minute of the twenty games went unquoted.

### Separate period markets exist too, and settle mid-game

| ticker | closes | parent game expiration |
|---|---|---|
| `KXWNBA1HWINNER-26AUG07PHXCONN-CONN` | 01:09:49Z | 02:30Z |
| `KXWNBA2HWINNER-26AUG07PHXCONN-CONN` | 01:49:45Z | 02:30Z |
| `KXMLBF5-26AUG072215DETSF-DET` | 03:34:44Z | 05:15Z |

`tests/fixtures/sports_coverage.json` — already in the repo, captured
2026-08-06 — lists **225 sports series, of which 46 are period or partial-game
markets** (35 of them carry `1H` in the ticker, mostly soccer):
`KXWNBA1HWINNER`, `KXWNBA1HTOTAL`, `KXWNBA1HSPREAD`, `KXWNBA2HWINNER`,
`KXWNBA2HSPREAD`, `KXWNBA2HTOTAL`, `KXWNBAOT`, `KXMLBF3`, `KXMLBF5`, `KXMLBF7`,
`KXMLBF5TOTAL`, `KXMLBF5SPREAD`, `KXMLBRFI`, `KXBRASILEIRO1H`,
`KXLEAGUESCUP1HSPREAD`, and so on. This fixture answered question 1's second
half for free and was never read for it. (`lessons.md`, "a captured fixture that
no test loads is decoration" — this one *is* loaded by tests, but was never
asked this question.)

### One correction that belongs in `lessons.md` regardless of the verdict

**The "3-hour offset" is not a timezone bug and it is not a constant.**
`occurrence_datetime` is not the start time. On `KXMLBGAME`, `KXWNBAGAME`,
`KXWNBA1HWINNER` and `KXWNBA2HWINNER` it is exactly equal to
`expected_expiration_time` — the expected *end*. MLB games average three hours,
which is the entire reason `−3h` reproduces the start; validated against the
time encoded in the ticker itself (`...072215...` = 22:15 ET = 02:15Z, and
`occ − 3h` = 02:15Z to the minute).

It does not generalise. `KXMLBF5`'s `occurrence_datetime` is 07:15Z against an
`expected_expiration_time` of 05:15Z — two hours beyond it, not equal to it.
Applying `−3h` to an F5 ticker yields a "true start" of 04:15Z, forty-one
minutes *after* the market had already closed. My first attempt at the phase
split for `KXMLBF5` reported "0 in-play minutes" for exactly this reason, and I
have not reported those numbers because they are an artifact of the wrong clock.

`match/linker.py` encodes `−3h`. It is right for MLB and WNBA game markets by
coincidence of game length, and it would be silently wrong for any period
series. **This is not established beyond the five series I checked** — I did not
determine why F5 differs, only that it does.

---

## 2. Can the odds side follow? — **No, at any price this project would pay**

### How the meter works

The Odds API charges `markets × regions` **per call, per sport**, not per game:
one call returns every game for that sport, live and upcoming. So the credit
driver is `hours of live coverage × calls/hour × markets × regions × leagues`,
and adding games to a slate is free while adding *time* is not.

The current config (`.env.example`: `ODDS_MARKETS=h2h,spreads,totals`,
`ODDS_REGIONS=us,eu`) is 6 credits per call, as `backend/odds/budget.py` already
documents.

### The refresh rate you would actually need is set by the provider, not by us

Checked 2026-08-08 on <https://the-odds-api.com/sports-odds-data/update-intervals.html>:

| Market type | Pre-match | In-play |
|---|---|---|
| Featured (h2h, spreads, totals) | 60s | **40s** |
| Additional (props, alternates, period markets) | 60s | 60s |
| Betting exchanges | 20s | 10s |

Nothing on that page ties the interval to the subscription tier, and no tier
advertises faster updates. **40 seconds is a floor you cannot buy your way
under.** Polling faster than 90 calls/hour therefore spends credits on data that
has not changed.

### The arithmetic

One league, thirteen hours of daily live coverage in season, at the provider's
own cadence:

    13h × 90 calls/h × 6 credits = 7,020 credits/day = 210,600/month

Against `ODDS_DAILY_CREDIT_BUDGET=16`, that is **439× the current daily
allowance** — and at 540 credits an hour it burns the free tier's *entire
500-credit month* in **56 minutes**.

Stripped to the cheapest configuration that could still devig a moneyline
(h2h only, `us` only, 1 credit per call): 1,170/day, 35,100/month. Still 70×
the free tier's month. Four leagues at the current config: ~842,000/month.

### Priced against the published tiers

From <https://the-odds-api.com/#get-access>, checked 2026-08-08:

| Plan | Credits/month | Price | What it buys in-play |
|---|---|---|---|
| Starter | 500 | free | 5.5 hours of one league, h2h/1-region, once — then the month is gone |
| 20K | 20,000 | $30/mo | 7.4h/day of one league, h2h only, one region. No spreads, no totals. |
| 100K | 100,000 | $59/mo | one league at the current 3×2 config for 6.2h/day, or three leagues at h2h/1-region |
| 5M | 5,000,000 | $119/mo | four leagues, current config, 13h/day, with ~6× headroom |
| 15M | 15,000,000 | $249/mo | the above plus props and alternates |

**The honest number is $119/month** for the current market and region set across
a real slate. $59/month buys a version of in-play with one league and no
spreads or totals.

### Why $119/month is not a small number here

`.env` has `BANKROLL_DOLLARS=1000`, `MAX_POSITION_DOLLARS=100`,
`MAX_EXPOSURE_DOLLARS=400`.

The theoretical headroom this tool exists to hunt is **0.38 percentage points**
(`CLAUDE.md`). To earn back $119/month on that headroom requires

    $119 ÷ 0.0038 = $31,316 of notional per month

— 31× the bankroll turned over every month, or 313 max-size positions, ~10 a
day, **every one of them capturing the entire theoretical headroom with zero
slippage.** Section 4 measures the slippage. It is larger than the headroom.

So the data bill is not a rounding error against a $1,000 bankroll; it is the
dominant cost, and it has to be paid before the first cent of edge.

**What this does not establish:** it does not establish that The Odds API is the
only supplier. A direct book feed or a Sportradar-class provider has different
economics and different latency. It establishes that *this* supply chain, at
*this* bankroll, does not pay for itself.

---

## 3. What replaces the closing line?

Nothing does, cleanly. Every candidate is a different statistic, and saying so
is the finding.

### What in-play breaks

The CLV machinery anchors on **one instant per game**, and in-play has no such
instant:

- `backend/store/schema.sql` — `closing_lines` is `UNIQUE (ticker,
  horizon_hours)`. Thirty in-play recommendations on one ticker want thirty
  different references; the table can hold one, and `store_closing_line` uses
  `ON CONFLICT DO UPDATE`, so the last write wins **silently**.
- `backend/scoring.py:markets_awaiting_scoring` selects one `commence_ms` per
  odds event and `fetch_closing_line` reads a 15-minute candlestick window
  ending at `true_commence − horizon`. Both are hard-wired to kickoff.
- `backend/analysis/clv.py:score_recommendations` refuses any row where
  `created_ms > closing_observed_ms`. In-play, *every* row is created after the
  kickoff-anchored line, so at present in-play rows would not merely score
  badly — they would all land in `skipped_entry_after_close`. This is why the
  runner's drop is a drop and not a suppression: the rows can never become
  evidence at any horizon.
- `backend/analysis/clv.py:horizons_agree` compares 1h against 6h and calls a
  moving result "convergence, not edge". In-play the price is *supposed* to
  converge continuously — that is what a live market does — so the guard that
  catches contamination pre-game would fire constantly in-play and mean nothing.

### The three candidate substitutes, and why none is the same statistic

| Candidate | What it actually measures | Why it is not CLV |
|---|---|---|
| **Settlement price (0 or 100)** | realised P&L on one bet | This is win-rate measurement, not CLV. `clv.py`'s own docstring says CLV was chosen precisely to get an answer in 200–300 observations instead of ~1,000. Against settlement, the variance goes back up and `LIVE_GATE_MIN_SCORED_RECOMMENDATIONS=300` is calibrated for the wrong statistic. |
| **End-of-period price** | the close of a *period* market | Only defined for `KX*1H*`/`KXMLBF5`-style series, not for the game market. A bet in the third quarter has no end-of-period ahead of it that is not also settlement. |
| **Price at entry + Δ** (e.g. +5 min) | short-horizon price prediction | Structurally the closest — "did I get a better price than the market did shortly after" — but it is *the statistic that stale-quote picking optimises*, which `lessons.md` records as measured and refuted at ~400ms. It is also not comparable to the pre-game CLV numbers, so the gate needs two thresholds, not one. |

### The floor, before anything is recorded

Even with a substitute chosen, `backend/gate.py:clustered_clv` pools every
scored row and `POPULATIONS` splits on suppression and size — **not on regime**.
An in-play row and a pre-game row would land in the same `actionable` bucket
carrying two different statistics. That is `lessons.md`, "two populations in one
record, told apart by dispersion", repeated with the guard that caught it last
time removed.

Minimum before a single in-play row is written:

1. a **regime column** on `recommendations` (or a `strategy_config_version` that
   segments on it), so the two populations can never be pooled by accident;
2. `closing_lines` keyed per **recommendation**, not per `(ticker, horizon)`;
3. `gate.py` reporting the two regimes separately, with its own threshold for
   each, and the pooled number suppressed rather than displayed.

Items 1 and 2 are `backend/store/schema.sql`, which is integrator-only. **This
is not work a worker lane can do**, and it should not be started until questions
2 and 4 are answered differently than they are here.

---

## 4. Is the edge plausibly there? — **No, by a factor of 3.5 to 6**

### The check, designed so that "no" is reportable

Compare the **cost of participating** against the **headroom**, using only free
Kalshi candlesticks. Two quantities:

- **(a) extra crossing cost** = in-play half-spread − pre-game half-spread
- **(b) drift over the shortest data age the odds side can achieve** (40s, from
  section 2)

If `(a) + (b) > 0.38c`, the answer is no and no further work is justified. The
check costs no bets, no orders and no odds credits, and it produces a number
either way.

### Measured: 14 MLB games and 6 WNBA games, 1-minute candlesticks

Pre-game window is the final three hours before the true start — the window the
runner actually operates in.

**MLB (`KXMLBGAME`, 14 games, 2026-08-07/08)**

| | pre-game | in-play |
|---|---|---|
| minutes observed | 2,459 | 2,631 |
| minutes with a two-sided quote | 2,459 (100%) | 2,631 (100%) |
| minutes with volume | 2,271 (92.4%) | 2,573 (97.8%) |
| contracts per minute | 891 | **6,863** |
| spread mean / median | 1.00c / 1.00c | 1.50c / 1.00c |
| spread p90 / p99 / max | 1.00c / 1.00c / 1.00c | 1.00c / 3.00c / 100.00c |
| **half-spread (cost to cross), mean** | **0.50c** | **0.75c** |
| \|Δmid\| per minute, mean / median | 0.00c / 0.00c | **1.63c** / 0.50c |
| \|Δmid\| per minute, p90 / p99 | 0.00c / 0.00c | 4.00c / 14.00c |
| minutes moving ≥ 1.0c | 4 (0.2%) | 1,270 (48.5%) |

**WNBA (`KXWNBAGAME`, 6 games, same night)**

| | pre-game | in-play |
|---|---|---|
| minutes observed | 1,024 | 913 |
| minutes with volume | 961 (93.8%) | 895 (98.0%) |
| contracts per minute | 785 | **11,531** |
| spread mean / median | 1.00c / 1.00c | 1.79c / 1.00c |
| spread p90 / p99 / max | 1.00c / 1.00c / 1.00c | 2.00c / 3.00c / 100.00c |
| **half-spread, mean** | **0.50c** | **0.89c** |
| \|Δmid\| per minute, mean / median | 0.01c / 0.00c | **2.31c** / 1.00c |
| minutes moving ≥ 1.0c | 9 (0.9%) | 453 (50.1%) |

The two leagues agree on every line, in the same direction, at similar
magnitude. This is a pooled result whose parts agree.

### The finding that argues against my own verdict, stated first

**In-play is where the money is.** Contracts per minute rise 7.7× (MLB) and
14.7× (WNBA) once the game starts, 98% of in-play minutes trade, and the book is
two-sided in every one of the 3,544 in-play minutes measured. Joseph's instinct
about this product was correct: it is real, it is liquid, and it is bigger than
the pre-game market this tool currently watches. The reason to decline is not
that there is nothing there.

### The arithmetic that decides it

Headroom: **0.38c** on a contract near 50c (0.38 percentage points, `CLAUDE.md`).

**(a) Extra crossing cost.** 0.75c − 0.50c = **0.25c** (MLB); 0.89c − 0.50c =
**0.39c** (WNBA). That is 66% and 103% of the entire headroom, spent before any
view is expressed. Note the median spread is unchanged at 1.00c in both leagues
— the mean rises because the *tail* fattens (p99 goes 1.00c → 3.00c, and the
100.00c max is a blown-out game with no offers on one side). So the extra cost
is not uniform; it is concentrated in exactly the moments the price has just
moved, which is when you would want to trade.

**(b) Drift over the odds side's 40-second floor.** Measured drift is at
1-minute resolution — candlesticks do not go finer, so the 40s figure is
**interpolated, not measured**, and reported as a range under two scaling
assumptions:

| | linear in t | √t |
|---|---|---|
| MLB (1.63c/min) | 1.09c | 1.33c |
| WNBA (2.31c/min) | 1.54c | 1.89c |

**(a) + (b) = 1.34c to 2.28c, against 0.38c of headroom — 3.5× to 6.0× over.**

### The cleanest way to say it

Pre-game, `MAX_ODDS_AGE_S=900` is a sane fifteen-minute tolerance because in
2,459 pre-game minutes the mid moved by ≥1c on **four of them (0.2%)**. In-play,
the mid moves ≥1c on **half of all minutes**. Fifteen minutes of pre-game
staleness costs less than forty seconds of in-play staleness. The existing
design is not conservative-by-luck; it is calibrated to a regime that in-play
does not share.

This is the same shape as `lessons.md`'s stale-quote result. There the edge
lived at ~400ms and a 60–180s detector could not reach it. Here the edge lives
inside 40s and the data supplier cannot deliver faster than that. Different
mechanism, identical conclusion: **the money is on the other side of a latency
gap we do not own.**

### What this does *not* establish

- **Not that no in-play edge exists.** A participant with a sub-second feed
  faces different values of (a) and (b). This establishes that *this tool's data
  supply chain* cannot reach it.
- **Twenty games, two leagues, one night** (2026-08-07/08). One point in the
  season, one weather, one slate.
- **It measures drift in Kalshi's own mid**, not in a devigged sportsbook
  consensus. The claim "a 40s-stale consensus is ~1.1–1.9c wrong" assumes the
  consensus tracks Kalshi. If the books are *slower* than Kalshi in-play — which
  is the likelier direction, since books suspend markets between plays — the
  error is larger, not smaller. The assumption is conservative, but it is an
  assumption and it was not tested (The Odds API was deliberately not called).
- **Nothing about maker.** At the 50.44% maker break-even the headroom is 1.94
  points, which exceeds the measured MLB drift and is comparable to the WNBA
  drift. See below.

### The one door not closed by arithmetic

Maker. 1.94 points of headroom is genuinely more than (a) + (b) for MLB. But a
resting limit order in a market that moves ≥1c half of all minutes is not
earning a spread — it is being adversely selected by whoever moved it, and this
repo has **no cancel path at all** (2026-08-08 handoff: "plain GTC limit, no
`time_in_force`, no cancel path anywhere in the repo"). Quoting in-play without
the ability to pull a quote is a way to lose money at a known rate.

So the maker door is closed by missing infrastructure rather than by
measurement, and it should be recorded as such rather than as "refuted".

---

## For the integrator

- **Files I wrote:** this one and `docs/adr/0006-in-play-scope.md` (proposed).
- **Branch:** `lane/inplay`. Not merged, not pushed.
- **Nothing under `backend/`, `frontend/`, `warehouse/` was modified.** The
  runner's `dropped_game_started` should stay exactly as it is; sections 3 and 4
  are the evidence that it was right, not merely defensible.
- **Outside my lane, needed by anyone who picks this up later:**
  - `tasks/lessons.md` — the `occurrence_datetime` correction in section 1. It
    is a live defect risk in `match/linker.py` for period series and is worth
    recording whether or not in-play is ever built.
  - `backend/store/schema.sql` and `backend/gate.py` — section 3's three
    prerequisites. Integrator-only by ADR 0003.
  - `tasks/NEXT.md` — the section 3 item should be closed against ADR 0006.
- **Shared state touched:** live Kalshi credentials, read-only `GET` only
  (`/events`, `/markets`, `/series/*/markets/*/candlesticks`). No POST. **The
  Odds API was not called and no credits were spent.** `data/` untouched.
