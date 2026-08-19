# The health flap is the proxy hop, and the backend was never failing

Measured on the live machine (`7812601a239428`, `86b91df`) 2026-08-19
13:41-14:20Z, with the betting window closed.

**What this establishes.** That Fly's health check fails because the connection
Next pools to uvicorn is closed by uvicorn before the next check reuses it, and
not because anything is slow, saturated, or out of memory.

**What it does not.** It does not explain the 2026-08-19 01:51-02:09Z outage —
**18 minutes of consecutive 30s timeouts is a different phenomenon** from a
15-23s flap that self-clears, and nothing here should be read as closing that.
It also does not measure Next's own outbound pool timeout, which is the other
end of the race and is not configured anywhere in this repo.

## The observation

Three health check failures in the hour to 14:00Z, each self-clearing:

```
13:08:40 failed -> 13:09:03 passing   (23s)
13:45:07 failed -> 13:45:25 passing   (18s)
13:59:05 failed -> 13:59:20 passing   (15s)
```

accompanied in the app log by

```
Failed to proxy http://127.0.0.1:8000/api/health Error: socket hang up
code: 'ECONNRESET'
```

## The standing explanation, and why it is wrong

Every previous session attributed this to CPU saturation from long passes: the
quote pass took 27-77s on a 15s cadence, `runner.py:1977` records it as having
"starved uvicorn of the CPU", and full passes are currently 90-126s because
ADR 0054 put the prune inside them.

**Two of the three failures happened while no pass was running at all.**
Reconstructing pass windows from `took_s`:

| pass ended | `took_s` | so it ran |
|---|---:|---|
| 13:11:00 | 122.4 | 13:08:58-13:11:00 |
| 13:27:59 | 90.9 | 13:26:28-13:27:59 |
| 13:46:11 | 126.1 | 13:44:05-13:46:11 |

The 13:08:40 failure **began 18 seconds before its pass started**. The 13:59:05
failure sits in the idle gap between the 13:46:11 pass and the next one at
~14:01. Only 13:45:07 falls inside a pass, which is roughly what three coin
flips against a box that is busy ~12% of the time would give anyway.

## The backend was answering the whole time

50 probes of `http://127.0.0.1:8000/api/health` on the box, 5s apart,
14:00:43-14:04:58, alongside `/proc/pressure/io`:

```
50 of 50 succeeded.  worst 1621ms, median 3ms, 44 of 50 under 130ms.
io full avg10 over the same window: 0.76 -> 90.40 (peak), never below 0.85
```

**IO pressure genuinely is severe** — 90% means the whole machine was stalled on
IO — and the backend served every request through it. Memory was not close:
`/proc/pressure/memory` full avg300 = 0.22.

So the thing Fly marks unhealthy on port 3000 is healthy on port 8000, at the
same moment, under the load that was supposed to be the cause.

## The mechanism, tested directly

`[checks.health]` targets **port 3000** — Next — every **15s** on live and
**30s** on demo, with a 5s timeout. Next proxies to uvicorn over a pooled
connection. uvicorn's `--timeout-keep-alive` defaults to **5 seconds** and the
entrypoint did not override it, so the pooled socket is always closed before the
next check arrives.

Driving the proxy on port 3000 over one reused connection, on the live box:

| gap between requests | failures |
|---|---|
| **15s** (Fly's live interval) | **5 of 10** |
| **3s** (inside the 5s keep-alive) | **0 of 10** |

The 15s failures land on requests 1, 3, 5, 7 and 9 — **perfectly alternating**.
That is the signature and it is what makes this diagnosis different in kind from
the three before it: a reused socket dies, the client reconnects, the fresh
socket succeeds, the next reuse dies. Nothing that is merely *slow* alternates.

n = 10 per arm, and the arms are 5/10 against 0/10 — Fisher two-sided
p = 0.033. Small, but the alternation is a mechanism, not an effect size, and
the mechanism is reproducible on demand.

## THE FIRST FIX WAS THE WRONG HOP, AND DEPLOYING IT IS HOW THAT WAS FOUND

The measurement above is correct and the conclusion drawn from it was not.
Because the app log named port 8000 — `Failed to proxy
http://127.0.0.1:8000/api/health` — uvicorn was assumed to be the process
closing early, and shipped with `--timeout-keep-alive 75`.

**Demo, running that fix, still failed 5 of 10.** Same 15s spacing, same
alternation:

```
demo @ dd480bd, KEEP_ALIVE unset, uvicorn --timeout-keep-alive 75
  15s gap   .X.X.X.X.X   5 of 10
  30s gap   .X.X.X       3 of 6     (demo's own check interval)
```

**There are two hops and both defaulted to 5 seconds.** Fly's edge pools a
connection to **Next on 3000**; Next pools a separate one to **uvicorn on
8000**. The test above connects to port 3000, so what it measured all along was
*Node's* `server.keepAliveTimeout` — 5s by default — and not uvicorn's at all.
The uvicorn flag fixed a real second instance of the same bug, which is what the
proxy error line was reporting, but it was never the one Fly trips over.

The correction is recorded rather than folded away because the reasoning that
produced it reads as sound: an error message naming a port is evidence about
that hop and about nothing else. **Fixing the hop an error names is not the same
as fixing the hop that is failing.**

## The fix, both halves

| hop | setting | value | bound |
|---|---|---|---|
| Fly edge -> Next :3000 | `KEEP_ALIVE_TIMEOUT` (ms) | **50000** | must clear the check; must stay under Node's 60s `headersTimeout` |
| Next -> uvicorn :8000 | `--timeout-keep-alive` | **75** | must outlive Next's, so the inner hop never hangs up first |

Next's standalone `server.js` reads `KEEP_ALIVE_TIMEOUT` and passes it to
`startServer`, which sets `server.keepAliveTimeout` **and nothing else**
(`start-server.js:248`) — `headersTimeout` stays at Node's 60s default, so this
value has a ceiling as well as a floor.

The floor is `interval + timeout + 10s`, absolute rather than a ratio: what has
to be absorbed is one *late* check, and lateness does not scale with the
interval. Live needs 30s, demo needs 45s, both have 50s.

`tests/test_keepalive_outlives_health_check.py` reads every interval and timeout
out of every `fly*.toml` and checks both hops against them, so no single number
can be changed alone. Nine breakages applied and watched go red: Next's setting
removed (5 fail), at Node's default (3), 35s which clears live but not demo (1),
90s past `headersTimeout` (2), uvicorn's flag removed (4), uvicorn dropped below
Next (1), a check interval raised (2), the check moved to port 8000 (1), and a
demo interval large enough that the floor crosses the ceiling (2).

## What this predicts

Health check failures on live should stop. If they continue at ~3/hour after
this ships, the alternation measured here is real but is not what Fly trips
over, and this explanation joins the other three.

**It should not change `took_s`, any `leg_*_ms`, or the prune.** If it appears
to, something other than these two settings went out with it.

Verify the same way it was found — on the box, over one reused connection, at
the deploy's own check interval. A green `flyctl checks list` is a single
sample against a bug that fails every *other* request.
