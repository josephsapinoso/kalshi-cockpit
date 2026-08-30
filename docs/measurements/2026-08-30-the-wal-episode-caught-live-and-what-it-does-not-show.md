# The WAL episode was caught live, and a restart was the only cure

Taken 2026-08-30 17:21-17:53Z against live (`kalshi-cockpit`, machine
`7812601a239428`, version 168, deployed 17:17:00Z). Instrument:
`scripts/inspect_live_db.py loop-rss -n 40` and `walk-log -n 15`, plus
`curl` timings against `/api/health` from a laptop.

**This is the episode `2026-08-30-the-wal-curve-is-flat-and-the-rss-level-
halved.md` said it could not reach.** That read closed with "whatever
produced 220 MiB is an episode, not this rate". One is recorded here. It was
found because Joe could not use the desk: the parlay screen took ~15s to
load and every "Price on Kalshi" tap was refused.

## The series

    iso (Z)     kind   wal_kb  avail_kb  cand_rows  cand_ms  link_ms  store_ms
    17:21:37    quote   16649   1297336        159      462      607       833
    17:22:53    quote   16649   1298380        159      455      605       444
    17:24:53    quote   17236   1301440        159      449      592       130
    17:29:22    quote   17236   1285872        164      461      605       324
    17:32:01    quote   17236   1270944        164      458      607       233
    17:32:26    FULL    31926    840240        164      926     1227       163
    17:36:56    quote   32042    721380        164    14703    21124      6954
    17:38:35    quote   32042    542140        164     2982     4743      1801
    17:39:47    quote   32042    535268        164    16799    23924     12167
    17:40:09    quote   32042    512808        164      455      598      1283
    17:41:30    quote   32042    522812        164    12482    17922      2527
    17:44:12    quote   66217    504560        164    31837    36864     12962
    17:46:49    quote   99551    577120        164    36632    48876     13127
    -- machine restarted 17:50:45Z --
    17:52:55    FULL       28   1534076       NULL     NULL     NULL      NULL

`walk-log` puts the 17:32:26Z pass at 12,744 events against 643 on every
narrowed pass either side of it, and 0 of 826 lines are the "quote pass took
the full walk" anomaly that query exists to find.

Laptop timings on `/api/health`, unauthenticated, same minutes:

    17:50Z (degraded)   3.425s
    17:53Z (restarted)  0.369s

## What this establishes

1. **The WAL grows without bound inside an episode and nothing brings it
   back.** 16.6 -> 99.5 MB in 25 minutes, monotone, and the only thing that
   reset it was a machine restart (28 KB after). That is consistent with the
   mechanism `scripts/run_loop.py` named on 2026-08-29 and could not test:
   nothing in the repo called `wal_checkpoint`, the automatic PASSIVE
   checkpoint abandons quietly against any reader, and `journal_size_limit`
   was at its default, which lets SQLite keep a checkpointed log at its
   high-water mark rather than shrinking it.
2. **The pass cadence stretched with it**, from ~20s between passes before
   17:32 to 2.6 minutes at 17:46.
3. **A restart is a complete cure and takes ~2 minutes**, RSS included
   (331 MB -> 131 MB, headroom 0.50 -> 1.53 GB).

## What this does NOT establish, and the reasons are separate

- **That the full walk caused it.** Joe opened the desk at almost exactly
  17:32 and stayed on it. The full walk and the arrival of a heavy reader are
  the same minute, and this window cannot separate them. `walk-log` says full
  walks run on their own schedule, so the next unattended one is the control
  that would.
- **That the WAL caused the query slowdown.** Inside the 32,042 KB plateau
  (17:36-17:41) `wal_kb` is byte-constant across five passes while
  `candidate_ms` runs 455 -> 16,799 ms. A regressor with no variance explains
  no variance -- the same verdict the 06:41Z read reached, for the same
  reason, one level up. The bimodality (0.45s passes interleaved with 12-36s
  passes) looks more like contention with a concurrent reader than like a
  monotone WAL effect, and that is a hypothesis, not a finding.
- **That `candidate_rows` is implicated.** It was 164 for the entire window,
  before and after the blow-up.
- **Anything about which of the two named 2026-08-29 mechanisms is real.**
  Neither is convicted here. What has changed is that the log is now bounded
  and every checkpoint attempt records whether a reader blocked it
  (`wal_ckpt_busy`), so the next episode carries the discriminating field
  instead of needing one invented afterwards.

## What was changed on the strength of it

`store.db.checkpoint_wal` plus `PRAGMA journal_size_limit = 0` on writers,
called once per pass from `run_loop.maybe_checkpoint` -- PASSIVE below 32 MiB
and TRUNCATE above it -- with the result written to `loop_rss.jsonl` as
`wal_ckpt_{mode,busy,log_frames,moved_frames,error}` and rendered by
`inspect_live_db loop-rss`. Measured in `tests/test_wal_checkpoint.py`:
with the size limit at its default a PASSIVE checkpoint left a 4,614,432-byte
log at 4,614,432 bytes; with it at 0 the same checkpoint left 4,152.

A successful TRUNCATE reports **zero** frames in both counters (SQLite
3.45.1 zeroes them with the file), so `busy` is the field that says whether
it worked. Reading the frame counts as "it did nothing" is the mistake this
paragraph exists to prevent.
