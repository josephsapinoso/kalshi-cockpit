"""The ceiling on Anthropic spend, and the refusal it produces.

These tests exist because `backend/agents/` shipped a billed fan-out with no
cap of any kind: `review._review_batch` gathered over every surfaced candidate,
on a loop that wakes up to ~96 times a day, with `ANTHROPIC_API_KEY` set on the
live instance. The only binding guard was that no row had ever surfaced -- a
measurement outcome, not a configuration value.

What this harness does NOT establish
------------------------------------
**That any of this has run against Anthropic.** Every call here goes to a stub
client. What is verified is that the *number* of calls is bounded and that the
rows past the bound are refused; whether a real `messages.parse` costs 4.5 cents
is arithmetic in `agents/base.py` and is not tested by anything, here or
elsewhere. Nothing in this repo reads an Anthropic-reported balance, so a drift
between this count and the invoice is invisible.

**That the defaults are the right numbers.** They are not measured. `surfaced`
has been 0 on every live pass, so the population that would calibrate a per-pass
ceiling does not exist. What is tested is that the configured number is the
number enforced, and that a malformed one refuses rather than defaults.

**That a refused row is visible to a human.** It is suppressed and carries a
stated reason, and `POST /api/orders` refuses on any reason -- that join is
established in `test_order_record.py` and deliberately not re-walked here. What
no test covers is whether the *card* renders the distinction between "the
Skeptic cleared this" and "nobody looked", which is `frontend/`'s question.

**That the day boundary matches the odds budget's in production.** Both default
to 10:00 UTC and the agent budget takes its hour from the same
`odds/timing.py` constant, but nothing asserts that a deployment which overrides
`ODDS_BUDGET_DAY_START_UTC_HOUR` also moves this one -- it does not, and that is
a known gap rather than a tested property.

Mutations run against this file
-------------------------------
Nine guards were disabled one at a time and `tests/test_agent_budget.py` plus
`tests/test_agent_wiring.py` re-run against each. **All nine went red**, and the
specific failure is recorded in the class docstring that owns the guard. One
(the required `conn`) went red for a different reason than expected, which is
recorded rather than tidied away -- see
`TestTheMeterCannotBeReachedWithoutADatabase`.
"""

from __future__ import annotations

import pytest

from backend.agents.base import (
    DEFAULT_MAX_CALLS_PER_DAY,
    DEFAULT_MAX_CALLS_PER_PASS,
    AgentConfig,
)
from backend.agents.budget import AgentBudget
from backend.agents.review import ReviewCandidate, review_surfaced
from backend.agents.skeptic import SkepticVerdict
from backend.config import ConfigError
from backend.engine import Recommendation
from backend.store import db

# 2026-08-11 14:00Z -- comfortably inside the sports day that opens at 10:00Z,
# so "earlier today" and "yesterday" are both expressible without straddling a
# boundary and making the test about arithmetic rather than about the ceiling.
NOW = 1_786_557_600_000
_ONE_HOUR = 3_600_000


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "budget.db")
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Stubs. No call in this file leaves the process.
# ---------------------------------------------------------------------------


def _verdict(kind: str = "plausible") -> SkepticVerdict:
    return SkepticVerdict(
        verdict=kind,
        primary_concern="checked settlement rules and found nothing.",
        checks_performed=["compared settlement rules"],
        recommended_action="investigate",
        confidence=0.6,
    )


class _StubMessages:
    def __init__(self, verdict):
        self._verdict = verdict
        self.seen = 0

    async def parse(self, **kwargs):
        self.seen += 1
        if self._verdict is None:
            # What `structured_call` sees when the model returns nothing it can
            # validate: a 200 with no parseable output, not an exception.
            return _StubResponse(None)
        return _StubResponse(self._verdict)


class _StubResponse:
    def __init__(self, verdict):
        self.parsed_output = verdict
        self.stop_reason = "end_turn"


class _StubClient:
    def __init__(self, verdict):
        self.messages = _StubMessages(verdict)


def _recommendation(index: int = 0, **overrides) -> Recommendation:
    """A surfaced row: no suppression reason and a positive size.

    Surfaced is the only population `review_surfaced` is ever handed, and it is
    also the only one `with_added_suppression` can restate -- it splits
    `reason_text` on the decision clause that only a surfaced row has.
    """
    base = dict(
        created_ms=NOW,
        strategy_config_version=1,
        ticker=f"KXTEST-{index:03d}",
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


def _prompt_kwargs(**overrides) -> dict:
    """A valid `skeptic.build_prompt` keyword set.

    Spelled out rather than left empty for the reason `test_agent_wiring.py`
    gives: an empty mapping raises inside `evaluate`, the isolation guard turns
    that into a `None` verdict, and the test would then assert the right
    outcome for entirely the wrong reason -- passing even if verdicts stopped
    being requested at all.
    """
    base = dict(
        ticker="KXTEST-000",
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


def _candidates(n: int) -> list[ReviewCandidate]:
    return [
        ReviewCandidate(
            recommendation=_recommendation(i),
            prompt_kwargs=_prompt_kwargs(ticker=f"KXTEST-{i:03d}"),
        )
        for i in range(n)
    ]


def _review(conn, candidates, *, per_pass, per_day, verdict=_verdict(), now=NOW):
    client = _StubClient(verdict)
    outcome = review_surfaced(
        candidates,
        conn=conn,
        config=AgentConfig(
            api_key="test-key",
            max_calls_per_pass=per_pass,
            max_calls_per_day=per_day,
        ),
        client_factory=lambda config: client,
        now=now,
    )
    return outcome, client


def _rows(conn):
    return conn.execute(
        "SELECT * FROM agent_calls ORDER BY id"
    ).fetchall()


# ---------------------------------------------------------------------------


class TestThePassCeilingBoundsOneFanOut:
    """The batch is one `asyncio.gather`; without a cap it is one unbounded one.

    Mutation: `reviewable = list(candidates[:allowance])` -> `list(candidates)`.
    `test_a_batch_larger_than_the_ceiling_makes_only_that_many_calls` went RED
    (10 calls, expected 3), as did both refusal tests below.
    """

    def test_a_batch_larger_than_the_ceiling_makes_only_that_many_calls(self, conn):
        _, client = _review(conn, _candidates(10), per_pass=3, per_day=100)

        assert client.messages.seen == 3

    def test_the_batch_is_bounded_before_the_calls_go_out_not_after(self, conn):
        """Reserving after the fact would bound the count and not the spend.

        A meter that recorded 10 calls and then refused the 11th has already
        paid for 10. The assertion that distinguishes the two designs is the
        stub's own counter, not the table.
        """
        _, client = _review(conn, _candidates(50), per_pass=2, per_day=100)

        assert client.messages.seen == 2
        assert len(_rows(conn)) == 2

    def test_a_batch_inside_the_ceiling_is_reviewed_whole(self, conn):
        """Anti-vacuity. A ceiling that refuses everything passes every test
        above while making the tool useless, so the affordable case is asserted
        separately."""
        outcome, client = _review(conn, _candidates(3), per_pass=8, per_day=100)

        assert client.messages.seen == 3
        assert outcome.reviewed == 3
        assert outcome.unreviewed == 0


class TestWhatTheCeilingRefusesComesBackRefused:
    """Truncation-in-silence is the failure this is designed against.

    Mutation: `_refuse_unreviewed` returning `candidate.recommendation`
    untouched. `test_an_unreviewed_row_is_not_orderable` and
    `test_an_unreviewed_row_is_distinguishable_from_a_cleared_one` both went
    RED. Mutation: dropping the `for candidate in refused:` loop entirely --
    `test_no_row_is_dropped` went RED with 3 rows for 10 candidates, and
    `runner._review_and_persist` would have raised on the length mismatch.
    """

    def test_no_row_is_dropped(self, conn):
        outcome, _ = _review(conn, _candidates(10), per_pass=3, per_day=100)

        assert len(outcome.recommendations) == 10
        assert outcome.reviewed == 3
        assert outcome.unreviewed == 7

    def test_an_unreviewed_row_is_not_orderable(self, conn):
        outcome, _ = _review(conn, _candidates(10), per_pass=3, per_day=100)

        for row in outcome.recommendations[3:]:
            assert row.suppressed_reason == "skeptic_unreviewed"
            assert row.suggested_contracts == 0
            assert row.reference_contracts == 0
            assert row.surfaced is False

    def test_an_unreviewed_row_is_distinguishable_from_a_cleared_one(self, conn):
        """The claim in requirement form: a row nobody attacked must not read
        like a row the Skeptic tried and failed to break.

        A `plausible` verdict leaves `suppressed_reason` at `None` -- so if the
        refusal were silent, the two populations would be byte-identical on the
        field the order endpoint reads.
        """
        outcome, _ = _review(
            conn, _candidates(4), per_pass=2, per_day=100, verdict=_verdict("plausible")
        )

        cleared = outcome.recommendations[:2]
        unreviewed = outcome.recommendations[2:]

        assert [r.suppressed_reason for r in cleared] == [None, None]
        assert {r.suppressed_reason for r in unreviewed} == {"skeptic_unreviewed"}

    def test_the_refusal_says_which_ceiling_bound(self, conn):
        outcome, _ = _review(conn, _candidates(10), per_pass=3, per_day=100)

        text = outcome.recommendations[9].reason_text
        assert "at most 3 Anthropic calls" in text, text
        assert "asked for 10" in text, text

    def test_a_reason_the_row_already_had_is_kept_not_replaced(self, conn):
        """An unreviewed row that was already suppressed for something else must
        carry both, the same way `apply_verdict` appends rather than overwrites.
        Losing the original reason would rewrite why the tool refused the bet.
        """
        candidate = ReviewCandidate(
            recommendation=_recommendation(0, suppressed_reason="stale_odds"),
            prompt_kwargs=_prompt_kwargs(),
        )
        outcome, _ = _review(conn, [candidate], per_pass=0, per_day=100)

        assert outcome.recommendations[0].suppressed_reason == (
            "stale_odds,skeptic_unreviewed"
        )


class TestTheDailyCeilingBoundsTheDay:
    """96 passes at the per-pass cap is 768 calls; the day is the real bound.

    Mutation: `min(state.per_pass_budget, state.remaining_today)` ->
    `state.per_pass_budget`. `test_calls_already_made_today_reduce_the_allowance`
    and `test_a_zero_daily_budget_makes_no_calls_at_all` both went RED.
    """

    def test_calls_already_made_today_reduce_the_allowance(self, conn):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        for _ in range(7):
            meter.record(
                called_ms=NOW - _ONE_HOUR, agent="skeptic", model="claude-opus-5"
            )

        _, client = _review(conn, _candidates(8), per_pass=8, per_day=10)

        assert client.messages.seen == 3

    def test_the_daily_count_survives_a_fresh_budget_object(self, conn):
        """The durability claim, at the granularity a test can reach.

        A per-process counter is what `PassCounts.skeptic_reviewed` already is,
        and it resets on every deploy -- so a daily cap built on one would reset
        with it. Reading the count back through a budget that shares nothing
        with the one that wrote it is the closest a unit test gets to a restart.
        """
        writer = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        for _ in range(4):
            writer.record(called_ms=NOW, agent="skeptic", model="claude-opus-5")

        reader = AgentBudget(conn, per_pass_budget=8, daily_budget=10)

        assert reader.state(NOW).spent_today == 4
        assert reader.allowance(NOW) == 6

    def test_yesterdays_calls_do_not_count_against_today(self, conn):
        """Anti-vacuity in the other direction: a window that never rolls is a
        lifetime cap wearing a daily cap's name, and it would eventually refuse
        everything forever."""
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        for _ in range(10):
            meter.record(
                called_ms=NOW - 30 * _ONE_HOUR,
                agent="skeptic",
                model="claude-opus-5",
            )

        assert meter.state(NOW).spent_today == 0
        assert meter.allowance(NOW) == 8

    def test_a_zero_daily_budget_makes_no_calls_at_all(self, conn):
        """Zero is a supported setting, not a misconfiguration -- it holds the
        fleet at no spend without unsetting the key."""
        outcome, client = _review(conn, _candidates(4), per_pass=8, per_day=0)

        assert client.messages.seen == 0
        assert outcome.reviewed == 0
        assert outcome.unreviewed == 4
        assert _rows(conn) == []

    def test_the_daily_refusal_is_the_one_reported_when_both_would_bind(self, conn):
        """Hardest to recover from first, as in `odds/budget.py`. A per-pass
        refusal needs a smaller batch; a daily one needs tomorrow, and naming
        the wrong one sends the operator to the wrong lever."""
        meter = AgentBudget(conn, per_pass_budget=3, daily_budget=4)
        for _ in range(3):
            meter.record(called_ms=NOW, agent="skeptic", model="claude-opus-5")

        reason = meter.refusal_reason(10, NOW)

        assert reason is not None
        assert "already made today" in reason
        assert "at most" not in reason


class TestEveryCallIsRecorded:
    """The table is both the meter and the only durable record the fleet ran.

    Mutation: skipping the `meter.record(...)` call when `verdict is None`.
    `test_a_call_that_produced_no_verdict_still_counts` went RED -- which is the
    exact hole that would let an Anthropic outage spend the day for free
    against the ceiling, retry after retry.
    """

    def test_a_reviewed_row_writes_one_row_with_its_verdict(self, conn):
        _review(conn, _candidates(2), per_pass=8, per_day=100, verdict=_verdict("defect"))

        rows = _rows(conn)
        assert len(rows) == 2
        assert [r["agent"] for r in rows] == ["skeptic", "skeptic"]
        assert [r["model"] for r in rows] == ["claude-opus-5", "claude-opus-5"]
        assert [r["verdict"] for r in rows] == ["defect", "defect"]
        assert [r["blocked"] for r in rows] == [1, 1]
        assert [r["ticker"] for r in rows] == ["KXTEST-000", "KXTEST-001"]

    def test_a_call_that_produced_no_verdict_still_counts(self, conn):
        """It cost money and it consumed the day's allowance either way."""
        _, client = _review(conn, _candidates(3), per_pass=8, per_day=100, verdict=None)

        assert client.messages.seen == 3
        assert len(_rows(conn)) == 3

    def test_no_verdict_records_NULL_and_never_zero(self, conn):
        """`unreadable resolves to None, never 0` -- at the storage layer.

        `blocked = 0` means "the Skeptic looked and did not block". A call that
        said nothing must not be counted as one that cleared the row, or a
        future read of this table would report a review that never happened.
        """
        _review(conn, _candidates(1), per_pass=8, per_day=100, verdict=None)

        row = _rows(conn)[0]
        assert row["verdict"] is None
        assert row["blocked"] is None

    def test_a_row_the_ceiling_refused_writes_nothing(self, conn):
        """Absence does not belong in the table that means presence -- the same
        rule `odds_sweep_log` exists for. A refusal row here would be counted
        as spend by the meter reading it, so the ceiling would tighten itself."""
        _review(conn, _candidates(5), per_pass=2, per_day=100)

        assert len(_rows(conn)) == 2


class TestTheCeilingsAreReadFromTheEnvironment:
    """A cap nothing can configure is a constant, and a cap that defaults
    silently is the defect one level down.

    Mutation: `_positive_int_env` returning `default` on `ValueError` instead of
    raising. `test_a_malformed_ceiling_refuses_to_load` went RED.
    """

    def test_the_documented_defaults_are_what_an_unset_environment_gives(
        self, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("AGENT_MAX_CALLS_PER_PASS", raising=False)
        monkeypatch.delenv("AGENT_MAX_CALLS_PER_DAY", raising=False)

        config = AgentConfig.from_env()

        assert config.max_calls_per_pass == DEFAULT_MAX_CALLS_PER_PASS == 8
        assert config.max_calls_per_day == DEFAULT_MAX_CALLS_PER_DAY == 24

    def test_the_environment_actually_overrides_the_defaults(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("AGENT_MAX_CALLS_PER_PASS", "2")
        monkeypatch.setenv("AGENT_MAX_CALLS_PER_DAY", "5")

        config = AgentConfig.from_env()

        assert (config.max_calls_per_pass, config.max_calls_per_day) == (2, 5)

    def test_a_malformed_ceiling_refuses_to_load(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("AGENT_MAX_CALLS_PER_DAY", "twenty")

        with pytest.raises(ConfigError, match="AGENT_MAX_CALLS_PER_DAY"):
            AgentConfig.from_env()

    def test_a_negative_ceiling_refuses_to_load(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("AGENT_MAX_CALLS_PER_PASS", "-1")

        with pytest.raises(ConfigError, match="AGENT_MAX_CALLS_PER_PASS"):
            AgentConfig.from_env()

    def test_no_key_still_means_no_config_and_no_spend(self, monkeypatch):
        """The ceilings must not turn the unconfigured case into a raise. Every
        local run and the demo instance take this path."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("AGENT_MAX_CALLS_PER_DAY", "twenty")

        assert AgentConfig.from_env() is None


class TestTheMeterCannotBeReachedWithoutADatabase:
    """The signature is the enforcement.

    An optional `conn` would let a caller reach the billed path with the meter
    absent, which is a restatement of the defect this module was changed to fix.

    **Mutation: `conn` given a default of `None`. It went RED -- but not the way
    this docstring predicted, and the difference is worth keeping.** The
    expectation was that the guard was purely Python's argument binding and that
    the mutation would therefore be caught only by the test below. What actually
    happened is that the failure moved *inside* the meter:
    `AgentBudget.state` raised `AttributeError: 'NoneType' object has no
    attribute 'execute'`.

    That is a strictly worse failure than the one the signature produces, and it
    is why the parameter stays required rather than being defended by a runtime
    check. A `TypeError` at the call site fails before the pricing pass has done
    any work. An `AttributeError` two frames into the budget fails *after* the
    slate has been judged and before anything is persisted -- so the cost of a
    caller forgetting the connection would be a day of the evidence record, not
    a stack trace. The loud, early failure is the design.
    """

    def test_review_surfaced_refuses_to_be_called_without_a_connection(self):
        with pytest.raises(TypeError, match="conn"):
            review_surfaced(  # type: ignore[call-arg]
                _candidates(1), config=AgentConfig(api_key="test-key")
            )

    def test_an_empty_batch_still_needs_no_database_work(self, conn):
        """The cheap path stays cheap: no candidates, no meter read, no row."""
        outcome = review_surfaced([], conn=conn)

        assert outcome.recommendations == []
        assert _rows(conn) == []
