# Result — the joint bound, and why its verdict is not evidence

**Run 2026-08-10.** Registration:
[`2026-08-10-preregistration-joint-bound.md`](2026-08-10-preregistration-joint-bound.md),
committed at `a23a36f` with Amendment 1 at `8ae4db0`. Harness `4158905`.
Audited by `measurement-skeptic`; verdict **UNSUPPORTED as a decision-bearing
reading**.

---

## The defect, first, because it governs everything below

**Branch Z — the outcome that would have closed this project's central question —
was arithmetically unreachable before the data existed.** The run had one
possible outcome and it returned it. `BRANCH N — NOT CLOSED` is therefore a
consequence of the design, not an observation about the record, and **it
authorises nothing — including the withdrawal of the plan to stop.**

Two independent proofs, both measured.

### 1. The complementary-leg identity

Each game carries two Kalshi tickers that are complements. Since the generous
fee is identically zero (§C3) and `S = ask − 1000·fair`:

```
S_A + S_B  =  (ask_A + ask_B) − 1000·(fair_A + fair_B)
           =  the market width  +  the conservative-devig deficit
```

**[MEASURED — 312 same-instant complementary pairs in this slice]**

```
S_A + S_B      min −5.1     median +13.0     max +82.0 tenths
```

So `min(S_A, S_B) ≤ (S_A + S_B)/2` ≤ **41.0 tenths = 4.10 points on the single
worst pair**, and ~0.65 points at the median. Branch Z required `min(S) > 16.7
points` on **every** row — i.e. Kalshi's width plus the devig deficit exceeding
33.4c on every game, on a venue that quotes to ~2c. The worst pair in the slice
misses by a factor of four; the median misses by twenty-five. Across all 42
games the largest per-cluster minimum is **+2.5 tenths (0.25c)**.

This holds for any two-sided record. **No slice, no sample size and no further
data could have produced Branch Z.**

### 2. Amendment 1 made Branch Z and the reachability precondition mutually exclusive

§5 registers the δ = 10.00 rung as *"a δ where `K` is certainly non-zero if the
arithmetic works at all"*, and §7 makes `K(10.00) = 0` a **suspected-harness-
defect** precondition under which no branch may be declared. Amendment 1 §A1
then moved Branch Z's threshold to **δ = 16.70**, above that rung. `K` is
monotone in δ, so:

> `K(16.70) = 0` ⟹ `K(10.00) = 0` ⟹ the reachability precondition trips ⟹
> **no branch may be declared.**

Branch Z cannot be declared under any data, by the document's own clauses.

**§A6 claims the amendment's failure mode is "more UNRESOLVED, never a false
declaration". That is wrong in kind, not degree:** it made Branch Z impossible
and Branch N certain, and §9 assigns Branch N the consequence *"the plan to stop
is withdrawn and re-planned"*. **A post-registration threshold move put the only
project-closing outcome out of reach and guaranteed the outcome that keeps the
project running.** That is the flattering direction.

No claim is made about intent, and none is warranted: §A1's sweep argument is
principled, data-independent, and was written to fix a real hole — the ladder
genuinely did top out below the devig knob's reach. **I authorised it, on the
reasoning that rounding both thresholds up is conservative.** It is conservative
against false closure and it is not conservative at all against the failure that
actually occurred. Recorded here rather than in a footnote.

### 3. The symmetric guard was missing, and it fired

The registration guards `K = 0` everywhere. Nothing guards `K ≈ N` everywhere.

| population | K(5.00) | K(10.00) | K(16.70) | of N |
|---|---:|---:|---:|---:|
| P0 | 976 | 984 | 984 | 1000 |
| **P1 (unsuppressed)** | **413** | **413** | **413** | **413 — 100%** |

Four of six rungs return essentially every row. **A ladder like that
discriminates nothing.** The missing guard is the mirror of the one that exists:
*if `K(δ_top) ≥ 0.9·N`, the ladder does not discriminate and no branch is read.*

### 4. What `K(0.00)` actually counts

Because §C3 makes the generous fee identically zero, `K(0.00) = #{ask <
1000·fair}` — the count of rows with a positive **gross** edge. That is the sign
of a subtraction the engine already performs on every row and already declines.
**213 of the 258 clearing rows have a gross edge smaller than the ~2c fee they
would actually pay.** They clear only because the bound deleted the venue's
cost — and the venue's cost advantage *is* the premise under test.

---

## The measurement that does discriminate, and it was in the same pull

**[MEASURED — this slice, re-derived independently three times]**

```
unsuppressed rows                                        413   in 38 games
  ...with a positive NET edge under the deployed fee        0
  largest clean GROSS edge                              17.9 tenths = 1.79c
  the deployed taker fee at N=1                         20.0 tenths = 2.00c
  largest clean NET edge                                −2.1 tenths
```

**Zero of 413 clean rows in 38 games has a positive net edge, and the best one
in the slice misses the fee by 0.21c.**

This could have come out the other way — a clean row above the fee was entirely
possible and did not appear — so unlike the bound it is a real reading of a real
question. It is also the separating observation that runs *against* the
"there is edge here" explanation: under that reading, clean rows should
sometimes clear the fee. None does.

### And every apparent edge is a row our own guards already caught

45 rows carry a positive net edge under the deployed fee. **Zero are
unsuppressed. Zero are actionable. They span 8 games.**

```
stale_odds                 37 rows / 8 games
too_few_books              30 rows / 4 games   ] the SAME event: 185 rows each
no_market_width            30 rows / 4 games   ] over the slice, id-sets identical
suspicious_edge            12 rows / 1 game
edge_within_method_noise   12 rows / 5 games
insufficient_depth          2 rows / 1 game
```

That is a **coherence result**: the suppression rules and the edge computation
agree about which rows are garbage. It needed no bound, and it empirically
confirms what the fresh-odds registration §0.3 could previously only derive from
a counter.

`too_few_books` and `no_market_width` are **one signal, not two** — 185 rows
each with symmetric difference 0. One contributing book means there is no width
to measure, so the second code is entailed by the first. Any count treating them
as independent double-weights them.

---

## The tail is one game, and the largest edge in the record is a coin flip

**The magnitude claims do not survive per-group inspection.** Nested sensitivity
of `D*`:

```
all 1000 rows                       D* = −34.000 points
drop the 21 degenerate-fair rows    D* = −29.674 points
drop the whole TORATL game          D* =  −5.286 points
drop all suppressed rows (P1)       D* =  −1.795 points   (n=413, G=38)
```

A **19x collapse**. Of the 20 largest gross edges, **12 belong to one game**
(`KXWNBAGAME-26AUG10TORATL`) and 20 of 20 are WNBA across three games. Anything
written about the tail is a statement about one WNBA game.

The largest apparent edge in the entire record rests on `fair_probability =
0.49999999999999994` — a coin flip — on a game the Kalshi book prices **84/16**.
21 rows, 2 WNBA games, `too_few_books` on 100% of them. At one instant all four
legs of the event return the identical value, and complementary sides cannot
both be 0.5, so it is a **fallback, not a devig**. It is intermittent: the same
event returns 0.456737 / 0.510549 at a later instant. A separate lane is tracing
the code path.

**A suspicion of mine, retracted.** I read the simultaneous large edges on both
`-TOR` and `-ATL` as an impossible book — a riskless arbitrage. It is not:
at all five instants where both YES asks are present they sum to ≥1000 tenths,
zero arbs. The Kalshi book is ordinary and coherent (Toronto ~16c, Atlanta
~84c). **The venue is fine; our fair is broken.**

### It is a bug, and the guard built to catch it cannot fire

Traced. **No line anywhere returns `0.5` as a default** — the value is a real
devig on a degenerate input, and it is the *most confident* fair the system can
produce from the *least* informative input it can receive.

**The float.** `devig.py:134-147`, `power()`, uses `brentq` to find the exponent.
On one book quoting `[1.85, 1.85]` it returns `k` one ULP high (2.22e-16), and
`p**k` rounds to `nextafter(0.5, 0)`:

```
multiplicative  0.5                    (exact)
additive        0.5                    (exact)
power           0.49999999999999994    <- the root-finder's error floor
shin            0.5000000000000137
```

`conservative_probability` takes `min` across the four (`devig.py:215-222`), so
it **systematically selects the root-finder's error**. That is why the value is
never exactly 0.5. Equal odds that hit it include 1.82, 1.85 and 1.86 — ordinary
h2h prices.

**The trigger, proved necessary rather than guessed:** one contributing book
quoting both outcomes at identical decimal odds in `(1.0, 2.0)`. `multiplicative`
sums to exactly 1 by construction, so both sides reading ~0.5 forces equal
implied probabilities; with `book_count == 1` that is one book, two identical
prices.

**The defect, and it is the same shape as
[[the-zero-that-means-no-measurement-passes-every-threshold]] one step on.**
A one-book equal-odds consensus makes `method_spread ≈ 1.37e-14`, so
`spread_tenths ≈ 1.4e-11`, and `suppression.py:231`:

```python
edge_tenths <= 0 or edge_tenths > spread_tenths,
```

**passes for any positive edge whatsoever.** `edge_within_method_noise` exists
precisely to catch edge that is an artefact of devig-method choice — and on the
one input where the edge is *purely* a devig-method artefact, it is structurally
incapable of firing.

**So `min_book_count = 2` is the single threshold between a fabricated 50/50
fair and a surfaced row**, and `too_few_books` / `no_market_width` are that one
threshold counted twice: both fire iff `book_count < 2` (`suppression.py:187`;
`devig.py:311-313`). It has **no environment plumbing anywhere** — not `.env`,
`.env.example`, `fly.live.toml` or `config.py` — so the deployed value is the
code default at `suppression.py:69`.

**Eight of the 21 rows are fresh, fillable and would surface.**
`odds_age_ms = 31088` (31 seconds), `kalshi_quote_age_ms = 0`, `+1.2c` post-fee
edge, under the 4c `suspicious_edge` ceiling:

```
id 979  KXWNBAGAME-26AUG10CHISEA-SEA  no   ask 470  edge +12.0  depth  101.0
id 980  KXWNBAGAME-26AUG10CHISEA-CHI  yes  ask 470  edge +12.0  depth 1092.97
    suppressed_reason: too_few_books,no_market_width
```

Set `min_book_count = 1` and these surface as actionable and count toward the
300-game floor. The gate is protected today only because `engine.py:205-208`
zeroes `reference_contracts` on any suppression — but `edge_tenths`,
`kelly_fraction` and `reason_text` are computed from the bogus fair *before*
suppression runs and are **persisted regardless** (`engine.py:161-166`, `:232`).
The three largest `|edge_tenths|` in the slice — `+330.0`, `+320.0`, `−360.0` —
are all this defect.

**No test covers it.** The suite's only equal-odds two-outcome fixtures are
`(1.95, 1.95)` — a value where the defect does *not* reproduce, all four methods
returning exactly 0.5 — and `(2.50, 2.50)`, which `_validate` refuses.
`TestMarketWidthIsUnmeasurableNotZero` covers the one-book case for *width* but
always with asymmetric odds. **An untested path produced the largest apparent
edge in the record.**

**One more two-limits-on-one-quantity, found in passing and not yet acted on:**
`SuppressionConfig.max_odds_age_ms = 900_000` (`suppression.py:40`) is hardcoded
and does **not** read `MAX_ODDS_AGE_S`, which is `900` in `fly.live.toml:128`
and `.env` and feeds a different object consumed by `gate.py`, `live.py` and
`routes.py`. They agree today; changing the environment value moves the gate and
the API but **not the runner's suppression**.

**Not fixed in this session, deliberately.** `suppressed_reason` is half the
`actionable` predicate, so changing when a suppression fires changes what the
gate counts — the repo already refused a cheaper version of exactly this move.
It needs an ADR and a decision, not a quick patch at the end of a session.

---

## What this run is, as a frame

Newest **1,000 of 1,543** rows, ids 544–1543, `created_ms` 2026-08-08T04:44:47Z
to 2026-08-10T03:25:43Z — 46.7 hours, 169 sweep instants, 42 games, MLB and WNBA
only. Snapshotted 2026-08-10T03:37:16Z.

- **`D-gate` UNMET. No branch declared.** The harness printed
  `NO BRANCH DECLARED. A precondition is unmet` and reported only the reading the
  run *would* support.
- **Unpinned, and the table grew under it** — `total` 1,543 against the 1,535 of
  §0.1, and the boundary group is split (3 rows share the oldest `created_ms`).
  So this is **not reproducible even as a slice.** The `max_id` pin exists in
  `main` and is not yet deployed.
- **CONFIRMATORY variant BLOCKED** — the deployed payload carries no per-method
  probabilities. 1,000 of 1,000 rows dropped, never imputed.
- **`n_rows` is uptime.** 1,000 rows collapse to **748 distinct
  `(cluster, instant, ask, fair)` tuples**; the recorder writes both complementary
  legs and `TOR-yes ask == ATL-no ask`. `K(0.00) = 258 rows` is 203 distinct
  tuples in 193 game-instants.
- **`G = 42` is honest as a count of games** — 2 series prefixes, 0 suffixes
  under more than one prefix, so Lane A §4 defect 1 does not fire. It licenses
  the *existence* claim and nothing about magnitude, where the honest `n` is one
  row and three games.
- **The clearing set is selected on staleness.** Odds age p50 **2.00 h** among
  clearing rows against **0.07 h** among non-clearing — 29x.

---

## Branch M — also a foregone conclusion, and its named rows die to its own counterargument

948 rows / 41 clusters in `[173, 827]`; 46 rows in 19 games clear under ALT-2 and
not ALT-0. **The margin is exactly 10.0 tenths on all 46** — that is the fee
difference and nothing else, so the "finding" is that 46 rows sat in a
one-cent-wide window. A density fact.

Max ALT-2 net edge among the 46 is **1.0c**. ADR 0017's adverse-selection
counterargument is **1.50c**. **Zero of the 46 survives it.** The run's statement
that the counterargument "stands unmodified" should read: *not one named row
clears it.*

---

## What this does not establish

Written to include the ones that could overturn it, not the survivable ones.

- **It says nothing about whether an edge exists at Kalshi.** It is a statement
  about one strategy's arithmetic on 1,000 rows of one 46-hour window, in two
  leagues, in August.
- **Every sentence here is about *this slice*, not *the record*.** The D-gate
  forbids the stronger form and the pull was unpinned besides.
- **The 413-clean-row result is not immune to the tail's problem.** 38 games, and
  the per-game parts have not been shown to agree on magnitude — only on sign.
- **The fee it measures against is `calculate_fee`'s bar, not Kalshi's.** The
  whole fee model is secondary-sourced and this project has **zero fills, ever**.
  If both candidate models are wrong, every number here moves.
- **`fair_probability` is the worst of four devig methods**, so every gross edge
  here is a deliberately shrunk number, and the shrinkage is largest at the wings.
- **The one that would overturn this reading, stated because it was absent from
  the harness docstring:** a non-zero `K` at the δ = 0 rung is near-certain on
  *any* two-sided record, because the generous fee is zero and complementary legs
  sum to the market width. The harness's caveats are all conditioned on "if the
  bound returns 0" — there was no bullet for what happened.

---

## What replaces it

**Not a whole-table re-run of this instrument.** It will return Branch N for the
same arithmetic reason. Two replacements, in order:

1. **Re-specify the estimand as the shortfall against the *deployed* fee on the
   clean population** — `min` and the distribution of `edge_after_fees_tenths`
   over P1/P3, per game, with the closure threshold set from the **fee-and-maker
   knob ceiling of 2.0 points (§C4)** rather than from the devig sweep's 16.7.
   That threshold is reachable in both directions. **Disclose in §0 that this
   slice was already observed to return max −2.1 tenths on 413 rows in 38
   games** — the quantity has been seen, and a registration that hides it is
   worse than one that declares it.
2. **Deduplicate to one observation per `(game, instant, market)`** before any
   count, and register the unit as the **game-instant**, not the row.

The `max_id` pin and the four per-method probabilities are built and pushed; they
need the deploy before either replacement can run against the whole table.
