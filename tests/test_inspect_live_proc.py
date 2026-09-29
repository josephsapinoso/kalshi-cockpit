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

import json
import re
from pathlib import Path

import pytest

from scripts.inspect_live_proc import (
    DiffRefused,
    cpu_delta,
    lifetime_cpu_cores,
    main,
    processes,
    read_cpu_totals,
    read_meminfo,
    read_net_counters,
    read_pid_cpu,
    render_delta,
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


def _pid_stat(pid: int, comm: str, utime: int, stime: int, start: int) -> str:
    """A `/proc/<pid>/stat` line in proc(5)'s field order, fields 1-22+."""
    # Fields 3-13 (state .. cmajflt), then utime 14, stime 15, cutime 16,
    # cstime 17, priority 18, nice 19, num_threads 20, itrealvalue 21,
    # starttime 22, then vsize and rss to show the line carries on.
    middle = "S 1 1 1 0 -1 4194560 100 0 0 0"
    return (
        f"{pid} ({comm}) {middle} {utime} {stime} 0 0 20 0 4 0 {start} "
        f"123456789 5000\n"
    )


def _cpu_proc(
    root: Path,
    *,
    uptime: float,
    aggregate: str,
    pids: dict[int, tuple[str, int, int, int]],
) -> Path:
    """A fake `/proc` carrying the three CPU sources, one pid per entry."""
    proc = root / "proc"
    proc.mkdir(parents=True)
    (proc / "uptime").write_text(f"{uptime} 1234.56\n", encoding="ascii")
    (proc / "stat").write_text(
        f"cpu  {aggregate}\ncpu0 1 2 3 4 5 6 7 8 0 0\ncpu1 1 2 3 4 5 6 7 8 0 0\n"
        "intr 12345\nctxt 999\n",
        encoding="ascii",
    )
    for pid, (comm, utime, stime, start) in pids.items():
        (proc / str(pid)).mkdir()
        (proc / str(pid) / "status").write_text(
            f"Name:\t{comm}\nVmRSS:\t  100000 kB\n", encoding="ascii"
        )
        (proc / str(pid) / "cmdline").write_bytes(comm.encode() + b"\x00")
        (proc / str(pid) / "stat").write_text(
            _pid_stat(pid, comm, utime, stime, start), encoding="ascii"
        )
    return proc


class TestTheCpuReaderReportsWhatTheKernelWrote:
    def test_pid_stat_is_split_after_the_last_parenthesis(self, tmp_path):
        """Mutation: `partition(")")` -- the name's own `)` shifts every field.

        A process may call itself anything, spaces and parentheses included.
        """
        pid_dir = tmp_path / "42"
        pid_dir.mkdir()
        (pid_dir / "stat").write_text(
            _pid_stat(42, "py (a) b", utime=3000, stime=1500, start=10000),
            encoding="ascii",
        )
        assert read_pid_cpu(pid_dir) == {
            "utime_ticks": 3000,
            "stime_ticks": 1500,
            "start_ticks": 10000,
        }

    def test_a_process_with_no_stat_is_listed_with_no_cpu(self, tmp_path):
        """The memory half must not start depending on the CPU half."""
        rows = processes(_fake_proc(tmp_path))
        assert [r["pid"] for r in rows] == [123, 456]
        assert all(r["cpu"] is None for r in rows)

    def test_the_aggregate_line_is_read_and_cores_are_counted(self, tmp_path):
        proc = _cpu_proc(
            tmp_path, uptime=100.0, aggregate="10 1 20 300 4 0 2 7 0 0", pids={}
        )
        totals = read_cpu_totals(proc)
        assert totals["steal"] == 7
        assert totals["iowait"] == 4
        assert totals["cores"] == 2

    def test_a_short_aggregate_line_is_refused_not_zero_filled(self, tmp_path):
        """No `steal` column is not zero steal. Mutation: zip without the length check."""
        proc = _cpu_proc(tmp_path, uptime=100.0, aggregate="10 1 20 300", pids={})
        assert read_cpu_totals(proc) == {}

    def test_lifetime_share_is_cpu_seconds_over_process_age(self):
        # Started 100 s after boot, box up 1,000 s: 900 s old. 450 CPU s.
        cpu = {"utime_ticks": 30000, "stime_ticks": 15000, "start_ticks": 10000}
        assert lifetime_cpu_cores(cpu, 1000.0, 100) == pytest.approx(0.5)

    def test_a_process_under_a_second_old_has_no_lifetime_share(self):
        cpu = {"utime_ticks": 5, "stime_ticks": 0, "start_ticks": 99950}
        assert lifetime_cpu_cores(cpu, 1000.0, 100) is None

    def test_the_report_carries_the_lifetime_share(self, tmp_path):
        proc = _cpu_proc(
            tmp_path,
            uptime=1000.0,
            aggregate="10 1 20 300 4 0 2 7 0 0",
            pids={7: ("python", 30000, 15000, 10000)},
        )
        data = report(proc, clk_tck=100)
        assert data["processes"][0]["lifetime_cpu_cores"] == pytest.approx(0.5)
        assert " 0.500  python" in render_text(data)


def _reading(tmp_path: Path, tag: str, **kwargs) -> dict:
    return report(_cpu_proc(tmp_path / tag, **kwargs), clk_tck=100)


class TestTheIntervalDiff:
    def test_a_process_share_is_its_cpu_seconds_over_wall_seconds(self, tmp_path):
        before = _reading(
            tmp_path, "a", uptime=1000.0, aggregate="0 0 0 0 0 0 0 0 0 0",
            pids={7: ("python", 30000, 15000, 10000)},
        )
        after = _reading(
            tmp_path, "b", uptime=1060.0, aggregate="0 0 0 0 0 0 0 0 0 0",
            pids={7: ("python", 32000, 16000, 10000)},
        )
        delta = cpu_delta(before, after)
        assert delta["wall_s"] == pytest.approx(60.0)
        (row,) = delta["processes"]
        assert row["cpu_s"] == pytest.approx(30.0)
        assert row["cores"] == pytest.approx(0.5)

    def test_a_reused_pid_is_not_subtracted_from_its_predecessor(self, tmp_path):
        """Mutation: match on pid alone -- the new process reports -420 CPU s."""
        before = _reading(
            tmp_path, "a", uptime=1000.0, aggregate="0 0 0 0 0 0 0 0 0 0",
            pids={7: ("python", 30000, 15000, 10000)},
        )
        after = _reading(
            tmp_path, "b", uptime=1060.0, aggregate="0 0 0 0 0 0 0 0 0 0",
            pids={7: ("python", 2000, 1000, 102000)},
        )
        delta = cpu_delta(before, after)
        assert delta["processes"] == []
        assert delta["only_in_after"] == [7]
        assert delta["only_in_before"] == [7]

    def test_steal_and_iowait_are_reported_beside_busy_not_inside_it(self, tmp_path):
        """Mutation: count steal as busy -- busy_share reads 17%, not 15%."""
        before = _reading(
            tmp_path, "a", uptime=1000.0, aggregate="0 0 0 0 0 0 0 0 0 0", pids={},
        )
        # Over the interval: user 100, system 50, idle 800, iowait 30, steal 20.
        after = _reading(
            tmp_path, "b", uptime=1005.0, aggregate="100 0 50 800 30 0 0 20 0 0",
            pids={},
        )
        box = cpu_delta(before, after)["box"]
        assert box["busy_share"] == pytest.approx(0.15)
        assert box["iowait_share"] == pytest.approx(0.03)
        assert box["steal_share"] == pytest.approx(0.02)
        # 150 busy ticks at 100 Hz over 5 s: 0.3 of a core.
        assert box["busy_cores"] == pytest.approx(0.3)
        assert "steal 2.0%" in render_delta(cpu_delta(before, after))

    def test_a_restart_between_readings_is_refused(self, tmp_path):
        """Mutation: drop the wall_s check -- the diff divides by a negative."""
        before = _reading(
            tmp_path, "a", uptime=5000.0, aggregate="0 0 0 0 0 0 0 0 0 0", pids={},
        )
        after = _reading(
            tmp_path, "b", uptime=60.0, aggregate="0 0 0 0 0 0 0 0 0 0", pids={},
        )
        with pytest.raises(DiffRefused, match="restarted"):
            cpu_delta(before, after)

    def test_readings_in_different_clock_units_are_refused(self, tmp_path):
        before = _reading(
            tmp_path, "a", uptime=1000.0, aggregate="0 0 0 0 0 0 0 0 0 0", pids={},
        )
        after = dict(before, clk_tck=250, uptime_s=1060.0)
        with pytest.raises(DiffRefused, match="clock ticks"):
            cpu_delta(before, after)

    def test_the_diff_reads_saved_readings_past_the_ssh_banner(
        self, tmp_path, capsys
    ):
        """What `> before.json` actually captures can carry flyctl's own lines."""
        before = _reading(
            tmp_path, "a", uptime=1000.0, aggregate="0 0 0 0 0 0 0 0 0 0",
            pids={7: ("python", 30000, 15000, 10000)},
        )
        after = _reading(
            tmp_path, "b", uptime=1060.0, aggregate="0 0 0 0 0 0 0 0 0 0",
            pids={7: ("python", 32000, 16000, 10000)},
        )
        a, b = tmp_path / "before.json", tmp_path / "after.json"
        a.write_text("Connecting to fdaa::3... complete\n" + json.dumps(before) + "\n")
        b.write_text(json.dumps(after) + "\nError: ssh shell: exit 1\n")
        assert main(["--diff", str(a), str(b), "--json"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["processes"][0]["cores"] == pytest.approx(0.5)

    def test_a_refused_diff_exits_nonzero_and_says_why(self, tmp_path, capsys):
        a = tmp_path / "before.json"
        a.write_text("no json here\n")
        assert main(["--diff", str(a), str(a)]) == 2
        assert "refused" in capsys.readouterr().err


_SNMP = (
    "Ip: Forwarding DefaultTTL\n"
    "Ip: 2 64\n"
    "Tcp: RtoAlgorithm RtoMin RtoMax MaxConn ActiveOpens PassiveOpens "
    "AttemptFails EstabResets CurrEstab InSegs OutSegs RetransSegs InErrs OutRsts\n"
    "Tcp: 1 200 120000 -1 100 5000 3 7 12 900000 850000 40 0 55\n"
    "Udp: InDatagrams NoPorts\n"
    "Udp: 10 0\n"
)
_NETSTAT = (
    "TcpExt: SyncookiesSent ListenOverflows ListenDrops TCPTimeouts "
    "TCPSynRetrans TCPLostRetransmit TCPAbortOnTimeout\n"
    "TcpExt: 0 2 2 31 9 1 0\n"
    "IpExt: InNoRoutes InTruncatedPkts\n"
    "IpExt: 0 0\n"
)


def _net_proc(root: Path, snmp: str = _SNMP, netstat: str | None = _NETSTAT) -> Path:
    proc = root / "proc"
    (proc / "net").mkdir(parents=True)
    (proc / "net" / "snmp").write_text(snmp, encoding="ascii")
    if netstat is not None:
        (proc / "net" / "netstat").write_text(netstat, encoding="ascii")
    return proc


class TestTheTcpCountersAreReadByName:
    def test_named_counters_come_from_the_values_row_under_their_header(self, tmp_path):
        """Mutation: read the header row as values -- `int('ActiveOpens')` raises."""
        counters = read_net_counters(_net_proc(tmp_path))
        assert counters["Tcp.PassiveOpens"] == 5000
        assert counters["Tcp.RetransSegs"] == 40
        assert counters["TcpExt.ListenDrops"] == 2
        assert counters["TcpExt.TCPSynRetrans"] == 9

    def test_counters_not_asked_for_are_left_out(self, tmp_path):
        counters = read_net_counters(_net_proc(tmp_path))
        assert "Tcp.MaxConn" not in counters
        assert "TcpExt.SyncookiesSent" not in counters
        assert not any(key.startswith(("Ip", "Udp")) for key in counters)

    def test_a_missing_file_is_absent_keys_not_zeros(self, tmp_path):
        """Mutation: default the missing file's counters to 0 -- ListenDrops reads 0."""
        counters = read_net_counters(_net_proc(tmp_path, netstat=None))
        assert "Tcp.RetransSegs" in counters
        assert not any(key.startswith("TcpExt.") for key in counters)

    def test_the_diff_subtracts_only_counters_both_readings_carry(self):
        base = {"clk_tck": 100, "processes": [], "cpu_ticks": {}}
        before = dict(base, uptime_s=100.0, net_counters={"Tcp.RetransSegs": 40, "Tcp.PassiveOpens": 5000})
        after = dict(
            base, uptime_s=700.0,
            net_counters={"Tcp.RetransSegs": 61, "Tcp.PassiveOpens": 5600, "TcpExt.ListenDrops": 2},
        )
        delta = cpu_delta(before, after)
        assert delta["net"] == {"Tcp.PassiveOpens": 600, "Tcp.RetransSegs": 21}
        assert "Tcp.RetransSegs                  21" in render_delta(delta)

    def test_a_reading_from_before_the_counters_existed_is_unknown_not_zero(self):
        base = {"clk_tck": 100, "processes": [], "cpu_ticks": {}}
        before = dict(base, uptime_s=100.0)  # a pre-2026-09-29 reading
        after = dict(base, uptime_s=700.0, net_counters={"Tcp.RetransSegs": 61})
        delta = cpu_delta(before, after)
        assert delta["net"] == {}
        assert "tcp counters: not in both readings" in render_delta(delta)


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
