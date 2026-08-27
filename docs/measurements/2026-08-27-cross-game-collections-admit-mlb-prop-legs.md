# Cross-game combo collections admit MLB prop legs

**Taken:** 2026-08-27, `GET /multivariate_event_collections` (paginated) via
`fetch_collections`. Read-only: no `lookup_combo`, no market minted, no order
path, no order book read.

**Run from the integration checkout by another lane**, because the parlay lane
has no credentials and reading them was denied there. The command was handed
over verbatim and executed unedited; the JSON came back whole rather than
summarised.

## The question

**Eligibility, not liquidity.** Will Kalshi let an MLB player-prop event be a
leg in a *cross-game* combination at all? This is a different question from
whether such a combination can be bought, and the answer here says nothing
about the second.

## The result

Prop legs are **present**. Of 1,389 collections, 17 are cross-game scope, and
three carry prop legs:

| collection | scope | legs | prop legs | detail_missing |
|---|---|---|---|---|
| `KXMVESPORTSMULTIGAMEEXTENDED-R` | cross_sport | 2033 | 35 | 0 |
| `KXMVECROSSCATEGORY-SHARD1-R` | cross_category | 2033 | 35 | 0 |
| `KXMVECROSSCATEGORY-R` | cross_category | 2033 | 35 | 0 |

All five MLB prop series appear — `KXMLBKS`, `KXMLBTB`, `KXMLBHIT`, `KXMLBHR`,
`KXMLBRBI`.

`detail_missing` is **0 on all 17 rows**, which is what licenses reading the
zeros as real. An absent `associated_events` field parses to zero legs and has
already produced four such phantoms in this repo's history; none of these is
one.

## Treat the three rows as ONE observation

Identical leg totals (2033), identical prop-leg counts (35) and an identical
series set across all three. That is the signature of one underlying pool
exposed under three tickers, not three independent confirmations. Counting it
as three would be the pooled-number failure CLAUDE.md's measurement rules name:
**print the parts and the largest contributor's share before believing an
aggregate.** The largest contributor's share here is effectively 100%.

## It is MLB-and-cross-category, not a general property

Every NFL, NBA and college multi-game collection carries **zero** prop legs —
fourteen rows, `KXMVENFLMULTIGAMEEXTENDED-W5` through `-W13`,
`KXMVENFLMULTIGAME-2526W3/W4`, `KXMVENBAMULTIGAMEEXTENDED-D20251113`,
`KXMVECBCHAMPIONSHIP-R`.

Whether that is seasonal or structural is **unresolved and is the same calendar
caveat `backend/kalshi/combos.py` already carries** — the original 2026-08-06
capture ran with the NBA finished and the NFL in preseason. One slate, one
instant. Do not generalise it to "cross-game collections admit props."

## The lookup path can reach these, verified by reading it

`_FALLBACK_COLLECTION_PREFIXES` (`backend/parlays.py:888-891`) is
`("KXMVESPORTSMULTIGAMEEXTENDED", "KXMVECROSSCATEGORY")`, which prefix-matches
all three. `_choose_collection` (`parlays.py:947-968`) first takes collections
whose leg set is a genuine superset of the card's event tickers — a real subset
test against real leg tickers, not a guess — and only then falls back by prefix,
taking the first by ticker sort, which is the `-R` variant in both cases.

**On this slate, every open prop event is eligible — 35 of 35.** Measured
after the fact, per series, by set comparison against `KXMVECROSSCATEGORY-R`
rather than by matching counts:

```
KXMLBKS   eligible 7  open 7   open_but_not_eligible []  eligible_but_not_open []
KXMLBTB   eligible 7  open 7   []  []
KXMLBHIT  eligible 7  open 7   []  []
KXMLBHR   eligible 7  open 7   []  []
KXMLBRBI  eligible 7  open 7   []  []
```

Same event tickers, not merely the same totals — 7 games x 5 statistics.

**An earlier draft of this document said eligibility was "partial", and that
was wrong.** It was inferred from `n_prop_legs = 35` with no denominator, which
is the same shape as the two prop-cost figures that went wrong in `.env.example`:
a number divided by an assumption. The denominator was measured instead of
guessed, and it inverted the claim.

**Write neither "partial" nor "total".** One slate cannot carry the second
either. The honest scope is: *on the 2026-08-27 slate, all 35 open prop events
were eligible; whether that holds structurally is unmeasured.* n = 7 games, one
instant. It says nothing about a fifteen-game day, a doubleheader, a late
scratch, or a fixture added after the collection was built.

**Only one of the three collections was checked** — `KXMVECROSSCATEGORY-R`. The
other two share its 2033-leg total and are near-certainly the same pool; that
was not verified and is not reported here as verified.

**A mechanism that would make this structural, explicitly NOT established:**
the `-R` suffix on all three suggests a *rolling* collection tracking the slate,
where the `KXMVENFLMULTIGAMEEXTENDED-W5..-W13` counterparts are fixed weekly
windows — and those carry zero props. That is a hypothesis with a clean test
(re-read on a slate of a different size), not evidence.

### The pre-tap check is still worth building, for a different reason

`_choose_collection` (`parlays.py:947-968`) takes collections whose leg set is a
genuine superset of the card's event tickers, then falls back by prefix. When a
card's prop leg is not in the chosen collection, the fallback fires anyway and
the tap posts a leg that collection does not contain. It fails at Kalshi rather
than silently, and `parlay_lookups` records it either way — but it fails *after*
a tap rather than being refused before one.

The motivation is **not** "eligibility is partial so this fires often". It is
"eligibility is total on the one slate measured, and the code must be correct on
the day it is not". That is the weaker motivation and the better-founded one.

## What this does NOT establish

- **Nothing about liquidity, and the two sentences must stay apart.**
  Constructible is not buyable. `yes_dollars` is empty on 40 of 40 combination
  books this repo has ever read, across three runs on two dates; combos are
  enter-only and the list ask is the complement of a resting NO bid. Nothing
  here touched a book.
- **Nothing about whether such a card is worth buying.** No EV, no edge, no fee
  model. ADR 0046's tripwire is untouched.
- **Nothing about same-game props.** Out of scope by construction: the ladder
  takes one leg per fixture and `correlation.py` refuses same-game pairs.
- **One slate, one instant.** Collection membership is not pinned and the `-R`
  suffix is known to rotate (`invalidate_collections_cache`).
