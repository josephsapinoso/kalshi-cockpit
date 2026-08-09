# Candle `yes_ask` vs the derived ask — ADR 0016 §3.3, re-scoped

**Date:** 2026-08-09
**Harness:** `scripts/reconcile_candle_ask.py`
**Tests:** `tests/test_candle_ask_reconciliation.py` (19)
**Raw:** `2026-08-09-candle-ask-reconciliation{,-run2,-deci}.json`
**Cost:** zero. Free Kalshi reads only, no odds credits, no orders, no deploy.

---

## `n` first

| Stratum | Distinct markets compared | Observations | Ask identity held |
|---|---|---|---|
| **game** (`KXMLBGAME`/`KXNFLGAME`/`KXWNBAGAME` moneyline) | **42** | 47 | 47 / 47 |
| **deci-cent** (`tapered_deci_cent`) | **4** | 4 | 4 / 4 |
| **total** | **46** | **51** | **51 / 51** |

The control — `bar.yes_bid.close` against the book's own published `yes_bid` —
passed **51 / 51**. Without that, a passing test could have been a coincidence
of timing rather than a fact about construction.

**46 distinct markets is the honest `n`, not 51.** Five markets were compared in
both game runs, four minutes apart; those are the same book seen twice, not two
independent draws. And 46 is small. It is small for a reason that turns out to
be the second finding of this exercise (§4), not because the sample was
constrained.

Of the 204 individual prices compared, **8 sat genuinely off the whole-cent
grid** — all in the deci-cent stratum, down to 0.5 of a cent. That is the cell
§3.3 specifically worried about, and it is the smallest one (§5).

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
day. **A structural disagreement would have shown on the first market; a
time-varying or intermittent one could pass this design unseen.**

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
| Game markets sampled | 60 | 166 |
| Compared | 14 | 33 |
| **TEST** `bar.yes_ask.close == 1000 − best_no_bid` | **14 / 14** | **33 / 33** |
| **CONTROL** `bar.yes_bid.close == book yes_bid` | 14 / 14 | 33 / 33 |
| `volume_fp` min / median / max | 18 / 6,021 / 31,100 | 0 / 6,454 / 414,020 |

A third run (§5) added 3 deci-cent markets on a fifteen-minute bracket: 3/3 and
3/3. A fourth, run ~25 minutes after the first as a smoke test of the harness
after it was refactored, compared 4 more game markets: 4/4 and 4/4. Its output
was not retained under `docs/measurements/`, so **it is excluded from every
count in this document** — it is corroboration, not evidence being banked.

Zero mismatches of any size. Not "within a tick" — **identical integers**, on
each of 51 observations across 46 distinct markets, spanning three leagues, two
tick structures, and `volume_fp` from 0 to 3.3 million.

Re-running four minutes later is the weakest possible version of "re-run at a
second horizon", and it is what the same-pass design allows. It moved nothing.

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
by construction of the experiment, not evidence against the identity.

Counting every row where the book was stable at both reads, the identity held
on **58 of 58** observations.

### The one-sided books explain *why* it agrees

Twelve rows were excluded because a side of the book was empty. They failed the
constancy precondition, so they are not evidence about the identity — but they
are legible, and together they show the mechanism:

| Book state | Live path | What the bar published |
|---|---|---|
| no NO bid | `derive_yes_ask` → `None` | `yes_ask` = 1000 (5 of 6 rows), 990 (1) |
| no YES bid | `derive_no_ask` → `None` | `yes_bid` = 0 (5 of 6 rows), 10 (1) |

`1000 = 1000 − 0`. **Kalshi appears to derive the ask the same way this repo
does, and to substitute `0` for an absent bid before deriving.** That is a
coherent rule, it is consistent with all 51 comparisons, and it is the same
"unreadable-resolves-to-zero" pattern `CLAUDE.md` bans on our side of the wire.
It is an inference from 12 rows, not a documented behaviour.

The single exception in each direction (990, 10) sat on a violently moving
in-play book — a WNBA and an MLB game, both at 1c/99c with one side of the book
empty, so the control could not be computed there at all. **The magnitude of the
substitution is not established by these rows; only that a number appears where
the live path refuses.**

---

## 4. The finding nobody asked for: bars are not emitted every minute

Over a **two-minute** window, most sampled markets returned **no bar at all**,
despite quoting two-sided books at both reads:

| | Bracket | Sampled | Returned ≥1 bar |
|---|---|---|---|
| Game, run 1 | 2 min | 60 | 29 (48%) |
| Game, run 2 | 2 min | 166 | 65 (39%) |
| Deci-cent, runs 1–2 | 2 min | 110 | 1 (1%) |
| Deci-cent, run 3 | **15 min** | 150 | 6 (4%) |

The last row is the same population at a 7.5x longer window for a 4x coverage
gain — sub-linear, which is what "bars follow activity" would predict and what
a fixed per-minute emission would not.

This is a fact about **bar availability**, and it is a Phase 0 operational risk
that ADR 0016 does not price in. §3.1 input 7 fixes the bar-selection rule as
`end_period_ts ≤ T`, which quietly assumes a bar exists near `T`.

**The mechanism is not established.** The obvious guess — bars follow activity —
is consistent with the data (markets with no bar skewed toward `volume_fp` under
50) but is not proven, and volume overlapped across the two groups (a market
with `volume_fp` 13.6 returned no bar while one at 17 did). It is not a hard
threshold.

**The sample is also the wrong regime for the question.** Most markets sampled
were days from kickoff (MLB games on 10–12 Aug, NFL preseason on 13–14 Aug),
read at a random minute. The backfill reads at `T = kickoff − 20 min`, when a
moneyline is far more active. **So 39–48% is a lower bound on coverage at the
backfill's horizon, not an estimate of it**, and it must be re-measured there
before Phase 0's scope is fixed. It does not threaten correctness; it threatens
how many of the ~1,200 games actually yield a row.

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
books are not rare (81 of 120 deci-structure markets probed had a best bid off
the grid); the difficulty is entirely that those series emit bars so seldom.

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

`n = 4` distinct deci markets is tiny and the effect size should not be read
from it. But the hypothesis this cell exists to kill is **structural**: if
Kalshi rounded a candle's published ask to whole cents, `KXPRESNOMR-28-TG` would
have shown `bar_ask` of 0 or 10, not 6. It showed 6. A rounding convention
cannot hide behind a small `n` when the price it would have to round is
resolvable at 0.1c and comes back exact. **What `n = 4` does leave open is a
rare or intermittent deci-cent defect**, which these observations cannot bound
at all.

---

## 6. What this does not establish

- **Agreement at horizons not sampled.** One instant, today. It says nothing
  about whether the identity held at any point inside the ~80-day retention
  window — which is precisely the data a backfill would read. A structural
  disagreement is excluded; a time-varying one is not.
- **Agreement for markets outside the sampled liquidity range** (`volume_fp` 0 to
  3,297,422; median ~6,200 in the game stratum).
- **Agreement in a moving book.** The constancy filter admits only markets whose
  quote stood still. That is deliberate — a moving book cannot separate a
  construction difference from a price change — but it means the result covers
  *quiet* books. That is the pre-game regime the backfill targets, and it is
  **not** the in-play regime, where the excluded rows disagreed 80% of the time
  on prices that had visibly moved between the two reads.
- **`n = 46` distinct markets, of which only 4 are deci-cent.** Enough to exclude
  a systematic construction difference, which would have shown on the first
  market. Not enough to bound a rare intermittent one: across 46 distinct
  markets a defect affecting 1 market in 20 would have been missed about 10% of
  the time, and in the deci-cent cell alone (`n = 4`) almost anything
  intermittent survives.
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

**Tests run:** two claims per comparison (TEST and CONTROL) over 51
observations, across two pre-declared strata, plus one bar-availability count.
A small, pre-declared set — not a scan over many cells — so no
multiple-comparisons correction applies. The result is also not the kind
multiplicity manufactures: it is zero deviation everywhere, not one significant
cell somewhere.

---

## 7. Verdict on ADR 0016 Phase 0

> **Proceed.** The backfill's price axis is sound. Input 5 should be moved from
> "⚠ partial" to clean, joining input 6, and the count in §3.1 becomes **13
> clean / 8 partial / 7 contaminated**.

The failure mode this check existed to catch — a published ask built differently
from the derived one — is not present. Kalshi's candle `yes_ask` and this
repo's `1000 − best_no_bid` are the same number, exactly, in integer tenths, on
every comparable market. Phase 0 is free and its data expires at ~80 days, so
the cost of proceeding is time and the cost of waiting is permanent loss.

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
   scope.** §4. Coverage of 39–48% at a random minute days out is a lower bound
   at the real horizon, but if coverage there is materially below 100% the game
   count — and therefore the `n ≈ 2,400` that justifies the whole build — needs
   restating.
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
