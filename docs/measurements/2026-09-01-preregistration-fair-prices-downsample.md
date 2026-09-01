# Pre-registration — a `fair_prices` retention downsample: which rows may be destroyed

**Registered 2026-09-01. No row of the live `fair_prices` table has been
inspected, counted, aged or sized in the course of writing this document.**

---

## Why this is pre-registered at all, when it is not a statistical estimate

Nothing here estimates a parameter. This registration fixes a **destructive data
rule** — a `DELETE` against the largest table in the live database — and it is
pre-registered for the reason a rule is harder to pre-register than an estimate,
not easier.

A retention rule destroys rows a future measurement would have read. Once the
byte figures are on the screen, every knob in the rule acquires a direction:
`RETENTION_DAYS` gets shorter, the evidence join gets looser, the horizon set
gets smaller, and each of those moves is individually defensible. The document
that stops that is the one written before anyone has seen which rows are
inconvenient.

The specific freedom being removed, named so it can be checked against the
write-up: **the temptation to lower `RETENTION_DAYS` until the number clears the
threshold.** §6 forbids it by name. If the eventual write-up reports a number at
any window other than 14 days as its deciding figure, this registration was
violated.

The second freedom being removed: **re-running the dry-run until it clears.** The
eligible byte count grows monotonically with the table. Against a fixed
threshold it crosses eventually with probability 1, whatever the truth is. §7
makes the deciding run a single named run.

---

## Prerequisites — checked before the dry-run is permitted to run

Each is a yes/no answered from the live database. **If any is NO, the dry-run
does not run and this document is amended rather than worked around.**

- **P1. Every production reader of `fair_prices` is still either
  bounded-window or reaches the table only through `recommendations.fair_price_id`.**
  Re-run the enumeration in F2 (a `grep` for `fair_prices` across `backend/`)
  at the moment the dry-run runs, not at the moment this was written. If a
  reader exists that is neither, D2 no longer protects it and this document is
  amended. The enumeration at registration is F2; it is a fact about
  2026-09-01, not a promise about the day the rule runs.
- **P2. `fair_prices` still has no retention rule.** `backend/store/retention.py`
  holds no `DELETE FROM fair_prices` and no other module does either. If one has
  landed since 2026-09-01, this document is **superseded**, not layered on: two
  retention rules against one table interact, and the interaction is not
  registered here.
- **P3. `closing_lines` is non-empty and D3's join resolves for at least one
  row.** Report `COUNT(*) FROM closing_lines` and the number of distinct
  `kalshi_markets.event_ticker` values it reaches, **beside** the eligible
  count, on every run. If `closing_lines` were empty, D3 would keep every row
  and the dry-run would report 0 eligible — and 0 from an empty join is not a
  finding about the age distribution. Reporting it as one is the failure this
  prerequisite exists to catch.
- **P4. `FAIR_PRICE_DOWNSAMPLE_ENABLED` is absent or `false` on the box the
  dry-run reads.** A dry-run taken where the rule is already armed measures a
  table that has already been cut, and reports a smaller eligible set than the
  one the decision is about.
- **P5. D5's anchor is computable for at least 90% of the rows that pass
  D1 ∧ D2 ∧ D3.** Report the fraction of those rows whose `odds_event_id` has
  no `odds_snapshots` row and therefore no `commence_ms`. **Those rows are
  KEPT, never deleted** — an unreadable anchor resolves to *keep*, never to
  *delete*, which is this repo's `None`-never-`0` convention applied to a
  destructive rule. If that fraction exceeds 0.10, the dry-run is reported and
  **the rule is not armed at any value**, because the keep set would then be
  dominated by a join failure rather than by the registered rule, and nobody
  could tell the two apart from the output.
- **P6. The dry-run deletes nothing, verified rather than asserted.**
  `SELECT COUNT(*) FROM fair_prices` is taken immediately before and
  immediately after the dry-run and printed as two numbers. Equal is the pass
  condition. A dry-run that only *claims* to be read-only is decoration.

---

## 1. The question, as a claim that could be false

**Primary claim, one-sided, both conjuncts:**

> Applying D1..D6 (§4) to the live `fair_prices` table at
> `RETENTION_DAYS = 14`
>
> **(a) frees at least 322,800,000 estimated bytes** — 2.00 days of runway at
> the volume clock's headline 161.40 MB/day — **and**
>
> **(b) deletes no row that any production reader enumerated in F2 can reach.**

Both conjuncts can come back false, and they fail for different reasons and to
different destinations.

- **(a) is the worthwhileness claim.** Its direction is fixed here as *at
  least*. It is one-sided deliberately: a two-sided reading lets a number below
  the threshold be written up as "it still frees something", which is how a
  destructive rule gets armed on a figure that would not have justified writing
  it.
- **(b) is the safety claim.** It is not a statistical claim at all — it is an
  enumeration (F2) plus a query (S1) plus a prerequisite that re-checks the
  enumeration (P1). It is falsified by finding one reader that D2 does not
  cover, and one is enough.

**What this claim is not.** It is not "the volume will not fill." It is not
"`fair_prices` is the right table to cut" (§9.3). It is not "bytes will be
returned to the filesystem" (§9.4, and that is the caveat that matters most).

---

## 2. The population, and the exclusions

**Population: every row of `fair_prices` on the live database at the instant
the dry-run's read transaction opens.** No sampling, no time window, no market
restriction, no sport restriction. Every row is *considered*; D1..D6 decide.

**Exclusions from the population: none.** That is deliberate and it is the
point. This document has no exclusion rule of the ordinary kind, because every
exclusion a retention rule could plausibly want — "skip the markets that grew
most", "skip the days that are cheap to keep", "start with the biggest rows" —
is an exclusion that references the quantity being measured. Stated flatly so
it can be checked:

> **No condition in D1..D6 references how many bytes a row occupies, how much
> space its deletion would free, which market or sport or link is largest, or
> any figure the dry-run produces.** Every condition is a fact about the row's
> age, its downstream references, or its position within its own identity's
> series. All six were fixed before any of them was evaluated against live.

**Tables out of scope, named so their absence is a decision rather than an
oversight** — this is the exact failure `backend/store/retention.py:53-55`
committed against `fair_prices` itself (F1): `odds_snapshots`,
`recommendations`, `closing_lines`, `event_links`, `kalshi_events`,
`kalshi_markets`, `kalshi_quotes`, `unmatched_items`, `unmatched_events`,
`manual_orders`, `parlay_positions`, `parlay_position_legs`, `orders`,
`api_credits`. None is touched by this rule. `kalshi_quotes` and
`unmatched_*` already have rules in `retention.py`; the rest have none and this
document does not give them one.

**Databases out of scope:** `data/demo.db` and any local or CI database. The
rule is registered against the live volume only. A dry-run against `demo.db` is
a syntax check and **no number from it may be quoted anywhere.**

---

## 3. The unit of observation

Two units, and they answer different halves of §1.

- **For the safety claim (§1b): the row.** A `fair_prices` row is what a reader
  reaches through `recommendations.fair_price_id` or through
  `parlays.CANDIDATE_SQL`. The safety claim is per-row and admits no aggregate.
- **For the retention claim (§1a): the identity-day**, defined as
  `(link_id, market, outcome_name, outcome_description, outcome_point,
  utc_day)`. The survivor set holds exactly one row per identity-day, plus the
  D5 anchors, plus the D6 newest. The series is **downsampled to daily
  resolution, never truncated** — no identity loses its history, it loses its
  intra-day sampling.

**What makes two units independent: nothing does, and that is the mechanism
rather than a defect.** Rows sharing an identity within a day are ~96
re-observations of one market driven by one 900-second timer against a
consensus that mostly has not moved. They are the opposite of independent, and
that non-independence is precisely what the rule harvests. Consequently:

> **No row count in this measurement may be reported as an `n` for any
> inferential purpose.** `eligible_rows` is a **census over a complete
> enumeration**, not a sample. It has no standard error, and printing one beside
> it would be inventing a sampling process that does not exist.

**Clustering variable, fixed now.** If any future analysis makes an inferential
claim about this rule — for instance "the downsample removes a different share
of prop rows than of moneyline rows" — the cluster is **`link_id`**, one linked
fixture. Not the row, not the identity, not the market. Registered here so it
cannot be chosen later: a game's h2h, spreads and prop rows all descend from one
`event_links` row and one odds feed, and counting them separately is the `n`
inflation this repo already shipped a gate fix for.

---

## 4. The cut — the deletion rule, fixed in advance

> **A `fair_prices` row is DELETABLE only if EVERY ONE of D1..D6 holds. Any
> single failure keeps it.** The rule is a conjunction of six keep-defaults, so
> every unresolvable input, every join miss and every NULL falls toward *keep*.
> S1 is written so that this is a property of the SQL, not of the prose.

### D1 — age

```
computed_ms < now_ms - RETENTION_DAYS * 86_400_000
```

with **`RETENTION_DAYS = 14`, registered.**

**Why 14, argued from the readers rather than from the disk.** The longest
*bounded-window* production reader of `fair_prices` is the parlay desk's
candidate scan. Its floor is

```
max(_CANDIDATE_SCAN_FLOOR_MULTIPLE * max_odds_age_ms, _CANDIDATE_SCAN_MIN_MS)
  = max(8 * 900_000, 2 * 3_600_000)
  = 7_200_000 ms = 2 hours
```

at the deployed `MAX_ODDS_AGE_S = 900` (F3). **14 days against a 2-hour longest
reader is a 168x margin.** That is the same *shape* of margin
`DEFAULT_QUOTE_RETENTION_MS` already holds — three days against a one-hour
longest reader, ~72x, chosen at `backend/store/retention.py:72-76` "so that a
reader added without reading this file has room to be wrong before it is
silently starved." This rule takes the same posture at more than twice the
factor, because `fair_prices` carries devig provenance that `kalshi_quotes`
does not and a wrong deletion here is unrecoverable.

**14 is not a compromise between the reader margin and the disk.** The disk did
not enter the choice. That is deliberate: a window chosen to hit a byte target
is a window chosen after seeing the data, one step removed.

### D2 — the evidence join

```
id NOT IN (SELECT fair_price_id FROM recommendations WHERE fair_price_id IS NOT NULL)
```

Every production `fair_prices` read other than the parlay desk reaches the table
**only** through `recommendations.fair_price_id`, as a 1:1 `LEFT JOIN` (F2):
`/api/slate` (`backend/api/routes.py:1371`), `/api/market/{ticker}`
(`:1870`), `/api/ledger` (`:2515`, paged over the **whole** history and
therefore unbounded in age), and the money path
`backend/store/manual_orders.py:389`. D2 is what makes the unbounded
`/api/ledger` reader safe.

**The referenced set is genuinely sub-daily, and this is why D2 is not a
no-op.** `backend/engine.py:496-500` records a **new** `recommendations` row on
every price change — *"A price that moves 47 -> 48 -> 47 must record three
observations"* — and each one points at that pass's `fair_prices` row. So the
rows a reader can reach are the rows where the price moved, not one per market
per day and not all of them.

**The degradation if D2 were wrong is a wrong claim, not a visible error**, and
that is why this is a keep-condition rather than a tolerance.
`backend/api/routes.py:6333-6341`: a row the devig join missed *"gets no score
at all"*, because scoring anyway *"would publish 'fewer than two devig methods
solved', which is a claim about the DEVIG when the truth is that there was no
fair price to read."* A D2 violation would manufacture exactly that state on a
ledger row that used to render correctly, and nothing on the screen would say a
row had been deleted.

### D3 — consumed into a durable derived artifact

At least one `closing_lines` row exists for a ticker in this row's Kalshi event:

```
fair_prices.link_id -> event_links.id
event_links.kalshi_event_ticker = kalshi_markets.event_ticker
kalshi_markets.ticker           = closing_lines.ticker
```

**If no such row exists, the market has not been scored yet and EVERY row for
it is kept**, regardless of age. D3 is the condition that stops the rule from
deleting the observation history of a fixture whose closing line was never
recorded — which is the one case where the raw series is the only record that
the fixture was ever priced.

**The Parquet lake is NOT the durable artifact and may not be cited as one.**
`backend/store/publish.py` is a CLI. Its only automated invocation is CI, against
`data/demo.db` (`.github/workflows/ci.yml:86`), and
`tests/test_has_callers.py:1084-1091` classifies it as a `Tool` whose purpose
note says in the repo's own words that *"Nothing on the instance runs it, which
is why `data/lake/` still holds what someone published by hand."* **It has never
run against live.** So `closing_lines`, plus the frozen
`recommendations.fair_price_id` link D2 protects, are the **only** durable
derived artifacts that exist for this table. Any future argument of the form "it
is safe to delete, it is in the lake" is false today and must be re-verified
rather than assumed.

### D4 — the daily downsample

It is **not** the newest row for its identity within its own UTC day. Identity
is

```
(link_id, market, outcome_name, outcome_description, outcome_point)
```

**byte-for-byte the partition `backend/parlays.py:356-357` uses**, including
`outcome_description` — which is `NULL` on team markets and load-bearing on
props, where it carries the player. Dropping it from the identity would collapse
every player on one prop market into one series and delete all but one of them.
It is in the partition because the production reader has it in its partition;
this rule does not get its own definition of what a market is.

SQLite's window `PARTITION BY` groups `NULL` with `NULL`, so a team market whose
`outcome_description` and `outcome_point` are both `NULL` partitions correctly.
That is the same semantics `CANDIDATE_SQL` already relies on.

**The survivor set is one row per identity per UTC day.** The series is
downsampled to daily resolution. It is never truncated, and no identity is ever
emptied.

### D5 — the closing-line anchors

It is **not** the last row at or before `commence_ms - h * 3_600_000` for its
identity, **for every registered horizon `h`.**

**Registered horizons: `h in {0.0, 1.0}`.** These are
`DEFAULT_HORIZON_HOURS = 0.0` (`backend/analysis/clv.py:76`) and
`CONTROL_HORIZON_HOURS = 1.0` (`clv.py:84`). Both, not just the primary: ADR
0011 kept the 1.0h rows deliberately, and the two-horizon convergence check is
the thing that distinguishes edge from convergence.

D5 preserves the h2 reading registered but never run at
`docs/measurements/2026-08-11-preregistration-outcome-scored-leadership.md:529` —
*"`closing_lines` mid at the row's `clv_horizon_hours` | the last admitted
`fair_prices` before that anchor"*. That measurement is registered, unrun, and
would be **permanently impossible** if the row it names were deleted. D5 exists
so a downsample does not silently void an open registration.

It also preserves the option CLAUDE.md holds open: a successor CLV registration
with an `edge_tenths` exclusion fixed in advance. That successor would need the
same anchor rows.

`commence_ms` is `MIN(commence_ms)` per `odds_event_id` from `odds_snapshots`,
restricted to `odds_event_id IN (SELECT odds_event_id FROM event_links)` —
**exactly as `CANDIDATE_SQL` computes it** (`backend/parlays.py:363-386`),
including the deliberate absence of a `commence_ms` filter inside the
aggregate, which that query's own comment explains at `:379-384`: filtering
before the `MIN` *"would let a RESCHEDULED fixture through whose true earliest
start is in the past."*

**D5 is applied without `CANDIDATE_SQL`'s seven-market restriction**, i.e. it
is deliberately *wider* than the reader it is derived from. A keep-rule narrower
than a reader is the failure mode; a keep-rule wider than a reader costs rows
and is safe.

### D6 — the newest row per identity, unconditionally

It is **not** the newest row for its identity, regardless of age, regardless of
`commence_ms`, regardless of whether the fixture has started or settled.

**D6 is redundant against D4 as both are written today** — the newest row
overall is necessarily the newest row within its own day. It is registered as a
separate condition anyway, so that an amendment to D4 (a different day
boundary, a different partition) cannot silently remove the guarantee that no
identity is ever emptied. A redundancy that survives an amendment is not a
redundancy.

---

## 5. The statistic, named as an estimator

Three quantities are produced, and **only one of them is an estimator.** The
distinction is registered here because all three will be quoted in the same
sentence and two of them are exact.

| quantity | what it is | error |
|---|---|---|
| `eligible_rows` | a **census count** over a complete enumeration | none. Exact given S1. |
| `eligible_row_fraction` = `eligible_rows / total_rows` | a **proportion over a complete enumeration** | **exactly zero sampling error.** There is no sample. `sqrt(p(1-p)/n)` is not applicable and printing it would invent a sampling process that does not exist. |
| `estimated_freed_bytes` | **an estimator**, and the only one here | **model error, not sampling error**, and therefore no standard error is computable |

`estimated_freed_bytes` is defined, fixed in advance, as

```
estimated_freed_bytes = eligible_row_fraction * 899_887_104
```

where 899,887,104 B is the `fair_prices` **family** — the table
(646,230,016) plus `idx_fair_link` (133,218,304) plus
`idx_fair_market_computed` (120,438,784), as measured by `db-sizes` on live at
2026-09-01T~16:40Z (F1). The family, not the table alone, because deleting a
row frees its index entries too.

**Its assumption, which must be printed on the same line as the number every
time it is printed: bytes per row are uniform across the table and both
indexes.** They are not exactly uniform — `books_used` is a JSON array whose
length varies with book count, and prop rows carry an `outcome_description`
that team rows do not. Nothing in this design measures that variation, and §9.2
says so.

**The word ESTIMATE is required in the output beside this number**, and the
number may not appear in any write-up without it.

---

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

## 7. The stopping rule

**Data collection is a single query. The stopping rule is therefore about which
run of it counts.**

- **The deciding run is the first dry-run executed against live on or after the
  date the implementation lands.** Its output is the number that governs §6, and
  it is recorded in the result file named in §8 with its UTC timestamp, its
  `git` SHA and the live `db_kb` at that instant.
- **Subsequent dry-runs are operational monitoring, labelled as such, and may
  not move the verdict.** They may be run freely. They may not be quoted in the
  arming ADR as evidence that the threshold was cleared.
- **If the deciding run has not happened by 2026-09-14** — the early end of the
  volume clock's honest bracket — the registration is **not** extended by
  default. It expires, and reopening it requires an amendment that states why
  the delay does not itself answer the question.
- **If the volume reaches ENOSPC before the deciding run, this registration is
  VOID.** The emergency response is an extend, not a hurried delete. A
  destructive rule executed under disk pressure is the self-arming failure §6
  forbids, arriving by a different door.

---

## 8. What would falsify this, and what happens then

### Falsified if

Any one of:

- `estimated_freed_bytes < 322,800,000` at `RETENTION_DAYS = 14` on the
  deciding run; **or**
- T-MECH fails: D4 removes fewer than 90% of the rows passing D1 ∧ D2 ∧ D3;
  **or**
- any of P1–P6 answers NO; **or**
- the safety claim §1b fails — one production reader is found that D2 does not
  cover.

### Where the negative gets written, fixed now

**`docs/measurements/2026-09-XX-fair-prices-downsample-dry-run-result.md`**,
where `XX` is the date of the deciding run. **One file, written either way.**
The positive and the negative share a destination deliberately: a negative
branch with no address is a negative that quietly never gets written.

The result file carries, in this order: the P1–P6 answers, the census counts,
the per-`link_id` view, T-MECH, then `estimated_freed_bytes`, then the §6
verdict verbatim, then §9 reproduced verbatim.

### Consequences, both directions

| verdict | what is built | what is killed |
|---|---|---|
| **ELIGIBLE TO PROPOSE ARMING** | an ADR is opened proposing arming, naming the human who decided. The flag stays `false` until that ADR lands. | nothing yet |
| **NOT WORTH ARMING** | nothing. The rule is not built further. | `fair_prices` retention is **closed as an approach**, and the volume answer is an extend past the reached 5 GB `auto_extend_size_limit` — a `fly.live.toml` change and a cost decision, which is a different ADR with a different author |
| **PREMISE REFUTED** | nothing. §5 of the volume clock is reopened. | the attribution of growth to intra-day re-observation, which several other plans lean on |

### Is this decision-relevant? Yes, and here is the test that was applied

An extend is available in **both** branches, which is the shape that usually
means "we proceed either way" and that the measurement should be killed. It is
not that shape here, and the reason is what happens *after* the extend: in the
clearing branch `fair_prices` growth becomes bounded and the extend is bought
once; in the non-clearing branch it stays unbounded and the extend is bought
again, at a rate the volume clock already measures. **Different files get edited
and a different recurring cost is taken on.** That is the test, applied before
the run rather than after.

---

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

## The power check — computed before any resource is committed

**Can this measurement answer this question at the scale available?**

### 1. What the dry-run can resolve exactly

`eligible_rows`, `eligible_row_fraction` and T-MECH are **census quantities over
a complete enumeration** (§5). They have no sampling error. There is no `n` at
which they fail to resolve, and no power calculation applies to them. **The
eligibility half of §1a is fully resolvable.**

### 2. What it cannot resolve, and the multiplicative unknown

The decision turns on **filesystem bytes**, and those are
`estimated_freed_bytes` multiplied by a free-list revolution coefficient in
[0, 1] that §9.5 says this design cannot touch. That is not an `n` problem and
no sample size fixes it. **The response registered here is to define the
threshold on the quantity that is resolvable** — estimated eligible bytes — and
to carry the coefficient as a named §9 caveat rather than hiding it inside the
number. A threshold defined on filesystem bytes would be unmeasurable and the
measurement would return a number anyway.

### 3. The timing arithmetic, which is the part that was nearly missed

The rule only touches rows older than `RETENTION_DAYS = 14`. Take the headline
fill date `F = 2026-09-17`. **By `F`, the rule can only ever have deleted rows
written before `F - 14 d = 2026-09-03.`**

```
  remaining growth window, 2026-09-01 -> 2026-09-17     16.06 days
  reachable by the rule before F  (to 2026-09-03)        2.00 days of writes
  UNTOUCHABLE before F            (2026-09-03 -> F)     14.06 days = 87.5%
```

**87.5% of the growth still to come before the volume fills is written too
recently for this rule to reach it.** Every byte of runway the rule can buy
before the deadline therefore comes from the **backlog** — rows already written
as of 2026-09-03 — and not from its steady-state behaviour.

The steady-state contribution reachable before `F` is at most

```
  2.00 days x 103.9 MB/day x 0.99 (D4 kill rate at a 900s cadence)
    = ~205.8 MB = ~1.27 days
```

so the whole prize before the deadline is bounded by `E + ~206 MB`, where `E` is
the deciding run's estimate — **times the [0, 1] coefficient of §9.5.**

**Two consequences, both registered here rather than discovered later.** First,
the backlog is bounded above by the share of the table older than 14 days, and
no arrangement of D2–D6 can increase it — only shortening `RETENTION_DAYS`
can, which §6 forbids by name, and this arithmetic is exactly why that
temptation will present itself. Second, **this rule is a bound on long-run
growth, not a rescue for 2026-09-17.** If the goal is the September deadline,
the extend is the instrument and this rule is not; if the goal is that
`fair_prices` stops being unbounded, this rule is the instrument and the
deadline is a coincidence. **Those are different goals and the write-up must
say which one it is claiming.**

### 4. Verdict of the power check

**READY, with the resolvable quantity as the threshold and the unresolvable one
named.** The census resolves exactly; the byte translation is a stated model;
the free-list coefficient is unmeasurable here and is carried as §9.4/§9.5
rather than absorbed. The design is **not** underpowered, and it is **not**
capable of answering "will this save the volume before 2026-09-17" — §3 above
shows why, in advance, and the decision rule is written against the question it
can answer.

### 5. What would settle §9.5, named but NOT authorised here

After any real delete — which this document does not authorise — read
`freelist_count` and `db_kb` daily for three days. If `db_kb` grows at the
pre-delete rate while `freelist_count` falls, the list revolves and the
`retention.py` assertion is right. If both grow, it accumulates and the measured
39.7% was the truth. **That is a separate registration and it may not be folded
into this one**, because it requires the destruction this document exists to
gate.

---

## Facts verified against source, not taken on trust

### F1. `fair_prices` is 646,230,016 bytes and has no retention rule. The omission was made with the table in the author's hand.

`db-sizes` on live, 2026-09-01T~16:40Z, via
`docs/measurements/2026-09-01-the-volume-clock.md` §5:

```
  fair_prices              646,230,016
  idx_fair_link            133,218,304
  idx_fair_market_computed 120,438,784
  family                   899,887,104   = 37.3% of the file
```

`backend/store/retention.py` mentions the table **in prose only**, at `:43`
(*"(`fair_prices` is keyed by `link_id`)"*) — **three lines above** the "What
this does NOT do" list, which names `odds_snapshots` as *"deliberately out of
scope rather than forgotten"* at `:53-55` and **does not name `fair_prices` at
all.** Verified: the module's only `DELETE FROM` statements are at `:204`,
`:239` and `:292`, and none touches `fair_prices`.

`fly.live.toml:603-604` records the consequence in the deployed config: *"Today
the answer is known: `fair_prices` is 646 MB and has no retention rule."*
`auto_extend_size_limit = "5GB"` at `fly.live.toml:607` — reached, so the
auto-extend net cannot fire again, and running out is ENOSPC: a hard down a
restart does not clear.

### F2. The complete enumeration of production `fair_prices` readers, 2026-09-01

Every one. Verified by `grep -rn "fair_prices" backend/`.

| reader | line | how it reaches the table | covered by |
|---|---|---|---|
| `/api/slate` | `backend/api/routes.py:1371` | `LEFT JOIN fair_prices f ON f.id = r.fair_price_id` | D2 |
| `/api/market/{ticker}` | `backend/api/routes.py:1870` | same join | D2 |
| `/api/ledger` | `backend/api/routes.py:2515` | same join, **paged over the whole history** | D2 |
| manual-order consensus | `backend/store/manual_orders.py:389` | same join — **the money path** | D2 |
| parlay candidate scan | `backend/parlays.py:314-399`, called at `:422` | `FROM fair_prices f` directly, `WHERE f.computed_ms >= ?` | D1 (bounded window, F3) |

`backend/seed_demo.py` writes `demo.db` and is out of scope (§2).
`backend/runner.py` and `backend/engine.py` are writers.
`backend/core/ladder.py` and `backend/odds/client.py` mention the table only in
comments.

**Why the D2-referenced set is genuinely sub-daily:** `backend/engine.py:496-500`
— *"**Consecutive, not global.** Only a row identical to the most recent row for
that `(ticker, side)` is skipped. A price that moves 47 -> 48 -> 47 must record
three observations"* — so a new `recommendations` row, pointing at that pass's
`fair_prices` row, is written on every price change and not on every pass.

**What a D2 violation would look like on the screen:**
`backend/api/routes.py:6333-6341` — *"A row the devig join missed gets no score
at all... scoring anyway would publish 'fewer than two devig methods solved',
which is a claim about the DEVIG when the truth is that there was no fair price
to read."* A wrong claim, not a visible error.

### F3. The parlay desk's scan floor is 2 hours at the deployed config

`backend/parlays.py:246` `_CANDIDATE_SCAN_FLOOR_MULTIPLE = 8`;
`:251` `_CANDIDATE_SCAN_MIN_MS = 2 * 3_600_000`;
`:417-421` `horizon_ms = max(_CANDIDATE_SCAN_FLOOR_MULTIPLE * (max_odds_age_ms or 0), _CANDIDATE_SCAN_MIN_MS)`;
`fly.live.toml:509` `MAX_ODDS_AGE_S = "900"`.

`8 * 900_000 = 7_200_000 ms = 2 h`, equal to the minimum. **14 days is a 168x
margin.** The `:242-243` comment records that 8x was chosen so the census
*"keeps an hour of headroom behind the case the suite actually pins."*

### F4. The margin shape is the one `kalshi_quotes` retention already holds

`backend/store/retention.py:72-76`: `DEFAULT_QUOTE_RETENTION_MS = 3 * _MS_PER_DAY`,
*"Three days against a one-hour longest reader is a ~72x margin, chosen so that
a reader added without reading this file has room to be wrong before it is
silently starved."* D1's 168x is the same argument at more than twice the
factor.

### F5. The Parquet lake has never run against live

`backend/store/publish.py` is a module-level CLI. Its only automated invocation
is `.github/workflows/ci.yml:86` — `python -m backend.store.publish --db
data/demo.db` — against the **seeded demo database**.
`tests/test_has_callers.py:1084-1091` classifies it as `Tool(run_by=("python -m
backend.store.publish",))` with the note *"Nothing on the instance runs it,
which is why `data/lake/` still holds what someone published by hand."*
**Verified: no scheduler, no runner call, no entrypoint reference.** D3's
durable artifacts are `closing_lines` and the frozen
`recommendations.fair_price_id` link, and nothing else.

### F6. D4's identity is byte-for-byte the production partition

`backend/parlays.py:356-357`:

```sql
ROW_NUMBER() OVER (
    PARTITION BY f.link_id, f.market, f.outcome_name,
                 f.outcome_description, f.outcome_point
    ORDER BY f.computed_ms DESC, f.rowid DESC
) AS rn
```

Copied without alteration, **including `outcome_description`.** The `:350-354`
comment explains the tie-break: *"this is arbitrary and STABLE, so two calls a
millisecond apart cannot offer different legs for the same rung."* S1 uses
`f.id` rather than `f.rowid`; `fair_prices.id` is `INTEGER PRIMARY KEY
AUTOINCREMENT` (`backend/store/schema.sql:549`) and is therefore the rowid
alias, so the two are the same column.

### F7. The registered horizons and the reading D5 protects

`backend/analysis/clv.py:76` `DEFAULT_HORIZON_HOURS = 0.0`;
`clv.py:84` `CONTROL_HORIZON_HOURS = 1.0`.
`closing_lines` carries `horizon_hours REAL NOT NULL` with `UNIQUE (ticker,
horizon_hours)` (`backend/store/schema.sql:200`, `:204`).

`docs/measurements/2026-08-11-preregistration-outcome-scored-leadership.md:529`
registers the h2 reading whose consensus side is *"the last admitted
`fair_prices` before that anchor"* — **registered, never run, and permanently
impossible if D5 did not exist.**

### F8. `commence_ms` is `MIN(commence_ms)` per linked `odds_event_id`

`backend/parlays.py:363-386`. Restricted to `odds_event_id IN (SELECT
odds_event_id FROM event_links)` for the query-plan reason recorded at
`:367-377`, and **deliberately not filtered on `commence_ms` inside the
aggregate** — `:379-384`: *"filtering rows before taking the MIN would let a
RESCHEDULED fixture through whose true earliest start is in the past. Rare, and
a silent wrong answer is worse than a slower right one."* S1 reproduces both.

### F9. The 64.4% is a share of organic bytes over 44.4 hours, not a rate

`docs/measurements/2026-09-01-the-volume-clock.md` §5:

```
  fair_prices             +116,903,936   over 44.4 +/- 1.0 h
  file total              +340,824,064
  less the v31 index build
    (idx_odds_sport_commence, +159,178,752)
  organic                 +181,645,312
  fair_prices share            64.4%
```

That section states in its own words: *"No per-day figure is given here, and
that is deliberate... This section is a composition. §3 is the rate."* The
derived daily contribution used in this registration is
`0.644 x 161.40 = 103.9 MB/day`, **quoted as conditional on the share holding at
the headline rate** (§9.3).

### F10. The clock, and that it is n = 1

`docs/measurements/2026-09-01-the-volume-clock.md` §4: free (statvfs
`f_bavail`) **2,592,702,464 B**; **161.40 MB/day** clean-24h db+WAL; fill
**2026-09-17**; *"Every date in this table is n = 1 day."* Honest bracket
**2026-09-14 to 2026-09-26**, and §6 says the early end is the one to plan
against. `VACUUM` prize **90,931,200 B = 0.56 days** (§7), against a margin that
closes in 0.56 days.

### F11. `FAIR_PRICE_DOWNSAMPLE_ENABLED` does not exist yet

Verified: no occurrence of `FAIR_PRICE_DOWNSAMPLE` or `DOWNSAMPLE` anywhere in
`backend/`, `scripts/`, `*.toml` or `.env.example`. The flag name is registered
here, unused, so that the implementation cannot arrive under a different name
with a different default.

---

## S1. The extraction query, fixed in advance

**This is the SELECT twin of the DELETE.** It returns exactly the deletable set.
The implementation is checked against this query, not this query against the
implementation. The dry-run runs this; the armed rule runs
`DELETE FROM fair_prices WHERE id IN (<this>)` and nothing else.

**Verified 2026-09-01 to parse and execute, and the `DELETE` twin verified to
be constructible from this exact text**, against a fresh in-memory database
built from `backend/store/schema.sql` — **for syntax only.** That database is
empty, so it returned zero rows, and **no value from that run is recorded
anywhere or may be quoted.** It is not `demo.db` and it is not live. What it
establishes is that the query is executable as written, so an implementation
that differs from it differs deliberately.

```sql
WITH params AS (
    SELECT
        :now_ms                                  AS now_ms,
        :retention_days                          AS retention_days,   -- registered value: 14
        :now_ms - :retention_days * 86400000     AS age_cutoff_ms
),

-- D5 support. The fixture's earliest recorded start, per LINKED odds event.
-- Byte-for-byte `backend/parlays.py:363-386`, including the linked-event
-- restriction and the deliberate absence of a `commence_ms` filter inside the
-- aggregate (a rescheduled fixture's true earliest start can be in the past).
commence AS (
    SELECT odds_event_id, MIN(commence_ms) AS commence_ms
    FROM odds_snapshots
    WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)
    GROUP BY odds_event_id
),

-- Every fair_prices row, with its identity, its UTC day, its fixture start and
-- its Kalshi event. LEFT JOIN on event_links deliberately: `link_id` is
-- NOT NULL REFERENCES event_links(id) (schema.sql:551), but an orphan must be
-- KEPT EXPLICITLY rather than kept by accidentally falling out of an inner
-- join. `kalshi_event_ticker IS NOT NULL` in the final predicate is that.
base AS (
    SELECT
        f.id, f.link_id, f.market, f.outcome_name, f.outcome_description,
        f.outcome_point, f.computed_ms,
        l.kalshi_event_ticker                                    AS kalshi_event_ticker,
        c.commence_ms                                            AS commence_ms,
        strftime('%Y-%m-%d', f.computed_ms / 1000, 'unixepoch')  AS utc_day
    FROM fair_prices f
    LEFT JOIN event_links l ON l.id = f.link_id
    LEFT JOIN commence    c ON c.odds_event_id = l.odds_event_id
),

-- D2. Every row any recommendation points at. `/api/ledger` pages the whole
-- history, so this set has no time bound and must not be given one.
referenced AS (
    SELECT DISTINCT fair_price_id AS id
    FROM recommendations
    WHERE fair_price_id IS NOT NULL
),

-- D3. Kalshi events that have produced at least one closing line, i.e. that
-- have been consumed into a durable derived artifact. The Parquet lake is NOT
-- one (F5) and must never be added here without re-verifying that it runs.
scored_events AS (
    SELECT DISTINCT m.event_ticker AS event_ticker
    FROM closing_lines cl
    JOIN kalshi_markets m ON m.ticker = cl.ticker
    WHERE m.event_ticker IS NOT NULL
),

-- D4. The newest row for its identity within its own UTC day. Partition copied
-- byte-for-byte from `backend/parlays.py:356-357` (F6), plus `utc_day`.
day_survivor AS (
    SELECT id FROM (
        SELECT b.id,
               ROW_NUMBER() OVER (
                   PARTITION BY b.link_id, b.market, b.outcome_name,
                                b.outcome_description, b.outcome_point,
                                b.utc_day
                   ORDER BY b.computed_ms DESC, b.id DESC
               ) AS rn
        FROM base b
    ) WHERE rn = 1
),

-- D5. The last row at or before `commence_ms - h*3_600_000`, per identity, for
-- EVERY registered horizon. Horizons are clv.py:76 and clv.py:84 (F7), and are
-- enumerated as a literal set so that adding one is a visible edit.
-- Rows with no computable `commence_ms` never enter this CTE and so are never
-- marked survivors here. P5 is what stops that from silently becoming a
-- deletion rule, by refusing to arm if they exceed 10%.
anchor_survivor AS (
    SELECT id FROM (
        SELECT b.id,
               ROW_NUMBER() OVER (
                   PARTITION BY b.link_id, b.market, b.outcome_name,
                                b.outcome_description, b.outcome_point, h.h
                   ORDER BY b.computed_ms DESC, b.id DESC
               ) AS rn
        FROM base b
        CROSS JOIN (SELECT 0.0 AS h UNION ALL SELECT 1.0 AS h) h
        WHERE b.commence_ms IS NOT NULL
          AND b.computed_ms <= b.commence_ms - CAST(h.h * 3600000 AS INTEGER)
    ) WHERE rn = 1
),

-- D6. The newest row per identity, unconditionally. Redundant against D4 as
-- both are written today, and registered separately so an amendment to D4
-- cannot silently remove the guarantee that no identity is ever emptied.
identity_newest AS (
    SELECT id FROM (
        SELECT b.id,
               ROW_NUMBER() OVER (
                   PARTITION BY b.link_id, b.market, b.outcome_name,
                                b.outcome_description, b.outcome_point
                   ORDER BY b.computed_ms DESC, b.id DESC
               ) AS rn
        FROM base b
    ) WHERE rn = 1
)

SELECT b.id
FROM base b
WHERE b.kalshi_event_ticker IS NOT NULL                                    -- orphan link -> KEEP
  AND b.computed_ms < (SELECT age_cutoff_ms FROM params)                   -- D1
  AND b.id              NOT IN (SELECT id           FROM referenced)       -- D2
  AND b.kalshi_event_ticker IN (SELECT event_ticker FROM scored_events)    -- D3
  AND b.id              NOT IN (SELECT id           FROM day_survivor)     -- D4
  AND b.id              NOT IN (SELECT id           FROM anchor_survivor)  -- D5
  AND b.id              NOT IN (SELECT id           FROM identity_newest)  -- D6
ORDER BY b.id;
```

**Every failure mode of this query falls toward KEEP, and that is a property of
the SQL rather than of the prose above it.** A `NULL` inside a `NOT IN` subquery
makes the predicate `NULL` rather than `TRUE`, so the row is not eligible. An
`IN` against a subquery with no match is `FALSE` or `NULL`, so the row is not
eligible. A missing `event_links` row fails `kalshi_event_ticker IS NOT NULL`.
A missing `commence_ms` never enters `anchor_survivor` — which is the one place
the direction is not automatic, and P5 is the guard for it.

`referenced` and `scored_events` both filter their key `IS NOT NULL` at the
source, so the `NOT IN` NULL trap cannot fire silently in either direction.

### Required output of the dry-run, in this order

**Read `n` before the effect size.** The harness prints, in this sequence, and a
harness that prints them in any other order is not this harness:

1. **P1–P6, each as YES or NO**, with the `closing_lines` row count (P3), the
   no-`commence_ms` fraction (P5), and the before/after
   `COUNT(*) FROM fair_prices` pair (P6).
2. `total_rows`, `eligible_rows`, `eligible_row_fraction`, and the count of rows
   removed by each of D1..D6 **individually** — so it is visible which condition
   is doing the work.
3. **The per-`link_id` view and the largest single contributor's share of
   `eligible_rows`.** A pooled number is not a finding until the parts agree,
   and this repo has been burned by two WNBA games carrying 41% of a
   population.
4. **T-MECH**: within rows passing D1 ∧ D2 ∧ D3, the fraction removed by D4.
   Threshold 0.90.
5. **Only then** `estimated_freed_bytes`, printed as
   `ESTIMATE <n> bytes (uniform bytes/row across table + both indexes; see §5)`.
6. The threshold `322,800,000` and the §6 verdict **verbatim**.
7. §9, reproduced verbatim.

Any sensitivity sweep is printed **after** all of the above, each value labelled
`SENSITIVITY — DELETES NOTHING — CANNOT ARM`.

The harness's module docstring states what it does not establish, per the repo
rule that every harness carries its own limits. §9.1 and §9.4 are the two that
must appear there in full.

---

## Registration record

| | |
|---|---|
| Registered | 2026-09-01 |
| Data seen at registration | **None.** No row of live `fair_prices` was counted, aged, sized or inspected. Published aggregates from `docs/measurements/2026-09-01-the-volume-clock.md` were read; no query was run against the table. |
| What is registered | a **destructive data rule**, not a statistical estimate |
| The cut | D1..D6, §4. A row is DELETABLE only if **every one** holds. |
| `RETENTION_DAYS` | **14**, registered. Sweep permitted at {7, 21, 28, 60}, dry-run only, cannot arm. |
| Identity | `(link_id, market, outcome_name, outcome_description, outcome_point)` — `backend/parlays.py:356-357`, byte-for-byte |
| Horizons preserved | `h in {0.0, 1.0}` — `clv.py:76`, `clv.py:84` |
| Unit of observation | the **row** for safety; the **identity-day** for retention |
| Cluster key, if ever needed | `link_id` |
| Primary quantity | `estimated_freed_bytes` = `eligible_row_fraction * 899,887,104` — the only estimator here; the other two are census counts |
| Threshold | **322,800,000 bytes** = 2.00 days at 161.40 MB/day = 35.9% of the family = 50.0% of the table |
| Secondary threshold | **T-MECH**: D4 removes >= 90% of D1 ∧ D2 ∧ D3 rows, else PREMISE REFUTED |
| Multiplicity | 1 cell. The sweep cannot arm, and the arming value was named before any value was computed. |
| Repeated-looks guard | a **deadline**, not a boundary — the quantity drifts monotonically and has no sampling noise. §7. |
| Stopping rule | the **first** dry-run on or after the implementation lands. Expires 2026-09-14. VOID on ENOSPC. |
| Flag | `FAIR_PRICE_DOWNSAMPLE_ENABLED`, default `false`. Does not exist yet (F11). |
| Arming | **NOT authorised by this document.** Requires a named human and a separate ADR. Must never be wired to `backend/store/volume.py`. |
| Result destination | `docs/measurements/2026-09-XX-fair-prices-downsample-dry-run-result.md`, **written either way** |
| Verdict of the power check | **READY** — census resolves exactly; the free-list coefficient is unmeasurable and is carried as §9.4/§9.5 rather than absorbed into the number |
| Known in advance | **87.5% of the growth remaining before 2026-09-17 is too recent for this rule to reach.** This is a bound on long-run growth, not a rescue for the September deadline. |
| Amendments | none |
