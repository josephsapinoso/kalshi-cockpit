# Start prompt — paste this to open the next session

Rewritten **2026-08-11 ~13:15Z**. The session that **found the instrument
reading a one-shot 24-credit capture had never been run by anything**, **killed
the leadership question on arithmetic rather than deferring it again**, and
**caught its own capture timer still alive after it had been stopped**.

Say *"read start.md and follow it"*, or paste this whole file.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md`. NEXT.md is the
actionable checklist and **its top supersedes everything here**.

## ⏱ FIRST — the capture is ARMED and it is NOT yours to fire

**`KalshiRepeatPoll` is a Windows scheduled task.** It fires
`scripts/capture_odds_repeat_poll.py --confirm-spend-24` at **11:00:00-07:00 =
18:00:00Z on 2026-08-11**. It is **not** a session timer, **not** a Monitor, and
**not** a background bash job. It survives session death, terminal close and
logoff. That was deliberate — see the trap below.

```
powershell -c "Get-ScheduledTask -TaskName KalshiRepeatPoll | Select-Object State"
powershell -c "(Get-ScheduledTaskInfo -TaskName KalshiRepeatPoll).LastTaskResult"
```

**DO NOT re-arm it. DO NOT run the capture by hand.** Two waiters means **48
credits, not 24**. A double-fire guard exists — `fire_now.sh` claims
`C:\Users\josep\AppData\Local\Temp\kalshi_capture\FIRED.lock` with an atomic
`mkdir` — but the guard is the backstop, not the plan.

**After 18:00Z, read these three, in this order:**

```
C:\Users\josep\AppData\Local\Temp\kalshi_capture\waiter.trace
C:\Users\josep\AppData\Local\Temp\kalshi_capture\EXIT_CODE
C:\Users\josep\AppData\Local\Temp\kalshi_capture\capture.log
```

**Read the exit code, not the prose.** `0` = polled. `3` = P4 failed, nothing
spent. `4` = P1 failed, nothing spent. `6` = aborted in flight on a credit
backstop. Anything else, read the log before saying a word about it.

**The window was measured free from ESPN and independently re-derived this
session by calling `check_slate()` at candidate `T0` values: P4 passes only
17:30Z–22:00Z on 2026-08-11.** At 22:30Z a kickoff enters the 20-minute
blackout; 2026-08-12 is too thin all day (1 event within 6 h at 12:00Z). 25
known MLB kickoffs, earliest 22:40Z. **There is no second attempt at this
slate.** If it did not fire, re-derive the next window free — the dry-run is
free and prints the kickoff list.

**Then analyse.** `scripts/analyse_odds_repeat_poll.py` — see §2 below before
you trust a single number it prints.

### The exact command, derived 2026-08-11 16:45Z so nobody re-derives it at 18:01Z

Every value below was read off the code or the live scheduler, not remembered:

- **What fires it:** `Get-ScheduledTask KalshiRepeatPoll` → `bash.exe -c "sh
  .../4e69ab52-.../scratchpad/fire_now.sh"`. **That path is a *previous*
  session's scratchpad and was verified to still exist** (1,068 bytes,
  06:04:21 local). If a temp sweep ever removes it the task fires into nothing
  and spends nothing — check `Test-Path` before assuming a silent success.
- **`fire_now.sh` passes no `--out-dir`**, so the default at
  `capture_odds_repeat_poll.py:701-703` applies: `docs/measurements/data`.
- **Artefact names** (`:671`, `run_tag` = `T0` as `%Y%m%dT%H%M%SZ` at `:578`):

```
docs/measurements/data/repeat_poll_20260811T180000Z_p1.json   (p1..p4)
```

- **The analyser takes the files as bare positional args** (`:469`,
  `nargs="+"`), no flags:

```
.venv\Scripts\python.exe scripts\analyse_odds_repeat_poll.py `
  docs\measurements\data\repeat_poll_20260811T180000Z_p1.json `
  docs\measurements\data\repeat_poll_20260811T180000Z_p2.json `
  docs\measurements\data\repeat_poll_20260811T180000Z_p3.json `
  docs\measurements\data\repeat_poll_20260811T180000Z_p4.json
```

**Pass each file exactly once.** A repeated `poll_index` is now `exit 2` — it
used to compare a poll with itself and print **CONFIRMED off a single poll**
(`a639591`). Fewer than four files can only ever reach UNRESOLVED (PC6).

## THE THREE THINGS THAT DECIDE THIS PROJECT

Joe said on 2026-08-11, and he was right to: *"You seem to do so much testing
instead of building."* **Write this at the top of every handoff until it stops
being true.** The honest answer is that the tool surfaces **zero** actionable
rows, so there is nothing to build *onto* yet, and exactly three questions
decide whether that changes. Everything else on this file is bookkeeping.

| # | Question | State |
|---|---|---|
| 1 | **Is the staleness guard wrong?** `stale_odds` is the **only** suppression code holding back any would-be-actionable row — **23 rows / 9 clusters**. If the guard is wrong, `actionable` goes 0 → 23. | **Fires 18:00Z today.** Not blocked. |
| 2 | **Is the fee coefficient 0.070 or 0.035?** At 0.035 the taker bar drops 52.00% → **50.88%**, against **0.38 points** of total headroom. That is the difference between "no edge exists" and "an edge exists". | **Blocked on Joe's phone.** 4 cells, **~$3.66**, any time before **2026-08-31**. |
| 3 | **Is Kalshi simply the sharp side?** | **DEAD — closed 2026-08-11 on arithmetic.** See §3. |

**Item 2 has been waiting on Joe since 2026-08-10 and is the largest single
lever on the board.** Do not chase him for it — but if he asks, run the watcher
*then* and hand him the four lines. Never generate the sheet in advance; a
pre-generated sheet is stale quotes wearing a live board's look.

## FIRST — check this file before you trust it

```
git log --oneline -25
git rev-list --count origin/main..HEAD
git status
```

**The tip at writing was `b3fd15a` plus this commit, and by the time you read
this that is wrong.** At writing: tree clean, **2,339 tests pass** (2,296
baseline + 43 new), `ruff check .` clean — all three verified by me, not
inherited.

**⚠ SEVEN commits are unpushed** (`57d2ad5`, `efa5bff`, `1aa75bd`, `0e9b310`,
`a639591`, `b3fd15a`, and this one). Joe last authorised a push through
`faa9d43`. **Ask before pushing** — every push publishes to the world
immediately.

**Treat every command in this file as a test never seen red** unless it says it
was run.

## WHAT THIS SESSION DID — four commits, and one of them was load-bearing

### 1. `a639591` — the instrument that spends 24 credits had never been run by anything

`scripts/analyse_odds_repeat_poll.py`, 481 lines implementing all six
preconditions, both thresholds, `S_strict` and `movers`, **had no test file and
was imported by no test.** Verified independently before acting: `ls` returns
nothing, `grep -rl analyse_odds_repeat_poll tests/` returns nothing.

That is failure #9/#10 repeating verbatim — `capture_fills_fixture.py` had no
test file and its exit code was unreachable by construction.

**Three real defects were found and fixed before the data exists**, which is the
only time they could have been fixed honestly:

1. **A repeated `poll_index` silently overwrote** in `{a["poll_index"]: ...}`.
   Handing the same file twice compared a poll with itself → `S = 1.0` →
   **CONFIRMED out of a single poll.** Now exit 2.
2. **A pair with no `last_update` was scored "static & identical"**, putting a
   reprice-with-no-stamp into the uninformative cell instead of defect cell D —
   hiding the exact evidence PC4 exists to catch. It is *unreadable*, not
   *static*: excluded and counted.
3. **`movers` KeyError'd on a partial capture.** Now `None`; an unmeasured
   control **fails** PC5 rather than defaulting to 0.

Also: `len(artefacts) != 4` refused both routes §8 admits (polls 1+3 primary,
1+4 PC2 fallback) — **fixed, not documented away**. PC6 still requires all four
polls, so a partial capture can only ever reach UNRESOLVED.

**43 new tests, 25 mutations, all in the module docstring, none pruned.** M2 was
**green on the first pass** (no scenario put `S` in the (0.20, 0.50] band) and a
test was added to kill it. **M19 stays green and proved nothing** — semantically
equivalent — and is **recorded rather than pruned**.

`poll_index` is **1-based on both sides** — `capture_odds_repeat_poll.py:588`
`enumerate(POLL_OFFSETS_S, start=1)`, `:648` writes it; analysis uses
`PRIMARY_PAIR = (1, 3)`. It matched. It is now *enforced*: a test re-derives
`start=` from the capture script's **AST**.

**I spot-checked this myself rather than taking the lane's word**: mutating
`PRIMARY_PAIR` to `(1, 4)` turns **15 tests red**. Restored, tree clean.

### 2. `0e9b310` — Amendment B: §7's good-news branch licensed a phrase defined nowhere

`measurement-skeptic` audited the ADR lane's *"§7 passes"* and returned
**SURVIVES NARROWED**: **one declaration branch was unpriced, and it was the
good-news branch.**

§7's mandatory `S_strict` qualifier has two legs; only `S_strict < 0.90` was
priced. At **`S_strict ≥ 0.90`** the registration licenses *"the strong
wording"* — **a term defined nowhere**: not in the registration, not in the
script, not in ADR 0020 (which does not exist). §9 defines it circularly. And
§10 already says a book-scoped stamp advanced by an unobserved market is
*"indistinguishable from a scrape clock even at `S_strict`"*.

**Amendment B fixes the permitted paragraph in advance and retires the term.**
Honour it verbatim when the result is written up; do not paraphrase it from
this file. It also records, as **§B2**, that `s_strict` binds on **1 → 4
always** while §6 reads as the deciding pair — a **registered deviation**.
**Do NOT "fix" that in the script.**

**The amendment lane corrected the auditor's own arithmetic** — the dangerous
leg becomes reachable at `N_adv ≤ 27`, not 25 — and **recorded the correction
instead of smoothing it**, against its own argument's direction. That is the
behaviour to copy.

### 3. `1aa75bd` — ADR 0026: every declaration branch prices the rival before the data

The general defect behind §A8 and §S8: **a registered rule that fires on an
observation the losing hypothesis predicts just as strongly.** It fires on
schedule, on the designed data, and establishes nothing — and **a registered
rule gets *less* scrutiny at the moment of use, because its authority came from
being fixed in advance.**

**This is now repo law. Apply it to every registration.** For each branch, write
what the rival predicts at that exact value; where they coincide, label the
branch **non-discriminating in advance**.

### 4. `b3fd15a` — the twelve-not-fourteen correction is not executable at four of its five sites

`ALL_CHECK_NAMES` has **12** entries (`backend/core/suppression.py:119-131`),
and five documents say fourteen. **Four of the five are registration bodies**,
which are never edited. So *"correct them as those files are next touched"*
**cannot run there**. The one checklist site is fixed; the rest are recorded.

**The design point survives everywhere**: all twelve codes contain underscores,
so the `instr`-not-`LIKE` predicate stands. **Do not append an amendment to a
registration to fix a count** — an amendment with no consequence for a threshold
or a decision rule dilutes the ones that have one.

## THE LEADERSHIP QUESTION IS DEAD. Do not re-open it, and do not re-scope it.

`docs/measurements/2026-08-11-preregistration-outcome-scored-leadership.md`
(`9e4cbaf`) prices the paired forecast-accuracy test that ADR 0021 §7's escape
hatch — *"Kalshi may be the sharp side"* — was said to need. **Verdict:
REFUSED ON POWER, with arithmetic.**

- The estimator is a mean of game-clustered paired Brier differences. In closed
  form `|t| = σ_d·√G`.
- At CLAUDE.md's own ~2c premise (`σ_d = 0.02`) it needs **~26,500 game
  clusters** — about eleven complete MLB seasons. **The record has 59 games
  across 34 recording instants.** A factor of ~440 in `G`.
- Even at the `suspicious_edge` ceiling on every game, max reachable
  `|t| = 0.38`. **The `G = 300` floor does not rescue it** — it was set for a
  different estimator and is off by two orders of magnitude here.

**Both provisional leads are discarded, not inherited.** The sign test *"needs
0.893"* is **non-discriminating at any `G`**: with a binary outcome both
hypotheses predict exactly 0.500. The Brier crossover at `G = 68` implies
`σ_d = 0.238`, twelve times the venue's stated accuracy.

**And the ADR 0026 finding survives infinite `n`:** `KALSHI-LEADS` coincides
exactly with the artefact rival — a consensus on 2–3 books of unproven
freshness, devigged by four methods that disagree by more than the whole
0.38-point headroom, is predicted to lose the paired Brier **for reasons
containing no information**. **This instrument can only return the answer nobody
proposed it to find.**

**Recommendation recorded: kill, not re-scope.** §0.7 prices the three obvious
re-scopings and none reaches `|t| = 1`. The escape hatch moves from *"neither
licensed nor refused"* to **refused for this instrument** — which is **not** a
claim that the escape hatch is false. **No dump is licensed, for this test or
any other.**

## DO NOT RE-OPEN THESE

**THE ODDS SCARE IS CLOSED.** *"Odds fetching stopped 2026-08-09T23:37:15Z"* led
two handoffs and is refuted **as a cause**: 22h 47m with zero in-scope fixtures,
then at 22:34:21Z the sweep **served**. Three attempts, the first two wrong.
**Prefer the observation that needs the least of your own machinery.**

**THE CLV DUMP IS REFUSED** — for the CLV instrument only. The registration
forbids declaring below `G = 300`; the record gives ~20 clusters. And the
question it was proposed for is now **§3 above: dead on power.**

## STILL OPEN

- **An ADR for the per-database / per-account credit gap** (Amendment A §A6).
  Urgency partly consumed by the P1 clause-3 fix at `39628e0` — the pre-flight
  now reads the account's live count. Real hole, no clock.
- **ADR 0020 — `stale_odds` reads a scrape clock.** **0020 stays reserved.**
  Quote **320**, not 440 or 335. **Waits on the 18:00Z result** — §7's mandatory
  qualifier *dictates* its permitted wording, so writing it first is writing a
  conclusion ahead of the rule that governs it. **This is the best first item
  for the post-capture session.**
- **`core/fees.py` cannot express the observed fee** — needs an **ADR, not a
  patch**. Six fills fit `k = 0.035` on MLB and `k = 0.070` on ATP with
  four-decimal rounding; `fees.py` expresses neither the split nor the
  granularity. **The ADR must decide whether the rate is per-category, and that
  needs item 2's fills.** Do not patch a coefficient in. **The `max()` hedge
  stays.**
- **An ADR for §A8's defect** — superseded by ADR 0026. Close it or fold it in.
- **ADR 0024 §5.1 / §5.2** — order path looser than suppression on depth.
  **REACHABLE ONLY**; `orders` is empty. §5.2 warns the one-line fix
  manufactures false confidence.
- **`decide_sweeps` reads only the daily ceiling** while `refusal_reason` checks
  three. Visible as a `refused` row, not closed.
- **Whether the dbt marts are computed over anything.** `publish()` has one
  caller — its own `__main__`. `ls /data/lake/recommendations` would settle it
  and **the ruling bans filesystem browsing**. **Unanswerable this session by
  any available means. Until then no dbt mart figure may be cited for live.**
- **Set the Anthropic spend limit.** Held at zero by `surfaced == 0`. **It
  switches itself on precisely when the project starts working.**

## GOVERNANCE — Joe's ruling, not a convention you may relax

`flyctl ssh console` against `kalshi-cockpit` may **only invoke a committed,
reviewed script by path**. No inline code, no `python -c`, no base64, no
filesystem browsing, no interactive session.

**The allowlist does NOT enforce this.** A permission pattern matches a command
*prefix* and cannot see inside `-C "..."`. **Three sessions wrote this rule and
two drifted from it within the hour.** Assume you will too.

**Deploys are batched and Joe's. Ask before money or a deploy. Do not ask
permission to continue** — Joe leaves 8-hour unattended stretches.

**The working phone check** (the old bearer-token one returns 401):

```
TOKEN=$(grep -m1 '^APP_AUTH_TOKEN=' .env | cut -d= -f2-)
curl -sS -c jar.txt -X POST -F "token=$TOKEN" -F "next=/" \
  https://kalshi-cockpit.fly.dev/session
curl -sS -b jar.txt https://kalshi-cockpit.fly.dev/api/window
```

## DECISIONS ALREADY MADE — do not re-put these to him

| Question | Decision |
|---|---|
| Round three, 4 cells or 5 | **CONTRADICTED — this row is not a decision.** It read *"(a) four cells, ~$3.66"*. `tasks/NEXT.md:90-93` records that cell `W` stays **UNRESOLVED** because Q-W was never answerable (`NEXT.md:74`), which is **not** §1.3's *"no series passed, `W` is not registered"* — so **§Power's four-cell branch is not licensed**. `scripts/watch_fee_bands.py:39-51` refuses to collapse the same distinction. Per line 12-13, NEXT.md's top supersedes this file: **read NEXT.md, not this row** |
| Is the $5 still worth spending | **Yes.** `core/fees.py` cannot resolve itself; it needs a fill |
| When Joe places the orders | **On his clock, any time before 2026-08-31** |
| When the watcher runs | **At the moment he places, never in advance** |
| Who fires the 24-credit poll | **Done — a scheduled task, decoupled from any session** |
| Partner's `stale_odds` finding | **ADR 0025.** The audit shrank it tenfold |

**A governance defect this table caused, and it is the reason row 1 now reads as
it does.** *"Do not re-put these to him"* outranked fresher evidence sitting in
the same repo: `NEXT.md:90-93` had already withdrawn the four-cell branch, and
$3.66 stayed queued against it because this list is read as settled rather than
as dated. **A decision list is a cache, and this one had no invalidation.**
Before quoting any row here, check whether NEXT.md's top has overtaken it — line
12-13 says it wins, and a row that has been overtaken must say so rather than go
quiet.

## THE STANDING SUSPICION — twelve guards that could not fail

**"This check is green" is unproven until the check has been seen to go red.**

**1–7** across earlier sessions. **8**, self-inflicted: a test asserted the
contested premise as a module constant and mutated only the arithmetic nobody
disputed. **9 and 10**: `capture_fills_fixture.py` had no return statement and
no test file; `test_a_stale_book_suppresses` anchored at **4×** its threshold.
**11 was not code** — Amendment A **§A8**, a *registered decision rule* that
fired correctly and established nothing.

**12, found 2026-08-11:** `scripts/analyse_odds_repeat_poll.py` — **481 lines,
no test file, imported by nothing, and about to read a one-shot 24-credit
capture.** Three real defects, one of which printed **CONFIRMED off a single
poll**.

## HOW THIS SESSION WAS WRONG

1. **I armed a one-shot money-spending timer inside the session and told Joe to
   keep the session open for six hours.** That was a bad design and he caught
   it, not me — *"is 6am pst here, you sure you don't want me to start a new
   session?"* **Anything with a wall-clock deadline goes to the OS scheduler,
   not to a Monitor, a background bash job, or a chained wakeup.**
2. **`TaskStop` reported success and the waiter was still alive.** It kept
   spawning `sleep` children for minutes afterwards. Two live waiters would have
   spent **48 credits**. **Verify a stopped background job with `ps`, never with
   the tool's own success message.**
3. **I let a subagent's brief carry a stale denominator** — "thirty-four
   scripts" is **forty-two** `scripts/*.py`. The lane caught it. Two of them
   ship either way.

### Earlier sessions — still live

1. **A registration's body is not the registration.** Grep any registration for
   `Amendment` and read the amendment's section titles **first**.
2. **The power of an instrument is not the power of the question.**
3. **An unchecked negative was published in the same commit as a lesson about
   unchecked negatives.**
4. **A subagent's confident negative was wrong and load-bearing.** **Re-run a
   delegated negative yourself before acting on it.**

## TRAPS

- **`start.md` is a snapshot; `git log` is the record.**
- **A background job reported stopped may still be running.** Check `ps`, and
  check for respawning children, not just the parent.
- **Mutation testing in a shared working tree makes every concurrent suite run
  untrustworthy.** A full-suite run from another lane at ~12:30Z reported 2
  failures that were another lane's mutation battery mid-restore. **Do not chase
  a failure in a file a concurrent lane owns without asking it first.**
- **`Dockerfile:66` does not decide what ships. `.dockerignore:59-61` does.**
  **Two of forty-two `scripts/*.py` are in the image.** Cite both lines or
  neither.
- **A status word in a handoff may be a human's summary, not the instrument's
  output.** `PREMATURE` led two handoffs and appears nowhere in the script.
  **Grep the named instrument for the literal token.**
- **A mutation that stays green may be semantically equivalent.** Record it;
  do not prune it to make the count clean.
- **Quote the pin beside every count.** `clean == 614` is identical at pin 1549
  and 1564, which is how a paragraph of pin-1549 figures got quoted against a
  pin-1564 result.
- **Two lanes in one working tree fight over git. Add by explicit path, never
  `git add -A`.**
- **"Routed separately" in a document is an unassigned task, not a handoff.**
  Route it to the lane that owns the file, explicitly, or it lands nowhere.
- **Every push publishes to the world immediately.** Push protection is ON.
- **The five Dependabot alerts are parked deliberately** — build-time only.
- **`?event_ticker=` ignores `limit` entirely** on Kalshi.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.**
- **`ruff format --check` reports ~153 files, pre-existing and enforced nowhere
  — do not "fix" it.**

## SETTLED — do not re-derive or re-propose

- **ADR 0025 — the `stale_odds` re-opening is refused, and narrowly.** The real
  number is **23 rows / 9 clusters / 8 odds snapshots**; **836 of 859 (97.3%)**
  cannot be surfaced by removing the guard. **The mechanism inverts**: a scrape
  clock makes `odds_age_ms` a **lower bound**, so every rejection is correct
  under either reading and the defect contaminates the **clean** set. **Never
  write "844 of 935" as rows in play.**
- **`ALL_CHECK_NAMES` has 12 entries, not 14.** **Six of the twelve never fired
  on this record.**
- **One signal, not two.** `elo.py` has no production caller. **Do NOT wire it
  up.**
- **A-versus-F is owned by ADR 0023 and the deferral STANDS.** Expiry
  2026-08-31 UTC, default **A**.
- **`KXMLBGAME` cannot fill a sub-20c pre-game band.** 0 of 51,286; cheapest
  26.0c. Round two is dead **on reachability, not budget**.
- **AVAILABILITY IS NOT FILLABILITY.** Every band number is a stored quote. **The
  separating observation is one small order.**
- **`KXATPDOUBLES` is not in the record at all.**
- **Option E is closed. Verdict H3 minus.** Model A's **coefficient** is
  confirmed to seven decimals at the ATP cell — only its cent ceiling is
  refuted. **Never write "Model A is refuted" bare.**
- **The coefficient is not one number across the record.** ATP matches
  `k = 0.070`; the five MLB fills match `k = 0.035`. **That is a hypothesis
  generator, not a finding** — two cells, one sport, one day, and it is the
  largest piece of good news anywhere in this record. **The `max()` hedge stays;
  the verdict stays H3−.** Never write *"the fee is 0.035"*.
- **H4 is UNTESTED, not pending and not confirmed** — and load-bearing:
  `settlement_fee()` (`core/fees.py:197`) feeds `core/ev.py:89,140`,
  `core/parlay.py:213`, **and** `scripts/rescore_fee_models.py:128` and
  `scripts/run_clean_shortfall.py:157`. §A8's declaration rule must not be
  applied.
- **The joint bound is dead on every population. H3b is REFUTED — sign only.**
- **Say `59 games across 34 recording instants`, never `614 rows`.**
- **The tautology objection is NARROWED, not withdrawn** — it covers **73.0%**.
  The other 27.0% returned **6 positive edges across all 423, every one
  suppressed, max +15.06 tenths** — not "nothing".
- **`betfair_ex_uk` is ABSENT — 0 rows, whole window.** Do not add the `uk`
  region. Every *"anchored on the sharps"* means **at most three books**.
- **Arming real trading is a code change** (ADR 0018), and ADR 0024 adds a
  precondition — satisfied in the repo, **not deployed**. **There is no minimum
  order size.** **Kalshi's `occurrence_datetime` runs exactly 3 hours late.**
- **`data/lake/` holds 847 rows of 2025 demo seed data.** The only safety is
  that nothing calls `publish()`.

## Standing instructions from Joe

1. **Call `partner` first** and let it set the queue. **Delegation is its call.**
   *Its output is not exempt from rule 3.* On 2026-08-11 it was **right about
   the biggest thing on the board** — it found the untested instrument — and
   the day before it produced four errors in one report.
2. **Parallelise by default — two concurrent lanes, never more.**
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news — and **especially a kill**. On 2026-08-11 it narrowed a
   *"§7 passes"* verdict to find an unpriced good-news branch hours before the
   spend. **It has never yet been wrong on this project.** But note this
   session's twist: **the lane it audited then corrected *its* arithmetic**, and
   was right. **Nobody is exempt, including the auditor.**
4. **Deploys are batched and Joe runs them.**
5. **Don't ask permission to continue. Do ask before money or a deploy.**
6. **Say unprompted when the session should end.**
7. **Watch the build-to-measure ratio and say so when it is wrong.** Joe raised
   it on 2026-08-11. The three questions at the top of this file are the answer;
   if a session's work is not one of them, say why out loud.
