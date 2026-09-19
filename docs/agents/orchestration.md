# Orchestrating from the main session

How the main session turns a backlog into dispatched work and back into a
merged tree. `docs/adr/0003-parallel-sessions-and-subagents.md` decides *how
lanes partition files*; this document decides *what gets dispatched, to
which agent, on which model, and how it comes back*.

## One queue

Every open item is a GitHub ticket, under one of two roots:

- **`#3`** — the wayfinder map, `wayfinder:map`, for decisions only Joe can
  make (a "Question for Joe" per CLAUDE.md workflow step 7).
- **`#80`** — `Engineering backlog`, labelled `backlog:root`, for build work.

`tasks/NEXT.md`'s Still-open section is **pointers only** — `#NN — one line`
— never the ticket's content restated. `tests/test_a_question_for_joe_has_a_ticket.py`
enforces this for Joe-questions specifically: a marker without a ticket
number, or citing `#3` itself instead of a real sub-issue, fails the test.

**Tree shape**, built with GitHub's native sub-issues:

    root (#3 or #80)
      -> type:epic   (a theme)
        -> type:story  (a deliverable with a checkable Done-when)
          -> type:task   (one unit of work for one agent or the main session)

Blocking uses GitHub's **native issue dependencies**, not a text convention —
see `docs/agents/issue-tracker.md` for the exact `gh api` calls. A ticket is
unblocked when every blocker is closed.

**Labels:**

- `type:epic` / `type:story` / `type:task` — position in the tree.
- `owner:main` / `owner:agent` / `owner:joe` — who executes it. `owner:agent`
  always carries a `model:*` label alongside it; `owner:main` and `owner:joe`
  never do, because the routing question doesn't apply to them.
- `model:haiku` / `model:sonnet` / `model:opus` — only meaningful on
  `owner:agent` tickets.
- `wayfinder:grilling` / `wayfinder:research` / `wayfinder:prototype` — all
  imply `owner:joe`: a decision he makes in conversation, a fact that must
  be surfaced before he can decide, or something he needs to react to.

## Session loop

1. **Read state.** `tasks/NEXT.md`'s latest entry, the top two entries of
   `tasks/lessons.md`, `git status`, then the two generated boards:

       .venv\Scripts\python.exe scripts/board.py        # the ticket frontier
       .venv\Scripts\python.exe scripts/lane_board.py   # worktrees and claims

   `board.py` walks map #3 and backlog root #80 through their sub-issues and
   prints the tree, the FRONTIER (open, unassigned, unblocked leaves grouped
   by owner then model) and WARNINGS (a leaf with no `owner:`, an agent leaf
   with no `model:` or no **Done when** line, a Still-open item with no
   ticket). Exit 0 clean, 1 warnings, 3 unreadable — an unreadable board is
   never reported as empty. `lane_board.py` is the only thing that sees every
   worktree at once, uncommitted work included; both are snapshots, not
   locks, so re-run them before claiming anything and again before pushing.
2. **Hand the board to `partner`.** Give it what's open, what landed, what's
   blocked; it returns a ranked list plus a dispatch table — ticket, agent,
   model, lane files. Execute that plan; show Joe the result. `partner` owns
   priority, not correctness (its own frontmatter).
3. **Dispatch.**
   - **Claim first**, before any work starts: `gh issue edit N --add-assignee @me`
     plus a comment naming the lane, the model, and the date. This is the
     session's first write on that ticket, per `docs/agents/issue-tracker.md`.
   - **Scouts need no worktree** — `fact-scout` and `lookup-scout` are
     read-only and share the main tree safely.
   - **Builders always get `isolation: "worktree"`**, spawned as
     `lane-builder`, per `docs/adr/0003-parallel-sessions-and-subagents.md`
     §3: without a worktree, a second agent's `Edit` can land on a file the
     first is mid-edit on, with no conflict marker, because git never sees
     the collision.
   - **Cap 2–3 concurrent build lanes** (ADR 0003 §6: collision risk scales
     with *pairs*, so three lanes carry three times the surface of two, not
     one and a half). Scouts are read-only and uncapped.
4. **Integrate.** Only the main session merges. At the merge boundary, after
   `git fetch` and a fresh `lane_board.py` read:
   - number any `DRAFT-` ADR (`docs/adr/README.md`);
   - run the **full** suite once, on the merged tree — a lane's green run
     only ever covered its own worktree, never the merge;
   - close the ticket with the merge sha;
   - only then remove the worktree. A merged lane is not a finished lane
     until its agent has actually reported back — removing the worktree
     first destroys the evidence if something needs re-checking.
5. **Close the session.** A `tasks/NEXT.md` entry naming what happened
   (pointers, not restated content), any lessons as *patterns* not
   incidents, push, and wait for CI before pushing again
   (`tasks/lessons.md`: a new push cancels the in-flight run, and a
   cancelled run verifies nothing).

## Model routing table

- **Haiku — read-only facts.** Inventories, greps, counts, citation checks,
  "does X exist," "is Y called." `fact-scout`; `Explore` for broad file
  location. A wrong answer here is cheap because it's a fact someone else
  can re-check in seconds.
- **Sonnet — a build whose ticket names its test.** Also: call-path traces,
  reading a config across environments, summarising what a module does,
  drafting an ADR for main to number, a mutation pass, frontend work built
  against a written spec. `lane-builder`, `lookup-scout`. **The test is not
  difficulty, it's whether the answer has a checkable shape** — if a wrong
  answer would be *visible* to whoever reads it, Sonnet is fine, because
  the error surfaces on its own.
- **Opus / main only** — never delegated:
  - `backend/kalshi/*`, `backend/core/{prices,fees,ev,sizing}.py`, the
    order/RFQ/hedge money paths.
  - `backend/store/schema.sql`, `backend/config.py`, `CLAUDE.md`,
    `fly.live.toml`.
  - Every ADR decision, every measurement write-up, every diagnosis whose
    symptom and cause agree too neatly.
  - Every merge, every deploy.
  - The reasoning: a wrong answer here would be *invisible* and would
    enter the record as fact — the exact failure mode the measurement
    rules in `CLAUDE.md` exist to catch.
- **The six named judgement agents** — `partner`, `measurement-skeptic`,
  `pre-registrar`, `kalshi-platform`, `runtime-realist`, `sharp-bettor` —
  are spawned with **no `model` argument, ever**. Their definition files
  already set model and effort deliberately (the 2026-09-09 effort review:
  none of them is lookup-shaped, because each one's completion criterion is
  a judgement). A `model` argument on the spawn call *overrides the agent
  file*, so passing `sonnet` there doesn't save money — it quietly demotes
  a reviewer Joe is relying on to catch you.

Rule of thumb, from `partner.md`: **Sonnet where a wrong answer is visible,
Opus where it would be invisible and enter the record.**

## What a brief contains

See `docs/agents/ticket-template.md` for the full shape. A ticket dispatched
to `lane-builder` must name its **Done when** test before the lane starts —
that line is what makes Sonnet safe to use, because it turns "did this work"
into something the ticket itself can check.

## What the main session never delegates

The Opus/main list above, restated as a checklist: money-path code, schema,
config, `CLAUDE.md`, ADR decisions, measurement write-ups, diagnoses,
merges, deploys. If a ticket touches any of these, it is `owner:main` — not
`owner:agent` with `model:opus`, because the point isn't the model, it's
that main holds the context (session state, what Joe has already ruled on,
the rest of the merged tree) that a fresh agent starts without.

## What this does not establish

- **The board is a snapshot, not a lock.** `lane_board.py` reserves nothing;
  two sessions can read it clean and still collide if they act on it at the
  same moment.
- **A green lane is not a merged tree.** A lane's own test run only ever
  covered its own worktree; only the full suite on the merged tree, step 4
  above, means the integration is sound.
- **Nothing enforces model routing but the reviewer reading the spawn
  call.** There is no guard that fails a build if a judgement agent got
  spawned with a `model` override, or if `owner:agent` work landed on
  `owner:main`'s list. This document states the rule; a human or an agent
  reading the dispatch has to actually apply it.
