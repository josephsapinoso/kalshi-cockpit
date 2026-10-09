"""The manual-order ticket warns before a single bets against a held leg (#333).

What this establishes
---------------------
- `ManualTicket.tsx` mounts `HeldConflictsNote` for the ticket's market AND
  its chosen side, and imports it.
- The note asks `/api/held-conflicts` with the side, and names `same_side`.
- The order POST call expression is byte-identical to the one before #333
  (copied below before the file was edited): the warning is read-only and
  changes nothing about how an order is built or sent.

What it does NOT establish: that the warning renders in a browser; that a
conflict is found for any real ticker (that is `test_held_conflicts.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TICKET = (REPO / "frontend/src/components/ManualTicket.tsx").read_text(
    encoding="utf-8"
).replace("\r\n", "\n")
NOTE = (REPO / "frontend/src/components/HeldConflictsNote.tsx").read_text(
    encoding="utf-8"
).replace("\r\n", "\n")
API = (REPO / "frontend/src/lib/api.ts").read_text(encoding="utf-8").replace("\r\n", "\n")

# Copied from ManualTicket.tsx before #333 touched it.
POST_CALL = """await placeManualOrder(
      {
        ticker,
        side,
        contracts,
        max_price_tenths: maxPriceTenths,
        idempotency_key: intentKey,
        combo_acknowledged: market.is_combo ? comboOk : false,
      },
    );"""


class TestTheTicketWarns:
    def test_the_note_is_imported_and_mounted_with_the_market_and_side(self):
        assert 'import HeldConflictsNote from "@/components/HeldConflictsNote";' in TICKET
        mount = re.search(r"<HeldConflictsNote\b([^>]*)/>", TICKET)
        assert mount, "ManualTicket does not mount HeldConflictsNote"
        assert "ticker={market.ticker}" in mount.group(1)
        assert "side={side}" in mount.group(1)

    def test_the_note_asks_with_the_side(self):
        assert "side?:" in NOTE
        assert "fetchHeldConflicts(ticker, side)" in NOTE
        assert "&side=" in API
        assert "same_side" in NOTE


class TestTheOrderIsUntouched:
    def test_the_post_call_expression_is_unchanged(self):
        assert TICKET.count("await placeManualOrder(") == 1
        assert POST_CALL in TICKET
