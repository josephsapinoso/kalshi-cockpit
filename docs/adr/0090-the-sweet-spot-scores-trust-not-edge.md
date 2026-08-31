# ADR 0090 — The sweet spot scores trust, not edge

Date: 2026-08-31
Status: accepted
Relates to: ADR 0021, ADR 0034, ADR 0038 (the closed hunt), ADR 0062,
ADR 0071 §2.5, ADR 0081, ADR 0089

## Context

Joe asked for a **"sweet spot"** — *"the overall score that determines a yes or
no on what is a good bet, either on a parlay or prop or pick."*

That is, read literally, the screen ADR 0038 closed. Put to him with the
evidence, he chose **trust rather than edge**, on all three surfaces.

## Why edge is excluded, and it is arithmetic rather than taste

The consensus-vs-Kalshi gap is the project's registered decision-bearing
statistic and it has been measured: **`beta = -0.141`**, `se_cluster 0.0478`,
every interval computed at either look lying entirely below the registered
0.40 NO-SIGNAL threshold, both arms negative (ADR 0021, ADR 0034).

A negative beta means the gap ranks the **least** trustworthy rows highest. A
composite containing it is therefore *worse* than the same composite without
it. This is not caution about a promising signal; it is the refusal to add a
term measured to point the wrong way.

## Decision

**The sweet spot is a count of the desk's own existing refusal criteria that a
row passes, with every failure named.** It says *this number is worth acting
on*. It never says *this bet wins*.

`backend/core/trust.py` — pure, deterministic, writes nothing.

### No invented thresholds

Every limit arrives from the config that already enforces it —
`StalenessConfig.max_odds_age_s` and `max_kalshi_quote_age_s`,
`SuppressionConfig.min_book_count` / `max_market_width` /
`min_depth_contracts`, and `ladder.AGREEMENT_SPREAD_POINTS`. **No argument has
a default**, deliberately: a default would be a second definition of a limit
that lives elsewhere, and `config.py` already refuses to boot when two limits
on one quantity disagree (`StalenessLimitsDisagree`). This module joins that
discipline instead of becoming the drift it exists to prevent.

`TrustThresholds.from_configs` is the only constructor, so there is no path by
which a caller supplies a number of its own.

### No invented weights

`dispersion.ts` sets the standard: *"the strip computes no composite — that
would be a model, and it would need its own ADR."* The score is a **count**.
Equal weighting is a choice, and it is the only one that adds no unmeasured
claim.

"Not every check matters equally" is answered by **naming every failure**, not
by a weight vector — which is `SuppressionResult.reason`'s own reasoning:
*"All failures, not just the first: a row suppressed for staleness that was
also mis-matched needs both facts, and the second matters more."* Choosing
*which* failure to call binding would be the importance weight this refuses to
invent.

### Unknown is not a pass

The third state, and the one that always breaks in the flattering direction. A
prop the skeptic never ran (`not_on_this_path`), a game with no scout
briefing, an unreadable depth — none is evidence of quality. Folding them into
`pass` makes the **least-examined row score highest**, which is the failure
`suppression.py` already records for `market_width = 0.0`: *"the
least-evidenced consensus in the system cleared this check most easily."*

So `passed`, `known` and `total` all travel, and the screen renders
`passed/known` with the unknown count beside it. Rendering `passed/total`
instead would silently count an unknown as a miss — the opposite error, and
equally wrong, because it punishes a row for a check nobody ran.

One deliberate asymmetry: a **`None` market width fails rather than reads
unknown**, because it means fewer than two books contributed — there was no
second book to disagree with. That is a measured absence of evidence, not an
absence of measurement, and `suppression.py` already draws the same line.

### The screen

**The number is never rendered bare.** A lone "6/8" beside a bet reads to a
beginner as "this is a 6-out-of-8 bet" — exactly the edge claim this design
avoids. So the label names its subject (*evidence*), every failure is spelled
out, the unknown count is shown, and a clean row still says the score is *"not
about whether the bet wins"*.

**No colour** — the palette's red means *lose* (ADR 0081), and a failing
evidence check is not a loss. **No ordering** — ADR 0071 §2.5; shown, never
sorted by. That stays a separate decision needing its own evidence.

### Boundary

`gate.py` may never import it, the same boundary `manual_orders`,
`combo_orders` and the hedge tables each have. A trust score is not evidence
and may not move the live-trading interlock's counter. Asserted on the import,
not on the word — `gate.py` uses "trust" in prose, and a guard whose first
finding is a false one gets deleted.

## What this does NOT establish

- **That a high-trust row wins.** Nothing here is scored against an outcome.
  Doing so would be a new measurement with its own pre-registration, and it is
  the obvious next question.
- **That the checks are equally important.** They are counted equally because
  that invents nothing, not because anyone measured them to be equal.
- **That a full score means bet.** The desk informs a bet Joe is making anyway
  (ADR 0071); it does not manufacture action.

## Status of the surfaces

Shipped on the **parlay card**. The **slate row** and **market detail** were
chosen too and are not yet built; the module is deliberately surface-agnostic
so they consume the same score rather than computing their own.
