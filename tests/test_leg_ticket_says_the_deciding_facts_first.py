"""The leg ticket says the facts that decide the bet first (#160).

From the sharp-bettor review of #158: the break-even ("you need this to
happen more than 93.46% of the time") and a zero-buyable state ("you can buy
0 contracts -- shard 0 holds $0.01") rendered at the bottom of the ticket,
under the amount box and the real-money strip. Joe answered on 2026-09-25,
with option buttons: at zero, say so at the top with the reason and **switch
the amount box off** -- visible, disabled -- until a re-read finds something
buyable. Partner placed the break-even beside the leg's fair chance, as a
plain fact.

The armed path's logic is not what moved: `canConfirm`, `openTicket`,
`reread`, `confirm`, the intent key and the payload are untouched, and the
last test here pins that `canConfirm` did not grow a clause.

**What these tests do not establish.** They read source text; there is no DOM
test runner in this repo. They cannot see that the notice renders for a real
zero-ceiling preflight, only that the source orders and gates it so. That is
checked by screenshot through a read-only proxy, recorded in the session's
NEXT.md entry.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TICKET = ROOT / "frontend" / "src" / "components" / "ManualTicket.tsx"


def _body() -> str:
    source = TICKET.read_text(encoding="utf-8")
    start = source.index("function TicketBody")
    # TicketBody ends where the next top-level doc comment begins.
    return source[start : source.index("\n/**", start)]


class TestTheDecidingFactsComeFirst:
    def test_the_break_even_renders_before_the_amount_box(self):
        body = _body()
        assert body.index("facts.breakeven_probability !== null &&") < body.index(
            "<DollarAmount"
        ), "the break-even is below the amount box again"

    def test_the_break_even_renders_before_the_real_money_strip(self):
        body = _body()
        assert body.index("facts.breakeven_probability !== null &&") < body.index(
            "{!market.dry_run && ("
        )

    def test_the_zero_buyable_notice_renders_before_the_amount_box(self):
        body = _body()
        notice = body.index('data-claim="zero-buyable"')
        assert notice < body.index("<DollarAmount")
        assert notice < body.index("{!market.dry_run && (")
        assert "You can buy 0 here right now." in body


class TestZeroBuyableSwitchesTheBoxOff:
    def test_zero_is_a_ceiling_of_exactly_zero_not_an_unread_one(self):
        """An unreadable wallet (`ceiling === null`) is ignorance, not zero,
        and must never switch the box off: unreadable resolves to None."""
        body = _body()
        assert "const zeroBuyable = ceiling === 0;" in body

    def test_the_notice_is_gated_on_zero_buyable(self):
        body = _body()
        gate = body.index("{zeroBuyable && (")
        assert gate < body.index('data-claim="zero-buyable"')

    def test_the_amount_box_is_disabled_at_zero(self):
        body = _body()
        amount = body[body.index("<DollarAmount") :]
        amount = amount[: amount.index("/>")]
        assert "disabled={sending || zeroBuyable}" in amount

    def test_the_reason_is_said_once_not_twice(self):
        """The depth line drops its `— why` tail at zero, because the notice
        at the top carries it in full, and the amount box's zero branch
        points up instead of printing the shard paragraph again."""
        source = TICKET.read_text(encoding="utf-8")
        body = _body()
        assert "!zeroBuyable && boundWhy !== null" in body
        amount = source[source.index("function DollarAmount") :]
        assert "<ShardRemedy" not in amount
        assert source.count("<ShardRemedy") == 1


class TestTheArmedPathDidNotMove:
    def test_can_confirm_did_not_grow_a_clause(self):
        """Switching the box off is presentation. Confirm was already off at
        zero through `contracts >= 1`; a `zeroBuyable` clause in `canConfirm`
        would be a second spelling of the same predicate."""
        body = _body()
        gate = body[body.index("const canConfirm") :]
        gate = gate[: gate.index(";")]
        assert "zeroBuyable" not in gate
        assert "contracts >= 1" in gate


class TestTheZeroReasonIsTrueForEveryBound:
    """From the kalshi-platform review of #160, three sentences that were
    false in reachable states."""

    def test_the_pointer_upward_is_keyed_on_a_zero_ceiling(self):
        """A side switch can leave `contracts` at 0 on a buyable side (both
        asks equal, both ceilings equal, so the effect does not re-run).
        Keyed on `contracts`, the amount box pointed at a notice that was
        not there."""
        source = TICKET.read_text(encoding="utf-8")
        amount = source[source.index("function DollarAmount") :]
        branch = amount[amount.index("affordable !== null && affordable >= 1 ?") :]
        pointer = branch.index("The note at the top of this")
        assert "{ceiling === 0 ? (" in branch[:pointer]
        assert "Edit the amount to count it again" in branch

    def test_a_price_grid_zero_says_the_grid(self):
        source = TICKET.read_text(encoding="utf-8")
        reason = source[source.index("function ZeroReason") :]
        reason = reason[: reason.index("\n}\n")]
        assert 'binding === "price_grid"' in reason
        assert "price grid" in reason

    def test_a_depth_zero_does_not_claim_nothing_rests(self):
        """The server floors depth and reads an unknown size as 0."""
        source = " ".join(TICKET.read_text(encoding="utf-8").split())
        assert "Nothing is resting at the ask" not in source
        assert "Less than one whole contract is resting at the ask" in source
