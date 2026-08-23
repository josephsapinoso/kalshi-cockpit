"""The desk window env parse: announce-and-fall-back, never crash the loop.

`ODDS_DESK_WINDOW_UTC` is a scheduling convenience loaded by the supervised
loop, so a bad value must disable the feature with an ERROR log rather than
raise -- a `ConfigError` at boot is a container crash loop recoverable only
with `flyctl`, and the disabled state is exactly the pre-desk behaviour.

What these tests do NOT establish: that the parsed window buys anything --
`tests/test_sweep_timing.py::TestTheDeskWindowKeepsTheSlatePriced` owns the
scheduling behaviour.
"""

from __future__ import annotations

import logging

from backend.config import OddsConfig, _desk_window_announced


class TestTheDeskWindowParse:
    def test_a_daytime_window_parses(self, monkeypatch):
        monkeypatch.setenv("ODDS_DESK_WINDOW_UTC", "16-20")
        assert _desk_window_announced("ODDS_DESK_WINDOW_UTC") == (16, 20)

    def test_a_midnight_crossing_window_parses(self, monkeypatch):
        monkeypatch.setenv("ODDS_DESK_WINDOW_UTC", "16-04")
        assert _desk_window_announced("ODDS_DESK_WINDOW_UTC") == (16, 4)

    def test_unset_and_empty_are_disabled_silently(self, monkeypatch, caplog):
        monkeypatch.delenv("ODDS_DESK_WINDOW_UTC", raising=False)
        with caplog.at_level(logging.ERROR):
            assert _desk_window_announced("ODDS_DESK_WINDOW_UTC") is None
        assert not caplog.records
        monkeypatch.setenv("ODDS_DESK_WINDOW_UTC", "  ")
        assert _desk_window_announced("ODDS_DESK_WINDOW_UTC") is None

    def test_garbage_disables_and_announces(self, monkeypatch, caplog):
        monkeypatch.setenv("ODDS_DESK_WINDOW_UTC", "4pm-9pm")
        with caplog.at_level(logging.ERROR):
            assert _desk_window_announced("ODDS_DESK_WINDOW_UTC") is None
        assert any("disabled" in r.getMessage() for r in caplog.records)

    def test_an_out_of_range_hour_disables_and_announces(
        self, monkeypatch, caplog
    ):
        monkeypatch.setenv("ODDS_DESK_WINDOW_UTC", "16-24")
        with caplog.at_level(logging.ERROR):
            assert _desk_window_announced("ODDS_DESK_WINDOW_UTC") is None
        assert any("disabled" in r.getMessage() for r in caplog.records)

    def test_equal_hours_are_refused_not_read_as_all_day(
        self, monkeypatch, caplog
    ):
        """An all-day desk at four sports is ~1150 credits against a 600/day
        cap; the ambiguous spelling must not be the expensive one."""
        monkeypatch.setenv("ODDS_DESK_WINDOW_UTC", "16-16")
        with caplog.at_level(logging.ERROR):
            assert _desk_window_announced("ODDS_DESK_WINDOW_UTC") is None
        assert any("disabled" in r.getMessage() for r in caplog.records)

    def test_the_credentialless_constructor_reads_it_too(self, monkeypatch):
        """The demo's window panel plans with the same schedule the runner
        spends with; a constructor that skipped the field would show a
        different timetable than the loop keeps."""
        monkeypatch.setenv("ODDS_DESK_WINDOW_UTC", "16-04")
        cfg = OddsConfig.load_without_credentials()
        assert cfg.desk_window_utc == (16, 4)

    def test_the_default_is_disabled(self, monkeypatch):
        monkeypatch.delenv("ODDS_DESK_WINDOW_UTC", raising=False)
        assert OddsConfig.load_without_credentials().desk_window_utc is None
