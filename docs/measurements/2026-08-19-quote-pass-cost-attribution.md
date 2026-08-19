# Where the quote pass spends its time — and an 18-minute live outage

Date: 2026-08-19
Status: diagnosis complete, fix not shipped

## What happened

Joe pasted the Discord channel. Alongside the heartbeat test he had asked for,
it held **eleven alarms he had not**: nine `The cockpit is not answering` from
the GitHub heartbeat and two `Cockpit API unreachable` from the loop's own
in-process check, spread across the day.

I had spent the session reporting live as healthy, on `curl` probes that
happened to land in the gaps.

A 5-second poller settled it:

```
probes 302   ok 229   timeouts 71     01:51:18Z -> 02:22:00Z
71 consecutive 30s timeouts   01:51:18Z -> 02:09:10Z   (18 minutes, hard down)
machine restarted             ~02:09:20Z
229 consecutive ok            02:09:39Z -> 02:22:00Z   (128-1835 ms)
```

`flyctl checks list` reported `critical — context deadline exceeded (Client
.Timeout exceeded while awaiting headers)` while my own `curl` was returning
200 in 0.14s. Both were true minutes apart.

## The mechanism, from the container's own log

```
pass 2 (quote): took_s 27.1   markets_quoted 7148
pass 3 (quote): took_s 36.4   markets_quoted 7148
pass 4 (quote): took_s 35.9   markets_quoted 7150
pass 5 (quote): took_s 52.5   markets_quoted 6911
pass 6 (quote): took_s 77.1   markets_quoted 6911

Failed to proxy http://127.0.0.1:8000/api/health  Error: socket hang up (ECONNRESET)
Health check 'health' on port 3000 has failed.
```

The quote pass is configured to run every **15 seconds**. It was taking up to
**77**. `shared-cpu-1x`, 1 GB, with uvicorn, Next and the loop on one vCPU: the
loop saturates it, uvicorn misses Fly's 5-second check, the machine is marked
unhealthy, and the GitHub heartbeat's 25-second cutoff times out.

## Cost attribution — two wrong theories, killed by measurement

**Theory 1: the 7,148 inserts per pass.** Measured with the real schema, real
indexes and the real functions, at increasing table sizes
(`scratchpad/measure_pass_cost.py`):

| pass | rows before | `upsert_discovered` | `store_quotes_from_discovery` | total |
|---:|---:|---:|---:|---:|
| 1 | 0 | 0.05 s | 0.02 s | 0.07 s |
| 10 | 64,350 | 0.06 s | 0.02 s | 0.08 s |
| 20 | 135,850 | 0.04 s | 0.07 s | 0.11 s |
| 30 | 207,350 | 0.04 s | 0.09 s | 0.13 s |
| 40 | 278,850 | 0.04 s | 0.13 s | **0.17 s** |

Roughly 14,000 SQL statements per pass cost **0.17 s** at 279k rows. It grows,
but from nothing to nothing. **Refuted.**

**Theory 2: parsing the catalogue.** `discover_from_events` over
`tests/fixtures/events_sports_nested.json` (32 events, 245 markets) takes
**1.3 ms**; scaled to live's ~11,191 events that is **0.46 s**. **Refuted.**

**What is left is the HTTP walk.** `run_kalshi_pass` calls
`events(with_nested_markets=True)`, which paginates `/events` at
`DEFAULT_PAGE_LIMIT = 200`. Live discovery reports `541 priceable;
not_game_level=8108, league_out_of_scope=2542` — about **11,191 events, so ~56
pages**, each carrying nested markets. At `DEFAULT_RATE_LIMIT_PER_SECOND = 8.0`
the limiter alone floors it at ~7 s; the rest is transfer and TLS on a
throttled shared vCPU. 26–76 s is exactly the residual.

**The waste ratio is ~160:1** — about 11,000 events fetched every 15 seconds so
that `run_pricing_pass` can link and price roughly **70**
(`events_linked: 66–72`, `fair_prices_written: 30`).

## Why it is intermittent

`Scheduler.interval()` returns the fast interval **only while a window is
open**. Windows follow kickoffs, so the box melts during them and recovers
between. The recorder age climbed steadily to 753 s after the 02:00Z WNBA
kickoff closed the window — the calm is the loop idling at the 900 s cadence,
not the problem being fixed.

## The obvious fix is worse, and the limiter is why

Fetching the ~70 linked events individually via `markets_for_event` looks
cheaper — small responses, no pagination. It is **more requests than pages**
(70 vs ~56) against a shared minimum-interval limiter that serialises them, so
`asyncio.gather` buys nothing. Not shipped, and recorded here so it is not
re-proposed.

The direction that survives: walk `/events?series_ticker=…` for only the
series that carry priceable leagues — a handful of requests instead of 56 —
leaving the full catalogue walk on the 900 s pass.

## The second, slower problem

`routes.py:2936` records `kalshi_quotes` as "roughly two thirds of an 879 MiB
file on the live volume". The volume is **2 GB**, and it filled once already
(2026-08-16). At 7,148 rows per pass every 15 s during an open window, that
table grows by millions of rows a day — and **every reader joins it by ticker
to a market that produced a recommendation** (`clv_signal.py:143`,
`slate.py:232`, `runner.py:592`). Quotes for the ~7,000 markets that are never
priced are read by nothing.

Narrowing what is stored is therefore both the disk fix and a change to the
record's population, and it needs its own decision. It is **not** the latency
fix — the measurements above show the writes cost 0.17 s.

## What this does not establish

The cost attribution is by elimination, not by profiling the live process: two
candidates were measured on a laptop SSD and found negligible, and the residual
was attributed to the network. A direct timing of the paginated walk inside the
container would be better evidence and was not taken — `flyctl ssh console` is
refused by the permission classifier here.

Nothing here establishes that the proposed fix works. It has not been built.
