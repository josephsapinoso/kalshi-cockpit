"""v63: Joe's one-tap tag for where a pick came from, and the per-source line.

Every fixture is synthetic (round invented prices on made-up tickers);
nothing is, or may be, copied from the operator's record.

What this establishes
---------------------
- A tag is stored only by his tap, cleared by a None, and refused when it is
  not one of the six sources. An untagged settled bet is `untagged`, never
  `own`.
- The per-source summary keeps the kinds apart, lists sources in the fixed
  order whatever the results, and gives a source with fewer than 5 expected
  wins or losses no range.
- Suggestions come only from a card stamp or a preset label, never from
  anything else, and a suggestion is never stored.
- The write route is auth-gated and touches only `pick_sources`.

What it does NOT establish
--------------------------
That a tag is true (it is his word after the fact), or that any source is
better than another: the line is the price-paid expectation and nothing more.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest

from backend import bets, pick_sources
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "backend" / "api" / "routers" / "ledger.py"
HEADERS = {"Authorization": "Bearer secret-token"}
NOW = 1_700_000_000_000

COMBO = "KXMVESYNTHETIC-SHARD1-S0000000000000000-AAAAAAAAAAA"
SINGLE = "KXSYNTHGAME-26JAN010000AAABBB-AAA"


def _settle(conn, ticker, *, price, won, n):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'KXSYNTH', ?, ?, 'yes', 1.0, ?, 0, NULL)",
        (ticker, "yes" if won else "no", 1_000 + n, price),
    )


def _tag(conn, ticker, source):
    pick_sources.set_pick_source(conn, ticker=ticker, source=source, now_ms=NOW)


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "p.db")
    yield c
    c.close()


class TestTheTagIsHisTapAndNothingElse:
    def test_untagged_is_null_not_own(self, conn):
        _settle(conn, f"{COMBO}-0", price=250, won=False, n=0)
        conn.commit()
        record = bets.bets_record(conn)
        assert record["bets"][0]["pick_source"] is None
        combo = record["by_source"]["combo"]
        assert [b["source"] for b in combo] == ["untagged"]
        assert record["pick_sources"]["tagged"] == {}

    def test_a_tap_stores_and_a_none_clears(self, conn):
        _tag(conn, COMBO, "friend")
        assert pick_sources.pick_sources_for(conn, [COMBO]) == {COMBO: "friend"}
        _tag(conn, COMBO, "chat")
        assert pick_sources.pick_sources_for(conn, [COMBO]) == {COMBO: "chat"}
        _tag(conn, COMBO, None)
        assert pick_sources.pick_sources_for(conn, [COMBO]) == {}

    def test_an_unknown_source_is_refused(self, conn):
        with pytest.raises(pick_sources.PickSourceRefused):
            _tag(conn, COMBO, "hunch")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pick_sources VALUES (?, 'hunch', ?)", (COMBO, NOW)
            )

    def test_suggestions_come_only_from_a_card_stamp_or_a_preset(self, conn):
        rows = {"P1": "safe", "P2": "checked", "P3": "game", "P4": "totals"}
        for i, (ticker, label) in enumerate(rows.items()):
            conn.execute(
                "INSERT INTO parlay_positions (source, label, stake_tenths, "
                "return_tenths, created_ms, combo_ticker, status) "
                "VALUES ('kalshi_combo', ?, 100, 1000, ?, ?, 'open')",
                (label, NOW + i, ticker),
            )
        conn.commit()
        assert pick_sources.suggested_sources(conn, list(rows)) == {
            "P1": "preset", "P4": "preset",
        }
        payload = pick_sources.pick_source_payload(
            conn, list(rows) + pick_sources.open_combo_tickers(conn)
        )
        # A suggestion is served, never stored.
        assert payload["tagged"] == {}
        assert set(payload["suggested"]) == {"P1", "P4"}


class TestTheBySourceLine:
    def test_a_source_with_too_few_expected_shows_no_range(self, conn):
        for i in range(4):
            ticker = f"{COMBO}-{i}"
            _settle(conn, ticker, price=250, won=i == 0, n=i)
            _tag(conn, ticker, "card")
        conn.commit()
        (card,) = bets.bets_record(conn)["by_source"]["combo"]
        assert (card["source"], card["wins"], card["losses"]) == ("card", 1, 3)
        assert card["expected"]["too_few"] is True
        assert card["expected"]["range_low"] is None

    def test_source_rows_are_not_ordered_by_result(self, conn):
        # `own` wins everything and `card` loses everything; the order is
        # still the fixed one, card before own.
        n = 0
        for source, won in (("own", True), ("card", False)):
            for _ in range(3):
                ticker = f"{COMBO}-{n}"
                _settle(conn, ticker, price=500, won=won, n=n)
                _tag(conn, ticker, source)
                n += 1
        conn.commit()
        combo = bets.bets_record(conn)["by_source"]["combo"]
        assert [b["source"] for b in combo] == ["card", "own"]

    def test_the_kinds_are_never_pooled_and_singles_wait_for_the_floor(self, conn):
        _settle(conn, f"{COMBO}-0", price=250, won=True, n=0)
        _settle(conn, f"{SINGLE}-0", price=500, won=True, n=1)
        _tag(conn, f"{COMBO}-0", "preset")
        _tag(conn, f"{SINGLE}-0", "preset")
        conn.commit()
        by_source = bets.bets_record(conn)["by_source"]
        assert set(by_source) == {"single", "combo"}
        assert by_source["combo"][0]["expected"] is not None
        assert by_source["single"][0]["expected"] is None


class TestTheWriteRoute:
    async def _post(self, app, body, headers=HEADERS):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.post("/api/pick-sources", json=body, headers=headers)

    def _app(self, tmp_path):
        path = tmp_path / "r.db"
        db.init_db(path).close()
        app = create_app(
            AppConfig(instance_mode="live", auth_token="secret-token", db_path=path)
        )
        return app, path

    async def test_it_stores_with_auth_and_refuses_without(self, tmp_path):
        app, path = self._app(tmp_path)
        refused = await self._post(app, {"ticker": COMBO, "source": "chat"}, headers={})
        assert refused.status_code == 401
        ok = await self._post(app, {"ticker": COMBO, "source": "chat"})
        assert ok.status_code == 200
        bad = await self._post(app, {"ticker": COMBO, "source": "hunch"})
        assert bad.status_code == 422
        conn = sqlite3.connect(path)
        try:
            assert conn.execute("SELECT source FROM pick_sources").fetchall() == [("chat",)]
        finally:
            conn.close()

    def test_tagging_never_touches_the_money_path(self):
        source = (REPO / "backend" / "pick_sources.py").read_text(encoding="utf-8")
        for table in ("manual_orders", "combo_rfq", "fills", "orders"):
            assert f"INTO {table}" not in source
            assert f"UPDATE {table}" not in source
        handler = LEDGER.read_text(encoding="utf-8").split(
            '"/api/pick-sources"', 1
        )[1].split("@app.get", 1)[0]
        # The code only, past the handler's docstring (which names the paths
        # it does not touch).
        handler = handler.split('"""', 2)[2]
        assert "set_pick_source" in handler
        for word in ("manual_order", "rfq", "hedge", "positions."):
            assert word not in handler
