"""Read observations 1-4 of the window-gate registration off a `sweep-log` pull.

    flyctl ssh console -a kalshi-cockpit \
      -C "python /app/scripts/inspect_live_db.py sweep-log -n 400 --limit 600 --json" \
      > pull.json
    .venv/Scripts/python.exe scripts/read_window_gate_observations.py pull.json \
      --open 2026-08-20T15:26:00Z --close 2026-08-20T16:26:00Z

The registration is `docs/measurements/2026-08-20-window-gate-plan.md`. The four
observations are fixed there; this script computes them and nothing else. It
takes the window bounds as arguments rather than deriving them, so a rerun
against a different slot cannot silently redefine what was registered.

Why `odds_sweep_log` and not the process log
--------------------------------------------
`fetch_and_store_odds` writes a row on every outcome including "nothing", so
every pass leaves one. `flyctl logs` drops lines; this table does not. The pass
grid is `DISTINCT pass_ms` -- **not** `COUNT(*)`, because one pass firing several
sports writes several rows and `sport_key` is nullable.

**`detail` carries the window state in the decision's own words**, which is what
makes observation 3 a durable reading rather than an inference from cadence. A
pass with the window closed says `no sweep: next slot is <sport> at HH:MMZ`; one
with it open says `no sweep: <sport>'s window is open and its odds are N min
old`; the sweep that opens it says `... holding the window open`. So
`window_open` can be read per pass off the table, and the loop's exit-state line
-- which only reaches the lossy process log -- is not needed for it.

This also fixes observation 4, which is otherwise read wrong. Earlier *open*
windows run at the fast cadence by design, and counting their 15s gaps as "early
wakes with no window coming" reports a FAIL on correct behaviour. The run-up arm
only counts passes this table says were window-closed.

What this does not establish
----------------------------
- **Observation 1 is not computed here at all.** `quotes_pruned` is persisted
  nowhere -- not in this table, not in any other, not on any API route. It is
  read from the process log, asymmetrically, and this script only supplies the
  list of in-window passes the log must be checked against.
- Nothing about whether the surfaced rows are correct. The registration says the
  same: this is a scheduling fix.
- Nothing about the 12-hour stability watch, which rides on the same deploy and
  is a separate observation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys

# Registered in the plan: the fast cadence, and the jitter the sleep carries.
# Named here so the pass/fail line quotes the number it was judged against.
FAST_INTERVAL_S = 15.0
SLOW_INTERVAL_S = 900.0
JITTER = 0.15

#: Observation 4 permits 2-4 bounded passes in the run-up. More than this, or an
#: early wake with no window coming, is the "already due" spin guard failing.
BOUNDED_PASSES_MIN = 2
BOUNDED_PASSES_MAX = 4

#: How long before the open the sleep bound starts biting, per the registration's
#: simulation (first bounded pass at 15:12Z for a 15:26Z open).
RUN_UP_S = 15 * 60


def _iso(ms: int) -> str:
    stamp = dt.datetime.fromtimestamp(ms / 1000, dt.UTC)
    return stamp.strftime("%H:%M:%S.%f")[:-3] + "Z"


def _parse_iso(text: str) -> int:
    naive = dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    return int(naive.replace(tzinfo=dt.UTC).timestamp() * 1000)


#: Substrings `decide_sweeps` writes when a window is open. Matched rather than
#: re-derived: a paraphrase of the reason is a second implementation of it, which
#: is the argument `sweeplog.py` gives for storing `detail` verbatim.
_OPEN_MARKERS = ("window is open", "holding the window open")

#: What it writes when the window is closed and a slot is merely scheduled.
_CLOSED_MARKER = "next slot is"


def pass_grid(payload: dict) -> tuple[list[int], dict[int, str]]:
    """`(ascending distinct pass_ms, pass_ms -> "open"|"closed"|"unknown")`.

    A pass is `open` if **any** of its rows says so. One pass can write several
    rows -- one per sport, plus a prop note -- and a single row saying the window
    is open is the decision that matters; the others are about a different sport.
    """
    stamps: set[int] = set()
    state: dict[int, str] = {}
    for section in payload["sections"]:
        if "last" not in section["title"]:
            continue
        if section["truncated"]:
            print(
                "WARNING: the tail section is TRUNCATED. Re-pull with a larger "
                "--limit; a truncated grid understates the pass count and would "
                "read as a gap.",
                file=sys.stderr,
            )
        ms_col = section["columns"].index("pass_ms")
        detail_col = section["columns"].index("detail")
        for row in section["rows"]:
            stamp, detail = int(row[ms_col]), str(row[detail_col])
            stamps.add(stamp)
            if any(marker in detail for marker in _OPEN_MARKERS):
                state[stamp] = "open"
            elif state.get(stamp) != "open":
                state[stamp] = (
                    "closed" if _CLOSED_MARKER in detail else state.get(stamp, "unknown")
                )
    return sorted(stamps), state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pull", help="the sweep-log --json file")
    ap.add_argument("--open", required=True, help="window open, YYYY-MM-DDTHH:MM:SSZ")
    ap.add_argument("--close", required=True, help="window close, same format")
    ap.add_argument(
        "--since",
        required=True,
        help=(
            "when the build under test started, same format. Observation 4 is "
            "scoped to it: `odds_sweep_log` outlives the deploy, so passes "
            "before this ran the OLD code and their cadence is not evidence "
            "about the fix. Required rather than defaulted -- a guessed "
            "boundary silently measures a different build."
        ),
    )
    args = ap.parse_args(argv)

    with open(args.pull, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    payload = json.loads(text[text.index("{") : text.rindex("}") + 1])

    grid, state = pass_grid(payload)
    if not grid:
        print("no passes in the pull at all -- wrong file, or the tail was empty")
        return 2

    w_open, w_close = _parse_iso(args.open), _parse_iso(args.close)
    since = _parse_iso(args.since)
    print(f"pass grid: {len(grid)} passes, {_iso(grid[0])} -> {_iso(grid[-1])}")
    print(f"window:    {args.open} -> {args.close}")
    print(f"build up:  {args.since}  ({sum(1 for t in grid if t < since)} "
          f"earlier passes ran the old code and are excluded)\n")

    if grid[-1] < w_close:
        print(
            "THE PULL ENDS BEFORE THE WINDOW CLOSES. Nothing below is the "
            "registered measurement; re-pull after the close.\n"
        )

    # ---- observation 2: the first pass after the open ---------------------
    after = [t for t in grid if t >= w_open]
    print("OBSERVATION 2 -- first pass after the open")
    if not after:
        print("  UNMEASURED: no pass at or after the open in this pull.\n")
    else:
        late_s = (after[0] - w_open) / 1000.0
        bar = FAST_INTERVAL_S * (1 + JITTER)
        verdict = "PASS" if late_s <= bar else "FAIL"
        print(f"  first pass {_iso(after[0])}, {late_s:+.1f}s after the open")
        print(f"  registered bar: within fast_interval+jitter = {bar:.1f}s")
        print(f"  pre-fix worst case was up to {SLOW_INTERVAL_S:.0f}s")
        print(f"  {verdict}\n")

    # ---- observation 3: the fast cadence latches --------------------------
    inside = [t for t in grid if w_open <= t <= w_close]
    print("OBSERVATION 3 -- window_open latches, and the fast cadence follows")
    latched = [t for t in grid if t >= w_open and state.get(t) == "open"]
    if not latched:
        print("  window_open NEVER read open in this table during the window.")
        print("  FAIL (or the window genuinely did not open -- check the slate)")
    else:
        print(
            f"  first pass reading window_open=True: {_iso(latched[0])}, "
            f"{(latched[0] - w_open) / 1000:+.1f}s after the open"
        )
        if after:
            passes_late = after.index(latched[0])
            print(f"  that is pass #{passes_late + 1} after the open (registered: 1)")
            print(f"  {'PASS' if passes_late == 0 else 'FAIL'}")
        print(f"  {len(latched)}/{len(inside)} in-window passes read open")
    if len(inside) < 2:
        print(f"  cadence UNMEASURED: {len(inside)} pass(es) inside the window.\n")
    else:
        gaps = [(b - a) / 1000.0 for a, b in zip(inside, inside[1:])]
        fast = [g for g in gaps if g <= FAST_INTERVAL_S * (1 + JITTER) + 5]
        print(f"  {len(inside)} passes inside, {len(gaps)} gaps")
        print(f"  median gap {statistics.median(gaps):.1f}s   max {max(gaps):.1f}s")
        print(f"  {len(fast)}/{len(gaps)} gaps at the fast cadence")
        # A window served at 15s for an hour is ~240 passes. Well under that
        # means it latched late or dropped out, which the max gap will show.
        expected = int((w_close - w_open) / 1000 / FAST_INTERVAL_S)
        print(f"  a fully-served 60-min window is ~{expected} passes")
        print(f"  {'PASS' if len(fast) > len(gaps) * 0.8 else 'FAIL'}\n")

    # ---- observation 4: the run-up is bounded, not spinning ---------------
    print("OBSERVATION 4 -- the run-up before the open")
    run_up = [t for t in grid if w_open - RUN_UP_S * 1000 <= t < w_open]
    before = [t for t in grid if since <= t < w_open - RUN_UP_S * 1000]
    print(f"  {len(run_up)} passes in the {RUN_UP_S // 60} min before the open")
    print(f"  registered as designed: {BOUNDED_PASSES_MIN}-{BOUNDED_PASSES_MAX}")
    for a, b in zip(run_up, run_up[1:]):
        print(f"    {_iso(a)} -> {_iso(b)}   {(b - a) / 1000:.1f}s")
    ok_count = BOUNDED_PASSES_MIN <= len(run_up) <= BOUNDED_PASSES_MAX
    # **Only window-closed passes.** An earlier open window runs at 15s by
    # design; counting its gaps here reports a FAIL on correct behaviour, which
    # is what the first draft of this script did.
    quiet = [t for t in before if state.get(t) == "closed"]
    skipped_open = len(before) - len(quiet)
    if len(quiet) > 1:
        earlier = [
            (b - a) / 1000.0
            for a, b in zip(quiet, quiet[1:])
            # A gap that spans an excluded open stretch is not a cadence
            # reading. Drop it rather than counting it as a long sleep.
            if not any(a < t < b for t in before if state.get(t) != "closed")
        ]
        floor = SLOW_INTERVAL_S * (1 - JITTER)
        early = [g for g in earlier if g < floor]
        print(
            f"  window-closed passes before the run-up: {len(quiet)} "
            f"({skipped_open} excluded as window-open)"
        )
        print(
            f"  their gaps: {len(earlier)}, min {min(earlier):.0f}s, "
            f"max {max(earlier):.0f}s"
        )
        print(
            f"  {len(early)} below the {floor:.0f}s slow-cadence floor "
            f"(any is an early wake with no window coming)"
        )
        ok_count = ok_count and not early
    print(f"  {'PASS' if ok_count else 'FAIL'}\n")

    # ---- observation 1: the list the log has to be checked against --------
    print("OBSERVATION 1 -- not computed here; check the log for these passes")
    print("  `quotes_pruned` is persisted nowhere. A non-zero value on any pass")
    print("  below falsifies fix 1. Absence does NOT confirm it -- the log is")
    print("  lossy, so an absent line is indistinguishable from a dropped one.")
    print(f"  in-window passes to look for: {len(inside)}")
    if inside:
        print(f"    first {_iso(inside[0])}   last {_iso(inside[-1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
