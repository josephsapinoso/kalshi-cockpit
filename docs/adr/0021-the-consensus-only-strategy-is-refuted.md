# 0021 — The consensus-only strategy is refuted on the record to date

**Date:** 2026-08-10
**Status:** Accepted as the record of a refutation. **The decision it forces is
framed in §8 and is Joe's. This ADR does not make it.**
**Extends `0005-the-gate-counts-actionable-games` (what `actionable` counts).
Defers entirely to `0018-arming-real-trading-is-a-code-change` on arming and
moves it in neither direction. Carries ADR 0019's citation rule. Does not
pre-empt ADR 0020, which is queued and owns the `stale_odds` remedy.**

Evidence: the registered run at
[`docs/measurements/2026-08-10-preregistration-clean-shortfall-distribution.md`](../measurements/2026-08-10-preregistration-clean-shortfall-distribution.md)
(**Amendment A**) and
[`docs/measurements/2026-08-10-clean-shortfall-distribution-result.md`](../measurements/2026-08-10-clean-shortfall-distribution-result.md)
(**Addendum A**, the released verdicts; **Addendum B**, the independent audit).
Registration §9 licenses this document on the branch that occurred — H1 declared
with `n_new == 0` — and requires that it cite **§0.2 for the number** and **this
run only for the denominator and the distribution**. It does.

---

## 1. The claim, in the only words the record licenses

> **Kalshi is not mispriced relative to a devigged sportsbook consensus it may
> itself lead.**

That is the whole finding. The sentence it is **not**, and which is forbidden by
the registration and by the joint-bound registration before it:

> ~~*No edge exists at Kalshi.*~~

The distinction is the point of this document rather than a caveat on it. The
measurement compares Kalshi against a consensus built, by design, from
`betfair_ex_eu` + `matchbook` (± `pinnacle`). If Kalshi is the sharp side of that
comparison, then "Kalshi versus devigged sportsbook consensus" is close to empty
**by construction**, and finding nothing in it is a fact about the instrument's
geometry rather than about the venue. §7 states that at full strength.

And the subject of the sentence is exact. It is **the consensus-only strategy**
that produced zero — not "the documented strategy". The second phrasing credits a
two-signal system that has never run (`CLAUDE.md`; `backend/model/elo.py` has no
production caller and `model_probability` is `NULL` on every row).

---

## 2. The evidence, and its denominators

**Zero clean rows clear the deployed fee.** `max E1 = −2.0534` tenths over the
clean population; zero clean deduplicated observations have `E1 > 0`, so H1's
enumeration clause had nothing to enumerate.

**The denominator, stated the way §9 requires it to be stated:**

| Quantity | Value | What it is |
|---|---:|---|
| `n_obs` | **323** | distinct `(cluster, instant, claim)` — the registered unit |
| `G` | **59** | distinct game clusters — the independence unit |
| `n_claims` | **118** | distinct `(cluster, claim)` — the hardest floor, ~2 per game |
| sweeps | **34** | distinct `created_ms` recording instants |
| `n_rows` | 614 | clean **rows**. Rows are uptime. **May not be quoted alone.** |

> **When stating how much evidence exists, say `59 games across 34 recording
> instants`.**

**Not 29.** The `29` that circulates elsewhere in this repo is the gate screen's
count of *scored* games; it answers the CLV and settlement question over a
different population, and using it here contradicts the result document's own
§S3. And **not 323 as an independence claim**: every row in a sweep is priced off
one odds snapshot, so the sweep is the dependence unit, the largest single sweep
carries **60/323 = 18.6%**, and that is more than triple the largest *cluster*'s
**5.3%** (`KXMLBGAME-26AUG091605DETSF`, 17 of 323). CLAUDE.md's
largest-contributor rule points at the sweep; both measurement documents printed
the cluster, and Addendum B §B3 supplies the number they omitted.

**Whole-table figures, from registration §0.2's pinned pull:**

```
unsuppressed rows                                614   in 59 games
  ...with a positive NET edge at the deployed fee  0
actionable rows anywhere in the table, ever        0
614 matches /api/gate's published no_edge count exactly
```

Per ADR 0019's citation rule, the 614 spans two strategy-config versions —
**578 clean rows under v1, 36 under v2** — and the boundary sits at id 1395. No
suppression threshold is observed to have moved across it, but the config body is
not readable over HTTP, so that is inference and is labelled as such in the
result document's §S5.

**The parts agree with the pooled number**, which is the condition CLAUDE.md sets
before a pooled number may be read at all: **every one of the 59 per-game maxima
is negative**, and the claim survives leave-one-game-out over all 59 clusters and
the `n_claims` key.

**And the population is only the clean one.** 950 of 1,564 rows are suppressed,
and **137 of them carry a positive net edge on the whole pinned table** (45 in
the newest-1,000 slice — Addendum A's Finding 2 corrects the slice figure that
registration §10 quotes). Anyone reading this ADR as "there is no edge in the
record" has read the wrong population.

---

## 3. What the release actually adds is ONE bit, and it is H3b

Five verdicts were released. **Presenting them as five corroborating results
would overstate the evidence**, because four were forced or near-forced before
any data was read. Addendum B §B1 item 4:

| Claim | Reach of its falsifier |
|---|---|
| **H1** — no clean observation clears | **Arithmetically impossible** to differ: `n_new = 0`, so the clean population is byte-identical to §0.2's |
| **H2** — no game dominates | Refutation needs **>161** observations in one cluster; observed max is **17** |
| **H4** — no fabricated fairs in the clean set | All 21 degenerate rows carry `too_few_books`; a **logically prior** check catches every one |
| **H3a** — the typical shortfall exceeds method noise | Prior disclosed at §R4 as *"leans declared"* |
| **H3b** — the **nearest** observation's shortfall exceeds its own method noise | **The only genuine coin flip — and it refuted** |

H2's declaration is evidence that the recorder sweeps all live games at once, not
that the record is well distributed. H1 carries the mandatory label
`REPRODUCTION — NOT A NEW OBSERVATION` and **may not be cited as a new
observation**: it is a checksum on §0.2.

**H3b is the bit.** `S_min = 2.0534` tenths against `spread_at_min = 2.3191`
tenths, one attaining observation (`id 726`, `KXMLBGAME-26AUG091335NYMPIT-NYM`,
`side=yes`, `ask=450`), no tie. The registered rule is *"Declared iff
`S_min > spread_at_min`"*. It is not. So, in the registration's own required
words:

> **The nearest clean observation is not distinguishable from clearing.**

**Therefore the sentence *"the nearest is 0.21c short"* may not be written** —
not here, not in `tasks/NEXT.md`, not anywhere. Nor may any statement of the form
*"the strategy nearly clears"* or *"clearly misses"*, at any `n`, nor any
figure expressing the shortfall as a multiple of its own noise. The magnitude is
not resolvable and the sample size is not why: the limiting quantity is the
devig-method spread. That ban was registered **pre-run**, in the power check, and
Amendment A §A6 item 4 records it binding in practice against a headline that was
nearly proposed.

**And, in these words, as §7 requires: H3a may not be described as having
answered H3b.** H3a is a statement about the typical observation; H3b is a
statement about one order statistic; declaring the first says nothing about the
second.

---

## 4. What the R3 ruling bought — and the refutation was not it

The run tripped `STOP THE LINE` on R3 (Grid D's middle cell holds 99.1% of
observations) and withheld all five verdicts. Amendment A ruled that R3's
saturation clause is a **labelling rule**, not a stop-the-line, and released
them.

**Restate the ruling in these words, and never in the looser paraphrase:**

> **No decision rule *partitions or stratifies by* Grid D.**

Not *"reads"*. `E1` is `1000·fair − ask − fee_tenths(ask)`, and `fee_tenths` **is**
Grid D's generating function — §4 derives Grid D by sweeping exactly it — so H1,
H3a and H3b all evaluate that function pointwise on every row. "Reads" is
literally false. The ruling stands on the **partition** property, which is the
only property R3's saturation clause could bear on. Amendment A §A2's closing
line already says this correctly; §A3's headline is the loose paraphrase, and
Addendum B §B1 item 1 corrects it.

**What the ruling bought: the denominator, the distribution, and the H3b
prohibition. It did NOT buy the refutation.** Registration **§0.2** measured
`max E1 = −2.1` tenths over the pinned table **independently of this run**, before
the registration was written and disclosed in it as a contaminating prior. Nobody
may later read the ruling as having rescued the finding.

**And §0.2 and this run are one population read twice under two pins** — the same
614 clean rows — **not two measurements.** §9's instruction to cite §0.2 for the
number and this run for the denominator is correct, and will read as two
corroborating sources unless that clause travels with it. It travels with it
here.

**Grid D keeps its banner.** `DEGENERATE — DOES NOT DISCRIMINATE`. Neither Grid D
nor Grid B may be referred to in any conclusion, and no cell in either may be
reported as significant or described with any word implying a test. Releasing the
verdicts did not release the cut. Grid D's 99.1% concentration remains what §S11
said it was — a descriptive fact about which prices the recorder writes, namely
near-even moneylines.

---

## 5. Three findings that make the refutation harder to attack

**5.1 The dependent-variable contamination is empirically inert on this pin.**
The obvious attack is that the clean population is defined partly by the outcome:
`suspicious_edge` removes stored edges above 40.0 tenths, and
`edge_within_method_noise` removes stored edges in `(0, spread_tenths]`. Measured
on the pinned table:

```
suspicious_edge            fires  86    ALONE:  0
edge_within_method_noise   fires  18    ALONE:  0
suppressed rows with E1 > 0                   137
   ...suppressed ONLY by edge-dependent codes:  0
```

**Deleting both edge-dependent checks from the deployed config would leave the
clean population byte-identical at 614 rows.** Every positive-edge row is caught
by at least one edge-**independent** check.

**Scoped honestly, because this is the finding most likely to be over-read:**
that is a fact about `pin = 1564`, **not a structural guarantee**. A future row
could be suppressed by `suspicious_edge` alone. The registration's §10 warning
stands as a warning; what this adds is that on this record it did not bite.

**5.2 H3b's refutation does not rest on one observation.** It survives every
re-cut attempted:

| Reading | `S_min` | `spread_at_min` | Verdict |
|---|---:|---:|---|
| No dedup at all, 614 clean rows | 2.0534 | 2.3191 | REFUTED |
| Registered representative rule (largest `E1`), 323 obs | 2.0534 | 2.3191 | REFUTED |
| **Opposite** representative rule (smallest `E1`) | 2.1652 | 4.9580 | REFUTED |
| Drop the attaining cluster | 2.1652 | 4.9580 | REFUTED |
| `n_claims` key, n = 118 | 2.0534 | 2.3191 | REFUTED |
| Leave-one-game-out, all 59 clusters | — | — | none declares H3b |

**The second-nearest observation refutes more decisively than the first.** The
margin at `id 726` is knife-edge; the *refutation* is not. That forecloses the
obvious attack, which is that a single row is carrying a prohibition.

One note that must travel with the table: §3 justified the largest-`E1`
representative rule as *"conservative in the direction that matters"*, and argued
it **only against H1**. For H3b the same rule keeps the smallest `S` per group —
the reading most likely to refute. It is consistent with §7's H3b tie-break, so
the direction is defensible, and since the **opposite** rule also refutes,
nothing turns on it. But §3's one-sided justification must not be quoted as
covering all five claims.

**5.3 The exact arithmetic reading of "not distinguishable from clearing".**

```
E1 + spread  =  −2.0534 + 2.3191  =  +0.2657 tenths
```

Under `p_multiplicative` the nearest clean row **clears** by 0.27 tenths; under
the conservative devig it **misses** by 2.05. That is the symmetric counterpart
of `edge_within_method_noise`, which the deployed system already applies in the
positive direction — it refuses an edge smaller than the disagreement among the
methods that produced it, and here the *shortfall* is smaller than the
disagreement among the methods that produced it.

**This pair of numbers is licensed only as the demonstration that the sign at
`id 726` is a function of devig-method choice.** It is not a statement of how far
the strategy falls short, and it does not reopen the magnitude ban of §3. Nothing
in this ADR may be quoted as *"the nearest one clears under multiplicative"* as
though that were an edge: rule 2 of `CLAUDE.md` is *use the worst of four devig
methods for any money decision*, and this row is exactly the case that rule
exists for.

---

## 6. What survives, and is worth keeping

Stated because a refutation that discards its own instrument leaves nothing to
build on.

- **The coherence result.** The suppression rules and the edge computation agree
  about which rows are garbage: every one of the 137 positive-edge rows on the
  pinned table is caught by an edge-independent check. That is a property of the
  system, and it needed no bound to establish.
- **The recorder.** 1,564 rows, complete, duplicate-free, pinned, with the four
  per-method probabilities on the payload and `p_conservative == min(four
  methods)` verified on every row. The integrity check the payload was designed
  to make possible passes on the whole record.
- **The measurement discipline.** The registration forbade its own most quotable
  sentence before the data existed, and then that clause fired. The audit
  re-derived every load-bearing statistic independently and matched to the last
  digit.
- **The denominator convention.** `59 games across 34 recording instants` is the
  honest form, and it is now written down.

---

## 7. LIMITS — the most important section in this document

A refutation is only as strong as the account it gives of how it could be wrong.
These are not hedges appended to a conclusion; several of them are reasons the
conclusion may be an artefact.

### 7.1 This is provisional in exactly the way a null at this `n` is provisional

The record is **one pinned snapshot of one 46+ hour recording window, in two
leagues, in one month.** MLB and WNBA, August 2026. There is **no interval
anywhere in the design**, deliberately: the five claims are census statements
over a fully enumerated finite population, so the family-wise error rate is
*empty* rather than controlled, and **nothing here generalises to a single future
row.** A reader who treats `n_obs = 323` as a sample size has misread it, and one
who treats `G = 59` as statistical power has misread it twice — the dependence
unit is the sweep, and there are 34 of them.

So the honest form of the claim is: *on this record, under this configuration, no
clean observation cleared.* It is not *this cannot happen*. A larger record, a
different league, a different season, or an opener rather than a mature line
could all return something else, and none of them has been sampled. **A null over
34 recording instants is a fact about 34 recording instants.**

### 7.2 What the comparison actually was — the strongest reason this may be a tautology

`consensus_devig` is anchored on `runner.SHARP_BOOKS`, and the anchoring
**discards a median of 26 of 29 usable books**, keeping `betfair_ex_eu` +
`matchbook` (± `pinnacle`). *(That figure is a fixture measurement and is not
observed on this record — **see the annotation below before quoting it**. The
mechanism it illustrates is unaffected.)*

**We have been testing Kalshi against the only references plausibly as sharp as
Kalshi.** Two betting exchanges and a low-margin book, all three of which are
themselves near-efficient, all three of which plausibly follow or lead the same
information Kalshi does. A comparison between two sharp prices returns nothing by
construction, and "returns nothing" is precisely what it returned.

This is not a footnote. It is the single most plausible alternative explanation
for the entire result, and it must not be buried at the bottom of a list. It has
two direct consequences already measured:

- `spread_tenths` measures disagreement among **three** opinions, not among the
  market. A narrow spread is partly a statement about how few opinions were
  admitted, and H3a/H3b inherit that in the direction that makes them **easier**
  to declare — which makes H3b's refutation the harder direction, and is the one
  place this limitation runs in the result's favour.
- The consensus this project calls "the market" is not the market.

> #### ANNOTATION 2026-08-10 — the mechanism above stands; **"a median of 26 of 29" is not measured on this record**
>
> **The sentence above is left exactly as written, and it is not withdrawn.**
> What follows narrows what may be quoted from it.
>
> **The provenance.** `26 of 29` comes from the registration's §0.6, where it is
> correctly labelled
> `[MEASURED FROM DATA — tests/fixtures/odds_mlb_h2h_spreads_totals.json]` and
> stated in its complementary form, *"anchoring keeps a median of 3 of 29 usable
> books"*. **§7.2 dropped the label** and applied the figure to the record's own
> rows. That fixture is a single Odds API capture with
> `captured_ms = 1786110562317` — **2026-08-07T13:49:22Z**.
>
> **The populations do not overlap, in time.** Every row's odds observation is
> `created_ms − odds_age_ms`. Over the pinned pull
> (`docs/measurements/2026-08-10-clean-shortfall-pull.json`, `pin = 1564`, all
> 1,564 rows carry both fields):
>
> ```
> fixture captured                 2026-08-07T13:49:22Z
> record odds observations         2026-08-07T19:28:12Z  ->  2026-08-09T23:35:18Z
> rows observed at or before the capture      0 of 1,564
> minimum gap, capture -> earliest row        5.65 hours
> ```
>
> **Zero rows overlap.** Unchanged on the `pin = 1549` pull
> (`2026-08-10-wholetable-pull.json`) — same range, same `0`, same 5.6471 h.
> **That is a checksum, not corroboration:** its 1,549 ids are a strict subset
> of these 1,564 and no row differs on either field. Reporting it as an
> independent replication would repeat the error §4 corrects when it says *"§0.2
> and this run are one population read twice under two pins — not two
> measurements."*
>
> **The reconstruction is exact, not an estimate.** `runner.py:629` passes the
> cycle stamp as `now` and `:731` writes the same variable as `created_ms`;
> inside, `age = now − basis` and `oldest = max(ages)`. So
> `created_ms − odds_age_ms` algebraically recovers the oldest contributing
> book's own `book_updated_ms`. Only two writers of `recommendations` exist
> (`runner.py:711`, and `seed_demo.py:267` which is demo-only), so no second
> clock enters.
>
> **Two directional checks, both run, because a reconstruction that can only err
> toward the claim it tests is worth choosing deliberately.** `odds_age_ms` is
> the **oldest** contributing book's age, so this places each row as *early* as
> the data allow — over the books that actually fed the consensus — which is the
> direction that would manufacture overlap. And the comparison is against
> `captured_ms` rather than the fixture's own latest book stamp
> (`2026-08-07T13:49:13Z`), which shortens the gap by 9.3 seconds rather than
> lengthening it. Both err toward overlap; neither found any.
>
> *Two places it is not maximally early, both bounded by one sweep interval and
> so immaterial against 5.65 hours: `oldest` ranges only over books that quoted
> **every** outcome, and `basis` falls back to `fetched_ms` when
> `book_updated_ms` is NULL.*
>
> **The number itself is not wrong — it is misapplied.** Re-derived from the
> fixture directly: across its 15 events the median h2h book count is **29**, the
> median surviving `SHARP_BOOKS` is **3**, and the median discarded is **26**.
> §0.6 computed it correctly. What did not survive the journey is the label.
>
> **There is a second gap, and it is in league.** The fixture is MLB-only; the
> record is 1,142 MLB and 422 WNBA rows. **The time gap voids all 1,564; the
> league gap voids 422 of them a second time**, on *kind*, before the clock is
> consulted at all. §0.6's own limits paragraph already says the capture is
> mature MLB, 8.9–12.4h from first pitch, and "structurally cannot contain an
> opener". None of that was carried across either.
>
> *(Three instant-counts are now in play and none may be substituted for
> another: **33** distinct odds-observation instants over all 1,564 rows; **27**
> over the 614 clean rows; and §2's **34 recording instants**, which counts
> distinct `created_ms` — a different clock — on those same 614.)*
>
> **What survives, and it is the part that matters.** §7.2's *argument* does not
> depend on the number. `consensus_devig` applies `runner.SHARP_BOOKS` on
> **every** row — that is code (`backend/runner.py:103`, `:658`;
> `backend/core/devig.py:288`), not data.
>
> **One qualification, and it must travel, because the first draft of this
> annotation got it wrong.** The anchoring is `selected = sharp or usable`. It is
> *attempted* on every row; whether it **binds** is data. On a row where **no**
> sharp book quoted, it falls back silently to the full book set — and that row
> was compared against a *wide* consensus, which is option B's proposition, not
> §7.2's. `book_count` cannot reveal it: three sharp books and three soft ones
> both read `3`. The outcome is recorded in `fair_prices.anchored_on_sharp`
> (`schema.sql:304`, written on every row since the table existed) — **and that
> column is not on this record either.** `4938701` adds it to `/api/ledger` for
> future rows.
>
> So *"we have been testing Kalshi against the only references plausibly as
> sharp as Kalshi"* holds **on every row where a sharp book quoted**, and what
> fraction that is remains **unobserved**. It stays the single most plausible
> alternative explanation for the whole result; it is not yet a measured
> property of all 1,564 rows.
>
> **The fraction is not innocent in either direction.** Rows that took the
> fallback were tested against a wide consensus *and still returned nothing* —
> which, to that extent, would mean the tautology reading does **not** cover the
> whole result. The record cannot settle it: `wide_market` fired **0** times
> over the 1,334 rows with a measurable width, but that does not discriminate,
> because the all-book width on the fixture (median 0.0213, max 0.0344) never
> approaches the 0.06 limit either. There is no proxy.
>
> Both bullets above are unaffected either way: they are statements about which
> books were admitted, not about how many were dropped.
>
> **What does not survive: the magnitude.** *How much* the anchoring discarded on
> the rows this ADR is about is **unobserved**. `26 of 29` may be quoted only as
> *"measured on one MLB fixture captured 5.65 hours before the record begins"*,
> never bare, and never as a property of the 1,564 rows. The same applies to
> §8's option **B**, which reuses the figure verbatim: the *reason* to widen the
> reference class stands on the mechanism; the size of the prize does not.
>
> **The registration refused a transfer of exactly this species, from exactly
> this fixture.** §10 — *"What this measurement cannot establish"*, line 1062 —
> writes of the same capture: *"that capture is mature MLB, 8.9–12.4h from first
> pitch, so it structurally cannot contain an opener … a zero from the fixture
> is close to worthless for this question and **must not be cited as
> corroboration**."* That sentence is about H4's degenerate-fair count rather
> than about the book count, so it is not a rule this ADR broke by name — **it
> is the same judgement, made about the same file, and it did not travel.**
> A provenance label and a stated refusal, both one document away, stopped
> nothing. That is the part worth keeping.
>
> **A likely mechanism for how the label came off**, offered as a reading rather
> than a fact: registration §R3 (line 1169) introduces the figure with *"this is
> measured on **the live anchoring**, not derived from example lines"* — true,
> and meaning *the production anchoring code applied to a fixture*. That
> sentence carries no `[MEASURED — §0.6]` tag, and one careless reading turns it
> into *measured on live data*. If so, the phrase is worth avoiding generally:
> **name the input, never only the code path that consumed it.**
>
> **Every bare reuse, from a grep — because a number that lost its label gets
> cited, and each citation then reads as corroboration for the last.**
>
> | Location | Status |
> |---|---|
> | §7.2 body, above | left as written, with an inline pointer to this annotation |
> | **§8 option B** (this document) | **annotated in place** — a decision table is the most quotable object here and the one a reader reaches without reading §7 |
> | `tasks/lessons.md:4306` | annotated in place |
> | registration line 1072 | correctly carries `[MEASURED — §0.6]` |
> | registration line 1169 | **NOT labelled** — reads *"measured on the live anchoring"*, which is the wording that invited this substitution |
> | `start.md:235` | bare — **out of this lane's scope, and the highest propagation risk of all**, since it is read at every session start |
> | `tasks/NEXT.md:206` | bare — out of scope |
> | `docs/adr/0019:522` | bare — out of scope |
>
> In the last three the figure supports a *mechanism* claim (that `SHARP_BOOKS`
> filters heavily), which is the half that survives, so none is load-bearing on
> the magnitude. They still need the label.
>
> **Why it was unobservable rather than merely unmeasured** — see the annotation
> to *"`market_width`, `book_count` and `books_used` were never observed"* in
> "What this does NOT establish" below. `81ffd9c` puts all three on
> `/api/ledger`, so a future record can answer this directly. **It does not fix
> the past**: rows already stored are unaffected, and re-measuring requires
> `odds_snapshots`, which is the first of the three queries in
> [`2026-08-10-three-queries-the-agents-could-not-run.md`](../measurements/2026-08-10-three-queries-the-agents-could-not-run.md).
>
> The generalised pattern is recorded in `tasks/lessons.md` — *a measurement's
> population must overlap the one you apply it to, in time and not only in kind*.

### 7.3 `fair_probability` is the worst of four devig methods

P6 asserts it and the record confirms it on all 1,549 rows: `p_conservative ==
fair_probability == min(four methods)`. That is a deliberate downward bias on
every fair value, so **every `E1` is a deliberately shrunk number** and the
shortfall distribution is shifted toward "falls short" by an unmeasured,
price-dependent amount that is largest at the wings.

H3a and H3b are the only things in this design that put a number beside that
shrinkage, and **they measure the *spread* of that input, not its *bias*.** The
bias is unmeasured. It is the right posture for a money decision — rule 2 of
`CLAUDE.md` — and it is exactly the wrong posture for establishing that no edge
is there.

### 7.4 The fee is `calculate_fee`'s conservative maximum, not Kalshi's

`core/fees.py` says so in its own docstring: the published schedule returns HTTP
429 to automated fetches, the coefficients come from secondary sources, **and as
of the July 2026 revision those sources disagree with each other.** The module
returns the **maximum** across candidate models, which is why this repo's
break-even bar is 52.00% rather than the 51.75% the published coefficient would
give, and why the headroom being hunted is 0.38 points rather than 0.63.

**This project has zero fills, ever.** If both candidate models are wrong, every
number in this ADR moves. Four real fills resolve it and nothing else does.

### 7.5 `odds_age_ms` is a scrape clock, so it is a LOWER BOUND on true line age

The evidence is a census, not a proof: **320 of 320** book+event pairs quoting
more than one priceable market carry one identical stamp across every market they
quote. So `odds_age_ms` measures how long since the aggregator last polled, not
how long since the line moved, and **a row that passed the `stale_odds` guard is
not proven fresh.** The clean 323 carries unmeasured staleness.

**Cited at inference strength, deliberately.** The confirming measurement — a
repeat poll checking whether `last_update` advances while prices are
byte-identical — is pre-registered at
[`2026-08-10-preregistration-odds-last-update-repeat-poll.md`](../measurements/2026-08-10-preregistration-odds-last-update-repeat-poll.md)
and **has not returned**. ADR 0020 owns the remedy and is not written.

**The asymmetry, stated correctly, because it is routinely stated as one thing
and is two.** If the induced error is two-sided, it adds variance to `E1` without
shifting its centre, and the maximum is convex, so mean-zero perturbations can
only **raise** the expected maximum (Jensen). H1's falsifier is `max E1 > 0`.
**The confound therefore pushes toward falsifying H1, and H1 was declared
anyway.**

**That does not transfer to H3b, and applied consistently it runs the other way.**
`S_min = −max E1` exactly — one displacement with opposite sign, attained by the
same observation. Whatever pushes `max E1` up pushes `S_min` down, and a smaller
`S_min` makes `S_min > spread_at_min` **harder**. So the same noise makes H3b
**easier to refute**.

> **"The confound ran against the result" is TRUE of H1 and FALSE of H3b. The
> two must never be stated as one.**

The refutation survives that, because refuting H3b yields a **prohibition on a
sentence** rather than a positive claim, and a confound that makes a prohibition
more likely can only over-restrict. Three further qualifications travel with the
H1 half: two-sidedness is **[ASSUMED]** and unmeasured; the perturbations are not
independent across the 323 (34 sweeps, §2), which shrinks the upward push without
reversing it; and the argument licenses a **sign and nothing else**. And the
"partly offsetting" pairing argument that appeared in an earlier draft of §AD5 is
**withdrawn**: staleness enters `S` through a **level** and `spread_tenths` is a
**dispersion**, so the offset is close to nil.

### 7.6 `stale_kalshi_quote` has an empty denominator

`kalshi_quote_age_ms` is **0 on all 1,564 rows, by construction**:
`backend/runner.py:913` writes `observed_ms = now` when inserting the quote, and
`:718` differences it against the same cycle stamp. The subtraction cannot return
anything else.

So the guard fired **0** times, and that zero is **"could not fire"**, not "did
not fire". **The ask's own freshness is unmeasurable from this record.** §S10
pools that zero with five other never-fired codes, which reads as six clean
guards and is five. This is `tasks/lessons.md`'s recurring shape — *the zero that
means "no measurement" passes every threshold* — and it is named here rather than
left in a diagnostic table.

### 7.7 The harness has no tests

**Nothing under `tests/` references `scripts/run_clean_shortfall.py`.**
`verdict_h1`–`verdict_h4`, `dedup`, `claim_of`, `spread_of`, `is_degenerate`,
`fee_tenths` and `derive_grid_d` are untested; only the imported helpers are
covered. `verdict_h3b`'s tie-break branch never executed and remains unexercised.
CLAUDE.md's rule — *every guard is verified by disabling it and watching the test
fail* — was not applied to the instrument that produced this ADR.

**It is mitigated by exactly one thing, and it is worth naming rather than
generalising:** `measurement-skeptic` re-derived every load-bearing statistic
from `2026-08-10-clean-shortfall-pull.json` **with its own code rather than the
harness** — `n_obs = 323`, `G = 59`, `n_claims = 118`,
`max E1 = −2.05344379322292`, `S_min`, `spread_at_min`, the attaining row, and
every leave-one-out result — and all of them match. That is a second
implementation agreeing, which is stronger than a test suite and narrower: it
covers the numbers actually quoted and nothing else.

---

## 8. The decision this forces, framed and NOT made

**If the refutation stands, continuing is a *different* project.** Not a tuned
version of this one. The options are laid out with what each would cost, and
**the call is Joe's.**

| Option | What it is | What it would cost |
|---|---|---|
| **A. Stop the consensus-only line** | Accept the refutation, keep the recorder and the measurement discipline as the asset they are, and stop looking for taker edge against devigged sportsbook consensus. | Nothing further to build. The sunk cost is already sunk, and the record stays useful as a baseline for anything that comes next. |
| **B. Change the reference class** | The comparison discarded a median of 26 of 29 books (§7.2) — **[ANNOTATED 2026-08-10: that figure is measured on one MLB fixture captured 5.65 h before this record's earliest odds observation, overlapping it on 0 of 1,564 rows. The *reason* to widen stands on the mechanism; the *size of the prize* is unobserved. See §7.2's annotation.]** Comparing against a *wider* consensus tests a different proposition: whether Kalshi is mispriced relative to the market rather than relative to the sharps. | A new ADR and a new registration. It also weakens rule 1 (*a large apparent edge is a bug*) — a wider consensus produces more apparent edge, most of it garbage, and the suppression layer would be doing more work with less justification. Cheap in credits, expensive in discipline. |
| **C. Invert the frame** | Use Kalshi as the *sharp reference* against a softer venue. If §7.2's tautology reading is right, that is the direction the information actually flows. | A second venue's prices and a matching layer. The previous project measured Kalshi↔Polymarket text matching at **0.56%**, with the matches themselves wrong — so "matching" is the whole problem, not a detail. A genuinely new project. |
| **D. The maker path** | A 50.44% bar instead of 52.00%, a different fee curve, and liquidity provision rather than price-taking. | ADR 0017 owns it and it is **proposed, not accepted**. Its own adverse-selection counterargument is 1.50c and no named row has ever cleared it. It also needs the fee model resolved to mean anything. |
| **E. Resolve the fee model first** | Four real fills through `/portfolio/fills`, placed by hand in the Kalshi app. Already authorised. | Small money, no code. It does not create an edge — but §7.4 means **every number in this ADR moves if the model is wrong**, and this is the only thing that closes it. It is the cheapest way to find out whether the refutation is measuring what it thinks it is. |
| **F. Keep recording and re-read at a larger `n`** | A new registration over more games, other leagues, or openers rather than mature lines. | Odds credits and calendar time. §8 of the registration is explicit: a second look is a **new registration**, not an amendment — a threshold re-evaluated against an accumulating database crosses eventually with probability 1. And §7.1 means the null is provisional, so this is a legitimate option rather than a refusal to accept the answer. |

**These are not ranked and no recommendation is made.** B, C and D are each a
different project with a different question; E is orthogonal and cheap; A and F
are the two honest readings of the same result.

---

## 9. What this ADR does NOT do

- **It does not close lines it did not test.** It says nothing about
  **calibration** (whether `fair_probability` is *right* is a different question
  with different inputs — `kalshi_markets.result`), nothing about **CLV** (no row
  here is scored; that registration is **UNDERPOWERED until G = 300**), nothing
  about the **maker path**, nothing about **combos** (`KXMVE`, ADR 0012), and
  nothing about **in-play**.
- **It does not recommend arming trading, and it does not recommend disarming
  it.** ADR 0018 owns that boundary and is untouched: `ORDERS_ARE_DRY_RUNS` stays
  `True`, and arming remains a code change requiring two barriers, five gate
  conditions and a deploy.
- **It does not propose wiring up `elo.py`.** The second signal was documented as
  a *conjunction* — "where both agree" — and a conjunction can only remove rows
  from the surfaced set. Adding an AND-gate to an empty set leaves it empty, so
  the missing half **cannot** explain `actionable = 0` away. That is arithmetic,
  and it is settled. A different design — blending a model probability into
  `fair_probability` to move the edge — is a new decision needing its own ADR,
  not the completion of an existing one.
- **It does not make Joe's decision.** §8 frames it.
- **It does not amend anything.** Addendum A's Finding 1 (`symmetric difference
  0` is a slice number; 15 on the table) and Finding 2 (`45 rows` is a slice
  number; **137** on the table) remain reported-and-unamended, and this ADR
  carries **137** wherever it needs that figure, per Finding 2's own instruction.

---

## What this does NOT establish

- **It establishes nothing about whether an edge exists at Kalshi.** §1. The
  forbidden sentence is forbidden here too.
- **It is a census, not a sample.** One pin (`1564`), one pull, one look, no
  interval anywhere, two leagues, one month, 34 recording instants.
- **Four of the five released verdicts add nothing.** §3. H1 is a checksum
  (`n_new = 0`) and may not be cited as a new observation.
- **The R3 ruling was made in the open, with the census already public**
  (committed at `3f2fa1a`, on a public repository, before any ruling existed).
  What protects each verdict is that the **rule** producing it was fixed before
  the run and is quoted verbatim in Amendment A §A5; what was decided in the open
  is only which guards may withhold.
- **The deployed revision of `suppression.py` is not pinnable to a SHA.** No
  `/api/*` route exposes a build SHA and `flyctl deploy` builds from a working
  directory rather than a commit. Every statement about what the deployed build
  *contains* rests on the record's own behaviour and on deploy timestamps.
- **The clean rows are not proven fresh** (§7.5), and the ask's own freshness is
  unmeasurable (§7.6).
- **`market_width`, `book_count` and `books_used` were never observed.**
  `/api/ledger` does not select them. Two of the three extra predicates
  registered in the brief are unanswered and remain so.

  > **ANNOTATION 2026-08-10 — the bullet is correct; the mechanism was checked
  > and it is not the one a reader would assume.** Verified against the code,
  > and against the query itself, because a lane brief asserted the opposite:
  >
  > *Line numbers below are at `81ffd9c^` — the state this ADR describes. They
  > have since moved; the symbols have not.*
  >
  > - The `fair_prices` join **is already there** —
  >   `backend/api/routes.py:757`, `LEFT JOIN fair_prices f ON f.id =
  >   r.fair_price_id` — and has been since the four devig readings were added.
  >   A reader who assumes the bullet means "the join is missing" is wrong.
  > - **`SELECT r.*` does not reach these three.** All three are columns of
  >   `fair_prices` (`backend/store/schema.sql:301-303`), not of
  >   `recommendations`, and the SELECT list named exactly five `f.` columns —
  >   the `p_*` readings. Executing the route's own query against a freshly
  >   migrated database and reading `cursor.description` returns 33 columns and
  >   none of the three. So the bullet's *"does not select them"* is **literally
  >   true**. The pinned pull agrees without reading any code: not one of the
  >   1,564 rows in `2026-08-10-clean-shortfall-pull.json` carries any of the
  >   three keys.
  > - **And `_serialise` is a second, independent barrier.** It hand-builds its
  >   dict and named none of the three, so widening the SQL alone would also
  >   have changed nothing. Two barriers, in two languages; either alone leaves
  >   the payload byte-identical. That is why this was not caught by reading one
  >   of them.
  >
  > **CORRECTION to the bullet's own wording: "never observed" is too strong,
  > and this ADR already relies on the observation.** The *columns* were never
  > selected — that part is exact. But `reason_text` carries `book_count` on
  > every row that tripped the rule: `suppression.py:291` writes
  > `f"{book_count} book(s), need {config.min_book_count}"`, and over the pinned
  > pull that string is **`1 book(s), need 2` on all 245 `too_few_books` rows**,
  > with no other value anywhere. Independently, **230** rows carry
  > `no_market_width`, which pins `market_width is None` on each. Their
  > symmetric difference is **15**, reproducing Addendum A's Finding 1 exactly.
  >
  > So the honest statement is: **`books_used` and `anchored_on_sharp` were
  > never observed; `market_width` and `book_count` were observed only where
  > they failed.** On the other 1,319 rows — including all 614 clean ones — only
  > bounds are known: `book_count ≥ 2` and `market_width ≤ 0.06`. The two
  > registered predicates remain unanswered, which is what the bullet is for.
  >
  > *(A by-product worth keeping: `wide_market` had **1,334** rows with a
  > measurable width and fired **0** times. Unlike §7.6's `stale_kalshi_quote`,
  > that is a real zero over a non-empty denominator — a guard that could have
  > fired and did not.)*
  >
  > **Fixed forward at `81ffd9c`** — both barriers, with tests verified by
  > disabling each, and extended at `4938701` with `anchored_on_sharp` — the
  > column §7.2's annotation shows is load-bearing on the tautology reading.
  > **The bullet still stands for this record**: both changes are read-only and
  > rewrite no stored row, so the 1,564 rows this ADR is about remain unobserved
  > on all four columns and the two registered predicates stay unanswered.
  > Re-measuring the *past* needs `odds_snapshots`; see
  > [`2026-08-10-three-queries-the-agents-could-not-run.md`](../measurements/2026-08-10-three-queries-the-agents-could-not-run.md).
- **Counted assumptions: 1.** A1 — that an MLB or WNBA moneyline has exactly two
  settling outcomes, so a `NO` on one ticker and a `YES` on the other name the
  same claim. Its registered detector ran and passed on all 59 clusters, so A1
  did not fail silently.
