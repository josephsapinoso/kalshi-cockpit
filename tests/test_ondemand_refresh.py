"""The refresh button: what a tap costs, what refuses it, and what it must not break.

The behaviour under test exists because of a clock, not a price.
`api/routes._live_ages` re-checks the stored consensus against *now* on every
read, so `actionable` goes false `MAX_ODDS_AGE_S` after the sweep that priced
the row. The rolling refresh (ADR 0030) holds that open across a planned kickoff
cluster and nothing else, so a slate opened two hours before first pitch is
struck through in full and correctly. This is the path by which a person can buy
their way out of that.

What these tests do NOT establish
---------------------------------
**That a refreshed row is a bettable row.** Every assertion here is about
freshness, credits and scheduling. `actionable` has been 0 for the life of the
record across every market type, and a fresh price is still a price with no edge
in it. Nothing here is evidence about edge and none of it may be quoted as such.

**That the aggregator's numbers actually move.** `odds_age_ms` is measured from
The Odds API's own `last_update`, which is their scrape stamp and not our fetch
time. The cooldown below is sized on the belief that two calls a minute apart
return the same quotes; that belief is *unmeasured*, and these tests pin the
cooldown's mechanics rather than its correctness.

**That the file survives a hostile writer.** The inbox is single-writer by
construction -- the API writes, the runner only reads -- and the tests exercise
malformed content, not concurrent writers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.odds import ondemand
from backend.odds.budget import CreditBudget, sweep_cost
from backend.odds.timing import (
    MANUAL,
    REFRESH,
    SCHEDULED,
    ManualRefresh,
    decide_sweeps,
    firing_for_slot,
    last_sweep_by_sport,
    plan_sweep_slots,
    refresh_interval_ms,
    upcoming_fixtures_by_sport,
)
from backend.store import db

MIN = 60_000
HOUR = 3_600_000


def ms(iso: str) -> int:
    return int(
        datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000
    )


# 18:00Z, inside the 10:00Z budget day, hours before an evening slate.
NOW = ms("2026-08-07T18:00:00")
MAX_ODDS_AGE_MS = 900_000
TEAM_COST = 6
PROP_COST = 20


@pytest.fixture
def inbox(tmp_path):
    return tmp_path / "inbox.json"


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "ondemand.db")
    yield c
    c.close()


def add_fixture(
    conn,
    *,
    sport_key="baseball_mlb",
    odds_event_id="e1",
    commence_ms=NOW + 3 * HOUR,
    fetched_ms=NOW,
):
    for book in ("pinnacle", "draftkings"):
        for outcome in ("Home", "Away"):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
                "sport_key, odds_event_id, commence_ms, home_team, away_team, "
                "bookmaker, market, outcome_name, price_decimal) "
                "VALUES (?, ?, ?, ?, ?, 'Home', 'Away', ?, 'h2h', ?, 2.0)",
                (fetched_ms, None, sport_key, odds_event_id, commence_ms, book, outcome),
            )
    conn.commit()


def accept(inbox, **kwargs):
    """Submit with the ceilings wide open, for tests about something else."""
    defaults = dict(
        sport_key="baseball_mlb",
        odds_event_id=None,
        now_ms=NOW,
        estimated_credits=TEAM_COST,
        budget_refusal=None,
    )
    return ondemand.submit(inbox, **{**defaults, **kwargs})


class TestWhatATapCosts:
    """The price is stated before it is spent, and props are the whole of it."""

    def test_a_team_refresh_is_one_sweep(self):
        assert (
            ondemand.manual_cost(
                team_cost=TEAM_COST, prop_cost_per_event=PROP_COST, odds_event_id=None
            )
            == TEAM_COST
        )

    def test_a_prop_refresh_includes_the_team_call_that_finds_the_game(self):
        """26, not 20.

        `fetch_and_store_props` is only ever reached from a *served* team sweep,
        and the fixture list it filters comes from that sweep's slate. Quoting
        20 would understate the tap by the one call that makes it possible.
        """
        assert (
            ondemand.manual_cost(
                team_cost=TEAM_COST, prop_cost_per_event=PROP_COST, odds_event_id="e1"
            )
            == TEAM_COST + PROP_COST
        )

    def test_the_cost_is_the_deployed_market_and_region_lists(self):
        """Derived, never a literal 6.

        `sweep_cost` is `markets x regions`. Writing 6 here would pass while the
        deployed config said otherwise, which is exactly how the prop bill was
        estimated at 10 a fixture and came in at 20.
        """
        assert sweep_cost(["h2h", "spreads", "totals"], ["us", "eu"]) == 6
        assert sweep_cost(["h2h"], ["us"]) == 1


class TestTheCooldown:
    def test_a_second_tap_on_the_same_key_is_refused_and_says_when(self, inbox):
        first = accept(inbox)
        assert first.accepted

        second = accept(inbox, now_ms=NOW + 30_000)
        assert not second.accepted
        assert second.retry_after_ms == ondemand.DEFAULT_COOLDOWN_MS - 30_000
        assert "30s ago" in second.detail

    def test_the_cooldown_clears(self, inbox):
        assert accept(inbox).accepted
        assert accept(inbox, now_ms=NOW + ondemand.DEFAULT_COOLDOWN_MS).accepted

    def test_a_different_fixtures_props_are_not_blocked_by_the_first(self, inbox):
        """One tap on one game must not silence the board.

        The cooldown key is `sport|fixture`, so a slate-wide team refresh and a
        per-fixture prop refresh are different purchases. Sharing a key would
        mean refreshing one game's props locked every other row for two minutes.
        """
        assert accept(
            inbox, odds_event_id="e1", estimated_credits=TEAM_COST + PROP_COST
        ).accepted
        assert accept(
            inbox,
            odds_event_id="e2",
            estimated_credits=TEAM_COST + PROP_COST,
            now_ms=NOW + 1_000,
        ).accepted

    def test_a_team_refresh_is_not_blocked_by_a_prop_refresh(self, inbox):
        assert accept(
            inbox, odds_event_id="e1", estimated_credits=TEAM_COST + PROP_COST
        ).accepted
        assert accept(inbox, now_ms=NOW + 1_000).accepted

    def test_a_refused_tap_writes_nothing(self, inbox):
        """The cooldown must not restart itself.

        A refusal that rewrote the file would push the retry further out on
        every impatient tap, so the button would get *further* from working the
        more it was pressed.
        """
        accept(inbox)
        before = inbox.read_text(encoding="utf-8")
        accept(inbox, now_ms=NOW + 30_000)
        assert inbox.read_text(encoding="utf-8") == before


class TestTheManualDailyCeiling:
    """Taps must not eat the schedule, which is what builds the record."""

    def test_it_refuses_once_the_days_taps_reach_the_slice(self, inbox):
        # Five prop refreshes at 26 is 130; a sixth would be 156 against 150.
        for i in range(5):
            assert accept(
                inbox,
                odds_event_id=f"e{i}",
                estimated_credits=TEAM_COST + PROP_COST,
                now_ms=NOW + i * 1_000,
            ).accepted

        refused = accept(
            inbox,
            odds_event_id="e9",
            estimated_credits=TEAM_COST + PROP_COST,
            now_ms=NOW + 9_000,
        )
        assert not refused.accepted
        assert "130 of 150" in refused.detail
        # Not a cooldown, so no countdown: a ceiling does not clear on a timer
        # and a UI counting down to it would be lying.
        assert refused.retry_after_ms == 0

    def test_yesterdays_taps_do_not_count_against_today(self, inbox):
        """The budget day rolls at 10:00Z, not at midnight.

        Counting on the calendar day would put a West Coast night's taps in the
        same bucket as the following afternoon's -- the same reason
        `CreditBudget` uses this boundary.
        """
        for i in range(5):
            assert accept(
                inbox,
                odds_event_id=f"e{i}",
                estimated_credits=TEAM_COST + PROP_COST,
                now_ms=NOW + i * 1_000,
            ).accepted

        # 10:00Z the next morning: a new budget day, and past every cooldown.
        tomorrow = ms("2026-08-08T10:00:00")
        assert accept(
            inbox,
            odds_event_id="e0",
            estimated_credits=TEAM_COST + PROP_COST,
            now_ms=tomorrow,
        ).accepted

    def test_the_ceiling_is_charged_on_acceptance_not_on_service(self, inbox):
        """Over-counting is the safe direction and is deliberate.

        The runner may still refuse a served tap on budget. Charging at
        acceptance refuses a tap that would have fit; charging at service would
        authorise spend that is already gone.
        """
        accept(inbox, estimated_credits=ondemand.DEFAULT_MANUAL_DAILY_CREDITS)
        refused = accept(inbox, sport_key="basketball_wnba", now_ms=NOW + 1_000)
        assert not refused.accepted
        assert "reserved for them today" in refused.detail


class TestTheRealBudgetStillDecides:
    def test_a_budget_refusal_is_passed_through_in_its_own_words(self, inbox):
        refused = accept(inbox, budget_refusal="the day is spent")
        assert not refused.accepted
        assert "the day is spent" in refused.detail

    def test_the_budget_is_checked_after_the_cooldown(self, inbox):
        """Cheapest and most decisive first, matching `/api/orders`.

        A key still cooling down must not reach the budget read at all -- the
        answer is the same either way, and the cooldown's is the one a person
        can act on.
        """
        accept(inbox)
        refused = accept(inbox, now_ms=NOW + 1_000, budget_refusal="the day is spent")
        assert not refused.accepted
        assert "the day is spent" not in refused.detail
        assert refused.retry_after_ms > 0


class TestTakingRequests:
    def test_only_requests_newer_than_the_watermark_come_back(self, inbox):
        accept(inbox)
        assert ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=NOW - 1) != []
        assert ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=NOW) == []

    def test_a_stale_request_is_dropped_rather_than_served_late(self, inbox):
        """Someone who tapped, waited and put the phone down is not waiting.

        Serving it spends credits to refresh a screen that has gone dark, and
        the TTL is what makes a runner restart safe to reason about.
        """
        accept(inbox)
        late = NOW + ondemand.DEFAULT_TTL_MS + 1
        assert ondemand.take(inbox, now_ms=late, after_ms=NOW - 1) == []

    def test_taking_does_not_modify_the_file(self, inbox):
        """The API is the only writer, and that is what removes the race.

        Two processes doing read-modify-write on one JSON file lose updates, and
        the update most likely to be lost is the cooldown -- the one thing here
        holding the spend down.
        """
        accept(inbox)
        before = inbox.read_text(encoding="utf-8")
        ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=NOW - 1)
        assert inbox.read_text(encoding="utf-8") == before

    def test_a_missing_inbox_is_empty_rather_than_an_error(self, tmp_path):
        assert ondemand.take(tmp_path / "nope.json", now_ms=NOW, after_ms=0) == []

    def test_a_malformed_entry_is_dropped_and_the_good_ones_survive(self, inbox):
        """This file is the one spend input that is not a database row.

        A truncated or hand-edited entry has to die here rather than reach
        `fetch_odds` as a sport key of `None`.
        """
        inbox.write_text(
            json.dumps(
                [
                    {"sport_key": "baseball_mlb", "requested_ms": NOW,
                     "estimated_credits": 6, "odds_event_id": None},
                    {"sport_key": None, "requested_ms": NOW, "estimated_credits": 6},
                    {"sport_key": "basketball_wnba", "requested_ms": "soon",
                     "estimated_credits": 6},
                    "not even a dict",
                ]
            ),
            encoding="utf-8",
        )
        due = ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=NOW - 1)
        assert [r.sport_key for r in due] == ["baseball_mlb"]

    def test_a_file_that_is_not_json_reads_as_empty(self, inbox):
        inbox.write_text("{ truncated", encoding="utf-8")
        assert ondemand.take(inbox, now_ms=NOW, after_ms=0) == []
        # And a submit on top of it still works, rather than the button going
        # permanently offline on one bad write.
        assert accept(inbox).accepted


class TestATapDoesNotStealTheWindowsOpeningCall:
    """The load-bearing one, and the reason `api_credits.trigger` exists.

    Props ride the `SCHEDULED` opening call only. A tap makes the identical
    `/sports/{sport}/odds` request at the identical cost, so if it counted as a
    served sweep it would move `last_sweep_by_sport` past `slot.fire_from_ms`,
    `firing_for_slot` would return `REFRESH` for the rest of that window, and
    the cluster would silently lose its entire prop purchase for the day.
    """

    def _slot(self, conn, now_ms):
        fixtures = upcoming_fixtures_by_sport(conn, now_ms=now_ms)
        [slot] = plan_sweep_slots(
            fixtures,
            now_ms=now_ms,
            slots_available=4,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        return slot

    def _record(self, conn, *, called_ms, trigger):
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost, "
            "trigger) VALUES (?, '/sports/baseball_mlb/odds', 'baseball_mlb', "
            "6, ?)",
            (called_ms, trigger),
        )
        conn.commit()

    def test_a_manual_sweep_is_invisible_to_the_planner(self, conn):
        commence = NOW + 40 * MIN
        add_fixture(conn, commence_ms=commence)
        slot = self._slot(conn, NOW)
        assert slot.is_due(NOW)

        self._record(conn, called_ms=NOW, trigger=MANUAL)

        last = last_sweep_by_sport(conn, since_ms=NOW - HOUR)
        assert last == {}, "a tap must not register as this sport's last sweep"
        assert (
            firing_for_slot(
                slot,
                now_ms=NOW + 1_000,
                last_sweep_ms=last.get("baseball_mlb"),
                refresh_interval_ms=refresh_interval_ms(MAX_ODDS_AGE_MS),
            )
            == SCHEDULED
        ), "the window must still open, and opening is what buys props"

    def test_a_planner_sweep_is_still_visible(self, conn):
        """The exclusion must be exact, not a blanket.

        A `NULL` trigger is every row written before schema v9 and every planner
        call after it. If those stopped counting, the planner would re-open an
        already-open window on every pass.
        """
        commence = NOW + 40 * MIN
        add_fixture(conn, commence_ms=commence)
        slot = self._slot(conn, NOW)

        self._record(conn, called_ms=NOW, trigger=None)

        last = last_sweep_by_sport(conn, since_ms=NOW - HOUR)
        assert last == {"baseball_mlb": NOW}
        assert (
            firing_for_slot(
                slot,
                now_ms=NOW + 1_000,
                last_sweep_ms=last["baseball_mlb"],
                refresh_interval_ms=refresh_interval_ms(MAX_ODDS_AGE_MS),
            )
            is None
        )

    def test_the_window_still_refreshes_on_its_own_clock_after_a_tap(self, conn):
        """A tap neither opens the window nor resets its refresh interval."""
        commence = NOW + 40 * MIN
        add_fixture(conn, commence_ms=commence)
        slot = self._slot(conn, NOW)

        self._record(conn, called_ms=NOW, trigger=None)         # the opening
        self._record(conn, called_ms=NOW + 60_000, trigger=MANUAL)  # a tap

        last = last_sweep_by_sport(conn, since_ms=NOW - HOUR)
        assert last == {"baseball_mlb": NOW}
        interval = refresh_interval_ms(MAX_ODDS_AGE_MS)
        assert (
            firing_for_slot(
                slot,
                now_ms=NOW + interval,
                last_sweep_ms=last["baseball_mlb"],
                refresh_interval_ms=interval,
            )
            == REFRESH
        )


class TestDecideSweepsServesTaps:
    def _budget(self, conn, daily=600):
        return CreditBudget(conn, daily_budget=daily)

    def _decide(self, conn, *, manual, now_ms=NOW, daily=600, prop_sports=()):
        return decide_sweeps(
            conn,
            in_scope={"baseball_mlb": now_ms + 3 * HOUR},
            budget=self._budget(conn, daily),
            cost=TEAM_COST,
            now_ms=now_ms,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            prop_cost_per_event=PROP_COST,
            prop_sports=prop_sports,
            allow_bootstrap=False,
            manual=manual,
        )

    def test_a_tap_fires_outside_every_planned_slot(self, conn):
        """The whole point. Three hours out, no slot is due and nothing is
        scheduled -- and that is exactly when a person is looking at a struck-
        through slate wondering why."""
        add_fixture(conn, commence_ms=NOW + 3 * HOUR)
        decision = self._decide(
            conn, manual=[ManualRefresh(sport_key="baseball_mlb")]
        )
        assert [f.trigger for f in decision.fire] == [MANUAL]
        assert decision.fire[0].slot is None
        assert decision.fire[0].prop_event_ids == ()

    def test_a_prop_tap_names_exactly_one_fixture(self, conn):
        add_fixture(conn, commence_ms=NOW + 3 * HOUR)
        decision = self._decide(
            conn,
            manual=[ManualRefresh(sport_key="baseball_mlb", odds_event_id="e1")],
            prop_sports=("baseball_mlb",),
        )
        [firing] = decision.fire
        assert firing.prop_event_ids == ("e1",)
        assert firing.projected_total_cost == TEAM_COST + PROP_COST

    def test_a_tap_is_refused_when_the_day_cannot_afford_it(self, conn):
        add_fixture(conn, commence_ms=NOW + 3 * HOUR)
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost) "
            "VALUES (?, '/sports/baseball_mlb/odds', 'baseball_mlb', 18)",
            (NOW - MIN,),
        )
        conn.commit()
        decision = self._decide(
            conn,
            manual=[ManualRefresh(sport_key="baseball_mlb", odds_event_id="e1")],
            prop_sports=("baseball_mlb",),
            daily=24,
        )
        assert decision.fire == ()
        assert "requested by hand cannot be served" in decision.detail

    def test_the_same_tap_twice_in_one_pass_bills_once(self, conn):
        add_fixture(conn, commence_ms=NOW + 3 * HOUR)
        decision = self._decide(
            conn,
            manual=[
                ManualRefresh(sport_key="baseball_mlb"),
                ManualRefresh(sport_key="baseball_mlb"),
            ],
        )
        assert len(decision.fire) == 1

    def test_a_tap_does_not_double_buy_a_slot_firing_this_pass(self, conn):
        """One pass, one buy per sport.

        What this costs is a 15-second delay to the opening `SCHEDULED` call --
        not its loss, because the tap left `last_sweeps` untouched.
        """
        add_fixture(conn, commence_ms=NOW + 40 * MIN)
        decision = self._decide(
            conn, manual=[ManualRefresh(sport_key="baseball_mlb")]
        )
        assert [f.trigger for f in decision.fire] == [MANUAL]

    def test_a_tap_and_a_planned_sweep_both_fire_in_one_pass(self, conn):
        """A tap on one sport does not cost another sport its window.

        **This is what the `remaining` truncation is really about**, and it is
        worth saying what it is NOT about. The obvious claim -- "a tap survives
        the planned-sweep cap" -- cannot be tested, because it cannot fail:
        `remaining` is `remaining_today // cost` and every manual firing spends
        at least `cost` from the same pool, so `len(manual_firing) <= remaining`
        is a theorem rather than a guard. Capping the taps as well was mutated in
        and no assertion moved. Prepending them is belt-and-braces; the
        arithmetic is what actually protects them.

        So this pins the observable half instead: both fire.
        """
        add_fixture(conn, sport_key="basketball_wnba", commence_ms=NOW + 40 * MIN)
        add_fixture(conn, odds_event_id="e2", commence_ms=NOW + 3 * HOUR)
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": NOW + HOUR, "basketball_wnba": NOW + HOUR},
            budget=self._budget(conn, daily=600),
            cost=TEAM_COST,
            now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            allow_bootstrap=False,
            manual=[ManualRefresh(sport_key="baseball_mlb")],
        )
        by_sport = {f.sport_key: f.trigger for f in decision.fire}
        assert by_sport == {"baseball_mlb": MANUAL, "basketball_wnba": SCHEDULED}


@pytest.fixture
def app_db(tmp_path):
    """A database holding one upcoming MLB fixture and nothing else.

    Built rather than seeded, because these tests assert on *which* fixture is
    known and the demo seed's slate is anchored to the clock.
    """
    path = tmp_path / "api.db"
    c = db.init_db(path)
    add_fixture(c, commence_ms=db.now_ms() + 3 * HOUR, fetched_ms=db.now_ms())
    c.close()
    return path


@pytest.fixture
def live_app(app_db, monkeypatch):
    from backend.api.routes import create_app
    from backend.config import AppConfig

    # The deployed daily cap, set explicitly. `OddsConfig.load`'s default is 16,
    # which is below the 26 a prop refresh costs -- so without this the prop
    # tests would assert on a budget refusal and read as a broken endpoint. The
    # refusal itself is pinned separately, against a cap chosen for it.
    monkeypatch.setenv("ODDS_DAILY_CREDIT_BUDGET", "600")
    return create_app(
        AppConfig(instance_mode="live", auth_token="secret-token", db_path=app_db)
    )


@pytest.fixture
def broke_app(app_db, monkeypatch):
    """A live instance whose day cannot afford a prop refresh."""
    from backend.api.routes import create_app
    from backend.config import AppConfig

    monkeypatch.setenv("ODDS_DAILY_CREDIT_BUDGET", "10")
    return create_app(
        AppConfig(instance_mode="live", auth_token="secret-token", db_path=app_db)
    )


@pytest.fixture
def demo_app(app_db):
    from backend.api.routes import create_app
    from backend.config import AppConfig

    return create_app(AppConfig(instance_mode="demo", db_path=app_db))


class TestTheEndpoint:
    """The route: authenticated, validating, and honest about what it did.

    The route is mounted on both instances and `require_auth` refuses it on the
    demo outright -- a public URL that can spend the account's credits is the
    boundary this project's security section exists for.
    """

    async def _post(self, app, **body):
        import httpx

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/api/odds/refresh",
                headers={"Authorization": "Bearer secret-token"},
                json=body,
            )

    async def test_the_demo_refuses_it_outright(self, demo_app):
        import httpx

        transport = httpx.ASGITransport(app=demo_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/odds/refresh", json={"sport_key": "baseball_mlb"}
            )
        assert response.status_code == 403

    async def test_it_requires_a_token(self, live_app):
        import httpx

        transport = httpx.ASGITransport(app=live_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/odds/refresh", json={"sport_key": "baseball_mlb"}
            )
        assert response.status_code == 401

    async def test_a_known_fixture_is_accepted_and_priced(self, live_app):
        """The happy path, and it states a cost rather than implying one."""
        body = (await self._post(live_app, sport_key="baseball_mlb")).json()
        assert body["accepted"] is True
        assert body["estimated_credits"] > 0
        assert "15 seconds" in body["detail"]

    async def test_a_prop_refresh_is_priced_above_a_team_refresh(self, live_app):
        """The expensive half is named as expensive, on the screen."""
        team = (await self._post(live_app, sport_key="baseball_mlb")).json()
        props = (
            await self._post(
                live_app, sport_key="baseball_mlb", odds_event_id="e1"
            )
        ).json()
        assert props["accepted"] is True
        assert props["estimated_credits"] > team["estimated_credits"]

    async def test_it_never_claims_the_odds_were_fetched(self, live_app):
        """This process cannot fetch anything.

        It opens the database read-only and is not the process holding the odds
        client. Saying "refreshed" would be a claim about a call that has not
        been made and may still be refused on budget.
        """
        body = (await self._post(live_app, sport_key="baseball_mlb")).json()
        assert "refreshed" not in body["detail"]
        assert set(body) == {
            "accepted", "detail", "estimated_credits", "retry_after_ms"
        }

    async def test_the_day_s_budget_still_refuses_a_tap_it_cannot_afford(
        self, broke_app
    ):
        """The API's own ceiling is not the only one, and must not be.

        A tap inside the manual daily slice can still be unaffordable on the
        day, and the reason a person needs is the budget's own words -- not
        "refused".
        """
        body = (
            await self._post(
                broke_app, sport_key="baseball_mlb", odds_event_id="e1"
            )
        ).json()
        assert body["accepted"] is False
        assert "the day's odds budget refuses this call" in body["detail"]
        assert "26" in body["detail"]

    async def test_a_sport_with_no_stored_fixture_is_refused_with_a_reason(
        self, live_app
    ):
        """Not a 404.

        The sport may be real and simply have no game inside the day. A reason
        in words is more use on a phone than a status code, and it is the shape
        every other refusal on this route takes.
        """
        body = (await self._post(live_app, sport_key="curling_mens")).json()
        assert body["accepted"] is False
        assert body["estimated_credits"] == 0
        assert "no curling_mens fixture" in body["detail"]

    async def test_an_unknown_fixture_is_refused_before_it_is_paid_for(
        self, live_app
    ):
        """Props are billed per fixture, so this must not pay to find out."""
        body = (
            await self._post(
                live_app, sport_key="baseball_mlb", odds_event_id="nosuchgame"
            )
        ).json()
        assert body["accepted"] is False
        assert "not a stored upcoming" in body["detail"]

    async def test_a_malformed_sport_key_never_reaches_the_handler(self, live_app):
        """A sport key is interpolated into a paid request path."""
        response = await self._post(live_app, sport_key="../../etc/passwd")
        assert response.status_code == 422


class TestTheWholePathFromTapToSpend:
    """One test that crosses every seam, because each half passes alone.

    The pieces are separately covered above and separately correct, and that is
    exactly the arrangement this repo keeps getting caught by: the API writes an
    inbox, the runner reads one, and nothing until now proved they were the same
    file with the same shape. `inbox_path` derives it from `db_path` on both
    sides precisely so they cannot disagree -- and a derivation nobody exercises
    is a convention, not a guarantee.
    """

    async def test_a_tap_reaches_decide_sweeps_as_a_manual_firing(
        self, live_app, app_db
    ):
        import httpx

        transport = httpx.ASGITransport(app=live_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/odds/refresh",
                headers={"Authorization": "Bearer secret-token"},
                json={"sport_key": "baseball_mlb", "odds_event_id": "e1"},
            )
        assert response.json()["accepted"] is True

        # The runner's side. The path is derived from the database, exactly as
        # `scripts/run_loop.py` derives it -- not read back from the response,
        # which would prove nothing about the two agreeing.
        now = db.now_ms()
        due = ondemand.take(
            ondemand.inbox_path(app_db), now_ms=now + 1_000, after_ms=now - 60_000
        )
        assert [(r.sport_key, r.odds_event_id) for r in due] == [
            ("baseball_mlb", "e1")
        ]

        conn = db.open_db(app_db)
        try:
            decision = decide_sweeps(
                conn,
                in_scope={"baseball_mlb": now + 3 * HOUR},
                budget=CreditBudget(conn, daily_budget=600),
                cost=TEAM_COST,
                now_ms=now + 1_000,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
                prop_cost_per_event=PROP_COST,
                prop_sports=("baseball_mlb",),
                allow_bootstrap=False,
                manual=[
                    ManualRefresh(
                        sport_key=r.sport_key, odds_event_id=r.odds_event_id
                    )
                    for r in due
                ],
            )
        finally:
            conn.close()

        [firing] = decision.fire
        assert firing.trigger == MANUAL
        assert firing.prop_event_ids == ("e1",)
        assert firing.slot is None, "a tap must never look like a window opening"

    async def test_a_served_tap_leaves_the_planner_seeing_no_sweep(self, conn):
        """The real path, through `fetch_and_store_odds`, to `api_credits`.

        This is the assertion the whole `trigger` column exists for, and it is
        deliberately taken from the database *after* a served call rather than
        from the value the runner computed on its way there. A stamp that were
        computed correctly and then dropped between here and the `INSERT` would
        pass every other test in this file.
        """
        from backend.config import OddsConfig
        from backend.odds.timing import last_sweep_by_sport
        from backend.runner import fetch_and_store_odds

        class FakeOdds:
            """Serves nothing, and records the credit row a real call would."""

            def __init__(self, budget):
                self.budget = budget

            async def fetch_odds(self, sport_key, *, now_ms, trigger=None):
                self.budget.record(
                    called_ms=now_ms,
                    endpoint=f"/sports/{sport_key}/odds",
                    cost=TEAM_COST,
                    sport_key=sport_key,
                    trigger=trigger,
                )
                return []

        add_fixture(conn, commence_ms=NOW + 3 * HOUR)
        budget = CreditBudget(conn, daily_budget=600)
        await fetch_and_store_odds(
            conn,
            FakeOdds(budget),
            budget,
            events=[],
            config=OddsConfig(
                api_key="x",
                base_url="https://example.invalid",
                markets=["h2h"],
                regions=["us"],
                daily_credit_budget=600,
            ),
            now=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            allow_bootstrap=False,
            manual=[ManualRefresh(sport_key="baseball_mlb")],
        )

        stamped = conn.execute(
            "SELECT trigger FROM api_credits ORDER BY id DESC LIMIT 1"
        ).fetchone()["trigger"]
        assert stamped == "manual"
        assert last_sweep_by_sport(conn, since_ms=NOW - HOUR) == {}, (
            "a served tap must leave the planner still seeing an unopened window"
        )
