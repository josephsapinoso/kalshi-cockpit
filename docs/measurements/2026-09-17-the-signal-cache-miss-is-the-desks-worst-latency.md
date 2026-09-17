# The `/api/signal` cache miss is the desk's worst measured latency, and the sweep that should have found it was hiding it

**Date:** 2026-09-17
**Instrument:** `scripts/time_live_routes.py` (per-rep maxima, added 2026-09-17)
and a single-route probe, both GETs with a minted session cookie.
**Cost:** zero odds credits. Attention is stamped only by
`POST /api/desk/attention`; these are GETs.

## What this establishes, and what it does not

**Establishes:** that `/api/signal` costs seconds rather than milliseconds on a
cache miss, that the miss recurs on a fixed 300 s cycle, and that both `/board`
and `/slate` block on it in their server components.

**Does not establish:** the miss cost under load, on a warm-vs-cold box
systematically, or with more than a handful of misses observed. Four slow
observations total. It does **not** establish that this has ever caused a
user-visible failure — no `read_budget` incident names this route. And every
timing here is taken from one client over the public internet, so a slow rep
could in principle be the network; the 300 s periodicity is what argues it is
not.

## The observation that started it

`time_live_routes.py` kept only `min` and `median` until 2026-09-17 and
discarded the per-rep vector. On its first run with maxima:

    /api/signal   med    108 ms    MAX  13,475 ms     (3 reps, 2026-09-16 ~23:0xZ)
    /api/signal   med    108 ms    MAX  13,776 ms     (5 reps, 2026-09-17 10:2xZ)

Two observations ~300 ms apart in value, on different days, on **different box
sizes** (2 GB then 4 GB). That is not the signature of a network hiccup.

## Ruling out the obvious, then finding the cause

A 40-rep single-route probe at 3 s spacing returned **max 162 ms, zero slow
reps.** Taken alone that reads as "cannot reproduce" — and it is the wrong
conclusion, because the probe ran entirely inside a cache window the earlier
sweep had just populated. Zero events in 40 draws bounds the rate no tighter
than 7.5% (rule of three), which is the honest reading and is not reassuring.

The cause is in the source, not the timings.
`backend/api/routers/status.py`:

    SIGNAL_CACHE_TTL_MS = 300_000
    _signal_cache: dict[str, object] = {}

`_cached_signal_report` recomputes on a miss via `report_from_connection`. The
module's own docstring says what that costs: the registered extraction *"scans
`recommendations` and runs one correlated subquery into `kalshi_quotes` per
surviving row"*, and `kalshi_quotes` is roughly two thirds of the file.

**So the median is the cache hit and the maximum is the cache miss.** They are
two different operations, and reporting their median describes neither.

## The prediction, and the test of it

If the cause is the TTL, then waiting it out must produce a slow rep on demand.
Cache last populated ~10:26Z; probed at 10:32:14Z:

    rep 0  10:32:14Z    5,231 ms   <-- SLOW
    rep 1  10:32:21Z    3,101 ms   <-- SLOW
    rep 2  10:32:26Z      106 ms
    rep 3  10:32:28Z       77 ms
    rep 4  10:32:30Z       99 ms
    rep 5  10:32:33Z      113 ms

Confirmed on demand.

**Two slow reps, not one, and that is a second finding.** `_signal_cache` is
**module state in one process**. A second worker process holds its own empty
cache, so the first request to each worker pays the join. The number of slow
requests per TTL window is therefore the number of workers, not one.

The cost varies widely with page-cache residency: 3.1 s to 13.8 s across the
four observations. The 13.8 s figure is **55% of the 25 s read budget**
(ADR 0135).

## Why nobody had seen it, and it is this instrument's own documented flaw

`time_live_routes.py` iterates `APIS + PAGES`. `/api/signal` is timed fourth;
`/board` and `/slate` are timed near the end. **So the sweep warms the signal
cache and then times the two pages that depend on it.** Those page figures are
not first-tap costs.

That is not a new discovery — it is written in the module's own
"what this does not establish" section, added the same day:

> Page figures are measured in the most favourable possible order, since
> `APIS` runs before `PAGES` and warms each page's own read path immediately
> before it is timed.

The caveat was correct and the sweep was still read as covering the pages. A
caveat that is true, documented and ignored is worth as much as an absent one.

## Why it reaches Joe

    frontend/src/app/board/page.tsx:62   signal = await fetchSignal().catch(() => null);
    frontend/src/app/slate/page.tsx:113  signal = await fetchSignal().catch(() => null);

Both are `force-dynamic` server components and both **await** it. So a page
load that lands on an expired cache blocks on the recompute. `/board` and
`/slate` are the two most-visited screens.

The `.catch(() => null)` means a failure degrades rather than breaks — the
page renders without the signal block. It does not time-bound the wait.

## What is NOT claimed

- **No production incident names this route.** `api_read_incidents`' recorded
  `read_budget` rows are `/api/slate?league=...` and `/api/parlays`. This has
  never been observed to breach the ceiling.
- **The 4 GB box does not fix it and was not bought for it.** The 13,776 ms
  observation is *from the 4 GB box*, after the scale. A bigger cache should
  reduce the miss cost, and the two largest observations sit on either side of
  the change, so nothing here separates them.
- **No fix is proposed here.** Precomputing on the recorder's cycle, sharing
  the cache across workers, or serving the page without awaiting it are all
  changes with their own trade-offs, and the docstring's reason for the 300 s
  TTL (`beta` moves at most once per market close) is still sound.

## The reason this is worth a document

It is the first measured tail this repo has. It exists only because an
instrument stopped throwing away its maxima the day before, and the first run
after that change found a number at 55% of a ceiling on the desk's busiest
screen. The previous session concluded from medians that the read budget's
trigger was "measured false"; a skeptic pass refused that, and this is what the
refused conclusion was covering up.
