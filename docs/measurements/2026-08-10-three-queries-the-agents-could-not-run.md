# Three queries neither agent could run — for Joe, on the live box

**Date:** 2026-08-10
**Status:** Specified, **not run.** No agent in this session had access to the
live database.
**Why this file exists:** ADR 0021's §7.2 quotes a magnitude measured on a
fixture that does not overlap the record it is applied to (see that section's
2026-08-10 annotation). Three questions decide whether that magnitude can be
re-measured on the record itself, or whether it is gone. All three are cheap,
all three are read-only, and **none of them spends an Odds API credit or
touches money.**

**Filed here rather than in `tasks/` deliberately.** These are measurement
specifications with pre-stated expected outputs, they belong beside the
registration and the result they follow from, and the reader most likely to need
them arrives from ADR 0021 — which links here from both annotated sections. The
lesson in `tasks/lessons.md` also points here.

---

## How to run them, and the access problem, stated first

`/api/*` exposes no arbitrary-SQL route, so these need a shell on the live
machine:

```
flyctl ssh console -a kalshi-cockpit
sqlite3 /data/cockpit.db
```

**`flyctl` is a laptop job and this tool is operated from a phone.**
`fly.live.toml` says so in its own comments, about a different hazard. That is a
real obstacle rather than a caveat, and it is the reason these are written down
instead of run: whoever is next at a laptop should paste all three in one
sitting.

**Q2 is the exception and is nearly free to unblock.** See its note below.

**Every statement below was executed before this file was published** — against a
database built by `backend.store.db.init_db` (the real schema, real migrations)
and seeded to reproduce the shape that breaks naive queries: two events, **two**
sweeps sharing one `fetched_ms` each, 29 books per event with three of them
sharp, recommendations created *between* the sweeps, and one deliberately
unlinked row. They parse, they run, and they return what each "expected output"
claims: `(usable_books 29, sharp_books 3)` per event-sweep, `unlinked = 1`,
`(linked_rows 2, unresolvable 0)` and `(checked 2, reproduces 2)`.

**Three defects were caught that way, and none of them would have raised an
error — each returns a confident wrong number.** They are named because they are
the reason to distrust unrun SQL in a document:

- **Q3 Level 1 originally took a *global* `MAX(fetched_ms)` per event and then
  filtered `<= created_ms`.** On the seed above it reports **`unresolvable = 2`
  out of 2** — total data loss — when both rows resolve cleanly to the first
  sweep. The runner sweeps each event repeatedly, so this would have condemned
  every row except those from an event's final sweep, and the reading table maps
  that to *"sweeps have been pruned … the magnitude is unrecoverable."* **A
  guard that fires when nothing is broken is worse than no guard**, and this one
  would have retired a live question on a query bug.
- **Q3 Level 2's join matched on `fetched_ms` alone** while its subquery was
  grouped by `(odds_event_id, fetched_ms)`. One sweep covers ~15 events at one
  instant, so it fanned out and returned `checked = 4` from 2 rows — comparing
  each row against other events' stamps while `reproduces` tracked along and the
  output looked healthy.
- **Q1's second query counted *books* in one column and *rows* in the other**,
  printing `29` beside `6` for a three-book keep, because each book quotes two
  outcomes. It also emitted no `sport_key`, so it could not have satisfied the
  reading table's own requirement to report MLB and WNBA separately.

**Paste-ready SQL in a document is code**, and it earns this repo's
disable-it-and-watch-it-fail treatment like anything else.

---

## Q1 — Does `odds_snapshots` still cover the record's window, and with how many books?

**The question this settles.** ADR 0021 §7.2 says sharp anchoring "discards a
median of 26 of 29 usable books". That `29` is measured on
`tests/fixtures/odds_mlb_h2h_spreads_totals.json`, captured
**2026-08-07T13:49:22Z**, against a record whose odds observations run
**2026-08-07T19:28:12Z → 2026-08-09T23:35:18Z** — zero of 1,564 rows overlap it,
minimum gap 5.65 hours. This query asks whether the record can answer the same
question about itself.

**Why it is answerable at all.** The ingest path filters by **market**, never by
**book**: `OddsClient._parse` (`backend/odds/client.py:300-323`) drops market
keys outside `PRICEABLE_MARKETS` and keeps every bookmaker that quotes one, and
`store_quotes` (`:395-414`) writes them all. `runner.SHARP_BOOKS` anchoring
happens later, inside `consensus_devig` (`backend/runner.py:658`), on data
already stored. **So if the sweeps are still on disk, the discarded books are
still on disk with them** — which is the whole reason this is worth asking.

```sql
-- Coverage in time, rows, and books, per sweep-day.
SELECT date(fetched_ms / 1000, 'unixepoch')          AS day,
       COUNT(*)                                      AS rows,
       COUNT(DISTINCT fetched_ms)                    AS sweeps,
       COUNT(DISTINCT odds_event_id)                 AS events,
       COUNT(DISTINCT bookmaker)                     AS books,
       COUNT(DISTINCT sport_key)                     AS sports
  FROM odds_snapshots
 GROUP BY day
 ORDER BY day;

-- The number §7.2 needs: books per event per sweep, h2h only, and how many of
-- them survive anchoring. Report the MEDIAN, not the mean -- §0.6 quoted a
-- median and the two must not be compared.
-- Three things this query has to get right, each of which was wrong in a
-- draft of this file:
--   * Both columns count BOOKS. Counting rows for one and books for the other
--     puts 29 beside 6 for a three-book keep, because each book quotes two
--     outcomes -- two units in one comparison.
--   * It groups and orders by `sport_key`. The reading table below REQUIRES
--     MLB and WNBA separately, and a query that cannot produce that would
--     reintroduce the exact population error this file exists to prevent.
--   * SQLite has no median. Take it OUTSIDE SQL, per sport_key, over
--     (usable_books - sharp_books). Do not substitute AVG.
SELECT sport_key, odds_event_id, fetched_ms,
       COUNT(DISTINCT bookmaker)                     AS usable_books,
       COUNT(DISTINCT CASE WHEN bookmaker IN
              ('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')
           THEN bookmaker END)                       AS sharp_books
  FROM odds_snapshots
 WHERE market = 'h2h'
 GROUP BY sport_key, odds_event_id, fetched_ms
 ORDER BY sport_key, usable_books;
```

**Expected output if the rows are intact.** The first query should show three
day-buckets spanning 2026-08-07 to 2026-08-09 at minimum, `sports` = 2
(`baseball_mlb`, `basketball_wnba`), and — this is the number that decides
everything — `books` in the **high twenties**, not 3 or 4. The second should
return one line per (event, sweep) with `usable_books` clustered near the
fixture's 29 for MLB.

**What each answer means.**

| Reading | Meaning |
|---|---|
| `books` ≈ 29 | §7.2's magnitude is **re-measurable on the record**. Take the per-league median off the second query and the borrowed fixture number can be retired. |
| `books` ≈ 3–4, `sharp_books` ≥ 2 | Only the anchored survivors were ever retained. The magnitude is **gone for this record** and §7.2's annotation is permanent. |
| `books` ≈ 3–4 **and** `sharp_books` = 0 | Not a retention story at all — the live `ODDS_REGIONS` was narrowed off the `us,eu` default, so `betfair_ex_eu` and `matchbook` never arrived. Check `fly.live.toml` before concluding anything about the data. |
| `sharp_books` = 0 on any row with `usable_books` ≥ 5 | The `selected = sharp or usable` fallback fired on that fixture: the row was priced against a **wide** consensus. This is the quantity ADR 0021 §7.2's annotation calls unobserved. |
| No rows before ~2026-08-09 | The window has been pruned by something not in `backend/`. That is itself a finding and Q3 becomes the urgent one. |
| Fewer books for WNBA than MLB | Expected, and it must be reported per league. §0.6's fixture is MLB-only, so a pooled median would repeat the population error this file exists because of. |

**One estimator caveat, larger than the median-vs-mean one above.**
`COUNT(DISTINCT bookmaker)` over `odds_snapshots` is **not** §0.6's
`usable_book_count`, which counts only books that quoted **every** outcome and
devigged successfully (`backend/core/devig.py`). The two coincide on the fixture
(29 = 29) and need not coincide on the record. Report which one you computed.

**Caveat, and it is the whole point of the caveat.** **Nothing in `backend/`
deletes from `odds_snapshots`.** The only `DELETE FROM` anywhere under
`backend/` is `backend/seed_demo.py:203`, a table-reset loop that names
`odds_snapshots` at `:200` and runs only against the demo database. The live
instance also has a persistent volume (`fly.live.toml`, `[mounts] source =
"cockpit_data"`), so a redeploy does not take the disk with it.

**"No code deletes it" is not "the rows are there."** It says nothing about a
volume that was recreated, a machine replaced, a manual `sqlite3` session, a
restore from an older snapshot, or a `DB_PATH` that pointed somewhere else for a
while. Run the query. The absence of a deleter is a reason to *expect* rows, not
evidence of them — this repo has been caught by exactly that inference before
(`tasks/lessons.md`, *code with no caller is not a feature*, in its mirror form).

---

## Q2 — How many recommendations have no link?

```sql
SELECT COUNT(*) AS unlinked FROM recommendations WHERE link_id IS NULL;

-- And the part the bare count cannot tell you: whether it is old rows or a
-- live defect.
SELECT strategy_config_version                       AS cfg,
       COUNT(*)                                      AS n,
       SUM(CASE WHEN link_id IS NULL THEN 1 ELSE 0 END) AS unlinked,
       MIN(created_ms)                               AS first_ms,
       MAX(created_ms)                               AS last_ms
  FROM recommendations
 GROUP BY cfg;
```

**The question this settles.** `link_id` is the only path from a row back to
the sportsbook fixture it was priced against —
`recommendations.link_id → event_links.odds_event_id → odds_snapshots`. A NULL
severs it, and a severed row **cannot be re-priced, re-devigged, or checked
against the books that produced it, ever**, whatever Q1 returns. Q3 is
meaningless for those rows by construction.

**Expected output.** `unlinked = 0`. The column is nullable in the schema but
`engine.persist_recommendation` is reached only through a linked candidate, so a
non-zero count means either rows predating the column or a path nobody has
traced. **Any non-zero value is a finding, not a nuisance** — report the count
and the `created_ms` range rather than filtering them out, because "N rows are
unreachable" changes the denominator of every re-measurement this file proposes.

**Read it against 1,564, not against 614.** 614 is the *clean* population.
`link_id` is not a suppression input, so an unlinked row can be clean, and
quoting the count against the smaller denominator would flatter it.

> **This one is a one-line change away from being answerable from a phone, and
> that change was deliberately not made.** `link_id` is a column of
> `recommendations`, so the ledger route's `SELECT r.*` **already puts it in the
> result set** (confirmed by reading `cursor.description`: `link_id` is there,
> and `market_width` / `book_count` / `books_used` are not) — `_serialise`
> simply never names it, which is why no pinned pull carries it either. That
> is the identical two-barrier shape as `market_width` / `book_count` /
> `books_used`, except that here only the second barrier is up. Adding
> `"link_id": row["link_id"]` to `_serialise` would make Q2 answerable by
> pulling `/api/ledger` from a browser. It is left undone because the lane brief
> scoped the payload widening to exactly three named fields, and widening a
> payload past its brief is how a change stops being reviewable. **Joe's call.**

---

## Q3 — Is each row's sweep still resolvable?

**The question this settles.** Q1 asks whether *any* odds survive. Q3 asks the
strictly harder thing: whether the **specific** sweep that priced each
recommendation can still be found. Reproducing §7.2's magnitude row-by-row needs
this; a day-level coverage count does not establish it.

**How resolution works.** `book_quotes_for_event`
(`backend/runner.py:222-236`) reads **one sweep** — `MAX(fetched_ms)` for that
event and market — never the union. So the sweep behind a row is the newest
`odds_snapshots.fetched_ms` for its `odds_event_id` at or before its
`created_ms`.

```sql
-- Level 1: does any sweep survive at or before each row's creation?
--
-- The correlated MAX matters. Taking a GLOBAL max per event and THEN filtering
-- `<= created_ms` asks a different and wrong question -- the runner sweeps each
-- event repeatedly, so every row except those from an event's final sweep would
-- come back "unresolvable" while being perfectly resolvable. That is a guard
-- that fires when nothing is broken, and the reading table below would have
-- mapped it to "sweeps have been pruned".
WITH r AS (
  SELECT rec.id, rec.created_ms, el.odds_event_id
    FROM recommendations rec
    JOIN event_links el ON el.id = rec.link_id
)
SELECT COUNT(*) AS linked_rows,
       SUM(CASE WHEN (SELECT MAX(o.fetched_ms) FROM odds_snapshots o
                       WHERE o.odds_event_id = r.odds_event_id
                         AND o.market = 'h2h'
                         AND o.fetched_ms <= r.created_ms) IS NULL
                THEN 1 ELSE 0 END) AS unresolvable
  FROM r;

-- Level 2: does the surviving sweep REPRODUCE the row's own freshness?
-- `odds_age_ms` is `created_ms` minus the oldest contributing book's
-- `book_updated_ms` (`backend/runner.py:252-304`). If that identity does not
-- hold, the sweep found is not the sweep used.
WITH r AS (
  SELECT rec.id, rec.created_ms, rec.odds_age_ms, el.odds_event_id
    FROM recommendations rec JOIN event_links el ON el.id = rec.link_id
), best AS (
  SELECT r.id, r.created_ms, r.odds_age_ms, r.odds_event_id,
         MAX(o.fetched_ms) AS sweep
    FROM r JOIN odds_snapshots o
      ON o.odds_event_id = r.odds_event_id AND o.market = 'h2h'
     AND o.fetched_ms <= r.created_ms
   GROUP BY r.id
)
SELECT COUNT(*) AS checked,
       SUM(CASE WHEN ABS((b.created_ms - u.oldest) - b.odds_age_ms) <= 1000
                THEN 1 ELSE 0 END) AS reproduces
  FROM best b
  JOIN (
      SELECT odds_event_id, fetched_ms,
             MIN(COALESCE(book_updated_ms, fetched_ms)) AS oldest
        FROM odds_snapshots WHERE market = 'h2h'
       GROUP BY odds_event_id, fetched_ms
  ) u ON u.fetched_ms = b.sweep AND u.odds_event_id = b.odds_event_id;
```

**Expected output.** Level 1: `unresolvable = 0`. Level 2: `reproduces` close to
`checked`.

**Check `checked == linked_rows` before reading anything else.** Level 2 joins
through a grouped subquery, and if the join key is ever incomplete it fans out —
a sweep covers ~15 events at one `fetched_ms`, so the count inflates by roughly
15x while `reproduces` inflates with it and the result still looks healthy.
**`checked > linked_rows` means the query is broken, not the data.**

**Read the two levels separately and never pool them.** They fail for different
reasons and the difference is the finding:

| Level 1 | Level 2 | Meaning |
|---|---|---|
| 0 unresolvable | ≈ all reproduce | The record is fully re-derivable. §7.2's magnitude can be re-measured row-by-row. |
| 0 unresolvable | many fail | Sweeps survive but the *wrong* ones are being matched — most likely the `MIN`/oldest-book reconstruction, since `odds_age_ms` takes the oldest book **that quoted every outcome**, and books dropped for a partial line are excluded there and included here. Treat a Level-2 miss as a bug in this query before treating it as data loss. |
| many unresolvable | — | Sweeps have been pruned. Only Q1's day-level counts remain usable and §7.2's magnitude is unrecoverable. |

**Level 2 is deliberately the weaker claim of the two.** It uses
`COALESCE(book_updated_ms, fetched_ms)`, which is the same optimistic fallback
the runner applies, and it does not reconstruct the "quotes every outcome" drop.
So a mismatch is a reason to look, not a result. **Do not report Level 2 as a
data-integrity number.**

---

## What these three do NOT establish

- **Nothing about whether an edge exists.** They are provenance queries. Every
  prohibition in ADR 0021 §1 and §3 applies unchanged to anything computed from
  their output.
- **They cannot un-lose data.** If Q1 or Q3 returns thin, ADR 0021 §7.2's
  annotation is permanent for this record and the honest response is to record
  that, not to reach for the fixture number again.
- **A good answer to Q1 does not license re-quoting `26 of 29`.** It licenses
  *re-measuring* it. The new number would be a different measurement on a
  different population and needs to be labelled as one — which is the entire
  lesson this file exists to enforce.
- **`81ffd9c` does not help here.** It puts `market_width`, `book_count` and
  `books_used` on `/api/ledger` for rows written **from now on**. It rewrites
  nothing already stored, so the 1,564 rows ADR 0021 is about stay unobserved on
  all three regardless of what these queries return.
