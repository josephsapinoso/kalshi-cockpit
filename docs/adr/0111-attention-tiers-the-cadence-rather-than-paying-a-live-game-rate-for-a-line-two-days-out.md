# ADR 0111 — Attention tiers the cadence rather than paying a live-game rate for a line two days out

- **Status:** ACCEPTED
- **Date:** 2026-09-07
- **Supersedes:** nothing. Amends the mechanism ADR 0071 §2.6 introduced.
- **Touches:** `backend/odds/timing.py` (`desk_wants`,
  `DESK_ATTENTION_FAST_HORIZON_MS`), `tests/test_desk_follows_attention.py`.
  No schema change, no config change, no route change, no screen change.

## The decision

While someone has the desk open, a sport is bought at the ten-minute cadence
**only if it plays inside twelve hours**. Beyond that it is still bought — at
the floor's hourly rate. It is never dropped.

Before this, the attended branch of `desk_wants` had no horizon at all: every
sport inside the *caller's* 48-hour `horizon_ms` re-bought every ten minutes.
The floor branch, one line below, had always checked
`soonest - now_ms > floor_horizon_ms` and skipped. The asymmetry was not a
decision; it was the branch nobody had needed to bound yet.

## Why now: the third sport is what makes it bite, and it arrives tonight

The attention slice is `DEFAULT_ATTENTION_DAILY_CREDITS = 300` a day, and a
sport on the ten-minute cadence costs six calls an hour at the deployed
`cost = 4`:

| sports inside 48 h | credits/hour | attended hours the slice funds |
|---|---|---|
| 2 | 48 | 6.25 |
| 3 | 72 | **4.17** |
| 4 | 96 | 3.13 |

Against that, the measured record. Attended minutes per budget day over the
nine days 20260825–20260902 ran **2.6 to 324** with no trend, and 20260827 —
the only day the slice has ever run out — spent the whole 300 in **4.88 hours**
(`docs/measurements/2026-09-03-desk-dwell-and-the-watcher-off-switch.md`).

**So the third sport alone takes Joe's attended budget below a day he has
already had.** And the third sport arrives by construction: NFL enters the
48-hour set at **03:35Z on 2026-09-08**, when its soonest Kalshi event crosses
the bootstrap horizon — with its kickoff about **45 hours** away. Under the old
branch that is a full day of live-game cadence on a line that moves on a daily
timescale, before it can price a single bet Joe could place.

The consequence is not a bigger bill. The slice is a hard cap and it holds:
what happens is that the slice runs out *earlier in the day*, and past it every
sport falls through to the hourly floor. The day is safe by the cap — as
`CLAUDE.md` now says of the whole 700 — and what the cap protects is the
budget, not the reading.

## Why a tier and not a cut, which is the part worth arguing

The obvious fix is to give the attended branch the floor's horizon and be done.
It was rejected, and the reason is in this repo's own test suite:
`test_attention_overrides_the_horizon` records the standing rule that

> Someone looking at a slate wants it priced, and the tool does not get to
> decide their fixture is too far away to be interesting.

That rule is about **whether** a far fixture is priced. It stays. This ADR is
about the **cadence** it is priced at, which the rule never spoke to.

A 12-hour cut would have been actively wrong under ADR 0071. Joe bets Sunday's
NFL on Friday; the desk's job at the moment of a bet is price transparency.
Cutting would leave Sunday's rows unbought for two days, past
`max_odds_age_s`, so the desk would go dark on exactly the fixtures he opened
it to look at — the same shape as the 2026-08-29 defect where *keeping the page
open was what suppressed the buying*.

Hourly is 4 credits an hour instead of 24, one sixth of the cost, and is well
inside the staleness gate for a line nobody is transacting on yet.

With one sport playing today and two playing tomorrow, the slice funds **9.38**
attended hours instead of 4.17 — past every dwell in the nine-day record.

## The alternative that was checked and is not available

The partner agent proposed a **viewed-sport filter** instead of a horizon: buy
fast for the league Joe is actually looking at. That would be better, and the
stored record cannot support it. `desk_attention` is `(id, seen_ms, path)`, and
`attention.normalise_path` **strips the query string** —
`normalise_path` splits on `?` and `#` before storing — so
`/board?league=americanfootball_nfl` is stored as `/board`. The record carries
which *screen*, never which *league*.

Making it available is a frontend change plus a column plus a migration, and it
would still only cover the case where a league filter is applied. Not taken
here. If the tier ever proves too blunt, that is the next lever and this
paragraph is where it starts.

## What this deliberately does not change

- **The slice and the floor do not move.** `DEFAULT_ATTENTION_DAILY_CREDITS`
  is still 300; `DESK_FLOOR_INTERVAL_MS` is still hourly;
  `DESK_FLOOR_HORIZON_MS` is still 12 h. The two capped terms in `CLAUDE.md`
  (~384 floor, ≤300 slice) are arithmetic over constants none of which moved,
  so **no published figure changes**. What changes is how quickly the slice is
  consumed inside its own cap.
- **The first buy of a sport is not delayed.** The tier paces *re-buying*: it
  is applied to `cadence_ms`, which is measured from `last_sweeps`, and a sport
  with no served sweep still returns `now_ms` through the bootstrap branch.
  Tonight's NFL bootstrap is untouched by this ADR.
- **The kickoff-window slot planner is untouched**, and it remains the largest
  of the three spenders — 67.0% of September's served sweeps, gated only by
  `credits_left`. Nothing here reduces the Sunday 09-13 exposure that comes
  from the window loop; see `CLAUDE.md`'s credit table, whose fourth row is
  still the only real ceiling.
- **`DESK_ATTENTION_FAST_HORIZON_MS` is equal to `DESK_FLOOR_HORIZON_MS` by
  value and not by reference.** They answer different questions — what the
  floor reaches at all, versus what attention pays a premium for — and either
  may move without the other. A test asserts the source does not define one in
  terms of the other, because defining it by reference is how a later edit
  moves both by accident.

## What would falsify this

- **Joe reports Sunday's NFL prices reading stale on a Friday.** The tier is
  wrong in the direction it was designed against, and the answer is the
  viewed-sport filter above, not a bigger horizon.
- **The slice still exhausts on a three-sport day.** Then the fast tier is not
  where the money went, and `credits-day --date … ` by trigger says where it
  did — the kickoff-window loop carries a NULL trigger and is six times larger
  than either capped term.
- **A sport turns out to be listed with `commence_ms` far in the future for
  fixtures that are actually today.** The tier reads `min(commences)`, so this
  would demote a live sport. Nothing observed suggests it; the read is from
  `odds_snapshots`, whose kickoff is the sportsbook's own and is the one this
  module was built to anchor on.

## Evidence

- Verified by reading, not inferred: `desk_wants`' attended branch set
  `cadence_ms = refresh_interval_ms` with no horizon test, while the `else`
  branch applied `floor_horizon_ms` and `continue`d.
- `DEFAULT_HORIZON_MS = 48 h`, `DESK_FLOOR_HORIZON_MS = 12 h`,
  `DESK_FLOOR_INTERVAL_MS = 1 h`, `DEFAULT_ATTENTION_DAILY_CREDITS = 300`.
- `upcoming_fixtures_by_sport` reads `odds_snapshots` bounded by the caller's
  `horizon_ms`, so 48 h is the attended branch's effective reach.
- Dwell: `docs/measurements/2026-09-03-desk-dwell-and-the-watcher-off-switch.md`.
- Four mutants, all red: the tier removed; the tier turned into a `continue`
  (which also reddens the pre-existing `test_attention_overrides_the_horizon`,
  so the standing rule guards itself); the boundary moved by one; and
  `min(commences)` turned into `max`.
