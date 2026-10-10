"""Which team the ticket is betting on, executed rather than read.

**The defect.** `rec.team` is `m.yes_side_team` (`backend/api/routes.py:2949`)
unconditionally, and `backend/runner.py:1278` writes a row for both sides of
every moneyline. So on a NO row `TicketSheet.tsx`'s heading is the name of the
team the bet pays out *against*, corrected only by a small `NO` pill in the meta
row below it.

**Why this runs `node` rather than asserting on source text.** The wrong answer
here is *the other team's name in a grammatical sentence* — it looks entirely
correct on screen, and a substring assertion passes unchanged on a mapping whose
two prepositions have been swapped. That is the whole failure mode, so the
mapping is executed. `frontend/src/lib/betDirection.ts` is plain TypeScript with
no React import and node strips types natively, so the real shipped function is
the one called here. Same reasoning as `tests/test_sweep_tone_predicate.py`.

What this establishes: that `betDirection` maps both sides to the right
preposition, refuses rather than guesses on every input it cannot read, and that
each of its three clauses changes an answer. Plus, by source text, that
`TicketSheet.tsx` calls it and renders the result.

What it does **not** establish: that the sentence is positioned well or is
legible at 320px (no DOM here, and that is `ui-designer`'s question); that
`yes_side_team` is itself correct in the database; or that a prop ever gets a
readable subject — it does not, and cannot, until `market_title` is emitted.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from pathlib import Path

import pytest
from tests._node_driver import node_driver

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "frontend" / "src" / "lib" / "betDirection.ts"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: this guard is real "
        "where node exists (CI and both dev machines) and a missing runtime is "
        "an environment fact, not a pending failure."
    ),
)

_DRIVER = """
import {{ betDirection }} from "{module}";
const rec = JSON.parse(process.argv[2]);
console.log(JSON.stringify({{ out: betDirection(rec) }}));
"""


def direction_of(rec: dict, *, source: str | None = None, tmp_path=None):
    """Call the shipped `betDirection` with `rec` and return its answer.

    `source` substitutes a mutated copy of the module, which is how the
    disabling checks below prove a clause is load-bearing.
    """
    if source is None:
        module_dir = MODULE.parent
    else:
        module_dir = tmp_path
        (module_dir / "betDirection.ts").write_text(source, encoding="utf-8")

    with node_driver(module_dir, _DRIVER.format(module="./betDirection.ts")) as driver:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(rec)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(module_dir),
        )

    assert out.returncode == 0, (
        f"node failed running the predicate:\n{out.stdout}\n{out.stderr}"
    )
    return json.loads(out.stdout.strip())["out"]


# Both rows describe the SAME Kalshi market. This is the pair the fix exists
# for: one team name, two opposite bets. Field values are the real shapes read
# off `/api/board` on the demo instance (`side` is lowercase; `team` is the
# short form, e.g. "Houston", not "Houston Astros").
YES_ROW = {"side": "yes", "team": "Houston"}
NO_ROW = {"side": "no", "team": "Houston"}

#: A prop. `yes_side_team` is NULL, so the heading falls back to a raw ticker.
PROP_ROW = {"side": "yes", "team": None}


class TestThePairThatDecidesTheFix:
    """One market, two sides. If these two agree, there is no fix here."""

    def test_buying_yes_is_betting_on_that_team(self):
        assert direction_of(YES_ROW) == {"preposition": "on", "team": "Houston"}

    def test_buying_no_is_betting_against_the_same_team(self):
        assert direction_of(NO_ROW) == {
            "preposition": "against",
            "team": "Houston",
        }

    def test_the_two_sides_of_one_market_disagree(self):
        """The whole point. Same team, opposite prepositions."""
        yes, no = direction_of(YES_ROW), direction_of(NO_ROW)
        assert yes["team"] == no["team"]
        assert yes["preposition"] != no["preposition"]


class TestItRefusesRatherThanGuesses:
    """Unreadable resolves to nothing, and the caller renders nothing."""

    @pytest.mark.parametrize(
        "team", [None, "", "   "], ids=["null", "empty", "whitespace"]
    )
    def test_no_team_yields_no_sentence(self, team):
        assert direction_of({"side": "yes", "team": team}) is None

    @pytest.mark.parametrize(
        "side",
        [None, "", "buy", "YE", "maybe"],
        ids=["null", "empty", "buy", "truncated", "nonsense"],
    )
    def test_an_unreadable_side_yields_no_sentence(self, side):
        """**Never falls through to "on".**

        A default of "on" would print a confident sentence backing a team on a
        row whose direction is unknown -- which is the exact defect, restored by
        the fix meant to remove it.
        """
        assert direction_of({"side": side, "team": "Houston"}) is None

    def test_case_and_padding_are_tolerated(self):
        """Clamp what you trust. The casing of an enum is not the thing under
        test, and `side` is lowercase today only by the runner's convention."""
        assert direction_of({"side": " NO ", "team": " Houston "}) == {
            "preposition": "against",
            "team": "Houston",
        }


class TestEveryClauseIsLoadBearing:
    """Disable it and watch it fail. A clause that survives is decoration."""

    def test_swapping_the_prepositions_is_caught(self, tmp_path):
        """The failure mode a substring test cannot see."""
        source = MODULE.read_text(encoding="utf-8")
        broken = source.replace(
            'if (side === "yes") return { preposition: "on", team };\n'
            '  if (side === "no") return { preposition: "against", team };',
            'if (side === "yes") return { preposition: "against", team };\n'
            '  if (side === "no") return { preposition: "on", team };',
        )
        assert broken != source, "the mutation did not apply; update this test"
        assert direction_of(NO_ROW, source=broken, tmp_path=tmp_path) == {
            "preposition": "on",
            "team": "Houston",
        }, "swapping the prepositions must change the NO answer"

    def test_dropping_the_no_clause_is_caught(self, tmp_path):
        source = MODULE.read_text(encoding="utf-8")
        broken = source.replace(
            '  if (side === "no") return { preposition: "against", team };\n', ""
        )
        assert broken != source, "the mutation did not apply; update this test"
        assert direction_of(NO_ROW, source=broken, tmp_path=tmp_path) is None

    def test_dropping_the_empty_team_guard_is_caught(self, tmp_path):
        """Without it a prop renders "You are betting on ." -- a sentence with
        no subject, which is worse than the ticker it replaced."""
        source = MODULE.read_text(encoding="utf-8")
        broken = source.replace("  if (team.length === 0) return null;\n", "")
        assert broken != source, "the mutation did not apply; update this test"
        assert direction_of(PROP_ROW, source=broken, tmp_path=tmp_path) == {
            "preposition": "on",
            "team": "",
        }

