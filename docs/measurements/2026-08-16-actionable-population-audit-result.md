# The first actionable rows — audited. Verdict: OVERSTATED

**Instrument:** `scripts/inspect_live_db.py actionable-audit` (added `1cdb429`,
deployed, run against `/data/cockpit.db` on `kalshi-cockpit` 2026-08-16).
**Population:** `gate.POPULATIONS["actionable"]` over the **whole table** — no
CLV filter, no age term, no pin. Three rows, and that is the entire record.
**Audit:** `measurement-skeptic`, which re-derived every figure independently.

Something real is here. It is much narrower than "actionable went from 0 to 3",
and the *timing* framing in `tasks/NEXT.md` does not survive.

---

## 1. The correction that has to lead: the transition was not on 2026-08-16

`tasks/NEXT.md` offered two explanations, both premised on the 17:32Z staleness
deploy (ADR 0030) having caused these rows. **All three `created_ms` predate it,
two by roughly twenty hours.**

| id | created | market | claim |
|---|---|---|---|
| 4861 | **2026-08-15T19:52:14.225Z** | `KXMLBGAME-…BOSPIT-PIT` yes | moneyline |
| 6174 | 2026-08-15T21:56:31.890Z | `KXMLBGAME-…BOSPIT-PIT` yes | moneyline (same claim) |
| 7349 | 2026-08-16T17:06:36.369Z | `KXMLBHIT-…WSHACHAPARRO87-1` yes | prop |

**The first actionable row in this project's history was written
2026-08-15T19:52:14.225Z.** Neither explanation in `NEXT.md` survives, because
both require a cause that did not yet exist.

### Why nobody saw it: two instruments, and the wrong one was consulted

**The instrument that was cited had an empty denominator for this question.**
`clv-coverage` sections D, E and G all run through `_CLV_CLUSTER_SELECT`, which
carries (`scripts/inspect_live_db.py:527-528`):

```
WHERE r.clv_scored_ms IS NOT NULL AND r.clv_tenths IS NOT NULL
  AND r.clv_horizon_hours = :horizon
```

An actionable row is by construction written **before** commence
(`backend/runner.py:1241`, `:856` drop any candidate where
`commence_ms <= stamp`). Until its game reaches the closing line it has
`clv_scored_ms IS NULL` and is **invisible** to that query. So the read that
reported "actionable is provably empty" was measuring a population from which
the entire class of interest had been removed. **The 0 → 3 transition is a
transition in the scoring population, not in the strategy's output.**

**The instrument that would have answered it runs every 900 s and is
phone-reachable.** `gate.population_counts` (`backend/gate.py:332-359`) has no
CLV predicate; `backend/api/routes.py:1302` publishes it over the whole table at
`since_ms=0` on `/api/gate`, and `scripts/run_loop.py:435` prints it every full
pass. **That counter read ≥1 continuously from 2026-08-15T19:52Z.** Nobody
looked.

### Three assertions in the record were false when written

| Claim | Committed | Rows already actionable |
|---|---|---|
| `docs/adr/0030-…:184` "`actionable` has been zero for the life of the project" | 2026-08-16 16:50Z | 2 |
| `docs/adr/0031-…:34-35` "`actionable` is simply empty … as it has been for the life of this record" | 2026-08-16 18:14Z | 2 |
| `docs/adr/0032-…:92` "`actionable` has been 0 for the life of the record" | 2026-08-16 19:01Z | 2 |

`CLAUDE.md` carries the same claim. The last **whole-table** measurement of
`actionable = 0` is ADR 0021's pin (`pin = 1564`, 2026-08-10). Everything after
that is repetition, and the one intervening measurement had a denominator that
excluded unstarted games.

`NEXT.md:377-380` had already flagged this as follow-up #1 — *"`actionable = 0`
… currently rests on an inference"* — and it was asserted three more times
anyway.

---

## 2. The arithmetic is sound. Every threshold clears, and the audit reproduced it

`p_conservative == min(four methods)` on all three rows to the last bit
(`backend/core/devig.py:215-222`). `method_spread` is max-minus-min over exactly
those four, converted at `backend/core/suppression.py:351`.

| id | devig spread (tenths) | `edge_tenths` | margin |
|---|---:|---:|---:|
| 7349 | 0.868 | 3.618 | +2.750 |
| 6174 | 1.585 | 5.456 | +3.871 |
| 4861 | 1.489 | 3.490 | +2.001 |

`edge_tenths` reproduces to 1e-12 from
`1000·p_conservative − ask − 1000·ceil₀.₀₀₀₁(0.07·1·P·(1−P))`. Depth
(629.9 / 261.4 / 548.5) clears the 10-contract floor; widths (0.023 / 0.006 /
0.011) clear 0.06; the 12.07-minute `odds_age` on 4861 is 80.5% of the bound.
Reference sizing reproduces exactly at quarter-Kelly on $1,000: 3 / 5 / 3.

**Check 4 passes cleanly and is worth saying out loud, because it is what killed
the predecessor project.** `entry_ask_tenths` is the derived ask, never a mid
(`engine.py:44`; `runner.py:1290-1298`), and `sizing.py:196` sizes against
`effective_price` = ask + fee. These buckets are built from the price you would
pay.

**ADR 0028's fee correction flipped exactly one row.** Under the pre-2026-08-14
fee ($0.02 at both 470 and 500 tenths), row 4861's edge would have been 0.990
tenths against a 1.489-tenth spread — suppressed as `edge_within_method_noise`.
6174 and 7349 would still have passed. The fee correction is a real contributing
cause of one row, and nothing establishes that the flip was toward truth rather
than toward a smaller safety margin.

---

## 3. Three rows are not three opportunities

6174 and 4861 are the same `(ticker, side)` at the **same ask (500 tenths)**,
re-priced off two consensus readings 2 h 04 m apart that moved by 0.20
probability points. So:

- **3 rows, 2 distinct claims, 2 games, 2 clusters.**
- **The largest contributor carries 2 of 3 rows (67%).**
- The two BOSPIT rows are **not independent observations.**

The honest form is *"one baseball moneyline, observed twice, plus one prop."*

---

## 4. Nobody could have bet these, and one column says so misleadingly

`suggested_contracts = 0` on all three at the deployed $100 bankroll
(`fly.live.toml:288-289`); reference sizing reproduces at 3 / 5 / 3. They are
evidence at the fixed $1,000 reference profile only (ADR 0015).

They were never rendered as cards either: `routes.py:954` counts a row as
surfaced only when `suggested_contracts > 0`, so the operator saw them struck
through.

**`ev_net_dollars = 0.0` is not an EV measurement.** `engine.py:251` writes
`ev.ev_dollars if contracts else 0.0`, and `contracts` is the deployed size. So
on **every** actionable row this column is structurally zero — a zero meaning
"no measurement" sitting in a column named EV. No downstream analysis may
average it.

**The Board contradicts the gate in prose.** `engine.py:332-333` writes
`"No edge."` when `contracts == 0`, and that is `suggested_contracts`. All three
rows read *"(+0.5c after fees). No edge."* At a $100 bankroll every row reads
"No edge." regardless of its edge — the phrase reports the size of the deposit
while naming it a property of the market. This is ADR 0015's own defect
surviving in the prose layer.

---

## 5. The lead alternative explanation: all three are soft-book fallbacks

`anchored_on_sharp = 0` on all three, and **no suppression check requires a
sharp anchor** — the column is written at `runner.py:581` and read by nothing in
the risk path. `devig.py:290-291`:

```python
sharp = {b: r for b, r in usable.items() if sharp_books and b in sharp_books}
selected = sharp or usable
```

So a zero there means **no sharp book quoted, and the fallback to the full
soft-book set was taken silently.** All three rows were priced against a soft
consensus.

ADR 0021 §8's annotation records that on the pinned table, the 423 fallback rows
produced **0 positive edges among the 189 unsuppressed, and 0 actionable**.
**The first three actionable rows in project history are 3 for 3 fallback
rows.** n = 3, so this is a lead and not a result — but it is the single most
plausible competing explanation, and nothing measured so far separates it.

Two supporting details:

- The prop's consensus is **three US recreational books** (betmgm, betonlineag,
  draftkings), with an overround of 0.068 against the moneylines' ~0.046.
  `overround` is stored and **read by no check**.
- Row 6174's 13 "books" contain at least two same-operator pairs —
  `betonlineag`/`lowvig` (one pricing engine, two skins) and
  `winamax_de`/`winamax_fr` — so `book_count = 13` overstates the independent
  opinions and `market_width = 0.00566` is partly measuring agreement between
  duplicates. `usable_book_count` is computed (`devig.py:339`) and **not
  stored**, so the record cannot say whether Pinnacle quoted and was rejected or
  never quoted at all.

---

## 6. What was suspected and is REFUTED

The pre-audit reading suspected the re-confirmation path of refreshing clocks
without re-checking staleness, leaving a stale row surfaced with fresh-looking
timestamps. **Half right, and the dangerous half is wrong.**

Confirmed: `confirm_recommendation` (`engine.py:437-443`) updates only the three
clock columns and does **not** re-evaluate suppression, and `persist_if_changed`
(`engine.py:489-502`) compares only ask and fair — so a candidate whose only
change is ageing odds records once, not twice. This is documented as deliberate
at `engine.py:469-472`.

Refuted: the confirmation does **not** make the row look fresher. Reconstructing
the odds-observation instant from both bases gives **byte-identical** answers on
all three rows:

| id | `created_ms − odds_age_ms` | `last_confirmed_ms − last_confirmed_odds_age_ms` |
|---|---:|---:|
| 7349 | 1 786 899 882 000 | 1 786 899 882 000 |
| 6174 | 1 786 830 807 000 | 1 786 830 807 000 |
| 4861 | 1 786 822 810 000 | 1 786 822 810 000 |

The confirmation carried the same snapshot forward with its age correctly
advanced, which is exactly what `gate.live_ages` (`gate.py:830-883`) requires.
**This is a guard that was built correctly and is working.**

The residual, stated honestly: the `actionable` **counter** has no age term at
all, so it counts creation-instant decisions and always will. Defensible — CLV
scores a decision made at an instant — but the counter and the screen answer
different questions and the counter's is the more permissive one.

The real cost of the design choice is elsewhere: the suppression log
**systematically undercounts `stale_odds` for exactly those candidates that were
once actionable**, so any "how often did this go stale" measurement over
`suppressed_reason` is biased against the rows that matter most.

---

## 7. Three findings the audit surfaced that were not asked for

**A. The Skeptic agent has never fired on this population and structurally
cannot.** `runner.py:1390` selects review targets on `c.recommendation.surfaced`,
and `engine.py:95-96` defines `surfaced` as `suppressed_reason is None and
suggested_contracts > 0` — **`suggested_contracts`, not `reference_contracts`.**
At $100 that is 0 on every row this tool has ever produced. So the adversarial
review layer, whose entire job is to attack rows that clear the gauntlet, has
never run on the population feeding the 300-game floor. Two definitions of "the
strategy would bet this", diverging exactly where the deposit is small. By this
repo's own standard, it is decoration on the path that matters.

**B. `suppressed_reason` has a vocabulary wider than the strategy hash covers.**
`ALL_CHECK_NAMES` is not exhaustive: `engine.py:235-236` can write
`sizing:{binding_constraint}`, and `agents/review.py:162,182` can write a
Skeptic verdict. Only `ALL_CHECK_NAMES` enters the strategy-config hash
(`runner.py:1086`), so **a change to the Skeptic's prompt or verdict vocabulary
moves `actionable` without minting a new `strategy_config_version`** — the exact
defect ADR 0019 exists to prevent, one layer out.

**C. Multiplicity has no correction on this predicate.**
`gate.always_valid_multiplier` (`gate.py:126-182`) exists because a threshold
re-evaluated on a growing record is thousands of looks, not one — and it is
applied **only to the CLV mean**. The runner re-evaluates ~100 candidates every
900 s against a >6,200-row record. Three crossings with binding margins of
2.0–3.9 tenths against a noise floor of 0.87–1.59 tenths is well within what a
zero-edge process produces at that number of looks.

Related: the check carrying the smallest margin here has never once changed an
outcome. ADR 0021 §5.1 measured `edge_within_method_noise` firing 18 times on
the pinned table and **alone 0 times**. `wide_market` has 0 fires over 1,334
rows with a measurable width. `too_few_books` is the only consensus-quality
check that has ever bitten.

---

## What is safe to write into the record

- Exactly **three** rows in the whole live `recommendations` table satisfy
  `gate.POPULATIONS["actionable"]`: two distinct `(ticker, side)` claims across
  two 2026-08-16 MLB fixtures, largest contributor 67%.
- Every deployed threshold is cleared, with independently re-derived margins:
  post-fee edges of 3.62 / 5.46 / 3.49 tenths against devig spreads of
  0.87 / 1.59 / 1.49. The arithmetic is sound.
- All three `created_ms` **predate** the 17:32Z staleness deploy, two by ~20
  hours. **Neither explanation in `NEXT.md` survives.** The first actionable row
  was written **2026-08-15T19:52:14.225Z**.
- `suggested_contracts = 0` and `ev_net_dollars = 0.0` on all three: evidence at
  the $1,000 reference bankroll only, unbuyable at the deployed $100, never
  rendered as a card.
- All three are `anchored_on_sharp = 0` — soft-book consensus by silent
  fallback, with no check requiring an anchor.
- ADR 0028's fee correction flipped row 4861 and only that row.

## What is NOT safe to write — each is the flattering reading

- ~~"`actionable` was 0 until 2026-08-16"~~ — it was ≥1 from
  2026-08-15T19:52Z and `/api/gate` said so the whole time.
- ~~"three actionable rows"~~ without "two markets, two games, one observed
  twice".
- ~~"the strategy found an edge"~~ — three crossings at 2–4 tenths out of
  >6,000 rows, on an unreviewed, uncorrected, continuously re-evaluated
  threshold, against a soft-book consensus. The competing explanation
  (soft-consensus fallback + multiplicity) predicts exactly these observations.
- ~~"the fee correction / staleness fix let real rows through"~~ — the fee
  correction is confirmed to have flipped **one** row; the staleness fix
  post-dates all three.

## The measurement that separates the two explanations, and it needs no new data

On the live record, split the **unsuppressed** population by
`fair_prices.anchored_on_sharp` and report the rate of `edge_tenths > 0` in
each, with per-game clustering and the largest contributor's share. ADR 0021 ran
the ancestor of this query on the pinned table (423 unanchored rows, 0 positive
among 189 unsuppressed). If the unanchored rate is now materially higher, the
three rows are an artefact of **which books were admitted**, and the honest
write-up is a fact about the reference class — not about Kalshi.

## What this audit does not establish

- **Nothing about whether the rows are profitable.** CLV is the arbiter and is
  not read here.
- **Nothing about the competing explanation's truth.** It is unseparated, not
  established. n = 3.
- **Nothing about other populations.** `no_edge` and `suppressed` were not
  examined.
- **It is a census at one instant.** Rows are written only when the ask or fair
  changes, so an absent row is not a market that never qualified.
