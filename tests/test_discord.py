"""Discord alerting tests.

Two properties are load-bearing:

1. **No order button, ever.** A tap-to-buy control in a chat client sits next
   to unrelated messages and is reachable by anyone who gets into the account.
2. **Alerting failure never propagates.** A Discord outage must degrade the
   tool to "no push notifications", never take down the loop recording
   evidence.
"""

from __future__ import annotations

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
