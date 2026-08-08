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
    backend/agents/*       ~40 tests implying a safety layer. Still orphaned;
                           named below so this file fails when it is wired up
                           and the exception can be deleted.

The failure has no line number. Every file is individually excellent, coverage
goes up, and the missing thing is the *absence of a call* -- which no reviewer
reads and no coverage tool reports, because the untested code does not exist.

The cheap detector was already written down in `tasks/lessons.md`:

    grep -rn "score_recommendations" --include=*.py .
    # if every hit is tests/ or a seeder, the feature does not exist yet

This is that grep, run by CI instead of by memory.

What this does not establish
----------------------------
That the caller is reached at *runtime*. A function imported by a module nobody
runs still passes here. It is a floor, not a proof -- the behavioural tests
beside it are what establish the path actually executes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Directories that do not count as a caller. A feature called only by its own
# tests and its own demo seeder is a feature that has not shipped.
NOT_A_CALLER = ("tests", "warehouse", ".venv", "node_modules", "__pycache__")

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
        "run_scoring_pass",
        "closing lines are never fetched, so `score_recommendations` has "
        "nothing to score even once it is called",
    ),
]


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


def test_the_agent_fleet_is_still_the_known_exception():
    """Deliberately inverted, so wiring it up makes this file fail.

    `backend/agents/*` carries ~40 green tests implying a safety layer that can
    block nothing: `skeptic.apply_verdict` is not called from the engine or the
    API. Asserting the *current* state rather than the desired one means the day
    someone connects it, this test goes red and points at the list above --
    which is where the entry belongs from then on.
    """
    assert callers_of("apply_verdict") == [], (
        "`apply_verdict` now has a caller. Move `apply_verdict` into "
        "MUST_HAVE_CALLERS and delete this test -- the exception has been "
        "closed, and leaving it here would let it silently open again."
    )
