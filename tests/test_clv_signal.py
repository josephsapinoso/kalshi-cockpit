"""`backend/analysis/clv_signal.py`: the registered test, moved but not changed.

**These tests exist because a move is the most dangerous kind of refactor here.**
`beta` is the project's registered decision-bearing statistic. Until ADR 0039 it
was produced only by a human running `scripts/run_signal_test.py` against a dump
on a laptop, and nothing in the suite would have noticed if the number drifted --
no test read it, and the published values lived in a docstring and a measurement
write-up, neither of which is executed. `ev.py` had been wrong for three days for
exactly that reason.

So the load-bearing assertion in this file is a **reproduction**: the committed
2026-08-16 dump, through this code, must give back both rows of the published
sensitivity table in
`docs/measurements/2026-08-16-clv-signal-test-interim-look.md` --
the registered primary (§P4's modal version 3 alone) at `beta_hat = -0.0528`,
`se_cluster = 0.0287`, `G = 86`, and the pooled fit at `-0.1412` / `0.0478` /
`G = 199`. If this file goes red, the statistic moved -- not the plumbing.

**Which of those two is `report.fit` changed on 2026-08-25, and the reason is
the point of the change.** It was the pooled one, because `build_report` pooled
every `strategy_config_version` unless a caller opted out and no caller did --
so on 2026-08-24 `GET /api/signal` declared `NO SIGNAL` at `G = 311` when §P4
and §7 make the registered primary `UNRESOLVED` at `G = 216`. `fit` is now the
primary; the pooled fit is carried as `pooled_fit` and never gets a verdict.
`docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md`.

Every claim below was observed red under a named mutation, written beside the
test. A guard that has never been seen to fail is decoration.

WHERE THE DATA COMES FROM
-------------------------
Two sources, deliberately different in kind:

- **The committed dump** `docs/measurements/2026-08-16-clv-signal-pull.json.gz`,
  for the reproduction. It is the real record: 3,692 rows, 199 clusters, taken
  off the live box. No synthetic population can pin a published number.
- **`backend/store/schema.sql` against a `tmp_path` file**, for the SQL. Not one
  `CREATE TABLE` is written here, because the failure being guarded against is a
  query naming a column the live database does not have, and a hand-written
  schema that agreed with the query would hide exactly that.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the live database's current contents.** The reproduction pins
  a 2026-08-16 snapshot. `G` on the box today is larger and unknown here.
- **Nothing about the registration being correct.** They pin that this code
  implements it. A disagreement between the two is settled by
  `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`, not here.
- **Nothing about the verdict at `G >= 300`.** No test in this file has ever
  seen a declaring branch fire on real data, because the record has never
  reached the floor.
- **Nothing about the frontend.** `TestTheRouteCannotPublishTheEffectAlone`
  pins what `GET /api/signal` can physically hand a renderer; whether a screen
  then reads it honestly is `frontend/`'s question and its own tests'.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

import pytest

from backend.api.routes import _signal_payload
from backend.analysis.clv_signal import (
    SQL_CLV_SIGNAL_PULL,
    a82_counts,
    build_report,
    observations,
    pull_rows,
    quote_disagrees,
    report_from_connection,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DUMP = REPO_ROOT / "docs" / "measurements" / "2026-08-16-clv-signal-pull.json.gz"
SCHEMA = REPO_ROOT / "backend" / "store" / "schema.sql"


def _dump_rows() -> list[dict]:
    with gzip.open(DUMP, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["query"] == "clv-signal-pull"
    rows: list[dict] = []
    for section in payload["sections"]:
        assert not section.get("truncated"), "a prefix of the record is not a sample"
        columns = section["columns"]
        rows.extend(dict(zip(columns, row)) for row in section["rows"])
    return rows


@pytest.fixture(scope="module")
def dump_rows() -> list[dict]:
    return _dump_rows()


class TestTheRegisteredNumberIsReproduced:
    """Both published `beta`s come back out of the code, to four places.

    **This class was re-anchored 2026-08-25 and the claim is unchanged.** It used
    to read the `-0.1412 / G = 199` figures off `report.fit`, because
    `build_report` then pooled every `strategy_config_version` unless a caller
    passed `modal_config_only=True` -- which no caller did. §P4 and §7 make the
    modal version the *primary* whenever more than one is present, so `fit` is
    now the modal-only fit and the pooled one is carried as `pooled_fit`. See
    `docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md` D1.

    **Nothing published became unreproducible**, which is why the re-anchor was
    allowed. `docs/measurements/2026-08-16-clv-signal-test-interim-look.md`
    prints a two-row sensitivity table and this class now pins *both* rows:

        | population        | rows  | G   | beta_hat | interval          |
        | all versions      | 3,692 | 199 | -0.141   | [-0.334, +0.052]  |
        | modal version (3) | 1,672 |  86 | -0.053   | [-0.205, +0.099]  |

    Mutation observed red: drop the `half_spread_tenths` term from
    `signal_test.fit`'s design matrix -- both fits move and every assertion
    below fails.
    """

    # -- the registered primary: §P4's modal version only ------------------

    def test_the_primary_is_the_modal_config_version_alone(self, dump_rows):
        """§P4/§7. Mutation observed red: change `len(versions) > 1` to
        `False` in `build_report` -- the primary becomes the pooled 199."""
        report = build_report(dump_rows)
        assert report.modal_config_applied
        assert report.modal_config_version == 3
        assert report.n_non_modal_dropped == 2020
        assert report.strategy_config_versions == {1: 359, 2: 56, 3: 1672, 4: 1605}

    def test_the_primary_beta_hat_is_minus_zero_point_zero_five_two_eight(
        self, dump_rows
    ):
        report = build_report(dump_rows)
        assert report.fit is not None, report.refusal
        assert round(report.fit.beta_hat, 4) == -0.0528
        assert round(report.fit.se_cluster, 4) == 0.0287

    def test_the_primary_g_is_eighty_six(self, dump_rows):
        """`G` counts only the modal version's games -- §7 in those words."""
        report = build_report(dump_rows)
        assert report.n_clusters == 86
        assert report.fit.n_clusters == 86
        assert report.n_analysed == 1672
        assert report.unclustered == 0

    def test_the_primary_interval_is_the_published_sensitivity_row(self, dump_rows):
        report = build_report(dump_rows)
        assert round(report.fit.lower, 4) == -0.2047
        assert round(report.fit.upper, 4) == 0.0992

    # -- the pooled fit: §P4's "reported separately" ------------------------

    def test_the_pooled_fit_still_reproduces_the_published_headline(self, dump_rows):
        """The interim look's headline row, preserved.

        A repo that can no longer reproduce a number in its own measurement
        record has made that record unverifiable, so §P4's "the others are
        reported separately" is implemented as a carried fit rather than a
        discarded one.

        Mutation observed red: set `pooled = None` unconditionally in
        `build_report`.
        """
        report = build_report(dump_rows)
        assert report.pooled_fit is not None
        assert round(report.pooled_fit.beta_hat, 4) == -0.1412
        assert round(report.pooled_fit.se_cluster, 4) == 0.0478
        assert report.pooled_fit.n_clusters == 199
        assert report.pooled_fit.n_rows == 3692
        assert round(report.pooled_fit.lower, 4) == -0.3342
        assert round(report.pooled_fit.upper, 4) == 0.0517

    def test_the_pooled_fit_never_carries_a_verdict(self, dump_rows):
        """The 2026-08-24 defect, stated as an invariant.

        `G = 199` pooled against `G = 86` primary is the same shape as the live
        record's `311` against `216`: the pooled number is the one that reaches
        the floor first, and it is not the one the registration declares on.
        There is no code path from `pooled_fit` to a verdict, and this asserts
        the verdict follows the primary even though pooled `G` is larger.
        """
        report = build_report(dump_rows)
        assert report.pooled_fit.n_clusters > report.fit.n_clusters
        assert report.verdict == "UNRESOLVED"
        assert not hasattr(report.pooled_fit, "verdict")

    def test_a_single_version_record_has_no_separate_pooled_fit(self, dump_rows):
        """Nothing to report separately, so nothing is reported.

        `pooled_fit` is not "the fit again"; it exists only to name the
        population §P4 excluded. With one version there is no such population.
        """
        one = [dict(r, strategy_config_version=3) for r in dump_rows]
        report = build_report(one)
        assert not report.modal_config_applied
        assert report.modal_config_version is None
        assert report.n_non_modal_dropped == 0
        assert report.pooled_fit is None
        assert report.n_clusters == 199

    def test_p1_is_satisfied_on_the_registered_statistic(self, dump_rows):
        """§A8.2's `matched / total`, not the superseded non-NULL coverage."""
        report = build_report(dump_rows)
        assert report.p1 == 1.0
        assert report.p1_passed
        assert report.quote_mismatch == 0, (
            "the side-dependent comparison reported 1,826 here when it was "
            "written YES-side-only; see 2026-08-16-quote-join-bias-result.md"
        )

    def test_the_arms_are_reported_beside_the_primary_figure(self, dump_rows):
        """The repo rule: a pooled number is not a finding until the parts agree.

        **Config version 3 is entirely moneyline**, so the registered primary on
        this dump has one arm and the prop arm's `-0.5192` belongs to the
        excluded versions. That is worth pinning rather than smoothing over: it
        says the two published rows of the sensitivity table are not the same
        measurement on more or less data, they are different populations.

        Mutation observed red: return `()` from `build_report`'s group loop.
        """
        report = build_report(dump_rows)
        arms = {g.name: g for g in report.by_market_type}
        assert set(arms) == {"moneyline"}
        assert round(arms["moneyline"].beta_hat, 4) == -0.0528
        assert arms["moneyline"].n_rows == 1672
        assert round(arms["moneyline"].share, 3) == 1.0


class TestTheVerdictCannotDeclareBelowTheFloor:
    """`UNRESOLVED` is a real answer and may not be rendered as "no signal"."""

    def test_the_record_reads_unresolved(self, dump_rows):
        assert build_report(dump_rows).verdict == "UNRESOLVED"

    def test_the_report_says_how_many_clusters_remain(self, dump_rows):
        """A screen has to be able to show `86 / 300` without doing arithmetic.

        **The counter is the primary's, not the record's, since 2026-08-25.**
        It read `199 / 300` while `fit` was the pooled fit; §P4 makes the modal
        version the primary, so `G` is 86 and 214 clusters remain. A screen
        counting down to a floor must count the population the floor governs --
        counting the pooled record reaches 300 first and would invite exactly
        the declaration this change refuses.

        Mutation observed red: return `self.clusters_to_declare` from
        `clusters_remaining`.
        """
        report = build_report(dump_rows)
        assert report.clusters_to_declare == 300
        assert report.clusters_remaining == 214

    def test_the_smallest_resolvable_beta_exceeds_the_estimate(self, dump_rows):
        """Printed before `beta_hat` because reading the effect first is how a
        small cell gets believed. At this `G` the test cannot resolve what it
        measured, which is the whole content of UNRESOLVED."""
        report = build_report(dump_rows)
        assert round(report.smallest_resolvable_beta, 4) == 0.1519
        assert report.smallest_resolvable_beta > abs(report.fit.beta_hat)


class TestARefusalIsNotASmallNumber:
    """The demo instance is the failure mode this class exists for.

    Its seeded history carries no `event_ticker` and no `kalshi_quotes`, so every
    row joins to a NULL half-spread. A caller that read `n_clusters` off that
    would render `G = 420` on the public screen -- a bigger number than the live
    record's 199, from a database with no signal in it at all.
    """

    def test_a_population_with_no_half_spread_refuses(self, dump_rows):
        stripped = [dict(r, half_spread_tenths=None) for r in dump_rows]
        report = build_report(stripped)
        assert report.fit is None
        assert report.verdict == "REFUSED"
        assert not report.p1_passed
        assert "P1 FAILED" in report.refusal

    def test_a_refusal_does_not_borrow_the_unresolved_verdict(self, dump_rows):
        """UNRESOLVED means a look happened and could not resolve. REFUSED means
        no look happened. Collapsing them reports a look that did not occur.

        Mutation observed red: set `verdict="UNRESOLVED"` in `refused()`.
        """
        report = build_report([dict(r, half_spread_tenths=None) for r in dump_rows])
        assert report.verdict != "UNRESOLVED"

    def test_an_empty_population_refuses_rather_than_returning_zero(self):
        report = build_report([])
        assert report.fit is None
        assert report.verdict == "REFUSED"
        assert report.n_analysed == 0

    def test_a_refused_report_still_carries_its_population_counts(self, dump_rows):
        """The panel has to be able to say *why*, and a bare exception loses it.

        `n_raw` is the dump, `n_analysed` is the §P4 primary. The two differ by
        the non-modal rows and both are carried, so a panel can say "1,672 of
        3,692 rows, version 3 only" rather than either number alone.
        """
        report = build_report([dict(r, half_spread_tenths=None) for r in dump_rows])
        assert report.n_raw == 3692
        assert report.n_analysed == 1672
        assert report.n_non_modal_dropped == 2020
        assert report.no_quote == 1672
        assert report.matched == 0


class TestTheExtractionIsTheRegisteredOne:
    """The SQL runs against the real schema, and the operator's copy matches."""

    def test_the_sql_is_byte_identical_to_the_operator_script(self):
        """Two copies of one definition, held together by this assertion.

        `scripts/inspect_live_db.py` cannot import this module: it runs as
        `python /app/scripts/...`, which puts `/app/scripts` on `sys.path` and
        not `/app`, so the import would pass here and fail on the money box
        (`inspect_live_db.py:350-358`). This is the same arrangement that file
        already uses for `_ACTIONABLE_PREDICATE`.

        Mutation observed red: change one space in either string.
        """
        source = (REPO_ROOT / "scripts" / "inspect_live_db.py").read_text(
            encoding="utf-8"
        )
        namespace: dict = {}
        start = source.index("_SQL_CLV_SIGNAL_PULL = (")
        end = source.index("\n)\n", start) + 3
        exec(source[start:end], namespace)  # noqa: S102 - a literal, not input
        assert namespace["_SQL_CLV_SIGNAL_PULL"] == SQL_CLV_SIGNAL_PULL

    def test_the_query_is_well_formed_against_the_shipped_schema(self, tmp_path):
        """Executed against `schema.sql`, never a hand-written table.

        Mutation observed red: rename `clv_horizon_hours` in the SQL -- sqlite
        raises `no such column` here rather than on the live box at 3am.
        """
        db = tmp_path / "cockpit.db"
        conn = sqlite3.connect(db)
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        assert pull_rows(conn) == []
        report = report_from_connection(conn)
        assert report.verdict == "REFUSED"
        conn.close()


class TestTheA82CountsAreThreeNotTwo:
    """"No quote at all" and "a quote that disagrees" are different failures."""

    def _row(self, **kw):
        base = dict(
            cluster_key="KXEVENT-1",
            edge_tenths=12.0,
            clv_tenths=7.0,
            side="yes",
            entry_ask_tenths=400,
            yes_bid_tenths=390,
            no_bid_tenths=600,
            half_spread_tenths=5.0,
        )
        base.update(kw)
        return base

    def test_a_matching_yes_row_is_matched(self):
        assert a82_counts([self._row()]) == {
            "matched": 1,
            "quote_mismatch": 0,
            "no_quote": 0,
        }

    def test_a_no_row_is_compared_against_the_no_side_ask(self):
        """The bug this pins reported every NO row as a mismatch by construction.

        Mutation observed red: drop the `side` branch in `quote_disagrees` and
        always read `no_bid_tenths` -- this row flips to `quote_mismatch`.
        """
        row = self._row(side="no", entry_ask_tenths=1000 - 390)
        assert not quote_disagrees(row)
        assert a82_counts([row])["matched"] == 1

    def test_a_missing_half_spread_is_no_quote_and_never_a_mismatch(self):
        counts = a82_counts([self._row(half_spread_tenths=None)])
        assert counts == {"matched": 0, "quote_mismatch": 0, "no_quote": 1}

    def test_a_disagreeing_quote_is_retained_not_dropped(self):
        """Excluding these would make the exclusion rate track book activity."""
        rows = [self._row(entry_ask_tenths=333)]
        counts = a82_counts(rows)
        assert counts["quote_mismatch"] == 1
        assert len(observations(rows)) == 1, "retained, not dropped"


class TestTheRouteCannotPublishTheEffectAlone:
    """`GET /api/signal`'s payload shape, and what it does on the demo instance.

    The shape assertions are about what a *renderer* can physically do. A screen
    that shows `beta_hat` with no `se_cluster` beside it is the one-number habit
    the always-valid multiplier exists to defeat, and asking the frontend to
    remember is how the frontend ended up a version behind on every correction.
    """

    def test_a_refused_report_carries_no_estimate_key_to_render(self, dump_rows):
        """Mutation observed red: emit `beta_hat` at the top level of the
        payload -- a refused run then has a number a screen could read."""
        report = build_report([dict(r, half_spread_tenths=None) for r in dump_rows])
        payload = _signal_payload(report, computed_ms=1_700_000_000_000)
        assert payload["available"] is False
        assert payload["estimate"] is None
        assert "beta_hat" not in payload
        assert payload["refusal"]

    def test_the_estimate_block_is_all_or_nothing(self, dump_rows):
        payload = _signal_payload(build_report(dump_rows), computed_ms=0)
        estimate = payload["estimate"]
        for key in (
            "beta_hat",
            "se_cluster",
            "n_clusters",
            "interval_lower",
            "interval_upper",
            "smallest_resolvable_beta",
        ):
            assert estimate[key] is not None, key
        assert round(estimate["beta_hat"], 4) == -0.0528

    def test_the_payload_says_a_declaring_look_is_not_permitted(self, dump_rows):
        payload = _signal_payload(build_report(dump_rows), computed_ms=0)
        assert payload["verdict"] == "UNRESOLVED"
        assert payload["may_declare"] is False
        assert payload["population"]["clusters_remaining"] == 214

    def test_the_payload_names_the_population_the_verdict_is_on(self, dump_rows):
        """A reader who sees `clusters` without §P4's flag cannot tell which
        population produced the verdict -- which is how 2026-08-24's screen
        declared NO SIGNAL at `G = 311` while the registered primary was
        UNRESOLVED at `G = 216`.

        Mutation observed red: drop `modal_config_applied` from
        `_signal_payload`'s population block.
        """
        payload = _signal_payload(build_report(dump_rows), computed_ms=0)
        pop = payload["population"]
        assert pop["modal_config_applied"] is True
        assert pop["modal_config_version"] == 3
        assert pop["non_modal_rows_excluded"] == 2020
        assert pop["clusters"] == 86
        assert pop["strategy_config_versions"] == {
            "1": 359, "2": 56, "3": 1672, "4": 1605
        }

    def test_the_payload_carries_no_second_beta_a_screen_could_declare_on(
        self, dump_rows
    ):
        """`pooled_fit` is a record-keeping field, not a wire field.

        The pooled slope reaches `G = 300` before the primary does, so putting
        it on the payload beside the primary hands a renderer two `beta`s and
        one verdict -- and the 2026-08-24 incident is what picking the wrong one
        looks like. The harness prints it; the API does not ship it.
        """
        payload = _signal_payload(build_report(dump_rows), computed_ms=0)
        flat = json.dumps(payload)
        assert "pooled" not in flat
        assert "-0.1412" not in flat
        assert round(payload["estimate"]["beta_hat"], 4) == -0.0528

    def test_the_payload_dates_itself(self, dump_rows):
        """A cached statistic that presents itself as current is a method that
        lies. `computed_ms` is what lets the screen render the age."""
        payload = _signal_payload(build_report(dump_rows), computed_ms=1234)
        assert payload["computed_ms"] == 1234
        assert payload["cache_ttl_ms"] > 0

    def test_the_arms_ship_beside_the_primary_figure(self, dump_rows):
        """The repo rule, enforced in the wire format rather than in a habit.

        One arm on this dump, because §P4's modal version (3) is entirely
        moneyline. The prop arm's `-0.5192` lives in the excluded versions --
        see `TestTheRegisteredNumberIsReproduced`.
        """
        payload = _signal_payload(build_report(dump_rows), computed_ms=0)
        arms = {a["name"]: a for a in payload["by_market_type"]}
        assert set(arms) == {"moneyline"}
        assert round(arms["moneyline"]["beta_hat"], 4) == -0.0528

    def test_the_demo_instance_refuses_rather_than_publishing_g_of_420(
        self, tmp_path
    ):
        """The public screen, on the real seeded demo database.

        `seed_history` writes 420 scored recommendations whose `kalshi_markets`
        rows have no `event_ticker` and for which no `kalshi_quotes` exist. A
        caller that read `n_clusters` off that would put `G = 420` on the
        instance strangers look at -- a bigger number than the live record's
        199, from a database with no signal in it.

        Mutation observed red: return `verdict="UNRESOLVED"` from
        `build_report`'s `refused()`.
        """
        from backend.api.routes import _signal_cache, create_app
        from backend.config import AppConfig
        from backend.seed_demo import seed_all
        from fastapi.testclient import TestClient

        _signal_cache.clear()
        path = tmp_path / "demo.db"
        seed_all(path)
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        with TestClient(app) as client:
            body = client.get("/api/signal").json()

        assert body["available"] is False
        assert body["estimate"] is None
        assert body["verdict"] == "REFUSED"
        assert body["verdict"] != "UNRESOLVED", (
            "REFUSED means no look happened; UNRESOLVED means one happened and "
            "could not resolve. Collapsing them reports a look that did not run"
        )
        assert "P1" in body["refusal"]
        _signal_cache.clear()

    def test_the_route_is_reachable_without_a_bearer_token(self, tmp_path):
        """Same grounds as `/api/gate`: a bearer token is not openable in a
        phone browser, and `require_auth` 403s on the demo instance."""
        from backend.api.routes import _signal_cache, create_app
        from backend.config import AppConfig
        from backend.seed_demo import seed_all
        from fastapi.testclient import TestClient

        _signal_cache.clear()
        path = tmp_path / "live.db"
        seed_all(path)
        app = create_app(
            AppConfig(instance_mode="live", auth_token="secret-token", db_path=path)
        )
        with TestClient(app) as client:
            assert client.get("/api/signal").status_code == 200
        _signal_cache.clear()


class TestTheDisclosureFiresOnItsOwn:
    """§A8.2's sentence is emitted by the code, not remembered by an author."""

    def test_above_five_percent_mismatch_the_report_demands_the_disclosure(self):
        rows = [
            dict(
                cluster_key=f"E{i // 4}",
                edge_tenths=float(i % 17),
                clv_tenths=float(i % 11),
                half_spread_tenths=float(i % 3),
                side="yes",
                entry_ask_tenths=333 if i % 10 == 0 else 400,
                yes_bid_tenths=390,
                no_bid_tenths=600,
                market_type="moneyline",
                strategy_config_version=4,
                unclustered=0,
            )
            for i in range(200)
        ]
        report = build_report(rows)
        assert report.quote_mismatch == 20
        assert report.disclosure_required

    def test_a_clean_record_does_not_demand_it(self, dump_rows):
        assert not build_report(dump_rows).disclosure_required
