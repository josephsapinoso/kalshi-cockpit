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

import re
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


def _without_comments(ts: str) -> str:
    """TypeScript source with comments removed, so a pin on what a screen
    *does* is neither satisfied nor defeated by prose about what it used to
    do. Several of these files now carry paragraphs naming a prop precisely
    because it was removed."""
    ts = re.sub(r"/\*.*?\*/", "", ts, flags=re.S)
    return re.sub(r"//[^\n]*", "", ts)


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
        # **`"<ManualTicket\n"`, not `"<ManualTicket"`.** The bare prefix also
        # matches prose ABOUT the control: a component added 2026-09-10 refers
        # to `<ManualTicket>` in its docstring, and the slice silently began
        # there instead, testing a comment. The claim below is unchanged and
        # the element still carries it; only the extraction was wrong.
        combo = source("components/PriceOnKalshi.tsx")
        assert "<ManualTicket\n" in combo, "the combination buy control moved"
        note = combo[combo.index("<ManualTicket\n"):]
        note = note[: note.index("/>")]
        assert "ticker={value.minted_market_ticker}" in note, (
            "this is not the buy control; re-scope the slice before trusting it"
        )
        # **The `note=` string, not the whole element.** The element also
        # carries a JSX comment that discusses the exit, so asserting over the
        # slice passed even with the word removed from the words Joe reads --
        # observed 2026-09-10 by mutating the note and watching this stay
        # green. A claim about the screen has to be tested against the screen.
        words = note[note.index('note="') + len('note="') :]
        words = words[: words.index('"')]
        assert "exit" in words, (
            "the combination buy does not say the book has no way out"
        )

    def test_no_surface_hands_the_ticket_a_masked_ask_flag(self):
        """**Inverted 2026-09-09 on Joe's instruction, not deleted.**

        This required the ticket to carry BOTH masked-ask wordings and the
        `priceAlreadyVisible` flag that chose between them (ADR 0065 §2, its
        2026-09-05 amendment). Joe removed the probability entry the mask
        existed to protect, so the flag has nothing to select and the prop is
        gone from the component. Reversed rather than dropped: a surface that
        starts passing it again is passing a prop that does not exist, which
        is drift worth failing on.

        Mutation observed red: add `priceAlreadyVisible` to any of the four
        mounts below.
        """
        ticket = source("components/ManualTicket.tsx")
        for banned in ("already on this screen", "wearing your handwriting"):
            assert banned not in ticket, (
                f"the masked-ask wording `{banned}` survives a ticket that "
                f"masks nothing"
            )
        for surface in (
            "components/SlateRow.tsx",
            "components/LiveBoard.tsx",
            "components/PriceOnKalshi.tsx",
            "app/market/[ticker]/page.tsx",
        ):
            body = _without_comments(source(surface))
            assert "priceAlreadyVisible" not in body, (
                f"{surface} passes a masked-ask flag to a ticket with no "
                f"such prop"
            )

    def test_the_search_result_list_carries_no_price_field(self):
        """The list stays price-free. It was ADR 0065's masking that made
        this load-bearing; what makes it load-bearing now is that a price
        here would carry no age, no currency judgement and no book beside it.
        Pinned on the client too, so a future field cannot be rendered here
        without this going red."""
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


class TestTheAmountIsTypedInDollars:
    """Joe's 2026-08-30 ruling on the ticket: "confusing. Let me just buy it
    and help me with putting in the amount in dollars." The venue transacts
    in contracts; Joe thinks in dollars; the control takes dollars and SHOWS
    the conversion rather than hiding it — the desk's job is to teach the
    mapping, not to abstract it away (ADR 0071: price transparency)."""

    def test_the_primary_input_is_dollars_not_a_contracts_stepper(self):
        ticket = source("components/ManualTicket.tsx")
        assert "Amount, in dollars" in ticket
        assert 'label="Contracts"' not in ticket, (
            "the contracts stepper was the confusing control; the dollar "
            "input replaced it rather than joining it"
        )

    def test_the_conversion_rounds_down_and_says_so(self):
        """The tool must never spend more than the number typed. Rounding a
        $5 bet at 43c up to 12 contracts would spend $5.16."""
        ticket = source("components/ManualTicket.tsx")
        assert "Math.floor(amountTenths / askTenths)" in ticket
        assert "rounded down" in ticket

    def test_an_untouched_ticket_cannot_buy_one_by_default(self):
        """`contracts` starts at 0 and the confirm needs >= 1, so a ticket
        opened and confirmed without typing an amount buys nothing — the
        old default of 1 made the amount optional."""
        ticket = source("components/ManualTicket.tsx")
        assert "setContracts(0);" in ticket
        assert "contracts >= 1" in ticket

    def test_too_small_an_amount_names_the_smallest_bet(self):
        ticket = source("components/ManualTicket.tsx")
        assert "the smallest\n              bet here is" in ticket.replace(
            "\r\n", "\n"
        ) or "the smallest bet here is" in " ".join(ticket.split())

    def test_whatever_trimmed_the_size_names_itself(self):
        """$100 typed against a thinner bound must not silently buy less —
        the line says what set the size, and it was not the typed amount.

        **Re-pointed 2026-09-08 (ADR 0112 Amendment 1), claim unchanged.** It
        required the words "your per-bet cap", which is now the one thing that
        never sets the size: Joe removed that cap by name and the route
        stopped applying it. The property worth pinning was never the cap --
        it is that a silently trimmed order says what trimmed it, because the
        remedies differ (wait for the book, or move money between Kalshi
        shards).
        """
        ticket = " ".join(source("components/ManualTicket.tsx").split())
        assert "not your typed amount" in ticket
        assert "the book or your Kalshi wallet" in ticket
        # And the dead cap may not come back to this line. The RENDERED
        # sentence is pinned, not the bare phrase: the comment above the
        # ceiling quotes "your per-bet cap" to say what it replaced, and a
        # guard that refused the quotation would forbid explaining the fix.
        # Same allowance `tests/test_combo_book_depth_claims.py` makes, for
        # the same reason -- a correction often opens with the words it is
        # striking.
        assert "your per-bet cap, not your typed amount" not in ticket

    def test_the_too_small_sentence_is_chosen_on_the_typed_amount_not_the_ceiling(
        self,
    ):
        """The 2026-09-14 defect, pinned at its predicate.

        `contracts` is `affordable` AFTER the shard/depth ceiling. Choosing
        the "not enough" sentence on it meant that a $1.00 typed against a
        25.7c ask on an empty shard rendered *"one contract costs 25.7c, so
        the smallest bet here is $0.26"* — accusing Joe of typing too little
        while his dollar covered three contracts. He read it, concluded the
        desk was broken, and placed that bet directly on Kalshi instead.

        The two questions are different and only one may pick this sentence:
        `affordable` answers "do his dollars cover a contract", `contracts`
        answers "will this order go". So the guard is structural rather than
        textual — the branch must test `affordable`, and the `contracts >= 1`
        arm must not be the only thing standing between him and the
        accusation.
        """
        ticket = " ".join(source("components/ManualTicket.tsx").split())
        assert "affordable !== null && affordable >= 1 ?" in ticket, (
            "the sentence blaming the typed amount must be reachable only "
            "when the typed amount is actually the binding constraint"
        )
        # And the affordable-but-unbuyable arm must say so in Joe's words.
        assert "your typed amount is not the reason" in ticket

    def test_an_unpayable_bet_names_the_shard_the_balance_and_where_it_can_be_placed(
        self,
    ):
        """`authorised_binding: "shard"` told the client which bound bit; the
        copy named no wallet and no figure, so a reader with a funded account
        took it as a statement about what he typed.

        **Re-pointed 2026-09-14 (ADR 0149), claim strengthened.** For a few
        hours this required the string `kalshi.com/account/exchange-indexes`,
        on the argument that a refusal must name its remedy. Measured the same
        evening: that page is now READ-ONLY — four balance cards and the
        auto-management toggle, no transfer control — so the sentence
        instructed an action Joe could not perform. A remedy that cannot be
        carried out is worse than no remedy, because it sends him away to
        fail rather than to the venue that will take the bet.

        What the refusal must still do: name the wallet, name what is in it,
        and say where the bet can actually be placed. The URL is now
        *forbidden* rather than required — the same shape as the dead
        per-bet cap in `test_whatever_trimmed_the_size_names_itself`.
        """
        ticket = " ".join(source("components/ManualTicket.tsx").split())
        assert "shard {shard.index}" in ticket
        assert "{shard.available_display}" in ticket
        # What is actually wrong: the wallet is empty, not the path closed.
        assert "has to hold the money before you tap" in ticket
        # Never a brake of ours on the SIZE of the bet (ADR 0112). Matched
        # case-insensitively: the sentence has opened the clause and started
        # mid-sentence across three rewrites today, and the claim is the
        # words, not where the full stop happens to fall.
        assert "cap of the desk" in ticket.lower()

    def test_the_refusal_does_not_claim_combos_cannot_be_bought_here(self):
        """**ADR 0150.** For one deploy this screen said the bet was
        "placeable on kalshi.com and not here", off three `insufficient_balance`
        probes taken while shard 1 held a cent.

        Six of Joe's seven real `manual_orders` rows are filled
        `KXMVECROSSCATEGORY-SHARD1` combinations placed through this very
        path on 09-08, 09-09 and 09-10, when that wallet was funded. Three
        refusals measured an empty wallet, not a closed path, and the copy
        turned a state into a property.

        A screen that tells him his own past bets were impossible teaches him
        to stop believing the screen.
        """
        ticket = " ".join(source("components/ManualTicket.tsx").split())
        assert "placeable on kalshi.com and not here" not in ticket
        assert "cannot be placed here" not in ticket
        # The positive claim that keeps it honest: it HAS worked when funded.
        assert "whenever it was funded" in ticket

    def test_the_allocation_page_is_not_offered_as_a_bare_remedy(self):
        """Whether that page can move money depends on a toggle Joe sets
        there: with "Disable balance management" OFF it is four balance cards
        and no control (measured 2026-09-14 morning); with it ON the transfer
        control appears (he used it that evening, ADR 0150 §6). A bare URL in
        the copy is therefore the ADR 0148 §4 remedy again — an instruction
        that works in one state and sends him to fail in the other — so both
        surfaces name the condition and neither names the page.

        This docstring said "cannot move money any more" until 2026-09-14
        (sixteenth session); that was a state restated as a property.

        Asserted across BOTH surfaces that carried it, because the sentence
        was copied into the glossary as well and a guard on one file would
        have left the other lying.
        """
        for module in ("components/ManualTicket.tsx", "lib/glossary.ts"):
            body = " ".join(source(module).split())
            assert "kalshi.com/account/exchange-indexes" not in body, (
                f"{module} names the page without the toggle state it needs"
            )

    def test_an_unreadable_wallet_is_not_rendered_as_an_empty_one(self):
        """`Unreadable resolves to None, never to 0` reaches the screen.

        A zero balance is a fact ("your money is gone"); an unread one is
        not, and this is the path where confusing them would send Joe to
        Kalshi to look for money that is sitting there.
        """
        ticket = " ".join(source("components/ManualTicket.tsx").split())
        assert "could not be read" in ticket
        assert "shard.index === null || shard.available_display === null" in ticket

    def test_the_trim_sentence_does_not_double_up_with_the_zero_case(self):
        """Joe got both sentences in one paragraph, with opposite causes:
        "the smallest bet here is $0.26" followed by "Trimmed to 0 — the book
        or your Kalshi wallet ... set the size". The trim line is for an order
        that was cut down, not for one that cannot be placed at all."""
        ticket = " ".join(source("components/ManualTicket.tsx").split())
        assert "capped && ceiling !== null && ceiling >= 1 &&" in ticket

    def test_the_confirm_button_carries_the_dollar_cost(self):
        ticket = source("components/ManualTicket.tsx")
        assert "for ${dollars(" in ticket

    def test_the_money_math_is_integer_tenths(self):
        """`core/prices.py`'s rule reaches the client: the conversion is
        `Math.round(parsed * 1000)` into tenths, and division happens only
        for display."""
        ticket = source("components/ManualTicket.tsx")
        assert "Math.round(parsed * 1000)" in ticket


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
