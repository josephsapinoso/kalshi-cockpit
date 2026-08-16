# The §A8.2 quote-join disagreement was a defect in the check — and it should have failed P1

**Question asked:** the 2026-08-16 interim look reported that 1,826 of 3,692 rows
(49.5%) carry a joined quote whose derived ask disagrees with the stored
`entry_ask_tenths`. Does it bias `gamma_hat` (−0.741) and therefore `beta_hat`
(−0.141)?

**Answer: no — but the reason matters more than the answer, and it is not
comfortable.** There is no disagreement; the 1,826 flagged rows are exactly the
1,826 `side='no'` rows and the check was side-blind. `beta_hat = −0.1412` is
arithmetically unchanged.

**Read this before the rest.** §A8.2 makes that counter the **P1 statistic**.
Under the side-blind check `matched / total = 1866 / 3692 = 0.5054`, which is
below the 0.90 floor, so **the 2026-08-16 interim look should have printed
`P1 FAILED. The primary analysis does not run.` and should never have reported
`beta_hat` at all.** It did not, because the harness was still computing the
superseded P1. So this correction **converts a would-be P1 failure into a P1
pass** — a correction in the direction that rescues the published number, which
is the class of correction that earns extra scrutiny rather than less.

**Harness:** `scripts/measure_quote_join_bias.py`
**Input:** `docs/measurements/2026-08-16-clv-signal-pull.json.gz`, the same
3,692-row dump the interim look ran on, `truncated: false`. No new extraction and
nothing re-pulled — a re-reading of the published population, not a second sample
of it.

## The defect, and it is in the instrument

`entry_ask_tenths` is the price paid for the side actually taken. Verified in the
**writers**, not merely in a reader's docstring: `backend/runner.py:899` (props)
and `backend/runner.py:1290` (moneyline) both call `ask_for_side(quote, side)`,
and `backend/store/db.py:620-631` is unambiguous —

```python
if side == "yes": return derive_yes_ask(row["no_bid_tenths"])   # 1000 - no_bid
if side == "no":  return derive_no_ask(row["yes_bid_tenths"])   # 1000 - yes_bid
```

`backend/engine.py:245` copies that to `entry_ask_tenths`. There is no third
writer. **The data is right and the check was wrong** — the diagnosis does not
invert.

`scripts/run_signal_test.py:_quote_disagrees` compared **every** row against
`1000 − no_bid_tenths`, the YES-side ask. The two sides' asks differ by the
market width, so it flagged every NO row by construction — always, not
occasionally.

**And §A8.2 had already written the correct comparison, three weeks earlier:**

```sql
CASE r.side
  WHEN 'yes' THEN ((1000 - q.no_bid_tenths)  = r.entry_ask_tenths)
  WHEN 'no'  THEN ((1000 - q.yes_bid_tenths) = r.entry_ask_tenths)
END AS quote_matches_entry,
```

This was not a subtle case nobody had considered. **The implementation deviated
from a specification that was written down correctly and on time.** That is a
stronger and less flattering account than "a reader checked the YES case and
stopped", and it is the one the record supports.

The identity is exact on the record — 1866/1866 and 1826/1826 — though see
"what would have falsified this" for how little that proves.

## What the join actually is, and why the clean number is not evidence

```
rows                          3692
§A8.2 matched                 3692
§A8.2 quote_mismatch             0
§A8.2 no_quote                   0
P1 = matched / total        1.0000  (floor 0.90)  PASSES
```

**Staleness is 0 on every row, and that is a fact about the writer, not the
record.** `created_ms` is not independently clocked. `run_once`
(`runner.py:1911`) and `run_quote_pass` (`runner.py:2043`) each compute
`stamp = now or now_ms()`, pass `now=stamp` into `store_quotes_from_discovery`,
which inserts `kalshi_quotes.observed_ms = now` (`runner.py:1842-1851`), then
pass **the same `stamp`** into `run_pricing_pass`, which writes `created_ms`.
`observed_ms` and `created_ms` are the same Python variable.

Confirmed independently of the signal pull, against all 10,288 recommendations
ever written (`docs/measurements/2026-08-16-decision-dump.json.gz`):

```
distinct kalshi_quote_age_ms : [0]   on all 10,288 rows
stale_kalshi_quote rows      : 0     -- the suppression check has never fired
```

So "every joined quote is stamped at exactly `created_ms`" is true and nearly
vacuous. It holds on 10,288 rows, not 3,692, and it could not have come out any
other way.

Two supporting checks, both exact on all 3,692 rows, and both retained because
they would have caught a genuinely different failure:

- `(1000 − no_bid) − yes_bid == (1000 − yes_bid) − no_bid`, so the registered
  `half_spread_tenths` is **side-symmetric** and is the correct control for both
  sides. The disagreement was in the check; it would have been a far worse
  finding in the control.
- No row has a negative half-spread. Range 5.0 to 320.0 tenths, median 5.0.

## The fits

Same estimator (`backend.analysis.signal_test.fit`). **Three distinct fits, plus
two rows that are algebraically the baseline:**

| fit | n | G | `beta` | se | `gamma` | interval |
|---|---:|---:|---:|---:|---:|---|
| **REGISTERED (baseline)** | 3692 | 199 | **−0.1412** | 0.0478 | −0.7407 | [−0.3342, +0.0517] |
| side=yes stratum | 1866 | 199 | −0.0948 | 0.0357 | −0.7726 | [−0.2391, +0.0495] |
| side=no stratum | 1826 | 199 | −0.1186 | 0.0475 | −0.3586 | [−0.3102, +0.0731] |
| *ALT CONTROL (tautology)* | 3692 | 199 | −0.1412 | 0.0478 | −0.7407 | [−0.3342, +0.0517] |
| *FRESH ≤ 60s (tautology)* | 3692 | 199 | −0.1412 | 0.0478 | −0.7407 | [−0.3342, +0.0517] |

**ALT CONTROL carries zero information and is labelled as such.** Registered
`hs = ((1000−no_bid) − yes_bid)/2`; ALT `hs = (entry_ask − same_side_bid)/2`,
which on a YES row is `((1000−no_bid) − yes_bid)/2` and on a NO row is
`((1000−yes_bid) − no_bid)/2` — the same value. It is identical **whenever
`ask_error == 0`, which is the thing under test.** Printing it agreeing is a
restatement of the tautology, not a demonstration about it. `FRESH ≤ 60s` is the
whole population for the same reason.

Both side strata are negative, so the pooled figure is not one side carrying the
other. `side` is **not a registered cut** and this table is a diagnostic.

## The channel

```
corr(edge, half_spread)   -0.1428
corr(edge, ask_error)     undefined -- ask_error is constant at +0
```

A mismeasured control biases a coefficient only through its correlation with that
regressor. There is no error to correlate.

## What would have falsified this

**Almost nothing could have, and that is the honest limit of the result.**

`entry_ask_tenths` is `1000 − opposite_bid` read off a `kalshi_quotes` row; the
extraction re-joins that same row (same-pass insert) and recomputes
`1000 − opposite_bid`. The 3692/3692 identity is `1000 − b == 1000 − b`. **It is
not an independent observation of anything.**

The one live failure mode it could have caught: a pass that priced a ticker for
which it stored no quote row — only one bid readable, so the extraction's
`yes_bid IS NOT NULL AND no_bid IS NOT NULL` subquery skips the fresh row and
reaches back to an older one. 0/3692 says that never occurred. That is the entire
discriminating power, and a reader must not take 0/3692 as a strong pass.

**The measurement that would actually clear the join:** for each recommendation,
count how many `kalshi_quotes` rows exist for that ticker with
`observed_ms < created_ms` whose bids *differ* from the joined row's. If that is
near zero, the join had no wrong answer available to give. That needs the
`kalshi_quotes` table and is not in this dump.

## What this changes

1. **`beta_hat = −0.1412` is arithmetically unchanged.** The counter gates
   whether the fit may be reported; it is not a regressor and does not enter
   `fit()`. The direction decided on 2026-08-16 is unaffected.
2. **`scripts/run_signal_test.py` now implements §A8.2's P1**, not the superseded
   one: it prints all **three** counts (`matched` / `quote_mismatch` /
   `no_quote`), gates on `matched / total`, and prints §A8.2's mandated
   disclosure sentence itself when `quote_mismatch / total > 0.05` — rather than
   trusting a write-up to remember it. On this record P1 = 1.0000 and PASSES.
3. **`_quote_disagrees` is side-aware**, matching the registered SQL.
4. **`tests/test_quote_join_disagreement.py` — 19 tests, and nothing covered any
   of this before.** Verified by mutation twice: restoring the side-blind body
   turns 5 red (all NO-row cases; no YES-row test moves), and folding
   `quote_mismatch` into `matched` turns 3 red including the P1 arithmetic.

## Is correcting this an amendment to the registration?

**No — but not for the reason first given.** The original argument here was that
the counter is "a diagnostic that touches no verdict branch". **That is false:
§A8.2 makes `matched / total` the P1 statistic, and P1 refuses the primary
analysis.**

The correct argument is narrower and stronger. §A8.2 registered the exact
side-aware expression before any data was seen. The implementation was
**non-compliant with the registration from the start**, and bringing it into
compliance restores the registered behaviour rather than changing it. Nothing in
the decision rule moved, and the fit is byte-identical before and after.

**The disclosure that owes with it:** the correction moves P1 from 0.5054 (FAIL)
to 1.0000 (PASS). A reader is entitled to know that the harness was fixed in the
direction that permits the number it had already published.

## What this does NOT establish

- **It cannot change the registered verdict, in either direction.** The look is
  taken on data already seen, `side` is not a registered cut, and §6 reads the
  REGISTERED line only. The verdict remains **UNRESOLVED** at G = 199 and may not
  be reported as "no signal."
- **It does not clear the join in any strong sense.** See "what would have
  falsified this". Both compared columns derive from one database row; this is a
  re-derivation of the writer's own arithmetic, not an independent check.
- **Staleness = 0 is forced by the writer, not observed** (`runner.py:1911`,
  `2043`, `1842-1851`). It holds on all 10,288 rows in the record's history, and
  the extraction's exclusion of `stale_kalshi_quote` therefore removes exactly 0
  rows. A future writer that decoupled the two clocks would invalidate this
  section, not merely date it.
- **`observed_ms` is our local REST-return clock, not a venue timestamp.** How
  old the book data was when Kalshi handed it over is unmeasured and unmeasurable
  from this dump.
- **The harness is still not fully §A8.2-compliant.**
  `backend/analysis/signal_test.py:coverage` — used by `fit()`'s other callers
  and by `tests/test_signal_test.py` — still implements the superseded
  non-NULL-half-spread statistic and is still documented in that module as "P1's
  statistic". Only `scripts/run_signal_test.py` reads the registered one. The
  counter is fixed; one of the two places that describe the gate is not.
- **It says nothing about the excluded `stale_odds` population, which is larger
  than previously written.** Recomputed from the decision dump: of **8,658**
  scored horizon-0 rows, **4,971 (57.4%)** carry `stale_odds` among their
  reasons and the extraction's `instr` predicate drops **all** of them. The
  figure **3,127** quoted elsewhere is the count whose *sole* reason is
  `stale_odds`, and using it understates the excluded population by ~40%.
- **It says nothing about `gamma_hat = −0.741` being the right size.** The
  control is correctly sourced; that it is large remains unexplained, and a
  negative half-spread coefficient is not obviously the sign a reader would
  predict.
- **Nothing about tradeability, fees, or fill.** Same limits as the parent test.
