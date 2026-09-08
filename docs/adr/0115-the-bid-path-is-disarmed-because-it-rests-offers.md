# ADR 0115 — The bid path is disarmed, because it rests offers and he asked to be rid of those

Status: accepted
Date: 2026-09-08

Supersedes the arming decision recorded in `backend/store/combo_orders.py`
(2026-08-30). Does not supersede ADR 0084, which decided how a resting bid
routes and reconciles; that reasoning is intact and is what makes re-arming a
one-line change rather than a rebuild.

## Context

`POST /api/parlays/bid` places a real good-till-cancelled bid on a Kalshi
combination. It was armed on 2026-08-30 — `COMBO_ORDERS_ARE_DRY_RUNS = False`
— in Joe's own words: *"the exchange is done. arm the switch."* Its blocking
precondition was verified rather than assumed: shard 1 read $21.4100, up from
$0.0100, so a bid could actually be paid for.

**On 2026-09-06 he asked for the offer-making controls to be removed** —
*"I don't want to make offers or find offers in shares"* — and the UI came out.
CLAUDE.md records that half of the ruling as **still standing** as of
2026-09-08, alongside the correction that he does bet through the cockpit into
Kalshi by paying the ask.

**The endpoint behind the removed UI stayed armed.** For two days the desk kept
a live, real-money, offer-resting door open onto a thing its owner had said he
did not want, reachable by anyone holding the session cookie, with no screen
that could reach it.

That was surfaced as an open question with three options and the facts under
each. He answered: **"disarm the bid path."**

### What was established first

- **Nothing was resting.** All five bids `combo_orders` has ever held are
  terminal: four `cancelled` when their first leg started, one
  `gone_at_venue`. So the flip stranded nothing, and no option was
  time-pressured.
- **Zero UI callers.** No `.tsx` imports `placeComboBid`, `cancelComboBid` or
  `listComboBids`.
- **It was not under-guarded**, and an audit saying so was retracted before
  this decision was put to him. `require_auth` refuses on `is_demo` before
  reading a token, so the arming discipline was already equivalent to the
  hand-bet path's. **This is not a safety fix and must not be recorded as
  one** — the reason is that the feature contradicts a standing instruction,
  which is a different and weaker claim than "it was dangerous".

## Decision

`COMBO_ORDERS_ARE_DRY_RUNS = True`.

One line, in a commit of its own, which is the procedure the constant's own
comment specified and the `MANUAL_ORDERS_ARE_DRY_RUNS` convention from
ADR 0063. An environment variable was refused for this switch when it was
built, and that still holds: *a switch somebody can nudge at 2am is not a
decision with a commit behind it.*

**The interlock worked and is worth recording.**
`test_the_armed_state_is_stated_here_so_a_flip_is_never_silent` asserted
`is False` and went red the moment the constant moved — exactly as its own
docstring predicted. It is now
`test_the_disarmed_state_is_stated_here_so_a_flip_is_never_silent`, asserting
`is True`, with the reason in the docstring. The acknowledgement is the point;
the assertion is only the trigger.

## What this does NOT do

- **The route, table, watcher and cancel path all stay.** A dry run still
  writes the `combo_orders` row and still returns *"Nothing was sent to the
  exchange"*, so the path stays rehearsable and the record of intent stays
  intact.
- **Deleting it was one of the three options and is not what he chose.**
  Do not "finish the job" by removing the route, the `api.ts` helpers or the
  `/parlay-bid` proxy on the reasoning that a disarmed path is dead code. It
  is disarmed, which is a different state, and re-arming is one line by
  design.
- **The hand-bet TAKER path is untouched and stays armed.** He pays the ask
  there — the half of the 2026-09-06 ruling that always stood, and the path
  that took its first two real fills the same day.
- **The engine is untouched.** `ORDERS_ARE_DRY_RUNS` was already `True`,
  `gate.py` still cannot read `combo_orders`, and no interlock population
  moves.
- **`COMBO_ORDER_MAX_SPEND_TENTHS` ($3.00) is untouched.** ADR 0112 removed
  the desk's ceilings from the hand-bet taker path and never reached this one.
  With the path disarmed the cap binds nothing real, and it should be left
  alone rather than tidied — it is the ceiling that would apply on re-arming,
  and quietly raising it while nobody is watching is how a removed cap comes
  back by accident.

## The switch is now readable from outside

`GET /api/health` gained `order_paths_dry_run`, reporting all three money
doors:

    "order_paths_dry_run": {
      "manual_orders": false,     # ARMED - he pays the ask
      "combo_bids": true,         # DRY   - this decision
      "engine_orders": true       # DRY   - always has been
    }

**Why this is not decoration.** All three switches are compile-time constants
with no environment override — deliberately, because arming should be a commit
rather than something nudgeable at 2am. The side effect was that *"is it
actually disarmed on the box?"* could only be answered by reasoning about what
a deployed sha contained. That is a claim about a commit, not a reading of the
running process, and this repo keeps a standing lessons entry about
verification methods that report health without looking.

`True` means DRY: the row is recorded and nothing is sent.

The test reads the values **through the modules** rather than restating the
literals, so it does not become a second place the arming state is written
down. `tests/test_combo_bid_routes.py::TestTheSwitch` owns the value; the
health test owns only that the wire reports it faithfully.

## Re-arming

Set the constant `False`, change the test to `is False`, and say why in the
docstring. If the reason is that Joe wants to make offers again, that reverses
the 2026-09-06 ruling and needs his words, not an inference from a screen or a
backlog item.
