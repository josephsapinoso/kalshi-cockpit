"""A server-tool error block's `error_code` reaches `agent_calls` (#316).

Convening 24 (2026-10-05) lost all six searches and the only record of why
was the model's own paraphrase, "server tool use limit exceeded" -- which
cannot tell our `max_uses` from the vendor's rate limit. The API says which
in a `web_search_tool_result` whose `content` is
`{"type": "web_search_tool_result_error", "error_code": ...}`.

**The limit IS captured, and it is not a `web_search_tool_result` error.**
Read 2026-10-06 off the committed scout capture
(`anthropic_scout_captured.json`): its fourth `code_execution_tool_result`
carries `return_code: 1` and `stderr: "Server tool use limit exceeded during
code execution."`, after exactly six billed searches of a `max_uses: 6` tool.
No `web_search_tool_result` error block accompanies it. Under dynamic
filtering (`web_search_20260209`) the search runs inside the sandbox, so the
cap surfaces as a failed execution, and until this file read it that way
five post-v64 cards that said "limit exceeded on every attempt" recorded
`{}`. The vendor's docs say a failed search is not billed, so the billed count
equalling the cap is the signature: every search up to the cap succeeded and
the next one killed the execution that held their output.

**The `web_search_tool_result_error` payload is still DERIVED.** Joe chose (A)
on 2026-10-05: no paid call to stage one. `_with_errors` starts from the real
capture and swaps one result block's content for the error shape the
installed SDK's own models define, validated through `Message.model_validate`
-- the SDK accepts it, but the SDK's models are only our belief about the
wire for THAT path.

What this establishes: a nonzero code-execution exit is counted, and the
captured limit text is named `server_tool_use_limit`; a derived error block
is counted by block type and code; a response with no errors records `{}`,
not NULL; a call with no response records NULL; and the code survives
`settle` onto the row. What it does not establish: that the API ever sends a
`web_search_tool_result_error` under dynamic filtering.
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


def _clean_captured() -> dict:
    """The capture with its one failed execution made to succeed, so the
    derived web-search-error cases start from a response with no errors."""
    payload = copy.deepcopy(_captured())
    for b in payload["content"]:
        if b["type"] == "code_execution_tool_result":
            b["content"]["return_code"] = 0
            b["content"]["stderr"] = ""
    return payload


def _with_errors(codes: list[str]) -> dict:
    """The clean capture with the first len(codes) search results failed."""
    payload = _clean_captured()
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

    def test_the_captured_limit_is_a_failed_execution_not_a_search_error(self):
        """The real capture: six searches succeeded, and the fourth code
        execution died on the cap. Until 2026-10-06 this test asserted the
        capture had NO errors, which pinned the blind spot."""
        payload = _captured()
        failed = [
            b for b in payload["content"]
            if b["type"] == "code_execution_tool_result" and b["content"]["return_code"] != 0
        ]
        assert len(failed) == 1
        assert failed[0]["content"]["stderr"] == (
            "Server tool use limit exceeded during code execution."
        )
        assert not any(
            isinstance(b.get("content"), dict) and "error_code" in b["content"]
            for b in payload["content"]
        ), "no web_search_tool_result error block accompanies the limit"
        assert tool_errors_from(_message(payload)) == (
            ("code_execution_tool_result:server_tool_use_limit", 1),
        )

    def test_the_billed_count_equals_the_cap_when_the_limit_hit(self):
        """A failed search is not billed (vendor docs), so billed == max_uses
        is the signature of the cap, not of six clean searches."""
        from backend.agents.scout import WEB_SEARCH_TOOL

        payload = _captured()
        assert payload["usage"]["server_tool_use"]["web_search_requests"] == (
            WEB_SEARCH_TOOL["max_uses"]
        )

    def test_a_capture_with_the_execution_fixed_has_no_errors(self):
        payload = _clean_captured()
        assert tool_errors_from(_message(payload)) == ()

    def test_any_other_nonzero_exit_is_counted_by_its_code(self):
        payload = _captured()
        for b in payload["content"]:
            if b["type"] == "code_execution_tool_result" and b["content"]["return_code"] != 0:
                b["content"]["return_code"] = 137
                b["content"]["stderr"] = "Killed"
        assert tool_errors_from(_message(payload)) == (
            ("code_execution_tool_result:exit_137", 1),
        )

    def test_the_log_line_keeps_the_stderr_and_drops_the_encrypted_stdout(self):
        from backend.agents.base import _error_blocks_json

        line = json.loads(_error_blocks_json(_message(_captured())))
        assert len(line) == 1
        assert line[0]["content"]["stderr"].startswith("Server tool use limit exceeded")
        assert line[0]["content"]["encrypted_stdout"].endswith(" chars>")

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
