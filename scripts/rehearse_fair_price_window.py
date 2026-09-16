r"""Rehearse the `fair-prices-by-market` bound on a paced copy of the live file.

    flyctl ssh console -a kalshi-cockpit \
      -C "python /app/scripts/rehearse_fair_price_window.py"

**Read-only against live.** The live database is opened `mode=ro` and every
timing, every `EXPLAIN` and the one `ANALYZE` run against a COPY, which is
deleted before this exits. Nothing here writes to `/data/cockpit.db`.

Why it exists
-------------
`scripts/measure_fair_price_window_index.py` priced the change on a modelled
table and returned an answer that overturns the brief: the index the work was
approved to build **is never chosen by the planner**, and what makes the window
seekable is `sqlite_stat1`. With statistics the planner runs the EXISTING
`idx_fair_market_computed` as a skip-scan (`ANY(market) AND computed_ms>?`)
because `market` has a handful of distinct values; without them it scans the
whole index and the window buys a fifth of what it could.

Two things about that answer can only be checked here:

1. **`market` cardinality is modelled in the bench and real here.** The
   skip-scan decision turns on it. If live's `fair_prices.market` holds
   hundreds of distinct prop keys rather than a handful, the whole result
   changes and this script says so before anything ships.
2. **`ANALYZE` is a global planner input, and the two hottest reads of
   `fair_prices` were tuned WITHOUT it.** `parlays.CANDIDATE_SQL` earned its
   `MULTI-INDEX OR` plan (ADR 0134, schema v37) on a statistics-free planner,
   and `runner.py`'s per-outcome dedupe lookup runs once per outcome per pass.
   A plan that good can be lost as easily as won. This script diffs the plan
   and the TIME of both, before and after, and refuses the change if either
   regresses.

ADR 0141 is why the output is a time and not a plan: `EXPLAIN QUERY PLAN` names
the access method and never the rows it touches.

The copy follows the procedure ADR 0134's deploy used
(`docs/measurements/2026-09-10-the-ladder-floor-oom-cycles-the-recorder.md`
§6): `sqlite3.backup`, 2,000 pages per 20 ms, so the recorder and the desk keep
the disk between bursts. That copy took 640 s for 5.17 GB; budget more now.

What this does NOT establish
----------------------------
- **Nothing about any read of `fair_prices` not listed in `STATEMENTS`.** The
  list is hand-built from a walk of `backend/` and is a claim about that walk,
  not about the table. A reader added later is not covered.
- **Nothing about the other tables.** `ANALYZE fair_prices` writes
  `sqlite_stat1` rows for that table's indexes only, and SQLite falls back to
  its built-in estimates for an index with no row -- but *falls back* is the
  documented behaviour, not something measured here.
- **Nothing about statistics going stale.** This is one snapshot against a
  table the recorder writes to continuously.
- **The copy is quiescent and live is not.** Every timing here runs with no
  concurrent writer, so it is a floor on the real cost and never a ceiling.
- **The copy may lag the live file by up to a checkpoint.** The source is
  opened `mode=ro`, and this repo has recorded that a read-only connection
  cannot read the WAL
  (`docs/measurements/2026-08-19-the-prune-loses-to-the-writer.md`). So rows
  written since the last checkpoint are absent from the copy. That is
  immaterial to every timing here -- a few minutes of recorder output against
  ten million rows changes no plan and no distribution -- but the row counts
  printed below are NOT the live counts, and must not be quoted as them.
- **It does not prove the census is worth running at all.** It prices making
  it cheap, which is a different question from whether anyone should.

**And this script is itself the expense ADR 0157 names.** It copies and reads
the whole live file, which evicts a page cache that can hold at most ~27% of
it, so the desk is cold afterwards. Run it on a quiet clock, and run
`scripts/warm_read_path.py` immediately after -- the script prints that
reminder at the end for the same reason.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import signal
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

from backend.parlays import CANDIDATE_SQL  # noqa: E402
from backend.runner import (  # noqa: E402
    _FAIR_PRICE_KEY_COLUMNS,
    _FAIR_PRICE_PAYLOAD_COLUMNS,
)
from scripts import inspect_live_db_decisions as decisions  # noqa: E402

LIVE_DB = "/data/cockpit.db"

#: **`sqlite3.backup` is not usable here, and finding out cost a live run.**
#:
#: The v37 rehearsal
#: (`docs/measurements/2026-09-10-the-ladder-floor-oom-cycles-the-recorder.md`
#: §6) copied 5.17 GB in 640 s with `sqlite3.backup`, paced 2,000 pages per
#: 20 ms, and that worked. Repeating it on 2026-09-16 against 6.32 GB did not,
#: and the way it failed is the part worth keeping: **SQLite restarts a backup
#: from page 1 whenever the source is written by another connection.** The
#: recorder writes every ~900 s; this copy needs ~1,200 s; so it restarted
#: forever. From outside it looked like a working copy -- the destination's
#: mtime advanced the whole time -- while its size sat frozen at the
#: high-water mark of the best attempt, 2,744,320,000 bytes, for six minutes.
#: There is no error and no progress output. It would have run until the ssh
#: session was killed.
#:
#: `VACUUM INTO` has no such semantics: it is one statement under one read
#: transaction, so a concurrent writer cannot restart it. Pacing and the
#: deadline come from a progress handler instead, which does fire during
#: `VACUUM INTO` (measured: 544 calls in 3.1 s at 50,000 opcodes) and can
#: abort it cleanly.
#:
#: **What that costs the measurement, and in which direction.** `VACUUM INTO`
#: writes a COMPACTED copy: the b-trees come out defragmented, so a scan on
#: the copy is more sequential than the same scan on live. That makes scans
#: relatively cheaper, which **understates** the benefit of turning a scan
#: into a seek -- the conservative direction, and the reason it is acceptable
#: here. The before/after ratio is unaffected either way, because both arms
#: run against the same copy.
VACUUM_PACE_OPCODES = 50_000
VACUUM_PACE_SLEEP_S = 0.001

ANALYZE_STEPS = ("PRAGMA analysis_limit=1000", "ANALYZE fair_prices")

#: Below this, a before/after ratio is the timer and not the query. Not
#: tuned: it is one millisecond, the resolution at which "it got 30%
#: slower" stops being a sentence about SQLite at all.
MIN_MEASURABLE_MS = 1.0

#: The per-outcome dedupe lookup, rebuilt from `runner.py`'s own column tuples
#: rather than retyped -- the same construction the writer performs at
#: `backend/runner.py:1204`, so it cannot drift from what runs.
RUNNER_LOOKUP_SQL = (
    "SELECT id, " + ", ".join(_FAIR_PRICE_PAYLOAD_COLUMNS) + " "
    "FROM fair_prices WHERE "
    + " AND ".join(f"{column} IS ?" for column in _FAIR_PRICE_KEY_COLUMNS)
    + " ORDER BY computed_ms DESC, id DESC LIMIT 1"
)


def census_sql() -> str:
    """The bounded census, out of the shipped module or synthesised from it."""
    sql = decisions._SQL_FAIR_PRICES_BY_MARKET
    if ":since" in sql:
        return sql
    return sql.replace(
        "FROM fair_prices GROUP BY",
        "FROM fair_prices WHERE computed_ms >= :since GROUP BY",
    )


def unbounded_sql() -> str:
    """The census as it stands on live today: no predicate at all.

    Derived by REMOVING the bound from the shipped statement rather than kept
    as a second literal, so the "before" arm is the shipped query minus
    exactly the thing being priced, and cannot drift into being some other
    query that merely resembles it.
    """
    sql = census_sql().replace("WHERE computed_ms >= :since ", "")
    if ":since" in sql:
        raise SystemExit(
            "REFUSED: could not strip the bound from the census statement, so "
            "the 'before' arm would be the bounded query wearing the "
            "unbounded label. Every ratio below would be 1.00x for the wrong "
            "reason."
        )
    return sql


def section_a_sql(indexed_by: str = "") -> str:
    """Section A, optionally forced onto `idx_odds_commence`.

    Section A's `commence_ms` bound does NOT seek: `idx_odds_window` (schema
    v41) leads with `market`, covers the select list and satisfies the
    `GROUP BY`, so the planner scans it whole and `commence_ms` -- its fourth
    column -- is applied as a filter. `ANALYZE` does not change that, measured
    both ways.

    Whether forcing `idx_odds_commence` is an improvement is a TIMING question
    and cannot be reasoned out: the forced plan seeks the range but then
    fetches every in-window row from the table, and a seven-day window on
    `odds_snapshots` may be a large fraction of it. Both arms run here, on the
    real distribution, and the one that wins wins. ADR 0141.
    """
    sql = decisions._SQL_ODDS_SNAPSHOTS_BY_MARKET
    if indexed_by:
        sql = sql.replace("FROM odds_snapshots", f"FROM odds_snapshots{indexed_by}")
    return sql


def plan(conn: sqlite3.Connection, sql: str, params) -> list[str]:
    return [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


def timed(conn: sqlite3.Connection, sql: str, params, reps: int) -> float:
    """Best of `reps`, in ms. Best rather than median: the copy is quiescent
    and the worst readings are the OS, not the query."""
    best = None
    for _ in range(reps):
        t0 = time.perf_counter()
        conn.execute(sql, params).fetchall()
        dt = (time.perf_counter() - t0) * 1000
        best = dt if best is None else min(best, dt)
    return best or 0.0


def snapshot_copy(src: str, dst: pathlib.Path, deadline_s: float,
                  pace_sleep_s: float) -> float:
    """`VACUUM INTO`, paced and deadline-guarded. Returns seconds elapsed.

    See the note beside `VACUUM_PACE_OPCODES` for why this is not
    `sqlite3.backup`. The progress handler does three jobs: it yields the disk
    back between bursts, it enforces a wall-clock deadline so a pathology
    ABORTS instead of running until someone notices, and it prints progress so
    a stall is visible while it is happening rather than afterwards.
    """
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    t0 = time.perf_counter()
    last_print = [t0]

    def handler() -> int:
        now = time.perf_counter()
        if now - t0 > deadline_s:
            return 1  # aborts the statement; sqlite3 raises OperationalError
        if now - last_print[0] >= 30.0:
            last_print[0] = now
            size = dst.stat().st_size if dst.exists() else 0
            print(f"    ... {now - t0:5.0f} s, {size / 1e9:5.2f} GB written",
                  flush=True)
        time.sleep(pace_sleep_s)
        return 0

    source.set_progress_handler(handler, VACUUM_PACE_OPCODES)
    try:
        source.execute("VACUUM INTO ?", (str(dst),))
    finally:
        source.set_progress_handler(None, 0)
        source.close()
    return time.perf_counter() - t0


def free_bytes(path: str) -> int:
    """Free bytes on the volume, or -1 where the platform cannot say.

    `shutil.disk_usage` rather than `os.statvfs`, which does not exist on
    Windows -- this script runs in the Linux container, but it is imported by
    the test that checks it parses, and an import-time platform assumption
    would make that test a Linux-only one without saying so.
    """
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return -1


def unlink_all(path: pathlib.Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        p = pathlib.Path(str(path) + suffix)
        if p.exists():
            p.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=LIVE_DB)
    ap.add_argument("--copy-to", default="/data/rehearse-fair-prices.db")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--deadline-s", type=float, default=1800.0,
                    help="abort the copy after this many seconds rather than "
                         "letting a pathology run unbounded (default 1800)")
    ap.add_argument("--pace-sleep-s", type=float, default=VACUUM_PACE_SLEEP_S,
                    help="seconds slept per progress-handler call, to leave "
                         "the disk to the recorder; 0 copies flat out")
    ap.add_argument("--cache-kib", type=int, default=8_000,
                    help="SQLite page cache per connection, small on purpose: "
                         "this box has 2.0 GB and no swap")
    ap.add_argument("--skip-unbounded", action="store_true",
                    help="skip timing the census as it stands today. It is a "
                         "full read of fair_prices and it is the number this "
                         "whole change is measured against, so skip it only "
                         "if the box is already in trouble")
    args = ap.parse_args()

    now_ms = int(time.time() * 1000)
    since = now_ms - args.days * 86_400_000
    src = pathlib.Path(args.db)
    dst = pathlib.Path(args.copy_to)

    # **A dropped ssh must not leave a multi-gigabyte orphan on the volume.**
    # `finally` does not run when the process is signalled, and on 2026-09-16
    # that left `/data` holding a 2.7 GB file that `df` still counted after it
    # was unlinked, because the surviving process had it open. These turn a
    # signal into a normal exit so the `finally` below fires.
    def _bail(signum, _frame):
        print(f"\nsignal {signum}: deleting the copy and exiting")
        unlink_all(dst)
        raise SystemExit(130)

    for name in ("SIGTERM", "SIGHUP", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _bail)
            except (ValueError, OSError):
                # Not the main thread, or not supported on this platform.
                pass

    print(f"sqlite {sqlite3.sqlite_version}   python {sys.version.split()[0]}")
    if tuple(int(n) for n in sqlite3.sqlite_version.split(".")) < (3, 32, 0):
        print("REFUSED: PRAGMA analysis_limit needs SQLite 3.32; this build "
              "would run a FULL ANALYZE, which is a table scan per index.")
        return 1

    live = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    live.execute("PRAGMA cache_size = %d" % -args.cache_kib)
    has_stats = live.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
        "AND name='sqlite_stat1'").fetchone()[0]
    print(f"live file          {src}  {src.stat().st_size:,} bytes")
    print(f"free on volume     {free_bytes(str(src.parent)):,} bytes")
    print(f"sqlite_stat1       {'PRESENT' if has_stats else 'ABSENT'}"
          "   (absent is the state the bench modelled)")

    # The one fact the bench could only model. Bounded so it is not itself the
    # expensive read: DISTINCT over the index, not over the table.
    t0 = time.perf_counter()
    markets = [r[0] for r in live.execute(
        "SELECT DISTINCT market FROM fair_prices").fetchall()]
    print(f"distinct markets   {len(markets)}  {sorted(markets)}  "
          f"({(time.perf_counter() - t0) * 1000:.0f} ms)")
    if len(markets) > 40:
        print("NOTE: that is far more than the bench modelled. A skip-scan "
              "over this many values is not the same purchase; read the "
              "timings below before believing the bench at all.")
    live.close()

    if dst.exists():
        print(f"REFUSED: {dst} already exists. A previous rehearsal did not "
              "clean up, and overwriting it would hide that.")
        return 1

    # **The volume has been filled before**
    # (`docs/measurements/2026-08-16-volume-full-incident.md`), and this script
    # writes a second copy of the largest file on it. The margin is the file's
    # own size again on top of the copy, not a percentage: what must survive
    # the run is the recorder's ability to keep writing WAL to the REAL
    # database while a file the same size sits beside it.
    needed = src.stat().st_size * 2
    free = free_bytes(str(dst.parent))
    if free < 0:
        print("REFUSED: cannot read free space on the target volume, so the "
              "copy would be made blind.")
        return 1
    if free < needed:
        print(f"REFUSED: {free:,} bytes free, {needed:,} needed (the copy "
              f"plus the live file's size again as margin). Rehearse after "
              "the volume has been extended -- `scripts/extend_volume_"
              "wizard.sh` -- not by shaving the margin.")
        return 1

    # **Printed so the copy can be killed from another shell.** A dropped
    # `flyctl ssh` does NOT take this process with it: on 2026-09-16 the client
    # was killed and PID 722 kept looping on the box, holding 2.7 GB of deleted
    # file open so the volume did not reclaim it. The signal handlers below are
    # the fix; the PID is the fallback when the signal never arrives.
    print(f"\npid {os.getpid()}")
    print(f"copying to {dst} with VACUUM INTO, deadline {args.deadline_s:.0f} s "
          f"...")
    try:
        try:
            elapsed = snapshot_copy(str(src), dst, args.deadline_s,
                                    args.pace_sleep_s)
        except sqlite3.OperationalError as exc:
            # The deadline aborts the statement as `interrupted`. Say which
            # it was: a genuine SQLite error and a hit deadline read the same
            # from here, and only one of them means "re-run with more time".
            print(f"\nREFUSED: the copy did not finish -- {exc}. If that says "
                  f"'interrupted', the {args.deadline_s:.0f} s deadline fired; "
                  "re-run with --deadline-s raised, on a quieter clock. "
                  "Nothing was measured.")
            return 1
        copied = dst.stat().st_size
        print(f"copied {copied:,} bytes in {elapsed:.0f} s "
              f"({copied / max(elapsed, 1e-9) / 1e6:.1f} MB/s); "
              f"source was {src.stat().st_size:,}, so the copy is "
              f"{100 * copied / max(src.stat().st_size, 1):.1f}% of it -- "
              "VACUUM INTO compacts, which is why it is smaller and why its "
              "scans are more sequential than live's")
        print(f"free now {free_bytes(str(dst.parent)):,} bytes")

        conn = sqlite3.connect(dst)
        conn.execute("PRAGMA cache_size = %d" % -args.cache_kib)
        rows = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]
        in_window = conn.execute(
            "SELECT COUNT(*) FROM fair_prices WHERE computed_ms >= ?",
            (since,)).fetchone()[0]
        print(f"\nfair_prices        {rows:,} rows, {in_window:,} inside the "
              f"{args.days}-day window ({in_window / max(rows, 1):.3%})")

        bounded = census_sql()
        statements = {
            "census (bounded)": (bounded, {"since": since}),
            "section A (bounded)": (section_a_sql(), {"since": since}),
            "section A (INDEXED BY idx_odds_commence)": (
                section_a_sql(" INDEXED BY idx_odds_commence"),
                {"since": since},
            ),
            "CANDIDATE_SQL": (CANDIDATE_SQL, (since, since, now_ms)),
            "runner dedupe lookup": (
                RUNNER_LOOKUP_SQL,
                (1, "h2h", "Home", None, None),
            ),
        }
        if not args.skip_unbounded:
            statements["census (unbounded, today)"] = (unbounded_sql(), ())
            statements["section A (unbounded, today)"] = (
                section_a_sql().replace("WHERE commence_ms >= :since ", ""), (),
            )

        before = {
            label: (plan(conn, sql, p), timed(conn, sql, p, args.reps))
            for label, (sql, p) in statements.items()
        }

        print("\nrunning ANALYZE on the copy ...")
        t0 = time.perf_counter()
        for stmt in ANALYZE_STEPS:
            conn.execute(stmt)
        conn.commit()
        analyze_s = time.perf_counter() - t0
        stat_rows = conn.execute(
            "SELECT tbl, idx, stat FROM sqlite_stat1 ORDER BY tbl, idx"
        ).fetchall()
        print(f"ANALYZE            {analyze_s:.1f} s, {len(stat_rows)} "
              "sqlite_stat1 rows")
        for tbl, idx, stat in stat_rows:
            print(f"    {tbl:24s} {str(idx):28s} {stat}")

        after = {
            label: (plan(conn, sql, p), timed(conn, sql, p, args.reps))
            for label, (sql, p) in statements.items()
        }

        print("\n" + "=" * 78)
        regressions = []
        # **A check that cannot fail is not a check.** On a table small enough
        # that every statement returns in under a millisecond, the ratio below
        # is timer noise and "no regression" means "nothing was measured".
        # Smoke-running this against a five-row database reported a clean pass,
        # which is exactly the reading someone would have quoted.
        unmeasurable = [
            label for label in statements
            if before[label][1] < MIN_MEASURABLE_MS
        ]
        for label in statements:
            pb, tb = before[label]
            pa, ta = after[label]
            verdict = "plan UNCHANGED" if pb == pa else "plan CHANGED"
            ratio = tb / ta if ta else float("inf")
            print(f"\n{label}")
            print(f"  before  {tb:10.1f} ms   {verdict}")
            for line in pb:
                print(f"      {line}")
            if pb != pa:
                print("  after's plan:")
                for line in pa:
                    print(f"      {line}")
            print(f"  after   {ta:10.1f} ms   {ratio:6.2f}x")
            # 1.25 is not a tuned threshold: it is wide enough that ordinary
            # timing noise on a quiescent copy does not trip it, and narrow
            # enough that a lost MULTI-INDEX OR could not hide inside it.
            if ta > tb * 1.25 and label not in unmeasurable:
                regressions.append((label, tb, ta))

        print("\n" + "=" * 78)
        if unmeasurable:
            print(f"UNMEASURABLE -- these ran in under {MIN_MEASURABLE_MS} ms "
                  "before the change, so their ratios are timer noise and "
                  "carry no verdict either way:")
            for label in unmeasurable:
                print(f"  {label}: {before[label][1]:.2f} ms")
            print("  On the live file this list should be EMPTY. If it is "
                  "not, the copy is not live's shape and nothing here was "
                  "tested.")
        print("\nSection A is a CHOICE, not a before/after: `bounded` and "
              "`INDEXED BY` above are two")
        print("plans for the same rows, both measured after ANALYZE. Take the "
              "faster one; if forcing the")
        print("index does not win, section A stays a filter and ADR 0159 says "
              "so rather than implying a seek.")
        if regressions:
            print("REGRESSED under ANALYZE -- do NOT ship the statistics step:")
            for label, tb, ta in regressions:
                print(f"  {label}: {tb:.1f} ms -> {ta:.1f} ms")
        else:
            print("No statement regressed by more than 25%. That is a "
                  "necessary condition for shipping ANALYZE, not a "
                  "sufficient one -- the copy is quiescent and the list of "
                  "statements is a hand-built claim.")
    finally:
        # Closed before the unlink, not after: on Windows the unlink raises on
        # an open handle and the copy survives, and a leftover copy makes the
        # NEXT run refuse. The container is Linux and would have deleted a
        # still-open file silently, which is worse.
        try:
            conn.close()
        except (NameError, sqlite3.Error):
            pass
        unlink_all(dst)
        print(f"\ncopy deleted; free on volume "
              f"{free_bytes(str(src.parent)):,} bytes")
        # **This script is itself the thing ADR 0157 is about.** Copying and
        # then reading a >5 GB file pulls it all through a page cache that
        # tops out near 1.49 GB on a 2.0 GB box, so the desk's own read path
        # has just been evicted -- and the person who pays for that is
        # whoever taps the desk next, minutes from now. Printed rather than
        # left in a docstring because the reminder has to reach the operator
        # who ran it, in the output they are already reading.
        print("\nNOW RUN, before you walk away:")
        print(f"    python /app/scripts/warm_read_path.py --db {src}")
        print("It pulls the parlay desk's read path back into the page cache "
              "(cold /api/parlays measured")
        print("20.5 s against a 25 s read budget). This run evicted it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
