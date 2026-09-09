"""A trigger, not a state: `KalshiRestClient.orders` must gain a reader the
day the bid path is armed, or this file goes red.

`tasks/NEXT.md` item 7 (ADR 0120): the reachability walk found
`KalshiRestClient.orders` -- the venue's own view of resting orders -- is read
by nothing. That is inert *today* only because `POST /api/parlays/bid` is
disarmed (`COMBO_ORDERS_ARE_DRY_RUNS = True`, `backend/store/combo_orders.py`,
ADR 0115): nothing rests, so there is nothing to reconcile against.

This is exactly the `check_fee` shape from `tasks/lessons.md` (2026-09-09,
"A justification decays into a lie..."): `Alerter.check_fee` had no caller and
a docstring that correctly said why -- "no order has ever been placed" -- until
the hand-bet path was armed on 2026-09-08 and the excuse expired **in
silence**, leaving 40 hours of fills unreconciled. The lesson drawn from that
was to write down the *condition that ends the excuse*, not just the excuse:
"wire this the day any order path is armed" survives contact with the future
where "no order has ever been placed" does not.

So rather than wiring a reader nobody needs yet (the partner agent ruled
against that -- nothing rests, so there is no caller to build), this converts
the excuse into a tripwire. The assertion is a conjunction:

    (bid path is dry) OR (something production-reachable reads
    `KalshiRestClient.orders`)

It is true today (first disjunct) and stays true if the bid path is ever
re-armed *and* a reconciler is wired in the same change. It goes red the
instant `COMBO_ORDERS_ARE_DRY_RUNS` flips to `False` with no reader added --
which is precisely the silent-gap failure mode `check_fee` demonstrated,
caught before the fact instead of 40 hours after it.

Why this is a standalone file and not a `MUST_HAVE_CALLERS` entry in
`tests/test_has_callers.py`
-----------------------------------------------------------------------------
That list (and `tests/test_reachable_callers.py`, one level deeper) is
opt-in by symbol -- which ADR 0022 already flagged as a check that "cannot
report what is missing from it", and it is exactly the gap that let this
finding sit unnoticed until ADR 0120's walk. But every entry on that list
names an *unconditional* requirement: the symbol must have a caller, full
stop. `KalshiRestClient.orders` is not that shape -- it must have a caller
**only once the bid path is armed**. Enrolling it there as-is would turn this
file red today, which is the wrong direction: nothing rests, wiring a reader
now would be a caller built for a capability nobody uses. So the condition
lives here, next to the flag it is conditioned on, rather than forcing
`MUST_HAVE_CALLERS`' shape onto a claim it cannot express.

How "reads `KalshiRestClient.orders`" is established
-----------------------------------------------------------------------------
The repo's existing convention (`test_has_callers.callers_of`) matches the
*bare symbol name* via `ast.Name`, `ast.Attribute.attr`, and `ast.alias`. That
is too noisy for the symbol `orders` specifically: `backend/api/routes.py`
has `from ..store import orders as orders_store`, whose `ast.alias(name=
"orders", asname="orders_store")` would satisfy the bare-symbol matcher
without calling anywhere near `KalshiRestClient.orders` -- it imports the
unrelated `store/orders.py` module. So this scans for an actual **method
call** shaped `<expr>.orders(...)` instead (an `ast.Call` whose `func` is an
`ast.Attribute` with `attr == "orders"`). `KalshiRestClient.orders` is the
only definition of a method named `orders` in the repo
(`grep -rn "def orders(" --include=*.py .`), so a call shaped this way can
only be reaching it. Everything else about "is it a production caller" is
the existing mechanism, reused rather than reinvented:
`tests.test_has_callers.production_sources` (excludes `tests/`, the demo
seeder, `.venv`, etc.) and `tests.test_has_callers._excluded_from_image`
(excludes callers `.dockerignore` drops from the container).

What this does not establish
-----------------------------------------------------------------------------
That a caller found here actually *reconciles* anything sensible -- only that
something beyond the defining module and its tests calls the method. A caller
that fetched the list and discarded it would satisfy this file while doing
nothing useful. That is the same floor `test_has_callers.py` documents for
every entry on it: a necessary condition, not a proof of correctness.
"""

from __future__ import annotations

import ast

from tests.test_has_callers import ROOT, _excluded_from_image, production_sources

from backend.store.combo_orders import COMBO_ORDERS_ARE_DRY_RUNS

#: The one and only definition, so a call shaped `<expr>.orders(...)` can only
#: be reaching this. Pinned by `TestTheDefinitionAssumptionStillHolds` below --
#: if a second `def orders(` ever appears, the call-site scan below could be
#: matching a different method, and this whole file would be checking nothing.
_DEFINING_MODULE = "backend/kalshi/rest.py"


def _method_call_sites(name: str) -> list[str]:
    """Production files, outside `_DEFINING_MODULE`, containing a call shaped
    `<expr>.<name>(...)`. See the module docstring for why this is narrower
    than the bare-symbol matcher `test_has_callers.callers_of` uses."""
    hits: list[str] = []
    for path in production_sources():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel == _DEFINING_MODULE:
            continue
        try:
            tree = ast.parse(path.read_text("utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == name
            ):
                hits.append(rel)
                break
    return hits


def kalshi_rest_orders_callers() -> list[str]:
    """Production callers of `KalshiRestClient.orders` that ship in the image."""
    return [c for c in _method_call_sites("orders") if not _excluded_from_image(c)]


class TestArmingTheBidPathRequiresAnOrderReader:
    def test_bid_path_is_dry_or_something_reads_kalshis_working_orders(self):
        callers = kalshi_rest_orders_callers()
        assert COMBO_ORDERS_ARE_DRY_RUNS or callers, (
            "`COMBO_ORDERS_ARE_DRY_RUNS` is False -- the bid path "
            "(`POST /api/parlays/bid`) is armed and rests real money on the "
            "exchange -- but nothing production-reachable calls "
            "`KalshiRestClient.orders`. Nothing reconciles the venue's own "
            "view of resting orders against this desk's record of what it "
            "thinks is resting. ADR 0115 disarmed this path on Joe's word "
            "('disarm the bid path'); re-arming it (flip "
            "`COMBO_ORDERS_ARE_DRY_RUNS` back to False, per that ADR's "
            "one-line, its-own-commit convention) must not land alone -- it "
            "must land together with something that calls "
            "`KalshiRestClient.orders` and reconciles what comes back "
            "against `combo_orders`/`working_orders`. This is the `check_fee` "
            "failure from tasks/lessons.md, caught before the fact: a "
            "justification ('nothing rests, so nothing needs reconciling') "
            "that was true when written and stopped being true in silence."
        )


class TestTheDefinitionAssumptionStillHolds:
    """The guard on the guard: if a second method named `orders` ever gets
    defined anywhere in the repo, the call-site scan above could be matching
    calls to *that* method instead, and the whole file would pass by checking
    the wrong thing."""

    def test_only_kalshirestclient_defines_a_method_named_orders(self):
        definitions: list[str] = []
        for path in production_sources():
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            try:
                tree = ast.parse(path.read_text("utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "orders"
                ):
                    definitions.append(f"{rel}:{node.lineno}")
        assert definitions == [f"{_DEFINING_MODULE}:711"], (
            f"expected exactly one `def orders(` at "
            f"{_DEFINING_MODULE}:711 (`KalshiRestClient.orders`), found "
            f"{definitions}. A second definition means the call-site scan "
            f"above can no longer assume `<expr>.orders(...)` reaches "
            f"`KalshiRestClient.orders` specifically."
        )


class TestTheScannerIsNotVacuous:
    """Verified by mutation (see the module docstring's "Verify by disabling"
    step in the task that added this file): flipping `COMBO_ORDERS_ARE_DRY_RUNS`
    to `False` in a scratch copy with no caller added turns
    `test_bid_path_is_dry_or_something_reads_kalshis_working_orders` red;
    restoring it turns it green. This class checks the cheaper, permanent half
    -- that the call-site scanner finds real calls at all, so a scanner bug
    that always returned `[]` cannot be mistaken for "no callers exist"."""

    def test_the_scanner_can_find_a_call_shaped_like_this(self):
        """`KalshiRestClient.fills` is called the same shape (`self.fills(`,
        `api.fills(` etc.) elsewhere in the repo, so the same AST pattern this
        file matches against `orders` is exercised against a symbol known to
        have callers -- proving the pattern-match itself works before trusting
        it to report zero for `orders`."""
        assert _method_call_sites("fills"), (
            "the `<expr>.<name>(...)` call-site scanner found zero calls to "
            "`.fills(`, a method with known production callers -- the "
            "scanner itself is broken, so its zero result for `.orders(` "
            "proves nothing"
        )

    def test_orders_itself_currently_has_no_production_caller(self):
        """Documents the current state this file's conjunction relies on the
        other half of (the bid path being dry) to stay green. If this ever
        starts failing -- a caller appears -- that is good news, not a
        regression, and this assertion should be deleted along with the
        `check_fee`-shaped tripwire test above becoming unconditionally true."""
        assert kalshi_rest_orders_callers() == [], (
            f"`KalshiRestClient.orders` now has production callers: "
            f"{kalshi_rest_orders_callers()}. That's good news, not a bug -- "
            f"update this test's expectation."
        )
