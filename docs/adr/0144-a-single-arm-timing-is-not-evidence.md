# 0144 — A single-arm timing is not evidence either

Date: 2026-09-10
Status: accepted
Amends: ADR 0141, which it agrees with and does not overturn.

Written by lane B on 2026-09-10 while adding `idx_odds_window`. Filed as
`DRAFT-a-single-arm-timing-is-not-evidence.md` with no ordinal taken, per
`docs/adr/README.md`; numbered 0144 at the merge checklist step, after
confirming `ls docs/adr/` topped out at 0143 on `main`.

## The decision

ADR 0141 says a plan diff cannot price an index: `EXPLAIN QUERY PLAN` reports
the access method and never how many rows the method touches, so **time it**.
That is right and stays.

This adds the half ADR 0141 leaves open: **how to time it.** Two numbers taken
from separate runs are not a before and an after. When comparing index
configurations, every arm gets its own copy of the same data and they are timed
**round-robin in one process**, and what gets recorded is the **paired ratio**,
with the span across whatever regimes the box can produce.

## Why — measured, not argued

Adding a covering index for `/api/window`'s freshness query, at live's shape
(3.63M rows, 2,640 events, 800 upcoming), on one desktop, over one evening:

```
same query, same data, same warm best-of-three

   session A      1,283 ms      (1.44 GB file fully resident, CPU-bound)
   session B      3,904 ms      (a second 1.46 GB file had been built since)
```

**A 3x swing in the headline with nothing changed but how much of the file the
OS still held.** Either number, written down and compared against an "after"
taken in the other session, would have produced a ratio between 1.6x and 15x —
any of which would have read as a finding.

The paired ratio over those same two regimes moved 5.1x → 5.8x. Across four
cache regimes it stayed inside 5.1x–6.1x. **The ratio is the stable quantity on
this hardware; the milliseconds are not.**

This is not a small refinement. It changed a conclusion in the same session:
two sequential runs had the cheaper four-column index ahead of the five-column
one in one cache regime and behind in the other, and the first draft of the
`schema.sql` comment recorded a 222-vs-184 ms win that **the paired measurement
does not support**. Timed round-robin, the real margin is 2–9%, consistent in
direction at four cache sizes — a different decision, honestly reached, and one
that names what dropping the fifth column would buy back.

## What this does not say

- **It does not make a local benchmark transferable.** ADR 0141's floor-versus-
  magnitude rule still governs: when the benchmark and production differ in
  which resource binds, a ratio is a direction and a floor, never a magnitude.
  v39's local 3x returned 81x on live. Interleaving makes the local ratio
  *trustworthy as a floor*; it does not make it a prediction.
- **It does not apply to a single absolute latency** — "the route takes 1.0 s
  on live" needs no second arm. It applies whenever two configurations are
  being compared.
- **It says nothing about how many rounds are enough.** Five was enough here
  to separate 5.1x from 1.0x and not enough to separate 2% from 9% confidently;
  the rule is to report the span rather than a single best.

## Consequences

- `scripts/measure_window_index.py` times every arm round-robin and says in its
  own docstring that a number written down earlier is not a baseline. Any
  successor index harness follows it rather than
  `scripts/measure_odds_scan_index.py`, whose arms are sequential.
- A recorded index justification carries the **span** across regimes, not one
  ratio.
- When an index comparison lands within a few percent, say so and name the
  mechanism that the benchmark cannot price, rather than promoting the noise to
  a result. `idx_odds_window`'s fifth column is bought on a 2–9% measured
  margin plus ~40,000 table-row fetches per call the box cannot charge for —
  and the comment says exactly that, including what to give back first.
