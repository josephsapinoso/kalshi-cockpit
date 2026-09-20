# The 882 MB nobody owned is ext4's root reserve — 2026-09-20 ~23:50Z

Ticket #94, story #92. A confirmation-seeking reading against a numeric
prediction, not an open-ended probe: story #92 predicted that the gap between
what `df` charges to `/data` and what a file walk can see is the filesystem's
root reservation, fixed and non-recoverable, and therefore irrelevant to the
volume's growth clock.

**Verdict: confirmed. The gap is the reserve, to within 75,050 bytes (0.0085%).
Story #92 closes, and the "882 MB might be recoverable" idea is dead.**

## Instrument

`scripts/inspect_live_disk.py`, run inside the container by path over
`flyctl ssh console` (`python /app/scripts/inspect_live_disk.py`), per the
committed-script rule. Stdlib only, `statvfs` only — it shells out to nothing,
`tune2fs` included. Live `git_sha` at read time: `3699593`.

`flyctl ssh` printed `Error: The handle is invalid.` and exited 1 *after* a
complete read. That is the recorded lie, not a failure.

## The reading

```
# disk  (/data)

total       21,103,947,776  19.7 GiB
used         8,586,477,568  8.0 GiB  (40.69%)
free        12,517,470,208  11.7 GiB

walked       7,704,124,118  7.2 GiB  in 8 files
unaccounted    882,353,450  841.5 MiB
reserved       882,278,400  841.4 MiB

largest file  /data/cockpit.db   7,697,891,328   7.2 GiB
```

    unaccounted - reserved = 75,050 bytes  (73.3 KiB, 0.0085% of the reserve)

## Predicted vs observed, side by side

| | predicted (story #92) | observed |
|---|---|---|
| what holds the gap | ext4 root reserve | ext4 root reserve — **confirmed** |
| the reserve's size | "~1.0 GiB of 5% reserve" | 882,278,400 B = 841.4 MiB |
| the reserve as a fraction of `f_blocks` | 5% (ext4's default) | **4.18%** |

**The structural claim was right and the percentage was wrong.** The volume is
not carrying ext4's 5% default; it is carrying 4.18% (215,400 reserved blocks
of 5,152,331 at 4,096 B). The prediction was already internally loose — 5% of
19.7 GiB is 1,008 MiB, not the 841.5 MiB the same sentence called it "close
to" — so the arithmetic that agreed was the gap-equals-reserve identity, not
the percentage. Nothing here establishes *why* it is 4.18%; this module reads
`statvfs` and does not ask `tune2fs`.

## Why the match is not circular, and where it is

Half-circular, and the honest statement of which half is the point of the
reading.

`capacity()` computes `free` from `f_bavail`, which **excludes** the root
reserve, and then `used = total - free`. So the reserve is charged to `used`
by construction, and `unaccounted = used - walked` therefore contains the
reserve by construction too. That part is arithmetic, not evidence.

What the reading *does* discriminate is everything else that could have been
in there. Had ~882 MB been held by a deleted-but-still-open file — the
hypothesis the 36th session tested and refuted on a 342-byte drift across a
restart — `unaccounted` would have come in at reserve **plus** that file,
about 1.72 GB. It did not. The residual is 73 KiB across eight files, which is
the expected size of `st_size` (what the walk sums) disagreeing with allocated
blocks (what `df` charges). **No unseen holder of consequence exists on
`/data`.**

## What this does not establish

- **Nothing about the growth clock.** This is one level, not a rate. `/data`
  is 40.69% used with `cockpit.db` at 7.2 GiB; whether that is weeks or months
  of headroom is #58's question and is Joe's to answer.
- **Nothing about the reservation staying put.** 4.18% is what the filesystem
  reports today. A reformat or a `tune2fs -m` would move it, and this module
  cannot see either.
- **Nothing about SQLite's ability to write.** Free space is not a successful
  write: a full WAL, a read-only mount or a quota each fail with bytes to
  spare.
- **Nothing about the container root.** This reads `/data` only. The ~15-day
  VACUUM window #58 turns on is a property of the container root filesystem,
  which is a different device and is not measured here.
