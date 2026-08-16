# 0031 — The refresh is also a button, and a tap is not a schedule

**Date:** 2026-08-16
**Status:** Accepted.
**Owns:** the on-demand odds refresh — `backend/odds/ondemand.py`, the `MANUAL`
trigger and `ManualRefresh` in `odds/timing.py`, `api_credits.trigger` (schema
v9), `POST /api/odds/refresh`, `GET /api/odds/refreshable`, the Next route
handler at `/refresh-odds`, and the panel on the Board and the Slate.
**Does not touch** `MAX_ODDS_AGE_S`, still 900. It does not relax a threshold;
it buys newer odds to put *inside* the existing one.
**Related:** ADR 0030, which this completes rather than replaces — 0030 owns
*when the planner* re-buys; this owns *when a person* does. ADR 0025, whose
subject (what `stale_odds` means) it again does not re-open.

---

## 1. The question that started it

> *"None of these props are being noticed as something that's better. I just
> want to make sure we're not over-inflating the idea of stale odds — because if
> you collect odds at a particular time and I look at it two or three hours
> later, all of them are gonna be disqualified and none of them are edible. So I
> think the latest odds should be available to me. Is the right answer to
> refresh the odds on demand when I am actually on the website?"*

Two claims and a proposal. The first claim is wrong, the second is exactly
right, and the proposal is what this ADR accepts.

## 2. The claim that is wrong, and it must be stated first

**Props are not being hidden by staleness.** After the cluster-key fix (ADR
0029) the live record carries **200 prop rows in `no_edge`** — priced against
fresh odds, evaluated, and found not to clear the fee. They are not suppressed
as `stale_odds` and they are not structurally excluded from `actionable`.
`actionable` is simply empty, for every market type, as it has been for the life
of this record.

> **Annotation, 2026-08-16 (added after the fact; the line above is left as
> written).** The claim that `actionable` has been zero for the life of the
> record **was false when this was committed.** It became non-zero on
> **2026-08-15T19:52:14Z**, and `gate.population_counts` published that over
> `/api/gate` on every pass from that moment.
>
> The claim came from `clv-coverage`, whose cluster query filters on
> `clv_scored_ms IS NOT NULL`. An actionable row is written *before* commence
> by construction, so the whole class sat outside that denominator until its
> game finished — the instrument could not see the thing being asserted about.
> The last valid whole-table measurement of 0 is ADR 0021's pin, 2026-08-10.
>
> **The decision this ADR makes is unaffected**, which is why this is an
> annotation and not a supersession: the audit found three rows, two distinct
> claims across two games, all three `anchored_on_sharp = 0` and therefore
> unseparated from the soft-book-fallback explanation. Nothing here would have
> been decided differently. Only the supporting sentence was wrong.
>
> See `docs/measurements/2026-08-16-actionable-population-audit-result.md`.


This matters because the natural reading of "make the odds fresher and the props
will show up" is a **prediction**, and it is one this change will appear to have
tested. It has not. Nothing in this ADR is evidence about edge, and no future
session may cite the refresh button as having improved — or failed to improve —
the surfaced count. A fresh price is still a price with no edge in it.

## 3. The claim that is right, and the line that proves it

`backend/api/routes.py`, in `_live_ages`:

```python
"actionable": readable and odds <= staleness.max_odds_age_s * 1000,
```

That is evaluated **at read time**, against the clock at the moment the page is
loaded — not at the moment the row was written. So a row priced perfectly at
14:00 is dead on a screen opened at 14:16, and every row on the slate is dead
together, because they share a sweep. Opening the cockpit two hours before first
pitch produces a fully struck-through board in which nothing is wrong: the games
are real, the prices are real, and a clock has ruled on all of them.

ADR 0030 fixed the write-time half of this — a cluster used to get one buy and
then go stale with the games an hour out. What it deliberately did not do is
cover instants outside a planned slot, because the planner has no reason to
spend there. **A person looking at the screen is that reason**, and it is the
one input the planner cannot predict.

## 4. What a tap buys, and why it is two buttons

| Tap | Calls | Credits |
|---|---|---|
| Team lines, whole slate for one sport | 1 | `markets x regions` = **6** |
| One fixture's player props | 2 | 6 + `prop_keys x regions` = **26** |

The props endpoint is billed per event, so a slate-wide prop refresh on a
13-game night is **338 credits** against a 600-credit day. It is therefore not
offered. The panel exposes props one fixture at a time and prints what all of
them together would cost, because the largest credit accident in this project's
history was a 6-credit request that spent 266 by triggering a per-event tail
nobody had priced.

A prop refresh is quoted at 26 and not 20. `fetch_and_store_props` is only ever
reached from a *served* team sweep and filters against that sweep's slate, so
the team call is part of the purchase rather than an accident of it.

## 5. The defect this had to design around, and it is the whole reason for a migration

An on-demand refresh makes **the identical request the planner makes**, at the
identical cost, against the identical endpoint. `_SERVED_SWEEP` in
`odds/timing.py` identified a served sweep by endpoint and cost alone.

So, without further work:

1. A tap writes an `api_credits` row that looks exactly like a planner sweep.
2. `last_sweep_by_sport` moves that sport's last-sweep stamp to now.
3. If the tap landed after `slot.fire_from_ms`, `firing_for_slot` now returns
   `REFRESH` instead of `SCHEDULED` for the rest of that window.
4. **Props ride the opening call only.**

One tap in the seconds before a window opened would cost that cluster its entire
prop purchase, for the day, and nothing anywhere would record that it had
happened. The tap would look like it worked. The slate would simply have no
props in it.

Schema **v9** adds `api_credits.trigger`, and `_SERVED_SWEEP` excludes exactly
`'manual'`. The column exists **to be excluded, not to be reported** — nothing
reads it for display. `COALESCE(trigger, '')` keeps every pre-v9 row counting as
a sweep, which is what those rows are; backfilling `'scheduled'` would assert a
fact about history this column was not there to observe.

`tests/test_ondemand_refresh.py::TestATapDoesNotStealTheWindowsOpeningCall`
pins it, and the mutation that removes the clause was run and caught.

## 6. Three ceilings, answering three different questions

*Cooldown, 2 minutes per key.* `odds_age_ms` is measured from The Odds API's own
`last_update` — their scrape stamp, not our fetch time — so two calls a minute
apart routinely return the same numbers at the same age. This is not politeness;
below it, a tap buys nothing and is billed anyway. **Keyed on `sport|fixture`**,
so refreshing one game's props does not silence the whole board.

*Manual daily ceiling, 150 of 600 credits.* Taps arrive unplanned; the schedule
is planned ahead against `remaining_today`. Without a sub-ceiling a busy evening
of tapping empties the day and the planner discovers it as a refusal after the
fact. This is the slice the schedule can lose without a cluster going dark.
**Charged on acceptance, not on service** — the runner may still refuse, and
over-counting refuses a tap that would have fit while under-counting authorises
spend that is already gone.

*The real budget.* Read through `CreditBudget.refusal_reason`, the same
implementation the planner spends against. Never a second count of the day.

**If taps routinely hit the 150, the answer is a wider scheduled window, not a
bigger slice.** A tap buys one person one screen; a scheduled sweep buys the
record.

## 7. Single-writer, because the API cannot write the database

`docker/entrypoint.sh` runs uvicorn and the chain runner as separate processes,
and the API opens the database `read_only=True`. A request therefore cannot be a
row. It is a JSON file beside the database, written **only** by the API and read
**only** by the runner, swapped with `os.replace` so a reader never sees a half
written file.

Two processes doing read-modify-write on one file lose updates, and the update
most likely to be lost is the cooldown — the one thing holding the spend down.

The cost of single-writer is that the runner has no durable record of what it
has served, so it holds a watermark in memory, initialised to **process start**.
A restart therefore *ignores* taps that predate it rather than replaying them. A
tap lost to a restart costs the person another tap; a tap replayed costs credits
nobody asked for, and only the first is recoverable by the person holding the
phone.

## 8. The security decision, stated rather than glossed

`lib/session.ts` issues a cookie that proves knowledge of `APP_AUTH_TOKEN`
without carrying it, specifically so a stolen cookie **cannot place an order**.
The ticket makes the operator type the token per order.

A refresh button cannot work that way. It is tapped on a handset, several times
an evening, and a 43-character paste each time is the friction that gets a
feature disabled rather than used. So the Next route handler at `/refresh-odds`
holds the token server-side and authorises on the session cookie.

**What that widens:** whoever holds the cookie can now spend up to 150 credits a
day of a 13,000-credit month. That is real and it is not zero. It is accepted
because the ceiling is enforced server-side and cannot be raised from the
client, and because the alternative is a button nobody can press. **It does not
widen toward money** — the order path still demands the token itself.

## 9. What this does not claim

- **Not that a refreshed row is a bettable row.** See §2. It is not evidence
  about edge in either direction.
- **Not that the aggregator's numbers move on a two-minute scale.** The cooldown
  is sized on the belief that they do not. That belief is **unmeasured**; the
  tests pin the cooldown's mechanics, not its correctness. Measuring it needs
  consecutive `last_update` stamps for one book/event pair, which the record now
  makes possible and nobody has taken.
- **Not that 150 is the right slice.** It is a first number chosen against a
  600-credit day and a 26-credit prop tap. It should be revisited against
  `api_credits` once taps have a history, not argued about beforehand.

## 10. Consequences taken deliberately

- A tap suppresses a same-sport planned sweep on that pass. The window's opening
  `SCHEDULED` call is delayed by one quote cadence (~15s), never lost, because
  the tap left `last_sweeps` untouched. Pinned by
  `test_a_tap_and_a_planned_sweep_both_fire_in_one_pass`.
- `fetch_and_store_props` gains a second way to name a fixture set
  (`only_events`). Both guards it already had step aside when one is given —
  neither was about slots as such, both were about never buying props for a
  fixture set nobody named, and a named set is what they were holding out for.
- The 202-shaped answer is `accepted`, never `refreshed`. The API process cannot
  fetch anything; saying otherwise would be a claim about a call that has not
  been made and may still be refused on budget.
