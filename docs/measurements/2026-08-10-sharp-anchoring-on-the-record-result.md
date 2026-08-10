# Sharp anchoring, measured on the record's own rows

**Run** 2026-08-10, read-only against the live database
(`kalshi-cockpit:/data/cockpit.db`, opened `mode=ro`), no Odds API credit spent.
**Harness** `docs/measurements/2026-08-10-sharp-anchoring-census.py`.
**Raw output** `docs/measurements/2026-08-10-sharp-anchoring-on-the-record-run.txt`.
**Population** recommendation `id <= 1564` -- the same 1,564 rows as
`2026-08-10-clean-shortfall-pull.json`. The table had grown to 1,676 by run
time; the extra 112 are excluded deliberately.

This replaces a fixture figure in ADR 0021 section 7.2 with an observation of
the record. It is good news for the project twice over -- it retires an
annotated unknown, and it weakens the tautology objection -- so every figure
below is stated with its unit and its denominator, and the two places the good
news is smaller than it first looked are marked.

---

## The one-line answer

On the record's own rows, sharp anchoring discarded **a median of 19 usable
books of 21**, and on **423 of the 1,564 rows (27.0%)** it did not bind at all:
no sharp book had quoted, and those rows were priced against the full book set.
Those 423 rows produced **zero** positive edges among the unsuppressed ones and
**zero** actionable rows.

---

## 1. The magnitude -- the unit decides the number

Three units, three different numbers, all correct for their own question. The
census as first run reported the middle one.

| Unit | n | usable books | sharp kept | **discarded** |
|---|---|---|---|---|
| Per `(event, fetch instant)`, all stored | 234 | 23 | 3 | **20** |
| Per event | 68 | 23 | 2.5 | **20.5** |
| **Per recommendation row (pinned)** | **1,564** | **21** | **2** | **19** |
| Per *clean* (unsuppressed) row | 614 | 25 | 3 | 22 |

All medians. Mean discarded per row is 18.98.

**The row is the right unit for section 7.2**, because 7.2 is a statement about
what the comparison was *on the record's rows*. Instant-weighting gives a fetch
instant that produced 2 rows the same weight as one that produced 44 (observed
range 2-44 rows per consumed instant), and it counts 62 instants the runner
**never read at all**. Event-weighting is the fixture's unit, and is the right
one only for the fixture-to-record comparison in section 3 below.

`usable` is well defined here: it means books that quoted every outcome, and on
this record it equals the full book set minus **12** partial-quote drops across
**3** instants. The devig step rejected **zero** books -- proven, not assumed,
in section 5.

**Parts agree.** Instants per event run 1 / 3.5 / 7 (min/median/max); the
largest single event is 3.0% of instants and the top five are 13.2%. Nothing is
carried by one fixture. Per-event median-sharp-kept is 3 for 33 of 68 events,
0 for 10, and spread across 1-2.5 for the rest.

## 2. Replacement wording for section 7.2

> `consensus_devig` is anchored on `runner.SHARP_BOOKS`, and over the 1,564 rows
> this ADR is about the anchoring **discards a median of 19 usable books of 21**,
> keeping `pinnacle` + `betfair_ex_eu` + `matchbook`. **On 423 of those rows
> (27.0%) it discarded nothing, because no sharp book had quoted** -- those rows
> were priced against the full book set, a median of 12 books.

## 3. The fixture was not wrong, it was measuring a fatter market

Re-derived on the same unit the fixture used (per event): the fixture gives 26
discarded of 29; the record gives **20.5 of 23**. The fixture overstates by
about 5.5 books on the like-for-like unit -- consistent with its own stated
provenance as a mature-MLB capture 8.9-12.4h from first pitch, when more books
are up. `26 of 29` remains quotable only as a fixture figure. It is now
superseded for the record by `19 of 21` (per row) and `20.5 of 23` (per event),
which must never be swapped for each other.

## 4. `betfair_ex_uk` contributes nothing, and the cause is NOT established

`betfair_ex_uk` appears **0 times** in `odds_snapshots` -- all three markets,
the entire window, 25,184 rows, 68 events. Not rare: absent. Consequences:

- `max sharp kept = 3` across all 234 instants, and `= 4` on none. A
  four-member constant has an effective size of **three**.
- Every sentence in the record of the form "anchored on the sharps" has been
  about at most three books.

An independent verbatim Odds API capture with the same request parameters
(`tests/fixtures/odds_mlb_h2h_spreads_totals.json`, `regions: [us, eu]`,
30 bookmakers) also contains **0** `betfair_ex_uk` while containing
`betfair_ex_eu`, `matchbook` and `pinnacle`. So this is a property of what the
API returns under this configuration, not of one database.

**The cause is not established, and the obvious explanation is contradicted.**
The live config is `ODDS_REGIONS=us,eu` (container env, and `regions='us,eu'` on
every row of `api_credits`), so "the `uk` region is not requested" is the
natural story -- but `williamhill`, `marathonbet` and `matchbook`, all commonly
documented as UK-region keys, **do** appear under that same request. Region
gating therefore does not cleanly predict what is observed.

Two explanations remain and this data cannot separate them: (a) the key is
region-gated behind `uk`; (b) the key is not returned for these sports at all.
**The observation that separates them:** one `/v4/sports/{sport}/odds` call with
`regions=uk` -- 3 credits for one sport at one market, 9 at three. Not spent.

This is **not** the ADR 0019 shape. The set is live and read; `runner.py:103` is
the only definition and `runner.py:658` is the only consumer. It is a live set
with a dead member.

**What follows for `SHARP_BOOKS`, and what does not.** What follows is that the
constant must stop advertising four. Either drop `betfair_ex_uk` with a comment
recording this measurement, or add a startup check that every member is
reachable under the configured regions and fails loudly when one is not -- the
second is preferable, because it is the version that fires again next time.
What does **not** follow is "add the `uk` region". That costs 50% more per
sweep (`cost = markets x regions`), and `betfair_ex_uk` is the same exchange
book as `betfair_ex_eu`; adding it would widen the count without widening the
information, which is precisely the failure ADR 0019 is about.

## 5. The wide-consensus rows are real -- the finding survives

The attack was: an instant is not a row, and a zero-sharp instant might be
dropped before it ever became one. It was not.

| | rows (of 1,564) | share | links | clean rows | CLV-scored |
|---|---|---|---|---|---|
| `anchored_on_sharp = 1` | 1,141 | 73.0% | 54 | 425 | 830 |
| `anchored_on_sharp = 0` | **423** | **27.0%** | 34 | **189** | 271 |

Zero rows failed to join to a `fair_prices` row, so the split is exhaustive.

**Correction to the headline number.** The census's **23.1%** is the
instant-weighted figure over all 234 stored instants, including 62 the runner
never read. The record's figure is **27.0% of rows** (423/1,564), **28.5% of
consumed instants** (49/172), and **30.8% of clean rows** (189/614). 23.1% is
not the number to quote about the record.

**Two independent confirmations that the census and the record are the same
mechanism, at row level:**

1. The 2x2 of (census says the instant had no sharp book) against (the row
   stores `anchored_on_sharp = 0`) is **423 / 1,141 with zero off-diagonal**.
2. `fair_prices.books_used` was recomputed from the raw snapshots for every
   h2h row and matched **21,550 of 21,550**. This also proves the devig step
   rejected no book: the reconstruction assumed `usable` = "quoted every
   outcome", and any devig rejection would have broken a match.

**And they returned nothing.** Among the 189 clean wide-consensus rows: **0**
had a positive edge (range -51.73 to -2.05 tenths, mean -28.43). Across all 423:
6 positive, all suppressed, max +15.06 tenths. `suggested_contracts = 0` and
`reference_contracts = 0` on **all 423**. The same is true of the sharp-anchored
side (0 of 425 clean rows positive; 0 actionable of 1,141).

**Read `n` before believing this.** 423 rows are not 423 independent
observations. They come from **34 links**, **49** consumed `(event, fetch)`
instants, **21** runner cycles and **13** distinct odds-observation stamps
(12 among the clean 189). The conservative unit is **34 fixtures**. The
per-link view does not show one fixture carrying it: largest link is 7.8% of
the 423 and 6.3% of the 189; top three are 20.1% and 17.5%.

**Where this is smaller than it reads, and it is the important part.** The
fallback set is **not** the wide reference class option B proposes.

- Option B would widen the reference class *deliberately, on every row*. These
  423 took the fallback because the sharps were **missing at that moment** -- a
  selected, non-random subset.
- It is selected toward **thin** instants, not wide ones. Zero-sharp instants
  carry a median of **12** books against 23 across all instants and 29 on the
  typical anchored instant; their maximum is 19 where the overall maximum is 31.
  Row-weighted, `book_count` on the 423 has a median of **12**.
- It is skewed by league: 385 of 423 are Pro Baseball, 38 Pro Basketball (W),
  against a 1,142/422 split overall.
- 190 of the 423 were already suppressed `stale_odds`, and 34 had a single book
  and were suppressed `too_few_books`.

So the supported sentence is *"a wide-consensus comparison was run on the subset
of instants where the sharps had not yet quoted"*, and **not** *"the project has
partly run option B"*. The second is the over-read, and the median of 12 books
is what refutes it.

## 6. Scope -- the same population, proven at row level

This is the defect being corrected, so it is not argued from window overlap.

| | start | end |
|---|---|---|
| Census, `fetched_ms` (h2h) | 2026-08-07 19:33:27 | 2026-08-09 23:37:15 |
| Census, `book_updated_ms` (h2h) | **2026-08-07 19:28:12** | 2026-08-09 23:37:21 |
| Record, `created_ms - odds_age_ms` | **2026-08-07 19:28:12** | 2026-08-09 23:35:18 |

The apparent 5m15s offset in the first row is entirely the difference between
when a book updated and when we fetched. The census's minimum `book_updated_ms`
equals the record's earliest odds observation **to the second**, and
`book_updated_ms` is non-NULL on all 10,284 h2h rows.

The identity is exact, not an overlap argument: `created_ms - odds_age_ms` was
reconstructed from the raw snapshots -- the oldest `book_updated_ms` among books
quoting every outcome at the instant the row read -- and matched **1,564 of
1,564** pinned rows with zero mismatches. Contrast the fixture, which overlapped
**0 of 1,564**.

**Two scope facts that must travel with this.** The record read **172** of the
234 stored instants; 62 were never read. And `fair_prices` runs to 2026-08-10
15:42 while odds fetching stopped 2026-08-09 23:37 -- after that the runner kept
re-reading one stored instant, which is what the `stale_odds` suppressions are
catching. The 1,564 rows rest on 172 instants (9.1 rows per instant on average),
205 runner cycles and 33 distinct odds-observation stamps. **Row count here
measures polling uptime as much as it measures evidence.**

## 7. The degenerate one-book consensus is already caught

Six instants had fewer than two usable books (four of them a single book). 245
pinned rows carry `book_count < 2`, and **all 245** were suppressed
`too_few_books`. 211 of those are `anchored_on_sharp = 1` rows where a single
sharp book was the entire consensus -- the anchoring, not the market, made them
degenerate. No new exposure; these are the rows ADR 0019 and the
degenerate-fair work already caught.

## 8. h2h only

`odds_snapshots` holds 7,392 spread rows and 7,508 total rows over the same
window and the same 68 events. `fair_prices` holds **21,526 rows and every one
is `market = 'h2h'`**. The engine has never written a fair price or a
recommendation about a spread or a total. Everything above is a moneyline
finding and does not extend past it.

## 9. Test count

Roughly thirty descriptive cuts across four passes. **Zero significance tests,
zero confidence intervals, zero thresholds.** No cut here can produce a false
finding by clearing a bar, because no cut is compared to a bar: every figure is
a complete enumeration of a fixed, pinned population. The one comparative
statement -- "0 of 189 clean wide-consensus rows had a positive edge" -- is an
exhaustive count, not an estimate. The multiplicity risk in this document is
zero; the over-reading risk is entirely in section 5's selection caveat.

## 10. Negative controls -- these queries were watched going red

A query nobody has seen fail is decoration. Q6/Q7 were re-run with one thing
deliberately broken at a time, against the same live database:

| Control | Result | Reads |
|---|---|---|
| A. Sharp list as shipped | `max_sharp 3`, `mean_discarded 18.98` | baseline |
| B. `betfair_ex_uk` **removed** from the list | **byte-identical to A** | the member is provably inert |
| C. `draftkings` **added** to the list | `max_sharp 4`, `mean_discarded 18.00` | the list is load-bearing |
| D. Q7 joined on the wrong key (`f.id = r.link_id`) | 981 / 583 | the join is load-bearing |
| E. Q7 with the `id <= 1564` pin removed | 452 / 1,226, "107.3%" | the pin is load-bearing |

**Control B is the anchor that matters, and it is why Q9 exists.** The census
query alone *cannot* distinguish a `SHARP_BOOKS` containing `betfair_ex_uk` from
one without it -- both give exactly the same answer on this data, which is the
same shape of definitional blind spot as testing a convention at the one value
where both conventions agree. Only a query that names the book directly
(Q9: 0 rows, all markets, whole window) can tell "absent" from "not asked for".

Control E also shows the record still growing during the audit: the unpinned
counts sum to 1,678 where an earlier pass in the same session saw 1,676. Every
figure in this document is pinned for that reason.

---

## What this measurement does not establish

- **Not that the sharp books are right.** It counts what was dropped and how
  often the filter bound. Nothing here compares any book's price to an outcome.
- **Not why `betfair_ex_uk` is absent.** Only that it is. The region hypothesis
  is contradicted by `williamhill` / `marathonbet` / `matchbook` appearing under
  the same request. One `regions=uk` call would settle it; it was not made.
- **Not that a wide-consensus strategy has been tested.** The 423 rows are the
  instants where the sharps had *not* quoted: thinner (median 12 books), 91%
  MLB, 45% already `stale_odds`. A test of option B requires re-scoring the
  record with anchoring off *on every row*, which is a different measurement.
- **Not that the zero edge on the 423 generalises.** They rest on 34 fixtures
  over 49 instants inside one 52-hour window, two leagues, one season.
- **Not anything about spreads or totals.** Section 8.
- **Not anything about rows created after 2026-08-09 23:37**, when odds fetching
  stopped and the runner began re-reading one stored instant.
- **Not a fresh sample.** This is the same 1,564 rows read a third way. It is a
  new *fact* about that population, not a replication of it. Calling it
  corroboration of the shortfall result would repeat the error ADR 0021
  section 4 corrects.
- **No causal claim about why the sharps were missing.** "Fetched before they
  posted" fits, but so does "they pulled their lines". Both predict every
  observation here. What separates them: `book_updated_ms` for the sharps on the
  neighbouring instants of the same event -- not run.
- **Not a verification of the guards it reports.** The `too_few_books` and
  `stale_odds` counts are read from stored rows; this run did not disable either
  guard and watch it go red.

## What section 7.2 may now be annotated to say

Not edited here. Routed separately. The supported wording:

1. The magnitude is **observed on the record**: a median of **19 usable books
   discarded of 21**, per row, over the pinned 1,564. `26 of 29` stays as the
   fixture figure it is; the like-for-like per-event record figure is
   **20.5 of 23**.
2. The mechanism paragraph is **unchanged**, but its scope is now measured:
   "we have been testing Kalshi against the only references plausibly as sharp
   as Kalshi" holds on **1,141 of 1,564 rows (73.0%)**, and the fraction that
   was previously "unobserved" is **27.0%**.
3. `anchored_on_sharp` **is** on the record and always was -- it is on
   `fair_prices`, not `recommendations`, which is why the ledger pull could not
   see it. The annotation's *"and that column is not on this record either"* is
   **wrong** and should be corrected to *"not exposed by `/api/ledger` until
   `4938701`"*.
4. The tautology objection is **narrowed, not withdrawn**. It covers 73.0% of
   the record. The remaining 27.0% was compared against a non-sharp consensus
   and also returned nothing -- but of a median of 12 books, not the full
   market, so this is **not** a partial run of option B and must not be written
   up as one.
5. Option **B** in section 8 keeps its rationale and loses its prize figure. The
   expected widening is from 2-3 books to about 21, not to 29.
6. Every statement of the form "anchored on the sharps" means **at most three
   books**, never four: `betfair_ex_uk` is on the record 0 times.
