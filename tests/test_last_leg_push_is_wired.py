"""The last-leg push (#329) is wired on the live loop and has a public
notifier method -- the two halves the lane could not touch.

What this establishes: the loop passes a book reader to the watcher on a
non-demo instance and none on demo; `DiscordNotifier.last_leg_watch` exists,
posts the pre-rendered sentence verbatim, and links to the held-bets screen.
What it does not establish: that the reader returns a real book on live, or
that Discord delivers -- a respx mock stands in for the transport.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import httpx
import respx

from backend.notify.discord import DiscordConfig, DiscordNotifier

ROOT = Path(__file__).resolve().parents[1]
RUN_LOOP = ROOT / "scripts" / "run_loop.py"


def _hedge_watch_call_kwargs() -> set[str]:
    tree = ast.parse(RUN_LOOP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "watch_hedges_forever"
        ):
            return {kw.arg for kw in node.keywords if kw.arg}
    raise AssertionError("run_loop.py no longer calls watch_hedges_forever")


class TestTheLoopPassesTheBookReader:
    def test_the_watcher_call_carries_read_combo_book(self):
        assert "read_combo_book" in _hedge_watch_call_kwargs()

    def test_the_reader_is_built_only_off_demo_and_waits_on_the_shared_timeout(self):
        source = RUN_LOOP.read_text(encoding="utf-8")
        assert "if not AppConfig.load().is_demo:" in source
        assert "timeout=COMBO_BOOK_READ_TIMEOUT_S" in source
        # The reader reaches the venue through the loop's own client and
        # asks for a BOOK, never a quote request: no RFQ word near it.
        start = source.index("read_combo_book = None")
        end = source.index("hedge_task = asyncio.create_task", start)
        block = source[start:end].lower()
        assert "orderbook(" in block
        assert "rfq" not in block and "accept" not in block


class TestTheNotifierHasAPublicMethod:
    def test_last_leg_watch_posts_the_sentence_verbatim(self):
        config = DiscordConfig(
            webhook_url="https://discord.test/webhook",
            cockpit_base_url="https://cockpit.test",
        )
        text = (
            "4 of 5 legs won. The book bids 5.1c a contract for this card now. "
            "Holding is worth about 91.5c a contract at the last leg's Kalshi "
            "price. Makers on tap."
        )

        async def run() -> dict:
            with respx.mock(assert_all_called=True) as mock:
                route = mock.post("https://discord.test/webhook").mock(
                    return_value=httpx.Response(204)
                )
                async with DiscordNotifier(config) as notifier:
                    ok = await notifier.last_leg_watch({"label": "Sunday six"}, text)
                assert ok is True
                return route.calls[0].request

        request = asyncio.run(run())
        body = request.content.decode("utf-8")
        assert text in body
        assert "One leg left" in body and "Sunday six" in body
        assert "/bets#open" in body
        lowered = body.lower()
        for forbidden in ("cash out", "lock", "should", "at least"):
            assert forbidden not in lowered

    def test_the_alerter_prefers_the_public_method_over_the_private_post(self):
        source = (ROOT / "backend" / "notify" / "alerts.py").read_text(encoding="utf-8")
        assert 'getattr(self.notifier, "last_leg_watch", None)' in source
