# 0147 — The weakest leg is chosen before its book is read, and that ordering stays

Written on `main` with no lane open; **0147 taken after `git fetch`** with
0146 the highest on `main`, per `docs/adr/README.md`. **No schema change, no
code change.** This ADR refuses a fix.

Date: 2026-09-14
Status: accepted
Scope: `backend/hedge.py::assess` (leg selection, `:776`–`:813`),
`backend/core/hedge.py::HedgeQuote.refusal` (`:174`–`:187`),
`tests/test_hedge_positions.py`. Nothing under `backend/api/`,
`backend/store/` or any order path is touched.

---

## 1. The item, as it was carried

`tasks/NEXT.md` (fifteenth session, "Known and declined") recorded:

> **`assess` picks the weakest leg before checking book status**, so a settled
> leg priced lowest makes the whole block a `market_closed` refusal even with
> a hedgeable live leg beside it. Words, not a raise. Unruled.

It was the only item on that list marked *unruled*. This ADR rules it, and the
ruling is **declined — the ordering is retained on purpose**. An unruled item
is how a future session either re-derives the trace at full cost or, worse,
ships the obvious fix; the obvious fix here is a money-touching regression.

## 2. What the code actually does

`assess` filters twice before it sorts:

    :754  any leg outcome == 'lost'   -> STATE_DEAD, returns
    :763  any leg outcome == 'void'   -> STATE_VOID_LEG, returns
    :776  pending  = legs with outcome == 'pending'
    :788  hedgeable = pending legs whose ticker is in `books`
    :813  weakest  = min(hedgeable, key=(price_of, leg_index))

Then `quote_for_hedge` builds a `HedgeQuote` for that one leg and
`refusal()` runs, with `MARKET_CLOSED` as its **first** check
(`core/hedge.py:182`, against `TERMINAL_STATUSES = {closed, settled,
finalized, determined}`). Selection therefore precedes status, exactly as the
item said.

**But the item's stated cause is wrong.** A leg the venue has *settled* cannot
be selected: `resolve_from_venue` would have written `won` or `lost` and the
`:754` short-circuit would have returned `STATE_DEAD` first. The reachable
case is narrower and is a **clock skew between two different fields**:

- `parlay_position_legs.outcome` is written by `resolve_from_venue`
  (`backend/hedge.py:456`) off `kalshi_markets.result`, which only
  `market_results.py`'s full pass writes, and only for a result that parses as
  `yes`/`no`. Anything else leaves the leg `pending` — deliberately, because
  unreadable must not resolve to a loss.
- `HedgeQuote.status` is read **fresh from the venue** on the current
  `/hedge` cycle.

So between the venue marking a market `closed` and `market_results.py`
recording its `result`, the leg is `pending` in our database and terminal on
the wire. If it still carries a resting bid, `price_of` returns a real
probability, and if that probability is the lowest of the pending set the leg
wins the `min` and the whole block refuses with `market_closed`.

Two boundary conditions worth pinning, because both narrow the window further:

- An **unreadable** bid sorts `2.0` — last, not first (`:805`, with its own
  comment). A terminal market with an empty book is therefore never selected.
  The scenario needs a terminal market that is *still quoted*.
- A leg winning at close prices high and is never selected. Selection requires
  the leg to be the one the market priced **weakest at the moment trading
  stopped**.

## 3. Why the fall-through fix is refused

The obvious repair — skip legs whose book is terminal, fall through to the
second-weakest — is worse than the defect, for a reason that does not depend
on any probability estimate:

**`/hedge` exists to price the exit on the leg that endangers the ticket.** If
the endangered leg cannot be hedged, there is no hedge to offer. Pricing the
*second*-weakest leg does not protect the ticket; it spends real money on the
leg that was never the problem, while the leg that was the problem sits
un-hedgeable and, on this path, has almost certainly just stopped trading
against us. The screen would show a priced, actionable hedge for a ticket
that is about to render `STATE_DEAD` on the next cycle.

The current ordering prevents that by accident. It is being made deliberate
here rather than left as an accident, which is the whole point of the
document.

The one thing that is genuinely wrong is a sentence of copy. `market_closed`
reads "*the venue is done with it, so there is nothing to buy*", when the
honest sentence in this window is closer to "*this ticket may have just died
and the venue has not published the result yet*". That is **not fixed here**
— see §5.

## 4. Reachability, stated at its real strength

This is established **by construction from source**, not observed. It has
never been seen on live and could not have been: all four `parlay_positions`
rows are `STATE_DEAD`, `/hedge` has produced zero locks in its life, and no
position has been recorded since 2026-09-10. Any claim that this fires at some
rate would be invented. The mechanism is real; its frequency is unmeasured and
unmeasurable on the current record.

Note also that this is not the way `/hedge` actually blanks in practice. The
observed-plausible failure is `get_conn`'s 25 s budget exhausted by
`build_payload`'s sequential per-ticker Kalshi reads, which returns 503 and
renders the whole screen as "Backend unreachable" (fifteenth session, known
and declined). That binds *before* leg ordering does — so relaxing the
ordering would change no symptom a person has seen.

## 5. What this ADR does and does not authorise

**Does:**

- Retain selection-before-status in `assess`. A change to that order needs a
  successor ADR naming what this one got wrong.
- Add the pinning test the trace found missing. `tests/test_hedge_positions.py`
  covers no case with **two pending legs both present in `books`**, one
  terminal and one live:
  `test_nothing_to_hedge_and_nothing_readable_are_different_answers` (`:896`)
  passes a single-entry `books`. The new test asserts the terminal leg **is**
  selected and the refusal **is** `market_closed` — i.e. it fails if someone
  ships the fall-through.

**Does not:**

- Change the `market_closed` copy. It is the honest complaint in §3, and it is
  still declined: the window is self-healing within one `market_results.py`
  pass, no person has ever read the sentence in this state, and every `/hedge`
  change ships validated on synthetic rows only — a posture this repo has
  already accepted once (ADR 0145) and should not accept twice for cosmetics.
- Promote anything else from the known-and-declined list.

## 6. Reopen trigger

**The first `parlay_positions` row that is not `STATE_DEAD` while its game is
running.** Until such a row exists, no `/hedge` change can be validated against
anything but synthetic fixtures, and `/hedge` work is unfundable — including
the copy fix in §5. When one does exist, the copy sentence and the 25 s
timeout are both in scope and rank above this ordering.
