"""#365: an Anthropic API failure settles as a failure, not `filed_nothing`.

`filed_nothing` is what a model that looked and found nothing settles. An
errored call (notably "Your credit balance is too low", 2026-10-10 23:50Z)
settled the same, which turned an outage into a content judgement and
corrupted `agent-spend`. Positive controls: a genuine empty reply still
settles `filed_nothing`.

Fixture: `fixtures/anthropic_credit_exhausted_error.json` -- message text as
recorded on live, envelope the SDK's documented shape (see its provenance).

Does NOT establish: the exact bytes Anthropic sends for this failure.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx

from backend.agents.base import api_error_verdict, is_credit_exhausted
from backend.agents.base import output_model_name
from backend.agents.game_script import build_card
from backend.agents.scout import ScoutReport
from tests.test_game_script_card import (
    CONFIG as GS_CONFIG, GAME, KICKOFF, NOW as GS_NOW, _conn_budget, _listing,
)
from tests.test_leg_verdict_seat import StubClient, _budget as lv_budget, _give
from tests.test_scout_desk import (
    DeskStubClient, StubResponse as DeskResponse, _budget as desk_budget, _convene,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "anthropic_credit_exhausted_error.json")
    .read_text(encoding="utf-8")
)


def credit_error() -> anthropic.BadRequestError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(
        FIXTURE["status_code"], request=request, json=FIXTURE["body"]
    )
    return anthropic.BadRequestError(
        FIXTURE["body"]["error"]["message"], response=response, body=FIXTURE["body"]
    )


class _Raises:
    def __init__(self, exc):
        self._exc = exc

    async def create(self, **kwargs):
        raise self._exc


def _verdicts(conn):
    return [r["verdict"] for r in conn.execute(
        "SELECT verdict FROM agent_calls ORDER BY id").fetchall()]


class TestThePredicate:
    def test_the_sdk_error_is_credit_exhausted(self):
        assert is_credit_exhausted(credit_error())

    def test_the_bare_text_is_credit_exhausted(self):
        assert is_credit_exhausted(FIXTURE["body"]["error"]["message"])

    def test_other_errors_are_not(self):
        assert not is_credit_exhausted(RuntimeError("reset"))
        assert not is_credit_exhausted(None)

    def test_the_verdict_names_the_kind(self):
        assert api_error_verdict("call_error", "credit") == "api_error:credit"
        assert api_error_verdict("call_error") == "api_error"
        assert api_error_verdict("schema_mismatch") is None


class TestScoutDesk:
    async def test_a_credit_failure_is_not_filed_nothing(self, tmp_path):
        conn, budget = desk_budget(tmp_path)
        client = SimpleNamespace(messages=_Raises(credit_error()))
        result = await _convene(client, budget)
        assert result.status == "failed"
        assert _verdicts(conn) == ["api_error:credit", "api_error:credit"]

    async def test_a_genuine_empty_reply_still_settles_filed_nothing(self, tmp_path):
        """Positive control: no report, but no error either."""
        conn, budget = desk_budget(tmp_path)
        client = DeskStubClient()
        original = client.messages.create

        async def create(**kwargs):
            if output_model_name(kwargs["output_format"]) == "ScoutReport":
                return DeskResponse(None)
            return await original(**kwargs)

        client.messages.create = create
        await _convene(client, budget)
        assert _verdicts(conn)[:2] == ["filed_nothing", "filed_nothing"]

    async def test_a_plain_error_is_api_error_without_a_kind(self, tmp_path):
        conn, budget = desk_budget(tmp_path)
        client = SimpleNamespace(messages=_Raises(RuntimeError("reset")))
        await _convene(client, budget)
        assert _verdicts(conn) == ["api_error", "api_error"]


class TestLegVerdict:
    async def test_a_credit_failure_is_not_filed_nothing(self, tmp_path):
        conn, budget = lv_budget(tmp_path)
        client = SimpleNamespace(messages=_Raises(credit_error()))
        result = await _give(client, budget)
        assert result.status == "failed"
        assert _verdicts(conn) == ["api_error:credit"]

    async def test_a_no_output_reply_still_settles_filed_nothing(self, tmp_path):
        conn, budget = lv_budget(tmp_path)
        await _give(StubClient(parsed=None), budget)
        assert _verdicts(conn) == ["filed_nothing"]


class TestGameScript:
    async def test_a_credit_failure_is_not_filed_nothing_and_the_card_says_so(
        self, tmp_path
    ):
        conn, budget = _conn_budget(tmp_path)
        client = SimpleNamespace(messages=_Raises(credit_error()))
        result = await build_card(
            conn, client, GS_CONFIG, budget,
            game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            game_title="Atlanta at Pittsburgh", kickoff_iso="2026-09-13T17:00Z",
            listing=_listing(), now_ms=GS_NOW,
        )
        assert _verdicts(conn) == ["api_error:credit"]
        assert "out of credit" in result.reason
