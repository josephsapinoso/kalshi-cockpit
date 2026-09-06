"""The parlay census analyzer's arithmetic, pinned against its registration.

`docs/measurements/2026-09-05-parlay-census-registration.md` §8 fixes H1's
critical values **by hand** at `k <= 18` (upheld) and `k >= 34` (refuted) for
`n = 52`, and requires that any recomputation be done "by the committed
instrument, not by hand". This file is where the two are checked against each
other: the registration's typed numbers, and what
`scripts/measure_parlay_census.py` derives from an exact Clopper-Pearson
interval with no scipy.

**Why that matters more than it looks.** The hand numbers were written before
the analyzer existed. If they disagreed, one of them is wrong and there would
be no way to tell which after the data was seen -- the temptation being to
adopt whichever boundary the observed `k` falls the friendly side of. Pinning
the agreement now removes that choice.

Nothing here reads the live database, the pulled copy, or any per-row datum.
These are properties of the arithmetic on synthetic inputs.
"""

from __future__ import annotations

import sys

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from measure_parlay_census import (          # noqa: E402
    BUCKET_EDGES,
    H1_ALPHA,
    H1_NULL,
    MAX_UNREADABLE_SHARE,
    W_END,
    W_START,
    binom_two_sided_p,
    clopper_pearson,
    critical_values,
    g_eff,
)


class TestTheInstrumentAgreesWithTheRegistration:
    def test_the_critical_values_at_the_expected_n_are_18_and_34(self):
        """§8, verbatim: `k <= 18` upholds, `k >= 34` refutes, at n = 52.

        Mutation observed red: change `H1_NULL` to 0.45.
        """
        assert critical_values(52) == (18, 34)

    def test_the_registered_constants_are_the_registered_values(self):
        assert (W_START, W_END) == (1787011200000, 1788566400000)
        assert H1_NULL == 0.5
        assert H1_ALPHA == 0.05
        assert MAX_UNREADABLE_SHARE == 0.20
        assert BUCKET_EDGES == (20, 50, 150, 400, 999)


class TestTheExactIntervalIsExact:
    def test_it_brackets_the_point_estimate(self):
        lo, hi = clopper_pearson(26, 52)
        assert lo < 0.5 < hi

    def test_the_boundaries_are_closed_rather_than_wrapped(self):
        assert clopper_pearson(0, 52)[0] == 0.0
        assert clopper_pearson(52, 52)[1] == 1.0

    def test_a_zero_denominator_refuses_rather_than_dividing(self):
        """`n = 0` is a state, not a proportion of zero."""
        assert clopper_pearson(0, 0) == (0.0, 1.0)

    @pytest.mark.parametrize("k,n", [(18, 52), (34, 52), (1, 10), (9, 10)])
    def test_the_interval_excludes_the_null_exactly_when_the_verdict_does(
        self, k, n
    ):
        lo, hi = clopper_pearson(k, n)
        upheld, refuted = critical_values(n)
        if upheld is not None and k <= upheld:
            assert hi < H1_NULL
        if refuted is not None and k >= refuted:
            assert lo > H1_NULL


class TestTheTwoSidedPValue:
    def test_the_null_itself_is_p_one(self):
        assert binom_two_sided_p(26, 52) == pytest.approx(1.0)

    def test_an_extreme_is_small(self):
        assert binom_two_sided_p(52, 52) < 1e-14

    def test_it_is_symmetric_under_the_null(self):
        assert binom_two_sided_p(10, 52) == pytest.approx(
            binom_two_sided_p(42, 52)
        )


class TestConcentration:
    def test_one_cluster_holding_everything_is_one_effective_cluster(self):
        assert g_eff([52]) == pytest.approx(1.0)

    def test_even_clusters_give_their_own_count(self):
        assert g_eff([4, 4, 4, 4]) == pytest.approx(4.0)

    def test_a_dominant_cluster_collapses_the_effective_count(self):
        """The shape the registration's downgrade 2 exists to catch: nominally
        many clusters, effectively very few."""
        assert g_eff([40, 1, 1, 1, 1]) < 2.0

    def test_no_clusters_is_zero_rather_than_a_division(self):
        assert g_eff([]) == 0.0


class TestTheInstrumentCannotReachTheVenue:
    """§11.3 and Amendment 1 A6: `lookup_combo` is never called, for any
    ticker, for any reason -- and importing nothing from `backend` is what
    makes that structural instead of promised. Same argument ADR 0078 makes
    for `core/hedge.py`."""

    def test_it_imports_nothing_from_backend(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts" / "measure_parlay_census.py"
        ).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines()
            if not line.strip().startswith("#")
        )
        for banned in ("import backend", "from backend"):
            assert banned not in code, (
                f"{banned!r} appears; the no-write-path guarantee becomes a "
                "promise rather than a property"
            )

    def test_it_opens_the_copy_read_only_and_not_immutable(self):
        """`immutable=1` ignores WAL state and would silently read a stale
        page set -- Amendment 1 A5 refuses it by name."""
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts" / "measure_parlay_census.py"
        ).read_text(encoding="utf-8")
        assert "?mode=ro" in source
        assert "immutable=1" not in source.replace(
            "never `immutable=1`", ""
        ).replace('"immutable=1" not in', "")
