# Does the prune keep up with the table it prunes?

**Date:** 2026-08-19
**Instance:** live (`kalshi-cockpit`)

## Why this exists

ADR 0054's throughput arithmetic assumed **every** full pass prunes. The window
gate added later that day means passes inside an open sweep window do not, so
the margin over the table's growth had to be recomputed rather than assumed.
The failure mode being checked is quiet: `quotes_pruned` reports a healthy
non-zero number every pass while the table grows anyway.

## Method

`slots_for_sport` — the same function the scheduler spends odds credits with —
was run against the live fixture table over a 48h horizon, and the resulting
sweep slots unioned so two sports open at once count as one open window.

## Result

```
sports with fixtures     2
raw slots               12
merged open intervals    5
open hours / day      4.33

full passes / day       96
  inside a window       17   (no prune)
  pruning               79
```

| budget | batches/pass | rows/day | vs 1.30M growth | break-even |
|---|---:|---:|---:|---|
| 5s (as shipped) | 1 | 1,574,000 | +274,000 | **7.75 open h/day** |
| **30s (adopted)** | 2 | 3,160,000 | +1,860,000 | ~15.9 open h/day |

One 20,000-row batch costs **~20s** on live. That is index maintenance, not the
scan: every deleted row comes out of a 476 MiB btree. A budget below 20s
therefore buys exactly one batch, which is why the shipped 5s and the observed
~40s prune were not a contradiction.

## The decision

Budget raised to 30s. The margin at one batch was 274,000 rows/day — 17% — and
its break-even is **7.75 open hours/day against 4.33 measured**. Both NFL and
NBA are out of season as this is written and both return within weeks, and
`backend/kalshi/combos.py`'s calendar caveat records that those two are exactly
the sports missing from this project's schedule captures. A 17% margin in front
of a known seasonal increase is not a margin.

The cost is ~40s of a full pass rather than ~20s, and it is affordable for one
reason only: retention never runs while a window is open, so the minutes it
spends are ones in which nothing is bettable.

## What this does NOT establish

- **It is a lower bound on window hours, so an upper bound on throughput.** It
  reads the next 48h of *known* fixtures; a sport whose schedule has not loaded
  is absent. The error is in the optimistic direction — treat a comfortable
  margin as "not obviously broken", never as verified.
- **Two sports is a small base.** 4.33 open hours/day comes from 12 raw slots
  across 2 sports. It will change, and the whole point of the 30s budget is
  that the answer stops being sensitive to it.
- **The growth figure is one day's observation** (1.37M rows on the busiest day
  measured, rounded to 1.30M). It is not a modelled rate and it was itself
  rising: 264k/day a week earlier.
- **Nothing here measures whether the prune reduces `leg_store_ms`.** That is
  ADR 0054's open prediction and needs the table actually trimmed.
