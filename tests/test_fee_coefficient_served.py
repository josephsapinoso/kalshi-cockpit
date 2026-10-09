"""The lookup and check payloads serve `fee_coefficient` (#334).

The buy-sheet cost line (#328) needs the fee coefficient to show its fee and
singles clauses. Until now only an RFQ quote carried enough to derive it. Both
payloads now serve the coefficient the Take-it button's all-in cost charges:
`core.fees.COMBO_TAKER_COEFFICIENT` (0.071), reached by
`combo_rfq._all_in` -> `core.hedge.combo_entry_fee_tenths`.

What these tests establish
--------------------------
That a priced lookup and a checked parlay each carry `fee_coefficient`; that it
equals the constant the RFQ path's fee is computed from, by value and by
identity of the import (a second literal goes red); and that the RFQ path's
fee for a known stake really is that coefficient's.

What they do not establish
--------------------------
That 0.071 is the right coefficient (the fee model is unresolved: ~0.035 was
measured on baseball, ADR 0027/0145), nor that the venue charges it.
"""

# ruff: noqa: F811  (fixtures are imported from the sibling test modules)
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import backend.core.fees as fees
import backend.core.hedge as core_hedge
import backend.parlay_check as parlay_check
import backend.parlays as parlays
from backend.core.hedge import SETTLEMENT_TENTHS, combo_entry_fee_tenths
from backend.store.db import now_ms

from tests.test_parlay_check import (  # noqa: F401  (fixtures)
    COMBO_PRICED_MARKETS,
    MAX_ODDS_AGE_MS,
    PRICED_BOOK,
    FakeApi,
    REAL_URL,
    _event_markets_payload,
    conn,
    seed_game,
)
from tests.test_parlay_lookup import (  # noqa: F401  (fixtures)
    HEADERS,
    POPULATED_BOOK,
    _served_legs,
    build,
    post,
)

REPO = Path(__file__).resolve().parents[1]


class TestTheCoefficientIsTheTakeItPaths:
    def test_the_rfq_fee_is_charged_at_the_served_constant(self):
        """The RFQ path's fee for a stake equals `k * stake * (1 - p)` at the
        constant the payloads serve -- so the served number IS the one the
        button's all-in cost uses, not merely a number of the same value."""
        count, price = 100, Decimal("0.40")
        stake = int(count * price * 1000)  # tenths of a cent
        settled = count * SETTLEMENT_TENTHS
        fee = combo_entry_fee_tenths(stake, settled)
        assert fee is not None
        expected = fees.COMBO_TAKER_COEFFICIENT * count * price * (1 - price)
        # Rounded up onto a grid, never below the raw charge.
        assert Decimal(fee) / 1000 >= expected - Decimal("0.0001")
        assert Decimal(fee) / 1000 - expected <= Decimal("0.0002")

    def test_hedge_and_both_builders_use_the_one_constant(self):
        assert core_hedge.COMBO_TAKER_COEFFICIENT is fees.COMBO_TAKER_COEFFICIENT
        assert parlays.COMBO_TAKER_COEFFICIENT is fees.COMBO_TAKER_COEFFICIENT
        assert parlay_check.COMBO_TAKER_COEFFICIENT is fees.COMBO_TAKER_COEFFICIENT

    def test_no_second_literal_in_either_builder(self):
        """The served line reads the imported constant; a retyped number goes red."""
        for name in ("parlays.py", "parlay_check.py"):
            source = (REPO / "backend" / name).read_text(encoding="utf-8")
            lines = [
                l for l in source.splitlines()
                if re.match(r'\s*"fee_coefficient":', l)
            ]
            assert len(lines) == 1, name
            assert "float(COMBO_TAKER_COEFFICIENT)" in lines[0], name
            assert not re.search(r"\d", lines[0]), name


class TestBothPayloadsServeIt:
    async def test_a_priced_lookup_carries_the_coefficient(self, build):
        app, _fake_api, _path = build(book_payload=POPULATED_BOOK)
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "stake_cents": 500, "legs": legs},
            headers=HEADERS,
        )
        body = response.json()
        assert body["status"] == "priced"
        assert body["fee_coefficient"] == float(fees.COMBO_TAKER_COEFFICIENT)

    async def test_a_checked_parlay_carries_the_coefficient(self, conn):
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="fc-a", team="Team FcA", other="Team FcB",
                           p=0.6, computed_ms=base)
        t2, e2 = seed_game(conn, game="fc-b", team="Team FcC", other="Team FcD",
                           p=0.55, computed_ms=base)
        conn.commit()
        market = dict(COMBO_PRICED_MARKETS["combos"][0])
        market.update(
            ticker="KXMVECROSSCATEGORY0-SHARD1-S2026AAAAAAAAAAA-BBBBBBBBBBB",
            mve_selected_legs=[
                {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
                {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
            ],
            exchange_index=1, status="active",
        )
        api = FakeApi(
            event_markets_payload=_event_markets_payload([market]),
            book_payload=PRICED_BOOK,
        )
        result = await parlay_check.check_parlay_text(
            conn, text=REAL_URL, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["status"] == "priced"
        assert result["fee_coefficient"] == float(fees.COMBO_TAKER_COEFFICIENT)
