"""One definition of "today" for the daily-loss kill switch, in two processes.

The defect this closes
----------------------
`size_position` engages `max_daily_loss_dollars` for **every row on the slate**
(`backend/core/sizing.py:186-191`), and the number it engages on comes from
`settlement.daily_realised_pnl_dollars`, whose window is a *sports* day cut at
`day_start_hour`. Two processes read that number:

    backend/api/routes.py:1546   day_start_hour=odds.budget_day_start_utc_hour
    backend/runner.py:625        <- no day_start_hour: the hardcoded constant

So the runner's kill-switch day came from `odds/timing.DEFAULT_DAY_START_UTC_HOUR`
and the order endpoint's from `ODDS_BUDGET_DAY_START_UTC_HOUR`. They agree today
only because that variable is unset on live and both resolve to 10. It is a
documented knob (`.env.example`), and the moment anyone sets it the two days
diverge with no symptom in either process -- each computes a boundary that is
internally consistent and neither ever compares it with the other's.

The same omission existed in `agents/budget.py`: `AgentBudget.from_config`
passed no hour while `.env.example` claimed the agent day rolls at
`ODDS_BUDGET_DAY_START_UTC_HOUR`. That sentence described an intention.

Direction of failure, which is not symmetric
--------------------------------------------
A **later** day start counts **less** of the day's realised P&L as "today", so
the kill switch engages **less** -- the permissive direction.

- configured hour **later** than the constant: the order endpoint is the
  permissive side.
- configured hour **earlier** than the constant: the *runner* is the permissive
  side, which is the sharper case. It is the shape of the quote-age divergence:
  the card is sized, surfaced, recorded and shown, and the endpoint then applies
  a fuller day of losses and refuses it.

What this harness does NOT establish
------------------------------------
**That no divergence can occur on the deployed instance.** No test can observe
one. The divergence is created entirely by a deployed environment value that a
test process never sees -- a test comparing one hardcoded default against
another passes green forever while Fly holds a third number. That is why the
guard is `config.assert_risk_day_start_agrees`, a **boot-time** assertion wired
into `api/routes.py` and `scripts/run_loop.py`, and why these tests pin only
that the assertion exists, raises (rather than warns), raises in both
directions, names the permissive side, and is called from both entry points.

**That the kill switch then does the right thing with the number.** That is
`tests/test_runner.py::TestTheSlateIsSizedAgainstOnePortfolio::
test_a_realised_loss_past_the_limit_sizes_the_whole_slate_to_zero` and
`tests/test_ev_sizing.py`. This module pins only *which day* is measured.

**That the four other "day" definitions in the repo are right.** The calendar
UTC month in `odds/budget.py:60` belongs to The Odds API and reconciliation
depends on agreeing with them; the calendar UTC day in `notify/alerts.py:69` is
alert dedupe and is harmless. Neither is collapsed into the sports day and
nothing here asserts about them.

**That `run_chain.py` cannot diverge.** It reads the configured hour directly
and carries no boot assertion, because it is a one-shot developer script rather
than a process that stays up. If it is ever promoted, it needs the assertion.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.agents.budget import AgentBudget
from backend.config import (
    OddsConfig,
    RiskDayDisagrees,
    assert_risk_day_start_agrees,
    configured_day_start_utc_hour,
)
from backend.odds.timing import DEFAULT_DAY_START_UTC_HOUR
from backend.runner import run_pricing_pass
from backend.settlement import daily_realised_pnl_dollars, risk_day_start_ms
from backend.store import db

ROOT = Path(__file__).resolve().parents[1]

# Inside the fixture window every other runner test uses.
NOW = 1_786_110_562_317 + 300_000


def _odds(hour: int) -> OddsConfig:
    return OddsConfig(
        api_key="", base_url="", daily_credit_budget=16,
        regions=["us"], markets=["h2h"],
        budget_day_start_utc_hour=hour,
    )


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "riskday.db")
    yield c
    c.close()


class TestTheBootAssertion:
    """`config.assert_risk_day_start_agrees`, the third of the family.

    Its two siblings compare a hardcoded `SuppressionConfig` field against an
    env-read `StalenessConfig` field. This one compares the **default** every
    risk-day signature still carries against the **configured** value, which is
    the only comparison that survives the fix: while they are equal a forgotten
    argument is harmless, and the moment they differ every defaulting call site
    is on a different day from every configured one.
    """

    def test_it_passes_on_the_deployed_pair(self):
        assert_risk_day_start_agrees(
            default_day_start_hour=DEFAULT_DAY_START_UTC_HOUR,
            odds=_odds(DEFAULT_DAY_START_UTC_HOUR),
        )

    def test_it_RAISES_rather_than_warning(self):
        """The day someone sets ODDS_BUDGET_DAY_START_UTC_HOUR on Fly.

        Downgrading this to `logger.warning` turns this test red. A log line
        nobody reads is not a control on a money path, and `flyctl logs` is
        lossy besides -- see `tasks/lessons.md` on verification methods that lie.
        """
        with pytest.raises(RiskDayDisagrees) as excinfo:
            assert_risk_day_start_agrees(
                default_day_start_hour=DEFAULT_DAY_START_UTC_HOUR,
                odds=_odds(14),
            )
        message = str(excinfo.value)
        assert "14" in message
        assert "0024" in message, "the error must say where the rule lives"

    def test_it_raises_in_both_directions(self):
        """A guard that only catches the permissive direction is half a guard.

        Earlier than the constant makes the *runner* permissive; later makes the
        *endpoint* permissive. Both are silent, and silent is the whole defect.
        """
        for hour in (0, 6, 9, 11, 14, 23):
            with pytest.raises(RiskDayDisagrees):
                assert_risk_day_start_agrees(
                    default_day_start_hour=DEFAULT_DAY_START_UTC_HOUR,
                    odds=_odds(hour),
                )

    def test_the_message_names_which_side_would_be_permissive(self):
        """The operator has to know which way to look, not just that it broke."""
        with pytest.raises(RiskDayDisagrees) as later:
            assert_risk_day_start_agrees(
                default_day_start_hour=10, odds=_odds(14)
            )
        with pytest.raises(RiskDayDisagrees) as earlier:
            assert_risk_day_start_agrees(
                default_day_start_hour=10, odds=_odds(6)
            )
        assert "the order endpoint" in str(later.value)
        assert "the runner" in str(earlier.value)

    def test_it_is_called_at_both_entry_points(self):
        """Removing it from either process turns this red.

        Asserted on the source because no behavioural test can distinguish
        "called at boot" from "not called" while the two values are equal --
        which, on any machine a test runs on, they are.
        """
        for relative in ("scripts/run_loop.py", "backend/api/routes.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            assert "assert_risk_day_start_agrees(" in source, (
                f"{relative} no longer asserts the risk day at startup; a "
                f"divergence in that process would be silent again"
            )


class TestTheRunnerUsesTheConfiguredDay:
    """`runner.py:625` passed no hour, so it silently used the constant."""

    def test_the_pass_hands_its_day_to_the_pnl_read(self, conn, monkeypatch):
        """Dropping `day_start_hour=` at the `daily_realised_pnl_dollars` call
        turns this red: the recorder sees 10 instead of 3.
        """
        seen: dict = {}

        def recorder(_conn, **kwargs):
            seen.update(kwargs)
            return 0.0

        monkeypatch.setattr(
            "backend.runner.daily_realised_pnl_dollars", recorder
        )
        run_pricing_pass(conn, [], now=NOW, day_start_hour=3)
        assert seen.get("day_start_hour") == 3, (
            "the runner's kill-switch day is not the one it was given"
        )

    def test_that_argument_is_load_bearing_and_not_decoration(self, conn):
        """The recorded argument changes the answer, so recording it means
        something.

        A $50 loss settled at 2026-08-08T05:00:00Z, read at 12:00Z the same day.
        The day that rolls at 03:00Z began before the loss and counts it; the
        day that rolls at 10:00Z began after it and does not -- so the hardcoded
        10 is the permissive reading, exactly as the module docstring says.
        """
        settled = 1_786_165_200_000   # 2026-08-08T05:00:00Z
        read_at = 1_786_190_400_000   # 2026-08-08T12:00:00Z
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
            "VALUES ('T', ?, ?)",
            (settled, settled),
        )
        conn.execute(
            "INSERT INTO orders (client_order_id, submitted_ms, ticker, side, "
            "action, order_type, count, limit_price_tenths, status, "
            "request_body_json, dry_run) "
            "VALUES ('r1', ?, 'T', 'yes', 'buy', 'limit', 10, 500, 'dry_run', "
            "'{}', 1)",
            (settled,),
        )
        conn.execute(
            "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
            "contracts, pnl_cents, dry_run, fill_assumption) "
            "SELECT id, ticker, ?, 'no', 10, -5000, 1, 'test' FROM orders "
            "WHERE client_order_id = 'r1'",
            (settled,),
        )
        conn.commit()

        at_three = daily_realised_pnl_dollars(
            conn, now_ms=read_at, dry_run=True, day_start_hour=3
        )
        at_ten = daily_realised_pnl_dollars(
            conn, now_ms=read_at, dry_run=True, day_start_hour=10
        )
        assert at_three == -50.0
        assert at_ten == 0.0, (
            "the two hours must disagree here, or the recorder test above is "
            "asserting on an argument that could not change anything"
        )

    @pytest.mark.parametrize("hour", [0, 3, 6, 9, 10, 11, 14, 23])
    def test_the_runners_day_never_starts_later_than_the_endpoints(
        self, conn, monkeypatch, hour
    ):
        """The permissive direction, pinned. RED if the runner ever defaults.

        A later start counts less of today's losses as today's, so the kill
        switch engages less. If the runner's day could start after the order
        endpoint's, the runner would size and surface a card the endpoint then
        refuses -- and with `hour < 10` that is exactly what the old defaulting
        code did. Equality is the passing state; "not later" is asserted because
        it is the property that matters if the two ever legitimately differ.
        """
        seen: dict = {}

        def recorder(_conn, **kwargs):
            seen.update(kwargs)
            return 0.0

        monkeypatch.setattr(
            "backend.runner.daily_realised_pnl_dollars", recorder
        )
        run_pricing_pass(conn, [], now=NOW, day_start_hour=hour)

        # What `api/routes.py:1546` would compute for the same instant.
        endpoint_day = risk_day_start_ms(NOW, hour=hour)
        runner_day = risk_day_start_ms(NOW, hour=seen["day_start_hour"])
        assert runner_day <= endpoint_day, (
            "the runner's risk day starts later than the order endpoint's, so "
            "less of today's realised P&L reaches the kill switch on the slate "
            "than reaches it on the order"
        )
        assert runner_day == endpoint_day

    def test_the_full_pass_takes_its_day_from_the_odds_config(self):
        """`run_once` derives the hour rather than accepting one.

        It already requires an `OddsConfig`, which is the object that carries
        the configured hour, so deriving it there makes the full pass unable to
        forget. Source-asserted: the call is one line and no behavioural test
        distinguishes `config.budget_day_start_utc_hour` from a literal 10 on a
        machine where the variable is unset.
        """
        source = (ROOT / "backend" / "runner.py").read_text(encoding="utf-8")
        assert "day_start_hour=config.budget_day_start_utc_hour," in source

    def test_the_quote_cadence_is_given_the_configured_hour_too(self):
        """The fast pass runs ~96 times a day against the full pass's ~1.

        It takes no `OddsConfig` -- it spends no credits, which is the point --
        so it is the one entry point that would silently keep the default.
        """
        source = (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        assert re.search(
            r"run_quote_pass\(.*?day_start_hour=odds_config\."
            r"budget_day_start_utc_hour",
            source,
            re.S,
        ), "run_loop no longer hands the quote pass the configured risk day"


class TestTheAgentBudgetUsesTheConfiguredDay:
    """`.env.example` claimed this before the code did it."""

    def test_from_config_reads_the_configured_hour(self, conn, monkeypatch):
        """Dropping `day_start_hour=` from `from_config` turns this red."""
        monkeypatch.setenv("ODDS_BUDGET_DAY_START_UTC_HOUR", "3")

        class _Cfg:
            max_calls_per_pass = 8
            max_calls_per_day = 24

        meter = AgentBudget.from_config(conn, _Cfg())
        assert meter.day_start_hour == 3
        assert meter.day_start_ms(NOW) == risk_day_start_ms(NOW, hour=3), (
            "the agent day and the risk day must be cut on the same clock"
        )

    def test_the_old_behaviour_was_the_permissive_one(self, conn, monkeypatch):
        """Direction, stated as a test rather than only as prose.

        A later day start puts fewer `agent_calls` rows inside the window, so
        `spent_today` reads low and the daily cap lets *more* calls through. The
        hardcoded 10 was later than a configured 3, so the old code overspent.
        """
        monkeypatch.setenv("ODDS_BUDGET_DAY_START_UTC_HOUR", "3")

        class _Cfg:
            max_calls_per_pass = 8
            max_calls_per_day = 24

        configured = AgentBudget.from_config(conn, _Cfg())
        hardcoded = AgentBudget(conn, per_pass_budget=8, daily_budget=24)
        assert hardcoded.day_start_ms(NOW) > configured.day_start_ms(NOW)


class TestTheEnvironmentIsParsedOnce:
    """Two parses of one variable drift, and the drift is invisible."""

    def test_the_hour_has_one_reader(self, monkeypatch):
        monkeypatch.setenv("ODDS_BUDGET_DAY_START_UTC_HOUR", "7")
        assert configured_day_start_utc_hour() == 7
        assert OddsConfig.load_without_credentials().budget_day_start_utc_hour == 7

    def test_an_out_of_range_hour_raises_in_both_constructors(self, monkeypatch):
        """`load_without_credentials` validated nothing until 2026-08-11.

        The demo instance and every credential-free reader used it, so
        `hour=99` would have travelled to a `datetime.replace` far from the
        config layer -- unreadable resolving to a crash somewhere else, rather
        than a refusal here.
        """
        from backend.config import ConfigError

        monkeypatch.setenv("ODDS_BUDGET_DAY_START_UTC_HOUR", "99")
        with pytest.raises(ConfigError):
            configured_day_start_utc_hour()
        with pytest.raises(ConfigError):
            OddsConfig.load_without_credentials()
