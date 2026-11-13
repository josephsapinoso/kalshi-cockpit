"""Write a consistent copy of the live database for the home rehearsal, invoked by path.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/snapshot_live_db.py --out /data/rehearsal-copy.db"

then `flyctl ssh sftp get /data/rehearsal-copy.db` from the laptop, then
`--delete /data/rehearsal-copy.db` to remove it (docs/runbooks/home-rehearsal.md).

Why this file exists
--------------------
The home rehearsal times the same pages against Fly and against a copy on the
home machine. The page cost this repo has measured is page-cache residency of
a file larger than the box's memory (ADR 0188 §2), so a seeded demo database
cannot stand in for the copy: it is the size of the file that is being tested.

Copying the file with `sftp get` while the chain runner writes can produce a
torn copy, so the copy is made here with SQLite's online backup API, which
yields a consistent snapshot while the writer keeps running. It copies in
batches and sleeps between them, so the writer is never locked out for long.

**The volume filled once (2026-08-16) and the machine died with it.** A copy
needs as much free space as the file itself. So this refuses unless the target
filesystem's free space exceeds the source size by `--headroom` (default 1.5x)
plus 1 GiB. Fly's volume auto-extend fires at 80% use; this script does not
rely on it.

What it can write: one file, at `--out`, which must end in `.db`, must not
exist yet, and must not be the source. What it can delete: only a path passed
to `--delete` whose name is `rehearsal-copy.db`. Nothing else.

What this does not establish
----------------------------
- That the copy is current when it is served. It is a snapshot; the live file
  moves on as soon as this finishes.
- That the copy reads at the same speed as the live file on Fly. That is the
  rehearsal's question, answered on the home machine.
- The live box's behaviour while the copy runs. The backup reads every page of
  the file once, which evicts other pages from the cache; expect the desk to be
  slower for some minutes afterwards, and run it outside a game window.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

GIB = 1024**3
DEFAULT_HEADROOM = 1.5
PAGES_PER_STEP = 4096
SLEEP_BETWEEN_STEPS_S = 0.05
DELETABLE_NAME = "rehearsal-copy.db"


class Refused(Exception):
    """A precondition failed; nothing was written."""


def free_bytes(path: Path) -> int:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def check_room(source: Path, out: Path, headroom: float) -> tuple[int, int]:
    """Return (need, free) or raise Refused when the copy would not fit."""
    size = source.stat().st_size
    wal = source.with_name(source.name + "-wal")
    if wal.exists():
        size += wal.stat().st_size
    need = int(size * headroom) + GIB
    free = free_bytes(out.parent)
    if free < need:
        raise Refused(
            f"not enough free space on {out.parent}: free {free / GIB:.2f} GiB, "
            f"need {need / GIB:.2f} GiB ({headroom}x the {size / GIB:.2f} GiB "
            f"source plus 1 GiB). Nothing was written."
        )
    return need, free


def check_paths(source: Path, out: Path) -> None:
    if not source.exists():
        raise Refused(f"source {source} does not exist")
    if out.suffix != ".db":
        raise Refused(f"--out must end in .db, got {out}")
    # Before the exists check, so pointing --out at the live file is named for
    # what it is rather than reported as an ordinary existing file.
    if out.resolve() == source.resolve():
        raise Refused("--out is the source database")
    if out.exists():
        raise Refused(f"{out} already exists; delete it first with --delete")
    if not out.parent.is_dir():
        raise Refused(f"{out.parent} is not a directory")


def snapshot(source: Path, out: Path, *, pages: int = PAGES_PER_STEP,
             sleep_s: float = SLEEP_BETWEEN_STEPS_S) -> None:
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(str(out))
    started = time.monotonic()
    last = [0.0]

    def progress(_status: int, remaining: int, total: int) -> None:
        now = time.monotonic()
        if now - last[0] >= 10 or remaining == 0:
            last[0] = now
            done = total - remaining
            print(f"[snapshot] {done}/{total} pages "
                  f"({100 * done / max(total, 1):.0f}%) "
                  f"{now - started:.0f}s", flush=True)
        time.sleep(sleep_s)

    try:
        src.backup(dst, pages=pages, progress=progress)
        dst.execute("PRAGMA journal_mode=DELETE")
        ok = dst.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if ok != "ok":
        out.unlink(missing_ok=True)
        raise Refused(f"quick_check on the copy returned {ok!r}; copy removed")
    print(f"[snapshot] wrote {out} ({out.stat().st_size / GIB:.2f} GiB), "
          f"quick_check ok, {time.monotonic() - started:.0f}s", flush=True)


def delete_copy(path: Path) -> None:
    if path.name != DELETABLE_NAME:
        raise Refused(f"--delete only removes a file named {DELETABLE_NAME}")
    if not path.exists():
        print(f"[snapshot] {path} does not exist; nothing to delete")
        return
    path.unlink()
    print(f"[snapshot] deleted {path}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path,
                    default=Path(os.environ.get("DB_PATH", "/data/cockpit.db")))
    ap.add_argument("--out", type=Path, help=f"where to write; name it {DELETABLE_NAME}")
    ap.add_argument("--headroom", type=float, default=DEFAULT_HEADROOM)
    ap.add_argument("--delete", type=Path, help=f"remove a {DELETABLE_NAME} and exit")
    args = ap.parse_args(argv)
    try:
        if args.delete is not None:
            delete_copy(args.delete)
            return 0
        if args.out is None:
            ap.error("--out or --delete is required")
        if args.headroom < 1.0:
            raise Refused("--headroom below 1.0 cannot fit a copy")
        check_paths(args.db, args.out)
        need, free = check_room(args.db, args.out, args.headroom)
        print(f"[snapshot] free {free / GIB:.2f} GiB >= need {need / GIB:.2f} GiB",
              flush=True)
        snapshot(args.db, args.out)
    except Refused as exc:
        print(f"[snapshot] REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
