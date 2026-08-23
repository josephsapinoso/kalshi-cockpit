"""`gauntlet_view`: the Skeptic panel's board, reconstructed from the reason.

What these tests establish: the reconstruction covers the declared vocabulary
exactly (both directions), the branch pairs report `not_taken` for the arm
that never ran, `sizing:` refusals pass through verbatim, and an unknown code
surfaces rather than vanishing.

What they do not establish: that the verdicts describe the present. They are
facts about the moment the row was written; the route serves `judged_ms`
beside them and the screen captions it.
"""

from __future__ import annotations

from backend.core.suppression import (
    ALL_CHECK_NAMES,
    _FAIL_ONLY_TWIN,
    gauntlet_view,
)


def verdicts(reason):
    return {c["code"]: c["verdict"] for c in gauntlet_view(reason)["checks"]}


class TestTheBoardCoversTheVocabularyExactly:
    def test_every_declared_check_gets_a_verdict_and_nothing_else_does(self):
        """Two-way pin against `ALL_CHECK_NAMES` — the same drift guard the
        gloss test uses. A check added to the vocabulary without a verdict
        here, or a verdict for a code the engine cannot write, both fail."""
        board = gauntlet_view(None)["checks"]
        assert [c["code"] for c in board] == list(ALL_CHECK_NAMES)

    def test_every_fail_only_twin_is_a_declared_check(self):
        for fail_only, sibling in _FAIL_ONLY_TWIN.items():
            assert fail_only in ALL_CHECK_NAMES
            assert sibling in ALL_CHECK_NAMES


class TestACleanRow:
    def test_always_run_checks_pass_and_fail_only_arms_are_not_taken(self):
        """`suppressed_reason IS NULL` means every check that ran passed —
        and the three absent-input arms never ran, which is a different fact
        from passing and must not render as one."""
        board = verdicts(None)
        for name in ALL_CHECK_NAMES:
            if name in _FAIL_ONLY_TWIN:
                assert board[name] == "not_taken", name
            else:
                assert board[name] == "passed", name


class TestAFailedRow:
    def test_named_codes_are_refused_and_the_rest_still_speak(self):
        board = verdicts("stale_odds,too_few_books,no_market_width")
        assert board["stale_odds"] == "refused"
        assert board["too_few_books"] == "refused"
        assert board["no_market_width"] == "refused"
        assert board["stale_kalshi_quote"] == "passed"
        assert board["suspicious_edge"] == "passed"

    def test_a_fail_only_code_marks_its_sibling_not_taken(self):
        """`no_market_width` fired means the width was absent, so
        `wide_market` — the value-present arm — never evaluated. Reporting
        it `passed` would claim a measurement that was never taken."""
        board = verdicts("no_market_width")
        assert board["no_market_width"] == "refused"
        assert board["wide_market"] == "not_taken"

    def test_the_value_present_arm_can_fail_while_its_twin_never_ran(self):
        board = verdicts("wide_market")
        assert board["wide_market"] == "refused"
        assert board["no_market_width"] == "not_taken"

    def test_all_three_branch_pairs_behave_alike(self):
        for fail_only, sibling in _FAIL_ONLY_TWIN.items():
            board = verdicts(fail_only)
            assert board[fail_only] == "refused"
            assert board[sibling] == "not_taken", (fail_only, sibling)


class TestWhatIsNotACheck:
    def test_a_sizing_refusal_passes_through_verbatim(self):
        """`engine.py` writes `sizing:<constraint>` when no check fired; it
        is a refusal with a different owner and must reach the screen with
        its name intact for `SIZING_GLOSS`."""
        view = gauntlet_view("sizing:max_daily_loss_dollars")
        assert view["sizing"] == ["sizing:max_daily_loss_dollars"]
        assert all(c["verdict"] != "refused" for c in view["checks"])

    def test_an_unknown_code_surfaces_rather_than_vanishing(self):
        """A newer server can name a check this build does not know. The
        code must surface — silently dropping it would render a refused row
        as clean."""
        view = gauntlet_view("brand_new_check")
        assert view["unknown"] == ["brand_new_check"]

    def test_empty_string_reads_as_clean(self):
        assert gauntlet_view("") == gauntlet_view(None)
