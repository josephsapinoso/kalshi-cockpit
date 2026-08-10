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

What this does not establish
----------------------------
That the caller is reached at *runtime*. A function imported by a module nobody
runs still passes the symbol half here. Module reachability is import-based, so
a module imported behind a branch that never fires still counts as LIVE. It is
a floor, not a proof -- the behavioural tests beside it are what establish the
path actually executes.
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
        "score_recommendations",
        "nothing can be scored, and the gate's 300-game counter stays at zero "
        "however long the system runs",
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
    (
        "review_surfaced",
        "`apply_verdict` has a definition and no path to it from a pass, so "
        "the Skeptic is wired up on paper only",
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
    was deleted. `review_surfaced` passes this because `runner.py` names it as
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
# ADR 0022 records how this list was arrived at and why nothing here is being
# wired up or deleted tonight.
DISPOSITIONS: dict[str, Tool | Quarantined] = {
    # -- Tools ---------------------------------------------------------------
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
    "backend/model/synthetic.py": Tool(
        run_by=("scripts/demo_builder.py",),
        purpose="Synthetic margin generator, documented as not-evidence. It "
                "must never reach the image: it manufactured a +28.4% EV "
                "teaser once already (`tasks/lessons.md`, 2026-08-06).",
    ),

    # -- Quarantined ---------------------------------------------------------
    "backend/agents/scout.py": Quarantined(
        reason="The information-gathering half of the agent fleet. Complete and "
               "tested; no caller anywhere. The only file that imports it is "
               "`scripts/measure_agent_cache_prefix.py`, which reads its prompt "
               "constants to measure cache prefixes and never calls `research`.",
        revive_if="a strategy is adopted that needs qualitative context, and "
                  "the Anthropic spend it implies is budgeted. Today the bill "
                  "is held at zero by `surfaced == 0`, so wiring it up would "
                  "start paying to decorate a line ADR 0021 refuted.",
        adr="docs/adr/0022-quarantine-the-orphaned-modules.md",
    ),
    "backend/agents/historian.py": Quarantined(
        reason="The weekly post-mortem. Same state as Scout, same importer, and "
               "`review` is called by nothing.",
        revive_if="ADR 0021 §8 Option B or F is taken up -- both need a "
                  "post-mortem loop, which is the strongest argument against "
                  "deleting this rather than parking it.",
        adr="docs/adr/0022-quarantine-the-orphaned-modules.md",
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
