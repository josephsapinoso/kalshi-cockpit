"""The derisk push: a ticket with several legs live, whose weakest leg is below
35% by the venue's own bid, reaches the phone naming the full and half hedge.

ADR 0078 Amendment 3 (Joe, 2026-10-18). What these tests establish: the key
fires only for a priced derisk with at least two pending legs whose hedged leg
is readable, strictly below 35% and in play (an unknown kickoff counts as in
play); it is once per leg, ever, and a different leg crossing is said again;
it has its own daily ceiling that only a delivered push spends and that no
other push shares; the embed names side, size, price, cost, the if-it-loses
figure and the worst case for the full and the half hedge, says when a size
is beyond the balance or the book, and never uses a lock word or a timing
word; and the real payload carries the `full`/`half` rungs and the raw
`bid_probability` the trigger reads.

What they do not establish: that hedging is worth doing at 35% or at any
other line, or that the price will not move before Joe reads the push.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from backend import hedge, hedge_watch
from backend.notify.alerts import (
    DERISK_KIND,
    DERISK_TRIGGER_PROBABILITY,
    MAX_DERISK_PUSHES_PER_DAY,
    Alerter,
    derisk_key,
)
from backend.notify.discord import DiscordConfig, DiscordNotifier
from backend.store import db

NOW_MS = 1_700_000_000_000
DAY_MS = NOW_MS - 3_600_000
CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"
DISCORD_CHANNEL = "555555555"
DISCORD_API = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL}/messages"

#: The rendered-copy words the lock and position-state embeds already refuse
#: (`tests/test_hedge_alerts.py`), restated so this file stands alone.
ALWAYS_FORBIDDEN = (
    "now", "consider", "warning", "alert", "at risk", "trouble",
    "still available", "hedge now", "collapsing",
)
MANY_LIVE_FORBIDDEN = ("guaranteed", "locked", "lock")


def rung(contracts, *, cost="$81.12", loses="$13.88", worst="-$86.12",
         fillable=True, affordable=True):
    return {
        "contracts": contracts,
        "cost_display": cost,
        "fee_display": "$1.12",
        "if_leg_wins_display": "still live",
        "if_leg_loses_display": loses,
        "floor_display": worst,
        "floor_is_a_gain": False,
        "fillable": fillable,
        "affordable": affordable,
    }


def leg(lid, *, label="Cincinnati to win", probability=0.20, chance="20%",
        outcome="pending", commence_ms=NOW_MS - 60_000, is_hedge_leg=False):
    return {
        "id": lid,
        "label": label,
        "outcome": outcome,
        "chance_display": chance,
        "bid_probability": probability,
        "commence_ms": commence_ms,
        "is_hedge_leg": is_hedge_leg,
    }


def position(*, pid=7, probability=0.20, chance="20%", commence_ms=NOW_MS - 60_000,
             hedge_leg_id=11, kind="derisk", refusal=None, full=None, half=None,
             legs=None, bankroll_known=True, pending_legs=None):
    """A serialised derisk ticket, cut to what the push reads."""
    if legs is None:
        legs = [
            leg(11, probability=probability, chance=chance,
                commence_ms=commence_ms, is_hedge_leg=hedge_leg_id == 11),
            leg(12, label="Los Angeles to win", probability=0.60, chance="60%",
                is_hedge_leg=hedge_leg_id == 12),
            leg(13, label="Boston to win", outcome="won", probability=None,
                chance="--"),
        ]
    block = {
        "refusal": refusal,
        "kind": kind,
        "ticker": CIN,
        "side": "no",
        "ask_display": "80c",
        "depth_at_ask": 500.0,
        "ladder": [],
        "live_legs": 2,
        "chance_display": "12%",
        "full": full if full is not None else rung(100),
        "half": half if half is not None else rung(50, cost="$40.56",
                                                   loses="$4.44",
                                                   worst="-$45.56"),
    }
    return {
        "id": pid,
        "label": "Saturday six",
        "stake_display": "$5.00",
        "return_display": "$100.00",
        "bankroll_known": bankroll_known,
        "pending_legs": (
            pending_legs if pending_legs is not None
            else sum(1 for x in legs if x["outcome"] == "pending")
        ),
        "legs": legs,
        "hedge": block,
    }


def screen(*positions):
    return {"as_of_ms": NOW_MS, "positions": list(positions),
            "notes": dict(hedge.NOTES)}


class Notifier:
    enabled = True

    def __init__(self, delivers=True):
        self.delivers = delivers
        self.derisk_sent: list[dict] = []

    async def hedge_lock(self, position, *, notes):
        return self.delivers

    async def position_state(self, position, *, notes, as_of_ms):
        return self.delivers

    async def hedge_derisk(self, position, *, notes):
        self.derisk_sent.append(position)
        return self.delivers


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


@pytest.fixture()
def discord_notifier():
    return DiscordNotifier(
        DiscordConfig(bot_token="t", channel_id=DISCORD_CHANNEL,
                      cockpit_base_url="https://cockpit.example"),
        client=httpx.AsyncClient(timeout=5.0),
    )


class TestTheDeriskKey:
    def test_a_weak_leg_in_play_is_keyed_on_the_position_and_the_leg(self):
        assert derisk_key(position(), now_ms=NOW_MS) == "hedge_derisk:7:11"

    def test_the_trigger_is_joes_35_percent(self):
        assert DERISK_TRIGGER_PROBABILITY == 0.35

    def test_exactly_35_percent_does_not_fire(self):
        assert derisk_key(position(probability=0.35), now_ms=NOW_MS) is None

    def test_just_below_35_percent_fires(self):
        assert derisk_key(position(probability=0.349), now_ms=NOW_MS) is not None

    def test_an_unreadable_bid_never_fires(self):
        assert derisk_key(position(probability=None), now_ms=NOW_MS) is None

    def test_a_leg_whose_game_has_not_started_does_not_fire(self):
        assert derisk_key(position(commence_ms=NOW_MS + 1), now_ms=NOW_MS) is None

    def test_an_unknown_kickoff_counts_as_in_play(self):
        assert derisk_key(position(commence_ms=None), now_ms=NOW_MS) is not None

    def test_a_lock_is_not_a_derisk(self):
        assert derisk_key(position(kind="lock"), now_ms=NOW_MS) is None

    def test_a_refused_hedge_has_nothing_to_name(self):
        refusal = {"reason": "stale_quote", "detail": "old"}
        assert derisk_key(position(refusal=refusal), now_ms=NOW_MS) is None

    def test_one_pending_leg_is_never_a_derisk(self):
        assert derisk_key(position(pending_legs=1), now_ms=NOW_MS) is None

    def test_no_full_rung_has_nothing_to_name(self):
        p = position()
        p["hedge"]["full"] = None
        assert derisk_key(p, now_ms=NOW_MS) is None

    def test_a_different_weakest_leg_gets_a_different_key(self):
        p = position(hedge_leg_id=12)
        p["legs"][1]["bid_probability"] = 0.10
        assert derisk_key(p, now_ms=NOW_MS) == "hedge_derisk:7:12"


class TestTheDeriskPushReachesThePhone:
    async def test_it_fires_once_across_four_cycles(self, conn):
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        for _ in range(4):
            await alerter.hedge_derisks(
                screen(position()), now_ms=NOW_MS, day_start_ms=DAY_MS
            )
        assert len(notifier.derisk_sent) == 1

    async def test_a_second_leg_crossing_is_said_again(self, conn):
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        await alerter.hedge_derisks(
            screen(position()), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        other = position(hedge_leg_id=12)
        other["legs"][1]["bid_probability"] = 0.10
        result = await alerter.hedge_derisks(
            screen(other), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        assert result.sent == ("hedge_derisk:7:12",)
        assert len(notifier.derisk_sent) == 2

    async def test_a_leg_above_the_line_is_neither_sent_nor_skipped(self, conn):
        notifier = Notifier()
        result = await Alerter(conn, notifier).hedge_derisks(
            screen(position(probability=0.50)), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        assert result.sent == () and result.skipped == ()
        assert notifier.derisk_sent == []

    async def test_the_ceiling_binds_at_four_delivered(self, conn):
        notifier = Notifier()
        tickets = [position(pid=pid) for pid in range(1, 7)]
        result = await Alerter(conn, notifier).hedge_derisks(
            screen(*tickets), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        assert MAX_DERISK_PUSHES_PER_DAY == 4
        assert len(result.sent) == 4
        assert len(result.skipped) == 2

    async def test_an_undelivered_push_does_not_spend_the_ceiling(self, conn):
        failing = Alerter(conn, Notifier(delivers=False))
        tickets = [position(pid=pid) for pid in range(1, 5)]
        result = await failing.hedge_derisks(
            screen(*tickets), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        assert len(result.failed) == 4
        working = Notifier()
        later = [position(pid=pid) for pid in range(5, 9)]
        result = await Alerter(conn, working).hedge_derisks(
            screen(*later), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        assert len(result.sent) == 4

    async def test_it_shares_no_ceiling_with_the_other_hedge_pushes(self, conn):
        for i, kind in enumerate(("hedge_lock", "position_state") * 4):
            conn.execute(
                "INSERT INTO notifications (kind, key, sent_ms, delivered) "
                "VALUES (?, ?, ?, 1)",
                (kind, f"{kind}:x:{i}", NOW_MS),
            )
        conn.commit()
        result = await Alerter(conn, Notifier()).hedge_derisks(
            screen(position()), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        assert result.sent == ("hedge_derisk:7:11",)

    async def test_the_row_is_kept_under_its_own_kind(self, conn):
        await Alerter(conn, Notifier()).hedge_derisks(
            screen(position()), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        kinds = [r[0] for r in conn.execute("SELECT kind FROM notifications")]
        assert kinds == [DERISK_KIND]

    async def test_a_notifier_that_is_off_says_nothing(self, conn):
        class Off(Notifier):
            enabled = False

        notifier = Off()
        result = await Alerter(conn, notifier).hedge_derisks(
            screen(position()), now_ms=NOW_MS, day_start_ms=DAY_MS
        )
        assert result.sent == () and notifier.derisk_sent == []


def _embed(route):
    return json.loads(route.calls.last.request.read())["embeds"][0]


def _rendered_text(embed):
    """Title, description and fields, lower-cased. The footer is `hedge.NOTES`
    verbatim and is excluded, as `tests/test_hedge_alerts.py` does."""
    parts = [embed.get("title", ""), embed.get("description", "")]
    for field in embed.get("fields", []):
        parts += [field.get("name", ""), field.get("value", "")]
    return " ".join(parts).lower()


class TestTheHedgeAvailableDeriskEmbed:
    @respx.mock
    async def test_it_names_the_bet_for_the_full_and_the_half_hedge(
        self, discord_notifier
    ):
        route = respx.post(DISCORD_API).mock(return_value=httpx.Response(200, json={}))
        async with discord_notifier as n:
            assert await n.hedge_derisk(position(), notes=dict(hedge.NOTES))
        embed = _embed(route)
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert embed["title"] == "Hedge available — Saturday six"
        assert "Cincinnati to win is at 20%" in embed["description"]
        assert "2 of 3 legs are still live" in embed["description"]
        assert fields["Full hedge"] == (
            "Buy 100 × NO at 80c, costs $81.12. If this leg loses: $13.88. "
            "Worst case: -$86.12."
        )
        assert fields["Half hedge"].startswith("Buy 50 × NO at 80c, costs $40.56.")
        assert fields["Ticket"] == "$5.00 → $100.00"
        assert embed["url"] == "https://cockpit.example/hedge"

    @respx.mock
    async def test_the_half_is_omitted_when_there_is_none(self, discord_notifier):
        route = respx.post(DISCORD_API).mock(return_value=httpx.Response(200, json={}))
        p = position()
        p["hedge"]["half"] = None
        async with discord_notifier as n:
            await n.hedge_derisk(p, notes=dict(hedge.NOTES))
        names = [f["name"] for f in _embed(route)["fields"]]
        assert "Half hedge" not in names and "Full hedge" in names

    @respx.mock
    async def test_it_says_when_a_size_is_beyond_the_balance_or_the_book(
        self, discord_notifier
    ):
        route = respx.post(DISCORD_API).mock(return_value=httpx.Response(200, json={}))
        p = position(full=rung(100, fillable=False, affordable=False))
        async with discord_notifier as n:
            await n.hedge_derisk(p, notes=dict(hedge.NOTES))
        full = {f["name"]: f["value"] for f in _embed(route)["fields"]}["Full hedge"]
        assert "more than the book holds at this price" in full
        assert "beyond your balance" in full

    @respx.mock
    async def test_an_unread_balance_is_said_as_unread(self, discord_notifier):
        route = respx.post(DISCORD_API).mock(return_value=httpx.Response(200, json={}))
        p = position(bankroll_known=False, full=rung(100, affordable=False))
        async with discord_notifier as n:
            await n.hedge_derisk(p, notes=dict(hedge.NOTES))
        full = {f["name"]: f["value"] for f in _embed(route)["fields"]}["Full hedge"]
        assert "your balance could not be read" in full
        assert "beyond your balance" not in full

    @respx.mock
    async def test_no_lock_word_and_no_timing_word(self, discord_notifier):
        route = respx.post(DISCORD_API).mock(return_value=httpx.Response(200, json={}))
        async with discord_notifier as n:
            await n.hedge_derisk(
                position(full=rung(100, fillable=False, affordable=False)),
                notes=dict(hedge.NOTES),
            )
        text = _rendered_text(_embed(route))
        for word in ALWAYS_FORBIDDEN + MANY_LIVE_FORBIDDEN:
            assert word not in text, word

    @respx.mock
    async def test_a_lock_block_never_renders_here(self, discord_notifier):
        route = respx.post(DISCORD_API).mock(return_value=httpx.Response(200, json={}))
        async with discord_notifier as n:
            assert not await n.hedge_derisk(
                position(kind="lock"), notes=dict(hedge.NOTES)
            )
        assert not route.called


def _record(conn, *, commence_ms=NOW_MS - 60_000):
    return hedge.record_position(
        conn,
        now_ms=NOW_MS,
        source="sportsbook",
        label="Saturday six",
        stake_tenths=5_000,
        return_tenths=100_000,
        legs=[
            {"ticker": CIN, "side": "yes", "label": "Cincinnati to win",
             "commence_ms": commence_ms},
            {"ticker": LAD, "side": "yes", "label": "Los Angeles to win",
             "commence_ms": commence_ms},
        ],
    )


def _book(ticker, *, yes_bid):
    return hedge.MarketBook(
        ticker=ticker, yes_bid_tenths=yes_bid, no_bid_tenths=1000 - yes_bid - 40,
        yes_ask_size=400.0, no_ask_size=400.0, status="active", observed_ms=NOW_MS,
    )


class TestTheRealPayloadCarriesWhatThePushReads:
    def _payload(self, conn, books):
        position_id = _record(conn)
        row = next(r for r in hedge.open_positions(conn) if int(r["id"]) == position_id)
        legs = hedge.legs_for(conn, position_id)
        assessment = hedge.assess(
            row, legs, books, now_ms=NOW_MS, max_quote_age_ms=30_000,
            spendable_tenths=10_000_000,
        )
        return hedge.serialise_position(row, legs, books, assessment, now_ms=NOW_MS)

    def test_the_derisk_block_names_the_full_and_half_rungs_off_the_ladder(
        self, conn
    ):
        payload = self._payload(
            conn, {CIN: _book(CIN, yes_bid=200), LAD: _book(LAD, yes_bid=600)}
        )
        block = payload["hedge"]
        assert block["kind"] == hedge.STATE_DERISK
        # $100 return: the full hedge is 100 contracts, the half 50.
        assert block["full"]["contracts"] == 100
        assert block["half"]["contracts"] == 50
        assert block["full"] in block["ladder"]
        assert block["half"] in block["ladder"]

    def test_each_leg_carries_the_raw_bid_its_percentage_is_rendered_from(
        self, conn
    ):
        payload = self._payload(
            conn, {CIN: _book(CIN, yes_bid=200), LAD: _book(LAD, yes_bid=600)}
        )
        by_label = {x["label"]: x for x in payload["legs"]}
        assert by_label["Cincinnati to win"]["bid_probability"] == pytest.approx(0.20)
        assert by_label["Los Angeles to win"]["bid_probability"] == pytest.approx(0.60)

    def test_the_real_payload_fires_the_key_end_to_end(self, conn):
        payload = self._payload(
            conn, {CIN: _book(CIN, yes_bid=200), LAD: _book(LAD, yes_bid=600)}
        )
        hedged = next(x for x in payload["legs"] if x["is_hedge_leg"])
        assert hedged["label"] == "Cincinnati to win"
        assert derisk_key(payload, now_ms=NOW_MS) == (
            f"hedge_derisk:{payload['id']}:{hedged['id']}"
        )


class TestTheWatcherCarriesTheDeriskPush:
    async def test_watch_once_returns_the_derisk_counts_under_their_own_prefix(
        self, conn
    ):
        _record(conn)

        async def fetch(ticker, *, observed_ms):
            raise RuntimeError("no venue in this test")

        summary = await hedge_watch.watch_once(
            conn, Alerter(conn, Notifier()), now_ms=NOW_MS,
            max_quote_age_ms=30_000, fetch_quote=fetch,
        )
        for key in ("derisk_alerts_sent", "derisk_alerts_failed",
                    "derisk_alerts_deduped"):
            assert key in summary, key
