"""Guards for four places the demo rendered healthy while the live tool was blind.

Three separate failures, one shape. In each, something was verified against the
only rows that were ever going to match it:

    the sweep trace   `/api/window` serves `last_look_*`; nothing in
                      `frontend/src` read it, so the readout built to make a
                      17-hour silence visible reached no screen. This tool is
                      operated from a phone; a field that stops at the wire is
                      not an observability fix.
    demo_execution    the script printed "0 of 300" under prose asserting the
                      sample size was satisfied, because `clv_horizon_hours` was
                      NULL and `NULL = 0.0` is NULL. Scenarios 2 and 3 were
                      byte-identical to scenario 1, which is the exact contrast
                      the script exists to draw.
    seed_demo         the demo's suppression vocabulary and the live one were
                      disjoint: `wide_market` 65 times (0 of 1,564 live),
                      `too_few_books` and `no_market_width` never (~230 each
                      live), and no composite at all -- so every consumer that
                      splits on "," ran only against single tokens.

What these tests do NOT establish
---------------------------------
**The frontend checks are reachability, not rendering.** This repo has no
JavaScript test runner, so they assert that `WindowBanner.tsx` reads the fields
and branches on the states -- not that the resulting pixels are legible, not
that the tone classes resolve, and not that a human would notice the gap. Those
need `npm run build` plus a pair of eyes, and the build is run separately.

**The seeder checks are about vocabulary and shape, not calibration.** They
assert the demo speaks the codes live speaks, produces composites, and gets
every code from `evaluate_suppression`. They say nothing about whether the
*rates* are right; the mix is a hand-set approximation and is documented as one.
"""

from __future__ import annotations

import collections
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from backend.core.suppression import ALL_CHECK_NAMES, Check, SuppressionResult
from backend.odds.timing import ActionableWindow
from backend.seed_demo import seed_all, seed_history
from backend.store import db

REPO = Path(__file__).resolve().parent.parent
API_TS = REPO / "frontend" / "src" / "lib" / "api.ts"
BANNER_TSX = REPO / "frontend" / "src" / "components" / "WindowBanner.tsx"


# `slots_planned` is the whole schedule; the banner renders the *next* slot,
# which `to_dict` already flattens into `next_sweep_ms/_sport/_games/_reason`.
# Listed explicitly rather than allowed by a rule, so adding a second exclusion
# is a decision somebody writes down.
WINDOW_FIELDS_NOT_ON_THE_PHONE = {"slots_planned"}


def _typescript_type_body(source: str, name: str) -> str:
    match = re.search(
        rf"export type {name} = \{{(.*?)\n\}};", source, re.DOTALL
    )
    assert match, f"no `export type {name}` in {API_TS}"
    # Block comments carry prose with colons in it, which would otherwise read
    # as field declarations.
    return re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.DOTALL)


def _typescript_field_names(body: str) -> set[str]:
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??:", body, re.MULTILINE))


@pytest.fixture(scope="module")
def window_payload() -> dict:
    """One `to_dict()`, built from the dataclass rather than from a live app.

    The point is the *key set*, and the keys do not depend on the values.
    """
    return ActionableWindow(
        now_ms=1,
        max_odds_age_ms=900_000,
        fixtures_upcoming=0,
        fixtures_fresh=0,
        open_until_ms=None,
        last_sweep_ms=None,
        last_sweep_sport=None,
        next_slot=None,
        slots_planned=(),
        next_call_ms=None,
        refresh_interval_ms=600_000,
        sweeps_remaining_today=0,
        spent_today=0,
        daily_budget=16,
        budget_day_start_ms=0,
    ).to_dict()


class TestTheSweepTraceReachesTheScreen:
    """A field on the wire that no component reads is not an observability fix.

    Reachability has two halves and this repo keeps checking one. The backend
    chain -- `sweeplog` to `window_status` to `/api/window` -- is pinned by
    `tests/test_sweep_trace.py`. These pin the other half.
    """

    def test_every_served_window_field_is_declared_on_the_phone(
        self, window_payload
    ):
        """The drift check, in the direction the drift actually went.

        Written as "everything the API serves must be typed" rather than
        "everything typed must be served", because the failure was a backend
        addition the frontend never learned about -- three new keys, zero hits
        for `last_look` under `frontend/src`, and no error anywhere, since an
        undeclared key on a JSON response is simply invisible to TypeScript.
        """
        declared = _typescript_field_names(
            _typescript_type_body(API_TS.read_text(encoding="utf-8"), "ActionableWindow")
        )
        served = set(window_payload) - WINDOW_FIELDS_NOT_ON_THE_PHONE
        assert served <= declared, (
            f"/api/window serves {sorted(served - declared)}, which no screen "
            f"can read: they are absent from `type ActionableWindow` in "
            f"{API_TS}"
        )

    @pytest.mark.parametrize(
        "field", ["last_look_ms", "last_look_outcome", "last_look_detail"]
    )
    def test_the_banner_reads_each_sweep_trace_field(self, field):
        """Typed is not rendered. The type is necessary and it is not enough."""
        assert field in BANNER_TSX.read_text(encoding="utf-8"), (
            f"`{field}` is on the wire and typed, but {BANNER_TSX.name} never "
            f"reads it, so it reaches no phone"
        )

    def test_the_banner_shows_the_gap_rather_than_the_two_ages_alone(self):
        """The gap IS the failure state, and nobody subtracts two ages by eye.

        A fresh `last_look` beside a stale `last_sweep` is the loop looking and
        declining every pass -- the 17-hour shape. Printing both numbers and
        leaving the reader to difference them puts the whole diagnostic in the
        one step that does not happen on a phone at a glance.
        """
        source = BANNER_TSX.read_text(encoding="utf-8")
        subtraction = re.search(
            r"last_look_ms\s*-\s*w\.last_sweep_ms", source
        ) or re.search(r"w\.last_look_ms\s*-\s*w\.last_sweep_ms", source)
        assert subtraction, (
            "WindowBanner renders `last_look_ms` and `last_sweep_ms` without "
            "ever differencing them; the gap between the two is the state the "
            "sweep log exists to expose"
        )

    def test_a_null_sweep_log_is_not_rendered_as_calm(self):
        """`null` means "never looked", which is blind, not clear.

        The repo's standing rule -- unreadable resolves to `None`, never `0` --
        has a rendering half: a missing measurement must not be drawn as a
        passing one. A dash where the trace should be is the calm-looking
        version of the outage itself.
        """
        source = BANNER_TSX.read_text(encoding="utf-8")
        assert re.search(r"last_look_ms === null", source), (
            "WindowBanner does not branch on `last_look_ms === null`, so a "
            "database that has never recorded a pass renders the same as one "
            "that looked and declined"
        )


def _run_demo_execution() -> str:
    """The script's real stdout, from a real process.

    Reading the output is the point. `tests/test_execution.py` asserts this
    script is a caller of the order path and never once looks at what it prints,
    which is how three of its six sections spent weeks narrating the opposite of
    their own result.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.demo_execution"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


@pytest.fixture(scope="module")
def demo_sections() -> dict[int, str]:
    """The printed output, split on the script's own `rule()` banners."""
    out = _run_demo_execution()
    parts = re.split(r"={70,}\n(\d)\. ", out)
    # parts[0] is the preamble; then (number, body) pairs.
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


class TestTheExecutionDemoPrintsWhatItNarrates:
    """A demo whose narration can drift from its output is a method that lies.

    Every assertion here reads the process's stdout. Asserting on the gate
    object instead would pass on the broken script: `evaluate_gate` was always
    correct, and it was correctly reporting an empty result set.
    """

    def test_the_empty_record_is_locked_on_the_sample_size(self, demo_sections):
        """The control. Section 1 has no rows and must say so."""
        assert "[FAIL] scored_recommendations" in demo_sections[1]
        assert "0 of 300" in demo_sections[1]

    def test_the_noisy_sample_satisfies_the_size_its_prose_claims(
        self, demo_sections
    ):
        """"The sample size is satisfied and the mean is positive" -- printed
        beneath a `[FAIL]` reading `0 of 300`."""
        section = demo_sections[2]
        assert "[PASS] scored_recommendations" in section, section
        assert "400 of 300" in section, section
        assert "The sample size is" in section

    def test_the_noisy_sample_is_still_stopped_by_the_noise_guard(
        self, demo_sections
    ):
        """The section's whole point: a satisfied floor is not evidence.

        Without this the fix could be "make everything pass", which would
        demonstrate the naive gate rather than the real one.
        """
        section = demo_sections[2]
        assert "[FAIL] clv_survives_noise_guard" in section, section
        assert "not evidence of an edge" in section

    def test_the_consistent_sample_clears_both_evidence_conditions(
        self, demo_sections
    ):
        section = demo_sections[3]
        assert "[PASS] scored_recommendations" in section, section
        assert "[PASS] clv_survives_noise_guard" in section, section
        assert "[FAIL] fee_model_verified" in section, section

    def test_the_three_gate_scenarios_are_distinguishable(self, demo_sections):
        """The contrast is the deliverable.

        Sections 1, 2 and 3 printed byte-identical condition blocks -- three
        databases built to differ, rendering as one. Compared on the verdicts
        rather than on the `scored_recommendations` line alone, because 2 and 3
        *should* agree on the sample size and differ only on the noise guard;
        it is the pattern across all four conditions that has to be unique.
        """
        verdicts = {
            n: tuple(re.findall(r"\[(PASS|FAIL)\] (\w+)", demo_sections[n]))
            for n in (1, 2, 3)
        }
        assert len(set(verdicts.values())) == 3, verdicts

    def test_no_scored_row_is_clustered_by_market_for_want_of_an_event(
        self, demo_sections
    ):
        """`INSERT OR IGNORE` silently dropped every `kalshi_markets` row.

        `first_seen_ms` and `last_seen_ms` are `NOT NULL` and the insert supplied
        neither, so SQLite ignored the constraint failure exactly as it ignores a
        duplicate key -- and the raw `sqlite3.connect` in the script does not
        enable `PRAGMA foreign_keys`, so nothing downstream objected. The only
        symptom was this footnote from the gate.
        """
        for n in (2, 3):
            assert "had no event ticker" not in demo_sections[n], demo_sections[n]


class TestTheDemoSpeaksTheLiveSuppressionVocabulary:
    """The demo produced codes live never writes, and never wrote live's.

    Live, over 1,564 rows: `stale_odds` 616, `too_few_books` ~239,
    `no_market_width` ~230, `wide_market` **0**, and 276+ rows carrying a
    comma-joined composite. The seeder produced `wide_market` 65 times,
    `too_few_books`/`no_market_width` never, and no composite at all.
    """

    @pytest.fixture(scope="class")
    def slate(self, tmp_path_factory):
        path = tmp_path_factory.mktemp("slate") / "demo.db"
        seed_all(path)
        conn = db.open_db(path, read_only=True)
        yield [
            r["suppressed_reason"]
            for r in conn.execute(
                "SELECT suppressed_reason FROM recommendations "
                "WHERE suppressed_reason IS NOT NULL"
            )
        ]
        conn.close()

    @pytest.fixture(scope="class")
    def history(self, tmp_path_factory):
        path = tmp_path_factory.mktemp("history") / "demo.db"
        seed_all(path)
        # Large enough that a 5% arm is not a coin flip, small enough to seed in
        # about a second.
        seed_history(path, n=600)
        conn = db.open_db(path, read_only=True)
        # NULL kept as `""`, not filtered out. Live is 614 clean rows of 1,564,
        # so a rate computed over suppressed rows only would be a rate about a
        # different population than the one the target table describes.
        yield [
            r["suppressed_reason"] or ""
            for r in conn.execute(
                "SELECT suppressed_reason FROM recommendations "
                "WHERE ticker LIKE 'KXHIST%'"
            )
        ]
        conn.close()

    def test_the_slate_produces_a_composite(self, slate):
        """The `,` path had no demo producer.

        `unnest(string_split(suppressed_reason, ','))` in
        `mart_suppression_audit.sql` and `.split(",")` in `routes.py` ran only
        against single tokens, where they are indistinguishable from an identity.
        A preregistered `NOT IN (...)` already matched the wrong population for
        exactly this reason.
        """
        assert any("," in r for r in slate), slate

    @pytest.mark.parametrize("code", ["too_few_books", "no_market_width"])
    def test_the_slate_produces_the_thin_consensus_codes(self, slate, code):
        """~230 rows each live, zero in the demo, because `_seed_books` always
        wrote 4-6 books and every scenario carried a float width."""
        assert any(code in r.split(",") for r in slate), slate

    def test_the_history_produces_the_live_composites(self, history):
        counts = collections.Counter(history)
        assert counts["too_few_books,no_market_width"] > 0, counts.most_common(8)
        assert counts["stale_odds,too_few_books,no_market_width"] > 0, (
            counts.most_common(8)
        )

    def test_the_history_is_mostly_the_two_codes_live_is_mostly_made_of(
        self, history
    ):
        """Shape, not calibration. Live is ~39% `stale_odds` and ~39% clean."""
        stale = sum(1 for r in history if "stale_odds" in r.split(","))
        assert 0.35 <= stale / len(history) <= 0.75, stale / len(history)

    def test_the_history_composite_rate_is_not_zero_and_not_everything(
        self, history
    ):
        """Live carries a composite on at least 276 of 1,564 rows -- 17.6%."""
        rate = sum(1 for r in history if "," in r) / len(history)
        assert 0.08 <= rate <= 0.40, rate

    def test_the_history_does_not_manufacture_a_rule_live_never_fires(
        self, history
    ):
        """`wide_market` is 0 of 1,564 live and was the demo's most common code.

        The seeded widths all sit under `max_market_width`, so the rule cannot
        fire here -- which is the live behaviour rather than a suppression of it.
        """
        assert not any("wide_market" in r.split(",") for r in history)

    def test_every_seeded_code_is_one_the_engine_can_write(self, slate, history):
        """A typo in a seeded string is invisible until a mart drops rows."""
        tokens = {t for r in slate + history for t in r.split(",") if t}
        assert tokens <= set(ALL_CHECK_NAMES), sorted(tokens - set(ALL_CHECK_NAMES))


class TestTheSeededReasonsComeFromTheRules:
    """Not a grep for hardcoded strings -- a substitution.

    `evaluate_suppression` is replaced with one that names a code no rule has,
    and every seeded reason must become that code. A seeder that spells the
    strings itself, or that spells half of them, fails: the string it wrote is
    still there.

    This is the guard that keeps the demo honest as the rules change. The
    previous seeder chose from a hand-written list, so it went on writing
    `wide_market` at 1-in-6 long after the live record had stopped producing it
    at all, and would have gone on writing it after a rename.
    """

    SENTINEL = "demo_fidelity_sentinel"

    def _refuse_everything(self, **_kwargs) -> SuppressionResult:
        return SuppressionResult(
            checks=(Check(self.SENTINEL, False, "substituted for the test"),)
        )

    def test_the_history_takes_every_reason_from_evaluate_suppression(
        self, tmp_path
    ):
        path = tmp_path / "substituted.db"
        seed_all(path)
        with mock.patch(
            "backend.seed_demo.evaluate_suppression", self._refuse_everything
        ):
            seed_history(path, n=40)

        conn = db.open_db(path, read_only=True)
        try:
            reasons = {
                r["suppressed_reason"]
                for r in conn.execute(
                    "SELECT suppressed_reason FROM recommendations "
                    "WHERE ticker LIKE 'KXHIST%'"
                )
            }
        finally:
            conn.close()
        assert reasons == {self.SENTINEL}, (
            # `None` is a possible member, so the set is sorted on `repr` --
            # `sorted()` on a mixed set raises, and a guard that dies with a
            # TypeError reports "the test is broken" where it means "the seeder
            # wrote its own strings".
            f"seed_history wrote {sorted(reasons, key=repr)}; anything other "
            f"than {self.SENTINEL!r} was spelled by the seeder rather than "
            f"decided by the rules"
        )

    def test_the_slate_takes_every_reason_from_evaluate_suppression(
        self, tmp_path
    ):
        """The slate reaches the rules through `engine.build_recommendation`,
        so the substitution goes in there rather than in the seeder."""
        path = tmp_path / "slate-substituted.db"
        with mock.patch(
            "backend.engine.evaluate_suppression", self._refuse_everything
        ):
            seed_all(path)

        conn = db.open_db(path, read_only=True)
        try:
            reasons = {
                r["suppressed_reason"]
                for r in conn.execute("SELECT suppressed_reason FROM recommendations")
            }
        finally:
            conn.close()
        assert reasons == {self.SENTINEL}, sorted(reasons)
