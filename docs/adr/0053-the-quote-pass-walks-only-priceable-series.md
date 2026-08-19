# 0053 — The quote pass walks only priceable series

Date: 2026-08-19
Status: accepted

## Context

The live instance was hard down for 18 unbroken minutes on 2026-08-19 and had
been failing roughly half of all heartbeat checks for a day. Nine alarms reached
Joe's phone before anyone acted on them.

The cause is in `run_kalshi_pass`, which every quote pass runs on a **15-second**
cadence while a betting window is open:

```
raw_events = [e async for e in kalshi_client.events(with_nested_markets=True)]
```

That paginates Kalshi's whole open catalogue. Measured against the real API on
2026-08-19: **11,160 events carrying 96,326 nested markets**, to find **~510**
priceable ones, of which `run_pricing_pass` links and prices about **70**.

On live's `shared-cpu-1x` the pass took 27 → 36 → 36 → 52 → **77** seconds
against its 15-second cadence. uvicorn shares that one vCPU, so it missed Fly's
5-second health check, Next logged `Failed to proxy 127.0.0.1:8000/api/health —
socket hang up`, and the GitHub heartbeat timed out at 25 seconds.

Full evidence, including the two theories that were refuted first, is in
`docs/measurements/2026-08-19-quote-pass-cost-attribution.md`.

## Two fixes were rejected before this one

**Raising `RUNNER_FAST_INTERVAL_S`** — proposed to Joe and wrong.
`scripts/run_loop.py:301` refuses to start when
`fast_interval × 1.15 + 8 > MAX_KALSHI_QUOTE_AGE_S`, i.e. above about **19s**.
Setting 60 would have stopped the recorder, not slowed it.

**Fetching the ~70 linked events individually** via `markets_for_event` — the
obvious fix, and worse. It is **more requests than pages** (70 vs ~56) against
`_RateLimiter`, a shared minimum-interval lock at 8/s that serialises them, so
`asyncio.gather` buys nothing. Caught by reading the limiter rather than by
shipping it.

## Decision

`run_kalshi_pass` takes `series_tickers`. When supplied it walks
`/events?series_ticker=…` once per series instead of the whole catalogue. The
**quote pass** supplies it; the **full pass** does not.

Measured on the same API session that produced the diagnosis:

| walk | time | events | markets |
|---|---:|---:|---:|
| full catalogue | **15.21 s** | 11,160 | 96,326 |
| 19 scoped walks | **3.13 s** | 573 | 6,917 |

**4.9× faster, and the saving is bytes rather than requests** — 19 scoped calls
against ~56 pages. Coverage was checked in the same run: every priceable event
the full walk found was also found by the scoped walks, plus one that listed
between the two.

**The full pass keeps the full walk, and must.** A narrowed walk can only re-see
series it already knows, so something has to look at the whole catalogue or a
newly-listed league is invisible forever. That job now runs every 900 s instead
of every 15 s.

**The cost, stated:** a series that appears between full passes is discovered up
to 900 s later instead of up to 15 s later. That is inside the 900 s odds
window, so no row that could have been bet is lost by it.

### Where the series list comes from

`priceable_series(conn, now)` — `SELECT DISTINCT series_ticker FROM
kalshi_events WHERE last_seen_ms >= now - 1800000`.

**Read from `kalshi_events`, not `event_links`.** That was the first instinct
and it is wrong: a link exists only where a fixture *matched* a sportsbook
event, so the set would collapse to the handful of game-level series linked at
that moment and silently stop quoting every prop, spread and total series.
`kalshi_events` holds exactly what `discover_from_events` classified as
priceable, so there is no second definition of "priceable" here that can drift
from discovery's.

**Two full passes of recency, not forever.** One interval would drop every
series in the gap between a full pass writing and the next quote pass reading.
Unbounded would walk a finished season's series every 15 seconds for the life of
the instance — the same unbounded-growth shape as the query that took the box
down on 2026-08-18.

**An empty set walks everything.** A fresh volume knows no series; fetching
nothing there would report a quiet slate, which is indistinguishable from a
quiet market.

## Verification

Suite 3,468 passed / 10 xfailed; ruff clean. Six new guards in
`TestTheQuotePassWalksOnlyPriceableSeries`, each disabled and watched go red.

**Two of them were green when first written**, and both are recorded because
the second was subtle:

- `FakeKalshi` accepted `series_ticker` and ignored it. Every assertion still
  passed, because the returned event list is identical either way — which is
  exactly the regression that would put the 15-second catalogue walk back
  without changing a visible number. The fake now filters, and that filter is
  load-bearing.
- The test written to make it load-bearing asserted on the **discovered**
  events, and was *also* green under that mutation: discovery drops an
  out-of-scope series either way, so nothing downstream of it can distinguish a
  narrowed fetch from a wide one. The assertion is now on what the client
  actually handed over, which is the quantity the change reduces.

## What this does not fix

**The disk.** `kalshi_quotes` is ~two thirds of an 879 MiB file on a 2 GB volume
that filled once already (2026-08-16), and this change does not shrink it: the
quote store iterates *priceable* events (~510), not the catalogue, so it wrote
~7,148 rows a pass before and writes about the same now. Narrowing what is
stored is a change to the record's population and needs its own decision.
Keeping the two apart matters — the writes measured **0.17 s** and are not the
latency problem.

**The guard that should have caught this.** `QUOTE_PASS_DURATION_BUDGET_S = 8.0`
is an assumption about how long a pass takes, and it was off by roughly 10×
against reality for an unknown length of time. It validates the *configured
interval* and never the *observed* duration, so the loop happily ran a 77-second
pass on a 15-second cadence while logging a warning nobody was reading. Left
open.
