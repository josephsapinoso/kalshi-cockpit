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
SLATE_ROW = FRONTEND / "components" / "SlateRow.tsx"
BOARD_PAGE = FRONTEND / "app" / "page.tsx"
LEDGER_PAGE = FRONTEND / "app" / "ledger" / "page.tsx"


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
        assert "edgeTone" in source(SLATE_ROW)

    def test_the_slate_row_never_names_the_positive_colour_itself(self):
        """The mechanism, not just the outcome.

        A component that keeps its own `text-positive` branch beside the shared
        tone is one edit away from the original defect, and the edit would look
        like a simplification.
        """
        assert "text-positive" not in code(SLATE_ROW), (
            "SlateRow must take its edge colour from EDGE_TONE_CLASS, so that "
            "'is this number money?' is answered in one place."
        )

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
        """Roughly one man in twelve cannot separate these two hues, and
        `--negative` is the same red as `--accent`. A rule carried by colour
        alone is carried by nothing for those readers."""
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

    def test_the_reason_is_not_rendered_at_the_weight_of_a_footnote(self):
        """The other half of the defect. The code naming the row a defect was
        `text-muted` on every row while the edge beside it was bright green."""
        row = source(SLATE_ROW)
        rejected = block(row, 'resolved === "rejected"', "}")
        assert "text-muted" not in rejected or "text-accent" in row, (
            "the suppression reason still renders in the muted colour with no "
            "escalated branch beside it."
        )


class TestEveryPathASuppressedRowCanReachTheScreenBy:
    """The point of the fix, checked rather than assumed.

    One component does not own this. A row carrying `suppressed_reason` is
    rendered by the Board's slate rows *and* by the Ledger, which lists every
    recommendation the database holds.
    """

    # Screens that colour an edge and cannot receive a refused row, with the
    # reason each one is safe. `build_recommendation` and
    # `with_added_suppression` both zero `suggested_contracts` on suppression
    # (asserted below), and `/api/board` only routes rows with
    # `suggested_contracts > 0` into `surfaced`/`expired` -- which are the only
    # rows these three ever see.
    CANNOT_RECEIVE_A_REFUSED_ROW = {
        "components/OpportunityCard.tsx": "rendered by LiveBoard from board.surfaced",
        # Matches on both substrings without ever colouring an edge: its
        # `edge_cents` is a field of the streamed quote it merges into a row,
        # and its `text-positive` is the LIVE feed-status chip. Kept in the
        # inventory rather than special-cased -- a screen that holds both names
        # for unrelated reasons today is one edit from holding them for the
        # related one.
        "components/LiveBoard.tsx": "board.surfaced only; colours a feed status, not an edge",
        "components/TicketSheet.tsx": "opens only for a surfaced row",
    }

    # The two screens a row carrying `suppressed_reason` actually reaches, and
    # therefore the two that must ask `edgeTone` rather than the sign. The
    # Ledger was the second one and was fixed one lane later than the Board.
    TAKE_THE_SHARED_TONE = {
        "components/SlateRow.tsx",
        "app/ledger/page.tsx",
    }

    def colouring_screens(self) -> set[str]:
        found = set()
        for path in FRONTEND.rglob("*.tsx"):
            text = source(path)
            if "edge_cents" not in text:
                continue
            if "text-positive" in text or '"positive"' in text:
                found.add(path.relative_to(FRONTEND).as_posix())
        return found

    def test_the_inventory_is_not_empty(self):
        """Without this the set could collapse to nothing and every membership
        assertion below would hold vacuously."""
        assert len(self.colouring_screens()) >= 4

    def test_no_screen_colours_an_edge_without_being_accounted_for(self):
        """The anchor that makes this an inventory rather than a snapshot.

        A new screen rendering `edge_cents` in a tone colour fails here until
        somebody decides which of the two groups it belongs to: it asks
        `edgeTone`, or the engine invariant says no refused row can reach it.
        """
        accounted = self.TAKE_THE_SHARED_TONE | set(self.CANNOT_RECEIVE_A_REFUSED_ROW)
        assert self.colouring_screens() <= accounted

    def test_the_board_slate_row_takes_the_shared_tone(self):
        assert "edgeTone" in source(SLATE_ROW)

    def test_the_ledger_takes_the_shared_tone(self):
        """The Ledger is the *wider* of the two paths, not a lesser one.

        The Board shows one windowed slate; the Ledger lists every
        recommendation the database holds, so before this every
        `suspicious_edge` row ever written rendered in the colour that means
        take this. This was a strict xfail while the file sat outside the
        Board lane's ownership.

        Asserting only that the name `edgeTone` appears in the file would pass
        on an import nothing calls, and on a file that computes the tone and
        then colours the span by the sign anyway. So: the helper is *called*,
        the class map is keyed on what it returned, and no sign-of-edge test
        reaches a tone colour.
        """
        ledger = code(LEDGER_PAGE)

        call = re.search(r"(?:const|let)\s+(\w+)\s*=\s*edgeTone\(\s*rec\s*\)", ledger)
        assert call, (
            "the Ledger does not call edgeTone on its row, so any tone name it "
            "mentions came from somewhere else."
        )
        tone = call.group(1)
        assert f"EDGE_TONE_CLASS[{tone}]" in ledger, (
            "the Ledger computes the shared tone and does not colour the edge "
            "with it, which renders exactly as the original defect."
        )
        assert f"EDGE_TONE_MARK[{tone}]" in ledger, (
            "the Ledger carries the rule in colour alone, so for a reader who "
            "cannot separate the two hues a suspicious_edge row is identical "
            "to a bettable one."
        )

    def test_the_ledger_never_decides_a_tone_colour_from_the_sign(self):
        """The mechanism, not just the presence of the call.

        `text-positive` legitimately survives on this page for `clv_tenths` --
        a settled measurement against Kalshi's close, which is an outcome
        rather than a claim that a number is money. What must not survive is a
        tone colour chosen from `edge_cents` in the same expression, which is
        the defect verbatim.
        """
        ledger = code(LEDGER_PAGE)
        # `[^;{}]`: one JSX expression. The defect was
        # `rec.edge_cents > 0 ? "text-positive" : "text-negative"`, with
        # nothing but a comparison and a quote between the two names.
        for pattern in (
            r"edge_cents[^;{}]*text-(?:positive|negative)",
            r"text-(?:positive|negative)[^;{}]*edge_cents",
        ):
            assert not re.search(pattern, ledger), (
                "the Ledger picks a tone colour from the sign of the edge, "
                "with no reference to whether the row was refused."
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

    def test_the_page_renders_both_halves_of_the_sentence(self):
        page = source(BOARD_PAGE)
        assert "slate.actionable_total" in page, (
            "the count the whole page exists to report is in the payload and "
            "on no screen, which is the defect."
        )
        assert "slate.recorded_total" in page

    def test_the_page_does_not_hardcode_the_finding(self):
        """A zero typed into the copy goes on reading as a finding on the day
        it stops being one."""
        page = source(BOARD_PAGE)
        sentence = block(page, "Bettable now", "</p>")
        assert "actionable_total" in sentence
        assert not re.search(r">\s*0\s*(?:of|<)", sentence)


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

    def test_the_page_says_something_about_the_dropped_rows(self):
        """Both halves: the guard that decides whether to speak, and the number
        it speaks. Asserting only that the field is mentioned somewhere passes
        on a block that is mentioned and never rendered."""
        page = source(BOARD_PAGE)
        assert "board.slate.off_basis > 0 && (" in page, (
            "nothing on the page is conditional on rows having been dropped, "
            "so they are accounted for in the payload and still vanish on the "
            "screen."
        )
        assert "{board.slate.off_basis}" in page, (
            "the page reacts to the drops without ever saying how many."
        )


# ---------------------------------------------------------------------------
# 4. The lesson goes below the prices.
# ---------------------------------------------------------------------------


class TestThePhoneReachesAPriceBeforeALesson:
    """`HowToRead` is ~1,700px of a ~9,000px page and sat between the counts and
    the cards, so every phone load scrolled past it to reach a price. The copy
    is good and is unchanged; only the placement moved."""

    def test_the_how_to_read_block_is_rendered_after_the_slate(self):
        page = source(BOARD_PAGE)
        assert "<HowToRead />" in page
        assert page.index("<HowToRead />") > page.index("The rest of the slate"), (
            "the explainer is still between the counts and the prices."
        )

    def test_the_copy_was_moved_and_not_rewritten(self):
        """The reviewer singled the writing out as good. This lane owns the
        call site, not the component, so the component must be untouched."""
        component = source(FRONTEND / "components" / "HowToRead.tsx")
        assert "How to read this board" in component
        for phrase in (
            "You need to be right 52 times in 100 here, not 50.",
            "The price is the one in cents. The percentage is not a price.",
            "The biggest edge on the board is deliberately held back.",
            "The swing is far larger than the edge, every time.",
        ):
            assert phrase in component

    def test_the_prose_the_reviewer_kept_is_still_there(self):
        """Two passages were named as genuinely good and stay verbatim: the
        three-way empty-board split, and the sentence about Kalshi pricing
        sports to two cents."""
        page = source(BOARD_PAGE)
        for phrase in (
            "Nothing recorded yet",
            "Nothing bettable now",
            "Nothing to bet",
            "about two cents against a",
        ):
            assert phrase in page
