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

## THE RESULT — the first NFL sweep fired at 03:23:58Z and both classes linked

Taken 2026-09-08 03:41–03:45Z through the instruments named above, on the
corrected reading rather than the one the pre-flight first wrote down.

**The buy.** `api_credits` carries one row for
`/sports/americanfootball_nfl/odds` at **2026-09-08T03:23:58.664Z**, `cost = 4`,
`markets = h2h,spreads`, `regions = us,eu`, **`trigger` NULL** — which is what a
bootstrap looks like and is why the grep for the string `bootstrap` was
forbidden. It is the newest `served` row in `odds_sweep_log` at that same
`pass_ms`, and the expected `skipped` props row landed on the same pass:
*"scheduled prop buying is off for americanfootball_nfl, so this window buys
team lines only."*

**It fired 3.9 minutes after the horizon crossing, inside the predicted bound.**
Predicted 03:20Z + one full-pass interval = ~03:35Z, ~03:37Z with jitter; actual
03:23:58Z. The pass that caught it came sooner than the 900 s worst case, which
is the interval being a ceiling rather than a period — the loop had a pass due
anyway. Nothing about the design is different from what was derived; the
derivation bounded it and the bound held.

**The link, read the way the correction says.** `unmatched_items` for
`Pro Football` is **still 66 rows** — the count did not move and was never going
to, because nothing sets `resolved` and nothing deletes on a link. What moved is
`last_seen`:

| series | frozen @ 03:05 | still fresh @ 03:39 | reading |
|---|---|---|---|
| `KXNFLGAME` | **32** | 0 | **linked** — stopped failing |
| `KXNFLSPREAD` | **16** | 0 | **linked** — inherits its game's link |
| `KXNFLTOTAL` | 0 | 16 | still failing, by scope — the feed buys no totals |
| `KXNFLTEAMTOTAL` | 0 | 2 | same |
| | **48** | **18** | |

03:05 is the last pass **before** the 03:23:58Z sweep. All 48 rows this
observation was about froze there; the 18 ladder rows kept re-stamping through
03:39. That is the success signature stated in advance, and it is the exact
partition: the two classes predicted to link are wholly frozen, the class
predicted to keep failing is wholly fresh, and no row falls on the wrong side.

**Why the two 09-07 baselines were worth taking.** Had only the 15:30Z baseline
existed, "48 rows frozen" would have been consistent with a queue that simply
stops stamping at night. The 16:25Z re-read established that it re-stamps every
pass, so a freeze is a fix. That inference is the whole reading and it now rests
on an observation rather than an assumption.

**Cost.** Budget day 20260907 closed at **300 of 700** across 75 calls. The
bootstrap's 4 credits were never near the cap; the 16:30Z headroom check was
correct and, as written, could not have been read off `list_unmatched.py` alone.

### What this does NOT establish

- **That the linked fixtures produce usable prices.** The link is
  Kalshi-event-to-sportsbook-fixture. Whether the books quote both sides, and
  whether `devig.py` finds enough of them to reach a fair value, is the next
  question and is not answered by an `unmatched_items` freeze.
- **Anything about Sunday 09-13.** This is one 4-credit bootstrap on a day that
  spent 300 of 700. The kickoff-window loop — the largest of the three spenders
  and the one with no cap but the day's — did not run for NFL tonight.
- **That `KXNFLTOTAL` will ever link.** It is out of scope by construction, not
  pending. The 18 fresh rows are the designed state and will keep re-stamping
  until `DEFAULT_UNMATCHED_RETENTION_MS` prunes on `last_seen_ms`.
- **That the 48 frozen rows are gone.** They are stale, not resolved. They
  vanish seven days after 03:05Z and not before, and a reader who returns to
  this queue mid-week will find them and must read the stamp, not the count.

## Item 3 — the NFL wire fixture, captured 2026-09-08 04:09Z, and the 4 credits it cost

Taken only after the sweep succeeded, for the reason the plan gave: tonight's
bootstrap was a 4-credit test with a 30-minute backoff, cheaper than any
pre-emptive capture and a real answer rather than a rehearsal.

`scripts/capture_nfl_odds_fixture.py --confirm-spend-4` →
`tests/fixtures/odds_nfl_h2h_spreads.json`, 926 KB.

    events    272          the entire NFL regular season in one response
    books     30           incl. pinnacle, betfair_ex_eu, matchbook
    markets   h2h, h2h_lay, spreads
    spreads   -14.5 .. +14.5 over 2,278 outcomes, all half-integer
    vendor    x-requests-remaining 17584, x-requests-used 2416

**LEDGER DRIFT: +4 credits the `api_credits` table will never show.** The table
is written by the runner on the live box; this call went from the laptop
straight to the vendor. Every `credits-day` and `credits-month` read for
2026-09-08 is therefore 4 low against the vendor's own counter. Recorded here
rather than left silent, because an unexplained 4-credit gap in a later
reconciliation is exactly what costs an hour. The vendor headers above are the
reconciling figures.

**The request shape is live's, not the laptop's, and that distinction nearly
went the wrong way.** `fly.live.toml` sets `ODDS_MARKETS = "h2h,spreads"`;
this laptop's `.env` carries `ODDS_MARKETS=h2h`. The first draft of the capture
script read the environment, which would have bought a **two**-credit payload
of a request the recorder does not make and pinned a code path nobody runs,
while looking entirely correct. The shape is now a pinned constant with the
cost guard asserting it still multiplies to 4.

### What the fixture pins, in `tests/test_odds.py`

Ten tests, in four classes. The two that could not have been written against
the MLB capture:

- **`TestFootballSpreadsAreNotBaseballSpreads`.** Baseball's run line is a
  fixed ±1.5, so every existing spread assertion in this repo is an assertion
  about a constant. Football's handicap runs ±14.5 here and hangs on
  half-point hooks — a 3 and a 3.5 are different bets. The tests pin that the
  range is football-sized, that hooks survive the parse, and that every spread
  market is two-sided and sums to zero.
- **`TestTheDeployedRequestBuysNoFootballTotals`.** This is the evidence for
  the "scope, not a defect" sentence about the 16 `KXNFLTOTAL` rows that kept
  re-stamping tonight. The deployed request does not ask for totals; the
  response carries none; nothing can link. It is written so that adding
  `totals` to `ODDS_MARKETS` **fails the test** — which is correct, because at
  that moment the ladder rows become linkable and the per-sweep cost rises by
  `len(regions)` at the same time.

### The guards were disabled and watched to fail — and one of them did not

Four mutations against `backend/odds/client.py`:

| # | mutation | result |
|---|---|---|
| M1 | `if market_key in EXCLUDED_MARKETS:` → `in ()` | **stayed green** |
| M2 | round `outcome_point` to an integer | red — hooks test |
| M3 | `outcome_point=None` | red — hooks test |
| M4 | add `h2h_lay` to `PRICEABLE_MARKETS` | red — both lay tests |

**M1 is the one worth recording.** It stayed green not because the test is
decoration but because the mutation was aimed at the wrong line:
`EXCLUDED_MARKETS` only selects which log message is emitted. The actual gate
is the `PRICEABLE_MARKETS` **whitelist** one line above
(`client.py:567`) — an unclassified market is dropped by default, and
`EXCLUDED_MARKETS` merely distinguishes "dropped on purpose" from "dropped
with a warning" in the log. M4 aims at the real guard and both lay tests go
red, the MLB one included.

The lesson generalises past this file: **a mutation that leaves the suite green
has two readings — the test is decoration, or the mutation missed the guard —
and they are distinguished by reading the code, not by trying another test.**

### What item 3 does NOT establish

- **That the parser prices football correctly.** These are wire-contract tests
  — fields present, markets classified, lay prices dropped, spreads two-sided.
  Nothing here says the resulting consensus is any good, and ADR 0038 already
  says the consensus signal is negative.
- **Anything seasonal.** One capture, one day. The response carried all 272
  regular-season games; that will not be true in December, and
  `test_the_capture_is_a_real_multi_book_nfl_response` deliberately asserts
  `>= 100` rather than `== 272` so a mid-season re-capture is not a false alarm.
- **Anything about Sunday 09-13's credit load.** One sweep returning 272
  fixtures for 4 credits is a fact about the *response*, not about how many
  sweeps the kickoff-window loop will plan.

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
