# Start prompt — paste this to open the next session

Written 2026-08-11 ~00:20Z. The session that **built round three's execution
kit**, **finished the live-database inspector**, and **had its own headline
result overturned by audit and rewrote it**.

Everything below the line is the prompt. Paste it whole, or say *"read start.md
and follow it"*.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md`. NEXT.md is the
actionable checklist and **its top supersedes everything here**.

## FIRST — check this file before you trust it

Run these three, in this order, before acting on anything below:

```
git log --oneline -25
git rev-list --count origin/main..HEAD
git status
```

**The tip at writing was `dd6ed11` and by the time you read this that is
wrong** — a handoff cannot count its own commit, and this guard has been needed
at nine, at twenty-one, and again here. At writing: everything pushed, tree
clean, **2,268 tests pass**, `ruff check .` clean.

**Treat every command in this file as a test never seen red** unless it says it
was run. The previous edition's headline health check returned 401 and always
would have.

## ⏱ TIME-SENSITIVE, free, and the window is OPEN if the clock has passed it

```
.venv\Scripts\python.exe scripts\capture_fills_fixture.py
```

**Not before 2026-08-11T05:30Z. Check the clock first.** It has returned
`PREMATURE` twice. Laptop only, needs `.env`, seconds, no money, no orders.

**An absent settlement row is NOT a $0.00 charge.** The state is *premature*,
never *null*; **no zero may be recorded anywhere**. **R5 does not fire.** **The
ATP position may not be read alone** — `KXATPDOUBLES-…CERETC` expires first and
is registered as non-discriminating (result §S9). Predictions are committed —
**point at them, do not copy**: §S9 of
`docs/measurements/2026-08-10-fee-model-fill-calibration-result.md`, and
Amendment A §A5/§A8 of the matching pre-registration. §A5 has still not returned
a value, so round three's §6.2 substitution stays **CONDITIONAL AND PENDING**
and **H4 remains untested**.

## DO NOT RE-OPEN THESE. Both led a previous handoff.

**1. THE ODDS SCARE IS CLOSED.** *"Odds fetching stopped 2026-08-09T23:37:15Z"*
led two handoffs and is refuted **as a cause**. Between the last in-scope kickoff
(2026-08-10T00:20Z, HOU @ SD) and the next (23:07Z, BOS @ TOR) there were **22h
47m with zero in-scope fixtures**. Then at **22:34:21Z the sweep SERVED** —
`spent_today` 0→6, `fixtures_upcoming` 13→29, and 08-11's MLB slots appeared
exactly as the registered prediction required. **The recorder is not dead and was
never shown to be.** Three attempts, the first two wrong, both in `lessons.md`:
attempt one used the live instance's own sweep plan, which is circular; attempt
two used a harness sharing the same planner, already recorded in ADR 0014 as
undercounting ~2x in the flattering direction; attempt three dropped the
estimator and printed a calendar. **Prefer the observation that needs the least
of your own machinery.**

**2. THE CLV DUMP IS REFUSED — for the CLV instrument only.** ADR 0021 §7's
escape hatch (*"Kalshi may be the sharp side, so the comparison is empty by
construction"*) **cannot** be closed by the registered CLV pass-through test at
any sample size this record supplies. The registration forbids declaring SIGNAL,
BUG or NO SIGNAL below `G = 300`; the record gives about **20** clusters. No
power arithmetic needed.

> **But do NOT read that as "the leadership question is closed", and this is the
> correction that matters.** The refusal was first written at the scope of the
> whole question and **an audit overturned it inside the hour**. The dump was
> proposed to supply *"who won"* — and **the CLV design needs no outcome column
> at all**. The question maps onto a **paired forecast-accuracy comparison**
> scored on `kalshi_markets.result`: different estimator, different null,
> **unpriced anywhere in this repo**. It is **neither licensed nor refused**.
> Two provisional figures exist as leads only — a paired sign test at `G = 60`
> would need a true rate above **0.893**, a paired Brier difference crosses over
> near `G = 68` — and **neither licenses a conclusion**. Designing that test is
> legitimate new work. Proposing a dump for it without a pre-registration is not.

## THE QUEUE

### 1. The repeat-poll capture — AUTHORISED, unblocks ADR 0020, and unrun

```
.venv\Scripts\python.exe scripts\capture_odds_repeat_poll.py
```

**Joe authorised 25 credits** (F9 widened, so the `/sports` pre-flight is
covered). **P1 was fixed at `39628e0`** — it now enforces clause 3 against a live
header and a `None` refuses; 30 tests, all 30 seen red under 19 mutations.
Amendment A is appended; the body is untouched.

**Check P4 at `T0` before spending anything:** no event commencing within 20
minutes, at least 5 within 6 hours. It is decided fresh at each `T0` and is the
registration's only time-bound. **The per-database / per-account credit gap
(Amendment A §A6) is still open and still has no ADR** — `CreditBudget` sums
*this* database's `api_credits` while the quota is per **account**.

**This is the highest-value runnable item on the board**, because ADR 0020's
`stale_odds` remedy waits on it and the credits are already granted. **Write the
remedy after the poll, not before.**

### 2. Round three — the kit is BUILT and Joe has a decision to make

$5.00 authorised 2026-08-10, hard expiry **2026-08-31 UTC**, **nothing spent**.
Joe places all five orders **by hand on his phone**; the order path is disarmed
and arming is a code change (ADR 0018).

- **The watcher**: `.venv\Scripts\python.exe scripts\watch_fee_bands.py --once`.
  **Run end-to-end against the live board on 2026-08-10** — it works. 64 tests,
  **20 mutations all seen red**. It enforces pre-game (`occurrence_datetime − 3h`;
  it skipped 72 in-play markets on that run), flags an imminent first pitch
  without filtering it, and prints the **first** qualifying market per cell —
  never a menu, because §3 forbids comparison between candidates.
- **The phone sheet**: `docs/round-three-phone-sheet.md`. Leads with the
  four-point check, because **P5 is the single most likely way this round is
  wasted** — round one's app defaulted to buy-in-dollars and produced
  `count = 0.27`.

**THE DECISION, and it is Joe's:**

> **Cell `W` is UNRESOLVED, and that is NOT §1.3's "no series passed".** Q-W
> reads `kalshi_quotes` on the live record; the laptop's `kalshi.db` is empty and
> `inspect_live_db.py` **cannot read that table** (see item 3). So **§Power's
> four-cell branch is not licensed** — nothing has failed, nothing has been run.
>
> **(a) Run 4 cells now** (~$3.66). Works. But the all-LOW vector then declares
> **H-SERIES, H-SPORT and H-NOTIONAL at once** and must be reported as a
> three-way non-separation.
> **(b) Add a Q-W query, Joe deploys, then run 5.** The fifth cell costs $0.39
> and buys real separation. Three weeks to expiry.
>
> **Recommend (b) if a deploy is coming anyway; (a) if not.** Do not decide this
> for him.

Justify the round on cells **`R`** and **`W`**, which earn on every branch
including `H-NONE`. **It is NOT the A-versus-F trigger** — ADR 0023's deferral
stands and every taker branch points at A. **Do not tell Joe it settles A vs F.**
Source of truth is
`docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`
**plus Correction A**. **Never edit a registration body; amendments are
appended.**

### 3. `inspect_live_db.py` runs — and answers 1 of the 4 questions it was queued for

Finished at `19bb3b6`: refusal block gone, **68 tests, 17 mutations all seen
red**, exits 0 on a real database.

**The handoff's claim that it "unblocks three questions at once" does not
survive its own whitelist**, which reads only `api_credits`, `odds_sweep_log`,
`kalshi_markets`, `kalshi_events`, `kalshi_series`, `closing_lines`, and
`recommendations` as a pinned ticker list.

| Question | Status |
|---|---|
| **Q-W** — cell `W`'s activation | **NOT ANSWERABLE** — needs `kalshi_quotes`, 0 occurrences |
| scored-game rate vs `gate.py`'s 300 floor | **NOT ANSWERABLE** — needs `recommendations` as a population |
| the 423 non-anchored rows | **NOT ANSWERABLE** — `fair_prices`, 0 occurrences |
| raw `closing_lines` | **PARTIAL** — pinned to `recommendations.id <= --pin` |

**Adding a `kalshi_quotes` query for Q-W is the highest-value change to this
file**, and it is item 2's option (b). A new query is a real change to what runs
against the money box: it needs its own review, and `Dockerfile:66` means it
reaches the machine only at the **next deploy**.

### 4. Still open, unchanged

- **An ADR for the per-database / per-account credit gap** (Amendment A §A6).
- **ADR 0020 — `stale_odds` reads a scrape clock.** Numbering runs 0019 → 0021 →
  0024; **0020 stays reserved**. Quote **320**, not 440 or 335. Re-derive free
  with `scripts/census_odds_stamps.py`. **Waits on item 1.**
- **ADR 0024 §5.1 / §5.2** — the order path is looser than suppression on depth.
  **REACHABLE ONLY**; `orders` is empty. §5.2 warns the obvious one-line fix
  manufactures false confidence.
- **`decide_sweeps` reads only the daily ceiling** while `refusal_reason` checks
  three. Now visible as a `refused` row, not closed.
- **`core/fees.py` cannot express the observed fee** — needs an **ADR, not a
  patch**. The `max()` hedge stays.
- **Whether the dbt marts are computed over anything at all.** `publish()` has
  exactly one caller — its own `__main__`. `ls /data/lake/recommendations`
  settles it, but that is filesystem browsing, which the ruling bans. **Until
  then no dbt mart figure may be cited for the live instance.**
- **Set the Anthropic spend limit.** Held at zero by `surfaced == 0`, not by a
  missing key. **It switches itself on precisely when the project starts
  working.**

## GOVERNANCE — Joe's ruling, not a convention you may relax

`flyctl ssh console` against `kalshi-cockpit` may **only invoke a committed,
reviewed script by path**. No inline code, no `python -c`, no base64, no
filesystem browsing, no interactive session.

**The allowlist does NOT enforce this.** A permission pattern matches a command
*prefix* and cannot see inside the quotes of `-C "..."`. **Three sessions have
now written this rule and two drifted from it within the hour** using read-only
one-liners. Assume you will too.

**Deploys are batched and Joe's. Ask before money or a deploy. Do not ask
permission to continue** — Joe leaves 8-hour unattended stretches.

**The working phone check** (the old bearer-token one returns 401; the gate is a
Next Edge middleware reading a `cockpit_session` cookie):

```
TOKEN=$(grep -m1 '^APP_AUTH_TOKEN=' .env | cut -d= -f2-)
curl -sS -c jar.txt -X POST -F "token=$TOKEN" -F "next=/" \
  https://kalshi-cockpit.fly.dev/session
curl -sS -b jar.txt https://kalshi-cockpit.fly.dev/api/window
```

## THE STANDING SUSPICION, and it caught this session's own work

**Seven guards found that could not fail**, three of them caught by a different
agent than wrote them. **"This check is green" is unproven until the check has
been seen to go red.**

**This session was the eighth, and it was self-inflicted.** A test class was
written to defend a refusal; it asserted the contested premise as a module
constant and then mutated only the arithmetic nobody disputed — **verified
everywhere except at the one point that carried the argument**, by the author who
needed that point to be true. It was rewritten. Every guard this session ships
states the mutation that killed it: 20 for the watcher, 17 for the inspector, 5
for the CLV rewrite.

## FOUR WAYS THIS SESSION WAS WRONG. Read these before doing analysis.

1. **A registration's body is not the registration.** A refusal was built on
   *"`beta = 1` is the ceiling of plausibility"* — a sentence Amendment 1 §A3
   **replaces outright**, in a file whose own header says the amendment governs.
   It was marked superseded in place, correctly, **and it was still the most
   quotable line in the file**. Grep any registration for `Amendment` and read
   the amendment's section titles first.
2. **The power of an instrument is not the power of the question.** Correct
   arithmetic about test A was used to cancel test B. **Nothing inside a correct
   calculation points at the question it is not about.**
3. **An unchecked negative was published in the same commit as a lesson about
   unchecked negatives.** *"These counts reproduce from no committed harness"* —
   they reproduce exactly, in one command. **The rule applies to your own claims,
   and there you will not notice.**
4. **A subagent's confident negative was wrong and load-bearing.** It reported a
   phrase appears in no ADR; `docs/adr/0021:34` has it. **Re-run a delegated
   negative yourself before acting on it** — and downgrade that agent's
   unverifiable claims too, because the failure was method.

## TRAPS

- **`start.md` is a snapshot; `git log` is the record.**
- **Backticks inside a shell-quoted Python string get executed by the shell.**
  Writing a markdown block containing backticks through `python -c "..."` cost
  several commands this session. **Bash heredocs also break** on a redirect
  operator in the content. **Write the content to the scratchpad with `Write`,
  then read it from a file in Python.** That works every time.
- **Two lanes in one working tree fight over git. Add by explicit path, never
  `git add -A`.** Verify every path in an ownership brief exists.
- **Read a lane's "left undone" section FIRST.** A seam between lanes is owned by
  nobody by construction.
- **"Routed separately" in a document is an unassigned task, not a handoff.** A
  correction sat one directory from an ADR that went on asserting the error.
- **Every push publishes to the world immediately.** Push protection is ON.
- **The five Dependabot alerts are parked deliberately** — four `postcss`, one
  `sharp`, build-time and unreachable at request time.
- **`?event_ticker=` ignores `limit` entirely** on Kalshi.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.**
- **`ruff format --check` reports ~153 files, pre-existing and enforced nowhere
  — do not "fix" it.**

## SETTLED — do not re-derive or re-propose

- **One signal, not two.** `elo.py` has no production caller. **Do NOT wire it
  up.** Any claim that two signals must "agree" describes a design, not the
  deployed system.
- **A-versus-F is owned by ADR 0023 and the deferral STANDS.** Expiry
  2026-08-31 UTC, default **A**. Do not re-open it on §5.4 — §7.2 cites it.
- **`KXMLBGAME` cannot fill a sub-20c pre-game band.** 0 of 51,286; cheapest
  26.0c. Round two is dead **on reachability, not budget**.
- **AVAILABILITY IS NOT FILLABILITY.** Every band number is a stored quote. **The
  separating observation is one small order**, and it has not been placed.
- **`KXATPDOUBLES` is not in the record at all.** Any ATP work needs a live board
  read first.
- **Option E is closed. Verdict H3 minus.** Model A's **coefficient** is
  confirmed to seven decimals at the ATP cell — only its cent ceiling is refuted.
  **Never write "Model A is refuted" bare.**
- **The joint bound is dead on every population. H3b is REFUTED — sign only**,
  with no "nearly clears" and no "clearly misses", at any `n`.
- **Say `59 games across 34 recording instants`, never `614 rows`.**
- **The tautology objection is NARROWED, not withdrawn** — it covers **73.0%** of
  the record. The other 27.0% (423 rows) was priced against a non-sharp consensus
  and returned 0 positive edges among the 189 unsuppressed (**6 positive across
  all 423, every one suppressed, max +15.06 tenths** — not "nothing"). Its
  conservative unit is **13 odds-observation stamps**, and it is **not** a partial
  run of option B.
- **`betfair_ex_uk` is ABSENT — 0 rows, whole window.** Do not "fix" it by adding
  the `uk` region: +50% credits for the same exchange as `betfair_ex_eu`. Every
  *"anchored on the sharps"* means **at most three books**.
- **Arming real trading is a code change** (ADR 0018), and ADR 0024 adds a
  precondition — satisfied in the repo, **not deployed**. **There is no minimum
  order size.** **Kalshi's `occurrence_datetime` runs exactly 3 hours late.**
- **`data/lake/` holds 847 rows of 2025 demo seed data** under `dt=2026-08-0*`
  names, and the reader is fully built. The only safety is that nothing calls
  `publish()`.

## Standing instructions from Joe

1. **Call `partner` first** and let it set the queue. **Delegation is its call.**
2. **Parallelise by default — two concurrent lanes, never more.**
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news — and **especially a kill**. It overturned this session's
   headline result and was right.
4. **Deploys are batched and Joe runs them.**
5. **Don't ask permission to continue. Do ask before money or a deploy.**
6. **Say unprompted when the session should end.** Joe would rather start a clean
   one than watch a full one degrade.
