# Live OOM-killed itself at 18:59:16Z, and memory pressure fits this incident better than table size does

Taken 2026-08-19 19:30-19:50Z on live (`a482fea`), while watching for the
`link slow` line the previous handoff asked for. The OOM was found by accident;
the memory measurements that follow it were not.

## What this establishes

That the loop process was killed by the kernel OOM killer at **18:59:16Z** and
the machine restarted at 18:59:43Z, unprompted -- no deploy; that in steady
state the loop holds **~555 MB RSS on a 962 MB box**; that **every full pass
adds ~55 MB and halves the page cache**, taking `MemAvailable` to 35 MB; and
that the page cache available to a **1.5 GB** database whose hot index is
**476 MiB** is therefore **~130 MB steady and ~76 MB during a full pass**.

## What it does not

**It does not establish that memory pressure causes the slow state.** That is
the seventh candidate mechanism on this incident and six of the first six were
wrong. What is claimed here is narrower and is argued below: it is the first
candidate that predicts the *timing* behaviour instead of explaining it away.

**One OOM event.** The log buffer reaches back only to ~17:56Z, so whether this
recurs on a schedule, or had happened before today, is unknown from here.

It does not identify what holds the 555 MB. The closing section names a
candidate and marks it as unverified, deliberately.

## The kill

```
18:36Z - 18:52Z   seven health-check failures on port 3000
18:59:16Z         Out of memory: Killed process 707 (python)
                  total-vm:1037280kB  anon-rss:675560kB
18:59:43Z         machine started; entrypoint, migrate, run_loop
19:00Z onward     took_s ~9s, leg_store_ms ~6s, leg_price_link_ms ~260ms
```

Same machine id, same release version 91. Nothing was deployed.

**The health-check failures are not a separate incident.** The handoff records
health flapping as *fixed and verified* on 2026-08-19 15:30Z, and it was --
`docs/measurements/2026-08-19-health-flap-is-the-proxy-hop.md` measured 0
failures of 12 where it had been 5 of 10. Seven failures in sixteen minutes
immediately before an OOM kill is the box dying, not the keep-alive regressing.
**Do not re-open the keep-alive fix on this evidence.**

## The steady state, and the full-pass spike

Sampled from `/proc` on live, one line per reading:

```
19:45:40Z  up 2758  rss 560 MB  avail 75 MB  cached 125 MB
19:45:55Z  up 2773  rss 559 MB  avail 76 MB  cached 126 MB
19:46:10Z  up 2788  rss 613 MB  avail 35 MB  cached  76 MB   <- full pass
19:46:25Z  up 2803  rss 603 MB  avail 39 MB  cached  83 MB
19:46:40Z  up 2818  rss 604 MB  avail 45 MB  cached  89 MB
19:46:55Z  up 2833  rss 601 MB  avail 45 MB  cached  84 MB
19:47:10Z  up 2848  rss 596 MB  avail 44 MB  cached  91 MB
19:47:25Z  up 2863  rss 568 MB  avail 62 MB  cached 121 MB
19:48:24Z  up 2922  rss 545 MB  avail 82 MB  cached 136 MB
```

Full passes ran at 19:01:25Z, 19:16:13Z, 19:31:55Z -- the 900s cadence -- so the
spike above is the next one. It lasts about a minute, which is that pass's
`took_s`.

**`MemAvailable` reaching 35 MB is the number to keep.** The database file is
1546 MB and `idx_quotes_ticker_time` alone was measured at 476 MiB. At 76-130 MB
of page cache, **under a tenth of the index the pass writes into every fifteen
seconds can be resident.** Every insert that misses is a disk read on a shared
volume.

## Why this fits where six previous candidates did not

The previous file
(`2026-08-19-window-store-leg-result.md`) records four properties of the slow
state that no theory has accounted for together:

| observation | table size | memory pressure |
|---|---|---|
| restart appears to fix it | no -- table is unchanged across a restart | **yes** -- and the "restart" was an OOM kill |
| transition is abrupt, not a ramp | no -- the table grows smoothly | **yes** -- a cache falls off a cliff, it does not taper |
| "uptime" does not quite fit | -- | **yes** -- RSS is not linear in uptime; the spike is per full pass |
| 5-8% table growth, ~2x store leg | poorly -- needs strong non-linearity | **yes** -- cache residency is the non-linearity |

The table-size story needs the insert cost to be sharply non-linear in row
count. `store/retention.py` records exactly that -- 0.17s at 279k rows, 6.0s
then 14.0s at 6.9M -- so it is not refuted, and the two are not rivals:
**cache residency is the mechanism by which table size costs anything.** What
memory pressure adds is a reason the same table can be fast at 19:00Z and slow
at 18:38Z.

**This is a hypothesis with a good fit, not a result.** It earns the next
measurement, not a fix.

## What the 555 MB might be, unverified

`PRAGMA cache_size` and `mmap_size` are never set (`store/db.py` sets only
`foreign_keys`, `journal_mode` and `synchronous`), so SQLite's per-connection
page cache defaults to ~2 MB and is **not** the holder.

The candidate is the walk. `run_kalshi_pass` does

```python
raw_events = [e async for e in kalshi_client.events(with_nested_markets=True)]
```

and on a **full** pass `run_once` passes no `series_tickers`, so this is the
whole catalogue with nested markets, materialised into one list. ADR 0053
measured that walk at **15.21s of transfer** against 3.13s for the scoped one.
`events()` is already an async generator; the comprehension is what forces the
catalogue to exist all at once.

That would explain a high flat baseline as well as the spike -- CPython returns
freed arenas to the OS only partially, so a peak becomes a floor.

**None of that is measured.** The falsifiable version: RSS should rise during
`leg_walk_ms` on a full pass and not during a quote pass's narrowed walk, and
the sampling above is too coarse to say. `leg_walk_ms` is ~7,060ms on a full
pass against ~2,300ms on a quote pass, which is consistent and is not evidence.

## The immediate consequence, which does not depend on the cause

The box is running with **35-82 MB free**. Whatever holds the memory, there is
no headroom for the write rate to grow into, and
`2026-08-19-the-prune-loses-to-the-writer.md` establishes that
`kalshi_quotes` is growing at **+6.4M rows/day** -- which grows the index, which
needs the page cache that is not there.

**ADR 0055 (write only on change) therefore attacks this too**, and by the same
arithmetic: fewer rows is a smaller index is more of it resident. That was not
the reason it was chosen and it does not become a second justification for it --
it is stated so that a future session reading this file does not treat the two
as competing work.
