# 0004 — Two polling cadences, and confirming an unchanged recommendation

**Status:** accepted, 2026-08-08

## Context

Three limits, each defensible on its own, and no module holding more than one:

| Limit | Where | Why that number |
|---|---|---|
| `MAX_KALSHI_QUOTE_AGE_S` = 30 | `config.StalenessConfig` | Kalshi is quoted by sub-200ms market makers. A 30-second-old price is a guess. |
| `MAX_ODDS_AGE_S` = 900 | `config.StalenessConfig` | A sportsbook consensus moves on a scale of minutes, not seconds. |
| loop interval = 900s | `scripts/run_loop.py` | The Odds API free tier: ~500 credits a month, 6 a sweep, ≈2 sweeps a day. |

Nothing computed their product. A recommendation is bettable only while **both**
its inputs are fresh, and the row is rewritten once per pass, so each row was
bettable for **thirty seconds** after the pass that wrote it. Two passes a day
carry fresh odds, so the tool was actionable for roughly **one minute a day** —
against the fifteen-minutes-twice-a-day that every document in this repo,
including the ones written while fixing the sweep *timing*, asserted.

A second mechanism made it worse rather than better. `engine.persist_if_changed`
deliberately does not write a row whose derived ask and fair probability match
the previous one, because without it ~98% of the evidence record would be
repetition. Every freshness check measured from `created_ms`. So on an unchanged
market the price stayed current and the row aged out anyway: "this observation
is old" and "this price is old" were the same number.

## Decision

### 1. Two cadences, because two dependencies have nothing in common

The 900s interval belongs to The Odds API alone. Kalshi REST is unmetered and is
the *tighter* freshness limit. So the loop runs:

- a **full pass** every `--interval` (900s): discovery, the odds sweep inside
  the budget, linking, devig, recommendations, closing-line scoring, alerts,
  digest;
- a **quote pass** every `--fast-interval` (15s) **while the window is open**:
  Kalshi discovery, the quotes it carries, and a re-price against stored odds.
  No credit, no candlesticks, no digest.

`scheduler.Tempo` owns both decisions — which cadence, and which kind of pass —
and `run_forever` accepts a callable interval so the cadence can follow the
window. The predicate for "open" is the existing `window_status(...).is_open`,
not a second notion of the same thing.

**Rejected: run the full pass every 15s.** `decide_sweeps` is budget-safe, so
this would not overspend. It would fetch candlesticks for every started game 240
times an hour, and it makes the cheap path one config change away from the
expensive one. A quote pass is handed no odds client at all, so it *cannot*
sweep.

**Rejected: raise `MAX_KALSHI_QUOTE_AGE_S`.** It is the one limit here that is
about the venue rather than about our budget, and relaxing a freshness bound to
make a slow poller look correct is the flattering direction.

### 2. An unchanged decision is confirmed, not skipped

`persist_if_changed` stamps the existing row via `confirm_recommendation`:

    last_confirmed_ms
    last_confirmed_quote_age_ms
    last_confirmed_odds_age_ms

`created_ms` is untouched, so nothing about the record or about CLV scoring
changes — the row still says when the decision was made.

**Both ages, or neither.** A confirmation is a complete re-statement about one
instant. Refreshing the quote clock alone is the tempting half-fix and is
*arithmetically identical* while no new sweep has happened, which is what makes
it look right; the variant that actually kills is one crediting a confirmation
with fresher odds than it observed, because a row confirmed every fifteen
seconds would then never expire and the tool would offer bets priced against a
consensus swept hours earlier. `gate.live_ages` takes all three columns or falls
back to `created_ms`.

### 3. One implementation of "how old is this now"

`gate.live_ages` is used by both `recommendation_freshness` (the order endpoint)
and `api.routes._live_ages` (the Board). The Board previously restated the
arithmetic beside a comment promising it matched. It no longer would have: the
basis moved, and a Board measuring from `created_ms` would strike through rows
the server would sell. Per `tasks/lessons.md` — do not test that two paths
agree, delete one of the paths.

### 4. The composition is written down where a test can read it

`scheduler.quote_refresh_survives_interval(interval, jitter, max_quote_age,
pass_duration)` returns whether polling that often actually keeps a row inside
the limit, and `run_loop` **refuses to start** when it does not — the same shape
as the existing `sweep_window_survives_interval`. The gap between confirmations
is the sleep *plus* the pass, so both are inputs.

`TestTheComposedWindow` asserts it on the shipped constants, and asserts that
the single 900s cadence this replaces fails. That is the only way a change to
either number announces itself: a row expiring between passes is
indistinguishable from a board with nothing on it.

### 5. Schema v2, migrated before anything opens the database

`SCHEMA_VERSION` 1 → 2. `schema.sql` is applied with `CREATE TABLE IF NOT
EXISTS`, so a new column never reaches a database that already exists;
`store.db.migrate` is the other half. It is gated on the recorded version *and*
each step is individually idempotent, because the volume holding the live record
cannot be recreated and a crash between the last `ALTER` and the version stamp
must be resumable.

`docker/entrypoint.sh` runs `scripts/migrate_db.py` **before uvicorn**. The API
opens read-only and `open_db` refuses an unrecognised version, so it cannot
migrate its way out of a stale volume — it would 500 on every page until the
chain runner happened to call `init_db`, while `/api/health` stayed green
because it touches no database. A test asserts the ordering in the script.

## Consequences

**What this buys.** Roughly 30 minutes a day of actionability instead of roughly
1. Within a window, a row stays bettable continuously rather than for the first
thirty seconds.

**What it explicitly does not buy.** The window is still fifteen minutes, twice
a day. That is `MAX_ODDS_AGE_S` and the credit budget, and Kalshi polling does
not touch either. `test_quote_passes_cannot_outlive_the_odds_window` fails if
that ever stops being true.

**Cost.** Roughly 90 extra Kalshi discovery passes a day, only while the window
is open, each storing ~1,500 quote rows — about double the current
`kalshi_quotes` growth. Unmetered in credits, not free in disk.

**Still open.** Refreshing the quote at order time (`tasks/NEXT.md`). Fifteen
seconds of staleness is much better than fifteen minutes and is not zero, and
only a live read at confirmation makes an execution price honest.
