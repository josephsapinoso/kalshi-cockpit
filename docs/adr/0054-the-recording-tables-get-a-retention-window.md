# 0054 — The recording tables get a retention window

**Date:** 2026-08-19
**Status:** accepted
**Supersedes nothing. Amends the separation instruction in the 2026-08-19 handoff.**

## Context

Nothing in this project had ever deleted a row. `kalshi_quotes` and
`unmatched_events` grew for the life of the volume, and by 2026-08-19 that was
causing two distinct failures.

**Disk.** The volume filled on 2026-08-16. On 2026-08-19 it was 79% full again
— 1.41 GiB of database on a 2 GiB filesystem, 405 MB free — growing 214 MiB/day
and accelerating: 264k quote rows/day a week earlier against 1.37M the previous
day. That is **1.9 days to full**, and a full SQLite volume is a hard down that
a restart does not clear, because `VACUUM` needs roughly twice the free space it
would have by then.

**Latency.** Each quote pass inserts ~5,300 rows into `kalshi_quotes`, behind a
`(ticker, observed_ms DESC)` index that had reached **476 MiB** on a machine
with 1 GiB of RAM. Measured on live:

| table size | store leg |
|---|---:|
| 279k rows | 0.17s |
| 6.9M rows | **6.0s**, then **14.0s** on the next pass |

on a **15 second** cadence. See
`docs/measurements/2026-08-19-quote-pass-leg-attribution.md`.

### This overturns one instruction, and it should be said plainly

The 2026-08-19 handoff and `tasks/NEXT.md` both instructed that narrowing
`kalshi_quotes` is a **disk** decision that must not be justified with latency
evidence, "because the writes measured 0.17s". That instruction was correct when
written and its *purpose* — do not justify one change with the other's evidence
— still stands. But its premise has expired: the 0.17s was measured at 279k
rows, and the store leg is now the largest measured leg of a pass. Bounding the
table is now **both** fixes at once.

That is not a licence to recycle either number. This ADR cites the leg
attribution for the latency half and the volume measurement for the disk half,
and neither is used for the other.

## Decision

Add `backend/store/retention.py`, called **once per full pass** (900s) and
never on the quote cadence.

**`kalshi_quotes`** — delete rows older than **3 days** whose `ticker` has never
appeared in `recommendations`.

Every production reader was enumerated before the rule was written:

| reader | reaches back |
|---|---|
| `runner.latest_kalshi_quote` | newest row for one ticker |
| `routes.py` recorder health | newest row overall |
| `slate.kalshi_drift_tenths` | **one hour** |
| `clv_signal.py` | joined through `recommendations.ticker` |

So the only reader that reaches past an hour reaches through a recommendation,
and `recommendations` is the only downstream table carrying a ticker at all
(`fair_prices` is keyed by `link_id`). Three days against a one-hour longest
reader is a ~72x margin — deliberately generous, so a future reader added
without reading the module has room to be wrong before it is silently starved.

On live this keeps 4.8% of the table unconditionally and makes 45.5% of
6,946,356 rows eligible immediately.

**`unmatched_events`** — delete rows older than **7 days**, unconditionally on
`resolved`. Unconditional because **0 of 506,655** live rows had ever been
resolved: a rule that spared resolved rows would spare nothing while reading as
a safeguard.

**Bounded twice: 20,000 rows per statement, and 5 seconds per pass.**

The batch size limits how long one `DELETE` holds the write lock. That is
**not** the same quantity as how long the *pass* is blocked, and conflating
them cost a live stall on the first run: the prune runs inside the pass, so
deleting until nothing matches blocked the recorder for the whole backlog
however small the batches were. Measured 2026-08-19: 1.25M rows removed at
~60k/minute with 1.8M still pending, `recorder.age_ms` climbing one second
per second throughout. The time budget was added in the same session that
shipped the bug.

Each table gets its own full budget rather than a shared deadline, so a
quote backlog cannot starve `unmatched_events` indefinitely.

The batch bound still earns its place on its own terms: a single unbounded
`DELETE` over millions of rows holds the write lock for its whole duration,
and the next quote pass would block behind it — turning a disk fix into a
latency incident. Both bounds are needed and neither substitutes for the
other.

### The two bounds are coupled to the pass interval, and the arithmetic is tight

A batch of 20,000 takes ~20s against the live table, so the 5s budget buys
**exactly one batch per pass**. Throughput is therefore
`DELETE_BATCH x passes-per-day`, and it has to beat the table's growth or
the prune loses ground while appearing to work:

```
96 full passes/day x 20,000  =  1.92M pruned/day
observed growth              =  1.30M rows/day
net drain                    =  0.62M/day  ->  ~2.8 days to clear the backlog
```

**Lowering `DELETE_BATCH` for a shorter stall would invert this.** At 5,000
it is 480k/day against 1.3M of growth -- the table grows forever while
`quotes_pruned` reports a healthy non-zero number every pass. Nothing in
the code couples these three quantities, so the check is this paragraph:
**change either constant and re-do the arithmetic against current growth.**

The tell that the backlog is still draining is `quotes_pruned` sitting at
exactly `DELETE_BATCH` every pass. When it drops below, the prune has
caught up and is in steady state.

**Both counts are reported on the pass line** (`quotes_pruned`,
`unmatched_pruned`), always, including zero: a prune that has stopped finding
anything and a prune that has stopped running produce the same silence.

## Also decided, and it is not code

The Fly volume was extended from 3 GB to 5 GB. That was done first, because it
removed the 1.9-day deadline in thirty seconds and let this rule be designed
rather than rushed. Free space went from 405 MB to 3.2 GB.

**A latent bug was found doing it.** The volume was *already* provisioned at
3 GB while the filesystem reported **2.0 G** — a previous extend had grown the
volume and never grown the filesystem. So the 2026-08-16 fill happened against
2 GB on a volume that was supposed to be 3. After this extend the filesystem
reports 4.9 G, so the resize did take this time. **Any future extend must be
verified with `df -h /data` on the machine, not with `flyctl volumes list`** —
the two disagreed for at least three days and the optimistic one is the one
`flyctl` prints.

## Consequences

- Both tables become bounded. Growth stops even without a `VACUUM`, because
  freed pages are reused by subsequent inserts.
- **The file does not shrink.** SQLite returns freed pages to a free list, not
  to the filesystem. Any claim that the database got smaller must come from a
  `VACUUM`, which is now affordable at 3.2 GB free but is not part of this
  change.
- The store leg should fall as the index shrinks. **That is a prediction, not a
  result** — the pass now reports `leg_store_ms`, so the next full pass after
  deploy measures it. If it does not fall, the index size was not the cause and
  this ADR's latency half is wrong while its disk half stands.
- The record's population changes: quotes for never-recommended tickers older
  than three days no longer exist. Nothing reads them today. A future analysis
  that wants them must raise the window here *before* it needs them.

## What would falsify this -- and the wrong way to check it

**Do not read `leg_store_ms` off a pass that pruned.** The prune and the
store write into the same index in the same pass, so a pruning pass measures
the store leg while millions of btree pages are being freed underneath it.
Observed 2026-08-19 on passes that pruned 20k-40k rows: **5,416ms then
10,450ms**, varying 2x with the table size barely moving. That is the prune
showing up in the store leg, not evidence about either.

**The clean measurement is a QUOTE pass**, which never prunes (the window
gate and the full-pass-only rule both see to that) and does the same store
work. Compare quote-pass `leg_store_ms` before and after the table is
trimmed. At the time of writing no instrumented quote pass had been
observed at all, so the prediction below is completely untested.


`leg_store_ms` staying at 6–14s after the table has been trimmed. That would
mean the insert cost is not driven by index size, and the latency argument
above would have to be withdrawn — leaving the disk argument, which stands on
its own measurement.

## Amendment, 2026-08-20 — the auto-extend net is exhausted, and the ceiling's tripwire fired by the wrong route

Recorded on the day the disk question was re-measured and closed (live
volume 42.77% used, `cockpit.db` byte-identical across a 17-minute window,
measured growth 0 B/day with ADR 0055 retention deployed and verified
running).

The volume sits at its `auto_extend_size_limit = "5GB"`. **The net that
saved the instance on 2026-08-16 cannot fire again** — any further growth
ends in ENOSPC, a hard down that a restart does not clear, and recovery is
a manual `fly volumes extend` from a laptop. Not urgent at 0 B/day; it must
exist in writing because the failure mode is silent until it is total.

The second fact is about the tripwire itself: `fly.live.toml`'s comment
said reaching 5GB means "something is growing that should have a retention
rule — find it, not raise the number". The 5GB was reached by *this ADR's
own manual extend*, not by unbounded growth — **the trigger fired without
its condition being true**, and the comment as written would have
misdirected the responder who hit it. The comment is corrected in the same
commit as this amendment. The pattern (a relaxed bound leaves the next
bound binding silently, with the symptom unchanged) is the two-limits
pattern; treat any future "we raised the limit" as also creating the next
tripwire to document.
