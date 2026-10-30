"""Two display fixes from the 2026-10-30 town hall's main lane (#415).

- The ticket's max-price stepper counts whole cents, so a deci-cent ceiling
  displayed rounded. The exact figure is now printed beside it, and the value
  sent is untouched.
- The hedge ladder's last column is the worse of two estimates; Joe's (A) to
  #406 labels it one.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TICKET = (ROOT / "frontend/src/components/ManualTicket.tsx").read_text(encoding="utf-8")
HEDGE = (ROOT / "frontend/src/components/HedgePositions.tsx").read_text(encoding="utf-8")


class TestTheTicketPrintsAnExactDeciCentCeiling:
    def test_a_deci_cent_ceiling_is_printed_to_the_tenth(self):
        assert "maxPriceTenths % 10 !== 0" in TICKET
        assert "Set to exactly {(maxPriceTenths / 10).toFixed(1)}c" in TICKET

    def test_the_stepper_still_sends_what_it_did(self):
        """Display only: the order path's setter is unchanged."""
        assert "onChange={(cents) => setMaxPriceTenths(cents * 10)}" in TICKET


class TestTheHedgeWorstCaseIsLabelledAnEstimate:
    def test_the_column_says_estimate(self):
        assert ">worst case (estimate)</th>" in HEDGE
        assert ">worst case</th>" not in HEDGE
