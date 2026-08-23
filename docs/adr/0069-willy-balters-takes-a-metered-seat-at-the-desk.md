# 0069 — Willy Balters takes a metered seat at the desk

**Date:** 2026-08-23
**Status:** Accepted.
**Builds on** ADR 0060 (the scout desk) and ADR 0068 (five areas, fully
present); **does not touch** the 2026-08-20 fleet ruling that Willy stays a
free non-LLM voice *on the Board's rows* — that refusal was about ambient
per-row spend, not an on-demand desk seat.

## 1. What happened

Joe named the voice himself ("willy balters") in his five-area desk
direction. The character already exists: the free `CrewBubble` line on slate
rows, reading only the book distribution, with the fiction's name
mutation-pinned (`tests/test_crew_bubble.py` — "Billy Walters" turns it
red). What was missing is the pro's *read of a game*: what in the desk's
filings would matter to a professional, the discipline that applies, and
what would change his mind.

## 2. The decision

**One fiction, two tiers.** The free row bubble stays exactly as it is
(one voice, one data source: the book distribution). The desk seat is new:
`backend/agents/pro_bettor.py`, a fourth metered call per convening,
reserved only after the master settles — same money contract as every seat
(reserve before request; a refusal spends nothing).

The seat's contract, each clause pinned:

- **Words only, structurally.** `SharpTake` (headline, read, discipline[],
  would_change_my_mind[]) has no numeric field anywhere, walked by
  `tests/test_pro_bettor.py` exactly as `DeskBriefing` is. The two hard
  rules (no probabilities/prices/"good bet"; no facts beyond the filings)
  are copied into the system prompt verbatim.
- **No tools.** The search budget belongs to the staff;
  `STAFF_PAIR_SEARCHES_WORST_CASE` remains the whole convening's worst case
  because this call cannot search. Source-pinned over the call block,
  mutation-verified red.
- **`status` semantics unchanged.** `complete` still means staff pair +
  master; the seat is additive. Its own outcome is `sharp` /
  `sharp_absent_reason` — an unaffordable or failed seat is an honest
  absence, never a downgraded briefing
  (`test_an_unaffordable_pro_seat_downgrades_nothing`).
- **The fiction stays a fiction.** Willy Balters, never the living
  professional — pinned in the persona prompt and the UI panel, matching
  the CrewBubble pin.

**Persistence (schema v19):** `scout_briefings.sharp_json TEXT`, nullable,
no backfill — NULL means the seat filed nothing or the briefing predates
it, never `{}`. Served as `sharp` on `GET /api/scout/{ticker}` (null, never
absent). The absence reason is logged at convening time and deliberately
not stored: on read, "predates the seat" and "filed nothing" render the
same honest words, and a stored reason would age into a claim about a
budget day long over.

## 3. Budget arithmetic

Per convening: **4 calls, worst-case 12 searches** (staff 2×6; master 0;
Willy 0), est. ~25–40k tokens. Against the live day caps
(`fly.live.toml`: 24 calls / 60 searches / 500k tokens): calls allow 6
convenings, **searches bind at 5**, tokens allow ~14 — so the day supports
**5 full convenings**, refused by name after that through the existing 429
path. At assumed list prices (`base.py`'s convention — arithmetic, not an
invoice): ~$0.50–0.70 per convening, ~$3.50 for a maxed day. The daily
caps, not the deposit, are the control; with the scheduled Skeptic retired
(ADR 0062) the desk is effectively the only spender.

## 4. What this does not reopen

Nothing about edge (ADR 0038 stands): the seat prices nothing, sizes
nothing, and its schema cannot carry a number. The Board's Willy refusal
stands. The gate, `ORDERS_ARE_DRY_RUNS`, and the suppression rules are
untouched.
