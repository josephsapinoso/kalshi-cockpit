# 0008 — Orders are recorded before they are sent, and exposure has one definition

**Status:** accepted, 2026-08-08

## Context

`POST /api/orders` ran thirteen checks, built an `OrderRequest`, dry-ran it
through `OrderPlacer`, and returned. It never wrote a row. The `orders` table
had existed since the first commit and had never held one.

`kalshi/orders.py` said, in its own module docstring, *"A dry run builds the
identical request body, generates the identical `client_order_id`, and writes
the identical row."* Two of those three were true.

Three things followed from the missing write, and they are not equally serious.

**The idempotency key existed only in memory.** `client_order_id` is generated
before the request precisely so that a timeout-then-retry cannot double-fill:
Kalshi recognises the repeat and returns the original order. The failure it is
*for* is a POST that times out after the exchange accepted it — an order in the
book, no response in hand. Recording after the response loses the key in exactly
that case.

**The evidence and the execution described different prices.** CLV scores off
`entry_ask_tenths`, the ask recorded when the recommendation was written. Since
ADR 0007 the order goes out at the ask re-read inside the request. Nothing
joined them, so the gate that arms real money would have been built on the
closing-line behaviour of one price while the money moved at another.

**And `max_exposure_dollars` had nothing to read.** Named in `tasks/NEXT.md` as
the reason to do this. It is the least of the three, for a reason set out below.

Writing the rows then surfaced something that had been invisible while the table
was empty: **there were two definitions of exposure.** `runner.py` summed `fills`
net of `settlements`; the order endpoint summed live `orders`. Both returned
`0.0` for the life of the project, so they had never disagreed.

## Decision

### 1. The row goes in before the request, not after

`store/orders.py::record_intent` inserts with `status = 'pending'` before
`OrderPlacer.place` is called. The outcome is stamped afterwards.

The two write failures get opposite treatment, because they happen at opposite
sides of the only irreversible step:

| | Failure to record | Failure to stamp the outcome |
|---|---|---|
| When | before the request | after it |
| Response | **503, order not sent** | 200, with the gap reported |
| Why | an order we cannot record is one we cannot reconcile, cancel or score, and the record is the product | the request has gone; on a live order the money has moved whatever this connection does |

A stamp that fails leaves the row in `pending` with the idempotency key, which
is the state reconciliation is written to read.

### 2. Only orders get rows. Refusals do not

`orders` means orders, not attempts. A refusal never reaches the placer and has
no request body to store.

This follows the repo's existing rule about rejection logs: ask what fraction of
inputs will trigger the entry, and if the answer is "most of them" it is a state
rather than an exception. Today essentially every tap is refused at the gate, so
a table of attempts would be a table of refusals, and the one row that mattered
would be buried. The refusal already reaches the caller and the log.

### 3. Exposure is `orders`, and `fills` is not a second source

Deleted `runner.current_exposure_dollars`; both callers now use
`store.orders.current_exposure_dollars`. Per `tasks/lessons.md`: don't test that
two paths agree, delete one of them.

`orders` is the right table for a **pre-trade** cap. A resting order is
committed capital and can fill at any moment; counting fills alone lets a
hundred resting orders each size against zero exposure, which is how a system
ends up a hundred times over its limit with every individual check passing.
Counting the order at its **limit** price rather than its fill price over-states
it slightly — a fill is never worse than the limit — and a risk cap should
over-state.

`fills` keeps the job its schema comment describes: measuring `fee_actual`
against `fee_predicted`.

### 4. The query enumerates the terminal statuses, not the live ones

The old query counted `status IN ('pending','resting','filled')`. That list
omitted `partially_filled` — a filled leg and a resting leg, both at risk — and,
worse, `unrecognised_response`, which means *"the response could not be read, so
this order may have filled"*. An enumeration of what counts drops that to zero,
which is unreadable-resolving-to-zero applied to an entire position.

Inverted: everything counts except `unfilled`, `rejected` and `canceled`. A
status added to `kalshi/orders.py` a year from now and forgotten here defaults to
counting, which refuses an order rather than permitting one.

A `NULL` limit price refuses rather than summing to zero, because `SUM` skips
NULLs and an unpriced order would otherwise read as a free position.

### 5. `limit_price_tenths` holds our side's price, not the wire leg's

V2 quotes the YES leg only, so buying NO at 40.5c is sent as a YES ask of 59.5c.
Exposure is `count * limit_price_tenths`, so the column has to hold what we pay.
Storing the sent price would measure a NO position at its complement:
over-stated below 50c and **under-stated above it**, which is the direction that
lets the cap pass a position it should refuse.

Nothing is lost. `request_body_json` holds the exact bytes including `price`, so
the wire value is recoverable and there is one column per meaning.

### 6. Dry runs are recorded and are not exposure

They are the audit trail and the CLV join; they commit no money.

The tempting alternative — count paper orders, so the cap binds today — is
worse. **Nothing settles a paper position.** `settlements` has no writer, so
paper exposure could only ratchet up until the endpoint refused everything with
no way to release it. A cap that can only close is an off switch, and this repo
already has a lesson about thresholds that are off switches.

## Consequences

**`max_exposure_dollars` still does not bind in production.** This is the part
of `tasks/NEXT.md`'s framing that the change does not deliver, and it should be
said plainly: writing rows was necessary but not sufficient, because every row
the running system writes is a dry run. The cap begins binding the day a live
order exists. Until then it is exercised only by tests that write `dry_run = 0`
rows by hand, and `tests/test_order_record.py` says so in its module docstring
rather than letting a green suite imply production coverage.

The prerequisite for a paper cap is a **paper settlement path**, not a change to
the exposure query.

**Three gaps are recorded rather than closed**, all of which become real the day
the gate opens. ~~Two~~ **Both of the first two are now closed** — 1 by ADR 0009
and 2 by the transaction change described above it — and they are kept here
because the reasoning that deferred them is worth reading beside what it cost:

1. ~~**Placement is not idempotent.**~~ **Closed 2026-08-08, ADR 0009.** The
   `UNIQUE` constraint on `client_order_id` stops a duplicate row; it does not
   stop a duplicate order, because each request mints a fresh id. Two taps are
   two orders. Closing it means the client supplying the key and the endpoint
   replaying the recorded outcome — a new path on the money endpoint that
   cannot be tested against live behaviour today, which is why it is filed
   rather than built.
   *That last clause was the weak part of this ADR.* The replay path never
   touches Kalshi at all, and the placement path is exercised in dry run to the
   same depth as everything else here — so "cannot be tested against live
   behaviour" was true of the exchange's re-send semantics and of nothing else.
   Building it found a `schema.sql` ordering defect that would have crash-looped
   the live instance on the next deploy.
2. ~~**Two concurrent requests can size against one exposure reading.**~~
   **Closed 2026-08-08.** `reserve_order` now writes the row and checks the cap
   in one `BEGIN IMMEDIATE` transaction, with the check *after* the insert.
3. **Exposure is fee-exclusive while the cap is spent fee-inclusive.**
   `size_position` bounds `contracts * effective_price`; the column holds the
   raw stake. Exposure therefore accumulates about 2% less than it consumed, at
   a 1c fee on a 50c contract. Correcting it needs a fee column on `orders`;
   it is not worth a migration for a 2% error on a cap no live order has reached.

**The API is now a writer.** It was read-only by construction, which is a real
safety property — the API cannot corrupt the evidence record while deciding — so
only the recording step opens a writable connection, in a worker thread, and the
thirteen checks above it still read through the read-only handle.

That makes two writer processes, which is why `connect` now passes an explicit
`timeout`: a blocked writer must wait rather than fail while the runner records
a pass. The first attempt at this set `PRAGMA busy_timeout = 5000` and was a
complete no-op, because CPython's `sqlite3` already defaults to exactly that.
Nothing revealed it except deleting the line and watching the test that claimed
to cover it stay green.
