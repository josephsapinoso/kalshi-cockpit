# The live volume filled, and the diagnosis tooling was inside the failure

**Down:** 2026-08-16 ~19:51Z → 20:45Z, about 54 minutes.
**Cause:** the 1 GB volume reached 100%. `cockpit.db` was 879 MiB of it.
**Fix:** volume auto-extend in `fly.live.toml`. No data deleted.
**Status:** back up, chain runner recording, health check passing.

## What happened

At 19:51Z the chain runner raised `sqlite3.OperationalError: database or disk
is full`. The entrypoint tore the container down, which is exactly what it is
built to do — a dead backend must not leave a container serving frozen prices.
Supervision worked.

On restart the boot got further back each time: `migrate_db.py` runs first and
opens the database for write, so the container died about one second in, every
time, until Fly stopped retrying at its restart cap.

## The part worth keeping

**Nothing on the machine could say what filled the disk.** `inspect_live_db.py`
answers questions about rows; this was a question about bytes. And the
governance rule — `flyctl ssh console` may only invoke a committed, reviewed
script by path — meant the answer had to come from a script, which had to be
run through a shell, which needs a **running machine**. The boot died before
ssh was usable for more than a second.

The tooling for diagnosing the failure was only reachable when the failure was
absent.

Three things were built to break that circularity, in order:

1. **`scripts/inspect_live_disk.py`** — capacity, the file walk, a
   by-extension view, and the largest files. Read-only by construction: no
   unlink, no truncate, no subprocess, and it never opens a file it lists, so
   no row data can reach a transcript through it. Both properties are asserted
   against the source text, because the risk is a path added later.
2. **`MAINTENANCE_HOLD=1`** in `docker/entrypoint.sh` — parks the container
   *before any write*, so the volume mounts and ssh comes up with nothing else
   running. It starts nothing, migrates nothing and deletes nothing. Set in
   `fly.live.toml` and deployed, never as an ad-hoc secret, so a machine in
   maintenance is a committed line someone can find.
3. **`inspect_live_db.py db-sizes`** — stored bytes per btree via `dbstat`,
   plus `freelist_count`, because "the disk is full" does not say whether to
   prune or to buy.

## What the instruments said

```
total        1,021,005,824  973.7 MiB
used         1,021,005,824  973.7 MiB  (100.0%)
free                     0  0.0 B
```

Three files, no stray artefacts, nothing to sweep up:

| file | size |
|---|---:|
| `/data/cockpit.db` | 879.4 MiB |
| `/data/cockpit.db-wal` | 27.8 MiB |
| `/data/cockpit.db-shm` | 64.0 KiB |

`freelist_count = 0` — **a `VACUUM` would have reclaimed nothing.** There was no
wasted space inside the file, only data. (And `VACUUM` rebuilds into a
temporary copy needing roughly the whole file free on the same filesystem, so
at 100% it was not runnable anyway.)

Where the bytes are, from `dbstat`:

| btree | bytes | share |
|---|---:|---:|
| `idx_quotes_ticker_time` | 286.7 MB | 31% |
| `unmatched_events` | 275.6 MB | 30% |
| `kalshi_quotes` | 267.1 MB | 29% |
| `odds_snapshots` | 28.4 MB | 3% |
| `fair_prices` | 23.9 MB | 3% |
| `idx_unmatched_open` | 10.7 MB | 1% |

Two things fall straight out:

- **`kalshi_quotes` plus its index is 553.8 MB — 60% of the file.** That is the
  observational record and it is supposed to be large. Note the index is
  *bigger than the table it indexes*.
- **`unmatched_events` plus its index is 286.3 MB — 31%**, and
  **nothing anywhere prunes it.** It is the work queue of things the linker
  refused to match, with a `resolved` flag, a free-text `reason` sentence per
  row, and no retention rule in any module. A diagnostic queue is a third of
  the production volume.

## The fix, and why this one

**Extend, do not delete.** Deleting rows is irreversible and 60% of the file is
the record itself. Disk costs about 15 cents per GB per month; deleting the
wrong rows costs the measurement. So `fly.live.toml` gained:

```toml
auto_extend_size_threshold = 80
auto_extend_size_increment = "1GB"
auto_extend_size_limit     = "5GB"
```

Threshold 80 rather than 90 because SQLite needs headroom it does not appear to
be using — a write extends the WAL first, and the repair path needs the file
size free. A volume that only extends at 90% can still be unable to run its own
repair.

Verified after deploy: **974 MiB → 1.9 GiB, free 0 → 967 MiB, 51% used.** The
hold came off and the runner resumed.

## A self-inflicted second outage, worth recording

The fix for the outage caused a second one. Editing `docker/entrypoint.sh` with
a direct file write left CRLF line endings in the working tree. `fly deploy`
sends the **working tree** as the build context, so the container got
`#!/usr/bin/env bash\r` and died with `env: 'bash\r': No such file or
directory`, exit 127.

This repo already had `.gitattributes` forcing `eol=lf` on `docker/*`, and
already had a lesson about exactly this shebang failure. Both guards held —
git stored LF throughout and `git status` was clean the whole time, because it
compares against the normalised blob. The bytes on disk were never checked.

## What this does not establish

- **Nothing about why the record grew when it did.** One reading is a level,
  not a trend. No growth rate was measured, so "when does 5 GB run out" is
  unanswered.
- **Nothing about what may be pruned.** `unmatched_events` at 31% is a
  candidate on size; whether those rows are still useful is a separate
  decision that nobody has made, and size is not expendability.
- **Nothing about whether 5 GB is the right ceiling.** It is a number chosen to
  be a real limit rather than a formality. If it is reached, the answer is to
  find what lacks a retention rule, not to raise it.
- **The 54-minute figure is downtime, not data loss.** How many closing lines
  and candlesticks were missed in that window is unmeasured, and candlesticks
  age out — some of it is not recoverable.
