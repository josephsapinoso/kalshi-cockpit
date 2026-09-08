# ADR 0112 — The caps come off the hand-bet path, and the bet password moves server-side

**Status:** Accepted by Joe, 2026-09-08, in a batched interview. Ordinal 0112
taken at merge, 2026-09-08, after `git fetch` (`docs/adr/README.md`). It was
written as `DRAFT-` with no ordinal and renamed here, which is the rule that
exists because 0074 and 0077 were each claimed twice in one day and git said
nothing.
**Date:** 2026-09-08.
**Decides:** which of the hand-bet path's brakes exist, and what authenticates
a hand bet. Nothing else.
**Touches nothing decided by** ADR 0015 (the gate's 300-game floor), ADR 0018
(arming is a code change), ADR 0038 (the hunt is closed), ADR 0045 (the caps
are *derived* rather than typed — that derivation still governs the engine).

## 1. What Joe decided

Four answers, given 2026-09-08. Two of them were given twice: he was asked
again after being shown a consequence he had not been told about, and he did
not move.

| # | Question | Answer |
|---|---|---|
| 1 | The per-bet ceiling, ~$2.14 (10% of a ~$21 balance) | **Remove it. "i will decide."** |
| 2 | The daily-loss kill switch, also ~$2.14 | **Remove it too** |
| 3 | Which brakes to keep — typed code, 10-minute cool-off | **"none"** |
| 3b | The total-exposure ceiling, 40% of balance (asked separately, later the same day) | **"remove the exposure ceiling too"** |
| 4 | Should the loss counter still see his in-app Kalshi bets | **Yes, keep counting** |

Answer 4 survives answers 1–2 and is not contradicted by them. The **counter**
stays and keeps reading `venue_settlements`, so the desk still knows and can
still *say* what the day has cost across both places he bets. What is removed
is the **kill switch** that acted on it. Information, not a brake — which is
ADR 0071's stated job for this product in almost so many words.

## 2. What he was told before answering, because a decision is only his if the facts were

Both re-asks are recorded because the first framing of each was incomplete,
and an answer to an incomplete question is not consent.

**On the caps (re-asked).** The per-bet cap and the daily-loss switch are the
*same number* — `POSITION_FRACTION_OF_BANKROLL` and
`DAILY_LOSS_FRACTION_OF_BANKROLL` are both `0.10` of the observed balance
(`backend/config.py:543-545`). Removing only the first leaves the second
closing the desk on the first losing bet larger than $2.14. He was shown that
interaction and chose to remove both.

**On the typed code (re-asked).** It was put to him first as an anti-impulse
guard, which is how `ManualTicket.tsx:45-47` describes it. That is not all it
is. Its own note continues: *"a session cookie must never place a bet"* — the
typed act is also the **credential**. The fact he was not given, and then was:
today a person holding his unlocked phone with the cockpit open cannot bet his
money, because they would have to produce 43 characters they do not have.
After this change, being logged in is enough. He chose removal knowing that.

## 3. What is NOT changed, and why the scope stops here

**AMENDMENT 1, 2026-09-08 (same day): the exposure ceiling went too.** The
paragraph below and §1's table were written while the total-exposure ceiling
(40% of the observed balance) still stood, and this document said so twice --
it was the one brake Joe had not been asked about, so it was deliberately left
alone rather than swept up in an instruction that did not reach it.

He was then asked, and answered: **"remove the exposure ceiling too."**

So the class is now empty. `reserve_manual_order` no longer takes
`max_exposure_dollars` and can no longer raise `ExposureCapExceeded`; check 6
refuses nothing and survives only to derive the figure the recorded row still
carries, so a bet stays legible later as "this was N times the ceiling that
used to exist"; and an unobserved balance no longer refuses, because refusing
on a precondition for a guard that no longer exists is how a removed cap comes
back by accident.

**Two things did NOT go with it, and both are about reading rather than
capping.** `current_manual_exposure_dollars` is still computed, because the
figure is what the desk reports about the position he is building. And an
exposure that cannot be READ still rolls the transaction back:
"cannot determine the budget must never resolve to unlimited" is a rule about
an unreadable value, not about a ceiling, and an unreadable total means a
broken write whatever bounds apply. `tests/test_manual_orders.py::
TestTheReserveIsAtomic` was re-pointed onto that surviving refusal rather than
deleted, so the insert-then-check-under-BEGIN-IMMEDIATE guarantee is still
pinned.

**`orders.reserve_order` still caps the ENGINE**, on §3's scoping below.

Everything else in this document stands as written, including §4's sentence
and §5's reservation -- which now covers five brakes rather than four.

**The engine's caps are untouched.** `core.sizing.size_position` still refuses
an underived `RiskConfig`, and ADR 0045's derivation still governs it. Joe was
answering about betting through the cockpit by hand; reading that as
permission to unbrake the automated path would be widening the request. The
engine has never placed an order (`ORDERS_ARE_DRY_RUNS = True`) and is gated
besides, so nothing is gained by touching it and a real boundary is lost.

**The live-trading interlock is untouched.** `gate.py` still never reads
`manual_orders`, pinned by a source-substring test at
`tests/test_combo_bid_routes.py:564`. Removing a hand-bet cap must not move
the 300-game counter, and it does not.

**Auth is not removed from any route.** `require_auth`
(`backend/api/routes.py:393`) still guards every mutating route, and
`CLAUDE.md`'s rule — *every mutating route requires auth* — still holds
literally. What changes is **where the bearer token comes from**: Joe's
fingers, or the server. The second is not a new invention here; it is the
pattern `/refresh-odds` and `/api/parlays/lookup` already use
(`frontend/src/lib/api.ts:1101, 2255, 2457`), where the browser proves session
and a Next route handler adds the bearer server-side. The manual ticket was
the outlier, and the asymmetry was drift rather than a decision — the combo
routes have required nothing typed for as long as they have existed.

**The other server-side checks stay.** Idempotency, the desk lockout, the
KXMVE acknowledgement, the stale-ask refusal, depth at the ask, the existing
position check, and reserve-then-check under the write lock are correctness,
not policy, and none was put to him.

## 4. The consequence, stated plainly so nobody has to infer it

**After this change the cockpit will not stop Joe from placing a bet of any
size his Kalshi balance can pay for, and will not stop him after any number of
losses.** The venue's own collateral is the only remaining bound on size.

That is the intended outcome and it is his to intend. It is recorded here in
one sentence so that a future session finding a large loss does not read the
absence of a brake as a bug and restore it. **Restoring any of these requires
Joe, not a session's judgement.**

## 5. What would overturn this

Joe saying so — the same standard ADR 0105 §5 sets, and the one his 2026-09-08
correction met. Nothing else: not a bad day, not a drawdown, not a future
session's discomfort with §4.

## 6. What this does not establish

- **Nothing about whether he will use the path.** `manual_orders` has 0 rows
  of any kind after 14 days armed. This removes four reasons it might have
  been unusable; it does not demonstrate that they were *the* reasons, and a
  census after the change is the only thing that could.
- **Nothing about combo buyability.** Shard 1 holds $0.01 and every combination
  order is refused by `check_affordable` before it is sent, whatever this ADR
  says. Funding that shard is Joe's to execute and is not a code change.
- **Nothing about the fee model.** ADR 0012 §5 still records the combination
  fee as unverified and ADR 0046's model still undercharges there; the hedged
  coefficient still prices a KXMVE order.
