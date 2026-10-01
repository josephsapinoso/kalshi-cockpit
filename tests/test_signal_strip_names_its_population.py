"""`SignalStrip` must say which games it counted, whenever that is not all of
them.

On 2026-08-24 this component rendered

    SIGNAL TEST   NO SIGNAL   311 of 300 games

and both numbers were honest. 311 was the cluster count the endpoint served and
300 was the registered floor. The sentence *between* them was not honest,
because nothing on the page said what the 311 was a count **of**: it was a fit
pooled across four `strategy_config_version`s, and §P4/§7 of
`docs/measurements/2026-08-09-preregistration-clv-signal-test.md` make the
primary the modal version alone — 216 games, below the floor, UNRESOLVED.

The backend defect is fixed in `backend/analysis/clv_signal.py` and pinned by
`tests/test_clv_signal.py`; `clusters` is now the primary's count and the
screen's arithmetic is right again on its own. **This file guards the second
half**, which is a product duty rather than a statistical one: a number
compared against a threshold has to name its population, because a reader who
cannot see the narrowing cannot audit the comparison. ADR 0071 §2.2 reserves
"braking" for exactly the case where a screen would otherwise state something
false.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing renders here.** The assertions are over **source text**, because
  this repo has no JS test runner (`frontend/package.json` has `dev`, `build`,
  `start`, `lint` and no test script). They prove the disclosure is written and
  is conditional; they do not prove it reaches the DOM, that it is legible at
  390px, or that a reader understands it. Only opening the page does that.
- **Nothing about the statistic.** Whether `clusters` is the right number is
  `tests/test_clv_signal.py`'s claim and the registration's, not this file's.
- **Nothing about the other states.** The refusal and declaring branches have
  their own copy and are not asserted here.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRIP = ROOT / "frontend" / "src" / "components" / "SignalStrip.tsx"
API_TS = ROOT / "frontend" / "src" / "lib" / "types" / "signal.ts"


def _source() -> str:
    return STRIP.read_text(encoding="utf-8")


class TestTheScreenNamesThePopulationItCounted:
    def test_the_disclosure_is_rendered_at_all(self):
        """Mutation observed red: delete the `modal_config_applied &&` block."""
        source = _source()
        assert "modal_config_applied" in source
        assert "strategy version" in source

    def test_the_disclosure_is_conditional_on_the_narrowing(self):
        """It must not appear when the record holds one config version.

        An unconditional "counting version N only" on a single-version record
        would describe a narrowing that did not happen, which is the same
        failure in the opposite direction.

        Mutation observed red: change the guard to `{true && (`.
        """
        source = _source()
        assert "{modal_config_applied && (" in source

    def test_the_excluded_row_count_travels_with_it(self):
        """"Version 4 only" without a magnitude is not a disclosure -- the
        reader cannot tell whether 12 rows or 2,097 were set aside.

        Mutation observed red: drop `non_modal_rows_excluded` from the copy.
        """
        source = _source()
        assert "non_modal_rows_excluded" in source

    def test_it_says_why_rather_than_only_what(self):
        """The registration's reason, in plain words, because a beginner reading
        "modal version" learns nothing. `CLAUDE.md`'s standing instruction is
        that every term is defined at first use."""
        source = _source()
        assert "a mixture of strategies is not one strategy measured for longer" in source

    def test_the_wire_type_carries_the_fields_the_copy_reads(self):
        """A renderer cannot disclose what the payload does not send.

        Mutation observed red: remove `modal_config_applied` from
        `ActionableSignal["population"]` in `lib/api.ts` -- `tsc` fails, and so
        does this.
        """
        api = API_TS.read_text(encoding="utf-8")
        for field in (
            "modal_config_applied",
            "modal_config_version",
            "non_modal_rows_excluded",
            "strategy_config_versions",
        ):
            assert field in api, field


RESULT_DOC = "docs/measurements/2026-10-01-clv-signal-test-result.md"


class TestTheStripNamesTheRegisteredResultOnceTheStopFired:
    """#256. Past section 7's stop the strip is a frozen live recompute, and
    the registered answer is the section 8 file, not the strip.

    Source-text assertions only (no JS runner): they prove the pointer is
    written and conditional on `signal.frozen`, not that it renders.
    """

    def test_the_copy_names_the_result_file(self):
        """Mutation observed red: remove the path from SignalStrip.tsx."""
        assert RESULT_DOC in _source()

    def test_the_pointer_is_conditional_on_the_stop_having_fired(self):
        """Before the stop there is no result file to point at.

        Mutation observed red: drop the `signal.frozen &&` guard.
        """
        assert "{signal.frozen && (" in _source()

    def test_it_says_its_own_figure_is_not_the_registered_one(self):
        assert "not the registered result" in _source()

    def test_the_backend_constant_matches_the_frontend_pointer(self):
        from backend.analysis.clv_signal import REGISTERED_RESULT_DOC

        assert REGISTERED_RESULT_DOC == RESULT_DOC
        assert (ROOT / RESULT_DOC).exists()

    def test_unresolved_is_never_rendered_as_no_signal_in_the_stopped_copy(self):
        """The stopped-state copy may only say 'no signal' to refuse it."""
        source = _source()
        start = source.index("{signal.frozen && (")
        block = source[start : source.index(")}", start)].lower()
        assert "unresolved" in block
        for line in block.splitlines():
            if "no signal" in line:
                assert "not " in line or "never" in line, line
