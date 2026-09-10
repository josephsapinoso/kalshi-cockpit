"""Time the live cockpit's pages and API routes as a browser would, read-only.

Mints the session cookie ({expiry}.{hmac_sha256(APP_AUTH_TOKEN, expiry)}) from
the local .env and never prints the token or the cookie. GETs only. Runs
sequentially so it does not load the box. Prints wall-clock per route.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://kalshi-cockpit.fly.dev"


def token() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_AUTH_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no APP_AUTH_TOKEN in .env")


def cookie() -> str:
    expiry = str(int(time.time() * 1000) + 3600 * 1000)
    sig = hmac.new(token().encode(), expiry.encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


PAGES = ["/parlays", "/board", "/slate", "/hedge", "/picks"]
APIS = [
    "/api/health",
    "/api/window",
    "/api/odds/refreshable",
    "/api/signal",
    "/api/parlays",
    "/api/board?include_suppressed=false",
    "/api/slate",
    "/api/hedge",
]


def main() -> None:
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    client = httpx.Client(
        base_url=BASE,
        cookies={"cockpit_session": cookie()},
        timeout=180.0,
        follow_redirects=False,
        headers={"user-agent": "cockpit-timing/1"},
    )
    rows = []
    for path in APIS + PAGES:
        times = []
        status = None
        size = 0
        ttfb = []
        for _ in range(reps):
            t0 = time.perf_counter()
            with client.stream("GET", path) as r:
                first = None
                for chunk in r.iter_bytes():
                    if first is None:
                        first = time.perf_counter() - t0
                    size += len(chunk)
                status = r.status_code
                loc = r.headers.get("location")
            times.append(time.perf_counter() - t0)
            ttfb.append(first or 0.0)
        rows.append((path, status, loc, statistics.median(ttfb), min(times), statistics.median(times), size // reps))
        print(f"{path:40s} {status} ttfb={statistics.median(ttfb)*1000:8.0f}ms min={min(times)*1000:8.0f}ms med={statistics.median(times)*1000:8.0f}ms bytes={size//reps:8d} {loc or ''}", flush=True)
    print()
    print(json.dumps([{"path": p, "status": s, "ttfb_ms": round(f*1000), "min_ms": round(mn*1000), "med_ms": round(md*1000), "bytes": b} for p, s, _, f, mn, md, b in rows], indent=1))


if __name__ == "__main__":
    main()
