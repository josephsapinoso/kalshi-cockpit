"""The prop-dispersion probe must never let the Odds API key reach output.

What this establishes: `_get_with_key` converts every failure path — non-200
status and escaping httpx exceptions — into a `SystemExit` whose message
carries neither the key nor the URL that embeds it. What it does NOT
establish: that the happy path parses odds correctly, or that any other
script is similarly guarded (see tasks/lessons.md 2026-08-20, the corrected
detection rule: grep for the credential entering `params=`, not for
`raise_for_status`).
"""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from probe_prop_dispersion import _get_with_key  # noqa: E402

SECRET = "SECRETKEY123456"


class TestProbeKeyWithheld:
    def test_non_200_exits_with_status_alone(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(401))
        with httpx.Client(transport=transport) as client:
            with pytest.raises(SystemExit) as excinfo:
                _get_with_key(
                    client,
                    "https://api.the-odds-api.com/v4/sports/baseball_mlb/events",
                    params={"apiKey": SECRET},
                )
        message = str(excinfo.value)
        assert "401" in message
        assert SECRET not in message
        assert "the-odds-api.com" not in message

    def test_transport_error_exits_with_class_alone(self):
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        transport = httpx.MockTransport(explode)
        with httpx.Client(transport=transport) as client:
            with pytest.raises(SystemExit) as excinfo:
                _get_with_key(
                    client,
                    "https://api.the-odds-api.com/v4/sports/baseball_mlb/events",
                    params={"apiKey": SECRET},
                )
        message = str(excinfo.value)
        assert "ConnectError" in message
        assert SECRET not in message
        assert "the-odds-api.com" not in message

    def test_200_passes_through(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=[])
        )
        with httpx.Client(transport=transport) as client:
            response = _get_with_key(
                client,
                "https://api.the-odds-api.com/v4/sports/baseball_mlb/events",
                params={"apiKey": SECRET},
            )
        assert response.json() == []
