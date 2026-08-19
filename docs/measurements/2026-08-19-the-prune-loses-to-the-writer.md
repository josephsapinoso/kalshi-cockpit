# The prune cannot win: 2 to 1 against ungated, 5.7 to 1 as it is scheduled

Taken 2026-08-19 17:56-18:38Z on live (`a482fea`), from the pass lines
themselves. Follows `2026-08-19-window-store-leg-result.md`, which closed the
`link_discovered_events` question and named `leg_store_ms` as the largest
remaining leg without saying why.

**Read the CORRECTION at the bottom before quoting any row count from this
file.** Three numbers in an earlier draft came from a read-only SQLite
connection that could not see the write-ahead log and was 749 seconds stale.
They are kept, marked, because the way they were caught is reusable.

## What this establishes

That `kalshi_quotes` is growing at **+6.4M rows/day** on live; that the prune
ADR 0054 installed is losing to the writer by **5.7 to 1** as scheduled and
would still lose **2 to 1** if it were never gated at all; that the shortfall is
therefore structural and not a scheduling miss; that the gate nonetheless
switches the prune off during exactly the periods the writing is fastest; and
that `retention.py`'s own sizing argument is built on a growth figure **6x
below** what live is doing.

## What it does not

**It does not establish that the table size is what makes the store leg slow.**
That is the obvious mechanism and it is not measured here. `leg_store_ms` is two
calls timed as one lump, and the split that would separate them (`0c609de`) is
committed but **not deployed**. This incident has produced five plausible
stories and four of them were wrong; this file does not add a sixth.

It is 42 minutes, one machine, one slate -- 532 events with two sports in
season. The write rate is a function of `markets_quoted`, so an off-season
slate writes less and NFL and NBA both return within weeks.

And `n = 1` on the prune: exactly one prune fired in the window, so the prune
rate below is a rate over a single observation. The bound that does not depend
on it is given beside it.

## The arithmetic

Every number here is summed off `pass N ok:` lines in a `flyctl logs` capture,
de-duplicated on `(timestamp, kind, markets_quoted)` because flyctl replays its
buffer on reconnect. No database access, which is the point -- see the
correction.

```
window   17:56:13Z -> 18:38:12Z   (42.0 min)
passes   38   (3 full, 35 quote)

rows WRITTEN   226,601   ->   323,844/hour   7,772,261/day
rows PRUNED     40,000   ->    57,166/hour   1,371,973/day
NET                                          +6,400,288/day
```

**The prune is saturated, not idle.** Every prune this repo has logged deleted
exactly `40,000` rows -- two batches of `DELETE_BATCH = 20_000`, the ceiling
`DEFAULT_BUDGET_S = 30.0` buys. It is not failing to find rows; it is stopping
because it ran out of budget, every time.

**The generous bound also loses.** If the prune fired on *every* full pass --
4/hour at the 900s slow interval, which is its design case -- it would clear
160,000/hour against 323,844/hour written. Still **2 to 1 against**. So the
deficit does not depend on the `n = 1` rate above: there is no scheduling fix
that closes it, only a smaller write or a bigger delete.

## Why the prune does not run: the window gates it, and the window is open

Of the three full passes in the window, **one pruned**:

```
17:56:13Z  full  took_s   67.1  quotes_pruned      0
18:11:38Z  full  took_s   73.7  quotes_pruned      0
18:38:12Z  full  took_s  155.8  quotes_pruned  40000   unmatched_pruned 865
```

`runner.py:2247` skips the prune when `window_open`, and the comment is right
about why: *"Retention has no deadline; a bettable minute does."*

**A window was open for the whole of this capture**, which is worth stating
because the handoff assumed the opposite. `WindowStatus.is_open` is
`fixtures_fresh > 0` (`backend/odds/timing.py:758`) -- *fresh odds exist* -- and
not *a sweep slot is active*. The next sweep slot was 20:50Z throughout, and
`sweep_decision` said so on every line, which reads like a closed window and is
not one.

The behavioural proof needs no endpoint: `Tempo.interval_s` returns the fast
interval **only** when `window_open`, and 35 quote passes fired between full
passes 900s apart. A closed window would have produced full passes alone.

So the 18:38 prune is not the normal case -- it is the flicker. Odds age out at
`max_odds_age_s`, `fixtures_fresh` touches 0 between sweeps, and the prune gets
that gap and no more.

**The gate is not the root cause, and the order matters.** Ungated, the prune
still loses 2 to 1; the gate is what takes that to 5.7. Fixing the schedule
would slow the growth and not stop it. Both need saying, because "the prune is
switched off" is the memorable half and the arithmetic above is the load-bearing
one.

**But the gate does make a feedback loop, and it is worth naming separately.**
The window opens; the cadence goes fast; the writer produces 5,962 rows every
~25s; the prune is switched off for precisely that period. The busier the box
is, the less it prunes -- and pruning is what keeps it fast. Nothing in the
design breaks the loop, because both halves are individually correct.

## `retention.py` is sized against a growth figure 6x below live

The constant's own comment does the arithmetic honestly and reaches the right
conclusion from the wrong input:

> Throughput is `batches x DELETE_BATCH x passes-outside-a-window`, against
> **~1.30M rows/day** of growth. At one batch that is 1.58M/day -- a 274k
> margin that runs out at 7.75 open hours/day, and live measured 4.33 [...]
> At two batches the same break-even is ~15.9 open hours/day, which the
> schedule cannot reach.

The comment's arithmetic is self-consistent: at 1.30M/day of growth,
`160,000 x (24 - open_hours) = 1,300,000` gives `open_hours = 15.9`, exactly as
written. Only the growth input is wrong.

Measured write rate is **7.77M/day**. Put that through the same expression and
it has no solution:

```
160,000/hour x 24 hours  =  3.84M/day        the ceiling, at ZERO open hours
                            7.77M/day        measured writes
```

**There is no number of open hours at which two batches break even**, because
the prune's absolute ceiling -- every full pass for a whole day, never gated --
is half the write rate. The break-even is not tight, and it is not a schedule
problem. Raising the batch count moves this; nothing about *when* the prune runs
can.

Where 1.30M/day came from is not established here and should not be guessed at.
Note only that it is close to the measured *prune* throughput (1.37M/day), which
is the kind of coincidence worth checking before assuming a typo.

## What it costs already

- `took_s` **18.0-35.0s against a 15s cadence**, with the scheduler warning on
  nearly every pass that the worst-case confirmation gap is past Kalshi's 30s
  quote limit. An expired quote row looks exactly like a row nobody wanted.
- One full pass with a prune took **155.8s**. The recorder writes nothing for
  the duration.
- `leg_store_ms` **7.9-21.4s**, up from **3.8-10.0s** measured at 17:26-17:31Z
  on the same code, seven minutes after a restart. That is the correlation the
  split timer exists to test, and it is not a result yet.

## CORRECTION -- three row counts in the first draft were 749 seconds stale

The first draft opened with `kalshi_quotes` at 6,234,248 rows, 1,253,304 of them
past the 3-day retention, and a 1.55 GB file. Those came from

```python
sqlite3.connect('file:/data/cockpit.db?mode=ro', uri=True)
```

over `flyctl ssh console`. **A read-only connection cannot read the WAL** -- it
cannot create the `-shm` file it would need -- so it serves the last checkpoint
and reports it without complaint. The database is in WAL mode with a 51.6 MB
WAL outstanding.

It was caught by accident and then confirmed on purpose. Two reads eleven
minutes apart returned byte-identical counts *and* an identical file size, on a
table taking 5,962 inserts every 25 seconds. The check that settles it costs one
line:

```
now_ms       1787165285422
max_observed 1787164536481
lag_s              748.9
```

Every count in the body above is derived from log lines instead, which have no
such failure mode. **Do not read live row counts through a `mode=ro` URI**;
compare `MAX(observed_ms)` against the clock before believing any of them.

The correction moves the numbers in the *unfavourable* direction -- the true
table is larger than reported and the true write rate higher -- which is why it
was worth chasing rather than shrugging at.

## What this does not decide

The fix. There are at least three shapes and they are not equivalent: write
fewer rows (a quote row per pass per market, where most markets have not moved),
delete more per prune, or keep less than three days. The first changes what the
recorder records and needs its own ADR; the second and third are dials. Nothing
here says which, and the store-leg split should land first so that "the table
size is the cost" stops being an assumption.

## Two candidate causes of the store leg, eliminated without a deploy

Both were cheap, both were checked because they were about to become story six,
and both are recorded so that the next session does not re-derive them.

**`priceable_series` is not the untimed gap.** It is a `SELECT DISTINCT ...
WHERE last_seen_ms >= ?` over `kalshi_events` with no index on that column,
evaluated as an argument to `run_kalshi_pass` and therefore outside every leg --
the same growing-scan shape as `_match_candidates`, in the same file, on the
same day. `kalshi_events` holds **1,590 rows**. A full scan of 1,590 rows is
milliseconds. The timer added in `0c609de` stays, because eliminating a
candidate by measurement is what it is for, but the shape was a coincidence.

**The WAL is not growing.** A write-ahead log that grows until a checkpoint
would fit the within-the-hour doubling better than table size does, and it would
fit the abrupt transitions the previous file describes. It is flat:

```
18:47:40Z   cockpit.db 1546.4 MB   cockpit.db-wal 51.6 MB
18:59:20Z   cockpit.db 1546.4 MB   cockpit.db-wal 51.6 MB   (uptime 95 min)
```

Read off the filesystem rather than through SQLite, which is the whole lesson of
the correction above. Checkpointing is keeping the WAL at a steady size, and the
main file is flat because ~25% of it is freelist being reused -- so the disk
half of ADR 0054 still holds even while the row count climbs. **Those two facts
are compatible and it is worth saying so**: "the file has stopped growing" is
not evidence that the table has.

**And the table-size story itself is weaker than it looks.** `leg_store_ms` was
3.8-10.0s at 17:26-17:31Z and 7.9-21.4s at 17:56-18:38Z, but the table grew only
~5-8% between those readings. A 5% larger table does not double insert cost.
Either the relationship is not linear in the region that matters -- plausible,
if the index has outgrown the page cache -- or something else moved. **This is
the sixth candidate mechanism on this incident and it gets no more credit than
the five before it.** The split timer decides it.
