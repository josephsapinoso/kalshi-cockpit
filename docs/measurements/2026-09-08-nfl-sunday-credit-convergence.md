# The NFL Sunday convergence: the clusters are cheap, the attended day is not

**Taken 2026-09-08**, against live (`kalshi-cockpit`, deploy `263179c`) and the
272-fixture NFL capture taken the same day. **Zero credits** — every figure is
either a read of `api_credits` or the real planner driven over a committed
fixture.

**Question (NEXT.md item 4).** Does the NFL Sunday of 2026-09-13 bind the
700-credit daily cap? The budget day runs 10:00Z 09-13 → 10:00Z 09-14, so the
00:20Z Sunday-nighter is charged to the **same** budget day as the 17:00Z games.
That convergence is what the question was raised about.

---

## The verdict, in two halves that point opposite ways

**The convergence is real and it is cheap.** The planner asks for 3 clusters on
09-13 — 8 games at 17:00Z, 4 at 20:25Z, 1 at 00:20Z — and the third cluster
costs **28 credits of 700, about 4%**. NFL's entire scheduled demand for the day
is **124 credits**. Against every observed non-NFL budget day (180–496),
`base + 124` lands at **304–620**. Scheduled demand alone does not bind.

**The attended day can bind, and it is not an exotic case — it is the modal
case for this particular Sunday.** The three spenders draw from one
undifferentiated 700 with **no reservation between them**, and their own
sub-caps sum past it:

    scheduled base (20260906 non-attention)      304
    NFL scheduled demand, 09-13                  124
    attention slice, if spent                    300   ODDS_ATTENTION_DAILY_CREDITS
    manual-tap reserve                           150   DEFAULT_MANUAL_DAILY_CREDITS
    ------------------------------------------------
    arithmetic ceiling                           878   against a 700 cap

**So the day cap is load-bearing, not slack.** That conclusion is a code fact
and survives every defect in the projection below: `CreditBudget.refusal_reason`
checks a flat `remaining_today < cost` (`backend/odds/budget.py:218`) with no
per-spender reservation.

---

## The number was wrong once here, and the way it was wrong is the lesson

This document first computed **116** credits for 09-13. The correct figure is
**124**, and 124 was **already in the record** — `2026-09-06-nfl-week-1-credit-headroom.md`
Amendment 1, and the docstring of
`tests/test_sweep_timing.py::test_a_full_window_is_seven_calls_and_the_number_is_written_down`,
which exists *specifically* to stop a six being quoted.

The defect: `scripts/simulate_nfl_sunday_credits.py` restated the due-window
predicate as `fire_from_ms <= now < fire_until_ms`. Production's
`SweepSlot.is_due` is `fire_from_ms <= now_ms <= fire_until_ms`
(`backend/odds/timing.py:281`). The strict `<` drops the seventh call of every
window — six refreshes counted as six calls, where seven is the number a cluster
actually costs.

**The script printed its own contradiction and it was not read.** Its banner
computes calls-per-window from the constants and prints `7 calls per full
window`; eight lines below, the body reported 18 window calls across 3 clusters.

Two things this says that generalise:

- **A consumer that restates a predicate is not covered by the test that pins
  the predicate.** `test_a_full_window_is_seven_calls...` was green throughout;
  it guards the planner, and the defect was in a script that declined to call
  it. The fix is not a better test of `is_due` — it is calling `is_due`.
- **A new derivation that disagrees with a published number must halt.** The
  116 was quoted with no comparison against the 124 already written down twice
  in this repo. Reproducing a figure is evidence; silently replacing one is not.

A second defect, found in the same audit: the script planned **once** at day
start, where `decide_sweeps` replans every pass. A cluster suppressed by
`MIN_SLOT_SEPARATION_MS` at 10:00Z becomes servable once the competing slot's
`fire_until` passes. **09-13 is unaffected** — its anchor set is identical
either way — but the season-worst claim was: one-shot planning reported a
maximum of 4 clusters and `{1:36, 2:2, 3:13, 4:6}`, where replanning gives a
maximum of **5** and `{1:36, 2:2, 3:5, 4:8, 5:6}`. **Six 5-cluster days were
invisible.**

`tests/test_simulate_nfl_sunday_credits.py` pins both. Reintroducing the strict
`<` turns three tests red; reverting to one-shot planning turns the season test
red. Both were verified by mutation, not assumed.

## What the simulator does, and the four things it cannot see

`scripts/simulate_nfl_sunday_credits.py` walks a budget day a minute at a time,
replanning through the real `plan_sweep_slots` over the real season schedule in
`tests/fixtures/odds_nfl_h2h_spreads.json`, and applies two rules: a due slot
buys on entry and every `refresh_interval_ms` (600s) thereafter; otherwise a
sport with a fixture inside `DESK_FLOOR_HORIZON_MS` (12h) buys at most hourly,
with the hour measured from the last buy of **any** kind, so a window refresh
suppresses a floor call rather than adding to it.

**It models demand, not spend.** It passes `slots_available=999` and carries no
credit ledger, so it structurally cannot observe the cap binding — which is the
thing being asked. It is also NFL-only, single-sport, and network-free: retries,
429s, a `fetch_odds` returning `[]` (which re-triggers bootstrap), and partial
slates are all unmodelled and can only add.

### The season, for context rather than as a claim

| budget day | dow | games | clusters | window | floor | credits |
|---|---|---:|---:|---:|---:|---:|
| 2026-11-08 | Sun | 13 | 5 | 28 | 10 | **152** |
| 2026-11-15 | Sun | 12 | 5 | 28 | 10 | 152 |
| 2026-10-04 | Sun | 14 | 5 | 28 | 9 | 148 |
| **2026-09-13** | **Sun** | **13** | **3** | **21** | **10** | **124** |

An independent re-derivation on a 15s grid gave **156** for 2026-11-08 rather
than 152. The gap is one call, and it is real rather than noise: on a
5-cluster day two windows overlap, and this simulator carries a single
`last_buy` across them (correct for one sport, since `decide_sweeps` serves at
most one due slot per sport per pass) while a per-slot model counts their
refreshes independently. **Quote the season worst as ~152–156, and do not
quote it at all for a week that can flex.**

## Why "displacement makes 878 loose" is wrong, having been believed here

The first draft argued the ceiling was loose because attention is displaced by
the schedule — CLAUDE.md records that a kickoff-window slot satisfies the
cadence before the attention branch, so those buys land with a NULL trigger.
That is true and it does not do what was claimed.

- A window call and an attention call for the same sport in the same ten
  minutes are **one call**, already counted in the window term. Displacement
  **relabels** it (`trigger=ATTENTION` → NULL); it does not remove it.
- `attention_spent` counts only ATTENTION-stamped rows
  (`backend/odds/timing.py:2388`). So a displaced buy leaves the slice
  *unspent*, and the slice then funds a call in a later hour.
- Therefore, under the premise where it matters — the slice being exhausted —
  **displacement moves exactly zero credits off the day's total.**

The general shape, which is worth more than this instance: **a mechanism that
relabels spend cannot be cited as a saving.** Check whether the cap it defers
to is a cap on the label or a cap on the money.

## What binding actually does, which is two states and not one

**Partial refusal comes first.** Inside a pass, each due slot reserves its whole
remaining tail — `held = min(projected, credits_left)`, up to 28 credits
(`timing.py:2206`). Service order is taps → bootstrap → slots (chronological) →
floor/desk, and that last loop iterates `for sport_key in sorted(fixtures)`
(`timing.py:2322`) — **alphabetical**. So under scarcity
`americanfootball_ncaaf` and `americanfootball_nfl` are served before
`baseball_mlb`, and `basketball_wnba` dies first. NFL's kickoff windows outrank
everyone's hourly floor. The slate degrades; it does not go dark.

**The full stop needs `remaining == 0`** → `fire=()`, every sport silent until
the next 10:00Z (`timing.py:2003`). A day that *demands* 728 does not
necessarily reach it, because the refusals begin much earlier and are what stop
it getting there.

An earlier version of this analysis reported only the second state. That
overstates the consequence and understates the frequency: the first state is
common and quiet, and the screen's own account of it is what item 5 was about.

## The base is one Sunday, on Labor Day weekend, under a retired policy

Observed budget days, decomposed by trigger (`credits-day --date`):

| day | dow | attention | scheduled | total |
|---|---|---:|---:|---:|
| 20260901 | Tue | 24 | 172 | 196 |
| 20260902 | Wed | 112 | 216 | 328 |
| 20260903 | Thu | 32 | 316 | 348 |
| 20260904 | Fri | 0 | 356 | 356 |
| 20260905 | Sat | 12 | 484 | **496** |
| 20260906 | Sun | 32 | 304 | 336 |
| 20260907 | Mon | 60 | 240 | 300 |

**Three reasons not to call this a Sunday base.**

1. **2026-09-07 is Labor Day.** 20260906/20260907 are the only Sunday and Monday
   of the NCAAF season carrying a scheduled Sunday and Monday slate. The single
   Sunday in the base is the *least* representative Sunday of the year, and its
   NCAAF component will not recur on 09-13 (NCAAF Week 3 plays no Sunday games).
2. **n = 1, and the cell of interest is n = 0.** There has never been a
   Sunday-with-NFL. The prior document's limitation — *"the base period omits
   precisely the weekday cells the projection is about"* — is **not** retired by
   this week, contrary to an earlier draft of this file. What exists now is one
   non-NFL holiday Sunday.
3. **Six of the seven days predate ADR 0111** (`9e7e6c7`, 2026-09-07), under
   which every sport inside the 48h horizon took the ten-minute attended
   cadence. The attention column measures a mechanism that no longer runs.

**And the central estimate used the wrong day.** Taking 20260906's 32 attention
credits as typical means projecting an essentially *unattended* Sunday for the
one day of the week Joe is most likely to sit on the desk all afternoon. The
slice needs ~75 attention calls — 4.2–6.3 attended hours at two or three sports
inside the fast horizon. **20260827 spent the whole slice in 4.88 hours**, and
observed dwell reaches 324 minutes in a day. Applying more scrutiny to good
news: the comfortable answer came from assuming he would not be watching.

## Also established, and one thing that was mis-credited

- **The NFL cold start cost 4 credits** — one call at 03:23:58Z on 2026-09-08,
  no retry storm. But this does **not** retire the prior document's unbounded
  cold-start risk, which was conditioned on a *failing* first sweep (700 credits
  in 2h54m). One success confirms the branch Amendment 1 had already simulated
  at exactly +4. What actually bounds the failure branch is
  `BOOTSTRAP_RETRY_BACKOFF_MS = 30 * 60 * 1000` (`timing.py:1239`, ADR 0109),
  committed 2026-09-06 — **before** the observation. Credit the code, not the
  one good day.
- **`credits-by-sport`'s default 7-day window truncates its oldest day
  mid-day.** 20260901 reads 180 there and 196 over the full budget day. Do not
  compare its oldest row to the others.
- **The ledger is short by 4 credits on 2026-09-08**, from the laptop-run wire
  capture. Immaterial to any total here; recorded because §1 of the prior
  document turns on ledger-and-server agreeing to within one call.

## What this does not establish

- **Any measured NFL Sunday.** `americanfootball_nfl` has two served sweeps in
  the entire record. Everything above is demand arithmetic against an observed
  non-NFL base.
- **Behaviour at four concurrent sports.** The base is two sports; NFL makes
  three. The prior document's open question stays open.
- **The season worst.** ~152–156, from one capture, on weeks that flex. Week 2
  is locked, so 09-13 itself is safe from that.
- **Whether the slice will actually be spent on 09-13.** This is the only live
  term and no simulation can supply it.

## The measurement that would settle it

After 10:00Z on 2026-09-14:

    scripts/inspect_live_db.py credits-day --date 20260913
    scripts/inspect_live_db.py sweep-log
    scripts/inspect_live_db.py visit-freshness

Read the three mechanisms apart from `odds_sweep_log.detail` (kickoff window /
hourly floor / desk open) rather than from `api_credits.trigger`, which pools
them and is displaceable. Record attended minutes on the same day, because
whether the slice binds is the whole question and it is the one term that has to
be observed rather than derived.
