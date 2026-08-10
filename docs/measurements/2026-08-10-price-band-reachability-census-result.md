# Result — the price-band reachability census, and its audit

**Run 2026-08-10 against the live `/data/cockpit.db`. Read-only throughout: the
connection is `file:...?mode=ro`, no network call, no order, no deploy, no
money.**

- Census harnesses: `scripts/census_band_reachability{,_pair,_detail,_atp,_allseries}.py`,
  committed with this document.
- Audit: a `measurement-skeptic` lane exported the raw slice and recomputed
  **off-machine with its own code**, without reading the census scripts for
  their numbers. Verdict **SURVIVES WITH QUALIFICATION**.
- Every number below was re-checked for this write-up against the saved run
  output and by re-executing the audit passes. Where the two lanes disagree,
  **both figures are printed with their cut** rather than one being chosen.
- This document carries **both** the census and the audit, because the audit
  reproduced the headlines by an independent route and that is part of the
  evidence — not a footnote to it.

> # VERDICT
>
> **1. `KXMLBGAME` cannot fill a sub-20c pre-game band.** 85 events, six slates,
> **zero** pre-game observations below 20c; cheapest ever **26.0c**. This is a
> wall, and two independent price sources put it in the same place.
>
> **2. `KXMLBSPREAD` reaches both registered bands, simultaneously, at every
> polling instant in the record**, on alternate run lines at strike 3.5 and 2.5.
>
> **3. And the second finding is AVAILABILITY, not fillability.** Every
> observation in it is a quote record. Two explanations fit all of them equally:
> real resting liquidity, or a maker showing 2,914 contracts at 13c who pulls on
> any incoming order. **No quote record can separate them.** The separating
> observation is one small order, and it has not been placed.

---

## THE `n` QUALIFICATION — read this before any figure below

**696 polling instants is uptime, not evidence.** The number is large because
the poller ran, not because the world was sampled 696 times.

```
polling instants                                696   <- NOT the sample size
polling SESSIONS (instants > 5 min apart)       261
share of the 696 from ONE observation day        64%  (447 of 696, 2026-08-09)
```

**The honest independent units:**

| unit | n |
|---|---:|
| game-days | **4** |
| events | **55** |
| pre-game markets | **330** |
| markets that ever supplied a low ask | **45** |
| maximal low-band episodes | **56** |
| events that ever printed below 10c | **3** |
| markets that ever printed below 10c | **3** |

**Concentration is good, and that is the half of this that is reassuring.**
Largest single market is **8.1%** of low rows, largest event **9.2%**, and all
four slates contribute (148 / 1,717 / 2,129 / 1,036 low rows). No slate carries
the finding alone.

**The deep tail is thin, and that is the half that is not.** Only 3 markets and
3 events ever printed below 10c — 307 rows in total, of which the 7c corner is
**22 rows from a single market**. Nothing below 10c should be treated as a
population.

**And nearly half the low band sits on the band's own edge.** 45.8% of low rows
are at 14c or 15c. The `≤13c` region — the part that matters for a `C = 20`
stake under $2.70 — is 54.2% of low rows over **26 markets / 24 events**.

---

## §1. Population and method

| | |
|---|---|
| source | live `/data/cockpit.db`, `kalshi_quotes` ⋈ `kalshi_markets` ⋈ `kalshi_events` |
| quote rows | **1,031,989** |
| series / events / markets | **11 / 361 / 3,146** |
| window | 2026-08-07T19:33Z → 2026-08-10T17:00Z |
| ask | derived: `1000 - no_bid_tenths`, tenths of a cent |
| unreadable ask | `no_bid_tenths IS NULL` → `None`, **never 0** (0 dropped; there were none) |
| pre-game boundary | `observed_ms < commence_ms - 3h` |

**The 3h subtraction is not a cushion.** `kalshi_events.commence_ms` is Kalshi's
`occurrence_datetime`, which runs exactly three hours late (ADR 0006 §1; see
also the comment at `backend/gate.py:899`). Subtracting 3h recovers the true
scheduled start, so "pre-game" means "before first pitch", with no margin.

The derived-ask convention is the schema's, not this harness's:
`backend/store/schema.sql:142` — *"yes_ask and no_ask are DERIVED at read time
as 1000 - the opposing bid"*.

### The 11 stored series — this is the true scope, and it is narrower than some documents assume

| series | quote rows | markets | events |
|---|---:|---:|---:|
| KXNFLSPREAD | 281,184 | 404 | 16 |
| KXNFLTOTAL | 211,584 | 304 | 16 |
| KXMLBTEAMTOTAL | 157,178 | 770 | 55 |
| KXMLBTOTAL | 124,715 | 644 | 55 |
| KXMLBSPREAD | 70,948 | 437 | 55 |
| KXMLBGAME | 56,230 | 170 | 85 |
| KXWNBASPREAD | 40,045 | 173 | 15 |
| KXWNBATOTAL | 35,321 | 146 | 15 |
| KXNFLGAME | 22,272 | 32 | 16 |
| KXNCAAFGAME | 20,880 | 30 | 15 |
| KXWNBAGAME | 11,632 | 36 | 18 |
| **TOTAL** | **1,031,989** | | |

**`KXATPDOUBLES` has 0 rows** in `kalshi_quotes`, `kalshi_events`,
`kalshi_markets` and `recommendations` (0 of 361 events, 0 of 3,146 markets, 0
of 1,692 recommendations). It is absent from `kalshi_series` entirely. Any ATP
work needs a **live board read** first; the prices are not on disk.

> **One arm of that check was vacuous and is recorded as such.** The same script
> also reports 0 `KXATP%` rows in `orders`, `fills` and `settlements` — but
> those tables hold **0 rows in total**, so the check could not have returned
> anything else. It is consistent with, and explained by, the fee-calibration
> result's §S11: the round-one ATP fills live at Kalshi and never enter the
> local `fills` table.

### The two cuts, stated once

The census ran to a **17:00Z** cut; the audit pulled its slice later and pinned
to **16:58Z**. Every difference between the two lanes' headline numbers is this
two-minute gap, and it was checked directly:

```
cut 16:58Z -> pre-game obs 52,470   instants 695   min ask 7.0c
cut 17:00Z -> pre-game obs 52,530   instants 696   min ask 7.0c
cut 17:05Z -> pre-game obs 52,530   instants 696   min ask 7.0c
cut 17:14Z -> pre-game obs 52,590   instants 697   min ask 7.0c
```

No conclusion moves. Below, census figures are the 17:00Z cut and audit figures
the 16:58Z cut, labelled where they differ.

---

## §2. Headline 1 — `KXMLBGAME` cannot fill a sub-20c pre-game band

```
pre-game observations   51,286  (census, 17:00Z)  /  51,206  (audit, 16:58Z)
events                  85          markets  170
observations below 20c  0
observations below 15c  0
cheapest pre-game ask ever recorded            26.0c
```

| statistic | value |
|---|---|
| all pre-game observations | min **26.0c**, p1 **29.0c**, p5 **37.0c**, p25 44.0c, median 50.0c |
| per-event minimum ask | min 26.0c, p10 35.0c, p25 39.0c, **median 42.0c**, p75 46.0c, max 49.0c |

**The parts agree.** Per-slate minimum of the per-event minima, across six
slates:

```
2026-08-07  29.0c      2026-08-10  26.0c
2026-08-08  29.0c      2026-08-11  28.0c
2026-08-09  29.0c      2026-08-12  37.0c
```

**No slate comes within 12c of a 14c band.** The largest contributor is 15 of 85
events (18%), so no single slate is carrying the result.

**A second, independently-sourced price puts the wall in the same place.**
`closing_lines.yes_ask_tenths` is written from the candlestick endpoint, not
derived from a NO bid: **177 rows, minimum 29.0c, 0 rows ≤14c.**
*(Reported by the census lane. This figure could not be re-derived from the
artefacts available to this write-up and is carried on that lane's authority —
unlike every other number in this document.)*

**Coverage does not stop early, so the wall is not an artefact of the poller
going quiet before first pitch.** The last pre-game quote sits a median **6.9
minutes** before first pitch, with 40 of 45 events within 15 minutes.
*(Same provenance caveat as the previous paragraph.)*

**Depth is not the limiter either.** At 31–39c pre-game, displayed size is
median 695 with 96.7% of rows showing ≥10 — the prices that exist are deep
enough. There is simply nothing cheap.

**Sub-15c prices do exist in `KXMLBGAME` — 825 of them — and every one is
in-play.** All 825 are on markets now settled/finalized/closed, and they occur
**140–215 minutes after first pitch**. There is no pre-game route to the band.

> **So a registered `KXMLBGAME` band of 6c–14c is dead on reachability, not on
> budget.** The hypothesis boundary `(0.15, 0.27]` sits entirely below the
> cheapest price the series has ever shown pre-game.

### `KXWNBAGAME` — reachable, and much weaker than it looks

18 events, 10,778 pre-game observations, minimum ask 12.0c. One event
(`KXWNBAGAME-26AUG10TORATL`) supplies a low-band ask, and **1 of 18** is the
whole finding.

**Its two halves never co-occur.** The event-level census counts it as
"offering both", but the per-instant check returns **0 simultaneous instants**:
it is one market drifting down across time, observed low at some instants and
high at others. That is a different and much weaker shape than a standing pair,
and the event-level count is the misleading one.

It is also **never near tip-off**: 75 low-band instants, minimum lead time
**422 minutes**, zero within 3 hours. And it is **one market**, so `n = 1` on
every axis that matters.

---

## §3. Headline 2 — `KXMLBSPREAD` fills both bands, simultaneously

```
events 55    pre-game markets 330    (series carries 437 markets in total)
pre-game observations  52,530 (census)  /  52,470 (audit)
distinct polling instants                     696 (census)  /  695 (audit)
minimum pre-game ask                          7.0c
per-event minimum ask, median                 15.0c
```

Per-slate minimum, four slates: **9.0c / 10.0c / 8.0c / 7.0c**. Per-event
minimum: min 7.0c, p25 12.0c, median 15.0c, max 18.0c. Every event in the record
reaches at least 18c.

**Both halves of the registered pair are on the board at the same instant, at
every instant:**

```
instants showing a LOW  ask (6-15c excl 10c) : 696 / 696
instants showing a HIGH ask (27-39c excl 30c): 696 / 696
instants showing BOTH simultaneously         : 696 / 696   (100.0%)
distinct events supplying the LOW half  : 40 of 55
distinct events supplying the HIGH half : 55 of 55
displayed size, LOW half : n 5,039  min 1  median 2,914   max 35,026
displayed size, HIGH half: n 16,773 min 1  median 4,624   max 689,905
```

---

## §4. The audit — what it reproduced, and the six things it added

A `measurement-skeptic` lane exported the raw slice and recomputed with its own
code, deliberately not reading the census scripts for their numbers.
**Every headline number reproduced exactly**, with all deltas accounted for by
the two-minute cut difference (§1). The verdict is **SURVIVES WITH
QUALIFICATION**, and the qualification is the `n` section at the top.

It also established six things the census did not. These are the load-bearing
half of this document.

### 4.1 Within-event simultaneity — and it is the same strike, opposite teams

The census's series-level pair is the weak claim: "somewhere in the series a low
existed and somewhere a high existed." The audit tested the strong one.

```
instants with a within-EVENT LOW/HIGH pair       : 695 of 695  (100.0%)
of which the pair is the SAME STRIKE, opposite team: 658
distinct events that ever supplied both          : 40
```

Example at 2026-08-07 19:33Z:

```
LOW  15.0c size 133  strike 3.5  KXMLBSPREAD-26AUG081610ATHBOS-ATH4
HIGH 32.0c size 150  strike 3.5  KXMLBSPREAD-26AUG081610ATHBOS-BOS4
```

**This is what the shape actually is:** the two sides of one alternate run line.
Not a coincidence of two unrelated games, and not a single market drifting —
which is what `KXWNBAGAME` turned out to be.

### 4.2 Depth at size

```
LOW-band displayed size, n = 5,030
  p0     1        p25   1,558       p90   12,879
  p1     2        p50   2,914       p100  35,026
  p5   355        p75   6,711
share >= 20 contracts : 98.23%
restricted to <= 13c  : n = 2,725, share >= 20 = 97.32%
```

**The distribution is bimodal — under 10 or over 50** — so the median is not
describing a typical row so much as the upper mode. The left tail is real: p0 is
1 contract and p1 is 2.

**But availability at size is not rationed by instant:** at **695 of 695**
instants at least one qualifying low market showed ≥20 displayed, with a
**minimum of 2, median 7, maximum 15** such markets on the board at once.

### 4.3 It is not a derivation artefact

The derived ask `1000 − no_bid_tenths` was attacked from four directions and
survived all four.

| check | result |
|---|---|
| one-sided books | **0** of 5,030 low rows have a missing or zero YES bid |
| bid-ask width | 1.0c at p0/p25/p50/p75, 2.0c at p95, **4.0c max**; none crossed |
| frozen book | median **1.2 min** since the book last changed; only **1.8%** on a book unchanged >60 min |
| the identity itself | on the captured wire payload, `1 − no_bid_dollars == yes_ask_dollars` on **245 of 245** markets |

All 52,470 pre-game asks are **whole cents**, and `price_structure` is
`linear_cent` — so no deci-cent rounding is in play here.

### 4.4 What kind of market it is — alternate run lines only

```
strike 3.5  spread   4,408 LOW rows   40 markets
strike 2.5  spread     622 LOW rows    5 markets
strike 1.5  spread       0 LOW rows    0 markets
```

The series carries **110 pre-game markets at each of the three strikes**, so
this is not a coverage artefact: the standard 1.5 run line never reaches the
band, and the entire finding lives on alternate run lines.

### 4.5 Price stability — the ask does not flicker

```
median gap between consecutive observations of one market : 0.4 min
given in-band at one poll, in-band at the next            : 99.7%
ask unchanged between consecutive polls                   : 98%
largest single move                                       : 2.0c
maximal in-band episodes: n = 56 across 45 markets
  duration: p10 62 min, median 569 min, p90 1,335 min
  >= 30 min: 93%      >= 2h: 86%
```

**A median episode lasts 9.5 hours.** Whatever is quoting these levels is not
darting in and out.

### 4.6 Time of day — it is there when a human is awake

```
LOW rows within 3h of first pitch : 37.1%   (37.8% at depth >= 20), 30 of 55 events
polling instants 17:00-23:59 ET   : 189
  with a qualifying low (>= 20)   : 189 / 189  (100%)
  with one at <= 13c              : 164 / 189  (87%)
  qualifying markets on the board : min 2, median 4, max 13
```

Controlling for polling, **every one of the 24 ET hours shows 100% of its
instants carrying a qualifying low market**. That is a stronger statement than
the evening window alone — and it is still uptime, per the `n` section.

### 4.7 `KXMLBTEAMTOTAL` — comparable or better, and NOT audited

```
pre-game observations 122,570 across 696 instants and 55 events
instants with BOTH halves simultaneously : 691 / 696  (99.3%)
distinct events supplying the LOW half   : 50
LOW-band observations                    : 8,292
depth at LOW half: median 1,613  max 21,000
```

On raw availability this **beats** `KXMLBSPREAD` on the low-half event count
(50 vs 40). **It has had none of §4.1–4.6 run against it** — no within-event
test, no artefact check, no persistence measurement, no strike breakdown. It is
a lead, not a result, and must not be cited as one.

*(The census lane also reports a 5.0c minimum ask for this series. That figure
is not in the artefacts available to this write-up and is carried on that lane's
authority.)*

---

## §5. The pre-game boundary for `KXMLBSPREAD` — this is an INFERENCE, and it is labelled

**The 3h offset is directly validated for two series and inferred for the
third.** The third is the one the headline rests on, so the inference is written
out rather than assumed.

| series | ticker-hour clock | sportsbook clock |
|---|---|---|
| `KXMLBGAME` | **85 / 85** agree | **47 / 47** agree with `commence − 3h`; **0 / 47** with `commence` as-is; 38 unlinked |
| `KXWNBAGAME` | 0 parsed (tickers carry no hour) | **14 / 14** agree with `commence − 3h` |
| `KXMLBSPREAD` | **55 / 55** agree | **zero** linked events — nothing to check against |

> **The inference, stated in full.** `KXMLBSPREAD` has no sportsbook-linked
> event, so its boundary cannot be validated against an independent clock
> directly. It is validated by **transfer**:
>
> 1. its ticker ET hour agrees with `commence − 3h` on **55 of 55** events; and
> 2. all **55** events share a **byte-identical `commence_ms`** with their
>    `KXMLBGAME` twin (same game suffix, 55 of 55 identical); and
> 3. **47** of those twins are sportsbook-validated at `commence − 3h`, and
>    **0 of 47** validate `commence` as-is.
>
> **This is a chain of three steps, not a measurement.** It would break if
> `KXMLBSPREAD` events systematically carried a different `commence_ms`
> convention from their `KXMLBGAME` twins — which step 2 excludes for these 55
> events and nothing excludes in general.

Note also that a boundary error in the *unsafe* direction would only make things
worse for the finding, not better: if the true start were 3h earlier than
assumed, rows now counted pre-game would be in-play, and in-play is where the
cheap prices are known to live.

---

## §6. Harness defects found by the audit — recorded, because a result document that hides its instrument's faults is the thing this repo keeps getting caught by

### 6.1 The depth-units guard could not fail, and its stated inference was backwards

`census_band_reachability.py`'s `depth_units_check` cross-checked
`max(no_bid_qty)` against `kalshi_markets.open_interest` to test whether the
size column was a contract count or a 10⁴-scaled integer.

**It cannot fail.** `no_bid_qty` traces to `yes_ask_size_fp`
(`backend/kalshi/discovery.py:634`, via `runner.py:914`) and `open_interest` to
`open_interest_fp` (`backend/kalshi/discovery.py:625`). Both are read by a plain
`float()` with no unscaling. They are **the same `_fp` family**, so their ratio
is **invariant under any common rescaling** — the exact transformation the test
existed to detect.

**Its printed conclusion was also backwards.** It printed:

> *"a size of 1 or a fraction below 1 proves the column is a CONTRACT count, not
> a 10^4-scaled integer"*

A fractional value **disproves** an integer contract count; it cannot prove one.
And the record is full of them — **9,676 distinct non-integer sizes**
(6.87, 8.86, 12.8, 17.21, 27.71, …).

This is `tasks/lessons.md`'s **"Never anchor a convention test on a fixed point
of the transformation"** recurring, in the same shape.

> **The conclusion survives on a different anchor, and the guard has been
> deleted rather than repaired.** Round one's F3 reports `fee_cost` $0.178500 at
> `C = 20`, `P = 0.15`, and
> `0.07 × 20 × 0.15 × 0.85 = 0.178500` **exactly**. `C` is therefore a contract
> count, and round one's fractional fill (`C = 0.27`) shows it admits fractions.
> That anchor is outside the `_fp` family and cannot be a fixed point of a
> rescaling of it.

### 6.2 The `cross` statistic in `_pair.py` — uninformative, not wrong

`census_band_reachability_pair.py` computed, under the label *"of which the two
halves came from different events"*:

```python
cross = [t for t in both_t if (lo_at[t] | hi_at[t]) - (lo_at[t] & hi_at[t]) or len(lo_at[t] | hi_at[t]) > 1]
```

**Correcting the brief this lane was given:** the expression is **not logically
wrong**. The symmetric-difference clause is *redundant* — if `lo ≠ hi` and both
are non-empty then their union necessarily has ≥2 elements — so the whole
expression reduces to `len(lo | hi) > 1`, which **is** the correct test for
"some cross-event pair exists".

**The defect is that it cannot discriminate.** With 40 events showing a low ask
and 55 showing a high ask at essentially every instant, `len(union) > 1` is true
by construction, and it duly returned **696 of 696**. It is a guard that cannot
fail *in this population*, reported as though it had passed a test.

**It has been replaced by the within-event statistic**, which is the one that
carries information and which the audit computed independently: at how many
instants does a **single event** supply both halves? That returns 695/695 and is
a real claim about the shape of the book (§4.1). It happens not to have mattered
for the conclusion, because the stronger within-event claim holds anyway.

### 6.3 `market_status` is the CURRENT status, not the status at `observed_ms`

Not previously recorded, and it weakens one of the census's two stated traps.

`kalshi_markets` holds one mutable row per ticker, so `status` and `result`
describe the market **at the last discovery sweep**, not at the moment the quote
was observed. A market that finalized hours after a pre-game quote reports
`finalized` beside that quote. Accordingly, 3,994 of the 5,030 low rows carry
`status = finalized` — which looks alarming and means nothing, because the quote
itself was pre-game by the time filter.

**The consequence is that the status column cannot do the trap-checking the
docstring assigns it.** The protection against settled-market artefacts is
entirely the pre-game **time** boundary (§5), which is sound. The status column
is decoration for that purpose and is now documented as such.

**It does, however, mark a genuinely narrower slice worth naming.** Restricted
to markets still `active` at pull time — the only rows where the outcome was
unknown when the record was read — the low band is **1,036 rows over 10 markets
/ 9 events** (97.3% at size ≥20). That is the forward-looking population, and it
is much smaller than 5,030.

### 6.4 Four of the five harnesses were never exercised before being pointed at production

The seed harness `seed_and_verify.py` built a real-schema database with a known
shape and checked the census reported it. **It invoked only
`census_band_reachability.py`.** The `_pair`, `_detail`, `_atp` and `_allseries`
scripts were never run against a known answer at all before their first
execution was against the live record.

**And the seed's own "both bands" case would not have caught the thing that
mattered.** The seeded event offers a low ask at `start − 7200s` and a high ask
at `start − 5400s` — **two different `observed_ms`**. The fixture would have
passed identically if simultaneity never occurred anywhere in the world, which
is precisely what §4.1 exists to establish. Defect 6.2 survived for exactly this
reason.

---

## §7. What this measurement does not establish

*Written for this result, not echoed from any module docstring. The first one is
the one that governs.*

1. **AVAILABILITY, NOT FILL PROBABILITY — and this is the whole ballgame.**
   Every number in §3 and §4 comes from a stored quote. **Two explanations fit
   every single observation equally well:** (a) real resting liquidity that
   would have filled a small order, or (b) a maker displaying 2,914 contracts at
   13c who cancels the moment an order arrives. Depth, persistence,
   two-sidedness, tight spreads and the wire-format identity **do not
   distinguish these two worlds** — a quote-stuffing maker produces all of them.
   **No quote record can separate them. The separating observation is one small
   order**, and it has not been placed. Nothing here licenses a claim about what
   would fill.
2. **One week of one August, four game-days.** It says nothing about September,
   nothing about a thin slate, nothing about a winter sport, nothing about any
   other month. It refutes and establishes only on the population it covers.
3. **Persistence is measured on the polling grid, so every survival figure is an
   UPPER BOUND.** The median inter-observation gap is 0.4 min; an exit and return
   between two polls is invisible. "99.7% still in band at the next poll" and
   "median episode 569 minutes" both silently assume nothing happened in the gaps.
4. **Displayed size is top-of-book as stored, never reconciled against an
   orderbook snapshot.** `no_bid_qty` is the size at the single level that makes
   our ask. Depth behind it is not in the record, and the stored value has not
   been checked against a full book.
5. **Count the tests.** 11 series × 2 bands = 22 band cells, plus 3 series
   interrogated in detail. Any cell resting on one event — `KXWNBAGAME` is
   exactly this — should be read as the noise it probably is.
6. **`KXMLBSPREAD` is a SELECTED MAXIMUM**, not a forced choice. It was picked
   as the best of an 11-series scan *after* the scan. Its figures carry the
   selection, and `KXMLBTEAMTOTAL` (§4.7) is the reminder that the ranking was
   close.
7. **It does not establish anything about `KXMLBTEAMTOTAL`** beyond raw
   availability. None of the artefact, persistence or within-event checks were
   run on it.
8. **It does not validate the `KXMLBSPREAD` pre-game boundary directly.** §5 is
   a three-step transfer inference and is labelled as one.
9. **It does not establish that the low band is tradeable at the size the
   registration wants.** 45.8% of low rows sit at the 14–15c band edge; the
   `≤13c` region is 26 markets / 24 events; and the sub-10c tail is 3 markets.
10. **It does not establish anything about the future board.** Restricted to
    markets unsettled at pull time, the low band is 10 markets / 9 events (§6.3).
11. **It does not license a registration, an order, or a code change.** No
    hypothesis is adopted here, and no fee, gate or sizing constant is touched.

---

## §8. Corrections to figures already in circulation

The handoff that commissioned this document carried figures that do not
reproduce. They are corrected here so the wrong ones cannot be re-quoted.

| circulated | actual | note |
|---|---|---|
| `KXMLBGAME` pre-game **p1 28.5c, p5 29.2c** | **p1 29.0c, p5 37.0c** | Both lanes agree. The circulated pair reproduces from neither. `p5 29.2c` is out by 7.8 points and would make the wall look far closer to the band than it is. **`tasks/NEXT.md` carried `p1 28.5c` and is corrected.** |
| per-slate minima `29/29/29/26/29/37` | `29/29/29/26/**28**/37` | 2026-08-11 is 28.0c, not 29.0c. Conclusion unaffected — the binding slate is 26.0c. |
| `51,206` pre-game obs (census) | **51,286** census / **51,206** audit | Both correct at their own cut; the audit figure had been attributed to the census. |
| `KXMLBSPREAD` "55 events, **437 markets**" | 437 in the **series**; **330** pre-game | The pre-game denominator is 330, and it is 330 that the 45 low-supplying markets should be read against. |
| `_pair.py`'s `cross` "does not test what its label claims" | It tests it **correctly but vacuously** | See §6.2. The distinction matters: the code was not computing the wrong thing. |
| "22 of the 307 sub-10c rows come from one market" | 307 sub-10c rows over **3 markets / 3 events**; the **7c** corner is 22 rows from 1 market | Re-stated so the two facts are not merged. |

Figures carried on the census lane's authority and **not** reproducible from the
artefacts available here, flagged in place above: the `closing_lines` cross-check
(177 rows / 29.0c), the pre-game coverage figure (median 6.9 min before first
pitch), and `KXMLBTEAMTOTAL`'s 5.0c minimum ask.
