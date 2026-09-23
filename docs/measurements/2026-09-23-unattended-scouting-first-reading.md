# Unattended scouting, first reading — the budget day `20260922` classified under the registration of 2026-09-21

**Status: OUTCOME D — NOT SEPARABLE (UNRESOLVED). Filled 2026-09-23 ~17:00Z
from reads taken unattended 09:05–10:55Z; nothing voided the day.** One
complete budget day cannot separate these ceilings, and no number of days can
while they coincide — the instrument that would is §6 of the registration,
ticketed as #137 below.

History, kept as written: **Status: SKELETON — written 2026-09-22 ~20:40Z,
before any row of the target day could be read.** Every datum below was
`<TO FILL>` (the slots are now filled; the branch text and §4 are untouched).
This file existed then so that (i) the §8 destination is on disk before the data, (ii) all five outcome
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
| (a) | `spend.day_start_ms` at T1 is not 2026-09-22T10:00:00Z (= `1790071200000`) | A1.2: (a) fires exactly when **no** read from either arm before 09:55:00Z carries that `day_start_ms` — the T1 selection in §1 returns nothing | **NO** — seven reads qualify (§1.1), every one carrying `1790071200000` |
| (b) | any `keyless` row on `20260922` in `scout-watch-log` | the T2 `scout-watch-log` read, day `20260922`, outcome column | **NO** — the day's outcomes are `no_candidate`, `convened` ×3, `refused_allowance`; no `keyless` (§2.1) |
| (c) | a deploy inside the target day changed any `AGENT_MAX_*` or `SCOUT_AUTO_*` value | `git log a56847f..<live sha at 10:00Z 09-23>`; `flyctl releases`; `git diff` of `fly.live.toml` between them. Known at skeleton time: the only deploy inside the day is `a56847f` at 15:48Z on 09-22 (run `35749807997`), `git diff eec635e a56847f` touches no such value (NEXT.md forty-fifth entry §3); the hold on `32b5dce`+ until after 14:00Z on 09-23 is what keeps this NO | **NO** — `flyctl releases` shows one release inside the day, v325 at 15:49Z 09-22 (deploy run `35749807997`, `headSha` `a56847f`); the previous, v324 at 05:25Z (run `35690590949`, `eec635e`), is before 10:00Z. `git diff eec635e a56847f` changes no `AGENT_MAX_*`/`SCOUT_AUTO_*` value anywhere (the only matching lines are prose in `tasks/NEXT.md`). No release between 15:49Z 09-22 and the read at 16:4xZ 09-23 |

**VOID?** **NO → continue.** Decided from the three rows above before §2 or
§5 was filled.

**Read-time context that is NOT a void criterion, stated so nobody promotes
it to one:** the skeleton said the 15:48Z deploy on 09-22 "restarted the
runner, which resets `scout_watch_log.cycle_count`". **That premise was
wrong:** `cycle_count` is a database upsert (`cycle_count = cycle_count + 1`,
`backend/store/scout_watch_log.py:145`), so no restart can reset it. The
`refused_allowance` row's 126 counts over 125.01 intervals of 600 s
(`first_ms` 1790082013383 → `last_ms` 1790157019893 = 75,006,510 ms) are
consistent with an unbroken cadence and do not prove one: `20260921` shows
92 counts over 89.71 intervals across three restarts (v322–v324), so a
restart can add a count, and one lost cycle plus one boot cycle would also
give 126. Whether the 15:49Z restart (v325) cost a cycle is unreadable. It
voids nothing.

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
  appeared in the output (`scripts/measure_118_trip.sh`, the exit-1 guard) —
  that is T1's test. For T2/T3 it is three row-count lines
  (`measure_118_trip.sh:130-139`); flyctl's own exit code is recorded, not
  acted on.

### 1.1 T1-window reads (every one, qualifying or not)

| arm | run / file | trusted wall-clock (GitHub `Date`) | HTTP | `spend.day_start_ms` | before 09:55:00Z? | `day_start_ms` = 1790071200000? | qualifies |
|---|---|---|---|---|---|---|---|
| A | run `35841970776` (started 09:16:34Z) | 09:16:42Z / 09:16:42Z | 200 | 1790071200000 | yes | yes | yes |
| A | run `35843511686` (started 09:32:10Z) | 09:32:14Z / 09:32:14Z | 200 | 1790071200000 | yes | yes | yes |
| A | run `35845257647` (started 09:50:06Z) | 09:50:44Z / 09:50:54Z | 200 | 1790071200000 | yes | yes | yes — **T1** |
| A | fourth cron fire | — | — | — | — | — | **did not happen**: four crons, three runs in `gh run list`; which of the four schedule strings went unfired is not in the list's output |
| B | `t1-1790154302.txt` | 09:05:02Z / 09:05:02Z | 200 | 1790071200000 | yes | yes | yes |
| B | `t1-1790155201.txt` | 09:20:00Z / 09:20:00Z | 200 | 1790071200000 | yes | yes | yes |
| B | `t1-1790156101.txt` | 09:35:00Z / 09:35:00Z | 200 | 1790071200000 | yes | yes | yes |
| B | `t1-1790157001.txt` | 09:50:00Z / 09:50:00Z | 200 | 1790071200000 | yes | yes | yes |

Wall-clock is the script's `STAMP before` / `STAMP after` lines, both from
GitHub's `Date` header (second resolution). Every Arm B read ends
`flyctl_exit=1` with `Error: The handle is invalid.` and `RESULT t1 ok`: the
known exit-1-after-a-good-read of `flyctl ssh` from a Windows task; the
script's success test is `day_start_ms` present, which it was. **All seven
reads carry the identical `spend` object**, and so did the 2026-09-22 19:40Z
rehearsals (§1.3): nothing was metered on the target day after 19:40Z 09-22.

(Add one row per read. Expected fires: Arm A 09:02/09:17/09:32/09:47Z, late
by GitHub's usual margin; Arm B 09:05/09:20/09:35/09:50Z if the laptop woke.
A fire that did not happen is a row saying so, not a missing row.)

**T1 = the latest qualifying row above:** Arm A, run `35845257647`. It is
latest on either stamp (09:50:44Z before / 09:50:54Z after, against Arm B's
09:50:00Z). `T1_ms` takes the **before** stamp — the earlier of the two, so
it covers the fewer rows; no row of the day falls between the stamps, so the
choice changes nothing.

| quantity | value at T1 |
|---|---|
| `T1_ms` (trusted wall-clock) | 1790157044000 (2026-09-23T09:50:44Z) |
| `spend.day_start_ms` | 1790071200000 (must be 1790071200000) |
| `K` = `tokens_today` | 630,719 (`calls_unmetered_today` = 1) |
| `TB` = `tokens_daily_budget` | 500,000 (expected 500,000) |
| `S` = `searches_today` | 30 |
| `SB` = `searches_daily_budget` | 60 (expected 60) |
| `calls_today` / `calls_daily_budget` | 10 / 24 |
| `calls_unmetered_today` | 1 — reported beside every token figure, per §4 |

If no row qualifies: §0(a) is YES, outcome E, §6.

### 1.2 T2/T3 sets (A1.3: first complete set from one arm's one run after 10:30:00Z)

| arm | run / file | trusted wall-clock | `scout-watch-log` present | `scout-briefings` present | `ladder-fixtures` present | complete set | used |
|---|---|---|---|---|---|---|---|
| B | `t2-1790159701.txt` | 10:34:21Z / 10:35:00Z | yes | yes | yes | yes | **yes** |
| A | run `35850434517` | 10:43:35Z / 10:43:35Z | yes | yes | yes | yes | printed |
| B | `t2-1790160601.txt` | 10:49:57Z / 10:50:09Z | yes | yes | yes | yes | printed |
| A | run `35851469176` | 10:54:42Z / 10:54:42Z | yes | yes | yes | yes | printed |

**T2/T3 set used:** Arm B, `t2-1790159701.txt` (first complete single-run set
after 10:30:00Z). Its three commands end `flyctl_exit=1` with the same
exit-1-after-a-good-read as §1.1; all three printed their full tables and the
script reported `RESULT t2 ok (3 of 3 reads)`. The four sets were diffed:
every `20260922` and `20260921` row is byte-identical across them; they
differ only in the QueryDefs' window-start line and in the in-progress
`20260923` `no_candidate` row (`cycle_count` 2 → 3 → 4 → 4), which §3 puts
OUT. Later complete sets are
equivalent (both QueryDefs group on `budget_day_ms`, the day is closed) and are
printed above, not stitched.

### 1.3 Context-only reads (A1.4) — printed, excluded

| what | arm | trusted wall-clock | why excluded |
|---|---|---|---|
| rehearsal t1 | A, run `35775325375` | 2026-09-22 ~19:40Z | outside the T1 window; a day in progress |
| rehearsal t2 | A, run `35775329649` | 2026-09-22 ~19:40Z | outside the T2 window; a day in progress |
| rehearsal t1 | B, `t1-1790106032.txt` | 2026-09-22 19:40:16Z (STAMP) | outside the T1 window; a day in progress |
| none other | | | every T1-window read qualified (§1.1) |

No spend figure from a context-only read feeds §3's conditions or §5; the
rehearsal spend is cited only as an upper bound on the crossing time (§3).

---

## 2. Read `n` first — the T2 readings, before any outcome is looked at

From the T2/T3 set in §1.2. §5: *"confirm the target day appears in
`scout-watch-log` and record `auto_count` / `tap_count` from `scout-briefings`
section A **before** looking at any outcome. Print the per-outcome breakdown
beside any total, and name the largest `cycle_count` contributor."*

- Target day `20260922` appears in `scout-watch-log`: **YES**, five rows.
  (NO is "missing instrumentation, not a quiet watcher", §4.)
- `C` = `auto_count` = **3**; `D` = `tap_count` = **0**
  (`scout-briefings` §A, day `20260922`). §4: a day with no tap rows is not a
  day Joe did not try.

### 2.1 `scout-watch-log`, day `20260922`, every row

| outcome | detail (verbatim) | `cycle_count` | `first_ms` | `last_ms` |
|---|---|---|---|---|
| `no_candidate` | no eligible fixture on the ladder this cycle | 13 | 1790071549908 (10:05:49Z) | 1790080422953 (12:33:42Z) |
| `convened` | sent the desk on KXMLBGAME-26SEP221840WSHDET-DET | 1 | 1790072751032 (10:25:51Z) | 1790072751032 |
| `convened` | sent the desk on KXMLBGAME-26SEP221905TBNYYG2-NYY | 1 | 1790077095667 (11:38:15Z) | 1790077095667 |
| `convened` | sent the desk on KXWNBAGAME-26SEP22CONNWSH-WSH | 1 | 1790081023515 (12:43:43Z) | 1790081023515 |
| `refused_allowance` | 3 of 3 unattended convenings already made today (SCOUT_AUTO_MAX_CONVENINGS_PER_DAY) | 126 | 1790082013383 (13:00:13Z 09-22) | 1790157019893 (09:50:19Z 09-23) |

Largest `cycle_count` contributor: **`refused_allowance`, 126 of 142
(88.7%)**; `no_candidate` 13 (9.2%); `convened` 3 (2.1%). `cycle_count` is a
duration proxy, not `n` (§3): the allowance held from 13:00Z to the end of
the day, ~21 of the day's 24 hours. Whether the 15:49Z restart cost a cycle is
unreadable (§0).

- `A` = the `refused_allowance` rows: **1**;
  `A.first_ms` = **1790082013383** (2026-09-22T13:00:13.383Z).
- `B` = the `refused_budget` rows: **0**. No `detail` to copy.

### 2.2 `scout-briefings`, day `20260922`

As printed in the T2 set:

- **A.** `20260922`: `auto_count` 3, `tap_count` 0.
- **B.** `20260922` `auto`: `complete` 1, `partial` 2.
- **C.** `refusal_reason` verbatim: 0 rows (over the whole 3-day window).

Section C is **not** a refusal count (§4, "Pre-flight refusals are
structurally absent"). The three `auto` briefings are the three `convened`
rows' tickers (ids 12, 13, 14 in the T1 read's `briefings` list).

### 2.3 `ladder-fixtures` (T3) — the demand side

As printed: `budget_day` 2026-09-17 → 55, 09-18 → 19, 09-19 → 37,
09-20 → 8, 09-21 → 9, **09-22 → 18**, 09-23 → 0 (cutoff 22:00Z, not yet
reached at read time). The QueryDef labels itself an approximation. Needed
only to separate outcome A's "supply or freshness" reading from the rest; A
is not selected (§5), so it is context.

### 2.4 `20260921` — OUT, printed separately, never pooled

Partial day: the flag went true ~14:15Z, so **4.25 h of 24 (17.7%)**
predate the feature — the registration's §3 says "3.75 h … (15.6%)", which is
an arithmetic error (10:00Z → 14:15Z is 4.25 h), copied into the skeleton and
corrected here; the registration is not edited. Its rows, labelled partial:
`refused_allowance`, `cycle_count` 92, `first_ms` 1790017124044 (18:58:44Z
09-21) → `last_ms` 1790070949902 (09:55:49Z 09-22), same detail as above;
`scout-briefings` `auto_count` 3, `tap_count` 0 (`complete` 2, `partial` 1).
**No `no_candidate` or `convened` rows for `20260921` appear in
`scout-watch-log`** although three auto briefings exist: the log's first row
(18:58:44Z) matches release v321 at 18:58Z 09-21, so the watch log covers
`20260921` from 18:58Z only (~15 h), and the three convenings predate it.

### 2.5 `20260923` — OUT, in progress at read time

Quoted only as read-time context, labelled incomplete, never counted: in the
set used, `no_candidate` `cycle_count` 2 (10:00:19Z → 10:10:20Z) and one
`convened` (10:20:21Z, KXMLBGAME-26SEP231310WSHDET-DET), `auto_count` 1,
`partial` 1; later sets differ only in `no_candidate` (3, 4, 4).

---

## 3. The deduction's coverage

§5's monotonicity argument covers only rows with `first_ms <= T1_ms`.

- Rows with `first_ms <= T1_ms`: **all five** rows of `20260922`
- Rows with `first_ms > T1_ms` (uncovered, reported as such): **none**
- `K < TB`? 630,719 vs 500,000 — **NO** (`K` exceeds `TB` by 130,719;
  `calls_unmetered_today` = 1)
- `S <= SB - 36`? 30 vs 24 — **NO**
- `A.first_ms <= T1_ms`? **YES** (13:00:13Z 09-22 vs 09:50:44Z 09-23)

What `K >= TB` does and does not say, under §4: the token and search brakes
had both been crossed **by T1**. The instant either was crossed is recorded
nowhere these reads reach. That every T1 read and both 19:40Z rehearsals
carry the same `spend` object bounds the crossing at or before 19:40:16Z 09-22 (Arm B rehearsal, context-only)
and says nothing about whether it came before or after 13:00:13Z.

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

### A — NEITHER CEILING WAS REACHED — not selected — because `A` is not empty (one `refused_allowance` row)

Condition: `A` is empty and `B` is empty.
Reading if selected: the day was limited by supply or freshness, not by a
ceiling. Report the `no_candidate` `cycle_count` and the `ladder-fixtures`
reading beside it: n.a.
§8 consequence, verbatim: *"nothing; #127 is closed as moot with the supply
reading attached"* — killed: *"the premise that a ceiling is what limits the
night"*. #127 is decision-relevant under A.

### B — ALLOWANCE BOUND, AND IT BOUND ALONE (H1 supported; masking FALSIFIED) — not selected — because `K < TB` failed (630,719 ≥ 500,000; `calls_unmetered_today` = 1) and `S <= SB - 36` failed (30 > 24)

Condition: `A` non-empty, `B` empty, `A.first_ms <= T1_ms`, `K < TB`,
`S <= SB - 36`.
Reading if selected: deductive, not statistical — at every recorded allowance
refusal, neither the token nor the search brake would have fired. Report
headroom `TB - K` = n.a. tokens and `SB - 36 - S` = n.a.
searches, and `floor((TB - K) / 170350)` = n.a. further convenings the
token ceiling would have permitted — **an estimate resting on day one's single
cost observation, not a measurement.**
§8 consequence, verbatim: *"#127 gets a concrete one-knob proposal: raise
`SCOUT_AUTO_MAX_CONVENINGS_PER_DAY` to a named number with the measured token
headroom beside it"* — killed: *"the belief that the allowance is
decorative"*. The knob sits inside the `AGENT_MAX_*` ceilings and is never
additive to them (`fly.live.toml:511` rule untouched).

### C — A BUDGET CEILING BOUND, AND IT IS NAMED — not selected — because `B` is empty (no `refused_budget` row)

Condition: `B` non-empty.
Reading if selected: each `detail` verbatim, and which ceiling each names —
tokens n.a., calls n.a., web searches n.a. — as three
separate counts, never one "budget refusal" total. The allowance masked
nothing on that day.
§8 consequence, verbatim: *"a ticket for Joe on whether the three
`AGENT_MAX_*` move together, with the verbatim `detail` as evidence"* —
killed: *"raising the allowance as a cheap lever — it buys nothing"*.
(Opening that ticket follows CLAUDE.md workflow step 7 — a sub-issue of map
#3 with its number in the handoff line — and it is a ninth ticket, not a ninth
entry in the frozen digest.)

### D — NOT SEPARABLE (masking possible, NOT established) — **SELECTED** — `A` non-empty, `B` empty, and both `K >= TB` (630,719 ≥ 500,000; `calls_unmetered_today` = 1) and `S > SB - 36` (30 > 24)

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

### E — VOID — not selected — because all three §0 criteria are NO

Condition: any §0 criterion YES.
Reading if selected: no outcome for `20260922`; the reason is recorded in §6
and §7's one slip applies.
§8 consequence, verbatim: *"nothing; one retry under §7"*.

**Asymmetry, registered:** B and C falsify masking (differently); D neither
confirms nor falsifies; **no outcome confirms masking** and this file may not
report one as if it did.

**Outcome for `20260922`: D.**
**Is #127 decision-relevant under it?** **No.** Under D this reading cannot
answer #127, and #127 must not proceed on it either way (§8 of the
registration). The honest headline, as §9 registered it: *"one complete
budget day cannot separate these ceilings, and no number of days can while
they coincide — here is the instrument that would."* The instrument is §6 of
the registration; its ticket is #137.

---

## 6. If the day slipped (§7) — filled only if §0 was VOID or a window was missed

§7: one registered fallback, `20260923` (T1 on 09-24 09:00–09:55Z, T2 on
09-24 10:30–14:00Z), under the same document; at most one slip; a second miss
closes the reading as not taken, which is itself the reportable result.

- Reason for the slip: no slip
- Crons and tasks re-dated (not re-derived): n.a. — deleted instead (§8)
- Second attempt outcome: n.a.

---

## 7. What this reading spent

Nothing on the target day: `GET /api/scout` is two SELECTs and
`today_summary` (`backend/api/routers/scout.py:325`, `:358`;
`backend/agents/budget.py:222`), the three QueryDefs are `cost=CHEAP`, no
tap was made, no live DB instrument beyond §2's three was run. Actions minutes:
the five scheduled runs took 14 + 16 + 54 + 14 + 14 = 112 s (start →
completion per `gh run list`), plus the two 09-22 rehearsals, 22 + 27 s. The
repo is public, so Actions is not billed.

---

## 8. Closing checklist for the session that fills this file (#136 Done-when 4)

- [x] §0 answered before §2 or §5 was read.
- [x] §1.1 lists every T1-window fire from both arms, including fires that did not happen.
- [x] `T1` is the **latest** qualifying read, not the first and not the cleaner-looking one.
- [x] §4 block still byte-identical to the registration (`diff <(sed -n '177,225p' <registration>) <(sed -n '185,233p' <this file>)` was empty at skeleton time, and again at fill time against the block's markers).
- [x] Exactly one §5 branch `SELECTED`; the other four say which condition failed.
- [x] `calls_unmetered_today` printed beside every token figure.
- [x] No sentence about briefing usefulness; no sentence about the phone's rendering.
- [x] No rate; no pooling with `20260921` or `20260923`.
- [x] `measurement-skeptic` has read this file before the outcome letter is copied to #118 / #127.
- [x] **Same commit:** delete `.github/workflows/measure-118.yml` and both laptop tasks (`schtasks //Delete //TN Kalshi118T1 //F`, same for `Kalshi118T2`) — the cron fires again next 23 September if left. Amendment 1's Done-when 4.
- [x] Status line at the top of this file changed from SKELETON to the outcome; the "written before any row" sentence kept as history, dated.
- [ ] **Only then** deploy (done after this commit; recorded in `tasks/NEXT.md`, not here) `32b5dce` or later, after 14:00Z on 09-23; read `/api/hedge` once afterwards for the settled/live split, write no count (ADR 0162).
- [x] Handoff: the outcome letter, the #127 consequence (or its non-relevance under D), and any new ticket by number, in the workflow-step-7 form.
