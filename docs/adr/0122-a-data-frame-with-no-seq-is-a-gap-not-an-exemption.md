# ADR 0122 — A data frame with no `seq` is a gap, not an exemption

Status: accepted
Date: 2026-09-09

Closes the last piece of `tasks/audit-2026-08-07.md` item 34, and fixes the
defect that writing the tests for it exposed.

## Context

`_check_sequence` (`backend/kalshi/ws.py`) is the integrity check on the whole
Kalshi feed. `seq` counts frames on the **connection**, not per market — one
shared sid, one strictly increasing sequence across every ticker — so an
undetected gap means deltas keep applying on top of a book that is missing an
update. There is no error. The desk prices against a **silently wrong
orderbook**, which is the worst failure this module has.

Audit item 34 recorded that `_check_sequence` was referenced by no test
anywhere in the repo. That was still true on 2026-09-09, and closing it is
what produced this ADR: 25 tests were written against the function, verified
by 11 mutations of `ws.py` with **zero survivors**, and writing them surfaced
a live hole that reading the function had not.

## The defect

The exemption for frames carrying no `seq` was written type-blind:

```python
seq = message.get("seq")
if seq is None:
    return True
```

The exemption is legitimate and the capture justifies it: in the committed
269-frame stream, `subscribed` is the **only** frame type lacking a `seq`, and
it arrives before seq 1. Reading it as a gap from zero would manufacture a gap
on every connection.

**But the rule as written accepts *any* frame without a `seq`, including a data
frame.** If an `orderbook_delta` ever arrived without one — a field rename on
Kalshi's side, which is precisely the failure class `orderbook.py` was
rewritten to catch after a renamed field emptied every book for a year — it
would pass the integrity check *and* be applied: `_apply` forwards `seq=None`,
and `apply_delta` only records a `seq` that is not None, so it accepts the
delta silently.

That is the exact outcome `_check_sequence` exists to prevent, reachable
through the one branch that skips it.

## Decision

**Scope the exemption to non-data frames.** A frame whose type is
`orderbook_snapshot` or `orderbook_delta` must carry a `seq`; arriving without
one is treated as a gap — every book on the connection invalidated,
`_pending_resync` set, the frame refused — and logged at ERROR rather than
WARNING, because unlike an ordinary gap it means the wire format has changed
under us.

The two type names now live in one module-level constant beside the two places
that branch on them.

### Why not scope it to `subscribed` alone

That is tighter and worse. An unknown control frame Kalshi adds later would
then force a reconnect every time it arrived, and **a reconnect loop is a
heavier failure than an unrecognised ack**. The property that matters is not
"is this frame `subscribed`" but "could this frame change a book" — so that is
what the code asks.

This is the same shape as the rule the repo already follows: *clamp what you
trust; refuse what you're validating.* A control frame is trusted and passes; a
data frame is being validated and must produce its credential.

## Consequences

- `backend/kalshi/ws.py` — the scoped check, the constant, and the reasoning in
  `_check_sequence`'s docstring so the next reader does not "simplify" it back.
- `tests/test_ws_client.py` — 5 new tests in
  `TestADataFrameWithNoSeqIsNotExempt`, on top of the 25 that closed item 34.
- **Verified by mutation in both directions**, which is what distinguishes this
  from a guess about what is safe:

  | mutation | result |
  |---|---|
  | revert to the type-blind exemption (the shipped defect) | **4 red**, all in the new class |
  | widen it to refuse *every* seqless frame | **8 red** — including the `subscribed` ack registration and both full-capture replays |
  | restored | 44 green in the file, 91 across the ws neighbourhood |

  The over-broad mutation reddening the capture replays is the useful half: it
  shows the narrow rule is not merely untested-but-safe, it is pinned against a
  real 269-frame stream.

### Two stale docstrings corrected in the same pass

Both described behaviour that does not exist, and both would have sent a
reader looking in the wrong place:

- `backend/kalshi/ws.py` header said a gap *"triggers an automatic
  unsubscribe/resubscribe for that one ticker"* — wrong twice: nothing is
  raised, and recovery is a whole-connection reconnect (ADR 0119).
- `backend/kalshi/orderbook.py:15` said *"a gap raises `SequenceGap`"*. It is
  constructed and **logged**; the resync travels by flag.

The rule those paragraphs exist to state — never patch forward across a gap —
is unchanged and kept.

## What this does not decide

Three things the same review surfaced, recorded so they are not re-found:

1. **The gap branch moves the cursor to an unbounded observed `seq`.** One
   corrupt or wildly large `seq` parks `_last_seq` there, after which every
   legitimate frame looks like a reorder and is dropped **silently**. The
   reconnect saves it in practice, since that resets `_last_seq = None`. There
   is no plausibility bound on gap size, and adding one is a separate change.
2. **A gap discards the frame that revealed it, even when that frame is a
   snapshot** — a frame that would have repaired the book. Harmless given the
   reconnect re-snapshots, but it means recovery always costs a full
   reconnect.
3. Whether the sequence-gap branch has **ever** fired in production. Nothing
   persists a `SequenceGap` — no table, no counter — so the only record is
   Fly's log buffer, which is lossy.
