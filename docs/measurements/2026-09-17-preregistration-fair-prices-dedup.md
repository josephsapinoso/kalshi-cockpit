# Pre-registration — did the `fair_prices` dedup deliver? And the correction that it already shipped

Written **2026-09-17**, before any post-deploy row of `fair_prices` has been
counted, sized or grouped by anything.

---

## 0. READ THIS FIRST — the assignment's premise is false, and the correction is the first finding

This document was commissioned as *"the successor pre-registration for the
non-destructive `fair_prices` deduplication"*, the second half of Joe's answer
`55E`, against ticket **#55 Amendment 1**, which says the dedup is *"the
non-destructive option nobody has registered."*

**It shipped eight days ago.**

```
commit  e8ec6ff  2026-09-09T21:56:46Z  "A consensus that has not moved is
                                        confirmed, not reinserted"
ADR     0133     Accepted 2026-09-09
schema  v36      (2026-09-09) fair_prices.confirmed_ms,
                 .confirmed_oldest_book_age_ms
        v37      (2026-09-10) idx_fair_market_confirmed, ADR 0134
live    SCHEMA_VERSION on main is 44; live is known to be >= v40 (ADR 0143,
        read 2026-09-15), so the live box has been running v36 since ~09-09/10
```

`backend/runner.py:write_fair_price` no longer ends in an unconditional
`INSERT`. For each outcome it looks up the most recent row sharing the
**five-column identity** `_FAIR_PRICE_KEY_COLUMNS = (link_id, market,
outcome_name, outcome_description, outcome_point)`; if every column of
`_FAIR_PRICE_PAYLOAD_COLUMNS` matches, it `UPDATE`s that row's `confirmed_ms`
and `confirmed_oldest_book_age_ms` and returns the existing id instead of
inserting. `computed_ms` and `oldest_book_age_ms` are `_FAIR_PRICE_FROZEN_COLUMNS`
and are excluded from the comparison by construction.

So the correctly-keyed identity that Amendment 2 §B4.4 said a successor *"must
fix in advance"* was fixed — in code, on 2026-09-09, by the same session that
recorded §B4. **The thing this document was asked to pre-register is a thing
that has been running in production for eight days.** You cannot pre-register
that. What follows is therefore not §B7's successor registration; it is a
different document with a different job, stated in §0.3.

### 0.1 The second correction: a non-destructive dedup does not shrink the file, and #55 Amendment 1 says it does

Ticket #55 Amendment 1 puts this row in front of Joe:

```
    dedup (IF it holds)  ~1.49 GB / ~2.9 GB db   ~51%   free
```

**That row is wrong, and Amendment 2 §B6.3 — cited in the same ticket — says so
in its own words:**

> *"It reclaims none. A dedupe **deletes nothing**, so it produces no freed page
> and touches no row already written. `fair_prices` was 1,705,545,728 B on
> 2026-09-09 and would still be 1,705,545,728 B the instant after a dedupe
> shipped. It changes the slope, not the level."*

A change-only insert takes the database from `5.07 GB` to `5.07 GB`. It does
not take it to `2.9 GB` and never will. The only operation that would move the
existing 2.41 GB is a **retrospective collapse of already-written rows**, which
is a `DELETE`, which is #55's option **C**, which §6 of the parent registration
already closed on its own NOT WORTH ARMING branch — and which, per §9.4, returns
**zero filesystem bytes** without a `VACUUM` that §7 of the volume clock says is
untested on this box and needs roughly the file size free on the same
filesystem, on a volume that has been 100% full once already.

**Consequence, and it is a ticket action rather than a note:** the option table
Joe is being asked to choose from contains a free option whose stated effect
does not exist. That correction belongs in #55 **before he answers**, as a
further amendment to the existing sub-issue — not as a new ticket, because #55
is already a sub-issue of map #3 and already carries this question.

### 0.2 The third correction, and it is the expensive one: §B7's successor can no longer be run as written

§B7 asks a successor to fix *"the claim, one-sided and falsifiable ... as a
statement about a slope"*, over *"the day, with the number of days and the
requirement that at least one is an NFL Sunday fixed in advance"*.

**Post-deploy, that measurement is impossible by construction.** A confirmed
pass writes no row and increments no counter. `confirmed_oldest_book_age_ms` is
overwritten on every confirmation, so only the last one survives. There is no
record of how many passes confirmed a row, and therefore **the duplication rate
cannot be computed from any data written after 2026-09-09.** The change that the
registration would have authorised destroyed the ability to register it.

It remains computable on **pre-2026-09-09 rows**, which are untouched (no
backfill, ADR 0133; the downsampler is off). Running it there would be an audit
of a decision already taken, not a registration, and it would authorise nothing.
**This document does not propose it**, and §11.6 says why that is a refusal
rather than an omission.

### 0.3 What this document actually registers

**The effect that shipped has never been measured.** No `db-sizes` read, no row
count, no growth figure has been taken on live since 2026-09-09T19:49Z — which
is *two hours before the dedup commit*. Nobody has checked whether ADR 0133
did anything at all.

That check is:

- **Not yet contaminated.** No post-deploy number has been seen by anyone.
- **Decision-bearing**, and §1.3 shows it decides which of two materially
  different questions goes to Joe in #55.
- **Cheap and bounded** — two seeking queries, no full-table scan, no `dbstat`
  (§9.5 explains why the byte read is deliberately *not* taken).
- **Enormously powered** (§1): the design must separate ~0.004 from ~1.0.

So the threshold is fixed here, before the number exists, exactly as it would
be for a prospective measurement. The mechanism ran blind; the measurement does
not have to.

### 0.4 Declared blindness — PARTIAL, and the contamination it creates

**Seen while writing this:** `backend/runner.py:1040-1260` (the dedup path in
full), `docs/adr/0133*` §1-2, `backend/store/db.py:60-135` (the v35-v42 history),
`backend/store/schema.sql:836-866` (the three `fair_prices` indexes),
`scripts/inspect_live_db_loop.py:100-195` (`db-sizes`), the parent registration
in full including Amendments 1 and 2, `gh issue view 55` including Amendment 1,
`docs/measurements/2026-09-17-preregistration-sharp-anchor-census-ncaaf.md`
(house format), `CLAUDE.md`.

**NOT blind, and it is declared rather than hidden.** I have read §B4's
99.73% / 99.61% / 99.75%, and I have read ADR 0133's own restatement of them.
A threshold chosen by someone who has seen a 99.7% can be placed to make the
answer come out.

**The guard.** The threshold in §6 is `0.25`. It is **not** placed near 0.003,
near 0.25, or near any observed value. It is derived in §6.2 from two things
that were on the record before 2026-09-09 — the 56.82% family share of file
growth and the residency arithmetic in #55 — and it is deliberately **~60x
weaker** than the mechanism's own prediction, so that the two unfixed model
steps of §B6.4 cannot flip it. A reader who suspects tuning should check that
claim against §6.2 rather than against the write-up.

**Not seen, not queried, not requested:** any `fair_prices` row count on live at
any date; any `db-sizes` output after 2026-09-09T19:49Z; any post-deploy
`confirmed_ms` value; the live file size today.

---

## 1. THE POWER CHECK, which comes before everything else

### 1.1 The statistic has no sampling error, so the question is separation, not `n`

The deciding statistic (§5) is a ratio of two **census counts over complete
enumerations** of two closed past windows. There is no sample, no standard
error, and `sqrt(p(1-p)/n)` does not apply — the same ruling §5 of the parent
document makes for `eligible_row_fraction`.

The separation required:

```
  mechanism working, as designed   rho ~ 0.004   (99.6% of inserts suppressed)
  mechanism doing nothing          rho ~ 1.0     (or above; see 11.5)
  registered cut                   rho = 0.25
```

**250x separation against a cut in between.** There is no `n` at which this
fails to resolve. **The binding uncertainty is confounding and generalisation,
not estimation**, and §11 carries it rather than the number.

### 1.2 The question the design CANNOT resolve, answered now by arithmetic, for free

**Does the 4 GB box fix the 503?** No, and it is knowable before it is bought.
This is the ADR 0016 habit: do the arithmetic before spending.

From the two dated `db-sizes` reads (§B2.1), the only rates on the record:

```
  D0          5,070,802,944 B     file, 2026-09-09T19:49Z
  file        326.6 MB/day        one 8.138-day interval, G = 1
  family      185.6 MB/day        56.82% of file growth
  non-family  141.0 MB/day        the remainder; odds_snapshots dominates it
                                  and has NO retention rule and NO owner
  cache       ~3.5 GB on a 4 GB box   (inherited from #55 Amd 1, UNVERIFIED)
  50% residency  <=> file <= 7.0e9 B
  headroom from D0                1,929,197,056 B
```

| scenario | file growth | days from D0 to 50% residency | crosses |
|---|---|---|---|
| dedup does nothing | 326.6 MB/day | **5.9** | ~2026-09-15 |
| dedup works perfectly (family -> 0) | 141.0 MB/day | **13.7** | ~2026-09-23 |
| what a 30-day billing month needs | <= 64.3 MB/day | 30.0 | — |

**Three verdicts, all free, all before the box is bought:**

1. **No achievable dedup result buys one billing month of >=50% residency on a
   4 GB box.** The non-family term alone is 141.0 MB/day against a requirement
   of 64.3. **A threshold denominated in residency-days would therefore be
   unclearable by any result**, and a threshold nothing can clear is not a
   decision rule. §6.2 denominates on the growth share instead, for this reason.
2. **The 4 GB box is a stopgap measured in weeks, not months**, at the realised
   rate — best case ~2.3x the time between paid upgrades. That is a finding
   about the plan, it is cheaper to learn now than after the run, and it is
   #55's own caveat ("it does not make the database smaller") with a number on
   it.
3. **Whether the box helps materially on the day it is bought depends on
   exactly the quantity this document measures.** Projecting D0 forward 7.4 days
   to today:

   ```
     if the dedup did nothing     ~7.49e9 B  ->  46.7% residency on a 4 GB box
     if the dedup worked          ~6.11e9 B  ->  57.3% residency on a 4 GB box
   ```

   Those are different answers to "did paying help", and nobody currently knows
   which one is true. That is the measurement.

### 1.3 Is it decision-relevant? Yes — different files are edited and a different question reaches Joe

The box is being scaled either way, so the naive test says "we proceed either
way, kill it." That is not the shape here:

- **PASS:** the `fair_prices` growth lever is **spent** — there is no second
  one, and no future plan may name it. The residual growth is non-family, the
  named next lever is `odds_snapshots` retention, and the ticket to Joe says
  *the box is a weeks-scale stopgap and the remaining lever is a table nobody
  owns.*
- **FAIL:** ADR 0133 is not delivering in production, #55 Amendment 1's free
  option does not exist in any form, Joe's option set collapses to **A or D**,
  and the work is a diagnosis of five named hypotheses (§8.2) rather than a
  retention plan.

Different follow-on work, different ticket text, different table named. That is
the test, applied before the run.

---

## 2. The claim, as a thing that could be false

**Primary claim, ONE-SIDED, direction fixed here:**

> Over the post-deploy window (§3.2), the number of rows inserted into
> `fair_prices` per UTC day for `market IN ('h2h','spreads')` is **at most 25%**
> of the number inserted per UTC day over the pre-deploy window (§3.1).

Stated as `rho <= 0.25`, where `rho` is defined in §5.1.

One-sided deliberately. A two-sided reading lets "it still came down a bit" be
written up as a success, which is how a change that half-works gets recorded as
one that works.

**Secondary claim, an ENUMERATION and not a statistic, falsified by one row:**

> Within the bounded probe of §5.3, no `fair_prices` key has two rows whose
> `[computed_ms, COALESCE(confirmed_ms, computed_ms)]` intervals overlap or run
> backwards.

This is the preservation claim (§7). It is not a test, carries no threshold and
no multiplicity, and **one violation falsifies it**. It outranks `rho`: a
preservation violation is a data-integrity finding and the result document leads
with it whatever `rho` says.

**What neither claim is.** Neither is "the duplication rate is 99.7%" (§0.2: no
longer measurable). Neither is "the file got smaller" (§0.1: it did not).
Neither is "the 4 GB box is sufficient" (§1.2: it is not). Neither is "ADR 0133
caused the change" (§11.5).

---

## 3. The population, the windows, and the exclusions

**Population: every row of `fair_prices` on the live database whose
`computed_ms` falls in one of the two windows below and whose `market` is in the
registered market set.** No sampling. Both windows are **closed and in the
past**, which has consequences §9.3 relies on.

### 3.1 The pre-deploy window

```
  [ 2026-09-01T00:00:00Z , start of the UTC day containing the v36 deploy instant )
```

Expected to be **2026-09-01 .. 2026-09-08 inclusive, 8 complete UTC days**,
containing Sunday 2026-09-06 and Saturday 2026-09-05.

The floor is 2026-09-01 because that is the date of the parent registration and
of the first `db-sizes` read on the record. Reaching further back crosses an
earlier market-set rollout and mixes populations. Fixed here, and independent of
anything the counts will say.

### 3.2 The post-deploy window

```
  [ first UTC day beginning strictly after the v36 deploy instant , 2026-09-17T00:00:00Z )
```

Expected to be **2026-09-10 .. 2026-09-16 inclusive, 7 complete UTC days**,
containing NFL Sunday **2026-09-13**.

**The end is 2026-09-17T00:00:00Z and it is chosen for a reason that must not be
relaxed:** the box is being scaled to 4 GB on 2026-09-17. Ending the window at
the start of that day keeps **both windows entirely on the 2 GB box**, so no
part of the deciding statistic straddles the scale. §9.2 explains why the *read*
is nonetheless taken after the scale, and why that is not a confound.

### 3.3 The excluded day, and why the exclusion is independent of the outcome

**The UTC day containing the v36 deploy instant is excluded from both windows.**
It is neither pre nor post: some of its passes ran unconditional inserts and some
ran the dedup, and nothing in the record says where the boundary fell inside the
day. The exclusion references the deploy clock, not the row count, not the
market, and not anything the queries produce.

### 3.4 The market set, and the two exclusions in it

`Q1` reports `market IN ('h2h','spreads','totals')`.

- **`rho` is computed on `('h2h','spreads')` only.** `totals` entered the feed
  on 2026-09-14 (ADR 0152) and therefore has **no pre-window denominator**.
  A ratio with a zero denominator is not a small ratio, it is not a ratio.
  `totals` counts are printed beside `rho` and excluded from it.
- **Player-prop markets are excluded entirely.** The reason is the query plan,
  not the data: `idx_fair_market_computed` leads with `market`, so a seek needs
  the market values enumerated, and the prop market key set
  (`PROP_MARKETS`, `backend/odds/client.py:169-178`) is open-ended and has
  changed twice this month. An unenumerated predicate turns `Q1` into the
  full-table scan that §9.4 forbids. **This exclusion references the index, not
  the dependent variable**, and it is registered before any count exists.

### 3.5 Tables and databases out of scope

`odds_snapshots` (named repeatedly in §1.2 and §11.2 as the residual growth term
and **not measured here**), `recommendations`, `closing_lines`, `kalshi_quotes`,
`manual_orders`, `parlay_positions`, every other table. `data/demo.db` and any
local or CI database: **no number from them may be quoted anywhere.**

---

## 4. The unit of observation, and the clustering — where `n` gets inflated

**The unit is the row for counting, and the UTC day for clustering.**

> `G_pre = 8`, `G_post = 7`. **The millions of rows are not `n`.**

§B6.1 fixes the cluster as **the day** and records that the original finding had
`G = 1`. This design raises `G` to 7 post-deploy days by using windows that are
already in the database — no waiting, no new collection.

**And 7 days is still not 7 independent replications**, which is the `G_eff`
error this project has made before (the `beta` fits: `G = 311` nominal,
`G_eff = 4.26`, one sport carrying 95.6% of the leverage). The seven days share
one recorder, one deployed config, one book list, one odds cadence and one
season. Accordingly:

- **No standard error is computed on `rho`, and none may be printed beside it.**
- **The per-day series is printed in full**, every day, both windows, never only
  the means. The repo's rule: a pooled number is not a finding until the parts
  agree.
- **The largest single day's share of post-window rows is printed beside
  `rho`.** If one day carries more than 50% of post-window rows, that is stated
  in the result document's first paragraph, in the manner of "two WNBA games
  carrying 41%".

**Clustering floor, fixed now:**

> The post window must contain **>= 6 complete UTC days** AND **>= 1 NFL Sunday
> (2026-09-13)** AND **>= 1 MLB weekday**. The pre window must contain **>= 6
> complete UTC days**.

**If the floor is not met — for instance if the v36 deploy instant turns out to
be later than 2026-09-11T00:00:00Z — the verdict is INCONCLUSIVE.** The read is
deferred and the windows are re-registered by a dated amendment with a later
end date. They are **not** reinterpreted at fewer days, and `rho` is **not**
computed on a short window "to see".

---

## 5. The statistics, named as estimators

### 5.1 `rho` — the deciding statistic

```
  R_pre  = (rows inserted, market IN ('h2h','spreads'), pre window)  / G_pre
  R_post = (rows inserted, market IN ('h2h','spreads'), post window) / G_post
  rho    = R_post / R_pre
```

**What it is: a ratio of two census counts over complete enumerations of two
closed windows.** Exact given `Q1`. **Not an estimator of the duplication
rate** — it is an insert-rate ratio across a configuration change, and §11.5
lists four things that moved inside the post window besides the dedup.

**Error class: none from sampling; all from confounding and generalisation.**

### 5.2 The reported-but-not-tested quantities

Printed in the result document, each labelled **CONTEXT — NOT A TEST**, no
threshold attached, no multiplicity incurred:

- rows per UTC day per market, both windows, in full (§4)
- `rho_h2h` and `rho_spreads` separately (§6.3 attaches the one registered gate
  to their agreement in direction, and nothing else)
- `totals` counts, post window only (§3.4)
- the largest day's share of post-window rows
- the count of post-window rows with `confirmed_ms IS NOT NULL`, and the
  distribution of `confirmed_ms - computed_ms` at p50/p90/max

### 5.3 The preservation probe

A bounded enumeration, not a statistic. Over **`market = 'h2h'` on the single
UTC day 2026-09-13** — fixed in advance, and chosen because it is the post
window's NFL Sunday and therefore the highest-pass-rate day, i.e. the day on
which an overlap bug is **most** likely to show. It is chosen to maximise the
chance of falsification, not to avoid it.

Returns: the count of violating adjacent pairs, and the first 20 of them.

---

## 6. The decision rule, with the multiplicity already counted

### 6.1 How many cells are tested

**One deciding cell: `rho`.** Plus **one registered binary gate**: the
direction agreement of `rho_h2h` and `rho_spreads` (§6.3). Plus **one
enumeration** (§5.3) which is falsified by a single row and carries no
threshold.

At one deciding cell there is no multiplicity correction to make, and the reason
is that the cut was named before any count existed — not because nothing else is
interesting. **Every other quantity in §5.2 is printed without a threshold and
may not acquire one in the write-up.** If the result document attaches a verdict
to a per-day figure, to `totals`, or to the `confirmed_ms` gap distribution,
this registration was violated.

### 6.2 The threshold, and why it is 0.25

Fixed here, from figures that were on the record before 2026-09-09:

```
  rho <= 0.25
```

1. **It is the level at which `fair_prices` stops being the majority
   contributor to file growth and becomes roughly a quarter of it.** Pre-deploy
   the family was **56.82%** of file growth: 185.6 of 326.6 MB/day. Holding the
   non-family term at 141.0, a family term at 25% of its old value gives
   `46.4 / (46.4 + 141.0) = 24.8%`. **That qualitative change — largest
   contributor to minor contributor — is the whole point of the exercise**, and
   it is a sentence rather than a fitted cut.
2. **It is ~60x weaker than the mechanism's own prediction** (`rho ~ 0.004`).
   §B6.4 names two unfixed model steps between a row rate and a byte claim, and
   §9.2 names an untested uniform-bytes-per-row assumption. Those are plausibly
   worth a factor of two or three. They are not worth a factor of sixty. **The
   cut is placed so that no model step this design leaves open can flip it.**
3. **It is deliberately NOT denominated in residency-days.** §1.2 shows no
   achievable result buys a billing month of >=50% residency on a 4 GB box, so
   a residency threshold would be unclearable by construction and the
   measurement would return a number that decided nothing.
4. **It is robust in the direction that matters.** Two confounds inside the post
   window push `rho` **up** (§11.5: `totals` markets added 09-14, NFL season
   live in post and not in pre). A **PASS despite them is a fortiori.** A FAIL
   is **not** a fortiori, which is why §8.2's FAIL branch is a diagnosis and not
   a revert.

### 6.3 The decision rule, verbatim

> On the single look defined in §9, over the two closed windows of §3, with the
> preconditions of §9.1 all answered YES:
>
> - **If any precondition in §9.1 answers NO, or the clustering floor of §4 is
>   not met** — the verdict is **INCONCLUSIVE**. `rho` is not computed, no
>   figure is quoted anywhere, and this document is amended rather than worked
>   around.
> - **If the preservation probe (§5.3) returns one or more violations** — the
>   verdict is **PRESERVATION VIOLATED**, it outranks every other branch, the
>   result document leads with it, and ADR 0133's non-destructive claim is
>   recorded as falsified. Nothing is built. `rho` is still reported, labelled
>   as subordinate to the integrity finding.
> - **If `rho_h2h` and `rho_spreads` fall on opposite sides of 0.25** — the
>   verdict is **SPLIT**. **No pooled `rho` is reported as the finding.** A
>   pooled number is not a finding until the parts agree.
> - **If `rho > 0.25`** — the verdict is **DEDUP NOT DELIVERING**. §8.2 applies.
> - **If `rho <= 0.25` AND the parts agree AND the preservation probe is clean
>   AND every precondition is YES** — the verdict is **DEDUP DELIVERING**.
>   §8.1 applies. **That is a verdict about the growth slope and about nothing
>   else**; it authorises no build, no arming, no schema change and no claim
>   about bytes on disk.
>
> **No branch of this rule permits moving the window boundaries in response to
> the counts.** The pre window, the post window, the excluded day and the market
> set are fixed in §3. A different window may be adopted only by a written,
> dated amendment that states its reason **without reference to any count this
> read produced.**

### 6.4 The repeated-looks hazard does not apply here, and the reason is not the usual one

This project measured a 13.7% floor on the probability that a threshold
re-evaluated against an accumulating database crosses under a true zero. **That
shape is absent here, by construction and not by promise:** `rho` is computed
over two **closed past windows**. Re-reading tomorrow returns the same counts.
It is not a monotone accumulating quantity and there is nothing for an
always-valid boundary to correct.

**The corollary, registered so it cannot be exploited:** because a re-read
cannot move `rho`, a re-read is cheap — and that is exactly why the window
boundaries, not the number of looks, are the thing §6.3 nails down. The freedom
this document removes is *sliding the windows*, not *looking twice*.

---

## 7. What is preserved — and the part that is NOT, stated plainly

The assignment asks what fact is guaranteed recoverable, and instructs that if
any fact is lost, the word "non-destructive" may not stand unqualified. **A fact
is lost. Three, in fact.**

### 7.1 PRESERVED: the value series, to interval granularity

For a key `K` and an instant `t`, the consensus payload the desk held is the
payload of the row for `K` with the greatest `computed_ms <= t`. No payload
value has ever been overwritten: a changed payload always inserts
(`backend/runner.py:1252-1256`), and the confirm path writes only `confirmed_ms`
and `confirmed_oldest_book_age_ms`. This is ADR 0055's change-log semantics,
applied to a second table.

**The test that would prove it, and it is §5.3:** the per-key rows must form a
non-overlapping, forward-ordered change log —
`COALESCE(confirmed_ms, computed_ms) >= computed_ms` on every row, and
`computed_ms(next) > COALESCE(confirmed_ms, computed_ms)(prev)` on every
adjacent pair. One violation means a confirmation landed on a row that was not
the latest for its key, and last-value-carried-forward reconstruction is then
wrong. **A clean probe does not establish the property globally** — it is one
market on one day (§5.3), and that limit is stated here rather than discovered
in the write-up.

### 7.2 LOST (1): which odds instant the runner consumed on a confirmed pass

A confirmed pass leaves no row. `docs/measurements/2026-08-10-sharp-anchoring-census.py:177-191`
walks every `h2h` row and matches each `computed_ms` to the odds instant it
consumed; that walk produced ADR 0021 §8's 73.0% figure. **It cannot be re-run
over any period after 2026-09-09.** ADR 0133's own docstring says so, and §B6.5
predicted it: *"The downsample destroys it backwards; a dedupe declines to
record it forwards. Neither is free, and a proposal that presents the dedupe as
costless has omitted this."*

### 7.3 LOST (2): per-pass `oldest_book_age_ms`

`confirmed_oldest_book_age_ms` is overwritten on every confirmation. Only the
**last** confirmation's input freshness survives; every intermediate one is
gone. §B4.5 already flagged that reconstructing it depends on
`odds_snapshots` continuing to have no retention rule — which nobody has
promised.

### 7.4 LOST (3): the gap between "unchanged" and "unobserved"

The lookup takes the most recent row for a key **across all time**, with no day
boundary. So a key last written ten days ago, re-derived today to the same
payload, **updates that ten-day-old row** and produces
`confirmed_ms - computed_ms = 10 days`. The interval says nothing about whether
the key was observed continuously inside it. **Last-value-carried-forward can
therefore assert a value stood at an instant at which nothing was observed at
all.** The reconstruction guarantee of §7.1 is exact to the *interval*, not to
the *instant*.

### 7.5 Therefore

> **"Non-destructive" is true of the value series and false of the observation
> series.** ADR 0133 destroys no recorded value and destroys the record of every
> pass that did not change one. Any sentence of the form "the dedup loses
> nothing" is wrong and this document refuses it.

---

## 8. What would falsify this, where the negative goes, and the consequences

### 8.0 Destination, fixed now, written whichever way it comes out

**`docs/measurements/2026-09-18-fair-prices-dedup-effect-result.md`**, linked
from `tasks/NEXT.md` in the same commit. **INCONCLUSIVE, SPLIT, NOT RUN and
PRESERVATION VIOLATED go to the same file.** A negative branch with no address
is a negative that quietly never gets written.

The result file carries, in this order: the §9.1 precondition answers; the
deploy instant and the two resolved windows; the per-day counts in full; the
per-market `rho`s; the largest-day share; `rho`; the preservation probe; the
§6.3 verdict **verbatim**; then §11 reproduced verbatim.

### 8.1 DEDUP DELIVERING

| | |
|---|---|
| **On screen** | **Nothing.** No screen reads `fair_prices` row counts and none is changed by this. |
| **On the box** | **Nothing.** The 4 GB scale is Joe's decision in #55 and is not conditioned on this result. |
| **Built** | Nothing. No ADR, no migration, no `SCHEMA_VERSION` bump. |
| **Written** | The result doc; a correction to #55 Amendment 1 replacing the `~2.9 GB` row with the slope figure and the note that the dedup shipped on 2026-09-09. |
| **Killed** | **`fair_prices` as a growth lever.** It is spent. No plan may name it again. The named residual is `odds_snapshots` — 141.0 MB/day, no retention rule, no owner — and naming it is all this document does about it. |

### 8.2 DEDUP NOT DELIVERING

| | |
|---|---|
| **On screen** | Nothing. |
| **Built** | **Nothing without an ADR**, and specifically **no revert**: §6.2(4) records that the confounds are not a fortiori in this direction, so a FAIL does not identify ADR 0133 as the cause. |
| **Written** | The result doc, plus the five hypotheses below **checked in this fixed order**, before any new one is entertained. |
| **Killed** | #55 Amendment 1's free option, in any form. Joe's option set becomes **A or D**, and that correction must reach the ticket before he answers. |

The five hypotheses, named before the number exists so the diagnosis is not
chosen to fit it:

1. **The deploy did not happen** when `git log` implies. `flyctl releases` and
   the live `SCHEMA_VERSION`.
2. **`books_used` churns.** It is `json.dumps(metadata.get("books_used", []))`
   and it is a payload column. If the book list in a sweep is unstable — and
   **ADR 0155 replaced regions with ten named books on 2026-09-15, inside the
   post window** — the payload never matches and every pass inserts. This is
   the most likely single cause and it is named first among the mechanisms.
3. **Float jitter** in `market_width`, `overround` or any `p_*` column, compared
   with `==` at `backend/runner.py:1240-1243`.
4. **`anchored_on_sharp` flipping** between passes as a sharp book enters and
   leaves the usable set (`backend/core/devig.py:280-289`).
5. **Key explosion**: `totals` and props multiplied the number of distinct keys
   (ADR 0152), so rows per day can rise even at a constant per-key suppression
   rate.

### 8.3 The question that reaches Joe, and the marker form

**Both branches end at a money decision only Joe can make** — §1.2's verdict
that the 4 GB box is a weeks-scale stopgap holds whichever way `rho` comes out.
Per CLAUDE.md workflow step 7, the session that writes the result document
**opens a sub-issue of map #3 in the same session** (recipe:
`docs/agents/issue-tracker.md`, "Open a ticket for Joe") and names it in the
handoff.

**The marker form is the one `docs/agents/issue-tracker.md` defines under "Open
a ticket for Joe"** — a one-sentence marker ending in the number the tracker
returns when the sub-issue is created. It is named there and not restated here,
on purpose: see below.
**This document deliberately does not write the marker, and the first draft of
this very paragraph did** — it quoted the form with a placeholder one line
above the sentence claiming it had not, and
`tests/test_a_question_for_joe_has_a_ticket.py` caught it. That guard refuses a
marker without a number and refuses `#3` as the number. The same collision hit
the sharp-anchor registration the day before, whose author had also been warned
about it. **The durable rule for a measurement doc is therefore: never quote
the marker form, name the conventions file instead** — a guard cannot tell a
template from the real thing, and it should not learn to, because a template is
exactly how a real marker gets missed. Writing one with a
placeholder cost a fix yesterday.

The one sentence differs by branch, and that difference is §1.3's
decision-relevance test made concrete:

- **PASS:** the growth lever on the biggest table is spent, the box is a
  weeks-scale stopgap at the realised rate, and the remaining lever is a table
  with no retention rule and no owner — what is the plan?
- **FAIL:** the free option you were shown in #55 does not work, so the choice
  is pay or accept the 503.

---

## 9. The protocol, the preconditions, the clock and the bound

### 9.1 Preconditions — each a YES/NO answered BEFORE `Q1` runs

**If any answers NO, the queries do not run, or the result is void if they
already have, and this document is amended rather than worked around.**

- **P1. `FAIR_PRICE_DOWNSAMPLE_ENABLED` is absent or `false` on the live box,
  and has been since 2026-09-01.** If it was ever armed, D1's 14-day window has
  deleted pre-window rows — 2026-09-01 plus 14 days is already past — and
  `R_pre` is a count over a cut table. Verdict INCONCLUSIVE.
- **P2. The deploy instant of the release carrying schema v36 is established**
  from `git log` plus `flyctl releases`, recorded to the minute in UTC, and
  the two windows of §3 are written down **before** `Q1` runs. `flyctl releases`
  is not a database read and touches no page cache.
- **P3. No `DELETE FROM fair_prices` exists in `backend/` outside
  `backend/store/fair_price_downsample.py`**, re-checked by grep at read time —
  the parent document's P2, re-taken.
- **P4. The read is a single read-only session** (`mode=ro`) and the query set
  is **exactly** `Q1` and `Q2`. A third query is an amendment, not a judgement
  call.
- **P5. The clustering floor of §4 is met** by the resolved windows. Checked on
  the window definitions, before any count.

### 9.2 THE RUN WINDOW, and the before/after-the-scale ruling

**THE RUN WINDOW, fixed: `2026-09-18T07:00Z` to `2026-09-18T11:00Z`.** One look,
taken once inside it, snapshot instant recorded beside every count. Roughly
3am-7am US Eastern: the recorder runs, Joe does not.

**The read is taken AFTER the 4 GB scale, deliberately, and this is a ruling
rather than a convenience:**

1. **The estimand cannot be confounded by it.** `rho` counts rows that were
   written into two **closed past windows**, both of which end at
   2026-09-17T00:00:00Z, before the scale. Those counts are already fixed in the
   database. The box the *reader* runs on cannot change them. A before/after
   confound would exist if this were a forward rate; it is not, and §3.2
   chose the window end precisely so that it is not.
2. **The read is the hazard, and the small box is where the hazard bites.** A
   large live read evicts the page cache and the desk pays on the next tap. That
   is a production incident on this record: `/api/parlays` 503
   `read_budget_exceeded` on 2026-09-10 with `ladder_candidates` at 74.8 s cold,
   three times the 25 s budget, on a 2 GB box at ~27% residency. Running this on
   the 2 GB box would be the measurement causing the exact failure it is about.
3. **A confound WOULD be self-inflicted if the post window were allowed to run
   to the read date.** It is not. Anyone tempted to "get one more day" is
   extending the window across a hardware change, and §6.3 forbids moving the
   boundaries.

**If no look is taken inside the window**, the measurement is **NOT RUN** and
goes to §8.0's file as such. A reschedule is a **dated amendment** — and unlike
a census of a live slate, rescheduling here does **not** change the population
(§6.4), so the amendment records the miss rather than re-deciding anything.

**Expiry: if the read has not been taken by 2026-09-25T00:00:00Z, this
registration expires.** Reopening requires an amendment stating why the delay
does not itself answer the question, and re-checking P1 — the pre window is
perishable if anyone arms the downsampler.

### 9.3 Row bounding — a property of the queries, not an intention

**`Q1` — the deciding counts.**

```
  SELECT market, <utc_day(computed_ms)> AS day, COUNT(*)
  FROM fair_prices
  WHERE market IN ('h2h','spreads','totals')
    AND computed_ms >= :pre_floor
    AND computed_ms <  :post_ceiling
  GROUP BY market, day
```

`idx_fair_market_computed ON fair_prices(market, computed_ms DESC)`
(`backend/store/schema.sql:842`) leads with `market`, so the `IN` list plus the
`computed_ms` bounds give a **seek per market value**, not a scan. **Omitting
either the `IN` list or the `computed_ms` bounds is what turns this into the
full-table read that costs the desk 75 s**, which is why §3.4 excludes props
(their market keys cannot be enumerated safely) and why both bounds are
mandatory. Output is at most `3 markets x ~17 days = 51 rows`; the row cap
cannot bind and is **not** relied on as the bound.

**`Q2` — the preservation probe.** Same index, `market = 'h2h'`, one UTC day
(`2026-09-13`), a window function over that day's rows for the adjacent-pair
comparison, returning a violation count and the first 20 violations.

**Order is fixed: `Q1` first, `Q2` second, then stop.** `Q1` is the deciding
query and runs while the cache is warm; running it after anything large risks
it timing out and being re-run, and a re-run is a second look to disclose.

### 9.4 What is NOT run, and why that is the most important line in this section

**`db-sizes` is NOT run. No `dbstat` read is taken.**

`_SQL_DBSTAT` is `SELECT name, SUM(pgsize), COUNT(*) FROM dbstat GROUP BY name`
(`scripts/inspect_live_db_loop.py:134-137`). `dbstat` is a virtual table over
**every page of every btree**: it is a full walk of the entire ~5 GB file and is
the single most cache-evicting query available on this box. Section A of the
same command (`pragma_page_count`/`page_size`/`freelist_count`) is O(1) and free;
section B is not.

It is declined on three grounds, all fixed before any number exists:

1. **It is not needed for the decision.** The deciding statistic is a row rate.
   The byte conversion is §B6.4's step 1, and §6.2(2) sizes the threshold so
   that step cannot flip it.
2. **The figure it would produce decays by design.** ADR 0162's ruling: a count
   that goes stale by the hour does not belong in a document every session is
   told to trust. A family byte figure read on 2026-09-18 is wrong by
   2026-09-20. The correct treatment is to **name the instrument**
   (`scripts/inspect_live_db.py db-sizes`) and require a fresh read before
   quoting — which is what §11.9 does.
3. **It is the largest available operational risk, spent on a context figure.**
   The 2026-09-10 503 is what a full read costs.

**If a byte figure is later wanted, that is a separate, dated decision with its
own run window.** It may not be bolted onto this look as a third query (P4).

---

## 10. The stopping rule

Data collection is **two queries over two closed windows**. There is nothing to
accumulate and nothing to wait for.

- **The deciding run is the single execution of `Q1` and `Q2` inside the run
  window of §9.2.** Its output governs §6.3.
- **A second execution of either query is a second look** and must be disclosed
  in the result document as such, with its reason, in the manner of
  `docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`.
  It cannot move `rho` (§6.4), so there is no legitimate reason to want one
  except a transport failure — and that reason must be written down.
- **The windows do not move, ever, in response to a count** (§6.3).
- **Expiry 2026-09-25T00:00:00Z** (§9.2).

---

## 11. WHAT THIS DOES NOT ESTABLISH — drafted before the run

Written to survive being read by someone looking for the caveat that was left
out.

### 11.1 It does not establish that a single existing byte was reclaimed

**Zero were.** §B6.3, and §0.1 above. The file was 5.07 GB before ADR 0133 and
5.07 GB the instant after. A PASS is a statement about a **slope over a future
interval** and every sentence quoting it must name the interval.

### 11.2 It does not establish that the file will stop growing

The non-family term — ~141.0 MB/day at the last measured interval, dominated by
`odds_snapshots` — is untouched by ADR 0133, has **no retention rule**, is
"deliberately out of scope rather than forgotten"
(`backend/store/retention.py:53-55`), and is **not measured here**. A PASS moves
the growth from 326.6 to ~141 MB/day. It does not move it to zero, and 141
MB/day alone exhausts the 4 GB box's residency advantage in about two weeks
(§1.2).

### 11.3 It does not establish that the 4 GB box is sufficient

§1.2 establishes the opposite, by arithmetic, before the box is bought: no
achievable value of `rho` buys a billing month of >=50% residency. The box is a
stopgap of weeks.

### 11.4 It does not establish that residency is what binds the 74.8 s query

#55 Amendment 1's own caveat, reproduced because it is the one most likely to be
dropped: the 74.8 s query was `ladder_candidates`, **not** a `fair_prices` read.
Shrinking `fair_prices` growth frees cache *for* it; that mechanism is
**plausible rather than demonstrated**. Relax residency and the plan, IOPS or
the 25 s ceiling itself may bind. Nothing here tests that, and a PASS is not
evidence that the 503 stops.

### 11.5 It does not establish that ADR 0133 caused whatever `rho` shows — and the asymmetry is registered

Four things moved inside the post window besides the dedup:

| change | date | direction on `rho` |
|---|---|---|
| `totals` markets bought (ADR 0152) | 2026-09-14 | **up** (new keys) — excluded from `rho` by §3.4, but props/rungs interact |
| NFL regular season live; not live in the pre window | from ~09-10 | **up** (more fixtures, more keys) |
| ten named books replace regions (ADR 0155) | 2026-09-15 | **either** — a changed `books_used` payload forces inserts |
| `idx_fair_market_confirmed` (v37) | 2026-09-10 | none on a **row** count; would matter for a byte count |

**Two push `rho` up, so a PASS is a fortiori. A FAIL is NOT.** A FAIL is
consistent with "the dedup works and the book list churned", and §8.2 therefore
forbids a revert and fixes the five hypotheses in order. **This asymmetry is
registered now because a FAIL write-up would otherwise be free to pick the
flattering attribution.**

### 11.6 It does not run §B7's successor, and that is a refusal with a reason

§B7 asked for a registered measurement of the duplication **rate** — correctly
keyed, multiple days, at least one NFL Sunday. **Post-deploy that is impossible**
(§0.2). **Pre-deploy it is possible and pointless**: the decision it would have
authorised was taken on 2026-09-09, so running it now is an audit of a shipped
change, it authorises nothing, and it costs a full window-function scan over
millions of pre-deploy rows — the exact read §9.4 declines. **Stated as a
refusal rather than left as an omission**, so a later session does not read this
document as having forgotten it.

### 11.7 It does not establish anything about props

Excluded by §3.4 on a query-plan ground. The prop arm of the ladder may
duplicate at a completely different rate and nothing here would see it.

### 11.8 It does not establish the duplication rate on any particular day

`rho` is a ratio of two window means over `G_pre = 8` and `G_post = 7` days that
are **not independent replications** (§4). The per-day series is printed, but no
day carries a verdict, and no standard error exists for any of them.

### 11.9 Its byte context is not measured and decays

No `dbstat` read is taken (§9.4). Every byte figure in this document comes from
the two dated reads of §B2.1 — 2026-09-01T16:40Z and 2026-09-09T19:49Z — and
the second is already eight days old. **Re-run `scripts/inspect_live_db.py
db-sizes` before quoting a family or file size**, and note that it is itself a
full-file walk that belongs in its own run window. The `~3.5 GB cache on a 4 GB
box` figure is inherited from #55 Amendment 1 and is **unverified**; if it is
wrong the residency table in §1.2 moves, but §6.2(3) means the threshold does
not.

---

## 12. Status

**READY.** Every section is fixed. Nothing is left open on the grounds that we
will see what the data looks like.

Two things are conditional and both are stated as rules with numbers, not
judgements: the window boundaries resolve from the v36 deploy instant read in
P2 **before** any count (§3), and the clustering floor of §4 returns
INCONCLUSIVE below six post-deploy days rather than being relaxed.

**This is not §B7's successor registration.** §0.2 and §11.6 say why one can no
longer be written for the prospective dedup, and §0.1 says why the retrospective
one is a `DELETE` that §6 of the parent document has closed.

**Three bounds hold this run, all protocol rather than caveat:** the
preconditions (§9.1), the run window on the clock (§9.2), and the seeking
predicate on both queries plus the refusal to run `dbstat` (§9.3, §9.4).

**This file must be committed before either query is executed.** Amendments are
additive and dated, never edits — the pre-fix text stays readable as what was
actually registered on 2026-09-17.

---

## 13. Amendment slots, named and numbered before they are needed

### A1 — RESERVED: the resolved windows

**Status at registration: EMPTY.** Filled when P2 establishes the v36 deploy
instant, **before** `Q1` runs: the two resolved date ranges, `G_pre`, `G_post`,
and confirmation that §4's floor is met. Written as a dated amendment to this
file, not decided inside the result document.

### A2 — RESERVED: any second look, any reschedule, any third query

Named so each is visibly an amendment rather than a judgement call: a re-run of
`Q1` or `Q2` (§10), a reschedule after NOT RUN (§9.2), a third query including
any `dbstat` read (§9.4, P4), converting any §5.2 quantity into a test (§6.1),
or arming the `fair_prices` downsampler between now and the look (P1).

### A3 — RESERVED: the `odds_snapshots` growth term

**Status at registration: EMPTY, and deliberately so.** §11.2 names it as the
residual — ~141 MB/day, no retention rule, no owner — and this document measures
nothing about it. It is named here so that the naming is on the record and so
that a future session does not present it as a discovery. **Any retention
proposal against it is a new registration with its own destructive-rule
discipline**, not an amendment to this one.

---

**Quantifiers, weakened at registration time where it is free.** This document
says "over the post window", "at the last measured interval", "in the observed
windows", "to interval granularity". It contains **no** claim that the dedup
*always*, *never* or *structurally* behaves any way — including §7.1's
preservation property, which is scoped to one market on one day by §5.3 and
which §7.4 already qualifies. The one unqualified negative it does make is
§11.1's *"zero bytes were reclaimed"*, and that is not a generalisation: it is
arithmetic on an operation that issues no `DELETE`.
