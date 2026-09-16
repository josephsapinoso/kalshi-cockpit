r"""Price the ways of making `fair-prices-by-market` bounded AND cheap.

    .venv\Scripts\python.exe scripts\measure_fair_price_window_index.py

`scripts/inspect_live_db_decisions.py::_q_fair_prices_by_market` is an
unbounded `GROUP BY market` over `fair_prices`, one of the two largest tables
on the box (~10.1M rows, ADR 0141 §Measurement). ADR 0157 forbids exactly that
shape -- an instrument whose cost lands on whoever touches the desk next -- and
the remedy it names is a default window.

**The window alone is not enough, and the obvious index does not help either.**
`fair_prices` has no index leading with `computed_ms`, so the brief for this
work was to add one. That is what this script was written to price, and the
measurement refused it: the planner does not choose the new index in any
configuration tested. What makes the window seekable is `sqlite_stat1` -- with
table statistics the planner runs the EXISTING `idx_fair_market_computed` as a
**skip-scan** (`ANY(market) AND computed_ms>?`), because `market` has a handful
of distinct values. Nothing in `backend/` has ever run `ANALYZE`, so live has
no statistics at all.

So the arms are a matrix, not a list: {no new index, non-covering, covering} x
{no statistics, `PRAGMA analysis_limit` + `ANALYZE fair_prices`}, plus the one
configuration that seeks without statistics by naming the index outright
(`INDEXED BY`).

**This script exists because ADR 0141 forbids pricing an index from a plan
diff.** `EXPLAIN QUERY PLAN` names the access method and never the rows it
touches; an index removed on that reasoning in 2026-08 cost the desk 503s two
weeks later. So the output here is a TIME -- and this run is the same rule
biting in the other direction, refusing an index that a plan-free argument had
already approved.

It executes the statements out of `inspect_live_db_decisions.py` itself rather
than a retyped copy, so the benchmark cannot drift from the query it prices.

What this does NOT establish
----------------------------
- **It is not the live table.** Row count, market mix, link fan-out and the
  `computed_ms` distribution are MODELLED from live's recorded shape, not
  sampled from it. `market` cardinality is the input the skip-scan decision
  turns on, and it is modelled here -- which is precisely why this result is
  not deployable on its own. The live magnitude comes only from the container
  rehearsal on a paced copy
  (`docs/measurements/2026-09-10-the-ladder-floor-oom-cycles-the-recorder.md`
  §6, the procedure), and so does the blast-radius check below.
- **Nothing about what `ANALYZE` does to every OTHER query on the box.**
  Statistics are a global planner input. ADR 0134's `MULTI-INDEX OR` on
  `CANDIDATE_SQL` was arrived at with no statistics present, and a plan that
  good can be lost as easily as won. This script times one statement. The
  rehearsal must diff the plan of every hot read before and after.
- **A single arm's milliseconds are not evidence**, which is why arms are timed
  round-robin in one process. Two arms timed minutes apart differ on page-cache
  residency alone. Compare arms from ONE run; never against an older number.
- **It cannot give a magnitude for the live win, only a direction and a
  floor.** This box has a fast SSD and may hold the whole file; live is
  I/O-bound against >5 GB with 2.0 GB of RAM. v39's local 3x returned 81x on
  live. `--cache-kib` shrinks SQLite's page cache toward live's regime.
- **It says nothing about `odds_snapshots`.** Section A of the census bounds on
  `commence_ms`, which `idx_odds_commence` already serves; nothing is bought
  there and nothing is timed here.
- **The write cost is one pass of inserts with no concurrent reader**, so it
  understates amplification on a box whose API connections compete with the
  recorder.
- **Nothing about statistics going stale.** `ANALYZE` is a snapshot; the
  recorder writes continuously. What keeps the skip-scan decision robust is
  that `market` cardinality is small and stable, not that the numbers stay
  exact -- and that is an argument, not a measurement.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import random
import re
import shutil
import sqlite3
import sys
import time

_HERE = pathlib.Path(__file__).resolve().parent
# Both, and in this order: the repo root so `backend`/`scripts` import as
# packages, and this directory because `inspect_live_db_decisions` imports its
# siblings by bare name. Running this file as a script adds the second
# implicitly; importing it (the test that checks it parses) does not.
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(1, str(_HERE))

from scripts import inspect_live_db_decisions as decisions  # noqa: E402

# Live's recorded shape. 10,112,298 rows is ADR 0141 §Measurement, read
# 2026-09-10; `fair_prices` is pruned, so the true number moves and the
# rehearsal on the paced copy is what reads it for real.
DEFAULT_ROWS = 10_112_298
LINKS = 4_200
NOW_MS = 1_757_500_000_000
DAYS_BACK = 90

NEW_INDEX_NAME = "idx_fair_computed"
NON_COVERING = f"CREATE INDEX {NEW_INDEX_NAME} ON fair_prices(computed_ms)"
COVERING = (
    f"CREATE INDEX {NEW_INDEX_NAME} ON fair_prices"
    "(computed_ms, market, link_id)"
)

#: `PRAGMA analysis_limit` bounds `ANALYZE` to a sample per index instead of a
#: full scan of each. That is the difference between a boot-time step measured
#: in milliseconds and one measured against the 600 s health grace -- and the
#: cardinality of `market` is what the decision turns on, which a sample of a
#: thousand rows per index settles as well as ten million do.
ANALYZE_STEPS = ("PRAGMA analysis_limit=1000", "ANALYZE fair_prices")

#: (label, CREATE INDEX or None, run ANALYZE, INDEXED BY clause)
ARMS: tuple[tuple[str, str | None, bool, str], ...] = (
    ("today", None, False, ""),
    ("stats only", None, True, ""),
    ("non-covering idx", NON_COVERING, False, ""),
    ("covering idx", COVERING, False, ""),
    ("non-covering + stats", NON_COVERING, True, ""),
    ("covering + stats", COVERING, True, ""),
    ("covering + INDEXED BY", COVERING, False, f" INDEXED BY {NEW_INDEX_NAME}"),
)

#: Weighted so no single market is the whole table: `h2h` is the plurality and
#: the prop keys are the long tail `ODDS_BUY_PROPS_ON_SCHEDULE = "false"` has
#: stopped feeding. The COUNT of distinct markets is the skip-scan's input, so
#: it is modelled deliberately small -- live's `fair_prices.market` holds the
#: three team keys plus whatever prop keys were ever bought.
MARKET_POOL = [
    m
    for m, w in (
        ("h2h", 42),
        ("spreads", 30),
        ("totals", 20),
        ("batter_home_runs", 4),
        ("pitcher_strikeouts", 4),
    )
    for _ in range(w)
]

#: Verbatim from `backend/store/schema.sql`, so the "today" arm is the real
#: shape -- including the three indexes that already exist, none of which leads
#: with `computed_ms`.
DDL = """
CREATE TABLE fair_prices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_ms         INTEGER NOT NULL,
    link_id             INTEGER NOT NULL,
    market              TEXT NOT NULL,
    outcome_name        TEXT NOT NULL,
    outcome_description TEXT,
    outcome_point       REAL,
    p_multiplicative    REAL,
    p_additive          REAL,
    p_power             REAL,
    p_shin              REAL,
    p_conservative      REAL NOT NULL,
    overround           REAL,
    market_width        REAL,
    book_count          INTEGER NOT NULL,
    books_used          TEXT NOT NULL,
    oldest_book_age_ms  INTEGER,
    confirmed_ms                    INTEGER,
    confirmed_oldest_book_age_ms    INTEGER,
    anchored_on_sharp   INTEGER NOT NULL DEFAULT 0
);
"""
BASELINE_INDEXES = (
    "CREATE INDEX idx_fair_link ON fair_prices(link_id, computed_ms DESC)",
    "CREATE INDEX idx_fair_market_computed "
    "ON fair_prices(market, computed_ms DESC)",
    "CREATE INDEX idx_fair_market_confirmed "
    "ON fair_prices(market, confirmed_ms DESC) WHERE confirmed_ms IS NOT NULL",
)

INSERT = (
    "INSERT INTO fair_prices (computed_ms, link_id, market, outcome_name, "
    "outcome_description, outcome_point, p_multiplicative, p_additive, "
    "p_power, p_shin, p_conservative, overround, market_width, book_count, "
    "books_used, oldest_book_age_ms, confirmed_ms, "
    "confirmed_oldest_book_age_ms, anchored_on_sharp) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

def unbounded_sql() -> str:
    """The census as it stands on live today: no predicate at all.

    Derived by REMOVING the bound from the shipped statement rather than kept
    as a second literal, so the "today" column is the shipped query minus
    exactly the thing being priced.
    """
    sql = bounded_sql().replace("WHERE computed_ms >= :since ", "")
    if ":since" in sql:
        raise SystemExit(
            "REFUSED: could not strip the bound from the census statement, so "
            "the unbounded column would be the bounded query under the wrong "
            "label."
        )
    return sql


def bounded_sql(indexed_by: str = "") -> str:
    """The windowed statement, derived from the module's own constant.

    Read out of `inspect_live_db_decisions` and, while the bound is not yet
    shipped there, synthesised from the same string -- so the day it ships this
    returns the shipped statement and never a second copy of it.
    """
    sql = decisions._SQL_FAIR_PRICES_BY_MARKET
    if ":since" not in sql:
        sql = re.sub(
            r"FROM fair_prices GROUP BY",
            "FROM fair_prices WHERE computed_ms >= :since GROUP BY",
            sql,
        )
    if indexed_by:
        sql = sql.replace("FROM fair_prices", f"FROM fair_prices{indexed_by}")
    return sql


def build(path: pathlib.Path, total_rows: int) -> None:
    for suffix in ("", "-wal", "-shm"):
        p = pathlib.Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    rng = random.Random(20260916)
    span_ms = DAYS_BACK * 86_400_000
    t0 = time.perf_counter()
    batch: list[tuple] = []
    written = 0
    while written < total_rows:
        # Rows land in passes: one link, one instant, a burst of rungs sharing
        # a `computed_ms`. That burst structure is what a window seeks into, so
        # a uniform scatter would flatter every bounded arm.
        link = rng.randrange(1, LINKS + 1)
        computed = NOW_MS - int(rng.random() ** 0.6 * span_ms)
        market = rng.choice(MARKET_POOL)
        for _ in range(rng.randrange(4, 14)):
            confirmed = (
                computed + rng.randrange(0, 900_000)
                if rng.random() < 0.004
                else None
            )
            batch.append((
                computed, link, market,
                "Home" if rng.random() < 0.5 else "Away",
                None if market in ("h2h", "spreads", "totals")
                else "J. Player Name",
                None if market == "h2h" else rng.uniform(-10.5, 10.5),
                rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7),
                rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7),
                rng.uniform(0.3, 0.7), rng.uniform(1.0, 1.08),
                rng.uniform(0.0, 0.06), rng.randrange(3, 11),
                '["pinnacle","draftkings","fanduel"]',
                rng.randrange(0, 900_000), confirmed,
                None if confirmed is None else rng.randrange(0, 900_000),
                1 if rng.random() < 0.6 else 0,
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
    # Deliberately NOT analysed: live has no `sqlite_stat1`, because nothing in
    # `backend/` has ever run ANALYZE. The baseline has to be live's baseline.
    conn.execute("DROP TABLE IF EXISTS sqlite_stat1")
    conn.commit()
    conn.close()


def pass_insert_ms(conn: sqlite3.Connection, rows: int = 400,
                   reps: int = 5) -> float:
    """One recorder pass's worth of inserts, best of `reps`.

    The write side, which a benefit-only argument leaves out.
    """
    payload = [
        (NOW_MS + i, 999_999, "h2h", "Home", None, None,
         0.5, 0.5, 0.5, 0.5, 0.5, 1.03, 0.01, 6, "[]", 1000, None, None, 0)
        for i in range(rows)
    ]
    best = None
    for _ in range(reps):
        t0 = time.perf_counter()
        conn.executemany(INSERT, payload)
        conn.commit()
        dt = (time.perf_counter() - t0) * 1000
        best = dt if best is None else min(best, dt)
        # Keyed on the synthetic link id; anything looser deletes real rows and
        # changes the table under the next arm.
        conn.execute("DELETE FROM fair_prices WHERE link_id = 999999")
        conn.commit()
    return best


def prepare(base: pathlib.Path, label: str, create: str | None,
            analyze: bool) -> pathlib.Path:
    slug = label.replace(" ", "_").replace("+", "and")
    path = pathlib.Path(f"{base}.{slug}")
    for suffix in ("", "-wal", "-shm"):
        p = pathlib.Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(base, path)
    conn = sqlite3.connect(path)
    build_s = analyze_s = 0.0
    if create:
        t0 = time.perf_counter()
        conn.execute(create)
        build_s = time.perf_counter() - t0
    if analyze:
        t0 = time.perf_counter()
        for stmt in ANALYZE_STEPS:
            conn.execute(stmt)
        analyze_s = time.perf_counter() - t0
    conn.commit()
    conn.close()
    print(f"  {label:24s} CREATE INDEX {build_s:6.1f}s   "
          f"ANALYZE {analyze_s * 1000:7.1f}ms   (cached file; live is slower)")
    return path


def open_arm(path: pathlib.Path, cache_kib: int) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA cache_size = %d" % -cache_kib)
    return conn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    ap.add_argument("--db", default=None)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--days", type=int, default=7,
                    help="the default window being priced (days)")
    ap.add_argument("--cache-kib", type=int, default=64_000,
                    help="SQLite page cache per connection; shrink it to "
                         "approximate the live box's memory pressure")
    ap.add_argument("--keep", action="store_true",
                    help="keep the built database and the per-arm copies")
    args = ap.parse_args()

    unbounded = unbounded_sql()
    since = NOW_MS - args.days * 86_400_000
    base = pathlib.Path(args.db or "fair_price_window_bench.db")
    build(base, args.rows)

    print("\nbuilding arms")
    paths, conns, stmts = {}, {}, {}
    for label, create, analyze, indexed_by in ARMS:
        paths[label] = prepare(base, label, create, analyze)
        conns[label] = open_arm(paths[label], args.cache_kib)
        stmts[label] = bounded_sql(indexed_by)
    sizes = {label: os.path.getsize(p) for label, p in paths.items()}
    base_size = os.path.getsize(base)

    total_rows = conns["today"].execute(
        "SELECT COUNT(*) FROM fair_prices").fetchone()[0]
    in_window = conns["today"].execute(
        "SELECT COUNT(*) FROM fair_prices WHERE computed_ms >= ?",
        (since,)).fetchone()[0]
    print(f"\n{total_rows:,} rows, {in_window:,} inside the {args.days}-day "
          f"window ({in_window / total_rows:.3%})")

    # Refuse outright if a configuration changes the ANSWER rather than the
    # speed. Every figure below would be void.
    answers = {
        label: [tuple(r) for r in conn.execute(stmts[label],
                                               {"since": since}).fetchall()]
        for label, conn in conns.items()
    }
    for label, rows in answers.items():
        if rows != answers["today"]:
            print(f"REFUSED: {label} changed the census itself, not merely "
                  "its speed.")
            return 1
    print(f"all arms return the same {len(answers['today'])} market rows, "
          "compared elementwise")

    print("\nplans (bounded statement)")
    for label, conn in conns.items():
        for line in [r[3] for r in conn.execute(
                "EXPLAIN QUERY PLAN " + stmts[label], {"since": since})]:
            print(f"  {label:24s} {line}")

    # Interleaved, and that is the whole design: absolute milliseconds move by
    # 3x between sessions on page-cache residency alone, so two arms timed
    # minutes apart are not comparable. The paired RATIO is the claim.
    print(f"\ntiming, round-robin, {args.rounds} rounds, "
          f"{args.cache_kib // 1000} MB page cache")
    labels = ["unbounded"] + [a[0] for a in ARMS]
    print("round  " + "  ".join(f"{c:>22s}" for c in labels))
    samples: dict[str, list[float]] = {c: [] for c in labels}
    for r in range(args.rounds):
        row = []
        t0 = time.perf_counter()
        conns["today"].execute(unbounded).fetchall()
        ms = (time.perf_counter() - t0) * 1000
        samples["unbounded"].append(ms)
        row.append(f"{ms:22.1f}")
        for label, *_ in ARMS:
            t0 = time.perf_counter()
            conns[label].execute(stmts[label], {"since": since}).fetchall()
            ms = (time.perf_counter() - t0) * 1000
            samples[label].append(ms)
            row.append(f"{ms:22.1f}")
        print(f"{r:5d}  " + "  ".join(row))

    def median(xs: list[float]) -> float:
        return sorted(xs)[len(xs) // 2]

    print()
    today = median(samples["unbounded"])
    for label in labels:
        grown = 0 if label == "unbounded" else sizes[label] - base_size
        print(f"  {label:24s} best {min(samples[label]):9.1f} ms   "
              f"median {median(samples[label]):9.1f} ms   "
              f"{today / median(samples[label]):8.2f}x vs today   "
              f"+{grown / 1e6:7.1f} MB   "
              f"{grown / total_rows:5.1f} B/row   "
              f"{grown / total_rows * DEFAULT_ROWS / 1e6:5.0f} MB on live")

    print("\nwrite cost, one 400-row pass, best of five")
    for label, *_ in ARMS:
        print(f"  {label:24s} {pass_insert_ms(conns[label]):8.2f} ms")

    for conn in conns.values():
        conn.close()
    if not args.keep:
        for path in paths.values():
            for suffix in ("", "-wal", "-shm"):
                p = pathlib.Path(str(path) + suffix)
                if p.exists():
                    p.unlink()

    print("\nRead the `today` row first: it is the window with nothing behind "
          "it, and if it does not beat")
    print("`unbounded` then the bound alone bought nothing. Then read which "
          "arms the PLANS show actually")
    print("using the new index -- an index the planner declines is 0 ms of "
          "benefit at full price.")
    print("The paired RATIO is the claim; the milliseconds belong to this "
          "machine. Live is I/O-bound against")
    print(">5 GB with 2.0 GB of RAM, so the ratio here is a FLOOR and never a "
          "magnitude (ADR 0141).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
