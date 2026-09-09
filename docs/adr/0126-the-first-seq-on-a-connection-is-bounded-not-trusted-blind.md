# ADR 0126 — The first `seq` on a connection is bounded, not trusted blind

Status: accepted
Date: 2026-09-09

Closes the gap ADR 0122 named in its own "what this does not decide". Amends
nothing; the seq-less-data-frame rule from 0122 is untouched and this reuses
its refusal path.

## Context

ADR 0122 made a data frame with no `seq` a gap rather than an exemption, and
recorded what it had not settled: **the gap branch parks `_last_seq` at an
unbounded observed `seq`.**

The live hole turned out to be narrower and worse than that sentence suggests.
It is the **first** frame on a connection.

`_check_sequence` short-circuits when `_last_seq is None`, which is the state
`_connect_and_consume` sets on every connect and reconnect. There was nothing
to compare the first frame against, so it was accepted at any value and parked
as the cursor. Every legitimate frame afterwards then satisfies
`seq <= _last_seq` and takes the **reorder** branch — which drops the frame
with a `logger.warning` and touches neither invalidation nor resync.

So the feed dies permanently, with:

- no error, because a reorder is an expected condition;
- `book.invalid` still `False`, because `apply_snapshot` clears it
  (`orderbook.py`);
- the receive-timeout never firing, because `_last_message_ms` is stamped in
  `_connect_and_consume` on every arriving frame, **before** `_handle` runs —
  including frames that are then dropped.

**Silent permanent staleness with no error is the worst failure this feed
has**, and every one of the four things that would normally catch it was
satisfied.

A test had **enshrined the behaviour as intended**:
`test_the_first_frame_on_a_connection_is_accepted_whatever_its_seq`, asserting
`seq = 8_675_309` is accepted and parks the cursor there. It is inverted by
this ADR.

**The mid-stream case was checked and does not share the hole.**
`_connect_and_consume` calls `_resync_all()` synchronously after `_handle()`
and before the next `ws.recv()`, so a forward gap of any size forces a
reconnect — resetting `_last_seq` to `None` — before another frame can be
judged against a poisoned cursor. The bootstrap frame is the only unrecovered
case.

## Scope: this corrupts the screen, never a fill

`live_quotes().fetch` is a fresh REST `GET /markets/{ticker}`
(`backend/kalshi/quotes.py`), so check 7 of the hand-bet path re-prices every
bet from the venue independently of this socket. **This is a display-path
correctness defect and must not be described as a money bug.**

## Decision

**`FIRST_SEQ_MAX_PLAUSIBLE = 10_000`** bounds the first `seq` accepted when
`_last_seq is None`.

The reasoning, which is what the constant is worth: `seq` is per-connection and
restarts near 1 — the committed capture's first data frame is `seq = 1`, right
after the one seq-less `subscribed` ack. Before the first market-data frame,
only per-ticker subscribe acks can consume sequence numbers, at most one each,
so the true first `seq` is bounded by the ticker count on the connection. A
personal desk following a handful of concurrent games has never been observed
subscribing more than the low dozens. 10,000 is two-plus orders of magnitude of
headroom — the same margin logic `orderbook.py` already uses for
`MAX_PLAUSIBLE_QUANTITY` — while still catching a mis-decoded integer or a
wraparound.

**A frame failing the bound is refused, loudly**: every book invalidated,
`_pending_resync` set, logged at `error`. The same treatment ADR 0122 gives a
seq-less data frame, and deliberately not a silent absorb — the defect being
fixed *is* a silent absorb.

**`MAX_PLAUSIBLE_GAP = 100_000`** is diagnostic only. An implausible
mid-stream forward jump is already handled safely, so this changes what is
logged ("corruption" rather than "gap") and nothing else. It is recorded here
as a constant with no behavioural surface, so nobody later mistakes it for a
guard.

## Verification

Both guards were disabled and the tests watched to fail:

| mutation | result |
|---|---|
| `FIRST_SEQ_MAX_PLAUSIBLE` bound removed entirely | **4 red** — the refusal, the boundary, the invalidation, the resync |
| `MAX_PLAUSIBLE_GAP` classification removed | **1 red** — the log-text test, which is its only surface |

The boundary is tested on both sides: exactly at the bound accepts, one past
refuses. 209 tests pass across every file touching this module.

## What this does not decide

- **Whether a corrupt `seq` has ever actually arrived.** Nothing in the record
  shows one. This bounds a reachable state, it does not report an incident.
- **Whether the reorder branch should invalidate.** It still drops silently for
  a *legitimate* reorder, which is correct; only the poisoned-cursor route into
  it is closed.
- **Anything about Kalshi's `seq` semantics beyond the committed capture.**
  Per-connection restart is read off one 269-frame recording.
