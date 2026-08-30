# The candidate scan, three index shapes — 2026-08-30

Instrument: `scripts/measure_odds_scan_index.py`, which imports
`runner.MATCH_CANDIDATE_SQL` rather than transcribing it, so the statement
timed here is the statement the pricing pass executes. Live btree sizes read
the same day with `scripts/inspect_live_db.py db-sizes`.

Command:

    .venv\Scripts\python.exe scripts\measure_odds_scan_index.py --rows 1500000 --repeats 7

## What this establishes

The **ordering** of three index shapes for the candidate scan, the query plan
each produces, and what the winning shape costs to build and to write into.

## What this does NOT establish

- **It is not the live table.** 1.5M rows, four sports at 55/20/15/10, ~350
  fixtures spread over −30d to +14d, eight bookmakers, two markets — modelled
  on the live shape, not sampled from it. The *ordering* is what this supports.
  The absolute milliseconds belong to this machine, this page cache and this
  distribution.
- **It does not reproduce the 27.7 s.** That came off the live box under a pass
  competing with the API's read connections. Nothing here recreates that
  contention, so this understates both the problem and the win.
- **The write cost has no concurrent reader.** Real amplification on live
  competes for the same connections and the same 2 GB of RAM.
- **The index size understates live.** Synthetic team names and event ids are
  short and uniform; real ones are neither.
- **`n` is one machine and one build of SQLite.** A different SQLite could pick
  a different plan. `tests/test_candidate_scan_plan.py` is what would catch
  that, not this document.
- **It says nothing about retention.** The index changes the constant. The
  growth term is untouched.

## Plan, by index shape

Machine-independent, and reproduced identically at 20,000 rows and at 1.5M:

    baseline   SEARCH odds_snapshots USING INDEX idx_odds_commence (commence_ms>?)
               USE TEMP B-TREE FOR DISTINCT

    narrow     SEARCH odds_snapshots USING INDEX idx_probe (sport_key=? AND commence_ms>?)
               USE TEMP B-TREE FOR DISTINCT

    covering   SEARCH odds_snapshots USING COVERING INDEX idx_probe (sport_key=? AND commence_ms>?)

The narrow form restricts the seek and leaves both remaining costs standing: a
table fetch per surviving row for the three projected columns, and the sort.
The covering form removes both, and the `DISTINCT` becomes a walk in index
order. **A plan without `USE TEMP B-TREE` is a different algorithm, not a
faster one.**

## Timings — 1,500,000 rows, 266 MB file

520,160 rows sit at or after the 24-hour floor across all sports. That is the
scan the predicate cannot avoid, to keep **73 distinct fixtures**.

| shape | plan | read cold | read warm p50 (n=7) | sweep write p50, 900 rows (n=15) | index | build |
|---|---|---|---|---|---|---|
| baseline | index + temp B-tree | 443 ms | **394 ms** (345–442) | 3 ms (3–10) | — | — |
| narrow | index + temp B-tree | 276 ms | **283 ms** (213–323) | 4 ms (4–11) | 47.0 MB | 1.8 s |
| covering | covering index | 1 ms | **0 ms** (0–0) | 7 ms (6–22) | 52.8 MB | 3.0 s |

**All three return the same 73 fixtures, compared as sets and not as counts** —
the script refuses to report otherwise. An index that changes the answer is not
a faster index.

### Reading the three columns together

- **The narrow form buys 28% and the covering form buys the query.** 394 → 283
  is a constant-factor improvement on the same algorithm; 394 → 0 is the sort
  and the table fetches ceasing to happen. This is the whole argument for
  paying five columns instead of two.
- **The write roughly doubles and stays trivial**: 3 ms → 7 ms per 900-row
  sweep. Against a read that was costing 394 ms every pass, and 27.7 s on live
  under contention, +4 ms per sweep is not a trade that needs deliberating.
- **The 0 ms is a skip, not a cache artifact.** It holds on a freshly opened
  read-only connection (1 ms cold), and the mechanism is visible in the plan:
  with the projected columns in key order the engine seeks past each run of
  duplicates instead of reading 286,000 index entries to find 73 answers.

### One correction to how this was first measured

The write column originally read **10 / 13 / 4 ms** — one 900-row batch per
configuration — an ordering in which the configuration with the *extra* index
was the fastest. That is not a result, it is the spread, and it was `n = 1`.
Repeating fifteen times per configuration produced the coherent 3/4/7. **This
repo's own rule caught it: read `n` before the effect size.**

## Live sizes, for the write-amplification cost

Read 2026-08-30 from `/data/cockpit.db` — 2,072,317,952 bytes on a 5 GB volume,
18.9 MB reclaimable by VACUUM:

    odds_snapshots      244,387,840   59,665 pages   13 columns
    idx_odds_event      136,421,376   33,306 pages   TEXT, TEXT, INTEGER
    idx_odds_commence    25,092,096    6,126 pages   INTEGER

**The live index will exceed the synthetic 52.8 MB.** `idx_odds_event` is 56%
of its table with two TEXT columns; the new one has four. Expect it between
`idx_odds_event`'s 136 MB and something under the table's own 244 MB — that is
a bracket, not an estimate, and **the real figure is to be read with `db-sizes`
after the first boot on v31 and recorded here.** Even the top of the bracket
takes the volume from ~41% to ~46%.

For context on the same volume, the two larger unretained btrees:
`fair_prices` 529,326,080 and `kalshi_quotes` 451,235,840, plus
`idx_quotes_ticker_time` at 398,708,736.

## The objection this had to answer

`fly.live.toml`'s `[[vm]]` comment, written after the box OOM-killed its own
loop on 2026-08-19: *"A larger index eats a larger cache."*

It is the right objection and the answer is not "the index is small". It is
that **this index reduces the page traffic of the query it serves**. Today the
pass drags ~520,000 table rows through a page cache that measured 27–135 MB
against a 1.5 GB database; afterwards it walks a contiguous index range and
touches the table not at all. Resident bytes go up by the size of the index;
bytes moved per pass go down by orders of magnitude.

## Follow-ups this does not close

1. **Read the real index size on live** with `db-sizes` after the v31 boot.
2. **Time the index build on live.** It took 3.0 s on 266 MB here, on a laptop.
   The health-check grace period was raised 40s → 120s to cover it, untested
   against the real box.
3. **`odds_snapshots` still has no retention rule.** `store/retention.py` says
   so in its own "what this does NOT do". This buys headroom, not a bound.
