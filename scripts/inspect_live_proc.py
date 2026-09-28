"""Read-only process-memory and CPU report for the live machine, invoked by path.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_proc.py"

CPU over an interval is two `--json` readings saved on the laptop and
subtracted there. The diff reads two local files and touches no machine. A
full pass runs every 900 s, so readings 15+ minutes apart cover at least one:

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_proc.py --json" > before.json
    # ... 15+ minutes ...
    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_proc.py --json" > after.json
    python scripts/inspect_live_proc.py --diff before.json after.json

Why this file exists
--------------------
The ~585 MB resident-set question (open since 2026-08-19) has a registered
falsification -- RSS should rise during `leg_walk_ms` on a full pass and not
on a quote pass, because `run_kalshi_pass` materialises the whole event
catalogue into one list on full passes only -- and no committed script could
read a process's RSS. The governance rule (`flyctl ssh console` may only
invoke a committed, reviewed script by path) meant the number that decides
the question was unreadable, the same gap `inspect_live_disk.py` closed for
bytes on disk.

This is the narrowest thing that answers it: `/proc/meminfo`'s headline
lines and one line per process (name, RSS, command line). Sampled either
side of a full pass, the RSS delta is the observation.

**CPU was added 2026-09-28 (ADR 0188).** The performance record carries two
dozen measured bottlenecks and every "CPU" entry among them is a wall-clock
overrun: no reading of CPU *time* on the live box had ever been taken, and
Fly's metrics endpoint answered 401. Whether any part of the stack is
compute-bound -- the question a Rust rewrite would have to answer yes to --
was unanswerable without one. Each process now carries `utime`, `stime` and
its start time from `/proc/<pid>/stat`; the report carries `/proc/stat`'s
aggregate `cpu` line, including `steal` (time the hypervisor withheld from a
vCPU that had work), and `/proc/uptime`.

Two structural properties
-------------------------
**It cannot modify anything.** No `unlink`, no write-mode `open`, no
subprocess. Every filesystem call is a read of a `/proc` text file, a
directory listing, or -- for `--diff` only, on the laptop -- a read of a
saved reading.

**A process dying mid-walk is a skip, not a crash.** `/proc` entries are
ephemeral by design; a sampler that dies on the race would fail exactly when
the machine is busiest, which is when the sample matters.

What this does not establish
----------------------------
- **Nothing about what the bytes hold.** RSS is a size, not an inventory; a
  step at a full pass is consistent with the catalogue list AND with any
  other full-pass-only allocation. It narrows, it does not name.
- **Nothing about growth over days.** One reading is a level; deltas need
  two readings and the pass log between them.
- **CPython rarely returns freed memory to the OS.** A one-time step that
  then holds flat is what an *already-freed* transient spike looks like from
  outside; "held" and "leaking" are different claims and only the trend
  across many passes separates them.
- **Nothing about which code burns the CPU.** A process's CPU seconds are a
  total over every thread and every line; a high share for `run_loop.py`
  says the recorder is busy, not which leg. Attribution needs a profiler,
  and this file deliberately is not one.
- **A lifetime share is an average since the process started.** A box that
  restarted an hour ago reports that hour, boot-time cache warm-up included.
  The interval diff is the reading for "now"; the lifetime share speaks for
  "typically" only on a box that has been up for a day.
- **Steal is the guest's view.** It counts time withheld from a runnable
  vCPU and cannot say why (a neighbour, or a quota). An idle VM cannot be
  stolen from, so low steal on a quiet interval says nothing about a busy
  one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MEMINFO_KEYS = ("MemTotal", "MemFree", "MemAvailable", "Cached", "SwapFree")

# `/proc/stat`'s aggregate line in the kernel's order (proc(5)). `guest` and
# `guest_nice` follow and are already counted inside `user` and `nice`, so
# they are not read: summing them would count guest time twice.
CPU_FIELDS = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")

# A core doing nothing. `iowait` is idle time with I/O outstanding -- here,
# SQLite waiting on the volume -- and `steal` is time the host ran someone
# else. Neither is this VM's work, so both sit beside `busy`, never inside it.
_NOT_WORKING = ("idle", "iowait", "steal")


class DiffRefused(ValueError):
    """Two readings that cannot honestly be subtracted."""


def clock_ticks() -> int:
    """USER_HZ, the unit of every `/proc` CPU counter.

    USER_HZ is part of the Linux userspace ABI and is 100 on x86-64 and
    arm64. `os.sysconf` does not exist on Windows, where the tests run, so
    the ABI value is used there; the report records which value it used and
    a diff refuses two readings that disagree.
    """
    try:
        return int(os.sysconf("SC_CLK_TCK"))
    except (AttributeError, ValueError, OSError):
        return 100


def read_meminfo(proc_root: Path) -> dict[str, int]:
    """The named `/proc/meminfo` lines, in kB. Missing keys are absent."""
    out: dict[str, int] = {}
    try:
        text = (proc_root / "meminfo").read_text(encoding="ascii")
    except OSError:
        return out
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in MEMINFO_KEYS:
            out[key] = int(rest.split()[0])
    return out


def read_uptime_s(proc_root: Path) -> float | None:
    """Seconds since boot from `/proc/uptime`. `None` if unreadable."""
    try:
        text = (proc_root / "uptime").read_text(encoding="ascii")
    except OSError:
        return None
    try:
        return float(text.split()[0])
    except (IndexError, ValueError):
        return None


def read_cpu_totals(proc_root: Path) -> dict[str, int]:
    """`/proc/stat`'s aggregate `cpu` line in ticks, plus `cores`.

    Empty when unreadable, and empty when the line is shorter than
    `CPU_FIELDS`: a kernel that does not report `steal` has not reported
    zero steal, and filling the gap with 0 would say it had.
    """
    try:
        text = (proc_root / "stat").read_text(encoding="ascii")
    except OSError:
        return {}
    totals: dict[str, int] = {}
    cores = 0
    for line in text.splitlines():
        head, _, rest = line.partition(" ")
        if head == "cpu":
            values = rest.split()
            if len(values) < len(CPU_FIELDS):
                return {}
            totals = {key: int(value) for key, value in zip(CPU_FIELDS, values)}
        elif head.startswith("cpu") and head[3:].isdigit():
            cores += 1
    if totals:
        totals["cores"] = cores
    return totals


def read_pid_cpu(pid_dir: Path) -> dict[str, int] | None:
    """`utime`, `stime` and `starttime` from `/proc/<pid>/stat`, in ticks.

    Field 2 is the command name in parentheses and may itself hold spaces or
    `)` -- a process can name itself anything -- so the split is taken after
    the LAST `)`. `None` when the file is unreadable or short; the process
    is still listed, with no CPU.
    """
    try:
        text = (pid_dir / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    _, paren, rest = text.rpartition(")")
    if not paren:
        return None
    fields = rest.split()
    # proc(5) numbers fields from 1 and `rest` begins at field 3 (state), so
    # field n sits at index n - 3: utime is 14, stime 15, starttime 22.
    try:
        return {
            "utime_ticks": int(fields[14 - 3]),
            "stime_ticks": int(fields[15 - 3]),
            "start_ticks": int(fields[22 - 3]),
        }
    except (IndexError, ValueError):
        return None


def lifetime_cpu_cores(
    cpu: dict[str, int] | None, uptime_s: float | None, clk_tck: int
) -> float | None:
    """Average cores this process has used since it started.

    1.0 is one core flat out for the process's whole life. `None` when
    either input is unreadable, and for a process under a second old, where
    the ratio of two near-zero numbers is noise.
    """
    if cpu is None or uptime_s is None:
        return None
    age_s = uptime_s - cpu["start_ticks"] / clk_tck
    if age_s < 1.0:
        return None
    return (cpu["utime_ticks"] + cpu["stime_ticks"]) / clk_tck / age_s


def processes(proc_root: Path) -> list[dict]:
    """One dict per live process: pid, name, rss_kb, cmdline, cpu. RSS-descending.

    Kernel threads (no VmRSS) are skipped -- they hold no user memory and
    listing them would bury the two python processes this exists to read.
    """
    rows: list[dict] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="ascii")
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue  # died between listing and reading; see module docstring
        name = ""
        rss_kb = None
        for line in status.splitlines():
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("VmRSS:"):
                rss_kb = int(line.split(":", 1)[1].split()[0])
        if rss_kb is None:
            continue
        rows.append(
            {
                "pid": int(entry.name),
                "name": name,
                "rss_kb": rss_kb,
                "cmdline": cmdline.replace(b"\x00", b" ").decode(
                    "utf-8", "replace"
                ).strip(),
                "cpu": read_pid_cpu(entry),
            }
        )
    rows.sort(key=lambda r: r["rss_kb"], reverse=True)
    return rows


def report(proc_root: Path, *, clk_tck: int | None = None) -> dict:
    ticks = clock_ticks() if clk_tck is None else clk_tck
    uptime_s = read_uptime_s(proc_root)
    rows = processes(proc_root)
    for row in rows:
        row["lifetime_cpu_cores"] = lifetime_cpu_cores(row["cpu"], uptime_s, ticks)
    return {
        "observed_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "clk_tck": ticks,
        "uptime_s": uptime_s,
        "cpu_ticks": read_cpu_totals(proc_root),
        "meminfo_kb": read_meminfo(proc_root),
        "processes": rows,
    }


def _match_key(row: dict) -> tuple[int, int] | None:
    cpu = row.get("cpu")
    return None if cpu is None else (row["pid"], cpu["start_ticks"])


def cpu_delta(before: dict, after: dict) -> dict:
    """CPU used between two `report()` readings, whole box and per process.

    A process is matched on pid AND start time. A pid the kernel handed to a
    new process between the readings is a different process, and
    subtracting its counters from its predecessor's reports nonsense -- often
    negative. Processes found in only one reading are named by pid, not
    silently dropped.
    """
    if before.get("clk_tck") != after.get("clk_tck"):
        raise DiffRefused(
            f"clock ticks differ ({before.get('clk_tck')} vs "
            f"{after.get('clk_tck')}); the counters are in different units"
        )
    clk_tck = after["clk_tck"]
    up_before, up_after = before.get("uptime_s"), after.get("uptime_s")
    if up_before is None or up_after is None:
        raise DiffRefused("a reading carries no uptime, so the interval is unknown")
    wall_s = up_after - up_before
    if wall_s <= 0:
        raise DiffRefused(
            f"uptime went from {up_before} s to {up_after} s: the box restarted "
            f"between the readings, or they were given in the wrong order"
        )

    box = None
    ticks_before, ticks_after = before.get("cpu_ticks"), after.get("cpu_ticks")
    if ticks_before and ticks_after:
        moved = {key: ticks_after[key] - ticks_before[key] for key in CPU_FIELDS}
        total = sum(moved.values())
        if total > 0:
            busy = total - sum(moved[key] for key in _NOT_WORKING)
            box = {
                "cores": ticks_after["cores"],
                "busy_share": busy / total,
                "iowait_share": moved["iowait"] / total,
                "steal_share": moved["steal"] / total,
                "busy_cores": busy / clk_tck / wall_s,
            }

    earlier = {
        key: row for row in before["processes"] if (key := _match_key(row))
    }
    later_keys = set()
    rows: list[dict] = []
    new_pids: list[int] = []
    for row in after["processes"]:
        key = _match_key(row)
        if key is None or key not in earlier:
            new_pids.append(row["pid"])
            continue
        later_keys.add(key)
        prev, cur = earlier[key]["cpu"], row["cpu"]
        used_s = (
            cur["utime_ticks"] + cur["stime_ticks"]
            - prev["utime_ticks"] - prev["stime_ticks"]
        ) / clk_tck
        rows.append(
            {
                "pid": row["pid"],
                "name": row["name"],
                "cmdline": row["cmdline"],
                "cpu_s": used_s,
                "cores": used_s / wall_s,
            }
        )
    rows.sort(key=lambda r: r["cpu_s"], reverse=True)
    return {
        "from": before.get("observed_at"),
        "to": after.get("observed_at"),
        "wall_s": wall_s,
        "box": box,
        "processes": rows,
        "only_in_after": sorted(new_pids),
        "only_in_before": sorted(pid for pid, _ in earlier.keys() - later_keys),
    }


def load_reading(path: Path) -> dict:
    """One `--json` reading saved from an ssh session.

    `flyctl ssh console` can print lines of its own around the command's
    output, so the reading is the last line that is a JSON object, not the
    whole file.
    """
    for line in reversed(path.read_text(encoding="utf-8-sig").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise DiffRefused(f"{path} holds no JSON reading")


def _cores(value: float | None) -> str:
    return "   n/a" if value is None else f"{value:6.3f}"


def render_text(data: dict) -> str:
    lines = [f"# proc report at {data['observed_at']}", ""]
    mem = data["meminfo_kb"]
    for key in MEMINFO_KEYS:
        if key in mem:
            lines.append(f"{key:<14} {mem[key]:>12,} kB  {mem[key] / 1024:,.1f} MiB")
    uptime_s = data.get("uptime_s")
    cores = (data.get("cpu_ticks") or {}).get("cores")
    lines.append(
        f"uptime {'n/a' if uptime_s is None else f'{uptime_s / 3600:,.2f} h'}"
        f"  cores {'n/a' if cores is None else cores}"
    )
    lines.append("")
    lines.append(f"{'pid':>7}  {'rss':>12}  {'cores':>6}  name / cmdline")
    for row in data["processes"]:
        lines.append(
            f"{row['pid']:>7}  {row['rss_kb'] / 1024:>8,.1f} MiB  "
            f"{_cores(row.get('lifetime_cpu_cores'))}  "
            f"{row['name']}  {row['cmdline'][:90]}"
        )
    lines.append("")
    lines.append("cores = average since the process started; see --diff for now")
    return "\n".join(lines)


def render_delta(delta: dict) -> str:
    lines = [
        f"# cpu from {delta['from']} to {delta['to']}"
        f" ({delta['wall_s']:,.1f} s)",
        "",
    ]
    box = delta["box"]
    if box is None:
        lines.append("box: no aggregate cpu line in one reading")
    else:
        lines.append(
            f"box: {box['busy_cores']:.3f} of {box['cores']} cores busy"
            f"  busy {box['busy_share']:.1%}  iowait {box['iowait_share']:.1%}"
            f"  steal {box['steal_share']:.1%}"
        )
    lines.append("")
    lines.append(f"{'pid':>7}  {'cpu_s':>9}  {'cores':>6}  name / cmdline")
    for row in delta["processes"]:
        lines.append(
            f"{row['pid']:>7}  {row['cpu_s']:>9,.1f}  {row['cores']:6.3f}  "
            f"{row['name']}  {row['cmdline'][:90]}"
        )
    for label, key in (("only in after", "only_in_after"), ("only in before", "only_in_before")):
        if delta[key]:
            lines.append(f"{label}: {', '.join(str(p) for p in delta[key])}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--proc", default="/proc", help="proc root (tests)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--diff",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="subtract two saved --json readings (laptop side; reads files only)",
    )
    args = parser.parse_args(argv)
    if args.diff:
        try:
            delta = cpu_delta(
                load_reading(Path(args.diff[0])), load_reading(Path(args.diff[1]))
            )
        except DiffRefused as refusal:
            print(f"refused: {refusal}", file=sys.stderr)
            return 2
        print(json.dumps(delta) if args.json else render_delta(delta))
        return 0
    data = report(Path(args.proc))
    print(json.dumps(data) if args.json else render_text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
