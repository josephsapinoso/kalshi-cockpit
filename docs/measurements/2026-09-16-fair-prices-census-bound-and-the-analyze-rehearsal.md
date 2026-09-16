# The census bound is worth 322x on live, and the ANALYZE rehearsal is REFUSED on its own guard

**Date:** 2026-09-16
**Instrument:** `scripts/rehearse_fair_price_window.py`, run in the live
container at `5b91dae` (schema v44), against a `VACUUM INTO` copy of
`/data/cockpit.db`.
**Relates to:** ADR 0159 (the census is bounded, the index is refused),
ADR 0157 (an instrument may not charge its cost to the desk), ADR 0141 (a plan
diff cannot price an index), ADR 0144 (a single arm timing is not evidence),
ADR 0134 (the ladder scan keys on the confirmed stamp).

## What was being asked

ADR 0159 shipped a seven-day bound on both halves of `fair-prices-by-market`
and **refused** the index the work was approved to buy, on a modelled timing.
It deliberately did **not** ship `ANALYZE fair_prices`, which the model said
was the real lever, because statistics are a global planner input and the two
hottest readers of `fair_prices` — `parlays.CANDIDATE_SQL` and `runner.py`'s
per-outcome dedupe lookup — earned their plans on a statistics-free planner.

This run answers two questions on live's real data: **what did the bound
actually buy**, and **does `ANALYZE` cost anything elsewhere**.

## The live shape, read rather than modelled

    fair_prices                 10,131,885 rows
    inside the 7-day window        634,949 rows   (6.267%)
    distinct `market` values             8   h2h, spreads, totals,
                                             batter_hits, batter_home_runs,
                                             batter_rbis, batter_total_bases,
                                             pitcher_strikeouts
    sqlite_stat1                    ABSENT
    /data/cockpit.db         6,316,498,944 bytes
    SQLite                          3.46.1

**`sqlite_stat1` is absent, confirmed on the box.** Nothing in `backend/` has
ever run `ANALYZE`, so every plan the live machine chooses comes from SQLite's
built-in guesses. That is a fact about the whole database, not about this query.

**The bench's window fraction was wrong by 4.4x**, and in the direction that
matters: it modelled 1.42% of rows inside seven days, live holds 6.267%. A
bounded read on live therefore touches far more rows than modelled — which is
why the bench's predicted ratio and the measured one differ so much below.

## Result 1 — the bound, which is already shipped

    census, UNBOUNDED (what live ran until today)   208,289.1 ms
    census, BOUNDED   (ADR 0159)                        645.8 ms      322x

**208 seconds.** Every run of `fair-prices-by-market` was a three-and-a-half
minute read of the second-largest table on a box whose page cache holds at most
~27% of the file. ADR 0157's argument was that the cost lands on whoever
touches the desk next; this is the size of it, and it is much larger than
anyone had supposed. The bench's 19.6x prediction understated the live win by
more than sixteen times, for the reasons ADR 0141 gives — the benchmark box is
CPU-bound with the file partly resident, live is I/O-bound against 6.3 GB with
2.0 GB of RAM.

This is free, carries no schema change, and is live as of `45b60b9`.

## Result 2 — ANALYZE works exactly as predicted, on the query it was for

    census, bounded, no statistics      645.8 ms   SCAN fair_prices USING INDEX idx_fair_market_computed
    census, bounded, after ANALYZE      191.9 ms   SEARCH ... (ANY(market) AND computed_ms>?)   3.37x

The skip-scan fires on live, and **it fires despite the statistics being
wrong about the thing it turns on**. `PRAGMA analysis_limit=1000` sampled
`idx_fair_market_computed` as ~1,001 rows per distinct `market`, which implies
about 10,000 distinct markets; the truth is 8. The planner still chose the
skip-scan. That is worth recording because the obvious next thought — "use a
full `ANALYZE` for true cardinality" — is not supported by anything here, and
would cost a full scan of every index instead of 23.5 s.

`ANALYZE fair_prices` under that limit took **23.5 s** and wrote exactly **3**
`sqlite_stat1` rows, one per index on that table. The blast radius is as narrow
as the command implies.

## Result 3 — the blast radius, where it was actually feared

    CANDIDATE_SQL            1,177.0 ms -> 1,157.5 ms   1.02x   plan UNCHANGED
    runner dedupe lookup          0.03 ms                       UNMEASURABLE

`CANDIDATE_SQL` keeps its `MULTI-INDEX OR` over `idx_fair_market_computed` and
the partial `idx_fair_market_confirmed`, line for line. **ADR 0134's plan — the
one that ended three OOM kills and took `candidate_ms` from ~4,600 to 327 —
survives `ANALYZE`.** That was the question worth a twenty-minute copy, and the
answer is clean.

The runner's dedupe lookup ran in 0.03 ms and the instrument refused to give it
a verdict rather than reporting its ratio. A statement that fast cannot be
measured this way, and saying so is not the same as saying it is fine.

## Result 4 — section A's bound is a filter, and forcing an index does not help

    section A, bounded                       1,459.8 ms   SCAN odds_snapshots USING INDEX idx_odds_window
    section A, INDEXED BY idx_odds_commence  1,421.6 ms   SEARCH ... (commence_ms>?)

Within noise of each other. ADR 0159 §4 says section A's `commence_ms` bound
filters rather than seeks, and asked this run whether forcing
`idx_odds_commence` was worth it. It is not: the forced plan seeks the range
and then pays for a `TEMP B-TREE FOR GROUP BY` that the covering scan avoids,
and the two cancel. **Section A stays a filter and stays described as one.**

## Why ANALYZE is REFUSED anyway — the instrument's own guard fired

    section A, UNBOUNDED    2,812.0 ms -> 7,168.2 ms   0.39x   plan UNCHANGED

2.5x slower, with an **identical plan**. Statistics do not make a query slower
without changing its plan. So this is not a finding about `ANALYZE`; it is a
finding about the measurement.

**The rehearsal's before/after design is the weakness, and it is mine.**
`scripts/measure_fair_price_window_index.py` times its arms **round-robin in
one process**, and says in its own docstring why: the identical query over the
identical data read 1,283 ms in one session and 3,904 ms in the next, purely on
page-cache residency. The rehearsal does not do that. It runs every "before"
timing, then `ANALYZE`, then every "after" timing — roughly thirty minutes
apart, on a box that was simultaneously running the recorder and had just had
its cache scoured by three 208-second reads. ADR 0144 is titled *a single arm
timing is not evidence*, and this is that, twice.

So the honest position is not "`ANALYZE` regressed section A". It is
**"this instrument cannot tell a regression from drift, and it flagged one."**

`ANALYZE` is therefore **not shipped**. `SCHEMA_VERSION` stays 44 and schema
v45 stays unallocated. The guard is not overruled because the numbers on the
other rows are attractive — that is precisely the move the measurement rules in
`CLAUDE.md` exist to stop.

## What a successor run needs

Not a longer run — a different shape. `sqlite_stat1` can be dropped and
rebuilt on a copy, so the two states **can** be interleaved:

    for round in range(n):
        DROP TABLE sqlite_stat1   -> time every statement
        ANALYZE fair_prices       -> time every statement

That makes the comparison paired within a few seconds instead of across half an
hour, which is the only thing that would let a 2.5x on `section A (unbounded)`
mean anything. Worth noting that the arm in question is a statement **ADR 0159
deleted** — nothing will run the unbounded census again — so a successor may
reasonably drop it and keep the arms that still exist.

## What this does not establish

- **Nothing about live's absolute milliseconds after the change.** Every
  timing here ran against a `VACUUM INTO` copy, which is compacted: its
  b-trees are defragmented and its scans more sequential than live's. That
  **understates** the benefit of replacing a scan with a seek — the
  conservative direction — and leaves the before/after ratio intact, since
  both arms share the copy.
- **Nothing about the other tables.** `ANALYZE fair_prices` writes statistics
  for one table's indexes. Whether the rest of the database wants them is a
  larger question with a wider blast radius and has never been asked.
- **Nothing about statistics going stale.** One snapshot, against a table the
  recorder writes to continuously.
- **Nothing about concurrent load.** The copy is quiescent; live is not. Every
  figure is a floor on the real cost, never a ceiling.
- **Nothing about `fair-prices-by-market` being worth running.** This priced
  making it cheap.

## Cost of the run

Zero odds credits. One `VACUUM INTO` copy: 5,189,292,032 bytes in 816 s
(6.4 MB/s, 82.2% of the source after compaction), deleted afterwards, volume
back to 13,901,041,664 bytes free. `scripts/warm_read_path.py` was run
immediately after and reported the parlay read path warm in 12.4 s. The desk
stayed healthy throughout: `/api/health` ok, recorder inside its 900 s cadence
at every check, live quotes available.
