"""#422 / ADR 0193 Amendment 1: who a tailed pick came from, per name.

Names here are invented ("sharp_a"); no operator data enters the repo.
"""

from __future__ import annotations

import httpx
import pytest

from backend import bets, pick_sources
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

COMBO = "KXMVESYNTHETIC-SHARD1-S0000000000000000-AAAAAAAAAAA"
SINGLE = "KXSYNTHGAME-26JAN010000AAABBB-AAA"
HEADERS = {"Authorization": "Bearer secret-token"}


def _settle(conn, ticker, *, price, won, n):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'KXSYNTH', ?, ?, 'yes', 1.0, ?, 0, NULL)",
        (ticker, "yes" if won else "no", 1_000 + n, price),
    )


def _tag(conn, ticker, source, name=None, now=1_700_000_000_000):
    pick_sources.set_pick_source(
        conn, ticker=ticker, source=source, now_ms=now, tailed_from=name
    )


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "t.db")
    yield c
    c.close()


class TestANameIsHisWordAndOnlyOnATailedPick:
    def test_a_tailed_name_is_refused_on_any_other_source(self, conn):
        for source in pick_sources.PICK_SOURCES:
            if source == "friend":
                continue
            with pytest.raises(pick_sources.PickSourceRefused):
                _tag(conn, COMBO, source, "sharp_a")
        assert pick_sources.pick_sources_for(conn, [COMBO]) == {}
        _tag(conn, COMBO, "friend", "sharp_a")
        assert pick_sources.tailed_from_for(conn, [COMBO]) == {COMBO: "sharp_a"}

    def test_changing_the_tag_away_from_tailed_clears_the_name(self, conn):
        _tag(conn, COMBO, "friend", "sharp_a")
        _tag(conn, COMBO, "chat")
        assert pick_sources.tailed_from_for(conn, [COMBO]) == {}
        assert pick_sources.tailed_names(conn) == []

    def test_a_name_is_trimmed_blank_is_none_and_long_is_refused(self, conn):
        _tag(conn, COMBO, "friend", "  sharp_a  ")
        assert pick_sources.tailed_from_for(conn, [COMBO]) == {COMBO: "sharp_a"}
        _tag(conn, COMBO, "friend", "   ")
        assert pick_sources.tailed_from_for(conn, [COMBO]) == {}
        assert pick_sources.pick_sources_for(conn, [COMBO]) == {COMBO: "friend"}
        _tag(conn, COMBO, "friend", "x" * 40)
        with pytest.raises(pick_sources.PickSourceRefused):
            _tag(conn, COMBO, "friend", "x" * 41)

    def test_the_label_is_tailed_pick_and_the_key_stays_friend(self):
        assert pick_sources.PICK_SOURCE_LABELS["friend"] == "Tailed pick"
        assert "friend" in pick_sources.PICK_SOURCES


class TestNamesAreListedInFirstUsedOrder:
    def test_tailed_names_are_listed_in_first_used_order_never_by_result(self, conn):
        # sharp_b is used first and LOSES everything; sharp_a is used later
        # and wins everything. Alphabetical or by-result order would put
        # sharp_a first; first-used puts sharp_b first.
        n = 0
        for name, won, now in (("sharp_b", False, 100), ("sharp_a", True, 200)):
            for _ in range(3):
                ticker = f"{COMBO}-{n}"
                _settle(conn, ticker, price=500, won=won, n=n)
                _tag(conn, ticker, "friend", name, now=now + n)
                n += 1
        conn.commit()
        assert pick_sources.tailed_names(conn) == ["sharp_b", "sharp_a"]
        record = bets.bets_record(conn)
        assert record["pick_sources"]["tailed_names"] == ["sharp_b", "sharp_a"]
        (friend,) = record["by_source"]["combo"]
        assert [e["name"] for e in friend["by_name"]] == ["sharp_b", "sharp_a"]

    def test_names_match_case_folded_and_the_first_spelling_wins(self, conn):
        _tag(conn, f"{COMBO}-0", "friend", "Sharp_A", now=100)
        _tag(conn, f"{COMBO}-1", "friend", "sharp_a", now=200)
        assert pick_sources.tailed_names(conn) == ["Sharp_A"]
        _settle(conn, f"{COMBO}-0", price=500, won=True, n=0)
        _settle(conn, f"{COMBO}-1", price=500, won=False, n=1)
        conn.commit()
        (friend,) = bets.bets_record(conn)["by_source"]["combo"]
        (line,) = friend["by_name"]
        assert (line["name"], line["wins"], line["losses"]) == ("Sharp_A", 1, 1)

    def test_a_tailed_pick_with_no_name_gets_a_last_no_name_line(self, conn):
        _settle(conn, f"{COMBO}-0", price=500, won=True, n=0)
        _settle(conn, f"{COMBO}-1", price=500, won=False, n=1)
        _tag(conn, f"{COMBO}-0", "friend")
        _tag(conn, f"{COMBO}-1", "friend", "sharp_a")
        conn.commit()
        (friend,) = bets.bets_record(conn)["by_source"]["combo"]
        assert [e["name"] for e in friend["by_name"]] == ["sharp_a", None]
        # Other sources carry no by_name.
        _settle(conn, f"{COMBO}-2", price=500, won=True, n=2)
        _tag(conn, f"{COMBO}-2", "own")
        conn.commit()
        blocks = bets.bets_record(conn)["by_source"]["combo"]
        assert "by_name" not in next(b for b in blocks if b["source"] == "own")


class TestAPerNameLineIsTheSourceLineOneLevelDown:
    def test_a_sharp_below_the_floor_prints_counts_without_a_rate(self, conn):
        # Combos: 4 bets at 25% -> 1 expected win, far under 5 each side.
        for i in range(4):
            _settle(conn, f"{COMBO}-{i}", price=250, won=i == 0, n=i)
            _tag(conn, f"{COMBO}-{i}", "friend", "sharp_a")
        # Singles: below SINGLES_SUMMARY_FLOOR -> counts only, no expected.
        for i in range(3):
            _settle(conn, f"{SINGLE}-{i}", price=500, won=True, n=10 + i)
            _tag(conn, f"{SINGLE}-{i}", "friend", "sharp_a")
        conn.commit()
        by_source = bets.bets_record(conn)["by_source"]
        (combo_line,) = by_source["combo"][0]["by_name"]
        assert (combo_line["wins"], combo_line["losses"]) == (1, 3)
        assert combo_line["expected"]["too_few"] is True
        assert combo_line["expected"]["range_low"] is None
        assert combo_line["expected"]["range_high"] is None
        (single_line,) = by_source["single"][0]["by_name"]
        assert single_line["expected"] is None
        assert single_line["wins"] == 3

    def test_a_name_with_enough_expected_each_side_gets_a_range(self, conn):
        for i in range(20):
            _settle(conn, f"{COMBO}-{i}", price=500, won=i % 2 == 0, n=i)
            _tag(conn, f"{COMBO}-{i}", "friend", "sharp_a")
        conn.commit()
        (line,) = bets.bets_record(conn)["by_source"]["combo"][0]["by_name"]
        assert line["expected"]["too_few"] is False
        assert line["expected"]["range_low"] is not None

    def test_name_lines_are_counted_in_the_range_count(self, conn):
        for i in range(20):
            _settle(conn, f"{COMBO}-{i}", price=500, won=i % 2 == 0, n=i)
            _tag(conn, f"{COMBO}-{i}", "friend", "sharp_a")
        conn.commit()
        record = bets.bets_record(conn)
        with_names = bets.count_ranges(record)
        for block in record["by_source"]["combo"]:
            block.pop("by_name", None)
        assert with_names == bets.count_ranges(record) + 1


class TestTheRoutePassesTheName:
    async def _post(self, app, body):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.post("/api/pick-sources", json=body, headers=HEADERS)

    async def test_the_route_stores_and_refuses_names(self, tmp_path):
        path = tmp_path / "r.db"
        db.init_db(path).close()
        app = create_app(
            AppConfig(instance_mode="live", auth_token="secret-token", db_path=path)
        )
        ok = await self._post(
            app, {"ticker": COMBO, "source": "friend", "tailed_from": " sharp_a "}
        )
        assert ok.status_code == 200 and ok.json()["tailed_from"] == "sharp_a"
        bad = await self._post(
            app, {"ticker": COMBO, "source": "own", "tailed_from": "sharp_a"}
        )
        assert bad.status_code == 422
        long_ = await self._post(
            app, {"ticker": COMBO, "source": "friend", "tailed_from": "x" * 41}
        )
        assert long_.status_code == 422
        c = db.open_db(path)
        try:
            assert pick_sources.tailed_names(c) == ["sharp_a"]
        finally:
            c.close()
