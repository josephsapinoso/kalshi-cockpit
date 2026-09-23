"""Tests for `scripts/session_context.py`, the SessionStart hook's brief.

What this does not establish
-----------------------------
- That Claude Code actually runs the hook. That is `.claude/settings.json`'s
  job and is only observable by starting a session; `TestTheHookIsWired`
  checks the file names this script, nothing more.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.session_context import build, head_through_entries

ROOT = Path(__file__).resolve().parent.parent

NEXT = """# Next

box text

## 2026-09-23 (second) newest
newest body

## 2026-09-22 older
older body
"""

LESSONS = """# Lessons

## 2026-09-23 - one
a

## 2026-09-22 - two
b

## 2026-09-21 - three
c
"""


def _repo(tmp_path: Path, next_md: str = NEXT, lessons: str = LESSONS) -> Path:
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "NEXT.md").write_bytes(next_md.encode("utf-8"))
    (tmp_path / "tasks" / "lessons.md").write_bytes(lessons.encode("utf-8"))
    return tmp_path


class TestTheBriefIsTheHeadOnly:
    def test_next_keeps_the_box_and_the_latest_entry_only(self, tmp_path):
        out = build(_repo(tmp_path))
        assert "box text" in out
        assert "newest body" in out
        assert "older body" not in out

    def test_lessons_keeps_the_top_two_entries(self, tmp_path):
        out = build(_repo(tmp_path))
        assert "## 2026-09-23 - one" in out
        assert "## 2026-09-22 - two" in out
        assert "three" not in out

    def test_a_file_with_fewer_entries_is_returned_whole(self):
        assert head_through_entries("# x\n## 2026 a\n", 3) == "# x\n## 2026 a\n"


class TestItNeverFailsSilently:
    def test_a_missing_file_is_named_not_skipped(self, tmp_path):
        (tmp_path / "tasks").mkdir()
        out = build(tmp_path)
        assert "tasks/NEXT.md: unreadable" in out

    def test_an_oversized_brief_is_cut_and_says_so(self, tmp_path):
        out = build(_repo(tmp_path), max_chars=40)
        assert out.endswith("read the files directly]\n")

    def test_the_real_brief_fits_under_the_cap_today(self):
        out = build(ROOT)
        assert "[truncated" not in out
        assert "## SESSION START" in out


class TestTheHookIsWired:
    def test_settings_run_this_script_on_session_start(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        groups = settings["hooks"]["SessionStart"]
        commands = [h["command"] for g in groups for h in g["hooks"]]
        assert any("scripts/session_context.py" in c for c in commands)
