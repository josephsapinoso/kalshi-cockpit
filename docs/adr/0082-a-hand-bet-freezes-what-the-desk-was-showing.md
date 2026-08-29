# ADR 0082 — A hand bet freezes what the desk was showing, and a combination records that there was nothing to freeze

**Date:** 2026-08-29
**Status:** Accepted
**Supersedes:** nothing. **Extends:** ADR 0063 (the manual path), ADR 0073
(arming it), ADR 0071 (what the desk is for).

---

## 1. The problem, as it stood this morning

`POST /api/manual-orders` has been armed since 2026-08-26. Joe places real
immediate-or-cancel orders through it, one tap at a time, and the row records
his own typed probability (`p_yes_bp`, `NOT NULL`, `CHECK 1..9999`).

**It records nothing about what he was looking at when he typed it.** Verified
against the schema on 2026-08-29: `manual_orders` had no `fair_price_id`, no
`link_id`, no copy of the devigged consensus, no book count, no anchoring flag,
and no timestamp for when any of that was computed.

The consequence is not inconvenience, it is loss. Recovering the consensus at
the moment of a bet after the fact means re-implementing the matcher chain

    ticker -> kalshi_markets.event_ticker -> event_links -> link_id -> fair_prices

against a nearest-`computed_ms` pick, on tables that retention prunes — and it
is **impossible in principle for a `KXMVE` combination**, because
`backend/kalshi/discovery.py` drops that prefix as junk, so no `kalshi_markets`
row for one has ever existed and none ever will.

So every hand bet placed between arming and this ADR is a bet that can never be
analysed. The table was one 4096-byte page when this was written — single-digit
rows — and the cost of the fix rises every day it is not made.

## 2. The decision

**Snapshot the values onto the row. Do not add a foreign key.**

An FK into `fair_prices` is a pointer into a mutable, retention-eligible table.
It answers *"what does that table say now"*, which is a different question from
*"what did the desk show him"*, and the two diverge silently — the second one
becomes unanswerable and nothing in the record marks the moment it did.

Eight nullable columns, written server-side at intent-write time
(`store/manual_orders.reserve_manual_order`, before `BEGIN IMMEDIATE` so the
write window is unchanged):

| column | type | unit |
|---|---|---|
| `consensus_fair_tenths` | INTEGER | tenths of a cent, 0–1000, for the side BOUGHT |
| `consensus_edge_tenths` | INTEGER | tenths of a cent, signed |
| `consensus_book_count` | INTEGER | books the devig used |
| `consensus_anchored_on_sharp` | INTEGER | 0 / 1 / NULL |
| `consensus_computed_ms` | INTEGER | when the consensus was computed, not when the row was written |
| `consensus_fair_price_id` | INTEGER | breadcrumb, may dangle |
| `consensus_link_id` | INTEGER | breadcrumb, may dangle |
| `consensus_absent_reason` | TEXT | why the snapshot is absent, when it is |

The two id columns are stored because the lookup already read them and a
breadcrumb costs nothing. **They are explicitly not the record.** A reader that
needs the value uses the frozen columns.

Schema **v28**. Additive, nullable, no backfill.

## 3. Where the value comes from, and why not from the matcher

The source is the freshest `recommendations` row for `(ticker, side)`, joined
to `fair_prices` on its own `fair_price_id`.

That is **literally what the Slate row rendered**: `/api/slate` selects the same
join, and `SlateRow.tsx` is the control that opens this door. Re-deriving the
consensus through the matcher chain would be a second implementation of a rule
that already exists, and the failure this repo keeps meeting is two spellings of
one fact that agree until one of them learns something.

It also costs nothing at the tap. The predicate and the ORDER BY are the shape
`engine.persist_if_changed` uses, so `idx_recs_ticker_side` covers it: a seek,
not a scan of a growing table, on the request that spends money.

**No age cutoff.** A ticker names one fixture, so an old row is the same market
rather than a different game. How stale the evidence was is
`submitted_ms - consensus_computed_ms`, recorded rather than judged — a
freshness threshold chosen at the write site would bake one session's opinion
into the record permanently, and permanently is the wrong tense for an opinion.

## 4. Unreadable resolves to `None`, never `0`

For a `KXMVE` combination there **is** no devigged consensus, and
`consensus_fair_tenths = 0` would read as *"the sportsbooks say this is worth
nothing"* — on a money row that is a lie, not a gap.

So every column is nullable and every absence states its cause, from a closed
vocabulary that the audit can count:

    combo_ticker           there is no consensus and never can be
    no_priced_row          the runner never priced this (ticker, side)
    unreadable_fair_value  fair_probability absent or outside [0, 1]
    lookup_failed          the read raised; the order still went

The last one is the only value that means the recorder broke, and it is written
down rather than swallowed so that it can be seen.

`_fair_tenths` bounds-checks before converting, and that check is the guard
rather than decoration: `core.prices.probability_to_tenths` **clamps** to
[0, 1], so passing a corrupted value through it would return a confident 0 or
1000 tenths — a settled outcome, written down as a live consensus.

`ConsensusSnapshot.__post_init__` ties the two halves together: an instance is
either a value with no reason or an absence with one. A silent hole is
unconstructible, so every NULL in the table has a stated cause.

## 5. The order path does not change

This is additive recording and nothing else. If the lookup raises, is slow, or
finds nothing, **the order still goes** and the columns are NULL.
`consensus_snapshot` catches `Exception` and returns the absence.

It deliberately does **not** catch `BaseException`: a `KeyboardInterrupt` or a
cancellation is the process being torn down, and relabelling that as a missing
fair value would hide a shutdown inside a data column.

Proven by `TestTheSnapshotCanNeverBlockABet`, which makes `_read_consensus`
throw and asserts the POST still returns 200 with a row written.

## 6. What this does not touch

- **`gate.py` never reads `manual_orders`.** Unchanged, and pinned by a test
  that also checks the new column names do not appear there. A hand bet still
  cannot move the live-trading interlock's 300-game counter (ADR 0063).
- **No ordering, no ranking, no score.** `beta = -0.141` means agreement with
  the consensus is not evidence of correctness. ADR 0071's rule holds: a
  per-row fact is transparency, an ordering is a claim. These columns are a
  per-row fact.
- **No backfill of the existing rows.** They stay NULL. Re-deriving a
  consensus from `fair_prices` as it stands *now* would produce a number that
  is, afterwards, indistinguishable in the record from one taken at the tap.
  That is exactly the contamination the snapshot exists to prevent, so the
  record says it did not know.
- **No CHECK constraints on the new columns.** SQLite refuses
  `ALTER TABLE ... DROP COLUMN` on a column named by a CHECK, and
  `tests/test_store.py::_v1_database` winds the schema back by dropping every
  migrated column. A constraint would make the migration untestable, which is
  worse than the constraint is good. The invariants live in
  `ConsensusSnapshot` instead, where they are enforced before the write.

## 7. Reading the record: `manual-orders-audit`

`scripts/inspect_live_db.py` is a fixed whitelist of named queries and none of
them touched `manual_orders`, so nobody could count the hand-bet record on live
without shipping code. One subcommand is added, six sections, **structure and
counts only**: the census, status buckets over a fixed vocabulary, snapshot
coverage split by whether the ticker is a combination, the absence reasons,
rows per ticker with the largest one's share, and contracts per order.

**It may never report P&L, profit, win rate, CLV, a settled outcome, or his
typed estimate.** `docs/measurements/2026-08-29-preregistration-operator-self-
assessment.md` fixes — before any result was seen — which panels on Joe's own
record may carry a verdict and at what `G`. An inspector that could print a win
rate would let the decision rule be chosen after the answer, on the
highest-flattery-risk measurement this project has attempted. That registration's
§0 records that the row count was *deliberately* not obtained while it was being
written, so no floor in it could be tuned to `n`; this query is what makes the
count available afterwards, scoped so that obtaining it cannot also obtain the
answer.

The prohibition is asserted over the SQL strings in
`tests/test_inspect_live_db.py`, not only stated in the docstring, because a
docstring is not read by the next edit.

## 8. What this does not establish

- **Nothing about whether the consensus was right.** It records what the desk
  showed. `beta = -0.141` is the reason that is not the same claim.
- **Nothing about coverage.** A snapshot will be absent far more often than
  present — every combination, every ticker no pass ever priced. Any later
  measurement must print the covered fraction beside any number derived from
  these columns, which §6b of the registration already requires.
- **Nothing about the rows already on the volume.** They are NULL and stay
  NULL. The population that can be analysed begins at this deploy.
- **Nothing about whether an order filled.** `status` is what this process
  wrote after reading the response, and `unrecognised_response` means it could
  not tell.
