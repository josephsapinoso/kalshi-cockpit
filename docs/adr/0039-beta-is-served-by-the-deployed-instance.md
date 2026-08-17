# ADR 0039 — `beta` is served by the deployed instance

**Date:** 2026-08-17
**Status:** Accepted
**Reverses:** the ADR 0022 quarantine of `backend/analysis/signal_test.py`.
**Does not reverse:** ADR 0022's quarantine of `scout.py` or `historian.py`,
which cost money on every pass and stay exactly where they are.
**Does not reopen:** ADR 0038. Nothing here is a new hunting line, and no row of
that table is overturned by putting a number on a screen.

## Context

The cockpit stated a conclusion — that the consensus-only signal does not work —
and stated its measured worth **nowhere**. `beta`, the project's registered
decision-bearing statistic, appeared **zero times in `frontend/src`** and could
be produced only by a human running `scripts/run_signal_test.py` on a laptop,
against a dump taken over `flyctl ssh`.

That is the same defect `/api/gate` and `/api/results` were built to close, in
the same direction: a number that exists only behind a laptop job, on a tool
that is operated from a phone. It is also the defect this repo has a name for —
built but never called — arriving in its subtler form, where the code runs fine
and only the *reader* is missing.

Two structural facts made it worse than a missing screen:

- **The extraction lived in a script, not in `backend/`.** §S1 of the
  registration was transcribed as `_SQL_CLV_SIGNAL_PULL` in
  `scripts/inspect_live_db.py`, and §A8.2's P1 statistic as `a82_counts` in
  `scripts/run_signal_test.py`. Neither ships to the deployed image
  (`.dockerignore:77` admits four scripts, and `run_signal_test.py` is not one).
- **Nothing in the suite read the number.** `beta_hat = -0.1412` was published
  in CLAUDE.md, in a measurement write-up and in a docstring — three places,
  none of them executed. `ev.py` had been wrong for three days for exactly that
  reason: **docstrings that publish measured numbers get re-run, not re-read.**

## The quarantine, and why its stated reason does not survive contact

`backend/analysis/signal_test.py` was classified in `DISPOSITIONS` as a `Tool`,
off the deployed machine deliberately, on this reasoning:

> the estimator carries the registered decision rule, and a rule that runs
> automatically on every pass is a rule that gets re-read thousands of times —
> which is what the always-valid multiplier inside it exists to defend against.

**The clause refutes itself in the second half.** An always-valid confidence
sequence is the construction whose defining property is that it holds
*simultaneously at every sample size*, so its coverage is unharmed by unlimited
optional stopping. Re-reading it thousands of times is the thing it is built
for. The premise ("this must not run automatically") is supported by naming the
exact instrument that makes running automatically safe.

What the reasoning was *reaching for* is real, and it is a different claim: that
the **declaring branches** — `SIGNAL`, `BUG`, `NO SIGNAL` — should not fire with
no human in the room. That is the claim this ADR has to decide, and it decides
it in the affirmative, because ADR 0038 already wants it:

> the `G = 300` look arrives on its own clock — no plan may depend on it

A look that arrives on its own clock and is then read by whoever next opens the
Board is *more* faithful to the registration than one that waits for someone to
remember to take it. The registration fixes the rule; discipline was the only
thing making the rule execute, and discipline is what a registration exists to
replace.

## Decision

1. **`backend/analysis/clv_signal.py` is created**, holding the registered
   extraction (§S1 as amended by §A1/§A2/§A2.2/§F3), §A8.2's three counts, and a
   `SignalReport` that packages what `signal_test.fit()`/`verdict()` return.
   Every expression in it was **moved, not rewritten**.
2. **`scripts/run_signal_test.py` becomes a printer** over `build_report`. The
   operator harness and the served endpoint are one computation, not two
   implementations that agree today.
3. **`GET /api/signal` serves it**, unauthenticated, on the same three grounds
   as `/api/gate`: the live deploy already 401s unauthenticated `/api/*` at the
   Next middleware, a bearer token is not openable in a phone browser, and
   `require_auth` 403s on demo. It reveals less than `/api/gate` already does.
4. **`signal_test.py` moves from `DISPOSITIONS` to `MUST_HAVE_CALLERS`.** The
   guard `test_a_quarantined_module_has_not_been_wired_up_by_the_back_door`
   went red on the first import, which is the behaviour it was built for, and
   its own message names this remedy.
5. **The reproduction is a test, not a claim.** `tests/test_clv_signal.py` runs
   the committed 2026-08-16 dump through the moved code and pins
   `beta_hat = -0.1412`, `se_cluster = 0.0478`, `G = 199`, the interval, and
   both per-arm figures.

## What was verified before this was accepted

The moved code was diffed against the pre-move code on the same data:

```
git show HEAD:scripts/run_signal_test.py  ->  before.txt
scripts/run_signal_test.py (moved)        ->  after.txt
diff before.txt after.txt                 ->  IDENTICAL, byte for byte
```

Both new guards were observed red under a named mutation and green on restore:
one space changed inside the SQL fails the byte-identity assertion against
`inspect_live_db.py`; replacing the half-spread column with zeros in
`signal_test.fit` moves `beta_hat` and fails five assertions. A guard that has
never been seen to fail is decoration.

## Consequences

- **The `G = 300` look now arrives by construction.** Nobody has to remember it,
  and no roadmap depends on it — which is what ADR 0038 asked for.
- **The screen cannot disagree with the record.** They are the same function.
  This is the specific failure the previous session found across the whole
  frontend: the backend was honest and every screen was a version behind.
- **A refusal renders as a refusal.** On demo the seeded history carries no
  `event_ticker` and no `kalshi_quotes`, so P1 fails and the report carries
  `verdict = "REFUSED"` with `fit = None`. `REFUSED` is deliberately not
  `UNRESOLVED`: the latter means a look happened and could not resolve, and
  saying it for a look that never ran reports a measurement that did not occur.
  Without this the public demo would have rendered **`G = 420`** — a larger
  number than the live record's 199, off a database with no signal in it.
- **A new full-table read lands on the two busiest screens.** Board and Slate do
  no full-table work today. The route is cached for 300s at
  `backend/api/routes.py:SIGNAL_CACHE_TTL_MS`, and `computed_ms` ships in the
  payload so the screen must render the number's age rather than implying it is
  live.
- **Two copies of the extraction SQL still exist.** `inspect_live_db.py` cannot
  import from `backend` — it runs as `python /app/scripts/...`, so `/app` is not
  on `sys.path` and an import would pass in the suite and fail on the money box.
  They are held identical by an assertion, which is the same arrangement that
  file already uses for `_ACTIONABLE_PREDICATE`.

## What this ADR does not establish

- **Nothing about the value of `beta`.** It moves a number to a screen. The
  verdict is still `UNRESOLVED` at `G = 199` and may not be reported as "no
  signal"; CLAUDE.md's "for planning, treat it as settled" is a planning
  instruction and not a verdict.
- **Nothing about the other two quarantined modules.** `scout` and `historian`
  spend Anthropic credits per pass. This ADR reaches neither, and the guard
  still covers both.
- **Nothing about the wall-clock cost on the live volume.** The join was never
  timed against an 879 MiB `kalshi_quotes`; the cache is sized on how often the
  inputs change, not on a measured query time. If the first live call is slow,
  that is a fact to measure, not a surprise this ADR ruled out.
