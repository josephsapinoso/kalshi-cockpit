"""Two lanes cannot claim the same ADR number, or bump the schema past itself.

WHY THIS EXISTS, AND IT IS A MEASURED FAILURE RATHER THAN A WORRY
-----------------------------------------------------------------
Work runs in parallel git worktrees. On 2026-08-27 two lanes collided three
times in one day, and the record of it is in the other lane's own commit
messages:

    "The hedging ADR becomes 0077, because 0074 was taken twice and git
     said nothing"
    "Merge main again, and the hedging ADR becomes 0078 -- 0077 collided too"
    "Merge main: two lanes both claimed schema v23, and the hedge tables
     take v24"

Each was caught by a human reading a merge. That is diligence, not a
mechanism.

**The ADR case is the silent one, and it is the reason this file exists.** Two
lanes writing `0077-a.md` and `0077-b.md` add two *different* filenames, so
git merges them cleanly and says nothing at all. Nothing downstream notices
either: every cross-reference in this repo cites an ADR by number, so a
duplicate number silently makes half those citations ambiguous.

**The schema case is NOT silent and this file says so rather than pretending
otherwise.** Both lanes edit the same `SCHEMA_VERSION = N` line, so git
conflicts and a human has to look. What is checked below is the weaker,
genuinely reachable failure: a version stamp that disagrees with the
migrations it is supposed to cover -- which a careless *resolution* of that
conflict produces.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about another branch.** A test can only see the tree it runs in.
  These fire when the lanes MERGE, which is the first moment the collision is
  representable at all -- not at the moment it is created.
- **Nothing about whether an ADR is right**, or whether its number is the one
  the author meant. Only that no two of them claim the same one and that a
  file's name agrees with its own title.
- **Nothing about `schema.sql` matching the database.** `test_store.py` and
  the migration tests own that; this only checks the version arithmetic.
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from backend.store.db import SCHEMA_VERSION, _MIGRATIONS

ADR_DIR = Path(__file__).resolve().parents[1] / "docs" / "adr"

#: An ADR declares its own number in its H1, with or without the `ADR` prefix
#: -- both spellings are in the record and neither is wrong.
_DECLARES_ADR = re.compile(r"^#\s+(?:ADR\s+)?(\d{4})\s+[—-]")

#: A companion document that supports an ADR **deliberately shares its
#: number**. `0006-in-play-evidence.md` sits beside `0006-in-play-scope.md`
#: and says so in its own first line; ADR 0003 keeps measurements out of
#: `tasks/inbox/` when re-deriving them costs real API work.
#:
#: This is why the rule keys on what a document CLAIMS TO BE rather than on
#: its filename. A naive "no two files share a numeric prefix" check reports
#: that pair as a collision, which it is not -- and a guard whose first finding
#: is a false one gets weakened or deleted.
_DECLARES_COMPANION = re.compile(r"^#\s+\w+\s+for\s+ADR\s+(\d{4})\b", re.I)


def _adr_files() -> list[Path]:
    return sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))


def _first_line(path: Path) -> str:
    return path.read_text(encoding="utf-8").splitlines()[0].strip()


class TestEveryADRNumberIsClaimedOnce:
    def test_the_corpus_is_big_enough_to_be_worth_checking(self):
        """Vacuity guard. Every test below passes over an empty list, and a
        glob that stops matching -- a rename, a moved directory -- would turn
        this whole file green and silent."""
        assert len(_adr_files()) > 60

    def test_no_two_adrs_declare_the_same_number(self):
        """Mutation observed red: copy any ADR to a new filename keeping its
        H1 number.

        The failure git cannot see. Two new files with different names merge
        clean, and every citation of that number becomes ambiguous.
        """
        by_number: dict[str, list[str]] = defaultdict(list)
        for path in _adr_files():
            match = _DECLARES_ADR.match(_first_line(path))
            if match:
                by_number[match.group(1)].append(path.name)
        clashes = {n: sorted(f) for n, f in by_number.items() if len(f) > 1}
        assert clashes == {}, (
            f"two lanes claimed the same ADR number: {clashes}. Renumber the "
            f"later one and update anything citing it -- see this file's "
            f"docstring for why nothing else will tell you."
        )

    def test_a_companion_is_not_counted_as_a_second_adr(self):
        """The rule keys on the claim, not the filename, and this is the case
        that forces it: `0006-in-play-evidence.md` shares 0006 with
        `0006-in-play-scope.md` **on purpose**.

        Mutation observed red: key the check on the filename prefix instead.
        It reports 0006 as a collision, which would be a false finding on the
        guard's very first run.
        """
        companions = [
            p.name for p in _adr_files()
            if _DECLARES_COMPANION.match(_first_line(p))
        ]
        assert "0006-in-play-evidence.md" in companions
        # And it is genuinely sharing a number with a real ADR, so the
        # exemption is load-bearing rather than decorative.
        assert any(
            _DECLARES_ADR.match(_first_line(p)) and p.name.startswith("0006")
            for p in _adr_files()
        )

    def test_every_file_declares_a_number_this_test_understands(self):
        """The other half of the vacuity guard, and the one that matters.

        A file whose H1 matches neither pattern is invisible to the collision
        check above -- so a new ADR written with a different title style would
        be silently exempt from the guard it most needs. Fail here instead, and
        make the author either match the convention or widen the pattern
        deliberately.
        """
        unreadable = [
            p.name for p in _adr_files()
            if not _DECLARES_ADR.match(_first_line(p))
            and not _DECLARES_COMPANION.match(_first_line(p))
        ]
        assert unreadable == [], (
            f"these files are exempt from the collision check because their "
            f"first line matches neither pattern: {unreadable}"
        )

    def test_a_filename_agrees_with_the_number_inside_it(self):
        """Mutation observed red: rename any ADR to a different number.

        A separate hazard from a collision and a likelier one after a manual
        renumber: `0078-....md` whose H1 still says `# 0077 —`. Citations use
        both forms -- some by path, some by number -- so the two must agree.
        """
        disagree = []
        for path in _adr_files():
            first = _first_line(path)
            match = _DECLARES_ADR.match(first) or _DECLARES_COMPANION.match(first)
            if match and not path.name.startswith(match.group(1)):
                disagree.append(f"{path.name} declares {match.group(1)}")
        assert disagree == []


#: A lane writes its ADR under a slug with no ordinal so there is nothing to
#: collide on, and the number is taken in the merge commit after a fetch. See
#: `docs/adr/README.md` and `tasks/lessons.md`, 2026-08-27.
_IS_DRAFT = re.compile(r"^DRAFT-[A-Za-z0-9][A-Za-z0-9._-]*\.md$")


def _drafts() -> list[Path]:
    return sorted(p for p in ADR_DIR.glob("*.md") if _IS_DRAFT.match(p.name))


def _current_branch() -> str | None:
    """The branch this tree is on, or None if that cannot be established.

    Unreadable resolves to None, never to a guess -- a detached HEAD in CI must
    not be silently treated as the integration branch, and must not silently
    exempt itself either.
    """
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(ADR_DIR.parents[1]),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    name = done.stdout.strip()
    return name if done.returncode == 0 and name and name != "HEAD" else None


class TestTheNumberIsAllocatedAtMergeNotAtWrite:
    """**This is the half a test could not previously reach.**

    Everything above fires at merge, which is the first moment a collision is
    representable in one tree. The collisions themselves were *created* hours
    earlier, when two lanes each took the number that was free when they
    looked. `tasks/lessons.md:168-191` settled that reading `main` first is not
    the fix -- the window is exactly as long as the gap between looking and
    pushing -- and that the fix is a filename with no ordinal in it.

    A draft is legal in a lane and illegal here. That asymmetry is what forces
    the number to be taken at the boundary rather than merely encouraged to be.
    """

    def test_no_draft_reaches_the_integration_branch(self):
        """Mutation observed red: drop a `DRAFT-x.md` into `docs/adr/` on main.

        Skips rather than passes off the integration branch, and names what it
        found, because a draft in a lane is the correct state and a silent
        green there would read as "checked and fine".
        """
        drafts = [p.name for p in _drafts()]
        branch = _current_branch()
        if branch != "main":
            if drafts:
                pytest.skip(
                    f"on `{branch or 'a detached HEAD'}`, not the integration "
                    f"branch; these still owe a number at merge: {drafts}"
                )
            pytest.skip(f"on `{branch or 'a detached HEAD'}`, not the integration branch")
        assert drafts == [], (
            f"these ADRs reached `main` without a number: {drafts}. Number them "
            f"in the merge commit, after `git fetch`, and update anything citing "
            f"them -- see docs/adr/README.md."
        )

    def test_a_draft_does_not_also_claim_an_ordinal(self):
        """A draft that declares a number in its H1 has taken one anyway, and
        has done it where nothing checks -- the worst of both.

        Mutation observed red: give a `DRAFT-*.md` an H1 of `# 0079 — ...`.
        """
        offenders = [
            p.name for p in _drafts() if _DECLARES_ADR.match(_first_line(p))
        ]
        assert offenders == [], (
            f"a draft must carry no ordinal; these do: {offenders}"
        )

    def test_a_draft_is_never_counted_as_a_numbered_adr(self):
        """The two globs must not overlap, or a draft would be invisible to one
        check and double-counted by the other.

        Mutation observed red: widen `_adr_files()` to `*.md`.
        """
        numbered = {p.name for p in _adr_files()}
        assert numbered.isdisjoint({p.name for p in _drafts()})


class TestTheSchemaVersionCoversItsMigrations:
    """**Weaker than the ADR guard, and deliberately so.**

    Two lanes bumping `SCHEMA_VERSION` edit the same line, so git conflicts and
    a human looks -- that collision is not silent and needs no test. What is
    reachable is a careless *resolution* of that conflict, or a migration added
    without moving the stamp.
    """

    def test_no_migration_claims_a_version_the_stamp_does_not_cover(self):
        """Mutation observed red: add a `_MIGRATIONS` key above SCHEMA_VERSION.

        `migrate()` runs every step whose key is greater than the recorded
        version and then stamps `SCHEMA_VERSION`. A step numbered above the
        stamp therefore runs once and is then re-run on every subsequent open,
        because the stamp never reaches it.
        """
        assert max(_MIGRATIONS) <= SCHEMA_VERSION, (
            f"migration v{max(_MIGRATIONS)} is above SCHEMA_VERSION "
            f"{SCHEMA_VERSION}; it would re-run on every open"
        )

    def test_the_stamp_may_run_ahead_of_the_migrations(self):
        """Not a bug, and asserted so the test above cannot be "fixed" into
        demanding equality.

        v22 (`loop_failures`) and v23 (`parlay_card_candidates`) are pure new
        tables. `executescript` creates them from `schema.sql` via
        `CREATE TABLE IF NOT EXISTS` on every open, on an existing volume as
        well as a fresh one, so neither needs a `_MIGRATIONS` entry --
        `_MIGRATIONS` is for changes to tables that already hold rows.
        """
        assert SCHEMA_VERSION > max(_MIGRATIONS)

    def test_the_migration_keys_have_no_gaps(self):
        """A gap means a step was deleted rather than superseded, and a
        database stamped inside the gap would skip straight past it."""
        keys = sorted(_MIGRATIONS)
        assert keys == list(range(keys[0], keys[-1] + 1))
