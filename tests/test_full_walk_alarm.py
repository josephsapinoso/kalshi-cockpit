"""The quote pass says which catalogue walk it took, and warns on the wrong one.

`run_kalshi_pass` branches on a truthy `series_tickers`: a per-series walk when
the list has anything in it, and a walk of the whole open catalogue (~14,010
events, ~28s) when it does not. An **empty** list takes the full branch
deliberately -- ADR 0053's docstring says so in those words, and that policy is
not what these tests are about.

What they are about is that the empty list is reachable while the loop is
running perfectly. `priceable_series` returns `[]` when no row in
`kalshi_events` was seen inside `PRICEABLE_SERIES_WINDOW_MS`, and
`discover_from_events` returning zero priceable events for thirty continuous
minutes produces exactly that with no missed pass, so no `pass_kind` bound
intervenes. Quote passes would switch to the ~10x walk on the ~22s cadence and
stay there. A scope-classification regression produces both halves at once --
an empty desk and a silent full walk -- and nothing else on the screen
separates it from a quiet night.

So the branch is recorded as a fact rather than inferred from `leg_walk_ms`,
and the one anomalous combination warns.

**What these tests do not establish**

- **That the full walk is slower.** That is a network property, measured in
  `docs/measurements/2026-08-19-quote-pass-cost-attribution.md` and not
  derivable from a fake client.
- **That `priceable_series` can actually empty in production.** These tests
  hand `run_kalshi_pass` an empty list directly; whether live discovery ever
  produces one is the open question the instrument exists to answer.
- **That the alarm reaches anyone.** It is a `logger.warning` on the same
  channel as every other runner anomaly. Whether that channel is watched is
  outside this file.
- **Anything about the durable record.** `run_loop.record_pass_walk` writes the
  per-pass line and `inspect_live_db walk-log` reads it; both are tested
  elsewhere.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from backend import runner
from backend.runner import PassCounts, run_kalshi_pass
from backend.store import db
from tests.test_runner import FakeKalshi, _mlb_template

ALARM = "FULL_WALK_ON_QUOTE_PASS"
NOW = 1_787_000_000_000
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def kalshi_events() -> list[dict]:
    """The captured wire payload, per the repo's rule against hand-built ones."""
    return json.loads((FIXTURES / "events_sports_nested.json").read_text("utf-8"))


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "runner.db")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def fresh_walk_state(monkeypatch):
    """The streak counter and the carried discovery count are module state.

    Reset per test, deliberately by `monkeypatch` rather than by assignment, so
    a test that fails part-way cannot leave the next one reading a streak it
    did not create.
    """
    monkeypatch.setattr(runner, "_FULL_WALK_QUOTE_PASSES", 0)
    monkeypatch.setattr(runner, "_LAST_WALK_DISCOVERED", None)


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and ALARM in r.getMessage()
    ]


class TestAQuotePassOnTheFullWalkIsAnAlarm:
    async def test_an_empty_series_list_raises_the_full_walk_alarm(
        self, conn, kalshi_events, caplog
    ):
        """The detector. An empty list means a *narrowed* caller had nothing to
        narrow with, which is the state that must never be silent."""
        client = FakeKalshi([_mlb_template(kalshi_events)])
        counts = PassCounts()
        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            await run_kalshi_pass(
                conn, client, now=NOW, counts=counts, series_tickers=[]
            )

        assert _warnings(caplog), (
            "a quote pass walked the whole catalogue and said nothing; that is "
            "the ~10x walk running on the ~22s cadence with no symptom"
        )
        assert counts.walk_scope == "full", counts.walk_scope
        assert counts.walk_series == 0, counts.walk_series

    async def test_the_alarm_names_what_the_previous_walk_discovered(
        self, conn, kalshi_events, caplog
    ):
        """The half that separates the two causes. A count that fell off a
        cliff is a classification regression; one that decayed is an emptying
        slate, and they need opposite responses."""
        client = FakeKalshi([_mlb_template(kalshi_events)])
        await run_kalshi_pass(
            conn, client, now=NOW, counts=PassCounts(), series_tickers=["KXMLBGAME"]
        )
        discovered = runner._LAST_WALK_DISCOVERED
        assert discovered, "the fixture walk discovered nothing, so the test is blind"

        counts = PassCounts()
        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            await run_kalshi_pass(
                conn, FakeKalshi([]), now=NOW, counts=counts, series_tickers=[]
            )

        assert counts.walk_prev_discovered == discovered, counts.walk_prev_discovered
        assert f"discovered {discovered} priceable events" in _warnings(caplog)[0]

    async def test_a_sustained_run_re_announces_without_flooding(
        self, conn, kalshi_events, caplog
    ):
        """Once per process would be lost -- the log stream retains ~10 minutes
        and the question is asked hours later. Once per pass would put ~160
        identical lines an hour into a 100-line buffer."""
        client = FakeKalshi([_mlb_template(kalshi_events)])
        repeat = runner.FULL_WALK_ALARM_REPEAT_PASSES
        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            for _ in range(repeat):
                await run_kalshi_pass(
                    conn, client, now=NOW, counts=PassCounts(), series_tickers=[]
                )

        fired = _warnings(caplog)
        assert len(fired) == 2, (
            f"{len(fired)} alarms over {repeat} passes; expected the first and "
            "one repeat"
        )


class TestTheNormalBranchesStaySilent:
    """The false-positive guard, and it matters more than the detector.

    A full pass takes the full walk every 900s by design, and a quote pass
    takes the narrowed one every ~22s by design. An alarm that fired on either
    would be ignored inside a day, and then the real one would be too.
    """

    async def test_a_narrowed_quote_pass_is_silent(
        self, conn, kalshi_events, caplog
    ):
        client = FakeKalshi([_mlb_template(kalshi_events)])
        counts = PassCounts()
        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            await run_kalshi_pass(
                conn, client, now=NOW, counts=counts,
                series_tickers=["KXMLBGAME", "KXWNBAGAME"],
            )

        assert _warnings(caplog) == [], _warnings(caplog)
        assert counts.walk_scope == "narrowed", counts.walk_scope
        assert counts.walk_series == 2, counts.walk_series

    async def test_a_full_pass_is_silent(self, conn, kalshi_events, caplog):
        """`None` is the full pass asking for the full walk. It takes the same
        branch as `[]` and means the opposite thing, which is why the caller
        passes the list through instead of normalising it away."""
        client = FakeKalshi([_mlb_template(kalshi_events)])
        counts = PassCounts()
        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            await run_kalshi_pass(conn, client, now=NOW, counts=counts)

        assert _warnings(caplog) == [], _warnings(caplog)
        assert counts.walk_scope == "full", counts.walk_scope
        assert counts.walk_series == 0, counts.walk_series

    async def test_a_narrowed_pass_clears_a_previous_streak(
        self, conn, kalshi_events, caplog
    ):
        """Otherwise the counter drifts and the repeat lands at an arbitrary
        offset into the *next* incident, understating how long it has run."""
        client = FakeKalshi([_mlb_template(kalshi_events)])
        await run_kalshi_pass(
            conn, client, now=NOW, counts=PassCounts(), series_tickers=[]
        )
        assert runner._FULL_WALK_QUOTE_PASSES == 1
        await run_kalshi_pass(
            conn, client, now=NOW, counts=PassCounts(),
            series_tickers=["KXMLBGAME"],
        )
        assert runner._FULL_WALK_QUOTE_PASSES == 0


class TestTheBranchIsAFactAndNotADuration:
    async def test_the_scope_is_recorded_where_the_branch_is(self):
        """`leg_walk_ms` separates the two branches in practice -- ~2,700ms
        against ~28,000ms -- and a duration is evidence about a branch, not the
        branch. A slow narrowed walk and a fast full walk both exist."""
        import inspect

        source = inspect.getsource(run_kalshi_pass)
        assert "counts.walk_scope" in source, (
            "`run_kalshi_pass` no longer records which branch it took, so the "
            "only remaining answer is inferred from `leg_walk_ms`"
        )

    async def test_an_unwalked_pass_is_neither_branch(self):
        """Empty string, not "full". A pass that never walked and a pass that
        walked everything need opposite responses, and a default of "full"
        would report the second for the first."""
        assert PassCounts().walk_scope == ""
        assert PassCounts().walk_prev_discovered is None

    async def test_the_walk_fields_are_reported_at_every_value(self):
        """Including `None` and `0`. A missing key cannot be told from a pass
        that did not walk, and `walk_prev_discovered` is `None` exactly when
        the process has just restarted -- the moment a reader most needs to
        know the number is unknown rather than zero."""
        reported = PassCounts().as_dict()
        for field in (
            "walk_scope", "walk_series", "walk_events_seen", "walk_prev_discovered"
        ):
            assert field in reported, f"`{field}` is dropped from the pass line"
        assert reported["walk_prev_discovered"] is None


class TestTheDurableRecordAndItsReadPath:
    """The pass line is loud and lossy. `flyctl logs` retains ~10 minutes and
    the question -- "when did the quote passes start walking everything?" -- is
    asked hours later, so the branch is also appended to a file on the data
    volume and read back by `inspect_live_db walk-log`.

    Beside the database rather than in it, the same call `loop_rss.jsonl` made:
    one append per pass on the hot path, never joined against anything. A
    column on a table would have meant a schema version, which a lane may not
    allocate alone (`schema.sql`, the v24 note).
    """

    def test_one_line_per_pass_carries_the_kind_and_the_scope(self, tmp_path):
        """Neither field alone is the reading. `quote` + `full` is the anomaly;
        `full` + `full` and `quote` + `narrowed` are both the design."""
        from scripts.run_loop import record_pass_walk

        path = tmp_path / "loop_walk.jsonl"
        record_pass_walk(
            path, now_ms=NOW, kind="quote",
            counts=PassCounts(
                walk_scope="full", walk_series=0, walk_events_seen=14_010,
                walk_prev_discovered=0,
            ),
        )
        record_pass_walk(
            path, now_ms=NOW + 22_000, kind="quote",
            counts=PassCounts(
                walk_scope="narrowed", walk_series=19, walk_events_seen=573,
                walk_prev_discovered=510,
            ),
        )
        lines = [json.loads(x) for x in path.read_text("utf-8").splitlines()]
        assert [x["kind"] for x in lines] == ["quote", "quote"]
        assert [x["scope"] for x in lines] == ["full", "narrowed"]
        assert lines[0]["events_seen"] == 14_010
        assert lines[1]["series"] == 19

    def test_an_unknown_previous_count_is_null_and_not_zero(self, tmp_path):
        """After a restart nothing has been discovered yet. Zero is the alarm
        condition itself, so borrowing it for "not observed" would manufacture
        the very reading the field exists to report."""
        from scripts.run_loop import record_pass_walk

        path = tmp_path / "loop_walk.jsonl"
        record_pass_walk(
            path, now_ms=NOW, kind="full", counts=PassCounts(walk_scope="full")
        )
        assert json.loads(path.read_text("utf-8"))["prev_discovered"] is None

    def test_a_telemetry_failure_never_kills_a_pass(self, tmp_path):
        """Same rule as `record_pass_rss`. A directory is not a file, so the
        open raises; the pass must not notice."""
        from scripts.run_loop import record_pass_walk

        (tmp_path / "loop_walk.jsonl").mkdir()
        record_pass_walk(
            tmp_path / "loop_walk.jsonl", now_ms=NOW, kind="quote",
            counts=PassCounts(walk_scope="full"),
        )

    def test_the_writer_and_the_reader_name_the_same_file(self):
        """`inspect_live_db.py` imports nothing from `backend` on purpose -- it
        is a standalone read-only inspector run over ssh -- so the path is
        spelled twice. A reader pointed at a file nobody writes reports a clean
        instrument, which is the one output this whole file exists to prevent.
        """
        import inspect as inspect_module

        from scripts import run_loop
        from scripts.inspect_live_db import WALK_LOG_NAME

        source = inspect_module.getsource(run_loop.main)
        assert f'"{WALK_LOG_NAME}"' in source, (
            f"`inspect_live_db` reads {WALK_LOG_NAME}; `run_loop.main` no "
            "longer writes a file by that name"
        )

    def test_the_read_path_separates_the_anomaly_from_the_design(self, tmp_path):
        """`walk-log`'s first section is the one combination worth looking at.
        A run that only ever took the designed branches must leave it empty."""
        import contextlib
        import io

        from scripts.inspect_live_db import main
        from scripts.run_loop import record_pass_walk

        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        walk = tmp_path / "loop_walk.jsonl"
        for i, (kind, scope) in enumerate(
            [("full", "full"), ("quote", "narrowed"), ("quote", "full")]
        ):
            record_pass_walk(
                walk, now_ms=NOW + i * 1000, kind=kind,
                counts=PassCounts(walk_scope=scope, walk_prev_discovered=510),
            )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["walk-log", "--db", str(db_path), "--json"])
        assert rc == 0
        report = json.loads(buf.getvalue())
        anomalies = report["sections"][0]
        assert anomalies["row_count"] == 1, anomalies
        assert "quote" in anomalies["rows"][0] and "full" in anomalies["rows"][0]

    def test_a_missing_file_says_so_rather_than_reporting_no_anomalies(
        self, tmp_path
    ):
        """An absent instrument and an instrument reporting nothing are the two
        readings this script exists to keep apart, and an empty section says
        the second in the voice of the first."""
        import contextlib
        import io

        from scripts.inspect_live_db import main

        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["walk-log", "--db", str(db_path), "--json"])
        assert rc == 0
        sections = json.loads(buf.getvalue())["sections"]
        assert len(sections) == 1, sections
        assert sections[0]["row_count"] == 1, (
            "a missing walk log reported zero rows, which reads as 'no quote "
            "pass ever took the full walk'"
        )
        assert "NOT THERE" in sections[0]["title"]
