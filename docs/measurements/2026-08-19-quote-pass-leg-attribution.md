# Where a pass's wall clock actually goes, leg by leg

**Date:** 2026-08-19
**Instance:** live (`kalshi-cockpit`), `shared-cpu-1x:1024MB`, region `ord`
**Commit:** `dfcf249` (leg instrumentation), on top of `f79f73a` (ADR 0053)

## Why this exists

`took_s` alone had sent two sessions after the wrong leg. The quote pass that
melted the box was attributed first to the inserts, then to the parse -- both
refuted -- before the HTTP walk was found and narrowed (ADR 0053). This session
then produced a *third* wrong attribution by the same mechanism, and it is
recorded here because the mechanism, not the answer, is the lesson.

## The third wrong attribution, and how it was produced

The narrowed walk was timed on the live box at **2.55s**, parse at 0.11s, and
the store legs at **0.02s** -- the last against a scratch database in tmpfs.
Against an observed `took_s` of 23.6s that subtraction leaves ~21s, and the
conclusion drawn was "pricing is the dominant leg".

Both inputs were wrong in the same direction.

- **The 23.6s was a single sample taken 16 minutes after a machine boot.** The
  next quote pass measured **9.7s**. `n = 1`, and the one sample was the one
  with cold caches.
- **The 0.02s store was measured against an empty database in RAM.** On the
  live volume, at 6.8M rows behind a 476 MiB index, the same leg measures
  **5,997 ms** -- three hundred times larger.

Neither error would have survived reading `n` before the effect size, which is
the first measurement rule in `CLAUDE.md`.

## The measurement

First instrumented pass on live, a **full** pass:

| leg | ms | what it is |
|---|---:|---|
| `leg_walk_ms` | 8,454 | Kalshi HTTP walk (full catalogue -- full passes are not narrowed) |
| `leg_parse_ms` | 96 | classifying the payload into priceable events |
| `leg_store_ms` | **5,997** | `upsert_discovered` + `store_quotes_from_discovery` |
| `leg_price_ms` | 2,793 | devig, review and persist |
| sum | 17,340 | |
| `took_s` | 44.6s | |

## What this establishes

**The store leg is 6.0 seconds, not 0.17.** The 2026-08-19 cost attribution
recorded the inserts at 0.17s and used that to rule them out, and this file
does not overturn that measurement -- it was taken at **279k rows** and was
correct there. It overturns its *continued use*: the table now holds 6.8M rows
behind a 476 MiB index, and the same work costs 35x more. A write cost measured
against a table that grows is a measurement with an expiry date.

**Pricing is not the dominant leg** -- 2.8s of a 44.6s pass. The subtraction
that said ~21s was wrong in both of its terms.

**Roughly 27s of the full pass is in none of these four legs.** That is
expected and not a defect: a full pass also runs scoring, settlement, market
results and alerts, none of which these fields cover. It is stated because a
sum well short of `took_s` must not be read as unexplained.

## What this does NOT establish

- **Nothing about an open window.** Every sample here was taken with the window
  closed, so the odds sweep leg did not run and the cadence was 900s rather
  than 15s. The first open window after this commit is `baseball_mlb` at
  **15:21Z**; that is the test, and it had not happened when this was written.
- **Nothing about a quote pass's legs.** The one instrumented sample is a full
  pass. A quote pass differs in the walk (narrowed, ~2.5s) and is otherwise the
  same work, which *projects* to ~11.4s -- a projection, not an observation.
- **Not a CPU measurement.** `perf_counter` is wall clock and includes time the
  process spent descheduled. That is the right number for "why is the box
  unresponsive" and the wrong one for "how much CPU does this leg need".
- **`n = 1`.** Everything above is one pass.

## The consequence for the disk decision

The 2026-08-19 handoff instructed that the `kalshi_quotes` population change is
a **disk** decision and must not be justified with latency evidence, because
the writes measured 0.17s. That instruction was correct when written and is now
obsolete in one direction: the store leg is 6.0s and scales with the table, so
narrowing or pruning that table is **both** the disk fix and a latency fix.

The instruction's *purpose* still holds and should be honoured -- the two must
not be conflated, and the ADR must cite this file for the latency half rather
than reusing the 0.17s number in either direction.
