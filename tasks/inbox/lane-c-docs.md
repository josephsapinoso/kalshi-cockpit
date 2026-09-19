# Lane C — docs — handoff

Four files delivered plus this note. Nothing outside the assigned list was
touched.

## Delivered

- `.claude/agents/fact-scout.md` — Haiku-tier, read-only, lookup-scout's
  cheaper sibling.
- `.claude/agents/lane-builder.md` — Sonnet-tier worktree builder, carries
  the lane protocol (toolchain paths, file ownership, DRAFT- ADRs, mutation
  verification, report shape).
- `docs/agents/orchestration.md` — the main-session dispatch loop and the
  model routing table extending `partner.md` rule 3.
- `docs/agents/ticket-template.md` — the `owner:agent` task body template,
  filled example, and the `gh` commands to create and link one.

## One correction against the brief, worth flagging

The brief's session-loop step 1 named `scripts/board.py` as "the generated
frontier," alongside `scripts/lane_board.py`. I checked the tree:
`scripts/board.py` **does not exist**. `scripts/lane_board.py` exists and
does something different — it's the worktree/branch collision detector from
ADR 0003 §6 (regenerates `tasks/LANES.md`), not a ticket-frontier generator.

I did not invent a second script to fill the gap. `docs/agents/orchestration.md`
step 1 instead points at the frontier query already documented in
`docs/agents/issue-tracker.md` (`gh issue list` scoped to the map's/backlog
root's open sub-issues, dropping blocked or assigned ones) and says
explicitly that no generated board file exists for tickets today. If a
frontier-generating script gets built later, that's the line to update.

Everything else in the brief checked out against the repo as written:

- `#3` (wayfinder map) and `#80` (`Engineering backlog`, `backlog:root`)
  both exist via `gh issue view`.
- The labels `type:epic/story/task`, `owner:main/agent/joe`,
  `model:haiku/sonnet/opus`, and the `wayfinder:*` set all already exist
  (`gh label list`) — this infrastructure is real, not aspirational.
- `.claude/agents/lookup-scout.md`, `partner.md` rule 3, ADR 0003, and
  `docs/agents/issue-tracker.md` were read in full before writing, per the
  brief's instruction to match voice and format.

## Not verified

No `gh` writes were made (per the "no gh write" rule for a docs lane and
the money-path/config caution generally) beyond the read-only `gh issue
view`/`gh label list` calls used to check the brief's claims. No tests
apply to markdown-only docs; nothing here changes runtime behavior.

## Branch / commits

Branch: current worktree branch (see `git branch --show-current` — this is
`.claude/worktrees/agent-af85b8496e057f394`'s own branch, not renamed by
this lane).

Commits, one per file, in order:
1. `Add fact-scout, a Haiku-tier read-only lookup agent`
2. `Add lane-builder, a Sonnet worktree builder for single tickets`
3. `Add docs/agents/orchestration.md, the main-session dispatch loop`
4. `Add docs/agents/ticket-template.md, the owner:agent task body`
