"""The poller and the matcher never hold a write transaction across an `await`.

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

WHY IT GREW, 2026-09-01
-----------------------
The same defect was sitting in `estimate_match.ensure_estimate_markets_known`
and **this file could not see it**, for two independent structural reasons.
Both are now fixed, and both are worth naming because a guard that cannot see
a defect reports health over broken code:

1. **It matched only `ast.Name` calls.** `await source.fetch(...)` is an
   `ast.Attribute`, so the one network call in `estimate_match.py` was
   invisible to the matcher. `IO_METHODS` exists for that.
2. **It inspected only straight lines.** The matcher's write sat at the end of
   iteration N and its `await` at the start of iteration N+1 -- a hold carried
   across the loop's back edge, which no straight-line scan can see. That is
   `test_no_loop_carries_an_uncommitted_write_into_the_next_iteration`.

ADR 0091 cleared `estimate_match.py` in passing ("every `estimate_match` helper
commits its own writes"). That is true of the four synchronous helpers and was
false of the one async one, which is how it survived a fix aimed at its exact
shape.

WHAT THIS ESTABLISHES
---------------------
That in every function named in `GUARDED`, no `await` performing I/O runs with
an uncommitted write -- neither in a straight line, nor carried across a loop's
back edge. Checked over the source with `ast` rather than by running anything.

WHAT IT DOES NOT
----------------
- **That the symptom is gone.** This fixes holders it can prove; the retention
  prune and the WAL `TRUNCATE` checkpoint were never examined and are the next
  suspects if failures continue at the same rate.
- **Anything by timing.** A stopwatch on a shared box is a flake. The
  structure is what was wrong, so the structure is what is pinned.
- **Anything about code it is not pointed at.** `GUARDED` is a list, not a
  sweep. A third module with this shape is invisible until it is added here.
- **Anything about a write it cannot recognise.** `_writes` looks for a string
  literal beginning `INSERT`/`UPDATE`/`DELETE`; SQL built at runtime, or a
  write inside a helper called synchronously, does not register.
- **Anything about `finally`.** `_walk` merges a `finally` block as an
  alternative path rather than a sequel, so a commit that lives only in a
  `finally` is not credited. None of the guarded functions has one.
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
MATCHER = ROOT / "backend" / "estimate_match.py"

#: Every function checked, by the file it lives in. Only the async ones: a
#: synchronous helper has no `await` to hold a lock across, and the whole
#: property is about wall-clock time spent inside one.
GUARDED = {
    POLLER: ("poll_portfolio", "poll_portfolio_forever"),
    MATCHER: ("ensure_estimate_markets_known", "run_match_pass"),
}

#: Bare-name calls that perform network I/O. Each is a Kalshi round trip, and
#: each must be preceded by a commit if anything was written.
IO_CALLS = (
    "poll_balance",
    "poll_fills",
    "poll_settlements",
    "poll_positions",
    "poll_portfolio",
    "run_match_pass",
    "ensure_estimate_markets_known",
)

#: Method calls that perform network I/O, matched on the attribute name.
#: `LiveQuoteSource.fetch` is `GET /markets/{ticker}` -- the only `await` in
#: `estimate_match.py`, and an `ast.Attribute` rather than an `ast.Name`, which
#: is one of the two reasons this file used to be blind to it.
IO_METHODS = ("fetch",)


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
    """The name of an awaited I/O call in this statement, if there is one.

    Matches a bare name against `IO_CALLS` and a method against `IO_METHODS`.
    The second half is not decoration: `await source.fetch(...)` parses as an
    `ast.Attribute`, and without it the only network call in `estimate_match.py`
    reads as no call at all.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Await):
            continue
        for inner in ast.walk(sub):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if isinstance(func, ast.Name) and func.id in IO_CALLS:
                return func.id
            if isinstance(func, ast.Attribute) and func.attr in IO_METHODS:
                owner = func.value
                prefix = f"{owner.id}." if isinstance(owner, ast.Name) else ""
                return f"{prefix}{func.attr}"
    return None


def _writes(node: ast.stmt) -> bool:
    """Whether this statement issues SQL that takes the write lock."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            head = sub.value.strip().upper()
            if head.startswith(("INSERT", "UPDATE", "DELETE")):
                return True
    return False


def _functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }


GUARDED_FUNCTIONS = [
    (path, name) for path, names in GUARDED.items() for name in names
]


def _ids(param):
    return param.name if isinstance(param, Path) else str(param)


@pytest.mark.parametrize("path,name", GUARDED_FUNCTIONS, ids=_ids)
def test_no_await_sits_between_a_write_and_its_commit(path, name):
    """Mutation observed red: delete any `conn.commit()` that follows an
    `await poll_*` in either poller function.

    The rule, which is the transferable part: **never hold a database write
    transaction across an `await` that performs I/O.** A lock is held in
    wall-clock time and an `await` is an unbounded amount of it.
    """
    fn = _functions(path)[name]
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
                    f"{path.name}:{name}: `await {call}()` at line "
                    f"{node.lineno} runs with an uncommitted write from line "
                    f"{dirty_at} -- the SQLite write lock is held across a "
                    f"network round trip, which is what made "
                    f"`store_closing_line` raise `database is locked`"
                )
            if call:
                # An awaited poller writes internally; the call itself counts
                # as a write, because its INSERTs open the transaction.
                dirty = True
                dirty_at = node.lineno


# --------------------------------------------------------------------------
# The loop-carried half.
#
# A straight-line scan cannot see a hold whose write is the last thing one
# iteration does and whose `await` is the first thing the next one does. That
# is the shape `ensure_estimate_markets_known` had: three `INSERT OR IGNORE`s
# per ticker, one commit after the whole loop, and `await source.fetch(...)` at
# the top of every iteration -- the write lock held across N-1 Kalshi round
# trips.
# --------------------------------------------------------------------------

def _branch_bodies(node: ast.AST) -> list[list]:
    return [
        getattr(node, attr)
        for attr in ("body", "orelse", "finalbody", "handlers")
        if isinstance(getattr(node, attr, None), list)
    ]


def _carried(lineno):
    """Mark a dirty state as inherited from the previous iteration.

    The sentinel is what keeps this test from re-reporting the straight-line
    violations the test above already owns: only an `await` reached while the
    *carried* write is still uncommitted is a loop-carried hold.
    """
    return ("carried", lineno)


def _is_carried(at) -> bool:
    return isinstance(at, tuple)


def _walk(stmts, dirty, dirty_at, on_io):
    """Thread may-be-dirty state through a statement list, in source order.

    Branch-aware rather than flattened, for the reason `_blocks` records: a
    write in one arm of an `if` is not held across an `await` in the other,
    because they never run in the same pass. Arms are walked from the same
    incoming state and their exits are merged (`any`), so a write on *either*
    path leaves the merge dirty. The incoming state is merged in too, because
    an `if` with no `else` and a loop that never runs both fall through.

    Deliberately imprecise in two directions, both recorded in the module
    docstring: a `finally` is merged as an alternative rather than a sequel,
    and a nested loop is walked once rather than to a fixed point.
    """
    for node in stmts:
        if _is_commit(node):
            dirty, dirty_at = False, None
            continue
        branches = _branch_bodies(node)
        if branches:
            outs = [_walk(b, dirty, dirty_at, on_io) for b in branches]
            outs.append((dirty, dirty_at))
            live = [at for is_dirty, at in outs if is_dirty]
            dirty = bool(live)
            inherited = [at for at in live if _is_carried(at)]
            dirty_at = (inherited or live or [None])[0]
            continue
        call = _io_call_name(node)
        if call and dirty:
            on_io(node, call, dirty_at)
        if _writes(node):
            dirty, dirty_at = True, getattr(node, "lineno", "?")
    return dirty, dirty_at


def _loops(fn: ast.AST) -> list[ast.AST]:
    return [
        node
        for node in ast.walk(fn)
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While))
    ]


@pytest.mark.parametrize("path,name", GUARDED_FUNCTIONS, ids=_ids)
def test_no_loop_carries_an_uncommitted_write_into_the_next_iteration(
    path, name
):
    """Mutation observed red: move `ensure_estimate_markets_known`'s
    `conn.commit()` back out of its `for` loop, exactly where it sat until
    2026-09-01. The test above stays green on that mutation -- it is a
    straight-line scan and the hold is across the back edge -- which is why
    this one exists.

    Two passes over each loop body. The first asks whether a path through it
    can reach the back edge with an uncommitted write; if so the second re-runs
    the body from that state and reports the first I/O `await` reached before a
    commit. That `await` runs under a lock taken by the previous iteration.
    """
    fn = _functions(path)[name]
    for loop in _loops(fn):
        exits_dirty, exit_at = _walk(loop.body, False, None, lambda *a: None)
        if not exits_dirty:
            continue
        failures: list[str] = []

        def report(node, call, at):
            if not _is_carried(at):
                # A local write reaching a local `await` is the straight-line
                # test's finding, not this one's. Reporting it here would put
                # the same defect under two names and call a same-iteration
                # hold a back-edge one.
                return
            failures.append(
                f"`await {call}()` at line {node.lineno} runs with the "
                f"uncommitted write from line {at[1]}"
            )

        _walk(loop.body, True, _carried(exit_at), report)
        if failures:
            pytest.fail(
                f"{path.name}:{name}: the loop at line {loop.lineno} reaches "
                f"its back edge with an uncommitted write, and the next "
                f"iteration performs I/O before committing it -- "
                + "; ".join(failures)
                + f". The SQLite write lock is held across every round trip "
                f"after the first, so N missing rows hold it across N-1 of "
                f"them. Commit inside the loop."
            )


def test_the_fast_branch_still_polls_all_four_endpoints():
    """The fix must not have removed a poll while adding commits.

    `poll_fills`, `poll_settlements` and `poll_positions` each ride the balance
    cadence for a recorded reason (the 2026-08-21 ruling, ADR 0064, and the
    2026-08-29 open-positions change). Dropping one to shorten the transaction
    would trade a lock for a hole in the record.
    """
    fn = _functions(POLLER)["poll_portfolio_forever"]
    called = {
        _io_call_name(node)
        for block in _blocks(fn)
        for node in block
        if _io_call_name(node) is not None
    }
    assert called >= {
        "poll_balance", "poll_fills", "poll_settlements", "poll_positions"
    }, called


def test_the_matcher_commits_inside_its_fetch_loop():
    """The positive statement of the fix, so a reader sees it without an AST.

    The guard above proves the absence of a hold; this proves the presence of
    the thing that removes it, and would catch a "fix" that deleted the commit
    outright instead of moving it.
    """
    fn = _functions(MATCHER)["ensure_estimate_markets_known"]
    loops = _loops(fn)
    assert len(loops) == 1, "the fetch loop is the only loop in this function"
    assert any(
        _is_commit(node) for node in ast.walk(loops[0]) if isinstance(node, ast.stmt)
    ), "the per-ticker `conn.commit()` is gone from the fetch loop"
