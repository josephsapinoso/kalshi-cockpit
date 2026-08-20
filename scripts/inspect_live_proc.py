"""Read-only process-memory report for the live machine, invoked by path.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_proc.py"

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

Two structural properties
-------------------------
**It cannot modify anything.** No `unlink`, no write-mode `open`, no
subprocess. Every filesystem call is a read of a `/proc` text file or a
directory listing.

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
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MEMINFO_KEYS = ("MemTotal", "MemFree", "MemAvailable", "Cached", "SwapFree")


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


def processes(proc_root: Path) -> list[dict]:
    """One dict per live process: pid, name, rss_kb, cmdline. RSS-descending.

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
            }
        )
    rows.sort(key=lambda r: r["rss_kb"], reverse=True)
    return rows


def report(proc_root: Path) -> dict:
    return {
        "observed_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "meminfo_kb": read_meminfo(proc_root),
        "processes": processes(proc_root),
    }


def render_text(data: dict) -> str:
    lines = [f"# proc report at {data['observed_at']}", ""]
    mem = data["meminfo_kb"]
    for key in MEMINFO_KEYS:
        if key in mem:
            lines.append(f"{key:<14} {mem[key]:>12,} kB  {mem[key] / 1024:,.1f} MiB")
    lines.append("")
    lines.append(f"{'pid':>7}  {'rss':>12}  name / cmdline")
    for row in data["processes"]:
        lines.append(
            f"{row['pid']:>7}  {row['rss_kb'] / 1024:>8,.1f} MiB  "
            f"{row['name']}  {row['cmdline'][:90]}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--proc", default="/proc", help="proc root (tests)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    data = report(Path(args.proc))
    print(json.dumps(data) if args.json else render_text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
