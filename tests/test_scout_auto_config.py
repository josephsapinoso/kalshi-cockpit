"""The unattended-scouting switch ships OFF, and its brakes have the defaults
ADR 0180 records.

What this module does NOT establish
-----------------------------------
That the watcher honours these values -- `tests/test_scout_watch.py` owns
that. This pins only the configuration contract: unset means off, and the
three brakes read from the environment under the names `.env.example`
documents, so a live toml that spells one of them wrongly falls back to a
default that is visible here rather than to a silent zero or a silent
unlimited.
"""

from __future__ import annotations

import pytest

from backend.config import ScoutAutoConfig


@pytest.fixture
def clean_env(monkeypatch):
    for key in (
        "SCOUT_AUTO_CONVENE_ENABLED",
        "SCOUT_AUTO_MAX_CONVENINGS_PER_DAY",
        "SCOUT_AUTO_RESERVE_TAP_CONVENINGS",
        "SCOUT_AUTO_REFRESH_HOURS",
    ):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


class TestTheSwitchShipsOff:
    def test_unset_means_off(self, clean_env):
        assert ScoutAutoConfig.load().enabled is False

    def test_the_word_true_turns_it_on(self, clean_env):
        clean_env.setenv("SCOUT_AUTO_CONVENE_ENABLED", "true")
        assert ScoutAutoConfig.load().enabled is True

    def test_the_word_false_is_off_even_when_set(self, clean_env):
        # `fly.live.toml` sets it to "false" explicitly rather than leaving it
        # unset; both must read as off.
        clean_env.setenv("SCOUT_AUTO_CONVENE_ENABLED", "false")
        assert ScoutAutoConfig.load().enabled is False


class TestTheBrakesHaveTheRecordedDefaults:
    def test_three_a_day_two_for_taps_six_hours(self, clean_env):
        config = ScoutAutoConfig.load()
        assert (config.max_per_day, config.reserve_taps, config.refresh_hours) == (
            3,
            2,
            6,
        )

    def test_each_brake_reads_its_own_variable(self, clean_env):
        clean_env.setenv("SCOUT_AUTO_MAX_CONVENINGS_PER_DAY", "7")
        clean_env.setenv("SCOUT_AUTO_RESERVE_TAP_CONVENINGS", "1")
        clean_env.setenv("SCOUT_AUTO_REFRESH_HOURS", "12")
        config = ScoutAutoConfig.load()
        assert (config.max_per_day, config.reserve_taps, config.refresh_hours) == (
            7,
            1,
            12,
        )


class TestLiveRunsTwoUnattendedConveningsADay:
    """#127, Joe answered (B) 2026-09-23: three convenings spent the whole
    500K token ceiling on both measured days and locked out his own taps.
    Live carries 2 explicitly; the code default stays 3 (ADR 0180)."""

    def test_the_live_toml_sets_two(self):
        import tomllib
        from pathlib import Path

        live = Path(__file__).resolve().parents[1] / "fly.live.toml"
        env = tomllib.loads(live.read_text(encoding="utf-8"))["env"]
        assert env.get("SCOUT_AUTO_MAX_CONVENINGS_PER_DAY") == "2"
