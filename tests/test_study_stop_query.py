"""`study-stop` re-implements a decision-bearing formula, so it is pinned.

`inspect_live_db.py` imports nothing from `backend` on purpose -- it is the one
script permitted to run against the live database, and a dependency on
application code would mean a deploy could change what the inspector computes.
The price is that ADR 0044 §5 arm 3's formula now exists **twice**: in
`backend.estimates.study_loss_dollars` and in `_q_study_stop`.

Two implementations of a stopping rule is a liability. This file makes them
agree by running both over the same fixtures -- including every refusal path,
because the refusals are the part that matters: `None` means *cannot know* and
must never be rendered as "not stopped".

Why the query exists at all
---------------------------
`POST /api/estimates` returns 423 with *"The study is stopped and logging is
closed, permanently"* once the arm fires. Decision-map ticket #11 (resolved
2026-09-01) repurposes that endpoint for a practice log decoupled from the
study, and its first build step is "read the arm's current value" -- which
nothing on the machine could do. The alternative was smuggling SQL onto the
money box in an `ssh` command line, which is the exact drift
`inspect_live_db.py` was created to end.

What this file does not establish
---------------------------------
- **Anything about the live value.** Every fixture is a `tmp_path` database.
- **That the registered formula is right.** It pins the two implementations to
  each other; the registration is the authority for the formula itself.
- **That the endpoint is reachable.** The self-lockout is a second, independent
  423, and this file only checks it is *reported*, not that it is honoured.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from backend import estimates
from backend.portfolio_poll import STUDY_START_MS_KEY
from backend.store import db

START_MS = 1_787_000_000_000


def _read(db_path: Path) -> dict:
    from scripts.inspect_live_db import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["study-stop", "--db", str(db_path), "--json"])
    assert rc == 0, buf.getvalue()
    rows = json.loads(buf.getvalue())["sections"][0]["rows"]
    return {r[0]: r[1] for r in rows}


def _settle(conn, *, side, contracts, entry, fee, result, ms=START_MS + 1):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f"T{ms}", "E", result, ms, side, contracts, entry, fee),
    )


def _build(tmp_path: Path, rows, *, open_study: bool = True) -> Path:
    path = tmp_path / "cockpit.db"
    conn = db.init_db(path)
    if open_study:
        conn.execute(
            "INSERT INTO meta (key, value, updated_ms) VALUES (?, ?, ?)",
            (STUDY_START_MS_KEY, str(START_MS), START_MS),
        )
    for i, row in enumerate(rows):
        _settle(conn, ms=START_MS + 1 + i, **row)
    conn.commit()
    conn.close()
    return path


WIN = dict(side="yes", contracts=2, entry=400, fee=10, result="yes")
LOSS = dict(side="yes", contracts=2, entry=400, fee=10, result="no")


class TestTheTwoImplementationsAgree:
    """The whole reason this file exists. If these diverge, the inspector is
    reporting a different stopping rule than the one the endpoint enforces --
    and the inspector is what a session will believe."""

    @pytest.mark.parametrize(
        "rows",
        [
            [],
            [WIN],
            [LOSS],
            [WIN, LOSS],
            [LOSS, LOSS, LOSS],
            [dict(side="no", contracts=5, entry=550, fee=17, result="no")],
            [dict(side="no", contracts=5, entry=550, fee=17, result="yes")],
        ],
        ids=["empty", "win", "loss", "mixed", "three-losses", "no-win", "no-loss"],
    )
    def test_the_loss_figure_matches_the_backend(self, tmp_path, rows):
        path = _build(tmp_path, rows)
        conn = db.connect(path)
        try:
            expected = estimates.study_loss_dollars(conn)
        finally:
            conn.close()

        reported = _read(path)["cumulative realised LOSS ($)"]
        assert reported == pytest.approx(expected), (
            f"the inspector and the endpoint disagree about the stopping "
            f"rule: {reported} vs {expected}"
        )

    def test_an_empty_study_is_zero_and_not_a_refusal(self, tmp_path):
        """A true $0.00 and a 'cannot know' are different answers, and the
        registered formula says an open study with no settlements is the
        first."""
        out = _read(_build(tmp_path, []))
        assert out["cumulative realised LOSS ($)"] == 0.0
        assert out["refusal"] is None
        assert out["money arm fired"] is False


class TestTheRefusalsAreTriStateAndNeverReadAsNotStopped:
    """`None` is 'cannot know'. Rendering it as 'not stopped' would tell a
    session logging is open when the record cannot say so -- the flattering
    direction, which this repo has been burned by repeatedly."""

    def test_a_study_never_opened_refuses(self, tmp_path):
        out = _read(_build(tmp_path, [WIN], open_study=False))
        assert out["cumulative realised LOSS ($)"] is None
        assert out["money arm fired"] is None
        assert "never stamped open" in out["refusal"]

    def test_a_void_result_refuses_rather_than_inventing_a_payout(self, tmp_path):
        """A void has no registered payout. Guessing one here would silently
        amend the stopping rule, which is the one thing a stopping rule may
        never do."""
        path = _build(
            tmp_path,
            [dict(side="yes", contracts=2, entry=400, fee=10, result="void")],
        )
        conn = db.connect(path)
        try:
            assert estimates.study_loss_dollars(conn) is None
        finally:
            conn.close()

        out = _read(path)
        assert out["money arm fired"] is None
        assert "neither 'yes' nor 'no'" in out["refusal"]

    def test_an_unreadable_fee_refuses(self, tmp_path):
        path = _build(tmp_path, [])
        conn = db.connect(path)
        _settle(conn, side="yes", contracts=2, entry=400, fee=None, result="yes")
        conn.commit()
        try:
            assert estimates.study_loss_dollars(conn) is None
        finally:
            conn.close()

        out = _read(path)
        assert out["money arm fired"] is None
        assert "unreadable entry price or fee" in out["refusal"]

    def test_the_refusal_reading_says_it_is_not_an_all_clear(self, tmp_path):
        path = _build(tmp_path, [WIN], open_study=False)
        from scripts.inspect_live_db import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["study-stop", "--db", str(path)])
        rendered = buf.getvalue()
        assert "CANNOT KNOW" in rendered, rendered
        assert "may not be read as 'not stopped'" in rendered, rendered


class TestTheArmFiresAtTheRegisteredCeiling:
    def test_the_ceiling_matches_the_backend_constant(self):
        """Spelled twice because the script imports nothing from `backend`. A
        drifted ceiling would report the arm clear while the endpoint refuses."""
        from scripts.inspect_live_db import STUDY_LOSS_CEILING_DOLLARS

        assert STUDY_LOSS_CEILING_DOLLARS == estimates.STUDY_LOSS_CEILING_DOLLARS

    def test_a_loss_at_the_ceiling_fires(self, tmp_path):
        """$100 exactly. The registered predicate is `>=`, so the boundary
        fires -- and a boundary that is off by one contract is the difference
        between logging being open and closed."""
        # 250 contracts at 40c, no fee, all lost => $100.00 lost.
        rows = [dict(side="yes", contracts=250, entry=400, fee=0, result="no")]
        out = _read(_build(tmp_path, rows))
        assert out["cumulative realised LOSS ($)"] == pytest.approx(100.0)
        assert out["money arm fired"] is True

    def test_a_loss_just_under_the_ceiling_does_not_fire(self, tmp_path):
        rows = [dict(side="yes", contracts=249, entry=400, fee=0, result="no")]
        out = _read(_build(tmp_path, rows))
        assert out["cumulative realised LOSS ($)"] == pytest.approx(99.6)
        assert out["money arm fired"] is False


class TestTheSelfLockoutIsReportedSeparately:
    """A clear money arm does not mean logging is open. The lockout is a
    second, independent 423 with its own clock, and a reader who sees only the
    arm will conclude the endpoint is reachable when it is not."""

    def test_an_active_lockout_is_reported(self, tmp_path):
        import time

        path = _build(tmp_path, [])
        conn = db.connect(path)
        until = int(time.time() * 1000) + 3_600_000
        conn.execute(
            "INSERT INTO self_lockouts (requested_ms, until_ms) VALUES (?, ?)",
            (int(time.time() * 1000), until),
        )
        conn.commit()
        conn.close()

        out = _read(path)
        assert out["self-lockout until"] is not None, out
        assert out["money arm fired"] is False, (
            "the money arm and the lockout must be reported independently"
        )

    def test_no_lockout_reports_null_not_absent(self, tmp_path):
        out = _read(_build(tmp_path, []))
        assert "self-lockout until" in out
        assert out["self-lockout until"] is None


class TestTheRefusalCanBeSizedRatherThanJustNamed:
    """Added 2026-09-01, after the first live read refused on
    `market_result = ''` and the obvious next question -- one void, or half the
    record? -- had no instrument.

    The registered formula stops at the FIRST unreadable row, so its refusal
    message names one row and structurally cannot count them. A reader deciding
    whether a silently-inoperative $100 stop is a nuisance or an emergency
    needs the count, and taking it must not disturb the formula.
    """

    def _mix(self, db_path: Path) -> dict:
        from scripts.inspect_live_db import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert main(["study-stop", "--db", str(db_path), "--json"]) == 0
        section = json.loads(buf.getvalue())["sections"][1]
        return {r[0]: r[1] for r in section["rows"]}

    def test_the_unreadable_rows_are_counted_not_just_named(self, tmp_path):
        path = _build(
            tmp_path,
            [WIN, WIN, LOSS]
            + [dict(side="yes", contracts=1, entry=100, fee=1, result="")] * 4,
        )
        mix = self._mix(path)
        assert mix.get("'' (empty string)") == 4, mix
        assert mix.get("yes") == 2, mix
        assert mix.get("no") == 1, mix

    def test_the_section_says_which_values_break_the_formula(self, tmp_path):
        """A count without that mapping makes the reader re-derive which
        values are fatal, which is where they will guess wrong."""
        path = _build(
            tmp_path,
            [WIN, dict(side="yes", contracts=1, entry=100, fee=1, result="")],
        )
        from scripts.inspect_live_db import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["study-stop", "--db", str(path)])
        rendered = buf.getvalue()
        assert "REFUSES the whole formula" in rendered, rendered
        assert "computable" in rendered, rendered

    def test_counting_does_not_disturb_the_registered_figure(self, tmp_path):
        """The count is a second read over the same rows. If adding it changed
        the loss, the instrument would be altering what it measures."""
        rows = [WIN, LOSS, LOSS]
        path = _build(tmp_path, rows)
        conn = db.connect(path)
        try:
            expected = estimates.study_loss_dollars(conn)
        finally:
            conn.close()
        assert _read(path)["cumulative realised LOSS ($)"] == pytest.approx(
            expected
        )

    def test_a_null_result_is_shown_as_NULL_and_not_as_empty(self, tmp_path):
        """`NULL` and `''` are different failures -- one is the poller never
        writing, the other is it writing nothing. Collapsing them would hide
        which."""
        path = _build(tmp_path, [WIN])
        conn = db.connect(path)
        _settle(conn, side="yes", contracts=1, entry=100, fee=1, result=None,
                ms=START_MS + 900)
        conn.commit()
        conn.close()
        mix = self._mix(path)
        assert mix.get("NULL") == 1, mix


class TestTheOffendingRowsAreIdentifiedAndNotJustCounted:
    """A count tells you the arm is off. Only the row tells you whether the
    cause is a genuine void the formula should tolerate or a poller gap that
    will recur -- and since the repair is money-touching and Joe's, handing him
    a number he cannot act on is not a finding.
    """

    def _rows(self, db_path: Path) -> list[list]:
        from scripts.inspect_live_db import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert main(["study-stop", "--db", str(db_path), "--json"]) == 0
        return json.loads(buf.getvalue())["sections"][2]["rows"]

    def test_the_unreadable_row_is_named(self, tmp_path):
        path = _build(
            tmp_path,
            [WIN, dict(side="yes", contracts=3, entry=250, fee=7, result="")],
        )
        rows = self._rows(path)
        assert len(rows) == 1, rows
        rendered = json.dumps(rows[0])
        assert "result unreadable" in rendered, rendered
        assert "3" in rendered, rendered

    def test_a_readable_row_is_not_listed(self, tmp_path):
        """If this filled up on healthy rows it would cry wolf on every read,
        and the section would be ignored by the second look."""
        assert self._rows(_build(tmp_path, [WIN, LOSS])) == []

    def test_an_unreadable_fee_is_distinguished_from_an_unreadable_result(
        self, tmp_path
    ):
        """Three different causes refuse the same formula and need three
        different repairs. Collapsing them into 'unreadable' would send the
        reader to the wrong one."""
        path = _build(tmp_path, [])
        conn = db.connect(path)
        _settle(conn, side="yes", contracts=1, entry=100, fee=None,
                result="yes", ms=START_MS + 5)
        conn.commit()
        conn.close()
        rendered = json.dumps(self._rows(path))
        assert "fee unreadable" in rendered, rendered

    def test_a_combo_is_labelled_as_one(self, tmp_path):
        """A KXMVE combination settling without a result is a different fact
        from a single market doing it -- combos are the majority of the
        record, and this repo has been wrong about them before."""
        path = _build(tmp_path, [])
        conn = db.connect(path)
        conn.execute(
            "INSERT INTO venue_settlements (ticker, event_ticker, "
            "market_result, settled_ms, side, contracts, entry_price_tenths, "
            "fee_cost_tenths) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("KXMVE-ABC", "E", "", START_MS + 9, "yes", 1, 100, 1),
        )
        conn.commit()
        conn.close()
        rendered = json.dumps(self._rows(path))
        assert "KXMVE combo" in rendered, rendered

    def test_an_empty_section_beside_a_refusal_means_the_study_never_opened(
        self, tmp_path
    ):
        """The one reading that would otherwise be ambiguous, so the title
        says it: no offending rows AND a refusal is the never-opened case,
        not a broken query."""
        path = _build(tmp_path, [WIN], open_study=False)
        assert self._rows(path) == []

        from scripts.inspect_live_db import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["study-stop", "--db", str(path)])
        assert "never being opened" in buf.getvalue()
