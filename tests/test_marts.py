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
import yaml

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

    def test_a_missing_required_mart_suppresses_every_headline(self, tmp_path):
        """Not just its own headline -- all of them.

        This test used to assert the opposite. It built a warehouse holding
        only `mart_clv_by_bucket` and asserted that its per-bucket verdict
        headlined the dashboard anyway, with `mart_multiple_comparisons`
        absent from the warehouse entirely. That is a per-bucket finding
        published without the count of tests behind it, which is the one
        thing the multiple-comparisons mart exists to prevent, and the test
        enshrined it rather than catching it.
        """
        path = tmp_path / "w.duckdb"
        conn = duckdb.connect(str(path))
        conn.execute(
            "create table mart_clv_by_bucket as select 1 as n, 'only one' as verdict"
        )
        conn.close()

        dashboards = read_dashboards(path)
        assert "mart_multiple_comparisons" in dashboards["missing_required_marts"]
        assert headline_verdicts(dashboards) == []

    def test_a_missing_OPTIONAL_mart_suppresses_nothing(self, tmp_path):
        """Otherwise the guard is over-broad and the dashboard never speaks.

        Only the marts marked required in `MARTS` qualify the others. A
        warehouse missing `mart_suppression_audit` is complete for the purpose
        of reading a verdict, and suppressing on it would train the reader to
        treat an empty headline list as normal -- which is how the suppression
        above stops meaning anything.
        """
        path = tmp_path / "w.duckdb"
        conn = duckdb.connect(str(path))
        for name, required in MARTS.items():
            if not required:
                continue
            conn.execute(
                f"create table {name} as select 1 as n, "
                f"'verdict for {name}' as verdict"
            )
        conn.close()

        dashboards = read_dashboards(path)
        assert dashboards["missing_required_marts"] == []
        assert dashboards["panels"]["mart_suppression_audit"]["status"] == "unavailable"

        headlines = headline_verdicts(dashboards)
        assert headlines, "every required mart is present; there is nothing to withhold"
        assert headlines[0].startswith("mart_multiple_comparisons")
        assert not any("mart_suppression_audit" in h for h in headlines)


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


class TestSuppressionAuditHoldsTheSharedVerdictFloor:
    """The suppression audit judges rules at the same floor as every other mart.

    Until 2026-08-29 `mart_suppression_audit` pronounced its verdicts -- "may
    be too tight", "looks protective" -- from `n_rejected >= 30`, a literal,
    while its siblings held verdicts to `min_scored_recommendations` (300) via
    the dbt var. ADR 0065 §3's `n >= 30` is a *display* floor: at n = 30 the
    design resolves only a 26-63-point calibration bias (2026-08-29
    registration §6a), so a verdict there describes the analyst's patience,
    not the rule.

    Source checks, deliberately (the pattern of
    `TestTheDashboardCannotRenderAnUncensoredResult`): the demo lake has no
    scored rows, so the mart is empty in CI and a data test alone is
    vacuously green there. The failure mode is someone re-hardcoding a
    smaller floor because the panel looks empty, and that is visible in the
    source.
    """

    MART = (
        Path(__file__).resolve().parents[1]
        / "warehouse" / "models" / "marts" / "mart_suppression_audit.sql"
    )
    DBT_GUARD = (
        Path(__file__).resolve().parents[1]
        / "warehouse" / "tests"
        / "assert_suppression_audit_never_judges_below_the_floor.sql"
    )

    def test_the_verdict_floor_is_the_shared_var(self):
        source = self.MART.read_text(encoding="utf-8")
        assert re.search(
            r"n_rejected\s*<\s*\{\{\s*var\('min_scored_recommendations'\)\s*\}\}",
            source,
        ), (
            "the verdict gate no longer reads min_scored_recommendations -- "
            "this mart is back to judging rules on a sample its siblings "
            "refuse to speak about"
        )

    def test_no_numeric_literal_gates_the_verdict(self):
        """`n_rejected > 1` (the stderr guard) is fine -- that is arithmetic
        validity, not judgement. A literal *floor* is spelled `< N`."""
        source = self.MART.read_text(encoding="utf-8")
        hardcoded = re.findall(r"n_rejected\s*<=?\s*\d+", source)
        assert hardcoded == [], (
            f"a literal floor gates the verdict again: {hardcoded}"
        )

    def test_the_dbt_guard_exists_and_refuses_a_sub_floor_verdict(self):
        """`dbt build` stays green with the guard deleted, so its existence is
        pinned here alongside the predicate that makes it a guard."""
        assert self.DBT_GUARD.exists(), self.DBT_GUARD
        guard = self.DBT_GUARD.read_text(encoding="utf-8")
        assert "n_rejected < {{ var('min_scored_recommendations') }}" in guard
        assert "not like 'insufficient sample%'" in guard


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


class TestThePipAuditIgnoreListIsPinned:
    """`pip-audit` in CI is the only thing watching this repo's shipped
    dependencies, because dependabot is permanently blind to `cryptography`
    here -- the dependency graph holds no resolved version for the package
    (both SBOM entries carry an empty `versionInfo`), and an advisory cannot
    match a node with no version. A stale alert self-corrects; a package with
    no version never matches an advisory again.

    That step is green only because it names seven advisory IDs to ignore, and
    a green step whose ignore list can grow silently is not a guard at all --
    it is the "always red" failure from this file's own CI header wearing the
    opposite disguise. So the exact set is pinned here. Adding an eighth
    ignore now means editing this test, which spells out what is being
    silenced, and that makes it a deliberate act rather than the easy way out
    of a red build at an awkward hour.

    This class lives in `test_marts.py` because `test_ci_runs_dbt_build` above
    is the one existing test that reads `.github/workflows/ci.yml`, and a
    second harness for the same file would be one more thing to keep in sync.

    What this does not establish: nothing here checks that the ignored
    advisories are still the right ones to ignore, or that their stated fix
    versions are current. It pins the *set*, so a change to it has to be
    argued for. Whether an entry still deserves its place is a judgement call
    that belongs to whoever next reads the comments in `ci.yml`.
    """

    WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"

    # Every advisory outstanding against `requirements.txt`.
    #
    # **SEVEN on 2026-09-08, ONE on 2026-09-09, ZERO on 2026-09-11.** Six were
    # `cryptography`, gone because the pin went 44 -> 50 (ADR 0124). The last
    # was GHSA-rgxp-2hwp-jwgg against pyarrow, gone because the pin went
    # 19.0.1 -> `~=25.0` -- the advisory tops out at 23.0.0, so `~=23.0` would
    # have re-admitted it and `~=25.0` has nothing in the affected range.
    # Nothing was silenced in either case: `pip-audit -r requirements.txt
    # --strict` with no ignores at all now reports "No known vulnerabilities
    # found" (run locally 2026-09-11 before the bump was pushed).
    #
    # The list is meant to shrink this way -- an ignore is deleted the moment
    # its bump lands, and this test going red is how that gets noticed. It
    # went red on exactly that removal, which is the good case and is why the
    # empty set below is a deliberate edit rather than a loosened assertion.
    #
    # **An empty list is the target state, not a gap in coverage.** The three
    # tests below still hold the step to --strict, to `requirements.txt`, to
    # failing the build, and to running before the suite, so zero ignores
    # means zero outstanding advisories rather than zero enforcement.
    #
    # `ci.yml` carries the full record beside the flag: what each was, what
    # fixed it, and whether the code path was reachable here.
    EXPECTED_IGNORES: set[str] = set()

    def _audit_step(self):
        workflow = yaml.safe_load(self.WORKFLOW.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["test"]["steps"]
        matches = [
            s for s in steps if "pip-audit" in (s.get("name") or "")
        ]
        assert len(matches) == 1, (
            "expected exactly one pip-audit step in the test job, found "
            f"{len(matches)} -- the dependency gate has been moved, renamed "
            "or duplicated"
        )
        return steps, matches[0]

    def test_the_ignore_list_is_exactly_what_is_recorded(self):
        _, step = self._audit_step()
        found = set(re.findall(r"--ignore-vuln\s+([A-Za-z0-9-]+)", step["run"]))
        assert found == self.EXPECTED_IGNORES, (
            "the pip-audit ignore list changed.\n"
            f"  added:   {sorted(found - self.EXPECTED_IGNORES)}\n"
            f"  removed: {sorted(self.EXPECTED_IGNORES - found)}\n"
            "An addition silences a real advisory on a dependency that ships "
            "to an instance holding real money: record it in ci.yml beside "
            "the flag, with what it is, what fixes it and why it is deferred, "
            "then add it here. A removal should mean the bump landed -- which "
            "is the good case, and still deliberate."
        )

    def test_the_audit_step_cannot_be_made_non_blocking(self):
        """A guard that cannot fail is not a guard. The ignore list is a
        record of named exceptions; `continue-on-error` would be a blanket
        one, and would turn the whole step into decoration."""
        _, step = self._audit_step()
        assert "continue-on-error" not in step, (
            "the pip-audit step no longer fails the build"
        )
        assert "|| true" not in step["run"]
        assert "--strict" in step["run"], (
            "--strict is what makes an unresolvable dependency red rather "
            "than silently skipped -- which is the exact blindness "
            "dependabot is stuck in for cryptography on this repo"
        )

    def test_it_audits_the_file_that_actually_ships(self):
        """`requirements.txt` is the ship/no-ship boundary: the Dockerfile
        installs it alone, so it is the only file whose contents reach the
        live instance. Auditing `requirements-dev.txt` instead would drag in
        every shipping finding anyway (it opens with `-r requirements.txt`)
        with nothing marking which rows are exposure."""
        _, step = self._audit_step()
        assert "-r requirements.txt" in step["run"]
        dockerfile = (
            Path(__file__).parents[1] / "Dockerfile"
        ).read_text(encoding="utf-8")
        assert "pip install --no-cache-dir -r requirements.txt" in dockerfile, (
            "the Dockerfile no longer installs requirements.txt alone, so "
            "that file may no longer be the ship/no-ship boundary this step "
            "assumes"
        )

    def test_the_audit_runs_before_the_suite(self):
        """Cheap and early, so a vulnerable dependency fails in about a minute
        rather than after the 15-minute cap."""
        steps, step = self._audit_step()
        names = [s.get("name") or s.get("uses") or "" for s in steps]
        assert names.index(step["name"]) < names.index("Tests")
