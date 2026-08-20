# The ~585 MB is a level set by the first full pass, not a climb

Taken 2026-08-20 19:37Z–20:21Z, the first observation the open item ("what
holds the ~585 MB is still unverified") has ever had. Instrument:
`scripts/inspect_live_proc.py` (new, `a41f20e`, read-only `/proc` reader),
sampled every ~45s across three full passes on a freshly booted machine
(the 19:31Z deploy restart). Raw samples committed beside this file
(`2026-08-20-rss-samples-run{1,2}.jsonl`); pass stamps from `sweep-log`.

## The observation

`run_loop.py`'s RSS, 54 samples, changes only:

```
19:37:54   607.1 MiB   <- first full pass (19:37:01) already complete
19:38:41   582.8 MiB   <- settles
  ... 17 minutes dead flat at 582.8 ...
19:55:31   643.6 MiB   <- full pass 2 (19:54:44)  +60.8
  ... flat ...
20:09:01   600.3 MiB   <- full pass 3 (~20:09)
20:09:48   588.5 MiB   <- settles                 -55.1
  ... flat to 20:21 ...
```

uvicorn sat at 166.2–166.4 MiB throughout; nothing else moved.

## What this establishes

- **The level is built by the FIRST full pass after boot** — 583 MiB was
  already resident within ~50s of the pass completing — and is then flat to
  the sample resolution between passes. The registered falsification
  direction holds: memory moves at full passes and at nothing else
  (17-minute flat stretches between them).
- **It is not a leak on this horizon.** Three passes moved the level
  +61 then −55: a breathing band of roughly 583–644 MiB, not a monotonic
  climb. The 2026-08-19 OOM arithmetic should treat ~644 MiB as the loop's
  working ceiling per pass, not 583 as its budget.
- **The quote-pass half is untested tonight** — the window was closed, so
  no quote passes ran. The between-pass flatness is the closed-window
  equivalent and is consistent with the claim, weaker than observing it.

## What this does not establish

- **What the bytes hold.** RSS is a size, not an inventory
  (`inspect_live_proc.py`'s own docstring). The first-pass timing is
  consistent with the suspected `raw_events = [e async for e in ...]`
  materialisation in `run_kalshi_pass` — a full pass with no
  `series_tickers` walks the whole catalogue into one list — but a heap
  profile, not an RSS trace, is what would name it. Streaming that list is
  the candidate fix if the level ever matters; at 2 GB with ~1 GB
  MemAvailable it currently does not.
- **Nothing about growth over days.** 45 minutes and three passes. The
  2026-08-19 OOM was a different regime (memory starved by the prune
  backlog); this measurement is of the healthy machine.
