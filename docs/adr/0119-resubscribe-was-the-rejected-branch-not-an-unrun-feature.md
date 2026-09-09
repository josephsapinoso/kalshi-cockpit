# ADR 0119 — `_resubscribe` was the rejected branch of a decision, not an unrun feature, and it is deleted

Status: accepted
Date: 2026-09-09

Closes `tasks/NEXT.md` open item 5 and the `_resubscribe` half of
`tasks/audit-2026-08-07.md` item 34.

## Context

`KalshiWebSocket._resubscribe` (`backend/kalshi/ws.py:269` before this change)
was called by nothing: not `run()`, not `_resync_all`, not any test. It was
found while re-checking an audit item and logged as the **fifth instance** of
this repo's "built but never called" pattern.

`tasks/NEXT.md` ruled it a **live-behaviour question rather than a tidiness
one**, and that ruling was right to make. The feared reading was specific and
serious: a resubscribe that never runs would mean a dropped socket silently
stops delivering the markets it was watching, and the desk would show **stale
prices rather than an error** — the dangerous failure, because the screen
still looks alive. The instruction was to establish which before deleting it
or writing it a caller, since deleting dead code that was covering a real gap
removes the evidence along with the symptom.

## What was established

**The no-caller finding is confirmed, in every form it could hide in.** The
bare identifier, dynamic `getattr` construction, string dispatch, scheduler
registries, and non-Python config were all searched. The five apparent hits in
`backend/live.py` are a different symbol — `self._resubscribe_s`, a float
interval. `tests/test_ws_client.py` names it only in its module docstring, as
history.

**Recovery is real and there are two independent mechanisms, neither of which
needs it:**

- **Inside the client.** `run()` catches `ConnectionClosed / OSError /
  TimeoutError`, backs off with jitter, and re-enters `_connect_and_consume`,
  which opens a new socket and re-subscribes **every** ticker
  (`ws.py:227-228`). Subscription state does not survive a reconnect and is
  not meant to: `_sids`, `_ticker_sids` and `_pending_subscriptions` are
  cleared at the top of every connection, `_last_seq` is reset, and every book
  is marked `invalid`.
- **Above the client.** `QuoteHub._one_cycle` (`backend/live.py:458`) builds a
  **brand-new `KalshiWebSocket` object** every cycle and tears the old one
  down. The object itself does not survive.

**And on the sequence-gap path — the exact scenario `_resubscribe` was written
for — the reconnect is not a fallback, it is the recorded decision.**
`_resync_all` refuses to per-ticker resubscribe and raises `ResyncRequired`
instead, and its docstring, three lines from the dead function, says why:

> Reconnecting rather than re-subscribing, deliberately. […] whether Kalshi
> answers a *redundant* subscribe with a new snapshot or a bare `ok` **has not
> been observed**. Building recovery on unobserved behaviour is how a resync
> path comes to exist without ever working.

So this is not the four earlier cases. **`_resubscribe` is the branch that
docstring rejects**, left in the file after the decision went the other way.

**The feared symptom cannot occur.** Staleness has four independent catchers,
and the one closest to the screen does not depend on the backend being honest:

| layer | mechanism |
|---|---|
| transport | 60s receive timeout on total silence → reconnect (`ws.py:234`) |
| per-book | `OrderBook.is_quotable` refuses on `invalid`, never-populated, or age (`orderbook.py:327-337`) |
| pricing | `price_against` returns `None` on `book.invalid` — no row is emitted at all (`live.py:293-294`) |
| screen | `SILENT_MS = 25_000`; past 25s with no frame of any kind the banner reads **FEED SILENT** / "Treat every price below as frozen" (`LiveBoard.tsx:29,134,341-348`) |

The order path is independent of all of it: the endpoint re-reads the book
server-side and `backend/gate.py:830` refuses on quote age, with
`MAX_KALSHI_QUOTE_AGE_S = "30"` deployed in `fly.live.toml:539` and a boot
assertion if it disagrees with the suppression config.

**The path is live on the live box, and that is a deployed value, not a
default.** `INSTANCE_MODE = "live"` at `fly.live.toml:81`; the repo default is
`demo`, and the hub is constructed only off-demo. Confirmed at runtime this
session: `/api/health` reported `live_quotes_available: true`, which reads
`hub is not None and hub.is_running`.

## Decision

**Delete `_resubscribe`**, and move its existence into the docstring that
rejected it. The deletion is safe precisely because the evidence is not in the
code — it is in `_resync_all`'s reasoning, which stays.

The docstring now names the deleted helper and states the condition for ever
rebuilding it: **first observe what Kalshi answers a redundant subscribe
with.** That is the single fact its correctness turns on, and the one nobody
has.

## Consequences

- `backend/kalshi/ws.py` — 12 lines removed, 8 added to `_resync_all`'s
  docstring. No behaviour change: the code was unreachable.
- `tests/test_ws_client.py` — its module docstring recounts the historical bug
  in terms of `_resubscribe`; a parenthetical now records that the function is
  gone and that the sid registry it needed is still load-bearing, so the
  tests below stand unchanged. 37 tests green across
  `test_ws_client.py` and `test_public_read_only.py`; `ruff` clean.
- **The "built but never called" tally drops from five to four.** This one
  should not have been counted with the others, and the distinction is worth
  keeping: a module with no caller is a feature that does not run; a *helper*
  with no caller may be the losing side of a decision that was made properly.
  Grep found both the same way. Only reading the neighbouring docstring told
  them apart.

## What this does not decide

- **Whether the sequence-gap branch has ever fired in production.**
  `_resync_all` logs a `SequenceGap` before raising, and nothing persists it —
  no table, no counter — so the only record is Fly's log buffer, which is
  lossy. If it has never fired live, then `_resync_all` itself is untraversed
  in production and the question of what `_resubscribe` would have done is
  doubly moot. Not established, and not required for this deletion.
- Whether `RESUBSCRIBE_S = 120.0` and `receive_timeout_s = 60.0` are the right
  intervals. Neither has an env override; both are code defaults **in force**
  rather than defaults mistaken for values. The 60s timeout binds first for a
  dead socket, so the 120s rebuild governs only which tickers are subscribed.
