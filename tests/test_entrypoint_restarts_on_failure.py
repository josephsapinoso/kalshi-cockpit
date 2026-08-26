"""A container that dies must exit non-zero, or the platform will not restart it.

Measured on live, 2026-08-26. `entrypoint.sh` tore the container down exactly
as designed when the chain runner died -- and exited 0. Fly's restart policy is
on-failure, so it logged

    machine exited with exit code 0, not restarting

and left the machine STOPPED. `auto_stop_machines = "off"` and
`min_machines_running = 1` do not govern a container that exited successfully.
The box then stayed down until an HTTP request woke it through
`auto_start_machines`, at 23-37 seconds of cold start, and recorded nothing in
between.

The function is behaviourally exercised rather than grepped: the real
`shutdown` is extracted from the real file and run, so a future rewrite that
keeps the name and loses the exit code is still caught.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That Fly restarts the machine.** That is the platform's behaviour and this
  suite cannot reach it. Confirm it by watching `flyctl machine status` event
  logs after a deploy.
- **Anything about the three failure branches' text**, only about the code they
  exit with.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "docker" / "entrypoint.sh"

def _working_bash() -> str | None:
    """A bash that can actually exec, resolved by absolute path.

    `subprocess` and `shutil.which` do not agree on this machine: bare "bash"
    resolves to the WSL shim, which fails with `execvpe(/bin/bash): No such
    file or directory` when WSL has no distribution installed, while `which`
    finds Git Bash. Resolving explicitly and then PROVING the shell runs is the
    difference between a test that is skipped and a test that reports a shell
    error as a failed assertion about the entrypoint.
    """
    found = shutil.which("bash")
    if found is None:
        return None
    try:
        probe = subprocess.run([found, "-c", "exit 7"], capture_output=True)
    except OSError:
        return None
    return found if probe.returncode == 7 else None


BASH = _working_bash()

pytestmark = pytest.mark.skipif(
    BASH is None, reason="no working bash on this machine"
)


def _shutdown_function() -> str:
    """The real `shutdown` body, lifted out of the real script."""
    source = ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(r"^shutdown\(\) \{.*?^\}", source, re.MULTILINE | re.DOTALL)
    assert match, "no `shutdown()` function in entrypoint.sh -- it was renamed"
    return match.group(0)


def _run(call: str) -> int:
    script = f'pids=""\n{_shutdown_function()}\n{call}\n'
    assert BASH is not None
    return subprocess.run([BASH, "-c", script], capture_output=True).returncode


class TestTheFailureTeardownExitsNonZero:
    def test_a_failure_teardown_exits_non_zero(self):
        assert _run("shutdown 1") != 0

    def test_a_signal_teardown_still_exits_zero(self):
        """A signal is somebody asking, not something breaking.

        A deploy sends TERM. Exiting non-zero there would make every deliberate
        stop look like a crash, which is the same defect pointed the other way.
        """
        assert _run("shutdown 0") == 0

    def test_the_default_is_zero_so_the_trap_needs_no_argument(self):
        assert _run("shutdown") == 0


class TestTheCallSitesPassTheRightCode:
    """Population counts, not spot checks (`tasks/lessons.md`, 2026-08-26)."""

    def _source(self) -> str:
        return ENTRYPOINT.read_text(encoding="utf-8")

    def test_the_supervisor_teardown_asks_for_a_restart(self):
        src = self._source()
        assert re.search(r"^shutdown 1$", src, re.MULTILINE), (
            "the `wait -n` teardown must call `shutdown 1`; a bare `shutdown` "
            "exits 0 and Fly will not restart the machine"
        )

    def test_no_bare_shutdown_call_survives_outside_the_trap(self):
        src = self._source()
        bare = re.findall(r"^\s*shutdown\s*$", src, re.MULTILINE)
        assert bare == [], (
            f"{len(bare)} bare `shutdown` call(s) remain. Every call site must "
            f"say which case it is: 0 for a signal, non-zero for a death."
        )

    def test_the_trap_names_its_exit_code_explicitly(self):
        src = self._source()
        assert "trap 'shutdown 0' INT TERM" in src
