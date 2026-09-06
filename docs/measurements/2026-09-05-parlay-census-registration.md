# PRE-REGISTRATION — the parlay census, and what it can and cannot say

**Written 2026-09-05, before any per-row read, any join, and any pairing of an
outcome with a stated probability.** Every population predicate, every unit,
every threshold, every denominator, the stopping rule and the decision rule are
fixed below, so that none of them can be chosen once the answer is visible.

Joe's question, in his words:

> *"an assessment of how each parlay I picked performed against the
> recommendations I have been receiving. See what we can learn from it to
> improve the parlay recommendations."*

**The headline of this registration is a refusal and it is free.** The question
as asked — *did my parlays perform well against what the desk told me* — cannot
be answered at the `n` in the record, and the arithmetic in §0 says so before
anything is looked at. Two of fifty-one resolved positions won; five of
fifty-two bought tickers have a desk price recorded at all. What the record
*can* answer is a different and, as it happens, more decision-relevant
question: **were these parlays bought as taker or as maker** — which tests a
claim three shipped surfaces currently make in Joe's face — and **what the
recommendation funnel actually looks like** from push to fill. Those are §D and
§E and they carry the only verdict in this document.

**This is a census, not a hunt.** ADR 0038 closed the edge hunt. Nothing here
reopens it, nothing here is evidence about `beta`, the 300-game gate, the
0.63-point cost headroom or the 51.75% break-even bar, and no verdict below may
be quoted in a sentence about edge. It touches `fills`, `venue_settlements`,
`parlay_lookups` and `notifications`. **It must never be pooled with
`recommendations`**, which is engine output and the registered population of the
ADR 0021/0034 CLV signal test — `backend/store/schema.sql:1182` says so in the
schema itself, and pooling hand-placed combination bets into it would
contaminate a different registered measurement with rows that were never engine
recommendations.

---

## 0. DECLARED BLINDNESS — exactly what has already been seen

This section exists because a pre-registration written after a partial read is
worth only what it declares. The following aggregates were read off the live
database **before** this file was written, and are therefore **not blind**:

| Seen | Value |
|---|---|
| `fills` rows with `ticker LIKE 'KXMVE%'` | 53, across 52 distinct tickers |
| First / last such fill | 2026-08-18T09:45Z / 2026-09-03T21:43Z |
| `venue_settlements` rows for those tickers | 52 |
| `market_result` split | `'no'` 49, `'yes'` 2, `''` 1 |
| Contracts on the `'no'` rows (all `side='yes'`) | 3995.76 |
| Contracts on the `'yes'` rows / the `''` row | 4.05 / 4.34 |
| `SUM(contracts * entry_price_tenths)/1000` | $60.13 |
| `SUM(fee_cost_tenths)/1000` | $3.74 |
| `parlay_lookups` rows | 34 (2026-08-22 → 2026-09-05), 31 with a non-null `minted_market_ticker` |
| `parlay_lookups.status` split | `book_empty` 24, `priced` 7, `error` 3 |
| Filled tickers appearing as a `minted_market_ticker` | 5 of 52 |
| `parlay_positions` / `parlay_position_legs` / `manual_orders` | 0 rows each |

**What follows from that, and it is binding.** Any statistic that is a
deterministic function of the table above **has already been observed and may
not be presented as a test of anything.** That covers:

- the win rate (2 of 51),
- total staked, total fees, and therefore net P&L to within the payout on
  4.05 contracts,
- the pooled `parlay_lookups` status proportions (24 / 7 / 3),
- the desk's coverage of Joe's parlays (5 of 52).

These are **transcriptions**. They are reported in the write-up because Joe
asked for them and they are true, and they carry **no verdict, no threshold and
no p-value**. A threshold applied after the number is known is not a threshold.

**What has NOT been seen, and is therefore genuinely blind:**

- `is_taker` on any of the 53 fills or 52 settlements — **the primary test**;
- `source`, `venue_order_id`, `n_fills_in_position` on any row;
- the per-position distribution of `contracts` and `entry_price_tenths`, hence
  every concentration figure;
- which tickers, which dates, which sports, which collections;
- `fair_joint_conservative`, `derived_yes_ask_tenths`, `book_depth` on any
  individual lookup, and any pairing of a lookup with an outcome;
- the `notifications` parlay-card counts and any leg-set overlap;
- `estimate_match_status`, `position_time_source` on any row.

---

## 1. GLOSSARY — every term defined at first use

- **Combination market / combo / KXMVE.** Kalshi's multivariate-event product:
  one contract that pays $1 if *all* its legs happen. The sportsbook word is
  *parlay*. Tickers begin `KXMVE`.
- **Leg.** One of the individual outcomes a combination requires.
- **Taker.** You buy at a price already resting on the book — someone else's
  offer was there and you hit it. Proves an offer existed.
- **Maker.** You post a price and wait; you fill only if someone comes to you.
  Proves a counterparty arrived, not that an offer was available.
- **Derived YES ask.** What buying YES costs, computed from the best resting NO
  bid: `1000 - book_no_bid_tenths` (tenths of a cent). This is *the price
  actually paid* and every bucket and every money figure in this document uses
  it, never a mid — CLAUDE.md's third measurement rule, and a bucket in the
  predecessor project showed +25.4 points and lost money for exactly this
  reason.
- **`fair_joint_conservative`.** The desk's own headline probability that a
  card's legs all happen: the worst of four devig methods per leg, combined
  through a seeded Gaussian copula that charges a small same-day correlation.
- **Clopper–Pearson interval.** An exact confidence interval for a proportion.
  Used throughout instead of `p ± 2·sqrt(p(1-p)/n)`, because the normal
  approximation needs at least 5 expected outcomes on each side and this record
  does not have them.
- **`G_eff` (Kish effective sample size).** `(Σw)² / Σw²` over per-unit weights.
  It says how many units a concentrated sample is really worth. Required beside
  every count in this repo, because `G = 311` was once 4.26 effective clusters.

---

## 2. THE POWER CHECK, WHICH COMES BEFORE EVERYTHING ELSE

### 2.1 The performance question cannot be answered here, and this is arithmetic

**Win rate.** 2 of 51 resolved. The exact 95% Clopper–Pearson interval is

```
    2/51  =  3.92%      95% CI  [0.48% , 13.46%]
```

A "safe" card, a "middle" and a "lottery" have stated joint probabilities that
plausibly span 1% to 25%. **That interval contains most of them.** The
measurement cannot distinguish a desk whose stated probabilities are right from
one that is three times too optimistic. CLAUDE.md's floor — *"require ≥5
expected outcomes on each side before a normal approximation is allowed to
speak"* — is not met and will not be met by anything in this window.

**Worse: at the population level there is no null at all.** A pooled win rate
is only testable against the probabilities the cards claimed, and those exist
for **5** of the 52 positions. For the other 47 there is no stated probability
in the record, so "did he beat expectation" has no expectation to beat. This is
the same defect §2.2 of `2026-08-29-preregistration-operator-self-assessment.md`
recorded for the operator screen, and the remedy is the same: the number is
displayed and never adjudicated.

**Return on stake.** The relevant sd is `sqrt(p(1-p))/p` dollars per dollar
staked at entry price `p`. At the mean entry price implied by the seen
aggregates (~1.5c):

| mean entry price | sd per $1 staked | 2·se at 52 units | 2·se at 10 effective units |
|---|---|---|---|
| 1.5c | 8.10 | ±225 pts | ±513 pts |
| 4c | 4.90 | ±136 pts | ±310 pts |
| 10c | 3.00 | ±83 pts | ±190 pts |
| 20c | 2.00 | ±55 pts | ±126 pts |

**The headroom this project exists to measure is 0.63 points.** The ROI
measurement is between 90× and 800× too coarse to see it, and that is before
clustering. A number will still be produced — $60.13 in, fees $3.74, some
payout out — and **it is a bank statement, not a measurement.** It is reported
as one.

### 2.2 The head-to-head cannot be answered here either

Calibration of `fair_joint_conservative` against realised 0/1 outcomes, over
the 5 positions where the desk priced the ticker Joe bought:

```
    n = 5,  p ~ 0.05    se = sqrt(0.05 * 0.95 / 5) = 9.75 percentage points
    2 se  =  +/- 19.5 points, against a quantity whose own magnitude is ~5
```

The error bar is four times the thing being estimated. To resolve a 2-point
calibration error at 95% would need **475 independent desk-priced parlays**. At
the observed accrual — 5 desk-priced-and-bought tickers in 14 days — that is
roughly **3.6 years**, against nothing that would keep the desk's pricing code
fixed for that long. **This arm is killed as an inference** (§7, Arm B) and
survives only as a five-row printed table.

### 2.3 The powered question, which is not the one asked

The record contains one binary field on 52 units that decides a claim three
shipped surfaces currently make: **`is_taker`**. At `n = 52` a proportion is
resolvable against a 50% null with an exact interval half-width of ±13.6
points, and the critical values (§8) are `k ≤ 18` and `k ≥ 34`. That is a real
test with real power, it needs no outcome, and it is blind. It is the primary.

### 2.4 The successor that would have power, named now so it is not invented later

Leg-level calibration: 52 parlays × 2–6 legs ≈ 150 leg outcomes, near
independent across games, against each leg's stored `fair_prices.p_conservative`.
To resolve a 2-point calibration error at p ≈ 0.6 needs **2,400 leg
observations** clustered by game — so even this is under-powered at present, by
a factor of ~16, but it is the only design in the family that is within an order
of magnitude. **It cannot be run from the record as it stands**: the legs of a
minted combination are not stored locally (`parlay_position_legs` has 0 rows) and
are known for at most the 31 tapped tickets. §11.4 registers a bounded read-only
probe of whether legs can be recovered at all; **the measurement itself requires
its own registration and is out of scope here.**

---

## 3. THE CLAIMS UNDER TEST, EACH STATED SO IT CAN COME BACK FALSE

**H1 (PRIMARY, verdict-bearing).** *Among the combination positions Joe entered
in the window, entry as a taker was available in a minority of cases — fewer
than half.* Direction: `p_taker < 0.5`. Two-sided test, because a result above
0.5 is at least as important as one below and a two-sided test reported
one-sided afterwards silently doubles its own false-positive rate.

This is the quantified form of a claim the repo currently states in universal
language. ADR 0085 says combinations are *"neither buyable nor sellable at a
resting price, most of the time"*; CLAUDE.md's memory line says *"combos are
unquoted — 61 of 61 with no ask"*; ADR 0012 §5 says *"enter-only"*. **Per
CLAUDE.md's instruction to distrust every universal quantifier, H1 tests the
weakest defensible version — "most of the time", i.e. >50% — and not "never".**
The universal version is refuted by a single taker fill and is not worth a test.

**H2 (descriptive, no verdict).** The recommendation funnel: of the parlay cards
pushed to Joe in the window, how many were tapped, minted, priced, and bought.
No threshold; a census.

**H3 (descriptive, no verdict).** Realised money: staked, fees, payout, net,
with the per-position table and the concentration figures beside it.

**H4 (killed as inference, printed as a table).** `fair_joint_conservative`
against the realised outcome on the ≤5 head-to-head positions.

**Explicitly NOT under test.** *"The desk's parlay recommendations are useful."*
That sentence has no operational definition that this record can bear, and §10
states what would have to exist before it could.

---

## 4. THE POPULATION, AND THE EXCLUSIONS

### 4.1 The window, closed now

```
    W_start = 1787011200000    2026-08-18T00:00:00Z
    W_end   = 1788566400000    2026-09-05T00:00:00Z   (exclusive)
```

`W_end` is midnight *this morning*, so the window is closed at the moment of
writing and cannot grow while the analysis is being written. **Rows that arrive
today are excluded even though they exist**, including any `parlay_lookups` tap
dated 2026-09-05 — which means the analysed tap count will be **smaller than
the 34 recorded in §0, and that difference is not a finding.**

### 4.2 Membership is by ENTRY time, never by settlement

**This is the exclusion rule that matters and it is the one most easily got
wrong.** Selecting positions by `settled_ms` inside the window would drop
exactly those positions still running — and whether a bet is still running is
not independent of its outcome. Membership is therefore fixed by the fill:

```sql
-- Arm A / Arm D population: one row per combination POSITION Joe entered.
CREATE TEMP VIEW census_positions AS
SELECT f.ticker              AS ticker,
       COUNT(*)              AS n_fills_observed,
       MIN(f.filled_ms)      AS first_fill_ms,
       MAX(f.filled_ms)      AS last_fill_ms,
       MAX(f.is_taker)       AS any_fill_taker,     -- see 5.3
       MIN(f.is_taker)       AS all_fills_taker,
       SUM(f.count)          AS contracts_filled,
       SUM(f.count * f.price_tenths) AS cost_tenths_from_fills,
       GROUP_CONCAT(DISTINCT f.source)         AS sources,
       SUM(f.venue_order_id IS NOT NULL)       AS n_fills_with_venue_order
FROM fills f
WHERE f.ticker LIKE 'KXMVE%'
  AND f.filled_ms >= 1787011200000
  AND f.filled_ms <  1788566400000
GROUP BY f.ticker;
```

Outcomes are attached by a **LEFT JOIN**, never an inner one:

```sql
SELECT p.*, v.market_result, v.settled_ms, v.side, v.contracts,
       v.entry_price_tenths, v.fee_cost_tenths, v.n_fills_in_position,
       v.event_ticker, v.is_taker AS settlement_is_taker,
       v.position_time_source, v.estimate_match_status
FROM census_positions p
LEFT JOIN venue_settlements v
  ON v.ticker = p.ticker
ORDER BY p.first_fill_ms;
```

A position with no settlement row is **OPEN**: excluded from every
outcome-bearing statistic, included in every exposure statistic, and **named
individually in the write-up**. It is not dropped silently.

### 4.3 Exclusions, and why each is outcome-independent

| Rule | Applies to | Why it is independent of the outcome |
|---|---|---|
| `ticker LIKE 'KXMVE%'` | scope | The product under study. A ticker prefix knows nothing about a result. |
| `filled_ms` in window | scope | A clock. |
| `is_taker IS NULL` → unmeasurable | H1 denominator only | Instrument coverage, not a result. **Resolves to unmeasurable, never to 0** (CLAUDE.md: *unreadable resolves to `None`, never `0`*). |
| Tool-placed fills flagged | H1 secondary | Provenance. Decided by `venue_order_id`, which is written at order time. |
| **No exclusion by size, price, sport, date or result** | — | There is none, and none may be added after the read. |

**No exclusion rule anywhere in this document references `market_result`,
`contracts`, or profit.** If executing the plan makes one look desirable, that
is the finding trying to select its own population; the correct response is to
report it in the write-up as a rejected temptation, as this repo has done before.

**Registered refusal precedent.** A combo experiment once pre-registered an
exclusion and the agent correctly refused to activate it when the sample turned
out thinner than assumed. The same standing permission applies here: **any rule
below may be refused at execution time if its precondition fails, and the
refusal is reported.** What may not happen is a *new* rule appearing.

---

## 5. THE UNIT OF OBSERVATION, AND THE CLUSTERING VARIABLE

### 5.1 The unit is the settled position — not the fill, not the row

**One row of `census_positions` = one unit.** Expected 52.

- **Not the fill.** 53 fills sit on 52 tickers, so one position was filled
  twice. Counting fills would make that position two observations of one bet.
  This is the same error the repo has already shipped and fixed once, when a
  gate counted 400 rows on one ticker as 400 observations.
- **Not the `venue_settlements` row per se**, although here it coincides. That
  table is keyed `UNIQUE (ticker, settled_ms)`, one row per settled *position*.
  **Precondition:** if any in-window ticker returns more than one settlement
  row, the unit becomes `(ticker, settled_ms)`, `n` changes, and the write-up
  says so before quoting any statistic.

### 5.2 How `n_fills_in_position` bears on it

It is the venue's own count of how many fills composed the position, and it is
used for exactly three things, all fixed now:

1. **A coverage check, not a weight.** Print `n_fills_in_position` against
   `n_fills_observed` from `fills`. A mismatch means our fill record is
   incomplete for that position — likely, since the fills poller started later
   than some positions — and every such position is **flagged
   `fill_record_partial`** and excluded from H1's primary denominator, because
   its taker/maker status cannot be read from an incomplete fill set.
2. **The mixed-position rule** (§5.3).
3. It is **never** an observation count and never a weight in any mean.

### 5.3 Taker status of a multi-fill position, decided now

- **Primary definition: `any_fill_taker`** — a position counts as taker if *any*
  constituent fill has `is_taker = 1`. Rationale: H1 is about whether an offer
  was ever available to hit, and one taker fill proves one was.
- **This is deliberately the definition that makes H1 harder to confirm.** The
  registered direction is `p_taker < 0.5`; the liberal rule inflates
  `p_taker`, so confirming H1 under it is conservative. Choosing the strict
  rule would have loaded the dice toward the answer the repo already believes.
- **Secondary, reported beside it: `all_fills_taker`.** If the two definitions
  land on opposite sides of the critical band, the verdict is UNRESOLVED and the
  write-up says which positions were mixed.
- **Corroboration:** `venue_settlements.is_taker` is printed for every position.
  Any disagreement with the fills-derived value is printed by ticker and the
  position is dropped from H1's primary denominator.

### 5.4 The clustering variable, and the honest admission about it

**What makes two combination positions dependent is a shared leg** — two
parlays containing the same game resolve from one final score, which is the
same reason this repo clusters by game everywhere else.

**That variable is not computable from the record.** Legs are stored for at most
the 31 tapped tickets (`parlay_lookups.selected_legs`) and for none of the other
21+. The leg-sharing graph therefore cannot be built, and **`n_eff` for any
outcome statistic is unknown, bounded above by 52 and below by 1.** This alone
forbids outcome inference and is registered as the cleanest reason the
performance question dies.

Observable proxies, all three reported, none promoted to a fix:

| Clustering | Definition | Used for |
|---|---|---|
| **C-day (primary proxy)** | UTC date of `first_fill_ms` | H1's leave-one-out check |
| **C-event** | `venue_settlements.event_ticker` | printed beside C-day |
| **C-legs (partial)** | Connected components of leg-sharing, computed **only over the subset with known legs**, with its coverage fraction printed | an upper bound on how bad C-day is |

C-day is a *proxy* and rests on an assumption stated here so it can be checked:
that leg-sharing is overwhelmingly within-day. That is likely for same-slate
parlays and **false for any futures leg**, and nothing in this measurement can
tell which. The assumption is testable only on the C-legs subset, and whatever
that subset shows does not license extending it to the rest.

---

## 6. THE CUT — BUCKET EDGES, FIXED IN ADVANCE

Buckets are on **the price actually paid**: `fills.price_tenths`, corroborated by
`venue_settlements.entry_price_tenths` (the venue's own total cost ÷ count).
**Never a mid, never `last_price`, and never `derived_yes_ask_tenths` from a
lookup taken at a different instant.**

```
    B1     1 - 20 tenths      (0.1c - 2.0c)
    B2    21 - 50 tenths      (2.1c - 5.0c)
    B3    51 - 150 tenths     (5.1c - 15.0c)
    B4   151 - 400 tenths     (15.1c - 40.0c)
    B5   401 - 999 tenths     (40.1c - 99.9c)
```

Five edges, chosen before any per-position price is known, spanning the whole
range so no position can fall outside. They are for **description only** —
counts, staked, fees per bucket. **No bucket is tested against anything**, and
no bucket may be split, merged or re-cut after the read. If a bucket is empty it
is printed empty.

Fee share is reported per bucket as `fee_cost_tenths / (contracts *
entry_price_tenths)`, because at a 1.5c entry the fee is a large fraction of the
stake and that is a fact about the product Joe can act on without any inference.

---

## 7. THE ARMS, THE STATISTICS, AND WHAT EACH ESTIMATES

### Arm A — the census (H3). DESCRIPTIVE. Expected n = 52 positions.

**Estimator: none. These are totals over a complete enumeration**, not estimates
of a population parameter, and they get no standard errors.

```
    staked_tenths  = SUM(contracts * entry_price_tenths)
    fees_tenths    = SUM(fee_cost_tenths)
    payout_tenths  = SUM(contracts * 1000) over WON positions only
    net_tenths     = payout - staked - fees
```

**Won** is defined by orientation and not assumed:
`(side='yes' AND market_result='yes') OR (side='no' AND market_result='no')`.
Do not assume every position is `side='yes'`; the §0 aggregate states it only
for the 49 losers.

**`net_tenths` is an upper bound on true net, not a point figure.** H4 —
whether Kalshi charges a settlement fee — is unresolved (ADR 0027), and
`fee_cost_tenths` is consistent both with there being no settlement charge and
with the field being entry-only. Any omitted settlement fee subtracts. The
write-up says "at most" and never "he lost exactly".

Also reported: count by `market_result`; count by `position_time_source`; count
by `estimate_match_status`; the per-bucket table from §6; and the per-position
table in full — 52 rows is small enough to print, and a pooled money figure is
not a finding until the parts are visible.

### Arm B — head-to-head (H4). KILLED AS INFERENCE. Expected n ≤ 5.

Join `parlay_lookups.minted_market_ticker = census_positions.ticker`, taking the
**earliest** lookup per ticker (fixed now; "earliest" is a clock rule, not a
choice about which price flatters the desk). Print, per row: ticker, tap time,
first fill time, `card_key`, `stake_cents`, `fair_joint_conservative`,
`derived_yes_ask_tenths`, `book_depth`, `collection_unverified`, the price
actually paid, `market_result`.

**No mean, no bias estimate, no Brier score, no calibration verdict, no
p-value.** §2.2 is why. If the table shows something striking, that observation
becomes a hypothesis for a successor registration and **is written up as a
hypothesis, in those words.**

One derived figure is permitted because it is a price comparison rather than an
outcome comparison, and it has no `n` problem: `price_paid_tenths −
derived_yes_ask_tenths` per row, printed per row, **never averaged**. It says
whether the desk's quoted ask was the price Joe got, which is a statement about
the instrument.

### Arm C — buyability of what the desk priced (H2 part 1). CENSUS.

Three denominators, all printed, primary named:

```
    C1  all in-window parlay_lookups rows                              (taps)
    C2  ... AND minted_market_ticker IS NOT NULL                       (mints)
    C3  COUNT(DISTINCT minted_market_ticker) over C2       <-- PRIMARY (cards)
```

C3 is primary because a repeat tap on the same card is not a second observation
of the market's liquidity — the same reason §5.1 rejects the fill as a unit.

```sql
SELECT status, COUNT(*) AS taps, COUNT(DISTINCT minted_market_ticker) AS cards
FROM parlay_lookups
WHERE requested_ms >= 1787011200000 AND requested_ms < 1788566400000
GROUP BY status;
```

Reported: the status split on all three denominators; the split by `card_key`
(safe / middle / lottery) as **counts only**; `collection_unverified` rate;
`book_depth` and `derived_yes_ask_tenths` distributions on the `priced` rows;
the `error` rows' `error` text listed verbatim.

**No test.** The pooled tap-level split was seen (§0), so C1 and C2 are
transcriptions; C3 is a re-weighting of a seen quantity and is close enough to
seen that it is treated the same way. **The `card_key` breakdown is blind but is
still not tested** — three cells over ~31 taps clustered by day cannot resolve
anything, and testing it would be the multiplicity this repo has already been
burned by.

**One registered code-reading check, C4, which needs no data.** `parlay_lookups`
records 7 `priced` rows — a resting NO bid existed, hence a derived YES ask —
while `docs/measurements/2026-08-30-combination-liquidity-census.md` reports
**0 of 61 quoted**. Either these read different fields or one of them is wrong.
Resolve it by reading `backend/parlays.py`, `backend/combo_bids.py` and
`scripts/`'s census source **before** interpreting either number, and state the
answer in the write-up. If they measure the same thing, that discrepancy is a
finding in its own right and outranks everything else in Arm C.

### Arm D — taker or maker (H1). PRIMARY. VERDICT-BEARING. Expected n = 52.

**Estimator: a single proportion** over independent-ish units —
`p_taker = k / n`, where `k` = positions with `any_fill_taker = 1` and `n` =
positions with readable taker status. The null is `p = 0.5`, from ADR 0085's own
words *"most of the time"*. Interval: **exact Clopper–Pearson**, because
`sqrt(p(1-p)/n)` is only correct for a proportion of independent draws and §5.4
says these are not fully independent — so the exact interval is used and then
stress-tested by leave-one-day-out rather than pretended to be robust.

Also printed, no tests attached: `source` split (`engine` / `venue_hand`), the
`venue_order_id` non-null count, the tool-placed subset separated out (a
tool-placed *resting bid* that filled proves a counterparty arrived, **not** that
an offer was available, and must not be read as evidence for either side of H1),
and the taker rate by C-day.

### Arm E — the recommendation funnel (H2 part 2). CENSUS.

The "recommendations I have been receiving" are the pushed parlay cards:

```sql
SELECT COUNT(*) FROM notifications
WHERE kind IN ('parlay_card', 'parlay_daily')
  AND sent_ms >= 1787011200000 AND sent_ms < 1788566400000;
```

split by `delivered` and `suppressed` — a claim that was never sent is not a
recommendation received (ADR 0080), and the three states must not be merged.

The funnel, each stage a count:

```
    pushed & delivered  ->  tapped  ->  minted  ->  priced  ->  bought  ->  won
```

**The matching rule between a push and a tap, fixed now.**
`notifications.key` for a parlay card is `<card_key>:<ticker>|<ticker>|...` with
tickers **sorted** (`backend/notify/alerts.py::parlay_key`). Normalise a
`parlay_lookups` row to the sorted tuple of `market_ticker` from
`selected_legs`. **Match = exact set equality of leg tickers.** Report both the
card_key-agnostic match and the card_key-inclusive match. **Subset matching,
fuzzy matching and same-game-different-line matching are forbidden** — each is
a researcher degree of freedom that can only enlarge the overlap.

Reported: how many delivered recommendations Joe acted on; how many of his 52
parlays trace to a recommendation; and — the number that answers his question
most directly — **how many did not.**

---

## 8. THE DECISION RULE, VERBATIM

> **There is exactly one verdict-bearing test in this measurement: H1, Arm D.**
> Everything else in this document is descriptive and may never be promoted to
> a verdict, at any later date, by anyone, without a new registration.
>
> Let `n` be the number of in-window combination positions with readable taker
> status (both a complete fill record and no fills/settlement disagreement), and
> `k` the number with `any_fill_taker = 1`. The test is two-sided against
> `p = 0.5` at `alpha = 0.05`, exact (Clopper–Pearson). **No multiplicity
> correction is applied and none is needed, because one test is being run.**
>
> At the expected `n = 52` the critical values are fixed here:
>
> * **`k <= 18`** — the interval lies entirely below 0.5.
>   **VERDICT: ADR 0085 UPHELD.** Taker entry into combinations was available
>   in a minority of Joe's positions. The desk's "you probably cannot buy this"
>   copy is true and stays.
> * **`k >= 34`** — the interval lies entirely above 0.5.
>   **VERDICT: ADR 0085 REFUTED ON THIS POPULATION.** Taker entry was the
>   majority case. Three shipped surfaces are telling Joe something false and
>   ADR 0085's demotion of the buy path rests on a premise contradicted by 52
>   of his own bets.
> * **`19 <= k <= 33`** — **VERDICT: UNRESOLVED.** Neither claim is made.
>
> If `n` differs from 52, the critical values are recomputed from the exact
> interval **by the committed instrument**, not by hand, and the recomputation
> is printed.
>
> **Three downgrades, applied in this order, each of which can only weaken the
> verdict:**
>
> 1. **Coverage.** If more than 20% of positions have unreadable taker status,
>    **the arm is REFUSED** and no verdict is issued. Unreadable resolves to
>    unmeasurable, never to maker.
> 2. **Concentration.** Compute `G_eff` over C-day clusters weighted by
>    position count. If the largest single C-day cluster holds **>= 25%** of
>    positions, or `G_eff < 10`, the verdict is suffixed
>    **UNRESOLVED - CONCENTRATION** unless it survives downgrade 3.
> 3. **Leave-one-day-out.** Refit dropping each C-day cluster in turn. If any
>    single drop moves `k/n` across either critical boundary, the verdict is
>    **UNRESOLVED - CONCENTRATION** regardless of the pooled result.
>
> **Rule 1 of this repo applies to the result whichever way it lands.** If
> `k >= 34`, that is a large apparent contradiction of a measured belief, and it
> is treated as a **bug until proven otherwise**: before the refutation is
> written up, the instrument must rule out that `is_taker` is mis-populated for
> combination fills, that the ADR 0084 buy path stamps its own fills taker, and
> that the venue reports combination fills differently from single-market fills.
> A refutation that survives those three checks is a refutation; one that does
> not is a defect report.
>
> **The money arms declare nothing.** No verdict of any kind — positive,
> negative, "profitable", "unprofitable", "the cards work", "the cards do not
> work" — may be issued from Arm A, Arm B, or Arm C.

### 8.1 Looks, counted

**One look, on one snapshot, at a closed window.** This measurement is not a
monitor and no threshold above may be re-evaluated as the record grows. This
repo has measured what repeated looks at an accumulating database do to a fixed
threshold — a 13.7% crossing rate under a true zero, and that was a floor. If a
second look is ever wanted, it needs an amendment to this file with an
always-valid boundary, written before the second read.

---

## 9. THE STOPPING RULE

- **Data collection has already stopped**, by §4.1: `W_end` is fixed at
  2026-09-05T00:00:00Z, in the past at the time of writing.
- **One extraction**, taken at the first execution after this file is committed,
  written to `docs/measurements/data/2026-09-05-parlay-census.json`, and every
  figure in the write-up traced to that file. If the extraction is re-run, the
  new file is dated separately and both are kept.
- **No "wait for more parlays".** Joe will keep betting; those bets belong to a
  successor registration, not to this one. Extending the window because the
  answer looked unresolved is the specific move this document exists to prevent.
- **`n` is what it is.** The measurement does not stop early on a good-looking
  interim and does not continue on a bad-looking one, because it takes one look.

---

## 10. WHAT IS BUILT, WHAT IS KILLED, AND WHERE THE NEGATIVE GOES

**The write-up has a destination now, before the number exists:**
`docs/measurements/2026-09-05-parlay-census-result.md`. **It is written and
committed whichever way every arm lands**, including the case where Arm D is
REFUSED for coverage and there is no verdict at all. A negative branch without a
destination produces a negative result that quietly never gets written.

| Outcome | What is built | What is killed |
|---|---|---|
| **H1 upheld (`k <= 18`)** | Nothing new. ADR 0085 stands, the parlay desk's job stays *pricing for a bet placed elsewhere*, and the improvement that follows is **recording the sportsbook bet** — `parlay_positions` has 0 rows, so ADR 0078's watcher has never had an input. That becomes the parlay lane's next item. | Any proposal to re-promote the Kalshi buy path on liquidity grounds. |
| **H1 refuted (`k >= 34`)**, surviving the three Rule-1 checks | An ADR re-opening ADR 0085's liquidity premise. The card copy and ADR 0085 are corrected **in the same commit** — CLAUDE.md's ordering lesson: copy that names a condition is falsified by fixing the condition, so the fix and the copy ship together or the screen lies in the interval. | The sentence "combinations are unquoted" in CLAUDE.md, ADR 0012 §5, ADR 0085 and the memory file — all four, or none. |
| **H1 unresolved / refused** | Nothing. | Nothing. The write-up records `n`, `k`, `G_eff` and the coverage fraction so a successor knows exactly what it inherits. |
| **Any Arm A / B / C outcome** | Nothing is built and nothing is killed on them. | — |

**And the plan finding, stated because it is cheaper to learn now.** Arms A, B
and C are **not decision-relevant**: no branch of any of them changes what gets
built. They are reported because Joe asked for a census of his own bets and is
entitled to one, and because a bank statement is a legitimate product. **Only
Arm D can change a decision, and Arm E can change a priority.** If the parlay
lane were being ranked purely on decision value, Arms A–C would not be run.

**"Improve the parlay recommendations" is not funded by this measurement in
either direction.** The record cannot say which cards were good. What it can
say is whether the desk was *present* for the bets at all (Arm E), and the
answer to that is already 5 of 52 from §0.

---

## 11. INSTRUMENTS

### 11.1 One new subcommand, committed before the pull

`scripts/inspect_live_db.py`, new `_q_parlay_census(conn, args)` following the
existing `_q_*` pattern, reusing `_binom_two_sided`. **It is committed before
the database is read**, so the queries cannot be adjusted after a first glance.
Sections it emits, in this order and no other: population and coverage → Arm D
(primary) → Arm E → Arm C → Arm A → Arm B. **Arm D prints first so that no
money figure is on screen when the verdict-bearing cell is read.**

### 11.2 The module docstring, drafted now

Every harness in this repo states what it does not establish, and drafting it
afterwards selects caveats that are survivable. The docstring must carry §12
verbatim.

### 11.3 What may not be touched

- `recommendations`, `beta`, `analysis/signal_test.py`, `gate.py` — not read,
  not written, not joined to.
- No outward-facing write. **`lookup_combo` mints a market and must not be
  called by this measurement at all**, for any ticker, for any reason.

### 11.4 The bounded probe for the successor, and its ceiling

To learn whether §2.4's leg-level design is even possible: a **read-only
`GET /markets/{ticker}`** on **at most 3** in-window combination tickers, whose
only recorded output is the boolean *"does the payload name its legs?"* plus the
key names present. **No outcome field from those payloads is read, recorded or
looked at.** If more than 3 tickers are wanted, that is the successor's
registration, not this one.

---

## 12. WHAT THIS MEASUREMENT CANNOT ESTABLISH

Drafted before the run, and the list is meant to include the items that would
overturn the result rather than only the survivable ones.

1. **Whether Joe's parlay betting is profitable, in either direction.** 2 of 51
   resolved winners; the exact interval is [0.48%, 13.46%]; the ROI error bar is
   90×–800× the 0.63-point headroom. The money figures are a bank statement.
2. **Whether the desk's stated probabilities are calibrated.** `n = 5`, error
   bar ±19.5 points against a quantity of magnitude ~5.
3. **Whether the desk's recommendations are good, useful, or better than
   nothing.** No control, no counterfactual, no comparison population, and 47 of
   52 positions have no desk price recorded at all.
4. **Anything causal about the desk and Joe's behaviour.** The nearest evidence
   is `2026-09-04-presence-at-the-moment-of-a-bet-result.md`, whose own verdict
   is UNRESOLVED — CONCENTRATION.
5. **Anything about sportsbook parlays.** They are invisible to `fills`;
   `parlay_positions` has 0 rows. If most of Joe's parlay activity is at a
   sportsbook, this census is a minority of his behaviour and cannot detect that
   it is.
6. **`n_eff` for any outcome statistic.** The leg-sharing graph cannot be built
   (§5.4). C-day is a proxy resting on an assumption that is false for futures
   legs, and nothing here can say how often that bites.
7. **That combination liquidity is stable.** The product is new and changed
   exchange shards inside this window. **Even a clean H1 verdict is a statement
   about 2026-08-18 to 2026-09-04 and about the collections Joe happened to
   choose** — a self-selected sample of markets, not a random one. This is the
   caveat most likely to overturn a refutation and it is stated first among the
   generalisation limits, on purpose.
8. **Whether Joe could have bought at the observed taker prices in size.** One
   fill proves one counterparty. Depth is a different question and `book_depth`
   exists only on the priced lookups.
9. **The true net after settlement fees.** H4 is unresolved; `net_tenths` is an
   upper bound (ADR 0027).
10. **Whether the copula's correlation charge is right.** Unmeasured (ADR 0012
    §5) and untouched here.
11. **Anything about `market_result = ''`.** One position, 4.34 contracts, and
    §13 handles it by bracketing rather than by deciding what the venue meant.
12. **Anything about the engine, the gate, or edge.** ADR 0038 is not reopened
    by this document and no sentence in the result file may suggest it is.

---

## 13. THE UNRESOLVED ROW, DECIDED NOW

One `venue_settlements` row carries `market_result = ''` on 4.34 contracts.
**Decided here, before its identity is known:**

- It is **UNRESOLVED**, not a loss and not a win. `''` is neither `'yes'` nor
  `'no'` and substituting either would be inventing an outcome.
- **Excluded** from: the win/loss denominator (which is therefore 51 if the
  other counts hold), `payout_tenths`, and Arm B if it appears there.
- **Included** in: `staked_tenths`, `fees_tenths`, the §6 buckets, all
  concentration figures, and Arm D's denominator — none of which need an
  outcome.
- **Named individually** in the write-up with its ticker, `event_ticker`,
  `settled_ms` and `position_time_source`.
- **Net P&L is reported as a bracket**, not a point:
  `[net assuming the stake is lost, net assuming the stake is returned]`. The
  spread is at most ~$0.07 at typical prices, so the bracket costs nothing and
  removes a choice.
- **No investigation of what `''` means may change its handling.** If the venue
  turns out to mean "void", the bracket already covers it; if it means
  "not yet settled", the bracket already covers it. The handling is fixed
  either way, which is the point of fixing it now.

---

## 14. CORRECTIONS MADE TO THE PROPOSED DESIGN, RECORDED BECAUSE THE SHAPES RECUR

1. **The population was proposed as "the 52 settled combination positions".**
   Selecting on settlement makes membership depend on whether a bet is still
   running, which is not independent of the outcome. Changed to selection by
   fill time with a LEFT JOIN to outcomes (§4.2).
2. **The census was proposed as an arm with findings.** Its headline statistics
   are deterministic functions of aggregates already read (§0), so it is a
   transcription. Demoted to descriptive with no thresholds.
3. **The `book_empty` arm was proposed as possibly "the most actionable
   finding".** Its pooled proportion was seen before registration, so it cannot
   be a test. It became a census plus **C4**, a code-reading check against the
   61-of-61 census, which is where the actual open question turned out to be.
4. **No arm in the original proposal was both blind and powered.** Arm D was
   added for that reason, and it is the only verdict in the document.
5. **"Performance against the recommendations" was one question.** It is at
   least four, with `n` of 52, 5, ~31 and (for legs) 0. Separating them is what
   made the power arithmetic possible at all.

---

## Provenance

- Written 2026-09-05, before any per-row read. §0 lists every aggregate seen.
- Author: the pre-registrar agent, at Joe's approval of the measurement.
- Governing documents: CLAUDE.md (three rules, measurement rules, conventions),
  ADR 0038 (the hunt is closed), ADR 0071 (what the desk is for), ADR 0078,
  ADR 0084, ADR 0085 (the claim H1 tests), ADR 0027 (H4, the fee bound),
  ADR 0012 §5.
- **This file is committed before the extraction runs.** A pre-registration that
  is written after the pull is a description of a decision already made.

---

## AMENDMENT 1 — 2026-09-05, the instrument moves out of the inspector

**Written blind.** No per-row data has been read by the author of this
amendment or by the coordinator who requested it, before or during its writing.
§0's list of seen aggregates is unchanged and nothing has been added to it. No
outcome, no taker count, no statistic has been observed.

**Scope: where the instrument lives, and nothing else.** Joe approved this route
explicitly, choosing it over splitting `scripts/inspect_live_db.py` first.

### A1. What does not change, stated first so it can be checked

**Nothing about the population, the unit, the clustering, the buckets, the
statistic, the decision rule, the downgrades or the stopping rule moves.**
§§1–10, §12 and §13 stand exactly as registered. In particular, H1's critical
values are unchanged and are restated here verbatim so that a reader of this
amendment alone cannot be told a different number later:

> * **`k <= 18`** — VERDICT: ADR 0085 UPHELD.
> * **`k >= 34`** — VERDICT: ADR 0085 REFUTED ON THIS POPULATION.
> * **`19 <= k <= 33`** — VERDICT: UNRESOLVED.
>
> at the expected `n = 52`, two-sided against `p = 0.5` at `alpha = 0.05`,
> exact (Clopper–Pearson), with the three downgrades of §8 applied in order.

Moving the instrument cannot touch any of these, and the reason is structural
rather than a promise: the decision rule is stated entirely over `n`, `k`, a
coverage fraction, `G_eff` and a leave-one-day-out refit. **Not one of those
quantities is a function of which file the code sits in.** §9's one-look rule
and §4.1's closed window are likewise untouched — the window is closed in the
past, so no instrument can enlarge it.

### A2. Why the inspector cannot take it — arithmetic, not preference

```
    scripts/inspect_live_db.py           260,285 bytes
    READ_TOOL_LIMIT_BYTES                262,144
    headroom                               1,859

    smallest comparable subcommand:
      _q_parlay_lookups_tail               2,603
      _q_study_stop                       12,801
      _q_visit_freshness                  21,505
```

Even the smallest comparable subcommand is 1.4× the space available.
`tests/test_session_files_are_readable.py` covers **every tracked file** with a
source suffix, enumerated via `git ls-files`, and its own docstring records that
**"There is no exemption list any more, deliberately: one existed for exactly
one file, and re-adding one is a decision, not an edit."** So the option of
carving out an exemption is closed by a prior decision, and a domain split of
the inspector is separate work with its own brief.

**This is recorded here rather than in a commit message because it is the kind
of constraint that gets re-derived.** A future session proposing a new
`_q_*` subcommand should read this paragraph and check the byte count first.

### A3. The replacement instrument

**`scripts/measure_parlay_census.py`** — a standalone analyzer, laptop-side,
replacing the `_q_parlay_census` subcommand named in §11.1. It carries forward
every rule §11 imposed:

- **Arm D's verdict-bearing cell prints first**, before any money figure reaches
  the screen. §11.1's ordering was never about the inspector; it is about what
  is on screen when the deciding number is read.
- **`lookup_combo` is never called**, for any ticker, for any reason. §11.3.
- **Read-only. One look.** The extraction is written to
  `docs/measurements/data/2026-09-05-parlay-census.json`, as §9 already fixed.
- **Committed before the pull**, so the analyzer exists in git ahead of the
  data. Precedent: the presence measurement's analyzer at `d2f51de`
  (01:13:01Z) against its first capture at 01:13:20Z.

### A4. THE CORRECTION — the capture cannot come from existing subcommands

**This is the part of the coordinator's proposal that does not survive contact
with the code, and it matters because of what silently drops if it is missed.**

The presence measurement's analyzer ran against four `inspect_live_db.py
--json` captures and "never opens the live database". Applying that pattern
here fails: the nearest existing capture, `h4-balance-spans`, emits

```
    fills:               id, ticker, filled_ms, count, price_tenths,
                         is_taker, fee_actual, source
    venue_settlements:   id, ticker, side, contracts, entry_price_tenths,
                         fee_cost_tenths, market_result, settled_ms
```

and **five columns this registration already depends on are absent**. Each one
gates a specific registered rule:

| Missing column | The registered rule it gates |
|---|---|
| `fills.venue_order_id` | §4.3 and §7 Arm D — the tool-placed flag |
| `venue_settlements.is_taker` | §5.3 corroboration, and the drop-on-disagreement rule |
| `venue_settlements.n_fills_in_position` | §5.2 — `fill_record_partial`, which **gates H1's primary denominator** |
| `venue_settlements.event_ticker` | §5.4 — C-event clustering |
| `position_time_source`, `estimate_match_status` | §7 Arm A prints |

**The hazard, named so it cannot happen quietly.** Executing against the
existing captures would have made those five checks unrunnable, and the
path of least resistance at execution time is to skip them. Three of them —
the coverage gate, the fills/settlement disagreement drop, and C-event —
are precisely the guards protecting H1's denominator and its downgrades. **An
instrument move that removes them is not an instrument move; it is a change to
the decision rule wearing an instrument's clothes**, and it is forbidden by A1.

**Registered rule:** if any of the five columns cannot be read at execution
time, the analyzer **names the column and applies §8's refusal or downgrade**.
It never silently omits a check, and it never substitutes a default —
CLAUDE.md's *unreadable resolves to `None`, never `0`*.

### A5. Where the data comes from instead

**`scripts/measure_parlay_census.py` opens a pulled, read-only copy of the live
database directly, with stdlib `sqlite3`, and owns its own SELECTs.** Those
SELECTs are not invented at execution time: §4.2 and §7 already fix them
verbatim, so the analyzer **transcribes** them.

- **Pull route:** `flyctl ssh sftp get`, the route ADR 0097 already used to
  preserve a baseline out of the repo. **No new box-side code, nothing added to
  the `.dockerignore` allowlist, and no query executed on the live box.**
- **It does not compete for the write lock.** Running SQL on the box would
  contend with the loop's writer — this repo has an ADR (0091) and two
  measurements about exactly that. A file copy read on a laptop cannot.
- **Opened `file:<path>?mode=ro`.** Not `immutable=1`: an immutable open ignores
  WAL state and would silently read a stale page set. The `-wal` and `-shm`
  files are pulled alongside the `.db` if present, and **the result file records
  which files were pulled**, because "we pulled the db" and "we pulled the db
  and its WAL" are different reads and only one of them is current.

**The torn-snapshot precondition, which is a refusal.** Before any statistic is
computed, the analyzer prints its own row counts, inside the closed window
`[W_start, W_end)`, for `fills` (KXMVE), `venue_settlements`, `parlay_lookups`
and `notifications`. These are compared against counts read on the box at
capture time through **existing** subcommands (`h4-balance-spans`,
`parlay-lookups-tail`, `notifications`). **The window is closed in the past and
therefore cannot grow, so the counts must match exactly.** Any mismatch means
the copy is torn or stale: **the measurement is REFUSED, no verdict is issued,
and the refusal is written to the result file.** A refusal is a record
(ADR 0083).

**The pull is the look.** §8.1's one-look rule attaches to it. Re-pulling
requires an amendment written before the second pull, not after the first
result is seen.

### A6. Does a standalone file weaken anything the registration relied on?

**No, and the coordinator's specific worry does not apply.** §11.1 chose the
inspector for two reasons — the house `_q_*` pattern, and the commit ordering —
and **neither is specific to that file**. The registration never relied on the
inspector importing nothing from `backend`.

**That property is real but exists for a different reason.**
`scripts/inspect_live_db.py` is stdlib-only because it runs **on the live box**,
under the `.dockerignore` allowlist and Joe's ruling that only a committed,
reviewed script may be run by path. This analyzer runs on a laptop against a
pulled copy, so that reason does not transfer. And the repo plainly permits the
alternative: `scripts/analyze_prop_onesided.py` imports
`backend.core.devig`, `backend.kalshi.props` and `backend.runner`.

**Stdlib-only is nonetheless REQUIRED here, and the reason is upgraded rather
than inherited.** §11.3 forbids any outward-facing write and says `lookup_combo`
"must not be called by this measurement at all, for any ticker, for any
reason". Importing nothing from `backend` makes that **structurally true instead
of promised**: `lookup_combo` is not reachable, no `httpx` client is
constructed, no write path to the live database or to Kalshi exists in the
process. This is the same argument ADR 0078 makes for `core/hedge.py`, where the
absence of an Anthropic client and of an `api_credits` write is asserted over
the source rather than trusted.

**It costs nothing.** Nothing in §6 or §7 needs a fee model, a devig, or
`core/prices`: payout is `contracts * 1000`, fees are the venue's own
`fee_cost_tenths`, and the buckets are on `price_tenths` as stored. If a future
step genuinely needs `backend`, that is an amendment, and the amendment must
say what it needs and why the structural guarantee is worth giving up.

**Registered as checkable:** the module's import block contains no `backend`
import, and the result file states that it was checked.

### A7. `.dockerignore` — not needed, and the exact rule

**The coordinator is right: no allowlist entry.** The script is laptop-side and
is never invoked on the box.

**But the rule that decides this is self-reference, not intent**, and it is a
trap worth writing down. `TestTheSshInvokedScriptsSurviveDockerignore` derives
the allowlist from each script's **own docstring naming its own absolute path**:
a docstring containing `/app/scripts/measure_parlay_census.py` would make the
test demand an allowlist entry. `.dockerignore`'s own comment records that
`run_signal_test.py`, `analyze_prop_onesided.py` and
`read_window_gate_observations.py` all contain `/app/scripts/` while naming
*`inspect_live_db.py`'s* path, and are correctly laptop-side.

So: **the new script's docstring must not self-reference an `/app/scripts/`
path.** It may name `/app/scripts/inspect_live_db.py` when documenting A5's
count cross-check, exactly as those three do.

### A8. Tool-placed positions — an ambiguity resolved now, blind

**The original left this open and it must not be decided after the count is
visible.** §4.3's table flags tool-placed fills as "H1 secondary", while §7's
Arm D says a tool-placed resting bid "must not be read as evidence for either
side of H1". Those two sentences can be read as "reported separately" or as
"excluded from the denominator", and the choice moves `k/n`.

**Resolved: tool-placed positions stay in H1's primary denominator**, counted by
`any_fill_taker` like every other position, and are additionally reported as a
separate subset. Reasons, both stated before the count is known:

1. A position Joe entered through the desk is still a combination position Joe
   entered. §4.2's membership rule is about entry, and it does not have an
   exception.
2. **Excluding them would bias toward refuting ADR 0085.** A tool-placed order
   *rests* (ADR 0084), so it is systematically maker; dropping the maker-heavy
   subset can only raise `p_taker`. An exclusion whose mechanism correlates with
   the outcome variable is the thing §4.3 exists to prevent, and it would cut
   toward the more interesting result.

**And the sentence in §7 is made operative rather than discarded:** a
**mandatory secondary fit excluding tool-placed positions is printed beside the
primary, and if the two land on opposite sides of either critical boundary the
verdict is UNRESOLVED.** So the tool-placed subset cannot by itself decide H1 —
which is what "must not be read as evidence for either side" was reaching for —
without an exclusion rule doing it silently. This mirrors §5.3's handling of the
two taker definitions.

**The join for the flag:** `fills.venue_order_id` against the tool's own record
of orders it placed, which for combinations is `combo_orders.kalshi_order_id`
(`combo_orders` also carries `dry_run`, and a `dry_run` order that has a venue
id would itself be a defect worth naming). This implements the flag §4.3
already registered; it does not add a new one.

### A9. §11.1 as amended — replacement text

> **11.1 One standalone analyzer, committed before the pull.**
> `scripts/measure_parlay_census.py`, laptop-side, stdlib-only (A6), reading a
> pulled read-only copy of the live database (A5). **It is committed before the
> copy is pulled**, so the queries cannot be adjusted after a first glance.
> Sections it emits, in this order and no other: integrity preconditions and
> coverage (A5, A4) → Arm D (primary) → Arm E → Arm C → Arm A → Arm B.
> **Arm D prints first so that no money figure is on screen when the
> verdict-bearing cell is read.** Its docstring carries §12 verbatim and does
> not self-reference an `/app/scripts/` path (A7).

The `_q_parlay_census` subcommand named in the original §11.1 **is withdrawn and
must not be written**, in this measurement or a successor, until
`scripts/inspect_live_db.py` has been split.

### A10. Ordering of this amendment's own commits

1. This amendment, committed first.
2. `scripts/measure_parlay_census.py`, committed second, before any pull.
3. The pull, then the single run, then
   `docs/measurements/2026-09-05-parlay-census-result.md`.

If the pull happens before step 2, the measurement is not pre-registered in its
instrument, and **the first line of the result file must say so.**

### A11. What Amendment 1 does not establish

- It does not make the census powered. §2 stands: Arm B is dead at `n = 5`, the
  money arms are transcriptions, and Arm D remains the only verdict.
- It does not verify that the pull route works. If `flyctl ssh sftp get` cannot
  produce a copy that passes A5's count check, the measurement is refused and
  a different capture design needs its own amendment — written before the data
  is seen, like this one.
- It does not resolve C4 (§7 Arm C), which is still a code-reading question.
- It does not license reading the live database from the analyzer. The analyzer
  opens a **copy**; that distinction is the whole of A5.
