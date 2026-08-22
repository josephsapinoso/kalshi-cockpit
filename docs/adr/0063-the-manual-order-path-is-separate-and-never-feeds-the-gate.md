# 0063 — The manual order path is separate, and it may never feed the gate's populations

**Date:** 2026-08-22
**Status:** Accepted.
**Owner of the decision:** Joe, verbatim request 2026-08-22: *"I'd really
like to be able to purchase from this portal as opposed to going on the
Kalshi site."* Shape ruled by a partner convening the same day (ui-designer,
retail-bettor, sharp-bettor, tilt-prone-gambler, disciplined-gambler,
kalshi-platform; direction in the 2026-08-22 session record and the approved
plan).
**Touches nothing decided by** ADR 0015 (the gate's floor), ADR 0018 (arming
the *engine* path is a code change), ADR 0038/0062 (the hunt is closed; the
tool is a betting desk). This ADR opens a second, hand-driven door; it does
not move the first one.

## 1. What happened

Joe asked to place his bets from the cockpit instead of the Kalshi app. The
convening found the request is the *safety* fix, not the risk: `/bets` shows
7W / 32L, −$11.27 over 39 settled positions since Aug 18 — roughly ten hand
bets a night placed in the Kalshi app, where none of this project's controls
(lockout, exposure caps, the daily-loss kill switch) can bind. The lockout is
today enforced in exactly one place, `POST /api/estimates`
(`backend/api/routes.py:2612`): "Not tonight" blocks *writing down a
probability* and blocks no bet. An in-portal channel is the only channel his
own limits can ever reach.

## 2. The decision

**Build `POST /api/manual-orders`, a separate route writing a separate
`manual_orders` table, gated by its own `MANUAL_ORDERS_ARE_DRY_RUNS`
constant.** The engine's path (`POST /api/orders`, `orders` table,
`ORDERS_ARE_DRY_RUNS`) is untouched.

**The hardest NO: never synthesise a `recommendations` row to reuse the
engine path.** That option will be re-proposed because it sounds disciplined
(one path, sixteen checks). It is the most dangerous option available, for a
mechanical reason: `backend/gate.py`'s actionable population predicate is
`r.suppressed_reason IS NULL AND r.reference_contracts > 0`, and a synthetic
row satisfies it exactly. Hand bets would silently increment the
live-trading interlock's own 300-game counter — the number ADR 0015 says
neither the deposit nor Joe's discretion may move. ADR 0043 records the
identical near-miss on `fills`, saved only by the `source='engine'` filter
landing before the first hand row.

**What the two paths may share** (portable primitives with no population
side-effects): the live quote re-read, the depth check, `reserve_order`'s
in-transaction exposure arithmetic, and the idempotency-key convention.
Duplication of everything else is the price of an uncontaminated evidence
record, and it is the correct price.

## 3. The safeguards are part of the decision, not options

Limit orders only, `immediate_or_cancel` only (the create response *is* the
answer; no resting state to track). Max price prefilled at the ask and
enforced server-side. P(YES) entered before the price is revealed (ADR
0065). The order bearer token stays required — a session cookie never places
a bet. Demo unreachable by construction: `instance_mode == "live"` AND an
explicit env flag, both checked server-side. Size is a server-computed
ceiling rendered as "of N authorised" — no free-text quantity. No fee quote
on `KXMVE` tickers (the never-undercharge property fails on combos, ADR
0046); elsewhere the confirmation says "costs **at most** $X", never
"costs $X", and never a payout figure (H4 untested, ADR 0027). Positions are
read before offering the opposite side, because Kalshi nets. A fixed cool-off
follows every completed purchase, with no override. `lockout_until` returns
the same 423 as the estimate route, in the same commit that ships the button,
alongside rewritten scope sentences on `/gate` and `TonightStrip` — both are
truthful today and materially misleading the moment this path exists.

Blocking prerequisites, none waivable: the daily-loss switch rewired to
`venue_settlements` (ADR 0064); the create-order response observed on the
real wire before any parser is trusted (the C0 probe — the spec-transcribed
parser at `backend/kalshi/orders.py:496` has never seen a live payload, and
one `unrecognised_response` order would permanently occupy a $1.02 exposure
budget); the lockout wiring above.

**Arming is Joe's act**, by ADR 0018's pattern (a code change plus a deploy),
first at a 1-contract ceiling, raised only when observed `fee_actual` matches
`fee_predicted` on real fills. The assistant building this never places an
order on his behalf; the C0 probe itself is run by Joe.

## 4. Rejected, with reasons

- **Synthetic recommendation rows** — §2; contaminates the gate.
- **Reusing the `orders` table with a `source` column** — the population
  predicates that guard money (`current_exposure_dollars`, gate evidence,
  `fee_model_verified`'s future MISMATCH branch) all read that table;
  every one becomes a filter that must never be forgotten. A table is a
  boundary; a column is a convention.
- **Market orders / GTC** — reintroduces the order-state machine this design
  exists to avoid, on a venue whose order lifecycle this repo has never
  observed.
- **Confirm dialogs, bet tallies, self-report prompts** — refused as theatre;
  `TonightStrip`'s own docstring has the argument ("a dialog gives the
  impulse a veto").
