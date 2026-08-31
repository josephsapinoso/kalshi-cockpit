# ADR 0091 — The poller held the write lock across three network round trips

Date: 2026-08-31
Status: accepted
Relates to: ADR 0043 (venue_hand fills), ADR 0064 (the settlements clock)

## Context

`OperationalError: database is locked` has killed a scoring pass four to five
times a day. Five occurrences carry the same shape, and the fifth
(2026-08-31T05:32:45Z) finally carried a traceback:

    scheduler.run_forever -> one_pass -> score_settle_and_alert
      -> scoring.run_scoring_pass:264 -> clv.store_closing_line:183
      -> conn.execute("INSERT INTO closing_lines ...")
      sqlite3.OperationalError: database is locked

**This is not a missing busy timeout.** `BUSY_TIMEOUT_MS = 5_000` is set on
every connection and `db.py` records that it is passed explicitly rather than
inherited, precisely so it cannot silently become zero. Something holds the
write lock for **longer than five seconds**.

## What holds it

**Two places, and the one that matters is not the one found first.** The
mirror was found first and is the smaller half; the fast branch of
`poll_portfolio_forever` has the identical shape and runs 144x more often.

### The fast branch -- every 300s, so 288 times a day

    result           = await poll_balance(conn, ...)      # INSERT -> lock taken
    fills_result     = await poll_fills(conn, ...)        # network, lock HELD
    settle_result    = await poll_settlements(conn, ...)  # network, lock HELD
    positions_result = await poll_positions(conn, ...)    # network, lock HELD
    conn.commit()

`poll_fills`, `poll_settlements` and `poll_positions` were each moved onto the
balance cadence for a recorded reason (the 2026-08-21 ruling, ADR 0064, the
2026-08-29 open-positions change). **Each move made the window wider, and none
of the three noticed** -- the transaction boundary was never part of the
question being asked.

### The mirror -- twice a day, plus every container boot

`poll_portfolio`:

    summary["settlements"] = await poll_settlements(conn, client, ...)
    summary["fills"]       = await poll_fills(conn, client, ...)
    summary["positions"]   = await poll_positions(conn, client, ...)
    summary["balance"]     = await poll_balance(conn, client, ...)
    conn.commit()

`poll_settlements` runs `INSERT OR IGNORE INTO venue_settlements` in a loop and
does not commit. Python's `sqlite3` opens an implicit write transaction at that
first INSERT, and in WAL mode the writer lock is held from there until COMMIT.

So the lock is acquired in the first call and released four lines later —
**with three Kalshi HTTP round trips in between.** Three network calls on a
shared-cpu box trivially exceed five seconds, and every other writer that lands
in that window gets `database is locked`: the scoring pass, the API, the bid
watcher.

**The surrounding comments show the transaction boundary was thought about, and
the wrong property was checked.** *"After the commit, so a matcher failure
cannot roll back the mirror"* reasons carefully about **rollback scope** and
says nothing about **lock duration**. Those are different questions and only
one of them was asked.

## What this does NOT establish

**That the symptom is gone.** The frequency now fits -- 288 windows a day
against four-to-five failures -- where the mirror alone (twice a day) never
did. That is a much better fit, and a fit is not a proof.

Other candidates remain unexamined: the retention prune (a DELETE over
`kalshi_quotes`, 451 MB), and the WAL `TRUNCATE` checkpoint, which takes an
exclusive lock — though that shipped 2026-08-30 and three of the five failures
predate it.

**So this ADR fixes a defect it can prove, and does not claim to have closed
the symptom.** If the failures continue at the same rate afterwards, that is
information rather than a surprise, and the next suspect is named above.

## Decision

**Commit each step before the next network call, in BOTH paths.** The write
lock is then held for one write burst rather than for three round trips.

Nothing that is actually relied upon becomes less atomic. The four steps write
independent records to different tables from different endpoints, each
`INSERT OR IGNORE`; a failure in `poll_fills` never made the settlements
already written wrong, and each endpoint's failure is recorded separately in
`poll_log` regardless. What the existing comment protects — the matcher not
rolling back the mirror — is unaffected, because that boundary is downstream of
all of this.

**The rule this establishes, which is the part worth keeping:** *never hold a
database write transaction across an `await` that performs I/O.* A lock is held
in wall-clock time, and an `await` is an unbounded amount of it.

## Consequences

- A guard asserts the shape rather than the outcome: no `await` may appear
  between a write and its commit in either function. A timing test would be a
  flake; the structure is what is wrong and the structure is what is pinned.
  It also pins that the fast branch still polls all four endpoints, so the
  transaction cannot be shortened by dropping a poll -- that would trade a lock
  for a hole in the record.
- **The guard produced two confident false findings before it was right**, both
  recorded in its own docstring: it counted a `while` header as a write because
  something nested inside it wrote, and it carried state across an `if`/`else`
  boundary so a write in one branch was blamed on a call in the other. A guard
  whose first finding is false gets deleted, so both are written down rather
  than quietly fixed.
- Every `estimate_match` helper commits its own writes, checked while
  investigating: nothing holds the lock across the 300s sleep. That was the
  worst case available and it is not happening.
- `store_closing_line`'s caller keeps its own defect, recorded separately: the
  `try/except` in `run_scoring_pass` wraps the fetch and not the store, so a
  lock error there still abandons every remaining market in the pass. Fixing
  the holder reduces how often that is reached; it does not make the loop
  tolerant. That is a second decision.
