# 0149 — The API cannot fund a shard, and neither can Joe any more

Written on `main` with no lane open; **0149 taken after `git fetch`** with 0148
the highest on `main`, per `docs/adr/README.md`. **No schema change.**

Date: 2026-09-14
Status: accepted
Scope: the finding, the ticket copy it corrects, and
`scripts/set_target_balance_allocation.py`. **`backend/api/routes.py` check 9a
is UNCHANGED and this ADR is the argument for leaving it alone.** Supersedes
the remedy half of ADR 0148 §4 and reopens ADR 0084's premise.

---

## 1. The finding

**A combination bet cannot be placed through this cockpit at all, and it is not
our defect.** Kalshi's API refuses an order whose exchange shard is
underfunded; Kalshi's own app quietly moves the money before submitting, and
does not do that for an API client; and Kalshi has removed the control that let
Joe move it himself.

Three things measured on 2026-09-14, in this order:

1. **`kalshi.com/account/exchange-indexes` is now read-only.** Read directly in
   Joe's browser: four balance cards and the "Disable balance management"
   toggle, then the footer. No transfer control anywhere on the page. The
   accessibility tree carries navigation links and one unlabelled button (the
   toggle) and nothing else.
2. **Auto-management does not fund a shard at rest.** The toggle was OFF
   (management ON) and the Combos shard still held one cent while the Default
   shard held effectively the whole balance.
3. **The API refuses, 3 for 3.**
   `scripts/probe_resting_combo_order.py` posted a 1-contract GTC buy at 2c on
   a live `KXMVECROSSCATEGORY-SHARD1` combination, three times, spaced. Every
   one returned **400 `insufficient_balance`**. A refused order moves no money,
   so the whole experiment cost nothing.

Kalshi's docs agree and say it plainly: *"Kalshi's collateralization checks
will continue to run within the matching engine. Programmatic traders must
preallocate collateral on a given exchange shard before order placement."*

A fourth reading closed the last gap: `GET /portfolio/target_balance_allocation`
returned **`{"allocations": []}`** — no standing allocation had ever been
configured, so nothing was ever going to fund that shard on this account.

## 2. What this settles, and what it does not

**Settled: check 9a is correct and stays.** It was suspected this session of
being a false brake — refusing bets the venue would accept, which is the
failure ADR 0112 exists to prevent and would have outranked everything. It is
not. It refuses exactly what the venue refuses, one round trip earlier. The
three probes are direct evidence at the venue, with the auto-management toggle
state **known** (unlike the 2026-08-30 observation, which never recorded it).

**Settled: ADR 0148 §4's remedy was wrong within hours of shipping.** That
ADR had the ticket tell Joe the shard "has to be allocated there first, at
kalshi.com/account/exchange-indexes". The page cannot do that. Instructing an
impossible action is worse than naming no remedy, because it sends him away to
fail instead of to the venue that will take the bet. Corrected here; ADR 0148
is not edited.

**Not settled: whether a target allocation is the fix.** `POST
/portfolio/target_balance_allocation` with `0=80, 1=20` returned 200 and reads
back correctly — and the balance had **not moved after ~4 minutes**, roughly 24
cycles of the documented 10-second rebalance clock. So the allocation is stored
and inert.

The hypothesis that fits every observation is that **the target allocation only
takes effect when "Disable balance management" is ON** — the two are
alternatives, not layers, and the toggle's own text says disabling it "will
require manually distributing funds to an exchange shard", which is what the
allocation endpoint is for. **Untested**, because testing it means turning off
the mechanism that currently makes Joe's website betting work, and the test
window overlapped first pitch. His call, deferred by him.

**Not settled: whether `read_shard_funds` reads the right number.** It reads
`balance_breakdown[].balance`; Kalshi defines spendable-per-shard as balance
*minus the value of resting orders*, and now publishes
`resting_order_value_breakdown`. If `balance` is gross, 9a is *permissive* — it
would pass an order the engine refuses. Opposite direction from the risk
investigated here, same line of code, and one capture settles it.

## 3. The decision

- **Check 9a is unchanged.** No brake is added and none is removed.
- **The ticket tells the truth about where the bet can be placed.** It names
  the shard and its balance, says Kalshi's app moves money for its own orders
  and not for ours, says the desk will not move money either, and says the bet
  is placeable on kalshi.com and not here. The dead URL is now **forbidden** by
  test on both surfaces that carried it.
- **`scripts/set_target_balance_allocation.py` is added, read-first.** It reads
  the current allocation and the per-shard balances, and sets a split only
  behind an explicit money flag. It calls `target_balance_allocation` and
  **not** `intra_exchange_instance_transfer`: ADR 0084 refused the latter
  because the venue warns it "run[s] in up to three non-atomic steps" whose
  completed steps are not undone on failure. A target allocation is
  declarative, idempotent, reversible by setting it back, and the venue owns
  the retry — a different object from the per-order transfer ADR 0084 ruled on.
- **ADR 0084's premise is recorded as void.** It ruled the desk never moves
  money *because the operator can do it at that page*. The operator can no
  longer do it at that page. The conclusion may still be right; the argument
  for it is gone, and a successor must re-argue it rather than cite 0084.

## 4. Why this matters more than the defect it grew out of

ADR 0148 fixed a sentence that blamed Joe's typed amount for an empty wallet.
This is the reason the wallet is empty and stays empty: **every combination bet
he makes through the cockpit is refused, and the same bet on Kalshi's website
fills.** Combinations are what he actually bets — all seven real `manual_orders`
rows are `KXMVECROSSCATEGORY-SHARD1`.

So the mechanism pushing his betting off the desk is now named and measured.
`docs/measurements/2026-09-04-presence-at-the-moment-of-a-bet-result.md`
returned UNRESOLVED — CONCENTRATION with no mechanism to point at. It has one
now. That measurement is **not** reopened by this and may not be cited as
though it were; what changed is that a cause exists where before there was only
a rate.

## 5. Reopen trigger

The toggle test in §2: turn "Disable balance management" on, watch whether the
standing allocation funds shard 1, and re-run the 2c probe. If it funds and the
order rests, combinations become placeable through the cockpit and this ADR's
§1 conclusion narrows to "only without a target allocation". If it does not,
the next question is whether the desk should call
`intra_exchange_instance_transfer` itself — which needs its own ADR and
reverses ADR 0084 on the merits rather than on a dead premise.
