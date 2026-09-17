"""Time the live cockpit's pages and API routes as a browser would, read-only.

Mints the session cookie ({expiry}.{hmac_sha256(APP_AUTH_TOKEN, expiry)}) from
the local .env and never prints the token or the cookie. GETs only. Runs
sequentially so it does not load the box. Prints wall-clock per route.

**Every rep is kept and the maximum is reported.** Until 2026-09-17 this
harness kept only `min` and `median` and discarded the per-rep vector, and a
session read "slowest median 1,727 ms" as a statement about the slowest
request. It is not. The 25 s read budget (ADR 0135) fires on the slowest
request, so a harness whose result will be compared against a ceiling must
record the tail; the medians it reported could not falsify anything about it.
`docs/measurements/2026-09-16-desk-route-latency-warm-box.md`,
`tasks/lessons.md` 2026-09-16 (eleventh).

**`max` at the default 2 reps is near-meaningless.** Two draws bound a tail
at nothing useful. Run 20+ reps before quoting `max`, and read `n` off the
output, which prints it for exactly this reason.

## What this does not establish

- **Nothing about the cold path, which is the only regime that has failed.**
  Every run warms the box as it goes, and both production read-budget events
  happened cold or after a page-cache eviction. A reassuring number here says
  nothing about the case that breaks.
- **Nothing about the tail at small `reps`.** Zero trips in `n` draws bounds
  the trip rate no tighter than roughly `3/n` (rule of three): 39 draws
  bounds it only to 7.7%. A clean run is not evidence of health.
- **Nothing about concurrent load.** One client, sequential, while the
  recorder writes. Two phones and a background read at once is a different
  question, and it is the one the 2026-09-10 `/api/parlays` 503 answered.
- **Page figures are measured in the most favourable possible order**, since
  `APIS` runs before `PAGES` and warms each page's own read path immediately
  before it is timed. These are not first-tap costs.
- **Nothing about any route not listed.** In particular the default sweep
  carries no league-filtered slate route -- the class that tripped the budget
  six times on 2026-09-15. Pass `--leagues` to time those; see `LEAGUE_APIS`.
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

# The league-filtered slate, timed by hand in section B of
# `docs/measurements/2026-09-16-desk-route-latency-warm-box.md` with a curl
# loop that existed nowhere in the repo -- so the one section covering the
# route class that has actually tripped the read budget in production was the
# one nobody could re-run. Committed here for reproducibility, and kept OFF
# the default sweep deliberately: the Saturday NCAAF re-time was killed
# (n = 2 with an unexplained 3.6x spread does not become a measurement by
# adding a third point under different load), so these must not quietly
# become standing routes that invite that read. Opt in with `--leagues`.
LEAGUE_APIS = [
    "/api/slate?league=americanfootball_nfl",
    "/api/slate?league=americanfootball_ncaaf",
    "/api/slate?league=baseball_mlb",
]


def main() -> None:
    argv = [a for a in sys.argv[1:] if a != "--leagues"]
    with_leagues = "--leagues" in sys.argv[1:]
    reps = int(argv[0]) if argv else 2
    client = httpx.Client(
        base_url=BASE,
        cookies={"cockpit_session": cookie()},
        timeout=180.0,
        follow_redirects=False,
        headers={"user-agent": "cockpit-timing/1"},
    )
    targets = APIS + (LEAGUE_APIS if with_leagues else []) + PAGES
    rows = []
    for path in targets:
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
        # The whole per-rep vector is kept. `max` is the number the 25 s read
        # budget is actually compared against; the median cannot falsify a
        # claim about the tail, which is the error this field exists to stop.
        rows.append(
            (
                path,
                status,
                loc,
                statistics.median(ttfb),
                min(times),
                statistics.median(times),
                max(times),
                size // reps,
                list(times),
            )
        )
        print(
            f"{path:40s} {status} ttfb={statistics.median(ttfb)*1000:8.0f}ms"
            f" min={min(times)*1000:8.0f}ms med={statistics.median(times)*1000:8.0f}ms"
            f" MAX={max(times)*1000:8.0f}ms bytes={size//reps:8d} {loc or ''}",
            flush=True,
        )
    print()
    print(f"reps per route: {reps}", end="")
    if reps < 20:
        print("  -- too few to say anything about the tail; MAX is not a bound", end="")
    print()
    print(
        json.dumps(
            [
                {
                    "path": p,
                    "status": s,
                    "reps": reps,
                    "ttfb_ms": round(f * 1000),
                    "min_ms": round(mn * 1000),
                    "med_ms": round(md * 1000),
                    "max_ms": round(mx * 1000),
                    "all_ms": [round(t * 1000) for t in every],
                    "bytes": b,
                }
                for p, s, _, f, mn, md, mx, b, every in rows
            ],
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
