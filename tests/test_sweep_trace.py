"""A refused odds sweep must leave a trace, and the trace must not lie.

Odds fetching stopped at 2026-08-09T23:37:15Z and ran 17+ hours behind a green
health check. It went unnoticed because a refused sweep left **no row in any
table in the schema**: `api_credits` is written only when an HTTP call was
actually made, `notifications` writes `window_open` only when a sweep succeeded,
and `decide_sweeps`' reason string was only logged -- and `flyctl logs` is
lossy. Silence and "the system never looked" were the same observation.

The obvious remedy is a zero-cost row in `api_credits` saying "refused". This
file exists because that remedy is a **booby trap**, and the first half of it is
the demonstration:

    `last_sweep_by_sport` filters on `called_ms >= ?` and `sport_key IS NOT
    NULL` and nothing else -- no endpoint filter, no cost filter -- so it reads
    a refusal row as a *served* sweep. `plan_sweep_slots` then drops that
    sport's slot as already served, and `decide_sweeps` drops it from the
    bootstrap candidates too. The fix for the silence would have made the
    silence permanent, for exactly the sport it was recording a refusal for.

Three lines below it, `_latest_sweep_row` *does* filter on the endpoint. One
reader of one table filtering and its neighbour not is the whole surface of the
bug, and the asymmetry was invisible because both queries look reasonable.

What this file does NOT establish
---------------------------------
That the trace is *acted on*. These tests assert that a refusal is recorded, is
recorded somewhere that no reader mistakes for a sweep, and can be read back.
Whether anyone looks at it -- an alert, a health check that goes red -- is a
different guarantee and is not tested here.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import httpx
import pytest
import respx

from backend.config import OddsConfig
from backend.odds.budget import CreditBudget
from backend.odds.client import OddsClient, OddsQuote
from backend.odds.sweeplog import (
    NO_DATA,
    REFUSED,
    SERVED,
    SKIPPED,
    last_sweep_outcome,
    record_sweep_outcome,
)
from backend.odds.timing import decide_sweeps, last_sweep_by_sport, window_status
from backend.runner import fetch_and_store_odds
from backend.store import db

MIN = 60_000
HOUR = 3_600_000

NOW = int(
    datetime.fromisoformat("2026-08-07T18:00:00")
    .replace(tzinfo=timezone.utc)
    .timestamp()
    * 1000
)

MAX_ODDS_AGE_MS = 900_000
SWEEP_COST = 6

# A kickoff 20 minutes out puts `NOW` inside the slot's due window: the slot
# fires from `anchor - max_odds_age - due_window` to `anchor - max_odds_age`.
SOON = NOW + 20 * MIN


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "trace.db")
    yield c
    c.close()


@pytest.fixture
def budget(conn):
    return CreditBudget(conn, daily_budget=400)


def add_fixture(conn, *, sport_key="baseball_mlb", commence_ms=SOON):
    for book in ("pinnacle", "draftkings"):
        for outcome in ("Home", "Away"):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, sport_key, "
                "odds_event_id, commence_ms, home_team, away_team, bookmaker, "
                "market, outcome_name, price_decimal) "
                "VALUES (?, ?, 'e1', ?, 'Home', 'Away', ?, 'h2h', ?, 2.0)",
                (NOW, sport_key, commence_ms, book, outcome),
            )
    conn.commit()


def write_the_naive_fix(conn, *, sport_key="baseball_mlb", endpoint, called_ms=None):
    """The remedy this file exists to refuse: a zero-cost row in `api_credits`.

    Parametrised on the endpoint because the two plausible spellings of the
    naive fix fail differently, and only one filter survives both. A refusal
    row recorded under a *distinct* endpoint (`/odds:refused`) would be caught
    by an endpoint filter; one recorded under the **same** endpoint the served
    call uses -- which is the more natural thing to write, since it is the call
    that was refused -- would not. `cost > 0` catches both.
    """
    conn.execute(
        "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost) "
        "VALUES (?, ?, ?, 0)",
        (called_ms if called_ms is not None else NOW, endpoint, sport_key),
    )
    conn.commit()


BOTH_SPELLINGS = pytest.mark.parametrize(
    "endpoint",
    ["/sports/baseball_mlb/odds", "/odds:refused"],
    ids=["same-endpoint-as-a-served-call", "a-distinct-refusal-endpoint"],
)


class TestTheNaiveFixIsABoobyTrap:
    """Write the refusal into `api_credits` and the scheduler stops sweeping.

    Every assertion here was RED before `last_sweep_by_sport` gained its filter,
    which is the point: the trap is demonstrated, not asserted.
    """

    def test_the_sweep_fires_when_nothing_has_been_recorded(self, conn, budget):
        """The control. Without it every assertion below could pass because the
        sweep was never going to fire in the first place."""
        add_fixture(conn)
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": SOON + 3 * HOUR},
            budget=budget,
            cost=SWEEP_COST,
            now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.sport_key for f in decision.fire] == ["baseball_mlb"], (
            f"nothing fires even with a clean record, so this file cannot "
            f"detect the trap at all: {decision.detail}"
        )

    @BOTH_SPELLINGS
    def test_a_zero_cost_row_is_not_read_as_a_served_sweep(self, conn, endpoint):
        """The trap itself, at its source.

        `last_sweep_by_sport` means "when did this sport last actually get
        swept". A row that spent no credits fetched no odds, so it is not a
        sweep -- but the query had no way to tell, and answered with the
        refusal's timestamp.
        """
        write_the_naive_fix(conn, endpoint=endpoint)
        served = last_sweep_by_sport(conn, since_ms=NOW - HOUR)
        assert "baseball_mlb" not in served, (
            f"a zero-cost refusal row recorded at {endpoint} reads as a served "
            f"sweep at {served.get('baseball_mlb')}. Every downstream reader "
            f"now believes odds were fetched for baseball_mlb when none were."
        )

    @BOTH_SPELLINGS
    def test_the_scheduler_does_not_decline_because_of_a_refusal_row(
        self, conn, budget, endpoint
    ):
        """The consequence, which is the part that costs money.

        `plan_sweep_slots` drops a slot whose sport has a recorded sweep at or
        after `fire_from_ms`. Fed a refusal row, it drops the very slot the
        refusal was recorded for -- so the scheduler declines to sweep because
        it declined to sweep.
        """
        add_fixture(conn)
        write_the_naive_fix(conn, endpoint=endpoint)

        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": SOON + 3 * HOUR},
            budget=budget,
            cost=SWEEP_COST,
            now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.sport_key for f in decision.fire] == ["baseball_mlb"], (
            f"the scheduler declined a due slot because a *refusal* was "
            f"recorded as a sweep. The trace intended to reveal the silence "
            f"causes it. detail: {decision.detail}"
        )

    @BOTH_SPELLINGS
    def test_the_bootstrap_path_is_not_blocked_by_a_refusal_row(
        self, conn, budget, endpoint
    ):
        """The second, independent corruption in the same query.

        `decide_sweeps` bootstraps a sport with no stored fixtures at all, once
        per budget day, and excludes any sport already in `last_sweeps`. A
        refusal row spends that one attempt without making a single call -- so
        a sport Kalshi lists and the sportsbook has never been asked about
        stays unpriced for the rest of the day.
        """
        write_the_naive_fix(conn, sport_key="basketball_wnba", endpoint=endpoint)

        decision = decide_sweeps(
            conn,
            in_scope={"basketball_wnba": NOW + 4 * HOUR},
            budget=budget,
            cost=SWEEP_COST,
            now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == ["bootstrap"], (
            f"the day's one bootstrap attempt for basketball_wnba was consumed "
            f"by a row recording that no call was made. detail: "
            f"{decision.detail}"
        )

    def test_a_served_sweep_is_still_read_as_one(self, conn, budget):
        """The guard on the guard, and it is not optional here.

        A filter that excluded *everything* would pass all four tests above by
        making `last_sweep_by_sport` always empty -- and the cost would be a
        second credit spent on every cluster already swept, which is real money.
        Both directions have to be shown to move.
        """
        budget.record(
            called_ms=NOW, endpoint="/sports/baseball_mlb/odds",
            sport_key="baseball_mlb", cost=6,
        )
        assert last_sweep_by_sport(conn, since_ms=NOW - HOUR) == {
            "baseball_mlb": NOW
        }, "a real, paid-for sweep is no longer visible, so every cluster would "\
           "be swept twice"

    def test_the_demo_seeders_endpoint_spelling_is_read_as_a_sweep_too(
        self, conn, budget
    ):
        """Two spellings of the same fact, and the mismatch was a live bug.

        `client.py` records `/sports/{sport_key}/odds`; `seed_demo.py` writes
        the literal `/odds`. `_latest_sweep_row` filtered on `endpoint =
        '/odds'`, so it matched every demo row and **no production row at all**
        -- the window panel's "last sweep" age read correctly on the demo and
        "never" on the live instance, which is precisely the readout that would
        have shown odds fetching had stopped.
        """
        budget.record(
            called_ms=NOW, endpoint="/odds", sport_key="baseball_mlb", cost=6
        )
        assert last_sweep_by_sport(conn, since_ms=NOW - HOUR) == {
            "baseball_mlb": NOW
        }

    def test_spend_on_a_non_odds_endpoint_is_not_a_sweep(self, conn, budget):
        """The other half of the predicate, and it is not decoration.

        The historical endpoints charge `10 x markets x regions` -- real spend,
        for a *backfill* of games already played, not a sweep of the current
        board. `cost > 0` alone would let one of those suppress the day's live
        sweep for that sport, which is the same failure as the refusal row with
        a bigger number on it.
        """
        budget.record(
            called_ms=NOW, endpoint="/sports/baseball_mlb/odds-history",
            sport_key="baseball_mlb", cost=60,
        )
        assert "baseball_mlb" not in last_sweep_by_sport(conn, since_ms=NOW - HOUR), (
            "a historical backfill was read as today's sweep, so the live "
            "board goes unpriced for that sport"
        )


# ---------------------------------------------------------------------------
# The remedy: a separate table that means "what this pass decided about odds".
# ---------------------------------------------------------------------------


@pytest.fixture
def odds_config():
    return OddsConfig(
        api_key="test-key",
        base_url="https://api.test-odds.invalid/v4",
        daily_credit_budget=400,
        regions=["us", "eu"],
        markets=["h2h", "spreads", "totals"],
    )


def log_rows(conn):
    return conn.execute(
        "SELECT * FROM odds_sweep_log ORDER BY id"
    ).fetchall()


class FakeOdds:
    """Returns what it is told to. `[]` is a real state, not a failure."""

    def __init__(self, quotes=()):
        self.quotes = list(quotes)
        self.calls: list[str] = []

    async def fetch_odds(self, sport_key: str, *, now_ms: int):
        self.calls.append(sport_key)
        return list(self.quotes)


def a_quote(sport_key="baseball_mlb", bookmaker="pinnacle", outcome="Home"):
    return OddsQuote(
        fetched_ms=NOW,
        book_updated_ms=NOW,
        sport_key=sport_key,
        odds_event_id="e1",
        commence_ms=SOON,
        home_team="Home",
        away_team="Away",
        bookmaker=bookmaker,
        market="h2h",
        outcome_name=outcome,
        outcome_point=None,
        price_decimal=2.0,
    )


class TestARefusalIsRecordedWhereItHappens:
    """The budget's refusal used to exist only in a `logger.warning`.

    Which of the three ceilings bound is the one fact that explains a silent
    day, and it lived exclusively in a log stream that drops lines.
    """

    @respx.mock
    async def test_a_refused_call_writes_a_row_naming_the_ceiling(
        self, conn, odds_config
    ):
        budget = CreditBudget(conn, daily_budget=6)
        budget.record(
            called_ms=NOW, endpoint="/sports/baseball_mlb/odds",
            sport_key="baseball_mlb", cost=6,
        )
        route = respx.get(
            f"{odds_config.base_url}/sports/baseball_mlb/odds"
        ).mock(return_value=httpx.Response(200, json=[]))

        async with OddsClient(odds_config, budget) as odds:
            assert await odds.fetch_odds("baseball_mlb", now_ms=NOW + 1) == []

        assert route.call_count == 0, "a refused call must not hit the network"

        rows = log_rows(conn)
        assert [r["outcome"] for r in rows] == [REFUSED], (
            "a refused sweep left no trace, which is the whole defect: silence "
            "is indistinguishable from a system that never looked"
        )
        assert rows[0]["sport_key"] == "baseball_mlb"
        assert "daily credits" in rows[0]["detail"], (
            f"the row does not say which ceiling bound, so it turns 'did it "
            f"look?' into 'why did it stop?': {rows[0]['detail']!r}"
        )

    @respx.mock
    async def test_the_refusal_row_does_not_land_in_api_credits(
        self, conn, odds_config
    ):
        """Where the trace goes is the decision this file exists to defend."""
        budget = CreditBudget(conn, daily_budget=6)
        budget.record(
            called_ms=NOW, endpoint="/sports/baseball_mlb/odds",
            sport_key="baseball_mlb", cost=6,
        )
        async with OddsClient(odds_config, budget) as odds:
            await odds.fetch_odds("baseball_mlb", now_ms=NOW + 1)

        credits = conn.execute("SELECT COUNT(*) c FROM api_credits").fetchone()
        assert credits["c"] == 1, (
            "the refusal was written into the table that means 'a call was "
            "made and it cost credits'"
        )

    def test_the_reason_and_the_refusal_are_one_implementation(self, conn):
        """`can_afford` is defined in terms of `refusal_reason`.

        Two implementations of the three ceilings would drift invisibly: the
        guard would still refuse, and the recorded reason would name a limit
        that was not the one that bound.
        """
        budget = CreditBudget(conn, daily_budget=6, monthly_budget=6)
        budget.record(called_ms=NOW, endpoint="/odds", cost=6)
        for cost in (1, 6, 100):
            assert budget.can_afford(cost, NOW) == (
                budget.refusal_reason(cost, NOW) is None
            )

    def test_an_affordable_call_gets_no_reason_at_all(self, conn):
        """`None`, not an empty string. An absent objection and an unreadable
        one must not share a representation."""
        budget = CreditBudget(conn, daily_budget=400)
        assert budget.refusal_reason(6, NOW) is None


class TestEveryPassSaysWhatItDidAboutOdds:
    """A pass that looked and declined must be distinguishable from one that
    never ran. That was the 17 hours."""

    async def _sweep(self, conn, budget, odds_config, odds, *, in_scope_events=()):
        return await fetch_and_store_odds(
            conn,
            odds,
            budget,
            events=list(in_scope_events),
            config=odds_config,
            now=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )

    async def test_a_pass_that_decides_nothing_still_records_why(
        self, conn, budget, odds_config
    ):
        odds = FakeOdds()
        await self._sweep(conn, budget, odds_config, odds)

        assert odds.calls == []
        rows = log_rows(conn)
        assert [r["outcome"] for r in rows] == [SKIPPED]
        assert rows[0]["sport_key"] is None, (
            "a pass that swept no sport must not name one"
        )
        assert rows[0]["detail"].startswith("no sweep:"), rows[0]["detail"]
        assert rows[0]["quotes_stored"] is None, (
            "0 and 'nothing was attempted' must not share a value"
        )

    async def test_a_served_sweep_records_what_it_stored(
        self, conn, budget, odds_config
    ):
        add_fixture(conn)
        odds = FakeOdds([a_quote(), a_quote(outcome="Away")])
        sweeps, stored, _ = await self._sweep(conn, budget, odds_config, odds)

        assert (sweeps, stored) == (1, 2)
        rows = log_rows(conn)
        # Two decisions, not one, since 2026-08-15: the team sweep, then
        # whether to buy player props for the fixtures it just paid for. The
        # second is SKIPPED here because no prop event was discovered, and it is
        # recorded rather than passed over for the reason this whole class
        # exists -- "we chose not to buy props" and "props were never
        # considered" are different states and cost different amounts.
        assert [r["outcome"] for r in rows] == [SERVED, SKIPPED]
        assert rows[0]["sport_key"] == "baseball_mlb"
        assert rows[0]["quotes_stored"] == 2
        assert rows[1]["detail"].startswith("props:"), rows[1]["detail"]
        assert rows[1]["quotes_stored"] is None, (
            "0 and 'nothing was attempted' must not share a value"
        )

    async def test_an_empty_slate_is_not_recorded_as_a_refusal(
        self, conn, budget, odds_config
    ):
        """The two states `fetch_odds` collapses into `[]`, kept apart.

        "We chose not to spend" and "we spent and there was nothing there" need
        opposite responses -- one is a budget problem, the other is a slate.
        """
        add_fixture(conn)
        odds = FakeOdds([])
        await self._sweep(conn, budget, odds_config, odds)

        assert odds.calls == ["baseball_mlb"]
        rows = log_rows(conn)
        assert [r["outcome"] for r in rows] == [NO_DATA]
        assert rows[0]["quotes_stored"] is None

    @respx.mock
    async def test_a_refused_sweep_records_exactly_one_row(
        self, conn, odds_config
    ):
        """Two writers on one event would contradict each other.

        The client records refusals at the point of refusal; the runner records
        everything else. If the runner also guessed, a refused sweep would carry
        both `refused` and `no_data` and no reader could say which happened.
        """
        add_fixture(conn)
        # Enough for the scheduler to plan a sweep, not enough to make the call:
        # `decide_sweeps` reads only the daily ceiling, while the server's own
        # count is checked in `refusal_reason`. That gap is real, and it is the
        # one that produces a planned sweep the client then refuses.
        budget = CreditBudget(conn, daily_budget=400)
        budget.record(
            called_ms=NOW - HOUR, endpoint="/sports/other/odds",
            sport_key=None, cost=6, remaining_reported=2,
        )
        respx.get(f"{odds_config.base_url}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=[])
        )

        async with OddsClient(odds_config, budget) as odds:
            await fetch_and_store_odds(
                conn, odds, budget, events=[], config=odds_config,
                now=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
            )

        rows = log_rows(conn)
        assert [r["outcome"] for r in rows] == [REFUSED], (
            f"expected exactly one refusal row, got "
            f"{[(r['outcome'], r['detail']) for r in rows]}"
        )
        assert "credits left this period" in rows[0]["detail"], rows[0]["detail"]


class TestTheTraceIsReadBack:
    """A trace nobody reads is half a fix.

    Four modules in this repo have been complete, tested, and called by
    nothing. `window_status` is what `/api/window` serves, which is what a
    phone can see.
    """

    def test_the_window_reports_the_last_time_a_pass_looked(self, conn, budget):
        record_sweep_outcome(
            conn, pass_ms=NOW, outcome=SKIPPED,
            detail="no sweep: 400 of 400 credits spent since 10:00Z",
        )
        payload = window_status(
            conn, budget=budget, now_ms=NOW + MIN,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=SWEEP_COST,
        ).to_dict()

        assert payload["last_look_ms"] == NOW
        assert payload["last_look_outcome"] == SKIPPED
        assert "400 of 400" in payload["last_look_detail"]

    def test_a_database_that_has_never_looked_says_so_rather_than_nothing(
        self, conn, budget
    ):
        """`None`, not a fabricated timestamp. After a fresh deploy "it has
        never looked" is the true state and is not "it looked and found
        nothing"."""
        payload = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=SWEEP_COST,
        ).to_dict()
        assert payload["last_look_ms"] is None
        assert payload["last_look_outcome"] is None
        assert payload["last_look_detail"] is None

    def test_the_last_look_is_not_the_last_sweep(self, conn, budget):
        """The gap between the two is the state that went unnoticed.

        A loop that is alive and declining every pass has a fresh `last_look`
        and a stale `last_sweep`. A loop that has died has both stale. Reporting
        only one cannot tell them apart -- and only `last_sweep` existed.
        """
        budget.record(
            called_ms=NOW - 17 * HOUR, endpoint="/sports/baseball_mlb/odds",
            sport_key="baseball_mlb", cost=6,
        )
        record_sweep_outcome(
            conn, pass_ms=NOW, outcome=SKIPPED, detail="no sweep: nothing due"
        )
        window = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=SWEEP_COST,
        )
        assert window.last_sweep_ms == NOW - 17 * HOUR
        assert window.last_look_ms == NOW


class TestTheRecordRefusesAnAmbiguousRow:
    """The constraints, verified by trying to violate them."""

    def test_an_unknown_outcome_is_refused(self, conn):
        with pytest.raises(ValueError, match="outcome must be one of"):
            record_sweep_outcome(
                conn, pass_ms=NOW, outcome="maybe", detail="something"
            )

    def test_a_row_with_no_reason_is_refused(self, conn):
        """A refusal recorded without its reason turns one unanswerable
        question into another."""
        with pytest.raises(ValueError, match="no reason"):
            record_sweep_outcome(
                conn, pass_ms=NOW, outcome=REFUSED, detail=""
            )

    def test_the_database_refuses_an_unknown_outcome_too(self, conn):
        """The Python guard is a message; the CHECK is the guarantee. A writer
        that bypasses `record_sweep_outcome` must not be able to widen the
        vocabulary by accident."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO odds_sweep_log (pass_ms, outcome, detail) "
                "VALUES (?, 'maybe', 'x')",
                (NOW,),
            )

    def test_only_a_served_sweep_may_claim_a_quote_count(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO odds_sweep_log (pass_ms, outcome, detail, "
                "quotes_stored) VALUES (?, 'refused', 'over budget', 0)",
                (NOW,),
            )

    def test_a_served_sweep_must_say_how_much_it_stored(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO odds_sweep_log (pass_ms, outcome, detail) "
                "VALUES (?, 'served', 'swept mlb')",
                (NOW,),
            )

    def test_the_most_recent_row_is_the_one_read_back(self, conn):
        for i, outcome in enumerate((SKIPPED, SKIPPED, NO_DATA)):
            record_sweep_outcome(
                conn, pass_ms=NOW + i, outcome=outcome, detail=f"pass {i}",
                sport_key="baseball_mlb" if outcome == NO_DATA else None,
            )
        assert last_sweep_outcome(conn)["detail"] == "pass 2"

    def test_an_empty_log_reads_as_none_rather_than_a_default_row(self, conn):
        assert last_sweep_outcome(conn) is None
