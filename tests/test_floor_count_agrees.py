"""/ledger and /gate must report one floor count, from one population (#230).

`/api/ledger` called `clustered_clv(conn)` with no population, so its
`clv_scored` pooled every scored game (1038 against 300 on live) while the Gate
counted only actionable games (57 against 300). The Evidence page then said
"the gate stays locked until this clears" beside a number the gate does not use.

**What this establishes:** on one fixture DB holding scored games in both the
actionable and the refused population, the two endpoints report the same game
count and the same floor.

**What it does not establish:** anything about whether either number is large
enough, or about the gate's own predicate (owned by `backend/gate.py`).
"""

from __future__ import annotations

import re

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.gate import DEFAULT_HORIZON_HOURS
from backend.store import db

# game -> (rows, suppressed_reason, reference_contracts)
_GAMES = {
    "odds-A": (3, None, 5),  # actionable
    "odds-B": (2, None, 5),  # actionable
    "odds-C": (4, "no_edge", 5),  # refused
    "odds-D": (2, None, 0),  # unsized, not a bet
}
_ACTIONABLE_GAMES = 2


async def _get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return (await c.get(path)).json()


@pytest.fixture
def app(tmp_path):
    path = tmp_path / "floor.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    for i, (game, (n, reason, ref)) in enumerate(_GAMES.items(), start=1):
        event = f"KXTEST-EVENT-{game}"
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms) "
            "VALUES (?, 1000, 1000)",
            (event,),
        )
        conn.execute(
            "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
            "league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, ?, ?, 'baseball_mlb', 'exact_alias_pair', 0, 1000)",
            (i, event, game),
        )
        for k in range(n):
            ticker = f"KXTEST-{game}-{k}"
            conn.execute(
                "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
                "VALUES (?, 1000, 1000)",
                (ticker,),
            )
            conn.execute(
                "INSERT INTO recommendations (created_ms, strategy_config_version, "
                "ticker, link_id, side, entry_ask_tenths, fair_probability, "
                "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
                "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
                "odds_age_ms, reason_text, suppressed_reason, clv_scored_ms, "
                "clv_tenths, clv_horizon_hours) "
                "VALUES (1000, 1, ?, ?, 'yes', 500, 0.52, 5.0, 0.1, 0.2, 0.01, 0, "
                "?, 1000, 2000, 'test row', ?, 2000, ?, ?)",
                (ticker, i, ref, reason, 10 + k, DEFAULT_HORIZON_HOURS),
            )
    conn.commit()
    conn.close()
    return create_app(AppConfig(instance_mode="demo", db_path=path))


def _gate_floor(gate: dict) -> tuple[int, int]:
    detail = next(
        c["detail"] for c in gate["conditions"] if c["name"] == "scored_recommendations"
    )
    m = re.match(r"(\d+) of (\d+) independent actionable games", detail)
    assert m, detail
    return int(m.group(1)), int(m.group(2))


class TestOneFloorCount:
    async def test_the_fixture_really_separates_the_populations(self, app):
        """Baseline: pooled and actionable differ, or the test is vacuous."""
        gate = await _get(app, "/api/gate")
        assert _gate_floor(gate)[0] == _ACTIONABLE_GAMES
        assert len(_GAMES) > _ACTIONABLE_GAMES

    async def test_ledger_and_gate_report_the_same_game_count(self, app):
        gate_games, gate_floor = _gate_floor(await _get(app, "/api/gate"))
        ledger = await _get(app, "/api/ledger")
        assert ledger["clv_scored"] == gate_games
        assert ledger["clv_required"] == gate_floor

    async def test_ledger_rows_are_the_actionable_rows_too(self, app):
        ledger = await _get(app, "/api/ledger")
        assert ledger["clv_scored_rows"] == 3 + 2
