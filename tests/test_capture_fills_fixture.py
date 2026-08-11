"""The capture script's state machine, driven to every branch.

This file exists because the script had **no tests at all** while being the
instrument that answers a registered question (Amendment A §A5). Its settlements
half printed prose and fell through to `return 0`, so "nothing new has settled"
and "the thing we were waiting for arrived" produced the same exit code. Two
handoffs recorded that it "returned PREMATURE"; the word appears nowhere in the
script's history.

Every assertion here was verified by breaking the code it defends and watching
it go red. The mutations are named beside each class -- an unnamed "it passes"
is the decoration this repo keeps finding.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from capture_fills_fixture import (  # noqa: E402
    BASELINE_SETTLEMENT_COUNT,
    EXIT_CONFIG,
    EXIT_FILLS_ENVELOPE,
    EXIT_MEANING,
    EXIT_NO_FILLS,
    EXIT_OK,
    EXIT_SETTLEMENTS_CONTRADICTED,
    EXIT_SETTLEMENTS_PREMATURE,
    FILLS_NO_KEY,
    FILLS_NONE,
    FILLS_OK,
    SETTLEMENTS_ABSENT,
    SETTLEMENTS_NO_KEY,
    SETTLEMENTS_OK,
    SETTLEMENTS_PREMATURE,
    classify_fills,
    classify_settlements,
    decide_exit_code,
)


def _settlements(n: int) -> list[dict]:
    """`n` settlement-shaped records. Only the count is under test."""
    return [{"ticker": f"T{i}", "fee_cost": "0.01"} for i in range(n)]


class TestBaselineIsTheMeasuredCount:
    """Mutation seen red: BASELINE_SETTLEMENT_COUNT = 0."""

    def test_baseline_is_fifty_five(self):
        # Measured 2026-08-10 against the production account. If this number
        # moves, the premature test moves with it and every earlier PREMATURE
        # verdict was taken against a different baseline.
        assert BASELINE_SETTLEMENT_COUNT == 55


class TestSettlementsClassification:
    """Mutations seen red, one per assertion:

    - `if settlements is None` -> `if False`
    - `if not settlements` -> `if False`
    - `len(settlements) <= baseline` -> `len(settlements) < baseline`
    - `len(settlements) <= baseline` -> `len(settlements) > baseline`
    """

    def test_missing_key_is_not_absent(self):
        # None means the envelope was renamed. Distinct from an empty list,
        # which means the account's history vanished. Opposite responses.
        assert classify_settlements(None) == SETTLEMENTS_NO_KEY

    def test_empty_list_contradicts_the_measurement(self):
        assert classify_settlements([]) == SETTLEMENTS_ABSENT

    def test_exactly_the_baseline_is_premature(self):
        # The boundary that matters: 55 is what was already there, so 55 is
        # nothing new. An off-by-one here reports the old history as a result.
        assert classify_settlements(_settlements(55)) == SETTLEMENTS_PREMATURE

    def test_below_the_baseline_is_premature(self):
        assert classify_settlements(_settlements(54)) == SETTLEMENTS_PREMATURE

    def test_one_above_the_baseline_is_the_only_way_to_be_ok(self):
        assert classify_settlements(_settlements(56)) == SETTLEMENTS_OK

    def test_baseline_is_injectable_so_the_boundary_is_testable(self):
        assert classify_settlements(_settlements(3), baseline=3) == (
            SETTLEMENTS_PREMATURE
        )
        assert classify_settlements(_settlements(4), baseline=3) == SETTLEMENTS_OK


class TestFillsClassification:
    """Mutations seen red: `if fills is None` -> `if False`;
    `if not fills` -> `if False`."""

    def test_missing_key_is_not_empty(self):
        assert classify_fills(None) == FILLS_NO_KEY

    def test_empty_is_a_state_not_an_error(self):
        assert classify_fills([]) == FILLS_NONE

    def test_populated_is_ok(self):
        assert classify_fills([{"fee_cost": "0.01"}]) == FILLS_OK


class TestExitCodePriority:
    """The ordering is the fix. Mutations seen red:

    - moving the `SETTLEMENTS_PREMATURE` check below the `FILLS_NONE` check
    - promoting the fills-envelope check above the settlements-envelope check
    - `return EXIT_SETTLEMENTS_PREMATURE` -> `return EXIT_OK`
    - `EXIT_SETTLEMENTS_PREMATURE = 4` -> `= 3`, colliding two codes

    **Not** claimed: swapping the settlements-envelope and premature checks.
    That mutation was applied and stayed GREEN, and it is right that it did --
    a status cannot be both `NO_KEY` and `PREMATURE`, so the swap is
    semantically equivalent and proves nothing about either guard. It is
    recorded here rather than quietly dropped, because a mutation list is a
    claim about what was verified.
    """

    def test_premature_outranks_zero_fills(self):
        # THE REGRESSION THIS FILE EXISTS FOR. The calibration trades have not
        # been placed, so fills is guaranteed empty. If zero-fills wins, the
        # settlements verdict -- the registered question -- can never be the
        # exit code, which is exactly the old behaviour.
        assert (
            decide_exit_code(SETTLEMENTS_PREMATURE, FILLS_NONE)
            == EXIT_SETTLEMENTS_PREMATURE
        )

    def test_premature_is_not_success(self):
        # The defect in one line: the old script returned 0 here.
        assert decide_exit_code(SETTLEMENTS_PREMATURE, FILLS_OK) != EXIT_OK
        assert (
            decide_exit_code(SETTLEMENTS_PREMATURE, FILLS_OK)
            == EXIT_SETTLEMENTS_PREMATURE
        )

    def test_a_renamed_settlements_envelope_outranks_everything(self):
        for fills_status in (FILLS_OK, FILLS_NONE, FILLS_NO_KEY):
            assert (
                decide_exit_code(SETTLEMENTS_NO_KEY, fills_status)
                == EXIT_SETTLEMENTS_CONTRADICTED
            )

    def test_vanished_settlements_outrank_everything(self):
        for fills_status in (FILLS_OK, FILLS_NONE, FILLS_NO_KEY):
            assert (
                decide_exit_code(SETTLEMENTS_ABSENT, fills_status)
                == EXIT_SETTLEMENTS_CONTRADICTED
            )

    def test_renamed_fills_envelope_when_settlements_are_fine(self):
        assert (
            decide_exit_code(SETTLEMENTS_OK, FILLS_NO_KEY) == EXIT_FILLS_ENVELOPE
        )

    def test_zero_fills_only_wins_once_settlements_moved(self):
        assert decide_exit_code(SETTLEMENTS_OK, FILLS_NONE) == EXIT_NO_FILLS

    def test_both_present_is_the_only_zero(self):
        assert decide_exit_code(SETTLEMENTS_OK, FILLS_OK) == EXIT_OK

    def test_zero_is_reachable_from_exactly_one_input_pair(self):
        # Guards against a future edit widening success. Every other
        # combination must be non-zero, and there are twelve of them.
        zeros = [
            (s, f)
            for s in (
                SETTLEMENTS_OK,
                SETTLEMENTS_PREMATURE,
                SETTLEMENTS_ABSENT,
                SETTLEMENTS_NO_KEY,
            )
            for f in (FILLS_OK, FILLS_NONE, FILLS_NO_KEY)
            if decide_exit_code(s, f) == EXIT_OK
        ]
        assert zeros == [(SETTLEMENTS_OK, FILLS_OK)]


class TestEveryCodeCanBeRead:
    """Mutation seen red: deleting an EXIT_MEANING entry."""

    @pytest.mark.parametrize(
        "code",
        [
            EXIT_OK,
            EXIT_FILLS_ENVELOPE,
            EXIT_CONFIG,
            EXIT_NO_FILLS,
            EXIT_SETTLEMENTS_PREMATURE,
            EXIT_SETTLEMENTS_CONTRADICTED,
        ],
    )
    def test_code_has_a_meaning(self, code):
        assert EXIT_MEANING[code].strip()

    def test_codes_are_distinct(self):
        codes = [
            EXIT_OK,
            EXIT_FILLS_ENVELOPE,
            EXIT_CONFIG,
            EXIT_NO_FILLS,
            EXIT_SETTLEMENTS_PREMATURE,
            EXIT_SETTLEMENTS_CONTRADICTED,
        ]
        assert len(set(codes)) == len(codes)

    def test_premature_never_reads_as_a_zero_charge(self):
        # start.md: "An absent settlement row is NOT a $0.00 charge." The text
        # a human reads must not permit that reading.
        text = EXIT_MEANING[EXIT_SETTLEMENTS_PREMATURE].lower()
        assert "not a zero" in text
        assert "premature" in text
