"""Discord alerting tests.

Two properties are load-bearing:

1. **No order button, ever.** A tap-to-buy control in a chat client sits next
   to unrelated messages and is reachable by anyone who gets into the account.
2. **Alerting failure never propagates.** A Discord outage must degrade the
   tool to "no push notifications", never take down the loop recording
   evidence.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from backend.notify.discord import DiscordConfig, DiscordNotifier

CHANNEL = "123456789"
API = f"https://discord.com/api/v10/channels/{CHANNEL}/messages"


@pytest.fixture
def config():
    return DiscordConfig(
        bot_token="test-token",
        channel_id=CHANNEL,
        cockpit_base_url="https://cockpit.example",
    )


@pytest.fixture(scope="module")
def http_client():
    return httpx.AsyncClient(timeout=5.0)


@pytest.fixture
def notifier(config, http_client):
    return DiscordNotifier(config, client=http_client)


class FakeRec:
    ticker = "KXMLBGAME-26AUG09HOUSD-HOU"
    team = "Houston"
    reason_text = "Houston: consensus fair 53.8c, Kalshi asks 50.3c. Buy 15."
    fair_probability = 0.538
    entry_ask_tenths = 503
    edge_tenths = 17.0
    suggested_contracts = 15
    ev_net_dollars = 0.26
    kalshi_quote_age_ms = 3000
    odds_age_ms = 240_000


class TestNoOrderButton:
    """The security boundary. Confirmation happens in the authenticated app."""

    @respx.mock
    async def test_the_embed_carries_no_interactive_components(self, notifier):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.opportunity(FakeRec())
        body = route.calls.last.request.read().decode()
        assert "components" not in body
        assert "custom_id" not in body

    @respx.mock
    async def test_the_embed_says_where_to_confirm(self, notifier):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.opportunity(FakeRec())
        body = route.calls.last.request.read().decode()
        assert "never placed from Discord" in body

    @respx.mock
    async def test_the_embed_deep_links_into_the_cockpit(self, notifier):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.opportunity(FakeRec())
        assert "cockpit.example" in route.calls.last.request.read().decode()


class TestOpportunityContent:
    @respx.mock
    async def test_carries_what_a_decision_needs(self, notifier):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            assert await n.opportunity(FakeRec())
        body = route.calls.last.request.read().decode()
        for expected in ("Consensus fair", "Kalshi asks", "Edge, net of fees",
                         "Suggested", "Quote age"):
            assert expected in body

    @respx.mock
    async def test_authenticates_as_a_bot(self, notifier):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.opportunity(FakeRec())
        assert route.calls.last.request.headers["Authorization"] == "Bot test-token"


class TestFailureAlerts:
    """These matter most: a broken feed makes the Board look calm."""

    @respx.mock
    async def test_a_dead_feed_says_prices_are_frozen(self, notifier):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.feed_died("10 reconnect attempts failed")
        body = route.calls.last.request.read().decode()
        assert "frozen" in body
        assert "should be trusted" in body

    @respx.mock
    async def test_exhausted_credits_explain_that_it_is_the_budget_working(
        self, notifier
    ):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.credits_exhausted(0)
        assert "not a bug" in route.calls.last.request.read().decode()

    @respx.mock
    async def test_a_fee_mismatch_is_stop_the_line(self, notifier):
        """The fee model being wrong makes every EV figure wrong."""
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.fee_mismatch("MKT", predicted=1.75, actual=2.00)
        body = route.calls.last.request.read().decode()
        assert "stop the line" in body.lower()
        assert "Do not place further orders" in body


class TestDegradesGracefully:
    """Alerting is optional infrastructure. It must never take down ingest."""

    async def test_unconfigured_notifier_is_disabled_not_broken(self):
        notifier = DiscordNotifier(None)
        assert not notifier.enabled
        async with notifier as n:
            assert await n.opportunity(FakeRec()) is False

    @respx.mock
    async def test_an_api_error_returns_false_rather_than_raising(self, notifier):
        respx.post(API).mock(return_value=httpx.Response(403, text="forbidden"))
        async with notifier as n:
            assert await n.opportunity(FakeRec()) is False

    @respx.mock
    async def test_an_unreachable_discord_returns_false_rather_than_raising(
        self, notifier
    ):
        respx.post(API).mock(side_effect=httpx.ConnectError("down"))
        async with notifier as n:
            assert await n.feed_died("x") is False

    def test_missing_env_yields_none_rather_than_an_exception(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
        assert DiscordConfig.from_env() is None


class TestDigest:
    @respx.mock
    async def test_reports_progress_toward_the_gate(self, notifier):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.daily_digest(
                surfaced=2, suppressed=4, no_edge=3, scored=17, required=300,
                suppression_counts={"stale_odds": 3, "wide_market": 1},
            )
        body = route.calls.last.request.read().decode()
        assert "17 / 300" in body
        assert "stale_odds" in body

    @respx.mock
    async def test_frames_a_quiet_day_as_normal(self, notifier):
        route = respx.post(API).mock(return_value=httpx.Response(200, json={}))
        async with notifier as n:
            await n.daily_digest(
                surfaced=0, suppressed=0, no_edge=9, scored=0, required=300,
                suppression_counts={},
            )
        assert "not a malfunction" in route.calls.last.request.read().decode()


WEBHOOK = (
    "https://discord.com/api/webhooks/1402938475610293847/"
    "xQ2v9LmT4pR7wYzB1nK6sHfJdA0cE8gU3iO5rV7tX9yZ2bN4mQ6pL1kS"
)


class TestTheWebhookPath:
    """The credential shape a phone can actually produce.

    A bot needs the developer portal, an application, a token reset, an OAuth
    invite URL, and Developer Mode toggled on in the app to reveal a channel id.
    A webhook is four taps inside the Discord app and yields one string. Since
    this tool is operated from a phone, that gap is the difference between
    alerting being configured and not.
    """

    @pytest.fixture
    def hook_notifier(self, http_client):
        return DiscordNotifier(
            DiscordConfig(
                cockpit_base_url="https://cockpit.example", webhook_url=WEBHOOK
            ),
            client=http_client,
        )

    @respx.mock
    async def test_it_posts_the_same_embed_to_the_webhook(self, hook_notifier):
        route = respx.post(WEBHOOK).mock(return_value=httpx.Response(204))
        assert await hook_notifier.failure("Feed died", "detail") is True
        assert route.called
        embed = json.loads(route.calls[0].request.content)["embeds"][0]
        assert "Feed died" in embed["title"]

    @respx.mock
    async def test_it_sends_no_bot_header(self, hook_notifier):
        """A webhook authenticates by its URL. `Authorization: Bot None` is a
        401 that presents as "Discord refused everything" with a correct URL --
        which reads as a bad webhook rather than a bad header."""
        route = respx.post(WEBHOOK).mock(return_value=httpx.Response(204))
        await hook_notifier.failure("x", "y")
        assert "authorization" not in route.calls[0].request.headers

    @respx.mock
    async def test_a_dead_webhook_still_does_not_raise(self, hook_notifier):
        respx.post(WEBHOOK).mock(return_value=httpx.Response(404))
        assert await hook_notifier.failure("x", "y") is False


class TestWhichCredentialWins:
    def test_a_webhook_alone_configures_the_notifier(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
        config = DiscordConfig.from_env()
        assert config is not None
        assert config.endpoint == WEBHOOK

    def test_a_bot_alone_still_works(self, monkeypatch):
        """The older path is supported, not merely tolerated -- switching a
        working live instance to a new credential shape is a change nobody
        should be forced into by an upgrade."""
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", CHANNEL)
        config = DiscordConfig.from_env()
        assert config is not None
        assert config.endpoint.endswith(f"/channels/{CHANNEL}/messages")
        assert config.headers["Authorization"] == "Bot tok"

    def test_the_webhook_wins_when_both_are_set(self, monkeypatch):
        """Explicit, because the docs name the webhook as the path to use and a
        precedence left to import order is one nobody can predict."""
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", CHANNEL)
        assert DiscordConfig.from_env().endpoint == WEBHOOK

    def test_a_blank_webhook_is_not_a_configuration(self, monkeypatch):
        """`fly secrets set DISCORD_WEBHOOK_URL=` sets an empty string, not an
        absent variable, and an empty endpoint would post to nowhere forever."""
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "   ")
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
        assert DiscordConfig.from_env() is None


class TestTheWebhookNeverReachesALog:
    def test_the_token_is_redacted_from_a_log_line(self):
        """It is a credential in a URL *path*, so every pattern written for the
        Odds API key -- query parameters and bearer headers -- misses it."""
        from backend.logging_setup import redact

        assert "xQ2v9LmT4pR7wYzB1nK6sHfJdA0cE8gU3iO5rV7tX9yZ2bN4mQ6pL1kS" not in (
            redact(f"HTTP Request: POST {WEBHOOK} 204")
        )
