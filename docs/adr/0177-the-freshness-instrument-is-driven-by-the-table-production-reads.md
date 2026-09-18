# 0177 — The freshness instrument is driven by the table production reads

**Status.** Accepted, 2026-09-18.

## The drift

`window-freshness` exists to recompute, at a stated instant, the ages
`backend/odds/timing.py::fixture_freshness` computes live. Its SQL carried a
comment saying so: *"The same shape as `fixture_freshness`, with ONE deliberate
addition: `fetched_ms <= :at`."*

That stopped being true on 2026-09-18, when schema v47 / ADR 0167 re-drove
`fixture_freshness` off the new `odds_fixtures` table — one row per fixture,
maintained by a trigger — because the old form walked the whole `market` prefix
of `idx_odds_window`, every h2h row ever stored, polled every three seconds by
every open tab. That change took `/api/window` from 6,974 ms to 101 ms.

**The instrument was not moved with it.** For four days it kept running the
pre-v47 shape while claiming to mirror production, so the one query whose
entire purpose is "what would the window indicator have said" was answering
with a method the window indicator no longer uses. This is the decayed
justification pattern `tasks/lessons.md` records the same day: the comment
asserting the equivalence is exactly what a reader checks instead of the SQL.

## Decision

**1. Drive all three statements from `odds_fixtures`, as production does.**
`_SQL_FRESHNESS_AT_FIXTURES`, `_SQL_FRESHNESS_AT_BOOKS` and `_SQL_BOOK_ROWS`
now select upcoming fixtures with a seek on `idx_odds_fixtures_commence`, take
each fixture's latest sweep with one correlated seek on `idx_odds_event`, and
read the books within it on `idx_odds_window`. The `:at` pin survives as
`AND s.fetched_ms <= :at` inside the per-fixture subquery, which is what makes
this a retrospective instrument rather than a second copy of production.

`_SQL_BOOK_ROWS` is included **because its own description claims it reads "the
exact population `window-freshness` reads"**. Moving one driver and not the
other would leave two definitions of that population and a sentence asserting
they are one — the drift this ADR exists to undo, re-created in the same file.

**2. The cost classification stays `walks-the-file`, though the walk is gone.**
All three entries remain `WALKS_THE_FILE`, so `main` still refuses them without
`--i-accept-the-cache-flush`. The walk is genuinely removed and the flag is
therefore over-asked — deliberately. Demoting a cost from expensive to cheap on
*reasoning* rather than a measurement is the flattering direction, and the cost
of being wrong is paid by the desk's page cache on a 4 GB box, not by whoever
reclassified it. Reclassifying is a deliberate edit to `KNOWN_WALKS` in
`tests/test_inspect_live_db.py` (pinned by name for exactly this) and wants a
live timing beside it. Note `visit-freshness` runs the freshness query twice
per visit over a default seven days, so it keeps the strongest claim to the
flag even after the other two are timed.

**3. Accept a shorter retrospective reach in exchange for matching
production.** `odds_fixtures` is INSERT/UPDATE-only — `trg_odds_fixtures_upsert`
never deletes — so it only grows. But v47 seeded it with
`commence_ms >= now - 7 days` at migration time, so a fixture whose last
snapshot insert predates v47 *and* whose `commence_ms` fell before that horizon
is absent. `odds_snapshots` has no retention rule, so the old driver did reach
further back. The reach is the price of measuring what the system measures, and
an instrument that is faithful for the instants anyone actually asks about
beats one that is unfaithful for all of them.

**The bound is printed, not documented.** `window-freshness` now emits a third
section, `_fixture_coverage_at`: the driver's row count and its earliest and
latest `commence_ms`. A caller passing an `--at` before `earliest_commence` can
see the population may be short instead of trusting a docstring. One row, one
seek.

## Verified by disabling it

The existing `TestWindowFreshnessMirrorsTheProductionMeasure` suite passed
**unchanged** under the rewrite, which is the main evidence the new driver
computes the same numbers — those tests assert specific ages against a seeded
fixture, and the trigger populates `odds_fixtures` from the same inserts. Two
mutations confirm they are not vacuous against the new shape:

```
age from MIN -> MAX over contributing books
  FAILED test_a_fixtures_age_is_its_oldest_books_stamp   (110000 != 1010000)
  FAILED test_window_freshness_still_reads_the_shared_helper

retrospective pin `AND s.fetched_ms <= :at` removed
  FAILED test_the_instant_pins_which_sweep_is_latest
```

The pin appears three times in the file, so the mutation was applied to
**exactly one** occurrence — `tasks/lessons.md`, same day: a pattern that
matches N patches one of N, and not the one you meant.

`tests/test_inspect_live_db.py`, `test_inspect_live_db_modules.py`,
`test_totals_pricing.py`, `test_window_freshness_index.py`: 463 passed.

## What this does NOT establish

- **Nothing about the new statements' cost.** They were not timed on the live
  volume; that is the whole of Decision 2, and the classification is
  conservative precisely because the measurement is missing.
- **Nothing about how much a short reading is short by.** Decision 3's coverage
  section states the driver's bound. How many fixtures are missing at a given
  `--at` is not knowable from `odds_fixtures` alone, and the section does not
  pretend otherwise.
- **Nothing new about the production measure's own approximation.** It still
  does not drop books that fail to quote every outcome before taking the
  oldest, so a fixture can read staler here than the runner will find it. That
  was true before and is inherited unchanged.
