# 2026-11-12: the first college-basketball slates, read (#401)

Owed on 2026-11-03 and 2026-11-08. Read on 2026-11-12, nine days late, so the
opening week is only partly visible. #360 shipped men's college basketball
(`basketball_ncaab`) into scope on a 2026-10-30 capture in which the books
listed 7 of Kalshi's 155 events. This note reads the four things #401 asked
for.

## 1. Odds credits: did the new league fit under the daily cap?

Instrument: `inspect_live_db.py credits-by-sport` (default window, the last
seven days), run on live through `instrument.yml` (run 43320983252,
2026-11-12T22:33Z). The window starts 2026-11-05T22:33Z, so the 11-05 row is
a partial day and **11-02 to 11-04 are not in it.** The 11-12 row is a partial
day too (the read was taken at 22:33Z, and the budget day runs to 10:00Z).

| budget day | calls | credits | sports | largest sport | its credits |
|---|---|---|---|---|---|
| 11-12 (partial) | 107 | 321 | 5 | basketball_ncaab | 78 |
| 11-11 | 170 | 510 | 5 | basketball_ncaab | 237 |
| 11-10 | 136 | 408 | 4 | basketball_ncaab | 132 |
| 11-09 | 138 | 414 | 5 | basketball_ncaab | 141 |
| 11-08 (Sun) | 193 | 579 | 4 | basketball_ncaab | 222 |
| **11-07 (Sat)** | **241** | **723** | 5 | basketball_ncaab | 225 |
| 11-06 | 149 | 447 | 4 | basketball_ncaab | 171 |
| 11-05 (partial) | 76 | 228 | 5 | basketball_ncaab | 78 |

- The daily cap is 800 (`ODDS_DAILY_CREDIT_BUDGET`, since #361). The heaviest
  day read, Saturday 11-07, spent 723: 77 under the cap, and above the ~700
  #401 asked to be flagged. On that day NCAAB was 225, college football 192,
  NHL 162, NBA 120, NFL 24.
- College basketball was the largest sport on seven of the eight days and
  tied for largest on the eighth (11-12, partial: NCAAB 78, NHL 78; the
  instrument names one `top_sport` and does not mark a tie).
- **Refusals: one kind is excluded by arithmetic, the rest are not read.**
  The daily-cap refusal (`budget.refusal_reason`'s third check, and
  `decide_sweeps`' `refused_by_budget`, written to `odds_sweep_log` as
  `refused`) fires only when the budget day's `SUM(api_credits.cost)` plus the
  next call's cost exceeds 800, which is the sum this table prints. Every call
  in the window cost 3 and no complete budget day (11-06 to 11-11) exceeded
  723, so that refusal cannot have fired on those six days. It is not
  excluded on 11-05 (10:00Z to 22:33Z of that budget day is outside the
  window) or on 11-12 (the day had not ended). The 18,000 monthly ceiling
  cannot have bound (November to 11-12 is at most ~10,400 at the daily cap).
  Not read: a refusal on the vendor's `x-requests-remaining`, and any
  `failed`, `no_data` or `skipped` row. `sweep-log` and `credits-day` print
  rows and are laptop reads, and the laptop's `flyctl` login had expired. The
  324-credit attention slice does not refuse a pass; since 2026-08-29 it
  demotes an attended sport to the hourly floor. So #360's Done-when ("no
  `decide_sweeps` refusal in `sweep-log`") is not met by this note, and
  #401 item 1's refusal read was still owed when this section was written; section 1b reads it.
- One Saturday is n = 1. The season's busiest college-basketball Saturdays
  come later, with more games than the 11-07 slate.

## 1b. The refusal read, 2026-11-13 (item 1)

Instrument: `inspect_live_db.py credits-day --date YYYYMMDD` (CHEAP), run
on live from the laptop by path over `flyctl ssh`, one call per budget day
(10:00Z boundary) from 11-02 to 11-12, read 2026-11-13 between 18:21Z and 18:23Z. Every
budget day is complete, including 11-12, which ended 11-13 at 10:00Z.

| budget day | calls | credits | `served` | `skipped` | `failed` | `refused` | `no_data` |
|---|---|---|---|---|---|---|---|
| 11-02 | 250 | **750** | 250 | 2,404 | 0 | 0 | 0 |
| 11-03 | 85 | 255 | 85 | 1,238 | 0 | 0 | 0 |
| 11-04 | 109 | 327 | 109 | 1,220 | 0 | 0 | 0 |
| 11-05 | 135 | 405 | 134 | 1,557 | **1** | 0 | 0 |
| 11-06 | 149 | 447 | 149 | 1,822 | 0 | 0 | 0 |
| 11-07 (Sat) | 241 | 723 | 241 | 2,151 | 0 | 0 | 0 |
| 11-08 (Sun) | 193 | 579 | 193 | 2,114 | 0 | 0 | 0 |
| 11-09 | 138 | 414 | 138 | 1,459 | 0 | 0 | 0 |
| 11-10 | 136 | 408 | 136 | 1,546 | 0 | 0 | 0 |
| 11-11 | 170 | 510 | 170 | 2,108 | 0 | 0 | 0 |
| 11-12 | 195 | 585 | 195 | 1,664 | 0 | 0 | 0 |

- **No `refused` row on any of the eleven days, and no row names the daily, monthly or vendor ceiling.** All three of
  `CreditBudget.refusal_reason`'s ceilings (the vendor's
  `x-requests-remaining`, the monthly cap and the daily cap) are written to
  `odds_sweep_log` as `refused` by `backend/odds/client.py:449-455` and
  `:565-571`, and that outcome has no row on any day. The vendor's ceiling is
  also excluded by its own value: `x-requests-remaining` never fell below
  14,111 (11-12), and it refuses below 3. The monthly ceiling is excluded by
  the ledger: 5,403 credits over 11-02..11-12, against 18,000.
- **Not every refusal writes `refused`.** `decide_sweeps`' cost refusals
  (`refused_for_cost`: hand taps, windows that cannot open, desk refreshes,
  alt lines, the attention slice) are written as `skipped`, and on a pass
  that also fires something they reach no table, only the log line. The
  kickoff loop holds a window's projected tail against `credits_left`, so
  such a refusal can happen below 800. On 11-02, 50 credits remained after
  04:37Z, so it is not excluded there. A tap refused at submit time
  (`ondemand.submit`) writes no `odds_sweep_log` row either.
- **The heaviest day is 11-02, the opener, at 750 of 800**: 50 under the cap,
  and heavier than the 723 Saturday section 1 called the heaviest. Section 1's
  window did not include 11-02. Two of eleven days were above ~700.
- **One `failed` pass**: an NFL call at 2026-11-06T00:00:09Z (budget day
  11-05). Its `api_credits` row carries cost 3 and NULL vendor headers. That
  row is written only after an HTTP response arrives, so the vendor answered
  with an error and no rate-limit headers. The vendor's `x-requests-used` went
  from 2070 to 2073 across this call and the next one, so the vendor appears
  not to have billed it, and the ledger is 3 credits over on 11-05. The status
  code is not in the credits-day output. One call in 1,801; it was
  not looked into further.
- `skipped` rows say why no call was due ("window is open … next refresh
  at", "next slot is…", the props-off notices). Two name a budget: on 11-03
  at 03:50Z (budget day 11-02) an NHL desk refresh "cannot be served: the
  attention slice is 324 credits a day and 324 are spent". That is the
  demotion to the hourly floor section 1 describes, not a refusal of the day.
- #360's Done-when ("no `decide_sweeps` refusal in `sweep-log`") is read
  here as: no `refused` row. The two attention-slice demotions above are
  `decide_sweeps` cost decisions that reach `sweep-log` as `skipped`.
- Cross-check: 11-06 to 11-11 match section 1's table call for call and
  credit for credit. 11-05 and 11-12 differ because section 1 read partial
  days.

## 2. Team names on the slate the books had posted (the 11-12 and 11-13 evenings)

`scripts/capture_team_names.py --league ncaab` on 2026-11-12 (zero odds
credits; `x-requests-last: 0`): 177 Kalshi `KXNCAAMBGAME` events in scope
against 62 Odds API fixtures. The 62 fixtures run 2026-11-12T23:00Z to
11-14T03:00Z on the book clock; Kalshi's 177 run to 11-16. All 62 are
accounted for: 61 linked, and the 62nd is Tennessee St. at Tennessee.

| bucket | with no aliases | with the re-derived file |
|---|---|---|
| linked | 52 | 61 |
| needs an alias (a fixture at this kickoff shares a side) | 10 | 1 |
| not carried (no fixture at this kickoff shares either side) | 18 | 18 |
| no book fixture at this kickoff | 97 | 97 |

- `backend/match/aliases/basketball_ncaab.yaml` gained eight entries, each
  read off this capture: Cal State Bakersfield, Loyola Maryland, Purdue Fort
  Wayne, Southern University, George Washington, Mount St. Mary's, Southeast
  Missouri St. and Louisiana-Monroe. The 2026-10-30 entry (`Miami (FL)`) earned
  its place again (North Alabama at Miami).
- **One pair cannot be fixed with an alias: Tennessee St. at Tennessee.**
  "Tennessee" is a token prefix of both book names. An alias only adds a
  match (`linker._matches`, test 2) and never removes the prefix match
  (test 3), so the pair has no one-to-one assignment and is refused. That is
  the safe failure. Making an override exclusive would change the linker for
  every league.
- In the first run, the 18 not-carried games were counted as `other`. The
  script's bucket did not recognise the linker's current wording for that
  refusal. Fixed in the script.
- `tests/test_ncaab_names_resolve.py` is rewritten on the new capture: the
  nine alias-earned links pinned pair by pair, 61/52 counts, no book fixture
  claimed twice, and every link at the same skew. Removing one alias turns two
  of its tests red.

## 3. Kickoff skew

`commence_skew_ms` (the book's `commence_time` minus Kalshi's
`occurrence_datetime`, `linker.py:443`) on the 61 linked games: **exactly
−3.0 hours on all 61**, i.e. Kalshi's time runs three hours late. That is the known three-hour
offset (`kalshi-api` skill). The linker's tolerance is 4 hours
(`DEFAULT_COMMENCE_TOLERANCE_MS`). Every link sits 1 hour inside it, and none
sits on the edge. On 10-30, 2 of 7 sat on the edge, and this capture does not
reproduce that. No tolerance change is indicated, and none was made.

Within this capture no game was lost to the tolerance: none of the 116
unlinked Kalshi events matches any of the 62 captured fixtures by name at any
offset, and all 97 with no fixture in the window tip at or after
2026-11-14T19:00Z on Kalshi's clock, more than four hours past the last
fixture the books had listed. What this cannot show is the skew on games the
books list later, including the whole 11-14 Saturday slate: these 61 links
are two weeknight evenings, and other leagues carry a −3.5 h tail (linker.py
comment) that would leave 30 minutes of headroom, not an hour.

## 4. WNBA billing

No `basketball_wnba` row appears in `api_credits` on any budget day from
11-05 to 11-12. This is consistent with billing having stopped after the
league's last fixture, but it does not date the stop. 11-02 to 11-04 are
outside the window.

## What this does not establish

- Credits for 11-02 to 11-04 by sport. The credits-day rows carry `sport_key`, but section 1b did not sum them by sport.
- Why the 11-06 00:00Z NFL call failed, or its status code (section 1b).
- That no sweep or tap was declined for cost. Cost refusals inside `decide_sweeps` are written as `skipped`, or as nothing when the same pass fired, and taps refused at submit write no row (section 1b).
- That the alias file is complete. 62 fixtures over two weeknight evenings;
  the 18 not-carried events include power-conference home games (Rutgers,
  Vanderbilt, Oklahoma, Florida St., Oregon St.) that the books may not have
  listed yet, and their names were never tested.
- That the 61 links are right by name beyond the nine pinned ones. They are
  held to one-fixture-one-link and a uniform skew, which a wrong link at the
  same kickoff could still satisfy.
- A Saturday ceiling. 723 is one Saturday, on which college football also
  bought 192. Credits follow kickoff clusters and attention, not game counts,
  and `sport_key` names the sport a call was made for, not what caused the
  day's total (credits-by-sport's own caveat).
- A refusal after 11-12. Section 1b's zero covers 11-02 to 11-12 only.
- `x-requests-last: 0` is the capture run's printed header; the reduced
  fixtures carry no header, so it cannot be checked against them.
