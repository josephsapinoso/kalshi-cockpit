# Half-spread dispersion — the `Var(half_spread)` term in the CLV test's C2 confound

**Measured 2026-08-09 against the live Kalshi API, read-only and
unauthenticated. No orders. No deploy. The Odds API was not called and no
credits were spent.**

- Harness: `scripts/measure_halfspread_dispersion.py`
- Raw output: `docs/measurements/2026-08-09-halfspread-dispersion.txt`
- Full result: `docs/measurements/2026-08-09-halfspread-dispersion.json`
- Tests: `tests/test_halfspread_dispersion.py` (31, each verified to fail when
  the guard it pins is disabled)

---

## The question

`docs/measurements/2026-08-09-preregistration-clv-signal-test.md` §C2 shows that
`clv_tenths` and `edge_tenths` are both computed against the same
`entry_ask_tenths`, so

```
CLV  = close_mid - ask   = (close_mid - entry_mid) - half_spread
edge = fair - ask - fee  = (fair - entry_mid)      - half_spread - fee
```

and therefore `Cov(edge, CLV)` contains `+Var(half_spread)`. A strictly positive
slope arises from mechanics with zero predictive power. **The algebra is
correct and is not disputed here.**

What was never measured is the magnitude. The document assumes
`sd(half_spread) = 4` tenths against `sd(edge_tenths) = 10` tenths, gets a
spurious slope of ~0.16, calls it *"the largest finding in this document"*, and
builds prerequisite **P1** on it — a hard block: *"if that fraction is below
0.90, the primary analysis does not run."*

`Var(half_spread)` is the entire term. This measurement supplies it.

It is **not** the question ADR 0006 §4 answered. That reported the pre-game
spread *mean* (1.00c, on 20 games, one night, two leagues). A mean is not
dispersion, and 20 games is not a population.

---

## Method

### Where the number comes from

The half-spread in tenths, via the derived-ask identity
(`core.prices.complement`, `store.db.derive_yes_ask`):

```
half_spread_tenths = ((1000 - no_bid_tenths) - yes_bid_tenths) / 2
```

Every price on both arms arrives as a **4-decimal dollar string** and is parsed
by `core.prices.dollars_to_tenths` — the same reader the recorder uses — so
deci-cent ticks survive. This matters: a whole-cent measurement would have
reported exactly the 1.00c constant that was in question. Kalshi's
`.../candlesticks` endpoint returns `yes_bid.close_dollars` / `yes_ask.close_dollars`
in the same 4-decimal form, so the candlestick arm is not resolution-limited
either.

### Arm B — the panel, and the primary

Settled game markets in the leagues `discovery.classify_series` actually puts in
scope, for games starting in the **14 days to 2026-08-09**, over the **final 180
minutes before the true start**, at **one-minute** candlestick resolution
(`period_interval=1`).

That window is not arbitrary. `odds.timing.slots_for_sport` fires a sweep at
`anchor - max_odds_age_ms` and covers games out to `anchor + COVERAGE_MS` (3
hours), and `runner.record_recommendations` re-derives every row while the 900s
odds window is open. So rows are written about markets roughly 0–3 hours from
their own kickoff. Markets days away from kickoff are not this population, and —
see Arm A — they look completely different.

The true start is `occurrence_datetime - 3h`, applied **only where
`occurrence_datetime == expected_expiration_time`**, which is ADR 0006 §1's
finding used as a condition rather than as an assumption. Where the two fields
disagree the field is taken at face value, because `KXMLBF5` is a series where
subtracting three hours produced a "start" 41 minutes after the market had
closed.

### Arm A — the live cross-section, and the control

Every in-scope market open at 2026-08-09T20:54Z, stratified by time to kickoff.
It exists to answer the question Arm B cannot: **is the near-kickoff tightness a
property of the market, or of the harness?**

Arm A is also where the derived-ask identity is verified, on live books that
publish `yes_ask_dollars` and `no_ask_dollars` beside the bids.

### Two controls, because a near-zero answer is the easiest kind to fake

1. **The identity holds.** `yes_ask == 1000 - no_bid` and
   `no_ask == 1000 - yes_bid`: **1,071 live quotes checked, 0 violations.**
2. **The instrument can see width.** The 15 widest live two-sided markets were
   re-read fresh and their latest one-minute bar pulled. **15 of 15 came back
   wider than one tick**; 13 of 15 matched the live book exactly (the two that
   did not are books that moved inside the bar's ≤60s lag); **the widest bar
   reported 410 tenths — a 41c spread.** The reader can represent width. It
   found none in the pre-game window.

Every candlestick bar is either kept or counted as a drop, by reason. Across the
whole panel: **78,047 bars seen, 78,047 kept, 0 dropped.** No bar was discarded
for a missing side, a one-sided book, or a crossed quote, so the filter cannot
be what made the answer constant.

---

## `n` — read this before the effect size

`n` is three numbers and **only the first is independent**:

| unit | Arm B (panel) | what it is |
|---|---:|---|
| **games** | **219** | the honest denominator. Two moneyline markets on one game settle from one final score. |
| markets | 438 | exactly 2 per game |
| market-minutes | 78,047 | 178 minutes per market. **Not 78,047 observations of anything.** |

Every distribution below is repeated with **one median per market** and **one
median per game**, so a market quoted for 178 minutes cannot carry a percentile.
`tests/test_halfspread_dispersion.py` pins the invariant that duplicating the
whole record `k` times leaves the per-game and per-market distributions
bit-identical.

Leagues: **Pro Baseball (65,201 minutes) and Pro Basketball (W) (12,846
minutes)**. Those are the only in-scope leagues with settled games in the
window. NCAAF and the NFL regular season had not started; NBA and NHL were out
of season.

---

## The distribution

### Arm B — pre-game, 0–180 minutes to kickoff, 219 games

Half-spread, **tenths of a cent**:

| view | n | mean | **sd** | min | p50 | p90 | p99 | max | distinct values |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| per market-minute | 78,047 | 5.01 | **0.27** | 5.0 | 5.0 | 5.0 | 5.0 | **10.0** | **2** |
| one median per market | 438 | 5.00 | **0.00** | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 1 |
| one median per game | 219 | 5.00 | **0.00** | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 1 |
| within-market sd | 438 | 0.08 | 0.25 | 0.0 | 0.0 | 0.4 | 1.1 | 1.7 | 29 |

**The half-spread takes exactly two values in the entire panel: 5 tenths
(0.5c) and 10 tenths (1.0c).** 77,817 of 78,047 minutes (99.71%) are at 5
tenths. The 230 wider minutes (0.29%) are spread over 44 of the 438 markets and
are all a 2c book — the widest observation in the whole panel is a half-spread
of 10 tenths, e.g. `KXMLBGAME-26AUG072215DETSF-SF` at 420/440 with 27 minutes to
first pitch.

**The final 15 minutes only** — the window ADR 0011 scores CLV in — n = 6,567
market-minutes over the same 219 games: mean 5.04, **sd 0.43**, p99 5.0, max
10.0, 99.24% at the floor.

### The parts agree

| stratum | n | mean | sd | max |
|---|---:|---:|---:|---:|
| Pro Baseball | 65,201 | 5.02 | 0.28 | 10.0 |
| Pro Basketball (W) | 12,846 | 5.01 | 0.21 | 10.0 |
| ask ∈ [10,200) | 1,521 | 5.03 | 0.40 | 10.0 |
| ask ∈ [200,800) | 74,999 | 5.01 | 0.27 | 10.0 |
| ask ∈ [800,990) | 1,527 | 5.00 | 0.13 | 10.0 |
| 0–15 min to kickoff | 6,567 | 5.04 | 0.43 | 10.0 |
| 15–60 min | 19,631 | 5.01 | 0.24 | 10.0 |
| 60–180 min | 51,428 | 5.01 | 0.26 | 10.0 |

Price buckets are Grid A from the pre-registration §4, on the derived ask, reused
verbatim rather than re-chosen. **No stratum has an sd above 0.43 tenths.** The
pooled number is not carried by one league, one price band, or one distance from
kickoff.

### Arm A — the live cross-section, and why the panel is not the whole story

Read at 2026-08-09T20:54Z: 154 in-scope events walked, 132 with a market still
pre-game, 1,071 markets.

Moneyline only — the market type the recorder writes rows about:

| minutes to kickoff | n | mean | sd | max |
|---|---:|---:|---:|---:|
| 60–180 | 2 | 5.0 | **0.0** | 5 |
| 180–720 | 2 | 5.0 | **0.0** | 5 |
| 720–2,880 (½–2 days) | 24 | 5.4 | 1.4 | 10 |
| 2,880+ (2 days to a month) | 110 | 11.8 | 9.1 | 50 |

All in-scope market types together — **which is a different and much wider
distribution**:

| minutes to kickoff | n | mean | sd | max |
|---|---:|---:|---:|---:|
| 0–15 | 8 | 16.2 | 29.8 | 95 |
| 15–60 | 11 | 28.6 | 34.3 | 100 |
| 60–180 | 32 | 7.8 | 7.1 | 35 |
| 180–720 | 19 | 5.0 | 0.0 | 5 |
| 720–2,880 | 165 | 9.8 | 3.7 | 20 |
| 2,880+ | 836 | 51.4 | 40.3 | **205** |

By market type (all times to kickoff): moneyline n=138, mean 10.5, sd 8.6, max
50; **spread n=508, mean 59.6, sd 47.2, max 205; total n=425, mean 32.0, sd
22.8, max 140.**

Two things to take from this. First, **wide spreads are real on Kalshi sports
and they are easy to find** — a 20.5c half-spread exists today
(`KXNFLSPREAD-26SEP13NYJTEN-NYJ3`, a month from kickoff). The measurement is not
"Kalshi never quotes wide"; it is "by the time the recorder is looking at a
moneyline, the book has converged to the tick". Second, **the wide rows inside
the 0–60 minute buckets are spreads and totals, not moneylines** — which is why
the moneyline-only restriction in §"What this does not establish" is
load-bearing rather than cosmetic.

---

## The tick floor, and the censoring assessment

**Every market sampled on both arms is `linear_cent`, with a single
`price_ranges` band of `step = "0.0100"` — 10 tenths.** So:

- the narrowest observable **spread** is 10 tenths (1c);
- the narrowest observable **half-spread** is 5 tenths (0.5c);
- **99.71% of the panel sits exactly on that floor.**

**Yes, this distribution is censored from below, and the mode is the censoring
point.** The honest statement is: the measured `sd(half_spread) = 0.27` tenths
is a *lower bound* on what market makers would quote if the grid were finer. If
Kalshi moved sports markets to a half-cent grid, the support would widen and this
number would have to be re-taken.

Two things follow, and they point in opposite directions, so both are stated:

1. **The censoring does not weaken the conclusion for this analysis.** What
   enters `Cov(edge, clv)` is the half-spread *actually paid*, which is the
   censored one. The confound is driven by the spread the strategy transacts at,
   not by a hypothetical finer one.
2. **The censoring is why the answer could change without warning.**
   `kalshi/grid.py` records that `scripts/capture_price_grids.py` found 1,426
   game markets on one grid on 2026-08-08, and that
   `.claude/skills/kalshi-api/SKILL.md` counted 60 `center_half_edge_half_cent`
   game markets on 2026-08-06. Kalshi publishes a `price_level_structure_updated`
   lifecycle event; a market's grid can change while it is open. This is a fact
   about today's slate, not about the exchange.

**It is not a resolution artefact of the harness.** Candlesticks return
4-decimal dollar strings and the parser preserves tenths; had a market quoted
50.5/51.0 it would have been read as a 2.5-tenth half-spread. None did.

**ADR 0006's "1.00c at every percentile including the max" is very slightly
wrong, and the correction is tiny.** On 20 games it saw zero pre-game minutes
wider than 1c. On 219 games there are 230 such minutes — 0.29%. So the earlier
claim was a small-`n` artefact of a real effect, not a false one. Nothing that
depended on it changes.

---

## The spurious slope, computed

`Var(half_spread) / Var(edge_tenths)`, the pre-registration's own formula:

| assumed `sd(edge_tenths)` | per market-minute | per game | **pre-registration's figure** |
|---|---:|---:|---:|
| 5 tenths | 0.0029 | 0.0000 | — |
| **10 tenths (its central assumption)** | **0.0007** | **0.0000** | **0.16** |
| 15 tenths | 0.0003 | 0.0000 | — |
| 20 tenths | 0.0002 | 0.0000 | — |

On the narrowest, most adverse cut inside the recorder's window — the final 15
minutes — it is **0.0019** at `sd(edge) = 10`.

**0.16 is too large by a factor of roughly 230.**

### `sd(half_spread) = 4` tenths is not merely wrong; on this grid it is impossible

The half-spread's support in the panel is `{5, 10}` tenths. For a two-point
support the standard deviation is `sqrt(p(1-p)) × (10 - 5)`, maximised at
`p = 0.5`, giving **2.5 tenths**. The assumed 4 tenths would need
`sqrt(p(1-p)) = 0.8`, i.e. `p(1-p) = 0.64`, which exceeds the maximum of 0.25 for
any probability. **No mixture of one-cent and two-cent spreads can produce
`sd = 4`.** Reaching it requires spreads of 3c and wider to be common — which is
what markets a month from kickoff look like, and nothing like what the recorder
sees.

---

## The one thing this could not measure, and the bound that replaces it

The confound that matters is `Var(half_spread)` **among the rows the CLV test
scores**, and the brief's live concern was that recommendations are written on
markets where Kalshi disagrees with a sportsbook consensus — plausibly the
wide-spread tail. Isolating that subset requires the consensus, which costs Odds
API credits, which this measurement was forbidden to spend. **It was not
measured and no claim is made about it.** Two things stand in its place.

### 1. Source check: the recorded population is barely selected at all

`backend/runner.py:record_recommendations` writes a row for **both sides of every
matched moneyline market** with a readable quote — there is no edge filter, and
`engine.persist_recommendation`'s docstring is explicit ("Store a
recommendation, suppressed or not"). The pre-registration §2 keeps `no_edge`
rows and `suspicious_edge` rows deliberately. So the analysis population is close
to *all* matched pre-game moneylines, not the disagreement tail.

Note also that the half-spread is a property of the **market**, not the side:
`((1000 - no_bid) - yes_bid)/2` for YES and `((1000 - yes_bid) - no_bid)/2` for
NO are the same number. Selecting a side cannot select a half-spread.

This weakens the selection worry considerably. It does not eliminate it — the
*scored* subset additionally requires a readable candlestick near kickoff, which
is liquidity-flavoured, and liquidity correlates with spread.

### 2. A bound that no selection can beat

Since the half-spread's support is `{5, 10}` tenths, **any** cut of this
population — however adversarial, however chosen after the fact — is a
reweighting of two points, and no reweighting of a two-point support exceeds
`(max - min)/2 = 2.5` tenths.

| if the wide (2c) fraction were… | implied `sd` | spurious slope at `sd(edge)=10` |
|---|---:|---:|
| 0.29% (**observed**) | 0.27 | **0.0007** |
| 1% | 0.50 | 0.0025 |
| 5% (17× the observed rate) | 1.09 | 0.0119 |
| 10% (34×) | 1.50 | 0.0225 |
| 25% | 2.17 | 0.0469 |
| 50% (the arithmetic maximum) | 2.50 | **0.0625** |

**Even the arithmetically impossible worst case — half of all scored rows drawn
from the 0.29% of market-minutes that quote 2c — gives 0.0625, which is still
2.6× below the assumed 0.16.** A selection that tripled or even multiplied the
wide rate by seventeen gives 0.012.

This is the strongest honest statement available without spending a credit:
**the confound cannot reach 0.16 by selection, because the population does not
contain the values that would be needed.**

---

## Verdict

### On the 0.16 spurious-slope figure: **drop it and replace it**

It should be replaced with the measured **0.0007** (219 games, 78,047
market-minutes, `sd(half_spread) = 0.27` tenths against the same assumed
`sd(edge) = 10`), and with the selection bound of **≤ 0.0625 under any cut**.

The sentence *"this is the largest finding in this document"* should be struck.
The algebra stays — it is right, it is worth having written down, and it is what
makes the bound computable. What goes is the magnitude and the standing.

The pre-registration is entitled to say it did the right thing: it flagged a real
mechanism and put a number on it *before* seeing data, exactly as a
pre-registration should. The number was an assumption clearly labelled as one
("a plausible half-spread SD of 4 tenths"). This measurement is the check that
assumption invited.

### On prerequisite P1: **revise — demote from blocking to reporting. Do not delete.**

**Why it should not stay blocking.** P1's stated purpose is to make the C2
control computable. With `Var(half_spread) ≈ 0`, `gamma` is estimated on a
regressor with essentially no variation: it is not identified, it absorbs
nothing, and its presence or absence cannot move `beta_hat` materially. A hard
block whose only justification is a control that does nothing is a block that
can only cost `n`. Given the design is already **UNDERPOWERED at any `n`
plausibly available today**, that cost is not hypothetical.

**Why it should not be deleted.** Three reasons, none of them C2:

1. **It is also a data-integrity check on the record itself.** A NULL
   `half_spread_tenths` means no `kalshi_quotes` row joined before `created_ms`.
   A record where 40% of scored rows have no pre-entry quote has a real problem —
   the quote pass is not writing, or the join is wrong — and P1 is currently the
   only thing that would surface it. That is worth keeping, reported at every
   look.
2. **The selected population was not measured.** The bound is small but not zero.
3. **The grid can change.** `price_level_structure_updated` is a real lifecycle
   event and half-cent game markets have existed on this exchange within the last
   week. If sports markets move to a finer grid, the support widens and this
   whole finding must be re-taken.

**The concrete revision, offered for the pre-registrar to write as a dated
amendment:**

> **P1 (amended).** Report, at every interim look: the fraction of scored rows
> for which the §S1 join returns a non-NULL `half_spread_tenths`;
> `sd(half_spread_tenths)` on the analysis population; and the implied spurious
> slope `Var(half_spread)/Var(edge_tenths)`. **The primary analysis is blocked
> only if that implied slope exceeds 0.04** — roughly a tenth of the smallest
> `beta` this design can resolve at `G = 300` (0.42). Coverage below 0.90 is
> **reported and investigated as a defect in the record**, and does not by itself
> stop the analysis.

0.04 is offered rather than asserted; what matters is that the gate moves from a
*proxy* (coverage) to the *quantity that actually matters* (the implied slope),
which is computable from the same join at no extra cost.

**A second amendment the pre-registrar should consider separately, with its cost
named.** §2 currently excludes rows where `half_spread_tenths IS NULL`. If the
control absorbs nothing, that exclusion buys nothing and costs `n`. Retaining
those rows and dropping `gamma` from the model would recover them — but it
**changes the population definition**, which under §7 restarts `G` for the
decision rule. That is a real cost on a design that needs `G >= 300`, and it is
why it is flagged as a separate decision rather than folded into the P1
revision above. Demoting P1 as written above is population-neutral and does not
restart `G`.

### Two incidental corrections to the pre-registration, free from the same data

- **§5's null offset is sharper than stated.** It says
  `E[clv_tenths] = -half_spread ≈ -5 to -15 tenths` under zero predictive power.
  It is **-5.0 tenths, with essentially no dispersion**, on 219 games. The level
  test's null is a point, not a range.
- **§9's caveat** — *"if P1 lands between 0.90 and 1.00, the residual
  contamination is proportional to the missing fraction and must be stated as a
  number"* — that number is now available and it is **≈ 0.0007 × (missing
  fraction)**, i.e. negligible at any coverage.

---

## What this does not establish

- **It does not measure the selected population.** No consensus was fetched, so
  "markets where Kalshi disagrees with the books" was never isolated. The
  selection bound above is a ceiling argument, not a measurement of the cut.
- **It says nothing about `beta`.** It bounds one contaminant of `beta`. The
  pre-registration's verdict — **UNDERPOWERED, wait, do not run** — is untouched
  by this and remains the operative instruction. Removing a confound does not
  create a sample.
- **Two leagues, fourteen days, one August slate.** Pro Baseball and Pro
  Basketball (W). Nothing about NFL regular season, NCAAF, NBA, or NHL, whose
  liquidity and spread regimes were not observed. Arm A's cross-section shows
  in-scope moneylines a month out quoting up to a 5c half-spread, so a league
  whose recorder window sits earlier in its price discovery could look different.
- **Moneyline only, on the primary arm.** Kalshi's in-scope **spread** markets
  live-quote at mean 59.6 tenths, sd 47.2; **totals** at mean 32.0, sd 22.8 —
  over a hundred times the moneyline's dispersion. `runner.py` writes rows for
  moneylines only today. **If that ever changes, every number in this document
  must be re-taken before the CLV test runs.** This is the single most likely way
  for the C2 confound to come back.
- **Pre-game only.** ADR 0006 measured in-play and found the tail fattens.
- **A candlestick close is a minute-end snapshot, and unsized.** Everything
  inside the minute is invisible, and a quote nobody could transact counts the
  same as one that could.
- **It is censored from below**, as set out above, and would have to be re-taken
  on a finer grid.
- **The start time is inferred**, not published: `occurrence_datetime - 3h`,
  applied only where that field equals `expected_expiration_time`. Games running
  long or short shift the time strata by tens of minutes. The strata are
  directional, not precise — which does not matter here, because every stratum
  gives the same answer.
- **`n = 219` is games, not 78,047.** Said again because the large number is the
  one that will get quoted.

---

## Incidental finding, outside this lane

Kalshi spells NFL preseason `product_metadata.competition = "Pro Football
Preseason"`. `discovery.IN_SCOPE_LEAGUES` keys on `"Pro Football"`. So the
**32 preseason game events and 726 preseason markets open today are classified
out of scope** and no row is written about them. That may be deliberate — the
odds side may not cover preseason, and preseason is a genuinely different pricing
regime — but it is not recorded anywhere as a decision, and it is exactly the
shape of the "Womens Pro Basketball" / "Pro Basketball (W)" bug that
`discovery.py`'s own comment warns about. Flagged here rather than fixed;
it belongs to whoever owns discovery.
