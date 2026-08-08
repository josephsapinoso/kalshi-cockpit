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
