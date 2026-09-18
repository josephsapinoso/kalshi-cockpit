# ADR 0175 — The RFQ row says which of three things happened

**Status:** Accepted
**Date:** 2026-09-18
**Schema:** v49 — `combo_rfqs.status` widened to admit `'priced_too_finely'`,
and `combo_rfqs.refused_too_fine` added
**Ticket:** #77 (build, no decision needed), opened while building #73
**Follows:** ADR 0172, which fixed the same defect on the screen and left it in
the database

---

## 1. The defect, and why it outlives the screen's version of it

ADR 0172 gave the RFQ payload a third outcome. `record_quotes` did not follow:

```python
(stored, STATUS_QUOTED if stored else STATUS_NO_QUOTES, rfq_id)
```

A refused quote never becomes an `RfqQuote`, so it is never in `seen`, so
`stored` is 0, so the durable row read `no_quotes` — which this module's own
constant comment defines in as many words:

> `quoted` and `no_quotes` are deliberately different rows rather than a count
> of zero. "We asked and nobody answered" is a measurement about the market;
> "we asked and never read the answer" is a bug in us, and a single `asked`
> status with `quote_count = 0` cannot tell them apart.

There is now a **third** case — *the market answered and we could not represent
what it said* — and it was filed under the first.

**This matters more than the screen's version did, and in the opposite
direction from how it looks.** The screen is read once, by someone who can go
and check. This row is the **population** any later measurement of *how often a
combination goes unquoted* would count, and it was contaminated in the
**flattering** direction: it made the market look quieter and less liquid than
it is. A screen that lies is caught by the next person to look. A record that
lies is discovered by a measurement built on it, months later, and it is the
measurement that gets blamed.

## 2. The decision

**Three statuses, matching the payload's, with the payload's precedence.**
`quoted` outranks `priced_too_finely`: a stored quote means there was a price to
show, and the reverse ordering would file a takeable price under a complaint.
A mutation reversing it fails.

**`refused_too_fine` is a COUNT and rides along in the same rebuild**, because
"how often" and "which case this was" are different questions and only the count
answers the first. Free in a rebuild that was happening anyway.

**`record_quotes` takes the count as an argument, and that asymmetry is the
point.** `quote_count` is read back *from the table* — deliberately, since it
differs from `len(quotes)` exactly when a write failed. `refused_too_fine`
**cannot** be, because a refused quote is never a row. That is the whole reason
the status was wrong, so the number has to come from the caller, which unions it
by quote id across the poll loop (#73) — the same figure the payload reports, so
the row and the screen cannot disagree about one moment.

**Nullable, no backfill, and no backfill is possible even in principle.** The
refusals were not counted anywhere before ADR 0172, so a pre-v49 `no_quotes` row
is **indistinguishable** from a genuine one. Guessing would put invented data
into the exact column that exists to stop a guess. A migrated row reads `NULL`
("does not know"); a new ask that refused nobody records `0`, which is a real
observation.

**A REBUILD, not a column step** — SQLite cannot widen a table-level CHECK in
place. Same shape and same reason as v35 and v38, whose `_parlay_lookups_create`
helper this copies so the CHECK's two spellings cannot drift. Cheap on the live
volume: `combo_rfqs` is one row per ask.

## 3. The mutation that stayed green, and the gap it exposed

**Narrowing the CHECK inside `_combo_rfqs_create` — i.e. shipping a migration
that rebuilds the table WITHOUT the new status — broke nothing.**

Every other test builds its database from `schema.sql` through `executescript`
and never runs the rebuild at all, so a fresh database got the wide CHECK from
`CREATE TABLE` and passed whatever the migration did. This is the failure
`init_db`'s own docstring already warns about for columns — *"a FRESH database
gets every column from `CREATE TABLE`, so a fixture-built one passes whatever
the migration does"* — arriving on a constraint instead.

And `test_the_schema_file_and_the_migrations_agree` does not catch it either: it
compares migrated **columns** and **indexes** against `schema.sql`, and a CHECK
is neither.

**That is a general gap and it is not closed here.** A rebuild producing a
different constraint from `schema.sql` is invisible for **every** table today —
v4's `settlements`, v10's `fills`, v35 and v38 included.
`TestTheWidenedCheckSurvivesTheMigration` closes only the instance in front of
it, by winding a real database back to v48 and migrating it forward, on the
repo's own "a database that already exists is the only case that matters"
pattern. A generic comparison of constraint text between a fresh and a migrated
database would close the class, and is not written.

## 4. Verification

**168 passed** across the store, route and migration suites. **Six mutations,
all red:**

| | mutation | result |
|---|---|---|
| M1 | the status collapses back to two outcomes | red |
| M2 | `priced_too_finely` outranks a stored quote | red |
| M3 | the count is never written | red, 6 failed |
| M4 | the caller stops threading the refusals through | red |
| M5 | the CHECK is not widened by the migration | red **after** §3's test |
| M6 | the CHECK is turned off rather than widened | red |

M6 exists because **widening a constraint and removing one look identical from
inside**: both make the new status insertable, and only a rejected value tells
them apart. M6's first pattern also matched two helpers and had to be
re-anchored — the third time in one session that a mutation script silently
patched one of N matches, which is now a lesson.

## 5. What this does not establish

- **Nothing about how often a real maker quotes in centi-cents.** The column
  exists so the question becomes answerable. It has no answer, and two rows
  would not be a rate.
- **Nothing about rows written before v49**, which cannot be reclassified even
  in principle (§2). Any measurement over this table must treat `NULL` as
  "unknown" and exclude those rows rather than reading them as zero.
- **Nothing about the other rebuilt tables' constraints** (§3).
- **It does not make the earlier `no_quotes` rows wrong or right.** It makes the
  ones written from now on distinguishable, which is a claim about the future
  population and nothing else.
