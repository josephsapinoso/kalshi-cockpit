"""`scripts/measure_118_trip.sh` and `.github/workflows/measure-118.yml`: the
unattended arms of #118's reading run the registered commands, on the
registered day, inside the registered windows, and can do nothing else.

The pre-registration fixed the *commands* (section 2) and the *windows*
(T1 09:00-09:55Z, T2 10:30-14:00Z on 2026-09-23) before any data existed.
Automating the trip must not quietly change either: a scheduler that runs a
slightly different QueryDef, or fires at 09:58Z, produces a number that looks
like T1 and is not. So the four command strings are compared byte for byte
against the registration's own text, every cron entry is checked against the
windows, and the workflow is refused any token that could mutate the box.

**2026-09-23: the reading is taken and the workflow is deleted** (outcome D,
`docs/measurements/2026-09-23-unattended-scouting-first-reading.md`). The
schedule and read-only guards went with it; what remains pins the script,
which the result document cites, and refuses the workflow's return.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the schedulers firing.** GitHub's cron is best-effort and a
  laptop can sleep. A green suite says the arms would take the right reading
  if they run, not that they ran.
- **Nothing about which read is T1.** Several reads will exist; Amendment 1
  of the registration picks one. This suite pins what each read *is*, not
  which one counts.
- **Nothing about the venue.** No test here opens an ssh console. The
  script's own rehearsal on 2026-09-22 is the only evidence it reads
  anything, and that evidence is on the ticket, not in this file.
- **Nothing about the Windows scheduled task.** It calls the same script by
  path; its triggers live in the Task Scheduler, outside the tree.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure_118_trip.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "measure-118.yml"
REGISTRATION = (
    ROOT
    / "docs"
    / "measurements"
    / "2026-09-21-preregistration-unattended-scouting-first-reading.md"
)

#: The registration's section 2, as it must appear in BOTH files. The test
#: does not hold these as the source of truth -- the registration does; this
#: list is the reader's copy so a drift in either file fails by name.
REGISTERED = {
    "T1_CMD": "python /app/scripts/fetch_live_route.py /api/scout",
    "T2_WATCH_LOG_CMD": (
        "python /app/scripts/inspect_live_db.py scout-watch-log --days 3 --day-start-hour 10"
    ),
    "T2_BRIEFINGS_CMD": (
        "python /app/scripts/inspect_live_db.py scout-briefings --days 3 --day-start-hour 10"
    ),
    "T3_LADDER_CMD": "python /app/scripts/inspect_live_db.py ladder-fixtures",
}

APP = "kalshi-cockpit"


def _code_lines(path: Path) -> str:
    """The file with every full-line comment dropped, so a guard reads what
    runs, not what the header says about it."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


def _script_assignments() -> dict[str, str]:
    text = SCRIPT.read_text(encoding="utf-8")
    found = {}
    for m in re.finditer(r"^(\w+_CMD)='([^']*)'$", text, flags=re.M):
        found[m.group(1)] = m.group(2)
    return found


class TestTheCommandsAreTheRegistrations:
    def test_the_script_defines_exactly_the_four_registered_commands(self):
        assert _script_assignments() == REGISTERED

    def test_every_registered_command_is_quoted_verbatim_in_the_registration(self):
        reg = REGISTRATION.read_text(encoding="utf-8")
        # T1 is registered as the whole flyctl line; the three QueryDefs as
        # the in-container command. Both forms must be present byte for byte.
        t1_full = f'flyctl ssh console -a {APP} -C "{REGISTERED["T1_CMD"]}"'
        assert f"`{t1_full}`" in reg
        for key in ("T2_WATCH_LOG_CMD", "T2_BRIEFINGS_CMD", "T3_LADDER_CMD"):
            assert f"`{REGISTERED[key]}`" in reg, key

    def test_the_script_runs_them_over_ssh_against_the_live_app_only(self):
        text = SCRIPT.read_text(encoding="utf-8")
        assert f"APP={APP}\n" in text
        # One ssh invocation shape, parameterised by the command only.
        calls = re.findall(r"^\s*flyctl ssh console .*$", text, flags=re.M)
        assert calls == ['    flyctl ssh console -a "$APP" -C "$cmd"']
        assert "flyctl deploy" not in text
        assert "secrets set" not in text

    def test_the_stamp_reads_githubs_clock_not_the_machines(self):
        code = _code_lines(SCRIPT)
        assert "https://api.github.com" in code
        # `date -u` may only appear parsing the header (`-d "$header"`),
        # never on its own as the source of the instant.
        found = re.findall(r"date -u\b(.*)$", code, flags=re.M)
        assert found, "the stamp no longer parses the header with date -u"
        for rest in found:
            assert '-d "$header"' in rest, rest


class TestTheWorkflowIsGoneAfterTheReading:
    """The reading was taken on 2026-09-23 and its result is written
    (`docs/measurements/2026-09-23-unattended-scouting-first-reading.md`).
    The workflow's crons are dated by day-of-month and month only, so a
    workflow left in the tree fires again every 23 September and ssh-reads the
    live box for a registration that is spent. Its schedule and read-only
    guards were pinned by this file while it existed (git history, `32b5dce`).
    """

    def test_the_dated_workflow_was_deleted_in_the_result_commit(self):
        assert not WORKFLOW.exists(), (
            "measure-118.yml is back: a dated cron with no year fires every "
            "23 September against a spent registration"
        )
