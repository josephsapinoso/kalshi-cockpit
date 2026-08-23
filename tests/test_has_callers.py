"""Every module on the critical path must be reachable from something that runs.

This project has now shipped the same defect three times: a module written to
completion, tested thoroughly, recorded as done in `tasks/todo.md`, and called
by nothing.

    analysis/clv.py        ~40 tests. Nothing ever called `score_recommendations`,
                           so no row could be scored and the gate's counter was
                           structurally pinned at zero for the project's life.
    notify/discord.py      ~20 tests. Not imported anywhere. The only match for
                           "discord" in the codebase was the word "discordant"
                           in `backtest.py`.
    backend/agents/*       ~40 tests implying a safety layer. Half of it was
                           wired up on 2026-08-08 -- `review`, `skeptic` and
                           `base` reach the chain through `runner.py:505`. The
                           other half, `scout` and `historian`, never was, and
                           is quarantined below rather than left to read as
                           part of a shipped fleet.

The failure has no line number. Every file is individually excellent, coverage
goes up, and the missing thing is the *absence of a call* -- which no reviewer
reads and no coverage tool reports, because the untested code does not exist.

The cheap detector was already written down in `tasks/lessons.md`:

    grep -rn "score_recommendations" --include=*.py .
    # if every hit is tests/ or a seeder, the feature does not exist yet

This is that grep, run by CI instead of by memory.

Opt-in lists only ratchet, they never discover
----------------------------------------------
`MUST_HAVE_CALLERS` below is a list of symbols someone remembered to add. Every
entry on it already had a caller when it was added: it exists so that a symbol
which *had* one cannot quietly lose it. That is a genuine guarantee and it is
worth keeping -- but it is the wrong shape for finding the defect in the first
place, because a symbol nobody thought about is a symbol nobody adds.

Measured 2026-08-10: **nine** production modules were unreachable from anything
the deployed image executes, and **zero** of them were on this list. In fifteen
entries the list had never once been extended to something that was orphaned at
the time of writing. An allowlist cannot report what is missing from it.

So the module-level half below is inverted: it **enumerates** every module under
`backend/`, computes which ones the deployed entry points can actually reach,
and requires every unreachable module to carry an explicit disposition. An
unclassified orphan fails. Nobody has to remember anything.

Two holes this closes, both found the same day
----------------------------------------------
1. **`scripts/` counted as a caller, but `.dockerignore` ships two of them.**
   `scripts/*` is excluded with a hand-kept `!` allowlist naming only
   `run_loop.py` and `migrate_db.py`, so 32 of the 34 scripts do not exist on
   the deployed machine. A module whose only caller was `demo_builder.py` read
   as "called" here and was absent from the running system -- the test's
   definition of "called" and the deployment's definition of "exists" disagreed,
   silently. This is the repo's recurring two-limits shape (`tasks/lessons.md`,
   2026-08-07): one guard covering half a property reads exactly like a guard
   covering all of it. Reachability below is rooted in what `entrypoint.sh`
   actually runs, derived from the script rather than listed here.

2. **Import counted as use.** A module the API imports and never calls passed.
   Kept deliberately for module-level reachability, where import *is* the
   relation that matters -- module-level code runs. Narrowed for the symbol
   list: `MUST_HAVE_CALLERS` now demands a reference outside the import
   statement, so a stale `from x import y` no longer stands in for a caller.

Deny-by-default over the call sites of a billed function
--------------------------------------------------------
The last section of this file is the *opposite* shape to `MUST_HAVE_CALLERS`,
and the difference has to be stated because ADR 0022's central complaint was
about allowlists.

That complaint was precise: `MUST_HAVE_CALLERS` "cannot report what is missing
from it". It is an allowlist of *symbols someone remembered*, drawn from an
unbounded population -- every symbol in the repo -- so an omission is invisible
and the check fails **open**. `BILLED_PATH_CALL_SITES` is an allowlist over a
population the scanner **enumerates itself**: every call of, and every reference
to, `structured_call` and `build_client` in production sources. Nothing has to
be remembered because nothing can be omitted -- a new call site is found by the
walk and fails for not being on the list. It fails **closed**. A future reader
should not file it under the pattern ADR 0022 condemned; it is the inversion of
that pattern, applied to call sites of a dangerous function rather than to
modules.

Why this exists rather than a meter inside `structured_call`
------------------------------------------------------------
`7b2252d` put a spend ceiling on `review_surfaced`, and an audit found the meter
is per-*caller*, not per-*call*: `structured_call` and `build_client` carry no
ceiling in their signatures, so a second caller starts unmetered by default.
Moving the meter down into `structured_call` was assessed and **rejected** --
the allowance is a batch question. `review_surfaced` must know it *before* the
fan-out in order to mark the rows it cannot afford `skeptic_unreviewed`; a
per-call refusal could only return `None`, which `apply_verdict` reads as "no
opinion", erasing the distinction between "nobody looked" and "the Skeptic
looked and had nothing". This file is the cheaper enforcement instead: it cannot
make the path metered, but it can make the *arrival of an unmetered caller* a
red test rather than an invoice.

Scout and Historian are permitted, and the permission is derived
---------------------------------------------------------------
`backend/agents/scout.py` and `backend/agents/historian.py` both call
`structured_call` today and neither is metered. They are not hand-waved onto the
allowlist. The allowed set is `BILLED_PATH_CALL_SITES` **plus** the modules that
`DISPOSITIONS` classifies `QUARANTINED` *and* that `reachable_modules()` cannot
reach -- computed, both halves, at assertion time. So the permission is exactly
the ADR 0022 invariant: an unmetered call site is tolerated only while the
deployed entry points provably cannot get to it. Wire Scout into the chain and
it stops being unreachable, so it drops out of the allowed set and turns *this*
test red for spending money, at the same moment it turns
`test_a_quarantined_module_has_not_been_wired_up_by_the_back_door` red for
escaping quarantine. Two independent guards, and the money one no longer depends
on someone remembering to also edit a list here.

What this does not establish
----------------------------
That the caller is reached at *runtime*. A function imported by a module nobody
runs still passes the symbol half here. Module reachability is import-based, so
a module imported behind a branch that never fires still counts as LIVE. It is
a floor, not a proof -- the behavioural tests beside it are what establish the
path actually executes.

And, for the billed-path ratchet specifically:

- **It does not make the path metered by construction.** `structured_call` and
  `build_client` still take no ceiling. The only claim is that the *set of
  callers* cannot grow in silence.
- **It is per module, not per call site.** An already-allowlisted module can
  gain a *second* call the batch meter never sees -- a retry loop, a two-stage
  prompt -- and stay green, because `AgentBudget` reserves one row per
  *candidate*, not per request. Verified by mutation on 2026-08-11: a second
  `structured_call` added inside `backend/agents/skeptic.py` left every
  assertion here **GREEN**. Recorded rather than closed: pinning a site count
  would go red on any honest refactor of a file already on the list, and the
  damage it guards against is the entry below, which is pinned at its own layer.
- **It would not have caught the `max_retries` defect.** That was an unmetered
  request *multiplier* inside an allowlisted caller: one `structured_call` from
  `skeptic.py` became up to three billed HTTP requests, because the SDK's
  `DEFAULT_MAX_RETRIES = 2` was in force and the meter still counted one. No
  call site appeared and none moved, so nothing in a call-site enumeration could
  see it. `test_build_client_asks_the_sdk_not_to_retry` pins that separately, at
  the constructor, where it actually lives.
- **It does not establish that the SDK is reached only through `base.py`.** It
  is not: `scripts/measure_agent_cache_prefix.py:64` constructs
  `anthropic.Anthropic()` directly. That file is excluded from the image by
  `.dockerignore` and only calls `messages.count_tokens`, but the enumeration
  here is over two named functions rather than over the SDK, so a module that
  imports `anthropic` and bills it directly is outside what this can see.
"""

from __future__ import annotations

import ast
import fnmatch
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Directories that do not count as a caller. A feature called only by its own
# tests and its own demo seeder is a feature that has not shipped.
#
# `.claude/worktrees` is here for a sharper reason than the others, and it is
# the one that would let this whole file pass over the bug it exists to catch.
# A parallel lane's worktree is a full second copy of the repo. Walking it means
# a symbol whose only caller lives in *another branch's* copy counts as called
# here -- so during any parallel session this test can go green on `main` for a
# symbol that has no caller on `main`. That is precisely the state
# `score_recommendations` was in for eleven build steps.
#
# It is also why the file was flaky: a lane writing to its worktree mid-walk
# makes `rglob` yield a path that no longer exists by the time it is read, which
# surfaced as `FileNotFoundError` on an unrelated symbol. The crash was the
# cheap symptom; the silent pass is the expensive one.
NOT_A_CALLER = (
    "tests",
    "warehouse",
    ".venv",
    "node_modules",
    "__pycache__",
    ".claude",
)

# The seeder is not a caller either, for the same reason tests are not: it is
# what `persist_recommendation` had for eleven build steps while the chain that
# was supposed to call it did not exist.
NOT_A_CALLER_FILES = ("backend/seed_demo.py",)

# (symbol, why it matters if it goes uncalled again)
MUST_HAVE_CALLERS = [
    (
        "poll_portfolio_forever",
        "the venue's portfolio record demonstrably expires (settlements lost "
        "55 records inside eight days; fills retain ~3 months), so a poller "
        "that nothing starts is a record silently rotting on a schedule -- "
        "and the registered gap tripwires read poll_log, which only a running "
        "loop writes",
    ),
    (
        "fetch_props",
        "MLB player props are never bought, so the whole prop half of the "
        "pipeline -- discovery, the inherited link, the per-(player, line) "
        "devig -- runs against an empty `odds_snapshots` and reports a clean "
        "zero. It shipped in this exact state on 2026-08-14: complete, tested, "
        "and referenced only by `tests/test_odds.py`",
    ),
    # `prop_quotes_for_event` and `_price_prop_event` deliberately are NOT
    # listed. Both are defined and called inside `runner.py`, and every check
    # below requires a referrer *outside* the defining module -- so listing them
    # would fail for a reason that has nothing to do with reachability. Their
    # call sites are held by the offline end-to-end test in
    # `tests/test_runner.py` and by the mutation battery, which is the right
    # instrument for a same-module edge.
    (
        "score_recommendations",
        "nothing can be scored, and the gate's 300-game counter stays at zero "
        "however long the system runs",
    ),
    (
        "report_from_connection",
        "`GET /api/signal` goes back to having nothing to serve, and `beta` -- "
        "the project's registered decision-bearing statistic -- returns to "
        "being producible only by a human running a script on a laptop against "
        "an ssh dump. That was the state ADR 0039 ended: the product stated a "
        "conclusion about whether the signal works and stated its measured "
        "worth nowhere, on a tool operated from a phone",
    ),
    (
        "persist_if_changed",
        "the evidence record stops growing while every screen keeps rendering",
    ),
    (
        "decide_sweeps",
        "the odds budget goes on whichever pass runs first, and the actionable "
        "window lands wherever the process happened to restart",
    ),
    (
        "window_status",
        "the Board cannot say whether anything on it can be acted on",
    ),
    (
        "record_sweep_outcome",
        "a refused sweep goes back to leaving no row in any table, and silence "
        "becomes indistinguishable from a system that never looked -- which is "
        "how odds fetching stopped on 2026-08-09 and ran 17+ hours behind a "
        "green health check",
    ),
    (
        "DiscordNotifier",
        "no alert reaches a phone, and the window is open for fifteen minutes "
        "twice a day",
    ),
    (
        "Alerter",
        "the notifier exists and nothing decides when to use it -- exactly the "
        "state this file exists to detect",
    ),
    (
        "check_feed",
        "a dead WebSocket is the one failure the Board cannot show -- prices "
        "stop moving and a stale number renders identically to a fresh one, so "
        "a broken feed makes the cockpit look CALM. Before 2026-08-18 the only "
        "failure alert with a caller needed five consecutive pass failures, "
        "which a container crash-loop skips entirely",
    ),
    (
        "check_credits",
        "odds fetches stop and the Board simply stops producing rows, which "
        "looks exactly like a quiet slate. `DiscordNotifier.credits_exhausted` "
        "was complete and referenced only by tests for the life of the project",
    ),
    (
        "run_settlement_pass",
        "no paper position ever closes, so paper exposure only ratchets up "
        "until the order endpoint refuses everything -- a cap that can only "
        "close is an off switch, which is exactly why ADR 0008 declined to "
        "count paper exposure at all",
    ),
    (
        "run_scoring_pass",
        "closing lines are never fetched, so `score_recommendations` has "
        "nothing to score even once it is called",
    ),
    (
        "run_market_result_pass",
        "`kalshi_markets.result` goes back to being NULL for every row, as it "
        "was for the project's life, and calibration can only ever be measured "
        "against `settlements` -- which reads `orders`, where the only writers "
        "are the auth-gated endpoint and the demo seeder",
    ),
    (
        "run_quote_pass",
        "the loop runs on the odds cadence alone, so every row is bettable for "
        "thirty seconds after the pass that wrote it and the tool is actionable "
        "for about a minute a day",
    ),
    (
        "live_ages",
        "the Board and the order endpoint go back to computing freshness by two "
        "separate paths, which is how a screen comes to offer a row the server "
        "refuses",
    ),
    (
        "Tempo",
        "nothing chooses between the two cadences, so either Kalshi is polled "
        "4,300 times a day or it is polled twice",
    ),
    (
        "quote_refresh_survives_interval",
        "the composed window goes unchecked again -- three defensible limits "
        "whose product is a tool nobody can use, with no module holding more "
        "than one of them",
    ),
    (
        "apply_verdict",
        "`backend/agents/*` goes back to being ~40 green tests implying a "
        "safety layer that can block nothing -- the fourth module in this "
        "project to be complete, tested, and called by nothing",
    ),
    # `review_surfaced` was an entry here from 2026-08-08 to 2026-08-21, when
    # ADR 0062 retired it as the pass default: a metered LLM re-attacking an
    # edge surface that no longer determines anything was spend against a
    # decision nobody makes (24 Opus calls in 4m22s on 2026-08-16, all
    # blocked). It is now opt-in only -- kept importable as the one metered
    # reviewer implementation, exercised by `test_agent_wiring.py` /
    # `test_agent_budget.py` as an *injected* reviewer -- so by this file's
    # definition it has no production caller, deliberately. What replaced the
    # ratchet on it: the entry below on its replacement, and
    # `TestTheScheduledSkepticIsRetired`, which goes red if the default is
    # flipped back (mutation-verified 2026-08-21).
    (
        "review_retired",
        "the pricing pass falls back to whatever reviewer someone wires next "
        "-- and the last time that seam was wired by default it billed the "
        "whole daily Opus cap in 4m22s guarding a decision nobody makes "
        "(ADR 0062 SS3)",
    ),
]

# Two symbols are deliberately NOT above, and it is worth saying why rather than
# leaving their absence to be read as an oversight. `confirm_recommendation` and
# `store.db.migrate` are each called only from the module that defines them --
# by `persist_if_changed` and `init_db` respectively, both of which *are* on the
# list. Adding them would fail this file for the wrong reason: they are reached,
# through an entry point already checked here. What guards them is behavioural,
# and each was verified by disabling it: `test_an_unchanged_row_is_confirmed_
# rather_than_left_to_rot` and `TestMigration`.


def production_sources() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if any(part in NOT_A_CALLER for part in rel.split("/")):
            continue
        if rel in NOT_A_CALLER_FILES:
            continue
        files.append(path)
    return files


def _defines(tree: ast.AST, symbol: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == symbol
        for node in ast.walk(tree)
    )


def _uses(tree: ast.AST, symbol: str) -> bool:
    """Whether the symbol is referenced in *code*.

    Parsed rather than grepped, and that is not fastidiousness. The first
    version of this file matched the source text and reported
    `persist_recommendation` as called from `backend/runner.py` -- where the
    only occurrence is a docstring explaining that nothing calls it. A detector
    for orphaned code that counts prose about orphaned code as evidence of a
    caller is worse than no detector, because it reads as a passing check.

    Imports count as a use on purpose: a module the entrypoint imports is wired
    in even when the call sits behind a branch, and the alternative -- demanding
    a syntactic call -- would fail on every dependency-injected caller in this
    repo.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == symbol:
            return True
        if isinstance(node, ast.Attribute) and node.attr == symbol:
            return True
        if isinstance(node, ast.alias) and symbol in (node.name, node.asname):
            return True
    return False


def callers_of(symbol: str) -> list[str]:
    """Production files that use the symbol, excluding the one that defines it."""
    hits: list[str] = []
    for path in production_sources():
        try:
            tree = ast.parse(path.read_text("utf-8", errors="replace"))
        except SyntaxError:                                   # noqa: PERF203
            continue
        if _defines(tree, symbol):
            continue
        if _uses(tree, symbol):
            hits.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return hits


@pytest.mark.parametrize(
    "symbol,consequence", MUST_HAVE_CALLERS, ids=[s for s, _ in MUST_HAVE_CALLERS]
)
def test_the_symbol_is_used_outside_its_own_module_and_tests(symbol, consequence):
    hits = callers_of(symbol)
    assert hits, (
        f"`{symbol}` is defined, tested, and called by nothing outside "
        f"tests/. If that stands, {consequence}. See tasks/lessons.md: "
        f"'Code with no caller is not a feature, it is a plan'."
    )


@pytest.mark.parametrize(
    "symbol,consequence", MUST_HAVE_CALLERS, ids=[s for s, _ in MUST_HAVE_CALLERS]
)
def test_the_caller_is_a_file_that_exists_on_the_deployed_machine(symbol, consequence):
    """Hole 1, closed for the symbol list.

    `callers_of` counts any production file, and `scripts/` is production by
    that definition. It is not production by `.dockerignore`'s definition:
    `scripts/*` with a two-entry `!` allowlist means 32 of the 34 scripts are
    absent from the image. So a symbol whose only caller is `demo_builder.py`
    satisfied the test above while being unreachable on the instance -- the
    exact state the file exists to detect, passing the file that detects it.

    Deliberately a *separate* test from the one above rather than a tightening
    of it, because the two failures want different fixes: no caller at all
    means the feature was never wired, while a non-shipping caller means it was
    wired to a laptop.
    """
    shipping = [c for c in callers_of(symbol) if not _excluded_from_image(c)]
    assert shipping, (
        f"`{symbol}` has callers, but every one of them is excluded from the "
        f"container image by .dockerignore: {callers_of(symbol)}. On the "
        f"deployed machine those files do not exist, so {consequence}"
    )


def _excluded_from_image(rel_path: str) -> bool:
    return _is_ignored(rel_path, _dockerignore_patterns())


def _uses_beyond_import(tree: ast.AST, symbol: str) -> bool:
    """Hole 2, narrowed: a reference that is not merely an `import` binding.

    `_uses` counts `ast.alias`, so `from x import y` alone reads as a caller.
    That is right for module reachability -- importing a module runs it -- and
    wrong for a symbol, where a stale import is the residue of a caller that
    was deleted. `review_retired` passes this because `runner.py` names it as
    a parameter default, which is a reference; a forgotten import would not.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == symbol:
            return True
        if isinstance(node, ast.Attribute) and node.attr == symbol:
            return True
    return False


@pytest.mark.parametrize(
    "symbol,consequence", MUST_HAVE_CALLERS, ids=[s for s, _ in MUST_HAVE_CALLERS]
)
def test_the_caller_does_more_than_import_the_symbol(symbol, consequence):
    referrers = []
    for path in production_sources():
        try:
            tree = ast.parse(path.read_text("utf-8", errors="replace"))
        except SyntaxError:                                   # noqa: PERF203
            continue
        if _defines(tree, symbol):
            continue
        if _uses_beyond_import(tree, symbol):
            referrers.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    assert referrers, (
        f"`{symbol}` is imported somewhere and referenced nowhere -- a stale "
        f"`from ... import` standing in for a caller that was deleted. If that "
        f"stands, {consequence}"
    )


# ---------------------------------------------------------------------------
# The same question, one level down: does anything supply the ARGUMENT?
# ---------------------------------------------------------------------------
# `MUST_HAVE_CALLERS` asks whether a function is reached. That is not the only
# way a control can be wired to nothing, and on 2026-08-10 this project found
# the other way.
#
# `size_position` has been called from four production sites since it was
# written. Its daily-loss kill switch is correct, is tested, and fires exactly
# at the boundary when it is handed a number. It was never handed one:
# `daily_pnl_dollars` was keyword-only with a default of `0.0`, and instrumenting
# the sizer across the whole suite found 1,358 calls of which exactly **one**
# carried a non-zero value -- from `tests/test_engine.py`. Driven end to end at
# the `fly.live.toml` profile against 40 settled positions totalling -$20,000
# realised, `POST /api/orders` returned HTTP 200.
#
# The reason no test caught it is worth stating precisely, because it is the
# fifth guard-that-cannot-fail this project has found in two sessions:
# `tests/test_ev_sizing.py::test_the_daily_loss_kill_switch_refuses` passes
# `daily_pnl_dollars=-100.0` **itself**. It could never go red, because the
# production question -- *does anything supply this?* -- is not the question it
# asks. **A test that constructs the parameter it is checking cannot detect
# that no caller constructs it.**
#
# So: the same grep, one level down. Not "is the function called" but "is the
# argument passed, at every call site, and by at least one caller that computed
# it rather than writing a literal".

# (function, parameter, why it matters if nothing supplies it)
MUST_BE_SUPPLIED = [
    (
        "size_position",
        "daily_pnl_dollars",
        "the daily loss kill switch is applied to a number the sizer invented, "
        "and an account $20,000 down places orders at full size",
    ),
    (
        "size_position",
        "current_position_dollars",
        "`max_position_dollars` is applied to a number the sizer invented -- "
        "measured, 76 contracts and ~$38.00 accumulated on ONE ticker against a "
        "$10 cap, stopped only by the $40 portfolio cap",
    ),
    (
        "build_recommendation",
        "daily_pnl_dollars",
        "every card on the Board is sized as though nothing had been lost "
        "today, so the screen offers bets the order endpoint will refuse",
    ),
    (
        "build_recommendation",
        "current_position_dollars",
        "the Board sizes every market as though nothing were held on it",
    ),
    (
        "price_against",
        "daily_pnl_dollars",
        "the live ticker keeps quoting a bettable size after the kill switch "
        "has engaged -- the screen and the server disagreeing about money",
    ),
    (
        "price_against",
        "position_dollars",
        "the live ticker sizes every market as though nothing were held on it",
    ),
]


def _call_sites(function: str) -> list[tuple[str, int, set[str], set[str]]]:
    """Every production call of `function`, with the keywords it passes.

    Returns `(file, line, keyword_names, keywords_given_a_literal)`.

    Calls, not references: `ast.Call` only, so the `def` itself and any docstring
    naming the function are invisible. That distinction is why this can scan the
    defining module too -- `price_against` is called from `_on_book` inside the
    module that defines it, and excluding definers the way `callers_of` does
    would skip its only production call site entirely.
    """
    found: list[tuple[str, int, set[str], set[str]]] = []
    for path in production_sources():
        try:
            tree = ast.parse(path.read_text("utf-8", errors="replace"))
        except SyntaxError:                                   # noqa: PERF203
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else None
            )
            if name != function:
                continue
            keywords = {kw.arg for kw in node.keywords if kw.arg}
            literals = {
                kw.arg for kw in node.keywords
                if kw.arg and isinstance(kw.value, ast.Constant)
            }
            found.append((rel, node.lineno, keywords, literals))
    return found


@pytest.mark.parametrize(
    "function,parameter,consequence", MUST_BE_SUPPLIED,
    ids=[f"{f}:{p}" for f, p, _ in MUST_BE_SUPPLIED],
)
def test_every_production_call_site_supplies_the_parameter(
    function, parameter, consequence
):
    """One omission is enough. Three wired call sites and one defaulted one is
    not defence in depth, it is a hole with three signposts around it."""
    sites = _call_sites(function)
    missing = [
        f"{rel}:{line}" for rel, line, keywords, _ in sites
        if parameter not in keywords
    ]
    assert not missing, (
        f"`{function}` is called at {missing} without passing `{parameter}`. "
        f"If that stands, {consequence}. See tasks/lessons.md: an optional "
        f"safety parameter is a guard that cannot fail."
    )


@pytest.mark.parametrize(
    "function,parameter,consequence", MUST_BE_SUPPLIED,
    ids=[f"{f}:{p}" for f, p, _ in MUST_BE_SUPPLIED],
)
def test_at_least_one_caller_supplies_a_value_it_actually_measured(
    function, parameter, consequence
):
    """The test above, closed against its cheapest false pass.

    `daily_pnl_dollars=0.0` at every call site satisfies "the parameter is
    supplied" while reproducing the bug exactly -- it is the old default written
    out by hand. A literal is a *claim*, and there are places one is correct:
    `engine.build_recommendation` sizes the reference profile against a clean
    book on purpose, and the demo seeder's database genuinely holds nothing. So
    this does not ban literals; it requires that somewhere, at least one caller
    passes an expression it had to compute.
    """
    sites = _call_sites(function)
    computed = [
        f"{rel}:{line}" for rel, line, keywords, literals in sites
        if parameter in keywords and parameter not in literals
    ]
    assert computed, (
        f"every production call of `{function}` passes a hardcoded constant for "
        f"`{parameter}`. That is the pre-2026-08-10 default written out by "
        f"hand, and it fails in exactly the same way: {consequence}"
    )


class TestTheParameterScannerIsNotVacuous:
    """The guard on the guard.

    A scanner that found no call sites would pass every assertion above by
    checking nothing -- which is the shape of the defect this whole file exists
    to detect, reproduced in the detector. So the call sites it must find are
    named, and both directions of the literal test are shown to move.
    """

    def test_the_scanner_finds_the_call_sites_the_audit_found(self):
        files = {rel for rel, _, _, _ in _call_sites("size_position")}
        for expected in (
            "backend/engine.py", "backend/api/routes.py", "backend/live.py",
        ):
            assert expected in files, (
                f"`size_position` call sites were located in {sorted(files)}, "
                f"which does not include {expected}. The scanner has stopped "
                f"seeing a production caller, so every assertion above it is "
                f"passing by finding nothing to check."
            )

    def test_the_scanner_sees_more_than_one_site_per_file(self):
        """`build_recommendation` sizes twice inside one function -- the offer
        and the reference profile -- and only one of them may carry a literal.
        A scanner that collapsed a file to a single site could not tell."""
        engine = [
            line for rel, line, _, _ in _call_sites("size_position")
            if rel == "backend/engine.py"
        ]
        assert len(engine) >= 2, engine

    def test_a_literal_and_a_computed_value_are_told_apart(self):
        """Directly, on the real tree, because the distinction is the whole
        content of the second test and it is invisible if it never moves."""
        sites = _call_sites("size_position")
        literal_zero = [
            (rel, line) for rel, line, keywords, literals in sites
            if "daily_pnl_dollars" in literals
        ]
        computed = [
            (rel, line) for rel, line, keywords, literals in sites
            if "daily_pnl_dollars" in keywords
            and "daily_pnl_dollars" not in literals
        ]
        assert literal_zero, (
            "no call site passes a literal for `daily_pnl_dollars`, so the "
            "literal detector is not being exercised at all"
        )
        assert computed, (
            "no call site passes a computed `daily_pnl_dollars`, so the "
            "detector cannot distinguish the two"
        )


# ---------------------------------------------------------------------------
# The inversion: enumerate every module, classify every orphan.
# ---------------------------------------------------------------------------


def _entrypoint_commands() -> list[str]:
    lines = []
    for raw in (ROOT / "docker" / "entrypoint.sh").read_text("utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _module_path(dotted: str) -> str | None:
    """`backend.api.routes` -> `backend/api/routes.py`, if it exists."""
    for candidate in (
        dotted.replace(".", "/") + ".py",
        dotted.replace(".", "/") + "/__init__.py",
    ):
        if (ROOT / candidate).exists():
            return candidate
    return None


def deployed_entry_points() -> list[str]:
    """What `docker/entrypoint.sh` actually executes.

    Derived from the script rather than listed here, for the reason the
    `.dockerignore` check above is derived from it: a hand-kept copy of a list
    that lives somewhere else has failed twice in this repo already, the same
    way both times. A fifth entry point added to the boot sequence is covered
    without anyone remembering this file exists.
    """
    found: list[str] = []

    def add(path: str | None) -> None:
        if path and path not in found:
            found.append(path)

    for line in _entrypoint_commands():
        for dotted in re.findall(r"python\s+-m\s+([A-Za-z0-9_.]+)", line):
            if dotted != "uvicorn":
                add(_module_path(dotted))
        # `python -m uvicorn backend.api.routes:create_app --factory`
        for dotted in re.findall(r"uvicorn\s+([A-Za-z0-9_.]+):", line):
            add(_module_path(dotted))
        for script in re.findall(r"(scripts/[A-Za-z0-9_./-]+\.py)", line):
            add(script)
    return found


def _backend_imports(rel: str) -> set[str]:
    """Dotted `backend.*` names imported by one file, absolute and relative."""
    path = ROOT / rel
    try:
        tree = ast.parse(path.read_text("utf-8", errors="replace"))
    except (SyntaxError, FileNotFoundError):
        return set()

    dotted = rel[:-3].replace("/", ".")
    if path.name == "__init__.py":
        package = dotted[: -len(".__init__")]
    else:
        package = dotted.rsplit(".", 1)[0] if "." in dotted else dotted

    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                if node.level > 1:
                    base = base[: -(node.level - 1)]
                module = ".".join(base) + (f".{node.module}" if node.module else "")
            else:
                module = node.module or ""
            out.add(module)
            # `from backend.store import db` names a *module*, not a symbol.
            for alias in node.names:
                out.add(f"{module}.{alias.name}")
    return {name for name in out if name.split(".")[0] == "backend"}


def production_modules() -> list[str]:
    """Every module under `backend/`. The enumeration this file is built on."""
    return sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "backend").rglob("*.py")
        if "__pycache__" not in str(path)
    )


def reachable_modules() -> set[str]:
    """Transitive import closure of the deployed entry points.

    Import, not call: module-level code runs on import, and a module the API
    imports behind a branch that never fires is still present and still a
    dependency. The narrower question -- is the *function* called -- is what
    `MUST_HAVE_CALLERS` above answers.
    """
    known = set(production_modules())
    seen: set[str] = set()
    stack = list(deployed_entry_points())

    def push(rel: str | None) -> None:
        if rel and rel not in seen:
            stack.append(rel)

    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.add(rel)
        # A module's parent packages are imported before it is.
        parts = rel[:-3].replace("/", ".").split(".")
        for depth in range(1, len(parts)):
            push(_module_path(".".join(parts[:depth])))
        for dotted in _backend_imports(rel):
            target = _module_path(dotted) or _module_path(dotted.rsplit(".", 1)[0])
            if target:
                push(target)
                inner = target[:-3].replace("/", ".").split(".")
                for depth in range(1, len(inner)):
                    push(_module_path(".".join(inner[:depth])))

    return seen & known


class Tool:
    """Not on the deployed machine, and that is the point.

    A measurement harness or a demo. It is run by a human, deliberately, from a
    laptop -- so its absence from the image is correct rather than a defect,
    and the thing worth asserting is that the runner named here is real.
    """

    kind = "TOOL"

    def __init__(self, run_by: tuple[str, ...], purpose: str):
        self.run_by = run_by
        self.purpose = purpose


class Quarantined:
    """Complete, tested, wired to nothing, and deliberately left that way.

    Distinct from `Tool` because nobody runs these at all. Quarantine is a
    state this file recognises, not a comment: the module must stay unreachable
    (`test_a_quarantined_module_has_not_been_wired_up_by_the_back_door`), so
    connecting one to the chain turns this file red and forces the decision to
    be taken again in the open. For `scout` and `historian` that decision spends
    real money on every pass, which is not something that should arrive as a
    side effect of an import.

    **`revive_if` is prose, and the only thing checked is that it is non-empty.**
    That is a known hole rather than an oversight, and it has cost something
    already: the Historian's condition was "ADR 0021 §8 Option B or F is taken
    up", ADR 0034 took Option F, and nothing went red -- the module was never
    reconsidered, and ADR 0038 later expired the condition entirely. ADR 0022
    §4.1 worried that quarantine would decay into deletion; what actually
    happened is the mirror, quarantine decaying into permanence because the
    prompt to re-read stopped being readable. No cheap machine-readable trigger
    was available (no ADR here carries a `Superseded` status, so a test for one
    would pass by finding nothing), so the hole is recorded rather than closed
    with a guard that cannot fail. See ADR 0040 §3.
    """

    kind = "QUARANTINED"

    def __init__(self, reason: str, revive_if: str, adr: str):
        self.reason = reason
        self.revive_if = revive_if
        self.adr = adr


# Every module under `backend/` that the deployed image cannot reach. Anything
# unreachable and absent from this table fails
# `test_every_unreachable_module_is_classified` -- which is the whole point:
# the previous version of this file could only check symbols someone had
# thought to name, and nine orphans went unnamed for the project's life.
#
# ADR 0022 records how this list was arrived at and why nothing here was being
# wired up or deleted that night. For `scout.py` and `historian.py` that
# provisional "not tonight" is now a settled "not at all": **ADR 0040** closes
# ADR 0038's pre-commitment that the quarantined agents be "either wired or
# deleted", and takes neither. Read it before proposing to delete one -- the
# deletion was measured, and it costs the only exercise the fail-closed
# billed-path mechanism at the bottom of this file has ever had.
DISPOSITIONS: dict[str, Tool | Quarantined] = {
    # -- Tools ---------------------------------------------------------------
    # `backend/portfolio_poll.py` was here, as a Tool, for exactly one commit
    # (26090d1). It is now reached from `scripts/run_loop.py`, which the
    # entrypoint starts on the live instance, so the classification came out
    # the same day it went in -- the registration's 12h/5min cadence needs a
    # process that is always up, and a laptop is not one. The row is kept as a
    # comment because the deletion is the wiring being done.
    # `backend/analysis/signal_test.py` was here, as a Tool, and ADR 0039 moved
    # it out. It is now reached from `GET /api/signal` via
    # `backend/analysis/clv_signal.py`, and its entry lives in
    # `MUST_HAVE_CALLERS` below. The reasoning it was quarantined under --
    # "a rule that runs automatically on every pass is a rule that gets re-read
    # thousands of times" -- named the always-valid multiplier as the thing it
    # was protecting, and the multiplier is precisely the construction that
    # makes unlimited re-reading valid. The row is kept as a comment because the
    # deletion is the decision.
    "backend/main.py": Tool(
        run_by=("python -m backend.main --seed-demo",),
        purpose="Local dev server. Superseded on the instance by entrypoint.sh, "
                "which runs uvicorn against `routes:create_app` directly, so "
                "nothing in this file ever executes in production. Kept because "
                "it is how the UI is developed outside market hours.",
    ),
    "backend/store/publish.py": Tool(
        run_by=("python -m backend.store.publish",),
        purpose="Snapshots SQLite into the Parquet lake. A human step by "
                "design -- `analysis/marts.py` names this command in the error "
                "it raises when the warehouse is missing. Nothing on the "
                "instance runs it, which is why `data/lake/` still holds what "
                "someone published by hand. See ADR 0022 on that landmine.",
    ),
    "backend/analysis/joint_bound.py": Tool(
        run_by=("scripts/run_joint_bound.py", "scripts/run_clean_shortfall.py"),
        purpose="The measurement kernel behind the joint-bound result. Runs "
                "against the record after the fact; nothing in the money path "
                "consults it.",
    ),
    "backend/kalshi/combos.py": Tool(
        run_by=("scripts/demo_combos.py",),
        purpose="KXMVE combo lookup. Real product, measured (1,389 collections, "
                "13,806 legs), and not on the chain -- the cockpit prices "
                "single markets. Reachable only from a demo script.",
    ),
    "backend/model/strikeouts.py": Tool(
        run_by=(
            "scripts/price_pitcher_k_ladder.py",
            "scripts/measure_pitcher_k_decay.py",
            "scripts/measure_home_run_ladder_scope.py",
        ),
        purpose="The compound distribution that prices a whole `KXMLBKS` ladder "
                "from one opinion. Correct, tested, mutation-verified -- and "
                "off the chain **permanently, by measurement**: ADR 0036 "
                "refuted the parameter supply, not the arithmetic. Public rate "
                "data cannot pin `k_per_bf` closer than 6.09 points of ladder "
                "price against a 1.75-point fee bar, and that figure is an "
                "in-sample upper bound no implementation can beat. So there is "
                "no slice 3 and no `MUST_HAVE_CALLERS` entry coming. It is kept "
                "rather than deleted because it is the cheapest way to re-test "
                "that conclusion if a better parameter source ever appears -- "
                "the one open door being starters with no prior season, whom "
                "both measurements exclude by construction.",
    ),
    "backend/model/synthetic.py": Tool(
        run_by=("scripts/demo_builder.py",),
        purpose="Synthetic margin generator, documented as not-evidence. It "
                "must never reach the image: it manufactured a +28.4% EV "
                "teaser once already (`tasks/lessons.md`, 2026-08-06).",
    ),

    # -- Quarantined ---------------------------------------------------------
    # ADR 0040 declared quarantine the *settled* state for Scout and Historian,
    # closing ADR 0038's pre-commitment that they be "either wired or deleted".
    # **The Scout left quarantine on 2026-08-21 (ADR 0060), the third way ADR
    # 0040 did not enumerate: revived on the owner's word.** Joe asked for the
    # desk by name; `backend/agents/scout.py` is now the desk's schema module,
    # its unmetered solo `research()` was deleted rather than wired, and the
    # spending happens only in `backend/agents/scout_desk.py`, metered by
    # `AgentBudget` -- see BILLED_PATH_CALL_SITES. The Historian remains, now
    # the only member `_unmetered_but_unreachable()` has.
    "backend/agents/historian.py": Quarantined(
        reason="The weekly post-mortem. The last quarantined agent since the "
               "Scout's ADR 0060 revival; its importer is only "
               "`scripts/measure_agent_cache_prefix.py`, and "
               "`review` is called by nothing. It is the ONE writer of the "
               "`lessons` table, which is why deleting it is not a no-op: "
               "`backend/playbook.py` is live and reports "
               "`historian_has_run: false` precisely to keep 'the agent is "
               "unwired' distinct from 'the record holds no lessons', and "
               "`frontend/src/app/playbook/page.tsx` renders 'The Historian has "
               "never run'. Delete the module and the table has no writer at "
               "all, so that distinction collapses. Pinned by "
               "`test_no_lessons_says_the_historian_has_not_run`.",
        revive_if="a post-mortem loop is wanted over the *record* rather than "
                  "over a strategy -- ADR 0038 makes the record the product, "
                  "and summarising it is the one Historian job the closure did "
                  "not retire -- with the spend budgeted first. The previous "
                  "condition, 'ADR 0021 §8 Option B or F is taken up', is "
                  "retired because it FIRED and nothing noticed: ADR 0034 took "
                  "Option F, this module was not reconsidered, and no test went "
                  "red because `revive_if` is only ever checked for being a "
                  "non-empty string. ADR 0038 then expired B and F together. "
                  "See ADR 0040 §3 -- quarantine becoming permanent by decay is "
                  "the mirror of the failure ADR 0022 §4.1 guarded against.",
        adr="docs/adr/0040-quarantine-is-the-settled-state-for-scout-and-historian.md",
    ),
    "backend/model/elo.py": Quarantined(
        reason="The in-house power-ratings model. CLAUDE.md's opening section "
               "exists because this was twice described as a live second "
               "signal: `model_probability` is NULL on every row, and no "
               "suppression rule, sizing calculation, EV computation or gate "
               "condition consumes it.",
        revive_if="never, in the documented form. The design was a *conjunction* "
                  "-- surface where both signals agree -- and an AND-gate over "
                  "an already-empty set stays empty, so this cannot explain "
                  "`actionable = 0` away. Blending it into `fair_probability` "
                  "would move rows, but that is a new decision needing its own "
                  "ADR, not the completion of this one.",
        adr="docs/adr/0022-quarantine-the-orphaned-modules.md",
    ),
    "backend/model/backtest.py": Quarantined(
        reason="Scores `elo.py` against the closing line. Imported only by "
               "`tests/test_model.py`; it is the harness for a model that does "
               "not run, so it inherits that model's status exactly.",
        revive_if="`elo.py` is revived. Reviving this one alone would measure "
                  "nothing, and reviving `elo.py` without it would put an "
                  "unvalidated model on the money path -- they move together.",
        adr="docs/adr/0022-quarantine-the-orphaned-modules.md",
    ),
}


class TestEveryOrphanIsAccountedFor:
    """The inversion. An unclassified orphan fails; nobody has to remember.

    Verified by adding a deliberate orphan and watching it go red, per
    CLAUDE.md -- green here proves nothing, because an enumeration that
    enumerates nothing passes every assertion below.
    """

    def test_the_entry_points_are_read_off_the_boot_script(self):
        """Anchors everything else against vacuity.

        If this returned `[]`, `reachable_modules` would be empty, every module
        would read as an orphan, and the classification test would fail loudly
        -- which is the safe direction. The dangerous direction is the reverse:
        a bug that made everything reachable would silently retire the whole
        check. So assert the specific four, and that they are files.
        """
        entries = deployed_entry_points()
        assert "backend/api/routes.py" in entries, (
            "the API is not being read as an entry point, so every module "
            "reachable only from the API would read as an orphan"
        )
        assert "scripts/run_loop.py" in entries, (
            "the chain runner is not being read as an entry point"
        )
        for entry in entries:
            assert (ROOT / entry).exists(), f"{entry} is not in the repo"

    def test_reachability_actually_discriminates(self):
        """The guard on the guard.

        A closure that returned every module would pass the classification test
        by finding no orphans at all, and a closure that returned none would
        pass `test_a_quarantined_module_...` the same way. Both directions have
        to be shown to move.
        """
        reachable = reachable_modules()
        modules = set(production_modules())
        assert "backend/runner.py" in reachable, (
            "the chain runner's own module is not reachable -- the closure is "
            "not following imports"
        )
        assert "backend/model/elo.py" not in reachable, (
            "an unreferenced module is being reported as reachable, so this "
            "file can no longer detect an orphan at all"
        )
        assert reachable != modules, "nothing is being excluded"
        assert reachable, "nothing is being included"

    def test_every_unreachable_module_is_classified(self):
        """The opt-in failure, closed.

        Fifteen entries in `MUST_HAVE_CALLERS` and not one of them named a
        symbol that was orphaned when it was added. This is the test that would
        have found the nine.
        """
        orphans = sorted(set(production_modules()) - reachable_modules())
        unclassified = [m for m in orphans if m not in DISPOSITIONS]
        assert not unclassified, (
            f"{unclassified} cannot be reached from anything "
            f"`docker/entrypoint.sh` runs, and carry no disposition. That is "
            f"the state `analysis/clv.py`, `notify/discord.py` and "
            f"`backend/agents/*` were each in -- complete, tested, recorded as "
            f"done, and absent from the running system. Either wire it into the "
            f"chain, delete it, or add it to DISPOSITIONS as a Tool (a human "
            f"runs it) or Quarantined (nobody does, deliberately). See "
            f"docs/adr/0022-quarantine-the-orphaned-modules.md."
        )

    def test_a_quarantined_module_has_not_been_wired_up_by_the_back_door(self):
        """Quarantine as a state, not a comment.

        `scout` and `historian` cost money on every pass they run. `elo` is the
        signal CLAUDE.md has now had to correct the record about twice. None of
        the three should be able to join the chain because someone added an
        import while doing something else -- so reaching them turns this red and
        the decision has to be taken in the open, with an ADR.
        """
        reachable = reachable_modules()
        escaped = sorted(m for m in DISPOSITIONS if m in reachable)
        assert not escaped, (
            f"{escaped} are classified as not running and the deployed entry "
            f"points can now reach them. If that is deliberate, move them out "
            f"of DISPOSITIONS and give them entries in MUST_HAVE_CALLERS "
            f"instead -- and for `scout`/`historian`, budget the Anthropic "
            f"spend first: the bill is currently zero only because nothing is "
            f"surfaced."
        )

    def test_the_dispositions_table_has_no_stale_entries(self):
        """A row for a module that no longer exists is a comment, not a check."""
        missing = sorted(m for m in DISPOSITIONS if not (ROOT / m).exists())
        assert not missing, f"{missing} are classified but not in the repo"

    @pytest.mark.parametrize(
        "module", sorted(m for m, d in DISPOSITIONS.items() if d.kind == "TOOL")
    )
    def test_a_tool_names_a_runner_that_exists_and_does_not_ship(self, module):
        """`Tool` claims two things, and both are checkable.

        That a human can run it -- so the named runner has to be real. And that
        its absence from the image is *why* it is unreachable -- so a
        `scripts/` runner must genuinely be excluded by `.dockerignore`. If one
        were shipped, the module would be reachable on the instance and the
        classification would be wrong in the flattering direction.
        """
        tool = DISPOSITIONS[module]
        assert tool.run_by, f"{module} is a Tool that names no way to run it"
        assert tool.purpose.strip(), f"{module} gives no purpose"
        patterns = _dockerignore_patterns()
        for runner in tool.run_by:
            if runner.startswith("scripts/"):
                assert (ROOT / runner).exists(), (
                    f"{module} names {runner}, which is not in the repo"
                )
                assert _is_ignored(runner, patterns), (
                    f"{module} is classified as a laptop tool, but {runner} "
                    f"ships in the image -- so it is not a tool, it is a "
                    f"deployed caller, and this module should be LIVE"
                )
            else:
                assert module[:-3].replace("/", ".") in runner, (
                    f"{module}'s runner command {runner!r} does not name it"
                )

    @pytest.mark.parametrize(
        "module", sorted(m for m, d in DISPOSITIONS.items() if d.kind == "QUARANTINED")
    )
    def test_a_quarantined_module_says_what_would_bring_it_back(self, module):
        """Parking something without a revival condition is how it becomes
        permanent by default. The ADR has to exist, too -- a citation to a file
        nobody wrote is the same silence with a reference number on it."""
        entry = DISPOSITIONS[module]
        assert entry.reason.strip(), f"{module} is quarantined for no stated reason"
        assert entry.revive_if.strip(), (
            f"{module} has no revival condition, so nothing will ever prompt a "
            f"reader to reconsider it and quarantine becomes deletion by decay"
        )
        assert (ROOT / entry.adr).exists(), (
            f"{module} cites {entry.adr}, which does not exist"
        )


# The agent-fleet exception that used to live here is closed. It asserted the
# *current* state -- that `apply_verdict` had no caller -- so that wiring the
# fleet up would turn this file red and point at the list above. It did, on
# 2026-08-08, and `apply_verdict` and `review_surfaced` are now entries in
# MUST_HAVE_CALLERS rather than a documented exception beside it.


# ---------------------------------------------------------------------------
# The billed path: deny-by-default over every caller of the Anthropic seam.
# ---------------------------------------------------------------------------
# The two questions above are "is this reached" and "is the argument supplied".
# This is the third: **who can reach the thing that spends money**, and the
# answer has to be a closed set rather than a growing one.
#
# `7b2252d` capped the fan-out in `review.review_surfaced`. The cap is real and
# it is in the wrong layer to be a property of the path: `structured_call` and
# `build_client` have no ceiling in their signatures, and `AgentBudget` has
# exactly one caller. A second caller of either does not have to opt out of the
# meter -- it starts outside it. See the module docstring for why the meter was
# not simply moved down (the allowance is a batch question, and a per-call
# refusal is indistinguishable from "no opinion").
#
# So: enumerate, and deny by default. The docstring says at length why this is
# not the allowlist ADR 0022 condemned.

# The functions that reach Anthropic. `build_client` is included as well as
# `structured_call` because it is the constructor of the object that bills --
# a module that builds its own client is off the meter whether or not it goes
# through `structured_call` afterwards.
BILLED_PATH = ("structured_call", "build_client")

# Where they are defined. Excluded by *path* rather than by "any module that
# defines a function of this name", which is the tempting shortcut and is an
# open door: a module that declared its own `structured_call` -- a wrapper, a
# shim, a local rebinding -- would exclude itself from the scan by the very act
# that makes it worth scanning.
#
# The price is a false positive if some unrelated module ever defines a function
# called `structured_call`. That direction fails **closed**, costs one line in
# the allowlist with a reason beside it, and is the direction to be wrong in on
# a path that bills.
BILLED_PATH_SOURCE = "backend/agents/base.py"

# Modules permitted to reach the billed path, and what meters them.
#
# Deliberately NOT a list of `file:line`. A line number goes stale on any edit
# above it, and a test that has to be re-blessed for unrelated reasons is a test
# that gets re-blessed without being read. The module is the unit that a human
# decides about.
BILLED_PATH_CALL_SITES: dict[str, str] = {
    "backend/agents/skeptic.py": (
        "`evaluate` is the one Skeptic call, and it is metered by its caller: "
        "`review.review_surfaced` reserves one `agent_calls` row per candidate "
        "before the fan-out starts. This module is downstream of the ceiling, "
        "not outside it."
    ),
    "backend/agents/review.py": (
        "Holds the meter. `review_surfaced` computes `AgentBudget.allowance` "
        "before the batch and refuses what it cannot afford with "
        "`skeptic_unreviewed`, so it is the only place a fan-out width is "
        "chosen. `build_client` appears here as the `client_factory` default -- "
        "a reference rather than a call, which is exactly why the scanner below "
        "counts references too."
    ),
    "backend/agents/scout_desk.py": (
        "The scout desk (ADR 0060). `convene_desk` makes at most three "
        "`structured_call`s per convening and every one is metered by "
        "`AgentBudget` against the same `agent_calls` day as the Skeptic: the "
        "staff pair is affordability-checked and reserved before the first "
        "request, and the master is reserved only after a staff note exists. "
        "A refusal makes zero calls."
    ),
    "backend/api/routes.py": (
        "The desk's caller. `send_scout_desk` requires auth, re-checks "
        "`AgentBudget.refusal_reason` *before* accepting the request (a tap "
        "against an exhausted day answers 429 and spends nothing), and "
        "`build_client` is called only inside the background task that "
        "`convene_desk` -- the metered site above -- immediately consumes."
    ),
}


def _billed_path_sites(symbol: str) -> list[tuple[str, int, str]]:
    """`(file, line, kind)` for every production use of `symbol`, kind in
    `{"call", "reference"}`, outside `BILLED_PATH_SOURCE`.

    **References as well as calls, and that is not belt-and-braces.**
    `_call_sites` above matches `ast.Call` only, and `build_client` is never
    called by name in production: `review.py` passes it as the `client_factory`
    parameter *default* and the call goes through that local name. So an
    `ast.Call` scan finds **zero** sites for it and every assertion over them
    passes by checking nothing -- the exact vacuity this file exists to detect,
    reproduced in the detector, on the half of the pair that constructs the
    billing object. A factory handed around by name is still a caller.

    An `import` is not a use here (`ast.alias` is not matched), for the reason
    `_uses_beyond_import` gives: a stale import is the residue of a caller that
    was deleted, and it must not stand in for one.
    """
    found: list[tuple[str, int, str]] = []
    for path in production_sources():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel == BILLED_PATH_SOURCE:
            continue
        try:
            tree = ast.parse(path.read_text("utf-8", errors="replace"))
        except SyntaxError:                                   # noqa: PERF203
            continue

        # A matching `ast.Call` also contains a matching `ast.Name`; recording
        # both would report one site twice and, worse, would report a plain call
        # as though something were passing the function around.
        called_names: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else None
            )
            if name == symbol:
                called_names.add(id(func))
                found.append((rel, node.lineno, "call"))

        for node in ast.walk(tree):
            if id(node) in called_names:
                continue
            if isinstance(node, ast.Name) and node.id == symbol:
                found.append((rel, node.lineno, "reference"))
            elif isinstance(node, ast.Attribute) and node.attr == symbol:
                found.append((rel, node.lineno, "reference"))
    return found


def _unmetered_but_unreachable() -> set[str]:
    """Quarantined modules the deployed entry points cannot reach.

    The derived half of the allowed set. `historian.py` calls
    `structured_call` and nothing meters it -- tolerable only because
    ADR 0022 holds it off the chain, and that is a computed property here
    rather than a sentence: both halves, `QUARANTINED` **and** not in
    `reachable_modules()`, are evaluated at assertion time. Wiring one up
    removes it from this set on the same commit that makes it billable.
    (`scout.py` was this set's other member for the project's whole life;
    it left via ADR 0060, and its unmetered `research()` left with it.)
    """
    reachable = reachable_modules()
    return {
        module
        for module, disposition in DISPOSITIONS.items()
        if disposition.kind == "QUARANTINED" and module not in reachable
    }


class TestNothingNewCanReachTheBilledPath:
    """A ratchet on who can spend money, not on how much.

    What it buys: a module that starts calling Anthropic has to say so in a
    diff, beside the reason it is allowed to. What it does not buy is in the
    module docstring, and the shortest version is that it counts *callers*, not
    *requests* -- which is why the `max_retries` defect is pinned separately
    below rather than by this class.

    Verified by mutation, 2026-08-11, per CLAUDE.md -- green proves nothing on
    an enumeration, because one that enumerates nothing passes everything here:

    - `backend/agents/budget.py` (LIVE, not allowlisted) given a
      `build_client(...)` and a `structured_call(...)`:
      **RED** on both parametrizations of
      `test_every_call_site_of_the_billed_path_is_allowlisted`, and RED on
      `test_the_unmetered_callers_are_exactly_the_quarantined_ones`. Reverted.
    - A **second** `structured_call` added inside `backend/agents/skeptic.py`,
      which is allowlisted: **GREEN**, all seven. That is the per-module
      granularity limitation stated in the module docstring, observed rather
      than predicted. Reverted.
    - `backend/agents/budget.py` given its *own* `def structured_call` beside
      the call, i.e. the shadowing evasion `BILLED_PATH_SOURCE` exists to shut:
      **RED**. Under the tempting `_defines`-based exclusion this would have
      been green. Reverted.
    """

    @pytest.mark.parametrize("symbol", BILLED_PATH)
    def test_every_call_site_of_the_billed_path_is_allowlisted(self, symbol):
        allowed = set(BILLED_PATH_CALL_SITES) | _unmetered_but_unreachable()
        unexpected = sorted(
            f"{rel}:{line} ({kind})"
            for rel, line, kind in _billed_path_sites(symbol)
            if rel not in allowed
        )
        assert not unexpected, (
            f"`{symbol}` reaches Anthropic and is used at {unexpected}, which is "
            f"not an allowlisted caller. The ceiling from 7b2252d lives in "
            f"`review.review_surfaced`, not in this function's signature, so a "
            f"new caller starts **unmetered**: it can spend past "
            f"AGENT_MAX_CALLS_PER_DAY without `agent_calls` recording a row. "
            f"Either route it through `review_surfaced`, or add it to "
            f"BILLED_PATH_CALL_SITES with the meter that bounds it named."
        )

    def test_the_scanner_sees_the_sites_the_audit_found(self):
        """Anti-vacuity, and the reason `_billed_path_sites` counts references.

        An enumeration that enumerates nothing satisfies the test above on any
        tree at all. Both symbols are pinned, and they are pinned in different
        *kinds* on purpose: `structured_call` is invoked, `build_client` is
        handed over as a factory default and never invoked by name anywhere in
        production. A call-only scanner reports zero sites for the second one.
        """
        source = ast.parse((ROOT / BILLED_PATH_SOURCE).read_text("utf-8"))
        for symbol in BILLED_PATH:
            assert _defines(source, symbol), (
                f"`{symbol}` is no longer defined in {BILLED_PATH_SOURCE}. This "
                f"file is scanning for a name that has moved, so it is watching "
                f"an empty seam while the real one is somewhere else."
            )

        calls = _billed_path_sites("structured_call")
        assert any(
            rel == "backend/agents/skeptic.py" and kind == "call"
            for rel, _, kind in calls
        ), (
            f"`structured_call` sites were located at {calls}, which does not "
            f"include a call from backend/agents/skeptic.py. The scanner has "
            f"stopped seeing the one metered caller, so the allowlist above is "
            f"passing by finding nothing."
        )

        factory = _billed_path_sites("build_client")
        assert any(
            rel == "backend/agents/review.py" and kind == "reference"
            for rel, _, kind in factory
        ), (
            f"`build_client` sites were located at {factory}, which does not "
            f"include a reference from backend/agents/review.py:245 -- the "
            f"`client_factory` default. If this scanner ever counts calls only, "
            f"it finds zero sites for `build_client` and guards nothing."
        )

    def test_the_allowlist_names_modules_that_exist(self):
        """A row for a module that has been renamed away is a comment."""
        missing = sorted(m for m in BILLED_PATH_CALL_SITES if not (ROOT / m).exists())
        assert not missing, f"{missing} are allowlisted but not in the repo"
        for module, reason in BILLED_PATH_CALL_SITES.items():
            assert reason.strip(), f"{module} is allowlisted with no stated meter"

    def test_the_unmetered_callers_are_exactly_the_quarantined_ones(self):
        """The substance of the scout/historian decision, asserted.

        They are allowed to hold an unmetered `structured_call` **only** while
        nothing on the instance can reach them. If the derived set ever went
        empty this whole permission would evaporate silently in the safe
        direction (the test above would go red), but the dangerous direction is
        the reverse: a quarantined agent becoming reachable while still counting
        as permitted. That cannot happen -- `_unmetered_but_unreachable`
        recomputes reachability -- and this asserts the set is populated by the
        two modules the audit actually found, so the mechanism is exercised.
        """
        unmetered = {
            rel for rel, _, _ in _billed_path_sites("structured_call")
            if rel not in BILLED_PATH_CALL_SITES
        }
        assert unmetered == {
            "backend/agents/historian.py",
        }, (
            f"the unmetered callers of `structured_call` are {sorted(unmetered)}, "
            f"not the one quarantined agent still parked (the Scout left via "
            f"ADR 0060, and its `research()` was deleted rather than allowed "
            f"to stand unmetered). If a module has "
            f"left this set it should be in BILLED_PATH_CALL_SITES with its "
            f"meter named; if one has joined, it is spending money with nothing "
            f"counting."
        )
        assert unmetered <= _unmetered_but_unreachable(), (
            f"{sorted(unmetered - _unmetered_but_unreachable())} call "
            f"`structured_call` with no meter and are now reachable from a "
            f"deployed entry point. Anthropic spend has arrived on the instance "
            f"as a side effect of an import -- see ADR 0022 §4."
        )


def _sdk_constructor_kwargs() -> dict[str, ast.expr] | None:
    """The keywords `build_client` passes to the SDK constructor, by AST.

    `None` when no constructor call can be found inside `build_client` at all,
    which the caller must treat as a failure rather than as "no keywords": a
    renamed or relocated constructor would otherwise retire the assertion below
    while leaving it green.
    """
    tree = ast.parse((ROOT / "backend" / "agents" / "base.py").read_text("utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "build_client":
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            name = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name)
                else None
            )
            if name in ("AsyncAnthropic", "Anthropic"):
                return {kw.arg: kw.value for kw in call.keywords if kw.arg}
    return None


class TestTheRequestMultiplierIsPinnedAtTheConstructor:
    """The thing the call-site ratchet above structurally cannot see.

    A caller is a caller whether it makes one HTTP request or three. The count
    the meter records is *candidates*; the count the invoice records is
    *requests*; and exactly one keyword argument makes those the same number.
    The installed SDK (`anthropic` 0.120.2) defaults to `DEFAULT_MAX_RETRIES =
    2` and retries 408/409/429/>=500 and connection errors, so dropping
    `max_retries=0` turns a 24-call day into up to **72 billed requests** with
    the other 48 invisible to `agent_calls` and to every assertion in this file.
    No call site appears or moves when that happens.

    `tests/test_agent_budget.py::TestOneCandidateIsExactlyOneRequest` asserts
    the same property behaviourally, against a real SDK object and a stub that
    would retry if the client let it. This is the cheap structural half beside
    it: it needs no SDK installed and it names the keyword, so a diff that
    deletes the keyword fails a test that quotes it.

    Verified by mutation, 2026-08-11, in both directions that matter -- removal
    and weakening, because a check that only catches deletion would pass on
    `max_retries=1`, which is the change someone would actually make:

    - `AsyncAnthropic(api_key=...)`, keyword dropped: **RED** ("no longer
      passes `max_retries`").
    - `AsyncAnthropic(api_key=..., max_retries=1)`: **RED** (not the literal 0).

    Both reverted.
    """

    def test_build_client_asks_the_sdk_not_to_retry(self):
        kwargs = _sdk_constructor_kwargs()
        assert kwargs is not None, (
            "no `AsyncAnthropic(...)`/`Anthropic(...)` construction was found "
            "inside `build_client`. Either the client is now built somewhere "
            "this cannot see, or the constructor was renamed -- and until this "
            "is repointed the retry ceiling is unasserted at the source level."
        )
        assert "max_retries" in kwargs, (
            "`build_client` no longer passes `max_retries`, so the SDK's "
            "DEFAULT_MAX_RETRIES = 2 applies and one metered candidate becomes "
            "up to three billed HTTP requests. The 24/day ceiling stops being a "
            "ceiling on spend and becomes a ceiling on candidates wearing "
            "spend's name -- see `build_client`'s docstring."
        )
        value = kwargs["max_retries"]
        assert isinstance(value, ast.Constant) and value.value == 0, (
            f"`build_client` passes max_retries={ast.unparse(value)}, not the "
            f"literal 0. Anything but 0 breaks the identity `1 candidate == 1 "
            f"messages.parse == 1 HTTP request`, and the day's true bill becomes "
            f"a range nothing in this repo can narrow."
        )

    def test_the_api_key_still_comes_from_the_config(self):
        """Anti-vacuity for the reader above, in the cheapest useful direction.

        If `_sdk_constructor_kwargs` ever matched some *other* call inside
        `build_client`, the retry assertion would be checking a stranger. The
        constructor is the one that is handed the key.
        """
        kwargs = _sdk_constructor_kwargs() or {}
        assert "api_key" in kwargs, (
            f"the call this test reads passes {sorted(kwargs)}, which does not "
            f"look like the Anthropic client construction"
        )


def _dockerignore_patterns() -> list[str]:
    """The file's rules, comments and blanks dropped, order preserved.

    Order is the whole semantic: `.dockerignore` is last-match-wins, so
    `scripts/*` followed by `!scripts/run_loop.py` ships one file and
    `!scripts/run_loop.py` followed by `scripts/*` ships none.
    """
    lines = []
    for raw in (ROOT / ".dockerignore").read_text("utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _matches(path: str, pattern: str) -> bool:
    """One pattern against one path, in Docker's `filepath.Match` semantics.

    Segment-wise rather than a flat `fnmatch`, because `*` does **not** cross a
    separator: `scripts/*` matches `scripts/migrate_db.py` and must not match
    `scripts/sub/deep.py`. A flat fnmatch gets that wrong in the direction that
    reports a file as shipped when it is not.
    """
    pattern_parts = pattern.rstrip("/").split("/")
    path_parts = path.split("/")

    # A pattern for a directory excludes everything beneath it (`tests/` hides
    # `tests/fixtures/x.json`), so a pattern shorter than the path may still
    # match -- but only as a prefix.
    if len(pattern_parts) > len(path_parts):
        return False
    if "**" not in pattern_parts and len(pattern_parts) < len(path_parts):
        path_parts = path_parts[: len(pattern_parts)]
    if len(pattern_parts) != len(path_parts):
        return False

    return all(
        fnmatch.fnmatchcase(actual, expected)
        for actual, expected in zip(path_parts, pattern_parts)
    )


def _is_ignored(path: str, patterns: list[str]) -> bool:
    """Whether `path` is excluded from the build context. Last match wins."""
    ignored = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        if _matches(path, pattern.lstrip("!")):
            ignored = not negated
    return ignored


class TestTheEntrypointRunsWhatItMustRunFirst:
    """The same question asked of a shell script instead of a module.

    `store.db.migrate` is reached from `init_db`, which the chain runner calls.
    That is not enough on the deployed instance: the **API** opens the database
    read-only and `open_db` refuses a schema version it does not recognise, so
    on a boot after a schema change it would 500 on every page until the runner
    happened to start -- while `/api/health`, which touches no database, stayed
    green throughout.

    So the migration has to run *before* uvicorn, and the only thing that can
    assert that is a test that reads the script. Nothing else in the suite runs
    `entrypoint.sh` at all.
    """

    def _commands(self) -> list[str]:
        """The script's executable lines, with comments and blanks dropped.

        Not the raw text. The first version of this test searched for
        `"uvicorn"` and matched the header comment explaining why the naive
        `uvicorn & exec node` pattern is wrong -- so it reported the backend
        starting at byte 111, before everything, and failed. That is exactly the
        defect `_uses` above exists to avoid, reproduced in the one file that
        documents it: **prose about a command is not the command.** This repo's
        comment density makes any text search a search of the comments.
        """
        lines = []
        for raw in (ROOT / "docker" / "entrypoint.sh").read_text("utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.append(stripped)
        return lines

    def _first_index(self, commands: list[str], needle: str) -> int:
        return next(
            (i for i, line in enumerate(commands) if needle in line), -1
        )

    def test_the_migration_runs_before_the_backend_starts(self):
        commands = self._commands()
        migrate_at = self._first_index(commands, "scripts/migrate_db.py")
        uvicorn_at = self._first_index(commands, "uvicorn")

        assert migrate_at != -1, (
            "entrypoint.sh does not migrate. A schema change would reach the "
            "live volume only when the chain runner next called init_db, and "
            "the API would refuse every read until then."
        )
        assert uvicorn_at != -1, "entrypoint.sh no longer starts the backend"
        assert migrate_at < uvicorn_at, (
            "the migration runs after uvicorn, so the API opens the old schema "
            "first and refuses it"
        )

    def test_the_detector_reads_commands_rather_than_comments(self):
        """The guard on the guard, because the naive version passed for a
        different reason than the one it claimed."""
        commands = self._commands()
        assert not any(line.startswith("#") for line in commands)
        assert any("uvicorn" in line for line in commands)

    # -- and the script it names has to be in the image ---------------------
    #
    # The ordering test above passed while the deployed container crash-looped
    # on `can't open file '/app/scripts/migrate_db.py'`. Both statements were
    # true at once: the entrypoint did run the migration first, and the file it
    # ran was not there. `.dockerignore` carries `scripts/*` with a hand-kept
    # `!` allowlist, and the allowlist was written when the entrypoint ran one
    # script and never revisited when it gained a second.
    #
    # This is the repo's own two-limits shape: one guard covering half a
    # property reads exactly like a guard covering all of it.

    def _scripts_the_entrypoint_runs(self) -> list[str]:
        """Paths of the form `scripts/<name>.py` in executable lines.

        Derived from the script, not listed here, so a third script added to
        the entrypoint is covered without anyone remembering to update a test.
        """
        found: list[str] = []
        for line in self._commands():
            for token in re.findall(r"scripts/[A-Za-z0-9_./-]+\.py", line):
                if token not in found:
                    found.append(token)
        return found

    def test_every_script_the_entrypoint_runs_survives_dockerignore(self):
        scripts = self._scripts_the_entrypoint_runs()

        # If this ever empties out, the test below silently stops asserting
        # anything -- a vacuous pass reads identically to a real one.
        assert scripts, (
            "no `scripts/*.py` found in entrypoint.sh. Either the entrypoint "
            "stopped running any, or the extractor stopped matching them."
        )

        patterns = _dockerignore_patterns()
        for script in scripts:
            assert (ROOT / script).exists(), (
                f"entrypoint.sh runs {script}, which is not in the repo"
            )
            assert not _is_ignored(script, patterns), (
                f"entrypoint.sh runs {script} and .dockerignore excludes it "
                f"from the build context, so `COPY scripts/` cannot ship it. "
                f"The container starts, fails to open the file and exits -- "
                f"add `!{script}` to the allowlist."
            )

    # -- the other half, which derivation cannot reach ----------------------
    #
    # Everything above asks "which scripts does the entrypoint run?" and is
    # therefore blind to the second class of script that must be in the image:
    # the ones Joe's `flyctl ssh console` ruling invokes by path. Nothing
    # executes those at boot, so nothing derives them, so the guard above
    # reports a healthy allowlist while they are missing from the filesystem.
    #
    # `inspect_live_db.py` was excluded from the image from the day it was
    # written. It was found on 2026-08-13, while preparing to deploy a new query
    # into it -- a deploy that would have shipped an image the query still was
    # not in, and the failure would have surfaced as a confusing `No such file`
    # at the ssh prompt rather than as anything a test said.
    #
    # This list is hand-kept BY NECESSITY, so it is asserted by name and the
    # reason is written next to it. A derived guard here would be a guard that
    # cannot fail.
    SSH_INVOKED_SCRIPTS = (
        "scripts/inspect_live_db.py",
        "scripts/inspect_live_disk.py",
        "scripts/inspect_live_proc.py",
        "scripts/fetch_live_route.py",
    )

    def test_every_script_the_ssh_ruling_invokes_survives_dockerignore(self):
        patterns = _dockerignore_patterns()
        for script in self.SSH_INVOKED_SCRIPTS:
            assert (ROOT / script).exists(), f"{script} is not in the repo"
            assert not _is_ignored(script, patterns), (
                f"`flyctl ssh console` is supposed to be able to run {script} "
                f"by path, and .dockerignore excludes it from the build "
                f"context, so `COPY scripts/` cannot ship it. The file is "
                f"simply absent on the live box. Add `!{script}`."
            )

    # -- the inverse guard: scripts that must NOT reach the money box --------
    #
    # Every assertion above is "this script must ship". The opposite claim is
    # made in prose in two places and checked nowhere:
    # `2026-08-16-preregistration-prop-onesided-recovery.md` §8 says
    # `analyze_prop_onesided.py` "must **not** be added to the image", and
    # `2026-08-15-preregistration-non-sports-spread-reachability.md` §8 says
    # the same of `census_non_sports_spread.py`.
    #
    # A requirement stated in a registration and enforced by nothing is
    # decoration. These are laptop Tools: they carry analysis, apply registered
    # decision rules, and have no business on a machine holding real money
    # where `flyctl ssh console` could invoke them by path -- which is exactly
    # what the ssh ruling makes possible for anything in the image.
    #
    # The realistic way this breaks is a widening rather than a targeted edit:
    # somebody re-includes `!scripts/*.py` to fix one missing file and ships
    # forty-odd others with it. Today's exclusion is incidental (they simply
    # were never allowlisted); this makes it deliberate.
    LAPTOP_ONLY_SCRIPTS = (
        "scripts/analyze_prop_onesided.py",
        "scripts/census_non_sports_spread.py",
    )

    def test_no_laptop_only_tool_reaches_the_image(self):
        patterns = _dockerignore_patterns()
        for script in self.LAPTOP_ONLY_SCRIPTS:
            assert (ROOT / script).exists(), (
                f"{script} is named as laptop-only but is not in the repo. "
                f"Delete the entry rather than leaving an assertion about a "
                f"file that cannot fail it."
            )
            assert _is_ignored(script, patterns), (
                f"{script} is a laptop Tool and .dockerignore now SHIPS it. "
                f"Its registration says it must not reach the image: it "
                f"applies a registered decision rule, and the ssh ruling lets "
                f"anything in the image be invoked by path against the live "
                f"database. Remove whatever re-includes it."
            )

    def test_the_two_lists_do_not_overlap(self):
        """A script cannot be both required and forbidden.

        Without this, adding a name to both lists would make one of the two
        assertions above unreachable -- and the suite would still be green,
        which is the shape of failure this file exists to catch.
        """
        overlap = set(self.SSH_INVOKED_SCRIPTS) & set(self.LAPTOP_ONLY_SCRIPTS)
        assert not overlap, overlap

    def test_the_two_classes_are_guarded_separately(self):
        """The guard on this guard.

        If an ssh-invoked script ever also became an entrypoint script, the
        derived test above would start covering it and this one would look
        redundant -- so assert the gap it exists to close is still a real gap.
        A pass here means the derived guard genuinely does not reach these.
        """
        derived = self._scripts_the_entrypoint_runs()
        assert self.SSH_INVOKED_SCRIPTS, "the hand-kept list emptied out"
        for script in self.SSH_INVOKED_SCRIPTS:
            assert script not in derived, (
                f"{script} is now run by entrypoint.sh, so the derived guard "
                f"covers it. Move it out of SSH_INVOKED_SCRIPTS rather than "
                f"keeping a second assertion that can no longer fail."
            )

    def test_the_dockerignore_matcher_agrees_with_the_rules_it_models(self):
        """The guard on this guard.

        A matcher that never reports "ignored" would pass the test above on any
        input at all, which is the shape of a check that cannot fail. So assert
        both directions on the real file: a capture script is excluded by
        `scripts/*`, and the allowlisted ones are not.
        """
        patterns = _dockerignore_patterns()

        assert _is_ignored("scripts/capture_fixtures.py", patterns), (
            "the matcher does not honour `scripts/*`, so it would report every "
            "script as shipped"
        )
        assert not _is_ignored("scripts/run_loop.py", patterns)
        assert not _is_ignored("backend/api/routes.py", patterns)
        # Last match wins, and a `!` line only counts if it comes after the
        # pattern it negates.
        assert _is_ignored("scripts/x.py", ["!scripts/x.py", "scripts/*"])
        assert not _is_ignored("scripts/x.py", ["scripts/*", "!scripts/x.py"])

    def test_every_script_the_entrypoint_runs_at_least_loads(self):
        """Import-time breakage in a boot step is a crash loop.

        `--help` exits before `main`, so this proves only that the module and
        its imports load -- which is the cheap half. The expensive half is
        below, and only for the migration, because it is the one boot step that
        can be run with no credentials and no network.
        """
        import subprocess

        for script in self._scripts_the_entrypoint_runs():
            result = subprocess.run(
                [sys.executable, str(ROOT / script), "--help"],
                capture_output=True, text=True, cwd=ROOT, timeout=120,
            )
            assert result.returncode == 0, (
                f"{script} does not load: {result.stderr[-800:]}"
            )

    def test_the_migration_step_actually_runs_on_a_real_old_database(self, tmp_path):
        """Run the boot step, as the boot step, against a database like the one
        on the volume.

        This file already asserted that `scripts/migrate_db.py` runs before
        uvicorn and that it survives `.dockerignore`. Both were true on
        2026-08-08 and the deploy still crash-looped, because the script read
        `db._MIGRATIONS` in a shape it no longer had:

            TypeError: '_Migration' object is not iterable

        Nothing executed it. The container did, once, in production. That is
        the same shape as the `.dockerignore` failure this class was written
        for -- a boot step covered by assertions *about* it rather than by
        running it -- so the fix is to run it.

        A subprocess rather than an import, because `python scripts/migrate_db.py`
        is literally what `entrypoint.sh` invokes, and the module-level
        `sys.path` insert it needs to work only happens that way.
        """
        import subprocess

        from backend.store import db

        path = tmp_path / "volume.db"
        connection = db.init_db(path)
        # Wind it back to the version behind the current one, which is the
        # transition the live volume is about to make.
        previous = sorted(db._MIGRATIONS)[-1]
        for name in db._MIGRATIONS[previous].indexes:
            connection.execute(f"DROP INDEX IF EXISTS {name}")
        # A step that rebuilds a table says how to put the old one back; there
        # is nothing generic to infer. This was `statement.split("EXISTS")[1]`,
        # which read `ALTER TABLE settlements_v4 RENAME TO settlements` as an
        # index name and raised -- the fifth reader of `_MIGRATIONS` to assume
        # every statement creates an index.
        for statement in db._MIGRATIONS[previous].undo_statements:
            connection.execute(statement)
        for table, column, _ in db._MIGRATIONS[previous].columns:
            connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(previous - 1),),
        )
        connection.commit()
        connection.close()

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "migrate_db.py"),
             "--db", str(path)],
            capture_output=True, text=True, cwd=ROOT, timeout=180,
        )
        assert result.returncode == 0, (
            "the boot step failed, which is a crash loop on the instance: "
            + result.stdout + result.stderr
        )
        assert f"migrated v{previous - 1} -> v{db.SCHEMA_VERSION}" in result.stdout, (
            result.stdout
        )
        # And the API can now open what the boot step left behind.
        db.open_db(path).close()

    def test_the_migration_step_is_idempotent_because_it_runs_every_boot(
        self, tmp_path
    ):
        import subprocess

        from backend.store import db

        path = tmp_path / "already.db"
        db.init_db(path).close()

        for _ in range(2):
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "migrate_db.py"),
                 "--db", str(path)],
                capture_output=True, text=True, cwd=ROOT, timeout=180,
            )
            assert result.returncode == 0, result.stderr
            assert "already at schema" in result.stdout, result.stdout

    def test_the_script_it_names_exists(self):
        """A boot step pointing at a missing file fails the deploy, loudly --
        but only on the deploy, which is the worst place to find out."""
        assert (ROOT / "scripts" / "migrate_db.py").exists()


class TestTheQuoteCadenceStaysQuiet:
    """Per-pass work must be guarded by `kind == "full"`, structurally.

    A quote pass runs every 15s while the window is open. Anything called
    unguarded there runs ~5,700 times a day, and this project has already lost
    its production log stream to exactly that: 962 warnings per pass overran a
    100-line buffer and made the boot lines unreadable for three sessions
    (`tasks/lessons.md`, 2026-08-09).

    The guard is asserted on the *source*, by AST, rather than by running the
    loop. Driving 61 quote passes to count log lines is the test I tried first;
    it needs a full fake exchange and it passes for the wrong reason the moment
    the window is closed, because then no quote pass fires at all.

    `run_scoring_pass` and `run_settlement_pass` are listed alongside the new
    one because they are guarded today for their own reasons -- credits and
    pointless requests -- and an enumeration that only names the newest case is
    a list someone will forget to extend.
    """

    FULL_PASS_ONLY = (
        "log_gate_progress",
        "run_scoring_pass",
        "run_settlement_pass",
        "run_market_result_pass",
        "daily_digest",
    )

    def _guarded_calls(self) -> set[str]:
        """Names called anywhere inside an `if kind == "full":` body."""
        tree = ast.parse((ROOT / "scripts" / "run_loop.py").read_text("utf-8"))
        guarded: set[str] = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            is_full_gate = (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "kind"
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "full"
                and isinstance(test.ops[0], ast.Eq)
            )
            if not is_full_gate:
                continue
            for inner in node.body:
                for call in ast.walk(inner):
                    if not isinstance(call, ast.Call):
                        continue
                    func = call.func
                    if isinstance(func, ast.Name):
                        guarded.add(func.id)
                    elif isinstance(func, ast.Attribute):
                        guarded.add(func.attr)
        return guarded

    def test_the_expensive_calls_are_all_behind_the_full_pass_guard(self):
        guarded = self._guarded_calls()
        missing = [name for name in self.FULL_PASS_ONLY if name not in guarded]
        assert not missing, (
            f"{missing} run on the 15s quote cadence -- ~5,700 times a day"
        )

    def test_the_guard_this_test_looks_for_actually_exists(self):
        """Anchors the test against its own vacuity.

        If `run_loop` were rewritten to dispatch on something other than
        `kind == "full"`, `_guarded_calls` would return an empty set and every
        assertion above would pass by finding nothing to check.
        """
        assert self._guarded_calls(), "no `if kind == \"full\":` block found"
