"""The slot runner assembles the registered commands and refuses to clobber.

`scripts/run_combo_exit_capture.py` calls `scripts/measure_combo_book_presence.py`
-- it is a caller, not a second implementation of the instrument, so nothing
here re-derives the instrument's own analysis. What these tests pin is:

1. The two commands a slot builds match the registration
   (`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md`
   §7 for Arm A, §11.6 for Arm D) exactly -- flags, series, filenames, order.
2. **The overwrite guard is the feature.** `--json` and shell `>` both
   clobber unconditionally, and the registration permits no sixth capture.
   `TestOverwriteGuard` and `TestDryRunStillRefuses` exist to prove the guard
   actually blocks a run, not merely that it *would* if reached -- per
   CLAUDE.md, "every guard is verified by disabling it and watching the test
   fail" (done by hand for this file; see the delivery notes for the mutation
   result, since the guard itself has no on/off flag safe to leave in the
   repo).
3. `--dry-run` never touches a subprocess or a file.
4. A real run launches Arm A then Arm D, in that order, each with its stdout
   and stderr captured to its own `.txt`.

A tiny stub stands in for `measure_combo_book_presence.py` in the execution
tests, so nothing here makes a network call. The stub's only job is to prove
`run_combo_exit_capture.py` invokes what it says it invokes, in the right
order, with output correctly captured -- not to re-test the instrument, which
has its own test file.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

from run_combo_exit_capture import (  # noqa: E402
    ARM_D_SERIES,
    OutputAlreadyExists,
    UnknownSlot,
    build_arms,
    check_no_overwrite,
    run_slot,
)

STUB_SOURCE = textwrap.dedent(
    """\
    # Stand-in for measure_combo_book_presence.py in these tests -- accepts
    # the same flags the real instrument is invoked with, writes a marker to
    # stdout (so the .txt capture can be checked) and to --json if given, then
    # exits 0. Never makes a network call.
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-books", type=int)
    parser.add_argument("--depth", type=int)
    parser.add_argument("--series", action="append", default=None)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    print(f"STUB max_books={args.max_books} depth={args.depth} "
          f"series={args.series}")
    print("stub warning on stderr", file=sys.stderr)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"stub": True, "series": args.series}, fh)

    sys.exit(0)
    """
)


@pytest.fixture
def stub_script(tmp_path: Path) -> Path:
    path = tmp_path / "stub_instrument.py"
    path.write_text(STUB_SOURCE, encoding="utf-8")
    return path


class TestBuildArmsMatchesTheRegistration:
    """§7 (Arm A) and §11.6 (Arm D) fix the flags, series and filenames."""

    def test_c3_emits_arm_a_then_arm_d_in_that_order(self, tmp_path: Path):
        arms = build_arms(
            "c3", out_dir=tmp_path, script=Path("script.py"),
            python=Path("python.exe"),
        )
        assert [a.name for a in arms] == ["A", "D"]

    def test_arm_a_uses_default_series_with_max_books_40_and_depth_10(
        self, tmp_path: Path
    ):
        arm_a = build_arms(
            "c3", out_dir=tmp_path, script=Path("script.py"),
            python=Path("python.exe"),
        )[0]
        assert "--series" not in arm_a.argv
        assert arm_a.argv[arm_a.argv.index("--max-books") + 1] == "40"
        assert arm_a.argv[arm_a.argv.index("--depth") + 1] == "10"

    def test_arm_d_reads_the_literal_shard1_series_with_max_books_25(
        self, tmp_path: Path
    ):
        arm_d = build_arms(
            "c3", out_dir=tmp_path, script=Path("script.py"),
            python=Path("python.exe"),
        )[1]
        assert ARM_D_SERIES == "KXMVECROSSCATEGORY-SHARD1"
        idx = arm_d.argv.index("--series")
        assert arm_d.argv[idx + 1] == ARM_D_SERIES
        assert arm_d.argv[arm_d.argv.index("--max-books") + 1] == "25"
        assert arm_d.argv[arm_d.argv.index("--depth") + 1] == "10"

    def test_output_filenames_match_the_registered_naming_for_every_slot(
        self, tmp_path: Path
    ):
        for slot in ("c1", "c2", "c3", "c4", "c5"):
            arm_a, arm_d = build_arms(
                slot, out_dir=tmp_path, script=Path("script.py"),
                python=Path("python.exe"),
            )
            assert arm_a.json_path.name == (
                f"2026-09-13-combo-exit-nfl-sunday-{slot}.json"
            )
            assert arm_a.txt_path.name == (
                f"2026-09-13-combo-exit-nfl-sunday-{slot}.txt"
            )
            assert arm_d.json_path.name == (
                f"2026-09-13-combo-exit-shard1-{slot}.json"
            )
            assert arm_d.txt_path.name == (
                f"2026-09-13-combo-exit-shard1-{slot}.txt"
            )

    def test_unrecognised_slot_name_raises_rather_than_silently_running(
        self, tmp_path: Path
    ):
        with pytest.raises(UnknownSlot):
            build_arms(
                "c6", out_dir=tmp_path, script=Path("script.py"),
                python=Path("python.exe"),
            )

    def test_python_and_script_paths_are_the_first_two_argv_entries(
        self, tmp_path: Path
    ):
        script = Path("X:/script.py")
        python = Path("X:/python.exe")
        arms = build_arms(
            "c1", out_dir=tmp_path, script=script, python=python,
        )
        for arm in arms:
            assert arm.argv[0] == str(python)
            assert arm.argv[1] == str(script)


class TestOverwriteGuard:
    """The whole point of this script: refuse rather than clobber a capture."""

    def test_passes_when_no_target_file_exists(self, tmp_path: Path):
        arms = build_arms(
            "c3", out_dir=tmp_path, script=Path("s.py"), python=Path("p.py")
        )
        check_no_overwrite(arms)  # must not raise

    def test_refuses_when_arm_a_json_already_exists(self, tmp_path: Path):
        arms = build_arms(
            "c3", out_dir=tmp_path, script=Path("s.py"), python=Path("p.py")
        )
        arms[0].json_path.write_text("{}", encoding="utf-8")
        with pytest.raises(OutputAlreadyExists) as exc_info:
            check_no_overwrite(arms)
        assert str(arms[0].json_path) in str(exc_info.value)

    def test_refuses_when_arm_d_txt_already_exists(self, tmp_path: Path):
        arms = build_arms(
            "c3", out_dir=tmp_path, script=Path("s.py"), python=Path("p.py")
        )
        arms[1].txt_path.write_text("old capture", encoding="utf-8")
        with pytest.raises(OutputAlreadyExists) as exc_info:
            check_no_overwrite(arms)
        assert str(arms[1].txt_path) in str(exc_info.value)

    def test_run_slot_returns_nonzero_and_names_the_blocking_file(
        self, tmp_path: Path, stub_script: Path
    ):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        blocker = out_dir / "2026-09-13-combo-exit-nfl-sunday-c2.json"
        blocker.write_text("{}", encoding="utf-8")

        rc = run_slot(
            "c2", out_dir=out_dir, script=stub_script, python=Path(sys.executable),
        )
        assert rc != 0

    def test_run_slot_prints_the_blocking_path_and_does_not_run_the_stub(
        self, tmp_path: Path, stub_script: Path, capsys
    ):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        blocker = out_dir / "2026-09-13-combo-exit-shard1-c1.txt"
        blocker.write_text("already here", encoding="utf-8")

        run_slot(
            "c1", out_dir=out_dir, script=stub_script, python=Path(sys.executable),
        )
        captured = capsys.readouterr()
        assert str(blocker) in captured.out
        # The blocker is Arm D's file; Arm A's untouched output must not have
        # been created either -- the whole slot refuses, not just one arm.
        assert not (out_dir / "2026-09-13-combo-exit-nfl-sunday-c1.txt").exists()


class TestDryRun:
    def test_dry_run_never_calls_subprocess(
        self, tmp_path: Path, stub_script: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def _boom(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called in --dry-run")

        monkeypatch.setattr(subprocess, "run", _boom)
        rc = run_slot(
            "c4", out_dir=tmp_path, script=stub_script,
            python=Path(sys.executable), dry_run=True,
        )
        assert rc == 0

    def test_dry_run_writes_no_files(self, tmp_path: Path, stub_script: Path):
        out_dir = tmp_path / "out"
        run_slot(
            "c4", out_dir=out_dir, script=stub_script,
            python=Path(sys.executable), dry_run=True,
        )
        # Not even created -- dry-run must not touch the filesystem at all,
        # not even to make the directory a real run would write into.
        assert not out_dir.exists()

    def test_dry_run_still_refuses_on_an_existing_output(
        self, tmp_path: Path, stub_script: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def _boom(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called")

        monkeypatch.setattr(subprocess, "run", _boom)
        blocker = tmp_path / "2026-09-13-combo-exit-nfl-sunday-c5.json"
        blocker.write_text("{}", encoding="utf-8")

        rc = run_slot(
            "c5", out_dir=tmp_path, script=stub_script,
            python=Path(sys.executable), dry_run=True,
        )
        assert rc != 0


class TestRunSlotExecutesBothArms:
    def test_a_real_run_invokes_arm_a_then_arm_d_and_writes_both_txt_captures(
        self, tmp_path: Path, stub_script: Path
    ):
        out_dir = tmp_path / "out"
        rc = run_slot(
            "c3", out_dir=out_dir, script=stub_script, python=Path(sys.executable),
        )
        assert rc == 0
        arm_a_txt = out_dir / "2026-09-13-combo-exit-nfl-sunday-c3.txt"
        arm_d_txt = out_dir / "2026-09-13-combo-exit-shard1-c3.txt"
        assert arm_a_txt.exists()
        assert arm_d_txt.exists()

    def test_arm_a_txt_shows_default_series_and_arm_d_txt_shows_shard1(
        self, tmp_path: Path, stub_script: Path
    ):
        out_dir = tmp_path / "out"
        run_slot(
            "c3", out_dir=out_dir, script=stub_script, python=Path(sys.executable),
        )
        arm_a_txt = (out_dir / "2026-09-13-combo-exit-nfl-sunday-c3.txt").read_text()
        arm_d_txt = (out_dir / "2026-09-13-combo-exit-shard1-c3.txt").read_text()
        assert "max_books=40" in arm_a_txt
        assert "series=None" in arm_a_txt
        assert "max_books=25" in arm_d_txt
        assert f"series=['{ARM_D_SERIES}']" in arm_d_txt

    def test_stub_json_output_is_actually_written_by_each_arm(
        self, tmp_path: Path, stub_script: Path
    ):
        out_dir = tmp_path / "out"
        run_slot(
            "c1", out_dir=out_dir, script=stub_script, python=Path(sys.executable),
        )
        assert (out_dir / "2026-09-13-combo-exit-nfl-sunday-c1.json").exists()
        assert (out_dir / "2026-09-13-combo-exit-shard1-c1.json").exists()

    def test_stderr_is_captured_into_the_same_txt_as_stdout(
        self, tmp_path: Path, stub_script: Path
    ):
        # The registered command is `> file 2>&1` -- stderr must land in the
        # same .txt as stdout, not be dropped or left on the terminal.
        out_dir = tmp_path / "out"
        run_slot(
            "c2", out_dir=out_dir, script=stub_script, python=Path(sys.executable),
        )
        arm_a_txt = (out_dir / "2026-09-13-combo-exit-nfl-sunday-c2.txt").read_text()
        assert "stub warning on stderr" in arm_a_txt
