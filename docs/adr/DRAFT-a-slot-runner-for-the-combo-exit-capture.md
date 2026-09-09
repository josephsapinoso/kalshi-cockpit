# DRAFT — A slot runner replaces the hand-typed run sheet for the 2026-09-13 capture

Status: proposed
Date: 2026-09-09

## Context

`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md` fixes
a five-slot capture across a 9¼-hour NFL Sunday (§7, Amendments 1 and 2),
with **two deliberately separate invocations per slot** — Arm A (comparison,
default series, `--max-books 40`) and Arm D (primary, `--series
KXMVECROSSCATEGORY-SHARD1 --max-books 25`). As registered, that is ten
commands typed by hand over the day, each with its own filename
(`docs/measurements/2026-09-13-combo-exit-{nfl-sunday,shard1}-cN.{json,txt}`).

Two properties of the registration make hand-typing risky:

1. **The stopping rule permits no sixth capture** (§7). `--json`, `--capture`
   and shell `>` all overwrite silently, so a slot typed as `c1` when `c2` was
   meant destroys an earlier capture with no warning.
2. **Redirecting stdout to a `.txt` is required, not optional** — `to_json`
   drops the scan denominator (§5 S3), and the 2026-08-18 run already lost it
   once by not capturing stdout.

Neither failure mode is hypothetical; both are named in the registration
itself as things that have already happened once in this project's record.

## Decision

`scripts/run_combo_exit_capture.py` turns each slot into one command:

    .venv\Scripts\python.exe scripts\run_combo_exit_capture.py --slot c3
    .venv\Scripts\python.exe scripts\run_combo_exit_capture.py --slot c3 --dry-run

It is a **caller**, not a second implementation — it assembles the exact
argv the registration fixes for Arm A (§7) and Arm D (§11.6) and hands each to
`subprocess`, with stdout+stderr captured to the registered `.txt` path
exactly as `> file 2>&1` would. `scripts/measure_combo_book_presence.py`
itself is untouched; nothing here re-derives the instrument's analysis.

**Before either arm runs, every one of the slot's four target output paths
(both arms' `.json` and `.txt`) is checked, and the whole slot refuses —
nothing runs, nothing is written — if any one of them already exists**,
naming the blocking file. This is the overwrite protection the registration's
"no sixth capture" rule needs and the shell redirection it specifies does not
provide on its own.

`--dry-run` prints the two commands a slot would run, without executing them
or touching the filesystem, and still runs the overwrite guard — so an
operator previewing Sunday's slot sees the refusal they would get for real,
at zero Kalshi-call cost.

Arm C (`KXMVENFLSINGLEGAME` / `KXMVENFLMULTIGAMEEXTENDED`) is not given a
per-slot invocation here. The registration does not give it one either — §7
and §11.6 fix Arm A's and Arm D's commands; Arm C is described in §2 and
§11.10 only as an arm that runs "if the instrument change ... lands" and is
"expected to abort", with no fixed per-slot command of its own, and
`tasks/NEXT.md`'s run sheet says "two invocations per slot" and lists only A
and D. If Arm C is to run on the day, that is a separate manual invocation,
not something this runner emits.

## Consequences

- Ten hand-typed commands become five (`--slot c1` … `--slot c5`), each
  producing both registered invocations in order.
- A wrong slot argument, or a re-run of a slot already captured, refuses
  loudly with a named blocking file instead of silently destroying data.
- The runner's own exit code is reserved for its own concerns — the
  overwrite refusal (3) and a failure to launch the subprocess at all (4). It
  does not interpret `measure_combo_book_presence.py`'s exit code (0, 1, or
  2 for `EmptySeriesRequested`) as its own success or failure, because all
  three are registered, valid **data** outcomes for that instrument, not
  failures of this runner.
- Verified by disabling the guard (commenting out the `check_no_overwrite`
  call in `run_slot`) and re-running `tests/test_run_combo_exit_capture.py`:
  three tests went red —
  `TestOverwriteGuard::test_run_slot_returns_nonzero_and_names_the_blocking_file`,
  `TestOverwriteGuard::test_run_slot_prints_the_blocking_path_and_does_not_run_the_stub`,
  and `TestDryRun::test_dry_run_still_refuses_on_an_existing_output` — and all
  eighteen passed again once the guard was restored.

## What this does not do

- Does not touch `scripts/measure_combo_book_presence.py`. That is the
  instrument under the pre-registration; this ADR changes nothing it
  measures.
- Does not retry a missed slot. §7's 30-minute rule ("a slot missed by more
  than 30 minutes is recorded missing, not moved") is an operator decision on
  the day, not something this script enforces or works around.
- Does not open the cockpit UI or read `/api`, and does not touch anything
  under `backend/odds/`, frozen until 10:00Z on 2026-09-14. It only shells out
  to the two commands the registration already specifies.
- Does not run Arm C. See "Decision" above.
