"""Shared pytest fixtures and path setup.

Lives at the repo root rather than in tests/ so that `backend.*` imports resolve
without an editable install -- pytest inserts the rootdir containing conftest.py
onto sys.path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def no_live_agent_calls(monkeypatch):
    """No test may reach the Anthropic API, whatever is in the environment.

    `backend/config.py` calls `load_dotenv()` at import, and every test imports
    it, so a developer with `ANTHROPIC_API_KEY` in `.env` had the key in
    `os.environ` for the whole suite. `AgentConfig.from_env()` reads exactly
    that, so the moment a test drives a *surfaced* row through
    `run_pricing_pass`, the Skeptic fires for real -- billed, over the network,
    and only on the machines that hold the secret.

    That is the failure `tasks/lessons.md` already names twice: **a test that
    depends on an input it does not supply is measuring the environment.** It
    would pass locally by calling Claude and pass in CI by silently skipping the
    review, and the two runs would be asserting different things under one name.

    So the key is removed for every test, and any test that wants a verdict
    injects a config and a client of its own. `raising=False` because most
    machines -- CI included -- do not have it set at all.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_live_kalshi_credentials(monkeypatch):
    """No test may hold Kalshi credentials, whatever is in the environment.

    Same mechanism as `no_live_agent_calls` above, and a strictly worse failure
    if it is missing. `load_dotenv()` at `backend/config.py` import time puts
    `.env` into `os.environ` for the whole suite, so on the owner's machine
    `KalshiConfig.load()` inside a test returned **real, signed credentials**.

    That was survivable only while no production code path could ask for a live
    `OrderPlacer` during a test. It stopped being survivable on 2026-08-26,
    when `MANUAL_ORDERS_ARE_DRY_RUNS` was set to False: from that commit the
    manual route builds a REST client and POSTs, so a test driving the happy
    path on a machine holding `.env` would have **sent a real order to the
    exchange**. Not hypothetical -- this suite runs on the machine with the key.

    So both credential variables are removed for every test.
    `KalshiConfig.load()` then raises `ConfigError` (`_require` on
    `KALSHI_PRIVATE_KEY_PATH`), the route words it as a 503, and nothing
    reaches the venue. A test that wants the armed path injects its own fake
    client and asserts on that.

    `KALSHI_PUBLIC_READ_ONLY` is deliberately NOT set here. Setting it would
    hand every test a config object that succeeds, which is the opposite of the
    intent: asking for credentials inside a test must **fail**, at the first
    call, loudly.
    """
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)


@pytest.fixture(autouse=True)
def odds_sweep_cost_is_supplied_not_ambient(monkeypatch):
    """The sweep cost is pinned to the deployed contract, for every test.

    `credits_per_sweep_per_sport` is `len(markets) * len(regions)`, both read
    from the environment through `load_dotenv()`. So any test that asserts a
    credit figure was reading whatever `.env` the machine happened to hold --
    the same failure `no_live_agent_calls` above exists for, with the odds
    config as the hidden input instead of a secret.

    It was not hypothetical. Two tests passed locally and failed in CI from
    2026-08-20, with no code change between them:

        test_it_reports_the_remaining_budget_in_sweeps   assert 2 == 0
        test_the_day_s_budget_still_refuses_a_tap...     '26' not in '...22'

    **And the values they were passing under run nowhere.** `ODDS_MARKETS` is
    not set on the live instance -- `flyctl secrets list` shows `ODDS_API_KEY`
    alone, and `fly.toml` sets neither -- so live takes the `h2h` default and a
    sweep costs 2. CI sets nothing either, so CI was right. The only machine
    that said 6 was a developer laptop whose `.env` disagrees with
    `.env.example`, which CLAUDE.md calls the contract. The green local run was
    the wrong one.

    Pinned to the contract rather than to the laptop, so a test that asserts a
    credit figure is asserting one the deployed system would actually produce.
    A test that wants different values sets them itself.
    """
    monkeypatch.setenv("ODDS_MARKETS", "h2h")
    monkeypatch.setenv("ODDS_REGIONS", "us,eu")


@pytest.fixture(autouse=True)
def forget_scope_warnings():
    """Unknown-scope warnings are deduplicated for the life of the *process*.

    That is deliberate -- re-warning every pass was 98 of the 100 lines in the
    live log buffer -- but it makes the warning a piece of cross-test state. Two
    tests using the same series would otherwise have their assertions decided by
    which one pytest happened to run first, and only the loser would fail. That
    is the environment-measurement failure this file's other autouse fixture
    exists for, with collection order as the hidden input rather than a secret.
    """
    from backend.kalshi.discovery import reset_scope_warnings

    reset_scope_warnings()
    yield
    reset_scope_warnings()


@pytest.fixture(autouse=True)
def forget_computed_joints():
    """The parlay copula cache is process-wide, so it is cross-test state.

    That is deliberate -- it exists because `/api/parlays` answered in 2.3s
    warm while recomputing a 200,000-sample Monte-Carlo per request -- but a
    cache that outlives a REQUEST also outlives a TEST, and every test that
    counts calls to `_joint` then has its assertion decided by which test
    pytest happened to run first. Exactly the hazard `forget_scope_warnings`
    above exists for, with collection order as the hidden input.

    Caught by `tests/test_ladder.py::TestJointMemo` going red the first time
    the whole suite ran after the cache was hoisted, which is the test doing
    its job.
    """
    from backend.core.ladder import _JOINT_CACHE

    _JOINT_CACHE.clear()
    yield
    _JOINT_CACHE.clear()


def load_fixture(name: str):
    """Load a captured API payload, skipping the test if it hasn't been captured.

    Wire-format tests must load real captured payloads, never hand-constructed
    ones. A hand-written fixture only proves the code agrees with the test
    author's memory of the API -- which is exactly how the previous project
    parsed every order book to zero levels, silently, for its entire life while
    305 synthetic tests passed.

    Skipping rather than failing on a missing fixture keeps the suite green for
    a contributor who has no credentials, while still refusing to substitute
    invented data.
    """
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(
            f"Fixture {name} not captured yet. Run the discovery spike "
            f"(scripts/capture_fixtures.py) against the live API to create it."
        )
    return json.loads(path.read_text(encoding="utf-8"))
