"""A combination bought through the desk is watched for its own exit.

A `KXMVE` combination is enter-only -- `yes_dollars` empty on 40 of 40 books
this repo has read, zero resting YES bids over 36 levels (ADR 0012 §5, ADR
0073) -- so hedging a leg is the only way out of one. `/hedge` (ADR 0078) is
that exit, and it watches `parlay_positions`.

Until 2026-09-09 the only writer of `parlay_positions` was
`POST /api/hedge/positions`, a separate tap on a separate screen. So the desk
armed the entry and left the exit to Joe's memory. Read off the live instance
on 2026-09-09: three real hand orders, two of them filled combinations on
2026-09-08, and `parlay_positions` held **zero rows** for the entire life of
both positions.

These tests pin the wiring that closes that loop, and the four ways it
refuses to invent one.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about whether a hedge is a good idea, or about the prices `/hedge`
  reports -- `test_hedge_arithmetic.py` and `test_hedge_api.py` own those.
- Nothing about the venue's create-order response; the placer is stubbed
  here exactly as it is in `test_manual_orders.py`.
- Nothing about the 37 `parlay_lookups` rows written before 2026-09-09.
  Their legs carry no label and the degraded path is asserted here on a
  synthetic row of that shape, not on the live ones.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from backend.api import routes as routes_module
from backend.kalshi.orders import OrderOutcome
from backend.store import db
from backend.store import manual_orders as manual_store

from tests.test_manual_orders import (
    AUTH,
    COMBO_TICKER,
    TICKER,
    StubQuotes,
    _app,
    _base_db,
    _body,
    _payload,
    post,
)


def _seed_lookup(
    path,
    *,
    minted=COMBO_TICKER,
    status="priced",
    legs=None,
    card_key="two-leg-card",
    requested_ms=1_700_000_000_000,
):
    """A `parlay_lookups` row, the way `_record_lookup` writes one."""
    if legs is None:
        legs = [
            {
                "event_ticker": "KXNFLGAME-26SEP13DETGB",
                "market_ticker": "KXNFLGAME-26SEP13DETGB-DET",
                "side": "yes",
                "label": "Detroit to win",
                "league": "nfl",
                "commence_ms": 1_700_000_500_000,
            },
            {
                "event_ticker": "KXNFLGAME-26SEP13BUFNYJ",
                "market_ticker": "KXNFLGAME-26SEP13BUFNYJ-BUF",
                "side": "yes",
                "label": "Buffalo to win",
                "league": "nfl",
                "commence_ms": 1_700_000_600_000,
            },
        ]
    conn = db.open_db(path)
    try:
        cursor = conn.execute(
            "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
            "selected_legs, collection_ticker, status, minted_market_ticker, "
            "derived_yes_ask_tenths, hold) "
            "VALUES (?, ?, 100, ?, 'COLL', ?, ?, 375, 0.17)",
            (requested_ms, card_key, json.dumps(legs), status, minted),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def _positions(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM parlay_positions ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _legs(path, position_id):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM parlay_position_legs WHERE position_id = ? "
            "ORDER BY leg_index",
            (position_id,),
        ).fetchall()
    finally:
        conn.close()


@pytest.fixture
def fills_for_real(monkeypatch):
    """Make the route's placer report a real, live, filled order.

    The deployed constant is False (the path is armed), and `conftest.py`
    removes the credentials so an armed route 503s at check 11 instead of
    reaching the venue. `records_only` solves that by pinning the dry-run
    flag, but a dry run is exactly the case that must NOT record a position
    -- so a test about the filled case cannot use it alone.

    So both are done: the constant is pinned True purely to skip the
    credential fetch, and the placer is replaced with one that reports
    whatever this fixture is told to report. **The route branches on
    `outcome.dry_run`, not on the constant**, which is what makes the two
    separable -- and the `dry_run=True` test below is the one that proves
    the branch is really reading the outcome.

    `fill_count` is what the venue says is held, and it is deliberately
    different from the requested contract count in the part-fill test.
    """

    def _placer_factory(fill_count=None, dry_run=False):
        monkeypatch.setattr(manual_store, "MANUAL_ORDERS_ARE_DRY_RUNS", True)

        class StubPlacer:
            def __init__(self, *args, **kwargs):
                self.dry_run = dry_run

            async def place(self, order):
                return OrderOutcome(
                    request=order,
                    status="filled" if fill_count else "unfilled",
                    dry_run=dry_run,
                    request_body={},
                    kalshi_order_id="stub-order-1",
                    fill_count=fill_count,
                    remaining_count=0.0,
                )

        monkeypatch.setattr(routes_module, "OrderPlacer", StubPlacer)

    return _placer_factory


async def _buy_combo(app, *, contracts=4, ticker=COMBO_TICKER, key="combo-key-0001"):
    return await post(
        app,
        "/api/manual-orders",
        json=_body(
            ticker=ticker,
            contracts=contracts,
            combo_acknowledged=True,
            max_price_tenths=700,
            idempotency_key=key,
        ),
        headers=AUTH,
    )


class TestAFilledCombinationBecomesAWatchedPosition:
    async def test_the_fill_writes_the_position_the_hedge_screen_reads(
        self, tmp_path, fills_for_real
    ):
        """The claim: buying a combination through the desk is enough. No
        second tap, no separate screen, no remembering."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        lookup_id = _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        response = await _buy_combo(app)
        assert response.status_code == 200, response.text

        rows = _positions(path)
        assert len(rows) == 1, "a filled combination must leave exactly one position"
        assert rows[0]["source"] == "kalshi_combo"
        assert rows[0]["status"] == "open"

    async def test_the_position_names_the_ticker_and_the_lookup_that_minted_it(
        self, tmp_path, fills_for_real
    ):
        """The two columns that existed since v-whatever and were sent by
        nobody. Without them the position and the fill are two unrelated
        rows and nothing can join them."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        lookup_id = _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        body = (await _buy_combo(app)).json()

        row = _positions(path)[0]
        assert row["combo_ticker"] == COMBO_TICKER
        assert row["parlay_lookup_id"] == lookup_id
        assert body["hedge_position_id"] == row["id"]

    async def test_every_leg_is_carried_across_with_its_name(
        self, tmp_path, fills_for_real
    ):
        """`/hedge` prices a leg and needs to say which one. A position whose
        legs are unnamed is a position he cannot act on."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        await _buy_combo(app)

        legs = _legs(path, _positions(path)[0]["id"])
        assert [leg["label"] for leg in legs] == [
            "Detroit to win", "Buffalo to win",
        ]
        assert [leg["ticker"] for leg in legs] == [
            "KXNFLGAME-26SEP13DETGB-DET", "KXNFLGAME-26SEP13BUFNYJ-BUF",
        ]
        # Structural, not a guess: a combination leg is a YES by definition.
        assert {leg["side"] for leg in legs} == {"yes"}
        assert {leg["outcome"] for leg in legs} == {"pending"}

    async def test_the_stake_is_what_he_paid_and_the_return_is_a_dollar_a_contract(
        self, tmp_path, fills_for_real
    ):
        """The equalising hedge is sized off these two numbers, so a
        misplaced decimal here becomes a wrong hedge in the sixth inning.

        The stub's derived ask is 450 tenths (the complement of the 550 NO
        bid in `_payload`), and four contracts pay $4.00 = 4,000 tenths."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        await _buy_combo(app)

        row = _positions(path)[0]
        assert row["return_tenths"] == 4000
        assert row["stake_tenths"] == 4 * 450
        assert row["return_tenths"] > row["stake_tenths"]

    async def test_a_part_fill_is_watched_at_the_size_the_venue_reports(
        self, tmp_path, fills_for_real
    ):
        """An IOC can fill part of an order. Recording the REQUESTED size
        would put contracts he does not own into the one table whose job is
        to say what he owns -- and would size the hedge against them."""
        fills_for_real(fill_count=1.0)
        path = _base_db(tmp_path)
        _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        await _buy_combo(app, contracts=4)

        row = _positions(path)[0]
        assert row["return_tenths"] == 1000, "one contract held, not four"
        assert row["stake_tenths"] == 450


class TestItRefusesToInventAPosition:
    async def test_a_dry_run_records_nothing(self, tmp_path, fills_for_real):
        """A dry run bought nothing. A position from one would be a holding
        that does not exist, on the screen that says what he holds."""
        fills_for_real(fill_count=4.0, dry_run=True)
        path = _base_db(tmp_path)
        _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        body = (await _buy_combo(app)).json()

        assert _positions(path) == []
        assert body["hedge_position_id"] is None
        assert body["hedge_position_note"] is None

    async def test_an_unfilled_order_records_nothing_and_raises_no_alarm(
        self, tmp_path, fills_for_real
    ):
        """Nothing matched, so nothing is held.

        The note must ALSO stay None. Telling him a combination is "not being
        watched" when he did not buy one is a false alarm about a position
        that does not exist -- and asserting the empty table alone does not
        catch it, because a position built from a zero fill is refused
        downstream anyway. That refusal is not this guard."""
        fills_for_real(fill_count=0.0)
        path = _base_db(tmp_path)
        _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        body = (await _buy_combo(app)).json()

        assert _positions(path) == []
        assert body["hedge_position_id"] is None
        assert body["hedge_position_note"] is None

    async def test_an_unrecognised_response_records_nothing_and_raises_no_alarm(
        self, tmp_path, fills_for_real
    ):
        """`fill_count` is None here: the order MAY have filled and the size
        is unknown. The route's own copy tells him to check the Kalshi app,
        and a position invented at the requested size would contradict it.

        The note stays None for the same reason as above -- and the whole
        point is that this branch is never entered, rather than entered and
        then failing on a `None`."""
        fills_for_real(fill_count=None)
        path = _base_db(tmp_path)
        _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        body = (await _buy_combo(app)).json()

        assert _positions(path) == []
        assert body["hedge_position_id"] is None
        assert body["hedge_position_note"] is None

    async def test_a_single_market_is_not_a_parlay(self, tmp_path, fills_for_real):
        """Only a combination is enter-only. A single market can be sold
        back, so it needs no hedge row -- and `hedge_position_note` stays
        None so 'not a combo' never reads as 'nothing is watching this'."""
        fills_for_real(fill_count=1.0)
        path = _base_db(tmp_path)
        quotes = StubQuotes(_payload(ticker=TICKER))
        app = _app(path, quotes=quotes)

        body = (
            await post(
                app, "/api/manual-orders",
                json=_body(idempotency_key="single-key-0001"), headers=AUTH,
            )
        ).json()

        assert _positions(path) == []
        assert body["hedge_position_id"] is None
        assert body["hedge_position_note"] is None

    async def test_a_fill_with_no_lookup_says_so_instead_of_going_quiet(
        self, tmp_path, fills_for_real
    ):
        """THE ONE THAT MATTERS. The money moved and nothing is watching it.

        Silence here is the exact failure this whole file exists to fix: he
        would believe the desk had his combination under watch when it had
        never heard of it. So the position is not invented AND the screen is
        told."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)          # no lookup row at all
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        body = (await _buy_combo(app)).json()

        assert _positions(path) == []
        assert body["hedge_position_id"] is None
        assert "NOT being watched" in body["hedge_position_note"]
        assert "enter-only" in body["hedge_position_note"]

    async def test_an_unpriced_lookup_is_not_used_to_build_a_position(
        self, tmp_path, fills_for_real
    ):
        """A `book_empty` row minted a ticker but priced nothing. Live rows
        39 and 40 share one `minted_market_ticker` with each other, so
        matching on the ticker alone would pick an outcome that never
        described a buyable market."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        _seed_lookup(path, status="book_empty")
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        body = (await _buy_combo(app)).json()

        assert _positions(path) == []
        assert "NOT being watched" in body["hedge_position_note"]

    async def test_the_most_recent_priced_lookup_wins(
        self, tmp_path, fills_for_real
    ):
        """A card can be looked up repeatedly and re-mint the same market.
        The legs he last saw are the legs he bought."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        _seed_lookup(path, requested_ms=1_700_000_000_000)
        newer = _seed_lookup(
            path,
            requested_ms=1_700_000_900_000,
            card_key="the-card-he-actually-tapped",
        )
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        await _buy_combo(app)

        row = _positions(path)[0]
        assert row["parlay_lookup_id"] == newer
        assert row["label"] == "the-card-he-actually-tapped"


class TestAPartialLegListIsRefusedOutright:
    """`record_position` refuses zero legs. It cannot refuse *missing* ones,
    and a combination watched as if a missing leg could not lose is worse
    than one that is not watched at all -- it is wrong rather than absent."""

    @pytest.mark.parametrize(
        "legs, why",
        [
            ([], "an empty list"),
            ([{"event_ticker": "E1"}], "a leg with no market ticker"),
            ([{"market_ticker": "M1"}, {"event_ticker": "E2"}], "one good, one not"),
        ],
    )
    async def test_an_unreadable_leg_list_records_nothing(
        self, tmp_path, fills_for_real, legs, why
    ):
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        _seed_lookup(path, legs=legs)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        body = (await _buy_combo(app)).json()

        assert _positions(path) == [], why
        assert "NOT being watched" in body["hedge_position_note"]


class TestAPreLabelLookupDegradesHonestly:
    async def test_ticker_labels_are_used_and_the_note_admits_it(
        self, tmp_path, fills_for_real
    ):
        """The 37 rows written before 2026-09-09 carry only the two tickers.

        A ticker truly names its leg, so standing in for the label is
        degradation rather than a wrong answer -- but the position has to say
        so, because a screen reading `KXNFLGAME-26SEP13DETGB-DET` where it
        should say "Detroit to win" looks broken rather than degraded."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        _seed_lookup(
            path,
            legs=[
                {
                    "event_ticker": "KXNFLGAME-26SEP13DETGB",
                    "market_ticker": "KXNFLGAME-26SEP13DETGB-DET",
                },
            ],
        )
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        await _buy_combo(app)

        row = _positions(path)[0]
        legs = _legs(path, row["id"])
        assert legs[0]["label"] == "KXNFLGAME-26SEP13DETGB-DET"
        assert legs[0]["side"] == "yes"
        assert "market tickers" in row["note"]
        assert "inventing them was refused" in row["note"]

    async def test_a_labelled_lookup_carries_no_such_apology(
        self, tmp_path, fills_for_real
    ):
        """The degraded note must not appear on a position that is fine --
        a warning that is always on is a warning nobody reads."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        _seed_lookup(path)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        await _buy_combo(app)

        assert "market tickers" not in _positions(path)[0]["note"]


class TestBookkeepingNeverFailsAPurchase:
    async def test_a_broken_position_write_still_reports_the_fill(
        self, tmp_path, fills_for_real, monkeypatch
    ):
        """The money is already spent when this runs. A bookkeeping failure
        that turned the response into a 500 would tell Joe his bet did not
        happen, which is the most expensive lie the desk could tell."""
        fills_for_real(fill_count=4.0)
        path = _base_db(tmp_path)
        _seed_lookup(path)

        def _explode(*args, **kwargs):
            raise RuntimeError("the position table is on fire")

        monkeypatch.setattr(routes_module, "_record_combo_position", _explode)
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1)
        )
        app = _app(path, quotes=quotes)

        response = await _buy_combo(app)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "filled"
        assert body["hedge_position_id"] is None
        assert "NOT being watched" in body["hedge_position_note"]


class TestTheLookupRecordsWhatThePositionNeeds:
    """The other half: `_record_lookup` has to persist the four fields, or
    everything above degrades to ticker labels forever."""

    def test_a_priced_lookup_carries_side_label_league_and_commence(self):
        from backend.core.ladder import CandidateLeg
        from backend.parlays import leg_details_for

        leg = CandidateLeg(
            label="Detroit to win",
            event_title="Detroit at Green Bay",
            kalshi_event_ticker="KXNFLGAME-26SEP13DETGB",
            kalshi_market_ticker="KXNFLGAME-26SEP13DETGB-DET",
            odds_event_id="odds-1",
            league="nfl",
            commence_ms=1_700_000_500_000,
            market="h2h",
            team="Detroit",
            point=None,
            p_conservative=0.55,
            p_by_method={},
            odds_age_now_ms=1000,
        )
        details = leg_details_for([leg])
        assert details[
            ("KXNFLGAME-26SEP13DETGB", "KXNFLGAME-26SEP13DETGB-DET")
        ] == {
            "side": "yes",
            "label": "Detroit to win",
            "league": "nfl",
            "commence_ms": 1_700_000_500_000,
        }
