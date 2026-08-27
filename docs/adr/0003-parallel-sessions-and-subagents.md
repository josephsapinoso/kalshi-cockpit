# 0003 — Running sessions and subagents in parallel

**Status:** accepted, 2026-08-07

## Context

Work on this repo is bounded by one session's context window, and the backlog is
mostly independent module-scoped defects. Running several workers at once is the
obvious speed-up. The obvious speed-up is also the obvious way to lose work.

The conflicts here are not evenly distributed. Most of the codebase partitions
cleanly; a handful of files are touched by *every* piece of work and will
collide every time.

## Decision

### 1. Partition by file ownership, not by task

Assign each worker a **lane** — a set of files it alone may write. Lanes that
have proven independent:

| Lane | Owns |
|---|---|
| model | `backend/model/*`, `tests/test_model.py` |
| correlation / builder | `backend/core/{correlation,parlay,teaser}.py`, `tests/test_builder.py` |
| measurement | `backend/analysis/*`, `tests/test_{validate,clv,marts}.py` |
| warehouse | `warehouse/**` |
| ingest | `backend/kalshi/*`, `backend/odds/*`, their tests |
| runner / gate | `backend/{runner,scoring,scheduler,gate,engine}.py`, their tests |
| frontend | `frontend/**` |

A task that needs two lanes is one task, not two workers.

> **Amended 2026-08-27, and the amendment is that the table went stale rather
> than that it was violated.** A lane was found writing across `ingest`,
> `frontend` and config at once, and the first reading was that it had broken
> §1. It had not: `backend/parlays.py` and `backend/core/ladder.py` appear in
> **no lane above at all**, because this table was written 2026-08-07 for a
> codebase with no parlay desk. You cannot violate a partition that does not
> cover the files. Add a row:
>
> | parlay desk | `backend/parlays.py`, `backend/core/{ladder,parlay}.py`, their tests |
>
> **And one row of the table does not bind where it appears to.** A TypeScript
> type declaration is owned by **whoever owns its producer**, not by the
> `frontend` lane. `frontend/src/lib/api.ts`'s types must change in the same
> commit as the backend field that fills them; splitting that across two
> workers produces a tree where the API returns a field and the type denies it
> — which is the incoherence §1 exists to prevent, so enforcing §1 literally
> there would cause the harm. Recorded in `docs/adr/README.md` too, because a
> lane arrives at that directory before it arrives here.
>
> **The correct partition for that lane was at the commit boundary, not the
> worker boundary**: a spend change (stop buying a feed) and a product change
> (admit prop markets to cards) are two commits by one worker, not two workers
> on one file's consumers.

### 2. Three files are integrator-only

`tasks/NEXT.md`, `tasks/lessons.md`, `tasks/audit-2026-08-07.md`.

Every piece of work wants to append to these, so they conflict every time and
the conflicts are semantic — two workers appending different lessons produce a
merge that resolves cleanly and reads as nonsense. **Workers write to
`tasks/inbox/<lane>.md` instead**; the integrating session merges and deletes.

`CLAUDE.md`, `backend/config.py` and `backend/store/schema.sql` are also
integrator-only: they are read by everything, and a schema change under a
worker's feet invalidates its tests silently.

> **Added 2026-08-27: `.env.example`, `fly.live.toml` and `tasks/LANES.md`.**
> Not because a lane conflicted on them — nothing had — but because
> `.env.example` is the contract (CLAUDE.md, Conventions) and `fly.live.toml
> [env]` is the *deployed live config*, so a lane editing either changes what
> the running machine does without a deploy having been the thing that decided
> it. `tasks/LANES.md` is generated in the integration worktree only; a lane
> regenerating it recreates exactly the append-conflict this section exists to
> prevent. The rule should exist before the edit that isn't harmless.

### 3. Use git worktrees for anything that edits code

`Agent(isolation: "worktree")`. Without it, two agents share one working tree and
the second one's `Edit` lands on a file the first is mid-way through changing —
with no conflict marker, because git never sees it.

### 4. Exactly one worker touches shared external state

These are not merge conflicts; they are real-world collisions no VCS will catch.

- **Deploys.** The `Deploy` workflow is serialised by `concurrency: deploy-<instance>`,
  so two runs queue rather than interleave — but two workers deploying different
  commits still produces a last-writer-wins race on what is actually live. Only
  the integrator deploys.
- **The Odds API budget.** ~16 credits/day, 6 per sweep. Two workers each running
  a live sweep burns the day's allowance in minutes. **No worker runs
  `scripts/run_chain.py` or `run_loop.py` without `--no-odds`.**

  > **Both figures are stale as of 2026-08-20, and the decision is not.** The
  > deployed sweep costs **2** (`fly.live.toml` sets `ODDS_MARKETS = "h2h"` and
  > `ODDS_REGIONS = "us,eu"`; `odds/budget.py:68` multiplies them) against a
  > **600**/day, 13,000/month ceiling (`fly.live.toml:214`, `:220`). The 16 was
  > `ODDS_DAILY_CREDIT_BUDGET`'s code default (`config.py:253`), never a
  > measured rate. Noted here rather than edited above because an ADR records
  > what was decided and when — but these two numbers were copied out of this
  > line into `backend/live.py`'s docstring and read as sourced there for
  > months, so the correction belongs beside the source as well as at the copy.
  > The decision itself — one worker owns the odds path — is unaffected and
  > stands: it is about contention, not about the size of the allowance.
- **`data/`** — the local SQLite database and Parquet lake. Gitignored, so it is
  invisible to merge, and `publish` + `dbt build` overwrite it wholesale. Give
  each worker its own path, or let only the warehouse lane touch it.
- **The live instance.** One runner, one volume. Never two.

### 5. Every worker reports what it could not own

A worker that needed a file outside its lane must say so rather than reaching for
it. That report is the integrator's merge list, and it is the only signal that
the partition was wrong.

## Consequences

Serial work stays correct by default; parallel work is correct only if the lanes
hold. The failure mode to watch for is a worker silently succeeding on a stale
copy — which is why worktrees are mandatory rather than advisory, and why the
integrator re-runs the full suite after merging rather than trusting each
worker's green result.

The measurement guards make this safer than it would otherwise be: `pytest` and
`dbt build` both have to pass on the merged tree, and every guard in this repo
is verified by disabling it, so a merge that quietly drops one shows up as a
test that no longer fails when it should.
