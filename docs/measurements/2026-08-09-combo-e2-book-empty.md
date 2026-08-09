# E2: is a combination's list quote backed by an order book?

Date: 2026-08-09
Status: **pre-registered — everything above `RESULTS` was committed to git
before a single order book was read.**

## The pre-registered question

E2 was fixed at the end of `2026-08-09-combo-leg-echo.md`, before this session
existed, and is run here as written:

> **E2.** For each combination carrying a `yes_ask` on `/markets`, read
> `/markets/{ticker}/orderbook` in the same pass. Record (a) whether the book is
> non-empty, (b) whether `1 − best_no_bid` reproduces the list `yes_ask`, and
> (c) whether any level derives to within 2c of a leg's cost. Report the rate of
> each with its `n`, split by scope, and report the **book-empty rate first** —
> if a material share of quoted rows have no book, the harvest's population is
> not what it was taken to be, and that supersedes every other question here.

### Why it matters

An exploratory look at 8 live echo combinations found **3 with an empty book
while `/markets` quoted them**, and one reading `0.0000 / 1.0000` on
`/markets/{ticker}` for 18 consecutive polls against a list quote of 0.463.
Every combo price this project holds — **all 2,116 rows of the harvest** — came
from the list endpoint. Whether any of them was backed by resting size at the
moment it was read has never been checked.

That exploratory 3-of-8 is `n = 8`. It is not a rate; it is the reason to
measure one.

## Operational choices, fixed now

E2's paragraph fixes the three quantities and the reporting order. It does not
fix the thresholds, the sample size or the selection rule, so those are written
here, before collection, and are not re-tuned afterwards.

Harness: `scripts/measure_combo_book_presence.py`. Free, **unauthenticated**
(both `/markets` and `/markets/{ticker}/orderbook` return 200 with no
signature), read-only. No order, no cancel, no lookup, **zero Odds API
credits**, no credential in the process.

### Definitions

| Term | Fixed as |
|---|---|
| eligible combination | a `/markets` row with non-empty `mve_selected_legs` and a readable `yes_ask` by `measure_combo_correlation.readable_quote` (`0 < ask < 1`). A `0.0000` ask is not an ask. |
| **book empty** | zero levels on `yes_dollars` **and** zero on `no_dollars` |
| NO-side empty | zero levels on `no_dollars` — reported separately, because `yes_ask` derives from the NO bid alone |
| **reproduces** | `\|(1 − best_no_bid) − list_ask\| ≤ 0.0005` — equality on the deci-cent grid. The raw difference is recorded for every row regardless. |
| derived yes price of a level | `1 − p` for a NO level at `p`; `p` itself for a YES level |
| **echo in book** | some level's derived yes price is within `ECHO_TOLERANCE` = 0.02 of some leg's `cost_to_buy_leg` |
| `cost_to_buy_leg` | **imported** from `measure_combo_correlation`, not re-implemented: `yes → yes_ask`, `no → 1 − yes_bid` |

`ECHO_TOLERANCE` is 0.02, the same constant `analyse_combo_domination` and the
leg-echo harness use, unchanged.

### Sampling

| | |
|---|---|
| Discovery | one `GET /markets?series_ticker=…&status=open&limit=1000` per series in `DISCOVERY_SERIES`, newest-first, **no paging** |
| Selection | the **first 20 eligible rows in discovery order** — fixed, not sampled at random, and not re-chosen after seeing a book |
| Leg prices | one batched `?tickers=…` read of every leg of those rows |
| Books | one `/markets/{ticker}/orderbook?depth=10` per selected row |
| Contemporaneity control | one batched re-read of the same combinations' list quotes, **after** the whole book pass |
| Budget | **2 + 1 + 20 + 1 = 24 Kalshi calls**, zero Odds API credits |

### Denominators, fixed now

Getting these wrong is how a rate flatters itself, so each is written before the
data exists:

- (a) is over **every scored row**.
- (b) is over rows **with a NO bid at all**. A row with no NO side has nothing
  to reproduce the ask with; counting it as a reproduction failure would
  double-count the book-empty rate inside (b).
- (c) is over rows with a **non-empty book and every leg priceable**. An
  unpriceable leg is excluded and counted, never scored as "no echo".

### Uncertainty

Every rate is reported as `k/n` with a **95% Wilson score interval**. At `n =
20` the normal approximation is not licensed by CLAUDE.md's "≥5 expected
outcomes on each side" rule, and the interval — not the point estimate — is the
result. Scope cells will be smaller still and are printed with their counts.

### Envelope guard, and why it is not a second copy

`ORDERBOOK_KEY` (`orderbook_fp`) and `MalformedOrderbookResponse` are
**imported** from `backend.kalshi.rest`. A missing envelope **raises and aborts
the row**; aborted rows are reported separately and are never counted as empty.

This is the whole hazard of this measurement. `KalshiRestClient.orderbook` once
read `payload["orderbook"]` and returned `{}` for every market on the exchange
without erroring — a book-empty rate of 100% that was really a key typo. **An
empty book is a legitimate state on this venue; a renamed field is not.**

### What this measurement will not establish

Fixed in advance so it cannot be quietly narrowed later.

- **Nothing about the 2,116 stored rows themselves.** Those markets are gone.
  This measures the population they were drawn from, on a later slate, and
  transfers only to the extent that population is stable.
- **Nothing about why a book is empty.** Replica lag between two endpoints, a
  quoter posting and pulling inside the gap, and a list price never backed by
  resting size all predict the same observation.
- **Nothing about tradeability.** These rows are provisional, with zero volume
  and zero open interest. A resting level is not a fill.
- **Nothing about non-eligible combinations.** Rows with no readable ask are
  excluded by construction.
- **Newest-first, so youngest.** Only the newest combinations carry a quote at
  all. If book presence grows with age, this rate is a lower bound and nothing
  here separates the two.
- **One slate, one window of seconds.** Not an edge: no fair value is computed
  and no combo fee model is verified.

---

## RESULTS

*(Not yet run. This section is written after collection and nothing above it
changes.)*
