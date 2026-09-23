---
description: Start a working session - read NEXT.md, run the boards, hand to partner, execute
---

Start this session the way `tasks/NEXT.md`'s SESSION START box says. The
SessionStart hook has already put the head of `tasks/NEXT.md` and the top of
`tasks/lessons.md` in context; if it is missing, read both files first.

1. Follow the SESSION START box in `tasks/NEXT.md` exactly. It is the
   checklist, and it outranks this file if the two disagree.
2. Re-verify state instead of trusting it: `git status`, `git log origin/main..main`,
   then `.venv\Scripts\python.exe scripts/board.py` and `scripts/lane_board.py`.
3. Check for open PRs a cloud routine may have opened (`gh pr list`). Review
   and merge or close each one per `docs/agents/orchestration.md` before new work.
4. Invoke `partner` with the board and state (CLAUDE.md workflow step 0).
   Execute its dispatch table.
5. Keep going without asking permission to continue. Stop only for a decision
   that is Joe's, and ask it with option buttons.

Focus for this session, if Joe gave one: $ARGUMENTS
