"""Slot runner for the 2026-09-13 combo-exit capture.

    .venv\\Scripts\\python.exe scripts\\run_combo_exit_capture.py --slot c3
    .venv\\Scripts\\python.exe scripts\\run_combo_exit_capture.py --slot c3 --dry-run

Ten hand-typed commands over one 9¼-hour day is how a slot gets typed for
the wrong hour. This turns each slot into one invocation. It is a **caller**,
not a second implementation: it assembles the exact commands the registration
fixes and hands them to `subprocess`, and it does not import, re-derive or
duplicate any analysis from `measure_combo_book_presence.py`.

The registration is the contract, not this docstring
------------------------------------------------------
`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md`,
§7 (Arm A's clock and command) and §11.6 (Arm D's clock, command and the
reason the two arms are separate invocations). If this file and the
registration ever disagree, the registration wins.

Five slots, fixed clock (§7, §11.6), no sixth capture, no slot moved more
than 30 minutes:

    C1 15:30Z   C2 17:30Z   C3 20:00Z   C4 23:30Z   C5 00:45Z (2026-09-14)

Two invocations per slot, run in this order and **deliberately separate
subprocess calls** -- folding them into one command would let an empty shard
page (`EmptySeriesRequested`, exit 2) abort Arm A's capture for that slot too:

    Arm A (comparison)  --max-books 40                 default series
    Arm D (PRIMARY)     --max-books 25 --series KXMVECROSSCATEGORY-SHARD1

Stdout+stderr are redirected to a `.txt` per capture, exactly as `> file 2>&1`
would do from a shell -- `to_json` drops the scan denominator (§5 S3), so an
uncaptured stdout loses it permanently. The 2026-08-18 run hit exactly this.

Arm C is not part of this run sheet
------------------------------------
Arm C (`KXMVENFLSINGLEGAME` / `KXMVENFLMULTIGAMEEXTENDED`) is registered but
is not given a per-slot command in §7 or §11.6 the way Arms A and D are, and
`tasks/NEXT.md`'s run sheet says "two invocations per slot" and lists only A
and D. Both NFL series returned 0 open rows midweek, and a named `--series`
with no open rows aborts the instrument by design (`EmptySeriesRequested`) --
so Arm C, if it were run, is *expected* to abort. That is recorded in the
registration so an abort is not later read as a failure; it is not a reason to
add a third invocation here.

Overwrite protection is the feature
------------------------------------
`--json`, `--capture` and shell `>` all overwrite unconditionally. A `c1`
slot typed while meaning to run `c2` would silently destroy an earlier
capture -- against a registered rule that permits no sixth capture
(§7: "No sixth capture"). So before any subprocess is started, every target
output path for the requested slot (both arms' `.json` and `.txt`) is checked,
and the whole slot refuses -- nothing is run, nothing is overwritten -- if any
one of them already exists. The refusal names the blocking file.

`--dry-run` runs the same refusal check and prints the exact commands it would
run, so Sunday's operator can preview a slot before typing it for real,
without spending a single Kalshi call.

What this does not do
----------------------
- Does not retry a failed slot. §7: a slot missed by more than 30 minutes is
  recorded missing, not moved -- that is an operator decision, not this
  script's.
- Does not interpret the instrument's exit code as this script's own success
  or failure. `measure_combo_book_presence.py` returns 0 (rows found), 1 (no
  rows chosen) or 2 (`EmptySeriesRequested`) -- all three are registered, valid
  *data* outcomes, not failures of this runner. This script's own non-zero
  exits are reserved for the overwrite refusal and for failing to launch the
  subprocess at all (e.g. a bad `--python`/`--script` path).
- Does not open the cockpit UI, read `/api`, or touch `backend/odds/`. Only
  shell subprocess calls against the two commands above.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_ROOT = Path(__file__).resolve().parents[1]

# §7, §11.6. The slot NAME is the stable identifier used in filenames -- it
# is not the whole date. C5 is the same NFL Sunday, the next UTC date.
SLOT_CLOCK: dict[str, str] = {
    "c1": "15:30Z",
    "c2": "17:30Z",
    "c3": "20:00Z",
    "c4": "23:30Z",
    "c5": "00:45Z (2026-09-14)",
}

DEFAULT_PYTHON = _ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_SCRIPT = _ROOT / "scripts" / "measure_combo_book_presence.py"
DEFAULT_OUT_DIR = _ROOT / "docs" / "measurements"

# §7's series is KXMVECROSSCATEGORY-SHARD1 and nothing else, per Amendment 2
# §12.1's prohibition on defining Arm D as "the shard variants of
# DISCOVERY_SERIES". A literal string, not a lookup that could drift.
ARM_D_SERIES = "KXMVECROSSCATEGORY-SHARD1"


@dataclass(frozen=True)
class ArmInvocation:
    """One arm's command for one slot, and where it writes.

    `argv[0]` is the python executable; the whole list is what `subprocess`
    receives, unquoted -- there is no shell in between to reinterpret it.
    """

    name: str  # "A" or "D", per the registration's own arm letters.
    argv: list[str]
    json_path: Path
    txt_path: Path

    @property
    def output_paths(self) -> tuple[Path, Path]:
        return (self.json_path, self.txt_path)

    def shell_line(self) -> str:
        """How this would read as the `> file 2>&1` shell form, for a human."""
        return " ".join(self.argv) + f" > {self.txt_path} 2>&1"


class UnknownSlot(ValueError):
    """`--slot` was not one of the five registered slot names."""


class OutputAlreadyExists(RuntimeError):
    """A target output file for this slot already exists.

    This is the overwrite-protection guard the whole script exists for. See
    the module docstring's "Overwrite protection is the feature" section --
    `--json` and shell `>` both clobber silently, and the registration permits
    no sixth capture, so a slip that reuses a slot name must refuse loudly
    rather than destroy an earlier capture.
    """


def build_arms(
    slot: str,
    *,
    out_dir: Path,
    script: Path,
    python: Path,
) -> list[ArmInvocation]:
    """The two registered commands for `slot`, Arm A then Arm D.

    Pure and side-effect-free -- it only builds paths and argv lists, so it is
    the part of this script that can be unit-tested without touching a
    filesystem or a subprocess.
    """
    if slot not in SLOT_CLOCK:
        raise UnknownSlot(
            f"unknown slot {slot!r}; must be one of {sorted(SLOT_CLOCK)}"
        )

    python_s = str(python)
    script_s = str(script)

    # §7's exact filenames.
    arm_a_json = out_dir / f"2026-09-13-combo-exit-nfl-sunday-{slot}.json"
    arm_a_txt = out_dir / f"2026-09-13-combo-exit-nfl-sunday-{slot}.txt"
    arm_a = ArmInvocation(
        name="A",
        argv=[
            python_s, script_s,
            "--max-books", "40",
            "--depth", "10",
            "--json", str(arm_a_json),
        ],
        json_path=arm_a_json,
        txt_path=arm_a_txt,
    )

    # §11.6's exact filenames.
    arm_d_json = out_dir / f"2026-09-13-combo-exit-shard1-{slot}.json"
    arm_d_txt = out_dir / f"2026-09-13-combo-exit-shard1-{slot}.txt"
    arm_d = ArmInvocation(
        name="D",
        argv=[
            python_s, script_s,
            "--series", ARM_D_SERIES,
            "--max-books", "25",
            "--depth", "10",
            "--json", str(arm_d_json),
        ],
        json_path=arm_d_json,
        txt_path=arm_d_txt,
    )

    # Arm A then Arm D, per §11.6: "run AFTER §7's Arm A command at the same
    # slot, within 10 minutes of it." Returning them in this order and running
    # them back to back in the same process satisfies that by construction.
    return [arm_a, arm_d]


def check_no_overwrite(arms: Sequence[ArmInvocation]) -> None:
    """Refuse the whole slot if ANY target output file already exists.

    Checked for both arms before either is run, so a `c1`-for-`c2` slip is
    caught before Arm A even starts -- not discovered after Arm A already
    clobbered a real capture and Arm D is about to do the same.
    """
    for arm in arms:
        for path in arm.output_paths:
            if path.exists():
                raise OutputAlreadyExists(
                    f"{path} already exists -- refusing to run slot with "
                    f"Arm {arm.name}. The registration permits no sixth "
                    "capture (§7); delete or move the file first if this is "
                    "a deliberate re-run, and check you typed the slot you "
                    "meant to."
                )


def run_arm(arm: ArmInvocation) -> int:
    """Run one arm, with stdout+stderr captured to its `.txt` exactly as
    `> file 2>&1` would from a shell. Returns the subprocess's exit code."""
    arm.txt_path.parent.mkdir(parents=True, exist_ok=True)
    with arm.txt_path.open("w", encoding="utf-8") as txt:
        result = subprocess.run(arm.argv, stdout=txt, stderr=subprocess.STDOUT)
    return result.returncode


def run_slot(
    slot: str,
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    script: Path = DEFAULT_SCRIPT,
    python: Path = DEFAULT_PYTHON,
    dry_run: bool = False,
) -> int:
    """Refuse-or-run one slot's two arms. Returns this script's exit code.

    Exit codes (distinct from the instrument's own, which are printed but
    never propagated -- see the module docstring):
        0   guard passed; both arms were printed (dry-run) or launched (real)
        3   REFUSED -- a target output file already exists
        4   FAILED to launch a subprocess at all (bad --python/--script path)
    """
    arms = build_arms(slot, out_dir=out_dir, script=script, python=python)

    try:
        check_no_overwrite(arms)
    except OutputAlreadyExists as exc:
        print(f"REFUSED: {exc}")
        return 3

    print(f"slot {slot} ({SLOT_CLOCK[slot]})")
    for arm in arms:
        print(f"  Arm {arm.name}: {arm.shell_line()}")

    if dry_run:
        print("\nDRY RUN -- nothing executed, nothing written.")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        for arm in arms:
            rc = run_arm(arm)
            print(f"  Arm {arm.name} exited {rc} -- see {arm.txt_path}")
    except OSError as exc:
        print(f"FAILED to launch subprocess: {exc}")
        return 4

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slot", required=True, choices=sorted(SLOT_CLOCK),
        help="which of the five registered slots to run (§7, §11.6).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the exact commands without running them or writing "
             "anything. The overwrite guard still runs.",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR,
        help="where capture files are written. Default: the registered "
             "docs/measurements. Override only for testing.",
    )
    parser.add_argument(
        "--script", type=Path, default=DEFAULT_SCRIPT,
        help="path to measure_combo_book_presence.py. Override only for "
             "testing -- Sunday's run must call the real instrument.",
    )
    parser.add_argument(
        "--python", type=Path, default=DEFAULT_PYTHON,
        help="python executable to invoke the instrument with. Default: "
             "this repo's venv, matching the registration's literal command.",
    )
    args = parser.parse_args(argv)

    return run_slot(
        args.slot,
        out_dir=args.out_dir,
        script=args.script,
        python=args.python,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
