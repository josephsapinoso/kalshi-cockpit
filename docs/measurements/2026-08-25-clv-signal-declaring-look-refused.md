# The G = 311 declaring look is refused — 2026-08-25

Registered in
[`2026-08-09-preregistration-clv-signal-test.md`](2026-08-09-preregistration-clv-signal-test.md),
as amended. Prior look:
[`2026-08-16-clv-signal-test-interim-look.md`](2026-08-16-clv-signal-test-interim-look.md).

**This is not the result document.** §8 fixes the result's destination as
`docs/measurements/2027-XX-XX-clv-signal-test-result.md`, written whichever way
it comes out. No result exists to write there. This file records that a look
which *presented itself* as declaring was audited and refused, and what would
have to be true for the next one to count.

---

## The claim that was audited

On 2026-08-24 the live `/api/signal` screen showed, and `tasks/NEXT.md`
recorded:

    SIGNAL TEST   NO SIGNAL   311 of 300 games
    beta -0.0766   se 0.0215   interval [-0.1545, +0.0013]

with the instrument's own words on the page: *"The record has reached the
registered floor of 300 games, so this verdict is a declaring one."*

## The reading reproduces exactly

Re-taken 2026-08-25 rather than inherited from a screenshot. Live pull
(`inspect_live_db.py clv-signal-pull --json --limit 100000`, 6.1 MB,
14,616 rows) through `scripts/run_signal_test.py`, and independently
re-implemented from the dump by the auditor:

```
G = 311   n = 14,616   P1 = 1.0000   unclustered = 0
sd(half_spread) 5.0154   sd(edge) 40.9806   sd(clv) 30.1481
multiplier 3.6288   smallest resolvable beta 0.0779
beta_hat -0.076589   gamma_hat -0.7713   se_cluster 0.021462
interval [-0.15447, +0.00129]
```

Byte-for-byte the screen's numbers. **The arithmetic is not what fails.**

## VERDICT: the declaration is refused. The registered verdict is UNRESOLVED.

> The registered primary (§P4 / §7 — modal `strategy_config_version` = 4 only)
> is `beta_hat = -0.0756`, `se_cluster = 0.0246`, **`G = 216`**, always-valid
> interval `[-0.1728, +0.0216]`. **G = 216 is below the registered floor of
> 300, so no verdict may be declared.** The pooled fit across all four config
> versions (`G = 311`, `beta_hat = -0.0766`, `[-0.1545, +0.0013]`) is reported
> separately as §P4 requires and **is not the primary**. Every interval
> computed at either look lies entirely below the NO-SIGNAL threshold of 0.40,
> and both arms are negative. The pooled estimate's leverage is concentrated:
> `too_few_books`/`no_market_width` carries **0.9392** of `sum(x_tilde^2)` on
> 13.5% of rows, so under §A4 **the pooled result is one group's result**.
> Effective clusters by inverse Herfindahl on leverage: **4.26**.

**`CLAUDE.md`'s existing sentence survives this audit intact and must not be
strengthened.** "Treat it as settled for planning; waiting is not work" stands.
What may **not** be written is that the registered declaring look has happened.

---

## Defects, each against the section it violates

### D1. §P4 and §7 — the declaration runs on a population the registration forbids as primary. Decisive.

> §P4: *"if it exceeds one, the primary analysis runs on the **modal version
> only** and the others are reported separately."*
> §7: *"A change of more than one version means the primary runs on the modal
> version and **`G` counts only those games**."*

The record holds four versions — `{1: 359, 2: 56, 3: 1682, 4: 12519}`. Both
clauses trigger; §A10 confirms P2–P4 stand unchanged. **No reading of §7 admits
the pooled declaration**: the only available ambiguity is whether "a change of
more than one version" counts versions or transitions, and four versions is
three transitions, so it fires either way. §P4 is unconditional from two
versions upward.

`build_report`'s `modal_config_only` defaults to `False`, and both
`GET /api/signal` and the harness's default invocation take the default. The
registered primary is 84 games short of the floor, not 11 over it.

### D2. §7 — the modal population changed identity between looks, so this is not one sequence

The interim look records the mix as 359 / 56 / **1,672** / 1,605 — modal
version **3**, and its modal-only sensitivity ran on v3 (`G = 86`,
`beta = -0.053`). Today modal is version **4**. From the dump the version
windows are disjoint: v3 spans 2026-08-10T22:34Z → 2026-08-15T17:44Z; v4 begins
2026-08-15T19:52:14Z.

**The registered primary population at look 1 and at look 2 share no rows.**
§7: *"`G` for the decision rule restarts if the population definition moved."*
The always-valid boundary is being asserted over a sequence whose defined
primary changed identity underneath it, and §7 already notes
`always_valid_multiplier` "documents this and does not correct for it."

The v4 sequence began 2026-08-15 and has reached `G = 216`.

### D3. §A4 — the mandatory leverage disclosure fires at 0.94, and nothing computes it

§A4's disclosure is unconditional and does not depend on the verdict: every
group's **leverage share** — its share of `sum_i (x_tilde_i)^2`, `edge_tenths`
residualised on `half_spread_tenths` and the intercept — is *"Reported beside
`beta_hat`, **always**"*, and a group above 0.50 whose removal leaves `G < 300`
requires the write-up to say **the pooled result is one group's result**.

Computed by the auditor from the dump:

| registered group | n | clusters | **leverage share** | G left | LOO upper |
|---|---:|---:|---:|---:|---:|
| `too_few_books` (=`no_market_width`) | 1,969 | 190 | **0.9392** | 271 | **UNTESTABLE** |
| Grid A `[200,800)` | 13,805 | 298 | **0.7592** | 32 | **UNTESTABLE** |
| `suspicious_edge` | 117 | 13 | 0.2415 | 311 | +0.0198 |
| Grid A `[800,990)` | 453 | 32 | 0.1739 | 311 | +0.0286 |
| `edge_within_method_noise` | 154 | 42 | 0.1531 | 311 | +0.0035 |
| Grid A `[10,200)` | 358 | 26 | 0.0669 | 311 | +0.0159 |
| unsuppressed | 12,382 | 271 | 0.0367 | 211 | UNTESTABLE |
| `wide_market` | 68 | 4 | 0.0208 | 311 | −0.0018 |
| `insufficient_depth` | 210 | 48 | 0.0065 | 311 | +0.0018 |
| `skeptic_*` | 4 | 4 | 0.0003 | 311 | +0.0012 |
| `no_depth`, `sizing:refused` | 0 | 0 | 0.0000 | — | — |

Two groups exceed 0.50 and both are untestable. The required sentence appears
nowhere, and `backend/analysis/clv_signal.py` computes no leverage share at all.

### D4. §A9.5 — wrong statistic and wrong grouping on the headline line

§A9 item 5 requires the **largest group's leverage share** on the same line as
`beta_hat`. The harness prints `largest contributor: moneyline at 91.4% of
rows` — a **row-count** share of `market_type`, which is **not a registered
group**. On that same grouping the leverage share is **0.9784**, not 91.4%.
Prop is 8.6% of rows and **2.2%** of the leverage.

### D5. §A4 — the downgrade branch is unimplemented, and has never executed

`verdict()` (`backend/analysis/signal_test.py:237-245`) returns NO SIGNAL from
the pooled fit alone. No registered group is computed and no leave-one-group-out
recomputation exists.

The auditor implemented it and ran it: **it does not fire** — seven of thirteen
groups are testable and the largest upper limit any returns is `+0.0286`, far
below 0.40. So this defect did not change the answer. But by this repo's own
rule — *"every guard is verified by disabling it and watching the test fail; if
it stays green, it's decoration"* — a branch that has never executed is
decoration, and it was harmless here by luck rather than design.

**A correction to the pre-audit reasoning, recorded because it was wrong in the
flattering direction.** The pre-audit note held that at `G = 311` against a
floor of 300 the downgrade test was near-vacuous, since only a group with ≤ 11
clusters could be removed. That is false: **removal only reduces `G` when it
empties a cluster**, and groups are non-exclusive. `too_few_books` spans 190
clusters and its removal leaves `G = 271`; `wide_market` spans 4 and its removal
leaves `G = 311`. The test was live and had to be run, not argued away.

### D6. The power check's sigma trigger fired, and the mandatory amendment is unwritten

> *"`sigma` is therefore a **reportable quantity at every interim look**, and if
> it comes in above 30 tenths **this document must be amended to raise the
> floor**."*

Reported: `sd(clv_tenths) = 30.1481` pooled, `31.6915` modal-only. Both above
30. §7: the amendment is written *"before the next look ... An amendment made
after a look and not recorded voids the registration."*

The interim look write-up reports none of `sigma_eps`, `sigma_x` or
`sd(half_spread)`, which §A9 item 2 requires at every look — so the trigger may
have been live at `G = 199` and gone unnoticed.

### D7. §A9 — five registered outputs are absent

`grep` for `family_wise|BUCKETS|horizons_agree` across
`backend/analysis/clv_signal.py` and `scripts/run_signal_test.py` returns
nothing. Missing from both runs: item 3 (`BANKROLL_DOLLARS`, open exposure,
daily P&L — added by §A5.1 precisely because `sizing.contracts`, and therefore
the regressor's basis, depends on them); item 6 (the §A4 group table and LOGO
results); item 7 (**Grid A and Grid B** with `family_wise_p` and
`family_wise_verdict`); item 8 (`horizons_agree`); item 9 (§9 verbatim).

### D8. §A9.2 — `sigma_eps` is a residual SD; the harness prints the raw SD, and they straddle the trigger

The power check defines `sigma_eps` as the **residual** SD of `clv_tenths`. The
harness prints `sd(clv_tenths)`. They are **29.7637** and **30.1491**, either
side of the 30 threshold. Whether D6 fires currently depends on which quantity
the reader takes, which the amendment must settle rather than the harness's
choice of line.

---

## The finding that matters more than any defect above

**`G = 311` is not the amount of evidence here. Effective clusters by inverse
Herfindahl on leverage: 4.26.**

- **2 games** carry 50% of the leverage on `beta`.
- **9 games** carry 90%.
- One game — `KXWNBAGAME-26AUG24GSMIN` — carries **43.80%** alone.
- All twelve top-leverage clusters are **WNBA moneyline**. WNBA is 19.1% of
  rows, 45 of 311 clusters, and **95.6% of the leverage**.

And those rows are pathological. Inside the `too_few_books` group `edge_tenths`
runs **−717.97 to +372.60 tenths** — a claimed edge of −71.8c on a WNBA
moneyline at an 82c ask, i.e. the consensus called fair ≈ 8c against Kalshi's
82c, off fewer than two books. `sd(edge_tenths)` is **107.8 inside that group
and 10.9 outside it**; 118 rows carry `edge < −100` tenths.

`CLAUDE.md` rule 1 is *"a large apparent edge is a bug until proven
otherwise."* **These are not edges.** `suspicious_edge` never fires on them
because `edge_ceiling_tenths = 40.0` bounds the **positive** side only, and
§A2.2 added a price bound but no edge bound. The registration never
contemplated a regressor with this tail.

### Sensitivity — diagnostic only; dropping high-leverage clusters is not a registered cut

| population | beta | se | G | interval | verdict |
|---|---:|---:|---:|---|---|
| all (as declared) | −0.0766 | 0.0215 | 311 | [−0.1545, **+0.0013**] | NO SIGNAL |
| drop top-10 leverage | −0.0189 | 0.0872 | 301 | [−0.3374, **+0.2996**] | NO SIGNAL |
| drop top-11 leverage | +0.0170 | 0.0971 | **300** | [−0.3381, **+0.3721**] | NO SIGNAL |
| drop top-12 leverage | +0.0459 | 0.1111 | 299 | [−0.3605, +0.4524] | below floor |

The last removal that stays at the floor lands the upper limit at **+0.3721
against a threshold of 0.400** — a margin of **0.028** — and `beta` has flipped
sign by then.

### The `sd(edge) = 41` counter-argument fails on its own premise

It was argued pre-audit that a floor raise predicated on `sigma` alone misreads
its own arithmetic, because `sigma_x` came in at 41 rather than the assumed 10,
so `sigma_eps/sigma_x = 0.74` against an assumed 2 and the realised MDE is
0.0779 rather than the feared 0.42.

**That premise is the artifact.** `sd(edge_tenths) = 40.98` is not a richer
regressor; it is 1,969 rows with broken fair values.

| population | G | sd(edge) | sigma_eps | se | **MDE** |
|---|---:|---:|---:|---:|---:|
| all (as declared) | 311 | **40.98** | 29.76 | 0.0215 | **0.0779** |
| drop top-11 leverage | 300 | 11.72 | 28.78 | 0.0971 | 0.3551 |
| drop top-12 leverage | 299 | 11.01 | 28.41 | 0.1111 | 0.4064 |
| no `too_few_books` rows | 271 | **10.90** | 28.35 | 0.1174 | **0.4391** |

The registration assumed `sigma_x = 10` and an MDE of **0.42** at `G = 300`.
Without the pathological rows `sd(edge)` is **10.90**. **The registration's
power arithmetic was right.** The apparent resolving power is purchased
entirely from rows CLAUDE.md rule 1 classifies as bugs until proven otherwise.

### Why beta moved −0.1412 → −0.0766 while G went 199 → 311

Three answers, and the third is the useful one.

1. **Sampling variation — consistent.** The looks are nested, so the test is on
   the increment: `sd(beta_new − beta_old) ≈ sqrt(0.0478² − 0.0215²) = 0.0427`
   against a difference of `+0.0646`, **z = 1.51**. Splitting today's record by
   cluster vintage: clusters present at the interim give **−0.1236**
   (se 0.0398, G = 146); clusters new since give **−0.0694** (se 0.0269,
   G = 165); difference z = 1.14.
2. **Composition — predicted in advance and confirmed.** The 2026-08-17
   annotation to the registration named this move by name — *"expected to drift
   **toward zero** ... by composition, not by evidence."* **Prop cluster count
   is identical at 81 at both looks** — zero prop clusters have accrued since
   ADR 0032 — so props fell from 40.7% of `G` to 26.0% while the arms are
   moneyline −0.0677 and prop −0.5192.
3. **What actually moved it.** The top three leverage clusters —
   43.80% + 16.36% + 7.53% = **67.7% of all leverage** — are
   `26AUG24GSMIN`, `26AUG19TORWSH` and `26AUG23INDCHI`, and **all three first
   appear after the interim look**. The move is, to first order, three WNBA
   games arriving. Neither "sampling variation" nor "composition" is the right
   framing; *"the estimate is a handful of games and the handful changed"* is.

---

## What this does not establish

- **Not that CLV pass-through is absent.** It establishes that on ~45 WNBA
  games' worth of effective leverage, dominated by rows whose consensus came
  from fewer than two books, no positive slope is detectable.
- Nothing about MLB; nothing about props after 2026-08-16; nothing about NFL,
  NCAAF or NBA; nothing about tradeability or fees.
- **Nothing about `beta` where bets would actually be placed.** Only 127 rows
  sit in the `0 < edge <= 40` tenths region.
- Nothing about the pooled `G = 311` figure as evidence — it is reported here
  because §P4 requires the non-modal populations be reported separately, not
  because it carries a verdict.

## What would have to happen for a declaration to be permitted

1. **Reach `G >= 300` on the modal config alone.** Currently 216. The only
   route that needs no amendment.
2. **Write the D6 amendment before that look**, resolving which `sigma` the
   trigger names (D8), and recording that it was written after the `G = 311`
   pooled result was known.
3. **Implement §A4 properly** in `backend/analysis/clv_signal.py`: the thirteen
   registered groups, leverage share, the largest share on the `beta_hat` line,
   and the LOGO recomputation — each verified by disabling it and watching it
   go red.
4. **Implement the missing §A9 outputs** (items 3, 6, 7, 8, 9).
5. **Adjudicate the `|edge| > 100` tail**, in an amendment written *before* the
   declaring look. It is covered by no registered exclusion, it produces 94% of
   the leverage, and the two choices give MDE 0.078 and 0.44 — i.e. they decide
   whether the test can resolve anything at all. Deciding it after the fact is
   choosing the analysis with the answer in view.
6. **Write the result to the registered destination** (§8), whichever way it
   comes out.

**A warning about step 2 and step 5, recorded rather than assumed away.** §7
exists to stop design changes made with the answer in view, and the answer is
now in view. An amendment written today is not blind. The one mitigating fact
is that the honest conclusion — that the effective evidence is ~4 clusters and
the floor should **rise**, not hold — runs against the amender's convenience,
which is the direction that costs credibility to fake. Any such amendment must
record that it was written after this look.

---

## Provenance

| | |
|---|---|
| Dump taken | 2026-08-25, live `kalshi-cockpit`, `git_sha 1bdc33b` |
| Rows | 14,616 (`clv-signal-pull`, `--limit 100000`) |
| Harness | `scripts/run_signal_test.py`, and an independent re-implementation by the auditor |
| Audited by | `measurement-skeptic`, before anything entered the record |
| Result | **Declaration refused.** Registered verdict UNRESOLVED at `G = 216`. |
| Written to `CLAUDE.md` | The stale `G = 199` is replaced by this look; the `UNRESOLVED` verdict it already carried is unchanged and was correct. |
