# 2026-09-07 — NFL live-path pre-flight, read at 07:21Z, zero credits

**Question.** Three days before the desk's first NFL slate, does every stage
the first NFL sweep depends on already hold what it needs — and if not, which
stage, so Wednesday's failure is diagnosed before it happens rather than
during it?

**Answer.** Every stage that can be checked without buying odds passes. The
one stage that cannot — the feed's NFL fixtures — is empty because **nothing
has bought them yet, and nothing can until 03:20Z on 2026-09-08**, when the
soonest Kalshi NFL event crosses the 48-hour bootstrap horizon. The first NFL
sweep then fires on the next full pass, by construction, with `allow_bootstrap`
at its default of `True`. The tap route cannot bring that forward: it refuses
a sport with no stored fixture (`backend/api/routers/odds.py:159-173`), so the
4-credit early buy the plan allowed was not available through the desk's own
spend path and was not taken by a side channel.

Every number below was read from the live database over `flyctl ssh` with a
read-only connection (`?mode=ro`), the Odds API's free `/v4/sports` listing,
and the live `/api/window` and `/api/slate` routes behind the session cookie.
No `api_credits` row was written by this measurement.

## The eight checks

| # | check | instrument | result | verdict |
|---|---|---|---|---|
| 1 | `americanfootball_nfl` active on the feed | `GET /v4/sports` (free) | `active: true`; tier at 17,896 of 20,000 remaining | pass |
| 2 | discovery holds Week 1 | `kalshi_events` where `series_ticker LIKE 'KXNFL%'`, commence in the next 9 days | **50 events**: 16 `KXNFLGAME`, 16 `KXNFLSPREAD`, 16 `KXNFLTOTAL`, 2 `KXNFLTEAMTOTAL`; all `open`; first 09-10 03:20Z (NE–SEA), last 09-15 03:15Z | pass |
| 3 | competition string | `unmatched_items.league` for those tickers | exactly `Pro Football` on every row; no `Pro Football Preseason` | pass |
| 4 | linked fixtures map to the NFL sport key | `event_links` joined to `odds_snapshots.sport_key` | 0 links — nothing to map yet | n/a until 5 |
| 5 | feed holds NFL fixtures | `odds_snapshots` where `sport_key = 'americanfootball_nfl'`; `api_credits` for the key | **0 fixtures, 0 credit rows, lifetime** | expected — see below |
| 6 | `unmatched_items` baseline | grouped by league × reason, `resolved = 0` | recorded below | baseline |
| 7 | planner knows NFL is coming | `/api/window` and a read-only replay of `decide_sweeps` on the live DB | no NFL slot (no fixtures); replay shows NFL **67 h out against a 48 h horizon** | pass, dated |
| 8 | screen renders it | `/api/slate?league=americanfootball_nfl` | HTTP 200, `filter.league` echoed, honest empty set (`hidden: 250`) | pass |

`kalshi_events.category` is `Sports` on every row — the competition string is
not stored on the events table. Check 3 reads it off `unmatched_items`, which
is where the linker writes what it was told. That is the same string the
classifier keys `IN_SCOPE_LEAGUES` on (`backend/kalshi/discovery.py:237`).

## Why check 5 is zero and when it stops being zero

The bootstrap branch in `decide_sweeps` (`backend/odds/timing.py:1998-2023`)
buys a sport that is in scope on Kalshi and has no stored fixtures **only when
its soonest Kalshi event is within `DEFAULT_HORIZON_MS` = 48 h**. Replayed on
the live database at 07:30Z with the runner's own inputs reconstructed from
`kalshi_events`:

    in_scope   baseball_mlb 12 h   americanfootball_ncaaf 19 h   americanfootball_nfl 67 h
    horizon    48 h
    fire       baseball_mlb (desk floor)     -- with allow_bootstrap True AND False

So NFL is not held back by anything; it is simply not yet inside the window.
The soonest event (`KXNFLGAME-26SEP09NESEA`, Kalshi commence 09-10 03:20Z,
which is Kalshi's clock ~3 h late for a real kickoff near 00:20Z) enters the
horizon at **2026-09-08 03:20Z**. The full pass runs every 15 minutes with
`allow_bootstrap=True` (`runner.py:2340` default; the ingest call at
`runner.py:3084` does not override it), so the first NFL sweep lands within
15 minutes of that — about 21 hours before the real kickoff, and before any
kickoff-window slot could be planned for it.

Two things that do NOT gate it, checked rather than assumed: the failed-sweep
backoff (ADR 0109) — NFL has never failed a sweep because it has never made
one — and the attention slice, which does not apply to `BOOTSTRAP`.

## The Wednesday baseline (check 6)

`unmatched_items` where `resolved = 0` and `league = 'Pro Football'`, grouped
by reason, at 07:21Z:

| reason (prefix) | rows | sightings | what it is |
|---|---|---|---|
| `no sportsbook fixture within the commence-time window` | **32** | 845,792 | all 32 `KXNFLGAME` events on the board — 16 Week 1 + 16 Week 2 (through 09-22); the class the first sweep should empty for Week 1, and for Week 2 only if the feed lists that far |
| `no linked game event for fixture …` | 16 | 24,771 each | `KXNFLSPREAD`, one per Week 1 game; resolves once the game event links |
| `expected 2 sides, got 19/27/28` | 12 | 30,503 per row | `KXNFLTOTAL` / `KXNFLTEAMTOTAL` ladders; **scope, not a defect** — the feed buys no `totals` (ADR draft, 2026-09-07) |

The previous entry's "32 of 32 `not_carried`, 842,656 sightings" is this first
row three hours later (845,792). **After the first NFL sweep, expect the first
row to fall to ~16 or lower (Week 1 cleared; Week 2 depends on the feed's
listing depth) and the second row to follow on the pass after**, since a
spread links through its game. The third row will not move and must not be
read as a failure.

Read it with `scripts/list_unmatched.py`'s query shape grouped by `league,
reason`; do **not** read `event_links`, which holds only the links that
succeeded and is truncated by the very tolerance it would be used to measure.

## Also found, not NFL

`combo_orders` row 2 — the bid placed 2026-09-01 19:59Z that filled at 21:40Z
and settled the next day — is still `status = 'resting'`, and
`backend/bid_watch.py:79-87` has been retrying its cancel **once a minute since
2026-09-01 22:41Z**, logging `ERROR … cancelling combo bid 2 at its deadline
failed; it is left working and will be retried on the next pass` each time
(07:20, 07:21, 07:22Z today). The venue's 404 is correct — the order is gone
because it filled — and the watcher cannot tell that from a transport failure.
That is the gate for the lane that fixes it, and it passed.

## What this does not establish

- That the first NFL sweep will **link**. Checks 2–3 say the Kalshi side is
  what the linker expects; check 5 says the book side has not been seen. The
  272-fixture capture in `tests/fixtures/` linked 16 of 16 against these same
  events, but that was a capture, not the live feed on the day.
- That the sweep will be **affordable**. It costs 4 credits against a day that
  has never run four sports; `docs/measurements/2026-09-06-nfl-week-1-credit-headroom.md`
  carries the projection, and this read adds nothing to it.
- Anything about `KXNFLTOTAL`. The ladders exist on Kalshi and the desk has no
  fair value for them, and both facts were already known.
