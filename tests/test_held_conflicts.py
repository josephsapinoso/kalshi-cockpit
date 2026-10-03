"""A combination about to be bought is checked against tickets already held.

Joe's 2026-10-03 choice after three of his tickets bet against each other.
Synthetic tickers and labels; nothing from the operator's record.

What this establishes
---------------------
- The same market on the other side is flagged (`opposite_side`).
- Two different teams to win the same full game are flagged (`other_winner`);
  a first-half winner (it has a tie) and a NO leg are not.
- A different market family (win beside cover, win beside a total) is NOT
  flagged -- whether they clash depends on the score.
- Settled positions, resolved legs and the combination's own position are
  ignored; an unrecorded combination answers `checked: false`, not "clean".
- The route serves the payload, and no spend path imports the module.

What it does NOT establish: that a held position is still live at the venue.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from backend import held_conflicts
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

REPO = Path(__file__).resolve().parents[1]
NOW = 1_700_000_000_000
COMBO = "KXMVESYNTH-S0000000000000000-NEW"

PSU = "KXNCAAFSPREAD-26JAN01PSUNW-PSU3"
TOTAL = "KXNCAAFTOTAL-26JAN01PITTVT-55"
NW_WIN = "KXNCAAFGAME-26JAN01PSUNW-NW"
PSU_WIN = "KXNCAAFGAME-26JAN01PSUNW-PSU"
NW_1H = "KXNCAAF1H-26JAN01PSUNW-NW"
PSU_1H = "KXNCAAF1H-26JAN01PSUNW-PSU"


def _hold(conn, legs, *, status="open", combo="KXMVESYNTH-HELD", outcome="pending"):
    conn.execute(
        "INSERT INTO parlay_positions (source, label, stake_tenths, return_tenths, "
        "created_ms, combo_ticker, status) VALUES ('kalshi_combo', 'held', 100, 1000, ?, ?, ?)",
        (NOW, combo, status),
    )
    pid = conn.execute("SELECT max(id) FROM parlay_positions").fetchone()[0]
    for i, (ticker, side) in enumerate(legs):
        resolved = None if outcome == "pending" else NOW
        source = None if outcome == "pending" else "manual"
        conn.execute(
            "INSERT INTO parlay_position_legs (position_id, leg_index, ticker, side, "
            "label, outcome, resolved_ms, resolved_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, i, ticker, side, f"held {ticker} {side}", outcome, resolved, source),
        )
    conn.commit()
    return pid


def _lookup(conn, legs, combo=COMBO):
    blob = json.dumps([
        {"market_ticker": t, "event_ticker": t.rsplit("-", 1)[0], "side": s,
         "label": f"new {t} {s}"}
        for t, s in legs
    ])
    conn.execute(
        "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
        "selected_legs, status, minted_market_ticker) VALUES (?, 'game', 100, ?, 'book_empty', ?)",
        (NOW, blob, combo),
    )
    conn.commit()


def _kinds(conn, combo=COMBO):
    return sorted(c["kind"] for c in held_conflicts.held_conflicts(conn, combo)["conflicts"])


def _conn(tmp_path):
    return db.init_db(tmp_path / "h.db")


class TestTheTwoExactClashes:
    def test_the_same_market_on_the_other_side(self, tmp_path):
        conn = _conn(tmp_path)
        _hold(conn, [(PSU, "yes"), (TOTAL, "no")])
        _lookup(conn, [(PSU, "no"), (TOTAL, "yes")])
        assert _kinds(conn) == ["opposite_side", "opposite_side"]

    def test_two_teams_to_win_the_same_game(self, tmp_path):
        conn = _conn(tmp_path)
        _hold(conn, [(PSU_WIN, "yes")])
        _lookup(conn, [(NW_WIN, "yes")])
        assert _kinds(conn) == ["other_winner"]

    def test_the_same_side_is_not_a_clash(self, tmp_path):
        conn = _conn(tmp_path)
        _hold(conn, [(PSU, "yes")])
        _lookup(conn, [(PSU, "yes")])
        assert _kinds(conn) == []


class TestNothingIsGuessed:
    def test_a_first_half_winner_has_a_tie_and_is_not_flagged(self, tmp_path):
        conn = _conn(tmp_path)
        _hold(conn, [(PSU_1H, "yes")])
        _lookup(conn, [(NW_1H, "yes")])
        assert _kinds(conn) == []

    def test_a_win_beside_the_other_teams_cover_is_not_flagged(self, tmp_path):
        conn = _conn(tmp_path)
        _hold(conn, [(PSU, "yes")])
        _lookup(conn, [(NW_WIN, "yes")])
        assert _kinds(conn) == []

    def test_a_no_on_one_team_beside_yes_on_the_other_is_not_flagged(self, tmp_path):
        conn = _conn(tmp_path)
        _hold(conn, [(PSU_WIN, "no")])
        _lookup(conn, [(NW_WIN, "yes")])
        assert _kinds(conn) == []

    def test_buying_no_on_the_other_team_agrees_with_holding_yes(self, tmp_path):
        # Holding Penn St. to win and buying "Northwestern does not win" can
        # both come in -- the same opinion twice, not a clash.
        conn = _conn(tmp_path)
        _hold(conn, [(PSU_WIN, "yes")])
        _lookup(conn, [(NW_WIN, "no")])
        assert _kinds(conn) == []

    def test_an_unrecorded_combination_is_unchecked_not_clean(self, tmp_path):
        conn = _conn(tmp_path)
        _hold(conn, [(PSU, "yes")])
        assert held_conflicts.held_conflicts(conn, COMBO) == {
            "checked": False, "conflicts": [],
        }


class TestOnlyLiveHoldingsCount:
    def test_settled_resolved_and_own_positions_are_ignored(self, tmp_path):
        conn = _conn(tmp_path)
        _hold(conn, [(PSU, "yes")], status="settled", combo="A")
        _hold(conn, [(PSU, "yes")], outcome="won", combo="B")
        _hold(conn, [(PSU, "yes")], combo=COMBO)
        _lookup(conn, [(PSU, "no")])
        assert _kinds(conn) == []


class TestTheRoute:
    async def test_it_serves_the_payload(self, tmp_path):
        path = tmp_path / "r.db"
        conn = db.init_db(path)
        _hold(conn, [(PSU, "yes")])
        _lookup(conn, [(PSU, "no")])
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            body = (await c.get("/api/held-conflicts", params={"ticker": COMBO})).json()
        assert body["checked"] is True
        assert [x["kind"] for x in body["conflicts"]] == ["opposite_side"]

    def test_no_spend_path_imports_it(self):
        for rel in ("backend/manual_order.py", "backend/combo_rfq.py",
                    "backend/store/manual_orders.py", "backend/positions.py"):
            path = REPO / rel
            if path.exists():
                assert "held_conflicts" not in path.read_text(encoding="utf-8"), rel
