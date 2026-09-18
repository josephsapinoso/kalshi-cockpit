# ADR 0170 — Joe types the RFQ size, both price surfaces are shown, and the button that spends prints the dollars

Date: 2026-09-18
Status: Accepted
Issues: #62 (answered A), #66, #67, #68, #70. Extends ADR 0164/0165 (the RFQ
path); applies #39's settled precedent to the second control that spends.

## Context

The RFQ surface is the newest armed thing on the desk and the only one that
spends on a single tap. It shipped in a day and had none of the review the
order-book path got in #39–#47. A pass over it found four defects that share
one shape: **a number that governs money, that the screen does not show.**

## Decision

### 1. The size is typed — #62, Joe's answer (A)

It was `targetCostDollars="5.0000"`, hardcoded at the mount, and trimmed
server-side to `SHARD_HEADROOM × available`.

**That is two independent limits on one quantity**, and they swap over at
**$5.5556** of shard balance: above it the hardcoded $5 binds, below it the
90% does. The symptom is identical either way, because nothing printed the
dollars — so funding the shard past $5.56 changed what the desk asked for,
silently. (The ticket's own evidence had this backwards and is corrected in a
comment on it rather than edited.)

Neither number was chosen for a bet. The $5 is the size the one measured RFQ
happened to be fired at, and the 0.90 is, in its own comment, *"a margin, not
a measurement."*

Now: Joe types dollars, the last value is remembered per device, and
**`SHARD_HEADROOM` becomes a wall instead of a second size** — an unaffordable
figure is refused with a `400` *before the makers are asked*, naming the
amount he can ask for. The failure this replaces burned 28 makers' answers
before telling him (2026-09-17).

**This is not a brake.** ADR 0112's five ceilings stay gone. Joe choosing his
own stake is the opposite of a ceiling; the collateral pool choosing it for
him was a default nobody picked.

### 2. Both price surfaces, and asking is offered on a priced book — #66

`book_yes_ask_tenths` was already in the payload and rendered nowhere. It is
now `book_ask_display`, through the one price renderer, beside the maker's
quote.

And `<AskTheMarket>` now mounts on the **priced** branch as well as the empty
one. A priced book was a dead end in the other direction: the desk sold him
the book's price without showing the one it could have asked for.

The justification is measured, and it is symmetry rather than preference:
on 2026-09-17 **the book beat the RFQ on two of three** held combinations
(5.10c vs 4.70c; 0.32c vs 0.14c) and **the RFQ was the only price on the
third**. Neither dominates, so a screen reading one surface sometimes reports
no price when there is one and sometimes shows the worse of two.

**Nothing ranks them.** Showing two prices is transparency; ordering them is a
claim, and `beta = -0.141` is why this desk does not make it (ADR 0071 §2.5).

### 3. A quote shows its age — #67

A maker stands behind a combination quote for about **three seconds** (a High
Volatility Market), against thirty elsewhere. This is the fastest-ageing
surface on the desk and it was the only one with no clock.

`asked_ms` is on the payload; the component ticks its own age and, past three
seconds, says the price has probably expired. **It relabels and never blocks**
— taking a dead quote fails at the venue with the venue's own reason, which is
a refusal and not a loss, and disabling a control on age would be a new
ceiling (ADR 0112 again).

It deliberately does **not** share `PriceOnKalshi`'s `QuoteAge`, which is
about a 900-second book read. Different claim, different words.

### 4. The button says what leaves the account — #68

It read `Take it at 59.3c` — a per-contract price on the control that spends.
It now reads `Take it — $5.00 all in`, with the fee included, because Kalshi
charges the combination taker fee **on top of** the contracts on a
fee-inclusive target.

On the worked example the difference is not rounding: **8.19 contracts at
59.3c is $4.86 of contracts and $5.00 all in.** Fourteen cents on a
five-dollar bet.

One fee model, not two: `combo_entry_fee_tenths` at `COMBO_TAKER_COEFFICIENT`
(0.071), the same number `/hedge` sinks on an open position (ADR 0145).

**Nulls rather than a friendlier number.** A quote whose size cannot be read
has an unknown cost, so the button falls back to `Take it` and the words say
the total is not known. Printing the contracts alone would be a smaller,
friendlier, wrong number.

### 5. The jargon teaches itself — #70

`rfq`, `maker`, `maker_quote` and `shard` are glossary entries, wrapped in
`<Term>` where the screen first uses them. Joe's standing instruction from
2026-08-18.

## What this does not establish

- **That Kalshi will charge exactly the all-in figure.** The coefficient
  exceeds every implied k this repo has measured *by construction*, so the
  number errs **high** — the safe direction for a cost shown before a tap,
  and the opposite of the rule for a hedge lock, where erring high would
  flatter.
- **Anything about which surface is better.** Two prices are shown. The
  comparison is Joe's.
- **Anything about how often a book carries an ask.** `book_ask_display` is
  null on most combinations and that is the resting state, not a fault.
- **Anything at runtime.** The screen tests read source; there is no React
  test runner in this repo.

## Two stale claims found on the way past

Both on the money path, both the repo's named *justifications decay toward
reassurance* pattern, and neither was the thing being worked on:

1. `PriceOnKalshi`'s module docstring said **"whether a SELL-side RFQ draws
   bids has never been tested."** It was tested on 2026-09-17 and the answer
   was bids — 16 of 44 quotes across 3 of 3 held combinations, every one at
   the full size asked.
2. The same docstring said `book_empty` "now renders `<AskTheMarket>`",
   which since #66 under-describes where it renders.

## Mutations

Twelve run, **twelve red**. No survivors.

| # | mutation | result |
|---|---|---|
| M1 | trim the target instead of refusing it | RED — 3 failed |
| M2 | refuse after the RFQ is created, not before | RED — 3 failed |
| M3 | let the whole shard be asked for, leaving nothing for the fee | RED |
| M4 | stop rendering the public book's ask | RED |
| M5 | drop the quote age from the payload | RED |
| M6 | drop the fee from the all-in figure | RED |
| M7 | guess a missing quote size so the button always shows a number | RED |
| M8 | hardcode the size back into the mount | RED |
| M9 | stop offering the ask on a priced book | RED |
| M10 | render the age once instead of ticking it | RED |
| M11 | put the bare price on the button instead of the all-in | RED |
| M12 | drop the glossary wrap on the shard | RED |
