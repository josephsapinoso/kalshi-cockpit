# E2: is a combination's list quote backed by an order book?

Date: 2026-08-09
Status: **complete, then revised.** Everything above `RESULTS` was committed to
git (`554b719`) before a single order book was read and **is still not edited** —
the corrections below are made underneath it, not inside it. The recorded
numbers are unchanged and the harness was not re-run to get a nicer sample;
what changed is the prose about them. See *Corrections after audit* at the end
for what was wrong and why.

**Headline, with its `n` first:** **4 of 20** quoted combinations had an empty
order book — 20.0%, 95% CI [8.1%, 41.6%]. A list ask with no resting size
behind it is a real state of this venue, at `n = 4`.

Two things that headline is not:

- **It is not a rate for the 2,116 stored combo rows.** This sample is 20/20
  `KXMVESPORTSMULTIGAMEEXTENDED` and 17/20 above three legs; that population is
  66% `KXMVECROSSCATEGORY` and 100% two- and three-leg. The structurally
  comparable subsample is `n = 3`. See *What this changes about the 2,116*.
- **It is not 0/14.** The contemporaneity control is reported below and it
  matters, but it is conditional on a second read that a list-only harvest
  never makes, and one direction of it is forced by how a derived ask is
  defined.

Separately: the list ask and the book-derived ask disagreed on **5 of 16** rows,
by −4.9c to +3.6c. The direction is 3 against the buyer and 2 in the buyer's
favour, with the largest single row in the buyer's favour, so **no directional
cost is claimed**. The consequence is direction-free: a combination's `/markets`
row is not a price you can transact at.

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

### What this sample is made of — read before any rate

The pre-registration fixed denominators and thresholds. It did not check that
the sample would span the population it was meant to inform, and it did not.

| | this sample (n = 20) | the 2,116-row harvest |
|---|---|---|
| `KXMVESPORTSMULTIGAMEEXTENDED` | **20** | 721 (34%) |
| `KXMVECROSSCATEGORY` | **0** | **1,395 (66%)** |
| 2-leg | 1 | 911 |
| 3-leg | 2 | 1,205 |
| 4+ legs | **17** | **0** |
| scope: cross / same / mixed / undecodable | 11 / 4 / 5 / 0 | 1,612 / 344 / 135 / 25 |

Neither gap is chance. `DISCOVERY_SERIES` is an ordered **tuple**, the pages are
concatenated in tuple order, and the pre-registered rule was "the first 20
eligible rows in discovery order" — so the sample fills from the first series
and can never reach the second. And the harvest's own eligibility rule refuses
anything over three legs (`too_many_legs_for_equicorrelation`, 10,228 rows
refused by `measure_combo_correlation`), so **17 of these 20 rows have a leg
count that occurs zero times in the target population.**

Both facts were checkable, at zero cost, from files already committed to this
repo. Neither was checked. The harness is fixed for future runs
(`round_robin`, `--max-legs`); the numbers below are **not** re-run.

### Exposure, per row rather than as one scalar

The pass spanned 3.4 seconds end to end, but no row was exposed for 3.4
seconds. Each row's own list-to-book gap runs **0.24 s (row 1) to 3.36 s (row
20)**, and the single scalar overstates the early rows and understates the late
ones. Combinations were 15.1–36.9 s old when read.

The four empty books fall at read positions **5, 12, 15 and 19** — none in the
four shortest-gap rows. That is `n = 4` and nothing is claimed from it, for a
reason worth stating plainly: **discovery is newest-first and the books are
read in that same order, so read position, age and exposure are perfectly
collinear in this design.** No run shaped like this one can attribute an empty
book to age rather than to exposure. A future run would have to randomise the
book-read order.

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

#### The contemporaneity control, and why it does not replace the headline

The same 20 list rows, re-read after the whole book pass:

| | k/n | rate | 95% Wilson |
|---|---|---|---|
| still carrying an ask at the re-read | 14/20 | 70.0% | [48.1%, 85.5%] |
| …of those, book empty | 0/14 | 0.0% | [0.0%, 21.5%] |
| of the 6 whose ask had gone, book empty | 4/6 | 66.7% | [30.0%, 90.3%] |

All four empty books belonged to rows whose list ask had disappeared by the
re-read. This is reported because the control was pre-registered, and it is
**not** promoted above 4/20, for three reasons.

**It is conditional on a read the harvest never makes.** The 2,116 rows came
from a list-only pass. There was no re-read, so there is no way to condition on
"still quoted afterwards" for any of them. 4/20 is the number that describes
what a list-only harvest collects; 0/14 describes what a *different* protocol
would collect.

**One direction of the association is mechanism-forced.** `yes_ask` on this
venue is `1000 − best_no_bid` (`SKILL.md`). If a row's list ask is book-derived
and its book stays empty, the re-read's `readable_quote` **must** return `None`,
because there is no NO bid to derive an ask from — and `readable_quote` refuses
rather than substituting 0. So the cell "book empty **and** still quoted", the
cell that carries the whole p-value, is the cell the definitions forbid from
being populated.

**But it is not a tautology, and the converse is falsified in-sample.** If the
table could not fire on any input it would be worthless; it can. Two rows —
`…7595CFE5F2` and `…B69FB10A5D4` — lost their list ask while **holding a
resting NO bid**, 2 of the 6 rows whose ask went away. So "quote ends" does not
imply "book empties". This is not the `kept 2116 of 2116, dropped 0` shape.

The Fisher exact test previously reported here (two-sided, **p = 0.0031**) is
**demoted to a footnote**. `git show --stat 554b719` shows the pre-registration
fixed Wilson intervals and named **no hypothesis test**; `grep -rn fisher` finds
the word only in this document's prose, and no committed code computes it. A
test chosen after seeing a 4/4-versus-0/14 table is a forking path, not "one
test" — and given the mechanism above, its null was never a live hypothesis.
The p-value is arithmetically right and informationally empty.

**0/14 is also not "backed quotes are always backed."** Its interval reaches
21.5%. Fourteen rows cannot exclude a one-in-five rate.

### (b) Does `1 − best_no_bid` reproduce the list ask?

Denominator: the 16 rows with a NO bid at all. A row with no NO side has
nothing to reproduce the ask with; counting it as a failure would re-report (a)
inside (b).

| | k/n | rate | 95% Wilson |
|---|---|---|---|
| reproduces exactly (≤ 0.0005) | 11/16 | 68.8% | [44.4%, 85.8%] |
| within 2c | 13/16 | 81.2% | [57.0%, 93.4%] |

#### The pooled 68.8% is a blend, not a rate

Six of those 16 rows are one automated quoter. Their books are **byte
identical** — a single NO bid of `0.9980 × 300` — on 10-to-15-leg parlays all
quoted at a list ask of 0.0020, all `cross_game`. Grouping on the book's exact
resting shape is defined on the bytes, not on any outcome, so it is not a
forking path. CLAUDE.md requires the per-group view:

| group | reproduces | 95% Wilson |
|---|---|---|
| the `0.9980 × 300` cluster | **6/6** | [61.0%, 100%] |
| everything else | **5/10** | [23.7%, 76.3%] |

**The 68.8% is a blend of 100% and a coin flip.** Outside the degenerate
cluster, whether the list ask matches the book is indistinguishable from chance
at this `n`.

The pre-registered scope table actively hides this. All six cluster rows are
`cross_game`, so that cell reads 6/9 — and **every one of those six successes
is the same quoter.** `cross_game` excluding the cluster is **0/3**: not one
non-cluster `cross_game` row reproduced.

#### Every difference, in full

Eleven exact, then:

    -0.0490   list 0.5490   book best NO bid 0.5000 -> derived 0.5000
    -0.0010   list 0.4830   book best NO bid 0.5180 -> derived 0.4820
    +0.0120   list 0.4240   book best NO bid 0.5640 -> derived 0.4360
    +0.0240   list 0.1730   book best NO bid 0.8030 -> derived 0.1970
    +0.0360   list 0.3660   book best NO bid 0.5980 -> derived 0.4020

**No direction is established.** Three disagreements are against the buyer and
two are in the buyer's favour, and the **largest single row in the sample,
−4.9c, is in the buyer's favour**. Three-versus-two on `n = 5` cannot support a
directional cost, and an earlier version of this document paired "the sign is
the part that costs money" with the project's 0.38-point fee headroom — which
frames a systematic cost the data does not contain. That framing is withdrawn.

The operational consequence survives without it, and is direction-free:
**a combination's `/markets` row is not a price you can transact at. A money
decision must read the book.** A 1–4c gap in either direction is decisive
against a 0.38-point headroom; you do not need it to be biased.

#### Which explanation each disagreement is consistent with

The earlier version said flatly that this "cannot be separated from a genuine
3.4-second price move." **Its own `confirm_ask` column separates it, row by
row, and was not used.** The re-read is a second observation of the list ask
after the book was read, so if the list was lagging and caught up, the re-read
lands on the book's derived value; if the list held its own value across the
book read, a transient move does not explain the gap.

| row | list | book derives | re-read | consistent with |
|---|---|---|---|---|
| `…7C5B267D08B` | 0.3660 | 0.4020 | **0.3670** | **not a move** — the list held its value across the book read while the book sat 3.5c away |
| `…B4B102D8DC8` | 0.1730 | 0.1970 | **0.1970** | a move/lag — the list caught up to the book exactly |
| `…D030A4B3418` | 0.4830 | 0.4820 | **0.4820** | a move/lag — same |
| `…0646AEECAFB` | 0.5490 | 0.5000 (best) / 0.5470 (deeper) | **0.5470** | **not the top of book** — the re-read matches the *deeper* level to the digit |
| `…B69FB10A5D4` | 0.4240 | 0.4360 | ask gone | **not adjudicable** |

So of the five: **two are consistent with the move/lag story, two are not, and
one cannot be resolved.** "Cannot be separated" was too strong.

`…0646AEECAFB` deserves its own line. Its book had two NO levels, 0.4530 and
0.5000. The **top** derives to 0.5000; the **deeper** derives to 0.5470. The
list read 0.5490 and the re-read read **0.5470 — the deeper level, exactly.**
The earlier version noticed the deeper level was "0.2c from the list's 0.5490"
and missed that the re-read matches it to the digit. At no point in the window
does the list equal the top-of-book derivation. This is `n = 1` and is a
pointer, not a finding: it says the list ask may not be a top-of-book
derivation at all, which is exactly what the follow-up check below tests.

### (c) Does any level derive to within 2c of a leg's cost?

Denominator: the 10 rows with a non-empty book **and** every leg priceable.
Six rows were excluded for an unpriceable leg — all six carried 10 to 15 legs,
so the exclusion is not random with respect to leg count.

| | k/n | rate | 95% Wilson |
|---|---|---|---|
| a level echoes a leg (≤ 0.02) | 1/10 | 10.0% | [1.8%, 40.4%] |

#### The direction of the exclusion, stated

The six excluded rows are **exactly** the six rows of the `0.9980 × 300`
cluster from (b) — the same automated quoter, identified twice by two unrelated
criteria. Their sole book level derives to 0.002.

Had they been scored on their partial leg sets, **five of the six would have
counted as echoes**, because each carries a leg priced at 0.010 and
`|0.002 − 0.010| = 0.008 ≤ 0.02`. The counterfactual is **6/16 = 37.5%** against
the reported **1/10 = 10.0%**, so the pre-registered exclusion moved the number
**down**, by a wide margin.

The rule is still the right one, but for a reason worth writing down, because
it is a defect in `ECHO_TOLERANCE` rather than a property of these rows.
**`ECHO_TOLERANCE` is an absolute 2c band, so near a price of zero everything
is within 2c of everything.** A 15-leg parlay quoted at 0.002 and a leg quoted
at 0.010 are not "the same price" by any economic reading; they are both simply
at the bottom of the grid. The five echoes the exclusion removed were
arithmetic, not evidence. `analyse_combo_domination` and `measure_combo_leg_echo`
share the constant and therefore share the flaw — a relative or log-odds band
would be the fix, and it must be pre-registered before the next echo run rather
than chosen now.

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

Largest contributor: `cross_game`, 11/20 = 55% of the pooled rate.

**No cell here has the power to agree or disagree with the pooled rate.** The
earlier version said "the parts do not visibly disagree", which is a
homogeneity claim, and a design with cells of 2/11, 0/4 and 2/5 cannot make
one — the absence of a visible difference at those counts is a property of the
counts, not of the venue. **No scope-level claim is made here.**

Worse, on the `reproduces` column this table is actively misleading, and the
split that matters is not scope at all. `cross_game` reads 6/9, and all six
successes are the single `0.9980 × 300` quoter. Drop that quoter and the cell
becomes **0 of the remaining 3**. The grouping that changes the reading is the
book signature, above — not scope.

### Structure of the sample, for whoever reads this next

- **15 of the 16 non-empty books were a single resting bid**, and the
  sixteenth had two levels. Equivalently: **19 of 20 books carried at most one
  level.** There is no depth. (The earlier version said "19 of 20 non-empty
  books were a single resting bid", which inflates books-with-a-bid from 16 to
  19 and contradicts this document's own (a) section. It was the one place the
  honest "non-empty means one bid, not a book" framing drifted.)
- **6 of 20 rows were quoted at 0.0020** — 10-to-15-leg parlays, each with a
  byte-identical NO bid of `0.9980 × 300`. One automated quoter, and it carries
  (b)'s pooled rate and is the whole of (c)'s exclusion.
- **3 of 20 rows had non-zero volume and open interest** (202, 213 and 509
  contracts), so this population is not entirely untraded junk — and **one of
  those three had an empty book** while the list quoted it at 0.1470.
- Ages 15–37 s. Only the newest combinations are quoted at all, so the sample
  is young by necessity, not by choice.

---

## What this changes about the 2,116 stored combo prices

Plainly: **it does not invalidate them, and it does not clear them.** It shows
that a list ask with no resting size behind it is a real state of this venue,
at `n = 4`.

**The 8%–42% interval is not a statement about the 2,116-row population.** That
population is 66% `KXMVECROSSCATEGORY`, which this sample did not touch at all,
and 100% two- and three-leg, which is 3 of these 20 rows. An earlier version of
this document wrote that the 2,116 rows "carry an unmeasured fraction — this
sample says somewhere in 8%–42% — of asks that had no resting size behind
them." **That transfer is unsupported and is withdrawn.**

The structurally comparable subsample — rows at 2 or 3 legs — is `n = 3`, of
which 1 was empty: Wilson **[6.1%, 79.2%]**. That is not a measurement. And
even that overstates the case, because all three are still from the wrong
series.

Both "what this does not establish" lists framed the transfer risk as
*temporal*: "transfers only to the extent that population is stable." **That
was the wrong axis.** The caveat that actually overturns the transfer is
structural non-overlap on series and leg count, and it was checkable from
`docs/measurements/2026-08-09-combo-domination.json` — a file already committed
to this repo — at zero cost. Nobody looked. The pre-registered list is left
unedited above; this paragraph is the correction.

What is now on the record, with its `n`:

1. **A row can carry a list ask with nothing resting behind it.** 4 of 20 on
   this sample. That was previously an 8-row anecdote; it is now an observation
   with an `n`, on a population that is not the harvest's.
2. **In this sample, that happened only to rows that were about to stop being
   quoted.** 0 of 14 still-quoted rows had an empty book — but one direction of
   that association is forced by how a derived ask is defined (see (a)), and
   the condition is one a list-only harvest never gets to apply.
3. **The list ask and the book-derived ask disagree often enough to matter.**
   5 of 16, from −4.9c to +3.6c, no direction established, and the pooled
   "reproduces" rate is a blend of one quoter at 6/6 and everything else at
   5/10.

What follows, concretely:

- **Any money decision on a combination must price off the order book, not the
  `/markets` row.** Finding (3) is a 1–4c effect in either direction against a
  0.38-point headroom. This is the actionable one, and it is cheap: one call
  per candidate. It does not depend on the transfer, on the direction, or on
  the cluster split.
- **Any future combo harvest should read the book in the same pass, or at
  minimum re-read the list a few seconds later and drop rows whose ask has
  gone.** The re-read costs one batched call per pass and would have caught all
  four empty-book rows here.
- **The 2,116 stored rows do NOT gain a quantified second caveat.** They gain a
  *qualitative* one: a list ask can be unbacked, so an unknown and unmeasured
  share of them may have been. No interval attaches to that share. Nothing here
  recovers which rows those were, and those markets are gone.
- **Nothing here reinstates anything.** The 94%, the 22.4% and both combo
  claims stay withdrawn.

### The measurement that would settle it

Named so the next session does not have to invent it, and so this document
cannot be read as having already answered it:

> **The same harness, with selection stratified across `DISCOVERY_SERIES` and
> restricted to at most three legs** — the harvest's own eligibility rule — at
> an `n` large enough that each series carries its own interval. Report the
> book-empty rate **per series**, never pooled, because the two series are
> minted by different generators and nothing here shows they behave alike.

Both changes are now in the harness (`round_robin`, `--max-legs 3`). The run
itself is not made here: E2's numbers stand as recorded, and re-running the
harness until the sample looks better is the move this document exists to
avoid.

---

## What this does NOT establish

In addition to the six limits fixed before collection, all of which still
apply — with one of them now known to have been the wrong limit:

- **Nothing about the 2,116 rows, as a population and not only individually.**
  The pre-registered limit said this "transfers only to the extent that
  population is stable", framing the risk as temporal. The binding risk is
  **structural**: 0 of 20 rows from the series that is 66% of the target, and
  17 of 20 at a leg count that occurs zero times in it. No rate here transfers,
  however stable the population is.
- **Not that the list endpoint is stale rather than the book flickering.** The
  causal direction between "the book empties" and "the quote ends" is not
  observable in a single re-read, and a quoter posting and pulling produces the
  same table.
- **Not that a backed quote stays backed.** 0/14 has an interval reaching
  21.5%. It is not zero — and one direction of the association it sits inside
  is mechanism-forced.
- **Not that any (b) disagreement is a pricing error.** The re-read adjudicates
  4 of the 5 and splits them 2 for the move/lag story and 2 against; it does
  not establish what the other explanation *is*. That is what the follow-up
  check below was added to test.
- **Not that age, exposure or read position drives the empty books.** All three
  are perfectly collinear in this design and cannot be separated by any
  re-analysis of this data.
- **Nothing at a finer time resolution than one re-read.** No time series was
  taken; a book that emptied and refilled inside the pass would be invisible.
- **Nothing about the echo hypothesis.** (c)'s 1/10 is a base rate on
  unselected rows and says nothing about combinations selected for echoing —
  and `ECHO_TOLERANCE`'s absolute 2c band is uninformative near price 0, which
  the exclusion happened to hide rather than fix.
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
   The contemporaneity control was added to bound it. It is genuinely useful —
   it adjudicates 4 of the 5 (b) disagreements row by row — but the
   0/14 it produces is conditional on a read a list-only harvest never makes,
   and its headline association is mechanism-forced in one direction. It is a
   control, not a replacement for 4/20.
4. **E2 fixes a population without fixing a sampling frame.** This is the one
   that cost the most. "For each combination carrying a `yes_ask` on
   `/markets`" names no series mix and no leg-count range, so "the first 20
   eligible rows in discovery order" satisfied it exactly while producing a
   sample with **zero** overlap in leg count with the population the run was
   meant to inform. A pre-registration that fixes thresholds and denominators
   but not the sampling frame protects against the wrong failure.

---

## Corrections after audit

The measurements are unchanged. The harness was **not** re-run to obtain a
better sample. What follows is the list of claims the prose made that the data
does not support, corrected in place above and itemised here so the correction
is auditable rather than invisible.

| # | claim as written | what the data says |
|---|---|---|
| 1 | the 2,116 rows "carry an unmeasured fraction — this sample says somewhere in 8%–42% —" of unbacked asks | **Unsupported, withdrawn.** The sample is 0/20 from the series that is 66% of that population, and 17/20 at leg counts that occur zero times in it. Comparable subsample `n = 3`. |
| 2 | (b)'s pooled 68.8% "reproduces" | A blend of one quoter at **6/6** and everything else at **5/10**. `cross_game` reads 6/9 with all six successes that quoter. |
| 3 | "three of them 1.2–3.6c *against* the buyer" beside the 0.38-point headroom | **No direction established.** 3 against, 2 in favour, largest row (−4.9c) in the buyer's favour. Framing withdrawn. |
| 4 | Fisher exact, p = 0.0031 | Post-hoc — `554b719` named no test and no committed code computes one. One direction is mechanism-forced by `yes_ask = 1000 − best_no_bid`. Demoted; the converse *is* falsified in-sample (2 of 6). |
| 5 | "This cannot be separated from a genuine 3.4-second price move" | The run's own `confirm_ask` column separates 4 of the 5, and was not used. 2 consistent with the move, 2 not, 1 unresolvable. |
| 6 | "the whole pass spanned 3.4 seconds" as the exposure | Per-row list-to-book gap runs 0.24 s to 3.36 s. Reported per row. Position, age and exposure are collinear; nothing is claimed from the empties' positions. |
| 7 | `GRID_TOL` justified by "the derived-ask identity held on 2,145 real quotes" | Misattributed. That check was within a single market-summary row, from an endpoint SKILL.md says **excludes MVE entirely**. Docstring fixed; the tolerance's value is unchanged. |
| 8 | (c)'s exclusion of 6 rows, direction unstated | Stated: the exclusion moved the rate **down**, 37.5% → 10.0%. See below — the audit that prompted this correction had the direction backwards. |
| 9 | "19 of 20 non-empty books were a single resting bid" | There are **16** non-empty books. 15 had one level, 1 had two. |
| 10 | "The parts do not visibly disagree" | A homogeneity claim the design cannot make at cells of 2/11, 0/4, 2/5. No cell has the power to agree or disagree. |

### Where the audit was itself wrong

Recorded because an audit is not above correction either, and because this one
would have put a new false statement into the record.

The audit asserted that (c)'s six excluded rows were "every one a **guaranteed**
non-echo", their "sole book level deriv[ing] to 0.002 against legs at 0.3–0.9",
and that excluding them therefore moved the rate **up** from 1/16 = 6.3% to
1/10 = 10.0%.

Checked against the run's own JSON: the legs do not run 0.3–0.9. Five of the
six rows carry a leg priced at **0.010**, and `|0.002 − 0.010| = 0.008 ≤ 0.02`,
so **five of the six would have scored as echoes, not as non-echoes.** The
counterfactual is 6/16 = 37.5%, and the exclusion moved the number **down**,
not up.

The exclusion is still right, but the reason is the opposite of the one given:
those five would have been *spurious* echoes, produced by an absolute 2c
tolerance applied at the bottom of the price grid where every price is within
2c of every other. The audit reached the correct verdict on the rule by an
argument that inverted the arithmetic — which is the same failure mode as the
prose it was auditing, and is why the direction is now computed by the harness
rather than reasoned about.
