# Pre-registration — the joint bound

**Written 2026-08-10.** `tasks/NEXT.md`, *"THE PLAN: one joint bound, then stop
and write the refutation"*. `partner`'s job one.

**Status: registered. PRIMARY is READY and runnable today on the newest-1,000
slice, and REQUIRED to be re-run whole-table before any ADR is written (§P1).
CONFIRMATORY is BLOCKED on a deploy, not on code (§P4).**

> **AMENDMENT 1, 2026-08-10 — read it before reading anything below.**
> Two changes. **(A1)** the δ ladder's top rung sat *below* the devig knob's
> measured reach, so Branch Z could have declared closure at a generosity the
> knob can exceed; a **δ = 16.7** rung is added and Branch Z's threshold moves
> to it. **(A2)** `ALT-2` moves from `N = 10` to **`N = 1`**, because the
> ADR 0017 Correction 1 premise quoted in §C5 — *"the smallest order this
> software can send is 10 contracts"* — was **retired on 2026-08-09 by ADR
> 0017's own Addendum A.2**. Six passages are marked in place with a pointer
> and **none has been deleted**; the amendment is appended at the end of this
> file and it, not the original text, governs.
> **The primary estimand does NOT change: `S` stays primary and `D*` is
> registered as a required derived print, not a replacement** (§A3).
> **The PRIMARY bound is untouched and its headline finding cannot move**, by
> §C3's size-invariance. Only the CONFIRMATORY variant's ALT-2 and Branch M
> are affected by A2.
> **No data had been observed when it was written** (§A0).
> See [Amendment 1](#amendment-1--2026-08-10).

- Owner: `pre-registrar` (agent), on behalf of Joe.
- Scored against by: `measurement-skeptic`, after the run.
- Negative-result destination fixed in §9, before the result exists.
- **Form matched to, and machinery reused from,**
  `docs/measurements/2026-08-10-preregistration-fresh-odds-edge-distribution.md`
  ("**Lane A**", with its Amendment 1) and
  `docs/measurements/2026-08-10-preregistration-devig-method-calibration.md`
  ("**Lane B**"). Where a rule already exists in those documents it is **cited,
  not restated**, so that nothing can be quietly re-chosen here. In particular:
  Lane A §2 (the `instr` freshness predicate), Lane A §4 (the cluster key and
  the HTTP fallback), Lane A §5 Grid B, Lane A §6 (the edge recomputation, the
  forbidden stored column, the forbidden add-back), Lane A §C1 (the exhaustive
  fee-model Δ table), Lane B §C2 (the `p_conservative == min(four)` invariant).

**This document must be committed before any count is produced.** A
pre-registration that lives only in a conversation has not been pre-registered.

---

## §0. What had already been observed when this was written

Same disclosure standard as Lane A §0. This is not a blind registration and
saying otherwise would be false.

### §0.1 Seen — whole-table counters, live, 2026-08-10

**[MEASURED FROM DATA — supplied by Joe, live, this session]**

```
populations   actionable 0     no_edge 614     suppressed 921     total 1535
horizons      "0" 532          "1" 569         unscored 434
gate          actionable 0g/0r   no_edge 20g/279r   suppressed 25g/253r
              29 scored games
ordering      the newest 1,000 rows carry only 169 distinct created_ms values;
              one created_ms is shared by 84 rows; 960 of the 1,000 tie with
              at least one other row
```

`actionable` has been **0 for the entire life of the record** — 1,535 rows.

### §0.2 Seen — earlier reads, same table, earlier instants

1,462 / 1,520 / 1,529 rows, in Lane A §0.1 and Lane B §0. Deltas between them
have not been audited and are not used.

### §0.3 What has NOT been seen, by anyone

**No per-row value of `entry_ask_tenths`, `fair_probability`, `edge_tenths`,
`p_multiplicative`, `p_additive`, `p_power` or `p_shin` has been read, computed,
estimated or inspected by anyone.** No shortfall, no histogram, no quantile, no
minimum. No count of rows inside the 18c–82c band exists — `docs/adr/0017`
Addendum A.4 is explicit that *"nobody has"* counted them. `G` for this
measurement is unknown.

### §0.4 Provenance labels

Every quantity is **[COMPUTED FROM CODE]**, **[MEASURED FROM DATA]** or
**[ASSUMED]**, per Lane A §0.5. Everything in §C, §5 and §F below was produced
by executing repository functions — `devig`, `method_spread`, `fee_candidates`,
`calculate_fee`, `effective_price` — on inputs chosen **here**, and is blind to
the record.

**Assumed inputs in this design: zero.** That is a property of a deterministic
bound and it is the main reason this instrument is worth more than either lane's
interval test. There is no σ, no boundary, no alpha and no `n` at which it stops
working.

---

## §C. Corrections to the brief, made before the design was fixed

Six. Four change the design rather than annotating it.

### C1. The 2.03 traces — but not to what `tasks/lessons.md` says asserts it

`partner` required this be traced rather than inherited. It traces, and the
trace turns up a smaller defect worth recording.

**[COMPUTED FROM CODE — `backend.core.devig.devig(...).method_spread(...)`,
executed here]**

| line (decimal odds) | method spread, points | source of the inputs |
|---|---:|---|
| **1.11 / 7.50** | **2.0304** | `tests/test_devig.py:28` — `HEAVY_FAV, LONGSHOT` |
| **2.10 / 1.80** | **0.1817** | `tests/test_devig.py:129`, `devig.py:10` |
| 1.95 / 1.95 | 0.0000 | `tests/test_devig.py:135` |
| 1.71 / 2.30 | 0.2120 | `tests/test_devig.py:26` — `FAV, DOG` |

So **`suppression.py:217-220`'s comment is reproducible to four figures** from
the repository alone, on inputs named in the test module. It is a real
measurement, not a folk number, and this registration may use it as a named
readout.

**The defect:** `tasks/lessons.md` (2026-08-06) says *"Both halves are asserted
in `TestMethodSpreadDependsOnLineShape` so the framing cannot quietly drift
back."* That class exists (`tests/test_devig.py:107`) and it asserts
`spread > 0.6`, `spread < 0.6` and `lopsided > even` — **three inequalities
against 0.6, and not the values 0.18 or 2.03.** The spread on the lopsided line
could fall to 0.61 points, or rise to 20, with the suite green. The halves are
*bounded*, not asserted. Recorded here rather than silently relied on.

### C2. 2.03 is not an upper bound on anything, and no fixed δ is

The brief calls 2.03 *"the documented maximum reach"*. It is the value on **one
line**, and the spread is **not monotone in lopsidedness** — additive devig
clamps at `_EPS` on extreme lines (`devig.py:127`), which collapses the spread
again:

**[COMPUTED FROM CODE]**

| line | spread, points |
|---|---:|
| 1.30 / 4.00 | 0.735 |
| 1.05 / 15.0 | 1.352 |
| 1.20 / 5.00 | 1.581 |
| **1.11 / 7.50** | **2.030** |
| 1.01 / 60.0 | 0.564 |
| 1.02 / 40.0 | 0.425 |

2.03 is a **local** maximum over the lines anyone has looked at. Nothing in the
repository proves a global one, and a consensus row is not even a single line:
`consensus_devig` averages each method across books *before* the min is taken,
and since `max` of averages ≤ average of `max`, the per-row consensus spread is
weakly **smaller** than the mean per-book spread — a direction, not a bound.

**Registered consequence, and it is the central design decision of this
document:** *the primary artefact is not a count at a chosen δ. It is the
distribution of the shortfall (§6), from which the count at **every** δ is
readable simultaneously.* The δ ladder of §5 is a set of named readouts off that
distribution, fixed in advance, and no δ outside the ladder may be introduced
after the data is read. This removes the δ knob from the analyst's hands
entirely, which is stronger than fixing one value of it and safer than trusting
2.03 to be a maximum it has not been shown to be.

### C3. The stacked generous basis is a **zero fee at every price and every size**

This was not known when the brief was written and it simplifies the primary to
one subtraction.

**[COMPUTED FROM CODE — `fee_candidates(p, N, maker=True)`, exhaustive over all
999 tradeable prices × N ∈ {1, 2, 5, 10, 50, 100, 500, 1000} = 7,992 cases]**
`model_b_per_contract_nearest` returns **0.00 in 7,992 of 7,992 cases.** The
closed form explains it: Model B's maker multiplier is `0.06/4 = 0.015`, and
`0.015 · P(1−P) ≤ 0.015 × 0.25 = 0.00375`, which rounds half-up to **zero
cents per contract at every price.** `_model_b` multiplies that zero by `N`.

Therefore, taking the **cheapest** candidate fee model *and* the maker basis
together — the stack `partner` permits for the dominating bound — the generous
fee is **identically zero**, and:

```
generous effective price  ==  the raw ask, at every price and at every order size
```

Three consequences, all binding:

1. **The primary bound is size-invariant.** It dominates the exact bound at
   `N = 1`, at `N = 10`, and at any `N` the software could ever send. No order
   size can be raised later as a reason the bound was too tight.
2. **The primary bound reduces to `is the loosest fair above the ask?`** — one
   subtraction per row, with the fee removed entirely.
3. **Nobody believes Kalshi charges nothing.** That is exactly what makes a zero
   count strong and exactly why the stacked count **may never be reported as an
   estimate of anything** (§10). It is the bound and only the bound.

### C4. The per-knob savings, exhaustively, before any row is read

**[COMPUTED FROM CODE — `fee_candidates`, all 999 prices, per contract at N=1,
in tenths of a cent, measured against the deployed basis (`calculate_fee` =
max model, taker, N=1)]**

| price band, tenths | fee knob alone | maker knob alone | **stacked** | stacking premium |
|---|---:|---:|---:|---:|
| `[1, 91]` | 10.0 | 0.0 | **10.0** | 0.0 |
| `[92, 172]` | 0.0 | 0.0 | **10.0** | **10.0** |
| `[173, 499]` | 10.0 | 10.0 | **20.0** | **10.0** |
| `[500, 500]` | 0.0 | 10.0 | **20.0** | **10.0** |
| `[501, 827]` | 10.0 | 10.0 | **20.0** | **10.0** |
| `[828, 908]` | 0.0 | 0.0 | **10.0** | **10.0** |
| `[909, 999]` | 10.0 | 0.0 | **10.0** | 0.0 |

The **fee knob** column reproduces Lane A §C1's Δ table on the same seven runs,
edge for edge — an independent recomputation agreeing to the digit, which is why
Lane A's §C2 reachability language is reused rather than re-derived. The
**maker knob** column reproduces `docs/adr/0017` Addendum A's band exactly:
10.0 tenths on the single contiguous run `[173, 827]` and zero outside it.

**The stacking premium is 0 or 10 tenths and never more**, and it is 10 tenths
at 807 of 999 prices. That is the quantitative form of `partner`'s constraint 1:
stacking is worth up to a full cent per contract beyond the best single
alternative, which is safe for a bound and would be a fabrication in a
measurement.

### C5. "1.94 points, 5.1x" is the `N = 100` limit, and it is not the operative figure

> **[SUPERSEDED IN PART by Amendment 1 §A2 — text retained.]** The table below
> is correct and unchanged. The *conclusion* drawn from it — that 1.88 pts /
> 4.9x at `N = 10` is "operative" — rests on a premise ADR 0017 retired in its
> own Addendum A.2 on 2026-08-09. The operative figure is **1.38 pts / 3.6x at
> `N = 1`**. See §A2.

**[COMPUTED FROM CODE — `effective_price(500, N, maker=...)`]** at 50.0c,
against a −110 sportsbook's 52.38%:

| basis | breakeven | headroom vs 52.38% | ratio to the taker's 0.38 |
|---|---:|---:|---:|
| taker, any N | 52.00% | 0.38 pts | 1.0x |
| maker, N=1 | 51.00% | **1.38 pts** | 3.6x |
| maker, N=10 | 50.50% | **1.88 pts** | 4.9x |
| maker, N=100 | 50.44% | **1.94 pts** | 5.1x |

The brief's **1.94 / 5.1x** is the large-order limit. `docs/adr/0017`
Correction 1 already fixed this: *"the smallest order this software can send is
10 contracts, so **1.88 points is the figure, not 1.38**"*. So the operative
maker headroom is **1.88 points, 4.9x** — not 1.94, and not 1.38. The
correction is small and it runs in the unflattering direction, which is why it
is made at registration time where it costs nothing.

### C6. `partner`'s slice-bias ruling is recorded, and it is challenged

The ruling: the newest-1,000 slice is volatility-weighted, therefore
edge-*inflating*, therefore a zero on it is a **stronger** result.

The mechanism is real and it is in the code, not in an argument:
`routes.py`'s own `/api/ledger` docstring says `engine.persist_if_changed`
writes a row *only when the ask or the fair moved*, so rows-per-game tracks
price volatility and the newest slice tilts toward volatile, wide-disagreement
games. **[COMPUTED FROM CODE]** So the direction is argued from the recorder's
write rule, which is better than a hunch.

**It is still not a measurement, and two things cut against it:**

- Recency selects on **time**, not on volatility. The slice is also a bankroll-era
  selection (Lane A §3 — `BANKROLL_DOLLARS` 1000 → 100 on 2026-08-09), a
  suppression-mix selection, and possibly a league-mix selection. None of those
  has a signed direction, and the repo has a scar exactly here: a frame filled
  entirely from one stratum whose interval was transferred to a population that
  was 66% the other.
- A ceiling argument that is right in direction can still be wrong in
  magnitude, and the artefact this document is for — *"one could not have been
  found here"* — is a **universal** claim. A universal claim proved on 1,000 of
  1,535 rows is not proved.

**Registered consequence, and this is a challenge to the ruling, not an
annotation of it:** the slice run is a **provisional read**, labelled as such in
its own output, and **§7's D-gate forbids writing the refutation ADR on it.**
The whole-table pull is cheap — `offset` and `max_id` are already in
`routes.py` at HEAD — so there is no reason to spend the strongest artefact this
project can produce on 65% of the rows.

---

## §P. Prerequisites — checked before each variant is permitted to run

Each is a yes/no. A NO stops that variant; this file is amended rather than
worked around.

- **P1 — whole-table coverage, for the ADR.** `/api/ledger` caps at
  `limit <= 1000` **[COMPUTED FROM CODE]** against 1,535 rows **[MEASURED]**.
  The PRIMARY **may** run on the newest-1,000 slice today, prefixed
  `NEWEST-1,000 SLICE — PROVISIONAL — NOT A PROPERTY OF THE TABLE`. It **may
  not** be quoted as a property of the record, and per §7's D-gate no ADR is
  written from it.
- **P2 — the paged pull is a total order and a pinned snapshot.** Required for
  every whole-table run, primary or confirmatory. The pull **must** send
  `max_id` read from page 0 on every subsequent page, and the route **must**
  order by `(created_ms DESC, id DESC)`. **[MEASURED, Joe, 2026-08-10]** the
  newest 1,000 rows carry only **169 distinct `created_ms`**, one value carries
  **84 rows**, and **960 of 1,000 tie** — so `created_ms DESC` alone is not a
  total order and an unpinned pull returns a different multiset from the table
  while `total`, `returned` and the page sizes all still add up. **[COMPUTED
  FROM CODE — `routes.py` `/api/ledger` at HEAD]** both are implemented; the
  prerequisite is that the **deploy carrying them has landed** and that the
  runner actually passes `max_id`. **Verification, mandatory and printed:**
  the pull is complete only when `offset + returned == total` under the pin,
  **and** `len(set(ids)) == total`. A pull failing either is discarded, not
  patched.
- **P3 — `entry_ask_tenths ∈ [10, 989]` and `fair_probability` non-NULL** on
  every analysed row. Rows outside are excluded and **counted** (§2). Reuses
  Lane A P3/P4 verbatim, including the reason: `effective_price` raises rather
  than pricing an untradeable ask at a zero fee.
- **P4 — CONFIRMATORY ONLY: the four devig methods are on the live payload.**
  **[COMPUTED FROM CODE]** `routes.py` at HEAD already `LEFT JOIN`s
  `fair_prices` and returns `p_multiplicative`, `p_additive`, `p_power`,
  `p_shin`, `p_conservative`. So the devig knob is blocked on a **deploy**, not
  on a code change. `partner`'s reading — a bare `SELECT *` with no join — was
  true of the deployed build and is no longer true of HEAD; recorded because
  the brief will be read again.
- **P5 — CONFIRMATORY ONLY: Lane B §C2's invariant holds on every joined row:**
  `p_conservative == min(p_multiplicative, p_additive, p_power, p_shin)` **and**
  `fair_probability == p_conservative`. Both are equalities the code should make
  necessary. If either fails anywhere, the join is wrong, the design is void,
  and no statistic is computed. Rows with any NULL among the four are **dropped
  and counted, never imputed** (`p_shin` may be NULL where the root-finder fell
  back — `devig.py:181`).

---

## §1. The question, as a claim that could be false

**Primary claim, one-sided, deterministic:**

> Over the registered population, the number of rows whose **ask** sits below
> the **most generous fair probability the project's own machinery can
> produce** — the loosest of the four devig readings, under the cheapest fee
> model, on the maker basis — is **zero**.

Written as a claim that can come back false: the estimand is `K(δ)`, the count
of bound-clearing rows at devig allowance `δ`, and the registered claim is
`K(δ) = 0` for every `δ` on the §5 ladder. `K(δ) ≥ 1` at any `δ` on the ladder
is a live outcome, is not a failure of the measurement, and is the outcome that
keeps the project alive.

**Direction, stated so it cannot be flipped afterwards:** the test is one-sided
in the *generous* direction. Every substitution moves the row toward
actionability. A bound that returned "fewer rows are actionable than we thought"
would be reporting an arithmetic error, not a finding.

**Why this is a bound and not an estimate.** `K(δ)` has no sampling
distribution. It is a statement about prices already written to disk: if on
every recorded row the ask sits above the loosest fair at a zero fee, then no
devig choice, no fee-model resolution, no maker/taker choice and no further
sample **of the same kind** could have produced an actionable row **among those
rows**. The quantifier "of the same kind" is load-bearing and is discharged in
§10.

**Two subordinate questions, registered here, neither able to substitute for the
primary:**

- **R2 — the shortfall.** How far short is the record? The full distribution of
  `S` (§6), and specifically the nearest row and the nearest game. *"0 rows, and
  the nearest row is 11c short"* is a far stronger artefact than *"0 rows"*, and
  it is the difference between a closed question and a near miss.
- **R3 — the maker line, which rides free.** Is there mass in the exact
  `[173, 827]` tenths band where the maker basis is worth a full cent at `N=1`,
  and does the **maker knob alone** (no stacking) clear any row there? This is
  the only quantity in the project where a positive finding is not
  power-precluded on its face, and it costs nothing extra.

---

## §2. The population, and the exclusions — fixed now, because it is the real degree of freedom

`partner` is right that this is where the answer would be chosen. **The count
moves a lot with it, and the flattering direction runs both ways:** `tasks/NEXT.md`
and `start.md` both frame 0 as the expected result, which makes **non-zero** the
finding that keeps the project alive, and 0 the finding that lets the plan
close on schedule. Both outcomes have a constituency, so the choice is made here
and the ladder is nested and reported in full.

### The four populations, nested, all reported, PRIMARY is the widest

| | population | predicate | standing |
|---|---|---|---|
| **P0** | **ALL rows** | `entry_ask_tenths BETWEEN 10 AND 989` **AND** `fair_probability IS NOT NULL` | **PRIMARY.** The decision rule of §7 is keyed to this and only this. |
| P1 | unsuppressed | P0 **AND** `suppressed_reason IS NULL` | Reported. |
| P2 | fresh odds | P0 **AND** Lane A §2's predicate | Reported. |
| P3 | fresh and unsuppressed | P1 **AND** P2 | Reported. |

**P0 is the primary because a bound is strongest over the widest population.**
Restricting to fresh or unsuppressed rows would answer a narrower question and
would be a choice made in the direction of a smaller count. The nesting
`P3 ⊆ P1, P2 ⊆ P0` is asserted as an invariant before any count is printed;
`K` is monotone non-increasing along it, and a violation voids the run.

**No horizon filter, and no CLV requirement.** The bound needs no outcome. Every
row carries an ask and a fair at creation time. Horizon and scoring status are
**strata** (§S2), never filters — restricting to the 29 scored games would
discard 98% of the record for no gain and would import ADR 0011's horizon
mixture into a question that does not have one.

### The freshness predicate, where P2 uses it

```sql
AND (r.suppressed_reason IS NULL
     OR instr(',' || r.suppressed_reason || ',', ',stale_odds,') = 0)
```

**`instr`, not `LIKE`** — this is **defect D1** of Amendment 1 to the CLV
registration, and it is reused verbatim from Lane A §2 rather than restated, so
it cannot be re-derived wrong. Two reasons, both live: SQLite `LIKE` reads `_`
as a single-character wildcard and **all fourteen** suppression codes contain
underscores; and `suppressed_reason` is a **comma-joined composite** of every
failing check, so `NOT IN ('stale_odds')` retains every composite row —
**[MEASURED, Lane A §0.1]** 27.8% of stale rows are composites.

Applied in Python instead of SQL, the predicate is
`"stale_odds" not in (row["suppressed_reason"] or "").split(",")` — exact token
match on the split, no wildcard surface. **These are the only two permitted
forms.**

### Excluded from every population, with the reason independent of the outcome

| Excluded | Why | Independent of the bound? |
|---|---|---|
| `entry_ask_tenths` outside `[10, 989]` | 0 and 1000 are settled outcomes, not quotes. `is_valid_price` rejects them and `effective_price` **raises** rather than pricing at a zero fee — which would fabricate an edge of +55c out of nothing. | Yes — a property of the stored price alone, evaluated before any fair is read. |
| `fair_probability IS NULL` | `NOT NULL` in `schema.sql:365` **[COMPUTED FROM CODE]**, so this should never fire. If it fires the row is **dropped and counted**, never imputed. | Yes. |
| CONFIRMATORY only: any NULL among the four `p_*` | A missing method is a real state (`devig.py:181`), and `max` over three methods is a different estimator from `max` over four. | Yes — a property of the join, not of the shortfall. |

**No exclusion in this document references `clv_tenths`, `settled_win`, the
stored `edge_tenths`, `suppressed_reason` (outside the explicitly-labelled P1/P2/P3
strata), or any outcome.** Every one is decidable from the row's own inputs.

### The rule that must not be activated after the fact

If P0's count comes back non-zero and the clearing rows turn out to be
suppressed, **narrowing the primary to P1 or P3 after seeing that is
forbidden.** All four counts are printed together, from one pass, and the
decision rule reads P0. The precedent is in this repo: a combo experiment
pre-registered an exclusion and the agent correctly **refused to activate it**
when the sample turned out thin. That refusal was only possible because the rule
was in writing first.

---

## §3. The unit of observation

**The unit for every count is the row; the unit for every reported rate and for
`G` is the game.** Both are printed side by side, always, everywhere — Lane A
§4's rule, reused. *"412 of 300"* on one screen beside *"9 of 300"* on another
is how the flattering number gets believed, and this repo shipped a gate that
counted 400 rows on one ticker as 400 observations.

**The clustering variable is
`COALESCE(kalshi_markets.event_ticker, recommendations.ticker)`** — Lane A §4
verbatim, the same key `gate.clustered_clv` uses, reused so it cannot be
re-chosen. Over HTTP only `ticker` is available and the **fallback key is Lane A
§4's**: split on `-`; if there are three or more segments drop the last;
otherwise use the string unchanged. No fixed character count is chopped — that
was the previous project's bug, which inflated `G` in the flattering direction.

Lane A §4's two registered defects carry over unchanged and are **printed, not
corrected**: the event ticker carries the series prefix, so spread and total rows
on one game would become up to three clusters; and the fallback cannot see a
market whose stored `event_ticker` differs from its ticker prefix.

**A note that matters more here than in Lane A.** For a bound, clustering is
**not** an inference device — there is no standard error to inflate. `G` is
reported for two specific and limited purposes: the rule-of-three rate bound of
the power check, and so that a non-zero `K` cannot be reported as "12 rows"
when it is one game. Nothing in §7's decision rule depends on `G`, deliberately,
so that a mis-keyed cluster cannot change the verdict.

---

## §4. The two variants, and why the primary dominates

### PRIMARY — the dominating bound. Computable today, and no deploy can change it.

The devig knob is not available per-row on the deployed build (§P4). Rather than
wait, substitute the knob's **reach** for its per-row value:

```
generous_fair(row, δ)  =  fair_probability  +  δ/100          (δ in points)
generous_price(row)    =  entry_ask_tenths / 1000            (fee = 0, per §C3)
```

evaluated across the whole δ ladder of §5 at once, via the shortfall
distribution of §6.

### CONFIRMATORY — the exact bound. After the deploy.

```
generous_fair(row)  =  max(p_multiplicative, p_additive, p_power, p_shin)
generous_price(row) =  the best SINGLE alternative, never the stack (§5)
```

### The domination argument, stated explicitly and with its validity condition

**Claim.** If the primary returns `K = 0` at a given δ, the exact bound returns
`K = 0` on every row whose true per-row method spread is ≤ δ.

**Why it holds.** `edge_after_fees_tenths` is
`(fair_probability − effective_price(ask, N, maker)) × 1000`. It is **monotone
strictly increasing in `fair_probability`, holding ask, size and fee basis
fixed**, and **monotone strictly decreasing in the fee**, holding fair and ask
fixed. Both are visible in the one expression at `core/ev.py:179-180` — no
saturation, no clamp, no rounding on the fair side. Therefore:

1. `max(p_mult, p_add, p_power, p_shin) = fair_probability + spread(row)`
   exactly, because `fair_probability == p_conservative == min(four)`
   (Lane B §C2, asserted as P5). So substituting `fair + δ` dominates the exact
   generous fair **iff `spread(row) ≤ δ`**.
2. The stacked generous fee is **identically zero** (§C3), which is ≤ every fee
   under every candidate model, every basis and every order size. So the primary
   dominates the exact bound's price side **unconditionally**, at every `N`.
3. Monotonicity in each argument separately gives the joint domination.

**The validity condition is 1, and it is not free.** Per §C2, no δ is proved to
bound `spread(row)`. This is discharged, not waved away, in three ways:

- The **δ = 5.0 readout** is deliberately absurd — 2.5x the largest spread
  anyone in this repo has produced from a real line, and larger than the entire
  method spread on every line in §C2's table.
- The **shortfall distribution** (§6) makes the domination checkable rather than
  assumed: the exact bound's clearing set at any spread `s` is contained in
  `{S < 10s}`, and that set's size is printed for the whole range of `s`, not
  just at the ladder points.
- The **confirmatory run settles it exactly**, and §7 requires it before the
  claim is stated in universal form.

**What the primary establishes on its own, and it is a lot:** a zero at δ = 5.0
says no row in the population could have been made actionable by any devig
reading within 5 percentage points of the conservative one, **at a fee of
zero**, **at any order size**. That is a statement no deploy, no fee
calibration, and no maker/taker decision can reverse.

---

## §5. The cut — every edge fixed in advance

Bucket boundaries are the richest source of unearned findings because there are
many defensible ones and they can be tried in sequence. Everything below is
fixed here and nothing may be re-cut after the data is read.

### The δ ladder — five named readouts, and no sixth

> **[AMENDED by Amendment 1 §A1 — text retained.]** A **sixth** rung is added
> at **δ = 16.7 points**, the largest devig-method spread produced anywhere in
> the swept two-outcome line space. The five below are unchanged and none moves.
> The heading's "and no sixth" is the clause the amendment overturns, and the
> reason is that the ladder as registered topped out **below** the knob it was
> built to bound. See §A1.

| δ, points | δ, tenths | what it is |
|---:|---:|---|
| **0.00** | 0.0 | no devig allowance at all — pure "ask vs conservative fair at zero fee" |
| **0.18** | 1.8 | the measured even-moneyline spread (§C1) — the typical slate |
| **2.03** | 20.3 | the measured lopsided-line spread (§C1) — the longshot end |
| **5.00** | 50.0 | **deliberately absurd**, per `partner`. 2.5x anything measured |
| **10.00** | 100.0 | a sanity rung, so that `K = 0` at 5.0 can be read against a δ where `K` is certainly non-zero if the arithmetic works at all |

The 10.00 rung exists for a specific reason from `tasks/lessons.md`: *a control
must be able to reach the confound it was built for.* A ladder on which `K = 0`
everywhere is indistinguishable from a harness that returns zero because it is
broken. **Registered: if `K(10.00) = 0` on P0, the run is treated as a suspected
harness defect and is not reported as a finding until the harness is shown to
return non-zero on a constructed row.**

### The shortfall histogram grid — eight cells, fixed here

Edges in tenths of a cent, on `S` (§6), left-open right-closed:

```
(-inf, 0]   (0, 10]   (10, 20.3]   (20.3, 50]   (50, 100]   (100, 200]
(200, 400]  (400, +inf)
```

Three of those edges are the δ ladder in tenths, so the histogram and the ladder
are the same partition read two ways and cannot disagree.

### Grid B — `analysis.validate.BUCKETS`, verbatim

`(10,100) (100,200) (200,300) (300,400) (400,500) (500,600) (600,700) (700,800)
(800,900) (900,990)` — reused rather than restated so it cannot be re-chosen.
**Bucketing is on `entry_ask_tenths`, the derived ask, the price actually paid,
never a mid.** A bucket in the predecessor project showed a +25.4 point edge and
lost money for exactly this reason. **Descriptive only, at any `n`.**

### The maker band — the exact edges, not the rounded ones

`[173, 827]` tenths, **not** the "18c–82c" of `docs/adr/0017` §1. **[COMPUTED
FROM CODE — §C4, exhaustive over 999 prices]** the `N=1` maker saving is 10.0
tenths on exactly that contiguous run and 0.0 outside it, and ADR 0017 Addendum
A records that §1 rounded inward by 0.7c on each side. The rounded band would
mislabel 14 prices.

### The exact bound's alternatives — three, fixed, and no stack

`partner`'s constraint 1: **stacking is permitted for the dominating bound and
FORBIDDEN for the exact one.** The cheaper-fee saving and the maker saving are
*alternatives*, not additions.

| | basis | `N` | why this `N` |
|---|---|---:|---|
| **ALT-0** | deployed: max fee model, taker | 1 | the baseline. Lane A §6's basis, reused so the two documents are commensurable |
| **ALT-1** | cheapest candidate fee model, taker | 1 | Lane A §6's `E1min`, reused. `E1min − E1 == Δ(price)` from §C4 is an **assertable invariant**, not a hope |
| **ALT-2** | max fee model (`calculate_fee`), maker | **10** | ADR 0017 Correction 1: *the smallest order this software can send is 10 contracts*. `N=1` maker is not a realisable state |

> **[SUPERSEDED by Amendment 1 §A2 — row retained.]** **ALT-2 is `N = 1`.**
> The justification above is false as of 2026-08-09: `min_order_contracts` was
> retired, `sizing.py:156` prices unconditionally at `contracts=1`, and `N = 1`
> maker is therefore the realisable state rather than the excluded one. `N = 10`
> becomes the labelled non-decision-bearing secondary — the exact inverse of
> what this row says. See §A2.

The exact bound clears a row iff it clears under **ALT-1 or ALT-2 individually**
— a union of realisable states, never their combination. **[COMPUTED FROM
CODE]** the stacked reading would be worth up to a further 10.0 tenths per
contract beyond the better alternative (§C4), and reporting that as the exact
bound would be a fabrication of exactly that size.

**`N` is not swept.** A swept `N` is a knob, and the savings under a sweep are a
sawtooth reaching 17.4 tenths at `N=100` **[COMPUTED FROM CODE]** — choosing a
partition after learning the shape of the fee curve is choosing a cut with
knowledge of the data-generating process, which Lane A §5 already forbids. The
size question is closed by the **primary**, whose zero fee dominates every `N`
(§C3), and it does not need re-opening here. `N=1` maker is printed as a
labelled non-decision-bearing secondary so that ADR 0017's `N=1` band remains
readable.

### No other cut

Not by side, not by league, not by day, not by time to kickoff, not by depth,
not by book count, not by a re-derivation of any grid at a different size. Each
of those is defensible and that is the problem.

---

## §6. The statistic, named as an estimator

### The edge is RECOMPUTED. The stored column is not used.

Lane A §6, reused in full and not restated: `schema.sql:375-383` says
`edge_tenths` is *"a per-contract edge at ONE specific size, which the column
does not carry"*; the divisor is not recoverable from the row; Amendment 1 §A5.1
measured the resulting steps at up to 5.0 tenths, price-dependent and
non-monotonic. **The stored `edge_tenths` enters no quantity in §7. The
`edge_tenths + fee_predicted` add-back is forbidden.** Both are selected in §S1
only so their divergence can be printed as a diagnostic, and the SQL alias says
so.

Every edge is recomputed per row through
`core.ev.edge_after_fees_tenths(ask_tenths=…, contracts=…, fair_probability=…,
maker=…)`, with the fee model substituted where an alternative requires it.

### The shortfall `S` — the primary artefact, named as what it is

**`S` is not an estimator. It is a deterministic per-row quantity with no
sampling distribution, in tenths of a cent per contract.**

```
PRIMARY:        S = entry_ask_tenths − 1000 × fair_probability
CONFIRMATORY:   S_k = 1000 × effective_price(ask, N_k, maker_k, model_k)
                      − 1000 × max(p_mult, p_add, p_power, p_shin)
```

Positive `S` means the row is **short** by that many tenths. The primary's `S`
has the zero fee already in it, per §C3, which is why it is one subtraction.

**The identity that makes the ladder free:**

```
row clears the primary bound at δ points   ⟺   S < 10δ
K(δ) = #{ rows : S < 10δ }
```

So `K(δ)` for **every** δ is a readout of one distribution. **This is why no δ
needs to be chosen and why the δ knob does not exist for the analyst.**

### The estimators actually reported, said out loud

Each has a different null and they are not interchangeable.

| Quantity | What it is | Null | Standing |
|---|---|---|---|
| `K(δ)` | **a count over a census** — zero sampling error | none; it is a census | **PRIMARY.** Decision-bearing by a deterministic rule. Carries **no alpha**. |
| `S` distribution | **a distribution over a census** | none | **PRIMARY artefact (R2).** Descriptive but decisive. |
| `G_K(δ)` | **a count of clusters** containing ≥1 clearing row | none | Reported beside every `K`. |
| rule-of-three rate bound | **an upper confidence bound on a per-game rate** in a wider universe | rate = 0 | The **only** inferential quantity in this document. Power check. |

**`sqrt(p(1−p)/n)` is correct for none of these and must not appear anywhere in
the output.** There is no `p`, there is no sample, and the trap it comes from is
the row count: `n_rows` is uptime, `n_clusters` is evidence.

### The printed form of the shortfall — fixed here, per `partner`'s constraint 3

Because *"0 rows, and the nearest row is 11c short"* is a far stronger artefact
than *"0 rows"*, the shortfall block is **required output**, in this order and
this shape:

```
JOINT BOUND — <PRIMARY dominating, stacked, fee=0 | CONFIRMATORY exact, ALT-k>
population <P0|P1|P2|P3>     rows N = ____    clusters G = ____

  K(δ=0.00 pts)  = ____ rows / ____ games
  K(δ=0.18 pts)  = ____ rows / ____ games
  K(δ=2.03 pts)  = ____ rows / ____ games
  K(δ=5.00 pts)  = ____ rows / ____ games
  K(δ=10.00 pts) = ____ rows / ____ games      [reachability rung — see §5]

  NEAREST ROW      S = +____._ tenths = ____.__ c short
                   ticker ____  side ___  ask ____  fair ______  created_ms ____
                   cluster ____   suppressed_reason ____
  NEAREST GAME     best row in its cluster: S = +____._ tenths = ____.__ c short
                   cluster ____   rows in cluster ____

  S over rows      min ____  p1 ____  p5 ____  p10 ____  p25 ____
                   p50 ____  p75 ____  p90 ____  max ____
  S per-cluster    minimum per cluster, then: min ____  p10 ____  p50 ____
                   p90 ____  max ____
  histogram        (-inf,0] ____  (0,10] ____  (10,20.3] ____  (20.3,50] ____
                   (50,100] ____  (100,200] ____  (200,400] ____  (400,inf) ____
```

**The headline sentence is fixed here too, so it cannot be re-worded to suit the
number:**

> *`K` rows of `N` clear the joint bound. The nearest row is `X.XX`c short of a
> fee-free ask at the loosest devig reading available to this project; the
> nearest game's best row is `Y.YY`c short.*

**Both halves are mandatory.** A run reporting `K` without the shortfall is
incomplete and may not be cited.

---

## §7. The decision rule, with the multiplicity already counted

### How many tests carry alpha: zero

| Family | Cells | Standing |
|---|---:|---|
| `K(δ)` over the five-rung ladder × four populations × two variants | 40 | **Deterministic censuses. No alpha.** |
| Shortfall histogram | 8 × 4 populations | Descriptive |
| Grid B cross-tab | 10 | Descriptive |
| Maker band (R3) | 4 | Descriptive |
| Strata prints (horizon, era, series prefix, config version) | printed | Descriptive |
| **Interval tests** | **0** | — |

**The project-wide interval-test count therefore stays at 3** — Lane A's `M`,
Lane B's `B1` and pooled `B3` — at `alpha = 0.05 / 3 = 0.0167` each, per Lane A
Amendment 1 §A1. **This document adds nothing to that budget and requires no
amendment to either lane.** That is the specific reason `partner` chose this
instrument over another interval test: against a project-wide
P(at least one descriptive cell clears from nothing) = **0.9993** (Lane A §A2),
an instrument that spends no alpha is worth more than one that spends a third of
what remains.

**What a zero-alpha instrument does *not* buy.** It does not license
pattern-reading across the 40 cells. `K` is monotone in δ and in the population
nesting **by construction**, so cells are not independent and a "pattern" across
them is arithmetic, not evidence. **No cell in this document may be declared a
finding.** The only claims permitted are the branch declarations below.

### The multiplicity that does still bite

`K(δ)` has no sampling error, but the **claim** it supports — *"no row could
have been actionable"* — is scoped to the rows examined, and the record grows.
Registered, so this is not rediscovered later:

- Every result is stated with an explicit scope: *"over the `N` rows of
  population P0 with `id <= max_id`, snapshotted `<UTC timestamp>`."*
- A re-run over a grown record is a **new artefact with its own dated result
  file**, not an update to the old one. It extends the scope; it does not
  re-test a hypothesis.
- Because `K = 0` can only be overturned by rows that did not exist when it was
  computed, and never by re-analysis of the same rows, **no always-valid
  boundary is required and none is used.** This is the one place in the project
  where repeated looks are genuinely free, and the reason is that the quantity
  is a census rather than an estimate.

### The decision rule, verbatim

> Let `K(δ)` be the number of rows in population **P0** clearing the bound at
> devig allowance δ, `G_K(δ)` the number of distinct clusters those rows fall
> in, and `S` the shortfall of §6. All four populations, all five δ rungs, both
> variants and the full shortfall block are computed and reported at every run.
> **The decision reads P0 and only P0.**
>
> **PRECONDITION — REACHABILITY.** If `K(10.00) = 0` on P0, the harness is
> treated as **suspected defective** and **no branch is declared**, until the
> harness is shown to return `K ≥ 1` on a constructed row whose ask sits one
> tenth below its fair. A bound that returns zero at every rung is
> indistinguishable from a bound that returns zero always.
>
> **PRECONDITION — COVERAGE (the D-gate).** A branch may be **declared** only
> from a run satisfying §P1 and §P2: the whole table, pinned by `max_id`, with
> `offset + returned == total` and `len(set(ids)) == total` both printed and
> both true. A newest-1,000 slice run is reported in full and labelled
> `PROVISIONAL`, and **no ADR, no CLAUDE.md edit and no line closure may be
> written from it.**
>
> **BRANCH Z — CLOSED.**
> Declared if and only if `K(δ) = 0` for **every** δ on the §5 ladder,
> on population P0, on a run satisfying both preconditions.
>
> **[AMENDED by Amendment 1 §A1 — text retained.]** The §5 ladder now carries a
> sixth rung at **δ = 16.7 points**, so this clause binds at 16.7 rather than
> at 10.0, and a new intermediate verdict **Z-NARROW** occupies
> `3.5 < min(S)/10 ≤ 16.7`. As registered, Branch Z could have been declared on
> a record whose nearest row was 12 points short — inside the knob's reach.
> See §A1.
> The finding is then written in these words and no broader ones: **"Kalshi is
> not mispriced relative to a consensus it may itself lead."** The sentence
> *"no edge exists at Kalshi"* is **forbidden** (§10).
> Branch Z is declared from the PRIMARY alone. The CONFIRMATORY run, when the
> deploy lands, is reported and can only **strengthen** it — the exact bound is
> tighter than the dominating one — and if the confirmatory contradicts the
> primary, the arithmetic is wrong and both are withdrawn.
>
> **BRANCH N — NOT CLOSED.**
> Declared if and only if `K(δ) ≥ 1` for some δ on the ladder, on P0.
> The declaration **must** state the smallest such δ, `K` and `G_K` at that δ,
> and the per-population counts `K` on P0/P1/P2/P3 so that a reader can see
> immediately whether the clearing rows are suppressed, stale, or both.
> **Branch N authorises per-knob decomposition and nothing else.** It does not
> authorise a trade, a sizing change, a strategy, a backfill, a new route, or a
> claim of edge. Per `partner`: *decompose per knob only conditional on a
> non-zero count.*
>
> **BRANCH M — THE MAKER LINE (R3), reported in every run regardless of Z or N.**
> Reported: the row and cluster count with `entry_ask_tenths` in the exact band
> `[173, 827]`; the shortfall block restricted to that band; and `K` under
> **ALT-2 alone** (maker basis, max fee model, `N=10`, no stacking, real
> per-row `p_max` in the confirmatory / `fair + δ` in the primary).
> **[SUPERSEDED by Amendment 1 §A2 — text retained: `N=1`, not `N=10`.
> `N=10` overstates the maker saving by 0.5 points at 50c, which is the
> flattering direction for this branch specifically.]**
> **Named** if and only if the band contains at least **5 clusters** — the
> repo's `MIN_EXPECTED_PER_SIDE` rule, read before the effect size — **and**
> ALT-2 alone clears at least one row that ALT-0 does not.
> Fewer than 5 clusters in the band: **the line closes with everything else**,
> and the write-up says so in those words.
> **What being named authorises, fixed here and exhaustively:** a **cancel
> path** and the **free markout harness**. **Not a strategy, not a maker order,
> not a sizing change.** `docs/adr/0017`'s counterargument stands unmodified:
> 1.50c of adverse selection erases the whole maker advantage, that is one and a
> half ticks on a venue quoting to ~2c, and **no fee arithmetic in this document
> addresses fill probability at all.**
>
> **Branches Z and N are exhaustive and mutually exclusive. Branch M is
> independent of both and may be named alongside either. No histogram cell, no
> Grid B bucket, no stratum and no population other than P0 may substitute for
> a branch statistic.**

---

## §8. The stopping rule

**Data collection has already ended for this instrument, and that is a property
of the instrument rather than a decision.** The bound is a census of rows
already written, not an accumulation.

The registered schedule, fixed here:

1. **PRIMARY, provisional run** — the newest-1,000 slice, today, labelled per
   §P1. Runs once.
2. **PRIMARY, whole-table run** — on the first day §P2's pinned paged pull is
   available on live. Runs once. **This is the run the decision rule reads.**
3. **CONFIRMATORY, whole-table run** — on the first day §P4's deploy has landed.
   Runs once. Reported whether or not Branch Z was already declared.

**No further looks are scheduled and none are needed.** A re-run over a grown
record is permitted at any time and is a **new artefact** with its own dated
result file (§7), never an amendment to an existing one.

**What is forbidden** is changing anything in §§1–7 after any run. If the design
must change, the amendment is written into this file with its date and reason
**before** the next run, and the pre-amendment result is reported alongside. **An
amendment made after a run and not recorded voids the registration.**

**A config bump is not a new sequence here**, unlike in Lane A: the bound makes
no i.i.d. assumption. But `strategy_config_version` is still printed, because
more than one value means the record is a mixture and a reader must know that
before quoting `N`.

---

## §9. What would falsify this, and what happens then

**Branch Z is falsified by a single row.** `K(δ) ≥ 1` at any δ on the ladder, on
P0, on a run meeting the D-gate. That is the entire falsification condition and
it is as sharp as this project gets.

**Branch M is falsified by** fewer than 5 clusters in `[173, 827]`, or by ALT-2
clearing no row that ALT-0 does not.

### The result's destination, fixed now, before the result exists

```
docs/measurements/<run-date>-joint-bound-result.md
```

One file, **written whichever way it comes out**, with that exact filename stem,
this document linked from its first line, and §6's headline sentence as its
first paragraph. Only the date varies. The provisional slice run and the
whole-table run go in the same file, as two labelled sections, so that a reader
cannot pick up the provisional number without the D-gate label attached to it.

If Branch Z is declared, the refutation ADR is:

```
docs/adr/0019-the-joint-bound-closes-the-consensus-only-question.md
```

**[COMPUTED FROM CODE — `ls docs/adr/`]** 0018 is taken
(`0018-arming-real-trading-is-a-code-change.md`), so 0019 is the next free
number and it is reserved here so two lanes cannot claim it.

### Consequences, in both directions

| Verdict | What is built | What is killed |
|---|---|---|
| **Z declared** | The refutation ADR 0019. CLAUDE.md's premise section is corrected from *"this tool exists to find out whether an edge is there"* to what it found. The record becomes the portfolio artefact. The recorder keeps running **because it costs nothing**, with no work planned against it and no promise attached. | The consensus-only line, at every knob setting. Lane A's branches A and B (a bound of zero dominates both). Lane B's B2. ADR 0016's backfill, permanently — no sample of the same kind can reverse a bound. Every accumulation-justified line in `tasks/NEXT.md`. |
| **N declared** | **Per-knob decomposition, and nothing else.** Which knob moved which rows, on which populations, at the smallest clearing δ. | The plan to stop. `tasks/NEXT.md`'s *"then stop"* section is withdrawn and re-planned, and this document is cited as the reason. |
| **M named** | A **cancel path** and the **free markout harness**. Both are already scoped in ADR 0017 and neither costs a dollar or a credit. | Nothing. Explicitly **not** authorised: a maker strategy, a maker order, a sizing change, a bankroll change. |
| **M not named** | Nothing. | The maker line, which is the last line in the project where a positive finding was not power-precluded on its face. The write-up says that in those words. |
| **Preconditions unmet** | Nothing. The failing precondition is reported by name. | Nothing yet. `UNRESOLVED` is a real answer. |

**This is decision-relevant in every branch.** Z closes the project's central
question and authorises a specific set of deletions; N re-opens the plan; M
authorises exactly two cheap artefacts and nothing more. **There is no branch
where the answer is "we proceed either way."**

---

## §10. What this measurement cannot establish — drafted before the run

Caveats written afterwards are selected to be survivable. These are written now,
and the list deliberately includes the ones that could overturn the result.

- **`partner`'s specific requirement, and the most important line in this
  document.** If the bound returns 0, the honest finding is **"Kalshi is not
  mispriced relative to a consensus it may itself lead."** It is **NOT** *"no
  edge exists at Kalshi."* `tasks/lessons.md` already suspects Kalshi is the
  sharp side, in which case "Kalshi versus devigged sportsbook consensus" is
  close to empty **by construction** — the comparison would be Kalshi against a
  lagging shadow of itself, and finding nothing there is a fact about the
  instrument's geometry, not about the venue. Writing the broader sentence would
  be the same overclaim, in the opposite direction, as the three this project has
  already caught. **Any write-up containing the broader sentence is defective and
  must be corrected.**
- **The four devig methods and the two fee models are the whole space this bound
  covers, and that space is small.** A *different* fair-value source — a power
  rating, a market-implied model, a fifth devig method, a book this project does
  not subscribe to — is outside it entirely. The bound says nothing about them,
  and CLAUDE.md is explicit that blending a model probability into
  `fair_probability` would be a new decision needing its own ADR.
- **The fee model is secondary-sourced and unverified, and this project has zero
  fills ever.** `core/fees.py`'s own docstring says so. The primary sidesteps
  this by using a zero fee — which no fee model can undercut — so the primary is
  robust to both models being wrong. **The confirmatory is not**, and its ALT-1
  and ALT-2 both move if Kalshi's real schedule differs from both candidates.
  Four real fills resolve this and nothing else does.
- **A zero fee is not a realisable state.** The primary's generous basis
  (§C3) charges nothing, at every price and every size. Nobody believes that.
  It is what makes a zero count strong and it is why the primary's `K` **may
  never be quoted as an estimate of how many rows would be actionable** under
  any real conditions.
- **`S` is the engine's own claim about a market, recomputed.** A distribution of
  claims is not evidence the claims are correct. Whether `fair_probability` is
  calibrated is a different question, is Lane B's, and is **UNDERPOWERED by four
  orders of magnitude** there.
- **The bound is scoped to the rows examined, and the record is 29 scored games
  and one August slate.** It says nothing about NBA, NCAAF, NFL regular season,
  in-play, or combos (`KXMVE`, ADR 0012). The rate bound in the power check is
  the only statement it makes about a wider universe and it is weak.
- **The record contains only the markets the recorder chose to look at.** The
  bound covers `recommendations`, which is downstream of discovery, sport scope,
  the sweep schedule (ADR 0014) and `persist_if_changed`'s write rule. A market
  never polled contributes no row and therefore cannot clear the bound. **This is
  the single most likely way the result is overturned** and it is stated first
  among the overturning caveats deliberately.
- **`persist_if_changed` writes only on movement**, so the population is
  movement-weighted and is not a time-uniform sample of quoted prices. §C6
  argues the direction inflates apparent edge; that argument is unmeasured.
- **`G` may be inflated** by the event-ticker key if spread or total rows ever
  enter the record (§3, Lane A §4 defect 1). Nothing in §7 depends on `G`,
  which is why this is a print rather than a correction — but the rule-of-three
  bound in the power check does depend on it, and inflating `G` makes that bound
  look tighter than it is.
- **Branch M's arithmetic is about *fees*, and about fees only.** Nothing in it
  says a maker order would be filled. Fill probability is ADR 0017 §5's problem,
  is unaddressed here, and ADR 0017 measured that pre-game Kalshi mids move ≥1c
  on ~0.5% of minutes — so the fills that do arrive are concentrated in exactly
  the minutes when someone knows something.
- **A slice run cannot be repaired by labelling it.** If the D-gate is not met
  and the provisional output is quoted as a property of the table by anyone,
  downstream or later, the label did not work. That is a known failure mode of
  this exact payload and the reason `total` and `returned` are both returned.

---

## The power check — this is the deliverable, not a preliminary

**Can this measurement answer this question at the `n` available?**

### For the bound itself: yes, exactly, at every `n` including `n = 1`

`K(δ)` is a census. There is no sampling error, no standard error, no boundary
and no minimum `n`. The detectable effect is **one row** — the smallest effect
the question has. **This is the only measurement in this project that is not
power-limited**, and that is precisely why `partner` ordered it first.

Contrast, at the project's real headroom: the venue lowers the bar from 52.38%
to 52.00% — **0.38 points, 3.8 tenths** — and Lane A's power check established
that resolving anything at that scale needs `G = 428` games at σ=20 under the
amended alpha, against a record that has produced **29 scored games in its
life**. **A design that can only resolve effects larger than a point is not
measuring the thing this project exists to measure.** The bound sidesteps that
entirely by not being an estimate.

### For the generalisation: no, and here is the arithmetic

A zero over the record does **not** bound the rate at which actionable rows occur
in a wider universe by zero. With 0 clearing games out of `G` clusters, the
one-sided 95% upper bound on the per-game rate is the rule of three, `3/G`:

**[COMPUTED FROM CODE — closed form]**

| `G` observed | 95% upper bound on the per-game rate | reading |
|---:|---:|---|
| 29 | **10.3%** | one game in ten could still clear, unseen |
| 60 | 5.0% | |
| 100 | 3.0% | |
| 300 | 1.0% | the gate's own floor |
| 1,000 | 0.3% | |

**Registered consequence:** the write-up states the rule-of-three bound at the
observed `G` **in the same paragraph as** any generalising sentence, and no
sentence of the form *"actionable rows do not occur"* may be written — only
*"no actionable row occurs in this record, and at `G = __` the per-game rate is
bounded above by `__`% with 95% confidence."*

`G` for this population has never been counted (§0.3). It is bounded below by
29 and above by the number of distinct games in 1,535 rows, and nothing narrows
it further, so the table above is printed with the row for the measured `G`
highlighted rather than guessed at now.

### Verdict of the power check

**ADEQUATE — and uniquely so.** The bound resolves its own question exactly, at
the `n` available, with zero assumed inputs and zero alpha. The **generalisation**
to a wider universe is weak and is bounded, not claimed. The measurement is
worth running for the first reason and must not be quoted for the second.

A measurement that cannot resolve the question is worse than none, because it
returns a number anyway and the number gets quoted. This one resolves it.

---

## §F. Facts verified against source, not taken on trust

- **F1.** `devig(["fav","dog"], [1.11, 7.50]).method_spread("dog") × 100 =
  **2.0304**` and `devig(["fav","dog"], [2.10, 1.80]).method_spread("fav") × 100
  = **0.1817**` **[COMPUTED FROM CODE]**, reproducing `suppression.py:217-220`
  from the repository. `TestMethodSpreadDependsOnLineShape` asserts
  `> 0.6`, `< 0.6` and `lopsided > even` — **not** the values (§C1).
- **F2.** `fee_candidates(p, N, maker=True)["model_b_per_contract_nearest"]`
  is **0.00 in 7,992 of 7,992** (price, size) combinations
  **[COMPUTED FROM CODE]**. The stacked generous fee is identically zero.
- **F3.** The `N=1` maker saving under `calculate_fee` is **10.0 tenths on the
  single contiguous run `[173, 827]` and 0.0 outside**, exhaustively over 999
  prices **[COMPUTED FROM CODE]** — reproducing `docs/adr/0017` Addendum A
  independently.
- **F4.** The `N=1` cheapest-model taker saving reproduces Lane A §C1's Δ table
  on all seven runs, edge for edge **[COMPUTED FROM CODE]**.
- **F5.** `effective_price(500, 1) = 0.5200`; `effective_price(500, 1,
  maker=True) = 0.5100`; `(500, 10, maker=True) = 0.5050`; `(500, 100,
  maker=True) = 0.5044` **[COMPUTED FROM CODE]** — the four numbers behind §C5.
- **F6.** `edge_after_fees_tenths` is `(fair_probability − effective_price) ×
  1000` at `core/ev.py:179-180`, with no clamp and no rounding on the fair side
  — which is the monotonicity the domination argument of §4 rests on
  **[COMPUTED FROM CODE]**.
- **F7.** `/api/ledger` at HEAD takes `limit (le=1000)`, `offset (ge=0)` and
  `max_id (ge=1)`, orders by `r.created_ms DESC, r.id DESC`, and
  `LEFT JOIN fair_prices f ON f.id = r.fair_price_id` returning
  `p_multiplicative, p_additive, p_power, p_shin, p_conservative`
  **[COMPUTED FROM CODE — `routes.py`]**. The confirmatory variant is blocked on
  the **deploy**, not on code.
- **F8.** The ledger payload names the price field **`ask_tenths`**, not
  `entry_ask_tenths` (`_serialise`) — Lane A F2, reused. Registering the field
  name removes the one place a rename silently empties a filter, which this repo
  has hit four times.
- **F9.** `docs/adr/` runs 0001–0018 with 0018 taken, so 0019 is free and is
  reserved by §9 **[COMPUTED FROM CODE — directory listing]**.

---

## §S1. The extraction, fixed in advance

**Whole-table pull, over HTTP, both variants:**

```
page 0:  GET /api/ledger?limit=1000&offset=0
         read `newest_id` from the payload  ->  MAX_ID
page k:  GET /api/ledger?limit=1000&offset=1000k&max_id=MAX_ID
stop when offset + returned == total
assert  len(set(row ids)) == total            # P2, printed
```

Fields consumed: `ask_tenths`, `fair_probability`, `suppressed_reason`,
`ticker`, `side`, `created_ms`, `clv_horizon_hours`, `strategy_config_version`,
`edge_tenths` (**diagnostic only**), `fee_predicted` (**diagnostic only**), and
for the confirmatory `p_multiplicative`, `p_additive`, `p_power`, `p_shin`,
`p_conservative`.

**Equivalent SQL, if the volume is read directly:**

```sql
SELECT
  COALESCE(m.event_ticker, r.ticker)            AS cluster_key,
  (m.event_ticker IS NULL)                      AS unclustered,
  substr(r.ticker, 1, instr(r.ticker, '-') - 1) AS series_prefix,
  r.id, r.ticker, r.side, r.created_ms,
  r.entry_ask_tenths, r.fair_probability,
  r.edge_tenths      AS stored_edge_tenths_DO_NOT_USE,
  r.fee_predicted    AS stored_fee_DO_NOT_USE,
  r.suppressed_reason, r.clv_horizon_hours, r.strategy_config_version,
  f.p_multiplicative, f.p_additive, f.p_power, f.p_shin, f.p_conservative
FROM recommendations r
LEFT JOIN kalshi_markets m ON m.ticker = r.ticker
LEFT JOIN fair_prices  f ON f.id = r.fair_price_id
WHERE r.entry_ask_tenths BETWEEN 10 AND 989
  AND r.fair_probability IS NOT NULL
ORDER BY r.created_ms DESC, r.id DESC;   -- a TOTAL order; see P2
```

The stored edge and fee columns are selected **only** so their divergence from
the recomputation can be printed as a diagnostic. They enter no quantity in §7.
The aliases say so.

**Provisional slice run:** `GET /api/ledger?limit=1000`, cluster key from Lane A
§4's HTTP fallback, every output prefixed
`NEWEST-1,000 SLICE — PROVISIONAL — NOT A PROPERTY OF THE TABLE`, and the count
of rows sharing the boundary `created_ms` printed — **[MEASURED]** one
`created_ms` on this table carries 84 rows, so the slice's boundary group may be
split, and a split boundary makes even the slice non-reproducible at its edge.

## §S2. Required output of every run, in this order

Read `n` before the effect size, and read the frame before `n`.

1. **The frame.** `total`, `returned`, `offset`, `max_id`, the P2 assertions as
   executed with their results, the boundary-tie count, and the D-gate verdict
   (`WHOLE TABLE` or `PROVISIONAL SLICE`).
2. **The population ladder.** `n_rows` and `G` for P0/P1/P2/P3, with the nesting
   invariant `P3 ⊆ P1, P2 ⊆ P0` asserted and printed. Excluded-row counts by
   reason (§2), separately.
3. **The composition, before any count.** Horizon × bankroll era (Lane A §3's
   three mechanical levels) × series prefix × `strategy_config_version`, in rows
   and clusters. Rows per cluster: distribution, and the largest cluster's share.
4. **The cluster-key integrity print.** Distinct series prefixes; the number of
   `<DATE+TEAMS>` suffixes appearing under more than one prefix; `unclustered`
   rows. Lane A §4 defect 1.
5. **PRIMARY shortfall block** (§6's fixed form), for P0 first, then P1, P2, P3.
6. **The reachability rung**, `K(10.00)`, checked and stated before any branch.
7. **Branch Z / Branch N**, with preconditions shown met or unmet.
8. **Branch M — the maker line.** Band `[173, 827]` row and cluster counts;
   shortfall block restricted to the band; ALT-2 vs ALT-0 clearing counts at
   `N=10`, with `N=1` printed beside it and labelled non-decision-bearing.
   **[SUPERSEDED by Amendment 1 §A2 — the two sizes swap roles: `N=1` is
   decision-bearing, `N=10` is the labelled secondary.]**
9. **CONFIRMATORY shortfall blocks**, one per alternative ALT-0/ALT-1/ALT-2,
   with **the stacked count explicitly NOT computed** and a line saying so.
10. **Invariants, asserted and printed:** `E1min − E1 == Δ(price)` per §C4;
    `p_conservative == min(four) == fair_probability` per P5; and the monotonicity
    of `K` in δ and along the population nesting.
11. **Diagnostics:** the distribution of `recomputed − stored_edge_tenths`, which
    is Lane A §6's size-basis artefact made into a printed number rather than an
    argument.
12. **Grid B cross-tab**, labelled **DESCRIPTIVE — CANNOT PRODUCE A FINDING**.
13. **The rule-of-three rate bound** at the measured `G`.
14. **§10, reproduced verbatim.**

The harness's module docstring states what it does not establish, per the repo
rule that every harness carries its own limits, and it leads with §10's first
bullet.

---

## Registration record

| | |
|---|---|
| Registered | 2026-08-10 |
| Data seen at registration | **Yes — see §0.** Whole-table counters, horizon split, population split, per-game counts, and the `created_ms` tie structure. **No per-row ask, fair, edge or devig value has been seen by anyone.** |
| Primary estimand | `K(δ)` — a **count over a census**, zero sampling error |
| Direction | One-sided, generous. `K(δ) = 0` is the registered claim; `K(δ) ≥ 1` is a live outcome |
| Primary basis | **Stacked generous: loosest devig at `fair + δ`, cheapest fee model, maker basis — which is a fee of exactly zero at every price and every size (§C3)** |
| Confirmatory basis | Real per-row `max(p_mult, p_add, p_power, p_shin)`; **ALT-1 or ALT-2 individually, never stacked** |
| δ ladder | 0.00 / 0.18 / 2.03 / 5.00 / 10.00 points — fixed, five rungs, no sixth **[AMENDED §A1: a sixth rung at 16.70]** |
| Population | **P0 = all rows with a tradeable ask and a non-NULL fair.** P1/P2/P3 reported, decision reads P0 |
| Cluster key | `COALESCE(kalshi_markets.event_ticker, recommendations.ticker)`; HTTP fallback per Lane A §4 |
| Bucket edges | Shortfall histogram (8 cells, §5); Grid B = `validate.BUCKETS` verbatim; maker band `[173, 827]` tenths exactly |
| Alpha spent | **Zero.** Project-wide interval-test count stays at 3 at `alpha = 0.0167` each. Neither lane needs amending |
| Boundary | **None, and none needed** — a census has no sampling distribution and repeated looks are free (§7) |
| Decision gate | Whole table, pinned by `max_id`, `offset + returned == total` **and** `len(set(ids)) == total`; plus the `K(10.00) ≥ 1` reachability rung |
| Stopping rule | §8 — three scheduled runs, then stop. A grown record is a new artefact, not an update |
| Result destination | `docs/measurements/<run-date>-joint-bound-result.md`, written either way. ADR **0019** reserved |
| Assumed inputs | **Zero** |
| Verdict at registration | **READY.** PRIMARY runnable today as PROVISIONAL; decision-bearing on the whole-table run; CONFIRMATORY blocked on a deploy, not on code |
| Amendments | **1**, dated 2026-08-10, below. **No data observed at amendment** (§A0). |

---

# Amendment 1 — 2026-08-10

**Reason: two defects found after commit `a23a36f`, one in a threshold and one
in a premise. Neither was found by looking at data; both were found by checking
this document's own citations against source.**

Nothing above has been deleted or rewritten. Nine passages carry a
`[SUPERSEDED]` or `[AMENDED]` marker in place. **Where this amendment and the
original text conflict, this amendment governs.** The original stays because the
record is the product.

**A process failure is recorded here rather than hidden, because it is the exact
failure this document exists to prevent.** The first response to these two
defects was a wholesale rewrite of the registration body — **561 insertions and
352 deletions against the committed text** — changing the primary estimand,
rewriting the decision rule and re-cutting §5, with no amendment block and no
`[SUPERSEDED]` markers. `partner` caught it and reverted it. A pre-registration
whose text is quietly rewritten after commit is not a pre-registration, and the
fact that the rewrite was well-intentioned and contained real improvements is
precisely why the rule has to be mechanical rather than a matter of judgement.
**The improvements are in this amendment instead, where they are dated,
attributed and diffable against what was registered.**

## A0. What had been observed when this was written: nothing

The clause that makes an amendment legitimate rather than contamination.

**No data was observed between the registration of this document and this
amendment.** The live database was not queried, `/api/ledger` was not called, no
pull was made, no odds credit was spent, and **no value of `S`, `K(δ)`, `D*`,
`G`, `n_rows`, any shortfall, any quantile or any argmin row exists anywhere or
was estimated from any record.** The §0 disclosure is unchanged and no line has
been added to it.

**What does exist, disclosed for completeness:** `backend/analysis/joint_bound.py`
(untracked, 32 KB) implements the committed specification, with `S` as the
instrument and the primary's zero fee verified exhaustively in tests. **Verified
before writing this: no result file exists at the registered destination
(`docs/measurements/*joint-bound-result*`), and no pull artefact exists.** The
harness has not been run against the record by me.

Everything below was produced by executing repository code on inputs chosen
here, or by reading repository source, and is **[COMPUTED FROM CODE]**,
reproducible from the repository alone.

**Per §8, nothing restarts.** No population definition moved. The primary bound
is untouched.

## A1. The δ ladder topped out below the knob it was built to bound

**What was registered.** §5: five rungs, `0.00 / 0.18 / 2.03 / 5.00 / 10.00`
points, *"and no sixth"*; §7 Branch Z declared **CLOSED** if `K(δ) = 0` at every
rung.

**Why it is superseded.** §C2 correctly recorded that *"2.03 is a local maximum
over the lines anyone has looked at"* and that *"nothing in the repository
proves a global one"* — and then set a ladder whose top rung was 10.0 points
anyway, without ever measuring what the knob can actually reach. Measuring it
now:

**[COMPUTED FROM CODE — sweep of the two-outcome line space. Book probabilities
allocated proportionally, `q_fav = p(1+v)` and `q_dog = (1−p)(1+v)`; spread is
`DevigResult.method_spread`; favourite swept 50.00%–98.99% in 0.01% steps]**

| overround `v` | worst method spread | at fair favourite |
|---:|---:|---:|
| 1% | 0.981 pts | 99.0% |
| 2% | 1.950 pts | 98.0% |
| 3% | 2.901 pts | 97.1% |
| 4% | 3.839 pts | 96.2% |
| 6% | 5.641 pts | 94.3% |
| 10% | 9.065 pts | 90.9% |
| **20%** | **16.649 pts** | 83.3% |

Restricted to the region this project trades — **favourite ≤ 85%, overround
≤ 6%** — the worst case is **3.472 points**, at the corner.

**And the sharpest form of it:** the 1.11 / 7.50 line carries an overround of
**3.42%** **[COMPUTED FROM CODE — `DevigResult.overround`]**, and the worst
spread *at that same hold* is **3.301 points**. So 2.03 is **not even the
maximum at its own overround**.

**The defect, stated plainly.** As registered, Branch Z could have declared the
central question **CLOSED** on a record whose nearest row was 12 points short —
comfortably inside the devig knob's reach. That is a false closure in the
flattering direction, inside an instrument built specifically to resist one.

**What now governs.**

| symbol | value | what it is |
|---|---:|---|
| `D_realistic` | **3.5 pts** | worst spread over favourite ≤ 85%, overround ≤ 6%. Measured 3.472, rounded **up** |
| `D_swept` | **16.7 pts** | worst spread anywhere in the swept space. Measured 16.649, rounded **up** |

- **A sixth δ rung is added at 16.70 points.** The five registered rungs are
  unchanged and none moves.
- **Branch Z** is declared iff `K(16.70) = 0` on P0 — equivalently
  `min(S)/10 > 16.7` points.
- **A new intermediate verdict, Z-NARROW**, occupies `3.5 < min(S)/10 ≤ 16.7`:
  closed against realistic slates, **not** closed against lopsided or high-hold
  lines. **In Z-NARROW the confirmatory run after the deploy becomes
  decision-bearing rather than a footnote, and the ADR waits for it.**
- **Branch N** is `min(S)/10 ≤ 3.5`, unchanged in substance from the committed
  Branch N.

**Both thresholds are rounded up, and that is not cosmetic:** a threshold the
record must *exceed* to declare closure is made harder to clear by rounding up,
so the rounding runs against the declaration. `partner`'s independent sweep gave
15.875 at the same nominal parameters where this one gives 16.649 — the
difference is grid resolution against the `q < 1` feasibility boundary — and
**the larger figure is registered**, because the disagreement runs in the
direction that matters.

**What A1 does NOT change.** The population ladder, the exclusions, the
freshness predicate, the cluster key, the `S` definition, the histogram grid,
Grid B, the maker band `[173, 827]`, the stopping rule, the result destination,
the D-gate, the harness-reachability precondition, the alpha budget (still
zero), and the PRIMARY bound itself. **The sweep is frozen at the parameters
printed above and may not be re-run at different bounds once `S` is known** —
that would be choosing the verdict threshold with knowledge of the answer.

## A2. ALT-2 moves from `N = 10` to `N = 1` — a retired premise, one section after §C1 warned about exactly this

**What was registered.** §5 set `ALT-2` at `N = 10`, justified as *"ADR 0017
Correction 1: the smallest order this software can send is 10 contracts. `N=1`
maker is not a realisable state"*, and §C5 concluded *"the operative maker
headroom is 1.88 points, 4.9x"*.

**Why it is superseded — the premise was retired on 2026-08-09, and ADR 0017
says so itself, in the same Addendum this document already cited.**
**[COMPUTED FROM CODE — read at source]**

- `backend/core/sizing.py:15` — *"**There is no minimum order size, because
  there is nothing for one to prevent.** There was, until 2026-08-09: a flat
  `min_order_contracts = 10`…"*
- `backend/core/sizing.py:189` — *"No minimum order size, and no whole-order fee
  check here either. Both would be guards that cannot fire."*
- `backend/config.py:273` — `MIN_ORDER_CONTRACTS` is in `RETIRED_SETTINGS`; it
  logs an ERROR on config load and surfaces on `/api/health`, and does not raise.
- `docs/adr/0017` **Addendum A.2** — *"The setting was removed the same day…
  There is no minimum order size anywhere in the sizer now, and **nothing
  replaced it**."*

**This is §C1's failure mode recurring one section later, and that is the part
worth recording.** §C1 caught a number traced to a document whose scope did not
support the use. §C5 then took a number from ADR 0017 **Correction 1** while
citing ADR 0017 **Addendum A.2** — the very addendum that retires Correction 1's
premise — for a different fact eleven lines away. **Tracing a citation to a
document is not the same as checking whether the document retired it**, and a
document can supersede itself without renumbering the passage it supersedes.

**The direction matters and it is the flattering one.** `N = 10` makes the maker
saving look **larger** than `N = 1` does: **[COMPUTED FROM CODE]** at 50c the
maker saving against the deployed basis is **10.0 tenths at `N = 1` and 15.0
tenths at `N = 10`** — an overstatement of 0.5 points — and the headroom figure
moves 1.38 → 1.88 points. That flatters **Branch M**, which `tasks/NEXT.md`
calls *"the one line where a positive finding is not power-precluded"*. An error
that inflates the only branch which could still produce a positive result is the
one to catch before the run, not after.

**What now governs.**

- **`ALT-2` is `N = 1`**, matching `sizing.py:156`'s unconditional
  `effective_price(ask_tenths, contracts=1)` and Lane A §F3. **`N = 10` is
  printed beside it as the labelled non-decision-bearing secondary** — the exact
  inverse of what §5 says.
- **§C5's operative figure is `1.38 points, 3.6x` at `N = 1`.** The §C5 table
  itself is correct and unchanged; only the sentence naming which row is
  operative is superseded. 1.94 / 5.1x remains the `N = 100` limit and remains
  not operative.
- **Branch M** is evaluated at `N = 1`; its 5-cluster gate, its band
  `[173, 827]`, and the exhaustive list of what it authorises — **a cancel path
  and the free markout harness, not a strategy** — are unchanged.

**A consequential correction outside this document, flagged rather than made.**
`tasks/lessons.md`, in commit `6f82830`, carries the sentence *"'1.94 points /
5.1x' failed the same way: real, and the N=100 limit, quoted for a system whose
minimum order is 10 contracts."* **That system has no minimum order.** The
lesson's own example has propagated the retired premise, which is a tidy
demonstration of the lesson it is teaching. It is flagged here and not edited
from inside a pre-registration amendment; correcting it is a separate commit.

**What A2 does NOT change, and this is the bound on the correction.** **The
PRIMARY bound is size-invariant** by §C3 — Model B's maker fee is 0.00 in 7,992
of 7,992 (price, size) cases, independently re-verified by `partner` — so the
stacked generous fee is zero at `N = 1`, at `N = 10` and at every size.
**The headline finding cannot move.** A2 touches only the CONFIRMATORY variant's
ALT-2 and Branch M.

## A3. `D*` is registered as a required derived print, NOT as a new estimand

`partner` asked whether `D*` — the smallest uniform additive bonus to
`fair_probability`, in points, at which any row clears — should replace `S` as
the primary estimand, and asked for it to be argued rather than asserted.

**Argued, and the answer is no.**

```
D*_row  =  S_row / 10                              exactly, by the units
D*      =  min over rows of D*_row  =  min(S) / 10
```

`D*` is a **reading of the committed artefact**, not a replacement for it. The
committed §6 already made the `S` distribution the primary artefact, already
registered every `K(δ)` as a readout of it, and already fixed the histogram, the
printed form and the nearest-row print. Nothing about the instrument changes if
the same numbers are divided by ten and reported as a minimum instead of as a
count.

**So the estimand does not move, and saying otherwise would overstate what was
wrong.** The genuine defect in the committed document was **the threshold**
(§A1) — the ladder topped out below the knob's reach — and a threshold defect is
fixed by fixing the threshold. Presenting a units change as an estimand change
would have obscured that, and would have forced a rewrite of
`backend/analysis/joint_bound.py`, which correctly implements the committed
spec.

**What is registered instead:** `D* = min(S)/10`, in probability points, is a
**required print** in every run's output block, on the line immediately above
`S`'s minimum, beside both verdict thresholds and beside the fee-and-maker
knob's ceiling from §C4. The reason is legibility and it is worth stating: the
verdict compares the record's requirement against **the devig knob's reach**,
which is denominated in points, so a reader should not have to divide by ten to
check the branch. **Cents stay in the printed form too**, because *"the nearest
row is 11c short"* is the sentence a human reads.

**One comparison the print makes free, and it is the strongest line in the
artefact if Branch Z is declared:** the fee-and-maker knob is worth **at most
2.0 points** (20 tenths in the middle band, 10 in the wings — §C4). So a `D*` of
15 points would mean the fee model and the maker basis are not merely *set*
generous but **arithmetically incapable of mattering, by a factor of seven.**
That sentence is authorised only when the numbers support it, and the factor is
computed, never rounded up in prose.

## A4. One addition that is not a correction: the argmin integrity precondition

`min(S)` is decided by a **single row**, and the committed §6 did not say what
happens if that row is corrupt. Registered now, before any run:

> **PRECONDITION — ARGMIN INTEGRITY.** The row setting `min(S)` is printed in
> full — ticker, side, ask, fair, `created_ms`, cluster, `suppressed_reason`,
> horizon, config version — and checked against **CLAUDE.md rule 1**, *a large
> apparent edge is a bug until proven otherwise*, **before any branch is
> declared**. If its ask or fair is implausible it is **investigated as a data
> defect**, and the run reports the bound both with and without it. In addition,
> `min(S)` is always printed beside the **p1, p5 and p10** of `S` and beside the
> per-cluster-minimum distribution, so that a lone outlier is visible as one.

This is the instrument's only real fragility and it runs both ways: a corrupt
row **understates** closure, a missing row **overstates** it. §P2's
`len(set(ids)) == total` is the only defence against the second, which is why
the paging pin is a prerequisite rather than a nicety.

## A5. One caveat added to §10, for the same reason the others are there

Appended to §10, and it is the caveat that could overturn Branch Z:

> **`D_swept = 16.7` is a maximum over a *swept* space, not over all lines.**
> The sweep is two-outcome, proportional-overround, favourite ≤ 99%, hold ≤ 20%
> **[COMPUTED FROM CODE — §A1]**. Three-way markets, non-proportional vig
> allocation — which is what real books actually do to longshots — and holds
> above 20% are outside it. **`min(S)/10 > 16.7` does not mean "above every
> conceivable devig spread"**; it means above every spread this sweep could
> produce. This caveat exists because the committed version of this document
> made exactly the error it warns about, one rung down.

## A6. What this amendment does not change, stated so the absence is deliberate

- **No population, predicate, exclusion, cluster key, bucket edge or grid
  moves.** P0 is still primary; the `instr` freshness predicate, Grid B, the
  histogram grid and the band `[173, 827]` are untouched.
- **The primary estimand is `S`, as registered.** §A3.
- **The PRIMARY bound and its size-invariance are untouched.** §C3 holds; the
  headline finding cannot move.
- **The alpha budget is still zero**, and the project-wide interval-test count
  is still 3 at `alpha = 0.0167` each. Neither Lane A nor Lane B needs amending.
- **The stopping rule, the result destination and the reserved ADR 0019 are
  unchanged.**
- **The direction of both corrections is conservative.** A1 makes Branch Z
  *harder* to declare; A2 makes Branch M *harder* to name. The failure mode of
  this amendment is **more UNRESOLVED, never a false declaration** — which is
  the right way round, since Z closes a line of work and M is the only branch
  that could still open one.
- **No human chooses anything as a result of this.** Both thresholds are fixed
  numbers computed before any row was read, and both alternatives' sizes are
  fixed by what the deployed sizer does rather than by anyone's preference.

---

**Amendment 1 ends. No data had been observed when it was written (§A0).**
