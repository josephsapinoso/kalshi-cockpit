"""`POST /api/hedge/positions/{id}/sell-quote` -- what makers would pay (#96).

Joe's answer (A) to #63: both exit prices on `/hedge`, read-only, no selling
from the desk. This route is the RFQ half; the public book's bid is #95.

The seven defects of #96's spec (the `kalshi-platform` review of the #76
slice-3 draft), each with the test that holds it:

1. size is `contracts_fp` floored from the venue's `position_fp`, never a
   dollar target -- `TestTheSizeIsTheHoldingFloored`;
2. never fired from the 60 s `hedge_watch` loop --
   `TestTheWatchLoopNeverAsks`;
3. goes through the one shared Kalshi client (the order path's limiter) --
   `TestTheAskUsesTheSharedClient`;
4. a size-based ask never reuses an open RFQ -- `tests/test_combo_rfq.py::
   TestAnOversizedOpenRfqIsReplacedNotReused::test_a_size_based_ask_is_
   refused_neither_reused_nor_deleted`, plus the route's 409 here;
5. a YES bid finer than a tenth is a named refusal, not a swallowed None --
   `TestABidTooFineToPrintIsNamed`;
6. the wire shape comes from a CAPTURED sell-side payload --
   `tests/fixtures/combo_rfq_quotes_sell_side.json`, `TestTheCapturedPayload`;
7. `yes_ask_tenths` nullable, by a v56 table rebuild --
   `TestTheSellOnlyQuoteIsStorable`.

What these do not establish
---------------------------
- Nothing about how often a held combination draws a bid. The fixture is one
  held combination at one moment (2026-09-24), a count, not a rate.
- Nothing about whether a bid would fill, or is good. Nothing here sells.
- Nothing about maker latency: the fake answers instantly.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from backend import hedge
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.kalshi.rfq import floor_contracts_fp, parse_quotes
from backend.store import db as store

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "combo_rfq_quotes_sell_side.json"
HEADERS = {"Authorization": "Bearer secret-token"}
TICKER = "KXMVECROSSCATEGORY-S2026SELL-TEST"
RFQ_ID = "rfq-sell"
COLLECTION = "KXMVECROSSCATEGORY-R"
LEGS = [
    {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
    {"event_ticker": "E2", "market_ticker": "M2", "side": "yes"},
]


def _captured_quotes(rfq_id: str = RFQ_ID) -> list[dict]:
    """The real sell-side quotes, re-pointed at the fake's RFQ id."""
    quotes = json.loads(FIXTURE.read_text(encoding="utf-8"))["quotes"]
    return [{**q, "rfq_id": rfq_id} for q in quotes]


def _pem(tmp_path: Path) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    path = tmp_path / "key.pem"
    if not path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return path


class FakeVenue:
    """The shared `KalshiRestClient`, recording calls in order.

    Deleting drops the quotes, as the venue does (measured 2026-09-17).
    """

    def __init__(self, *, held_fp="2.01", quotes=None, conflict=False):
        self.calls: list[str] = []
        self.bodies: list[dict] = []
        self.held_fp = held_fp
        self.quotes = quotes if quotes is not None else _captured_quotes()
        self.conflict = conflict
        self.deleted = False

    async def positions(self):
        self.calls.append("positions")
        if self.held_fp is None:
            return [{"ticker": "KXMVE-SOMETHING-ELSE", "position_fp": "3.00"}]
        return [{"ticker": TICKER, "position_fp": self.held_fp}]

    async def get(self, path, **params):
        self.calls.append("market")
        assert path == f"/markets/{TICKER}", path
        return {"market": {"ticker": TICKER, "mve_collection_ticker": COLLECTION,
                           "mve_selected_legs": LEGS}}

    async def request(self, method, path, *, params=None, json_body=None):
        if method == "POST" and path.endswith("/rfqs"):
            self.calls.append("create")
            assert params == {"exchange_index": 1}, "the write must name the shard"
            self.bodies.append(dict(json_body))
            if self.conflict:
                raise RuntimeError('HTTP 409 {"error":{"code":"already_exists"}}')
            return {"id": RFQ_ID}
        if method == "GET" and path.endswith("/quotes"):
            self.calls.append("read")
            return {"quotes": [] if self.deleted else self.quotes}
        if method == "DELETE":
            self.calls.append("delete")
            self.deleted = True
            return {}
        raise AssertionError(f"unexpected {method} {path}")


def _seed(conn, *, combo_ticker=TICKER, source="kalshi_combo") -> int:
    return hedge.record_position(
        conn,
        now_ms=1_000,
        source=source,
        label="two legs",
        stake_tenths=1_020,
        return_tenths=10_000,
        legs=[
            {"ticker": "M1", "side": "yes", "label": "One"},
            {"ticker": "M2", "side": "yes", "label": "Two"},
        ],
        combo_ticker=combo_ticker,
        placed_ms=1_000,
        book=None if source == "kalshi_combo" else "DraftKings",
    )


@pytest.fixture()
def build(tmp_path, monkeypatch):
    def _build(*, venue=None, combo_ticker=TICKER, source="kalshi_combo"):
        path = tmp_path / "t.db"
        conn = store.init_db(path)
        position_id = _seed(conn, combo_ticker=combo_ticker, source=source)
        conn.commit()
        conn.close()

        fake = venue or FakeVenue()
        made: list[FakeVenue] = []

        def _client(config, client=None):
            made.append(fake)
            return fake

        monkeypatch.setattr("backend.api.routes.KalshiRestClient", _client)
        monkeypatch.setenv("KALSHI_API_KEY", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(_pem(tmp_path)))
        monkeypatch.setattr("backend.combo_rfq.QUOTE_WAIT_S", 0.05)
        monkeypatch.setattr("backend.combo_rfq.QUOTE_POLL_S", 0.01)
        app = create_app(
            AppConfig(instance_mode="live", auth_token="secret-token", db_path=path)
        )
        return app, fake, path, position_id, made
    return _build


async def _ask(app, position_id, headers=HEADERS):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(
            f"/api/hedge/positions/{position_id}/sell-quote", headers=headers
        )


class TestTheCapturedPayload:
    """Defect 6: the parser is tested against what the venue actually sent."""

    def test_the_sell_only_quotes_are_kept_on_a_sell_side_read(self):
        read = parse_quotes({"quotes": _captured_quotes()}, rfq_id=RFQ_ID,
                            keep_sell_only=True)
        assert len(read.quotes) == 17
        sell_only = [q for q in read.quotes if q.yes_ask_tenths is None]
        assert len(sell_only) == 2, "the two quotes with no_bid 0.0000"
        assert all(q.no_bid_tenths is None for q in sell_only)
        assert all(q.yes_bid_tenths is not None for q in sell_only)

    def test_the_best_bid_is_one_the_buy_rule_would_have_dropped(self):
        """The whole reason for defect 7: the best exit on the capture was a
        sell-only quote."""
        sell = parse_quotes({"quotes": _captured_quotes()}, rfq_id=RFQ_ID,
                            keep_sell_only=True)
        assert sell.quotes[0].yes_bid_tenths == 102
        assert sell.quotes[0].yes_ask_tenths is None
        buy = parse_quotes({"quotes": _captured_quotes()}, rfq_id=RFQ_ID)
        assert len(buy.quotes) == 15, "the buy-side read must not change"
        assert max(q.yes_bid_tenths or 0 for q in buy.quotes) == 101

    def test_the_bid_size_is_the_yes_side_field(self):
        """`yes_contracts_fp`, not `no_contracts_fp`: a sell-only quote
        carries no buy-side size at all."""
        read = parse_quotes({"quotes": _captured_quotes()}, rfq_id=RFQ_ID,
                            keep_sell_only=True)
        best = read.quotes[0]
        assert best.contracts is None
        assert best.yes_bid_contracts == 2.0
        no_bid = [q for q in read.quotes if q.yes_bid_tenths is None]
        assert no_bid and all(q.yes_bid_contracts is None for q in no_bid)


class TestABidTooFineToPrintIsNamed:
    """Defect 5: a real exit price in hundredths of a cent is a refusal with
    a name, recorded by quote id -- never a silent None."""

    def test_the_refusal_carries_the_quote_id(self):
        row = {**_captured_quotes()[1], "yes_bid_dollars": "0.0055"}
        read = parse_quotes({"quotes": [row]}, rfq_id=RFQ_ID, keep_sell_only=True)
        assert read.refused_bid_finer_than_tenths == frozenset({row["id"]})

    async def test_the_route_says_so_instead_of_nobody_bid(self, build):
        quotes = [
            {**q, "yes_bid_dollars": "0.0055"} if q["yes_bid_dollars"] != "0.0000"
            else q
            for q in _captured_quotes()
        ]
        app, _, _, position_id, _ = build(venue=FakeVenue(quotes=quotes))
        body = (await _ask(app, position_id)).json()
        assert body["status"] == "bid_too_finely"
        assert body["refused_bid_too_fine"] == 8
        assert "finer than a tenth of a cent" in body["words"]


class TestTheSizeIsTheHoldingFloored:
    """Defect 1: `contracts_fp`, floored to 0.01, from the venue's holding."""

    @pytest.mark.parametrize("held,asked", [
        ("8.226", "8.22"), ("2.01", "2.01"), ("60.97", "60.97"), ("0.019", "0.01"),
    ])
    def test_the_floor(self, held, asked):
        assert floor_contracts_fp(held) == asked

    @pytest.mark.parametrize("held", ["0.009", "0.00", "-3", "eight", "NaN"])
    def test_an_unaskable_holding_is_none_never_zero(self, held):
        assert floor_contracts_fp(held) is None

    async def test_the_create_body_carries_contracts_fp_and_no_dollar_target(self, build):
        app, fake, _, position_id, _ = build(venue=FakeVenue(held_fp="8.226"))
        assert (await _ask(app, position_id)).status_code == 200
        body = fake.bodies[0]
        assert body["contracts_fp"] == "8.22"
        assert "target_cost_dollars" not in body and "contracts" not in body
        assert body["mve_selected_legs"] == LEGS
        assert body["mve_collection_ticker"] == COLLECTION
        assert body["rest_remainder"] is False

    async def test_a_holding_under_a_hundredth_refuses_before_any_write(self, build):
        app, fake, _, position_id, _ = build(venue=FakeVenue(held_fp="0.004"))
        response = await _ask(app, position_id)
        assert response.status_code == 409
        assert "create" not in fake.calls


class TestTheWatchLoopNeverAsks:
    """Defect 2: `hedge_watch` runs `build_payload` every 60 s unattended.
    An RFQ from there is ~1,440 a day on the order path's write budget."""

    def test_hedge_watch_names_no_rfq_function(self):
        source = (REPO / "backend" / "hedge_watch.py").read_text(encoding="utf-8")
        for name in ("ask_makers_to_buy_back", "create_rfq", "sell-quote", "combo_rfq"):
            assert name not in source, f"hedge_watch.py references {name}"

    def test_build_payload_names_no_rfq_function(self):
        source = (REPO / "backend" / "hedge.py").read_text(encoding="utf-8")
        assert "ask_makers_to_buy_back" not in source
        assert "create_rfq" not in source


class TestTheAskUsesTheSharedClient:
    """Defect 3: the RFQ write goes through `create_app`'s one Kalshi client,
    the same object (and limiter) the order path and buy-side RFQ use."""

    async def test_every_venue_call_went_to_the_one_client(self, build):
        app, fake, _, position_id, made = build()
        await _ask(app, position_id)
        await _ask(app, position_id)
        assert made == [fake], "a second client was built for the exit ask"
        assert fake.calls.count("create") == 2

    def test_routes_hands_the_hedge_router_combo_api(self):
        source = (REPO / "backend" / "api" / "routes.py").read_text(encoding="utf-8")
        start = source.index("hedge_router.register(")
        assert "combo_api=combo_api" in source[start:start + 400]


class TestTheRoute:
    async def test_it_needs_auth(self, build):
        app, fake, _, position_id, _ = build()
        assert (await _ask(app, position_id, headers={})).status_code in (401, 403)
        assert fake.calls == []

    async def test_an_unknown_ticket_is_404_and_asks_nothing(self, build):
        app, fake, _, _, _ = build()
        assert (await _ask(app, 999)).status_code == 404
        assert fake.calls == []

    async def test_a_hand_recorded_slip_is_refused_before_the_venue(self, build):
        app, fake, _, position_id, _ = build(combo_ticker=None, source="sportsbook")
        response = await _ask(app, position_id)
        assert response.status_code == 409
        assert "recorded by hand" in response.json()["detail"]
        assert fake.calls == []

    async def test_a_combination_not_held_at_the_venue_is_not_asked_about(self, build):
        app, fake, _, position_id, _ = build(venue=FakeVenue(held_fp=None))
        response = await _ask(app, position_id)
        assert response.status_code == 409
        # The reason, not just the status: the size floor would also refuse
        # a missing holding, with words that blame the size instead.
        assert "among your open positions" in response.json()["detail"]
        assert "create" not in fake.calls

    async def test_an_open_rfq_of_ours_is_a_409_not_a_reuse(self, build):
        app, fake, _, position_id, _ = build(venue=FakeVenue(conflict=True))
        response = await _ask(app, position_id)
        assert response.status_code == 409
        assert "already open" in response.json()["detail"]
        assert "delete" not in fake.calls and "read" not in fake.calls

    async def test_quotes_are_read_before_the_rfq_is_withdrawn(self, build):
        app, fake, _, position_id, _ = build()
        await _ask(app, position_id)
        assert fake.calls[:3] == ["positions", "market", "create"]
        assert fake.calls[-1] == "delete"
        assert fake.calls.count("delete") == 1
        assert "read" in fake.calls[3:-1]

    async def test_the_answer_is_best_bid_first_and_says_it_does_not_sell(self, build):
        app, _, _, position_id, _ = build()
        body = (await _ask(app, position_id)).json()
        assert body["status"] == "bid"
        assert body["best_bid_tenths"] == 102
        assert [b["yes_bid_tenths"] for b in body["bids"]] == sorted(
            (b["yes_bid_tenths"] for b in body["bids"]), reverse=True
        )
        assert len(body["bids"]) == 8
        assert body["makers_answered"] == 17
        assert body["held_fp"] == "2.01" and body["asked_fp"] == "2.01"
        assert "does not sell" in body["words"]
        for word in ("rare", "usually", "often", "seldom", "common"):
            assert word not in body["words"].lower(), (
                f"'{word}' is a frequency claim (#60, #64)"
            )

    async def test_the_ask_and_every_quote_are_recorded_and_withdrawn(self, build):
        app, _, path, position_id, _ = build()
        await _ask(app, position_id)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            rfq = conn.execute("SELECT * FROM combo_rfqs").fetchone()
            assert rfq["purpose"] == "exit"
            assert rfq["contracts_fp_requested"] == "2.01"
            assert rfq["deleted_ms"] is not None
            assert rfq["status"] == "quoted"
            rows = conn.execute("SELECT * FROM combo_rfq_quotes").fetchall()
            assert len(rows) == 17
            assert sum(r["yes_ask_tenths"] is None for r in rows) == 2
        finally:
            conn.close()

    async def test_nobody_bidding_is_a_stated_outcome(self, build):
        quotes = [q for q in _captured_quotes() if q["yes_bid_dollars"] == "0.0000"]
        app, _, _, position_id, _ = build(venue=FakeVenue(quotes=quotes))
        body = (await _ask(app, position_id)).json()
        assert body["status"] == "no_bid"
        assert body["best_bid_display"] is None
        assert "none bid" in body["words"]


class TestTheAcceptPathRefusesAnExitQuote:
    """Nothing on the exit path sells, and the BUY accept must not take an
    exit ask's quote either -- it would read a NULL ask as a price."""

    async def test_accepting_an_exit_quote_is_refused_before_anything_is_sent(
        self, build
    ):
        app, fake, path, position_id, _ = build()
        await _ask(app, position_id)
        calls_before = list(fake.calls)
        conn = sqlite3.connect(path)
        try:
            quote_id = conn.execute(
                "SELECT quote_id FROM combo_rfq_quotes "
                "WHERE yes_ask_tenths IS NOT NULL LIMIT 1"
            ).fetchone()[0]
        finally:
            conn.close()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            response = await c.post(
                "/api/parlays/rfq/accept",
                json={"rfq_id": RFQ_ID, "quote_id": quote_id},
                headers=HEADERS,
            )
        assert response.status_code == 409
        assert "does not sell" in response.json()["detail"]
        assert fake.calls == calls_before, "the accept reached the venue"
        conn = sqlite3.connect(path)
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM combo_rfq_quotes WHERE accepted_ms IS NOT NULL"
            ).fetchone()[0] == 0, "an accept intent was written"
        finally:
            conn.close()


class TestTheSellOnlyQuoteIsStorable:
    """Defect 7: v56 rebuilds `combo_rfq_quotes` without the NOT NULLs, on a
    database that already exists -- the only case that matters."""

    def _v55_database(self, tmp_path):
        path = tmp_path / "v55.db"
        conn = store.init_db(path)
        conn.execute(
            "INSERT INTO combo_rfq_quotes (rfq_id, quote_id, captured_ms, "
            "yes_ask_tenths, no_bid_tenths, yes_bid_tenths, contracts) "
            "VALUES ('rfq-old', 'q-old', 1, 593, 407, 60, 8.19)"
        )
        for table, column, _ in store._MIGRATIONS[56].columns:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        for statement in store._MIGRATIONS[56].undo_statements:
            conn.execute(statement)
        store._set_meta(conn, "schema_version", "55")
        conn.commit()
        conn.close()
        return path

    def test_the_v55_shape_really_refuses_a_sell_only_quote(self, tmp_path):
        conn = sqlite3.connect(self._v55_database(tmp_path))
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO combo_rfq_quotes (rfq_id, quote_id, captured_ms, "
                    "yes_bid_tenths) VALUES ('r', 'q', 1, 102)"
                )
        finally:
            conn.close()

    def test_migrating_admits_it_and_keeps_the_old_row(self, tmp_path):
        conn = store.init_db(self._v55_database(tmp_path))
        try:
            old = conn.execute(
                "SELECT * FROM combo_rfq_quotes WHERE quote_id = 'q-old'"
            ).fetchone()
            assert old is not None, "the rebuild dropped an existing quote"
            assert (old["yes_ask_tenths"], old["no_bid_tenths"],
                    old["yes_bid_tenths"]) == (593, 407, 60)
            assert old["yes_bid_contracts"] is None, "backfilled a size nobody read"
            conn.execute(
                "INSERT INTO combo_rfq_quotes (rfq_id, quote_id, captured_ms, "
                "yes_bid_tenths, yes_bid_contracts) VALUES ('r', 'q', 1, 102, 2.0)"
            )
            conn.commit()
        finally:
            conn.close()

    def test_the_other_constraints_survive_the_rebuild(self, tmp_path):
        conn = store.init_db(self._v55_database(tmp_path))
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO combo_rfq_quotes (rfq_id, quote_id, captured_ms) "
                    "VALUES ('rfq-old', 'q-old', 2)"
                )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO combo_rfqs (rfq_id, requested_ms, ticker, "
                    "collection_ticker, selected_legs, exchange_index, status, "
                    "purpose) VALUES ('x', 1, 'T', 'C', '[]', 1, 'asked', 'sell')"
                )
        finally:
            conn.close()
