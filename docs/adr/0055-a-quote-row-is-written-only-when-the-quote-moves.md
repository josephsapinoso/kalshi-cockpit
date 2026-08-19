# ADR 0055 — A quote row is written only when the quote moves, and freshness moves to its own column

Status: **accepted**, 2026-08-19. Joe chose this over tuning the prune, having
been given both.

Supersedes nothing. Sits on top of ADR 0054, which installed the retention
window this decision exists because it cannot win.

## Context

Two measurements, taken the same afternoon, and neither is a judgement call.

**The prune cannot win at any schedule.**
`docs/measurements/2026-08-19-the-prune-loses-to-the-writer.md`: live writes
**7.77M rows/day** into `kalshi_quotes`. The prune's absolute ceiling -- four
full passes an hour, every hour, never once skipped for an open window -- is
**3.84M/day**. It is not a tight margin and it is not a scheduling miss: there
is no number of open hours at which the arithmetic closes. Measured throughput
as actually scheduled is 1.37M/day, so the table is growing **+6.4M rows/day**.

**84.5% of what it writes is a copy of the row before it.**
`docs/measurements/2026-08-19-how-often-a-kalshi-quote-actually-moves.md`: two
independent methods agree. Every field `store_quotes_from_discovery` writes,
other than the ticker and the clock, is byte-identical to the previous
observation for the same ticker on 84.5% of consecutive pairs.

So the writer is producing five rows of no new information for every one that
carries any, and the cleanup was sized for a sixth of the load.

## Decision

**`kalshi_quotes` becomes a change log.** A row is inserted only when the quote
differs from the last stored quote for that ticker.

**`confirmed_ms` is added to `kalshi_quotes`**, and the unchanged case updates it
in place on the existing row rather than inserting a new one.

The two columns answer two different questions and the whole design is that they
are not the same question:

| column | means | who reads it |
|---|---|---|
| `observed_ms` | when this price **first appeared** | drift, CLV, retention |
| `confirmed_ms` | when we last saw it **still true** | the staleness gate |

**The recorder-liveness check moves off `kalshi_quotes` and onto the `meta`
table**, written once per pass.

## Why the naive version of this is a product outage

Stated plainly because it is the reason `confirmed_ms` exists and not a detail:

`runner.py:1092` and `runner.py:1488` compute

```python
kalshi_quote_age_ms = stamp - int(quote["observed_ms"])
```

from `latest_kalshi_quote`, and `core/suppression.py:200` refuses the row when
that exceeds **30s**. If unchanged quotes simply stopped being written,
`observed_ms` would freeze at the last price change -- and a college-football
spread that has not moved in an hour would present as a **one-hour-old quote**
and be suppressed as stale.

That is not an edge case. It is **84.5% of the slate**, and the markets it hits
hardest are precisely the ones the measurement shows are quietest. The tool
would go quiet and every individual component would still be behaving as
documented.

**A quote that has not moved is not a stale quote, and the schema could not tell
those apart.** That is the actual defect being fixed here; the row count is the
symptom that made it visible.

## Every reader, and what happens to it

The enumeration in `store/retention.py` is reused rather than redone, with the
two it does not cover added.

| reader | uses | effect |
|---|---|---|
| `runner.latest_kalshi_quote` -> suppression | newest row for a ticker | **changes**: reads `COALESCE(confirmed_ms, observed_ms)` |
| `routes.py:537` recorder health | newest row overall, by `id DESC` | **changes**: reads the `meta` heartbeat |
| `slate.kalshi_drift_tenths` | a one-hour window | **changes, and this ADR got it wrong first** -- see below |
| `clv_signal.py` | `observed_ms <= created_ms ORDER BY DESC LIMIT 1` | unaffected. Already "the most recent quote at or before this time", which is the correct reading of a change log |
| `routes.py:3264` `price_is_current` | quote age vs the 30s limit | **changes**, same substitution as the suppression gate |
| retention `DELETE` | `observed_ms` vs the window | **changes**: filters on `COALESCE(confirmed_ms, observed_ms)`, and now deletes far less |

`notify/alerts.py:472` was checked and does **not** read this table; its
docstring already records why, and that reasoning is unchanged.

### The drift column, which this ADR first recorded as unaffected

The first version of the table above said `kalshi_drift_tenths` was *"unaffected,
and slightly more honest"*. That is wrong, and it is left in the history because
it is the same class of mistake as the staleness one and was caught only by
reading the function instead of reasoning about it.

`slate.py` collects rows **inside** the window and returns `None` when there are
fewer than two:

```sql
WHERE ticker = ? AND observed_ms >= ?   ORDER BY observed_ms DESC
```

Today a market that has not moved for an hour has ~240 identical rows in that
window, so `latest - earliest` is **0** -- and 0 is the truthful answer: the
price did hold steady. Under a change log the same market has **one** row, or
none, and the function returns `None`. So the drift column would go blank for
exactly the 84.5% of markets whose drift is most confidently known.

The docstring's rule -- *"`None` ... Never 0, which would assert the price held
steady"* -- is about not fabricating steadiness from missing data. Turning a
measured steadiness into `None` breaks the same rule from the other side.

**The fix is a better query than the one there now**, and it is an improvement
independent of this ADR: the baseline should be *the most recent quote at or
before the start of the window*, not the oldest quote inside it. Today, a market
first quoted twenty minutes ago reports twenty minutes of movement as an hour's
-- a bug that exists in the current code and that nobody has hit because the
copies hid it.

```
baseline := latest row with observed_ms <= now - window
            else the oldest row inside the window
latest   := the most recent row for the ticker
None     := only when baseline and latest are the same observation and
            no row precedes the window -- i.e. genuinely one data point
```

A market steady across the whole window then has a baseline at or before the
window start, `latest` is that same row, and the answer is **0** -- measured,
not fabricated.

### Retention would delete the live quote, and that is the same bug again

`prune_quotes` selects on `observed_ms` against the three-day window. Under a
change log, a market whose price has genuinely not moved in three days has one
row, with an `observed_ms` three days old and a `confirmed_ms` from this pass --
and the prune would delete **the current quote**.

The market then has no quote at all until the next pass rewrites it, which means
at least one pass where `latest_kalshi_quote` returns `None` and the market
cannot be priced. Self-healing, and still wrong: the row deleted is the only
record of a live price.

So retention filters on `COALESCE(confirmed_ms, observed_ms)` -- *keep what was
recently confirmed*, not *keep what was recently written*. Three readers now
make that same substitution, which is the tell that the column was the missing
concept rather than a patch: **every question about whether a quote is still
good is a question about confirmation, and every question about the price
history is a question about observation.**

## What was rejected

**Tuning the prune (raise `DELETE_BATCH`, raise the budget, cut retention
below three days).** It does not close the gap -- the ceiling is half the write
rate before any of those dials are touched -- and each of them makes the stall
worse. A full pass that prunes already takes **155.8s**, during which the
recorder writes nothing. Buying disk with latency, on a box that is already
missing a 15s cadence, is the wrong direction.

This is a rejection of *"dials instead of"*, not of *"dials as well as"*. See
the open item below.

**A separate `kalshi_quote_state` table**, one row per ticker, holding the
current quote and its confirmation time. It is the better design on cost: the
unchanged path would touch a ~25k-row table that stays entirely in page cache,
where the decision above needs an index seek into the 476 MiB
`(ticker, observed_ms DESC)` btree for every market on every pass. It was
rejected **for now** because it repoints every reader instead of two, and
because the cost it optimises is not yet measured.

**The condition for revisiting it is written down rather than left to taste:**
if `leg_store_ms` does not fall roughly in proportion to the rows removed once
this ships, the seek is the remaining cost and the state table is the answer.
The split shipped in `0c609de` (`leg_store_upsert_ms` / `leg_store_quotes_ms`)
is what makes that readable.

## What this does not do

**It does not make the saving permanent.** 84.5% is a property of the slate,
not of Kalshi. College football and NFL are 57% of today's markets at 98-99%
unchanged because nobody is trading a game days away; today's baseball runs
51-74%. On an all-active slate the write rate lands near **3.5M/day against the
3.84M/day ceiling** -- a 9% margin on a prune that is skipped whenever a window
is open. **The prune's ceiling is still worth raising**, and this ADR does not
license closing that item.

**It does not shrink the file**, for the reason ADR 0054 already gives: freed
pages go on the freelist. The measured flatness of `cockpit.db` at 1546.4 MB is
freelist reuse and was never evidence that the table had stopped growing.

**It does not measure the store leg.** Whether table size is what makes
`leg_store_ms` cost 8-21s is still an assumption -- the sixth on this incident,
of which four were wrong. It is not a premise of this decision: the write rate
is a problem on its own arithmetic whatever the store leg turns out to be.

**It does not change what a quote means to a reader that asks correctly.** "The
quote at time T" is unchanged. "A row exists near time T" was never a guarantee
the schema made, and any future reader assuming it will now be wrong sooner.

## Migration

`confirmed_ms` is added nullable, and every reader uses
`COALESCE(confirmed_ms, observed_ms)`. Rows written before this ADR carry NULL
and continue to read exactly as they did, which makes the deploy reversible
without a backfill: old code ignores a column it does not know about, and new
code reads old rows correctly.
