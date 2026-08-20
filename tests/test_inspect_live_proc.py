"""`scripts/inspect_live_proc.py`: the RSS reader for the 585 MB question.

The database is not touched and no fixture is captured: `/proc` is faked
under `tmp_path`, because the machine these tests run on (Windows) has no
`/proc` at all -- which is itself the reason the script takes `--proc`.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the live machine's memory.** Every number here was written
  by this file.
- **Nothing about the 585 MB question.** A green suite says the instrument
  reads what the kernel writes; the observation is taken by sampling the
  live box either side of a full pass, and interpreted there.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.inspect_live_proc import (
    processes,
    read_meminfo,
    render_text,
    report,
)

ROOT = Path(__file__).resolve().parents[1]


def _fake_proc(tmp_path: Path) -> Path:
    proc = tmp_path / "proc"
    (proc / "123").mkdir(parents=True)
    (proc / "456").mkdir()
    (proc / "789").mkdir()
    (proc / "meminfo").write_text(
        "MemTotal:        2000000 kB\n"
        "MemFree:           69000 kB\n"
        "MemAvailable:     951000 kB\n"
        "Cached:          1000000 kB\n"
        "SwapFree:              0 kB\n"
        "Irrelevant:          123 kB\n",
        encoding="ascii",
    )
    (proc / "123" / "status").write_text(
        "Name:\tpython\nVmRSS:\t  585000 kB\n", encoding="ascii"
    )
    (proc / "123" / "cmdline").write_bytes(b"python\x00scripts/run_loop.py\x00")
    (proc / "456" / "status").write_text(
        "Name:\tuvicorn\nVmRSS:\t  120000 kB\n", encoding="ascii"
    )
    (proc / "456" / "cmdline").write_bytes(b"uvicorn\x00backend:app\x00")
    # A kernel thread: no VmRSS line. Must be skipped, not crashed on.
    (proc / "789" / "status").write_text("Name:\tkworker\n", encoding="ascii")
    (proc / "789" / "cmdline").write_bytes(b"")
    return proc


class TestTheReaderReportsWhatTheKernelWrote:
    def test_meminfo_keeps_the_named_keys_and_drops_the_rest(self, tmp_path):
        mem = read_meminfo(_fake_proc(tmp_path))
        assert mem["MemAvailable"] == 951000
        assert mem["MemFree"] == 69000
        assert "Irrelevant" not in mem

    def test_processes_are_rss_descending_with_cmdline(self, tmp_path):
        rows = processes(_fake_proc(tmp_path))
        assert [r["pid"] for r in rows] == [123, 456]
        assert rows[0]["rss_kb"] == 585000
        assert rows[0]["cmdline"] == "python scripts/run_loop.py"

    def test_a_kernel_thread_without_vmrss_is_skipped(self, tmp_path):
        rows = processes(_fake_proc(tmp_path))
        assert all(r["pid"] != 789 for r in rows)

    def test_a_process_dying_mid_walk_is_a_skip_not_a_crash(self, tmp_path):
        """Mutation: remove the OSError continue -- this raises instead.

        A pid directory with no readable files is the shape `/proc` presents
        when the process exits between `iterdir` and the read.
        """
        proc = _fake_proc(tmp_path)
        (proc / "999").mkdir()
        rows = processes(proc)
        assert [r["pid"] for r in rows] == [123, 456]

    def test_the_text_render_prints_mib_beside_kb(self, tmp_path):
        text = render_text(report(_fake_proc(tmp_path)))
        assert "951,000" in text  # MemAvailable in kB
        assert "571.3 MiB" in text  # 585000 kB

    def test_missing_meminfo_is_empty_not_fatal(self, tmp_path):
        (tmp_path / "empty").mkdir()
        assert read_meminfo(tmp_path / "empty") == {}


class TestTheReportCannotModifyAnything:
    """Same guard shape as `inspect_live_disk`: asserted against the source.

    Mutation: add `os.unlink(...)` or `open(p, "w")` anywhere -- the scan
    names it.
    """

    # Strip the module docstring, which legitimately names the forbidden
    # calls in prose -- same split `test_inspect_live_disk.py` uses.
    SOURCE = (
        (ROOT / "scripts" / "inspect_live_proc.py")
        .read_text(encoding="utf-8")
        .split('"""', 2)[-1]
    )

    def test_no_removal_write_or_subprocess_call(self):
        for pattern in (
            r"\bunlink\b",
            r"\brmdir\b",
            r"\bremove\b",
            r"\btruncate\b",
            r"\bsubprocess\b",
            r"open\([^)]*[\"'](?:w|a|r\+)[\"']",
            r"write_text|write_bytes",
        ):
            assert not re.search(pattern, self.SOURCE), pattern
