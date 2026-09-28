"""`requirements.txt` pinned `pandas~=2.2` and nothing imported it.

Checked 2026-09-28 (#189, part of #185/ADR 0188): no file in `backend/`,
`scripts/`, `tests/` or `warehouse/` contains `import pandas` or
`from pandas`, and there is no `.df()`, `fetchdf` or `to_pandas` call
anywhere. It rode along for the install-time and image-size cost, and for
`pip-audit` to keep checking it, with no caller to show for either.

This file does two things:

1. Asserts `pandas` is gone from `requirements.txt`.
2. Holds every *other* heavy analytics dependency (`numpy`, `scipy`,
   `pyarrow`, `duckdb`) to the bar pandas failed, so the next one that rides
   along unused is caught here instead of found by a session grepping the
   tree by hand. "Heavy" is judged by what these are: compiled, multi-MB
   wheels that its own comment in `requirements.txt` groups under
   `# --- Analytics ---`, not by the small pure-Python packages beside them
   (`PyYAML`, `python-dotenv`) that cost nothing to carry unused.

What "has an importer" means here
----------------------------------
At least one `import X` / `from X import ...` in `backend/` (walked
recursively), OR in a script that actually ships in the container image --
derived from `.dockerignore`'s `!scripts/...` allowlist lines, the same
mechanism `tests/test_has_callers.py` uses for the module-reachability half
of this question. A script excluded by `.dockerignore` (everything under
`scripts/` except the allowlisted names) does not count: it is a laptop-side
tool, and an import that exists only there is not a reason to ship the
package to the image tests/ and warehouse/ (dbt models, dbt tests) are
deliberately NOT scanned -- `warehouse/` isn't part of `requirements.txt`'s
install closure at all (dbt-duckdb comes from `requirements-dev.txt`), and a
test-only import would make this file pass for a dependency the *shipped*
image does not need, which is the same hole `test_has_callers.py` closed for
symbol reachability.

What this does not establish
-----------------------------
- That the importer is itself reached at runtime. Same floor as
  `test_has_callers.py`'s module-reachability half: a module `backend/`
  imports behind a branch that never fires still counts.
- Anything about `requirements-dev.txt`. `dbt-duckdb~=1.9` lives there and
  pulls in its own dependency closure at dev/CI time regardless of what this
  file finds -- see the note in `requirements.txt` beside the removed
  `pandas` pin, and the docstring class below for what was checked about it.
- That a package absent from this HEAVY list has a caller. Only the four
  named below are held to the bar; expanding the list to cover a fifth
  heavy dependency is a decision for whoever adds it, not something this
  file infers on its own.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
DOCKERIGNORE = ROOT / ".dockerignore"

# Every heavy runtime dependency `requirements.txt` still pins. `pandas` is
# deliberately NOT here -- it was removed, and its absence from the pin file
# is asserted separately, below.
HEAVY_DEPS = ("numpy", "scipy", "pyarrow", "duckdb")


def _requirements_text() -> str:
    return REQUIREMENTS.read_text("utf-8")


def _pinned_packages() -> set[str]:
    """Package names pinned in `requirements.txt`, lowercased.

    A pin line looks like `pandas~=2.2` or `uvicorn[standard]~=0.34` --
    package name, optional `[extra]`, then a version specifier. Comments and
    blank lines are skipped.
    """
    names: set[str] = set()
    for raw in _requirements_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)", line)
        if match:
            names.add(match.group(1).lower())
    return names


def _shipped_scripts() -> list[Path]:
    """`scripts/*.py` files that actually reach the container image.

    Derived from `.dockerignore`'s `!scripts/...` allowlist lines, the same
    source `tests/test_has_callers.py` reads for the module-reachability
    check. `scripts/*` is excluded wholesale and then re-included one file
    (or glob) at a time; a script not named there does not exist on the
    deployed machine, so an import found only inside it is not evidence the
    image needs the package.
    """
    text = DOCKERIGNORE.read_text("utf-8")
    paths: list[Path] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("!scripts/"):
            continue
        pattern = line[1:]  # drop the leading "!"
        for match in ROOT.glob(pattern):
            if match.is_file() and match.suffix == ".py":
                paths.append(match)
    return paths


def _backend_files() -> list[Path]:
    return [p for p in (ROOT / "backend").rglob("*.py") if "__pycache__" not in str(p)]


def _imports(path: Path) -> set[str]:
    """Top-level module names this file imports (`import X` / `from X import ...`)."""
    try:
        tree = ast.parse(path.read_text("utf-8", errors="replace"))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def _importers(package: str) -> list[str]:
    """Shipped files (relative paths) that import `package` at the top level."""
    hits: list[str] = []
    for path in _backend_files() + _shipped_scripts():
        if package in _imports(path):
            hits.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return hits


class TestPandasIsGone:
    def test_pandas_is_absent_from_requirements(self):
        pinned = _pinned_packages()
        assert "pandas" not in pinned, (
            "`pandas` is still pinned in requirements.txt, but nothing in "
            "backend/, scripts/, tests/ or warehouse/ imports it (checked "
            "2026-09-28, #189). If a caller now exists, this test -- not "
            "the pin -- is what should change: add pandas to HEAVY_DEPS "
            "above so its importer is held to the same bar as the others."
        )

    def test_nothing_shipped_imports_pandas(self):
        """Belt and suspenders on the claim the ticket opened with: even if
        the pin came back by accident (a transitive requirement, a merge),
        nothing in the shipped surface reaches for it."""
        hits = _importers("pandas")
        assert not hits, (
            f"pandas is imported by {hits} even though it is not pinned in "
            f"requirements.txt -- that import will fail at runtime unless "
            f"another pinned package happens to vendor it."
        )


class TestEveryHeavyRuntimeDependencyHasAnImporter:
    """The guard `pandas` should have had from the start.

    Mutation (see the ticket): re-add `pandas~=2.2` to `requirements.txt`
    and this class's `test_every_heavy_runtime_dependency_has_an_importer`
    stays green (nothing imports it), which is exactly the state that let
    the unused pin sit for as long as it did. The dependency-absent-an-
    importer failure mode is caught by pairing this file's *presence* check
    against `HEAVY_DEPS` with a human decision to add a name to the list --
    the same shape `MUST_HAVE_CALLERS` in `test_has_callers.py` uses, and
    the same limit: an entry nobody added is an entry this cannot see. What
    it DOES catch, mechanically, is a heavy dependency named in this list
    losing its only caller, and a `pandas`-shaped one already on the list
    never having had one.
    """

    @pytest.mark.parametrize("package", HEAVY_DEPS)
    def test_every_heavy_runtime_dependency_has_an_importer(self, package):
        pinned = _pinned_packages()
        assert package in pinned, (
            f"`{package}` is in HEAVY_DEPS but not pinned in "
            f"requirements.txt -- update one or the other, this list "
            f"should describe what's actually shipped."
        )
        hits = _importers(package)
        assert hits, (
            f"`{package}~=...` is pinned in requirements.txt but nothing "
            f"in backend/ or a shipped script imports it. That is the "
            f"exact shape `pandas` was in (#189) -- install time and "
            f"image size paid for a package with no caller. Either wire "
            f"it up, or drop the pin and remove `{package}` from "
            f"HEAVY_DEPS in this file."
        )


class TestTheScanIsNotVacuous:
    """Fail-closed guard: a scan that silently found nothing would make
    every assertion above pass by checking nothing, which is the exact
    failure mode this file exists to catch, reproduced in the detector."""

    def test_backend_files_are_found(self):
        assert len(_backend_files()) >= 20, (
            "backend/ walk returned suspiciously few files; the importer "
            "scan below trusts this to be a real walk of backend/."
        )

    def test_shipped_scripts_are_found(self):
        shipped = _shipped_scripts()
        assert shipped, (
            ".dockerignore's `!scripts/...` allowlist resolved to no "
            "files -- either the allowlist changed shape or the glob "
            "parsing here broke. Either way the shipped-script half of "
            "the importer scan is checking nothing."
        )

    def test_known_importers_are_found(self):
        """Each HEAVY_DEPS package is known (from the ticket's own grep) to
        have a real importer today. Naming one confirms the scanner sees
        genuine call sites, not just an empty result it cannot distinguish
        from "nothing imports this"."""
        assert "backend/core/correlation.py" in _importers("numpy")
        assert "backend/core/devig.py" in _importers("scipy")
        assert "backend/store/publish.py" in _importers("pyarrow")
        assert "backend/analysis/marts.py" in _importers("duckdb")
