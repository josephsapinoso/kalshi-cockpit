# 0022 — Nine orphaned modules are quarantined, and the detector that missed them is inverted

**Date:** 2026-08-10
**Status:** Accepted.
**Owns:** `tests/test_has_callers.py` (the module-level half), `backend/agents/`,
`backend/model/`, `backend/main.py`.
**Defers to `0021-the-consensus-only-strategy-is-refuted` §8** on what strategy
comes next, and to **CLAUDE.md** on `elo.py`. Neither is reopened here.
**Number:** 0022, not 0020 — **0020 is reserved for the `stale_odds` scrape-clock
ADR** (ADR 0021 §7.5 queues it), which is deliberately not written this session.

---

## 1. The finding

`tasks/start.md` claims six modules are built-and-never-called. Enumerated
mechanically against what `docker/entrypoint.sh` actually executes, the number is
**nine**, plus a set of partially-dead modules and a symbol-level tail.

Worse than the count: **zero of the nine were in `MUST_HAVE_CALLERS`.** All
fifteen entries in that list name symbols that already had callers when they were
added. The list is a *ratchet* — it stops a symbol that has a caller from
quietly losing one — and it had never once been extended to something that was
orphaned at the time of writing.

That is the opt-in failure in its purest form, and it is the reason for the
inversion in §4. **An allowlist cannot report what is missing from it.** The
file's own docstring said the detector was "that grep, run by CI instead of by
memory", but the grep it automated was the one that takes a symbol you already
suspect. Nobody suspected these nine.

This is the fourth appearance of the shape `tasks/lessons.md` names *"Code with
no caller is not a feature, it is a plan"* (2026-08-07), and the first time it
has been found by counting rather than by accident.

---

## 2. The two structural holes in the detector

Both are the repo's recurring **two limits on one quantity** shape
(`tasks/lessons.md`, 2026-08-07): one guard covering half a property reads
exactly like a guard covering all of it.

### 2.1 `scripts/` counted as a caller, but the image ships two of them

`callers_of` walks every `.py` outside `tests/`, `warehouse/`, `.venv/`,
`node_modules/` and `.claude/`. `scripts/` is therefore production, by that
definition.

It is not production by `.dockerignore`'s definition. Verified directly:

```
scripts/*
!scripts/run_loop.py
!scripts/migrate_db.py
```

**32 of the 34 scripts do not exist on the deployed machine.** (Partner's brief
said 37 of 39; the repo holds 34 `.py` files under `scripts/` plus one `.sh`, so
the correct figure is 32 of 34. The conclusion is unaffected and slightly
understated.)

So the test's definition of *called* and the deployment's definition of *exists*
disagreed, silently, and the disagreement always resolved in the flattering
direction: a module whose only caller is `scripts/demo_builder.py` read as wired
in while being absent from the running system. Five of the nine dead modules are
dead **only** because of this hole — under the old detector every one of them
looked called.

The `.dockerignore` allowlist has already failed twice by being hand-kept
(`run_loop.py`, then `migrate_db.py`; the second crash-looped the container).
The fix here is the same one that class already uses: **derive the roots from
`docker/entrypoint.sh` rather than listing them.** A fifth boot step is covered
without anyone remembering this file exists.

### 2.2 Import counted as use

`_uses` matches `ast.alias`, so `from x import y` alone satisfied the check —
a stale import left behind by a deleted caller stands in for the caller.

The docstring defended this on purpose, and for module reachability the defence
is right: importing a module runs its module-level code, and a dependency-injected
caller never names the symbol syntactically. So the hole is **kept** where import
is the relation that matters and **closed** where it is not:

- Module reachability (§4) stays import-based.
- `MUST_HAVE_CALLERS` gains `test_the_caller_does_more_than_import_the_symbol`,
  which requires a `Name` or `Attribute` reference outside the import statement.
  `review_surfaced` passes because `runner.py:505` names it as a parameter
  default — a reference. A forgotten import would not.

---

## 3. The enumeration

Reachability is the transitive import closure of the four things
`docker/entrypoint.sh` executes: `backend/seed_demo.py`, `scripts/migrate_db.py`,
`backend/api/routes.py` (via `uvicorn ... --factory`) and `scripts/run_loop.py`.

### 3.1 Module-level dead — nine

| Module | Only importer | Why it is dead on the instance |
|---|---|---|
| `backend/agents/scout.py` | `scripts/measure_agent_cache_prefix.py` | Not in the image. And that script reads the module's *prompt constants* to measure cache prefixes — it never calls `research`. |
| `backend/agents/historian.py` | `scripts/measure_agent_cache_prefix.py` | Same. `review` is called by nothing, anywhere. |
| `backend/model/elo.py` | `tests/test_model.py` | No production importer at all. |
| `backend/model/backtest.py` | `tests/test_model.py` | Harness for `elo.py`. |
| `backend/model/synthetic.py` | `scripts/demo_builder.py` | Not in the image. |
| `backend/analysis/joint_bound.py` | `scripts/run_joint_bound.py`, `scripts/run_clean_shortfall.py` | Not in the image. |
| `backend/kalshi/combos.py` | `scripts/demo_combos.py` | Not in the image. |
| `backend/main.py` | nothing | Superseded alternate entry point; `entrypoint.sh` runs uvicorn against `routes:create_app` directly. |
| `backend/store/publish.py` | nothing | The lake writer. Mentioned only inside an error *string* in `analysis/marts.py`. See §6. |

**Partner's framing was right on the count and on the membership, and wrong on
one classification, which is worth correcting because it changes the
disposition:** `scout.py` and `historian.py` do have a production importer
(`measure_agent_cache_prefix.py`), so a purely mechanical "is anything importing
this" rule files them as tooling. They are not tooling. That script imports the
modules to read prompt text; nobody runs the agents. They are classified
**QUARANTINED**, by judgement, and the judgement is then held to a mechanical
invariant (§4).

### 3.2 Confirmed live, and previously suspected wrongly — three

`backend/agents/review.py`, `backend/agents/skeptic.py` and
`backend/agents/base.py` are **wired**. `backend/runner.py:61` imports
`review_surfaced`, `runner.py:505` passes it as the `review` parameter default,
and `review.py` pulls `skeptic` and `base` behind it. The Skeptic runs on every
pricing pass. Verified, not assumed.

The lesson generalises past this file: *"`backend/agents/*` is orphaned"* was
true when it was written (2026-08-08 wired half of it) and became false without
anything updating the sentence. Half a package changing status is exactly the
case a per-module enumeration catches and a per-package adjective does not.

### 3.3 Partially dead — four, not three

Modules the image imports, whose public surface is mostly unreachable. Named
here for the record; **not** classified in `DISPOSITIONS`, because the module
*is* live and the granularity of the enumeration is the module.

| Module | Why it is live | What is dead inside it |
|---|---|---|
| `backend/analysis/validate.py` | a function-local `from .validate import Observation` in `clv.py` | `summarise`, `report`, `pooling_check`, `check_edge_money_consistency`, `summarise_clv`, `BucketResult`, `Summary`, `PoolingVerdict`, `CLVResult`, `ConsistencyWarning` — the whole measurement-harness surface |
| `backend/core/teaser.py` | `routes.py:63` imports `find_wong_candidates` | `build_leg`, `value_teaser`, `TeaserValuation`, `TeasedLeg`, `TeaserUnpriceable` — reachable only from `demo_builder.py` |
| `backend/model/margins.py` | `teaser.py:31` imports from it | `fit_by_spread`, `spread_bucket_for`, `default_distribution`, `published_sd`, `published_total_sd`, `teaser_leg_probability`, `TeaserLeg` |
| `backend/core/correlation.py` | `routes.py:46`, `parlay.py:55` | `implied_correlation`, `equicorrelation_floor`, `equicorrelated_joint`, `CorrelationUnreachable` |

Partner's brief said three. It is four; `correlation.py` is the one not named.

`implied_correlation` is worth a sentence on its own, because
`tasks/lessons.md` (2026-08-07) records it as *"the module's own refusal now has
a data source"* — the payoff that made the KXMVE correction more than a
correction. It is reachable from `scripts/demo_combos.py` and
`scripts/measure_combo_correlation.py`, neither of which ships. The data source
exists and nothing on the instance consults it.

### 3.4 Symbol-level orphans

The tail is larger than a hand-list can track: **39** public symbols in live
modules are unreachable from a deployed entry point through the intra-module call
graph, and **17** of those are reachable only through a `scripts/` file that the
image excludes.

**No hand-written table of these is being added, deliberately.** A hand-list here
would reproduce the exact defect this ADR exists to fix, one level down. What is
added instead is a *derived* check: every symbol already in `MUST_HAVE_CALLERS`
must have at least one caller that survives `.dockerignore` (§2.1) and at least
one reference beyond an import (§2.2). All fifteen pass today, so the check
starts as a ratchet rather than a debt.

---

## 4. The decision: quarantine — do not wire, do not delete

**Partner's call, executed as given.** The reasoning, recorded so no future
session re-derives it:

- **Wiring Scout and Historian means live Anthropic calls.** The bill is
  currently held at exactly zero by `surfaced == 0`. Turning on spend to
  decorate a line that ADR 0021 refuted three commits ago is backwards.
- **Deletion is unrecoverable**, and Historian plausibly matters under ADR 0021
  §8 **Option B** (change the reference class) and **Option F** (keep recording
  and re-read at larger `n`) — both need a post-mortem loop.
- **`elo.py` specifically must not be wired.** CLAUDE.md and `tasks/NEXT.md`
  both forbid it, and the argument is arithmetic rather than judgement: the
  documented design was a **conjunction** — surface where both signals agree —
  and an AND-gate over an already-empty set leaves it empty. The missing half
  cannot explain `actionable = 0` away. Blending a model probability into
  `fair_probability` *would* move rows, but that is a new decision needing its
  own ADR, not the completion of this one. `backtest.py` moves with `elo.py`:
  reviving the harness alone measures nothing, and reviving the model without
  its harness puts an unvalidated model on the money path.

### 4.1 Quarantine is a mechanical state, not a comment

This is the part that makes the decision hold. A comment saying *"do not wire
this up"* is exactly the artefact that failed for eleven build steps. So
`tests/test_has_callers.py` now carries:

```python
DISPOSITIONS: dict[str, Tool | Quarantined] = { ... }
```

and four checks over it:

1. **`test_every_unreachable_module_is_classified`** — the inversion. Every
   module under `backend/` is enumerated; every one the entry points cannot
   reach must appear in `DISPOSITIONS`. **An unclassified orphan fails.** This
   is the test that would have found the nine.
2. **`test_a_quarantined_module_has_not_been_wired_up_by_the_back_door`** — the
   invariant that gives quarantine teeth. A quarantined module must stay
   unreachable. Adding an import that connects Scout to the chain turns this
   file **red**, and the only way to green is to move the entry out of
   `DISPOSITIONS` and into `MUST_HAVE_CALLERS` — a deliberate act, in a diff,
   with this ADR cited. Live spend cannot arrive as a side effect of an import.
3. **`test_a_tool_names_a_runner_that_exists_and_does_not_ship`** — a `Tool`
   claims a human runs it and that its absence from the image is *why* it is
   unreachable. Both are checked: the named `scripts/` runner must exist **and**
   must be excluded by `.dockerignore`. If a runner were ever allowlisted into
   the image, the module would be reachable and the classification would be
   wrong in the flattering direction.
4. **`test_a_quarantined_module_says_what_would_bring_it_back`** — every
   quarantined entry carries a `revive_if` and a live ADR path. Parking
   something without a revival condition is how it becomes permanent by default.

The distinction between the two classes is *intent*, and it is a human
judgement; the invariant they share — **not reachable from the image** — is
mechanical, and the test enforces it either way.

| Class | Meaning | Members |
|---|---|---|
| `Tool` | A human runs it deliberately, from a laptop. Absence from the image is correct. | `main.py`, `store/publish.py`, `analysis/joint_bound.py`, `kalshi/combos.py`, `model/synthetic.py` |
| `Quarantined` | Nobody runs it. Parked with a stated revival condition. | `agents/scout.py`, `agents/historian.py`, `model/elo.py`, `model/backtest.py` |

`model/synthetic.py` is a `Tool` with an edge to it worth stating: it *must*
never reach the image. It manufactured a +28.4% EV teaser once already
(`tasks/lessons.md`, 2026-08-06) by being right on the mean and wrong on the
variance. Check 3 above now asserts that its runner is excluded, so the property
"the synthetic generator is not on the instance" has a test rather than a
convention.

### 4.2 The red-test demonstration

Per CLAUDE.md — *every guard is verified by disabling it and watching the test
fail* — green proves nothing here, because an enumeration that enumerates
nothing passes every assertion in it. Two directions were shown to move, and
both are recorded in §7.

---

## 5. What was NOT done, and why

- **Nothing was wired up.** §4.
- **Nothing was deleted.** §4.
- **The partially-dead modules in §3.3 were not split or trimmed.** Splitting
  `margins.py` so the live 20% stops carrying the dead 80% is a real
  improvement and a different change; doing it inside a session that is
  inverting the detector would mean the detector's first real run happened
  against a tree it had just rewritten.
- **`backend/store/publish.py` was not wired into the runner**, even though
  §6 is the strongest argument that something should write the lake on a
  schedule. That is a data-pipeline decision with its own failure modes
  (a writer on a 15s cadence is how this project lost its log stream once
  already), and it is queued, not taken.
- **The data lake was not cleaned.** §6.

---

## 6. The data-lake landmine — recorded, not fixed

Verified 2026-08-10 by reading the Parquet directly. **Do not fix this tonight;
it needs a decision about what the lake is for.**

`data/lake/` holds fifteen tables partitioned `dt=2026-08-07`, `dt=2026-08-08`,
`dt=2026-08-09`. Two observations, and it is their conjunction that is dangerous:

**Empty partitions that read as measured zeroes.** `fair_prices` and
`event_links` have **0 rows in all three partitions**. So do `fills`, `lessons`,
`model_ratings` and `unmatched_events`. A partition that exists and is empty is
not distinguishable, downstream, from a day on which nothing happened — which is
this repo's oldest rule (*"unreadable must never resolve to zero"*,
`tasks/lessons.md` 2026-08-06) reappearing at the storage layer, where the
sentinel is a **directory** rather than a value.

**Demo data wearing the record's directory names.** `recommendations` holds
**847 rows** across those three 2026-dated partitions — 429 + 9 + 409. Every row
is stamped between **2025-07-23 and 2025-08-10**. It is `seed_demo` output,
filed under partition names that assert it was recorded last week.

Partner's brief said *"nothing reads it today"*. **That is the one part of the
brief that is wrong, and the correction makes it worse rather than better.** The
dbt warehouse reads it directly —
`warehouse/models/staging/stg_recommendations.sql:25` does
`read_parquet('../data/lake/recommendations/**/*.parquet')`, and
`mart_calibration.sql` and `mart_fee_reconciliation.sql` read `settlements` and
`fills` the same way. `/api/dashboards` then reads those marts through
`analysis/marts.py`.

So the reader is not hypothetical; it is built, and it is one `dbt build` away
from putting 2025 demo rows on a screen labelled with 2026 dates. What is
missing is only that **nothing on the deployed machine runs either step** —
neither `python -m backend.store.publish` (the writer, quarantined as a `Tool`
in §4) nor `dbt build`. The safety is an accident of the boot script, not a
design.

The shape is one this file has named before and is worth stating in its general
form:

> **A pipeline whose writer is a human step accumulates artefacts that outlive
> the reason they were written, under names that assert otherwise.** The
> directory listing is identical whether the data is a record or a rehearsal.

The fix, when it is taken, is not to delete the rows. It is to make the
provenance unfalsifiable — a partition should carry the instance mode that
produced it, so `demo` data cannot be read as `live` data by anything, ever.
Deleting the files leaves the mechanism that created them intact.

---

## 7. Verification

Both directions of the new guard were exercised against the real tree.

**Direction 1 — an unclassified orphan must fail.** A module
`backend/deliberate_orphan.py` importing nothing and imported by nothing was
added, the suite run, and
`test_every_unreachable_module_is_classified` went **red**, naming the file.
Removed afterwards. This is the check that the nine escaped for the project's
life.

**Direction 2 — quarantine must be escape-proof.** A single line was added to
`backend/runner.py` importing `backend.agents.scout`, and
`test_a_quarantined_module_has_not_been_wired_up_by_the_back_door` went **red**,
naming `backend/agents/scout.py`. Reverted afterwards. This is the direction
that matters for money: it is the one that fires when someone wires an
Anthropic-billing agent into the chain while doing something else.

Both anti-vacuity guards were also written and are permanent:
`test_the_entry_points_are_read_off_the_boot_script` fails if the entry-point
extractor stops matching, and `test_reachability_actually_discriminates` fails if
the closure ever returns everything or nothing — either of which would retire the
whole check while leaving it green.

---

## What this does NOT establish

- **That any classified module is correct code.** This ADR is about
  reachability only. It makes no claim that `elo.py` works, that `joint_bound.py`
  is right, or that the agents would behave if run.
- **That a LIVE module's code executes.** Reachability is import-based by
  design (§2.2). A module imported behind a branch that never fires counts as
  LIVE here and may be as dead in practice as anything in `DISPOSITIONS`. The
  39 symbol-level orphans of §3.4 are the visible part of that gap; the
  behavioural tests are what establish execution.
- **That the enumeration is complete below module granularity.** §3.4 is
  measured but not enforced. A function that loses its last caller inside a live
  module still passes unless it is in `MUST_HAVE_CALLERS`.
- **That `scripts/` is now covered.** The enumeration is over `backend/**`. A
  script that becomes orphaned is not detected, and the two that ship are
  checked only for existence and load, by the class above.
- **That the lake is safe.** §6 records the landmine and fixes nothing. The
  only thing standing between 2025 demo rows and the Dashboards screen is that
  nobody has run `dbt build` on the instance.
- **That the nine are the last of them.** They are the last *findable by this
  method*. A tenth module reachable only through a `__getattr__`, an entry-point
  string in config, or a dynamic import would not appear in an AST import
  closure.
