"""`recommendations.fee_predicted` may not be summed or averaged.

**The hazard.** `engine.build_recommendation` computes the fee at
`sizing_contracts = max(1, sizing.contracts)`, so the persisted column means
three different things depending on the row:

    sizing.contracts == N > 0   ->  the whole order's fee
    sizing.contracts == 0       ->  one contract's fee
    suppressed after sizing     ->  the fee for the order that was then refused,
                                    because `with_added_suppression` zeroes the
                                    size without touching the fee

Observed on the seeded database: `suggested_contracts = 0` with
`fee_predicted = 0.7877`, which is neither per-contract nor payable.

**What this guard is for, and it is not the display path.** `OpportunityCard`
reads the field correctly today because it renders it inside a
`suggested_contracts > 0` block, where the meaning is unambiguous. The failure
this prevents is in *analysis*: somebody sums or averages the column across
rows to get "fees paid" or "mean fee", and lands a number that mixes units
across three populations. That is the shape of essentially every measurement
error in this repo's history, and a comment at the write site is not read at the
moment the mistake is made.

**Uninstantiated today, deliberately.** Nothing currently aggregates it, so this
file is green on arrival. That is the point: it is a tripwire for the day
someone adds the sum, not a description of a present defect. Two facts checked
at the time of writing --

* `backend/analysis/joint_bound.py:262` binds it as `stored_fee_DO_NOT_USE`, an
  earlier session defending against the same hazard by naming;
* `warehouse/models/marts/mart_fee_reconciliation.sql` does average
  `fee_predicted`, and is **exempt and correct**: it reads the *fills* parquet
  lake, where the column is an order's own predicted fee with exactly one
  meaning. It never touches `stg_recommendations`' copy.

What this establishes: that no analysis code aggregates the ambiguous column.
What it does **not** establish: that the column's three meanings are correct,
that anything renders it correctly, or that `fee_actual` is comparable to it --
that is `mart_fee_reconciliation` and `scripts/rescore_fee_models.py`.
"""

from __future__ import annotations

import re

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ANALYSIS = REPO / "backend" / "analysis"
MODELS = REPO / "warehouse" / "models"

#: The recommendations staging model. A mart that does not select from this has
#: no access to the ambiguous column and is out of scope.
RECOMMENDATIONS_SOURCE = "stg_recommendations"

#: `sum(fee_predicted)`, `avg( fee_predicted )`, `round(avg(fee_predicted), 4)`.
#: Whitespace-tolerant because SQL formatting varies and a guard defeated by a
#: newline is decoration.
_AGGREGATE = re.compile(
    r"\b(sum|avg|total|mean|median|min|max)\s*\(\s*fee_predicted\s*\)",
    re.IGNORECASE,
)

#: The naming convention an earlier session established at
#: `backend/analysis/joint_bound.py`. A read that carries this marker has
#: announced that it knows.
_MARKED_UNUSABLE = "DO_NOT_USE"

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def sql_without_comments(source: str) -> str:
    """SQL with comments removed, because a guard must read the query.

    Caught by this test's own first run: `mart_fee_reconciliation` mentions
    `stg_recommendations` exactly once, inside the comment *"See
    stg_recommendations for why `/` is wrong here."* Scanning raw text made the
    guard report the correct, exempt model as an offender -- a false positive
    that would have been "fixed" by weakening the guard or, worse, by editing
    a correct mart. **This repo's own prose is dense enough that any source
    scan must strip comments or it is reading the documentation.**
    """
    return _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", source))


def _sql_models() -> list[Path]:
    """Every dbt model, excluding `target/` -- that is compiled output, not
    source, and guarding generated files makes the suite fail on a `dbt run`."""
    return [
        p
        for p in MODELS.rglob("*.sql")
        if "target" not in p.parts
    ]


class TestNoDbtModelAggregatesTheAmbiguousColumn:
    def test_no_model_reading_recommendations_aggregates_fee_predicted(self):
        offenders = []
        for path in _sql_models():
            source = sql_without_comments(path.read_text(encoding="utf-8"))
            if RECOMMENDATIONS_SOURCE not in source:
                continue
            for match in _AGGREGATE.finditer(source):
                offenders.append(f"{path.relative_to(REPO)}: {match.group(0)}")
        assert not offenders, (
            "recommendations.fee_predicted means whole-order, per-contract, or "
            "the fee for a refused order depending on the row, so aggregating "
            "it mixes units. Compute the fee from the ask and a stated size "
            "instead. Offenders:\n  " + "\n  ".join(offenders)
        )

    def test_the_fills_mart_is_exempt_and_still_aggregates(self):
        """Pins the exemption so it is not 'fixed' by a later reader.

        `mart_fee_reconciliation` averages `fee_predicted` and is correct: its
        source is the fills lake, where the column has one meaning. If this
        model ever starts reading `stg_recommendations`, the test above catches
        it -- this one exists so the *reason* it is allowed stays written down.
        """
        mart = MODELS / "marts" / "mart_fee_reconciliation.sql"
        source = sql_without_comments(mart.read_text(encoding="utf-8"))
        assert _AGGREGATE.search(source), (
            "the fills mart no longer aggregates fee_predicted; if that is "
            "deliberate, delete this test rather than weakening it"
        )
        assert RECOMMENDATIONS_SOURCE not in source, (
            "mart_fee_reconciliation now reads stg_recommendations while still "
            "aggregating fee_predicted -- that mixes the three meanings"
        )


class TestAnalysisCodeDoesNotReadItUnmarked:
    def test_every_read_under_analysis_announces_that_it_is_unusable(self):
        """`backend/analysis/` is the registered-measurement path.

        A bare read there is one refactor away from an aggregate. The
        convention -- already used at `joint_bound.py` -- is that the binding
        name carries `DO_NOT_USE`, so the hazard is visible at the use site and
        not only at the write site.
        """
        offenders = []
        for path in ANALYSIS.rglob("*.py"):
            for n, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "fee_predicted" not in line:
                    continue
                if _MARKED_UNUSABLE in line:
                    continue
                offenders.append(f"{path.relative_to(REPO)}:{n}: {line.strip()}")
        assert not offenders, (
            "fee_predicted read under backend/analysis/ without the "
            f"{_MARKED_UNUSABLE} marker. The column means three different "
            "things depending on the row; bind it with the marker in the name "
            "or compute the fee from the ask. Offenders:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_known_marked_read_is_still_there(self):
        """If `joint_bound`'s marked read disappears, the test above collapses
        to `assert [] == []` and becomes vacuous in both directions -- the same
        defect ADR 0040 caught in the quarantine guard."""
        source = (ANALYSIS / "joint_bound.py").read_text(encoding="utf-8")
        assert "stored_fee_DO_NOT_USE" in source, (
            "the one marked read is gone, so the guard above no longer has a "
            "positive case and proves nothing"
        )
