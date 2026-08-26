"""The buy controls: where they are mounted, and what they say when they are.

`tests/test_manual_orders.py` drives the route. This file covers the half
that shipped with it and the half that had never shipped at all: the ticket
is now mounted inline on the slate rows, the Picks cards, the parlay legs
and a search result, and `GET /api/manual/search` is the way in to a market
no screen surfaced.

Both halves are here because they fail in opposite directions.
`tasks/lessons.md` records that "a feature and the one path that invokes it
are two deliverables, and only the second one ships" -- so every mount is
asserted by name, on the source, and a component that quietly stops being
rendered shows up here rather than as a screen nobody can bet from. And the
sentences are asserted because on these particular surfaces the words are
load-bearing: a leg-buy that does not say it is not the parlay turns the
card's joint figure into a promise about a bet nobody placed.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing renders.** There is no JS test framework in this repo and none
  is added here (see `tests/test_parlay_screen.py`'s docstring for the
  standing argument). These are source assertions and one driven route; no
  DOM exists, no click happens, and "the control is mounted" means the JSX
  is present, not that it paints.
- **Nothing about the venue.** The search reads `kalshi_markets`, which is
  discovery's mirror; a market missing from it is missing here, and no test
  can tell the difference between "Kalshi does not list it" and "discovery
  has not walked it".
- **Nothing about whether any of this should be bet.** ADR 0038 closed the
  hunt; these are doors, not opinions.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from backend.api.routes import create_app
from backend.config import AppConfig, ManualOrderConfig
from backend.store import db

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"


def source(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The mounts.
# --------------------------------------------------------------------------

#: Every surface that must offer a hand bet, and what it is.
MOUNTS = {
    "components/SlateRow.tsx": "a Picks row",
    "components/LiveBoard.tsx": "a Picks card",
    "app/slate/page.tsx": "a Games row",
    "app/market/[ticker]/page.tsx": "the market screen",
    "components/ParlayCards.tsx": "a parlay leg",
    "components/PriceOnKalshi.tsx": "a priced combination",
    "components/MarketSearch.tsx": "a searched market",
}


class TestTheControlIsActuallyMounted:
    def test_every_surface_renders_the_ticket(self):
        """Mutation observed red: delete any one `<ManualTicket` below."""
        missing = [
            f"{rel} ({what})"
            for rel, what in MOUNTS.items()
            if "<ManualTicket" not in source(rel)
        ]
        assert not missing, (
            f"these surfaces import nothing that can place a bet: {missing}"
        )

    def test_the_picks_card_mounts_outside_the_engine_trigger(self):
        """`TicketTrigger` wraps a whole card in a `<button>`; a ticket
        nested inside one is invalid markup whose inputs swallow their own
        clicks. Pinned on ordering, because the bug is silent."""
        board = source("components/LiveBoard.tsx")
        trigger_close = board.index("</TicketTrigger>")
        assert board.index("<ManualTicket") > trigger_close, (
            "the hand-bet ticket is inside TicketTrigger's button"
        )

    def test_the_search_is_reachable_from_both_reading_screens(self):
        for rel in ("app/slate/page.tsx", "app/market/[ticker]/page.tsx"):
            assert "<MarketSearch" in source(rel), rel


class TestTheWordsThatCarryTheClaim:
    def test_the_leg_buy_says_it_is_not_the_parlay_before_it_opens(self):
        """The card shows a joint fair value; three legs bought separately
        are not that bet.

        Asserted on the `<summary>` specifically, and the first draft of
        this test is why: sliced over the whole component it stayed GREEN
        with the summary sentence deleted, because the same claim appears
        again inside the ticket's `note` -- which a reader sees only after
        opening a control they opened without being told. The visible line
        is the one that has to carry the claim.

        Mutation observed red: drop the clause from the summary."""
        block = source("components/ParlayCards.tsx")
        block = block[block.index("function LegBuys"):]
        summary = block[block.index("<summary"):block.index("</summary>")]
        assert "not this parlay" in summary, (
            "the leg-buy control does not distinguish itself from the "
            "combination the card prices, before it is opened"
        )

    def test_the_combo_buy_names_the_missing_exit(self):
        combo = source("components/PriceOnKalshi.tsx")
        assert "<ManualTicket" in combo
        note = combo[combo.index("<ManualTicket"):]
        note = note[: note.index("/>")]
        assert "exit" in note, (
            "the combination buy does not say the book has no way out"
        )

    def test_the_ticket_tells_the_truth_about_the_mask_on_both_surfaces(self):
        """ADR 0065's mask holds only where the surface hides the ask. The
        ticket must carry BOTH wordings, and the estimate step must still
        show no price under either. Mutation observed red: collapse the
        ternary to one branch."""
        ticket = source("components/ManualTicket.tsx")
        assert "priceAlreadyVisible" in ticket
        assert "already on this screen" in ticket, (
            "no wording exists for a surface that shows the ask"
        )
        assert "wearing your handwriting" in ticket, (
            "the masked wording was lost"
        )

    def test_the_estimate_step_still_shows_no_price_on_either_surface(self):
        """The pin `tests/test_manual_orders.py` holds, re-asserted here
        because the surface fork is a new way to break it."""
        ticket = source("components/ManualTicket.tsx")
        start = ticket.index('{phase.name === "estimate"')
        block = ticket[start:ticket.index("{phase.name ===", start + 30)]
        assert "ask_display" not in block and "ask_tenths" not in block

    def test_the_search_result_list_carries_no_price_field(self):
        """The masking survives the search screen only because the payload
        has no quote in it. Pinned on the client too, so a future field
        cannot be rendered here without this going red."""
        search = source("components/MarketSearch.tsx")
        for banned in ("ask_display", "ask_tenths", "yes_bid", "last_price"):
            assert banned not in search, banned


class TestTheComboAcknowledgementGatesTheConfirm:
    def test_the_confirm_requires_it_on_a_combination(self):
        """Mutation observed red: drop the `comboOk` clause from
        `canConfirm`. The server refuses regardless -- this pins the client
        half so the screen cannot offer a confirm the route will 422."""
        ticket = source("components/ManualTicket.tsx")
        gate = ticket.index("const canConfirm")
        block = ticket[gate:ticket.index("return (", gate)]
        assert "market.is_combo || comboOk" in block, (
            "the confirm no longer requires the combination acknowledgement"
        )

    def test_the_armed_state_warns_before_the_confirm_not_after(self):
        """The path is armed (2026-08-26), so the ticket has to say money
        moves BEFORE the confirm — the server's note says it in the receipt,
        by which time the order has gone. Rendered only when `dry_run` is
        false, so it cannot become wallpaper.

        Mutation observed red: drop the `!market.dry_run` block."""
        ticket = source("components/ManualTicket.tsx")
        body = ticket[ticket.index("function TicketBody"):]
        assert "!market.dry_run &&" in body, (
            "the ticket no longer distinguishes the armed state before the "
            "confirm"
        )
        warning = body[body.index("!market.dry_run &&"):]
        warning = warning[: warning.index("</p>")]
        assert "spends real money" in warning
        assert "no way to cancel" in warning

    def test_the_size_ceiling_comes_from_the_server(self):
        """`max_contracts` is served so the client cannot hold a stale copy
        of a constant that exists to be raised deliberately."""
        ticket = source("components/ManualTicket.tsx")
        assert "market.max_contracts" in ticket


# --------------------------------------------------------------------------
# The search route.
# --------------------------------------------------------------------------

AUTH = {"Authorization": "Bearer secret-token"}


def _db(tmp_path):
    path = tmp_path / "search.db"
    conn = db.init_db(path)
    now = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO kalshi_events "
        "(event_ticker, title, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, ?)",
        ("KXMLBKS-26AUG26LADSF", "Los Angeles vs San Francisco", now, now),
    )
    conn.execute(
        "INSERT INTO kalshi_markets "
        "(ticker, event_ticker, title, player_name, status, close_ms,"
        " first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
        (
            "KXMLBKS-26AUG26LADSF-SFWEBB6",
            "KXMLBKS-26AUG26LADSF",
            "Logan Webb 6+ strikeouts",
            "Logan Webb",
            now + 3_600_000,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return path


def _app(path, *, mode="live", manual=ManualOrderConfig(enabled=True)):
    return create_app(
        AppConfig(instance_mode=mode, auth_token="secret-token", db_path=path),
        manual_order_config=manual,
    )


async def get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path)


class TestTheSearchFindsWhatNoScreenSurfaced:
    async def test_a_prop_the_recorder_never_priced_is_findable(self, tmp_path):
        """The whole point: `recommendations` is empty here, so no screen in
        the product shows this market, and it is still reachable."""
        app = _app(_db(tmp_path))
        response = await get(app, "/api/manual/search?q=Webb")
        assert response.status_code == 200
        tickers = [m["ticker"] for m in response.json()["markets"]]
        assert "KXMLBKS-26AUG26LADSF-SFWEBB6" in tickers

    async def test_the_payload_carries_no_price_column(self, tmp_path):
        """ADR 0065 survives the search screen only if this holds. Mutation
        observed red: select a quote column in `estimates.search_markets`."""
        app = _app(_db(tmp_path))
        response = await get(app, "/api/manual/search?q=Webb")
        keys = set(response.json()["markets"][0].keys())
        assert not (
            keys
            & {
                "ask_tenths",
                "ask_dollars",
                "yes_bid_dollars",
                "last_price_dollars",
                "fair_probability",
            }
        ), f"the search leaked a price: {keys}"

    async def test_one_character_asks_nothing(self, tmp_path):
        app = _app(_db(tmp_path))
        response = await get(app, "/api/manual/search?q=W")
        assert response.status_code == 200
        assert response.json()["markets"] == []

    async def test_the_demo_refuses_on_its_mode(self, tmp_path):
        """A search box that answers where the buy cannot reach is a door
        described as a door and leading nowhere."""
        app = _app(_db(tmp_path), mode="demo")
        response = await get(app, "/api/manual/search?q=Webb")
        assert response.status_code == 403

    async def test_the_flag_off_refuses_too(self, tmp_path):
        app = _app(_db(tmp_path), manual=ManualOrderConfig(enabled=False))
        response = await get(app, "/api/manual/search?q=Webb")
        assert response.status_code == 403
        assert "MANUAL_ORDERS_ENABLED" in response.json()["detail"]
