"""Agent fleet tests.

No network: the Anthropic client is stubbed. What is tested here is the
*contract* around the agents, which is where the safety actually lives —
the schemas that make certain outputs unrepresentable, and the deterministic
gates that stand behind the prompts.

A prompt is guidance. A gate is enforcement. Every rule that matters has both.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.agents import historian, scout, skeptic
from backend.agents.base import HOUSE_CONTEXT, AgentConfig, structured_call
from backend.agents.historian import ConfigProposal, HistorianReport
from backend.agents.scout import ScoutFinding, ScoutReport
from backend.agents.skeptic import SkepticVerdict
from backend.store import db


class StubResponse:
    def __init__(self, parsed=None, stop_reason="end_turn", category=None):
        self.parsed_output = parsed
        self.stop_reason = stop_reason
        self.stop_details = type("D", (), {"category": category})() if category else None


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


class TestSharedCall:
    async def test_the_cache_breakpoint_is_on_the_last_system_block(self):
        """It was on the shared block, and cached nothing.

        The intent was sound -- cache the house context once, so a per-agent
        prompt change cannot invalidate it for the other two. The effect was
        zero: `HOUSE_CONTEXT` is 401 tokens and Claude Opus 5 will not cache a
        prefix under 512, so the breakpoint produced no entry, no error and no
        warning. A cache that does not fire is indistinguishable from one that
        does, unless you go and count.

        On the last block the prefix is 738-985 tokens depending on the agent.
        Re-measure with `scripts/measure_agent_cache_prefix.py` if either the
        prompts or the model change -- the minimum is model-specific and is
        **not** monotonic across releases (512 on Claude Opus 5, 4096 on
        Opus 4.6).
        """
        client = StubClient(StubResponse(parsed=None))
        await structured_call(
            client, model="m", system="agent specific",
            user_content="hi", output_model=SkepticVerdict,
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

    async def test_an_api_failure_returns_none_rather_than_raising(self):
        client = StubClient(raises=RuntimeError("down"))
        assert await structured_call(
            client, model="m", system="s", user_content="u",
            output_model=SkepticVerdict,
        ) is None

    async def test_a_refusal_returns_none(self):
        """A safety refusal is HTTP 200 with content that will not match the
        schema, so it must be caught before touching parsed_output."""
        client = StubClient(StubResponse(stop_reason="refusal", category="cyber"))
        assert await structured_call(
            client, model="m", system="s", user_content="u",
            output_model=SkepticVerdict,
        ) is None

    async def test_house_context_states_the_two_cent_reality(self):
        """The agents' priors have to match the venue's."""
        assert "2 cents" in HOUSE_CONTEXT or "two cents" in HOUSE_CONTEXT
        assert "13 automated market makers" in HOUSE_CONTEXT


class TestSkeptic:
    """Rejection is the default, and the Skeptic cannot approve anything."""

    def test_the_prompt_makes_rejection_the_default(self):
        assert "until you have tried and failed" in skeptic.SYSTEM
        assert "cannot approve a bet" in skeptic.SYSTEM

    def test_the_verdict_schema_has_no_probability_field(self):
        """An agent that could emit a fair price would be an unfalsifiable
        component in the money path."""
        fields = set(SkepticVerdict.model_fields)
        assert not fields & {"fair_probability", "fair_price", "edge", "stake"}

    @pytest.mark.parametrize("verdict", ["defect", "suspicious"])
    def test_negative_verdicts_block(self, verdict):
        v = SkepticVerdict(
            verdict=verdict, primary_concern="x", checks_performed=["a"],
            recommended_action="reject", confidence=0.8,
        )
        assert v.blocks_bet

    def test_plausible_does_not_block_but_also_does_not_approve(self):
        v = SkepticVerdict(
            verdict="plausible", primary_concern="checked four lines",
            checks_performed=["a"], recommended_action="proceed_with_caution",
            confidence=0.5,
        )
        assert not v.blocks_bet
        assert v.recommended_action != "bet"

    def test_recommended_action_cannot_be_bet(self):
        """The literal type makes it unrepresentable, not merely discouraged."""
        with pytest.raises(ValidationError):
            SkepticVerdict(
                verdict="plausible", primary_concern="x", checks_performed=["a"],
                recommended_action="bet", confidence=0.5,
            )

    def test_a_verdict_can_only_add_a_suppression_reason(self):
        """An agent that could clear a reason would be a way to argue past the
        deterministic checks."""
        v = SkepticVerdict(
            verdict="defect", primary_concern="regulation vs overtime",
            checks_performed=["market mismatch"], recommended_action="reject",
            confidence=0.9,
        )
        assert skeptic.apply_verdict(v, "stale_odds") == "stale_odds,skeptic_defect"
        assert skeptic.apply_verdict(v, None) == "skeptic_defect"

    def test_a_plausible_verdict_leaves_existing_reasons_intact(self):
        v = SkepticVerdict(
            verdict="plausible", primary_concern="x", checks_performed=["a"],
            recommended_action="proceed_with_caution", confidence=0.5,
        )
        assert skeptic.apply_verdict(v, "stale_odds") == "stale_odds"

    def test_no_verdict_changes_nothing(self):
        assert skeptic.apply_verdict(None, "wide_market") == "wide_market"

    def test_the_prompt_carries_per_method_devig_figures(self):
        """So the agent can see method disagreement exceeding the claimed edge."""
        prompt = skeptic.build_prompt(
            ticker="T", market_title="m", outcome_name="Houston",
            event_title="Houston vs San Diego", kalshi_ask_cents=50.3,
            consensus_fair_cents=53.8, edge_cents=1.7, quote_age_s=3,
            odds_age_s=240, book_count=5, market_width_points=1.2,
            depth_at_ask=800.0,
            devig_methods={"multiplicative": 0.538, "shin": 0.536},
            commence_iso="2026-08-10T03:20:00Z",
        )
        assert "multiplicative" in prompt
        assert "method choice" in prompt

    def test_the_prompt_excludes_stake_and_bankroll(self):
        """Including them would invite the agent to reason about sizing."""
        prompt = skeptic.build_prompt(
            ticker="T", market_title="m", outcome_name="H", event_title="e",
            kalshi_ask_cents=50, consensus_fair_cents=53, edge_cents=2,
            quote_age_s=1, odds_age_s=1, book_count=4, market_width_points=1,
            depth_at_ask=100.0, devig_methods={"shin": 0.53}, commence_iso=None,
        )
        assert "bankroll" not in prompt.lower()
        assert "contracts" not in prompt.lower()


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


class TestHistorian:
    """The flywheel's brake. Prompts guide; validate_proposals enforces."""

    def _report(self, *, distinguishable: bool, sample: int) -> HistorianReport:
        return HistorianReport(
            period="2026-W32", lesson_title="t", lesson_body="b",
            evidence_read=["mart_clv_by_bucket"],
            findings_are_distinguishable_from_chance=distinguishable,
            proposals=[
                ConfigProposal(
                    parameter="max_market_width", current_value="0.06",
                    proposed_value="0.10", rationale="r",
                    supporting_sample_size=sample, risk_if_wrong="worse fills",
                )
            ],
        )

    def test_proposals_are_rejected_when_findings_are_chance(self):
        kept, rejected = historian.validate_proposals(
            self._report(distinguishable=False, sample=5000)
        )
        assert kept == []
        assert "not distinguishable from chance" in rejected[0]

    def test_proposals_are_rejected_on_a_thin_sample(self):
        """Twenty bets is not evidence, and a flywheel that tunes on twenty
        bets is overfitting with extra steps."""
        kept, rejected = historian.validate_proposals(
            self._report(distinguishable=True, sample=30)
        )
        assert kept == []
        assert "overfitting" in rejected[0]

    def test_a_well_supported_proposal_survives(self):
        kept, rejected = historian.validate_proposals(
            self._report(distinguishable=True, sample=800)
        )
        assert len(kept) == 1
        assert rejected == []

    def test_the_prompt_orders_the_multiple_comparisons_verdict_first(self):
        assert "READ_THIS_FIRST" in historian.build_prompt(
            period="p", multiple_comparisons={"verdict": "NOT EVIDENCE"},
            clv_by_bucket=[], calibration=[], suppression_audit=[],
            fee_reconciliation=[], current_config={},
        )

    def test_the_prompt_says_noise_cells_are_no_evidence(self):
        assert "it is no evidence" in historian.SYSTEM

    def test_an_empty_proposal_list_is_framed_as_success(self):
        assert "good week's work" in historian.SYSTEM

    def test_a_stored_report_is_unapproved(self, tmp_path):
        """Nothing takes effect until a human accepts it."""
        conn = db.init_db(tmp_path / "h.db")
        report = self._report(distinguishable=True, sample=800)
        historian.store_report(conn, report, created_ms=1)
        row = conn.execute("SELECT * FROM lessons").fetchone()
        conn.close()
        assert row["accepted_by_user"] is None
        assert row["proposed_config_diff"] is not None

    def test_a_report_with_no_proposals_stores_no_diff(self, tmp_path):
        conn = db.init_db(tmp_path / "h2.db")
        report = HistorianReport(
            period="p", lesson_title="Nothing yet",
            lesson_body="No bucket clears the noise guard.",
            evidence_read=["mart_multiple_comparisons"],
            findings_are_distinguishable_from_chance=False,
        )
        historian.store_report(conn, report, created_ms=1)
        row = conn.execute("SELECT * FROM lessons").fetchone()
        conn.close()
        assert row["proposed_config_diff"] is None
