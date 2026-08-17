# 0040 — Quarantine is the settled state for Scout and Historian, and the pre-commitment to wire-or-delete is discharged as "neither"

**Date:** 2026-08-17
**Status:** Accepted. This ADR **makes** a decision: it discharges an open
pre-commitment carried by ADR 0038 by taking the third option that
pre-commitment did not offer, and it says why the two it did offer are both
wrong.
**Owns:** `backend/agents/scout.py`, `backend/agents/historian.py`, and the
`Quarantined` rows for those two modules in `tests/test_has_callers.py`.
**Supersedes, for those two modules only,** the disposition rationale recorded
in [ADR 0022 §4](0022-quarantine-the-orphaned-modules.md). ADR 0022's decision
for `elo.py` and `backtest.py` is untouched, and so is its inversion of the
detector.
**Does not reopen** ADR 0038's closure of the edge hunt. Nothing here proposes
wiring an agent up.

---

## 1. The pre-commitment being discharged

[ADR 0038](0038-the-edge-hunt-is-closed-and-the-record-is-the-product.md), in
its Consequences section, commits in writing:

> The quarantined `backend/agents/` orphans (ADR 0022) are now either wired or
> deleted before the repo is called finished; a declared state is fine
> internally and **reads as dead code to a stranger**.

That sentence has been sitting unmet. An Accepted ADR carrying an unmet
pre-commitment is exactly what a future session pays full price to re-derive,
so it is closed here rather than left to drift.

**The motive in that sentence is portfolio legibility, not correctness and not
cost.** The clause that carries the argument is *"reads as dead code to a
stranger"*. That matters, because §5 shows the stranger does not in fact
encounter these two modules as dead code — the product tells them, on screen,
what the modules are and why they are switched off.

---

## 2. First correction: the set is two, not seven, and the phrase "the
`backend/agents/` orphans" is wrong

ADR 0038's sentence, and the brief that carried it forward, both speak of *"the
quarantined `backend/agents/` orphans"* as though the directory were the unit.
It is not. `backend/agents/` holds seven files and **five of them are live.**

Measured with `reachable_modules()` from `tests/test_has_callers.py`, whose
entry points are derived from `docker/entrypoint.sh` rather than listed
(`['backend/seed_demo.py', 'scripts/migrate_db.py', 'backend/api/routes.py',
'scripts/run_loop.py']`):

| module | reachable from a deployed entry point? | the edge that makes it so |
|---|---|---|
| `backend/agents/__init__.py` | **LIVE** | empty file; parent package of `base`, imported before it |
| `backend/agents/base.py` | **LIVE** | `backend/api/routes.py:82` — `from ..agents.base import AgentConfig` |
| `backend/agents/budget.py` | **LIVE** | `backend/agents/review.py:105` — `from .budget import AgentBudget` |
| `backend/agents/review.py` | **LIVE** | `backend/runner.py:70` — `from .agents.review import ReviewCandidate, review_surfaced` |
| `backend/agents/skeptic.py` | **LIVE** | `backend/agents/review.py:103` — `from . import skeptic` |
| `backend/agents/historian.py` | **ORPHAN** | only `scripts/measure_agent_cache_prefix.py:39`, which `.dockerignore` excludes from the image |
| `backend/agents/scout.py` | **ORPHAN** | only `scripts/measure_agent_cache_prefix.py:39`, same exclusion |

The orphan set is **`scout.py` and `historian.py`, and nothing else.** Executed
against the directory as written, the pre-commitment would have deleted the
Skeptic — which `backend/runner.py` calls on every full pass — the spend meter
that bounds it, and the config object the live health check reads.

**This is the third consecutive session in which a sentence predicating over a
set in this repo has been wrong about the set's membership.** The remedy is the
one CLAUDE.md already applies to the two-signal claim: cite file and line, so a
future session re-checks a citation in thirty seconds instead of re-checking an
adjective.

### 2.1 `agent_fleet_configured` reads an environment variable, not the directory

The live `/api/health` payload reports `"agent_fleet_configured": true` while
demo reports `false`, which invites the reading that something on the instance
enumerates `backend/agents/`. It does not.

`backend/api/routes.py:472` is `"agent_fleet_configured": AgentConfig.from_env()
is not None`, and `AgentConfig.from_env` (`backend/agents/base.py:128`) reads
`ANTHROPIC_API_KEY` from the environment and returns `None` when it is unset.
The field reports **whether a key is configured**, never which modules exist.
Live and demo differ because live holds the secret.

So the field is not evidence that Scout or Historian is reachable — the
reachability walk in §2 is the evidence, and it says they are not. But the field
*is* the reason `base.py` may never be deleted: it puts `backend/agents/base.py`
on the live API's import graph.

---

## 3. Second correction: the Historian's revival condition already fired, and
nothing noticed

ADR 0022 parked the Historian with this revival condition, still present in
`DISPOSITIONS` until this ADR:

> revive_if: ADR 0021 §8 Option B or F is taken up — both need a post-mortem
> loop, which is the strongest argument against deleting this rather than
> parking it.

**Option F was taken up.** [ADR 0034](0034-the-a-versus-f-call-is-f-for-a-fortnight-against-the-annotation.md)
is titled for it. The condition fired, the Historian was not reconsidered, and
no test went red — because
`test_a_quarantined_module_says_what_would_bring_it_back` asserts only that
`revive_if` is a **non-empty string**. It cannot tell a live condition from a
fired one or from an expired one.

Then [ADR 0038](0038-the-edge-hunt-is-closed-and-the-record-is-the-product.md)
closed the hunt, which retired F and B together.

So the recorded revival condition has been, in sequence, **fired and then
expired**, and the repo registered neither transition. ADR 0022 §4.1 worried
about the opposite failure — *"quarantine becomes deletion by decay"* — and the
failure that actually occurred is its mirror: **quarantine becomes permanent by
decay, because the condition that would have prompted a re-read stopped being
readable and nothing said so.**

That is a defect in the recorded rationale, and it is fixed in §7 by writing
conditions that are unfired and still reachable after ADR 0038. It is *not* an
argument for deletion: a stale revival condition is a stale sentence, and the
cure for a stale sentence is a correct one.

---

## 4. What deletion would actually cost, measured

The recommendation this ADR was written against was **delete the genuine
orphans**, on four grounds. Three of them are answered by measurement.

### 4.1 It makes the billed-path guard vacuous — measured, not predicted

`tests/test_has_callers.py` carries
`TestNothingNewCanReachTheBilledPath::test_the_unmetered_callers_are_exactly_the_quarantined_ones`,
whose substance is:

```python
unmetered = {rel for rel, _, _ in _billed_path_sites("structured_call")
             if rel not in BILLED_PATH_CALL_SITES}
assert unmetered == {"backend/agents/scout.py", "backend/agents/historian.py"}
assert unmetered <= _unmetered_but_unreachable()
```

Both files were deleted on a scratch commit and the suite was run. Result:

```
FAILED test_the_unmetered_callers_are_exactly_the_quarantined_ones
  AssertionError: the unmetered callers of `structured_call` are [], not the
  two quarantined agents ADR 0022 parked.
FAILED test_the_dispositions_table_has_no_stale_entries
2 failed, 2961 passed, 10 xfailed, 1 error in 229.88s
```

(The error is `tests/test_agents.py` failing to collect: `TestScout` and
`TestHistorian` import the deleted modules. 32 tests in that file, of which
those two classes are the deletable part; the full-suite count falls from
**2,995** to **2,961**.)

The only way to make that assertion green again is to rewrite it as
`assert unmetered == set()`. At that point **both of its assertions are
vacuous**: `set() == set()` holds on any tree at all, and `set() <= anything`
is true by definition. The second one is the load-bearing half — it recomputes
reachability so that a quarantined agent cannot become reachable while still
counting as permitted — and against an empty left-hand side it can never fail.

This is not a cosmetic loss. `_unmetered_but_unreachable()` and the derived
permission it feeds are, by the file's own docstring, the **inversion** of the
allowlist pattern ADR 0022 condemned:

> `BILLED_PATH_CALL_SITES` is an allowlist over a population the scanner
> **enumerates itself** … It fails **closed**. A future reader should not file
> it under the pattern ADR 0022 condemned; it is the inversion of that pattern,
> applied to call sites of a dangerous function rather than to modules.

Scout and Historian are the **only** members that mechanism has ever had.
Delete them and the repo keeps the machinery and loses every case that
exercises it — a guard that cannot fail, which is the single defect this
codebase has spent the most effort learning to detect. The kill criterion set
for this task was *"if removing the modules guts `tests/test_has_callers.py`'s
structure"*. It does, and the gutting is measurable rather than aesthetic.

### 4.2 "They spend Anthropic credits per pass" is false

They are called by nothing on either instance, so they spend **zero**. The
premise inverts the actual state: the quarantine is *why* the bill is zero, and
`test_a_quarantined_module_has_not_been_wired_up_by_the_back_door` is what holds
it there. Deleting the modules and deleting the guard that keeps them unwired
are different acts with the same effect on today's invoice and opposite effects
on tomorrow's.

### 4.3 "Wiring them is on the standing kill list" is an argument for quarantine

It is — and quarantine is the mechanism that enforces it. ADR 0038 closed the
hunt; wiring the Scout would spend money decorating a line the record refutes.
Nothing here disputes that. But "must not be wired" is satisfied by a guard
that turns red when someone wires it, which exists and is green. It does not
require the file to be absent.

### 4.4 "Git history keeps them" keeps the source, not the guard

True, and irrelevant to §4.1. Git history preserves the bytes of `scout.py`. It
does not preserve a live, running assertion that the unmetered callers of
`structured_call` are exactly the modules the deployed entry points cannot
reach. That assertion only exists while the modules do.

---

## 5. The stranger does not read them as dead code

ADR 0038's stated motive was that a declared state *"reads as dead code to a
stranger"*. On this repo, for these two modules, it does not — because both are
**named on live user-facing surfaces that exist specifically to report their
disconnection**, and both surfaces are pinned by tests.

**The Scout.** `frontend/src/components/CrewBubble.tsx` renders a Scout bubble
on every board row. Its entire text is an admission:

> "I have not looked at this game. I am not switched on yet — nobody has
> budgeted the calls."

The component's own docstring states the principle: *"**Silence and a
disconnected wire are different states.** The Scout is quarantined by ADR 0022
and has never been called by anything that runs. Its line therefore says so,
rather than rendering an empty findings list that would read as 'nothing to
report'."* Pinned by
`tests/test_crew_bubble.py::test_the_scout_says_it_has_not_looked`.

**The Historian.** `backend/playbook.py` is live and returns
`"historian_has_run": bool(entries)`. Its module docstring: *"`lessons` has
exactly one writer — the Historian — and the Historian has never been called by
anything that runs. So an empty lessons list means the agent is unwired, not
that the record contains no lessons."* `frontend/src/app/playbook/page.tsx:94`
renders **"The Historian has never run"**. Pinned by
`tests/test_playbook.py::test_no_lessons_says_the_historian_has_not_run`.

Delete the modules and both surfaces become false in the same specific way. The
distinction they were built to preserve — *unwired* versus *nothing to report* —
collapses into a third state neither of them can express, *does not exist*. The
`lessons` table would go from one writer that has never been called to **no
writer at all**, and `historian_has_run: false` would stop being a fact about
wiring.

Deletion is therefore not the removal of two inert files. It is an edit to
`backend/playbook.py`, `frontend/src/components/CrewBubble.tsx`,
`frontend/src/app/playbook/page.tsx`, `scripts/measure_agent_cache_prefix.py`,
`backend/notify/discord.py`'s documented digest set, and four test files — in
order to make a portfolio read cleaner, at the cost of the guard in §4.1 and of
two honest admissions on screen. **An honest admission on screen is a better
portfolio artefact than an absence**, and it is the same argument ADR 0038 made
for keeping a negative result.

---

## 6. The decision

**Neither wired nor deleted. Quarantine is declared the settled, finished state
for `backend/agents/scout.py` and `backend/agents/historian.py`, and ADR 0038's
pre-commitment is discharged by this ADR.**

The pre-commitment offered two options and the evidence supports a third. It was
written as a guard against this repo's most-repeated defect — a plan mistaken
for a feature — and that guard is not needed here, because these two modules are
not mistakable for features. They are reported as switched off by the product
itself, by a test, and by a disposition table that recomputes reachability at
assertion time.

**"Finished" now means:** the modules stay, unreachable and unwired; the
quarantine remains mechanical rather than commented; and no future session may
read ADR 0038 as an outstanding instruction to delete them.

**What would reopen this:** a decision to wire either module up — which needs
its own ADR, a budgeted spend, and a strategy that ADR 0038 has not closed —
or the removal of the live surfaces in §5, which would remove the argument in
§5 with them.

---

## 7. What changes in the code

Only `tests/test_has_callers.py`, and only the two `Quarantined` rows. No
production module is touched, so nothing about the deployed system changes.

1. **Both `revive_if` strings are rewritten.** The Historian's cited ADR 0021 §8
   Options B and F; per §3 those have fired and expired. The Scout's cited *"a
   strategy is adopted that needs qualitative context"*, which ADR 0038 closed
   the door to. Both are replaced with conditions that are unfired today and
   still reachable after ADR 0038.
2. **Both `reason` strings gain the §5 fact** — that a live surface reports the
   module as switched off, and which test pins it — so the argument against
   deleting them is at the site of the decision rather than only in this file.
3. **Both `adr` fields point at this ADR**, which cites ADR 0022 rather than
   replacing it. A reader arriving at the disposition table gets the current
   governing decision first.

`elo.py` and `backtest.py` are left exactly as ADR 0022 wrote them. Their
revival conditions are arithmetic (a conjunction over an empty set) rather than
strategic, so nothing in ADR 0034 or ADR 0038 could have fired or expired them.

---

## 8. Verification

- Full suite at the parent commit `999857f`: **2,995 passed, 10 xfailed.**
- Full suite after this ADR's changes: **2,995 passed, 10 xfailed.** No test
  added, removed, or weakened; two data strings corrected.
- The deletion measurement in §4.1 was run on a scratch commit and reverted;
  `git status` clean afterwards, both files restored.
- `ruff check .` clean.

---

## What this does NOT establish

- **That the Scout or the Historian is any good.** Neither has ever run against
  a real market. Nothing here is evidence about the quality of their output,
  and the question is not opened.
- **That quarantine is right for any other module.** The argument turns on §4.1
  (these two are the only exercise of a specific guard) and §5 (these two have
  live surfaces reporting their state). A module with neither property gets no
  cover from this ADR.
- **That `agent_fleet_configured` means the fleet works.** It means
  `ANTHROPIC_API_KEY` is set. The Skeptic is the only agent the key is spent on,
  and `surfaced == 0` is what holds even that bill near zero.
- **That the revival conditions in §7 will be noticed if they fire.** They are
  prose, checked only for non-emptiness — which is precisely the hole §3
  documents. Closing it needs a machine-readable trigger, and no cheap one was
  available: no ADR in `docs/adr/` currently carries a `Superseded` status, so a
  test for one would pass by finding nothing. Recorded as an open weakness
  rather than closed with a guard that cannot fail.
