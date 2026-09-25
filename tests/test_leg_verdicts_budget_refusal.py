"""#154: when the scouts' daily allowance is spent, `/api/leg-verdicts` says
so in plain words instead of passing `AgentBudget.refusal_reason`'s operator
text ("500000 of 500000 Anthropic tokens already recorded today") to the
card.

One translation site (`backend.api.routers.leg_verdicts._budget_refusal_message`),
before `_refusal_item`. `backend/agents/budget.py` is untouched -- the scout
desk and the server log still read its own text (`refusal_reason` logs it
before returning).

What these tests establish, one per claim in the ticket:

- A token-ceiling refusal served by the route carries no operator jargon.
- The "back in N hours" wording is correct for a `now` a known distance
  before the next day boundary, reading the budget's own `day_start_hour`
  rather than a hard-coded 10:00 UTC.
- A refusal that has nothing to do with the budget (a leg after kickoff)
  passes through byte-for-byte unchanged.

What this does not establish: that the translation reads well on the
`LegVerdicts.tsx` card -- `tests/test_leg_verdicts_ui.py` owns that half, and
this ticket does not touch that file unless the prefix reads wrong.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.agents.budget import AgentBudget
from backend.agents.leg_verdict import LEG_VERDICT_TOKEN_RESERVATION
from backend.api.routers import leg_verdicts as leg_verdicts_router
from backend.leg_verdicts import RUNNING_PATIENCE_MS
from backend.store import db as store
from backend.store.db import now_ms
from tests.test_leg_verdicts_store import _make_app, _seed_leg

# A day boundary hour deliberately unequal to the module's own default (10),
# so a test that passes only because the code reads `self.day_start_hour`
# (never a hard-coded 10:00 UTC) is the only way these go green.
_DAY_START_HOUR = 14


class TestATokenCeilingRefusalHasNoOperatorJargon:
    def test_the_served_reason_has_no_anthropic_no_token_no_long_digit_run(
        self, tmp_path, monkeypatch
    ):
        db_path = tmp_path / "route.db"
        conn = store.init_db(db_path)
        t = now_ms()
        _seed_leg(
            conn, ticker="KXTEST-TOKENS", commence_ms=t + 3_600_000,
        )
        # A single call already recorded today, with far more tokens than
        # the ceiling we are about to set -- trips the token brake
        # specifically, not the call-count or per-pass ones.
        conn.execute(
            "INSERT INTO agent_calls "
            "(called_ms, agent, model, input_tokens, output_tokens, "
            "web_searches) VALUES (?, 'scout', 'm', 900000, 0, 0)",
            (t,),
        )
        conn.commit()
        conn.close()

        monkeypatch.setenv("LEG_VERDICT_ENABLED", "true")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("AGENT_MAX_TOKENS_PER_DAY", "1000")
        client = TestClient(_make_app(db_path))

        resp = client.post(
            "/api/leg-verdicts",
            json={
                "trigger": "price_tap",
                "legs": [{"ticker": "KXTEST-TOKENS", "side": "yes"}],
            },
        )
        assert resp.status_code == 202
        leg = resp.json()["legs"][0]
        assert leg["state"] == "refused"
        reason = leg["refusal_reason"]
        assert reason
        assert "Anthropic" not in reason
        assert "token" not in reason.lower()
        assert re.search(r"\d{4,}", reason) is None
        # And it is the plain sentence, not just "not jargon."
        assert reason.startswith("The scouts have used today's allowance.")


class TestItNamesWhenTheScoutsAreBack:
    """Route-level, not just a unit call: `now` is pinned by monkeypatching
    `backend.store.db.now_ms` (the router calls `db.now_ms()` fresh each
    request, so this takes effect) and the day boundary is pinned by
    `ODDS_BUDGET_DAY_START_UTC_HOUR` -- deliberately not 10, the module
    default, so a hard-coded 10:00 UTC could not pass this test by accident.
    Routing the check through the actual call site, rather than only calling
    `_budget_refusal_message` directly, is what makes disabling the
    translation at that site turn this test red too.
    """

    def _fire(self, tmp_path, monkeypatch, *, now: datetime):
        db_path = tmp_path / "route.db"
        conn = store.init_db(db_path)
        _seed_leg(
            conn, ticker="KXTEST-HOURS", commence_ms=int(now.timestamp() * 1000) + 3_600_000,
        )
        # A single call already recorded "today" (relative to `now`), with
        # a daily-call ceiling of 1 -- trips the calls brake deterministically,
        # without needing to seed tokens/searches too.
        conn.execute(
            "INSERT INTO agent_calls "
            "(called_ms, agent, model, input_tokens, output_tokens, "
            "web_searches) VALUES (?, 'scout', 'm', 1, 0, 0)",
            (int(now.timestamp() * 1000),),
        )
        conn.commit()
        conn.close()

        monkeypatch.setenv("LEG_VERDICT_ENABLED", "true")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("AGENT_MAX_CALLS_PER_DAY", "1")
        monkeypatch.setenv(
            "ODDS_BUDGET_DAY_START_UTC_HOUR", str(_DAY_START_HOUR)
        )
        now_ms_ = int(now.timestamp() * 1000)
        monkeypatch.setattr(store, "now_ms", lambda: now_ms_)

        client = TestClient(_make_app(db_path))
        resp = client.post(
            "/api/leg-verdicts",
            json={
                "trigger": "price_tap",
                "legs": [{"ticker": "KXTEST-HOURS", "side": "yes"}],
            },
        )
        assert resp.status_code == 202
        leg = resp.json()["legs"][0]
        assert leg["state"] == "refused"
        return leg["refusal_reason"]

    def test_hours_until_reset_is_correct_and_reads_day_start_hour(
        self, tmp_path, monkeypatch
    ):
        boundary = datetime(
            2026, 1, 2, _DAY_START_HOUR, 0, 0, tzinfo=timezone.utc
        )
        # 3h01m before the next roll -> rounds UP to 4 hours.
        now = boundary - timedelta(hours=3, minutes=1)
        reason = self._fire(tmp_path, monkeypatch, now=now)
        assert "in about 4 hours" in reason

    def test_under_an_hour_says_so_not_zero_hours(self, tmp_path, monkeypatch):
        boundary = datetime(
            2026, 1, 2, _DAY_START_HOUR, 0, 0, tzinfo=timezone.utc
        )
        now = boundary - timedelta(minutes=30)
        reason = self._fire(tmp_path, monkeypatch, now=now)
        assert "in under an hour" in reason
        assert "0 hours" not in reason


class TestANonBudgetRefusalPassesThroughUnchanged:
    def test_a_leg_after_kickoff_is_the_raw_resolve_leg_text(
        self, tmp_path, monkeypatch
    ):
        db_path = tmp_path / "route.db"
        conn = store.init_db(db_path)
        t = now_ms()
        _seed_leg(
            conn, ticker="KXTEST-STARTED", commence_ms=t - 1_000,
        )
        conn.close()

        monkeypatch.setenv("LEG_VERDICT_ENABLED", "true")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        client = TestClient(_make_app(db_path))

        resp = client.post(
            "/api/leg-verdicts",
            json={
                "trigger": "price_tap",
                "legs": [{"ticker": "KXTEST-STARTED", "side": "yes"}],
            },
        )
        assert resp.status_code == 202
        leg = resp.json()["legs"][0]
        assert leg["state"] == "refused"
        # `resolve_leg`'s own text, byte-for-byte -- never touched by the
        # budget translation, which only fires for `budget.refusal_reason`.
        assert leg["refusal_reason"] == "This game has already started."


class TestInFlightVerdictsCountAgainstTheCeiling:
    """#156: a verdict's tokens and searches are recorded only when it
    settles, so without a reservation a burst of legs all read the same
    recorded total and all pass. Budget day 20260925 admitted 16 in 11
    seconds at 334,711 recorded and closed at 1,120,442 against 500,000.

    The background call is stubbed out, so every admitted leg stays
    `running` -- exactly the in-flight state the burst was in.
    """

    def _client(self, tmp_path, monkeypatch, *, tickers, env, now=None):
        db_path = tmp_path / "route.db"
        conn = store.init_db(db_path)
        t = now_ms() if now is None else now
        for ticker in tickers:
            _seed_leg(conn, ticker=ticker, commence_ms=t + 3_600_000)
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
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return db_path, TestClient(_make_app(db_path))

    @staticmethod
    def _post(client, tickers):
        resp = client.post(
            "/api/leg-verdicts",
            json={
                "trigger": "card_button",
                "legs": [{"ticker": t, "side": "yes"} for t in tickers],
            },
        )
        assert resp.status_code == 202
        return [leg["state"] for leg in resp.json()["legs"]]

    def test_one_burst_admits_only_what_the_token_ceiling_can_reserve(
        self, tmp_path, monkeypatch
    ):
        # 200,000 / 60,000 reserved each: legs see 0, 60K, 120K, 180K
        # reserved and pass; the fifth sees 240K and is refused.
        tickers = [f"KXTEST-BURST{i}" for i in range(8)]
        _, client = self._client(
            tmp_path, monkeypatch, tickers=tickers,
            env={"AGENT_MAX_TOKENS_PER_DAY": "200000"},
        )
        assert LEG_VERDICT_TOKEN_RESERVATION == 60_000
        states = self._post(client, tickers)
        assert states == ["pending"] * 4 + ["refused"] * 4

    def test_a_second_tap_while_those_run_is_refused(
        self, tmp_path, monkeypatch
    ):
        first = [f"KXTEST-FIRST{i}" for i in range(4)]
        _, client = self._client(
            tmp_path, monkeypatch, tickers=first + ["KXTEST-SECOND"],
            env={"AGENT_MAX_TOKENS_PER_DAY": "200000"},
        )
        assert self._post(client, first) == ["pending"] * 4
        assert self._post(client, ["KXTEST-SECOND"]) == ["refused"]

    def test_a_run_gone_quiet_stops_holding_budget(
        self, tmp_path, monkeypatch
    ):
        # Four `running` rows older than the patience window are a process
        # that died; they are not served as pending, so they must not hold
        # the day's budget either.
        tickers = [f"KXTEST-DEAD{i}" for i in range(4)]
        db_path, client = self._client(
            tmp_path, monkeypatch, tickers=tickers + ["KXTEST-FRESH"],
            env={"AGENT_MAX_TOKENS_PER_DAY": "200000"},
        )
        assert self._post(client, tickers) == ["pending"] * 4
        conn = store.open_db(db_path)
        conn.execute(
            "UPDATE leg_verdicts SET requested_ms = requested_ms - ?",
            (RUNNING_PATIENCE_MS + 1,),
        )
        conn.commit()
        conn.close()
        assert self._post(client, ["KXTEST-FRESH"]) == ["pending"]

    def test_searches_in_flight_count_too(self, tmp_path, monkeypatch):
        # 12 searches a day at 3 worst case each: legs 1-4 reserve 3, 6, 9,
        # 12 and pass; the fifth would need 15.
        tickers = [f"KXTEST-SEARCH{i}" for i in range(6)]
        _, client = self._client(
            tmp_path, monkeypatch, tickers=tickers,
            env={"AGENT_MAX_SEARCHES_PER_DAY": "12"},
        )
        assert self._post(client, tickers) == ["pending"] * 4 + ["refused"] * 2


class TestAnUnreservedCallerIsUnchanged:
    def test_reserved_tokens_defaults_to_zero(self, tmp_path):
        conn = store.init_db(tmp_path / "b.db")
        budget = AgentBudget(
            conn,
            daily_budget=100,
            per_pass_budget=100,
            tokens_daily_budget=1000,
            searches_daily_budget=0,
        )
        t = now_ms()
        conn.execute(
            "INSERT INTO agent_calls (called_ms, agent, model, input_tokens, "
            "output_tokens, web_searches) VALUES (?, 'scout', 'm', 999, 0, 0)",
            (t,),
        )
        conn.commit()
        assert budget.refusal_reason(1, t) is None
        assert budget.refusal_reason(1, t, reserved_tokens=1) is not None
