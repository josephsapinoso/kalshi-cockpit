"""A billed reply that fails to parse settles with its usage (#371).

On live at 2026-10-12T19:06:34Z the master scout's reply did not match
`DeskBriefing`; the vendor billed the call, `messages.parse` raised before
handing back the `Message`, and the ledger row settled `filed_nothing` with
NULL tokens -- a billed call the 5M ceiling never counted, labelled as a
quiet desk. `structured_call` now calls `messages.create` and runs the
SDK's `parse_response` itself, so the usage is read off the raw message
before anything is parsed.

Every payload here is a captured response (`tests/fixtures/`), driven
through the SDK's real `Message` type and real `parse_response`: that is
what keeps `_parse_structured`'s shortcut for test doubles honest, because
nothing in this file uses the shortcut.

What this file does NOT establish: that the live SDK version matches the
one these tests import (the pin is `anthropic~=0.49`); that a `refusal`
`stop_reason` is what the vendor sends for every refusal shape; or the
token count of the real 19:06Z reply, which was lost before this change.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
from anthropic.types import Message

from backend.agents import scout_desk
from backend.agents.base import StructuredCallOutcome, output_model_name, structured_call
from backend.agents.scout import ScoutReport
from backend.store import db
from backend.agents.budget import AgentBudget

from tests.test_scout_desk import CONFIG, DeskStubClient, DeskStubMessages

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def message(payload: dict) -> Message:
    return Message.model_validate(payload)


def mismatched(payload: dict) -> dict:
    """The captured report with its JSON text cut in half: the shape of a
    reply that hit `max_tokens`, which pydantic reports as `json_invalid`
    and which fails every schema, not only this one."""
    out = copy.deepcopy(payload)
    for block in out["content"]:
        if block["type"] == "text":
            block["text"] = block["text"][: len(block["text"]) // 2]
    return out


class _CreateStub:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises:
            raise self._raises
        return self._response


class _Client:
    def __init__(self, **kw):
        self.messages = _CreateStub(**kw)


async def call(client, output_model=ScoutReport) -> StructuredCallOutcome:
    return await structured_call(
        client, model="claude-sonnet-5", system="x", user_content="y",
        output_model=output_model, max_tokens=100,
    )


class TestTheRequestIsCreateWithTheSdkSchema:
    async def test_output_format_is_the_json_schema_create_takes(self):
        client = _Client(response=message(load("anthropic_scout_report.json")))
        await call(client)
        sent = client.messages.calls[0]["output_config"]["format"]
        assert sent["type"] == "json_schema"
        assert "properties" in sent["schema"]
        assert "findings" in sent["schema"]["properties"]


class TestABilledMismatchKeepsItsUsage:
    async def test_a_schema_mismatch_settles_with_usage_and_its_own_verdict(self):
        payload = mismatched(load("anthropic_scout_report.json"))
        outcome = await call(_Client(response=message(payload)))
        assert outcome.parsed is None
        assert outcome.failure == "schema_mismatch"
        assert outcome.usage is not None
        u = payload["usage"]
        assert outcome.usage.input_tokens == (
            u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
        )
        assert outcome.usage.output_tokens == u["output_tokens"]
        assert outcome.settle_verdict == "schema_mismatch"
        assert "json_invalid" in (outcome.failure_detail or "")

    async def test_the_mismatch_is_real_not_a_quiet_parse(self):
        """Positive control: the unmodified capture parses to a report."""
        outcome = await call(_Client(response=message(load("anthropic_scout_report.json"))))
        assert isinstance(outcome.parsed, ScoutReport)
        assert outcome.failure is None
        assert outcome.settle_verdict is None
        assert outcome.usage is not None


class TestARefusalIsARefusalNow:
    async def test_a_refusal_reaches_the_refusal_branch_with_usage(self):
        payload = load("anthropic_scout_refusal.json")
        outcome = await call(_Client(response=message(payload)))
        assert outcome.failure == "refusal"
        assert outcome.parsed is None
        assert outcome.usage is not None
        assert outcome.settle_verdict == "refusal"


class TestATransportDeathStillSettlesNull:
    async def test_an_exception_before_a_response_has_no_usage(self):
        outcome = await call(_Client(raises=RuntimeError("down")))
        assert outcome.failure == "call_error"
        assert outcome.usage is None
        assert outcome.settle_verdict == "api_error"


class _MasterMismatchMessages(DeskStubMessages):
    """The desk's stub, with the master's reply a real captured `Message`
    whose JSON does not match `DeskBriefing`."""

    async def create(self, **kwargs):
        if output_model_name(kwargs["output_config"]) == "DeskBriefing":
            self.calls.append(kwargs)
            # A captured reply cut in half: real usage, JSON that no schema
            # accepts -- the shape of the 2026-10-12 19:06Z master reply.
            return message(mismatched(load("anthropic_scout_report.json")))
        return await super().create(**kwargs)


class _MasterMismatchClient(DeskStubClient):
    def __init__(self, **kwargs):
        self.messages = _MasterMismatchMessages(**kwargs)


async def _convene(client, budget):
    return await scout_desk.convene_desk(
        client, CONFIG, budget,
        ticker="KXTEST", event_title="A at B", league="baseball_mlb",
        commence_iso="2026-08-21T22:00:00+00:00",
        home_team="B", away_team="A", now_ms=1_000_000,
    )


class TestTheMasterScoutSettlesWithUsage:
    async def test_a_master_reply_that_does_not_parse_is_billed_in_the_ledger(self, tmp_path):
        conn = db.init_db(tmp_path / "desk.db")
        budget = AgentBudget(
            conn, per_pass_budget=8, daily_budget=24,
            searches_daily_budget=0, tokens_daily_budget=0,
        )
        result = await _convene(_MasterMismatchClient(), budget)
        assert result.status == "partial"
        assert result.briefing is None
        row = conn.execute(
            "SELECT verdict, input_tokens, output_tokens FROM agent_calls "
            "WHERE agent = 'scout_master'"
        ).fetchone()
        assert row["verdict"] == "schema_mismatch"
        assert row["input_tokens"] is not None and row["input_tokens"] > 0
        assert row["output_tokens"] is not None and row["output_tokens"] > 0


class TestTheScreenNamesTheCase:
    def test_the_partial_sentence_says_the_answer_may_not_have_parsed(self):
        text = (REPO / "frontend" / "src" / "components" / "ScoutDesk.tsx").read_text(
            encoding="utf-8"
        )
        flat = re.sub(r"\s+", " ", text)
        assert "his answer did not parse" in flat
        assert "the day&rsquo;s budget could not afford it" in flat


class TestTheOldSentenceIsGone:
    def test_base_no_longer_says_the_count_is_lost(self):
        source = (REPO / "backend" / "agents" / "base.py").read_text(encoding="utf-8")
        assert "its token count is lost" not in source
        assert "client.messages.parse(" not in source
        assert "client.messages.create(" in source


class TestTheRequestBindsToTheRealCreate:
    """Every stub here takes `**kwargs`, so a parameter `create` does not have
    passed the suite and raised TypeError on every live call (#371 sent
    `output_format`, which only `parse` takes). Bind to the SDK's own
    signature so the next one fails here."""

    async def test_the_sent_kwargs_bind_to_async_messages_create(self):
        import inspect

        from anthropic.resources.messages import AsyncMessages

        client = _Client(response=message(load("anthropic_scout_report.json")))
        await call(client)
        sent = client.messages.calls[0]
        inspect.signature(AsyncMessages.create).bind(None, **sent)

    async def test_the_schema_rides_in_output_config_beside_effort(self):
        client = _Client(response=message(load("anthropic_scout_report.json")))
        await call(client)
        sent = client.messages.calls[0]
        assert "output_format" not in sent
        assert sent["output_config"]["format"]["type"] == "json_schema"
        assert "effort" in sent["output_config"]


class TestTheStepCountIsRecorded:
    """#383: each `agent_calls` row records how many server-tool steps the
    returned `Message` took, read off a captured reply with tool blocks; NULL
    when no reply came back, never 0. Answers #370's "steps are unrecorded"."""

    def _budget(self, tmp_path):
        conn = db.init_db(tmp_path / "steps.db")
        return conn, AgentBudget(conn, per_pass_budget=8, daily_budget=24)

    async def test_a_reply_with_tool_blocks_counts_its_server_tool_use_blocks(self):
        payload = load("anthropic_scout_captured.json")
        expected = sum(1 for b in payload["content"] if b["type"] == "server_tool_use")
        assert expected == 10  # the capture, not the walk, fixes this number
        outcome = await call(_Client(response=message(payload)))
        assert outcome.usage is not None
        assert outcome.usage.server_tool_steps == expected

    async def test_a_reply_with_no_tool_blocks_reads_zero_not_null(self):
        outcome = await call(_Client(response=message(load("anthropic_scout_report.json"))))
        assert outcome.usage.server_tool_steps == 0

    async def test_the_count_reaches_the_ledger_row(self, tmp_path):
        conn, budget = self._budget(tmp_path)
        outcome = await call(_Client(response=message(load("anthropic_scout_captured.json"))))
        call_id = budget.reserve(called_ms=1_000, agent="scout", model="m")
        budget.settle(call_id, usage=outcome.usage)
        row = conn.execute(
            "SELECT server_tool_steps FROM agent_calls WHERE id = ?", (call_id,)
        ).fetchone()
        assert row["server_tool_steps"] == 10

    async def test_a_call_that_never_returned_settles_null_not_zero(self, tmp_path):
        conn, budget = self._budget(tmp_path)
        outcome = await call(_Client(raises=RuntimeError("down")))
        call_id = budget.reserve(called_ms=1_000, agent="scout", model="m")
        budget.settle(call_id, usage=outcome.usage)
        row = conn.execute(
            "SELECT server_tool_steps FROM agent_calls WHERE id = ?", (call_id,)
        ).fetchone()
        assert row["server_tool_steps"] is None
