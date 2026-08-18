"""The host a phone is sent to must be stated, and live must refuse a loopback.

**What this establishes:** that `COCKPIT_BASE_URL` is stated in both deploy
configs as an absolute non-loopback `https://` URL; that a live instance
refuses to boot when it is absent or loopback; that the pre-existing
`APP_AUTH_TOKEN` live refusal actually raises; and that a `DiscordNotifier`
built under the live `[env]` emits an embed whose link host is the deployed
one.

**What it does not establish:** that either URL points at a machine that is up,
that the webhook credential works (`.github/workflows/secrets.yml` posts a
synthetic embed for that), or that any alert has ever been delivered.
`notifications.delivered` is written and read by nothing outside tests.

Why it exists. Until 2026-08-18 `COCKPIT_BASE_URL` appeared in three source
files and **zero tests**, and in neither fly config. Live therefore ran on
`backend/config.py`'s `http://localhost:3000` default for the life of the
alerter, so every Discord embed that reached Joe's phone linked to the phone
itself. `tests/test_discord.py` could not catch it: every test there hands
`DiscordConfig` a good `cockpit_base_url` by construction, so `from_env`'s
default is never exercised — the same self-constructing shape that
`test_has_callers.py:483-488` was built for.

**The `APP_AUTH_TOKEN` case here is not padding.** That refusal has guarded
live since it was written and had never been watched to fail: grep across
`tests/` returns one hit, `test_build_identity.py:244`, which sets the variable
as a decoy secret and never calls `AppConfig.load()`. Nothing in the repo
called `AppConfig.load()` under `pytest.raises` before this file. A refusal
nobody has seen refuse is decoration, and it was three lines away.

**Generalisation deliberately not attempted here.** The durable fix is the
enumerate-and-classify inversion: AST-walk `backend/config.py` for every
`_optional(NAME, default)` and require each name to be stated in both `[env]`
blocks or listed in an explicit table of defaults-that-are-decisions. This file
guards one setting; that walk would guard the class. It needs its own ADR.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
import respx

from backend.config import AppConfig, ConfigError
from backend.notify.discord import DiscordConfig, DiscordNotifier

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_CONFIGS = {
    "fly.live.toml": REPO_ROOT / "fly.live.toml",
    "fly.demo.toml": REPO_ROOT / "fly.demo.toml",
}

SETTING = "COCKPIT_BASE_URL"

# Every spelling of "this machine". A live instance must reject all of them:
# the value is handed to a phone, where none of them resolves to the cockpit.
LOOPBACK_HOSTS = ["localhost", "127.0.0.1"]

WEBHOOK = "https://discord.com/api/webhooks/1/abcdef"


def deployed_env(name: str) -> dict:
    return tomllib.loads(DEPLOY_CONFIGS[name].read_text(encoding="utf-8"))["env"]


@pytest.fixture(scope="module")
def live_env():
    return deployed_env("fly.live.toml")


@pytest.fixture(scope="module")
def demo_env():
    return deployed_env("fly.demo.toml")


class FakeRec:
    """The minimum an `opportunity()` embed reads. Mirrors `test_discord.py`."""

    ticker = "KXMLBGAME-26AUG09HOUSD-HOU"
    team = "Houston"
    reason_text = "Houston: consensus fair 53.8%, Kalshi asks 50.3c. Buy 15."
    fair_probability = 0.538
    entry_ask_tenths = 503
    edge_tenths = 17.0
    suggested_contracts = 15
    ev_net_dollars = 0.26
    kalshi_quote_age_ms = 3000
    odds_age_ms = 240_000


class TestTheSettingIsStatedInBothConfigs:
    """A value nobody chose is not a value — the `fly.demo.toml` risk-cap rule."""

    @pytest.mark.parametrize("config_name", sorted(DEPLOY_CONFIGS))
    def test_the_setting_is_present(self, config_name):
        assert SETTING in deployed_env(config_name), (
            f"{SETTING} is absent from {config_name}, so that instance falls "
            f"through to backend/config.py's localhost default."
        )

    @pytest.mark.parametrize("config_name", sorted(DEPLOY_CONFIGS))
    def test_the_value_is_an_absolute_https_url(self, config_name):
        parsed = urlparse(deployed_env(config_name)[SETTING])
        assert parsed.scheme == "https", f"{config_name}: {SETTING} must be https"
        assert parsed.netloc, f"{config_name}: {SETTING} has no host"

    @pytest.mark.parametrize("config_name", sorted(DEPLOY_CONFIGS))
    def test_the_host_is_not_loopback(self, config_name):
        value = deployed_env(config_name)[SETTING]
        for host in LOOPBACK_HOSTS:
            assert host not in value, (
                f"{config_name}: {SETTING}={value!r} points at the machine "
                f"reading it. On a phone that is the phone."
            )

    def test_the_two_instances_do_not_share_a_host(self, live_env, demo_env):
        """Vacuity guard: pasting one host into both configs must be visible.

        Every assertion above passes if live and demo carry the same URL, and
        that failure is worse than an omission — a demo alert would deep-link
        into the instance holding real credentials.
        """
        assert live_env[SETTING] != demo_env[SETTING]


class TestLiveRefusesToBootWithoutAPublicHost:
    """The refusal, watched failing. `create_app` runs this at boot under
    uvicorn, which `entrypoint.sh` supervises with `wait -n` — so a raise here
    takes the container down rather than serving a broken link."""

    @pytest.fixture(autouse=True)
    def _live_and_authed(self, monkeypatch):
        """Everything a live boot needs EXCEPT the setting under test.

        Without the token the loader raises on `APP_AUTH_TOKEN` first and every
        test below would pass for the wrong reason.
        """
        monkeypatch.setenv("INSTANCE_MODE", "live")
        monkeypatch.setenv("APP_AUTH_TOKEN", "a-token")

    def test_unset_is_refused(self, monkeypatch):
        monkeypatch.delenv(SETTING, raising=False)
        with pytest.raises(ConfigError, match=SETTING):
            AppConfig.load()

    @pytest.mark.parametrize("host", LOOPBACK_HOSTS)
    def test_a_loopback_host_is_refused(self, host, monkeypatch):
        monkeypatch.setenv(SETTING, f"http://{host}:3000")
        with pytest.raises(ConfigError, match=SETTING):
            AppConfig.load()

    def test_a_public_host_is_accepted(self, monkeypatch):
        """The other half. A guard that refuses everything is not a guard."""
        monkeypatch.setenv(SETTING, "https://kalshi-cockpit.fly.dev")
        assert AppConfig.load().cockpit_base_url == "https://kalshi-cockpit.fly.dev"

    def test_demo_is_not_subject_to_the_refusal(self, monkeypatch):
        """Local development is the demo mode, and localhost is correct there."""
        monkeypatch.setenv("INSTANCE_MODE", "demo")
        monkeypatch.setenv(SETTING, "http://localhost:3000")
        assert AppConfig.load().cockpit_base_url == "http://localhost:3000"


class TestTheAuthTokenRefusalAlsoRaises:
    """The pre-existing guard nobody had watched fail.

    Not this file's subject, but it is the guard the one above was modelled on
    and it was three lines from being exercised. A copied refusal is only worth
    what the original is.
    """

    def test_live_without_a_token_is_refused(self, monkeypatch):
        monkeypatch.setenv("INSTANCE_MODE", "live")
        monkeypatch.delenv("APP_AUTH_TOKEN", raising=False)
        monkeypatch.setenv(SETTING, "https://kalshi-cockpit.fly.dev")
        with pytest.raises(ConfigError, match="APP_AUTH_TOKEN"):
            AppConfig.load()

    def test_demo_without_a_token_boots(self, monkeypatch):
        monkeypatch.setenv("INSTANCE_MODE", "demo")
        monkeypatch.delenv("APP_AUTH_TOKEN", raising=False)
        assert AppConfig.load().auth_token is None


class TestTheEmbedLinkCarriesTheDeployedHost:
    """End-to-end, and this is the assertion that catches the whole class.

    Every test in `test_discord.py` constructs `DiscordConfig` with a good
    `cockpit_base_url`, so none of them can see what `from_env` would have
    produced on the live machine. This one builds the notifier the way the
    deployed process does — from the environment — and reads the host back off
    the embed that would have reached the phone.
    """

    @pytest.fixture(autouse=True)
    def _live_environment(self, live_env, monkeypatch):
        monkeypatch.setenv(SETTING, live_env[SETTING])
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)

    @respx.mock
    async def test_the_opportunity_link_host_is_the_deployed_one(self, live_env):
        route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={}))

        async with DiscordNotifier(DiscordConfig.from_env()) as notifier:
            assert await notifier.opportunity(FakeRec())

        embed = route.calls.last.request.read()
        url = httpx.Response(200, content=embed).json()["embeds"][0]["url"]
        assert urlparse(url).netloc == urlparse(live_env[SETTING]).netloc
        for host in LOOPBACK_HOSTS:
            assert host not in url

    @respx.mock
    async def test_the_link_addresses_the_ticker_on_a_page_that_reads_it(self):
        """`/?focus=` was read by nothing; `/market/<ticker>` is a real route.

        The host fix alone would have produced a link that loads the Board and
        silently ignores the ticker — a bug that survives its own fix. This
        asserts the path, not just the host, and the frontend route it names is
        `frontend/src/app/market/[ticker]/page.tsx`.
        """
        route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={}))

        async with DiscordNotifier(DiscordConfig.from_env()) as notifier:
            assert await notifier.opportunity(FakeRec())

        body = route.calls.last.request.read()
        url = httpx.Response(200, content=body).json()["embeds"][0]["url"]
        assert urlparse(url).path == f"/market/{FakeRec.ticker}"
        assert "focus" not in url
