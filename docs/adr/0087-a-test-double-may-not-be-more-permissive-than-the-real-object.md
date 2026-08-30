# ADR 0087 — A test double may be simpler than the real object, never more permissive

Date: 2026-08-30
Status: accepted
Amends: ADR 0084 (the resting-bid door)

## What happened

Joe's first real resting bid — 9 contracts at 20.1c on a combination, shard 1 —
passed its `2026-08-30T23:00:00Z` auto-cancel deadline and was **not**
withdrawn. It was still `resting` three minutes later.

The watcher was not dead. It was running exactly on schedule — 23:00:16Z,
23:01:16Z, 23:02:16Z, once a minute as designed — and failing every time:

    RuntimeError: KalshiRestClient used outside its context manager.
    Use `async with KalshiRestClient(cfg) as api:`.

`scripts/run_loop.py:1006` passed `lambda: KalshiRestClient(kalshi_config)` —
a **constructed but unentered** client. `KalshiRestClient.client` raises before
a request is ever built, so `cancel_order` could not reach the venue. **Every
cancel this watcher ever attempted failed, from the day ADR 0084 shipped it.**

Two things limited the damage, and both were deliberate design rather than
luck:

- **Nothing lied.** `cancel_due_bids` catches, logs, and leaves the row
  working — it never writes "cancelled" over an order still live at the venue.
  The table was accurate the whole time; the deadline simply was not enforced.
- **The manual path was unaffected.** `/api/parlays/bids/{id}/cancel` builds
  its client through `combo_api()`, which passes an explicit `client=`, so the
  guard is satisfied. Joe could always cancel from the cockpit.

## Why every test was green

`tests/test_bid_watch.py` had five tests over this behaviour and none could
have caught it, for two independent reasons that compound:

1. **Every test called `cancel_due_bids` directly**, handing it a client
   someone else had prepared. The bug lived in `watch_bids_forever`, in the
   step where the loop builds the client — the one seam production actually
   runs, and the only seam nothing exercised.
2. **`FakeApi` was more permissive than `KalshiRestClient`.** It answered
   `cancel_order` whether or not it had been entered. So it modelled a client
   that does not exist, and the defect was invisible *by construction*.

And the wiring guard, `TestItIsActuallyStarted`, asserts the **string**
`"watch_bids_forever(args.db"` appears in `run_loop.py`. It does. That check is
necessary and it is not sufficient: a source grep can say a call exists; only
running the thing says the call works. This is the second instance of the
pattern already in `tasks/lessons.md` — *a test that names a symbol is not a
guard on that symbol* — and the first one where it cost a live feature its
entire function.

## Decision

**A test double may be simpler than the object it stands in for. It may not be
more permissive. Wherever the real object refuses, the double refuses.**

`FakeApi` now implements `__aenter__`/`__aexit__` and raises the same
`RuntimeError`, with the same wording, when used unentered. Three existing
tests had to be updated to enter it — which is the point: they were passing a
client in a state production never produces.

One of those three is worth naming. `test_the_row_stays_working_when_the_venue_
refuses` passed unentered **for the wrong reason** — on the context-manager
error rather than on the venue refusal it claims to test. A green test asserting
the right outcome via the wrong failure is worse than a red one.

### The fix itself

`watch_bids_forever` enters the client it builds:

    now_ms = db.now_ms()
    if due_for_cancel(conn, now_ms=now_ms):
        async with api_factory() as api:
            await cancel_due_bids(conn, api, now_ms=now_ms)

**Guarded on there being work**, rather than entered unconditionally. The
factory exists so a keyless instance does not build a Kalshi client for a
feature it does not expose; entering one every 60s regardless would have
quietly undone that and logged a failure a minute, forever. The same `now_ms`
serves the check and the work, so the two reads cannot disagree.

### The guard that would have caught it

`TestTheWatcherDrivesARealCancel` drives `watch_bids_forever` itself with
`max_passes=1` and asserts three things the old tests could not see: that the
client was **entered**, that it was **closed** (a client per pass never closed
is a socket leak per minute), and that **no client is built when nothing is
due**. Mutation observed red on all three by restoring the unentered call.

It needs no injected clock. `KICKOFF_MS` is a fixed instant in 2026-08-29,
permanently in the past, so a bid carrying it is due under the real clock —
production keeps its own clock rather than growing a parameter that exists only
to be tested.

## Consequences

- The deadline on a resting bid is enforced for the first time.
- **`ADR 0084`'s central safety claim was aspirational until now.** Its
  reasoning stands — a fill after kickoff is a bet on a game under way at a
  pre-game price, with no exit on a combination — but the mechanism did not
  work. Read ADR 0084 with that correction attached.
- The rule above applies beyond this file. Any double for an object with a
  lifecycle — context managers, connections, sessions — should refuse what the
  real one refuses. Nothing else in the repo was found doing this: the only
  other `factory()` call sites (`agents/review.py`, `notify/alerts.py`) build
  coroutines, not clients.

## What this does not establish

- **That a bid was ever at risk of filling.** The census on the same day found
  61 combination markets, 0 with liquidity, 1 that has ever traded. The
  counterparty this guards against has still never been observed.
- **That the cancel now reaches the venue.** The tests prove the client is
  entered and the call is made; only a real deadline passing on live proves the
  round trip. That verification is a follow-up, not a claim.
