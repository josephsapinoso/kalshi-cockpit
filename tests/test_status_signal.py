"""`/api/signal`'s payload and cache: the #227 fixes.

Three claims, each observed red under a named mutation (beside the test):

- the served payload carries `sigma_exceeds_ratchet` (B6(5) was computed and
  never served);
- a section A4 downgrade never serves `may_declare = True`, so the strip cannot
  say "this verdict is a declaring one" beside UNRESOLVED;
- past section 7's stopping rule the verdict is not recomputed.

None of this changes what `build_report` computes.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.analysis.clv_signal import build_report
from backend.api.routers import status
from backend.api.routers.status import (
    SIGNAL_CACHE_TTL_MS,
    SIGNAL_STOP_CLUSTERS,
    SIGNAL_STOP_MS,
    _cached_signal_report,
    _signal_cache,
    _signal_payload,
)
from tests.test_clv_signal import dump_rows  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def _clean_cache():
    _signal_cache.clear()
    yield
    _signal_cache.clear()


@pytest.fixture
def report(dump_rows):  # noqa: F811
    return build_report(dump_rows)


class TestThePayload:
    def test_it_serves_sigma_exceeds_ratchet(self, report):
        """Mutation: drop the key from the payload."""
        payload = _signal_payload(report, computed_ms=0)
        assert "sigma_exceeds_ratchet" in payload
        assert payload["sigma_exceeds_ratchet"] is report.sigma_exceeds_ratchet
        assert payload["sigma_exceeds_ratchet"] is not None

    def test_it_serves_null_not_false_when_nothing_measured(self, report):
        no_fit = dataclasses.replace(report, sd_clv=None)
        assert _signal_payload(no_fit, 0)["sigma_exceeds_ratchet"] is None

    def test_a_downgraded_verdict_never_serves_a_declaring_flag(self, report):
        """Mutation: revert `may_declare` to the floor comparison alone."""
        above_floor = dataclasses.replace(
            report,
            n_clusters=report.clusters_to_declare + 10,
            downgraded_by="wnba_leverage",
            section6_verdict="NO SIGNAL",
            verdict="UNRESOLVED",
        )
        payload = _signal_payload(above_floor, 0)
        assert payload["downgraded_by"] == "wnba_leverage"
        assert payload["may_declare"] is False

    def test_an_undowngraded_verdict_above_the_floor_may_declare(self, report):
        """The other direction: the guard is not 'never declare'."""
        above = dataclasses.replace(
            report, n_clusters=report.clusters_to_declare, downgraded_by=None
        )
        assert _signal_payload(above, 0)["may_declare"] is True


class TestPastTheStoppingRuleTheVerdictIsNotRecomputed:
    def _seed(self, report, computed_ms):
        _signal_cache["report"] = report
        _signal_cache["computed_ms"] = computed_ms

    @pytest.fixture
    def recompute(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            status, "report_from_connection",
            lambda conn: calls.append("inline") or None,
        )
        monkeypatch.setattr(
            status, "_maybe_start_background_signal_refresh",
            lambda *a, **k: calls.append("background"),
        )
        return calls

    def test_g_at_the_cap_freezes_even_when_the_ttl_has_lapsed(
        self, report, recompute, monkeypatch
    ):
        """Mutation: delete the `_verdict_is_frozen` early return."""
        final = dataclasses.replace(report, n_clusters=SIGNAL_STOP_CLUSTERS)
        self._seed(final, computed_ms=1)
        monkeypatch.setattr(status.db, "now_ms", lambda: 1 + 10 * SIGNAL_CACHE_TTL_MS)
        got, at = _cached_signal_report(None, None, read_budget_ms=1)
        assert got is final and at == 1
        assert recompute == []

    def test_a_report_taken_after_the_stop_date_freezes(
        self, report, recompute, monkeypatch
    ):
        self._seed(report, computed_ms=SIGNAL_STOP_MS)
        monkeypatch.setattr(
            status.db, "now_ms", lambda: SIGNAL_STOP_MS + 10 * SIGNAL_CACHE_TTL_MS
        )
        _cached_signal_report(None, None, read_budget_ms=1)
        assert recompute == []

    def test_a_report_taken_before_the_stop_date_is_refreshed_once_more(
        self, report, recompute, monkeypatch
    ):
        """Below both stops the stale-while-revalidate path is unchanged, and a
        report taken before collection ended is not final."""
        self._seed(report, computed_ms=SIGNAL_STOP_MS - 1)
        monkeypatch.setattr(
            status.db, "now_ms", lambda: SIGNAL_STOP_MS + 10 * SIGNAL_CACHE_TTL_MS
        )
        _cached_signal_report(None, None, read_budget_ms=1)
        assert recompute == ["background"]

    def test_the_payload_says_frozen(self, report):
        final = dataclasses.replace(report, n_clusters=SIGNAL_STOP_CLUSTERS)
        assert _signal_payload(final, 0)["frozen"] is True
        assert _signal_payload(report, 0)["frozen"] is False
