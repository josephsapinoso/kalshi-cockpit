# 0066 — The pass control lives on the market screen, not the slate row

**Date:** 2026-08-22
**Status:** Accepted.
**Builds on** slice B6 (`desk_passes`, `POST /api/desk/pass`) and ADR 0063's
manual ticket; **changes nothing** about what the pass record stores or how
it is served.

## 1. What happened

`POST /api/desk/pass` was complete, tested, and had no frontend caller. The
record could hold every bet Joe placed and no evidence he ever looked at a
market and walked away — the decision the table exists to make countable was
still unrecordable from any screen. The only question left was *where* the
control goes, and two placements were argued: the market screen, or a
per-row control on the slate.

## 2. The decision

**The pass control is one bordered secondary pill on `/market/[ticker]`,
rendered directly below the manual ticket.** That is where the deciding
happens: the scout desk's facts, the quote strip, and the ticket are all on
that screen, so "I looked at this and chose not to bet it" is a sentence
about that screen. It follows the ticket in the document order and is
deliberately not styled as the ticket's sibling — a quiet `border-border`
pill (TonightStrip's), never `bg-accent`, because red is money (ADR 0061 §3)
and a pass must read as the calm alternative, not as a rival call to action.

Three rules carried in from the gestures that already exist:

- **No confirm dialog.** TonightStrip and NotTonight both record why: "a
  dialog gives the impulse a veto." A pass is the safe direction; it needs
  the veto least of anything in the product.
- **Reason optional, collapsed.** Passing without a reason is one tap; the
  reason field is behind a small disclosure. `DeskPassRequest` already rules
  that a required reason is a toll on the correct boring action.
- **Records, does not hide.** On success the control reads "Passed" and
  disables; the market's facts stay on screen. A pass is a decision about
  tonight, not a curtain over the market — and it blocks nothing, which the
  control says in a tap-visible Hint.

## 3. The per-row slate placement is rejected

Not deferred — rejected, for three reasons that compound:

1. **The 390px geometry has nowhere honest to put it.** The slate's Row is
   server-rendered, and its only 390px-safe region is the full-width stack.
   A per-row control means a Pass bar under every game on a scan list that
   can run 40 rows deep — the quietest gesture in the product repeated forty
   times becomes the loudest thing on the screen.
2. **A tap-cheap pass converts the floor into noise.** `passes.py` records
   a *floor on deliberate passes* — only taps are counted, so every tap must
   be a decision. A control reachable mid-scroll on every row invites
   passing as tidying ("clear the ones I'm not reading"), and the /bets
   decisions headline counts each of those taps as a decision. The record
   inflates in the flattering direction, which is the one direction this
   repo's measurement rules exist to guard.
3. **Night + market is the complete ladder.** "Not tonight"
   (`scope='tonight'`, via TonightStrip/NotTonight) passes the whole night;
   the market-screen control passes one market *after looking at it*. A
   third rung — per-row, cheaper than the market screen's — would make the
   least-considered pass the easiest to record, which is the wrong gradient:
   cost should fall as consideration rises, not as it drops away.

## 4. Constraints that stand

- **No rate, ratio, streak, or average over passes, ever.** The served
  payload is `{total, first_ms}` and
  `tests/test_desk_passes.py::test_the_headline_numbers_are_served_as_counts_only`
  pins the key set. A pass is never scored against an outcome.
- **Append-only, no dedupe.** The same test module greps every backend
  source file for UPDATE/DELETE on `desk_passes`. Idempotence is UI state —
  the control disables after success — not a DB constraint; two deliberate
  passes on different evenings are two decisions.
- **Auth like every mutation.** The browser holds no bearer token; the
  `/pass` Next route handler holds it server-side (the `/scout-desk`
  pattern) and is named in `middleware.ts`'s `JSON_ROUTE_HANDLERS` so an
  expired session gets JSON 401, not an HTML login page behind a 200.
