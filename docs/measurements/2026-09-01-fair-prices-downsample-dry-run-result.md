# `fair_prices` downsample — dry-run result: **NOT WORTH ARMING**

Deciding run **2026-09-01**, against the live instance.
Registration: `docs/measurements/2026-09-01-preregistration-fair-prices-downsample.md`.

> **Two defects were found in the instrument that produced this run, and both
> are recorded here rather than quietly repaired.**
>
> 1. **P6 answered NO** on a race, not a deletion. Rehabilitated by **Amendment
>    1** to the registration, which was written **after** this run and **blind**
>    to every figure in it. §0 evaluates its four salvage conditions.
> 2. **T-MECH was computed backwards.** The harness reported the fraction D4
>    *keeps* under the label of the fraction it *removes*, so the first draft of
>    this file carried `VERDICT PREMISE REFUTED` — **the opposite of what the
>    run measured**. Corrected in `212b44b`. §4.
>
> The second was caught by an audit before this file entered the record, and the
> first was not caught by that instrument's own tests at all. Neither changes
> `estimated_freed_bytes`, which is what the verdict below rests on.

## Verdict

**This block is a summary and the registered order begins at §1.** §8 fixes the
order as P1–P6, the census counts, the per-`link_id` view, T-MECH, then
`estimated_freed_bytes` — *"read `n` before the effect size"* is the reason for
it, and the body below follows it exactly. The deviation is noted rather than
silently taken, because a summary that opens with two effect sizes is the thing
that rule exists to discourage.

    VERDICT   NOT WORTH ARMING

    T-MECH                  98.68%  against a 90.00% floor    PASS
    estimated_freed_bytes   36,039,175 B  against 322,800,000 B    FAIL

**The verdict holds at every look taken**, which is reported here rather than
left to the deciding run alone (§7 and the four-look table in §7 below):

    run 1  20:37Z  deciding    36,039,175 B   11.2% of threshold
    run 2  21:05Z  monitoring  36,043,030 B   11.2%
    run 3  ~21:5xZ monitoring  35,966,698 B   11.1%
    run 4  ~22:2xZ monitoring  36,004,882 B   11.2%

**T-MECH passes and the rule is still not worth arming, and those are two
separate findings.**

The supported statement is narrow and is stated in full here because the short
version is the most convenient sentence in this file: **D4 removes 98.68% of the
D1 ∧ D2 ∧ D3 population against a registered 90% floor, so T-MECH passes and the
PREMISE REFUTED branch is not taken.** That population is 4.10% of the table
(§4). It is *not* a finding that "the premise holds" of `fair_prices` generally —
§5 records a whole-table density roughly 8× different from the premise's figure,
so the premise's *number* does not describe this table even though its
*direction* is corroborated, more strongly whole-table (99.84%) than in the aged
slice.

The cut is not worth taking because there is almost nothing for it to reach:
**95.66% of `fair_prices` is younger than the 14-day window** (§5).

### Consequences, from §8's table, not chosen here

| | |
|---|---|
| **What is built** | nothing. The rule is not built further. |
| **What is killed** | `fair_prices` retention is **closed as an approach**. |
| **What the volume answer is** | an extend past the reached `auto_extend_size_limit`. **Already taken** — Joe extended the volume 5 GB → 10 GB on 2026-09-01 and raised the limit to 20 GB. §8 calls for a different ADR with a different author; the action it names is done, and no ADR is owed by this document. |

**This is not the PREMISE REFUTED branch and must not be read as it.** That
branch would have reopened §5 of `2026-09-01-the-volume-clock.md` and killed the
attribution of growth to intra-day re-observation. The first draft of this file
printed that branch. It is wrong: nothing here overturns that attribution, and
§4 corroborates it inside the population it was measured on.

---

## 0. Two instrument defects, and what each one does to this run

### 0.1 P6 — rehabilitated under Amendment 1

The deciding run answered **P6 = NO**: `COUNT(*)` before 3,786,454, after
3,786,848. The count went **up** by 394. A deletion moves it down, and the
harness opens the database `mode=ro`, so SQLite refuses every write on that
connection. The 394 rows are the live recorder inserting while the report ran.

The registered P6 required the two counts to be **equal**, which tests a property
of the world (did anything else write?) rather than the property P6 names (did
this instrument delete?). Amendment 1 §A3 is precise about the shape and this
file adopts its framing over the one used during the session: P6 tested a
**race**, not an impossibility. A report finishing between two recorder commits
would have answered YES. *That is worse rather than better — a check that passes
for no reason is not redeemed by also failing for no reason, and the passing case
is the more dangerous, because nobody audits a YES.*

**§A9's four salvage conditions:**

| # | condition | evaluation |
|---|---|---|
| 1 | P1–P5 all answered YES | **YES** — §1; only P6 answered NO |
| 2 | `after >= before` | **YES** — 3,786,848 ≥ 3,786,454 |
| 3 | P6b passes | **YES** — worked below |
| 4 | the result file records the rehabilitation | **this file** |

    delta               = 3,786,848 - 3,786,454              = 394 rows
    perturbation_bytes  = ceil(394 / 3,786,454 * 899,887,104) = 93,638
    gate                = max(93,638, 100,000)               = 100,000
    | est - threshold | = | 36,039,175 - 322,800,000 |       = 286,760,825

    286,760,825 > 100,000   ->   P6b PASSES, by 2,867x

**One of Amendment 1's own arguments does not survive, and neither did this
file's first replacement for it. Both are withdrawn.**

§A9 argues that a re-take would move the primary quantity "by a fraction of the
threshold that is plausibly of order one", against a defect moving it 0.029%, and
concludes *"the remedy is some three orders of magnitude larger than the
disease"* — the remedy "points uphill".

The first draft of this file replaced that with a measured drift of ~198,257
B/day, fitted from runs 1 and 2. **That was a rate through noise and it had the
wrong sign.** Four looks now exist:

    run 1 -> run 2     +3,855 B   (28 min)
    run 1 -> run 3    -72,477 B
    run 1 -> run 4    -34,293 B

The estimate **falls** as often as it rises, and run 4 fell while the table grew
by 31,680 rows. `estimated_freed_bytes` is `eligible / total × constant`, so it
tracks the eligible **fraction**, and while the table is dominated by fresh rows
that fraction declines even as the eligible count climbs.

So **neither the drift rate nor its sign is established at the hour scale**, and
no order-of-magnitude comparison between remedy and disease can be made in either
direction. Extrapolating a 28-minute window by ×51.4 is the artifact §9.3 refuses
with the exponent reversed, on a database whose own config records that *"a
growth measurement here must span >= 24 h or it measures the quiet part."*

**Better than either argument: the salvage-versus-re-take choice is now
empirically moot, and it resolves against §A9's stated direction.** §A9's own
fallback provides that if the salvage is rejected, the governing figure is *the
lesser* of the void run's and the re-take's. Run 4 **is** a re-take under the
corrected, deployed instrument, and it returns **36,004,882 — below** the
deciding run's 36,039,175. Both of §A9's paths therefore land on
`NOT WORTH ARMING`, and the re-take path lands *further* from the threshold. So
§A9's bullet 2 is disposed of entirely — not only its magnitude but its "the
remedy points uphill" direction — with no order-of-magnitude comparison needed
from anyone.

**Two distinct rulings must not be merged, and the first draft merged them.**
P6b's 2,867× margin is salvage **condition 3** — the test of whether *this run
decides at all*. The *choice* of salvage over re-take rested on §A9's bullets 1
and 3: the cross-table perturbation that a bare re-take does not close, and §7's
classification of any later number as monitoring. Both survive. Saying the ruling
"rests on the margin" answers the first question with the second one's evidence.

**This also falsifies a premise of §6, and in the direction that strengthens the
verdict.** §6 reasons that *"the eligible byte count is monotonically increasing
in wall-clock time … it therefore crosses with probability 1"*, and treats that
as a repeated-looks hazard needing a deadline. The registered **estimator** is
not monotone — three of the four looks are below the first. Re-running until the
threshold cleared was never an available abuse. §6 is byte-frozen and cannot be
edited, so this is recorded here and in Amendment 2.

**What the salvage does not repair.** §A6 establishes that P6b bounds the
`fair_prices` component **and nothing else**. S1 reads six tables and the live
runner writes to four of the others during the report — `recommendations`,
`closing_lines`, `odds_snapshots`, `event_links`. Their magnitude is unknown and
their sign is not fixed. A bare re-take would not close that either; only a
pinned read snapshot does, and §A12's correction landed after this run
(`93f6a86`) and is **verified working on live**: a subsequent monitoring run
reports `read snapshot: PINNED`, `delta +0`, and P6 = YES.

### 0.2 T-MECH — inverted, and the verdict was the opposite of the data

`backend/store/fair_price_downsample.py` assigned
`t_mech = day_survivors / d123_rows`. A **day survivor is the row D4 keeps** —
§4's deletable condition is *"it is **not** the newest row for its identity
within its own UTC day"*, and `_D123_SQL` selects `is_day_survivor` on exactly
that basis. So the field carried the **keep** fraction while its own docstring,
the harness label `of those, removed by D4`, and `verdict`'s
`< T_MECH_THRESHOLD` comparison all read it as the **remove** fraction.

    reported   1.32%  against a 90% floor   ->  PREMISE REFUTED
    actual    98.68%  against a 90% floor   ->  PASS

**The run's own output contradicted the reported figure, four lines apart, and
the check was one division.** Eligibility requires *failing* D4, so
`eligible_rows / d123_rows` is a lower bound on the removal rate:

    151,642 / 155,248 = 97.68%

D4 cannot remove 1.32% of a population 97.68% of which is already marked
deletable.

**Why nothing caught it.** Every `t_mech` assertion in the suite hand-set the
field on a `DownsamplePlan(...)` constructor and asserted the `verdict` property.
None ran `plan()` against rows and read the number back, so the statistic's
direction was verified by no data at all. Three tests now do, all confirmed red
against the old expression. Corrected in Python only — `t_mech` is derived
outside `REGISTERED_DELETABLE_SQL`, so §S1 is untouched and its byte-for-byte pin
still holds.

**The asymmetry is the thing to carry.** P6 failed *expensively* — it ended the
run — and earned a 700-line amendment written under a blinding protocol. T-MECH
failed *conveniently* — it ended the work — and nobody divided 151,642 by
155,248.

---

## 1. Prerequisites

    P1 readers still covered by D1/D2   YES  14 modules, all enumerated by F2
    P2 no second retention rule         YES  no other module deletes from fair_prices
    P3 closing_lines resolves           YES  3,223 rows reaching 450 distinct
                                             kalshi_markets.event_ticker
    P4 the rule is not already armed    YES  FAIR_PRICE_DOWNSAMPLE_ENABLED=(absent)
    P5 anchor computable for >=90%      YES  no commence_ms on 0.00% of the
                                             D1&D2&D3 rows (threshold 10.00%);
                                             those rows are KEPT
    P6 nothing was deleted              NO   COUNT(*) before 3,786,454,
                                             after 3,786,848   [rehabilitated,
                                             Amendment 1 §A4/§A9 — see §0.1]

P4 is worth reading twice: it is a direct read of the **deployed** environment
confirming the rule is disarmed on live, which is stronger than a config default
in the repo.

**P1's message is imprecise, and this file's first attempt to corroborate it was
wrong in the direction that mattered.**

`F2_KNOWN_READERS` holds **15** entries; the grep finds **14** files; F2's table
and prose name **8** — including `backend/engine.py`, which the grep does *not*
find. So *"all enumerated by F2"* conflates the harness constant with the
registration section it names.

The first draft asserted that "every mention in the excess files is a comment, a
migration list, or the rule itself, so no uncovered production reader exists."
**That is false.** `backend/store/publish.py:45` carries `"fair_prices"` in
`PUBLISHED_TABLES` — a whole-table SELECT to Parquet, unbounded in age, and
**not** reached through `recommendations.fair_price_id`, so **D2 does not cover
it**. The registration does handle it (F5: never run against live; D3 forbids
citing the lake), but that is an *argued exclusion*, not an absence — and the
difference is the whole content of a safety prerequisite.

Of the seven found-but-not-in-F2, six are inert — `config.py` (docstring),
`slate.py` (comment), `store/db.py` (migration column lists), `store/retention.py`
(prose), `store/schema.sql` (DDL), `store/fair_price_downsample.py` (the rule
itself). `store/publish.py` is the seventh and is a real reader.

P1's substantive answer stands at **YES** on the registration's own terms. It is
written out at this length because this is a **safety** prerequisite whose
allowlist was authored in the same sitting as the rule it guards — the
configuration in which such a list is least trustworthy — and because the first
attempt to check it independently got it wrong.

## 2. `n`, before any effect size

    total_rows                 3,786,454
    eligible_rows                151,642
    eligible_row_fraction          4.00%   (a census, not a sample:
                                            exactly zero sampling error)

    what each condition keeps, individually (overlapping, NOT additive)
      base_rows                      3,786,848
      kept_orphan_link                       0
      kept_by_d1_age                 3,622,414
      kept_by_d2_referenced             41,570
      kept_by_d3_unscored            2,888,702
      kept_by_d4_day_survivor            5,950
      kept_by_d5_anchor                  5,390
      kept_by_d6_newest                  3,342

**`total_rows` and `base_rows` differ by 394 within one run**, because `plan()`
issued nine unenclosed reads and the recorder wrote between them;
`eligible_row_fraction` divides by the earlier count. The effect is 0.01% and
changes nothing here, but it is the concrete instance of the defect §A12(4)
exists for, and it is named rather than left for a reader to notice.

## 3. The parts

    distinct link_id contributing        259
    largest single contributor         2.00%
      link_id 37584           3,034  2.00%
      link_id 37454           2,789  1.84%
      link_id 37581           2,717  1.79%
      link_id 36515           2,404  1.59%
      link_id 37848           2,298  1.52%
      link_id 36512           2,128  1.40%
      link_id 36721           2,079  1.37%
      link_id 35585           2,016  1.33%
      link_id 36713           1,919  1.27%
      link_id 36514           1,750  1.15%
      ... and 249 more

    top 10 = 15.26% of eligible_rows; 249 links share the remaining 84.74%

**Effective cluster count, since a largest-contributor share alone is one order
statistic.** Inverse-Herfindahl over the ten known shares plus the tail:

    G_eff = 189.4   with a uniform tail
    G_eff =  82.4   under maximum admissible tail skew
                    (73 further links at the 10th's 1.15%, remainder ~0)

against 259 nominal. **Only the 82.4 is a bound**; the 189.4 is a scenario, and
the conclusion is drawn from 82.4 alone. The bound uses only published
quantities: the tail total 84.74%, the ordering guarantee that no tail link
exceeds the 10th's 1.154%, and the 249-link count.

82.4 is **19.3× the CLV signal test's 4.26 — about 1.3 orders of magnitude, not
two**, which is what the first draft said. The conclusion is unaffected: no
concentration correction is applied.

**`CLAUDE.md`'s `G_eff` requirement does not formally bind here**, and the number
is printed anyway. §3 of the registration forecloses the inferential reading —
*"No row count in this measurement may be reported as an `n` for any inferential
purpose"* — so there is no estimator whose variance clusters can inflate. It is
reported because the comparison was invited, and an invited comparison should be
answered with a number rather than an adjective.

**What this view does not cover, which is where concentration would actually
bite.** The per-`link_id` view is over `eligible_rows`. The model assumption that
matters is §5's — *bytes per row are uniform across the table and both indexes* —
and that is false in a **known, group-structured** way: `books_used` is a JSON
array whose length varies with book count, and prop rows carry an
`outcome_description` that team rows do not. No per-group view of row width was
produced, and §9.2 correctly says nothing tests it. So the parts agree on the
quantity where concentration was least likely to matter, and are unmeasured where
the estimator's model actually lives.

## 4. T-MECH — does D4 do the work the premise claims? **Yes.**

    rows passing D1 & D2 & D3        155,248
    of those, removed by D4           98.68%   (threshold 90.00%)  PASS

    implied density                  ~75.8 rows per identity-day in this slice
    premise's implied figure         ~96 rows/day  ->  ~99% removal

**The premise is corroborated, to within 0.3 percentage points of its own implied
figure.** D4 collapses essentially everything it is shown.

Recovered by hand from the deciding run's own printed 1.32% as `1 − 0.0132 =
98.68% ± 0.005pp`, which is the precedent §A9 condition 3 already set for P6b. No
re-run supplied it, and §7 would classify a re-run as monitoring in any case.

**This is a statement about `d123_rows` and nothing wider.** That population is
**4.10%** of the table — rows aged past 14 days *and* unreferenced *and* whose
event carries a closing line. 95.9% of the rows making `fair_prices` large never
enter the denominator. No sentence in this file generalises from `d123` to the
table, and the first draft's *"whatever is making `fair_prices` large, it is not
dense intra-day re-observation"* was exactly that error — a fact about one
filtered slice promoted to a fact about the product, which is the shape
`CLAUDE.md` records for `/markets` being 99.8% `KXMVE`.

## 5. Why the estimate is small — the age split, which is the actual finding

    younger than 14 days   3,622,414   95.66%   <- never reaches the rule
    aged past 14 days        164,434    4.34%
      of those, in d123      155,248    94.4% of aged
        of those, eligible   151,642   97.68% of d123
    eligible / total                     4.00%

**There is almost no backlog for a 14-day rule to reach.** D4 works; the age
filter shows it 4.34% of the table. Two competing explanations both predicted a
small byte figure — "the cut does not collapse anything" and "there is nothing
aged to collapse" — and the separating observation is T-MECH *within* the aged
population, which was computed and read backwards. Corrected, it separates them
cleanly in favour of the second.

This sharpens the power check's §3 ("87.5% of remaining growth is unreachable")
into a **measured 95.66% of the existing table**, and it is the part of this run
that generalises.

**One anomaly, recorded rather than resolved.** `kept_by_d4_day_survivor` = 5,950
is the count of distinct identity-days over the whole table and
`kept_by_d6_newest` = 3,342 the count of distinct identities, giving

    whole-table density  3,786,848 / 5,950  =  636 rows per identity-day
    aged-slice density                      =  ~76 rows per identity-day
    premise                                 =  ~96 rows per identity-day
    days per identity    5,950 / 3,342      =  1.78

**The mechanism is not a mystery and the first draft was wrong to publish it as
one.** `backend/scheduler.py:276` sets `DEFAULT_FAST_INTERVAL_S = 15.0`: the loop
runs a quote pass every **15 seconds** while the actionable window is open, not
on a 900 s timer, and `backend/runner.py:3286`'s `run_quote_pass` writes
`fair_prices` rows. `fly.live.toml` already records that four in-play hours carry
99.51% of a day's growth. So:

    4 h in-play at 15 s   =  960 rows
    20 h at 900 s         =   80 rows
    potential             = 1,040 per identity-day   vs 636 observed

Right order. Publishing this as an open question would have sent a future session
to measure what `scheduler.py:276` already states. The premise's *"~100
candidates every 900s, so a market accumulates roughly 96 rows a day"*
(`backend/store/fair_price_downsample.py:17-19`) describes **one of two
cadences** — the slow one.

**What is genuinely open is the opposite of what the first draft asked.** The
whole-table density is explained. The unexplained figure is why the **aged slice
runs at ~76 rows per identity-day, below the premise's 96 rather than above it**,
on a table whose fast cadence is 15 seconds. That is a real question, it is
narrow, and it is the only part of this paragraph a future session should spend
anything on.

**Two cautions on the comparison itself.** The ~75.8 figure is
`d123_rows / day-survivors-within-d123`, not `d123_rows / identity-days-in-the-
aged-slice`: an identity-day whose survivor row is excluded by D2 contributes
rows but no survivor, so ~75.8 is biased **upward** and the two densities are not
the same estimator. And the useful restatement from the same column is that
**D4's whole-table removal rate is 99.84%** (1 − 5,950/3,786,848) against 98.68%
in the aged slice — so the premise's *direction* is corroborated more strongly
whole-table, while its ~96/day *number* describes the slow cadence only.

## 6. The estimate

    ESTIMATE 36,039,175 bytes   (uniform bytes/row across table + both indexes;
                                 see S5)
    family measured on live 2026-09-01: 899,887,104 bytes

    threshold 322,800,000 bytes = 2.00 days at 161.40 MB/day

36,039,175 is **11.2%** of the threshold — worth ~0.22 days of runway at the
headline rate.

**The durable form of the result is in the eligible fraction, not in bytes**,
because the threshold is denominated in the same units and the registration
prints them itself:

    threshold      322,800,000 / 899,887,104  =  35.87% of the family
    deciding run       151,642 / 3,786,454    =   4.00%
    factor short                                  8.96x

**The eligible fraction would have to be nine times what it is.** That statement
comes from the deciding run alone, it does not depend on
`FAIR_PRICE_FAMILY_BYTES` being the right constant, and it is stable across all
four looks — the fraction sat within 0.009 percentage points of 4.00% over about
two hours of live reads (§7). Restating the estimate as a share of the family
would merely repeat `eligible_row_fraction`; comparing it to the *threshold's*
share of the family is what makes the comparison say something.

Per §5 this is an **ESTIMATE** and carries the word. §9.4 governs: SQLite returns
freed pages to a free list, not to the OS, so this is an upper bound on
filesystem bytes recovered without a `VACUUM`, multiplied by an unmeasured
free-list coefficient in [0, 1] (§9.5).

**It is smaller than the `VACUUM` prize the volume clock puts at 90,931,200 bytes
(0.56 days), and that comparison is directional only.** Both quantities are soft
in different ways — this one by the free-list coefficient, that one by two
candidate mechanisms the volume clock says give opposite answers and which are
untested on this box. The ordering is safe to state; a ratio between them is not,
and the first draft's "less than half" claimed a precision neither number has.

## 7. Provenance

| | |
|---|---|
| deciding run | 2026-09-01, ~20:37Z, **duration ~28 min** |
| live `git_sha` | `d6bb7d2` |
| harness | `scripts/dry_run_fair_price_downsample.py`, `mode=ro`, snapshot **not** pinned |
| retention_days | 14 (the registered arming value; not a sensitivity sweep) |
| `/data/cockpit.db` | 2,413,142,016 B, read 21:14Z |

**§7's requirement that `db_kb` be recorded *at the instant* of the deciding run
is UNMET, and it is not load-bearing.** The reading above is ~9 minutes after the
run ended. Nothing in this file depends on it: `estimated_freed_bytes` multiplies
the eligible fraction by `FAIR_PRICE_FAMILY_BYTES = 899,887,104`, a constant §5
freezes deliberately so that the same eligible fraction cannot yield different
verdicts on different days. Saying only "adjacent, not simultaneous" would leave
a reader to wonder whether the verdict moves. It does not.

**The duration is ASSUMED, not derived, and the assumption is probably wrong.**
The harness printed no elapsed time on this run — the gap §A12 names. Run 2's
`before` (3,786,848) equals run 1's `after` exactly, but that establishes only
that **no recorder insert landed between run 1's last count and run 2's first
count**. Converting that to a duration needs the recorder's burst cadence, about
which §A6 says this registration has no opinion; at a 900 s interval it yields
only `duration > ~13 min`. The "~28 minutes" in the first draft assumed the runs
were contiguous.

The one *measured* comparable is **435.9 s (7.3 minutes)**, from a later
monitoring run under a pinned snapshot — 3.9× shorter than the assumed figure. A
still later run measured 643.1 s. So the deciding run's nine-snapshot spread is
bounded below at ~13 minutes and is otherwise unknown, and no number in this file
depends on it now that the drift rate has been withdrawn (§0.1).

**Three monitoring runs followed, and all three are reported with their
estimates.** §7 makes them monitoring that may not move the verdict; the deciding
run is the first one, per the rule and not by selection. They are reported in
full because the first draft of this file cited run 3 four times for the
operational facts that flattered it — `PINNED`, `delta +0`, `P6 = YES`, `435.9 s`
— and omitted its estimate, which is **below** the deciding run's. By this file's
own standard that is a selective report.

| run | when | harness state | estimate | vs run 1 |
|---|---|---|---|---|
| 1 | 20:37Z | pre-fix; no pin, `==`, inverted T-MECH | 36,039,175 | *deciding* |
| 2 | 21:05Z | pre-fix | 36,043,030 | +3,855 |
| 3 | ~21:5xZ | post-§A12 (`93f6a86`); pinned, 435.9 s | 35,966,698 | **−72,477** |
| 4 | ~22:2xZ | post-T-MECH fix (`212b44b`); pinned, 643.1 s | 36,004,882 | −34,293 |

Runs 3 and 4 report `P6 ... YES`, `read snapshot: PINNED`, `delta +0` and
`connection refuses writes: YES`. Run 4 prints `of those, removed by D4 98.69%`
and `VERDICT NOT WORTH ARMING` **directly**, independently reproducing the
verdict this file recomputed by hand from run 1's inverted output.

The spread across all four looks is 76,332 bytes, or 0.024% of the threshold, and
every look sits at 11.1–11.2% of it.

---

## The §6 decision rule, reproduced verbatim

## 6. The decision rule, with the multiplicity already counted

### How many cells are tested

**One.** The arming decision is evaluated at `RETENTION_DAYS = 14` and nowhere
else.

The dry-run **may** additionally be run at `RETENTION_DAYS in {7, 21, 28, 60}`
as a **sensitivity sweep** — registered here as a set so it cannot be extended
later. Every sweep value is labelled **SENSITIVITY — DELETES NOTHING — CANNOT
ARM** in the output. The multiplicity is 1 rather than 5 **by construction, and
the construction is that the arming value was named before any of the five was
computed** — not because the sweep is uninteresting. Five values at a naive
"pick the best" would be five chances at one threshold, which is the whole
mechanism this document exists to block.

### The decision rule, verbatim

> At `RETENTION_DAYS = 14`, on the live database, with
> `FAIR_PRICE_DOWNSAMPLE_ENABLED` absent or `false`, on the single deciding run
> defined in §7:
>
> - **If any of P1–P6 answers NO** — the dry-run does not run, or its result is
>   void if it already has, and this document is **amended** rather than worked
>   around.
> - **If T-MECH fails** — that is, if within the rows passing D1 ∧ D2 ∧ D3, the
>   D4 downsample removes **fewer than 90%** — the verdict is **PREMISE
>   REFUTED**. The "~96 intra-day re-observations per market" premise does not
>   describe this table, §5 of `2026-09-01-the-volume-clock.md` must be
>   reopened before anything is armed, and no arming proposal may be made on
>   this document.
> - **If `estimated_freed_bytes < 322,800,000`** — the verdict is **NOT WORTH
>   ARMING**. The rule is not deployed at `RETENTION_DAYS = 14` and **not at any
>   other value either**. The answer to the volume clock is an extend past the
>   reached `auto_extend_size_limit = "5GB"`, and that is written up whether or
>   not anyone likes it.
> - **If `estimated_freed_bytes >= 322,800,000` AND P1–P6 all YES AND T-MECH
>   holds** — the verdict is **ELIGIBLE TO PROPOSE ARMING**. That is a
>   proposal, not an arming.
>
> **No branch of this rule permits lowering `RETENTION_DAYS` in response to the
> number.** Reaching the threshold by shortening the window is the specific
> failure this document exists to prevent, and it is forbidden here by name. A
> shorter window may be adopted only by a written amendment to this document
> that states its reader-margin argument **without reference to any byte figure
> the dry-run produced.**

### The threshold, and why it is 322,800,000 bytes

Fixed in advance, from figures that were already published before any row was
counted:

```
  322,800,000 B  =  2.00 days of runway at the headline 161.40 MB/day
                 =  35.9% of the 899,887,104-byte fair_prices family
                 =  50.0% of the 646,230,016-byte fair_prices table
```

Two reasons, both independent of the eventual number:

1. **It must clear the free, non-destructive option by a clear margin.** §7 of
   the volume clock puts the `VACUUM` prize at 90,931,200 B = **0.56 days**, and
   judges it *"Worth recording that it is going; not worth a plan."* A rule that
   is **irreversible** and that **forecloses all sub-daily analysis forever**
   (§9.1) must beat a reversible, non-destructive option by more than a factor
   of one. 2.00 days is **3.55x** it.
2. **It must buy a decision-useful amount of time.** Two days is one clean
   second measurement day — which §9 of the volume clock names as the single
   cheapest improvement available, *"one day of waiting and would double the
   evidence"* — plus a deploy window.

### The repeated-looks hazard, and why the guard is a deadline rather than a boundary

The eligible byte count is **monotonically increasing** in wall-clock time: the
table only grows, and rows only get older. Against a fixed threshold it
therefore crosses **with probability 1**, eventually, whatever the truth about
the rule's worth is. Re-running the dry-run daily until it clears is not one
look; it is as many looks as there are days, and it always succeeds.

An always-valid confidence sequence is the wrong instrument here, because the
quantity has no sampling noise to correct for (§5) — it has a **drift**. The
correct guard for a monotone quantity is a **deadline**, and §7 is that
deadline. Restated for the audit: *the number that governs is the one from the
first dry-run taken on or after the implementation lands.* A later, larger
number is monitoring, not evidence.

### Arming, which this document does not authorise

- The rule ships **behind `FAIR_PRICE_DOWNSAMPLE_ENABLED`, defaulting to
  `false`**, with a **dry-run mode that deletes nothing** and reports the rows
  and estimated bytes it *would* free.
- **The dry-run is the only permitted source of the bytes figure.** No estimate
  derived any other way — from page counts, from `db-sizes` deltas, from a
  post-hoc `VACUUM`, from arithmetic on §5 of the volume clock — may be
  substituted for it or quoted alongside it as corroboration.
- **Arming is a separate, later decision. It requires a named human and an ADR,
  and it is NOT authorised by this registration.** A verdict of ELIGIBLE TO
  PROPOSE ARMING authorises writing that ADR and nothing else.
- **It must never be self-arming on a disk threshold.** `backend/store/volume.py`
  exposes `read_volume` (`:171`) and `classify(free_bytes)` (`:213`); **this
  document forbids wiring either of them to the deletion path.** An automatic
  destructive deletion fired by a disk alarm is a guard that goes off at the
  worst possible moment — under ENOSPC pressure, at the hour a slate is live,
  with nobody reading the output — and its failure mode is deleting the wrong
  rows fast. The disk alarm's job is to say the disk is filling. Deciding what
  to destroy is a human's.

---

---

## §9 reproduced verbatim, as §8 requires

## 9. What this cannot establish — drafted before the run

### 9.1 A downsampled `fair_prices` cannot support any analysis at sub-daily resolution, ever again

**This is the cost, it is permanent, and it is not recoverable by any later
decision.** For rows older than `RETENTION_DAYS`, the intra-day series is gone.

Named concretely, so it is not an abstraction:
`docs/measurements/2026-08-10-sharp-anchoring-census.py:177-191` walks **every
`h2h` `fair_prices` row** and matches each row's `computed_ms` to the odds-fetch
instant it actually consumed — *"for each fair_prices row, the odds instant it
read = MAX(fetched_ms) <= computed_ms for that odds_event_id"* — and reports
which of the stored instants the runner ever consumed. That is a **genuine
intra-day time series**, and it produced the 73.0% sharp-anchoring figure ADR
0021 §8 rests on. **It could not be re-run on a downsampled table for any period
older than `RETENTION_DAYS`**, because one row per identity per day cannot be
matched to ninety-six fetch instants.

Generalised: **any future question of the form "how did the consensus move
during the game-day" is foreclosed for rows older than `RETENTION_DAYS`.** That
includes line-movement questions, steam-move detection, the timing of when a
sharp book first moved, and any recomputation of the anchoring census on
historical data. The rule does not make those questions harder. It makes them
impossible.

### 9.2 It does not establish how many bytes will be freed

`estimated_freed_bytes` is a modelled quantity (§5) resting on a uniform
bytes-per-row assumption that nothing here tests. **The dry-run is the only
permitted source of that figure**, and even the dry-run's figure is an estimate
with the word ESTIMATE attached. The only *measured* byte figure would come from
a `VACUUM` after a real delete, which this document does not authorise.

### 9.3 It does not establish that `fair_prices` is the right thing to shrink

§5 of `docs/measurements/2026-09-01-the-volume-clock.md` is a **composition over
a 44.4 ± 1.0 hour window, not a rate.** Its own §9 says the residual *"is
defined as `file total - subtotal` and absorbs those two indexes plus schema
overhead, so there is no arrangement of the numbers under which it would fail to
close"* — `idx_fair_link` and `idx_fair_market_computed` were **not measured on
the earlier date at all.**

**The 64.4% figure is a share of that window's 181,645,312 organic bytes.** It
is **not** a per-day rate. If the share holds at the headline rate,
`fair_prices` contributes about **103.9 MB/day** of the 161.40 MB/day, and that
"if" is the whole content of the sentence. **The figure "117 MB/day" does not
exist**: 116,903,936 bytes is a 44.4-hour total, and dividing it by 1.85 days
reproduces exactly the pooled artifact §3 of that document refuses.

### 9.4 It does not establish that deleting rows moves free space at all — and this is the most important caveat here

SQLite returns freed pages to a **free list, not to the filesystem.**
`backend/store/retention.py:48-52` states it in the repo's own words: *"only
`VACUUM` gives space back to the OS."*

So **this rule may free 0 filesystem bytes.** Its entire effect may be to slow
future growth by letting new inserts land on reused pages instead of extending
the file — which is a real effect, and is not the same effect, and moves the
fill date by a different amount.

And the `VACUUM` escape hatch is not available as a backstop:
`docs/measurements/2026-09-01-the-volume-clock.md` §7 shows it is **untested on
this box**, that its two candidate mechanisms *"give opposite answers"*, and
that the prize is **90,931,200 bytes = 0.56 days** against a margin that closes
in 0.56 days — *"an option worth thirteen hours of runway may expire in thirteen
hours."*

**Any write-up of this rule that reports a byte figure without this paragraph
attached is reporting a number that may be entirely notional.**

### 9.5 It does not establish that the free list will revolve rather than accumulate

§5.2 and §9 of the volume clock call this **the largest single uncertainty in
the document**. Measured, it was *accumulating* at **39.7% of organic bytes**;
asserted at `backend/store/retention.py:48-52`, freed pages *are* reused and
*"the growth stops even without"* a `VACUUM`. **The measurement and the
assertion disagree, on the record, and n = 1 window cannot separate them.**

The consequence for this rule is multiplicative and unbounded downward: the
runway it buys is `estimated_freed_bytes` times a revolution coefficient in
[0, 1] that **this design cannot measure at all.** If the coefficient is 0, the
rule buys zero days however large the eligible set is.

### 9.6 n = 1 day on the rate that motivates the whole thing

Every date in the volume clock's §4 table is **one 24-hour window, one MLB
slate, one instrument**, and its rate is *"a floor rather than a centre."* The
honest bracket is **2026-09-14 to 2026-09-26** against a headline of
2026-09-17. The threshold in §6 is denominated in days at 161.40 MB/day and
inherits every bit of that uncertainty. It is not re-derived if the rate moves;
moving it requires an amendment, for the same reason `RETENTION_DAYS` does.

### 9.7 It does not establish that the rule is safe against readers added after 2026-09-01

F2 is an enumeration taken on one day. P1 re-takes it. Neither can protect
against a reader added between the dry-run and the arming, which is one more
reason arming is a separate ADR with a named human rather than a consequence of
this document.

---
