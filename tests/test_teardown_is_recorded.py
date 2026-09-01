"""The death instrument: a dying container names its dead child durably.

The 2026-08-29 gap read established that every pass gap ends with a child
process dying and the entrypoint naming it -- on stdout, which Fly retains for
~10 minutes, so the name was gone both times anyone asked. These tests pin the
two halves of the replacement instrument:

- `record_teardown` in `docker/entrypoint.sh` writes the child's name and the
  memory headroom to a file on the volume, and every death branch calls it.
- `record_pass_rss` in `scripts/run_loop.py` appends one line per pass so the
  memory trajectory INTO a death is on disk, and swallows every failure so
  telemetry can never be why a pass dies.

The bash function is behaviourally exercised rather than grepped, the same way
`test_entrypoint_restarts_on_failure.py` runs the real `shutdown`: the real
function is lifted from the real file and run, so a rewrite that keeps the
call sites and loses the write is still caught.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **That `dmesg` says anything on live.** As a non-root user under
  `kernel.dmesg_restrict` it may print nothing; the function must survive
  that, and here it is absent entirely.
- **Which child actually dies on live**, or why. This is the instrument, not
  the diagnosis.
- **Anything about /proc on the live box.** Every value here was written by
  this file, the same convention as `test_inspect_live_proc.py`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.run_loop import (
    RSS_LOG_CAP_BYTES,
    RSS_LOG_KEEP_BYTES,
    record_pass_rss,
)

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker" / "entrypoint.sh"


def _working_bash() -> str | None:
    """Same resolution as `test_entrypoint_restarts_on_failure.py`, for the
    same reason: bare "bash" can resolve to a WSL shim that cannot exec."""
    found = shutil.which("bash")
    if found is None:
        return None
    try:
        probe = subprocess.run([found, "-c", "exit 7"], capture_output=True)
    except OSError:
        return None
    return found if probe.returncode == 7 else None


BASH = _working_bash()


def _record_teardown_function() -> str:
    source = ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(
        r"^record_teardown\(\) \{.*?^\}", source, re.MULTILINE | re.DOTALL
    )
    assert match, "no `record_teardown()` in entrypoint.sh -- it was renamed"
    return match.group(0)


@pytest.mark.skipif(BASH is None, reason="no working bash on this machine")
class TestTheTeardownIsWrittenToTheVolume:
    def _run(self, tmp_path: Path, call: str) -> Path:
        log = tmp_path / "last_teardown.log"
        script = (
            f'TEARDOWN_LOG="{log.as_posix()}"\n'
            f'DB_PATH="{(tmp_path / "cockpit.db").as_posix()}"\n'
            f"{_record_teardown_function()}\n{call}\n"
        )
        assert BASH is not None
        result = subprocess.run([BASH, "-c", script], capture_output=True)
        assert result.returncode == 0, result.stderr
        return log

    def test_the_dead_child_is_named_with_a_timestamp(self, tmp_path):
        log = self._run(tmp_path, 'record_teardown "CHAIN RUNNER exited"')
        text = log.read_text(encoding="utf-8")
        assert "CHAIN RUNNER exited" in text
        # An ISO-8601 UTC stamp, because "when" is the first question the
        # reading asks and the file outlives many boots.
        assert re.search(r"=== \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z ", text)

    def test_deaths_append_rather_than_overwrite(self, tmp_path):
        """Two deaths in one day is the observed rate; the second must not
        erase the first."""
        log = self._run(
            tmp_path,
            'record_teardown "BACKEND exited"\n'
            'record_teardown "FRONTEND exited"',
        )
        text = log.read_text(encoding="utf-8")
        assert "BACKEND exited" in text
        assert "FRONTEND exited" in text

    def test_a_missing_dmesg_and_meminfo_do_not_fail_the_recording(
        self, tmp_path
    ):
        """On this machine neither exists, so passing at all IS the test --
        the function must exit 0 with only the header line written."""
        log = self._run(tmp_path, 'record_teardown "BACKEND exited"')
        assert "BACKEND exited" in log.read_text(encoding="utf-8")

    def test_the_default_path_sits_beside_the_database(self, tmp_path):
        """Unset, the log lands in `dirname DB_PATH` -- the volume, the one
        filesystem that survives the restart that follows every death."""
        script = (
            f'DB_PATH="{(tmp_path / "cockpit.db").as_posix()}"\n'
            f"{_record_teardown_function()}\n"
            'record_teardown "BACKEND exited"\n'
        )
        assert BASH is not None
        result = subprocess.run([BASH, "-c", script], capture_output=True)
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "last_teardown.log").exists()


class TestEveryDeathBranchRecords:
    """Population counts, not spot checks (`tasks/lessons.md`, 2026-08-26)."""

    def test_all_three_named_children_are_recorded(self):
        src = ENTRYPOINT.read_text(encoding="utf-8")
        calls = re.findall(r'^\s*record_teardown "(.+?)"', src, re.MULTILINE)
        assert sorted(calls) == [
            "BACKEND exited",
            "CHAIN RUNNER exited",
            "FRONTEND exited",
        ], (
            "every branch of the wait -n teardown must record which child "
            f"died; found {calls}"
        )

    def test_the_recording_happens_before_the_exit(self):
        """`shutdown 1` never returns, so a record after it is a record
        never written."""
        src = ENTRYPOINT.read_text(encoding="utf-8")
        exit_at = src.index("\nshutdown 1")
        for name in ("BACKEND", "CHAIN RUNNER", "FRONTEND"):
            call_at = src.index(f'record_teardown "{name} exited"')
            assert call_at < exit_at, f"{name}: recorded after `shutdown 1`"


class TestTheSamplerHasACaller:
    """This repo has shipped four complete, tested modules that nothing
    called (`tasks/lessons.md`). The sampler is useless unless the pass
    invokes it, and no behavioural test below would notice the call gone."""

    def test_one_pass_samples_before_it_works(self):
        src = (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        body = src[src.index("async def one_pass") :]
        call_at = body.find("record_pass_rss(")
        assert call_at != -1, "one_pass no longer samples RSS"
        # Before the work, not after: a wedged pass never reaches "after",
        # and the last line before a wedge is the whole point.
        first_work = min(
            x for x in (body.find("run_once("), body.find("run_quote_pass("))
            if x != -1
        )
        assert call_at < first_work, (
            "the RSS sample must precede the pass's work, or a wedge "
            "leaves no line"
        )


def _fake_proc(tmp_path: Path, rss_kb: int = 714000, avail_kb: int = 666000):
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


class TestTheRssCurveIsOnDisk:
    def test_one_line_per_pass_with_rss_and_headroom(self, tmp_path):
        log = tmp_path / "loop_rss.jsonl"
        proc = _fake_proc(tmp_path)
        record_pass_rss(
            log,
            now_ms=1_788_000_000_000,
            kind="quote",
            produced_by=None,
            proc=proc,
        )
        record_pass_rss(
            log,
            now_ms=1_788_000_015_000,
            kind="full",
            produced_by="quote",
            proc=proc,
        )
        rows = [
            json.loads(line)
            for line in log.read_text(encoding="utf-8").splitlines()
        ]
        # The storage fields are asserted in
        # `tests/test_pass_storage_telemetry.py` and the checkpoint fields in
        # `tests/test_wal_checkpoint.py`. Here they are only required to be
        # PRESENT and null, because this call supplies neither a database
        # path, nor a previous pass's counts, nor a checkpoint attempt --
        # `None` and not `0`, since a zero would read as "the WAL is empty"
        # (the opposite of the 2026-08-29 finding) or as "a checkpoint ran
        # and was not blocked", which is the reading the 2026-08-30 change
        # exists to make trustworthy.
        blank = {
            "wal_kb": None,
            "db_kb": None,
            "candidate_rows": None,
            "candidate_ms": None,
            "leg_price_link_ms": None,
            "leg_store_quotes_ms": None,
            "wal_ckpt_mode": None,
            "wal_ckpt_busy": None,
            "wal_ckpt_log_frames": None,
            "wal_ckpt_moved_frames": None,
            "wal_ckpt_error": None,
        }
        assert rows == [
            dict(
                ms=1_788_000_000_000,
                kind="quote",
                produced_by=None,
                rss_kb=714000,
                available_kb=666000,
                **blank,
            ),
            dict(
                ms=1_788_000_015_000,
                kind="full",
                produced_by="quote",
                rss_kb=714000,
                available_kb=666000,
                **blank,
            ),
        ]

    def test_the_reading_names_the_pass_that_produced_it(self, tmp_path):
        """`kind` and `rss_kb` describe different passes, and this is the field
        that separates them.

        The sample is taken before any work, so `kind` is the pass about to run
        while the memory is what the pass before it left. On 2026-08-29 a 570MB
        step was charged to the wrong pass type off exactly this confusion, and
        `Tempo.pass_kind` labelling the first pass of every process `"full"`
        unconditionally makes the line after a boot the worst case.
        """
        log = tmp_path / "loop_rss.jsonl"
        proc = _fake_proc(tmp_path)
        record_pass_rss(
            log, now_ms=1, kind="full", produced_by=None, proc=proc
        )
        record_pass_rss(
            log, now_ms=2, kind="quote", produced_by="full", proc=proc
        )
        rows = [
            json.loads(line)
            for line in log.read_text(encoding="utf-8").splitlines()
        ]

        # A boot line: nothing before it produced this reading, and that None
        # is also the restart marker the append-only file otherwise lacks.
        assert rows[0]["produced_by"] is None
        assert rows[0]["kind"] == "full"

        # The step between the two rows belongs to the full pass that ran
        # between them -- readable off the second row alone, without inferring
        # anything from the row above it.
        assert rows[1]["produced_by"] == "full"
        assert rows[1]["kind"] == "quote"

    def test_a_machine_with_no_proc_writes_nothing_and_raises_nothing(
        self, tmp_path
    ):
        """This is the dev-box branch -- Windows has no /proc -- and it is
        also the guard that telemetry can never kill a pass."""
        log = tmp_path / "loop_rss.jsonl"
        record_pass_rss(
            log,
            now_ms=1,
            kind="quote",
            produced_by="full",
            proc=tmp_path / "no-such-proc",
        )
        assert not log.exists()

    def test_an_unwritable_log_raises_nothing(self, tmp_path):
        """A full volume is precisely when this runs; it must degrade to
        silence, not to a sixth consecutive failure."""
        proc = _fake_proc(tmp_path)
        record_pass_rss(
            tmp_path,  # a directory: open() for append fails
            now_ms=1,
            kind="quote",
            produced_by="full",
            proc=proc,
        )

    def test_the_cap_keeps_the_newest_lines(self, tmp_path):
        """The file is a diagnostic on the data volume, and an uncapped
        diagnostic on that volume has filled it once already (2026-08-16)."""
        log = tmp_path / "loop_rss.jsonl"
        proc = _fake_proc(tmp_path)
        filler = json.dumps({"ms": 0, "kind": "quote", "rss_kb": 1}) + "\n"
        log.write_text(filler * (RSS_LOG_CAP_BYTES // len(filler) + 10))
        record_pass_rss(
            log, now_ms=99, kind="full", produced_by="quote", proc=proc
        )
        lines = log.read_text(encoding="utf-8").splitlines()
        assert log.stat().st_size <= RSS_LOG_KEEP_BYTES
        assert json.loads(lines[-1])["ms"] == 99

    #: A production line as actually written on live, measured 2026-09-01 at
    #: **286.6 bytes** mean. The fixture above uses a ~42-byte line -- 6.8x
    #: narrower -- and that single parameter is the whole reason the guard was
    #: verified for years against a case it never meets.
    LIVE_LINE_BYTES = 286

    def _wide_filler(self) -> str:
        """One log line padded to the production width."""
        bare = json.dumps({"ms": 0, "kind": "quote", "rss_kb": 1, "pad": ""})
        pad = self.LIVE_LINE_BYTES - len(bare) - 1
        assert pad > 0, "LIVE_LINE_BYTES is narrower than the bare object"
        return (
            json.dumps(
                {"ms": 0, "kind": "quote", "rss_kb": 1, "pad": "x" * pad}
            )
            + "\n"
        )

    def test_the_cap_binds_at_production_line_width(self, tmp_path):
        """The assertion above, re-asked in the right unit at the real width.

        The previous version of `test_the_cap_keeps_the_newest_lines` asserted
        `len(lines) <= RSS_LOG_KEEP_LINES` while the limit being enforced is a
        **byte** cap. Against its ~42-byte fixture the file held ~49,900 lines,
        the slice genuinely trimmed, and the assertion passed. Against a
        production 286-byte line the file holds ~7,317 lines at the cap, so
        `[-8000:]` kept every one of them and wrote the file back
        **unchanged** -- still over the cap, re-trimming on every pass forever.

        A line-count assertion cannot see that: `7,317 <= 8,000` is true of a
        file that was never trimmed. Asserting bytes is what makes the no-op
        visible. The defect was not a missing test; it was a passing one whose
        fixture differed from production in the single parameter the guard
        depends on.
        """
        log = tmp_path / "loop_rss.jsonl"
        proc = _fake_proc(tmp_path)
        filler = self._wide_filler()
        assert len(filler) == self.LIVE_LINE_BYTES, "fixture is not at width"

        log.write_text(filler * (RSS_LOG_CAP_BYTES // len(filler) + 10))
        before = log.stat().st_size
        assert before > RSS_LOG_CAP_BYTES, "fixture did not exceed the cap"

        record_pass_rss(
            log, now_ms=99, kind="full", produced_by="quote", proc=proc
        )

        after = log.stat().st_size
        assert after < before, (
            "the file was written back unchanged: at production line width "
            "the cap is a no-op that still runs on every pass"
        )
        assert after <= RSS_LOG_KEEP_BYTES, "trimmed, but not to the budget"
        # Hysteresis. Trimming to the trigger itself leaves the file one write
        # from tripping again, so the rewrite runs every pass even when the
        # units agree. The target must be strictly below the trigger.
        assert after <= RSS_LOG_CAP_BYTES // 2

        lines = log.read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[-1])["ms"] == 99, "newest line was not kept"
        for line in lines:
            json.loads(line)  # whole lines only; never starts mid-object
