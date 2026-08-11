"""The Skeptic, connected to the pricing pass.

`backend/agents/*` was the fourth module in this project to be complete, tested
and invoked by nothing. These are the tests that the *connection* works, which
is a different claim from the ~40 tests asserting the agents themselves behave.

What these tests do not establish
---------------------------------
**That this has ever changed an outcome on real money.** The Skeptic runs only
on rows that would be surfaced, and `surfaced` has been 0 for the life of the
project, so on the live instance this path has never executed. The slate below
is built by taking the captured Kalshi and odds payloads the rest of the suite
uses and nudging **one** number -- the NO bid on one market, which sets the
derived YES ask -- until the row clears the suppression gauntlet. Every other
value is the bytes the two APIs actually sent.

That nudge is stated rather than hidden because it is the whole reason a test
can exist here at all: without it there is no surfaced row anywhere in this
repo, and a wiring test with nothing to wire is decoration.

Where the "the Skeptic can stop a bet" claim is actually established
-------------------------------------------------------------------
In two links, deliberately not re-walked here as a third test:

1. A blocked row persists with `suppressed_reason` set and
   `suggested_contracts` at zero -- `test_a_blocking_verdict_never_reaches_the
   _database_as_orderable`, below.
2. `POST /api/orders` answers 422 and writes no order for any row carrying a
   `suppressed_reason` -- `test_order_record.py`, which drives the real
   endpoint against a row suppressed for `stale_odds`.

`skeptic_defect` is the same shape as `stale_odds` as far as that endpoint is
concerned: it refuses on the reason before it looks at anything else. A third
test asserting the join would be a copy of (2) with one string changed.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from backend.agents.base import AgentConfig
from backend.agents.review import ReviewCandidate, ReviewOutcome, review_surfaced
from backend.agents.skeptic import SkepticVerdict
from backend.engine import Recommendation, with_added_suppression
from backend.kalshi.discovery import discover_from_events
from backend.odds.client import store_quotes
from backend.runner import run_pricing_pass, store_quotes_from_discovery, upsert_discovered
from backend.store import db

FIXTURES = Path(__file__).parent / "fixtures"

# Same clock as `test_runner.py`: five minutes after the odds capture was taken.
NOW = 1_786_110_562_317 + 300_000

# The captured market's NO bid is 0.5200, which derives a 48c YES ask against a
# 55.7c consensus -- a 5.9c edge, refused by `suspicious_edge` for exceeding the
# 4c ceiling. 0.4900 derives a 51c ask and a 2.9c edge, which is inside every
# threshold and is also a realistic number: the venue prices to ~2c.
SURFACING_NO_BID = "0.4900"


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "wiring.db")
    yield c
    c.close()


@pytest.fixture(scope="module")
def kalshi_events() -> list[dict]:
    return json.loads((FIXTURES / "events_sports_nested.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def odds_capture() -> dict:
    return json.loads(
        (FIXTURES / "odds_mlb_h2h_spreads_totals.json").read_text("utf-8")
    )


@pytest.fixture
def surfacing_slate(conn, kalshi_events, odds_capture):
    """A database holding exactly one surfaced candidate. Returns the events.

    The alignment is `test_runner.aligned_kalshi_event`'s, with one addition:
    the market's own `title` is rewritten too. Leaving it alone is what the live
    Skeptic caught on the first real run of this path -- it read a market titled
    "Houston vs San Diego Winner?" under an event titled "Pittsburgh vs New York
    M" and correctly called the pairing a defect. Correct of it, and a fixture
    bug rather than a finding, so the fixture is fixed.
    """
    from backend.config import OddsConfig
    from backend.odds.budget import CreditBudget
    from backend.odds.client import OddsClient

    client = OddsClient(
        OddsConfig(
            api_key="x", base_url="https://example.invalid",
            daily_credit_budget=16, regions=["us", "eu"],
            markets=["h2h", "spreads", "totals"],
        ),
        CreditBudget(conn, daily_budget=16),
    )
    store_quotes(
        conn,
        client._parse(
            odds_capture["events"], sport_key="baseball_mlb", fetched_ms=NOW
        ),
    )
    odds_event = next(
        e for e in odds_capture["events"] if e["home_team"] == "Pittsburgh Pirates"
    )

    template = next(
        e for e in kalshi_events
        if (e.get("event_ticker") or "").startswith("KXMLBGAME-")
        and len(e.get("markets") or []) == 2
    )
    event = copy.deepcopy(template)
    home, away = "Pittsburgh", "New York M"
    event["event_ticker"] = "KXMLBGAME-TESTPITNEW"
    event["title"] = f"{home} vs {away}"
    for market, name in zip(event["markets"], (home, away)):
        market["event_ticker"] = event["event_ticker"]
        market["ticker"] = f"{event['event_ticker']}-{name[:3].upper()}"
        market["yes_sub_title"] = name
        market["title"] = f"{home} vs {away} Winner?"
        market["occurrence_datetime"] = odds_event["commence_time"]
        market["close_time"] = odds_event["commence_time"]

    event["markets"][0]["no_bid_dollars"] = SURFACING_NO_BID

    events = discover_from_events([event])
    upsert_discovered(conn, events, now=NOW)
    store_quotes_from_discovery(conn, events, now=NOW)
    return events


def _rows(conn) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT ticker, side, suggested_contracts, suppressed_reason, "
            "reason_text FROM recommendations ORDER BY id"
        ).fetchall()
    ]


def _orderable(conn) -> list[dict]:
    """Exactly the rows the order endpoint would let through.

    Written as the endpoint's own predicate rather than as `surfaced`, because
    the claim being tested is about what money can reach, and the endpoint reads
    the database rather than any object this process is holding.
    """
    return [
        r for r in _rows(conn)
        if r["suggested_contracts"] > 0 and not r["suppressed_reason"]
    ]


def _prompt_kwargs(**overrides) -> dict:
    """A valid `skeptic.build_prompt` keyword set.

    Spelled out rather than left empty. An empty mapping raises `TypeError`
    inside `evaluate`, which the isolation guard turns into a `None` verdict --
    so a test using `{}` would assert the right outcome for entirely the wrong
    reason, and would keep passing if verdicts stopped being applied at all.
    """
    base = dict(
        ticker="KXTEST-ABC",
        market_title="Pittsburgh vs New York M Winner?",
        outcome_name="Pittsburgh Pirates",
        event_title="Pittsburgh vs New York M",
        kalshi_ask_cents=51.0,
        consensus_fair_cents=55.7,
        edge_cents=2.9,
        quote_age_s=0.0,
        odds_age_s=424.3,
        book_count=3,
        market_width_points=0.0034,
        depth_at_ask=120.0,
        devig_methods={"multiplicative": 0.557, "shin": 0.5579},
        commence_iso="2026-08-07T17:05:00+00:00",
        matched_sportsbook_teams=["New York Mets", "Pittsburgh Pirates"],
    )
    base.update(overrides)
    return base


def _verdict(kind: str = "defect") -> SkepticVerdict:
    return SkepticVerdict(
        verdict=kind,
        primary_concern="the Kalshi market settles on regulation time.",
        checks_performed=["compared settlement rules"],
        recommended_action="reject",
        confidence=0.8,
    )


class _Reviewer:
    """A stand-in for `review_surfaced` that records what it was asked."""

    def __init__(self, verdict=None, on_call=None):
        self._verdict = verdict
        self._on_call = on_call
        self.batches: list[list[ReviewCandidate]] = []

    def __call__(self, candidates, **kwargs) -> ReviewOutcome:
        self.batches.append(list(candidates))
        if self._on_call is not None:
            self._on_call(list(candidates))
        # `conn` and `now` are forwarded rather than re-supplied: the runner is
        # what owns both, and a stand-in that invented its own would be testing
        # a budget the production path never uses.
        return review_surfaced(
            candidates,
            config=AgentConfig(api_key="test-key"),
            client_factory=lambda config: _StubClient(self._verdict),
            **kwargs,
        )

    @property
    def calls(self) -> int:
        return sum(len(b) for b in self.batches)


class _StubMessages:
    def __init__(self, verdict, raises=None):
        self._verdict = verdict
        self._raises = raises
        self.seen = 0

    async def parse(self, **kwargs):
        self.seen += 1
        if self._raises is not None:
            raise self._raises
        return _StubResponse(self._verdict)


class _StubResponse:
    def __init__(self, verdict):
        self.parsed_output = verdict
        self.stop_reason = "end_turn"


class _StubClient:
    def __init__(self, verdict, raises=None):
        self.messages = _StubMessages(verdict, raises)


class TestTheSlateActuallySurfacesSomething:
    """Without this, every test below is vacuously green.

    A wiring test whose fixture surfaces nothing asserts that nothing happened
    to nothing. Assert the precondition separately so a change that stops the
    row surfacing fails *here*, naming the cause, instead of quietly turning
    four other tests into no-ops.
    """

    def test_exactly_one_candidate_reaches_the_skeptic(self, conn, surfacing_slate):
        reviewer = _Reviewer()
        counts = run_pricing_pass(conn, surfacing_slate, now=NOW, review=reviewer)

        assert reviewer.calls == 1, (
            f"expected one surfaced row to review, got {reviewer.calls}. "
            f"Rows: {_rows(conn)}"
        )
        assert counts.skeptic_reviewed == 1

    def test_the_reviewed_row_is_the_one_with_the_edge(self, conn, surfacing_slate):
        reviewer = _Reviewer()
        run_pricing_pass(conn, surfacing_slate, now=NOW, review=reviewer)

        reviewed = reviewer.batches[0][0].recommendation
        assert reviewed.ticker == "KXMLBGAME-TESTPITNEW-PIT"
        assert reviewed.side == "yes"
        assert reviewed.surfaced

    def test_the_no_edge_rows_are_not_reviewed(self, conn, surfacing_slate):
        """Cost, not correctness -- and it is the larger of the two.

        A live pass builds ~100 rows and nearly all have no edge. Reviewing them
        all would buy a hundred "no"s a pass at 96 passes a day.
        """
        reviewer = _Reviewer()
        run_pricing_pass(conn, surfacing_slate, now=NOW, review=reviewer)

        assert len(_rows(conn)) == 4, "the slate should still record every candidate"
        assert reviewer.calls == 1


class TestReviewHappensBeforeAnythingIsPersisted:
    """The window this restructure exists to close.

    `apply_verdict` folds into `suppressed_reason`. If the row is already on
    disk when the Skeptic is asked, then for the duration of one Anthropic round
    trip `POST /api/orders` would find a row with a positive size and no reason
    and sell it. The endpoint reads the database, so "we have not applied the
    verdict yet" is not a state it can observe.
    """

    def test_no_orderable_row_exists_while_the_skeptic_is_being_asked(
        self, conn, surfacing_slate
    ):
        observed: list[list[dict]] = []
        reviewer = _Reviewer(
            verdict=_verdict("defect"),
            on_call=lambda _candidates: observed.append(_orderable(conn)),
        )

        run_pricing_pass(conn, surfacing_slate, now=NOW, review=reviewer)

        assert observed == [[]], (
            "an orderable row was already on disk when the Skeptic was asked "
            f"about it: {observed}"
        )

    def test_a_blocking_verdict_never_reaches_the_database_as_orderable(
        self, conn, surfacing_slate
    ):
        counts = run_pricing_pass(
            conn, surfacing_slate, now=NOW,
            review=_Reviewer(verdict=_verdict("defect")),
        )

        assert _orderable(conn) == []
        assert counts.surfaced == 0
        assert counts.skeptic_blocked == 1

        blocked = next(
            r for r in _rows(conn) if r["ticker"] == "KXMLBGAME-TESTPITNEW-PIT"
            and r["side"] == "yes"
        )
        assert blocked["suppressed_reason"] == "skeptic_defect"
        assert blocked["suggested_contracts"] == 0
        assert "Buy" not in blocked["reason_text"]
        assert "regulation time" in blocked["reason_text"]

    def test_a_plausible_verdict_leaves_the_row_surfaced(self, conn, surfacing_slate):
        """`plausible` is not approval, and must not read as a change.

        The Skeptic cannot clear a reason or add a contract. All it can do on a
        `plausible` verdict is nothing, and "nothing" has to be observable --
        otherwise a bug that dropped every verdict would look identical.
        """
        counts = run_pricing_pass(
            conn, surfacing_slate, now=NOW,
            review=_Reviewer(verdict=_verdict("plausible")),
        )

        assert counts.surfaced == 1
        assert counts.skeptic_reviewed == 1
        assert counts.skeptic_blocked == 0
        assert len(_orderable(conn)) == 1


class TestASkepticOutageDoesNotStopThePass:
    """A slate that silently stops being recorded is the worse failure.

    The record is the asset: 300 independent games at ~15 a day is three weeks
    of unbroken recording, so a day not recording is a day added to the earliest
    date this project can answer its own question. Losing agent commentary costs
    nothing by comparison.
    """

    def test_an_api_failure_records_the_slate_anyway(self, conn, surfacing_slate):
        def failing(candidates, **kwargs):
            return review_surfaced(
                candidates,
                config=AgentConfig(api_key="test-key"),
                client_factory=lambda config: _StubClient(
                    None, raises=RuntimeError("anthropic is down")
                ),
                **kwargs,
            )

        counts = run_pricing_pass(conn, surfacing_slate, now=NOW, review=failing)

        assert counts.recommendations == 4
        assert counts.surfaced == 1, "no verdict means no opinion, not a refusal"
        assert counts.skeptic_blocked == 0

    def test_a_prompt_that_cannot_be_built_is_isolated_to_its_own_row(
        self, conn, surfacing_slate
    ):
        """`evaluate` builds its prompt *before* the API call.

        So `structured_call`'s own None-on-failure contract cannot catch this
        one, and an exception raised inside `asyncio.gather` cancels the batch.
        Reproduced by handing the candidate a keyword `build_prompt` does not
        take, which is what a drifted field would look like.
        """
        candidate = ReviewCandidate(
            recommendation=_recommendation(),
            prompt_kwargs={"not_a_real_field": 1},
        )

        outcome = review_surfaced(
            [candidate],
            conn=conn,
            config=AgentConfig(api_key="test-key"),
            client_factory=lambda config: _StubClient(_verdict("defect")),
        )

        assert outcome.reviewed == 1
        assert outcome.blocked == 0
        assert outcome.recommendations[0] is candidate.recommendation

    def test_an_unconfigured_fleet_reviews_nothing_and_refuses_nothing(
        self, conn, surfacing_slate
    ):
        """The state on every instance without `ANTHROPIC_API_KEY` set.

        Including the live one until the secret is added, so this is the
        production behaviour today rather than a hypothetical.
        """
        counts = run_pricing_pass(conn, surfacing_slate, now=NOW)

        assert counts.skeptic_reviewed == 0
        assert counts.skeptic_blocked == 0
        assert counts.surfaced == 1


class TestTheAsyncSeamWorksWhereItIsActuallyCalledFrom:
    """`asyncio.run` would pass every other test in this file and fail live.

    `run_pricing_pass` is sync, but its production callers -- `run_once` and
    `run_quote_pass` -- are `async def` and call it directly. So on the deployed
    instance this executes inside a running event loop, which is the one place
    `asyncio.run` raises. Every test above calls the pass from sync code and
    would not have noticed.
    """

    def test_a_review_runs_from_inside_a_running_event_loop(
        self, conn, surfacing_slate
    ):
        async def as_the_runner_calls_it():
            return run_pricing_pass(
                conn, surfacing_slate, now=NOW,
                review=_Reviewer(verdict=_verdict("defect")),
            )

        counts = asyncio.run(as_the_runner_calls_it())

        assert counts.skeptic_reviewed == 1
        assert counts.skeptic_blocked == 1
        assert _orderable(conn) == []

    def test_the_same_review_runs_from_sync_code(self, conn, surfacing_slate):
        """The pair matters: one seam has to serve both callers.

        `scripts/run_chain.py` drives a pass without a loop and the scheduler
        drives one inside a loop. A fix for either case that breaks the other
        is not a fix.
        """
        counts = run_pricing_pass(
            conn, surfacing_slate, now=NOW,
            review=_Reviewer(verdict=_verdict("defect")),
        )

        assert counts.skeptic_blocked == 1


def _recommendation(**overrides) -> Recommendation:
    base = dict(
        created_ms=NOW,
        strategy_config_version=1,
        ticker="KXTEST-ABC",
        link_id=1,
        fair_price_id=1,
        side="yes",
        entry_ask_tenths=510,
        depth_at_ask=120.0,
        fair_probability=0.5569,
        model_probability=None,
        edge_tenths=29.2,
        fee_predicted=0.31,
        ev_net_dollars=1.47,
        kelly_fraction=0.25,
        suggested_contracts=12,
        reference_contracts=12,
        kalshi_quote_age_ms=0,
        odds_age_ms=424_317,
        suppressed_reason=None,
        reason_text=(
            "St. Louis Cardinals: consensus fair 55.7%, Kalshi asks 51c "
            "(+2.9c after fees). Buy 12."
        ),
    )
    base.update(overrides)
    return Recommendation(**base)


class TestTheRowIsRestatedConsistently:
    """Three fields move together or two screens disagree about one row."""

    def test_a_blocked_row_is_no_longer_orderable_by_either_predicate(self):
        row = with_added_suppression(
            _recommendation(), reason="skeptic_defect", problem="a stated reason"
        )

        # The order endpoint refuses on the reason; the Board splits on the
        # size. Both have to say no, or the screen offers what the server
        # refuses with a 422.
        assert row.suppressed_reason == "skeptic_defect"
        assert row.suggested_contracts == 0
        assert row.surfaced is False
        assert row.ev_net_dollars == 0.0
        # And the fourth: the gate counts `reference_contracts`, so a row the
        # fleet vetoed must not go on accumulating evidence for a bet the
        # strategy declined to make. ADR 0005, arriving through a column that
        # did not exist when it was written.
        assert row.reference_contracts == 0

    def test_the_decision_clause_is_replaced_not_appended(self):
        row = with_added_suppression(
            _recommendation(), reason="skeptic_defect", problem="a stated reason"
        )

        assert "Buy 12" not in row.reason_text
        assert row.reason_text.endswith("Not actionable -- a stated reason.")

    def test_a_team_name_containing_a_full_stop_keeps_its_head_intact(self):
        """The reason the split is from the right.

        "St. Louis Cardinals" puts a ". " inside the head, so a left-hand split
        would truncate the row's own description to "St." and lose the prices --
        on the card whose entire job is showing them.
        """
        row = with_added_suppression(
            _recommendation(), reason="skeptic_defect", problem="a stated reason"
        )

        assert row.reason_text.startswith(
            "St. Louis Cardinals: consensus fair 55.7%, Kalshi asks 51c "
            "(+2.9c after fees)."
        )

    def test_the_agents_verdict_is_never_the_only_thing_standing(self, conn):
        """A `None` verdict cannot un-suppress a row the checks refused."""
        already = _recommendation(
            suppressed_reason="stale_odds", suggested_contracts=0
        )
        client = _StubClient(_verdict("plausible"))
        outcome = review_surfaced(
            [ReviewCandidate(recommendation=already, prompt_kwargs=_prompt_kwargs())],
            conn=conn,
            config=AgentConfig(api_key="test-key"),
            client_factory=lambda config: client,
        )

        assert client.messages.seen == 1, "the verdict path must actually have run"
        assert outcome.recommendations[0].suppressed_reason == "stale_odds"
        assert outcome.blocked == 0


class TestTheReviewedSetAndTheVerdictsCannotDrift:
    """The one failure here that money could reach.

    The runner matches verdicts to rows by position. A reviewer returning a
    short list would make `zip` drop the tail silently, and the dropped rows
    would persist as surfaced having never been reviewed -- the exact state this
    whole restructure exists to make impossible.
    """

    def test_a_short_reply_refuses_the_slate_rather_than_persisting_it(
        self, conn, surfacing_slate
    ):
        def drops_the_answer(candidates, **kwargs):
            return ReviewOutcome(recommendations=[], reviewed=len(candidates))

        with pytest.raises(RuntimeError, match="cannot be matched"):
            run_pricing_pass(
                conn, surfacing_slate, now=NOW, review=drops_the_answer
            )

        assert _rows(conn) == [], "nothing should have been written"


class TestHealthSaysWhetherTheFleetIsConfigured:
    """The only way to tell, from a phone, that the Fly secret took effect.

    An unconfigured fleet is silent by design -- `AgentConfig.from_env()`
    returns `None` and every row comes back unreviewed -- and that is also what
    a working Skeptic looks like on a slate with nothing surfaced, which is
    every slate so far. So without this field, "the key is set" and "the
    process can see the key" cannot be told apart from outside.
    """

    def _health(self, monkeypatch, key):
        from fastapi.testclient import TestClient

        from backend.api.routes import create_app
        from backend.config import AppConfig, GateConfig

        if key is None:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        else:
            monkeypatch.setenv("ANTHROPIC_API_KEY", key)

        app = create_app(
            AppConfig(instance_mode="demo", db_path=":memory:"),
            gate_config=GateConfig(live_trading_enabled=False),
        )
        with TestClient(app) as client:
            return client.get("/api/health").json()

    def test_it_is_false_without_the_secret(self, monkeypatch):
        assert self._health(monkeypatch, None)["agent_fleet_configured"] is False

    def test_it_is_true_once_the_secret_is_set(self, monkeypatch):
        assert self._health(monkeypatch, "sk-ant-x")["agent_fleet_configured"] is True

    def test_it_never_carries_the_credential(self, monkeypatch):
        """A health endpoint is public on both instances -- Fly's own check
        needs it to be. It reports a boolean or it reports a leak."""
        body = self._health(monkeypatch, "sk-ant-secret-value")
        assert "sk-ant-secret-value" not in json.dumps(body)
