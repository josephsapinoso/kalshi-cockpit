# 0067 — The slate ranks likely winners by one unscored column

**Date:** 2026-08-23
**Status:** Accepted.
**Amends** the slate page's "no ordering by anything but kickoff" rule
(`frontend/src/app/slate/page.tsx`, 2026-08-21) for one new block only;
**changes nothing** about the rows, the Board, the gate, or any suppression
rule.

## 1. What happened

Joe, 2026-08-23, verbatim: *"I just want to see what are good-chance picks
and everything is rejected."* The Board answers one question — is Kalshi
mispriced against the devigged sharp consensus? — and the measured answer is
almost always no (live census that morning: 90 of 100 candidates "no edge",
Kalshi within ~0.1c of Pinnacle/Betfair/Matchbook on the checked rows). A
screen organised around that question is empty by *finding*, not by defect
(ADR 0038, ADR 0062), and the person funding the tool read the emptiness as
the tool refusing to tell him anything at all.

"Good chance to win" is a different question from "good bet", and the record
already answers it every night: `fair_probability` — the worst-of-four-methods
devigged consensus, side-denominated — is on every slate row and had never
been ranked or surfaced as what it is: the best available estimate of who
wins.

## 2. The decision

**`/api/slate` serves a `picks` block — "who's likely to win tonight" — and
the slate screen renders it above the rows.** One entry per game: the side
the consensus makes the favorite, ranked by `fair_probability` descending.
Server-computed, server-worded, rendered by
`frontend/src/components/GoodChancePicks.tsx`.

The rules, each pinned by `tests/test_slate_picks.py` /
`tests/test_good_chance_picks.py`:

1. **A sort on ONE stored, unscored column is not a weighting.** The
   2026-08-21 rule this amends said "a ranking *is* a weighting"; the line
   is redrawn, not erased: a composite of two or more factors remains
   forbidden (ADR 0021 §9, `backend/slate.py`'s prohibitions), and the rows
   below the block still order by kickoff and nothing else.
2. **Fair% and break-even never share a block.** `edge_tenths` is exactly
   `1000 × (fair − breakeven)`, so rendering both hands the reader the
   measured-negative edge by subtraction. The picks block carries fair%; the
   rows carry break-even; a key-walk test refuses any edge-shaped field in
   the block (mutation-verified red).
3. **The chance≠edge sentence travels with the payload** and renders
   verbatim: *"Chance to win, by the books' consensus — not an edge. The
   price already charges for the chance: a 70% favorite costs about 70
   cents, so a likely winner is not a profitable bet."* Pinned verbatim
   (mutation-verified red).
4. **YES-side rows only.** On a NO row `team` names the yes side — the
   opponent of the pick — and a route that renames sides is a derivation
   that goes wrong silently. A game with no fresh YES row on its favorite's
   side is counted out (`favorite_unpriced`), never ranked from the
   underdog's number.
5. **A stale consensus does not rank** (live odds age past
   `max_odds_age_s`, mutation-verified red), and the exclusion is counted
   (`stale_consensus`) — "no pick" and "no measurement" are different facts.
   A stale Kalshi quote withholds only the ask (null, never a souvenir);
   the chance can outlive the price.
6. **The block is not a chase surface.** No ticket, no order route, no
   `bg-accent` (red = money, ADR 0061 §3), no urgency ink, no hit-rate or
   streak tally (the aggregate the CLV ruling bans below n ≥ 30). Entries
   link to the game's own screen — where the desk, the ticket, and the Pass
   control (ADR 0066) already live.

## 3. What this does not reopen

Nothing about edge. The ranking column is unscored and stays unscored unless
a pre-registered measurement scores it; the gate, `ORDERS_ARE_DRY_RUNS`, the
suppression rules and the Board's edge rendering are untouched. ADR 0038's
closure stands: this block surfaces the books' opinion, it does not claim
the tool has one.
