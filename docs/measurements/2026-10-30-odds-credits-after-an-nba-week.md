# Odds credits after an NBA week, and what college basketball adds — 2026-10-30

Ticket #361 (Joe's (B) to #359, 2026-10-10). Read by main, session 105.

**What this establishes:** what the odds feed actually spent per sport per budget
day from 10-11 to 10-29, whether the 700/day cap or the 18,000/month ceiling bound
on any day, and a projection for November with men's college basketball in scope.
**What it does not establish:** the cost of a college-basketball day. No NCAAB
call has been made, so that term is an *estimate* with a stated range and two
independent derivations, not a reading. It does not establish anything about
props (scheduled prop buying is off, `ODDS_BUY_PROPS_ON_SCHEDULE = "false"`),
and nothing about on-demand alternate lines beyond the cap they sit inside.

## Instruments (all committed, all `cost=CHEAP`, read 2026-10-30 ~14:30Z)

    inspect_live_db.py credits-by-sport --since 20261011   103 rows, 20 budget days
    inspect_live_db.py credits-month                       October to date
    inspect_live_db.py credits-reset                       billing-period rolls
    inspect_live_db.py sweep-log -n 3                      outcomes, all time
    inspect_live_db.py credits-day --date 20261024         the busiest day's decisions
    The Odds API /v4/sports, /v4/sports/{key}/events       x-requests-last: 0 on every call
    Kalshi /trade-api/v2/events?series_ticker=KXNCAAMBGAME public, unauthenticated

## 1. Day totals (budget day starts 10:00Z)

    day        cost  largest sport           its cost
    20261011   327   americanfootball_nfl    168
    20261012   228   icehockey_nhl            90
    20261013   284   icehockey_nhl           138
    20261014   213   baseball_mlb             72
    20261015   291   icehockey_nhl            90
    20261016   291   baseball_mlb             93
    20261017   483   americanfootball_ncaaf  204   Saturday
    20261018   312   americanfootball_nfl    123   Sunday
    20261019   438   icehockey_nhl           111
    20261020   279   icehockey_nhl           114   NBA regular season opens
    20261021   264   basketball_nba          102
    20261022   303   icehockey_nhl           102
    20261023   390   americanfootball_ncaaf  111
    20261024   546   americanfootball_ncaaf  174   Saturday -- busiest day in the window
    20261025   390   icehockey_nhl           129   Sunday
    20261026   339   basketball_nba           99
    20261027   309   icehockey_nhl           108
    20261028   345   basketball_nba          111
    20261029   291   icehockey_nhl            84
    (20261030  33 at 14:08Z -- partial, excluded)

n = 19 complete days. **Max 546, against a cap of 700. The cap never bound.**
On the busiest day the largest sport was 174 of 546 (32%), so that day is
not one sport's spike. The largest share in the window is NFL on Sunday 10-11
(168 of 327, 51%), a day well under the cap.

**#359's estimate was wrong by about 170, in the safe direction** (one
post-NBA Saturday, n = 1). It put the busiest Saturday at 706–726. The measured
Saturday after NBA opened was 546. NBA cost 75–123 a day across the ten days
10-20..10-29 (n = 10, mean 99; 10-19's 36 and 10-18's 6 are preseason), below
#359's 115–135 on 8 of the 10 days. The Saturday also
carried less NFL than the estimate assumed (30, against 102–168 on Sundays).

## 2. Refusals

`odds_sweep_log` holds **2 `refused` rows in its whole life, both 2026-08-15**,
and 3 `failed`, the latest 2026-10-17 15:00Z. On 10-24 the passes recorded 182
`served` and 2,264 `skipped`. Every skip names a reason. The largest class
(~1,345 rows, each unique because it carries times) is "<sport>'s window is
open and its odds are N min old; next refresh at …". The repeated ones are
"next slot is …" and the props notes. None names the budget, and only 6 of the
day's 182 calls were attention-triggered (18 credits), so the attention slice
did not bind either.

**What sweep-log cannot show.** A `refused` row is written only when the whole
day is spent (`backend/odds/timing.py:2044`). A sport refused for cost on a
pass where another sport fired reaches the log stream, not `odds_sweep_log`
(`backend/runner.py:2804–2879`). The no-refusal claim therefore rests on
arithmetic. Refusing a sport needs fewer than 3 credits left after the other
sports' window holds (at most 21 each), and on 10-24 at least 154 were always
left. Joe's (B) on
#359 says the cap moves only on a measured day that needs it, and no day has
needed it.

## 3. The month

`credits-month`: **9,831 credits used 10-01..10-30 14:08Z**. `remaining_reported`
fell from 19,997 to 10,170, and `credits-reset` shows the period rolled at
2026-10-01T00:05Z (used 10,554 → 3), so this window is one billing period. At
the 10-20..10-29 rate (3,456 over 10 days, 346/day) October closes at about
**10,300** (10,200–10,500: 9,831 plus ~34 h at 346/day, one of them a
Saturday) of the plan's 20,000 and our own 18,000 ceiling. #359's partner note
projected 12–13K.

## 4. What leaves the slate in November

- **MLB: gone.** The Odds API lists 0 `baseball_mlb` events, and the last MLB
  call was 10-28. It cost 29/day on average over 10-20..10-29 (291 in 10 days).
- **WNBA: one fixture left.** The API lists exactly one `basketball_wnba` event,
  `2026-11-01T00:00:00Z`, home team Golden State. WNBA cost 24/day on average over
  10-20..10-29 (240 in 10 days), and that spend did **not** come from the
  11-01 fixture. The floor buys only a sport with a fixture inside 12 hours
  (`DESK_FLOOR_HORIZON_MS`, `backend/odds/timing.py:507`), so that fixture
  reaches the floor only from 10-31 12:00Z. Attention bought just 6 calls of
  all sports on 10-24. Which fixtures drove the spend is not established here.
  If 11-01 is the last game, WNBA stops after it; a further game would bill
  legitimately.

November baseline without them: 346 − 29 − 24 ≈ **293/day** (NFL, NCAAF, NBA,
NHL).

## 5. College basketball — an estimate, two ways

**Kalshi has listed it.** `KXNCAAMBGAME`, 155 open events, every one carrying
`product_metadata.competition = "College Basketball (M)"`: 1 on 11-01, 133 on
11-02, 21 on 11-03, all `exchange_index: 3`. The Odds API's `basketball_ncaab`
is `active: true` but lists **7** fixtures (2 on 11-01, 5 on 11-02). The
sportsbooks post lines nearer tip-off, and the desk can only buy what the feed
lists.

**Cost scales with the tip-off span, not the game count — and the two-hour
rule does not cap it.** `MIN_SLOT_SEPARATION_MS` (`backend/odds/timing.py:208`)
is applied only among the slots chosen on one pass (`timing.py:951`). Once a
slot's `fire_until` passes, it drops out, and the next cluster inside two hours
becomes eligible and ranks first because it is already due (`timing.py:944`).
So windows chain into a continuous 10-minute refresh. The evidence is 123
minutes for one MLB cluster on 08-16 (`fly.live.toml`) and about 1,070 NCAAF
"window is open" skips on 10-24. A slate tipping every half hour from 16:00Z
to 04:00Z can hold the 10-minute cadence from 14:45Z to 03:45Z: 13 h × 6 × 3
≈ 234, plus about 30 of hourly floor outside it, so **≈ 265/day**. The hard
per-sport maximum is 24 × 6 × 3 = 432. This first draft derived a "≈ 220
ceiling" from the two-hour rule; the audit refuted it.

**Analog from the record:** NCAAF is the closest shape we have (dozens of
games, tip-offs spread across one day). Its Saturdays cost **204** (10-17) and
**174** (10-24). #359's estimate for NCAAB was 150–250.

Range used below: **150–270/day** on a full slate. Early-November weekdays will
mostly sit lower.

## 6. The day's sum, redone

    day                 baseline (measured, minus MLB/WNBA)   + NCAAB    total    cap
    Mon 11-02 (opener)  10-26: 339 - 51 - 51 = 237             150-270   387-507  700
    Sat 11-07 (worst)   10-24: 546 - 54 - 36 = 456             150-270   606-726  700

**Monday 11-02 fits, with at least 193 to spare.** **A November Saturday can
cross the cap at the top of the range.** It reaches 726 only if NCAAB holds the
10-minute cadence all day on the heaviest Saturday we have recorded. At the
NCAAF analog (about 204) it is 660. Trigger for action: a `refused` row in
`sweep-log`, a day total above about 600, or any `credits-day` reason
containing "remain". With five sports in scope, a pass can refuse one sport for
cost once spend passes 700 - 4x21 - 3 = about 613. On a pass where another
sport fired, that refusal is not written to `odds_sweep_log`.

## 7. November, and the 20,000 warning

(293 + 150..270) x 30 = **13,300-16,900**. That is under our 18,000 ceiling
and the plan's 20,000. **No date in November is projected to cross 20,000, so
the pre-approved $59 plan is not needed for November.** The feed cannot reach
20,000 on its own, because every call path goes through `OddsClient` and the
loop's `CreditBudget`, including on-demand taps and alternate lines.
`refusal_reason` checks the calendar-month total of all `api_credits` rows
against 18,000 (`backend/odds/budget.py:257`). The vendor's October count
(9,830) matched ours (9,831), so nothing else spent on this key. The caveat: a
second user of the same key (demo, a local script) would count against the
vendor's 20,000 but not against our 18,000.

## Decision recorded

- `ODDS_MONTHLY_CREDIT_BUDGET = "18000"` is **left as it is**. Nothing
  projects past it.
- `ODDS_DAILY_CREDIT_BUDGET` is **raised from 700 to 800**. Joe chose this on
  2026-10-30, mid-session, over waiting for a measured Saturday. The raise
  costs nothing unless a day spends past 700, and the 18,000 monthly ceiling
  still bounds the month. It removes the one projected case where a
  November Saturday's college-basketball load would take every sport dark
  until 10:00Z.
- `tests/test_desk_follows_attention.py` asserted that the day could not fund
  the floor, the attention slice and the tap reserve in full (762 > 700). That
  assertion now reads `<=` at 800. It was mutation-verified red at 700.
- College basketball (#360) goes into scope. The opener fits.
- Re-read `credits-by-sport` and `credits-day` on 11-03 (the opener) and 11-08
  (the first NCAAB Saturday).
