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

## The fix

`--timeout-keep-alive 75` in `docker/entrypoint.sh`, clearing live's 15s and
demo's 30s with margin. Margin rather than a bare inequality because both ends
are timers and the box demonstrably stalls on IO for seconds at a time.

`tests/test_keepalive_outlives_health_check.py` reads the interval out of every
`fly*.toml` and compares it to the flag, so the relationship cannot silently
break when either number is changed alone. Six ways of breaking it were applied
and watched go red: flag removed (5 fail), flag at uvicorn's default (5), 20s
which clears live but not demo (3), 31s which ties demo (1), live's interval
raised past the flag (2), and the check moved to port 8000 (1).

## What this predicts

Health check failures on live should stop. If they continue at the same ~3/hour
after this ships, the alternation measured above is real but is not what Fly is
tripping over, and this explanation joins the other three.

**It should not change `took_s`, any `leg_*_ms`, or the prune.** If it appears
to, something other than the keep-alive flag went out with it.
