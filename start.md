# start.md — this is not the session-start door

The session-start instruction lives in **`CLAUDE.md`** (the "Workflow" section)
and the current state lives in **`tasks/NEXT.md`**. Read those, in that order,
then `tasks/todo.md` and `tasks/lessons.md`.

This file used to be a third copy of that instruction. It was last maintained
on 2026-08-15 (`dafefaf`) and nothing linked to it afterwards — zero references
from `CLAUDE.md`, `tasks/NEXT.md`, `tasks/todo.md`, `tasks/lessons.md` or
`README.md` — so it went on asserting things the record had since overturned
(that the Scout was "TABLED BY JOE. Do not start it unasked" and that
`BILLED_PATH_CALL_SITES` "cannot be satisfied by editing a list"; ADR 0060
switched the Scout desk on 2026-08-21, `backend/agents/scout_desk.py` is an
entry in that allowlist, and the "hypothetical on-demand tap" it priced is
the deployed `POST /api/scout/{ticker}`). A stale copy read confidently is
worse than none, which is why the content was removed rather than refreshed.

The file is kept so a paste-open of `start.md` lands here instead of on a
missing file. Do not add instructions to it.
