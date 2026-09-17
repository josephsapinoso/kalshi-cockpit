"""Characterise the /api/signal tail seen at ~13.5 s on two separate days.

GETs only, one route, sequential, session cookie minted from the local .env
the way `scripts/time_live_routes.py` does. Never prints the token or cookie.
Buys no odds credits: attention is stamped only by POST /api/desk/attention.

Prints EVERY rep with a wall-clock timestamp, so a slow rep can be lined up
against the recorder's ~900 s write cycle afterwards. The whole point is the
per-rep vector -- a median here would hide the thing being investigated.

What this does NOT establish: the cause. It is one route from one client over
the public internet; a slow rep could be the box, the network, or the client.
It bounds how OFTEN a slow rep happens under these conditions and nothing else.
"""

import hashlib
import hmac
import pathlib
import statistics
import sys
import time

import httpx

BASE = "https://kalshi-cockpit.fly.dev"
ROUTE = "/api/signal"


def token() -> str:
    for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_AUTH_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no APP_AUTH_TOKEN in .env")


def cookie() -> str:
    expiry = str(int(time.time() * 1000) + 3600 * 1000)
    sig = hmac.new(token().encode(), expiry.encode(), hashlib.sha256).hexdigest()
    return expiry + "." + sig


def main() -> None:
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    gap = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    times = []
    slow = []
    with httpx.Client(
        base_url=BASE,
        cookies={"cockpit_session": cookie()},
        timeout=60.0,
        follow_redirects=False,
        headers={"user-agent": "cockpit-timing/1"},
    ) as client:
        for i in range(reps):
            wall = time.strftime("%H:%M:%SZ", time.gmtime())
            t0 = time.perf_counter()
            r = client.get(ROUTE)
            dt = time.perf_counter() - t0
            times.append(dt)
            flag = ""
            if dt > 2.0:
                flag = "   <-- SLOW"
                slow.append((i, wall, dt))
            print(
                "%3d  %s  %8.0f ms  http %d%s" % (i, wall, dt * 1000, r.status_code, flag),
                flush=True,
            )
            if i + 1 < reps:
                time.sleep(gap)

    print()
    print("n            %d" % len(times))
    print("min          %8.0f ms" % (min(times) * 1000))
    print("median       %8.0f ms" % (statistics.median(times) * 1000))
    print("max          %8.0f ms" % (max(times) * 1000))
    print("slow (>2s)   %d of %d" % (len(slow), len(times)))
    for i, wall, dt in slow:
        print("   rep %d at %s: %.0f ms" % (i, wall, dt * 1000))
    if not slow:
        # Rule of three: zero events in n draws bounds the rate at ~3/n, no
        # tighter. Say it rather than let a clean run read as health.
        print("no slow rep: bounds the rate no tighter than %.1f%%" % (300.0 / len(times)))


if __name__ == "__main__":
    main()
