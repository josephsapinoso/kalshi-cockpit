# Pre-registration — a `fair_prices` retention downsample: which rows may be destroyed

**Registered 2026-09-01. No row of the live `fair_prices` table has been
inspected, counted, aged or sized in the course of writing this document.**

> **AMENDMENT 1, 2026-09-01 — read it before reading anything below.**
> **P6 is superseded.** Its "Equal is the pass condition" is **not a property of
> the dry-run at all** — the pair is equal only if no recorder commit lands
> between the two counts, and nothing here bounds either the report's duration
> or the recorder's cadence. It answered NO on the deciding run for that reason,
> and it would have answered YES on a shorter run for no better one. The
> original text is retained in place and marked. The pass condition is now
> `after >= before`, and a new **P6b** is added which can only ever *void* a
> run.
>
> **The amendment was written after the deciding run and blind to its
> substantive results.** §A8 argues why that is admissible here; §A9 rules on
> whether the run stands. **Nothing else changes** — §§1–5, §6 byte-for-byte,
> the 322,800,000-byte threshold, `RETENTION_DAYS = 14`, T-MECH's 0.90, §7's
> stopping rule and §9's caveats are untouched (§A10).
>
> See [Amendment 1](#amendment-1--2026-09-01--p6-could-not-pass-on-live-and-the-deciding-run-was-voided-by-it).

> **AMENDMENT 2, 2026-09-09 — three records, no change to the rule.**
> **`FAIR_PRICE_FAMILY_BYTES` stays pinned at 899,887,104** even though the live
> family is now 2,409,955,328 — 2.68x it. Raising a constant the estimator
> multiplies, after the eligible fraction has been seen, is the contamination
> this document exists to prevent, and the verdict is invariant under the
> correction either way (§B2). **Arming is CLOSED**, and it was closed by §6's
> own NOT WORTH ARMING branch on the deciding run, not by anybody's later
> judgement — **no arming ADR is owed and none will be written** (§B3). And a
> **non-destructive alternative was measured**: consecutive `fair_prices` rows
> for one key are value-identical **99.7%** of the time, on three windows of one
> MLB day. It is an **observation with no registered threshold**, it authorises
> nothing, and §B6 says the six things it does not establish (§B4, §B7).
>
> **Nothing in §§1–9, S1, P1–P6b or any threshold moves** (§B8).
>
> See [Amendment 2](#amendment-2--2026-09-09--the-family-constant-stays-pinned-arming-is-closed-and-a-non-destructive-option-was-measured).

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

  > **[SUPERSEDED by Amendment 1 §A4 — text retained.]** "Equal is the pass
  > condition" **tests a race, not the dry-run.** `backend/runner.py:980` inserts
  > into this table on every recorder cycle, so the pair is equal only when no
  > commit lands between the two counts — and P6 answered NO on the deciding run
  > for that reason and no other (observed: before 3,786,454, after 3,786,848,
  > **+394**).
  > The pass condition is now **`after >= before`** — *no row was removed* —
  > plus a probe that the connection refuses writes (§A7), and Amendment 1 adds
  > **P6b**, a margin check that can only void a run. `mode=ro` remains the
  > enforcement; the count pair remains the crude second check, and §A7 says why
  > both are needed rather than either.

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
| Amendments | **2**. **Amendment 1**, 2026-09-01: written **after** the deciding run and **blind** to its substantive results; §A8 is the argument, §A9 the ruling; it amends **P6 only** and adds **P6b**. **Amendment 2**, 2026-09-09: records only — `FAIR_PRICE_FAMILY_BYTES` **stays pinned** (§B2), arming is **CLOSED** by §6's own verdict and no ADR is owed (§B3), and a measured non-destructive alternative is recorded as an **observation that registers no test** (§B4, §B7). It changes no prerequisite, condition, threshold or query (§B8). |

---

# Amendment 1 — 2026-09-01 — P6 could not pass on live, and the deciding run was voided by it

**Status: this is an amendment. It changes one prerequisite and adds one.** It
replaces P6's pass condition, adds **P6b** — a margin check that can only ever
*void* a run and never rescue one — and requires two new lines of output. It
changes nothing else: §§1–5 are untouched, **§6 is untouched byte-for-byte**
(§A10 gives a mechanical reason as well as a principled one), and the
322,800,000-byte threshold, `RETENTION_DAYS = 14`, T-MECH's 0.90 and §7's
stopping rule all stand exactly as registered.

**It was written after the deciding run, and it was written blind.** Its author
was given P6's own `before`/`after` pair and nothing else — not `total_rows`,
not `eligible_rows`, not `eligible_row_fraction`, not `estimated_freed_bytes`,
not T-MECH, not the per-`link_id` view, not the verdict. That is recorded here
rather than in a covering note because a reader auditing this document in a year
can check this file and cannot check a note. **§A8 is the argument that writing
it afterwards is acceptable, and it is an argument rather than an assurance.**
§A9 rules on the run already taken and names the fallback if the argument is
rejected.

## A1. The defect, in the registration rather than the code

P6, quoted from this document verbatim (retained in place above, marked):

> - **P6. The dry-run deletes nothing, verified rather than asserted.**
>   `SELECT COUNT(*) FROM fair_prices` is taken immediately before and
>   immediately after the dry-run and printed as two numbers. Equal is the pass
>   condition. A dry-run that only *claims* to be read-only is decoration.

`scripts/dry_run_fair_price_downsample.py:191` implements it faithfully:

```
p6_ok = before == after
```

**The code is correct against the registration. The registration is wrong.**
`fair_prices` has exactly one writer, `backend/runner.py:980`, and it inserts
one row per outcome per market on every evaluation cycle of the live recorder —
which is the table's entire purpose and the reason it needed a retention rule at
all. So the two counts are equal only when no recorder commit lands between
them, and **nothing in this registration bounds either the report's duration or
the recorder's cadence.** "Equal is the pass condition" therefore does not test
the dry-run. It tests a race whose terms were never registered.

## A2. The evidence, which is P6's own output

On the deciding run:

```
COUNT(*) FROM fair_prices   before  3,786,454
                            after   3,786,848
                            delta      +394
```

Three things establish that this is concurrent insertion and not deletion, and
each is checkable without any other figure from the run:

1. **The direction.** A deletion makes `after` smaller. `after` is larger, by
   394 rows — 0.0104% of the table.
2. **Deletion was impossible on that connection.** `main()` opens the database
   `sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)`, and SQLite raises
   `attempt to write a readonly database` on any write attempted through it.
   This document already says so: the `COUNT(*)` pair is the *crude* second
   check and `mode=ro` is the enforcement.
3. **The property P6 names is "the dry-run deletes nothing."** Equality is a
   strictly stronger predicate than that property, and the extra strength does
   no safety work whatsoever. It is falsified by a writer P6 holds no opinion
   about and never intended to constrain.

## A3. Why this is a broken check rather than an unlucky run, and what follows

It is not that P6 *happened* to fail. **P6's answer was never about the
dry-run.** The report issues nine separate reads with no enclosing transaction,
so the two counts are taken at two different snapshots and see every commit in
between; whether one lands there is settled by the report's duration against the
recorder's cadence. Neither is registered, and the harness does not so much as
print the first (§A12).

**The honest claim is the weaker one, and it is worse rather than better.** P6
is not *strictly* unsatisfiable: a report completing entirely between two
recorder cycles would see equality and answer YES. **That is the problem, not a
reprieve from it.** A prerequisite that answers NO because the run was slow, and
would have answered YES because it was fast, says nothing either way about
whether the instrument deleted a row — the only thing it claims to be about. **A
check that passes for no reason is not redeemed by also failing for no reason**,
and the passing case is the more dangerous of the two, because nobody audits a
YES. On a table of this size, read nine times with window functions over every
row, the presumption is that a live report straddles a recorder cycle — but that
presumption is unmeasured, and being unmeasured is itself part of the defect.

The consequence is the part that matters. Under §6's own clause —

> **If any of P1–P6 answers NO** — the dry-run does not run, or its result is
> void if it already has, and this document is **amended** rather than worked
> around.

— **whether this registration can return a non-void verdict on live is settled
by a stopwatch.** Not just this run: any run. The defect would have gone
unnoticed indefinitely had the harness only ever been exercised against
`demo.db` and the synthetic fixture in `tests/test_fair_price_downsample.py`,
neither of which has a concurrent writer. It surfaced because the instrument was
finally pointed at the system it was built for.

That is also why the amendment is **forced rather than chosen**: leaving P6 as
written does not preserve one verdict at the cost of another, it leaves §6's
void clause firing on a race. That has to be repaired whatever any run said, and
§A8 leans on it.

## A4. The corrected pass condition

Four candidates were considered. The ruling is a two-tier one, and both tiers
are registered here.

| | candidate | verdict |
|---|---|---|
| **A** | `after >= before` — "no row was removed" | **adopted now**, hardened by §A7 |
| **B** | pin one read snapshot for the whole report; predicate returns to `==` | **adopted for every future deciding run** (§A12); cannot be applied to a run already taken |
| **C** | `after >= before AND after - before <= K` | **rejected as a gate** — §A6 |
| **D** | drop the count pair, rely on `mode=ro` alone | **rejected** — §A7 |

### The amended P6, verbatim

> **P6. The dry-run deletes nothing, verified rather than asserted.**
> `SELECT COUNT(*) FROM fair_prices` is taken immediately before and
> immediately after the dry-run and printed as two numbers, **together with
> their difference**. The pass condition is
>
> ```
> after >= before        and, where the caller opened the database read-only,
>                        a probe confirming the connection refuses writes
> ```
>
> — that is, **no row was removed**. Rows *appearing* between the two counts are
> the live recorder (`backend/runner.py:980`) doing its job; they are not a
> finding, they are not an error, and they do not void anything. A dry-run that
> only *claims* to be read-only is still decoration, which is why the read-only
> property is **probed rather than assumed** (§A7).

### And the new P6b, verbatim

> **P6b. The decision margin is outside the concurrency perturbation.** The rows
> inserted during the run perturb `eligible_row_fraction`, and therefore
> `estimated_freed_bytes`, by a bounded amount. Compute
>
> ```
> perturbation_bytes = ceil( (after - before) / before * 899,887,104 )
> gate               = max(perturbation_bytes, 100,000)
> ```
>
> If `| estimated_freed_bytes - 322,800,000 | <= gate`, the run **does not
> decide**. Its verdict is **UNRESOLVED — MARGIN INSIDE THE CONCURRENCY
> PERTURBATION**, and a re-take under the snapshot-corrected harness of §A12 is
> required before any §6 verdict may be read off it.

**Why B is the better predicate and A is what is adopted today.** Under a single
pinned read snapshot, `after == before` tests *exactly* the property P6 names —
"this connection deleted nothing" — because a transaction sees its own writes and
sees no one else's. `after >= before` tests something weaker: **no net removal**.
A concurrent inserter can mask a deletion by this connection; ten rows deleted
against 394 inserted nets +384 and A answers YES. That hole is real and it is
named here rather than glossed. It is accepted because (i) B changes what the
two counts *mean* and so cannot be applied retroactively to counts already
taken, and (ii) the read-only probe of §A7 closes the same hole from the other
side, on the only path where it is reachable.

## A5. Does the amended P6 still do work? Four ways it can answer NO

A predicate that can never fail is as useless as one that can never pass, so the
falsifiers are enumerated rather than asserted. Each is a mechanism that exists
in this repo today:

1. **`report()` accepts any connection.** `mode=ro` is set in `main()`, at the
   connection; the function that decides P6 takes whatever it is handed.
   `tests/test_fair_price_downsample.py` already calls
   `harness.report(conn, ...)` with a **writable** fixture connection, and any
   future caller may. On that path the count pair is the only guard there is.
2. **A one-token regression.** `mode=ro` → `mode=rw`, or the `uri=True` dropped,
   is a single-character edit that no type checker and no other test catches.
3. **A mis-wire inside the module the plan lives in.**
   `backend/store/fair_price_downsample.py:638-639` already contains
   `cursor = conn.execute(sql, params); conn.commit()` — the armed DELETE path —
   taking the same connection object `plan()` takes. A call-site slip between
   the two is one identifier.
4. **A second deleter.** P2 failing *between* its grep and the run, or an armed
   rule on another deploy against the same volume, removes rows this connection
   never touched. `after >= before` catches that; `mode=ro` does not.

Four nameable failure modes is not decoration.

## A6. Why the insert count is reported but not gated on

Bounding the *insert* delta as part of P6's pass condition was considered and is
**rejected**, for three reasons in ascending order of seriousness:

1. **Any bound is a number, and the only number available to pick it from is the
   delta this run produced.** Choosing a threshold from the run's own output is
   the move this document exists to prevent, and the innocuousness of the
   quantity is not a defence — that is what every such choice looks like from
   the inside.
2. **This registration has no registered opinion about the recorder's write
   rate.** Nothing here fixes how many markets are evaluated, how many outcomes
   each carries, or how long the report takes. A bound would be invented rather
   than derived, and inventing one after the fact is worse than not having one.
3. **It would repeat P6's own category error.** An insert bound is a claim about
   the *environment*. Folding it into a prerequisite about the *instrument* is
   precisely how P6 came to be falsifiable by a writer it had no opinion about.
   The lesson of §A11 would be re-broken in the act of writing it down.

**What replaces it.** The delta becomes a mandatory reportable, printed on P6's
line and carried into the result file, never a gate; and P6b (§A4) converts it
into a check that is *derived* rather than chosen.

**Why P6b's formula is derived.** Concurrent insertion **into `fair_prices`**
can increase `total_rows` and cannot increase `eligible_rows`, and that is a
property of the registered cut rather than a hope:

- A row inserted during the run has `computed_ms ≈ now`, so **D1** excludes it —
  it is inside the retention window by construction.
- It cannot free a previously-protected row either. The only condition a fresh
  insert can disturb is **D6** (`identity_newest`): the previously-newest row for
  that identity stops being the newest. But that displaced row is at least
  `RETENTION_DAYS` old and the fresh row is in *today's* UTC day, so the
  displaced row is still the newest row in its own day and **D4** keeps it — and
  a keep on any single condition keeps the row, because §4 is a conjunction.

So with `f = eligible / total` and `δ = after - before` rows arriving,
`estimated_freed_bytes = f · 899,887,104` is perturbed **downward** by at most

```
899,887,104 · δ / total        (since f <= 1)
= 899,887,104 · 394 / 3,786,454
= 93,638 bytes   =  0.029% of the 322,800,000-byte threshold
```

The `100,000` floor absorbs the fact that `total_rows` is read at its own
snapshot inside `plan()` and need not equal `before`.

**P6b is written two-sided on purpose.** The `fair_prices` perturbation's
direction is known to be conservative, so a one-sided gate would be defensible
arithmetic — and
writing it one-sided would require its author to know which side of the
threshold the figure fell on. It is written as an absolute value so that it can
be written blind.

**P6b bounds the `fair_prices` component and nothing else, and the limit is
stated here rather than left to be discovered.** S1 reads six tables, and the
live runner writes to at least four of the five besides `fair_prices` while the
report is running:
`recommendations` (`backend/engine.py:415`, D2), `closing_lines`
(`backend/analysis/clv.py:184`, D3), `odds_snapshots`
(`backend/odds/client.py:659`, D5's `commence` CTE) and `event_links`
(`backend/match/linker.py:598`). A `recommendations` row committing mid-report
*removes* a row from the eligible set; a `closing_lines` row *adds* an event
ticker to `scored_events` and can add rows to it. **δ does not measure those and
P6b does not bound them.** Their magnitude is unknown and their sign is not
one-directional. Nothing short of §A12(4)'s pinned snapshot closes this; it is
present in the deciding run, and it would be equally present in any re-take not
taken under a snapshot — which is why §A9 does not treat a bare re-take as the
clean option.

## A7. Is `mode=ro` plus a `COUNT(*)` floor the right belt-and-braces pair?

**Yes as a pair, no as currently wired — and the fix is to probe rather than
assume.**

They are not redundant, and the reason is that they protect different callers.
`mode=ro` is set in `main()` and protects the **script**. The `COUNT(*)` pair is
computed in `report()` and protects the **function**. Neither covers the other's
path, so D — dropping the count pair — would leave `report()` unguarded on
exactly the path the test suite already exercises.

But the belt is asserted rather than checked at the place it is relied on.
`tests/test_fair_price_downsample.py::test_it_cannot_delete_because_sqlite_refuses`
opens **its own** `mode=ro` connection and demonstrates that SQLite refuses
writes on it. That is a test of SQLite. It is not a test that the connection
`report()` received is read-only, and it is the same shape of gap as the defect
this amendment exists for: a guard verified where the hazard cannot occur.

**Registered requirement:** where the caller opened the database read-only, P6
must **probe** that the connection refuses writes rather than assume it, and
print the probe's result on P6's line. The probe's exact form is the harness
author's (§A12 suggests one); what is registered is that the property is checked
and printed, not that it is believed.

## A8. Written after the run, and blind — the argument, and its residual

**The argument.** This amendment changes exactly one boolean and adds a second.
Neither is an input to any verdict-bearing quantity: not to `eligible_rows`, not
to `eligible_row_fraction`, not to `estimated_freed_bytes`, not to T-MECH, not to
any of D1..D6, not to S1. Under the original P6 the deciding run is **VOID** —
no verdict at all. Under the amended P6 the run's verdict is whatever the
instrument already computed, by code this amendment does not edit and does not
authorise editing. **The amendment can therefore select between "no verdict" and
"the verdict already computed". It cannot select which verdict.** Three further
properties make that checkable rather than merely asserted:

1. **The correction is forced, not chosen** (§A3). Under the un-amended P6,
   whether a verdict exists at all is settled by how long the report took
   against when the recorder last committed. That needed repairing whatever this
   run said — and it would have needed it just as much had the race gone the
   other way and P6 answered YES, in which case a broken check would have been
   passed by luck and nobody would ever have looked at it. Leaving it alone is
   not the conservative option.
2. **The corrected predicate is the one P6's own prose already names.** "The
   dry-run deletes nothing" was always the property. The amendment makes the
   condition match the sentence above it. It does not reach for a new condition
   that happens to pass.
3. **The amendment adds a way for the run to fail that did not exist before**
   (P6b, §A6). An amendment written to rescue a run does not do that, and this
   author cannot know whether P6b fires.

**The residual, stated because leaving it out would be the flattering move.**
Blindness establishes that *this text* was written without reference to the
outcome. It does not establish that the *decision to amend at all* was reached
blind, because the person holding the result commissioned it. That freedom — the
freedom to choose whether a known verdict counts — is not removed by anything
written here. What reduces it is that §A9's conditions are stated as predicates a
third party can evaluate against the result file, rather than as a judgement, and
that one of them can void the run.

## A9. Ruling on the run already taken: **salvageable**, under four conditions

**The run is salvageable and should be salvaged, not re-taken.** The reasoning,
and the strongest part of it runs against the project's interest:

- **The defect is mechanical, and its `fair_prices` component is bounded at
  93,638 bytes in the conservative direction** (§A6). It is not an effect on the
  measurement; it is an effect on a check that was never about the measurement.
  The cross-table component §A6 names is unbounded and unsigned — **and a bare
  re-take does not remove it**, only §A12(4) does. Re-running without the
  snapshot buys the drift below and closes nothing.
- **Re-taking is the flattering move, and by a magnitude comparable to the
  decision itself.** `eligible_rows` is monotonically increasing in wall-clock
  time — §6 says so and builds §7's deadline guard on it. A re-take taken `d`
  days later admits every row that crossed the 14-day boundary in the interval.
  Nothing in this registration measures that aging-in rate, but the threshold
  itself sets the scale: 322,800,000 bytes is **2.00 days** of database growth
  at the headline 161.40 MB/day. A re-take a day or two later therefore moves
  the primary quantity by a fraction of the threshold that is plausibly of order
  one — against a defect that moves it by 0.029%. **The remedy is some three
  orders of magnitude larger than the disease, and it points uphill.**

  > **[WITHDRAWN 2026-09-01, after the run, by the result file. This bullet's
  > conclusion is unsupported and its stated direction is wrong.]** Four live
  > looks show `estimated_freed_bytes` is **not monotone** — it is
  > `eligible / total x constant`, and while the table is dominated by fresh
  > rows the fraction falls even as the eligible count climbs. Three of the four
  > sit *below* the deciding run, and run 4 — a re-take under the corrected
  > instrument — returns 36,004,882 against the deciding run's 36,039,175, so
  > the re-take path lands **further from the threshold**, not nearer it.
  > Neither a drift rate nor its sign is established at the hour scale, so no
  > order-of-magnitude comparison holds in either direction.
  >
  > **The ruling of this section is unchanged**; bullets 1 and 3 carry it, and
  > the salvage conditions below are untouched. This is a pointer, not a
  > rewrite: nothing in the rule, the thresholds, section 6 or S1 moves. Written after
  > the figures were seen, and recorded here rather than only in the result file
  > because a reader who opens this document must not find the argument standing
  > alone. Full working:
  > `docs/measurements/2026-09-01-fair-prices-downsample-dry-run-result.md`
  > section 0.1.
- **§7 already classifies the later number.** *"The number that governs is the
  one from the first dry-run taken on or after the implementation lands. A
  later, larger number is monitoring, not evidence."* Re-taking is taking the
  second look at a monotone quantity and calling it the first.

**The four conditions, all evaluable by the result-holder against the run's own
output, none requiring this author to see it:**

1. **P1–P5 all answered YES.** If any answered NO, the run is void for a reason
   this amendment does not reach and must be re-taken. This amendment
   rehabilitates P6 and nothing else.
2. **`after >= before` on that run.** Satisfied: 3,786,848 >= 3,786,454.
3. **P6b passes** — `| estimated_freed_bytes - 322,800,000 | > 100,000`. The
   harness did not print this; it must be computed by hand from the run's own
   figures and recorded. If it fails, the run does **not** decide and §A12's
   correction must land before a re-take.
4. **The result file records the rehabilitation.** It prints `before`, `after`
   and the delta; it cites this amendment by number; and it states that the
   amendment was written after the run and blind. A salvaged run that does not
   say it was salvaged is worse than a void one.

**The fallback, pre-committed here so it is not available as a choice later.**
If the result-holder prefers the letter of §6 — that a NO voids the run whatever
the reason — then the correct action is to land §A12's correction and re-take,
and **in that case the governing `estimated_freed_bytes` is the LESSER of the
void run's figure and the re-take's.** Not the re-take's, and not the larger.
§7's monotone-drift guard is the reason, and fixing it now, blind, is what stops
the choice being made later with both numbers on the screen.

**This ruling does not move §7's date.** The 2026-09-14 expiry stands. If the
salvage is rejected and a re-take cannot be taken before it, the registration
expires as written and reopening it needs a further amendment.

## A10. What this amendment does not change — the blast radius, stated

Nothing below is touched, and the list is exhaustive by section:

- **§1** — both conjuncts of the primary claim, and its one-sided direction.
- **§2** — the population and every exclusion.
- **§3** — the unit of observation, the census-not-a-sample rule, and the
  registered cluster key `link_id`.
- **§4** — D1, D2, D3, D4, D5, D6, and `RETENTION_DAYS = 14`. The sensitivity
  set `{7, 21, 28, 60}` is unchanged and still cannot arm anything.
- **§5** — all three quantities and the `estimated_freed_bytes` formula.
- **§6 — byte-for-byte, not one character.** Every clause of the decision rule,
  the **322,800,000-byte threshold**, the **T-MECH 90% threshold**, the
  multiplicity of 1, the repeated-looks reasoning, and the prohibition on
  lowering `RETENTION_DAYS` in response to the number. The principled reason is
  that a post-hoc amendment must not reach the rule it is being judged by. The
  mechanical reason is that
  `scripts/dry_run_fair_price_downsample.py::_section()` reproduces §6 and §9
  **verbatim into every run's output**, so editing §6 would silently change the
  text printed beside the figures of a run already taken.
- **§7** — the stopping rule, the "first dry-run" wording, the **2026-09-14**
  expiry, and the ENOSPC void. §A9 rules on *which* run §7's "first" selects; it
  does not move the rule or the date.
- **§8** — the falsification list and the single result destination
  `docs/measurements/2026-09-XX-fair-prices-downsample-dry-run-result.md`,
  written either way. Its "any of P1–P6 answers NO" clause now reads against the
  amended P6, which is the only way it can read at all.
- **§9** — all eleven caveats, reproduced verbatim as before.
- **S1** — the extraction query, unchanged. This amendment adds no fenced SQL
  block, deliberately: `test_the_sql_is_section_s1_of_the_registration_byte_for_byte`
  compares the module against the **last** fenced `sql` block in this file.
- **Arming** — still not authorised, by this document or by this amendment.
  Nothing here permits a single row to be deleted.
- **`backend/gate.py`** — untouched, as always. It is a different number for a
  different decision.
- **No code.** This amendment edits no file but this one. §A12 is a
  recommendation to whoever owns the harness, not an edit and not an
  authorisation to change any behaviour beyond what §A4 and §A7 register.

Sweep runs are affected only in that each pass evaluates the amended P6 on its
own count pair. They still cannot arm and their P6b is diagnostic only.

## A11. The general defect, named so it is not repeated

> **A prerequisite was validated only against a fixture in which the hazard it
> guards against cannot occur, and was then relied on against a live system in
> which it can.**

The sharper form, because it generalises further and is the one to carry:

> **P6 named a property of the instrument and tested a property of the world.**
> *"The dry-run deletes nothing"* is a statement about what **this process** did.
> `COUNT(*) before == COUNT(*) after` is a statement about what the **table**
> did. On a fixture the two coincide, because the instrument is the only actor.
> On live they come apart, because it is not — and the check then fails in the
> direction that indicts the innocent party.

Two cheap checks fall out of it:

1. **A prerequisite phrased as an equality over a live-mutable quantity is
   suspect on sight.** Of P1–P5, none is: P1 is a subset test against a code
   enumeration (`found - F2_KNOWN_READERS`, so a *removed* reader correctly does
   not fail it), P2 a grep, P3 and P5 inequalities, P4 an environment read. **P6
   was the only equality in the set, and the only one over a quantity a live
   process moves.** That is the whole of the audit, and it is why this
   amendment's blast radius is one prerequisite.
2. **A guard tested only where the hazard is absent has not been tested.** This
   repo already holds the rule that a guard is verified by disabling it and
   watching the test fail. The `mode=ro` test passes against a database nothing
   else is writing, and the count pair was never once exercised against a
   concurrent writer — which is the only condition under which it was ever going
   to be evaluated in anger.

## A12. What the harness must change — a recommendation, authorised by §A4 and §A7

Recorded here so that the document, not a commit message, is what authorises the
change. **It is not made by this amendment.**

At `scripts/dry_run_fair_price_downsample.py:191`, `p6_ok = before == after`
becomes, in substance:

```
p6_no_removal = after >= before          # A: "no row was removed"
p6_readonly   = probe(conn)              # A7: probed, not assumed
p6_ok         = p6_no_removal and (p6_readonly or not expect_readonly)
```

with four companions:

1. **Print the delta** on P6's line — `before`, `after`, `after - before` — and
   carry all three into the result file. It is a reportable, never a gate (§A6).
2. **Probe the connection** rather than assume it. `report()` should take an
   explicit `expect_readonly` flag that `main()` sets and the fixture tests do
   not, so the writable-connection path still exercises the count half. The
   probe must be a write that is a no-op on a writable connection.
3. **Print P6b.** Compute `perturbation_bytes` and `gate` per §A4 and print the
   verdict `UNRESOLVED — MARGIN INSIDE THE CONCURRENCY PERTURBATION` when it
   fires. Without this the check exists only in prose, which is the state P6 was
   already in.
4. **Pin one read snapshot for the whole report** (candidate B), so that
   `total_rows`, `eligible_rows`, `d123_rows` and the per-`link_id` view all
   describe **one** state of the database rather than nine, and so that a future
   P6 can return to `==` and test exactly the property it names. **Verify on the
   box that the snapshot actually pins** — a read transaction against a
   `mode=ro` WAL database has platform-dependent shared-memory requirements —
   and if it does not, fall back to A and record that it did not.
   **Once a run is taken under a pinned snapshot, its P6 pass condition is `==`,
   not `>=`.**

And one gap worth closing while there: **the harness prints no wall-clock
duration**, so the delta cannot be converted to a rate and a future reader cannot
tell a 394-row delta over 40 seconds from one over 40 minutes. Print the elapsed
time.

## A13. Registration record for this amendment

```
amendment          1
date               2026-09-01
defect             P6's pass condition tested a race between the report's
                   duration and the recorder's cadence; neither is registered
evidence           COUNT(*) before 3,786,454, after 3,786,848, delta +394
                   (P6's own output; no other figure from the run was seen)
writer             backend/runner.py:980, one row per outcome per cycle
enforcement        mode=ro, scripts/dry_run_fair_price_downsample.py main()
P6 was             after == before
P6 is              after >= before, plus a read-only probe where applicable
P6b added          margin outside max(perturbation, 100,000) bytes; can only void
perturbation       fair_prices component <= 93,638 bytes = 0.029% of the
                   threshold, conservative in sign; cross-table component
                   unbounded, closed only by A12(4)'s pinned snapshot
threshold          322,800,000  UNCHANGED
RETENTION_DAYS     14           UNCHANGED
T-MECH             0.90         UNCHANGED
stopping rule      first run on or after the implementation lands; expires
                   2026-09-14  UNCHANGED
section 6          UNCHANGED, byte-for-byte
ruling             the deciding run is SALVAGEABLE under the four conditions of
                   A9; fallback if rejected is re-take, governed by the LESSER
                   of the two figures
written            after the deciding run, blind to its substantive results
general defect     a prerequisite validated only against a fixture with no
                   concurrent writer, then relied on against a live one
```

---

# Amendment 2 — 2026-09-09 — the family constant stays pinned, arming is closed, and a non-destructive option was measured

**Status: this is an amendment. It changes no prerequisite, no condition, no
threshold and no query.** §§1–5 stand, **§6 stands byte-for-byte**, §7's
stopping rule and 2026-09-14 expiry stand, §8's destination stands, §9's caveats
stand, S1 stands, and P1–P6b stand as Amendment 1 left them. §B8 states the
blast radius section by section, as §A10 did.

It does three things, all of them recording rather than deciding:

1. It rules on `FAIR_PRICE_FAMILY_BYTES`, which the live table has outgrown by
   2.68x. **The ruling is that it stays pinned** (§B2), and the ruling is
   argued rather than asserted, because the opposite ruling is the more natural
   one and is wrong.
2. It records that **arming is closed**, that it was closed by §6's own decision
   rule on the deciding run rather than by anybody's later judgement, and that
   the "separate ADR with a named human" §6 names **is not owed and will not be
   written** (§B3). It names the one measured condition that would reopen it.
3. It records a **new measured fact about how `fair_prices` grows** — consecutive
   rows for the same key are value-identical 99.7% of the time — together with
   the six things it does not establish (§B4, §B6). It **registers no test, and
   authorises no change**: §B7 says what a successor registration would have to
   fix in advance before any byte figure derived from it may be quoted.

**Provenance, stated because this document's habit is to state it.** The
2026-09-09 `db-sizes` read and the three-window duplication scan were taken by a
session other than this one, read-only against live, and are reproduced here
with their instruments named. This author verified the *source* claims
independently — the constant and its comment, the reachability of `run`, the
`enabled`-before-`dry_run` ordering, the unconditional `INSERT`, the two callers
of `run_pricing_pass`, the 15-second fast cadence — and did **not** take the
live reads. Every figure below carries which of the two it is.

---

## B1. What this amendment is answering, in one line each

| owed | answer | where |
|---|---|---|
| `FAIR_PRICE_FAMILY_BYTES` is 2.68x stale | **stays pinned.** Superseded as a description of the table; unchanged as the registered estimator's input | §B2 |
| the arming ADR §6 contemplates | **not owed.** §6 returned NOT WORTH ARMING on the deciding run; arming was never ELIGIBLE TO PROPOSE | §B3 |
| a non-destructive option nobody had measured | **recorded, not registered.** 99.7% of consecutive rows carry no change, on one day | §B4, §B7 |

---

## B2. `FAIR_PRICE_FAMILY_BYTES` — the ruling is that it stays pinned

### B2.1 The two dated reads, and the arithmetic between them

Registered (§5, F1), `db-sizes` on live 2026-09-01T~16:40Z:

```
  fair_prices                 646,230,016
  idx_fair_link               133,218,304
  idx_fair_market_computed    120,438,784
  family                      899,887,104     37.29% of a 2,413,142,016 file
```

Read 2026-09-09T~19:49Z, `db-sizes` on live, machine `7812601a239428`
(reproduced from `backend/store/fair_price_downsample.py`'s docstring, which
carries the same pair):

```
  fair_prices               1,705,545,728
  idx_fair_link               365,211,648
  idx_fair_market_computed    339,197,952
  family                    2,409,955,328     47.53% of a 5,070,802,944 file
```

Over the 8.138 days between them:

```
  family      +1,510,068,224 B   =  185.6 MB/day   ratio 2.678x
  table       +1,059,315,712 B   =  130.2 MB/day   ratio 2.639x
  file        +2,657,660,928 B   =  326.6 MB/day   ratio 2.101x
  family share of file growth                        56.82%
```

Two things in that block are worth naming rather than leaving in the numbers.

**The rate, not the share, is what was wrong.** §9.3 warned that the volume
clock's 64.4% was *"a share of that window's 181,645,312 organic bytes"* and not
a rate. The share held to within eight points (56.82% realised against 64.4%
projected). The **file rate** did not: 326.6 MB/day realised against the
161.40 MB/day the threshold in §6 is denominated in — **2.02x**. §9.6 registered
that the clock was `n = 1` day and that its rate was *"a floor rather than a
centre."* It was a floor, and by a factor of two.

**The two indexes grew faster than the table** (2.741x and 2.816x against
2.639x), so the family-to-table ratio moved from 1.3925 to 1.4130 in eight days.
That is a small movement and it is recorded for one reason: §5's estimator rests
on *"bytes per row are uniform across the table and both indexes"*, an
assumption §9.2 says nothing here tests. A composition that moves 1.5% in eight
days is not evidence against the assumption, but it is evidence that the thing
the assumption fixes is not itself fixed.

### B2.2 Why raising the constant is the contamination and not the correction

The natural reading of a stale constant is that it should be brought current.
Here it should not, and the reason is the reason this document exists.

`estimated_freed_bytes` is `eligible_row_fraction * FAIR_PRICE_FAMILY_BYTES`
(§5). The fraction has now been measured — 4.00% on the deciding run
(`docs/measurements/2026-09-01-fair-prices-downsample-dry-run-result.md` §5).
**Raising the constant after the fraction is on the screen re-scales a verdict
computed from rows that have already been inspected.** It is the same move as
lowering `RETENTION_DAYS` until the number clears, arriving through the other
factor of the same product, and §6 forbids that move by name. That the
re-scaling would push *toward* the threshold rather than away from it is what
makes it worth forbidding rather than what makes it harmless.

The code comment at `backend/store/fair_price_downsample.py:203-216` already
says this, and says it correctly:

> **DO NOT UPDATE THIS NUMBER TO MATCH THE LIVE TABLE.** [...] changing the
> constant to follow it is precisely the contamination the pre-registration
> exists to prevent: it would re-scale every byte verdict after the rows were
> seen. Raising it requires an amendment to the registration, not an edit here.

**This is that amendment, and its ruling is DO NOT RAISE.** The comment's
closing line — *"Amendment owed either way"* — is discharged here. The debt was
to write the ruling down, not to change the number.

### B2.3 The invariance check, which is what makes the ruling cheap

A pin is only defensible if it cannot be hiding a different verdict. It is not
hiding one, and the check is arithmetic:

```
  threshold                                 322,800,000 B
  family, 2026-09-09                      2,409,955,328 B
  eligible fraction that would clear it           13.394%
  eligible fraction measured, deciding run          4.005%   (151,642 / 3,786,454)
  multiple required                                 3.344x
```

At the 2026-09-09 family and the measured fraction, the naive re-scale is
**96,513,891 B — 29.9% of the threshold**, against the pinned constant's
36,039,175 B and 11.2%. The verdict is `NOT WORTH ARMING` under both. **The
correction does not reach the verdict**, and the direction of the pin's error
is the safe one: §5's estimator computed against a family 2.68x too small is a
**floor**, and a floor that fails a threshold fails it a fortiori. The code
comment states this consequence too, and it is correct as stated.

The 13.394% figure is the useful artifact of this section. It is a **falsifiable
bar, fixed here in advance of any further look**: for the byte conjunct of §1a
to clear at a family of that size, the eligible fraction would have to be more
than three and a third times what it measured. §B3.5 uses it.

### B2.4 What the constant now is, stated so a future reader is not confused by it

- As **a description of the live `fair_prices` family**, `899_887_104` is
  **superseded**. It described 2026-09-01. It does not describe today, and
  anyone quoting it as a current table size is quoting an eight-day-old number.
  The two dated reads in §B2.1 are what a description should cite.
- As **the registered input to §5's estimator**, it is **unchanged and stays
  unchanged.** It is not a measurement of the table; it is a constant fixed
  before the rows were seen, and its whole function is that the same eligible
  fraction cannot produce a different verdict on a different day.
- **Any future measurement of this table registers its own family figure with
  its own date.** It does not raise this one. A constant that is raised once has
  established that it can be raised.

### B2.5 No code changes, and one that is now forbidden rather than merely discouraged

This amendment edits no file but this one. It converts the comment's *"Raising
it requires an amendment"* from a procedure into a **completed decision**: the
amendment has been written and it declines. A future session proposing to raise
`FAIR_PRICE_FAMILY_BYTES` is proposing to overturn §B2.2 and §B2.3, and owes an
amendment that says which of the two it disputes.

---

## B3. Arming is CLOSED — and §6 closed it, not this amendment

### B3.1 The ground, which was already on the record

§6 has four branches. The deciding run took the third:

```
  VERDICT                 NOT WORTH ARMING
  estimated_freed_bytes   36,039,175 B  against 322,800,000 B    FAIL  (11.2%)
  T-MECH                  98.68%        against 90.00%           PASS
```

`docs/measurements/2026-09-01-fair-prices-downsample-dry-run-result.md`. §6's
own words for that branch: *"The rule is not deployed at `RETENTION_DAYS = 14`
and **not at any other value either**."* §8's consequence table for it: *"
`fair_prices` retention is **closed as an approach**."*

**So there is no arming ADR to write, and there never was one owed.** §6 says an
arming ADR is authorised by a verdict of ELIGIBLE TO PROPOSE ARMING and by
nothing else. That verdict was not returned. This section exists because a
reader who meets §6's arming language before meeting the result file can
reasonably infer a pending decision, and a pending decision that nobody has
killed gets re-derived in October.

**This amendment is not the decision.** The decision was the deciding run's, and
recording it here is bookkeeping. That distinction matters: an amendment that
re-decided a closed verdict on fresh grounds would be deciding after the fact,
which is the failure this document was written against. §B3.3's grounds are
therefore recorded as **corroboration of a closed verdict, and are not load-
bearing.**

### B3.2 The retraction: arming was never a week of engineering, and cost was never the reason

Recorded because a wrong reason for a right decision is a liability — it invites
re-opening the moment the wrong reason is falsified.

The claim that arming would take a week of engineering was made and **has been
retracted by its author.** It is false, and the source says so:

- `fair_price_downsample.run` **is reachable on the live loop.**
  `backend/runner.py:3168` calls it; `run_once` contains that call;
  `scripts/run_loop.py:1458` passes `downsample=downsample_config`, loaded at
  `scripts/run_loop.py:811`.
- It refuses at `backend/store/fair_price_downsample.py:672` —
  `if not getattr(config, "enabled", False): return 0` — because
  `FAIR_PRICE_DOWNSAMPLE_ENABLED` defaults to `False`
  (`backend/config.py:979`) and `fly.live.toml` sets none of the three
  variables.
- **Arming is an environment change, not a build.** Two of the three flags must
  both move — `enabled=true` **and** `dry_run=false` — which
  `backend/config.py:965-970` records as a deliberate asymmetry rather than an
  accident.

Two details that sharpen it, verified here rather than taken on trust:

1. **The `enabled` check sits before the `dry_run` branch**, at `:672` against
   `:675`. So the live loop has never executed the dry read either — not the
   `DELETE`, not the `plan()`. Every dry-run figure this registration has ever
   quoted came from `scripts/dry_run_fair_price_downsample.py`, run by hand
   against a `mode=ro` connection. The loop has never planned.
2. **Even armed, it would run at most once per full pass and only outside a
   bettable window.** `backend/runner.py:3152-3169` puts the call inside the
   same `window_open()` guard as `retention.prune`, and `run_loop.py` passes the
   config on the **full-pass** branch only — the quote-pass branch at
   `run_loop.py:1460` onward does not receive it.

**None of this is an argument for arming.** It is the removal of a false
argument against it, so that the real one stands alone.

### B3.3 The supplementary grounds — corroboration, explicitly not the ground

Recorded so that a future session weighing a re-open sees what it is weighing
against. Each is checkable; none of them decided anything.

- **The whole prize is small against the headroom already bought.** Deleting the
  **entire** `fair_prices` family — 2,409,955,328 B, which no rule here proposes
  and D6 forbids outright — buys `2,409,955,328 / 326,573,222 = 7.38 days` at the
  realised file rate. The volume was extended 5 GB → 10 GB on 2026-09-01 and
  10 GB → 20 GB on 2026-09-09, and the module docstring puts the ~14 GiB now
  free at about 46 days. **Destroying the largest table in the database in its
  entirety extends the runway by roughly a sixth.** The registered rule reaches
  4.00% of it.
- **And 7.38 days is an upper bound twice over.** It assumes freed bytes become
  filesystem bytes at 1:1, which §9.4 says they may not: freed pages go to a
  free list and *"only `VACUUM` gives space back to the OS"*
  (`backend/store/retention.py:48-52`). And §9.5's revolution coefficient in
  `[0, 1]` multiplies it, unmeasurable by this design. The honest statement is
  `7.38 days x c`, `c` unknown.
- **Irreversibility against an estimator known to be a floor.** §9.1 is the
  permanent cost — the intra-day series is gone for rows past the window, and
  the sharp-anchoring census that produced ADR 0021 §8's 73.0% could not be
  re-run. Paying a permanent cost on a number whose own comment calls it an
  understatement is a bad trade in both directions of the understatement.
- **A non-destructive option now exists and did not on 2026-09-01** (§B4). It
  deletes nothing, forecloses no historical question, and reaches the growth
  rate rather than the backlog — which §3 of the power check identified as the
  binding constraint before any of this was measured.

### B3.4 The module stays in the tree, disabled and unarmed

**`backend/store/fair_price_downsample.py` is not dead code and is not to be
removed.** Four reasons, in descending order of how expensive the mistake would
be:

1. It carries `REGISTERED_DELETABLE_SQL`, which
   `tests/test_fair_price_downsample.py::test_the_sql_is_section_s1_of_the_registration_byte_for_byte`
   pins to **the last fenced `sql` block in this file.** Deleting the module
   deletes the only mechanical link between S1 and any executable artifact.
   This registration would stop being pinned to anything.
2. It is **reached** (§B3.2) and refuses on its own config. That is the
   registered shipped state — §6: *"The rule ships behind
   `FAIR_PRICE_DOWNSAMPLE_ENABLED`, defaulting to `false`"* — not an accident of
   wiring, and `tests/test_has_callers.py` classifies it accordingly.
3. Its docstring carries the two dated byte reads of §B2.1 and the realised
   growth rate. It is where the next session that asks "what is this table
   doing" will look.
4. `tests/test_volume_alarm.py` and `tests/test_fair_price_downsample.py` assert
   that `backend/store/volume.py` cannot reach it — the §6 prohibition on
   self-arming from a disk threshold. Removing the module removes the thing
   those guards guard.

**This is the same posture the bid path is held in** (ADR 0115): present,
disarmed, one line from re-arming, and explicitly not removable as dead code.

### B3.5 What would have to change to reopen it — one measured condition, fixed here

Not a mood, not a disk alarm, not a busier month. **A successor registration**,
because §7 has already spent this one: the deciding run was taken 2026-09-01,
later looks are *"monitoring, not evidence"*, and the registration expires
2026-09-14 regardless. There is no route to a second deciding number under this
document.

That successor would have to carry, fixed before it looks:

- **An eligible fraction at or above 13.394%** at a family of 2,409,955,328 B,
  or the equivalent product against whatever family it registers with its own
  date (§B2.3). Measured: 4.005%. It needs 3.344x.
- **A reason the age distribution moved**, stated as a mechanism and not as a
  number. The deciding run's finding was that **95.66% of the table is younger
  than 14 days** and that this *"is the part of this run that generalises."*
  Nothing reopens on the byte figure alone while that holds.
- **An answer to §9.5's coefficient**, or an explicit acceptance that the prize
  is `estimate x c` with `c` unmeasured.
- **An argument against the non-destructive option** (§B4), which did not exist
  when this document was written and now has to be beaten rather than ignored.

---

## B4. The new fact: consecutive `fair_prices` rows are value-identical 99.7% of the time — measured on one day

**This section records a measurement. It registers nothing, decides nothing and
authorises nothing** (§B7).

### B4.1 The mechanism, verified in source

`write_fair_price` (`backend/runner.py:909`) ends in an **unconditional
`INSERT`, one row per outcome, every call** — `backend/runner.py:980-1000`, a
17-column `INSERT INTO fair_prices` with no prior read of the last row and no
comparison against it. There is no skip path.

`run_pricing_pass` (`backend/runner.py:1804`) is reached from **both** pass
types: `backend/runner.py:3175`, the 900 s full pass, and
`backend/runner.py:3343`, the quote pass. `backend/scheduler.py:276` sets
`DEFAULT_FAST_INTERVAL_S = 15.0`. So while an actionable window is open the
consensus is re-derived and re-inserted every ~15–20 s.

**The inputs cannot have moved on most of those passes.** `MAX_ODDS_AGE_S = 900`
(`fly.live.toml:538`) is the age at which the consensus behind a row is refused,
and the odds feed's floor is a ten-minute cadence with an hourly idle floor
(ADR 0071 §2.6, ADR 0111). A row is re-derived roughly forty times between two
possible movements of the thing it is derived from.

**The repo already holds the change-only pattern, one table over.**
`backend/engine.py:496-500` skips a `recommendations` row identical to the most
recent row for that `(ticker, side)`, on an evidence argument — *"A Ledger where
98% of rows are the same row is unreadable"* — and is careful that the rule is
**consecutive, not global**, so a price that moves 47 → 48 → 47 records three
times. `fair_prices` is the half of that pair that never got it. That asymmetry
is the finding's context and it is checkable in ten seconds.

### B4.2 The three windows

Read-only against live, 2026-09-09, by the lane named in the preamble. Key =
`(link_id, market, outcome_name, outcome_point)`; payload = the 11 value
columns; `computed_ms` and `oldest_book_age_ms` excluded (§B4.5). A
*transition* is one consecutive pair within a key.

| window | ends | span | passes | passes/h | transitions | UNCHANGED |
|---|---|---|---|---|---|---|
| A | 0.3 h ago | 3.98 h | 414 | 104.0 | 199,506 | **99.73%** |
| B | 4.2 h ago | 5.15 h | 420 | 81.6 | 199,504 | **99.61%** |
| C | 22.3 h ago | 2.01 h | 392 | 195.0 | 199,488 | **99.75%** |

Within these three windows the figure is a **census, not a sample**: every
consecutive pair was enumerated. It has no standard error, for the same reason
§5 gives for `eligible_row_fraction`, and printing one beside it would invent a
sampling process that does not exist. Its uncertainty is entirely in
generalisation (§B6), not in estimation.

**The pooled cadence figure does not describe any of the three windows, and the
per-window column is printed above for that reason.** The reported day figure is
**72.3 passes/hour**, p50 gap 21.2 s, ~1,735 distinct `computed_ms` per day
against **96** for the full pass alone — 18.1x. But the windows run at 81.6,
104.0 and 195.0 passes/hour: 72.3/h is a **day average across idle hours at the
900 s cadence**, not a window rate, and the two must not be substituted for each
other. The 2.4x spread across three windows on one day is itself the most
useful thing in the table about how variable this is.

### B4.3 The parts, and the concentration

**Per-group.** `h2h` and `spreads` agree to 2 d.p. inside every window. That
satisfies the repo's *"a pooled number is not a finding until the parts agree"*
for the market split, and only for that split. It is a **within-day** check: it
cannot separate a market effect from a day effect, because there is one day.

**Concentration.** The largest single key holds 1.3–2.6% of all changes, so the
change mass is not concentrated in one market the way two WNBA games once
carried 41% of an actionable population. **Read `n` before that effect size**:
at 99.73% unchanged over 199,506 transitions, window A holds roughly **539
changes**, so "the largest key holds 2.6%" is on the order of **fourteen
events**. That is enough to rule out gross concentration and not enough to rule
out a moderate one.

**The other tail.** 344 of 494 keys — 69.6% — changed **zero** times across
window A. So the unchanged mass is not one quiet market dragging an average
down; most keys contributed no change at all.

**Cluster count: not reported, and therefore no inferential claim.** §3 fixes
the cluster for any inferential claim about this table as **`link_id`**, and 494
keys are not 494 clusters — one game contributes an h2h pair plus every spread
rung. The number of distinct `link_id`s in these windows was not taken, so no
`G` exists and none may be constructed later from the key count. **That is
exactly the `n` inflation §3 was written to block, and this measurement is one
step from committing it.**

### B4.4 The key differs from §4's registered identity by one column

The scan's key is `(link_id, market, outcome_name, outcome_point)`. §4's D4
identity — copied byte-for-byte from `backend/parlays.py:356-357` (F6) — is
`(link_id, market, outcome_name, outcome_description, outcome_point)`.
**`outcome_description` is missing from the scan's key.**

§4 says what dropping it does: *"which is `NULL` on team markets and
load-bearing on props, where it carries the player. Dropping it from the
identity would collapse every player on one prop market into one series."*

**The direction of the resulting error runs against the finding, not toward
it.** `outcome_description` is one of the 11 payload columns, so two rows for
different players in one interleaved series compare as **CHANGED**. The scan
therefore counts transitions that a correctly-keyed scan would not, and 99.7% is
a **floor** with respect to this discrepancy. The magnitude is unknown: the prop
share of these windows was not reported, and on an MLB slate it could be
anything from zero to most of the rows.

**Any implementation derived from this uses §4's identity, not the scan's key.**
The scan's key is adequate for an observation whose error is signed the safe
way. It is not adequate for a rule.

### B4.5 The two excluded columns, and why one of them needs its justification stated as a mechanism

`computed_ms` and `oldest_book_age_ms` were excluded from the payload. The
second exclusion was made with the reason *"including it would find zero
duplicates"*, and **an exclusion justified by the result it prevents is the
shape this document exists to refuse** (§2). It survives, but only because a
mechanism can be stated for it that is independent of the outcome:

- `oldest_book_age_ms` is *"the consensus's own input freshness at
  `computed_ms`"* (`backend/runner.py:936-939`, ADR 0070). Holding the odds
  input fixed, it **increments with wall-clock on every pass by construction**.
  It is a clock reading carried on the row, not a property of the consensus, so
  it cannot be equal across two passes and its inequality carries no information
  about whether the consensus moved.
- **The repo has already made this exact ruling once**, on the table that does
  have change-only insertion. `backend/engine.py:502-505`: *"A candidate whose
  only change is ageing odds — surfaced at 60 s, suppressed at 900 s — records
  once, not twice. The transition is reconstructable from `created_ms` and the
  staleness limits."*

**And the reconstructability claim is weaker here than there, which must be said
now rather than discovered later.** For `fair_prices`, `oldest_book_age_ms` is
reconstructable only against `odds_snapshots.fetched_ms` — the join
`docs/measurements/2026-08-10-sharp-anchoring-census.py:177-191` performs. That
table has **no retention rule** and is named *"deliberately out of scope rather
than forgotten"* (`backend/store/retention.py:53-55`, and §2 here). So the
reconstruction is contingent on another table's continuing lack of a rule, which
is not a guarantee. **A change-only insert on `fair_prices` would discard a
measured column whose recovery depends on a table nobody has promised to keep.**

---

## B5. Why the non-destructive option dominates — the one argument, and its limit

Stated as an argument about SQLite's page allocation, because that is what it
is, and it is **not measured here**:

> A downsample's prize is **freed pages**, and §9.5's revolution coefficient in
> `[0, 1]` multiplies it — *"If the coefficient is 0, the rule buys zero days
> however large the eligible set is."* A dedupe's prize is **bytes never
> written**. A page that is never allocated does not enter the free list, so it
> does not need the list to revolve in order to count.

That is why "delete nothing" is not merely safer here but reaches a different
quantity. It is also the whole of the argument — **and it is an argument about
the slope, not the level.** §B6 puts the limits on it.

**The §9.5 contradiction is noted and not resolved.** §9.5 records that the free
list was *measured* accumulating at **39.7% of organic bytes**, while
`backend/store/retention.py:48-52` *asserts* that freed pages *are* reused so
*"the growth stops even without"* a `VACUUM`. **The measurement and the
assertion disagree, on the record, and `n = 1` window cannot separate them.**
Nothing in this amendment separates them either, and a reported
`auto_vacuum = 0` on the live database (read 2026-09-09 by the same lane; not
independently verified here) is consistent with both — it establishes that only
a `VACUUM` returns bytes to the filesystem, which neither side disputes, and
says nothing about whether the freed pages revolve inside the file.

---

## B6. What this amendment does NOT establish

Drafted in the same posture as §9: written to survive being read by someone
looking for the caveat that was left out.

### B6.1 The 99.7% is one day, and the cluster is the day

Three windows totalling **11.1 hours on 2026-09-09**, an **MLB slate**. Three
windows are **not three independent samples.** They share the slate, the fixture
set, the book set, the odds cadence, the deployed config and the weather. The
clustering variable is the **day**, and **`G = 1`**. Every agreement reported in
§B4.3 is a within-day agreement.

This is the same defect §9.6 registered against the volume clock — *"Every date
in the volume clock's §4 table is one 24-hour window, one MLB slate, one
instrument"* — and §B2.1 shows what it cost there: a rate that was a floor by a
factor of two. **The recurrence is the point.** A second day is the cheapest
improvement available to anyone who wants this figure to mean more, exactly as
it was for the clock.

### B6.2 It does not establish the rate on an NFL Sunday, which is the case that differs most

The quantity being measured is *how often the consensus moves between two
15-second passes*, and the window profile is the input that most directly drives
it. An NFL Sunday plans **3 kickoff clusters, the season's worst 4**, each a
60-minute window of seven calls (CLAUDE.md; `tests/test_sweep_timing.py` pins
the seven). That is a different arrival process for the odds, a different
concurrency of open windows, and a different market mix.

**Nothing here bounds the figure on that day in either direction**, and a
successor registration that samples only MLB days has chosen its population
after seeing which population was convenient.

### B6.3 It does not establish that a dedupe reclaims a single existing byte

It reclaims none. A dedupe **deletes nothing**, so it produces no freed page and
touches no row already written. `fair_prices` was 1,705,545,728 B on 2026-09-09
and would still be 1,705,545,728 B the instant after a dedupe shipped.

**It changes the slope, not the level**, and only from the moment it ships. Any
sentence of the form "this would save N bytes" is a statement about a future
interval and must name the interval.

### B6.4 It does not establish a byte figure at all, and none may be quoted from it

Two model steps separate the measured row rate from any byte claim, and neither
has been taken:

1. **Row rate to byte rate.** 99.7% is a share of *rows*. Converting it to a
   share of *bytes* inherits §5's *"bytes per row are uniform across the table
   and both indexes"* assumption, which §9.2 says nothing tests, and §B2.1 shows
   the family composition moving 1.5% in eight days.
2. **Window rate to day rate.** The measurement is over in-play windows at
   82–195 passes/hour. The day contains idle hours at the 900 s cadence. A day
   figure requires the window/idle mix, which is not reported here.

**No byte figure derived from this measurement may be quoted anywhere until a
successor registration fixes both steps in advance.** That includes the arming
question in §B3: the dedupe's dominance there rests on it deleting nothing and
foreclosing nothing, not on it being larger.

### B6.5 It does not establish that a dedupe is safe, and it forecloses the same question §9.1 names

**The symmetry, stated because the tidy version of this finding omits it.** §9.1
is the downsample's permanent cost: for rows older than the window, the
intra-day series is gone, and
`docs/measurements/2026-08-10-sharp-anchoring-census.py:177-191` — which walks
every `h2h` row and matches each `computed_ms` to the odds instant it consumed,
and which produced ADR 0021 §8's 73.0% — could not be re-run.

**A change-only insert forecloses the same class of question prospectively.** A
pass that writes no row leaves no trace, so from the day it ships the record no
longer says *which fetch instants the runner consumed*, only *when the answer
changed*. That is 99.7% of the evidence that census reads, going forward. The
downsample destroys it backwards; a dedupe declines to record it forwards.
**Neither is free, and a proposal that presents the dedupe as costless has
omitted this.**

Also unestablished: which production readers of `fair_prices` (F2) depend on
row *cadence* rather than row *content*, and whether the parlay desk's
`CANDIDATE_SQL` behaves identically against a sparser series. F2 enumerated
readers for a **deletion** rule. It has not been re-run against a **write-rate**
change, and P1 does not cover that question.

### B6.6 It does not reopen anything §6 closed

The downsample verdict is `NOT WORTH ARMING` and this amendment leaves it there.
A better alternative existing is not evidence that the closed option was
mis-judged, and §B3.3's grounds are corroboration rather than re-decision.

---

## B7. This is an observation, not a registered test — what a successor must fix in advance

**No threshold was named before the 99.7% was computed.** There is therefore no
decision rule it can satisfy, and it cannot arm, authorise or fund anything.
Written down plainly because a measured number with no registered threshold is
the exact input that acquires one after the fact.

A successor registration — its own file under `docs/measurements/`, dated,
committed **before** the run — would have to fix at minimum:

1. **The claim, one-sided and falsifiable**, as a statement about a *slope*:
   e.g. "the daily `fair_prices` byte growth under change-only insertion is at
   most X% of the observed rate", with X named first.
2. **The identity**, which is §4's, `outcome_description` included (§B4.4).
3. **The payload column set**, enumerated, with an explicit ruling on
   `computed_ms` and `oldest_book_age_ms` and the reconstructability argument of
   §B4.5 stated as a mechanism.
4. **The unit and the cluster: the day**, with the number of days and the
   requirement that **at least one is an NFL Sunday** fixed in advance, and the
   per-`link_id` view printed beside every aggregate.
5. **The stopping rule**: a date or a day count, not "when it looks stable."
6. **The multiplicity**: markets x windows x days is a cell count, and it should
   be computed before the run rather than after.
7. **The prospective §9.1 cost** (§B6.5), accepted explicitly by a named human,
   because it is the same class of irreversible information loss this document
   refused to grant the downsample — it merely arrives through a different door.
8. **The negative branch's destination**, fixed before the run.

Until that exists, the correct status of the dedupe is: **a measured property of
one day, an argued structural advantage over the downsample, and an unbuilt,
unregistered, unauthorised change.**

---

## B8. Blast radius — what this amendment does not change

Exhaustive by section, in the form §A10 used:

- **§§1–5** — both conjuncts of §1, the population, the units, the census-not-a-
  sample rule, the `link_id` cluster, D1–D6, `RETENTION_DAYS = 14`, the
  sensitivity set `{7, 21, 28, 60}`, and **§5's `estimated_freed_bytes` formula
  including the constant `899,887,104`** (§B2).
- **§6 — byte-for-byte, not one character**, for both of §A10's reasons: a
  post-hoc amendment must not reach the rule it is judged by, and
  `scripts/dry_run_fair_price_downsample.py::_section()` reproduces §6 and §9
  **verbatim into every run's output**, so editing either would change the text
  printed beside figures already published.
- **§7** — the stopping rule, the "first dry-run" wording, the **2026-09-14**
  expiry, the ENOSPC void. §B3.5 relies on §7 rather than moving it.
- **§8** — the falsification list and the single result destination, which has
  been written.
- **§9 — 9.1 through 9.7, verbatim.** §B6 is additional and subordinate; where
  §B5 touches §9.5 it records the contradiction and resolves nothing.
- **The power check** — including §3's timing arithmetic, which the deciding run
  sharpened to a measured 95.66%.
- **S1** — unchanged. **This amendment adds no fenced `sql` block, deliberately**:
  `test_the_sql_is_section_s1_of_the_registration_byte_for_byte` compares the
  module against the **last** fenced `sql` block in this file, and an amendment
  that added one would silently become the registered query.
- **P1–P6, P6b** — as Amendment 1 left them.
- **Arming** — still not authorised, and now **closed** (§B3). Nothing here
  permits a single row to be deleted, and §6's prohibition on wiring
  `backend/store/volume.py` to the deletion path stands.
- **`backend/gate.py`** — untouched. A different number for a different
  decision.
- **No code.** This amendment edits no file but this one. It authorises no edit
  to `FAIR_PRICE_FAMILY_BYTES` (it forbids one), no edit to the harness, no
  environment change on live, and no dedupe.

**One thing outside this document is flagged and not owned here.**
`fly.live.toml:660-661` reasons from the 161.40 MB/day figure that *"the 10GB
volume runs to roughly mid-November"*. The realised file rate is 326.6 MB/day
(§B2.1), 2.02x that. The comment's arithmetic is superseded by the same
correction that supersedes the family constant. **That is a note, not an edit
and not a task**; whoever next touches that block owns it.

---

## B9. Registration record for this amendment

```
amendment          2
date               2026-09-09
changes            nothing in sections 1-9, S1, P1-P6b, or the thresholds
records            three things: a byte ruling, a closure, and an observation

FAIR_PRICE_FAMILY_BYTES
  registered       899,887,104   (family, live 2026-09-01T~16:40Z)
  live now         2,409,955,328 (family, live 2026-09-09T~19:49Z, 2.678x)
  ruling           STAYS PINNED. Superseded as a description of the table;
                   unchanged as the estimator's input. Raising it re-scales a
                   verdict computed after the rows were seen.
  invariance       verdict is NOT WORTH ARMING under both. At the 2026-09-09
                   family the eligible fraction would have to reach 13.394%;
                   measured 4.005%; multiple required 3.344x.
  direction        the pinned value makes the estimator a FLOOR, so a FAIL
                   against the threshold fails a fortiori
  discharges       the "amendment owed" note at
                   backend/store/fair_price_downsample.py:203-216

ARMING
  status           CLOSED, by section 6's own NOT WORTH ARMING branch on the
                   deciding run -- not by this amendment
  figure           36,039,175 B against 322,800,000 B, 11.2%; T-MECH 98.68% PASS
  ADR owed         NONE. Section 6 authorises an arming ADR only on a verdict of
                   ELIGIBLE TO PROPOSE ARMING, which was not returned.
  retracted        "arming is a week of engineering" is FALSE. `run` is reached
                   at runner.py:3168 <- run_once <- run_loop.py:1458 and refuses
                   at fair_price_downsample.py:672 on an env default. Cost was
                   never the reason and may not be cited as one.
  also verified    the `enabled` check precedes the `dry_run` branch, so the
                   live loop has never executed the dry read either
  module           STAYS IN THE TREE, disabled and unarmed. Not dead code: it
                   carries the SQL that section S1 is pinned to by test.
  reopens only on  a successor registration (section 7 has spent this one) with
                   an eligible fraction >= 13.394% and a stated mechanism for
                   why the age distribution moved

DEDUPE OBSERVATION
  mechanism        write_fair_price (runner.py:909) ends in an unconditional
                   INSERT per outcome; run_pricing_pass is reached from the
                   900s full pass AND the 15s quote pass (scheduler.py:276)
  windows          A 3.98h 99.73% | B 5.15h 99.61% | C 2.01h 99.75% UNCHANGED
  per-group        h2h and spreads agree to 2dp in every window (within-day)
  concentration    largest key 1.3-2.6% of changes; that is ~14 events in
                   window A, enough to rule out gross concentration only
  zero-change keys 344 of 494 in window A
  cadence          72.3 passes/h is a DAY average; the windows run 82-195/h
  cluster          the DAY. G = 1. No inferential claim is available.
  key defect       omits outcome_description, which section 4 requires; the
                   error is signed AGAINST the finding, so 99.7% is a floor
  status           OBSERVATION. No threshold was fixed before it was computed,
                   so it registers no test and authorises nothing.
  does not show    the NFL-Sunday rate; any reclaimed byte (slope, not level);
                   any byte figure at all without two unfixed model steps; that
                   a dedupe is safe -- it forecloses section 9.1's question
                   PROSPECTIVELY, which the tidy version of this finding omits
  unresolved       section 9.5's contradiction stands: measured accumulating at
                   39.7% of organic bytes vs retention.py:48-52's assertion that
                   freed pages are reused. n = 1 window cannot separate them.

provenance         the 2026-09-09 db-sizes read and the three-window scan were
                   taken by another session, read-only on live. The source
                   claims -- the constant, the reachability, the check ordering,
                   the unconditional INSERT, the two callers, the 15s cadence --
                   were verified here directly.
```
