# NCAAF alternate spreads and totals are two-sided, and cost what the formula says

**Date:** 2026-10-03, ~19:10Z. **Ticket:** #303 step 1, for Joe's answer (A) on #304.
**n = 1 event:** BYU @ TCU, kickoff 2026-10-03T23:00Z, about 4 hours out.

## The call

One `GET /sports/americanfootball_ncaaf/events/{id}/odds` with
`markets=alternate_spreads,alternate_totals` and the ten live `ODDS_BOOKMAKERS`
(`fly.live.toml:655`). It was made from a scratch script with the local key, and it
is not in the repo. The `/events` listing that found the event id billed 0.

| quantity | value |
|---|---|
| `x-requests-last` (credits billed) | **2** — `sweep_cost` = 2 markets × ceil(10/10), as `backend/odds/budget.py` computes |
| books returned (of 10 asked) | 6: pinnacle, draftkings, fanduel, fanatics, betmgm, bovada |
| alternate_spreads lines quoted per book | 8–60 |
| alternate_totals lines quoted per book | 8–104 |
| lines where the book quoted only one side | **0 at every book, in both markets** |
| books quoting BYU −6.5 (the friend's leg) | 6 of 6 |
| books quoting Over/Under 47.5 | 5 of 6 (not draftkings) |

"Two-sided" means: spreads have both teams at the same absolute line, and totals have both
Over and Under at the same line. Pinnacle, the sharp anchor, quotes 9 lines in each market.

## What this establishes

- On this event, alternate team lines can be devigged at the friend's exact number from
  six books including Pinnacle. The one-sided failure that killed MLB alternate *props*
  (`backend/odds/client.py` ~L215, 2026-08-16) did not occur here.
- The vendor bills alternate team keys at the ordinary per-market rate.

## What this does not establish

- **n = 1 event, one sport, one moment.** It says nothing about NFL, NBA, MLB or NHL
  alternates, or about how this game's alternate prices look nearer kickoff or in a
  smaller college game. Every college game Joe checks has its own coverage, and
  `alt_lines.py` must count dropped one-sided quotes rather than assume this result.
- It does not say the alternate prices are accurate, only that they can be paired.
  Worst-of-four (`consensus_devig`) still applies.
- Four of the ten configured books returned nothing for these keys, and why is unknown.
