"""No surface that prices a row tells Joe the only way to lose is variance.

The killed sentence sat under the cost block on `OpportunityCard` and, in
prose, in the fifth bullet of `HowToRead`: a multiple of the expected value,
then a run of ten bets, then the clause that granted the premise -- that the
edge itself was not in question and only the swing was. Both of its inputs
(`ev_net_dollars` and `sd_dollars`) are functions of `fair_probability`, which
is the devigged-consensus-vs-Kalshi gap, and that gap is the quantity this
repo has measured twice:

    2026-08-16   beta_hat -0.1412   always-valid [-0.3342, +0.0517]   G = 199
    2026-08-25   beta_hat -0.0756   always-valid [-0.1728, +0.0216]   G = 216

Both intervals lie entirely below the registered NO-SIGNAL threshold of 0.40
and both arms are negative; `CLAUDE.md` says to treat the signal as settled
negative for planning. A sentence whose only named risk is variance therefore
asserts, on the money screen, the one thing the record does not support.
`tests/test_trust_surfaces.py` already refuses the same composite for the
evidence score, for the same reason: *a composite carrying the gap would rank
the least trustworthy rows highest.*

Issue #48, answered A by Joe on 2026-09-16, removed the sentence, both
`Swing, 1 SD` figures, and the three payload fields that fed them
(`sd_dollars`, `losing_run_bets`, `losing_run_probability`). This file is what
stops them coming back, and -- the lesson from
`test_combo_exit_copy_is_small_and_unmeasured_on_every_surface.py` -- what
stops a NEW priced surface being written without anyone checking it.

WHAT KEEPS AN OMISSION FROM PASSING
-----------------------------------
`PRICED_SURFACES` is a registry, not a memory. Every frontend file that
renders a per-row money figure must be in it or `TestTheRegistryCannotBecomeASubset`
names the file; so a sixth screen built next month fails until someone lists
it, rather than passing because nobody remembered it. The claim sweeps run
over the *whole* frontend tree and the whole of the server's non-docstring
copy for the same reason.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Source text, not rendering.** Same instrument and same limit as the combo
  exit sweep: a green suite says the words are not in the files, not that the
  screen renders what it should.
- **Nothing about whether the gap predicts anything.** `beta` is owned by
  `docs/measurements/2026-08-16-clv-signal-test-interim-look.md` and its
  successor; nothing here re-measures it, and the verdict on record is
  UNRESOLVED, not "no signal".
- **Nothing about the rest of the cost block.** "$X for the contracts and $Y
  in fees. All of it is lost if this settles the other way." is a fact about
  the money and is kept; `tests/test_api.py` owns those two fields.
- **Comments are stripped before matching**, so a file may still carry a dated
  record of the removed reasoning -- `lib/liveSizing.ts` names the old field
  in the passage explaining a past defect, deliberately. The rule that follows
  from `tasks/lessons.md` (2026-09-16, tenth) is the other half: a correction
  trail must *describe* the killed sentence, never reproduce it, because a
  Python docstring is not stripped here and would re-trigger the guard.

Mutations, each observed red on 2026-09-16:
  1. restore the "with the edge completely real" clause on `OpportunityCard`
  2. restore the `Swing, 1 SD` <Figure> on `TicketSheet` (the field sweep)
  3. restore `"sd_dollars": sd` in the `_serialise` payload
  4. restore the "Ten bets like that end the week down almost half the time"
     sentence in `HowToRead`'s fifth bullet
  5. delete the `TicketSheet` entry from `PRICED_SURFACES` while the file
     still prices a row (the registry sweep names the unregistered file)
  6. add a fresh "even if the edge is real" string to `backend/notify/discord.py`
     -- an unregistered backend module, so the server-copy sweep is what has
     to name it
  7. neuter `EDGE_IS_REAL` to a pattern that matches nothing, which passes
     every prohibition above perfectly (the anchor names it)

THE THIRD PATTERN (issue #52, answer A, Joe, 2026-09-16)
--------------------------------------------------------
`HowToRead`'s fifth bullet kept the premise after mutation 4 removed the run
length: it said the swing was larger than *the* edge, and it offered a bad
week as something that failed to show the tool was broken. Both grant an
edge -- the second by making the week the thing that fails to reveal one. `A_BAD_RUN_EXONERATES` refuses
that shape across the same three sweeps. The half of the sentence that warns
against chasing losses is kept and is explicitly NOT matched: it is true
whatever `beta` is, and a guard that ate it would leave the screen quieter
about the one risk it can state.

Mutations for that pattern, each observed red on 2026-09-16:
  8. put the retired clause back in `HowToRead` -- the one that offered a
     losing week as failing to show the tool was broken (described rather
     than reproduced, per `tasks/lessons.md` 2026-09-16, tenth)
  9. neuter `A_BAD_RUN_EXONERATES` to a pattern that matches nothing
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
BACKEND = ROOT / "backend"

#: Every surface that puts a per-row money figure in front of Joe, plus the
#: one module that composes them. Enumerated so a new one has to be added by
#: hand; swept below so forgetting is a failure rather than an exemption.
PRICED_SURFACES = [
    pytest.param(FRONTEND / "components" / "OpportunityCard.tsx", id="board-card"),
    pytest.param(FRONTEND / "components" / "TicketSheet.tsx", id="ticket-sheet"),
    pytest.param(FRONTEND / "lib" / "api.ts", id="payload-types"),
    pytest.param(BACKEND / "api" / "serialise.py", id="serialiser"),
]

#: What makes a file a priced surface: it names a money figure that belongs to
#: one recommendation row. Deliberately the *row* fields and not "dollars",
#: which every ledger total and bankroll caption would match.
PRICED_MARKER = re.compile(
    r"\bev_net_dollars\b|\btotal_cost_dollars\b|\bstake_dollars\b"
)

#: The three fields that carried the swing to the screen, and the constant
#: that set the run length. Names rather than sentences, because a field that
#: is served is a field something will eventually render.
SWING_FIELDS = re.compile(
    r"\bsd_dollars\b"
    r"|\blosing_run_probability\b"
    r"|\blosing_run_bets\b"
    r"|\bLOSING_RUN_BETS\b"
)

#: Granting the premise: the edge is not in question, only the variance is.
#: "real edge" on its own is deliberately absent -- `backend/agents/base.py`
#: tells the fleet that "Real edges on this venue are 2-3 cents", which is a
#: claim about size and is the opposite warning.
EDGE_IS_REAL = re.compile(
    r"edge\s+(?:is\s+|was\s+|were\s+)?"
    r"(?:completely|entirely|genuinely|really|perfectly)\s+real"
    r"|(?:completely|entirely|genuinely|perfectly)\s+real\s+edge"
    r"|(?:with|if|assuming|granting|even\s+if|because)\s+the\s+edge\s+"
    r"(?:is\s+|was\s+|were\s+)?real"
    r"|\bedge\s+is\s+real\b",
    re.IGNORECASE,
)

#: The same premise worn the other way round: a bad stretch is offered as
#: something that FAILS to disprove the edge. A sentence of that shape says
#: nothing about variance and everything about what is assumed to be there --
#: only a tool with an edge can have a losing week that fails to reveal it,
#: and the reader is told what the week does not prove rather than what the
#: record says. Retired from `HowToRead`'s fifth bullet by issue
#: #52 (answer A, Joe, 2026-09-16); the protective half of that sentence --
#: a losing week is not a reason to bet bigger -- is true whatever `beta` is
#: and is deliberately NOT matched here.
A_BAD_RUN_EXONERATES = re.compile(
    r"\b(?:losing|lost|bad|down)\s+(?:week|month|run|streak|stretch|day)\b"
    r"[^.]{0,80}?(?:is|are|was|were)\s+not\s+(?:evidence|proof|a\s+sign)"
    r"|\b(?:losing|lost|bad|down)\s+(?:week|month|run|streak|stretch|day)\b"
    r"[^.]{0,80}?(?:is|are|was|were)n['’]?t\s+(?:evidence|proof|a\s+sign)"
    r"|\bnot\s+evidence\s+(?:that\s+)?(?:the\s+)?"
    r"(?:tool|model|engine|system|desk)\s+is\s+broken"
    r"|\b(?:does|do|did)\s+not\s+mean\s+(?:the\s+)?"
    r"(?:tool|model|engine|system|desk)\s+is\s+broken",
    re.IGNORECASE,
)

#: The run-length half of the same sentence. It says nothing about the edge on
#: its own, which is exactly why it has to be refused separately: dropping the
#: clause and keeping the number would leave a probability derived from the
#: same gap on the screen with the qualifier gone.
LOSING_RUN_CLAIM = re.compile(
    r"\b(?:ten|\d+)\s+bets\s+(?:like\s+that|this\s+shape|of\s+this\s+shape)"
    r"|\bbets\s+this\s+shape\s+end\s+down"
    r"|\bend\s+(?:the\s+week\s+)?down\s+(?:almost\s+)?(?:half|\d)"
    r"|\blosing\s+run\s+probab",
    re.IGNORECASE,
)


def code_only(path: Path) -> str:
    """`path`'s source with comments stripped, whitespace collapsed.

    Two lessons in one function. Comments are stripped so a dated record of
    the removed reasoning does not fail the guard that removed it
    (`lib/liveSizing.ts` keeps one on purpose). Whitespace is collapsed
    because JSX and Prettier wrap prose at 80 columns, and a guard that
    matches a phrase only when it fits on one line is a guard against short
    sentences (`tasks/lessons.md`, 2026-09-16, tenth).

    Python docstrings are NOT comments here and are not stripped: server copy
    and module prose are read by the same eyes, and a docstring that quotes
    the killed sentence would put it back in the tree.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        text = re.sub(r"(?m)#.*$", "", text)
    else:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"(?m)^\s*//.*$", "", text)
    return re.sub(r"\s+", " ", text)


def frontend_files() -> list[Path]:
    return sorted(FRONTEND.rglob("*.ts*"))


def _is_docstring(node: ast.AST, parent: ast.AST) -> bool:
    body = getattr(parent, "body", None)
    return (
        isinstance(body, list)
        and bool(body)
        and body[0] is node
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def server_copy(path: Path) -> list[str]:
    """Every non-docstring string literal in `path`, whitespace collapsed.

    Same instrument as the combo-exit sweep and for the same reason: an
    f-string is unparsed so its literal halves read as one sentence rather
    than as fragments that each satisfy nothing.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip: set[int] = set()
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            if _is_docstring(child, parent):
                skip.add(id(child.value))
        if isinstance(parent, ast.JoinedStr):
            for piece in parent.values:
                skip.add(id(piece))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            found.append(ast.unparse(node))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
        ):
            found.append(node.value)
    return [re.sub(r"\s+", " ", s) for s in found]


class TestTheScanReadsRealFiles:
    """The anchor. Every sweep below reports "nothing found" when it passes,
    which is also what a broken regex, a moved directory or an emptied
    registry report."""

    @pytest.mark.parametrize("path", PRICED_SURFACES)
    def test_every_registered_surface_exists_and_prices_a_row(self, path):
        assert path.exists(), f"{path} is registered and missing"
        assert PRICED_MARKER.search(code_only(path)), (
            f"{path.name} is registered as a priced surface and names no "
            "per-row money figure; either it stopped being one (drop it) or "
            "the marker moved (fix PRICED_MARKER)"
        )

    def test_the_tree_walk_finds_the_screens(self):
        names = {p.name for p in frontend_files()}
        for expected in ("OpportunityCard.tsx", "TicketSheet.tsx", "HowToRead.tsx"):
            assert expected in names

    def test_the_claim_patterns_match_the_sentences_they_retired(self):
        """An over-eager edit that makes a regex match nothing passes every
        prohibition perfectly. These are the shapes, reassembled here rather
        than quoted from any file."""
        real = "of the time — with the " + "edge" + " completely real."
        run = "so 10 " + "bets this shape end down" + " 46% of the time"
        assert EDGE_IS_REAL.search(real)
        assert EDGE_IS_REAL.search("even if the edge is real")
        assert LOSING_RUN_CLAIM.search(run)
        assert LOSING_RUN_CLAIM.search("Ten bets like that end the week down")
        assert SWING_FIELDS.search('"sd_dollars": sd,')
        exonerates = "so a losing week is not " + "evidence the tool is broken"
        assert A_BAD_RUN_EXONERATES.search(exonerates)
        assert A_BAD_RUN_EXONERATES.search("a bad run isn't evidence of much")
        assert A_BAD_RUN_EXONERATES.search("that does not mean the model is broken")
        # And do not fire on the warning that says the opposite.
        assert not EDGE_IS_REAL.search("Real edges on this venue are 2-3 cents.")
        # ... nor on the half of the retired sentence that was KEPT. It warns
        # against chasing losses and grants nothing; a guard that swallowed it
        # would push the screen toward saying less than it safely can.
        assert not A_BAD_RUN_EXONERATES.search(
            "a losing week is not a reason to bet bigger"
        )
        assert not A_BAD_RUN_EXONERATES.search(
            "a week's results tell you almost nothing"
        )


class TestNoPricedSurfaceCarriesTheSwingFields:
    """Mutations 2 and 3."""

    @pytest.mark.parametrize("path", PRICED_SURFACES)
    def test_a_registered_surface_does_not_name_them(self, path):
        hit = SWING_FIELDS.search(code_only(path))
        assert hit is None, (
            f"{path.name} names {hit.group(0)!r}: the swing and the run "
            "probability came off every surface with issue #48, because both "
            "are functions of the consensus-vs-Kalshi gap"
        )

    def test_no_file_in_either_tree_names_them(self):
        """The prohibition is cheap to widen, and a field is easy to serve
        from a second module."""
        offenders: list[str] = []
        for path in frontend_files() + sorted(BACKEND.rglob("*.py")):
            hit = SWING_FIELDS.search(code_only(path))
            if hit is not None:
                offenders.append(f"{path.relative_to(ROOT)} {hit.group(0)!r}")
        assert not offenders, (
            f"the swing fields are back in the tree: {offenders}"
        )


class TestNoScreenSaysTheEdgeIsReal:
    """Mutations 1 and 4, and the whole-tree half that makes a new surface
    fail without being registered first."""

    @pytest.mark.parametrize("path", PRICED_SURFACES)
    def test_a_registered_surface_makes_no_claim_about_the_edge(self, path):
        text = code_only(path)
        for pattern, what in (
            (EDGE_IS_REAL, "grants that the edge is real"),
            (LOSING_RUN_CLAIM, "prices a run of bets off that edge"),
            (A_BAD_RUN_EXONERATES, "offers a bad stretch as failing to disprove one"),
        ):
            hit = pattern.search(text)
            assert hit is None, (
                f"{path.name} {what} ({hit.group(0)!r}): the gap it is "
                "computed from measured negative twice, so variance is not "
                "the only way this loses"
            )

    def test_no_frontend_file_makes_the_claim(self):
        offenders: list[str] = []
        for path in frontend_files():
            text = code_only(path)
            for pattern in (EDGE_IS_REAL, LOSING_RUN_CLAIM, A_BAD_RUN_EXONERATES):
                hit = pattern.search(text)
                if hit is not None:
                    offenders.append(
                        f"{path.relative_to(ROOT)} {hit.group(0)!r}"
                    )
        assert not offenders, (
            "screens that offer variance as the only way to lose, outside "
            f"every registered surface: {offenders}"
        )

    def test_no_sentence_the_server_composes_makes_the_claim(self):
        """Mutation 6. `reason_text`, the notes and the pushes are copy too."""
        offenders: list[str] = []
        for path in sorted(BACKEND.rglob("*.py")):
            for sentence in server_copy(path):
                for pattern in (EDGE_IS_REAL, LOSING_RUN_CLAIM, A_BAD_RUN_EXONERATES):
                    hit = pattern.search(sentence)
                    if hit is not None:
                        offenders.append(
                            f"{path.relative_to(ROOT)}: {hit.group(0)!r} in "
                            f"{sentence[:90]!r}"
                        )
        assert not offenders, (
            f"server-composed copy granting the edge: {offenders}"
        )


class TestTheRegistryCannotBecomeASubset:
    """Mutation 5: enumerate rather than remember.

    This is the half that the combo-exit sweep exists to teach. Every
    assertion above runs against a list; a screen that is not on the list is
    checked by the tree sweeps only, and a future prohibition written per
    surface would miss it entirely. So the list has to be complete, and
    incompleteness has to be the failure.
    """

    def test_every_frontend_file_that_prices_a_row_is_registered(self):
        registered = {p.values[0] for p in PRICED_SURFACES}
        unregistered = [
            str(path.relative_to(ROOT))
            for path in frontend_files()
            if PRICED_MARKER.search(code_only(path)) and path not in registered
        ]
        assert not unregistered, (
            "these files render a per-row money figure and are not in "
            f"PRICED_SURFACES, so nothing checks what they claim beside it: "
            f"{unregistered}"
        )

    def test_the_serialiser_is_the_only_backend_module_registered(self):
        """Named so the registry's scope is a decision with a reason rather
        than an accident: the server has one module that composes a priced
        row, and the rest of the backend is swept by copy and by field name
        without being listed."""
        backend_entries = [
            p.values[0] for p in PRICED_SURFACES
            if BACKEND in p.values[0].parents
        ]
        assert backend_entries == [BACKEND / "api" / "serialise.py"]
