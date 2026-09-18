r"""Price `idx_odds_window` against `/api/window`'s freshness query.

    .venv\Scripts\python.exe scripts\measure_window_index.py

`odds/timing.py::fixture_freshness` is the dominant continuous read on the live
box. Replayed read-only on live 2026-09-10 with every statement timed,
`window_status` took **0.95 s, of which 0.91 s was its one `GROUP BY
odds_event_id` over `odds_snapshots`** -- and `/api/window` is fetched on load
by four server-rendered pages (`board`, `parlays`, `slate`, `picks`), polled
every 3 s for 30 s and then every 10 s by `RefreshWhenPriced`, polled by
`Nav.tsx` on every visible tab, and called by `run_loop.py`.
`docs/measurements/2026-09-10-the-ladder-floor-oom-cycles-the-recorder.md` §7.

**This script exists because ADR 0141 forbids pricing an index from a plan
diff.** `EXPLAIN QUERY PLAN` reports the access method and never how many rows
the method touches; an index was removed in 2026-08 on that reasoning and cost
the desk 503s two weeks later. So the output here is a TIME.

It runs `timing.fixture_freshness` itself rather than a retyped copy, and pulls
the statement out of that function's own source for the `EXPLAIN`, so there is
no second copy of the SQL to drift. `backend/odds/` is read, never written.

What this does NOT establish
----------------------------
- **It is not the live table.** Row count, market mix, event ids and fixture
  spread are modelled from live's shape, not sampled from it. What it supports
  is the ORDERING of the configurations and a floor on the gap between them;
  the absolute milliseconds belong to this machine and this page cache.
- **A single arm's milliseconds are not evidence at all, and that is why the
  arms are timed round-robin.** Measured here: the identical query over the
  identical data read 1,283 ms in one session and 3,904 ms in the next, purely
  on how much of the 1.44 GB file the OS still held resident. The paired ratio
  over those same two regimes moved only 5.1x -> 5.8x. Compare arms from ONE
  run of this script; never against a number written down earlier.
- **It cannot give a magnitude for the live win, only a direction and a
  floor.** This box is at worst partly cached with a fast SSD; live is
  I/O-bound against a 5.19 GB file on a small machine, and what the index
  removes -- ~1.46M table-row fetches per call -- is I/O. v39's local 3x
  returned 81x on live. A benchmark that differs from production in which
  resource binds never transfers a magnitude. `--cache-kib` shrinks SQLite's
  page cache to move this box in live's direction; the ratio rises when it does.
- **The write cost is one sweep's worth of inserts**, with no concurrent
  reader, so it understates the real amplification on a box whose API
  connections compete with the recorder.
- **It says nothing about retention.** `odds_snapshots` has no retention rule,
  so this changes the constant and leaves the growth term alone.
- **It does not price the boot build honestly.** `CREATE INDEX` here runs
  against a cached file; on live expect minutes, not seconds.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import os
import pathlib
import random
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.odds import timing  # noqa: E402

# Live, 2026-09-10: 3,696,485 rows, ~800 fixtures with `commence_ms >= now`,
# `ODDS_MARKETS = "h2h,spreads"` plus prop keys from the prop sweep, 32-char
# Odds API event ids.
DEFAULT_ROWS = 3_696_485
UPCOMING_EVENTS = 800
PAST_EVENTS = 1_840
NOW_MS = 1_757_500_000_000

NEW_INDEX = (
    "CREATE INDEX idx_odds_window ON odds_snapshots"
    "(market, odds_event_id, fetched_ms DESC, commence_ms, book_updated_ms)"
)
#: The forms that were considered. Two are refused by the planner outright;
#: the four-column one is a live 25 MB option, measurably slower by 4-9%.
#: See the comment beside the CREATE in `schema.sql`.
ALTERNATIVES = {
    "four-column":
        "CREATE INDEX idx_odds_window ON odds_snapshots"
        "(market, odds_event_id, fetched_ms DESC, commence_ms)",
    "commence-sought":
        "CREATE INDEX idx_odds_window ON odds_snapshots"
        "(market, commence_ms, odds_event_id, fetched_ms, book_updated_ms)",
    "commence-leading":
        "CREATE INDEX idx_odds_window ON odds_snapshots"
        "(commence_ms, market, odds_event_id, fetched_ms DESC, book_updated_ms)",
}

SPORTS = ("americanfootball_nfl", "baseball_mlb", "basketball_wnba",
          "basketball_nba")
# Weighted so `market = 'h2h'` is the plurality and nowhere near the whole
# table: its selectivity is exactly what an index leading on `market` trades
# on, so guessing it generously would flatter the result.
MARKET_POOL = [m for m, w in (("h2h", 40), ("spreads", 34),
                              ("batter_home_runs", 9),
                              ("pitcher_strikeouts", 9),
                              ("player_pass_tds", 8)) for _ in range(w)]
BOOKMAKERS = tuple(f"book_{n}" for n in (
    "pinnacle", "draftkings", "fanduel", "betmgm", "caesars", "betrivers",
    "williamhill", "pointsbet", "betonline", "bovada", "lowvig", "mybookie",
    "betfair", "matchbook", "onexbet", "unibet", "betclic", "coolbet",
    "nordicbet", "betsson", "everygame", "tipico"))
TEAMS = ("Kansas City Chiefs", "San Francisco 49ers", "Los Angeles Dodgers",
         "New York Yankees", "Philadelphia Phillies", "Las Vegas Aces",
         "Minnesota Lynx", "Boston Celtics", "Oklahoma City Thunder",
         "Baltimore Orioles", "Seattle Seahawks", "Milwaukee Brewers")

#: The table and the indexes that exist before this change, verbatim from
#: `backend/store/schema.sql`, so the "before" arm is the real shape.
DDL = """
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
"""
BASELINE_INDEXES = (
    "CREATE INDEX idx_odds_event "
    "ON odds_snapshots(odds_event_id, market, fetched_ms DESC)",
    "CREATE INDEX idx_odds_event_commence "
    "ON odds_snapshots(odds_event_id, commence_ms)",
    "CREATE INDEX idx_odds_commence ON odds_snapshots(commence_ms)",
    "CREATE INDEX idx_odds_sport_commence "
    "ON odds_snapshots(sport_key, commence_ms, odds_event_id, home_team, "
    "away_team)",
)

# v47's table, index and backfill, as `backend/store/db.py::_MIGRATIONS[47]`
# declares them but with the floor as a bound parameter rather than the wall
# clock, so the synthetic slate (anchored at NOW_MS) is seeded the same way a
# volume is. The trigger is deliberately absent: nothing inserts into this
# database after the build, and the trigger's cost is `sweep_insert_ms`'s
# question, timed by `measure_odds_fixtures.py`.
FIXTURES_DDL = (
    "CREATE TABLE IF NOT EXISTS odds_fixtures ("
    "    odds_event_id   TEXT PRIMARY KEY,"
    "    sport_key       TEXT NOT NULL,"
    "    commence_ms     INTEGER NOT NULL,"
    "    home_team       TEXT,"
    "    away_team       TEXT,"
    "    last_fetched_ms INTEGER NOT NULL"
    ")",
    "CREATE INDEX IF NOT EXISTS idx_odds_fixtures_commence "
    "ON odds_fixtures(commence_ms, sport_key)",
)
FIXTURES_BACKFILL = (
    "INSERT OR IGNORE INTO odds_fixtures "
    "(odds_event_id, sport_key, commence_ms, home_team, away_team, "
    " last_fetched_ms) "
    "SELECT odds_event_id, sport_key, commence_ms, home_team, away_team, 0 "
    "FROM odds_snapshots WHERE commence_ms >= ?"
)
INSERT = (
    "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
    "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
    "outcome_name, outcome_description, outcome_point, price_decimal) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
)


def statement() -> str:
    """The SQL `fixture_freshness` runs, read out of the function itself.

    Parsed rather than retyped: a benchmark against a statement nobody executes
    is the drift `tasks/lessons.md` records.
    """
    tree = ast.parse(inspect.getsource(timing.fixture_freshness).lstrip())
    found = [
        n.args[0].value
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "execute" and n.args
        and isinstance(n.args[0], ast.Constant)
        and isinstance(n.args[0].value, str)
    ]
    if len(found) != 1:
        raise SystemExit(
            "REFUSED: `fixture_freshness` no longer holds exactly one literal "
            f"`conn.execute(...)` ({len(found)} found). This script would be "
            "timing a statement nothing runs."
        )
    return found[0]


def build(path: pathlib.Path, total_rows: int) -> None:
    for suffix in ("", "-wal", "-shm"):
        p = pathlib.Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    rng = random.Random(20260910)
    per_event = total_rows // (UPCOMING_EVENTS + PAST_EVENTS)
    t0 = time.perf_counter()
    batch, written = [], 0
    for e in range(UPCOMING_EVENTS + PAST_EVENTS):
        event_id = f"{e:08x}{rng.getrandbits(96):024x}"   # 32 chars, as live
        sport = SPORTS[e % len(SPORTS)]
        home, away = rng.choice(TEAMS), rng.choice(TEAMS)
        commence = (
            NOW_MS + rng.randrange(0, 14 * 86_400_000) if e < UPCOMING_EVENTS
            else NOW_MS - rng.randrange(1, 60 * 86_400_000)
        )
        # Sweeps land on a cadence, each writing a burst of rows sharing one
        # `fetched_ms` -- the property the query keys on.
        n_rows = per_event + rng.randrange(-200, 201)
        sweeps = max(1, n_rows // 44)
        for s in range(sweeps):
            fetched = commence - (sweeps - s) * 3_600_000
            for _ in range(44):
                market = rng.choice(MARKET_POOL)
                batch.append((
                    fetched,
                    None if rng.random() < 0.08
                    else fetched - rng.randrange(0, 900_000),
                    sport, event_id, commence, home, away,
                    rng.choice(BOOKMAKERS), market,
                    home if rng.random() < 0.5 else away,
                    None if market in ("h2h", "spreads") else "J. Player Name",
                    None if market == "h2h" else rng.uniform(-10, 10),
                    rng.uniform(1.3, 4.5),
                ))
                written += 1
                if len(batch) >= 50_000:
                    conn.executemany(INSERT, batch)
                    batch.clear()
    if batch:
        conn.executemany(INSERT, batch)
    conn.commit()
    print(f"built {written:,} rows in {time.perf_counter() - t0:.1f}s")
    for stmt in BASELINE_INDEXES:
        conn.execute(stmt)
    conn.commit()
    # v47: `fixture_freshness` now drives from `odds_fixtures`, so the arms
    # need the table. Built here the way the migration builds it on a volume
    # -- the same bounded backfill, relative to NOW_MS rather than the wall
    # clock -- so what this script still measures is `idx_odds_window`'s
    # contribution under the statement that runs today.
    for stmt in FIXTURES_DDL:
        conn.execute(stmt)
    conn.execute(FIXTURES_BACKFILL, (NOW_MS - 7 * 86_400_000,))
    conn.commit()
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()


def sweep_insert_ms(conn: sqlite3.Connection, rows: int = 900,
                    reps: int = 5) -> float:
    payload = [
        (NOW_MS + i, NOW_MS, "baseball_mlb", f"bench{i:027x}",
         NOW_MS + 10 ** 7, "Los Angeles Dodgers", "New York Yankees",
         "book_pinnacle", "h2h", "Los Angeles Dodgers", None, None, 1.91)
        for i in range(rows)
    ]
    best = None
    for _ in range(reps):
        t0 = time.perf_counter()
        conn.executemany(INSERT, payload)
        conn.commit()
        dt = (time.perf_counter() - t0) * 1000
        best = dt if best is None else min(best, dt)
        # Keyed on the synthetic id prefix: anything looser deletes real rows
        # and quietly changes the table under the next arm.
        conn.execute("DELETE FROM odds_snapshots WHERE odds_event_id "
                     "LIKE 'bench%'")
        conn.commit()
    return best


def prepare(base: pathlib.Path, label: str, create: str | None) -> pathlib.Path:
    """One arm's own copy of the data, with its index already built."""
    if create is None:
        return base
    path = pathlib.Path(f"{base}.{label}")
    for suffix in ("", "-wal", "-shm"):
        p = pathlib.Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(base, path)
    conn = sqlite3.connect(path)
    t0 = time.perf_counter()
    conn.execute(create)
    build_s = time.perf_counter() - t0
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()
    print(f"  {label:26s} CREATE INDEX {build_s:5.1f}s "
          "(cached file; live is minutes)")
    return path


def open_arm(path: pathlib.Path, cache_kib: int) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size = %d" % -cache_kib)
    return conn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    ap.add_argument("--db", default=None,
                    help="where to build; defaults to a file in the CWD")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--cache-kib", type=int, default=64_000,
                    help="SQLite page cache per connection; shrink it to "
                         "approximate the live box's memory pressure")
    ap.add_argument("--alternatives", action="store_true",
                    help="also time the column orderings that were considered")
    args = ap.parse_args()

    sql = statement()
    base = pathlib.Path(args.db or "window_index_bench.db")
    build(base, args.rows)

    arms: dict[str, str | None] = {"before": None, "idx_odds_window": NEW_INDEX}
    if args.alternatives:
        arms.update(ALTERNATIVES)

    print("\nbuilding arms")
    paths = {label: prepare(base, label, create)
             for label, create in arms.items()}
    conns = {label: open_arm(path, args.cache_kib)
             for label, path in paths.items()}
    sizes = {label: os.path.getsize(path) for label, path in paths.items()}
    rows_in_table = conns["before"].execute(
        "SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]

    # Warm every arm, and refuse outright if any of them changes the ANSWER.
    answers = {label: timing.fixture_freshness(conn, now_ms=NOW_MS)
               for label, conn in conns.items()}
    for label, ages in answers.items():
        if ages != answers["before"]:
            print(f"REFUSED: {label} changed the freshness list, not merely "
                  "the speed. Every figure would be void.")
            return 1
    print(f"\nall arms return the same {len(answers['before'])} fixtures, "
          "compared elementwise")

    print("\nplans")
    for label, conn in conns.items():
        plan = [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql,
                                           ("h2h", NOW_MS, "h2h"))]
        seeks = [s for s in plan if s.startswith("SEARCH")]
        print(f"  {label:26s} covering arms {sum('COVERING' in s for s in seeks)}"
              f"/{len(seeks)}")
        for line in plan:
            print(f"      {line}")

    # **Interleaved, and that is the whole design.** The absolute milliseconds
    # on a desktop move by 3x between sessions on page-cache residency alone,
    # so two arms timed minutes apart are not comparable. Timing them
    # alternately in one process is what makes the RATIO mean something.
    print(f"\ntiming, round-robin, {args.rounds} rounds, "
          f"{args.cache_kib // 1000} MB page cache")
    print("round  " + "  ".join(f"{label:>16s}" for label in arms))
    samples: dict[str, list[float]] = {label: [] for label in arms}
    for r in range(args.rounds):
        row = []
        for label in arms:
            t0 = time.perf_counter()
            timing.fixture_freshness(conns[label], now_ms=NOW_MS)
            ms = (time.perf_counter() - t0) * 1000
            samples[label].append(ms)
            row.append(f"{ms:16.1f}")
        print(f"{r:5d}  " + "  ".join(row))

    def median(xs: list[float]) -> float:
        return sorted(xs)[len(xs) // 2]

    print()
    base_median = median(samples["before"])
    for label in arms:
        vals = samples[label]
        grown = sizes[label] - sizes["before"]
        print(f"  {label:26s} best {min(vals):8.1f} ms   "
              f"median {median(vals):8.1f} ms   "
              f"{base_median / median(vals):5.2f}x   "
              f"+{grown / 1e6:6.1f} MB   "
              f"{grown / rows_in_table:5.1f} bytes/row   "
              f"{grown / rows_in_table * 3_696_485 / 1e6:5.0f} MB on live")

    print("\nwrite cost, one 900-row sweep, best of five")
    for label in arms:
        print(f"  {label:26s} {sweep_insert_ms(conns[label]):8.2f} ms")

    for conn in conns.values():
        conn.close()
    for label, path in paths.items():
        if label == "before":
            continue
        for suffix in ("", "-wal", "-shm"):
            p = pathlib.Path(str(path) + suffix)
            if p.exists():
                p.unlink()

    print("\nThe paired RATIO is the claim; the milliseconds belong to this "
          "machine and this page cache.")
    print("This box is at worst partly cached with a fast SSD; live is "
          "I/O-bound against 5.19 GB on a small")
    print("machine, so the ratio here is a FLOOR on the live win and never a "
          "magnitude. Shrink --cache-kib to")
    print("watch it move in the direction live sits in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
