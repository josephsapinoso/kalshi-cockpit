# 0143 — The venue's own fill numbers are kept on the permanent row

Written by lane D with no ordinal; 0143 taken at the merge commit after
`git fetch`, per `docs/adr/README.md`. Ships **schema v40**.

Date: 2026-09-11
Status: proposed
Scope: `manual_orders` only. `orders`, `combo_orders` and `parlay_positions`
are untouched.

---

## 1. The fact this starts from

Every price column on `manual_orders` is **the ask the desk sent**, and none of
them was ever a venue report.

- `_insert_intent` (`backend/store/manual_orders.py`) writes
  `limit_price_tenths` from `OrderRequest.fill_price_tenths`
  (`backend/kalshi/orders.py:298`), a property whose own docstring reads "what
  one contract of *our* side costs at the price being sent". It is written
  **before the request leaves the process**, under `reserve_manual_order`'s
  reserve-then-check.
- `record_outcome` then stamped `status`, `kalshi_order_id` and `error_text`
  and **nothing else**, dropping `OrderOutcome.fill_count`,
  `.average_fill_price_dollars` and `.average_fee_paid_dollars` on the floor.

Read against the source on 2026-09-11, all three confirmed:
`OrderOutcome` (`backend/kalshi/orders.py:387-408`) carries the three fields;
`_read_response` (`:517-566`) fills them from a payload observed by the C0
probe; `record_outcome` (`:765-786` before this change) discarded them.

**`manual_orders` has no `fill_price_tenths` column.** CLAUDE.md named one
until 2026-09-11, along with the wrong class and the wrong line number, and the
correction is already in the spine. This ADR is written against the corrected
reading, not the old one.

## 2. Why now, and why not "it is in `fills`"

The same three numbers reach `fills` through the portfolio poller
(`backend/portfolio_poll.parse_fill`), and that is not a substitute.

- **`fills` is retention-eligible on ~3 months. `manual_orders` is permanent.**
  Joe's first real fills through this door landed 2026-09-08 (ADR 0113; four by
  2026-09-09, ADR 0129). The venue-side truth about them starts dropping out of
  the record around December, leaving a permanent row that says what we *asked
  for* beside no row at all saying what we were *charged*.
- The join between them is `kalshi_order_id` ↔ `fills.venue_order_id`, which
  exists but cannot survive the deletion of one side.
- The venue's count already reaches one table and not this one:
  `routes.py:3952` sizes `_record_combo_position` from `outcome.fill_count`,
  so `parlay_positions.contracts` is the venue's number while `manual_orders`
  kept only the requested count.

## 3. Decision

Three nullable columns on `manual_orders`, written by `record_outcome` from the
`OrderOutcome` it already receives.

| column | type | source | conversion |
|---|---|---|---|
| `venue_fill_count` | `REAL` | `OrderOutcome.fill_count` | `float`, refusing negative and non-finite |
| `venue_avg_fill_price_tenths` | `INTEGER` | `.average_fill_price_dollars` | `core.prices.dollars_to_tenths`, then `is_valid_price` |
| `venue_avg_fee_dollars` | `REAL` | `.average_fee_paid_dollars` | `Decimal`, refusing negative and non-finite |

### 3.1 Why the count is REAL

This file's QUANTITIES convention, and `fills.count`. V2 counts are fixed-point
decimal strings (`"1.00"`) and the venue supports fractional contracts to 0.01;
an `INTEGER` column would truncate.

### 3.2 Why the price is tenths

`core.prices.dollars_to_tenths` is the reader `portfolio_poll.parse_fill`
already uses for `fills.price_tenths`, and the venue sends a 4dp dollar string,
which **is** tenths of a cent. The point of the column is to sit on the same
0–1000 scale as `limit_price_tenths` so the two are directly comparable, which
is the entire reason for storing it.

It is exact for any price a single fill can take. On a multi-fill order
`average_fill_price` is volume-weighted and can land between tenths
(`"0.2005"`), where it is rounded half-up — a twentieth of a cent, recorded
rather than refused, and said out loud in both the column comment and the
parser's docstring rather than left for someone comparing this against `fills`
to find them off by one.

### 3.3 Why the fee is DOLLARS, and why that is not a new exception

`fills.fee_actual` is `REAL` dollars. `portfolio_poll.parse_fill` states the
reason outright: "the one money field in this module not stored in tenths, and
that is the existing table's contract, not a new decision" —
`core.fees.calculate_fee` returns dollars and `gate._fee_model_verified`
compares in dollars. Following that is following a precedent, not opening a
second one.

A second reason applies here and not to the price: **a per-contract fee is
below the resolution of a tenth.** The observed fee on the C0 capture is
`"0.0014"` — 1.4 tenths, which `dollars_to_tenths` writes as `1`, a 29%
understatement of the only number on the row that says what the venue charged.
Storing the fee in tenths would destroy the fact the column exists for.

The name spells `_dollars` for the reason `portfolio_poll` insists on: a tenths
value passed into a dollars comparison is 1000× out and reads as a fee-model
mismatch rather than as a unit error.

### 3.4 NULL means the venue told us nothing, and never zero

Three states, three different facts, and none of them is "the venue charged
nothing":

| state | `venue_fill_count` | price | fee |
|---|---|---|---|
| dry run | `NULL` | `NULL` | `NULL` |
| rejected | `NULL` | `NULL` | `NULL` |
| zero fill (IOC matched no one) | `0.0` | `NULL` | `NULL` |

A dry run builds the outcome with all three unset — no request left. A
rejection means the POST raised and no response was ever read (the order may
still have reached Kalshi; what is certain is that we did not see an answer).
A zero fill is a real, observed `0.0` count beside two money columns that stay
`NULL`, because "nothing filled" is not "nothing was charged at a price of
nothing".

`_venue_price_tenths` additionally refuses anything outside `is_valid_price`:
`dollars_to_tenths("0.0000")` is `0`, and a `0` in a price column reads as a
contract that settled worthless rather than as an absence. Refused, not
clamped — clamping a price onto the edge of the book is the failure
`kalshi/orders.py`'s module docstring exists to describe.

A fee of `0.0` is **kept**. Unlike a price of zero it is a thing the venue can
legitimately report.

### 3.5 `record_outcome` still cannot unwind the order

By the time it runs the request has gone, and a bookkeeping failure must never
report a completed purchase as failed. So the derivation is split in two, the
same shape as `_read_consensus` / `consensus_snapshot` in the same file:

- `_read_venue_fill` may raise, so the refusal is provable by making it throw.
- `venue_fill` wraps it and swallows `Exception` — never `BaseException`, since
  a `KeyboardInterrupt` is the process being torn down and relabelling that as
  a missing fill would hide a shutdown inside a data column.
- The call sits **before** the `try` whose only declared failure is
  `sqlite3.Error`, so an unexpected exception from the derivation cannot be
  reported as a database failure. Pinned by a source-ordering assertion.

If the read fails, the status, the order id and the error text are still
written and the three columns are `NULL` — exactly what they were before the
columns existed.

## 4. What does NOT change

**Additive bookkeeping only.** Nothing about what is sent, ordered, priced or
gated moves.

- `MANUAL_ORDERS_ARE_DRY_RUNS` is unchanged (`False`), `ORDERS_ARE_DRY_RUNS` is
  unchanged (`True`).
- No brake is restored and none is removed (ADR 0112 and its Amendment 1 stand).
- `backend/gate.py` still never reads this table (ADR 0063).
- `_insert_intent`, `reserve_manual_order`, the route's thirteen checks, the
  price ceiling, the depth check and the netting guard are untouched.
- **`/hedge`'s figure is unchanged by this commit.** `core/hedge.py` reads
  `parlay_positions.stake_tenths`, which `_record_combo_position` still
  computes from `order.fill_price_tenths` (the sent ask). Rewiring it to the
  venue's average is a **money-path change** with its own decision to make,
  and is deliberately not taken here. This commit makes that decision
  *possible* by recording the number; it does not make it.
- The `/hedge` figure therefore remains an **upper bound**. Only one of its two
  independent reasons is addressed even in principle; the other is the
  settlement charge, H4, untested (ADR 0027, and `core/hedge.py:43-45`).

## 5. Schema version — PLACEHOLDER

The step is numbered **40 as a placeholder, not an allocation.**
`lane-b-window-index` holds 40 too and is unmerged, so exactly one of the two
lanes renumbers at merge.

40 rather than a "free" 41 because
`tests/test_parallel_lanes_do_not_collide.py::test_every_version_is_accounted_for`
forbids a hole in the version line: a lane cannot skip a number to dodge a
collision, only mark the one it took.

Three places hold the same number and are re-taken **together**, after
`git fetch`:

1. `backend/store/db.py` — `SCHEMA_VERSION`
2. `backend/store/db.py` — the `_MIGRATIONS` key
3. `backend/store/schema.sql` — the `(v40 PLACEHOLDER, 2026-09-11)` marker in
   the `manual_orders` block

All three carry a loud `!! PLACEHOLDER !!` comment. The migration is a column
step: three nullable columns, no default, no backfill, no CHECK (SQLite refuses
`ALTER TABLE ... DROP COLUMN` on a column named by any CHECK, and
`tests/test_store.py::_v1_database` winds the schema back by dropping exactly
these). Every existing row reads `NULL`, which is the truth about it: those
outcomes were recorded before the fields existed and nothing may invent what
the venue said.

## 6. The census registration is NOT the authority for this, and it is still wrong in three places

`docs/measurements/2026-09-10-preregistration-recorded-fill-vs-venue-charge.md`
§8.4 says in terms:

> **8.4 Nothing here moves money-touching code.** … Persisting three columns is
> a recording change, and a recording change only.

and §11.9 lists "nothing that authorises a change to money-touching code" among
what it does not establish. **It is not cited as authority here.** This
decision stands on §1–§4 above: a permanent row that records only what we asked
for, beside a temporary one that records what we were charged, is a record that
forgets the half that cost money.

**Outstanding, and deliberately not fixed by this lane** — amending a
registration is not a lane's call, and the registration is a pre-registration
whose whole value is that it was fixed before the data was seen:

1. §0.1 and §2 (H1) and §8.1 name **`manual_orders.fill_price_tenths`**. No
   such column exists; it is `limit_price_tenths`.
2. §0.1, §2 and §8.1 name **`OrderOutcome.fill_price_tenths`**. The property is
   on `OrderRequest` (`backend/kalshi/orders.py:298`). `OrderOutcome` has no
   such property, which is exactly why nothing the venue returned was ever in
   that column.
3. The preamble ties its decision to "**schema v39**", which has since been
   taken by `idx_odds_event_commence`.

**One thing the brief for this lane listed as an error is not one.** The
registration's §7 cites `backend/api/routes.py:3959` for
`_record_combo_position` writing `fill_price_tenths=order.fill_price_tenths`
into `parlay_positions`, and that citation is correct as of this commit —
verified at `routes.py:3959` and `:4318`. The corrected CLAUDE.md makes the
same attribution.

Correcting (1)–(3) needs a dated amendment by whoever owns the registration.
Recorded here so it is not lost.

## 7. What this does not establish

- **Nothing about whether the venue's numbers are right.** This records what
  came back. The census in §6 is what will compare them against what the desk
  sent, and it cannot run on rows that do not carry the venue side.
- **Nothing about `/hedge` becoming exact.** See §4.
- **Nothing that generalises the V2 response shape.** The fixture is the C0
  probe's one ticker, one day, one series (`tests/fixtures/create_order_responses.json`,
  synthetic by the ADR 0035 precedent because the raw capture is operator
  data). The parser still refuses loudly on any missing field.
- **Nothing about rows already written.** Every `manual_orders` row that exists
  reads `NULL` in all three columns and stays that way. Backfilling from
  `fills` would put a number sourced from a different endpoint at a different
  time into a column whose meaning is "what the create-order response said",
  and a column that means two things is a `NULL` with extra steps.
- **Nothing about the engine path.** `store/orders.record_outcome` and
  `store/combo_orders.record_outcome` drop the same three fields and are
  untouched; the engine has never placed an order, and the bid path is
  disarmed (ADR 0115).

## 8. Tests

`tests/test_manual_order_venue_fill_fields.py`, 29 tests. The wire shapes come
from `tests/fixtures/create_order_responses.json` through the real
`OrderPlacer._read_response`, and the rows are written through the real
`reserve_manual_order` / `record_outcome` against a real `init_db` database.

Fifteen mutations were applied and every one went red; the table is in the lane
report.
