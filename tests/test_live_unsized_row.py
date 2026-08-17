"""A live-zeroed Board row must stop being offerable, executed rather than read.

**The defect.** `LiveBoard` merges a streamed quote over the recorded row,
overwriting `suggested_contracts` with `quote.contracts`. `backend/live.py`
computes that with the same `size_position` the order endpoint uses, so it
reaches **0** when the price moves against the row mid-stream -- by design. The
merge overwrites nothing else, so the card:

* lost its cost block to a `suggested_contracts > 0` guard,
* kept a `reason_text` still reading *"Sized at 14."*,
* and stayed wrapped in `TicketTrigger`, i.e. tappable, opening a ticket for a
  size the server had already decided to refuse.

Server-side re-validation is intact and would reject such an order, so nothing
could be bought -- this is a wrong screen, not a hole in the order path. It is
still the failure this repo names in the dangerous direction.

**Why `node` and not a substring assertion.** Every other frontend guard here
reads the `.tsx` as text. That is worth nothing for *"does this predicate reach
the right verdict"*: a substring assertion passes unchanged on a predicate that
has been exactly inverted, and a wrong verdict is exactly this defect. The
verdict lives in `frontend/src/lib/liveSizing.ts` as plain TypeScript so the
shipped function can be called for real. Same reasoning and same shape as
`tests/test_sweep_tone_predicate.py`.

What this establishes: the mapping from a row's size to whether it may be
offered, that the clause is load-bearing under mutation, and that both call
sites actually consult it. What it does **not** establish: that
`backend/live.py` zeroes the size correctly (`tests/test_live.py`), that the
copy is well-worded, or anything about the order endpoint's own re-validation.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SIZING_TS = REPO / "frontend" / "src" / "lib" / "liveSizing.ts"
LIVE_BOARD = REPO / "frontend" / "src" / "components" / "LiveBoard.tsx"
CARD = REPO / "frontend" / "src" / "components" / "OpportunityCard.tsx"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: this guard is real "
        "where node exists (CI and both dev machines) and a missing runtime is "
        "an environment fact, not a pending failure."
    ),
)


# ---------------------------------------------------------------------------
# The states
# ---------------------------------------------------------------------------

#: The ordinary case: a row served in `surfaced`, which `routes.py` builds only
#: when `suggested_contracts > 0`, still sized after the feed re-priced it.
SIZED_LIVE = {"suggested_contracts": 14, "live": True}

#: **The defect's state.** The feed re-sized this row to zero because the price
#: moved. Before the fix the card kept "Sized at 14." and stayed tappable.
ZEROED_BY_THE_FEED = {"suggested_contracts": 0, "live": True}

#: A row at zero that did not come from the feed. Unreachable from the server
#: today, and deliberately still refused -- the guard must not depend on
#: `routes.py` continuing to filter, which is the "built but never called"
#: shape pointed the other way.
ZEROED_NOT_LIVE = {"suggested_contracts": 0, "live": False}

#: Unreadable resolves to refusing, never to offering. `NaN <= 0` is `false`,
#: so this is the case a naive comparison gets wrong in the offering direction.
UNREADABLE = {"suggested_contracts": float("nan"), "live": True}

NEGATIVE = {"suggested_contracts": -3, "live": True}


_DRIVER = """
import {{ liveSizing }} from "{module}";
const row = JSON.parse(process.argv[2]);
if (row.suggested_contracts === "NaN") row.suggested_contracts = NaN;
console.log(JSON.stringify(liveSizing(row)));
"""


def verdict_of(row: dict, *, source: str | None = None, tmp_path=None) -> dict:
    """Call the shipped `liveSizing` with `row` and return its verdict.

    `source` substitutes a mutated copy of the module, which is how the
    disabling checks below prove the clause is load-bearing.
    """
    if source is None:
        module_dir = SIZING_TS.parent
    else:
        module_dir = tmp_path
        (module_dir / "liveSizing.ts").write_text(source, encoding="utf-8")

    payload = dict(row)
    if isinstance(payload["suggested_contracts"], float) and payload[
        "suggested_contracts"
    ] != payload["suggested_contracts"]:
        payload["suggested_contracts"] = "NaN"

    driver = module_dir / "_sizing_driver.mjs"
    driver.write_text(_DRIVER.format(module="./liveSizing.ts"), encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(module_dir),
        )
    finally:
        driver.unlink(missing_ok=True)

    assert out.returncode == 0, (
        f"node failed running the predicate:\n{out.stdout}\n{out.stderr}"
    )
    return json.loads(out.stdout.strip())


class TestThePairThatDecidesTheFix:
    """The two states the fix must tell apart. If it cannot, it is not a fix."""

    def test_a_sized_live_row_is_still_offerable(self):
        assert verdict_of(SIZED_LIVE)["offerable"] is True

    def test_a_row_the_feed_zeroed_is_not_offerable(self):
        assert verdict_of(ZEROED_BY_THE_FEED)["offerable"] is False

    def test_the_two_reach_opposite_verdicts(self):
        """The assertion the whole lane rests on, stated as one comparison."""
        assert (
            verdict_of(SIZED_LIVE)["offerable"]
            != verdict_of(ZEROED_BY_THE_FEED)["offerable"]
        )


class TestTheStaleSentenceIsReplacedNotAccompanied:
    """`reason_text` is written against the size the row had when recorded.

    Leaving it beside a correction would put "Sized at 14." and "no longer
    sized" on one card, which is worse than either alone.
    """

    def test_a_sized_row_supplies_no_note_so_the_recorded_reason_stands(self):
        assert verdict_of(SIZED_LIVE)["note"] is None

    def test_a_zeroed_row_supplies_a_note_to_replace_it(self):
        note = verdict_of(ZEROED_BY_THE_FEED)["note"]
        assert note is not None
        assert "no longer sized" in note.lower()

    def test_the_note_says_the_price_moved_only_when_the_feed_is_why(self):
        """A non-live zero was not caused by a price move, so it must not claim
        one. Two states, two sentences, neither borrowed."""
        assert "price moved" in verdict_of(ZEROED_BY_THE_FEED)["note"].lower()
        assert "price moved" not in verdict_of(ZEROED_NOT_LIVE)["note"].lower()
        assert verdict_of(ZEROED_NOT_LIVE)["offerable"] is False


class TestUnreadableRefusesRatherThanOffers:
    """`CLAUDE.md`: unreadable resolves to `None`, never to `0` -- here, to
    refusing rather than to offering. `NaN <= 0` is `false`, so a comparison
    alone would call an unreadable size offerable."""

    def test_nan_is_not_offerable(self):
        assert verdict_of(UNREADABLE)["offerable"] is False

    def test_a_negative_size_is_not_offerable(self):
        assert verdict_of(NEGATIVE)["offerable"] is False


class TestTheClauseIsLoadBearing:
    """Disable it and watch it fail. A guard that stays green is decoration."""

    def test_dropping_the_nan_check_lets_an_unreadable_size_be_offered(
        self, tmp_path
    ):
        source = SIZING_TS.read_text(encoding="utf-8").replace(
            "typeof contracts !== \"number\" || Number.isNaN(contracts) || contracts <= 0",
            "contracts <= 0",
        )
        assert source != SIZING_TS.read_text(encoding="utf-8"), "mutation did not apply"
        assert verdict_of(UNREADABLE, source=source, tmp_path=tmp_path)["offerable"] is True

    def test_inverting_the_size_test_offers_exactly_the_wrong_rows(self, tmp_path):
        source = SIZING_TS.read_text(encoding="utf-8").replace(
            "contracts <= 0", "contracts > 0"
        )
        assert source != SIZING_TS.read_text(encoding="utf-8"), "mutation did not apply"
        assert (
            verdict_of(SIZED_LIVE, source=source, tmp_path=tmp_path)["offerable"]
            is False
        )


class TestBothCallSitesActuallyConsultIt:
    """A predicate nothing calls is decoration -- this repo's named defect.

    Source-text assertions are the right tool for *this* claim, which is about
    an edge existing, not about a verdict being correct.
    """

    def test_live_board_gates_the_ticket_trigger_on_it(self):
        source = LIVE_BOARD.read_text(encoding="utf-8")
        assert "liveSizing" in source, "LiveBoard does not import the predicate"
        assert ".offerable" in source, (
            "LiveBoard imports the predicate without consulting its verdict"
        )
        trigger = source.index("<TicketTrigger")
        gate = source.index(".offerable")
        assert gate < trigger, (
            "the TicketTrigger is not behind the offerable check, so a zeroed "
            "row is still tappable"
        )

    def test_the_card_replaces_reason_text_with_the_note(self):
        source = CARD.read_text(encoding="utf-8")
        assert "liveSizing" in source, "OpportunityCard does not import the predicate"
        assert "sizing.note ?? rec.reason_text" in source, (
            "the card renders reason_text without letting the note replace it"
        )
