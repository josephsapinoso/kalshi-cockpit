# ADR 0049 — The failure channel is wired, and the failure that actually happened stays uncovered

**Date:** 2026-08-18
**Status:** Accepted, **amended the same day — the title's second clause no
longer holds.** The filename is kept because links are cheaper than accuracy in
a slug and the body records both states. See "AMENDED" below: one query against
the live volume closed the gap and reversed a decision made above it.
**Follows:** ADR 0048 (the deep link), which is what sent a reviewer into this module.

## What was there

`DiscordNotifier` has three purpose-built failure alerts — `feed_died`,
`credits_exhausted`, `fee_mismatch` — each carrying copy that says what the
failure means for the numbers on screen. **All three had zero production
callers.** Every reference in the tree was a test.

The one failure alert that *was* wired is `alerter.failure("Recording loop
died", ...)` at `scripts/run_loop.py`, inside `except LoopFailed`. That needs
`MAX_CONSECUTIVE_FAILURES = 5` consecutive pass failures
(`backend/scheduler.py:56,335`).

**So the only working failure alert cannot fire on the failure mode that has
actually happened to this instance.** The 2026-08-16 volume-full incident
crash-looped the *container*, which kills the process before `LoopFailed` is
ever raised.

`FAILURE_KINDS = ("loop_failed", "credits_exhausted", "feed_died")` was
referenced by nothing in the tree — not even by its own module — and **not one
of its three strings matched the one kind ever sent**. A constant nobody reads
cannot be wrong, so it was wrong for the life of the project.

## The decision

**1. A feed watchdog, in the process that owns the notifier.**
`Alerter.check_feed` runs on every pass, full and quote, beside the good news.

**2. Its denominator is not optional.** It is silent when `markets_priced == 0`.
Overnight there is nothing to quote; a watchdog without this clause buzzes every
night, and a muted channel is strictly worse than no channel.

**3. `hub_running` crosses the process boundary, and the in-process alternative
was checked and rejected.** The reviewer proposed reading the age of the newest
`kalshi_quotes` row — symptom-based, no plumbing, and claimed to catch a hub
that reconnected but re-subscribed to nothing.

**That last claim does not survive reading the writers.** `kalshi_quotes` is
written **only** by `runner.store_quotes_from_discovery`, at `source = 'rest'`,
on every pass. `QuoteHub` writes nothing to it. Quote age therefore measures
this loop's own liveness and is blind to the WebSocket entirely — and a loop
cannot alert on its own death in any case, so the signal it *does* carry is one
nothing can act on.

The hub lives in the uvicorn process, which already publishes the canonical
answer as `/api/health`'s `live_quotes_available`. Reading it is not a second
implementation: `docker/entrypoint.sh:176` polls the same endpoint on the same
loopback address to decide the backend has started.

**4. An unreadable probe is its own alert.** `None` is never `False`. "The API
did not answer on loopback" and "the hub is down" are different facts with
different fixes, and reporting the second when the first happened is this repo's
*unreadable-resolves-to-zero* defect pointing the other way.

**5. `FAILURE_KINDS` is now the dedupe key's allowlist**, asserted in
`Alerter._failure`. The kind is half of `notifications`'s `UNIQUE (kind, key)`,
so a typo does not fail loudly — it opens a second bucket and the phone gets the
same alert twice a day, which reads as the alerter being noisy rather than as a
bug. The declared strings are the exact embed titles, so the queryable record
and the thing Joe reads are the same name.

**6. `credits_exhausted` is wired** off `budget.remaining_today()`. Not a
malfunction — the budget working — but invisible from the Board, which simply
stops producing rows.

## AMENDED the same day: the gap is closed, and the record decided two things

The paragraph below stood for about an hour. Joe ran the one query this ADR's
review had asked for, and its answer settled two open items and reversed a
third. Amended rather than superseded because nothing above is wrong — only
incomplete.

```
digest       12   delivered 12
window_open  93   delivered 93
failure       1   delivered  0
opportunity   —   NO ROWS AT ALL
```

**1. `opportunity` has never fired.** Not one row in the project's life. So all
93 `window_open` buzzes — about eight a day across twelve budget days — opened
onto a board with nothing on it. `after_pass` now requires `counts.surfaced > 0`.

`tests/test_alerts.py` previously asserted the **opposite** ("it is the only
signal that the machinery ran"). That reasoning was not silly; it was
unmeasured. The daily digest is also that signal, on a cadence that cannot
storm, and the empty case turned out to be not a minority of the traffic buying
a heartbeat but *all* of it. The reversal is recorded in the test's own
docstring rather than swapped quietly.

**2. The one failure alert ever attempted was not delivered.** `delivered = 0`,
one for one. Before today the only wired failure was "Recording loop died",
sent as the last thing a dying process does — the alerter claims the row before
sending, so a process that dies mid-send leaves exactly this. **The loop died
and Joe was not told, and nothing said so for months.** `/api/health` now
carries `notifications: {last_delivered_ms, undelivered_last_24h, total_ever}`.

**3. The external dead-man's switch is built**:
`.github/workflows/heartbeat.yml`, every 15 minutes, posting to the same Discord
webhook from a machine the app's problems cannot reach. Three checks: does
`/api/health` answer, does it say ok, and **is the recorder still writing**.

That third one needed a new field. `entrypoint.sh` supervises the loop with
`wait -n`, so a loop that *exits* takes the container down and is visible from
outside — but a loop that is alive and **stuck** keeps every existing check
green while the record stops accumulating. `/api/health` now carries
`recorder: {last_write_ms, age_ms}`, and the heartbeat alarms past 30 minutes
(two missed full passes; one is a slow pass, two is a pattern).

**The irony is worth keeping.** `kalshi_quotes` age — the signal rejected above
as blind to the WebSocket — is exactly the right signal *for the loop's own
pulse*, read by something outside the process. The reviewer's instinct was
sound and its subject was wrong.

Both new health blocks are wrapped so they can never take `/api/health` down:
it is the liveness probe both `entrypoint.sh` and the heartbeat read, and a
route that 500s because a SELECT failed turns a reporting gap into an outage —
and into a false alarm on a phone. Unreadable resolves to `None`, never to a
number the heartbeat would act on.

**What the heartbeat still cannot do**, stated because this ADR's whole subject
is unclaimed coverage: GitHub's cron is best-effort, routinely delayed, and
skipped entirely on repositories idle for 60 days. It bounds time-to-notice at
*roughly* 15 minutes, never exactly, and it is itself a system that can fail
silently. Strictly better than nothing off-box. Not a pager.

### The amendment shipped broken, twice, and that belongs here

`a08c1a9` took the live instance down for about fifteen minutes. Two defects,
both mine, both in the observability code rather than in anything it watches.

**`budget.remaining_today()` raised AttributeError on every pass.**
`remaining_today` is a property on `BudgetState`, which `CreditBudget.state()`
returns. `tests/test_has_callers.py` had verified the call site *existed* —
which was true and useless. **"The symbol is referenced" and "the reference
resolves" are different facts**, and a grep-based caller check only proves the
first. `run_loop.main()` has no caller but `__main__`, so nothing executes it.
Closed by `tests/test_run_loop_attributes_resolve.py`, an AST walk over every
`obj.attr` in the loop, verified by reintroducing the exact defect.

**`SELECT MAX(observed_ms) FROM kalshi_quotes` on `/api/health` is what killed
it.** Measured on 3,000,000 rows with this schema and index: 323.7 ms against
0.116 ms for `ORDER BY id DESC LIMIT 1`, and linear against constant.
`/api/health` is hit by Fly's check, Next's proxy **and, because of this ADR,
the loop's own probe** — the walk exceeded the probe's 2s timeout and uvicorn
stopped answering on loopback.

`EXPLAIN QUERY PLAN` reports `SEARCH ... USING COVERING INDEX` for the MAX and
a bare `SCAN` for the LIMIT form, which reads as the MAX being optimised. It is
not: `observed_ms` is the second column of the index. **A plan is a shape, not
a cost.**

**Both blocks were correctly wrapped so they could not 500. Nothing stopped
them being slow**, and for a liveness probe slow is the worse failure — it is
indistinguishable from death. That is the gap this ADR's own subject should
have predicted: the monitoring became the thing that needed monitoring.

### The original paragraph, kept

**The container crash-looping.** It kills this process before any of the above
runs, and it is the failure that has actually happened here. **Nothing running
inside the box can report the box being dead.** That needs an external
dead-man's switch — a Fly health-check alert, or something off-box that expects
a heartbeat and shouts when it stops. It is not built here and must not be
believed to be.

**`fee_mismatch` still has no caller**, and that is recorded rather than hidden.
`ORDERS_ARE_DRY_RUNS = True` (`store/orders.py:129`) means this instance has
never placed an order, so there is no fill to reconcile and no honest place to
call it from. The method now exists as one obvious hook for the reconciliation
path when arming happens.

**Whether any alert has ever been delivered.** `notifications.delivered` is
written by `alerts.py` and read by nothing outside tests, and
`/api/health`'s `notifications_configured` is a boolean about whether a string
is non-empty. Revoke the webhook and a broken alerter is indistinguishable from
a quiet slate. Separate work.

## One defect fixed on the way past

`Alerter._surfaced_this_pass` filtered on `suggested_contracts > 0` while the
canonical predicate — `Recommendation.surfaced` at `engine.py:95` — is that
*and* unsuppressed. They agree today (`engine.py` zeroes contracts on
suppression), so this was not a live bug; it is the two-paths-one-definition
shape the digest query beside it was already repaired for.

**Its test could not have caught it.** `test_a_suppressed_row_is_never_announced`
proved the claim by *inserting `contracts=0` itself* — it constructed the zero
it was checking, so it passed on the first clause alone and never exercised the
second. The test now inserts a suppressed row that is **sized above zero**,
which is the state the second clause exists for, and a separate test covers the
state production actually produces. Same shape as the `daily_pnl_dollars` defect
`tests/test_has_callers.py` was built for.

## Guards

`check_feed` and `check_credits` are in `MUST_HAVE_CALLERS`, so unwiring either
turns `tests/test_has_callers.py` red — the specific failure this ADR is about.
Six guards in `tests/test_alerts.py` were each verified by disabling them and
watching the file go red: the empty-slate denominator, the unreadable-probe
branch, the `suppressed_reason` clause, the declared-kind assertion, and the
routing through the purpose-built notifier methods rather than the generic one.
