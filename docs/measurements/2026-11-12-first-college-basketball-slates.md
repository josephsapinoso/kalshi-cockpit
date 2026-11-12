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
  #401 item 1's refusal read is still owed; #401 stays open for it.
- One Saturday is n = 1. The season's busiest college-basketball Saturdays
  come later, with more games than the 11-07 slate.

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

- Anything about 11-02 to 11-04, the opening days.
- That no pass was refused on any day (item 1).
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
- Anything about a refusal on the vendor's own count (`x-requests-remaining`),
  on any day.
- `x-requests-last: 0` is the capture run's printed header; the reduced
  fixtures carry no header, so it cannot be checked against them.
