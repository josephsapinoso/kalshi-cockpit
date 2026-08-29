"""The per-pass line carries the WAL, the database and the candidate scan.

**Why this exists.** On 2026-08-29 `/data/cockpit.db` was 1,910,190,080 bytes
and `/data/cockpit.db-wal` was 230,765,352 -- 220 MiB of write-ahead log that
had never been reset. `journal_mode = WAL`, `synchronous = NORMAL`, nothing in
the repo calls `wal_checkpoint`, and a passive autocheckpoint cannot RESET the
log while any reader holds an older snapshot: the API opens a connection per
request and a Fly health check hits `/api/health` every 15 seconds.

The storage legs blew out together -- `leg_price_link_ms` 18.7-32.2s,
`leg_store_quotes_ms` 13-17s -- while the HTTP walk stayed at ~2.7s, and two
mechanisms fit that equally: the WAL making every write slow, or
`_match_candidates` (`SELECT DISTINCT ... WHERE sport_key = ? AND commence_ms
>= ?`, `sport_key` in no index) scanning a growing `odds_snapshots`. Four
fields on one line per pass turn that into a correlation rather than a repro.

**What this establishes.** That an absent or unreadable WAL resolves to `None`
and never to `0`; that a row written before these fields existed still parses
in the reader; that `candidate_rows` is the count `_match_candidates` actually
returned rather than a constant, a call count, or a cached figure; and that
`one_pass` supplies the database path and the previous pass's counts, so the
fields are not four columns of null forever.

**What it does not establish.**

- **That either mechanism is the cause.** These are instruments. Two
  quantities that both grow with the age of a process correlate whatever is
  driving the legs; the informative case is a flat `candidate_rows` under a
  swinging leg, and that is a reading of live data, not of this file.
- **What the live figures are.** Every number here is synthetic. Nothing in
  this suite touches `/data/cockpit.db`.
- **That the cost is negligible on the live box.** Two `os.stat` calls and a
  `len()` are cheap by construction, not by measurement here.
- **Anything about the `kind` field's semantics.** `kind` stamps the pass
  about to run while the RSS describes the pass before it; that mismatch is
  known, is being corrected elsewhere, and is untouched by this file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import runner  # noqa: E402
from backend.kalshi.discovery import DiscoveredEvent  # noqa: E402
from backend.runner import PassCounts, link_discovered_events  # noqa: E402
from backend.store import db  # noqa: E402
from scripts.inspect_live_db import (  # noqa: E402
    DEFAULT_ROW_CAP,
    QUERIES,
    loop_rss_path,
    main as inspect_main,
)
from scripts.run_loop import file_kb, record_pass_rss  # noqa: E402

NOW = 1_787_000_000_000


def _fake_proc(tmp_path: Path, rss_kb: int = 714000, avail_kb: int = 666000):
    """The `/proc` the sampler reads. Windows has none, so every test needs it."""
    proc = tmp_path / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self" / "status").write_text(
        f"Name:\tpython\nVmSize:\t900000 kB\nVmRSS:\t{rss_kb} kB\n"
    )
    (proc / "meminfo").write_text(
        "MemTotal:        2015232 kB\n"
        f"MemAvailable:     {avail_kb} kB\n"
        "MemFree:          111616 kB\n"
    )
    return proc


def _one_row(tmp_path: Path, **kwargs) -> dict:
    log = tmp_path / "loop_rss.jsonl"
    # `produced_by` is required at the call, not defaulted in the writer:
    # None there already means "first pass of this process, nothing produced
    # this reading", so a default would make a caller that forgot look
    # identical to a genuine first pass on every row.
    kwargs.setdefault("produced_by", None)
    record_pass_rss(
        log,
        now_ms=NOW,
        kind="quote",
        proc=_fake_proc(tmp_path),
        **kwargs,
    )
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, f"expected one line, got {len(lines)}"
    return json.loads(lines[0])


# ---------------------------------------------------------------------------
# 1. The WAL resolves to None, never 0
# ---------------------------------------------------------------------------


class TestAnUnreadableWalIsNoneAndNeverZero:
    """`0` would read as "the WAL is empty", which is the opposite of the
    finding. This repo's standing rule -- unreadable resolves to `None`, never
    `0` -- is load-bearing here rather than stylistic.

    Mutation: `except OSError: return None` -> `return 0` in
    `scripts/run_loop.file_kb`. Every test in this class goes red.
    """

    def test_a_missing_wal_file_is_none(self, tmp_path):
        database = tmp_path / "cockpit.db"
        database.write_bytes(b"x" * 4096)
        row = _one_row(tmp_path, db_path=database)
        assert row["wal_kb"] is None
        assert row["wal_kb"] != 0
        # Present, not omitted: a reader must be able to tell "not measured"
        # from "this row predates the column", and only the key does that.
        assert "wal_kb" in row

    def test_an_unreadable_wal_file_is_none(self, tmp_path, monkeypatch):
        """A WAL that exists and cannot be stat'd -- a permission error on a
        volume, which is exactly the state a diagnosis runs in."""
        database = tmp_path / "cockpit.db"
        database.write_bytes(b"x" * 4096)
        (tmp_path / "cockpit.db-wal").write_bytes(b"y" * 8192)

        import os as real_os

        real_stat = real_os.stat

        def refusing(path, *a, **kw):
            if str(path).endswith("-wal"):
                raise PermissionError(13, "denied")
            return real_stat(path, *a, **kw)

        monkeypatch.setattr("scripts.run_loop.os.stat", refusing)
        row = _one_row(tmp_path, db_path=database)
        assert row["wal_kb"] is None
        assert row["db_kb"] == 4

    def test_no_database_path_leaves_both_none(self, tmp_path):
        row = _one_row(tmp_path)
        assert row["wal_kb"] is None and row["db_kb"] is None

    def test_a_wal_that_exists_reports_its_size(self, tmp_path):
        """The other half of the same guard: `None` must not be what the field
        always says. A guard that can only report absence is decoration."""
        database = tmp_path / "cockpit.db"
        database.write_bytes(b"x" * (3 * 1024))
        (tmp_path / "cockpit.db-wal").write_bytes(b"y" * (220 * 1024))
        row = _one_row(tmp_path, db_path=database)
        assert row["wal_kb"] == 220
        assert row["db_kb"] == 3

    def test_a_genuinely_empty_wal_reports_zero(self, tmp_path):
        """`0` is a legitimate MEASUREMENT when the file is there and empty.
        Resolving that to `None` would be the same error pointed the other
        way -- an absence borrowing a present value's representation."""
        database = tmp_path / "cockpit.db"
        database.write_bytes(b"x" * 4096)
        (tmp_path / "cockpit.db-wal").write_bytes(b"")
        row = _one_row(tmp_path, db_path=database)
        assert row["wal_kb"] == 0

    def test_file_kb_takes_no_handle(self, tmp_path):
        """A stat, and nothing else. An instrument that opened the database to
        measure a contended WAL would change what it measures."""
        import ast
        import inspect

        import scripts.run_loop as mod

        tree = ast.parse(inspect.getsource(mod.file_kb))
        fn = tree.body[0]
        # Docstrings stripped, or the prose describing what it must not do
        # would satisfy the search for what it must not do.
        if ast.get_docstring(fn) is not None:
            fn.body = fn.body[1:]
        body = ast.unparse(fn)
        for forbidden in ("sqlite3", "connect(", "PRAGMA", "execute("):
            assert forbidden not in body, f"file_kb touches {forbidden}"
        assert file_kb(tmp_path / "nope") is None


# ---------------------------------------------------------------------------
# 2. The pass counts ride along, and `None` when there is no previous pass
# ---------------------------------------------------------------------------


class TestTheStorageLegsSitBesideTheWal:
    """`leg_price_link_ms` and `leg_store_quotes_ms` were already computed on
    `PassCounts` and were readable only from a log line. On one row beside
    `wal_kb` and `candidate_rows` they become a time series."""

    def test_the_previous_passs_legs_are_carried(self, tmp_path):
        counts = PassCounts()
        counts.leg_price_link_ms = 32_200
        counts.leg_store_quotes_ms = 17_000
        counts.candidate_rows = 4_311
        counts.leg_price_candidates_ms = 30_100
        row = _one_row(tmp_path, counts=counts)
        assert row["leg_price_link_ms"] == 32_200
        assert row["leg_store_quotes_ms"] == 17_000
        assert row["candidate_rows"] == 4_311
        assert row["candidate_ms"] == 30_100

    def test_no_previous_pass_is_null_not_zero(self, tmp_path):
        """The first pass after a restart. Zeroes here would put a false flat
        stretch into exactly the region a restart makes interesting."""
        row = _one_row(tmp_path, counts=None)
        for key in (
            "leg_price_link_ms",
            "leg_store_quotes_ms",
            "candidate_rows",
            "candidate_ms",
        ):
            assert key in row, key
            assert row[key] is None, key

    def test_a_telemetry_failure_never_kills_the_pass(self, tmp_path):
        """The whole line is best-effort. An unwritable log, a stat that
        raises and a counts object of the wrong shape must all degrade to
        silence rather than to a consecutive failure."""
        record_pass_rss(
            tmp_path,  # a directory: open() for append fails
            now_ms=NOW,
            kind="quote",
            produced_by=None,
            proc=_fake_proc(tmp_path),
            db_path=tmp_path / "cockpit.db",
            counts=object(),
        )


class TestOnePassSuppliesBoth:
    """A field nothing supplies reads null forever -- this repo has shipped
    four complete modules that nothing called (`tasks/lessons.md`), and the
    sampler's own caller test exists for the same reason.

    Mutation: drop `db_path=` or `counts=` from the call in `one_pass`.
    """

    def _one_pass_body(self) -> str:
        src = (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        body = src[src.index("async def one_pass") :]
        return body[: body.index("log.info(")]

    def test_the_sample_is_given_the_database_path(self):
        call = self._one_pass_body()
        start = call.index("record_pass_rss(")
        window = call[start : start + 600]
        assert "db_path=" in window, "the sampler cannot stat what it is not told"

    def test_the_sample_is_given_the_previous_counts(self):
        call = self._one_pass_body()
        start = call.index("record_pass_rss(")
        window = call[start : start + 600]
        assert "counts=last_counts[0]" in window

    def test_the_counts_are_published_before_the_second_half(self):
        """A pass that dies in scoring must still hand its legs forward --
        those are the passes a diagnosis most wants."""
        body = self._one_pass_body()
        assert body.index("last_counts[0] = counts") < body.index(
            "score_settle_and_alert(kind"
        )


# ---------------------------------------------------------------------------
# 3. candidate_rows is the count actually returned
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "candidates.db")
    yield c
    c.close()


def _fixture_rows(
    conn, sport_key: str, n: int, *, books: int = 3, commence=NOW, start: int = 0
):
    """`books` snapshot rows per fixture, so DISTINCT has something to do.

    `start` offsets the fixture ids so a second call ADDS fixtures rather than
    re-inserting the same ones under more bookmakers.
    """
    for i in range(start, start + n):
        for b in range(books):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, sport_key, "
                "odds_event_id, commence_ms, home_team, away_team, bookmaker, "
                "market, outcome_name, price_decimal) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    NOW,
                    sport_key,
                    f"{sport_key}-evt-{i}",
                    commence,
                    f"Team {i}A",
                    f"Team {i}B",
                    f"book{b}",
                    "h2h",
                    f"Team {i}A",
                    1.9,
                ),
            )
    conn.commit()


def games(sport_key: str, n: int) -> list[DiscoveredEvent]:
    return [
        DiscoveredEvent(
            event_ticker=f"KX{sport_key.upper()}-{i}",
            series_ticker=f"KX{sport_key.upper()}",
            league=sport_key,
            sport_key=sport_key,
            market_type="moneyline",
            title=f"Team {i}A vs Team {i}B",
            commence_ms=NOW,
            markets=(),
        )
        for i in range(n)
    ]


class TestCandidateRowsIsTheRealCount:
    """The number that was unmeasured, and the gap in the whole analysis.

    Mutation: `candidate_stats["rows"] = sum(...)` -> `= candidate_calls`, or
    -> a literal. Each of the first three tests goes red.
    """

    def test_it_counts_distinct_fixtures_not_snapshot_rows(self, conn):
        _fixture_rows(conn, "baseball_mlb", 7, books=4)
        stats: dict = {}
        link_discovered_events(
            conn, games("baseball_mlb", 3), now=NOW, candidate_stats=stats
        )
        # 28 snapshot rows, 7 distinct fixtures. The query is SELECT DISTINCT
        # and the figure must be what it returned, not what it scanned.
        assert stats["rows"] == 7

    def test_it_does_not_multiply_by_the_number_of_events(self, conn):
        """`_match_candidates` is cached per sport per pass, so twenty events
        pay for one scan. Reporting twenty times the population would restate
        the very bug ADR-era caching removed."""
        _fixture_rows(conn, "baseball_mlb", 5)
        stats: dict = {}
        link_discovered_events(
            conn, games("baseball_mlb", 20), now=NOW, candidate_stats=stats
        )
        assert stats["calls"] == 1
        assert stats["rows"] == 5

    def test_two_sports_sum(self, conn):
        _fixture_rows(conn, "baseball_mlb", 6)
        _fixture_rows(conn, "basketball_wnba", 2)
        stats: dict = {}
        link_discovered_events(
            conn,
            games("baseball_mlb", 3) + games("basketball_wnba", 3),
            now=NOW,
            candidate_stats=stats,
        )
        assert stats["calls"] == 2
        assert stats["rows"] == 8

    def test_it_moves_when_the_population_moves(self, conn):
        """Not a cached or constant figure: the same call on a database with
        more fixtures reports more. A hardcoded value passes every test above
        and fails this one."""
        _fixture_rows(conn, "baseball_mlb", 2)
        first: dict = {}
        link_discovered_events(
            conn, games("baseball_mlb", 3), now=NOW, candidate_stats=first
        )
        _fixture_rows(conn, "baseball_mlb", 9, start=2)
        second: dict = {}
        link_discovered_events(
            conn, games("baseball_mlb", 3), now=NOW, candidate_stats=second
        )
        assert first["rows"] == 2
        assert second["rows"] == 11

    def test_the_24_hour_cutoff_is_respected(self, conn):
        """`since_ms = now - 86_400_000`. A fixture that has aged out is not
        in the population the leg pays for, and must not be counted as
        though it were."""
        _fixture_rows(conn, "baseball_mlb", 4)
        _fixture_rows(
            conn,
            "baseball_mlb",
            3,
            commence=NOW - 86_400_000 - 60_000,
            start=100,
        )
        stats: dict = {}
        link_discovered_events(
            conn, games("baseball_mlb", 2), now=NOW, candidate_stats=stats
        )
        assert stats["rows"] == 4

    def test_the_elapsed_ms_is_reported(self, conn):
        """It was already computed and went nowhere but a WARNING above 8s, so
        the ordinary pass -- the one a series is made of -- recorded nothing."""
        _fixture_rows(conn, "baseball_mlb", 3)
        stats: dict = {}
        link_discovered_events(
            conn, games("baseball_mlb", 3), now=NOW, candidate_stats=stats
        )
        assert "ms" in stats and stats["ms"] >= 0

    def test_omitting_the_dict_changes_nothing(self, conn):
        """Optional in the signature so the linking tests need not care. The
        production call site is guarded by `tests/test_has_callers.py`."""
        _fixture_rows(conn, "baseball_mlb", 3)
        link_discovered_events(conn, games("baseball_mlb", 3), now=NOW)


class TestThePassCountsCarryIt:
    """`run_pricing_pass` is the only production caller, and the counts are
    what `record_pass_rss` reads."""

    def test_the_fields_exist_and_are_always_reported(self):
        counts = PassCounts()
        assert "candidate_rows" in counts.as_dict()
        assert "leg_price_candidates_ms" in counts.as_dict()
        assert counts.as_dict()["candidate_rows"] == 0

    def test_the_pricing_pass_assigns_them(self):
        """Mutation: delete either assignment in `run_pricing_pass`."""
        src = (ROOT / "backend" / "runner.py").read_text(encoding="utf-8")
        assert 'counts.candidate_rows = candidate_stats.get("rows", 0)' in src
        assert (
            'counts.leg_price_candidates_ms = candidate_stats.get("ms", 0)' in src
        )


# ---------------------------------------------------------------------------
# 4. An old row still parses, in every reader
# ---------------------------------------------------------------------------


OLD_SHAPE = {
    "ms": NOW,
    "kind": "quote",
    "rss_kb": 714000,
    "available_kb": 666000,
}


class TestAnOldRowStillParses:
    """The file is append-only and capped by tail, so on the day the fields
    landed the newest ~8,000 lines are a MIXTURE of shapes. A reader that
    refuses the old shape refuses the history the new fields are compared
    against -- and would take the whole diagnosis with it.

    Mutation: `record.get(name)` -> `record[name]` in `_q_loop_rss`. Both
    tests below go red with a KeyError.
    """

    def _run(self, tmp_path, rows, tail=10):
        (tmp_path / "loop_rss.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        args = argparse.Namespace(
            db=str(tmp_path / "cockpit.db"), tail=tail, limit=DEFAULT_ROW_CAP
        )
        return QUERIES["loop-rss"].run(None, args)[0]

    def test_a_row_from_before_the_fields_existed_reads_as_null(self, tmp_path):
        section = self._run(tmp_path, [OLD_SHAPE])
        assert section.row_count == 1
        row = dict(zip(section.columns, section.rows[0]))
        assert row["rss_kb"] == 714000
        for key in ("wal_kb", "db_kb", "candidate_rows", "leg_price_link_ms"):
            assert row[key] is None, key

    def test_old_and_new_rows_read_side_by_side(self, tmp_path):
        new = dict(OLD_SHAPE, ms=NOW + 15_000)
        new.update(
            wal_kb=225_356,
            db_kb=1_865_420,
            candidate_rows=4_311,
            candidate_ms=30_100,
            leg_price_link_ms=32_200,
            leg_store_quotes_ms=17_000,
        )
        section = self._run(tmp_path, [OLD_SHAPE, new])
        assert section.row_count == 2
        newest = dict(zip(section.columns, section.rows[0]))
        oldest = dict(zip(section.columns, section.rows[1]))
        assert newest["ms"] == NOW + 15_000, "rows are not newest-first"
        assert newest["wal_kb"] == 225_356
        assert oldest["wal_kb"] is None

    def test_a_missing_file_is_zero_rows_not_a_crash(self, tmp_path):
        args = argparse.Namespace(
            db=str(tmp_path / "cockpit.db"), tail=5, limit=DEFAULT_ROW_CAP
        )
        section = QUERIES["loop-rss"].run(None, args)[0]
        assert section.row_count == 0

    def test_an_unparseable_line_is_skipped_and_counted(self, tmp_path):
        """A truncated final line is what a killed process leaves. Dropping
        the whole file over it would lose the record the kill is diagnosed
        from."""
        (tmp_path / "loop_rss.jsonl").write_text(
            json.dumps(OLD_SHAPE) + "\n" + '{"ms": 1, "kin\n',
            encoding="utf-8",
        )
        args = argparse.Namespace(
            db=str(tmp_path / "cockpit.db"), tail=5, limit=DEFAULT_ROW_CAP
        )
        section = QUERIES["loop-rss"].run(None, args)[0]
        assert section.row_count == 1
        assert "1 unparseable" in section.title

    def test_the_reader_looks_beside_the_database(self, tmp_path):
        assert loop_rss_path(str(tmp_path / "cockpit.db")) == (
            tmp_path.resolve() / "loop_rss.jsonl"
        )

    def test_the_cli_exits_zero_and_prints_the_line(self, tmp_path, capsys):
        database = tmp_path / "cockpit.db"
        db.init_db(database).close()
        (tmp_path / "loop_rss.jsonl").write_text(
            json.dumps(OLD_SHAPE) + "\n", encoding="utf-8"
        )
        assert inspect_main(["loop-rss", "--db", str(database)]) == 0
        out = capsys.readouterr().out
        assert "# loop-rss" in out
        assert "wal_kb" in out


class TestTheWriterAndTheReaderAgree:
    """A round trip, because two lists of column names in two files is exactly
    how an instrument goes quietly blank."""

    def test_every_written_key_is_a_column_the_reader_renders(self, tmp_path):
        counts = PassCounts()
        counts.leg_price_link_ms = 1
        counts.leg_store_quotes_ms = 2
        counts.candidate_rows = 3
        counts.leg_price_candidates_ms = 4
        database = tmp_path / "cockpit.db"
        database.write_bytes(b"x" * 4096)
        (tmp_path / "cockpit.db-wal").write_bytes(b"y" * 2048)
        written = _one_row(tmp_path, db_path=database, counts=counts)

        args = argparse.Namespace(
            db=str(database), tail=5, limit=DEFAULT_ROW_CAP
        )
        section = QUERIES["loop-rss"].run(None, args)[0]
        rendered = dict(zip(section.columns, section.rows[0]))
        missing = set(written) - set(rendered)
        assert not missing, f"the reader drops {sorted(missing)}"
        for key, value in written.items():
            assert rendered[key] == value, key
