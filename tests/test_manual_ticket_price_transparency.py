"""Five answers on the manual ticket, 2026-09-16 (tickets #39 #40 #42 #44 #46).

Joe answered the batched interview in one line -- `39A 40A 42A 44A 46C` --
and every one of them is a fact put on, or taken off, the screen where a bet
is decided. This file pins each at the server half where there is one and at
the ticket's source where the words are load-bearing.

  #39 A  The fee is on the Confirm button, inside an "at most" figure, and the
         break-even is on the line above it. Both are SERVED: the preflight
         carries `fee_per_contract_tenths` and `breakeven_probability` per
         side, from the same fee module the order path runs, and the ticket
         multiplies by the typed count and formats -- no fee curve in
         TypeScript (`serialise.py`, beside `total_cost_dollars`, says why).
         The sentence "the exact fee on this venue is still being measured"
         is retired in favour of the number. ADR 0062 Amendment 1.
  #40 A  The ask carries its age, ticking, and a re-read control fetches the
         preflight again and re-pins the max price to the new ask. Informs,
         never gates: `canConfirm` reads neither.
  #42 A  `commence_ms` joins the preflight -- the sportsbook's clock via
         `event_links`, never `kalshi_events` -- and a started game says so
         above the confirm. An unknown kickoff renders nothing.
  #44 A  `kalshiMarketUrl` in both refusal states and beside the depth line,
         as a plain link that says it leaves the cockpit.
  #46 C  `venue_daily_pnl_dollars` is gone from the preflight. It was
         computed on every open under a comment saying "it is shown" and was
         rendered nowhere; a signed running P&L on a deciding screen is the
         chase trigger this repo has deleted twice.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing renders.** The ticket half is source assertions over the TSX,
  the same instrument as `tests/test_buy_controls.py`; a green run says the
  branches exist, not that they paint, tick or are legible at 390px.
- **Nothing about the fee model's truth.** The route is checked AGAINST
  `core/fees.py`, not against a typed number, so this fails if the route
  stops calling the module and passes whatever the module says. Whether the
  module matches the venue is `tests/test_fees.py` and the fee measurements.
- **Nothing about the venue's kickoff.** `commence_ms` is whatever
  `odds_snapshots` holds for the linked fixture; a wrong link is a wrong
  clock, and `tests/test_slate_kickoff_matches_detail.py` owns that the
  surfaces agree with each other.

Mutations, each observed red (recorded in the build report, not repeated
per test):
  1. serve `fee_per_contract_tenths: 0` when the fee is unreadable
  2. price the fee with `calculate_fee` on a combination
  3. drop the `for at most` figure back to `contracts * ask`
  4. restore the "still being measured" sentence
  5. delete the `setInterval` tick
  6. make the re-read keep the opening `maxPriceTenths`
  7. add `quoteAge` to `canConfirm`
  8. serve `commence_ms` from `kalshi_events.commence_ms`
  9. render the started line on `commence_ms === null`
 10. delete `<KalshiLink` from the refused branch
 11. restore `venue_daily_pnl_dollars` to the preflight
"""

from __future__ import annotations

import re
import sys
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from backend.core.fees import calculate_fee, combo_taker_fee
from backend.store import db

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_desk_panels import code_only  # noqa: E402
from test_manual_orders import (  # noqa: E402
    COMBO_TICKER,
    TICKER,
    StubQuotes,
    _app,
    _base_db,
    _payload,
    _seed_consensus,
    get,
)

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
TICKET = SRC / "components" / "ManualTicket.tsx"
ROUTES = REPO / "backend" / "api" / "routes.py"


def ticket_source() -> str:
    return TICKET.read_text(encoding="utf-8").replace("\r\n", "\n")


def ticket_code() -> str:
    return code_only(ticket_source())


def preflight_source() -> str:
    """The body of `manual_market` alone, so a pin on what the preflight does
    is not satisfied by the POST route two screens later."""
    text = ROUTES.read_text(encoding="utf-8")
    start = text.index('@app.get("/api/manual/market/{ticker}")')
    end = text.index('@app.get("/api/manual/search")', start)
    return text[start:end]


def _fee_tenths_and_breakeven(ask_tenths: int, *, combo: bool):
    """The expected pair, from the fee module rather than a typed number."""
    fee = (combo_taker_fee if combo else calculate_fee)(ask_tenths, 1)
    assert fee is not None
    exact = Decimal(str(fee)) * 1000
    return (
        int(exact.to_integral_value(rounding=ROUND_CEILING)),
        float((Decimal(ask_tenths) + exact) / 1000),
    )


# --------------------------------------------------------------------------
# #39 -- the fee is served, and the ticket only multiplies.
# --------------------------------------------------------------------------


class TestTheFeeOnTheButtonIsTheServers:
    async def test_the_preflight_serves_the_fee_module_per_contract(
        self, tmp_path
    ):
        """A single market: `calculate_fee` at one contract, taker, flat
        coefficient, rounded UP onto a whole tenth."""
        app = _app(_base_db(tmp_path))
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        for side in ("yes", "no"):
            facts = body["sides"][side]
            ask = facts["ask_tenths"]
            assert ask is not None
            fee_tenths, breakeven = _fee_tenths_and_breakeven(ask, combo=False)
            assert facts["fee_per_contract_tenths"] == fee_tenths
            assert facts["breakeven_probability"] == breakeven

    async def test_n_times_the_served_fee_never_undercharges_the_order(
        self, tmp_path
    ):
        """"At most" is the claim, so the product the button shows must sit
        at or above the per-order charge for every count the ticket can
        type. `N * ceil(x) >= ceil(N * x)`, checked rather than asserted."""
        app = _app(_base_db(tmp_path))
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        facts = body["sides"]["yes"]
        served = facts["fee_per_contract_tenths"]
        for count in range(1, 41):
            order_fee = calculate_fee(facts["ask_tenths"], count)
            assert order_fee is not None
            assert count * served >= order_fee * 1000, count

    async def test_a_combination_is_priced_through_the_combo_coefficient(
        self, tmp_path
    ):
        """Mutation observed red: `calculate_fee` on a combination. The
        0.070 coefficient undercharged four of the eight combo fills on the
        record (ADR 0073), and "at most" must hold on both products."""
        quotes = StubQuotes(_payload(ticker=COMBO_TICKER, exchange_index=1))
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{COMBO_TICKER}")).json()
        assert body["is_combo"] is True
        facts = body["sides"]["yes"]
        fee_tenths, breakeven = _fee_tenths_and_breakeven(
            facts["ask_tenths"], combo=True
        )
        assert facts["fee_per_contract_tenths"] == fee_tenths
        assert facts["breakeven_probability"] == breakeven
        single = _fee_tenths_and_breakeven(facts["ask_tenths"], combo=False)
        assert (fee_tenths, breakeven) != single, (
            "the combination pair equals the single-market pair at this ask, "
            "so the test cannot tell which coefficient ran"
        )

    async def test_the_break_even_at_fifty_cents_is_the_applied_bar(
        self, tmp_path
    ):
        """51.75% -- the spine's applied bar -- and not the ceiled tenth's
        51.8%. The break-even is served from the $0.0001 fee, and this is
        the one ask where the two differ visibly."""
        quotes = StubQuotes(_payload(yes_bid_tenths=500, no_bid_tenths=500))
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        facts = body["sides"]["yes"]
        assert facts["ask_tenths"] == 500
        assert facts["fee_per_contract_tenths"] == 18
        assert round(facts["breakeven_probability"], 4) == 0.5175

    async def test_no_ask_serves_no_fee_and_never_a_free_one(self, tmp_path):
        """Mutation observed red: `fee_per_contract_tenths: 0` on no ask.
        A zero fee beside a missing ask is a free bet drawn from nothing --
        `calculate_fee` refuses that and the route must not undo it."""
        quotes = StubQuotes(_payload(yes_bid_tenths=0, no_bid_tenths=1000))
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        for side in ("yes", "no"):
            facts = body["sides"][side]
            assert facts["ask_tenths"] is None
            assert facts["fee_per_contract_tenths"] is None
            assert facts["breakeven_probability"] is None

    def test_the_button_says_at_most_with_the_fee_inside_it(self):
        """Mutation observed red: `contracts * facts.ask_tenths` alone."""
        code = ticket_code()
        button = code[code.index("onClick={onConfirm}"):]
        button = button[: button.index("</button>")]
        assert "for at most ${dollars(" in button
        assert "contracts * feeBasisTenths" in button
        assert "+ fee ${" in button
        # An unreadable fee is said, never priced at zero.
        assert "feeBasisTenths === null" in button
        assert "could not price" in button

    def test_a_raised_max_price_prices_the_button_off_the_max(self):
        """The receipt prices the worst case at the SENT limit
        (`orders.py:worst_case_cost_dollars`), so once the Max-price stepper
        is above the ask, "at most" off the ask is false by (max - ask) x N
        plus the fee delta -- kalshi-platform review, 2026-09-16. The stake
        basis becomes the max and the fee basis the served 50c ceiling.
        Mutations observed red: basis fixed to the ask; fee basis fixed to
        the ask's fee."""
        code = ticket_code()
        start = code.index("const raised =")
        block = code[start : code.index("</button>", start)]
        assert "maxPriceTenths > facts.ask_tenths" in block
        assert "raised ? maxPriceTenths : facts.ask_tenths" in block
        assert "facts.fee_ceiling_per_contract_tenths" in block
        assert "contracts * priceBasisTenths + contracts * feeBasisTenths" in block
        assert "your max price" in block

    async def test_the_fee_ceiling_is_the_charge_at_fifty_cents(self, tmp_path):
        """P*(1-P) peaks at 50c, so the fee there bounds the fee at any
        price; the ticket uses it once the max price is raised. Same
        combo/single choice as the ask's own fee."""
        app = _app(_base_db(tmp_path))
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        for side in ("yes", "no"):
            facts = body["sides"][side]
            cap, _ = _fee_tenths_and_breakeven(500, combo=False)
            assert facts["fee_ceiling_per_contract_tenths"] == cap
            assert cap >= facts["fee_per_contract_tenths"]
            for ask in range(10, 1000, 10):
                assert _fee_tenths_and_breakeven(ask, combo=False)[0] <= cap

    def test_the_break_even_prints_hundredths_so_the_bar_is_not_rounded_toward_the_bet(self):
        """`(0.5175 * 100).toFixed(1)` is "51.7" in JavaScript -- the bar
        rounded DOWN, toward the bet, and a display the served exact figure
        was meant to avoid. Two decimals print the applied bar as 51.75%."""
        code = ticket_code()
        assert "(facts.breakeven_probability * 100).toFixed(2)" in code
        assert ".toFixed(1)}%" not in code

    def test_the_ticket_reimplements_no_fee_curve(self):
        """No coefficient in an expression, no `P * (1 - P)`, no `Math.ceil`
        on money: the client multiplies a served integer by a count and
        formats. The rendered sentence may NAME the coefficient ("a flat
        0.070"), which is why the coefficient is banned as an operand rather
        than as a substring."""
        code = ticket_code()
        for banned in ("* 0.07", "0.07 *", "* 0.071", "0.071 *", "(1 - ", "Math.ceil"):
            assert banned not in code, f"a fee curve is being priced here: {banned!r}"
        # The one place the fee is touched is a multiplication by the count.
        uses = re.findall(r"[^\n]*fee(?:_ceiling)?_per_contract_tenths[^\n]*", code)
        assert uses, "the served fee is never read"
        for use in uses:
            # Either a served figure is chosen as the basis, or the basis is
            # multiplied by the count. Nothing else touches it.
            assert (
                "? facts.fee_ceiling_per_contract_tenths" in use
                or ": facts.fee_per_contract_tenths" in use
                or "=== null" in use
            ), use
        basis_uses = re.findall(r"[^\n]*feeBasisTenths[^\n]*", code)
        for use in basis_uses:
            assert (
                "contracts * feeBasisTenths" in use
                or "=== null" in use
                or "const feeBasisTenths" in use
            ), use

    def test_the_break_even_line_is_served_and_sits_above_the_confirm(self):
        code = ticket_code()
        line = code.index("facts.breakeven_probability !== null &&")
        assert line < code.index("onClick={onConfirm}")
        assert "You need this to happen more than" in code
        assert "to break even" in " ".join(code.split()) or 'k="breakeven"' in code
        # Printed, not divided out: the only arithmetic is the percent scale.
        assert "facts.breakeven_probability * 100" in code
        assert "/ 1000" not in code[line : line + 800]

    def test_the_still_being_measured_sentence_is_retired(self):
        """Mutation observed red: restore the sentence. The number replaces
        the excuse; the truth that the coefficient is deliberately high
        stays."""
        text = " ".join(ticket_source().split())
        assert "still being measured" not in text
        assert "deliberately" in text and "0.070" in text


# --------------------------------------------------------------------------
# #40 -- the ask carries its age, and the book can be re-read.
# --------------------------------------------------------------------------


class TestTheAskCarriesItsAgeAndCanBeReread:
    def test_the_age_is_read_off_observed_ms_on_a_tick(self):
        """Mutation observed red: delete the `setInterval`. A frozen age is
        the defect `LiveBoard.tsx` fixed for the Picks cards -- a 6pm read
        still says "30s ago" at 11pm."""
        code = ticket_code()
        assert "market.observed_ms" in code
        assert "setInterval(tick, TICKET_TICK_MS)" in code
        assert "clearInterval(timer)" in code
        assert "formatAge(Math.max(0, now - market.observed_ms))" in code

    def test_the_age_sits_beside_each_ask(self):
        code = ticket_code()
        buttons = code[code.index('(["yes", "no"] as const).map'):]
        buttons = buttons[: buttons.index("</button>")]
        assert "ask_display ?? \"no ask\"" in buttons
        assert "{quoteAge}" in buttons

    def test_the_reread_refetches_and_repins_the_max_price(self):
        """Mutation observed red: keep `maxPriceTenths` on re-read. The
        ceiling sent with the order is the ask AS READ; a re-read that left
        the opening ask pinned would send a ceiling the route refuses."""
        code = ticket_code()
        body = code[code.index("const reread = async"):]
        body = body[: body.index("const confirm = async")]
        assert "await fetchManualMarket(ticker)" in body
        assert "setMaxPriceTenths(market.sides[nextSide].ask_tenths)" in body
        assert 'setPhase({ name: "ticket", market })' in body
        # One ticket, one order: the idempotency key is not regenerated.
        assert "setIntentKey" not in body
        assert "Re-read the book" in code

    def test_a_failed_reread_leaves_the_ticket_open(self):
        code = ticket_code()
        body = code[code.index("const reread = async"):]
        body = body[: body.index("const confirm = async")]
        assert "setRereadNote(" in body
        assert 'name: "blocked"' not in body
        assert 'name: "closed"' not in body

    def test_nothing_about_the_age_reaches_the_confirm(self):
        """Mutation observed red: `quoteAge` in `canConfirm`. ADR 0112
        removed five brakes; a staleness gate is the sixth."""
        code = ticket_code()
        gate = code[code.index("const canConfirm"):]
        gate = gate[: gate.index("return (")]
        for name in ("quoteAge", "observed_ms", "now ", "rereadNote", "commence"):
            assert name not in gate, f"{name!r} gates the confirm"
        confirm = code[code.index("onClick={onConfirm}"):]
        confirm = confirm[: confirm.index(">")]
        assert "disabled={!canConfirm}" in confirm

    def test_nothing_refreshes_on_its_own(self):
        """No auto-refresh (the brief's word). The only `fetchManualMarket`
        calls are the open and the tap."""
        code = ticket_code()
        assert code.count("fetchManualMarket(ticker)") == 2
        effects = re.findall(r"useEffect\(\(\) => \{(.*?)\}, \[", code, flags=re.S)
        for effect in effects:
            assert "fetchManualMarket" not in effect


# --------------------------------------------------------------------------
# #42 -- the ticket half: a started game says so.
# --------------------------------------------------------------------------


def _seed_kickoff(path, *, commence_ms: int, odds_event_id: str = "odds-1"):
    """One sportsbook row for the fixture `_seed_consensus` links, so the
    preflight's `MIN(commence_ms)` has something to read."""
    conn = db.open_db(path)
    try:
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
            "commence_ms, home_team, away_team, bookmaker, market, "
            "outcome_name, price_decimal) VALUES (?, 'baseball_mlb', ?, ?, "
            "'B', 'A', 'pinnacle', 'h2h', 'A', 1.9)",
            (commence_ms, odds_event_id, commence_ms),
        )
        conn.commit()
    finally:
        conn.close()


class TestTheTicketKnowsWhenTheGameStarted:
    async def test_commence_ms_is_the_sportsbooks_clock(self, tmp_path):
        """Mutation observed red: read `kalshi_events.commence_ms` instead.
        The seed puts a DIFFERENT time on the Kalshi event, three hours
        later (ADR 0006's offset), so a fallback to it is caught."""
        path = _base_db(tmp_path)
        _seed_consensus(path)
        kickoff = 1_700_000_000_000
        _seed_kickoff(path, commence_ms=kickoff)
        conn = db.open_db(path)
        try:
            conn.execute(
                "UPDATE kalshi_events SET commence_ms = ? WHERE event_ticker = 'E1'",
                (kickoff + 3 * 3_600_000,),
            )
            conn.commit()
        finally:
            conn.close()
        app = _app(path)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["commence_ms"] == kickoff

    async def test_an_unlinked_ticker_serves_null_not_a_time(self, tmp_path):
        """A combination, and any ticker discovery has not walked, has no
        fixture. `null`, and never a Kalshi-clock substitute."""
        path = _base_db(tmp_path)
        _seed_consensus(path)
        conn = db.open_db(path)
        try:
            conn.execute(
                "UPDATE kalshi_events SET commence_ms = 1 WHERE event_ticker = 'E1'"
            )
            conn.commit()
        finally:
            conn.close()
        app = _app(path)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["commence_ms"] is None
        quotes = StubQuotes(_payload(ticker=COMBO_TICKER, exchange_index=1))
        combo = (await get(_app(path, quotes=quotes), f"/api/manual/market/{COMBO_TICKER}")).json()
        assert combo["commence_ms"] is None

    def test_the_started_line_renders_only_on_a_known_past_kickoff(self):
        """Mutation observed red: render on `commence_ms === null`. An
        unknown kickoff establishes nothing, so it renders nothing -- never
        "not started"."""
        code = ticket_code()
        assert "market.commence_ms !== null && market.commence_ms <= now &&" in code
        # Rendered words, comments stripped: the comment above the line
        # quotes the forbidden phrase to say why it is forbidden.
        text = " ".join(code.split())
        assert "this is in-play" in text
        assert "from before kickoff" in text
        assert "not started" not in text.lower()
        assert "not yet started" not in text.lower()

    def test_the_started_line_sits_above_the_confirm_and_gates_nothing(self):
        code = ticket_code()
        line = code.index("market.commence_ms !== null")
        assert code.index("<Exposure words={exposure} />") < line
        assert line < code.index("onClick={onConfirm}")
        gate = code[code.index("const canConfirm"):]
        gate = gate[: gate.index("return (")]
        assert "commence" not in gate


# --------------------------------------------------------------------------
# #44 -- the way out, on every state.
# --------------------------------------------------------------------------


class TestEveryStateLinksOutToKalshi:
    def _branch(self, code: str, phase: str) -> str:
        """That phase's JSX alone: from its predicate to the next phase's, or
        to the end of `body` when it is the last one rendered."""
        start = code.index(f'phase.name === "{phase}" &&')
        rest = code[start + 1 :]
        nxt = re.search(r'phase\.name === "(?!' + phase + r')\w+" &&', rest)
        end = nxt.start() if nxt is not None else rest.index("return inline ?")
        return code[start : start + 1 + end]

    def test_the_link_is_the_shared_helper_not_a_typed_url(self):
        code = ticket_code()
        assert 'from "@/lib/kalshiLink"' in code
        assert "kalshiMarketUrl(ticker)" in code
        assert "https://kalshi.com/markets/" not in code, (
            "a URL typed here is a second copy of the verified scheme"
        )

    def test_the_blocked_state_carries_it(self):
        assert "<KalshiLink" in self._branch(ticket_code(), "blocked")

    def test_the_refused_state_carries_it(self):
        """Mutation observed red: delete `<KalshiLink` from the refused
        branch."""
        assert "<KalshiLink" in self._branch(ticket_code(), "refused")

    def test_the_open_ticket_carries_it_beside_the_depth_line(self):
        code = ticket_code()
        depth = code.index('<Term k="depth">Depth</Term>')
        paragraph = code[depth : code.index("</p>", depth)]
        assert "<KalshiLink" in paragraph

    def test_it_is_a_plain_link_that_says_it_leaves(self):
        code = ticket_code()
        link = code[code.index("function KalshiLink"):]
        link = link[: link.index("\n}\n")]
        assert "<a" in link and "<button" not in link
        assert 'target="_blank"' in link
        assert 'rel="noopener noreferrer"' in link
        assert "leaves the cockpit" in link
        # A combination has no deep link and the label must not call the
        # market list "this market".
        assert "KALSHI_MARKETS_INDEX" in link


# --------------------------------------------------------------------------
# #46 -- no running P&L on the preflight.
# --------------------------------------------------------------------------


class TestThePreflightComputesNoRealisedPnl:
    async def test_the_key_is_gone_from_the_payload(self, tmp_path):
        """Mutation observed red: restore the field."""
        app = _app(_base_db(tmp_path))
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert "venue_daily_pnl_dollars" not in body
        assert not any("pnl" in key for key in body), sorted(body)

    def test_the_read_itself_is_gone_not_just_the_key(self):
        """A read that is computed and dropped still costs the open and still
        invites the next session to "just wire it up"."""
        assert "venue_daily_realised_pnl_dollars" not in preflight_source()

    def test_the_comment_no_longer_says_it_is_shown(self):
        body = preflight_source()
        assert "it is shown, which is the job ADR 0071 names" not in body
        assert "chase trigger" in body

    def test_the_frontend_never_read_it(self):
        for rel in ("lib/api.ts", "components/ManualTicket.tsx"):
            assert "venue_daily_pnl_dollars" not in (SRC / rel).read_text(
                encoding="utf-8"
            ), rel
