"""The review seam in the pricing pass, and the retirement that sits in it.

`backend/agents/*` was the fourth module in this project to be complete, tested
and invoked by nothing. These were the tests that the *connection* worked --
that a surfaced row reached the Skeptic, that its verdict was applied before
anything was persisted, that a blocked row could never be sold. The Skeptic was
retired as the pass default on 2026-08-21 (ADR 0062) and deleted on 2026-09-05
together with `review_surfaced`, the metered caller these tests used to inject
(`docs/adr/DRAFT-the-historian-and-the-skeptic-are-deleted-and-the-desk-has-been-convened.md`).

What is left to test is the **seam**: `run_pricing_pass` still judges every row,
hands the surfaced ones to `review`, and persists only afterwards. That shape is
what stops a surfaced row sitting orderable on disk while something looks at it,
and it is what `TestTheScheduledSkepticIsRetired` attaches to. The reviewer
injected here is a stand-in that returns rows blocked or untouched and reaches
no client; the tests that needed a client -- an API failure, an unbuildable
prompt, an unconfigured key, the dedicated-thread event loop -- were tests of
the deleted function and went with it.

What these tests do not establish
---------------------------------
**That any reviewer runs on the deployed instance.** None does. The default is
`review_retired`, which refuses every surfaced row and calls nothing, and the
last test class here is what keeps that true. The slate below is built by
taking the captured Kalshi and odds payloads the rest of the suite uses and
nudging **one** number -- the NO bid on one market, which sets the derived YES
ask -- until the row clears the suppression gauntlet. Every other value is the
bytes the two APIs actually sent. That nudge is stated rather than hidden
because it is the whole reason a test can exist here at all: without it there
is no surfaced row anywhere in this repo, and a seam test with nothing to hand
over is decoration.

Where the "a blocked row cannot be sold" claim is actually established
---------------------------------------------------------------------
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

import copy
import json
from pathlib import Path

import pytest

from backend.agents.review import ReviewCandidate, ReviewOutcome
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


class _Reviewer:
    """A stand-in reviewer that records what the seam handed it.

    `verdict=None` passes every row through untouched -- what an opted-in
    reviewer with no opinion did. `verdict="defect"` (or `"suspicious"`)
    blocks every row with the tag the deleted `apply_verdict` used to fold in,
    restated through `with_added_suppression` exactly as the runner persists
    it. Nothing here reaches a client: the metered reviewer is deleted, and
    these tests are about the seam, not the reviewer.
    """

    def __init__(self, verdict=None, on_call=None):
        self._verdict = verdict
        self._on_call = on_call
        self.batches: list[list[ReviewCandidate]] = []

    def __call__(self, candidates, **kwargs) -> ReviewOutcome:
        del kwargs  # `conn` and `now`, which a stand-in has no use for
        self.batches.append(list(candidates))
        if self._on_call is not None:
            self._on_call(list(candidates))
        rows: list[Recommendation] = []
        blocked = 0
        for candidate in candidates:
            if self._verdict in ("defect", "suspicious"):
                rows.append(
                    with_added_suppression(
                        candidate.recommendation,
                        reason=f"skeptic_{self._verdict}",
                        problem=(
                            f"the reviewer calls this {self._verdict}: the "
                            f"Kalshi market settles on regulation time"
                        ),
                    )
                )
                blocked += 1
            else:
                rows.append(candidate.recommendation)
        return ReviewOutcome(
            recommendations=rows, reviewed=len(rows), blocked=blocked
        )

    @property
    def calls(self) -> int:
        return sum(len(b) for b in self.batches)


class TestTheSlateActuallySurfacesSomething:
    """Without this, every test below is vacuously green.

    A seam test whose fixture surfaces nothing asserts that nothing happened
    to nothing. Assert the precondition separately so a change that stops the
    row surfacing fails *here*, naming the cause, instead of quietly turning
    four other tests into no-ops.
    """

    def test_exactly_one_candidate_reaches_the_reviewer(self, conn, surfacing_slate):
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

        A live pass builds ~100 rows and nearly all have no edge. A reviewer
        handed them all would buy a hundred "no"s a pass at 96 passes a day.
        """
        reviewer = _Reviewer()
        run_pricing_pass(conn, surfacing_slate, now=NOW, review=reviewer)

        assert len(_rows(conn)) == 4, "the slate should still record every candidate"
        assert reviewer.calls == 1


class TestReviewHappensBeforeAnythingIsPersisted:
    """The window the two-phase pass exists to close.

    A reviewer folds into `suppressed_reason`. If the row is already on disk
    when it is asked, then for the duration of one round trip `POST
    /api/orders` would find a row with a positive size and no reason and sell
    it. The endpoint reads the database, so "we have not applied the verdict
    yet" is not a state it can observe.
    """

    def test_no_orderable_row_exists_while_the_reviewer_is_being_asked(
        self, conn, surfacing_slate
    ):
        observed: list[list[dict]] = []
        reviewer = _Reviewer(
            verdict="defect",
            on_call=lambda _candidates: observed.append(_orderable(conn)),
        )

        run_pricing_pass(conn, surfacing_slate, now=NOW, review=reviewer)

        assert observed == [[]], (
            "an orderable row was already on disk when the reviewer was asked "
            f"about it: {observed}"
        )

    def test_a_blocking_verdict_never_reaches_the_database_as_orderable(
        self, conn, surfacing_slate
    ):
        counts = run_pricing_pass(
            conn, surfacing_slate, now=NOW, review=_Reviewer(verdict="defect"),
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

    def test_a_pass_through_verdict_leaves_the_row_surfaced(self, conn, surfacing_slate):
        """No opinion is not approval, and must not read as a change.

        A reviewer cannot clear a reason or add a contract. All it can do on a
        no-opinion outcome is nothing, and "nothing" has to be observable --
        otherwise a bug that dropped every verdict would look identical.
        """
        counts = run_pricing_pass(
            conn, surfacing_slate, now=NOW, review=_Reviewer(verdict=None),
        )

        assert counts.surfaced == 1
        assert counts.skeptic_reviewed == 1
        assert counts.skeptic_blocked == 0
        assert len(_orderable(conn)) == 1


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
        # And the fourth: the gate counts `reference_contracts`, so a row a
        # reviewer vetoed must not go on accumulating evidence for a bet the
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


class TestTheReviewedSetAndTheVerdictsCannotDrift:
    """The one failure here that money could reach.

    The runner matches verdicts to rows by position. A reviewer returning a
    short list would make `zip` drop the tail silently, and the dropped rows
    would persist as surfaced having never been reviewed -- the exact state the
    two-phase pass exists to make impossible.
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
    returns `None` and the scout desk refuses to be sent -- and that is also
    what a configured desk looks like on a day nobody sends it. So without this
    field, "the key is set" and "the process can see the key" cannot be told
    apart from outside.
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


class TestTheScheduledSkepticIsRetired:
    """ADR 0062: the pass's default reviewer spends nothing and promotes nothing.

    Verified by disabling, twice. On 2026-08-21: put `review=review_surfaced`
    back as the `run_pricing_pass` default and the first test failed -- with no
    key in the test environment that reviewer returned the surfaced row
    *untouched*, so it persisted orderable and the suppression assertion went
    red. On 2026-09-05, with `review_surfaced` deleted: make the default a
    reviewer that passes every row through (`lambda candidates, *, conn, now:
    ReviewOutcome(recommendations=[c.recommendation for c in candidates],
    reviewed=len(candidates))`) and the first test fails the same way --
    `_orderable(conn)` holds the surfaced row, `skeptic_unreviewed` is
    nowhere, and `counts.surfaced` is 1. The distinction matters because "no
    `agent_calls` rows" alone cannot separate the two defaults on a keyless
    machine; what separates them is what the row is allowed to become.
    """

    def test_the_default_pass_refuses_the_surfaced_row_and_spends_nothing(
        self, conn, surfacing_slate
    ):
        counts = run_pricing_pass(conn, surfacing_slate, now=NOW)

        assert counts.skeptic_reviewed == 0
        assert counts.skeptic_unreviewed == 1
        assert counts.surfaced == 0
        assert _orderable(conn) == [], (
            "a surfaced row persisted orderable under the retired default; "
            "retiring the reviewer must not promote the rows it reviewed"
        )
        suppressed = [r for r in _rows(conn) if r["suppressed_reason"]]
        assert any(
            "skeptic_unreviewed" in r["suppressed_reason"]
            and "retired (ADR 0062)" in (r["reason_text"] or "")
            for r in suppressed
        ), f"no row carries the retirement refusal. Rows: {_rows(conn)}"

        spent = conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"]
        assert spent == 0, "the retired default reserved or settled a metered call"

    def test_review_retired_needs_no_database_and_no_client(self, conn, surfacing_slate):
        """The signature is the proof there is no billed path: it takes no
        client factory, no config, no budget -- and `conn` is accepted unused,
        so even a caller with no database cannot reach a meter."""
        from backend.agents.review import review_retired

        reviewer = _Reviewer()
        run_pricing_pass(conn, surfacing_slate, now=NOW, review=reviewer)
        candidate = reviewer.batches[0][0]

        outcome = review_retired([candidate], conn=None)

        assert outcome.reviewed == 0
        assert outcome.blocked == 0
        assert outcome.unreviewed == 1
        row = outcome.recommendations[0]
        assert row.suggested_contracts == 0
        assert "skeptic_unreviewed" in row.suppressed_reason

    def test_an_empty_batch_stays_empty(self):
        from backend.agents.review import review_retired

        outcome = review_retired([], conn=None)
        assert outcome == ReviewOutcome(recommendations=[], unreviewed=0)

    def test_no_metered_reviewer_exists_to_opt_back_into(self):
        """The retirement used to be a default with an alternative one import
        away. Since 2026-09-05 there is no alternative: the module exports no
        reviewer but the retired one, and imports nothing that can bill."""
        import ast
        from pathlib import Path

        from backend.agents import review

        assert not hasattr(review, "review_surfaced")
        source = (Path(review.__file__)).read_text("utf-8")
        imported = {
            node.module
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any(m in ("base", "budget", "skeptic") for m in imported), (
            f"review.py imports {sorted(imported)}; a reviewer that can reach "
            f"`base.structured_call` is a reviewer that can spend"
        )
