# Start prompt — paste this to open the next session

Rewritten **2026-08-11 ~06:30Z**. The session that **gave two untested scripts a
verdict they never had**, **had one backlog claim shrunk tenfold and its own
headline claim reversed, both by audit**, and **found the inspector was never on
the deployed machine at all**.

Say *"read start.md and follow it"*, or paste this whole file.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md`. NEXT.md is the
actionable checklist and **its top supersedes everything here**.

## ⏱ DO THIS FIRST — it is time-boxed and it is today

```
.venv\Scripts\python.exe scripts\capture_odds_repeat_poll.py --dry-run
.venv\Scripts\python.exe scripts\capture_odds_repeat_poll.py --confirm-spend-24
```

**Joe decided 2026-08-11 that a session fires this unattended.** 24 credits,
already authorised, nothing spent yet.

**P4 passes only between 17:30Z and ~22:00Z on 2026-08-11** — measured free from
ESPN. Outside that the script refuses and spends nothing, so **run the dry-run
first regardless of the clock**: it is free and it prints the next kickoffs.

**There is no second attempt at a slate.** Four polls over ~15 minutes; an abort
halfway loses all 24 credits and the slate has moved. Do not start it on a
flaky connection.

**Its value went UP on 2026-08-11**: ADR 0025 §5 establishes that **no unit test
in this repo can separate the two readings of `last_update`**. The poll is the
registered instrument and there is no cheaper substitute.

**If the window has passed**, re-derive the next one free — the dry-run prints
the kickoff list, and `check_slate()` in that script can be called at candidate
`T0` values without spending anything.

## FIRST — check this file before you trust it

Run these three, in this order, before acting on anything below:

```
git log --oneline -25
git rev-list --count origin/main..HEAD
git status
```

**The tip at writing was `57d2ad5` and by the time you read this that is
wrong** — a handoff cannot count its own commit, and this guard has been needed
at nine, at twenty-one, and twice more since. At writing: tree clean,
**2,296 tests pass**, `ruff check .` clean.

**⚠ `57d2ad5` was NOT pushed.** Joe authorised one push explicitly (through
`faa9d43`) and was asleep when the settlement result landed. **Check
`git rev-list --count origin/main..HEAD` and ask him before pushing** — every
push publishes immediately.

**Treat every command in this file as a test never seen red** unless it says it
was run. A previous edition's headline health check returned 401 and always
would have.

## ✅ THE 05:30Z CAPTURE HAS RUN. Exit 0. Do not re-run it for §A5.

Ran **2026-08-11T05:32Z**. Settlements **55 → 58**, fills **0 → 6**. §A5 has
returned a value. Full write-up:
`docs/measurements/2026-08-11-settlement-fee-capture-result.md`, audited by
`measurement-skeptic` → **SURVIVES NARROWED**.

**What it settled:** reading 3 (the cent-display rule) is refuted — **for
`KXMLBGAME`, on 2026-08-11 only.** §A2.1's confound is **worse** here than at
fill time: the ATP position has not settled, so there is **no cross-sectional
lever at all** and category and era differ together.

**What it did NOT settle, against the first reading of it — including mine:**
**H4 is UNTESTED, not confirmed.** The observation landed in the branch of
Amendment A **§A8** where its two readings are indistinguishable. **§A8's
declaration rule is logically defective — a future session must not apply it.**
It is the *second* defective auxiliary reading in that registration (§S8 records
the first). The H4 denominator is **1, not 3**: two positions lost, and at
settlement `P ∈ {0,1}` a `k·C·P(1−P)` charge is **identically zero**.

**This LOWERS confidence.** `settlement_fee()` (`core/fees.py:197`) is consumed
by `core/ev.py:89,140` and `core/parlay.py:213` — **every EV figure in the tool
rests on H4**, now explicitly untested rather than pending.

**⚠ THE NUMBER NOT TO ACT ON.** The MLB fills imply `k = 0.035`, which would put
the bar at **50.88%** against 52.00% — a 1.12-point drop on a 0.38-point
headroom, **3.9× the good news in the whole record**, from **two cells, one
sport, one day**. **The verdict stays H3− and the `max()` hedge stays.** Six
things must be true before the bar moves; they are listed in §3 of the result
document and **none of them are done**. Over-estimating the fee costs
opportunity; under-estimating it costs money.

**Still outstanding:** the ATP position `…CERETC` has not settled. **§S9 fixed
in advance that it must not be read** — two readings both predict $0.18 there.
Re-running the capture is free and would pick it up, but it **cannot**
discriminate anything, so it is not queued as evidence.

```
.venv\Scripts\python.exe scripts\capture_fills_fixture.py
```

Laptop only, needs `.env`, seconds, no money, no orders. The 05:30Z gate has
passed and the run is done — the command is kept here only because the ATP
position is still unsettled.

**CORRECTED 2026-08-11: this script has never returned `PREMATURE`.** That word
appears nowhere in it and never did — a human read the output twice and supplied
it. The settlements half had **no return statement at all** and fell through to
`return 0`, and the zero-fills branch returned *before* it could report, so the
exit code answering §A5 (which is about a **settlement**) was unreachable by
construction. Fixed 2026-08-11: six exit codes, `4` is a real PREMATURE, all
thirteen mutations seen red (`tests/test_capture_fills_fixture.py`, which is the
first test file this script has ever had). **Read the exit code, not the prose.**

**An absent settlement row is NOT a $0.00 charge.** The state is *premature*,
never *null*; **no zero may be recorded anywhere**. **R5 does not fire.** **The
ATP position may not be read alone** — `KXATPDOUBLES-…CERETC` expires first and
is registered as non-discriminating (result §S9). Predictions are committed —
**point at them, do not copy**: §S9 of
`docs/measurements/2026-08-10-fee-model-fill-calibration-result.md`, and
Amendment A §A5/§A8 of the matching pre-registration.

**§A5 HAS NOW RETURNED A VALUE** (2026-08-11T05:32Z). **H4 still remains
untested** — but for a different and stronger reason than "the data has not
arrived": the data arrived and landed in §A8's **non-discriminating branch**.
Round three's §6.2 substitution is **no longer pending on §A5**; check the
round-three registration for what, if anything, it now depends on, rather than
assuming this released it.

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

**Its value went UP on 2026-08-11.** ADR 0025 §5 establishes that **no unit test
in this repo can distinguish the two readings of `last_update`** — both return
the same answer for every input a test can supply. The poll is the registered
instrument and there is no cheaper substitute.

**MEASURED WINDOW, free, from ESPN:** P4 passes only between **17:30Z and
~22:00Z**. Before that the slate is too thin (0 events within 6h at 00:16Z, 2 at
17:00Z); after ~22:20Z a game starts inside the 20-minute blackout. Re-check at
the real `T0` — the script decides P4 itself and spends nothing if it fails.

### 2. Round three — kit BUILT, scope DECIDED, waiting only on Joe's thumbs

$5.00 authorised 2026-08-10, hard expiry **2026-08-31 UTC**, **nothing spent**.
Joe places the orders **by hand on his phone**; the order path is disarmed and
arming is a code change (ADR 0018).

> **There is nothing to decide and nothing to prompt him about.** Scope is
> **four cells, ~$3.66** (decided 2026-08-11). Placement is **on his clock, any
> time before 2026-08-31**. Do **not** generate a phone sheet in advance and do
> **not** chase him for it — if he asks, run the watcher then.

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

**THE DECISION — MADE. Do not re-put it to him.**

> **Cell `W` is UNRESOLVED, and that is NOT §1.3's "no series passed".** Q-W
> reads `kalshi_quotes` on the live record; the laptop's `kalshi.db` is empty and
> `inspect_live_db.py` **cannot read that table** (see item 3). So **§Power's
> four-cell branch is not licensed** — nothing has failed, nothing has been run.
>
> **DECIDED 2026-08-11 by Joe: (a), four cells, ~$3.66.** The case for (b)
> rested entirely on a deploy being free because one was already coming. It
> was not — see the `.dockerignore` correction in item 3. Option (b)'s real
> price is a widening of what ships to the money machine, plus a query, plus a
> deploy carrying nothing else.
>
> **The cost of (a) is stated, not hidden:** if the vector comes back all-LOW it
> declares **H-SERIES, H-SPORT and H-NOTIONAL at once**, and it must be reported
> as a **three-way non-separation** — not as three findings.
>
> **Cell `W` stays UNRESOLVED**, which is *not* §1.3's "no series passed", so
> §Power's four-cell branch is still not licensed. Nothing failed; nothing ran.
>
> **Placement is on Joe's clock** (decided 2026-08-11): the phone sheet is a
> standing procedure, the watcher runs at the moment he places and not before,
> any time before the **2026-08-31** expiry. A sheet generated in advance is
> stale quotes wearing the look of a live board.

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

**CORRECTED 2026-08-11 — and the correction killed option (b).** This block used
to say a `kalshi_quotes` query "reaches the machine only at the next deploy",
citing `Dockerfile:66`. **A deploy is not sufficient and no deploy is pending.**

- `.dockerignore:59-61` is `scripts/*`, `!scripts/run_loop.py`,
  `!scripts/migrate_db.py`. **Two of thirty-four scripts ship.**
  `inspect_live_db.py` is not one of them, so it has **never read the
  production database** — its tests build a `tmp_path` file from the schema
  (`tests/test_inspect_live_db.py:85-96`).
- `git diff --name-only 799a5f3..HEAD` (the deployed SHA to HEAD) touches
  **zero** files that enter the image. So "recommend (b) if a deploy is coming
  anyway" resolves to: **a deploy is not coming anyway.**

Option (b) is therefore a `.dockerignore` widening **plus** a new query **plus**
a deploy that exists only to carry them. **Joe chose (a): four cells.**

### 4. Still open — two entries sharpened on 2026-08-11, the rest unchanged

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
  patch**. The `max()` hedge stays. **This got sharper on 2026-08-11, not
  softer:** the six fills fit `k = 0.035` on MLB and `k = 0.070` on ATP with
  four-decimal rounding, and `fees.py` can express neither the split nor the
  granularity. **Do not patch a coefficient in.** The ADR has to decide whether
  the rate is per-category before any number changes.
- **An ADR for §A8's defect.** A registered decision rule declared a hypothesis
  on an observation its rival predicts equally well. That is a *design* failure
  in how this project writes registrations, and it has now happened twice in one
  document (§S8 is the first). Worth its own ADR so the next registration's
  rules are written with both branches priced.
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

## DECISIONS JOE MADE ON 2026-08-11 — do not re-put these to him

Taken in a `/grilling` session. They are settled; execute them.

| Question | Decision |
|---|---|
| Round three, 4 cells or 5 | **(a) four cells, ~$3.66.** Option (b) died with the `.dockerignore` finding — no deploy was coming anyway |
| Is the $5 still worth spending | **Yes.** `core/fees.py` cannot resolve itself; it needs a fill |
| When Joe places the orders | **On his clock, any time before 2026-08-31.** Phone sheet is a standing procedure |
| When the watcher runs | **At the moment he places, never in advance.** A pre-generated sheet is stale quotes wearing a live board's look |
| Who fires the 24-credit poll | **This session, unattended**, inside the P4 window |
| The 05:30Z capture | **Fix the script first, then run.** Done at `aaf163a` |
| A repeat blank from the capture | **Write it up as a defect. Do not retry on a schedule.** A repeat blank means §S9's expiry clock is what to question |
| Partner's `stale_odds` finding | **ADR it, skeptic-gated.** Done — ADR 0025, and the audit shrank it tenfold |

## THE STANDING SUSPICION, and it caught this session's own work

**Eleven guards have now been found that could not fail.** **"This check is
green" is unproven until the check has been seen to go red.**

**1–7** — found across earlier sessions, three of them caught by a different
agent than wrote them.

**8, self-inflicted.** A test class written to defend a refusal asserted the
contested premise as a module constant and then mutated only the arithmetic
nobody disputed — **verified everywhere except at the one point that carried the
argument**, by the author who needed that point to be true.

**9 and 10, found 2026-08-11 in code nobody had tested.**
`capture_fills_fixture.py`'s settlements half had **no return statement** and
fell through to `return 0`, and the fills branch returned *before* it could
report, so the exit code answering §A5 was unreachable by construction. That
script had **no test file at all**. And `test_a_stale_book_suppresses` anchored
at **4×** its threshold, so an off-by-one in the limit stayed green while its
docstring asserted the semantics the code corrects.

**11 is the one to study, because it was not code.** Amendment A **§A8** is a
*registered decision rule*, and it is logically defective: it declares H4 on an
observation that the losing hypothesis predicts just as strongly. It fired
correctly, on schedule, on data that arrived exactly as designed — and it
established nothing. **A registered rule gets less scrutiny at the moment of
use, not more, because its authority came from being fixed in advance.**

Every guard shipped 2026-08-11 states the mutation that killed it: **13** for the
capture script, **4** for the staleness boundary. One mutation was applied and
**stayed green** — semantically equivalent, so it proved nothing — and it is
**recorded in the docstring rather than pruned**, because a mutation list is a
claim about what was verified.

## HOW RECENT SESSIONS WERE WRONG. Read these before doing analysis.

### 2026-08-11 — three, and two were mine rather than a subagent's

1. **I reported a result an hour before the audit killed it.** *"`BALMIN-MIN`
   won, so H4 has its separation"* — no. The observation landed in §A8's
   **non-discriminating** branch, and the losing hypothesis predicts the same
   equality unconditionally. **Ask what the rival hypothesis predicts at the
   exact input you observed, before recording any verdict.**
2. **I put a claim in an ADR without running it.** The ADR said a tenfold slip
   in the staleness limit would have survived the old 4× anchor. It would not —
   it goes red. One mutation settled it. **The rule about unchecked negatives
   applies to your own confident positives too.**
3. **The `partner` agent produced four errors in one report, all leaning
   toward cutting work from the board.** It self-corrected three; the fourth —
   quoting pin-1549 census figures against a pin-1564 result — was caught only
   by the audit. **A self-audit is not an audit, and the direction of an
   author's caught errors does not predict the direction of the missed ones.**

### Earlier sessions — still live

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
- **`Dockerfile:66` does not decide what ships. `.dockerignore:59-61` does.**
  `scripts/*` with `!run_loop.py` and `!migrate_db.py` — **two of thirty-four
  scripts are in the image.** Never conclude a file ships because a `COPY` names
  its directory; check the exclusion layer in the same breath and cite both
  lines or neither.
- **A status word in a handoff may be a human's summary, not the instrument's
  output.** `PREMATURE` led two handoffs and appears nowhere in the script it
  described. **Grep the named instrument for the literal token before repeating
  it.**
- **A mutation that stays green may be semantically equivalent, not a bad test.**
  One of thirteen was, this session. **Do not prune it from the list to make the
  count clean** — record that it was applied and why it proved nothing.
- **Quote the pin beside every count.** `clean == 614` is identical at pin 1549
  and pin 1564, which is exactly how a whole paragraph of pin-1549 figures got
  quoted against a pin-1564 result and reproduced perfectly on the one number
  anyone spot-checks.
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

- **ADR 0025 — the `stale_odds` re-opening is refused, and the refusal is
  narrow.** *"ADR 0021 rests on a guard that discarded the only rows that could
  have contradicted it, 844 of 935"* was audited **OVERSTATED**. The real number
  is **23 rows / 9 clusters / 8 odds snapshots**; **836 of 859 (97.3%)** cannot
  be surfaced by removing the guard. **The mechanism inverts**: a scrape clock
  makes `odds_age_ms` a **lower bound**, so every rejection is correct under
  either reading and the defect contaminates the **clean** set — ADR 0021 §7.5,
  which the claim cited while concluding its opposite. All 11 of the 23 that
  carry a close are **negative** (mean −18.64 tenths vs −5.12 clean), and **8 of
  23 are not pre-game**. **Never write "844 of 935" as rows in play.**
- **`ALL_CHECK_NAMES` has 12 entries, not 14** (`backend/core/suppression.py:119`,
  verified). Five committed documents say fourteen. **Six of the twelve never
  fired on this record.**

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
- **The coefficient is not one number across the record, and this is the live
  question.** The ATP fill matches `k = 0.070` exactly; the five MLB fills match
  `k = 0.035`. **That is a hypothesis generator, not a finding** — two distinct
  fee cells, one sport, one day, and it is the largest piece of good news
  anywhere in this record. It would move the bar from 52.00% to **50.88%** on a
  **0.38-point** headroom. **The `max()` hedge stays; the verdict stays H3−.**
  Six preconditions are listed in §3 of
  `docs/measurements/2026-08-11-settlement-fee-capture-result.md` and **none are
  done**. Never write *"the fee is 0.035"* or *"the bar falls to"*.
- **H4 is UNTESTED, not pending and not confirmed** — and it is load-bearing:
  `settlement_fee()` (`core/fees.py:197`) feeds `core/ev.py:89,140` and
  `core/parlay.py:213`, so **every EV figure rests on it**. §A8's declaration
  rule must not be applied.
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
   *Its output is not exempt from rule 3* — on 2026-08-11 it produced four errors
   in one report, all leaning toward cutting work off the board, and the audit
   caught the one it had missed itself.
2. **Parallelise by default — two concurrent lanes, never more.**
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news — and **especially a kill**. On 2026-08-11 it overturned
   a backlog claim (10× too large, mechanism inverted) *and* this session's own
   headline result (H4), and it was right both times. **It has never yet been
   wrong on this project. Budget for it rather than treating it as optional.**
4. **Deploys are batched and Joe runs them.**
5. **Don't ask permission to continue. Do ask before money or a deploy.**
6. **Say unprompted when the session should end.** Joe would rather start a clean
   one than watch a full one degrade.
