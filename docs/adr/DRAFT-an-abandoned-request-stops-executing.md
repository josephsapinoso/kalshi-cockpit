# ADR DRAFT — An abandoned request stops executing

**Status:** Draft, 2026-09-09. No ordinal assigned; renumber and accept when
merged alongside the fix to whichever query actually caused the incident this
records (a separate lane's work — see §4).

## 1. The finding

Four API routes returned 500, each at almost exactly 30 seconds, the same
night. The 30-second cliff is not a database timeout — it is
`frontend/next.config.ts:17-19`, where Next.js's rewrite proxy defaults
`proxyTimeout` to 30s. Past it, Next drops the request and answers its own
generic error. **uvicorn does not find out.** The SQLite statement the route
was running keeps executing on the worker thread, with nothing left to read
its result and nothing telling it to stop.

Each abandoned statement holds memory the whole time it runs:
`store.db.connect` sets `PRAGMA temp_store = MEMORY` (deliberately, see that
module — the alternative is spilling sorts and `GROUP BY`s onto the Fly
volume, the slowest thing in the request) plus a read connection's page cache
(`READ_CACHE_KIB`). A proxy that gives up doesn't free any of that; it only
stops being the one asking. Enough abandoned statements piled up and the
2 GB box's uvicorn process was OOM-killed at 1.88 GB RSS.

This is a *blast-radius* fix, not a root-cause fix: it bounds how much damage
one slow query — any slow query, on any route, for any reason — can do once a
client has stopped waiting for it. Finding and fixing the specific query that
ran long enough to trigger this is a separate lane's work (§4).

## 2. The design

`store.db.connect()` (and `open_db()`, which forwards to it) gain a keyword,
`statement_budget_ms: int | None = None`. When set, a
`sqlite3.set_progress_handler` callback is installed that aborts the running
statement — `sqlite3.OperationalError: interrupted` — once
`time.monotonic()` has passed a deadline computed from the budget at connect
time.

`backend/config.py` adds `AppConfig.api_read_budget_ms`, from
`API_READ_BUDGET_MS` (default `25_000`). `backend/api/routes.py`'s `get_conn`
— the per-request read-only connection dependency — passes it through. A
`sqlite3.OperationalError` exception handler registered on the `FastAPI` app
turns an "interrupted" one into a 503:

```json
{
  "error": "read_budget_exceeded",
  "budget_ms": 25000,
  "detail": "the query ran past the API read budget and was stopped so the
             request could not pile up behind a proxy that had already given
             up"
}
```

Any other `OperationalError` (a locked database, a malformed statement) is
re-raised from the handler and falls through to Starlette's ordinary 500 —
this is a defence against abandonment, not a general SQLite error handler,
and misreporting an unrelated bug as a budget hit would hide it.

## 3. Why per-connection, not per-statement

The obvious frame is "budget the statement, not the connection" — a fresh
30-second (or 25-second) clock for every query a request happens to run. That
is not available: `sqlite3_progress_handler` fires every *N* virtual-machine
instructions, not at statement boundaries, so there is no callback with
visibility into "a new statement just started" that could reset a clock. The
honest design available is per-**connection**: the deadline is fixed once, at
`connect()`, and every statement run on that connection afterward shares
whatever is left of the one budget.

That coincides with per-**request** for the caller this exists for.
`routes.get_conn` (`backend/api/routes.py:426-452`) opens exactly one
connection per API request and closes it when the request ends — so
per-connection and per-request are the same guarantee here, and the design
does not have to choose between them. It would not coincide for a connection
reused across several unrelated statements; nothing in this repo hands a
budgeted connection to such a caller, and the docstring on `connect()` says
so, so a future caller doesn't inherit the coincidence by accident.

The runner, migrations, and scripts (`init_db`, `migrate`, `scripts/*`) never
pass `statement_budget_ms` and are unaffected — they legitimately run
statements that take longer than 25 seconds, and budgeting those would abort
real work rather than defend against an abandoned one.

## 4. What this does not fix

**The query that actually ran 30+ seconds is still unidentified from this
lane.** This ADR bounds the consequence, not the cause; another lane is
finding and fixing the root query. Once it lands, `api_read_budget_ms` stays
on — it is a general defence against the *next* slow query, not a patch for
this one.

## 5. The trade-off explicitly NOT taken

**Flipping `PRAGMA temp_store` from `MEMORY` to `FILE`** would also bound the
memory an abandoned statement can hold, by moving sort/`GROUP BY` scratch
space onto disk instead of RAM. It is not taken here, and should not be taken
casually later: the Fly volume backing this database is under a growth alarm
(see `store.db`'s own comments on `WAL_TRUNCATE_ABOVE_KIB` and the
2026-08-19 OOM measurement), and routing scratch I/O onto a volume already
being watched for growth trades one resource pressure for another rather than
removing it. `temp_store = MEMORY` stays exactly as it is; this ADR's fix is
orthogonal to it — a budgeted connection that gets interrupted frees its temp
storage on abort either way.

## 6. Tests

`tests/test_api_read_budget.py`:

- a budgeted connection aborts a long recursive CTE with
  `sqlite3.OperationalError` inside roughly a second of the budget;
- an unbudgeted connection completes a short statement normally;
- the route-level 503, with its JSON shape, when a request's connection is
  interrupted;
- `.env.example` documents `API_READ_BUDGET_MS`.

Mutation-tested per this repo's testing convention: removing the
`set_progress_handler` call makes the first test fail (observed with a
deadline/thread guard, not a hang); removing the exception handler makes the
third test fail.
