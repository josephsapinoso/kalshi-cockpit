# Result — the clean-population shortfall distribution

Registration:
[`2026-08-10-preregistration-clean-shortfall-distribution.md`](2026-08-10-preregistration-clean-shortfall-distribution.md).
Executed exactly as registered. **Not amended** — every correction and every
tension below is reported for the registrar to rule on by appended amendment,
and none has been acted on.

| | |
|---|---|
| `pulled_at_utc` | **2026-08-10T05:07:23.073061+00:00** |
| `pin` (`newest_id` off page 0) | **1564** |
| `total` under the pin | **1564** in 2 pages, `len(ids) == len(set(ids)) == total` |
| `backend/core/suppression.py`, repository revision **at pull time** | **`c4bca6b`** — *"ADR 0019: the agreement family is blind to correlated garbage"*, committed **2026-08-10T05:00:06Z**, 7 min before the pull. Prior revision `58f7a7c` (2026-08-07). |
| `backend/core/suppression.py`, **deployed** revision | **NOT PINNABLE TO A SHA — see below. This is §V detector 3 reporting UNKNOWN, not an assumption that the tree and the deployment agree.** |
| Last deploy before the pull | **2026-08-10T04:06:34Z** — **61 min before the pull, and 54 min before `c4bca6b` was committed** |
| Harness | `scripts/run_clean_shortfall.py` |
| Raw pull | `docs/measurements/2026-08-10-clean-shortfall-pull.json` |
| Full §S output | `docs/measurements/2026-08-10-clean-shortfall-run.txt` |

**On the deployed revision, and the §V ruling.** **[COMPUTED FROM CODE]** no
`/api/*` route exposes a build SHA, Fly release descriptions carry no git SHA,
and `flyctl deploy` builds from the working *directory* rather than from a
commit — which was dirty at the time. So the deployed build **cannot be pinned
to a SHA** and is reported as unknown, as §V requires.

**The deploy record still settles the void condition, and settles it twice
over.** **[MEASURED — `flyctl releases`]** the most recent deploy is
**2026-08-10T04:06:34Z**, which is **before** Lane A's `c4bca6b` and **before**
the pull. **No deploy occurred between the registration and the completion of
the pull**, so §V's part (a) is not satisfied by anything. Independently, §V's
part (c) fails: **[MEASURED FROM DATA]** `inconsistent_consensus_metadata`
appears **0 times in 1,564 rows**, including every row written after that
deploy. §V's test requires all three parts. **The registration is NOT VOID**,
and — unlike at registration time — that is now read off the deploy record
rather than inferred from source.

Lane A committing `c4bca6b` mid-run changes nothing: a commit is not a deploy,
and `suppressed_reason` is write-once, so no local change can reach a persisted
row.

---

## THE RUN STOPPED. No claim is declared.

```
*** STOP THE LINE ***
    tripped: R3 (saturated: Grid D)
```

**[MEASURED FROM DATA]** Grid D's middle cell `[173, 827]` holds **320 of 323**
clean deduplicated observations = **99.1%**, at or above §R3's `0.90` saturation
threshold.

§7 is verbatim: *"§R1, §R3, §R4's H4 twin and `G >= 2` are evaluated and printed
before any claim. If any of them trips, no claim is declared, the run reports
`STOP THE LINE` with the tripped guard named."* §9's table repeats it. So:

> **H4, H2, H3a, H3b and H1 are WITHHELD. None is declared, none is refuted,
> and §9's refutation ADR is not written from this run.**

The harness withholds the verdicts rather than printing "would have been X".
Printing the parenthesised answer is a declaration in all but name, and worse: it
would hand a future registrar the five results, so any amendment relaxing R3
would be written with the answers already visible. That is precisely the
contamination the document exists to prevent.

**Stated honestly, because it cannot be hidden and pretending otherwise would be
dishonest:** §S mandates the underlying census statistics be printed *regardless*
(§S items 6–9 say "printed regardless" in four places), and they are printed
below. A reader can compute from them what each verdict would have been. That is
a consequence of the registration's own structure — a guard that trips at the
same moment the statistics are computed — not something introduced here. **Any
amendment to R3 must be written in the knowledge that the census is already
visible, and must say so.**

### The tension the registrar must rule on

§R3's own text gives a *local* consequence — a saturated grid "is printed with
the banner `DEGENERATE — DOES NOT DISCRIMINATE` and may not be referred to in any
conclusion" — while §7 and §9 make R3 a **stop-the-line**. §S item 11 separately
labels Grid D `DESCRIPTIVE — CANNOT PRODUCE A FINDING`.

So a cut that the registration itself declares incapable of producing a finding
vetoes five claims that do not depend on it. The stricter reading was followed
because §7 and §9 agree with each other and the user brief restated it. **The
registrar owns which reading governs; this run does not choose.**

**And note that Grid D saturating is a fact, not an instrument failure.**
**[COMPUTED FROM CODE — `effective_price(p, 1)` swept over all 999 tradeable
prices]** the deployed taker fee at one contract is a three-run step function
`[1,172] = 10.0` / `[173,827] = 20.0` / `[828,999] = 10.0` tenths — derived by
the harness from the fee curve, never typed in, and matching the registration
exactly. **[MEASURED FROM DATA]** 99.1% of the clean population pays the same
20.0-tenth bar. Grid D "does not discriminate" *because near-even moneylines are
what the recorder writes*, which is worth knowing and is the opposite of a
broken instrument.

---

## §S1 — The frame. Prerequisites.

| Check | Verdict | Evidence |
|---|---|---|
| **P1** deployed route serves the pin | **MET** | page 0 returned `newest_id = 1564` |
| **P2** pull complete and duplicate-free | **MET** | `len(ids) = len(set(ids)) = total = 1564`, `max(id) = 1564 <= pin`, table did not move during the pull |
| **P3** every clean `ask_tenths` in `[1, 999]` | **MET** | 0 dropped |
| **P4** `suppressed_reason` never `""` | **MET** | count 0 |
| **P5** four `p_*` non-NULL on the clean set | **MET** | 0 rows excluded from H3a/H3b |
| **P6** `p_conservative == fair_probability` | **MET** | 614/614 |
| **P6** `p_conservative == min(four methods)` | **MET** | 0 violations |
| **P7** `inconsistent_consensus_metadata` never fires | **MET** | 0 occurrences in 1,564 rows |

Page 0 was fetched twice — once unpinned to learn the pin, then **re-fetched
under the pin** — because an unpinned page 0 can carry rows above the pin, and
`id <= pin` is the entire basis on which the snapshot is immutable.

## §S2 — The guards, before any claim

| Guard | Value | Verdict |
|---|---|---|
| **R1** `n_window` | **323 of 323** clean deduplicated observations have own `spread_tenths < 40.0` | **PASS** — H1's falsifier was arithmetically reachable |
| **R2** `n_new` | **0** clean rows with `id > 1549` | H1 is a **checksum, not a measurement**: `REPRODUCTION — NOT A NEW OBSERVATION`. Never a stop. |
| **R3** Grid D | largest cell `(173, 827)` **320/323 = 99.1%** | **TRIPS** |
| **R3** Grid B | largest cell `(500, 600)` **107/323 = 33.1%** | PASS |
| **R3** series prefix | largest cell `KXMLBGAME` **265/323 = 82.0%** | PASS |
| **R3 twin** `G` | **59** clusters | PASS |
| **R4's H4 twin** | degenerate predicate returns **0** clean / **21** suppressed | **PASS** — the predicate demonstrably fires |

**R2 in full.** 15 rows arrived between §0.2's pull (`pin = 1549`) and this one
(`pin = 1564`). **[MEASURED]** all 15 are suppressed — 14 `stale_odds`, one
`stale_odds,too_few_books,no_market_width`. **Zero of them are clean.** So the
clean population is byte-identical to §0.2's, and H1 could not have returned
anything other than its known value. R2 did its job.

## §S3 — The five counts, side by side

| Count | Value | What it is |
|---|---:|---|
| `n_rows` | **614** | clean rows — this is **uptime** |
| `n_ticker_side_instants` | **614** | integrity: **equals `n_rows`** ✓ the recorder is not double-writing |
| `n_obs` | **323** | distinct `(cluster, created_ms, claim)` — **the registered unit** |
| `n_claims` | **118** | distinct `(cluster, claim)` — the hardest floor |
| `G` | **59** | distinct clusters — **the independence unit** |

- **dedup ratio `n_rows / n_obs` = 1.901.** Registration §0.3 item 1 named this as
  the whole point of the run: `614` was never a count of distinct evidence.
  **[MEASURED]** it is `323`, and at the standing-claim floor it is `118` — about
  **two per game**, which is what A1 predicts and nothing more.
- **non-normalisable clusters: 0.** A1's registered detector. Every one of the 59
  clusters has a suffix set of exactly two members, so every `no` row normalised
  onto its opponent's claim and **A1 did not fail silently**.
- **near-duplicate instants: 0** claim-pairs with `|Δ created_ms| <= 1000 ms`.
  §3's leak 1 did not materialise; nothing was collapsed to make that true.

**614 and 59 reproduce §0.2 exactly**, which is the cross-check that this run's
population predicate is the same one.

## §S4 — Cluster-key integrity

- **[MEASURED]** distinct series prefixes over the whole pull: `KXMLBGAME` 1,142,
  `KXWNBAGAME` 422. Two, as expected.
- **`<DATE+TEAMS>` suffixes under more than one prefix: 0.** §3's registered
  known defect **did not fire** — `G` is not inflated by spread or total rows.
- **collapsed groups (size ≥ 2): 291.** Within-group `fair_probability` range:
  **max 0.0 on every group** — §C2's structural identity asserted and **holding**,
  so the `fair_price_id` join and the opponent lookup behave as
  `runner.py:665-693` says.
- Within-group `ask_tenths` range: **min 0, median 0, max 20 tenths; 220 of 291
  groups have range 0.** So the two legs of a claim are quoted off two different
  order books and **usually, but not always, agree** — exactly what §C2 predicted
  and refused to assume. The registered representative rule (largest `E1`) is
  what handles the other 71.

## §S5 — Composition, before any rate

| prefix | `strategy_config_version` | `clv_h` | obs | share | clusters |
|---|---|---:|---:|---:|---:|
| KXMLBGAME | 1 | 1.0 | 118 | 36.5% | 26 |
| KXMLBGAME | 1 | 0.0 | 117 | 36.2% | 16 |
| KXWNBAGAME | 1 | 0.0 | 30 | 9.3% | 4 |
| KXMLBGAME | 1 | — | 20 | 6.2% | 8 |
| KXWNBAGAME | 1 | 1.0 | 14 | 4.3% | 6 |
| KXMLBGAME | 2 | — | 8 | 2.5% | 4 |
| KXWNBAGAME | 2 | — | 6 | 1.9% | 3 |
| KXWNBAGAME | 1 | — | 6 | 1.9% | 1 |
| KXMLBGAME | 2 | 0.0 | 2 | 0.6% | 1 |
| KXWNBAGAME | 2 | 0.0 | 2 | 0.6% | 1 |

Observations per cluster: **min 2, p25 2, median 4, p75 8, max 17.**

> **LARGEST CLUSTER — printed beside every aggregate, per CLAUDE.md:**
> `KXMLBGAME-26AUG091605DETSF`, **17 of 323 = 5.3%**.

### §V detector 1 has fired: the record IS already a multi-configuration mixture

**[MEASURED FROM DATA]** two distinct `strategy_config_version` values, and the
boundary is exact:

```
version 1   ids    1 – 1394   2026-08-07T19:33Z – 2026-08-09T19:39Z   (578 clean)
version 2   ids 1395 – 1564   2026-08-09T20:09Z – 2026-08-10T05:06Z   ( 36 clean)
```

The registration requires the write-up to say so, and it does. Three things bound
what it means:

1. **It is not a §V trigger.** The boundary is at 2026-08-09T20:09Z. §0.2's pinned
   pull (`pin = 1549`) already spanned it, so the mixture was in the data the
   registrar saw. No configuration change occurred during or after this
   registration: ids 1550–1564 are all version 2.
2. **No suppression threshold moved observably.** **[MEASURED FROM DATA — the
   deployed record alone; the config body is not on the payload]** every
   suppression code's firing boundary is mutually consistent across the two
   versions: `suspicious_edge` fires above `(38.07, 59.13]` tenths on v1 and no v2
   row contradicts it (the registered ceiling is 40.0); `stale_odds` fires above
   `(808872, 964270]` ms on v1 — bracketing 900,000 ms — and no v2 row
   contradicts it; `edge_within_method_noise` satisfies `0 < edge <= spread` on
   every row of both. The version bump is therefore **consistent with a change to
   `kelly_fraction` or `max_order_contracts`** — the other two members of the
   version payload — rather than to `SuppressionConfig`.
3. **That is inference, not proof.** **[COMPUTED FROM CODE]** no route exposes the
   config body, so what actually changed at id 1395 is **not readable over HTTP**
   and is not claimed here.

---

## §S6 — H4. Fabricated fairs in the clean population. **Reported first.**

**Verdict: WITHHELD — STOP THE LINE.** The census is printed as §7 requires.

| Quantity | Value |
|---|---:|
| `n_degen`, **clean** population (pre-dedup) | **0** |
| `n_degen`, **suppressed** population (the paired control) | **21** |
| same under the narrower `tasks/NEXT.md` ULP signature | clean **0**, suppressed **21** |
| **the undercount, as a number** | **0** |
| clean degenerate rows in `ask ∈ [440, 479]` | **0** |

### The registered ULP correction was right to make and cost nothing here

§0.7 item 3 registered that requiring `p_power` one ULP below 0.5 *undercounts*,
because it drops the `1.95/1.95` case where all four methods return exactly 0.5.
**[MEASURED FROM DATA]** on this record every one of the 21 degenerate rows
carries the identical vector

```
p_multiplicative 0.5   p_additive 0.5   p_power 0.49999999999999994   p_shin 0.5
```

— exactly one ULP below on `p_power` — so the two predicates return **the same
21**. The correction is a true statement about a reachable case that **has not
occurred in this record**. Using the broader predicate was still right: it is the
only one that would have caught the other case, and its cost was zero.

### Extra predicate 1 — the two-book degenerate census, and it answers more than asked

The registered deduction makes it free: `too_few_books` fires iff
`book_count < 2` **[COMPUTED FROM CODE — `suppression.py:185`]**, so a clean row
has `book_count >= 2` **by construction**, and every clean row matching the
predicate *is* a two-book degenerate row. `n_degen(clean) = 0` therefore answers
ADR 0019's pending input 1: **reachable, never occurred, on this record.**

**[MEASURED FROM DATA]** the record says something stronger than H4 asked for.
All **21** degenerate rows carry `too_few_books`, so all 21 have
`book_count < 2` — they are **one-book** degenerate fairs, which the deployed
guards **do** catch. They fall in **2 games** (`KXWNBAGAME-26AUG10CHISEA` 11,
`KXWNBAGAME-26AUG10TORATL` 10), asks 160–850 tenths, and every one is suppressed.

> **The two-book degenerate fair — the state ADR 0019 is actually about — has
> never occurred anywhere in this record, in the clean population or the
> suppressed one.** Every observed degenerate fair is the one-book case.

That is a materially better answer for the ADR 0019 lane than "0 clean rows",
and it is a census of the live record rather than of the mature-MLB fixture that
§10 correctly says is the wrong population to clear H4 with.

## §S7 — H2. Concentration.

**Verdict: WITHHELD — STOP THE LINE.**

**[MEASURED]** `max_game_share = 17/323 = 0.0526` against the registered
threshold of `0.50`.

The full per-game table — all 59 clusters with observation count, share, `min S`,
`max S` and `max E1` — is in `2026-08-10-clean-shortfall-run.txt`. Extract:

| cluster | obs | share | min S | max S | max E1 |
|---|---:|---:|---:|---:|---:|
| KXMLBGAME-26AUG091605DETSF | 17 | 5.3% | 16.34 | 34.32 | −16.34 |
| KXMLBGAME-26AUG091610LADAZ | 16 | 5.0% | 14.59 | 38.95 | −14.59 |
| KXMLBGAME-26AUG091435BALTEX | 13 | 4.0% | 12.05 | 33.93 | −12.05 |
| KXWNBAGAME-26AUG09DALMIN | 12 | 3.7% | 9.96 | 45.45 | −9.96 |
| … 51 more … | | | | | |
| **KXMLBGAME-26AUG091335NYMPIT** | 8 | 2.5% | **2.05** | 40.27 | **−2.05** |
| KXMLBGAME-26AUG071910LAAMIA | 4 | 1.2% | 2.17 | 52.79 | −2.17 |

**Every one of the 59 per-game maxima is negative.** The parts agree with the
pooled number — which is the condition CLAUDE.md sets before a pooled number is
readable at all.

## §S8 — H3a, then H3b

**Both verdicts: WITHHELD — STOP THE LINE.**

`n_spread` = **323** of 323 (every clean deduplicated observation has all four
`p_*`), against `MIN_EXPECTED_PER_SIDE = 5`. The `n`-before-effect-size
precondition is satisfied.

| | min | p25 | median | p75 | max |
|---|---:|---:|---:|---:|---:|
| `S` (shortfall, tenths) | 2.05 | 19.81 | **25.58** | 31.53 | 52.79 |
| `spread_tenths` | 0.02 | 0.77 | **1.88** | 5.41 | 32.98 |

- paired median `S − spread_tenths`, **nearest rank: +22.70**
- paired median `S − spread_tenths`, **interpolated: +22.70** — the two
  conventions **agree in sign**, so H3a's answer does not rest on a convention
  the registration left open
- share of observations with `S > spread_tenths`: **319/323 = 98.8%**

**H3b — the one that governs the citable sentence.**

```
S_min          =  2.0534 tenths  =  0.2053c
spread_at_min  =  2.3191 tenths        (1 attaining observation, no tie)

id=726  KXMLBGAME-26AUG091335NYMPIT-NYM  side=yes  ask=450  fair=0.4679465562067771
        p_mult 0.47026560719938837   p_add  0.46875187753965314
        p_pow  0.4679465562067771    p_shin 0.4687518775396557
        spread 2.3191   E1 −2.0534
```

**[MEASURED]** the observed `spread_tenths` distribution on the live record —
median **1.88**, range **0.02 – 32.98** tenths — is wider than §0.6's fixture
calibration (median 1.3, range 0.32 – 4.61). The registration built H3b on the
observation that `S_min = 2.1` sits **inside** the fixture's spread range; on the
live record the attaining row's own spread is **2.3191**, and it is the row's own
spread that H3b compares against. Both numbers are printed; no verdict is read
off them.

## §S9 — H1. Reproduction, not discovery. **Reported last, deliberately.**

**Verdict: WITHHELD — STOP THE LINE.** R2 label: **`REPRODUCTION — NOT A NEW
OBSERVATION`** (`n_new = 0`).

**[MEASURED]** `max E1` over clean deduplicated observations = **−2.05 tenths
(−0.205c)**. Zero clean deduplicated observations have `E1 > 0`; the enumeration
clause had nothing to enumerate.

**[COMPUTED FROM CODE + MEASURED]** §3's representative rule makes the
deduplicated maximum equal the row maximum, §0.2 measured that maximum over
`id <= 1549`, and `n_new = 0`. So this number is **arithmetically incapable** of
differing from the prior. It is a checksum. It is reported as one.

## §S10 — Diagnostics

- **The per-row identity holds.** `E1 == 1000·fair − ask − fee_tenths(ask)`, max
  |residual| **1.226 × 10⁻¹³** over 614 rows.
- **The size-basis artefact is exactly zero on this population.**
  `E1 − stored edge_tenths` is **0.00 on all 614 clean rows**. §5's recomputation
  was still right to insist on — the divisor is not recoverable from the row, so
  the equality had to be *checked*, not assumed — but on the clean set every row
  sized to zero contracts and `engine.py:204`'s `max(1, contracts)` already
  priced at n=1. **The artefact is real elsewhere and absent here.**
- **Per-code counts over the suppressed population** (950 rows), exact token match
  on the split, no wildcard surface (§C1):

| code | count |
|---|---:|
| `stale_odds` | **859** |
| `too_few_books` | **245** |
| `no_market_width` | **230** |
| `suspicious_edge` | 86 |
| `edge_within_method_noise` | 18 |
| `insufficient_depth` | 17 |
| `stale_kalshi_quote`, `no_commence_time`, `commence_skew`, `no_depth`, `wide_market`, `inconsistent_consensus_metadata` | **0** |

Six of the twelve declared check names have **never fired** in 1,564 rows. No
token was observed that is absent from `ALL_CHECK_NAMES`.

### Finding 1 — `too_few_books` and `no_market_width` are NOT one signal on the whole table

**This corrects a registered number.** §S item 10 registers them as *"one signal,
not two — **[MEASURED — slice]** 185 rows each, symmetric difference 0; both fire
iff `book_count < 2`"*.

**[MEASURED FROM DATA — whole pinned table]**

```
too_few_books        245
no_market_width      230
symmetric difference  15      all 15 are too_few_books WITHOUT no_market_width
```

The 15 are `id` **53–143**, created **2026-08-07T19:33Z – 20:06Z**. From
`id = 144` (**20:12Z**) onward the two codes are **perfectly coincident across
1,421 consecutive rows**.

**The cause is identified and it is already in this repo's own lessons file.**
Commit **`58f7a7c`** (2026-08-07) — *"devig: an unmeasurable market width must
refuse, not read as perfect agreement"* — is the fix for
*"the zero that means 'no measurement' passes every threshold"*. Before it,
`market_width` was `0.0` on a one-book consensus rather than `None`, so
`no_market_width` could not fire while `too_few_books` did. **The deploy of that
fix landed between 20:06Z and 20:12Z on 2026-08-07, and the record shows it
happening.**

Three consequences, none acted on:

1. **The registered "symmetric difference 0" is true of the slice and false of
   the table.** The 15 rows are the *oldest* in the record, so the newest-1,000
   slice **structurally cannot contain them**. This is the registration's own §6
   warning about slices, landing on the registration.
2. **`strategy_config_version` did not see it.** All 15 rows and all 1,421
   coincident rows are **version 1**. §V names this as the live hole — *"adding,
   removing or rescoping a `Check(...)` adds no field, so it mints no new
   version"* — and the same is true of a change to the *producer* feeding the
   checks. **The hole is now observed rather than hypothesised: the record spans
   two producer behaviours and the version column is blind to the boundary.**
3. **P7 and §V(c) still hold, but the evidence changes shape.** The state
   `book_count < 2 AND market_width is not None` — precisely what
   `inconsistent_consensus_metadata` tests for — is **representable and has
   occurred 15 times in this record.** It is unsatisfiable for the *current*
   producer, and the record backs that with 1,421 consecutive clean rows, but the
   supporting claim is "the current producer has not violated the invariant",
   **not** "the state cannot exist". **For the ADR 0019 lane: the check is not
   decoration — it is a regression detector for a bug that actually happened, on
   this record, on 2026-08-07.**

### Finding 2 — §10's "45 rows carry a positive edge" is a slice number

Registration §10's first bullet — the one that would overturn the result — says
*"45 rows carry one; all are suppressed"*, labelled **[MEASURED — slice]**.

**[MEASURED FROM DATA — whole pinned table, recomputed `E1` at n=1]**

```
suppressed rows with a positive net edge, newest-1,000 slice   45   (reproduces exactly)
suppressed rows with a positive net edge, WHOLE PINNED TABLE  137   in 19 clusters
                                                    max E1   +389.10 tenths
      top reasons: stale_odds,suspicious_edge 66 | stale_odds 23
                   stale_odds,too_few_books,no_market_width 12
```

The slice figure reproduces at exactly 45, which is the cross-check that this
recomputation matches the registration's method. **The whole-table figure is
137.** §10 is reproduced verbatim by the harness as registered; anyone carrying
its first bullet into a whole-table document must carry **137**, not 45. The
bullet's *argument* is unaffected and in fact strengthened.

## §S11 — Grid D, then Grid B. `DESCRIPTIVE — CANNOT PRODUCE A FINDING`

**Grid D** — **`*** DEGENERATE — DOES NOT DISCRIMINATE ***`**

| cell | obs | share | min S | median S | max E1 |
|---|---:|---:|---:|---:|---:|
| `[1, 172]` | 1 | 0.3% | 20.60 | 20.60 | −20.60 |
| `[173, 827]` | **320** | **99.1%** | 2.05 | 25.65 | −2.05 |
| `[828, 999]` | 2 | 0.6% | 21.49 | 21.49 | −21.49 |

**Grid B** — `analysis.validate.BUCKETS`, verbatim. `outside` = **0**, so the
pooled population and the grid are the same rows.

| cell | obs | share | min S | median S | max E1 |
|---|---:|---:|---:|---:|---:|
| `(10, 100)` | 0 | 0.0% | — | — | — |
| `(100, 200)` | 2 | 0.6% | 20.60 | 20.60 | −20.60 |
| `(200, 300)` | 11 | 3.4% | 9.96 | 27.08 | −9.96 |
| `(300, 400)` | 31 | 9.6% | 12.69 | 20.32 | −12.69 |
| `(400, 500)` | 106 | 32.8% | 2.05 | 23.06 | −2.05 |
| `(500, 600)` | **107** | **33.1%** | 2.17 | 26.20 | −2.17 |
| `(600, 700)` | 46 | 14.2% | 12.31 | 29.21 | −12.31 |
| `(700, 800)` | 18 | 5.6% | 18.96 | 32.25 | −18.96 |
| `(800, 900)` | 2 | 0.6% | 21.49 | 21.49 | −21.49 |
| `(900, 990)` | 0 | 0.0% | — | — | — |
| `outside` | 0 | 0.0% | — | — | — |

Neither grid may be referred to in any conclusion, and no cell in either may be
reported as significant or described with any word implying a test.

## §S12 — The one-way downgrades

Every claim was recomputed on the reduced population leaving out **each of the 59
clusters in turn**, and separately on the **`n_claims` key** (all instants
collapsed, `n = 118`).

```
H4:  survives leave-one-game-out over all 59 clusters and the n_claims key
H2:  survives leave-one-game-out over all 59 clusters and the n_claims key
H3a: survives leave-one-game-out over all 59 clusters and the n_claims key
H3b: survives leave-one-game-out over all 59 clusters and the n_claims key
H1:  survives leave-one-game-out over all 59 clusters and the n_claims key
```

**No reduction reversed anything.** This is a *stability* statement and reveals no
verdict: it says only that no single game and no instant-collapse changes the
answer, whatever the answer is. The downgrade rule is strictly one-way and had
nothing to downgrade.

---

## The three extra predicates registered in the brief

1. **The two-book degenerate census.** Delivered — §S6 above, and it returned
   more than was asked: not merely zero in the clean population, but **zero
   two-book degenerate fairs anywhere in the record**, all 21 observed
   degenerates being one-book. The undercounting ULP signature was avoided as
   instructed; on this record it makes no difference and that is reported as a
   number (**0**), not argued.

2. **Post-anchor `book_count` distribution, and duplicate-price-vector pairs
   surviving anchoring in `books_used`** — **NOT REACHABLE. Skipped.**
   **[COMPUTED FROM CODE — `/api/ledger`'s SQL is
   `SELECT r.*, f.p_multiplicative, f.p_additive, f.p_power, f.p_shin,
   f.p_conservative FROM recommendations r LEFT JOIN fair_prices f ...`, and
   `_serialise` whitelists 38 keys]** — neither `book_count` nor `books_used`
   appears in the query or the payload. Verified against the live payload's key
   set. **No deploy is proposed to get them and no different cut is
   substituted.**

3. **Observed `market_width` distribution** — **NOT REACHABLE. Skipped.** Same
   evidence: `market_width` is on `fair_prices` and is not selected by the route
   or emitted by `_serialise`.

**A partial substitute exists and is reported without being dressed up as the
thing asked for:** `too_few_books` fires iff `book_count < 2`, so the per-code
census bounds the low tail — **245 of 1,564 rows (15.7%) had `book_count < 2`**,
and every clean row has `book_count >= 2`. That is one bit of the distribution,
not the distribution.

---

## Provenance — and the count of the assumed

Every number above is labelled **[COMPUTED FROM CODE]**, **[MEASURED FROM DATA]**
or **[ASSUMED]**.

> **Assumed inputs: 1.** A1 — that an MLB or WNBA moneyline has exactly two
> settling outcomes, so a `NO` on one ticker and a `YES` on the other name the
> same claim. **Its registered detector ran and passed on all 59 clusters**
> (`non-normalisable clusters = 0`), so A1 did not fail silently.

No other quantity in this document is assumed. Nothing was imputed: unreadable
resolved to `None` and was counted, never to `0`.

---

## What this measurement does not establish

Registration §10 is reproduced verbatim by the harness (`§S13` of the run log)
and governs. Beyond it, this run adds four of its own:

- **It declared nothing.** R3 tripped and no claim was evaluated for a verdict.
  Nothing here licenses the refutation ADR, licenses the sentence *"the nearest
  is 0.21c short"*, forbids that sentence, closes ADR 0019, or authorises any
  change to `tasks/NEXT.md`.
- **The census statistics are printed and a reader can derive the verdicts from
  them.** Stated above rather than hidden. Any amendment to R3 is being written
  with the numbers visible.
- **§10's "45 rows" bullet is a slice number (137 on the table)** — Finding 2 —
  and §S item 10's "symmetric difference 0" is a slice number (15 on the table) —
  Finding 1. Both are reported for the registrar. **Neither has been amended.**
- **The deployed revision of `suppression.py` is not pinnable to a SHA**, so
  every statement here about what the deployed build *contains* rests on the
  record's own behaviour (0 occurrences of `inconsistent_consensus_metadata`;
  1,421 consecutive invariant-respecting rows) and on the deploy *timestamp* —
  not on the repository. In particular, whether the build serving this pull
  carries ADR 0019's added check is **unknown**, and does not matter: §V's part
  (c) fails either way.
- **`market_width`, `book_count` and `books_used` were not observed at all.** Two
  of the three extra predicates are unanswered and remain so.

---

# Addendum A — the five verdicts, released

**Appended 2026-08-09.** Append-only. Everything above this line is committed
text and stands exactly as written — including the five `WITHHELD — STOP THE
LINE` lines in §S6, §S7, §S8 and §S9, and the `THE RUN STOPPED. No claim is
declared.` banner. **None of it is edited.** Where those lines read `WITHHELD`,
they are **superseded by reference** by §AD2 below, in the same way the
registration's `| Amendments | none |` row is superseded by Amendment A rather
than corrected in place.

## §AD0. The authority, and why a withheld verdict is now stated

**Amendment A**, appended to
[`2026-08-10-preregistration-clean-shortfall-distribution.md`](2026-08-10-preregistration-clean-shortfall-distribution.md)
and committed at **`3a0716d`** (*"measurement: Amendment A — R3's saturation
clause is a labelling rule, and H3b is REFUTED"*). Sections **§A2** (the
drafting conflict), **§A3** (the ruling), **§A5** (the verdicts).

The ruling, verbatim from §A3:

> **A stop-the-line guard may only be predicated on a cut that at least one
> hypothesis's decision rule reads.** A guard predicated on a partition of the
> population that no registered decision rule evaluates is a **labelling rule**:
> it attaches its banner to that partition and forbids the partition's use in
> any conclusion, and it **may not withhold a verdict**.

Applied to this run: **no hypothesis's decision rule reads Grid D.** H1 is a
maximum over observations, H2 a share over the cluster partition, H3a and H3b
per-row paired quantities, H4 a count — verified against §7 and against
`scripts/run_clean_shortfall.py:359-406`. R3's saturation clause is therefore a
labelling rule here, and the five verdicts it withheld are released. **R1, R3's
`G < 2` twin and R4's H4 twin keep stop-the-line status** and all three passed
on this run independently of the ruling.

**The ruling was made with these numbers already public**, and Amendment A §A0
declares it: the census was committed at `3f2fa1a` and pushed to a public
repository before any ruling existed. That disclosure travels with this
addendum. **The rule producing each verdict below was fixed before the run and
is quoted verbatim beside it; the rule about which guards may withhold a verdict
was not.** This is an open ruling on a drafting conflict, not a
re-registration, and no verdict below may be cited as though it were the latter.

## §AD1. What did not change

The pin (`1564`), the pull, the population, the cluster key, the dedup key, the
cuts, the estimators, the five decision rules and the stopping rule are all
untouched. **No re-pull. No recomputation. No new cell.** Every statistic in
§AD2 is one already printed in §S2–§S12 above and already committed at
`3f2fa1a`. §8's *one pull, one pin, one look* stands.

## §AD2. The five verdicts

Reported in the registered order — H4 first because it can contaminate H1, H1
last because its answer was already known.

| Claim | Registered rule (§7), verbatim | Statistic, as printed above | Verdict |
|---|---|---|---|
| **H4** | *"**Declared** iff `n_degen == 0`."* | §S6: `n_degen` clean = **0**; suppressed (the paired control) = **21**; narrower ULP signature returns the same 21; clean rows in `ask ∈ [440,479]` = 0 | **DECLARED** |
| **H2** | *"**Declared** iff `max_game_share <= 0.50`."* | §S7: `17 / 323 = 0.0526`, largest cluster `KXMLBGAME-26AUG091605DETSF` | **DECLARED** |
| **H3a** | precondition `n_spread >= 5`, then *"**Declared** iff `median over those observations of (S − spread_tenths) > 0`."* | §S8: `n_spread = 323`; paired median **+22.70** on both nearest-rank and interpolated conventions; `S > spread_tenths` on 319 / 323 | **DECLARED** |
| **H3b** | *"**Declared** iff `S_min > spread_at_min`."* | §S8: `S_min = 2.0534`, `spread_at_min = 2.3191`, one attaining observation (id 726), no tie | **REFUTED** |
| **H1** | *"**Declared** iff `max over clean deduplicated observations of E1 <= 0`."* | §S9: `max E1 = −2.0534` tenths; zero observations with `E1 > 0` | **DECLARED**, carrying **`REPRODUCTION — NOT A NEW OBSERVATION`** |

**H1's label is mandatory and mechanical, not editorial.** `n_new = 0`: all 15
rows written between `id 1549` and `pin 1564` are suppressed (§S2), so the clean
population is byte-identical to registration §0.2's and H1 was arithmetically
incapable of returning anything else. **H1 is a checksum and may not be cited as
a new observation.**

**§7's one-way downgrade rule had nothing to downgrade.** §S12: all five survive
leave-one-game-out over all 59 clusters and the `n_claims` key. That is a
*stability* statement and stability is not support — it says only that no single
game and no instant-collapse changes an answer. That §S12 disclosed stability
for verdicts the run had declined to state is recorded as a recurrence in
`tasks/lessons.md`, under *"Suppressing a conclusion is not suppressing the
finding"*.

## §AD3. H3b is refuted. What is now forbidden, and what replaces it

`S_min = 2.0534` tenths against `spread_at_min = 2.3191` tenths: **the nearest
clean observation's shortfall is smaller than that same observation's own
devig-method spread.** In the registration's own words, required by §7 in these
words: **the nearest clean observation is not distinguishable from clearing.**

**Therefore the sentence *"the nearest is 0.21c short"* may not be written** —
not in the refutation ADR, not in `tasks/NEXT.md`, not anywhere. Occurrences
already written, **requiring annotation** (recorded here and in Amendment A
§A6 item 2; not discharged, as those files are other lanes'):

- `tasks/NEXT.md:345` — *"the best misses by 0.21c"*
- `docs/measurements/2026-08-10-joint-bound-result.md:111` — *"in the slice
  misses the fee by 0.21c"*
- `docs/measurements/2026-08-10-joint-bound-result.md:400` — *"−2.1 tenths
  (0.21c short)"*

`tasks/NEXT.md:150` already anticipated that the sentence *"may not be writable
at all"*; it needs the answer, not a correction.

**What replaces it, and it is sign only:**

> **No clean observation clears the deployed fee.** How far the nearest one
> falls short is **not resolvable by this measurement**, at this `n` or at any
> `n`, because the limiting quantity is the devig-method spread rather than the
> sample size.

**No magnitude language is licensed.** §S13, reproduced by the harness at run
time from the registration's power check: *"**The magnitude is not resolvable;
only the sign is.** No statement of the form 'the strategy nearly clears' or
'clearly misses' is licensed at any `n`."* That includes any
multiple-of-its-own-noise figure. The ban is recorded as having bound in
practice in Amendment A §A6 item 4, and the figure it forbade is named there
rather than repeated here.

**And, in these words, as §7 requires when H3a is declared and H3b refuted:
H3a may not be described as having answered H3b.** H3a is a statement about the
typical observation; H3b is a statement about one order statistic; declaring the
first says nothing about the second.

## §AD4. The R3 label still binds. Releasing the verdicts did not release the cut

Grid D keeps its **`DEGENERATE — DOES NOT DISCRIMINATE`** banner. **Neither Grid
D nor Grid B may be referred to in any conclusion**, and no cell in either may be
reported as significant or described with any word implying a test. That
prohibition is the entirety of what R3's saturation clause now does, and
Amendment A relaxed no part of it.

Grid D's 99.1% concentration remains what §S11 said it was: a fact about which
prices the recorder writes — near-even moneylines — and **descriptive**.

## §AD5. The staleness caveat, with its direction argued rather than asserted

**The defect.** `odds_age_ms` derives from The Odds API `last_update`, which the
evidence says is a **scrape** stamp rather than a per-line reprice stamp: **320
of 320** book+event pairs quoting more than one priceable market share one stamp
across every market they quote (`tasks/NEXT.md` item 1, ADR 0020 pending; the
confirming measurement is registered in
[`2026-08-10-preregistration-odds-last-update-repeat-poll.md`](2026-08-10-preregistration-odds-last-update-repeat-poll.md)
and is **not yet a verdict**). So **true line age is bounded below, not
measured, by `odds_age_ms`**, and a row that passed `stale_odds` is *not proven
fresh*. **The clean 323 carries unmeasured staleness.** This is not a hedge — it
is a named hole and it is not closed by anything in this run.

**The argument that it runs against H1, and it holds — for H1, in direction
only.** If the error a stale line induces in `fair_probability` is two-sided,
then it adds variance to `E1` without shifting its centre; and the maximum is a
convex function, so independent mean-zero perturbations can only **raise** the
expected maximum. H1's falsifier is `max E1 > 0`. **The confound therefore
pushes toward falsifying H1, and H1 was declared anyway.** That is a real
robustness statement about H1's declaration and it survives.

**Three qualifications, all of which must travel with it.**

1. **Two-sidedness is [ASSUMED], not measured.** It requires the consensus fair
   to be unpredictable in sign over the unmeasured staleness interval. Nothing
   in this repo measures that, and a systematic drift correlated with the side
   being priced would give the error a sign. The repeat-poll capture cannot
   answer it either: it measures whether the **stamp** advances, not whether the
   **price** drifts.
2. **The perturbations are not independent across the 323.** Every row from one
   odds sweep is priced off one scraped snapshot, and §S4 shows 291 collapsed
   groups with a median of 4 observations per cluster. The number of independent
   staleness draws is far below 323, which **shrinks** the upward push on the
   maximum without reversing it. The argument therefore licenses a **sign and
   nothing else** — consistent with §S13, which forbids magnitude claims here
   anyway.
3. **It does not transfer to H3b, and applied consistently it runs the other
   way.** `S_min = −max E1`: they are one displacement with opposite sign,
   attained by the same observation (id 726). Whatever pushes `max E1` up pushes
   `S_min` down, and a smaller `S_min` makes `S_min > spread_at_min` **harder** —
   so the confound makes H3b **easier to refute**. That does not invalidate the
   refutation, because refuting H3b yields a **prohibition on a sentence**, not
   a positive claim: a confound that makes a prohibition more likely can only
   over-restrict, never over-claim. **But "the confound ran against the result"
   is true of H1 and false of H3b, and the two must not be stated as one.**

Partly offsetting, and worth one line rather than a paragraph: H3b's comparison
is **paired within one row** (§5), and both `S` and `spread_tenths` are computed
from the same stale snapshot, so the pairing absorbs whatever staleness moves
the two terms together. It does not absorb what moves them differently, and how
much of each there is has not been measured.

## §AD6. What this release does not license

Registration §10 governs in full and is reproduced by the harness at §S13.
Beyond it, this release adds:

- **It does not make any released verdict a new observation.** H1 is a checksum
  (`n_new = 0`). H2, H3a, H3b and H4 are census statements about one pinned
  snapshot of one recording window in two leagues in August, with **no interval
  anywhere** and no inference to any other row.
- **The denominator is `n_obs = 323` observations in `G = 59` clusters**, with a
  hardest floor of `n_claims = 118` — roughly two per game. §9 requires exactly
  these beside any citation of the result and **forbids quoting `n_rows = 614`
  alone**. The **29** that circulates elsewhere in this repo is the count of
  *scored* games on the gate screen; it is a different population answering the
  CLV and settlement question, and it is **not** this measurement's denominator.
- **Clean population only.** 614 clean rows of 1,564; 950 are suppressed. And
  per §2 the clean set is **defined partly by the dependent variable** —
  `suspicious_edge` removes stored edges above 40.0 tenths, and
  `edge_within_method_noise` removes stored edges in `(0, spread_tenths]`. §S10
  Finding 2 measures the consequence: **137 suppressed rows on the whole pinned
  table carry a positive net edge** (45 in the newest-1,000 slice). Anyone
  quoting this result as "there is no edge in the record" has read the wrong
  population.
- **The honest claim, and it is the only one licensed:** *"Kalshi is not
  mispriced relative to a consensus it may itself lead."* The sentence *"no edge
  exists at Kalshi"* is **forbidden** — the same prohibition the joint-bound
  registration carries. If Kalshi is the sharp side, "Kalshi versus devigged
  sportsbook consensus" is close to empty by construction, and finding nothing
  in it is a fact about the instrument's geometry rather than about the venue.
- **The clean rows are not proven fresh** (§AD5), and the deployed revision of
  `suppression.py` is still not pinnable to a SHA.
- **`market_width`, `book_count` and `books_used` were never observed.** Two of
  the three extra predicates remain unanswered, as stated above.
- **The refutation ADR is not written here**, and nothing in this addendum
  writes it. §9 licenses it on this branch — H1 declared with `n_new == 0` —
  and requires that it **cite registration §0.2 for the number and this run only
  for the denominator and the distribution.**
