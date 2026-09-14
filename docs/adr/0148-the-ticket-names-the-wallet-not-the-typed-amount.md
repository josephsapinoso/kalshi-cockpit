# 0148 — The ticket names the wallet, not the typed amount

Written on `main` with no lane open; **0148 taken after `git fetch`** with 0147
the highest on `main`, per `docs/adr/README.md`. **No schema change.**

Date: 2026-09-14
Status: accepted
Scope: `backend/api/routes.py` (`GET /api/manual/market/{ticker}` payload only
— no order path, no check, no ceiling), `frontend/src/lib/api.ts`,
`frontend/src/components/ManualTicket.tsx`, `frontend/src/lib/glossary.ts`.

---

## 1. What happened

Joe tried to buy a `KXMVECROSSCATEGORY-SHARD1` combination through the
cockpit on 2026-09-14. Kalshi's book showed **25.7c with 945 contracts
resting**. He typed **$1.00**. The ticket said:

> Depth: 945 at the ask · you can buy 0 contracts — that is what this market's
> Kalshi wallet can pay for
>
> **Not enough: one contract costs 25.7c, so the smallest bet here is $0.26.**
> Trimmed to 0 — the book or your Kalshi wallet, not your typed amount, set
> the size. No cap of the desk's is involved.

He read it as the desk telling him his dollar was too small for a 26c
contract, concluded the tool was broken, **and placed the bet directly on
Kalshi instead.**

This is the failure ADR 0071 is about. The desk's job at the moment of a bet
is price transparency; it instead produced an untrue sentence and pushed the
bet off the tool. It is also the first time the cockpit has been measured
*causing* a bypass rather than merely failing to attract one — the
2026-09-04 presence measurement returned UNRESOLVED and had no mechanism to
point at.

## 2. The defect

`DollarAmount` computes two different numbers:

    affordable = floor(amountTenths / askTenths)   // $1.00 / 25.7c = 3
    contracts  = min(affordable, ceiling)          // min(3, 0)     = 0

`ceiling` is the server's `authorised_contracts`, which since 2026-09-08
carries the structural ceiling, the depth at the ask and **what the market's
exchange shard can pay for** — and no cap of ours (ADR 0112 Amendment 1).

The render then chose its sentence on `contracts`:

    contracts >= 1  ->  "Buys N contracts at ... each"
    otherwise       ->  "Not enough: one contract costs X, so the smallest
                         bet here is X."

The `otherwise` sentence is a claim about `affordable`. Selecting it on
`contracts` makes it fire whenever *anything* zeroes the size, and then it
blames the typed amount for a constraint the typed amount had nothing to do
with. **This repo's named failure — one predicate with two spellings, and the
screen naming the wrong one** — now on the money path for the fourth time,
and the second time in the direction of refusing a bet the venue would have
taken (`_authorised_for_side`'s own docstring records the first).

Worse, `capped = affordable > ceiling` was **also** true (3 > 0), so the trim
sentence rendered too. He got two sentences in one paragraph asserting
opposite causes.

## 3. Why the true cause was invisible

The real constraint was Kalshi's collateral sharding: the account is split
across numbered wallets, every market settles on exactly one, and **the venue
will not move money between them to pay for an order**. Measured on this
account twice — `$21.40` stranded on shard 0 against a shard-1 order
(2026-08-30), and shard 1 `$22.24` / shard 0 `$0.00` (2026-09-08).

`POST /api/manual-orders` check 9a has said all of this since 2026-09-08, in
full, naming the shard, its balance and `kalshi.com/account/exchange-indexes`.
The **ticket** knew only `authorised_binding: "shard"` and could therefore say
no more than *"that is what this market's Kalshi wallet can pay for"* — true,
and actionable by nobody. The three facts existed one route away and were not
served.

`combo_orders.check_affordable`'s docstring had already written the rule this
violated: *"the venue's own refusal is useless to a person ... the money is on
a different shard, and only the desk is in a position to say so."*

## 4. The decision

**`GET /api/manual/market/{ticker}` serves the shard and its balance**, so the
screen can say what the refusal already says, before he types an amount:

    "shard": {"index": 1, "available_tenths": 0, "available_display": "$0.00"}

Unreadable is `null` on every field, never `0`: a zero balance is the claim
"your money is gone", and an unread one is not that claim.

**The sentence is chosen on `affordable`, never on `contracts`.** A third
branch carries the case this defect lived in — the typed amount is sufficient
and something else zeroed the size — and it says so in those words, then names
the binding constraint: the shard (with its number, its balance and the
allocation link), the book's depth, or an unreadable wallet.

The trim sentence renders only when an order was actually cut down
(`ceiling >= 1`). At `ceiling = 0` the branch above says it in full.

`exchange-shard` enters `glossary.ts`, because Joe has asked to be taught the
terms rather than handed them and this one is not guessable.

**Nothing here changes what is allowed.** No check, no ceiling and no route
behaviour moved; ADR 0112 §5 reserves restoring a brake to Joe and none is
restored. This is the same refusal, said earlier and truthfully.

## 5. Verified by disabling

- Shard block removed from the payload → both route tests red (`KeyError`).
- Unreadable shard resolved to `0` instead of `None` → the never-zero test
  red.
- The branch predicate reverted to the pre-fix form → both ticket-copy guards
  red.

## 6. What this does not establish

That Joe's money was on the wrong shard on 2026-09-14. **The balance was never
read at the time and cannot be recovered** — `venue_balance_snapshots` stores
only the account total, with no per-shard breakdown, and the shard balance is
fetched live at ticket time and discarded. The screen he pasted proves
`authorised_binding: "shard"` and `authorised_contracts: 0`, which means the
shard held less than 25.7c; where the dollar went is inferred from the two
earlier measurements, not observed.

Also not established: that the new sentence would have kept the bet on the
desk. It removes an untrue sentence and supplies the remedy; whether he acts
on it is the next fill's evidence.

## 7. Follow-on, not done here

`venue_balance_snapshots` records only the total — the number that is wrong
for every payability question. Recording the per-shard breakdown on the same
poll would make "which wallet was funded when" answerable after the fact
instead of never. Not built: it is a schema change on a session that was
fixing a live defect, and no question is currently blocked on it.
