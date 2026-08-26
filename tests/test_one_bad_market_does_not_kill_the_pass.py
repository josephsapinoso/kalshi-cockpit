"""A single unpriceable candidate must cost one row, not the whole pass.

Written after the live incident of 2026-08-26. One team moneyline arrived with
a derived ask of 1000 tenths, `core.ev.effective_price` raised, nothing between
it and `run_pricing_pass` caught it, and the pass died. Five consecutive dead
passes raised `LoopFailed` and ended the recording process; `entrypoint.sh`
exited 0; Fly read that as an intentional stop and did not restart. The live
machine was down between page loads for hours, recording nothing.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the source defect is fixed.** That is `tests/test_store.py::
  TestDerivedAsks`. This file tests the containment, which must hold even
  when the next refusal comes from somewhere nobody has predicted.
- **That every refusal is caught.** `UNPRICEABLE_CANDIDATE` is deliberately
  narrow. A `sqlite3.Error` still ends the pass, on purpose: a defect that is
  counted and skipped is a defect nobody fixes.
"""

from __future__ import annotations

import pytest

from backend import runner


class TestARefusalIsCountedNotPropagated:
    def setup_method(self):
        runner._UNPRICEABLE_SEEN.clear()

    def test_a_refusing_candidate_returns_none_and_increments_the_counter(
        self, monkeypatch
    ):
        counts = runner.PassCounts()

        def refuse(candidate, **kwargs):
            raise ValueError("ask 1000 tenths is not a tradeable price")

        monkeypatch.setattr(runner, "build_recommendation", refuse)
        got = runner._priced_or_counted(counts, object())

        assert got is None
        assert counts.dropped_unpriceable == 1

    def test_a_good_candidate_is_passed_through_untouched(self, monkeypatch):
        counts = runner.PassCounts()
        sentinel = object()
        monkeypatch.setattr(
            runner, "build_recommendation", lambda candidate, **kw: sentinel
        )

        assert runner._priced_or_counted(counts, object()) is sentinel
        assert counts.dropped_unpriceable == 0

    def test_a_defect_still_ends_the_pass(self, monkeypatch):
        """The catch is narrow on purpose.

        A schema that changed under us raises `AttributeError`. Counting that
        as "one unpriceable row" would turn a broken instance into a record
        that quietly stops growing -- the one failure this project is least
        able to notice.
        """
        counts = runner.PassCounts()

        def broken(candidate, **kwargs):
            raise AttributeError("row has no attribute 'ask_tenths'")

        monkeypatch.setattr(runner, "build_recommendation", broken)
        with pytest.raises(AttributeError):
            runner._priced_or_counted(counts, object())
        assert counts.dropped_unpriceable == 0

    def test_the_reason_is_logged_once_not_once_per_market(
        self, monkeypatch, caplog
    ):
        """A thousand rungs of one broken ladder is one action item."""
        counts = runner.PassCounts()
        monkeypatch.setattr(
            runner,
            "build_recommendation",
            lambda candidate, **kw: (_ for _ in ()).throw(ValueError("same reason")),
        )
        with caplog.at_level("WARNING", logger="backend.runner"):
            for _ in range(50):
                runner._priced_or_counted(counts, object())

        assert counts.dropped_unpriceable == 50
        matching = [r for r in caplog.records if "same reason" in r.getMessage()]
        assert len(matching) == 1, f"logged {len(matching)} times, want 1"


class TestBothCallSitesUseTheGuard:
    """A population count, not a spot check.

    `tasks/lessons.md`, 2026-08-26: a scan-based pin silently redefines its own
    population every time the code it scans is reformatted. Asserting the COUNT
    is what turns a new, unguarded third call site into a red test rather than
    something the suite absorbs.
    """

    def _source(self) -> str:
        import inspect

        return inspect.getsource(runner)

    def test_no_call_site_calls_build_recommendation_directly(self):
        src = self._source()
        direct = src.count("= build_recommendation(")
        assert direct == 0, (
            f"{direct} call site(s) bypass `_priced_or_counted`; one refusal "
            f"there ends the whole pass"
        )

    def test_both_known_call_sites_go_through_the_guard(self):
        src = self._source()
        guarded = src.count("= _priced_or_counted(")
        assert guarded == 2, (
            f"expected 2 guarded call sites (the prop path and the team path), "
            f"found {guarded}. A new one needs its own `if ... is None: continue`."
        )

    def test_every_guarded_call_site_refuses_a_none_recommendation(self):
        """`None` must never reach `pending`."""
        src = self._source()
        assert src.count("if recommendation is None:") == 2
