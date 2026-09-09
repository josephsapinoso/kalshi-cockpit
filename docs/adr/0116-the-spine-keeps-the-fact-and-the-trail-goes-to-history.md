# ADR 0116 — The spine keeps the corrected fact; the trail of how it was corrected goes to `docs/history/`

Status: accepted
Date: 2026-09-08

## Context

Joe asked for the fat to be cut from `CLAUDE.md`, the unused skills and
agents, the outdated task files and the duplicate lessons. Three audits ran
first. What they found:

- `CLAUDE.md` was 43,936 bytes. One section headed *"The consensus-only signal
  has been measured, and it is negative"* was 26KB — 61% of the file — and
  covered beta, the odds-credit budget, the attention slice, combos, fees and
  all four order paths, mostly as correction narrative: *"this paragraph used
  to say"*, struck-through closed defects, a correction of a correction. About
  17KB classified as history with a verified home already (an ADR, a
  `docs/measurements/` file, or a `timing.py` comment block). Three
  `file:line` citations were stale (`runner.py:684`, `timing.py:1943-2028`,
  `analyse_combo_domination.py:71`), and one paragraph still called the desk
  *"a read surface, not a transaction surface"* sixty lines after the
  paragraph recording two real fills through it.
- Six of the twelve `.claude/agents/` files — `graphic-designer`,
  `ui-designer`, `ux-designer`, `retail-bettor`, `tilt-prone-gambler`,
  `disciplined-gambler` — each had one live citation, five of the six to the
  same document (`docs/reviews/2026-08-21-market-screen-direction.md`), and
  two of them did not load in the session's agent list at all. 34KB of
  definitions for one review eighteen days old.
- `tasks/todo.md` was a build log that stopped on 2026-08-09 and carried the
  hand-collected test counts NEXT.md retired on 2026-09-01, yet `CLAUDE.md`,
  `AGENTS.md` and `start.md` all named it a session-start read.
  `tasks/PHONE.md` had 0 of 24 boxes ticked and every item done or moot.
  `tasks/PROMPT-next-session.md` and `tasks/next-session-prompt.md` were
  paste-in prompts for 2026-08-18 and 2026-08-20 with zero references.
  `tasks/LANES.md`'s generated board was a 2026-08-27 snapshot naming lanes
  that had merged. `tasks/NEXT.md`'s SESSION START box built a paragraph of
  guidance on `/wayfinder`, a skill the installed plugin version does not
  ship.
- `tasks/lessons.md` opened with 4.8KB narrating its own splits — the file
  breaking its own rule 1 at the top of itself — and 11 of its 38 lessons
  duplicated each other, an archived lesson, or a `CLAUDE.md` rule.
- `.claude/skills/kalshi-api/SKILL.md`'s Fees section still said
  `calculate_fee` returns the maximum across candidate models. That hedge was
  retired on 2026-08-14 (ADR 0028). The Codex mirror under `.agents/` was an
  older copy, and `.codex/agents/kalshi-platform.toml` pointed at a
  `.Codex/skills/` path that does not exist.

## Decision

**A spine carries the corrected fact and a citation. The trail of how the
fact got corrected lives where the citation points**, and where no such
place exists, in `docs/history/`.

1. `CLAUDE.md` was rewritten to rules and facts. The pre-cut file is
   preserved verbatim as `docs/history/claude-md-2026-09-08.md`, cited from
   the new preamble. The one 26KB section became five: the signal, the hunt's
   closure (with combos and the cost bars), what the recorder costs, what is
   armed, and what the tool is for. The three stale citations were repointed
   and the read-surface contradiction resolved in favour of the two fills.
   `tests/test_fees.py`'s docstring, which still quoted the retired 52.00%
   bar, was corrected in the same pass.
2. The six one-shot agents were **deleted**, on Joe's word. Their review
   survives in `docs/reviews/` and ADRs 0047, 0061, 0063; the comments in
   `ScoutDesk.tsx`, `market/[ticker]/page.tsx` and `test_bet_direction.py`
   that attribute a rule to one of them are left as provenance. Six agents
   remain — `partner`, `measurement-skeptic`, `pre-registrar`,
   `sharp-bettor`, `runtime-realist`, `kalshi-platform` — which is the set
   the `.codex/` mirror already carried.
3. `tasks/todo.md`, `tasks/PHONE.md` and both prompt files moved verbatim to
   `tasks/archive/` (`todo-2026-08-09.md`, `phone-2026-08-09.md`,
   `prompt-2026-08-17.md`, `prompt-2026-08-19.md`). Session start now reads
   `tasks/NEXT.md` then `tasks/lessons.md`; every pointer at `todo.md` and
   `PHONE.md` outside the record was repointed in the same commit, because
   `start.md` exists to record what happens when one is not.
   `tasks/audit-2026-08-07.md` stays in place with a dated status header —
   two registrations and ADR 0003 cite it by item number.
4. `tasks/NEXT.md`: the seven split-narrative paragraphs in its header moved
   to `tasks/archive/next-split-log.md`; the three closed entries
   (2026-09-07 ×2 and the first 2026-09-08 session) moved to
   `tasks/archive/next-2026-09-08-second.md`, md5-verified, with the index
   block written in the same edit; the SESSION START box was rewritten to
   the rules it carries, and says the `/wayfinder` skill is not installed.
5. `tasks/lessons.md`: the preamble became the three rules; the split
   narratives moved to `tasks/archive/lessons-split-log.md`; seven lessons
   moved verbatim to `tasks/archive/lessons-2026-09-08-dedup.md`, each with
   its reason — three as duplicates or an incident, four as the losing half
   of a merge whose survivor carries a dated merge note. The index was
   regenerated and now has a section pointing at the dedup file. One lesson
   was added: this decision's pattern.
6. `SKILL.md`'s Fees section now states the ADR 0028 position; sections that
   restated `CLAUDE.md` or a module docstring became one-line pointers; the
   `.agents/` mirror is a copy of it again and the `.toml` path is fixed.

## What this does not decide

- Whether `tasks/NEXT.md`'s session index, which grows monotonically and is
  now its largest section, should itself be split. It is 20KB and not a
  problem yet.
- Whether the six open items in `tasks/audit-2026-08-07.md` are still open.
  The header says they have not been re-checked; that is a status pass, not
  this ADR.
- Whether the remaining `docs/adr/` and `docs/measurements/` files carry the
  same inline-correction sediment. They are reached by pointer, not loaded
  every turn, so the cost is different and the decision is separate.

## Verification

`tests/test_session_files_are_readable.py`, `tests/test_combo_book_depth_claims.py`
(the strike-marker guard: a forbidden phrase and its marker left `CLAUDE.md`
together), `tests/test_stale_exit.py`, `tests/test_sweep_timing.py`,
`tests/test_inspect_live_db_modules.py` and `tests/test_fees.py` were run
against the rewritten spine before anything else moved, and the full suite
before the commits. Every moved block was hashed against `git show HEAD:` with
line endings normalised. The agent list a fresh session sees cannot be
verified from inside this one; the next session should see six project agents.
