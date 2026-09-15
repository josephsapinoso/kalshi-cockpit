# 0157 — An instrument may not charge its cost to the desk

**Date:** 2026-09-15
**Status:** accepted
**Supersedes:** nothing. Extends the bounded-read rule of ADR 0148 (`api_read_incidents`) from routes to the inspector.

## Context

A partner pass proposed a finding — *no sharp book quotes player props, so four
of the ten named bookmakers are dead weight on the prop endpoint* — and named
`scripts/inspect_live_db.py prop-bookmakers` as the way to confirm it on live.

Two things came out of trying to run it.

### 1. The finding is not established, and the fixture cannot establish it

It rests on `tests/fixtures/odds_mlb_player_props.json`: nine books returned,
none of them `pinnacle`, `matchbook` or `betfair_ex_eu`. The sibling team
fixture, `odds_mlb_h2h_spreads_totals.json`, carries a `params` envelope —

```json
"params": {"regions": ["us", "eu"], "markets": ["h2h", "spreads", "totals"]}
```

— and under `us,eu` all four sharps appear on team markets. **The prop fixture
has no `params` envelope at all.** Its nine books are all US books, which is
exactly what `regions=us` returns, so "EU books do not quote props" and "that
capture never asked for EU" produce the identical file and the fixture cannot
separate them. One event, one date, one sport, one market family
(`pitcher_strikeouts`), and the absent evidence is the parameter that decides
it. The finding is recorded as **unverified** and nothing is changed on its
strength; the confound, not the conclusion, is the durable part.

That a verbatim capture of one endpoint records its request parameters and a
verbatim capture of another does not is itself the defect — the envelope is
what makes an *absence* in a capture readable.

### 2. The instrument that would settle it charges its cost to Joe

`_SQL_PROP_BOOKMAKERS` was a `GROUP BY bookmaker` over `odds_snapshots` whose
only predicate was `outcome_description IS NOT NULL`. No index leads with that
column, so the single available plan is a full scan of the largest table on the
box. `odds_snapshots` is exempt from retention pruning by design, so it only
grows.

The cost does not land on the session that runs it. It lands on **whoever
touches the desk next**, because the scan evicts the page cache the live reads
run through — `tasks/lessons.md` records a read-only `GROUP BY` over this table
costing the desk 75 seconds per query afterwards. It was 22:35Z with MLB first
pitch at 22:40Z, so the query was not run.

An instrument whose expense is paid by a different party, minutes later, is one
nobody attributes correctly: the session sees a query that returned promptly,
and Joe sees a desk that got slow for no reason he can trace.

## Decision

**A whitelisted read may not be unbounded, and its default may not be the
unbounded case.**

`prop-bookmakers` gains a `commence_ms` floor and an optional sport cut:

```sql
WHERE commence_ms >= :since
  AND (:sport IS NULL OR sport_key = :sport)
  AND outcome_description IS NOT NULL
```

`idx_odds_commence` serves the range; `idx_odds_sport_commence` serves it when
`--sport` names one. `--since YYYYMMDD` moves the floor and **defaults to seven
days, not to the epoch** — the default matters more than the flag, because the
unbounded call is the one a session reaches for mid-game, when it is dearest.
A malformed `--since` raises rather than falling back to no bound: a silently
ignored bound is an unbounded query wearing a flag.

The window is printed as its own section beside the counts. A windowed count
and a lifetime count are different numbers, and this repo has already paid for
two quantities sharing one name (CLAUDE.md, `actionable`; and the transacted
path's three counts).

`--sport` is a filter second and a bound first. `book-rows` needed nothing: it
was already bounded on `commence_ms >= :at`.

The query's docstring gains a **What this does not establish** section, because
the reading it invites is wrong in a specific way: since ADR 0155 the request
names ten books, so a book absent from the result may simply never have been
asked for, and a **misspelled or sport-absent key is silently absent from the
response while still consuming one of the ten slots** — indistinguishable here
from a book that quotes no props. It must be read beside `ODDS_BOOKMAKERS`.

## Consequences

- The decisive read is now safe to run during games, so the props question can
  be answered from live `odds_snapshots` for **zero credits** — the table
  records every returned book key per sport per fetch, unconditionally.
- No book list changed. Whether to buy a different ten on the prop endpoint is
  a decision about what the desk buys, it rests on an unverified finding, and
  it is Joe's call.
- The seven-day default will silently exclude a question about an older
  population. That is the intended failure direction: a too-narrow window
  reports a number that is visibly small, while a too-wide one reports a
  correct number and a slow desk.

## Guards

`tests/test_prop_bookmakers_is_bounded.py`, three mutations each observed red:

| # | mutation | red |
|---|---|---|
| 1 | drop `AND commence_ms >= :since` | 3 tests, including **both** `EXPLAIN QUERY PLAN` guards |
| 2 | neuter the sport cut to `(:sport IS NULL OR :sport IS NOT NULL)` | `test_naming_a_sport_excludes_the_others` |
| 3 | `_prop_since_ms` returning `0` with no `--since` | `test_an_absent_since_still_produces_a_recent_floor` |

The plan guards assert no bare `SCAN odds_snapshots` and that `commence_ms>?`
appears in the plan. **A plan names the access method, never the rows it
touches** — the v39 note in `schema.sql` is this repo's record of that mistake
— so the plan test is the guard and the live read is the measurement.

The mutations were applied against a **copy** of the file, not reverted through
`git checkout`: a prior session lost real uncommitted work in the same file
that way (`tasks/lessons.md`).

## What this does not decide

- Whether any sharp book quotes player props. Unverified; see Context §1.
- Whether the ten named books are right for the prop endpoint. Not touched.
- Whether the prop fixture should be recaptured with a `params` envelope. It
  should, and it is recorded in `tasks/NEXT.md` rather than done here, because
  recapturing costs credits and the live table answers the same question free.
