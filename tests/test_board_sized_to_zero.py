"""SIZED TO ZERO is its own state on the Board (ticket #25, Joe's 25C).

Every row the gate has ever counted actionable -- 51 rows across 15 games at
the 2026-09-01 re-audit -- had `suggested_contracts = 0`: the gate counts at
the fixed $1,000 reference profile (`gate.POPULATIONS["actionable"]`,
`suppressed_reason IS NULL AND reference_contracts > 0`, ADR 0015 §3) and
quarter-Kelly at the observed balance sizes each of them to zero. `/api/board`
split its buckets on `suggested_contracts`, so the whole actionable population
was filed under `no_edge` and captioned "no edge after fees" two inches below a
headline counting it.

The split is now on the gate's own column. `population_counts` is NOT forked
-- the Board buckets downstream of the row -- and this module pins the two
counts equal on one fixture so they cannot drift apart silently.

**What this does not establish.**

- Nothing here makes a row bettable. `suggested_contracts` is 0 on every row
  in the new bucket by definition, the order endpoint re-derives sizing inside
  the request, and the gate's `actionable` count is read, not redefined.
- The frontend assertions are over source text and one Node run of the caption
  function, because this repo has no JS test runner. They do not render the
  page, so they cannot show the chip is legible or that the tile fits at 390px.
- It does not establish that the reference profile is the right one to count
  at, or that the gate should open. It checks that whatever the gate counts,
  the Board names in the same words.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from tests.test_api import _slate_row, get
from tests.test_board_screen import (
    API_TS,
    BOARD_PAGE,
    SLATE_ROW,
    _one_row_db,
    block,
    code,
    source,
)

GATE_ACTIONABLE = "r.suppressed_reason IS NULL AND r.reference_contracts > 0"


def _reference_size(conn, ticker: str, reference: int | None) -> None:
    """Set `reference_contracts` on a row `_slate_row` already wrote.

    `_slate_row` writes `reference_contracts = suggested_contracts`, which is
    the reference-profile deployment where the two are equal by construction.
    The population this module is about is the one where they DIFFER -- the
    gate counts the row at $1,000 and the deposit sizes it to zero -- and an
    UPDATE after the fact keeps one INSERT encoding the row shape.
    """
    conn.execute(
        "UPDATE recommendations SET reference_contracts = ? WHERE ticker = ?",
        (reference, ticker),
    )


def _tickers(rows) -> set[str]:
    return {r["ticker"] for r in rows}


@pytest.fixture
def split(tmp_path):
    """Five rows, all inside the slate, one per branch of the split."""
    from backend.store.db import now_ms

    path, conn = _one_row_db(tmp_path, "split.db")
    now = now_ms()
    # Counted at the reference bankroll, sized to zero at the deposit.
    _slate_row(conn, ticker="KXCOUNTED", created_ms=now - 30_000)
    _reference_size(conn, "KXCOUNTED", 4)
    # No bet at either bankroll.
    _slate_row(conn, ticker="KXNOBET", created_ms=now - 31_000)
    # A pre-v6 row that escaped the backfill: unreadable, not zero.
    _slate_row(conn, ticker="KXNULLREF", created_ms=now - 32_000)
    _reference_size(conn, "KXNULLREF", None)
    # Refused by a rule AND sized at the reference profile: the shape that
    # would flatter the new bucket if suppression did not win.
    _slate_row(conn, ticker="KXREFUSED", created_ms=now - 33_000,
               suppressed="stale_odds")
    _reference_size(conn, "KXREFUSED", 5)
    # Sized at the deposit too, so it is surfaced or expired, never here.
    _slate_row(conn, ticker="KXSIZED", created_ms=now - 34_000, contracts=3)
    conn.commit()
    conn.close()
    return path, create_app(AppConfig(instance_mode="demo", db_path=path))


class TestTheSplitIsOnTheGatesColumn:
    async def test_a_counted_unbuyable_row_is_sized_to_zero_and_not_no_edge(
        self, split
    ):
        """(a) The population the ticket is about, landing where it says.
        Mutation observed red: drop the `reference_contracts` branch so the
        row falls through to `no_edge`."""
        _, app = split
        body = (await get(app, "/api/board?include_suppressed=true")).json()
        assert _tickers(body["sized_to_zero"]) == {"KXCOUNTED"}
        assert "KXCOUNTED" not in _tickers(body["no_edge"]), (
            "the row the gate counts is still filed under NO EDGE, which is "
            "the defect verbatim."
        )
        assert body["counts"]["sized_to_zero"] == 1
        assert len(body["sized_to_zero"]) == body["counts"]["sized_to_zero"]

    async def test_the_row_carries_the_size_the_caption_prints(self, split):
        """The screen says "reference size 4"; the payload must carry the 4,
        and `suggested_contracts = 0` beside it or the row is an offer."""
        _, app = split
        body = (await get(app, "/api/board?include_suppressed=true")).json()
        (row,) = body["sized_to_zero"]
        assert row["reference_contracts"] == 4
        assert row["suggested_contracts"] == 0
        assert row["suppressed_reason"] is None

    async def test_a_row_with_no_reference_size_is_still_no_edge(self, split):
        """(b) NO EDGE now means what its caption says: no bet at any bankroll.
        A NULL reference lands there too, on the gate's own reading -- an
        unreadable size must not count as a bet. Mutation observed red:
        `(row["reference_contracts"] or 0) > 0` -> `is not None`."""
        _, app = split
        body = (await get(app, "/api/board?include_suppressed=true")).json()
        assert _tickers(body["no_edge"]) == {"KXNOBET", "KXNULLREF"}
        assert body["counts"]["no_edge"] == 2

    async def test_suppression_outranks_sizing(self, split):
        """(c) A refused row with a reference size is refused. The gate says
        the same -- `suppressed_reason IS NOT NULL` is its own population --
        and a Board that moved it here would count a rejected bet as
        evidence. Mutation observed red: test the reference size before the
        suppression reason."""
        _, app = split
        body = (await get(app, "/api/board?include_suppressed=true")).json()
        assert "KXREFUSED" in _tickers(body["suppressed"])
        assert "KXREFUSED" not in _tickers(body["sized_to_zero"])

    async def test_a_deposit_sized_row_is_never_sized_to_zero(self, split):
        """The first branch is unchanged: a row with `suggested_contracts > 0`
        is bettable or expired whatever its reference size, and that is the
        branch a top-up moves a row out of this bucket by."""
        _, app = split
        body = (await get(app, "/api/board?include_suppressed=true")).json()
        assert "KXSIZED" in _tickers(body["surfaced"] + body["expired"])
        assert "KXSIZED" not in _tickers(body["sized_to_zero"])


class TestTheBoardAndTheGateCannotDrift:
    """(d) `population_counts` was not forked; pin that it did not need to be."""

    async def test_the_board_count_and_the_gate_count_agree(self, split):
        """The gate's `actionable` is every unrefused row with a reference
        size, whatever the deposit sized it to -- so on a slate with nothing
        older than the window it is exactly the Board's sized-to-zero rows
        plus the rows the deposit also sized. Read the gate directly, not
        through the payload, so the identity is against the interlock's own
        function."""
        from backend.gate import population_counts
        from backend.store.db import connect

        path, app = split
        body = (await get(app, "/api/board?include_suppressed=true")).json()
        conn = connect(path)
        try:
            gate = population_counts(conn, 0)["actionable"]
        finally:
            conn.close()
        counts = body["counts"]
        assert gate == counts["sized_to_zero"] + counts["surfaced"] + counts["expired"]
        assert body["slate"]["actionable_total"] == gate
        assert gate == 2, "the fixture must hold exactly the two counted rows"

    async def test_with_every_row_unsized_the_two_counts_are_equal(self, tmp_path):
        """The sharper form, on the shape the live record actually has:
        `suggested_contracts = 0` on every row the gate has ever counted."""
        from backend.gate import population_counts
        from backend.store.db import connect, now_ms

        path, conn = _one_row_db(tmp_path, "unsized.db")
        now = now_ms()
        for i, reference in enumerate((3, 7, 0, 12)):
            _slate_row(conn, ticker=f"KXZ-{i}", created_ms=now - 30_000 - i)
            _reference_size(conn, f"KXZ-{i}", reference)
        conn.commit()
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))

        body = (await get(app, "/api/board?include_suppressed=true")).json()
        conn = connect(path)
        try:
            gate = population_counts(conn, 0)
        finally:
            conn.close()
        assert body["counts"]["sized_to_zero"] == gate["actionable"] == 3
        assert body["counts"]["no_edge"] == gate["no_edge"] == 1
        assert body["counts"]["surfaced"] == body["counts"]["expired"] == 0

    async def test_nothing_leaves_the_slate_by_gaining_a_bucket(self, split):
        """A fifth bucket that `returned` did not count would re-open the
        silent-drop defect `test_board_screen` section 3 closed, one bucket
        over. Mutation observed red: leave `sized_to_zero` out of `returned`."""
        _, app = split
        body = (await get(app, "/api/board?include_suppressed=true")).json()
        every = (
            body["surfaced"] + body["expired"] + body["suppressed"]
            + body["sized_to_zero"] + body["no_edge"]
        )
        assert len(every) == body["slate"]["returned"] == 5
        assert body["slate"]["in_window"] == 5

    async def test_it_is_hidden_under_the_same_flag_as_no_edge(self, split):
        """Rest-of-the-slate rows travel together. The count is always sent,
        the rows only when asked for, exactly as `suppressed` and `no_edge`."""
        _, app = split
        body = (await get(app, "/api/board")).json()
        assert body["sized_to_zero"] == []
        assert body["no_edge"] == []
        assert body["counts"]["sized_to_zero"] == 1

    async def test_the_reference_bankroll_travels_with_the_slate(self, split):
        """The caption prints "$1,000"; the figure comes off the server so the
        page cannot go on saying it after the constant moves."""
        from backend.config import REFERENCE_BANKROLL_DOLLARS

        _, app = split
        slate = (await get(app, "/api/board")).json()["slate"]
        assert slate["reference_bankroll_dollars"] == REFERENCE_BANKROLL_DOLLARS

    def test_the_split_reads_the_gate_column_and_restates_no_predicate(self):
        """The route buckets on `reference_contracts` -- the column
        `gate.POPULATIONS["actionable"]` reads -- and carries no second SQL
        spelling of the gate's predicate. Two fragments encoding one
        definition is the drift `population_counts`' docstring warns about."""
        from backend import gate
        from backend.api import routes

        assert gate.POPULATIONS["actionable"] == GATE_ACTIONABLE, (
            "the gate's predicate moved; re-read this module against it"
        )
        text = source(Path(routes.__file__))
        handler = block(text, '@app.get("/api/board")', '@app.get("/api/slate")')
        # The docstring and the comments quote the gate's predicate while
        # explaining why the code does not restate it; strip them so the
        # assertion is about the code.
        handler = re.sub(r'""".*?"""', "", handler, flags=re.DOTALL)
        handler = re.sub(r"^\s*#.*$", "", handler, flags=re.MULTILINE)
        assert 'row["reference_contracts"]' in handler
        assert "sized_to_zero.append(item)" in handler
        assert "reference_contracts > 0" not in handler, (
            "the Board restates the gate's predicate in SQL instead of "
            "bucketing on the column."
        )
        assert "population_counts(conn, 0)" in handler, (
            "the Board no longer reads the gate's own count for "
            "actionable_total."
        )


class TestTheScreenNamesTheState:
    """(e) Source pins for the chip, the caption, the tile and the sentence."""

    def test_the_row_has_the_state_and_the_chip_names_it(self):
        row = code(SLATE_ROW)
        states = block(row, "export type SlateState =", ";")
        assert '"sized-to-zero"' in states
        chip = block(row, '"sized-to-zero": {', "},")
        assert 'label: "SIZED TO ZERO"' in chip
        assert "text-positive" not in chip, "a counted size is not an offer"
        assert "negative" not in chip and "accent" not in chip, (
            "the chip carries a tone colour, and colour is a claim; this row's "
            "claim is a fact about two bankrolls, not a verdict."
        )

    def test_the_caption_says_both_halves_and_the_row_renders_it(self):
        """"reference size N at $1,000" alone reads as a size to buy; "sized
        to 0" alone reads as NO EDGE with a different chip."""
        row = code(SLATE_ROW)
        caption = block(row, "export function sizedToZeroCaption(", "\n}")
        assert "reference size " in caption
        assert "sized to 0 at your balance" in caption
        # And it is what the row renders for the state, not a helper nothing
        # calls.
        assert 'resolved === "sized-to-zero"' in row
        assert "sizedToZeroCaption(rec, referenceBankrollDollars)" in row

    def test_the_caption_is_what_the_function_actually_produces(self):
        """Run the real declarations, as `test_board_screen` does for
        `edgeTone`. Node strips erasable TypeScript natively."""
        row = source(SLATE_ROW)
        fns = "".join(
            f"export function {name}(" + block(row, f"export function {name}(", "\n}") + "\n}\n"
            for name in ("formatBankroll", "sizedToZeroCaption")
        )
        harness = (
            "type Recommendation = { reference_contracts: number | null };\n"
            + fns
            + """
const full = sizedToZeroCaption({ reference_contracts: 4 }, 1000);
// Two different bankrolls print two different figures: the caption reads
// the argument, not a literal.
if (sizedToZeroCaption({ reference_contracts: 2 }, 2500) !== "reference size 2 at $2,500 · sized to 0 at your balance") {
  console.error("the bankroll in the caption is not the one passed in");
  process.exit(1);
}
if (full !== "reference size 4 at $1,000 · sized to 0 at your balance") {
  console.error(`full caption: ${full}`);
  process.exit(1);
}
const nul = sizedToZeroCaption({ reference_contracts: null }, 1000);
if (nul !== "sized to 0 at your balance") {
  console.error(`null caption: ${nul}`);
  process.exit(1);
}
"""
        )
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not on PATH; the source assertions above still hold")
        with tempfile.TemporaryDirectory() as d:
            tmp_ts = Path(d) / "sized_to_zero_caption.ts"
            tmp_ts.write_text(harness, encoding="utf-8")
            scratch = subprocess.run(
                [node, str(tmp_ts)], capture_output=True, text=True, timeout=60
            )
        assert scratch.returncode == 0, scratch.stderr + scratch.stdout

    def test_the_page_maps_the_bucket_to_the_state(self):
        page = code(BOARD_PAGE)
        assert "board.sized_to_zero.map(" in page, (
            "the bucket is in the payload and rendered by nothing."
        )
        mapping = block(page, "board.sized_to_zero.map(", "})")
        assert '"sized-to-zero"' in mapping
        assert (
            "referenceBankrollDollars={board.slate.reference_bankroll_dollars}"
            in page
        )

    def test_the_page_has_the_tile_and_counts_it_as_hidden(self):
        page = code(BOARD_PAGE)
        assert (
            '<Stat label="Sized to zero" value={board.counts.sized_to_zero} />'
            in page
        )
        hidden = block(page, "const hidden =", ";")
        assert "board.counts.sized_to_zero" in hidden, (
            "with rejected rows hidden the page under-counts what it is not "
            "showing, which is the old defect at one remove."
        )

    def test_the_record_sentence_reconciles_with_the_tiles(self):
        """"N of M ever recorded" is the gate's count at the reference
        bankroll. The sentence now says so and names the rows that count
        there and buy nothing here, so the headline and the chips agree about
        what "actionable" means -- the disagreement Joe's option A would have
        left standing."""
        page = source(BOARD_PAGE)
        sentence = block(page, "Bettable now{", "</p>")
        assert "actionable_total" in sentence
        assert "{referenceBankroll}" in sentence
        assert "SIZED TO ZERO" in sentence
        assert "{board.counts.sized_to_zero}" in sentence

    def test_no_edge_keeps_its_caption_and_the_header_names_three_reasons(self):
        row = code(SLATE_ROW)
        assert '"no edge after fees"' in row
        page = source(BOARD_PAGE)
        header = block(page, "<h1", "</header>")
        assert "quarter-Kelly" in header and "buys no" in header, (
            "the header still names two kinds of refusal while the rows show "
            "three."
        )

    def test_the_types_carry_the_bucket(self):
        api = source(API_TS)
        board = block(api, "export type Board = {", "\n};")
        assert "sized_to_zero: Recommendation[];" in board
        counts = block(board, "counts: {", "};")
        assert "sized_to_zero: number;" in counts
        assert "reference_bankroll_dollars: number;" in board
