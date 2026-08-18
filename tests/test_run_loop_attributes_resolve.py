"""Every attribute `scripts/run_loop.py` reaches for actually exists.

**What this establishes:** that each `budget.X`, `alerter.X`, `tempo.X` and
`counts.X` named in the loop resolves on the class the loop actually binds
there. Statically, without running a pass.

**What it does not establish:** that the call is *correct* -- right arguments,
right semantics, right time. It catches the name, not the meaning. It also
cannot see attributes reached dynamically (`getattr`), and there are none in
that file today.

Why it exists, and the shape is the point
-----------------------------------------
On 2026-08-18 `scripts/run_loop.py` shipped `budget.remaining_today()` to the
live instance. `remaining_today` is a **property on `BudgetState`**, which
`CreditBudget.state(now_ms)` returns -- `CreditBudget` itself has no such
attribute. Every pass raised `AttributeError` after recording, and five
consecutive failures would have taken the container down.

**Nothing could have caught it.** The whole of `run_loop.main()` is one long
function with no caller but `__main__`, so it is never imported by a test and
never executed by one. `tests/test_has_callers.py` verified that
`alerter.check_credits` *is called* -- which was true, and useless, because the
call could not run. **"The symbol is referenced" and "the reference resolves"
are different facts**, and the first was the only one under test.

That is the same gap in a different coat as the defect this file's own session
was fixing: a test that constructs the thing it is checking. Here the test
constructed the call graph by grepping for a name, and a name is not a call.

The general fix is a static walk, because the specific fix -- unit-testing
`score_settle_and_alert` -- would need most of a container. This walk costs
nothing, needs no fixtures, and covers every future call site in the file
without anyone remembering to add one.

**Deliberately not a type checker.** mypy over `scripts/` would subsume this and
much more; it is also a project-sized decision with its own ADR, and this repo
has none today. If one lands, delete this file and say so in the commit.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.notify.alerts import Alerter
from backend.odds.budget import CreditBudget
from backend.scheduler import Tempo
from backend.runner import PassCounts

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_LOOP = REPO_ROOT / "scripts" / "run_loop.py"

# The local name the loop binds, and the class it binds there. Each pair was
# read off `main()`; a new long-lived local worth checking gets added here.
#
# `counts` is `PassCounts` at every site in this file -- `one_pass` builds it
# from `run_once`/`run_quote_pass`, both of which return one.
BOUND = {
    "budget": CreditBudget,
    "alerter": Alerter,
    "tempo": Tempo,
    "counts": PassCounts,
}


def attributes_reached(name: str) -> set[str]:
    """Every `name.attr` in `run_loop.py`, from the AST rather than a regex.

    A regex would also match the string `"budget.remaining_today"` inside a log
    line or a docstring -- and this file's whole subject is a check that looked
    like it was verifying something and was not.
    """
    tree = ast.parse(RUN_LOOP.read_text(encoding="utf-8"))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == name
    }


class TestEveryAttributeResolves:
    @pytest.mark.parametrize("name,cls", sorted(BOUND.items(), key=lambda kv: kv[0]))
    def test_the_loop_reaches_for_nothing_that_does_not_exist(self, name, cls):
        reached = attributes_reached(name)
        missing = sorted(a for a in reached if not hasattr(cls, a))
        assert not missing, (
            f"`scripts/run_loop.py` reaches for {name}.{{{', '.join(missing)}}} "
            f"and {cls.__name__} has no such attribute. This raises "
            f"AttributeError on the deployed machine and nowhere else -- "
            f"`main()` has no caller but `__main__`, so no test executes it. "
            f"Check whether the attribute lives on a value the object RETURNS "
            f"rather than on the object: `remaining_today` is a property on "
            f"`BudgetState`, which is what `CreditBudget.state()` gives you."
        )

    @pytest.mark.parametrize("name,cls", sorted(BOUND.items(), key=lambda kv: kv[0]))
    def test_the_walk_actually_found_something(self, name, cls):
        """Vacuity guard, and it is not decoration here.

        If a rename made the AST walk match nothing, every assertion above
        would pass over an empty set -- a green test proving nothing, which is
        the exact failure this file was written about. Asserting a floor means
        the walk breaking is visible as a failure rather than as silence.
        """
        assert len(attributes_reached(name)) >= 2

    def test_the_specific_regression_stays_caught(self):
        """The 2026-08-18 defect, pinned.

        `remaining_today` is a property on `BudgetState`, never on
        `CreditBudget`. If someone adds a convenience method of that name to
        `CreditBudget` this test should be deleted, not adjusted -- the hazard
        would genuinely be gone.
        """
        from backend.odds.budget import BudgetState

        assert hasattr(BudgetState, "remaining_today")
        assert not hasattr(CreditBudget, "remaining_today")
