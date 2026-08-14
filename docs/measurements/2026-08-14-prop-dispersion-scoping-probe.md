# Scoping probe — MLB player props vs a multi-book consensus

**2026-08-14. EXPLORATORY. NOT PRE-REGISTERED. Not a finding, and nothing here
may be cited as one.**

No hypothesis was fixed before the data was seen, no decision rule was
registered, and the cuts below (`books >= 4`, `edge > method spread`) were
chosen **while looking at the output**. That is exactly the freedom
`pre-registrar` exists to remove. This document scopes whether a registered
measurement is worth running. It does not substitute for one.

Producer: `scripts/probe_prop_dispersion.py`. Two runs, 2026-08-14, ~2 hours
apart, 138 Odds API credits each.

---

## Why it was run

ADR 0021 §7.2, verbatim:

> *"We have been testing Kalshi against the only references plausibly as sharp
> as Kalshi. ... A comparison between two sharp prices returns nothing by
> construction, and 'returns nothing' is precisely what it returned."*

The deployed runner prices **2 of Kalshi's 3,405 sports series** — `KXMLBGAME`
and `KXWNBAGAME` — against `betfair_ex_eu` + `matchbook` (± `pinnacle`). This
probe changes both halves at once: **player props** as the target, and the
**soft books that actually quote them** as the reference.

## What works, and it is the part worth keeping

The plumbing is real and cheap:

- **Kalshi prop ladders exist for essentially every game.** `KXMLBKS`,
  `KXMLBTB`, `KXMLBHIT`, `KXMLBHR`, `KXMLBRBI` — 12–13 open events each,
  227–263 markets on a 14-game slate, `linear_cent` grid, displayed size in the
  thousands on the liquid rungs.
- **The mapping is exact, not fuzzy.** Kalshi's `N+` is the books' `Over N−0.5`.
  `yes_sub_title` parses cleanly (`"Clay Holmes: 4+"`), 0 unparsed of 227.
- **Keying on (player, threshold) removes the team-mapping problem entirely.**
  0 name collisions across the slate.
- **8 books quote props** — DraftKings, FanDuel, BetMGM, BetRivers, Bovada,
  BetOnline, Fanatics, MyBookie. **No Pinnacle, no Betfair.** The reference set
  is genuinely soft, which is the point of the exercise.
- **Cost:** 138 credits per full sweep including alternates, against 19,670
  remaining. ~140 sweeps affordable.

## What it found

| population | n | clears at deployed `k = 0.070` | clears at measured `k = 0.035` |
|---|---:|---:|---:|
| all comparisons | 96 | 1 | 3 |
| **≥ 4 books** | **42** | **0** | **1** |

"Clears" means net edge > 0 **and** net edge > its own devig method spread —
CLAUDE.md's rule that a spread of 1–2 points exceeds the advantage being hunted.

**Every large apparent edge came from a one-book "consensus".** Run 1's top
rows: `+19.1t` on 1 book, `+10.0t` on 1 book, `+8.5t` on 2 books at depth 39.
Meanwhile every row with 5–7 books was **negative** at the deployed fee. That is
rule 1 — *a large apparent edge is a bug until proven otherwise* — reproducing
in the wild, and it is the most reassuring thing in this document.

**The single survivor, identical on both runs:**

```
Yoshinobu Yamamoto 7+ strikeouts   ask 52.0c   consensus fair 53.6%
6 books   method spread 3.7t   depth 3,251   net +7.7t at k=0.035, -2.3t at k=0.070
```

`n = 1`, on one slate, unregistered. **It is a reason to run a registered
measurement, not a bet.**

## The finding that actually matters, and it is not about props

**At the deployed fee coefficient, props return zero — the same answer game
lines gave.** Changing the target market did not change the conclusion.

**What changes it is the fee.** Every row that clears, clears only at
`k = 0.035` — the coefficient ADR 0028 measured on 9 baseball fills and
deliberately did **not** adopt, because the record spans four days.

So the binding constraint on this whole strategy is **the fee coefficient, not
the choice of market.** That is a correction to the working assumption: the
second MLB observation window, ≥3–4 weeks after 2026-08-14, is not a
nice-to-have tidying up an ADR. It is the gate. Props are baseball, so
whatever that window says about `k` applies to everything above.

## The cheapest available improvement

**174 of 222 matched keys were dropped for having no two-sided book.** The
`_alternate` feeds cover the full ladder (1.5 → 9.5) but most books quote only
the Over there, and `consensus_devig` needs both sides.

Recovering those is **~4.6× the comparison count for zero extra credits** — the
data is already in the payload. The principled route is to estimate each book's
overround from its own two-sided primary line for the same player and market,
then apply it to that book's one-sided alternates. **That is an assumption and
must be registered as one**, not slipped in.

## What this does not establish

1. **Not an edge.** A gap against a soft-book consensus is a gap. Either Kalshi
   is mispriced or Kalshi is right and the books are wrong; **this probe cannot
   tell those apart.** Only CLV against Kalshi's own close can — rule 3.
2. **One slate, two pulls, two hours apart.** Not independent days. `n = 96`
   comparisons over ~14 games is not power.
3. **Nothing about fills.** Displayed size is displayed size.
4. **Nothing about the NO side's reachability.** NO asks are derived from the
   YES bid; no depth-at-the-bid durability was measured.
5. **The cuts were chosen after seeing the data.** Stated again here because it
   is the single most important limitation and the easiest to forget.

## Suggested next step

A **pre-registered** run: fix the population (which series, which slates, how
many days), the book-count floor, the method-spread rule, the horizon, and the
stopping rule **before** the next pull — then score the survivors on CLV against
Kalshi's close rather than on the gap. `pre-registrar` owns that document.
