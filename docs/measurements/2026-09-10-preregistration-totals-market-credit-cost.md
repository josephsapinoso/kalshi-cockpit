# Pre-registration — does adding `totals` to ODDS_MARKETS fit under the 700/day cap?

**Registered 2026-09-10**, before the 2026-09-13 budget day opens and before
the odds freeze lifts at 10:00Z 2026-09-14. No data for the baseline day
exists at the time of writing. Zero credits are spent by this measurement.

## 0. Precondition, checked before any of the rest is worth running

`totals` currently has **no consumer**: `backend/core/ladder.py`
`TEAM_MARKETS_ONLY = frozenset({"h2h","spreads"})`, `backend/parlays.py`
`CANDIDATE_SQL` admits `h2h`, `spreads` and the five MLB prop keys only, and
no totals subtitle parser, link inheritance or pricing branch exists
(`backend/kalshi/spreads.py` refuses totals by docstring; the runner's
derived-event set carries only PROP and SPREAD). `fair-prices-by-market`
found 41,292 `totals` rows in `odds_snapshots` and **zero** in `fair_prices`,
last written 2026-08-16.

**If the pricer and the ladder do not accept `totals` at the moment
`ODDS_MARKETS` changes, the answer is DO NOT ADD regardless of every figure
below**, because the spend buys dead history. This section is a gate, not a
caveat, and it is decided by reading two files rather than by any measurement.

## 1. The claims, stated so each can come back false

**H1 (billing).** A team `/odds` call is billed `len(markets) x len(regions)`
by the vendor, so adding a third market multiplies the per-call charge by
exactly **1.5** (4 -> 6 at `ODDS_REGIONS = "us,eu"`).
*Direction: one-sided is meaningless here — H1 is an equality and any
disagreement beyond one call refutes it.*
Provenance of the 1.5: `sweep_cost`, `backend/odds/budget.py:66-68`. It is a
code fact about **our** arithmetic; H1 is the claim that the vendor agrees.

**H2 (call-count invariance).** The number of team `/odds` calls per budget day
does not depend on `ODDS_MARKETS`. Slot planning runs off fixtures
(`plan_sweep_slots`), not markets; `/odds` returns the same event set.
*Falsified if post-change team-call counts leave the pre-change range for a
comparable slate.*

**H3 (the decision claim).** Projected demand for budget day 20260913 under a
three-market config, `D_hat`, is **at most 560 credits** — 80% of the 700 cap.
*Directional and one-sided: the alternative of interest is `D_hat > 560`.*

H3 is the decision-bearing claim. H1 and H2 are gates on it: if either fails,
`D_hat` is not computable by the method registered here and the look is void.

## 2. Population and exclusions, fixed now

**Baseline day.** Budget day **20260913**: `called_ms` in
[10:00:00Z 2026-09-13, 10:00:00Z 2026-09-14), the 10:00Z boundary of
`CreditBudget.day_start_ms`. NFL Week 2 Sunday, inside the freeze, so no
odds-path logic change can land inside it.

**Rows.** All `api_credits` rows in that window, split into two strata *by
endpoint and market string, both outcome-independent*:
- **T (team sweeps):** `endpoint` is the `/sports/{key}/odds` path AND
  `markets = 'h2h,spreads'`. These scale by 1.5.
- **P (everything else):** props, historical, anything with a different market
  string. These do **not** scale — `prop_market_keys()` is independent of
  `ODDS_MARKETS`. Carried at recorded cost.

**Refused demand.** `odds_sweep_log` rows in the same window with
`outcome = 'refused'` or a skip whose `detail` names a budget ceiling
(the three strings built in `CreditBudget.refusal_reason` and the two in
`decide_sweeps`' desk branch). Each such refused call is unserved demand.

**Exclusions, all independent of the outcome:**
- **E1 — retry storm.** If more than 5% of the day's `api_credits` rows carry
  `http_status` not in (200, NULL), 20260913 is disqualified as a baseline and
  the next full NFL Sunday inside a 2-market config is used. This keys on
  transport status, never on the day's total.
- **E2 — logic change inside the window.** If any commit touching
  `backend/odds/**` or `backend/scheduler.py` deploys inside the window, the
  day is disqualified. (The freeze makes this unlikely; the rule exists so the
  disqualification is not a judgement call afterwards.)
- **E3 — UI contamination is NOT an exclusion.** Attention dwell on 20260913 is
  part of the day, not noise to be removed. Per the standing NEXT.md
  instruction nobody opens the cockpit UI to run the combo-exit capture, but if
  someone does, the day still counts and the dwell is reported.

There is **no exclusion keyed on the credit total**. An exclusion that fires
because the number came out high is the finding.

## 3. Unit of observation and clustering

The unit is the **budget day**, not the call. Calls within a day are not
independent: they are paced by one planner off one fixture set against one
shared 700-credit ledger, and a refusal on one call causes the next. n = 1 day
for the baseline. This is stated so no figure below is ever quoted with a
denominator of "N calls".

The secondary unit for H1 is the **consecutive-row pair** in `api_credits`,
which is genuinely near-independent because each pair carries the vendor's own
counter.

## 4. The cut — fixed edges

Only two numeric edges are used, both fixed here:

- **560 credits** = 80% of the 700 cap. Chosen as the cap minus a 20% margin,
  before seeing 20260913, because a projection built on one simulated NFL day
  (124, `2026-09-08-nfl-sunday-credit-convergence.md`) and one non-NFL base
  should not be run to the last credit.
- **700 credits** = `ODDS_DAILY_CREDIT_BUDGET`, `fly.live.toml`.

No bucketing by sport, hour, or trigger enters the decision. Those splits are
reported as description only and are named in §9 as things the look does not
establish.

## 5. The statistics, named as estimators

**For H1 — a set of exact integer deltas, not a mean.**
`delta_i = used_reported(i) - used_reported(i-1)` over consecutive
`api_credits` rows with both values non-NULL and `called_ms` differing by
>= 60 s (the gap requirement excludes concurrent in-flight responses arriving
out of order, the trap recorded in `2026-09-06-nfl-week-1-credit-headroom.md`
§4). H1 predicts `delta_i == cost_i` on every such pair.
Validated **before the change** on three market counts already in the record:
1-market era (predict 2), current 2-market (predict 4), the 2026-08-16 prop
rows (predict 10). Reported as counts of agreeing / disagreeing pairs, not as
a proportion with a standard error — the quantity is deterministic under H1
and any disagreement is a refutation, not a tail event.

**For H3 — a deterministic transform of one observed day, not an estimate.**

    D_hat = 1.5 x SUM(cost over stratum T)
          + SUM(cost over stratum P)
          + 6 x (count of budget-refused planned team calls)

`D_hat` has no sampling distribution and no confidence interval, and none will
be reported. It is what the ledger of 20260913 would have cost at three
markets, plus the demand the cap already suppressed. Its uncertainty is
entirely structural (§9), not statistical.

**A second, reported alongside and never instead:** the arithmetic ceiling

    A = 1.5 x SUM(cost over T where trigger IS NULL or 'desk')
      + 300   (ODDS_ATTENTION_DAILY_CREDITS — a credit cap, it does NOT scale)
      + 150   (DEFAULT_MANUAL_DAILY_CREDITS — also a credit cap)

`A` is what the day could have demanded, `D_hat` is what it did. Both are
quoted or neither.

**Binding is an event, not a statistic.** Whether `fire=()` occurred is read
directly from `odds_sweep_log` and is true or false. It carries no error bar
and needs no multiplicity correction.

## 6. Decision rule, verbatim, with multiplicity counted

Three cells are tested on the baseline: H1 (agreement of used-deltas), H2
(team-call count in range), H3 (`D_hat` against 560 and 700). Two of the three
are deterministic checks of an equality and cannot produce a false positive by
noise. No alpha is spent and none is corrected, because no cell is an estimate
of a population parameter. **If any future write-up reports a *rate* — "NFL
Sundays bind X% of the time" — this registration does not cover it and it is
underpowered by §10.**

    IF H1 fails on the pre-change validation (any used-delta pair disagrees
    with sweep_cost by more than one call across the three market counts):
        the 1.5x projection is void. Do not add totals. Re-derive the billing
        model first and register again.

    ELSE IF the §0 consumer precondition is unmet:
        DO NOT ADD TOTALS. Ship the pricer and ladder support first.

    ELSE IF any pass on 20260913 recorded refused_by_budget = True, or any
    odds_sweep_log row that day names a budget ceiling as its reason:
        DO NOT ADD TOTALS. The 2-market config already binds; 1.5x can only
        be worse.

    ELSE IF D_hat <= 560:
        ADD TOTALS. No other change. Enter the 7-day monitoring window (§7).

    ELSE IF 560 < D_hat <= 700:
        ADD TOTALS ONLY WITH THE ATTENTION SLICE LOWERED to
            s = 6 * floor( (700 - 150 - 1.5 * scheduled_T) / 6 )
        where scheduled_T = SUM(cost over T where trigger IS NULL or 'desk').
        If s < 60 (fewer than ten attended calls), treat as DO NOT ADD:
        a slice that small is not an attended cadence, it is a rounding error.

    ELSE (D_hat > 700):
        DO NOT ADD TOTALS.

**Rollback rule, pre-committed, for the monitoring window.** Revert
`ODDS_MARKETS` to `"h2h,spreads"` within one budget day if, on any budget day
in the window, EITHER (a) one or more passes record `refused_by_budget = True`,
OR (b) budget-named refusals exceed 10% of (served + refused) team calls for
the day. Reverting is a one-line config change and is not a finding; it is the
brake.

**Consequence in both directions, stated now.** If it clears: `totals` is added
and the parlay ladder gains totals legs. If it does not clear: `totals` stays
off and the totals-leg card is not built this season — not deferred, not
"revisited when there is headroom". The measurement is decision-relevant in
both directions; neither branch is "proceed anyway".

**ADR 0110 binds above this document.** It already refuses totals this season
at `us,eu` and dates the only lever that admits them (drop `eu`, 3 credits a
call) to 2026-09-28 behind two preconditions. An ADD branch here does not
override that ADR; it supplies the measured four-sport budget day the ADR's
first precondition asks for.

## 7. Stopping rule

- **Baseline read:** taken **once**, after 10:00Z 2026-09-14, on budget day
  20260913. One look. If the read is botched it may be re-run against the same
  rows, but the day is not re-chosen.
- **Monitoring window:** exactly **7 budget days**, beginning with the first
  full budget day after `ODDS_MARKETS` changes. It ends on schedule whether or
  not anything is observed. It is not extended to catch a Sunday, and it is not
  cut short because the first days look quiet.
- **2026-09-20** (the first NFL Sunday outside the freeze) is a **confirmatory
  observation inside that window, not a second arm.** It cannot on its own
  clear or refute anything; it can only trigger the rollback rule.

## 8. What falsifies the 1.5x claim

Consecutive `used_reported` deltas that do not equal `sweep_cost` for the
config in force. Specifically: post-change team-sweep deltas that are not 6, or
pre-change deltas that are not 4 / 2 / 10 at the three historical market counts.
Plausible mechanisms that would produce this and are therefore live
alternatives: the vendor charging per market *returned* rather than per market
*requested*; a flat per-call charge; a discount on additional markets; a second
consumer on the key (which would push the vendor's count above ours — the
2026-09-06 read found ours above theirs by exactly one boundary call, which
rules a second consumer out **as of that read only**).

**`api_credits.cost` cannot falsify H1**, because `budget.record` writes our
own `sweep_cost` into it. Any write-up that reads a post-change `cost` of 6 as
confirmation has confirmed nothing.

## 9. What this cannot establish, written before the run

- **A probability that an NFL Sunday binds.** n = 1 baseline day, n <= 1 Sunday
  in the monitoring window, one operator. §10 gives the arithmetic.
- **Anything about attention dwell on the day it matters.** Dwell is the one
  free term, it ranges 2.6-324 minutes/day over nine observed days, it is
  bimodal, and no simulation supplies it. `D_hat` inherits whatever dwell
  20260913 happened to have. A quiet Sunday makes `D_hat` an under-estimate of
  a busy one and there is no correction for this.
- **Four concurrent sports.** The record's maximum is three (MLB, NCAAF, NFL);
  WNBA re-entering makes four and is unobserved. MLB's regular season ends
  2026-09-27, which cuts the other way inside the monitoring window and means
  the window's later days are not exchangeable with its earlier ones.
- **Whether NFL Week 3 (09-20) plans the same cluster count as Week 2.** Week 2
  is locked at 13 games / 3 clusters; later weeks flex, and the season worst is
  ~152-156 credits at 5 clusters. Any 09-20 comparison must re-plan through
  `plan_sweep_slots`, never assume 124.
- **The value of totals legs.** Nothing here says a totals leg is worth 2
  credits a call. It is a cost question only; ADR 0038 governs value, and the
  hunt is closed.
- **Cold-start / failure spend.** A failing bootstrap can spend the whole cap
  in 2h54m with a page open and is bounded by `BOOTSTRAP_RETRY_BACKOFF_MS`, not
  by `D_hat`. Unmodelled here and can only add.
- **Completeness of `api_credits`.** It counts rows the recorder wrote; an
  unrecorded call is invisible to it. `used_reported` is the only independent
  check.
- **What `api_credits.trigger` means.** `'attention'` is a **lower bound** on
  attention-cadence buying (a kickoff-window slot satisfies the cadence first
  and lands NULL), and it is a **duration meter, not an occurrence meter** — it
  measures dwell. The mechanism split (kickoff window / hourly floor / desk
  open) is read from `odds_sweep_log.detail`, never from `trigger`.

## 10. The power check

**The rate question is dead at every n available.** To estimate P(the cap binds
on an NFL Sunday) to +/-0.10 at 95% needs ~96 Sundays at p ~ 0.5. The 2026 NFL
regular season has 18. Even +/-0.20 needs ~24. **No season-length record can
produce that rate**, so it is not asked, and any write-up that reports one is
outside this registration.

**The demand question is answerable at n = 1 day, because it is arithmetic.**
`D_hat` is a deterministic transform of a complete ledger; it has no sampling
error. What it has is one unmeasured input (dwell) and a set of structural
gaps (§9), and those are reported as bounds rather than as an interval.

**The look is decision-relevant, which is the check that matters.** Applying
the registered 1.5x to the seven observed budget days already in the record
(196, 328, 348, 356, 496, 336, 300) gives 294-744 — a range that **straddles
both registered edges**. So the rule can return ADD, ADD-WITH-SLICE-LOWERED or
DO-NOT-ADD, and none of the three is foreclosed before the baseline is read. If
the scaled range had lain entirely under 560 the look would be unnecessary; if
entirely over 700 it would already be decided.

## 11. Can 20260913 serve as the control, and what contaminates it

**It is not a control in the experimental sense** — there is no randomisation
and no concurrent comparison. It is a **pre-change baseline for a deterministic
transformation**, and it is usable only because H2 holds: the same day's calls,
re-priced. If H2 fails, the baseline is worthless and §6 says so.

Contaminants, all named before the read:

1. **Dwell.** The live term, unmeasurable in advance, up to 300 credits. The
   largest single threat and the reason `A` is reported beside `D_hat`.
2. **Slate composition.** 20260913 carries NFL + MLB + NCAAF; NCAAF Week 3
   plays no Sunday games. 20260920 may differ on all three counts, and MLB ends
   09-27. Two Sundays are not exchangeable and will not be treated as such.
3. **Retry storms and 401/429s** — E1 disqualifies the day.
4. **UI opens for the combo-exit capture.** Standing instruction is that nobody
   opens the cockpit UI for it; a page-open adds dwell. If it happens the day
   still counts and the fact is recorded (E3).
5. **A deploy inside the window.** A deploy is not contamination; an odds-path
   *logic* change is, and E2 disqualifies on it. The freeze is what makes this
   controllable.
6. **The 2026-09-07 cadence change (ADR 0111).** Both 09-13 and 09-20 are after
   it, so it does not differ between them — but every budget day before
   2026-09-07 measures a mechanism that no longer runs and may not be pooled
   with them.

## 12. Where the negative result gets written

`docs/measurements/2026-09-14-totals-market-credit-cost-result.md`, whichever
way it comes out. If the rule returns DO NOT ADD, that file is still written,
on that date, with `D_hat`, `A`, the used-delta table, and the §6 branch taken.
If `totals` is never added, the file is the record of why.

## 13. Reproduction

    scripts/inspect_live_db.py credits-day --date 20260913
    scripts/inspect_live_db.py credits-by-sport --since 20260907
    scripts/inspect_live_db.py sweep-log -n 400
    scripts/inspect_live_db.py credits-reset
    scripts/inspect_live_db.py visit-freshness --since 20260907
    scripts/inspect_live_db.py fair-prices-by-market      # the §0 gate

Read the mechanism split from `odds_sweep_log.detail`, never from
`api_credits.trigger`. Read `credits-day`'s trailing row-count line before
quoting any section — a truncated section renders identically to an empty one.
