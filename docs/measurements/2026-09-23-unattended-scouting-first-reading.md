# Unattended scouting, first reading — the budget day `20260922` classified under the registration of 2026-09-21

**Status: SKELETON — written 2026-09-22 ~20:40Z, before any row of the target
day could be read.** Every datum below is `<TO FILL>`. This file exists now so
that (i) the §8 destination is on disk before the data, (ii) all five outcome
branches are written down before one of them is true, and (iii) the VOID checks
come first on the page and cannot be skipped by filling forward. The session
that fills it is the 2026-09-23 result-doc session (#136 Done-when 4). Anything
in this file that is not a slot is quoted from, or points at, the registration:
`docs/measurements/2026-09-21-preregistration-unattended-scouting-first-reading.md`
(Amendment 1, 2026-09-22 ~19:40Z, is in force). Ticket: #118; arms: #136.

**What this document is.** A census of one agent budget day, `20260922`
(2026-09-22T10:00:00Z → 2026-09-23T10:00:00Z), `n = 1`, classified into
exactly one of the registration's five outcomes by §5's rule. It is not a rate
and it is one look (§5, "Multiplicity and looks").

**What it does not establish** is §4 of the registration, quoted verbatim in
§4 below, and nothing in this file may soften it.

---

## 0. VOID checks — decided first, before any outcome is read

§3 has exactly three criteria and there is no fourth. Each is answered
yes/no from the reads in §1 and the deploy record, **before** §2 or §5 is
filled. If any is YES the outcome is **E** and §6 applies; nothing further is
classified for `20260922`.

| # | criterion (§3, verbatim in short) | how it is read | answer |
|---|---|---|---|
| (a) | `spend.day_start_ms` at T1 is not 2026-09-22T10:00:00Z (= `1790071200000`) | A1.2: (a) fires exactly when **no** read from either arm before 09:55:00Z carries that `day_start_ms` — the T1 selection in §1 returns nothing | `<TO FILL: YES/NO>` |
| (b) | any `keyless` row on `20260922` in `scout-watch-log` | the T2 `scout-watch-log` read, day `20260922`, outcome column | `<TO FILL: YES/NO>` |
| (c) | a deploy inside the target day changed any `AGENT_MAX_*` or `SCOUT_AUTO_*` value | `git log a56847f..<live sha at 10:00Z 09-23>`; `flyctl releases`; `git diff` of `fly.live.toml` between them. Known at skeleton time: the only deploy inside the day is `a56847f` at 15:48Z on 09-22 (run `35749807997`), `git diff eec635e a56847f` touches no such value (NEXT.md forty-fifth entry §3); the hold on `32b5dce`+ until after 14:00Z on 09-23 is what keeps this NO | `<TO FILL: YES/NO>` |

**VOID?** `<TO FILL: YES → outcome E, go to §6 / NO → continue>`

**Read-time context that is NOT a void criterion, stated so nobody promotes
it to one:** the 15:48Z deploy on 09-22 restarted the runner, which resets
`scout_watch_log.cycle_count`. §3 reports `cycle_count` as a *duration proxy*;
one discontinuity sits inside the day at `<TO FILL: the cycle_count values
either side, from the T2 read>`. This biases the duration reading downward for
the outcome that was standing at 15:48Z and voids nothing.

---

## 1. Every read taken, both arms — the A1.2 table

A1.2, verbatim: *"T1 is the latest successful read, from either arm, whose
trusted wall-clock is strictly before 2026-09-23T09:55:00Z and whose
`spend.day_start_ms` equals 2026-09-22T10:00:00Z. That read's trusted
wall-clock is `T1_ms`, and its `tokens_today` and `searches_today` are `K`
and `S`. Every read taken, from both arms, is printed in the result document
with its arm, its trusted wall-clock and its `day_start_ms`; a read at or
after 09:55:00Z, or carrying a different `day_start_ms`, is not T1 and is
printed as context only."*

Where the reads come from:

- Arm A: `gh run list --workflow measure-118.yml --limit 20`, then
  `gh run download <id>` for each; the artifact is named `118-<trip>-<run id>`
  and the run's own timestamp is GitHub's clock. The script also prints a
  `STAMP` line with `github_date=` from the `Date` header.
- Arm B: `%LOCALAPPDATA%\kalshi-cockpit\118\t1-<epoch>.txt` and
  `t2-<epoch>.txt`; the `STAMP` line's `github_date=` is the trusted clock,
  **never** the filename epoch or the machine clock.
- A read is "successful" when the script exited 0, i.e. `day_start_ms`
  appeared in the output (`scripts/measure_118_trip.sh`, the exit-1 guard).

### 1.1 T1-window reads (every one, qualifying or not)

| arm | run / file | trusted wall-clock (GitHub `Date`) | HTTP | `spend.day_start_ms` | before 09:55:00Z? | `day_start_ms` = 1790071200000? | qualifies |
|---|---|---|---|---|---|---|---|
| A | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` |
| B | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` |

(Add one row per read. Expected fires: Arm A 09:02/09:17/09:32/09:47Z, late
by GitHub's usual margin; Arm B 09:05/09:20/09:35/09:50Z if the laptop woke.
A fire that did not happen is a row saying so, not a missing row.)

**T1 = the latest qualifying row above:** `<TO FILL: arm, run/file>`.

| quantity | value at T1 |
|---|---|
| `T1_ms` (trusted wall-clock) | `<TO FILL>` |
| `spend.day_start_ms` | `<TO FILL>` (must be 1790071200000) |
| `K` = `tokens_today` | `<TO FILL>` |
| `TB` = `tokens_daily_budget` | `<TO FILL>` (expected 500,000) |
| `S` = `searches_today` | `<TO FILL>` |
| `SB` = `searches_daily_budget` | `<TO FILL>` (expected 60) |
| `calls_today` / `calls_daily_budget` | `<TO FILL>` / `<TO FILL>` |
| `calls_unmetered_today` | `<TO FILL>` — reported beside every token figure, per §4 |

If no row qualifies: §0(a) is YES, outcome E, §6.

### 1.2 T2/T3 sets (A1.3: first complete set from one arm's one run after 10:30:00Z)

| arm | run / file | trusted wall-clock | `scout-watch-log` present | `scout-briefings` present | `ladder-fixtures` present | complete set | used |
|---|---|---|---|---|---|---|---|
| A | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` |
| B | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` | `<TO FILL>` |

**T2/T3 set used:** `<TO FILL: arm, run/file>`. Later complete sets are
equivalent (both QueryDefs group on `budget_day_ms`, the day is closed) and are
printed above, not stitched.

### 1.3 Context-only reads (A1.4) — printed, excluded

| what | arm | trusted wall-clock | why excluded |
|---|---|---|---|
| rehearsal t1 | A, run `35775325375` | 2026-09-22 ~19:40Z | outside the T1 window; a day in progress |
| rehearsal t2 | A, run `35775329649` | 2026-09-22 ~19:40Z | outside the T2 window; a day in progress |
| rehearsal t1 | B, `t1-1790106032.txt` | 2026-09-22 19:40:16Z (STAMP) | outside the T1 window; a day in progress |
| `<TO FILL: any other non-qualifying read>` | | | |

No spend figure from a context-only read is written anywhere in this file.

---

## 2. Read `n` first — the T2 readings, before any outcome is looked at

From the T2/T3 set in §1.2. §5: *"confirm the target day appears in
`scout-watch-log` and record `auto_count` / `tap_count` from `scout-briefings`
section A **before** looking at any outcome. Print the per-outcome breakdown
beside any total, and name the largest `cycle_count` contributor."*

- Target day `20260922` appears in `scout-watch-log`: `<TO FILL: YES/NO>`
  (NO is "missing instrumentation, not a quiet watcher", §4.)
- `C` = `auto_count` = `<TO FILL>`; `D` = `tap_count` = `<TO FILL>`
  (`scout-briefings` §A, day `20260922`).

### 2.1 `scout-watch-log`, day `20260922`, every row

| outcome | detail (verbatim) | `cycle_count` | `first_ms` | `last_ms` |
|---|---|---|---|---|
| `<TO FILL>` | | | | |

Largest `cycle_count` contributor: `<TO FILL: outcome, share of the day's
total cycle_count>`. `cycle_count` is a duration proxy, not `n` (§3), and it
carries the 15:48Z discontinuity named in §0.

- `A` = the `refused_allowance` rows: `<TO FILL: count>`;
  `A.first_ms` = `<TO FILL>`.
- `B` = the `refused_budget` rows: `<TO FILL: count>`; each `detail`
  verbatim: `<TO FILL>`. (A `refused_budget` row's `detail` carries the spend
  figure at that refusal, §4; copy it whole.)

### 2.2 `scout-briefings`, day `20260922`

Sections A, B, C as printed: `<TO FILL>`. Section C is **not** a refusal
count (§4, "Pre-flight refusals are structurally absent").

### 2.3 `ladder-fixtures` (T3) — the demand side

`<TO FILL: as printed>`. Needed only to separate outcome A's "supply or
freshness" reading from the rest.

### 2.4 `20260921` — OUT, printed separately, never pooled

Partial day: the flag went true ~14:15Z, so 3.75 h of 24 (15.6%) predate the
feature. Its rows, labelled partial: `<TO FILL>`.

### 2.5 `20260923` — OUT, in progress at read time

Quoted only as read-time context, labelled incomplete, never counted:
`<TO FILL or "not quoted">`.

---

## 3. The deduction's coverage

§5's monotonicity argument covers only rows with `first_ms <= T1_ms`.

- Rows with `first_ms <= T1_ms`: `<TO FILL>`
- Rows with `first_ms > T1_ms` (uncovered, reported as such): `<TO FILL>`
- `K < TB`? `<TO FILL: K, TB, YES/NO>`
- `S <= SB - 36`? `<TO FILL: S, SB - 36, YES/NO>`
- `A.first_ms <= T1_ms`? `<TO FILL: YES/NO/n.a. (A empty)>`

---

## 4. What the reading may NOT claim — §4 of the registration, verbatim

<!-- §4 VERBATIM BLOCK BEGIN — spliced from the registration by line range; do not edit here -->
To be quoted verbatim in the result document.

- **Not a rate. `n` = 1 budget day.** It is a census of 2026-09-22. "The
  allowance binds first" as a general statement is not supported by it and may
  not be written. §0 shows no `n` would support it either.
- **Spend at the instant of a `refused_allowance` is unreadable.** There is no
  committed reader of `agent_calls` anywhere in `scripts/` — the only mention
  of the table in that directory is the `scout-watch-log` docstring saying
  `agent_calls` is the meter (`scripts/inspect_live_db_parlays.py:1008`). T1
  is a *snapshot at one later instant*, not a spend-at-refusal reading, and
  the §5 rule uses it only through the monotonicity argument stated there.
  One narrow exception, and it does not help in the masking case: a
  `refused_budget` row's `detail` is `refusal_reason`'s own sentence and
  therefore carries the spend figure at that refusal verbatim (and, because
  `detail` is part of the row's unique key, a changing spend figure fragments
  into new rows). But a `refused_budget` row exists only when the allowance
  did **not** bind first — precisely the case where masking is not in
  question.
- **Joe's refused taps are deliberately unrecorded.** A tap against an
  exhausted day raises `HTTPException(429)` at
  `backend/api/routers/scout.py:277` and writes nothing, before the `INSERT`
  at `:278`. So no reading here bounds how often he was turned away, and a
  day with no tap rows is not a day he did not try.
- **Pre-flight refusals are structurally absent from `scout_briefings`.** A
  row reaches `status = 'refused'` only via a desk run that had already
  started (`agents/scout_desk.py:441` → the `UPDATE` at
  `routers/scout.py:189`). Section C of `scout-briefings` is not a refusal
  count and must not be totalled as one.
- **`scout_watch_log` can undercount and cannot overcount.**
  `record_watch_outcome` swallows its own write failures so it can never fail
  the decision it records. A missing row is unreadable, not zero. It cannot
  misname which ceiling bound.
- **There is no history before 2026-09-21 and there will be no backfill.** The
  table arrived with schema v53. An empty or short history is missing
  instrumentation, not a quiet watcher.
- **A day with no rows is not a day nothing happened.** Neither query can tell
  "nothing convened" from "the recorder was down" — the caveat `credits-day`
  carries for `api_credits`.
- **`tokens_today` may undercount actual tokens** — `calls_unmetered_today`
  counts today's calls whose usage never came back. This does **not** weaken
  §5's deduction, because the brake at `budget.py:289` reads the same
  undercounting field; the deduction is about *whether the brake would have
  fired*, which is exact. It does forbid any claim about what the day
  genuinely cost. Report `calls_unmetered_today` beside every token figure.
- **Nothing about briefing quality.** `convened` means the desk was sent.
  Whether any briefing was useful is not in scope and no sentence about
  usefulness may appear.
- **Nothing about the public surface.** `fetch_live_route.py` reads the
  backend loopback, not what a phone renders.
<!-- §4 VERBATIM BLOCK END -->

---

## 5. Outcome — exactly one, decided in §5's order; NONE SELECTED AT SKELETON TIME

The five branches are written out before any is true. The filling session
marks exactly one `SELECTED` and leaves the other four standing with
`not selected — because <which condition failed>`, so the reader can check the
partition was applied and not chosen.

### A — NEITHER CEILING WAS REACHED — `<TO FILL: SELECTED / not selected — because …>`

Condition: `A` is empty and `B` is empty.
Reading if selected: the day was limited by supply or freshness, not by a
ceiling. Report the `no_candidate` `cycle_count` and the `ladder-fixtures`
reading beside it: `<TO FILL>`.
§8 consequence, verbatim: *"nothing; #127 is closed as moot with the supply
reading attached"* — killed: *"the premise that a ceiling is what limits the
night"*. #127 is decision-relevant under A.

### B — ALLOWANCE BOUND, AND IT BOUND ALONE (H1 supported; masking FALSIFIED) — `<TO FILL>`

Condition: `A` non-empty, `B` empty, `A.first_ms <= T1_ms`, `K < TB`,
`S <= SB - 36`.
Reading if selected: deductive, not statistical — at every recorded allowance
refusal, neither the token nor the search brake would have fired. Report
headroom `TB - K` = `<TO FILL>` tokens and `SB - 36 - S` = `<TO FILL>`
searches, and `floor((TB - K) / 170350)` = `<TO FILL>` further convenings the
token ceiling would have permitted — **an estimate resting on day one's single
cost observation, not a measurement.**
§8 consequence, verbatim: *"#127 gets a concrete one-knob proposal: raise
`SCOUT_AUTO_MAX_CONVENINGS_PER_DAY` to a named number with the measured token
headroom beside it"* — killed: *"the belief that the allowance is
decorative"*. The knob sits inside the `AGENT_MAX_*` ceilings and is never
additive to them (`fly.live.toml:511` rule untouched).

### C — A BUDGET CEILING BOUND, AND IT IS NAMED — `<TO FILL>`

Condition: `B` non-empty.
Reading if selected: each `detail` verbatim, and which ceiling each names —
tokens `<TO FILL>`, calls `<TO FILL>`, web searches `<TO FILL>` — as three
separate counts, never one "budget refusal" total. The allowance masked
nothing on that day.
§8 consequence, verbatim: *"a ticket for Joe on whether the three
`AGENT_MAX_*` move together, with the verbatim `detail` as evidence"* —
killed: *"raising the allowance as a cheap lever — it buys nothing"*.
(Opening that ticket follows CLAUDE.md workflow step 7 — a sub-issue of map
#3 with its number in the handoff line — and it is a ninth ticket, not a ninth
entry in the frozen digest.)

### D — NOT SEPARABLE (masking possible, NOT established) — `<TO FILL>`

Condition: `A` non-empty, `B` empty, and (`K >= TB` or `S > SB - 36` or
`A.first_ms > T1_ms`).
Reading if selected: **UNRESOLVED.** The reading is consistent with masking
and cannot distinguish it from an allowance that bound first on merit. The
sentence "the allowance masks the token ceiling" is not written. §0 of the
registration says repeating the reading cannot escape this; the instrument
that would is §6 of the registration (an `agent-spend` QueryDef over
`agent_calls` with cumulative sums, or recording the ladder's state on a
`refused_allowance` row — the latter touches `scout_watch.py`, which #118 may
not).
§8 consequence, verbatim: *"a ticket for the §6 instrument"* — killed: *"this
measurement's ability to answer #127 — stated plainly, not buried"*. #127 is
**not** decision-relevant under D; say so.

### E — VOID — `<TO FILL>`

Condition: any §0 criterion YES.
Reading if selected: no outcome for `20260922`; the reason is recorded in §6
and §7's one slip applies.
§8 consequence, verbatim: *"nothing; one retry under §7"*.

**Asymmetry, registered:** B and C falsify masking (differently); D neither
confirms nor falsifies; **no outcome confirms masking** and this file may not
report one as if it did.

**Outcome for `20260922`: `<TO FILL: one letter>`.**
**Is #127 decision-relevant under it?** `<TO FILL: yes under A/B/C, no under D, n.a. under E>`

---

## 6. If the day slipped (§7) — filled only if §0 was VOID or a window was missed

§7: one registered fallback, `20260923` (T1 on 09-24 09:00–09:55Z, T2 on
09-24 10:30–14:00Z), under the same document; at most one slip; a second miss
closes the reading as not taken, which is itself the reportable result.

- Reason for the slip: `<TO FILL or "no slip">`
- Crons and tasks re-dated (not re-derived): `<TO FILL: commit>`
- Second attempt outcome: `<TO FILL or n.a.>`

---

## 7. What this reading spent

Nothing on the target day: `GET /api/scout` is two SELECTs and
`today_summary` (`backend/api/routers/scout.py:325`, `:358`;
`backend/agents/budget.py:222`), the three QueryDefs are `cost=CHEAP`, no
tap was made, no live DB instrument beyond §2's three was run. Actions minutes:
`<TO FILL: sum of the measure-118 runs' durations>`.

---

## 8. Closing checklist for the session that fills this file (#136 Done-when 4)

- [ ] §0 answered before §2 or §5 was read.
- [ ] §1.1 lists every T1-window fire from both arms, including fires that did not happen.
- [ ] `T1` is the **latest** qualifying read, not the first and not the cleaner-looking one.
- [ ] §4 block still byte-identical to the registration (`diff <(sed -n '177,225p' <registration>) <(sed -n '185,233p' <this file>)` was empty at skeleton time).
- [ ] Exactly one §5 branch `SELECTED`; the other four say which condition failed.
- [ ] `calls_unmetered_today` printed beside every token figure.
- [ ] No sentence about briefing usefulness; no sentence about the phone's rendering.
- [ ] No rate; no pooling with `20260921` or `20260923`.
- [ ] `measurement-skeptic` has read this file before the outcome letter is copied to #118 / #127.
- [ ] **Same commit:** delete `.github/workflows/measure-118.yml` and both laptop tasks (`schtasks //Delete //TN Kalshi118T1 //F`, same for `Kalshi118T2`) — the cron fires again next 23 September if left. Amendment 1's Done-when 4.
- [ ] Status line at the top of this file changed from SKELETON to the outcome; the "written before any row" sentence kept as history, dated.
- [ ] **Only then** deploy `32b5dce` or later, after 14:00Z on 09-23; read `/api/hedge` once afterwards for the settled/live split, write no count (ADR 0162).
- [ ] Handoff: the outcome letter, the #127 consequence (or its non-relevance under D), and any new ticket by number, in the workflow-step-7 form.
