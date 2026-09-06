"""The inspector is eight files now, and three things have to stay true.

`scripts/inspect_live_db.py` reached 254,479 bytes on 2026-09-06 -- 97% of the
262,144-byte ceiling at which the Read tool refuses a file outright. That
refusal is silent truncation, not an error, so the file had become
unmaintainable in a way no test could see: nobody could add a query without
pushing it over, and a trim had already been tried and had bought weeks. It
was split into an entrypoint plus seven domain modules.

A split moves three properties out of the reach of the guards that used to
cover them, and this file is those three guards.

**1. The image.** `.dockerignore` carries `scripts/*` and an `!` allowlist,
and `tests/test_has_callers.py` derives two halves of that allowlist -- what
`docker/entrypoint.sh` runs, and what declares its own
`/app/scripts/<name>.py` invocation. **Neither derivation can see an import.**
Only the entrypoint is invoked by path, so only the entrypoint declares that
path, so the ssh derivation reports a healthy allowlist while the seven
modules it imports are absent from the image. That failure surfaces as
`ModuleNotFoundError` at an ssh prompt during an incident -- the same shape as
the four `.dockerignore` failures that file records, in a half neither of its
derivations reaches.

**2. The subcommand surface.** The names are the interface. `CLAUDE.md` cites
`credits-day`, `credits-month`, `visit-freshness` and `sweep-log` by name;
`tasks/NEXT.md` and the `docs/measurements/` record cite more. A rename or a
disappearance is a break in every document that cites it, and it would not
fail any existing test -- `QUERIES` would simply be smaller and everything
downstream of it would agree.

**3. The ceiling itself.** `tests/test_session_files_are_readable.py` fails
any tracked source file at or over 262,144 bytes, which is the backstop and
is far too late: at that point the file is already unreadable and the fix is
another split. The budget here fires at 60%, which is where a module can
still be read, understood and cut deliberately.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about the queries being correct.** `tests/test_inspect_live_db.py`
  and its siblings own that. A green suite here says the eight files reach the
  box, expose the same names, and can be read.
- **Nothing about `.dockerignore` being sufficient.** It checks that the
  pattern file does not *exclude* the modules. That `COPY scripts/ ./scripts/`
  then copies them is a property of the Dockerfile, asserted below by reading
  it, and neither assertion runs a docker build.
- **Nothing about the live box.** No test here has opened `/data/cockpit.db`
  or run anything on Fly.

MUTATIONS OBSERVED RED (2026-09-06), each restored immediately after:
- `test_every_module_the_entrypoint_imports_survives_dockerignore`: deleted
  the `!scripts/inspect_live_db_*.py` line from `.dockerignore` -- all seven
  domain modules reported excluded from the image.
- `test_the_derivation_sees_the_imports_it_is_supposed_to_see`: pointed the
  extractor at `scripts/migrate_db.py`, which imports no sibling.
- `test_no_subcommand_has_disappeared`: renamed `"credits-month"` to
  `"credits-month-RENAMED"` in `QUERIES`. A rename rather than a deletion on
  purpose -- a rename is the failure mode that reads as harmless and breaks
  every document citing the old name.
- `test_every_inspector_module_is_under_the_read_budget`: lowered
  `READ_BUDGET_BYTES` to 40,000; the two largest modules tripped it and the
  other six passed, so the parametrisation discriminates rather than failing
  wholesale.
- `TestTheDualImportArrangementWorks`: replaced the `sys.path` append in
  `scripts/inspect_live_db.py` with `pass`. Two went red --
  `test_the_package_import_works_too`, because `from scripts.inspect_live_db
  import ...` can no longer find the siblings, and
  `test_the_entrypoint_appends_rather_than_prepends_its_directory`. The
  path-invocation test stayed GREEN, which is the point of running both: a
  path invocation already has `scripts/` on `sys.path`, so the box would
  never have shown this break.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_has_callers import _dockerignore_patterns, _is_ignored

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ENTRYPOINT = SCRIPTS / "inspect_live_db.py"

#: The Read tool's hard ceiling, from `tests/test_session_files_are_readable.py`.
READ_TOOL_LIMIT_BYTES = 262_144

#: The budget this file enforces: 60% of the ceiling.
#:
#: Not the ceiling itself. A guard that fires at the ceiling fires at the
#: moment the file has already become unreadable, which is what happened to
#: the pre-split module -- it was found at 97%, by a session that wanted to
#: add a query and could not. 60% leaves room to add several queries to any
#: one domain before the next cut has to be considered, and it leaves the
#: file readable while that decision is taken.
READ_BUDGET_BYTES = int(READ_TOOL_LIMIT_BYTES * 0.60)

#: Every subcommand, as of the split. Pinned, not derived.
#:
#: A derived list would compare `QUERIES` to itself and could not fail. These
#: names are cited by `CLAUDE.md`, `tasks/NEXT.md` and the measurement record,
#: so the list is the interface contract and belongs written down.
#:
#: Adding a query means adding its name here, deliberately, in the same
#: commit. Removing one means deleting a name here -- which is the moment to
#: grep the repo for it, because a document citing a subcommand that no longer
#: exists is worse than one citing nothing.
SUBCOMMANDS = (
    "actionable-audit",
    "book-rows",
    "closing-lines-for-pull",
    "clv-coverage",
    "clv-signal-pull",
    "combo-bids-tail",
    "credits-day",
    "credits-month",
    "credits-tail",
    "db-sizes",
    "decision-dump",
    "estimate-match-status",
    "events-for-pull",
    "failure-journal",
    "forward-lock",
    "h4-balance-spans",
    "h4-settlement-balance",
    "kalshi-quotes-band",
    "lock-attribution",
    "loop-rss",
    "manual-order-refusals",
    "manual-orders-audit",
    "notifications",
    "parlay-candidates-timing",
    "parlay-lookups-tail",
    "pass-gaps",
    "prop-bookmakers",
    "prop-rungs",
    "prune-frontier",
    "results-for-pull",
    "series",
    "study-stop",
    "sweep-log",
    "visit-freshness",
    "walk-log",
    "window-freshness",
)


def _sibling_modules_imported_by(path: Path) -> list[str]:
    """`scripts/<name>.py` for every sibling module `path` imports.

    Parsed from the AST rather than grepped, and restricted to names that
    resolve to a real file beside it. A module imported under a name with no
    matching file is not silently dropped -- `test_every_import_resolves`
    below turns that into a failure, because on the box it would be a
    `ModuleNotFoundError` at the first line of the run.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.append(node.module)
    out: list[str] = []
    for name in names:
        if "." in name:
            continue
        candidate = SCRIPTS / f"{name}.py"
        if candidate.exists() and candidate != path:
            rel = f"scripts/{candidate.name}"
            if rel not in out:
                out.append(rel)
    return sorted(out)


def _top_level_import_names(path: Path) -> list[str]:
    """Every bare module name the file imports, resolved or not."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.append(node.module)
    return sorted({n for n in names if "." not in n})


class TestTheInspectorFamilySurvivesDockerignore:
    """The allowlist half that neither existing derivation can reach."""

    def test_the_derivation_sees_the_imports_it_is_supposed_to_see(self):
        """Anchor against vacuity.

        If the extractor stopped matching, every assertion below would pass by
        finding nothing to check -- which is precisely how the hand-kept half
        of this allowlist failed four times.
        """
        found = _sibling_modules_imported_by(ENTRYPOINT)
        assert len(found) >= 5, (
            f"the entrypoint is supposed to import a family of domain "
            f"modules and the extractor found {found}. Either the split was "
            f"undone or the extractor stopped matching."
        )
        assert "scripts/inspect_live_db_common.py" in found

    def test_every_module_the_entrypoint_imports_survives_dockerignore(self):
        """The one that would have caught the fifth failure of this allowlist.

        `COPY scripts/ ./scripts/` copies what `.dockerignore` admits. The
        entrypoint is admitted by name; its imports are admitted by the
        `!scripts/inspect_live_db_*.py` glob, and nothing but this test says
        so.
        """
        patterns = _dockerignore_patterns()
        missing = [
            rel
            for rel in _sibling_modules_imported_by(ENTRYPOINT)
            if _is_ignored(rel, patterns)
        ]
        assert not missing, (
            f"{missing} are imported by scripts/inspect_live_db.py, which is "
            f"invoked on the live box over `flyctl ssh console`, and "
            f"`.dockerignore` excludes them from the build context. The "
            f"inspector would raise ModuleNotFoundError on its first import "
            f"line, at an ssh prompt, during an incident. Add an `!` line."
        )

    def test_every_import_resolves_to_a_file_or_the_stdlib(self):
        """A name with no file and no stdlib module is a crash on the box."""
        unresolved = []
        for name in _top_level_import_names(ENTRYPOINT):
            if (SCRIPTS / f"{name}.py").exists():
                continue
            try:
                __import__(name)
            except ImportError:
                unresolved.append(name)
        assert not unresolved, (
            f"{unresolved} are imported by the inspector entrypoint and "
            f"resolve to neither a sibling module nor an importable package"
        )

    def test_the_dockerfile_copies_the_whole_scripts_directory(self):
        """The second allowlist, one layer up.

        `.dockerignore` deciding a file may enter the build context is only
        half of shipping it; a `COPY` has to name it. This is a directory
        copy today, so the glob above is sufficient -- if it ever becomes a
        list of files, the glob silently stops being enough and this fails.
        """
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        copies = [
            line.strip()
            for line in dockerfile.splitlines()
            if line.strip().startswith("COPY ") and "scripts" in line
        ]
        assert copies == ["COPY scripts/ ./scripts/"], (
            f"the Dockerfile's scripts COPY lines are {copies}. This test "
            f"assumed one directory copy; if it is now per-file, every "
            f"inspector module needs naming there too."
        )

    def test_no_domain_module_claims_to_be_ssh_invoked(self):
        """The domain modules must not join the other derived list.

        `test_has_callers.py` derives the ssh-invoked set from a script naming
        its OWN `/app/scripts/<name>.py`. A domain module that did so would be
        claiming it can be run by path, which it cannot -- it has no `main`,
        no parser and no `__main__` block.
        """
        for path in sorted(SCRIPTS.glob("inspect_live_db_*.py")):
            text = path.read_text(encoding="utf-8")
            assert f"/app/scripts/{path.name}" not in text, (
                f"{path.name} declares its own live invocation path, but it "
                f"is a library module with no entry point"
            )


class TestTheSubcommandSurfaceIsUnchanged:
    """The names are the interface, and documents cite them."""

    def test_no_subcommand_has_disappeared(self):
        from scripts.inspect_live_db import QUERIES

        missing = sorted(set(SUBCOMMANDS) - set(QUERIES))
        assert not missing, (
            f"{missing} were subcommands of `inspect_live_db.py` and are not "
            f"any more. `CLAUDE.md`, `tasks/NEXT.md` and the "
            f"`docs/measurements/` record cite these by name; a rename or a "
            f"removal is a break in every document that does. If the removal "
            f"is deliberate, grep for the name first and fix what cites it."
        )

    def test_no_subcommand_has_appeared_unrecorded(self):
        """The other direction, so this list cannot rot into a subset.

        A pinned list that only checks one way stops being a description of
        the surface the moment a query is added, and then the guard above is
        asserting something about a file that no longer exists.
        """
        from scripts.inspect_live_db import QUERIES

        extra = sorted(set(QUERIES) - set(SUBCOMMANDS))
        assert not extra, (
            f"{extra} are new subcommands. Add them to SUBCOMMANDS in this "
            f"file so the surface stays written down."
        )

    def test_every_subcommand_resolves_and_names_a_callable(self):
        """`QUERIES` holding a name is not the same as the name working."""
        from scripts.inspect_live_db import resolve_query

        for name in SUBCOMMANDS:
            spec = resolve_query(name)
            assert callable(spec.run), f"{name} has no runnable query"
            assert spec.description.strip(), f"{name} has no description"

    def test_the_help_text_lists_every_subcommand(self):
        """The epilog is how a caller on the box discovers the names."""
        from scripts.inspect_live_db import _build_parser

        epilog = _build_parser().epilog
        for name in SUBCOMMANDS:
            assert f"  {name:<24}" in epilog, f"{name} is not in --help"


class TestTheInspectorCanStillBeRead:
    """The defect the split existed to fix, guarded so it cannot recur."""

    def _family(self) -> list[Path]:
        return sorted(SCRIPTS.glob("inspect_live_db*.py"))

    def test_the_family_is_not_empty(self):
        family = self._family()
        assert len(family) >= 5, f"only {len(family)} inspector modules found"

    @pytest.mark.parametrize(
        "name", [p.name for p in sorted(SCRIPTS.glob("inspect_live_db*.py"))]
    )
    def test_every_inspector_module_is_under_the_read_budget(self, name: str):
        size = (SCRIPTS / name).stat().st_size
        assert size < READ_BUDGET_BYTES, (
            f"scripts/{name} is {size:,} bytes, over the {READ_BUDGET_BYTES:,}"
            f"-byte budget (60% of the {READ_TOOL_LIMIT_BYTES:,}-byte Read-tool"
            f" ceiling). Split it along a domain seam and add the new module to"
            f" `.dockerignore`'s `!scripts/inspect_live_db_*.py` glob -- do not"
            f" raise this number, and do not trim: trimming is what was tried"
            f" on the 254KB module and it bought weeks."
        )


class TestTheDualImportArrangementWorks:
    """Two path layouts, one file, and the box only ever exercises one."""

    def test_the_entrypoint_runs_when_invoked_by_path(self):
        """`python /app/scripts/inspect_live_db.py`, reproduced locally.

        This is the invocation the ssh ruling permits and the only one the
        live box makes. It puts `scripts/` on `sys.path` and NOT the repo
        root, so `from scripts.inspect_live_db import ...` would fail here and
        a bare `import inspect_live_db_common` must work.

        Run from a directory that is not the repo, so a working-directory
        accident cannot supply the path.
        """
        result = subprocess.run(
            [sys.executable, str(ENTRYPOINT), "--help"],
            cwd=str(ROOT.parent),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"invoking the inspector by path failed:\n{result.stderr}"
        )
        assert "credits-day" in result.stdout

    def test_the_package_import_works_too(self):
        """`from scripts.inspect_live_db import ...`, which is how tests reach it.

        Here the repo root is on `sys.path` and `scripts/` is not, which is
        the opposite layout. Both have to work off one set of import
        statements, and the `sys.path` append in the entrypoint is what makes
        that true.
        """
        from scripts.inspect_live_db import QUERIES, main

        assert callable(main)
        assert QUERIES

    def test_the_entrypoint_appends_rather_than_prepends_its_directory(self):
        """The append is load-bearing and reads like a style choice.

        At `sys.path[0]` the scripts directory would shadow repo-root modules
        for everything imported later in the process, and under pytest that
        process is the whole suite. On the box the directory is already
        `sys.path[0]`, so the append costs nothing there.
        """
        source = ENTRYPOINT.read_text(encoding="utf-8")
        assert "sys.path.append(_HERE)" in source
        assert "sys.path.insert(0, _HERE)" not in source
