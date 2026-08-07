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
