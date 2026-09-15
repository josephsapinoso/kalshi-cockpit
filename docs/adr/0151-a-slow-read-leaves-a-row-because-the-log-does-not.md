# 0151 — A slow read leaves a row, because the log does not

Written on `main` with no lane open; **0151 taken after `git fetch`** with 0150
the highest on `main`. **Schema v42**: `api_read_incidents`, a pure new table
(`_TABLELESS_VERSIONS`), no migration step. This constant, `SCHEMA_VERSION`,
the `schema v42` line in `schema.sql` and this ADR are ONE number.

Date: 2026-09-15
Status: accepted
Scope: `backend/store/schema.sql`, `backend/store/db.py`,
`backend/api/routes.py` (the read-budget handler and the combo-fill position
recorder), `scripts/run_loop.py` (the loopback health probe),
`backend/notify/alerts.py` (`check_feed`'s detail),
`scripts/inspect_live_db.py read-incidents`. Also rules two carried items
struck for good (§4). Nothing in the gate, the signal, the order path's
decision or the pricing changes.

---

## 1. What happened

On 2026-09-15 at 00:37Z Joe bought MLB props for the Giants game on Kalshi,
refreshed the cockpit, and the Games screen said "Backend unreachable". The
live log showed why: an API read had hit its 25 s per-statement budget and
been interrupted (ADR 0135's defence), which returns 503, which every screen
renders as unreachable. It hit again 36 s later, and a third time at
00:46:08Z inside the 72 s full pass the recorder runs after a deploy. Each
hit sat inside a heavy write pass: the first two forty to seventy-five
seconds after the pass that ran Joe's hand prop refresh (1,502 quotes,
9,278 markets written), the third inside boot's full pass.

The warning said only that *something* had been interrupted. It was reworded
the same night to carry the method, the path with its query, and the
elapsed time (`99432bc`), and NEXT.md said "the next hit is a measurement".

**That was false, and the partner caught it.** `flyctl logs` keeps a bounded
number of lines, and every scheduler pass emits a ~900-character INFO dict
every ~20 s. Measured on the live app during a busy window: 100 lines
spanning forty seconds. By the time the 00:37Z hits were looked for, they
were gone. The three hits that motivated the rewording were unrecoverable
before the rewording deployed. A warning improved but not persisted is the
same warning.

## 2. The decision

**Every slow-read incident is written to `api_read_incidents`**, by the thing
that noticed it, and the log line is the fallback rather than the record.

Two writers, one table, one `kind` column with a CHECK:

- `read_budget` — `routes._sqlite_operational_error`, on the 503. Method,
  path with query, elapsed since the request was stamped by a middleware,
  the sqlite error, the budget.
- `health_probe` — `run_loop.probe_hub_running`, when the loop's 2 s
  loopback probe of `/api/health` fails or answers ≥ 400. The exception
  class and elapsed. This probe runs **every pass** against a route that
  opens the database, so it is a 2 s-threshold detector of exactly the
  "reads crawl during a heavy write pass" hypothesis — twelve times more
  sensitive than the route budget, already deployed, and until tonight its
  outcome was one constant string.

**The writer is best-effort and never raises.** It opens its own connection
with a one-second lock wait (`API_INCIDENT_WRITE_TIMEOUT_S`), because the
incident happens *because* the database is contended and a five-second wait
on the way out of a 503 handler would hold the request open for exactly the
wait the budget exists to end. A refused write logs every field and returns
`False`. **A count in this table is therefore a FLOOR**, and the inspector
says so beside the count.

**The alert carries the probe's words.** `FAILURE_API_UNREACHABLE` used to
reach the phone with `detail = "health probe failed"`. `ReadTimeout` is "the
box is slow"; `ConnectError` is "the box is down"; the two are now
distinguishable after the fact, on the phone and in the table.

## 3. What this does not establish

**Why a read is slow.** Two candidate mechanisms — SQLite writer contention
versus CPU starvation on two shared vCPUs with a 6 GB file and 2 GB of RAM —
and nothing here separates them. **No pre-registration is written now**,
on the partner's ruling: a decision rule on a statistic nobody can compute
is worse than none, and there is no denominator (three hits against an
unknown count of heavy passes that did not blank). Collect rows with paths,
elapsed times and probe classes; register when there is a statistic. And
hold the 25 s budget where it is: if the binding constraint is the write
pass's duration, widening the budget returns the symptom with the guard
gone.

## 4. Two carried items struck for good, so a fourth session does not re-derive them

Both had been dropped twice as having no named consumer. The partner ruled
tonight, and the reasons are recorded here so the ruling is the last word.

**`parlay_positions.status` never advances — STRUCK.** It advances at Joe's
tap: `close_position` (`backend/hedge.py`) behind
`POST /api/hedge/positions/{id}/close` and the `/hedge-close` proxy. Legs
settle automatically (`resolve_from_venue`, from `hedge_watch.py`), and the
screen shows a dead ticket as dead through the computed `state`, not
through `status`. An *automatic* close would have to choose which signal
ends a position, and `backend/hedge.py` already records that the venue can
settle a combination before its legs do; choose wrong and a live ticket's
alerts are killed silently, the one failure `/hedge` exists to prevent.
Four rows, all dead, all visibly dead. No consumer the tap does not serve.

**No hedge-evaluation table — STRUCK.** A recorder over a structurally
empty source: `/hedge` has produced zero locks in its life, all four
positions are `STATE_DEAD`, and the four error terms it would record have
never been exercised on a live row. Building the recorder before the event
is the shape this repo refuses. If Joe ever contemplates an actual hedge,
the row is a by-product of that hedge, not a prerequisite.

## 5. Two carried items built, because each was a silently wrong number

**`int(fill_count)` truncation — a refusal, not a rounding.** The combo-fill
position recorder did `contracts=int(filled)` on a float off the wire. A
venue-reported 2.5 became a 2-contract holding, understating the stake and
therefore flattering the `/hedge` figure — the direction refused by policy.
A non-integral fill now records **no position** and says so on the
ticket, the same choice `unrecognised_response` makes twelve lines above
and the same shape as "unreadable resolves to `None`, never `0`". No real
fill has ever been fractional; the guard exists so the first one is said
out loud. `4.0` is still four contracts.

**The API-unreachable alert's exception class — §2**, now that item 4 of
NEXT.md is its consumer.

## 6. Order of work and what was verified

Persistence first, then the probe (a two-line addition once the table
exists), then the truncation refusal — sequential on `main`, no lanes: the
worktree tax (no `.venv`, no `node_modules`) outweighs an hour of disjoint
edits. `tests/test_api_read_incidents.py` (ten tests) and two added to
`tests/test_combo_fill_is_watched_for_a_hedge.py`; **five mutations each
seen red**: the writer's `except` narrowed, the route's record call
deleted, the probe's record made a no-op, the alert detail reverted to the
constant, the fractional branch removed. Read back on live with
`scripts/inspect_live_db.py read-incidents`.
