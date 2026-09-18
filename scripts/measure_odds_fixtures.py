r"""Rehearse schema v47 at live's shape: the backfill, the trigger, the reads.

    .venv\Scripts\python.exe scripts\measure_odds_fixtures.py

`/api/window` is fetched on load by four server-rendered pages and polled by
every open tab. On 2026-09-17 it measured 7 s at the median on live and tripped
the 25 s read budget twice, because both of its fixture reads --
`odds/timing.py::upcoming_fixtures_by_sport` and `::fixture_freshness` --
derived the set of upcoming fixtures by walking every stored snapshot row of
every upcoming fixture. v47 adds `odds_fixtures`, one row per fixture kept by a
trigger, and rewrites both reads to seek into it.

Three questions, each answered with a TIME and not a plan (ADR 0141):

1. **The migration's cost at boot.** The v47 backfill statement, run once on a
   cold-built database at live's shape. This is what the 600 s health grace
   has to cover on the volume. Peak resident set is read beside it, because
   the 2026-09-10 incident was a scan whose wall-clock read "slow but fine"
   while its RSS was the finding.
2. **The trigger's cost per sweep.** A 900-row sweep insert with and without
   the trigger, round-robin, because a per-row upsert on every snapshot insert
   is a tax the recorder pays forever.
3. **The reads, before and after.** The v41 statements (retyped here, labelled
   as such, because they no longer exist in the source) against the v47
   functions, on the same database, alternately, five rounds.

Reuses `measure_window_index.build` so the slate is the same live-shaped one
that priced v41: 3.6M rows, 2,640 events, 800 upcoming.

What this does NOT establish
----------------------------
- **Not the live table.** Modelled from live's shape as of 2026-09-10; the
  live table is larger now and its upcoming population is what the NFL and
  NCAAF weekends make it. Ratios and ordering transfer; milliseconds do not.
- **Not the cold-cache regime the budget fires in.** Everything here runs
  warm after the build. The v39 index went 3x local -> 81x live on exactly
  that gap. A post-deploy timing of `/api/window` is the only settlement
  (`scripts/time_live_routes.py`).
- **Not the moved-kickoff behaviour.** The synthetic slate quotes one kickoff
  per fixture, so the trigger's "latest sweep wins" rule is exercised by
  `tests/test_window_freshness_index.py`, not here.
- **RSS is this interpreter's, on this OS.** Windows reports it through
  `ctypes`; the number is the process peak, which includes the build.
  What matters is the DELTA across the backfill, printed as such.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import pathlib
import shutil
import sqlite3
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import measure_window_index as bench  # noqa: E402
from backend.odds import timing  # noqa: E402
from backend.store import db as store  # noqa: E402

NOW_MS = bench.NOW_MS

V41_FRESHNESS = (
    "WITH latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
    "  WHERE market = ? AND commence_ms >= ? GROUP BY odds_event_id"
    ") "
    "SELECT MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms "
    "FROM odds_snapshots o JOIN latest l "
    "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
    "WHERE o.market = ? GROUP BY o.odds_event_id"
)
V41_UPCOMING = (
    "SELECT sport_key, commence_ms FROM ("
    "  SELECT DISTINCT sport_key, odds_event_id, commence_ms"
    "  FROM odds_snapshots WHERE commence_ms >= ? AND commence_ms <= ?"
    ")"
)
TRIGGER_SQL = None  # read from schema.sql below, never retyped


def _trigger_from_schema() -> str:
    src = (ROOT / "backend" / "store" / "schema.sql").read_text(encoding="utf-8")
    start = src.index("CREATE TRIGGER IF NOT EXISTS trg_odds_fixtures_upsert")
    end = src.index("END;", start) + len("END;")
    return src[start:end]


def _rss_mb() -> float:
    if sys.platform == "win32":
        class C(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        c = C()
        c.cb = ctypes.sizeof(C)
        kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return c.WorkingSetSize / 1e6
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3


def _open(path: pathlib.Path, cache_kib: int) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA cache_size = -{cache_kib}")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def _old_freshness(conn) -> list[int]:
    rows = conn.execute(V41_FRESHNESS, ("h2h", NOW_MS, "h2h")).fetchall()
    return sorted(NOW_MS - int(r["oldest_ms"]) for r in rows)


def _old_upcoming(conn) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for r in conn.execute(V41_UPCOMING, (NOW_MS, NOW_MS + timing.DEFAULT_HORIZON_MS)):
        out.setdefault(r["sport_key"], []).append(int(r["commence_ms"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", type=int, default=bench.DEFAULT_ROWS)
    ap.add_argument("--db", default=None)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--cache-kib", type=int, default=64_000)
    args = ap.parse_args()

    base = pathlib.Path(args.db or "odds_fixtures_bench.db")
    bench.build(base, args.rows)          # includes the v47 table, backfilled
    conn = _open(base, args.cache_kib)
    n_rows = conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
    n_fix = conn.execute("SELECT COUNT(*) FROM odds_fixtures").fetchone()[0]
    print(f"\n{n_rows:,} snapshot rows, {n_fix:,} fixtures backfilled")

    # 1. the backfill, cold: drop and rebuild the table the way the step would.
    conn.execute("DROP TABLE odds_fixtures")
    conn.commit()
    for stmt in bench.FIXTURES_DDL:
        conn.execute(stmt)
    rss0 = _rss_mb()
    t0 = time.perf_counter()
    conn.execute(bench.FIXTURES_BACKFILL, (NOW_MS - 7 * 86_400_000,))
    conn.commit()
    backfill_ms = (time.perf_counter() - t0) * 1000
    rss1 = _rss_mb()
    n_fix2 = conn.execute("SELECT COUNT(*) FROM odds_fixtures").fetchone()[0]
    plan = [r[3] for r in conn.execute(
        "EXPLAIN QUERY PLAN " + bench.FIXTURES_BACKFILL, (NOW_MS - 7 * 86_400_000,))]
    print(f"\n1. backfill: {backfill_ms:,.0f} ms for {n_fix2:,} fixtures; "
          f"RSS {rss0:.0f} -> {rss1:.0f} MB (delta {rss1 - rss0:+.0f})")
    for line in plan:
        print(f"      {line}")
    assert n_fix2 == n_fix, (n_fix2, n_fix)

    # 3 (before 2, so the trigger is not yet installed): reads, round-robin.
    old_f, new_f = _old_freshness(conn), timing.fixture_freshness(conn, now_ms=NOW_MS)
    old_u, new_u = _old_upcoming(conn), timing.upcoming_fixtures_by_sport(conn, now_ms=NOW_MS)
    if old_f != new_f or {k: sorted(v) for k, v in old_u.items()} != {k: sorted(v) for k, v in new_u.items()}:
        print("REFUSED: v47 changed an answer, not merely the speed. "
              f"freshness {len(old_f)} vs {len(new_f)}; upcoming "
              f"{ {k: len(v) for k, v in old_u.items()} } vs "
              f"{ {k: len(v) for k, v in new_u.items()} }")
        return 1
    print(f"\n3. reads agree: {len(new_f)} fixtures' ages, "
          f"{sum(len(v) for v in new_u.values())} upcoming kickoffs")
    arms = {
        "v41 freshness": lambda: _old_freshness(conn),
        "v47 freshness": lambda: timing.fixture_freshness(conn, now_ms=NOW_MS),
        "v41 upcoming": lambda: _old_upcoming(conn),
        "v47 upcoming": lambda: timing.upcoming_fixtures_by_sport(conn, now_ms=NOW_MS),
    }
    samples: dict[str, list[float]] = {k: [] for k in arms}
    print("round  " + "  ".join(f"{k:>15s}" for k in arms))
    for r in range(args.rounds):
        row = []
        for k, fn in arms.items():
            t0 = time.perf_counter()
            fn()
            ms = (time.perf_counter() - t0) * 1000
            samples[k].append(ms)
            row.append(f"{ms:15.1f}")
        print(f"{r:5d}  " + "  ".join(row))
    med = {k: statistics.median(v) for k, v in samples.items()}
    print("median " + "  ".join(f"{med[k]:15.1f}" for k in arms))
    print(f"paired ratio, median to median: freshness "
          f"{med['v41 freshness'] / max(med['v47 freshness'], 1e-3):.1f}x, "
          f"upcoming {med['v41 upcoming'] / max(med['v47 upcoming'], 1e-3):.1f}x")

    # 2. the trigger's cost per sweep, round-robin on two copies.
    conn.close()
    with_t = pathlib.Path(str(base) + ".trigger")
    without = pathlib.Path(str(base) + ".notrigger")
    for p in (with_t, without):
        for suffix in ("", "-wal", "-shm"):
            q = pathlib.Path(str(p) + suffix)
            if q.exists():
                q.unlink()
        shutil.copyfile(base, p)
    ct = _open(with_t, args.cache_kib)
    ct.execute(_trigger_from_schema())
    ct.commit()
    cn = _open(without, args.cache_kib)
    cn.execute("PRAGMA journal_mode=WAL")
    ct.execute("PRAGMA journal_mode=WAL")
    t_with, t_without = [], []
    print(f"\n2. a 900-row sweep insert, {args.rounds} rounds, round-robin")
    for _ in range(args.rounds):
        t_with.append(bench.sweep_insert_ms(ct))
        t_without.append(bench.sweep_insert_ms(cn))
    print(f"   without trigger  median {statistics.median(t_without):7.1f} ms   {t_without}")
    print(f"   with trigger     median {statistics.median(t_with):7.1f} ms   {t_with}")
    ct.close()
    cn.close()
    for p in (with_t, without):
        for suffix in ("", "-wal", "-shm"):
            q = pathlib.Path(str(p) + suffix)
            if q.exists():
                q.unlink()
    print(f"\nschema version under test: {store.SCHEMA_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
