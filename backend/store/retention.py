"""Bounded growth for the two recording tables that had none.

Nothing in this project deleted a row until 2026-08-19. `kalshi_quotes` and
`unmatched_events` accumulated for the life of the volume, which is two
separate failures rather than one:

ADR 0056 then changed what a row in the second of them *is*. The work queue is
now `unmatched_items`, one row per item rather than one per sighting, and the
window below reads `last_seen_ms`. `unmatched_events` is the old append-only
table, no longer written, drained by `prune_legacy_unmatched` and dropped when
it is empty. The `kalshi_quotes` rule is untouched by that change.

- **Disk.** The volume filled on 2026-08-16 and was 79% full again three days
  later, growing ~214 MiB/day and accelerating. A full SQLite volume is a hard
  down that a restart does not clear, and `VACUUM` needs roughly twice the free
  space it would have by then.
- **Latency.** Each quote pass inserts ~5,300 rows into `kalshi_quotes` behind
  a `(ticker, observed_ms DESC)` index that had reached 476 MiB on a machine
  with 1 GiB of RAM. The insert leg measured 0.17s at 279k rows, and 6.0s then
  14.0s at 6.9M -- on a 15s cadence. See
  `docs/measurements/2026-08-19-quote-pass-leg-attribution.md`.

The second is why this is not merely housekeeping: the index is the thing the
pass writes into every fifteen seconds, and its size is the pass's cost.

What is kept, and why it is safe
--------------------------------
Every production reader of `kalshi_quotes` was enumerated before this was
written, because a retention rule is only as good as the claim that nothing
reads what it drops:

===========================  ==============================================
`runner.latest_kalshi_quote` newest row for one ticker
`routes.py` recorder health  newest row overall
`slate.kalshi_drift_tenths`  a **one hour** window
`clv_signal.py`              joined to a row in `recommendations`
===========================  ==============================================

So the only reader that reaches back beyond an hour reaches back through
`recommendations.ticker`. A row is kept when **either** it is inside the
retention window **or** its ticker has ever produced a recommendation --
`recommendations` is the only downstream table carrying a ticker at all
(`fair_prices` is keyed by `link_id`). On live at 6,946,356 rows, 4.8% of the
table is ticker-recommended and is kept regardless of age.

What this does NOT do
---------------------
- **It does not shrink the file.** SQLite returns freed pages to a free list,
  not to the filesystem; only `VACUUM` gives space back to the OS. Freed pages
  *are* reused by subsequent inserts, so the growth stops even without one --
  but a report that the database is smaller must come from `VACUUM`, not from
  this.
- **It does not bound the tables it does not name.** `odds_snapshots` was
  33.6 MiB and growing slowly when this was written; it is deliberately out of
  scope rather than forgotten.
- **`fair_prices` is not bounded here, and until 2026-09-01 it was not named
  here either.** That was worse than an oversight: the table is mentioned at
  `:43` of this docstring, three lines above this list, so it was in the
  author's hand while the exclusions were being written and still got neither a
  rule nor an exclusion. It reached **646,230,016 bytes** and ~64% of the
  volume's organic growth
  (`docs/measurements/2026-09-01-the-volume-clock.md`). A rule for it now
  exists in `backend/store/fair_price_downsample.py`, registered in
  `docs/measurements/2026-09-01-preregistration-fair-prices-downsample.md` and
  **shipped off**. It is a separate module rather than a fourth prune here
  precisely so that the registered cut and this file's unregistered ones cannot
  be edited as if they were the same kind of thing.
- **It does not make the retention window a claim about the record's value.**
  The window is set by what the readers reach, not by how long a quote is
  interesting. If a future reader wants older history, it must raise the
  window here rather than discover the rows are gone.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MS_PER_DAY = 24 * 60 * 60 * 1000

#: How far back a quote is kept for a ticker that never produced a
#: recommendation. Three days against a one-hour longest reader is a ~72x
#: margin, chosen so that a reader added without reading this file has room to
#: be wrong before it is silently starved.
DEFAULT_QUOTE_RETENTION_MS = 3 * _MS_PER_DAY

#: `unmatched_items` is a diagnostic: one row per work item the linker could
#: not match. No production code path reads it -- the linker writes it and
#: `store/publish.py` exposes it to dbt. Kept longer than the quotes because a
#: matching regression is diagnosed over days, not hours.
#:
#: **Measured against `last_seen_ms`, and since ADR 0056 that is a different
#: question from the one this window used to ask.** Under the append-only shape
#: a row was a sighting, so ageing one out dropped a stale observation. A row is
#: now the item itself, so this says "forget work nobody has seen for a week" --
#: and an item still failing every pass is never eligible however old it is,
#: which is correct and was not expressible before.
DEFAULT_UNMATCHED_RETENTION_MS = 7 * _MS_PER_DAY

#: Rows deleted per statement. A single unbounded `DELETE` over millions of
#: rows holds the write lock for the whole of it, and the loop's next quote
#: pass would block behind it -- turning a disk fix into a latency incident.
#: Batching lets the writer interleave.
DELETE_BATCH = 20_000

#: How long a prune may hold the pass, in seconds.
#:
#: **Batching alone did not bound this, and the first live run proved it.** The
#: batch size limits how long one `DELETE` holds the write lock, which is a
#: different quantity from how long the *pass* is blocked -- the prune runs
#: inside the pass, so a loop that deletes until nothing matches blocks the
#: recorder for the whole backlog however small the batches are. On the first
#: run, 2026-08-19, that was 1.25M rows at ~60k/minute with 1.8M still to go,
#: and `recorder.age_ms` climbed one second per second for the duration: no
#: quotes recorded at all while it ran.
#:
#: So the prune takes a time budget and leaves the rest for the next pass. A
#: backlog drains over several passes instead of one long stall, and the
#: steady state -- one pass's worth of newly-aged rows -- finishes well inside
#: the budget and is unaffected.
#: Measured on live 2026-08-19: one 20,000-row batch costs **~20s**, which is
#: index maintenance rather than the scan -- every deleted row must come out
#: of a 476 MiB btree. So a budget under 20s buys exactly one batch and the
#: number is misleading about what it spends; 30s buys two and says so.
#:
#: **Two batches is not tuning, it is the margin.** Throughput is
#: `batches x DELETE_BATCH x passes-outside-a-window`, against ~1.30M rows/day
#: of growth. At one batch that is 1.58M/day -- a 274k margin that runs out
#: at **7.75 open hours/day**, and live measured **4.33** with only two
#: sports in season. NFL and NBA are both out of season as this is written
#: and both return within weeks. At two batches the same break-even is
#: ~15.9 open hours/day, which the schedule cannot reach.
#:
#: The cost is ~40s of a full pass instead of ~20s, and it is affordable for
#: exactly one reason: this never runs while a window is open, so the
#: minutes it spends are ones in which nothing is bettable.
DEFAULT_BUDGET_S = 30.0


@dataclass(frozen=True)
class PruneResult:
    """What one prune removed. Zero is a normal, reportable answer."""

    quotes_deleted: int = 0
    unmatched_deleted: int = 0
    #: Rows removed from the pre-ADR-0056 `unmatched_events` table, which is no
    #: longer written and is being drained to nothing. **Counted separately
    #: rather than folded into `unmatched_deleted`, because the two mean
    #: opposite things**: one is steady-state housekeeping that should stay
    #: small forever, the other is a one-off backlog that should reach zero and
    #: stay there. Summed together, the backlog draining would look exactly like
    #: the steady state misbehaving.
    legacy_unmatched_deleted: int = 0

    @property
    def total(self) -> int:
        return (
            self.quotes_deleted
            + self.unmatched_deleted
            + self.legacy_unmatched_deleted
        )


def _delete_in_batches(conn, sql: str, params: tuple, *, budget_s: float) -> int:
    """Run a bounded `DELETE` until it stops matching or the budget runs out.

    Each batch is its own transaction. A crash midway therefore leaves the
    table partly pruned rather than rolled back, which is the correct
    direction: the rows were surplus, and resuming simply removes the rest.

    The budget is checked *between* batches, never inside one, so the deadline
    is honoured to within one batch rather than exactly. That is deliberate:
    the alternative is abandoning a `DELETE` mid-statement, and a prune that
    can leave a half-applied transaction behind is worse than one that
    overruns by a few hundred milliseconds.
    """
    deadline = time.monotonic() + budget_s
    removed = 0
    while True:
        cursor = conn.execute(sql, params)
        conn.commit()
        if not cursor.rowcount:
            return removed
        removed += cursor.rowcount
        if time.monotonic() >= deadline:
            return removed


def prune_quotes(
    conn,
    *,
    now: int,
    retention_ms: int = DEFAULT_QUOTE_RETENTION_MS,
    budget_s: float = DEFAULT_BUDGET_S,
) -> int:
    """Drop quotes older than the window whose ticker never produced a bet.

    The `NOT IN` is against `recommendations.ticker` rather than against a
    join, because the question is about the ticker's whole history and not
    about any one recommendation's timing: a market quoted for hours before it
    was ever recommended keeps that entire run, which is what makes the
    surviving series usable for closing-line work.
    """
    # **`confirmed_ms`, not `observed_ms` (ADR 0055).** The table is a change
    # log: a market whose price genuinely has not moved in three days has one
    # row, with an `observed_ms` three days old and a `confirmed_ms` from this
    # pass. Selecting on `observed_ms` would delete **the live quote** -- the
    # market would then have no quote at all until the next pass rewrote it,
    # and `latest_kalshi_quote` would return `None` for a market that is
    # perfectly well priced. Keep what was recently *confirmed*.
    return _delete_in_batches(
        conn,
        "DELETE FROM kalshi_quotes WHERE id IN ("
        "  SELECT id FROM kalshi_quotes"
        "  WHERE COALESCE(confirmed_ms, observed_ms) < ?"
        "    AND ticker NOT IN (SELECT ticker FROM recommendations)"
        "  LIMIT ?"
        ")",
        (now - retention_ms, DELETE_BATCH),
        budget_s=budget_s,
    )


def prune_unmatched(
    conn,
    *,
    now: int,
    retention_ms: int = DEFAULT_UNMATCHED_RETENTION_MS,
    budget_s: float = DEFAULT_BUDGET_S,
) -> int:
    """Forget work items nobody has seen inside the window.

    Unconditional on `resolved`, unlike the quotes rule, and that is
    deliberate: on live, **0 of 788,944** rows had ever been marked resolved,
    so a rule that spared resolved rows would spare nothing and would read as a
    safeguard while being a no-op. If the resolution path is ever built, this
    is the line to revisit.

    **`last_seen_ms`, never `first_seen_ms` (ADR 0056).** Pruning on first-seen
    would delete an item the linker is still failing on every pass, and the very
    next pass would insert it again with `seen_count` back to 1 -- so a
    week-long failure would present as new, forever, while the pass line
    reported a healthy prune. That is the same class of defect as a guard that
    validates its parameter instead of its observation: busy, green, and blind.
    """
    return _delete_in_batches(
        conn,
        "DELETE FROM unmatched_items WHERE id IN ("
        "  SELECT id FROM unmatched_items WHERE last_seen_ms < ? LIMIT ?"
        ")",
        (now - retention_ms, DELETE_BATCH),
        budget_s=budget_s,
    )


#: The pre-ADR-0056 table. No longer written by anything; drained to nothing and
#: then dropped. The name is spelled out here rather than inlined so the day it
#: can be deleted, `grep` finds every place that has to go with it.
LEGACY_UNMATCHED_TABLE = "unmatched_events"


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def prune_legacy_unmatched(
    conn, *, budget_s: float = DEFAULT_BUDGET_S
) -> int:
    """Drain the pre-ADR-0056 `unmatched_events` table, then drop it.

    **This exists because the obvious migration was measured and refused.**
    Collapsing the old table in place at boot costs, rehearsed against live on
    2026-08-19, **229s** for the `GROUP BY` and **218s** for the `DROP TABLE`
    over its 181,154 pages. Migrations run before uvicorn, so that is a
    multi-minute outage under a health check that does not wait -- and a machine
    killed part-way re-runs the step from the top, which is a crash loop on the
    one volume that cannot be recreated.

    So the cost is moved off the boot path and onto the machinery that already
    bounds exactly this: batched deletes, a time budget, full passes only. The
    table drains over a few passes instead of blocking one boot.

    **Everything is deleted, with no window at all**, unlike every other rule
    here. Nothing reads this table, nothing writes it any more, and the linker
    re-derives its entire contents into `unmatched_items` on the next pass --
    so a retention window over it would preserve nothing that is not already
    being rebuilt.

    **The `DROP` only happens once the table is empty**, which is the whole
    point: dropping 181,154 pages costs 218s, dropping one costs nothing. Kept
    inside the same budget check so a slow drain cannot turn into a slow drop.

    Returns rows removed. Zero once the table is gone, forever.
    """
    if not _table_exists(conn, LEGACY_UNMATCHED_TABLE):
        return 0
    removed = _delete_in_batches(
        conn,
        f"DELETE FROM {LEGACY_UNMATCHED_TABLE} WHERE id IN ("
        f"  SELECT id FROM {LEGACY_UNMATCHED_TABLE} LIMIT ?"
        ")",
        (DELETE_BATCH,),
        budget_s=budget_s,
    )
    empty = conn.execute(
        f"SELECT 1 FROM {LEGACY_UNMATCHED_TABLE} LIMIT 1"
    ).fetchone() is None
    if empty:
        conn.execute(f"DROP TABLE {LEGACY_UNMATCHED_TABLE}")
        conn.commit()
        logger.info(
            "retention: %s is empty and has been dropped", LEGACY_UNMATCHED_TABLE
        )
    return removed


def prune(
    conn,
    *,
    now: int,
    quote_retention_ms: int = DEFAULT_QUOTE_RETENTION_MS,
    unmatched_retention_ms: int = DEFAULT_UNMATCHED_RETENTION_MS,
    budget_s: float = DEFAULT_BUDGET_S,
) -> PruneResult:
    """Both prunes, for the full pass to call once per slow interval.

    **Never call this on the quote cadence.** The prune competes for the same
    write lock as the inserts it exists to keep fast, and at the 15s cadence it
    would run during exactly the minutes a bettable window is open.
    """
    result = PruneResult(
        quotes_deleted=prune_quotes(
            conn, now=now, retention_ms=quote_retention_ms, budget_s=budget_s
        ),
        # Its own budget, not the remainder of the quotes one: a large quote
        # backlog would otherwise starve this table indefinitely, and the
        # table that is never reached is the one nobody notices growing.
        unmatched_deleted=prune_unmatched(
            conn, now=now, retention_ms=unmatched_retention_ms, budget_s=budget_s
        ),
        # Its own budget again, and last: this is a finite backlog, so starving
        # it merely postpones the day it finishes, while starving either of the
        # two above lets a live table grow.
        legacy_unmatched_deleted=prune_legacy_unmatched(conn, budget_s=budget_s),
    )
    if result.total:
        logger.info(
            "retention: pruned %d kalshi_quotes, %d unmatched_items and "
            "%d legacy unmatched_events rows",
            result.quotes_deleted,
            result.unmatched_deleted,
            result.legacy_unmatched_deleted,
        )
    return result
