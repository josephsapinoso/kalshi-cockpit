"""Parlay cards push to Discord, once per card, in the desk's own words.

The desk's whole product is three cards, and until now they reached Joe only if
he opened a browser. ADR 0071 settles the tool as a personal betting desk whose
job at the moment of a bet is price transparency -- so putting the cards in the
channel he already watches is the product arriving, not a new feature.

Two properties carry the whole thing:

- **The dedupe key IS the change detection.** `notifications.UNIQUE (kind, key)`
  drops a card whose legs have not moved. There is no timestamp comparison and
  no threshold to tune, and it survives the restart an in-memory policy would
  not.
- **Every number is a string the server already rendered.** The embed does no
  arithmetic, so it cannot drift from the screen.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **That Discord accepts the embed.** `_post` is faked here. Only posting to
  the real webhook proves the wire shape, and that is a human action -- the
  same argument `heartbeat.yml`'s `force_alarm` input makes.
- **That a card is worth buying.** No edge is claimed anywhere in this path,
  and none was measured (ADR 0038). `backend/core/ladder.py`'s own docstring is
  the authority.
- **That the ladder builds good cards.** `tests/test_ladder.py` owns that;
  these tests take a built payload as given.
- **Anything about ordering.** Cards go out in ladder order, which is a shape
  (2-3 legs, 4, 6), not a ranking. ADR 0071 SS2.5 forbids ranking by the gap.
"""

from __future__ import annotations

import pytest

from backend.notify.alerts import (
    MAX_PARLAY_PUSHES_PER_DAY, Alerter, parlay_key,
)
from backend.notify.discord import (
    COLOUR_OPPORTUNITY, COLOUR_PARLAY, DiscordConfig, DiscordNotifier,
)
from backend.parlays import NOTES
from backend.store import db

NOW = 1_787_680_800_000
DAY_START = NOW - 3_600_000


def _leg(ticker: str, team: str = "Yankees") -> dict:
    return {
        "ticker": ticker,
        "event_ticker": f"EV-{ticker}",
        "event_title": "Yankees at Red Sox",
        "team": team,
        "label": f"{team} win",
        "league": "baseball_mlb",
        "commence_ms": NOW + 3_600_000,
        "market": "h2h",
        "point": None,
        "fair_percent_display": "64.2%",
    }


def _card(key: str = "safe", tickers=("A", "B", "C")) -> dict:
    return {
        "key": key,
        "title": key.title(),
        "legs": [_leg(t) for t in tickers],
        "not_built_reason": None,
        "joint": {
            "conservative_percent_display": "26.5%",
            "method_range_display": "24.1%–29.8%",
            "fair_cost_display": "26.5c",
            "correlation_note": "Same-night games move together a little.",
        },
        "at_stakes": [
            {
                "stake_cents": 500, "stake_display": "$5.00",
                "contracts_display": "~18.9", "payout_display": "$18.87",
                "is_default": True,
            },
        ],
    }


def _ladder(*cards) -> dict:
    return {"generated_ms": NOW, "cards": list(cards), "excluded": {},
            "notes": dict(NOTES)}


@pytest.fixture()
def conn(tmp_path):
    c = db.init_db(tmp_path / "parlay_alerts.db")
    yield c
    c.close()


class FakeNotifier:
    """Records embeds instead of posting them."""

    enabled = True

    def __init__(self, *, deliver: bool = True):
        self.posted: list[dict] = []
        self._deliver = deliver

    async def parlay_card(self, card, *, notes):
        self.posted.append({"card": card, "notes": notes})
        return self._deliver


class TestTheKeyIsTheCardsIdentity:
    """This is the claim the whole feature rests on."""

    def test_the_same_legs_in_a_different_order_are_the_same_card(self):
        """Mutation observed red: drop `sorted(...)` in `parlay_key`.

        `build_ladder` orders legs by `(-p_conservative, ...)`, so two
        probabilities crossing between passes reorders the same set -- and an
        order-sensitive key would push the same parlay again.
        """
        assert parlay_key(_card(tickers=("A", "B", "C"))) == parlay_key(
            _card(tickers=("C", "A", "B"))
        )

    def test_a_changed_leg_is_a_different_card(self):
        assert parlay_key(_card(tickers=("A", "B", "C"))) != parlay_key(
            _card(tickers=("A", "B", "D"))
        )

    def test_the_same_legs_at_a_different_rung_are_different_cards(self):
        """Mutation observed red: drop `card.get('key')` from the key.

        The same legs as a Safe and as a Middle are different suggestions.
        """
        assert parlay_key(_card("safe", ("A", "B"))) != parlay_key(
            _card("middle", ("A", "B"))
        )

    def test_a_card_with_no_legs_has_no_identity(self):
        """`"safe:"` would make every empty card the same card forever."""
        assert parlay_key({"key": "safe", "legs": []}) is None

    def test_a_leg_missing_its_ticker_does_not_become_an_empty_slot(self):
        key = parlay_key({"key": "safe", "legs": [_leg("A"), {"ticker": None}]})
        assert key == "safe:A"


class TestOneCardIsAnnouncedOnce:
    async def test_a_built_card_is_sent(self, conn):
        notifier = FakeNotifier()
        result = await Alerter(conn, notifier).parlay_cards(
            _ladder(_card()), now_ms=NOW, day_start_ms=DAY_START
        )
        assert result.sent == ("safe",)
        assert len(notifier.posted) == 1

    async def test_the_same_card_on_the_next_pass_is_not_resent(self, conn):
        """Mutation observed red: give `parlay_cards` a key of `str(now_ms)`.

        This is what makes it safe to ask on every pass. Without it a card
        would be pushed every fifteen seconds for as long as its legs held.
        """
        alerter = Alerter(conn, FakeNotifier())
        await alerter.parlay_cards(_ladder(_card()), now_ms=NOW, day_start_ms=DAY_START)
        again = await alerter.parlay_cards(_ladder(_card()), now_ms=NOW + 15_000, day_start_ms=DAY_START)
        assert again.sent == ()
        assert again.skipped == ("safe",)

    async def test_a_price_move_alone_does_not_resend(self, conn):
        """The legs are the card. A re-quote of the same six legs is the same
        suggestion, and a phone that buzzes for a tenth of a cent gets muted."""
        alerter = Alerter(conn, FakeNotifier())
        await alerter.parlay_cards(_ladder(_card()), now_ms=NOW, day_start_ms=DAY_START)
        moved = _card()
        moved["joint"]["conservative_percent_display"] = "27.9%"
        moved["legs"][0]["fair_percent_display"] = "66.0%"
        assert (await alerter.parlay_cards(
            _ladder(moved), now_ms=NOW + 15_000, day_start_ms=DAY_START
        )).sent == ()

    async def test_a_changed_leg_is_announced(self, conn):
        """The material-change trigger, and it needs no separate machinery."""
        alerter = Alerter(conn, FakeNotifier())
        await alerter.parlay_cards(_ladder(_card()), now_ms=NOW, day_start_ms=DAY_START)
        fresh = await alerter.parlay_cards(
            _ladder(_card(tickers=("A", "B", "D"))), now_ms=NOW + 900_000,
            day_start_ms=DAY_START,
        )
        assert fresh.sent == ("safe",)

    async def test_an_unbuilt_card_says_nothing(self, conn):
        """A push saying "nothing tonight" is a notification with no action."""
        notifier = FakeNotifier()
        unbuilt = {
            "key": "lottery", "title": "Lottery", "legs": [],
            "not_built_reason": "needs 6 fresh games and the slate has 2",
            "joint": None, "at_stakes": [],
        }
        result = await Alerter(conn, notifier).parlay_cards(
            _ladder(unbuilt), now_ms=NOW, day_start_ms=DAY_START
        )
        assert result.sent == ()
        assert notifier.posted == []

    async def test_every_rung_gets_its_own_notification(self, conn):
        notifier = FakeNotifier()
        result = await Alerter(conn, notifier).parlay_cards(
            _ladder(
                _card("safe", ("A", "B")),
                _card("middle", ("A", "B", "C", "D")),
            ),
            now_ms=NOW, day_start_ms=DAY_START,
        )
        assert result.sent == ("safe", "middle")

    async def test_a_failed_delivery_is_recorded_as_failed(self, conn):
        result = await Alerter(conn, FakeNotifier(deliver=False)).parlay_cards(
            _ladder(_card()), now_ms=NOW, day_start_ms=DAY_START
        )
        assert result.failed == ("safe",)
        row = conn.execute(
            "SELECT delivered FROM notifications WHERE kind = 'parlay_card'"
        ).fetchone()
        assert row["delivered"] == 0, (
            "'we decided to alert' and 'the alert arrived' are different facts"
        )

    async def test_no_notifier_sends_nothing_and_does_not_raise(self, conn):
        """Alerting is optional infrastructure; the recorder is not."""
        result = await Alerter(conn, None).parlay_cards(
            _ladder(_card()), now_ms=NOW, day_start_ms=DAY_START
        )
        assert result.sent == ()


class TestTheDayHasACeiling:
    """The dedupe key alone is not a ceiling, and this is why.

    `ladder_candidates` takes pre-game fixtures only, so **every kickoff drops
    a game out of the pool**. If that game was in a card, the leg set changes,
    the key changes, and the card is legitimately new by the dedupe rule. On a
    14-fixture MLB night that is up to fourteen correct pushes per rung and a
    phone nobody leaves un-muted.
    """

    async def test_a_night_of_kickoffs_cannot_push_forever(self, conn):
        """Mutation observed red: remove the `MAX_PARLAY_PUSHES_PER_DAY` check.

        Each iteration is a genuinely different leg set, exactly as a game
        starting produces. Without a ceiling every one of them sends.
        """
        alerter = Alerter(conn, FakeNotifier())
        sent = 0
        for n in range(14):
            result = await alerter.parlay_cards(
                _ladder(_card(tickers=(f"G{n}", f"G{n + 1}", f"G{n + 2}"))),
                now_ms=NOW + n * 900_000, day_start_ms=DAY_START,
            )
            sent += len(result.sent)
        assert sent == MAX_PARLAY_PUSHES_PER_DAY

    async def test_the_ceiling_resets_on_the_next_budget_day(self, conn):
        alerter = Alerter(conn, FakeNotifier())
        for n in range(MAX_PARLAY_PUSHES_PER_DAY):
            await alerter.parlay_cards(
                _ladder(_card(tickers=(f"G{n}", "X", "Y"))),
                now_ms=NOW + n * 1000, day_start_ms=DAY_START,
            )
        tomorrow = NOW + 86_400_000
        result = await alerter.parlay_cards(
            _ladder(_card(tickers=("P", "Q", "R"))),
            now_ms=tomorrow, day_start_ms=tomorrow - 3_600_000,
        )
        assert result.sent == ("safe",)

    async def test_an_undelivered_push_does_not_burn_the_ceiling(self, conn):
        """Mutation observed red: drop `delivered = 1` from the count.

        A push Discord rejected did not reach the phone. Charging it against a
        ceiling that exists to protect the phone would let one outage silence
        the rest of the day.
        """
        alerter = Alerter(conn, FakeNotifier(deliver=False))
        for n in range(MAX_PARLAY_PUSHES_PER_DAY + 2):
            await alerter.parlay_cards(
                _ladder(_card(tickers=(f"G{n}", "X", "Y"))),
                now_ms=NOW + n * 1000, day_start_ms=DAY_START,
            )
        assert alerter._parlay_pushes_today(day_start_ms=DAY_START) == 0

    async def test_one_ladder_cannot_all_pass_a_ceiling_with_room_for_one(
        self, conn
    ):
        """Mutation observed red: re-query the count per card instead of
        incrementing `pushed_today` in the loop.

        The count is committed per send, so a re-query would see it -- but only
        if `_send` delivered before the next read. Incrementing locally is what
        makes three rungs share one budget rather than each reading a stale
        figure.
        """
        alerter = Alerter(conn, FakeNotifier())
        for n in range(MAX_PARLAY_PUSHES_PER_DAY - 1):
            await alerter.parlay_cards(
                _ladder(_card(tickers=(f"G{n}", "X", "Y"))),
                now_ms=NOW + n * 1000, day_start_ms=DAY_START,
            )
        result = await alerter.parlay_cards(
            _ladder(
                _card("safe", ("P", "Q")),
                _card("middle", ("P", "Q", "R", "S")),
                _card("lottery", ("P", "Q", "R", "S", "T", "U")),
            ),
            now_ms=NOW + 999_000, day_start_ms=DAY_START,
        )
        assert len(result.sent) == 1, (
            "the ladder spent more of the day's budget than was left"
        )
        assert result.skipped == ("middle", "lottery")


class TestTheEmbedRepeatsTheDeskRatherThanRecomputingIt:
    @staticmethod
    def _notifier():
        posted: list[dict] = []
        n = DiscordNotifier(
            DiscordConfig(
                cockpit_base_url="https://kalshi-cockpit.fly.dev",
                webhook_url="https://discord.com/api/webhooks/x/y",
            )
        )
        n._post = lambda embed: _record(posted, embed)  # type: ignore[method-assign]
        return n, posted

    async def test_the_four_caveats_travel_verbatim(self):
        """Mutation observed red: drop `notes.get("enter_only")` from the footer.

        Two of these are the difference between a number and money: the cost is
        FAIR value and not a quote, and the market is enter-only.
        """
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        embed = posted[0]
        assert NOTES["fair_value"] in embed["footer"]["text"]
        assert NOTES["enter_only"] in embed["footer"]["text"]
        assert NOTES["fee"] in embed["footer"]["text"]
        assert NOTES["chance"] in embed["description"]

    async def test_every_number_on_it_is_a_string_the_payload_carried(self):
        """The no-arithmetic rule. Mutation observed red: render the joint as
        `f"{joint * 100:.1f}%"` from a float instead of reading the display
        string -- the embed and the screen then disagree by a rounding step."""
        notifier, posted = self._notifier()
        card = _card()
        await notifier.parlay_card(card, notes=dict(NOTES))
        rendered = str(posted[0])
        for shown in (
            card["joint"]["conservative_percent_display"],
            card["joint"]["method_range_display"],
            card["joint"]["fair_cost_display"],
            card["at_stakes"][0]["payout_display"],
            card["legs"][0]["fair_percent_display"],
        ):
            assert shown in rendered, f"{shown!r} was recomputed, not repeated"

    async def test_it_carries_no_edge_and_no_recommendation(self):
        """ADR 0038 closed the hunt; ADR 0071 makes the job transparency.

        Asserted over the field NAMES and the title, not over the whole embed:
        `NOTES["chance"]` contains the words "not an edge", which is the
        disclaimer and must survive. A blanket substring ban would delete the
        sentence that does the work -- it caught exactly that when first
        written.
        """
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        embed = posted[0]
        claims = " ".join(
            [embed["title"]] + [f["name"] for f in embed["fields"]]
        ).lower()
        for forbidden in ("edge", "ev", "expected", "recommend", "value bet"):
            assert forbidden not in claims.split(), (
                f"a field is labelled {forbidden!r}; this embed states fair "
                f"value and claims nothing"
            )

    async def test_the_disclaimer_that_it_is_not_an_edge_survives(self):
        """The other half, so the test above cannot be satisfied by deleting
        the sentence rather than by not claiming an edge."""
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        assert "not an edge" in posted[0]["description"]

    async def test_it_is_not_coloured_as_an_opportunity(self):
        """Green is this palette's "we found something", which this is not."""
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        assert posted[0]["color"] == COLOUR_PARLAY
        assert COLOUR_PARLAY != COLOUR_OPPORTUNITY

    async def test_every_leg_is_identifiable(self):
        """A leg you cannot identify is one you cannot check: the side taken
        AND the fixture, because "Yankees" does not say against whom."""
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        rendered = str(posted[0])
        assert "Yankees win" in rendered
        assert "Yankees at Red Sox" in rendered

    async def test_it_links_to_the_cockpit_and_carries_no_button(self):
        """Same ruling as `opportunity`: no tap-to-buy in a chat client."""
        notifier, posted = self._notifier()
        await notifier.parlay_card(_card(), notes=dict(NOTES))
        assert posted[0]["url"] == "https://kalshi-cockpit.fly.dev/parlays"
        assert "components" not in posted[0]

    async def test_an_unbuilt_card_is_refused_at_the_transport_too(self):
        """Belt and braces: `Alerter` filters these, and so does this. Neither
        alone is a guarantee that a "nothing tonight" push cannot happen."""
        notifier, posted = self._notifier()
        sent = await notifier.parlay_card(
            {"key": "lottery", "title": "Lottery", "legs": [],
             "not_built_reason": "needs 6 fresh games", "joint": None,
             "at_stakes": []},
            notes=dict(NOTES),
        )
        assert sent is False
        assert posted == []

    async def test_an_unconfigured_notifier_refuses_rather_than_raising(self):
        assert await DiscordNotifier(None).parlay_card(
            _card(), notes=dict(NOTES)
        ) is False


async def _record(bucket: list, embed: dict) -> bool:
    bucket.append(embed)
    return True


class TestTheLoopAsksOnEveryPass:
    """Source-pinned: `run_loop.main()` has no caller but `__main__`."""

    @staticmethod
    def _source() -> str:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        return (root / "scripts" / "run_loop.py").read_text(encoding="utf-8")

    def test_the_loop_pushes_parlay_cards(self):
        assert "alerter.parlay_cards(" in self._source()

    def test_it_is_not_gated_behind_a_full_pass(self):
        """Mutation observed red: move the call inside `if kind == "full":`.

        The dedupe makes asking on the fast cadence free, and asking only every
        900s would sit on a newly-buildable card for a quarter of an hour.
        """
        source = self._source()
        call = source.index("alerter.parlay_cards(")
        full_gate = source.index('if kind == "full":', call - 3000)
        assert full_gate > call, (
            "the parlay push now sits inside the full-pass branch, so a new "
            "card can wait up to 900s for a notification"
        )

    def test_it_reads_the_same_staleness_limit_the_screen_does(self):
        """A push built on a looser limit than `/api/parlays` would announce a
        card the screen refuses to show."""
        source = self._source()
        block = source[source.index("alerter.parlay_cards("):][:600]
        assert "max_odds_age_ms=staleness.max_odds_age_s * 1000" in block
