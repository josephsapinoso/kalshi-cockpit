# The window-gate observations, taken — 2026-08-20 baseball_mlb 15:26Z–16:26Z

The four observations registered in `2026-08-20-window-gate-plan.md` (written
03:40Z, before the code changed), taken after the window closed at 16:26Z.
Durable source: `odds_sweep_log`, pulled at 16:28:49Z through the committed
read-only inspector and preserved verbatim as
`2026-08-20-window-gate-sweep-log-pull.json`. Log source: two independent
captures started 13:45Z (a stream and a 150s poller), merged and deduped; both
were verified appending before the window. Computed by
`scripts/read_window_gate_observations.py` (committed, tested, `--since
2026-08-20T03:54:00Z` scoping out the 194 pre-deploy passes).

Build under test: `5656133`, deployed 03:54Z, `/api/health` confirmed. The box
did not restart all day — zero machine-lifecycle lines in either capture, and
the pass counter is continuous from pass 1 to the close.

## The verdicts

| # | registered observation | verdict |
|---|---|---|
| 1 | no `quotes_pruned > 0` on any pass 15:26Z–16:26Z | **PASS** — 3 exposures, all 0, backlog proven live |
| 2 | first pass after 15:26Z within ~17s | **PASS** — +6.9s |
| 3 | `window_open` latches within one pass; 15s cadence begins | **PASS** — with an artifact explained below |
| 4 | 900s cadence holds before the window; 2–4 bounded passes in the run-up | **PASS** — 2 bounded, 0 early wakes |

### Observation 1 — the gate held, and the backlog proves the zeros are real

Three full passes ran inside the window. All three report an affirmative
`'quotes_pruned': 0` counter on their captured pass lines — presence of a zero,
not absence of a line, which is stronger than the registration's fallback
anticipated:

```
15:38:28  pass 64   full  33.6s  quotes_pruned 0
15:53:44  pass 113  full  33.9s  quotes_pruned 0
16:08:45  pass 161  full  33.7s  quotes_pruned 0
```

The controls, both sides. Before: out-of-window full passes pruned all day
(15:06:31 → 4,074 rows; 15:22:58 → 2,037), so the backlog refills at roughly
2,000 rows per 15 minutes. After: the first full pass past the close pruned
**8,148 rows at 16:26:45** — 45 seconds after the window ended, almost exactly
four skipped prune opportunities' worth. The gate was refusing real work for
the whole hour, and the work was still there the moment the window closed.

Zero `retention: pruned` lines carry an in-window timestamp. (One at 16:26:45
matches a careless minute-bounded grep; it is 45s past the close, on the pass
whose `pass_ms` stamp is 16:26:11 — outside the window on the registered
predicate.)

### Observation 2 — the sleep bound delivered the open

First pass at or after 15:26:00Z: **15:26:06.9Z, +6.9s**, against the
registered bar of `fast_interval x (1+jitter) = 17.2s` and a pre-fix worst
case of up to 900s. The 03:57Z simulation predicted +1.4s mean; +6.9s is
within one fast interval of it. That pass is the one that served the sweep —
`served | 6 game(s) from 16:41Z` in its own `odds_sweep_log` row.

### Observation 3 — latched within one pass, and the analysis script's FAIL line is an artifact

The registered wording is *"latches true within one pass of 15:26Z"*. The
serving pass (15:26:06.9) opened the window **mid-pass** — the exact mechanism
the plan's fault-1 analysis documents — so the first decision that could read
it open was the next one: **15:26:23.9, +17.0s, one pass later.** The
registered claim holds.

`read_window_gate_observations.py` prints `FAIL` here, and that line is
preserved rather than edited away: the script operationalised the observation
as "the first pass after the open reads open", which is stricter than the
registration and false by construction whenever the opening sweep is served
mid-pass. Compounding it, the script's open-markers do not match this served
row's wording (`holding the window open` appears on refresh-cycle serves, not
on this scheduled serve). The script's cadence half is unaffected: **148/148
in-window passes read open** in their own decision text, median gap 18.2s,
142/147 gaps at the fast cadence.

### Observation 4 — no spin, and the run-up converged

Pre-window, on the new build: 44 window-closed passes, every gap between 769s
and 1,062s (the 1,062 is a 1,035 ceiling plus a ~34s full-pass duration —
gaps are start-to-start). **Zero gaps below the 765s floor**, which is the
"already due" spin guard holding. In the final 15 minutes: **2 bounded
passes** (15:22:47 → 15:25:48, 181s), inside the registered 2–4 band.

## Two unregistered anomalies, recorded for the next session

Neither is one of the four registered observations and neither falsifies one.
Both are reported because they cost real minutes of an open window.

**Two mid-window cadence dropouts, same signature.** Pass 56 ends healthy at
15:28:50 (quote, 2.7s); **no process log line of any kind for 6m07s**; pass 57
starts healthy at 15:34:54. Again at the tail: pass at 16:18:46 (odds 2.1min
old, decision reads open), then nothing until 16:26:34 — 468s, the rest of the
window. Pass numbers consecutive both times; no restart; every in-pass
decision on both sides reads `window is open`.

The first dropout's arithmetic is exact: 369.7s × 1.15 lands on the 15:36:00
refresh — the **bounded-sleep branch**, which only runs when
`tempo.window_open` is False. So at the end of pass 56 the cadence flag read
closed while every decision inside the passes read open. That is the same
end-of-pass-flag staleness family that fix 1 cured at the prune — **the
cadence still reads the flag assigned at the end of the previous pass**, and
something at the end of pass 56 wrote it False. What wrote it False is not
recoverable from these logs; the second dropout's 468s does not match the same
arithmetic cleanly and is left unexplained rather than force-fitted.

Cost: ~838s of a 3,600s window served at the slow-recovery cadence — 148
passes against ~201 achievable. The window was **served**, at roughly
three-quarters of the designed density.

**These do not reopen the fixes measured here.** Fix 1's falsifier did not
fire in 3 exposures; fix 2 delivered the open at +6.9s. The dropouts are a
third defect in the same family, in a read neither fix touched.

## The 12-hour stability watch — separate observation, matured

Deploy 03:54Z; watch matured 15:54Z. Zero restarts, zero OOM lines, pass
counter continuous across the whole day including the open window. Reported
separately from the gate observations, as the registration requires.

## What this does not establish

- Nothing about the correctness of any surfaced row — this was a scheduling
  measurement.
- Nothing about the cause of the two dropouts. The bounded-sleep arithmetic
  fits the first; that is a hypothesis with one data point, not a diagnosis.
- Observation 1's three zeros are three exposures on one slate. The gate's
  code path is the same on every window, but this measurement covers this
  window.
- The ~585 MB holder, `unmatched_events` growth, and the health flap remain
  untouched and open.
