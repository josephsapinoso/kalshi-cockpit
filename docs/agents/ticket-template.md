# Ticket template: an `owner:agent` task

Copy-pasteable body for a `type:task` issue dispatched to a lane. See
`docs/agents/orchestration.md` for how it fits into the session loop, and
`docs/adr/0003-parallel-sessions-and-subagents.md` §1–§2 for what "Must not
touch" is enforcing.

## The template

    **Goal**
    <one sentence — what the tree is like after this lands>

    **Done when**
    <a named test the lane runs to prove it, e.g. `tests/test_x.py::TestY::test_claim`,
    or a captured artefact path if there's no test to point at. This line is
    what makes Sonnet safe to dispatch here: a wrong answer is visible,
    because the caller can run the same line and see it fail.>

    **Lane owns**
    <the exact files this ticket may write, nothing broader>

    **Must not touch**
    tasks/NEXT.md, tasks/lessons.md, CLAUDE.md, backend/config.py,
    backend/store/schema.sql, .env.example, fly.live.toml, tasks/LANES.md
    (ADR 0003 §2), plus any money-path file this ticket doesn't own:
    backend/kalshi/*, backend/core/{prices,fees,ev,sizing}.py, the
    order/RFQ/hedge routes.

    **Verification recipe**
    <exact commands, with the absolute venv path, e.g.:>
    C:/Users/josep/Documents/Claude/Projects/kalshi_betting_tool/.venv/Scripts/python.exe -m pytest -q tests/test_x.py
    C:/Users/josep/Documents/Claude/Projects/kalshi_betting_tool/.venv/Scripts/python.exe -m ruff check backend/x.py

    **Report back**
    Branch; Commits; Done-when test and its result; Tests run (counts);
    Mutations (guard -> test that went red); Files needed outside the lane
    (not touched); Not verified; Handoff notes written to inbox (y/n).
    (the `lane-builder` headings — see `.claude/agents/lane-builder.md`)

## Field guidance, one line each

- **Goal** — one sentence, no design discussion. If it needs a second
  sentence, it's a story, not a task.
- **Done when** — a test the lane can run and the caller can re-run
  independently. Never "looks right" or "should work."
- **Lane owns** — a file list, not a directory glob wider than needed. A
  lane that needs two lanes' worth of files is two tickets.
- **Must not touch** — the ADR 0003 §2 list, always, plus whatever
  money-path files this specific ticket doesn't own even if adjacent.
- **Verification recipe** — commands as they will actually be typed,
  including the absolute `.venv` path; a lane worktree has no `.venv` of
  its own.
- **Report back** — the `lane-builder` heading set, so every ticket's
  report is diffable against every other ticket's report.

## Filled example

    **Goal**
    Add a WHERE clause to the scoring index scan so suppressed rows are
    excluded before the candidate loop, not after.

    **Done when**
    `tests/test_scoring.py::TestIndexScan::test_suppressed_rows_never_enter_the_loop`

    **Lane owns**
    backend/scoring.py, tests/test_scoring.py

    **Must not touch**
    tasks/NEXT.md, tasks/lessons.md, CLAUDE.md, backend/config.py,
    backend/store/schema.sql, .env.example, fly.live.toml, tasks/LANES.md,
    backend/kalshi/*, backend/core/{prices,fees,ev,sizing}.py, the
    order/RFQ/hedge routes.

    **Verification recipe**
    C:/Users/josep/Documents/Claude/Projects/kalshi_betting_tool/.venv/Scripts/python.exe -m pytest -q tests/test_scoring.py
    C:/Users/josep/Documents/Claude/Projects/kalshi_betting_tool/.venv/Scripts/python.exe -m ruff check backend/scoring.py

    **Report back**
    Branch; Commits; Done-when test and its result; Tests run (counts);
    Mutations (guard -> test that went red); Files needed outside the lane
    (not touched); Not verified; Handoff notes written to inbox (y/n).

## Creating and linking the ticket

Same shape as `docs/agents/issue-tracker.md`'s "Open a ticket for Joe," with
`type:task`/`owner:agent`/`model:*` labels instead of a `wayfinder:*` one:

    gh issue create --title "<the task, as a sentence>" \
      --label "type:task" --body-file body.md          # prints the URL; note the #NN

    gh api repos/josephsapinoso/kalshi-cockpit/issues/<NN> --jq .id   # the DATABASE id, not NN

    gh api --method POST repos/josephsapinoso/kalshi-cockpit/issues/<STORY-NN>/sub_issues \
      -F sub_issue_id=<database-id>

    gh issue edit <NN> --add-label "type:task,owner:agent,model:sonnet"

The second command's output is the database id needed by the third — not
the `#NN` and not the node_id. The last command's `model:*` value should
match what the dispatch table in `docs/agents/orchestration.md` decided,
before the lane is spawned, not after.
