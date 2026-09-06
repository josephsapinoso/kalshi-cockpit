"""`base.py`'s structured-call path, driven by a real `ParsedMessage`.

**The gap this closes, and the gap it leaves.** ADR 0106 §5.2 records that no
captured Anthropic payload exists under `tests/fixtures/`, against CLAUDE.md's
convention that wire-format tests load captured payloads. It is a gap on the
one money-spending path that survived ADR 0106: `scout.py` is live and has
eight briefings behind it.

**It is closed as of 2026-09-06**, by `anthropic_scout_captured.json` -- one
real paid call, authorised by Joe, taken with
`scripts/capture_agent_wire_fixture.py`. The two SDK-derived fixtures beside
it stay: they are small, they exercise the refusal path a live call did not
produce, and `scripts/build_agent_wire_fixture.py` says at length why a
generated payload could never have closed the gap alone.

The capture falsified the model of the wire that every stub in this repo had
carried. A real scout call returns **25 content blocks and exactly one is
`text`** -- the rest are `server_tool_use`, `web_search_tool_result`,
`code_execution_tool_result` and `thinking` -- and the text block is last, so
`parsed_output` walks past twenty-four of them. Its `usage` carries a nested
`cache_creation`, `output_tokens_details.thinking_tokens` and `inference_geo`;
its envelope carries `container` and `stop_details`. None of that was guessed
correctly.

These files also close a different and, until then, unnoticed hole: **the
existing stubs bypassed the very thing they were testing.**

`tests/test_agents.py:48` and `tests/test_scout_desk.py:56` each build a fake
response and assign `self.parsed_output = parsed`.
`anthropic.types.ParsedMessage.parsed_output` is a **property** which walks
`content` for the first text block carrying a parsed value. Assigning over it
means the property never ran, no content block was ever built, and the JSON
was never validated against `ScoutReport` -- so those tests assert that
`base.py` can read an attribute the test had just set on a bare object. They
would pass against an SDK whose parsing was entirely broken.

Here the object under test is built the way the SDK builds it:
`Message.model_validate(<fixture>)` then
`anthropic.lib._parse._response.parse_response(output_format=ScoutReport, ...)`
-- the same function `client.messages.parse` calls. So the payload must
satisfy the SDK's own models, the JSON must satisfy `ScoutReport`, and
`parsed_output` is the real property doing the real walk.

That the SDK's models are themselves only our *belief* about the wire is why
a derived fixture could not settle §5.2 on its own -- it cannot falsify what
it was generated from. The captured payload is what does.

What this establishes: that a well-formed response yields a `ScoutReport`
through the real property; that a refusal is caught *before* `parsed_output`
is touched, in that order; that `_usage_from` reads the real usage shape
including both server-tool counters; and that the fixtures on disk are ones
the installed SDK accepts.

What this does **not** establish: that Anthropic sends this; that the prompt
is any good; that the Scout is worth its money (ADR 0071 §3 and the
`scout_briefings` volume own that); or anything about the retired reviewer.
"""

from __future__ import annotations

import json

from pathlib import Path

import pytest

from backend.agents.base import _usage_from
from backend.agents.scout import ScoutReport

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def parsed_message(payload: dict):
    """Build the object `client.messages.parse` would return, the same way.

    Imported inside the helper rather than at module scope so a missing or
    moved SDK internal fails one test with a legible import error instead of
    collecting the whole file as an error.
    """
    from anthropic.types import Message
    from anthropic.lib._parse._response import parse_response

    message = Message.model_validate(payload)
    return parse_response(output_format=ScoutReport, response=message)


class TestTheFixturesAreOnesTheSdkAccepts:
    """If the SDK would reject a fixture, every test built on it is a false
    green. This is the assertion the hand-built stubs could not make."""

    @pytest.mark.parametrize(
        "name", ["anthropic_scout_report.json", "anthropic_scout_refusal.json"]
    )
    def test_the_payload_validates(self, name):
        from anthropic.types import Message

        Message.model_validate(load(name))

    def test_the_usage_block_carries_both_server_tool_counters(self):
        """`web_fetch_requests` is required by the SDK's model and was missing
        from the first draft of the fixture, which the validator refused. A
        hand-built stub would have carried the omission silently."""
        usage = load("anthropic_scout_report.json")["usage"]
        assert set(usage["server_tool_use"]) == {
            "web_search_requests",
            "web_fetch_requests",
        }


class TestTheRealPropertyProducesTheReport:
    def test_parsed_output_walks_the_content_blocks(self):
        """The property, not an assignment. This is the whole point of the
        file: `parsed_output` is computed from `content`, and no test in this
        repo had ever run it."""
        report = parsed_message(load("anthropic_scout_report.json")).parsed_output
        assert isinstance(report, ScoutReport)
        assert report.game == "Milwaukee Brewers at New York Mets"
        assert len(report.findings) == 2

    def test_the_json_must_satisfy_our_own_output_model(self):
        """`parse_response` validates the text block against `ScoutReport`, so
        a fixture that drifted from the model would raise here rather than
        yield a half-built object."""
        payload = load("anthropic_scout_report.json")
        text = json.loads(payload["content"][0]["text"])
        del text["searched_for"]
        payload["content"][0]["text"] = json.dumps(text)
        with pytest.raises(Exception):
            parsed_message(payload)

    def test_the_freshness_split_survives_the_round_trip(self):
        """`has_fresh_news` is a property on our model reading a field the SDK
        parsed. One fresh finding and one stale one, so it has something to
        separate rather than defaulting true."""
        report = parsed_message(load("anthropic_scout_report.json")).parsed_output
        assert report.has_fresh_news is True
        assert [f.likely_already_priced for f in report.findings] == [False, True]

    def test_an_absent_source_url_stays_none_rather_than_empty(self):
        """The optional field, exercised rather than assumed. Unreadable and
        absent are not the empty string anywhere in this repo."""
        report = parsed_message(load("anthropic_scout_report.json")).parsed_output
        assert report.findings[1].source_url is None


class TestARefusalNeverReachesTheRefusalBranch:
    """**A finding, not a design.** `base.py` reads as though it checks
    `stop_reason == "refusal"` before touching `parsed_output`. It cannot:
    `messages.parse` runs the SDK's `parse_response` over every text block
    with no regard for `stop_reason`, so a refusal's non-schema content raises
    a pydantic `ValidationError` inside `.parse()` and the `Message` is never
    returned.

    Found on 2026-09-05 by writing these tests to the comment's claim and
    watching them fail. The old hand-built stubs could not have found it --
    they assigned `parsed_output` onto a bare object and never ran the SDK's
    parsing at all.

    The consequence is on the meter, not on safety: the call was billed, and
    its token count lives on the `Message` we never get, so the row settles
    with NULL usage. `base.py` now catches `ValidationError` separately and
    says so; recovering the count would mean reimplementing the SDK's
    `output_format` -> JSON-schema transformation.
    """

    def test_the_message_itself_carries_the_refusal(self):
        """The stop reason IS on the envelope -- so the branch would be right
        if the SDK ever handed the Message back."""
        from anthropic.types import Message

        assert Message.model_validate(
            load("anthropic_scout_refusal.json")
        ).stop_reason == "refusal"

    def test_parsing_a_refusal_raises_instead_of_returning(self):
        """The defect, pinned. If a future SDK stops parsing a refusal's
        content, this goes red and `base.py`'s dormant branch becomes the
        live path -- which is exactly when someone should re-read both."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            parsed_message(load("anthropic_scout_refusal.json"))

    def test_base_catches_that_error_apart_from_a_transport_failure(self):
        """The two differ in the one way the meter cares about: this one spent
        tokens. Mutation observed red: collapse the two `except` clauses."""
        source = (
            REPO / "backend" / "agents" / "base.py"
        ).read_text(encoding="utf-8")
        assert "except ValidationError:" in source, (
            "a billed-but-unparseable response is logged as a transport "
            "failure again, so a refusal and a dead network read alike"
        )
        assert "the call was billed and its token count is lost" in source


class TestUsageIsReadFromTheRealShape:
    def test_the_three_input_counters_are_summed(self):
        """`input_tokens + cache_creation + cache_read`. A response billed
        mostly to the cache would otherwise read as nearly free."""
        parsed = parsed_message(load("anthropic_scout_report.json"))
        raw = load("anthropic_scout_report.json")["usage"]
        usage = _usage_from(parsed)
        assert usage.input_tokens == (
            raw["input_tokens"]
            + raw["cache_creation_input_tokens"]
            + raw["cache_read_input_tokens"]
        )
        assert usage.output_tokens == raw["output_tokens"]

    def test_web_searches_come_from_the_server_tool_block(self):
        usage = _usage_from(parsed_message(load("anthropic_scout_report.json")))
        assert usage.web_searches == 4


class TestTheCapturedPayloadIsTheRealWire:
    """**A real Anthropic response, captured 2026-09-06.** One paid call,
    authorised by Joe, via `scripts/capture_agent_wire_fixture.py`. This is
    what closes ADR 0106 §5.2 -- the SDK-derived fixtures above could not,
    because a payload generated from the SDK's models cannot falsify them.

    It falsified my model of the wire immediately, which is the point:
    """

    CAPTURED = "anthropic_scout_captured.json"

    def test_the_sdk_accepts_it(self):
        from anthropic.types import Message

        Message.model_validate(load(self.CAPTURED))

    def test_the_real_response_is_mostly_not_text(self):
        """**25 content blocks, exactly one of them `text`.** Every
        hand-written stub in this repo, and the SDK-derived fixture above,
        modelled a response as a single text block. A real scout call with the
        web-search tool returns `server_tool_use`, `web_search_tool_result`,
        `code_execution_tool_result` and `thinking` blocks, and the one text
        block is LAST. `parsed_output` walks past twenty-four of them to find
        it -- which is the property working, and is a walk no stub ever
        exercised.
        """
        blocks = load(self.CAPTURED)["content"]
        kinds = [b["type"] for b in blocks]
        assert len(blocks) > 10, "the capture no longer exercises a long walk"
        assert kinds.count("text") == 1
        assert kinds[-1] == "text", (
            "the text block is no longer last, so the property's walk is no "
            "longer exercised to its end"
        )
        assert {"server_tool_use", "web_search_tool_result", "thinking"} <= set(kinds)

    def test_parsed_output_finds_the_report_past_the_tool_blocks(self):
        report = parsed_message(load(self.CAPTURED)).parsed_output
        assert isinstance(report, ScoutReport)
        assert report.searched_for, "the model reported no searches"

    def test_the_usage_shape_is_richer_than_the_derived_fixture(self):
        """Fields the real wire carries that the SDK-derived fixture did not:
        a nested `cache_creation`, `output_tokens_details.thinking_tokens`,
        and `inference_geo`. `_usage_from` reads none of them and must not
        break on them -- it sums the three input counters and reads
        `server_tool_use`, and everything else on this block is someone else's
        field."""
        usage = load(self.CAPTURED)["usage"]
        assert "cache_creation" in usage
        assert "thinking_tokens" in usage["output_tokens_details"]
        assert usage["server_tool_use"]["web_search_requests"] > 0

    def test_usage_reads_the_captured_block(self):
        parsed = parsed_message(load(self.CAPTURED))
        raw = load(self.CAPTURED)["usage"]
        usage = _usage_from(parsed)
        assert usage.input_tokens == (
            raw["input_tokens"]
            + raw["cache_creation_input_tokens"]
            + raw["cache_read_input_tokens"]
        )
        assert usage.web_searches == raw["server_tool_use"]["web_search_requests"]

    def test_the_envelope_carries_fields_the_derived_fixture_lacked(self):
        """`container` and `stop_details` are on the real envelope and were
        absent from every stub. Neither is read by `base.py` today --
        `stop_details.category` is read only on the refusal path -- but a
        fixture that lacks them cannot show that."""
        body = load(self.CAPTURED)
        assert "stop_details" in body
        assert "container" in body

    def test_it_carries_no_credential_and_no_account_identifier(self):
        """This repo is public. The capture is the response body only -- no
        request, no headers -- and this pins that a future re-capture cannot
        quietly add one."""
        import re

        raw = (FIXTURES / self.CAPTURED).read_text(encoding="utf-8")
        for pattern in (r"sk-ant", r"(?i)authorization", r"-----BEGIN",
                        r"(?i)api[_-]?key", r"josephsapinoso"):
            assert not re.search(pattern, raw), (
                f"the captured fixture matches {pattern!r}"
            )

    def test_search_results_carry_no_plaintext_article_body(self):
        """Third-party page content arrives as `encrypted_content`, so the
        fixture cites sources without reproducing them. If a future SDK or
        API version returns plaintext, this goes red and the fixture needs a
        decision before it is committed."""
        for block in load(self.CAPTURED)["content"]:
            if block["type"] != "web_search_tool_result":
                continue
            for result in block["content"]:
                assert "encrypted_content" in result
                assert set(result) <= {
                    "encrypted_content", "page_age", "title", "url", "type",
                }, f"unexpected field in a search result: {sorted(result)}"
