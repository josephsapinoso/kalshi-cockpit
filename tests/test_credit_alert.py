"""#368: the first credit failure of a budget day pushes ONE phone alert, and
the screen that refused the tap says the AI account is out of credit.

Drives the verbatim credit-error fixture (#365) through the real call and
settle paths (`give_leg_verdict`, `convene_desk`) with a fake notifier, and
reads the `notifications` ledger.

Does NOT establish: that Discord delivers it, or that the live process has a
Discord config (the helper builds one from the environment, as the runner's
alerter does).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.agents.game_script import call_failed_reason
from backend.api.routers.game import no_card_line
from backend.api.routers.scout import _screen_refusal
from backend.leg_verdicts import _row_to_response
from backend.notify import credit_alert
from tests.test_api_error_is_not_filed_nothing import _Raises, credit_error
from tests.test_leg_verdict_seat import NOW, _budget, _give
from tests.test_scout_desk import _budget as desk_budget, _convene


class FakeNotifier:
    enabled = True

    def __init__(self):
        self.sent = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def ai_credit_exhausted(self):
        self.sent += 1
        return True


@pytest.fixture
def notifier(monkeypatch):
    fake = FakeNotifier()
    monkeypatch.setattr(credit_alert, "make_notifier", lambda: fake)
    return fake


def _rows(conn):
    return conn.execute(
        "SELECT kind, key, detail FROM notifications WHERE kind = ?",
        (credit_alert.AI_CREDIT_KIND,),
    ).fetchall()


class TestOnePushPerBudgetDay:
    async def test_a_credit_error_queues_exactly_one_row(self, tmp_path, notifier):
        """Positive control."""
        conn, budget = _budget(tmp_path)
        await _give(SimpleNamespace(messages=_Raises(credit_error())), budget)
        rows = _rows(conn)
        assert len(rows) == 1
        assert rows[0]["key"] == str(budget.day_start_ms(NOW))
        assert notifier.sent == 1

    async def test_a_second_credit_failure_the_same_day_queues_none(
        self, tmp_path, notifier
    ):
        conn, budget = _budget(tmp_path)
        client = SimpleNamespace(messages=_Raises(credit_error()))
        await _give(client, budget)
        await _give(client, budget)
        assert len(_rows(conn)) == 1
        assert notifier.sent == 1

    async def test_the_next_budget_day_may_push_again(self, tmp_path, notifier):
        conn, budget = _budget(tmp_path)
        client = SimpleNamespace(messages=_Raises(credit_error()))
        await _give(client, budget)
        await credit_alert.push_if_credit_failed(
            budget, credit_alert.CREDIT_VERDICT, NOW + 25 * 3_600_000
        )
        assert len(_rows(conn)) == 2

    async def test_a_non_credit_api_error_queues_none(self, tmp_path, notifier):
        conn, budget = _budget(tmp_path)
        await _give(SimpleNamespace(messages=_Raises(RuntimeError("reset"))), budget)
        assert _rows(conn) == []
        assert notifier.sent == 0

    async def test_the_scout_desk_pushes_once_for_its_three_failed_calls(
        self, tmp_path, notifier
    ):
        conn, budget = desk_budget(tmp_path)
        await _convene(SimpleNamespace(messages=_Raises(credit_error())), budget)
        assert len(_rows(conn)) == 1
        assert notifier.sent == 1

    async def test_the_row_carries_no_secret_or_envelope(self, tmp_path, notifier):
        conn, budget = _budget(tmp_path)
        await _give(SimpleNamespace(messages=_Raises(credit_error())), budget)
        detail = _rows(conn)[0]["detail"].lower()
        assert "credit balance" not in detail and "request_id" not in detail
        assert "sk-" not in detail

    async def test_an_unconfigured_notifier_claims_nothing(self, tmp_path, monkeypatch):
        conn, budget = _budget(tmp_path)
        off = FakeNotifier()
        off.enabled = False
        monkeypatch.setattr(credit_alert, "make_notifier", lambda: off)
        await _give(SimpleNamespace(messages=_Raises(credit_error())), budget)
        assert _rows(conn) == []


FORBIDDEN = ("AGENT_MAX", "_PER_DAY", "Anthropic", "ANTHROPIC", "API")


class TestTheRefusedTapSaysSo:
    def _assert_plain(self, text):
        assert "out of credit" in text
        for word in FORBIDDEN:
            assert word not in text, word

    def test_the_game_card_line(self):
        stored = call_failed_reason("credit_exhausted")
        line = no_card_line({"status": "refused_invalid", "reason": stored})
        self._assert_plain(line)

    async def test_the_leg_verdict_row(self, tmp_path, notifier):
        conn, budget = _budget(tmp_path)
        result = await _give(SimpleNamespace(messages=_Raises(credit_error())), budget)
        # the record keeps the vendor sentence; the screen does not
        assert "Anthropic" in result.refusal_reason
        row = {
            "status": "failed", "ticker": "T", "side": "yes", "id": 1,
            "ask_tenths": None, "completed_ms": NOW, "requested_ms": NOW,
            "refusal_reason": result.refusal_reason,
        }
        self._assert_plain(_row_to_response(row, now_ms=NOW)["refusal_reason"])

    async def test_the_scout_desk_row(self, tmp_path, notifier):
        conn, budget = desk_budget(tmp_path)
        result = await _convene(SimpleNamespace(messages=_Raises(credit_error())), budget)
        assert result.status == "failed"
        row = {
            "status": "failed", "refusal_reason": result.refusal_reason,
            "completed_ms": NOW, "requested_ms": NOW,
        }
        self._assert_plain(_screen_refusal(row, NOW))

    def test_a_non_credit_reason_is_left_alone(self):
        assert credit_alert.screen_sentence("the call returned nothing") is None


class TestTheGameCardSeat:
    async def test_a_credit_failed_card_pushes_once_and_its_line_is_plain(
        self, tmp_path, notifier
    ):
        from backend.agents.game_script import build_card
        from tests.test_game_script_card import (
            CONFIG, GAME, KICKOFF, NOW as GS_NOW, _conn_budget, _listing,
        )

        conn, budget = _conn_budget(tmp_path)
        client = SimpleNamespace(messages=_Raises(credit_error()))
        result = await build_card(
            conn, client, CONFIG, budget,
            game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            game_title="Atlanta at Pittsburgh", kickoff_iso="2026-09-13T17:00Z",
            listing=_listing(), now_ms=GS_NOW,
        )
        assert len(_rows(conn)) == 1 and notifier.sent == 1
        line = no_card_line({"status": result.status, "reason": result.reason})
        assert "out of credit" in line and "Anthropic" not in line
