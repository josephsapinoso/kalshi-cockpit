# Candle `yes_ask` vs the derived ask — ADR 0016 §3.3, re-scoped

**Date:** 2026-08-09
**Harness:** `scripts/reconcile_candle_ask.py`
**Tests:** `tests/test_candle_ask_reconciliation.py` (25)
**Audited by:** `measurement-skeptic`, 2026-08-09 — verdict "overstated"; the
corrections are folded in and the retractions are marked in place.
**Raw:** `2026-08-09-candle-ask-reconciliation{,-run2,-deci}.json`
**Cost:** zero. Free Kalshi reads only, no odds credits, no orders, no deploy.

---

## `n` first

| Stratum | Observations | Distinct markets | Distinct **events** | Ask identity held |
|---|---|---|---|---|
| **game** (`KXMLBGAME`/`KXNFLGAME`/`KXWNBAGAME` moneyline) | 47 | 42 | **33** | 47 / 47 |
| **deci-cent** (`tapered_deci_cent`) | 4 | 4 | 4 | 4 / 4 |
| **total** | 51 | 46 | **37** | **51 / 51** |

The yes-bid control passed **51 / 51** — but see §3 for what that control can
and cannot cover; it is weaker than it looks.

**The honest `n` is 37, not 51, and probably not 46 either.** Three deflations,
each one level below the last:

- 51 observations → **46 distinct markets**: five markets were compared in both
  game runs, four minutes apart. The same book seen twice.
- 46 markets → **37 distinct events**: nine games contributed *both* sides, and
  the two sides of one Kalshi game are near-mirror books (`…CLECWS-CLE` at
  650/340 against `…CLECWS-CWS` at 340/650). Correlated views of one price.

Under the miss-probability framing used in §6, that is the difference between
"a defect in 1 market in 20 would have been missed 9% of the time" and **18%**.
The larger number is the right one.

Of the 204 individual prices compared, **8 sat off the whole-cent grid** — all
in the deci-cent stratum, all from **2 markets**, and all at ≤0.7c or ≥99.3c.
That is the cell §3.3 specifically worried about, and it is by far the weakest
one (§5).

---

## 1. The question

ADR 0016 §3.3 calls this "one free verification, before anything else". It gates
Phase 0 of the backfill — the free half that harvests Kalshi candlestick bars,
and the half that **expires at ~80 days**.

Live, this project never reads a published ask. It derives one, in exactly one
place (`backend/store/db.py:derive_yes_ask`):

    yes_ask = 1000 − best_no_bid        (integer tenths of a cent)

A candlestick bar instead **publishes** `yes_ask` directly. ADR 0016 marks input
5 as "⚠ different construction — published ask vs derived-from-bid". If the two
disagree by even one tick, every backfilled entry price is wrong, in the
direction that decides whether a 4c edge exists — because the entry price *is*
the derived ask. The predecessor project's +25.4 point "edge" that lost $4.92 a
market was bucketed on the mid and transacted at the ask; this is the same class
of error one level further back.

---

## 2. The re-scope, and how it differs from the ADR's design

**§3.3 as written is not runnable here.** It specifies an *offline*
reconciliation: "the live database already holds `kalshi_quotes` with real bids
at known instants. Pull the candle for the same minute and compare." The local
`data/demo.db` is synthetic and its `kalshi_quotes` table has zero rows, and the
live database is on a Fly volume this lane has no access to.

So the same identity was tested a different way: **capture a fresh quote and the
candle covering that same moment in one pass.**

| | ADR §3.3 (offline) | This run (same-pass) |
|---|---|---|
| Quotes | months of stored history | one instant, today |
| Regime | whatever the live poller saw | whatever was quoting 2026-08-09 20:15–20:41Z |
| Instants per market | many | one (two for five markets) |
| Establishes | agreement across the retention window | agreement at one instant, today |

**The difference matters and should not be glossed.** A same-pass run cannot
show the identity held on 2026-06-01, which is the data a backfill would
actually read. What it *can* show is whether the two are the same construction
at all — and a construction difference (a rounding convention, an off-by-a-tick,
a different source book) would be a property of the endpoint rather than of the
day. **A structural disagreement on a quiet two-sided book would have shown on
the first market; a time-varying or intermittent one could pass unseen — and one
confined to moving or one-sided books would too. One was: see §3.**

### The protocol, and why a naive comparison would mean nothing

A candle is OHLC over an interval; a quote is an instant. Comparing a bar's
close against a book read at some other moment measures the market's
volatility, not the endpoint's construction. Observed while building this: one
in-play MLB market's `yes_bid.close` went 0.77 → 0.61 → 0.67 → 0.73 over four
consecutive one-minute bars.

So a market entered the comparison only when the quote was shown to have stood
still across the bars being compared, by **two independent sources**:

1. The order book was read at `t0` and again at `t1`, and both best bids were
   unchanged. (Two reads cannot rule out a move-and-return, which is why 2
   exists.)
2. Every bracketed bar had `open == high == low == close` on **both** `yes_bid`
   and `yes_ask`, and agreed with every other bracketed bar — Kalshi's own data
   asserting the level never moved inside the interval.

A bar counted as bracketed only if its whole interval `(end−60, end]` fell
strictly between the two book reads, so no book read sat inside an interval it
was being compared against.

**On reading `high`/`low`/`open`.** ADR 0016 input 8 bans those fields for
*reconstructing a price*, correctly, because they look forward inside the bar.
They are read here for a different purpose — a constancy test in a live
reconciliation, where there is no `T` and nothing is being reconstructed. Only
`close` was ever compared. The ban is not weakened: a backfill must still read
`close` alone.

Both parsers are imported from production rather than reimplemented —
`store.db.derive_yes_ask` and `analysis.clv.parse_candlestick` — so the run
tests the code the money path executes, not a local restatement of it.

---

## 3. Result: they agree, exactly, in integer tenths

Two runs, four minutes apart, 2026-08-09.

| | Run 1 | Run 2 |
|---|---|---|
| Game markets sampled | 60 | 166 (a strict **superset** of run 1's 60) |
| Compared | 14 | 33 |
| **TEST** `bar.yes_ask.close == 1000 − best_no_bid` | **14 / 14** | **33 / 33** |
| **CONTROL** `bar.yes_bid.close == book yes_bid` | 14 / 14 | 33 / 33 |
| `volume_fp` min / median / max | 18 / 6,021 / 31,100 | 0 / 6,454 / 414,020 |

Where the other rows went — the full game-stratum histogram across all runs,
which the sampled/compared counts above hide:

| | markets | of those with a bar |
|---|---|---|
| sampled | 226 | |
| `no_bars` | 132 | — |
| **had a bar** | **94** | 100% |
| `book_moved` | 31 | 33% |
| `one_sided_book` | 12 | 13% |
| `bar_not_flat` | 4 | 4% |
| **compared** | **47** | **50%** |

Half the rows that carried data were dropped. That is the constancy filter
working as designed, and it is also the sample this result actually rests on.

A third run (§5) added 3 deci-cent markets on a fifteen-minute bracket: 3/3 and
3/3. A fourth, run ~25 minutes after the first as a smoke test of the harness
after it was refactored, compared 4 more game markets: 4/4 and 4/4. Its output
was not retained under `docs/measurements/`, so **it is excluded from every
count in this document** — it is corroboration, not evidence being banked.

Zero mismatches of any size **among comparable markets**. Not "within a tick" —
identical integers, on each of 51 observations, spanning three leagues and two
tick structures.

That qualifier is load-bearing. **The record contains 14 non-zero ask deltas**,
all on excluded rows — 12 `book_moved` and 2 `one_sided_book`. They are
discussed below and they are not swept into the headline.

Re-running four minutes later is the weakest possible version of "re-run at a
second horizon", and it is what the same-pass design allows. It moved nothing.

### What the control does not cover

An earlier draft of this document claimed that without the control "a passing
test could have been a coincidence of timing". That overstates it, and the
correction matters:

**The CONTROL compares `bar.yes_bid` against `book.yes_bid`. The TEST derives
from `book.no_bid`.** They touch different sides of the book. A bar carrying a
stale NO side passes the control and is caught by nothing except the constancy
filter. So the control establishes that the *right bar* was selected for the
YES side; it says nothing about the freshness of the quantity the ask is
actually built from. `tests/…::test_the_control_does_not_cover_the_side_the_test_consumes`
pins this so the claim cannot drift back.

The NO side is protected by the constancy filter alone — and the two
`book_moved` rows below are what a NO-side slip looks like.

### Are the exclusions hiding the disagreement?

The obvious attack on this result: markets were excluded, the survivors agreed,
and the filter manufactured the headline. No exclusion looks at `ask_delta` —
`compare()` returns before it is computed — but that only establishes the filter
is *blind* to the outcome, not that it is *neutral*. So: recompute the identity
on the excluded rows too, wherever both numbers exist.

| Exclusion | Book stable at `t0`/`t1`? | Computable | Ask identity held |
|---|---|---|---|
| `compared` | yes | 51 | **51 (100%)** |
| `bar_not_flat` | yes | 7 | **7 (100%)** |
| `one_sided_book` | n/a — a side was empty | 6 | 4 (67%) |
| `book_moved` | **no** | 15 | 3 (20%) |

This is the pattern a correct construction plus timing noise predicts, and it is
not the pattern a hidden disagreement would produce.

`bar_not_flat` is the informative row. Those markets were excluded because the
bar's OHLC showed the level moving inside the interval — but the book was
identical at both reads, so the quote moved and returned. They agree **7 of 7**.
Had the ask been built differently, they would have disagreed at whatever rate
the construction error implies, regardless of constancy. They disagree at the
same rate as the clean rows: zero.

`book_moved` disagrees 80% of the time, which is what comparing an interval's
close against a book read at a different price looks like. That group is noise
generated by the experiment, not evidence against the identity.

Counting every row where the book was stable at both reads, the identity held
on **58 of 58** observations.

**Two of the disagreeing rows deserve naming rather than burying**, because they
have the shape the harness's own docstring calls indicting — a failed test
beside a passing control:

| ticker | bar bid vs book bid | derived ask → bar ask |
|---|---|---|
| `KXMLBGAME-26AUG111915NYMATL-NYM` | 430 = 430 (control passes) | 460 → 450 (**−10**) |
| `KXMLBGAME-26AUG102140MILSD-MIL` | 490 = 490 (control passes) | 510 → 500 (**−10**) |

The innocent reading is that the NO bid moved while the YES bid held — which is
precisely the blind spot named above, and plausible on markets at `volume_fp` 4
and 2,412. **The record cannot confirm it**: these runs stored only the `t0`
book, so no reader can see which side moved. The harness now records `t1` as
well; these three runs predate that, so for them the innocent reading is an
assumption, not an observation. Anyone re-running this should check it.

### The one-sided books: where the identity actually fails

Twelve rows were excluded because a side of the book was empty. **They cannot
be both "not evidence" and the basis of a mechanism**, so here is what they do
and do not support.

What they establish, and it is the one thing that matters operationally:

| Book state | Live path | What the bar published |
|---|---|---|
| no NO bid | `derive_yes_ask` → `None` | `yes_ask` = 1000 (5 of 6 rows), 990 (1) |
| no YES bid | `derive_no_ask` → `None` | `yes_bid` = 0 (5 of 6 rows), 10 (1) |

**A bar publishes a number where the live path refuses.** That is a genuine
construction difference, and it is why Condition 1 in §7 exists.

What they do **not** establish is *why*. An earlier draft asserted that Kalshi
substitutes `0` for an absent bid and then derives (`1000 − 0 = 1000`). That
reading is contradicted by its own data: `KXMLBGAME-26AUG091335ATHBOS-ATH` had a
**live `yes_bid` of 990** and no NO bid, and the bar published `yes_bid` = **0**
alongside `yes_ask` = 1000. Substitution predicts `yes_bid` = 990 there. A
competing explanation — a bar with no usable quote is emitted as the sentinel
pair (0, 1000) — fits every cited row at least as well, and nothing here
separates the two. **The mechanism is not established and the claim is
withdrawn.** The action item does not depend on it.

Disclosure, since these rows are being discussed rather than discarded: of the
6 one-sided rows where an ask *was* derivable, **4 agreed and 2 disagreed**
(`…PHXWSH-PHX`, 10 → 20; `…ATHBOS-BOS`, 10 → 1000). Both exceptions come from
the same WNBA game and an in-play MLB game, both at 1c/99c with the YES side of
the book empty — so the control could not be computed on either. They fail the
constancy precondition and are not counted, but they are on the record.

---

## 4. The finding nobody asked for: bars are not emitted every minute

Over a **two-minute** window, most sampled game markets returned **no bar at
all**, while quoting a two-sided book at the first read:

> **Game stratum, pooled: 94 of 226 markets returned a bar — 41.6%
> (95% CI 35.4–48.1).**

Reporting run 1 and run 2 as separate rates would be wrong: **run 2's 166
markets are a strict superset of run 1's 60**. On the same 60 markets, coverage
went 29/60 (48%) to 18/60 (30%) five minutes later, and **15 of 60 flipped**
bar/no-bar state between the two windows. So the spread is mostly within-market
temporal variance, not a difference between populations, and the lowest figure
actually observed is 30%.

The deci-cent stratum is far worse — 1 of 110 at a 2-minute bracket, 6 of 150 at
15 minutes. Those are near-disjoint samples at different volumes (they share 3
markets), the difference is not separable from noise (Fisher two-sided
*p* = 0.24), and an earlier draft's "sub-linear, which is what bars-follow-
activity would predict" inference does not survive either point. Withdrawn.

This is a fact about **bar availability**, and it is a Phase 0 operational risk
ADR 0016 does not price in. §3.1 input 7 fixes the bar-selection rule as
`end_period_ts ≤ T`, which quietly assumes a bar exists near `T`.

**The mechanism is not established, and the obvious guess is wrong in the
obvious form.** Coverage by lifetime `volume_fp` across the game stratum:

| `volume_fp` | markets | returned a bar |
|---|---|---|
| < 50 | 28 | 25% |
| 50 – 500 | 42 | 29% |
| 500 – 5,000 | 33 | 36% |
| 5,000 – 50,000 | 80 | 29% |
| **> 50,000** | 43 | **93%** |

Flat below 50,000 and a step above it — not a gradient in traded volume. And
`KXMLBGAME-26AUG121545HOUSF-SF` returned a bar and was compared at `volume_fp`
**0.00**, which rules out lifetime volume as the gate outright. *Quote* activity
is the untested candidate; this run does not measure it.

One caveat on the framing above: `compare()` records `no_bars` before it
evaluates two-sidedness, and only the `t0` book was stored, so "quoting a
two-sided book" is verified at the **first read only** for the 132 no-bar rows.

**The sample is also the wrong regime for the question.** Most markets sampled
were days from kickoff (MLB games on 10–12 Aug, NFL preseason on 13–14 Aug),
read at a random minute. The backfill reads at `T = kickoff − 20 min`, when a
moneyline is far more active. **So 41.6% (CI 35.4–48.1) is a lower bound on
coverage at the backfill's horizon, not an estimate of it**, and it must be
re-measured there before Phase 0's scope is fixed. It does not threaten
correctness; it threatens how many of the ~1,200 games actually yield a row.

---

## 5. Deci-cent rounding: answered, on the smallest cell here

§3.3 names a deci-cent rounding convention as a specific hazard: *"If the two
differ — by a tick, by a rounding convention, on deci-cent markets — every
backfilled entry price is off."*

In the game stratum, **188 prices were compared and zero sat off the whole-cent
grid.** Every game-series market observed ticks `linear_cent`, so the
backfill's own population cannot exercise the question at all. The deci-cent
stratum had to be borrowed from elsewhere on the exchange, and at a two-minute
bracket it barely returned data — one comparable market out of 110. Off-cent
books are common enough to sample: **67 of the 257 distinct deci-structure
markets read here (26%) had a best bid off the whole-cent grid.** The difficulty
is that those series emit bars so seldom.

(An earlier draft cited "81 of 120" here. That number came from a scratch probe
that was not retained and it cannot be reproduced from any committed artifact.
26% is the figure the saved runs support, and it is the one that stands.)

A third run widened the bracket to **fifteen minutes** to catch them: 150
sampled, 144 returned no bar, 3 compared. All four deci-cent markets compared
across the three runs:

| Market | Run | book `yes_bid` | book `no_bid` | derived ask | bar `yes_ask.close` |
|---|---|---|---|---|---|
| `SENATELA-28-R` | 1 | 840 | 110 | 890 | **890** |
| `KXMIDTERMMOV-MI04D-P1` | 3 | 330 | 600 | 400 | **400** |
| `KXPRESNOMR-28-TG` | 3 | **5** | **994** | **6** | **6** |
| `KXPRESNOMD-28-CBOO` | 3 | **6** | **993** | **7** | **7** |

(integer tenths of a cent; 5 tenths is half a cent. Bold marks values off the
whole-cent grid.)

**8 of the 16 prices in this stratum were off the whole-cent grid, and the
identity held exactly on every one.** Control 4/4, test 4/4.

`n = 4` is tiny and the off-grid evidence is narrower still — **only 2 of the 4
carry any off-grid price at all**; `KXMIDTERMMOV-MI04D-P1` and `SENATELA-28-R`
are entirely whole-cent and contribute nothing to the rounding question. All 4
are `tapered_deci_cent`, where the deci ticks live only near 0 and 100, so all 8
off-grid prices sit at **≤0.7c or ≥99.3c on two long-dated nomination
longshots**. Seven pure `deci_cent` markets were sampled and none was ever
comparable.

What that does support: if Kalshi rounded a candle's published ask to whole
cents, `KXPRESNOMR-28-TG` would have shown `bar_ask` of 0 or 10, not 6. It
showed 6. **A whole-cent rounding convention is refuted.** What it does not
support is anything about the **mid-range**, which no compared deci market
sampled, or about intermittent defects, which `n = 2` cannot bound.

Two excluded rows narrow that mid-range gap without closing it. Both failed the
constancy filter (`bar_not_flat`) so neither counts, but both carry a mid-range
off-grid price and the identity held exactly on each:

| Market | book `yes_bid` / `no_bid` | derived ask | bar `yes_ask.close` |
|---|---|---|---|
| `KXMIDTERMMOV-MNSEND-P1` | 860 / **86** | **914** | **914** |
| `KXFEDCHGCOUNT-27JAN01-E1` | 326 / **608** | **392** | **392** |

39.2c and 91.4c — the region §5 would otherwise have to call untested.
Corroborating, excluded, not load-bearing.

---

## 6. What this does not establish

- **Agreement at horizons not sampled.** One instant, today. It says nothing
  about whether the identity held at any point inside the ~80-day retention
  window — which is precisely the data a backfill would read. A structural
  disagreement is excluded; a time-varying one is not.
- **Agreement for markets outside the sampled liquidity range.** Reported per
  stratum, because the harness promises never to pool them: game `volume_fp` 0
  to 414,020 (median ~6,200); deci-cent 3,737 to 3,297,422.
- **Agreement in a moving book.** The constancy filter admits only markets whose
  quote stood still. That is deliberate — a moving book cannot separate a
  construction difference from a price change — but it means the result covers
  *quiet* books. That is the pre-game regime the backfill targets, and it is
  **not** the in-play regime, where the excluded rows disagreed 80% of the time
  on prices that had visibly moved between the two reads.
- **`n = 37` distinct events, of which 4 are deci-cent.** Enough to exclude a
  systematic construction difference on quiet two-sided books, which would have
  shown on the first market. Not enough to bound a rare intermittent one: across
  37 events a defect affecting 1 in 20 would have been missed about **18%** of
  the time, and in the deci-cent cell (`n = 4`, of which 2 carry off-grid
  prices) almost anything intermittent survives.
- **That `depth_at_ask` is recoverable.** It is not, at any price. ADR 0016 §3.2
  settles that from the captured fixture and nothing here revisits it.
- **That the backfill's other contaminated inputs are safe.** This verifies
  input 5 and touches input 6. Inputs 7, 8, 9, 10, 25, 27 and 28 are untouched.
- **That the identity will hold tomorrow.** Kalshi can change a construction
  without notice, exactly as it can change the retention window.
- **The exclusion analysis is post-hoc.** The four groups in §3 were not
  pre-registered as comparison cells; they are the harness's own exclusion
  reasons, recomputed after the fact. They are a robustness check on this
  result, not an independent finding, and the `bar_not_flat` cell is `n = 7`.

**Tests run:** 102 claims (51 comparisons × TEST and CONTROL), plus one
bar-availability count. No multiplicity correction is applied, and the reason is
**not** that the set was pre-declared — it was not. Run 2 raised `--max-game`
from 60 to 200 after seeing run 1; run 3 changed the stratum, the bracket (2 →
15 bars), the sample (30 → 150) and the page depth (6 → 12) *after* the
two-minute deci run returned almost nothing. **That is optional stopping: the
deci sampling was widened until deci markets appeared.** Had a mismatch lived
among the 144 markets that returned no bar, it would never have been seen.

The correction is unnecessary for a different reason: multiplicity manufactures
*one significant cell somewhere*, and this result is zero deviation in every
cell. A scan cannot fabricate that.

---

## 7. Verdict on ADR 0016 Phase 0

> **Proceed.** The backfill's price axis is sound on two-sided books. Input 5
> moves from "⚠ different construction" to clean **only under a stated rule** —
> joining inputs 11 and 13 in §3.1's existing "clean only under the stated rule"
> parenthetical, not the unconditional list. The rule: *exclude bars publishing
> `yes_ask = 1000` or `yes_bid = 0` where the opposing bid is absent.* The §3.1
> tally becomes **13 clean / 8 partial / 7 contaminated**.

The failure mode this check existed to catch is **absent on two-sided books and
present at the boundary.** On every comparable market Kalshi's candle `yes_ask`
and this repo's `1000 − best_no_bid` are the same integer. But where a side of
the book is empty the bar publishes a number and `derive_yes_ask` returns
`None`, and that *is* a construction difference — Condition 1 below is the
acknowledgement of it, not a precaution against a hypothetical.

Phase 0 is free and its data expires at ~80 days, so the cost of proceeding is
time and the cost of waiting is permanent loss.

**Three conditions, in order of severity:**

1. **A backfill must not read a boundary quote as a price.** On the 12 one-sided
   rows seen, a bar published `yes_bid = 0` where the book had no YES bid and
   `yes_ask = 1000` where it had no NO bid — a number where `derive_yes_ask`
   returns `None` and the caller refuses. Twelve rows on near-resolved in-play
   markets is thin evidence for a general rule, which is an argument for
   handling it, not for assuming it away. Flag those rows and exclude them from
   the actionable-rate measurement; do **not** silently null them, because 0 is
   a genuine price on a settled loser and the two cases must stay
   distinguishable. Left unhandled, a fabricated 1c ask presents as an enormous
   edge — CLAUDE.md rule 1, arriving as data.
2. **Measure bar coverage at `T = kickoff − 20 min` before fixing Phase 0's
   scope.** §4. Coverage of 41.6% (CI 35.4–48.1) at a random minute days out is
   a lower bound at the real horizon, but if coverage there is materially below
   100% the game count — and therefore the `n ≈ 2,400` that justifies the whole
   build — needs restating.
3. **Do not carry the deci-cent result beyond its `n`.** §5. The identity held
   exactly on sub-cent prices, which kills the rounding-convention hypothesis,
   but on `n = 4` markets. Phase 0 is unaffected either way — every game-series
   market observed ticks `linear_cent` — so this is a note for any later
   extension to a deci-cent population, not a blocker now.

**What would overturn this.** The offline reconciliation §3.3 actually
specifies, run against `kalshi_quotes` on the live volume once that is
reachable. It costs nothing, it covers the retention window this run cannot, and
it is the only thing that closes the time-varying gap. Phase 0 should not wait
for it — the bars are expiring — but Phase 1's credits should not be spent
before it runs.
