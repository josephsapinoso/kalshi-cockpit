"""Probe the public cockpit for fixed-length stalls, and analyse the gaps.

Reproduces the probe behind every stall count in
`docs/measurements/2026-09-28-a-fixed-3-second-stall-sits-upstream-of-uvicorn.md`
(sections A, C, E) so #193's 30 s health-check trial can be re-read.

Each `--base-url` is its own arm: its own pooled keep-alive `httpx.Client`, its
own thread, all arms in the same window. Each arm round-robins the built-in
targets `/api/health` and `/no-such-page-probe` (built in so nothing on the
command line starts with `/`; Git Bash rewrites a leading `/` into a Windows
path, `tasks/lessons.md` 2026-09-28). GETs only, read-only.

**A stall is `elapsed_ms >= STALL_MS` and nothing else decides it.** HTTP status
is its own column, so a fast 404 is never a stall, and a transport error is
recorded as an error, never as a stall. (An earlier scratch version labelled
every non-200 SLOW.)

Trial decision rule, fixed before the reading (#193): F = fraction of gaps
between consecutive stalls that are under 24 s. MOVED means at least 12 gaps
and none under 24 s. UNMOVED means F >= 0.25.

`--auth` mints the `cockpit_session` cookie as `scripts/time_live_routes.py`
does, from the local `.env`. The token and the cookie never reach stdout,
stderr or the output file. `--out` is required and may not be inside the repo
(operator data never enters the repo).

## What this does not establish

- One client and one path family from one laptop; nothing about other networks.
- Stalls are counted only when a probe request happens to land on one; a stall
  between requests is invisible, and the interval bounds what can be seen.
- Keep-alive vs `--fresh` changes which connections are measured.
- No rate is quotable from one evening.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://kalshi-cockpit.fly.dev"
TARGETS = ["/api/health", "/no-such-page-probe"]
STALL_MS = 1000.0
GAP_THRESHOLD_S = 24.0
COLUMNS = ["ts_utc", "arm", "path", "status", "elapsed_ms", "stall", "error"]


def token() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_AUTH_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no APP_AUTH_TOKEN in .env")


def cookie() -> str:
    expiry = str(int(time.time() * 1000) + 3600 * 1000)
    sig = hmac.new(token().encode(), expiry.encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


# ---- pure analysis -------------------------------------------------------

def is_stall(elapsed_ms: float | None, error: str = "") -> bool:
    """Only elapsed time decides; a transport error is never a stall."""
    if error or elapsed_ms is None:
        return False
    return elapsed_ms >= STALL_MS


def stall_gaps(timestamps: list[float]) -> list[float]:
    """Seconds between consecutive stalls, given epoch-second timestamps."""
    ts = sorted(timestamps)
    return [b - a for a, b in zip(ts, ts[1:])]


def fraction_under(gaps: list[float], threshold_s: float = GAP_THRESHOLD_S) -> float | None:
    if not gaps:
        return None
    return sum(1 for g in gaps if g < threshold_s) / len(gaps)


def _pct(vals: list[float], q: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))]


def summarise(rows: list[dict]) -> dict[str, dict]:
    """Per-arm summary from recorded rows (dicts keyed by COLUMNS)."""
    out: dict[str, dict] = {}
    for arm in dict.fromkeys(r["arm"] for r in rows):
        mine = [r for r in rows if r["arm"] == arm]
        ok = [float(r["elapsed_ms"]) for r in mine if not r["error"]]
        stalls = [r for r in mine if str(r["stall"]).lower() == "true"]
        stall_ms = [float(r["elapsed_ms"]) for r in stalls]
        stamps = [datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00")).timestamp()
                  for r in stalls]
        gaps = stall_gaps(stamps)
        statuses: dict[str, int] = {}
        for r in mine:
            key = "error" if r["error"] else str(r["status"])
            statuses[key] = statuses.get(key, 0) + 1
        out[arm] = {
            "n": len(mine),
            "stalls": len(stalls),
            "stall_ms_range": (min(stall_ms), max(stall_ms)) if stall_ms else None,
            "p50": statistics.median(ok) if ok else None,
            "p95": _pct(ok, 0.95) if ok else None,
            "statuses": statuses,
            "gaps": gaps,
            "F": fraction_under(gaps),
            "min_gap": min(gaps) if gaps else None,
        }
    return out


def format_summary(summary: dict[str, dict]) -> str:
    lines = []
    for arm, s in summary.items():
        rng = s["stall_ms_range"]
        lines.append(f"arm {arm}")
        lines.append(f"  n={s['n']} stalls={s['stalls']} "
                     f"stall_ms={'none' if rng is None else f'{rng[0]:.0f}..{rng[1]:.0f}'}")
        p50, p95 = s["p50"], s["p95"]
        lines.append(f"  p50={'n/a' if p50 is None else f'{p50:.1f}'} ms "
                     f"p95={'n/a' if p95 is None else f'{p95:.1f}'} ms")
        lines.append(f"  status counts: {s['statuses']}")
        gaps = s["gaps"]
        lines.append(f"  gaps ({len(gaps)}): {[round(g, 1) for g in gaps]}")
        f, mg = s["F"], s["min_gap"]
        lines.append(f"  F(gaps<{GAP_THRESHOLD_S:.0f}s)={'n/a' if f is None else f'{f:.3f}'} "
                     f"min_gap={'n/a' if mg is None else f'{mg:.1f}'} s")
    return "\n".join(lines)


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---- probe ---------------------------------------------------------------

def refuse_inside_repo(out: Path) -> None:
    resolved = out.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise SystemExit(f"--out {out} is inside the repo; operator data never enters it")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def probe_once(client: httpx.Client, arm: str, path: str) -> dict:
    ts = _now_iso()
    t0 = time.perf_counter()
    status, error = "", ""
    try:
        resp = client.get(arm.rstrip("/") + path)
        status = resp.status_code
    except httpx.HTTPError as exc:
        error = type(exc).__name__
    elapsed = (time.perf_counter() - t0) * 1000
    return {"ts_utc": ts, "arm": arm, "path": path, "status": status,
            "elapsed_ms": f"{elapsed:.1f}", "stall": is_stall(elapsed, error),
            "error": error}


def run_arm(arm: str, seconds: float, interval: float, fresh: bool,
            cookies: dict | None, transport, rows: list, lock: threading.Lock) -> None:
    def make() -> httpx.Client:
        return httpx.Client(timeout=30.0, cookies=cookies, transport=transport)

    client = None if fresh else make()
    end = time.monotonic() + seconds
    i = 0
    while time.monotonic() < end:
        path = TARGETS[i % len(TARGETS)]
        i += 1
        if fresh:
            with make() as c:
                row = probe_once(c, arm, path)
        else:
            row = probe_once(client, arm, path)
        with lock:
            rows.append(row)
        time.sleep(interval)
    if client is not None:
        client.close()


def run_probe(bases: list[str], seconds: float, interval: float, fresh: bool,
              cookie_value: str | None, transport=None) -> list[dict]:
    cookies = {"cockpit_session": cookie_value} if cookie_value else None
    rows: list[dict] = []
    lock = threading.Lock()
    threads = [threading.Thread(target=run_arm, args=(b, seconds, interval, fresh,
                                                       cookies, transport, rows, lock))
               for b in bases]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(rows, key=lambda r: r["ts_utc"])


def write_rows(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None, transport=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-url", action="append", dest="bases",
                    help=f"repeatable; each is its own arm (default {DEFAULT_BASE})")
    ap.add_argument("--seconds", type=float, default=1800)
    ap.add_argument("--interval", type=float, default=1.0, help="seconds per arm")
    ap.add_argument("--fresh", action="store_true", help="new connection per request")
    ap.add_argument("--auth", action="store_true",
                    help="send a minted cockpit_session cookie from local .env")
    ap.add_argument("--out", type=Path, help="required for a probe run; not inside the repo")
    ap.add_argument("--analyse", type=Path, help="re-read a recorded file and summarise")
    args = ap.parse_args(argv)

    if args.analyse:
        print(format_summary(summarise(read_rows(args.analyse))))
        return 0
    if not args.out:
        ap.error("--out is required")
    refuse_inside_repo(args.out)
    bases = args.bases or [DEFAULT_BASE]
    rows = run_probe(bases, args.seconds, args.interval, args.fresh,
                     cookie() if args.auth else None, transport)
    write_rows(args.out, rows)
    print(format_summary(summarise(read_rows(args.out))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
