# 0083 — A refusal is a record, and an unobserved payload is not a position

Date: 2026-08-30. Status: accepted.

Two decisions, one evening, both forced by the same fact: `manual_orders`
had zero rows in four days armed, Joe was about to try the dollar buy
ticket on a real bet, and the path he was about to exercise carried one
guard reading a payload nobody had ever seen and ~23 refusal branches
writing nothing anywhere.

## Decision 1 — an unobserved venue payload may not drive a refusal decision

Either observe and parse it, or refuse explicitly and say so. What is not
allowed is the middle state this repo was in: `backend/bets.py` refusing to
parse `/portfolio/positions` rows because the shape was unobserved, while
`backend/api/routes.py` check 10 silently decided off the same rows —
refusing any row that *named the ticker*, quantity unread. The refusal and
the assumption cannot both be right about the same wire.

### The observation (2026-08-30, `scripts/capture_positions_fixture.py`)

Two calls against the production account, verbatim captures in gitignored
`data/captures/` (operator data never enters the repo; the committed
artifact is a shape assertion over synthetic values, the ADR 0035
precedent):

- Envelope: `{"cursor", "event_positions", "market_positions"}`.
- The quantity field is **`position_fp`, a fixed-point STRING**, and it is
  genuinely **fractional** (`'22.88'` observed live). The docs' legacy
  `position` integer is absent. Any reader parses `Decimal`; `int()`
  misreads a real position and `float` carries binary noise into an
  equality-with-zero test.
- **The bare endpoint returns zero-quantity rows for markets already
  exited**: 2 bare vs 1 with `count_filter=position`, and the zero row was
  a market exited three days earlier, still being served. So check 10
  refused re-entry to markets Joe had left, and "Open now: N" counted
  "ever traded", not "open".
- `cursor` came back empty on this account — which proves pagination
  unnecessary at this size and nothing at any other size.

### What changed (commit `a45d088`)

`rest.positions()` gained three fixes that travel together, because after
one binds the next is the limit: `count_filter=position` (the venue's own
non-zero cut), cursor pagination (a real position past page 1 fails the
netting guard **open**), and the missing-key raise replacing `or []` (a
renamed envelope read as "no open positions" — the fifth instance of this
repo's most-repeated defect). Check 10 now compares `position_fp`: zero
passes, nonzero refuses, unparseable refuses — unreadable resolves to a
refusal, never to zero. Proven by mutation: reintroducing refuse-on-zero
turns `test_an_exited_market_no_longer_refuses_the_buy` red.

### What this does not establish

What the venue's filter does to a row that flips to zero mid-session;
anything about `event_positions` (2 rows observed, parsed nowhere); the
in-play shape of a row. The capture script stays in the repo so the next
question starts from an observation instead of a docstring.

## Decision 2 — every armed path records its own refusals durably

Three instances of one pattern in three days:

1. A refused hand bet wrote nothing (all ~23 branches before check 11's
   reservation — the whole pre-reservation surface of the one path that
   spends Joe's money at his own tap).
2. A failed estimate-match pass wrote nothing (`portfolio_poll.py`'s
   except branch logged and moved on, while every sibling wrote
   `poll_log`; fixed in the item-4 lane, merged tonight).
3. A poisoned-connection pass failure wrote nothing — five times in a row,
   across the exact window `loop_failures` exists to explain — until
   `record_loop_failure_durably` shipped on 2026-08-29.

The shared defect: **a failure path whose only record is a log line**, on
an instance whose containers demonstrably restart and whose `flyctl logs`
are lossy. A log line is not a record.

### What changed (commit `21da67e`)

Schema v29, `manual_order_refusals`: append-only, one row per refusal,
carrying the check number and name, the exact detail string Joe was shown,
the request values, and the live ask when one had been fetched. One
recorder rather than 23 edits — the checks run inside a single
try/except with a check pointer updated at the top of each numbered check.

Three properties, each load-bearing:

- **A recording failure never converts a 422 into a 500.** Throwaway
  connection (the poisoned shared connection is exactly what the
  2026-08-30 incident proved can refuse writes), journal fallback beside
  the database (`manual_order_refusals.jsonl`), and the route swallows
  even a recorder that blows up entirely. The refusal Joe sees *is* the
  refusal; this is forensics beside it.
- **`gate.py` may never read the table** — the identical ADR 0063/0078
  boundary, pinned by its own substring test because the existing
  `manual_orders` pin does not match this table's name. A refusal must not
  move the live-trading interlock's counter.
- **Forensic, not analytic.** No dashboard, no counter, no screen.
  "Count how often the brakes fired" is analytics over single-digit rows;
  the value is knowing which of the numbered checks refused an attempted
  bet, with what values, without a screenshot. Readable on the live box
  via the whitelisted `manual-order-refusals` query in
  `inspect_live_db.py`.

## The rule this generalises

When a path is armed — when it can spend or refuse real money at a real
tap — its failure and refusal branches write durable rows *first* and log
lines second. NEXT.md's open item 6 ("a refused hand bet writes nothing")
is closed by this; any future armed surface (a sell path, a hedge
execution) inherits the requirement on arrival, not after its own
three-day pattern.
