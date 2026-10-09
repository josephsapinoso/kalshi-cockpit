"""The last-leg push (#329): every leg but one has won and the last has not started.

What these tests establish: the push fires once, with the book's bid and the
last leg's Kalshi price, for a ticket with 4 legs won and 1 pending whose
kickoff is ahead; it does not fire with two legs pending, with a lost or void
leg, with a started last game (the existing in-play path owns that) or with an
unrecorded kickoff; the sentence states numbers and "about" and contains none
of the refused words; an empty, unreadable or unwired public book is not
collapsed into one another; and `hedge_watch` / the alerter never reach the
makers (no RFQ module, no sell-quote or accept call) -- walked in the source,
not asserted in prose.

What they do not establish: that the real combination-book reader is handed to
the watcher in production (`scripts/run_loop.py` must pass it; this lane does
not own that file), or that the figure is worth acting on.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

from backend import hedge, hedge_watch
from backend.notify import alerts as alerts_module
from backend.notify.alerts import LAST_LEG_KIND, Alerter, last_leg_sentence
from backend.notify.discord import DiscordConfig, DiscordNotifier
from backend.store import db

ROOT = Path(__file__).resolve().parent.parent
NOW_MS = 1_700_000_000_000
COMBO = "KXMVE-LASTLEG-TEST"
LAST = "KXMLBGAME-26AUG26LADSD-LAD"
DISCORD_CHANNEL = "555555555"
DISCORD_API = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL}/messages"
REFUSED = ("cash out", "cashout", "lock", "should", "ceiling", "floor",
           "conservative", "at least")


class Notifier:
    enabled = True

    def __init__(self):
        self.texts: list[str] = []

    async def last_leg_watch(self, position, text):
        self.texts.append(text)
        return True


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def make_ticket(conn, *, outcomes, last_commence=NOW_MS + 3_600_000,
                combo_ticker=COMBO):
    legs = []
    for i, outcome in enumerate(outcomes):
        is_last = i == len(outcomes) - 1
        legs.append({
            "ticker": LAST if is_last else f"KXMLBGAME-26AUG26T{i}-T{i}",
            "side": "yes",
            "label": f"Team {i} to win",
            "commence_ms": last_commence if is_last else NOW_MS - 86_400_000,
        })
    pid = hedge.record_position(
        conn, now_ms=NOW_MS, source="kalshi_combo", label="Five legs",
        stake_tenths=5_000, return_tenths=100_000, legs=legs,
        combo_ticker=combo_ticker,
    )
    for row, outcome in zip(hedge.legs_for(conn, pid), outcomes):
        if outcome != "pending":
            hedge.resolve_leg(conn, leg_id=row["id"], outcome=outcome,
                              now_ms=NOW_MS - 1, source="manual")
    return pid


def book_reader(yes_levels):
    async def _read(ticker):
        return {"yes_dollars": yes_levels, "no_dollars": []}
    return _read


async def fetch_quote(ticker, *, observed_ms):
    market = SimpleNamespace(yes_bid_tenths=915, no_bid_tenths=70,
                             yes_ask_size=10.0, no_ask_size=10.0)
    return SimpleNamespace(ticker=ticker, market=market, status="active",
                           observed_ms=observed_ms)


async def run(conn, notifier, *, reader=None, now_ms=NOW_MS):
    return await hedge_watch.watch_last_leg_once(
        conn, Alerter(conn, notifier), now_ms=now_ms, max_quote_age_ms=30_000,
        fetch_quote=fetch_quote, read_combo_book=reader,
    )


class _Plain(Alerter):
    """An Alerter whose in-play pushes are inert, so the test sees only ours."""

    async def hedge_locks(self, *a, **k):
        return alerts_module.AlertResult()

    async def position_states(self, *a, **k):
        return alerts_module.AlertResult()


def notification_count(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE kind = ?", (LAST_LEG_KIND,)
    ).fetchone()[0]


WON4 = ["won", "won", "won", "won", "pending"]


class TestItFiresOnTheLastLegState:
    async def test_four_won_and_one_unstarted_fires_once(self, conn):
        make_ticket(conn, outcomes=WON4)
        notifier = Notifier()
        reader = book_reader([["0.0510", "38709.00"]])

        first = await run(conn, notifier, reader=reader)
        second = await run(conn, notifier, reader=reader)

        assert len(first["alerts_sent"]) == 1
        assert second["alerts_sent"] == [] and len(second["alerts_deduped"]) == 1
        assert notification_count(conn) == 1
        assert notifier.texts == [
            "4 of 5 legs won. The book bids 5.1c a contract for this card now. "
            "Holding is worth about 91.5c a contract at the last leg's Kalshi "
            "price. Makers on tap."
        ]

    async def test_an_empty_book_says_no_public_bid(self, conn):
        make_ticket(conn, outcomes=WON4)
        notifier = Notifier()
        await run(conn, notifier, reader=book_reader([]))
        assert "No public bid right now; makers on tap." in notifier.texts[0]
        assert "The book bids" not in notifier.texts[0]

    async def test_an_unreadable_book_is_not_called_empty(self, conn):
        make_ticket(conn, outcomes=WON4)
        notifier = Notifier()

        async def broken(ticker):
            raise RuntimeError("403")

        await run(conn, notifier, reader=broken)
        assert "could not be read" in notifier.texts[0]
        assert "No public bid" not in notifier.texts[0]

    async def test_a_book_that_was_never_read_says_nothing(self, conn):
        make_ticket(conn, outcomes=WON4)
        notifier = Notifier()
        result = await run(conn, notifier, reader=None)
        assert result["alerts_sent"] == [] and notifier.texts == []
        assert notification_count(conn) == 0

    async def test_the_sentence_carries_none_of_the_refused_words(self, conn):
        make_ticket(conn, outcomes=WON4)
        for levels in ([["0.0510", "9.00"]], []):
            notifier = Notifier()
            conn.execute("DELETE FROM notifications")
            conn.commit()
            await run(conn, notifier, reader=book_reader(levels))
            text = notifier.texts[0].lower()
            assert "about" in text
            for word in REFUSED:
                assert word not in text, word

    async def test_it_does_not_say_what_he_paid(self, conn):
        make_ticket(conn, outcomes=WON4)
        notifier = Notifier()
        await run(conn, notifier, reader=book_reader([["0.0510", "9.00"]]))
        assert "$" not in notifier.texts[0] and "paid" not in notifier.texts[0]


class TestItStaysQuietOtherwise:
    async def test_two_pending_legs_do_not_fire(self, conn):
        make_ticket(conn, outcomes=["won", "won", "won", "pending", "pending"])
        notifier = Notifier()
        result = await run(conn, notifier, reader=book_reader([["0.0510", "9"]]))
        assert result["alerts_sent"] == [] and notifier.texts == []
        assert not hedge_watch.last_leg_waiting(conn, now_ms=NOW_MS)

    async def test_a_started_last_game_is_left_to_the_in_play_path(self, conn):
        make_ticket(conn, outcomes=WON4, last_commence=NOW_MS - 1)
        notifier = Notifier()
        result = await run(conn, notifier, reader=book_reader([["0.0510", "9"]]))
        assert result["alerts_sent"] == [] and notifier.texts == []
        assert not hedge_watch.last_leg_waiting(conn, now_ms=NOW_MS)
        assert hedge_watch.anything_in_progress(conn, now_ms=NOW_MS)

    async def test_an_unrecorded_kickoff_is_not_called_unstarted(self, conn):
        make_ticket(conn, outcomes=WON4, last_commence=None)
        notifier = Notifier()
        result = await run(conn, notifier, reader=book_reader([["0.0510", "9"]]))
        assert result["alerts_sent"] == [] and notifier.texts == []

    async def test_a_lost_leg_does_not_fire(self, conn):
        make_ticket(conn, outcomes=["won", "won", "lost", "won", "pending"])
        notifier = Notifier()
        result = await run(conn, notifier, reader=book_reader([["0.0510", "9"]]))
        assert result["alerts_sent"] == [] and notifier.texts == []

    async def test_a_void_leg_does_not_fire(self, conn):
        make_ticket(conn, outcomes=["won", "won", "void", "won", "pending"])
        notifier = Notifier()
        result = await run(conn, notifier, reader=book_reader([["0.0510", "9"]]))
        assert result["alerts_sent"] == [] and notifier.texts == []

    async def test_a_closed_ticket_does_not_fire(self, conn):
        pid = make_ticket(conn, outcomes=WON4)
        hedge.close_position(conn, position_id=pid, now_ms=NOW_MS,
                             status="settled", source="manual")
        notifier = Notifier()
        result = await run(conn, notifier, reader=book_reader([["0.0510", "9"]]))
        assert result["alerts_sent"] == [] and notifier.texts == []


class TestTheLoopReachesIt:
    async def test_the_loop_fires_it_while_nothing_is_in_play(self, tmp_path):
        path = tmp_path / "cockpit.db"
        setup = db.init_db(path)
        try:
            make_ticket(setup, outcomes=WON4)
        finally:
            setup.close()
        notifier = Notifier()
        slept: list[float] = []

        async def sleep(seconds):
            slept.append(seconds)

        await hedge_watch.watch_hedges_forever(
            path, lambda c: Alerter(c, notifier), fetch_quote=fetch_quote,
            read_combo_book=book_reader([["0.0510", "9"]]),
            max_quote_age_ms=30_000, sleep=sleep,
            clock=lambda: NOW_MS / 1000, max_cycles=2,
        )
        assert len(notifier.texts) == 1
        assert slept == [hedge_watch.IDLE_INTERVAL_S] * 2

    async def test_it_still_fires_while_another_game_is_in_play(self, tmp_path):
        path = tmp_path / "cockpit.db"
        setup = db.init_db(path)
        try:
            make_ticket(setup, outcomes=WON4)
            # A second ticket whose game is under way keeps the cycle busy.
            hedge.record_position(
                setup, now_ms=NOW_MS, source="sportsbook", label="Live one",
                stake_tenths=5_000, return_tenths=100_000,
                legs=[{"ticker": "KXMLBGAME-26AUG26CINSF-CIN", "side": "yes",
                       "label": "Cincinnati", "commence_ms": NOW_MS - 1}],
            )
            assert hedge_watch.anything_in_progress(setup, now_ms=NOW_MS)
        finally:
            setup.close()
        notifier = Notifier()

        async def sleep(seconds):
            return None

        await hedge_watch.watch_hedges_forever(
            path, lambda c: _Plain(c, notifier), fetch_quote=fetch_quote,
            read_combo_book=book_reader([]), max_quote_age_ms=30_000,
            sleep=sleep, clock=lambda: NOW_MS / 1000, max_cycles=1,
        )
        assert len(notifier.texts) == 1

    async def test_the_sixty_second_cycle_reads_no_combination_book(self, conn):
        make_ticket(conn, outcomes=WON4)
        notifier = Notifier()
        summary = await hedge_watch.watch_once(
            conn, Alerter(conn, notifier), now_ms=NOW_MS,
            max_quote_age_ms=30_000, fetch_quote=fetch_quote,
        )
        assert notifier.texts == [] and "last_leg_alerts_sent" not in summary


class TestTheDiscordPath:
    @respx.mock
    async def test_it_posts_the_sentence_through_the_embed_post(self, conn):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        make_ticket(conn, outcomes=WON4)
        config = DiscordConfig(bot_token="t", channel_id=DISCORD_CHANNEL,
                               cockpit_base_url="https://cockpit.example")
        async with httpx.AsyncClient() as client:
            async with DiscordNotifier(config, client=client) as notifier:
                result = await run(conn, notifier, reader=book_reader([]))
        assert len(result["alerts_sent"]) == 1
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        assert embed["description"].startswith("4 of 5 legs won.")


class TestItNeverAsksTheMakers:
    """Walk the source: no RFQ module, no sell-quote or accept call."""

    BANNED_NAMES = ("rfq", "sell_quote", "sell_back", "accept", "place_order",
                    "manual_orders")

    @staticmethod
    def _names(path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.lower() for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.add((node.module or "").lower())
                found.update(a.name.lower() for a in node.names)
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    found.add(fn.attr.lower())
                elif isinstance(fn, ast.Name):
                    found.add(fn.id.lower())
        return found

    @pytest.mark.parametrize("rel", ["backend/hedge_watch.py",
                                     "backend/notify/alerts.py"])
    def test_no_import_or_call_reaches_the_makers(self, rel):
        names = self._names(ROOT / rel)
        hits = sorted(n for n in names for b in self.BANNED_NAMES if b in n)
        assert hits == []


class TestTheSentenceShape:
    def test_a_ticket_not_in_the_state_has_no_sentence(self):
        position = {"id": 1, "combo_book": {"state": "empty"},
                    "legs": [{"outcome": "won", "commence_ms": 1},
                             {"outcome": "pending", "commence_ms": 2}]}
        assert last_leg_sentence(position, now_ms=3) is None
        assert last_leg_sentence(position, now_ms=1) is not None

    def test_the_module_exports_its_kind(self):
        assert alerts_module.LAST_LEG_KIND == "last_leg_watch"
