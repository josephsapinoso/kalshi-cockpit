"""A settled card-built combination carries its card's "drop this if" line.

Joe, 2026-10-03: the review of his game-script parlays could not say whether
a card's warning came true, because `/api/game-cards` serves upcoming cards
only. `/api/bets` now carries, per combination row, the card stamped with its
ticker: the drop-if words and the T-2h re-check, nothing scored.

Synthetic tickers and words.

What this does NOT establish: whether the drop-if happened -- the re-check is
one search, and `not_found` is not a confirmation. The row shows what the card
said and what the check found; it grades nothing.
"""

from __future__ import annotations

from pathlib import Path

from backend import bets
from backend.store import db, game_script_cards

REPO = Path(__file__).resolve().parents[1]
COMBO = "KXMVESYNTHETIC-SHARD1-S0000000000000000-CARDCARDCAR"
OTHER = "KXMVESYNTHETIC-SHARD1-S0000000000000000-NOCARDNOCAR"
NOW = 1_700_000_000_000


def _settle(conn, ticker, n):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'KXSYNTH', 'no', ?, 'yes', 1.0, 200, 0, NULL)",
        (ticker, 1_000 + n),
    )


def _card(conn, *, combo, drop_if, built_ms, recheck=None):
    card_id = game_script_cards.insert_card(
        conn, game_event_ticker="KXNFLGAME-26JAN01AAABBB", sport_key="nfl",
        kickoff_ms=NOW, built_ms=built_ms, status="built", story="A slow game.",
        legs=[{"market_ticker": "KXNFLTOTAL-26JAN01AAABBB-40", "side": "no"}],
        drop_if=drop_if,
    )
    conn.execute(
        "UPDATE game_script_cards SET combo_ticker = ?, recheck_status = ?, "
        "recheck_ms = ? WHERE id = ?",
        (combo, recheck, NOW if recheck else None, card_id),
    )
    conn.commit()


def _rows(conn):
    return {b["ticker"]: b for b in bets.bets_record(conn)["bets"]}


class TestTheCardRidesOnTheRow:
    def test_a_stamped_combo_carries_its_drop_if_and_recheck(self, tmp_path):
        conn = db.init_db(tmp_path / "c.db")
        _settle(conn, COMBO, 0)
        _settle(conn, OTHER, 1)
        _card(conn, combo=COMBO, drop_if="The starting QB is ruled out.",
              built_ms=NOW, recheck="not_found")
        rows = _rows(conn)
        assert rows[COMBO]["card"] == {
            "drop_if": "The starting QB is ruled out.",
            "recheck_status": "not_found",
            "recheck_note": None,
        }
        assert rows[OTHER]["card"] is None

    def test_the_newest_card_wins_when_a_ticker_was_stamped_twice(self, tmp_path):
        conn = db.init_db(tmp_path / "c.db")
        _settle(conn, COMBO, 0)
        _card(conn, combo=COMBO, drop_if="old words", built_ms=NOW)
        _card(conn, combo=COMBO, drop_if="new words", built_ms=NOW + 1)
        assert _rows(conn)[COMBO]["card"]["drop_if"] == "new words"

    def test_the_screen_never_grades_the_card(self):
        page = (REPO / "frontend" / "src" / "app" / "bets" / "page.tsx").read_text(
            encoding="utf-8"
        )
        block = page.split("function CardWarning", 1)[1].split("\nfunction ", 1)[0]
        for word in ("correct", "right", "wrong", "accurate", "score"):
            assert word not in block.lower(), word
