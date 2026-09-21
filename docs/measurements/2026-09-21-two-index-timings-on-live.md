# Two index timings on live — 2026-09-21 ~01:30Z

Tickets #88 (story #86) and #91 (story #89), taken in one pass after the
deploy of `62bf5d5`. Live `git_sha` confirmed `62bf5d5` against `origin/main`
before either run.

**Both readings overturn the premise of the ticket that asked for them, in
opposite directions.** #87's `WHERE` clause bought nothing measurable; and the
479.6 MB index #89 is about is not the one the live planner uses.

Common census, read at the same instant by both instruments:

```
odds_snapshots                    5,426,214 rows
  distinct odds_event_id              1,292
event_links                           3,948 rows
  distinct odds_event_id                930
recommendations (clv_scored_ms NULL) 29,906
venue_settlements                       151
```

**5.4 M rows against 1,292 distinct fixtures.** That ratio is the reason for
the first result below and it was in nobody's arithmetic.

---

## 1. #88 — the scoring candidate scan: the `WHERE` clause bought nothing

`inspect_live_db.py scoring-candidate-timing`. One connection, one instant,
bounded arm first and cold, unbounded arm after and warm — the unflattering
order for the fix.

| # | statement | rows | ms |
|---|---|---|---|
| 1 | BOUNDED whole scan (deployed, post-#87) | 249 | **489.3** |
| 2 | BOUNDED `odds_snapshots` GROUP BY alone | 930 | 416.9 |
| 3 | UNBOUNDED GROUP BY alone (pre-#87 text) | 1,292 | 393.1 |
| 4 | UNBOUNDED whole scan (pre-#87 text) | 249 | **423.5** |

**The row sets agree: 249 against 249.** `tests/test_scoring_candidate_scan_is_bounded.py`
proves on a seeded database that the bound cannot change the answer; it now
holds on 5.4 M live rows as well.

**Verdict: no measurable improvement, and the direction is against the fix.**

The claim this reading supports is the negative one. It does **not** support
"the unbounded version is faster": 393–489 ms across four single runs on a
shared machine, with the bounded arm carrying the cold-cache penalty by
design, cannot separate a real 60 ms from noise plus cache. What it can say
is that **no improvement is visible at this size**, which is what the ticket
asked.

**Why, from the plans.** Both arms ride the same covering index:

```
BOUNDED    SEARCH odds_snapshots USING COVERING INDEX idx_odds_event_commence (odds_event_id=?)
           + LIST SUBQUERY: SCAN event_links USING COVERING INDEX
UNBOUNDED  SCAN  odds_snapshots USING COVERING INDEX idx_odds_event_commence
```

`idx_odds_event_commence` is `(odds_event_id, commence_ms)` — exactly the
shape this aggregate needs. So the "unbounded" arm was never a table scan: it
is a sequential scan of a covering index that collapses 5.4 M entries into
1,292 groups. The bounded arm replaces that with 930 index seeks plus a scan
of `event_links`, and **930 seeks are not cheaper than one ordered pass.**

**#87's stated justification does not survive this.** Its premise was that
"the planner had to aggregate every row of `odds_snapshots` before the outer
joins narrowed anything." The aggregate was real; its cost was not, because
the covering index was already there. This is the scar behind `2e66f36`
(*"the plan was never the cost"*) repeating with the sign flipped — there, a
plan said an index was unneeded and the stopwatch disagreed; here, a plan
shape (SEARCH rather than SCAN) was taken as the win and the stopwatch says
there wasn't one.

**#87 should not be reverted on this reading, and the reason is not
sentiment.** The bound is correct (it cannot change the answer, proven twice
now), and its cost scales with `event_links` while the unbounded arm's scales
with `odds_snapshots`. Today those are 930 and 1,292 groups over 5.4 M rows;
the day distinct fixtures grow faster than links, the bound starts paying.
**What should not survive is the claim that it bought something today.**

**Reclassification, per the rule.** `scoring.py`'s statement is *not* demoted
to cheap on this reading either — 489 ms is not free, and the instrument
itself stays `WALKS_THE_FILE` permanently because its unbounded arm exists to
walk.

---

## 2. #91 — `idx_odds_event` is not the index doing the work

`inspect_live_db.py odds-snapshots-latest-price-timing`, the instrument #90
built. It times the two-statement "latest price" shape all four of
`backend/runner.py`'s `book_quotes_for_event`, `prop_quotes_for_event`,
`spread_quotes_for_event` and `totals_quotes_for_event` run, on the busiest
`(odds_event_id, market)` pair — 12,270 rows for that pair, 23,996 for the
event.

| # | statement | rows | ms |
|---|---|---|---|
| 1 | WITH INDEX — whole latest-price read | 50 | **1.5** |
| 2 | WITH INDEX — `MAX(fetched_ms)` alone | 1 | **0.0** |
| 3 | NOT INDEXED — `MAX(fetched_ms)` alone | 1 | **87,019.5** |
| 4 | NOT INDEXED — whole read | 50 | 1,222.2 |

Row counts agree, 50 against 50.

**The headline is the plan, not the time.**

```
WITH INDEX -- MAX        SEARCH odds_snapshots USING COVERING INDEX idx_odds_window (market=? AND odds_event_id=?)
WITH INDEX -- row fetch  SEARCH odds_snapshots USING INDEX idx_odds_window (market=? AND odds_event_id=? AND fetched_ms=?)
```

**The live planner reaches for `idx_odds_window`, not `idx_odds_event`.**
Both statements, both arms. That is #89's own question — whether any
production statement plans onto the 479.6 MB `idx_odds_event` — and on this
access path, the one it was built for, the answer is **no**.

The lane that wrote the instrument saw the same substitution on a seeded
schema and reported it rather than hardcoding an expectation, which is why the
instrument prints whichever index the planner picked.

**87 seconds is the cost of having no index at all**, not the cost of
`idx_odds_event`. `NOT INDEXED` suppresses **every** index on the table, so
arm 3 is "no index, cold" and measures the value of *some* index on this path
— about five orders of magnitude. It says nothing about the marginal value of
`idx_odds_event` specifically, which is the question the drop would turn on.
(Arm 4's 1,222 ms is the same statement warm, after arm 3 pulled the table
through memory.)

### What this does not establish, and it is the load-bearing part

- **Not that `idx_odds_event` is safe to drop.** This instrument covers one
  access path. Any other statement — the recorder's writes aside — could be
  planning onto it, and none has been enumerated. The story needs a sweep of
  every `odds_snapshots` reader before a drop is even a proposal.
- **Not that `NOT INDEXED` is the same as the index being absent.** It forces
  the planner off indexes for that statement; it does not remove the index's
  write cost, its page-cache footprint, or its 479.6 MB. The module comment
  says so, deliberately.
- **Not a rate, for either section.** Single runs, one connection, one
  instant, on a machine also running the recorder.
- **Not free.** Arm 3 walked 5.4 M rows and took 87 seconds; the desk's page
  cache was flushed behind it. That is the cost `--i-accept-the-cache-flush`
  exists to make someone type, and it was typed deliberately, once.
