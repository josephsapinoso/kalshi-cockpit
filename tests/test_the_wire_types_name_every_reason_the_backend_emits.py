"""The `HeldPosition` wire unions in `api.ts` must name every string
`backend.hedge` can actually emit for `combo_book_reason`, `combo_book.state`
and `stake_basis` -- and nothing they don't.

Why: #128 added `COMBO_BOOK_REASON_NOTHING_PENDING = "nothing_pending"`
(`backend/hedge.py:134`) and served it on most rows; `api.ts:3641` kept
typing the field as `"no_ticket" | "no_reader_wired" | null` until #130
noticed by accident a day later. Nothing failed: `comboBookNote` never reads
the reason, `tsc` cannot see the wire, and there is no JS test runner. The
unions are hand-maintained against Python constants, and the drift is
invisible by construction.

Three pairs, each checked both directions -- a value the backend emits that
the type lacks, and a value the type names that nothing emits (a dead
literal is the same drift the other way):

- reason: `backend.hedge` attributes named exactly `COMBO_BOOK_REASON_*`
  vs. the `combo_book_reason` union (`null` excluded).
- state: `backend.hedge` attributes named `COMBO_BOOK_*` but NOT
  `COMBO_BOOK_REASON_*` vs. the `state` field inside the `combo_book: {...}`
  block on `HeldPosition`.
- basis: `backend.hedge` attributes named `STAKE_BASIS_*` vs. the
  `stake_basis` union (`null` excluded).

The prefix match for the reason pair is exact (`COMBO_BOOK_REASON_`, not a
loose `COMBO_BOOK_`) on purpose: a loose prefix also collects the four state
constants and reports a drift that does not exist.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- Anything about `stake_basis_reason`. It is deliberately typed
  `string | null` (`api.ts:3583-3589`) because its values are bare string
  literals scattered through `backend/hedge.py` (`hand_recorded_position`,
  `no_order_row`, ...), not module-level constants with a common prefix --
  it cannot be guarded this way and this test does not claim to.
- That any value assigned to these fields outside the named constants (a
  typo'd literal written some other way) is caught.
- Any wire type or screen other than `HeldPosition` in `api.ts`.
"""

from __future__ import annotations

import re
from pathlib import Path

import backend.hedge as hedge

API_TS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "api.ts"


def _backend_values(prefix: str, *, exclude_prefix: str | None = None) -> set[str]:
    """String values of module-level `backend.hedge` attributes whose name
    starts with `prefix` (and, if given, does NOT start with `exclude_prefix`)."""
    values = set()
    for name, value in vars(hedge).items():
        if not name.startswith(prefix):
            continue
        if exclude_prefix is not None and name.startswith(exclude_prefix):
            continue
        if isinstance(value, str):
            values.add(value)
    return values


def _quoted_members(text: str) -> set[str]:
    """Every double-quoted string literal in `text`, `"null"` dropped (the
    union's `null` is a bare keyword, not a string, but this stays defensive
    if that ever changes)."""
    return {m for m in re.findall(r'"([^"]*)"', text) if m != "null"}


def _api_ts_source() -> str:
    return API_TS.read_text(encoding="utf-8")


def _field_union(source: str, field: str) -> set[str]:
    """The quoted members of `field: "a" | "b" | ... ;` on `HeldPosition`,
    matched from the field name to the terminating semicolon. DOTALL so a
    reflow across lines still matches."""
    match = re.search(rf"\b{re.escape(field)}:\s*(.*?);", source, flags=re.DOTALL)
    assert match, f"could not find a `{field}:` field in {API_TS}"
    return _quoted_members(match.group(1))


def _combo_book_state_union(source: str) -> set[str]:
    """The quoted members of the `state` field inside the `combo_book: {...}`
    block on `HeldPosition` -- not the unrelated top-level `state:` field
    (`"lock" | "derisk" | ...`) that also exists on the same type."""
    block_match = re.search(
        r"combo_book:\s*\{(.*?)\}\s*\|\s*null;", source, flags=re.DOTALL
    )
    assert block_match, f"could not find the `combo_book: {{...}}` block in {API_TS}"
    return _field_union(block_match.group(1), "state")


class TestReasonPair:
    def test_combo_book_reason_constants_match_the_union(self):
        backend_values = _backend_values("COMBO_BOOK_REASON_")
        ts_values = _field_union(_api_ts_source(), "combo_book_reason")
        assert backend_values == ts_values, (
            f"backend.hedge COMBO_BOOK_REASON_* values: {backend_values!r}\n"
            f"api.ts combo_book_reason union members: {ts_values!r}\n"
            f"backend emits but the type lacks: {backend_values - ts_values!r}\n"
            f"type names but nothing emits: {ts_values - backend_values!r}"
        )


class TestStatePair:
    def test_combo_book_state_constants_match_the_union(self):
        backend_values = _backend_values(
            "COMBO_BOOK_", exclude_prefix="COMBO_BOOK_REASON_"
        )
        ts_values = _combo_book_state_union(_api_ts_source())
        assert backend_values == ts_values, (
            f"backend.hedge COMBO_BOOK_* (non-reason) values: {backend_values!r}\n"
            f"api.ts combo_book.state union members: {ts_values!r}\n"
            f"backend emits but the type lacks: {backend_values - ts_values!r}\n"
            f"type names but nothing emits: {ts_values - backend_values!r}"
        )


class TestBasisPair:
    def test_stake_basis_constants_match_the_union(self):
        backend_values = _backend_values("STAKE_BASIS_")
        ts_values = _field_union(_api_ts_source(), "stake_basis")
        assert backend_values == ts_values, (
            f"backend.hedge STAKE_BASIS_* values: {backend_values!r}\n"
            f"api.ts stake_basis union members: {ts_values!r}\n"
            f"backend emits but the type lacks: {backend_values - ts_values!r}\n"
            f"type names but nothing emits: {ts_values - backend_values!r}"
        )
