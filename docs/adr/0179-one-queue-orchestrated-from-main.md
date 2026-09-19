# ADR 0179 — One queue, orchestrated from the main session

**Status:** Accepted
**Date:** 2026-09-19
**Schema:** none
**Ticket:** #85 (Epic: Orchestration) under backlog root #80; Joe's three
answers in-session, 2026-09-19
**Supersedes, in part:** the three-queue answer of 2026-08-28 recorded in
`tasks/NEXT.md`'s session box ("THIS FILE IS THE FRONT DOOR")
**Amends:** ADR 0003 §2 — the integrator-only file list and the
`tasks/inbox/<lane>.md` convention stand; what changes is where the *queue*
lives, not who may write which file

---

## 1. What was happening

For roughly a month every item was executed inside the main session, one
after another, at the top model. Joe's part of most sessions was "read
NEXT.md and continue". The backlog lived in three places: this file's Open
list (repo and infrastructure work), map #3's open tickets (decisions for
Joe), and *decided-not-yet-built* — a closed ticket carrying a spec, which
belonged to nobody until a session copied it here. The first of those refilled
itself every session, in prose, and every session re-derived it instead of
dispatching it. `tasks/lessons.md` 2026-09-16 (eighth) records the cost on
the decision queue; the same decay ran on the build queue and nothing went
red about it, because nothing measured it.

Joe asked, 2026-09-19, for the main session to orchestrate rather than
execute, for work to run concurrently where independent, for the lowest model
that can do each job, and for a ticket system with epics, stories and tasks
assigned to agents or to the main session.

## 2. Decision

### 2.1 One queue, on GitHub

Every open item is a GitHub issue. Two roots: **map #3** holds Joe's
decisions (unchanged, `wayfinder:*` labels, `docs/agents/issue-tracker.md`);
**backlog root #80** holds build work. The tree is root → `type:epic` →
`type:story` → `type:task`, linked as GitHub sub-issues; blocking is a native
issue dependency. A GitHub issue has one parent, so a ticket that is Joe's
stays under #3 and its epic names it in prose ("Owns #58").

Labels on every leaf: one `owner:` (`main` / `agent` / `joe`) and, on
`owner:agent`, one `model:` (`haiku` / `sonnet` / `opus`).
`wayfinder:grilling`, `research` and `prototype` imply `owner:joe`.

`tasks/NEXT.md` keeps the session narrative and a Still-open list of
**pointers** — `#NN — one line` — never a restated item.
`tests/test_a_question_for_joe_has_a_ticket.py::TestTheRecordHonoursTheRule::test_every_open_item_names_a_ticket`
refuses an item with no number, and `#3` does not count. That extends the
2026-09-16 rule from "an item that asks Joe" to every item.

### 2.2 The main session orchestrates

`scripts/board.py` prints the generated frontier (open, unassigned, unblocked
leaves, grouped by owner and model) and warns on a leaf with no owner, an
agent leaf with no model or no **Done when** line, and a Still-open item with
no ticket. The main session runs it, hands it to `partner` for a ranked list
**and a dispatch table**, then dispatches: claim the ticket, spawn the agent,
merge the lane, number the ADR at the boundary, run the full suite once on the
merged tree, close the ticket with the sha, write the record. Protocol:
`docs/agents/orchestration.md`. Ticket bodies for agent work:
`docs/agents/ticket-template.md`.

### 2.3 Model routing

| tier | agent | takes |
|---|---|---|
| Haiku | `fact-scout` (new), `Explore` | read-only facts: inventories, greps, counts, citation checks, "does the fixture / caller exist" |
| Sonnet | `lane-builder` (new), `lookup-scout` | a build whose ticket names the test that proves it; call-path traces; drafts for main to number; mutation passes |
| Opus / main | the session | `backend/kalshi/*`, `core/{prices,fees,ev,sizing}.py`, the order, RFQ and hedge money paths, `schema.sql`, `config.py`, `CLAUDE.md`, `fly.live.toml`, ADR decisions, measurement write-ups, diagnoses, every merge, every deploy |
| as their files say | `partner`, `measurement-skeptic`, `pre-registrar`, `kalshi-platform`, `runtime-realist`, `sharp-bettor` | spawned with **no** `model` argument, because the spawn argument overrides the file and silently demotes a reviewer |

Joe fixed Haiku's scope as **read-only scouting only** — no edits, even
mechanical ones with a pinning test. The 2026-09-09 rule "Sonnet is the
default when you delegate" is unchanged; this adds a cheaper tier beneath it
and names what stays above it.

## 3. What this does not establish

- Nothing enforces model routing. A `model` argument on a spawn call is read
  by nobody but the session that writes it. The guard is the reviewer reading
  the dispatch table, and `partner`'s brief now asks for that table.
- The board is a snapshot, not a lock (the same limit `lane_board.py`
  states). Two sessions can both read a ticket as unassigned.
- A ticket's **Done when** naming a test makes a wrong build *visible*; it
  does not make it impossible. The main session still runs the full suite on
  the merged tree and still mutates new guards (CLAUDE.md, Testing).
- GitHub Projects was declined (it needs an interactive `gh auth refresh`);
  the tree, the labels and the board are the whole system.

## 4. Consequences

- The Still-open list stops being a place work is stored. A session that
  finds an item with no ticket opens one before writing the entry, or the
  test refuses the entry.
- ADR 0003 §6's "two lanes is comfortable" stands as the build-lane cap;
  read-only scouts do not count against it, because they own no files.
- Counts that decay (ADR 0162) are unaffected: a ticket is a pointer, and a
  pointer does not go stale the way a number does.
