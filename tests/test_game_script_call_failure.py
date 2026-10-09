"""#309: a failed call or failed search is a machine failure, named and retried.

It was stored as the scout's judgement (`skipped`, a done status, or
`refused_invalid` "the call returned nothing") and shown as "No clean story".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend import game_script_watch as gsw
from backend.agents import game_script
from backend.agents.game_script import CardOutput, build_card
from backend.api.routers.game import no_card_line
from backend.game_script_watch import BUILD, Fixture, WatchBudget, decide
from tests.test_game_script_card import (
    CONFIG, GAME, KICKOFF, NOW, StubResponse, StubUsage, _conn_budget, _listing, _row,
)

H = 3_600_000


class _ZeroSearchUsage(StubUsage):
    class server_tool_use:  # noqa: N801
        web_search_requests = 0


class _Messages:
    def __init__(self, exc=None, parsed=None, usage=None):
        self._exc, self._parsed, self._usage = exc, parsed, usage

    async def parse(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        resp = StubResponse(self._parsed)
        if self._usage is not None:
            resp.usage = self._usage
        return resp


async def _run(tmp_path, messages):
    conn, budget = _conn_budget(tmp_path)
    result = await build_card(
        conn, SimpleNamespace(messages=messages), CONFIG, budget,
        game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
        game_title="Atlanta at Pittsburgh", kickoff_iso="2026-09-13T17:00Z",
        listing=_listing(), now_ms=NOW,
    )
    return conn, result


def _schema_error():
    try:
        CardOutput.model_validate({"skip": "not a bool", "legs": 3})
    except ValidationError as exc:
        return exc
    raise AssertionError("the probe payload should not validate")


def _roomy():
    return WatchBudget(tokens_today=0, tokens_ceiling=10_000_000,
                       searches_today=0, searches_ceiling=1000)


class TestAFailedSearchIsRetryable:
    async def test_a_zero_search_skip_is_not_in_a_done_status(self, tmp_path):
        parsed = CardOutput(skip=True, reason="Nothing to say.")
        conn, result = await _run(
            tmp_path, _Messages(parsed=parsed, usage=_ZeroSearchUsage())
        )
        row = _row(conn, result.card_id)
        assert row["status"] not in gsw.DONE_STATUSES
        assert row["reason"].startswith(game_script.CALL_FAILED_PREFIX)
        assert "search" in row["reason"]

    async def test_decide_builds_that_game_on_the_next_pass(self, tmp_path):
        parsed = CardOutput(skip=True, reason="Nothing to say.")
        conn, _ = await _run(
            tmp_path, _Messages(parsed=parsed, usage=_ZeroSearchUsage())
        )
        cards = [dict(r) for r in conn.execute(
            "SELECT game_event_ticker, status, reason, built_ms FROM game_script_cards"
        ).fetchall()]
        later = NOW + 2 * H  # past the backoff
        acts = decide(later, [Fixture(GAME, "nfl", later + H)], cards, _roomy())
        assert [(a.kind, a.game_event_ticker) for a in acts] == [(BUILD, GAME)]

    async def test_a_search_error_reason_is_a_failure_even_with_searches_counted(
        self, tmp_path
    ):
        parsed = CardOutput(skip=True, reason="Search tool was unavailable for this game.")
        conn, result = await _run(tmp_path, _Messages(parsed=parsed))
        assert result.status == "refused_invalid"

    async def test_a_skip_after_real_searches_stays_the_scouts_judgement(self, tmp_path):
        parsed = CardOutput(skip=True, reason="Too little news.")
        conn, result = await _run(tmp_path, _Messages(parsed=parsed))
        assert result.status == "skipped"


class TestTheFailureKindIsNamed:
    async def test_the_schema_mismatch_path_stores_a_reason_naming_it(self, tmp_path):
        conn, result = await _run(tmp_path, _Messages(exc=_schema_error()))
        assert result.status == "refused_invalid"
        reason = _row(conn, result.card_id)["reason"]
        assert reason.startswith(game_script.CALL_FAILED_PREFIX)
        assert "schema" in reason

    async def test_a_transport_error_is_named_apart_from_a_schema_mismatch(self, tmp_path):
        conn, result = await _run(tmp_path, _Messages(exc=RuntimeError("reset")))
        reason = _row(conn, result.card_id)["reason"]
        assert "errored" in reason and "schema" not in reason

    async def test_the_reason_carries_the_exception_class_or_pydantic_error_types(
        self, tmp_path
    ):
        conn, result = await _run(tmp_path, _Messages(exc=_schema_error()))
        assert "ValidationError:" in _row(conn, result.card_id)["reason"]
        conn, result = await _run(
            tmp_path / "b",
            _Messages(exc=RuntimeError("Error code: 400 credit balance is too low")),
        )
        reason = _row(conn, result.card_id)["reason"]
        assert "RuntimeError: Error code: 400 credit balance is too low" in reason

    async def test_a_lost_usage_settles_null_not_zero(self, tmp_path):
        conn, result = await _run(tmp_path, _Messages(exc=_schema_error()))
        got = conn.execute(
            "SELECT input_tokens FROM agent_calls WHERE id = ?", (result.agent_call_id,)
        ).fetchone()
        assert got[0] is None


class TestTheScreenDoesNotSpeakAsTheScout:
    @pytest.mark.parametrize("reason", [
        game_script.call_failed_reason("search_failed", detail="Search tool was unavailable"),
        game_script.call_failed_reason("schema_mismatch"),
    ])
    def test_no_card_line_says_the_call_failed(self, reason):
        line = no_card_line({"status": "refused_invalid", "reason": reason})
        assert not line.startswith("No clean story")
        assert line.startswith("No card yet") and "retried" in line

    def test_a_scouts_own_refusal_still_reads_as_no_clean_story(self):
        line = no_card_line({"status": "refused_invalid", "reason": "the card has 4 legs"})
        assert line == "No clean story: the card has 4 legs"


class TestARetryIsNotATightLoop:
    FAIL = game_script.call_failed_reason("no_output")

    def _row(self, built_ms, reason=None):
        return {"game_event_ticker": "A", "status": "refused_invalid",
                "reason": reason or self.FAIL, "built_ms": built_ms}

    def _fx(self):
        return [Fixture("A", "americanfootball_nfl", NOW + 3 * H)]

    def test_a_failure_inside_the_backoff_is_not_retried_yet(self):
        assert decide(NOW, self._fx(), [self._row(NOW - 600_000)], _roomy()) == []

    def test_a_failure_past_the_backoff_is_retried(self):
        acts = decide(NOW, self._fx(), [self._row(NOW - 2 * H)], _roomy())
        assert [a.kind for a in acts] == [BUILD]

    def test_a_game_that_keeps_failing_stops_at_the_cap(self):
        rows = [self._row(NOW - (5 + i) * H) for i in range(3)]
        assert gsw.MAX_FAILED_ATTEMPTS <= 3
        assert decide(NOW, self._fx(), rows, _roomy()) == []

    def test_a_validator_refused_card_is_paced_like_a_failed_call(self):
        # Billed in full, and a rule the model trips once it can trip every
        # pass: an hour's backoff, and the same cap (session 82).
        invalid = "the card has 4 legs; it needs 2 to 3"
        assert decide(NOW, self._fx(), [self._row(NOW - 60_000, invalid)], _roomy()) == []
        rows = [self._row(NOW - (5 + i) * H, invalid) for i in range(3)]
        assert decide(NOW, self._fx(), rows, _roomy()) == []
        acts = decide(NOW, self._fx(), [self._row(NOW - 2 * H, invalid)], _roomy())
        assert [a.kind for a in acts] == [BUILD]

    def test_the_outages_legacy_rows_do_not_cap_a_game(self):
        rows = [self._row(NOW - 60_000 * (i + 1), "the call returned nothing")
                for i in range(10)]
        acts = decide(NOW, self._fx(), rows, _roomy())
        assert [a.kind for a in acts] == [BUILD]


class _RecordingMessages(_Messages):
    def __init__(self):
        super().__init__(exc=RuntimeError("stop after the request is recorded"))
        self.sent = None

    async def parse(self, **kwargs):
        self.sent = kwargs
        return await super().parse(**kwargs)


class TestTheCardIsNotCutOffAtTheOldCap:
    """#338: 3000 output tokens cut finished research off at the final answer."""

    async def test_the_card_call_sends_the_named_output_cap(self, tmp_path):
        messages = _RecordingMessages()
        await _run(tmp_path, messages)
        assert messages.sent["max_tokens"] == game_script.GAME_SCRIPT_MAX_OUTPUT_TOKENS

    def test_the_cap_is_at_least_the_scout_staffs(self):
        assert game_script.GAME_SCRIPT_MAX_OUTPUT_TOKENS >= 6000
