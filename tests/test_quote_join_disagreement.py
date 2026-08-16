"""§A8.2's disagreement counter is side-dependent, and the first version was not.

`entry_ask_tenths` is the price paid **for the side actually taken**
(`backend/analysis/clv.py:151`), so the ask it must be compared against is
`1000 - no_bid` on a YES row and `1000 - yes_bid` on a NO row. The original
check used the YES-side ask on every row, which flags **every NO row by
construction**. On the 2026-08-16 record it reported 1,826 disagreements that
were exactly the 1,826 `side='no'` rows; the true count is 0.

No test covered this function, which is why it shipped. Every test below was
observed red under the named mutation.

**This counter is not decoration, and calling it one was the second mistake.**
§A8.2 makes `matched / total` the P1 statistic — "a strictly tighter gate than
the one registered" — so the counter is a **precondition input** that can refuse
the primary analysis. Under the side-blind check `matched / total = 1866/3692 =
0.5054`, and the 2026-08-16 interim look should have printed `P1 FAILED` and
reported no `beta_hat` at all. It did not, because the harness was still reading
the superseded statistic (non-NULL half-spread coverage, 1.0000).
`TestP1ReadsMatchedOverTotal` pins that arithmetic.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the live record.** Every row here is built in this file. That
  the deployed join is exact is a measurement, recorded in
  `docs/measurements/2026-08-16-quote-join-bias-result.md`, not a property these
  tests can assert.
- **Nothing about the *value* of `beta`.** The counter gates whether `beta_hat`
  may be reported; it is not a regressor and does not enter `fit()`. So the
  published `-0.1412` is arithmetically unchanged by this correction — while the
  correction is nonetheless what makes reporting it permissible, which is the
  direction that flatters the number and is disclosed for that reason.
- **Nothing about whether a disagreement is a defect.** A market that moved
  between the quote and the write produces one legitimately. The counter counts;
  it does not adjudicate.
- **Nothing about the rest of §A8.2 compliance.** These tests pin the three
  counts, the P1 denominator and the 0.05 disclosure threshold.
  `backend/analysis/signal_test.py:coverage` still implements the superseded
  statistic and is still what `fit()`'s callers see.
"""

from __future__ import annotations

import pytest

from scripts.run_signal_test import (
    A82_MISMATCH_DISCLOSURE_THRESHOLD,
    _quote_disagrees,
    a82_counts,
)


def _row(side: str, ask: int, *, yes_bid: int | None, no_bid: int | None) -> dict:
    return {
        "side": side,
        "entry_ask_tenths": ask,
        "yes_bid_tenths": yes_bid,
        "no_bid_tenths": no_bid,
    }


class TestTheComparisonIsSideDependent:
    """The regression. A NO row priced off the YES bid is not a disagreement.

    Mutation: compare every row against `1000 - no_bid`, i.e. restore the
    original body. **2 of this class's 3 tests go red, and 5 of the 11 in the
    file** -- every one of them a NO-row case. No YES-row test moves, which is
    exactly how the defect survived: a reader who checks the YES case and stops
    sees correct behaviour.
    """

    def test_a_yes_row_whose_ask_matches_the_no_bid_agrees(self):
        # yes ask = 1000 - no_bid = 1000 - 400 = 600
        assert not _quote_disagrees(_row("yes", 600, yes_bid=380, no_bid=400))

    def test_a_no_row_whose_ask_matches_the_yes_bid_agrees(self):
        # no ask = 1000 - yes_bid = 1000 - 380 = 620
        assert not _quote_disagrees(_row("no", 620, yes_bid=380, no_bid=400))

    def test_a_no_row_is_not_judged_against_the_yes_side_ask(self):
        """The two sides' asks differ by the market width, so a side-blind check
        is not merely imprecise -- it is wrong by a quantity that grows with the
        spread. Here the YES ask is 600 and the NO ask is 620.
        """
        row = _row("no", 620, yes_bid=380, no_bid=400)
        assert (1000 - row["no_bid_tenths"]) != row["entry_ask_tenths"]
        assert not _quote_disagrees(row)


class TestARealDisagreementIsStillCaught:
    """The counter must not be neutered into always returning False.

    Mutation: `return False` unconditionally. Both tests here go red; neither
    test above does, which is why this class exists separately.
    """

    def test_a_yes_row_priced_off_a_different_instant_disagrees(self):
        assert _quote_disagrees(_row("yes", 590, yes_bid=380, no_bid=400))

    def test_a_no_row_priced_off_a_different_instant_disagrees(self):
        assert _quote_disagrees(_row("no", 615, yes_bid=380, no_bid=400))

    def test_a_one_tenth_difference_is_a_disagreement(self):
        """Money is integer tenths of a cent and the comparison is exact. A
        tolerance here would silently absorb the deci-cent tick the repo exists
        to respect.
        """
        assert _quote_disagrees(_row("yes", 601, yes_bid=380, no_bid=400))


class TestAMissingQuoteIsNotADisagreement:
    """§A8.2's whole point: "no quote at all" and "a quote that disagrees" are
    different problems with different remedies, and are counted separately.

    Mutation: return `True` when the bid is `None`. The two counts then double-
    count the same rows and their sum exceeds the population.
    """

    def test_a_yes_row_with_no_opposite_bid_is_not_counted(self):
        assert not _quote_disagrees(_row("yes", 600, yes_bid=380, no_bid=None))

    def test_a_no_row_with_no_opposite_bid_is_not_counted(self):
        assert not _quote_disagrees(_row("no", 620, yes_bid=None, no_bid=400))

    def test_the_side_that_matters_is_the_opposite_one(self):
        """A NO row missing only `no_bid` still has everything the check needs,
        and must be judged rather than skipped. Mutation: key the `None` guard
        on `no_bid_tenths` regardless of side -- this row is then dropped from
        the count and a real disagreement goes unreported.
        """
        assert _quote_disagrees(_row("no", 615, yes_bid=380, no_bid=None))


class TestSideIsReadCaseInsensitively:
    """The column is free text in SQLite and the record carries lowercase.

    Mutation: compare `row["side"] == "no"` without lowering. An upstream writer
    that stored 'NO' would silently revert every NO row to the YES-side
    comparison -- the original bug, reintroduced by data rather than by code.
    """

    def test_upper_case_no_is_still_a_no_row(self):
        assert not _quote_disagrees(_row("NO", 620, yes_bid=380, no_bid=400))

    def test_a_missing_side_falls_back_to_the_yes_comparison(self):
        """Not a judgement call: the fallback must be *some* fixed side, and YES
        keeps the behaviour of every row the original check got right. A row
        with no side is malformed and belongs in the extraction's problem, not
        this counter's.
        """
        row = {
            "side": None,
            "entry_ask_tenths": 600,
            "yes_bid_tenths": 380,
            "no_bid_tenths": 400,
        }
        assert not _quote_disagrees(row)


class TestA82SplitsThreeWaysNotTwo:
    """§A8.2: "Three counts are reported, never two."

    `no_quote` and `quote_mismatch` are different failures with different
    remedies -- one is missing data, the other is a control recovered from the
    wrong observation -- and P1 as originally registered refused only the
    second.

    Mutation: fold `quote_mismatch` into `matched`. `test_a_mismatch_is_not_
    counted_as_matched` goes red, and with it the P1 gate below, because a run
    with every control joined off the wrong quote would then report P1 = 1.0000.
    """

    def test_the_three_counts_partition_the_population(self):
        rows = [
            _row("yes", 600, yes_bid=380, no_bid=400) | {"half_spread_tenths": 110.0},
            _row("no", 615, yes_bid=380, no_bid=400) | {"half_spread_tenths": 110.0},
            _row("yes", 600, yes_bid=380, no_bid=None) | {"half_spread_tenths": None},
        ]
        counts = a82_counts(rows)
        assert counts == {"matched": 1, "quote_mismatch": 1, "no_quote": 1}
        assert sum(counts.values()) == len(rows)

    def test_a_mismatch_is_not_counted_as_matched(self):
        rows = [_row("no", 615, yes_bid=380, no_bid=400) | {"half_spread_tenths": 110.0}]
        assert a82_counts(rows)["matched"] == 0

    def test_no_quote_outranks_mismatch_so_a_row_is_counted_once(self):
        """A row with no half-spread is `no_quote` even if its bids would also
        fail the identity. Mutation: test `_quote_disagrees` first -- the counts
        then sum to more than the population and P1's denominator is wrong.
        """
        rows = [_row("no", 615, yes_bid=380, no_bid=400) | {"half_spread_tenths": None}]
        assert a82_counts(rows) == {"matched": 0, "quote_mismatch": 0, "no_quote": 1}

    def test_an_empty_population_yields_zeroes_not_a_crash(self):
        assert a82_counts([]) == {"matched": 0, "quote_mismatch": 0, "no_quote": 0}


class TestP1ReadsMatchedOverTotal:
    """The defect that let `beta_hat` be published on 2026-08-16.

    §A8.2: "P1's 0.90 floor now applies to `matched / total`, not to non-NULL
    half-spread coverage. That is a strictly tighter gate than the one
    registered." The harness read the looser statistic, which is 1.0000 on a
    record where every control is present but half are joined off the wrong
    quote.

    These tests pin the arithmetic of the gate, not the harness's printing.
    """

    def test_the_side_blind_record_would_have_failed_p1(self):
        """The actual 2026-08-16 shape: 1,866 matched, 1,826 mismatched, 0
        missing. Non-NULL coverage is 1.0000 and P1 is 0.5054 -- the two
        statistics disagree by 0.4946, and only one of them refuses.
        """
        rows = [
            _row("yes", 600, yes_bid=380, no_bid=400) | {"half_spread_tenths": 110.0}
            for _ in range(1866)
        ] + [
            _row("no", 615, yes_bid=380, no_bid=400) | {"half_spread_tenths": 110.0}
            for _ in range(1826)
        ]
        counts = a82_counts(rows)
        p1 = counts["matched"] / len(rows)
        assert counts["no_quote"] == 0
        assert p1 == pytest.approx(0.5054, abs=1e-4)
        assert p1 < 0.90

    def test_the_corrected_record_passes_p1(self):
        """Same rows, side-aware. Every one is `matched`, so P1 is 1.0000.

        This is the disclosure the write-up owes: the correction moves P1 from
        FAIL to PASS, which is the direction that rescues the published number.
        """
        rows = [
            _row("yes", 600, yes_bid=380, no_bid=400) | {"half_spread_tenths": 110.0}
            for _ in range(1866)
        ] + [
            _row("no", 620, yes_bid=380, no_bid=400) | {"half_spread_tenths": 110.0}
            for _ in range(1826)
        ]
        counts = a82_counts(rows)
        assert counts == {"matched": 3692, "quote_mismatch": 0, "no_quote": 0}
        assert counts["matched"] / len(rows) == 1.0


class TestTheDisclosureThresholdIsTheRegisteredOne:
    """§A8.2 fixes 0.05, and the harness prints the sentence rather than
    trusting an author to remember it.

    Mutation: raise the constant to 0.50. The 2026-08-16 look at 0.4946 then
    falls below it and the mandated disclosure is silently skipped -- which is
    exactly what happened when no constant existed at all.
    """

    def test_the_threshold_is_five_percent(self):
        assert A82_MISMATCH_DISCLOSURE_THRESHOLD == 0.05

    def test_the_side_blind_mismatch_rate_would_have_tripped_it(self):
        assert (1826 / 3692) > A82_MISMATCH_DISCLOSURE_THRESHOLD
