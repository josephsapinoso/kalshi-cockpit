# E2: is a combination's list quote backed by an order book?

Date: 2026-08-09
Status: **complete.** Everything above `RESULTS` was committed to git (`554b719`)
before a single order book was read; nothing in it was edited afterwards.

**Headline, with its `n` first:** 4 of 20 quoted combinations had an empty
order book — 20.0%, 95% CI [8.1%, 41.6%]. **All four were rows whose list ask
had vanished 3.4 seconds later**; of the 14 still quoted at both ends of the
pass, 0 had an empty book (CI [0.0%, 21.5%]). Separately, and arguably worse:
the list ask and the book-derived ask disagreed on **5 of 16** rows, three of
them by 1.2–3.6c *against* the buyer.

## The pre-registered question

E2 was fixed at the end of `2026-08-09-combo-leg-echo.md`, before this session
existed, and is run here as written:

> **E2.** For each combination carrying a `yes_ask` on `/markets`, read
> `/markets/{ticker}/orderbook` in the same pass. Record (a) whether the book is
> non-empty, (b) whether `1 − best_no_bid` reproduces the list `yes_ask`, and
> (c) whether any level derives to within 2c of a leg's cost. Report the rate of
> each with its `n`, split by scope, and report the **book-empty rate first** —
> if a material share of quoted rows have no book, the harvest's population is
> not what it was taken to be, and that supersedes every other question here.

### Why it matters

An exploratory look at 8 live echo combinations found **3 with an empty book
while `/markets` quoted them**, and one reading `0.0000 / 1.0000` on
`/markets/{ticker}` for 18 consecutive polls against a list quote of 0.463.
Every combo price this project holds — **all 2,116 rows of the harvest** — came
from the list endpoint. Whether any of them was backed by resting size at the
moment it was read has never been checked.

That exploratory 3-of-8 is `n = 8`. It is not a rate; it is the reason to
measure one.

## Operational choices, fixed now

E2's paragraph fixes the three quantities and the reporting order. It does not
fix the thresholds, the sample size or the selection rule, so those are written
here, before collection, and are not re-tuned afterwards.

Harness: `scripts/measure_combo_book_presence.py`. Free, **unauthenticated**
(both `/markets` and `/markets/{ticker}/orderbook` return 200 with no
signature), read-only. No order, no cancel, no lookup, **zero Odds API
credits**, no credential in the process.

### Definitions

| Term | Fixed as |
|---|---|
| eligible combination | a `/markets` row with non-empty `mve_selected_legs` and a readable `yes_ask` by `measure_combo_correlation.readable_quote` (`0 < ask < 1`). A `0.0000` ask is not an ask. |
| **book empty** | zero levels on `yes_dollars` **and** zero on `no_dollars` |
| NO-side empty | zero levels on `no_dollars` — reported separately, because `yes_ask` derives from the NO bid alone |
| **reproduces** | `\|(1 − best_no_bid) − list_ask\| ≤ 0.0005` — equality on the deci-cent grid. The raw difference is recorded for every row regardless. |
| derived yes price of a level | `1 − p` for a NO level at `p`; `p` itself for a YES level |
| **echo in book** | some level's derived yes price is within `ECHO_TOLERANCE` = 0.02 of some leg's `cost_to_buy_leg` |
| `cost_to_buy_leg` | **imported** from `measure_combo_correlation`, not re-implemented: `yes → yes_ask`, `no → 1 − yes_bid` |

`ECHO_TOLERANCE` is 0.02, the same constant `analyse_combo_domination` and the
leg-echo harness use, unchanged.

### Sampling

| | |
|---|---|
| Discovery | one `GET /markets?series_ticker=…&status=open&limit=1000` per series in `DISCOVERY_SERIES`, newest-first, **no paging** |
| Selection | the **first 20 eligible rows in discovery order** — fixed, not sampled at random, and not re-chosen after seeing a book |
| Leg prices | one batched `?tickers=…` read of every leg of those rows |
| Books | one `/markets/{ticker}/orderbook?depth=10` per selected row |
| Contemporaneity control | one batched re-read of the same combinations' list quotes, **after** the whole book pass |
| Budget | **2 + 1 + 20 + 1 = 24 Kalshi calls**, zero Odds API credits |

### Denominators, fixed now

Getting these wrong is how a rate flatters itself, so each is written before the
data exists:

- (a) is over **every scored row**.
- (b) is over rows **with a NO bid at all**. A row with no NO side has nothing
  to reproduce the ask with; counting it as a reproduction failure would
  double-count the book-empty rate inside (b).
- (c) is over rows with a **non-empty book and every leg priceable**. An
  unpriceable leg is excluded and counted, never scored as "no echo".

### Uncertainty

Every rate is reported as `k/n` with a **95% Wilson score interval**. At `n =
20` the normal approximation is not licensed by CLAUDE.md's "≥5 expected
outcomes on each side" rule, and the interval — not the point estimate — is the
result. Scope cells will be smaller still and are printed with their counts.

### Envelope guard, and why it is not a second copy

`ORDERBOOK_KEY` (`orderbook_fp`) and `MalformedOrderbookResponse` are
**imported** from `backend.kalshi.rest`. A missing envelope **raises and aborts
the row**; aborted rows are reported separately and are never counted as empty.

This is the whole hazard of this measurement. `KalshiRestClient.orderbook` once
read `payload["orderbook"]` and returned `{}` for every market on the exchange
without erroring — a book-empty rate of 100% that was really a key typo. **An
empty book is a legitimate state on this venue; a renamed field is not.**

### What this measurement will not establish

Fixed in advance so it cannot be quietly narrowed later.

- **Nothing about the 2,116 stored rows themselves.** Those markets are gone.
  This measures the population they were drawn from, on a later slate, and
  transfers only to the extent that population is stable.
- **Nothing about why a book is empty.** Replica lag between two endpoints, a
  quoter posting and pulling inside the gap, and a list price never backed by
  resting size all predict the same observation.
- **Nothing about tradeability.** These rows are provisional, with zero volume
  and zero open interest. A resting level is not a fill.
- **Nothing about non-eligible combinations.** Rows with no readable ask are
  excluded by construction.
- **Newest-first, so youngest.** Only the newest combinations carry a quote at
  all. If book presence grows with age, this rate is a lower bound and nothing
  here separates the two.
- **One slate, one window of seconds.** Not an edge: no fair value is computed
  and no combo fee model is verified.

---

## RESULTS

Status: **complete.** One pass, 20 combinations, **24 Kalshi calls**, zero Odds
API credits, zero orders, zero rows aborted on a malformed envelope. Raw data:
`2026-08-09-combo-e2-book-empty.json`; the 20 captured order books are pinned
as a wire fixture at `tests/fixtures/combo_orderbooks.json`.

The whole pass spanned **3.4 seconds** from the list read to the last book
read. Combinations were 15.1–36.9 s old when read.

### (a) The book-empty rate — reported first, as pre-registered

| | k/n | rate | 95% Wilson |
|---|---|---|---|
| **book empty** (no level on either side) | **4/20** | **20.0%** | **[8.1%, 41.6%]** |
| NO side empty (`yes_ask` cannot derive) | 4/20 | 20.0% | [8.1%, 41.6%] |

Those two lines are identical because **no book in this sample carried a single
YES level.** Every non-empty book was one resting NO bid — 15 of 16 had exactly
one level, one had two. "Non-empty" here means one bid, not a book.

Read `n` first: 4 of 20. The interval runs from 8% to 42%, so this sample is
consistent with anything from "one row in twelve" to "two rows in five".

#### The contemporaneity control changes how (a) should be read

The same 20 list rows, re-read after the whole book pass:

| | k/n | rate | 95% Wilson |
|---|---|---|---|
| still carrying an ask 3.4 s later | 14/20 | 70.0% | [48.1%, 85.5%] |
| …of those, book empty | **0/14** | **0.0%** | **[0.0%, 21.5%]** |
| of the 6 whose ask had gone, book empty | 4/6 | 66.7% | [30.0%, 90.3%] |

**All four empty books belonged to rows whose list ask had disappeared 3.4
seconds later.** Every row still quoted at both ends of the pass had a book.

One test was run on this (Fisher exact, two-sided, on the pre-registered
control): **p = 0.0031**. That is one test, on a 2×2 whose smallest cell is
zero, and the association may be close to definitional — if a book emptying and
a quote ending are the same event seen through two endpoints, the table has to
look like this. It is reported because the control was fixed in advance, not
because p < 0.05 means much at these counts.

**0/14 is not "backed quotes are always backed."** Its interval reaches 21.5%.
Fourteen rows cannot exclude a one-in-five rate.

### (b) Does `1 − best_no_bid` reproduce the list ask?

Denominator: the 16 rows with a NO bid at all. A row with no NO side has
nothing to reproduce the ask with; counting it as a failure would re-report (a)
inside (b).

| | k/n | rate | 95% Wilson |
|---|---|---|---|
| reproduces exactly (≤ 0.0005) | 11/16 | 68.8% | [44.4%, 85.8%] |
| within 2c | 13/16 | 81.2% | [57.0%, 93.4%] |
| **book-derived ask WORSE than the list ask** | **3/16** | **18.8%** | **[6.6%, 43.0%]** |

Every difference, in full — eleven exact, then:

    -0.0490   list 0.5490   book best NO bid 0.5000 -> derived 0.5000
    -0.0010   list 0.4830   book best NO bid 0.5180 -> derived 0.4820
    +0.0120   list 0.4240   book best NO bid 0.5640 -> derived 0.4360
    +0.0240   list 0.1730   book best NO bid 0.8030 -> derived 0.1970
    +0.0360   list 0.3660   book best NO bid 0.5980 -> derived 0.4020

The sign is the part that costs money. On three rows the price you could
actually pay was **1.2c, 2.4c and 3.6c worse** than the list quoted. The
project's entire fee headroom is 0.38 points.

The `-0.0490` row is worth naming: its book had two NO levels, 0.4530 and
0.5000. The **top** level derives to 0.5000, but the **deeper** one derives to
0.5470 — 0.2c from the list's 0.5490. The list ask reproduced a level that was
not the top of book. That is the same shape the leg-echo document's exploratory
section flagged, and it is `n = 1`.

**This cannot be separated from a genuine 3.4-second price move.** Nothing here
distinguishes "the list row was stale" from "the book moved between the two
reads", and a 3.6c move in 3.4 seconds on a provisional combination is not
implausible.

### (c) Does any level derive to within 2c of a leg's cost?

Denominator: the 10 rows with a non-empty book **and** every leg priceable.
Six rows were excluded for an unpriceable leg — all six carried 10 to 15 legs,
so the exclusion is not random with respect to leg count.

| | k/n | rate | 95% Wilson |
|---|---|---|---|
| a level echoes a leg (≤ 0.02) | 1/10 | 10.0% | [1.8%, 40.4%] |

**This is not comparable to the exploratory "5 of 5" it was written to follow
up.** Those 8 books were read on combinations *selected because their list ask
already echoed a leg*. These 20 were not selected on anything. (c) here is a
base rate over unselected rows; the exploratory number was conditional on the
echo. Putting them in the same sentence would be the error this project has
already withdrawn two combo claims for.

### Split by scope — every cell is small and none is claimed

| scope | n | empty | NO-side empty | reproduces | echoes |
|---|---|---|---|---|---|
| cross_game | 11 | 2/11 | 2/11 | 6/9 | 1/3 |
| same_game | 4 | 0/4 | 0/4 | 3/4 | 0/4 |
| mixed | 5 | 2/5 | 2/5 | 2/3 | 0/3 |
| undecodable | 0 | — | — | — | — |

Largest contributor: `cross_game`, 11/20 = 55% of the pooled rate. The parts do
not visibly disagree, but four rows cannot agree or disagree with anything.
**No scope-level claim is made here.**

### Structure of the sample, for whoever reads this next

- **19 of 20 non-empty books were a single resting bid.** There is no depth.
- **6 of 20 rows were quoted at 0.0020** — 10-to-15-leg parlays, each with an
  identical NO bid of `0.9980 × 300`. Almost certainly one automated quoter.
- **3 of 20 rows had non-zero volume and open interest** (202, 213 and 509
  contracts), so this population is not entirely untraded junk — and **one of
  those three had an empty book** while the list quoted it at 0.1470.
- Ages 15–37 s. Only the newest combinations are quoted at all, so the sample
  is young by necessity, not by choice.

---

## What this changes about the 2,116 stored combo prices

Plainly: **it does not invalidate them, and it does not clear them.**

What is now on the record, with its `n`:

1. **A row can carry a list ask with nothing resting behind it.** 4 of 20
   (8%–42%). That was previously an 8-row anecdote; it is now a measured rate
   with a wide interval.
2. **In this sample, that happened only to rows that were about to stop being
   quoted.** 0 of 14 still-quoted rows had an empty book. The economical
   reading is that the list endpoint's ask lags the book by seconds at
   end-of-life, so a list-only harvest collects some rows whose price was
   already gone. Fourteen rows cannot make that a rule.
3. **The list ask and the book-derived ask disagree often enough to matter.**
   5 of 16, three of them 1.2–3.6c in the direction that costs money.

What follows, concretely:

- **Any money decision on a combination must price off the order book, not the
  `/markets` row.** Finding (3) is a 1–4c effect against a 0.38-point headroom.
  This is the actionable one, and it is cheap: one call per candidate.
- **Any future combo harvest should read the book in the same pass, or at
  minimum re-read the list a few seconds later and drop rows whose ask has
  gone.** The re-read costs one batched call per pass and would have caught all
  four empty-book rows here.
- **The 2,116 stored rows keep a second caveat.** They already cannot support
  the two withdrawn claims in ADR 0012's addendum. Now they also carry an
  unmeasured fraction — this sample says somewhere in 8%–42% — of asks that had
  no resting size behind them. Nothing here recovers which rows those were, and
  those markets are gone.
- **Nothing here reinstates anything.** The 94%, the 22.4% and both combo
  claims stay withdrawn.

---

## What this does NOT establish

In addition to the six limits fixed before collection, all of which still
apply:

- **Not that the list endpoint is stale rather than the book flickering.** The
  causal direction between "the book empties" and "the quote ends" is not
  observable in a single re-read, and a quoter posting and pulling produces the
  same table.
- **Not that a backed quote stays backed.** 0/14 has an interval reaching
  21.5%. It is not zero.
- **Not that the (b) disagreements are pricing errors.** A 3.4-second gap
  separates the two reads and a real move inside it is not excluded.
- **Nothing at a finer time resolution than one re-read.** No time series was
  taken; a book that emptied and refilled inside the pass would be invisible.
- **Nothing about the echo hypothesis.** (c)'s 1/10 is a base rate on
  unselected rows and says nothing about combinations selected for echoing.
- **Nothing about the 2,116 rows individually.** This measures the population
  they came from, later, and transfers only if that population is stable.
- **Not a null result anywhere it reads like one.** Every zero above is a small
  count with an interval attached.
- **Not an edge.** No fair value, no combo fee model.

### One arithmetic artifact, declared

`0.62 − 0.64` is `−0.020000000000000018` in binary floating point, so a level
exactly two cents from a leg fails `≤ 0.02`. The threshold was pre-registered
at 0.02 and is **not** retuned here — adding an epsilon after seeing the data
is precisely the move this document exists to avoid. It cannot have moved the
reported rate: no scored row came within 0.001 of the boundary, and
`tests/test_combo_book_presence.py` asserts that against the run's own JSON.
`analyse_combo_domination` and `measure_combo_leg_echo` carry the same knife
edge, so this is the project's existing behaviour, not a defect introduced here.

---

## Objections to the pre-registration, recorded separately

E2 was run exactly as written. These are the places where, having run it, the
specification looks under-determined. They are recorded here rather than folded
into the protocol, because amending a pre-registration after seeing its data is
how one stops meaning anything.

1. **E2 fixes a scope split without fixing a sample size.** Splitting 20 rows
   four ways yields cells of 0 to 11 and twelve numbers nobody can read. The
   table is printed as required and nothing in it is claimed. A split is only
   informative once the pooled `n` can survive being quartered.
2. **E2's (b) does not name a denominator.** If empty-book rows count as
   reproduction failures, (b) silently re-reports (a) and both look worse
   together. The denominator used here — rows with a NO bid — was fixed before
   collection and declared, but that was this session's choice, not E2's.
3. **"In the same pass" is not simultaneity.** A REST pass takes seconds, and a
   combination's quote lives tens of seconds; E2 does not name that confound.
   The contemporaneity control was added to bound it, and it turned out to be
   the difference between reporting "20% of quoted rows have no book" and
   reporting what actually happened. Without it this run would have produced
   the tidier, worse-supported number.
