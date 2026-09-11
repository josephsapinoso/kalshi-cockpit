"""The boot warm-up actually warms, rather than silently skipping.

WHY THIS EXISTS
---------------
`scripts/warm_read_path.py` swallows every exception on purpose: it runs during
boot on the machine that holds real money, and a warm-up that can fail a boot is
worse than a cold cache. The cost of that decision is that **every failure is
invisible unless someone reads the log.**

It shipped broken on 2026-09-10 and proved the point. `python
scripts/warm_read_path.py` puts `/app/scripts` on `sys.path`, not `/app`, so
`from backend.parlays import ...` raised and the boot logged:

    [warm] skipped: ModuleNotFoundError: No module named 'backend'

Nothing else was wrong. The container was healthy, the entrypoint was correct,
the deploy succeeded, and the warm-up did nothing at all — the first
`/api/parlays` still took 17.9s. The only symptom was one line in a log stream
that retains about ten minutes.

So this runs the script the way the entrypoint runs it — as a subprocess, from
the repo root, by path — and asserts it reports success. A test that imported
the module directly would put the repo root on `sys.path` itself and could not
have caught this.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about whether warming helps.** Whether pulling these pages in makes
  the first real request faster is a live measurement against the 20.5s cold
  baseline, and a temp database of a few rows cannot speak to it.
- **Nothing about timing.** The script races the first user request by
  construction; that is a property of the boot, not of this.
- It does not assert the entrypoint runs it — `test_has_callers.py` and
  `test_entrypoint_background_jobs_are_liveness_signals.py` own that.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from backend.store import db as store

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "warm_read_path.py"


def run(db_path: pathlib.Path) -> subprocess.CompletedProcess:
    """As the entrypoint invokes it: by path, cwd at the repo root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "warm.db"
    conn = store.init_db(path)
    conn.commit()
    conn.close()
    return path


class TestItWarmsRatherThanSkipping:
    def test_it_reports_success_on_a_real_database(self, seeded):
        proc = run(seeded)
        assert proc.returncode == 0, proc.stderr
        assert "[warm] skipped" not in proc.stdout, (
            "the warm-up swallowed an error and did nothing; the boot would "
            f"look healthy and the cache would stay cold. Output: {proc.stdout}"
        )
        assert "parlay read path warmed" in proc.stdout, proc.stdout

    def test_it_can_import_backend_when_run_by_path(self, seeded):
        """The exact 2026-09-10 failure, named so a regression is unambiguous."""
        proc = run(seeded)
        assert "ModuleNotFoundError" not in proc.stdout, (
            "`python scripts/warm_read_path.py` cannot import `backend` -- the "
            "repo root is not on sys.path. See migrate_db.py:22."
        )

    def test_it_reports_the_leg_count_so_an_empty_read_is_visible(self, seeded):
        """A warm-up that reads an empty database and one that reads the slate
        both 'succeed'. The count is how a human tells them apart."""
        proc = run(seeded)
        assert "candidate legs" in proc.stdout, proc.stdout


class TestItCannotBreakTheBoot:
    def test_a_missing_database_still_exits_zero(self, tmp_path):
        """The swallow is the design. It must hold for the failure mode most
        likely on a real box -- a volume that is not there yet."""
        proc = run(tmp_path / "does-not-exist.db")
        assert proc.returncode == 0, (
            "the warm-up exited non-zero; under `set -e` in the entrypoint "
            "that is a failed boot on the machine holding real money"
        )
        assert "[warm] skipped" in proc.stdout, proc.stdout

    def test_a_corrupt_database_still_exits_zero(self, tmp_path):
        path = tmp_path / "corrupt.db"
        path.write_bytes(b"this is not a sqlite file, not even close")
        proc = run(path)
        assert proc.returncode == 0, proc.stderr
        assert "[warm] skipped" in proc.stdout, proc.stdout

    def test_it_never_writes(self, seeded):
        """Read-only, single-shot. The chain runner is the writer; a second
        writer on the volume during boot buys nothing and risks something."""
        source = SCRIPT.read_text(encoding="utf-8")
        assert "mode=ro" in source
        before = seeded.stat().st_mtime_ns
        run(seeded)
        assert seeded.stat().st_mtime_ns == before, (
            "the warm-up modified the database"
        )
