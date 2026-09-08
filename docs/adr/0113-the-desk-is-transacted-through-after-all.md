# ADR 0113 — The desk is transacted through after all, and the census was never wrong

**Status:** Accepted. Joe's instruction, 2026-09-08. Ordinal 0113 taken at
merge, 2026-09-08, after `git fetch` (`docs/adr/README.md`).
**Date:** 2026-09-08.
**Supersedes:** ADR 0105, "The desk is read, not transacted through", in its
central decision (§3, first sentence) and in §6's standing instruction to
sessions. **Its §1 census is retained in full and re-read, not withdrawn.**
**Companion to** ADR 0112, which removed the four things standing in the way.
**Touches nothing decided by** ADR 0015, ADR 0018, ADR 0038, ADR 0063 §2,
ADR 0071 §2.2.

## 1. This is the overturning condition ADR 0105 named, in its own words

§5 of that ADR listed two things that would overturn it "and nothing softer".
The second was **"Joe saying so."**

He said so on 2026-09-08, unprompted, correcting a premise rather than
answering a question: he wants to place bets on Kalshi — **single markets and
combinations both — through the cockpit directly**. He added that where
earlier work recorded him choosing to "record one he paid for at a
sportsbook", he had meant **Kalshi's own sportsbook**, and that he does not
want a control for logging bets placed at a third-party book at all.

So this supersede is not a session's reinterpretation of the evidence. It is
the mechanism the superseded ADR specified, firing exactly as written.

**One narrowing, because §5 tied "Joe saying so" to a specific question.** It
pointed at question D — whether ticket #11's price-free log screen is killed
or kept. He has **not** answered that. See §4.

## 2. The census stays true, and becomes more useful

ADR 0105's load-bearing number is **0 of 27**: between 2026-08-25 and
2026-09-04, Joe placed 27 taker hand fills on Kalshi and none went through
`manual_orders`, which had been armed the whole time. That is a census, not a
test, and **nothing here disputes a single row of it.** It is still 0. As of
this writing `manual_orders` has 0 rows of any kind — no real, no dry-run, no
refusal.

What changes is the **inference drawn from it**, and only that:

| | Read as |
|---|---|
| ADR 0105 | He does not want to transact here. The desk is a read surface. |
| This ADR | He does want to. **The door had something wrong with it.** |

That is why this is a supersede rather than a rewrite: the finding survives
intact and the conclusion built on it is replaced. The same shape as the
2026-08-18 combo-row correction, where the reason was wrong and the verdict
held; here the observation was right and the reason was wrong.

**And the second reading has since been supported by something the first
could not explain.** ADR 0112 found four brakes on that door, each of which
Joe removed on being shown it:

- a per-bet ceiling of **~$2.14** — 10% of a ~$21 balance — against a man who
  bets 25c to $3 and had been told the cap was $3.00;
- a daily-loss kill switch at the **same** ~$2.14, counting losses from bets
  he places in the Kalshi app, so two settled losses closed the desk before
  he opened it;
- a 10-minute cool-off against a measured ~2.3 fills per sitting;
- a 43-character bearer token retyped from scratch on every order.

And a fifth, found the same day and not a brake at all: the path had **no
shard awareness**, so with his real allocation (shard 1 $22.24, shard 0
$0.00) every single-market bet would have been refused by the venue with a
bare `insufficient_balance`.

A census of 0 through a door in that condition does not distinguish "he does
not want to" from "he could not". ADR 0105 could not have known that — the
four were not enumerated until 2026-09-08 — and the honest statement is that
its inference was **underdetermined**, not careless.

## 3. The decision

**The desk is a transaction surface as well as a read surface.** Work that
assumes Joe will transact through it is funded again, and ADR 0105 §6's
instruction — that sessions "read this before proposing any input, form,
confirm or tap on the desk that presumes a bet will pass through it", with
"the burden is the census" — is **withdrawn**. There is no such burden. The
burden now runs the other way: a session proposing to remove or throttle a
transaction path needs Joe, per ADR 0112 §5.

ADR 0071 §2.2 is unchanged and is the reason this is coherent rather than a
reversal of purpose: **price transparency at the moment of a bet** was always
the job. What ADR 0105 narrowed was the *venue* of that moment, on the
evidence that the moment happened in the Kalshi app. Joe has said he wants the
moment to happen here. Same job, different room.

## 4. What this does NOT refund, and the distinction matters

**ADR 0105 §3's two specific kills are not automatically restored.** He spoke
about placing bets. He did not speak about either of these, and reading a
general instruction as consent to every item filed under it is how a decision
map gets re-litigated by inference:

- **Ticket #11's price-free log form.** Still killed. §5 tied "Joe saying so"
  to question D specifically, and question D is unanswered. A form for logging
  an *estimate* is not a control for *placing a bet*; if anything his
  correction cuts against it, since the thing he disowned was recording bets
  rather than making them. Reopening this needs question D answered.
- **Wiring `/api/estimates/last-scored` to a screen.** Still killed, and for a
  reason untouched by any of this: the source is **structurally empty**
  (`last_scored_call` selects `is_study_row = 0`, and no such row can exist
  without the form above). A funded transaction surface does not populate it.

## 5. What else is unchanged

- **The presence verdict is still UNRESOLVED — CONCENTRATION.** ADR 0105 §4
  forbids quoting "presence is solved" from it and that prohibition survives
  verbatim here. Joe's intent is not evidence about where he was standing.
- **The engine's gate.** `gate.py` still never reads `manual_orders` or
  `combo_orders` (ADR 0063 §2), pinned by a source-substring test at
  `tests/test_combo_bid_routes.py:564`. Arming the hand path did not arm the
  engine and this does not either.
- **`desk_attention` still measures dwell, not use.** ADR 0105's closing
  caveat stands: a rise in those rows is not evidence for this ADR any more
  than it was against the last one.
- **ADR 0078's `/hedge`** survives, and only its external-book framing is
  wrong. Watching a position he already holds is still wanted. The
  `parlay_positions` deletion clause that would have fired on 2026-09-15 is
  **vacated** — the entry form defaulted to the option he has now disowned,
  on seven surfaces, for the whole observation window, so a 0 there could not
  separate "hedging is unwanted" from "logging someone else's slip is
  unwanted". See
  `docs/measurements/2026-09-08-parlay-positions-check-amendment-registration.md`.

## 6. What would overturn this

Joe saying so — the same standard, applied symmetrically. Not a quiet period,
not a session's discomfort, and specifically **not** a second census of 0.

That last exclusion is deliberate and is the lesson this pair of ADRs exists
to carry. A count of zero through a door with five defects measured exactly
one thing: the door. Any future census offered as evidence about what he wants
must first establish that the path was usable over its whole window — which
means, at minimum, dating the window from the ADR 0112 deploy
(`95fbe16`, live 2026-09-08) and stating what still refuses. Otherwise it will
be the same measurement, read the same wrong way, a second time.

## 7. What this does not establish

- **Nothing about whether he will actually use it.** The brakes are off and
  the path is deployed; that is a hypothesis with the obstacles removed, not a
  result. The first real `manual_orders` row is the finding, and there is not
  one yet.
- **Nothing about combinations being buyable at large.** Shard 1 is funded and
  his own fills went in as takers 51 times out of 52, but the resting-book
  census is unchanged and a browse-and-buy combo board would still render
  mostly empty. See the 2026-09-08 correction in `CLAUDE.md`'s combo row.
- **Nothing about the caps being right or wrong.** ADR 0112 records that they
  are gone on his instruction. Whether that is wise is his call and this
  document takes no view.
