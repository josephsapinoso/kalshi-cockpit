# Pre-registration — the NCAAF sharp-anchor census, and the cut that separates "thin book" from "thin sport"

Written **2026-09-17**, before any row of the Saturday slate exists.

**Date note, so nobody reconciles it twice.** The authoring host's clock read
`2026-09-16` when this file was committed; the calendar day it was written for
and against is **Thursday 2026-09-17**. Where the two disagree, the written
date is the one that binds.

**Two dates, and they are not the same one — say which you mean.** The **slate**
is Saturday **2026-09-19** (budget day, 10:00Z floor); the **read** is taken
early Sunday **2026-09-20**, in the 07:00Z–11:00Z window §9.2 fixes, because
Saturday afternoon is when Joe is on the desk and a big live read is paid for by
his next tap. The result document is named for the slate.

Registered because `tasks/NEXT.md` open item 2 says the census **does not run
without a registration**, and names the reason: the registration must state
**in writing, beforehand, what changes on screen under each outcome**. That
requirement is discharged in §8 and §10 and nowhere else; a screen consequence
invented on Saturday against Saturday's numbers is exactly the thing this
document class exists to prevent.

This is a **census of two instruments**, not an estimate about a population.
Its job is narrow and is stated at the top so it cannot inflate:

1. **Verify the magnitude behind a decision already taken.** Joe chose option A
   on 2026-09-16; `frontend/src/components/AnchorBaseRate.tsx` shipped in
   `432cbb9`. The census does not re-open that choice (§8.1).
2. **Close one rival explanation, or fail to and say so.** `matchbook` returned
   on **3 of 57** NCAAF events (`team-bookmakers`, read 2026-09-16), so *"thin
   book"* explains the observed NCAAF deficit as well as *"thin sport"* does.
   §5 fixes the cut that separates them **before** Saturday.
3. **Feed ticket #54** — what the Picks screen should show — with evidence that
   may retire one of its options. §8.4 fixes what "a small fraction of NCAAF
   rows" means, in numbers, today. **It writes no screen consequence for Picks**:
   that screen's design is #54's, it is open, and §13 slot `A1` is reserved for
   his answer.

Three bounds hold this run, and each is a **protocol clause rather than a
caveat**: the exemption that authorises the split at all (§0.2), the clock
window that keeps the read away from Joe's Saturday slate (§9.2), and the row
bounds on the queries themselves (§9.4).

---

## 0. Standing before anything is read

### 0.1 Declared blindness — and it is PARTIAL, which matters

**Seen while writing this**, and this list is the honest one:

- `scripts/inspect_live_db.py` (registry entries and CLI flags for
  `sharp-anchor-census` and `team-bookmakers`; the module docstring's three
  census exemptions), `scripts/inspect_live_db_decisions.py`
  (`_SQL_SHARP_ANCHOR_CENSUS`, `_SQL_TEAM_BOOKMAKERS`,
  `_q_sharp_anchor_census`, `_q_team_bookmakers`, `_sharp_anchor_since_ms`,
  `_SHARP_ANCHOR_DEFAULT_DAYS`), `scripts/inspect_live_db_common.py`
  (`DEFAULT_ROW_CAP = 2000`, `DEFAULT_DAY_START_HOUR = 10`).
- `backend/runner.py:166` (`SHARP_BOOKS`), `backend/core/devig.py:280-289`
  (`selected = sharp or usable`), `backend/kalshi/discovery.py:238` (the
  league → `sport_key` map), `frontend/src/components/AnchorBaseRate.tsx`.
- `tasks/NEXT.md` twenty-fourth (continued) and twenty-sixth entries; GitHub
  ticket **#54** in full; `CLAUDE.md` measurement rules;
  `docs/measurements/2026-09-10-preregistration-recorded-fill-vs-venue-charge.md`
  (house format);
  `backend/store/fair_price_downsample.py` (retention, for §9.3).

**NOT blind, and this is declared rather than hidden.** The 2026-09-16 census
output over a two-day window (rows computed since 2026-09-14T02:59Z) is on the
record in `tasks/NEXT.md` and I have read it. I know that NCAAF `spreads` read
46/153 rows with links 23/46, `totals` 50/176 with links 25/50, and `h2h`
110/131 with links 55/12; I know NFL, MLB and WNBA cells too.

**The contamination this creates, and the guard against it.** Thresholds chosen
by someone who has seen a 0.30 and an 0.84 can be placed to make the answer come
out. The guard is that every threshold in §8 is a **round number placed between
the two observed values, not near either**, and each is justified by what it
means on the screen rather than by where the prior data sat:

- `0.50` means *"most rows on this screen have no sharp book behind them"* — a
  sentence, not a fitted cut.
- `0.95` means *"the block would render a full fraction on every line"* — the
  point at which a base-rate block is incapable of carrying information.
- `0.90` and `0.50` on book coverage (§5) mean *"the book was on nearly every
  fixture"* and *"the book was missing from more than half of them"*.

No threshold is set to a value observed on 2026-09-16, and none sits within 0.10
of one. A reader who thinks a threshold was tuned should check that claim
against this paragraph rather than against a later write-up.

**Not seen, not queried, not requested:** any Saturday 2026-09-19 row (none
exists), any Saturday fixture list, any Saturday book response, any
`anchored_on_sharp` value computed after 2026-09-16.

### 0.2 The exemption this runs under — named, because the default is REFUSAL

**A split on a decision-bearing flag is refused by default in this repo, and
that refusal is not a formality.** `CLAUDE.md` records the analogous case in
plain words: splitting the unsuppressed population by `anchored_on_sharp` and
reporting a rate in each is *"deliberately refused, not merely unrun"*, and
`scripts/inspect_live_db_decisions.py` declines it by design — *"a query
carrying a decision rule is not a dump, so that module emits the rows and no
aggregate"* (module docstring, `:11`; restated at `:185` inside
`_SQL_SHARP_ANCHOR_CENSUS`'s own comment, and the actionable-population refusal
sits at `:234`). **Running such a split needs a registration first, not a
volunteer.** This is that registration, and without this section the census
looks exactly like the thing the repo refuses.

**The authorising exemption, verified by reading it:**
`scripts/inspect_live_db.py:125` — *"The third exemption: `sharp-anchor-census`
is a per-bucket split, by `(league, market, anchored_on_sharp)`, which the rule
above would forbid. Same census argument — an exhaustive `COUNT(*)` over a
bounded window under three keys, no sample, no null, no standard error."* It is
the third of three, beside `clv-coverage` sections D and F and
`manual-orders-audit`, and it rests on the same argument each of those does.

**What the exemption does and does not cover — the distinction this
registration turns on.**

- It authorises the instrument to **emit the split**: both values of the flag
  as their own rows, so the denominator is always on the screen.
- It does **not** authorise the instrument to emit a **ratio**. The query prints
  none, and the name says `-census` rather than `-rate` for exactly that reason:
  it was drafted as `sharp-anchor-rate` and renamed, because a query whose name
  promises the one quantity it must not emit is a query someone eventually makes
  emit it.

**Therefore: `scripts/inspect_live_db*.py` is NOT MODIFIED by this measurement,
in any file, for any reason.** No ratio is added to it, no `--league` default is
changed, no column is added. The two derived ratios this design uses — `A`
(§6.1) and `cov` (§5.1) — are computed **in the registered write-up, from
printed counts, under a decision rule fixed in this document before the counts
exist.** That is the `clv-coverage` precedent verbatim: *"A ratio of the two is
still a derived quantity and is not printed here; if one is written down it must
carry the snapshot instant, the horizon, and the attribution."* Accordingly
**every `A` and every `cov` written down must carry the snapshot instant and the
window floor beside it** (§6.1, §9.2); one that does not is not a figure from
this measurement.

### 0.3 What class of thing this is

A **per-bucket split over an exhaustive, bounded window**, run under the
exemption §0.2 names. There is no sample,
no null hypothesis and no standard error, so no interval, p-value or
significance statement appears anywhere in this design or its write-up. The
failures the "not a measurement harness" rule protects against are not reachable
by counting rows that all exist.

What IS reachable, and what this document actually controls, is **selection**:
which cell gets headlined, which window gets quoted, which of two explanations
gets called the finding. §5, §6, §8 and §9 fix all four in advance.

---

## 1. THE POWER CHECK, which comes before everything else

### 1.1 The inferential question is not the binding one

Exhaustive counts over a fixed window cannot be underpowered in the usual sense:
every row in the window is read. So the standard question ("what effect is
detectable at this `n`?") has no purchase on the row shares in §6.

### 1.2 The binding power question is the CUT, and it has an `n` floor

The cut in §5 separates *thin book* from *thin sport* using `pinnacle`'s
fixture coverage on NCAAF. That quantity is a ratio of two integers printed by
`team-bookmakers`, and its **resolution is 1/E**, where `E` is the NCAAF fixture
count the window contains.

| `E` (NCAAF fixtures in window) | resolution of `cov` | can it separate 0.50 from 0.90? |
|---|---|---|
| 5 | 0.20 | No — one fixture moves it a fifth of the way across the whole range |
| 10 | 0.10 | Marginally, and one fixture is a fifth of the gap |
| **20** | **0.05** | **Yes — one fixture is an eighth of the gap** |
| 57 (the 2026-09-16 figure) | 0.018 | Comfortably |

**Registered floor: `E ≥ 20`.** Below it the cut is declared UNSEPARATED and
§8.2's verdict is not taken, whatever the coverage number looks like. This is
fixed now precisely because Saturday is the biggest slate of the week and the
temptation on the day will be to say "close enough".

**The registration does not assume the `n` it wants.** `E ≥ 20` may fail: the
window may catch a thin week, the vendor may return a short fixture list, the
budget cap may have truncated the day (`decide_sweeps` returns `fire=()` when
the 700 binds, and **every** sport stops until the next 10:00Z boundary). Those
are live possibilities and §8.6 gives the floor-failure branch its own screen
consequence rather than treating it as an accident.

### 1.3 Verdict on power

**READY as a census; the CUT is conditionally powered and its condition is
stated as a number, not as a judgement.** No credits are spent (both queries are
read-only SQL over data the recorder has already bought), so the cost of the run
is the page-cache cost in §9.4 and a session's attention — which is why the cut
being unresolvable is an acceptable outcome rather than a wasted one.

---

## 2. The claims, as things that could be false

Three claims, stated with direction. Each can come back negative and each has a
destination in §10 if it does.

**H1 — the magnitude behind the shipped component.**
On the Saturday window, the NCAAF `spreads` and `totals` cells are THIN as §6.3
defines it (anchored row share below 0.50 **and** anchored links below unanchored
links), while the NCAAF `h2h` cell is not.
*Direction: one-sided per cell, and the direction is inherited from structure,
not chosen.* `SHARP_BOOKS` has four members (`runner.py:166`), `betfair_ex_uk`
is not purchased, and `betfair_ex_eu` quotes `h2h` only — so `spreads` and
`totals` can anchor on **two** books where `h2h` can anchor on **three**. The
predicted direction of the h2h-vs-spreads gap is therefore partly mechanical
(§11.4), and H1 is registered as the claim that the gap is *large*, not that it
exists.

**H2 — the rival explanation is closed.**
The NCAAF deficit is not explained by `matchbook`'s absence, because `pinnacle`
was present on nearly every NCAAF fixture in the same window
(`cov(ncaaf, pinnacle) ≥ 0.90`) and anchoring still failed.
*Direction: two-sided and reported two-sided.* The opposite result —
`cov(ncaaf, pinnacle) < 0.50` — is a real finding about the feed and is written
up as such (§8.2, §10).
**Why the cut is drawn on `pinnacle` and not on `matchbook`:** `consensus_devig`
computes `selected = sharp or usable` (`devig.py:288-289`), so **one** sharp book
present at a rung is sufficient for `anchored_on_sharp`. `matchbook` at 3 of 57
therefore cannot, on its own, explain a deficit on a slate `pinnacle` covers.
This single logical step is the whole reason the cut works, and it is written
down before the data so it cannot be discovered afterwards in whichever form
suits the numbers.

**H3 — the ticket-#54 claim.**
On the Saturday window, the NCAAF `h2h` cell — the population Picks actually
renders, since every Picks row is the moneyline favourite — is **not** THIN.
*Direction: one-sided, and the falsifying direction is the informative one.* If
NCAAF `h2h` comes back THIN, #54's premise changes: the block on Picks would
carry real variation and option B ("leave Picks alone") loses its strongest
argument. §8.4 fixes that consequence now — as evidence on a ticket, not as a
screen change.

---

## 3. Population and exclusions

### 3.1 The census population

```
fair_prices f JOIN event_links e ON e.id = f.link_id
WHERE f.market IN ('h2h','spreads','totals')
  AND f.computed_ms >= <2026-09-19T10:00:00Z>
```

`e.league` is **Kalshi's own string** (`discovery.py:238`), not an Odds API
`sport_key`. The four live values are `Pro Baseball`, `NCAA Football`,
`Pro Basketball (W)`, `Pro Football`. An unrecognised `--league` returns nothing,
which reads identically to a league with no rows — which is why §9.1 runs the
**unfiltered** call and derives NCAAF from it, rather than trusting a filtered
call to have found the league.

### 3.2 The coverage population

```
odds_snapshots
WHERE commence_ms >= <2026-09-19T10:00:00Z>
  AND outcome_description IS NULL          -- team markets, not props
```

### 3.3 Exclusions, and why each is independent of the outcome

| # | Exclusion | Why it cannot reference the quantity measured |
|---|---|---|
| X1 | `market NOT IN ('h2h','spreads','totals')` | Fixed in the instrument's SQL before this registration existed; it is the set of markets this desk buys. Independent of anchoring. |
| X2 | `computed_ms < 2026-09-19T10:00Z` | A clock floor fixed by calendar, set before any row exists. It is the budget-day boundary (`DEFAULT_DAY_START_HOUR = 10`), not a boundary chosen to include or exclude rows. |
| X3 | `outcome_description IS NOT NULL` (coverage query) | Props, a different path that has returned 0 rows on every sport for a fortnight. The discriminator is a schema column, not a price. |
| X4 | Leagues other than NCAAF, for H1/H3 | Named in advance: **NCAA Football** only. The other leagues are **not excluded** — they are reported as registered comparators (§6.4), so "NCAAF is the worst" is a statement with the alternatives printed beside it. |

**No exclusion references `anchored_on_sharp`, a row share, a link count, or a
book's identity.** There is no rule below that removes a cell for being
inconvenient.

**X5 — the pre-declared refusal branch, on the combo-experiment precedent.**
If `E < 20` (§1.2), **the cut in §5 is not computed at all** and the write-up
reports `E` and stops on that question. The trigger is a fixture count fixed
here, so activating the refusal is a rule and not a judgement — the same shape
as the exclusion a prior combo experiment correctly declined to activate.

---

## 4. Unit of observation, and the clustering that is NOT available

### 4.1 The unit is the FIXTURE; the row is not an observation

A fixture (`event_links.id`, the `link_id`) contributes **one row per rung per
pass**, and the runner re-evaluates candidates every 900s. So `rows_n` is
`passes × rungs` and is not a count of opportunities. A single fixture re-priced
all day can dominate a cell: the 2026-09-16 read has NFL `spreads` at 902
unanchored rows over **17** links.

### 4.2 `links` DOES NOT PARTITION — the trap, named before it can be sprung

`links` is `COUNT(DISTINCT link_id)` computed **separately for each value of the
flag**, so a fixture with some anchored rungs and some unanchored ones is counted
in **both** rows. Therefore, registered as prohibitions:

- `links_anchored / (links_anchored + links_unanchored)` is **not a proportion**
  and may not be computed, printed or quoted.
- `links_anchored + links_unanchored` is **not a fixture count**; it is an upper
  bound. `max(links_anchored, links_unanchored)` is a lower bound. Both are
  printed as `F_hi` and `F_lo` and neither is called "the number of fixtures".
- "How many NCAAF fixtures had no sharp anchor anywhere" is **not answerable by
  this instrument** and no sentence resembling it may appear in the write-up.
  Answering it needs a query that does not exist, and building one is not part of
  this registration.

### 4.3 The largest-contributor share is UNOBTAINABLE here, and that changes the design

`CLAUDE.md` requires the largest contributor's share beside any aggregate. The
instrument emits no per-`link_id` breakdown and this registration does **not**
authorise adding one. So the rule is satisfied in the only way available: **no
verdict rests on a row share alone.** §6.3 requires the row share and the link
counts to point the same way, and a cell where they disagree returns **DISAGREE
— no verdict**, which is a reportable outcome with its own screen consequence
(§8.5). That is `CLAUDE.md`'s "a pooled number is not a finding until the parts
agree", implemented as a rule rather than as an aspiration.

---

## 5. The cut, fixed in advance — thin book vs thin sport

### 5.1 The quantities, defined so they can be computed from what is printed

From the `team-bookmakers` table, for sport `s` and book `b`:

```
events(s, b)   printed directly, per (sport_key, bookmaker)
E(s)         = MAX over all returned books of events(s, b)
cov(s, b)    = events(s, b) / E(s)
```

`E(s)` is a **lower bound on the fixture count**, not the fixture count: the
instrument prints no distinct-event total for a sport, and the best-covered book
may itself have missed a fixture. It is used anyway because it is computable from
the printed table, it can only make `cov` **larger**, and §5.2's book-thin branch
therefore cannot be triggered by the approximation — only the rung-thin branch
can, and §5.3 requires a second condition for that branch.

### 5.2 The three-way verdict, and it is exhaustive

Computed on `s = americanfootball_ncaaf`, `b = pinnacle`, and only if `E ≥ 20`:

| condition | verdict | what it means |
|---|---|---|
| `cov < 0.50` | **BOOK-THIN** | The one book that can anchor NCAAF spreads/totals was missing from more than half the fixtures. Presence is binding; "thin book" survives and the deficit is a **feed** fact, not a league fact. |
| `cov ≥ 0.90` **and** H1's cells are THIN | **RUNG-THIN** | The sharp book was on nearly every fixture and the anchor still failed. Presence is not binding; the loss is at the **rung** — Kalshi lists margins no single main line matches. "Thin book" is closed as the explanation. |
| anything else | **UNSEPARATED** | Both explanations survive. Reported as the cut failing, in those words. |

`0.50 ≤ cov < 0.90` falls into UNSEPARATED by construction, as does `cov ≥ 0.90`
with cells that are not THIN. **The middle band is a real outcome with a real
write-up (§10), not a gap to be argued across on the day.**

### 5.3 Why RUNG-THIN needs the second condition

`cov ≥ 0.90` alone says the book was there. It says nothing about anchoring. The
conjunction — book present on nearly every fixture **and** the cells still thin —
is the only configuration that rules the book out. Registering the conjunction
now prevents the Saturday reading of "`pinnacle` covered everything, so it's the
rungs" from being stated without checking that the cells are actually thin.

### 5.4 No price axis, and this is a deliberate departure

`CLAUDE.md` requires bucketing on the derived ask rather than the mid. **There is
no price bucket here at all.** Anchoring is a property of the input feed at a
rung; it is not a function of a price this desk would pay, and introducing a
price axis would manufacture bucket-edge freedom (the richest source of unearned
findings) for a quantity that has no price dependence in its definition. The
departure is registered so a later reader can tell a decision from an omission.

### 5.5 The comparator set, named now

`Pro Football` and `Pro Baseball`, each × `{h2h, spreads, totals}`. `Pro
Basketball (W)` is **named as a comparator and expected to fail the cell floor**
(§6.2) — it is listed here so that its absence from the results is a registered
expectation rather than a quiet drop.

---

## 6. The statistic, named as an estimator — and there is none

### 6.1 What is computed

Per `(league, market)` cell, from the two rows the census prints for that cell:

| quantity | form |
|---|---|
| `rows_anchored`, `rows_unanchored` | raw counts, printed |
| `A` = `rows_anchored / (rows_anchored + rows_unanchored)` | a **census share of the row population in the window**; not a proportion of fixtures, not an estimate of anything, no interval |
| `links_anchored`, `links_unanchored` | raw counts, printed, **never ratioed** (§4.2) |
| `F_lo` = `max(links_*)`, `F_hi` = sum | bounds on the fixture count, labelled as bounds |
| `first_ms`, `last_ms` | printed, per cell |

`A` is the **only** ratio computed on the census side. `cov` (§5.1) is the only
ratio computed on the coverage side. **No mean, no sd, no interval, no p-value,
no significance statement, at any `n`, ever.**

### 6.2 The cell floor — `n` before effect size, as a rule with a trigger

**A cell's share `A` may not be quoted, compared, or given a verdict unless**

```
F_lo >= 8      (at least eight distinct fixtures on the larger side)
AND rows_total >= 40
```

Both must hold. `F_lo ≥ 8` is the fixture floor: below it a single fixture's
re-pricing can carry the cell and §4.3 gives no way to see that it did.
`rows_total ≥ 40` is the row floor, and it is deliberately the weaker of the two
— rows are cheap and fixtures are not, so the fixture condition is the one that
binds.

**If a cell fails the floor**, it is printed with its counts and the words
**"below the registered cell floor — no verdict"**, and it takes no part in H1,
H2 or H3. It is not pooled with another cell to reach the floor: pooling `h2h`
into `spreads` to make an `n` is the exact move `AnchorBaseRate` was built to
refuse.

**If NCAAF `h2h` fails the floor**, H3 is unresolved and §8.4's #54 branch does
not fire — the ticket waits on Joe untouched. **If all three NCAAF cells fail the
floor**, the measurement returns NOT RUN (§8.6).

### 6.3 The cell verdict, requiring the parts to agree

| row share | link sign | verdict |
|---|---|---|
| `A < 0.50` | `links_anchored < links_unanchored` | **THIN** |
| `A >= 0.95` | `links_anchored > links_unanchored` | **SATURATED** |
| `0.50 <= A < 0.95` | either | **MIXED** |
| `A < 0.50` | `links_anchored >= links_unanchored` | **DISAGREE — no verdict** |
| `A >= 0.95` | `links_anchored <= links_unanchored` | **DISAGREE — no verdict** |

The link sign is an **ordinal comparison of two overlapping exhaustive counts**,
not a rate, and is described that way in the write-up. A cell can be in both
counts (§4.2); the sign is still meaningful because both counts are exhaustive
over the same window.

### 6.4 The form of the output — fixed, and exhaustive

- **Every cell the census returns is printed**, including the fully anchored
  ones and the ones below the floor. This inherits `AnchorBaseRate`'s own
  property: rendering only the thin ones is a warning that fires on bad news and
  stays quiet otherwise.
- **Ordering is `(league, market)` alphabetical — never by `A`, never by row
  count, never "worst first".** No top-N, no "the worst cell", no callout of a
  maximum. Selection on the max is the error a `measurement-skeptic` pass caught
  on 2026-09-16 and it is forbidden here by ordering rather than by intention.
- **Permitted columns, exhaustive:** `league`, `market`, `anchored_on_sharp`,
  `rows_n`, `links`, `first_ms`, `last_ms`, and the derived `A`, `F_lo`, `F_hi`,
  `verdict`. Nothing else.
- **Forbidden in the output:** any settled outcome, any closing line, any
  `clv_*` column, any P&L, any edge figure, any per-row price, any ranking of
  rows or games. The census reads `fair_prices` and `event_links` and joins
  nothing onward.

---

## 7. Counting the tests — multiplicity fixed before the run

**K = 10 verdicts, and the list is closed:**

| # | comparison |
|---|---|
| 1–3 | NCAAF × {`h2h`, `spreads`, `totals`} — §6.3 verdicts (primary) |
| 4–6 | Pro Football × {`h2h`, `spreads`, `totals`} — comparators |
| 7–9 | Pro Baseball × {`h2h`, `spreads`, `totals`} — comparators |
| 10 | `cov(ncaaf, pinnacle)` against §5.2's two thresholds (one verdict, not two) |

`Pro Basketball (W)` is expected to fail the cell floor and contributes no
verdict; if it passes, it is printed but is **not** added to K and carries no
verdict, because it was not registered as one.

**There is no familywise error rate to correct, and here is why that is not a
loophole.** Every verdict is a threshold applied to exhaustive counts. There is
no sampling distribution, so there is no probability that a cell crosses a
threshold "by chance" — the count is the count. Ten cells tested at two standard
errors would produce about **0.46** false findings from pure noise, and this
project has already produced a 20-point "finding" from data generated with no
edge in it; that arithmetic is the reason **no cell is converted into a test**.
If a successor wants a test, it needs a dated amendment stating the null before
computing anything once.

**What multiplicity DOES buy here is selection freedom, and it is controlled
by §6.4**: all ten are printed, in fixed order, whether or not any is
interesting, and the headline may name only the cells §8 names.

---

## 8. THE DECISION RULE, verbatim — and what changes on screen

> **8.1 The shipped component is NOT on trial, in either direction.**
> `AnchorBaseRate` (`432cbb9`) renders counts computed from the rows already on
> the Games slate. It needs no query, spends no credits, and cannot go stale.
> **No outcome of this census removes it, alters its grouping, or converts its
> counts to percentages.** Joe chose option A on 2026-09-16 and a census does not
> overturn an operator's preference about his own screen. A result that makes the
> block look unnecessary is a **question for Joe**, not a licence to unship
> (§8.5).
> **Screen consequence of §8.1 on the Games slate: none, under every
> outcome.**
>
> **8.2 The rival explanation — three branches, three consequences.**
> Computed only if `E >= 20` (§1.2, X5).
>
> - **RUNG-THIN** (`cov(ncaaf, pinnacle) >= 0.90` and NCAAF `spreads`/`totals`
>   THIN): "thin book" is closed. **Screen consequence: none.** The write-up
>   records that the deficit is structural at the rung and that buying more books
>   would not fix it. A stale justification is corrected in the same commit:
>   `AnchorBaseRate.tsx`'s docstring says the warning fires "on about seven rows
>   in ten", a figure from the 2026-09-16 two-day window; it is **re-stated with
>   the Saturday number and its window instant, or generalised to a range**, per
>   the standing rule that a justification decays toward reassurance.
> - **BOOK-THIN** (`cov(ncaaf, pinnacle) < 0.50`): the deficit is a **feed**
>   fact. **Screen consequence: none immediately.** Changing `ODDS_BOOKMAKERS` is
>   a money decision (ten named books, `ceil(books/10)` region-equivalents, and
>   every sharp book is EU-region) and is **Joe's call**. This branch therefore
>   **opens a new sub-issue of map #3 in the same session**, written into the
>   handoff in the one-sentence marker form that ends in that new ticket's
>   own number, per `CLAUDE.md`
>   workflow step 7. Without the ticket the question does not exist.
> - **UNSEPARATED** (anything else, including `E < 20`): **Screen consequence:
>   none.** The write-up says, in these words, that the registered cut did not
>   separate the two explanations and that both survive. It does not substitute
>   a different cut found on the day.
>
> **8.3 SCOPE — every screen consequence in this section is about the GAMES
> slate, and about no other screen.**
> The Games slate is the screen whose design is settled: Joe answered on
> 2026-09-16, `AnchorBaseRate` shipped in `432cbb9`, and the component's
> grouping, wording and counts-never-percentages rule are all decided. A screen
> consequence can be written for it because there is a decided design to leave
> alone or to annotate.
>
> **No screen consequence is written here for Picks, deliberately.** Picks is
> the subject of **open ticket #54**, which Joe has not answered. Writing a
> screen consequence for a screen whose design is an open question would be this
> document choosing the answer to #54 in advance — the same failure as choosing a
> bucket edge after seeing the data, run in the other direction. **The Picks
> consequence is deferred to a named, numbered amendment slot, `A1` (§13), which
> #54's answer fills in.** Until that slot is filled, **nothing ships on Picks,
> whatever this census returns.**
>
> **8.4 Ticket #54 — what "a small fraction" means, fixed here and not on
> Saturday, as EVIDENCE ONLY.**
> The Picks screen renders one row per game and that row is always the moneyline
> favourite, so the only cell that bears on #54 is **NCAAF `h2h`**. The pooled
> all-market NCAAF figure is **refused as a #54 input**: pooling is precisely
> what the shipped component was built to avoid, and a pooled NCAAF number
> describes neither market family.
>
> The three branches below produce a **comment on #54 and nothing else**. None
> of them ships, removes, rewords or reworks anything on any screen; none of
> them closes the ticket; none of them reassigns it.
>
> - **"A small fraction" = the NCAAF `h2h` cell returns THIN** (`A < 0.50` with
>   link agreement, §6.3), having passed the cell floor. Then Picks rows are
>   mostly unanchored and option **B** ("leave Picks alone") loses its strongest
>   argument. **This is the sense in which #54 may answer itself with evidence**
>   — and the number that decides it is `0.50`, fixed today, against counts that
>   do not yet exist. **Screen consequence: NONE. Nothing ships on Picks on this
>   evidence.** The wording — whether the line says `moneyline` out loud
>   (option A) or not (option C) — is the whole substance of the ticket and is
>   Joe's. The session posts the cell's counts to **#54**, marks the evidence
>   against option B, and leaves the ticket open and his.
> - **NCAAF `h2h` returns SATURATED** (`A >= 0.95`): the block on Picks would
>   render a full fraction on every line for this window and could carry no
>   variation — evidence **for** option B. **Screen consequence: NONE.** Counts
>   to **#54** as a comment; ticket stays open and his.
> - **NCAAF `h2h` returns MIXED, fails the cell floor, or DISAGREEs**: **#54 is
>   untouched** and the write-up says so. **Screen consequence: none.**
>
> **In every branch the Picks screen is unchanged on Saturday and remains
> unchanged until §13's slot `A1` is filled by his answer.**
>
> **8.5 The one outcome that raises a NEW question for Joe — and it is a
> GAMES-slate outcome.**
> If NCAAF `spreads` **and** `totals` both return **SATURATED or MIXED with
> `A >= 0.80`** — i.e. the Saturday slate contradicts the magnitude that
> motivated shipping the block — then the screen is carrying a block justified by
> a number the record no longer supports. That is a user-facing justification
> contradicting this repo's measured record, which `CLAUDE.md` workflow step 7
> makes a **question for Joe**: it **opens a sub-issue of map #3 in the same
> session**, named in the handoff in the one-sentence marker form that ends in
> that ticket's own number.
> **Screen consequence on the Games slate: none until he answers.** The block is
> not removed, not reworded and not weakened by a session acting alone (§8.1).
>
> **8.6 NOT RUN, and it is a real outcome.**
> If all three NCAAF cells fail the cell floor (§6.2), or the census returns no
> `NCAA Football` rows at all, the result is **NOT RUN** — written up as such,
> with the window instant, the row counts observed, and `sweep-log` checked for a
> refusal **before** anything is diagnosed. **Screen consequence: none.** It is
> not rescheduled to the following Saturday without a dated amendment (§9.2).
>
> **8.7 Nothing here moves money-touching code, the gate, or a cap.**
> The gate stays exactly where it is. `ORDERS_ARE_DRY_RUNS` stays `True`. No
> ranking, ordering or suppression is added to any screen on the strength of any
> number produced here — the anchor flag is a per-row fact and an ordering would
> be a claim. No `ODDS_BOOKMAKERS` or `ODDS_MARKETS` change is made by a session;
> §8.2's BOOK-THIN branch opens a ticket and stops. **And nothing here ships a
> Picks change**: that screen is #54's, and §13's slot `A1` is the only route to
> it.

**Summary of screen consequences — GAMES SLATE, which is the only screen this
document may speak for — including every outcome where nothing changes:**

| outcome | Games-slate consequence | Picks |
|---|---|---|
| RUNG-THIN | **Nothing.** Component docstring's stale magnitude re-stated with the new window and its instant. | unchanged — §13 `A1` |
| BOOK-THIN | **Nothing.** Opens a map #3 sub-issue for Joe, same session. | unchanged — §13 `A1` |
| UNSEPARATED (incl. `E < 20`) | **Nothing.** Write-up says the cut failed, in those words. | unchanged — §13 `A1` |
| NCAAF `h2h` THIN | **Nothing.** | unchanged. Evidence comment on **#54**; ticket stays open and his |
| NCAAF `h2h` SATURATED | **Nothing.** | unchanged. Evidence comment on **#54** recommending B |
| NCAAF `h2h` MIXED / floor-fail / DISAGREE | **Nothing.** | unchanged. #54 untouched |
| NCAAF `spreads` and `totals` both `A >= 0.80` | **Nothing until Joe answers.** Opens a map #3 sub-issue, same session. | unchanged — §13 `A1` |
| NOT RUN | **Nothing.** | unchanged |

**Read those columns.** Under **every** registered outcome both screens change
nothing on Saturday. That is not an oversight and it is the honest finding about
this measurement's decision-relevance: it **verifies a magnitude and closes an
explanation**, and both of its live decision branches end at a ticket for Joe
rather than at a build. If that is not worth a session's attention, the time to
say so is now — before the run — and this paragraph exists so that it can be
said now. What the run buys is a corrected justification under the shipped
component, a closed rival explanation, and evidence on a ticket that is currently
waiting on him with none.

---

## 9. The stopping rule and the protocol

### 9.1 The protocol — four queries, and no fifth

Exactly four live reads, in this order, all read-only, all bounded:

```
1.  sharp-anchor-census --since 20260919
2.  sharp-anchor-census --since 20260919 --league "NCAA Football"
3.  team-bookmakers     --since 20260919
4.  team-bookmakers     --since 20260919 --sport americanfootball_ncaaf
```

Query 1 runs **before** query 2 deliberately: an unrecognised `--league` returns
no rows, which reads identically to a league with none, so the unfiltered call is
what establishes that `NCAA Football` is present at all. Queries 2 and 4 are
narrowings of a known answer, not discoveries.

**`--since 20260919` is mandatory and explicit on all four.** The defaults (two
days for the census, seven for the books) are lookbacks, not this Saturday, and a
default that happens to cover the slate is still an unregistered window. A
malformed `--since` is refused by the instrument rather than ignored — a silently
dropped bound is an unbounded query wearing a flag.

**All four run inside the clock window §9.2 fixes, and nowhere else.** The
instrument is not modified to support any of this (§0.2).

### 9.2 THE RUN WINDOW — a clock bound, not only a row bound, and a protocol clause

**The hazard, stated first because it is the one that can do real damage.** A
large live read evicts the page cache, and the desk pays for it on the **next**
tap, minutes later. That is not a worry, it is a production incident already on
this record: on 2026-09-10 `/api/parlays` returned 503 `read_budget_exceeded`
with `ladder_candidates` at **74.8 s cold**, three times the 25 s budget, after a
page-cache eviction. The box is 2 GB against a 5.43 GB database with ~27%
maximum residency — **structural and unfixed**.

**Saturday is an NCAAF betting day and Joe will be on the desk.** A census run
on Saturday afternoon is a live candidate to 503 his positions screen mid-game —
the measurement causing the exact failure it sits next to. Proximity **in time**
to his use is the hazard, not concurrency: the read can complete cleanly and the
damage still lands on his next tap. **A row bound does not address this. Only a
clock bound does.**

**THE RUN WINDOW, fixed: `2026-09-20T07:00Z` to `2026-09-20T11:00Z`.**
One look, taken once inside it, snapshot instant printed beside every count.

- **After the last NCAAF game settles, not before the first kicks off.** The
  alternative safe slot — before Saturday's first kickoff, roughly 10:00Z–15:00Z
  — is rejected on the merits: the window floor is 2026-09-19T10:00Z, so a read
  at 15:00Z would contain a few hours of pricing and almost none of the slate.
  It would be safe and worthless. `07:00Z` Sunday is after the west-coast night
  games have commenced and settled, and it captures the whole day.
- **It is dead time on both sides of it.** 07:00Z–11:00Z Sunday is roughly
  3am–7am US Eastern: NCAAF is done, and the first NFL kickoff is ~17:00Z, six
  hours after the ceiling. Neither slate is being watched.
- **The ceiling exists so "wait a bit longer and re-read" is not available.** A
  window that can be extended is a window chosen against the data.
- **Defer-within-window, then stop.** If the desk shows attention inside the
  window — a live visit, a tab open — the look waits for the next quiet point
  **inside** the window. It does not push past 11:00Z.
- **If no look is taken inside the window, the measurement is NOT RUN** (§8.6)
  and is **not** silently rescheduled to the following Saturday. Rescheduling is
  a fresh look at a fresh population and requires a **dated amendment**
  recording that the first window was missed and that nothing from it was seen.
- **No part of this measurement runs on 2026-09-19 at all.** Not a rehearsal,
  not a row count, not a "quick check that the league string is right". The
  league string is checked by query 1 inside the window (§9.1).

**Comparator caveat this window creates, registered now.** A read at 07:00Z
Sunday over a floor of 10:00Z Saturday contains NFL rows priced ahead of NFL
Sunday alongside the NCAAF rows. The comparator cells (§5.5) are therefore a
mixture of "a completed NCAAF day" and "an NFL day not yet played", and the
comparison is between leagues, **not** between equivalent points in a fixture's
life.

**This is not a monitor and it does not accrue.** No threshold here is
re-evaluated as a database grows. A threshold re-evaluated on every request
against an accumulating record is not one look but thousands, and under a true
zero it crosses eventually with probability 1 — measured in this project at
13.7%, and that is a floor. Nothing in this design has that shape, and any
successor that wants a repeated look needs an always-valid boundary registered
before the first look.

**A second run of any of the four queries is a second look** and must be
disclosed in the result document as such, with the reason, in the manner of
`docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`.

### 9.3 Retention — the evidence is not perishable inside this window

`backend/store/fair_price_downsample.py` is **off, and dry by default**, and its
registered rule deletes only rows older than 14 days (D1), keeping the newest row
per identity per UTC day (D4) regardless. A look within 24 hours of the window is
therefore reading an untouched population. **One precondition, checked before the
look and recorded:** confirm the downsampler has not been armed since this file
was written. If it has, that is an amendment, not a footnote.

### 9.4 Row bounding — the second half of the protocol, not a caveat

**A full-table read on live evicts the page cache and costs the desk ~75 s per
query afterwards.** This is measured, not feared: `/api/parlays` returned 503
`read_budget_exceeded` in production on 2026-09-10 with `ladder_candidates` at
**74.8 s cold**, three times the 25 s budget, on a 2 GB box against a 5.43 GB
database with ~27% maximum page-cache residency. The condition is structural and
unfixed.

The bounds, and each is a property of the query rather than an intention:

- **The census SQL seeks rather than scans.** `market IN ('h2h','spreads',
  'totals')` with `computed_ms >= :since` uses `idx_fair_market_computed`, which
  leads with `market` — `SEARCH f USING INDEX idx_fair_market_computed (market=?
  AND computed_ms>?)`, measured, not assumed. The `--since` floor is what keeps
  the seek short; **omitting it is what turns this into the full-table read that
  costs the desk 75 s**, which is why §9.1 makes it mandatory.
- **The coverage SQL is bounded on `commence_ms >= :since`.**
- **Output is capped** at `--limit`, default `DEFAULT_ROW_CAP = 2000`. The census
  `GROUP BY` yields at most `leagues × 3 markets × 2 flags` ≈ 24 rows, so the cap
  cannot bind and is not relied on as the bound. `team-bookmakers` yields at most
  `sports × 10 books`.
- **Four queries total.** No exploratory fifth, no `--league` sweep over the
  other three leagues (query 1 already contains them), no unfiltered call without
  `--since`.
- **Run in one read-only session**, and record the UTC instant of each.
- **Inside the run window of §9.2, and nowhere else.** The row bounds above keep
  the read small; the clock bound keeps it away from his slate. Both are
  required and neither substitutes for the other.

---

## 10. What would falsify this, and where the negative goes

**Destination, fixed now, and written whichever way it comes out:**
`docs/measurements/2026-09-19-sharp-anchor-census-ncaaf-result.md` — named for
the **slate**, 2026-09-19, though the read is taken on 2026-09-20 (§9.2) —
linked from `tasks/NEXT.md` in the same commit.

**The NOT RUN and UNSEPARATED branches go to the same file.** A pre-registration
whose negative branch has no destination produces a negative result that quietly
never gets written; this one has a filename before it has a number.

| outcome | what is written | what is built | what is killed |
|---|---|---|---|
| RUNG-THIN, NCAAF cells THIN | All ten verdicts in fixed order; the cut's verdict; the stale docstring magnitude corrected | Nothing | "Thin book" as an explanation of the NCAAF deficit |
| BOOK-THIN | All ten verdicts; `cov` per book per sport | Nothing. A map #3 sub-issue for Joe | Nothing — the book-list question becomes his |
| UNSEPARATED | All ten verdicts, and the sentence "the registered cut did not separate the two explanations" | Nothing | Nothing. The rival explanation stays open, by name |
| `E < 20` | `E`, and the refusal (X5) | Nothing | The cut, this run |
| NCAAF `h2h` THIN | The cell's counts, posted to #54 | Nothing | Option B's strongest argument |
| NCAAF `h2h` SATURATED | The cell's counts, posted to #54 | Nothing | Option A's premise on Picks |
| NCAAF `spreads`+`totals` both `A >= 0.80` | The contradiction, first | Nothing. A map #3 sub-issue for Joe | Nothing until he answers |
| NOT RUN | The window, the counts seen, `sweep-log` checked | Nothing | Nothing |

**Both live decision branches end at a ticket, not at a build**, and §8 says so
in advance rather than discovering it afterwards.

---

## 11. WHAT THIS DOES NOT ESTABLISH

Drafted before the run, and deliberately including the items that would overturn
the result rather than only the survivable ones.

1. **Nothing about WHY a row is unanchored.** `anchored_on_sharp` records that no
   purchased sharp book contributed to that rung. It does not distinguish a book
   that quoted a different line, quoted one side, failed the devig, or never
   returned. `team-bookmakers` is the input side and is a strict **upper bound**
   on anchoring, never a lower one — four gaps separate them and every one runs
   the same way.
2. **Nothing that a rate over `rows_n` would mean.** `rows_n` is `passes ×
   rungs`. `A` is a share of a row population in a window, not a rate of
   opportunity, not a probability, and not a statement about any fixture.
3. **`links` does not partition** (§4.2). No fixture-level proportion is
   computed, quoted or implied anywhere.
4. **Nothing about market difficulty, and this is the caveat most likely to be
   omitted.** `h2h` can anchor on three purchased sharp books; `spreads` and
   `totals` can anchor on **two**, because `betfair_ex_eu` quotes `h2h` only and
   `betfair_ex_uk` is not bought. **Part of any h2h-vs-spreads gap is therefore
   mechanical book availability, not a property of spread markets**, and the
   census cannot apportion the two. A write-up that reads the gap as "spreads are
   harder" is wrong on this registration's own terms.
5. **Nothing about the horizon, and the second-horizon rule cannot be satisfied
   here.** `CLAUDE.md` requires re-running at a second horizon; the instrument
   emits no horizon split and this registration does not authorise building one.
   `A` is therefore a **mixture over every pass in the window**, near and far
   from commence, and **may not be read as "the anchor rate at the moment Joe
   looks."** The rule is unmet, deliberately, and stated rather than quietly
   skipped.
6. **The census population is NOT the component's population.**
   `AnchorBaseRate` counts the rows currently on the Games slate — the newest
   recommendation per market. The census counts every `fair_prices` row in a
   window. **The two numbers can differ and neither validates the other's
   arithmetic.** This census verifies a magnitude; it does not verify a rendered
   figure, and no sentence may claim it does.
7. **Nothing about whether an unanchored price is WRONG.** The fallback is the
   full usable book set — a worse consensus, not a missing one. This counts how
   often the fallback fired.
8. **Nothing about price quality or about the edge.** Presence and anchoring,
   not correctness. `beta = -0.141`; nothing here reopens the signal question and
   nothing here may be used to rank rows.
9. **Nothing about a league or book absent from the output.** Three causes are
   indistinguishable: the book quotes nothing on that sport, the sport had no
   fixture in the window, or the key is misspelled and was dropped while still
   costing one of the ten slots.
10. **Nothing about a week other than this one.** One Saturday, one window. A
    slate is not a season, and the budget cap can truncate a day: when the 700
    binds, `decide_sweeps` returns `fire=()` and every sport stops until the next
    10:00Z boundary. A thin window may be a thin purchase rather than a thin
    slate, and `sweep-log` is checked before anything is diagnosed.
11. **Nothing about `E` being the fixture count.** It is a lower bound derived
    from the best-covered book (§5.1), so `cov` is an **upper** bound on
    coverage.
12. **Nothing that authorises a change to money-touching code, the gate, a cap,
    a ranking, or the book list** (§8.6).

---

## 12. Status

**READY.** Every section is fixed. Nothing is left open on the grounds that we
will see what the data looks like.

One conditional, and it is stated as a number rather than as a judgement: the
**cut** in §5 is computed only if `E >= 20` (§1.2, X5); below that floor it
returns UNSEPARATED and the run says so. That is a registered branch, not an
underspecification.

One slot is **deliberately empty and named**: `A1` (§13), the Picks screen
consequence, which belongs to ticket #54 and to Joe. An empty named slot is not
an underspecification either — it is the one place in this document where the
answer is genuinely not ours to fix, and leaving it unnamed is what would have
let a session choose it on Saturday against Saturday's numbers.

**Three bounds, not one, and all three are protocol rather than caveat:** the
authorising exemption (§0.2), the run window on the clock (§9.2), and the row
bounds on the queries (§9.4).

**This file must be committed before any of the four queries is executed.**
Amendments are additive and dated, never edits — the pre-fix text stays readable
as what was actually registered on 2026-09-17.

---

## 13. Amendment slots, named and numbered before they are needed

Amendments to this file are **additive and dated, never edits**. Two slots are
reserved and named now, so that the thing each would decide cannot be decided
silently inside a result document.

### A1 — RESERVED: the Picks screen consequence, filled by ticket #54's answer

**Status at registration: EMPTY, and deliberately so.** §8.3 scopes every screen
consequence in this document to the Games slate. Picks has none, because its
design is an open question Joe has not answered.

**What fills this slot:** Joe's answer to **#54** — option A (block on Picks,
grouped by league, saying `moneyline` out loud), B (leave Picks alone), or C
(block with no market-family wording). When he answers, `A1` is written as a
dated amendment stating, in advance of any build, what the Picks screen renders
and what this census's NCAAF `h2h` counts do and do not license about it.

**Until `A1` is written, nothing ships on Picks**, regardless of what the census
returns, and §8.4's branches produce a comment on #54 and nothing else.

**If he answers before Saturday**, `A1` is written before the run and the run
proceeds under it. **If he answers after**, `A1` is written then and cites the
result document rather than being folded back into it. Either way the Picks
consequence is fixed in writing before a screen moves.

### A2 — RESERVED: any second look, any reschedule, any fifth query

Named so that each is visibly an amendment rather than a judgement call:
a re-run of any of the four queries (§9.2), a reschedule after NOT RUN (§8.6),
a fifth query (§9.1), converting any cell into a statistical test (§7), adding a
cell to `K` (§7), or arming the `fair_prices` downsampler between now and the
look (§9.3).

---

**Quantifiers, weakened at registration time where it is free.** This document
says "on this window", "in the observed window", "cannot be apportioned by this
instrument". It contains no claim that anchoring *always*, *never*, or
*structurally* behaves any way — including the structural-sounding book-count
fact in §11.4, which is scoped to the books this instance currently purchases and
would change the day `ODDS_BOOKMAKERS` moves.
