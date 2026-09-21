"""The recorder loop's own health: memory, walks, failures, gaps, volume, pushes.

Queries: `loop-rss`, `walk-log`, `failure-journal`, `pass-gaps`,
`notifications`, `db-sizes`, `db-growth-by-table`,
`odds-snapshots-latest-price-timing`.

What these share is that none of them reads the evidence record. They read
the machine that grows it -- the resident set and WAL size per pass
(`loop_rss.jsonl`), which catalogue walk each pass took
(`loop_walk.jsonl`), what failed and whether the failure table could even
record it (`loop_failures.jsonl` beside `loop_failures`), the holes between
passes in `odds_sweep_log`, what reached the phone, and where the bytes on
the volume went. `pass-gaps` sits here rather than with the feed because its
reading is the *join* of a hole with the failures inside it: the gap is in
the sweep ledger and the diagnosis is in the loop's journal.

**Every SQL string in this module is a constant.** This module is imported by
`inspect_live_db.py`, is never run directly, and inherits every disclaimer in
that file's docstring.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from inspect_live_db_common import (
    Section,
    _derive_iso,
    _fetch,
    _iso,
)


# **The gaps in the pass ledger, which is how an outage is actually found.**
#
# `odds_sweep_log` gets a row from every completed pass, so the interesting
# thing in it is not the rows -- it is the holes between them. On 2026-08-25
# this had to be computed by hand, by pulling 400 rows and diffing them
# locally, which is exactly the "smuggle the code in with the question" drift
# this file exists to replace.
#
# The window function does the diff in SQLite. `-n` bounds the scan; the
# threshold is a bound parameter so a caller can ask about a quiet night at a
# different cadence without editing SQL.
_SQL_PASS_GAPS = (
    "WITH recent AS ("
    "  SELECT pass_ms FROM odds_sweep_log ORDER BY pass_ms DESC LIMIT ?"
    "), diffed AS ("
    "  SELECT pass_ms, pass_ms - LAG(pass_ms) OVER (ORDER BY pass_ms) AS gap_ms"
    "  FROM recent"
    ") SELECT gap_ms, pass_ms AS resumed_ms FROM diffed "
    "WHERE gap_ms > ? ORDER BY gap_ms DESC"
)

# `--gap-ms` is shared with `visit-freshness`, whose default is a different
# constant, so the flag defaults to None and each query applies its own.
_PASS_GAP_DEFAULT_MS = 1_200_000

# **What actually went to the phone, split by kind.**
#
# `/api/health` publishes `notifications.total_ever` and nothing else, so the
# only question it can answer is "more than before?" -- which on 2026-08-26 was
# read as three parlay pushes repeating when the parlay keys had not moved at
# all. A total is not a breakdown, and deducing a breakdown from one is how a
# wrong story survives.
# `suppressed` is selected beside `delivered`, and without it this section
# cannot be read. A row that was claimed and deliberately never sent (ADR
# 0076 burns the change key when the scheduled card goes out) is
# `delivered = 0` like a genuine failure, so `n - delivered` overstates the
# failures by up to `len(PUSHED_CARD_KEYS)` a day. Read on live 2026-08-27
# this section said `parlay_card 20 / 15 delivered` and the five were every
# one a burn.
_SQL_NOTIFICATIONS_BY_KIND = (
    "SELECT kind, COUNT(*) AS n, SUM(delivered) AS delivered, "
    "SUM(suppressed) AS suppressed, "
    "SUM(CASE WHEN delivered = 0 AND suppressed = 0 THEN 1 ELSE 0 END) "
    "AS undelivered, "
    "MIN(sent_ms) AS first_ms, MAX(sent_ms) AS last_ms "
    "FROM notifications GROUP BY kind ORDER BY n DESC"
)

_SQL_NOTIFICATIONS_TAIL = (
    "SELECT id, sent_ms, kind, key, delivered, suppressed, detail "
    "FROM notifications ORDER BY sent_ms DESC, id DESC"
)

# Every failure recorded across the same scan, so a gap can be read against
# them. Rows inside a hole mean the loop was FAILING; a hole with no rows means
# nothing came back to raise -- a wedged pass, or a container that went away.
# That contrast is the whole reason `loop_failures` exists (schema v22).
_SQL_LOOP_FAILURES_TAIL = (
    "SELECT id, failed_ms, pass_number, consecutive_failures, pass_kind, error "
    "FROM loop_failures ORDER BY failed_ms DESC, id DESC"
)


# ---------------------------------------------------------------------------
# Where the bytes went.
# ---------------------------------------------------------------------------
#
# **Written during the 2026-08-16 volume-full incident.** The disk report said
# `/data` was 100% used and that `cockpit.db` was 879 MiB of the 974 MiB
# volume -- three files, no stray artefacts, nothing to sweep up. That answers
# "what filled the disk" and leaves the question that decides the fix: prune a
# table, or buy a bigger volume?
#
# `dbstat` is a virtual table giving the real page count per btree, so it
# measures **stored bytes including indexes and overflow**, which is the
# quantity the volume actually charges for. Row counts cannot substitute: one
# table with 40,000 wide rows and another with 400,000 narrow ones sort in
# opposite orders under the two measures, and only one of them is the disk.
#
# It is compiled in on most builds and is **not guaranteed**, so the caller
# gets row counts as a labelled fallback rather than an error -- during an
# incident a partial answer beats a stack trace. The two are reported as
# separate sections so nobody reads a row count as a byte count.
#
# Read `page_count * page_size` against the file size as a completeness check:
# a large gap is free pages inside the file, which means a `VACUUM` would
# reclaim space without deleting a single row. That distinction is the whole
# decision, and it is why `freelist_count` is here.
_SQL_DB_PAGE_SUMMARY = (
    "SELECT (SELECT * FROM pragma_page_count()) AS page_count, "
    "(SELECT * FROM pragma_page_size()) AS page_size, "
    "(SELECT * FROM pragma_freelist_count()) AS freelist_count, "
    "(SELECT * FROM pragma_page_count()) * (SELECT * FROM pragma_page_size()) "
    "  AS total_bytes, "
    "(SELECT * FROM pragma_freelist_count()) * (SELECT * FROM pragma_page_size())"
    "  AS reclaimable_by_vacuum_bytes"
)

# `unused` is per-page dead space *inside* the bytes `pgsize` already charges
# for -- a page that is 4096 bytes on disk and 30% empty still costs 4096,
# and until this column existed that 30% was invisible: `pgsize` alone cannot
# tell "rows were added" from "pages bloated" apart, which is the exact gap
# #123 (docs/measurements/2026-09-18-where-the-database-bytes-are.md:104-111)
# named and the 2026-09-21 reading was spent without closing. `fill_pct` is
# derived, not stored by SQLite: `100 * (pgsize - unused) / pgsize`, i.e. the
# share of each btree's allocated bytes that is live. `NULLIF` on the
# denominator turns a zero-page btree's division into SQL NULL -- which
# `sqlite3` hands back as `None` -- rather than a fabricated 0 or a
# ZeroDivisionError; see `_q_db_sizes`'s docstring for what a low fill_pct
# does and does not establish. `pgsize` is left exactly as it was: every
# prior reading in the record (2026-09-18, 2026-09-21) used that column
# under this meaning, and changing it would silently break the comparison.
_SQL_DBSTAT = (
    "SELECT name, SUM(pgsize) AS bytes, SUM(unused) AS unused_bytes, "
    "COUNT(*) AS pages, "
    "ROUND(100.0 * (SUM(pgsize) - SUM(unused)) / NULLIF(SUM(pgsize), 0), 1) "
    "  AS fill_pct "
    "FROM dbstat GROUP BY name ORDER BY bytes DESC"
)


def _q_db_sizes(conn: sqlite3.Connection, args) -> list[Section]:
    """Stored bytes per table and index, largest first.

    What this does not establish
    ----------------------------
    - **Nothing about what may be deleted.** Size is not expendability. The
      largest table is usually the highest-frequency observation, which may
      also be the only record of a price at an instant.
    - **`reclaimable_by_vacuum_bytes` is not free disk.** `VACUUM` rebuilds
      into a temporary copy, so it needs roughly the file size *free* on the
      same filesystem before it can give any back. On a volume at 100% it is
      not runnable at all, which is exactly the trap this was written in.
    - **A dbstat row named for an index is charged to that index**, not folded
      into its table. Sum the table and its indexes before concluding what a
      table costs.
    - **`unused_bytes` is dead space *inside allocated pages* -- what a
      `VACUUM` would repack away, not free disk and not evidence a table's
      rows are expendable.** A page can be mostly `unused` while every row
      still on it matters; this column says nothing about which rows those
      are. A high `unused_bytes` (low `fill_pct`) on an INDEX in particular is
      the signature of heavy deletion under random insert order -- SQLite
      does not compact a btree on DELETE, it only marks the freed slot -- so
      a pruned, randomly-keyed index can grow in on-disk bytes with zero new
      rows written anywhere. That distinguishes "rows were added" from "pages
      bloated" for the first time this instrument has been able to; it does
      not by itself say which one happened for any given btree without also
      reading `db-growth-by-table`'s rowid high-water mark alongside it.
    """
    sections = [
        _fetch(
            conn,
            _SQL_DB_PAGE_SUMMARY,
            (),
            title="A. file-level pages (compare total_bytes against the file on disk)",
            cap=args.limit,
        )
    ]
    try:
        sections.append(
            _fetch(
                conn,
                _SQL_DBSTAT,
                (),
                title=(
                    "B. stored bytes per btree, via dbstat (indexes listed "
                    "separately; unused_bytes/fill_pct show dead space inside "
                    "allocated pages, not free disk)"
                ),
                cap=args.limit,
            )
        )
    except sqlite3.OperationalError:
        # dbstat is optional at compile time. Say so in the title rather than
        # returning row counts under a heading that implies bytes. This
        # fallback has no `unused`/`fill_pct` columns at all -- not columns
        # holding 0 -- because a row count carries no notion of page
        # fragmentation to report. Unreadable resolves to absent, never 0.
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        rows = [(n, conn.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]) for n in names]  # noqa: S608
        rows.sort(key=lambda r: r[1], reverse=True)
        sections.append(
            Section(
                title="B. dbstat UNAVAILABLE -- row counts only, NOT bytes",
                columns=("name", "rows"),
                rows=rows,
                cap=args.limit,
            )
        )
    return sections


# ---------------------------------------------------------------------------
# Which table grew -- without walking the file.
# ---------------------------------------------------------------------------
#
# `db-sizes` answers "where are the bytes" but costs a `dbstat` walk of the
# entire file (or, without `dbstat`, an unbounded `COUNT(*)` per table, built
# inline in `_q_db_sizes`'s fallback branch above -- itself WALKS_THE_FILE-
# shaped and only tolerated as a labelled fallback). Four sessions running
# have wanted a cheaper answer to a narrower question: which table grew
# since the last reading?
#
# `MAX(rowid)` on an ordinary rowid btree is a single read of the rightmost
# leaf page -- SQLite does not scan to find it, it descends the btree once.
# That is O(log n) in the page count, not O(n) in the row count, and it does
# not touch the rest of the file. Differencing two readings of it gives rows
# inserted since, without walking anything.
#
# `MAX(rowid)` is a BETTER answer than `COUNT(*)` for this question, not just
# a cheaper one: `kalshi_quotes` and `fair_prices` are pruned tables (ADR
# references in `docs/measurements/2026-09-18-where-the-database-bytes-are.md`
# -- `kalshi_quotes` has been flat at ~1.2 GB for nine days while its writer
# keeps inserting), so a count taken now and a count taken later can both be
# smaller than the number of rows actually written in between. A rowid
# high-water mark only goes up -- SQLite does not reuse a rowid after a
# DELETE on an ordinary (non-`AUTOINCREMENT`) table, and every table read
# here is declared `INTEGER PRIMARY KEY AUTOINCREMENT`, which is the one
# declaration that guarantees it never reuses one even across a full empty
# table (`backend/store/schema.sql`).
#
# Tables named per #120: the three that were >100 MB in the 2026-09-18
# byte census (`odds_snapshots`, `fair_prices`, `kalshi_quotes` -- "everything
# else" summed to 0.22 GB across 118 btrees, so nothing else cleared the
# threshold) plus `poll_log`, named explicitly in scope because it is the
# other table this question keeps getting asked about even though it did not
# appear in that census.
#
# One SQL string, each table's `MAX(rowid)` a separate scalar subquery `UNION
# ALL`-ed together -- not a Python loop building SQL, so this stays a
# constant like every other SQL string in this module. `MAX(rowid)` over a
# table with zero rows returns SQL NULL, which `sqlite3` hands back as
# `None` -- exactly the "unreadable resolves to None, never 0" convention,
# and it falls out of `MAX()`'s own semantics rather than needing a
# COALESCE that could hide a real zero-vs-empty distinction.
_SQL_DB_GROWTH_BY_TABLE = (
    "SELECT 'odds_snapshots' AS table_name, "
    "  (SELECT MAX(rowid) FROM odds_snapshots) AS max_rowid "
    "UNION ALL "
    "SELECT 'fair_prices', (SELECT MAX(rowid) FROM fair_prices) "
    "UNION ALL "
    "SELECT 'kalshi_quotes', (SELECT MAX(rowid) FROM kalshi_quotes) "
    "UNION ALL "
    "SELECT 'poll_log', (SELECT MAX(rowid) FROM poll_log)"
)


def _q_db_growth_by_table(conn: sqlite3.Connection, args) -> list[Section]:
    """`MAX(rowid)` per large table -- difference two readings for rows-since.

    Each row is one scalar subquery reading the rightmost leaf of a rowid
    btree: bounded work regardless of table size, no scan, no `dbstat`. Take
    this reading twice, subtract, and the difference is rows inserted in
    between -- for `kalshi_quotes` and `fair_prices`, which are pruned, that
    is a number `COUNT(*)` cannot give you, because pruning can make a later
    count smaller than an earlier one even while the table keeps growing.

    What this does not establish
    -----------------------------
    - **A rowid high-water mark is not a row count.** A DELETE does not lower
      it -- which is exactly why it measures inserts, not survivors. Do not
      read `max_rowid` as "how many rows are in the table now"; `db-sizes`'s
      row-count fallback answers that question, at WALKS_THE_FILE cost.
    - **It is not bytes.** A row's width varies table to table and even row
      to row, and no index is charged anywhere in this reading. `db-sizes`
      is the byte account; this is not a substitute for it.
    - **One reading is a level, not a rate.** This function reports the
      current high-water mark only. A rate needs two readings taken apart in
      time and a caller to do the subtraction and divide by the elapsed
      time -- neither happens here.
    """
    rows = conn.execute(_SQL_DB_GROWTH_BY_TABLE).fetchall()
    return [
        Section(
            title=(
                "MAX(rowid) per table -- NULL means the table has never had "
                "a row written (not the same as 0)"
            ),
            columns=("table_name", "max_rowid"),
            rows=[tuple(r) for r in rows],
            cap=args.limit,
        )
    ]


def _q_notifications(conn: sqlite3.Connection, args) -> list[Section]:
    """What reached the phone, by kind, then the tail in full.

    `key` is printed because for `parlay_card` it IS the dedupe rule -- rung
    plus sorted leg tickers -- so two rows with the same key would be a bug in
    `UNIQUE (kind, key)` and two with different keys explain a repeat push
    without anyone having to guess at it.

    What this does not establish
    ----------------------------
    - **That a delivered alert was read**, or was worth sending. `delivered`
      is Discord returning 2xx, nothing more.
    - **Why a kind is absent.** `opportunity` has never fired in this
      project's life, which is a fact about the Board being empty rather than
      about the notifier.

    `undelivered` is the column to read, not `n - delivered`. A `suppressed`
    row was claimed on purpose and never sent -- the scheduled parlay card
    burning the change channel's key -- so it is neither a delivery nor a
    failure, and only the explicit column tells the three apart.
    """
    kinds = _fetch(
        conn,
        _SQL_NOTIFICATIONS_BY_KIND,
        (),
        title="notifications: by kind -- delivered, suppressed, undelivered",
        cap=args.limit,
    )
    kinds = _derive_iso(kinds, "first_ms", "first_iso")
    kinds = _derive_iso(kinds, "last_ms", "last_iso")
    tail = _fetch(
        conn,
        _SQL_NOTIFICATIONS_TAIL,
        (),
        title=f"notifications: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    return [kinds, _derive_iso(tail, "sent_ms", "sent_iso")]


#: Where `scripts/run_loop.py` appends one line per pass. Derived from `--db`
#: rather than configured, because the writer derives it the same way: two


#: settings for one path is how a reader comes to inspect a file nobody writes.
WALK_LOG_NAME = "loop_walk.jsonl"


def _q_walk_log(conn: sqlite3.Connection, args) -> list[Section]:
    """Which catalogue walk each pass took, and every quote pass on the full one.

    The read path for `run_loop.record_pass_walk`. **Not a table** -- this is
    the one query here that reads a file beside the database, for the reason
    the file exists: one append per pass on the hot path, never joined against
    anything, and it has to survive the process that writes it.

    The reading is the PAIR of `kind` and `scope`, and neither alone:

        kind full  / scope full        the design -- something has to look at
                                       the whole catalogue or a newly-listed
                                       league is invisible forever
        kind quote / scope narrowed    the design -- ADR 0053's ~5x saving
        kind quote / scope full        the anomaly. `priceable_series` returned
                                       nothing, so the ~22s cadence is walking
                                       ~14,000 events. Nothing is broken enough
                                       to raise and nothing on the screen says
                                       so.

    `prev_discovered` is what the walk before it recognised, and it is what
    separates the two causes of an empty series list. A count that fell off a
    cliff -- 510 to 0 between two passes -- is a scope-classification
    regression. One that decayed over hours is a slate that emptied. They need
    opposite responses and the aggregate cannot tell them apart, which is why
    the number is stored per pass rather than summarised.

    **A missing file reports itself, and does not report zero rows.** An absent
    instrument and an instrument saying "no full walks" are the two readings
    this whole script exists to keep apart, and an empty section says the
    second in the voice of the first. So the absent case returns one row naming
    the path instead -- visible in both renderers, and impossible to skim past.

    What this does not establish
    ----------------------------
    - **Which league or rule stopped classifying.** The count is the alarm;
      the `discovery:` summary line is the diagnosis.
    - **Anything about a pass that died before its walk finished.** The line
      is written after the walk, so a wedged pass leaves none -- `pass-gaps`
      is the instrument for that half.
    - **Anything before 2026-08-29**, when the writer landed. An older window
      reads as a clean file whatever it did.
    """
    path = Path(args.db).resolve().parent / WALK_LOG_NAME
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [
            Section(
                title="walk-log: THE INSTRUMENT IS NOT THERE -- this is not 'no full walks'",
                columns=("problem", "path", "writer"),
                rows=[(str(exc), str(path), "scripts/run_loop.record_pass_walk")],
                cap=args.limit,
            )
        ]

    parsed: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            # A torn last line is what an append-only log looks like mid-write.
            # Counted by its absence rather than guessed at.
            continue

    columns = ("iso", "ms", "kind", "scope", "series", "events_seen", "prev_discovered")

    def _row(entry: dict) -> tuple[Any, ...]:
        ms = entry.get("ms")
        return (
            _iso(ms if isinstance(ms, int) else None),
            ms,
            entry.get("kind"),
            entry.get("scope"),
            entry.get("series"),
            entry.get("events_seen"),
            entry.get("prev_discovered"),
        )

    anomalies = [
        e for e in parsed
        if e.get("kind") == "quote" and e.get("scope") == "full"
    ]
    anomalies.reverse()
    tail = list(reversed(parsed))[: max(0, args.tail)]

    cap = args.limit
    return [
        Section(
            title=(
                f"walk-log: QUOTE passes that took the FULL walk, newest first "
                f"({len(anomalies)} of {len(parsed)} lines in {path.name})"
            ),
            columns=columns,
            rows=[_row(e) for e in anomalies[:cap]],
            truncated=len(anomalies) > cap,
            cap=cap,
        ),
        Section(
            title=f"walk-log: last {args.tail} passes, newest first",
            columns=columns,
            rows=[_row(e) for e in tail[:cap]],
            truncated=len(tail) > cap,
            cap=cap,
        ),
    ]


FAILURE_LOG_NAME = "loop_failures.jsonl"


def _q_failure_journal(conn: sqlite3.Connection, args) -> list[Section]:
    """Every pass failure as the JOURNAL saw it, beside what the TABLE kept.

    The read path for `db.record_loop_failure_durably`'s first layer -- a
    journal written on the hot path since 2026-08-30 that, until this query
    landed, had no reader anywhere in the repo.

    Why it is not `pass-gaps` with a different tail
    ----------------------------------------------
    `pass-gaps` reads the `loop_failures` TABLE, and the table is the artifact
    the journal exists to replace: a pass that dies mid-transaction poisons
    the shared connection with a stale WAL snapshot, so the failure row itself
    fails with "database is locked" (`record_loop_failure_durably`'s own
    docstring). The one failure class most worth counting is exactly the
    class the table goes quiet under.

    The reading is therefore the PAIR, and section 1 is the whole point: a
    journal line whose `ms` matches no `loop_failures.failed_ms` is a failure
    that happened and left no row. If section 1 is empty the table can be
    trusted for that window; if it is not, every count taken off the table is
    a floor.

    Section 2 carries the `diagnosis` lines, which are the durable recorder's
    own verdict and exist nowhere else: "a fresh connection wrote it" means
    the CONNECTION is poisoned and a restart cures it, while "the database
    itself refuses writes" is a different fact.

    **Read section 2 with two limits it cannot state itself**
    (`docs/measurements/2026-09-01-the-lock-failure-table-is-a-floor.md`
    carries the audit that found them):

    - **It samples the wrong moment.** The diagnosis is the lock state when
      the RECORD was attempted -- after the raise, the journal append and
      `record_loop_failure_durably`'s `rollback()` -- not at the failure. On
      lines before 2026-09-01 that rollback swallowed `sqlite3.Error`
      unrecorded, so "the shared connection still held the write lock" is
      NOT excluded by one of them. Section 3 carries the observation for
      every line written since.
    - **It does not name the holder.** The poller, the API's per-request
      connections, `maybe_checkpoint` and `store_closing_line` all produce
      this reading; `both refused` is CONSISTENT WITH the poller, not
      evidence for it. Separating them needs the poller's own start and
      finish times, which nothing here reads.

    **Section 3 is the first of those limits closing, and only the
    first.** Since 2026-09-01 the writer journals its `rollback()` --
    `in_transaction` before it, whether it raised, what it raised -- joined
    to what the row attempt did next. Read `in_transaction` FIRST: a
    rollback with no open transaction is a no-op that always succeeds, so
    `rollback_ok = True` alone does not separate "poison cleared" from
    "nothing to clear". It still does not name the holder. Lines before the
    field carry no rollback entry and the section counts them; **an empty
    section 3 is not "no rollback was attempted"** -- every journalled
    failure attempted one.

    And section 1 is a census, not a rate: its rows are SELECTED by having no
    table row, and `journal_only` is the only outcome that produces one. So
    "every line in section 1 says both connections refused" is a tautology,
    not a finding. The population to quote is section 4's -- how many
    recorded on the shared connection, how many on a fresh one, how many on
    neither.

    Section 5 renders the newest traceback one line per row: it is written
    only here (stdout retention on the machine is ~10 minutes) and a table
    cell cannot hold it.

    **A missing file reports itself, and does not report zero rows**, for
    `walk-log`'s reason: an absent instrument and one saying "no failures"
    are the two readings this script exists to keep apart.

    What this does not establish
    ----------------------------
    - **That a window with no lines was a healthy window.** The journal is
      written by the loop; a container that died between passes writes
      nothing at all. `pass-gaps` is the instrument for that half, and its
      own docstring says the pair is the reading.
    - **Anything before 2026-08-30**, when the durable recorder landed. An
      older window reads as a clean file whatever it did.
    - **Why a section-1 line has no row.** It says the row is absent, not the
      cause. `record_loop_failure_durably` returns `journal_only` only after a
      fresh connection ALSO refused, so a section-1 line with no matching
      section-2 diagnosis is the shape to look at twice: it means either the
      line predates the fallback, or the process died between the two writes.
    """
    path = Path(args.db).resolve().parent / FAILURE_LOG_NAME
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [
            Section(
                title=(
                    "failure-journal: THE INSTRUMENT IS NOT THERE -- this is "
                    "not 'no failures'"
                ),
                columns=("problem", "path", "writer"),
                rows=[(
                    str(exc),
                    str(path),
                    "backend.store.db.record_loop_failure_durably",
                )],
                cap=args.limit,
            )
        ]

    parsed: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # A torn last line is what an append-only log looks like mid-write.
            continue
        if isinstance(entry, dict):
            parsed.append(entry)

    # THREE shapes share the file, and classification is by an explicit
    # `kind` field since 2026-09-01. It used to be by key-ABSENCE -- a line
    # with no `diagnosis` key was a failure -- which is a rule that silently
    # miscounts the next shape somebody adds, and the rollback line added
    # that day would have been counted as a failure under it. Lines written
    # before the field carry no `kind`, so the old heuristic stays as the
    # fallback for exactly those; it is not dead code until the journal is.
    def _kind(entry: dict) -> str:
        declared = entry.get("kind")
        if isinstance(declared, str):
            return declared
        return "diagnosis" if "diagnosis" in entry else "failure"

    failures = [e for e in parsed if _kind(e) == "failure"]
    diagnoses = [e for e in parsed if _kind(e) == "diagnosis"]
    rollbacks = [e for e in parsed if _kind(e) == "rollback"]

    # Indexed by position, not by name: `connect_readonly` does not set a
    # `row_factory`, so every row here is a plain tuple.
    recorded_ms = {
        int(row[0])
        for row in conn.execute("SELECT failed_ms FROM loop_failures").fetchall()
        if row[0] is not None
    }

    def _in_table(entry: dict) -> Optional[bool]:
        ms = entry.get("ms")
        if not isinstance(ms, int):
            return None
        return ms in recorded_ms

    failure_columns = (
        "iso", "ms", "pass_number", "consecutive_failures", "pass_kind",
        "in_table", "error",
    )

    def _failure_row(entry: dict) -> tuple[Any, ...]:
        ms = entry.get("ms")
        return (
            _iso(ms if isinstance(ms, int) else None),
            ms,
            entry.get("pass_number"),
            entry.get("consecutive_failures"),
            entry.get("pass_kind"),
            _in_table(entry),
            entry.get("error"),
        )

    missing = [e for e in failures if _in_table(e) is False]
    missing.reverse()
    diagnoses_newest = list(reversed(diagnoses))
    tail = list(reversed(failures))[: max(0, args.tail)]

    # The three outcomes `record_loop_failure_durably` returns, recovered from
    # the artifacts rather than from a field -- the outcome string is logged
    # and never persisted. A diagnosis line is written only when the shared
    # connection refused, so its presence beside a surviving row is what
    # separates "recorded" from "recorded_on_fresh_connection".
    #
    # **This tally is the population to quote, and section 1's is not.**
    # Section 1's rows are selected by having no table row, and journal-only
    # is the only outcome that produces one, so a rate computed over them is
    # a tautology. An audit on 2026-09-01 caught exactly that being written
    # up as "14 of 14 say both connections refused".
    diagnosed_ms = {
        e["ms"] for e in diagnoses if isinstance(e.get("ms"), int)
    }
    on_shared = sum(
        1 for e in failures
        if _in_table(e) is True and e.get("ms") not in diagnosed_ms
    )
    on_fresh = sum(
        1 for e in failures
        if _in_table(e) is True and e.get("ms") in diagnosed_ms
    )

    # The cure attempt, joined to what happened next. `record_loop_failure_
    # durably` journals `kind: "rollback"` after its `rollback()` and before
    # the row attempt, so the pair answers the question neither half can:
    # `in_transaction = True, rollback_ok = True, then = recorded` is the
    # rollback working; the same two with `then = journal_only` is a cure
    # that did not cure.
    rollback_ms = {
        e["ms"] for e in rollbacks if isinstance(e.get("ms"), int)
    }

    def _outcome_of(ms: Any) -> Optional[str]:
        if not isinstance(ms, int):
            return None
        if ms not in recorded_ms:
            return "journal_only"
        return (
            "recorded_on_fresh_connection" if ms in diagnosed_ms
            else "recorded"
        )

    # A failure with no rollback line predates the observation, which landed
    # 2026-09-01. Reporting only the observations would let an empty section
    # read as "no rollback was ever attempted" on a journal whose every line
    # attempted one -- the `walk-log` failure mode, in the flattering
    # direction.
    unobserved = sum(
        1 for e in failures if e.get("ms") not in rollback_ms
    )
    rollbacks_newest = list(reversed(rollbacks))

    newest_tb = next((e for e in reversed(failures) if e.get("traceback")), None)
    tb_lines = (newest_tb.get("traceback") or "").splitlines() if newest_tb else []
    tb_stamp = (
        _iso(newest_tb.get("ms"))
        if newest_tb and isinstance(newest_tb.get("ms"), int)
        else None
    )

    cap = args.limit
    return [
        Section(
            title=(
                f"failure-journal: failures the TABLE never got "
                f"({len(missing)} of {len(failures)} journal failures have no "
                f"loop_failures row) -- a non-zero count makes every "
                f"table-derived count a FLOOR"
            ),
            columns=failure_columns,
            rows=[_failure_row(e) for e in missing[:cap]],
            truncated=len(missing) > cap,
            cap=cap,
        ),
        Section(
            title=(
                f"failure-journal: DIAGNOSIS lines, newest first "
                f"({len(diagnoses)} in {path.name}). TWO LIMITS: this is the "
                f"lock state when the RECORD was attempted -- after the pass "
                f"raised and after the rollback in section 3 -- not when the "
                f"pass failed; and it does not name the holder, so 'a fresh "
                f"connection was refused too' is CONSISTENT WITH the poller, "
                f"the API's connections and the checkpoint alike. Lines "
                f"written before 2026-09-01 end 'this is not the "
                f"poisoned-connection case' unconditionally; that sentence "
                f"is only earned in section 3's in_transaction = False row."
            ),
            columns=("iso", "ms", "diagnosis"),
            rows=[
                (
                    _iso(e.get("ms") if isinstance(e.get("ms"), int) else None),
                    e.get("ms"),
                    e.get("diagnosis"),
                )
                for e in diagnoses_newest[:cap]
            ],
            truncated=len(diagnoses) > cap,
            cap=cap,
        ),
        Section(
            title=(
                f"failure-journal: what the CURE ATTEMPT found "
                f"({len(rollbacks)} observations; {unobserved} failures "
                f"predate the field, which landed 2026-09-01 -- an empty "
                f"section is NOT 'no rollback was attempted'). READ "
                f"in_transaction FIRST: a rollback on a connection with no "
                f"open transaction is a no-op that always succeeds, so "
                f"rollback_ok = True alone is consistent with the poison "
                f"being cleared AND with there having been nothing to clear. "
                f"`then` is what the row attempt did next. NEITHER FIELD "
                f"NAMES THE HOLDER."
            ),
            columns=(
                "iso", "ms", "in_transaction", "rollback_ok",
                "rollback_error", "then",
            ),
            rows=[
                (
                    _iso(e.get("ms") if isinstance(e.get("ms"), int) else None),
                    e.get("ms"),
                    e.get("in_transaction"),
                    e.get("rollback_ok"),
                    e.get("rollback_error"),
                    _outcome_of(e.get("ms")),
                )
                for e in rollbacks_newest[:cap]
            ],
            truncated=len(rollbacks) > cap,
            cap=cap,
        ),
        Section(
            title=(
                f"failure-journal: last {args.tail} failures, newest first. "
                f"THE POPULATION: {len(failures)} journalled -- {on_shared} "
                f"recorded on the shared connection, {on_fresh} on a fresh "
                f"one, {len(missing)} on neither. Quote THIS, not section 1's "
                f"count, which is selected by its own outcome."
            ),
            columns=failure_columns,
            rows=[_failure_row(e) for e in tail[:cap]],
            truncated=len(tail) > cap,
            cap=cap,
        ),
        Section(
            title=(
                f"failure-journal: traceback of the newest failure "
                f"({tb_stamp or 'none carries one'}) -- written HERE and "
                f"nowhere else; stdout retention on the machine is ~10 min"
            ),
            columns=("line",),
            rows=[(line,) for line in tb_lines[:cap]],
            truncated=len(tb_lines) > cap,
            cap=cap,
        ),
    ]


#: Columns of `loop_rss.jsonl`, in the order they are rendered.
#:
#: Read with `.get(name)`, so a row written before a field existed reports
#: `None` for it rather than failing the whole read. That is not politeness:
#: the file is append-only and capped by tail, so on the day a field is added
#: the newest ~8,000 lines are a MIXTURE of shapes, and a reader that refuses
#: the old shape refuses the history the new field is being compared against.
#:
#: `None` and `0` are different answers here and the whole instrument turns on
#: it -- `wal_kb: null` is "not measured", `wal_kb: 0` is "the WAL is empty".
_LOOP_RSS_COLUMNS = (
    "ms",
    "kind",
    # `kind` names the pass ABOUT to run; `rss_kb` is the state the
    # previous pass left. `produced_by` is what says so, and dropping it
    # here is how a reader re-creates the misattribution the field was
    # added to prevent.
    "produced_by",
    "rss_kb",
    "available_kb",
    "wal_kb",
    "db_kb",
    "candidate_rows",
    "candidate_ms",
    "leg_price_link_ms",
    "leg_store_quotes_ms",
    # The checkpoint the PREVIOUS pass attempted, on the same terms as the
    # leg timings above. `wal_ckpt_busy = 1` beside a `wal_kb` that keeps
    # climbing is a reader holding the log open; `0` beside the same climb
    # says the readers are innocent and sends the diagnosis elsewhere.
    "wal_ckpt_mode",
    "wal_ckpt_busy",
    "wal_ckpt_log_frames",
    "wal_ckpt_moved_frames",
    "wal_ckpt_error",
)


def loop_rss_path(db_path: str) -> Path:
    """Where `scripts/run_loop.py` writes its per-pass line.

    One expression, shared, because the writer derives the same path from
    `args.db` and a reader that computed its own would go quietly blank the
    day either moved.
    """
    return Path(db_path).resolve().parent / "loop_rss.jsonl"


def _q_loop_rss(conn: sqlite3.Connection, args) -> list[Section]:
    """The per-pass memory and storage line, newest first.

    Not a table -- `loop_rss.jsonl` sits BESIDE the database on the data
    volume, for the reason `run_loop.py` gives: its job is to survive the
    process that writes it. `conn` is unused and is accepted so this reads
    like every other query here.

    The line carries two experiments at once and they are read differently:

        rss_kb, available_kb        the memory trajectory into a container
                                    death (2026-08-29)
        wal_kb, db_kb               the WAL that was 220 MiB against a 1.9 GB
                                    database and never reset
        candidate_rows, candidate_ms
                                    the `_match_candidates` scan the link leg
                                    is mostly made of
        leg_price_link_ms, leg_store_quotes_ms
                                    the two legs that blew out together while
                                    the HTTP walk stayed flat

    The discrimination the last three groups exist for: if the store leg
    tracks `wal_kb` while the link leg tracks `candidate_rows`, both
    mechanisms are real and additive; if BOTH legs track `wal_kb` while
    `candidate_rows` is flat, the query is an artifact and the storage layer
    is the whole story.

    **The four pass counts describe the PREVIOUS pass.** The line is written
    before any work, so everything on it is the state the pass began in.
    `record_pass_rss` owns that reasoning.

    What this does not establish
    ----------------------------
    - **Causation, from any pair of columns.** Two quantities that both grow
      with the age of a process correlate whatever is driving the legs. The
      informative case is a FLAT `candidate_rows` under a swinging leg.
    - **Anything before the field existed.** A `null` is "this row predates
      the column", not "the file was missing" -- the two are indistinguishable
      here and only `ms` separates them.
    - **That the record is complete.** The file is capped at
      `RSS_LOG_CAP_BYTES` by keeping the newest lines, and a container restart
      does not mark itself. Read it beside `pass-gaps`.
    """
    path = loop_rss_path(args.db)
    effective = max(0, min(args.tail, args.limit))
    rows: list[tuple[Any, ...]] = []
    malformed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        # Absent is a state, not an error: no pass has run on this volume, or
        # the loop is on a box with no `/proc` and never writes. Reported as
        # `0 rows`, which the renderer gives its own words.
        lines = []
    for line in reversed(lines):
        if len(rows) >= effective + 1:
            break
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(record, dict):
            malformed += 1
            continue
        rows.append(tuple(record.get(name) for name in _LOOP_RSS_COLUMNS))
    truncated = len(rows) > effective and effective == args.limit
    section = Section(
        title=(
            f"loop_rss.jsonl: last {effective} passes, newest first "
            f"({path}, {malformed} unparseable line(s) skipped)"
        ),
        columns=_LOOP_RSS_COLUMNS,
        rows=rows[:effective],
        truncated=truncated,
        cap=args.limit,
    )
    return [_derive_iso(section, "ms", "iso")]


def _q_pass_gaps(conn: sqlite3.Connection, args) -> list[Section]:
    """Holes in the pass ledger, and every failure recorded near them.

    **Read the two sections together -- separately they each mislead.** A gap
    alone does not say what happened; a failure alone does not say whether the
    record actually stopped. The reading is the join:

        gap with failures inside it   the loop was failing and retrying
        gap with no failures at all   nothing came back to raise: a wedged
                                      pass, or the container went away
        failures with no gap          transient, absorbed, record intact

    **The middle line is narrower evidence since 2026-08-28, and more
    useful.** `run_forever` now bounds a pass with `DEFAULT_PASS_DEADLINE_S`,
    so a hung *await* raises `PassDeadlineExceeded` and lands in the failures
    half. A gap that still carries no failure row therefore means the process
    was not running, or was blocked in a synchronous call the deadline cannot
    interrupt -- a long SQLite read against a 1.9 GB file being the standing
    candidate. The sixteen unexplained holes that preceded the deadline are
    `docs/measurements/2026-08-28-recorder-silence-is-chronic.md`.

    The threshold defaults to 1,200,000 ms -- above the 1,035s ceiling on a
    healthy shut-window sleep (900s x 1.15), so an ordinary quiet night does
    not fill the output with its own cadence.

    What this does not establish
    ----------------------------
    - **That a gap with no failures was a wedge.** A restart looks identical
      from inside the database. `flyctl machine status` settles it, and the
      machine event log is the only place that can.
    - **Anything before schema v22**, for the failures half. The table did not
      exist, so an old gap reads as "no failures" whatever its cause. Check
      `failed_ms` coverage before drawing the contrast on a historical window.
    """
    gap_ms = args.gap_ms if args.gap_ms is not None else _PASS_GAP_DEFAULT_MS
    gaps = _fetch(
        conn,
        _SQL_PASS_GAPS,
        (args.tail, gap_ms),
        title=(
            f"gaps over {gap_ms / 1000:.0f}s in the last {args.tail} "
            f"odds_sweep_log rows, widest first"
        ),
        cap=args.limit,
    )
    gaps = _derive_iso(gaps, "resumed_ms", "resumed_iso")
    failures = _fetch(
        conn,
        _SQL_LOOP_FAILURES_TAIL,
        (),
        title=f"loop_failures: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    return [gaps, _derive_iso(failures, "failed_ms", "failed_iso")]


_SQL_READ_INCIDENTS = (
    "SELECT seen_ms, kind, method, path, elapsed_ms, error, budget_ms "
    "FROM api_read_incidents ORDER BY seen_ms DESC"
)

_SQL_READ_INCIDENTS_BY_KIND = (
    "SELECT kind, count(*) AS n, min(seen_ms) AS first_ms, max(seen_ms) AS last_ms, "
    "max(elapsed_ms) AS worst_elapsed_ms FROM api_read_incidents GROUP BY kind"
)


def _q_read_incidents(conn: sqlite3.Connection, args) -> list[Section]:
    """The last N `api_read_incidents` rows (-n), newest first, beside a
    per-kind count. `read_budget` is the API's 25 s statement budget firing
    (a 503, which the screens render as "Backend unreachable"); `health_probe`
    is the loop's 2 s loopback probe failing, every pass, and is the sensitive
    instrument. The writer is best-effort with a one-second lock wait, so a
    count here is a FLOOR: a hit under hard contention may have no row and
    only a log line, and the log lives under a minute."""
    tail = _fetch(
        conn,
        _SQL_READ_INCIDENTS,
        (),
        title=f"api_read_incidents: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    by_kind = _fetch(
        conn,
        _SQL_READ_INCIDENTS_BY_KIND,
        (),
        title="api_read_incidents: count per kind (a FLOOR -- see the writer)",
        cap=args.limit,
    )
    return [
        _derive_iso(tail, "seen_ms", "seen_iso"),
        _derive_iso(by_kind, "last_ms", "last_iso"),
    ]


# ---------------------------------------------------------------------------
# odds_snapshots "latest price" reads, timed with and without idx_odds_event.
# ---------------------------------------------------------------------------
#
# Ticket #90, story #89 (task 4b). `idx_odds_event` --
# `(odds_event_id, market, fetched_ms DESC)`, `backend/store/schema.sql:286`
# -- was built for the access path `backend.runner` runs once per event per
# market to find what a book is currently quoting: `MAX(fetched_ms)` for an
# `(odds_event_id, market)` pair, then the row(s) at that stamp. All four of
# `book_quotes_for_event` (`backend/runner.py:525`), `prop_quotes_for_event`
# (`:666`), `spread_quotes_for_event` (`:812`) and `totals_quotes_for_event`
# (`:949`) run exactly this two-statement shape, differing only in the
# `market` filter (a literal for h2h/spreads/totals, a `json_each` IN-list
# for props). `_SQL_LATEST_PRICE_MAX` and `_SQL_LATEST_PRICE_ROWS` below are
# `book_quotes_for_event`'s two statements retyped as literals -- there is no
# named constant in `backend/runner.py` to import or pin against, the same
# situation `scoring-candidate-timing` is in with `backend/scoring.py`'s
# inline SQL, and for the same reason this script carries no import from
# `backend` at all.
#
# **This times ONE (odds_event_id, market) pair, not the table.** The pair is
# auto-picked as the one with the most rows (a "hot" fixture and market,
# `_SQL_PICK_HOTTEST_EVENT_MARKET`) unless `--odds-event-id` names one, in
# which case its own busiest market is picked (`_SQL_PICK_MARKET_FOR_EVENT`).
# Either way this is one instance of the access pattern, not a census of
# every instance the recorder runs in a pass.
#
# **"Without the index" means `NOT INDEXED`, not the index being absent, and
# that difference is not cosmetic.** SQLite's per-statement `NOT INDEXED`
# clause (https://sqlite.org/lang_indexedby.html) forbids the planner from
# routing that FROM-clause reference through ANY index, forcing a full table
# scan of `odds_snapshots` for that statement only. It simulates the READ-PATH
# shape the index's absence would produce -- SEARCH becomes SCAN -- on the
# SAME file, with the index's pages still resident in the page cache from
# whatever else touched them. It does NOT simulate `idx_odds_event` being
# absent from disk: no write-amplification saving, no smaller file, no freed
# page-cache room. Ticket #90's task explicitly forbids dropping the index
# here (the scar is `backend/store/schema.sql:242-262`'s comment on commit
# `2e66f36` -- "the plan was never the cost", restored the same day it was
# removed) so `NOT INDEXED` is the only mechanism this instrument uses, and it
# answers a narrower question than "what would happen if the index did not
# exist": it answers "what does the planner do to this exact statement when
# it is not allowed to use ANY index," which on a table with three other
# indexes over `odds_snapshots` columns is not automatically the same plan a
# truly index-less table would get either.
#
# **The run order is fixed and it is the unflattering one**, for the same
# reason `scoring-candidate-timing` runs its bounded text first: the variant
# expected to be faster (WITH the index available) runs FIRST, cold; the
# variant expected to be slower (`NOT INDEXED`) runs SECOND, with the same
# table already warm from the first run. So the indexed figure carries the
# cold-cache penalty and the `NOT INDEXED` figure gets the warm-cache
# discount -- any gap that survives that handicap is a FLOOR on the index's
# benefit, not a ceiling, and the reverse order would flatter the index.

_SQL_LATEST_PRICE_CENSUS = (
    "SELECT (SELECT COUNT(*) FROM odds_snapshots) AS odds_snapshots_rows, "
    "       (SELECT COUNT(*) FROM odds_snapshots WHERE odds_event_id = :oid) "
    "           AS rows_for_this_event, "
    "       (SELECT COUNT(*) FROM odds_snapshots WHERE odds_event_id = :oid "
    "           AND market = :mkt) AS rows_for_this_event_market"
)

#: Picks the busiest (odds_event_id, market) pair in the whole table -- used
#: when the caller does not name one with --odds-event-id. Walks the table by
#: design; this query's cost is WALKS_THE_FILE regardless of which branch runs.
_SQL_PICK_HOTTEST_EVENT_MARKET = (
    "SELECT odds_event_id, market, COUNT(*) AS n FROM odds_snapshots "
    "GROUP BY odds_event_id, market ORDER BY n DESC LIMIT 1"
)

#: Picks the busiest market WITHIN one caller-named event.
_SQL_PICK_MARKET_FOR_EVENT = (
    "SELECT market, COUNT(*) AS n FROM odds_snapshots "
    "WHERE odds_event_id = ? GROUP BY market ORDER BY n DESC LIMIT 1"
)


def _latest_price_max_sql(not_indexed: bool) -> str:
    """`book_quotes_for_event`'s first statement (`backend/runner.py:542-545`),
    retyped, with `NOT INDEXED` appended when simulating the index's absence.
    """
    table = "odds_snapshots NOT INDEXED" if not_indexed else "odds_snapshots"
    return (
        f"SELECT MAX(fetched_ms) AS m FROM {table} "
        "WHERE odds_event_id = ? AND market = ?"
    )


def _latest_price_rows_sql(not_indexed: bool) -> str:
    """`book_quotes_for_event`'s second statement (`backend/runner.py:550-554`),
    retyped, with `NOT INDEXED` appended when simulating the index's absence.
    """
    table = "odds_snapshots NOT INDEXED" if not_indexed else "odds_snapshots"
    return (
        "SELECT bookmaker, outcome_name, price_decimal, book_updated_ms, "
        f"fetched_ms, commence_ms FROM {table} "
        "WHERE odds_event_id = ? AND market = ? AND fetched_ms = ?"
    )


def _run_latest_price_whole(
    conn: sqlite3.Connection, not_indexed: bool, oid: str, market: str
) -> tuple[float, int]:
    """Run both statements of the latest-price read back to back and time the
    pair together, the way `book_quotes_for_event` actually runs them: the
    second statement depends on the first's `MAX(fetched_ms)`."""
    started = time.perf_counter()
    max_row = conn.execute(
        _latest_price_max_sql(not_indexed), (oid, market)
    ).fetchone()
    fetched_ms = max_row[0] if max_row else None
    if fetched_ms is None:
        rows: list[Any] = []
    else:
        rows = conn.execute(
            _latest_price_rows_sql(not_indexed), (oid, market, fetched_ms)
        ).fetchall()
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    return elapsed_ms, len(rows)


def _run_latest_price_max_alone(
    conn: sqlite3.Connection, not_indexed: bool, oid: str, market: str
) -> tuple[float, int]:
    """Time just the `MAX(fetched_ms)` statement -- the half `idx_odds_event`'s
    `fetched_ms DESC` ordering most directly targets."""
    started = time.perf_counter()
    rows = conn.execute(_latest_price_max_sql(not_indexed), (oid, market)).fetchall()
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    return elapsed_ms, len(rows)


def _q_odds_snapshots_latest_price_timing(
    conn: sqlite3.Connection, args
) -> list[Section]:
    """Time `odds_snapshots`' "latest price" read, with and without
    `idx_odds_event` available to the planner, on one (odds_event_id, market)
    pair.

    Six sections: a census of what the pair reads over, the four wall times
    (plus an agreement check) in the order they were taken, then
    `EXPLAIN QUERY PLAN` for all four statements (the MAX and the row fetch,
    indexed and `NOT INDEXED`).

    What this does not establish
    ----------------------------
    - **Not whether `idx_odds_event` is safe to drop.** `NOT INDEXED` forces a
      full scan for one statement on one connection; it does not remove the
      index's write cost, its page-cache footprint, or its benefit to any
      OTHER statement that reaches for it (`idx_odds_event` is shared with the
      write path and with `parlay-candidates-timing`'s subquery via the
      commence-index companion). See the module comment above for exactly
      what the mechanism does and does not simulate -- do not read a gap here
      as "dropping the index would cost this much."
    - **Not what a live request costs.** One statement pair on an idle-ish
      read-only connection with its own page cache, not the runner's writer
      connection contending with the recorder loop.
    - **Not a stable number.** One reading on a shared machine, and the fixed
      run order (see the module comment) means the NOT INDEXED figures are
      measured warm after the indexed figures have already touched the same
      table -- read the gap as a floor, not a ceiling.
    - **Not a census of the access pattern.** This times one
      (odds_event_id, market) pair, auto-picked as the busiest in the table
      (or the busiest market of a caller-named event). It says nothing about
      how many times a night this exact shape runs, or about cold events with
      few rows where a table scan and an index seek may cost about the same.
    - **Not a verdict from the plan alone.** `EXPLAIN QUERY PLAN` reports the
      access method, never the number of rows touched -- the same caution
      `backend/store/schema.sql:242-262`'s comment on `idx_odds_event_commence`
      makes about this exact index family. The wall times are the evidence;
      the plans are context for reading them.
    """
    if args.odds_event_id:
        oid = args.odds_event_id
        picked = conn.execute(_SQL_PICK_MARKET_FOR_EVENT, (oid,)).fetchone()
        market, pair_rows = (picked[0], picked[1]) if picked else ("h2h", 0)
        how_picked = f"--odds-event-id {oid!r}, busiest market in it"
    else:
        picked = conn.execute(_SQL_PICK_HOTTEST_EVENT_MARKET).fetchone()
        if picked:
            oid, market, pair_rows = picked[0], picked[1], picked[2]
        else:
            oid, market, pair_rows = "", "h2h", 0
        how_picked = "auto-picked: busiest (odds_event_id, market) pair"

    census = _fetch(
        conn,
        _SQL_LATEST_PRICE_CENSUS,
        {"oid": oid, "mkt": market},
        title=(
            f"what this reads over -- pair chosen by {how_picked}, "
            f"{pair_rows} rows for it at pick time"
        ),
        cap=args.limit,
    )

    whole_with, whole_with_rows = _run_latest_price_whole(conn, False, oid, market)
    max_with, max_with_rows = _run_latest_price_max_alone(conn, False, oid, market)
    max_without, max_without_rows = _run_latest_price_max_alone(
        conn, True, oid, market
    )
    whole_without, whole_without_rows = _run_latest_price_whole(
        conn, True, oid, market
    )

    agree = whole_with_rows == whole_without_rows
    timings = Section(
        title=(
            "wall time, one read-only connection, in this order (indexed "
            "runs cold, NOT INDEXED runs warm -- the unflattering order; "
            "see the module comment)"
        ),
        columns=("statement", "rows", "ms"),
        rows=[
            [
                "1. WITH INDEX -- whole latest-price read (MAX + row fetch)",
                whole_with_rows,
                whole_with,
            ],
            ["2. WITH INDEX -- MAX(fetched_ms) alone", max_with_rows, max_with],
            [
                "3. NOT INDEXED -- MAX(fetched_ms) alone",
                max_without_rows,
                max_without,
            ],
            [
                "4. NOT INDEXED -- whole latest-price read (MAX + row fetch)",
                whole_without_rows,
                whole_without,
            ],
            [
                "whole-read row counts agree" if agree
                else "WHOLE-READ ROW COUNTS DISAGREE -- NOT INDEXED changed "
                     "the answer",
                whole_with_rows,
                whole_without_rows,
            ],
        ],
    )

    plans = []
    for label, sql, params in (
        ("EXPLAIN QUERY PLAN: WITH INDEX -- MAX(fetched_ms)",
         _latest_price_max_sql(False), (oid, market)),
        ("EXPLAIN QUERY PLAN: WITH INDEX -- row fetch",
         _latest_price_rows_sql(False), (oid, market, 0)),
        ("EXPLAIN QUERY PLAN: NOT INDEXED -- MAX(fetched_ms)",
         _latest_price_max_sql(True), (oid, market)),
        ("EXPLAIN QUERY PLAN: NOT INDEXED -- row fetch",
         _latest_price_rows_sql(True), (oid, market, 0)),
    ):
        plans.append(
            _fetch(
                conn,
                "EXPLAIN QUERY PLAN " + sql,
                params,
                title=label,
                cap=args.limit,
            )
        )

    return [census, timings] + plans

