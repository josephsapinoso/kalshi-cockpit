"""Discord alerting.

You are not at a laptop, so the tool has to reach you. Discord gets native push
to a phone with no app install and no PWA quirks, and it renders an embed well
enough to make a decision from.

**Alerts carry no order button, deliberately.** Discord could support one —
interactions are signed and it would be convenient. But a tap-to-buy control in
a chat client is a footgun: it sits next to unrelated messages, it is reachable
by anyone who gets into the account, and it is exactly the surface where a
misfire is easiest. The embed deep-links into the authenticated cockpit and the
confirmation happens there.

Three classes of message, and the third matters most:

- **Opportunities.** Only surfaced ones. A phone notification for every
  suppressed candidate would train you to ignore the channel.
- **Digests.** Daily summary and the weekly Historian post-mortem.
- **Failures.** A dead WebSocket, an exhausted credit budget, or a fee
  mismatch. These are the ones you cannot discover by looking at the Board,
  because a broken feed makes the Board look *calm* — prices simply stop
  moving, and stale numbers render exactly like fresh ones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"

# Discord embed colours, as integers.
COLOUR_OPPORTUNITY = 0x1A7F52   # --positive
COLOUR_DIGEST = 0xB3995D        # --accent-2
COLOUR_FAILURE = 0xAA0000       # --accent


@dataclass(frozen=True)
class DiscordConfig:
    bot_token: str
    channel_id: str
    cockpit_base_url: str

    @classmethod
    def from_env(cls) -> Optional["DiscordConfig"]:
        """Returns None when unconfigured rather than raising.

        Alerting is optional infrastructure. A missing Discord token should
        degrade the tool to "no push notifications", never take down the
        ingest loop that is recording evidence.
        """
        import os

        token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        channel = os.getenv("DISCORD_CHANNEL_ID", "").strip()
        if not token or not channel:
            return None
        return cls(
            bot_token=token,
            channel_id=channel,
            cockpit_base_url=os.getenv("COCKPIT_BASE_URL", "").strip()
            or "http://localhost:3000",
        )


class DiscordNotifier:
    """Posts to one channel. Never raises into the caller."""

    def __init__(
        self, config: Optional[DiscordConfig], *, client: Optional[httpx.AsyncClient] = None
    ):
        self.config = config
        self._client = client
        self._owns_client = client is None

    @property
    def enabled(self) -> bool:
        return self.config is not None

    async def __aenter__(self) -> "DiscordNotifier":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
            self._owns_client = True
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _post(self, embed: dict) -> bool:
        """Send one embed. Returns whether it landed.

        Swallows transport failures on purpose: a Discord outage must not stop
        the ingest loop, and the alert it could not deliver is still recorded
        in the database either way.
        """
        if not self.config or self._client is None:
            return False
        try:
            response = await self._client.post(
                f"{DISCORD_API}/channels/{self.config.channel_id}/messages",
                headers={"Authorization": f"Bot {self.config.bot_token}"},
                json={"embeds": [embed]},
            )
            if response.status_code >= 400:
                logger.warning(
                    "discord post failed: HTTP %d %s",
                    response.status_code, response.text[:200],
                )
                return False
            return True
        except httpx.HTTPError:
            logger.warning("discord unreachable", exc_info=True)
            return False

    # -- opportunities -----------------------------------------------------

    async def opportunity(self, rec, *, ticker_url: Optional[str] = None) -> bool:
        """Alert on one surfaced opportunity.

        The embed carries what a decision needs — fair, ask, edge, stake,
        freshness — and a link. No button.
        """
        if not self.config:
            return False

        url = ticker_url or f"{self.config.cockpit_base_url}/?focus={rec.ticker}"
        edge = rec.edge_tenths / 10.0

        return await self._post(
            {
                "title": f"{getattr(rec, 'team', None) or rec.ticker}",
                "description": rec.reason_text,
                "url": url,
                "color": COLOUR_OPPORTUNITY,
                "fields": [
                    _field("Consensus fair", f"{rec.fair_probability * 100:.1f}c"),
                    _field("Kalshi asks", f"{rec.entry_ask_tenths / 10:.1f}c"),
                    _field("Edge, net of fees", f"{edge:+.1f}c"),
                    _field("Suggested", f"{rec.suggested_contracts} contracts"),
                    _field(
                        "Expected",
                        f"{rec.ev_net_dollars:+.2f} on "
                        f"${rec.entry_ask_tenths / 1000 * rec.suggested_contracts:.2f}",
                    ),
                    _field(
                        "Quote age",
                        f"{rec.kalshi_quote_age_ms / 1000:.0f}s / "
                        f"books {rec.odds_age_ms / 60000:.0f}m",
                    ),
                ],
                # Says out loud why there is no button here.
                "footer": {
                    "text": "Confirm in the cockpit — orders are never placed from Discord."
                },
            }
        )

    # -- digests -----------------------------------------------------------

    async def daily_digest(
        self,
        *,
        surfaced: int,
        suppressed: int,
        no_edge: int,
        scored: int,
        required: int,
        suppression_counts: dict[str, int],
    ) -> bool:
        if not self.config:
            return False

        top = sorted(suppression_counts.items(), key=lambda kv: -kv[1])[:4]
        breakdown = "\n".join(f"`{name}` × {n}" for name, n in top) or "none"

        return await self._post(
            {
                "title": "Daily summary",
                "color": COLOUR_DIGEST,
                "fields": [
                    _field("Surfaced", str(surfaced)),
                    _field("Suppressed", str(suppressed)),
                    _field("No edge", str(no_edge)),
                    _field("Scored on CLV", f"{scored} / {required}", inline=False),
                    _field("Top suppression reasons", breakdown, inline=False),
                ],
                "footer": {
                    "text": "Most candidates have no edge. A quiet day is the "
                            "normal result, not a malfunction."
                },
            }
        )

    # -- failures ----------------------------------------------------------

    async def failure(self, kind: str, detail: str) -> bool:
        """Alert on something the Board cannot show you.

        A broken feed makes the cockpit look *calm*: prices stop moving and
        stale numbers render identically to fresh ones. These alerts exist
        because silence is the symptom.
        """
        if not self.config:
            return False
        return await self._post(
            {
                "title": f"⚠ {kind}",
                "description": detail,
                "color": COLOUR_FAILURE,
                "footer": {
                    "text": "A broken feed looks like a quiet market. Check the "
                            "cockpit before trusting any price."
                },
            }
        )

    async def feed_died(self, detail: str) -> bool:
        return await self.failure(
            "Kalshi feed died",
            f"{detail}\n\nEvery downstream price is now frozen at its last "
            f"value. Nothing on the Board should be trusted until this "
            f"reconnects.",
        )

    async def credits_exhausted(self, remaining: int) -> bool:
        return await self.failure(
            "Odds credits exhausted",
            f"{remaining} credits left this period. Odds fetches are being "
            f"refused, so opportunities will stop appearing — that is the "
            f"budget working, not a bug.",
        )

    async def fee_mismatch(self, ticker: str, predicted: float, actual: float) -> bool:
        return await self.failure(
            "Fee model mismatch — stop the line",
            f"`{ticker}`: predicted ${predicted:.2f}, Kalshi charged "
            f"${actual:.2f}.\n\nThe fee model is wrong, so every EV figure is "
            f"wrong by an unknown amount. Do not place further orders until "
            f"`core/fees.py` is reconciled against real fills.",
        )


def _field(name: str, value: str, *, inline: bool = True) -> dict:
    return {"name": name, "value": value, "inline": inline}
