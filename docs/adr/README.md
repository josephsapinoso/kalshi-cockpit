# How an ADR is numbered

**This file exists because the rule had no home.** Until 2026-08-27 the ADR
numbering convention lived in exactly three places — a `tasks/lessons.md`
entry, the session-start box of `tasks/NEXT.md`, and the regexes in
`tests/test_parallel_lanes_do_not_collide.py`. Enforcement was stronger than
the documentation, so a lane that came straight to `docs/adr/` and never opened
`tasks/` could not find the rule it was about to break. That is roughly how all
three of the 2026-08-27 collisions happened.

## The shape

    docs/adr/NNNN-kebab-slug.md

with an H1 that declares its own number:

    # 0078 — Title
    # ADR 0078 — Title      (both spellings are in the record; neither is wrong)

A **companion** document deliberately shares its parent's number and says so in
its own first line:

    # Evidence for ADR 0006

`0006-in-play-evidence.md` sits beside `0006-in-play-scope.md` on purpose. The
guard keys on what a document *claims to be*, never on its filename, for
exactly this reason — and that exemption is pinned, because a guard whose first
finding is a false one gets weakened or deleted.

## Do not take the next free number

**Allocate at MERGE time, not at write time.** `ls docs/adr/ | tail` answers
"what was free when I looked", which is a different question from "what is free
now". A lane that runs for hours races every other lane for the whole of it,
and the check has a window exactly as long as the gap between looking and
pushing. This is not hypothetical: ADR 0074 was taken twice, the renumber to
0077 collided too, and both merged **cleanly**, because two lanes writing
`0077-a.md` and `0077-b.md` are different filenames and git has nothing to
conflict on. See `tasks/lessons.md`, the 2026-08-27 entry.

So, in a lane:

    docs/adr/DRAFT-<slug>.md          # no ordinal, nothing to collide on

and the number is taken **in the merge commit, after `git fetch`, as the last
thing before the push**. `tests/test_parallel_lanes_do_not_collide.py` fails if
a `DRAFT-` file reaches the integration branch, which is what makes the
numbering unavoidable at the boundary rather than merely encouraged.

If you would rather number optimistically, that is allowed — but then
`ls docs/adr/ | tail` and
`git show main:backend/store/db.py | grep SCHEMA_VERSION` are **part of the
push**, not part of the planning, and they are re-run after every `git fetch`,
however many times that is.

**Three counters in this repo name global state and can each be allocated
twice:** `SCHEMA_VERSION`, the ADR ordinal, and any migration step number.
None of them is safe to hold across a test run.

## Before you claim anything, read the board

    .venv\Scripts\python.exe scripts/lane_board.py

It reads every worktree and local branch at once and reports what each is
claiming, including uncommitted work — the state no test can see, because a
test only sees the tree it runs in. **It is a snapshot, not a lock, and it
reserves nothing.** `tasks/LANES.md` is where a claim is *stated* for other
lanes to read; the board is how you find out whether the statement is still
true.

## Lane ownership

`docs/adr/0003-parallel-sessions-and-subagents.md` §1 partitions files between
parallel workers. Two clarifications live here because they were settled after
that ADR and a reader arrives at this directory first:

- **A type declaration is owned by whoever owns its producer**, not by the
  frontend lane. `frontend/src/lib/api.ts`'s types must change in the same
  commit as the backend field that fills them; splitting that across two
  workers produces a tree where the API returns a field and the type denies it,
  which is the incoherence §1 exists to prevent.
- **`.env.example` and `fly.live.toml` are integrator-only**, alongside §2's
  list. `.env.example` is the contract (CLAUDE.md, Conventions) and
  `fly.live.toml [env]` is the deployed live config; a lane editing either
  changes what the running machine does without a deploy being the thing that
  decided it.
