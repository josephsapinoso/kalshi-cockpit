"""Reading the dbt marts, and the distinction the whole module exists for.

`unavailable` and `empty` must never collapse into one another. A warehouse that
was never built and a warehouse with nothing to report both produce zero rows,
and rendered on a dashboard both read as "nothing to worry about" -- but only
one of them means the numbers are simply absent.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest

from backend.analysis.marts import (
    MARTS,
    WarehouseMissing,
    headline_verdicts,
    read_dashboards,
)


@pytest.fixture
def warehouse(tmp_path):
    """A warehouse holding every mart, one row each, with a verdict."""
    path = tmp_path / "warehouse.duckdb"
    conn = duckdb.connect(str(path))
    for name in MARTS:
        conn.execute(
            f"create table {name} as select 1 as n, "
            f"'verdict for {name}' as verdict"
        )
    conn.close()
    return path


class TestMissingWarehouse:
    def test_a_missing_file_raises_rather_than_returning_empty(self, tmp_path):
        with pytest.raises(WarehouseMissing) as exc:
            read_dashboards(tmp_path / "absent.duckdb")
        assert "dbt build" in str(exc.value)

    def test_the_refusal_explains_both_steps(self, tmp_path):
        """Publish then build. Missing either produces the same empty screen."""
        with pytest.raises(WarehouseMissing) as exc:
            read_dashboards(tmp_path / "absent.duckdb")
        assert "publish" in str(exc.value)
        assert "nothing to report" in str(exc.value)


class TestPanelStates:
    def test_a_populated_mart_is_ok(self, warehouse):
        panels = read_dashboards(warehouse)["panels"]
        assert panels["mart_clv_by_bucket"]["status"] == "ok"
        assert panels["mart_clv_by_bucket"]["rows"]

    def test_a_mart_that_built_and_produced_nothing_is_empty(self, tmp_path):
        path = tmp_path / "w.duckdb"
        conn = duckdb.connect(str(path))
        for name in MARTS:
            conn.execute(f"create table {name} (n integer, verdict varchar)")
        conn.close()

        panel = read_dashboards(path)["panels"]["mart_calibration"]
        assert panel["status"] == "empty"
        assert "produced no rows" in panel["note"]

    def test_a_mart_absent_from_the_warehouse_is_unavailable_not_empty(
        self, tmp_path
    ):
        """The distinction this module exists to preserve."""
        path = tmp_path / "w.duckdb"
        conn = duckdb.connect(str(path))
        conn.execute("create table mart_clv_by_bucket as select 1 as n")
        conn.close()

        panels = read_dashboards(path)["panels"]
        assert panels["mart_calibration"]["status"] == "unavailable"
        assert panels["mart_calibration"]["status"] != "empty"
        assert "not empty" in panels["mart_calibration"]["note"]

    def test_missing_required_marts_are_named(self, tmp_path):
        path = tmp_path / "w.duckdb"
        conn = duckdb.connect(str(path))
        conn.execute("create table mart_clv_by_bucket as select 1 as n")
        conn.close()

        missing = read_dashboards(path)["missing_required_marts"]
        assert "mart_multiple_comparisons" in missing
        assert "mart_suppression_audit" not in missing, "optional, not required"


class TestHeadlines:
    def test_multiple_comparisons_is_read_first(self, warehouse):
        """It qualifies everything below it. Reading a two-sigma bucket without
        the count of tests behind it is how noise became a finding once already."""
        headlines = headline_verdicts(read_dashboards(warehouse))
        assert headlines[0].startswith("mart_multiple_comparisons")

    def test_every_verdict_is_carried_through_verbatim(self, warehouse):
        headlines = headline_verdicts(read_dashboards(warehouse))
        assert len(headlines) == len(MARTS)
        for name in MARTS:
            assert any(f"verdict for {name}" in h for h in headlines)

    def test_unavailable_panels_contribute_no_headline(self, tmp_path):
        path = tmp_path / "w.duckdb"
        conn = duckdb.connect(str(path))
        conn.execute(
            "create table mart_clv_by_bucket as select 1 as n, 'only one' as verdict"
        )
        conn.close()
        assert headline_verdicts(read_dashboards(path)) == [
            "mart_clv_by_bucket: only one"
        ]


class TestTheDashboardCannotRenderAnUncensoredResult:
    """The presentation half of the noise guard, tested as a guard.

    Suppressing a conclusion does not suppress the finding if its operands are
    still on screen: `gap = actual - implied`, so a row reading
    `73.0c | 46 | 73.0% | 52.2% | (noise)` hands the reader the 20.8-point
    result by subtraction. The marts now emit pre-censored `*_display` columns;
    this asserts the page reads those and not the raw ones.

    A source check rather than a render check, deliberately -- the failure mode
    is someone reaching for the obvious column name, and that is visible in the
    source before it is visible in a screenshot.
    """

    PAGE = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "app" / "dashboards" / "page.tsx"
    )

    # Columns that are results. Rendering any of them raw re-opens the leak.
    RESULT_COLUMNS = (
        "actual_rate",
        "mean_pnl_cents",
        "beat_close_rate",
        "mean_clv_cents",
    )

    def _column_keys(self) -> set[str]:
        """The `key:` values the page actually binds to table columns."""
        source = self.PAGE.read_text(encoding="utf-8")
        return set(re.findall(r'key:\s*"([a-z_]+)"', source))

    def test_the_page_exists_where_this_test_thinks_it_does(self):
        """Otherwise every assertion below passes vacuously."""
        assert self.PAGE.exists(), self.PAGE
        assert self._column_keys(), "no column bindings found -- regex is stale"

    @pytest.mark.parametrize("column", RESULT_COLUMNS)
    def test_no_result_column_is_rendered_raw(self, column):
        assert column not in self._column_keys(), (
            f"{column} is a result. Bind {column.replace('_rate', '')}_display "
            f"or the equivalent censored column instead -- a raw value here "
            f"renders a finding in a cell the guard has already refused."
        )

    def test_the_censored_columns_are_the_ones_bound(self):
        keys = self._column_keys()
        for expected in ("actual_display", "gap_display", "beat_close_display"):
            assert expected in keys, f"{expected} is not rendered"

    def test_implied_and_n_stay_raw(self):
        """Not everything is censored, and the distinction is the point. The
        price paid and the sample size are inputs, true regardless of outcome;
        withholding them would make the table unreadable without hiding
        anything, since one operand is enough to break the subtraction."""
        keys = self._column_keys()
        assert "implied_probability" in keys
        assert "n" in keys


class TestFreshness:
    def test_the_snapshot_lag_is_stated_not_implied(self, warehouse):
        """These marts are built from Parquet, so they lag live SQLite."""
        payload = read_dashboards(warehouse)
        assert payload["warehouse_built_ms"] > 0
        assert "lag" in payload["freshness_note"]

    def test_the_connection_is_read_only(self, warehouse, monkeypatch):
        """The API process must not be able to mutate the warehouse.

        This test previously had **no assertions at all**. It called
        `read_dashboards`, then opened a *separate* connection of its own and
        created a table on it -- which proves something about the test's
        connection and nothing whatever about the one under test. It would have
        passed unchanged if `read_dashboards` opened read-write.

        Asserted on the call itself, which is where the property lives. The
        Dashboards screen is served by the same process that holds the live
        credentials, and the warehouse is the evidence record; a writable handle
        there is a path from a rendering bug to a corrupted measurement.
        """
        opened: list[dict] = []
        real_connect = duckdb.connect

        def spy(*args, **kwargs):
            opened.append(kwargs)
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(duckdb, "connect", spy)
        read_dashboards(warehouse)

        assert opened, "read_dashboards opened no connection"
        assert all(kw.get("read_only") for kw in opened), (
            "the warehouse was opened writable by the process that serves the API"
        )


class TestMartLogicIsCoveredSomewhere:
    """`pytest` does not run `warehouse/tests/*.sql`, so the headline test count
    excludes every measurement guard expressed in dbt.

    That is not a coverage hole — CI runs `dbt build`, which runs them — but it
    IS a reporting one: "834 tests passing" reads as "everything is checked",
    and the marts carry the noise guard, the calibration censoring and the
    multiple-comparisons count. This pins the arrangement so it cannot quietly
    stop being true, which is the failure a comment alone would not catch.
    """

    def test_ci_runs_dbt_build(self):
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        assert "dbt build" in workflow, (
            "CI no longer runs the mart tests, and pytest never did — the "
            "measurement guards in warehouse/tests/ are now unrun by anything"
        )

    def test_the_singular_tests_still_exist(self):
        """A dbt test deleted is a guard deleted, and `dbt build` would stay
        green with an empty tests directory."""
        tests_dir = Path(__file__).parents[1] / "warehouse" / "tests"
        names = {p.name for p in tests_dir.glob("*.sql")}
        assert len(names) >= 5, f"only {len(names)} mart tests remain: {names}"
        assert "assert_every_significance_mart_is_counted.sql" in names
