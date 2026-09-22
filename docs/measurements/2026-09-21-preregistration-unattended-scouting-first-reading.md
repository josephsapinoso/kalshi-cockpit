# Pre-registration — the first dated reading of unattended scouting (#118)

**Written 2026-09-21, before any of the data below was read.** No live query
was run in the session that wrote this, and no live row was seen. Everything
quoted here comes from source and config committed in this repo.

Registers the reading #118 owes 24–72 h after `SCOUT_AUTO_CONVENE_ENABLED`
went true on live at **2026-09-21 ~14:15Z**, and amends #118's Done-when item
3, which asks a question the ladder order makes unanswerable as written.

Serves the decision on **#127** — move a ceiling, or leave it.

---

## 0. The power check, which comes first

**The three candidate ceilings all land within one convening of each other.
The instrument's resolution is one convening. So the ordering question is not
resolvable by counting convenings, and no amount of waiting fixes that.**

The watcher's ladder, in the order it is actually evaluated
(`backend/scout_watch.py:151` keyless → `:178` allowance → `:200`
`AgentBudget.refusal_reason`, whose own ladder is
`backend/agents/budget.py:280` calls → `:287` tokens → `:297` searches →
`:309` per-pass):

| # | ceiling | live value | the watcher reserves | convenings it permits |
|---|---|---|---|---|
| 1 | `SCOUT_AUTO_MAX_CONVENINGS_PER_DAY` | 3 | — | **3** |
| 2 | `AGENT_MAX_CALLS_PER_DAY` | 24 | 6 calls | 6–7 (3 calls/convening) |
| 3 | `AGENT_MAX_TOKENS_PER_DAY` | 500,000 | none (gated on recorded total) | **≈2.9** at day one's 170,350/convening |
| 4 | `AGENT_MAX_SEARCHES_PER_DAY` | 60 | 36 searches | **3** at worst case |

Arithmetic for rows 2–4: `reserved_calls = 2 * (1 + reserve_taps)` = 6 and
`reserved_searches = STAFF_PAIR_SEARCHES_WORST_CASE * (1 + reserve_taps)` =
12 × 3 = 36 (`scout_watch.py:198`, `reserve_taps = 2`,
`STAFF_PAIR_SEARCHES_WORST_CASE = 2 × 6 = 12`,
`backend/agents/scout_desk.py:83`). Searches refuse when
`searches_today + 36 > 60`, i.e. above 24 — two worst-case convenings. Tokens
refuse when `tokens_today >= 500_000`; day one's three convenings cost
~511,051, so 2 fit and the 3rd is the last one allowed.

**#118 item 3's premise that searches allow 5/day is wrong.** 60 ÷ 12 = 5
ignores the watcher's 36-search reserve. Inside the watcher, searches permit
**3**, the same number as the allowance. The 5/day figure describes a tap
(`routers/scout.py:271` reserves only 12), not the unattended path.

So: the separations to be resolved are **0 convenings** (allowance 3 vs
searches 3) and **0.07 convenings** (tokens 2.93 vs 3). The measurement's
quantum is 1 convening. A design whose detectable effect is 1 unit cannot
resolve a 0-unit gap, at any `n`.

**Verdict on the ordering question as #118 phrased it: UNDERPOWERED, and not
by sample size.** No number of budget days separates three ceilings that
coincide. This is knowable now, for free, which is the point of computing it
now.

**What is still answerable, and why the trip is worth taking:** one
complete day can *deductively falsify* masking, in one direction only. See
§5. That is the reading this document registers.

---

## 1. The claim, as something that can come back false

**H1 (directional, one-sided):** On the target budget day, at the instant of
every recorded `refused_allowance` decision, the token ceiling had **not**
been reached — i.e. `SCOUT_AUTO_MAX_CONVENINGS_PER_DAY` refused the watcher
while `AGENT_MAX_TOKENS_PER_DAY` still had headroom, so the allowance was
doing load-bearing work rather than standing in front of an already-closed
door.

**H0 / the masking hypothesis:** the allowance refuses first *only because it
is checked first*, and the token ceiling was already crossed — the allowance
masks it and moving the allowance buys nothing.

H1 is falsifiable and is registered one-sided because the session that
proposed this reading already believes masking (§4 of the task brief). A
one-sided test that could be re-reported two-sided after the fact is the
failure this document exists to prevent, so the direction is fixed here: the
reading may only *falsify* masking, never *confirm* it. See §5 outcome D.

Secondary, non-inferential, registered so it is not chosen later: the per-day
census counts in §3, reported as counts, never as rates.

---

## 2. The amended Done-when item 3 (the replacement cut)

> **3. On the first COMPLETE unattended budget day (2026-09-22 10:00:00Z →
> 2026-09-23 10:00:00Z), classify the day into exactly one of the five
> outcomes in §5 of
> `docs/measurements/2026-09-21-preregistration-unattended-scouting-first-reading.md`,
> using exactly three readings taken on one live trip:**
>
> - **T1, taken between 2026-09-23 09:00:00Z and 09:55:00Z** (inside the
>   target day, before it rolls):
>   `flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/fetch_live_route.py /api/scout"`
>   → record `spend.day_start_ms`, `tokens_today`, `tokens_daily_budget`,
>   `searches_today`, `searches_daily_budget`, `calls_today`,
>   `calls_daily_budget`, `calls_unmetered_today`, and the wall-clock instant
>   of the read as `T1_ms`.
>   **Pre-condition, checked before anything else:** `spend.day_start_ms` must
>   equal 2026-09-22T10:00:00Z. If it does not, the day rolled during the
>   trip; the snapshot is VOID and §7's fallback applies.
> - **T2, taken between 2026-09-23 10:30:00Z and 14:00:00Z** (after the day
>   rolled, so the table reads a closed day):
>   `python /app/scripts/inspect_live_db.py scout-watch-log --days 3 --day-start-hour 10`
>   and
>   `python /app/scripts/inspect_live_db.py scout-briefings --days 3 --day-start-hour 10`.
> - **T3, same trip as T2:**
>   `python /app/scripts/inspect_live_db.py ladder-fixtures` — the demand
>   side, needed only to separate outcome E from the rest.
>
> **Done when** the result document named in §8 exists, states the outcome
> letter from §5, and quotes §4's caveat block verbatim.

**Why T1 exists and the original plan had no T1.** The plan as briefed was a
single trip at 09-23 10:30–14:00Z. `/api/scout` reports spend for the budget
day containing *now* (`AgentBudget.today_summary`), so a snapshot taken after
10:00Z on 09-23 reports the **09-23** day — thirty minutes old, near zero, and
about a different day than the one being read. Without T1 the token level for
the target day is unreadable by any committed instrument and the reading
collapses to outcome D by construction. T1 is the whole measurement.

---

## 3. Population, unit of observation, exclusions

**Unit of observation: one agent budget day.** Not a calendar day, not a
cycle, not a convening. Both QueryDefs group on `budget_day_ms` with
`--day-start-hour 10`, which is the same clock `AgentBudget.day_start_ms`
counts the allowance against (`backend/config.py:270`,
`ODDS_BUDGET_DAY_START_UTC_HOUR` default 10, absent from `fly.live.toml`).
Two days are independent only in the weak sense that the allowance resets;
they are **not** independent in fixture supply (the sports calendar is weekly
and an NFL Sunday is not a Tuesday), so no day-to-day pooling is registered
here and none may be added later without a successor registration.

**IN — exactly one day:** `20260922`, i.e. 2026-09-22T10:00:00Z →
2026-09-23T10:00:00Z. `n = 1`. This is a **census of that day**, not a sample
of days, and §4 forbids stating it as a rate.

**OUT, reported separately, never pooled — `20260921`.** The flag went true
at ~14:15Z, so 3.75 h of a 24 h day (15.6%) predate the feature. The
allowance is a *per-day count*, so a truncated day cannot exhaust it on the
same schedule as a full one; pooling it would bias the "a ceiling bound" count
downward. It is printed in its own section of the result doc, labelled
partial, with the missing hours stated.

**OUT — `20260923`**, in progress at read time. May be quoted only as
read-time context, explicitly labelled incomplete, never counted.

**VOID rule, fixed now, and it does not reference the outcome.** The target
day is void and §7's fallback applies if any of: (a) `spend.day_start_ms` at
T1 is not 2026-09-22T10:00:00Z; (b) any `keyless` row appears on the target
day in `scout-watch-log` (the key went missing mid-day, so the watcher was not
the thing being measured); (c) `git log` / `flyctl releases` shows a deploy
that changed any `AGENT_MAX_*` or `SCOUT_AUTO_*` value inside the target day.
None of these three reads the convening count, the refusal outcome, or the
token level. **A day is never voided for having produced an inconvenient
outcome**, and there is no fourth criterion.

**Clustering / `n` inflation.** `scout_watch_log` holds one row per
(budget_day, outcome, detail) with a `cycle_count`, not one row per 600 s
cycle. **`cycle_count` is not `n`.** A `refused_allowance` row with
`cycle_count = 47` is one decision repeated by a timer, not 47 observations —
the same error the gate made counting 400 rows on one ticker. The registered
`n` is 1 day. `cycle_count` is reported as a *duration* proxy (how long the
ceiling held), which is what a counter that fires on a cadence while a
condition holds actually measures.

---

## 4. What the reading may NOT claim

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

---

## 5. The decision rule, fixed in advance

Read `n` first: confirm the target day appears in `scout-watch-log` and record
`auto_count` / `tap_count` from `scout-briefings` section A **before** looking
at any outcome. Print the per-outcome breakdown beside any total, and name the
largest `cycle_count` contributor.

Definitions, all from the readings in §2:
- `A` = the `refused_allowance` rows on `20260922`; `A.first_ms` = the
  earliest `first_ms` among them.
- `B` = the `refused_budget` rows on `20260922`, with `detail` verbatim.
- `C` = `auto_count`, `D` = `tap_count`, both from `scout-briefings` §A.
- `K` = `tokens_today` at T1; `TB` = `tokens_daily_budget` (expected 500,000).
- `S` = `searches_today` at T1; `SB` = `searches_daily_budget` (expected 60).

**The monotonicity argument, stated once.** `tokens_today` and
`searches_today` are sums over `agent_calls` rows inside the day and are
non-decreasing in time. So `K < TB` implies the token check
(`tokens_today >= TB`) was false at **every** instant `t <= T1_ms` of that
day. Likewise `S <= SB - 36` implies the watcher's search check
(`searches_today + 36 > SB`) was false at every `t <= T1_ms`. **The deduction
covers only rows with `first_ms <= T1_ms`**; a row later than T1 is outside it
and is reported as uncovered.

Exactly one outcome. Decide in this order.

**A — NEITHER CEILING WAS REACHED.** `A` is empty and `B` is empty.
→ The day was limited by supply or freshness, not by a ceiling. Report the
`no_candidate` `cycle_count` and the `ladder-fixtures` reading beside it.
**#127's consequence: moving any ceiling buys nothing on a day like this**;
#127 should be closed as moot unless a later day differs.

**B — ALLOWANCE BOUND, AND IT BOUND ALONE (H1 supported; masking FALSIFIED).**
`A` is non-empty, `B` is empty, `A.first_ms <= T1_ms`, `K < TB`, and
`S <= SB - 36`.
→ Deductive, not statistical: at every recorded allowance refusal on that day,
neither the token nor the search brake would have fired. The allowance was
load-bearing. Report the headroom `TB - K` tokens and `SB - 36 - S` searches,
and `floor((TB - K) / 170350)` as the number of further convenings the token
ceiling would have permitted — labelled an estimate resting on day one's
single cost observation, not a measurement.
**#127's consequence: `SCOUT_AUTO_MAX_CONVENINGS_PER_DAY` is the lever, and it
is a one-knob change** — it sits inside the `AGENT_MAX_*` ceilings and is never
additive to them, so raising it does not touch the standing rule at
`fly.live.toml:511` that the three `AGENT_MAX_*` move together or not at all.

**C — A BUDGET CEILING BOUND, AND IT IS NAMED.** `B` is non-empty.
→ Copy each `detail` verbatim and report *which* ceiling each names — tokens,
calls, or web searches — as three separate counts, never as one
"budget refusal" total. This outcome means the allowance did **not** mask
anything on that day: the ladder reached the budget check and recorded what it
found, spend figure included.
**#127's consequence: raising the allowance buys nothing.** Buying more
convenings requires moving an `AGENT_MAX_*`, which under
`fly.live.toml:511` means moving all three together — a larger money decision
that is Joe's alone and needs its own ticket, not this reading's conclusion.

**D — NOT SEPARABLE (masking possible, NOT established).** `A` is non-empty,
`B` is empty, and either `K >= TB` or `S > SB - 36` (or
`A.first_ms > T1_ms`).
→ Both the allowance and a budget ceiling were crossed by T1, and **the
instant the budget ceiling was crossed is recorded nowhere** — `agent_calls`
has no committed reader, and `refused_allowance` details carry no spend. The
ordering is unreadable. **Report UNRESOLVED.** Do not write "the allowance
masks the token ceiling"; write that the reading is consistent with masking
and cannot distinguish it from an allowance that bound first on merit. §0 says
this outcome cannot be escaped by repeating the reading, so the result document
must instead name the instrument that would resolve it (§6).

**E — VOID.** Any §3 void criterion fired. No outcome is reported; §7's
fallback day is read instead and the reason is recorded.

### What would falsify "the allowance masks the token ceiling"

**Outcome B falsifies it outright**, deductively, for that day. **Outcome C
falsifies it in a different way** — the ladder reached and recorded a budget
ceiling, so nothing was masked. Outcome D neither confirms nor falsifies. **No
outcome confirms masking**, and the result document may not report one as if
it did. That asymmetry is registered deliberately: the instruments can rule
masking out and cannot rule it in.

### Multiplicity and looks

No significance test is performed and no threshold is crossed, so there is no
`p` to correct — the five outcomes are a deterministic partition of recorded
facts. The multiplicity risk here is **repeated looks at a growing table**,
and it is handled by fixing the count now: **this is ONE look, at ONE day.**
Any later look at `scout_watch_log` for this question — in particular any
attempt to state a *rate* ("the allowance bound first on X of Y days") — is a
new question, requires a successor registration, and requires an always-valid
boundary, because a threshold re-evaluated against an accumulating table
crosses under a true null eventually with probability 1 (measured at 13.7% in
this project, a floor).

---

## 6. If the answer is D, the instrument that would resolve it

Stated now so it is not invented afterwards to fit the result. Resolving the
ordering needs the token meter read **at the instant of the refusal**, which
means one of:

1. A committed `agent-spend` QueryDef over `agent_calls`
   (`backend/store/schema.sql:1387`; columns `called_ms`, `agent`, `model`,
   `input_tokens`, `output_tokens`, `web_searches`, all NULL-able and NULL
   meaning unmetered) grouping by budget day and cumulative sum, so the
   crossing time of each ceiling is readable. `cost=CHEAP` is plausible —
   `agent_calls` is a small table — but the `--days` bound and the whole-table
   scan must be argued in its docstring before it is written.
2. Or: record the full `refusal_reason` ladder's state on a
   `refused_allowance` row too, so the allowance refusal carries the spend it
   was standing in front of. That is a change to `scout_watch.py`, i.e. the
   unattended-spend path, and #118 is forbidden from touching it.

Neither is in scope for this reading. Whichever is chosen becomes a ticket.

---

## 7. Stopping rule

**Data collection ends at T2**, on 2026-09-23, within 10:30–14:00Z, for the
single day `20260922`. It does not end "when there is enough" and it does not
extend because the day looked unusual.

**One registered fallback, and only one.** If the T1 window (09:00–09:55Z) or
the T2 window is missed, or the day is VOID under §3, the reading slips to the
next complete budget day (`20260923`, T1 on 09-24 09:00–09:55Z, T2 on 09-24
10:30–14:00Z) under this same document, and the reason for the slip is
recorded in the result. **At most one slip.** A second miss closes the reading
as not taken, which is itself the reportable result. This bounds the reading
at two attempts so "read again tomorrow" cannot become a search for a day that
produces outcome B.

---

## 8. Falsification destination and consequence

**The result document is
`docs/measurements/2026-09-23-unattended-scouting-first-reading.md`, and it is
written whatever the outcome — including outcomes A, D and E, which produce no
finding.** Registering the destination now is the point: a negative branch with
no destination produces a negative result that never gets written.

Consequences, both directions, fixed before the data:

| outcome | what is built | what is killed |
|---|---|---|
| **B** | #127 gets a concrete one-knob proposal: raise `SCOUT_AUTO_MAX_CONVENINGS_PER_DAY` to a named number with the measured token headroom beside it | the belief that the allowance is decorative |
| **C** | a ticket for Joe on whether the three `AGENT_MAX_*` move together, with the verbatim `detail` as evidence | raising the allowance as a cheap lever — it buys nothing |
| **A** | nothing; #127 is closed as moot with the supply reading attached | the premise that a ceiling is what limits the night |
| **D** | a ticket for the §6 instrument | this measurement's ability to answer #127 — stated plainly, not buried |
| **E** | nothing; one retry under §7 | — |

**#127 is decision-relevant under B, C and A, and not under D.** Say so in the
result rather than proceeding either way.

---

## 9. Can one complete budget day answer #127 at all?

**Partly, and not the part #118 asked for. Stated plainly:**

**No** — it cannot establish which ceiling binds *in general*. §0 shows why,
and the reason is arithmetic, not sample size: at day one's cost the allowance
(3), the worst-case search ceiling (3) and the token ceiling (≈2.9) coincide
inside one convening, and one convening is the smallest thing the instrument
can count. Day one sat 2.2% above the token break-even
(170,350 vs 500,000 ÷ 3 = 166,667); a 2.2% swing in mean convening cost flips
which ceiling bites, and `n = 1` gives no estimate at all of between-day
variation in that cost. Estimating a *rate* would need a proportion over
budget days, and with a weekly sports calendar the effective cluster is the
week, so an interval narrow enough to act on is roughly three weeks of
unchanged config — and changing any ceiling restarts that clock, which makes
the rate question self-defeating for a decision that is about changing a
ceiling.

**Yes** — it can do three useful things, and they are what the trip is for:

1. **Deductively falsify masking for one day** (outcome B), via §5's
   monotonicity argument. That is a real, checkable result from `n = 1`,
   because it is a census with a deterministic branch, not an estimate.
2. **Tell whether any ceiling bound at all** (outcome A vs the rest). If the
   night is supply-limited, #127 is moot and no ceiling needs moving — and
   that closes the ticket more cheaply than any ordering result would.
3. **Prove the instruments work on real rows** — that `scout-watch-log` and
   `scout-briefings` return coherent, joinable readings of a live unattended
   day, which nothing has yet established.

**The honest headline for the result document, if it comes back D:** "one
complete budget day cannot separate these ceilings, and no number of days
can while they coincide — here is the instrument that would." That sentence
is registered here so it cannot be softened later.

---

## Amendment 1 — 2026-09-22 ~19:40Z — the reading is taken by automation, and which read is T1 is fixed now

**Additive, and written before any row of the target day has been read.** T1's
window opens 2026-09-23 09:00:00Z. No sentence above is edited or deleted.
**§2's commands, §3's population and exclusions, §5's decision rule and §7's
stopping rule are unchanged by this amendment** — §2 fixes the command, not the
operator. No outcome letter is referenced here, and **no void criterion is
added**: §3 still has exactly three and "there is no fourth criterion" stays
true.

### A1.1 Who takes the reading

Two independent arms run §2's commands **verbatim** from one committed script,
`scripts/measure_118_trip.sh`: the same
`flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/fetch_live_route.py /api/scout"`
string for T1, the same two `inspect_live_db.py` lines plus `ladder-fixtures`
for T2/T3.

- **Arm A — `.github/workflows/measure-118.yml`**, dated to 2026-09-23, cron at
  09:02, 09:17, 09:32 and 09:47Z (T1) and 10:35 and 10:50Z (T2/T3). Four T1
  fires because GitHub's scheduler is **late, not absent**, measured on this
  repo's own heartbeat: median gap between runs 22.6 min, **maximum 245 min**,
  n = 199 (`.github/workflows/heartbeat.yml:45`). Four fires do not make the
  window certain; they make a miss less likely, and a miss is still §7's
  business, not a reason to widen the window. Each run uploads its output as an
  artifact, and the run's timestamp is GitHub's clock.
- **Arm B — a Windows scheduled task on Joe's laptop**, same minutes
  (02:05, 02:20, 02:35, 02:50 PDT; 03:35, 03:50 PDT), same script, output to
  `%LOCALAPPDATA%\kalshi-cockpit\118\`. Its wall-clock comes from the `Date`
  header of `curl -sI https://api.github.com`, **never the machine clock**: the
  machine printed `07:40:58 UTC` when it was 14:40Z (`tasks/lessons.md:103`).

Both arms may fire, both arms' output is data, and **neither arm is preferred
over the other** in A1.2 — preferring one after seeing both would be the
degree of freedom this document exists to remove.

### A1.2 Which read is T1 — fixed now, because several reads will exist

> **T1 is the latest successful read, from either arm, whose trusted wall-clock
> is strictly before 2026-09-23T09:55:00Z and whose `spend.day_start_ms` equals
> 2026-09-22T10:00:00Z. That read's trusted wall-clock is `T1_ms`, and its
> `tokens_today` and `searches_today` are `K` and `S`. Every read taken, from
> both arms, is printed in the result document with its arm, its trusted
> wall-clock and its `day_start_ms`; a read at or after 09:55:00Z, or carrying
> a different `day_start_ms`, is not T1 and is printed as context only.**

**Why "latest" is the conservative choice, not the convenient one.**
`tokens_today` and `searches_today` are non-decreasing within a budget day
(§5's monotonicity argument), so the latest qualifying read **maximises** `K`
and `S`. §5's masking-falsification branch requires `K < TB` *and*
`S <= SB - 36`, so taking the latest read makes that falsification **harder to
obtain, never easier** — the
rule is fixed against the direction the session proposing the reading would
prefer. It also maximises coverage: §5's deduction covers rows with
`first_ms <= T1_ms`, and the latest read covers the most of them.

**How §3(a) applies when several reads exist — same criterion, no new one.**
§3(a) voids the day when "`spend.day_start_ms` at T1 is not
2026-09-22T10:00:00Z". Under the rule above, a read carrying a different
`day_start_ms` is not a T1 at all, so (a) fires exactly when **no** read from
either arm before 09:55:00Z carries `day_start_ms` = 2026-09-22T10:00:00Z —
the selection returns nothing, because the day rolled early or every attempt
failed. Nothing is added, nothing is relaxed.

### A1.3 Which set is T2/T3

The set used is the **first successful set after 2026-09-23T10:30:00Z in which
all three commands come from one arm's one run**, which preserves §2's "one
trip": the three readings are of one instant, not stitched from two. Later sets
are equivalent and are printed too — both QueryDefs group on `budget_day_ms`
with `--day-start-hour 10` (`scripts/inspect_live_db.py:790-850`, all three
`cost=CHEAP`), and the target day closed at 10:00Z, so a later read of it can
differ only by rows dated `20260923`, which §3 puts OUT. If no single-run set
qualifies, §7's one slip applies; stitching two runs is not registered.

### A1.4 Today's rehearsal runs are not readings

Both arms are exercised on **2026-09-22**, the day this amendment is written,
to prove they run at all. Those reads fall outside T1's window, so they cannot
be T1 under A1.2: they are **context only**, and are still printed in the
result document. They cannot perturb the day either.
`GET /api/scout` is read-only — one SELECT over `scout_briefings`
(`backend/api/routers/scout.py:325`) plus `AgentBudget.today_summary`
(`:358`), whose `state()` is a single SELECT over `agent_calls`
(`backend/agents/budget.py:222`) — and the three QueryDefs are `cost=CHEAP`,
so no rehearsal walks the file or flushes the live cache. Nor is a rehearsal a
"look" in §5's sense: §5 counts evaluations of the decision rule, and a read
that cannot be T1 cannot feed it.

### A1.5 What this amendment does not touch

§7 is unchanged: if neither arm produces a qualifying T1 read, the reading
slips once to `20260923`, with the reason recorded. The human trip on
2026-09-23 — the #129/#107 captures, and the deploy of `fdbe92f` taken after
T2 — is **not part of the reading** and contributes no row to it; the deploy
lands outside the target day, so §3(c) is not engaged and is not weakened here.

**Registration status after Amendment 1: READY, unchanged.** The decision rule
quoted below stands word for word; this amendment fixes only who runs §2's
commands and which of several reads is `T1`.

---

## Registration status

**UNDERPOWERED for #118 item 3 as originally written** (which ceiling binds
first, in general) — detectable effect 1 convening/day against gaps of 0 and
0.07 convenings; no `n` resolves it. **Re-scoped, not killed**, to the
one-sided deductive falsification in §1/§5, which is answerable at `n` = 1 and
is registered READY.

**Decision rule, verbatim, for checking against the eventual write-up:**

> Outcome B (ALLOWANCE BOUND ALONE) requires all of: `refused_allowance` rows
> present on `20260922`; no `refused_budget` rows on `20260922`;
> `A.first_ms <= T1_ms`; `tokens_today < tokens_daily_budget` at T1; and
> `searches_today <= searches_daily_budget - 36` at T1. Any of `K >= TB`,
> `S > SB - 36`, or `A.first_ms > T1_ms`, with `B` empty, is outcome D and is
> reported UNRESOLVED. **No outcome confirms masking.** `n` = 1 budget day: a
> census, not a rate.
