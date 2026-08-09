# 0016 — The historical backfill: what it is for, how its rows are tagged, and where hindsight leaks in

**Status:** proposed, 2026-08-09

Settles the three things `start.md` says must be settled **before a single line
of the backfill loop is written**. This is a design document. It specifies a
schema change; it does not implement one, and no code under `backend/store/`
was touched by the lane that produced it.

Zero Odds API credits were spent writing this. Every number below comes from the
code, from `docs/adr/0011`'s retention addendum, from `tasks/NEXT.md`'s live
readings, from `tests/fixtures/candlesticks_mlb.json`, or from The Odds API's
own published cost formula.

---

## 1. The prediction, written down before the loop exists

### 1.1 What the record already says

Live, over a 24-hour window (`tasks/NEXT.md`, gate progress at 04:38Z and the
15:46Z window read):

    actionable = 0   no_edge = 161 → 193   suppressed = 265
    suppressed by: stale_odds=256, too_few_books=73, no_market_width=73,
                   edge_within_method_noise=4

`stale_odds` is 256 of 265 suppressions and is structural — the credit budget,
not the market. Strip it and the population where the engine could actually
speak is:

| | |
|---|---|
| decisions with a fresh consensus | ~202 (193 `no_edge` + ~9 suppressed for a non-staleness reason) |
| of which actionable | **0** |

One decision is one `(market, side)` pair. This is the `n` the prediction is
built on, and it is the right one: the backfill chooses `T`, so `stale_odds`
cannot fire in it by construction. The backfill's comparison group is the
fresh-odds population, never the pooled 426 rows.

### 1.2 The prediction, as a number with an interval

Zero successes in 202 trials. The exact one-sided 95% Clopper–Pearson upper
bound on the per-decision actionable rate is

    p ≤ 1 − 0.05^(1/202) = 0.0147  (1.47%)

which the rule of three (3/202 = 1.49%) reproduces to two decimals.

A backfill of **~1,200 MLB games** is **~2,400 decisions** (both sides of one
moneyline per game).

> **Pre-registered prediction.** Actionable decisions from a 1,200-game
> backfill: **point estimate 0, 95% upper bound 35.** Actionable *games*
> (the unit the gate counts): **point estimate 0, 95% upper bound 35**, and
> realistically below that, since both sides of one game are rarely
> simultaneously actionable.
>
> **The gate needs 300 actionable games. It does not open.**

### 1.3 The gate cannot open, and that is knowable now — so state which goal

This is the part worth being blunt about. Reaching 300 actionable games out of
1,200 needs a **25% per-game** rate, i.e. ~12.5% per decision. The probability
of observing 0 in 202 decisions if the true rate were that high is

    (1 − 0.125)^202 = 1.9 × 10⁻¹²

That is not "unlikely". It is a different system. And the ceiling does not move
with sample size: even a perfect zero across the full 2,400 decisions leaves the
95% upper bound at 0.125% — **3 actionable games from 1,200**, against a floor
of 300.

**So the counter goal is unreachable by arithmetic, independently of what the
data turn out to say.** No honest version of this build fills the counter.

**This build is for the measurement goal.** It exists to move the actionable-rate
estimate from n=202 to n≈2,400 — a 6x tightening of the bound on the one number
that decides whether this strategy is worth continuing. Framed as "fill the
counter" it is a guaranteed failure that will read as one. Framed as "measure the
actionable rate at n=2,400" it is the highest-value thing available, because it
either ends the strategy honestly or overturns the current picture, and those are
the only two outcomes that matter.

Anyone who later reports this build as "the backfill failed to open the gate" is
reporting the thing this ADR said in advance would happen.

### 1.4 Pre-registered readings — decided now, not after the numbers land

| Result | Reading | Action |
|---|---|---|
| **0–35 actionable decisions** (inside the predicted interval) | The live measurement confirmed at 12x the sample. The strategy as specified — Kalshi moneyline against devigged consensus — does not produce bets. | Stop hunting this edge. The product becomes the measurement record and the honest negative result. Say so in `CLAUDE.md`. |
| **36–120 actionable** (above the bound, far below the floor) | The historical regime differs from live. **Look for the leak first.** Section 3's contaminated rows are the first suspects, in this order: depth exemption, choice of `T`, bar selection. | Freeze. Audit against Section 3's table before any number enters the record. `measurement-skeptic` reviews before it is written down. |
| **>120 actionable** | ~4x the 95% bound. Under CLAUDE.md rule 1, a large apparent effect is a bug until proven otherwise, applied to the whole harness rather than to one row. | Treat as a defect in the reconstruction. Do not report a rate. |
| **Any result, plus mean CLV > 0 clearing the always-valid bound** | Interesting, and still not gate-opening: backfilled rows do not count (Section 2.4). | A separate, pre-registered follow-up, not a licence to arm anything. |

One more pre-registration, because it is the failure mode that would make the
predicted result arrive for the wrong reason: **if the harness runs with
`BANKROLL_DOLLARS=100`, `size_position` refuses every row** (`start.md`: at $100
with `MIN_ORDER_CONTRACTS=10`, quarter-Kelly sizes under one contract on every
edge below `edge_ceiling_tenths`). That produces exactly 0 actionable for a
configuration reason and would look like confirmation. The harness must pin a
declared reference bankroll and **abort loudly** if the configured value would
make the actionable count structurally zero. See Section 3, input 21.

### 1.5 What this build does not establish

That no edge exists anywhere on Kalshi. It measures one strategy (moneyline,
devigged sportsbook consensus, one league, one 80-day window, today's
thresholds) against one benchmark. It says nothing about spreads, totals,
in-play, combos, or a power-ratings model that has never run.

---

## 2. Schema v6: a provenance column on `recommendations`

### 2.1 The problem, one level up from ADR 0011

`recommendations` has 27 columns and none records where a row came from. Write
retrospective rows into it and `evaluate_gate` reads one population where there
are two.

ADR 0011 fixed exactly this shape one level down: `clv_horizon_hours` was added
because `clv_tenths` was becoming "a silent mixture of two regimes". The
remedy there — tag, filter, let the counter drop loudly rather than blend — is
the remedy here.

It is not hypothetical and not new. `seed_demo.py:384` and
`scripts/demo_execution.py:67` already `INSERT INTO recommendations`. The table
has held a mixture since the demo seeder was written; nothing has ever been able
to say so.

### 2.2 The column

```sql
ALTER TABLE recommendations
    ADD COLUMN provenance TEXT NOT NULL DEFAULT 'live';
```

| | |
|---|---|
| **Name** | `provenance` |
| **Type** | `TEXT NOT NULL DEFAULT 'live'` |
| **Live rows** | `'live'` — written by `runner.run_pricing_pass` from a quote observed by this process |
| **Backfilled rows** | `'backfill'` — reconstructed at a chosen `T` from historical odds and candlestick bars |
| **Demo rows** | `'demo'` — `seed_demo.py`, `scripts/demo_execution.py`. Not a new state; a state that already existed and was unnameable |
| **Default for rows written before it existed** | `'live'` |

**Why `TEXT` and not `is_backfill INTEGER`.** A boolean cannot express the third
value that is already in the table today. Two-valued columns are how a third
case gets silently filed under one of the first two — `tasks/lessons.md`,
"test the filter's exclusions": an unrecognised value must fail a drift test,
not fall into a default. A drift test enumerates the distinct values in the
column and asserts each is explicitly classified as gate-eligible or not.

**Why `NOT NULL DEFAULT 'live'` rather than nullable.** Three reasons, and the
third is the one that decides it:

- On the live volume, every existing row *is* a live-engine row — the only other
  writers are the demo seeder and the demo execution script, which run on the
  demo deploy's separate database (ADR 0002). The demo seeder resets rather than
  appends, so a demo volume rewrites its own rows with `'demo'` on the next boot.
- A `NULL` state would have to be handled at every one of the 21 call sites in
  Section 2.5, and `COALESCE(provenance,'live')` repeated 21 times is 21 chances
  to write `provenance = 'live'` instead and silently drop the whole history.
- **A `NULL` can never be a backfilled row**, because the writer that produces
  backfilled rows cannot exist before the column does. So the strict reading buys
  nothing against the hazard the column exists for, and costs the live record.

This differs from ADR 0011's choice deliberately. There, `NULL` on
`clv_horizon_hours` meant *unscored*, so excluding it was free. Here excluding
the default would discard live evidence to guard against a state that cannot
arise.

**No second column is needed to identify a backfill run.**
`strategy_config_version` already segments by configuration, and the backfill
mints its own version (`ensure_strategy_config` does this automatically, since
the config dict will differ). The pair `(provenance, strategy_config_version)`
identifies a run.

**One migration hazard, already documented in `schema.sql:376–384`:** SQLite's
`DROP COLUMN` rewrites the stored `CREATE TABLE` text, and a comment sitting
immediately before the *last* column survives the drop while the column does
not. `provenance` must not be added as the last column with a comment above it,
or the migration tests that build a "v5 database" by dropping v6's columns turn
the table unparseable. Add it before the CLV block, or carry no comment above it.

### 2.3 Should the gate count backfilled rows? **No.**

Stated explicitly because the task asks for it, and defended because the
temptation is real: 1,200 games is four times the floor and it is sitting right
there.

**(a) Backfilled rows pass a strictly weaker rule set.** Kalshi's candlestick
payload carries no resting size — verified against the captured fixture, which
has `volume_fp` and `open_interest_fp` and no book at all (Section 3, input 10).
So `depth_at_ask` is `None`, and `no_depth` / `insufficient_depth` — a check that
fires on live rows — cannot be evaluated. A backfilled "actionable" row is
actionable under fewer conditions than a live one. Counting it makes the money
gate **easier**, and ADR 0005 established that a money guard may only ever move
harder. That alone settles it.

**(b) The risk caps are structurally inert.** There is no order history at a past
`T`, so `current_exposure_dollars`, `current_position_dollars` and
`daily_pnl_dollars` are all zero. `max_position_dollars`, `max_exposure_dollars`
and `max_daily_loss_dollars` can never bind. Same direction: weaker filtering.

**(c) The selection process differs.** Live, `T` is decided by
`odds/timing.decide_sweeps` under a credit budget. In the backfill we choose `T`.
Even if every value were perfectly reconstructable, the two are not one
population, because they are not sampled the same way.

**(d) Precedent.** ADR 0011 already accepted the cost of a counter that *drops*
when a regime changes, rather than a counter that blends. The 1.0h rows are kept
"as record, not as evidence". Backfilled rows get exactly that status.

**What they are for instead:** the actionable-rate measurement of Section 1,
`mart_suppression_audit`, `mart_clv_by_bucket` and `horizons_agree` — every one
of which must report them **segmented by provenance and never pooled**. This is
the repo's own rule that a pooled number is not a finding until the parts agree,
applied before the pooling can happen.

### 2.4 Two sites the obvious chokepoints do not cover

Filtering `gate.POPULATIONS` covers the CLV estimator, the population counts, the
digest and both API gate surfaces. It does **not** cover these two, and both are
worse than a mis-reported statistic:

**`live.open_decisions` (`backend/live.py:151`)** selects
`suggested_contracts > 0 AND suppressed_reason IS NULL`, newest per
`(ticker, side)`, and carries `authorised_contracts` — it bounds order size and
drives the WebSocket re-pricing subscription. A backfilled row with a positive
size would authorise contracts on a market that settled two months ago.
**Highest-severity item in this document.** It must filter `provenance = 'live'`.

**`engine.persist_if_changed` (`backend/engine.py:410`)** compares against the
most recent stored row for a `(ticker, side)` *regardless of provenance*. Two
failures follow. A backfilled row becomes "the previous row" and a live pass's
identical decision is silently swallowed as a confirmation instead of recorded.
Worse, `confirm_recommendation` then stamps that **backfilled** row with the live
pass's `last_confirmed_ms` and both live ages — so `gate.live_ages` reads it as
fresh, and a two-month-old reconstructed decision presents to the order path as a
current one. The lookback must be scoped to the same provenance.

`engine.persist_recommendation` should take `provenance` as a **required**
argument with no default, so a future writer cannot omit it.

### 2.5 Every query that must start filtering on it

Found by enumeration across `backend/`, `warehouse/` and `scripts/`, not
guessed. `frontend/` contains no SQL — it is a pure HTTP client of the routes
below.

**Money / gate — filter to `provenance = 'live'`:**

| # | Site | Why |
|---|---|---|
| 1 | `gate.POPULATIONS` — `backend/gate.py:284` | The single chokepoint: adding the clause once here covers `clustered_clv`, `clv_by_population`, `_clv_evidence` and `population_counts`, and transitively the digest and both API gate surfaces |
| 2 | `gate.clustered_clv` — `gate.py:397` | The gate's CLV estimator. Filter here too, since `population=None` bypasses `POPULATIONS` entirely |
| 3 | `gate.population_counts` — `gate.py:312` | The "can the gate ever open" counter |
| 4 | `gate.recommendation_freshness` — `gate.py:779` | Read by the order endpoint |
| 5 | `api.routes.place_order` — `routes.py:845` | Must refuse a non-live provenance **by name**. A 60-day-old row also fails the staleness check, but defence by coincidence is the pattern `lessons.md` records under the `market_width` bug masked by `min_book_count` |
| 6 | `live.open_decisions` — `live.py:151` | Section 2.4. Authorises contracts |
| 7 | `api.routes.board` — `routes.py:489` | The Board must not offer a settled game as an opportunity |
| 8 | `api.routes.market` — `routes.py:570` | Newest row per ticker; a backfilled row could become "the" row |
| 9 | `notify.alerts._digest_stats` — `alerts.py:258, 269` | A backfill run injects thousands of rows into a day window and makes the phone digest nonsense |
| 10 | `gate.log_gate_progress` — `gate.py:345` | Via 1 and 3 |

**Evidence / measurement — must segment by provenance, never pool:**

| # | Site | Why |
|---|---|---|
| 11 | `clv.load_observations` — `clv.py:294` | Add `provenance` to the `group_by` keys. Pooling across it is the Simpson's-paradox axis this parameter exists for |
| 12 | `clv.horizons_agree` — `clv.py:333` | Run per provenance. Mixing regimes into a drift statistic destroys the one check that catches convergence |
| 13 | `engine.suppression_summary` — `engine.py:440` | A backfill's suppression profile is different **by construction** (no depth check, no stale odds). Pooling corrupts the one diagnostic that says which rule is killing everything |
| 14 | `playbook.config_versions` — `playbook.py:76–100` | Counts rows and actionable per config version; the backfill's version will dominate the table |
| 15 | `api.routes.ledger` — `routes.py:604` + its pooled `clustered_clv(conn)` at `:608` | The Ledger's headline counters must not pool |
| 16 | `api.routes.suppression` — `routes.py:625` | Via 13 |

**Write path:**

| # | Site | Change |
|---|---|---|
| 17 | `engine.persist_recommendation` — `engine.py:310` | Required `provenance` argument, no default |
| 18 | `engine.persist_if_changed` — `engine.py:410` | Scope the dedupe lookback to the same provenance (Section 2.4) |
| 19 | `seed_demo.py:384`, `scripts/demo_execution.py:67` | Write `'demo'` |

**Not filtered, but load-bearing:**

| # | Site | Note |
|---|---|---|
| 20 | `clv.score_recommendations` — `clv.py:214` | Scores everything, correctly — backfilled rows are the measurement. The `created_ms <= closing_observed_ms` rule still applies and is satisfied by `T ≤ kickoff − 15min` (Section 3, input 25) |
| 21 | `scoring.markets_awaiting_scoring` — `scoring.py:108` | Must **not** exclude backfill, but ~1,200 extra markets each trigger two Kalshi candlestick calls per pass. Needs a bound or a separate pass. Operational hazard, not a correctness one |

**Warehouse.** `store/publish.py:98` is `SELECT * FROM {table}`, so the column
crosses the Parquet boundary with no change. From there:

| # | Site | Change |
|---|---|---|
| 22 | `warehouse/models/staging/stg_recommendations.sql:16` | Expose `provenance`. Single entry point for the whole warehouse |
| 23 | `mart_clv_by_bucket`, `mart_calibration`, `mart_suppression_audit` | Group by or filter to one provenance |
| 24 | `mart_multiple_comparisons` | **Grouping by provenance doubles the cell count, so it doubles `n_tests`.** That is correct and must be reflected, not worked around — the model exists to count tests, and this build adds tests |

Tests insert into `recommendations` directly in ten files. The `DEFAULT 'live'`
keeps every one of them compiling; whether they are still testing the right
population is a separate question each one has to answer.

---

## 3. Look-ahead: every input, and when it was observable relative to `T`

This is the bulk of the work and the whole risk. A backtest that flatters is
worse than none.

Two sources, with opposite properties, and the asymmetry drives the build order:

- **Kalshi candlesticks** — free, and **perishable**: ~80 days, measured
  (`docs/adr/0011` addendum), after which the market delists and the history goes
  with it.
- **The Odds API historical** — expensive (10x), and **permanent**: snapshots back
  to 2020-06-06.

> **Build order consequence: harvest the Kalshi side first, before spending a
> single credit.** It is free and it is the half that expires. Capture the entry
> bars, the closing bars, *and* the market metadata (`ticker`, `yes_side_team`,
> `series_ticker`) for the whole 80-day window, because when a market delists,
> `/markets` stops listing it and the constructed ticker 404s — both halves go at
> once.

### 3.1 The table

`T` is the reconstructed decision instant. "Observable at `T`" means a
participant standing at `T` could have read this value.

| # | Input | Live source | Observable at `T`? | Historical source can deliver it as of… | Verdict |
|---|---|---|---|---|---|
| 1 | `ticker` (market universe) | `/events?with_nested_markets` | Yes | **Now**, not `T`. Only currently-listed markets are visible | ⚠ **Survivorship.** A market listed at `T` and since removed is invisible. Direction unknown |
| 2 | `side` (yes/no) | Derived | — | Derived | ✅ |
| 3 | `market_type`, `yes_side_team` | Market metadata | Yes | Static over market life | ✅ |
| 4 | `price_structure` (cent / deci-cent) | Market metadata | Yes | Static | ✅ |
| 5 | YES `ask_tenths` | `1000 − best_no_bid`, derived | Yes | Candle `yes_ask.close_dollars` at `end_period_ts ≤ T` | ⚠ **Different construction** — published ask vs derived-from-bid. Needs one free verification (§3.3) |
| 6 | NO `ask_tenths` | `1000 − best_yes_bid` | Yes | `1000 − yes_bid.close_dollars` at `end_period_ts ≤ T` | ✅ Same identity as live |
| 7 | Bar selection | n/a | — | The bar whose period **contains** `T` closes up to 60s **after** `T` | ❌ **Contaminated unless the rule is `end_period_ts ≤ T`.** The obvious "nearest bar" selection leaks up to a minute of future |
| 8 | `high_dollars` / `low_dollars` / `open_dollars` on `yes_bid`, `yes_ask` | n/a | No | Present in every bar | ❌ **Forward-looking within the bar. Must never be read.** Only `close` is safe |
| 9 | `price.close_dollars` (last trade) | n/a | No | Present in every bar | ❌ **This is `last_price`.** CLAUDE.md: on a settled market it has already converged on the outcome. Must never be read |
| 10 | `depth_at_ask` | Opposing bid size (`yes_ask_size_fp` / WS book) | Yes | **Nothing.** The captured fixture carries `volume_fp` (traded) and `open_interest_fp` — neither is resting size at the ask | ❌ **CANNOT BE RECONSTRUCTED.** See §3.2 |
| 11 | `kalshi_quote_age_ms` | `T − observed_ms`, usually <30s | Yes | `T − end_period_ts` | ✅ **if `T` is defined as a bar's `end_period_ts`** (age = 0 genuinely). Any other `T` gives 0–60s against a 30s limit, suppressing ~half the rows for a granularity reason |
| 12 | Raw book prices per outcome | `/v4/sports/{s}/odds` | Yes | `/v4/historical/.../odds?date=T` returns the snapshot at or before `T`; `timestamp` says which. 5-min grid since Sept 2022, and the whole 80-day window is post-2022 | ✅ **The cleanest input in the table** |
| 13 | `book_updated_ms` (per-book `last_update`) | Response field | Yes | Present in historical snapshots | ✅ but compute `odds_age_ms = T − book_updated_ms`, **not** `snapshot_timestamp − book_updated_ms`, or the books read up to 5 min fresher than they were |
| 14 | `book_count`, `books_used`, `anchored_on_sharp` | Derived from 12 | Yes | Derived from 12 | ⚠ Book **coverage** in historical snapshots may differ from live, changing how often `too_few_books` fires. Measure it; do not assume |
| 15 | `market_width` | Derived from 12 | Yes | Derived from 12 | ✅ |
| 16 | Four devig probabilities, `p_conservative`, `method_spread` | Pure functions of 12 | Yes | Same | ✅ |
| 17 | `commence_ms` (sportsbook) | Odds response | Yes | Carried on the historical snapshot itself — **as of `T`** | ✅ Better than live's own record: a game postponed *after* `T` still shows its pre-`T` scheduled start |
| 18 | `commence_skew_ms` | Kalshi `occurrence_datetime` − odds commence | Yes | Kalshi half is read **now**; odds half is as of `T` | ⚠ **Mixed clocks.** For a rescheduled game the skew is fictional. Exclude games whose as-of-`T` and as-of-now odds commence disagree |
| 19 | `link_id` (alias match) | `match/linker` | Yes | Alias tables are curated **today** | ⚠ **Selection effect, not look-ahead.** A link that would have failed at `T` may succeed now, admitting games live would have dropped. Record it |
| 20 | `model_probability` | Never assigned | — | Never assigned | ✅ Absent in both, identically |
| 21 | `RiskConfig` (bankroll, kelly, caps, `min_order_contracts`) | `.env` | n/a | Today's config on a past decision — that **is** the counterfactual | ⚠ **`BANKROLL_DOLLARS` is a trap.** At $100 every row refuses and the run returns the predicted answer for the wrong reason. Pin a declared reference bankroll; abort loudly otherwise (§1.4) |
| 22 | `current_exposure` / `position` / `daily_pnl` | `store.orders` | Yes | No order history at a past `T`; all zero | ⚠ **Caps never bind → weaker filtering → flattering direction.** Record it |
| 23 | `SuppressionConfig` thresholds | `.env` | n/a | Today's thresholds | ⚠ Pin; segment via `strategy_config_version` |
| 24 | `fee_predicted` | `calculate_fee` | n/a | Deterministic in ask and size | ⚠ Pinned to the conservative-max model. If the fee-calibration trades land mid-run the rows split into two regimes; `strategy_config_version` covers it |
| 25 | `created_ms` = **`T` itself** | `odds/timing.decide_sweeps` under a credit budget | — | **Chosen by us** | ❌ **The single largest look-ahead risk in the design.** See §3.4 |
| 26 | Closing line at horizon 0 | Candles in `[kickoff−15min, kickoff]` | **No — after `T` by design** | Same | ✅ It is the dependent variable, not an input. Requires `T ≤ kickoff − 15min` so `created_ms ≤ closing.observed_ms` holds |
| 27 | `kalshi_markets.status`, `.result` | Market metadata | **No** | Read now = the outcome | ❌ **Fully contaminated.** Not read by the recommendation path today. Must not become a filter on which games to include |
| 28 | `kalshi_markets.volume_24h`, `.open_interest` | Market metadata | Values differ | Read now = post-settlement | ❌ **Contaminated as stored.** The backfill's discovery upsert would overwrite these with today's values. The candle's `open_interest_fp` *is* as-of-`T` and is the correct substitute if ever needed |

**Tally: 28 inputs.**

- **12 clean** — 2, 3, 4, 6, 11, 12, 13, 15, 16, 17, 20, 26. (11 and 13 are clean
  only under the stated rule; 5 joins them once §3.3 verifies it.)
- **9 partial or regime-different** — 1, 5, 14, 18, 19, 21, 22, 23, 24. Each must
  be recorded rather than corrected away.
- **7 contaminated or unreconstructable** — 7, 8, 9, 10, 25, 27, 28.

Of those seven, **five are contamination by *availability*** (8, 9, 27, 28, and 7
as a selection rule): the column exists, reads plausibly, and must be banned by
name. **One (10) is contamination by *absence*** and is the structural one. **One
(25) is the choice of `T`**, which is a process risk rather than a data one and
is the largest of the three kinds.

### 3.2 The one that cannot be reconstructed: `depth_at_ask`

Verified against `tests/fixtures/candlesticks_mlb.json`, a verbatim capture. A
bar carries exactly:

    end_period_ts, open_interest_fp, volume_fp,
    price{close,high,low,mean,open,previous}_dollars,
    yes_ask{close,high,low,open}_dollars,
    yes_bid{close,high,low,open}_dollars

There is no resting size anywhere. `volume_fp` is what traded; `open_interest_fp`
is contracts outstanding. Neither is "how many contracts I could lift at the
ask", which is what `min_depth_contracts = 10` checks and what ADR 0010's
`depth_capped_taker` fill assumption rests on.

Three options, and only one is honest:

- **Set `None` and let suppression refuse.** `no_depth` fires on every row,
  actionable is structurally 0, and the run measures nothing. Rejected — this is
  the same shape as the $100 bankroll trap.
- **Substitute a constant.** Fabrication. Rejected outright.
- **Set `None`, exempt the depth check for `provenance = 'backfill'`, and record
  the exemption.** Accepted — and it is precisely why the gate must not count
  these rows (§2.3(a)). A backfilled actionable row passed one fewer check than a
  live one, and the record must be able to say so.

The exemption must be a named, tested carve-out in the harness, not a `None` that
happens to slip past — and it must appear in `suppression_summary` as an
explicit `depth_not_reconstructable` state rather than as silence.

### 3.3 One free verification, before anything else

> **Done, 2026-08-09 — they agree.**
> `docs/measurements/2026-08-09-candle-ask-reconciliation.md`,
> `scripts/reconcile_candle_ask.py`. 51 observations across 46 distinct markets,
> zero mismatches, in integer tenths, including 8 genuinely sub-cent prices.
>
> **Re-scoped, and the difference matters.** The design below reconciles against
> the live `kalshi_quotes` table; that database was not reachable from the lane
> that ran this, so it captured a fresh quote and the candle covering the same
> moment in one pass instead. That excludes a *structural* construction
> difference — which is what this section asks about — but it does **not** cover
> the retention window, so a time-varying disagreement would have escaped it.
> The offline version below is still worth running once the live volume is
> reachable, and should be, before Phase 1's credits are spent.
>
> Input 5 moves to clean; the §3.1 tally becomes 13 clean / 8 partial / 7
> contaminated. Two conditions attach to Phase 0 — a bar publishes a boundary
> value where the live path returns `None`, and bar coverage is not one per
> minute per market. Both are in the write-up's §7.

**Does the candle's published `yes_ask.close` equal the ask this project
derives?** Live, the ask is `1000 − best_no_bid` and the schema is emphatic that
asks are derived, never stored as published. The candle publishes `yes_ask`
directly. If the two differ — by a tick, by a rounding convention, on deci-cent
markets — every backfilled entry price is off, in the direction that decides
whether a 4c edge exists.

Cost: zero. The live database already holds `kalshi_quotes` with real bids at
known instants. Pull the candle for the same minute and compare. Do this before
the first credit is spent.

### 3.4 The choice of `T` is the whole experiment

Any rule for picking `T` that uses information about the game — its price path,
its result, whether an edge existed at some minute — is hindsight, and it will
produce a beautiful backtest.

**The rule, fixed here and not to be tuned after seeing results:** `T` is a pure
function of the slate's kickoff schedule as it stood at `T`. Concretely, run
`odds/timing.decide_sweeps` over the historical slate exactly as the live
scheduler would have, and take its slots. Fallback if that proves impractical:
`T = kickoff − 20 min`, applied uniformly, satisfying `T ≤ kickoff − 15min` for
input 26.

The pre-registration that makes this checkable: **the number of snapshot
timestamps is decided by the schedule alone, before any price is read.** If the
harness ever fetches more than the planned snapshots, or picks among them, the
run is void.

---

## 4. Costing

**The Odds API's own formula**, confirmed against the vendor guide (a docs fetch,
zero credits): *"The usage quota cost for historical odds is 10 per region per
market. cost = 10 × [markets] × [regions]."* Snapshots are on a 5-minute grid
from September 2022; the whole 80-day window is inside that.

| | |
|---|---|
| Markets requested | `h2h` only — `runner.py` prices moneyline and nothing else. **1** |
| Regions | `us,eu` — `eu` carries Pinnacle, Betfair and Matchbook, and `consensus_devig` anchors on them. Dropping `eu` is not a saving, it is a different experiment. **2** |
| **Cost per call** | 10 × 1 × 2 = **20 credits** |
| Calls per day | ~6 kickoff clusters, from `scripts/measure_slot_coverage.py` (6 slots covered 18 of 19 games on a real 19-game slate). One call returns the whole slate at one instant |
| Days | ~80 (candlestick retention, measured) |
| Games | ~1,200 MLB → ~2,400 decisions |
| **Total** | 80 × 6 × 20 = **9,600 credits** |

**Does it fit?** Budgets are `ODDS_DAILY_CREDIT_BUDGET = 400`,
`ODDS_MONTHLY_CREDIT_BUDGET = 13,000`, plan = 20,000/month. Reserved headroom is
**7,000 per month**.

**9,600 does not fit in one month. It fits in two.** And it fits in two *safely*,
because the perishable half is free: harvest all the Kalshi bars first (§3), then
spend odds credits at whatever rate the reserve allows, since Odds API history
never expires.

Note the daily cap: 400/day at 20 credits a call is 20 calls a day, so ~3.3 days
of backfill per real day. 480 calls is ~24 days of wall-clock at the daily cap.
That is fine and is worth knowing before someone reports the loop as hung.

**Recommended phasing:**

| Phase | Scope | Credits | Fits |
|---|---|---|---|
| 0 | Kalshi bars + market metadata, full 80 days | **0** | Immediately, and **urgently** — this is the half that expires |
| 1 | 27 days, ~400 games, ~800 decisions | 27 × 6 × 20 = **3,240** | Comfortably inside one month's 7,000 reserve |
| 2 | Remaining 53 days, ~800 games | **6,360** | Second month — **exercised only if Phase 1's actionable count is non-zero** |

Phase 1 alone takes the pooled sample to n ≈ 1,000 decisions and the 95% upper
bound from 1.47% to **0.30%** — which already answers the question the build
exists to ask. Phase 2's marginal value is a further tightening to 0.125%, on a
question that was already decided. Do not pre-commit to it.

---

## 5. Decision

1. **Build it for the measurement goal, not the counter.** The prediction and its
   interval are in §1.2; the readings are pre-registered in §1.4. The gate does
   not open, and that was knowable before the loop was written.
2. **Ship schema v6 — `provenance TEXT NOT NULL DEFAULT 'live'` — before a single
   backfilled row is written.** The 21 call sites in §2.5 change with it, and
   `live.open_decisions` and `persist_if_changed` are not optional.
3. **The gate counts `provenance = 'live'` only**, for the reasons in §2.3.
4. **Harvest the free, perishable Kalshi half first**, then Phase 1's 3,240
   credits. Verify §3.3 before spending any of them.
5. **Fix `T` by the rule in §3.4 before looking at a single price**, and pin the
   reference bankroll per §1.4.

## What this does not establish

That the backfill is worth building at all if the answer is already 1.9 × 10⁻¹²
against. It is — but only because "measure the rate at n=2,400" is a different
and better question from "reach 300". If the next reader wants the counter, the
honest answer is that no amount of history supplies it, and this document exists
so that answer costs zero credits to obtain.
