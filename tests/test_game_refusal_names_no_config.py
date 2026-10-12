"""The /game 503 for a keyless instance says the state, not the variable (#369).

`ConfigError` text is the operator's sentence (it names the variable and the
`fly secrets` fix) and stays so; the screen must not print it. Establishes
nothing about any other refusal on these routes.
"""
from __future__ import annotations

import re

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig, ConfigError, KalshiConfig
from backend.store import db as store

HEADERS = {"Authorization": "Bearer secret-token"}
TOKEN = re.compile(r"[A-Z][A-Z0-9_]{5,}")


@pytest.fixture
def keyless_app(tmp_path, monkeypatch):
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.setenv("KALSHI_API_KEY", "key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    path = tmp_path / "t.db"
    store.init_db(path).close()
    return create_app(
        AppConfig(
            instance_mode="live",
            auth_token="secret-token",
            db_path=path,
        )
    )


async def _send(app, method, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.request(method, path, headers=HEADERS)


class TestCredentialsRefusal:
    def test_the_config_error_still_names_the_variable(self, monkeypatch):
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.setenv("KALSHI_API_KEY", "key")
        with pytest.raises(ConfigError, match="KALSHI_PRIVATE_KEY_PATH"):
            KalshiConfig.load()

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/game/KXNBAGAME-26OCT12AAABBB/legs"),
            ("POST", "/api/game/KXNBAGAME-26OCT12AAABBB/card"),
        ],
    )
    async def test_the_503_detail_names_no_config_variable(
        self, keyless_app, method, path
    ):
        r = await _send(keyless_app, method, path)
        assert r.status_code == 503, r.text
        detail = r.json()["detail"]
        assert "no Kalshi credentials on this instance" in detail
        assert not TOKEN.search(detail), detail
