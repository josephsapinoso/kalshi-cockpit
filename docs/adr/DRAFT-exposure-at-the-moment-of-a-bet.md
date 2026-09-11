# DRAFT — The ticket says how deep he already is

**No ordinal taken.** Lane A wrote this; the integrating session assigns the
number if it keeps it. Date: 2026-09-10.

## Context

ADR 0112 removed all five brakes from the hand-bet path on Joe's word. Those
caps were the only consumer of his exposure figure in the whole product: the
per-bet spend cap and the 10%-of-balance cap both read what was already at
risk, and when they went, nothing read it any more. Nothing on any screen
carried it either — `OpenPositions` renders it on `/slate` and `/bets`, and a
bet is not placed on either. `/parlays`, the screen all four real combination
fills were placed on (ADR 0113, ADR 0129), fetched no position data at all.

ADR 0071 §2.2 makes price transparency the desk's job at the moment of a bet.
What Kalshi charges is one half of "what is this costing me". What he already
has on is the other half, and it was missing at the one moment it decides
anything.

## Decision

**1. One line inside `ManualTicket.tsx`, above the confirm.** Not on each
screen. The ticket is mounted on seven surfaces — `LiveBoard`, `MarketSearch`,
`ParlayCards`, `PriceOnKalshi`, `SlateRow`, `market/[ticker]/page.tsx`,
`slate/page.tsx` — and one edit inside the component reaches all seven.
`tests/test_manual_ticket_exposure.py` pins the seven, so a surface that stops
mounting the ticket cannot silently stop showing exposure.

**2. A new route, `GET /api/exposure`, serving `open_positions` and nothing
else.** `/api/bets` already serves the same block, and also `bets_record(limit
= 200)`, the pass summary and the lockout clock. This read happens every time
a ticket opens, on seven surfaces, beside a live Kalshi book read. The payload
is two keys and the test pins them by name, which is what stops the next
screen's needs from being bolted onto a buy button's read.

**3. It informs and it NEVER blocks.** A staleness or exposure gate on the
confirm would be a sixth ceiling on a hand bet, which is a reversal of
ADR 0112 and not a feature. The posture is `PriceOnKalshi.tsx`'s `QuoteAge`
block: relabel, never gate. Two tests enforce it — the exposure state does not
appear in `canConfirm`, and no `disabled=` expression on the ticket reads it —
and both go red under the obvious mutation.

**4. Unreadable renders as the server's own words, never as `$0.00`.**
`backend/bets.py` words five staked refusals with care, and a `$0.00` on this
line would report "nothing at risk" off a dead poller: the false negative in
the flattering direction, on the one figure that exists to say what is at
risk. Every refusal ends "That is not the same as nothing at risk."

**5. The figure wears the clock of the read that produced it.** The count's
clock, never the balance's — `openPositionsStamps.ts` exists because one
borrowed the other's and the borrowed one was the container's boot time.

## What this does not do

It does not gate, size, warn, or rank. It states one fact the reader can act
on and stops. It is not a brake returning under a new name, and a future
session reading "exposure" beside a buy button should not restore one.

It also does not establish that the mirror behind the figure is complete: a
position opened while the poller was down is absent, and no freshness stamp
can say so. That is `open_positions`' own caveat and this changes nothing
about it.

## Consequence noted in passing

`glossary.ts`'s `exposure` entry said "the exposure cap bounds that total, so
one bad night cannot take the whole bankroll". On the engine path that is
still true; on the hand-bet path it has been false since ADR 0112, and this
line renders that definition at the buy button. The entry now says nothing
caps it on a bet placed by hand.
