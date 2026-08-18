# ADR 0043 — The gate counts engine fills, and v10 is why that had to be said out loud

**Date:** 2026-08-18
**Status:** Accepted
**Decides:** that `gate._fee_model_verified` counts rows in `fills` with
`source = 'engine'`, and no others.
**Does not change:** what that condition means, what it currently reports, or
any number it produces today. On every existing database the result is
byte-identical, because every row that exists is an engine row and there are
none.
**Does not touch:** `ORDERS_ARE_DRY_RUNS` (still `True`,
`backend/store/orders.py:129`), the 300-game `actionable` floor, or any other
gate condition. Nothing here arms the order path.
**Defers, explicitly and without rejecting:** whether hand-placed fills
*should* count. See "The question this does not answer".

## Context

`gate._fee_model_verified` asks whether `calculate_fee` matches what Kalshi
actually charged, over rows in `fills`:

```sql
SELECT COUNT(*) AS total,
       SUM(CASE WHEN ABS(fee_actual - fee_predicted) > ? THEN 1 ELSE 0 END)
FROM fills
WHERE fee_actual IS NOT NULL
```

Its own docstring records that the condition has never been able to fire: the
table has no producer, `total` is always 0, and the `MISMATCH` branch is
unreachable. It also states the rule that produced this ADR:

> Wiring a producer changes what the gate counts, which is a `partner` decision
> and an ADR, not a patch: this repo has a standing rule against altering the
> gate's inputs to make something easier.

**The query is unguarded because it never needed a guard.** When it was
written, `fills` could only mean *orders this engine placed* — the only writer
that could ever exist was the order path. The restriction lived in the table,
not in the SQL, and nothing had to say it out loud.

**Schema v10 (`79e42aa`) ended that.** It added
`source TEXT NOT NULL DEFAULT 'engine'` and dropped the `kalshi_markets`
foreign key on `ticker`, for one reason: `fills` is about to hold a second kind
of row — bets Joe places by hand, in the Kalshi app, polled back from
`/portfolio/fills`. The column exists precisely because the table stopped being
single-purpose.

**And those rows now exist.** Polled 2026-08-18T~03:00Z: `/portfolio/fills`
returned **25 real fills**, every one carrying a real `fee_cost`, and
`/portfolio/settlements` returned 22 settled positions. This repo had recorded
that endpoint as measured *empty*, twice, across eight query shapes. It is not
empty any more.

So the fee ground truth this gate condition has been waiting for is one
`INSERT` away — and that `INSERT` would move a live-trading interlock as a side
effect of switching on a logging feature.

## Decision

**`AND source = 'engine'`, in the gate query, landing before the first row with
any other source is ever written.**

### 1. This preserves the condition's meaning; it does not narrow it

The standing rule forbids altering the gate's inputs **to make something
easier**. Direction is the whole content of that rule.

The set this query was written to count is *engine fills*. Before v10 the table
enforced that by construction. After v10 it does not. Adding the filter keeps
the query counting the same set across a schema change that would otherwise
silently widen it. **It is a repair, not a relaxation** — and on every database
in existence it changes nothing at all, because the widening has not happened
yet.

**That argument is only available before the first non-engine `INSERT`.**
Afterwards, removing rows from a gate's denominator is indistinguishable from
tuning a gate to taste, whatever the commit message says. This is why the
ordering was treated as a hard prerequisite rather than a preference: the
filter and its test land first, and only then may the poller write.

### 2. An allowlist, never a denylist

`source = 'engine'`, not `source != 'venue_hand'`.

The denylist form passes every behavioural test and admits the *next* source
value by omission. A `backfill` or `import` source added a year from now must
be excluded until somebody decides otherwise, not swept in by a filter that
only knows about the kinds that existed when it was written.

This is the same family as the repo's rule that **unreadable resolves to
`None`, never `0`**: when the meaning of a value is unknown, refuse it rather
than guess. The test asserts the allowlist property directly, and the denylist
mutation is one of the two checked below.

## The question this does not answer

**Whether hand-placed fills should count is open, defensible, and deferred —
not rejected.**

The case for admitting them is good: arithmetic does not care who placed the
order. A `fee_cost` returned by Kalshi tests `calculate_fee` identically
whether the order came from `OrderPlacer` or from a thumb. If the gate were
being designed today it might well be written to accept any real fill.

Two reasons it is not settled here:

**It is not purely a loosening, and nobody knows which way it cuts.** If those
25 fills *mismatch* our model, the currently unreachable `MISMATCH` branch
becomes reachable and the gate becomes **stricter**. A logging feature must not
roll that dice in either direction.

**The reversible move comes first.** Filtering costs nothing and can be undone
by deleting one line. Admitting the rows spends the option and cannot be
un-spent, because the gate's history would then contain a period where it
counted them.

**The condition for reopening, named now so it cannot be chosen later:** after
the 25 fills have been analysed **off-gate** and it is known whether they match
`calculate_fee`. That analysis needs no permission from anyone and is the
largest fee sample this project has ever held.

**One trap for whoever does it.** Joe's realised fee rate across 22 settled
positions is **4.03% of stake**. At 50c on baseball, `k = 0.035` predicts 1.76%
and `k = 0.070` predicts 3.52% — his figure is above *both*. A pooled number is
not a finding until the parts agree: print the per-fill view (ticker, side,
price, contracts, `fee_cost`, implied `k`, taker/maker) and the largest
contributor's share before quoting 4.03% anywhere. At least three explanations
fit — a price mix nowhere near 50c, a settlement charge (which is **H4**, still
untested, ADR 0027), or the nine-fill baseball `k = 0.035` result not surviving
contact with 25 fills — and the pooled figure distinguishes none of them.

## Verification

Every guard checked by disabling it and watching the test fail
(`tests/test_gate_counts_engine_fills_only.py`):

| mutation | result |
|---|---|
| remove `AND source = 'engine'` entirely | **RED** — 4 failed |
| weaken it to `AND source != 'venue_hand'` | **RED** — 1 failed |

The second is caught by exactly one test, which is the point of writing that
test separately: the denylist is behaviourally correct for every source that
exists today and wrong for the first one that does not.

The suite also asserts the condition still reports `met=True` on a matching
**engine** fill. Without that, a filter excluding *everything* would satisfy
the two exclusion tests and look right — which is how a guard becomes
decoration.

## Related

- **ADR 0022** — the built-never-called classification `fills` belongs to. This
  ADR does not remove it from that list; the table still has no production
  writer as of this commit.
- **ADR 0027** — the cost headroom is an upper bound pending H4. The 22 settled
  positions plus an account balance are what could close H4, and that is
  another reason to analyse these rows off-gate rather than through it.
- **ADR 0041** — the demo sizes at the caps it deploys. Same shape of failure:
  a change one level away from where anyone was looking.
- The calibration pre-registration
  (`docs/measurements/2026-08-17-preregistration-joe-calibration-bet-log.md`)
  §9.6 recommends reusing `fills` rather than building a second table. That
  recommendation stands and is followed here; what it did not know about was
  the gate coupling, which is what this ADR adds.
