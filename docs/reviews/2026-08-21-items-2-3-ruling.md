# Partner ruling — the refusal on real data, and the lockout after the study

Convened 2026-08-21 ~21:00Z, while item 1 (`/bets`) awaited commit. The
executing session asked three forks on work items 2 and 3; the ruling below
is recorded verbatim so the build cannot drift from it and no future session
re-derives it.

## (a) The source: fills for the count and stakes. Not settlements. Not both.

`venue_settlements` cannot answer the question item 2 asks. A settlement
lands when the *game* ends, which is uncorrelated with when the bet was
placed — so "settled tonight" mixes bets made days ago and structurally
omits every bet made in the last hour. It is the wrong clock.

Worse, the only number settlements can produce for a night is **net**, and a
signed running P&L on the deciding screen is the chase trigger this repo has
already refused twice: the `(you're net up $X)` parenthetical was deleted
from `frontend/src/app/estimate/page.tsx` on 2026-08-20, and `/api/slate`'s
`money` block carries a standing comment that cash and open positions are
**never summed** for exactly this reason. Item 2 must not reintroduce it one
line below.

So: **count of markets bet and dollars staked, since the day roll, from
`fills`.** Unsigned, non-evaluative, and the only quantity on the desk that
answers "what have I already done tonight" at the moment it matters.
`/bets` is where the net lives, and it stays there.

Build spec:

- **Unit of "a bet" is a distinct `ticker`**, not a fill row — a partial
  fill is not a second decision. Render `n` markets; ignore the fill count.
- **Stake = `SUM(count * price_tenths)`** over those fills. Money at risk on
  a binary; the honest denominator.
- **No `source` filter.** ADR 0043's `engine`/`venue_hand` split keeps the
  fee-calibration population clean; "how much have I committed tonight" is
  not that question, and both are money committed. Say so in the comment.
- **Day boundary is `OddsConfig.budget_day_start_utc_hour`** (default
  10:00Z), the same roll the lockout, the odds budget and the risk day use.

**The binding constraint: `MIRROR_INTERVAL_S = 12 * 3600` — fills are
mirrored twice a day.** A strip reading the fills table at 8pm on a 10am
mirror renders "no bets tonight" while Joe has three on — a false negative
in the flattering direction, on the one screen whose purpose is to interrupt
him. Disqualifying. Two changes, both required:

1. **Poll fills on the balance cadence** — a fills-only pass beside
   `poll_balance` in `poll_portfolio_forever` at 300s. Keep the 12-hour
   mirror exactly as registered for settlements, positions and
   `run_match_pass` (the matcher is study machinery, registered clock).
   Record in the comment that this is **not an amendment**: the registration
   sets a cadence floor for completeness; polling more often can only make
   the mirror more complete. Kalshi's API is unmetered.
2. **Stamp the strip and refuse when stale.** `as_of_ms` = most recent
   `poll_log` row with `endpoint='fills' AND ok=1`. Null or older than
   **30 minutes** (6× cadence — survives two failed polls, too tight for an
   evening to hide in) → count and stake render `null` → "not read since
   HH:MM", never `0`. None-never-0 applied to a display; the guard that
   survives if the cadence regresses.

## (b) The screen: the landing screen only — `frontend/src/app/slate/page.tsx`

`/` is a re-export of it, so one edit covers both, and it already carries
the money line the strip belongs beside (cash / open positions /
daily-loss). Not `/board` — one tap away, output empty for 1,005 passes.
Not `/market` — the pre-commitment moment is arrival, not mid-market, and a
self-control display on three screens is a nag that gets tuned out inside a
week. If he later reaches Kalshi without passing the landing screen, that is
a real finding — but there is no client-side nav telemetry to establish it,
so no follow-up measurement is promised.

Payload: a **new sibling key `tonight`** on `/api/slate`, not a widening of
`money` (whose contract is about never summing — do not put a different kind
of number inside it):

    "tonight": {
      "day_start_ms": int,
      "as_of_ms": int | null,          # last ok fills poll
      "bets": int | null,              # distinct tickers; null when stale
      "staked_tenths": int | null,
      "staked_display": str | null,    # server-rendered
      "lockout_until_ms": int | null
    }

`lockout_until_ms` rides here for the reason the study payload gave: the
strip that renders tonight is the strip that renders the lockout — one
fetch, one state, no second poller.

## (c) The lockout post-study: render-only, desk-named routes, honest copy

It cannot stop a hand bet in the Kalshi app, and pretending otherwise is the
flattering direction. What it *can* do is what the tilt review valued: make
the recognition concrete at the moment of arrival, and record every reach
for it — `self_lockouts` is append-only and that record's value survives
complete without enforcement.

- **New route `POST /api/desk/lockout`.** Same table, same clock-derived
  release, still no disengage and no duration picker.
  `frontend/src/app/lockout/route.ts` repoints its upstream one line.
- **Leave `POST /api/estimates/lockout` and `lockout_until_ms` on
  `/api/estimates/stop` in place**, deprecated in the docstring, pointing at
  the new route. Both read one table, so they cannot disagree. The 423 on
  `POST /api/estimates` is a working guard with a passing test — not spent.
- **The landing banner does not hide the slate and has no "show anyway"** —
  a show-anyway is a disengage in a costume, and suppressing the screen
  would push him to the Kalshi app with *less* information. It renders above
  the rows, states the release time, and says plainly it cannot stop him at
  the venue — a note from the version of him that decided.
- **No engagement counter.** A lockout tally reads as a score in both
  directions.

## Re-ranking

- **Numbering collision in `tasks/NEXT.md`** (two lists, two numberings) —
  refer to work items by NAME from here on.
- **Promote "strip the landing screen"** (edge point estimate off,
  dispersion-as-range behind a tap) to immediately after the refusal/lockout
  work — same file, and shipping the honest number under a discredited
  precise one would undercut it.
- **Demote and re-scope "CLV on his own bets"**: per-bet rows only — your
  price, Kalshi's close, the difference — **no average, no hit rate** until
  n ≥ 30 with the per-group view beside it. Read n before the effect size,
  on his own money.
- **Drop the nav-swap clause** of the ticket cleanup (Scout took the sixth
  slot; the swap no longer exists). Dead-code removal + "Ledger" rename stay
  as one janitorial slice, last.
- **Not doing, explicitly:** no settlements-based "tonight" figure anywhere;
  no lockout on `/market` or `/board`; no `GET` lockout route; no amendment
  to `MIRROR_INTERVAL_S` for settlements or the matcher.
