"""Is each `MUST_HAVE_CALLERS` symbol *reached* from a deployed entry point?

`tests/test_has_callers.py` asks three questions of every symbol on that list:
is it named in a production file, does that file ship in the image, and is
the naming more than an `import`. All three are one level deep -- they ask
whether *some function* names the symbol, never whether that function is
itself reached from anything `docker/entrypoint.sh` runs.

`skeptic.apply_verdict` passed all three for fifteen days while unreachable
on the live machine. Its only production referrer was `review._amend`, called
only by `review_surfaced`, which nothing had called since ADR 0062 made
`review_retired` the pass default (2026-08-21). `reachable_modules()` did not
catch it either: that walk is the *import* closure, and `review.py` was
imported by the runner for `review_retired` -- import-reachable and called are
different properties. The entry's own consequence string named the failure it
could not detect: "~40 green tests implying a safety layer that can block
nothing". Both were deleted on 2026-09-05; the ADR named in `DISPOSITIONS`
carries the record.

This file asks the fourth question. Starting from the code that runs at import
in every module the entry points reach, it follows every name a reached
function body references into the functions that carry that name, to a fixed
point, and asserts each listed symbol is in the reached set.

What it does NOT establish
--------------------------
**That a reached symbol is called on any real pass.** The walk is by *name*,
not by resolved object, and it over-approximates on purpose: a name reached
anywhere counts everywhere (two functions called `get` are both reached if
either is), a decorated definition counts as reached at import (a FastAPI
route, a `@property`, a `@dataclass`), and a reached class reaches its dunder
methods. Nested function bodies are walked with their parent. Names in
annotations count. It cannot see `getattr(module, "name")`, string dispatch,
or a name only ever spelled inside a string, and it cannot see a method a
framework calls by protocol (`logging.Filter.filter`,
`Formatter.formatException`, an object handed to a library that calls it). So
a **red** here means no body *this repo* reaches names the symbol, and a
**green** is the weaker claim that some reached body does. That is one level
deeper than `has_callers`, and it is exactly the level `apply_verdict` sat at.

**That the unreached set is dead.** On 2026-09-05 the walk left 54 of 1,086
definitions in the deployed closure unreached. Some are framework callbacks
(above); some are retired fee models kept as records (`fees._model_b`); one
is `AgentBudget.allowance`, whose only caller was the deleted
`review_surfaced`. None of that is asserted here -- the list is a finding
for an ADR, not a guard, because a walk that over-approximates reachability
cannot also be the authority on death.

**That the entry points are right.** They are `has_callers`'s
`deployed_entry_points()`, derived from the boot script, minus the demo
seeder that file already refuses to count as a caller.

Mutations run against this file
-------------------------------
Recorded in the class docstrings, with the date.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path
from textwrap import dedent

import pytest

from tests.test_has_callers import (
    MUST_HAVE_CALLERS,
    NOT_A_CALLER_FILES,
    ROOT,
    deployed_entry_points,
    reachable_modules,
)

_DEF = (ast.FunctionDef, ast.AsyncFunctionDef)


def _referenced(node: ast.AST) -> set[str]:
    """Every plain name and attribute name under `node`, nested bodies included."""
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            out.add(child.id)
        elif isinstance(child, ast.Attribute):
            out.add(child.attr)
    return out


def _import_time_names(tree: ast.Module) -> set[str]:
    """Names referenced by code that runs when the module is imported.

    Everything except the *bodies* of function definitions: module statements,
    class bodies, decorators, argument defaults. A function's body runs only
    when something calls it, which is the whole question.
    """
    out: set[str] = set()

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEF):
                for part in (*child.decorator_list, *child.args.defaults,
                             *child.args.kw_defaults):
                    if part is not None:
                        out.update(_referenced(part))
                continue
            if isinstance(child, ast.Name):
                out.add(child.id)
            elif isinstance(child, ast.Attribute):
                out.add(child.attr)
            visit(child)

    visit(tree)
    return out


def _definitions(tree: ast.Module):
    """`(name, node, decorated, owner_class)` for every def and class."""
    found = []

    def visit(node: ast.AST, owner: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                found.append((child.name, child, bool(child.decorator_list), owner))
                visit(child, child.name)
            elif isinstance(child, _DEF):
                found.append((child.name, child, bool(child.decorator_list), owner))
                visit(child, owner)
            else:
                visit(child, owner)

    visit(tree, None)
    return found


def reached_names(files: list[Path], seeds: set[str] | frozenset[str] = frozenset()) -> set[str]:
    """The fixed point: names some executed body references, transitively.

    Seeds: every import-time reference in every file, plus every decorated
    definition (a decorator is a call made at import with the function as its
    argument -- that is how a route handler or a property is reached without
    anything ever naming it), plus `seeds` -- names the boot script itself
    invokes without any Python naming them (uvicorn's `--factory`). Then, for
    as long as it grows: a definition whose name is reached contributes its
    body's references; a reached class contributes its dunder methods.
    """
    defs_by_name: dict[str, list] = {}
    reached: set[str] = set(seeds)
    for path in files:
        try:
            tree = ast.parse(path.read_text("utf-8", errors="replace"))
        except SyntaxError:
            continue
        reached |= _import_time_names(tree)
        for name, node, decorated, owner in _definitions(tree):
            defs_by_name.setdefault(name, []).append((node, owner))
            if decorated:
                reached.add(name)

    expanded: set[str] = set()
    while True:
        pending = reached - expanded
        if not pending:
            return reached
        for name in pending:
            expanded.add(name)
            for node, _owner in defs_by_name.get(name, ()):
                if isinstance(node, ast.ClassDef):
                    for member in node.body:
                        if isinstance(member, _DEF) and member.name.startswith("__") \
                                and member.name.endswith("__"):
                            reached.add(member.name)
                else:
                    reached |= _referenced(node)


def _factories_the_boot_script_invokes() -> frozenset[str]:
    """`uvicorn backend.api.routes:create_app --factory` calls `create_app`
    by name from the shell. No Python names it, so the walk is seeded with it."""
    text = (ROOT / "docker" / "entrypoint.sh").read_text("utf-8")
    return frozenset(
        m.group(1)
        for m in re.finditer(r"uvicorn\s+[A-Za-z0-9_.]+:([A-Za-z0-9_]+)", text)
    )


def walked_files() -> list[Path]:
    """The import closure of the boot script, plus the entry scripts themselves.

    `reachable_modules()` returns `backend/` modules only; the entry points
    under `scripts/` are where `main()` lives, so they are added back. The demo
    seeder is an entry point the boot script runs and `has_callers` refuses to
    count as a caller; the same refusal applies here.
    """
    rels = (set(reachable_modules()) | set(deployed_entry_points())) \
        - set(NOT_A_CALLER_FILES)
    return sorted(ROOT / rel for rel in rels)


@lru_cache(maxsize=1)
def _reached_on_the_deployed_tree() -> frozenset[str]:
    return frozenset(
        reached_names(walked_files(), seeds=_factories_the_boot_script_invokes())
    )


class TestTheWalkerCanTellWiredFromDead:
    """Anti-vacuity, on a tree built to the shape of the defect.

    `dead` below is `apply_verdict`: referenced by exactly one function, and
    that function referenced by nothing. `has_callers`'s three checks would
    pass `dead` (a production file names it, in code, beyond an import). The
    walker must not.

    Mutation, 2026-09-05: `reached_names` returning every defined name --
    `test_a_function_whose_only_referrer_is_unreached_is_not_reached`,
    `test_a_reached_class_reaches_its_dunders_and_only_those` and the
    real-tree `test_the_pricing_pass_is_reached_and_not_everything_is` went
    RED. Mutation: drop the decorated-definition seed --
    `test_a_decorated_definition_is_reached_at_import` went RED and nothing
    else did: on the real tree every `MUST_HAVE_CALLERS` symbol is also
    reached through `create_app` or `run_loop.main`, so the seed guards the
    case this class describes (a handler nothing names) rather than today's
    list.
    """

    @pytest.fixture
    def tree(self, tmp_path: Path) -> list[Path]:
        (tmp_path / "entry.py").write_text(dedent("""\
            from a import wired, Wrapped, register

            wired()
            Wrapped()
        """), encoding="utf-8")
        (tmp_path / "a.py").write_text(dedent("""\
            def register(f):
                return f

            def wired():
                return helper()

            def helper():
                return 1

            def caller():            # nothing names this
                return dead()        # so this is `apply_verdict`

            def dead():
                return 2

            @register
            def decorated():
                return 3

            class Wrapped:
                def __init__(self):
                    self.x = via_init()

                def method(self):
                    return unreached_method_target()

            def via_init():
                return 4

            def unreached_method_target():
                return 5
        """), encoding="utf-8")
        return [tmp_path / "entry.py", tmp_path / "a.py"]

    def test_a_function_called_at_import_is_reached_transitively(self, tree):
        reached = reached_names(tree)
        assert "wired" in reached
        assert "helper" in reached, "one level down from an import-time call"

    def test_a_function_whose_only_referrer_is_unreached_is_not_reached(self, tree):
        reached = reached_names(tree)
        assert "caller" not in reached
        assert "dead" not in reached, (
            "`dead` is named by `caller`, which nothing names -- the "
            "`apply_verdict` shape. A walker that reaches it is a walker "
            "that would have passed the defect this file exists for."
        )

    def test_a_decorated_definition_is_reached_at_import(self, tree):
        assert "decorated" in reached_names(tree)

    def test_a_reached_class_reaches_its_dunders_and_only_those(self, tree):
        reached = reached_names(tree)
        assert "__init__" in reached
        assert "via_init" in reached, "reached through `__init__`"
        assert "method" not in reached, "a method nothing calls"
        assert "unreached_method_target" not in reached


class TestTheDeployedTreeIsWalkedNotEnumerated:
    """The guard on the guard, on the real tree.

    A walk that reached everything would pass every symbol below by
    construction; one that reached nothing would fail them all for the wrong
    reason. Both directions are pinned.
    """

    def test_the_walk_starts_from_the_boot_script(self):
        files = {str(p.relative_to(ROOT)).replace("\\", "/") for p in walked_files()}
        assert "scripts/run_loop.py" in files
        assert "backend/api/routes.py" in files
        assert "backend/seed_demo.py" not in files, (
            "the demo seeder is not a caller (`has_callers`, NOT_A_CALLER_FILES)"
        )

    def test_the_api_factory_is_seeded_from_the_boot_script(self):
        """`create_app` is named by the shell, not by Python. Without the seed
        every route handler is still reached (decorated), but the lifespan
        and everything constructed inside the factory is not."""
        assert _factories_the_boot_script_invokes() == {"create_app"}
        assert "create_app" in _reached_on_the_deployed_tree()

    def test_the_pricing_pass_is_reached_and_not_everything_is(self):
        reached = _reached_on_the_deployed_tree()
        assert "run_pricing_pass" in reached, (
            "`run_loop.main` -> `run_once` -> `run_pricing_pass` is the spine "
            "of the recorder; a walk that cannot follow it follows nothing"
        )
        defined: set[str] = set()
        for path in walked_files():
            tree = ast.parse(path.read_text("utf-8", errors="replace"))
            defined |= {name for name, _n, _d, _o in _definitions(tree)}
        unreached = sorted(defined - reached)
        assert unreached, (
            "every definition in the deployed closure is reached, so this walk "
            "is an enumeration wearing a walk's name"
        )


@pytest.mark.parametrize(
    "symbol,consequence", MUST_HAVE_CALLERS, ids=[s for s, _ in MUST_HAVE_CALLERS]
)
def test_the_symbol_is_reached_from_a_deployed_entry_point(symbol, consequence):
    """The fourth question, for every symbol the first three already pass.

    Mutation, 2026-09-05, on the real tree: in `backend/runner.py`, the call
    `persist_if_changed(conn, rec)` in `_review_and_persist` replaced by
    `rec is None`, and a new module-level `_orphaned_referrer(conn, rec)`
    added whose body is the original call -- the `apply_verdict` shape,
    exactly. All three `has_callers` tests for `persist_if_changed` stayed
    GREEN (the file names it, ships, and names it beyond an import). This
    test went RED.
    """
    assert symbol in _reached_on_the_deployed_tree(), (
        f"`{symbol}` is named by a production file, but no function that "
        f"names it is itself reached from anything `docker/entrypoint.sh` "
        f"runs. That is the state `apply_verdict` was in from 2026-08-21 to "
        f"2026-09-05, passing every check in `test_has_callers.py`. If it "
        f"stands, {consequence}."
    )
