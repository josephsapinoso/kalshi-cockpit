# H4 settlement-fee test — Look 2 result (2026-08-21, written up early)

Registered by `2026-08-20-preregistration-h4-settlement-fee.md` and its
Amendments 1 (`9bc9dad`) and 3 (`9693847`). This is the look write-up §10
requires of every look, produced **early** — at the channel diagnostic's
date rather than on 2026-09-03 — because A17.5 fixed that consequence
before the diagnostic's pull was taken.

## Verdict

> **BLOCKED ON INSTRUMENT**, per A17.5, on the channel diagnostic's
> **BLIND — on a covered-winner denominator of 1**
> (`2026-08-21-h4-channel-diagnostic-result.md`, audited before entering
> the record).

No Look 2 pull was taken, no cluster was classified, no residual was
computed, and no `U` figure exists. **Look 3 is cancelled and the H4 look
series closes.** The A9–A12 analyzer is never built (A17.5), and A12.4's
fallback never runs because the look it governed no longer exists.

## What this verdict means, and does not

- **H4 stays UNTESTED.** `settlement_fee()`'s *"exactly one fee"* is
  neither confirmed nor refuted, and ADR 0027's upper-bound caveat stands
  permanently as worded: the 0.63-point cost headroom remains an upper
  bound, not a point figure. Per §6, the words "zero", "no settlement
  fee" and "H4 confirmed" may not be used of this outcome; they appear
  here only as the prohibition.
- **BLOCKED ON INSTRUMENT is a statement about the study's own reading
  apparatus**, not about Kalshi. The cash-balance channel, at a 300s
  cadence and $0.001 resolution, did not show the record's one covered
  winner's **predicted** credit inside the registered tolerance — while the same record shows
  the channel reconciling 15 of its 16 fills to within 0.5 tenth — every
  fill but the winner's own close — and carrying, in the span holding
  that closing fill, a movement of +4950 tenths — `P_i` less that fill's
  own notional of 50 tenths — 1h31m **before** settlement, which the
  registered statistic cannot credit, and which the pull cannot separate
  into "the payout landed early" versus "the position was closed, so no
  credit was due." The instrument, not the venue, is what the series ran
  out of.
- **The terminal state was named before the diagnostic's pull.** A14
  (Amendment 1) — written after Look 1's residuals had been seen and
  while the balance series through 2026-08-20T04:20:39.418Z had been
  read, but before any span-design residual had been computed by anyone
  and before section E had ever been pulled (A15) — wrote: *"if settled
  proceeds do not credit the cash balance at all … the honest terminal
  state after Look 3 is BLOCKED ON INSTRUMENT."* The diagnostic reached
  that state two looks early, for the price of one read-only pull.
- **Reopening has exactly one door** (A17.11): a further dated amendment
  shipping a new instrument on a different channel — a proceeds-reporting
  settlement endpoint, `portfolio_value` after its unit is pinned, or a
  venue transaction ledger — with guards shipped before any pull and a
  decision rule registered with both consequences fixed. Nothing else
  reopens it.

## §6.1, carried to the series' close

Joe's answer to the transfer question is on record as **cannot recall**
(`30f1c2e`, the UNANSWERED branch). Per A13 it changed no verdict, was
not re-asked, and is not re-asked here.

## What this does not establish

Everything Look 1's result file and the diagnostic's own "what this does
not establish" sections state, unchanged. This file adds no measurement;
it records the registered consequence of one.
