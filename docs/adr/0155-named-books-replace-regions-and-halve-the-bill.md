# 0155 — Named books replace regions, and halve the bill

Date: 2026-09-15
Status: Accepted
Amends the credit model in ADR 0071 §2.6 and ADR 0111; does not change any
cadence, cap or window.

## Context

ADR 0152 added `totals` to `ODDS_MARKETS` on 2026-09-14. The vendor charges
`markets × regions` (`backend/odds/budget.py:sweep_cost`), so with
`ODDS_REGIONS = "us,eu"` every scheduled call went **4 → 6 credits, a 50%
rise against an unchanged 700/day cap** — a cap sized for 4 when it was raised
600→700 on 2026-08-23 (`fly.live.toml:248`).

### The cap now binds, measured not projected

Every historical budget-day replayed at its own **call count** × 6, with the
300-credit attention slice applied (attention is capped in *credits*, so at 6c
it buys fewer calls; the naive replay overstates it and two days drop out once
corrected):

| day | calls | actual | at 6c |
|---|---|---|---|
| 2026-08-24 Mon | 141 | 564 | **846** |
| 2026-08-23 Sun | 139 | 290 | **834** |
| 2026-09-12 Sat | 133 | 532 | **798** |
| 2026-09-05 Sat | 124 | 496 | **744** |
| 2026-08-28 Fri | 120 | 480 | **708** |
| 2026-08-29 Sat | 118 | 472 | **708** |

Six days in a month exceed 700, and all six are floor+kickoff days, which the
attention cap does **not** bound. Every one had ≤3 sports in scope; the first
4-sport weekend is 2026-09-17..20. When 700 binds, `decide_sweeps` returns
`fire=()` and **every** sport stops until the next 10:00Z boundary.

### The obvious lever was a trap

`sweep_cost` is `markets × regions`, so `ODDS_REGIONS = "us"` looks like a free
halving — 6 → 3. It is not free. `runner.SHARP_BOOKS` is
`{pinnacle, betfair_ex_eu, betfair_ex_uk, matchbook}`, `consensus_devig`
selects on it exclusively when any member is present (`selected = sharp or
usable`, `core/devig.py:289`), and **every sharp book this feed actually
carries is EU-region**. Read off live 2026-09-15 over the last 40k
`odds_snapshots`: `pinnacle`, `matchbook`, `betfair_ex_eu` present;
`betfair_ex_uk` absent entirely. None is offered in the vendor's `us` region.

So `regions = "us"` makes `sharp = {}` on every row, and the consensus falls
back to unweighted retail. The size of that: **22,850 of the last 40,000
`fair_prices` rows (57%) carry `anchored_on_sharp = 1`; dropping `eu` takes it
to 0.** That trades the thing the desk exists for — sharp consensus to price
Kalshi against (ADR 0071) — for three credits a call.

**This was approved and not shipped.** Joe answered "drop eu regions and ship
it" on the framing that the cost was "the EU books in the consensus". That
framing was written before anyone checked *which* books `eu` carried; the
check was run first, the approval was returned to him with the 57% figure
attached, and he chose this option instead.

## Decision

**Buy named bookmakers instead of whole regions.**

The vendor's rule: *"Every group of 10 bookmakers is the equivalent of 1
region"*, and *"if both `bookmakers` and `regions` are both specified,
`bookmakers` takes priority"*. So ten named books at three markets is
**3 credits**, the same saving as dropping `eu`, with the sharp anchor intact.

**Verified against their own counter before any code was written**
(2026-09-15, one paid call, bracketed by the free `/v4/sports` probe):

```
before   used=5048  remaining=14952
odds call status=200        x-requests-last: 3
after    used=5051  remaining=14949
MEASURED COST (used delta) = 3
books asked for : 10    books returned : 10    missing : []
```

### The ten, and why each

| book | why |
|---|---|
| `pinnacle` | sharp; h2h + spreads + totals |
| `matchbook` | sharp; h2h + spreads + totals |
| `betfair_ex_eu` | sharp; **h2h only** — 0 spreads, 0 totals |
| `fanduel`, `draftkings`, `williamhill_us`, `fanatics`, `sport888`, `bovada`, `betmgm` | the seven highest-coverage books across all three markets (~1100 h2h / ~1100 spreads / ~420 totals each over the last 60k snapshots) |

`betfair_ex_uk` is in `SHARP_BOOKS` and is **deliberately not here**: it
returned nothing in the last 40k snapshots, and an absent book still consumes
a slot toward the next group of ten.

**Spreads and totals are anchored by `pinnacle` + `matchbook` alone**, because
`betfair_ex_eu` quotes h2h only. That is true today under `us,eu` as well —
this change does not cause it — but it is now written down.

## Consequences

- Every scheduled call is **3 credits, not 6**. The idle floor at 4 sports
  falls ~576 → ~288/day; a full kickoff cluster 42 → 21; the attention slice
  buys twice the dwell per credit. All six over-cap days above replay under
  350.
- **The sharp anchor is unchanged.** The 57% of rows that anchor on a sharp
  book get identical prices — `selected = sharp` reads the same three books.
- **The fallback consensus narrows**, on the 43% where no sharp quotes: seven
  quality US books instead of ~30 mixed. `SuppressionConfig.min_book_count` is
  2, so the `too_few_books` gate is not at risk; `book_count` and
  `market_width` do change, and both feed `score_trust`.
- **No cap is raised.** `ODDS_DAILY_CREDIT_BUDGET` stays 700 and
  `ODDS_MONTHLY_CREDIT_BUDGET` stays 18,000. Raising the daily was considered
  and refused: 700 × 30 = 21,000 > 18,000, so the daily has never bounded the
  month, and relaxing it moves the bind to a monthly ceiling that blacks out
  until the calendar rolls.
- `ODDS_BOOKMAKERS` defaults to empty, so any deployment that does not set it
  keeps buying regions exactly as before.

## What this does not establish

- **That the saving holds for prop calls.** The verification call was
  `/sports/{sport}/odds`, the team path. The per-event prop endpoint bills the
  same way by documentation and shares `sweep_cost`, but no prop call has been
  made under `bookmakers`. The first NFL prop tap is the measurement.
- **That these ten spell correctly for every sport.** They were verified on
  `baseball_mlb`. A misspelled or sport-absent key is **silently absent from
  the response and still costs a slot** — it does not error. NCAAF, NFL and
  WNBA coverage under this list is unmeasured; read the returned book set on
  the first call for each.
- **Anything about price quality.** Whether a 10-book fallback consensus is
  better or worse than a 30-book one on the 43% of rows without a sharp is not
  measured here and is not claimed. The sharp-anchored majority is unchanged,
  which is the property this decision rests on.

## Guards, each seen red once

`tests/test_named_bookmakers_billing.py`.

| mutation | test that went red |
|---|---|
| `sweep_cost` ignores `bookmakers`, bills on `regions` (pre-0155) | 6 tests, incl. `test_ten_books_cost_one_region` |
| `_region_params` merges both keys instead of choosing | `TestExactlyOneKeyIsSent` (2) |
| `credits_per_sweep_per_sport` multiplies `markets × regions` directly | `test_credits_per_sweep_reads_the_books` |
| the env parser keeps empty/whitespace names | `test_the_env_list_is_parsed_without_phantom_books` (3) |

`TestTheLiveDeployNamesTenBooksAndKeepsTheSharps` reads `fly.live.toml`
itself, so the deployed list cannot drift past ten, gain a duplicate, or lose
a sharp without a red test.

## The pattern

**Before offering a config knob as a cost lever, read what is actually on it.**
`regions` looked like a pure multiplier in `sweep_cost` and was in fact the
carrier of every sharp book in the system. The arithmetic was visible in one
line; the consequence took a query against `odds_snapshots` and one against
`fair_prices`. Cost levers are proposed from the formula and must be validated
against the data.
