"""Agent fleet tests.

No network: the Anthropic client is stubbed. What is tested here is the
*contract* around the agents, which is where the safety actually lives --
the schemas that make certain outputs unrepresentable, and the shared call
that every seat goes through.

A prompt is guidance. A gate is enforcement. Every rule that matters has both.

Until 2026-09-05 this file also carried `TestSkeptic` and `TestHistorian`. Both
modules were deleted -- the Skeptic's caller had been retired since ADR 0062
and the Historian was never called by anything that runs -- and the classes
went with them (`docs/adr/0106-the-historian-and-the-skeptic-are-deleted-and-the-desk-has-been-convened.md`).
`ScoutReport` is the `output_model` in the shared-call tests below because it
is the schema a live seat actually parses into; the stub never inspects it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.agents import scout
from backend.agents.base import HOUSE_CONTEXT, AgentConfig, structured_call
from backend.agents.scout import ScoutFinding, ScoutReport


class StubUsage:
    """The SDK usage block, down to the one nested field the meter reads."""

    def __init__(self, input_tokens=0, output_tokens=0, web_searches=None,
                 cache_creation=0, cache_read=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation
        self.cache_read_input_tokens = cache_read
        # Absent (None) means no server tool ran, matching the wire shape.
        self.server_tool_use = (
            None
            if web_searches is None
            else type("S", (), {"web_search_requests": web_searches})()
        )


class StubResponse:
    def __init__(self, parsed=None, stop_reason="end_turn", category=None,
                 usage=None):
        self.parsed_output = parsed
        self.stop_reason = stop_reason
        self.stop_details = type("D", (), {"category": category})() if category else None
        self.usage = usage


class StubMessages:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.last_kwargs = None

    async def parse(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raises:
            raise self._raises
        return self._response


class StubClient:
    def __init__(self, response=None, raises=None):
        self.messages = StubMessages(response, raises)


CONFIG = AgentConfig(api_key="test", model="claude-opus-5")


class TestConfig:
    def test_missing_key_yields_none_rather_than_raising(self, monkeypatch):
        """Agents are decision support. A missing key must not stop the ingest
        loop that records the evidence."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert AgentConfig.from_env() is None

    def test_defaults_to_opus_5(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.delenv("AGENT_MODEL", raising=False)
        assert AgentConfig.from_env().model == "claude-opus-5"

    def test_the_contract_file_carries_the_code_default(self):
        """`.env.example` says it keeps the Opus line "only because
        `backend/agents/base.py`'s DEFAULT_MODEL does, and the two disagreeing
        would be worse than either." That sentence described an intention with
        nothing holding it; this holds it. Live pins a different value in
        `fly.live.toml` on purpose (ADR 0071 section 2.7) and is not read here:
        the contract is what an operator copies, the deploy file is what one
        machine runs, and only the first must equal the code.
        """
        from pathlib import Path

        from backend.agents.base import DEFAULT_MODEL

        contract = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
            encoding="utf-8"
        )
        lines = [
            ln for ln in contract.splitlines() if ln.startswith("AGENT_MODEL=")
        ]
        assert len(lines) == 1, f"expected one AGENT_MODEL line, found {lines}"
        assert lines[0] == f"AGENT_MODEL={DEFAULT_MODEL}"


class TestSharedCall:
    async def test_the_cache_breakpoint_is_on_the_last_system_block(self):
        """It was on the shared block, and cached nothing.

        The intent was sound -- cache the house context once, so a per-agent
        prompt change cannot invalidate it for the other seats. The effect was
        zero: `HOUSE_CONTEXT` is 401 tokens and Claude Opus 5 will not cache a
        prefix under 512, so the breakpoint produced no entry, no error and no
        warning. A cache that does not fire is indistinguishable from one that
        does, unless you go and count.

        On the last block the prefix was 738-985 tokens for the seats measured
        on 2026-08-08, none of which bills today. Re-measure with
        `scripts/measure_agent_cache_prefix.py` -- now pointed at the desk's
        own seats -- if either the prompts or the model change; the minimum is
        model-specific and is **not** monotonic across releases (512 on Claude
        Opus 5, 1024 on Sonnet 5, 4096 on Opus 4.6).
        """
        client = StubClient(StubResponse(parsed=None))
        await structured_call(
            client, model="m", system="agent specific",
            user_content="hi", output_model=ScoutReport,
        )
        system = client.messages.last_kwargs["system"]
        assert system[0]["text"] == HOUSE_CONTEXT
        assert "cache_control" not in system[0], (
            "the breakpoint is back on the shared block, where the prefix is "
            "too short to cache"
        )
        assert system[-1]["cache_control"] == {"type": "ephemeral"}
        # The whole point is that the cached prefix includes the per-agent
        # half, so a breakpoint on a block that is not last would shrink it
        # again without moving.
        assert system[-1]["text"] == "agent specific"

    async def test_an_api_failure_returns_no_parse_and_no_usage(self):
        """No response arrived, so both halves are None -- the caller settles
        NULL usage, never 0, and `calls_unmetered_today` counts the row."""
        client = StubClient(raises=RuntimeError("down"))
        outcome = await structured_call(
            client, model="m", system="s", user_content="u",
            output_model=ScoutReport,
        )
        assert outcome.parsed is None
        assert outcome.usage is None

    async def test_a_refusal_returns_no_parse_but_keeps_the_usage(self):
        """A safety refusal is HTTP 200 with content that will not match the
        schema, so it must be caught before touching parsed_output -- and it
        was still BILLED, so the usage block must survive for the meter."""
        client = StubClient(StubResponse(
            stop_reason="refusal", category="cyber",
            usage=StubUsage(input_tokens=100, output_tokens=7),
        ))
        outcome = await structured_call(
            client, model="m", system="s", user_content="u",
            output_model=ScoutReport,
        )
        assert outcome.parsed is None
        assert outcome.usage is not None
        assert outcome.usage.input_tokens == 100
        assert outcome.usage.output_tokens == 7

    async def test_usage_sums_the_cache_classes_and_reads_searches(self):
        """`input_tokens` is the whole presented prompt -- uncached plus cache
        write plus cache read -- and `web_searches` comes from the nested
        `server_tool_use` block. Absent `server_tool_use` is an observed zero
        (no server tool ran), not a substitution."""
        client = StubClient(StubResponse(
            usage=StubUsage(input_tokens=10, output_tokens=5, web_searches=4,
                            cache_creation=700, cache_read=300),
        ))
        outcome = await structured_call(
            client, model="m", system="s", user_content="u",
            output_model=ScoutReport,
        )
        assert outcome.usage.input_tokens == 1010
        assert outcome.usage.output_tokens == 5
        assert outcome.usage.web_searches == 4
        assert outcome.usage.total_tokens == 1015

        quiet = StubClient(StubResponse(usage=StubUsage(input_tokens=1)))
        assert (await structured_call(
            quiet, model="m", system="s", user_content="u",
            output_model=ScoutReport,
        )).usage.web_searches == 0

    async def test_house_context_states_the_two_cent_reality(self):
        """The agents' priors have to match the venue's."""
        assert "2 cents" in HOUSE_CONTEXT or "two cents" in HOUSE_CONTEXT
        assert "13 automated market makers" in HOUSE_CONTEXT


class TestScout:
    """Research only. No numbers that could reach a bet."""

    def test_the_schema_cannot_express_a_forecast(self):
        finding_fields = set(ScoutFinding.model_fields)
        report_fields = set(ScoutReport.model_fields)
        forbidden = {
            "probability", "fair_price", "win_probability", "edge",
            "adjustment", "line", "spread",
        }
        assert not finding_fields & forbidden
        assert not report_fields & forbidden

    def test_the_prompt_forbids_estimating_probabilities(self):
        assert "must NOT estimate any probability" in scout.SYSTEM

    def test_an_empty_report_is_valid(self):
        """Inventing minor observations to look thorough makes the whole feed
        less trustworthy."""
        report = ScoutReport(
            game="A vs B", summary="Nothing noteworthy found.",
            searched_for=["injury reports", "weather"],
        )
        assert report.findings == []
        assert not report.has_fresh_news

    def test_old_news_does_not_count_as_fresh(self):
        """Old news explains nothing about a current gap -- every venue has
        already reacted."""
        report = ScoutReport(
            game="A vs B", summary="s", searched_for=["x"],
            findings=[
                ScoutFinding(
                    category="injury", fact="Out for the season",
                    source="ESPN", reported_when="three weeks ago",
                    likely_already_priced=True,
                )
            ],
        )
        assert not report.has_fresh_news

    def test_recent_news_is_flagged_as_fresh(self):
        report = ScoutReport(
            game="A vs B", summary="s", searched_for=["x"],
            findings=[
                ScoutFinding(
                    category="lineup", fact="Starter scratched",
                    source="The Athletic", reported_when="25 minutes ago",
                    likely_already_priced=False,
                )
            ],
        )
        assert report.has_fresh_news

    def test_searched_for_is_required(self):
        """An empty result only means something if you know what was looked for."""
        with pytest.raises(ValidationError):
            ScoutReport(game="g", summary="nothing", searched_for=[])

    def test_uses_the_server_side_web_search_tool(self):
        assert scout.WEB_SEARCH_TOOL["type"] == "web_search_20260209"
