"""Time the `_match_candidates` scan against three index shapes, and price the write.

    .venv\\Scripts\\python.exe scripts\\measure_odds_scan_index.py --rows 1500000

`runner._match_candidates` is

    SELECT DISTINCT odds_event_id, commence_ms, home_team, away_team
    FROM odds_snapshots WHERE sport_key = ? AND commence_ms >= ?

and `sport_key` is in no index (`schema.sql` carries
`idx_odds_event(odds_event_id, market, fetched_ms DESC)` and
`idx_odds_commence(commence_ms)`). So the plan seeks `idx_odds_commence` to
`now - 24h` and scans **every sport's** rows forward from there, fetching each
one from the table to test `sport_key`, then feeds the survivors through a temp
B-tree for the DISTINCT. On live 2026-08-30 that reached **27.7 s**, took the
pass to 104 s, starved the API's read connections and failed the Fly health
check on port 3000 at 22:06:03Z.

This script measures whether an index fixes it and what the index costs, on a
synthetic table of the real shape. It imports `MATCH_CANDIDATE_SQL` from
`backend.runner` rather than copying it, so the statement timed here is the
statement the runner executes -- there is no second copy to drift.

What this does NOT establish
----------------------------
- **It is not the live table.** Row count, sport mix and fixture spread are
  modelled from the live shape, not sampled from it. The *ordering* of the
  three configurations is what this supports; the absolute milliseconds belong
  to this machine, this page cache and this synthetic distribution.
- **It does not measure the live page cache.** Every configuration is timed on
  a freshly opened connection and again warm, and both are printed, because the
  live symptom appeared on a 2 GB database where the cold read is the one that
  hurt.
- **The write cost is one sweep's worth of inserts**, not a day of them, and it
  is measured with no concurrent reader. Real write amplification on the live
  box competes with the API's connections; this understates it.
- **It says nothing about retention.** `odds_snapshots` has no retention rule
  at all, so an index makes a growing scan cheaper without making it bounded.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.runner import MATCH_CANDIDATE_SQL  # noqa: E402

DAY_MS = 86_400_000

#: The three shapes under test. `baseline` is what `schema.sql` ships today.
NARROW_INDEX = (
    "CREATE INDEX idx_probe ON odds_snapshots(sport_key, commence_ms)"
)
COVERING_INDEX = (
    "CREATE INDEX idx_probe ON odds_snapshots"
    "(sport_key, commence_ms, odds_event_id, home_team, away_team)"
)

#: Modelled on the live slate: one dominant sport plus three smaller ones. The
#: mix matters because the whole defect is that a sport predicate cannot be
#: pushed into the seek -- a single-sport table would show no difference at all.
SPORTS = (
    ("baseball_mlb", 0.55),
    ("basketball_wnba", 0.20),
    ("americanfootball_ncaaf", 0.15),
    ("americanfootball_nfl", 0.10),
)

BOOKMAKERS = (
    "pinnacle", "betfair_ex_uk", "matchbook", "draftkings", "fanduel",
    "betmgm", "caesars", "betrivers",
)
MARKETS = ("h2h", "spreads")


def _build(path: Path, rows: int, now_ms: int, seed: int) -> None:
    """Write `rows` synthetic snapshots with the live table's shape."""
    rng = random.Random(seed)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        CREATE TABLE odds_snapshots (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_ms          INTEGER NOT NULL,
            book_updated_ms     INTEGER,
            sport_key           TEXT NOT NULL,
            odds_event_id       TEXT NOT NULL,
            commence_ms         INTEGER NOT NULL,
            home_team           TEXT NOT NULL,
            away_team           TEXT NOT NULL,
            bookmaker           TEXT NOT NULL,
            market              TEXT NOT NULL,
            outcome_name        TEXT NOT NULL,
            outcome_description TEXT,
            outcome_point       REAL,
            price_decimal       REAL NOT NULL
        );
        CREATE INDEX idx_odds_event
            ON odds_snapshots(odds_event_id, market, fetched_ms DESC);
        CREATE INDEX idx_odds_commence ON odds_snapshots(commence_ms);
        """
    )

    # Fixtures are re-quoted every sweep, so the row count grows while the
    # fixture count does not. That is the shape that makes the scan expensive:
    # ~350 distinct fixtures behind a million-plus rows.
    fixtures: list[tuple[str, str, int, str, str]] = []
    for sport, share in SPORTS:
        count = max(1, int(350 * share))
        for i in range(count):
            # Spread over -30d to +14d: most fixtures are already past, which
            # is why the predicate keeps so few and the scan reads so many.
            commence = now_ms + rng.randint(-30 * DAY_MS, 14 * DAY_MS)
            fixtures.append(
                (sport, f"{sport[:3]}-evt-{i:05d}", commence,
                 f"Home {i:04d}", f"Away {i:04d}")
            )

    batch: list[tuple] = []
    written = 0
    sweep = 0
    while written < rows:
        fetched = now_ms - (sweep * 600_000)
        sweep += 1
        for sport, event_id, commence, home, away in fixtures:
            for book in BOOKMAKERS:
                for market in MARKETS:
                    batch.append((
                        fetched, fetched - 5_000, sport, event_id, commence,
                        home, away, book, market, home, None,
                        None if market == "h2h" else rng.choice([-1.5, 1.5]),
                        1.0 + rng.random(),
                    ))
                    written += 1
                    if written >= rows:
                        break
                if written >= rows:
                    break
            if written >= rows:
                break
        if len(batch) >= 50_000 or written >= rows:
            conn.executemany(
                "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
                "sport_key, odds_event_id, commence_ms, home_team, away_team, "
                "bookmaker, market, outcome_name, outcome_description, "
                "outcome_point, price_decimal) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                batch,
            )
            conn.commit()
            batch = []
    if batch:
        conn.executemany(
            "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
            "sport_key, odds_event_id, commence_ms, home_team, away_team, "
            "bookmaker, market, outcome_name, outcome_description, "
            "outcome_point, price_decimal) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()


def _plan(conn: sqlite3.Connection, since_ms: int) -> str:
    rows = conn.execute(
        "EXPLAIN QUERY PLAN " + MATCH_CANDIDATE_SQL,
        ("baseball_mlb", since_ms),
    ).fetchall()
    return " | ".join(r[3] for r in rows)


def _time_query(path: Path, since_ms: int, repeats: int) -> dict:
    """Cold-connection first read, then the warm median over `repeats`."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    plan = _plan(conn, since_ms)

    t0 = time.perf_counter()
    rows = conn.execute(
        MATCH_CANDIDATE_SQL, ("baseball_mlb", since_ms)
    ).fetchall()
    cold_ms = (time.perf_counter() - t0) * 1000
    kept = len(rows)
    # The rows themselves, not their count. An index that returns the same
    # NUMBER of different fixtures would satisfy a count check, and the whole
    # claim being made is that a different plan returns the same answer.
    answer = frozenset(tuple(r) for r in rows)

    warm: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        conn.execute(MATCH_CANDIDATE_SQL, ("baseball_mlb", since_ms)).fetchall()
        warm.append((time.perf_counter() - t0) * 1000)
    conn.close()
    return {
        "plan": plan,
        "kept": kept,
        "answer": answer,
        "cold_ms": cold_ms,
        "warm_p50_ms": statistics.median(warm),
        "warm_min_ms": min(warm),
        "warm_max_ms": max(warm),
    }


def _time_sweep_write(
    path: Path, now_ms: int, sweep_rows: int, repeats: int
) -> tuple[float, float, float]:
    """Sweep-sized inserts, repeated, as `(p50, min, max)` milliseconds.

    **Repeated because one batch is `n = 1` and this repo reads `n` before the
    effect size.** The first version of this took a single 900-row sample per
    configuration and produced 10 / 13 / 4 ms -- an ordering in which the
    *extra* index was the fastest, which is not a result, it is the spread. A
    median over several batches is the least this can be and still be quoted.

    Still not the live write path: no concurrent reader, no WAL pressure from
    an API holding connections open. It understates.
    """
    conn = sqlite3.connect(path)
    times: list[float] = []
    for run in range(repeats):
        batch = [
            (now_ms, now_ms - 5_000, "baseball_mlb", f"probe-{run}-{i}",
             now_ms + DAY_MS, "Home 0001", "Away 0001", "pinnacle", "h2h",
             "Home 0001", None, None, 1.9)
            for i in range(sweep_rows)
        ]
        t0 = time.perf_counter()
        conn.executemany(
            "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
            "sport_key, odds_event_id, commence_ms, home_team, away_team, "
            "bookmaker, market, outcome_name, outcome_description, "
            "outcome_point, price_decimal) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
        times.append((time.perf_counter() - t0) * 1000)
    conn.execute("DELETE FROM odds_snapshots WHERE odds_event_id LIKE 'probe-%'")
    conn.commit()
    conn.close()
    return statistics.median(times), min(times), max(times)


def _index_bytes(path: Path, name: str) -> int | None:
    """Stored size via `dbstat`, or None where the build lacks that vtable.

    `dbstat` is compiled in on the deployed image (`inspect_live_db.py db-sizes`
    reads it) and is **not** compiled into every local Python's SQLite, which is
    why `_file_bytes` below exists as the fallback that always works.
    """
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT SUM(pgsize) FROM dbstat WHERE name = ?", (name,)
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except sqlite3.OperationalError:
        return None          # dbstat is not compiled in on every build
    finally:
        conn.close()


def _file_bytes(path: Path) -> int:
    """Database file size with the WAL folded back in.

    Checkpointed first, because an index built inside a WAL transaction sits in
    the -wal file until it is not, and reading the main file alone would report
    an index that costs nothing.
    """
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return path.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1_500_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--sweep-rows", type=int, default=900)
    parser.add_argument("--write-repeats", type=int, default=15)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--db", default=None, help="where to build the probe db")
    args = parser.parse_args()

    now_ms = 1_788_000_000_000
    since_ms = now_ms - DAY_MS
    path = Path(args.db) if args.db else Path("odds_scan_probe.db")
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()

    print(f"building {args.rows:,} rows at {path} ...", flush=True)
    t0 = time.perf_counter()
    _build(path, args.rows, now_ms, args.seed)
    print(f"  built in {time.perf_counter() - t0:.1f}s, "
          f"{path.stat().st_size / 1e6:.0f} MB")

    total = sqlite3.connect(path).execute(
        "SELECT COUNT(*) FROM odds_snapshots"
    ).fetchone()[0]
    scanned = sqlite3.connect(path).execute(
        "SELECT COUNT(*) FROM odds_snapshots WHERE commence_ms >= ?",
        (since_ms,),
    ).fetchone()[0]
    print(f"  {total:,} rows total, {scanned:,} at or after the 24h floor "
          f"(all sports) -- that is the scan the predicate cannot avoid\n")

    configs = (
        ("baseline (schema.sql as shipped)", None),
        ("narrow (sport_key, commence_ms)", NARROW_INDEX),
        ("covering (+ odds_event_id, home_team, away_team)", COVERING_INDEX),
    )

    kept_by_config: dict[str, int] = {}
    answers: dict[str, frozenset] = {}
    baseline_file = 0

    for label, create in configs:
        conn = sqlite3.connect(path)
        conn.execute("DROP INDEX IF EXISTS idx_probe")
        conn.commit()
        conn.close()
        without = _file_bytes(path)
        if not create:
            baseline_file = without

        conn = sqlite3.connect(path)
        if create:
            t0 = time.perf_counter()
            conn.execute(create)
            build_s = time.perf_counter() - t0
        else:
            build_s = 0.0
        conn.execute("ANALYZE")
        conn.commit()
        conn.close()

        result = _time_query(path, since_ms, args.repeats)
        write_p50, write_min, write_max = _time_sweep_write(
            path, now_ms, args.sweep_rows, args.write_repeats
        )
        # `dbstat` where the build has it, file-size delta where it does not.
        # The delta is the honest fallback: it is what the volume actually pays.
        size = _index_bytes(path, "idx_probe") if create else 0
        if create and not size:
            size = _file_bytes(path) - without

        kept_by_config[label] = result["kept"]
        answers[label] = result["answer"]

        print(f"{label}")
        print(f"  plan          {result['plan']}")
        print(f"  kept          {result['kept']} distinct fixtures")
        print(f"  cold          {result['cold_ms']:.0f} ms")
        print(f"  warm p50      {result['warm_p50_ms']:.0f} ms "
              f"(min {result['warm_min_ms']:.0f}, "
              f"max {result['warm_max_ms']:.0f})")
        print(f"  sweep write   p50 {write_p50:.0f} ms for {args.sweep_rows} "
              f"rows (min {write_min:.0f}, max {write_max:.0f}, "
              f"n={args.write_repeats})")
        if create:
            print(f"  index size    {size / 1e6:.1f} MB "
                  f"({100 * size / baseline_file:.0f}% of the indexless file)")
            print(f"  build time    {build_s:.1f} s")
        print()

    # **An index that changes the answer is not a faster index.** Printing the
    # row count beside each timing is not checking it, and the whole point of
    # the covering form is that it returns the same set from a different plan.
    if len(set(answers.values())) != 1:
        print(f"REFUSED: the three configurations return different fixture "
              f"sets, not merely different counts: {kept_by_config}")
        return 1
    print(f"All three return the same {len(next(iter(answers.values())))} "
          f"fixtures, compared as sets and not as counts.")

    print("Ordering is the claim; the milliseconds belong to this machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
