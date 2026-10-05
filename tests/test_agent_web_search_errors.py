"""A server-tool error block's `error_code` reaches `agent_calls` (#316).

Convening 24 (2026-10-05) lost all six searches and the only record of why
was the model's own paraphrase, "server tool use limit exceeded" -- which
cannot tell our `max_uses` from the vendor's rate limit. The API says which
in a `web_search_tool_result` whose `content` is
`{"type": "web_search_tool_result_error", "error_code": ...}`.

**The error payload is DERIVED, not captured, and that is a known gap.** No
real error block exists yet. Joe chose (A) on 2026-10-05: no paid call to
stage one; `structured_call` logs each error block raw, and the first natural
failure's block is promoted into `tests/fixtures/` to replace the derivation
below. The derivation starts from the REAL captured scout response
(`anthropic_scout_captured.json`) and swaps one result block's content for the
error shape the installed SDK's own models define, then validates it through
`Message.model_validate` -- so the SDK accepts it, but the SDK's models are
only our belief about the wire, and this file cannot falsify them.

What this establishes: an error block is counted by block type and code; a
clean response records `{}`, not NULL; a call with no response records NULL;
and the code survives `settle` onto the row. What it does not establish: that
the API sends this shape, or what convening 24's code was.
"""

from __future__ import annotations

import copy
import json

from pathlib import Path

import pytest

from backend.agents.base import CallUsage, _usage_from, tool_errors_from
from backend.agents.budget import AgentBudget
from backend.store import db

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = 1_786_557_600_000


def _captured() -> dict:
    return json.loads(
        (FIXTURES / "anthropic_scout_captured.json").read_text(encoding="utf-8")
    )


def _with_errors(codes: list[str]) -> dict:
    """The captured response with the first len(codes) search results failed."""
    payload = copy.deepcopy(_captured())
    results = [b for b in payload["content"] if b["type"] == "web_search_tool_result"]
    assert len(results) >= len(codes)
    for block, code in zip(results, codes):
        block["content"] = {"type": "web_search_tool_result_error", "error_code": code}
    return payload


def _message(payload: dict):
    from anthropic.types import Message

    return Message.model_validate(payload)


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "errors.db")
    yield c
    c.close()


class TestTheErrorCodeIsRead:
    def test_each_failed_search_is_counted_by_its_code(self):
        message = _message(
            _with_errors(["max_uses_exceeded", "too_many_requests", "max_uses_exceeded"])
        )
        assert tool_errors_from(message) == (
            ("web_search_tool_result:max_uses_exceeded", 2),
            ("web_search_tool_result:too_many_requests", 1),
        )

    def test_a_clean_captured_response_has_no_errors(self):
        """The real capture's six search results and four code-execution
        results all succeeded; none of them may read as an error."""
        assert tool_errors_from(_message(_captured())) == ()

    def test_the_usage_carries_the_errors(self):
        usage = _usage_from(_message(_with_errors(["unavailable"])))
        assert usage is not None
        assert usage.tool_errors == (("web_search_tool_result:unavailable", 1),)


class TestTheCodeReachesTheRow:
    def _settle(self, conn, usage):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        call_id = meter.reserve(called_ms=NOW, agent="scout_staff", model="m")
        meter.settle(call_id, verdict="partial", usage=usage)
        return conn.execute(
            "SELECT tool_error_codes FROM agent_calls WHERE id = ?", (call_id,)
        ).fetchone()[0]

    def test_a_failed_search_is_stored_with_its_code(self, conn):
        usage = _usage_from(_message(_with_errors(["max_uses_exceeded"] * 6)))
        stored = self._settle(conn, usage)
        assert json.loads(stored) == {"web_search_tool_result:max_uses_exceeded": 6}

    def test_a_clean_call_stores_an_empty_object_not_null(self, conn):
        usage = CallUsage(input_tokens=1, output_tokens=1, web_searches=3)
        assert self._settle(conn, usage) == "{}"

    def test_a_call_with_no_response_stores_null(self, conn):
        assert self._settle(conn, None) is None


class TestTheInstrumentReadsIt:
    def test_agent_tool_errors_groups_codes_and_keeps_null_apart(self, conn):
        from scripts.inspect_live_db import CHEAP, QUERIES  # noqa: I001
        import inspect_live_db_parlays as parlays

        query = QUERIES["agent-tool-errors"]
        assert query.cost == CHEAP
        assert "LIMIT ?" in parlays._SQL_AGENT_TOOL_ERRORS
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        failed = _usage_from(_message(_with_errors(["max_uses_exceeded"])))
        for usage in (failed, failed, None, CallUsage(1, 1, 0)):
            call_id = meter.reserve(called_ms=NOW, agent="scout_staff", model="m")
            meter.settle(call_id, verdict="x", usage=usage)

        class Args:
            limit = 2000
            tail = 5

        (section,) = query.run(conn, Args())
        cols = section.columns
        got = {
            r[cols.index("tool_error_codes")]: r[cols.index("calls")]
            for r in section.rows
        }
        assert got == {
            '{"web_search_tool_result:max_uses_exceeded": 1}': 2,
            None: 1,
            "{}": 1,
        }
