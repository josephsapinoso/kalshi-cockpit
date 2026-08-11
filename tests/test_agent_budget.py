"""The ceiling on Anthropic spend, and the refusal it produces.

These tests exist because `backend/agents/` shipped a billed fan-out with no
cap of any kind: `review._review_batch` gathered over every surfaced candidate,
on a loop that wakes up to ~96 times a day, with `ANTHROPIC_API_KEY` set on the
live instance. The only binding guard was that no row had ever surfaced -- a
measurement outcome, not a configuration value.

What this harness does NOT establish
------------------------------------
**That any of this has run against Anthropic.** Every call here goes to a stub
client. What is verified is that the *number* of calls is bounded, that one
candidate is one request, and that the rows past the bound are refused.

**Nothing here checks what a call costs**, and the number it would check
against is itself unverified: the dollar figures in `agents/base.py` rest on a
claude-opus-5 list price marked `[ASSUMED, uncited]` there, which no fixture,
invoice or API response in this repo confirms. Nothing reads an
Anthropic-reported balance either, so a drift between this count and the real
invoice is invisible in both directions at once. The count is the only claim
this harness can make good on -- which is why `agents/base.py` puts the safety
argument on the count and not on the dollars.

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

**That a stub client models the SDK.** `_StubClient` is a hand-written object,
not a captured payload, so it cannot show that `anthropic.AsyncAnthropic`
behaves the way `_RetryingStubClient` pretends it does. What
`TestOneCandidateIsExactlyOneRequest` establishes is the two halves separately:
that `build_client` sets `max_retries=0` on a real SDK client, and that *given*
a client which does not retry, one candidate produces one request. The join is
the SDK's documented contract, not a test.

Mutations run against this file
-------------------------------
**Fourteen guards have been disabled one at a time**, `tests/test_agent_budget.py`
and `tests/test_agent_wiring.py` re-run against each, and the outcome recorded in
the class docstring that owns the guard. **Thirteen went red. One stayed green
and is recorded rather than pruned** -- see `TestEveryCallIsRecorded`, where a
`settle` that is skipped changes nothing because `reserve` has already written
the same NULLs. Another (the required `conn`) went red by a different mechanism
than predicted, which is kept rather than tidied away -- see
`TestTheMeterCannotBeReachedWithoutADatabase`.

**The count was "nine" until 2026-08-11, and only seven were ever written down.**
The two undocumented ones could not be recovered, and inventing two to match the
commit message would have been worse than the miscount, so the number was
corrected to what this file actually carries. The seven added since are
`max_retries`, reserve-before-spend (twice: moved, and made conditional), the
per-pass distribution arithmetic, the read-side summary, and the two guards that
had never been fired by anything at all:

- `review.py`'s "the budget refused and would not say which ceiling" raise
  carried `# pragma: no cover`, so nothing had ever driven it.
- `runner.py`'s length-mismatch raise was asserted only as a *consequence* of
  another test's mutation ("`_review_and_persist` would have raised") and had
  never actually raised.

Both are now driven directly by `TestAGuardIsNotAGuardUntilItHasFired`. By this
repo's standard an unfired guard is decoration, and two of them sat in the money
path of the commit that introduced the money path.
"""

from __future__ import annotations

import pytest

from backend.agents.base import (
    DEFAULT_MAX_CALLS_PER_DAY,
    DEFAULT_MAX_CALLS_PER_PASS,
    AgentConfig,
    build_client,
)
from backend.agents.budget import AgentBudget
from backend.agents.review import ReviewCandidate, ReviewOutcome, review_surfaced
from backend.agents.skeptic import SkepticVerdict
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


class _Transient(Exception):
    """What a 429 or a 529 looks like to the SDK's retry loop."""


class _RetryingStubMessages:
    """A stub that models the SDK's retry loop instead of hiding it.

    `_StubMessages.parse` increments once per invocation and never retries, so
    every `client.messages.seen == N` assertion in this file counts `parse()`
    calls -- **not HTTP requests**. That is the exact gap the SDK default fell
    through: `structured_call` collapses every attempt into one return, and the
    meter counts once per candidate, so two silent retries per candidate were
    invisible to both.

    This stub separates the two counters and takes `max_retries` from what
    `build_client` actually configures, so raising that setting makes the
    request count diverge from the candidate count and the test goes red.
    """

    def __init__(self, verdict, *, max_retries: int, failures_before_success: int):
        self._verdict = verdict
        self._max_retries = max_retries
        self._failures = failures_before_success
        self.parses = 0    # `messages.parse(...)` invocations
        self.requests = 0  # HTTP requests those invocations would make

    async def parse(self, **kwargs):
        self.parses += 1
        attempt = 0
        while True:
            attempt += 1
            self.requests += 1
            if attempt > self._failures:
                return _StubResponse(self._verdict)
            if attempt == 1 + self._max_retries:
                # Out of attempts. `structured_call` turns this into `None`.
                raise _Transient("429 rate_limit_error")


class _RetryingStubClient:
    def __init__(self, verdict, *, max_retries: int, failures_before_success: int):
        self.messages = _RetryingStubMessages(
            verdict,
            max_retries=max_retries,
            failures_before_success=failures_before_success,
        )


class _Crash(BaseException):
    """The process dying, not an API call failing.

    Deliberately **not** an `Exception`: `review._evaluate_one` catches
    `Exception` to isolate one bad candidate from the batch, and a test that
    used a catchable error would be testing that guard instead of the crash
    window. `BaseException` walks out through `asyncio.gather`, out of the
    dedicated thread, and out of `review_surfaced` -- which is what a killed
    container looks like from the meter's point of view.
    """


class _DyingStubMessages:
    def __init__(self, verdict, *, die_on: int):
        self._verdict = verdict
        self._die_on = die_on
        self.seen = 0

    async def parse(self, **kwargs):
        self.seen += 1
        if self.seen == self._die_on:
            raise _Crash("the process died part-way through the fan-out")
        return _StubResponse(self._verdict)


class _DyingStubClient:
    def __init__(self, verdict, *, die_on: int):
        self.messages = _DyingStubMessages(verdict, die_on=die_on)


def _sdk_max_retries() -> int:
    """What `build_client` actually configures on a real SDK client.

    Read from the SDK object rather than restated as a literal, so the test
    cannot keep asserting a number the production path stopped using.
    """
    return build_client(AgentConfig(api_key="test-key-not-used")).max_retries


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

    def test_a_batch_larger_than_the_ceiling_makes_only_that_many_calls_at_scale(
        self, conn
    ):
        """The same claim at 50 candidates, where truncation would be obvious.

        This replaced `test_the_batch_is_bounded_before_the_calls_go_out_not_
        after`, which asserted `seen == 2` and `len(_rows(conn)) == 2` under the
        name of the reserve-first property. **Those two assertions are satisfied
        by a reserve-first design and a record-after design alike** -- it was an
        anchor chosen at the one point where the two candidate designs give the
        same answer, so it could never have discriminated between them. The
        property it was named for is now tested by
        `TestTheReservationSurvivesACrashMidFanOut`, which kills the client
        mid-`gather` and asks what the table says.
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
    (2, expected 0) and `test_a_candidate_that_needs_a_retry_is_still_one_
    request` went RED (6 requests for 3 candidates).
    """

    def test_build_client_does_not_let_the_sdk_retry(self):
        """The choice, asserted against the real SDK object rather than a stub.

        `max_retries=1` would keep review coverage on a transient failure at the
        cost of exactness -- 24 counted calls would be 24 to 48 requests with
        nothing able to say which. `0` was chosen because the retry already
        exists one level up, at pass granularity, where `agent_calls` sees it.
        """
        assert _sdk_max_retries() == 0

    def test_a_candidate_that_needs_a_retry_is_still_one_request(self, conn):
        """Every candidate hits a transient failure. Nothing retries it.

        Three candidates, three requests, three metered rows -- and three
        `NULL` verdicts, because a call the SDK did not retry is a call that
        came back with no opinion. That last part is the cost of the choice and
        it is asserted rather than left implicit.
        """
        client = _RetryingStubClient(
            _verdict(), max_retries=_sdk_max_retries(), failures_before_success=1
        )
        outcome = review_surfaced(
            _candidates(3),
            conn=conn,
            config=AgentConfig(
                api_key="test-key", max_calls_per_pass=8, max_calls_per_day=100
            ),
            client_factory=lambda config: client,
            now=NOW,
        )

        assert client.messages.parses == 3
        assert client.messages.requests == 3, (
            "one candidate must be one HTTP request; the meter counts "
            "candidates, so any other ratio is spend it cannot see"
        )
        rows = _rows(conn)
        assert len(rows) == 3
        assert [r["verdict"] for r in rows] == [None, None, None]
        assert outcome.reviewed == 3

    def test_the_stub_would_have_caught_a_retry(self, conn):
        """Anti-vacuity: the stub is only evidence if it can count to two.

        If `_RetryingStubMessages` never retried under any setting, the test
        above would pass against a client that retried three times. Driving the
        same stub with the SDK's own default proves the counter is live.
        """
        client = _RetryingStubClient(
            _verdict(), max_retries=2, failures_before_success=1
        )
        review_surfaced(
            _candidates(3),
            conn=conn,
            config=AgentConfig(
                api_key="test-key", max_calls_per_pass=8, max_calls_per_day=100
            ),
            client_factory=lambda config: client,
            now=NOW,
        )

        assert client.messages.parses == 3
        assert client.messages.requests == 6
        assert len(_rows(conn)) == 3, (
            "and the meter still says 3 -- which is the defect, stated as a test"
        )


class TestTheReservationSurvivesACrashMidFanOut:
    """The crash window, and which direction it must err in.

    `_review_batch` fires the whole `asyncio.gather` at once. If rows were
    written only after every call returned, a process death mid-batch would
    leave up to `AGENT_MAX_CALLS_PER_PASS` billed calls with no row -- and since
    `spent_today` is `COUNT(*)` over `agent_calls`, the pass after the restart
    would see a *larger* allowance than it was owed. `docker/entrypoint.sh`
    restarts, `run_loop` re-prices the same slate, the same rows surface, and
    nothing in this repo bounded that loop.

    Mutation: move the `meter.reserve(...)` comprehension back below
    `_run_off_loop` (i.e. restore record-after). Both tests in this class went
    RED -- `test_a_crash_mid_fan_out_leaves_the_day_charged_not_free` with
    `spent_today == 0` for three calls that had already gone out, and
    `test_the_reserved_rows_carry_the_row_they_were_for` with an empty table.
    Zero rows for three billed calls is the exact permissive direction the
    reserve exists to prevent, and it is what a crash loop compounds.
    """

    def test_a_crash_mid_fan_out_leaves_the_day_charged_not_free(self, conn):
        client = _DyingStubClient(_verdict(), die_on=2)

        with pytest.raises(_Crash):
            review_surfaced(
                _candidates(3),
                conn=conn,
                config=AgentConfig(
                    api_key="test-key", max_calls_per_pass=8, max_calls_per_day=24
                ),
                client_factory=lambda config: client,
                now=NOW,
            )

        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        assert meter.state(NOW).spent_today == 3, (
            "the whole fan-out was reserved before it went out, so the crash "
            "over-counts rather than handing the next pass a free allowance"
        )
        assert meter.state(NOW).remaining_today == 21

    def test_the_reserved_rows_carry_the_row_they_were_for(self, conn):
        """A reservation nobody can attribute is a number, not a record.

        Written before the verdict exists, so `ticker` and `side` come off the
        candidate rather than the amended row -- and if that ever stopped being
        the same value, the durable record of what the fleet spent money on
        would go blank exactly when it mattered.
        """
        client = _DyingStubClient(_verdict(), die_on=1)

        with pytest.raises(_Crash):
            review_surfaced(
                _candidates(2),
                conn=conn,
                config=AgentConfig(api_key="test-key"),
                client_factory=lambda config: client,
                now=NOW,
            )

        rows = _rows(conn)
        assert [r["ticker"] for r in rows] == ["KXTEST-000", "KXTEST-001"]
        assert [r["side"] for r in rows] == ["yes", "yes"]
        assert [r["verdict"] for r in rows] == [None, None]
        assert [r["blocked"] for r in rows] == [None, None]

    def test_a_completed_batch_still_records_exactly_one_row_per_call(self, conn):
        """Anti-vacuity. Reserve-then-settle must not double-count.

        The obvious way to get the crash test green is to write a row in both
        places, which would make the meter tighten itself by a factor of two on
        every successful pass.
        """
        _review(conn, _candidates(4), per_pass=8, per_day=100, verdict=_verdict("defect"))

        rows = _rows(conn)
        assert len(rows) == 4
        assert [r["verdict"] for r in rows] == ["defect"] * 4


class TestAGuardIsNotAGuardUntilItHasFired:
    """Two raises that had never been raised by anything.

    `review.py`'s "which ceiling bound?" check carried `# pragma: no cover`, and
    `runner.py`'s length-mismatch check was only ever asserted as a *side effect*
    of another test's mutation. By this repo's rule -- every guard is verified by
    disabling it and watching the test fail -- both were decoration, in the money
    path, in a commit whose message said nine guards had been mutated.

    Mutation: delete the `raise RuntimeError` in `review.review_surfaced`.
    `test_a_refusal_with_no_stated_reason_refuses_to_persist` went RED: the rows
    came back suppressed with the reason text `the Skeptic never saw this row: `
    and nothing after the colon, which is the silent-truncation outcome one
    string away.

    Mutation: delete the length-mismatch `raise RuntimeError` in
    `runner._review_and_persist`. `test_a_short_review_result_refuses_to_persist`
    went RED, and the tail row persisted **surfaced and unreviewed** -- `zip`
    dropped it without a word.
    """

    def test_a_refusal_with_no_stated_reason_refuses_to_persist(self, conn):
        class _InconsistentBudget:
            """Allows part of the batch, then declines to say what refused the
            rest. Not a shape the real `AgentBudget` can produce today -- which
            is the point: the guard exists for the version of it that can."""

            def allowance(self, now_ms):
                return 1

            def refusal_reason(self, requested, now_ms):
                return None

        with pytest.raises(RuntimeError, match="declined to say which ceiling"):
            review_surfaced(
                _candidates(3),
                conn=conn,
                config=AgentConfig(api_key="test-key"),
                client_factory=lambda config: _StubClient(_verdict()),
                budget=_InconsistentBudget(),
                now=NOW,
            )

        assert _rows(conn) == [], "and it refused before spending anything"

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
    """The daily cap is the money control, and it is the only one.

    This docstring used to open "96 passes at the per-pass cap is 768 calls",
    which describes a system this module does not implement:
    `min(per_pass, remaining_today)` puts both ceilings in the same `min()`, so
    768 is unreachable by any configuration. See
    `TestThePerPassCapDistributesTheDayItDoesNotShrinkIt` for what the per-pass
    cap does instead.

    Mutation: `min(state.per_pass_budget, state.remaining_today)` ->
    `state.per_pass_budget`. `test_calls_already_made_today_reduce_the_allowance`
    and `test_a_zero_daily_budget_makes_no_calls_at_all` both went RED.
    """

    def test_calls_already_made_today_reduce_the_allowance(self, conn):
        meter = AgentBudget(conn, per_pass_budget=8, daily_budget=10)
        for _ in range(7):
            meter.reserve(
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

    Mutation: `allowance` -> `max(0, state.remaining_today)` (drop the per-pass
    term). Four of the six tests here went RED and two stayed GREEN, and
    **which two is the finding**: every `len(_rows(conn)) == 24` assertion
    survived, in all four parametrisations. Removing the per-pass ceiling
    entirely does not raise the day's bill by one call. What went red was the
    *shape* -- `test_the_pass_cap_spreads_the_day_over_three_passes` (23
    reviewed on pass 1 instead of 8) and the pass-count assertion at
    `per_pass` of 1, 3 and 8. `per_pass=24` is already the no-cap case, so both
    of its tests stayed green by construction.

    That is the two properties separating cleanly under the knife, which is
    what the old "768 calls, ~$35 a day" docstring had conflated.
    """

    def test_the_pass_cap_spreads_the_day_over_three_passes(self, conn):
        widths = []
        for _ in range(3):
            outcome, _ = _review(conn, _candidates(23), per_pass=8, per_day=24)
            widths.append((outcome.reviewed, outcome.unreviewed))

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
        first, _ = _review(conn, _candidates(23), per_pass=24, per_day=24)
        second, _ = _review(conn, _candidates(23), per_pass=24, per_day=24)

        assert (first.reviewed, first.unreviewed) == (23, 0)
        assert (second.reviewed, second.unreviewed) == (1, 22)
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
            _review(conn, _candidates(23), per_pass=per_pass, per_day=24)
            passes += 1
            assert passes <= 96, "a pass that spends nothing would loop forever"

        assert len(_rows(conn)) == 24, (
            "the day is the daily cap whatever the fan-out width; 96 x "
            f"{per_pass} is not reachable"
        )
        # A pass reviews at most min(per_pass, len(slate)) rows, and the slate
        # here is 23 -- so `per_pass=24` takes two passes, not one.
        per_saturated_pass = min(per_pass, 23)
        assert passes == -(-24 // per_saturated_pass)


class TestTheSpendIsReadableWithoutOpeningTheDatabase:
    """`agent_calls` appears in two files and nothing read `spent_today`.

    `fly.live.toml` says "raise deliberately, after the first real bill" on an
    instance operated from a phone, and until now there was no phone-reachable
    answer to "how much of today's 24 have I spent?". This is the read side;
    the `/api/health` field that should carry it is **outstanding** --
    `backend/api/routes.py` was another lane's file when this was written.

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

    Mutation: skipping the `meter.settle(...)` call when `verdict is None`.
    `test_no_verdict_records_NULL_and_never_zero` stayed **GREEN**, and that is
    recorded rather than pruned: `reserve` already writes `NULL, NULL`, so a
    settle with no verdict writes the values that are already there. The
    property moved with the write -- what holds it now is that `reserve` runs
    for every candidate regardless of outcome, and the mutation that catches
    *that* is in `TestTheReservationSurvivesACrashMidFanOut`.

    Mutation: reserving lazily, from the verdict list rather than the candidate
    list -- `... if verdict is not None else None for candidate, verdict in
    zip(reviewable, verdicts)`. Five tests went RED, including
    `test_a_call_that_produced_no_verdict_still_counts` (0 rows for 3 calls)
    and `test_no_verdict_records_NULL_and_never_zero` (no row to read at all).
    That is the exact hole that would let an Anthropic outage spend the day for
    free against the ceiling, retry after retry: every call that failed would
    be a call the meter never saw.
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
