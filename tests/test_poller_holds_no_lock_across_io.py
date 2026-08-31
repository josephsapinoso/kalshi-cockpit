"""The portfolio poller never holds a write transaction across an `await`.

WHY THIS EXISTS
---------------
`OperationalError: database is locked` killed a scoring pass four to five times
a day. The traceback (2026-08-31T05:32:45Z) landed in
`clv.store_closing_line`, and `BUSY_TIMEOUT_MS = 5_000` was already set on
every connection -- so something was holding the write lock for over five
seconds.

It was this module. The fast branch of `poll_portfolio_forever` ran

    await poll_balance(...)       # INSERTs -> SQLite's write lock is taken
    await poll_fills(...)         # network round trip, lock HELD
    await poll_settlements(...)   # network round trip, lock HELD
    await poll_positions(...)     # network round trip, lock HELD
    conn.commit()                 # lock released

every `balance_interval_s` -- 300s, so **288 times a day**. `poll_portfolio`
had the identical shape on the 12-hour mirror clock. The frequency is what
made the fast branch the one that mattered: four-to-five failures a day fits
288 windows and does not fit two.

WHAT THIS ESTABLISHES
---------------------
That no `await` sits between a write and its commit in either path, checked
over the source with `ast` rather than by running anything.

WHAT IT DOES NOT
----------------
- **That the symptom is gone.** This fixes a holder it can prove; the
  retention prune and the WAL `TRUNCATE` checkpoint were never examined and
  are the next suspects if failures continue at the same rate.
- **Anything by timing.** A stopwatch on a shared box is a flake. The
  structure is what was wrong, so the structure is what is pinned.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POLLER = ROOT / "backend" / "portfolio_poll.py"

#: The calls that perform network I/O in this module. Each is a Kalshi round
#: trip, and each must be preceded by a commit if anything was written.
IO_CALLS = (
    "poll_balance",
    "poll_fills",
    "poll_settlements",
    "poll_positions",
    "poll_portfolio",
)


def _blocks(fn: ast.AST) -> list[list[ast.stmt]]:
    """Every contiguous statement list in the function, each checked alone.

    **Blocks rather than one flattened stream, and branches rather than a
    single pass.** Two earlier versions of this were wrong in opposite ways and
    both are worth recording, because each produced a confident false finding:

    1. Appending compound nodes as well as recursing made a `while` count as a
       write whenever anything nested inside it wrote, so the guard blamed the
       loop header.
    2. Flattening `body` then `orelse` into one stream carried state across the
       `if`/`else` boundary, so a write in the mirror branch was reported as
       held across the fast branch's first call -- two paths that never run in
       the same pass.

    The property is about a straight line of statements, so each straight line
    is checked on its own and state never crosses a branch.
    """
    blocks: list[list[ast.stmt]] = []

    def visit(nodes: list) -> None:
        leaves: list[ast.stmt] = []
        for node in nodes:
            children = [
                getattr(node, attr, None)
                for attr in ("body", "orelse", "finalbody", "handlers")
                if isinstance(getattr(node, attr, None), list)
            ]
            if children:
                for child in children:
                    visit(child)
            else:
                leaves.append(node)
        if leaves:
            blocks.append(leaves)

    visit(fn.body)
    return blocks


def _is_commit(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "commit"
    )


def _io_call_name(node: ast.stmt):
    """The name of an awaited I/O call in this statement, if there is one."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Await):
            for inner in ast.walk(sub):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                    if inner.func.id in IO_CALLS:
                        return inner.func.id
    return None


def _writes(node: ast.stmt) -> bool:
    """Whether this statement issues SQL that takes the write lock."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            head = sub.value.strip().upper()
            if head.startswith(("INSERT", "UPDATE", "DELETE")):
                return True
    return False


def _functions():
    tree = ast.parse(POLLER.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }


@pytest.mark.parametrize("name", ["poll_portfolio", "poll_portfolio_forever"])
def test_no_await_sits_between_a_write_and_its_commit(name):
    """Mutation observed red: delete any `conn.commit()` that follows an
    `await poll_*` in either function.

    The rule, which is the transferable part: **never hold a database write
    transaction across an `await` that performs I/O.** A lock is held in
    wall-clock time and an `await` is an unbounded amount of it.
    """
    fn = _functions()[name]
    for block in _blocks(fn):
        dirty = False      # a write has happened with no commit since
        dirty_at = None
        for node in block:
            if _writes(node):
                dirty = True
                dirty_at = getattr(node, "lineno", "?")
            if _is_commit(node):
                dirty = False
                dirty_at = None
            call = _io_call_name(node)
            if call and dirty:
                pytest.fail(
                    f"{name}: `await {call}()` at line {node.lineno} runs "
                    f"with an uncommitted write from line {dirty_at} -- the "
                    f"SQLite write lock is held across a network round trip, "
                    f"which is what made `store_closing_line` raise "
                    f"`database is locked`"
                )
            if call:
                # An awaited poller writes internally; the call itself counts
                # as a write, because its INSERTs open the transaction.
                dirty = True
                dirty_at = node.lineno


def test_the_fast_branch_still_polls_all_four_endpoints():
    """The fix must not have removed a poll while adding commits.

    `poll_fills`, `poll_settlements` and `poll_positions` each ride the balance
    cadence for a recorded reason (the 2026-08-21 ruling, ADR 0064, and the
    2026-08-29 open-positions change). Dropping one to shorten the transaction
    would trade a lock for a hole in the record.
    """
    fn = _functions()["poll_portfolio_forever"]
    called = {
        _io_call_name(node)
        for block in _blocks(fn)
        for node in block
        if _io_call_name(node) is not None
    }
    assert called >= {
        "poll_balance", "poll_fills", "poll_settlements", "poll_positions"
    }, called
