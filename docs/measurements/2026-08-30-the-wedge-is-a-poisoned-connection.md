# 2026-08-30 — The recorder's hour-long silences are a poisoned connection, and the failure table was structurally blind to them

Two Discord heartbeat alerts fired on the night of 2026-08-29 (20:10 and
20:28 Pacific): *"the recording loop has not written a quote for 43/61
minutes."* This document is the diagnosis, taken while the evidence still
existed, and the reason the record could not have taken it by itself.

## The timeline, from the live instance

All times UTC, 2026-08-30. Live was on `fe239d6` (deployed 01:53Z).

| time | fact | source |
|---|---|---|
| 02:26:47 | last completed pass writes `odds_sweep_log` id 19228 and the recorder heartbeat | `sweep-log` |
| 02:27:38 → 03:27:53 | portfolio poller succeeds every 5 minutes, unbroken: `balance`/`fills`/`settlements`/`positions` all `ok=1`, 13 cycles | `poll_log` |
| 02:40:52, 02:57:42, 03:14:05, 03:28:20 | four passes attempt and fail; each writes a `loop_rss.jsonl` line (a FILE) carrying cached metrics; none writes `odds_sweep_log` or `loop_failures` (the DATABASE) | `loop_rss.jsonl` |
| 03:28:30 | `LoopFailed: 5 consecutive failed passes; last error: OperationalError: database is locked` — and the dying `FAILURE_LOOP_DIED` alert itself dies on `alerts.py:373 _claim`, same error | Fly log buffer |
| 03:28:32 | container exits (`exit_code=1, oom_killed=false`), the entrypoint's designed teardown | `flyctl machine status` |
| 03:28:53 | fresh boot; first pass ok in 118.8s; `wal_kb: 4` | logs, `loop_rss.jsonl` |

An earlier gap the same night (silent ~00:28 → resumed 01:13:39, on
`c9ca0cd`, pre-deploy) has the same shape; its logs are gone. Both builds
carry the 600s pass deadline (shipped 2026-08-28).

## The discriminating observation

**The lock was not held continuously by anyone.** If a single connection had
held the write lock for an hour, the poller could not have committed either.
It committed thirteen times. The only state that produces *this* split —
one connection refused instantly on every write while every other connection
writes freely — is a **stale WAL read snapshot on the refused connection**:
SQLITE_BUSY_SNAPSHOT, reported by Python as the same "database is locked"
string, and immune to the busy timeout because waiting cannot make a stale
snapshot fresh.

Mechanism, reproduced in `tests/test_poisoned_connection_is_cured.py`
against this repo's own Python (3.11.9):

1. A pass dies between statements — cancelled by the 600s deadline, or
   raising — and abandons a half-read cursor. Nothing on the failure path
   rolls back or resets.
2. If (and only if) something long-lived still references that cursor, the
   connection keeps a read snapshot. A refcount-freed cursor releases it
   and nothing happens — measured, which is why this fires rarely rather
   than on every failure.
3. The poller's separate connection keeps committing, advancing the WAL
   past the snapshot.
4. Every write on the poisoned connection now fails instantly:
   the next pass, `record_loop_failure`, the alerter's `_claim`. All three
   share the connection.
5. Five strikes → `LoopFailed` → the process exits → the entrypoint tears
   the container down → restart cures it (a new process has no stale
   snapshot) — and resets the WAL, destroying the measurement in flight.

Also measured, not assumed: `Connection.rollback()` alone does **not**
cure the referenced-cursor case (CPython stopped resetting statements on
rollback in 3.11); closing the cursor and rolling back does; production
cannot reach the cursor.

## What this inverts

`loop_failures`' documented reading was *"rows mean failing; no rows across
a gap mean wedged or gone."* This incident adds the third state the table
cannot represent: **failing in a way that refuses the failure row itself.**
The table showed silence across the exact window it exists to explain,
twice in one night — the blind spot is precisely the failure class that
kills the loop.

## What changed (same commit)

- `db.record_loop_failure_durably`: journals every pass failure — with
  traceback — to `loop_failures.jsonl` beside the database (a file no lock
  can refuse), attempts the rollback cure, and falls back to a throwaway
  connection for the row. Fresh-connection success while the shared one
  refuses is itself the diagnosis, and the journal says so in words.
- The dying `FAILURE_LOOP_DIED` alert rolls back first and retries once on
  a fresh connection.

## What this does not establish

- **Which statement was abandoned, or what holds its reference.** The
  candidates (an exception chain kept alive by a logging handler, a
  suspended generator) are untested. The journal's tracebacks will name
  the failing await next time; that is the instrument this diagnosis
  lacked.
- **Whether the 00:28 wedge was the same mechanism.** Same signature, no
  surviving logs. Stated as consistent, not proven.
- **Any WAL-size effect on pass latency.** Separate thread; the WAL here
  was 32MB and quote passes were fast right up to the wedge.

## Consequences for the WAL measurement

The WAL growth curve restarts from zero at every one of these deaths
(01:53Z deploy, 03:28Z wedge-death). A "day of uptime" now requires a day
without a poisoned-connection suicide; if the fix's cure path works, the
loop survives the poison and the curve survives with it.
