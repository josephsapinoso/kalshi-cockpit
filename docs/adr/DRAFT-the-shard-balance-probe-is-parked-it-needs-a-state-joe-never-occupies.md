# The shard-balance probe is parked, because it needs an account state Joe never occupies

**Status:** draft, no ordinal — main assigns the number at merge. Accepted as a
**park of a queue item**, and as nothing else. The question it would settle —
is `balance_breakdown[].balance` gross or net of resting orders? — is **not
answered here and is not closed.** **Joe has not ruled on this.** Every
`tasks/NEXT.md` entry that carried the item says *"Joe's call"*; this ADR
records the partner's standing recommendation, the fact that nothing has
argued against it, and the decision to stop paying for the item's place in the
queue. It does not convert either of those into his answer.

**Date:** 2026-09-15
**Scope:** `tasks/NEXT.md`'s standing probe item. **No code changes**, no
schema change, no deploy. `scripts/probe_resting_combo_order.py` and its
tests stay exactly as ADR 0151's session left them.

---

## 1. The item, and how long it has been standing there

`scripts/probe_resting_combo_order.py` places one 2c GTC bid on a live shard-1
`KXMVE` combination, reads `/portfolio/balance?exchange_index=<shard>` while
the bid is resting — *the only second this repo ever has a known resting
order* — and cancels it. It is a real order on a real account, so it runs only
with Joe at the keyboard.

The line **"Run the fixed probe once, with Joe at the keyboard"** has been
carried in five consecutive `tasks/NEXT.md` entries:

| entry | line | how it appears |
|---|---|---|
| 2026-09-14, seventeenth session | `NEXT.md:1107` | item 1 — origin, written the session the cancel bug was fixed |
| 2026-09-15, eighteenth session | `:982` | item 2, "carried from the seventeenth entry" |
| 2026-09-15, nineteenth session | `:874` | item 3, "(carried)" |
| 2026-09-15, twentieth session | `:677` | item 2 — **the partner first recommends PARKING it with an ADR** |
| 2026-09-15, twenty-first session | `:364` | item 3 — "The partner *again* recommends PARKING… it has now survived several sessions unchallenged" |

The *question* is older than the task. It enters as item 3 of the sixteenth
entry (`NEXT.md:1270`, 2026-09-14) and as the third "Not settled" of
**ADR 0149 §2**, written the same day: `read_shard_funds` reads
`balance_breakdown[].balance`, Kalshi defines spendable-per-shard as balance
*minus resting-order value*, so if `balance` is gross then check 9a is
**permissive** — it passes an order the venue refuses.

So: six entries have carried the question, five have carried the probe as a
task, none has run it, and the two that carry the recommendation to park drew
no argument against it. **"Unchallenged" is a description of the record, not
evidence.** Nobody has argued for the probe either; the item has simply been
re-typed.

## 2. What the probe would settle, read at source

`read_shard_funds` (`backend/store/combo_orders.py:195`) parses
`balance_breakdown[]`, matches on `exchange_index`, and converts the row's
`balance` — dollars as a 4dp string — to tenths. It has three callers:

- `backend/api/routes.py:3158`, the read path: the shard balance that feeds
  `_manual_authorised_count` (`:3002`), which is the **"of N authorised"**
  number `ManualTicket.tsx` disables the confirm button above;
- `backend/api/routes.py:3763`, inside `POST /api/manual-orders` — **check 9a**
  (`:3721`), on the one armed real-money path;
- `backend/combo_bids.py:148` → `check_affordable`, on the bid path, which is
  dry (`COMBO_ORDERS_ARE_DRY_RUNS = True`, `combo_orders.py:101`, ADR 0115).

**Gross and net differ by exactly one quantity: the value of orders resting on
that shard.** With nothing resting they are the same number, and every caller
above is reading the right one.

## 3. The argument for parking

**Joe does not rest orders, and the desk cannot rest one for him.**

- He said so: *"I don't want to make offers or find offers in shares"*
  (2026-09-06), and on that ground **ADR 0115** disarmed
  `POST /api/parlays/bid`, the only route in this repo that sends
  `time_in_force="good_till_canceled"` (`backend/combo_bids.py:164`).
- The armed path sends **`immediate_or_cancel`** (`routes.py:3716`). An IOC
  fills against visible depth or dies; its remainder does not rest. So no bet
  Joe places through this cockpit can put the account into the state where the
  two readings diverge.
- The one other place a GTC is described — `_place_order`'s comment at
  `routes.py:2565`, "a plain GTC limit… a bid lifted in between leaves a
  resting remainder" — is on the **engine** path, and the engine is dry
  (`ORDERS_ARE_DRY_RUNS = True`, `backend/store/orders.py:129`) and has never
  placed an order.

So the probe's cost is not "a few cents". It is **manufacturing the single
account state the desk is built to avoid**, in order to measure a difference
that is zero in every state the account actually occupies. ADR 0150's own
tail is the demonstration: the 2026-09-14 run's cancel omitted
`?exchange_index`, 404'd, and left a real resting order on the account to be
taken back by hand. The script has since been fixed and its tests pin the fix,
but the incident is the honest price of the look — the probe is the only thing
that has ever put a resting order on this account, and it is being proposed in
order to read one.

**And the failure mode, if the assumption is wrong, is permissive rather than
costly.** If `balance` is gross, the desk lets through an order the venue
rejects — **400 `insufficient_balance`** (the status observed three times,
ADR 0149 §1). That is a refused order. A refused order moves no money, records
no fill, and is the venue's own rule arriving one round trip later than it
could have. It is **not** a missed bet, not a wrong price, and not a number
in the risk path.

## 4. The decision

1. **The probe comes off the queue.** It is not scheduled, not ranked, and not
   carried forward. A session that reaches this file should not re-add it.
2. **Nothing is asserted about gross vs net.** `read_shard_funds`'s docstring,
   check 9a, `_manual_authorised_count` and ADR 0149 §2 all stay exactly as
   written. ADR 0149 §2 remains the live statement of the open question; this
   ADR parks the *task*, not the *uncertainty*.
3. **No brake is added and none is removed**, in either direction. Check 9a is
   unchanged, as it has been since ADR 0149 §3 and ADR 0150 §5.
4. **The park rests on the partner's standing recommendation and on nothing
   stronger.** It is not Joe's ruling, it is not a measurement, and it may not
   be cited as either. A later session citing this ADR is citing an argument,
   which can be wrong, not a decision Joe made, which cannot be overruled by
   argument.

## 5. What unparks it

Any one of these, and the question is live again with no further permission
needed:

- **Joe says one sentence: "re-arm the bid path"** — or anything that means he
  wants to rest an offer. That reverses the 2026-09-06 ruling ADR 0115 records,
  and it needs his words rather than an inference from a screen or a backlog
  item (ADR 0115, "Re-arming"). The moment an order of his can rest, gross and
  net can differ on a shard he is betting from, and §3's whole argument is
  void.
- **A venue balance refusal is actually seen on the money path** — a
  `400 insufficient_balance` on an order that check 9a passed. That is the
  permissive failure firing, and one sighting turns a theoretical direction
  into an observed defect. `api_read_incidents` and the manual-order record
  are where it would show; nothing today watches for it specifically, which is
  itself a thing a future session may decide to fix instead of running the
  probe.
- **The venue starts publishing `resting_order_value_breakdown` on this
  account.** Both 2026-09-14 balance captures carried
  `balance_breakdown[].balance` and **no such field at all**; ADR 0149 §2 names
  it because Kalshi documents it. If it appears, the question is answerable
  from a *free read of the existing balance call* with nothing resting — the
  entire cost argument in §3 evaporates and the look should simply be taken.

## 6. What the park costs if §3 is wrong

Bounded, and worth stating rather than leaving as "it's fine":

- **The screen can overstate `authorised_contracts`.** A gross balance makes
  the ticket's "of N authorised" larger than the shard can pay for, and that is
  a number on a screen, not only a refusal at the venue. It is wrong *only
  while something rests on that shard*, which is the same condition the
  question needs — so under §3's premise the count is exact in every state that
  has occurred.
- **A tap can be spent on a refusal.** Check 9a exists (`routes.py:3721`)
  precisely because a bare `insufficient_balance` against a $22 account
  *"reads as a broken cockpit rather than as 'your money is in the other
  pocket'"*. A permissive 9a hands Joe the bare refusal 9a was built to
  prevent.
- **ADR 0150 §4 names why that is the expensive part**: a screen that tells Joe
  something false about his own money teaches him to stop believing the screen,
  which is the one thing a price-transparency tool cannot afford (ADR 0071
  §2.2).

None of that moves money, and all of it is repairable by the look this ADR
declines to schedule. That is the trade being made, on purpose, and it is
reversible by any of §5.

## 7. Limits of this ADR — what was not verified at source

- **That Joe never rests an order at the venue itself.** This repo can
  establish that *it* cannot rest one for him (§3) and that he asked for
  offer-making to be removed (ADR 0115). It cannot see his kalshi.com
  activity, and ADR 0150 §6 records him operating that account by hand. A
  resting order placed in Kalshi's own app would satisfy the probe's
  precondition without anything here knowing — and would not be visible to
  this argument.
- **The "no `resting_order_value_breakdown`" reading is second-hand.** It is
  recorded in `tasks/NEXT.md` (seventeenth entry) from two live captures.
  Captures are operator data and are gitignored, so the payload could not be
  re-read here; a grep of the tree finds the field named only in ADR 0149.
- **The 2026-09-14 "23:34:43Z shard 1 unchanged after the 23:28:57Z 201"
  reading is not evidence of gross**, and the same entry says why: nothing
  records when Joe's hand cancel landed, so the window may not contain the
  input. It is listed here so no later session mistakes it for a partial
  answer.
