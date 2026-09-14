# 0150 — An empty wallet is a state, not a closed path

Written on `main` with no lane open; **0150 taken after `git fetch`** with 0149
the highest on `main`. **No schema change.** **Corrects ADR 0149 §1 and §4**,
which are wrong as written and were live on the screen for one deploy.

Date: 2026-09-14
Status: accepted
Scope: `frontend/src/components/ManualTicket.tsx` copy,
`tests/test_buy_controls.py`, `scripts/set_target_balance_allocation.py`
(gains a shard-to-shard transfer). Check 9a is still unchanged.

---

## 1. What ADR 0149 got wrong

It concluded, and shipped to the screen:

> A combination bet cannot be placed through this cockpit at all […] this bet
> is placeable on kalshi.com and not here.

**False, and refuted by this repo's own record.** `manual_orders` holds seven
real rows, six filled, and **every one is `KXMVECROSSCATEGORY-SHARD1`** —
combination orders placed through `POST /api/manual-orders`, the API path, and
filled on 2026-09-08, 09-09 and 09-10. The audit establishing that was run at
the start of the same session that then declared the path closed.

What was different on those dates is the only thing that was different: **the
shard was funded.** Check 9a's own comment block records shard 1 at $22.24 on
2026-09-08; `kalshi-shards-collateral` recorded $14.17 on 09-09. On 2026-09-14
it held $0.01 against $22.68 on Default.

So the three `insufficient_balance` probes measured **an empty wallet, not a
closed path.** Every one of them is still valid; the generalisation drawn from
them was not. The correct claim is the narrow one: *an API order is refused
when its shard is underfunded, and Kalshi's app — unlike this tool — funds the
shard for you as you bet there.*

Joe rejected the conclusion on exactly this ground, from memory of his own
fills, before any of it was re-read.

## 2. Funding a shard is possible, and the mechanism was already in hand

`POST /portfolio/intra_exchange_instance_transfer` takes `source` and
`destination` of `event_contract` (Predictions) or `margined` (Perpetual
Futures) — **and** optional `source_exchange_shard` / `destination_exchange_shard`.

The account page exposes only the *instance* axis. That is why the page reads
as "you can only transfer between Predictions and Perpetuals", and why its
disappearance of a shard control was mistaken for the capability being gone.
**The shard axis lives on the same call and the UI simply does not surface
it.** A same-side transfer (`event_contract` → `event_contract`) across two
shards funds a shard.

This was in the research this session had already received and was not
connected to the question it answered.

## 3. What changes

- **The refusal copy states the state, not a property.** It names the shard
  and its balance, says the wallet has to hold the money before he taps, says
  bets on this shard have gone through from here **whenever it was funded**,
  and offers the two ways forward. Guarded: the strings "placeable on
  kalshi.com and not here" and "cannot be placed here" are now **forbidden**,
  and "whenever it was funded" is required.
- **`set_target_balance_allocation.py` gains `--transfer N --from-shard A
  --to-shard B`**, behind the same money flag, with before/after balances and
  a capture. Amounts are **centicents** (hundredths of a cent) — `$1.00 =
  10,000`, ten times this project's tenths, converted in exactly one place.
- **This is still not in the desk.** ADR 0084's objection stands where it
  actually applies: an *automatic, per-order* transfer on the money path could
  strand funds mid-sequence with nobody watching, because the venue warns the
  transfer "run[s] in up to three non-atomic steps" that are not undone on
  failure. A one-off, operator-run, captured transfer is a different object.
  **Joe executes it**; the agent is refused this by policy and did not run it.

## 4. The error, named, because it is the third of the day

Each of these was a claim about the world drawn from one observation of one
state, and each reached a user-facing surface before it was checked:

1. "Your $1 went to a different shard" — inferred, never observed, and the
   balance was unrecoverable afterwards (ADR 0148 §6 now records this).
2. "Kalshi could not have shipped a product where API users are stranded,
   therefore auto-management covers the API" — an argument from a third
   party's design coherence, with a false premise.
3. "Combos cannot be placed here" — three refusals against an empty wallet,
   generalised into a property of the path, while six filled combination
   orders sat in the local record.

The common shape: **a measurement of a state, restated as a property of the
system.** The tell is a sentence with no "while" or "when" in it. Three
refusals support *"while shard 1 holds a cent"* and support nothing about
*"at all"*.

The specific danger on this surface: a screen that tells Joe his own past
bets were impossible teaches him to stop believing the screen, which is the
one thing a price-transparency tool cannot afford (ADR 0071 §2.2).

## 5. What is still true from ADR 0149

- Check 9a is correct and stays. The three probes establish that.
- The account page is read-only and carries no shard transfer control.
- Auto-management does not fund a shard at rest, and
  `target_balance_allocation` returned `{"allocations": []}`.
- Auto-management does not fund a shard at rest, and `target_balance_allocation`
  was `{"allocations": []}` when this began.

## 6. Confirmed after §1-§5 were drafted — the toggle is the funding control

Joe turned "Disable balance management" **ON** and moved his whole balance to
Exchange 1 himself. **So the transfer control exists and appears once
auto-management is off** — its absence was the toggle's doing, not a
capability Kalshi removed. Read after: shard 1 `$22.6800`, shard 0 `$0.0065`.

The 2c probe was then re-run on the same combination that had refused three
times, and returned **201 accepted**. That closes the question in the
direction §1 predicts: *funded shard → order accepted*, and the earlier
refusals measured the balance and nothing else.

Two consequences recorded rather than left implicit:

- **Singles are now the unplaceable ones.** A single-market bet draws on
  shard 0, which holds two thirds of a cent. The constraint did not go away;
  it moved. Check 9a will say so correctly, and the §3 copy states it as a
  state.
- **The `0=80, 1=20` allocation was cleared** to `{"allocations": []}` on
  Joe's instruction, because under manual mode it could have pulled 80% back
  to Default and undone his move. Automatic rebalancing is off.

**The probe left a real order resting.** Its cancel omits `?exchange_index`,
so the `DELETE` 404'd — the exact failure `backend/kalshi/rest.py:655-670`
recorded on 2026-08-30 and this script never adopted. Cancelled by hand
(`reduced_by 1.00`); nothing is resting. Fixing the script is open work, as
is an unexplained **401** from the orders-list read in the same run.
- ADR 0084's premise — "the operator can do it at that page" — is still void.
  The operator does it at the **API** now.
