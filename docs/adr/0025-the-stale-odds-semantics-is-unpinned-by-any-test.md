# 0025 — The `stale_odds` semantics is unpinned by any test, and its removal moves the actionable counter by 23 rows

**Date:** 2026-08-11
**Status:** Accepted. This ADR **records two facts and makes one decision**: it
fixes the magnitude of what `stale_odds` holds back, records that no test in
this repo can distinguish the two candidate readings of `last_update`, and
decides that this changes nothing about ADR 0021's headline.
**Owns:** the magnitude figure (23 rows / 9 clusters / 8 odds snapshots) and the
test-coverage defect at `tests/test_suppression.py:49-53`.
**Defers entirely** to **ADR 0021 §7.5** on the *direction* of the semantics
defect, and to **ADR 0020** (reserved) on the remedy. This ADR does **not**
re-open ADR 0021's refutation, does not change a threshold, and does not
license removing `stale_odds`.
**Does not touch** ADR 0023 (A-versus-F), ADR 0024 (arming), or the fee model.

---

## 0. Provenance, because this ADR exists only because an audit shrank it

This began as a claim roughly ten times larger, produced by an agent triaging
the backlog:

> *"ADR 0021's headline is contingent on `stale_odds` being semantically
> correct, and that has never been written down. `stale_odds` touches 844 of 935
> suppressed rows. If `last_update` is a crawler clock, the central refutation
> rests on a guard that discarded the only rows that could have contradicted
> it."*

`measurement-skeptic` returned **OVERSTATED**. Four of that paragraph's moves do
not survive and they are recorded here rather than deleted, because the shape of
the error is the reusable part:

1. **`844 of 935` does no work in the argument it sits in.** Of the 859
   stale-touching rows (pin 1564), **836 — 97.3% —** cannot be surfaced by
   removing `stale_odds`: they carry non-positive edge or fail an
   edge-independent check as well. The operative number is **23**. A
   reason-code *coverage* statistic was promoted to a claim about what the
   guard *holds back*. That is this repo's named failure shape, run again.
2. **"Never been written down" is false.** ADR 0021 **§7.5** writes down the
   semantics defect, its direction and its evidence.
   `2026-08-10-preregistration-odds-last-update-repeat-poll.md` is the
   registered instrument for it, and its own limits section pre-emptively
   forbids the conclusion drawn: *"establishing that one of them measures the
   wrong thing does not make any row actionable, and no write-up may imply it
   does."* What was genuinely undocumented is the **magnitude**, which is one
   sentence long and is §1 below.
3. **The mechanism runs backwards** — see §3. This is the one that mattered.
4. **The census figures were pin-1549 numbers presented against a pin-1564
   result.** `clean == 614` under both pins, which is exactly what made the
   substitution invisible. ADR 0021 §4 already carries the rule this breaks.

The claim's author had self-corrected three separate errors in the same report
before it reached the audit, **all three leaning the same way** — toward "these
rows are junk". The fourth leaned the other way and was caught by someone else.
**A self-audit is not an audit**, and the direction of an author's errors does
not predict the direction of the ones they miss.

---

## 1. The magnitude, which is the new fact

> **On the pinned record, `stale_odds` is the only suppression code holding
> back any row that would otherwise be `actionable` — and it holds back 23 rows
> across 9 game clusters and 8 odds snapshots, all under
> `strategy_config_version` 1.**
>
> Re-running `RiskConfig.reference()` sizing on those 23 returns **4–37
> contracts** on every one, so removing `stale_odds` alone, with every other
> threshold unchanged, would move `population_counts["actionable"]` from **0
> rows to 23**, and the gate's scored-actionable game counter from **0 of 300 to
> 4 of 300**.

Read the `n` before the effect size, as the house rules require:

```
23 rows
  -> 18 distinct tickers
  ->  9 distinct game clusters
  -> 11 distinct sweeps (created_ms)
  ->  8 distinct odds-observation stamps      <- the dependence unit (ADR 0021 §2)
```

Every one of the 9 games is priced off **exactly one** odds snapshot:
`p_conservative` is byte-identical across a game's 2–6 rows and only the Kalshi
ask moves. One stamp (`KXWNBAGAME-26AUG07GSDAL`) carries **6 of 23 rows =
26.1%**; two stamps together carry **43.5%**. A pooled number is not a finding
until the parts agree, and here the parts are eight.

**4 of 300 is not "the gate nearly opens".** At `G = 4` the gate's
`always_valid_multiplier` (`gate.py:527-530`) is far above its already-punitive
value at `n = 20`. Nine games buys nothing; four buys less.

---

## 2. The decision

> **Nothing about ADR 0021's headline changes, and `stale_odds` is not
> removed, relaxed, or re-tuned.**
>
> The magnitude in §1 is recorded so that no future session has to re-derive
> it, and so that no future session can quote *"844 of 935"* as though it were
> the number of rows in play. **The number of rows in play is 23.**

The reason this is a decision rather than a shrug is §3.

---

## 3. The mechanism runs backwards, and this is the load-bearing correction

The original claim's premise was *"`last_update` is a crawler/scrape clock"*.
That premise is **correct** — it is exactly what `suppression.py:210-243` and
ADR 0021 §7.5 establish on a 320-of-320 census, and the guard's own message
already says `book last scraped ...`, having been corrected from a `last moved`
wording that was false.

**But under a scrape clock, `odds_age_ms` is a LOWER BOUND on true line age.**
ADR 0021 §7.5 says so in its heading. A row rejected at 259 minutes carries
price information *at least* 259 minutes old under **either** candidate reading.
**The rejection is correct either way.**

So the defect a scrape clock produces is that the guard is **too permissive**,
and it contaminates the **clean** population — rows that pass are not proven
fresh — which is §7.5's *"the clean 323 carries unmeasured staleness"*. It does
not make the discarded rows wrongly discarded.

Only the **opposite** semantics — `last_update` as a *reprice* timestamp, where
an old stamp means a confirmed-unmoved line — would make the 23 wrongly
discarded. **The claim asserted premise (a) and drew conclusion (b).**

And the reprice reading does not rescue them anyway: `odds_age_ms` on the 23
spans **20.2 minutes to 18.7 hours**, with six above nine hours. A book that has
not repriced an MLB moneyline in 18.7 hours has most likely stopped quoting it,
which is the correlated-garbage case **ADR 0019** exists for.

---

## 4. What the closing line says, since it is available and was not run

CLAUDE.md rule 3: *validate against Kalshi's own closing line.* Eleven of the 23
carry a score.

| cluster | scored rows | `clv_tenths` |
|---|---:|---|
| `KXWNBAGAME-26AUG07GSDAL` | 4 | −15, −5, −25, −15 |
| `KXWNBAGAME-26AUG09LVNY` | 3 | −25, −35, −35 |
| `KXWNBAGAME-26AUG09DALMIN` | 2 | −15, −25 |
| `KXMLBGAME-26AUG091335TORPHI` | 2 | −5, −5 |

**All eleven are negative**, mean **−18.64 tenths**, all four scored clusters
negative — against a cluster-mean-of-means of **−5.12 tenths** over the 20
scored clean `no_edge` games. Positive means you beat the close
(`backend/analysis/clv.py:148`).

Where a closing-line check exists, the rows the guard discarded **lost to
Kalshi's own close by more than the rows it kept.** No p-value is attached and
none may be: four clusters.

**And 8 of the 23 rows are not pre-game.** Four of the nine games were already in
progress when the row was written — 4, 9, 10 and 65 minutes past first pitch,
verified against `tests/fixtures/odds_mlb_h2h_spreads_totals.json`'s own
`commence_time` to within one minute. Those rows compare a **live** Kalshi ask
against a **frozen pre-game** sportsbook consensus scraped 20 to 259 minutes
earlier, and they carry the four largest MLB edges in the set. Against the clean
614, only 8 of 508 MLB rows (1.6%) are post-start. ADR 0021 §9 establishes
nothing about in-play; lifting `stale_odds` would import in-play rows into a
pre-game refutation.

---

## 5. The test-coverage defect, which is the part worth acting on

`tests/test_suppression.py:49-53`:

```python
def test_a_stale_book_suppresses(self):
    """A book that has not repriced in an hour is stale even if we fetched
    it a second ago."""
    result = check(odds_age_ms=3_600_000)
    assert "stale_odds" in result.reason
```

Two defects, verified directly:

1. **It anchors at 4× the threshold.** `max_odds_age_ms` is `900_000`
   (`suppression.py:48`); the test fires at `3_600_000`. The boundary is
   untested, so an **off-by-one** (`900_001`) and a **boundary-operator flip**
   (`<=` to `<`) both stay green.

   **Stated precisely, because the first draft of this sentence overreached.**
   It originally said "an off-by-one, a unit slip, or a tenfold error all stay
   green". A tenfold error does **not**: at a limit of `9_000_000` the 4× anchor
   of `3_600_000` no longer suppresses, and the old test goes red. Checked, not
   reasoned — the mutation was run. A 4× anchor catches errors larger than 4×
   and is blind to everything smaller, which is the ordinary and boring truth
   about a loose anchor, and it is still the defect: the errors a threshold
   actually suffers are small ones.
2. **Its docstring asserts the semantics the code explicitly corrects.** *"has
   not repriced"* is the reprice-clock reading; `suppression.py:210-243` says
   `last_update` is a scrape clock and the guard's message says `last scraped`.

Together: **no test in this repo can tell the two readings of `stale_odds`
apart.** The anchor was chosen at a point where both readings return the same
answer — the same shape as `clv_tenths(500, 500, "no")`, a check that cannot
distinguish the thing it is named for.

**Fixed in this commit:** the docstring now states the scrape-clock reading, and
boundary tests pin `900_000` (passes) against `900_001` (suppresses). That pins
the **threshold**. It does **not** pin the **semantics** — no unit test can,
because both readings agree on every input a test can supply. The registered
instrument for that is
`docs/measurements/2026-08-10-preregistration-odds-last-update-repeat-poll.md`,
and **it has not returned**. Its P4 window is 17:30Z–22:00Z.

---

## 6. What this does not establish

- **It does not establish that any of the 23 rows carried a real edge.** Eleven
  carry a closing-line score and all eleven are negative (mean −18.64 tenths,
  all four scored clusters negative), against −5.12 tenths per cluster over the
  20 scored clean games. Twelve are unscored and their sign is unknown.
- **It does not establish that `stale_odds` discards fresh rows.** Under the
  scrape-clock reading the evidence supports, `odds_age_ms` is a lower bound on
  true line age, every one of the 23 rejections is correct, and the defect
  contaminates the **clean** population instead. Only a reprice-clock reading
  would make the rejections wrong, and no measurement in this repo
  distinguishes the two.
- **It does not establish anything about `strategy_config_version` 2.** All 23
  rows are v1. Across the 84 sole-stale v2 rows, **zero** carry a positive
  post-fee edge.
- **It is 8 odds snapshots, not 23 observations.** Each of the 9 games is priced
  off exactly one odds observation. One snapshot carries 26.1% of the rows and
  two carry 43.5%.
- **It says nothing about pre-game trading, because 8 of the 23 rows are not
  pre-game.** Four of the nine games were in progress when the row was written.
- **It does not establish that the gate would open.** The gate counts scored
  actionable clusters against a floor of 300; this moves it to 4.
- **The census figures behind the original claim were pin-1549**
  (`docs/measurements/2026-08-10-wholetable-pull.json`) while ADR 0021's
  headline is **pin-1564** (`docs/measurements/2026-08-10-clean-shortfall-pull.json`).
  At pin 1564 they read 859 / 616 / 950. **The 23 rows and the 9 clusters are
  identical under both pins; nothing else is.**
- **There is no committed harness for the original claim.** Every figure here
  was re-derived from the two committed pulls with independent code during the
  audit. `scripts/run_clean_shortfall.py` computes none of it.
- **The cut was unregistered and post-hoc**, taken after the record had been
  read repeatedly, on the reason code already known to dominate — eight or more
  cuts of one table, three of which produced errors that had to be withdrawn.
  There is no test statistic anywhere in this ADR, so no significant cell was
  manufactured; but the framing was **selected, not pre-committed**.
- **`ALL_CHECK_NAMES` has 12 entries, not 14.** Verified directly at
  `backend/core/suppression.py:119`. At least five committed documents say
  fourteen, including
  `2026-08-10-preregistration-odds-last-update-repeat-poll.md:866`, whose
  sentence bears directly on this question. **Six of the twelve never fired on
  this record.**

---

## 7. Consequences

- **The repeat poll's value goes up, not down.** It is the registered instrument
  for the only question that could change §3's direction, and §5 shows no unit
  test can substitute for it. It stays the highest-value runnable item.
- **No document may say "844 of 935" as the number of rows `stale_odds` is
  holding back.** It is 23. The 844 figure is reason-code coverage, at the wrong
  pin, and it is 97.3% rows that removal cannot surface.
- **No document may say ADR 0021's refutation "rests on a discarded set that
  could have contradicted it".** 836 of 859 could not, and the 23 that could
  lost to the close.
- **The "one of fourteen suppression codes" phrasing is wrong** wherever it
  appears and should be corrected to twelve as those files are next touched.
