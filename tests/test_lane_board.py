"""`scripts/lane_board.py` must never call a tree clean that it could not read.

WHY THESE ARE BUILT ON REAL GIT REPOSITORIES
--------------------------------------------
Every fixture below runs `git init`, makes real commits and adds real
worktrees under `tmp_path`. Faking git's output would test the parser and not
the instrument, and the instrument's whole job is to be right about git.

**They must not depend on Joe's actual worktrees existing.** CI checks out one
tree with no lanes at all (`.github/workflows/ci.yml` runs `python -m pytest
-q`), so a test written against the live lanes would be permanently vacuous
there -- green, silent, and proving nothing. Only
`TestTheRealRepoIsStillReadable` touches the real repo, and it is a vacuity
guard rather than an assertion about any particular lane.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about whether a reported collision is worth acting on.** These
  assert that the board reports what git would do, not that a human should
  care.
- **Nothing about a live session.** The board reads the filesystem; a lane
  holding a change in an unsaved buffer is invisible to it and to these tests.
- **Nothing about timing.** The board is a snapshot, and no test here can show
  that two lanes did not collide in the gap between two runs.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lane_board  # noqa: E402
from tests import test_parallel_lanes_do_not_collide as guard  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# fixtures: real repositories, built from nothing
# --------------------------------------------------------------------------


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", message], repo)


def _adr(number: str, slug: str) -> str:
    return f"# {number} \u2014 {slug}\n\n**Status:** accepted\n"


def _db(version: int) -> str:
    return (
        "# The comment above the stamp discusses v22 and v23 in prose, which is\n"
        "# why the pattern is anchored.\n"
        f"SCHEMA_VERSION = {version}\n"
        "_MIGRATIONS = {}\n"
    )


def _base_repo(root: Path) -> Path:
    """A repo with `main`, a few ADRs including a companion, and a db.py."""
    # The integration checkout lives beside unrelated projects, and the lanes
    # live somewhere else entirely. That is the real layout -- main under
    # `Documents/Claude/Projects/`, lanes under `~/.herdr/worktrees/` -- and
    # getting it wrong in a fixture is what let the sibling-scan defect ship.
    repo = root / "projects" / "origin"
    repo.mkdir(parents=True)
    (root / "lanes").mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@example.invalid"], repo)
    _run(["git", "config", "user.name", "test"], repo)
    _write(repo / "docs/adr/0001-first.md", _adr("0001", "First"))
    _write(repo / "docs/adr/0002-second.md", _adr("0002", "Second"))
    _write(
        repo / "docs/adr/0002-second-evidence.md",
        "# Evidence for ADR 0002\n\nA companion, sharing 0002 on purpose.\n",
    )
    _write(repo / lane_board._DB_PATH, _db(10))
    _write(repo / "app.py", "\n".join(f"line {n}" for n in range(1, 201)) + "\n")
    _commit(repo, "base")
    return repo


def _lane_root(repo: Path) -> Path:
    return repo.parents[1] / "lanes"


def _add_lane(repo: Path, name: str) -> Path:
    path = _lane_root(repo) / name
    _run(["git", "worktree", "add", "-q", "-b", name, str(path), "main"], repo)
    _run(["git", "config", "user.email", "t@example.invalid"], path)
    _run(["git", "config", "user.name", "test"], path)
    return path


def _give_it_a_remote(repo: Path) -> Path:
    """A real bare remote, pushed to, so `origin/main` genuinely exists.

    Faking the remote would test the parser and not the instrument, and the
    whole defect this guards is that a LOCAL read looks identical to a pushed
    one from the integrator's seat.
    """
    remote = repo.parents[1] / "remote.git"
    _run(["git", "init", "-q", "--bare", str(remote)], repo)
    _run(["git", "remote", "add", "origin", str(remote)], repo)
    _run(["git", "push", "-q", "-u", "origin", "main"], repo)
    return remote


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _base_repo(tmp_path)


def board(repo: Path, **kwargs):
    lanes, notes = lane_board.collect(repo, main_ref="main", **kwargs)
    findings = lane_board.analyse(repo, lanes, "main")
    return lanes, findings, notes


def lane_named(lanes, name):
    return next(lane for lane in lanes if lane.label == name)


def findings_of(findings, severity=None, kind=None, subject=None):
    return [
        f
        for f in findings
        if (severity is None or f.severity == severity)
        and (kind is None or f.kind == kind)
        and (subject is None or f.subject == subject)
    ]


# --------------------------------------------------------------------------


class TestAnADRNumberIsClaimedOnce:
    def test_two_lanes_claiming_one_number_is_a_collision(self, repo: Path):
        """Mutation observed red: drop the cross-lane grouping in
        `find_adr_collisions`. Two lanes writing `0009-a.md` and `0009-b.md`
        are different filenames, so git merges them clean and reports nothing
        -- which is the failure this whole file descends from.
        """
        for name, slug in (("lane-a", "a"), ("lane-b", "b")):
            path = _add_lane(repo, name)
            _write(path / f"docs/adr/0009-{slug}.md", _adr("0009", slug))
            _commit(path, f"claim 0009 as {slug}")

        _, findings, _ = board(repo)
        hits = findings_of(findings, "COLLISION", "adr", "ADR 0009")
        assert len(hits) == 1
        assert "lane-a" in hits[0].detail and "lane-b" in hits[0].detail

    def test_a_number_already_on_main_is_a_collision(self, repo: Path):
        """Mutation observed red: skip the main baseline entirely. A lane
        re-using 0002 under a new filename reports clean."""
        path = _add_lane(repo, "lane-a")
        _write(path / "docs/adr/0002-different.md", _adr("0002", "Different"))
        _commit(path, "re-use 0002")

        _, findings, _ = board(repo)
        assert findings_of(findings, "COLLISION", "adr", "ADR 0002")

    def test_an_adr_inherited_from_main_is_not_a_claim(self, repo: Path):
        """**The false-finding guard.** Mutation observed red: remove the
        `number:path` subtraction against main's own claims -- every ADR the
        lane merely inherited is reported as a fresh claim, and on the real
        repo that is seventy-eight false findings on the first run.
        `tests/test_parallel_lanes_do_not_collide.py:57-66` records what
        happens to a guard whose first finding is false.
        """
        _add_lane(repo, "lane-a")
        lanes, findings, _ = board(repo)
        assert lane_named(lanes, "lane-a").adr_claims == []
        assert findings_of(findings, "COLLISION", "adr") == []

    def test_a_companion_document_is_not_a_second_claim(self, repo: Path):
        """Mutation observed red: treat `_DECLARES_COMPANION` matches as
        ordinary claims. `0002-second-evidence.md` and `0002-second.md` are
        then a collision on main against itself, which is a false finding on
        an intentional, pinned arrangement.
        """
        _add_lane(repo, "lane-a")
        _, findings, _ = board(repo)
        assert findings_of(findings, "COLLISION", "adr", "ADR 0002") == []

    def test_an_uncommitted_adr_is_still_a_claim(self, repo: Path):
        """Mutation observed red: drop `--untracked` from the worktree
        `git grep`. An ADR a lane has written but not committed becomes
        invisible -- and that is precisely the pre-merge moment this instrument
        exists for, since the guard already covers the post-merge one.
        """
        path = _add_lane(repo, "lane-a")
        _write(path / "docs/adr/0009-uncommitted.md", _adr("0009", "Uncommitted"))

        lanes, _, _ = board(repo)
        claims = lane_named(lanes, "lane-a").adr_claims
        assert [(c.number, c.origin) for c in claims] == [("0009", "working-tree")]

    def test_a_draft_carries_no_number_and_is_listed_for_the_integrator(self, repo: Path):
        """The merge-time allocation rule: a lane writes a slug with no
        ordinal, so there is nothing to collide on. Mutation observed red:
        make `_IS_DRAFT` match nothing -- the draft is silently not listed and
        the integrator has no idea a number is owed.
        """
        path = _add_lane(repo, "lane-a")
        _write(path / "docs/adr/DRAFT-a-thing.md", "# A thing\n\nNo ordinal yet.\n")

        lanes, findings, _ = board(repo)
        lane = lane_named(lanes, "lane-a")
        assert lane.drafts == ["docs/adr/DRAFT-a-thing.md"]
        assert lane.adr_claims == []
        assert findings_of(findings, "COLLISION", "adr") == []


class TestASchemaVersionIsClaimedNotInherited:
    def test_a_version_the_lane_did_not_touch_is_inherited(self, repo: Path):
        """**Trap 1, and the second false-finding guard.** A lane that is
        behind holds main's OLD stamp without ever having touched `db.py`.

        Mutation observed red: decide on the value (`lane.schema_version !=
        main.schema_version`) instead of on provenance. The real `parlay_props`
        lane -- ten commits behind, holding v23 against main's v24, `db.py`
        untouched -- is then reported as a schema collision on the board's
        first run.
        """
        _add_lane(repo, "lane-a")
        _write(repo / lane_board._DB_PATH, _db(11))
        _commit(repo, "main bumps to v11")

        lanes, findings, _ = board(repo)
        lane = lane_named(lanes, "lane-a")
        assert lane.schema_version == 10
        assert lane.schema_is_claimed is False
        assert findings_of(findings, "COLLISION", "schema") == []

    def test_two_lanes_claiming_one_version_is_a_collision(self, repo: Path):
        """Mutation observed red: group by version without filtering on
        `schema_is_claimed`, or drop the grouping. Both lanes bumping to v11
        edit the same line, so git conflicts loudly -- but a careless
        resolution is what `tests/test_parallel_lanes_do_not_collide.py`
        already says is the reachable failure, and this catches it earlier.
        """
        for name in ("lane-a", "lane-b"):
            path = _add_lane(repo, name)
            _write(path / lane_board._DB_PATH, _db(11))
            _commit(path, f"{name} claims v11")

        _, findings, _ = board(repo)
        hits = findings_of(findings, "COLLISION", "schema", "schema v11")
        assert len(hits) == 1
        assert "lane-a" in hits[0].detail and "lane-b" in hits[0].detail

    def test_a_lane_that_touched_db_is_reported_as_claiming(self, repo: Path):
        """The other half: provenance must actually fire when it should.
        Mutation observed red: hardcode `schema_is_claimed = False` -- the test
        above still passes and every real claim goes unreported."""
        path = _add_lane(repo, "lane-a")
        _write(path / lane_board._DB_PATH, _db(11))
        _commit(path, "lane-a claims v11")

        lanes, _, _ = board(repo)
        assert lane_named(lanes, "lane-a").schema_is_claimed is True


class TestOverlapIsSeparatedFromCollision:
    def _two_edits(self, repo: Path, lane_line: int, main_line: int) -> Path:
        path = _add_lane(repo, "lane-a")
        for target, line, marker in (
            (path, lane_line, "LANE"),
            (repo, main_line, "MAIN"),
        ):
            body = (target / "app.py").read_text(encoding="utf-8").splitlines()
            body[line - 1] = f"line {line} {marker}"
            _write(target / "app.py", "\n".join(body) + "\n")
        _commit(repo, "main edits app.py")
        return path

    def test_overlapping_hunks_in_one_file_are_a_collision(self, repo: Path):
        """Mutation observed red: return False from `hunks_collide` -- the one
        file git will genuinely stop on is reported as a clean merge."""
        self._two_edits(repo, lane_line=100, main_line=100)
        _, findings, _ = board(repo)
        assert findings_of(findings, "COLLISION", "hunk", "app.py")

    def test_a_hunk_collision_does_not_claim_the_merge_will_fail(self, repo: Path):
        """It says MAY conflict, because that is all it knows.

        On 2026-08-27 this board reported `backend/parlays.py` as overlapping
        and git auto-resolved it cleanly: main's added import and the lane's
        two lines sat inside one 3-line context window, and adjacency makes a
        conflict **possible, not certain**. Both the board's author and the
        lane predicted a conflict and both were wrong in the same direction --
        the lane found out by merging and checking the result by hand rather
        than trusting the clean exit.

        The wording is what a person acts on, so it is worth a test of its own.
        Mutation observed red: restore "git will conflict".
        """
        self._two_edits(repo, lane_line=100, main_line=100)
        _, findings, _ = board(repo)
        hit = findings_of(findings, "COLLISION", "hunk", "app.py")[0]
        assert "will conflict" not in hit.detail
        assert "MAY conflict" in hit.detail

    def test_distant_edits_to_one_file_are_an_overlap_not_a_collision(self, repo: Path):
        """**The false-finding guard for the file half.** Mutation observed
        red: compare at file level instead of hunk level.

        On the day this shipped, a file-level detector called
        `frontend/src/lib/api.ts` a collision when the lane's edit was at line
        685 and main's at 2467 -- 1,780 lines apart and semantically unrelated.
        That merge is clean, and a tool whose first output is a false alarm on
        a clean merge gets ignored.
        """
        self._two_edits(repo, lane_line=10, main_line=190)
        _, findings, _ = board(repo)
        assert findings_of(findings, "COLLISION", "hunk", "app.py") == []
        assert findings_of(findings, "OVERLAP", "file", "app.py")

    def test_an_overlap_alone_does_not_fail_the_default_exit_code(self, repo: Path):
        """Mutation observed red: promote OVERLAP to exit 1 by default. Every
        board with two lanes touching one file goes red, and per `ruff.toml`'s
        own comment in this repo, a guard that fails every time says exactly as
        much as one that never fails.
        """
        self._two_edits(repo, lane_line=10, main_line=190)
        lanes, findings, _ = board(repo)
        _, code = lane_board.verdict(findings, lanes, strict_overlap=False)
        assert code == 0
        _, strict = lane_board.verdict(findings, lanes, strict_overlap=True)
        assert strict == 1

    def test_uncommitted_work_is_compared_too(self, repo: Path):
        """The gap that actually existed. Mutation observed red: seed
        `changed_since_base` from committed diffs only -- a lane holding 712
        uncommitted lines reports as quiet, which is exactly the state the real
        `parlay-props` lane was in when this was written.
        """
        path = _add_lane(repo, "lane-a")
        body = (path / "app.py").read_text(encoding="utf-8").splitlines()
        body[99] = "line 100 LANE, uncommitted"
        _write(path / "app.py", "\n".join(body) + "\n")
        main_body = (repo / "app.py").read_text(encoding="utf-8").splitlines()
        main_body[99] = "line 100 MAIN"
        _write(repo / "app.py", "\n".join(main_body) + "\n")
        _commit(repo, "main edits app.py")

        _, findings, _ = board(repo)
        assert findings_of(findings, "COLLISION", "hunk", "app.py")


class TestUnreadableIsNeverClean:
    def test_a_missing_worktree_is_unreadable_not_clean(self, repo: Path):
        """**The load-bearing test.** Mutation observed red: make `git()`
        report ok on a non-zero exit, or let `dirty_files` return `([], None)`
        on failure. A worktree whose directory was deleted then renders as a
        lane with zero dirty files and the board exits 0 -- "I could not look"
        printed as "there is nothing there", in the flattering direction.
        """
        path = _add_lane(repo, "lane-a")
        for child in sorted(path.rglob("*"), reverse=True):
            child.unlink() if child.is_file() else child.rmdir()
        path.rmdir()

        lanes, findings, _ = board(repo)
        lane = lane_named(lanes, "lane-a")
        assert lane.unreadable is not None
        assert lane.dirty == []
        assert findings_of(findings, "UNREADABLE", "lane", "lane-a")
        _, code = lane_board.verdict(findings, lanes, strict_overlap=False)
        assert code == 3

    def test_a_worktree_whose_git_fails_is_unreadable_not_clean(self, repo: Path):
        """The directory EXISTS and git still cannot answer -- a corrupt `.git`
        pointer, a permissions problem, a half-removed worktree.

        This case is separate from the one above and was found by mutating:
        deleting the directory is caught earlier by the `is_dir()` check, so
        the test above passed for the wrong reason and left
        `dirty_files`' error return -- the actual load-bearing line -- with no
        coverage at all.

        Mutation observed red: `return [], None` instead of the error string in
        `dirty_files`. The lane then renders with zero dirty files, no
        `unreadable` reason, and the board exits 0 on a tree it never read.
        """
        path = _add_lane(repo, "lane-a")
        pointer = path / ".git"
        if pointer.is_dir():
            shutil.rmtree(pointer)
        else:
            pointer.unlink()
        pointer.write_text("gitdir: nowhere-at-all\n", encoding="utf-8")

        lanes, findings, _ = board(repo)
        lane = lane_named(lanes, "lane-a")
        assert lane.unreadable is not None
        assert lane.dirty == []
        assert findings_of(findings, "UNREADABLE", "lane", "lane-a")
        _, code = lane_board.verdict(findings, lanes, strict_overlap=False)
        assert code == 3

    def test_exit_is_three_when_unreadable_and_nothing_collides(self, repo: Path):
        """Mutation observed red: fold 3 into 0. The verdict then reads OK on a
        board that never saw one of its lanes."""
        _add_lane(repo, "lane-a")
        stale = _lane_root(repo) / "left-behind"
        (stale / "frontend").mkdir(parents=True)

        lanes, findings, _ = board(repo)
        line, code = lane_board.verdict(findings, lanes, strict_overlap=False)
        assert code == 3
        assert "UNREADABLE 1" in line

    def test_a_leftover_directory_is_reported_as_unregistered(self, repo: Path):
        """Mutation observed red: drop the disk scan in `unregistered_dirs`.
        The real `hedging-research` shell -- two empty directories that
        `git worktree prune` will not remove and `git -C` calls "not a git
        repository" -- disappears from the report entirely.
        """
        _add_lane(repo, "lane-a")
        stale = _lane_root(repo) / "left-behind"
        (stale / "frontend").mkdir(parents=True)

        lanes, _, _ = board(repo)
        lane = lane_named(lanes, "left-behind")
        assert lane.kind == "unregistered-dir"
        assert "absent from `git worktree list`" in lane.unreadable

    def test_a_sibling_of_the_integration_checkout_is_never_a_lane_candidate(
        self, repo: Path
    ):
        """**The destructive false positive, pinned.** Reported by the
        `parlay-props` lane before anyone acted on it.

        Run from a LANE, the integration checkout looks like just another
        worktree, so its parent -- a general projects folder -- was treated as
        a lane root. Sixteen of Joe's unrelated repositories were reported with
        the words "a human deletes it", one of them the predecessor project
        `CLAUDE.md` tells every session to read.

        Mutation observed red **only with both checks in `derive_lane_roots`
        removed together**, and that is worth saying rather than hiding: the
        two are redundant, either alone suppresses the defect, so mutating one
        is masked by the other. Removing both reproduces exactly what shipped
        -- the neighbour below reported as a leftover lane shell.
        """
        lane = _add_lane(repo, "lane-a")
        neighbour = repo.parent / "someones-other-project"
        neighbour.mkdir(parents=True)

        # Read the world the way the lane sees it -- which is where it broke.
        lanes, _ = lane_board.collect(lane, main_ref="main")
        labels = {entry.label for entry in lanes}
        assert "someones-other-project" not in labels

    def test_a_directory_with_its_own_git_is_never_reported(self, repo: Path):
        """The second half of the gate. A leftover lane shell has no `.git` --
        git removed the pointer and left the directories -- while somebody
        else's checkout always has one.

        Mutation observed red: drop the `_is_its_own_repository` check. An
        unrelated repository sitting in the lane root is reported as a shell to
        delete.
        """
        _add_lane(repo, "lane-a")
        stranger = _lane_root(repo) / "not-a-lane"
        stranger.mkdir(parents=True)
        _run(["git", "init", "-q"], stranger)

        lanes, _, _ = board(repo)
        assert "not-a-lane" not in {entry.label for entry in lanes}

    def test_the_finding_does_not_instruct_a_human_to_delete(self, repo: Path):
        """It is an observation, not an order. The first wording said "a human
        deletes it", and a false positive phrased as an instruction is how a
        reporting tool causes the harm it was built to prevent.

        Mutation observed red: restore that phrasing.
        """
        _add_lane(repo, "lane-a")
        stale = _lane_root(repo) / "left-behind"
        (stale / "frontend").mkdir(parents=True)

        lanes, _, _ = board(repo)
        reason = lane_named(lanes, "left-behind").unreadable
        assert "a human deletes it" not in reason
        assert "check before removing it" in reason

    def test_a_binary_change_reports_none_lines_not_zero(self, repo: Path):
        """Mutation observed red: map numstat's `-` to 0. A binary change then
        reads as a zero-line change, which is the same lie one layer down."""
        path = _add_lane(repo, "lane-a")
        (path / "blob.bin").write_bytes(bytes(range(256)) * 4)
        _commit(path, "add a binary")
        (path / "blob.bin").write_bytes(bytes(reversed(range(256))) * 4)

        lanes, _, _ = board(repo)
        entry = next(f for f in lane_named(lanes, "lane-a").dirty if f.path == "blob.bin")
        assert entry.lines is None

    def test_an_undecodable_untracked_file_reports_none(self, repo: Path):
        """Mutation observed red: swallow the decode error and return 0."""
        path = _add_lane(repo, "lane-a")
        (path / "junk.txt").write_bytes(b"\xff\xfe\x00\x01binary-ish")

        lanes, _, _ = board(repo)
        entry = next(f for f in lane_named(lanes, "lane-a").dirty if f.path == "junk.txt")
        assert entry.lines is None

    def test_a_timeout_is_unreadable_not_clean(self, monkeypatch, repo: Path):
        """Mutation observed red: drop the `TimeoutExpired` handler in
        `git()`. It propagates and kills the whole board -- or, if caught
        higher up and defaulted, returns empty stdout that parses as clean.
        """

        def _timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)

        monkeypatch.setattr(lane_board.subprocess, "run", _timeout)
        result = lane_board.git(["status"], cwd=repo)
        assert result.ok is False
        assert result.returncode is None  # never 0


class TestAnUnpushedIntegrationBranchIsAFinding:
    """It was displayed and not a finding, which is the same defect one layer up.

    The board printed `vs origin N unpushed` in its LANES section all along.
    Twice on 2026-08-27 an integrator merged, read `git log -1 main`, and
    reported "done" while `origin/main` was several commits behind -- the read
    passes because the object store is shared, so a local merge is
    indistinguishable from a pushed one from that seat. Both were caught from
    outside, by the lane, not by the board.
    """

    def test_an_unpushed_adr_number_is_a_collision(self, repo: Path):
        """**The consequential case.** A lane fetching right now sees that
        number as free, allocates it, and the duplicate merges cleanly -- the
        ordinal race reopened by a push gap instead of a reservation gap.

        Mutation observed red: drop the `counters` branch and return the
        informational finding for everything.
        """
        _give_it_a_remote(repo)
        _write(repo / "docs/adr/0009-new.md", _adr("0009", "New"))
        _commit(repo, "take 0009")

        lanes, findings, _ = board(repo)
        hit = findings_of(findings, "COLLISION", "unpushed", "main")
        assert hit, "an unpushed ADR number must fail the board"
        assert "0009-new.md" in hit[0].detail
        _, code = lane_board.verdict(findings, lanes, strict_overlap=False)
        assert code == 1

    def test_an_unpushed_schema_bump_is_a_collision(self, repo: Path):
        """The other global counter. Mutation observed red: drop `_DB_PATH`
        from the `counters` test."""
        _give_it_a_remote(repo)
        _write(repo / lane_board._DB_PATH, _db(11))
        _commit(repo, "bump to v11")

        hit = findings_of(board(repo)[1], "COLLISION", "unpushed", "main")
        assert hit and lane_board._DB_PATH in hit[0].detail

    def test_unpushed_commits_that_allocate_nothing_do_not_fail(self, repo: Path):
        """**The false-finding guard.** Every commit is unpushed for the
        seconds between making it and pushing it, so failing on that alone
        would put the board red almost always -- and `ruff.toml`'s own comment
        in this repo says a guard that fails every time says as much as one
        that never does.

        Mutation observed red: promote this to COLLISION.
        """
        _give_it_a_remote(repo)
        _write(repo / "README.md", "prose, allocating nothing\n")
        _commit(repo, "docs only")

        lanes, findings, _ = board(repo)
        assert findings_of(findings, "COLLISION", "unpushed") == []
        assert findings_of(findings, "OVERLAP", "unpushed", "main")
        _, code = lane_board.verdict(findings, lanes, strict_overlap=False)
        assert code == 0

    def test_a_fully_pushed_branch_reports_nothing(self, repo: Path):
        """Mutation observed red: emit the finding whenever a remote exists."""
        _give_it_a_remote(repo)
        assert findings_of(board(repo)[1], kind="unpushed") == []

    def test_a_repo_with_no_remote_reports_nothing(self, repo: Path):
        """No `origin/main` means unknowable, not unpushed. Every fixture in
        this file above has no remote, so a false positive here would have made
        the whole file noisy -- and per CLAUDE.md unreadable resolves to None,
        never to a claim.

        Mutation observed red: treat a missing upstream as 0 pushed.
        """
        _write(repo / "README.md", "no remote anywhere\n")
        _commit(repo, "local only")
        assert findings_of(board(repo)[1], kind="unpushed") == []


class TestTheVerdictCannotLookGreenWhileBlind:
    def test_the_verdict_states_all_three_counts(self, repo: Path):
        """Mutation observed red: delete the UNREADABLE count from the verdict
        line. It reads `COLLISIONS 0` and looks green while a lane was never
        read at all."""
        _add_lane(repo, "lane-a")
        lanes, findings, _ = board(repo)
        line, _ = lane_board.verdict(findings, lanes, strict_overlap=False)
        for word in ("COLLISIONS", "OVERLAPS", "UNREADABLE", "LANES COMPARED"):
            assert word in line

    def test_no_lanes_says_so_rather_than_reporting_clean(self, repo: Path):
        """A repo with only the integration tree compared nothing. Mutation
        observed red: return plain OK -- an empty board reads as a clean one."""
        lanes, findings, _ = board(repo)
        line, code = lane_board.verdict(findings, lanes, strict_overlap=False)
        assert code == 0
        assert "NO LANES" in line


class TestTheInstrumentCannotDriftFromTheGuard:
    def test_the_adr_patterns_are_byte_identical_to_the_guard(self):
        """Two parsers that disagreed about what an ADR claims would let the
        board call a tree clean that the guard then fails on at merge.

        Mutation observed red: change either pattern in either file.
        """
        assert lane_board._DECLARES_ADR.pattern == guard._DECLARES_ADR.pattern
        assert lane_board._DECLARES_COMPANION.pattern == guard._DECLARES_COMPANION.pattern

    def test_the_board_imports_no_application_code(self):
        """The instrument that reports on a broken lane must not die when a
        lane breaks an import. Mutation observed red: add
        `from backend.store.db import SCHEMA_VERSION`.
        """
        tree = ast.parse(Path(lane_board.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "backend" not in imported
        assert "frontend" not in imported

    def test_no_home_directory_is_hardcoded(self):
        """The lane root is derived from git's own answer. Mutation observed
        red: paste the absolute herdr path back into the module."""
        source = Path(lane_board.__file__).read_text(encoding="utf-8")
        for literal in (".herdr", "C:\\Users", "/Users/", "josep"):
            assert literal not in source

    def test_every_git_call_routes_through_the_wrapper(self):
        """`--no-optional-locks` is applied in exactly one place, so no caller
        can forget it and take `index.lock` in a worktree a live session is
        editing this second.

        Mutation observed red: call `subprocess.run(["git", ...])` directly
        anywhere in the module.
        """
        source = Path(lane_board.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        direct = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name != "run" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.List) and first.elts:
                head = first.elts[0]
                if isinstance(head, ast.Constant) and head.value == "git":
                    direct.append(node.lineno)
        # The single permitted one is inside `git()` itself, which prepends
        # the flag; assert there is exactly one and that it is that one.
        assert len(direct) == 1
        assert "--no-optional-locks" in source.splitlines()[direct[0]]


class TestTheRealRepoIsStillReadable:
    """Vacuity guard, in the spirit of the existing collision file's.

    A glob or a `git grep` pattern that quietly stopped matching would turn
    every test above green and silent, because they all build their own trees.
    This one runs against the repository the instrument actually ships in.
    """

    def test_the_integration_tree_is_found_and_carries_an_adr_baseline(self):
        lanes, _ = lane_board.collect(REPO, main_ref="main")
        main = next((lane for lane in lanes if lane.is_main), None)
        assert main is not None, "no lane on the integration branch"
        assert main.unreadable is None
        numbers = {claim.number for claim in main.adr_claims if claim.kind == "adr"}
        assert len(numbers) > 60, "the ADR baseline stopped being read"
        assert main.schema_version is not None
        assert main.schema_is_claimed is True

    def test_the_real_board_renders_without_raising(self):
        """Rendering is where a `None` becomes a printed `?`; a formatting bug
        there would only ever be found by a human running it."""
        lanes, notes = lane_board.collect(REPO, main_ref="main")
        findings = lane_board.analyse(REPO, lanes, "main")
        line, code = lane_board.verdict(findings, lanes, strict_overlap=False)
        entries, _ = lane_board.list_worktrees(REPO)
        text = lane_board.render(
            REPO,
            lanes,
            findings,
            notes,
            "FIXED-STAMP",
            line,
            lane_board.derive_lane_roots(entries, REPO, None),
        )
        assert "VERDICT" in text
        assert code in (0, 1, 3)
