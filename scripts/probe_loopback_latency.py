"""Time uvicorn, Next's proxy and Next alone from inside the box, invoked by path.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/probe_loopback_latency.py --seconds 300"

Why this file exists
--------------------
#193: about 1 in 20-40 public requests to the live desk takes a fixed ~3.1 s
where the rest take ~100 ms. `curl -w` from outside puts the 3 s after the TLS
handshake, so it is on the server side of the edge. It hits `/api/health`,
`/api/signal` (a cache hit that runs no SQL) and a 404 page that Next answers
without calling the backend, all at the same rate
(`docs/measurements/2026-09-28-a-fixed-3-second-stall-sits-upstream-of-uvicorn.md`).
The recorder's own loopback probe of uvicorn (`run_loop.HEALTH_URL`, 2 s
threshold, every pass) has never recorded a slow answer.

That leaves two hops: Fly's proxy into the machine, and Next's server on
:3000. Only a reading taken inside the box can separate them. This makes one
GET a round against each of three fixed targets, all on loopback:

    uvicorn     http://127.0.0.1:8000/api/health   the backend, direct
    next-proxy  http://127.0.0.1:3000/api/health   Next's rewrite proxy to it
    next-only   http://127.0.0.1:3000/login        Next alone, no backend call

- **Stalls on `next-*` but not `uvicorn`:** the stall is in Next.
- **Stalls on none of them:** the stall is in Fly's proxy hop, which this box
  cannot see.

Three structural properties
---------------------------
**A mutation is unrepresentable.** The one network call is
`urllib.request.urlopen(url, timeout=...)` with a bare string and no `data`,
which the stdlib defines as a GET. No method argument exists anywhere.

**The targets are constants.** No argument or environment variable names a
URL, a host, a port or a path, so the script cannot be pointed at anything
but these three loopback URLs. There is nothing to allowlist, because nothing
is supplied.

**It is bounded.** `--seconds` is capped at 900 and `--interval` floored at
0.25 s, so one invocation sends at most ~10,800 tiny requests. It reads no
file and writes nothing: no database, no disk, no subprocess.

What this does not establish
----------------------------
- **Nothing about Fly's edge.** A clean run here says the stall is upstream of
  the machine. It does not say where, and nothing on this box can.
- **Fresh connections, not pooled ones.** `urlopen` opens a new TCP
  connection per request. Fly's proxy reuses pooled connections into :3000,
  so a stall that lives only in connection reuse will not show here. That
  result would itself point at the reuse path.
- **Nothing about load.** One client, sequential, a few requests a second.
- **Nothing about the cause inside a hop.** It names the hop, not the timer.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Fixed, loopback-only, and read from nowhere else (see the docstring).
TARGETS: tuple[tuple[str, str], ...] = (
    ("uvicorn", "http://127.0.0.1:8000/api/health"),
    ("next-proxy", "http://127.0.0.1:3000/api/health"),
    ("next-only", "http://127.0.0.1:3000/login"),
)

TIMEOUT_S = 30.0
MAX_SECONDS = 900
MIN_INTERVAL_S = 0.25


def timed_get(url: str, *, opener=urllib.request.urlopen, clock=time.perf_counter):
    """One GET: (status or None, elapsed ms, error class name or None).

    An HTTP error status is a completed answer and keeps its status. A
    connection failure or timeout has no status and says which it was.
    """
    started = clock()
    status: int | None
    error: str | None = None
    try:
        with opener(url, timeout=TIMEOUT_S) as resp:
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, OSError) as exc:
        status, error = None, type(exc).__name__
    return status, (clock() - started) * 1000, error


def percentile(sorted_ms: list[float], q: float) -> float | None:
    """Nearest-rank percentile of an ascending list. `None` when empty."""
    if not sorted_ms:
        return None
    rank = max(1, min(len(sorted_ms), math.ceil(q * len(sorted_ms))))
    return sorted_ms[rank - 1]


def summarise(samples: dict[str, list[float]], slow: list[dict], errors: dict[str, int]) -> dict:
    out = {}
    for name, _ in TARGETS:
        ms = sorted(samples.get(name, []))
        out[name] = {
            "n": len(ms),
            "slow": sum(1 for s in slow if s["target"] == name),
            "errors": errors.get(name, 0),
            "p50_ms": percentile(ms, 0.50),
            "p95_ms": percentile(ms, 0.95),
            "max_ms": ms[-1] if ms else None,
        }
    return out


def run(
    seconds: float,
    interval_s: float,
    slow_ms: float,
    *,
    get=timed_get,
    monotonic=time.monotonic,
    sleep=time.sleep,
    stamp=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    echo=lambda line: print(line, flush=True),
) -> dict:
    """Round-robin the targets for `seconds`, echoing every slow answer."""
    samples: dict[str, list[float]] = {name: [] for name, _ in TARGETS}
    slow: list[dict] = []
    errors: dict[str, int] = {}
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        for name, url in TARGETS:
            at = stamp()
            status, ms, error = get(url)
            if error is not None:
                errors[name] = errors.get(name, 0) + 1
            else:
                samples[name].append(ms)
            if error is not None or ms >= slow_ms:
                row = {"at": at, "target": name, "status": status, "ms": round(ms), "error": error}
                slow.append(row)
                echo(f"SLOW {at} {name} status={status} {ms:.0f} ms error={error}")
        sleep(interval_s)
    return {"slow": slow, "summary": summarise(samples, slow, errors)}


def render(result: dict) -> str:
    lines = ["", f"{'target':<11} {'n':>5} {'slow':>5} {'err':>4} {'p50':>7} {'p95':>7} {'max':>7}"]
    for name, row in result["summary"].items():
        def cell(v):
            return "n/a" if v is None else f"{v:.0f}"
        lines.append(
            f"{name:<11} {row['n']:>5} {row['slow']:>5} {row['errors']:>4} "
            f"{cell(row['p50_ms']):>7} {cell(row['p95_ms']):>7} {cell(row['max_ms']):>7}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=300.0)
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between rounds")
    parser.add_argument("--slow-ms", type=float, default=1000.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not 0 < args.seconds <= MAX_SECONDS:
        parser.error(f"--seconds must be in (0, {MAX_SECONDS}]")
    if args.interval < MIN_INTERVAL_S:
        parser.error(f"--interval must be at least {MIN_INTERVAL_S}")
    result = run(args.seconds, args.interval, args.slow_ms)
    print(json.dumps(result) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
