"""#363: a budget refusal Joe can see names WHICH daily cap refused it (tokens,
web searches or calls) and when the day resets in Pacific time, in plain
words, never a config name.

Lesson 2026-10-10: the reason stored for the record (names the dial) and the
sentence shown to the operator are different strings with different tests.
`AgentBudget.refusal_reason` is untouched here; these tests read the SERVED
sentence from the real routes.

What this does not establish: how the sentence looks on the phone
(`tests/test_leg_verdicts_ui.py` owns the card), nor the Odds API credit
budget's refusal, which is a different budget.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.routers import leg_verdicts as leg_verdicts_router
from backend.api.routers.game import plain_budget_refusal
from backend.store import db as store
from tests.test_leg_verdicts_store import _make_app, _seed_leg
from tests.test_scout_api import AUTH, live_app, post, scout_db  # noqa: F401

# Not the module default (10), so a literal could not pass by accident.
_DAY_START_HOUR = 14
# 2026-01-02 08:00 UTC is 00:00 PST; the roll at 14:00 UTC is 6:00 AM PT.
_NOW = datetime(2026, 1, 2, 8, 0, 0, tzinfo=timezone.utc)
_NOW_MS = int(_NOW.timestamp() * 1000)
_RESET_CLAUSE = "They're back at 6:00 AM PT, in about 6 hours."
_CONFIG_NAME = re.compile(r"AGENT_MAX|SCOUT_|_PER_DAY|_PER_PASS")


def _leg_refusal(tmp_path, monkeypatch, *, env: dict, seed_tokens: int = 0):
    db_path = tmp_path / "route.db"
    conn = store.init_db(db_path)
    _seed_leg(conn, ticker="KXTEST-CAP", commence_ms=_NOW_MS + 3_600_000)
    if seed_tokens:
        conn.execute(
            "INSERT INTO agent_calls (called_ms, agent, model, input_tokens, "
            "output_tokens, web_searches) VALUES (?, 'scout', 'm', ?, 0, 0)",
            (_NOW_MS, seed_tokens),
        )
        conn.commit()
    conn.close()

    async def _no_call(*args, **kwargs):
        return None

    monkeypatch.setattr(leg_verdicts_router, "_run_leg_verdict", _no_call)
    monkeypatch.setenv("LEG_VERDICT_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MAX_CALLS_PER_DAY", "100")
    monkeypatch.setenv("AGENT_MAX_CALLS_PER_PASS", "100")
    monkeypatch.setenv("AGENT_MAX_SEARCHES_PER_DAY", "1000")
    monkeypatch.setenv("AGENT_MAX_TOKENS_PER_DAY", "100000000")
    monkeypatch.setenv("ODDS_BUDGET_DAY_START_UTC_HOUR", str(_DAY_START_HOUR))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(store, "now_ms", lambda: _NOW_MS)
    resp = TestClient(_make_app(db_path)).post(
        "/api/leg-verdicts",
        json={
            "trigger": "check_button",
            "legs": [{"ticker": "KXTEST-CAP", "side": "yes"}],
        },
    )
    assert resp.status_code == 202
    return resp.json()["legs"][0]


class TestALegVerdictRefusalNamesItsCapAndTheResetClock:
    def test_a_token_cap_refusal_says_tokens_and_when_it_resets(
        self, tmp_path, monkeypatch
    ):
        leg = _leg_refusal(
            tmp_path, monkeypatch,
            env={"AGENT_MAX_TOKENS_PER_DAY": "1000"}, seed_tokens=900_000,
        )
        assert leg["state"] == "refused"
        words = leg["refusal_reason"]
        assert "token allowance" in words
        assert "search" not in words
        assert words.endswith(_RESET_CLAUSE)
        assert not _CONFIG_NAME.search(words)
        assert "Anthropic" not in words
        assert re.search(r"\d{4,}", words) is None

    def test_a_search_cap_refusal_says_searches_and_when_it_resets(
        self, tmp_path, monkeypatch
    ):
        # One leg reserves 3 searches; a cap of 2 refuses it with no spend.
        leg = _leg_refusal(
            tmp_path, monkeypatch, env={"AGENT_MAX_SEARCHES_PER_DAY": "2"}
        )
        assert leg["state"] == "refused"
        words = leg["refusal_reason"]
        assert "web-search allowance" in words
        assert "token" not in words
        assert words.endswith(_RESET_CLAUSE)
        assert not _CONFIG_NAME.search(words)

    def test_headroom_produces_no_refusal_sentence(self, tmp_path, monkeypatch):
        # Positive control: same route, same input, caps with room.
        leg = _leg_refusal(tmp_path, monkeypatch, env={})
        assert leg["state"] == "pending"
        assert leg["refusal_reason"] is None


class TestTheScoutDeskTapRefusalNamesItsCap:
    @pytest.mark.asyncio
    async def test_the_429_detail_is_plain_words_with_the_reset_clock(
        self, live_app, scout_db, monkeypatch  # noqa: F811
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("AGENT_MAX_CALLS_PER_DAY", "1")
        monkeypatch.setenv("ODDS_BUDGET_DAY_START_UTC_HOUR", str(_DAY_START_HOUR))
        response = await post(live_app, "/api/scout/KXTEST-LINKED", headers=AUTH)
        assert response.status_code == 429
        detail = response.json()["detail"]
        assert detail.startswith("The scouts have used today's call allowance.")
        assert re.search(r"back at \d{1,2}:\d{2} [AP]M PT", detail)
        assert not _CONFIG_NAME.search(detail)


class TestThePlainFunction:
    def test_a_stored_refusal_from_an_earlier_day_carries_no_clock(self):
        reason = "5 of 4 Anthropic tokens already recorded today"
        yesterday = _NOW_MS - 30 * 3_600_000
        words = plain_budget_refusal(
            reason, _NOW_MS, _DAY_START_HOUR, stored_ms=yesterday
        )
        assert words == "The scouts have used today's token allowance."

    def test_the_per_pass_ceiling_carries_no_daily_clock(self):
        words = plain_budget_refusal(
            "one pass may make at most 8 Anthropic calls, and this pass "
            "asked for 9",
            _NOW_MS,
            _DAY_START_HOUR,
        )
        assert "PT" not in words
        assert "AGENT_MAX" not in words
