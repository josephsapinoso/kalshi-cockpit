"""`lock-attribution` runs a rule that was fixed before the join existed.

`tasks/NEXT.md` open item 2: *"Before crediting ADR 0091, attribute the
holder."* ADR 0091's own argument is a rate -- the fast poller branch runs 288
times a day and the mirror twice, and *"four to five failures a day fits 288
windows and does not fit two"* -- and a rate is not an attribution. Nothing had
placed one observed `database is locked` failure inside one poller window.

The registration is
`docs/measurements/2026-09-01-lock-holder-attribution-registration.md`, written
before the query existed. These tests pin the parts of it that a later edit
could quietly move: the window, the threshold, the unit, the refusal
conditions, and above all **that no exonerating verdict is available**.

What this file establishes
--------------------------
That the query scores a burst against the newest poller cycle start at or
before it, that it convicts when the bursts really do cluster there, that it
says NOT ESTABLISHED rather than "cleared" when they do not, and that it
refuses outright when `poll_log` does not span the journal.

What it does not establish
--------------------------
- **Anything about the live population.** Every fixture here is a `tmp_path`
  database written by the real writers. A green suite is not a verdict.
- **That 14 s is the right window.** It is the registration's bound on three
  Kalshi round trips plus `BUSY_TIMEOUT_MS`, fixed before looking; these tests
  pin that it has not moved, not that it is correct.
- **That the poller is the only candidate holder.** `maybe_checkpoint`, the
  API's per-request connections and `store_closing_line` raise the same error
  and this query cannot see them at all.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from backend.portfolio_poll import log_poll_attempt
from backend.store import db

#: 2026-08-31T00:00:00Z, a round number so the fixtures' offsets are readable.
BASE = 1_788_134_400_000
CYCLE_MS = 300_000


def _read(db_path: Path, *args: str) -> list[dict]:
    from scripts.inspect_live_db import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["lock-attribution", "--db", str(db_path), "--json", *args])
    assert rc == 0, buf.getvalue()
    return json.loads(buf.getvalue())["sections"]


def _section(sections: list[dict], needle: str) -> dict:
    """By NAME, never by index -- the lesson of 2026-09-01."""
    matches = [s for s in sections if needle in s["title"]]
    assert len(matches) == 1, (
        f"{needle!r} matched {len(matches)}: "
        f"{[s['title'][:60] for s in sections]}"
    )
    return matches[0]


PRECONDITIONS = "PRECONDITIONS"
DETAIL = "every locked failure, oldest first"
TEST = "THE REGISTERED TEST"
REFUSED = "REFUSED"


def _build(
    tmp_path: Path,
    *,
    offsets_s: list[float],
    cycles: int = 200,
    repeats_per_burst: int = 0,
    cycle_ms: int = CYCLE_MS,
    error: str = "OperationalError: database is locked",
) -> Path:
    """A database with `cycles` poller cycles and one burst per offset.

    Both halves are written by the REAL writers -- `log_poll_attempt` for
    `poll_log` and `record_loop_failure_durably` for the journal -- so a change
    to either shape breaks this file rather than being papered over.
    """
    db_path = tmp_path / "cockpit.db"
    conn = db.init_db(db_path)
    for i in range(cycles):
        stamp = BASE + i * cycle_ms
        for endpoint in ("balance", "fills", "settlements", "positions"):
            log_poll_attempt(
                conn, now_ms=stamp, endpoint=endpoint, ok=True, row_count=1
            )
    conn.commit()

    journal = tmp_path / "loop_failures.jsonl"
    pass_number = 0
    for i, offset in enumerate(offsets_s):
        # Spread the bursts across cycles so no two share one.
        stamp = BASE + (i + 1) * cycle_ms + int(offset * 1000)
        pass_number += 1
        db.record_loop_failure_durably(
            conn, db_path=db_path, journal_path=journal, failed_ms=stamp,
            pass_number=pass_number, consecutive_failures=1, error=error,
            pass_kind="full", exc=RuntimeError("x"),
        )
        for r in range(repeats_per_burst):
            pass_number += 1
            db.record_loop_failure_durably(
                conn, db_path=db_path, journal_path=journal,
                failed_ms=stamp + (r + 1) * 1000, pass_number=pass_number,
                consecutive_failures=r + 2, error=error, pass_kind="full",
                exc=RuntimeError("x"),
            )
    conn.close()
    return db_path


class TestTheQueryExistsAndIsReachable:
    def test_it_is_registered(self):
        from scripts.inspect_live_db import QUERIES

        assert "lock-attribution" in QUERIES

    def test_it_reads_the_same_journal_the_loop_writes(self):
        """Spelled twice -- `inspect_live_db` imports nothing from `backend` --
        so a reader pointed at a file nobody writes reports a clean
        instrument."""
        import inspect as inspect_module

        from scripts import run_loop
        from scripts.inspect_live_db import FAILURE_LOG_NAME

        assert f'"{FAILURE_LOG_NAME}"' in inspect_module.getsource(run_loop.main)


class TestTheRegisteredConstantsHaveNotMoved:
    """Widening the window or loosening the threshold after seeing the offsets
    is the defect the registration exists to prevent. It cannot be prevented,
    only made visible -- so it is pinned here, where a diff shows it."""

    def test_the_window_is_the_registered_fourteen_seconds(self):
        from scripts.inspect_live_db import LOCK_WINDOW_S

        assert LOCK_WINDOW_S == 14.0, (
            "three Kalshi round trips bounded at 3 s each, plus "
            "BUSY_TIMEOUT_MS of 5 s; fixed before the join was computed"
        )

    def test_the_threshold_is_one_percent_and_not_five(self):
        from scripts.inspect_live_db import LOCK_ALPHA

        assert LOCK_ALPHA == 0.01, (
            "0.05 on the n-th test of a corpus is not a 5% error rate"
        )


class TestTheOffsetIsMeasuredFromTheCycleStart:
    def test_a_burst_inside_the_window_is_scored_inside_it(self, tmp_path):
        detail = _section(_read(_build(tmp_path, offsets_s=[2.0])), DETAIL)
        row = detail["rows"][0]
        assert 2.0 in row, row
        assert True in row, row

    def test_a_burst_outside_the_window_is_scored_outside_it(self, tmp_path):
        detail = _section(_read(_build(tmp_path, offsets_s=[150.0])), DETAIL)
        row = detail["rows"][0]
        assert 150.0 in row, row
        assert False in row, row

    def test_the_null_probability_uses_the_OBSERVED_gap(self, tmp_path):
        """`C` is read from `poll_log`, never assumed to be 300 s. A poller
        whose cadence changed would otherwise be tested against a null that
        does not describe it."""
        rows = _section(_read(_build(tmp_path, offsets_s=[2.0] * 6)), TEST)["rows"]
        p0 = next(r for r in rows if r[0] == "p0 = W / C")
        # 1e-5 rather than 1e-6: the screen rounds p0 to five decimals, and
        # asserting past the displayed precision tests the formatter.
        assert abs(p0[1] - 14.0 / 300.0) < 1e-5, p0
        assert "300" in str(p0[2]), p0

    def test_a_DIFFERENT_cadence_moves_the_null(self, tmp_path):
        """The guard above passes against a hardcoded 300, so it is not a
        guard on its own -- found by asking what mutation it would survive.
        At a 60 s cadence the same window is five times as likely under the
        null, and a hardcoded p0 would convict where it must not."""
        db_path = _build(tmp_path, offsets_s=[1.5] * 6, cycle_ms=60_000)
        rows = _section(_read(db_path), TEST)["rows"]
        p0 = next(r for r in rows if r[0] == "p0 = W / C")
        assert abs(p0[1] - 14.0 / 60.0) < 1e-5, p0
        assert "60" in str(p0[2]), p0


class TestOnlyBurstsEnterTheTest:
    """`Tempo.pass_kind` re-arms a full pass the moment one fails, so the
    failures inside a burst are one draw. Counting them as four inflates
    significance by about an order of magnitude -- the exact defect the
    2026-08-25 audit found in the CLV look."""

    def test_repeats_are_shown_but_not_counted(self, tmp_path):
        db_path = _build(tmp_path, offsets_s=[2.0, 2.0], repeats_per_burst=3)
        sections = _read(db_path, "-n", "50")

        detail = _section(sections, DETAIL)
        assert detail["row_count"] == 8, detail["row_count"]

        rows = _section(sections, TEST)["rows"]
        n = next(r for r in rows if r[0] == "n (bursts scored)")
        assert n[1] == 2, f"repeats entered the test: {n}"

    def test_the_precondition_block_reports_both_counts(self, tmp_path):
        db_path = _build(tmp_path, offsets_s=[2.0, 2.0], repeats_per_burst=3)
        rows = _section(_read(db_path, "-n", "50"), PRECONDITIONS)["rows"]
        assert next(r for r in rows if "journal failures" in r[0])[1] == 8
        assert next(r for r in rows if "bursts" in r[0])[1] == 2


class TestTheVerdicts:
    def test_bursts_clustered_at_the_cycle_start_CONVICT(self, tmp_path):
        """Six of six inside a 4.7% window. If this does not convict, the
        query cannot detect the thing it was built for."""
        rows = _section(_read(_build(tmp_path, offsets_s=[1.5] * 6)), TEST)["rows"]
        verdict = next(r for r in rows if r[0] == "VERDICT")
        assert verdict[1] == "POLLER IMPLICATED", rows
        p = next(r for r in rows if "binomial" in r[0])
        assert float(p[1]) < 0.01, p

    def test_bursts_spread_across_the_cycle_do_NOT_convict(self, tmp_path):
        rows = _section(
            _read(_build(tmp_path, offsets_s=[40.0, 90.0, 140.0, 190.0, 240.0, 280.0])),
            TEST,
        )["rows"]
        assert next(r for r in rows if r[0] == "VERDICT")[1] == "NOT ESTABLISHED"

    def test_a_null_result_is_never_reported_as_the_poller_being_cleared(
        self, tmp_path
    ):
        """The clause most likely to be violated later, so it is on the screen
        rather than only in the registration. At n = 6 and p0 = 0.047 the null
        expects 0.28; a k of 0 is what the null PREDICTS, and reporting it as
        an acquittal is reading a foregone conclusion as a finding."""
        title = _section(
            _read(_build(tmp_path, offsets_s=[40.0, 90.0, 140.0, 190.0, 240.0, 280.0])),
            TEST,
        )["title"]
        assert "NO EXONERATING VERDICT EXISTS IN THIS DESIGN" in title, title
        assert "may NOT be reported" in title, title
        assert "cleared" in title, title

    def test_the_screen_separates_attribution_from_efficacy(self, tmp_path):
        """Convicting the poller says nothing about whether ADR 0091 fixed it.
        Two claims, and the entry that conflates them is the one that gets
        written."""
        title = _section(_read(_build(tmp_path, offsets_s=[1.5] * 6)), TEST)["title"]
        assert "Attribution is not efficacy" in title, title

    def test_a_high_k_below_the_threshold_still_does_not_convict(self, tmp_path):
        """Two of two inside the window is suggestive and p = 0.0043... is not
        the whole rule: the count must also exceed expectation AND clear 0.01.
        A test that convicted here would convict on almost any small sample."""
        rows = _section(_read(_build(tmp_path, offsets_s=[1.0])), TEST)["rows"]
        assert next(r for r in rows if r[0] == "VERDICT")[1] == "NOT ESTABLISHED"


class TestItRefusesRatherThanReportingAnUnmeasurableOffset:
    def test_poll_log_not_spanning_the_journal_is_a_REFUSAL(self, tmp_path):
        """A burst scored against a cycle stamp hours away measures the hole in
        `poll_log`, not the poller's lock -- and it would land in the 'outside
        the window' bucket, biasing the test AGAINST H1 while looking like
        evidence."""
        db_path = _build(tmp_path, offsets_s=[2.0], cycles=1)
        sections = _read(db_path)
        assert _section(sections, REFUSED)["row_count"] == 1
        assert not [s for s in sections if TEST in s["title"]], (
            "a verdict was computed on preconditions that were not met"
        )

    def test_the_precondition_block_names_the_span_check(self, tmp_path):
        rows = _section(_read(_build(tmp_path, offsets_s=[2.0], cycles=1)),
                        PRECONDITIONS)["rows"]
        spans = next(r for r in rows if "spans the journal" in r[0])
        assert spans[1] is False, spans

    def test_a_missing_journal_says_so_rather_than_reporting_no_failures(
        self, tmp_path
    ):
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        sections = _read(db_path)
        assert len(sections) == 1, sections
        assert "NOT THERE" in sections[0]["title"]
        assert "not 'no failures'" in sections[0]["title"]

    def test_an_empty_journal_is_not_a_verdict_about_the_poller(self, tmp_path):
        """`walk-log`'s rule. Zero failures means nothing to attribute, which
        is not the same as having attributed nothing to the poller."""
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        (tmp_path / "loop_failures.jsonl").write_text("", encoding="utf-8")

        title = _read(db_path)[0]["title"]
        assert "nothing to attribute" in title, title
        assert "not a verdict about the poller" in title, title


class TestThePopulationIsTheLockedFailuresOnly:
    def test_a_non_lock_failure_is_excluded(self, tmp_path):
        """`PassDeadlineExceeded` inserts fine and has no lock holder to
        attribute. Including it would dilute k with rows the hypothesis says
        nothing about."""
        db_path = _build(tmp_path, offsets_s=[1.5] * 6)
        conn = db.init_db(db_path)
        db.record_loop_failure_durably(
            conn, db_path=db_path,
            journal_path=tmp_path / "loop_failures.jsonl",
            failed_ms=BASE + 50 * CYCLE_MS + 1500, pass_number=900,
            consecutive_failures=1, error="PassDeadlineExceeded: 75s",
            pass_kind="full", exc=RuntimeError("x"),
        )
        conn.close()

        rows = _section(_read(db_path, "-n", "50"), TEST)["rows"]
        assert next(r for r in rows if r[0] == "n (bursts scored)")[1] == 6

    def test_the_rollback_and_diagnosis_lines_are_not_failures(self, tmp_path):
        """They share the file and carry no `pass_number`. Counting either
        would double every burst that got one."""
        db_path = _build(tmp_path, offsets_s=[1.5] * 6)
        raw = (tmp_path / "loop_failures.jsonl").read_text(encoding="utf-8")
        kinds = [json.loads(x)["kind"] for x in raw.splitlines() if x.strip()]
        assert kinds.count("rollback") == 6, kinds

        rows = _section(_read(db_path, "-n", "50"), TEST)["rows"]
        assert next(r for r in rows if r[0] == "n (bursts scored)")[1] == 6


class TestTwoGuardsThatWereMissingUntilTheMutationRunFoundThem:
    """Both of these passed every mutation I wrote until I disabled the code
    they were supposed to guard and the suite stayed green. Neither fixture
    above could reach them: every burst sat a few seconds AFTER a cycle start,
    which is exactly the shape that makes 'nearest' and 'preceding' agree, and
    no fixture had enough bursts for a significant DEFICIT.
    """

    def test_a_burst_just_BEFORE_a_cycle_start_is_scored_against_the_earlier_one(
        self, tmp_path
    ):
        """A failure 5 s before a poller cycle STARTS cannot have been caused
        by that cycle -- the lock it would take does not exist yet. Scoring
        against the nearest stamp in either direction manufactures a
        conviction out of a failure that preceded its own cause, which is the
        2026-09-01 lesson one file over.
        """
        db_path = _build(tmp_path, offsets_s=[295.0])
        row = _section(_read(db_path), DETAIL)["rows"][0]
        assert 295.0 in row, row
        assert False in row, (
            "scored against the FOLLOWING cycle: a 5 s 'offset' to a lock "
            "that had not been taken yet"
        )

    def test_a_significant_DEFICIT_does_not_convict_the_poller(self, tmp_path):
        """140 bursts, none in the window. The lower tail alone is
        0.9533**140, and the two-sided test also sums the upper outcomes at
        least as improbable -- which is why 100 bursts was not enough and the
        first draft of this test failed at p = 0.0155. The result is under the
        0.01 threshold and is evidence AGAINST H1, not for it. Without the
        `k > expected` clause the verdict reads POLLER IMPLICATED off a number
        that says the opposite.
        """
        offsets = [40.0 + (i % 25) * 10.0 for i in range(140)]
        rows = _section(_read(db_path := _build(tmp_path, offsets_s=offsets),
                              "-n", "200"), TEST)["rows"]
        assert db_path.exists()
        k = next(r for r in rows if r[0] == "k (offset <= W)")[1]
        expected = next(r for r in rows if r[0] == "expected under H0")[1]
        p = float(next(r for r in rows if "binomial" in r[0])[1])
        assert k == 0 and k < expected, (k, expected)
        assert p < 0.01, f"the fixture no longer reaches the deficit case: p={p}"
        assert next(r for r in rows if r[0] == "VERDICT")[1] == "NOT ESTABLISHED"


class TestTheGuardsAnAuditFoundMissing:
    """`measurement-skeptic`, 2026-09-01, running its own mutations against
    this file: deleting `not covered` from the precondition branch left all 23
    tests green. The only fixture reaching the refusal used `cycles=1`, which
    refuses through the `median_gap_s is None` clause instead -- so the span
    check never fired, and this file's own docstring claimed it did.

    A guard no fixture reaches is decoration, and a docstring asserting it is
    worse than silence.
    """

    def test_a_journal_running_PAST_the_last_cycle_stamp_is_refused(
        self, tmp_path
    ):
        """The discriminating case: `poll_log` is healthy and has a usable
        median gap, so the `median_gap_s` clause does NOT fire -- only the span
        check can refuse this. A burst after the last stamp would otherwise be
        scored against a cycle that is hours old, land in the
        outside-the-window bucket, and bias the test while looking like
        evidence."""
        db_path = _build(tmp_path, offsets_s=[2.0], cycles=200)
        conn = db.init_db(db_path)
        db.record_loop_failure_durably(
            conn, db_path=db_path,
            journal_path=tmp_path / "loop_failures.jsonl",
            failed_ms=BASE + 400 * CYCLE_MS,        # far past the last stamp
            pass_number=999, consecutive_failures=1,
            error="OperationalError: database is locked", pass_kind="full",
            exc=RuntimeError("x"),
        )
        conn.close()

        sections = _read(db_path, "-n", "20")
        pre = _section(sections, PRECONDITIONS)["rows"]
        gap = next(r for r in pre if "median cycle gap" in r[0])
        spans = next(r for r in pre if "spans the journal" in r[0])
        assert gap[1] is not None, (
            "the fixture no longer reaches the span check: it is refusing "
            "through the median-gap clause instead"
        )
        assert spans[1] is False, spans
        assert _section(sections, REFUSED)["row_count"] == 1
        assert not [s for s in sections if TEST in s["title"]], (
            "a verdict was computed on a journal poll_log does not span"
        )

    def test_the_matched_cycle_SPAN_is_reported_beside_the_offset(
        self, tmp_path
    ):
        """The registration said the poller's cycle END was recorded nowhere
        and used that to rule out any exonerating verdict. It was wrong: the
        poller sleeps AFTER its cycle, so the gap to the next stamp bounds the
        cycle above, from the same table.

        This is the falsifying half of the measurement. Without it, a burst on
        a cycle that finished normally -- meaning something OTHER than the
        poller held the lock -- is indistinguishable from one on a cycle that
        hung."""
        db_path = _build(tmp_path, offsets_s=[2.0], cycles=200)
        cure = _section(_read(db_path), DETAIL)
        assert "cycle_span_s" in cure["columns"], cure["columns"]
        assert 300.0 in cure["rows"][0], cure["rows"][0]

        rows = _section(_read(db_path), TEST)["rows"]
        labels = [r[0] for r in rows]
        assert any("matched-cycle span, min" in x for x in labels), labels
        assert any("matched-cycle span, median" in x for x in labels), labels

    def test_the_p_value_is_not_formatted_to_a_literal_zero(self, tmp_path):
        """It printed `0.000000` for a quantity around 5e-18 -- so the screen
        said the p-value was zero, and every write-up quoting it had to compute
        it somewhere else. That is how the first draft of the result document
        got a number 22% off the instrument's own."""
        rows = _section(_read(_build(tmp_path, offsets_s=[1.5] * 13)), TEST)["rows"]
        p = next(r for r in rows if "binomial" in r[0])[1]
        assert float(p) > 0.0, f"the p-value formatted to a literal zero: {p}"
        assert "e-" in str(p), f"not in scientific notation: {p}"
