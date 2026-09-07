# 0108 — The live inspector is split by its own section banners, and the split is guarded by a size budget

**Status:** accepted (built 2026-09-06, written up 2026-09-06)

> **Ordinal taken at commit time after `git fetch`**, per `docs/adr/README.md`.
> Drafted as `DRAFT-` with no number; 0108 was claimed as the last step before
> the commit, with `git worktree list` showing no other lane running. Three ADR
> numbers collided in one day because lanes read `main` first, and "what was
> free when I looked" is not an allocation.

## Context

`scripts/inspect_live_db.py` reached **97% of the 262,144-byte ceiling** at
which the Read tool refuses a file outright. That is the same ceiling
`tasks/NEXT.md` and `tasks/lessons.md` hit on 2026-08-17, and it fails the same
way: not with an error, but with a session reading the head of the file and
silently believing it has the whole thing. It was blocking work.

The inspector is the tool that reads the live money box during an incident. A
file nobody can open in one piece is the wrong shape for that job.

## Decision

**Split it into eight modules, cut where the file's own section banners already
cut it**, and enforce the result with a size budget rather than a convention.

- Largest module is **22.0%** of the ceiling against a **60%** budget the commit
  enforces. The budget is the artifact; the current sizes are just where it left
  them.
- **Zero content lines lost, proved by multiset diff** rather than by review. A
  split is a claim that nothing was lost, and that claim is cheap to check and
  expensive to be wrong about.
- The cut follows the banners because they encode the author's own grouping. A
  cut by line count would have produced eight files nobody could name.

**The surface is unchanged, and the proof is mechanical rather than argued:**

- 36 subcommands before and after, same names and same descriptions.
- 14 argparse actions with identical option strings.
- `--help` **byte-identical at 13,633 bytes**.
- All 40 subcommands (36 plus Lane A's four) invoked **by path in a subprocess
  with only `scripts/` on `sys.path`** — the box's own arrangement, not the test
  runner's.

Lane A's four ad-hoc queries are folded in rather than left loose:
`credits-reset`, `credits-by-sport`, `credits-rate`, `fair-prices-by-market`.

## Consequences

### The third `.dockerignore` allowlist failure, and why both existing guards were blind to it

`.dockerignore`'s `!` allowlist has now failed **four times**. `test_has_callers.py`
derives two halves of it — what `entrypoint.sh` runs, and what declares its own
`/app/scripts/<name>.py` — and **neither derivation can see an import**.

Splitting one script into eight created seven modules that are *imported*, not
invoked. Only the entrypoint is invoked by path, so only it declares one. **Both
existing guards would have reported a healthy allowlist while seven modules were
absent from the image**, surfacing as `ModuleNotFoundError` at an ssh prompt
during an incident — which is precisely when the inspector is wanted.

**The pattern worth carrying: a guard that derives its expectations from
invocation cannot see a dependency introduced by import.** Splitting a file
converts the second kind into the first, so any allowlist keyed on "what gets
run" goes stale the moment a script grows modules.

### A guard was written, found green under its own mutation, and replaced

The NULL test began as *"a NULL cannot **manufacture** a drop"* and passed with
the filter removed, because SQL's three-valued logic already gives that away for
free. The property the filter actually buys is the opposite: **an unreadable row
must not *hide* a reset by breaking the pairing across it.**

Recorded in the docstring rather than quietly rewritten, because the wrong
version is the one a reader would write again.

### `credits-month` now cites `credits-reset` at the point of reading

A MIN/MAX over a calendar month straddles the vendor's billing reset and reports
a maximum describing no live state. That reading was nearly mis-taken. The
warning now lives in the subcommand's own description rather than in a document
someone would have to already suspect they needed.

## What this does not decide

- **It does not change any query's semantics.** Byte-identical `--help` and
  identical subcommand surface are the whole claim; a query that was wrong
  before this is wrong after it.
- **It does not fix the allowlist derivation**, only the one instance. A guard
  that reads imports as well as invocations is still owed, and the count of
  allowlist failures is now four.
- **It sets no precedent for splitting on size alone.** The banners are what
  made this cut safe; a file without them needs a different argument.
