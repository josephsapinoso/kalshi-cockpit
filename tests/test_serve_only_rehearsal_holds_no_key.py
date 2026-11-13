"""A serve-only rehearsal copy holds no Kalshi key and records nothing.

`SERVE_ONLY=1` in `docker/entrypoint.sh` exists so a copy of the live database
can be served on another machine and timed against Fly
(`docs/runbooks/home-rehearsal.md`). The copy must not become a second live
instance: a second chain runner double-spends the odds budget and the Kalshi
rate limit, and a copy holding the key carries the armed hand-bet path.

The refusal tests run the real script. Its SERVE_ONLY checks sit before the
first `python` call, so a refused boot exits without touching a database.

What this does not establish
----------------------------
- That the image boots and serves in serve-only mode. That is the runbook's
  first step, run on the machine that will serve the copy.
- That nothing else in the image reads a key from somewhere other than
  `KALSHI_PRIVATE_KEY_B64`. `KalshiConfig.load` under
  `KALSHI_PUBLIC_READ_ONLY=true` returns a config with no key path, which is
  what makes the credentialed paths refuse; that is tested in
  `tests/test_public_read_only.py`, not here.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ENTRYPOINT = REPO / "docker" / "entrypoint.sh"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _boot(tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    """Run the entrypoint with a minimal env. Refusals exit before any python."""
    base = {
        "PATH": os.environ.get("PATH", ""),
        "INSTANCE_MODE": "live",
        "DB_PATH": str(tmp_path / "never-created.db"),
    }
    base.update(env)
    return subprocess.run(
        ["bash", str(ENTRYPOINT)],
        env=base,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )


@needs_bash
class TestServeOnlyRefusesAnyKalshiCredential:
    def test_a_key_on_a_serve_only_copy_is_a_boot_refusal(self, tmp_path):
        done = _boot(
            tmp_path,
            SERVE_ONLY="1",
            KALSHI_PUBLIC_READ_ONLY="true",
            KALSHI_PRIVATE_KEY_B64="bm90LWEta2V5",
        )
        assert done.returncode == 1
        assert "KALSHI_PRIVATE_KEY_B64 is set. Refusing." in done.stdout
        assert not (tmp_path / "never-created.db").exists()

    def test_serve_only_requires_public_read_only(self, tmp_path):
        done = _boot(tmp_path, SERVE_ONLY="1")
        assert done.returncode == 1
        assert "requires KALSHI_PUBLIC_READ_ONLY=true" in done.stdout

    def test_a_mistyped_flag_is_refused_rather_than_read_as_off(self, tmp_path):
        # "true" or "yes" read as 0 would boot a full live instance -- runner,
        # key, armed path -- on a machine meant to hold a copy.
        done = _boot(tmp_path, SERVE_ONLY="true", KALSHI_PUBLIC_READ_ONLY="true")
        assert done.returncode == 1
        assert "must be 0 or 1" in done.stdout


class TestServeOnlyStartsNoRunnerAndMaterialisesNoKey:
    """Static: the two blocks that would make a copy live are both guarded."""

    def _text(self) -> str:
        return ENTRYPOINT.read_text(encoding="utf-8")

    def test_the_key_block_is_skipped_under_serve_only(self):
        assert re.search(
            r'if \[ "\$\{INSTANCE_MODE\}" != "demo" \] && '
            r'\[ "\$\{SERVE_ONLY\}" != "1" \]; then\n'
            r'  if \[ -z "\$\{KALSHI_PRIVATE_KEY_B64:-\}" \]; then',
            self._text(),
        )

    def test_the_chain_runner_is_never_started_under_serve_only(self):
        text = self._text()
        guard = text.index('if [ "${SERVE_ONLY}" = "1" ]; then\n  echo "[entrypoint] serve-only copy')
        runner = text.index("python scripts/run_loop.py")
        # The runner launch sits in the elif after the serve-only branch, so
        # serve-only can never fall through to it.
        between = text[guard:runner]
        assert 'elif [ "${INSTANCE_MODE}" != "demo" ]; then' in between
        assert text.count("python scripts/run_loop.py") == 1
