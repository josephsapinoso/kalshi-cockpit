"""A background child of the entrypoint is a liveness signal, not a task.

WHY THIS EXISTS
---------------
`docker/entrypoint.sh` ends in `wait -n`, which returns as soon as **any** job
of that shell exits, and then tears the container down so Fly restarts it. That
is the whole liveness design: uvicorn, Next and the chain runner are each
asserting "if I exit, the container is broken."

Adding a background job that is *supposed* to finish breaks it silently. The
warm-up added on 2026-09-10 runs for about twenty seconds and exits normally;
written as a bare `&` it satisfies `wait -n` on its own success, the teardown
runs, finds every real child alive, falls through to the `else` branch, reports
"FRONTEND exited" and shuts the container down. Fly restarts it, the warm-up
runs again, and the machine crash-loops every twenty seconds while every
process inside it is healthy — with a log line naming the wrong culprit.

It was caught before shipping. This is what makes that repeatable.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **It does not run the script.** This is a shell-shape guard over the text of
  the entrypoint; whether `warm_read_path.py` works is its own question.
- **Nothing about boot time.** That the warm-up is backgrounded is asserted
  here; that backgrounding it is *enough* to keep the boot fast is a live
  measurement, not a unit test.
- It cannot see a job started by a script the entrypoint calls.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
ENTRYPOINT = REPO / "docker" / "entrypoint.sh"


def lines() -> list[str]:
    return ENTRYPOINT.read_text(encoding="utf-8").splitlines()


def code_lines() -> list[tuple[int, str]]:
    """Numbered, comments and blanks dropped, **continuations joined**.

    The join is not tidiness. uvicorn is started as a three-line command whose
    `&` sits on `--timeout-keep-alive 75 &`, a line containing no hint of what
    it launches. Analysing raw lines reports that as an undisowned task and
    demands a `disown` that would make the backend's death invisible — a guard
    whose advice, followed, breaks the thing it guards.
    """
    joined: list[tuple[int, str]] = []
    pending = ""
    start = 0
    for i, raw in enumerate(lines(), start=1):
        stripped = raw.strip()
        if not pending:
            if not stripped or stripped.startswith("#"):
                continue
            start = i
        if stripped.endswith("\\"):
            pending += stripped[:-1].strip() + " "
            continue
        joined.append((start, (pending + stripped).strip()))
        pending = ""
    if pending:
        joined.append((start, pending.strip()))
    return joined


#: A line that backgrounds something: ends in `&`, but not `&&`.
BACKGROUNDED = re.compile(r"(?<!&)&\s*$")

#: The three children whose exit MUST bring the container down. Each is
#: deliberately not disowned.
LIVENESS_CHILDREN = ("uvicorn", "node frontend/server.js", "run_loop.py")


class TestEveryBackgroundJobDeclaresWhichKindItIs:
    def test_each_backgrounded_line_is_a_child_or_is_disowned(self):
        """The whole rule, in one assertion.

        A backgrounded line is either one of the three liveness children, or it
        must be followed by `disown` — there is no third option that leaves
        `wait -n` behaving correctly.
        """
        code = code_lines()
        for idx, (lineno, text) in enumerate(code):
            if not BACKGROUNDED.search(text):
                continue
            if any(child in text for child in LIVENESS_CHILDREN):
                continue
            following = code[idx + 1][1] if idx + 1 < len(code) else ""
            assert following.startswith("disown"), (
                f"entrypoint.sh:{lineno} backgrounds a job that is not one of "
                f"the liveness children and is not disowned:\n    {text}\n"
                "`wait -n` returns when ANY job exits, so a task that finishes "
                "on purpose will tear the container down and blame the "
                "frontend. Add `disown` on the next line."
            )

    def test_the_liveness_children_are_never_disowned(self):
        """The mirror. Disowning uvicorn would make its death invisible and
        leave the container serving frozen prices — the exact failure the
        teardown exists to prevent."""
        code = code_lines()
        for idx, (lineno, text) in enumerate(code):
            if not any(child in text for child in LIVENESS_CHILDREN):
                continue
            if not BACKGROUNDED.search(text):
                continue
            following = code[idx + 1][1] if idx + 1 < len(code) else ""
            assert not following.startswith("disown"), (
                f"entrypoint.sh:{lineno} disowns a liveness child, so its death "
                f"no longer restarts the container:\n    {text}"
            )

    def test_the_warm_up_is_backgrounded_and_disowned(self):
        """The specific case that motivated this file."""
        text = ENTRYPOINT.read_text(encoding="utf-8")
        assert "scripts/warm_read_path.py" in text
        match = re.search(
            r"python scripts/warm_read_path\.py[^\n]*&\n\s*disown", text
        )
        assert match is not None, (
            "the warm-up is no longer `& disown`; if it is backgrounded "
            "without disown it crash-loops the container every ~20s"
        )

    def test_wait_n_is_still_what_ends_the_script(self):
        """If the liveness mechanism changes, this whole guard needs rewriting
        rather than silently passing against a file it no longer describes."""
        assert "wait -n" in ENTRYPOINT.read_text(encoding="utf-8")


class TestTheHazardIsWrittenDown:
    def test_the_comment_explains_why_disown_is_there(self):
        """`disown` reads like a tidying detail. Without the reason beside it,
        the next person removes it and gets a crash loop that blames the
        frontend."""
        text = ENTRYPOINT.read_text(encoding="utf-8")
        assert "disown" in text
        assert "crash-loop" in text or "crash loop" in text
        # Fragments: the entrypoint wraps its prose across comment lines, so a
        # substring spanning a line break fails on formatting alone.
        assert "is a liveness" in text and "signal, not a task" in text


@pytest.mark.parametrize("child", LIVENESS_CHILDREN)
def test_each_liveness_child_is_actually_started(child: str):
    """Guards the list above against going stale: if a child is renamed, the
    rule stops covering it and this says so rather than passing vacuously."""
    assert child in ENTRYPOINT.read_text(encoding="utf-8")
