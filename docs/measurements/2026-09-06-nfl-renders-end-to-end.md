# NFL renders end to end, and the commence offset is a shift plus noise rather than a constant

**Taken 2026-09-06**, three days before the 2026 NFL season opens (Wednesday
2026-09-09). Read-only. **Zero Odds API credits**: the Kalshi side is a
committed verbatim capture, the book side is a committed fixture, and the live
reads are `mode=ro` over `event_links`.

---

## Why this was taken

Everything verified about NFL before this was about **credits** and **team
names**. Nobody had asked whether the pipeline *works* on NFL data. The concern
was specific: `prop_market_keys()` returns five MLB-only keys, which is correct
by design but proves league-shaped assumptions exist and are not always
labelled. A silent drop would show as an empty slate rather than an error, on
the week the desk is most likely to be looked at.

## The verdict

**It works, and it was driven rather than inspected.**
`tests/fixtures/events_nfl_preseason.json` turns out to hold **16 genuine
`Pro Football` regular-season Week 1 events** alongside the 16 preseason ones it
is named for, so no synthetic Kalshi data was needed.

| stage | code exercised | result |
|---|---|---|
| discovery | `discover_from_events` | **16/16** admitted; 16 preseason correctly dropped; **0** unreadable `commence_ms` |
| matching | `link_event` vs 272 real book fixtures | **16/16 matched**, every one `exact_alias_pair` |
| pricing | `consensus_devig` → derived ask → `settlement_fee` | **16/16 priced**, 0 failures, 0 unreadable NO bids |

The two-city traps resolved correctly: `New York J`/`New York G` and
`Los Angeles R`/`Los Angeles C` each bound to the right franchise, which is the
case `_bijection` exists for. `devig.py` and `engine.py` contain **zero**
`sport_key` references — the pricing path is sport-agnostic in fact, not only in
intent.

The events are the real Week 1 slate, including the Wednesday opener
(`KXNFLGAME-26SEP09NESEA`), the Sunday blocks, and `26SEP14DENKC` on Monday.

## The finding: the 3-hour offset is a shift plus noise, and the comment said otherwise

`linker.py`'s tolerance comment read: *"the offsets ... are identical, which
makes it a fixed shift and not a duration."* That was measured on **24 same-day
pairs** on 2026-08-07. Re-measured over the **whole live `event_links` record**:

```
league                 n      min       max      distribution
Pro Baseball        1,872   -3.07h   -2.98h     -2.98 x1520, -3.00 x340, -3.07 x12
NCAA Football         304   -3.50h   +3.00h     -3.00 x297, -3.50 x4, +3.00 x2, -1.00 x1
Pro Basketball (W)     87   -3.50h   -2.00h     -3.00 x79, -2.83 x5, -3.50 x2, -2.00 x1
```

The **shift is right** — the mass sits at −3.00h exactly, as the original
reading said. What 24 pairs could not see is the **tail**: six links at −3.50h,
and two NCAAF links at **+3.00h where Kalshi is *earlier* than the book**. Read
it as a 3-hour shift plus up to ~30 minutes of genuine per-fixture disagreement
about kickoff, occasionally sign-reversed.

**So the headroom is 30 minutes, not an hour.** `max|skew| = 3.50h` against
`DEFAULT_COMMENCE_TOLERANCE_MS = 4h`.

**NFL is the comfortable case and that is a fact about NFL, not about the
tolerance.** All 16 Week 1 events link at exactly +3.00h, because NFL kickoffs
are quarter-hour aligned. The margin belongs to the tolerance, which every
league shares.

### The tolerance was NOT widened, deliberately

Widening cannot cause a wrong match — `link_event` refuses when more than one
fixture matches the same team pair in-window — but it does turn more MLB
doubleheaders into refusals. The tail is **8 links in 2,263**. Trading a
real MLB refusal rate against 8 rows is the wrong direction.

### What is actually worth fixing is the classification, not the number

When the tolerance *is* exceeded the refusal is stamped `NOT_CARRIED`, and
`runner.py`'s `unmatched_by_sport` docstring says of that half: *"`not_carried`
is scope and needs nobody."*

That sentence is right for its intended case — Kalshi lists NCAA Division II and
the odds feed does not carry it. It is wrong for a systematic clock drift, which
lands in the same bucket. **A whole league failing to link would arrive in the
category explicitly marked as needing no attention** — the same silent total
failure the 2-hour tolerance caused in August, recreated one layer up.

A league we buy odds for, with fixtures in the record, at 100% `not_carried`, is
a broken link and not scope. **Not built here.** Recorded as the open item.

### And NFL is sitting in that state right now, which is what makes it concrete

Live `unmatched_items`, unresolved, at the time of this measurement:

```
Pro Baseball    no sportsbook fixture within the commence-time window   126 items    339,862 sightings
Pro Football    no sportsbook fixture within the commence-time window    32 items    842,656 sightings
NCAA Football   no sportsbook fixture within the commence-time window    21 items    201,434 sightings
```

**Pro Football carries the largest sighting count in the entire table**, and the
cause is benign: `api_credits` has **zero rows for `americanfootball_nfl`** — the
NFL odds feed has never been called, because the season has not started and the
floor only buys for a sport with a fixture inside twelve hours. With no book
fixtures stored there is nothing to match against, so all 32 open `KXNFLGAME`
events refuse with the window reason.

**That is exactly the point.** A league at 32-of-32 `not_carried` with 842,656
sightings is *indistinguishable* from a league whose clock drifted past the
tolerance, and it has been sitting in the record for weeks being correctly
ignored — because `not_carried` "needs nobody".

**So this hands Wednesday a falsifiable check with a known baseline.** After the
first NFL odds sweep on 2026-09-09:

> `Pro Football` / *no sportsbook fixture within the commence-time window*
> should collapse from **32 items to ~0**.
>
> If it does not, the link is broken and the slate will look empty rather than
> broken. Read it with `unmatched_items` grouped by league and reason; do not
> read `event_links`, which by construction only contains links that succeeded.

That last clause is the trap this document nearly fell into: **the skew
distribution above is truncated by the very tolerance it is being used to
assess.** A fixture already outside 4h never becomes a row. `max|skew| = 3.50h`
is a lower bound on the spread of the underlying relationship, not a measurement
of it — and `unmatched_items` is where the other tail lives.

## Other league-shaped code, audited

No path was found on which NFL data would **raise**. Every sport-keyed lookup
uses `.get()` with an explicit default, every regex result is `None`-checked,
and there is no innings/quarters/halves constant anywhere in the risk path.

Three drop mechanisms exist and all three are counted or warned rather than
silent:

1. **Unknown `competition` string** — the classic failure (48 events / 726
   markets lost in August). Moot for NFL: the live capture confirms Kalshi sends
   exactly `"Pro Football"`, which `IN_SCOPE_LEAGUES` carries.
2. **Unknown spread unit** — `_KNOWN_UNITS = r"runs?|points?"`
   (`kalshi/spreads.py`). **No `KXNFLSPREAD` event exists in any committed
   fixture**, so NFL's phrasing is inferred rather than observed. Low risk: the
   same fixture carries `KXCFLSPREAD` reading *"British Columbia Lions wins by
   over 20.5 points"* — a football league already using the whitelisted unit and
   the exact grammar. And the failure is **counted**
   (`dropped_unknown_spread_unit`), so it would be visible zero supply, not
   silence. Worth capturing one real `KXNFLSPREAD` event to pin it.
3. **The credit cap** — the only one that produces a screen reading "no edge"
   when the truth is "the desk stopped buying". Covered by
   `2026-09-06-the-global-stop-is-not-invisible.md`; `credits-day --date` now
   answers it.

**Prop exclusion is correct by design and is recorded, not silent**:
`PROP_SERIES` is five `KXMLB*` keys, scheduled prop buying is off for every
sport, and `prop_sports` is derived from discovered ladders — so no NFL prop
credit is ever reserved or spent.

**The frontend is clean** — no `switch` on sport, no per-sport icon, colour or
sort order; an unknown league key renders as itself rather than being guessed.
The one cosmetic wrong note is pervasive **"tonight"** copy: an NFL Sunday's
main block kicks at **10:00 Pacific**, so "tonight" is simply the wrong word for
most of an NFL slate. The backend half of this was already renamed
(`kickoff_after_tonight` → `kickoff_outside_window`); the copy is the remainder.

## Two things this audit found that are NOT about parsing

- **`sorted(fixtures)` decides who gets starved.** The floor/desk loop iterates
  sports alphabetically, so `americanfootball_ncaaf` < `americanfootball_nfl` <
  `baseball_mlb` < `basketball_wnba`. When credits run short, **football is
  served and baseball and basketball drop to the hourly floor.** MLB is the
  population the CLV record is accumulated on. Two independent readings reached
  this; it is `sorted()` for determinism, not a chosen priority.
- **The single/manual order path sends no `exchange_index`.**
  `EXCHANGE_INDEX_DEFAULT`, `EXCHANGE_INDEX_COMBOS` and `EXCHANGE_INDEX_PARAM`
  are imported by `kalshi/orders.py` and used **exactly once each — the import
  itself**. `combo_bids.py` reads the shard off the market and refuses if absent;
  the order path does not. Kalshi moved Sports to shard 3 on 2026-08-24, and a
  shard-3 order was refused `user_not_found` (an unfunded shard). Blast radius is
  small — 0 of 27 real fills since arming went through this path — but it fails
  at the moment of a bet.

## What this does not establish

- **No NFL market has ever been priced against a real book line.**
  `nfl_names_books.json` carries no odds by design, so stage 3 used **synthetic**
  three-book odds. It tests the plumbing. **No number from it is evidence about
  NFL prices, about an edge, or about calibration.**
- **One Kalshi capture, one date.** 16 events out of a 272-fixture season. Flex
  scheduling moves kickoffs, and a game moved off a quarter-hour would carry a
  skew this capture cannot show.
- **It does not prove a card renders.** The audit ends at a priced row; the
  parlay ladder and the Board were read for league-shaped code, not driven.
- **`KXNFLSPREAD` remains unobserved** — inferred safe from CFL, not measured.
- **The skew figures describe links that SUCCEEDED.** A fixture already outside
  4h never becomes an `event_links` row, so this distribution is truncated by
  the very tolerance it is being used to assess. It is a lower bound on the
  spread of the underlying relationship.
