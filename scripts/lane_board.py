"""Cross-worktree collision detector for parallel lanes. Read-only.

    .venv\\Scripts\\python.exe scripts/lane_board.py
    .venv\\Scripts\\python.exe scripts/lane_board.py --write
    .venv\\Scripts\\python.exe scripts/lane_board.py --lane-root PATH --strict-overlap

Why this file exists
--------------------
Work on this repo runs in parallel git worktrees ("lanes"), and on 2026-08-27
two of them collided three times in one day: ADR 0074 claimed twice, then 0077
claimed twice, then schema v23 claimed twice. Two of those merged **cleanly** --
two lanes writing `0077-a.md` and `0077-b.md` are different filenames, so git
says nothing at all, and every cross-reference to that number silently becomes
ambiguous.

`tests/test_parallel_lanes_do_not_collide.py` was added for exactly that and is
the right guard, but it names its own limit in its docstring: *"A test can only
see the tree it runs in. These fire when the lanes MERGE ... not at the moment
[the collision] is created."* Until this file, nothing in the repo could see two
lanes at once, and the oversight that existed was a hand-maintained table in
`tasks/NEXT.md` that was already wrong about both lanes within hours.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **It is a snapshot, not a lock, and it reserves nothing.** Two lanes can run
  it a second apart, both see a number free, and both take it. It shortens the
  window; it does not close it. A reservation is *stated* in `tasks/LANES.md`
  and honoured by convention -- nothing here enforces one.
- **It does not fix the ordinal counters and must not be read as fixing them.**
  `tasks/lessons.md:168-191` settled that: *"'Read `main` before taking one' is
  NOT the fix ... The fix is to allocate at MERGE time, not at write time."*
  What it genuinely establishes is the collision *surface* between live trees,
  for which no guard existed at all.
- **A predicted conflict is not a conflict.** Overlapping hunks mean a human
  will have to look at that file; they do not mean the merge fails, and
  non-overlapping edits to one file merge correctly. This is why file-level
  overlap is reported but does **not** fail the exit code by default: on the
  day this shipped, a file-level detector called `frontend/src/lib/api.ts` a
  collision when the two edits were 1,780 lines apart. `tasks/NEXT.md:99-103`
  pins the reason that matters -- a guard whose first finding is a false one
  gets weakened or deleted.
- **Inherited is not claimed.** A lane that is ten commits behind holds main's
  *old* `SCHEMA_VERSION` without ever having touched `db.py`. That is not a
  claim and is never reported as one; provenance, not value, decides.
- **It cannot see an unsaved editor buffer**, a `.gitignore`d file, a decision
  that exists only in another session's context, or anything on a remote -- no
  fetch is performed, so `origin/main` is whatever the last fetch left.
- **It cannot say which lane is right.** An overlap is a fact; who yields is a
  judgement.
- **A clean board is not a merged board.** Two lanes changing disjoint files can
  still produce a semantically broken tree. That is what the suite is for.

Unreadable resolves to None, never to zero
------------------------------------------
Per CLAUDE.md, a tree that cannot be read is reported `UNREADABLE` with its
reason, is counted separately in the verdict, and exits 3. It is **never**
reported as clean. Silently mistaking "I could not look" for "there is nothing
there" is the one way an instrument like this lies, and it lies in the
flattering direction. The same rule covers a binary or undecodable file, whose
changed-line count is `None` and prints as `?`.

Two structural properties, not conventions
------------------------------------------
**Every git call goes through `git()`, which prepends `--no-optional-locks`.**
A bare `git status` refreshes the index and therefore takes `index.lock` in a
worktree another live session is editing this second. No caller can forget the
flag because no caller passes it.

**No application code is imported.** This is stdlib-only and never imports
`backend`, because the instrument that reports on a broken lane must not die
when a lane breaks an import.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Kept byte-identical to `tests/test_parallel_lanes_do_not_collide.py`, and
#: `tests/test_lane_board.py` asserts that they still are. Two parsers that
#: disagreed about what an ADR claims would let this board call a tree clean
#: that the guard then fails on at merge -- the exact confusion it exists to
#: remove. The `0006` companion exemption is load-bearing and lives in both.
_DECLARES_ADR = re.compile(r"^#\s+(?:ADR\s+)?(\d{4})\s+[—-]")
_DECLARES_COMPANION = re.compile(r"^#\s+\w+\s+for\s+ADR\s+(\d{4})\b", re.I)

#: An ADR written under a slug with no ordinal, per the merge-time allocation
#: rule in `docs/adr/README.md`. Legal in a lane, illegal on the integration
#: branch -- which is what makes the numbering unavoidable at the boundary.
_IS_DRAFT = re.compile(r"^DRAFT-[A-Za-z0-9][A-Za-z0-9._-]*\.md$")

#: Anchored, because the comment block above the assignment in `db.py`
#: discusses v23 and v24 in prose and an unanchored search finds those first.
_SCHEMA_VERSION = re.compile(r"^SCHEMA_VERSION\s*=\s*(\d+)", re.M)

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+")

_ADR_DIR = "docs/adr"
_DB_PATH = "backend/store/db.py"

#: Lines of slack when deciding whether two hunks touch. git's own merge
#: refuses to auto-resolve changes closer than its context, so comparing bare
#: ranges would call an adjacent pair independent when git will not.
_HUNK_SLACK = 3

_TIMEOUT = 45.0


@dataclass
class GitResult:
    ok: bool
    stdout: str
    stderr: str
    #: None on timeout or a missing binary -- never 0, which would read as
    #: "ran and succeeded".
    returncode: int | None


def git(args: list[str], *, cwd: Path, timeout: float = _TIMEOUT) -> GitResult:
    """One git invocation. The only place `--no-optional-locks` is applied."""
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return GitResult(False, "", f"timed out after {timeout}s", None)
    except OSError as exc:
        return GitResult(False, "", str(exc), None)
    return GitResult(done.returncode == 0, done.stdout, done.stderr, done.returncode)


def _out(args: list[str], *, cwd: Path) -> str | None:
    result = git(args, cwd=cwd)
    return result.stdout if result.ok else None


@dataclass
class Claim:
    number: str
    path: str
    #: "committed" | "working-tree"
    origin: str
    #: "adr" | "companion". A companion document deliberately shares its
    #: parent's number -- `0006-in-play-evidence.md` sits beside
    #: `0006-in-play-scope.md` and says so in its own first line -- so it is
    #: excluded from collision grouping. Without this the board's very first
    #: finding on the real repo is a false one, which
    #: `tests/test_parallel_lanes_do_not_collide.py:57-66` says is how a guard
    #: gets deleted.
    kind: str


@dataclass
class DirtyFile:
    path: str
    status: str
    #: None for binary or undecodable content. Never 0.
    lines: int | None


@dataclass
class Lane:
    label: str
    #: "worktree" | "branch" | "unregistered-dir"
    kind: str
    path: Path | None = None
    branch: str | None = None
    sha: str | None = None
    ahead: int | None = None
    behind: int | None = None
    upstream_ahead: int | None = None
    upstream_behind: int | None = None
    dirty: list[DirtyFile] = field(default_factory=list)
    adr_claims: list[Claim] = field(default_factory=list)
    drafts: list[str] = field(default_factory=list)
    schema_version: int | None = None
    #: False when the value is merely inherited from an older main.
    schema_is_claimed: bool = False
    merge_base: str | None = None
    changed_since_base: frozenset[str] = frozenset()
    unreadable: str | None = None
    is_main: bool = False

    @property
    def ref(self) -> str | None:
        return self.branch or self.sha


@dataclass
class Finding:
    #: "COLLISION" | "OVERLAP" | "UNREADABLE"
    severity: str
    #: "adr" | "schema" | "hunk" | "file" | "lane"
    kind: str
    subject: str
    detail: str


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------


def repo_root(start: Path) -> Path | None:
    out = _out(["rev-parse", "--show-toplevel"], cwd=start)
    return Path(out.strip()) if out and out.strip() else None


def list_worktrees(root: Path) -> tuple[list[dict[str, str]], str | None]:
    out = _out(["worktree", "list", "--porcelain"], cwd=root)
    if out is None:
        return [], "`git worktree list` failed -- is this a git repository?"
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    if current:
        entries.append(current)
    return entries, None


def derive_lane_roots(
    entries: list[dict[str, str]], root: Path, override: Path | None
) -> list[Path]:
    """Directories that hold lane worktrees.

    Derived from git's own answer, never from a hardcoded home directory. This
    goes empty the moment the last lane merges, which is why `--lane-root`
    exists and why `tasks/LANES.md` records the path in prose.
    """
    roots: list[Path] = []
    for entry in entries:
        path = Path(entry["worktree"])
        if path.resolve() == root.resolve():
            continue
        parent = path.parent
        if parent not in roots:
            roots.append(parent)
    if override is not None and override not in roots:
        roots.append(override)
    return roots


def unregistered_dirs(lane_roots: list[Path], entries: list[dict[str, str]]) -> list[Path]:
    """Directories sitting in a lane root that git does not know about.

    `git worktree prune` does not remove these -- it only cleans `.git`'s
    administrative copies -- so a merged lane can leave a shell behind that
    looks like a lane and is not one.
    """
    known = {Path(e["worktree"]).resolve() for e in entries}
    found: list[Path] = []
    for lane_root in lane_roots:
        try:
            children = sorted(p for p in lane_root.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            if child.resolve() not in known:
                found.append(child)
    return found


def local_branches(root: Path) -> tuple[list[tuple[str, str]], str | None]:
    out = _out(
        ["for-each-ref", "--format=%(refname:short)%09%(objectname:short)", "refs/heads"],
        cwd=root,
    )
    if out is None:
        return [], "`git for-each-ref` failed; branches without a worktree unread"
    pairs = []
    for line in out.splitlines():
        name, _, sha = line.partition("\t")
        if name:
            pairs.append((name, sha))
    return pairs, None


# --------------------------------------------------------------------------
# per-tree reads
# --------------------------------------------------------------------------


def ahead_behind(root: Path, base: str, rev: str) -> tuple[int | None, int | None]:
    """Returns (ahead of base, behind base), or (None, None) if unreadable."""
    out = _out(["rev-list", "--left-right", "--count", f"{base}...{rev}"], cwd=root)
    if out is None:
        return None, None
    left, _, right = out.strip().partition("\t")
    try:
        return int(right), int(left)
    except ValueError:
        return None, None


def merge_base(root: Path, base: str, rev: str) -> str | None:
    out = _out(["merge-base", base, rev], cwd=root)
    return out.strip() if out and out.strip() else None


def dirty_files(worktree: Path) -> tuple[list[DirtyFile], str | None]:
    """Uncommitted work: tracked modifications and untracked files alike.

    `-z -uall` because the default porcelain quotes non-ASCII paths with octal
    escapes, and because a rename emits two NUL-separated paths for one status
    pair.
    """
    result = git(["status", "--porcelain=v1", "-z", "-uall"], cwd=worktree)
    if not result.ok:
        return [], f"git status failed: {result.stderr.strip() or result.returncode}"

    fields = result.stdout.split("\0")
    statuses: dict[str, str] = {}
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        code, name = entry[:2], entry[3:]
        if code[0] in "RC":
            # `-z` puts the source path in the following field; the entry's own
            # path is the destination, which is the one that changed.
            index += 1
        statuses[name] = code

    counts: dict[str, int | None] = {name: None for name in statuses}
    numstat = git(["diff", "HEAD", "--numstat", "-z"], cwd=worktree)
    if not numstat.ok:
        return [], f"git diff HEAD failed: {numstat.stderr.strip() or numstat.returncode}"
    for line in numstat.stdout.replace("\0", "\n").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, removed, name = parts[0], parts[1], parts[2]
        if name not in counts:
            continue
        if added == "-" or removed == "-":
            counts[name] = None  # binary: unreadable, not zero
        else:
            try:
                counts[name] = int(added) + int(removed)
            except ValueError:
                counts[name] = None

    for name, code in statuses.items():
        if code != "??":
            continue
        try:
            body = (worktree / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            counts[name] = None
            continue
        counts[name] = len(body.splitlines())

    return (
        [DirtyFile(name, statuses[name], counts[name]) for name in sorted(statuses)],
        None,
    )


def _adr_h1s(root: Path, lane: Lane) -> dict[str, str] | None:
    """path -> first line, for every ADR this tree currently holds.

    One `git grep` rather than seventy-nine `git show`s. The pattern is a bare
    `^#` and the real parsing happens in Python, so no non-ASCII pattern has to
    survive the command line on Windows.
    """
    if lane.path is not None:
        result = git(["grep", "--untracked", "-n", "-E", "^#", "--", _ADR_DIR], cwd=lane.path)
        prefix_fields = 0
    elif lane.ref is not None:
        result = git(["grep", "-n", "-E", "^#", lane.ref, "--", _ADR_DIR], cwd=root)
        prefix_fields = 1
    else:
        return None
    # `git grep` exits 1 when nothing matches, which is not an error here.
    if not result.ok and result.returncode != 1:
        return None

    h1s: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split(":", 2 + prefix_fields)
        if len(parts) < 3 + prefix_fields:
            continue
        path = parts[prefix_fields]
        lineno = parts[prefix_fields + 1]
        text = parts[prefix_fields + 2]
        if lineno != "1":
            continue
        h1s[path] = text.strip()
    return h1s


def _claim_of(first: str) -> tuple[str, str] | None:
    """(number, kind) for a first line, or None if it declares nothing."""
    match = _DECLARES_ADR.match(first)
    if match:
        return match.group(1), "adr"
    match = _DECLARES_COMPANION.match(first)
    if match:
        return match.group(1), "companion"
    return None


def _adr_files(root: Path, lane: Lane) -> list[str]:
    if lane.path is not None:
        out = _out(
            ["ls-files", "--cached", "--others", "--exclude-standard", "--", _ADR_DIR],
            cwd=lane.path,
        )
    elif lane.ref is not None:
        out = _out(["ls-tree", "-r", "--name-only", lane.ref, "--", _ADR_DIR], cwd=root)
    else:
        return []
    return sorted(out.split()) if out else []


def schema_version(root: Path, lane: Lane) -> int | None:
    if lane.path is not None:
        try:
            text = (lane.path / _DB_PATH).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    elif lane.ref is not None:
        text = _out(["show", f"{lane.ref}:{_DB_PATH}"], cwd=root)
        if text is None:
            return None
    else:
        return None
    match = _SCHEMA_VERSION.search(text)
    return int(match.group(1)) if match else None


# --------------------------------------------------------------------------
# hunk-level comparison
# --------------------------------------------------------------------------


def _base_ranges(args: list[str], *, cwd: Path) -> list[tuple[int, int]] | None:
    """Changed line ranges expressed in the MERGE-BASE's coordinates.

    Both sides of a comparison are diffed *from the same base*, so the `-`
    side of each hunk header is a common coordinate system and the ranges are
    directly comparable. A pure insertion prints `-N,0` and becomes the
    zero-width point N.
    """
    out = _out(args, cwd=cwd)
    if out is None:
        return None
    ranges: list[tuple[int, int]] = []
    for line in out.splitlines():
        match = _HUNK.match(line)
        if not match:
            continue
        start = int(match.group(1))
        count = 1 if match.group(2) is None else int(match.group(2))
        ranges.append((start, start) if count == 0 else (start, start + count - 1))
    return ranges


def _ranges_touch(
    left: list[tuple[int, int]], right: list[tuple[int, int]], slack: int = _HUNK_SLACK
) -> bool:
    for a_start, a_end in left:
        for b_start, b_end in right:
            if a_start - slack <= b_end and b_start - slack <= a_end:
                return True
    return False


def hunks_collide(
    root: Path, lane: Lane, main_ref: str, path: str
) -> bool | None:
    """Do this lane and main change overlapping regions of one file?

    None means it could not be established, which is not False.
    """
    if lane.merge_base is None:
        return None
    if lane.path is not None:
        lane_ranges = _base_ranges(
            ["diff", "-U0", lane.merge_base, "--", path], cwd=lane.path
        )
    elif lane.ref is not None:
        lane_ranges = _base_ranges(
            ["diff", "-U0", lane.merge_base, lane.ref, "--", path], cwd=root
        )
    else:
        return None
    main_ranges = _base_ranges(
        ["diff", "-U0", lane.merge_base, main_ref, "--", path], cwd=root
    )
    if lane_ranges is None or main_ranges is None:
        return None
    return _ranges_touch(lane_ranges, main_ranges)


# --------------------------------------------------------------------------
# collection
# --------------------------------------------------------------------------


def collect(
    root: Path, *, main_ref: str = "main", lane_root: Path | None = None
) -> tuple[list[Lane], list[str]]:
    notes: list[str] = []
    entries, error = list_worktrees(root)
    if error:
        return [], [error]

    lanes: list[Lane] = []
    branched: set[str] = set()
    for entry in entries:
        branch = entry["branch"].rsplit("/", 1)[-1] if "branch" in entry else None
        if branch:
            branched.add(branch)
        path = Path(entry["worktree"])
        lane = Lane(
            label=path.name,
            kind="worktree",
            path=path,
            branch=branch,
            sha=(entry.get("HEAD") or "")[:7] or None,
            is_main=(branch == main_ref),
        )
        if not path.is_dir():
            lane.unreadable = f"worktree path is registered but absent: {path}"
        lanes.append(lane)

    branches, branch_error = local_branches(root)
    if branch_error:
        notes.append(branch_error)
    for name, sha in branches:
        if name in branched:
            continue
        lanes.append(
            Lane(
                label=name,
                kind="branch",
                branch=name,
                sha=sha,
                is_main=(name == main_ref),
            )
        )

    lane_roots = derive_lane_roots(entries, root, lane_root)
    for stale in unregistered_dirs(lane_roots, entries):
        lanes.append(
            Lane(
                label=stale.name,
                kind="unregistered-dir",
                path=stale,
                unreadable=(
                    f"present on disk at {stale}, absent from `git worktree list`. "
                    f"`git worktree prune` will not remove it; a human deletes it."
                ),
            )
        )
    if not lane_roots:
        notes.append(
            "no lane root could be derived (no lane worktree is registered); "
            "pass --lane-root to check for leftover directories"
        )

    main_lane = next((lane for lane in lanes if lane.is_main), None)
    if main_lane is None:
        return lanes, notes + [f"no worktree or branch named `{main_ref}`"]

    main_h1s = _adr_h1s(root, main_lane) or {}
    main_claims: dict[str, str] = {}
    for path, text in main_h1s.items():
        parsed = _claim_of(text)
        if parsed is not None:
            main_claims[f"{parsed[0]}:{path}"] = path

    for lane in lanes:
        if lane.unreadable:
            continue
        _fill(root, lane, main_ref, main_claims, notes)
    return lanes, notes


def _fill(
    root: Path,
    lane: Lane,
    main_ref: str,
    main_claims: dict[str, str],
    notes: list[str],
) -> None:
    if lane.path is not None:
        files, error = dirty_files(lane.path)
        if error:
            lane.unreadable = error
            return
        lane.dirty = files

    changed: set[str] = {f.path for f in lane.dirty}

    if lane.is_main:
        lane.upstream_ahead, lane.upstream_behind = ahead_behind(
            root, f"origin/{main_ref}", main_ref
        )
    elif lane.ref is not None:
        lane.ahead, lane.behind = ahead_behind(root, main_ref, lane.ref)
        lane.merge_base = merge_base(root, main_ref, lane.ref)
        if lane.merge_base is None:
            lane.unreadable = "no merge-base with the integration branch"
            return
        committed = _out(
            ["diff", "--name-only", lane.merge_base, lane.ref], cwd=root
        )
        if committed is None:
            lane.unreadable = "could not diff against the merge-base"
            return
        changed |= set(committed.split())
    lane.changed_since_base = frozenset(changed)

    h1s = _adr_h1s(root, lane)
    if h1s is None:
        notes.append(f"{lane.label}: ADR headings unreadable")
    else:
        for path, text in sorted(h1s.items()):
            parsed = _claim_of(text)
            if parsed is None:
                continue
            number, kind = parsed
            if not lane.is_main and main_claims.get(f"{number}:{path}") == path:
                continue  # byte-for-byte main's own claim, inherited, not this lane's
            lane.adr_claims.append(
                Claim(
                    number=number,
                    path=path,
                    origin="working-tree" if path in changed else "committed",
                    kind=kind,
                )
            )
    lane.drafts = [
        path for path in _adr_files(root, lane) if _IS_DRAFT.match(path.rsplit("/", 1)[-1])
    ]

    lane.schema_version = schema_version(root, lane)
    if lane.schema_version is None:
        notes.append(f"{lane.label}: SCHEMA_VERSION unreadable")
    lane.schema_is_claimed = lane.is_main or _DB_PATH in changed


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------


def find_adr_collisions(lanes: list[Lane]) -> list[Finding]:
    by_number: dict[str, list[str]] = {}
    for lane in lanes:
        if lane.unreadable:
            continue
        for claim in lane.adr_claims:
            if claim.kind == "companion":
                continue  # shares its parent's number on purpose
            by_number.setdefault(claim.number, []).append(f"{lane.label}:{claim.path}")
    return [
        Finding(
            "COLLISION",
            "adr",
            f"ADR {number}",
            f"claimed by {', '.join(sorted(where))}",
        )
        for number, where in sorted(by_number.items())
        if len(where) > 1
    ]


def find_schema_collisions(lanes: list[Lane]) -> list[Finding]:
    """Only *claimed* versions collide. An inherited value is not a claim."""
    claimed = [
        lane
        for lane in lanes
        if not lane.unreadable and lane.schema_is_claimed and lane.schema_version is not None
    ]
    by_version: dict[int, list[str]] = {}
    for lane in claimed:
        by_version.setdefault(lane.schema_version, []).append(lane.label)
    return [
        Finding(
            "COLLISION",
            "schema",
            f"schema v{version}",
            f"claimed by {', '.join(sorted(where))}",
        )
        for version, where in sorted(by_version.items())
        if len(where) > 1
    ]


def find_overlap(root: Path, lanes: list[Lane], main_ref: str) -> list[Finding]:
    findings: list[Finding] = []
    main_lane = next((lane for lane in lanes if lane.is_main), None)
    if main_lane is None:
        return findings
    workers = [
        lane
        for lane in lanes
        if not lane.is_main and not lane.unreadable and lane.merge_base is not None
    ]

    for lane in workers:
        moved = _out(["diff", "--name-only", lane.merge_base, main_ref], cwd=root)
        if moved is None:
            lane.unreadable = "could not read what main changed since the merge-base"
            continue
        for path in sorted(lane.changed_since_base & set(moved.split())):
            collides = hunks_collide(root, lane, main_ref, path)
            if collides is None:
                findings.append(
                    Finding(
                        "UNREADABLE",
                        "hunk",
                        path,
                        f"{lane.label} vs {main_ref}: hunks could not be compared",
                    )
                )
            elif collides:
                findings.append(
                    Finding(
                        "COLLISION",
                        "hunk",
                        path,
                        f"{lane.label} vs {main_ref}: overlapping hunks -- git will conflict",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "OVERLAP",
                        "file",
                        path,
                        f"{lane.label} vs {main_ref}: both moved, disjoint hunks -- merges clean",
                    )
                )

    for index, first in enumerate(workers):
        for second in workers[index + 1 :]:
            for path in sorted(first.changed_since_base & second.changed_since_base):
                findings.append(
                    Finding(
                        "OVERLAP",
                        "file",
                        path,
                        f"{first.label} vs {second.label}: both are changing this file",
                    )
                )
    return findings


def analyse(root: Path, lanes: list[Lane], main_ref: str = "main") -> list[Finding]:
    findings = find_overlap(root, lanes, main_ref)
    findings += find_adr_collisions(lanes)
    findings += find_schema_collisions(lanes)
    findings += [
        Finding("UNREADABLE", "lane", lane.label, lane.unreadable)
        for lane in lanes
        if lane.unreadable
    ]
    order = {"COLLISION": 0, "UNREADABLE": 1, "OVERLAP": 2}
    return sorted(findings, key=lambda f: (order[f.severity], f.kind, f.subject))


def verdict(findings: list[Finding], lanes: list[Lane], *, strict_overlap: bool) -> tuple[str, int]:
    collisions = [f for f in findings if f.severity == "COLLISION"]
    unreadable = [f for f in findings if f.severity == "UNREADABLE"]
    overlaps = [f for f in findings if f.severity == "OVERLAP"]
    compared = [
        lane
        for lane in lanes
        if not lane.is_main and not lane.unreadable and lane.kind != "unregistered-dir"
    ]

    line = (
        f"COLLISIONS {len(collisions)}   OVERLAPS {len(overlaps)}   "
        f"UNREADABLE {len(unreadable)}   LANES COMPARED {len(compared)}"
    )
    if collisions:
        return line + "   ->  exit 1 (COLLISION)", 1
    if strict_overlap and overlaps:
        return line + "   ->  exit 1 (OVERLAP, --strict-overlap)", 1
    if unreadable:
        return line + "   ->  exit 3 (UNREADABLE: this is not a clean bill)", 3
    if not compared:
        return line + "   ->  exit 0 (NO LANES: nothing was compared)", 0
    return line + "   ->  exit 0 (OK)", 0


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def _lines(count: int | None) -> str:
    return "?" if count is None else str(count)


def render(
    root: Path,
    lanes: list[Lane],
    findings: list[Finding],
    notes: list[str],
    stamp: str,
    verdict_line: str,
    lane_roots: list[Path],
    *,
    main_label: str = "main",
    max_files: int = 12,
) -> str:
    out: list[str] = []
    add = out.append

    add(f"# lane board -- {stamp}")
    add(f"# repo       {root.as_posix()}")
    add(f"# lane root  {', '.join(p.as_posix() for p in lane_roots) or 'NONE DERIVABLE'}")
    add("# Generated by `scripts/lane_board.py`. Do not hand-edit; regenerate.")
    add("# A snapshot, not a lock. It reserves nothing and does not fix the")
    add("# ordinal counters -- see the script docstring and tasks/lessons.md:168-191.")
    add("")

    add("LANES")
    add("-----")
    for lane in lanes:
        sha = lane.sha or "???????"
        if lane.kind == "unregistered-dir":
            add(f"{lane.label:<24}  UNREGISTERED DIRECTORY")
            add(f"{'':<24}      {lane.unreadable}")
            add("")
            continue
        where = lane.branch or "detached"
        add(f"{lane.label:<24}  {sha}  {where}  ({lane.kind})")
        if lane.unreadable:
            add(f"{'':<24}      UNREADABLE -- {lane.unreadable}")
            add("")
            continue
        if lane.path is not None:
            add(f"{'':<24}      path      {lane.path.as_posix()}")
        if lane.is_main:
            ahead = "?" if lane.upstream_ahead is None else lane.upstream_ahead
            behind = "?" if lane.upstream_behind is None else lane.upstream_behind
            add(f"{'':<24}      vs origin {ahead} unpushed, {behind} unpulled")
        else:
            ahead = "?" if lane.ahead is None else lane.ahead
            behind = "?" if lane.behind is None else lane.behind
            base = (lane.merge_base or "???????")[:7]
            add(f"{'':<24}      vs main   {ahead} ahead, {behind} behind   merge-base {base}")
        if lane.dirty:
            total = sum(f.lines for f in lane.dirty if f.lines is not None)
            unknown = sum(1 for f in lane.dirty if f.lines is None)
            tail = f", {unknown} unreadable" if unknown else ""
            add(f"{'':<24}      dirty     {len(lane.dirty)} files, {total} lines{tail}")
            shown = sorted(lane.dirty, key=lambda f: -(f.lines or 0))[:max_files]
            for entry in shown:
                add(f"{'':<24}        {entry.status}  {_lines(entry.lines):>6}  {entry.path}")
            if len(lane.dirty) > max_files:
                add(
                    f"{'':<24}        ... and {len(lane.dirty) - max_files} more "
                    f"(--max-files 0 shows all)"
                )
        else:
            add(f"{'':<24}      dirty     clean")
        if lane.is_main:
            numbers = sorted(c.number for c in lane.adr_claims if c.kind == "adr")
            highest = numbers[-1] if numbers else "none"
            add(
                f"{'':<24}      adr       baseline: {len(numbers)} numbers on "
                f"{main_label}, highest {highest}"
            )
        elif lane.adr_claims:
            for claim in lane.adr_claims:
                add(
                    f"{'':<24}      adr       {claim.number}  {claim.path}  "
                    f"({claim.origin}, {claim.kind})"
                )
        else:
            add(f"{'':<24}      adr       no unmerged claim")
        if lane.drafts:
            add(f"{'':<24}      drafts    {', '.join(lane.drafts)}  (need a number at merge)")
        version = "?" if lane.schema_version is None else lane.schema_version
        if lane.schema_is_claimed:
            add(f"{'':<24}      schema    v{version}  CLAIMED")
        else:
            add(
                f"{'':<24}      schema    v{version}  INHERITED -- {_DB_PATH} untouched "
                f"since the merge-base, so this is not a claim"
            )
        add("")

    add("FINDINGS")
    add("--------")
    if not findings:
        add("none -- no two trees are changing overlapping regions, and nothing is")
        add("claimed twice. This is not a promise that a merge will be semantically")
        add("correct; that is what the suite is for.")
    for finding in findings:
        add(f"{finding.severity:<10} {finding.kind:<6} {finding.subject}")
        add(f"{'':<10} {'':<6} {finding.detail}")
    add("")

    for note in notes:
        add(f"NOTE  {note}")
    if notes:
        add("")

    add(f"VERDICT  {verdict_line}")
    return "\n".join(out) + "\n"


#: Everything above this line in `tasks/LANES.md` is written by a person and
#: survives a regenerate; everything below it is replaced wholesale. The split
#: exists because the two halves rot differently: a pasted snapshot can only be
#: *old*, and a reader tells at a glance by comparing its sha to `main`, while a
#: hand-typed "3 behind" is simply *wrong* within the hour -- which is exactly
#: what happened to the lane table in `tasks/NEXT.md`.
_BOARD_MARKER = "<!-- BOARD BELOW -- regenerated by scripts/lane_board.py; do not hand-edit -->"

_DEFAULT_HEADER = """\
# Lanes

**Nothing below the marker is authoritative, and none of it is hand-written.**
Regenerate it:

    .venv\\Scripts\\python.exe scripts/lane_board.py --write

Run that before you claim an ADR number or a schema version, and again before
you push. It is a snapshot, not a lock -- see the script's docstring and
`docs/adr/README.md`.

## Slow facts

- Lane worktrees are **Herdr's**, not any session's. Nothing in this repo starts
  or stops one; `git worktree list` is the only truth about which exist.
- `tasks/LANES.md` is **integrator-only**, in the spirit of ADR 0003 §2. A lane
  regenerating it recreates the append-conflict that section exists to prevent.
- On 2026-08-27 two lanes collided three times in one day, on ADR ordinals and
  on `SCHEMA_VERSION`. Two of the three merged **cleanly**, because two lanes
  writing `0077-a.md` and `0077-b.md` have no line to conflict on. Guard:
  `tests/test_parallel_lanes_do_not_collide.py`. Rule: `docs/adr/README.md`.

## Allocation ledger

The only part a measurement cannot produce, because it is a claim about the
*future*: what a live lane has said it will take, before it exists on disk.
Add a row when you claim; close it with the merge sha when it lands.

| lane | claims | stated | closed by |
|---|---|---|---|
| `parlay-props` | an ADR number, at merge | 2026-08-27, as `DRAFT-alternate-prop-keys-are-not-bought.md` | _open_ |

"""


def _merge_board(path: Path, board: str) -> str:
    """Replace the generated half of `LANES.md`; keep the hand-written half."""
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        existing = ""
    header = (
        existing.split(_BOARD_MARKER)[0] if _BOARD_MARKER in existing else _DEFAULT_HEADER
    )
    return f"{header}{_BOARD_MARKER}\n\n```\n{board}```\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-worktree collision detector for parallel lanes (read-only).",
        epilog=(
            "exit 0 OK; 1 a number/version claimed twice or overlapping hunks; "
            "2 usage or repository error; 3 a tree could not be read, which is "
            "never the same as clean."
        ),
    )
    parser.add_argument("--repo", default=None, help="repository to read (default: this file's)")
    parser.add_argument("--main", default="main", help="integration branch (default: main)")
    parser.add_argument(
        "--lane-root",
        default=None,
        help="extra directory to scan for leftover lane directories",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="also write the board to tasks/LANES.md in the integration worktree",
    )
    parser.add_argument(
        "--strict-overlap",
        action="store_true",
        help="treat a same-file, disjoint-hunk overlap as a failure too",
    )
    parser.add_argument(
        "--max-files", type=int, default=12, help="dirty files listed per lane; 0 for all"
    )
    parser.add_argument("--stamp", default=None, help="timestamp to print (default: now, UTC)")
    args = parser.parse_args(argv)

    start = Path(args.repo) if args.repo else Path(__file__).resolve().parents[1]
    root = repo_root(start)
    if root is None:
        print(f"NOTE  not a git repository: {start}", file=sys.stderr)
        return 2

    if args.stamp is not None:
        stamp = args.stamp
    else:
        from datetime import datetime, timezone

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lane_root = Path(args.lane_root) if args.lane_root else None
    lanes, notes = collect(root, main_ref=args.main, lane_root=lane_root)
    if not lanes:
        for note in notes:
            print(f"NOTE  {note}", file=sys.stderr)
        return 2

    findings = analyse(root, lanes, args.main)
    verdict_line, code = verdict(findings, lanes, strict_overlap=args.strict_overlap)
    entries, _ = list_worktrees(root)
    board = render(
        root,
        lanes,
        findings,
        notes,
        stamp,
        verdict_line,
        derive_lane_roots(entries, root, lane_root),
        main_label=args.main,
        max_files=args.max_files if args.max_files > 0 else 10**9,
    )
    print(board, end="")

    if args.write:
        target = next(
            (lane.path for lane in lanes if lane.is_main and lane.path is not None), root
        )
        board_path = target / "tasks" / "LANES.md"
        board_path.write_text(_merge_board(board_path, board), encoding="utf-8")
        print(f"\nwrote {(target / 'tasks' / 'LANES.md').as_posix()}")
    return code


if __name__ == "__main__":
    sys.exit(main())
