# Start prompt — paste this to open the next session

Written 2026-08-09, late. The session that ran six lanes in parallel, had three
of its own documents audited, and watched the arithmetic reproduce to the digit
in all three while the conclusions were wrong anyway. Read the corrections
section before quoting any number from this file.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log.

## State

`main` is at `a60f4bb`. **1,732 tests**, ruff clean, tree clean, pushed.

**LIVE IS UNCHANGED and still runs `1d81d3c`.** Nothing was deployed this
session, no order was placed, no odds credit was spent, no gate was touched.
Health was read from the browser rather than inferred:

    instance_mode=live  live_trading_enabled=false  execution_available=false
    live_quotes_available=true  agent_fleet_configured=true
    retired_settings_set=[]

**So `main` carries code live has never run** — the market-result pass, the
league warning, the bounded residue. None of it writes a row until a deploy, and
a deploy is Joe's.

Six agents in `.claude/agents/`, loading automatically: **`partner`** (directs
the fleet — *delegation is its call, not the executing agent's*),
**`measurement-skeptic`**, **`pre-registrar`** (new — it owns the *before*),
**`sharp-bettor`**, **`kalshi-platform`**, **`runtime-realist`**.

**Standing instructions from Joe, which override defaults:**

1. **Call `partner` first** and let it set the queue.
2. **Parallelise by default** — independent items as concurrent worktree lanes.
   Six ran this session and all six landed.
3. **`measurement-skeptic` audits anything before it enters the record**, and
   especially when it is good news.
4. **Before shipping anything that runs at boot on live, ask what clears it if it
   fails.** Recovery needing `flyctl` is a laptop job; Joe works from a phone.
5. **Don't ask permission to continue.** Do ask before money or a re-deploy.

## THE BLOCKER — one tap, and everything is downstream of it

An agent cannot read the evidence record. `frontend/src/middleware.ts` gates
everything except `/api/health`, `/login`, `/session` and three static files, and
an agent must not enter a password. **Joe signs in at
`kalshi-cockpit.fly.dev/login`, then opens `/api/ledger?limit=1000`.**

There is no local substitute. **`data/demo.db` is 100% synthetic** on four
independent tells, so every number in `data/lake/` and `data/warehouse.duckdb`
— including the "36 of 300" and "51 of 300" CLV buckets — is a number about
generated data.

The five questions it answers are enumerated in NEXT.md. The one that decides
the session: **has `run_scoring_pass` ever returned `scored > 0` on live?** Two
prior runs recorded 0. Both bugs are fixed in source and nobody has confirmed a
non-zero count. If it is still zero, the top item is fixing scoring.

## READ THIS — the pattern that produced every correction

Three documents were audited. **In all three the arithmetic reproduced exactly** —
every cell of a power table, every Wilson interval, every fee row — and in all
three the conclusion was wrong, because the numbers from *outside* the code were
assumed and never labelled.

The clearest specimen: a correct covariance identity, a correct multiplication,
and a spurious-slope estimate of **0.16 that was off by ~230x**, because one
factor was a plausible guess. It was called "the largest finding in this
document" and made a *blocking* prerequisite. A measurement of the adjacent
quantity was sitting in `docs/adr/0006` and was neither cited nor used.

Internal consistency cannot catch this: the error is upstream of every operation
performed, and a document that survives the check reads as *more* rigorous.

**So: label every number computed from code / measured from data / assumed, and
count the third kind.** Before assuming a constant, grep `docs/adr` and
`docs/measurements` — this project had already measured it twice.

Two corollaries: **a grid is not a sample** ("1,206 of 1,206" is a deterministic
function's domain, not 1,206 observations), and **prefer a bound to a point
estimate on a small support** — the strongest result of the session was not
`sd = 0.27` but that `sd <= 2.5` is forced by the support, which closed the
question permanently.

## What the lanes landed

**The half-spread confound is dead.** 219 games / 438 markets / 78,047
market-minutes: the pre-game half-spread takes **exactly two values, 5 and 10
tenths, 99.71% at 5**; sd 0.27 per market-minute, **0.00 per game**. On a
two-point support `{5, 10}`, `sd = sqrt(p(1-p))·5 <= 2.5`, so the assumed 4 is
*arithmetically impossible* and no selection can push the spurious slope above
0.0625. **It returns the moment the recorder writes rows about spreads or
totals** — those live-quote at sd 47.2 and 22.8, and stay wide inside 60 minutes.

**The signal test is pre-registered and says WAIT.** Smallest resolvable slope is
2.28 at G=40 and 1.00 at G=100, where 1.0 is full lossless pass-through — the
ceiling of what can exist. **G=300 is the first point it resolves anything**, and
that lands on the gate's own floor independently. Amendment 1 fixes four defects
including a registered SQL predicate that did not exclude what it claimed
(`suppressed_reason` is comma-joined, so `NOT IN` retained every multi-reason
stale row) and a `beta > 1 -> BUG` rule that would have classified a true signal
as a defect half the time at G=300.

**Candles and derived asks agree 51/51**, integer-exact in tenths, including 8
sub-cent prices. ADR 0016 Phase 0 can proceed under three conditions — the
sharpest being that **the identity fails at the boundary**: where a side of the
book is empty a bar publishes `yes_ask = 1000` where `derive_yes_ask` correctly
returns `None`, which unhandled fabricates a 1c ask and reads as an enormous edge.

**`kalshi_markets.result` is written**, and its residue bounded: one tied game
went from 192 ERROR lines/day forever to 2 total. **Calibration now has inputs;
it is not yet possible** — the column has zero readers.

**Combo E2** is corrected to what its audit supports, and its follow-up settles
the mechanism: the engine term is **zero on 9 of 9 rows**, so the disagreement is
replica skew, not a pricing engine. What survives is direction-free: a
combination's `/markets` row is not a price you can transact at.

**`edge_tenths` is net of fees** and `schema.sql` said the opposite, plus four
more drifted comments. `audit-2026-08-07.md` had already found it as item 41 and
marked it **closed** — 41 bundled nine findings and this one was skipped.

## Traps from this session specifically

- **A worktree copy satisfied the has-no-caller detector.** `test_has_callers`
  was walking **132 backend `.py` files from other branches**, so a symbol whose
  only caller lived on an unmerged branch passed on `main` — in the one file that
  exists to catch exactly that. Parallel lanes made a previously-fine test unsafe.
- **A guard can stay green because a *stricter* guard downstream catches your
  deformation.** Break per guard, not per function. And a break that is the
  original expression rewritten is a faulty break, not a passing guard — that
  happened twice and was caught both times.
- **Closing a bundled audit item ticks the parts that were skipped.**
- **An exclusion with no warning is an accident, not a decision.** NFL preseason
  is spelled `"Pro Football Preseason"`; 726 markets across 48 events vanished,
  and the drift test covered `competition_scope` but not `league`.
- **Before widening a population, find the column that marks which one a row came
  from.** If there isn't one, widening is not a config change.
- **`?event_ticker=` ignores `limit` entirely** on Kalshi — it returned all 82
  markets of the largest event for `limit=1`. The old code was safe by a
  mechanism nobody had guessed.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.** The budget is
  shared with live.
