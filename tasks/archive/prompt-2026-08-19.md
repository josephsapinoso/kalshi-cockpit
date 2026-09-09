Read tasks/NEXT.md and start.

Job: take the four registered observations off the live box for the window
gate fix. Do NOT re-open the fix. It shipped, it is deployed, it is
unverified — the whole job is the measurement.

Run `date -u` FIRST. The plan assumes the baseball_mlb window 15:26Z-16:26Z
on 2026-08-20 (confirmed live, 6 games, earliest fixture 16:41Z).

  before 15:26Z  — nothing to measure yet. Do NOT deploy. Say how long is
                   left and pick up something from the open list instead.
  15:26-16:26Z   — window OPEN. Read only. No deploy, no restart, no push
                   that could trigger one.
  after 16:26Z   — take the measurements. This is the job.
  next day       — the window has passed unmeasured. Say so plainly, then
                   re-plan against the next slot rather than reconstructing
                   from a lossy log.

READ THE REGISTRATION BEFORE ANY LOG.
docs/measurements/2026-08-20-window-gate-plan.md was written before the code
changed. Four observations. Do not invent new ones after seeing output, and
do not quietly drop one that is inconvenient.

Where the durable data is — this is the part that costs hours if you miss it:

  - The DB is /data/cockpit.db. NOT /data/kalshi.db (that path is a decoy;
    connecting to it silently creates an empty file). Open it read-only:
    sqlite3.connect("file:/data/cockpit.db?mode=ro", uri=True). There is no
    sqlite3 binary on the box — use python.
  - `odds_sweep_log` is ONE ROW PER PASS with `pass_ms`. That is your pass
    timing record for observations 2, 3 and 4, and it is durable.
    `flyctl logs` is lossy — see memory. Do not build a finding on it.
  - `quotes_pruned` is NEVER persisted. It exists only in the log line. So
    observation 1 cannot be read directly after the fact. Decide how you
    will evidence it BEFORE the window — the honest fallback is the oldest
    `observed_ms` in `kalshi_quotes`, which jumps if a prune ran. If you
    cannot evidence it, say it is unmeasured. Do not infer it from the
    other three.

Four things that look broken and are not. Do not investigate them:

  - 2-4 passes closer together than 900s in the ~15 min BEFORE a window.
    That is the fix working — the sleep bound recomputes and converges.
    More than 4, or early wakes with no window coming, IS a fault.
  - recorder.age_ms near 900s with the window closed: the loop is idling on
    its slow cadence. Check for an open window before calling it a fault.
  - MemFree near zero is page cache. Read MemAvailable.
  - CI is green as of 82cd2aa. The baseline is green now, so a red run is
    real and is yours. It was red all day 2026-08-19 for an unrelated
    reason (ADR-free, see lessons.md 2026-08-20).

Do NOT sample live memory by looping flyctl ssh console. It's in lessons.md.

The null result is a real outcome: if no window opened — empty slate, or the
odds budget spent — observations 1-3 have no denominator and the fix is
UNTESTED, not confirmed. Check `odds_sweep_log` and `sweeps_remaining_today`
before reading a quiet window as a pass. Write it up as untested and say so
in NEXT.md.

The 12-hour stability watch rides on the same deploy. It is a SEPARATE
observation and must not be reported as evidence for either fix.

Verify line numbers and counts yourself. This repo has had five wrong
attributions on one incident, and the last session found a second root cause
the handoff had not named.
