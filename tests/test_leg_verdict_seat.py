"""The leg scout's own contract (#151, ADR 0186).

- **It says TAKE or PASS, and never a number.** `LegVerdict` is walked the
  same way `DeskBriefing` and `SharpTake` are. The prompt forbids a
  probability, a price, a line and a stake.
- **It writes for a beginner.** The plain-words rule is in the prompt and
  names the jargon it bans. The reason is capped, and an overrun is recorded
  as failed rather than clipped.
- **One leg is one metered call.** Affordability is checked before anything,
  the reserve row comes before the request, and every exit settles. A refusal
  spends nothing.
- **The seat never sees our fair percentage.** It is scored against the price,
  so it must not be built from our model of the price.

What this does not establish: that a verdict is right. That is the
pre-registered measurement's job
(`docs/measurements/2026-09-25-preregistration-scout-leg-verdicts.md`).
"""

from __future__ import annotations

import inspect
import typing

from pydantic import BaseModel as PydanticBase

from backend.agents import leg_verdict
from backend.agents.base import AgentConfig, CallUsage
from backend.agents.budget import AgentBudget
from backend.agents.leg_verdict import (
    LEG_VERDICT_MAX_SEARCHES,
    PLAIN_WORDS_RULE,
    REASON_MAX_CHARS,
    SYSTEM,
    LegVerdict,
    build_prompt,
    give_leg_verdict,
)
from backend.store import db

CONFIG = AgentConfig(api_key="test", model="claude-sonnet-5")
NOW = 1_790_400_000_000


class StubUsage:
    input_tokens = 900
    output_tokens = 120
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0

    class server_tool_use:  # noqa: N801 -- mirrors the SDK attribute
        web_search_requests = 2


class StubResponse:
    def __init__(self, parsed, *, usage=True):
        self.parsed_output = parsed
        self.stop_reason = "end_turn"
        self.stop_details = None
        self.usage = StubUsage() if usage else None


class StubMessages:
    def __init__(self, parsed=None, *, raises=False, conn=None):
        self._parsed = parsed
        self._raises = raises
        self._conn = conn
        self.calls: list[dict] = []
        self.rows_at_call: int | None = None

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._conn is not None:
            self.rows_at_call = self._conn.execute(
                "SELECT COUNT(*) AS c FROM agent_calls"
            ).fetchone()["c"]
        if self._raises:
            raise RuntimeError("down")
        return StubResponse(self._parsed)


class StubClient:
    def __init__(self, **kwargs):
        self.messages = StubMessages(**kwargs)


def _budget(tmp_path, *, daily=24, searches_daily=0, tokens_daily=0):
    conn = db.init_db(tmp_path / "lv.db")
    return conn, AgentBudget(
        conn, per_pass_budget=8, daily_budget=daily,
        searches_daily_budget=searches_daily, tokens_daily_budget=tokens_daily,
    )


def _prompt():
    return build_prompt(
        label="Chicago wins", side="yes", ask_display="Kalshi asks 43¢ for YES",
        event_title="Chicago at Washington", league="basketball_wnba",
        commence_iso="2026-09-26T23:00:00Z", briefing_text=None,
    )


async def _give(client, budget):
    return await give_leg_verdict(
        client, CONFIG, budget, ticker="KXTEST-1", side="yes",
        prompt=_prompt(), now_ms=NOW,
    )


class TestTheVerdictIsAWordNeverANumber:
    def test_the_verdict_schema_has_no_numeric_field(self):
        """Adding `confidence: float` to `LegVerdict` turns this red."""

        def leaves(annotation):
            args = typing.get_args(annotation)
            if not args:
                yield annotation
            for arg in args:
                yield from leaves(arg)

        for name, field in LegVerdict.model_fields.items():
            for leaf in leaves(field.annotation):
                if isinstance(leaf, type) and issubclass(leaf, PydanticBase):
                    raise AssertionError(f"{name}: nested models are not expected")
                if isinstance(leaf, str):
                    continue
                assert leaf not in (int, float, complex), name
                assert not isinstance(leaf, (int, float, complex)), name

    def test_the_verdict_is_take_or_pass_and_nothing_else(self):
        (annotation,) = [LegVerdict.model_fields["verdict"].annotation]
        assert set(typing.get_args(annotation)) == {"take", "pass"}

    def test_the_prompt_forbids_a_probability_price_line_or_stake(self):
        assert (
            "Never state a probability, a fair price, a line, a point spread, "
            "or how much to stake." in SYSTEM
        )

    def test_a_pass_must_name_a_concrete_fact(self):
        """The counterweight to HOUSE_CONTEXT's lean toward PASS."""
        assert "A PASS must name a concrete fact." in SYSTEM


class TestItWritesForABeginner:
    def test_the_prompt_asks_for_plain_everyday_words_for_a_beginner(self):
        assert PLAIN_WORDS_RULE in SYSTEM
        assert "beginner" in PLAIN_WORDS_RULE
        for jargon in ("CLV", "devig", "steam", "sharp money", "juice"):
            assert jargon in PLAIN_WORDS_RULE, jargon

    async def test_a_reason_over_the_length_cap_is_recorded_failed_not_clipped(
        self, tmp_path
    ):
        conn, budget = _budget(tmp_path)
        long = LegVerdict(verdict="pass", reason="x" * (REASON_MAX_CHARS + 1))
        result = await _give(StubClient(parsed=long), budget)
        assert result.status == "failed"
        assert result.verdict is None
        assert result.refusal_reason == "reason over length cap"
        row = conn.execute(
            "SELECT verdict, input_tokens FROM agent_calls"
        ).fetchone()
        assert row["verdict"] == "over_length"
        assert row["input_tokens"] == 900  # billed usage kept

    async def test_a_reason_at_the_cap_is_kept_whole(self, tmp_path):
        _, budget = _budget(tmp_path)
        exact = LegVerdict(verdict="take", reason="y" * REASON_MAX_CHARS)
        result = await _give(StubClient(parsed=exact), budget)
        assert result.status == "complete"
        assert result.verdict.reason == exact.reason


class TestOneLegIsOneMeteredCall:
    async def test_one_verdict_is_one_reserved_call_with_at_most_three_searches(
        self, tmp_path
    ):
        conn, budget = _budget(tmp_path)
        client = StubClient(
            parsed=LegVerdict(verdict="take", reason="Nothing new on either team."),
            conn=conn,
        )
        result = await _give(client, budget)
        assert result.status == "complete"
        assert len(client.messages.calls) == 1
        assert client.messages.rows_at_call == 1  # reserved BEFORE the request
        (tool,) = client.messages.calls[0]["tools"]
        assert tool["max_uses"] == LEG_VERDICT_MAX_SEARCHES == 3
        row = conn.execute(
            "SELECT agent, ticker, side, verdict, web_searches FROM agent_calls"
        ).fetchone()
        assert dict(row) == {
            "agent": "leg_verdict", "ticker": "KXTEST-1", "side": "yes",
            "verdict": "take", "web_searches": 2,
        }
        assert result.usage == CallUsage(900, 120, 2)

    async def test_an_unaffordable_leg_spends_nothing_and_names_the_ceiling(
        self, tmp_path
    ):
        conn, budget = _budget(tmp_path, daily=0)
        client = StubClient(parsed=LegVerdict(verdict="take", reason="ok"))
        result = await _give(client, budget)
        assert result.status == "refused"
        assert result.refusal_reason
        assert client.messages.calls == []
        assert conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"] == 0

    async def test_the_search_worst_case_is_checked_before_the_call(self, tmp_path):
        """A search ceiling with room for 2 refuses a seat that may search 3."""
        _, budget = _budget(tmp_path, searches_daily=2)
        client = StubClient(parsed=LegVerdict(verdict="take", reason="ok"))
        result = await _give(client, budget)
        assert result.status == "refused"
        assert client.messages.calls == []

    async def test_a_crashed_call_settles_null_usage_never_zero(self, tmp_path):
        conn, budget = _budget(tmp_path)
        result = await _give(StubClient(raises=True), budget)
        assert result.status == "failed"
        row = conn.execute(
            "SELECT verdict, input_tokens, output_tokens, web_searches "
            "FROM agent_calls"
        ).fetchone()
        assert row["verdict"] == "filed_nothing"
        assert row["input_tokens"] is None
        assert row["output_tokens"] is None
        assert row["web_searches"] is None


class TestTheSeatNeverSeesOurFairPercent:
    def test_the_prompt_builder_takes_no_fair_probability(self):
        params = set(inspect.signature(build_prompt).parameters)
        assert not {p for p in params if "fair" in p or "prob" in p}

    def test_the_prompt_carries_the_side_and_the_ask_in_words(self):
        text = _prompt()
        assert "YES" in text
        assert "Kalshi asks 43¢ for YES" in text
        assert "%" not in text


class TestTheLegVerdictsTable:
    def test_a_complete_row_must_carry_what_scoring_needs(self, tmp_path):
        import sqlite3

        import pytest

        conn = db.init_db(tmp_path / "t.db")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO leg_verdicts (ticker, side, requested_ms, "
                "completed_ms, status, verdict, reason, model, trigger) "
                "VALUES ('T', 'yes', 1, 2, 'complete', 'take', 'ok', 'm', "
                "'price_tap')"
            )

    def test_a_verdict_requested_after_kickoff_cannot_be_complete(self, tmp_path):
        import sqlite3

        import pytest

        conn = db.init_db(tmp_path / "t.db")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
                "commence_ms, requested_ms, completed_ms, status, verdict, "
                "reason, model, trigger) VALUES ('T', 'yes', 430, 100, 200, "
                "300, 'complete', 'take', 'ok', 'm', 'price_tap')"
            )

    def test_a_reason_over_the_cap_cannot_be_stored(self, tmp_path):
        import sqlite3

        import pytest

        conn = db.init_db(tmp_path / "t.db")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
                "commence_ms, requested_ms, completed_ms, status, verdict, "
                "reason, model, trigger) VALUES ('T', 'yes', 430, 900, 200, "
                "300, 'complete', 'take', ?, 'm', 'price_tap')",
                ("z" * (REASON_MAX_CHARS + 1),),
            )


def test_the_module_is_the_seat_the_adr_names():
    assert "ADR 0186" in (leg_verdict.__doc__ or "")
