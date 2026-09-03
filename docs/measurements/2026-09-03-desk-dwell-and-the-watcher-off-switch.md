# 2026-09-03 — Desk dwell, not desk abandonment; and the cold-open watcher is switched off on the opens it exists for

Two readings taken on the same morning, both from the live instance, both
correcting a sentence written the day before. Neither is a registered
measurement and neither enters the signal record; both are operator-behaviour
and instrument readings with `n = 1 operator`.

## 0. What was asked, and by whom

The partner agent, invoked at session start, was handed the 2026-09-02 entry's
"the desk went quiet" finding (attention-tagged odds buys 75 → 5 a day over
five days; `manual_orders` 0 rows lifetime) and the queue ranked around it.
It asked two questions before ranking anything:

1. Is "went quiet" a fact about *how often* Joe opens the desk, or about
   something else the counter measures?
2. Yesterday's `/picks` self-heal (`RefreshWhenPriced`, ADR 0098 Amendment 1)
   was written against the visit-freshness read of 2026-09-02. Does it run on
   the opens that read described?

## 1. Sources

All read-only, none touching the money path.

| read | how | when |
|---|---|---|
| `visit-freshness --since 20260820` | `flyctl ssh console -C "python /app/scripts/inspect_live_db.py …"` | 2026-09-03 ~06:10Z |
| `credits-day --date 20260830` | same | same |
| `manual-orders-audit` | same | same |
| `estimate-match-status` | same | same |
| `loop_rss-2026-09-02T19Z.jsonl` | copy of live `data/loop_rss.jsonl` taken 2026-09-02, in `data/live-snapshots/` (gitignored) | pass log, 6,066 passes, 2026-08-29T18:03Z → 2026-09-02T19:39Z |

The analysis script is throwaway (session scratchpad); every figure below was
recomputed from the raw rows rather than copied from the partner's report,
and the two agree.

## 2. Reading 1 — visits per day are flat; attended minutes are not

`desk_attention` rows clustered into visits with a 300 s gap. Budget day
starts 10:00Z, as `credits-day` defines it.

    budget_day  visits  attended_min  zero_length  nothing_fresh_at_open
    20260825     14         76.0          6            8
    20260826      7         46.7          2            6
    20260827      6        324.2          2            3
    20260828      8        127.0          2            2
    20260829      5         10.9          1            2
    20260830      5        223.2          1            3
    20260831      8          9.5          4            7
    20260901      5          2.6          3            2
    20260902      7        161.3          2            2

- **Opens per day: 5–8 on every day after the first.** Nothing in the
  column reads as a fall.
- **Attended minutes per day: 2.6 to 324, no trend.** 08-27 (the day the
  slice ran out) and 08-30 and 09-02 are each multi-hour; 08-29, 08-31 and
  09-01 are each under eleven minutes. The 2026-09-02 entry's "75 → 5"
  was the count of ten-minute-cadence buys *while a page is open* — a
  duration meter — and it was read as an occurrence meter.
- **Half the visits are one heartbeat long.** 23 of 65 have
  `duration_s = 0`. Over 08-31..09-02, 19 visits: nine at zero, the rest
  7, 13, 23, 38, 120, 158, 173, 179, 212 s and one at 9,305 s.

**Two caveats travel with every row.** `desk_attention` is `(id, seen_ms)`
and nothing else: it cannot tell a reader from a tab left open and visible
(the 9,305 s visit on 09-02 is most of that day's minutes), and a
backgrounded tab stamps nothing, so a visit that was *read* in the
background is invisible. Nothing here is a measure of reading.

### 2.1 The attention tag is displaceable by the schedule

`credits-day --date 20260830` shows eight baseball buys on a ten-minute
cadence between 15:11Z and 17:04Z with `trigger = NULL` and **no visit in
progress** (visit 40 ended 07:40Z; visit 41 starts 17:14Z). Those are
kickoff-window slot buys (`firing_for_slot`), which satisfy the sport's
cadence before the attention branch is consulted, so an attended buy that
would have been tagged `'attention'` is not made. `trigger = 'attention'`
is therefore a **lower bound** on attention-cadence buying, and on a
slate-heavy afternoon it undercounts. This is why the 2026-08-27 "4.9
hours" figure in `CLAUDE.md` is one day and not a rate.

### 2.2 What reading 1 corrects

- The 2026-09-02 NEXT.md entry: "~15-fold in five days … does not plausibly
  cover a factor of fifteen" described a fall in dwell, not in opens.
- The refreshed interview artifact's lead question, *"why did you stop
  opening it?"*, presupposed a behaviour the data does not show. It should
  read: *when you open it (about 6×/day, usually under a minute), what are
  you checking?*
- `manual_orders = 0` lifetime is now corroborated by `manual-orders-audit`
  on live (census A: `n_rows 0`); it had been single-sourced.

## 3. Reading 2 — the watcher is off on 8 of 26 opens, all of them the stale ones

`RefreshWhenPriced` is gated on `anAutomaticBuyIsComing(actionable)`,
computed on the server render from `/api/window`. `readNextWindow` returns
`loop_stalled` when `now_ms - last_look_ms > LOOP_STALL_MS` (180,000 ms),
and `loop_stalled` makes the predicate false, so the component returns
before setting an interval and renders *"It will not change by itself until
you reload it."* The loop's unattended idle cadence is ~900 s
(`RUNNER_INTERVAL_S`; full→full median 926.8 s over the 6,066 passes).

For each of the 26 visits whose start lies inside the pass log's span, the
age of the most recent pass at the visit's first heartbeat:

    stalled (>180 s) & nothing fresh at open      8
    stalled (>180 s) & something fresh            0
    not stalled      & nothing fresh at open      7
    not stalled      & something fresh           11

- **8 of 26 opens (31%) rendered the watcher switched off.**
- **8 of the 15 nothing-fresh opens (53%) did** — the population the watcher
  exists for.
- **0 of 11 fresh opens did**, and that is structural rather than lucky: a
  fresh fixture implies the ten-minute cadence was running, so the last pass
  is never more than ~30 s old.
- Exhibit: visit 59, 2026-09-02T13:28:22Z, 13 s long. Last pass 926 s old at
  open; the cold-open heartbeat woke the loop and the buy landed at +0.6 s;
  `fixtures_fresh` went 0 → 150 inside the visit. The screen said it would
  not change.

Ages at open for the eight: 712, 766, 815, 340, 307, 554, 501, 926 s — every
one inside the loop's normal idle sleep. None was a stalled loop.

### 3.1 The mechanism, in one sentence

`anAutomaticBuyIsComing` is evaluated from a snapshot taken **before the
page's own heartbeat exists**, so it asks whether a buy is scheduled using
facts that predate the thing that schedules the buy. Fixing `LOOP_STALL_MS`
alone would be wrong twice over: raising it past 900 s blinds the screen to a
genuinely dead loop for fifteen minutes, and the stall question is not the
buy question. Lane D (2026-09-03) separates them; its ADR takes its number at
merge.

### 3.2 The other two off-switches, unobserved here

`slice_spent`: `refused_sweeps = 0` on all 65 visits since 08-20, so not
binding in this sample; it bound on 08-27/28 and will on a four-sport slate.
`nothing_to_schedule`: not observed; the attended branch of `desk_wants` has
no horizon filter, so while a page is open the desk buys regardless of what
the reading says. Both are recorded so the fix is not scoped to the one that
happened to bind.

## 4. What this does not establish

- **That the heal produces a card.** It re-renders a comparison. `actionable`
  is 51 rows / 15 games lifetime at the reference profile and 0 at the
  deployed bankroll.
- **Why Joe opens the desk.** Dwell and frequency are recorded; intent is
  not, and the question is put to him directly (see the session entry).
- **A rate.** 9 budget days, 65 visits, one operator. Per-day dwell is
  bimodal (sub-minute opens plus an occasional multi-hour tab) and no
  central figure describes it; none is offered.
- **`share_first_age_over_limit`.** This read prints 0.846; the 2026-09-02
  read printed 0.911. Both derive from `first_age_ms`, which
  `2026-09-02-visit-freshness-first-read.md` §3 refused on three grounds.
  The usable figure is `nothing_fresh_at_open`: **35/65 = 0.538** over the
  two weeks (21/45 = 0.467 over the previous read's window).
- **That the fix is live.** It is not, at the time of writing.
