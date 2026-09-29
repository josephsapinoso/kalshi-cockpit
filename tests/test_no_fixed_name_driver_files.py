"""No test writes a fixed-name `_*.mjs` / `_*.ts` file into the source tree.

A node driver has to sit beside the module it imports, so it cannot live in
`tmp_path`. Under `pytest -n auto` two workers then race on one literal path
(#190's proof run: 11 tests failed with ENOENT that pass serially). The fix is
a unique NAME, from `tests/_node_driver.py`. This file keeps it fixed.

How: parse every `tests/*.py`; in any file that calls `.write_text` or
`.write_bytes`, flag every string constant that is exactly a `_`-prefixed
`.mjs`/`.ts` filename (optionally with a directory). `tests/_node_driver.py`
is the helper and is excluded, as is this file.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- A fixed name assembled at run time (f-string, concatenation) is invisible to
  it. The suite itself is the check for those: `pytest -n auto` fails loudly.
- A fixed name WITHOUT a leading underscore. Such a write into a private
  `tmp_path` is safe; one into the source tree is not caught here.
- That the helper's names are unique across machines; only across processes
  and calls on one host.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
EXCLUDED = {"_node_driver.py", Path(__file__).name}
FIXED_NAME = re.compile(r"(^|/)_[^\s/\"']*\.(mjs|ts)$")


def fixed_name_writers(source: str) -> list[tuple[int, str]]:
    """(line, literal) for each fixed-name literal in a file that writes files."""
    tree = ast.parse(source)
    writes = any(
        isinstance(n, ast.Attribute) and n.attr in {"write_text", "write_bytes"}
        for n in ast.walk(tree)
    )
    if not writes:
        return []
    return [
        (n.lineno, n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and FIXED_NAME.search(n.value)
    ]


class TestNoFixedNameDriverFiles:
    def test_no_test_file_writes_a_fixed_name_driver(self):
        offenders = []
        for path in sorted(TESTS.glob("*.py")):
            if path.name in EXCLUDED:
                continue
            for line, literal in fixed_name_writers(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.name}:{line} {literal!r}")
        assert not offenders, (
            "fixed-name node driver written into the source tree; two xdist "
            "workers would race on it. Use tests/_node_driver.node_driver:\n"
            + "\n".join(offenders)
        )

    def test_the_scanner_catches_a_fixed_name_and_passes_a_helper_call(self):
        bad = 'p = d / "_x_driver.mjs"\np.write_text("x")\n'
        also_bad = 'q = "_m.ts"\nq2.write_bytes(b"")\n'
        good = "with node_driver(d, src) as p:\n    p.read_text()\n"
        assert fixed_name_writers(bad) == [(1, "_x_driver.mjs")]
        assert fixed_name_writers(also_bad) == [(1, "_m.ts")]
        assert fixed_name_writers(good) == []

    def test_the_helper_names_are_unique_per_call(self):
        from tests._node_driver import unique_name

        names = {unique_name() for _ in range(200)}
        assert len(names) == 200
        assert all(re.fullmatch(r"_driver_\d+_[0-9a-f]{32}\.mjs", n) for n in names)

    def test_the_helper_unlinks_on_exit_and_on_error(self, tmp_path):
        from tests._node_driver import node_driver

        with node_driver(tmp_path, "1") as path:
            assert path.read_text() == "1"
        assert not path.exists()
        try:
            with node_driver(tmp_path, "2") as path2:
                raise RuntimeError
        except RuntimeError:
            pass
        assert not path2.exists()
