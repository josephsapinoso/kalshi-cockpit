# Worker inbox

Parallel workers write findings here instead of appending to `tasks/NEXT.md`,
`tasks/lessons.md` or `tasks/audit-2026-08-07.md` — those three are
integrator-only, because every task wants to append to them and the resulting
merges resolve cleanly while reading as nonsense.

One file per lane: `tasks/inbox/<lane>.md`. The integrating session merges them
into the real documents and deletes them.

See `docs/adr/0003-parallel-sessions-and-subagents.md` for the lane definitions
and the shared-state rules.
