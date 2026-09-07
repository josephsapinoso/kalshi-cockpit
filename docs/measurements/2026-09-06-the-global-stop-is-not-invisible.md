# The global budget stop is not invisible on both surfaces — one of the two, and not the one named

**Taken 2026-09-06**, by tracing the deployed code on `main` at `4a6d63e` (the
sha `/api/health` reports for both live and demo). No live database was read
and no credit was spent; every claim below is a citation plus one synthetic
exercise of the query under test.

---

## The claim under test

`tasks/NEXT.md`, open item 3, in its own words:

> **The global stop is invisible on both surfaces** — if 700 binds,
> `decide_sweeps` returns `fire=()` and every sport stops, and a refused sweep
> writes no `api_credits` row, so exhaustion reads as an *absence*.

and, in the fuller form at the 2026-09-06 third entry:

> Post-hoc read exists: `credits-day --date 20260913` plus `sweep-log` filtered
> on `outcome='refused'`.

**Verdict: the first sentence is false as written, and the recommended
instrument in the second is the actual defect.** The item was funded as a
falsification before a build, on the partner's ranking, and the falsification
is most of the result.

---

## 1. What the planner does when the cap binds — confirmed

`backend/odds/timing.py:1835-1845`. When `remaining == 0`, `decide_sweeps`
returns `fire=()` with a detail string:

```
no sweep: {spent} of {budget} credits spent since {HH:MM}Z,
which is not enough for another {cost}-credit call
```

`backend/runner.py:2393-2396` writes that string to `odds_sweep_log`:

```python
if not decision.fire:
    record_sweep_outcome(
        conn, pass_ms=now, outcome=SKIPPED, detail=decision.detail
    )
```

So a stopped pass **is** recorded, with the budget named. That is the half the
claim gets wrong.

## 2. The screen is not silent — REFUTED

`timing.py:1578-1579` carries the row to `ActionableWindow` as
`last_look_outcome` / `last_look_detail`; `timing.py:1382-1383` serialises both;
`frontend/src/lib/api.ts:1220-1221` types them; and
`frontend/src/components/WindowBanner.tsx:318` renders `detail={w.last_look_detail}`
on `/board`. **The budget sentence reaches the screen verbatim.**

The tone is `warn`, but it is reached by the wrong branch and that is worth
recording. `frontend/src/lib/sweepTone.ts:168` fires on
`last_look_outcome === "refused" || === "failed"`, which a `skipped` row does
not match. It reaches `warn` two branches later, on *"nothing swept and a
window has opened"* — the generic 17-hour-outage shape. `WindowBanner.tsx:244-251`
already comments that slot planning is unfiltered by budget, so an exhausted
day still computes a first window and this fallback is guaranteed to fire.

**Consequence, and it is minor: a budget exhaustion and a dead recorder produce
the same colour**, separated only by the detail text underneath. Not built
against here. The operator's action differs (wait for the 10:00Z rollover
versus investigate the recorder), so it is a real if small gap; it is recorded
rather than fixed because the words already distinguish the two and the colour
is correct in both cases.

## 3. The post-hoc read is the defect — CONFIRMED, and it is the recommendation itself

Two facts that only bite together:

- `REFUSED` is written **only** behind `budget.refusal_reason`, at
  `backend/odds/client.py:343-352`, which runs inside `fetch_odds`. It requires
  a call to have been attempted.
- Once `remaining == 0`, no call is attempted for any sport, so `fetch_odds` is
  never entered. `backend/runner.py:127` imports `NO_DATA, SERVED, SKIPPED` and
  **never imports `REFUSED` at all.**

So a day on which the cap binds produces **one** `refused` row — the single
pass that ran out mid-flight, via `client.py` — and then `skipped` rows for the
entire remainder of the budget day.

`sweep-log` filtered on `outcome='refused'` therefore finds the *instant* of
exhaustion and misses the *state*. On a cap that binds at 15:40Z that is one
row against roughly sixteen hours. And `sweep-log` is not day-scoped at all:
`_SQL_SWEEP_LOG_GROUPS` takes no parameters
(`scripts/inspect_live_db_feed.py`), so it groups over all time and cannot be
pointed at 20260913.

The same trap is already documented one function away, for a different cause —
the `refused_sweeps` note on `visit-freshness` warns that a slice-spent sport
"reaches this log only as `skipped`". The daily cap does the same thing and
nothing said so.

**This also means the vocabulary is being used against its own definition.**
`backend/odds/sweeplog.py:71-88` defines them explicitly: *"`REFUSED` means the
budget declined — **we** stopped. `SKIPPED` means the pass chose not to look."*
The global cap stop is the budget declining, and it is written as `SKIPPED`.

## 4. `credits-day` shows the absence — CONFIRMED

`_q_credits_day` read `api_credits` and nothing else: three sections, all from
one table. A refused or unattempted call writes no row there, so the day's rows
simply stop — byte-for-byte what a quiet slate looks like.

---

## What was built

`credits-day --date` gains two `odds_sweep_log` sections scoped to the **same**
budget-day window it already computes:

- what the passes decided that day, by outcome;
- refusals and skips grouped by the **reason they name**, which collapses the
  hundreds of identical rows a stopped day produces into one line with a count
  and a span.

Both outcomes, deliberately: the pair is the reading. Exercised against a
synthetic exhausted day (175 calls to exactly 700 credits, then one `refused`
at 15:49:35Z and 196 `skipped`):

```
api_credits: row count and summed cost for that day
    (175, 700)
odds_sweep_log: what the passes decided that day, by outcome
    ('skipped', 196, 15:20:00Z -> 07:35:00Z next day)
    ('served',    3, 10:20:00Z -> 12:20:00Z)
    ('refused',   1, 15:49:35Z)
odds_sweep_log: refusals and skips that day, grouped by the reason they name
    ('skipped', 196, ..., 'no sweep: 700 of 700 credits spent since 10:00Z,
                           which is not enough for another 4-credit call')
    ('refused',   1, ..., '700 of 700 credits spent today; ...')
```

Five tests in `tests/test_inspect_live_db.py::TestCreditsDaySaysWhetherTheCapBound`,
including a vacuity guard that asserts the section is empty on the same
database without the seeded stop. **All four guards were mutated and all four
went red** — dropping `'skipped'` from the `IN` clause, removing the day scope
from either query, and dropping the sections from the return list. The mutation
harness restored from a byte copy, never `git checkout` (`tasks/lessons.md`,
2026-09-06).

## What this does not establish

- **Nothing has been observed on a real exhausted day.** The cap has never
  bound on this instance; the exercise above is synthetic and asserts the
  query's shape, not the live record's. The first real test is 2026-09-13 if
  the NFL Sunday projection is wrong.
- **It does not measure how likely the cap is to bind.** That is the four-sport
  budget-day question, still open.
- **It says nothing about whether the stop is the right behaviour.** Stopping
  every sport rather than the one that overspent (`timing.py:1835`) is a design
  choice this document does not review.
- **The tone collision in §2 is unfixed**, and no test pins it either way.
