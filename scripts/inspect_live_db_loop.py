"""The recorder loop's own health: memory, walks, failures, gaps, volume, pushes.

Queries: `loop-rss`, `walk-log`, `failure-journal`, `pass-gaps`,
`notifications`, `db-sizes`.

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

_SQL_DBSTAT = (
    "SELECT name, SUM(pgsize) AS bytes, COUNT(*) AS pages "
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
                title="B. stored bytes per btree, via dbstat (indexes listed separately)",
                cap=args.limit,
            )
        )
    except sqlite3.OperationalError:
        # dbstat is optional at compile time. Say so in the title rather than
        # returning row counts under a heading that implies bytes.
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
