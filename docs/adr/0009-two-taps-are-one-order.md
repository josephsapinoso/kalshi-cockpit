# 0009 — Two taps are one order

**Status:** accepted, 2026-08-08

Closes gap 1 of ADR 0008, which recorded it rather than building it.

## Context

`client_order_id` is generated inside `OrderRequest`, once per **request**. It
is a real idempotency key and it does a real job — Kalshi recognises a re-send
carrying the same one and returns the original order instead of creating a
second. That is the recovery path for a POST that times out after the exchange
accepted it.

It cannot do anything about two taps. Two taps are two requests, two
`OrderRequest`s, two freshly minted ids, and therefore two orders that Kalshi
will accept as entirely distinct. The `UNIQUE` constraint on the column stops a
duplicate *row*; it was never able to stop a duplicate *order*.

This matters more here than it would in most systems. The cockpit is operated
from a phone. A double-tap, and a retry after a connection drops on a train, are
not exotic failure modes — and the gate opening is precisely the moment they
stop being harmless.

## Decision

### 1. The client supplies a key identifying the intent

`POST /api/orders` takes `idempotency_key`, and the sheet mints one when it
**opens**, not when Confirm is tapped. That is the whole mechanism: both halves
of a double-tap, and every retry of one lost response, carry the same value. A
key minted per tap would be a fresh key per tap and would protect nothing.

### 2. It is required, not optional

An optional key protects only the callers that remember it, which is the shape
of a guard that cannot fail. Requiring it broke fifteen tests, all mechanically,
and that breakage is the evidence that the endpoint really does require it.

The cost is real and small: any non-browser caller must now generate one. That
is a one-line change for them and is arguably correct anyway.

### 3. The lookup runs before every other check

Step 0, ahead of the thirteen. Not an optimisation — a correctness requirement.
A retry after a lost response arrives seconds or minutes later, by which time
the recommendation has aged past its limits, so a replay placed *after* the
freshness checks would answer *"the price moved"* to the one request that must
be answered with what already happened.

### 4. The recorded response is replayed, not rebuilt

`orders.response_body_json` holds the answer verbatim. Reconstructing it from
the columns would be a second implementation of the response shape, free to
drift from the first — and it would drift **silently**, because the only thing
that renders it is a duplicate tap, which is by definition the path nobody
exercises by hand.

One field is added on the way out: `replayed`. A byte-identical response would
claim a second order was placed.

### 5. A row with no recorded response refuses rather than retrying

`NULL` means the row was reserved and the process never got as far as
answering, so an order may be resting on the exchange under its
`client_order_id` and nothing in this database can say whether it is. Sending a
second one is unsafe; claiming the first succeeded is also unsafe. It answers
409 and names the id to reconcile. This is
unreadable-must-never-resolve-to-zero applied to an open position.

### 6. Three layers, none of them redundant

| Layer | Covers | Cannot cover |
|---|---|---|
| Step 0 read, on the read-only handle | a retry against a now-stale row | two taps landing together — both miss it |
| Duplicate check inside `reserve_order`'s `BEGIN IMMEDIATE` | concurrent taps: the second blocks on the first's write lock, then sees its row | a writer that does not go through `reserve_order` |
| `UNIQUE INDEX` on `idempotency_key` | any writer, including ones added later | nothing — it is the floor |

`record_intent` is the concrete reason the third layer exists: it commits on its
own and never passes through `reserve_order`.

### 7. Two keys, kept separate

`client_order_id` goes to Kalshi and dedupes against the exchange.
`idempotency_key` comes from the client, the exchange never sees it, and it
dedupes against us. Collapsing them into one value — letting the client supply
`client_order_id` — is tempting and would leave client-controlled bytes on the
wire to the exchange, with whichever failure the survivor does not cover
silently uncovered.

## Consequences

**This deploy carries a migration.** `SCHEMA_VERSION` 2 → 3: two nullable
columns on `orders` and a unique index. Nullable because every row already on
the live volume has no key, and SQLite treats NULLs as distinct in a unique
index, which is what makes the constraint addable to a table with history.

**And building it found a defect that would have crash-looped the live
instance.** `init_db` applied `schema.sql` *before* migrating, which is fine for
as long as migrations only add columns and breaks the moment the schema file
declares an index over one — `executescript` runs against existing databases
too, and the column is not there yet. A fresh database gets the column from
`CREATE TABLE`, so it passes every test written against one. `init_db` now
migrates first. See `tasks/lessons.md`.

**What is still not established:** no order has ever been placed, so the outcome
being replayed is always `dry_run`. The path is exercised; the exchange's own
behaviour under a re-send is not, and stays untested until a real order exists.

**Gap 2 of ADR 0008 is also closed**, by the earlier change that put the row and
the cap check in one transaction. Gap 3 — exposure fee-exclusive against a
fee-inclusive cap, ~2% — was left open here on the grounds that it needed a
migration. **It did not, and it is closed as of 2026-08-09**; see ADR 0008.
