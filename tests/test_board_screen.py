"""Three defects a `sharp-bettor` review found on the deployed Board.

1. **A refused row was painted in the colour that means take this.** The edge
   took `text-positive` on `edge_cents > 0` alone, so the live demo drew
   `REJECTED  Los Angeles D  60.2% fair / 34.2c ask  +24.4c` with the number in
   bright green and `suspicious_edge` in small grey monospace beside it. That is
   the largest apparent edge in the room rendered as the most attractive thing
   on the page, by the rule (`CLAUDE.md` #1) that exists to catch it.
2. **The record's own headline was in the payload and on no screen.**
   `recorded_total` was serialised and typed and rendered nowhere, so once the
   Board was correctly windowed onto one slate, "Bettable now: 0" read as a
   quiet half-hour rather than as zero actionable across the life of the
   database.
3. **`/api/board` claimed nothing is silently discarded and discarded rows.**
   `truncated` compared the window against the rows *fetched* rather than the
   rows *returned*, so a row dropped by the `live_ages` re-decision was counted
   in `in_window`, absent from every bucket, and set nothing.

**What this does not establish.**

- The frontend assertions are over **source text**, because this repo has no JS
  test runner (`frontend/package.json` has `dev`, `build`, `start`, `lint` and
  no test script). They check that the components consult the shared tone and
  never name the positive colour themselves. They do **not** render anything, so
  they cannot prove a class reaches the DOM, that the palette is legible, or
  that the layout is right on a phone. Only opening the page does that.
- Nothing here establishes that a suppression rule is *correctly calibrated*, or
  that `actionable_total` being zero is the right answer. It checks that
  whatever the server decided is what the screen says.
- `TestEveryPathASuppressedRowCanReachTheScreenBy` is an inventory of the paths
  as they exist today. A new screen that renders `edge_cents` will be caught by
  the anchor test only if it also names a tone colour; one that invents its own
  way to say "good" would not be.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from backend.api.routes import create_app
from backend.config import AppConfig

# The board fixtures already exist and there must not be two INSERTs encoding
# one row shape. `_slate_row` is the one that knows which columns
# `gate.live_ages` reads, including the half-written confirmation this module
# needs and would otherwise have to reproduce from the schema.
from tests.test_api import _every_row, _slate_row, get

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
API_TS = FRONTEND / "lib" / "api.ts"
# The Board page, its slate row and the Ledger page were deleted 2026-10-10
# (#342); what remains here is the shared tone helper, the Slate page and the
# `/api/board` route, which stays.
SLATE_PAGE = FRONTEND / "app" / "slate" / "page.tsx"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code(path: Path) -> str:
    """The file with its comments removed.

    The assertions about which class names a component *uses* must not be
    satisfied or broken by a docstring that quotes one. This repo's components
    carry long comments naming the exact classes they no longer use, and that is
    the documentation working rather than the guard failing.
    """
    text = re.sub(r"/\*.*?\*/", "", source(path), flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def block(text: str, opener: str, closer: str) -> str:
    """The text between `opener` and the next `closer`. Raises if absent.

    Deliberately not a regex over the whole file: every use here wants one
    named declaration, and a pattern that silently matches nothing is how a
    source-text test goes vacuous.
    """
    assert opener in text, f"{opener!r} is not in the file this test reads"
    rest = text.split(opener, 1)[1]
    assert closer in rest, f"{opener!r} is not closed by {closer!r}"
    return rest.split(closer, 1)[0]


# ---------------------------------------------------------------------------
# 1. Colour is a claim, not the sign of a subtraction.
# ---------------------------------------------------------------------------


class TestARefusedRowIsNeverPaintedAsMoney:
    def test_the_files_this_module_reads_are_the_ones_it_thinks_they_are(self):
        """A capture-style anchor.

        Every assertion below is a string search, and the failure mode of a
        string search is agreeing perfectly with a file that no longer contains
        the thing being tested. If the tone helper is renamed or moved, this
        says so instead of letting four tests pass over its absence.
        """
        api = source(API_TS)
        assert "export function edgeTone(" in api
        assert "export const EDGE_TONE_CLASS" in api
        assert "export function hasSuppression(" in api

    def test_suppression_is_consulted_before_the_sign_of_the_subtraction(self):
        # From the opening brace, so the parameter's type annotation -- which
        # names both fields -- cannot stand in for reading either of them.
        body = block(source(API_TS), "): EdgeTone {", "\n}")
        first_reason = body.index("suppressed_reason")
        assert "edge_cents" in body, "the tone must still fall back to the sign"
        assert first_reason < body.index("edge_cents"), (
            "edgeTone reached the sign of the edge before it looked at whether "
            "the row was refused, which is the original defect exactly."
        )

    def test_the_positive_tone_is_unreachable_for_a_refused_row(self):
        body = block(source(API_TS), "): EdgeTone {", "\n}")
        assert body.index("suppressed_reason") < body.index('"positive"'), (
            'edgeTone can return "positive" without having consulted '
            "suppressed_reason."
        )

    def test_no_refused_tone_maps_to_the_positive_colour(self):
        classes = block(source(API_TS), "export const EDGE_TONE_CLASS", "\n};")
        for tone in ("suspect", "refused"):
            line = next(
                ln for ln in classes.splitlines() if ln.strip().startswith(tone + ":")
            )
            assert "text-positive" not in line, (
                f"the {tone} tone renders a refused row in the colour that "
                f"means take this."
            )

    def test_suspicious_edge_is_escalated_beyond_the_other_refusals(self):
        """`suspicious_edge` is the code that means the data is broken.

        It is also the code whose rows sort to the top of any edge ranking, so
        it is the one that must not read as a quieter version of the same
        thing. The escalation is structural rather than a second hue: a filled
        chip, so the figure stops reading as a figure.
        """
        classes = block(source(API_TS), "export const EDGE_TONE_CLASS", "\n};")
        lines = {
            ln.split(":", 1)[0].strip(): ln
            for ln in classes.splitlines()
            if ":" in ln and ln.strip()
        }
        assert "bg-" in lines["suspect"], (
            "the suspect tone is colour alone, so it reads as one more shade "
            "beside the other refusals."
        )
        assert "bg-" not in lines["refused"]
        assert lines["suspect"] != lines["refused"]

    def test_the_tone_survives_the_colour_being_invisible(self):
        """Roughly one man in twelve cannot separate these two hues. A rule
        carried by colour alone is carried by nothing for those readers.

        The second half of this reason -- "`--negative` is the same red as
        `--accent`" -- was true until ADR 0081 and is not the reason the mark
        exists."""
        marks = block(source(API_TS), "export const EDGE_TONE_MARK", "\n};")
        suspect = next(
            ln for ln in marks.splitlines() if ln.strip().startswith("suspect:")
        )
        # `[^"]`, not `\S`: an empty string is two quote characters and `\S`
        # matches the closing one, so the obvious pattern passes on exactly the
        # value it exists to reject. Caught by mutating the map to `""`.
        assert re.search(r':\s*"[^"]', suspect), (
            "the suspect tone has no non-colour cue, so on a monochrome or "
            "colour-blind reading it is identical to a bettable row."
        )

    def test_a_row_that_broke_several_rules_still_matches_by_code(self):
        """`suppressed_reason` is a comma-joined list.

        `SuppressionResult.reason` joins every failed check with `,`, so
        `suspicious_edge,wide_market` is as ordinary as the single word — and an
        equality test would quietly miss the rows that broke the most rules,
        which are the ones worth shouting about.
        """
        body = block(source(API_TS), "export function hasSuppression(", "\n}")
        assert '","' in body or "','" in body, (
            "hasSuppression does not split the comma-joined reason list, so a "
            "row reading 'suspicious_edge,wide_market' escapes the loud tone."
        )

class TestAZeroContractRowIsNeverPaintedAsMoney:
    """The second bound on the same quantity.

    `no_edge` on the wire means `suggested_contracts == 0` with no suppression
    code (`backend/api/routes.py`, the bucket split) — the sizer refused the
    row, not a rule. `edgeTone` used to consult only `suppressed_reason`, so
    these rows fell through to the sign test and a `+4.1c` the bankroll cannot
    buy rendered `text-positive`. Below ~$250 of bankroll quarter-Kelly sizes
    under one contract across the whole band, so this was the modal row.
    """

    def test_the_size_is_consulted_before_the_sign_of_the_subtraction(self):
        body = block(source(API_TS), "): EdgeTone {", "\n}")
        assert "suggested_contracts" in body, (
            "edgeTone no longer reads suggested_contracts, so a zero-sized row "
            "is coloured by the sign of a subtraction its bankroll cannot buy."
        )
        assert body.index("suggested_contracts") < body.index('"positive"'), (
            'edgeTone can return "positive" without having consulted the size.'
        )

    def test_the_suppression_codes_still_outrank_the_size(self):
        """`suspicious_edge` must stay the loudest claim on the row. A
        zero-sized suspect row is a data defect first and an unbettable row
        second, and the chip treatment must win."""
        body = block(source(API_TS), "): EdgeTone {", "\n}")
        assert body.index("suppressed_reason") < body.index("suggested_contracts")

    def test_no_cell_of_the_cross_product_renders_positive_at_zero_size(self):
        """The behaviour itself, not its source text — run the real function.

        Node strips erasable TypeScript natively, so the actual `edgeTone` and
        `hasSuppression` declarations are copied into a scratch module and
        executed over every combination of edge sign and suppression state at
        `suggested_contracts: 0`. None may come back "positive".
        """
        api = source(API_TS)
        fns = "".join(
            f"export function {name}(" + block(api, f"export function {name}(", "\n}") + "\n}\n"
            for name in ("hasSuppression", "edgeTone")
        )
        # The Pick<> annotations reference the Recommendation interface; a
        # local alias keeps the scratch module self-contained.
        harness = (
            "type Recommendation = { edge_cents: number; "
            "suppressed_reason: string | null; suggested_contracts: number };\n"
            + fns
            + """
for (const edge_cents of [5, 0, -5]) {
  for (const suppressed_reason of [null, "stale_odds"]) {
    const tone = edgeTone({ edge_cents, suppressed_reason, suggested_contracts: 0 });
    if (tone === "positive") {
      console.error(`positive at zero size: edge=${edge_cents} reason=${suppressed_reason}`);
      process.exit(1);
    }
  }
}
"""
        )
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            tmp_ts = Path(d) / "edge_tone_cross_product.ts"
            tmp_ts.write_text(harness, encoding="utf-8")
            node = shutil.which("node")
            if node is None:
                pytest.skip("node is not on PATH; the source assertions above still hold")
            scratch = subprocess.run(
                [node, str(tmp_ts)], capture_output=True, text=True, timeout=60
            )
        assert scratch.returncode == 0, (
            "a zero-contract row rendered as money:\n" + scratch.stderr + scratch.stdout
        )


class TestEveryPathASuppressedRowCanReachTheScreenBy:
    """The point of the fix, checked rather than assumed.

    One component does not own this. The Board, its slate rows and the Ledger
    were the screens a refused row reached; all three were deleted (#342,
    2026-10-10), so the inventory below is now empty by construction and any
    screen that colours an edge has to be decided here again.
    """

    def colouring_screens(self) -> set[str]:
        found = set()
        for path in FRONTEND.rglob("*.tsx"):
            text = source(path)
            if "edge_cents" not in text:
                continue
            if "text-positive" in text or '"positive"' in text:
                found.add(path.relative_to(FRONTEND).as_posix())
        return found

    def test_no_screen_colours_an_edge_without_being_accounted_for(self):
        """The anchor that makes this an inventory rather than a snapshot.

        A new screen rendering `edge_cents` in a tone colour fails here until
        somebody decides whether it asks `edgeTone` or the engine invariant
        says no refused row can reach it. The accounted set is empty today.
        """
        assert self.colouring_screens() == set()

    def test_the_slate_screen_renders_no_edge_at_all(self):
        """Inverted 2026-08-21, and the inversion is the point.

        This test used to require the Slate to colour its edge column through
        the shared tone. The partner's betting-desk ruling (docs/reviews/
        2026-08-21-items-2-3-ruling.md, executing ADR 0062) took the edge
        point estimate OFF the landing screen entirely: the Board, one tap
        away, is the edge-finder feature and still renders it through the
        tone map, which the tests around this one still enforce. What the
        landing screen must now do is stronger than colouring correctly --
        it must not render the number at all, in any ink, because a point
        estimate the record measured at beta = -0.141 is not a fact a
        deciding screen may lead with.

        `edge_tenths`/`edge_cents` may appear in comments explaining their
        own absence; `code()` strips those. Mutation observed red: re-add
        `row.edge_cents.toFixed(1)` to the row.
        """
        slate = code(SLATE_PAGE)
        assert "edge_cents" not in slate, (
            "the Slate renders the edge point estimate again -- the ruling "
            "that removed it is dated and named in the page docstring"
        )
        assert "edgeTone" not in slate and "EDGE_TONE_CLASS" not in slate, (
            "the Slate consults the edge tone machinery, which means an edge "
            "is being coloured somewhere on the landing screen"
        )

    def test_the_allowlisted_screens_really_cannot_receive_a_refused_row(self):
        """The allowlist above is a claim about the engine, so check it there.

        A refused row with a positive size would render as a bettable card the
        server then refuses with a 422 -- the failure `engine.py` names -- and
        it would also walk straight past the tone fix, because those cards read
        `suggested_contracts` rather than `suppressed_reason`.
        """
        import inspect

        from backend import engine

        built = inspect.getsource(engine.build_recommendation)
        assert "contracts = 0 if (result.suppressed" in built, (
            "build_recommendation no longer zeroes the size on suppression, so "
            "a refused row can reach the surfaced cards."
        )
        added = inspect.getsource(engine.with_added_suppression)
        assert "suggested_contracts=0" in added


# ---------------------------------------------------------------------------
# 2. The screen's central fact.
# ---------------------------------------------------------------------------


def _one_row_db(tmp_path, name: str):
    from backend.store import db as store

    path = tmp_path / name
    conn = store.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    return path, conn


class TestTheBoardStatesTheRecordAndNotOnlyTheSlate:
    """"Bettable now: 0" is a claim about half an hour. The finding is about
    the whole record, and windowing the Board correctly is what took it away."""

    @pytest.fixture
    def record(self, tmp_path):
        from backend.store.db import now_ms

        path, conn = _one_row_db(tmp_path, "record.db")
        now = now_ms()
        # In the slate, and nothing the strategy would have bet.
        _slate_row(conn, ticker="KXNOW-A", created_ms=now - 30_000)
        _slate_row(conn, ticker="KXNOW-B", created_ms=now - 31_000,
                   suppressed="suspicious_edge")
        # Out of the slate by hours, and the one row the gate would count. It
        # must reach `actionable_total` and no other number on the payload.
        _slate_row(conn, ticker="KXOLD", created_ms=now - 6 * 3_600_000,
                   contracts=3)
        conn.commit()
        conn.close()
        return create_app(AppConfig(instance_mode="demo", db_path=path))

    async def test_the_payload_counts_the_whole_record_not_the_window(self, record):
        slate = (await get(record, "/api/board?include_suppressed=true")).json()["slate"]
        assert slate["recorded_total"] == 3
        assert slate["in_window"] == 2
        assert slate["actionable_total"] == 1, (
            "actionable_total is being computed over the slate, so the Board "
            "would report a quiet half-hour as the life of the record."
        )

    async def test_a_refused_row_never_counts_as_actionable(self, tmp_path):
        """The gate's predicate is `suppressed_reason IS NULL AND
        reference_contracts > 0`, and this reads it rather than restating it --
        a screen and an admission criterion that derive one number by two paths
        eventually disagree, and the screen is the one that gets believed."""
        from backend.store.db import now_ms

        path, conn = _one_row_db(tmp_path, "refused.db")
        now = now_ms()
        # Sized *and* refused: the shape that would flatter the count.
        _slate_row(conn, ticker="KXREFUSED", created_ms=now - 30_000,
                   contracts=5, suppressed="suspicious_edge")
        conn.commit()
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))

        slate = (await get(app, "/api/board?include_suppressed=true")).json()["slate"]
        assert slate["recorded_total"] == 1
        assert slate["actionable_total"] == 0

    async def test_an_empty_database_reports_zero_of_zero(self, tmp_path):
        from backend.store import db as store

        path = tmp_path / "empty.db"
        store.init_db(path).close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        slate = (await get(app, "/api/board")).json()["slate"]
        assert slate["recorded_total"] == 0
        assert slate["actionable_total"] == 0

# ---------------------------------------------------------------------------
# 3. Nothing is silently discarded -- now true.
# ---------------------------------------------------------------------------


class TestNothingLeavesTheSlateWithoutBeingCounted:
    """`/api/board`'s docstring made this claim and the arithmetic broke it.

    `in_window` comes from the SQL basis; the loop then re-decides each row on
    `gate.live_ages`, which is the stricter reading, and dropped the losers with
    a bare `continue`. `truncated` compared `in_window` against the rows
    *fetched*, so such a row was counted in the window, returned in nothing, and
    set no flag. The page printed nothing about it.
    """

    @pytest.fixture
    def half_written(self, tmp_path):
        """One current row, and one whose confirmation is half written.

        The half-written row is newer to SQL (`MAX(created_ms,
        COALESCE(last_confirmed_ms, created_ms))` takes the timestamp at face
        value) and four hours old to `live_ages`, which requires both
        confirmed ages beside it. That asymmetry is deliberate and is the only
        way a row leaves the slate after being counted into it.
        """
        from backend.store.db import now_ms

        path, conn = _one_row_db(tmp_path, "halfwritten.db")
        now = now_ms()
        _slate_row(conn, ticker="KXNOW", created_ms=now - 30_000)
        _slate_row(conn, ticker="KXHALF", created_ms=now - 4 * 3_600_000,
                   confirmed_ms=now - 40_000, confirmed_ages=False)
        conn.commit()
        conn.close()
        return create_app(AppConfig(instance_mode="demo", db_path=path))

    async def test_the_fixture_really_produces_the_disagreement(self, half_written):
        """Without this the two counts could agree because nothing was dropped,
        and every assertion below would hold over an empty case."""
        body = (await get(half_written, "/api/board?include_suppressed=true")).json()
        assert body["slate"]["in_window"] == 2
        assert {r["ticker"] for r in _every_row(body)} == {"KXNOW"}

    async def test_the_dropped_row_is_counted_in_its_own_field(self, half_written):
        slate = (await get(half_written, "/api/board?include_suppressed=true")).json()[
            "slate"
        ]
        assert slate["off_basis"] == 1

    async def test_the_page_is_told_the_slate_is_incomplete(self, half_written):
        """`truncated` is what the page reads to print "showing N of M". It
        compared against the rows fetched, so this stayed False."""
        slate = (await get(half_written, "/api/board?include_suppressed=true")).json()[
            "slate"
        ]
        assert slate["returned"] == 1
        assert slate["truncated"] is True

    async def test_the_window_accounts_for_every_row_it_counted(self, half_written):
        """The identity the claim reduces to, with no `LIMIT` in play."""
        slate = (await get(half_written, "/api/board?include_suppressed=true")).json()[
            "slate"
        ]
        assert slate["in_window"] == slate["returned"] + slate["off_basis"]

    async def test_a_complete_slate_reports_neither(self, tmp_path):
        """The negative case. A flag that is always on says nothing."""
        from backend.store.db import now_ms

        path, conn = _one_row_db(tmp_path, "clean.db")
        now = now_ms()
        for i in range(3):
            _slate_row(conn, ticker=f"KXNOW-{i}", created_ms=now - 30_000 - i)
        conn.commit()
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))

        slate = (await get(app, "/api/board?include_suppressed=true")).json()["slate"]
        assert slate["off_basis"] == 0
        assert slate["truncated"] is False
        assert slate["returned"] == slate["in_window"] == 3

    async def test_the_limit_and_the_re_decision_are_reported_separately(
        self, tmp_path
    ):
        """Two unrelated reasons a row is missing. Folding the second into the
        first would say `LIMIT` did something `LIMIT` did not do, and send
        anyone reading the page looking in the wrong place."""
        from backend.store.db import now_ms

        path, conn = _one_row_db(tmp_path, "both.db")
        now = now_ms()
        for i in range(4):
            _slate_row(conn, ticker=f"KXNOW-{i}", created_ms=now - 30_000 - i)
        _slate_row(conn, ticker="KXHALF", created_ms=now - 4 * 3_600_000,
                   confirmed_ms=now - 40_000, confirmed_ages=False)
        conn.commit()
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))

        slate = (
            await get(app, "/api/board?include_suppressed=true&limit=3")
        ).json()["slate"]
        assert slate["in_window"] == 5
        assert slate["returned"] == 3
        assert slate["off_basis"] == 0, (
            "the LIMIT took the three newest rows, so the half-written row was "
            "never fetched and must not be reported as re-decided."
        )
        assert slate["truncated"] is True

    def test_the_docstring_states_the_claim_it_now_keeps(self):
        """The claim was to be made true, not deleted."""
        from backend.api import routes

        text = source(Path(routes.__file__))
        assert "Nothing is silently discarded" in text
        assert "slate.off_basis" in text

# ---------------------------------------------------------------------------
# 4. The lesson goes below the prices.
# ---------------------------------------------------------------------------


class TestFairAndBreakevenNeverShareTheRow:
    """**The claim is unchanged; the direction was inverted 2026-08-24.**

    This class was `TestBreakevenShipsAloneOnTheScreen` (fleet convening item
    6, the screen half). The property it guards has never moved: `edge_tenths`
    is exactly 1000 x (fair - breakeven), so the slate row may carry **one** of
    those two and never both, or the reader reconstructs the measured-negative
    edge by subtraction.

    What changed is which one. ADR 0071 section 2.2 settles the desk's job as
    price transparency -- what Kalshi charges against what the sharps say it is
    worth -- and under that job fair is the number the row lacks, while
    break-even is the ask with the fee added rather than a third fact. Joe's
    answer, 2026-08-24, Q17. Ask stays a price and fair stays a probability
    (`format_price` vs `format_probability`), so their difference is not the
    edge: the fee is missing from it.

    The convening's own reasoning is what permits this rather than what
    forbids it -- item 6 argued the row needs a number that makes the price a
    decision, not that the number must be break-even specifically.

    The API half is untouched: `test_api.py::TestBreakevenShipsAlone` still
    requires `breakeven_win_rate` on every priced row of the **payload**. It
    left the component, not the wire, so the market screen and the Board can
    still render it.
    """

    def test_the_slate_row_renders_fair(self):
        assert "fair_percent_display" in code(SLATE_PAGE)

    def test_breakeven_does_not_co_render(self):
        """The inverted assertion. Was `assert "breakeven_win_rate" in ...`.

        Mutation-verified red 2026-08-24 by restoring the break-even span
        beside the new fair one -- which is exactly the co-render the class
        forbids, and the reason this is a swap rather than an addition.
        """
        assert "breakeven_win_rate" not in code(SLATE_PAGE)

    def test_the_raw_fair_float_still_does_not_render(self):
        """Unchanged, and it survives the swap for its original reason.

        The row renders the **server-formatted string**, never the float:
        `core/prices.py:130-143` records that a fair value put through
        `format_price` came out as `53.8c` and sat beside a real ask at the
        same type size, "the one place a left-to-right scan reads the wrong
        number as the thing you pay". Rendering the float here would invite
        exactly that, plus the client-side arithmetic the money rule forbids.
        """
        assert "fair_probability" not in code(SLATE_PAGE)
        for method in ("p_multiplicative", "p_additive", "p_power", "p_shin",
                       "p_conservative"):
            assert method not in code(SLATE_PAGE)

    def test_the_fair_cell_is_unconditional(self):
        """A latent column-shift bug the swap had to avoid inheriting.

        The break-even span rendered only when `breakeven_win_rate !== null`,
        so on a row with no tradeable price the xl grid lost a child and every
        column from `Books` rightward shifted one track left. The eleven-track
        template has no slack for that. `fair_percent_display` is server-made
        and already carries `--` for an unreadable value, so the cell is
        always present -- asserted here because the failure is silent and
        only visible as a misaligned desktop row.
        """
        page = code(SLATE_PAGE)
        assert "fair_percent_display !== null &&" not in page
        assert "fair_percent_display &&" not in page


class TestMoneyRendersWithoutAVerdict:
    """Fleet convening item 5, the screen half."""

    def test_cash_and_open_positions_render_separately(self):
        """Since 2026-08-22 (B2/B3) the page renders server-made display
        strings (`cash_display`) and the open-position block lives in its own
        component, still a sibling of the money line and still never summed
        with it — the property this class exists for is unchanged."""
        page = code(SLATE_PAGE)
        assert "cash_display" in page
        assert "<OpenPositions" in page

    def test_nothing_arithmetically_combines_them(self):
        """Mutation observed red: render
        `(cash_tenths + open_positions_tenths) / 1000` as a total."""
        page = code(SLATE_PAGE)
        for expr in (
            "cash_tenths +",
            "+ data.money.cash_tenths",
            "open_positions_tenths +",
            "+ data.money.open_positions_tenths",
            "cash_tenths -",
            "- data.money.open_positions_tenths",
        ):
            assert expr not in page, f"the money line combines its facts: {expr!r}"

    def test_the_study_ceiling_is_not_the_denominator(self):
        """The $100 ceiling reads as budget remaining to a reader holding $8.
        The only line on this screen is the daily-loss cap derived from his
        balance — rendered since 2026-08-22 (B2) as the server's
        `daily_line_display` string rather than a client-formatted float.

        2026-09-30 (#228): that line is gone too. ADR 0112 removed the
        daily-loss cap from the hand-bet path on 2026-09-08, so the screen
        stopped naming a cap that binds nothing."""
        page = code(SLATE_PAGE)
        assert "ceiling_dollars" not in page
        assert "daily_line_display" not in page
