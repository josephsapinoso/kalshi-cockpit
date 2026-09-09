"""`scripts/backfill_orphan_combo_position.py` writes one authorised row.

What these tests do not establish
---------------------------------
- **Not that the write is permitted to run.** Whether the live write executes
  is a permission-system and operator question. These tests exercise the
  script against a temporary database and never reach live.
- **Not that the row is correct as bookkeeping.** They establish that every
  figure comes from `parlay_lookups` and `manual_orders` rather than from a
  literal in the script, and that the script refuses every target it was not
  authorised to touch. Whether the position is really held is the venue's
  answer, not this script's.
- **Nothing about the registration's statistic.** The row is excluded from `R`
  and its sitting from `G` by Amendment 1; no test here counts anything.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "backfill_orphan_combo_position.py"
_SCHEMA = _ROOT / "backend" / "store" / "schema.sql"

TICKER = "KXMVECROSSCATEGORY-SHARD1-S2026FAD1B866580-EE12A337E52"
LEGS = [
    {"event_ticker": "KXMLBGAME-26SEP091845LAABOS",
     "market_ticker": "KXMLBGAME-26SEP091845LAABOS-BOS"},
    {"event_ticker": "KXMLBGAME-26SEP091905COLNYY",
     "market_ticker": "KXMLBGAME-26SEP091905COLNYY-NYY"},
    {"event_ticker": "KXMLBGAME-26SEP092210CINLAD",
     "market_ticker": "KXMLBGAME-26SEP092210CINLAD-LAD"},
]


def _run(db: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--db", str(db), *flags],
        capture_output=True, text=True, cwd=str(_ROOT),
    )


@pytest.fixture
def db(tmp_path) -> Path:
    """The live shape: a filled real combo order and the lookup that priced it."""
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO manual_orders (id, client_order_id, submitted_ms, ticker,"
        " side, action, count, max_price_tenths, p_yes_bp, status,"
        " request_body_json, dry_run)"
        " VALUES (4,'cid-4',1788966716378,?,'yes','buy',4,410,3390,'filled',"
        "'{}',0)",
        (TICKER,),
    )
    conn.execute(
        "INSERT INTO parlay_lookups (id, requested_ms, card_key, stake_cents,"
        " selected_legs, status, minted_market_ticker,"
        " derived_yes_ask_tenths, hold)"
        " VALUES (41,1788966684073,'safe',100,?,'priced',?,410,0.174)",
        (json.dumps(LEGS), TICKER),
    )
    conn.commit()
    conn.close()
    return path


def _positions(db: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM parlay_positions").fetchall()
    finally:
        conn.close()


class TestTheAuthorisedRowIsWritten:
    def test_a_dry_run_writes_nothing(self, db):
        result = _run(db, "--dry-run")
        assert result.returncode == 0, result.stderr
        assert _positions(db) == []

    def test_the_commit_writes_one_row_with_the_venues_own_arithmetic(self, db):
        """Stake and return are derived, never typed.

        4 contracts at 410 tenths is 1640, which is what `venue_positions`
        independently reports as `exposure_tenths` on live. The return is 4
        contracts at $1.00. Asserting the numbers rather than the row count is
        the distinguishing consequence: a row that appeared with the wrong
        stake would size a hedge wrongly and a count assertion would pass.
        """
        result = _run(db, "--commit")
        assert result.returncode == 0, result.stderr
        rows = _positions(db)
        assert len(rows) == 1
        assert rows[0]["stake_tenths"] == 1640
        assert rows[0]["return_tenths"] == 4000
        assert rows[0]["combo_ticker"] == TICKER
        assert rows[0]["parlay_lookup_id"] == 41
        assert rows[0]["source"] == "kalshi_combo"

    def test_all_three_legs_are_persisted(self, db):
        assert _run(db, "--commit").returncode == 0
        conn = sqlite3.connect(db)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM parlay_position_legs"
            ).fetchone()[0]
        finally:
            conn.close()
        assert n == 3

    def test_the_note_denies_that_the_wiring_wrote_it(self, db):
        """The provenance marker, which is the whole reason for the override.

        ADR 0125's wiring writes "Recorded automatically from the hand-bet
        path". On this row that sentence is false, and a false provenance
        marker inside an open observation window is what Amendment 1 exists to
        prevent. The note must deny Joe's authorship in terms, because the row
        is otherwise indistinguishable from one he made.
        """
        assert _run(db, "--commit").returncode == 0
        note = _positions(db)[0]["note"]
        assert "NOT an act of recording by Joe" in note
        assert "Amendment 1" in note
        assert "Recorded automatically from the hand-bet path" not in note


class TestEveryUnauthorisedTargetIsRefused:
    """A general backfill tool is not what was authorised.

    Each refusal is asserted by the state it leaves behind -- no row -- AND by
    a non-zero exit, because a script that returned 0 having written nothing
    would read as success to whoever runs it.
    """

    def test_a_second_run_refuses_rather_than_writing_a_second_holding(self, db):
        assert _run(db, "--commit").returncode == 0
        again = _run(db, "--commit")
        assert again.returncode != 0
        assert "already watches" in (again.stdout + again.stderr)
        assert len(_positions(db)) == 1

    def test_a_dry_run_order_is_refused(self, db):
        conn = sqlite3.connect(db)
        conn.execute("UPDATE manual_orders SET dry_run = 1 WHERE id = 4")
        conn.commit()
        conn.close()
        result = _run(db, "--commit")
        assert result.returncode != 0
        assert "dry run" in (result.stdout + result.stderr)
        assert _positions(db) == []

    def test_an_unfilled_order_is_refused(self, db):
        conn = sqlite3.connect(db)
        conn.execute("UPDATE manual_orders SET status = 'unfilled' WHERE id = 4")
        conn.commit()
        conn.close()
        result = _run(db, "--commit")
        assert result.returncode != 0
        assert _positions(db) == []

    def test_a_different_ticker_on_id_4_is_refused(self, db):
        """The database is not assumed to be the one the amendment describes."""
        conn = sqlite3.connect(db)
        conn.execute("UPDATE manual_orders SET ticker = 'KXMVE-OTHER' WHERE id = 4")
        conn.commit()
        conn.close()
        result = _run(db, "--commit")
        assert result.returncode != 0
        assert _positions(db) == []

    def test_a_lookup_that_never_priced_is_refused(self, db):
        """No priced lookup means the position cannot be built, not that it has no legs."""
        conn = sqlite3.connect(db)
        conn.execute("UPDATE parlay_lookups SET status = 'book_empty' WHERE id = 41")
        conn.commit()
        conn.close()
        result = _run(db, "--commit")
        assert result.returncode != 0
        assert "no priced" in (result.stdout + result.stderr)
        assert _positions(db) == []

    def test_an_unparsable_leg_list_aborts_rather_than_watching_a_partial_ticket(
        self, db
    ):
        """ADR 0125 refuses a partial leg list and this amendment does not relax it.

        A ticket watched with a leg missing would show the missing leg as
        incapable of losing, which is worse than not watching it at all.
        """
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE parlay_lookups SET selected_legs = ? WHERE id = 41",
            (json.dumps([{"event_ticker": "E"}]),),
        )
        conn.commit()
        conn.close()
        result = _run(db, "--commit")
        assert result.returncode != 0
        assert _positions(db) == []
