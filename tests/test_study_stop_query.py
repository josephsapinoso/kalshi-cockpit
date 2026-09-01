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
