"""The manual-order ticket mounts the held-conflicts warning, without
touching how the order is built or sent (#333).

Positions #78 and #79 were manual orders holding the opposite sides of two
legs of a combination (#75) -- NEXT.md:302-308, 2026-10-02. The combo check
(`backend/held_conflicts.py`, mounted on `AskTheMarket.tsx`) already covered
that incident for a combination; the manual-order ticket, the screen the
incident actually happened on, never called it at all, because it has no
`parlay_lookups` row to check against.

This is read-only over the component's source rather than a browser drive:
the risk in a change like this is that mounting a new, unrelated read
component also nudges the order-sending code it sits beside, so the thing
worth pinning is that the `placeManualOrder` call is untouched, not that the
note renders a particular pixel.

What this establishes
----------------------
- `HeldConflictsNote` is imported and mounted for the ticket's own market
  and the side currently selected.
- The POST call expression that sends the order is byte-identical to the
  text it was before this ticket, copied in below.

What this does NOT establish
-----------------------------
That the note renders correctly in a browser, or that `/api/held-conflicts
?side=` answers correctly for a single market -- `tests/test_held_conflicts
.py` and a browser own those.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TICKET = REPO / "frontend/src/components/ManualTicket.tsx"

# Copied verbatim from the file as it stood before #333. The claim is that
# this exact text still appears afterwards -- not that it was re-derived to
# look the same.
PLACE_ORDER_CALL = """const result = await placeManualOrder(
      {
        ticker,
        side,
        contracts,
        max_price_tenths: maxPriceTenths,
        idempotency_key: intentKey,
        combo_acknowledged: market.is_combo ? comboOk : false,
      },
    );"""


def _source() -> str:
    return TICKET.read_text(encoding="utf-8")


class TestTheOrderCallIsUntouched:
    def test_the_post_call_expression_is_byte_identical(self):
        assert PLACE_ORDER_CALL in _source()


class TestTheNoteIsMounted:
    def test_held_conflicts_note_is_imported(self):
        assert (
            'import HeldConflictsNote from "@/components/HeldConflictsNote"'
            in _source()
        )

    def test_held_conflicts_note_is_mounted_with_the_tickets_market_and_side(self):
        assert re.search(
            r"<HeldConflictsNote\s+ticker=\{market\.ticker\}\s+side=\{side\}\s*/>",
            _source(),
        ), "expected <HeldConflictsNote ticker={market.ticker} side={side} />"
