# 0176 — A migrated database is compared on shape, not on column names

**Status.** Accepted, 2026-09-18. Generalises ADR 0175 §3, which closed only
the v49 instance and said in terms that the generic guard was unwritten.

## The hole

`tests/test_store.py::TestMigration::test_the_schema_file_and_the_migrations_agree`
compares a migrated database against `schema.sql` on **migrated column names**
and **index names**. It never reads `sqlite_master.sql`. So everything else a
`CREATE TABLE` declares — CHECKs, NOT NULLs, DEFAULTs, UNIQUEs, types, foreign
keys — was unverified between the two paths a database can arrive by.

That is not a theoretical gap. Shipping v49 narrowed a CHECK inside a rebuild
step and **the entire suite stayed green**, because every fixture in this repo
builds its database with `executescript` on `schema.sql` and never runs the
rebuild at all. `init_db`'s own docstring has always warned about this shape —
"a FRESH database gets every column from `CREATE TABLE`, so a fixture-built one
passes whatever the migration does" — but it warns about *columns*, and the
guard that discharges it enumerates *columns*. The same trap arrives on
constraints and nothing was looking.

**22 tables in `backend/store/schema.sql` carry CHECK constraints**, including
`orders`, `fills`, `manual_orders`, `parlay_positions`,
`parlay_position_legs` and `combo_rfqs` — the armed money path.

The general shape, recorded in `tasks/lessons.md` the same day: **a guard that
enumerates one kind of schema object gets read as covering the schema.**

## Measured before it was fixed

Walking every one of the 40 migrations — wind a fresh database back to v(N−1),
migrate it forward, compare the full DDL against a database built from
`schema.sql` — found **zero** divergences on anything except column order.
Every CHECK, NOT NULL, DEFAULT, UNIQUE, type and reference already agreed.

So this ADR fixes no live defect. It closes the route by which one could ship
unseen, which is the only thing that can be claimed and is stated here so a
later session does not read the guard's arrival as evidence that something had
been wrong.

## Decision

Compare the two databases on **normalised DDL, as a multiset of top-level
clauses**, at both boundaries:

- **per step**, folded into
  `test_each_single_step_runs_on_a_database_one_version_behind`, which is the
  transition a deployed volume actually makes. Folded in rather than given its
  own parametrised test because that test is the only place that already holds
  a single-step-migrated database, and winding 40 versions back a second time
  would double the slowest test in the file to re-derive one.
- **over the whole sweep**, in a new
  `test_a_swept_database_has_the_same_shape_as_a_fresh_one`, which is the
  transition every fixture and every restored backup makes. Both are kept
  because a rebuild that is correct stepwise can still land somewhere else when
  it runs after another rebuild.

Three normalisations, each for a reason that would otherwise make the guard
fire on a non-difference:

1. **SQL comments are stripped.** `schema.sql` carries the canonical column
   commentary and a rebuild's DDL does not. A difference in prose is not a
   difference in shape.
2. **Identifier quoting is stripped.** `ALTER TABLE … RENAME TO` leaves the new
   name quoted (`"combo_rfqs"`) where `schema.sql` does not.
3. **Column ORDER is not compared.** A migrated column arrives by
   `ALTER TABLE ADD COLUMN` and lands at the end; `schema.sql` declares it
   inline. The two orders differ on **12 objects today** with nothing else
   between them. Nothing in this repo reads a row positionally — `row_factory`
   is `sqlite3.Row` throughout — so ordering is a difference without a
   consequence, and a guard that failed on all 12 on day one would be weakened
   or deleted rather than heeded. Hence a multiset: order drops out and
   everything else survives.

The split is **depth-aware**, so `CHECK (status IN ('a', 'b'))` stays one
clause rather than becoming fragments that would compare equal to a different
constraint built from the same pieces. It is a **multiset, not a set**, because
two identical clauses are a different shape from one. A statement with no
parenthesised body is compared **whole** rather than dropped — a splitter that
returns nothing for a shape it did not anticipate is a guard that passes on the
case it did not understand.

## Verified by disabling it

Per CLAUDE.md's testing rule, and against the exact defect ADR 0175 records as
having stayed green:

```
mutation: v49's forward rebuild emits the NARROW CHECK, schema.sql untouched

FAILED test_a_swept_database_has_the_same_shape_as_a_fresh_one
FAILED test_each_single_step_runs_on_a_database_one_version_behind[49]

  migrating v48 -> v49: table:combo_rfqs has a different shape on a migrated
  database than on one built from schema.sql.
    only in schema.sql : ["CHECK (status IN ('asked', 'quoted', 'no_quotes',
                          'error', 'priced_too_finely'))"]
    only in migrated   : ["CHECK (status IN ('asked', 'quoted', 'no_quotes',
                          'error'))"]
```

The failure message names the **clause**, not merely the object, deliberately.
"`combo_rfqs` differs" would send the next session to diff two 20-line
`CREATE TABLE` statements by eye, which is the conditions under which the
narrowed CHECK shipped in the first place.

The mutation was applied and reverted **by hand, not with `git checkout`** —
`tasks/lessons.md` records that checking out to undo a mutation also erases
uncommitted real work, and the guard under test was itself uncommitted at that
moment.

## What this does NOT establish

- **Nothing about data.** It compares declared shape. A migration that
  preserves every constraint and drops every row passes this and is caught, if
  at all, by the row-count assertions elsewhere in `TestMigration`.
- **Nothing about column order**, by choice — see Decision 3. If something ever
  does read a row positionally, this guard will not be what catches it.
- **Nothing about a constraint SQLite does not record in `sqlite_master`.**
  `PRAGMA foreign_keys`, triggers created outside `schema.sql`, and anything
  applied at connection time are all outside what is compared.
- **Nothing about whether the constraints are the RIGHT ones.** It asserts the
  two paths agree, not that either is correct. Widening a CHECK in both places
  passes — and note the sibling trap `tasks/lessons.md` records, that
  **widening a constraint and removing it look identical from inside**, so the
  test that separates those is still the one asserting a bad value is refused.

## Cost

`tests/test_store.py` runs 111 tests in ~21s, unchanged within noise: the
per-step assertion reuses a database the test already built, and the sweep test
adds one migration run.
