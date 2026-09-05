"""The ceiling on Anthropic spend, and the refusal it produces.

These tests exist because `backend/agents/` shipped a billed fan-out with no
cap of any kind: the Skeptic's caller gathered over every surfaced candidate,
on a loop that wakes up to ~96 times a day, with `ANTHROPIC_API_KEY` set on the
live instance. The only binding guard was that no row had ever surfaced -- a
measurement outcome, not a configuration value -- and on 2026-08-16 it stopped
binding: 24 metered Opus calls in 4m22s, the whole daily cap (ADR 0062 §3).

**The meter's one live caller is now the scout desk.** `review_surfaced`, the
caller this file was written around, was retired as the pass default on
2026-08-21 (ADR 0062) and deleted on 2026-09-05 together with `skeptic.py`
(`docs/adr/0106-the-historian-and-the-skeptic-are-deleted-and-the-desk-has-been-convened.md`).
The tests that drove the meter *through* it -- the per-pass fan-out width, the
reservation surviving a mid-batch crash, the reserve/settle row per verdict,
the required `conn`, the "which ceiling bound?" raise -- were tests of the
deleted function's contract and went with it. What remains is `AgentBudget`'s
own contract, driven directly, plus the refusal `review_retired` produces and
the runner's length guard on the seam. The desk's reserve-before-call is
`tests/test_scout_desk.py`'s to pin.

What this harness does NOT establish
------------------------------------
**That any of this has run against Anthropic.** Nothing here leaves the
process. What is verified is that the *number* of calls a day allows is
bounded, that a refused row comes back refused, and that a settled call
records what it consumed.

**Nothing here checks what a call costs**, and the number it would check
against is itself unverified: the dollar figures in `agents/base.py` rest on a
claude-opus-5 list price marked `[ASSUMED, uncited]` there, which no fixture,
invoice or API response in this repo confirms. Nothing reads an
Anthropic-reported balance either, so a drift between this count and the real
invoice is invisible in both directions at once. The count is the only claim
this harness can make good on -- which is why `agents/base.py` puts the safety
argument on the count and not on the dollars.

**That the defaults are the right numbers.** They are not measured. What is
tested is that the configured number is the number enforced, and that a
malformed one refuses rather than defaults.

**That a refused row is visible to a human.** It is suppressed and carries a
stated reason, and `POST /api/orders` refuses on any reason -- that join is
established in `test_order_record.py` and deliberately not re-walked here.

**That the day boundary matches the odds budget's in production.** Both default
to 10:00 UTC and the agent budget takes its hour from the same
`odds/timing.py` constant, but nothing asserts that a deployment which overrides
`ODDS_BUDGET_DAY_START_UTC_HOUR` also moves this one -- it does not, and that is
a known gap rather than a tested property.

**That one candidate is one HTTP request, end to end.** `build_client` is
asserted to set `max_retries=0` on a real SDK object here, and
`tests/test_has_callers.py` pins the keyword at the source. The stub that used
to model the SDK's retry loop drove `review_surfaced` and was deleted with it;
the join is the SDK's documented contract, not a test.

Mutations run against this file
-------------------------------
Recorded in the class docstring that owns each guard, with the date. The
mutation history of the deleted `review_surfaced` tests -- fourteen guards,
thirteen red -- is in this file at `ef8434b` and is not restated here, because
a mutation record for a test that no longer exists is a claim nothing can
re-check.
"""

from __future__ import annotations

import pytest

from backend.agents.base import (
    DEFAULT_MAX_CALLS_PER_DAY,
    DEFAULT_MAX_CALLS_PER_PASS,
    AgentConfig,
    CallUsage,
    build_client,
)
from backend.agents.budget import AgentBudget
from backend.agents.review import ReviewCandidate, ReviewOutcome, review_retired
from backend.config import ConfigError
from backend.engine import Recommendation
from backend import runner
from backend.runner import PassCounts, _review_and_persist
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


def _sdk_max_retries() -> int:
    """What `build_client` actually configures on a real SDK client.

    Read from the SDK object rather than restated as a literal, so the test
    cannot keep asserting a number the production path stopped using.
    """
    return build_client(AgentConfig(api_key="test-key-not-used")).max_retries


def _recommendation(index: int = 0, **overrides) -> Recommendation:
    """A surfaced row: no suppression reason and a positive size.

    Surfaced is the only population the seam hands a reviewer, and it is also
    the only one `with_added_suppression` can restate -- it splits
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


def _candidates(n: int) -> list[ReviewCandidate]:
    return [ReviewCandidate(recommendation=_recommendation(i)) for i in range(n)]


def _rows(conn):
    return conn.execute(
        "SELECT * FROM agent_calls ORDER BY id"
    ).fetchall()


def _spend_a_pass(meter: AgentBudget, requested: int, *, now: int = NOW):
    """One pass's worth of reserving, the way a metered caller does it.

    Asks the meter what it may afford, reserves exactly that many rows, and
    returns `(reserved, refused)`. Written here rather than imported because
    the caller it imitates is deleted; what it exercises is `allowance` and
    `reserve`, in the order any metered caller must take them -- the answer
    first, the rows before the requests go out.
    """
    allowance = meter.allowance(now)
    reserved = min(allowance, requested)
    for _ in range(reserved):
        meter.reserve(called_ms=now, agent="skeptic", model="claude-opus-5")
    return reserved, requested - reserved


# ---------------------------------------------------------------------------


class TestOneCandidateIsExactlyOneRequest:
    """The meter counts candidates. Only `max_retries=0` makes that a bill.

    The installed SDK (`anthropic` 0.120.2) defaults to `DEFAULT_MAX_RETRIES =
    2` and retries 408/409/429/>=500 and connection errors. `structured_call`
    collapses every attempt into one return value and `AgentBudget` records once
    per candidate, so under the default a 24/day ceiling permitted up to **72
    billed requests** with the other 48 invisible to the meter and to every
    assertion in this file.

    Mutation: `build_client` -> `anthropic.AsyncAnthropic(api_key=...)` (drop
    `max_retries=0`). `test_build_client_does_not_let_the_sdk_retry` went RED
    (2, expected 0) on 2026-08-11 and again on 2026-09-05.
    """

    def test_build_client_does_not_let_the_sdk_retry(self):
        """The choice, asserted against the real SDK object rather than a stub.

        `max_retries=1` would keep coverage on a transient failure at the cost
        of exactness -- 24 counted calls would be 24 to 48 requests with
        nothing able to say which. `0` was chosen because the retry already
        exists one level up, at the caller, where `agent_calls` sees it.
        """
        assert _sdk_max_retries() == 0


class TestAGuardIsNotAGuardUntilItHasFired:
    """A raise that had never been raised by anything.

    `runner.py`'s length-mismatch check was only ever asserted as a *side
    effect* of another test's mutation. By this repo's rule -- every guard is
    verified by disabling it and watching the test fail -- it was decoration,
    in the money path, in a commit whose message said nine guards had been
    mutated.

    Mutation: delete the length-mismatch `raise RuntimeError` in
    `runner._review_and_persist`. `test_a_short_review_result_refuses_to_persist`
    went RED, and the tail row persisted **surfaced and unreviewed** -- `zip`
    dropped it without a word. (`review.py`'s "which ceiling bound?" raise,
    which this class also used to drive, was deleted with `review_surfaced`.)
    """

    def test_a_short_review_result_refuses_to_persist(self, conn):
        """`amended = dict(zip(positions, outcome.recommendations))`.

        A short list makes `zip` drop the tail silently, and the dropped rows
        persist as surfaced without ever having been reviewed. That is the one
        failure in `_review_and_persist` that money can reach.
        """
        pending = _candidates(3)

        def _short_review(candidates, *, conn, now):
            kept = [c.recommendation for c in candidates][:-1]
            return ReviewOutcome(
                recommendations=kept, reviewed=len(kept), blocked=0, unreviewed=0
            )

        with pytest.raises(RuntimeError, match="cannot be matched to their verdicts"):
            _review_and_persist(
                conn,
                pending,
                counts=PassCounts(),
                review=_short_review,
                now=NOW,
            )

    def test_a_matching_review_result_persists(self, conn, monkeypatch):
        """Anti-vacuity: a guard that raised on the happy path would stop the
        pricing pass dead, and every test above it would still be green.

        `persist_if_changed` is stubbed because this is a test of the length
        guard, not of persistence -- the real one needs `link_id` and
        `fair_price_id` rows that `_recommendation` invents, and building that
        fixture here would make the test about foreign keys.
        """
        monkeypatch.setattr(runner, "persist_if_changed", lambda conn, rec: rec)
        pending = _candidates(3)

        def _whole_review(candidates, *, conn, now):
            rows = [c.recommendation for c in candidates]
            return ReviewOutcome(
                recommendations=rows, reviewed=len(rows), blocked=0, unreviewed=0
            )

        counts = _review_and_persist(
            conn, pending, counts=PassCounts(), review=_whole_review, now=NOW
        )

        assert counts.recommendations == 3
        assert counts.surfaced == 3


class TestARefusedRowComesBackRefused:
    """Truncation-in-silence is the failure this is designed against.

    `review_retired` is the pass default (ADR 0062). Every surfaced row it is
    handed comes back with `skeptic_unreviewed` folded into its reason and
    its size zeroed -- a row nobody attacked must not be indistinguishable
    from one a reviewer cleared, and it must not be sellable.

    Mutation, 2026-09-05: `_refuse_unreviewed` returning
    `candidate.recommendation` untouched. `test_an_unreviewed_row_is_not_
    orderable`, `test_the_refusal_says_why` and `test_a_reason_the_row_
    already_had_is_kept_not_replaced` went RED; `test_no_row_is_dropped`
    stayed green, which is correct -- the count is `len(candidates)` and does
    not depend on the restatement.
    """

    def test_no_row_is_dropped(self, conn):
        outcome = review_retired(_candidates(10), conn=conn)

        assert len(outcome.recommendations) == 10
        assert outcome.reviewed == 0
        assert outcome.unreviewed == 10

    def test_an_unreviewed_row_is_not_orderable(self, conn):
        outcome = review_retired(_candidates(10), conn=conn)

        for row in outcome.recommendations:
            assert row.suppressed_reason == "skeptic_unreviewed"
            assert row.suggested_contracts == 0
            assert row.reference_contracts == 0
            assert row.surfaced is False

    def test_the_refusal_says_why(self, conn):
        outcome = review_retired(_candidates(1), conn=conn)

        text = outcome.recommendations[0].reason_text
        assert "retired (ADR 0062)" in text, text
        assert "Buy" not in text, text

    def test_a_reason_the_row_already_had_is_kept_not_replaced(self, conn):
        """An unreviewed row that was already suppressed for something else must
        carry both. Losing the original reason would rewrite why the tool
        refused the bet."""
        candidate = ReviewCandidate(
            recommendation=_recommendation(0, suppressed_reason="stale_odds"),
        )
        outcome = review_retired([candidate], conn=conn)

        assert outcome.recommendations[0].suppressed_reason == (
            "stale_odds,skeptic_unreviewed"
        )

    def test_it_reserves_nothing(self, conn):
        """Absence does not belong in the table that means presence. A row
        here would be counted as spend by the meter reading it."""
        review_retired(_candidates(5), conn=conn)

        assert _rows(conn) == []


class TestTheDailyCeilingBoundsTheDay:
    """The daily cap is the money control, and it is the only one.

    `min(per_pass, remaining_today)` puts both ceilings in the same `min()`,
    so "96 passes at the per-pass cap" is unreachable by any configuration.
    See `TestThePerPassCapDistributesTheDayItDoesNotShrinkIt` for what the
    per-pass cap does instead.

    Mutation, 2026-08-11: `min(state.per_pass_budget, state.remaining_today)`
    -> `state.per_pass_budget`. `test_calls_already_made_today_reduce_the_
    allowance` and `test_a_zero_daily_budget_allows_no_calls_at_all` both
    went RED. Re-run 2026-09-05 against the re-pointed tests: both RED again,
    and `test_the_daily_count_survives_a_fresh_budget_object` with them.
    """

    def test_calls_already_made_today_reduce_the_allowance(self, conn):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        for _ in range(7):
            meter.reserve(
                called_ms=NOW - _ONE_HOUR, agent="skeptic", model="claude-opus-5"
            )

        assert meter.allowance(NOW) == 3
        assert _spend_a_pass(meter, 8) == (3, 5)

    def test_the_daily_count_survives_a_fresh_budget_object(self, conn):
        """The durability claim, at the granularity a test can reach.

        A per-process counter is what `PassCounts.skeptic_reviewed` already is,
        and it resets on every deploy -- so a daily cap built on one would reset
        with it. Reading the count back through a budget that shares nothing
        with the one that wrote it is the closest a unit test gets to a restart.
        """
        writer = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        for _ in range(4):
            writer.reserve(called_ms=NOW, agent="skeptic", model="claude-opus-5")

        reader = AgentBudget(conn, per_pass_budget=8, daily_budget=10)

        assert reader.state(NOW).spent_today == 4
        assert reader.allowance(NOW) == 6

    def test_yesterdays_calls_do_not_count_against_today(self, conn):
        """Anti-vacuity in the other direction: a window that never rolls is a
        lifetime cap wearing a daily cap's name, and it would eventually refuse
        everything forever."""
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        for _ in range(10):
            meter.reserve(
                called_ms=NOW - 30 * _ONE_HOUR,
                agent="skeptic",
                model="claude-opus-5",
            )

        assert meter.state(NOW).spent_today == 0
        assert meter.allowance(NOW) == 8

    def test_a_zero_daily_budget_allows_no_calls_at_all(self, conn):
        """Zero is a supported setting, not a misconfiguration -- it holds the
        fleet at no spend without unsetting the key."""
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=0)

        assert meter.allowance(NOW) == 0
        assert meter.refusal_reason(4, NOW) is not None
        assert _spend_a_pass(meter, 4) == (0, 4)
        assert _rows(conn) == []

    def test_the_daily_refusal_is_the_one_reported_when_both_would_bind(self, conn):
        """Hardest to recover from first, as in `odds/budget.py`. A per-pass
        refusal needs a smaller batch; a daily one needs tomorrow, and naming
        the wrong one sends the operator to the wrong lever."""
        meter = AgentBudget(conn, per_pass_budget=3, daily_budget=4)
        for _ in range(3):
            meter.reserve(called_ms=NOW, agent="skeptic", model="claude-opus-5")

        reason = meter.refusal_reason(10, NOW)

        assert reason is not None
        assert "already made today" in reason
        assert "at most" not in reason


class TestThePerPassCapDistributesTheDayItDoesNotShrinkIt:
    """What `AGENT_MAX_CALLS_PER_PASS` is for, stated as arithmetic.

    Three files claimed "96 passes at 8 calls each is 768 calls, ~$35 a day".
    That is not reachable: `allowance = max(0, min(per_pass, remaining_today))`
    puts both ceilings in one `min()`, so **the day is the daily cap for any
    per-pass value in [1, 24]**. The per-pass cap is not decoration either --
    it decides how the day's 24 are spread across the day's passes, and on a
    23-row slate that is the difference between three reviewed passes and one.

    Mutation, 2026-08-11 and re-run 2026-09-05: `allowance` ->
    `max(0, state.remaining_today)` (drop the per-pass term). The day's-total
    assertions all stayed GREEN, and **which ones is the finding**: removing
    the per-pass ceiling entirely does not raise the day's bill by one call.
    What went RED was the *shape* -- `test_the_pass_cap_spreads_the_day_over_
    three_passes` (23 reserved on pass 1 instead of 8) and the pass-count
    assertion at `per_pass` of 1, 3 and 8. `per_pass=24` is already the no-cap
    case, so its parametrisation stayed green by construction.
    """

    def test_the_pass_cap_spreads_the_day_over_three_passes(self, conn):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        widths = [_spend_a_pass(meter, 23) for _ in range(3)]

        assert widths == [(8, 15), (8, 15), (8, 15)]
        assert len(_rows(conn)) == 24

    def test_without_the_pass_cap_the_first_pass_takes_almost_the_whole_day(
        self, conn
    ):
        """The counterfactual the 768 figure was standing in for.

        The day is still 24 -- it is spent by the *second* pass of ~96 rather
        than multiplied. So the cost of dropping the per-pass cap is that a
        slate at 10:05 UTC eats the allowance every later slate needed, not
        that the bill goes up.
        """
        meter = AgentBudget(conn, per_pass_budget=24, daily_budget=24)
        first = _spend_a_pass(meter, 23)
        second = _spend_a_pass(meter, 23)

        assert first == (23, 0)
        assert second == (1, 22)
        assert len(_rows(conn)) == 24

    @pytest.mark.parametrize("per_pass", [1, 3, 8, 24])
    def test_the_days_total_is_the_daily_cap_whatever_the_pass_cap_is(
        self, conn, per_pass
    ):
        """768 is unreachable. Run the day out and count.

        Passes until the meter refuses everything, then asserts the total is
        the daily cap and not `per_pass` times the number of passes. The number
        of passes it takes is asserted too, because "24 rows" alone is also
        what a broken loop that stopped after one pass would produce.
        """
        meter = AgentBudget(conn, per_pass_budget=per_pass, daily_budget=24)
        passes = 0
        while meter.allowance(NOW) > 0:
            _spend_a_pass(meter, 23)
            passes += 1
            assert passes <= 96, "a pass that spends nothing would loop forever"

        assert len(_rows(conn)) == 24, (
            "the day is the daily cap whatever the fan-out width; 96 x "
            f"{per_pass} is not reachable"
        )
        # A pass reserves at most min(per_pass, len(slate)) rows, and the slate
        # here is 23 -- so `per_pass=24` takes two passes, not one.
        per_saturated_pass = min(per_pass, 23)
        assert passes == -(-24 // per_saturated_pass)


class TestTheSpendIsReadableWithoutOpeningTheDatabase:
    """`agent_calls` appears in two files and nothing read `spent_today`.

    `fly.live.toml` says "raise deliberately, after the first real bill" on an
    instance operated from a phone, and until now there was no phone-reachable
    answer to "how much of today's 24 have I spent?". This is the read side;
    `/api/health` carries it.

    Mutation: `today_summary` -> `remaining_today=self.daily_budget` (ignore
    what has been spent). `test_the_summary_counts_down_as_the_day_is_spent`
    went RED (24, expected 19).
    """

    def test_a_fresh_day_reports_the_whole_allowance(self, conn):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)

        summary = meter.today_summary(NOW)

        assert summary.calls_today == 0
        assert summary.daily_budget == 24
        assert summary.remaining_today == 24
        assert summary.per_pass_budget == 8

    def test_the_summary_counts_down_as_the_day_is_spent(self, conn):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        for _ in range(5):
            meter.reserve(called_ms=NOW, agent="skeptic", model="claude-opus-5")

        summary = meter.today_summary(NOW)

        assert summary.calls_today == 5
        assert summary.remaining_today == 19

    def test_the_summary_names_the_day_boundary_it_used(self, conn):
        """The boundary is the sports day, not midnight, and an operator
        reading "3 of 24" at 09:00 UTC needs to know which day that is."""
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)

        summary = meter.today_summary(NOW)

        assert summary.day_start_hour == 10
        assert summary.day_start_ms == meter.day_start_ms(NOW)
        assert summary.day_start_ms <= NOW

    def test_yesterdays_calls_are_not_in_todays_summary(self, conn):
        """Anti-vacuity: a lifetime counter wearing a daily counter's name
        would satisfy every assertion above."""
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        for _ in range(9):
            meter.reserve(
                called_ms=NOW - 30 * _ONE_HOUR, agent="skeptic", model="claude-opus-5"
            )

        summary = meter.today_summary(NOW)

        assert summary.calls_today == 0
        assert summary.remaining_today == 24


class TestEveryCallIsRecorded:
    """The table is both the meter and the only durable record the fleet ran.

    `reserve` writes the row before the request goes out; `settle` fills in
    what came back and never adds a row. Driven on the meter directly since
    2026-09-05 -- the reviewer that used to drive it is deleted, and the scout
    desk takes the two calls in the same order.

    Mutation, 2026-09-05: `settle` writing `0` for a `None` `blocked`
    (`int(blocked or 0)`). `test_no_verdict_records_NULL_and_never_zero` went
    RED. Mutation: `settle` inserting a fresh row instead of updating --
    `test_settle_never_adds_a_row` went RED with two rows for one call, and
    `test_a_settled_verdict_writes_one_row_with_its_verdict` with it.
    """

    def test_a_settled_verdict_writes_one_row_with_its_verdict(self, conn):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        call_id = meter.reserve(
            called_ms=NOW, agent="skeptic", model="claude-opus-5",
            ticker="KXTEST-000", side="yes",
        )
        meter.settle(call_id, verdict="defect", blocked=True)

        rows = _rows(conn)
        assert len(rows) == 1
        assert rows[0]["agent"] == "skeptic"
        assert rows[0]["model"] == "claude-opus-5"
        assert rows[0]["verdict"] == "defect"
        assert rows[0]["blocked"] == 1
        assert rows[0]["ticker"] == "KXTEST-000"

    def test_no_verdict_records_NULL_and_never_zero(self, conn):
        """`unreadable resolves to None, never 0` -- at the storage layer.

        `blocked = 0` means "looked and did not block". A call that said
        nothing must not be counted as one that cleared the row, or a future
        read of this table would report a review that never happened.
        """
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        call_id = meter.reserve(called_ms=NOW, agent="skeptic", model="claude-opus-5")
        meter.settle(call_id, verdict=None, blocked=None)

        row = _rows(conn)[0]
        assert row["verdict"] is None
        assert row["blocked"] is None

    def test_settle_never_adds_a_row(self, conn):
        """Reserve-then-settle must not double-count: a settle that inserted
        would make the meter tighten itself by a factor of two on every
        successful pass."""
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        call_id = meter.reserve(called_ms=NOW, agent="skeptic", model="claude-opus-5")
        meter.settle(call_id, verdict="plausible", blocked=False)

        assert len(_rows(conn)) == 1
        assert meter.state(NOW).spent_today == 1


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


class TestTheTokenMeterSeesWhatTheCallCapCannot:
    """The v17 brakes: searches and tokens, evaluated before the reserve.

    The 24-call cap counts calls; a scout-desk staff call carries the
    web-search tool at `max_uses: 6`, so one convening can spend 12 searches
    and an unbounded prompt inside four perfectly-counted calls. These caps
    read spend already RECORDED (settled usage) before the next reserve --
    never a field the gated call itself will write, which is the
    "receipt, not a brake" lesson (`tasks/lessons.md`, 2026-08-21).

    Mutations run: (1) `state()` summing `web_searches` changed to count
    rows -- the search test goes red; (2) the `tokens_today >=` check
    removed from `refusal_reason` -- the token test goes red; (3) `settle`
    writing usage columns dropped -- the settle test goes red. File restored
    byte-identical after each.
    """

    def _spend_one(self, meter, *, searches=0, input_tokens=0, output_tokens=0):
        call_id = meter.reserve(called_ms=NOW, agent="scout_staff_home", model="m")
        meter.settle(
            call_id,
            verdict="filed",
            usage=CallUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                web_searches=searches,
            ),
        )

    def test_settle_records_the_usage_and_null_stays_null(self, conn):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        self._spend_one(meter, searches=5, input_tokens=1000, output_tokens=200)
        # A second call whose response never arrived settles no usage: the
        # columns stay NULL, never 0.
        dead = meter.reserve(called_ms=NOW, agent="scout_staff_away", model="m")
        meter.settle(dead, verdict=None)
        rows = conn.execute(
            "SELECT input_tokens, output_tokens, web_searches FROM agent_calls "
            "ORDER BY id"
        ).fetchall()
        assert tuple(rows[0]) == (1000, 200, 5)
        assert tuple(rows[1]) == (None, None, None)
        state = meter.state(NOW)
        assert state.searches_today == 5
        assert state.tokens_today == 1200
        assert state.calls_unmetered_today == 1

    def test_the_search_brake_refuses_before_the_money_leaves(self, conn):
        """With 50 of 60 searches recorded, a fan-out that could spend 12 more
        is refused up front -- the worst case would cross the ceiling."""
        meter = AgentBudget(
            conn, per_pass_budget=8, daily_budget=24,
            searches_daily_budget=60, tokens_daily_budget=500_000,
        )
        for _ in range(5):
            self._spend_one(meter, searches=10)
        assert not meter.can_afford(2, NOW, searches_worst_case=12)
        reason = meter.refusal_reason(2, NOW, searches_worst_case=12)
        assert "50 of 60 web searches" in reason
        # The same fan-out with no tools is still affordable: the call caps
        # alone govern it.
        assert meter.can_afford(2, NOW, searches_worst_case=0)

    def test_the_token_brake_refuses_once_the_recorded_total_crosses(self, conn):
        meter = AgentBudget(
            conn, per_pass_budget=8, daily_budget=24,
            searches_daily_budget=60, tokens_daily_budget=10_000,
        )
        self._spend_one(meter, input_tokens=9_000, output_tokens=999)
        assert meter.can_afford(2, NOW)
        self._spend_one(meter, input_tokens=0, output_tokens=1)
        assert not meter.can_afford(2, NOW)
        assert "10000 of 10000 Anthropic tokens" in meter.refusal_reason(2, NOW)

    def test_a_zero_ceiling_means_unconfigured_and_refuses_nothing(self, conn):
        """The many existing constructors that pass only call caps must keep
        meaning what they meant: call caps only, no token/search brakes."""
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        for _ in range(3):
            self._spend_one(meter, searches=1000, input_tokens=10**9)
        assert meter.can_afford(2, NOW, searches_worst_case=12)

    def test_from_config_wires_both_ceilings(self, conn, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("AGENT_MAX_SEARCHES_PER_DAY", "7")
        monkeypatch.setenv("AGENT_MAX_TOKENS_PER_DAY", "123")
        meter = AgentBudget.from_config(conn, AgentConfig.from_env())
        assert meter.searches_daily_budget == 7
        assert meter.tokens_daily_budget == 123
        summary = meter.today_summary(NOW)
        assert summary.searches_daily_budget == 7
        assert summary.tokens_daily_budget == 123
        assert summary.searches_today == 0
        assert summary.tokens_today == 0
        assert summary.calls_unmetered_today == 0

    def test_an_unmetered_call_cannot_slip_under_the_search_brake(self, conn):
        """NULL usage adds nothing to the sums -- the brake under-counts, by
        design, and the call cap stays the outer bound. What must hold is
        that the NULL rows are COUNTED as unmetered, so the summary can say
        what the sums do not cover."""
        meter = AgentBudget(
            conn, per_pass_budget=8, daily_budget=24,
            searches_daily_budget=60, tokens_daily_budget=500_000,
        )
        dead = meter.reserve(called_ms=NOW, agent="scout_staff_home", model="m")
        meter.settle(dead, verdict=None)
        assert meter.state(NOW).calls_unmetered_today == 1
        assert meter.can_afford(2, NOW, searches_worst_case=12)
