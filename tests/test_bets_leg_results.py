"""Your bets: each settled combination leg shows its own result (#294).

WHAT THIS ESTABLISHES
----------------------
(i)   Every leg of a readable combination carries a `result` key, in one
      vocabulary (won / lost / void, None for unread), whichever source
      supplied it: the desk's own `parlay_position_legs.outcome` or
      `kalshi_markets.result` (written once by the market-result pass).
(ii)  Reading is local: `bets_record` takes a sqlite connection and nothing
      else, so a page load cannot re-read Kalshi, and a second read writes
      nothing.
(iii) A leg whose market result was never read is None, never "lost".
(iv)  The page renders every leg through one element with one style; neither
      payload nor page carries a losing-leg highlight or a tally.

Leg tickers come from the captured `tests/fixtures/combo_lookup_response.json`;
no account data is used.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- That `kalshi_markets` holds a result for every leg of every historical
  combination: it holds one only for markets discovery saw and the result
  pass finalized. Others render "result not read".
- Rendering in a browser.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from backend import bets, hedge
from backend.store import db

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "combo_lookup_response.json").read_text(
        encoding="utf-8"
    )
)
COMBO = FIXTURE["market"]["ticker"]
LEGS = FIXTURE["market"]["mve_selected_legs"]
PAGE = (ROOT / "frontend" / "src" / "app" / "bets" / "page.tsx").read_text(
    encoding="utf-8"
).replace("\r\n", "\n")


def _settle(conn):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'E', 'no', 1000, 'yes', 2.0, "
        "400, 20, NULL)",
        (COMBO,),
    )
    conn.commit()


def _lookup(conn):
    blob = [
        {"event_ticker": g["event_ticker"], "market_ticker": g["market_ticker"],
         "side": g["side"], "label": f"leg {i}"}
        for i, g in enumerate(LEGS)
    ]
    conn.execute(
        "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
        "selected_legs, status, minted_market_ticker) "
        "VALUES (1, 'safe', 100, ?, 'priced', ?)",
        (json.dumps(blob), COMBO),
    )
    conn.commit()


def _market(conn, ticker, result):
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, result, first_seen_ms, "
        "last_seen_ms) VALUES (?, ?, 1, 1)",
        (ticker, result),
    )
    conn.commit()


def _legs(conn):
    bet = next(b for b in bets.bets_record(conn)["bets"] if b["ticker"] == COMBO)
    return bet["legs"]


class TestLegResultsAreShownAlike:
    def test_every_leg_result_is_shown_alike_and_read_once(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn)
        _lookup(conn)
        # One leg's market finalized yes, one no; both legs were bought YES.
        _market(conn, LEGS[0]["market_ticker"], "yes")
        _market(conn, LEGS[1]["market_ticker"], "no")
        legs = _legs(conn)
        assert [leg["result"] for leg in legs] == ["won", "lost"]
        # Same keys on every leg: nothing singles one out in the payload.
        assert len({tuple(sorted(leg)) for leg in legs}) == 1
        # Read once: a second page load issues no write and changes nothing.
        before = conn.total_changes
        assert _legs(conn) == legs
        assert conn.total_changes == before
        # The reader has no venue client: its only I/O handle is sqlite.
        assert list(inspect.signature(bets.bets_record).parameters) == [
            "conn", "limit",
        ]
        # The page draws every leg through one element with one style.
        assert PAGE.count("data-leg-result>") == 1
        assert "legResultWord(leg.result)" in PAGE
        row = PAGE[PAGE.index("data-leg-results"):]
        row = row[: row.index('bet.kind === "single"')]
        assert not re.search(r"text-(negative|positive)|leg\.result ===", row)

    def test_an_unread_leg_is_none_not_lost(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn)
        _lookup(conn)
        _market(conn, LEGS[0]["market_ticker"], "no")
        legs = _legs(conn)
        assert legs[0]["result"] == "lost"
        assert legs[1]["result"] is None  # never discovered

    def test_a_recorded_position_outcome_wins_and_can_be_void(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _settle(conn)
        hedge.record_position(
            conn, now_ms=5, source="kalshi_combo", label="mine",
            stake_tenths=1000, return_tenths=4000, combo_ticker=COMBO,
            legs=[
                {"ticker": g["market_ticker"], "side": g["side"],
                 "label": f"leg {i}", "event_ticker": g["event_ticker"]}
                for i, g in enumerate(LEGS)
            ],
        )
        leg_id = conn.execute(
            "SELECT id FROM parlay_position_legs ORDER BY leg_index LIMIT 1"
        ).fetchone()["id"]
        hedge.resolve_leg(
            conn, leg_id=leg_id, outcome="void", now_ms=9, source="manual"
        )
        # The market table says "yes"; the recorded void is what shows.
        _market(conn, LEGS[0]["market_ticker"], "yes")
        legs = _legs(conn)
        assert legs[0]["result"] == "void"
        assert legs[1]["result"] is None

    def test_leg_result_is_side_aware(self):
        assert bets.leg_result(None, "no", "no") == "won"
        assert bets.leg_result(None, "yes", "no") == "lost"
        assert bets.leg_result(None, "", "yes") is None
        assert bets.leg_result(None, "yes", None) is None
