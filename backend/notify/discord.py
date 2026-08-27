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
from urllib.parse import quote

import httpx

from backend.config import DEFAULT_COCKPIT_BASE_URL

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"

# Discord embed colours, as integers.
COLOUR_OPPORTUNITY = 0x1A7F52   # --positive
COLOUR_DIGEST = 0xB3995D        # --accent-2
COLOUR_FAILURE = 0xAA0000       # --accent
#: Parlay cards get `--accent-2`, the same neutral as the digest, and
#: **deliberately not** `COLOUR_OPPORTUNITY`. Green is this palette's "we found
#: something" and a parlay card is not that: it is fair value on a combination
#: Joe asked to see, with no edge claimed and none measured. ADR 0071 SS2.5 --
#: showing a number is transparency, ranking or colouring by it is a claim.
COLOUR_PARLAY = 0xB3995D


@dataclass(frozen=True)
class DiscordConfig:
    """Where to post. Two shapes, and the simpler one is the default.

    **A webhook URL** (`DISCORD_WEBHOOK_URL`) is one string, created inside the
    Discord mobile app in about four taps: channel -> Edit Channel ->
    Integrations -> Webhooks -> New Webhook -> Copy URL. No developer portal, no
    application, no OAuth invite, no Developer Mode toggle to reveal a channel
    id. Since this tool is operated from a phone, that difference is the whole
    difference between alerting being configured and not.

    **A bot token plus channel id** is the older path and still supported. It
    buys nothing this alerter uses -- it posts embeds to one channel and nothing
    else -- and its token is broader: a bot token works everywhere the bot has
    been added, while a webhook can only post to the one channel it was made in.
    So the webhook is not merely easier, it is the smaller credential.

    A webhook URL carries its token **in the path**, which is the same hazard as
    the Odds API key in a query string. `logging_setup` redacts it; see
    `_WEBHOOK_PATTERN` there and `tasks/lessons.md`.
    """

    cockpit_base_url: str
    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None
    channel_id: Optional[str] = None

    @classmethod
    def from_env(cls) -> Optional["DiscordConfig"]:
        """Returns None when unconfigured rather than raising.

        Alerting is optional infrastructure. A missing Discord credential should
        degrade the tool to "no push notifications", never take down the ingest
        loop that is recording evidence.

        The webhook wins when both are set. Silently preferring one of two
        configured transports is a thing to be explicit about rather than to
        leave to import order -- and this order is the one a reader can predict
        from the docs, which name the webhook as the path to use.
        """
        import os

        base = os.getenv("COCKPIT_BASE_URL", "").strip() or DEFAULT_COCKPIT_BASE_URL

        webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        if webhook:
            return cls(cockpit_base_url=base, webhook_url=webhook)

        token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        channel = os.getenv("DISCORD_CHANNEL_ID", "").strip()
        if not token or not channel:
            return None
        return cls(
            cockpit_base_url=base, bot_token=token, channel_id=channel
        )

    @property
    def endpoint(self) -> str:
        if self.webhook_url:
            return self.webhook_url
        return f"{DISCORD_API}/channels/{self.channel_id}/messages"

    @property
    def headers(self) -> dict[str, str]:
        """A webhook authenticates by its URL and must carry no bot header.

        Sending `Authorization: Bot <empty>` to a webhook is a 401, and the
        failure would present as "Discord refused everything" with a correct
        URL -- which reads as a bad webhook rather than a bad header.
        """
        if self.webhook_url:
            return {}
        return {"Authorization": f"Bot {self.bot_token}"}


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
                self.config.endpoint,
                headers=self.config.headers,
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

        **The link goes to `/market/<ticker>`, and the two reasons are
        separate.** It used to be `/?focus=<ticker>`, which was broken twice
        over: the host was `localhost:3000` because no deploy file stated
        `COCKPIT_BASE_URL`, and `focus` was read by nothing —
        `frontend/src/app/page.tsx` types its params as `{ rejected?: string }`
        and no file in the tree reads a `focus` param. Fixing the host alone
        would have produced a link that loads the Board and ignores the ticker,
        which is the plausible-looking half-fix.

        `/market/[ticker]` is genuinely ticker-addressable and **still renders
        after the opportunity expires**, which the Board does not — an alert
        read twenty minutes late lands on the price history rather than on a
        page that has forgotten the row.
        """
        if not self.config:
            return False

        url = ticker_url or (
            f"{self.config.cockpit_base_url}/market/{quote(rec.ticker, safe='')}"
        )
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

    async def window_open(self, *, window, surfaced: int) -> bool:
        """The odds just refreshed, so the slate is briefly bettable.

        The alert without which the rest of the tool cannot be used. Credits
        afford two sweeps a day and the consensus goes stale in fifteen minutes,
        so if this does not reach a phone at the moment it happens, nobody is
        looking when it matters.

        It reports **both** limits, because they are not the same number and
        they are kept fresh by different things: the books last
        `max_odds_age_s` and can only be refreshed by spending a credit, while
        each row also needs a Kalshi quote under thirty seconds -- which a quote
        pass re-reads every fifteen seconds for as long as the window is open
        (`runner.run_quote_pass`).

        Both are still stated. The fifteen minutes is real *because* the fast
        cadence exists, not on its own: with a single 900s cadence this alert
        promised fifteen minutes of actionability and delivered thirty seconds.
        An alert quoting only the odds limit would be right today and would go
        back to lying the moment the quote pass stopped running, with nothing to
        say it had.
        """
        if not self.config:
            return False

        closes = (
            f"about {round(window.seconds_remaining / 60)} min"
            if window.seconds_remaining
            else "shortly"
        )
        headline = (
            f"{surfaced} bet{'' if surfaced == 1 else 's'} on the board"
            if surfaced
            else "Nothing surfaced"
        )
        return await self._post(
            {
                "title": "Odds are fresh — the window is open",
                "description": (
                    f"**{headline}.** Fresh odds are a chance to look, not a "
                    f"signal to bet: most windows open onto an empty board, "
                    f"which is the expected result."
                ),
                "url": self.config.cockpit_base_url,
                "color": COLOUR_OPPORTUNITY if surfaced else COLOUR_DIGEST,
                "fields": [
                    _field("Closes in", closes),
                    _field(
                        "Fixtures priced",
                        f"{window.fixtures_fresh} of {window.fixtures_upcoming}",
                    ),
                    _field(
                        "Credits left today",
                        f"{window.sweeps_remaining_today} sweep(s)",
                    ),
                ],
                "footer": {
                    "text": "A row also needs a Kalshi quote under 30s, so "
                            "individual bets expire sooner than this window."
                },
            }
        )

    async def parlay_card(self, card: dict, *, notes: dict) -> bool:
        """One parlay card from the desk, rendered for a phone.

        **Every number here is a string the server already rendered.** `card`
        is a `parlays._serialise_card` payload verbatim, and this method does
        no arithmetic on it -- not a rounding, not a percentage, not a
        multiplication. The screen and the embed therefore cannot disagree,
        which they would within a week if this formatted its own floats. The
        same rule `frontend/src/lib/api.ts` keeps, for the same reason.

        **It states fair value and no edge, and that is the product.** ADR 0071
        settles the desk's job as price transparency: what a combination is
        worth by the books' consensus, beside what Kalshi charges. There is no
        edge on this embed because none is claimed and none was measured --
        `beta = -0.141` (ADR 0038). Nothing here ranks cards against each other
        either; they go out in ladder order, which is a shape (2 legs, 4, 6),
        not a judgement.

        **The four caveats travel verbatim.** `parlays.NOTES` says the cost is
        fair value rather than a quote, that Kalshi's combo price exists only
        once built and will differ, that combos are enter-only, and that the
        fee model is unverified. Two of those are the difference between a
        number and money. They are passed in rather than imported so this
        module keeps its one-way dependency on nothing.

        **No button, and the link goes to the cockpit.** Same ruling as
        `opportunity` above and the module docstring: a tap-to-buy control in a
        chat client is a footgun, and the combination has to be built in the
        Kalshi app anyway.
        """
        if not self.config:
            return False
        if card.get("not_built_reason") is not None:
            # A card that did not build is not news on a phone. The screen says
            # why, in the slot the card would have occupied; a push saying
            # "nothing tonight" is a notification with no action behind it.
            return False

        joint = card.get("joint") or {}
        legs = card.get("legs") or []

        fields = [
            _field(
                # `event_title` is the fixture, `label` is the side taken. Both,
                # because "Yankees" alone does not say against whom, and a leg
                # you cannot identify is one you cannot check.
                f"{leg.get('label') or leg.get('team') or leg['ticker']}",
                f"{leg.get('event_title') or ''}\n"
                f"{leg.get('fair_percent_display')} by consensus",
                inline=False,
            )
            for leg in legs
        ]

        default_stake = next(
            (row for row in card.get("at_stakes") or [] if row.get("is_default")),
            None,
        )
        if joint.get("conservative_percent_display"):
            fields.append(
                _field("All legs hit", joint["conservative_percent_display"])
            )
        if joint.get("method_range_display"):
            # The band, never without the headline. Four devig methods disagree
            # by 1-2 points and that spread is wider than the fee advantage this
            # project went looking for -- a single number hides exactly that.
            fields.append(
                _field("Across four methods", joint["method_range_display"])
            )
        if joint.get("fair_cost_display"):
            fields.append(_field("Fair cost", joint["fair_cost_display"]))
        if default_stake:
            fields.append(
                _field(
                    f"At {default_stake['stake_display']}",
                    f"{default_stake['contracts_display']} contracts, "
                    f"{default_stake['payout_display']} if it lands",
                    inline=False,
                )
            )

        description = notes.get("chance", "")
        if joint.get("correlation_note"):
            description = f"{description}\n\n{joint['correlation_note']}"

        return await self._post(
            {
                "title": f"{card.get('title')} — {len(legs)} legs",
                "description": description,
                "url": f"{self.config.cockpit_base_url}/parlays",
                "color": COLOUR_PARLAY,
                "fields": fields,
                "footer": {
                    "text": "\n".join(
                        note for note in (
                            notes.get("fair_value"),
                            notes.get("enter_only"),
                            notes.get("fee"),
                        ) if note
                    )
                },
            }
        )

    async def hedge_lock(self, position: dict, *, notes: dict) -> bool:
        """A hedge that locks a known amount on a ticket Joe holds (ADR 0074).

        **This is the only alert in the product that names a dollar figure it
        stands behind**, and it can because the figure is not a forecast: with
        one leg live and every other already won, buying `n` contracts of the
        other side has a known answer in both branches. Two observed numbers
        and some algebra.

        **Every string arrives pre-rendered**, exactly as `parlay_card` does
        and for its reason: the screen and the embed must not be able to
        disagree by a rounding step, which they would within a week if this
        formatted its own floats.

        **It says what is available and never "hedge now".** ADR 0072 Decision
        1: alert text may contain only nouns traceable to a field the check
        actually read. This check read a price, a depth and a payout. It did
        not read the future, so it does not mention it -- and the
        `not_advice` caveat travels in the footer saying so.

        **A de-risk never reaches this method.** Hedging one of several live
        legs locks nothing, and a phone that buzzes for a number the tool
        cannot stand behind is a phone nobody leaves un-muted. Those stay on
        the screen; `Alerter.hedge_locks` is what enforces it.

        **No button, and the link goes to the cockpit.** Same ruling as every
        other embed here -- and in this case the hedge cannot be placed from
        the cockpit either (the manual door is capped at one contract), so the
        screen names the size and Kalshi takes the order.
        """
        if not self.config:
            return False
        block = position.get("hedge") or {}
        rung = block.get("best_available")
        if block.get("kind") != "lock" or not block.get("guaranteed") or not rung:
            # Nothing to say. Guarded here as well as in the policy because a
            # transport that renders an unlocked "lock" is one that will
            # eventually be called by something that forgot to check.
            return False

        fields = [
            _field(
                "Locks",
                f"{block['guaranteed_display']} whichever way it goes",
                inline=False,
            ),
            _field(
                "Buy",
                f"{rung['contracts']} x {block.get('side', '').upper()} "
                f"at {block.get('ask_display')}",
                inline=False,
            ),
            _field("Costs", rung["cost_display"]),
            _field("Ticket", f"{position['stake_display']} -> "
                             f"{position['return_display']}"),
        ]
        live = [leg for leg in position.get("legs") or []
                if leg.get("outcome") == "pending"]
        if live:
            fields.append(
                _field(
                    "Leg still live",
                    f"{live[0].get('label')} — {live[0].get('chance_display')} "
                    "by the venue's own bid",
                    inline=False,
                )
            )

        return await self._post(
            {
                "title": f"Hedge available — {position.get('label')}",
                "description": (
                    "Every other leg has won. Buying the other side of the "
                    "last one now has a known answer in both branches."
                ),
                "url": f"{self.config.cockpit_base_url}/hedge",
                # Deliberately NOT the palette's opportunity green. Green is
                # "we found something"; this is "you already have something,
                # and here is what it is worth to close it".
                "color": COLOUR_PARLAY,
                "fields": fields,
                "footer": {
                    "text": "\n".join(
                        note for note in (
                            notes.get("upper_bound"),
                            notes.get("not_advice"),
                            notes.get("no_button"),
                        ) if note
                    )
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
        scored_actionable: int,
        required: int,
        suppression_counts: dict[str, int],
    ) -> bool:
        if not self.config:
            return False

        top = sorted(suppression_counts.items(), key=lambda kv: -kv[1])[:4]
        breakdown = "\n".join(f"`{name}` × {n}" for name, n in top) or "none"

        # The floor counts *games the strategy would have bet*. The pooled count
        # beside it is every scored game including the ones it refused, and the
        # first live digest reported that pooled figure under a label reading
        # "Scored on CLV" — which a reader takes as progress toward arming real
        # money. Both numbers, with the gap named, so a large pooled count
        # cannot be read as evidence the strategy has produced any.
        if scored_actionable == scored:
            clv_line = f"{scored} / {required}"
        else:
            clv_line = (
                f"**{scored_actionable}** / {required} actionable\n"
                f"({scored} scored in total — the rest are games this strategy "
                f"refused or had no edge on, so they say nothing about it)"
            )

        return await self._post(
            {
                "title": "Daily summary",
                "color": COLOUR_DIGEST,
                "fields": [
                    _field("Surfaced", str(surfaced)),
                    _field("Suppressed", str(suppressed)),
                    _field("No edge", str(no_edge)),
                    _field("Scored on CLV", clv_line, inline=False),
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
