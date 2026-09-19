# Lane B: scripts/board.py

Delivered `scripts/board.py`, `tests/test_board.py`,
`tests/fixtures/board_issues.json`. 31 tests, ruff clean, mutation pass done
(see the report handed back to the caller for the full list). Notes for
`tasks/NEXT.md` / `tasks/lessons.md`:

## For NEXT.md's SESSION START box

The hand-typed `gh api .../sub_issues` one-liners for the map's frontier
query can be replaced by:

    .venv\Scripts\python.exe scripts/board.py

It walks BOTH #3 (map) and #80 (backlog root) in one pass, prints a
frontier grouped by owner/model, and — new, the hand-typed query never did
this — warns when an open leaf has no owner, when an `owner:agent` leaf is
missing a `model:` label or a `Done when` line in its body, and when a
`tasks/NEXT.md` Still-open item names no ticket besides `#3` (the same decay
`tests/test_a_question_for_joe_has_a_ticket.py` guards, applied a session
earlier — before the item is copied forward again, not after).

## Fact worth recording (lessons.md pattern candidate)

**The real live tree under both roots, as of 2026-09-19, is exactly two
levels deep and every child is a leaf.** All 72 children of #3 and all 5
epics under #80 have `sub_issues_summary.total == 0` — checked both via the
summary field and, for the 5 epics, by calling `/sub_issues` on each
directly to make sure the summary wasn't lying. That means every "a non-leaf
is not on the frontier" and "an owner:agent leaf" test case in
`tests/test_board.py` had to come from the fixture's hand-appended
`synthetic` key — the real capture has none of those shapes yet. If #80's
epics grow stories/tasks underneath them, or anyone starts using
`owner:agent` for real, board.py's untested-on-real-data paths (recursion
past one level, the two agent-leaf warnings) get their first live exercise;
worth a spot-check with `--fixture` swapped for a live run at that point.

## Also true and possibly worth a line somewhere

`gh api .../issues/<n>/sub_issues --paginate` already returns `body` and
`issue_dependencies_summary` on every child — the build brief's "if the
endpoint omits them, fetch per-node" branch is real code in `board.py`
(`_ensure_full_fields`) but is dead on the current API version. Left in
because "the day the shape changes" is exactly the day you don't want to
discover it by a KeyError.

## Not verified

- `fetch_tree`'s actual `gh` subprocess path (the part that is NOT
  `--fixture`) has no test coverage — see `tests/test_board.py`'s own
  module docstring. It was run by hand once, live, to build the fixture, and
  behaved as documented; it is not exercised by pytest.
- Whether `scripts/board.py` needed an entry in `test_has_callers.py`'s
  `DISPOSITIONS` table: the full run (122 passed) did not flag it, so no
  entry was added. If a future session adds one and it complains, that's a
  real finding, not something this lane silently worked around.
