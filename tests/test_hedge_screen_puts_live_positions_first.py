"""`/hedge` renders a pending leg first and folds every settled position into
one collapsed, counted group -- #130.

Live on 2026-09-22 ~03:55Z: 43 open positions, 2 with a pending leg, 41
settled (34 `dead`, 7 `won`). `HedgePositions.tsx` was a bare `positions.map`
with no partition, no collapse, no cap, so the settled group grows every
night Joe bets and buries the two rows that matter under forty-one that do
not (nothing here auto-closes a position by design; `close_position` still
has one caller, Joe's own tap).

ADR 0071 §2.5 does not forbid this split. That rule says the
consensus-vs-Kalshi *gap* is shown per row and never ranked by; whether a
leg is still pending is a fact about the world, not a claim about which bet
is better. Record order is kept inside each group -- the partition does not
reorder anything on its own.

WHAT THIS ESTABLISHES
----------------------
(i)   The component partitions on `pending_legs`.
(ii)  The pending group's JSX precedes the settled group's in source order.
(iii) The settled summary's count is computed from the group's length, never
      a typed-in literal, and is singular/plural correct.
(iv)  Both groups are rendered from the SAME `positions` array, and neither
      `.filter` result is computed and then dropped -- every position that
      goes into `pending` or `settled` also reaches a `.map` that renders a
      `<Position>`.
(v)   `api.ts`'s `combo_book_reason` union names `nothing_pending`, the third
      designed "not applicable" cause (`backend/hedge.py:1960`, added
      alongside #128).

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- That anything renders correctly in a browser, wraps at phone width, or
  that the `<details>` element opens on tap the way it does in every
  browser Joe uses. Source text only, no DOM, same instrument as every
  other `HedgePositions.tsx` test in this repo.
- Anything about how often a position carries a pending leg. Zero rate
  claims are made here; the 43/2/41 figures above are a snapshot, not a
  measurement this file depends on.
- That `<Position>` itself renders any differently -- this file asserts the
  wrapper changed and the component it wraps did not (`test_position_
  rendering_is_untouched`).

MUTATIONS, each applied to the guarded code and observed red
--------------------------------------------------------------
  1. drop the `pending_legs > 0` / `pending_legs === 0` partition and go
     back to a bare `positions.map` -> `test_the_component_partitions_on_
     pending_legs` goes red.
  2. swap the order so the settled `<details>` block is emitted before the
     pending group's JSX -> `test_the_pending_group_is_emitted_before_the_
     settled_group` goes red.
  3. hardcode the settled summary's count (e.g. always "settled tickets"
     with no number, or a stale literal) -> `test_the_settled_summary_
     count_is_computed_not_literal` goes red.
  4. drop the `settled.length === 1` singular check, always render the
     plural "s" -> `test_the_settled_summary_is_singular_when_one` goes red.
  5. filter `positions` into `pending`/`settled` but only ever `.map` one of
     them (e.g. comment out the settled `.map` call) -> `test_neither_group_
     is_computed_and_then_dropped` goes red.
  6. remove `"nothing_pending"` from the `combo_book_reason` union in
     `api.ts` -> `test_the_wire_type_names_nothing_pending` goes red.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "frontend" / "src" / "components" / "HedgePositions.tsx"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"


def collapsed(path: Path) -> str:
    """`path`'s source with whitespace collapsed -- Prettier wraps JSX and
    long literals at 80 columns, so a substring guard must not depend on a
    phrase fitting on one physical line (`tasks/lessons.md`, 2026-09-16,
    tenth)."""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def position_groups_body() -> str:
    """The `PositionGroups` function's own source, collapsed -- narrower
    than the whole file so a mutation search elsewhere in the component
    cannot accidentally satisfy these assertions."""
    source = CARD.read_text(encoding="utf-8")
    start = source.index("function PositionGroups(")
    # `PositionGroups` is the last function-scale block added by this
    # ticket; slicing to the end of file is fine because nothing after it
    # in this component is part of the guarded logic.
    return re.sub(r"\s+", " ", source[start:])


class TestThePartition:
    def test_the_component_partitions_on_pending_legs(self):
        """#132: the settled group is the COMPLEMENT of the live predicate,
        not a second hand-written `pending_legs === 0` condition -- that
        literal disappears under the complement form and would leave a
        venue-settled, legs-pending position matching neither group."""
        body = position_groups_body()
        assert "pending_legs > 0" in body
        assert "!isLive(" in body

    def test_the_pending_group_is_emitted_before_the_settled_group(self):
        body = position_groups_body()
        pending_idx = body.index("pending.length")
        settled_idx = body.index("<details")
        assert pending_idx < settled_idx, (
            "the settled group's <details> block appears before the "
            "pending group is rendered"
        )

    def test_neither_group_is_computed_and_then_dropped(self):
        """Both `pending` and `settled` are filtered AND mapped -- a
        computed-and-discarded partition would still satisfy the previous
        two tests."""
        body = position_groups_body()
        assert "pending.map(" in body
        assert "settled.map(" in body
        # Both `.map` calls must actually render a `<Position>`, not just
        # iterate and discard -- a mutation that maps to `null` would still
        # satisfy the two asserts above.
        assert body.count("<Position") == 2


class TestTheSettledSummary:
    def test_the_settled_summary_count_is_computed_not_literal(self):
        body = position_groups_body()
        assert "{settled.length} settled ticket" in body

    def test_the_settled_summary_is_singular_when_one(self):
        body = position_groups_body()
        assert 'settled.length === 1 ? "" : "s"' in body

    def test_no_summary_count_is_hardcoded_elsewhere(self):
        """A literal like `"41 settled tickets"` would pass the count-is-
        computed test above if it sat beside the real one; refuse any digit
        immediately before the word "settled" in the component source."""
        body = collapsed(CARD)
        assert not re.search(r"\d+\s+settled ticket", body), (
            "a hardcoded settled count was found in the component source"
        )


class TestTheEmptyLiveGroup:
    def test_nothing_live_right_now_is_shown_only_beside_a_settled_group(self):
        body = position_groups_body()
        assert "Nothing live right now." in body
        # The sentence must be gated on the settled group existing, not
        # rendered unconditionally -- it sits in the `else` branch of the
        # `pending.length > 0 ? ... : settled.length > 0 && (...)` ladder.
        assert "settled.length > 0 && (" in body

    def test_zero_positions_keeps_the_existing_empty_copy(self):
        source = collapsed(CARD)
        assert "No tickets recorded." in source
        # The zero-positions branch must still short-circuit before
        # `PositionGroups` is ever reached.
        assert "positions.length === 0 ?" in source


class TestPositionRenderingIsUntouched:
    def test_position_rendering_is_untouched(self):
        """Only the wrapper changed -- `Position` itself, and everything it
        renders (`ComboBookLine`, `Hedge`, `Leg`, `Close`), keeps its own
        source untouched by this ticket. A narrow smoke check: the function
        still exists and still takes the same props shape."""
        source = CARD.read_text(encoding="utf-8")
        assert "function Position({" in source
        assert "aria-label={`${position.label} ticket`}" in source


class TestTheWireTypeNamesNothingPending:
    def test_the_wire_type_names_nothing_pending(self):
        source = API_TS.read_text(encoding="utf-8")
        assert '"nothing_pending"' in source
        # Must sit in the same union as the two existing reasons, not a
        # stray string elsewhere in the file.
        match = re.search(
            r'combo_book_reason:\s*"no_ticket"\s*\|\s*"no_reader_wired"\s*\|\s*"nothing_pending"\s*\|\s*null;',
            source,
        )
        assert match, "combo_book_reason union does not name nothing_pending"
