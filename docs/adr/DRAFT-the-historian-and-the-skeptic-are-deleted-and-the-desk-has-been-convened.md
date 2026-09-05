# The Historian and the Skeptic are deleted, and the desk has been convened

**Status:** Draft — numbered at merge, after `git fetch` (`docs/adr/README.md`).
Lane C, 2026-09-05. Every file that cites this document does so by its
`DRAFT-` path; the integrator renumbers them in the merge commit
(`grep -rl DRAFT-the-historian` finds them: `backend/agents/review.py`,
`backend/agents/base.py`, `backend/playbook.py`, `tests/test_has_callers.py`,
`tests/test_agent_wiring.py`, `tests/test_agent_budget.py`,
`tests/test_agents.py`, `docs/adr/0071-*.md`).
**Date:** 2026-09-05.
**Decides:** the deletion of `backend/agents/historian.py`,
`backend/agents/skeptic.py` and the metered half of
`backend/agents/review.py`; the record's correction on whether the scout desk
has run on live; the guard that the `apply_verdict` finding earns; and two
cost facts that are recorded here and deliberately not fixed.
**Sources:** the partner's 2026-09-05 audit of `backend/agents/` (every claim
re-verified in this lane at `ef8434b`, §1); a live read of `/api/scout` and
`/api/health` on 2026-09-05 (§2); ADR 0022, 0040, 0060, 0062, 0069, 0071;
`tests/test_has_callers.py`, `tests/test_reachable_callers.py`.
**Overturns:** ADR 0040 for the Historian only — quarantine was declared its
settled state and this takes the second of the two options ADR 0040 declined.
**Touches nothing decided by** ADR 0060 (the desk is on, on the owner's word),
ADR 0062 (the pass default is `review_retired`; the invoice question is
closed), ADR 0069 (the fourth seat), ADR 0071 §2.7 (`claude-sonnet-5` on live,
and the 5-vs-6 convening ceiling, which `fly.live.toml` already documents and
this ADR says nothing further about).

## 1. What was deleted, and why none of it was a feature

At `ef8434b`, `backend/agents/` was 113,614 bytes across nine files. Three
pieces of it could not be reached from anything `docker/entrypoint.sh` runs:

| piece | bytes | why it could not run |
|---|---|---|
| `historian.py` | 9,532 | Its only importer was `scripts/measure_agent_cache_prefix.py`, which `.dockerignore` excludes (`scripts/*` with no `!` line for it). `backend/playbook.py:166,236` read the `lessons` *table*, not the module. That table had one writer — this module — and no row on any instance, ever. |
| `skeptic.py` | 8,318 | Imported at `review.py:103`, so its module body ran at boot; no function in it was ever entered. Every function was reached only through `review_surfaced`. |
| `review.py`'s metered half — `review_surfaced`, `_review_batch`, `_evaluate_one`, `_run_off_loop`, `_amend` | 16,776 of 18,940 | Zero production callers. `git grep review_surfaced ef8434b -- backend scripts docker` finds its definition and one docstring sentence in `runner.py:1796`; every other hit is a test injecting it. The runner has imported `review_retired` and used it as the `run_pricing_pass` default since ADR 0062 (`runner.py:71`, `:1776`). |

Total: **34,626 bytes, 30.5% of the package**, none of it on any path from
the four entry points (`backend/api/routes.py` via uvicorn, `scripts/run_loop.py`,
`scripts/migrate_db.py`, and the demo seeder). The other four modules are
live and untouched in substance: `scout_desk.py` imports `WEB_SEARCH_TOOL`,
`ScoutReport`, `PRO_BETTOR_SYSTEM` and `SharpTake` from `scout.py` and
`pro_bettor.py` on the billed path (`scout_desk.py:59-61`), and `base.py` and
`budget.py` are what it bills through.

**Deleting `review_surfaced` removes the live-spend seam CLAUDE.md records.**
The 24 metered Opus calls in 4m22s on 2026-08-16 — the whole daily cap,
re-reviewing four prop rows six times at quote-pass cadence (ADR 0062 §3,
`fly.live.toml:45-54`) — went out through that function. It has been
opt-in-only since 2026-08-21 and nothing opted in; now there is no metered
reviewer in the tree to opt into. `review.py` is 7,425 bytes after the
rewrite: the seam (`ReviewCandidate`, `ReviewOutcome`, `_refuse_unreviewed`,
`review_retired`), and a docstring carrying the dated history of what sat in
it. The seam stays because `TestTheScheduledSkepticIsRetired` attaches to it —
make any reviewer that passes rows through the `run_pricing_pass` default and
the surfaced row persists orderable; re-verified by that mutation on
2026-09-05, with the deleted function replaced by a pass-through lambda.
`review.py` now imports neither `base`, nor `budget`, nor the SDK, and
`test_no_metered_reviewer_exists_to_opt_back_into` pins that (mutation: add
`from .base import build_client` — red).

What went with them, and what was re-pointed rather than deleted:

- **Tests of the deleted functions' contracts** (`TestSkeptic`, `TestHistorian`,
  `TestThePassCeilingBoundsOneFanOut`, `TestTheReservationSurvivesACrashMidFanOut`,
  `TestTheMeterCannotBeReachedWithoutADatabase`, the async-seam and outage
  classes in `test_agent_wiring.py`) are gone. Their mutation history — fourteen
  guards, thirteen red — is in those files at `ef8434b` and is not restated,
  because a mutation record for a test that no longer exists is a claim nothing
  can re-check.
- **`test_agent_budget.py` now drives `AgentBudget` directly** (`allowance`,
  `reserve`, `settle`, `today_summary`) plus the refusal `review_retired`
  produces. Every mutation its class docstrings claim was re-run in this lane
  on 2026-09-05 and went red as stated, two of them with one more red than
  recorded (now recorded).
- **`scripts/measure_agent_cache_prefix.py` is re-pointed, not deleted.** It
  counted `skeptic.SYSTEM`, `scout.SYSTEM` and `historian.SYSTEM` — two
  deleted modules and one schema module whose prompt no live seat sends. It
  now counts the four seats that bill (`STAFF_SYSTEM_TEMPLATE` rendered home
  and away, `MASTER_SYSTEM`, `pro_bettor.SYSTEM`) under `AGENT_MODEL` if set.
  It is the free `count_tokens` instrument for the held question in §5.1, and
  it has never been run against the prompts that spend money.
- **`playbook.historian_has_run` keeps its name**, because
  `backend/api/routes.py` names it and that file is Lane B's today. Its value
  is still what it says — whether a `lessons` row exists — and its docstring
  now says the table has no writer at all rather than an unwired one.
- **`tests/test_has_callers.py`**: `apply_verdict` leaves `MUST_HAVE_CALLERS`
  with a comment recording §3; the Historian's `Quarantined` entry is removed;
  the `skeptic.py`/`review.py` entries leave `BILLED_PATH_CALL_SITES`;
  `callers_of` states its one-level limit in its docstring. Nothing else in
  that file was touched — Lane B owns its `routes.py` hunks.

## 2. The desk has been convened on live, eight times

ADR 0071 §3 recorded *"Not established: whether the scout desk has ever been
convened on live, and so whether any Anthropic money has been spent at all."*
That was true on 2026-08-24 and is not true now. Read on 2026-09-05 at
~04:15Z over the committed loopback fetcher —

    flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/fetch_live_route.py /api/scout"

— HTTP 200, with `GET /api/health` reporting `agent_fleet_configured = true`:

    scout_briefings     8 rows, ids 1-8, every status = complete,
                        has_briefing = true, refusal_reason = null
    first requested_ms  1787320910043 = 2026-08-21T14:01:50Z
                        KXMLBGAME-26AUG211610ATLMIL-ATL
    last  requested_ms  1788127572062 = 2026-08-30T22:06:12Z
                        completed 22:10:06Z, KXWNBAGAME-26AUG30GSPDX-GS
    budget day from     1788516000000 = 2026-09-04T10:00Z
                        0 of 24 calls, 0 of 60 searches,
                        0 of 500,000 tokens, 0 unmetered

So the desk has spent Anthropic money on eight convenings between
2026-08-21 and 2026-08-30 — the first two days under ADR 0060's three-call
shape, the rest after ADR 0069 (2026-08-23) made it four. `count(agent_calls)`
on the volume was **not** read: no committed instrument emits it, and the
inspector was not extended for it in this lane. The correction is appended
beneath ADR 0071's own sentence in the ADR 0104 form; the four copies of
"three calls" / "never run against a real slate" that were still in the tree
(`frontend/src/app/scout-desk/route.ts`, `backend/agents/scout_desk.py`
twice, `tests/test_scout_api.py`) now carry the read, dated. `routes.py:2304`
already said four and was not touched.

## 3. `apply_verdict` passed three caller tests while unreachable, and the guard that earns

`skeptic.apply_verdict` was on `MUST_HAVE_CALLERS` from 2026-08-08. Its
consequence string read *"`backend/agents/*` goes back to being ~40 green
tests implying a safety layer that can block nothing — the fourth module in
this project to be complete, tested, and called by nothing."* From
2026-08-21, when ADR 0062 put `review_retired` on the pass default, that
sentence described the live machine exactly, and all three tests stayed
green for fifteen days:

- `test_the_symbol_is_used_outside_its_own_module_and_tests` — `review.py`
  names it, in `_amend`. True.
- `test_the_caller_is_a_file_that_exists_on_the_deployed_machine` —
  `review.py` ships. True.
- `test_the_caller_does_more_than_import_the_symbol` — the reference is a
  call, not an import binding. True.

`callers_of` (`test_has_callers.py:421`) walks one level: is the symbol named
in a production file. It never asks whether the function doing the naming is
itself reached. `_amend` was called only by `review_surfaced`, and
`review_surfaced` by nothing. The import closure (`reachable_modules()`,
`DISPOSITIONS`, `TestEveryOrphanIsAccountedFor`) did not catch it either:
`review.py` was imported by the runner *for `review_retired`*, so the module
was reachable and the function inside it was dead. Named, import-reachable,
and called are three properties; the guards measured the first two.

**`tests/test_reachable_callers.py` asks the third.** Starting from the code
that runs at import in every module of the deployed closure (plus the
`create_app` factory the boot script names from the shell, plus every
decorated definition — a decorator is a call made at import), it follows every
name a reached body references into the definitions carrying that name, to a
fixed point, and asserts each `MUST_HAVE_CALLERS` symbol is in the reached
set. It is a name walk, not a resolved call graph, and over-approximates on
purpose: a red is reliable, a green is the weaker claim. Its own docstring
states what it cannot see (string dispatch, framework-invoked methods).

Mutation evidence, 2026-09-05:

- On the real tree, `runner._review_and_persist`'s call
  `persist_if_changed(conn, rec)` replaced by `rec is None`, and a new
  module-level `_orphaned_referrer(conn, rec)` added whose body is the
  original call — the `apply_verdict` shape exactly. All three `has_callers`
  tests for `persist_if_changed` stayed **green**; the new test went **red**.
- `reached_names` made to return every defined name: the tmp-tree test built
  to the defect's shape (`dead` named only by `caller`, which nothing names)
  went red, as did the real-tree "not everything is reached" pin.
- The decorated-definition seed dropped: the tmp-tree decorated pin went red
  and nothing else did — on the real tree every listed symbol is also reached
  through `create_app` or `run_loop.main`. The seed is kept for the case the
  pin describes (a handler nothing names), not for today's list, and the
  docstring says so.

Every file was restored byte-for-byte after each mutation.

## 4. What the deletion does to the billed-path guards

ADR 0040 §4.1 measured deleting the Historian as *the loss of the only
exercise the fail-closed billed-path mechanism ever had*. That measurement was
right and the cost is taken knowingly:

- `_unmetered_but_unreachable()` — the derived permission for a quarantined,
  unreachable module to hold an unmetered `structured_call` — has **no
  member**. It is kept as the shape a future quarantined caller would be
  judged by, and its docstring says nothing exercises it.
- `test_the_unmetered_callers_are_exactly_the_quarantined_ones` asserted
  `unmetered == {"backend/agents/historian.py"}` and then a subset check that
  would have become `set() <= anything`. It is replaced by
  `test_every_caller_of_the_billed_path_is_metered`, which asserts the
  tighter statement the deletion made true: **no** module is permitted an
  unmetered call. Mutation: a `structured_call()` placed in `budget.py` turned
  it and `test_every_call_site_of_the_billed_path_is_allowlisted` red.
- The reference-kind branch of `_billed_path_sites` has no production
  exemplar: `review.py`'s `client_factory=build_client` default was the one
  production *reference* rather than call, pinned so a call-only scanner could
  not pass by finding nothing. The pin now points at the desk's call sites;
  the branch itself still fires (mutation: `factory = build_client` in
  `budget.py` — red, reported as `(reference)`). A production reference is not
  manufactured to keep the old pin.

## 5. Recorded here and deliberately not fixed

**5.1 Prompt caching is plausibly off on live, and the cost is unmeasured.
HELD.** `AGENT_MODEL` on live is `claude-sonnet-5` (`fly.live.toml`, ADR 0071
§2.7) while `base.DEFAULT_MODEL`, `.env.example:428` and every test see
`claude-opus-5`. `.env.example:419-427` warns that Sonnet's minimum cacheable
prefix is 1024 tokens against Opus 5's 512, and that the prefixes measured on
2026-08-08 were 738-985 — **for prompts that no longer exist**. The desk's own
four prefixes have never been counted. `base.py:384-400` records the trade as
accepted (a Sonnet call uncached is cheaper than an Opus call cached). Whether
that is true at the desk's actual prefix lengths is one free run of the
re-pointed script away (`AGENT_MODEL=claude-sonnet-5
scripts/measure_agent_cache_prefix.py`); it spends no tokens and was not run
in this lane because it needs `ANTHROPIC_API_KEY` in the environment. Held,
not decided.

**5.2 No captured Anthropic payload exists anywhere in the repo.** CLAUDE.md's
convention — *wire-format tests load captured payloads from `tests/fixtures/`,
never hand-constructed ones* — is unsatisfied on the one path that spends
money. `tests/fixtures/` holds nothing Anthropic-shaped; every test of
`structured_call` and of the desk uses a hand-written stub (`StubClient`,
`StubResponse`). This ADR records the gap and does not close it: capturing a
payload costs a real call, and which call to capture (a staff scout with
web-search blocks, or the master) is a decision about the fixture's scope
that this lane was not asked to take.

**5.3 The walker's first finding on the real tree, not acted on.** With
`review_surfaced` gone, `AgentBudget.allowance` has **no caller outside
tests** — the desk gates on `refusal_reason` and reserves directly. The same
walk lists `study_stop_fired`, `loop_failures_since`, `prices.cents_to_tenths`,
`runner.reset_walk_alarm`, `attention.seen_at_least_once_since` and
`alerts.check_fee` with no production caller, and `discover_from_events`
called only from laptop scripts. `budget.py` is needed in full by the live
desk and nothing in it was deleted; the rest is outside this lane. The
walker's docstring says why it is a finding and not a guard.

**5.4 Stale copies outside this lane's permission**, for the integrator:
`.env.example:405-410` still explains the Skeptic and the Historian as seats
that cannot spend (integrator-only file); `fly.live.toml:42-52,336,377` cite
the Skeptic as history and are correct as dated; `tests/test_has_callers.py:1399`
says the desk makes "at most three" calls inside the `scout_desk.py`
allowlist entry, which sits between this lane's hunk and Lane B's and was left
alone.

## 6. What this does not establish

- **What the eight convenings, or the 24 Skeptic calls, cost in dollars.**
  ADR 0062 §4 closed the invoice question and it is not reopened. The count is
  the reliable quantity.
- **Whether any briefing moved a bet.** `scout_briefings` records that the
  desk was sent; nothing joins it to a fill, and ADR 0105 found the desk is
  read, not transacted through.
- **`count(agent_calls)` on the live volume.** Not read.
- **That the unreached set in §5.3 is dead.** The walk over-approximates
  reachability and cannot also be the authority on death; each name there
  needs its own look before anyone deletes it.
- **That prompt caching is off on live.** §5.1 says *plausibly*; the
  instrument exists and has not been run against the deployed model.

## 7. Consequences

- `backend/agents/` describes what runs: a scout desk with four metered
  seats, its meter, and the retired seam. No module in it can spend without
  appearing in `BILLED_PATH_CALL_SITES`.
- A symbol whose only referrer is dead is a red test, not a fifteen-day
  silence. The lesson is written in `tasks/lessons.md`, 2026-09-05, in
  pattern form.
- ADR 0071 §3's open question on the desk is closed by a dated read with its
  instrument named, and the four stale copies in the tree say the same thing.
- **Lesson, pattern form:** *a module can be import-reachable and dead, so
  "nothing imports it" is a sufficient reason to delete and never a necessary
  one* — and a caller check is only as deep as the walk behind it.
