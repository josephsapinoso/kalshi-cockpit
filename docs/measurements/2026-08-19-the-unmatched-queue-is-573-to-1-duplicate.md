# The unmatched queue is 573:1 duplicate, and collapsing it at boot costs eight minutes

**Taken:** 2026-08-19, ~23:20–00:10Z, against the live instance (`kalshi-cockpit`,
`f198404`, 2 GB, healthy).
**Feeds:** ADR 0056.

## What was asked

`tasks/NEXT.md` named `unmatched_events` as "the next table with this shape" —
the same append-a-row-per-pass problem ADR 0055 had just fixed for
`kalshi_quotes` — and estimated ~1.7M rows/day against a 7-day window. The
question was whether the ADR 0055 fix shape applies.

## What the table holds

```
total rows                              788,944
distinct (side, identifier, league)         983
distinct + detail                         1,245
distinct + detail + reason                1,376     <- the work items
distinct reason strings                     559
rows ever marked resolved                     0
```

**573 rows per work item.** The eight largest:

```
kalshi  KXNCAAFGAME-26SEP18HOUTTU   NCAA Football   2477 rows,  1 distinct reason
kalshi  KXNCAAFGAME-26SEP19LSUMISS  NCAA Football   2477 rows,  1
kalshi  KXNCAAFGAME-26SEP19MSUND    NCAA Football   2477 rows,  1
kalshi  KXNFLGAME-26SEP13ARILAC     Pro Football    2477 rows,  1
kalshi  KXNFLGAME-26SEP13DALNYG     Pro Football    2477 rows,  1
kalshi  KXNFLGAME-26SEP13GBMIN      Pro Football    2477 rows,  1
kalshi  KXNFLGAME-26SEP13MIALV      Pro Football    2477 rows,  1
kalshi  KXNFLGAME-26SEP13WASPHI     Pro Football    2477 rows,  1
```

The identical 2,477 is the number of passes since the last prune, not a
coincidence: these are out-of-season NFL and NCAA fixtures listed on Kalshi with
no sportsbook counterpart, so the linker fails on them every single pass and
will keep failing until those seasons start.

**`resolved` is 0 on all 788,944 rows.** No code path sets it. This is a queue
designed to be worked by hand and it has never been worked once.

## The measurement that changed the design

The intended fix was a schema migration collapsing the table in place. Rehearsed
against live before writing it:

| statement | time |
|---|---:|
| `COUNT(*)` over the table | **1.6 s** |
| `GROUP BY side, identifier, COALESCE(league,''), COALESCE(detail,''), reason` | **229.4 s** |
| `CREATE TABLE t AS SELECT * FROM unmatched_events` (400 MB, scratch db) | **218.2 s** |
| `DROP TABLE t` (181,154 pages) | **217.6 s** |

The `GROUP BY` is 143× the `COUNT(*)` over the same rows because it sorts on
five columns, two of which are long free-text sentences, and spills.

Migrations run in `init_db`, at boot, before uvicorn binds. So the intended
change was a **four-to-eight minute boot**, under a health check that does not
wait, on a volume that cannot be recreated — and the version stamp is written
only after the whole step succeeds, so a machine killed part-way re-runs it from
the top. That is a crash loop, and it is the v11 failure this repo already
survived once.

The migration was built, tested (11 guards, each verified by breaking it), and
**thrown away on this measurement**. ADR 0056 records what replaced it.

## What this does NOT establish

- **These timings are not properties of the disk.** They were taken from a box
  concurrently serving quote passes at ~50% IO pressure, and the rehearsal's own
  load pushed `recorder.age_ms` from 5.9 s to 28 s while it ran. A quiet box —
  which is what a boot actually is — would be faster, possibly much faster. This
  is the *same* trap as the prune-loses-to-the-writer file corrected earlier the
  same day: **a number taken from a loaded system describes the load.**

  **The design deliberately does not depend on how much faster.** What was
  chosen is O(1) at boot whether the disk is fast or slow. That is the correct
  response to an uncertain number — not a reason to go and re-measure it, and
  not a licence to quote 229 s as a fact about SQLite.

- **573:1 is not a constant.** It is a ratio between a table that grows without
  bound and a work list that does not, so it is a function of how long the table
  has been accumulating since the last prune. It measured ~548:1 four hours
  earlier the same day. Only the 1,376 is stable; the numerator is a clock.

- **1,376 work items is not 1,376 distinct problems.** 983 of them are distinct
  `(side, identifier, league)` triples; the remaining ~393 are the same fixture
  recorded under a changed `detail` or `reason`. Whether those are separate work
  or one item whose description drifted has not been examined.

- **Nothing here says the queue is worth keeping.** It says it is cheap to keep
  once deduplicated. Nothing has ever read it and nothing has ever resolved a
  row; a defensible alternative is to delete the table outright. That decision
  was not taken here.

- **No latency claim.** `record_unmatched` was 8,162 ms in one `link slow` line
  on 2026-08-19 at 19:31Z, on a memory-starved box, and 60–260 ms afterwards.
  Neither figure was taken against the new shape.
