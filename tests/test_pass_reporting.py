"""One pass, one log line.

A pass used to report itself twice. `run_pricing_pass` logged its counts from
`backend/runner.py`, and about four milliseconds later the scheduler logged
`pass N ok` carrying the same dict plus the scoring, settlement and alert
counts. Two lines, one a strict subset of the other.

That was tolerable at 900s and a flood at ~22s, which is the cadence the quote
pass runs at while the odds window is open -- the exact minutes when something
interesting is happening and `flyctl logs` has 100 lines to spend. The line was
not the problem; the caller was. **A logging rate is a property of the caller,
not of the code.**

So the inline line is gone, and the three claims that make removing it safe are
asserted here rather than argued in a commit message:

1. `run_pricing_pass` says nothing about its counts.
2. The loop's line carries every field the deleted one did -- a *superset*, so
   nothing is lost.
3. The one thing the inline line did that the loop's cannot: report counts for
   a pass that recorded successfully and then died before `pass N ok`.

What this does not establish
----------------------------
That the deployed instance emits one line per pass. These are claims about the
code; the observation belongs in the live log, where the previous version of
this fix was verified. `flyctl logs` drops lines under a burst, so absence
there is not evidence either way -- read timestamps, not counts.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
from pathlib import Path

import pytest

from backend.runner import PassCounts, run_pricing_pass

ROOT = Path(__file__).resolve().parents[1]


def _load_run_loop():
    """Import `scripts/run_loop.py`, which is not a package."""
    spec = importlib.util.spec_from_file_location(
        "run_loop_under_test", ROOT / "scripts" / "run_loop.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


run_loop = _load_run_loop()


def _populated_counts() -> PassCounts:
    """Every field non-default, so a dropped one is visible rather than falsy.

    `as_dict` filters on truthiness outside `ALWAYS_REPORT`, so counts built
    from defaults would omit most keys and a test asserting "every key survives"
    would be asserting almost nothing.
    """
    counts = PassCounts()
    for index, name in enumerate(vars(counts), start=1):
        value = getattr(counts, name)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            setattr(counts, name, index)
        elif isinstance(value, str):
            setattr(counts, name, f"{name}-said-something")
        elif isinstance(value, list):
            setattr(counts, name, [f"{name}-entry"])
    return counts


class FakeLog:
    def __init__(self):
        self.errors: list[tuple] = []

    def error(self, message, *args):
        self.errors.append((message, args))


class TestThePricingPassDoesNotReportItself:
    def test_it_logs_nothing_about_its_counts(self, tmp_path, caplog):
        """The disable-check: restore the `logger.info` and this goes red."""
        from backend.store import db

        conn = db.init_db(tmp_path / "quiet.db")
        try:
            with caplog.at_level(logging.DEBUG, logger="backend.runner"):
                counts = run_pricing_pass(conn, [], now=1_786_110_562_317)
        finally:
            conn.close()

        # The counts still exist -- the pass reports by returning, which is
        # what every caller already reads.
        assert counts.as_dict()["recommendations"] == 0

        offenders = [
            r.getMessage()
            for r in caplog.records
            if r.name == "backend.runner" and "pass" in r.getMessage()
        ]
        assert not offenders, (
            "run_pricing_pass logged its own counts. Two callers already report "
            f"them and both report a superset: {offenders}"
        )


class TestTheLoopsLineIsASuperset:
    """The reason the inline line is removable, stated as an assertion.

    Prose in a handoff file said `pricing pass:` was "a strict subset of
    `pass N ok`". True when written, and nothing held it true. If `CombinedPass`
    ever prefixes or drops a recording field, this fails instead of the log
    quietly losing a column nobody notices is missing.
    """

    def test_every_recording_field_survives_into_the_loops_line(self):
        counts = _populated_counts()
        merged = run_loop.CombinedPass(counts, kind="full", seconds=1.0).as_dict()

        for key, value in counts.as_dict().items():
            assert key in merged, f"`{key}` is reported by nothing at all"
            assert merged[key] == value, f"`{key}` arrives changed"

    def test_it_says_which_cadence_produced_it(self):
        """A quote pass carries no `clv_` counts, so it must be labelled.

        Without the label, "scoring did not run" reads as "scoring found
        nothing" -- the confusion `sweep_decision` exists to prevent one column
        over.
        """
        merged = run_loop.CombinedPass(
            PassCounts(), kind="quote", seconds=0.4
        ).as_dict()

        assert merged["pass"] == "quote"
        assert not any(k.startswith("clv_") for k in merged)


class TestCountsSurviveALateFailure:
    """The one job the deleted line did that the loop's line cannot.

    A pass records, then scores, settles and alerts. Dying in the second half
    leaves rows on disk and, without this, a traceback that says where it broke
    and nothing about what had already been written.
    """

    def test_a_late_failure_reports_what_the_pass_recorded(self):
        log = FakeLog()
        counts = PassCounts(recommendations=24, odds_sweeps=1, surfaced=0)

        with pytest.raises(RuntimeError, match="candlesticks"):
            with run_loop.counts_survive_a_late_failure(log, "full", counts):
                raise RuntimeError("candlesticks 502")

        assert len(log.errors) == 1
        _, args = log.errors[0]
        assert args[0] == "full"
        assert args[1]["recommendations"] == 24
        assert args[1]["odds_sweeps"] == 1

    def test_it_re_raises_rather_than_swallowing(self):
        """Reporting is not handling.

        The loop counts consecutive failures and takes the process with it at
        five. A pass that reports its counts and then returns normally would
        reset that counter, so a permanently broken scoring leg would look like
        a healthy loop forever -- which is exactly the shape
        `docker/entrypoint.sh` exists to prevent for the two server processes.
        """
        original = ValueError("the original")

        with pytest.raises(ValueError) as raised:
            with run_loop.counts_survive_a_late_failure(
                FakeLog(), "quote", PassCounts()
            ):
                raise original

        assert raised.value is original

    def test_a_pass_that_succeeds_says_nothing_extra(self):
        """Otherwise this reintroduces the per-pass line it replaced."""
        log = FakeLog()

        with run_loop.counts_survive_a_late_failure(log, "quote", PassCounts()):
            pass

        assert log.errors == []

    def test_the_loop_actually_wraps_its_second_half_in_it(self):
        """Structural, because the runtime path costs odds credits to exercise.

        `one_pass` lives inside `main`, behind a live Kalshi client and an odds
        client that spends from a budget shared with the deployed instance --
        so no test drives it, and a correct helper called by nothing is this
        repo's most-repeated defect. Reading the tree is the cheap floor.
        """
        tree = ast.parse(
            (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        )
        one_pass = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.AsyncFunctionDef)
                and node.name == "one_pass"
            ),
            None,
        )
        assert one_pass is not None, "`one_pass` is gone; this test is vacuous"

        guarded = {
            call.func.attr if isinstance(call.func, ast.Attribute)
            else getattr(call.func, "id", None)
            for block in ast.walk(one_pass)
            if isinstance(block, ast.With)
            and any(
                getattr(item.context_expr.func, "id", None)
                == "counts_survive_a_late_failure"
                for item in block.items
                if isinstance(item.context_expr, ast.Call)
            )
            for call in ast.walk(block)
            if isinstance(call, ast.Call)
        }
        assert "score_settle_and_alert" in guarded, (
            "the scoring/settling/alerting half of a pass runs outside "
            "`counts_survive_a_late_failure`, so a pass that records and then "
            "dies reports a traceback and no counts"
        )


class TestTheLadderReportsWhyItRefusedLegs:
    """The measurement that says whether the 2026-08-28 guard ever fired.

    A leg whose `p_conservative` is not positive zeroes a card's joint and,
    on 2026-08-28, raised `ZeroDivisionError` inside `score_settle_and_alert`
    on live -- killing the tail of every pass. The fix refuses such a leg and
    counts it as `fair_probability_not_positive`.

    That count existed only in `/api/parlays`' response, which needs auth, so
    the question the fix raises -- *did the guard fire, or did the bad leg
    simply age out?* -- was unanswerable from outside the container. These
    guards put the tally on `pass N ok`, where `flyctl logs` can read it.

    What this does not establish
    ----------------------------
    That the deployed loop emits these keys. It asserts what `CombinedPass`
    reports and that `score_settle_and_alert` hands it the payload's tally;
    the observation belongs in the live log.
    """

    def test_each_refusal_reason_reaches_the_pass_line(self):
        """Disable-check: drop the `ladder_excluded` block and this goes red."""
        merged = run_loop.CombinedPass(
            PassCounts(),
            kind="full",
            seconds=1.0,
            ladder_excluded={
                "fair_probability_not_positive": 2,
                "stale_consensus": 7,
            },
        ).as_dict()

        assert merged["ladder_fair_probability_not_positive"] == 2
        assert merged["ladder_stale_consensus"] == 7
        assert merged["ladder_excluded"] == 9

    def test_a_ladder_that_refused_nothing_still_says_so(self):
        """Zero is a reading. Absence is not, and they must not look alike.

        The ladder is built only on a pass that swept or a full pass, so a
        quote pass carrying no `ladder_` keys is the common case. Without an
        always-emitted total, "built and refused nothing" and "never ran" are
        the same line -- the repo's "unreadable resolves to None, never 0"
        convention, pointed at a log.
        """
        merged = run_loop.CombinedPass(
            PassCounts(), kind="full", seconds=1.0, ladder_excluded={}
        ).as_dict()

        assert merged["ladder_excluded"] == 0

    def test_a_pass_that_built_no_ladder_reports_no_tally(self):
        merged = run_loop.CombinedPass(
            PassCounts(), kind="quote", seconds=0.4
        ).as_dict()

        assert not any(k.startswith("ladder_") for k in merged), merged

    def test_the_loop_actually_reads_the_payloads_excluded_tally(self):
        """Structural, for the reason the sibling AST guard gives.

        `score_settle_and_alert` lives inside `main` behind a live Kalshi
        client and a shared odds budget, so no test drives it. The defect this
        catches is the one that shipped: `build_ladder_payload` was called
        inline as an argument and its `excluded` dict discarded, so a correct
        count reached nothing.
        """
        tree = ast.parse(
            (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        )
        func = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.AsyncFunctionDef)
                and node.name == "score_settle_and_alert"
            ),
            None,
        )
        assert func is not None, (
            "`score_settle_and_alert` is gone; this test is vacuous"
        )
        source = ast.unparse(func)

        # `.get('excluded')` and not the bare word: `ladder_excluded=` below
        # contains "excluded" as a substring, so the loose spelling would pass
        # vacuously the moment the second assertion did.
        assert "get('excluded')" in source, (
            "`score_settle_and_alert` never reads the ladder payload's "
            "`excluded` tally, so the refusal counts reach no log line"
        )
        assert "ladder_excluded=" in source, (
            "the tally is read but never handed to `CombinedPass`, so it is "
            "computed and thrown away -- the exact defect this guards"
        )
