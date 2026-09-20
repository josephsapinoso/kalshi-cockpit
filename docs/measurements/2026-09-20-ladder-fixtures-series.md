# What unattended scouting would actually demand — 2026-09-20 ~23:50Z

Ticket #116's input. The 38th session took one reading (`/api/parlays` at
22:03Z: 21 leg slots across 9 distinct fixtures), said one reading is not a
rate, and parked the question behind "a deploy first and then a week". Live is
now on `3699593`, so the deploy has happened.

**The week is not needed, and the series that was built for this question does
not answer it.** The binding number is structural and can be read out of the
source tonight.

## 1. The quantity that drives spend

`backend/scout_watch.py:178` reads tonight's ladder through
`build_ladder_payload_widening` — the same call `GET /api/parlays` serves —
and `_distinct_fixtures_kickoff_soonest` walks **the distinct fixtures on the
cards**, convening at most one per cycle. So demand is the card payload's
distinct fixture count, not the size of the pool the cards were drawn from.

That count has a hard ceiling that needs no sampling. `CARD_SHAPES`
(`backend/core/ladder.py:254`) is nine fixed recipes whose `max_legs` sum to
**30**, and the ladder takes one leg per game, so a night's ladder can carry
at most **30 distinct fixtures, ever**.

Two direct readings of the real quantity, both today:

| instant | leg slots | distinct fixtures | cards filled |
|---|---|---|---|
| 2026-09-20T22:03Z (38th session) | 21 | 9 | — |
| 2026-09-20T23:44Z (this session) | 12 | **6** | 4 of 9 |

At 23:44Z the payload's own `excluded` counters read `stale_consensus: 23`,
`kickoff_outside_window: 142` — 165 candidates narrowed to 12 leg slots. The
kickoff-window filter is what separates the pool from the demand.

## 2. The 30-day series, and why it is not the answer

`inspect_live_db.py ladder-fixtures --days 30`, run on live (`cost=CHEAP`:
one bounded seek on `idx_fair_market_computed` per market per day, **not** a
`WALKS_THE_FILE` query, so it does not flush the desk's page cache — a future
session need not fear re-running it).

```
2026-08-22  28   2026-09-01  110   2026-09-11   52
2026-08-23  14   2026-09-02  102   2026-09-12   32
2026-08-24  23   2026-09-03  123   2026-09-13    0
2026-08-25  29   2026-09-04  135   2026-09-14   20
2026-08-26  97   2026-09-05  102   2026-09-15   25
2026-08-27 101   2026-09-06   67   2026-09-16   12
2026-08-28 104   2026-09-07   93   2026-09-17   55
2026-08-29 101   2026-09-08  135   2026-09-18   19
2026-08-30  98   2026-09-09  127   2026-09-19   37
2026-08-31 108   2026-09-10    9   2026-09-20    8
```

**The parts do not agree, so there is no median to quote.** Pooled it reads
n = 30, median 61, range 0–135 — and that pooled figure describes no night,
because the series has a regime break at 2026-09-10:

| window | n | median | range |
|---|---|---|---|
| 2026-08-22 → 08-25 | 4 | 25.5 | 14–29 |
| 2026-08-26 → 09-09 | 15 | **102** | 67–135 |
| 2026-09-10 → 09-20 | 11 | **20** | 0–55 |

What caused the break is not established here and is not this reading's
question.

**And the series measures the pool, not the demand.** Its own docstring
(`scripts/inspect_live_db_parlays.py:_q_ladder_fixtures`) says a day's count
is "best read as a **loose UPPER BOUND** on how many fixtures a `tonight`
ladder could have drawn from that evening, not the number the ladder actually
built cards from" — it applies no commence-time bound at all, so a game
already in progress or kicking off next week counts the same as one a
`tonight` card could reach. The two readings above show how loose: 135 in the
pool on 2026-09-08 against 6 and 9 fixtures on the cards today.

Where the series does bind: on **11 of the 30 days the pool was ≤ 30**, so on
those nights the pool, not the card structure, was the tighter ceiling. On the
other 19 the structural 30 is the only bound it gives.

## 3. The arithmetic

A convening costs **4 calls and up to 12 searches**
(`STAFF_PAIR_SEARCHES_WORST_CASE = 2 × WEB_SEARCH_TOOL["max_uses"] = 12`,
`backend/agents/scout_desk.py:83`; four seats — scout, staff pair, master).

Deployed ceilings (`fly.live.toml`): `AGENT_MAX_CALLS_PER_DAY = 24`,
`AGENT_MAX_SEARCHES_PER_DAY = 60`. **The search cap binds first**, at
**5 convenings a day**, where the call cap would allow 6 — the file's own
comment says so, and raising calls alone buys nothing. Inside that,
`SCOUT_AUTO_MAX_CONVENINGS_PER_DAY = 3` and
`SCOUT_AUTO_RESERVE_TAP_CONVENINGS = 2` apply when the flag is on; they are
never additive to the ceilings.

| to cover | convenings | calls | searches | vs 24 / 60 |
|---|---|---|---|---|
| today's 23:44Z ladder | 6 | 24 | 72 | 1.0× / **1.2×** |
| today's 22:03Z ladder | 9 | 36 | 108 | 1.5× / **1.8×** |
| a structurally full ladder | 30 | 120 | 360 | 5.0× / **6.0×** |

Joe's own taps come out of the same ceilings, so any figure above is the auto
path alone.

## What this does not establish

- **Two readings of the demand quantity, both on one evening, are not a
  rate.** The 6 and the 9 are 100 minutes apart on the same slate. The 30 is
  arithmetic and holds always; everything between 6 and 30 is unsampled.
- **Nothing about what a convening costs in dollars.** The ceilings are
  counts. `fly.live.toml`'s own note says the point estimate that used to sit
  there was low by ~1.9×.
- **Nothing about whether a briefing changes a bet.** ~13 orders is not an n,
  nothing is registered over it, and #114 records the leg's scout state at bet
  time precisely so the question becomes askable later rather than now.
- **Nothing about the regime break.** The 2026-09-10 collapse from ~102 to
  ~20 is visible and unexplained; it may be seasonal, a feed change, or a
  recorder change. It is not chased here.
- **The `ladder-fixtures` instrument is not wrong, it answers a different
  question.** It bounds the pool. Nothing in the repo records the ladder
  payload's own fixture count over time, which is why only two readings of it
  exist.
