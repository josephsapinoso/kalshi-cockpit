# ADR 0092 — A closing line that cannot be stored costs one line, not the pass

Date: 2026-08-31
Status: accepted
Relates to: ADR 0091 (the lock holder), ADR 0043

## Context

`run_scoring_pass` has always said what it intends, in its own docstring:

> Failures on one market are recorded and the pass continues. A single market
> whose candlesticks 404 must not stop the other thirty from being scored — an
> observation lost is indistinguishable from one never generated.

The `try` delivered that for the **fetch** and left `store_closing_line`
outside it. So a `database is locked` on one write — four to five times a day
before ADR 0091 — escaped the function, killed the whole pass, and abandoned
every market still in the loop.

**That is the expensive direction.** A closing line not stored is not deferred,
it is lost: candlesticks age out, and a game closes once. `fly.live.toml`
already says as much about a stopped machine; the same is true of a pass that
dies halfway.

## Decision

**The store runs inside the guard the docstring already describes.** A failure
costs the line it was writing and nothing else.

Three parts, and the second and third are not decoration:

- **The store is inside the `try`.** One lost line, not a lost pass.
- **`lines_unstored` is its own counter**, never folded into `candles_missing`.
  A 404 from candlesticks is history the venue no longer has; a failed store is
  history we *held* and dropped. Only the second is ours to fix, and only the
  second means something was lost rather than never generated. Mixing them made
  a lock storm read as a bad night for the candle endpoint.
- **A `rollback()` before continuing.** A lock can refuse the `commit()` rather
  than the `execute()`, which leaves the write transaction open — and then
  every subsequent store in the pass fails too, turning one lost line into the
  whole loop's worth by a different route than the one being fixed.

## Why absorbing this is right, when absorbing is usually wrong

This repo is hostile to swallowed exceptions, correctly. The distinction:

- **Nothing is silent.** The failure increments a dedicated counter and appends
  to `counts.errors`, both of which ride the pass's own log line. A lock storm
  is *more* visible than before, not less: previously it appeared once as a
  dead pass, and the lines it cost were invisible because they were never
  attempted.
- **The alternative loses more.** A raise abandons every market still queued.
  There is no reading under which failing thirty writes is a better response to
  one refused write.
- **It is not a substitute for fixing the cause.** ADR 0091 removed the biggest
  lock holder. This makes the loop survive the *next* holder, whatever it turns
  out to be. Two repairs, neither replacing the other, and the counter is how
  anyone will know whether a next holder exists.

## What this does NOT establish

- **That no closing lines are lost.** They are — one per failure, and
  `lines_unstored` is the count. This bounds the loss to what actually failed.
- **That the lock failures are gone.** ADR 0091's own "not claimed" section
  stands: the frequency fit, and a fit is not a proof.

## Consequences

- Four guards, each mutation-observed-red. **Two of them were decoration first
  and are recorded as such**, because the pattern keeps recurring:
  - the rollback test raised before touching SQL, so nothing was
    mid-transaction and deleting the rollback left it green;
  - the fix for that inserted a probe row under an invented ticker, which
    `closing_lines`' FOREIGN KEY refused *before* a transaction opened — so the
    probe never existed and the assertion passed either way.

  A seeded ticker at an unused horizon is what finally made it fail. **Third
  time this week a guard needed its mutation actually run before it was real**
  (see ADR 0087, ADR 0090).
