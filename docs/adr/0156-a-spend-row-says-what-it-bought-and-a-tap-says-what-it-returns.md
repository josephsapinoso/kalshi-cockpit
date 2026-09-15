# 0156 — A spend row says what it bought, a mint path states its side, and a tap says what it returns

Date: 2026-09-15
Status: Accepted
Schema: **v44** (`api_credits.bookmakers`)
Follows ADR 0154 (wrong-side verdict) and ADR 0155 (named books).

Three small corrections, each found by shipping the one before it. They are one
ADR because they share a shape: **a value that was right became a description
that was wrong.**

## 1. `api_credits.bookmakers` — the ledger described a purchase that did not happen

ADR 0155 began sending `bookmakers` **instead of** `regions`, billed at
`markets × ceil(books/10)`. `CreditBudget.record` kept writing only `regions` —
the configured value, not the sent one. The first named-book sweep landed on
live as:

```
2026-09-15T21:10:43Z  baseball_mlb  h2h,spreads,totals  regions=us,eu  cost=3
```

The table's own rule says `cost` is *"what we predicted: markets × regions"*, so
that row reads `3 × 2 = 6` against a recorded 3. The call sent **no regions at
all**.

**`cost` was right throughout**, so the reconciliation this module opens by
claiming as its central safety property — our tally against `x-requests-used` —
never drifted. What was wrong is the only column that says *why* the cost is
what it is, which is the first thing anyone debugging a drift would read.

**Decision.** Add `api_credits.bookmakers` (v44, additive). `record` takes and
writes it. **NULL means "this call bought regions"** — true of every row before
2026-09-15, and not the same as "bought no books". `regions` keeps being
written, so a pre-0155 row reads exactly as it always did; readers take
`bookmakers` first and fall back to `regions` only when it is NULL.

`scripts/inspect_live_db_feed.py` is fixed in the same change: `_CREDIT_COLUMNS`
gained the column, and the comment claiming `cost = markets × regions` now
states the named-book rule. An instrument that showed `regions` alone would
print `us,eu` beside `cost = 3` and invite the reader into the same arithmetic
that made the column necessary.

## 2. The mint path will not guess a side

`echoed_legs` and `lookup_combo` carried `side: str = "yes"` keyword defaults
(`backend/kalshi/combos.py`). Every live caller passes explicit 3-tuples from
`parlays.py:2796`, so the default was unreached — but this is the path that
**creates a market on the exchange**, and the failure it would produce is the
one ADR 0154 and `2d8de82` both produced elsewhere: a NO thing silently treated
as YES, wrong only on the rows that are not YES.

Two holes, closed together:

| | what it did |
|---|---|
| the default | a caller passing bare 2-tuples got `"yes"` without typing it |
| the echo | `leg.get("side", side)` fell back to the **posted** side, so an echo that omits the field compared EQUAL for an all-YES card — agreement reported on a direction Kalshi never stated |

The second is the more serious, and it is the error `echoed_legs`' own docstring
already refuses for the field as a whole (*"`unreadable` is NOT treated as
agreement"*), committed one level down on a single leg.

**Decision.** `side` becomes a required keyword on both functions — a 2-tuple's
fallback is always something a caller chose. A leg in the echo without a `side`
is `unreadable`, never assumed. `_leg_sides` refuses a side that is neither
`yes` nor `no` before it reaches the venue's body, the same refusal as
`_ask_facts_for_side` and `_verdict_facts_for_side` (ADR 0154).

The 2-tuple form is kept: three capture/probe scripts and several tests use it
as shorthand for a single-side card, and they now state the side.

## 3. The tap rate Joe actually experiences

Joe's own report, 2026-09-15 morning: *"I also tried buying it, but ran into an
error that said that i was unable to do so because no one was selling it."*
That is `book_empty`, and nobody had ever quoted it as a rate. Read off live
2026-09-15 over the whole of `parlay_lookups`:

```
77 taps    28 priced    44 book_empty    3 error    2 refused
```

**The desk's core interaction fails more often than it works**, and the screen
did not say so.

**Decision.** A fourth disclosure sentence on `/parlays`, `notes.tap_outcome`,
built from `TAP_CENSUS_*` constants like the three censuses before it, so the
day the census moves and the sentence does not, the test goes red.

**One lifetime figure, and deliberately no per-card breakdown.** Per card the
counts run 2 to 30, and `totals` at 0 of 3 would read as a totals defect when
`P(3 of 3 | base rate 57%) ≈ 0.19` — indistinguishable from the whole. A
per-card rate would be an ordering dressed as a per-row fact, which ADR 0071
§2.5 forbids. The note also says the empty book is the **venue's**, not the
card's, because an honest failure rate with no cause attached reads as "this
desk is broken".

## Consequences

- One migration (v44), additive, no backfill. Old rows keep their meaning.
- No behaviour change to what is bought, priced, hedged or sent. The named-book
  cut itself is ADR 0155 and is unchanged here.
- `/parlays` gains one sentence. No card, ordering or score moves.

## What this does not establish

- **That the 57% rate predicts the next tap.** It is a lifetime count over a
  changing venue, slate and card set, not a forecast. The note says what has
  happened and promises nothing, for the same reason `notes.unquoted` had to
  retract "you can buy in" once already.
- **That a NO-leg combination is ever quoted.** Both `side = "no"` rows in
  `parlay_lookups` (ids 75, 76) are `book_empty`, n = 2, which cannot be
  separated from the base rate either.
- **Anything about why a book is empty.** The rate counts outcomes; the cause
  is ADR 0085's territory and is unchanged.

## Guards, each seen red once

| mutation | test that went red |
|---|---|
| `record` drops `bookmakers` from the INSERT | `test_a_named_book_call_records_the_books` |
| the v44 migration adds no column | `test_the_schema_is_v44`, `test_the_migration_reaches_an_existing_database` |
| `side: str = "yes"` defaults restored | `test_the_side_must_be_stated_not_defaulted` |
| `leg.get("side", side)` restored in the echo | `test_an_echo_that_omits_a_side_is_unreadable_not_a_match` |
| the yes/no check dropped from `_leg_sides` | `test_a_side_that_is_neither_is_refused_before_it_reaches_the_venue` |

`test_the_migration_reaches_an_existing_database` drops the column and stamps
the database back to 43, because a migration that only ever runs against a
freshly created schema proves nothing about the live volume.

## The pattern

Written to `tasks/lessons.md`: **when a call changes what it sends, the row that
records it is part of the change.** ADR 0155 got the arithmetic right and left
the description behind, and the description is what the next reader trusts. The
same shape as the stale comment ADR 0154 found, and as CLAUDE.md's transacted-path
counts going six orders stale in a day — a value and its description drift apart
silently, and only the description is ever read.
