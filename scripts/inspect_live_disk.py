"""Read-only disk report for the live volume, invoked by path.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_disk.py"

Why this file exists
--------------------
On 2026-08-16 the live machine died with
`sqlite3.OperationalError: database or disk is full`. The chain runner raised,
the entrypoint tore the container down as designed, and the machine stopped --
which on `fly.live.toml` means the record stops growing and candlesticks age
out unrecovered.

**Nothing on the machine could say what filled it.** `inspect_live_db.py`
answers questions about rows; a full volume is a question about bytes, and the
governance rule -- `flyctl ssh console` may only invoke a committed, reviewed
script by path -- meant there was no way to ask it. That is the same gap the
actionable population had: the failure was legible in the logs and its *cause*
was not readable at all.

This is deliberately the narrowest thing that answers it: capacity, free space,
and the largest files under the volume. It reports and never deletes.

Two structural properties
-------------------------
**It cannot modify anything.** There is no `unlink`, no `truncate`, no `open`
for write, and no subprocess. The only filesystem calls are `statvfs`, `walk`
and `stat`. A future edit that adds a deletion is a visible diff on a file
whose whole stated purpose is that it does not delete -- and deleting from the
volume that holds the money record should be a separate, argued change.

**It never opens a file it lists.** Sizes come from `stat`, so no contents
reach the transcript. `/data` holds the operational database; a report that
read bytes out of it would be a way to get row data into a log through the
back door.

What this does not establish
----------------------------
- **Nothing about what is safe to delete.** It ranks by size. The largest file
  is usually the database itself, and that is not a candidate. Deciding what
  may go needs to know which artefacts are reproducible -- Parquet snapshots
  are, the SQLite file is not -- and that judgement is not encoded here.
- **Nothing about growth rate.** One reading is a level, not a trend. Two
  readings apart in time give a rate; this prints one.
- **`df` and the file walk can disagree, and the gap is the finding.** Space
  held by a deleted-but-still-open file (a rotated log an running process has
  not released, a SQLite WAL mid-checkpoint) is charged to the filesystem and
  invisible to `walk`. If free space is low and the walk does not account for
  it, that difference is the answer, not a rounding error.
- **Nothing about whether SQLite can write.** A database can fail to grow with
  bytes still free -- a full WAL, a read-only mount, a quota. "Free space
  exists" is not "the write will succeed".
"""

from __future__ import annotations

import argparse
import json
import os
import stat as stat_module
import sys
from dataclasses import dataclass
from typing import Any, Optional, Sequence

# The live volume, matching `inspect_live_db.py`'s `DEFAULT_DB` directory.
DEFAULT_ROOT = "/data"

# Enough to find what filled a volume without dumping a directory listing into
# a transcript. The count is reported, so a cap that hides something says so.
DEFAULT_TOP = 25

_UNITS = ("B", "KiB", "MiB", "GiB", "TiB")


@dataclass(frozen=True)
class Entry:
    path: str
    bytes_: int


def human(n: float) -> str:
    """Bytes as a short human string.

    Printed *beside* the exact byte count, never instead of it: "1.0 GiB" is
    the readable form and the integer is the one a later reading can be
    differenced against.
    """
    for unit in _UNITS:
        if abs(n) < 1024 or unit == _UNITS[-1]:
            return f"{n:.1f} {unit}"
        n /= 1024
    raise AssertionError("unreachable")


def capacity(root: str) -> dict[str, Any]:
    """Total, used and free bytes for the filesystem holding `root`.

    `f_bavail` rather than `f_bfree`: the difference is the reserve only root
    may use, and the process that failed here does not run as root
    (`Dockerfile` runs non-root). Reporting `f_bfree` would show space the
    writer cannot actually have -- the flattering direction, on the exact
    question of why a write failed.
    """
    st = os.statvfs(root)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    return {
        "root": root,
        "total_bytes": total,
        "free_bytes": free,
        "used_bytes": total - free,
        "used_pct": round(100.0 * (total - free) / total, 2) if total else None,
    }


def walk(root: str) -> tuple[list[Entry], int, int]:
    """Every regular file under `root`, its total size, and an error count.

    Symlinks are not followed and their targets are not counted, so a link out
    of the volume cannot inflate the total. Unreadable entries are counted
    rather than raised on: a report that dies on one permission error tells you
    nothing about the other ten thousand files.
    """
    entries: list[Entry] = []
    total = 0
    errors = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.lstat(path)
            except OSError:
                errors += 1
                continue
            if not stat_module.S_ISREG(st.st_mode):
                continue
            entries.append(Entry(path, st.st_size))
            total += st.st_size
    entries.sort(key=lambda e: e.bytes_, reverse=True)
    return entries, total, errors


def by_extension(entries: Sequence[Entry]) -> list[tuple[str, int, int]]:
    """(extension, file count, summed bytes), largest first.

    This is the view that names a *cause* rather than a file. One 2 GiB
    database is a fact about the record; four thousand Parquet snapshots
    summing to 2 GiB is a fact about a job with no retention rule, and the
    top-N file list alone cannot tell those apart.
    """
    grouped: dict[str, list[int]] = {}
    for e in entries:
        ext = os.path.splitext(e.path)[1].lower() or "(none)"
        grouped.setdefault(ext, []).append(e.bytes_)
    rows = [(ext, len(sizes), sum(sizes)) for ext, sizes in grouped.items()]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


def report(root: str, top: int) -> dict[str, Any]:
    cap = capacity(root)
    entries, walked, errors = walk(root)
    return {
        "capacity": cap,
        "walked_bytes": walked,
        "walked_files": len(entries),
        "walk_errors": errors,
        # df-used minus walk-total. Positive means space is held by something
        # the walk cannot see -- most often a deleted file a process still has
        # open. See the module docstring; this is a finding, not a rounding.
        "unaccounted_bytes": cap["used_bytes"] - walked,
        "by_extension": [
            {"ext": ext, "files": n, "bytes": b} for ext, n, b in by_extension(entries)
        ],
        "largest": [{"path": e.path, "bytes": e.bytes_} for e in entries[:top]],
        "largest_truncated": len(entries) > top,
    }


def render_text(data: dict[str, Any]) -> str:
    cap = data["capacity"]
    out = [
        f"# disk  ({cap['root']})",
        "",
        f"total       {cap['total_bytes']:>14,}  {human(cap['total_bytes'])}",
        f"used        {cap['used_bytes']:>14,}  {human(cap['used_bytes'])}"
        f"  ({cap['used_pct']}%)",
        f"free        {cap['free_bytes']:>14,}  {human(cap['free_bytes'])}",
        "",
        f"walked      {data['walked_bytes']:>14,}  {human(data['walked_bytes'])}"
        f"  in {data['walked_files']:,} files"
        + (f", {data['walk_errors']} unreadable" if data["walk_errors"] else ""),
        f"unaccounted {data['unaccounted_bytes']:>14,}"
        f"  {human(data['unaccounted_bytes'])}"
        "   <- held by something the walk cannot see (see docstring)",
        "",
        "by extension",
        "------------",
    ]
    for row in data["by_extension"]:
        out.append(
            f"  {row['ext']:<12} {row['files']:>7,} files "
            f"{row['bytes']:>14,}  {human(row['bytes'])}"
        )
    out += ["", f"largest {len(data['largest'])} files", "-" * 24]
    for row in data["largest"]:
        out.append(f"  {row['bytes']:>14,}  {human(row['bytes']):>10}  {row['path']}")
    if data["largest_truncated"]:
        out.append("  ... more files exist; raise --top")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only disk report for the live volume. Never deletes."
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        print(f"no such directory: {args.root}", file=sys.stderr)
        return 2

    data = report(args.root, max(1, args.top))
    print(json.dumps(data, indent=2) if args.json else render_text(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
