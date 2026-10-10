"""The desk-built parlay pushes have an off switch, and live has it off.

Joe's (A) to #350 (2026-10-10): stop the pushes, keep the ladder view. The
ground is ADR 0071 §2.1 -- the desk does not manufacture action -- and the
2026-10-09 professional-bettor review, which read a pushed desk-built parlay
as exactly that.

What this file establishes: with `parlay_pushes_enabled=False` an `Alerter`
whose notifier IS configured (a) answers `parlay_cards_could_send` with
`False`, which is the gate the runner reads BEFORE building the ladder, so
the 200,000-sample copula is skipped too, and (b) sends nothing from
`parlay_cards` even when handed a built ladder; that `PARLAY_PUSHES_ENABLED`
is the one env read behind it, defaulting on; and that `fly.live.toml` pins
the three values Joe chose on 2026-10-10 (pushes off, automatic cards off,
the 2.5M token ceiling).

What it does not establish: anything about the other channels (failures,
digest, hedge), which the switch must not touch -- `tests/test_alerts.py`
covers those; or that the runner wires the flag through (that is a one-line
constructor argument in `scripts/run_loop.py`, pinned by source text below
because the loop is not driven end to end by any test).
"""

from __future__ import annotations

import sqlite3
import tomllib
from pathlib import Path

import pytest

from backend.config import configured_parlay_pushes_enabled
from backend.notify.alerts import Alerter
from backend.store import db

ROOT = Path(__file__).resolve().parents[1]


class _ConfiguredNotifier:
    """A notifier that claims to be configured and records what it was asked
    to send. If the switch leaks, `sent` fills."""

    enabled = True

    def __init__(self) -> None:
        self.sent: list = []

    async def parlay_card(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return True


def _conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "parlay_switch.db")


class TestTheSwitchStopsBothTheBuildGateAndTheSend:
    def test_off_the_runner_side_gate_says_no_before_any_ladder_is_built(self, tmp_path):
        alerter = Alerter(_conn(tmp_path), _ConfiguredNotifier(), parlay_pushes_enabled=False)
        assert alerter.enabled, "the notifier is configured; only the parlay switch is off"
        assert alerter.parlay_cards_could_send(
            now_ms=1_800_000_000_000, day_start_ms=1_799_990_000_000, card_hour_utc=0
        ) is False

    def test_on_the_same_alerter_could_send(self, tmp_path):
        alerter = Alerter(_conn(tmp_path), _ConfiguredNotifier(), parlay_pushes_enabled=True)
        assert alerter.parlay_cards_could_send(
            now_ms=1_800_000_000_000, day_start_ms=1_799_990_000_000, card_hour_utc=0
        ) is True

    async def test_off_a_ladder_that_would_have_sent_sends_nothing_and_claims_nothing(self, tmp_path):
        """Positive control first: the same ladder, settled through the same
        helper the sibling suite uses, IS sent with the switch on. Only then
        does "nothing with it off" mean anything -- without the control this
        test stayed green under mutation (2026-10-10), because a ladder that
        cannot send for another reason cannot tell the switch from the
        debounce."""
        from tests.test_parlay_cards_reach_the_phone import FakeNotifier, _card, _ladder, _settle

        on = FakeNotifier()
        sent = await _settle(Alerter(_conn(tmp_path), on, parlay_pushes_enabled=True), _ladder(_card()))
        assert sent.sent == ("safe",) and len(on.posted) == 1, "control: the switch on, the card goes"

        conn = db.init_db(tmp_path / "parlay_switch_off.db")
        off = FakeNotifier()
        result = await _settle(Alerter(conn, off, parlay_pushes_enabled=False), _ladder(_card()))
        assert tuple(result.sent) == ()
        assert off.posted == []
        n = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        assert n == 0, "an off switch must not even claim a notification row"

    def test_the_default_is_on_so_a_fresh_copy_behaves_as_the_record_describes(self, tmp_path):
        assert Alerter(_conn(tmp_path), _ConfiguredNotifier()).parlay_pushes_enabled is True


class TestTheOneEnvRead:
    def test_defaults_on(self, monkeypatch):
        monkeypatch.delenv("PARLAY_PUSHES_ENABLED", raising=False)
        assert configured_parlay_pushes_enabled() is True

    @pytest.mark.parametrize("raw", ["false", "0", "off", "no"])
    def test_reads_off(self, monkeypatch, raw):
        monkeypatch.setenv("PARLAY_PUSHES_ENABLED", raw)
        assert configured_parlay_pushes_enabled() is False

    def test_the_loop_hands_the_flag_to_the_alerter_it_builds(self):
        text = (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        assert "configured_parlay_pushes_enabled" in text
        assert "Alerter(conn, discord, parlay_pushes_enabled=parlay_pushes_enabled)" in text


class TestLivePinsWhatJoeChoseOn20261010:
    """The deploy file is where the owner's choice lives (fly.live.toml's own
    rule). Three values moved together on 2026-10-10: #349 (A), #350 (A)."""

    @pytest.fixture(scope="class")
    def live_env(self) -> dict:
        with (ROOT / "fly.live.toml").open("rb") as handle:
            return tomllib.load(handle)["env"]

    def test_parlay_pushes_are_off(self, live_env):
        assert live_env["PARLAY_PUSHES_ENABLED"] == "false"

    def test_automatic_game_script_cards_are_off(self, live_env):
        assert live_env["GAME_SCRIPT_AUTO_ENABLED"] == "false"

    def test_the_token_ceiling_is_two_and_a_half_million(self, live_env):
        assert live_env["AGENT_MAX_TOKENS_PER_DAY"] == "2500000"

    def test_the_contract_names_the_switch(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        assert "PARLAY_PUSHES_ENABLED=true" in text
