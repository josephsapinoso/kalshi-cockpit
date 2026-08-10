# Pre-registration — the clean-population shortfall distribution

**Written 2026-08-10 (UTC).** `tasks/NEXT.md` queue item 2. Replaces the joint
bound, which is dead: see
[`2026-08-10-joint-bound-result.md`](2026-08-10-joint-bound-result.md).

- Owner: `pre-registrar` (agent), on behalf of Joe. Scoped by `partner`.
- Scored against by: `measurement-skeptic`, after the run.
- Negative-result destination: fixed in §9, before the result exists.
- **Status at registration: READY-CONDITIONAL.** The condition is named in §V
  and it is a stop-the-line, not a caveat.

> **This document does not revive the joint bound, in any form.** No knob is
> relaxed, no generous-alternative arithmetic appears anywhere below, and no
> quantity here is computed against anything but the **deployed** fee, the
> **deployed** suppression configuration and the **deployed** conservative
> devig. If a future reader finds a "what if every setting were loosest"
> calculation in this design, it is a defect and the design is void.

---

## §0. What had already been observed when this was written

**Both priors are disclosed, because disclosing only the slice would understate
how much is already known.** This is the most contaminating section in the
document and it is first.

### §0.1 Prior 1 — the 413-row / 38-game slice

**[MEASURED FROM DATA — newest-1,000 pull, 2026-08-10, unpinned]**

```
unsuppressed rows                                       413   in 38 games
  ...with a positive NET edge at the deployed fee         0
  largest clean GROSS edge                             17.9 tenths = 1.79c
  the deployed taker fee at n=1, mid-band               20.0 tenths = 2.00c
  largest clean NET edge                               −2.1 tenths
```

### §0.2 Prior 2 — the whole table, pinned, complete, duplicate-free

**[MEASURED FROM DATA — pinned pull, `pin = newest_id = 1549`, `total = 1549`,
1,549 rows / 1,549 distinct ids, 2026-08-10]**

```
unsuppressed rows                                       614   in 59 games
  ...with a positive NET edge at the deployed fee         0
  largest clean NET edge                               −2.1 tenths  (0.21c short)
actionable rows anywhere in the table, ever               0
614 matches /api/gate's published `no_edge` count exactly
p_conservative == fair_probability                   1549 of 1549
p_conservative == min(four devig methods)            1549 of 1549
degenerate-fair signature rows                          21  (1.4%), 2 games,
                                                             0 unsuppressed
```

### §0.3 So the outcome is substantially known. State what this adds.

Plainly, without dressing:

**It adds three things and no fourth.**

1. **Deduplication.** `614` is a count of *rows*. Rows are uptime. The
   recorder writes both complementary legs of every game and
   `persist_if_changed` writes on every price move, so `614` is not a count of
   distinct pieces of evidence. **[MEASURED — slice]** 1,000 rows collapsed to
   748 distinct `(cluster, instant, ask, fair)` tuples. The deduplicated count
   for the clean population has never been computed on any key.
2. **A distribution instead of a maximum.** `−2.1 tenths` is one order
   statistic. Nothing is known about the median, the spread, the per-game
   maxima, or the largest game's share.
3. **ADR 0019's pending input 1, answered for free** (§0.6, §1 H4). Whether a
   *two-book* degenerate fair — one that passes every guard and lands in the
   clean population — exists in the live record has never been checked. The
   clean population of this pull is exactly the place it would be, and the four
   `p_*` needed to detect it are already on the payload.

**What it does NOT add:** a new answer to "does any clean row clear the fee".
That is answered. §0.2 measured it directly, and §0.4 shows the published
counter alone already bounds it. **A registration that presented §1 as an open
question would be presenting a foregone conclusion**, which is exactly the
failure that killed the joint bound, and §R exists to stop it happening twice.

### §0.4 What the published counter alone entails, before any query

**[COMPUTED FROM CODE]** `core/sizing.py:156` prices every sizing decision at
`effective_price(ask_tenths, contracts=1)`, and `full_kelly_fraction > 0` iff
`fair > effective_price`, i.e. iff `E1 > 0` (§6). `engine.py:207` zeroes
`reference_contracts` on any suppression. Therefore

```
actionable  ==  (suppressed_reason IS NULL)  AND  (reference.contracts >= 1)
```

**[COMPUTED FROM CODE — exhaustive binary search over all 999 tradeable prices
at `RiskConfig().reference()`]** the smallest `E1` that sizes to `>= 1`
contract has supremum **1.0 tenths, attained at ask = 480**. So

> `actionable = 0` over the whole table ⟹ **every clean row has
> `E1 < 1.0 tenths`** (0.10c).

The maximum this measurement can tighten that published bound by is therefore
**1.0 tenths**, and §0.2 has already tightened it to **−2.1 tenths** by direct
measurement. **The incremental information in the maximum is zero.** This is
registered so it cannot be re-discovered as a finding.

**Sizing is not a confound, and that follows from the same number.** There is
no hidden population of positive edges rounded away by the sizer: the window
between "positive edge" and "sizes to one contract" is at most 1.0 tenths wide
at every price.

### §0.5 What has NOT been seen, by anyone

No deduplicated count on any key. No quantile, median, IQR, per-game maximum,
per-game count, largest-contributor share, or histogram of `E1` or of the
per-row devig-method spread, over any population. No value of the ratio
`clean rows / clean deduplicated observations`. No count of degenerate fairs
in the **clean** population on any predicate — the 21 rows of §0.2 were counted
on the undercounting ULP signature and were all *suppressed*. **No number in
§2, §3, or H2/H3a/H3b/H4 of §7 exists anywhere** — and in particular
`spread_at_min`, the spread of the single nearest observation, has never been
computed, which is what leaves H3b genuinely open despite §0.6.

### §0.6 Prior 3 — the devig-method spread on the live money path

**[MEASURED FROM DATA — `tests/fixtures/odds_mlb_h2h_spreads_totals.json`,
15 events, 425 h2h quotes, by running
`consensus_devig(..., sharp_books=runner.SHARP_BOOKS)`; supplied by the
coordinating lane before this registration was committed]**

```
consensus method_spread, live anchoring   median 1.3 tenths
                                          range  0.32 – 4.61 tenths
per-book, all 425 h2h quotes              median 4.31, p90 11.19, max 22.19
                                          12.7% demand < 0.1 tenth
anchoring keeps a median of 3 of 29 usable books
   (always betfair_ex_eu + matchbook, ± pinnacle)
```

**This is the reference class H3a and H3b actually use** and it is *not* the
`~1.8 / ~20.3 tenths` pair quoted in `suppression.py`'s comment: those are
per-outcome figures for two example lines, whereas `fair_prices.p_*` — and
therefore every `spread_tenths` this design computes — is the **post-anchoring
consensus** spread. The power check and §R1 below use the measured live-path
numbers, not the comment's.

**Two consequences, both binding, and the second created a new claim:**

1. **The prior on H3a moves.** The typical clean shortfall is bounded below by
   2.1 tenths (§0.2) and the typical method spread is 1.3, so H3a is *likelier*
   to be declared than refuted. Registered anyway; a claim whose prior is known
   is not thereby a foregone conclusion, and §R4 checks reachability rather than
   plausibility.
2. **The coordinating lane's inference was about the nearest row, not the
   median, and it is right about that.** `min(S) = 2.1 tenths` sits **inside**
   the measured consensus-spread range `[0.32, 4.61]`. That is a statement about
   the order statistic that produces the citable sentence, and the median cannot
   answer it. **H3b is registered because of this** (§1), and it is the claim
   that governs whether *"the nearest is 0.21c short"* may be written at all.

**The capture's limits, stated because they bound what it licenses.** It is one
fixture of **mature MLB, 8.9–12.4h from first pitch**, so it **structurally
cannot contain an opener**, and the degenerate-fair defect actually observed in
the record was **WNBA**. Nothing here is a property of the live record; it is a
calibration of the instrument's input, on the nearest available real capture.

### §0.7 Seen — repository state, including one in-flight document

Not data, but it was read and it changed this design, so it is disclosed.

At registration the working tree carried **`docs/adr/0019-the-agreement-family-
is-blind-to-correlated-garbage.md`, status Proposed**, uncommitted, plus a
comment-and-test-only change to `core/suppression.py` (no threshold moved;
`edge_ceiling_tenths` is still 40.0 and `min_book_count` is still 2, verified by
diff). Three things in it govern sections below and are adopted here:

1. **The `tasks/lessons.md` headline is being corrected.**
   `edge_within_method_noise` is *correctly scoped* — on a symmetric two-way
   line method choice contributes genuinely zero ambiguity, so the guard passing
   is a true statement. §10 no longer repeats the superseded framing.
2. **[MEASURED — ADR 0019 §2, by running `consensus_devig` into
   `evaluate_suppression`]** two books both quoting `1.85/1.85` give
   `fair ≈ 0.5`, `market_width = 0.0`, `book_count = 2` and
   **`suppressed_reason = None`** — a fabricated fair in the *clean* population.
   **Reachable, and NOT observed.** Two further measurements bound how much that
   reachability is worth, and both are disclosed because they weaken H4's
   premise rather than support it:
   **[MEASURED — same fixture]** `market_width == 0.0` arises on **0 of 15**
   events on the live path (range 0.00044–0.00924), so two correlated sharp
   books do **not** in fact produce an exact zero; and **0 of 425** h2h quotes
   are symmetric (min `|price_a − price_b| = 0.030` — a continuum with a floor,
   not a spike). Symmetry does appear on spreads and totals at 2.0% / 2.4%, but
   **[COMPUTED FROM CODE — `runner.py:99`, `MONEYLINE = "h2h"`]** those never
   reach suppression. Against that: the fixture is mature MLB and cannot contain
   an opener, and the observed defect was WNBA — **the wrong population to
   clear H4 with.** H4 over the live record is the census that can (§1).
3. **The degenerate-fair signature in `tasks/NEXT.md` undercounts.** Requiring
   `p_power` one ULP below 0.5 **drops** the `1.95/1.95` case, where all four
   methods return exactly 0.5 and the guard is *more* dead, not less. The
   registered predicate is therefore `abs(p_multiplicative − 0.5) < 1e-12`
   alone.

**Nothing in ADR 0019 is treated as decided.** It is Proposed. It is used here
only for (a) a code-measured fact, (b) a predicate correction, and (c) the §V
trigger.

### §0.8 Provenance labels, and the count of the assumed

Every quantity is labelled **[COMPUTED FROM CODE]**, **[MEASURED FROM DATA]**
or **[ASSUMED]**.

**There is exactly one assumed input in this design:**

> **A1 [ASSUMED].** A moneyline market in MLB and WNBA has exactly two
> settling outcomes — no draw — so a `NO` on one team's ticker and a `YES` on
> the other team's ticker in the same event name the same claim. This is a
> fact about the sports, not something this repo measures.
> **Detector, registered:** §3's per-cluster ticker-suffix-set print. A cluster
> whose observed suffix set is not exactly two members is **not normalised** and
> is reported separately. A1 therefore fails loudly rather than silently.

Count of assumed inputs: **1**.

---

## §C. Corrections to the brief, made before the design was fixed

Recorded rather than quietly fixed, because the brief will be read again.

### C1. The `instr` predicate is right, and it does not apply to the primary population

The brief requires the freshness predicate
`instr(',' || suppressed_reason || ',', ',stale_odds,') = 0` **rather than
`LIKE`**, and the reason given is correct and is not style: SQLite `LIKE` reads
`_` as a single-character wildcard, **all fourteen suppression codes contain
underscores** **[COMPUTED FROM CODE — eleven `Check(...)` names in
`core/suppression.py`, plus `sizing:<constraint>` from `engine.py:219` and
`skeptic_defect` / `skeptic_suspicious` appended with a comma by
`agents/skeptic.py:200`]** — **fifteen if ADR 0019 deploys, which adds
`inconsistent_consensus_metadata`; §V rules it is not a void trigger because it
cannot fire (P7), but §S item 10's token census must enumerate it if the
deployed build carries it, or the census describes a vocabulary the producer no
longer has** — and `suppressed_reason` is a comma-joined composite
of **every** failed check (`SuppressionResult.reason`,
`core/suppression.py:95-103`) — so `NOT IN ('stale_odds')` retains every
composite row. That was defect D1 of the CLV registration's Amendment 1.

**It does not apply here.** The registered population is
`suppressed_reason IS NULL` (§2), which is **strictly stronger** than any
freshness predicate: a `stale_odds` row is by definition non-NULL. No substring
test is executed anywhere in the primary path, so the wildcard hazard has no
surface in it.

**The `instr` form is registered where it does apply** — §S item 10, the
per-code diagnostic over the *suppressed* population, which is the only place
this design tokenises the composite column. Both forms are fixed here:

```sql
-- SQL, if the run is ever made against the volume directly:
instr(',' || r.suppressed_reason || ',', ',<code>,') > 0
```

```python
# Python, over the HTTP payload — exact token match on the split, no wildcard
# surface at all. This is the form the run will actually use.
code in (row["suppressed_reason"] or "").split(",")
```

### C2. "One observation per `(game, instant, market)`" needs `market` pinned down, and the right key is code-derived rather than empirical

The brief's rationale cites `TOR-yes ask == ATL-no ask` — an **empirical**
equality observed in the slice. The equality of the *fair* is stronger than
that and is **structural**, which makes a better key:

**[COMPUTED FROM CODE — `runner.py:665-693`]** for `side == "no"` the runner
sets `side_outcome` to *the opponent* and joins
`fair_price_id = fair_ids[side_outcome]`. So

```
row(ticker <EVENT>-X, side "yes") -> fair = p_conservative(X)
row(ticker <EVENT>-Y, side "no" ) -> fair = p_conservative(the other outcome, = X)
```

The two rows carry the **identical** `fair_probability` **by construction**,
not by coincidence. The worked example in the joint-bound result is
`id 979 = ...CHISEA-SEA no` and `id 980 = ...CHISEA-CHI yes`, both ask 470,
both edge +12.0.

**The ask is NOT identical by construction** and the brief's framing slightly
overstates this. `ask_for_side` derives a YES ask from the market's own NO bid
and a NO ask from its own YES bid (`runner.py:673`, `:682`), so the two rows of
one claim are quoted off **two different Kalshi order books**. Their asks
happened to coincide in the slice. §3 therefore registers a **representative
selection rule** and a **mandatory within-group ask-range print**, rather than
assuming the collapse is lossless.

### C3. There is no `event_ticker` on the ledger payload

**[COMPUTED FROM CODE — `_serialise`, `routes.py:1991-2072`]** the payload
carries `id, ticker, side, created_ms, ask_tenths, fair_probability,
p_multiplicative, p_additive, p_power, p_shin, p_conservative, edge_tenths,
fee_predicted, suggested_contracts, reference_contracts, kelly_fraction,
kalshi_quote_age_ms, odds_age_ms, depth_at_ask, suppressed_reason,
reason_text, clv_tenths, clv_horizon_hours, strategy_config_version` and
**not** `event_ticker` or `league`. The cluster key over HTTP is therefore the
registered fallback of §3, with its known defect printed.

---

## §P. Prerequisites — checked before any statistic is computed

Each is a yes/no. If any is NO, the run stops and this file is **amended by
appending**, never edited in place.

- **P1 — the deployed route serves the pin.** Page 0 returns a non-`None`
  `newest_id`. If it does not, the deployed build predates the paging contract
  and **no run happens** — a slice is not a population here and labelling it
  has already failed to travel with the number
  (`2026-08-10-joint-bound-result.md` §10).
- **P2 — the pull is complete and duplicate-free.**
  `len(ids) == len(set(ids)) == total`, asserted, not inspected.
- **P3 — `ask_tenths` is a tradeable price on every analysed row**, i.e. in
  `[1, 999]` **[COMPUTED FROM CODE — `core/prices.is_valid_price`; 0 and 1000
  are settled outcomes and `effective_price` raises rather than pricing them at
  a zero fee]**. Out-of-range rows are **counted and dropped, never clamped**.
- **P4 — `suppressed_reason` is never the empty string.** Assert the count of
  `suppressed_reason == ""` is 0. `SuppressionResult.reason` returns `None`
  when nothing fired, so this should never fire; if it does, the population
  predicate is ambiguous and the run stops.
- **P5 — the four `p_*` are non-NULL on the clean population**, or §7's H3a and H3b are
  not evaluable. They are nullable in `fair_prices`
  **[COMPUTED FROM CODE — `store/schema.sql:290-293`]**. A NULL resolves to
  `None` and the row is **excluded from H3a and H3b only**, counted, and never imputed
  to 0.
- **P7 — if the deployed build carries `inconsistent_consensus_metadata`, it
  never fires.** ADR 0019's added check compares `market_width is None` against
  `book_count < 2`. **[COMPUTED FROM CODE]** `consensus_devig` derives both from
  `len(selected)` (`devig.py:311-313`), and the check uses a **literal** two
  rather than `config.min_book_count`, so the two operands are equal by
  construction at any config. The evidence required is the coordinating lane's
  offered pin-test — an assertion that the check never fires across
  `tests/fixtures/odds_mlb_h2h_spreads_totals.json` — **plus** the run's own
  token census (§S item 10) showing zero occurrences in the record. If either
  shows it firing, the clean population moved and §V's void condition is met.
- **P6 — `p_conservative == fair_probability` and
  `p_conservative == min(p_multiplicative, p_additive, p_power, p_shin)`** on
  every analysed row. This proves the `fair_price_id` join landed on the right
  row. It held 1,549/1,549 in §0.2; it is re-asserted, not assumed.

---

## §1. The question, as a claim that could be false

Three registered claims. **Each states its direction. Each has its reachability
checked in both directions in §R.** Their standings differ and the difference is
the point.

> **H1 — REPRODUCTION, not discovery.** Over the clean, deduplicated population
> of the whole pinned table, the **maximum** recomputed net edge `E1` is
> **at most 0** — no clean observation clears the deployed fee.
> *Direction: one-sided, `max E1 <= 0`. Falsifier: at least one clean
> deduplicated observation with `E1 > 0`.*
>
> **§0.2 has already measured this at row granularity and §3's representative
> rule makes the deduplicated maximum identical to the row maximum.** H1 is
> therefore **live only over rows written since `id = 1549`.** §R2 requires the
> `id > 1549` suffix count to be printed **before** the verdict, and if that
> suffix is empty the verdict is labelled
> `REPRODUCTION — NOT A NEW OBSERVATION` and may not be cited as one.

> **H2 — CONCENTRATION. Genuinely open.** No single game contributes more than
> **50%** of the clean deduplicated observations.
> *Direction: two-sided in the sense that both outcomes are informative;
> declared as `max_game_share <= 0.50`. Falsifier: `max_game_share > 0.50`.*
> The 50% is not a chosen constant in any meaningful sense — it is the point at
> which "the pooled distribution" and "one game's distribution" stop being
> distinguishable, and CLAUDE.md already requires the largest contributor's
> share beside every aggregate.

> **H3a — RESOLUTION, TYPICAL ROW. Genuinely open.** On **at least
> half** of clean deduplicated observations, the shortfall `S = −E1` exceeds
> that same observation's own devig-method spread
> `spread_tenths = (max − min over the four p_*) × 1000`.
> *Direction: one-sided, `median(S − spread_tenths) > 0`. Falsifier:
> `median(S − spread_tenths) <= 0`.*
>
> **[PRIOR DISCLOSED — §0.6]** the live-path consensus spread has median
> **1.3 tenths** and every clean `S` is at least **2.1** (§0.2), so H3a is
> likelier to be declared than refuted. It is registered anyway and its
> reachability is checked in §R4 rather than argued from that prior.

> **H3b — RESOLUTION, THE NEAREST ROW. Genuinely open, on a knife edge, and it
> is the deliverable.** Let `S_min` be the smallest shortfall over clean
> deduplicated observations and `spread_at_min` be the devig-method spread **of
> the observation that attains it**. Then `S_min > spread_at_min`.
> *Direction: one-sided. Falsifier: `S_min <= spread_at_min`.*
> If two or more observations tie at `S_min`, the claim is evaluated at the one
> with the **largest** `spread_at_min` — the reading least likely to declare —
> and all tied observations are printed.
>
> **Why this and not the median, and the credit is the coordinating lane's.**
> The sentence the recorded lesson demands is *"0 rows clear, and the nearest
> is X.XXc short"*. That sentence is about **one order statistic**, and H3a's
> median cannot license it. **[MEASURED — §0.6]** `S_min = 2.1 tenths` sits
> **inside** the measured consensus-spread range `[0.32, 4.61]`, so whether the
> nearest row is distinguishable from the bar depends on that row's own spread
> and **is not determined by anything observed**. Neither answer is known and
> the two are close.
>
> **What each answer forbids.** If H3b is **refuted**, the nearest clean row is
> **not distinguishable from clearing** given the uncertainty in its own fair,
> and *"the nearest is 0.21c short"* **may not be written** — in the ADR, in
> `tasks/NEXT.md`, or anywhere else — and the existing occurrences of it must be
> annotated. Only *"no clean observation clears"* survives. If H3b is
> **declared**, the sentence is licensed and must be quoted with
> `spread_at_min` beside it.

> **H4 — FABRICATED FAIRS IN THE CLEAN POPULATION. Genuinely open, and it is
> another lane's blocker.** No clean row carries a degenerate fair.
> *Predicate, fixed here and deliberately NOT the `tasks/NEXT.md` signature:*
> `abs(p_multiplicative − 0.5) < 1e-12`. *Direction: declared on a count of
> zero. Falsifier: at least one clean row matching.*
>
> **Why the predicate drops the ULP condition.** **[MEASURED — ADR 0019 §2]**
> requiring `p_power` one ULP below 0.5 silently drops the `1.95/1.95` case,
> where all four methods return exactly 0.5, the method spread is exactly
> `0.0`, and the guard is *more* dead rather than less. The narrower signature
> undercounts, and undercounting flatters.
>
> **Why the clean population is the right place to look, and why `book_count`
> is not needed.** ADR 0019's SQL joins `fair_prices.book_count >= 2`, which is
> not on the ledger payload. It does not need to be: `too_few_books` fires iff
> `book_count < min_book_count = 2` **[COMPUTED FROM CODE —
> `suppression.py:185`]**, so **a clean row has `book_count >= 2` by
> construction**. Every clean matching row is therefore a two-book degenerate
> row, which is precisely ADR 0019's pending input 1.
>
> **What each answer does.** Zero → *reachable, never occurred*, and ADR 0019's
> §4 pin-test is the whole remedy. Non-zero → this run carries the count, the
> ask distribution and the ids, ADR 0019 cannot be Accepted as drafted, **and
> H1's own result is contaminated**, because a fabricated 0.5 fair clears
> `0 < net_edge <= 40.0` only in `ask ∈ [440, 479]` **[MEASURED — ADR 0019
> §4]** — a window inside this population.

**Nothing else is a claim.** Every other quantity in §S is descriptive, and
§7 makes descriptive cells structurally incapable of producing a finding.

---

## §2. The population, and the exclusions

### Included

Every row of the pinned pull with

- `suppressed_reason IS NULL` — **the clean population**, and
- `ask_tenths` in `[1, 999]` (P3), and
- `fair_probability` non-NULL.

**Whole table, not a slice.** No date filter, no horizon filter, no CLV
requirement, no league filter, no cap, no ordering-based draw. Every row
satisfying the predicate enters. This removes the discovery-order failure by
construction.

### Excluded, with the reason each exclusion is independent of the outcome

| Excluded | Why | Independent of `E1`? |
|---|---|---|
| `suppressed_reason IS NOT NULL` | This *is* the population definition: the clean set is the set the deployed system would act on. | **NO, and this is disclosed rather than claimed.** See below. |
| `ask_tenths` outside `[1, 999]` | 0 and 1000 are settled outcomes, not quotes; `effective_price` raises rather than pricing them at a zero fee. | Yes — a property of the stored price alone. |
| `fair_probability` NULL | `NOT NULL` in the schema; an assertion that should never fire. Dropped and counted, never imputed. | Yes. |

### The exclusion that is NOT outcome-independent, stated plainly

**Two of the eleven suppression checks are functions of the edge itself**
**[COMPUTED FROM CODE — `core/suppression.py:224-244`]**:

```python
"edge_within_method_noise":  edge_tenths <= 0 or edge_tenths > spread_tenths
"suspicious_edge":           edge_tenths <= config.edge_ceiling_tenths   # 40.0
```

So the clean population is **defined partly by the dependent variable**. A row
is squeezed out from above if its stored edge exceeds 40.0 tenths, and from
below if its stored edge lies in `(0, spread_tenths]`.

**This is not a defect that can be fixed by choosing a different population** —
the clean set is exactly the set the deployed system acts on, and that is the
set the question is about. What it forbids is reading `max E1 <= 0` as evidence
that *no* positive edge exists in the record: 45 rows with a positive net edge
exist and every one is suppressed **[MEASURED — slice]**. §10 carries this and
§R computes what it does to reachability.

### A rule that must not be activated after the fact

If the deduplicated `n` comes in thin, the temptation will be to relax the
population to `suppressed_reason` containing only "harmless" codes, or to
re-admit `edge_within_method_noise` rows. **That is forbidden.** The precedent
is in this repo: a combo experiment pre-registered an exclusion and the agent
correctly refused to activate it when the sample turned out too thin. Refusing
was possible only because the rule existed in writing first.

**No exclusion in this document references `clv_tenths`, `settled_win`, or the
stored `edge_tenths` column.** The two edge-dependent suppression codes are
inherited from the deployed system, disclosed above, and not chosen here.

---

## §3. The unit of observation, the clustering variable, and the dedup key

**`measurement-skeptic`'s priority target is this section.** It is specified to
be attacked.

### The independence unit is the game. Nothing smaller is claimed independent.

**Clustering variable:** `cluster_key` = the ticker with its final `-`-segment
removed when the ticker has three or more `-`-segments; otherwise the ticker
unchanged. **[COMPUTED FROM CODE — 702 real tickers in `tests/fixtures/`;
`KXWNBAGAME-26AUG10TORATL-TOR` → `KXWNBAGAME-26AUG10TORATL`]** No fixed
character count is chopped; that was the predecessor's bug, which inflated `G`.

A game's markets resolve from one final score. Two observations are independent
only if their `cluster_key`s differ.

**Known defect, registered rather than discovered later:** the event ticker
carries the series prefix, so if the recorder ever writes rows about spreads or
totals, one game becomes several clusters and `G` inflates — the flattering
direction. **[MEASURED — whole record]** `KXMLBGAME` 1,131 and `KXWNBAGAME` 418
rows; no TOTAL or SPREAD market has ever been recommended. **Mandatory print:**
distinct series prefixes, and the count of `<DATE+TEAMS>` suffixes appearing
under more than one prefix. Non-zero means `G` is inflated and by how much.

### The dedup key, fixed

**`claim_key(row)`**, built in two steps:

1. **Suffix set per cluster.** Over the whole pinned pull (not per instant),
   collect `suffix(ticker)` = the final `-`-segment, for every row of that
   cluster. Call it `T(cluster)`.
2. **The claim.**
   - `side == "yes"` → `claim = suffix(ticker)`.
   - `side == "no"` and `|T(cluster)| == 2` → `claim = the other member of T`.
   - `side == "no"` and `|T(cluster)| != 2` → **not normalised**; `claim =
     ("NO", suffix(ticker))`, and the cluster is reported in the
     non-normalisable list.

**The registered unit of observation is the `(cluster_key, created_ms,
claim)` triple.** Justification is §C2's code-derived identity: the two rows of
a normalised claim carry the *same* `fair_probability` by construction, so they
are one reading of one consensus about one outcome at one instant.

### Representative selection within a duplicate group — load-bearing

> Within each `(cluster_key, created_ms, claim)` group, the retained
> observation is the row with the **largest `E1`**. Ties are broken by the
> **lowest `id`**.

Two reasons, both registered before the run:

- **It is conservative in the direction that matters.** Keeping the most
  favourable row maximises the chance of falsifying H1. Dedup therefore cannot
  manufacture the null.
- **It makes the deduplicated maximum exactly equal to the row maximum**, so
  H1's answer cannot move because of a key choice. Every effect of dedup lands
  on the count and the distribution, which is where it belongs.

### Five counts, printed side by side, always

| Count | Definition | What it is |
|---|---|---|
| `n_rows` | clean rows | **uptime** |
| `n_ticker_side_instants` | distinct `(cluster, created_ms, ticker, side)` | integrity: **must equal `n_rows`** or the recorder is double-writing |
| `n_obs` | distinct `(cluster, created_ms, claim)` | **the registered unit** |
| `n_claims` | distinct `(cluster, claim)` | the hardest floor — one observation per standing claim, all instants collapsed |
| `G` | distinct `cluster_key` | **the independence unit** |

**No count in this document is claimed to be a count of independent
observations.** Even `n_claims` gives roughly two per game.

### Three leaks in the key, all registered, all in the inflating direction

1. **Instant granularity.** `created_ms` is an exact integer. Two rows of one
   claim written 1 ms apart are two observations. **[MEASURED]** one
   `created_ms` on this table carries 84 rows, so a sweep does share one stamp
   — but nothing enforces it. **Print:** the count of claim-pairs whose
   `created_ms` differ by `<= 1000 ms`. **Do not collapse them** — choosing a
   tolerance after seeing the distribution is choosing a cut from the data.
2. **`persist_if_changed`.** A row is written only when the ask or the fair
   *moved* (`engine.persist_if_changed`), so one leg of a claim may be absent
   at instant `t` while the other is written. The standing claim is then
   counted once at `t` and once at its own earlier instant. Keyed dedup cannot
   see this. `n_claims` is the bound that does.
3. **Volatility weighting.** For the same reason, rows-per-game tracks price
   volatility, so the record over-represents volatile, wide-disagreement games
   — **the direction that inflates an apparent edge**. `n_claims` and the
   per-game view are the detectors; nothing here corrects it.

### The within-group print that tests C2's collapse

For every collapsed group of size `>= 2`: the range of `ask_tenths` and the
range of `fair_probability`. **The fair range must be 0.0 on every group** —
that is C2's structural identity asserted, and a non-zero value means the
`fair_price_id` join or the opponent-lookup does not behave as
`runner.py:665-693` says. The ask range is **expected to be non-zero sometimes**
and is reported as a distribution, not asserted.

---

## §4. The cut — bucket edges, fixed in advance

**Bucketing is on `ask_tenths`, the derived ask — the price actually paid,
never a mid.** **[COMPUTED FROM CODE — `runner.py:673`, `ask_for_side` derives
a YES ask from the opposing NO bid]**. A bucket in the predecessor project
showed a +25.4 point edge and lost money for exactly this reason.

### Grid D — the deployed-fee-homogeneous partition at n=1

**Three cells, derived from the fee curve itself, not chosen.**
**[COMPUTED FROM CODE — `effective_price(p, 1)` swept over all 999 tradeable
prices]** the deployed taker fee at one contract is a three-run step function:

```
ask_tenths [  1, 172]   fee = 10.0 tenths   (172 prices)
ask_tenths [173, 827]   fee = 20.0 tenths   (655 prices)
ask_tenths [828, 999]   fee = 10.0 tenths   (172 prices)
```

This is the coarsest partition on which **the bar a row must clear** is
constant. It is the only cut with any claim to being natural here, and it is
data-blind.

### Grid B — `analysis.validate.BUCKETS`, verbatim

**[COMPUTED FROM CODE]** ten cells: `(10,100) (100,200) … (900,990)`. Reused
rather than restated so it cannot be re-chosen. Rows outside `[10, 990)` fall in
no Grid B cell and are counted in an explicit `outside` row — the pooled
population and the grid must be the same rows or neither is readable.

### No other cut

**No cut may be introduced after the data is read.** Not by side, not by day,
not by league, not by time to kickoff, not by depth, not by odds age, not by a
re-derivation of Grid D at a different contract size. Each is defensible and
that is exactly the problem.

Grid D is explicitly **not** re-derived at any `n != 1`. n=1 is fixed by §6 for
reasons independent of the cut.

---

## §5. The statistic, named as an estimator

### The edge is RECOMPUTED. The stored column is a diagnostic. Add-back is forbidden.

`store/schema.sql:375-383` states it: `edge_tenths` is a per-contract edge at
**one specific size which the column does not carry** — `engine.py:204` computes
it at `max(1, sizing.contracts)`, the fee's per-order rounding is size-dependent,
and the divisor is not recoverable from the row.

```python
E1 = backend.core.ev.edge_after_fees_tenths(
        ask_tenths=ask_tenths, contracts=1,
        fair_probability=fair_probability, maker=False)

S  = -E1        # the SHORTFALL, in tenths of a cent. S > 0 means it falls short.
```

**[COMPUTED FROM CODE — verified numerically]** the identity
`E1 == 1000*fair − ask − fee_tenths(ask)` holds exactly, with `fee_tenths` the
Grid D step function. It is asserted per row at run time.

- **`maker=False`.** Taker. The maker path has a different bar (50.44%) and is
  out of scope; see §10.
- **n=1 and it is not convenience.** It is the most conservative per-contract
  fee any order size pays, it is what `size_position` itself prices at
  (`sizing.py:156`), and it is the basis on which `actionable` is decided —
  which is what makes §0.4's derivation exact.
- **The add-back is forbidden.** Reconstructing a gross edge as
  `edge_tenths + fee_predicted` is exact only at N=1 and silently enormous
  otherwise — ADR 0017 Addendum A gives 208 tenths against a true 28. The N is
  not in the row.
- **No `E1min`, no cheapest-model variant, no maker variant, no alternative
  devig.** Those are knob relaxations and the joint bound is dead.

### The estimators, said out loud

| Quantity | Estimator | Standing |
|---|---|---|
| `max E1` | **a maximum over a complete enumeration of a finite, fully observed population** | H1. A census statement. Sampling error is exactly zero *for this snapshot* and **undefined** as an estimate of anything else. |
| `max_game_share` | **a ratio of two exact counts over the same census** | H2. No interval. |
| `median(S − spread_tenths)` | **the median of a paired within-observation difference** | H3. Paired: both terms come from the same row, so no between-row variance enters. No interval. |
| per-game `max S`, quantiles of `S`, Grid D / Grid B cells | order statistics of a census | **Descriptive.** §7. |

**`sqrt(p(1-p)/n)` is correct for none of these.** It is not used anywhere in
this design, and neither is any other standard error: see §7.

---

## §6. The extraction, fixed in advance

**The pull is pinned, and the code already exists — do not re-derive it.**
`scripts/run_joint_bound.py:159-217`:

1. `GET /api/ledger?limit=1000&offset=0` with no `max_id`. Read `newest_id`.
2. `pin = int(page0["newest_id"])`. Pass `max_id=pin` on **every** subsequent
   page, paging by `offset` until `offset >= total`, where `total` is read
   under the same pin.
3. Assert `len(ids) == len(set(ids)) == total` (P2). Record `pin` and
   `pulled_at_utc` in the result.

**Why the pin is load-bearing and `offset` alone is a trap:** the route sorts
`(created_ms DESC, id DESC)`, so a row written *during* a multi-page pull lands
on page 0 and shifts every later page. **[MEASURED — reproduced, 120 rows in
four pages with one 84-row sweep landing mid-pull]** unpinned returned 120 rows
of which only 90 were distinct, with 84 original rows never returned; pinned
returned 120 distinct. **The failure is silent** — every page reports the right
`returned` and the pages sum to `total`.

Credentials: `configure_logging()` **before** any client is constructed. `httpx`
logs full request URLs at INFO and this repo has already put a working
credential into a transcript that way. The token is read from the repo-root
`.env`, used for one form POST to `/session`, held in memory, and never written
to the cache file.

The pull is cached to
`docs/measurements/<run-date>-clean-shortfall-pull.json` so the analysis is
re-cuttable without re-pulling.

---

## §7. The decision rule, with the multiplicity already counted

### The multiplicity count is zero, and that is a design choice with a price

| Family | Cells | Interval attached? |
|---|---:|---|
| H1, H2, H3a, H3b, H4 | 5 | **No.** Census statements over a fully enumerated finite population. |
| Grid D | 3 | No |
| Grid B | 11 (10 + `outside`) | No |
| Per-game | `G` (≈59 expected) | No |
| Series-prefix strata | 2 expected, printed | No |
| `strategy_config_version` strata | printed | No |
| Suppressed-population per-code diagnostic | 14 | No |

> **No cell in this design carries an interval, a standard error, a p-value or
> a significance mark.** A cell with no interval attached cannot "clear 2 SE",
> so it cannot produce a false finding by clearing a threshold, and the
> family-wise error rate of this design is **empty rather than controlled**.
> **[COMPUTED]** the arithmetic that would otherwise apply: ~90 descriptive
> cells at two standard errors gives `90 × 0.0455 = 4.1` expected false
> findings and `P(at least one) > 0.98`. That is the number this design avoids
> by not being an inference.

**The price, stated because it is real:** nothing in this document generalises.
It is a census of one pinned snapshot of one 46+ hour recording window in two
leagues in August. It supports no statement about future rows, and any reader
who treats `n_obs` as a sample size has misread it. That is registered in §10
and repeated in the harness docstring.

**There is no always-valid boundary because there is no interval and no second
look.** §8 permits exactly one pull. A re-look is a new registration.

### The decision rule, verbatim

> **All five claims are evaluated and all five are reported, in the order
> H4, H2, H3a, H3b, H1.** H1 is reported last deliberately: it is the one whose answer
> is already known, and putting it first is how a reproduction gets read as a
> discovery. H4 is reported first because it can contaminate H1.
>
> **GUARDS FIRST.** §R1, §R3, §R4's H4 twin and `G >= 2` are evaluated and
> printed **before any claim**. If any of them trips, **no claim is declared**,
> the run reports `STOP THE LINE` with the tripped guard named, and the
> refutation ADR of §9 is not written from it. §R2 is printed at the same time
> but is a **labelling** rule, not a stop: it never blocks a claim, it decides
> whether H1 may be called new.
>
> **H4 — FABRICATED FAIRS.**
> Let `n_degen` be the count of clean rows (pre-dedup, so nothing can hide in a
> collapsed group) with `abs(p_multiplicative − 0.5) < 1e-12`.
> **Declared** iff `n_degen == 0`.
> **Refuted** iff `n_degen > 0`; the write-up then enumerates every one by
> `id`, `ticker`, `side`, `ask_tenths`, all four `p_*`, `odds_age_ms` and
> `created_ms`, reports how many fall in `ask ∈ [440, 479]`, and **flags H1 as
> CONTAMINATED** — a clean row built on a fabricated fair is not evidence about
> the strategy either way.
> Printed regardless, and separately: the same count over the **suppressed**
> population, and the count under the narrower ULP signature, so the
> undercounting of §0.6 item 3 is visible as a number rather than argued.
>
> **H2 — CONCENTRATION.**
> Let `max_game_share = (observations in the largest cluster) / n_obs`.
> **Declared** iff `max_game_share <= 0.50`.
> **Refuted** iff `max_game_share > 0.50`, and the write-up must then state, in
> these words, that **the pooled distribution is one game's distribution**, and
> every pooled quantile in the result is struck through and replaced by the
> per-game table.
> Reported at every level regardless: `n_obs`, `G`, the per-game observation
> counts, and the largest cluster's share — **beside every aggregate**, per
> CLAUDE.md.
>
> **H3a — RESOLUTION, TYPICAL ROW.**
> Precondition, printed **first**: `n_spread`, the number of clean deduplicated
> observations with all four `p_*` non-NULL. If `n_spread < 5`, H3a and H3b are
> both **UNRESOLVED** — the repo's `MIN_EXPECTED_PER_SIDE` rule, read before the
> effect size — and no statement about resolution may be made.
> Given `n_spread >= 5`:
> **Declared** iff `median over those observations of (S − spread_tenths) > 0`.
> **Refuted** iff `median(S − spread_tenths) <= 0`.
> Reported regardless: the paired median, the share of observations with
> `S > spread_tenths`, and the marginal distributions of `S` and of
> `spread_tenths` (min, p25, median, p75, max) **side by side in one table**.
> **H3a may not be described as having answered H3b**, and the write-up says so
> in those words if it declares H3a and refutes H3b.
>
> **H3b — RESOLUTION, THE NEAREST ROW. This one governs the citable sentence.**
> Let `S_min = min(S)` over clean deduplicated observations with all four `p_*`
> non-NULL, and `spread_at_min` the spread of the attaining observation — the
> **largest** such spread if there is a tie, with every tied observation
> printed.
> **Declared** iff `S_min > spread_at_min`.
> **Refuted** iff `S_min <= spread_at_min`, and the write-up must then state, in
> these words, that **the nearest clean observation is not distinguishable from
> clearing**, must **not** contain any sentence of the form *"the nearest is
> X.XXc short"*, and must list the existing occurrences of that sentence in
> `tasks/NEXT.md` and `2026-08-10-joint-bound-result.md` as requiring
> annotation.
> Printed regardless: `S_min`, `spread_at_min`, the attaining observation's
> `id`, `ticker`, `side`, `ask_tenths`, `fair_probability` and all four `p_*`.
>
> **H1 — REPRODUCTION.**
> **Declared** iff `max over clean deduplicated observations of E1 <= 0`.
> **Refuted** iff at least one clean deduplicated observation has `E1 > 0`; the
> write-up then **enumerates every such observation** by `id`, `ticker`,
> `side`, `ask_tenths`, `fair_probability`, the four `p_*`, `spread_tenths`,
> `depth_at_ask`, `odds_age_ms` and `kalshi_quote_age_ms`.
> **Labelling is mandatory and mechanical.** Let `n_new` be the count of clean
> rows with `id > 1549`. If `n_new == 0`, the H1 verdict is printed as
> `REPRODUCTION — NOT A NEW OBSERVATION`. If `n_new > 0`, H1 is **additionally
> evaluated on the `id > 1549` suffix alone** and both results are printed; only
> the suffix result may be described as new.
>
> **THE ONE-WAY DOWNGRADE.**
> Each declared or refuted claim is recomputed on the reduced population that
> leaves out **each cluster in turn** (leave-one-game-out) and, separately, on
> `n_claims` — the all-instants-collapsed key of §3. **If any recomputation
> reverses a declaration or a refutation, that claim is downgraded to
> UNRESOLVED and the write-up names the reduction that caused it, in those
> words.** The rule is strictly one-way: it can never create a declaration and
> can never raise a verdict.
>
> **No bucket, no stratum, no Grid D cell, no Grid B cell and no per-game cell
> may substitute for any of the five claim statistics, or be reported as
> significant, or be described with any word implying a test.**

---

## §R. The reachability guards — both directions, because the last instrument failed here

`tasks/lessons.md`, *"A reachability guard has to run in both directions"*: the
joint bound guarded `K = 0` everywhere and did not guard `K ≈ N` everywhere,
and it saturated at 100%. Falsifiability is a property of the instrument as a
whole and had no owner. It has one here.

### R1 — the falsifier of H1 must be arithmetically reachable

**What would falsify H1:** a clean deduplicated observation with `E1 > 0`.

**Is it reachable? Checked as arithmetic, not plausibility.** A clean row is one
where all eleven checks pass and sizing did not refuse. Two checks are functions
of the edge (§2), so a clean row with a positive stored edge requires

```
spread_tenths  <  edge_tenths  <=  40.0        # config.edge_ceiling_tenths
```

**[MEASURED FROM DATA — §0.6, the live money path, which is the right
reference class and not the `~1.8 / ~20.3` example-line pair in
`suppression.py`'s comment]** the post-anchoring consensus spread has median
**1.3 tenths** and a range of **0.32 – 4.61 tenths**. So the window is
`(4.61, 40.0]` at its **narrowest observed** and `(0.32, 40.0]` at its widest —
**non-empty across the entire observed range**, and wider than the example-line
figures would have suggested. The guard is satisfied more comfortably on the
measured numbers than on the derived ones, which is the safe direction. The falsifier is
reachable. It is also **observed to occur elsewhere in the record**: 45 rows
carry a positive net edge **[MEASURED — slice]**, so the value is one the system
demonstrably produces; they are all suppressed, which is what H1 is about.

**Registered guard, evaluated at run time rather than asserted here:**

> **R1.** Print `n_window`, the count of clean deduplicated observations whose
> own `spread_tenths` is strictly below 40.0 — i.e. for which a positive clean
> edge is not excluded by the two edge-dependent checks acting together.
> **If `n_window == 0`, H1 could not have returned its falsifier. STOP THE
> LINE: no claim is declared and the write-up states that the instrument could
> not have seen the effect.**

### R2 — H1 must be able to return something other than its known value

The symmetric twin, and the one the joint bound lacked.

> **R2.** Print `n_new`, the count of clean rows with `id > 1549` — rows written
> since the pull of §0.2. `id` is `INTEGER PRIMARY KEY AUTOINCREMENT`, so this
> is exact.
> **If `n_new == 0`, H1 is arithmetically incapable of returning anything other
> than −2.1 tenths**, because §3's representative rule makes the deduplicated
> maximum equal the row maximum and §0.2 already measured that maximum over
> ids ≤ 1549. It is then **not a measurement**, it is a checksum, and it is
> labelled `REPRODUCTION — NOT A NEW OBSERVATION` in the verdict line and in
> every table it appears in. **This is not a stop-the-line** — H2, H3a and H3b remain
> live at any `n_new`, including zero — but H1 may not be cited as evidence.

### R3 — no cut may saturate

The direct mirror of the ladder that returned 984 of 1,000.

> **R3.** For each of Grid D, Grid B and the series-prefix stratum: if any
> single cell contains `>= 0.90` of `n_obs`, that grid **discriminates nothing**
> and is printed with the banner `DEGENERATE — DOES NOT DISCRIMINATE` and may
> not be referred to in any conclusion.
> And the twin of H2: if `G < 2`, no per-group view exists and **no pooled
> quantity is reported at all** — a pooled number is not a finding until the
> parts agree, and one part cannot agree with itself.

### R4 — the instrument must be able to return both answers on H2, H3a, H3b and H4

**H2.** `max_game_share` lies in `(0, 1]` by construction. With `G = 59`
**[MEASURED — §0.2]** and `n_obs` unknown, both `<= 0.50` and `> 0.50` are
arithmetically reachable: the former requires no game to hold more than half the
observations, the latter requires one that does. Neither is excluded by any
choice in this document. **Reachable both ways.**

**H3a and H3b.** `S − spread_tenths` is a difference of two independently
varying non-negative quantities. `S` is bounded below by 2.1 tenths
**[MEASURED — §0.2, `max E1 = −2.1`]** and above by nothing in particular;
`spread_tenths` runs **0.32 – 4.61 tenths, median 1.3** on the live path
**[MEASURED — §0.6]**. Both statistics can fall on either side of zero.
**Reachable both ways.**

**But their priors differ sharply and that is registered rather than left to be
discovered.** H3a compares the *typical* `S` — at least 2.1 and plausibly much
larger — against a median spread of 1.3, so **H3a leans declared**. H3b
compares `S_min = 2.1` against **one row's** spread drawn from `[0.32, 4.61]`,
which straddles it, so **H3b is genuinely a coin-flip on the evidence
available**. H3b is therefore the informative one, and §7 orders the report so
H3a cannot be read as having answered it.

**H4.** `n_degen >= 0` by construction, so `n_degen == 0` is trivially
reachable. The falsifier — `n_degen > 0` — requires the *state* to be reachable,
and **[MEASURED — ADR 0019 §2, `consensus_devig` into `evaluate_suppression`]**
it is: two books at `1.85/1.85` give `book_count = 2`, `market_width = 0.0`,
`method_spread ≈ 1e-14` and `suppressed_reason = None`. Every one of the eleven
checks passes. So a clean degenerate row is producible by the deployed code, not
merely imaginable. **Reachable both ways.** Whether it has *occurred* is the
question, and it is unanswered anywhere.

**And the twin, which matters because H4 is a zero-count claim.** A claim
declared on a count of zero is the shape that has already failed in this repo
twice — `tasks/lessons.md`,
*"the zero that means no measurement passes every threshold"*. The guard is the
paired print registered in §7: the **same predicate over the suppressed
population**, whose value is expected non-zero. **If the predicate returns 0 on
BOTH the clean and the suppressed populations, the predicate itself is
suspect** — §0.2 measured 21 matching rows, all suppressed, under a *narrower*
signature, so a broader predicate returning fewer is arithmetically impossible.
**That is a STOP THE LINE, and it names the harness rather than the record.**

---

## §8. The stopping rule

**One pull, one pin, one look.**

Data collection for this measurement ends at the pin taken in §6, on the date
the run executes. There is no accumulation, no interim look, no "when we have
enough". `total` and `pin` are recorded in the result.

**A second look is a new registration.** If the record is to be re-read, it is
re-registered — this file is not amended to permit a second look, because a
threshold re-evaluated against an accumulating database is not one look, it is
thousands, and under a true zero it crosses eventually with probability 1
(**[MEASURED — this repo, 1,200 pure-noise sequences]** 13.7% within 100 looks,
and that is a floor).

**Amendments are appended, never edited in place**, with their date, their
reason, and an explicit statement of what had been observed when they were
written. **An amendment made after the run and not recorded voids the
registration.**

---

## §9. What would falsify this, and what happens then

### The result's destination, fixed now, before the result exists

```
docs/measurements/<run-date>-clean-shortfall-distribution-result.md
```

One file, **written whichever way it comes out**, with that exact filename
stem, this document linked from its first line. Only the date varies.

### Consequences, in both directions

| Outcome | What is built | What is killed |
|---|---|---|
| **Any stop-the-line guard trips (R1, R3, R4's H4 twin, or `G < 2`)** | Nothing. The write-up says the instrument could not have seen the effect, and says which guard. | The run. §9's ADR is **not** written from it. |
| **H1 declared, `n_new > 0`** | The refutation ADR may be written, and **must** quote `n_obs`, `G`, `n_claims`, the largest game's share and the shortfall distribution — never `n_rows` alone. | The consensus-only taker line as a source of positive expectancy at the deployed configuration, at this `n`, stated with an honest denominator. |
| **H1 declared, `n_new == 0`** | The ADR may be written but must cite §0.2 as its evidence and this run only for the **denominator and the distribution**. | Nothing extra. The reproduction label travels with the number. |
| **H1 refuted** | The refutation ADR is **not written.** The clearing observations are enumerated and handed to the `min_book_count` / `edge_within_method_noise` lane — a clean row that clears is either a real opportunity or the known degenerate-fair bug surfacing somewhere new, and both need the bug fixed first. | The plan to close the line, immediately. |
| **H4 declared (`n_degen == 0`)** | ADR 0019's pending input 1 is answered *reachable, never occurred*; its §4 pin-test stands as the whole remedy and it can move toward Accepted. | The case for building a symmetric-placeholder detector (ADR 0019 §3(c)), on this record. |
| **H4 refuted (`n_degen > 0`)** | The count, the ask distribution and the ids go to the ADR 0019 lane immediately. **H1 is flagged CONTAMINATED and the refutation ADR is not written until the clean population is re-derived.** | ADR 0019 as drafted; the "0 unsuppressed" reassurance in `tasks/NEXT.md`; and this registration's own §2 population, which would need re-registering. |
| **H2 refuted (`> 50%` in one game)** | Per-game reporting only. | Every pooled quantile in the result, struck through. |
| **H3a declared** | The ADR may state that the *typical* clean shortfall is larger than devig-method choice explains, with the paired median. | The reading that the strategy is, in general, one method-choice away from clearing. |
| **H3a refuted** | The ADR **must** state the typical distance to the bar is inside the noise of its own input. | Any distributional claim about magnitude. |
| **H3b declared** | *"0 clean observations clear, and the nearest is X.XXc short"* is licensed, and must be quoted with `spread_at_min` beside it. | Nothing. |
| **H3b refuted** | The ADR states only *"no clean observation clears"*. | **Every sentence of the form *"the nearest is 0.21c short"*** — including those already in `tasks/NEXT.md` and `2026-08-10-joint-bound-result.md`, which must be annotated. This is the branch that changes what is already written down. |

### Is this decision-relevant, honestly?

**Partly, and the honest form is worth stating rather than overclaiming.** The
refutation ADR gets written in most branches — its *existence* is close to
determined by §0. What this measurement decides is its **denominator**, its
**quoted sentence**, and its **strength claim**, and H3b can forbid the strength
claim entirely. H1's refutation is the one branch that changes the plan outright
and it is the least likely.

If a reader concludes from this table that the answer is "we proceed either
way", that reading is available for H1 and is **not** available for H3b. H3b is
why this is worth running.

---

## §10. What this measurement cannot establish — drafted before the run

Written now, and deliberately including the ones that could overturn the
result rather than the survivable ones.

- **The one that would overturn it, first.** **The clean population is defined
  partly by the dependent variable** (§2): `suspicious_edge` removes stored
  edges above 40.0 tenths and `edge_within_method_noise` removes stored edges in
  `(0, spread_tenths]`. So `max E1 <= 0` over the clean set is **not** evidence
  that no positive edge exists in the record. 45 rows carry one; all are
  suppressed. Anyone quoting this result as "there is no edge" has read the
  wrong population.
- **The second that would overturn it, and the framing here is deliberately
  not the one in `tasks/lessons.md`.** That file says
  `edge_within_method_noise` is *structurally incapable of firing* on a one-book
  equal-odds consensus. **ADR 0019 (Proposed, in flight) corrects this**: the
  guard is correctly scoped — on a symmetric two-way line method choice
  contributes genuinely zero ambiguity, so the guard passing is a true
  statement. The real blind spot is that the **whole agreement family**
  (`edge_within_method_noise`, `wide_market` / `no_market_width`,
  `too_few_books`) is uniformly blind to *correlated* garbage, because
  placeholder lines agree with each other perfectly. **[MEASURED — ADR 0019
  §2]** two books at `1.85/1.85` produce `fair ≈ 0.5`, `width = 0.0`,
  `book_count = 2` and `suppressed_reason = None` — **inside this measurement's
  population**. The only thing bounding it is `edge_ceiling_tenths = 40.0`,
  which was never justified for that job. H4 is the registered detector; under
  either framing, **this population is a function of thresholds that could
  change** (§V).
- **H4's premise is reachable, not observed, and the only real capture
  available is the wrong population to clear it with.** **[MEASURED — §0.6]**
  `market_width == 0.0` occurs on 0 of 15 events and 0 of 425 h2h quotes are
  symmetric in `tests/fixtures/odds_mlb_h2h_spreads_totals.json` — but that
  capture is **mature MLB, 8.9–12.4h from first pitch**, so it **structurally
  cannot contain an opener**, and the degenerate fair actually seen in the
  record was **WNBA**. A zero from H4 over the live record is a census of the
  record and is worth having; a zero from the fixture is close to worthless for
  this question and must not be cited as corroboration.
- **The devig spread this design compares against is built from very few
  books by design.** **[MEASURED — §0.6]** the live anchoring keeps a median of
  **3 of 29** usable books. So `spread_tenths` measures disagreement among
  `betfair_ex_eu`, `matchbook` and sometimes `pinnacle` — not among the market.
  A narrow spread is therefore partly a statement about how few opinions were
  admitted, and H3a/H3b inherit that in the direction that makes them **easier**
  to declare.
- **It is a census, not a sample.** No quantity here supports an inference to
  future rows, to other months, or to other leagues. There is no interval
  anywhere in the design and that is deliberate (§7).
- **The fee it measures against is `calculate_fee`'s bar, not Kalshi's.** The
  entire fee model is secondary-sourced and unverified — `core/fees.py` says so
  in its own docstring — and this project has **zero fills, ever**. If both
  candidate models are wrong, every number here moves. Four real fills resolve
  this and nothing else does.
- **`fair_probability` is the worst of four devig methods** (P6 asserts it), so
  every `E1` is a deliberately shrunk number and the shortfall distribution is
  shifted toward "falls short" by an unmeasured, price-dependent amount that is
  largest at the wings. H3a and H3b are the only things in this design that put
  a number beside that shrinkage, and they measure the *spread*, not the *bias*.
- **The magnitude is not resolvable; only the sign is.** See the power check.
- **It says nothing about whether an edge exists at Kalshi.** It is a statement
  about one strategy's arithmetic on one pinned snapshot. If Kalshi is the
  sharp side, "Kalshi versus devigged sportsbook consensus" is close to empty
  by construction, and finding nothing there is a fact about the instrument's
  geometry rather than about the venue.
- **It says nothing about calibration** — whether `fair_probability` is *right*
  is a different question with different inputs (`kalshi_markets.result`).
- **It says nothing about CLV.** No row here is scored. Whether these prices
  beat Kalshi's close is the CLV registration's question and it is
  **UNDERPOWERED until G = 300**.
- **It says nothing about the maker path** (a 50.44% bar and a different fee
  curve), nothing about combos (`KXMVE`, ADR 0012), and nothing about in-play.
- **One season, two leagues, one month.** MLB and WNBA in August 2026. Nothing
  about NBA, NCAAF, NFL, or tennis.
- **`G` may be inflated by the event-ticker key** if spread or total rows ever
  enter the record (§3). The suffix-collision print detects; it does not
  correct.
- **`n_obs` is not a count of independent observations** and neither is
  `n_claims`. Independence lives at the cluster. Three named leaks (§3) all
  inflate it.
- **The record is a census of rows already written**, downstream of discovery
  and of `persist_if_changed`'s movement-only write rule. A market never polled
  contributes no row and cannot appear.

---

## The power check — which comes before all of it

**Can this measurement answer this question at the `n` available?**

There is no sampling here, so the power question is not about `n`. It has three
parts and they are answered separately.

### 1. Reachability — can the instrument return each answer?

Answered in §R, computed rather than assumed. **H1's falsifier is reachable but
its answer is already known over ids ≤ 1549** — R2 makes that mechanical rather
than a matter of anyone's reading. **H2, H3a, H3b and H4 are reachable in both directions
and genuinely unknown.**

### 2. Increment over the priors — what does the run buy?

**[COMPUTED FROM CODE]** the published `actionable = 0` alone bounds
`max E1 < 1.0 tenths` (§0.4). **[MEASURED — §0.2]** the whole-table pull already
put it at **−2.1 tenths**. So:

| Quantity | Known before the run | Increment from the run |
|---|---|---|
| `max E1` over clean rows | **−2.1 tenths, measured** | **zero** |
| clean row count | 614 rows, 59 games | zero |
| `n_obs`, `n_claims`, dedup ratio | **nothing** | the whole quantity |
| quantiles of `S`, per-game maxima | **nothing** | the whole quantity |
| `max_game_share` | **nothing** | the whole quantity (H2) |
| `median(S − spread_tenths)` | **nothing** | the whole quantity (H3) |

**The maximum buys nothing. The denominator and the distribution buy
everything.** If the run is written up with the maximum as its headline, it has
been written up as a rediscovery.

### 3. Resolution — is the reported quantity finer than the noise in its input?

**This is the part that constrains what may be said, and it is the calibration
the brief demands.**

| Quantity | Magnitude |
|---|---|
| The venue's entire headroom (52.38% → 52.00%) | **3.8 tenths** |
| The observed clean shortfall | **2.1 tenths** |
| Consensus devig spread on the **live money path**, median **[MEASURED — §0.6]** | **1.3 tenths** |
| Consensus devig spread on the live money path, range **[MEASURED — §0.6]** | **0.32 – 4.61 tenths** |
| Per-outcome spread on two example lines (`suppression.py`'s comment — **the wrong reference class**, kept only so nobody re-imports it) | ~1.8 / ~20.3 tenths |
| The size-basis artefact in the stored edge column (why §5 recomputes) | up to **5.0 tenths** |

**The reported shortfall of 2.1 tenths sits INSIDE the measured range of the
uncertainty in the fair value that generates it** — `[0.32, 4.61]` — and above
its median of 1.3. It is not merely the same order of magnitude as the input
noise; on the money path it is within that noise's interquartile reach. **This
is measured on the live anchoring, not derived from example lines**, and the
anchoring discards a median of 26 of 29 usable books to keep 3
(`betfair_ex_eu` + `matchbook` ± `pinnacle`), so the consensus being compared
against is built from very few books **by design**.

> **Registered consequence.** This design resolves the **sign** of the
> shortfall exactly, as a census, and does **not** resolve its **magnitude**.
> No statement of the form *"the strategy nearly clears"* or *"the strategy
> clearly misses"* may be made from this measurement at any `n`. **H3b is the
> registered test of whether even the single citable sentence survives**, and if
> H3b is refuted the prohibition is absolute rather than stylistic and reaches
> back to text already written.

### Verdict of the power check

**ADEQUATE for the sign, for the deduplicated denominator, for the
concentration question (H2), for both resolution questions (H3a, H3b) and for
H4's census. PERMANENTLY UNDERPOWERED for
the magnitude, at any `n` this record will reach, because the limiting quantity
is the devig-method spread and not the sample size. ZERO increment on the
maximum, which §0 has already measured.**

A measurement that cannot resolve the question is worse than none, because it
returns a number anyway and the number gets quoted. **This one can resolve four
of the five questions put to it, and §R + §7's labelling rules are what stop the
fifth — the magnitude — being quoted.**

---

## §S. Required output of every run, in this order

Read the frame before `n`, and `n` before the effect size.

1. **The frame.** `pulled_at_utc`, `pin`, `total`, pages, `len(ids)`,
   `len(set(ids))`, and P1–P6 each printed as MET or UNMET.
2. **The guards.** R1 (`n_window`), R2 (`n_new`), R3 (per-grid saturation),
   `G >= 2`. **Before any claim.**
3. **The five counts** of §3 side by side, plus the dedup ratio
   `n_rows / n_obs`, plus the count of non-normalisable clusters and the
   count of near-duplicate instants (`|Δ created_ms| <= 1000 ms`).
4. **Cluster-key integrity.** Distinct series prefixes; `<DATE+TEAMS>` suffixes
   under more than one prefix; the within-group `fair_probability` range
   (**must be 0.0 on every collapsed group**) and the within-group
   `ask_tenths` range distribution.
5. **Composition, before any rate.** Series prefix × `strategy_config_version`
   × `clv_horizon_hours`, in observations and clusters, with shares. The
   distribution of observations per cluster and **the largest cluster's share**.
6. **H4** — `n_degen` over the clean population, the same count over the
   suppressed population, the count under the narrower ULP signature, and the
   `ask ∈ [440, 479]` sub-count. **Before H1**, because it can contaminate it.
7. **H2**, with the per-game table.
8. **H3a**, with `n_spread` printed first, then the paired median, then `S`
   and `spread_tenths` side by side (min/p25/median/p75/max).
   Then **H3b**: `S_min`, `spread_at_min`, and the attaining observation in
   full. H3b is printed **after** H3a and labelled as the one that governs the
   citable sentence.
9. **H1**, last, with its R2 label, and both the whole-table and `id > 1549`
   evaluations when `n_new > 0`.
10. **Diagnostics.** The distribution of `E1 − stored edge_tenths` (the
   size-basis artefact of §5 as a printed number rather than an argument); the
   per-row assertion `E1 == 1000·fair − ask − fee_tenths(ask)`; and the
   per-code counts over the **suppressed** population using the `instr` /
   token-split predicate of §C1, with `too_few_books` and `no_market_width`
   reported as **one signal, not two** (**[MEASURED — slice]** 185 rows each,
   symmetric difference 0; both fire iff `book_count < 2`).
11. **Grid D, then Grid B**, each labelled
    `DESCRIPTIVE — CANNOT PRODUCE A FINDING`, with any saturated cell carrying
    R3's banner and the Grid B `outside` count shown.
12. **The one-way downgrades** (leave-one-game-out, and the `n_claims` key),
    naming any reduction that reversed a verdict.
13. **§10, reproduced verbatim.**

The harness module docstring states what this does not establish, per the repo
rule that every harness carries its own limits.

---

## §V. Verdict at registration, and the condition

**READY-CONDITIONAL.**

## The condition, corrected — it is keyed to DEPLOYMENT and to FIREABILITY, not to the working tree

**An earlier draft of this section voided the registration on any change to
`SuppressionConfig` in the working tree. That was wrong, the coordinating lane
challenged it, and the challenge is upheld.** Recorded here rather than
silently fixed, because over-broad void conditions are how two independent
lanes become mutually exclusive for no arithmetic reason.

**The mechanism, verified against source rather than accepted on description:**

- `suppressed_reason` is computed at `engine.py:217` and written **at INSERT**
  by `persist_recommendation` (`engine.py:362-379`).
- `gate.POPULATIONS` (`gate.py:323`) reads it **from the table**.
- **[COMPUTED FROM CODE — grepped every `UPDATE recommendations` in the repo]**
  the only mutations are to `clv_tenths`, `closing_line_id`,
  `last_confirmed_ms`, `clv_horizon_hours` and `reference_contracts`
  (`analysis/clv.py:267`, `engine.py:421`, `store/db.py:234,259`).
  **Nothing anywhere UPDATEs `suppressed_reason`.** It is write-once.

So the clean population of §2 is decided, row by row, by **the binary that was
deployed at each row's `created_ms`**. A local edit cannot reach a persisted
row, and the `max_id` pin excludes rows written after the pull begins.

### The void condition, restated

> **This registration is VOID if, before the pull completes, a change is
> DEPLOYED that can alter `suppressed_reason` on at least one row the current
> consensus producer can emit.**
>
> Three-part test, all three required:
> **(a) Deployed.** Working-tree and committed-but-undeployed changes cannot
> reach persisted rows (mechanism above). Deploys are batched and Joe's.
> **(b) Capable of altering `suppressed_reason`.** A comment, a test, or a
> raise on a branch no production caller reaches cannot.
> **(c) Able to fire on a producible row.** A check whose predicate is
> unsatisfiable given the producer's invariants cannot move any row.

### Applying it to ADR 0019: NOT a void trigger. Lane A is free to commit and to deploy.

- **No threshold value moved.** Verified by diff: `min_book_count` 2,
  `edge_ceiling_tenths` 40.0, `max_market_width`, `max_odds_age_ms`,
  `max_kalshi_quote_age_ms`, `max_commence_skew_ms`, `min_depth_contracts` all
  untouched. The §V list is intact.
- **`inconsistent_consensus_metadata` fails (c).** **[COMPUTED FROM CODE]** it
  tests `(market_width is None) == (book_count < 2)`; `consensus_devig` derives
  both from `len(selected)` (`devig.py:311-313`), and the check uses a
  **literal** two rather than `config.min_book_count`, so the operands are equal
  by construction **at any config value** — the literal is what makes it an
  invariant assertion rather than a config-coupled check, and it is the reason
  this ruling does not expire if `min_book_count` later moves.
- **The comment and `runner.py:342`'s raise fail (b).** The raise replaces
  `metadata.get("book_count", 0)`, unreachable from the only production caller.

**Answering the question directly: holding Lane A's commit is not necessary,
and a clean tree is not necessary.** Neither is sufficient either — the thing
that matters is (a). What I do ask for is **P7**: the offered pin-test asserting
the check never fires across the fixture. That is the evidence for (c), it costs
one test, and without it (c) rests on my reading of two files.

### What this condition does NOT protect against, stated because it is the live hole

**The record may ALREADY be a multi-configuration mixture**, and one of the two
detectors cannot see half of it.

**[COMPUTED FROM CODE — `runner.py:539`, `ensure_strategy_config`,
`engine.py:325-359`]** the version payload is
`{"suppression": suppression.__dict__, "kelly_fraction": ..., "max_order_contracts": ...}`,
so **any change to a `SuppressionConfig` field value mints a new
`strategy_config_version` automatically**. That detector is real, not
decoration.

**But adding, removing or rescoping a `Check(...)` adds no field**, so it mints
**no** new version. `inconsistent_consensus_metadata` is exactly that case.
**A check-vocabulary change is invisible to `strategy_config_version`.** The
partial substitute is §S item 10's token census, which detects a new code only
if it *fires* — and a check that cannot fire cannot move the population anyway,
which is why (c) closes the loop rather than leaving it open.

**Three detectors, with their coverage stated honestly:**

1. **`strategy_config_version` distribution** (§S item 5). Covers **threshold
   value** changes, past and future, completely. More than one value in the
   record means it is already a mixture and the write-up must say so.
2. **H4's own count.** `n_degen` over the clean population is **0 today**
   **[MEASURED — §0.2, on a predicate that can only undercount]**. Non-zero is
   either a configuration move or ADR 0019's pending input answering positively,
   and detector 1 distinguishes them.
3. **The DEPLOYED revision of `backend/core/suppression.py`**, recorded in the
   result header beside `pin` and `pulled_at_utc`. **[COMPUTED FROM CODE — no
   `/api/*` route exposes a build SHA]** this is **not readable from the
   payload** and must be taken from the deploy record. **If it cannot be
   established, the result says so** rather than assuming the tree and the
   deployment agree — this session began with `main` and live on different
   revisions, so they routinely do not.

---

## Registration record

| | |
|---|---|
| Registered | 2026-08-10 (UTC) |
| Repo state seen at registration | ADR 0019 (Proposed, uncommitted), one added check that cannot fire, and a raise replacing an unreachable default in `runner.py:342`; **no threshold value moved**. Disclosed in §0.7, ruled on in §V. |
| Data seen at registration | **Yes — §0. Three priors disclosed**, including the live-path devig spread (§0.6) that created H3b: the 413-row / 38-game slice and the whole-table 614-row / 59-game pinned pull, each returning 0 positive net edges and max −2.1 tenths. **No deduplicated count, quantile, per-game value or devig-spread distribution has been seen by anyone.** |
| Claims | **5.** H4 (`n_degen == 0`), H2 (`max_game_share <= 0.50`), H3a (`median(S − spread_tenths) > 0`), **H3b (`S_min > spread_at_min` — governs the citable sentence)**, H1 (reproduction, `max E1 <= 0`). Reported in that order. |
| Direction | H1 one-sided; H2 declared on `<= 0.50`; H3a and H3b one-sided; H4 declared on a count of zero, with a paired non-zero control on the suppressed population |
| Interval tests | **0.** No standard error, no p-value, no significance mark anywhere. Census statements only. |
| Multiplicity | **Not spendable by construction** — no cell carries an interval, a standard error, a p-value or a significance mark. The arithmetic avoided: ~90 cells, 4.1 expected false findings, P(≥1) > 0.98 |
| Edge basis | **Recomputed** `edge_after_fees_tenths(ask_tenths, contracts=1, fair_probability, maker=False)`. Stored column is a diagnostic. **Add-back forbidden.** |
| Population | `suppressed_reason IS NULL`, whole pinned table, `ask_tenths ∈ [1, 999]`, `fair_probability` non-NULL |
| Cluster key | ticker minus its final `-`-segment when ≥3 segments |
| Dedup key | `(cluster_key, created_ms, claim)`; representative = **largest `E1`**, ties by lowest `id` |
| Bucket edges | Grid D `[1,172] [173,827] [828,999]` on `ask_tenths` (the deployed fee's own step function, computed from code); Grid B = `validate.BUCKETS` verbatim. Both descriptive. |
| Pull | Pinned: `newest_id` from page 0 as `max_id` on every page; assert `len(ids) == len(set(ids)) == total` |
| Stopping rule | **One pull, one pin, one look.** A second look is a new registration. |
| Result destination | `docs/measurements/<run-date>-clean-shortfall-distribution-result.md`, written either way |
| Assumed inputs | **1** — A1, that MLB/WNBA moneylines have exactly two settling outcomes. Detector registered in §0.6. |
| Verdict | **READY-CONDITIONAL** — condition in §V: void only if a change is **deployed** that can alter `suppressed_reason` on a row the producer can emit. **ADR 0019 is ruled NOT a trigger**; Lane A may commit and deploy. Outstanding ask: **P7**, the pin-test that `inconsistent_consensus_metadata` never fires. |
| Amendments | none |
