# The WAL curve is flat, the discrimination could not be run, and the RSS level halved

Taken 2026-08-30 06:41-06:48Z against live (`kalshi-cockpit`, machine
`7812601a239428`, build `91a66f18`). Instrument: `wal_kb`, `db_kb`,
`candidate_rows`, `candidate_ms`, `leg_price_link_ms`, `leg_store_quotes_ms`
on each `/data/loop_rss.jsonl` line, shipped in `fe239d6` and first read here.
Window: the boot at **04:03:30Z**, 2.64 hours of uptime, **128 passes**, no
death. Raw series committed beside this file as
`2026-08-30-loop-rss-samples.jsonl`.

This is the read `tasks/NEXT.md` has carried as thread 1 since 2026-08-29.

## The pre-framed question, and why it has no answer

The registered discrimination (`scripts/run_loop.py:250-256`) was:

    store_quotes tracks wal_kb, link tracks candidate_rows
                                both mechanisms are real and additive
    both track wal_kb, candidate_rows flat
                                the query is an artifact, the WAL is all of it

**Neither row can be selected, because both regressors are constant.**

    wal_kb           two values in 128 rows:  4 (first pass), then 18544 x127
    db_kb            one value in 128 rows:   1865420
    candidate_rows   one value in 127 rows:   162

Against those constants the dependent variable moved 44-fold:

    leg_store_quotes_ms   n=127  min 62   p50 79   p90 97   max 2700
    leg_price_link_ms     n=127  min 551  p50 572  p90 592  max 950
    candidate_ms          n=127  min 419  p50 435  p90 451  max 744

A regressor with zero variance explains no variance. **The correct verdict is
that the design could not run on this window, not that the WAL is exonerated
and not that it is convicted.** Both named mechanisms are unexercised.

The file sizes were verified independently of the instrument, twice, 45s
apart, by `ls -la` inside the container:

    06:43:51Z   cockpit.db 1910190080   cockpit.db-wal 18989112
    06:44:37Z   cockpit.db 1910190080   cockpit.db-wal 18989112

1910190080 / 1024 = 1865420 KB and 18989112 / 1024 = 18544.06 KB, so the
instrument is reading the real files and is not caching. **Both mtimes advance
while both sizes do not** -- the WAL is being written in place at a stable
high-water mark, which is autocheckpointing working, not stalled.

## What did explain the storage leg: the kind of pass

    produced_by=full    n=  9   p50 439   p90 2700   max 2700   >200ms: 5 of 9
    produced_by=quote   n=118   p50  79   p90   92   max  621   >200ms: 2 of 118

A 5.6x separation in medians. **Read `n` first: nine full passes is a thin
cell** and this is one window, so it is a lead rather than a result. It is
also the unsurprising direction -- a full pass stores more quotes -- and it is
the variable the registered design did not include.

## The WAL does not grow with uptime on this horizon

Three boots carry the field. Ordered by how long they ran:

    boot 04:03:30Z   2.64 h   128 rows   wal 0.0 -> 18.1 MB
    boot 01:52:32Z   1.60 h    55 rows   wal 0.0 -> 31.3 MB
    boot 03:28:53Z   0.29 h     2 rows   wal 0.0 -> 21.9 MB

**The longest window has the smallest WAL.** The 220 MiB recorded before the
01:53Z deploy is therefore not a steady climb at this rate; a 2.64-hour window
that plateaus at 18.5 MB cannot reach 220 MiB by extrapolation. Whatever
produced 220 MiB is an episode, not this rate.

## The WAL was flat across the wedge that killed the 01:52Z boot

That boot died at 03:28:31Z with `CHAIN RUNNER exited`. Its last four
instrumented passes:

    02:26:47Z  wal 25.6 MB  cand 163  cand_ms 444  link 583  store 825
    02:40:52Z  wal 31.3 MB  cand 162  cand_ms 431  link 568  store 680
    02:57:42Z  wal 31.3 MB  cand 162  cand_ms 431  link 568  store 680
    03:14:05Z  wal 31.3 MB  cand 162  cand_ms 431  link 568  store 680

The last three lines are **byte-identical across all four leg figures**. Three
independent millisecond timers do not repeat exactly, and the instrument's own
docstring says the counts describe the *previous* pass: these rows are two
passes that started, read a `counts` object nothing had refreshed, and wrote it
again. **The wedge is visible in the record as a repeated line**, from
~02:40:52Z to the death 48 minutes later -- which is a second, cheaper wedge
detector than `pass-gaps`, and it needs no gap to have elapsed.

`wal_kb` held at 31.3 MB across the whole wedge. So for this incident the WAL
neither grew during the wedge nor preceded it. **The hypothesis that a wedge
balloons the WAL is refuted for this occurrence** (one occurrence).

## The guest-OOM question is answered: no

`/data/last_teardown.log` holds two records, both `CHAIN RUNNER exited`:

    01:13:16Z   MemFree 825556 kB   MemAvailable 1610212 kB
    03:28:31Z   MemFree 360872 kB   MemAvailable 1096868 kB

`record_teardown` runs `dmesg | tail -n 40` (`docker/entrypoint.sh:218`) and in
both records those 40 lines are the **end of the kernel boot sequence**, ending
at `Run /fly/init as init process`. The ring buffer had acquired nothing since
boot, so no OOM kill was printed. With 1.1-1.6 GB available at the moment of
death and a silent ring buffer, **the guest-OOM hypothesis left open on
2026-08-29 is refuted for both of these deaths.** The child is named, twice,
and it is the chain runner -- consistent with the poisoned-connection diagnosis
(`2026-08-30-the-wedge-is-a-poisoned-connection.md`), not with a kernel kill.

## The RSS level halved, and the 2026-08-20 measurement predicted the fix

RSS by minutes elapsed since each boot in the file (MB):

    boot            0     5    15    30    60    90   120   160   240   360
    08-29 18:03Z  128   667   667   692   682   745   730   720   742   741
    08-30 01:13Z  128   655   655   662     -     -     -     -     -     -
    08-30 01:44Z  128   652   652     -     -     -     -     -     -     -
    08-30 01:52Z  128   341   341     -     -     -     -     -     -     -
    08-30 04:03Z  128   128     -   332   333   339   339   339     -     -

Two findings.

**It is a level, not a leak** -- reproducing
`2026-08-20-the-585mb-is-a-level-not-a-leak.md` on a second instrument. The
level is built by the first full pass after boot (the 04:03Z boot sits at 128
MB until its first full pass at t=16.8 min, then steps straight to 332) and is
flat thereafter to the sample resolution.

**The level halved, and the control is eight minutes wide.** The 01:44:29Z boot
was a secrets restart of `c9ca0cd`; the 01:52:32Z boot was the `fe239d6`
deploy. Eight minutes apart, same hour, same slate, same workload: **652 MB
against 341 MB.** Time of day and fixture load cannot separate two boots eight
minutes apart, so this is the image.

`fe239d6` contains `0cfa849`, *"The walk is classified as it arrives, and the
peak was the list, not the junk"* -- confirmed new in `fe239d6` and absent from
`c9ca0cd` by `git merge-base --is-ancestor`. It replaces `raw_events = [e async
for e in kalshi_client.events(...)]` with a streamed walk. That is **exactly**
the fix the 2026-08-20 measurement named as its candidate without being able to
test it: *"the suspected `raw_events = [e async for e in ...]` materialisation
... Streaming that list is the candidate fix if the level ever matters."*

Three independent numbers now agree, which is what makes this a result rather
than a coincidence: the 2026-08-20 measurement **named** the list; `0cfa849`'s
own replay at live scale **predicted** 1,036 MB held against 24 MB dropped; and
this window **measured** the deployed effect on the real box, ~650-745 MB down
to ~340 MB. Named 2026-08-20, shipped by a lane 2026-08-29, observed on live
2026-08-30.

## What this does not establish

- **Nothing about days.** 2.64 hours and 128 passes. The 220 MiB WAL and the
  ~60-minute stall-to-death constant both live on a longer horizon than this
  window reaches.
- **What raised the WAL high-water mark in steps.** It stepped 0 -> 14.4 ->
  16.7 -> 25.6 -> 31.3 MB on the 01:52Z boot. The 16.7 -> 25.6 step follows the
  01:56:31Z odds sweep by 46 seconds, which is suggestive; the 25.6 -> 31.3 step
  has no sweep anywhere near it (nothing between 01:56:31Z and 04:20:20Z, per
  `credits-day`). One step matching and one not matching is not a mechanism.
- **What the two 10-25x scan spikes were.** 02:02:27Z read `candidate_ms`
  11202 / `leg_price_link_ms` 14881, and 02:09:13Z read 5451 / 7201, both with
  `wal_kb` flat at 25.6 MB and `candidate_rows` flat at 163. Neither registered
  regressor moved. Contention with another writer is the obvious third
  candidate and this window does not test it.
- **Causation between any pair of fields**, per the instrument's own docstring.
- **That the halved RSS prevents anything.** The deaths were not OOM (above),
  so halving the level removes a hypothesis rather than a cause.

## The next discriminating read, if this is reopened

The registered design needs a window in which `wal_kb` actually varies. Two
ways to get one, neither of which is a checkpoint or a VACUUM:

1. **Let a boot run into a wedge with the instrument on it.** The repeated-line
   signature above dates the wedge onset to the pass, so `wal_kb` on either
   side of that boundary is the reading the design wanted.
2. **Sample across a served sweep during an active slate.** Tonight's window
   was overnight -- the next slot is 16:21Z for 12 MLB games -- so
   `candidate_rows` sat at 162 all night. A daytime window varies both
   regressors at once.

Until one of those exists, `wal_kb` is not evidence in either direction.
