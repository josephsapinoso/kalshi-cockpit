"""The leg scout is advisory and stays that way (#152, ADR 0186).

`leg_verdicts` is a shown-beside-the-buy-button opinion, never a gate: the
table CHECK constraints and the route both keep it that way, but the one
thing no constraint can enforce is a *future* line of code inside the money
handlers that reads it anyway -- a `SELECT ... FROM leg_verdicts` dropped
into `parlay_rfq_accept` or `place_manual_order` would compile, run, and
change nothing about the schema, so nothing above this test file would
catch it.

**Fails closed.** `test_only_allowlisted_files_mention_leg_verdicts` walks
every `.py`/`.sql` file under `backend/` and asserts the table name appears
nowhere outside a short, named allowlist. A new file that mentions the table
-- anywhere, for any reason -- fails until a human adds it to the list and
says why. This is the same shape `tests/test_has_callers.py` uses for
`structured_call`/`build_client`: enumerate the population, do not remember
the answer.

**Mutation-checkable at the two handlers that actually spend.** Adding a
`leg_verdicts` read to `parlay_rfq_accept` or `place_manual_order` turns
both `test_only_allowlisted_files_mention_leg_verdicts` (the file-level
sweep) and the matching handler-specific test red -- verified below by
literally doing that and reverting it (see the module docstring of the
lane's own report, not repeated here as a comment beside production code,
because a comment claiming "we checked" goes stale the moment anyone
believes it instead of re-running this file).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Every file allowed to mention the table name `leg_verdicts`, and why.
#: `backend/api/routes.py` is here ONLY for the router import/registration
#: line (`leg_verdicts as leg_verdicts_router`, and the `.register(...)`
#: call) -- never for a query on the table itself, which is what the two
#: handler-specific tests below check directly.
ALLOWLIST = {
    "backend/store/schema.sql",  # the table's own definition
    "backend/store/db.py",  # the schema-version comment for v57
    "backend/leg_verdicts.py",  # the module that owns the table
    "backend/api/routers/leg_verdicts.py",  # the routes that read/write it
    "backend/api/routes.py",  # the router import + one .register() line
}


def _mentions(text: str) -> bool:
    return "leg_verdicts" in text


def test_only_allowlisted_files_mention_leg_verdicts():
    hits: set[str] = set()
    for path in (REPO / "backend").rglob("*"):
        if not path.is_file() or path.suffix not in (".py", ".sql"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _mentions(text):
            hits.add(path.relative_to(REPO).as_posix())
    unexpected = hits - ALLOWLIST
    assert not unexpected, (
        f"{sorted(unexpected)} mention `leg_verdicts` and are not on the "
        f"allowlist. Either this is a legitimate new reader/writer of the "
        f"table -- add it to ALLOWLIST with a reason -- or it is exactly "
        f"the failure mode this test exists to catch: a money-path handler "
        f"reading an advisory table."
    )
    missing = ALLOWLIST - hits
    assert not missing, (
        f"{sorted(missing)} are allowlisted but no longer mention "
        f"`leg_verdicts` -- the allowlist has gone stale and should shrink."
    )


def _function_source(file_path: Path, func_name: str) -> str:
    """The exact source text of the (possibly nested) function `func_name`
    inside `file_path`, via `ast`, so a handler buried inside `register()`
    or `create_app` is found regardless of indentation."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                return segment
    raise AssertionError(f"{func_name} not found in {file_path}")


class TestMoneyPathHandlersNeverMentionTheTable:
    """The two handlers that actually spend, checked directly rather than
    only through the file-level sweep above -- so a mutation that adds a
    `leg_verdicts` read inside either one is caught by a test named after
    the exact claim it breaks, not only by the general sweep."""

    def test_rfq_accept_never_mentions_leg_verdicts(self):
        src = _function_source(
            REPO / "backend/api/routers/parlays.py", "parlay_rfq_accept"
        )
        assert "leg_verdicts" not in src

    def test_manual_orders_never_mentions_leg_verdicts(self):
        src = _function_source(REPO / "backend/api/routes.py", "place_manual_order")
        assert "leg_verdicts" not in src


def test_leg_verdicts_table_is_never_joined_by_gate_or_hedge():
    """`backend/gate.py` and `backend/hedge.py` (the interlock and the
    watcher ADR 0078 describes) must never gain a `leg_verdicts` reference
    either -- neither is a spend handler, but both feed a decision, and
    ADR 0186 only licenses this table to inform a buy button, never to move
    the gate or the hedge estimate."""
    for rel in ("backend/gate.py", "backend/hedge.py"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "leg_verdicts" not in text, rel
