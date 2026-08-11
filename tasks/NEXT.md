# Next — your checklist

## 2026-08-11 — ADR 0025: the `stale_odds` claim was OVERSTATED by ~10x, and its mechanism ran backwards

A backlog-triage agent proposed that ADR 0021's headline *"0 actionable rows,
ever"* rests on a guard that **discarded the only rows that could have
contradicted it**, citing `844 of 935`. `measurement-skeptic` returned
**OVERSTATED**. `docs/adr/0025-the-stale-odds-semantics-is-unpinned-by-any-test.md`
records what survived. **Do not re-open this from the original framing.**

**What is true and is new:** `stale_odds` is the only suppression code holding
back any would-be-`actionable` row, and it holds back **23 rows / 9 game
clusters / 8 odds snapshots**, all `strategy_config_version` 1. Removing it
alone would move `actionable` from **0 rows to 23** and the gate's scored counter
from **0 of 300 to 4 of 300**.

**What is false, and must not be repeated:**

- **`844 of 935` is not the number of rows in play.** It is reason-code
  coverage, **at the wrong pin**, and **836 of 859 (97.3%)** cannot be surfaced
  by removing the guard. The number is **23**.
- **The mechanism inverts.** `odds_age_ms` is a **scrape** clock, so it is a
  **lower bound** on true line age — every rejection is correct under either
  reading, and the defect contaminates the **clean** set instead. That is ADR
  0021 §7.5, which the claim cited while concluding its opposite.
- **"Never written down" is false.** §7.5, two registrations and ADR 0020's
  queue all write it down. Only the **magnitude** was undocumented.
- **The 23 lost to the close.** All 11 that carry a score are negative (mean
  **−18.64 tenths**) against **−5.12** per cluster over the 20 scored clean
  games. And **8 of the 23 are not pre-game** — 4 of the 9 games were in
  progress when the row was written.

**What to act on:** the repeat poll's value goes **up**. It is the registered
instrument for the only question that could change the direction, and ADR 0025
§5 shows no unit test can substitute — `test_a_stale_book_suppresses` anchored
at **4×** the threshold with a docstring asserting the semantics the code
corrects. Boundary tests added; 4 mutations seen red.

**Also settled:** `ALL_CHECK_NAMES` has **12** entries, not 14. Verified at
`backend/core/suppression.py:119`. At least five committed documents say
fourteen — correct them as those files are next touched.

## 2026-08-10 — `inspect_live_db.py` RUNS NOW, and answers ONE of the four questions it was queued for

The script is finished: refusal block gone, **68 tests**, **17 mutations all seen
red**, exits 0 against a real database. `19bb3b6`.

**But the reason it was prioritised is largely gone, and that is the finding.**
The handoff said finishing it *"unblocks three questions at once"*. Its whitelist
reads only `api_credits`, `odds_sweep_log`, `kalshi_markets`, `kalshi_events`,
`kalshi_series`, `closing_lines`, and `recommendations` (tickers only, pinned).

| Question | Status | Blocker |
|---|---|---|
| **Q-W** — cell `W`'s activation, half of what the $5.00 bought | **NOT ANSWERABLE** | needs `kalshi_quotes`, which appears **0** times in the file |
| scored-game rate vs `gate.py`'s 300 floor | **NOT ANSWERABLE** | `gate.py:354` counts `FROM recommendations` as a population; the whitelist selects only tickers |
| the 423 non-anchored rows | **NOT ANSWERABLE** | `fair_prices` appears **0** times |
| raw `closing_lines` | **PARTIAL** | returns the columns, but restricted to `recommendations.id <= --pin` |

**Verified independently rather than taken from the lane's report.** A negative
claim of this weight gets its own grep — this file's own rule, and it had just
been written into `lessons.md` when this arrived.

**No query was added, and that is correct.** A new query is a real change to what
runs against the money box, needs its own review, and reaches the machine only at
the **next deploy** (`Dockerfile:66`). **Adding a `kalshi_quotes` query for Q-W is
the highest-value next step on this file** — it is the difference between round
three running five cells and four. It needs a deploy either way, and deploys are
Joe's.

**Consequence for round three:** cell `W` stays **UNRESOLVED**. That is **not**
§1.3's *"no series passed, `W` is not registered"*, so §Power's four-cell branch
is **not** licensed. `scripts/watch_fee_bands.py` reports exactly this
distinction and refuses to collapse it.

## 2026-08-10 — ADR 0021 §7: the dump is refused for the CLV test, and NOT ruled on for the other one

**This section was first written in a stronger form and an audit overturned two
of its three load-bearing moves within the hour.** Both versions were mine, in
one session, with no reader in between. What follows is the corrected scope; the
faults are recorded in `tasks/lessons.md` because they are the useful part.

### What is settled, by registration and not by arithmetic

**The registered CLV pass-through test cannot declare anything on this record**,
and no power calculation is needed to say so
(`2026-08-09-preregistration-clv-signal-test.md:420-427`, a clause Amendment 1
does **not** supersede):

> **UNRESOLVED.** Declared in every other case, **including every look taken when
> `G < 300`**. […] A look taken when `G < 300` may report point estimates and
> intervals. **It may not declare SIGNAL, BUG or NO SIGNAL.**

Amendment 1 §A3's replacement SIGNAL and BUG clauses each re-state `G >= 300`.
The record supplies **~20 game clusters** on §2's registered population (60 is
the *unfiltered* count). **A dump raising `G` to 60 buys an UNRESOLVED, which the
record already has.**

### What was NOT ruled on, and this is the correction that matters

**The dump was proposed for a different test, and that one is still unpriced.**
The handoff said the record *"is missing only who won"* — but the CLV design
needs `clv_tenths` and `edge_tenths`, both already scored, and **no outcome
column at all**. ADR 0021 §9 already separates them: outcome-scored calibration
is *"a different question with different inputs — `kalshi_markets.result`"*.

**So do not read this as "the leadership question is closed".** *"Is Kalshi the
sharp side"* maps onto a **paired forecast-accuracy** comparison — Kalshi's price
against the devigged consensus, both scored on `result`. Different estimator,
different null, **no committed arithmetic anywhere in this repo**. Two
provisional figures exist as **leads, not results**: a paired sign test at
`G = 60` would need a true rate above **0.893**, and a paired Brier difference
crosses over near **`G = 68`** before clustering. Both point the same way.
**Neither licenses a conclusion, and either needs its own pre-registration.**

> **The first version claimed the refusal at the scope of the whole question.**
> That is this repo's named failure shape — the `/markets` sample that licensed
> *"Kalshi has no combo product"* — measurement about one instrument, conclusion
> about the subject. Anyone proposing a dump for the **outcome-scored** test is
> not re-opening a closed question; they are opening one nobody has designed.

### The premise that was withdrawn

The first version argued *"MDE 1.57 exceeds the ceiling of plausibility
`beta = 1`, therefore the design cannot resolve anything"*. **Amendment 1 §A3
(:1093) replaces the `beta > 1 -> BUG` rule outright** and states a point
estimate above one is the **expected** reading under a deliberately conservative
engine. The sentence quoted as a ceiling was from a body the file's own header
(:10-15) says does not govern. **Never quote this registration's body without
checking Amendment 1.**

The MDE table survives as **corroboration only**: 4.40 at `G = 20`, 3.09 at 29,
1.93 at 48, 1.57 at 60, 0.42 at the floor of 300. Monotone decreasing in `G`
(checked at every integer to 5,000), which is what lets an argument at the
largest count cover every smaller one. It carries two assumptions the refusal no
longer needs — `sigma_eps/sigma_x = 2` is **assumed and measured nowhere**
(§A5.2), and the boundary assumes **independence across games**
(`gate.py:165-169`) which the record contradicts. Both errors reduce power.

### The falsifier that already ran, and needs no dump

On **423 of 1,564 rows (27.0%)** no sharp book had quoted, so those rows were
priced against the **full** book set — **0** positive edges among the **189**
unsuppressed. **Across all 423: 6 positive rows, every one suppressed, max
+15.06 tenths.** Not "nothing appeared".

> **Read the `n` first.** 423 rows are **13 distinct odds-observation stamps**.
> The source document names *"34 links"*, but ADR 0021 §2 settles it the other
> way — *"the sweep is the dependence unit"* — and 13 is tighter. The set is
> selected toward **thin** instants (median **12** books against 23 overall), is
> **91% MLB**, and **190 of 423** were already `stale_odds`. It **narrows** the
> tautology objection to 73% of the record. **Not** a partial run of option B.

### One number corrected the other way

The first version called the counts 48 and 29 *"unverified, reproducing from no
committed harness"*. **They reproduce exactly** from
`docs/measurements/2026-08-10-clean-shortfall-pull.json`: 1,564 rows over **60**
clusters, 1,101 with any `clv_tenths` over **48**, 532 horizon-0 over **29**, and
614 unsuppressed over **59** — which is §2's own `G = 59`. **The pull carries no
`event_ticker` column**, so the cluster key is the ticker minus its final
segment; `COALESCE(event_ticker, ticker)` silently gives market-level 120/96/55.
A negative claim about the repo's own contents was published without running the
search that refutes it.

**Pinned in code:** `tests/test_clv.py`,
`TestTheCLVDesignCannotDeclareAnythingOnThisRecord` and
`TestTheRegisteredPowerTableReproduces`. Seen red under five mutations, including
the cluster-key degradation above and the fixed-sample 1.96 that flips the
reading.

## 2026-08-10 — CORRECTED: ADR 0021 §7.2 asserted something its own source had already refuted

`2026-08-10-sharp-anchoring-on-the-record-result.md` ended *"Not edited here.
**Routed separately.**"* **The routing never happened**, so ADR 0021 §7.2 went on
saying `anchored_on_sharp` is *"not on this record either"*. It is — on
**`fair_prices`**, not `recommendations`, which is why a ledger pull missed it.
All six of that document's routed items are now applied in place, and the
pattern is in `lessons.md`.

## 2026-08-10 22:34:21Z — THE SWEEP SERVED. The latch is refuted, F4's prediction held.

Read at **2026-08-10T22:40:19Z**, inside the registered 22:22–22:52Z slot:

```
last_look       2026-08-10T22:34:21Z   outcome: served
last_sweep      2026-08-10T22:34:21Z   (was 2026-08-09T23:37:15Z)
spent_today     6                      (was 0)
fixtures_upcoming  29                  (was 13)
mlb slots       22:55Z, 08-11T01:25Z, 08-11T21:56Z, 08-12T00:54Z
```

**Every field moved the way the pre-registered `served` branch said it would.**
`spent_today` went 0 → 6, which is exactly one sweep at
`credits_per_sweep_per_sport = 6`.

**The latched `x-requests-remaining` hypothesis is REFUTED.** It was the last
candidate standing, and it predicted a refusal *before the request went out*.
The request went out and was served.

**F4's prediction is CONFIRMED, and this is the part that was falsifiable.**
Before the sweep, live held **0 of ESPN's 15 MLB fixtures for 08-11** and its
plan had no 08-11 MLB slot. After one served sweep the slot is there at
**2026-08-11T21:56:00Z** — against ESPN's independently derived **21:55Z**, one
minute apart, which is what two sources agreeing on a cluster's earliest kickoff
looks like. `fixtures_upcoming` more than doubled, 13 → 29. **"The fixture store
is stale by construction between sweeps and self-corrects" was registered as
refutable and was not refuted.**

> **What this still does not establish, and it is written down because the
> temptation runs the other way.** A served sweep tonight shows the sweeper
> works **on the current build**. It does **not** retro-establish that the
> 21.5-hour gap was benign: today's deploy sits between the gap and this test,
> so any explanation involving wedged process state — a hung `httpx` client, a
> stalled event loop — was silently repaired by the deploy and would report as
> health here. **F1 is what makes the gap benign** (an empty denominator, from
> the calendar), not this. Confirming the sweeper tonight and concluding the gap
> was fine is ADR 0014's misdiagnosis run in reverse.

**Consequence for the queue:** start.md's queue item 1 and the "everything else
this project builds is worth nothing if the recorder is dead" framing are
**closed**. The recorder is not dead and was never shown to be. Item 6
(`decide_sweeps` reads only the daily ceiling while `refusal_reason` checks
three) stays **REACHABLE ONLY** — it was promoted-on-condition if tonight
returned `refused`, and it did not.

## 2026-08-10 — RESOLVED: the 21.5-hour odds gap had an empty denominator

**The framing that led the last two handoffs — "odds fetching stopped
2026-08-09T23:37:15Z" read as a possible dead recorder — is refuted as a
*cause*. There was no in-scope fixture to sweep for.** The strongest form of
this needs no scheduler at all and is a calendar fact:

```
2026-08-10T00:20:00Z   HOU @ SD     (baseball_mlb)   <- last in-scope kickoff
        ...  22h 47m, zero in-scope fixtures  ...
2026-08-10T23:07:00Z   BOS @ TOR    (baseball_mlb)   <- next in-scope kickoff
```

Straight from ESPN across the 20260809 and 20260810 buckets, six in-scope
leagues, **zero Odds API credits**. The last served sweep, 23:37:15Z, falls
inside the 08-09 slate's final slot window (fire 23:35–00:05Z, anchor
00:20Z = HOU @ SD).

**F1 (scoped).** Every in-scope fixture on the 2026-08-10 slate kicks off at or
after 22:52Z: `measure_slot_coverage.py --date 20260810` reports 12 of 12 games
covered by four slots beginning 22:22Z, nothing MISSED. **The deployed schedule
offered no sweep slot between 2026-08-10T00:20Z and 22:22Z.** The measurement
comes from ESPN through the repo's own `plan_sweep_slots`, so it does not depend
on `odds_snapshots` and is not circular.

> **F1 was OVERSTATED before this closing step, and the reason is worth
> keeping.** `plan_sweep_slots` applies `MIN_SLOT_SEPARATION_MS` only against
> slots chosen in the *same* plan, and `measure_slot_coverage.py` plans once
> from 10:00Z while the deployed loop re-plans every 900 s. ADR 0014's
> 2026-08-10 annotation already records the resulting **~2x undercount** (6
> planned vs 13 simulated). A one-shot plan therefore undercounts slots **in
> the direction that makes "zero slots" easier to believe.** The open sub-range
> was 2026-08-10T00:22Z–03:20Z: a fixture there is covered by the 00:20Z slot's
> 3-hour `COVERAGE_MS` so it never prints as MISSED, and dropped by the 2-hour
> separation so it never prints as a slot. **Closed by printing the raw
> `fetch_slate("20260809")` kickoff list: zero in-scope kickoffs inside it.**

**F1 licenses:** that the gap has an empty denominator, and that no cause may be
inferred from the gap's *length*.
**F1 does not license:** that the sweeper can still serve; that the
2026-08-09T23:37:15Z stop has an established cause. **Fact 3's "No cause is
established, and none is written here on purpose" is unchanged.**

**F2 — the loop is alive.** Two consecutive full passes committed
`odds_sweep_log` rows **919.2 s apart** (20:53:01.058Z → 21:08:20.274Z), inside
the [765 s, 1035 s] sleep range implied by `--interval 900` and `JITTER = 0.15`
(`backend/scheduler.py:93-96`). Only the runner writes that table, so an
advancing `last_look_ms` **is** proof the loop reached the sweep decision twice.
**One interval is not a cadence** — n = 2 looks is n = 1 interval. Says nothing
about any pass after 21:08:20Z.

**F3 — the two sources agree in structure and disagree in membership.** Live's
`slots_planned` and the ESPN-derived plan agree **to the minute on all four
08-10 slot times** (22:22/23:15/00:53/01:15Z), so both agree on the earliest
kickoff of every cluster. But ESPN counts 9 and 6 games in the two MLB slots
against live's 8 and 5, and the totals reconcile exactly against
`fixtures_upcoming: 13`. Measured state of `odds_snapshots`: **9 of ESPN's 10
MLB fixtures for 08-10, 2 of 2 WNBA for 08-10, 2 of 3 WNBA for 08-11, 0 of 15
MLB for 08-11.** The MLB deficit localises to one fixture commencing in
**[2026-08-11T01:38Z, 01:45Z]**. Whether that is a book that does not quote it
or a store that missed it **is not established**. Say *"agrees in cluster
structure, short by one MLB fixture"* — **never "not depleted"**.

**F4 — live cannot price tomorrow's MLB slate.** For 2026-08-11 live holds
**zero of ESPN's 15 MLB fixtures**. Reading: the fixture store is stale by
construction between sweeps, so `slots_planned` beyond the next sweep **is not a
forecast**. **Testable prediction, and it is what gives F4 teeth:** if the
22:22Z sweep serves, 08-11 MLB slots must appear on the next `/api/window` read.
If a sweep serves and they do not, "stale by construction, self-corrects" is
refuted and something else is dropping fixtures.

> A withdrawn clause, kept so it is not re-derived: an earlier draft claimed
> live scheduled the 08-11 WNBA slot at 23:25Z against ESPN's 22:45Z. **That was
> a transcription error.** `fire_from_ms: 1786488300000` decodes to
> 2026-08-11T22:45:00Z. The two sources agree to the minute.

### Still open, and it is now the only candidate standing

**A latched `x-requests-remaining`.** `CreditBudget.state`
(`backend/odds/budget.py:158-161`) caches the last-seen header from the most
recent `api_credits` row and `refusal_reason` (`:202-223`) checks it **first**.
If the 23:37:15Z response carried a remaining below the sweep cost, every later
call is refused *before the request goes out*, so no row ever updates the cache.
**Self-locking, permanent, loop stays alive, no trace before `1c13b8f`, starts
at exactly a sweep boundary, and survives a deploy** because the value lives in
`/data/cockpit.db`. Nothing observed so far separates it from F1.

**`/api/window` cannot see it.** `refusal_reason` checks **three** ceilings and
the daily one is checked **last**; `ActionableWindow.to_dict`
(`timing.py:438-485`) exposes only `sweeps_remaining_today`, `spent_today`,
`daily_budget`. So *"budget is not binding"* is supported for the **daily**
ceiling only — the cached `x-requests-remaining` and the monthly cap
(`fly.live.toml:122`) are **not established**.

### How to read the 22:22–22:52Z observation

`last_sweep_by_sport(since_ms=10:00Z)` returns nothing for MLB (its last sweep
predates the budget-day start), so the slot **will** be offered.

| Result | Meaning |
|---|---|
| `served`, `last_sweep_ms` advances, `spent_today: 0 → 6` | The sweeper works **on the current build**. Refutes the latch. **Does NOT retro-establish that the 21.5-hour gap was benign** — a restart sits between the gap and the test. |
| `refused` + a named ceiling | Strongest possible outcome, and the branch the deploy cannot confound. |
| `skipped` inside its own slot | The plan and the decision disagree. New defect, and the most interesting of the three. |
| `last_look_ms` frozen at 21:08:20Z | The loop died between reads. Decisive the other way. |

**Capture four fields, not one:** `last_look_outcome`, `last_look_detail`,
`spent_today`, and `slots_planned` for 08-11 (F4's prediction, free).

### The read that would settle it without waiting — blocked on a deploy

One query answers the latch, the monthly cap, **and** whether 08-09 served the
six slots its slate offered:

```sql
SELECT called_ms, endpoint, sport_key, cost, remaining_reported, used_reported
FROM api_credits ORDER BY called_ms DESC LIMIT 5;
```

**Joe's ruling permits a committed script by path only. Do not reach for
`python -c` to get around it; that is the drift already recorded in
`lessons.md`.**

> **CORRECTED 2026-08-11.** This paragraph used to add that `Dockerfile:66`
> copies `scripts/` into the image, "so a script committed today reaches the
> live machine only at the next deploy". **A deploy is not sufficient.**
> `.dockerignore:59-61` is `scripts/*` with `!scripts/run_loop.py` and
> `!scripts/migrate_db.py` — two of thirty-four scripts ship, and
> `inspect_live_db.py` is not one of them. Verified by reading
> `.dockerignore` directly and by `git diff --name-only 799a5f3..HEAD`, which
> touches no file that enters the image.
>
> The consequence is a decision, not a footnote: making the inspector usable on
> the live machine requires **widening `.dockerignore`** — a change to what
> ships to the machine holding real money — **plus** a deploy. See the
> round-three entry below; this is why the four-cell branch was chosen.

### A verb to keep honest

*"The last served sweep at 23:37:15Z falls inside the 00:20Z slot's window"* is
a **time-containment observation, not a causal link.** `decide_sweeps` has two
triggers (`timing.py:640-679`); a `bootstrap` sweep fires outside any slot and
writes an identical `api_credits` row, and that table stores endpoint, cost and
sport — **not** the trigger. Say *"falls inside its window"*, never *"was that
slot's sweep."*

## 2026-08-10 — The documented phone health check cannot pass, and never could

`start.md:199` billed this as *"the single highest-value minute available to the
next session"*:

```
curl -H 'Authorization: Bearer …' https://kalshi-cockpit.fly.dev/api/window
```

**It returns HTTP 401 `{"detail":"Not authenticated. Sign in at /login."}`.**
The gate is `frontend/src/middleware.ts`, a Next Edge middleware matching
`/((?!_next/static|_next/image).*)` that runs **before** the `/api/*` rewrite and
reads only the `cockpit_session` cookie (`<expiry>.<hmac>`, HMAC-keyed on
`APP_AUTH_TOKEN`). **The `Authorization` header is never read by it.**
`require_auth` (`backend/api/routes.py:339`) has exactly one call site —
`POST /api/orders` at `:1103`. `GET /api/window` at `:606` has no auth
dependency at all; uvicorn binds loopback, so the middleware is the whole gate.

**The working recipe** — `POST /session` with form field `token`, keep the
cookie, then GET:

```
TOKEN=$(grep -m1 '^APP_AUTH_TOKEN=' .env | cut -d= -f2-)
curl -sS -c jar.txt -X POST -F "token=$TOKEN" -F "next=/" \
  https://kalshi-cockpit.fly.dev/session
curl -sS -b jar.txt https://kalshi-cockpit.fly.dev/api/window
```

**Why this is its own species of defect.** The existing record covers
*verification methods that lie* — green over broken code. This is the inverse: a
documented verification step that **cannot execute at all**. Its danger is
misattribution — a 401 from a documented health check reads as *"the instance is
down"* or *"auth is broken"*, not as *"the doc is wrong"*. **A next session
running it as written would most likely have concluded the live instance was
unreachable.**

## ⏱ Time-sensitive, and it is free

`.venv\Scripts\python.exe scripts\capture_fills_fixture.py` must be re-run
**after 2026-08-11T05:30Z**. It ran at 18:18:12Z and returned **PREMATURE** —
all four 2026-08-10 positions still `active`, last expiry 05:10Z. **An absent
settlement row is not a $0.00 charge, R5 does not fire, and the ATP position may
not be read alone.** Full statement — including what round three inherits as
still-conditional — is the time-sensitive item at the top of `start.md`.

## 2026-08-11 — RESOLVED: `capture_odds_repeat_poll.py`'s P1 could not fail. Fixed at `39628e0`.

> **THE STOP IS LIFTED.** `39628e0` gives the capture a **pre-flight `/sports`
> probe** (unmetered) and enforces P1 clause 3 against that **live header**. A
> `None` now **refuses** — 30 tests, all 30 observed red under 19 mutations,
> including M1 which restores the original "`None` passes" shape and turns 11
> red. **Amendment A is appended** to the registration; the body is untouched,
> and no hypothesis, prediction, population, statistic, threshold, decision rule
> or destination changed.
>
> **Two things did NOT get fixed and remain open — read them before running it:**
>
> 1. **The per-database / per-account credit gap (§ below) still has no ADR.**
>    Amendment A §A6 records it as open.
> 2. **A new assumed input is registered (F9): `/sports` is unmetered.** If that
>    is wrong the capture costs **25 credits against a 24-credit
>    authorisation** — a one-credit breach of an explicit authorisation.
>    **Joe's call, not an agent's.**
>
> The registration carries **no dated expiry**; its only time-bound is **P4**,
> decided fresh at each `T0` (no event commencing within 20 minutes, at least 5
> within 6 hours). That is *not* the round-three expiry, which is a different
> document.

**The defect, kept for the record — this is what was wrong:**

**The 24 credits are already authorised** (registration §head: *"The capture Joe
authorised: 24 Odds API credits, one shot"*), P0 is satisfied at `60629c2` and
the scripts exist — so any session can run this, and it must not until the fix
below lands.

**Two of P1's three registered preconditions cannot fail on the machine the
script is designed to run on.** `scripts/capture_odds_repeat_poll.py:281-291`
guards clause 2 (`remaining_this_month`) and clause 3
(`x-requests-remaining`) with `is not None`. On the laptop both **are** `None` —
local `api_credits` holds **0 rows** so `remaining_reported` is `None`, and
`.env` sets no `ODDS_MONTHLY_CREDIT_BUDGET` so `remaining_this_month` is `None`
(`backend/odds/budget.py:85-94`). Neither can append to `failures`. The script
then prints **`P1 pass`** at `:301`. All three values *are* printed
(`:267-276`), which satisfies the registration's literal "printed before poll
1" — two of the three lines say `None` and the script reports a pass.

**The comment at `:257-258` states the opposite and is false:** *"The monthly
ceiling and the server's own `x-requests-remaining` are NOT touched and still
refuse."* **They do not refuse. They are absent.** This is
[[the-false-reassurance-in-a-comment-outlives-the-code-it-describes]] sitting on
top of a guard that cannot fire — inside a *pre-registration's* precondition
set, which is worse than in code, because fixing the rules before the data is
the entire purpose of the document.

**Keep the exposure in proportion — this is not a fire.** The script raises the
daily cap to exactly `REQUIRED_CREDITS = 24` (`:259`), so clause 1 *does* bind
and the spend is capped at **24 credits of a prepaid 20,000 tier**. The
deferred live-header check at `:344-350` is real but weaker than P1: it fires
from poll 1 onward against `still_needed = cost * (4 - index)` = **18** at poll
1, so **the first 6 credits are spent on a counter that has never seen the
account.** The defect is the vacuous precondition, not an unbounded spend.

### The fix is free, and the code for it is already in this repo

`scripts/setup_odds_key.sh` (`probe_key`, ~`:227-239`) calls **`/sports`** and
reads `x-requests-remaining` from the response headers. **The Odds API does not
meter `/sports`.** So the account-truthful number was obtainable at zero credit
cost at any moment, including before poll 1.

**Remedy, queued:** give the capture script a pre-flight `/sports` probe and
enforce P1 clause 3 against **that live header**, not against
`state.remaining_reported`. Zero credits, no change to `CreditBudget`. Then
**append an amendment** to
`docs/measurements/2026-08-10-preregistration-odds-last-update-repeat-poll.md`
recording that clauses 2 and 3 were unenforceable as first implemented and what
now enforces them. **Never edit the registration body in place** — Amendment A's
precedent governs.

### The larger finding underneath it, which needs its own ADR

**The credit budget is enforced per-DATABASE; the quota is per-ACCOUNT.**
`CreditBudget.state()` sums this database's `api_credits`
(`backend/odds/budget.py:150-176`). `x-requests-remaining` **is** parsed
(`backend/odds/client.py:278-279`) and **is** enforced first in line
(`budget.py:202-208`, pinned by `tests/test_odds.py:630-639`) — but against the
header **as of this instance's own last call**, cached in this database
(`budget.py:159-162`). Every credit another instance spends in between is
invisible until this one calls and overwrites the cache, i.e. after spending.

**Consequence: `drift` is mis-specified.** `budget.py:97-119` defines it as
`spent_this_month - used_reported` and documents it as *"our cost model
disagrees with theirs"*. With two databases on one key it is
**`(our spend) − (everyone's spend)`**, which trends negative regardless of
whether the cost model is right. `budget.py:18-22` presents that reconciliation
as the meter's central safety property; **it cannot serve that role while more
than one database holds the key.**

**OBSERVED, not merely reachable, and already realised once.**
`docs/measurements/2026-08-10-sharp-anchoring-on-the-record-run.txt:181` shows
the live instance's `api_credits` at `remaining_reported: 19940`,
`used_reported: 60` on 2026-08-09; the laptop's `api_credits` holds **0 rows**
on the same date. And `tasks/NEXT.md` already records a realised instance on the
free tier: *"one local smoke test cost 6 of ~500 monthly credits"*, with
reconciliation catching it only after the fact.

**Why it is money and not just a refused sweep:** the tier is **prepaid**
(`budget.py:3-4`). Exhaustion returns 429 → `QuotaExhausted`
(`client.py:66,70-71`), explicitly *not retryable this period* and explicitly
not a rate limit. The live cockpit then loses its only sportsbook price source
for the balance of the period, `stale_odds` suppresses everything, and the 429
arrives mid-slate. **A local script cannot see the live instance's spend and the
live instance cannot see the script's**, so neither can refuse on the other's
behalf.

**Not established:** no numeric drift for the live instance. The committed
sample shows 2 of its 16 rows, so the apparent `16 x 6 = 96` against
`used_reported = 60` is **not a finding** — row costs and months are unverified
for the other 14. Do not quote it.

---

## 2026-08-11 — The demo instance renders a healthy version of the screen that is empty on live

Four cases were enumerated where a value differs between the seed path and the
production path **and a reader discriminates on it**. Three are being fixed.
**These two are facts, not bugs, and they change how the record should be read.**

### D1. The `surfaced` bucket has only ever rendered on the demo

`reference_contracts` and `suggested_contracts` are **0 on 1,564 of 1,564** live
rows (`docs/measurements/2026-08-10-clean-shortfall-pull.json`). `seed_history`
(`backend/seed_demo.py:407`) writes `rng.randint(10, 30)` into both for
unsuppressed rows — **215** of them on a fresh seed.

`backend/api/routes.py:551`:

```python
if row["suggested_contracts"] > 0:
    (surfaced if item["actionable"] else expired).append(item)
```

**On live that branch has never been taken.** So `surfaced`, `expired`, the size
and cost display, the buy affordance and the entry into the order path are
exercised **only against seeded rows**. The same is true of
`gate.POPULATIONS["actionable"]` — the counter the Gate screen reports against
300.

> **Why this matters beyond coverage.** `actionable = 0` is a **measurement
> outcome** and the central finding of ADR 0021. What was not recorded is that
> the demo instance is simultaneously rendering a *populated* version of that
> same screen. **That makes the live zero easy to read as a display problem
> rather than as the finding it is.** Anyone comparing the two instances is
> looking at the strongest available illusion that the tool "works on demo and
> is broken on live". It is not broken. The row set is empty because the
> strategy surfaced nothing.

**Do not fix this by seeding fewer contracts.** The demo's job is to exercise
the path; the finding is that the path has no live exercise, and the honest
response is to say so wherever the two instances are compared — not to make the
demo emptier.

### D2. `publish()` has exactly one caller — its own `__main__`

`backend/store/publish.py:222`. Nothing in `docker/entrypoint.sh`,
`scripts/run_loop.py` or the scheduler invokes it. **The Parquet lake is written
only when a human types `python -m backend.store.publish`.**

Two consequences, pointing opposite ways, and both need stating:

- **It is the safety** that ADR 0022 §6 identified — `data/lake/` holds 847 rows
  of 2025 demo seed data under `dt=2026-08-0*` directory names with a fully
  built reader, and the only thing stopping it being served is that nothing
  calls `publish`. That safety is now confirmed to be a *missing caller*, which
  is exactly as fragile as ADR 0022 said.
- **It also means every dbt mart may be a claim about nothing** on the live
  instance. If the lake was never written there, `mart_suppression_audit`,
  `mart_clv_by_bucket` and `mart_multiple_comparisons` are computed over an
  empty or stale input. **Not established** — it needs one `ls /data/lake/recommendations`
  over `flyctl ssh console`, which is behind the production-read governance
  question. Until then, **do not cite a dbt mart figure for the live instance.**

### D3. Two more, being fixed now, recorded so the fix is checkable

- **`/api/window`'s `last_look_*` reaches no screen.** The trace added at
  `1c13b8f` is served by `backend/odds/timing.py:475-477` and consumed by
  nothing: `frontend/src/lib/api.ts:620-640` omits the three fields and
  `grep -rn "last_look" frontend/src` returns zero hits. **The readout built
  specifically to make the 17-hour silence visible does not reach the phone.**
  Same shape as the bug it fixed, one hop downstream — the value is correct and
  the consumer does not exist.
- **The demo and live suppression vocabularies are disjoint.** Live is dominated
  by `stale_odds` (616), `too_few_books` (~239) and `no_market_width` (~230),
  with **`wide_market` on 0 of 1,564 rows**. The demo produces `wide_market` 65
  times and the other two **never**, and **never produces a composite at all** —
  so `mart_suppression_audit`'s `string_split(suppressed_reason, ',')` and
  `routes.py:506`'s `.split(",")` are exercised only against single tokens.
  **This has already bitten once:** a preregistered
  `NOT IN ('stale_odds','stale_kalshi_quote')` predicate silently matched the
  wrong population for exactly this reason —
  `docs/measurements/2026-08-09-preregistration-clv-signal-test.md:843,945-984`.

---

## 2026-08-10, overnight — SIX DURABLE FACTS FROM TONIGHT'S LANES

These are **facts and queued items**, not a plan. Two of them close things the
section below still asks for; read these before acting on it. Nothing here is
deployed, nothing here spends money.

### 1. `KXMLBGAME` cannot fill a sub-20c pre-game band. The census below is answered.

The "census the minimum `KXMLBGAME` ask per event" item in the next section has
been run against the stored record. **85 events, 6 slates, 0 of 51,286 pre-game
observations below 20c.** Cheapest pre-game ask ever recorded **26.0c**; p1
**29.0c**, p5 **37.0c**. Cross-checked against `closing_lines.yes_ask_tenths`,
which is independently sourced and puts the floor at **29.0c** — two sources,
same wall.

*(Corrected 2026-08-10: this line previously read "p1 **28.5c**". That figure
reproduces from neither the census nor the audit — both return p1 29.0c. The
audit's own cut, pinned two minutes earlier at 16:58Z, counts 51,206 pre-game
observations rather than 51,286; neither number is wrong and both are printed
with their cut in the result document.)*

**Sub-15c prices exist in the record only 140–215 minutes after first pitch**,
i.e. deep in-play. There is no pre-game route to the band.

**So round two as written is dead**, and it is dead on reachability, not on
budget: a registered band of 6c–14c on `KXMLBGAME` cannot be filled at the
prices the series offers, and the hypothesis boundary `(0.15, 0.27]` sits
entirely below the cheapest price the series has ever shown pre-game. Any
re-proposal must either move the series or state, up front and from the board,
where the price is coming from. See
[[a-reachability-guard-has-to-run-in-both-directions]] and
[[reachability-has-two-halves-and-this-project-keeps-checking-one]] in
`tasks/lessons.md`.

**The honest limit:** this is **one week of one August**, MLB only. It says
nothing about September, nothing about a winter slate, and nothing about any
other series. It refutes the band on the population it covers and no wider.

**Status of the write-up: THE AUDIT HAS LANDED AND THE FLAG IS LIFTED.** The
`measurement-skeptic` lane exported the raw slice, recomputed off-machine with
its own code, and returned **SURVIVES WITH QUALIFICATION** — every headline
number reproduced, all deltas explained by a two-minute cut difference. These
figures are **released** and citable:

> **`docs/measurements/2026-08-10-price-band-reachability-census-result.md`**

The five harnesses are committed at `scripts/census_band_reachability*.py`.
Cite the result document, not this section.

**Two qualifications travel with every figure above and below. Do not quote one
without them.**

1. **`n` is 4 game-days, not 696 instants.** The 696 polling instants are
   **uptime, not evidence**: 64% of them come from a single observation day
   (2026-08-09) and 261 polling sessions cover all of them. The honest
   independent units are **4 game-days, 55 events, 330 pre-game markets, 45
   markets that ever supplied a low ask, 56 low-band episodes**. Concentration
   is good (largest market 8.1% of low rows, largest event 9.2%, all four
   slates contribute) but the deep tail is thin: only **3 markets and 3 events**
   ever printed below 10c.
2. **AVAILABILITY, NOT FILLABILITY.** Every number is a stored quote. Two
   worlds fit all of them equally: real resting liquidity, or a maker showing
   2,914 contracts at 13c who pulls on any incoming order. Depth, persistence,
   two-sidedness and tight spreads **do not distinguish them**, and no quote
   record can. **The separating observation is one small order**, and it has
   not been placed. Nothing here licenses a claim about what would fill.

### 1b. `KXMLBSPREAD` reaches both registered bands, simultaneously — released with the same two qualifications

The escape from fact 1 is **not** tennis (fact 2) and **not** a wider
`KXMLBGAME` band. It is the MLB alternate run line.

**55 events, 330 pre-game markets, minimum pre-game ask 7.0c**, per-event
minimum ask median 15.0c, per-slate minima 9c/10c/8c/7c across four slates.
The low band (6–15c excl 10c) and high band (27–39c excl 30c) were **both on
the board at 696 of 696 polling instants**, and the audit's stronger test found
a **single event** supplying both halves at **695 of 695** — with **658** of
those pairs being the **same strike, opposite teams**. Depth median 2,914 low /
4,624 high; 98.23% of low rows show ≥20 contracts.

**The narrowings that matter, and they are not small:** the band lives
**entirely on alternate run lines** (strike 3.5 and 2.5; **zero** at 1.5,
though the series carries 110 pre-game markets at each strike); **45.8%** of low
rows sit on the band's own 14–15c edge; and restricted to markets still
unsettled at pull time the low band is **10 markets / 9 events**.

**`KXMLBTEAMTOTAL` looks comparable or better on raw availability** (low band at
691/696 instants from **50** distinct events) and **has not been audited at
all** — no within-event test, no artefact check, no persistence measurement. It
is a lead, not a result.

### 2. `KXATPDOUBLES` is not in the record at all

**0 rows** in `kalshi_quotes`, `kalshi_events`, `kalshi_markets` and
`recommendations`. The record holds exactly **11 series**: MLB
GAME/SPREAD/TOTAL/TEAMTOTAL, NFL GAME/SPREAD/TOTAL, NCAAF GAME, WNBA
GAME/SPREAD/TOTAL.

This matters because the escape hatch from fact 1 — "a within-series price pair
in `KXATPDOUBLES`" — is written in the section below as though the prices were
knowable from disk. **They are not.** Any ATP work needs a **live board read**
first, and that read is a precondition, not a detail.

### 3. Odds fetching stopped at 2026-08-09T23:37:15Z and ran 17+ hours unnoticed behind a green health check

Last odds observation in the record: **2026-08-09T23:37:15Z**. The loop was
**alive the whole time** — it kept writing ~5,000 quote rows an hour — and the
health check stayed green throughout. Every `recommendations` row written in
that window carried `stale_odds`.

**No cause is established, and none is written here on purpose.** This repo has
a recorded misdiagnosis of exactly this shape (ADR 0014: a frozen counter blamed
on the sweep scheduler, when the slate was empty). The observation is the fact;
the cause is **open**. Candidate explanations must be distinguished by evidence
before one is written down.

> #### ANNOTATION 2026-08-11 — **fact 3 is TWO facts. One of them now has a mechanism. The other is still uncaused.**
>
> **Nothing above is withdrawn.** *"No cause is established, and none is written
> here on purpose"* still governs — read the split before using any of this.
>
> **(i) Odds fetching STOPPED. Still uncaused. Nothing below touches it.**
> No candidate explanation for the stop is offered, supported or excluded here.
> ADR 0020 remains the reserved owner and remains unwritten.
>
> **(ii) It went UNNOTICED for 17 hours. This half now has a mechanism, and it
> is structural rather than circumstantial.** `backend/odds/timing.py`
> `_latest_sweep_row` filtered `WHERE endpoint = '/odds'`. There are exactly
> **two** writers of `api_credits.endpoint` in the repo:
>
> - **production** — `backend/odds/budget.py:257`, the only `INSERT`, fed by
>   `backend/odds/client.py:273` as `endpoint=path`, where `path` is
>   `/sports/{sport_key}/odds`;
> - **demo/seed** — `backend/seed_demo.py:321-323`, the hardcoded literal
>   `'/odds'`.
>
> Two writers, exhaustively enumerated, and they disagree — so the claim is
> **structural, not a sample**: the equality matched **every demo row and zero
> production rows**. Corroborated by a real dump,
> `docs/measurements/2026-08-10-sharp-anchoring-on-the-record-run.txt:181`,
> showing `'endpoint': '/sports/baseball_mlb/odds'`.
>
> **Consequence:** `window_status.last_sweep_ms` was permanently `None` on the
> **live** instance and correct on the **demo** instance, so
> `frontend/src/components/WindowBanner.tsx:91` showed no last-sweep age on the
> machine that holds real money. **The readout that would have shown odds
> fetching had stopped had never worked on live, and worked perfectly on the
> instance used to check it.**
>
> **Fixed at `1c13b8f`** by a shared predicate
> `_SERVED_SWEEP = "endpoint LIKE '%/odds' AND cost > 0"` used by both readers.
> `seed_demo.py` needed no change — `%` matches the empty string, so both
> spellings work.
>
> ### The boundary, and it is the whole point of splitting the fact
>
> **(ii) is not a diagnosis of (i), and combining them would be ADR 0014
> exactly.** A blind readout explains why nobody *saw* the stop. It offers no
> account of why fetching stopped, and it cannot: the readout is downstream of
> the sweep and reads a table the loop was not writing to during the window.
> **Do not let a future session read "the last-sweep readout was broken" as
> "that is why the odds stopped."** They are different claims and only one of
> them is supported.
>
> **A third thing is also still unexplained.** The **health check stayed
> green**. `_latest_sweep_row`'s blindness explains the WindowBanner's silence
> and nothing else; the Fly health check
> (`fly.live.toml [checks.health]`) is a separate surface with a separate
> predicate and this finding says nothing about it. So fact 3 is really three
> observations, of which one now has a mechanism.
>
> **What it does establish, and it is worth stating plainly:** the project's
> primary staleness readout was verified on an instance where it worked and
> deployed to an instance where it could not. That is
> [[a-detectors-production-must-be-the-deployments-production]] realised on the
> money instance, and it is why `1c13b8f` is a bigger result than the
> refused-sweep trace it was found while building.

### 4. A refused sweep leaves no trace in any table in the record

Checked across the whole schema (`backend/store/schema.sql`). Three independent
silences, each individually reasonable:

- `api_credits` gets a row **only if an HTTP call was made** —
  `backend/odds/client.py:233-234` returns `[]` before the request when
  `can_afford` is false, and the insert is at `backend/odds/budget.py:236`.
- `notifications` writes `window_open` **only when `sweeps_this_pass > 0`**
  (`backend/notify/alerts.py:183`).
- `decide_sweeps` returns a `detail` string that is **only logged**
  (`backend/runner.py:868`), and `flyctl logs` is lossy.

So **silence is indistinguishable from a system that never looked**, which is
why fact 3 went unnoticed for 17 hours.

**QUEUED — and read the trap before choosing the fix.** The obvious remedy is a
zero-cost row in `api_credits` recording the refusal. **That remedy is unsafe as
stated:** `last_sweep_by_sport` (`backend/odds/timing.py:315-322`) filters only
on `called_ms >= ?` and `sport_key IS NOT NULL`, with **no endpoint or cost
filter**, so it would read the refusal row as a *served* sweep and silently
disable the scheduler for that sport. A separate table, a `cost = 0` filter
added to that query first, or a different sink entirely are all viable. **The
remedy is queued, not chosen.**

### 5. Config drift: `ODDS_DAILY_CREDIT_BUDGET` is 400 deployed against a code default of 16

`fly.live.toml:116` sets `400`. `backend/config.py:194` defaults to `16`, and so
does `.env.example` — which CLAUDE.md names as **the contract**. Not binding
today, because the deployed value is the larger one. **A rollback or a
regeneration of `fly.live.toml` drops the budget 25x, silently**, and the
symptom would be refused sweeps, which per fact 4 leave no trace.

Related and now annotated: ADR 0014's "6 sweeps, 36 credits" is the *one-shot
plan's* count, not the loop's; the dynamic figure is roughly 2x. See the
annotation appended to `docs/adr/0014-the-sweep-schedule-is-accepted-as-it-stands.md`.

### 6. `beb91d8` is committed and **unpushed**

`config: the quote-age pair now refuses to start when it disagrees` — adds
`assert_kalshi_quote_age_limits_agree`, closing the twin of the pair ADR 0019 §6
closed.

**Why it mattered:** a divergence between the two quote-age limits let a
12-second-old quote leave suppression with `suppressed_reason IS NULL` —
**actionable, and counted in the gate's 300-game denominator** — while
`backend/gate.py:746` and `backend/api/routes.py:1946` refused the same quote.
The screen and the denominator disagreed with the order path.

---

## ⏱ 2026-08-10, evening — RUN THIS FIRST, THEN READ THE REST

**Read this first. It supersedes everything below it.**

```
.venv\Scripts\python.exe scripts\capture_fills_fixture.py
```

Laptop only, seconds, **no money, no deploy, no orders.** `/portfolio/fills` has
a measured retention window with an upper bound near **three months**;
`/portfolio/settlements` is the durable record. Predictions were committed
**before** the data existed:

| position | Σ fill fees | granularity changed | settlement is a different quantity | old cent model |
|---|---:|---:|---:|---:|
| `KXMLBGAME-…BALMIN-MIN` | $0.0088 | **$0.0088** | **$0.01** | **$0.02** |
| `KXMLBGAME-…TEXLAA-LAA` | $0.0088 | **$0.0088** | **$0.01** | **$0.02** |
| `KXMLBGAME-…KCLAD-KC` (3 orders, 11.27 contracts) | $0.0778 | **$0.0778** | **$0.08** | **$0.16** |
| `KXATPDOUBLES-…CERETC` | $0.1785 | $0.1785 | $0.18 | $0.18 |

**The ATP row does not discriminate. Do not read it** — reading 3 and the old
cent model both predict $0.18.

**GUARD (R5), registered:** no settlement charge **AND** no visible entry fees
means you are measuring nothing — **STOP THE LINE, naming the harness, not the
exchange.**

**Settles:** which of the three readings of the settlement-vs-fill contradiction
holds, and **H4** (settlement charges no second fee). **Does not settle:** the
rate attribution — H-SERIES / H-SPORT / H-SIZE / H-PRICE / H-NOTIONAL are
untouched.

**Then, also free, before any round three:** census the **minimum `KXMLBGAME` ask
per event over the stored `kalshi_markets` record** — it decides whether the
sub-15c band is *ever* reachable, i.e. whether the dead end below is real or was
one bad evening. Zero cost, data already on disk.

### §7.2's magnitude is MEASURED on the record now — the unit is the ROW

`docs/measurements/2026-08-10-sharp-anchoring-on-the-record-result.md`, audited.
**The fixture's "26 of 29" is replaced by a median of 19 usable discarded of 21,
per recommendation row.** Three units give three answers (234 instants → 20 of
23; 68 events → 20.5 of 23; **1,564 rows → 19 of 21**), and the row is right
because §7.2 is a claim about rows. The fixture **overstated by ~5.5 books** on
its own unit. Devig rejected **zero** books — `fair_prices.books_used`
recomputed from raw snapshots matched **21,550 of 21,550** h2h rows.

**27.0% of rows (423/1,564) have `anchored_on_sharp = 0`.** **This is NOT a
partial run of Option B** — those rows fell back because the sharps were
*missing*, so the subset is skewed **thin** (median 12 books vs 23 overall, 29
on a typical anchored instant; 385/423 MLB; 190 already `stale_odds`). **And it
returned nothing: 0 of 189 clean wide-consensus rows had a positive edge.** That
is a reason to doubt Option B, not to run it.

**`betfair_ex_uk` is ABSENT** — 0 rows, all markets, whole window. `SHARP_BOOKS`
advertises four and has three reachable. **Cause NOT established**, and the
obvious story is contradicted (`ODDS_REGIONS=us,eu` yet `williamhill`,
`marathonbet`, `matchbook` appear). **Do not add the `uk` region** — +50%
credits per sweep for the same exchange as `betfair_ex_eu`.

**Correct ADR 0021 §7.2's annotation:** it claims `anchored_on_sharp` is *"not
on this record either."* **False** — it is on `fair_prices`, written on every row
since the table existed, merely unexposed by `/api/ledger` until `4938701`.

**Row count measures polling uptime as much as evidence:** 1,564 rows rest on
**172 of 234** stored instants and 205 cycles.

### The record was RE-SCORED under all three fee models — and this is the decision

`docs/measurements/` (Lane A), audited, **12 corrections taken**.

```
                              max E1    rows E1>0    SURFACE
deployed  0.07 ceil-to-CENT   -2.0534     0/614         0
step 1    0.07 ceil-$0.0001   +0.5466     3/614         0
step 2    0.035 ceil-$0.0001  +9.2466     9/614     4 rows / 3 claims / 3 games
```

**ADR 0021's conclusion SURVIVES step 1 and FALLS under step 2.** So the rate
attribution — round two — is now the only thing that decides it.

**The finding nobody expected:** those same three rows **clear the fee under the
UNCHANGED deployed model at 25+ contracts.** The old fee rounded up *per order*,
so one contract paid the whole ceiling and 25 spread it. `sizing.py` prices every
decision at `C=1` and never re-prices. **Part of "no edge" was the tool always
choosing the most expensive way to buy** — and that is independent of which fee
model wins.

**Corrections to `partner`'s hypothesis:** `edge_within_method_noise` refuses all
three step-1 rows, but the **reference sizing floor refuses them independently** —
delete either and the answer is still zero. That floor is a **config value**: it
stops firing above a reference bankroll of ~**$1,822**. "Decorative guard becomes
decisive" lands under **step 2**, not step 1, where it fires alone 5 times and
decides 4 bets. **Step 1 is not "well supported" as a whole** — its *rounding* is;
its *coefficient* is refuted at three MLB cells by ~2×, and every surfacing row is
MLB. And the **NOTIONAL** attribution breaks step 2: three of the four survivors
have notionals above $3.00 and would take the high rate, where none surfaces.

### THE ACCOUNT HAS FILLS NOW — six of them, and both fee models are dead

Joe ran **ADR 0021 Option E** on 2026-08-10. Artefact:
`docs/measurements/2026-08-10-fee-model-fill-calibration-result.md`, audited by
`measurement-skeptic`. **Verdict H3−: both registered models refuted at all four
cells, every observed fee below `min(A, B)`.**

**SOLID:** Kalshi charges **sub-cent** fees as of 2026-08-10 — `core/fees.py`'s
cent-granular contract is **wrong for the current schedule**. Reported `fee_cost`
is **`ceil` to $0.0001**; scope is **per-order**, refuted coefficient-free.
**Model A's *coefficient* is confirmed to seven decimals** at the ATP cell
(`0.07 × 20 × 0.1275 = 0.1785000`, charged `0.1785`) — **only its cent ceiling is
refuted**, never write "Model A is refuted" bare. And **`$0.0001` is not
representable in `core/prices.py`'s integer tenths of a cent**; that units
question is an **ADR, not a patch**.

**NOT WRITABLE:** *"the rate is per-category."* **Five** attributions fit all six
fills equally — by **series**, **order size**, **price region**, **sport**, and
**notional stake** (a threshold in `($2.70, $3.00]`). `k = 0.035` is writable only
as *"at `KXMLBGAME`, `C ∈ {0.27, 1, 10}`, `P ∈ {0.27, 0.48}`, on 2026-08-10."*
**No change to `calculate_fee`, to `CLAUDE.md`'s 52.00% bar, or to ADR 0021** —
§2 of the registration forbids deploying a model fitted to these fills. **The
`max()` hedge stays.**

**The decomposition — never quote the bottom row alone:**

```
                                          fee@50c  break-even  headroom  S_min E1   sizes?
deployed   0.07, ceil-to-CENT             $0.0200    52.00%      0.38     -2.0534     NO
step 1     drop the cent ceiling only     $0.0175    51.75%      0.63     +0.5466     NO
step 2     also halve the coefficient     $0.0088    50.88%      1.50     +9.2466    YES
```

**ADR 0021's refutation is NOT overturned by the well-supported half.** Step 1 is
solid; step 2 is 77% of the win and a post-hoc fit at two prices in one 14-minute
window. Under step 1 alone `S_min` reaches +0.5466 tenths — **below** the
1.0-tenth sizing supremum, so it does not size. Also **`KXWNBAGAME` is 422 of
1,564 rows (27.0%) with zero fills**; a naive `k=0.035` moves 137 → 206 positive
rows of which **85 are WNBA**.

**Two findings that stand on their own:** `gate.py`'s `_fee_model_verified` has
**never been able to fire** (nothing in production writes `fills`), so nothing in
this codebase would have caught the fee model being wrong — **and it was**. And
**Kalshi's own app displayed a `$0.02` estimate and charged `$0.0088`**, a 2.3x
overstatement, with `$0.02` being exactly Model A — the likely origin of the
wrong coefficient here.

### Round two: REGISTERED AND NOT RUN, and the reason is a repeat defect

`docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-two.md`
would have broken the confound for ~$4. **Zero fills placed, so nothing in it is
contaminated and it is reusable as written.**

**The cheapest `KXMLBGAME` game-winner ask on the board was 28c** — full list,
live games included — against a required band of **6c–14c**. Every price-region
threshold consistent with round one lies in `(0.15, 0.27]`, so **the whole
boundary interval sits below the cheapest price the series offers**, plausibly
always: MLB moneylines cluster ~20–80c.

**The defect, named because it is the second time:** §3 claimed a reachability
precondition and checked the cells would *discriminate* if filled. It never
checked the band was *fillable*. **That is the joint bound's failure exactly.**
Check both halves, always.

**D1/D2 were not two cells of four — they were the design.** Isolating SIZE from
NOTIONAL forces `P ≤ 0.135`; isolating PRICE at `C = 1` forces `P ≤ 0.15`. The
band carried **three of the four separations**.

Rulings in **Amendment B** (`8e86500`) not to re-derive: **in-play is rejected on
a confound, not a policy** (it is the only route to the band, so in-play state
and sub-15c price are perfectly collinear and H-INPLAY's vector is identical to
H-PRICE's); **the mirror does not rescue it** (a NO at 12c is a genuine 12c fee
observation, but H-PRICE's prediction there is undetermined — and it is moot,
since `KXMLBGAME` lists two markets per event, one per team, so the underdog is
buyable as a genuine YES; the constraint is baseball's variance, not the book
side); **`C = 10` at 31–39c isolates NOTIONAL with no low price at all**
(registered as Cell N, consumes ~$4 alone); and **the escape if the census kills
the band** is a within-series price pair in `KXATPDOUBLES` (~$0.54), with the
transfer back to `KXMLBGAME` resting on H-PRICE's own global-rule claim and
labelled as doing so.

---

## 2026-08-10, overnight — THE REFUTATION IS WRITTEN, AND IT QUOTES A FIXTURE AS A FACT

**Read this first. It supersedes everything below it.**

`main` at **`d00430d`**, **pushed, in sync**. **1,964 tests**, ruff clean,
`next build` clean, tree clean. **LIVE IS UNCHANGED** — everything is committed
and *undeployed*, and the bundle still carries the **Next.js middleware-bypass
security patch**.

### 0. This file and `start.md` were both WRONG about what was left to do

Yesterday's `start.md` led with *"the refutation ADR is now unblocked, and it is
the critical path."* **`docs/adr/0021-the-consensus-only-strategy-is-refuted.md`
already existed and was committed.** A session read it, believed it, and would
have re-derived a finished document.

**`start.md` is a snapshot; `git log` is the record.** Before acting on any
"still to do" here, run `git log --oneline -20` and `ls docs/adr/`. Thirty
seconds, and it caught a whole wasted lane.

### 1. §7.2's "26 of 29" is a fixture number applied to a record it does not overlap

ADR 0021 §7.2 — the section carrying the **strongest attack on our own
refutation**, that the whole thing may be a tautology — says sharp anchoring
*"discards a **median of 26 of 29** usable books"*.

That is measured on `tests/fixtures/odds_mlb_h2h_spreads_totals.json`, captured
**2026-08-07T13:49:22Z**. The record's odds observations run
**19:28:12Z → 08-09T23:35:18Z**.

```
rows at or before the fixture capture      0 of 1,564
minimum gap                                5.647 hours
```

Both directional checks err *toward* finding overlap. Neither found any.

**The number is right and only its address is wrong.** `26 of 29` reproduces to
the digit through the production path on the fixture, and the registration
labelled it correctly as `[MEASURED FROM DATA — tests/fixtures/…]`. **ADR 0021
dropped the label.**

**Scope it honestly — the exciting reading is the wrong one.** §7.2's *argument*
does not fall. What is extrapolated is only the **magnitude**. §7.2 survives; its
number does not, and may be quoted only as *"measured on one MLB fixture captured
5.65 hours before the record begins"* — never bare, never as a property of the
1,564 rows.

Annotated in all five places it had reached: `docs/adr/0021` (annotation),
`docs/adr/0019:522`, `tasks/lessons.md`, `start.md`, item 2 of §5 below, and the
registration (**Annotation B, appended** — the body carries no inline marker
anywhere, following Amendment A's precedent, so none was added).

**The populations differ in *time*, not in kind, so nothing about the sentence
looked wrong.** That is the new variant of
[[a-true-measurement-licensed-a-false-conclusion]] and it is now in
`lessons.md`.

### 2. `measurement-skeptic` caught the correction over-claiming — and it produced a field

Verdicts: **A SOUND, B SOUND WITH CORRECTIONS, C SOUND.** All corrections taken,
none defended. The load-bearing one:

**The draft said sharp anchoring applies "by construction". False.** The code is
`selected = sharp or usable` — anchoring is *attempted* on every row, but whether
it **binds** is data. Where no sharp book quoted, the row was priced against the
**wide** consensus. That is the over-claim appearing *inside the paragraph
correcting an over-claim*.

So `anchored_on_sharp` — **written on every row since the table existed, read by
nothing** — is now on the `/api/ledger` payload. Without it §7.2's central claim
is **unfalsifiable on the record**.

Two other corrections: the `pin = 1549` pull is a **checksum, not
corroboration** (strict subset, zero differing rows); and "never observed" was
too strong — `reason_text` carries `book_count` on all 245 `too_few_books` rows.

### 3. Option B is testable at ZERO credits, and this is the newest fact here

`odds_snapshots` is **append-only and stores every book** (`schema.sql:189-207`).
Sharp anchoring is a **read-time** filter (`runner.py:658` →
`devig.py:290-291`), **not a write-time discard.** The schema comment states the
intent verbatim: *"the moment we store only a consensus we lose the ability to
re-run with a different method."*

So the wide-consensus recompute over the **real** record needs no Odds API
credits. It needs one of: the `_serialise` widening in the next deploy
(committed, waiting), or one query on the volume.

**A fixture proxy for this was proposed and killed by `partner`** — running it
would have manufactured a second copy of the exact defect §7.2 was being
annotated for. **Do not resurrect it.**

### 4. The orphan count was six. It is NINE — ADR 0022

`tests/test_has_callers.py` is **inverted** from an opt-in allowlist to
**enumerate-and-classify**: an *unclassified* symbol now **fails**.

**All fifteen `MUST_HAVE_CALLERS` entries named symbols that already had
callers.** The list had never once been pointed at anything orphaned at the time
— a ratchet against *re*-orphaning, structurally incapable of finding what nobody
suspected. Two structural holes:

- **`scripts/` counted as a caller, but `.dockerignore` admits 2 of 34 scripts
  into the image.** Five of the nine were invisible for this reason alone. The
  clearest evidence: adding `build_leg` to the list turned the new
  shipping-caller check **red while the two older checks on the same symbol
  stayed green.**
- **Import counts as use.**

| Class | Modules |
|---|---|
| **`Tool`** (a human runs it; absence from the image is correct) | `backend/main.py`, `store/publish.py`, `analysis/joint_bound.py`, `kalshi/combos.py`, `model/synthetic.py` |
| **`Quarantined`** (nobody runs it; parked with a stated revival condition) | `agents/scout.py`, `agents/historian.py`, `model/elo.py`, `model/backtest.py` |

**Disposition is quarantine — do not wire, do not delete.** Wiring Scout and
Historian means live Anthropic calls, and the bill is held at zero by
`surfaced == 0`. **`elo.py`: do NOT wire it up.**

Verified red in **three directions** plus two permanent anti-vacuity guards.
Green proves nothing here — an enumeration that enumerates nothing passes
everything.

Also corrected: **four** partially dead, not three. The unnamed one is
`backend/core/correlation.py`, and it is the interesting one —
`implied_correlation` is the measured data source `lessons.md` calls the payoff
of the KXMVE correction, and it reaches nothing on the instance.

### 5. A landmine, recorded not fixed — and worse than it was briefed

`data/lake/` holds `recommendations` partitions named `dt=2026-08-0*` containing
**847 rows stamped 2025-07-23 → 2025-08-10** — demo seed data wearing the
record's directory names. `fair_prices` and `event_links` are **0 rows** (as are
`fills`, `lessons`, `model_ratings`, `unmatched_events`).

**"Nothing reads it" is FALSE.** The dbt warehouse reads those partitions
directly (`stg_recommendations.sql:25`) and `/api/dashboards` reads the marts
built from them. **The reader is fully built.** The only thing between 2025 demo
data and a 2026-labelled screen is that `docker/entrypoint.sh` happens never to
invoke `publish` or `dbt build` — verified directly against the script.

**The safety is an accident of the boot script, not a design.** ADR 0022 §6.

### 6. The queue

1. **ADR 0020 — `stale_odds` reads a scrape clock.** Still the open ADR; the
   numbering runs 0019 → 0021 → 0022 and **0020 stays reserved for it**.
   **`partner` deliberately deferred deciding the remedy**: the evidence that
   settles it is Joe's repeat poll, which lands in hours, and choosing first
   inverts the order this repo keeps an agent to prevent. **Write it after the
   poll.** Details at §5 item 1 below — and quote **320**, not 440, not 335.
2. **Whatever Option Joe picks from ADR 0021 §8.** Do not start B, C, D or F
   speculatively — each is a different project with a different question, and §8
   says so. **`partner`'s position: Option E first** (four fee-calibration fills,
   already authorised), because §7.4 means every number in ADR 0021 moves if the
   fee model is wrong and this account has **zero fills, ever**.

   > **[DONE 2026-08-10 — E ran, and §7.4's condition is MET: the fee model IS
   > wrong. "Zero fills, ever" is also now false twice over.]** See the top
   > section of this file. **A–D and F remain open and none is started**, and the
   > A-vs-F call should wait for the settlement capture and the rate attribution,
   > because E's answer partly reopens the question A was going to close.
3. **The three queries neither agent could run** —
   `docs/measurements/2026-08-10-three-queries-the-agents-could-not-run.md`, with
   pre-stated expected outputs. **All six statements were executed against a
   seeded real schema before the document was committed**, catching three defects
   that returned confident wrong numbers rather than errors. **All three need
   `flyctl`, which is a laptop job and Joe is phone-only.** Q2 is one
   `_serialise` line from being phone-answerable; left undone deliberately, with
   the reason written down.

### 7. Deferred overnight, with reasons

- **The symbol-level orphan tail.** ADR 0022 §3.4 deliberately did **not**
  hand-write a table of the 39 — that would reproduce the opt-in defect one level
  down. The symbol half got two *derived* checks instead; all 15 entries pass, so
  it starts as a ratchet rather than a debt.
- **The `data/lake/` landmine** — recorded, not fixed.
- **`§S13` / §10 duplication** — unchanged; the fix is to delete one of the two
  texts, not to test that they agree.

---

## ⚠ 2026-08-10 — READ THIS IF YOU ARE A PARALLEL SESSION

Infrastructure changed underneath you, from a session running in parallel. This
does **not** supersede the technical work below — it is a different lane. But
these four points will cost you time if you meet them cold.

1. **THE REPO IS NOW PUBLIC.** Every push publishes to the world immediately.
   Before committing a measurement, fixture, log capture or screenshot, ask
   whether it should be world-readable. Screenshots of the live UI are the
   sharp edge — one live run away from showing a real position or bankroll.
2. **Push protection is ON.** A push containing anything that looks like a
   credential will be **rejected by GitHub**. That is the guard working. Do
   **not** bypass it — stop, look at what tripped it, and rotate if it is real.
   Nothing in existing history trips it: GitHub's own scan of the full history
   returned **0 alerts**, independently confirming the gitleaks audit.
3. **CI now cancels superseded runs.** If you push twice in quick succession
   and the earlier run shows `cancelled`, **that is not a failure and not
   something to debug** — `ci.yml` gained `concurrency` with
   `cancel-in-progress: true`. Judge CI by the run on your latest SHA.
4. **`.github/workflows/**` and `.gitignore` were edited.** Pull before touching
   either. `.tmp_*` is now gitignored and `.tmp_shots390/` was removed from the
   tip, so screenshot and probe scratch output is no longer committable — which
   is intended.

Nothing in `backend/`, `tests/`, `warehouse/` or `frontend/` was touched, so
work in progress there is unaffected.

---

## 2026-08-10, end of session — ADR 0019 LANDED, AND THE REPORTED BUG WAS WRONG

**Read this first. It supersedes everything below.**

`main` at `e350867`, pushed. **1,911 tests, ruff clean, `next build` clean.**
**LIVE IS UNCHANGED** — everything in this session is committed and *undeployed*.

### 0. BEFORE THE NEXT DEPLOY — one new way to fail to boot

ADR 0019 §6 adds `assert_odds_age_limits_agree`, called at startup by **both**
`create_app` and `run_loop`. It **raises** when
`SuppressionConfig.max_odds_age_ms` (hardcoded `900_000`) disagrees with
`MAX_ODDS_AGE_S`. That is deliberate — the divergence it catches is silent, and
a warning nobody reads is not a control — but it means a mismatched value now
**stops the container instead of quietly skewing the window.**

Checked: `fly.live.toml:128` is `"900"`, `.env.example:71` is `900`, and
`fly.demo.toml` omits it so it takes the `900` code default. All three agree, so
this is safe to deploy **today**.

**Not checked, and it cannot be from this machine: whether a Fly *secret* sets
`MAX_ODDS_AGE_S`.** A secret overrides `[env]` invisibly. Confirm with
`flyctl secrets list` before deploying, or the first symptom is a crash loop.

### 1. The reported bug was misdiagnosed, and that correction is the ADR

`start.md` led with *"`edge_within_method_noise` cannot fire on the one input it
was built for."* **It was not built for that input.** Its own comment scopes it
to method-choice ambiguity, and on a symmetric two-way line method choice
contributes genuinely zero ambiguity — every method returns 0.5 because the vig
splits evenly. The guard passing says *"method choice does not explain this
edge"*, which is **true**. The defect in the worked example is that one book's
dead line became a consensus: a `book_count` fact, caught twice.

Do not re-open it as a bug in that guard.

### 2. What is actually wrong — and no new guard was added

Three guards — method spread, market width, book count — are three readings of
**one** question, *do the sources agree?*, and correlated garbage agrees with
itself perfectly. **Measured:** two books quoting a symmetric line give
`fair = 0.5`, `market_width = 0.0`, `book_count = 2`, `reason=None`. They need
not agree on the hold — multiplicative devig of a symmetric line is exactly 0.5
for any odds, so a 33.3%-hold book and a 2.6%-hold book look like perfect
agreement.

**So `min_book_count = 2` does NOT bound the defect.** NEXT.md's old "all
single-book" described rows *observed*, not what the guards *permit*.
**Reachable, and NOT observed** — 0 of 15 events in the real capture.

Three fixes were considered and **all three rejected, with reasons in the ADR**.
Do not re-propose them: refusing on unmeasurable dispersion fires on exactly the
rows two codes already fire on; an epsilon floor is an off switch wearing a
guard's clothes (the guard's median demand on real live-path input is **1.3
tenths** against a **20.0-tenth** fee, so it is essentially never binding); and a
symmetry detector targets the wrong feature, since **43.8% of h2h quotes
duplicate another book's**.

**What actually bounds it, and it was never justified for the job:**
`edge_ceiling_tenths`. A fabricated 0.5 fair only surfaces at an ask in
**[440, 479] tenths = 44.0c–47.9c**, a 4.0c window where the fabrication is
nearly right anyway. Now declared and pinned. Measured by deformation: raising
the ceiling to 50.0 — a 25% wider hole — was **green across every pre-existing
test**.

### 3. Strategy versioning was broken, and the ADR draft claimed otherwise

`ensure_strategy_config` hashed `suppression.__dict__` — field **values** — so
adding, removing or renaming a check **minted no version**, and two check
vocabularies would have pooled with nothing recording the split.
`suppressed_reason` is half the `actionable` predicate. Fixed:
`ALL_CHECK_NAMES` is hashed as `suppression_checks` and pinned against the
source. **Prospective only** — it does not retroactively split anything.

### 4. THE CLEAN-SHORTFALL RUN STOPPED THE LINE — and that is the guard working

Registration **committed at `81d59bc` before the run**, which is what makes it a
pre-registration. Result:
`docs/measurements/2026-08-10-clean-shortfall-distribution-result.md`.

```
*** STOP THE LINE ***   tripped: R3 (saturated: Grid D)
Grid D middle cell [173, 827] holds 320 of 323 clean observations = 99.1%
```

**H4, H2, H3a, H3b and H1 are all WITHHELD. Nothing is declared or refuted, and
the refutation ADR may not be written from this run.** Do not quote a verdict
from it; the harness deliberately withheld them rather than printing "would have
been X", because printing the parenthesised answer hands a future registrar the
results before any amendment relaxing R3 is written.

**This is the joint bound's missing symmetric guard, installed and firing.** The
joint bound died because nothing checked whether its decision value was
reachable; this registration checked, in both directions, and stopped itself.
That is the instrument behaving correctly, not a failure.

**But the census statistics print regardless — §S mandates it — and they close
ADR 0019's open input:**

```
n_degen, clean population        0        <- reachable, never occurred
n_degen, suppressed (control)   21        <- the predicate demonstrably fires
clean degenerate rows in [440,479]  0
```

All 21 are **one-book** fairs, in 2 WNBA games, every one suppressed — caught by
the deployed guards. The two-book case ADR 0019 proves reachable **has not
happened**.

Two honest riders. The ULP correction **cost nothing here**: all 21 carry
`p_power` exactly one ULP below 0.5, so broad and narrow predicates returned the
same 21 and the measured undercount is **0**. It was still right to make. And
**R2 fired usefully** — 15 rows arrived since the last pin and *all 15 are
suppressed*, so the clean population is byte-identical to the previous pull and
H1 was labelled `REPRODUCTION — NOT A NEW OBSERVATION`.

**H3b remains the open question and is now the reason to re-register:** the
2.1-tenth shortfall sits *inside* the measured live-path devig spread
`[0.32, 4.61]`, so *"the nearest is 0.21c short"* may not be writable at all. A
re-registration must decide what to do about R3 — Grid D saturating at 99.1% is
a fact about the record, not a defect, and a rule that can never clear it is a
rule that can never report.

> **[ANSWERED 2026-08-09 — and the re-registration was the wrong instrument.]**
>
> **H3b is REFUTED.** Not "may not be writable" — **is not writable.**
> `S_min = 2.0534` tenths against `spread_at_min = 2.3191` on the whole-record
> clean population. The shortfall is smaller than that same observation's own
> devig spread.
>
> **And the re-registration was killed rather than written.** Every statistic
> this question turns on was already committed at `3f2fa1a` and pushed to a
> **public** repo, so there was nothing left to blind — a fresh
> "pre-registration" would have been a rule chosen with the answers in hand,
> wearing a pre-registration's clothes. What was written instead is an **open
> ruling with the contamination declared**: Amendment A (`3a0716d`) and
> Addendum A (`33f1219`).
>
> **The R3 decision, stated answer-independently so it generalises:** *a
> stop-the-line guard may only be predicated on a cut that at least one
> hypothesis's decision rule reads.* No hypothesis reads Grid D, so its
> saturation clause is a **labelling** rule and may not withhold a verdict.
> R1, R3's `G < 2` twin and R4's H4 twin keep stop-the-line status. Grid D
> keeps its `DEGENERATE` banner and still may not be cited in any conclusion —
> releasing the verdicts did **not** release the cut.
>
> Five verdicts released: H1 DECLARED (`REPRODUCTION`, `n_new = 0`), H2
> DECLARED, H3a DECLARED, **H3b REFUTED**, H4 DECLARED. **Do not describe H3a
> as having answered H3b** — §7 forbids it explicitly.

### 5. The queue

1. **ADR 0020 — `stale_odds` reads a scrape clock.** `odds_age_ms` comes from
   The Odds API `last_update`, which is a **scrape** timestamp: **320 of 320**
   book+event pairs quoting more than one priceable market share one stamp
   across every market they quote, and **27 of 30** books carry exactly one
   stamp across fifteen games. **The false message is already corrected;** the
   remedy is undecided and has three live options.

   **Quote 320. Not 440, and not 335.** This read "440 of 440" until
   2026-08-09; 120 of those pairs quote a single priceable market, where
   unanimity is vacuous. The first fix said 335 and was *also* padded — it
   counted raw payload keys including `h2h_lay`, which `EXCLUDED_MARKETS` never
   stores. Corrected in four places (here, `start.md`, `docs/adr/0019`,
   `backend/core/suppression.py`) and re-derivable at zero credit cost with
   `scripts/census_odds_stamps.py`.

   **Do not say "it measures our polling cadence."** The aggregator scrapes on
   its own schedule; our polling only samples it. The defensible claim is the
   weaker one: `last_update` is **not a per-line reprice timestamp**.
2. **The refutation ADR** — still waits on item 4. Its argument is provisional in
   exactly the way an n=29 null is provisional; say so in its own named section.
   The honest claim is *"Kalshi is not mispriced relative to a consensus it may
   itself lead"*, **never** *"no edge exists at Kalshi"*. And note what the
   comparison actually was: sharp anchoring discards a **median of 26 of 29**
   books, keeping `betfair_ex_eu + matchbook (± pinnacle)`. We have been testing
   Kalshi against the only references plausibly as sharp as Kalshi.

   > **ANNOTATION 2026-08-10 — `26 of 29` is a FIXTURE figure.** Measured on
   > `tests/fixtures/odds_mlb_h2h_spreads_totals.json`, captured
   > 2026-08-07T13:49:22Z, overlapping the record on **0 of 1,564 rows**
   > (minimum gap 5.65 h). The *argument* — that we tested Kalshi against
   > references as sharp as Kalshi — **stands**; only the magnitude is
   > unobserved on the record. And "anchoring discards" is itself too strong:
   > the code is `selected = sharp or usable`, so anchoring is *attempted* every
   > row and whether it **binds** is data. See §1 and §2 at the top of this file.
3. **JOE'S CALL — 24 Odds API credits** against 400/day. Two polls of the same
   games at a short interval, checking whether `last_update` advances while
   prices are byte-identical. **The repeat poll is the primary purpose**, not the
   league coverage: it converts the scrape-clock finding from inference to proof
   and generalises past one league. Secondary: WNBA + one low-liquidity league
   at ~48h and ~2h out, to reach the posting-time stratum nothing has sampled.

### 6. Deferred, with reasons, so they are not rediscovered

- **`§S13` does not reproduce registration §10, and the result document claimed
  it did.** `run_clean_shortfall.py:1106` splits its **own `__doc__`** on
  `"What this harness does NOT establish"` and echoes that — 8 bullets, against
  §10's 16. `§S` item 12 says *"§10, reproduced verbatim"*; it never was.
  Corrected in place in the result document (`§ What this measurement does not
  establish`). **The magnitude ban survives regardless** — it is in the printed
  text *and* registered pre-run in the power check, so Amendment A does not
  depend on this.

  **The fix is to delete one of the two texts, not to test that they agree** —
  `tasks/lessons.md`, *a shared object cannot disagree with itself*. The harness
  should read §10 out of the registration file at run time. Deferred because
  changing an instrument whose run is already complete, without re-running it,
  is its own hazard; and reconciling 16 bullets against 8 is real work, not a
  one-line patch.

- **The vector-collapse remedy** — probably a no-op, because the duplicate groups
  are recreational books discarded *before* the consensus exists. Lane B carries
  the predicate. Zero survivors → recorded as rejected-with-a-number, never
  revisited.
- **The 219 / `unreadable_examples` widening** — next deploy bundle.
- **`runner.py:989`** still passes `suppression.max_odds_age_ms` into the odds
  sweep. Safe *because of* the §6 assertion, not independently of it.
- **`test_has_callers.py` coverage is opt-in.** `MUST_HAVE_CALLERS` is
  hand-maintained, so absence from the list is indistinguishable from having a
  caller. That is how the count of built-never-called items reached **six**.

---

## 2026-08-10 — INFRASTRUCTURE INTERRUPT: Actions minutes, and the public flip

**This is a separate lane. It does *not* supersede the section below — the bug
found by the failed bound is still job one.** This is here because it was
found in a parallel session that has now closed, and because it has a deadline
the technical work does not.

### What happened

GitHub emailed that the account is at **90% of its 2,000 included Actions
minutes**. This repo is private, so every minute is billed, and it is ~95% of
measurable paid usage: **692 billed minutes** in three days.

The cause is not slow CI. It is **job count and trigger breadth**:

| Workflow | Actual compute | Billed |
|---|---|---|
| CI (141 runs × 3 jobs) | 303 min | **562** |
| Deploy (41) | 66 min | 91 |
| Ops (39) | **5 min** | 39 |

GitHub rounds **every job** up to a whole minute, so the Secret scan runs 8
seconds and bills 60. `ci.yml` had no `concurrency` block while push gaps ran
1.0–1.4 min against a ~2 min CI, so superseded runs billed in full.

Caveat on the number: ~725 min measured across all private repos vs ~1,800
implied by the email. Unreconciled — `gh api user/settings/billing/actions`
404s because the `gh` token lacks `user` scope. github.com/settings/billing is
authoritative. It does not change the fix.

### Done in that session

`.github/workflows/**` only — one commit, no code touched:

- `ci.yml` — added `concurrency` with `cancel-in-progress: true`
- all six jobs across all four workflows — added `timeout-minutes`

The timeout matters beyond cost: **no job anywhere had one**, so all inherited
GitHub's 6-hour default. `ops.yml` relies on `--no-tail` to terminate at all,
and its own comment says that without it the step "hangs until the job times
out" — that was 360 billable minutes, a fifth of the monthly allowance, from one
dispatch that prints nothing.

`deploy.yml` and `secrets.yml` keep `cancel-in-progress: false`. **Do not
"fix" that** — a half-finished `flyctl deploy` must queue, never be killed.

### Open — needs a keyboard

1. **Joe: set the Actions spending limit to $10.** At the default $0, Actions
   *stops* at the cap rather than slowing, taking `Deploy` and `Ops` with it —
   the only phone paths to Fly. See `tasks/PHONE.md` item 0.
2. ~~Full-history secret audit~~ **DONE 2026-08-10 — CLEAN. The repo is clear
   to go public.** No credential has ever been committed, on any ref.

   What was actually run, so nobody repeats it:

   - **gitleaks over `--log-opts="--all --full-history"`** (218 commits, 14 MB).
     Two `private-key` findings, **both verified false positives**: the bodies
     are 3 and 37 base64 characters (`.github/workflows/ci.yml` canary printf,
     `tests/test_logging_redaction.py` fixture) and neither parses as DER. A
     real RSA-2048 key is ~1,600 characters.
   - **Blob-level scan of all 1,944 objects reachable from every ref** — a
     strict superset of diff-based scanning, which is what closes gitleaks'
     218-vs-240 commit gap — against 12 credential patterns (Fly, Discord bot +
     webhook, Anthropic, OpenAI, AWS, GitHub PAT, Slack, generic assigned
     secret). **One** hit: a 32-hex value in the redaction test.
   - **That hit was verified synthetic.** Its sha256 differs from the live
     `ODDS_API_KEY`; it appears in exactly one file, ever, and only as the
     subject of `assert <value> not in cleaned`. This was the specific risk
     called out in advance — the Odds key has no greppable prefix — and it came
     back clean on a value comparison, not a guess.
   - **Every live secret** (`APP_AUTH_TOKEN`, `KALSHI_API_KEY`, `ODDS_API_KEY`)
     checked byte-for-byte against every historical blob: **absent**.
   - **`KALSHI_PRIVATE_KEY_PATH` points outside the repo tree entirely**
     (`~/.kalshi/`), so the key is structurally uncommittable.
   - **`.gitignore` carried `.env`, `.env.*`, `*.pem`, `*.key`, `*.pfx` from
     the first commit** (`330fe04`) — verified, not taken from CLAUDE.md.
   - **Entropy sweep** (>4.4 bits, len 28–80): every hit is a public Kalshi
     ticker (`KXMLB…`, `KXMVE…`) or an ESPN URL. No secrets.

   Caveat worth keeping: `ANTHROPIC_API_KEY`, `DISCORD_BOT_TOKEN` and
   `DISCORD_CHANNEL_ID` are empty in `.env`, so they could not be compared by
   value. They were covered by pattern (`sk-ant-`, bot-token and webhook
   regexes) across all blobs, which found nothing.

   **Housekeeping: done in `81a9657`.** `.tmp_shots390/` (six PNGs, 1.5 MB,
   committed by accident in `a92ac42`, never gitignored) is removed from the
   tip, and `.gitignore` now carries `.tmp_*` — the pattern, not the directory
   name, because the suffix is generated per run and pinning the name would
   leave `.tmp_shots391/` addable tomorrow. No history rewrite: the images were
   demo data. One of them showed the configured bankroll, which is a reason to
   stop shipping screenshots rather than to rewrite the past.

   **Nothing now blocks the flip.** Settings → General → Danger Zone. It is
   still irreversible, so do it at a keyboard.

---

## 2026-08-10, end of session — THE BOUND FAILED, AND IT FOUND A REAL BUG

**Read this first. It supersedes everything below, including the section
immediately following, which was written mid-session and is now partly wrong.**

`docs/measurements/2026-08-10-joint-bound-result.md` is the artefact. `main` at
the tip, pushed, **1,890 tests**, ruff clean, `next build` clean, tree clean.
Live still runs `ec53ba9`.

### 1. The joint bound could not have worked, and that is now proved

**Branch Z — the outcome that would have closed the central question — was
arithmetically unreachable before the data existed.** So `BRANCH N — NOT CLOSED`
is a consequence of the design, not an observation, and **it authorises nothing,
including the withdrawal of the plan to stop.** `measurement-skeptic`: verdict
**UNSUPPORTED as a decision-bearing reading**.

Two proofs, both measured:

- **The complementary-leg identity.** Each game has two complementary tickers,
  and at a zero fee `S_A + S_B = (ask_A + ask_B) − 1000(fair_A + fair_B)` = market
  width + devig deficit. Over 312 same-instant pairs: median +13.0, max +82.0
  tenths. So `min(S_A,S_B) ≤ 41.0 tenths = 4.10 points` at the **worst** pair,
  against Branch Z's requirement of `> 16.7 points on every row`. It misses by 4x
  at the best pair and 25x at the median, **on any two-sided record**.
- **Amendment 1 made Branch Z and the reachability precondition mutually
  exclusive.** §5 registers δ=10.00 as *"certainly non-zero if the arithmetic
  works at all"*; A1 moved Branch Z above it. `K` is monotone, so `K(16.70)=0`
  trips the precondition and no branch may be declared. **I authorised that
  amendment**, on the reasoning that rounding thresholds up is conservative —
  true against false closure, no protection against this.

**Do not re-run this instrument on the whole table.** It returns Branch N for the
same arithmetic reason. The replacements are in the result doc's last section.

### 2. THE REAL FINDING — and it could have come out the other way

    unsuppressed rows                              413   in 38 games
      ...with positive NET edge at the deployed fee  0
      largest clean GROSS edge          17.9 tenths = 1.79c
      the deployed taker fee            20.0 tenths = 2.00c
      largest clean NET edge                     −2.1 tenths

**Zero of 413 clean rows clears the fee, and the best misses by 0.21c.** And all
45 rows carrying a positive net edge are **suppressed** — zero unsuppressed, zero
actionable, 8 games. The guards and the edge computation agree about which rows
are garbage. That is a coherence result, it needed no bound, and it is better
evidence than the instrument was built to produce.

> **[SUPERSEDED 2026-08-09 — the second sentence above is NOT WRITABLE.]**
> Kept in place rather than deleted, because the deleted version of a wrong
> claim is invisible to the next reader who reaches for it.
>
> *"the best misses by 0.21c"* was **refuted by H3b** on the whole-record
> clean population: `S_min = 2.0534` tenths against `spread_at_min = 2.3191`
> tenths, so **the shortfall is smaller than that same observation's own devig
> spread**. A miss that cannot be distinguished from the width of the ruler is
> not a measured miss. See Addendum A `§AD3` in
> `docs/measurements/2026-08-10-clean-shortfall-distribution-result.md`
> (`33f1219`), ruled by Amendment A (`3a0716d`).
>
> **The first sentence stands**: zero rows clear, and that is sign-only and
> intact. What dies is every statement about *how far* — "misses by", "nearly
> clears", "clearly misses", and any multiple-of-noise figure — at any `n`.
> Registered replacement wording: *"the nearest clean observation is not
> distinguishable from clearing."*

### 3. THE BUG — and it is the top of the queue

**`edge_within_method_noise` cannot fire on the one input where the edge is
purely a devig-method artefact.** One book quoting both outcomes at identical
odds makes all four methods agree to ~1e-14, so `spread_tenths ≈ 1.4e-11` and
`edge > spread_tenths` passes for **any** positive edge. Produces a 50/50 fair on
a game the book prices **84/16**, and the three largest `|edge_tenths|` in the
slice.

**`min_book_count = 2` is the single threshold standing between a fabricated
fair and a surfaced row**, and it has **no environment plumbing anywhere** —
not `.env`, `.env.example`, `fly.live.toml` or `config.py`. `too_few_books` and
`no_market_width` fire on the *identical* condition (185 rows each, symmetric
difference 0), so they are one guard counted twice, not defence in depth.

**Eight rows were fresh, fillable, +1.2c post-fee, and stopped only by that
threshold.** ids 979/980 are the worked example.

**Not fixed, deliberately.** `suppressed_reason` is half the `actionable`
predicate, so changing when a suppression fires changes what the gate counts.
Needs an ADR and `partner`, not a patch. **This is job one next session.**

Signature to grep on live:
`SELECT COUNT(*) FROM fair_prices WHERE ABS(p_multiplicative-0.5) < 1e-12 AND ABS(p_additive-0.5) < 1e-12`

Also found in passing, unacted: **`SuppressionConfig.max_odds_age_ms = 900_000`
is hardcoded and does not read `MAX_ODDS_AGE_S`.** They agree today; changing the
env value moves the gate and the API but **not the runner's suppression.**

### 4. What is NOT established, so nobody quotes it wrong

- Every sentence above is about **the newest-1,000 slice**, not the record. The
  pull was **unpinned** and the table grew under it (1,543 vs the 1,535 of §0.1),
  so it is **not reproducible even as a slice**.
- 1,000 rows are only **748 distinct `(cluster, instant, ask, fair)` tuples** —
  the recorder writes both complementary legs and `TOR-yes ask == ATL-no ask`.
  `n_rows` is uptime.
- `D*` collapses **19x** under nested exclusion; **12 of the top 20 gross edges
  are one WNBA game**. Nothing about magnitude survives per-group inspection.
- The clearing set is **stale-selected**: odds age p50 2.00h vs 0.07h, 29x.
- **Branch M's 46 named rows all sit exactly 10.0 tenths apart** — the fee
  difference, nothing else — with max net edge 1.0c against ADR 0017's 1.50c
  adverse-selection counterargument. **Zero of the 46 survives it.**

### 4b. DEPLOYED, verified, and `unreadable_examples` paid for itself immediately

Joe deployed 2026-08-10. Verified independently, not by the workflow's own
assertions: four `/api/*` routes 401 unauthenticated, forged bearer 401, health
unchanged. All three bundle items live.

- **Paging works on the real table:** pinned pull, 2 pages, `pin = 1549`,
  **1,549 rows, 1,549 distinct ids, complete and duplicate-free.**
- **The join is correct on every row:** `p_conservative == fair_probability ==
  min(four)` on **1,549 of 1,549**.
- **Whole-table discriminating measurement:** **614 unsuppressed rows in 59
  games, 0 with a positive net edge**, largest clean net edge **−2.1 tenths**.
  614 matches `/api/gate`'s `no_edge` exactly — two code paths agreeing. And it
  is the *same* −2.1 as the slice, so the slice hid nothing at the top.
- **The degenerate-fair bug is bounded:** 21 rows, 2 games, **1.4%** of the
  record, all single-book, 0 unsuppressed, 8 fresh.

**THE LEAD ON THE 219 — and it must not be over-read.** `unreadable_examples`
returns:

    KXMLBTOTAL-26AUG071840NYMPIT-3 .. -7

**All five are `KXMLBTOTAL` — MLB *totals*, and all five are the same game**
(five thresholds of NYM@PIT). Set beside a fact measured over the whole record:

    series prefixes across all 1,549 recommendation rows:
      KXMLBGAME   1131      KXWNBAGAME   418
    any TOTAL or SPREAD market ever recommended:  False

**The recommendation engine has never written a row about a total or a spread.**
So *if* the unreadable set is dominated by totals, the 219 is **not a leak in
the evidence path at all** — those markets are polled by the result pass because
discovery finds them, and never bet. It would be 12% missing from a sample
nothing joins to.

**What is NOT established:** that the other 214 are totals. Five examples, all
from one event, and the route appears to return the first five rather than a
sample — so this is a lead, not a census. Do not write it up as an explanation.
**The cheap next step is to widen `unreadable_examples` or census by series
prefix**, which now needs no deploy for the census half if the count is exposed
per series. This is the same shape as
[[a-true-measurement-licensed-a-false-conclusion]]: the measurement is about
five tickers and the conclusion on offer is about 219.

### 5. The queue

1. **The `edge_within_method_noise` / `min_book_count` defect** — ADR + fix.
   Route through `partner`; it changes what the gate counts.
2. **Joe's deploy** (below), then the replacement measurement — shortfall against
   the **deployed** fee on the clean population, threshold from the 2.0-point
   knob ceiling, deduplicated to one observation per `(game, instant, market)`.
   Register it with §0 disclosing that this slice already returned max −2.1
   tenths on 413 rows / 38 games.
3. **The refutation ADR waits.** Branch N authorises nothing; the honest
   refutation now rests on §2 above, and it is provisional in exactly the way an
   n=29 null is provisional. Say so in its own section or it repeats the failure.

---

## 2026-08-10, mid-session — JOE: ONE COMMAND (still true; the ADR framing above supersedes)

```
! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit
```

**The bundle is built, tested, pushed and waiting.** `main` is at `a23a36f`;
live still runs `ec53ba9`. 1,790 tests, ruff clean, `next build` clean, tree
clean, no worktrees.

**What changed, and why this is no longer "queued, whenever":** the previous
plan said the joint bound could run on the newest-1,000 slice and the deploy
was confirmatory. **`pre-registrar` challenged that and won, and the
registration is committed.** The whole value of this instrument is that it is
**not provisional** — it converts *"we didn't find one"* into *"one could not
have been found here"*. A universal claim proved on 1,000 of 1,535 rows hands
that back. So the registration carries a **D-gate**: a slice run is reported in
full and labelled `PROVISIONAL`, and **no ADR, no CLAUDE.md edit and no line
closure may be written from it.**

So the ordering is now: slice run today (provisional, real, and it will tell us
the answer's shape) → your deploy → whole-table run → refutation ADR. **The ADR
waits on the command above.** Nothing else does.

### What ships in it

1. **`offset`, `max_id`, `newest_id` on `/api/ledger`** (`9b8ed19`) — and the
   pin is the load-bearing half. `offset` alone is a trap: the route sorts
   newest-first, so a row written *during* a multi-page pull lands on page 0 and
   shifts every later page. **[MEASURED] one `created_ms` on this table carries
   84 rows** — a sweep writes its whole slate at one instant. Reproduced, 120
   rows in four pages with one sweep landing mid-pull:

       unpinned          returned 120, distinct  90, 30 duplicated,
                         and 84 original rows never returned
       pinned to max_id  returned 120, distinct 120,  0 duplicated

   **The failure is silent** — every page reports `returned` 30, the pages sum
   to 120, and `total` agrees. So `offset` without `max_id` would have produced
   a "whole-table" measurement over a multiset that is not the table.

2. **The four devig readings on the ledger row** (`9b8ed19`), joined through
   `recommendations.fair_price_id`. `fair_probability` is `p_conservative`, the
   *lowest* method — a deliberate downward bias that mechanically produces
   `edge <= 0`. Without the other three, `actionable = 0` cannot be separated
   into "Kalshi is sharp" and "we chose a low fair".

3. **`unreadable_examples`** (`4473641`, already built).

**`kalshi_markets.result` is still NOT exposed**, deliberately. No reader,
calibration is dead at this `n`, and a field added for a consumer that does not
exist is how this repo got four built-never-called modules.

No migration: `SCHEMA_VERSION` unchanged and `schema.sql` untouched — the
changes are one route and one type file.

### Three inputs the registration corrected, all before any data

**Every one moved in the direction that makes the bound harder to close**,
which is the opposite of the usual failure here and worth noticing.

- **The stacked generous basis is a fee of exactly ZERO.** Measured
  exhaustively over 999 prices × 8 order sizes: Model B's maker multiplier is
  0.015, and `0.015·P(1−P) ≤ 0.00375` rounds half-up to zero cents per contract
  in **7,992 of 7,992** cases. So the primary bound reduces to *"is the loosest
  fair above the raw ask?"* and is **size-invariant** — no order size can later
  be raised as a reason the bound was too tight. Nobody believes Kalshi charges
  nothing; that is exactly what makes a zero count strong, and exactly why the
  stacked number may never be quoted as an estimate of anything.
- **The 2.03-point devig spread is an example wearing the label of a bound.**
  It traces and reproduces to four figures — but `TestMethodSpreadDependsOnLine
  Shape` asserts three *inequalities*, never the values, so `tasks/lessons.md`'s
  claim that "both halves are asserted" is **wrong**. And the spread is
  **non-monotone** in lopsidedness (1.02/40.0 gives 0.425 — additive clamps), so
  **no fixed δ is a bound at all.** The artefact is therefore the **shortfall
  distribution**, from which `K(δ)` is readable at every δ at once. The δ knob
  does not exist for the analyst.
- **"1.94 points, 5.1x" for the maker basis is the `N=100` limit.** ADR 0017
  Correction 1 already fixed 10 contracts as this software's minimum order, so
  **1.88 points and 4.9x** is operative. The band is `[173, 827]` tenths
  exactly; "18c–82c" rounds inward and mislabels 14 prices.

### The one number to read when it lands

Not the count. **The shortfall.** *"0 rows clear, and the nearest row is X.XXc
short of a fee-free ask at the loosest devig reading available"* is the whole
finding; a bare zero is not citable and the registration says so.

---

## 2026-08-10 — THE PLAN: one joint bound, then stop and write the refutation

`partner` re-triaged after `pre-registrar` refuted two of its three load-bearing
claims. It took both, and the resulting plan is smaller and stronger than
anything proposed this session. **This section supersedes the ordering below
it.**

### Collapse both lanes into one instrument

Lane A's fee-model flip and the devig B2 check are **the same instrument pointed
at different knobs**: *take our most conservative choice, set it to the most
generous alternative, recount.* Run separately they produce two documents a
reader has to combine. Run together they produce the number that settles it:

> **With every conservative choice this project makes set simultaneously to its
> most generous alternative — the loosest of four devig methods, the cheaper fee
> model, and the maker basis — how many rows are actionable?**

One pull, one module, one registration. **If it returns 0, per-knob attribution
is a footnote and the central question is closed.** Decompose per knob *only*
conditional on a non-zero count.

Two reasons this is the right instrument and not fishing:

- **It is a bound, not an estimate.** Same move that permanently closed the
  half-spread question with `sd <= 2.5`, where a point estimate would only have
  nudged it.
- **It is deterministic, so it carries no alpha at all** — it does not enter the
  multiplicity count. Against P(at least one cell clears from nothing) = 0.9993,
  that matters enormously.

### Why this is the whole ballgame — the argument to keep

**A null at n=29 games is provisional.** A future session will reasonably ask
whether more data or a different devig would have changed it.

**The joint bound is not provisional.** It is a deterministic statement about
prices already recorded: if the ask sits above the most generous fair under the
cheapest fee on every row, then **no method choice, no fee resolution, and no
additional sample of the same kind could have produced an actionable row.** It
converts *"we didn't find one"* into *"one could not have been found here"* —
and **no amount of future data can reverse it.**

By CLAUDE.md's own standard — the product is the record — that is a *delivered
result*, and a better portfolio artefact than a cockpit asserting an unverified
edge.

### Then stop

If the bound returns 0: write the refutation ADR, correct CLAUDE.md's premise
section from *"this tool exists to find out whether an edge is there"* to what
it found, and close every accumulation-justified line. **Leave the recorder
running because it costs nothing, but with no work planned against it and no
promise attached.**

**Accumulating more rows is worthless and always was.** 1,529 rows is 29 games;
ADR 0016 caps a 1,200-game backfill at 35 actionable against a floor of 300. Any
plan whose mechanism is "keep it running" is not a plan, and the fall slate does
not rescue it.

### The one line where a positive finding is not power-precluded

**The maker basis.** Verified this session: at 50c the maker fee is exactly half
the taker fee ($0.0100 vs $0.0200), and the headroom is **1.94 points against
0.38 — 5.1x.** It is the only quantity in this project where a positive result
is not excluded on its face, it is R3 inside the registration, and **it rides
free inside the same joint bound at zero extra cost.**

If it shows no mass in the 18c–82c band, the line closes with everything else.
If it does show mass, ADR 0017's counterargument still stands and it authorises
exactly two things: **a cancel path and the free markout harness. Not a
strategy.**

### The bundle shrinks — the calibration route is OUT

Its justification died with the power calculation, and a route must not be kept
alive on a rationale invented after the old one failed.

1. **`offset` on `/api/ledger`**
2. **The four per-method probabilities on the ledger payload**, joined through
   `recommendations.fair_price_id` — raw data out, recount in a tested local
   module, because batched deploys make baked-in analysis cost a release to
   re-cut
3. **`unreadable_examples`** (built, `4473641`)

**Do NOT expose `kalshi_markets.result`.** There is no reader, calibration is
dead at this `n`, and a field added for a consumer that does not exist is how
this repo got four built-never-called modules. **The data accrues; the analysis
waits for `n`.** The 1,601 outcomes keep accruing free at ~15 games/day, and a
5-point gross miss needs ~400 games — reachable in months, not this quarter.
Written down so nobody rediscovers the idea and rebuilds the harness.

Build order is `offset` → widen the payload → one joint module. Reporting order
is the joint bound first.

### Cut the descriptive surface structurally, not by count

0.9993 does not mean "be careful with descriptives". It means **at least one
striking cell is guaranteed to exist from nothing**, and this repo already
records that a "not the test" label falls off in three weeks while the digits
stay.

They cannot simply be deleted — the measurement rules *mandate* per-group views.
So cut by kind:

- **Keep** cells that are decompositions of a registered quantity, plus the
  largest contributor's share. That is the mandated consistency check.
- **Delete** every free-floating cell that is not a decomposition of something
  registered.
- **Strip intervals, standard errors and significance marks from all
  descriptives.** Count and share only.

The last is the structural part: **a cell with no interval attached cannot
"clear 2 SE" — it leaves the multiplicity count by construction rather than by a
label that erodes.** Expect 156 to land near 20–30; `pre-registrar` sets the
exact number.

**Then recompute Bonferroni.** If the joint bound is primary and carries no
alpha, the alpha-carrying count may fall below 3, which loosens the correction
on whatever remains. Do not inherit 0.0167.

### The decision that is Joe's, and when to make it

If the joint bound returns 0, **continuing is not a smaller version of this
project — it is a different one**: liquidity provision, or Kalshi as the sharp
reference against another venue. That deserves a fresh decision made with a
clean record in hand, not a drift out of an ambiguous one.

**Make that call after the refutation is written, not now.** Cost to get there:
the three-item bundle, one deterministic module, one skeptic pass. Days, not
weeks, and no money.

---

## 2026-08-10 — the edge test is REGISTERED, and it retracts a claim of mine

`docs/measurements/2026-08-10-preregistration-fresh-odds-edge-distribution.md`.

**It must be committed before Stage B runs.** That single act is what makes it a
pre-registration rather than a note, and the agent deliberately left it
uncommitted rather than assume.

Verdict as registered: **READY** for branches A and C, **READY at `G >= 100`**
for branch B, **BLOCKED on P1** (full-table access, i.e. the `offset` deploy) for
all three — which independently confirms `partner`'s promotion of `offset` to a
prerequisite — and **permanently UNDERPOWERED at the 3.8-tenth headroom scale**:
349 games needed at sigma=20, against **29 scored games in the record's entire
life.** No claim at that scale may be made from this measurement at any `G` it
will plausibly reach. Write that down before quoting any number from it.

### RETRACTION — `no_edge` is honestly named after all

Two entries below, I speculated that `no_edge` might conflate *"the edge was
non-positive"* with *"the edge was positive but too small to round up to one
contract"*, and that `actionable = 0` might therefore be partly a sizing
artifact. **That is refuted, deductively, and it was refuted before any data was
cut — which is exactly what the pre-registration is for.**

`sizing.py` prices every decision at one contract. Measured directly against
`RiskConfig.load().reference()` (bankroll $1,000, quarter-Kelly), the smallest
post-fee edge that still sizes to at least one contract is:

    ask   20.0c   0.7 tenths        ask   60.0c   1.0 tenths
    ask   30.0c   0.9 tenths        ask   70.0c   0.9 tenths
    ask   40.0c   1.0 tenths        ask   80.0c   0.6 tenths
    ask   50.0c   1.0 tenths

So the sizing floor is about **one tenth of one cent** — nil. Therefore
`actionable ⟺ (no suppression code) AND (n=1 post-fee edge > 0)`, and since
`actionable` has been 0 across 1,529 rows, **every unsuppressed row already has
a non-positive edge.** There is no hidden population of small positive edges
being rounded away. The question "does any unsuppressed fresh row clear the bar"
is already answered, and the registration does not ask it.

My speculation was the flattering direction, and it was wrong. Leaving it
standing would have sent someone to go looking for a population that provably
does not exist.

### The fee-model question is smaller than this file has been claiming

**Measured exhaustively over all 999 prices** (`fee_candidates`, in dollars, at
n=1):

    the two models differ by exactly $0.01/contract, or by nothing
    they AGREE exactly at 163 of 999 prices:
        9.2c - 17.2c        50.0c only        82.8c - 90.8c

**At exactly 50.0c the fee models agree, so resolving them cannot move that row
at all** — and 50c is the middle of the band this strategy trades. The
difference is quantised to a whole cent; it is not the smooth "0.38 points" this
file has repeatedly implied.

That gives a pre-computable **unreachable domain**, and it discharges the
standing rule that *a control must be able to reach the confound it was built
for*: a flip count of zero over an empty domain is registered as UNRESOLVED, not
as a refutation. Branch A therefore prints `R > 0` (fresh rows in the reachable
domain) as a precondition **before** any rate.

**This does not kill Lane C** — outside those 163 prices a whole cent per
contract is large against the headroom — but it does mean the $5 buys less than
"resolves the bar for every row", and nobody should say that again.

### Three more design points worth not re-deriving

- **The freshness predicate is `instr`, not `LIKE`.**
  `instr(',' || suppressed_reason || ',', ',stale_odds,') = 0` — because `_` is a
  `LIKE` wildcard and **all fourteen suppression codes contain underscores.**
  This is Amendment 1's D1 defect one step further on.
- **The edge is recomputed, never read.** `edge_after_fees_tenths(ask,
  contracts=1, fair)` per row; the stored column is selected only as
  `stored_edge_tenths_DO_NOT_USE` for a divergence diagnostic. Add-back is
  forbidden by the registration.
- **Multiplicity is counted: 37 descriptive cells, ~82% chance one clears from
  nothing, and exactly one interval test carries alpha.** League is substituted
  by raw ticker series prefix, with the reason recorded — `kalshi_series.league`
  is written on first insert only and is unreliable for NFL.

Exactly **one** assumed input in the whole design (sigma), and it appears only as
a column of the power table and gates no threshold.

---

## 2026-08-10 — `partner` re-triaged: calibration is the CONTROL for the edge test

The queue changed for a reason nobody had stated. **Read this before picking up
anything below it.**

### Why D2 (calibration) is now top, and it is not close

If `model_probability` is NULL and nothing reads it, then `fair_probability` —
the worst-of-four devigged consensus — **is the entire model**. So
`actionable = 0` reduces to a single claim: *Kalshi's ask is at or above our
worst-of-four fair, essentially always.* Two explanations fit that equally well:

- **(a)** Kalshi is sharp and correctly priced. Premise refuted; the answer is no.
- **(b)** Our fair is systematically too low **because we chose to make it so.**

CLAUDE.md rule 2 takes the **minimum** across four devig methods on the side
being bought. That is a deliberate downward bias on fair value, and a downward
bias mechanically produces `edge <= 0`. `schema.sql:295` is blunter than the
rule is — *"Three layers of conservatism (worst method, derived ask, fee-net) is
deliberate."*

Now set that beside the arithmetic already in `tasks/lessons.md`: **the
devig-method spread runs 1–2 percentage points, and the taker headroom is 0.38
points.** If the conservatism costs anywhere near its own spread, the
worst-of-four rule is eating **three to five times the entire edge being
hunted** — and `actionable = 0` is partly a restatement of our own policy rather
than a fact about the venue.

**(b) is not a reprieve and it is not a bug.** It is a policy consequence that
has never been priced.

### What makes it answerable today

`fair_prices` stores **all five** — `p_multiplicative`, `p_additive`, `p_power`,
`p_shin`, `p_conservative` (`schema.sql:290-297`) — and
`recommendations.fair_price_id` FKs straight to it. With 1,601 outcomes now
recorded, **D2's scope expands from one calibration curve to five**: each method
against realised outcomes.

That puts a measured number on what rule 2 costs. **Lane A measures where the
edge distribution sits; D2 measures whether the ruler is straight.** Running A
without D2 reports a distribution in units nobody has validated.

### Three guardrails, because this is the flattering direction

1. **Pre-register before looking**, jointly with the Lane A registration, so the
   five curves and the bucket edges are fixed together and this cannot become
   five chances to find one.
2. **Count the tests.** Five methods x price buckets is exactly the 1,190-cell
   shape that produced "dozens of significant results" in the predecessor.
   `mart_multiple_comparisons` logic must travel with it — and note
   `audit-2026-08-07.md` item 7 says that counter already undercounts.
3. **This is NOT licence to weaken rule 2.** The rule stands until a measurement
   retires it. *"Measure what the guard costs against outcomes"* and *"relax the
   guard because it fires too often"* are different acts, and the difference is
   on the record here so that nobody quoting a number from this can blur them.

### Lane B: `offset` is promoted to a prerequisite

Not a convenience. `/api/ledger` returns the newest 1,000 of 1,529 and the
record grows ~500-600 rows/day (measured: +67 in ~3h), so by the time the bundle
ships it is closer to half the table.

**And the bias is not benign.** `engine.persist_if_changed` writes a new row only
when the ask or the fair *moved*, so rows-per-game tracks **price volatility** —
and a slice weighted toward high-row-count games is weighted toward volatile,
uncertain, wide-disagreement games. That is the direction that **inflates an
apparent edge.** Running the decisive measurement on that slice is not
acceptable.

`partner` reversed its own preference here, and the reason generalises: it
wanted a server-side aggregate route returning the histogram directly, but
**batched deploys kill that** — baking bucket edges into a release means waiting
for the next bundle every time `measurement-skeptic` wants a different cut. Raw
rows pulled once, analysed in a tested local module, re-cut freely, is strictly
better under slow deploys.

### The bundle, final — four items, nothing else

1. **`offset` on `/api/ledger`** — smallest, and Lane A's credibility depends on it.
2. **The calibration route**, all five methods. Needs a server-side join
   (`kalshi_markets.result` x `fair_prices.p_*`) the ledger payload cannot
   supply, so a route is right here even though a local module is right for A.
3. **`unreadable_examples`** — already built (`4473641`).
4. Nothing else.

**One addition considered and REJECTED, because the reason generalises.**
Persisting `binding_constraint` would turn R2 into a `GROUP BY` instead of a
reconstruction. The only cheap way is widening the f-string at `engine.py:219`
to append `sizing:{...}` — but that writes into **`suppressed_reason`, which is
half the `actionable` predicate.** That would *change what the gate counts in
order to make a measurement easier.* Refused. It is reconstructable from
`edge_tenths` (`NOT NULL` on every row), so refusing costs nothing.

### Kills, and no resurrections

- **`publish.py` as a boot-time step — killed.** With programmatic read access a
  **pull-based archiver** is simpler, needs no deploy, is testable locally, and
  adds nothing that runs at boot on live. A pull script that fails is a laptop
  job that never touched production; the standing question *"what clears it if
  it fails?"* answers itself.
- **The maker histogram as a standalone item — killed.** It is R3 inside Lane
  A's registration. Double-tracking it means running it twice with different
  bucket edges, and the more interesting answer is the one that gets quoted.
- **The 219 — explicitly deferred, not investigated.** Reason recorded so it does
  not resurface: `abandoned_total: 0` makes it 12% missing from a *future*
  sample, not a leak. Revisit only if calibration comes back power-limited.
- **No resurrections.** The backfill is *further* dead: the live question moved
  from "collect more decisions" to "is our devig biased", which is answerable on
  data already on disk, while Phase 0 harvests Kalshi **bars, not outcomes.**

### On `elo.py` — do not wire it up to make the documentation true

It is written, tested, and has no caller — the fifth in that pattern. *"It is
already built, we may as well"* is how a sunk cost becomes a strategy, and
wiring it would be engineering around the finding in the exact way the standing
instruction forbids: **it changes what is measured so the zero stops being a
zero.**

One conditional under which it earns a look, and it is downstream of both
measurements: if calibration shows the consensus fair is *well* calibrated **and**
Lane A shows the edge distribution centred just below zero, a second independent
signal could plausibly add information rather than paper over an absence. That
is a decision for after both, not before either.

---

## 2026-08-10 — the power-ratings finding is AUDITED, and `no_edge` may be misnamed

`runtime-realist` confirmed the claim, corrected one overstatement of mine, and
produced an argument stronger than the one I had. **CLAUDE.md is corrected.**

### The correction to my own claim

I wrote that `model_probability` is "read by nothing". Too strong.
`/api/ledger`'s `SELECT *` fetches it and `_serialise` (`routes.py:1820`) drops
it key by key; `warehouse/models/staging/stg_recommendations.sql:60` selects it
and no mart references it. Accurate phrasing: **written to the database, carried
into one staging view, and consumed by no decision anywhere.**

Also found, and neither was in my version: `elo.py` **is shipped into the
container** (`.dockerignore` excludes `tests/` and `scripts/*` but not
`backend/`), so it is deployed and never imported. And `tests/test_has_callers.py`
never caught the orphan because `EloModel`/`backtest` are simply **not in its
`MUST_HAVE_CALLERS` list** (lines 77-159) — the detector's coverage is opt-in, so
absence from the list is indistinguishable from having a caller. Adding them
would turn CI red, correctly; **that is a kill-or-keep decision for `partner`,
not a test fix.**

`seed_demo.py:268` also omits `model_probability`, so demo and live are
identical on this point. The specific way the claim could have been half-true is
closed.

### THE ARGUMENT THAT SETTLES IT — a conjunction cannot rescue an empty set

As documented, the second signal was a **conjunction**: "surfaces opportunities
where *both agree*." A conjunction only ever removes rows from the surfaced set.
**Adding an AND-gate to a set that is already empty leaves it empty.** So the
missing half cannot explain `actionable = 0` away — not as a matter of judgement
about informational efficiency, but arithmetically.

A *different* design — blending a model probability into `fair_probability` to
move the edge — could shift rows either way. That is a new decision needing its
own ADR, not the completion of an existing one. **Do not let it be smuggled in
as "finishing what was started".**

### THE OPEN QUESTION THIS RAISED, and it may be the real one

`actionable` splits on `reference_contracts > 0`, so **sizing is at least as
likely a cause of the zero as edge is.** Look at the two predicates together
(`gate.py:323-324`):

    actionable   suppressed_reason IS NULL AND reference_contracts > 0
    no_edge      suppressed_reason IS NULL AND (reference_contracts IS NULL
                                                OR reference_contracts <= 0)

So the 614 `no_edge` rows are rows that **passed every suppression rule** —
staleness, book count, market width, method noise — and were then sized to zero
contracts at the $1,000 reference bankroll.

`no_edge` is therefore a name for two different things that nobody has
separated: *"the edge was negative or zero"* and *"the edge was positive but too
small to round up to one contract"*. Rough arithmetic (**computed from code, not
measured**): at $1,000, quarter-Kelly, 50c, a Kelly fraction around 0.002 sizes
to ~1 contract, so anything below roughly that rounds to zero and is filed as
`no_edge`.

**If a meaningful share of those 614 rows carry a small positive edge, then
`actionable = 0` is partly a sizing artifact and partly a finding, and the
current reporting cannot tell you which.** That is precisely what the fresh-odds
edge-distribution pre-registration is built to answer, which raises its value —
it is no longer only "is there an edge", it is "is the counter measuring what
its name says".

**Do not act on this before the pre-registration is written.** The temptation is
to go and look at the 614 immediately; the record has already been partly seen,
and an unregistered cut here is exactly the fishing expedition the registration
exists to prevent.

---

## 2026-08-10 — DEPLOYED, D1 is answered, and deploys are now BATCHED

`ec53ba9` deployed to live ~01:55Z and verified independently, not by the
workflow's own assertions. No migration: `SCHEMA_VERSION` 6 on both commits and
`schema.sql`/`db.py` **byte-identical** to the previously deployed commit.

    unauthenticated   /api/results /api/gate /api/ledger /api/orders all 401
                      forged bearer 401; /gate /ledger /board all 307 -> /login
    health            instance_mode=live, live_trading_enabled=false,
                      execution_available=false, retired_settings_set=[]
    gate wording      the ADR 0018 correction shipped (detail cites docs/adr/0018)

### D1 IS ANSWERED: the outcome pass works, and nothing has been lost

    verdict            "recording"
    recorded_total     1601   (no 1039, yes 562)
    pending_total      0
    abandoned_total    0      <- nothing has aged out
    too_new_total      1300   <- today's slate, not yet 2h past commence
    unreadable_total   219

**`abandoned_total: 0` is the number that retires the deadline.** The rolling
7-day loss was real as a mechanism and has never bitten: no outcome has been
dropped. The calibration consumer (NEXT item 3) now has 1,601 real inputs.

### The 219, and the hypothesis that died

12% of everything resolved is `finalized` with no readable outcome. Diagnosed as
far as it can go without a deploy — **record this so the next session does not
repeat the same guesses:**

- **Measured:** 802 settled game markets pulled from Kalshi across five series
  parse **100% READABLE**. The parser is not broken and the wire format has not
  moved.
- **Measured:** 800 settled markets bucketed by age — `<1h`, `1-3h`, `3-12h`,
  `12-48h`, `>48h` — carry **zero** unreadable results. The freshest was 0.48h
  past close with `settlement_timer_seconds=60` and a populated `result`.
- **Measured:** `determined` and `finalized` are both rejected as status filters
  (HTTP 400). Only `settled` is queryable. This confirms the note already in
  `market_results.py`.
- **REFUTED — do not re-propose it:** that Kalshi reaches `finalized` *before*
  publishing `result`, letting the pass refuse a market that is merely
  mid-settlement and stamp it permanently unreadable. The age buckets say no.
  It is a good hypothesis and it is wrong.

Read the above as a **bound, not a refutation**: a snapshot of markets Kalshi
already calls settled cannot observe the transition itself.

So the 219 are unexplained. `unreadable_examples` (five named tickers) is built
and committed to close that — a count cannot be investigated, a ticker can — but
it **needs a deploy** to be readable.

**It is not urgent, and `abandoned_total: 0` is why.** Nothing is leaking. This
is 12% missing from a future calibration sample, to be fixed once, not a loss in
progress. An earlier version of this file implied otherwise; that was
"unexplained" being read as "urgent".

### DECISION: deploys are batched from here

Joe's call, 2026-08-10, and it is the right one — deploy-per-change was costing
him a wait-and-verify cycle for each small additive route.

What changed the economics is the live read access: **most remaining work needs
no deploy at all.** The split, so it does not have to be re-derived:

| Needs no deploy | Needs a deploy (queued) |
|---|---|
| `runtime-realist` audit, then the CLAUDE.md correction | `unreadable_examples` (built, `4473641`) |
| The fresh-odds pre-registration | Ledger `offset` (not started) |
| Analysis over the newest 1,000 ledger rows | The calibration consumer (not started) |

**One live caveat while `offset` waits:** `/api/ledger` returns the newest 1,000
of 1,529 rows, which over-represents games that generated many rows. Every rate
computed off it describes a **biased slice**, and any number produced before
that deploy must say so rather than imply it covers the table.

---

## 2026-08-10, earlier — LIVE READ ACCESS IS UNBLOCKED

Joe put the live `APP_AUTH_TOKEN` on **line 68 of `.env`** (repo root,
gitignored). Verified working: form-POST `token` to `/session` returns 303 with
a `Set-Cookie`, and the cookie opens `/api/gate` and `/api/ledger` at 200. **An
agent can now read the live evidence record programmatically.** Every
measurement below is a raw read of a live counter, taken 2026-08-10 ~01:37Z.

    populations.counts   actionable 0    no_edge 614    suppressed 906
    ledger               total 1520      horizons: "0" 532, "1" 569, unscored 419
    gate, per population actionable 0g/0r   no_edge 20g/279r   suppressed 25g/253r
                         "none of the 29 scored game(s) is actionable"
    window               closed; spent_today 54 of 400; next sweep 23:07Z MLB, 8 games
    fee_model_verified   "no fills yet" — matches the local probe

**An internal consistency check that holds:** 279 + 253 = 532, exactly the
horizon-`"0"` row count. So the gate counts only the current primary horizon and
the 569 legacy 1.0h rows are correctly excluded, as ADR 0011 specifies. And
20g + 25g = 45 against 29 distinct games, so 16 games carry both no_edge and
suppressed rows — the populations overlap at the game level and must not be
added.

**The one number worth reading twice: 29 scored games, against a floor of 300,
and 0 actionable.**

### Unaudited delta — do not quote this until it is checked

Against the previous session's read (1,462 rows; horizon `"0"` 476):
**+58 rows, and horizon `"0"` went 476 → 532 (+56)** while `"1"` stayed frozen
at 569 exactly as predicted. That reads as *scoring at the current horizon is
accumulating*, which would be the mechanism working.

It has **not** been through `measurement-skeptic` and the 476 baseline is taken
from the prior handoff rather than independently re-derived. Two obvious ways it
could mislead: the two reads are hours apart with no control for slate size, and
a row count is a measure of uptime rather than of evidence
([[one-observation-recorded-thirty-times]]). **`actionable` is still 0 after 58
more rows**, and that part needs no audit.

### Two things this read settles

1. **The `gate.py` wording fix is committed but NOT deployed.** Live still
   serves the old `config_enabled` text — "arming is a deliberate human act,
   kept separate from the evidence conditions" — without the ADR 0018
   correction. It ships on the next deploy, which is Joe's.
2. **D1 is still not readable over HTTP, and now provably so.** No route exposes
   `kalshi_markets.result`; the eleven `/api/*` GETs are health, stream/quotes,
   board, window, market/{ticker}, ledger, suppression, gate, playbook,
   dashboards, builder/wong-screen. **Verifying the result backfill needs a new
   route and therefore a deploy** — it is not reachable with the token alone.
   Given the rolling 7-day loss described below, that route is now the cheapest
   high-value change available.

---

## 2026-08-10 — half the documented strategy has never run, and the $5 buys a field name

Session ended early: **four parallel lanes were killed mid-flight by an API
session limit**, not by any code fault. What landed is below and is complete and
green. What did not land is listed with what it had already done, so it can be
resumed rather than restarted.

`main` was at `b6ce9c9` on entry, verified independently: tree clean, no
worktrees, `main == origin/main`, **1,753 tests passing**. One handoff
correction: `origin/lane/frontend-wip` still exists remotely but is fully merged
(0 commits ahead), so it is stale-but-harmless rather than a lost branch.

### THE FINDING — the second signal has never existed

`CLAUDE.md`'s opening paragraph describes the product as comparing Kalshi
against devigged consensus **and an in-house power-ratings model**, surfacing
opportunities where **both agree**. In the deployed system there is no second
signal and no agreement requirement.

**Verified from code, four ways:**

- `backend/runner.py:685` builds the production `Candidate` and never passes
  `model_probability`, so it takes its dataclass default of `None`. Every live
  row has it NULL.
- `model_probability` appears in `backend/engine.py` at five sites only: two
  dataclass declarations, one pass-through (`:231`), and the INSERT column list
  and value tuple (`:368`, `:375`). **Written to the database, read by nothing.**
- It is referenced nowhere in `backend/core/`, `backend/gate.py` or
  `backend/api/` — so no suppression rule, sizing calculation, EV computation,
  gate condition or API response consumes it.
- `backend/model/elo.py` — the power-ratings model itself — is imported only by
  `backend/model/backtest.py` and `tests/test_model.py`, and `backtest.py` is in
  turn imported only by that same test. **No production caller.**

One near-miss worth keeping, because it is how this claim could have been
overstated: `backend/model/margins.py` *does* have a production path
(`core/teaser.py` → `routes.py:62 find_wong_candidates`). That is the teaser
feature, not the power-ratings signal in the recommendation engine. The
distinction is real and the claim is scoped to `elo.py` and
`model_probability`.

**How to read this, and how not to.** `actionable = 0` over 1,462 rows describes
a **consensus-only** strategy, not the two-signal one on record. That is *not*
evidence the missing half would help — CLAUDE.md's own premise is that Kalshi is
informationally efficient, and there is no reason to expect a power-ratings
model to beat a devigged sharp consensus on major-league sides. **Do not treat
this as a reprieve.** What it changes is the *description*: the record cannot
honestly be written up as "the strategy found no edge" when half of it has never
run. It is "consensus alone found no edge, at n=1,462, over horizon-mixed rows."

**CLAUDE.md is deliberately NOT edited yet.** The independent `runtime-realist`
audit of this claim was one of the four lanes killed by the limit, and the
standing rule is that things get audited before entering the record — the spine
document most of all. **First job next session: re-run that audit, then correct
CLAUDE.md's opening paragraph.** The evidence above is mechanical and I believe
it holds; it has simply not been checked by a second pair of eyes.

### The fills probe — the $5 is load-bearing for more than the fee value

Probed Joe's **production** account (`api.elections.kalshi.com`, confirmed not
demo): **zero fills, ever.** So there is no free path to the fee model, and no
historical fills from the predecessor project to mine.

> **[BOTH SENTENCES ARE FALSE — corrected 2026-08-10. Kept in place because the
> deleted version of a wrong claim is invisible to whoever reaches for it next.]**
>
> **"Zero fills, ever" was true of `/portfolio/fills` and false of the account.**
> `GET /portfolio/settlements` returns **55 settled positions** dated 2025-11-27
> → 2026-05-10, every one carrying `fee_cost`. The account had traded; the fills
> endpoint had simply **aged them out** — a retention window with an upper bound
> near three months, confirmed across eight query shapes.
>
> **So "there is no free path to the fee model" was wrong, and it cost real
> money to find out.** Eleven single-game settlements pin the coefficient to
> `(0.069771, 0.070129]` and fit `ceil-to-CENT × 0.07` **11 of 11** — at zero
> cost, on data already on the account, before any trade was placed.
>
> **The pattern, and it is the reusable part:** *an empty endpoint is not an
> empty account.* One endpoint returning nothing was read as a fact about the
> world rather than about that endpoint's retention policy, and no second
> endpoint was tried. Ask what else would carry the same quantity before
> concluding the quantity does not exist. See the top section of this file, and
> `docs/measurements/2026-08-10-fee-model-fill-calibration-result.md`.

Separate what that settled from what it did not:

- **Measured:** the envelope is `{"cursor": str, "fills": list}`. So
  `payload.get("fills")` reads the right key, and the four-wrong-wire-keys
  failure is not present at the envelope level.
- **Not measured, and unmeasurable without a fill:** every field *inside* a
  record — including whether the fee is called `fee`, its units, and whether it
  is per-contract or per-order.

`backend/kalshi/rest.py:fills()` documented `fee` as **ground truth**. That name
was inherited from the predecessor and had never been observed here. Docstring
corrected to say what is measured and what is not.

**So the four trades buy the fee *value* and the fee *field name* at once.**
Spend the money without capturing verbatim first and the answer may be
unreadable, in the well-formed-empty way this repo has been burned by four
times. `scripts/capture_fills_fixture.py` is written, run, and currently exits
3 with an honest "zero fills, nothing to capture". **Run it immediately after
the trades fill, before writing any parser.**

Not time-critical, and that is stated rather than assumed: `/portfolio/fills` is
historical, so the laptop step can wait for the next laptop session. Kalshi's
fill retention window is **unknown to this project** — assumed, not measured —
so do not stretch it indefinitely.

Also corrected: `tests/test_execution.py`'s fee test claimed the calibration
trades "do not also need a `/portfolio/fills` poll" because the fee arrives in
the order response. **Wrong for the trades actually planned** — see ADR 0018;
our order path cannot place a real order, so the trades go through the Kalshi
app and produce no order response here. `/portfolio/fills` is the only channel.

### ADR 0018 — arming real trading is a code change, not a config act

`backend/store/orders.py:129` is `ORDERS_ARE_DRY_RUNS = True`, a **module
constant with no environment read**. `routes.py:1382` is the only production
`OrderPlacer` construction and takes it; `place` short-circuits to
`STATUS_DRY_RUN` before any POST. The only `dry_run=False` constructions in the
repo are in tests.

**`LIVE_TRADING_ENABLED` satisfies one gate condition and moves no money.**
`gate.py`'s wording did not say that was false — it said nothing about what the
flag is *sufficient* for, and a reader supplies the wrong answer. Both branches
of the condition detail now say so, and the ADR enumerates all four things that
would have to move, in order (including a second barrier nobody had recorded:
`routes.py` passes no REST client, so flipping the constant alone raises at
construction rather than placing an order).

Enforced by `TestArmingRealTradingIsACodeChange`. **The disable-check was run by
hand this session and all four deformations confirmed**, including the two that
matter most: a *harmless* `dry_run=True` literal at the call site is still
refused (the defect is divergence between two sites, not the value at either),
and pointing the AST walker at a name that does not exist turns it red on
`found >= 2` rather than passing vacuously.

### `fly.live.toml` was wrong on both halves, and one has a bill attached

It said the agent fleet and the notifier "are not wired into the runner, so
nothing reads them yet." Both false, verified: `run_loop.py:278` reads
`DiscordConfig.from_env()` on every boot, and `runner.py:489` defaults
`review=review_surfaced` with both production callers going through it.

**The trap, and it is specific to live.** There are two independent reasons the
Anthropic bill is zero — an empty candidate list (`review.py:194`, checked
*before* the environment) and a missing key (`:197`). Locally, reason 2 does the
work. **On live it does not**: live reports `agent_fleet_configured: true`, so
the key is set, and the only thing standing between the deployment and a live
bill is `surfaced == 0`.

So the spend is gated by a **measurement outcome**, not by config — it switches
itself on precisely when the project starts working. One call per surfaced row
per pass, ~96 passes a day. **Set a spend limit on the Anthropic account.**

### The D1 deadline, derived rather than repeated

`MARKET_RESULT_MAX_AGE_S` is **unset on live**, so the 7-day code default
applies (`config.py:410`). The result pass drops any market more than 7 days
past commencement.

That makes it a **rolling loss, not a cliff**: if the pass is silently broken,
one day of outcomes is lost per day, permanently, and it cannot be detected from
outside. That is what makes the read-access decision below the gating item
rather than a convenience.

### DECISION WAITING ON JOE — it blocks two queue items

An agent cannot read the live evidence record. The `APP_AUTH_TOKEN` in the local
`.env` is **not** the live token (verified: live `/session` 303s it to
`/login?error=1`).

**Recommended: type the live `APP_AUTH_TOKEN` into the local `.env` yourself.**
Never paste it into a chat window. `.env` is gitignored and the existing loader
picks it up; every future measurement becomes programmatic.

Blast radius: an agent holding it can read every route and create dry-run order
rows. It **cannot** move money — ADR 0018 is exactly why, and the gate is closed
on three independent evidence conditions besides. The alternative (a Bash
permission rule for `flyctl ssh console`) is strictly more powerful, grants raw
DB access, and reintroduces the laptop dependency we are trying to remove.

Until then the live pull is a phone tap: **`GET /api/gate` is the single
highest-yield request** — four gate conditions plus `populations.counts` over
the whole table.

### The four lanes that were killed, and where each got to

Resume rather than restart. None left the tree dirty except the first.

1. **ADR 0018 + doc defects — LANDED.** It died before writing the ADR, having
   already made good, correctly-cited edits to `gate.py` and `fly.live.toml`.
   Those were verified line by line and kept; the ADR was written by hand and
   one overstated claim was tightened (the Anthropic sentence above — the
   absence of a key *also* keeps the bill at zero, so the claim is true of live
   specifically, not universally).
2. **Pre-registration for the fresh-odds edge distribution — NOT STARTED.**
   Wrote nothing. This is NEXT.md item 2 and still needs `pre-registrar`. The
   record has now been seen, so an unregistered cut is a fishing expedition.
3. **`publish` + ledger `offset` — NOT STARTED.** Its worktree was pruned. The
   premise to re-verify first: `publish()` reportedly writes to a
   container-local relative path with no route serving it, so the evidence
   record has never left the volume, and `/api/ledger` has no way to page past
   the newest 1,000 of 1,462 rows.
4. **`runtime-realist` audit of the power-ratings finding — NOT STARTED.** See
   the top section. This is the first job next session.

### `partner`'s kill list, recorded so it is not re-litigated

In-play (3.5–6x underwater on measured cost vs headroom); ADR 0016 Phases 1 and
2 (9,600 credits for precision on a question already answered twice); Phase 0
downgraded to no-go (the 80-day window rolls forward with no cliff, and it needs
a `provenance` column that was never shipped, i.e. a schema v7 migration on the
live volume); combo/KXMVE (hit its own stopping rule); Scout and Historian (no
production caller — `playbook.py:18` says so in its own source); the dbt
warehouse and Dashboards screen (`warehouse/` is not in the Dockerfile and
`/api/dashboards` is a 503 on live — build analysis as Python modules behind
routes, the way `/api/gate` just proved works from a phone); NFL preseason
widening; and the maker *live* test (no cancel path exists).

### One housekeeping note

`.claude/worktrees/agent-ac69ee4907c57aa1a/frontend` could not be removed — a
file handle is still open on it. It contains **zero files** and `.claude` is on
`NOT_PRODUCTION`, so it cannot pollute the has-no-caller walker. Delete it when
convenient.

---

## 2026-08-09, ~22:40Z — DEPLOYED, and `actionable` has been 0 for the whole record

`main` at `1002028`, pushed, **CI green on all three jobs**. 1,753 tests, ruff
clean, `next build` clean, tree clean, no worktrees.

**LIVE IS DEPLOYED on `1002028`** and verified independently, not by the
workflow's own assertions. Demo went first as the canary:

    demo   seven pages 200, instance_mode=demo, execution_available=false,
           /api/orders 403 with and without a forged bearer
    live   instance_mode=live, live_trading_enabled=false,
           retired_settings_set=[], six pages 307 -> /login (with ?next=),
           /api/orders 401 with and without a forged bearer,
           /api/ledger and /api/gate 401 unauthenticated

No migration ran and that was checked before triggering, not hoped:
`SCHEMA_VERSION` is 6 on both the previous live commit and this one, and every
`schema.sql` change since is comment text with the column definitions
byte-identical.

### THE FINDING — read this before planning anything

`/api/gate` now exposes `populations`, which nothing could reach before (it
existed only as a log line, i.e. `flyctl`, i.e. a laptop). Over the **whole
table, at every horizon, since the record began**:

    actionable      0
    no_edge       594
    suppressed    868
    total rows   1462

    predicate: actionable = suppressed_reason IS NULL AND reference_contracts > 0

**Zero rows, ever, in 1,462 written.** Not "zero in a recent window", not "zero
among scored rows" — the strategy has never once produced a row it would have
bet at the fixed $1,000 reference bankroll. **G = 0 against a floor of 300, and
the numerator has never been anything else.**

Set beside ADR 0016 — a 1,200-game backfill has a 95% ceiling of 35 actionable
games — the honest reading is that **the gate is not reachable by accumulating
more of the same.** That is not a plumbing failure. It is CLAUDE.md's premise
returning the answer it warned was likely:

> Kalshi's advantage is cost, not information. This tool exists to find out
> whether an edge is there — not to assume one.

**Do not engineer around this.** Relaxing a threshold to make `actionable`
non-zero would manufacture the evidence the gate exists to demand.

### The record is 39% legacy, and that was invisible until now

    horizons:  "0": 476   "1": 569   unscored: 417     total: 1462

**569 rows carry the 1.0h anchor** that v5 tags and never re-scores. Any number
computed over "rows with a CLV" without filtering the horizon is a mixture of
two regimes at a factor of 2.2 — and it biases **upward**, because a 1h line is
the weaker benchmark (`analysis/clv.py:69-71`).

`total: 1462` against `limit: 1000` also means the ledger's default window is a
**slice**. Every rate taken off it describes the newest rows, which are
size-biased toward games that generated many rows.

### The three URLs — sign in once at `/login`, then from a phone

| Question | URL | Read |
|---|---|---|
| Is the record horizon-mixed? | `/api/ledger?limit=1` | `horizons`; `"0"` is evidence, `"1"` can never count |
| Has `actionable` **ever** fired? | `/api/gate` | `populations.counts` |
| Slice or table? | `/api/ledger?limit=1000` | `total` vs `returned` |

### Next, in order

1. **The four fee-calibration trades (~$5, Joe's).** Promoted: this is no longer
   only a gate condition, it is a **live hypothesis about why `actionable` is
   zero.** `calculate_fee` returns the max across two candidate models, which
   sets the break-even bar at 52.00% rather than 51.75% and costs up to 0.8c per
   contract at the wings (measured; see ADR 0017 Addendum A). Only real fills
   resolve it. If the cheaper model is the true one, the bar moves *toward* the
   strategy — and that is testable for five dollars.
2. **The fresh-odds edge distribution, pre-registered first.** `stale_odds` is
   on 575 of 1,000 recent rows, so most of the record cannot speak; among those
   that could, `no_edge` is 594. If fresh-odds edges sit just under the bar, item
   1 decides everything. If they are centred negative, **the premise is refuted
   and that gets written down.** Route through `pre-registrar` — the record has
   now been seen, so an unregistered cut is a fishing expedition.
3. **The calibration consumer.** `kalshi_markets.result` is now being written on
   live, and has **zero readers**. It answers a different question — *is
   `fair_probability` right?* — that needs no actionable row at all, so it is the
   one live line of evidence the 0-actionable wall does not block. Outcomes only
   accrue forward from this deploy.

### Corrections — do NOT quote these numbers from the earlier reconnaissance

`measurement-skeptic` audited the first live read and most of the arithmetic was
invalid, every defect tracing to a field the API did not expose (now fixed).

- **"38 scored games" — withdrawn.** The ticker regex used to key games never
  matched a market ticker at all, only event tickers, and where it matched it
  chopped a fixed three characters. Splitting one event into several *inflates*
  G, which shrinks the multiplier and the cluster-robust error — the flattering
  direction. The registered key is
  `COALESCE(kalshi_markets.event_ticker, recommendations.ticker)`.
- **"Mean CLV −5.16 sits essentially on the null" — withdrawn.** The
  commensurability holds (`clv_tenths` is measured against the closing YES mid
  and reduces to minus the half-spread on *both* sides, checked away from 50c
  where the old NO-side bug vanishes). But at G=28 the always-valid interval is
  **[−37, +27] tenths**: it contains the null, contains zero, and contains a
  +2.7c edge. It confirms nothing.
- **The ungrouped slope — deliberately not recorded here.** At G=28 the minimum
  detectable slope is ~3.2 against a ceiling of 1.0, so it is noise, and it was
  not the registered estimand (game-clustered partial slope controlling
  `half_spread_tenths`). A "not the test" label falls off in three weeks and the
  digits stay.
- **"87 rows is the D1 bug's cost" — overstated.** Computed over a horizon-mixed
  slice that is not the registered population.
- **`commence_ms` null on every row was a serialiser gap, not a data gap.**

**What survives, and it is the cleanest number in the set:** 160 of 575 rows
carrying `stale_odds` have it as part of a **composite** reason (27.8%). That
needs no population definition and directly corroborates Amendment 1's D1 — the
superseded `NOT IN` predicate would have retained every one.

### The reference/suggested question, settled

The audit said `actionable=0` was not evidence about reference sizing, because
the v6 backfill set `reference_contracts = suggested_contracts` on every
pre-existing row. **Right about the mechanism, too strong about the claim.**

`git show 78b5790^:fly.live.toml` — the deployment in force when the backfill ran
— sets `BANKROLL_DOLLARS=1000`, `KELLY_FRACTION=0.25`, and leaves the three caps
unset so they fall to code defaults 100/400/50. **Identical to `REFERENCE_*` on
all six numbers.** The backfill is an identity, not an estimate. So those rows
*were* genuinely sized at $1,000: what is untested is the new
`RiskConfig.reference()` code path, not the proposition.

**A falsifiable prediction to check later:** `BANKROLL_DOLLARS` dropped 1000 ->
100 in the same commit as the backfill, so every row written since genuinely
diverges. Rows with `reference_contracts > suggested_contracts` must start
appearing in the counted set once they reach the 0.0h anchor. If they never do,
something is wrong.

### Also landed this session

- **`kalshi_markets.result` is written** — declared in the schema and written by
  nothing for the project's life. Its residue is bounded: one tied game went from
  192 ERROR lines/day *forever* to 2 total, and a permanently stuck event from
  ~96 requests/day forever to zero after 7 days.
- **An unrecognised league is now a decision.** NFL preseason is spelled
  `"Pro Football Preseason"`; 726 markets across 48 events were dropped with no
  warning and no failing test. Scope is deliberately unchanged — **including it
  is not a config change**, see the note in the previous section.
- **`test_has_callers` no longer counts a worktree copy as a caller** (it was
  walking 132 `.py` files from other branches).
- **`edge_tenths` is net of fees** and `schema.sql` said the opposite, plus four
  more drifted comments.

---

## 2026-08-09, late — six lanes landed, and three audits refuted the prose over them

`main` at `a60f4bb`. **1,732 tests**, ruff clean, tree clean. Nothing was
deployed, no order was placed, no odds credit was spent, no gate was touched.

**LIVE IS UNCHANGED and still runs `1d81d3c`.** Read independently from the
browser this session, not inferred:

    {"status":"ok","instance_mode":"live","live_trading_enabled":false,
     "execution_available":false,"notifications_configured":true,
     "live_quotes_available":true,"agent_fleet_configured":true,
     "retired_settings_set":[]}

**So `main` now carries code live has never run** — the market-result pass, the
league warning, the bounded residue. None of it produces a row until a deploy,
and a deploy is Joe's.

### THE BLOCKER, and it is one tap

Everything downstream of the signal test needs the live evidence record. There
is **no local proxy**: `data/demo.db` is 100% synthetic on four independent
tells (`event_links`, `fair_prices` and `kalshi_quotes` all zero rows against
409 recommendations; all 400 scored rows carry `closing_line_id = NULL`, which
the live path cannot produce; `strategy_configs` holds one row reading "seeded
demo configuration"). **Every number in `data/lake/` and `data/warehouse.duckdb`
is a number about generated data, including the "36 of 300" and "51 of 300" CLV
buckets.**

`middleware.ts` gates everything except `/api/health`, `/login`, `/session` and
three static files, so an agent cannot read the record. Sign in at
`kalshi-cockpit.fly.dev/login`, then `GET /api/ledger?limit=1000`.

Five things only that answers:

1. `clv_scored` **in games**, not rows. That is `n`, read before any effect size.
2. `SELECT clv_horizon_hours, COUNT(*) ... WHERE clv_scored_ms IS NOT NULL
   GROUP BY 1`. Both horizons present makes any pooled mean a mixture of two
   regimes (ADR 0011).
3. `SELECT reference_contracts > 0, COUNT(*) FROM recommendations GROUP BY 1`.
   One distinct value is the tell that the actionable branch has never been taken.
4. Whether `run_scoring_pass` has **ever** returned `scored > 0` on live. Two
   prior runs recorded "249 joined, 249 skipped, 0 scored" and "unreadable_quotes:
   20, scored: 0". Both bugs are fixed in source and **nobody has confirmed a
   non-zero count.** If it is still zero, the top item becomes fixing scoring.
5. `kalshi_quotes` bid coverage, for the pre-registration's P1.

### Next, in order

1. **The CLV signal test — registered, and the registration says WAIT.**
   `docs/measurements/2026-08-09-preregistration-clv-signal-test.md` plus
   Amendment 1. Against the Robbins boundary already in `gate.py`, the smallest
   resolvable slope is 2.28 at G=40 and 1.00 at G=100 — where 1.0 is full
   lossless pass-through, the ceiling of what can exist. **G=300 is the first
   point it resolves anything decision-relevant**, arrived at independently and
   landing on the gate's own floor. Run it when `n` is there, not before.
2. **The maker histogram**, with the two pre-steps now written into ADR 0017
   Addendum A: count the rows in the band first (nobody has), and say whether you
   plotted the n=1 stored column or recomputed at n=10.
3. **ADR 0016 Phase 0.** Candles and derived asks agree 51/51, so the price axis
   is sound. Three conditions in
   `docs/measurements/2026-08-09-candle-ask-reconciliation.md`, and it is still
   time-critical: the Kalshi candlestick half expires at ~80 days.

### The half-spread confound is dead, and by a bound rather than an estimate

Measured on **219 games / 438 markets / 78,047 market-minutes**: the pre-game
half-spread takes **exactly two values, 5 and 10 tenths, 99.71% at 5**. SD is
0.27 per market-minute and **0.00 per game**. The spurious slope is 0.0007
against the 0.16 the pre-registration assumed — off by ~230x.

**The permanent part:** on a two-point support `{5, 10}`, `sd = sqrt(p(1-p))·5`,
maximised at **2.5**. The assumed 4 is arithmetically impossible, so **no
selection of this population can push the spurious slope above 0.0625.** P1 is
demoted from blocking to reporting.

**The one condition that brings it back:** if the recorder ever writes rows about
**spreads or totals**. Those live-quote at sd 47.2 and sd 22.8 — over a hundred
times the moneyline's — and stay wide inside 60 minutes of kickoff.

Also: ADR 0006's "max 1.00c" was a small-`n` artefact. At 219 games, 0.29% of
minutes quote 2c.

### Decisions waiting on Joe

- **The four fee-calibration trades.** ~$5, pre-authorised, unchanged. Still a
  hard gate condition no amount of CLV can satisfy.
- **NFL preseason.** 726 markets across 48 events are excluded, now explicitly
  and with a warning rather than silently. **Including it is not a config
  change.** `KXNFLGAME`/`KXNFLSPREAD`/`KXNFLTOTAL` each carry *both* league
  strings with `competition_scope = "Game"` on both, so neither the ticker nor
  the scope separates the populations — only `product_metadata.competition` does,
  and nothing persists it per row. The only league cut in the analysis path joins
  through `kalshi_series.league`, one row per series, **written on first insert
  only** — so switching would freeze that row on whichever population was seen
  first and relabel *both* sides, retroactively, at read time. Widening needs a
  league column written at recommendation time plus a backfill decision.
- **`backend/agents/skeptic.py`** hands the LLM Skeptic a net edge labelled
  `claimed_edge_cents` beside `ask_cents` and `fair_cents`, whose difference is
  the *gross* edge. Renaming that key changes a prompt, i.e. behaviour.
- **`backend/settlement.py:171-180`** raises `SettlementRefused` on `determined`
  markets carrying a result. It **cannot fire today** (`positions_awaiting_
  settlement` reads `FROM orders`, live has zero) and activates the day the first
  order exists. Note the premise that `determined` normally carries a populated
  `result` is an **inference, not a measurement** — the capture holds zero
  `determined` markets.

### What landed

- **`kalshi_markets.result` is written.** Declared in the schema, written by
  nothing for the project's life. ~1,400 game markets a day get an outcome, bet
  or not. **Calibration now has inputs; calibration is not yet possible** —
  the column has zero readers, and `clv.py` and `mart_calibration` both read
  `settlements`.
- **Its residue is bounded.** One tied game went from 192 ERROR lines/day forever
  to 2 total; a permanently stuck event from ~96 requests/day forever to zero
  after 7 days. There is a real stuck one in our own capture, unresolved since
  January.
- **`edge_tenths` is net of fees**, and `schema.sql` said the opposite. Four more
  column comments disagreed with their writers. `audit-2026-08-07.md` had already
  found this as item 41 and recorded it **closed** — 41 bundled nine findings and
  this one was skipped.
- **ADR 0017 Addendum A**, with three of its own four numbers corrected by audit,
  every error in the flattering direction.
- **Combo E2**, corrected to what its audit supports, plus the follow-up that
  separates the explanations: the engine term is **zero on 9 of 9 rows**, so the
  disagreement is replica skew, not a pricing engine. One row's list quoted a
  best NO bid of 0.7070 against the book's 0.4020 — a **30.5-cent** cross-
  endpoint disagreement 0.71s apart.
- **`pre-registrar`** joins the fleet. It owns the *before*; `measurement-skeptic`
  owns the *after*.
- **`test_has_callers` no longer counts a worktree copy as a caller.** It was
  walking **132 backend `.py` files from other branches**, so a symbol whose only
  caller lived on an unmerged branch passed on `main` — in the one file that
  exists to catch code with no caller.

### Read this before quoting any number above

`measurement-skeptic` audited three documents and the arithmetic reproduced **to
the digit** in every one. The conclusions were still wrong, because the inputs
that came from outside the code were assumed and unlabelled. The lesson is in
`tasks/lessons.md` — *arithmetic that reproduces to the digit says nothing about
its inputs* — and the practical form is: label every number **computed from
code**, **measured from data**, or **assumed**, and count the third kind.

---

## 2026-08-09, ~19:30Z — the bankroll trap is fixed; the backfill cannot open the gate

`main` at `1d81d3c`, **pushed, CI green, and DEPLOYED TO LIVE** (~19:48Z).
1,538 tests, ruff clean, `next build` clean, 11 dbt nodes green. The v5 -> v6
migration ran on the real volume; gate locked; six pages 307; `/api/orders` 401.
First gate progress on the new code: actionable=0 of 300, no_edge=287,
suppressed=287, with stale_odds=239 dominating.

### Done

- **ADR 0015** — the deposit no longer decides what counts as evidence. Schema
  v6 adds `reference_contracts`; the gate, the digest, the Playbook screen and
  the warehouse all count it. `min_order_contracts` deleted with no replacement
  (the sizer already pays the worst per-contract fee, proved rather than
  enumerated). Caps re-scaled 10/40/10. `BANKROLL_DOLLARS=100`.
- **Five of that ADR's claims were corrected by `measurement-skeptic`**, two
  refuted. The guard was not refusing everything — it was confining the evidence
  to the wings, which is worse. See `start.md`.
- **UI consensus, 7 of 8 items.** `/rejections` screen, whole slate visible,
  `53.8%`, fee-inclusive total, variance, `clv_tenths` on the Ledger.
- Four stale worktrees removed; `.claude/worktrees` no longer doubles every grep.

### Next, in the order `partner` set it

1. **`publish` wired into the live loop plus retrieval**, so the evidence record
   leaves the volume. Currently the only copy is on a Fly disk.
2. **The signal test.** Does the strategy have predictive power at all? Every
   other line of work is downstream of this.
3. **The maker histogram**, then the maker test only if it clears — ADR 0017's
   precondition. Plot the edge distribution between the taker bar and 1.00–1.50
   points below it, 18c–82c only. No mass, kill the line for free.

### The backfill: designed, and the design says do not build it for the counter

**ADR 0016.** 0 actionable in ~202 fresh-odds decisions puts a 95% ceiling of
**35 actionable games** on a 1,200-game backfill, against a floor of 300. The
gate cannot be reached this way and that is knowable now, before spending 9,600
credits. Build it to *measure the rate at n=1,200*, or not at all.

7 of 28 inputs are contaminated by look-ahead and `depth_at_ask` cannot be
reconstructed at all. Phase 0 is free and time-critical — the Kalshi candlestick
half expires at 80 days while the odds half never does.

### The combo line: one free experiment left, then drop it

The leg-echo test is **not answerable at any cadence** — combination quotes and
leg ticks live on disjoint timescales. What is worth ~20 free calls is **E2**,
pre-registered in `docs/measurements/2026-08-09-combo-leg-echo.md`: read the
order book alongside the list quote and report the book-empty rate. 3 of 8
quoted combinations had an empty book, and every combo price this project holds
came from the list endpoint without that ever being checked.

---


## CLOSED 2026-08-09 — the 94% is withdrawn, and the replacement died too

**Answered. `docs/adr/0012` addendum. Do not act on either number.**

The re-run gave same-game 22.4% against 94%, and cross-game fell with it, which
looked like the staleness verdict. **`measurement-skeptic` refused it and was
right.** Three things, each independently fatal:

1. **17/18 is one expected outcome on the non-refusal side.** It should never
   have been printed as a rate, and no smaller rate replaces it.
2. **The two runs are different populations** — same-game went 3.7% -> 16.3% of
   the measurable sample, two-sided fell 5x. Not comparable.
3. **A leg echo explains 86% of every domination event in every scope.** The
   combination's ask equals one of its own legs' costs to within 2c. Excluding
   those: cross-game 1.9%, same-game 3.3%, on 19 games, intervals overlapping.
   **119 rows match a leg that is not the cheapest** — impossible under any
   dependence structure, so for that subset the quote is not a joint at all.

Also found, both mine: the age control **cannot run** (nothing older than ~71s
is ever sampled; the confound lives at 39 minutes), and the contemporaneity
filter was a **tautology** — one stamp per round on the joint and every leg made
the gap identically zero, and it printed "dropped 0" as evidence. Both fixed.

**Next step is ~20 free API calls, not another 70-minute harvest**: re-read the
near-leg tickers and record whether the combo ask moves tick-for-tick with the
matched leg.

### Superseded — the original ticket


**Raised 2026-08-09 by Joe. Not overturned — suspected. Settle it, don't assume
it either way.**

### The claim on the record

`docs/adr/0012` reports that of **18** same-game combinations found, **17 had an
ask outside the Frechet bounds** — a quoted combination price no dependence
structure can produce. The refusal gradient was read as suggestive of strong
positive same-game dependence:

    cross-game   102/437   23%
    mixed          9/19    47%
    same-game     17/18    94%

The ADR names one alternative explanation and does not rule it out: *"a stale
leg quote looks identical."*

### Why it is suspect

`leg_quote` in `scripts/measure_combo_correlation.py` cached each leg's quote by
ticker **with no expiry for the whole run**, and `survey`'s comment defended
this as keeping a combination contemporaneous with its legs. It does the
opposite. The cache pins a leg to the first moment *that run* saw it; Kalshi
mints ~700 combinations a minute and the run keeps discovering them, so a
combination first seen in round 40 was priced against a leg quote from round 1 —
**39 minutes earlier**.

Comparing a fresh joint against a 39-minute-old leg produces "the ask is
impossible given the legs" whether or not anything is mispriced. **The harness
was manufacturing the exact confound the ADR names as its alternative
explanation**, and the effect grows with `--rounds`, so the recommended
55-round invocation was the most affected.

Fixed 2026-08-09: the cache is cleared per round, and `Quote.observed_ms` plus
`Combo.created_ms` now record contemporaneity as data rather than as policy.

### What settles it

Re-run the harvest on the fixed code and compare refusal rates against the three
above. **Cross-game is the control** — if staleness drove the gradient, the
cross-game rate must fall too, not just same-game.

    .venv\Scripts\python.exe scripts\measure_combo_correlation.py ^
        --pages 4 --rounds 55 --interval 60 --json docs\measurements\<date>-combo.json

Then read domination separately:

    .venv\Scripts\python.exe scriptsnalyse_combo_domination.py <capture>

### How to read the outcome

| Result | Meaning |
|---|---|
| Same-game rate falls sharply, cross-game falls too | The gradient was substantially harness staleness. **Correct ADR 0012.** |
| Same-game stays ~94%, cross-game falls | The gradient is real and now better evidenced. Strengthen the ADR. |
| Both unchanged | The cache was not the driver. Record that the mechanism was ruled out. |

### Read `n` before the effect size — this is the part most likely to bite

**Eighteen.** Seventeen-of-eighteen reads as decisive and is a very small cell,
and only 18 same-game combinations appeared in **46,916** markets. Whatever the
new run says, the sample may still be too thin to carry a claim. Have
`measurement-skeptic` audit before anything is written into the ADR — the
first check it runs is whether the denominator existed at all.

Also unchanged from the ADR: **none of the 18 was two-sided**, so every
same-game number rests on the ask-only population, which ADR 0012 itself
refuses for correlation (sd 0.254, spanning −0.757 to +0.898). A refusal rate
computed on a population the same document refuses to invert is not obviously
sound, and that tension predates this ticket.

### Do not

- Do not silently edit ADR 0012's numbers. If they are wrong, the correction is
  an addendum that says what was believed, why, and what changed — the record
  is the product.
- Do not conclude "the cache explains it" without the cross-game control moving.
  That is assuming the answer this ticket exists to test.

---

## 2026-08-09, ~16:00Z — the gate freeze was an empty slate. DECIDED: accept.

**Joe chose option 1. `docs/adr/0014`. Do not reopen without new evidence.**

The previous handoff diagnosed the ten-hour `no_edge=177` freeze as the sweep
scheduler being too restrictive, and escalated three options. The diagnosis was
wrong: **today's first in-scope kickoff was 16:15Z and the frozen interval ran
05:51Z-15:45Z.** No games, so no slots, so no windows. The counter did not move
because nothing asked it a question.

What was measured, all free (ESPN + the repo's own `plan_sweep_slots`, no odds
credits):

    Today's slate: 19 games (mlb 15, wnba 4)
    Slots at the deployed 2h separation: 6, covering 18 of 19 distinct games
    Cost: 36 credits of 400
    Loosening MIN_SLOT_SEPARATION_MS to 1h: 8 sweeps, 19 of 19 -- ONE more game

And a real window, read live at 15:46:44Z:

    basketball_wnba (scheduled): 3 game(s) from 16:30Z
    odds_sweeps 1, odds_quotes_stored 762
    recommendations 24, surfaced 0, suppressed 8
    no_edge 177 -> 193      (+16, matching the 05:36Z sweep exactly)

So one open window writes ~24 rows: **16 no_edge, 8 suppressed, 0 actionable.**

**Option 2 refused** — there is no uncovered population to reach; it buys one
game a day for 12 credits and costs freshness on the 13-game cluster.
**Option 3 refused** — it reverses ADR 0005, and that was a safety property:
`suspicious_edge` rows are the likeliest carriers of a systematic CLV, so
pooling moves the mean rather than diluting it.

**The arithmetic that makes it moot.** 300 independent games against a ~19-game
slate is **16 days minimum even if every game were actionable**, and the rate is
zero. The scheduler was never the binding constraint. The two levers that are:
the **four fee-calibration trades** (still Joe's, still a hard gate condition)
and a **historical backfill** (~80-day candlestick horizon, ~1,200 MLB games,
budget headroom already reserved).

Also corrected: this file's "≤12 useful slots/day per sport, so six leagues
cannot exceed ~432/day" is a ceiling from the separation constant alone. The real
bound is kickoff clusters — three per sport on an August slate, six sweeps total.
The budget has ~11x the headroom that reasoning assumed.

`scripts/measure_slot_coverage.py --date YYYYMMDD` makes this re-measurable on a
winter slate rather than re-arguable.

---

## 2026-08-09, 06:00–09:00Z — five items closed, and one of them was Joe's

`main` is pushed and CI-green. **1,405 tests**, ruff clean, `next build` clean,
five pages measured at 320/390/430 and looked at. Nothing was
deployed, no order was placed, no gate was touched, no odds credit was spent.

### 1. One log line per pass, not two

`pricing pass:` was a strict subset of `pass N ok`, emitted ~4ms earlier from a
different module, at whatever rate the caller happened to run — 900s when it was
written, ~22s once the odds budget went 16 → 400. Deleted.

The recorded reason it was "not simply removable" — that `run_chain.py` would go
silent — **was wrong**: `run_chain.py` has always printed `counts.as_dict()` as
indented JSON. What the inline line did carry, and nothing else did, is a pass
that recorded fine and then died in scoring, where `run_forever` logs a traceback
saying where it broke and nothing about what had already been written. That job
moved to `counts_survive_a_late_failure` in `run_loop.py`, on the failure path
where it earns its place.

The claim that made the deletion safe is now an assertion instead of prose in a
handoff file: every field of `PassCounts.as_dict()` must survive into
`CombinedPass.as_dict()` unrenamed.

### 2. Exposure counts the fee — ADR 0008's gap 3, closed with no migration

Three ADRs deferred this on the grounds that it "needs a fee column on
`orders`". **It needed no column.** `count` and `limit_price_tenths` were
already stored and are exactly what `calculate_fee` takes. The real obstacle was
that exposure was a SQL `SUM` and the fee is a maximum across candidate models
with a per-order rounding step — not expressible in SQL. So the obstacle was the
duplicate implementation, restated as a schema problem.

`store.orders.exposure_contribution` is now the only expression of what an open
order commits, called by both the ticket's projection and the cap. Those were
previously two paths pinned together by a test. They agreed, and both left the
fee out — which is the one defect a two-paths-agree test is blind to. Lesson
written.

Ten contracts at 50c now read $5.20, not $5.00.

### 3. The combo lookup no longer needs Joe — the price was always readable

**This was item 4 on his list and it is off it.** The authorised
`POST .../lookup` is *unspent* and no longer on the critical path.

Kalshi's users mint provisional combination markets by tapping legs in the app —
about **700 a minute** — and `GET /markets` returns them carrying
`mve_selected_legs`, `mve_collection_ticker` and a live quote. Nothing has to be
created. The reason nobody had noticed: 5,000 consecutive open markets span
**6 minutes 48 seconds** of `created_time`, `/markets` is newest-first, and a
quote decays within ~2 minutes — so paging depth-first is guaranteed to find
nothing, and three separate walks did exactly that. The sample has to be
accumulated over *time*, polling the newest page.

**The control ran, and it is the finding.** Cross-game legs are near-independent,
so their true rho is 0. Over 55 minutes and 46,916 distinct markets:

    cross-game, TWO-SIDED, n=23    rho at mid  +0.003   sd 0.089
    cross-game, ask only,  n=308   rho at ask  +0.234   sd 0.254

At the mid the method **returns the right answer** — +0.003 where the truth is
zero. The ask-only population is refused, and not because its bias is large: it
has sd 0.254 spanning −0.757 to +0.898, and a bias you cannot subtract is a
refusal rather than an offset. A 26-minute run replicates it (mid −0.033, n=12).

**No same-game correlation has been measured**, and that is the honest state: 18
same-game combinations appeared, **none two-sided**, and 17 of 18 had an ask
outside the Frechet bounds for their own legs.

**That refusal rate is itself the second finding.** An ask above `min(marginal)`
is one no dependence structure produces:

    cross-game   23%      mixed   47%      same-game   94%

The gradient runs cleanly through `mixed`, which is what same-game *pairs*
driving it would look like — strong positive dependence pushes the joint toward
`min(marginal)`, and near that ceiling any margin puts the ask above it. Kept
suggestive rather than claimed: a stale leg quote looks identical. The sharper
test needs no correlation at all — compare the combination's ask against the
cheapest leg's own **ask**, since a combination costing more than a leg that
pays out in a superset of cases is dominated outright. Leg bids and asks are now
recorded in the `--json` output for exactly that.

`docs/adr/0012`; both runs in `docs/measurements/`.

Also corrected: `active_quoters` is `[]` on **all 14,240** published legs while
those same leg markets are two-sided with 21,247 contracts of open interest. It
is not a liquidity signal, and "0 of 13,806 legs quoted" said nothing about
whether a combination could be priced.

### 4. `orderbook()` returned an empty book for every market on the exchange

Found by accident while probing for a market with a genuinely empty book: the
probe found none, and then reported `{}` for a market carrying **21,256
contracts of open interest and a two-sided quote**. Two facts that cannot both
be true.

`KalshiRestClient.orderbook` read `payload["orderbook"]`. The envelope is
**`orderbook_fp`**, and the sides inside it are `yes_dollars` / `no_dollars` —
not the socket's names. With `or {}` behind the lookup it returned an empty
book, always, silently.

**It has no callers**, which is the only reason it never cost anything. It now
raises `MalformedOrderbookResponse` on a missing envelope, because an empty book
is a legitimate state on this venue and a renamed field is not, and the two must
not share a return value.

**This is the fourth wrong wire key in this project**, after `data["yes"]`,
`multivariate_event_collections`, and `competition_scope == "game"`. All four
returned something empty, correctly typed and plausible. The prose rule against
it was written after the first and did not stop the next three.

So there is now a mechanical one — `tests/test_parsers_return_something.py`:

- **Every parser, run on a real capture, must return something non-empty.** One
  line each. All four historical bugs die to it; nothing else catches them,
  because a wrong key yields a well-formed empty collection that satisfies every
  assertion written about its contents.
- **Every fixture must be read by some test**, or be listed as evidence with a
  reason. That check immediately found two that nothing read —
  `sports_coverage.json` and `occurrence_datetime_probe.json` — which is a
  lesson this repo already had, sitting live in the tree.

### 5. Playbook screen — built. Research screen — deliberately not

Joe's item 3 was "the Research and Playbook screens". **One of them should not
be built yet, and saying so is the useful half.**

**Research: not built.** It would read Scout findings. There is no table for
them, `agents/scout.py` is called by nothing that runs, and wiring it means
Anthropic calls with web search on a schedule. A screen over a source that is
structurally empty is worse than no screen — it *looks* like a feature. This
repo has the lesson: code with no caller is a plan, not a feature.

**Playbook: built**, because its main source is real. `strategy_configs` is
written by `engine.py` in production, and `recommendations.strategy_config_
version` has been written since the engine existed and **read by nothing**.
That matters: a threshold edit splits the evidence into halves that cannot be
pooled, and the halves look exactly like one continuous record once totalled.

`GET /api/playbook` + `/playbook`. Per version: recommendations, markets,
unsuppressed, actionable, CLV scored, the diff from its predecessor, and a
caveat when the version carries too few rows to say anything. Markets beside
rows, deliberately — the row count measures uptime, not evidence.

Two things it refuses to collapse:

- **An empty lessons list is not "nothing to report".** `lessons` has one
  writer, the Historian, and nothing calls it. The screen says *"The Historian
  has never run"* — the same distinction `analysis/marts.py` draws between an
  unbuilt warehouse and an empty one.
- **`accepted_by_user` has three states.** NULL is "nobody decided", 0 is
  "rejected". Collapsing them either empties the awaiting-approval list or puts
  every rejected proposal back in front of Joe forever.

Verified at 320/390/430 and **looked at**, which found three defects the
measurement could not:

- `grid-cols-2` at 320px painted "Recommendations" over its neighbour without
  overflowing anything — `minmax(0, 1fr)` lets a column shrink below its own
  content, so `scrollWidth` stays exactly equal to the viewport. This is the
  "CONSENSUSKALSHI" defect; only the per-element check sees it.
- `{floor} observations` across two JSX lines rendered as `100observations`.
- **The sixth nav link pushed the Gate off-screen at 390px.** The row scrolls
  rather than clipping, which is the designed degradation — but the Gate is the
  screen that says whether money can move, so Playbook goes last instead.

### Still open, unchanged

- **The four fee-calibration trades.** Joe's, pre-authorised, not done. Still a
  gate condition and still the binding constraint on it.
- **`gate progress (24h)`** needs a full day on the new budget. Untouched here.
- **`discovery:` on a quote pass** — proven by test, not yet observed on live.
  Needs an open odds window (next ~15:45Z).

---

## DEPLOYED (2026-08-09, 05:36Z) — the budget stopped being the constraint

Key installed (machine v22, 05:33Z) and `f1fb326` deployed (v23). Gate locked,
five pages 307, `/api/orders` 401. The first full pass on the new budget, beside
the last one on the old:

    old (05:34)  sweep_decision: no sweep: 12 of 16 credits spent
                 events_linked 10   fair_prices_written 20   recommendations  4
    new (05:36)  odds_sweeps 1      odds_quotes_stored 626
                 events_linked 16   fair_prices_written 32   recommendations 24

**A sweep fired on the first pass and 626 quotes landed.** Linked games up 60%,
priced games up 60%, six times the recommendations. `alerts_sent: window_open`.

And the window now *stays* open, which it almost never did: quote passes are
running every ~22s continuously rather than for 15 minutes twice a day. That is
the whole point of the change.

`gate progress` moved in the right direction within two passes:

    05:34  actionable=0  no_edge=161  suppressed=262
    05:36  actionable=0  no_edge=177  suppressed=270  (+suspicious_edge=2)

`no_edge` +16 is fresh odds producing honest "no bet here" answers on games that
previously had nothing to price against. **`actionable` is still 0** — that is
the real question and it now has a growing sample instead of a starved one.

`suspicious_edge=2` is new and is *not* an opportunity: it is CLAUDE.md's first
rule firing, two edges large enough to be a bug until proven otherwise.

### Log volume — the `discovery:` line is fixed; one duplicate remains

**Correction to the figure in the previous section: ~12,000 lines a day was
wrong, and wrong in the alarming direction.** It assumed the window stays open
all day. It does not. A sweep opens it for `MAX_ODDS_AGE_S` (900s) and then it
shuts: measured on live, the 05:36Z sweep produced quote passes from 05:38:44 to
05:51:14 — about 12.5 minutes, ~34 passes — and the next slot was 15:45Z, nine
hours later. At 10–20 sweeps a day that is roughly **400–800 quote passes, so
1,200–2,400 lines**, not 12,000.

The fix is still worth having and the reasoning behind it is unchanged. The
*size* of the problem was overstated by roughly 5x, by extrapolating a window
that had been open for the twenty minutes I happened to be watching. Reading a
rate off a burst is the same error as reading a population off a log buffer,
which this file already records from earlier the same day.

A quote pass emitted three lines every ~22s while the window is open, against a
100-line `flyctl logs` buffer. That still eroded the readability won hours
earlier by collapsing the 962-line scope burst — during exactly the windows when
something interesting is happening.

**`discovery:` is fixed.** It prints on every full pass — the heartbeat, so
silence still cannot mean "discovery did not run" — and on a quote pass only
when its numbers change. Both halves are needed and each is verified by
disabling it: change-detection alone reintroduces the exact ambiguity the
unconditional print existed to prevent.

The general shape, which is the part worth carrying: **a logging rate is a
property of the caller, not of the code.** This line was correct at 900s and a
flood at 22s without one character of it changing. The trigger was the odds
budget going 16 → 400 four hours earlier — a change in a different subsystem
entirely.

**Verification status, stated exactly.** Proven by test — 61 identical quote
passes produce one line, and disabling either half turns a different test red.
**Not yet observed on live**, because the window closed minutes after the deploy
and quote passes only run while it is open. The next window is ~15:45Z; the
check is that `discovery:` appears once per *full* pass and not once per quote
pass. Do not record this as confirmed until that has been read.

**Still duplicated, and not fixed:** `pricing pass:` is a strict subset of
`pass N ok`, emitted ~4ms earlier by a different module (`runner.py` vs the
scheduler in `run_loop.py`). In the loop it carries nothing the later line does
not. It is not simply removable, because `run_chain.py` emits no `pass ok` line
and would go silent. Worth ~4,000 lines/day if resolved; left alone rather than
guessed at.

---

## Superseded (2026-08-09) — the 20K tier is bought; the key is not installed

Two steps, in order, and step 1 is Joe's:

1. `bash scripts/setup_odds_key.sh` — the key never passes through an agent.
2. `gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`

`main` carries `ODDS_DAILY_CREDIT_BUDGET = 400` (was 16) and
`ODDS_MONTHLY_CREDIT_BUDGET = 13000`. **Not deployed**, though approved: the live
machine has not restarted since 04:37Z, so the wizard has not run, and 400/day
against the old 500/month key would burn the free tier's remainder for nothing.

**400, not 645.** Spend is capped by the scheduler, not the budget:
`MIN_SLOT_SEPARATION_MS` gives each sport ≤12 useful slots/day, so six leagues
cannot exceed ~432/day whatever the budget says. 400 puts the *fixture schedule*
in charge, which is the state the scheduler was written for and has never been
in. The gap to 20,000 is deliberate headroom for a backfill.

**A guard that was missing.** `BudgetState.spent_this_month` had been computed
since the module was written and checked by nothing. Fine while every call cost
6 credits; not fine once the historical endpoints (10× per call) exist, since a
backfill can spend the month between two daily resets. `can_afford` now checks
three ceilings — the provider's, ours-per-month, ours-per-day — and unset means
uncapped, never 0.

### Candlestick retention: ~80 days, measured

`scripts/measure_candlestick_retention.py`, free, unauthenticated. Bars at every
age to 79 days; at 80+ the market is **gone**, not delisted — constructed
tickers 404 while the same construction resolves both sides at 5d and 60d.
Addendum on `docs/adr/0011`.

- **Scoring: unaffected.** And it refutes the open worry that some of the 190
  unscoreable rows had aged out — every one is inside the window, so the
  ordering rule is the whole explanation.
- **Backtest: this is the horizon.** ~80 days ≈ 1,200 MLB games, above the 300
  the gate needs. Costing and the rule it must not break are below.

---

## The gate is blocked by the odds budget, and the guards are fine

Instrumented in `8c37e44` and **answered on the first pass** (live, 04:38Z):

    gate progress (24h): actionable=0 of 300 needed, no_edge=161, suppressed=265;
    suppressed by: stale_odds=256, too_few_books=73, no_market_width=73,
                   edge_within_method_noise=4

426 rows in 24h. The worry that sent me looking — that a miscalibrated rule was
refusing everything and pinning the gate's counter at zero — is **refuted**, and
what replaced it is more useful.

**`stale_odds` is 256 of 265 suppressed rows (~97%), and it is structural, not a
bug.** The odds budget is 16 credits/day at 6 a sweep, so ~2 sweeps, each opening
a 15-minute window. A full pass runs every 900s regardless, so ~94% of passes
write rows whose sportsbook consensus has already aged past `MAX_ODDS_AGE_S`.
Those rows *should* be refused. This is the composition already recorded in
`tasks/lessons.md` under two-limits-on-one-quantity — the tool is actionable
about 30 minutes a day — now visible as a row count instead of an argument.

**And the rows that did have fresh odds answered `no_edge` 161 times and
`actionable` 0 times.** That is the honest no-edge result, on the population
where the engine was actually able to speak. It is the premise of the whole
project holding, not a fault:

> Kalshi's advantage is cost, not information. This tool exists to find out
> whether an edge is there — not to assume one. (CLAUDE.md)

### What this means for the gate, stated plainly

The 300-game floor is not reachable by waiting. The binding constraint is odds
credits, and it is upstream of everything: no credits → no fresh consensus → no
actionable row → no CLV → no gate. Three options, and none is free:

1. **Pay for odds.** A larger Odds API tier buys more sweeps, more windows, more
   rows with fresh consensus. This is the only one that changes the arithmetic
   rather than the accounting.
2. **Spend the existing budget better.** Two sweeps a day is a *scheduling*
   choice. Concentrating them on the densest slate window, or sweeping one sport
   rather than all, trades coverage for freshness. Cheap to try, bounded upside.
3. **Accept it and let the record accumulate slowly.** At 0 actionable rows a
   day the floor is never reached, so this is only honest if (2) moves the number
   off zero first.

**Do not "fix" this by relaxing `MAX_ODDS_AGE_S`.** A stale consensus priced
against a live Kalshi ask is exactly how a fabricated edge enters the record,
and the record is the product.

### Two readings of this line that would be wrong

- **The reason counts do not partition.** A row carries a comma-joined list and
  `suppression_summary` counts each name, so 256+73+73+4 sums above the 265 rows.
  Read them as "how often each rule fired", never as shares of a whole.
- **`too_few_books=73` and `no_market_width=73` are one population, not two.**
  Identical counts because they co-occur by construction: one book cannot
  disagree with itself, so a single-book consensus has no measurable width.
  `tasks/lessons.md` records that sharp-book anchoring *causes* the single-book
  case. Counting them as two distinct problems would double the apparent size of
  a small one.

Caveat on scope: one day, one slate, in August — MLB and NFL preseason, with
NBA, NHL and NCAAF out of season. A denser winter slate is a different
measurement and this should be re-read then.


## READ FIRST (2026-08-09, later) — the log stream drops lines, and the number everyone quoted was a 10% sample

The one cheap check the previous handoff asked for is **done, and the answer is
zero.** The per-process scope dedupe holds in production. Evidence, because a
count off `flyctl logs` cannot settle it on its own:

    03:17:05  94 warnings, all one timestamp, all from pass 1 of a fresh process
    03:30:46  pass 2 -- zero new warnings; the 94 had aged to 91 in the buffer

The buffer rolls forward and no warning carries a second timestamp. The dedupe
was never broken; a count taken from a lossy buffer just cannot distinguish
"re-emitted" from "still sitting there". **The timestamp is the discriminator,
not the count.**

### What the check turned up instead, which is larger

`unknown_scopes=962` prints on the same line as those 94 warnings. Two counts of
one quantity, disagreeing tenfold, printed together and never read against each
other. Measured against the live exchange
(`scripts/measure_unknown_scopes.py`, free, no odds credits):

| | Recorded in this file | Actually |
|---|---|---|
| unknown (series, scope) pairs | 94 | **962** |
| distinct scopes | — | **317** |
| in leagues we price | "none of them a sport" | **227 pairs, 56 scopes** |

**The exclusion is still correct** — every excluded scope in a priceable league
is a future, an award, or a period/prop market (`Extra Innings`, `YRFI/NRFI`,
`First 5 Innings Winner`, WNBA `1st Half Winner`, `Win Totals`, `Draft`). No
game-level moneyline, spread or total is being dropped. But that was true by
luck rather than by the reasoning on record, and the reassuring sentence came
from a sample nobody knew was a sample.

### Fly drops log lines. Absence is not evidence of non-emission

962 lines in ~90ms into a 100-line buffer: ~90% dropped, **including the
neighbouring `discovery:` summary**, which is unconditional, was verified to
emit locally, and is proven to have run by its own return value appearing one
line later. It still was not in the stream.

So **the two boot lines were never merely "pushed out"** — they were competing
with a 962-line burst, and any conclusion drawn from a line *not* appearing in
`flyctl logs` is unfounded.

Fixed in `f7adbad`: one aggregated warning per process, naming the 56 priceable
scopes and counting the other 261. **The first pass now emits 2 lines where it
emitted 963.** The `no occurrence_datetime` warning four lines away had the
identical undeduplicated shape, latent, and is deduped per series.

### Watch item, and it qualifies the previous handoff: 59 was a batch, not a rate

Three passes on the record now, and the CLV counter did not keep moving:

    03:17  pass 1  full   scored 59  skipped 190  rows_joined 249
    03:30  pass 2  quote  (CLV runs on full passes only)
    03:44  pass 3  full   scored  0  skipped 190  rows_joined 190  lines_stored 44

`rows_joined` fell by exactly 59 — the scored rows dropping out of the join.
What is left is the 190 permanent residue ADR 0011 predicted. **The 59 was the
backlog being scored retroactively in one step, and the full pass since scored
nothing new**, while storing 44 fresh closing lines.

That is not yet a fault, and it is not yet growth either. The pricing pass wrote
`recommendations: 1` and then `0`, with `unchanged_confirmed: 39/40` — the
dedupe stamping existing rows rather than writing new ones, which is correct and
means `created_ms` stays put. A row can only score if a *new* row is written
before its game's close, so the counter's growth rate is bounded by how often
the pass writes a genuinely new recommendation, not by how many lines are
stored.

So: `clv_scored` went from **structurally impossible** to **possible**, which is
the real win and stands. It has not yet been shown to *accumulate*. Read
`rows_joined` and `recommendations` together over a full day before believing
either story; if `rows_joined` stays pinned at 190, no new row is scoring.

### DEPLOYED and READ (2026-08-09, 04:07Z) — the burst hypothesis is confirmed

Live is on `e885bca`. One machine `started`, 1/1 checks, restarted in place on
the volume, gate locked, five pages 307, `/api/orders` 401 with and without a
forged bearer.

**The first pass is now 10 log lines. It was 963.** Three things never before
observed:

    [migrate] /data/cockpit.db already at schema v5      <- a reading, not an inference
    INFO backend.api.routes: API starting: instance_mode=live ...
    INFO backend.kalshi.discovery: discovery: 167 priceable events;
         unknown_scopes=962; rejected ...                <- first appearance ever

That third line is the confirmation. It is emitted in the **same millisecond**
as the aggregated warning, from code that never changed — so the reason it had
never arrived was the 962-line burst sitting in front of it, exactly as
diagnosed. The one warning now reads `317 unrecognised competition_scope
value(s) across 962 series ... (56 named, 261 counted)`.

Also: the live db is `/data/cockpit.db`, not `/data/live.db` as earlier notes in
this file said.

First pass on the new image: `recommendations: 4, suppressed: 4, surfaced: 0,
unchanged_confirmed: 36`, `clv_scored: 0`, `clv_rows_joined: 190`.

---

## READ FIRST (2026-08-09) — the gate's counter cannot grow, and it is arithmetic

Found while reading the live logs. **`clv_scored` has been 0 on every recent
pass, and it is not a transient.** Two passes on record:

    rows_joined: 228   scored: 0   skipped_entry_after_close: 228   (08-08)
    rows_joined: 249   scored: 0   skipped_entry_after_close: 249   (08-09)

The previous handoff flagged 228/228 as "worth a second look if it does not
move". It moved to 249/249.

**The composition, and neither number is wrong on its own:**

| Quantity | Where | Value |
|---|---|---|
| Sweep fires at | `odds/timing.py`, `fire_until = anchor - max_odds_age_ms` | kickoff − 15 min |
| ...through | `fire_from = fire_until - due_window_ms` | kickoff − 45 min |
| Closing line read at | `scoring.py`, `target_ms = commence - horizon` | kickoff − 60 min |
| Scoring requires | `clv.py`, `r.created_ms <= c.observed_ms` | entry before the close |

A recommendation cannot exist before its odds sweep, so the **earliest** any row
is created is kickoff − 45 min. The closing line is observed at kickoff − 60 min
(earlier still, by up to `WINDOW_MINUTES`). So `created_ms <= observed_ms` is
false for **every** row the scheduled sweep path produces, permanently.

The gate needs **300 scored games**. On this path it will never reach one.

**Why it was invisible, and why it is new.** Every counter reads healthy;
`rows_joined` is nonzero and `skipped_entry_after_close` is faithfully reported
— that counter was *added on purpose* so this case would be visible. It was
visible. Nobody multiplied it out. And an earlier run really did score 34 rows,
because before `odds/timing.py` landed the sweeps fired at arbitrary times, so
some rows happened to land more than an hour before kickoff. **The scheduler fix
— correct on its own terms, and the thing that made the tool actionable — closed
the last path by which anything could be scored.**

This is [[two-limits-on-one-quantity]] on the one number the gate is built from.

**`docs/adr/0011` decides it, and it is now implemented** (schema v5).

The close becomes the **last pre-game quote** (primary horizon 0, control 1.0h,
which is where the ~34 already-scored rows sit). Shortening it is also the
*conservative* direction, which was the surprise: a market sharpens toward
kickoff, so scoring against a price an hour out was measuring against a weaker
benchmark and would have flattered any result it ever produced.

All four pieces landed, and the two that mattered most were found by the
disable-check rather than by writing them:

1. `DEFAULT_HORIZON_HOURS = 0.0`, `CONTROL_HORIZON_HOURS = 1.0`. **Watch for
   truthiness** — `0.0` is falsy and this repo has a lesson about zeros that
   mean something. Grep every `if horizon` before trusting it.
2. Schema v5: `recommendations.clv_horizon_hours`, backfilled `1.0` where
   `clv_scored_ms IS NOT NULL`. Without it `clv_tenths` becomes a silent
   mixture of two regimes.
3. Tag the rows scored at 1.0h with `clv_horizon_hours = 1.0` and **leave
   them alone** (amended by Joe before it ran anywhere). The gate's filter
   already excludes them, so clearing them bought nothing and would have
   edited the one record that cannot be recreated.
4. The composition test: fail if `primary_horizon + WINDOW_MINUTES` reaches back
   past `max_odds_age_ms + due_window_ms` before kickoff. Express it as a
   relationship between the four constants, not as `assert horizon == 0.0` —
   pinning the value passes while someone widens the due window and rebuilds
   the same collision from the other side.

---

## DEPLOYED (2026-08-09, ~03:17Z) — and `clv_scored` left zero

Live is on the current image. `restarts=0`, one machine, volume attached, gate
locked, five pages 307 -> /login, `/api/orders` 401 with and without a forged
bearer. First pass on the new image:

    CLV scoring at 0.0h horizon: {'scored': 59, 'skipped_entry_after_close': 190,
                                  'rows_joined': 249}
    settlement pass: {'positions_open': 0, 'settled': 0, 'still_unresolved': 0,
                      'refused': 0}
    pricing pass: {... 'surfaced': 0, 'skeptic_reviewed': 0, 'skeptic_blocked': 0 ...}

**`scored` had been 0 for the project's entire life.** The evidence layer is
recording. The gate's binding constraint is no longer code — it is the four
fee-calibration trades, which need Joe.

**Still unobserved:** the `[migrate]` and `API starting` boot lines. v5 running
was confirmed by its effects, which is an inference. The first pass of a fresh
process still emits all 94 scope warnings at once and fills the 100-line buffer;
any *later* pass should be clean, and checking that is the first task next
session. See `start.md`.

---

## HANDOFF (2026-08-09, ~00:10Z — the settlement path is built, nothing is deployed)

**State:** 1,288 tests, ruff green, `dbt build` 11 nodes green, pushed. `main`
is `2353bd1`. **Both instances are still on `89bf56a`** — everything below is
local and unshipped.

### Demo is deployed and green. **Live is the one thing outstanding.**

    # from the browser -- the classifier blocks live from a session:
    # Actions -> Deploy -> Run workflow -> live -> type kalshi-cockpit

Demo went out on `2353bd1` and verified: five pages 200, `instance_mode=demo`,
and both boot lines readable —

    [migrate] /data/demo.db already at schema v4
    INFO backend.api.routes: API starting: instance_mode=demo ...

**What the canary did not prove, and cannot.** The entrypoint *seeds before it
migrates*, and `seed_all` calls `init_db`, which builds the database at the
current version and stamps it. So `migrate_db.py` on demo is a no-op **by
construction** — "already at v4" there means the seeder had just created it at
v4, not that a transition ran. Demo proves the image boots and that the schema
file and the v4 shape agree on a fresh database. It says nothing about v3 → v4.

Live's volume is the only real test of that, and it is the first non-additive
migration in this project. What backs it instead: the boot script was run twice
against a genuine v3 database carrying rows (migrated, then no-op, orders
preserved, index present), and `test_the_migration_step_actually_runs_on_a_real_
old_database` runs it as a subprocess against a database wound back one version.

**v4 rebuilds `settlements`.** The rebuild is idempotent at every crash point
and was verified by running `scripts/migrate_db.py` twice against a genuine v3
database, but it is the first migration in this project that is not purely
additive, so the canary matters more than usual.

Three things to read in the log once it lands. The first two are the claims
`start.md` asked me to verify and I could not — see why below:

    [migrate] /data/live.db migrated v3 -> v4
    INFO backend.api.routes: API starting: instance_mode=live
    backend.settlement: settlement pass: {'positions_open': 0, 'settled': 0, ...}

### Why claims 1 and 2 were unverifiable, which turned out to be a real defect

`flyctl logs` returns a line-bounded buffer, and **98 of the 100 lines in it were
one warning** — `unrecognised competition_scope`, 94 distinct series, not one of
them a sport (`KXFED`, `KXWMT`, AP polls, draft picks). A quote pass re-emits the
whole set every 15s while the window is open. The boot lines were pushed out
within seconds of every boot.

The dedupe was there and was being cleared at the top of every pass, by a fix
for "warned once at boot then went quiet". Both halves defended in prose, four
lines apart. Now: the warning names a developer action item **once per process**,
and `discovery:` prints `unknown_scopes=N` every pass, including at zero. The
live stream should be readable for the first time.

Claim 3 is answered: **the fleet has never run.** The live pass line reads
`'surfaced': 0` — and carried neither `skeptic_reviewed` nor `skeptic_blocked`,
because `ALWAYS_REPORT` omitted the two fields whose own comment says they are
"reported anyway". Fixed; they print now.

### What landed

- **ADR 0010** — the paper settlement path, six decisions, three of them
  measurement decisions. Written after the capture, not before.
- **`backend/settlement.py`** — reads Kalshi's `result`, writes one row per
  position, releases its capital. On the full pass only.
- **Schema v4** — `settlements` is per-position (`order_id`, `dry_run`,
  `fill_assumption`, `depth_at_order`, `UNIQUE (order_id)`); `orders` gains
  `fill_assumption` and `assumed_filled_count`.
- **`max_exposure_dollars` binds in production for the first time**, on paper.
  This reverses ADR 0008, and only settlement makes it safe. Paper and live are
  separate budgets, never pooled, so the first real order sees a clean one.
- **The migration framework stopped parsing SQL.** Five readers recovered index
  names from statement text; one is the boot script, under `set -e`. v4's
  `ALTER TABLE ... RENAME` would have exited 1 there. Verified by restoring the
  old parser and watching it happen.

### Two things worth your attention

1. **I introduced a silent regression and caught it late.** v4's `NOT NULL
   order_id` turned `seed_demo`'s `INSERT OR IGNORE` into a no-op: zero
   settlements written, count of 400 returned, calibration mart quietly empty.
   The rule now in `lessons.md` is mechanical — when adding a `NOT NULL`, grep
   every `INSERT OR IGNORE INTO <table>` in the repo. I ran it; nothing else is
   affected.
2. **One disable-check stayed green and it was a real gap**, not a false alarm:
   `positions_awaiting_settlement` and the exposure query encode the same
   "which positions are open" rule, and only one had a test for the case v4
   exists for. Both covered now.

### Still open

- **The two boot lines are still unobserved.** They need a deploy; the flood
  that hid them is fixed.
- **No live instance has ever produced a surfaced row**, so the settlement pass
  will report `positions_open: 0` indefinitely and the fleet still costs
  nothing. Both are honest zeros, and both are now *printed* rather than
  inferred.
- **`ws.py` has still never opened a socket on live.** Unchanged.
- Exposure is fee-exclusive against a fee-inclusive cap (~2%). Re-costed while
  migrating and deliberately left open: adding a column is cheap, changing what
  `limit_price_tenths` means is not.
- Two things need Joe, neither urgent: **one combo price lookup**, and the
  **four fee-calibration trades**.

---

## HANDOFF (2026-08-08, evening — demo is deployed, live is one tap away)

**State:** 1,243 tests, ruff green, frontend builds, **pushed**, CI green on
every push. `main` is `883c8be`.

### THE ONE THING OUTSTANDING: deploy live

    ! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit

Everything below is already on **demo** and verified there. Live is still on
`a567ee7` and healthy. The Claude Code classifier blocks the live deploy from
this session (it allowed the demo one), so it needs a human or the browser.

**It carries the v2 → v3 migration.** Two nullable columns on `orders`
(`idempotency_key`, `response_body_json`) plus a unique index. Expect
`[migrate] ... migrated v2 -> v3` in the logs — unlike the previous deploy,
where the absence of migration output was correct.

After it lands, three things to confirm:
`agent_fleet_configured: true` on `/api/health` (the secret is already set on
Fly), the `migrated v2 -> v3` line, and an `API starting: instance_mode=live`
line.

### The canary caught a crash loop, which is the headline

The first demo deploy **failed**, at Verify, with a 502 that was not a cold
start. `scripts/migrate_db.py` read `_MIGRATIONS` in a shape it no longer had:

    TypeError: '_Migration' object is not iterable

`_MIGRATIONS` gained a dataclass so v3 could carry an index as well as columns;
every reader inside `backend/` was updated and the one in `scripts/` — the only
reader that runs at boot — was not. **Straight to live, that is a crash loop on
the volume holding the evidence record.**

`test_has_callers.py` already asserted the migration runs before uvicorn *and*
survives `.dockerignore`. Both true, and it still crash-looped: a boot step
covered by assertions *about* it rather than by running it. Nothing executed
the script. It runs in a test now, as a subprocess, exactly as the entrypoint
invokes it, against a database wound back one version — verified by restoring
the bug and watching it fail with the same TypeError.

### Verified on demo, so the same image is proven to boot

    [migrate] /data/demo.db already at schema v3
    INFO backend.api.routes: API starting: instance_mode=demo ...

That second line **answers the logging question** that had been open since the
morning: timestamp, level, logger name, through the root logger. The API
process configures logging. It was unanswerable from outside before, because
uvicorn runs `--no-access-log` and the hub only speaks when something changes —
so a healthy API and a mute one produced identical log streams. `create_app`
now says one thing at boot, which is what makes the stream readable at all.

**What demo still cannot prove:** its database is reseeded every boot, so it
was *created* at v3 and never ran the v2 → v3 transition. Live's volume is at
v2 with real rows and will be the first real execution of that path. Backed by
`test_each_single_step_runs_on_a_database_one_version_behind`, which was added
after noticing that every migration test built a **v1** database — so 1 → 3 was
covered as a sweep and 2 → 3, the only transition production makes, was not.

### Also landed

- **The agent fleet is wired.** `backend/agents/review.py`. Reviews before
  persisting, surfaced rows only, thread-based async seam. It blocked a real
  row on its first live API call. See the closed item in section 2.
- **Two taps are one order.** ADR 0009.
- **`Ops` has no default instance.** It defaulted to `demo`, so a dropped input
  succeeded against the wrong box — worse than failing. The run summary now
  names the app and cross-checks `/api/health`.
- **`agent_fleet_configured` on `/api/health`**, because an unconfigured fleet
  is silent by design and was otherwise indistinguishable from a working one.
- `ANTHROPIC_API_KEY` **is set on Fly** (live), inert until the deploy.

### The agent fleet is wired up

`backend/agents/review.py`. The pass collects, reviews the surfaced rows in one
batch, applies verdicts, then persists — so there is no window in which an
unreviewed row is orderable. Details in the closed item in section 2.

Two things the design note in this file got wrong, both of which would have
shipped green: `asyncio.run` at the seam raises inside a running loop, which is
where production always calls it from; and the test suite was making live
Anthropic calls on any machine with the key in `.env`, so the same test called
Claude locally and skipped the review in CI. Both in `tasks/lessons.md`.

**It blocked a real row on its first live run** — see the item for what it
caught and why that was a fixture bug rather than a venue finding.

### Two taps are one order

`docs/adr/0009`. The client mints an idempotency key when the ticket **opens**,
so a double-tap and a retry after a dropped connection carry the same one; the
endpoint replays the first attempt's recorded response instead of placing a
second order. Required, not optional — an optional key protects only the callers
that remember it.

Three layers, and the ADR sets out what each covers that the others cannot: the
step-0 read (survives a stale row), the check inside `reserve_order`'s write
lock (survives concurrent taps), and the unique index (survives a writer that
does not go through `reserve_order`). Disabling each one turns a different test
red, which is how they were checked.

**Building it found a defect that would have crash-looped the live instance.**
`init_db` applied `schema.sql` *before* migrating. That is fine for as long as
migrations only add columns, and it breaks the moment the schema file declares
an index over one — `executescript` runs against existing databases too, and the
column is not there yet. A **fresh** database gets it from `CREATE TABLE`, so
every test written against one passes. `init_db` migrates first now, and the
migration tests were generalised to cover every version and every table rather
than hardcoding v2 and `recommendations`.

Gap 2 of ADR 0008 was already closed last session; gap 3 (exposure fee-exclusive
against a fee-inclusive cap, ~2%) stands and is still not worth a migration.

### Not started: the paper settlement path

The remaining backend item, and the prerequisite for `max_exposure_dollars`
binding on anything before a live order exists. It needs a settlement source
from Kalshi and a decision about whether a dry run is assumed to have filled,
which is a measurement question rather than a plumbing one — assuming a fill at
the limit flatters the record, and the record is the product.

---

## HANDOFF (2026-08-08, 14:4xZ — the sheet is merged, and running it found four more)

**State:** 1,206 tests, ruff green, seven pushes, **CI green on every one**.
`lane/frontend-wip` is verified and merged; the branch can be deleted.

### Both instances are deployed, on `a567ee7`

**Demo first as a canary, then live** — the ordering that paid for itself last
time. Demo verified before live was triggered.

    demo  https://kalshi-cockpit-demo.fly.dev   five pages 200 over 20
                                                requests, no error text,
                                                instance_mode=demo,
                                                /api/orders -> 403 with and
                                                without a forged bearer
    live  https://kalshi-cockpit.fly.dev        five pages 307 -> /login,
                                                /api/orders 401 with and
                                                without a forged bearer

    {"status":"ok","instance_mode":"live","live_trading_enabled":false,
     "execution_available":false,"notifications_configured":true,
     "live_quotes_available":true}

**The ticket sheet was tapped on the deployed demo**, not only locally: opens
at 320 and 390, fits both, returns **403**, focus stays inside the dialog.

**No migration ran, and that was checked rather than hoped.** `SCHEMA_VERSION`
is 2, the volume was already at 2, and the only `schema.sql` change since the
previous deploy was comment text on two existing `orders` columns — verified
from the diff before triggering. The price grid is not persisted at all, so
ADR 0007 needed nothing from the volume.

**The live deploy failed once, correctly.** `confirm_live` arrived empty from
the GitHub mobile web form and the guard stopped the job at step 3, before
flyctl. That is the safeguard working and the failure mode `tasks/PHONE.md`
already records: the mobile form is unreliable for workflows with inputs. Use
`gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`.

**Still unobserved, and it needs the `Ops` workflow:** machine state, restart
count, and the log stream. Two things to look for in the logs, both of which
only production can show — that the migration was a **no-op**, and that
`backend.*` INFO lines now appear *at all*, which is the whole point of the
logging fix below.

### The lane is merged, and none of its defects were layout

The ticket sheet fit 320/390/430 on the first render. What was wrong was
behaviour, which is the argument for running a thing rather than reading it:

- **The focus trap opened at the moment the answer arrived.** Confirm unmounts
  when the response lands, focus falls to `<body>`, and the Tab handler only
  wraps from the first or last control *inside* the panel — so the next Tab
  walked into the page behind the veil.
- **A disabled Confirm named the wrong reason.** On an expired row it said
  "The token above is required", three paragraphs under its own note saying
  the consensus had aged out. Typing the token would have left the button
  exactly as dead. That is most rows, most of the day.
- **Close was a 59x26 target**, on a sheet whose docstring argues from thumbs.
- A **403** offered "Back", beside a sentence saying retrying will not help.

`scripts/check_ticket_sheet.py` is the new check and the reason all four were
found: it taps, waits out the entrance animation, measures, presses Confirm,
and measures the answer. `--fail-order` renders the offline state, which no
database can produce and is the only way to see the two-button action bar.

**Verified against three instances:** live with a locked gate (**423**, four
conditions), an expired-row instance, and demo (**403**). Also
`--fail-order` for the no-reply state.

### `check_mobile.py` could not see a whole class of defect, and now can

The Board read **"CONSENSUSKALSHI"** at 320px — a label needing 86px in a 69px
cell, painting over its neighbour. `grid-cols-3` is `repeat(3, minmax(0, 1fr))`
and the `0` lets a column shrink below its own content, so nothing overflowed:
same `scrollWidth` as a correct layout, same screenshot dimensions. The only
evidence was looking at the picture.

The script now also reports any leaf with visible overflow whose `scrollWidth`
exceeds its `clientWidth`. Across five pages and seven widths it found that
defect twice and nothing else. The card is two columns until `lg`, with the
edge spanning below — and the breakpoint is measured, not chosen: the Board
goes two-up at `sm`, so a card at 640px is *narrower* than one at 430px and
`sm:grid-cols-3` would have reintroduced it one breakpoint up.

### The deployed API process had no logging configuration at all

`docker/entrypoint.sh` runs `uvicorn backend.api.routes:create_app --factory`,
so `backend/main.py` — the only caller of `basicConfig` — has never run on a
deployed instance. Started that way, the root logger has no handler: **every
`backend.*` INFO record was discarded**, and what did come out went through
`lastResort` with no timestamp, level or logger name. The API is the process
that runs the quote hub, whose entire recent design is "a dead feed must be
visible".

The redaction filter added after a live credential reached a transcript was
therefore installed in the runner and not in the API. Nothing here puts a key
in a URL today, so what was lost was defence in depth rather than a key.

`create_app` calls `configure_logging()` now — the one seam every entry point
shares. Verified by disabling, and by re-running the exact entrypoint command.

### One observation, recorded rather than acted on

**`ws.py` has now been run in production shape**, which had not happened
before. Subscribing to a ticker the exchange does not recognise gets back a
snapshot carrying only `market_id` and `market_ticker` — no levels field on
either side — and the parser correctly raises rather than inventing an empty
book. What that does **not** settle is whether a real market with a genuinely
empty book looks the same. All 12 snapshots in the capture carry both sides
with levels, so the two cases are currently indistinguishable. One live
subscription to an illiquid real market would settle it, at zero odds credits.
Do not "fix" it by treating a missing key as an empty book — that is the
unreadable-resolves-to-zero failure the module exists to prevent.

### The exposure cap bounded each order and not the portfolio

`store.orders.reserve_order`. The endpoint read exposure on its read-only
handle, sized against it, then inserted on a different connection — so two
requests arriving together each sized as though the other did not exist. The
row and the cap check are now one transaction, with the check **after** the
insert, so the answer is a fact about the database rather than a prediction.

Two things worth carrying: the test is two real threads on two connections,
because `TestClient` never makes the hop and that is how the last concurrency
regression test in this repo passed against unfixed code; and **the docstring
I wrote first was wrong** — it credited `BEGIN IMMEDIATE`, and a deferred
`BEGIN` leaves the test green because the insert takes the write lock anyway.
What is load-bearing is the order of the two statements.

It still cannot fire in production. Dry runs consume none of the cap, which is
asserted as a test rather than left in prose.

### The README claimed the wire format was unverified

It has been verified since 2026-08-07, by the capture that found the parser
reading 0 of 257 frames. Three other numbers had drifted, and every one of
them understated the work. Also added: the demo link, the gate section, and
the two browser checks that cannot run in CI.

---

## HANDOFF (2026-08-08, overnight — three lanes, and CI was already red)

**State:** 1,201 tests, `dbt build` 11 nodes green, ruff green (newly wired),
tree clean, **pushed, and CI is green on all three jobs** — the first fully
green run in 37 pushes.

**Two tests turned out to be measurements of the environment**, both found in
the last hour and both now fixed: the demo seed contradicted itself between
10:00Z and 15:00Z (two sweeps five hours apart, a budget day rolling at
10:00Z), and an order-path assertion compared against the literal string
`odds 1800s old` while CI, being slower to build the fixture, produced
`1802s`. Neither was a flake to retry — the first was a real defect in the
demo, the second a test asserting machine speed. Both lessons are in
`tasks/lessons.md`; the general form is that a test depending on an input it
does not supply is measuring the environment, not the code. **Still not deployed** — the live instance is on the
image from before ADR 0007, so the next deploy carries the V2 order path, the
price-grid snap, and everything below. The order path is dry-run-only and the
gate is locked, so nothing here is urgent. **Deploying is your call; I did
not.**

Five things landed: the order record, the three CI follow-ups, the
`occurrence_datetime` measurement, a repair to CI that had to happen first,
and a cache breakpoint in the agent fleet that had never cached anything.

### Two lanes did not finish, and one has work worth keeping

Both were killed by a session limit mid-task, not by anything they hit.

- **`lane/frontend-wip` — the ticket bottom sheet, committed but NOT merged.**
  `TicketSheet.tsx` (962 lines), `TicketProvider.tsx`, and changes to
  `page.tsx` / `LiveBoard.tsx` / `lib/api.ts`. It died while running
  `check_mobile.py`, so **nothing has been rendered, measured at 320/390/430,
  or tapped against a locked gate** — and the gate refusal is the state this
  component will actually be in. Committed only so a worktree cleanup cannot
  delete it. Finish the verification before merging.
- **README** — nothing committed. Start it over.

### The agent fleet's prompt cache was a no-op

`agents/base.py` marked `HOUSE_CONTEXT` with `cache_control`, behind a comment
calling the savings "the whole reason to cache". Measured against
`claude-opus-5`: the block is **401 tokens** and the minimum cacheable prefix
is **512**. It had never produced an entry — no error, no warning,
`cache_creation_input_tokens: 0`.

Breakpoint moved to the last system block (738–985 tokens per agent).
`scripts/measure_agent_cache_prefix.py` re-measures and exits non-zero if any
agent falls under. It exists because the minimum is model-specific and **not
monotonic** — 512 on Claude Opus 5, 1024 on Opus 4.8, 4096 on Opus 4.6 — so
pointing `AGENT_MODEL` at an older model turns the cache off silently.

**The module is still called by nothing.** This fixes a path that has never
run. Wiring the fleet up is still open and is the largest thing left in
section 2 — see the note under that item for the design I did not build.

### Read this first — the secret scan was red on `main` and nobody had pushed

The `quoted` pattern added two commits earlier matches a quote followed by a PEM
header ending the line. `tasks/lessons.md` documents that exact case **by
reproducing it**, in a fenced code block. So the repair for a false negative
shipped a false positive onto the file explaining the false negative — third
consecutive turn of the same screw on one check.

The quote was never the distinguishing feature. **The next line is.** A quoted
header followed by a fence is a mention; one followed by forty characters of
base64 is a key. That one case is now two lines of awk, no path exclusion was
added, and `tasks/lessons.md` joins the two files asserted to stay clean —
because prose about leaked keys is a genuinely plausible place for one to be
pasted, and excluding it would make the most likely accident the least visible.

Verified by extracting the step and running it: clean tree 0, five planted
shapes each 1, both negatives 0.

### `orders` rows are written — and the framing in this file was wrong

`docs/adr/0008`. The item said the point was to give `max_exposure_dollars`
something to read. **It does not do that**, and that is worth saying plainly:
every order the running system places is a dry run, dry runs commit nothing, so
the cap still does not bind in production. It begins binding the day a live
order exists.

Counting paper orders instead would make it bind and would be worse — nothing
settles a paper position, so paper exposure could only ratchet up until the
endpoint refused everything with no way to release it. **A paper settlement path
is the prerequisite, not a change to the exposure query.**

What the change is actually for is the other two reasons, and the first is the
serious one:

- **`client_order_id` existed only in memory.** It is the idempotency key, and
  the failure it exists for is a POST that times out *after* Kalshi accepted it.
  Recording after the response loses the key in exactly that case. The row now
  goes in as `pending` **before** the request; a failed write refuses the order,
  a failed *outcome* write does not unwind it and is reported instead.
- **CLV and the fill priced different numbers.** `orders.recommendation_id` is
  the join that did not exist.

**And it surfaced two implementations of exposure.** `runner.py` summed `fills`
net of `settlements`, the endpoint summed live `orders`. Both had been on the
money path for the project's life and both returned `0.0` every time, so they
had never disagreed — and they answer different questions, so they would have
the moment a row was written. One deleted. `orders` wins: a resting order is
committed capital, and counting fills alone lets a hundred resting orders each
size against zero.

The surviving query enumerates the **terminal** statuses instead of the live
ones. The old list dropped `partially_filled` and `unrecognised_response` — the
status this project invented so an unreadable response could not be mistaken for
anything, valued at zero dollars by an allow-list.

13 guards verified by disabling. One stayed green: `PRAGMA busy_timeout = 5000`
is exactly CPython's own default, so the line was a literal no-op. Now an
explicit `timeout=` on `connect`, because there are two writer processes and the
value should be one we chose.

### `occurrence_datetime` is a shifted start. Story B is refuted

The open question in section 3 is closed, at zero odds credits.
`scripts/measure_occurrence_datetime.py`, capture in
`tests/fixtures/occurrence_datetime_probe.json`, full write-up was in
`tasks/inbox/research.md`.

The discriminator is a period series: an F5 market and a game market on the same
game must agree if the field is a start and differ by the period if it is an
end. Across 15 series pairs, **not one period market is earlier than its game
market**; 13 identical, 2 later. On one MLB game, nine market types — including
`KXMLBRFI` (resolves ~20 min in) and `KXMLBEXTRAS` (resolves at the end or
later) — carry the identical value, exactly +3.00h from the first pitch written
in words in each market's own `rules_primary`. Markets expiring hours apart
cannot share an expiry.

I re-derived the +3.00h from the committed capture myself rather than taking the
agent's word for it. Note the persisted evidence is thinner than the headline:
the fixture holds 15 period pairs and one anchored game, while the agent
measured 171 pairs and 189 fixtures live. The script re-derives the rest against
a free endpoint.

**Consequence for the code: change nothing.** The offset is not
game-length-dependent, so the fixed 4h tolerance in `match.linker` and
`core.suppression` is correct — that was the worry and the answer is no. But
`KXMLBF5` sits at **+5h** while `KXMLBF5SPREAD`, covering the identical five
innings, sits at +3h, so the extra two hours are per-series data entry. Nothing
in scope prices a period series today; the day one is priced, a 4h tolerance
drops every `KXMLBF5` market silently. Filed in section 2.

### CI follow-ups: all three done, one unverifiable until pushed

- `.gitignore` was missing `.p12` **and** `.pkcs8`; CI refused both.
- **ruff is wired, not dropped.** Its current default selects 413 rules and
  finds 513 violations here, which would have been red on the first push — the
  exact failure just removed. Selected `E4,E7,E9,F` (59 rules), excluded the 4
  codes accounting for all 32 findings, 55 rules active, **0** findings.
  Verified by planting an `F821` and watching it exit 1.
- Actions bumped off the retiring Node runtime: `checkout@v7`,
  `setup-python@v7`, `setup-node@v7`, `gitleaks-action@v3`, each confirmed by
  reading `action.yml` at that tag rather than guessing. **An Action cannot run
  locally, so this one is unverified until the first push** — watch that all
  four jobs still start.

Wiring ruff immediately caught eight F811s in the new test file: importing a
fixture by name makes every signature that takes it a redefinition. Split into
`build_armed_db` rather than silenced.

### What is still open, and what is new

The three gaps recorded in ADR 0008, all of which become real the day the gate
opens and none of which are worth building against an untestable live path now:
~~**placement is not idempotent**~~ (**done 2026-08-08, ADR 0009** — and the
"untestable" framing was wrong: the replay path never touches Kalshi, and
building it found a migration-ordering defect that would have crash-looped the
live instance), ~~**two concurrent requests can size against one exposure
reading**~~ (**done 2026-08-08**, `reserve_order`), and **exposure is
fee-exclusive while the cap is spent fee-inclusive** (~2%) — still open, still
not worth a migration.

---

## HANDOFF (2026-08-08, 05:2xZ — deployed, and the demo found the bug for us)

**Both instances are on the new image.** Demo verified, live verified, live
machine `started`, checks 1/1, **restarts 0**, volume attached.

    demo  https://kalshi-cockpit-demo.fly.dev   five pages 200, no error text,
                                                instance_mode=demo, forged
                                                bearer on /api/orders -> 403
    live  https://kalshi-cockpit.fly.dev        five pages 307 -> /login,
                                                /api/orders 401 with and
                                                without a forged bearer

    {"status":"ok","instance_mode":"live","live_trading_enabled":false,
     "execution_available":false,"notifications_configured":true,
     "live_quotes_available":true}

**The migration ran.** `unchanged_confirmed: 50` on the first pass is a v2
column doing its job, so the schema change reached the volume before uvicorn
opened it.

### The two-step deploy paid for itself on its first use

The demo crash-looped: `can't open file '/app/scripts/migrate_db.py'`, exit 2
under `set -e`, ten restarts, machine gone. `.dockerignore` denies `scripts/*`
and allowlists by hand; the allowlist named `run_loop.py` and nothing else,
because it was written when the entrypoint ran one script. **Live would have
taken the same crash loop on the volume holding the only copy of the record.**

`TestTheEntrypointRunsWhatItMustRunFirst` asserted the migration runs before
uvicorn and passed throughout — it was true, and the file it named was not in
the image. The allowlist is now derived from the entrypoint rather than
maintained by hand. See `tasks/lessons.md`.

**Also fixed before the live deploy: the diagnostic you were told to watch was
counting the wrong population.** `observe_pass_duration` ran on every pass and
always compared against the *fast* interval, so the first full pass — 167
events, 1,426 markets, 228 rows joined, 14.9s, healthy, window closed — raised
`passes_over_quote_budget`. Full passes happen every 900s forever, so that
counter would have been ~96 routine entries a day and could never have shown
the one condition it exists for. `kind` is now a required argument and full
passes get their own counter.

### Read this before believing the ticker is verified

**`ws.py` still has not opened a socket in production.** `live_quotes_available:
true` says the hub *loop* is running, which is exactly what it was changed to
mean — but `_one_cycle` returns early with `{"type": "idle"}` when no row is
bettable, and with `surfaced: 0` and the odds budget spent there have been no
bettable rows. So no WebSocket has been opened on the live instance, and the
things you asked me to watch for — reconnect loops, memory growth on a 1GB
machine — **cannot be observed yet.** They become observable the first time a
window opens with a surfaced row, not before.

### The gate's population — reported, not yet decided

Done as you specified: **both groups side by side, with `n` for each, before
anyone changes which one the floor counts.** `gate.clv_by_population` returns
`actionable` / `no_edge` / `suppressed` / `pooled`, the three matching the
digest's own framing so the two screens cannot describe the record differently.
The gate's `scored_recommendations` detail now carries
`actionable Ng/Nr, no_edge Ng/Nr, suppressed Ng/Nr` beside the aggregate, and
when nothing actionable has been scored it says so outright.

**The digest had the same defect and it is the one that reaches your phone.**
`_digest_stats` ran its own SQL with a comment saying it counted "the way the
gate counts it" — true, and the gate's way was the mixture. It now calls
`clv_by_population` rather than agreeing with it, per the repo's rule about
deleting one of two paths. The Discord embed reports the actionable count as
the headline with the pooled count beside it and the gap named.

Fixing it surfaced a fixture that could not have been real: a test set
`clv_tenths` without `clv_scored_ms`, which the digest's looser predicate
accepted and `score_recommendations` can never produce — it writes both in one
UPDATE.

**Decided (you said "decide for me"): the floor counts `actionable`.** Both CLV
conditions now read that population. `docs/adr/0005-the-gate-counts-actionable-
games.md` has the full reasoning; the short version is that it is a *safety*
change, not a relabelling — a systematic CLV among refused rows moves the
pooled mean rather than blunting it, and `suspicious_edge` rows are the
likeliest carriers, so pooled they could arm real money on evidence about bets
the strategy declines to make. It also moves the gate strictly further away in
both conditions: the actionable set is a subset, so the floor is harder to
reach, and `always_valid_multiplier` *grows* as `n` shrinks (9.84 at n=20
against 3.66 at n=300), so a small actionable sample clears a taller bar. A
money guard that changes should change in that direction.

It reads **0 of 300** and will for a while. The breakdown sits beside it.

**And it caught a test fixture arming the gate from refused rows.**
`test_quote_refresh.armed_db` built 400 scored games at
`suggested_contracts=0` — "no edge here", four hundred times — and that
satisfied the floor, so every order-path test below it ran through a gate
opened by evidence the strategy would never have acted on. A gate fixture has
to be built from the population the gate counts.

### What to look at, and when

The budget day rolls at **10:00Z**. Until then no sweep can fire (`24 of 16
credits spent since 10:00Z`), so the window stays closed, no quote passes run,
and `surfaced: 0` means nothing at all. After the first sweep of the new day:

- `surfaced` — this is the first time the sentence "still 0 after a full window
  with the fast cadence running is the honest no-edge result" can be true.
- `passes_over_quote_budget` — now genuinely means the fast cadence is failing.
  `full_passes_over_limit_in_window` is the structural one and is expected to
  be nonzero, roughly once per window.
- The socket. First time `ws.py` runs for real.

**One number to keep an eye on that nobody has flagged yet:** the CLV pass
joined 228 rows and scored **0**, all of them `skipped_entry_after_close`. That
is the documented cost of requiring the entry to precede the close, and the
earlier run had 34 scored, so the scored rows are simply not re-joined — but
228/228 skipped is worth a second look if it does not move once games settle.

---

## Joe's asks, 2026-08-08 — four of them; two are done

Raised in chat while the quote-refresh work was landing.

1. **~~Stream the prices. Make the Board a ticker.~~ — done.** *"I'm thinking
   about this like a stock ticker. Billy Walters would like it."* And the
   sharper version: *"it seems like you're doing a lot to manage prices at their
   very small window snapshot, so wouldn't it just be easier to stream the
   prices in?"*

   He was right about the Kalshi half. `backend/live.py` is the hub, and
   **`backend/kalshi/ws.py` finally has a caller** — it was the fifth module in
   this project to be complete, tested and invoked by nothing. Verified against
   the live exchange: real book state for `KXNCAAFGAME-26SEP19MSUND-ND` arrived
   over the socket and out through SSE, and the depth it reported (640.95 at the
   yes ask) matches `yes_ask_size_fp` from the REST capture — an independent
   confirmation of the crossover.

   What it does **not** do, and this is the part to keep saying out loud:

   - **It does not widen the actionable window.** The fair value comes from a
     devigged sportsbook consensus at ~16 credits a day, 6 a sweep. Streaming
     Kalshi gives a live ask against a fair value up to fifteen minutes old.
     The window is an odds-budget fact and no amount of Kalshi streaming
     touches it. The banner and the feed header both say so.
   - **It does not replace the order-time refresh.** A browser's price is a
     client-supplied price and the server must never trust one. `POST
     /api/orders` re-reads the book itself; streaming means the two usually
     agree.
   - **The browser is given no arithmetic.** Edge and size are recomputed *on
     the server* by the same functions the order endpoint calls. Shipping the
     fee curve to TypeScript so the client could subtract it would put two
     implementations of a money calculation one refresh apart.
   - **A stopped ticker must look stopped.** Heartbeat every 10s regardless,
     `down` pushed the instant the feed dies and repeated on every heartbeat,
     and a client-side timer that treats total silence as a fault.

   **Verified end to end**, including the thing most likely to be silently
   broken: SSE survives Next's `/api/*` rewrite unbuffered — frames arrive
   exactly one heartbeat apart through the proxy, not in bursts.

   Two things left on it, neither blocking:
   - The hub prices against `exposure = 0` rather than reading the portfolio per
     frame. Display-only, and the order endpoint applies the real exposure, but
     the size on a card can therefore exceed what the server would accept once
     fills are persisted.
   - On a market with no book activity the cards keep their recorded prices
     until the first frame arrives. Correct, and it means "LIVE" can sit above
     a recorded price for a few seconds after a restart.

2. **~~A Kalshi-platform specialist agent~~ — done, and it earned its keep
   immediately.** `.claude/agents/kalshi-platform.md`. *"so that agent can check
   against everything we're doing to make sure everything is copacetic."*

   Pointed at the quote-refresh commit it found a defect I had introduced and
   two more besides — see the handoff below. It needs a session restart to
   register as a subagent type; until then it can be run by handing the file to
   a general-purpose agent.

3. **Is in-play betting viable?** See the item in section 3 — it is the largest
   of the four and the one with a real chance of a "no". Note that the order
   path now **refuses a started game** (added in response to finding 1 below),
   so nothing can leak into the record while the question is open.

4. **Is Python the right language everywhere?** *"if some other code language
   base works better in some places use that instead — Rust, C++, whatever."*
   Worth answering with a measurement rather than an opinion, and the repo's own
   rule applies: measure the style rule before believing it. The starting
   position, to be checked rather than assumed:

   - Nothing here has been shown to be compute-bound. The devig solvers, the
     copula, Elo — all microseconds on a ~100-game slate. The analytical half
     already runs in C++ via DuckDB.
   - The measured costs are network and budget: Kalshi REST round trips, a
     ~500ms `httpx.AsyncClient` construction (fixed by sharing it, not by
     rewriting), and 16 odds credits a day.
   - The one place latency genuinely decides money is stale-quote picking at
     ~400ms — and `tasks/lessons.md` records that as measured and refuted. It
     is a co-location problem, not a language problem.

   So the honest task is: `took_s` is already logged per pass; instrument the
   stages inside it, find where the wall clock actually goes, and only then
   consider rewriting a specific stage. A finding of "nothing is
   compute-bound" is a real answer and should be written down as an ADR so it
   is not re-litigated.

---

## HANDOFF (2026-08-08, later still — the price is live, and a review caught me)

**State:** 1,064 tests, frontend builds, all five pages fit 320/390px, Board and
ticker verified by rendering them against the live exchange. **Not deployed** —
the earlier migration has not shipped either, so the next deploy carries both.

Three things landed: the order-time quote refresh, the streaming ticker, and the
fixes from the Kalshi-platform review of the first one.

### The review found a defect I introduced, and it was the repo's own first rule

**Re-sizing at the live ask is one-sided.** An adverse move shrinks the order to
zero and refuses; a *favourable* move just buys more, up to what the engine
authorised. `size_position` is monotonic in price, so the re-derivation had a
refusal branch in one direction and none in the other — and the direction with
none is the one *"a large apparent edge is a bug until proven otherwise"* exists
for. An ask that fell six cents since the row was written is not six cents of
found money.

Fixed: `suppression.edge_ceiling_tenths` now runs at order time against the live
edge, using the engine's own config rather than a second constant.

**And the runner's in-play drop only covers rows it has not written yet.** A row
recorded ten minutes before kickoff keeps its size and stays inside the 900s
odds window well into the first quarter — and the refresh makes that worse, not
better, because the ask becomes a live in-play price while the fair value beside
it is a pre-game consensus. Measured in-play edges ran −200 to +68 tenths.
`recommendation_freshness` now carries the **sportsbook's** kickoff (joined
through `link_id`, never `kalshi_events.commence_ms`, which runs three hours
late) and the order path refuses a started game.

Three smaller ones, all from the same review:

- **Kalshi sends `"0.0000"`, not a missing field**, so the `live_ask is None`
  branch could never fire on a real one-sided book and the refusal that reached
  the screen said *"the price moved. Recorded 45c, live 100c"*. Now
  `is_valid_price`, with a message about there being no offer.
- The depth refusal claimed a fill guarantee the order does not have — plain GTC
  limit, no `time_in_force`, no cancel path anywhere in the repo. Reworded, and
  the thinness is logged.
- A 404 for an unknown ticker was served as 503, telling whoever is holding the
  phone to retry something that will never work.

**Still open from that review, recorded rather than fixed:**

- **The CLV price and the fill price are now different numbers.** CLV scores off
  `entry_ask_tenths`; the order goes out at the live ask. Nothing joins them
  because `orders` is still never written. The gate that arms real money is
  built entirely on CLV, so its evidence base and its executed bets would
  describe different prices. This is an argument for persisting orders *before*
  anything is armed, not after.
- **`_current_exposure_dollars` always returns `0.0`** for the same reason, so
  `max_exposure_dollars` does not currently bind in production even though it
  binds in the tests.
- One assumption still strictly unverified: no fixture ties `yes_ask_size_fp` to
  an orderbook NO-bid quantity *directly*. One call closes it —
  `GET /markets/{ticker}/orderbook`, compare the NO side's quantity against
  `yes_ask_size_fp`.

### Found while deciding whether to deploy — fixed, and it was the same shape

The hub's loop had no `except` around it, and `_load_subscriptions` opens the
database. `open_db` refuses an unrecognised schema version, **which is exactly
the state on the first boot after this deploy's migration** if the API comes up
before the runner has migrated. The task would have died, nothing would have
restarted it, and `/api/health` would have gone on reporting the ticker
available — because that checked `hub is not None`, a claim about construction.

A dead hub still answers `/api/stream/quotes` with snapshots and heartbeats,
both empty, which renders as a quiet market. That is the exact failure a ticker
introduces and the one the heartbeat exists to prevent, arriving through the
door nobody was watching.

Now: the cycle is wrapped, the failure is broadcast as `down` rather than only
logged, the loop retries, and health reports `is_running`.

### What to look at once it is live

- `live_quotes_available` on `/api/health` says whether the ticker is running —
  the loop, not the object. If it is `false` on the live instance, the hub died
  and the log has the reason.
- The feed header on the Board: `LIVE`, `FEED DOWN`, `FEED SILENT`, `NO LIVE
  ROWS`. `NO LIVE ROWS` is the expected state for most of the day.
- ~~**The rewrite destination is read at Next's start, not at build**~~ —
  **wrong, corrected 2026-08-08.** It is read at **build**. `next build`
  evaluates `next.config.ts` and freezes the result into
  `.next/routes-manifest.json`:
  `"destination": "http://127.0.0.1:8000/api/:path*"`. Setting `API_ORIGIN` at
  runtime does not move it.
  **`API_ORIGIN` is read in two places at two different times**, which is the
  part that bites: `next.config.ts` (build, the browser's `/api/*` proxy) and
  `lib/api.ts` `BASE` (runtime, server-component fetches). Set it at runtime
  and the two halves point at *different backends* — server components render
  from one and the browser's POST goes to the other. Caught by exactly that:
  a demo instance's ticket reported `401 Not authorised` while the demo
  backend's own answer, one curl away, was `403 This is the demo instance`.
  The image is correct by coincidence — the Dockerfile's runtime
  `API_ORIGIN` is the same value as the build-time default, and both
  processes share a host. The conclusion stands and the mechanism was wrong;
  the danger is that the wrong mechanism suggests a fix that silently does
  nothing. To point the proxy elsewhere you must **rebuild**.

---

## HANDOFF (2026-08-08, earlier — the 30-second window is fixed)

**State:** 998 tests, `dbt build` 11 nodes green, frontend builds, all five
pages fit 320/390px. **Not yet deployed** — see "Deploying this" below, because
this one carries a schema migration and the boot order matters.

### What changed

The previous handoff's item 1 — *"the window is 30 seconds, not 15 minutes"* —
is done, by the two fixes it proposed as composing. They do compose, and neither
works alone.

**1. A second cadence.** `backend/runner.run_quote_pass` re-reads Kalshi,
re-prices against the odds already stored, and spends nothing. The loop now runs
a **full pass every 900s** and a **quote pass every 15s while the window is
open** (`backend/scheduler.Tempo`). Kalshi REST is unmetered; the 900s interval
was The Odds API's limit applied to a leg that never needed it.

**2. `last_confirmed_ms`.** A quote pass that re-derives an identical decision
stamps the existing row instead of writing a duplicate, so `persist_if_changed`
keeps the record clean *and* freshness stops measuring from `created_ms`. Three
new columns, all nullable: the instant, and **both** ages at that instant.

Measured on a simulated 930 seconds of passes (61 quote, 1 full) against a real
database with fake clients:

    recommendation rows      4        (not 248 — the dedupe still holds)
    confirmed                4/4
    quote age at the end     0.0s     (limit 30s)
    odds age at the end      1354s    (limit 900s — correctly expired)

That last line is the point as much as the others. **This does not widen the
window.** Fifteen minutes twice a day is `MAX_ODDS_AGE_S` and the credit budget,
and no amount of Kalshi polling changes it. What changes is that the fifteen
minutes are now usable throughout rather than for the first thirty seconds —
about 30 min/day of actionability instead of about 1.

Item 3 from the last handoff — **refresh the quote at order time** — is still
open and is still the real fix for execution. It closes the gap between "this
row was true 15 seconds ago" and "this row is true now", which confirmation
narrows and cannot close.

### Deploying this

**The migration must run before uvicorn.** `docker/entrypoint.sh` now does that
(`scripts/migrate_db.py`), and a test asserts the ordering. The reason it
matters: the API opens read-only and `open_db` refuses an unrecognised schema
version, so on the first boot after this change the live instance would 500 on
every page until the runner happened to call `init_db` — while `/api/health`
stayed green throughout, because it touches no database.

Verified against a synthetic v1 database with 128 rows: refused before, migrated
v1 → v2, 128 rows kept, all three columns present, second run a no-op.

`RUNNER_FAST_INTERVAL_S` defaults to 15. Do not raise it past 18 and do not
raise `MAX_KALSHI_QUOTE_AGE_S` — the loop refuses to start if the composed
worst-case gap exceeds the limit, and 30s is the right number for a venue quoted
by sub-200ms market makers.

### What to look at once it is live

- `pass` and `took_s` are now on every loop log line. If `took_s` on a quote
  pass approaches 8s the fast cadence stops keeping rows inside the limit;
  `Tempo.observe_pass_duration` logs a warning and counts it as
  `passes_over_quote_budget`.
- **`surfaced` should stop being structurally zero during a window.** It has
  always been 0, and part of that was that nothing could survive 30 seconds. If
  it is still 0 after a full window with the fast cadence running, that is the
  honest no-edge result rather than an artefact — which is the first time that
  sentence has been true.

---

## HANDOFF (2026-08-08, earlier)

**State:** 935 tests, `dbt build` 11 nodes green, **both instances deployed and
verified**. The four items from the last handoff are done — sweep timing, the
window on the Board, Discord wiring, and the scored-ratio investigation, which
turned up a defect rather than a transient.

First live pass on the new image:

    dropped_game_started: 9          the in-play guard firing on real data
    clv_scored: 34                   up from 8 at the start of the session
    sweep decision: no sweep -- 24 of 16 credits spent since 10:00Z

The odds budget for today was already spent by the old scheduler (plus 6 on a
local smoke test), so **the first sweep the new timing chooses will be after
10:00Z on the 8th.** That is the thing to look at first: whether it lands
20–45 minutes before a cluster of kickoffs rather than wherever the process
restarted.

`clv_scored` answers the last handoff's item 4. The 100%-unscoreable reading was
a transient: closing lines only exist for games that have started, so early in a
run every joined row is a late one. 34 rows are now scored and the count is
climbing.

  demo  https://kalshi-cockpit-demo.fly.dev   (public, no credentials)
  live  https://kalshi-cockpit.fly.dev        (login: APP_AUTH_TOKEN)

### ~~Pick this up first — the window is 30 seconds, not 15 minutes~~

**Done 2026-08-08.** Fixes 1 and 2 below are both implemented; see the handoff
at the top of this file. Fix 3 — refresh the quote at order time — is still
open. The original write-up is kept because it is the clearest statement of the
problem.

The premise of the last handoff was wrong and the fix exposed it. **Two limits
bound the actionable window and the tighter one decides it:**

    MAX_ODDS_AGE_S         900   the sportsbook consensus
    MAX_KALSHI_QUOTE_AGE_S  30   the price you would actually pay
    loop interval          900   how often a row is written

A row is bettable for **thirty seconds after each pass**, then the server
refuses it. Two sweeps a day, so the tool is actionable for about a minute a
day, not half an hour. Every document in this repo said fifteen minutes,
including this one. The Board now states it rather than hiding it — expired rows
are struck through and labelled — but stating a problem is not fixing it.

Three candidate fixes, cheapest first. They compose; the first two together are
probably enough.

1. **Poll Kalshi fast while the window is open.** Kalshi REST is unmetered — the
   15-minute interval exists for the odds budget alone. A short pass (Kalshi
   quotes + re-price only, no sweep) every ~20s during the ~15 minutes after a
   sweep would cost nothing and keep a row inside its 30s limit for the whole
   window. `run_ingest_pass` already separates the odds leg, so this is mostly
   scheduler work.
2. **An unchanged row goes stale even though the market has not moved.**
   `persist_if_changed` deliberately does not rewrite a row whose ask and fair
   are unchanged — correct for the record, wrong for freshness, because
   `recommendation_freshness` measures from `created_ms`. A `last_confirmed_ms`
   column, updated on every pass that re-derives the same numbers, separates
   "this observation is old" from "this price is old". Needs a schema column and
   a change in `gate.recommendation_freshness`; the record semantics do not
   change.
3. **Refresh the quote at order time.** The real fix for execution, and the
   biggest: the ticket sheet reads a live Kalshi quote before confirming. Also
   closes the "the price moved between recording and ordering" gap that (2)
   leaves open.

Do not raise `MAX_KALSHI_QUOTE_AGE_S`. 30s is the correct number for a venue
quoted by sub-200ms market makers; the poll rate is what is wrong.

### And read this before touching the gate

The first live Discord digest (2026-08-08 02:39Z, one budget day) says:

    Surfaced 0   Suppressed 319   No edge 201   Scored on CLV 16 / 300

    stale_odds                                × 196
    stale_odds,suspicious_edge                ×  66
    stale_odds,too_few_books,no_market_width  ×  16
    too_few_books,no_market_width             ×  11

**`stale_odds` is on 278 of 319 suppressions — 87%.** `tasks/lessons.md` already
has the rule this breaks: *"before adding something to a rejection log, ask what
fraction of inputs will trigger it. If the answer is 'most of them', it is a
state, not an exception, and logging it as an exception destroys the log's value
as a diagnostic."* That has now happened. The suppression summary is one code
and a long tail, so it can no longer surface a miscalibrated rule — which is the
only reason it exists. Stale odds are the *normal* condition for 23.5 hours a
day; they are a state.

**And the gate is counting the wrong population.** `clustered_clv` pools every
row with a `clv_tenths`, with no filter on `suppressed_reason` or
`suggested_contracts`. So "16 / 300" is 16 games of CLV drawn overwhelmingly
from rows the strategy explicitly *rejected*. That measures the closing-line
behaviour of "any Kalshi market we happened to poll", not of this strategy.

The dilution is conservative — it drags a real edge toward zero rather than
inventing one — so nothing unsafe has happened. It is still the wrong number
under a label that says "our edge", and the 66 `suspicious_edge` rows are
exactly the population most likely to carry a *systematic* CLV in one direction,
which would move the pooled mean rather than merely blunt it. The repo's own
rule: **a pooled number is not a finding until the parts agree, and the
per-group view goes beside every aggregate.**

The sharp version, and the reason this is item 2 rather than item 5: **rows
become eligible only when they are actionable, and nothing has been actionable
yet.** Surfaced is 0 and has always been 0. So the two findings are one finding
— the 30-second window starves the only population the gate should be measuring,
while the counter reads 16 because it is counting a different one. Fixing the
window is what makes the gate's number mean anything.

Do not simply add `WHERE suggested_contracts > 0`. That is the correct
population and it is currently empty, so the gate would read 0/300 forever and
the change would look like a regression. Report both groups first —
actionable and rejected, side by side, with n for each — then decide which one
the floor counts.

### Then

- [x] ~~**Turn on Discord**~~ — **done 2026-08-08 02:41Z.** `DISCORD_WEBHOOK_URL`
  is a repo secret and a Fly secret; live reports
  `notifications_configured: true`; the workflow posted a real message and
  Discord replied 204. `tasks/PHONE.md` item 4 has the steps if it ever needs
  redoing — and note the GitHub mobile *app* is unreliable for workflows with
  inputs, so use the browser URL or ask me.
  **The bug that made this necessary:** the code read
  `DISCORD_BOT_TOKEN`/`DISCORD_CHANNEL_ID` while `PHONE.md` had said
  `DISCORD_WEBHOOK_URL` since it was written, so following the documented phone
  path would have configured nothing and reported nothing wrong.

- **Watch the first scheduled sweep**, some time after 10:00Z on the 8th. The
  log line to look for is `sweep decision: <sport> (scheduled): N game(s) from
  HH:MMZ, sweeping 45-15 min before first kickoff`. A `bootstrap` trigger there
  would mean no sportsbook fixtures were stored, which is a different problem.
- **Decide what to do with the in-play rows already in the live record.** They
  cannot be scored and they inflate the Ledger and the suppression summary.
  Deleting rows from the live evidence database is your call, not mine.

### What changed this session

- `backend/odds/timing.py` — clusters the day's kickoffs, scores each cluster by
  games covered, and fires a sweep only in a 30-minute window before one.
  Anchored on the **sportsbook's** kickoff; Kalshi's runs 3h late. Budget day
  rolls at 10:00Z, not UTC midnight. `plan_sweep` deleted, not left beside it.
- `/api/window` + `WindowBanner` — open/closed, time left, next sweep and why,
  credits left. Same planner as the runner, not a second implementation.
- `/api/board` splits `surfaced` from `expired`, recomputing both ages with the
  arithmetic the order endpoint uses.
- `backend/notify/alerts.py` — the caller `discord.py` never had. Dedupe lives
  in a `notifications` table so a restart cannot re-announce the slate.
- `runner` drops fixtures whose game has started. 36 of 104 rows on a live pass
  were in-play, with edges spanning −200 to +68 tenths against −39 to −18 for
  the pre-game rows on the same slate.
- `tests/test_has_callers.py` — the orphaned-code grep from `lessons.md`, run by
  CI and parsed with `ast` rather than matched as text.

### Running this in parallel

`docs/adr/0003-parallel-sessions-and-subagents.md` defines the file-ownership
lanes, the three integrator-only documents, and the shared state that no VCS
will protect — the odds budget (~16 credits/day, 6 a sweep), deploys, `data/`,
and the live instance. Workers use `Agent(isolation: "worktree")` and write
findings to `tasks/inbox/<lane>.md`.

**One addition, learned the hard way:** running `scripts/run_loop.py` locally
spends from the same monthly odds quota as the live instance, and neither
instance's `api_credits` table can see the other's. One local smoke test cost 6
of ~500 monthly credits. Reconciliation against `x-requests-remaining` catches
the drift after the fact; nothing prevents it.

### Still waiting on the user (both pre-authorised)

- **Fee-calibration trades** — four minimum-size orders at ~10c/30c/50c/80c in
  the Kalshi app. Clears a gate condition and retires the conservative fee hedge
  that suppresses essentially every longshot.
- **One combo price lookup** — `POST .../lookup`, no money, yields a measured
  same-game correlation.

---


Tick these off as you go. `tasks/todo.md` is the build log; this is the
actionable list.

State as of 2026-08-07: **653 tests passing**, `dbt build` green (10 nodes),
Docker image builds, cockpit renders clean at 320/390/430px, live WebSocket
verified against real markets.

---

## 1. Blocked on you

Four things I can't do without you. Each is a few minutes.
**All four are doable from your phone — see `tasks/PHONE.md` for the exact
taps.** Deployment used to need a laptop because `flyctl` has no mobile
client; `.github/workflows/deploy.yml` now runs it from a GitHub "Run workflow"
button.

- [x] ~~**Deploy the demo instance to Fly**~~ — **done 2026-08-07.**
      **https://kalshi-cockpit-demo.fly.dev** — one machine in `ord`, scales to
      zero, no credentials, no execution path. Deployed via the `Deploy`
      workflow (`gh workflow run Deploy -f instance=demo`); `FLY_API_TOKEN` is
      set as a repo secret. Verified: all five pages 200 with no error text over
      20 consecutive requests, `/api/health` reports `instance_mode=demo`, and
      `POST /api/orders` with a forged bearer answers **403**.
      **The first deploy was broken and looked fine.** It served "Backend
      unreachable" on 9 of 15 requests while `/api/health` stayed green — the
      API's SQLite connection was thread-bound and FastAPI runs the sync
      dependency and the sync endpoint on different threadpool workers. 758
      local tests and a local container run all missed it, because an idle
      threadpool reuses one worker. See `tasks/lessons.md`.
      Added `.github/workflows/ops.yml` (read-only `logs`/`status`/`machines`)
      because there was otherwise no way to read the deployed instance's logs —
      `flyctl` has no mobile client and needs a token nobody holds locally.
- [x] ~~**Deploy the live instance**~~ — **done 2026-08-07.**
      **https://kalshi-cockpit.fly.dev** — 1GB machine in `ord`, volume
      `cockpit_data`, never scales to zero. Gate verified locked: all four
      conditions unmet, `live_trading_enabled=false`, `POST /api/orders` 401s
      with and without a forged token.
      **The record is now growing.** First pass: 184 events discovered, 32
      linked, 3,612 odds quotes, 1,549 markets quoted, **128 recommendations
      recorded, 0 surfaced**. 64 markets awaiting a closing line.
      Two blockers were found and fixed by pre-flighting the image, neither
      findable by any test: the private-key materialisation was documented in
      `fly.live.toml` and never implemented, and `scripts/` was excluded from
      the image so `run_loop.py` — the entrypoint's own process — was absent
      from the filesystem.
- [ ] **Say yes/no to one combo price lookup.** `POST .../lookup` returns a
      Kalshi combo's price but *creates a market on the exchange* if that
      combination is new. No money moves; it's what the app does every time you
      tap a leg. I've left it refusing by default. This is the only way to get
      a real combo quote and back out an implied same-game correlation.
- [ ] **Decide on fee-calibration trades.** The fee model is still a hedge
      between two sources that disagree, and it can only be settled by real
      fills. Four minimum-size orders at ~10c/30c/50c/80c would close a
      year-old open question for a few dollars. This is real money, so it's
      your call.

- [ ] **`ODDS_API_KEY` is exposed — rotation deliberately deferred
      (2026-08-07).** A live run put the key into a terminal transcript: httpx
      logs full request URLs at INFO and The Odds API takes its key as a *query
      parameter*, so making a request was enough. Nothing logged it
      deliberately. **The cause is fixed** —
      `backend/logging_setup.py` redacts at the root logger and pins httpx to
      WARNING — but the leaked value is still valid.
      Judged not worth rotating for now: it is a free-tier key, 500
      credits/month, no money and no account access attached, and Kalshi's
      credentials were never exposed (they sign headers, not URLs). The residual
      risk is someone draining the quota, which would silently stop the record
      accumulating once the live instance is running. Revisit if the odds path
      is ever put on a paid tier.

---

## 1b. Found by deploying live

- [x] ~~**The live cockpit is fully public**~~ — **done 2026-08-07.** A
      shared-token login now gates every page and every proxied API route on
      the live instance; the demo stays open, because it is the portfolio link.

      **Gated in Next, not in the backend.** uvicorn binds `127.0.0.1:8000` and
      is never published — `/api/*` is reachable only because `next.config.ts`
      rewrites it, and middleware runs *before* rewrites. So one gate covers
      pages and API together, and server components keep calling the backend
      over loopback with no token to thread through.

      **The cookie is not the token.** `APP_AUTH_TOKEN` authorises
      `POST /api/orders`; the cookie carries `<expiry>.<HMAC(token, expiry)>`,
      so a stolen cookie costs read access and cannot be replayed as order
      authority. Tampered signatures and expired cookies both 401.

      **The switch is the token's presence**, not `INSTANCE_MODE` — the backend
      already refuses to boot in live mode without `APP_AUTH_TOKEN`, so
      "live but unauthenticated" is unreachable rather than merely unlikely.

      Three traps caught by testing the built image rather than the dev server:
      `/api/health` must stay public or Fly's check fails and the machine
      crash-loops; `process.env` in middleware had to be verified as
      *runtime*-read, since the same image must gate with the token set and not
      without; and `NextResponse.redirect` built its URL from the container's
      bind address, which would have sent the browser to
      `https://0.0.0.0:3000/ledger` — now a relative `Location`.

---

## 2. Fix before any real money

- [x] ~~**`clv.py` does not require the entry to precede the close**~~ — **done
      2026-08-07** (audit item 11). The closing line is read at
      `commence - horizon` and the runner records right up to kickoff, so at a
      1h horizon every recommendation made in the final hour was scored against
      a quote observed **before the decision existed**. Whether that flatters or
      punishes depends purely on which way the market drifted in between, so it
      put drift straight into the number built to detect edge — and the live
      instance starts scoring tonight, so it was contaminating a record that
      cannot be repaired retroactively.
      Now `created_ms <= observed_ms`, in `score_recommendations` *and* in
      `horizons_agree`, where it matters more: the 6h line is observed five
      hours earlier, so without it the two horizons compared different
      populations and part of the measured "drift" was just a change in which
      rows were counted. Excluded rows are counted
      (`skipped_entry_after_close`) and stay unscored rather than consumed, so
      they remain candidates for a shorter horizon.
      **The cost is stated, not hidden:** late recommendations go unscored at a
      given horizon, so the scored sample skews early.
      Verified by disabling (4 red). Adding it also turned 5 `test_scoring`
      tests red, because their fixtures created recommendations *after* the
      closing line — the rule catching unrealistic test timing on its first run.


- [x] ~~**`devig.market_width` reports `0.0` for a single book**~~ — **done
      2026-08-07** (audit item 10). "No disagreement measurable" rendered as
      "perfect agreement", so the least-evidenced consensus in the system passed
      the width suppression most easily. Now `Optional[float]`: `None` when
      fewer than two books contributed, and suppression **refuses** on it under
      a distinct `no_market_width` code — "books disagree" and "there was no
      second book to disagree with" call for different fixes.
      A measured `0.0` (two books quoting identically) still passes, and that
      pair is the test that matters: if `None` and `0.0` ever behave the same
      again, the states have been collapsed back together.
      **The larger finding underneath it:** sharp anchoring *causes* the
      single-book case. Three books agreeing to within 3.1 points, one of them
      sharp, yields `book_count = 1` and no measurable width — the anchoring
      discards the agreement evidence, which was the strongest signal the line
      was trustworthy. `usable_book_count` is now reported so the log can tell
      "only one book quotes this" from "five did and we kept the sharp one".
      Both guards verified by disabling. It had been masked by
      `min_book_count = 2` catching the same rows — a working guard hiding a
      broken one.

These are open defects from the 2026-08-07 audit. Full detail with file:line in
`tasks/audit-2026-08-07.md`. Ordered by how much they'd distort a money
decision.

- [x] ~~**The gate's `n` counts non-independent observations**~~ — **done
      2026-08-07.** Rows are now clustered by **game** (`kalshi_markets.
      event_ticker`, not ticker — a game's moneyline, spread and total resolve
      from one final score) and the standard error is the cluster-robust
      sandwich estimator. The 300 floor counts independent games; the Ledger
      shows games over the floor with the row count beside it, so the two
      screens cannot disagree. Two anchors chosen so a wrong implementation
      differs: singleton clusters reproduce the classical `s²/n` exactly, and
      duplicating every observation `k` times leaves the standard error
      bit-identical (the old estimator returned `stderr/√k`). Verified by
      disabling it two ways — clustering by row turned 5 tests red, dropping the
      finite-cluster correction turned the other 2 red. **Found on the way:**
      the test helper's `INSERT OR IGNORE INTO kalshi_markets` had been silently
      inserting nothing since the file was written (`first_seen_ms` is `NOT
      NULL`), so every gate test's join matched nothing. Both in
      `tasks/lessons.md`.
- [x] ~~**Continuous monitoring with no peeking correction**~~ — **done
      2026-08-07.** The noise guard now uses an always-valid bound (Robbins
      normal mixture, `m` tied to the 300-game floor) instead of two standard
      errors. Measured on 1,200 pure-noise sequences looked at 100 times each:
      the old rule fires on **13.7%**, the new one on **0%**. The cost is stated
      rather than buried — 3.66 standard errors at the floor instead of 2, about
      1.8x the effect size, and the gate's detail string reports the multiplier
      it used. Verified by disabling it (returning 2.0) and watching the
      simulation and the boundary test go red. Compounds with the clustering fix
      above: both corrections apply to the same statistic.
- [x] ~~**`margins.fit()` destroys the published standard deviation on a thin
      sample**~~ — **done 2026-08-07.** `fit` no longer overwrites `sd` from a
      sample too thin to estimate it: `MIN_GAMES_FOR_SD = 30`, deliberately
      separate from `MIN_GAMES_FOR_EMPIRICAL = 200` because "can this sample
      show me the shape?" and "can it tell me the width?" are different
      questions. Below it the league's `PUBLISHED_SD` is kept and
      `sd_is_measured` says so. The count alone was never sufficient — 300
      identical margins clears n≥30 and still estimates zero — so the check is
      on the estimate too. `_normal_survival` now **raises** on a non-positive
      width instead of returning 1.0/0.0, and a zero-width distribution cannot
      be constructed at all. Verified by restoring the old `max(1, n-1)`
      computation and watching 4 tests go red.
- [x] ~~**`backtest.beats_close` contradicts its own verdict**~~ — **done
      2026-08-07.** Both now derive from one `PairedComparison`, so there is no
      second path to disagree with; the invariant *"`beats_close is True` iff
      the verdict claims an edge"* is asserted across twelve seeds, because the
      two paths agreed whenever the gap was large and diverged exactly on the
      marginal cases. It also respects `min_games` now — a 50-game backtest
      could previously report `True` beside a verdict saying "No verdict".
      **Fixed audit item 14 in the same change:** the noise band used
      `sqrt(0.25/n)`, the null for a *single* proportion, where the gap is a
      difference of two accuracies on the *same* games. Now McNemar's
      `sqrt(b+c)/n`. The two coincide at exactly 25% discordance — which is why
      it looked right — and above it the old form is too narrow, 1.55x too small
      at 60% discordance, in the direction that manufactures significance.
      Verified by restoring each old implementation in turn.
- [x] ~~**Refresh the Kalshi quote at order time**~~ — **done 2026-08-08.**
      Item 3 of the three window fixes, and the last of them.
      `POST /api/orders` now re-reads `GET /markets/{ticker}` inside the
      request and **prices, sizes and caps the order against what comes back**;
      the recorded ask is provenance from that point on. `backend/kalshi/
      quotes.py`; wire format pinned by `tests/fixtures/market_single.json`,
      which stores the same ticker as `/events` returns it beside the
      single-market payload so a rename in one and not the other fails a test.
      Size is re-derived through `size_position` rather than against a new
      "how far may a price move" threshold, so a price that erased the edge
      returns zero contracts without anyone choosing a tolerance — and a
      *better* price still cannot exceed what the engine authorised.
      **Two things fell out of it that were not in the plan.** The route's
      portfolio-cap re-check became unreachable — the sizer now applies the same
      caps at the same instant against the same exposure, at a fee-inclusive
      price strictly above the one the re-check compared — so it was deleted
      rather than left looking like protection, with the caps now verified *at
      order time* instead. And `/api/board` had to change: with the quote
      re-read at order time, a stale recorded quote no longer stops an order, so
      splitting `surfaced`/`expired` on both clocks was striking through
      everything between 30s and 15 minutes after a pass — nearly the whole
      window — while the server would have sold it. `actionable` is now the odds
      clock and `price_is_current` is the Kalshi one; the card says "still
      bettable, but this price was read 4m ago and will move".
      17 guards verified by disabling; two were decoration on the first pass and
      both were real defects rather than missing tests.
- [x] ~~**Deci-cent asks can't fill.**~~ — **done 2026-08-08.** Checking it
      against Kalshi's write API turned a rounding fix into an endpoint
      migration, and found a second defect on the way. `docs/adr/0007`.
      **Prices now snap to the market's own `price_ranges`**, which Kalshi
      documents as the source of truth and explicitly tells clients not to infer
      from `price_level_structure`. No default grid: unreadable resolves to
      `None` at ingest and the order path refuses, because assuming whole cents
      is the bug.
      **The order goes to `POST /portfolio/events/orders` (V2)**, because the
      legacy path takes integer cents and cannot express 50.5c at all. It is
      also absent from Kalshi's current API reference — we had been posting to a
      deprecated endpoint for the whole project, invisibly, because nothing has
      ever posted. V2 quotes the **YES leg only** (`bid`/`ask`), so buying NO at
      `p` is selling YES at `1 - p`; `time_in_force` and
      `self_trade_prevention_type` are required and were absent.
      **The response defect found in the same change:** V2 emits no `status`
      field, and the old parser read `response["order"]["status"]` defaulting to
      `"resting"` — so every live order would have been recorded as resting with
      a null order id. Status is now derived from the fill counts and an
      unreadable response is `unrecognised_response`, which nothing can mistake
      for success.
      **Measured before believing the size of it:**
      `scripts/capture_price_grids.py` walked the live exchange —
      **1,426 game markets, all `linear_cent`.** So this costs no fills today;
      the "~25%" is a fact about all Kalshi markets, not about the ones we
      price. That does **not** mean sub-cent game markets don't exist (60 of
      2,145 on 2026-08-06, and a market's grid can change while it is open).
      6 guards verified by disabling; one of them was decoration on the first
      pass — a redundant bound check — and was deleted rather than kept.
      1,139 tests.
      **Dividend:** the V2 response carries `average_fee_paid` per contract, so
      the fee-calibration trades will read the true fee out of the order
      response itself rather than needing a `/portfolio/fills` poll.
- [x] ~~**Calibration panel leaks the number it suppresses**~~ — **done
      2026-08-07.** It rendered `implied` and `actual` on every row, and
      `gap = actual - implied`, so the suppressed finding sat one subtraction
      away in two adjacent columns. Censoring now happens in the mart
      (`actual_display`, `pnl_display`, `beat_close_display`, `clv_display`),
      so the presentation layer never receives an uncensored result; raw
      columns stay for analysis. `implied` and `n` stay visible because neither
      is a result. The dbt test that was meant to catch this was a tautology
      (`(A∧B) ∧ ¬(A∧B)`) and now recomputes from raw inputs; a source guard
      stops the frontend rebinding a raw column. Both verified by
      re-introducing the leak and watching them fail. 7 noise cells, 0
      reconstructable.
- [x] ~~**`mart_multiple_comparisons` undercounts tests**~~ — **done
      2026-08-07.** It counted `mart_calibration` alone while
      `mart_clv_by_bucket` and `mart_suppression_audit` ran their own
      two-standard-error tests uncounted. Measured on the seeded no-edge
      history: 8 tests instead of 11 moves p from **0.401 to 0.311** — a 29%
      improvement in apparent significance bought by forgetting to count. The
      model that exists to catch multiplicity was committing it.
      Findings are read from each mart's **own published conclusion** rather
      than recomputed, because a counter that disagrees with the thing it counts
      is worse than no counter. Both directions count in the suppression audit —
      "REVIEW" and "protective" each cleared the bar; only "neutral" did not.
      `generate_series(0, 200)` replaced with a series to `n_findings - 1`, so
      the sum can no longer truncate (which pushed p toward 1 — the bug that
      hides findings sat one edit from the bug that invents them).
      `tests_by_source` is a column now and renders under the verdict, so the
      total is checkable rather than asserted. A new dbt test names the three
      sources independently and fails if one is dropped — verified by dropping
      `suppression_audit` and watching it go red. `dbt build` 11 nodes green.
      **Deliberately still not counted:** `gate.py`'s noise guard, which is
      multiplicity along the *time* axis and already carries its own
      always-valid bound (folding it in would apply two corrections to one
      test), and `validate.py`, which tests the same observations these marts
      do.
- [x] ~~**Capture an Odds API fixture**~~ — **done 2026-08-07.** The capture
      already existed (`tests/fixtures/odds_mlb_h2h_spreads_totals.json`, 15
      events, 30 books) and **no test loaded it**, so the wire format was still
      pinned only by hand-written payloads. A capture nothing reads is
      decoration. Eight tests now parse the real bytes, including a drift test
      asserting every market key present is explicitly classified.
      **Closed the `h2h_lay` SEV 1 in the same change:** the API returns
      `h2h_lay` from Betfair and Matchbook without being asked, and `_parse`
      stored any key it was given. Lay quotes are now dropped at ingest, so no
      downstream grouping can pool them. Measured on the fixture: back
      `2.24/1.79` sums to 1.00509, lay `2.28/1.81` sums to 0.99108 — devig
      removes an overround, and an underround gives it nothing to remove.
- [x] ~~**Wire up the agent fleet.**~~ — **done 2026-08-08.**
      `backend/agents/review.py` is the seam; `run_pricing_pass` collects,
      reviews the surfaced rows in one batch, applies verdicts, then persists.
      All four decisions below were implemented as designed. The
      `test_has_callers` exception is closed and `apply_verdict` /
      `review_surfaced` are ordinary entries in `MUST_HAVE_CALLERS`.

      **It has run against the real Anthropic API, which the design note said
      would not be possible.** The first end-to-end run surfaced a row and the
      Skeptic *blocked* it — correctly, and for a reason no deterministic check
      could have reached: the test fixture's market title still read "Houston
      vs San Diego Winner?" under an event titled "Pittsburgh vs New York M",
      so the contract being priced was not the fixture matched against the
      book. That is a fixture bug rather than a finding about the venue, and it
      is exactly the failure class in the Skeptic's own docstring (FIXTURE
      MISMATCH). Fixed in the fixture; the point is that the layer works.

      **The design note's decision 3 was wrong and would have shipped broken.**
      `asyncio.run` at the seam raises whenever the pass runs inside a loop —
      which is always, in production, because `run_once` and `run_quote_pass`
      are coroutines calling the sync pass directly. It passes every sync test.
      The batch now runs on a dedicated thread with its own loop, with a test
      that calls the pass the way the scheduler does. See `tasks/lessons.md`.

      **Also found: the suite was making live API calls on any machine with the
      key in `.env`.** `backend/config.py` calls `load_dotenv()` at import, so
      `AgentConfig.from_env()` saw the key in every test. The same test called
      Claude locally and skipped the review in CI — green both times, asserting
      different things. An autouse fixture in `conftest.py` now removes it for
      the whole suite, and the reviewer is a **parameter** on `run_pricing_pass`
      so the one leg that costs money is visible in the signature.

      Seven guards verified by disabling: the thread seam, the contracts
      zeroing, the right-hand text split, the per-candidate failure boundary,
      review-before-persist, the verdict/row alignment check, and the conftest
      key removal (verified with a deliberately invalid key, which produced a
      real 401 from `api.anthropic.com` — proof the request had left the box).
      One of them caught a weak test of my own: it was passing through the
      exception path rather than a real verdict.

      **Still needs `ANTHROPIC_API_KEY` as a Fly secret** before it does
      anything on the live instance. Without it the fleet is unconfigured and
      every row comes back untouched, which is the live behaviour today.

      **The original design note, kept because it is the clearest statement of
      why each decision is what it is** — four decisions, each of which took a
      while to arrive at:

      1. **Run the Skeptic only on rows that would be surfaced**
         (`suggested_contracts > 0`, no suppression reason). Not on every
         candidate: a live pass builds ~100 rows and ~all of them have no edge,
         so reviewing them all would spend real money to be told "no" a hundred
         times. It also means the cost today is **zero calls**, because
         surfaced has always been 0.
      2. **Review before persisting, not after.** `apply_verdict` folds into
         `suppressed_reason`, and if the row is already on disk there is a
         window — one Anthropic round trip — in which the order endpoint would
         sell an unreviewed row. So the pass has to collect its
         recommendations, review the surfaced ones in one async batch, apply
         verdicts, and only then persist. That is the restructure: the loop
         currently builds and persists in the same breath.
      3. **`run_pricing_pass` is sync and `structured_call` is async.** Either
         make the pass async (touches every caller and test) or run the batch
         through `asyncio.run` at the one seam. Prefer the seam.
         *(The seam was right; `asyncio.run` was not — see above.)*
      4. **A Skeptic outage must not stop the pass.** `structured_call`
         already returns `None` on failure and `apply_verdict` already treats
         `None` as "no opinion", so this falls out — but assert it, because
         the alternative is a slate that silently stops being recorded.

      Needs `ANTHROPIC_API_KEY` as a Fly secret before it does anything on the
      live instance; it is in `.env` locally and `AgentConfig.from_env()`
      returns `None` without it, which degrades to no commentary rather than
      failing.

      ~~**And it cannot be verified against real data.**~~ — **partly wrong,
      and worth keeping for the correction.** The claim was that zero surfaced
      rows means zero verdicts, so the wiring could only be proven against
      fixtures. True of the *live record*, and false of the wiring: a captured
      slate with one number nudged (the NO bid on one market, which sets the
      derived YES ask) surfaces a row, and that row went to the real API and
      came back blocked. What remains unverified is narrower and still worth
      saying in the module — **no live instance has ever produced a surfaced
      row, so this path has never run on data the tool found by itself.**

~30 more findings are triaged in `tasks/audit-2026-08-07.md`.

- [x] ~~**The odds sweeps fire at the wrong time of day**~~ — **done 2026-08-08.**
      `backend/odds/timing.py`. See the handoff at the top of this file.
- [x] ~~**Surface the window on the Board**~~ — **done 2026-08-08.** And it
      immediately contradicted the page under it, which is how the 30-second
      window was found.
- [x] ~~**Wire up Discord**~~ — **done 2026-08-08.** `backend/notify/alerts.py`
      is the caller. Secrets still need setting on the live app.

---

## 3. Ready to build (no blockers)

- [x] ~~**The chain runner**~~ — **done 2026-08-07.** `backend/runner.py` joins
      discovery → odds sweep → link → devig → engine → `recommendations`.
      Nothing joined them before: `persist_recommendation` was called only by
      `seed_demo.py` and tests, `odds_snapshots` had a writer and no reader, and
      `fair_prices` had neither. **Verified against the live API**, not just
      fixtures: 175 events discovered, 19 linked, 2,746 odds quotes, 76
      recommendations recorded, **0 surfaced** — no edge, which is the expected
      and honest result. `scripts/run_chain.py` runs one pass; `--no-odds`
      spends no credits.
      Quotes ride on the `/events` payload (`yes_bid_dollars`,
      `yes_ask_size_fp`) rather than a second orderbook call — no extra request,
      and no second wire format to guess at.
      **Three defects found by running it live**, all in `tasks/lessons.md`:
      the credential leak above; Kalshi's `occurrence_datetime` running exactly
      3h late, which blocked *every* link; and the same offset then blocking
      every candidate at a second, unconnected limit in `suppression`.
      Still moneyline-only — spreads and totals are ingested and not yet priced.

- [x] ~~**Run it on a schedule**~~ — **done 2026-08-07.** `backend/scheduler.py`
      + `scripts/run_loop.py`. Jittered interval (default 900s), and it **dies
      loudly**: a transient failure is retried, but `MAX_CONSECUTIVE_FAILURES`
      in a row re-raises, killing the process, tripping `wait -n` in
      `entrypoint.sh` and taking the container down. A loop that swallowed its
      errors would leave the cockpit serving a record that had silently stopped
      growing, which reads as a quiet slate. Started by the entrypoint on
      **live only** — the demo holds no credentials. Smoke-tested live for two
      passes.
- [x] ~~**CLV scoring pass**~~ — **done 2026-08-07.** `backend/scoring.py`
      fetches closing lines from candlesticks and calls `score_recommendations`,
      which had existed since the evidence layer was built and had **never been
      called by anything** — so no row could ever be scored and the gate's
      counter was structurally pinned at zero.
      **The anchor is the sportsbook's commence time, not Kalshi's.** Kalshi's
      runs 3h late, so a "1h before close" reading against it lands *two hours
      into the game* — a quote from after the outcome is partly known, which
      would have produced a strong and entirely fake CLV signal in the one
      measurement this project exists to make. Lines are stored at both
      horizons for `horizons_agree`, but only the primary is scored, so
      `clv_tenths` is never a silent mixture. Four guards verified by disabling.

- [x] ~~**The record accumulates near-duplicate rows**~~ — **done 2026-08-07.**
      `engine.persist_if_changed` skips a row identical in derived ask *and*
      fair probability to the previous row for that `(ticker, side)`. Measured
      on a real two-pass run: 152 rows carried 77 distinct combinations, so half
      the record was repetition after two passes and would have been ~98% at 96
      passes a day.
      **Consecutive, not global** — a price moving 47 → 48 → 47 records three
      observations, because the return to 47 is a genuine second opportunity and
      global dedupe would thin the record exactly where the market is moving.
      Both directions verified by disabling: removing the check re-records an
      unchanged slate, and comparing against the oldest row instead of the
      latest swallows the return.
      Settled **before** live recording starts, deliberately: changing what gets
      recorded mid-stream puts two regimes in one dataset. The rule is part of
      the strategy config, so it mints a version and the record segments on it.

- [ ] **Is in-play betting viable? — measured, and the answer was NOT accepted.**
      `docs/adr/0006-in-play-scope.md` proposed closing it as out of scope;
      **Joe rejected that on 2026-08-08.** The question stays open. The
      measurements below were not disputed — they are kept in
      `docs/adr/0006-in-play-evidence.md` and should not be re-derived.

      **The three guards stay on while it is open**, and none of them came from
      the rejected ADR: the runner still drops started games, the order path
      still refuses one, and **no in-play row enters the evidence record**.
      Reopening the scope means designing the in-play regime — starting with
      what replaces the closing line — not letting rows in and separating the
      populations afterwards.

      All four questions were answered against the live exchange; **zero odds
      credits were spent** and no POST was made.

      **Joe was right about the product, and that is the part to say first.**
      Kalshi keeps the game market open in-play — `can_close_early: true`, and
      20 of 20 games measured (14 MLB, 6 WNBA) had a two-sided quote in *every*
      minute after the true start. In-play volume is **7.7x** (MLB) and
      **14.7x** (WNBA) the pre-game rate, and 98% of in-play minutes trade. The
      liquidity is real and it is where the action is.

      **It is out of scope because we cannot see it in time, not because it
      isn't there.** Two independent reasons, either sufficient:

      - **Cost.** Half-spread rises from 0.50c to 0.75c (MLB) / 0.89c (WNBA),
        and the mid moves ≥1c on ~half of in-play minutes against ~0.5%
        pre-game. Crossing plus 40s of unavoidable staleness is **1.34–2.28c
        against 0.38c of fee headroom** — 3.5x to 6x. Both leagues agree in
        direction and magnitude.
      - **Budget.** The Odds API refreshes in-play every 40s regardless of
        plan, so one league at the current market/region fan-out is ~7,020
        credits/day against a budget of 16. The realistic tier is $119/month,
        needing $31,316 of monthly notional to break even on the data bill
        alone.

      **And CLV has no in-play substitute that is the same statistic.**
      Settlement price is a win-rate measurement, which puts back the
      ~1,000-observation variance `clv.py` exists to avoid; entry-plus-delta is
      exactly what stale-quote picking optimises. Reopening needs a substitute
      argued *before* any row is recorded, plus a regime column, `closing_lines`
      keyed per recommendation rather than per `(ticker, horizon)`, and a gate
      that never pools the two regimes.

      Also from that work, unaffected by the rejection: `dropped_game_started`
      stays a **drop**, not a suppression — a
      suppression entry claims we considered it. Maker is *unreachable* rather
      than refuted: the headroom is 1.94 points there, but a resting order in a
      market moving ≥1c half the time is being adversely selected and this repo
      has **no cancel path at all**. Recorded as missing infrastructure, not as
      a measurement.

- [x] ~~**Verify what `occurrence_datetime` actually is.**~~ — **done
      2026-08-08, and it is a shifted start.** The expected-end story is
      refuted. `scripts/measure_occurrence_datetime.py`, capture in
      `tests/fixtures/occurrence_datetime_probe.json`, reasoning in
      `tasks/lessons.md`. Zero odds credits, no POST.
      **`match.linker` and `core.suppression` need no change** — the offset is a
      fixed +3h and is not game-length-dependent, so a fixed tolerance is right
      for a two-hour sport as much as a three-hour one. That was the worry and
      the answer is no.
      **The residual, which is real and new:** `KXMLBF5` carries **+5h** while
      `KXMLBF5SPREAD`, covering the identical five innings, carries +3h. The
      extra two hours are per-series data entry, not semantics — but the 4h
      tolerance is between the two, so the day this project prices a period
      series, every `KXMLBF5` market is dropped silently. Nothing in scope does
      today.

      What has to be answered before any of it is buildable, cheapest first:

      1. **Does Kalshi keep the game market open in-play, or list separate
         period markets?** One `/events` walk during a live game settles it —
         read `status` and `close_time` on a game whose kickoff has passed, and
         look for half/quarter series alongside `KX*GAME`. Free, no credentials
         beyond what is already exercised.
      2. **Can the odds side even follow?** The Odds API charges per call and
         the free tier is ~16 credits a day. In-play needs a refresh every
         minute or two per game, not twice a day, so this is a **paid-tier
         question, not a code question** — price it before building anything.
         If the answer is no, the honest result is "out of scope until the odds
         budget changes", recorded as such.
      3. **What replaces the closing line?** CLV is the only measurement this
         project trusts, and it anchors on a quote read before kickoff. An
         in-play bet has no such anchor — the natural substitute is the price
         at settlement or at the end of the period, and it is *not* obviously
         the same statistic. Nothing may enter the evidence record until this
         is settled, or the two populations pool into one number the way the
         in-play rows already nearly did.
      4. **Is the edge plausibly there?** In-play is where the venue's latency
         story is worst — this is the corner most contested by bots, and
         `tasks/lessons.md` already records that stale-quote picking lives at
         ~400ms. Expect the answer to be no, and design the check so a no is
         reportable.

      Do **not** simply remove the in-play drop to find out. That would put both
      populations in one record with nothing to tell them apart afterwards,
      which is the failure `tasks/lessons.md` names as "two populations in one
      record, told apart by dispersion".

- [ ] **Research screen** — Scout findings with sources and timestamps, model-
      vs-market disagreements, steam moves.
- [ ] **Playbook screen** — lessons, config versions, proposed changes awaiting
      your approval. The flywheel's UI.
- [x] ~~**Ticket bottom sheet** on the Board~~ — **done 2026-08-08.**
      `lane/frontend-wip` verified and merged. `TicketSheet.tsx`,
      `TicketProvider.tsx`, and the ticket trigger on the Board's live and
      expired cards; suppressed cards stay untappable, because a sheet with a
      permanently dead Confirm would suggest the decision is reversible.
      **It had never been rendered**, and no check in the repo could have
      rendered it: it mounts on a tap, so `check_mobile.py` never sees it, and
      it is `position: fixed`, so it cannot widen the `scrollWidth` that script
      decides on. `scripts/check_ticket_sheet.py` is the replacement — it taps,
      waits out the entrance animation, measures, presses Confirm, and measures
      the answer.
      **It fit 320/390/430 on the first render. The three defects were
      behavioural**, which is the part worth remembering: focus escaped to
      `<body>` the instant Confirm unmounted, so the trap opened exactly when
      the answer appeared; the line under a disabled Confirm asked for the
      token on rows whose consensus had aged out, where typing it changes
      nothing; and Close was a 59x26 target on a sheet that argues from thumbs.
      A fourth, same shape as the second: a 403 offered "Back" beside a
      sentence saying retrying will not help.
      Verified against three instances — live with a locked gate (**423, four
      conditions**), an expired-row instance (Confirm off, and now for the
      stated reason), and demo (**403**, the backend's own sentence verbatim).
      `--fail-order` renders the offline answer, the only way to see the
      two-button action bar at all; it fits 320 on one line each, which the
      component's own comment had flagged as the risk.
      **What it deliberately does not do:** no arithmetic on money, anywhere.
      Every figure is the server's, rendered as it arrived, and where a number
      is genuinely absent — the total before you confirm — it says so instead
      of multiplying. `worst_case_cost_dollars` on the board row would let that
      line be a number.
- [x] ~~**README** — the portfolio piece.~~ — **done 2026-08-08.** It already
      existed and had drifted, which is worse than missing: **"The WebSocket
      wire format is unverified"** had been false since 2026-08-07, and leaving
      it in hid the most instructive failure in the project behind an apology
      for not having looked. "Roughly 0.6 percentage points" sat two paragraphs
      below a table whose rows differ by 0.38. The test count and the demo
      slate were both stale.
      Added the live demo link (the thing a portfolio README most needs and did
      not have), a gate section carrying the two conditions whose earlier
      versions would have talked someone into a bet, the order path in the
      diagram, and the two browser checks that cannot run in CI.
      **Still missing, deliberately:** an architecture *diagram* rather than
      ASCII, and screenshots. Both want the deploy to be current first.
- [x] ~~**GitHub Actions** — tests, `dbt build`, and secret scanning on push.~~
      — **this line was wrong in both directions, 2026-08-08.** CI was built in
      the first commit and has been running pytest, `seed_demo` → `publish` →
      `dbt build`, and `next build` green throughout. This checklist said it did
      not exist.
      **And the part nobody was reading was red.** The secret scan failed on
      **36 consecutive pushes** since 2026-08-07 19:17Z, because it grepped for
      the *phrase* `BEGIN … PRIVATE KEY` and two files legitimately contain it —
      `docker/entrypoint.sh` validating a decoded key's format, and
      `tests/test_logging_redaction.py` proving the redactor strips a PEM block.
      It fired on the hygiene. A check that is always red carries no
      information: the run that finds a real key looks identical to the 36 that
      found a comment about one, and red becomes the resting state.
      Now matches **material**: a header alone on its line, a header followed by
      a base64 body, and a header immediately after a quote that then ends the
      line. That third one was added on merge — narrowing to material had
      dropped `KEY = """-----BEGIN RSA PRIVATE KEY-----`, which the broken
      pattern did catch. The `:!*.yml` exclusion is gone, so a key pasted into
      `warehouse/profiles.yml` is now scannable.
      **Verified by running the step, not by reading it:** extracted from the
      YAML and run under bash — clean tree exits 0, five planted shapes each
      exit 1 (own line, after a triple-quote in `.py`, escaped in `.json`,
      inside a `.yml`, and a tracked `.p12`). Random bodies, never key material.
      The exclusions are asserted against the two real files, so a future
      widening fails loudly instead of turning CI red again.
      Also note what gitleaks does **not** do: it scans only the commits in the
      push, never the tree and never history. A key committed last week and
      still present is invisible to it.

- [x] ~~**Three CI follow-ups**~~ — **done 2026-08-08.** `.gitignore` was
      missing `.pkcs8` as well as `.p12`. ruff is wired at 55 active rules with
      0 findings, chosen so it is green on the first push rather than red — its
      current default finds 513. Four actions bumped off the retiring Node
      runtime, the only one of the three that cannot be verified without a
      push. See the handoff at the top.
- [x] ~~**Write `orders` rows.**~~ — **done 2026-08-08.** `docs/adr/0008`. The
      description above was wrong about why it mattered: it does **not** make
      `max_exposure_dollars` bind, because every order is a dry run and dry runs
      commit nothing. What it does is make `client_order_id` durable before the
      request goes out, and join the CLV price to the executed one. It also
      turned up a second implementation of exposure. Handoff at the top.
- [x] ~~**A paper settlement path.**~~ — **done 2026-08-09.**
      `backend/settlement.py`, `docs/adr/0010`, schema v4. `settlements` gets
      its first writer, and `max_exposure_dollars` binds in production for the
      first time — on paper, scoped to the paper population so the first live
      order still sees a clean budget. That reverses ADR 0008's refusal, and
      only settlement makes it safe: exposure that can only ratchet up is a cap
      that can only close.
      **The capture came before the parser and the first finding would have
      broken everything silently:** `GET /markets?status=settled` returns
      markets whose `status` reads `finalized`, and `finalized` is rejected as
      a filter. `status == "settled"` matches zero markets forever and reports
      it as "nothing settled yet". Three more from the same 44 rows are in
      `tasks/lessons.md`.
      Paper P&L is walled off from the gate by construction, not by convention
      — `gate.py` does not read `settlements` and a test asserts it. The module
      docstring states what paper P&L does not establish.
      Eleven guards verified by disabling; one stayed green and was a real gap.
- [ ] **Make placement idempotent, before the gate opens.** Each request mints a
      fresh `client_order_id`, so two taps are two orders; the `UNIQUE`
      constraint stops a duplicate row and not a duplicate order. Costs nothing
      today because every order is a dry run. The shape: the client supplies the
      key, and the endpoint replays the recorded outcome instead of placing
      again. Deliberately not built yet — it is a new path on the money endpoint
      that nothing can exercise against live behaviour.
- [x] ~~**Serialise the exposure read with the insert.**~~ — **done
      2026-08-08.** `store.orders.reserve_order` writes the row and then checks
      the cap against the portfolio *including it*, in one transaction. The
      endpoint's own exposure read stays where it is and stays advisory: the
      sizer decides how big an order should be, the reservation decides whether
      the portfolio can hold it, and only the second has to be atomic.
      **The check runs after the insert, not before.** Reading and then
      deciding whether to write is the same race one level in; writing first
      and asking "what is the total now" makes the answer a fact rather than a
      prediction, and the rollback is exact — a refusal leaves nothing on disk,
      which matters because a stranded `pending` row counts as exposure by
      design.
      Verified by a real two-thread test on two connections, not `TestClient`,
      which drives the app through one portal and never makes the hop — the
      trap that made an earlier concurrency regression test in this repo pass
      against unfixed code.
      **And the docstring was wrong before it was tested.** It claimed
      `BEGIN IMMEDIATE` was what made it correct. Measured: a deferred `BEGIN`
      leaves the test green, because the insert is the first statement and
      takes the write lock anyway. What is load-bearing is the *order* of the
      two statements. `IMMEDIATE` stays for the next edit — the moment someone
      reads a daily-loss total before writing, deferred would read stale and
      fail on the upgrade — but it is documented as insurance rather than as
      the mechanism.
      **It still cannot fire in production**, and that is not a bug: dry runs
      are excluded from exposure, so the paper orders the running system places
      consume none of the cap. Asserted as a test rather than left in prose.

---

## 4. Verified working

So you know what's actually solid:

- **Live WebSocket** — 6/6 books populated from real MLB markets, derived-ask
  identity holds on every one, subscription registry complete, sequence gaps
  handled at the connection level.
- **Kalshi REST + auth** — signing verified against the live API; discovery
  pinned by drift tests over real captures.
- **Devig** — four methods, worst-of-four for money decisions, Shin verified
  not to degenerate.
- **Suppression + engine** — every candidate recorded, suppressed or not, with
  its config version.
- **Measurement** — noise guard under the null, pooling check, multiple-
  comparisons mart. On seeded no-edge data the dashboard correctly reads
  *"NOT EVIDENCE: 1 finding from 10 tests, 37% by chance."*
- **Builder** — parlays priced against devigged consensus; same-game legs
  refused rather than guessed; Wong teasers priced from bucketed empirical
  margins and correctly coming out negative at −120.
- **Combos** — 1,389 collections mapped; a combo quote inverts to an implied
  correlation.
- **Gate** — five conditions, one shared implementation, locked by default.
- **Cockpit** — Board, Builder, Dashboards, Ledger, Gate. Clean at 320px.

---

## The honest status

No bet has been placed and no edge has been demonstrated. The tool is built to
find out whether one exists, and every measurement in it is built to avoid
flattering the answer. The gate is locked and correctly reports that it has
zero scored recommendations, no verified fee model, and no evidence.

That's the expected state. The premise was always that Kalshi's advantage is
cost, not information — it lowers the break-even bar from 52.38% to ~52.00%
taker, and does not clear it for you.
