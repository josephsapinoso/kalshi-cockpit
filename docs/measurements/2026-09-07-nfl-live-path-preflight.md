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
row three hours later (845,792).

### CORRECTION, 2026-09-07 15:20Z — the count will not fall, and reading it would have called a success a failure

This section said: *"After the first NFL sweep, expect the first row to fall to
~16 or lower (Week 1 cleared; Week 2 depends on the feed's listing depth) and
the second row to follow on the pass after."* **That is wrong, and it is wrong
in the direction that reads a working link as a broken one.**

Nothing sets `unmatched_items.resolved = 1` — `linker.py` only ever upserts
(`linker.py:571-587`), moving `last_seen_ms` forward and incrementing
`seen_count` — and nothing deletes a row on success. The only thing that
removes one is `retention.DEFAULT_UNMATCHED_RETENTION_MS`, **7 days measured on
`last_seen_ms`** (`store/retention.py:110`). So when Week 1 links, its 16 rows
do not go anywhere: they stop being re-derived and sit at a frozen stamp for a
week.

**The count at 04:00Z will still be 32. That is the success case.** What
separates the two halves is `last_seen`:

| after a successful first sweep | rows | `last_seen` |
|---|---|---|
| Week 1 `KXNFLGAME` — linked | 16 | **frozen** at the last failing pass, ~03:3xZ |
| Week 2 `KXNFLGAME` — still unlinkable if the feed does not list that far | 16 | **moving**, stamped by the newest pass |
| `KXNFLSPREAD` | 16 | moving until the game links, then frozen |
| `KXNFLTOTAL` / `KXNFLTEAMTOTAL` ladders | 18 | moving — scope, not a defect |

So: **read the stamps, never the count.** A count that stays at 32 says
nothing at all; 32 rows all carrying a *fresh* stamp is the broken-link case.

### Read it with the instrument, which now exists on the box

This section also said to read it *"with `scripts/list_unmatched.py`'s query
shape"* — which is what happened, as ad-hoc SQL over `flyctl ssh`, because the
script itself was never in the image. That is the thing
`scripts/inspect_live_db.py`'s ruling forbids in those words: *"nothing that
carries its own source in the command line."* Fixed the same day — the script
now declares its live path, `.dockerignore` re-includes it, and the derivation
in `TestTheSshInvokedScriptsSurviveDockerignore` makes the pair inseparable:

    flyctl ssh console -a kalshi-cockpit \
      -C "python /app/scripts/list_unmatched.py --db /data/cockpit.db --league 'Pro Football'"

It orders by `last_seen_ms DESC` and prints both stamps, so the live rows sort
above the frozen ones and the reading above is the one the output gives.

### The baseline re-taken through the shipped instrument, 15:30Z

This is the reference for tonight, and it supersedes the 07:21Z table above as
the thing to compare against — same day, same queue, but read by the tool that
will read it again at 04:00Z rather than by a different one.

| series | rows | reason | `first_seen` | `last_seen` |
|---|---|---|---|---|
| `KXNFLGAME` | **32** | no sportsbook fixture within the commence-time window | 2026-08-20 00:27 | **2026-09-07 15:30** |
| `KXNFLSPREAD` | **16** | no linked game event for fixture … | 2026-08-24 03:25 | **2026-09-07 15:30** |
| `KXNFLTOTAL` | **16** | expected 2 sides, got … | 2026-08-25 15:39 | **2026-09-07 15:30** |
| `KXNFLTEAMTOTAL` | **2** | expected 2 sides, got … | 2026-09-02 20:53 | **2026-09-07 15:30** |
| | **66** | | | 0 stale |

**Every one of the 66 carries the same fresh `last_seen`.** That is the correct
pre-sweep state and it is what makes tonight legible: right now *nothing* is
frozen, so any frozen row at 04:00Z is a row the first NFL sweep fixed.

**The total is 66, not the 60 recorded at 07:21Z, and the growth is entirely in
the class that does not matter.** The ladder rows went 12 → 18; the two classes
tonight is about — 32 `KXNFLGAME` and 16 `KXNFLSPREAD` — are **unchanged**. Do
not read the total as drift in the thing being measured.

Reading it cost nothing: `flyctl ssh`, a `mode=ro` connection, no
`api_credits` row.

### Re-taken at 16:25Z, and it has not moved

A second pre-sweep read, 55 minutes after the first and 11.1 hours before the
earliest the bootstrap can fire. Identical in every cell that decides tonight:
**66 rows, the same 32 / 16 / 16 / 2 split, `last_seen` = `2026-09-07 16:25`
on all 66, 0 stale.**

Two agreeing pre-sweep reads are not redundancy. Tonight's reading turns on
*frozen versus fresh*, and one baseline cannot separate a queue that re-stamps
every pass from one that merely happened to be stamped at 15:30Z. Two reads
55 minutes apart, both wholly fresh, establish that it re-stamps every pass —
the premise the whole reading rests on, and one that was until now assumed
rather than shown.

The queue's soonest row is `KXNFLGAME-26SEP09NESEA`, the same event check 2
named as the one that crosses the horizon. Nothing has changed hands.

### The 700-credit day cap cannot eat tonight's observation

Worth checking because it is the one ungated way tonight dies quietly: the
budget day rolls at 10:00Z, so **03:35Z on 09-08 falls inside budget day
20260907**, not a fresh one. Were the cap to bind first, `decide_sweeps` would
return `fire=()` and the bootstrap would be refused with no NFL row to read —
and the refusal would look, from `list_unmatched.py` alone, exactly like a
sweep that fired and failed to link.

Read at 16:30Z: **15 calls, 60 of 700 credits**, 640 remaining with ~17.5 h of
the budget day still to run. The heaviest day this instance has ever recorded
is 492 (20260827). The cap is not a live risk tonight; it is Sunday 09-13's
risk, and this read changes nothing about that projection.

The same read dates the attention slice: the day's first `trigger = 'attention'`
rows are 16:15Z and 16:25Z, both `americanfootball_ncaaf`. The desk was open
while this was being read. That is **not** evidence about ADR 0111 in either
direction — NCAAF's kickoff is inside twelve hours, so the tiered rule and the
deployed rule award it the same ten-minute cadence.

### And the instrument needed one fix before it was usable

Its first live run returned **75.8 KB for 66 rows** — lines of 1,300 to 2,249
characters. `KXNFLTEAMTOTAL`'s `detail` is the whole points ladder joined by
" vs ", ~2,100 characters, and a column table takes its width from its worst
cell, so all 66 rows were padded to it. The `last_seen` column — the *only*
column the reading above uses — sat two thousand characters right of where
anyone would look.

Cells are now cut at 80 characters with the count of cuts printed and `--full`
to recover them. The same read is now **17 KB**, 52 cells cut. Commit
`763adad`, deployed and verified on live at 15:52Z.

Do **not** read `event_links`, which holds only the links that succeeded and is
truncated by the very tolerance it would be used to measure.

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
- That the sweep will be **affordable on 09-13**. Tonight's affordability is
  now established rather than assumed — 60 of 700 at 16:30Z, inside the same
  budget day the bootstrap fires in — but that is one 4-credit call on a quiet
  Monday. Sunday is a different day and
  `docs/measurements/2026-09-06-nfl-week-1-credit-headroom.md` still carries the
  only projection of it; nothing here moves that number.
- Anything about `KXNFLTOTAL`. The ladders exist on Kalshi and the desk has no
  fair value for them, and both facts were already known.
