"""Buying one fixture's alternate spreads/totals by hand (#303 steps 4-5).

Joe's answer on #304: when he checks a friend's parlay, the desk buys that
game's other lines so a leg off the books' main number can be priced. This
file pins the spend half: the request kind, its ceilings, what the planner
charges for it, and what the runner calls.

What this does not establish
-----------------------------
- That the vendor returns two-sided alternate lines for any given game. One
  NCAAF event did (docs/measurements/2026-10-03-ncaaf-alternate-lines-are-two-
  sided.md, n = 1); `backend/alt_lines.py` counts the books it has to drop.
- That the check route submits these requests, or that the screen words them.
  That is #303 step 6.
- That `fetch_props` parses and stores the alternate keys. That is #305, and
  this file's runner test uses a fake client that returns nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.odds import ondemand
from backend.odds.budget import CreditBudget, sweep_cost
from backend.odds.timing import (
    ALT_LINE_MARKETS,
    MANUAL,
    ManualRefresh,
    decide_sweeps,
    last_sweep_by_sport,
)
from backend.store import db

HOUR = 3_600_000
NOW = int(datetime(2026, 10, 3, 18, 0, tzinfo=timezone.utc).timestamp() * 1000)
TEAM_COST = 3
ALT_COST = 2


@pytest.fixture
def inbox(tmp_path):
    return tmp_path / "inbox.json"


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "alt.db")
    yield c
    c.close()


def submit(inbox, **kwargs):
    defaults = dict(
        sport_key="americanfootball_ncaaf",
        odds_event_id="ev1",
        now_ms=NOW,
        estimated_credits=ALT_COST,
        budget_refusal=None,
        kind=ondemand.KIND_ALT_LINES,
    )
    return ondemand.submit(inbox, **{**defaults, **kwargs})


class TestTheAltRequestHasItsOwnCooldownAndCeiling:
    def test_alt_request_has_its_own_cooldown_and_ceiling(self, inbox):
        assert submit(inbox).accepted
        again = submit(inbox, now_ms=NOW + 30_000)
        assert not again.accepted and again.retry_after_ms > 0

    def test_an_alt_buy_does_not_cool_down_a_props_tap_on_the_same_fixture(self, inbox):
        assert submit(inbox).accepted
        props = submit(
            inbox, kind=ondemand.KIND_TEAM, estimated_credits=TEAM_COST + 20,
            now_ms=NOW + 1_000,
        )
        assert props.accepted, props.detail

    def test_a_different_fixture_is_a_different_purchase(self, inbox):
        assert submit(inbox).accepted
        assert submit(inbox, odds_event_id="ev2", now_ms=NOW + 1_000).accepted

    def test_the_alt_sub_ceiling_refuses_before_the_manual_slice_does(self, inbox):
        for i in range(15):  # 15 x 2 = the 30 allowed
            assert submit(inbox, odds_event_id=f"ev{i}", now_ms=NOW + i).accepted
        refused = submit(inbox, odds_event_id="ev99", now_ms=NOW + 100)
        assert not refused.accepted
        assert "30" in refused.detail and "checked parlays" in refused.detail
        # The team tap still has the rest of the 150.
        assert submit(
            inbox, kind=ondemand.KIND_TEAM, odds_event_id=None,
            estimated_credits=TEAM_COST, now_ms=NOW + 200,
        ).accepted

    def test_alt_spend_counts_inside_the_manual_slice_not_beside_it(self, inbox):
        assert submit(inbox, kind=ondemand.KIND_TEAM, odds_event_id=None,
                      estimated_credits=149).accepted
        refused = submit(inbox, now_ms=NOW + 1_000)
        assert not refused.accepted
        assert "150" in refused.detail

    def test_an_alt_request_with_no_fixture_is_refused_outright(self, inbox):
        with pytest.raises(ValueError):
            submit(inbox, odds_event_id=None)

    def test_entries_written_before_303_decode_as_team_taps(self, inbox):
        inbox.write_text(
            '[{"sport_key": "baseball_mlb", "odds_event_id": null, '
            '"requested_ms": %d, "estimated_credits": 3}]' % NOW,
            encoding="utf-8",
        )
        [req] = ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=0)
        assert req.kind == ondemand.KIND_TEAM

    def test_the_kind_survives_the_round_trip_through_the_file(self, inbox):
        submit(inbox)
        [req] = ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=0)
        assert req.kind == ondemand.KIND_ALT_LINES and req.odds_event_id == "ev1"

    def test_an_unknown_kind_in_the_file_is_dropped(self, inbox):
        inbox.write_text(
            '[{"sport_key": "x", "odds_event_id": "e", "requested_ms": %d, '
            '"estimated_credits": 2, "kind": "everything"}]' % NOW,
            encoding="utf-8",
        )
        assert ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=0) == []


class TestThePlannerChargesAltMarketsOnly:
    def _decide(self, conn, manual, *, daily=600, alt_line_cost=ALT_COST):
        return decide_sweeps(
            conn,
            in_scope={"americanfootball_ncaaf": NOW + 5 * HOUR},
            budget=CreditBudget(conn, daily_budget=daily),
            cost=TEAM_COST,
            now_ms=NOW,
            max_odds_age_ms=900_000,
            prop_cost_per_event=20,
            allow_bootstrap=False,
            manual=manual,
            alt_line_cost=alt_line_cost,
        )

    def test_alt_buy_costs_alt_markets_only(self, conn):
        decision = self._decide(conn, [ManualRefresh(
            sport_key="americanfootball_ncaaf", odds_event_id="ev1", alt_lines=True)])
        [firing] = decision.fire
        assert firing.trigger == MANUAL
        assert firing.cost == ALT_COST and firing.projected_total_cost == ALT_COST
        assert firing.alt_line_event_ids == ("ev1",)
        assert firing.prop_event_ids == ()
        assert firing.slot is None

    def test_an_alt_buy_and_a_team_tap_for_one_sport_are_both_served(self, conn):
        decision = self._decide(conn, [
            ManualRefresh(sport_key="americanfootball_ncaaf", odds_event_id="ev1", alt_lines=True),
            ManualRefresh(sport_key="americanfootball_ncaaf"),
        ])
        assert sorted(f.cost for f in decision.fire) == [ALT_COST, TEAM_COST]

    def test_the_day_refuses_an_alt_buy_it_cannot_afford(self, conn):
        decision = self._decide(
            conn,
            [ManualRefresh(sport_key="americanfootball_ncaaf", odds_event_id="ev1", alt_lines=True)],
            daily=1,
        )
        assert decision.fire == ()

    def test_no_configured_cost_refuses_rather_than_buying_free(self, conn):
        decision = self._decide(
            conn,
            [ManualRefresh(sport_key="americanfootball_ncaaf", odds_event_id="ev1", alt_lines=True)],
            alt_line_cost=0,
        )
        assert decision.fire == ()

    def test_the_cost_is_two_markets_at_the_deployed_ten_books(self):
        books = ["b%d" % i for i in range(10)]
        assert sweep_cost(ALT_LINE_MARKETS, ["us"], books) == 2


class TestTheRunnerServesItAsAManualPerEventCall:
    async def test_alt_buy_is_not_a_served_sweep(self, conn):
        from backend.config import OddsConfig
        from backend.runner import fetch_and_store_odds

        calls = []

        class FakeOdds:
            def __init__(self, budget):
                self.budget = budget

            async def fetch_odds(self, sport_key, *, now_ms, trigger=None):
                raise AssertionError("an alt-line buy must not buy the team sweep")

            async def fetch_props(self, sport_key, odds_event_ids, *, now_ms,
                                  markets=None, regions=None, trigger=None):
                calls.append((sport_key, list(odds_event_ids), list(markets), trigger))
                self.budget.record(
                    called_ms=now_ms,
                    endpoint=f"/sports/{sport_key}/events/{odds_event_ids[0]}/odds",
                    cost=ALT_COST, sport_key=sport_key, trigger=trigger,
                )
                return []

        budget = CreditBudget(conn, daily_budget=600)
        await fetch_and_store_odds(
            conn, FakeOdds(budget), budget, events=[],
            config=OddsConfig(
                api_key="x", base_url="https://example.invalid",
                markets=["h2h", "spreads", "totals"], regions=["us"],
                bookmakers=["b%d" % i for i in range(10)],
                daily_credit_budget=600,
            ),
            now=NOW, max_odds_age_ms=900_000, allow_bootstrap=False,
            manual=[ManualRefresh(sport_key="americanfootball_ncaaf",
                                  odds_event_id="ev1", alt_lines=True)],
        )
        assert calls == [("americanfootball_ncaaf", ["ev1"], list(ALT_LINE_MARKETS), "manual")]
        assert last_sweep_by_sport(conn, since_ms=NOW - HOUR) == {}, (
            "an alt-line buy bought no main line; counting it as the sport's "
            "sweep would cost the next window its opening call"
        )
