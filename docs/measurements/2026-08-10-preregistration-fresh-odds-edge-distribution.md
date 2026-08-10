# Pre-registration — the fresh-odds edge distribution

**Written 2026-08-10.** `tasks/NEXT.md` item 2.

**Status: registered. RUNNABLE for the composition print (Stage A) today.
BLOCKED for the primary (Stage B) on full-table access.** See §P and the power
check. Nothing here may be run against the newest-1,000 slice and reported as a
property of the table.

> **AMENDMENT 1, 2026-08-10 — read it before reading anything below.**
> The alpha of the single interval test moves from **0.05 to 0.0167**, because
> a second registration now shares this project's alpha budget. Five passages
> are marked in place with a pointer and **none has been deleted**; the
> amendment is appended at the end of this file and it, not the original text,
> governs. **No threshold, floor, branch or bucket edge moves.**
> **No data had been observed when it was written.**
> See [Amendment 1](#amendment-1--2026-08-10).

- Owner: `pre-registrar` (agent), on behalf of Joe.
- Scored against by: `measurement-skeptic`, after the run.
- Negative-result destination: fixed in §9, before the result exists.
- Form matched to `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`
  and its **Amendment 1**, whose defect **D1** — a `NOT IN` predicate against a
  comma-joined composite column — is the same hazard this document faces and
  §2 discharges explicitly.

---

## §0. What had already been observed when this was written

**This is not a blind registration and saying otherwise would be false.** The
CLV registration could open with "no data was observed, at any point, by
anyone". This one cannot: the live evidence record has been read repeatedly this
session, over HTTP, with a real token. A reader has to be able to judge what was
knowable when these rules were set, so everything seen is listed here.

### §0.1 Seen — the whole table, as of 2026-08-10

**[MEASURED FROM DATA — `/api/gate` and `/api/ledger`, live, this session]**

```
populations   actionable 0     no_edge 614     suppressed 915     total 1529
horizons      "0" 532          "1" 569         unscored 428
gate          actionable 0g/0r   no_edge 20g/279r   suppressed 25g/253r
              29 scored games in total, none actionable
freshness     stale_odds on 575 of the newest 1,000 rows
composites    160 of those 575 (27.8%) carry stale_odds inside a comma-joined
              composite reason
```

`actionable` has been **0 for the entire life of the record** — not zero in a
window, zero always, across 1,529 rows.

### §0.2 Seen — earlier reads, same session, same table

1,462 rows / horizon `"0"` 476, and 1,520 rows / horizon `"0"` 532. Both are
the same growing table at earlier instants. Row-count deltas between them have
**not** been audited and are not used here.

### §0.3 What follows deductively from §0.1, before any new data is pulled

This is the most contaminating thing in this document and it is stated up front
rather than discovered halfway through the analysis.

**[COMPUTED FROM CODE]** `core/sizing.py:156` prices every sizing decision at
`effective_price(ask_tenths, contracts=1)` — always one contract, whatever the
order size. At the reference profile (`REFERENCE_BANKROLL_DOLLARS = 1000.0`,
`kelly_fraction = 0.25`, caps 100/400/50), `size_position` returns
`contracts >= 1` at a post-fee edge of **0.1 tenths** at every price from 20.0c
to 80.0c — the smallest increment there is. And `engine.py:207` zeroes
`reference_contracts` whenever any suppression code fires.

Therefore, on the live record:

```
actionable  ==  (no suppression code)  AND  (post-fee n=1 edge > 0)
```

and since `actionable` has been 0 across 1,529 rows, **every unsuppressed row in
the record already has a non-positive n=1 post-fee edge.** That is not a
prediction; it is arithmetic on a counter that has been read.

**Two consequences, both binding on the design:**

- A registration whose headline question were "does any unsuppressed fresh row
  clear the bar" would be asking a question already answered. It is not asked.
  What is asked is **how far below the bar, and whether the unresolved fee model
  can reach it** (§1) — quantities the counter does not determine.
- The `suppressed` population is **not** covered by the derivation. A suppressed
  row can carry a large positive edge (`suspicious_edge` fires strictly *above*
  +40 tenths). Branch C of §7 lives entirely there and its answer is open.

### §0.4 What has NOT been seen, by anyone

No distribution, histogram, quantile, mean, or per-row value of `edge_tenths`,
`entry_ask_tenths` or `fair_probability` has been read, computed or estimated
from the record. No per-row payload has been inspected. No count of distinct
games in the *unscored* portion of the table exists. **`G` for this measurement
is unknown.**

Every fee, sizing and boundary number below was produced by executing project
code on inputs chosen here — `calculate_fee`, `fee_candidates`,
`effective_price`, `size_position`, `always_valid_multiplier` — and is labelled
**[COMPUTED FROM CODE]**. Those are properties of the repository, reproducible
from it alone, and blind to the record.

### §0.5 Provenance labels, and the count of the third kind

`tasks/lessons.md`: *arithmetic that reproduces to the digit says nothing about
its inputs.* Four documents were audited recently, the arithmetic reproduced
exactly in all four, and the conclusions were still wrong because inputs from
outside the code were assumed and unlabelled — one spurious-slope estimate off
by ~230x from a single guessed factor.

Every quantity in this document is labelled **[COMPUTED FROM CODE]**,
**[MEASURED FROM DATA]** or **[ASSUMED]**.

**There is exactly one assumed input in the whole design: `sigma`, the
between-game standard deviation of the per-game mean edge.** It is not
measured anywhere in this repo — grepped: `docs/adr/**` and
`docs/measurements/**` contain no measurement of the dispersion of
`edge_tenths`, and `docs/adr/0017` Addendum A is explicit that nobody has even
counted the rows in a band. It therefore appears **only** as a free parameter of
the power table (a column, never a point), and it is a **required print before
any verdict** (§S2). No threshold in §7 depends on its value.

---

## §C. Corrections to the brief, made before the design was fixed

Three things in the task as handed over are wrong or incomplete. Recorded rather
than quietly fixed, because the brief will be read again.

### C1. "Just under the bar" is 10.0 tenths or 0.0 tenths, not 0.38 points

The brief frames branch 1 as *"edges cluster just under the bar → the fee-model
question decides everything"*, with the bar at 52.00% against 52.38% and 0.38
points of headroom. The 0.38 is right about the **venue** and wrong as the width
of the band the four trades can decide.

**[COMPUTED FROM CODE — `fee_candidates`, exhaustive over all 999 tradeable
prices, at one contract]** the gap between the most and least expensive
candidate fee model, per contract, in tenths of a cent:

| price band | model gap Δ at n=1 |
|---|---:|
| 0.1c – 9.1c | **10.0** |
| 9.2c – 17.2c | **0.0** |
| 17.3c – 49.9c | **10.0** |
| **exactly 50.0c** | **0.0** |
| 50.1c – 82.7c | **10.0** |
| 82.8c – 90.8c | **0.0** |
| 90.9c – 99.9c | **10.0** |

Model A is the maximum at **all 999 prices** at n=1 (0 exceptions; independently
recorded in `docs/adr/0017` Addendum A), so the cheapest candidate is always
Model B and Δ = A − B.

Two things follow, and the second is the one that decides the design:

1. **The band is quantised to a whole cent.** Kalshi charges whole cents and
   both models round; at one contract the fee-model question is worth exactly
   1.0c per contract or exactly nothing. A "cluster just under the bar" analysis
   with a 3.8-tenth window would be measuring the wrong interval.
2. **At exactly 50.0c the fee-model question is worth zero**, and
   `effective_price(500, 1)` is **52.00%** under both models
   **[COMPUTED FROM CODE]** — which is where CLAUDE.md's bar comes from. So in
   the middle of the band this strategy actually trades, resolving the fee model
   **cannot move a single row**. The same is true on 9.2–17.2c and 82.8–90.8c.

### C2. The control must be able to reach the confound — and here it provably cannot everywhere

`tasks/lessons.md`: *a control must be able to reach the confound it was built
for*; a previous control's entire domain sat inside the region where the effect
could not appear, and its empty cells were printed as evidence of flatness.

C1 makes that concrete and pre-computable. **The fee-model branch has a
reachable domain and an unreachable one, known before any data is pulled:**

- **Reachable:** rows priced in `[173, 500)` or `(500, 828)` tenths (plus the
  far wings), where Δ = 10.0. A row here can flip.
- **Unreachable by construction:** rows at exactly 500 tenths, or in
  `[92, 173)` or `[828, 909)`. A row here can **never** flip, at any edge.

**Registered consequence (§7, branch A):** the count of fresh rows in the
reachable domain is printed **before** the flip count, and a flip count of zero
is a refutation **only if** the reachable domain is non-empty. If it is empty,
the answer is UNRESOLVED and the write-up says the instrument could not have
seen the effect.

### C3. League is not a column on `recommendations`, and the stored league label is unreliable

The brief requires league as a stratum. `recommendations` has no league column.
Reaching one requires `kalshi_markets → kalshi_events → kalshi_series.league`,
which is **not exposed by any `/api/*` route** and which `tasks/NEXT.md` records
as written **on first insert only** — so for NFL, where two league strings share
one series ticker, the stored label freezes on whichever population was seen
first and relabels both, retroactively, at read time.

**Registered substitute:** the stratum is the **series prefix of the market
ticker** — the substring before the first `-` — used verbatim as a raw string
and never mapped. **[COMPUTED FROM CODE — 702 real tickers in
`tests/fixtures/`]** every market ticker has the shape
`<SERIES>-<DATE+TEAMS>-<OUTCOME>` and every event ticker the shape
`<SERIES>-<DATE+TEAMS>`, e.g. `KXMLBGAME-26AUG09DETSEA-SEA`. `KXMLBGAME` and
`KXWNBAGAME` are unambiguous; no mapping table is consulted and no NFL
preseason/regular-season distinction is claimed.

---

## §P. Prerequisites — checked before the primary is permitted to run

Each is a yes/no. If any is NO the primary does not run and this document is
amended rather than worked around.

- **P1 — full-table access.** `/api/ledger` caps at `limit <= 1000`
  **[COMPUTED FROM CODE — `routes.py:634`, `Query(200, le=1000)`]** against a
  table of 1,529 rows **[MEASURED]**, and there is no `offset`. The primary
  requires **every** row of `recommendations`, reached by either (a) the ledger
  `offset` parameter shipping, or (b) a direct read of the volume. **Until then
  Stage B does not run.** Stage A (§S2 items 1–4, composition only) may run on
  the newest-1,000 slice and its output is prefixed
  `NEWEST-1,000 SLICE — NOT A PROPERTY OF THE TABLE`.
- **P2 — the cluster key is real, not regexed.** The registered key is
  `COALESCE(kalshi_markets.event_ticker, recommendations.ticker)` (§4). Over
  HTTP only `ticker` is available, so the HTTP-derived key is a **fallback**
  (§4) and its disagreement rate with the real key must be reported the first
  time both are available. The previous project's game key
  *"never matched a market ticker at all, and where it matched it chopped a
  fixed three characters"*, inflating `G` — the flattering direction.
- **P3 — `entry_ask_tenths` is within `[10, 989]` on the rows analysed.** Rows
  outside are excluded (§2). Report the excluded count. `effective_price` raises
  on an untradeable price rather than pricing it at a zero fee, so an
  out-of-range row would abort the recomputation rather than silently produce a
  fabricated edge — but it must be counted, not caught.
- **P4 — `fair_probability` is non-NULL on every analysed row.** It is
  `NOT NULL` in the schema **[COMPUTED FROM CODE — `schema.sql:365`]**, so this
  is an assertion that should never fire. If it fires, the row is dropped and
  counted, never imputed.

---

## §1. The question, as a claim that could be false

**Primary hypothesis, one-sided:**

> Among rows whose sportsbook consensus was fresh, the mean across **games** of
> the per-game mean post-fee edge, recomputed at a fixed size of one contract,
> is **below −10.0 tenths of a cent** — that is, below the widest amount the
> unresolved fee model is worth at that size (§C1).

Written as a claim that can come back false in a stated direction: the estimand
is `M`, the mean over game-clusters of the per-cluster mean of `E1` (§6), and
the registered claim is `M < -10.0` tenths. `M >= -10.0` is a live outcome and
is not a failure of the measurement.

**Why −10.0 and not 0.** Zero is the break-even bar and a mean below zero is
already implied for the unsuppressed population by §0.3, so testing against zero
would test something already known. −10.0 tenths is the threshold at which the
answer stops depending on the unresolved fee model: below it, the cheapest
candidate model cannot rescue the typical game **even at the prices where it is
worth a full cent**. That threshold is **[COMPUTED FROM CODE]**, fixed here, and
does not move.

**Two subordinate questions, both registered here and neither able to substitute
for the primary:**

- **A — reachability.** How many fresh games contain at least one row that is
  not actionable under the maximum-fee model and **is** actionable under the
  cheapest candidate, at the reference profile? A count, not a rate.
- **C — composition.** Among fresh rows whose recomputed edge is **positive**,
  which suppression code is carried most often, and over how many games? A
  description, not a test.

---

## §2. The population, and the exclusions

### The predicate, written correctly against a composite column

`SuppressionResult.reason` is `",".join(c.name for c in self.failures)`
**[COMPUTED FROM CODE — `core/suppression.py`]**: a comma-joined composite of
**every** check that failed, not one code. All checks run deliberately, so
staleness co-occurs with other failures by construction. **[MEASURED]** 160 of
the 575 recent rows carrying `stale_odds` carry it inside a composite — 27.8%.

**A `NOT IN ('stale_odds')` predicate retains every one of those 160 rows.**
That is defect **D1** of Amendment 1 to the CLV registration; it was real,
material, and it is the same hazard here. It is not repeated.

**The governing predicate — a delimited whole-field substring test:**

```sql
AND (r.suppressed_reason IS NULL
     OR instr(',' || r.suppressed_reason || ',', ',stale_odds,') = 0)
```

- **`instr`, not `LIKE`, and it is not style.** SQLite `LIKE` reads `_` as a
  single-character wildcard and every code in this vocabulary contains
  underscores, so `'%,stale_odds,%'` also matches `,staleXodds,`. No colliding
  code exists today, which is exactly the problem: a predicate correct only
  because nobody has added a colliding name has a trap in it.
- **The delimiting commas are required in both directions.** Without them a
  future `stale_odds_upstream` would be silently excluded.
- **The vocabulary it must survive:** eleven codes from `core/suppression.py`
  — `stale_kalshi_quote`, `stale_odds`, `no_commence_time`, `commence_skew`,
  `no_depth`, `insufficient_depth`, `too_few_books`, `no_market_width`,
  `wide_market`, `edge_within_method_noise`, `suspicious_edge`
  **[COMPUTED FROM CODE — extracted from the `Check(...)` constructors]** —
  plus `sizing:refused` from `engine.py` and `skeptic_defect` /
  `skeptic_suspicious`, which `agents/skeptic.py:200` appends **with a comma**
  onto whatever reason already exists. Fourteen strings; Amendment 1 §A2
  tabulates them as thirteen rows by grouping the two skeptic tags.
- **The same test is applied in Python, not re-expressed.** If the population is
  built from an HTTP payload rather than SQL, the predicate is
  `"stale_odds" not in (row["suppressed_reason"] or "").split(",")` — exact
  token match on the split, which is the same rule and has no wildcard surface.

### Included

Every row of `recommendations` with

- the freshness predicate above, **and**
- `entry_ask_tenths BETWEEN 10 AND 989`, **and**
- `fair_probability IS NOT NULL`.

**No CLV requirement, and no horizon filter.** The edge exists on every row at
creation time; scoring is a later and separate event. Restricting to scored rows
would cut the population to the 29 games that happen to have been scored and
would import ADR 0011's horizon mixture into a question that does not need it.
Horizon is a **stratum** here (§3), not a filter.

### Excluded, with the reason each exclusion is independent of the outcome

| Excluded | Why | Independent of the edge? |
|---|---|---|
| `stale_odds` anywhere in the composite | The consensus behind `fair_probability` had aged past `MAX_ODDS_AGE_S = 900` **[COMPUTED FROM CODE — `fly.live.toml:128`]**, so part of the apparent edge is drift that has already happened. This is the definition of the population, not a convenience. | Yes — a function of input timestamps only, evaluated before the edge is computed. |
| `entry_ask_tenths` outside `[10, 989]` | 0 and 1000 are settled outcomes, not quotes; `is_valid_price` rejects them and `effective_price` raises rather than pricing at a zero fee. Also keeps the pooled population and the bucket grids on the same rows, which Amendment 1 §A2.2 found the CLV registration had failed to do. | Yes — a property of the stored price alone. |

### Retained deliberately

**Every other suppression code is retained**, including `stale_kalshi_quote`.
The question as posed is about **odds** freshness; excluding a second code would
answer a different question and would do it after the fact.

`stale_kalshi_quote` nevertheless contaminates the *ask*, which is half of the
edge, so it is registered as a **mandatory sensitivity group** (§7): the primary
is re-run with it excluded, and a verdict that does not survive that re-run is
downgraded to UNRESOLVED. That is Amendment 1 §A4's leave-one-group-out rule,
reused rather than reinvented.

### A rule that must not be activated after the fact

If the sample comes in thin the temptation will be to relax the freshness
predicate to recover `n`. **That is forbidden.** The precedent is in this repo:
a combo experiment pre-registered an exclusion and the agent correctly refused
to activate it when the sample turned out too thin. Refusing was only possible
because the rule was in writing first.

**No exclusion in this document references `clv_tenths`, `settled_win`, the
stored `edge_tenths`, or any outcome.** Every one is decidable from the row's
inputs.

---

## §3. The sampling frame and its strata

**This repo has a scar here and it is the reason this section exists.** A
measurement fixed its analysis and not its frame, drew "the first 20 eligible
rows in discovery order" from a concatenated list, filled entirely from one
stratum, and transferred the interval to a population that was 66% the other.

**The frame is the whole table, not a draw from it.** No sampling, no ordering,
no cap: every row satisfying §2 enters. That removes the discovery-order failure
by construction — but it does **not** remove it from a run made over HTTP today,
which is why P1 blocks the primary.

### The strata, with the expected share of each

**The composition is printed before any rate.** Not beside it, not after it —
before. A rate whose frame has not been printed is a rate about an unknown
population.

| Stratum | Levels | Expected share | Provenance |
|---|---|---|---|
| **Horizon** | `0`, `1`, unscored | 532 / 569 / 428 of 1529 = **34.8% / 37.2% / 28.0%** | **[MEASURED FROM DATA — §0.1, whole table]** |
| **League** | series prefix of the ticker (§C3) | **unknown** | Never measured. Must be printed. |
| **Bankroll era** | pre / boundary / post | **unknown** | Never measured. Must be printed. |
| **Freshness** | fresh / stale (the §2 split) | ~42.5% fresh | **[MEASURED FROM DATA — 575 of the newest 1,000 carry `stale_odds`; this is a **slice** figure and is not a property of the table]** |
| **Strategy config version** | integer | unknown | Must be printed; more than one value means the record is a mixture. |

### The bankroll era, defined mechanically

`BANKROLL_DOLLARS` went 1000 → 100 in `78b5790`, committed
**2026-08-09 18:52:58Z** **[COMPUTED FROM CODE — `git log -G BANKROLL_DOLLARS --
fly.live.toml`]** and deployed at **~19:48Z** **[ASSUMED — read off a handoff
note in `tasks/NEXT.md`, not measured; no deploy timestamp is recorded in the
database]**. Because the deploy instant is approximate, three levels, not two:

| Level | Rule on `created_ms` |
|---|---|
| `pre` (definitely $1,000) | `< 1786301578000` (the commit instant) |
| `boundary` (unassignable) | `>= 1786301578000` and `< 1786308480000` (deploy + 1h) |
| `post` (definitely $100) | `>= 1786308480000` |

`boundary` rows are **retained and reported separately**, never assigned to
either era. Assigning them would be a guess wearing a label.

**Why the era matters even though the primary recomputes the edge.** `E1` (§6)
is recomputed from `(entry_ask_tenths, fair_probability)` and is therefore
**invariant to the bankroll** — that is one of the reasons for recomputing. The
era still selects *which rows exist*, because `suspicious_edge` and
`edge_within_method_noise` fire on the stored, bankroll-dependent edge. So the
era is a population-membership stratum, not a scale stratum, and it is printed
for that reason.

### The size-bias warning that applies to any HTTP run

`/api/ledger` returns the **newest** 1,000 rows ordered by `created_ms DESC`. It
is a recency selection, not a random sample: it takes recent games whole and
older games not at all, truncating exactly one game at the boundary. Two
consequences, both registered:

- The slice is **plausibly one bankroll-era stratum in its entirety** — the
  exact failure the scar above describes. The era composition print is what
  detects it.
- Row-level rates over the slice are dominated by games that generated many
  rows. That is why every quantity in §6 is computed **per cluster first**.

---

## §4. The unit of observation

**The unit is the game. The clustering variable is
`COALESCE(kalshi_markets.event_ticker, recommendations.ticker)`** — the same key
`gate.clustered_clv` uses, reused verbatim so it cannot be re-chosen.

Two rows are independent only if they come from different event tickers. A
game's markets resolve from one final score and their prices move together; a
poller writing rows on a timer measures uptime. This repo shipped a gate that
counted 400 rows on one ticker as 400 observations and the fix was clustering by
game.

**`n_rows` and `n_clusters` are printed side by side, always, everywhere.**
"412 of 300" on one screen beside "9 of 300" on another is how the flattering
number gets believed.

### The HTTP fallback key, and its two known defects

Over HTTP only `ticker` is available. The fallback key is: **split on `-`; if
there are three or more segments, drop the last one; otherwise use the string
unchanged.** **[COMPUTED FROM CODE — 702 real tickers in `tests/fixtures/`]**
`KXMLBGAME-26AUG09DETSEA-SEA` → `KXMLBGAME-26AUG09DETSEA`, and
`KXATPMATCH-26AUG09FONSHE` (already an event ticker) is left alone. No fixed
character count is chopped; that was the previous project's bug.

Two defects are registered rather than discovered later:

1. **The event ticker carries the series prefix**, so if the recorder ever
   writes rows about spreads or totals, one game becomes up to three clusters
   and `G` is inflated — the flattering direction, because it shrinks the
   cluster-robust error. **Mandatory print:** the distinct series prefixes
   present, and the number of `<DATE+TEAMS>` suffixes appearing under more than
   one prefix. A non-zero count there means `G` is inflated and the write-up
   must say by how much. This defect is present in the SQL key too — it is a
   property of Kalshi's event tickers, not of the fallback.
2. The fallback cannot see a market whose stored `event_ticker` differs from its
   ticker prefix. P2 requires the disagreement rate the first time both keys are
   computable.

**Fewer than 2 clusters returns `None`, never a number.**

---

## §5. The cut — bucket edges, fixed in advance

Bucket boundaries are the richest source of unearned findings because there are
many defensible ones and they can be tried in sequence. Two grids, both fixed
here, neither able to produce a finding.

**Bucketing is on `entry_ask_tenths` — the derived ask, the price actually paid,
never a mid.** A bucket in the predecessor project showed a +25.4 point edge and
lost money for exactly this reason.

### Grid F — the fee-model-homogeneous partition at n=1

Seven cells, **derived from `fee_candidates`, not chosen from data**
**[COMPUTED FROM CODE — §C1, exhaustive over all 999 prices]**. Δ is the
per-contract model gap in tenths:

```
[10, 92)    Δ=10      [92, 173)   Δ=0       [173, 500)  Δ=10
[500, 501)  Δ=0                                                  <- exactly 50.0c
[501, 828)  Δ=10      [828, 909)  Δ=0       [909, 990)  Δ=10
```

This is the coarsest partition on which the quantity branch A depends is
constant. The three `Δ=0` cells are the **unreachable domain** of §C2 and are
labelled as such in every table they appear in.

### Grid B — `analysis.validate.BUCKETS`, verbatim

Ten 10c buckets from 10 to 990, reused rather than restated so it cannot be
re-chosen. **Descriptive only, at any `n`.**

### No other cut

**No cut may be introduced after the data is read.** Not by side, not by day,
not by time to kickoff, not by depth, not by a re-derivation of Grid F at a
different contract size. Each of those is defensible and that is the problem.

Grid F is explicitly **not** re-derived at n=10 after the fact: at n=10 the
model gap is a 40-segment sawtooth running 0–8 tenths **[COMPUTED FROM CODE]**,
and choosing that partition after learning the shape of the fee curve is
choosing a cut with knowledge of the data-generating process.

---

## §6. The statistic, named as an estimator

### The edge is RECOMPUTED, never read from the stored column

This is the section the brief warns is left to the analyst. It is not left open.

`schema.sql:375-383` says it plainly: `edge_tenths` is *"a per-contract edge at
ONE specific size, which the column does not carry"* — `engine.py` computes it
at `max(1, sizing.contracts)`, the fee's per-order rounding is size-dependent,
so two rows with different sizes are not on the same scale, and the divisor is
**not recoverable from the row** (`suggested_contracts` is the post-suppression
number, zeroed on exactly the rows this population is full of). Amendment 1
§A5.1 measured the resulting steps at up to **5.0 tenths**, price-dependent,
zero at 50c, and **non-monotonic** at 30c and 70c.

**Registered decision: the stored `edge_tenths` column is not used for any
quantity in §7.** Every edge is recomputed, per row, at a fixed size:

```python
E1  = core.ev.edge_after_fees_tenths(
          ask_tenths=entry_ask_tenths, contracts=1,
          fair_probability=fair_probability, maker=False)
```

`E1` is in **tenths of a cent per contract, net of the maximum-model fee**, and
it is on one scale for every row in the record because the size is fixed by this
document rather than by the operator's account state at the instant of the pass.

- **n=1 is the primary and the reason is not convenience.** It is the most
  conservative per-contract fee any order size pays
  (`ceil_cent(a·N) <= ceil_cent(a)·N`, and Model B is linear in `N`), it is what
  `size_position` itself prices at, and it is the basis on which most of the
  record was written. `docs/adr/0017` Addendum A reaches n=1 for the deployed
  profile independently.
- **n=10 is a registered secondary**, reported and non-decision-bearing, chosen
  to match ADR 0017 §1's figure so the two documents are commensurable. It
  cannot change a verdict.
- **The add-back is forbidden.** Reconstructing a gross edge as
  `edge_tenths + fee_predicted` is exact at N=1 and silently enormous otherwise
  — ADR 0017 Addendum A gives 208 tenths against a true 28 — and the N is not in
  the row.
- `E1min` is the same quantity computed against the **cheapest** candidate fee
  model, obtained by substituting `backend.core.ev.settlement_fee` with a
  Model-B-only implementation (`fees._model_b`) for the duration of the
  recomputation. `E1min - E1 = Δ(price)` from §C1, which is an assertable
  invariant, not a hope.

### The estimators, said out loud

Each has a different null and they are not interchangeable.

| Quantity | Estimator | Null | Standing |
|---|---|---|---|
| `M` | **a mean of game-clustered per-cluster means of `E1`** | `M = -10.0` tenths (§1) | **PRIMARY.** The only interval test in the design. |
| `A` | **a count of clusters** with ≥1 flip-to-actionable row | none — a count | Decision-bearing (branch A), by a deterministic rule, no alpha. |
| `Pmodal` | **a share of clusters within a named subgroup** | none stated | Descriptive (branch C). Cannot be a finding. |
| per-cluster `max E1` | a maximum | none | Descriptive, **upward-biased by row count**, printed only beside the rows-per-cluster distribution. |

**`sqrt(p(1-p)/n)` is correct for none of these**, and the trap it comes from is
the row count: `n_rows` is uptime, `n_clusters` is evidence.

`M`'s standard error is **cluster-robust**, using `gate._cluster_robust_stderr`
applied to `(k, sum_of_E1)` per cluster — the same sandwich the gate already
runs, reused rather than reimplemented. Two invariants are asserted as tests
before any result is believed, chosen so a wrong implementation gives a
*different* answer:

- **Singleton clusters reproduce the classical standard error exactly.** Catches
  a dropped `G/(G-1)`.
- **Duplicating every observation `k` times leaves the mean and the standard
  error bit-identical.** The naive estimator returns `stderr/sqrt(k)` on that
  input; this states the old bug as an invariant.

### The flip definitions, fixed here

- **`edge_flip`** (row-level): `E1 <= 0 < E1min`. Pure fee-model arithmetic.
- **`actionability_flip`** (row-level): `suppressed_reason IS NULL` **and**
  `size_position(..., risk=RiskConfig().reference(), current_exposure_dollars=0.0)`
  returns `contracts >= 1` under the Model-B-only fee and `0` under the
  maximum-model fee. This is the quantity that would move `actionable` off zero.
- **`indeterminate`**: a row whose only suppression codes are `suspicious_edge`
  or `edge_within_method_noise` — both of which are thresholds on the stored,
  max-model edge and could themselves change under Model B. These are counted
  **separately** and are neither flips nor non-flips. Registering this in
  advance is what stops them being swept into whichever column suits.

---

## §7. The decision rule, with the multiplicity already counted

### How many tests are being run

Counted now, not after.

| Family | Cells | Standing |
|---|---:|---|
| Primary interval test on `M` | **1** | Decision-bearing, always-valid boundary, alpha = 0.05 **[SUPERSEDED by Amendment 1 — now 0.0167]** |
| Branch A flip count | **1** | Decision-bearing, **deterministic** — a count with a reachability precondition, no alpha spent |
| Branch C composition | **1** | Descriptive; names a constraint, cannot declare a finding |
| Grid F cells | 7 | Descriptive |
| Grid B cells | 10 | Descriptive |
| Suppression-code groups | 14 | Descriptive |
| Horizon strata | 3 | Descriptive |
| Era strata | 3 | Descriptive |
| League strata | unknown, printed | Descriptive |

**The multiplicity arithmetic, computed now.** 37 descriptive cells at the
conventional two-standard-error rule give `37 × 0.0455 = 1.68` expected false
findings, and **at least one cell clears by chance about 82% of the time from
nothing**. This project has already produced a 20-point "finding" at two
standard errors from data generated with no edge in it whatsoever, and the
predecessor produced dozens from 1,190 cells. **A descriptive cell that clears
any threshold while the primary does not is the one that got lucky, and the
write-up must say so in those words.**

Exactly **one** interval test carries alpha, which is why alpha is not split.

### The boundary is always-valid, because the record is looked at repeatedly

This table grows and will be re-read. A two-standard-error rule re-evaluated
against an accumulating database is not one look; measured on 1,200 pure-noise
sequences in this repo it fires **13.7%** of the time within 100 looks, and
13.7% is a floor because the simulation stops and the record does not. Under a
true zero it crosses eventually with probability 1.

> **[SUPERSEDED by Amendment 1 §A1 — text retained.]** `alpha = 0.05` becomes
> `alpha = 0.0167`, and the multipliers below become **5.82 at G=100** and
> **4.22 at G=300**. Nothing else in this paragraph changes.

The boundary is `gate.always_valid_multiplier(G, tuning=300, alpha=0.05)` — the
Robbins normal mixture already implemented here, tuned to the gate's own floor.
**[COMPUTED FROM CODE]** it is 5.01 at G=100 and 3.66 at G=300, never
approaching 2 at any `n`. The cost is real and stated. Interim looks are
therefore permitted without limit and without penalty.

Note, and it is not a check on anything: the multiplier is *tuned to* 300, so
any agreement found at G=300 is the tuning parameter reappearing in its own
output. Amendment 1 §A5.3 withdrew exactly that claim from the CLV
registration.

### The decision rule, verbatim

> Let `m = always_valid_multiplier(G, tuning=300, alpha=0.0167)`
> **[AMENDED 2026-08-10 from `alpha=0.05`; §A1]**, `se` the
> cluster-robust standard error of `M`, and the always-valid interval
> `[M - m*se, M + m*se]`. `G` is **fresh game-clusters**, never rows.
>
> **All three branches are evaluated at every look and all three are reported.
> They are not mutually exclusive; more than one may be declared.** A branch
> that is neither declared nor refuted is **UNRESOLVED**, and UNRESOLVED is a
> real answer.
>
> **BRANCH B — PREMISE REFUTED (edges are centred negative).**
> Declared if and only if, at a look taken when `G >= 100` **and** the
> always-valid half-width `m*se <= 10.0` tenths, the always-valid **upper**
> limit is below −10.0 tenths: `M + m*se < -10.0`.
> **Counter-declared as NOT REFUTED** if, under the same two preconditions, the
> always-valid **lower** limit is at or above −10.0 tenths: `M - m*se >= -10.0`.
> In every other case, UNRESOLVED.
>
> **BRANCH A — FEE-MODEL-DECIDABLE.**
> Precondition, checked and printed **first**: `R`, the number of fresh rows in
> the **reachable domain** of §C2 (Grid F's four `Δ=10` cells), is greater than
> zero. If `R = 0` the branch is **UNRESOLVED** and the write-up states that the
> instrument could not have seen the effect — a zero flip count over an empty
> domain is not evidence of anything.
> Given `R > 0`:
> **Declared** if and only if `A >= 1` — at least one fresh game contains a row
> that is not actionable under the maximum-fee model and is actionable under the
> cheapest candidate, at the reference profile, carrying no suppression code.
> **Refuted** if and only if `A = 0` at a look taken when `G >= 100`. `A = 0`
> means resolving the fee model cannot move a single game in the record, and
> that is written down in those words.
> The `indeterminate` count (§6) is printed beside `A` at every look. If
> `indeterminate > A`, the branch is **UNRESOLVED regardless**, because the
> rows that could change the answer outnumber the ones that decided it.
>
> **BRANCH C — THE BINDING CONSTRAINT IS ELSEWHERE.**
> Let `P` be the set of fresh rows with `E1 > 0`. Reported at every look:
> `|P|` in rows and in clusters, and the per-code cluster counts over the
> fourteen codes of §2.
> **Named** if and only if `P` covers **at least 5 clusters** — the repo's
> `MIN_EXPECTED_PER_SIDE` rule, read before the effect size — and some single
> code is carried by at least half of `P`'s clusters. The write-up then names
> that code, with its cluster count and share, as the binding constraint.
> Fewer than 5 clusters: **UNRESOLVED, and no code is named.** The biggest gaps
> come from the smallest cells.
> **This branch is a description of composition, not a test.** It may not be
> reported as significant, and it cannot raise or lower any other branch.
>
> **THE SENSITIVITY THAT CAN DOWNGRADE, AND NEVER UPGRADE.**
> Every declared or refuted branch is recomputed on each of the following
> reduced populations, where the reduction leaves `G >= 100`:
> (i) excluding rows carrying `stale_kalshi_quote`;
> (ii) excluding legacy `clv_horizon_hours = 1.0` rows;
> (iii) excluding the `boundary` bankroll-era rows;
> (iv) leaving out each Grid F cell in turn.
> **If any recomputation reverses a declaration or a refutation, that branch is
> downgraded to UNRESOLVED and the write-up names the reduction that caused it,
> in those words.** The rule is strictly one-way: it can never create a
> declaration and can never raise a verdict. Reductions that would leave
> `G < 100` are not tested and are not grounds for downgrade; their share of
> the clusters is printed instead, and if any single one exceeds 0.50 the
> write-up must state that **the pooled result is one group's result**.
>
> **No bucket, no stratum, no league and no descriptive cell may substitute for
> any of the three branch statistics.**

### Where the `G >= 100` floor comes from

**[COMPUTED FROM CODE]** the always-valid half-width `m·sigma/sqrt(G)`:

| `G` | mult | σ=5 | σ=10 | σ=20 | σ=30 |
|---:|---:|---:|---:|---:|---:|
| 29 | 8.31 | 7.7 | 15.4 | 30.9 | 46.3 |
| 60 | 6.09 | 3.9 | 7.9 | 15.7 | 23.6 |
| **100** | **5.01** | **2.5** | **5.0** | **10.0** | **15.0** |
| 200 | 4.03 | 1.4 | 2.9 | 5.7 | 8.6 |
| 300 | 3.66 | 1.1 | 2.1 | 4.2 | 6.3 |

At `G = 100` the half-width equals the entire 10-tenth fee-model band at
σ = 20. Below that, "centred negative" cannot be distinguished from "centred
negative but rescuable by the cheaper fee model", which is the distinction the
whole question turns on. The floor is stated as `G >= 100` **and** the explicit
half-width precondition `m*se <= 10.0`, so that a large measured σ raises the
requirement automatically rather than by anyone's later choice.

---

## §8. The stopping rule

Data collection ends at whichever comes **first**:

1. `G = 300` fresh game-clusters in the §2 population; or
2. **2026-11-30**, a calendar date and not a state of the data; or
3. every one of the three branches has been declared or refuted at a look
   meeting its own precondition.

Interim looks are permitted without penalty and without limit — that is what the
always-valid boundary is bought with. There is no alpha to spend.

**What is forbidden** is changing anything in §§1–7 after a look. If the design
must change, the amendment is written into this file with its date and reason
**before** the next look, the pre-amendment result is reported alongside, and
`G` restarts if the population definition moved. **An amendment made after a
look and not recorded voids the registration.**

**A config bump is a new sequence.** If `strategy_config_version` changes
mid-record the boundary's i.i.d. assumption breaks; report the version
distribution at every look, and if more than one version is present the primary
runs on the modal version with `G` counting only those games.

---

## §9. What would falsify this, and what happens then

**The primary hypothesis (§1) is falsified by** an always-valid lower limit at
or above −10.0 tenths at a look meeting branch B's preconditions. Branch A is
falsified by `A = 0` over a non-empty reachable domain at `G >= 100`. Branch C
is falsified by `P` covering at least 5 clusters with no code reaching half of
them — a positive-edge population with no single binding constraint.

**The result's destination, fixed now, before the result exists:**

```
docs/measurements/<run-date>-fresh-odds-edge-distribution-result.md
```

One file, **written whichever way it comes out**, with that exact filename stem,
the same sections, and this document linked from its first line. Only the date
varies. Registering the destination in advance is what stops a negative result
from quietly never being written.

**Consequences, in both directions, so the measurement is decision-relevant:**

| Verdict | What is built | What is killed |
|---|---|---|
| **B declared (REFUTED)** | The finding is written up: *consensus-only taker edge, at this `n`, is centred below the bar by more than the fee model can explain.* CLAUDE.md's premise is recorded as returning the answer it warned was likely. | The taker consensus-only line as specified. The four fee-calibration trades drop from "decides everything" to "buys a field name" — still worth ~$5 for the wire format, no longer worth waiting on. ADR 0016's backfill stays dead. |
| **A declared** | The four fee-calibration trades become **the** next action, and the write-up names the exact number of games that would move. `scripts/capture_fills_fixture.py` runs immediately after the fills. | Nothing. |
| **A refuted** | Nothing new. | The belief that resolving the fee model can open the gate. Written down so no future session re-derives it. |
| **C named** | Work on the named constraint, in the write-up's words, with its cluster count. If it is `too_few_books` or `wide_market` the answer is book coverage; if `insufficient_depth`, it is a venue-liquidity finding; if `skeptic_*`, it is a prompt. | Whichever lines the named constraint rules out. |
| **All three UNRESOLVED at the stopping rule** | Nothing. Report `G`, σ and the intervals. | The *timeline*, not the hypothesis: if the recording rate cannot reach `G = 100` fresh clusters by 2026-11-30, the recording rate is the binding constraint and that is the thing to fix or abandon. |

**This is decision-relevant in every branch.** Branch B kills a line of work,
branch A promotes a specific $5 action to the top of the queue, branch A's
refutation demotes it, and branch C redirects. There is no branch where the
answer is "we proceed either way".

---

## §10. What this measurement cannot establish — drafted before the run

Caveats written afterwards are selected to be survivable. These are written now,
and the list deliberately includes the ones that could overturn the result.

- **It says nothing about whether the edge is real.** `E1` is the engine's own
  claim about a market, recomputed at a fixed size. A distribution of claims is
  not evidence that the claims are correct. That is the CLV signal test's
  question and it is registered separately and is **UNDERPOWERED until G=300**.
- **It says nothing about calibration.** Whether `fair_probability` is right is
  a different question with different inputs (`kalshi_markets.result`, which now
  has data and zero readers).
- **The break-even bar it measures against is `calculate_fee`'s bar, not
  Kalshi's.** The entire fee model is secondary-sourced and unverified —
  `core/fees.py` says so in its own docstring, and this project has **zero fills
  ever**. If both candidate models are wrong, every number here moves and the
  Δ table of §C1 moves with it. Four real fills resolve this and nothing else
  does.
- **A flip count is an arithmetic statement about the record, not a forecast.**
  `A >= 1` says a row *would have been* actionable under a different fee model.
  It does not say the bet would have filled, or won, or cleared the spread.
- **`fair_probability` is the worst of four devig methods**, so `E1` is a
  deliberately shrunk number and the distribution is shifted left by an
  unmeasured, price-dependent amount — the method spread is ~1.8 tenths on an
  even moneyline and ~20.3 on a longshot **[COMPUTED FROM CODE —
  `suppression.py`]**. The location of this distribution is therefore *not* the
  location of the true edge distribution, and the gap is largest exactly at the
  wings, where Grid F says the fee-model question is worth the most.
- **The population is defined by the absence of one suppression code, and that
  code was evaluated at the 900s threshold the deployment happened to carry.**
  A different `MAX_ODDS_AGE_S` is a different population. Nothing in the record
  says what fraction of "fresh" rows sat at 890s versus 30s;
  `odds_age_ms` is stored and its distribution is a required print (§S2), but
  no threshold in §7 depends on it.
- **Recomputing at n=1 answers a question about one contract.** It does not
  bear on ADR 0017 §1's n=10 figure, and the n=10 secondary is reported
  precisely so nobody has to guess which was plotted. `tasks/lessons.md`
  records this family as *"a true measurement licensed a false conclusion"*.
- **`G` may be inflated by the event-ticker key** if spread or total rows ever
  enter the record (§4). The mandatory suffix-collision print is the detector,
  and it detects rather than corrects.
- **One season, and the leagues that were in it.** An August 2026 slate — MLB,
  WNBA — with NFL preseason explicitly out of scope. It says nothing about NBA,
  NCAAF or NFL regular season, and nothing about in-play.
- **It says nothing about the maker path**, which has a different bar (50.44%)
  and a different fee curve, and nothing about combos (`KXMVE`, ADR 0012).
- **A slice run cannot be repaired by labelling it.** If P1 is not satisfied and
  Stage A output is quoted as a property of the table by anyone, downstream or
  later, the label did not work. That is a known failure mode of this exact
  payload and the reason `total` and `returned` are both returned.
- **The always-valid boundary assumes clusters are independent and identically
  distributed across games.** Same-day games sharing a market-wide liquidity
  shock, one sportsbook feed degrading across a whole slate, or a single sweep
  window writing every row for an hour all violate that, and nothing here
  corrects for it.

---

## The power check — this is the deliverable, not a preliminary

**Can this measurement answer this question at the `n` available?**

### `n` is unknown, and that is the first finding

`G` for this population — distinct games among fresh rows, scored or not — **has
never been counted by anyone**. The 29 games on the gate screen are *scored*
games at the primary horizon, a strict and much smaller subset. Because this
measurement needs no CLV, `G` here is bounded below by 29 and above by the
number of distinct games in 1,529 rows, and nothing narrows it further.

**Registered consequence:** `G` is printed before any effect size, and the
verdict at any look with `G < 100` is UNRESOLVED for branches A and B by rule,
not by judgement.

### What is resolvable, at what `G`

**[COMPUTED FROM CODE — `always_valid_multiplier(G, tuning=300, alpha=0.05)`]**
`G` required for the always-valid half-width to fall below a target, by σ:

| target half-width | σ=5 | σ=10 | σ=20 | σ=30 |
|---|---:|---:|---:|---:|
| **10.0 tenths** (the fee-model band, §C1) | 23 | 47 | **101** | 164 |
| **3.8 tenths** (the venue's entire headroom) | 63 | 140 | **349** | 651 |

> **[SUPERSEDED by Amendment 1 §A1 — table retained.]** At the amended
> `alpha = 0.0167` the same table reads **26 / 55 / 120 / 198** and
> **74 / 168 / 428 / 811**. The conclusions below are unchanged and the
> direction of the change is to make both harder, never easier.

Read against the real headroom, as the brief requires. **The venue lowers the
bar from 52.38% to 52.00% — 0.38 points, 3.8 tenths — and the devig-method
spread alone is 1–2 points.** So:

- **This design can resolve the 10-tenth question at plausible `G`.** That is
  the question §1 asks, and it is asked at that width deliberately, because it
  is the width at which the answer stops depending on the unresolved fee model.
- **This design cannot resolve the 3.8-tenth question** unless σ is small and
  `G` is large: 349 games at σ=20, against a record that has produced 29 scored
  games in its life. **Registered: no claim at the 3.8-tenth scale may be made
  from this measurement, at any `G` it is likely to reach.** A design that can
  only resolve effects larger than a point is not measuring the thing this
  project exists to measure — and this one is honest about which of the two
  scales it is on.
- **Branch A needs no σ and no interval.** It is a count over a domain whose
  size is computable in advance, which is why it is the branch most likely to
  return an answer first. That is a property of the design, not a prediction
  about the count.

### Verdict of the power check

**ADEQUATE for the 10-tenth (fee-model) question at `G >= 100`, given the
half-width precondition. UNDERPOWERED for anything at the venue's 3.8-tenth
headroom scale, permanently, at any `G` this record will plausibly reach.
BLOCKED today on P1 (full-table access), not on statistics.**

The honest reading of §0.3 is that the expensive part of this question is
already answered by a counter — nothing has ever been actionable — and what
remains is *how far below, and can the fee model reach it*, which is cheap. This
measurement is worth running for that reason and not for a larger one.

A measurement that cannot resolve the question is worse than none, because it
returns a number anyway and the number gets quoted.

---

## §F. Facts verified against source, not taken on trust

- **F1.** `routes.py:634` — `/api/ledger` takes `limit: int = Query(200, le=1000)`
  and there is no `offset`. `total` and `returned` are both in the payload, so a
  slice is detectable from the payload alone.
- **F2.** The ledger payload names the price field **`ask_tenths`**, not
  `entry_ask_tenths` (`_serialise`, `routes.py:1864`). It carries
  `fair_probability`, `suppressed_reason`, `created_ms`, `ticker`, `side`,
  `edge_tenths`, `fee_predicted`, `suggested_contracts`, `reference_contracts`,
  `odds_age_ms`, `kalshi_quote_age_ms`, `clv_horizon_hours` and
  `strategy_config_version`. It does **not** carry `event_ticker`, `league`, or
  (on this route) `commence_ms`. Registering the field names removes the one
  place a rename would silently empty a filter — the fourth-wrong-wire-key
  failure this repo has hit four times.
- **F3.** `core/sizing.py:156` prices at `contracts=1` unconditionally, so
  `reference_contracts > 0` is equivalent to a positive n=1 post-fee edge. This
  is what makes §0.3's derivation exact rather than approximate.
- **F4.** `effective_price(500, 1)` returns **0.5200** **[COMPUTED FROM CODE]**,
  reproducing CLAUDE.md's 52.00% taker bar from the code rather than from the
  prose. At 20c it is 22.00%, at 30c 32.00%, at 80c 82.00% — the bar is
  `ask + 2c` across the middle band at one contract.
- **F5.** `fee_candidates(p, 1)` — Model A is the maximum at all 999 tradeable
  prices, so the cheapest candidate is always Model B and Δ = A − B, taking
  exactly the two values 10.0 and 0.0 tenths on the seven runs of §C1.

---

## §S1. The extraction, fixed in advance

**Stage B (primary), against the full table:**

```sql
SELECT
  COALESCE(m.event_ticker, r.ticker)          AS cluster_key,
  (m.event_ticker IS NULL)                    AS unclustered,
  substr(r.ticker, 1, instr(r.ticker, '-') - 1) AS series_prefix,
  r.id, r.ticker, r.side, r.created_ms,
  r.entry_ask_tenths, r.fair_probability,
  r.edge_tenths          AS stored_edge_tenths_DO_NOT_USE,
  r.suppressed_reason, r.suggested_contracts, r.reference_contracts,
  r.odds_age_ms, r.kalshi_quote_age_ms,
  r.clv_horizon_hours, r.strategy_config_version
FROM recommendations r
LEFT JOIN kalshi_markets m ON m.ticker = r.ticker
WHERE r.entry_ask_tenths BETWEEN 10 AND 989
  AND r.fair_probability IS NOT NULL
  -- FRESH: `stale_odds` absent from a COMMA-JOINED COMPOSITE column.
  -- `NOT IN ('stale_odds')` retains `'stale_odds,wide_market'` and 27.8% of
  -- stale rows are composites. That was defect D1 of Amendment 1.
  -- `instr`, not `LIKE`: `_` is a single-character wildcard in SQLite LIKE
  -- and every code in this vocabulary contains underscores.
  AND (r.suppressed_reason IS NULL
       OR instr(',' || r.suppressed_reason || ',', ',stale_odds,') = 0);
```

The stored edge column is selected **only** so its divergence from `E1` can be
reported as a diagnostic (§S2 item 8). It enters no statistic in §7. The alias
says so.

**Stage A (composition only), over HTTP:** `GET /api/ledger?limit=1000`, the
same predicate applied in Python as
`"stale_odds" not in (row["suppressed_reason"] or "").split(",")`, the cluster
key from the §4 fallback, and **only** items 1–4 of §S2 printed, under the
prefix `NEWEST-1,000 SLICE — NOT A PROPERTY OF THE TABLE`.

## §S2. Required output of every run, in this order

Read `n` before the effect size, and read the frame before `n`.

1. **The frame.** `total` and `returned` (slice or table), the §2 predicate as
   executed, and `n_rows` / `G` for the fresh population.
2. **The composition, before any rate.** Horizon × era × series-prefix ×
   `strategy_config_version`, in clusters and rows, with each cell's share.
   The `boundary` era count separately. The distribution of rows per cluster,
   and the largest cluster's share of rows.
3. **The cluster-key integrity print.** Distinct series prefixes; the number of
   `<DATE+TEAMS>` suffixes appearing under more than one prefix (§4 defect 1);
   `unclustered_rows`.
4. **`odds_age_ms` distribution** over the retained population — median and p90
   — so "fresh" is a measured range, not a label.
5. **σ and the resolvable effect.** The measured between-cluster SD of the
   per-cluster mean `E1`, labelled **measured**, compared against the power
   table's columns; then the always-valid half-width at this `G`, printed
   **before** `M`.
6. **`R`, the reachable-domain row and cluster count** (§C2), printed **before**
   the flip counts.
7. **The three branches**, each with its verdict, its preconditions shown as
   met or unmet, and the largest contributing group's share on the same line as
   `M`. The `indeterminate` count beside `A`.
8. **Diagnostics:** the distribution of `E1 - stored_edge_tenths`, which is the
   size-basis artefact of §6 made into a printed number rather than an argument;
   and the assertion `E1min - E1 == Δ(price)` per §C1, which must hold exactly.
9. **The sensitivity re-runs** (i)–(iv) and any downgrades, naming the reduction.
10. **Grid F, then Grid B**, each labelled **DESCRIPTIVE — CANNOT PRODUCE A
    FINDING**, with the three `Δ=0` cells labelled **UNREACHABLE BY
    CONSTRUCTION**.
11. **The n=10 secondary**, labelled non-decision-bearing.
12. **§10, reproduced verbatim.**

The harness's module docstring states what it does not establish, per the repo
rule that every harness carries its own limits.

---

## Registration record

| | |
|---|---|
| Registered | 2026-08-10 |
| Data seen at registration | **Yes — see §0.** Whole-table counters, horizon split, population split, per-population game counts, and the `stale_odds` composite rate. **No per-row value and no edge distribution has been seen by anyone.** |
| Primary estimand | `M` — mean over fresh game-clusters of the per-cluster mean of `E1` |
| Direction | One-sided, negative (`M < -10.0` tenths) |
| Edge basis | **Recomputed** `edge_after_fees_tenths(ask, contracts=1, fair)`; the stored column is not used |
| Population | §2, `instr`-delimited freshness predicate on a composite column |
| Cluster key | `COALESCE(kalshi_markets.event_ticker, recommendations.ticker)`; HTTP fallback in §4 |
| Bucket edges | Grid F (fee-model-homogeneous at n=1, seven cells, derived from `fee_candidates`); Grid B = `validate.BUCKETS` verbatim. Both descriptive. |
| Boundary | `gate.always_valid_multiplier(G, tuning=300, alpha=0.0167)`, one interval test **[amended 2026-08-10 from 0.05; §A1]** |
| Decision floor | `G >= 100` **and** half-width `<= 10.0` tenths for branches A and B |
| Stopping rule | §8 — `G = 300`, or 2026-11-30, or all branches resolved |
| Result destination | `docs/measurements/<run-date>-fresh-odds-edge-distribution-result.md`, written either way |
| Assumed inputs | **One** — σ, which appears only as a column of the power table and gates no threshold |
| Verdict at registration | **READY for branches A and C; READY for branch B at `G >= 100`; BLOCKED on P1 (full-table access) for all three; permanently UNDERPOWERED at the 3.8-tenth headroom scale** |
| Amendments | **1**, dated 2026-08-10, below. No data observed at amendment. |

---

# Amendment 1 — 2026-08-10

**Reason: a second registration now shares this project's alpha budget.**
`docs/measurements/2026-08-10-preregistration-devig-method-calibration.md` was
written the same day, by the same agent, deliberately — `partner`'s requirement
was that the two be designed jointly so the multiplicity is counted **across**
them rather than within each. That count is in that document's §M and it is
reproduced below.

Nothing above has been deleted or rewritten. Five passages carry a
`[SUPERSEDED]` or `[AMENDED]` marker in place. **Where this amendment and the
original text conflict, this amendment governs.** The original stays because the
record is the product: a pre-registration whose text is quietly rewritten is not
a pre-registration.

## A0. What had been observed when this was written: nothing new

The clause that makes an amendment legitimate rather than contamination.

**No data was observed between the registration of this document and this
amendment.** The live database was not queried, no route was called, no script
was run, no odds credit was spent, and no value of `M`, `E1`, `A`, `R`, `G`,
`n_rows` or σ exists anywhere or was estimated from any record. The §0
disclosure of this document is unchanged and no line has been added to it.

Everything below was produced by executing repository code on inputs chosen
here — `always_valid_multiplier` swept over `G` and alpha — and is **[COMPUTED
FROM CODE]**, reproducible from the repository alone.

**Per §8, `G` does not restart.** The population definition has not moved; only
the width of the boundary has, and it has moved in the conservative direction.

## A1. The alpha of the single interval test: 0.05 → 0.0167

**What was registered.** §7: *"exactly one interval test carries alpha, which is
why alpha is not split"*, at `alpha = 0.05`.

**Why it is superseded.** The premise — one interval test in the project — was
true when written and is no longer. The joint count across both registrations
is:

| | |
|---|---:|
| Alpha-carrying interval tests, project-wide | **3** (`M` here; `B1` and pooled `B3` there) |
| Descriptive cells, project-wide | **156** (37 here; 119 there) |
| Expected false findings at 2 SE over the descriptive cells | **7.10** |
| P(at least one descriptive cell clears from nothing) | **0.9993** |

This document's own §7 gave 37 cells, 1.68 expected, and 82%. **The joint
figure is effectively certain**, which is the whole reason for counting across
documents rather than within one.

**What now governs.** Family-wise 0.05 across the project, Bonferroni across the
three interval tests:

```
alpha per interval test = 0.05 / 3 = 0.01667
```

so the boundary in §7's decision rule, in the paragraph above it, and in the
power table is `gate.always_valid_multiplier(G, tuning=300, alpha=0.0167)`.

Bonferroni rather than anything sharper because the three tests run on different
populations with unknown dependence, and a sharper correction would require
assuming a dependence structure nobody has measured.

**What it changes, computed rather than asserted [COMPUTED FROM CODE]:**

| | alpha = 0.05 | alpha = 0.0167 |
|---|---:|---:|
| multiplier at `G = 100` | 5.012 | **5.823** |
| multiplier at `G = 300` | 3.656 | **4.215** |
| `G` for half-width ≤ 10.0 tenths (σ = 5/10/20/30) | 23/47/101/164 | **26/55/120/198** |
| `G` for half-width ≤ 3.8 tenths (σ = 5/10/20/30) | 63/140/349/651 | **74/168/428/811** |

**What it does NOT change, stated so the absence is deliberate:**

- **No threshold moves.** The −10.0 tenth threshold of branch B, the `G >= 100`
  floor, the `m*se <= 10.0` half-width precondition, branch A's reachability
  rule, branch C's five-cluster gate, the sensitivity list, Grid F's edges,
  Grid B, the cluster key, the population predicate, the stopping rule and the
  result destination are all unchanged.
- **No human chooses anything as a result of this.** The design already made the
  binding condition a **half-width precondition** rather than a bare `G` count,
  precisely so that a change in the multiplier would tighten the requirement
  automatically. It does exactly that: the effective floor rises from ~101 to
  ~120 games at σ = 20.
- **The direction is conservative in every branch.** A wider boundary makes
  branch B's REFUTED harder to declare and its NOT REFUTED harder to declare,
  so the failure mode of this amendment is **more UNRESOLVED, never a false
  declaration**. Since branch B's REFUTED is the verdict that would kill a line
  of work, an amendment whose error can only delay it is the right way round.
- **Branch A is untouched.** It is a deterministic count with a reachability
  precondition and carries no alpha, so no correction applies to it. Applying
  one would be a second correction to a test that is not an inference.

## A2. One addition to §7, following from the joint count

Add to §7, after the multiplicity table:

> **The 37 cells counted here are not the project's total.** The joint count is
> 156 descriptive cells across this document and the devig-method registration,
> giving 7.10 expected false findings at two standard errors and P(≥1) = 0.999.
> A reader taking a cell from this document without the other lane's cells in
> the denominator is undercounting, and undercounting flatters — the p-value is
> monotone in the number of tests. `warehouse/models/marts/mart_multiple_
> comparisons.sql` **cannot** supply this count: it counts warehouse marts only,
> `warehouse/` is not in the Dockerfile, `/api/dashboards` is a 503 on live, and
> `tasks/audit-2026-08-07.md` item 7 records that it already undercounts what it
> does cover. **The project-wide count lives in these two documents and nowhere
> else.**

---

**Amendment 1 ends. No data had been observed when it was written (§A0).**
