# AGENTS.md

**Read [`CLAUDE.md`](CLAUDE.md). It is the spine, and this file is a pointer to
it rather than a second copy of it.**

Then read `tasks/NEXT.md`, `tasks/todo.md` and `tasks/lessons.md`, in that
order, exactly as `CLAUDE.md` says. All three fit in one read; their history
lives verbatim in `tasks/archive/`.

## Why this file is nine lines instead of two hundred

It used to be a full copy of `CLAUDE.md`, and on 2026-08-15 it was found to be a
**stale** one. It stated the taker break-even bar as **52.00%** when `CLAUDE.md`
had said **51.75%** since 2026-08-14, and it was missing the whole ADR 0028
correction that moved it — the reasoning about `TAKER_COEFFICIENT`, the 0.63
headroom, and the fact that headroom is an upper bound pending H4.

That is this repo's most-repeated failure shape in a new place: **two statements
of one quantity, where the tighter one wins in silence.** A number this project
has already corrected twice was sitting wrong in the file a Codex session reads
first, and nothing would have flagged it — a copy does not report that it has
fallen behind.

So the duplication is removed rather than re-synchronised. Re-synchronising
fixes today's drift and schedules tomorrow's.

## Harness-specific paths

Everything in `CLAUDE.md` applies verbatim. Only the tooling directories differ:

| `CLAUDE.md` says | On this harness |
|---|---|
| `.claude/skills/` | `.agents/skills/` |
| `.claude/agents/` | `.codex/agents/` (same six agents, same instructions, `.toml`) |

**Do not restate any rule, number or citation from `CLAUDE.md` here.** If
something is worth an agent knowing, it belongs in `CLAUDE.md`, where both
harnesses read it.
