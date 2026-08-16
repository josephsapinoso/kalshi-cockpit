"""The prop-rung analyser's loader: what it accepts and what it refuses.

Scope is deliberately the loader and nothing below it. The arithmetic in this
script is registered in
`docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md` and its
verdict is checked against that document by reading the run, not by a test
asserting a number here -- a test that restated the decision rule would be a
second copy of it, and the whole point of pre-registration is that there is one.

What these tests do cover is the two ways a dump can lie about its own extent:
being a prefix of the record, and being unreadable in the form it was stored.
Both produce a *number* rather than an error if the loader is careless, and a
number is what gets written down.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from scripts.analyze_prop_onesided import RefusedInput, load_rungs

_COLUMNS = [
    "odds_event_id",
    "bookmaker",
    "base_market",
    "is_alternate",
    "player",
    "point",
    "over_price",
    "under_price",
    "quote_rows",
    "fetched_ms",
]

_ROW = ["OE1", "betmgm", "batter_hits", 0, "A Player", 0.5, 1.9, 2.0, 2, 1000]


def _payload(*, truncated: bool = False, query: str = "prop-rungs") -> dict:
    return {
        "query": query,
        "db": "/data/cockpit.db",
        "sections": [
            {
                "title": "odds_snapshots: prop rungs",
                "columns": _COLUMNS,
                "rows": [list(_ROW)],
                "row_count": 1,
                "truncated": truncated,
                "cap": None,
            }
        ],
    }


def _write(path: Path, payload: dict) -> Path:
    text = json.dumps(payload)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


class TestAGzippedDumpReadsIdenticallyToAPlainOne:
    """The 2026-08-16 one-shot is 10MB raw and 261KB gzipped.

    A dump that can never be re-taken has to be committed to stay
    re-checkable, and this repo is going public, so the stored form is the
    compressed one. That is only safe if the two forms are the same input.

    Mutation: drop the `.gz` branch in `_read`. `json.loads` is then handed
    binary and raises `UnicodeDecodeError` -- loud, but from the wrong layer,
    and the failure a future session sees would point at the file rather than
    at the reader.
    """

    def test_the_two_forms_produce_the_same_rungs(self, tmp_path):
        plain = _write(tmp_path / "d.json", _payload())
        packed = _write(tmp_path / "d.json.gz", _payload())

        from_plain, excl_plain = load_rungs([plain])
        from_packed, excl_packed = load_rungs([packed])

        assert from_plain == from_packed
        assert excl_plain == excl_packed
        assert len(from_packed) == 1

    def test_a_gz_dump_is_not_read_as_bytes_by_accident(self, tmp_path):
        """Guards the decode, not just the open.

        `gzip.open` in binary mode would return bytes that `json.loads` still
        accepts, so a wrong mode passes a naive equality test. Asserting on a
        parsed string field forces the text path.
        """
        packed = _write(tmp_path / "d.json.gz", _payload())
        rungs, _ = load_rungs([packed])
        assert rungs[0].book == "betmgm"
        assert isinstance(rungs[0].book, str)


class TestATruncatedDumpIsRefusedRatherThanAnalysed:
    """A capped dump is the alphabetical front of the record, not a sample.

    Mutation: delete the `truncated` branch. The 2026-08-16 run then reports a
    feasibility census over 20,000 of 41,827 rungs -- the books whose names
    sort early -- and prints a per-bookmaker table that looks complete.

    This is not hypothetical: `tasks/NEXT.md` documented the dump command with
    `--limit 20000`, which truncates the real record by 52%.
    """

    def test_the_flag_stops_the_run(self, tmp_path):
        path = _write(tmp_path / "d.json", _payload(truncated=True))
        with pytest.raises(RefusedInput, match="truncated"):
            load_rungs([path])

    def test_a_truncated_gz_is_refused_too(self, tmp_path):
        """The compressed path must not bypass the check.

        Mutation: read `.gz` through a separate branch that forgets to run the
        section loop's guard. The stored one-shot is a `.gz`, so this is the
        path that actually carries the record.
        """
        path = _write(tmp_path / "d.json.gz", _payload(truncated=True))
        with pytest.raises(RefusedInput, match="truncated"):
            load_rungs([path])

    def test_a_dump_of_a_different_query_is_refused(self, tmp_path):
        path = _write(tmp_path / "d.json", _payload(query="clv-coverage"))
        with pytest.raises(RefusedInput, match="clv-coverage"):
            load_rungs([path])


class TestTheCommittedOneShotIsStillReadable:
    """The stored dump is the evidence for the 2026-08-16 UNMEASURABLE verdict.

    It can never be re-taken -- props came off the sweep schedule at v43 (ADR
    0032), so the record stopped growing. If this file ever stops loading, the
    result document is left citing numbers nothing can reproduce.

    Mutation: corrupt or re-compress the artefact. This is the only test that
    reads it, and it asserts the two counts the verdict turns on rather than
    the whole census.
    """

    DUMP = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "measurements"
        / "2026-08-16-prop-rungs-dump.json.gz"
    )

    def test_it_loads_and_carries_the_population_the_result_cites(self):
        rungs, _ = load_rungs([self.DUMP])
        alternates = [r for r in rungs if r.is_alternate]
        assert len(alternates) == 35_448
        assert [r for r in alternates if r.two_sided] == [], (
            "no alternate rung was ever quoted two-sided; this empty list IS "
            "the finding, and a non-empty one would overturn the verdict"
        )
