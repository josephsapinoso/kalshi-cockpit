# 0014 — The sweep schedule is accepted as it stands

**Status:** accepted, 2026-08-09 (Joe's decision)

Closes the "READ THIS FIRST" item in `start.md`: that the gate's counters had
frozen for ten hours and the sweep scheduler was to blame. It was not, and the
options written up to fix it were answering a misdiagnosis.

## Context

On 2026-08-09 the live instance reported the same line on every pass from
05:36Z to 15:18Z:

    gate progress (24h): actionable=0 of 300 needed, no_edge=177, suppressed=271

`no_edge` sat at **exactly 177** across ten hours and twenty-odd passes, while
`suppressed` churned and `stale_odds` dominated. Every pass in that stretch
reported the same sweep decision:

    no sweep: next slot is basketball_wnba at 15:45Z-16:15Z for 3 game(s)
    from 16:30Z, sweeping 45-15 min before first kickoff

The reading on record was that `odds/timing.py` only fires 45–15 minutes before
a kickoff, so most passes price against odds that have aged out, and that
nobody had multiplied out how many passes a slot-based scheduler leaves with
fresh odds.

**That reading was wrong, and the error was in the measurement window.** Today's
first kickoff in any in-scope league is 16:15Z. Between the 05:51Z window
closing and 15:45Z there was not one fixture on the slate in any of the six
leagues `IN_SCOPE_LEAGUES` covers. The scheduler was not declining to fire — it
had nothing to aim at. A frozen counter over an interval containing no inputs
is not evidence of a stuck mechanism.

Three measurements settled it.

**The schedule already covers the slate.** Feeding the real slate through the
repo's own `plan_sweep_slots` (`scripts/measure_slot_coverage.py`, free — ESPN,
no odds credits):

    Today's slate: 19 games (mlb 15, wnba 4)
    Slots planned at the deployed 2h separation: 6
    Distinct games covered: 18 of 19        (36 credits of 400)
    MISSED  baseball_mlb  CIN @ WSH  16:15Z

Six windows, not one, and all of them after 15:45Z.

**Loosening the separation buys one game.** The single miss is the 16:15Z
opener, dropped because its slot sits 80 minutes from the 17:35Z cluster and
`MIN_SLOT_SEPARATION_MS` keeps the one covering 13 games:

    separation 2h (deployed) ->  6 sweeps (36 credits), 18 of 19 games
    separation 1h            ->  8 sweeps (48 credits), 19 of 19 games

**A real open window behaves exactly as designed.** The 15:45Z slot fired at
15:46:44Z:

    sweep decision: basketball_wnba (scheduled): 3 game(s) from 16:30Z
    pricing pass:   odds_sweeps 1, odds_quotes_stored 762,
                    recommendations 24, surfaced 0, suppressed 8
    gate progress:  actionable=0 of 300, no_edge=193, suppressed=273

`no_edge` moved 177 → 193: **+16 in one pass**, the same jump the 05:36Z sweep
produced. Of 24 rows written, 16 were `no_edge`, 8 suppressed, 0 actionable.

## Decision

**Accept the schedule unchanged.** Do not add slots, do not loosen
`MIN_SLOT_SEPARATION_MS`, and do not change what the gate counts.

Three options were on the table and two of them are refused on their merits:

- **Sweep more slots per sport.** Refused because there is no uncovered
  population to reach. The stated trade — "freshness at kickoff for coverage
  across the day" — assumed coverage was missing. It is 18 of 19. The change
  buys one game per day for 12 credits and costs freshness on the cluster
  covering 13 games.
- **Change what the gate counts.** Refused on safety grounds. This reverses
  ADR 0005, and that decision was not cosmetic: `suspicious_edge` rows are the
  likeliest carriers of a *systematic* CLV, so pooling them moves the mean
  rather than diluting it toward zero. It would arm real money on evidence
  about bets this strategy declines to make.

**And the arithmetic that makes the choice easy.** The gate counts 300
independent *games*. A slate is ~19 games. So 300 is **at minimum 16 days away
even if every game on every slate were actionable**, and the observed actionable
rate is zero across every fresh-odds decision this system has made. No
scheduling change moves a number bounded by the size of the slate. The
scheduler was never the binding constraint.

## Consequences

- `actionable=0` after a day of real windows is **the answer**, not a fault.
  The tool is actionable in the pre-kickoff windows and nowhere else, by design.
- The odds budget is confirmed as massively non-binding: 36 credits of 400 for
  a full slate. `tasks/NEXT.md`'s "≤12 useful slots/day per sport, so six
  leagues cannot exceed ~432/day" is a ceiling from the separation constant
  alone; the real bound is kickoff clusters, which on an August slate is three
  per sport.
- **The 300-game floor is not reachable by waiting**, and that is now recorded
  rather than rediscovered. The two things that move it are unchanged: the four
  fee-calibration trades (a hard gate condition, Joe's, no amount of CLV
  substitutes for it) and a historical backfill, where the ~80-day candlestick
  horizon is ~1,200 MLB games. The budget headroom to 13,000/month was reserved
  for the latter.
- `MAX_ODDS_AGE_S` and every suppression threshold stay where they are. A stale
  consensus priced against a live Kalshi ask is how a fabricated edge enters the
  record, and the record is the product.

## What would change this decision

- **A denser slate.** Every number here is August, with MLB and WNBA live and
  NBA, NHL and NCAAF out of season. A winter slate is several times the games
  and a different measurement; `scripts/measure_slot_coverage.py --date` exists
  so it can be re-read rather than re-argued.
- **A non-zero actionable rate.** If games start clearing the bar, the value of
  the 19th game per day stops being negligible and the 1h separation is worth
  re-costing.
- **Distinct-game coverage falling below the slate.** The claim accepted here is
  "the schedule covers the games that exist". If a future slate shape breaks
  that, this ADR is void.
