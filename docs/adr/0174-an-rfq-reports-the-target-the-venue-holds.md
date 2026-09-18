# ADR 0174 — An RFQ reports the target the venue holds

**Status:** Accepted
**Date:** 2026-09-18
**Ticket:** #72 (build, no decision needed)
**Amends nothing. No schema change.**

---

## 1. The defect

`create_rfq` **reuses** an open RFQ whenever its target is at least the one
wanted, and `ask_market_to_price` **holds RFQs open by default** — that is what
makes the accept reachable on a second tap. Put together:

    Joe asks at $1.00       -> RFQ created at $1.00, held open
    Joe asks at $5.00       -> create 409s `already_exists`
                            -> the $1.00 RFQ is reused
                            -> payload reports target_cost_dollars "5.0000"

He is shown **quotes sized for $1.00** beside a field saying **$5.00**, and the
venue was never asked at the larger number.

`create_rfq` returned a bare `str`, so the caller had nothing to report but the
figure it had passed in. **The lie was structural: the function could not tell
the truth because its return type had no room for it.**

**What did NOT lie, and it matters:** the Take-it button's all-in figure is
computed from the quote's own size, so it stayed honest throughout. What lied
is the target line and any reading of "you are about to spend about what you
typed".

`target_cost_requested` was added to surface exactly this class of divergence,
back when an unaffordable target was silently trimmed. **The trim became a
refusal in #62, so the two fields have been equal by construction ever since —
a divergence field reporting no divergence while the real one went unreported.**

## 2. The decision

**`create_rfq` returns an `RfqHandle`: the id, the target the venue actually
holds, and whether the RFQ was reused.**

The ticket offered a second option — refuse to reuse an RFQ whose target is
below the one asked for — and called it simpler. **It was not taken.** Reuse
exists because replacing means deleting, and deleting **destroys quotes that
may be on screen with a confirm pending** (measured 2026-09-17: a re-read after
DELETE came back empty). Option two fixes a false field by changing the world
the field describes, and it costs a real thing to do it. Reporting the truth
costs nothing.

### `None`, never the requested figure standing in

`RfqHandle.target_cost_dollars` is the venue's own string, verbatim, or `None`
when the venue named none — which is every `contracts=` ask, since those carry
no dollar target at all. **A field that reports the request when it cannot read
the truth is the defect, not the fix**, so the fallback is `None` and the
caller's `handle.target_cost_dollars or target` is reached only for the
`contracts=` case, where no dollar target exists to be wrong about.

### The sentence is said only on the divergence

`_words` leads with it — **prepended, not appended**, because it changes what
every price below it means:

> *"These quotes answer a request for $1.0000, not the $5.0000 you asked for —
> an earlier request on this combination was still open, so the venue was never
> asked at the larger number. The sizes below are the ones it was asked at."*

**Said only when the two differ.** ADR 0170 Amendment 1 is the precedent: a
quote-age warning that fired on every first paint was decoration that trains
the reader to skip warnings, and it was removed the same day it shipped. A
mutation making this one unconditional fails two tests.

**And it is said even when makers answered.** The branch that has prices is
exactly the branch where the reader is about to act on them.

## 3. Verification

**84 passed** across `test_combo_rfq.py` and `test_combo_rfq_route.py`, plus 91
on the rest of the RFQ surface. **Seven mutations, all red:**

| | mutation | result |
|---|---|---|
| M1 | the reuse path reports the target we asked for — **the defect** | red, 3 failed |
| M2 | an unreadable venue target falls back to the request | red |
| M3 | the payload reports the requested target again | red |
| M4 | the divergence sentence is never said | red, 3 failed |
| M5 | the sentence is said unconditionally (could never be false) | red, 2 failed |
| M6 | the sentence is dropped on the branch that HAS prices | red, 2 failed |
| M7 | `reused` is never set | red |

M5 is the one worth naming: it is the ADR 0170 failure mode written as a
mutation, so a later change that makes the warning unconditional fails rather
than shipping.

## 4. What this does not establish

- **Nothing about how often this path is walked.** It exists because RFQs are
  held open; how often Joe re-asks at a larger number after a smaller one is
  **unmeasured**, and this ADR adds no counter for it.
- **Nothing about the quotes being wrong.** They are real quotes at the price
  and size the venue was asked for. The defect was the label, not the prices,
  and the all-in figure on the button was correct throughout.
- **Nothing about the reverse case.** Asking at $1.00 when a $5.00 RFQ is open
  takes the *replace* branch (`_is_reusable` is false), which deletes and
  recreates, so the two targets agree there by construction. That branch is
  unchanged.
- **Nothing about `combo_rfqs.target_cost_dollars` in the database.**
  `record_rfq` is `ON CONFLICT DO NOTHING`, so a reused RFQ keeps its original
  row and its original target — which is already correct — and a fresh one
  writes the target it was created at. No row changes.
