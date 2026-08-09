# Start prompt — paste this to open the next session

Written 2026-08-09 ~17:00Z, end of the session that refuted the scheduler
diagnosis, found the combo harness manufacturing its own confound, created three
agents, and learned that Joe's real bankroll is a tenth of what the tool assumes.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log.

## State

`main` is pushed and **CI green on all three jobs** (Frontend, Tests +
warehouse, Secret scan). 1,435 tests, ruff clean.

**Nothing was deployed.** Live is still on `e950c49` and carries none of this
session's work. `fly.live.toml` changed, so a deploy is now a real change rather
than a no-op. **Deploying live is Joe's call.**

Three new agents in `.claude/agents/`, loading automatically:
**`partner`** (Joe's equal in decision-making, directs both fleets),
**`measurement-skeptic`** (audits a claim before it enters the record),
**`sharp-bettor`** (reviews the product as someone who bets for a living).
Use them. `partner` is a good first call of a session.

## READ THIS FIRST — do NOT just set BANKROLL_DOLLARS to 100

Joe's real bankroll is **$100/week**, not the $1,000 in `fly.live.toml:97`. An
earlier draft of this handoff called that a one-line fix. **It is a trap, and
setting it would silently disable the evidence record.**

Verified by running `size_position` directly:

    bankroll  min_order  contracts  refused  constraint
      1000       10         15       False    kelly
       700       10         10       False    kelly
       400       10          0       True     below_min_order_contracts
       100       10          0       True     below_min_order_contracts
       100        3          0       True     below_min_order_contracts
       100        1          1       False    kelly

At $100 with the deployed `MIN_ORDER_CONTRACTS=10`, quarter-Kelly on the edges
this tool actually finds sizes to under one contract, so **every row is
refused**. And `gate.py:285` defines the counter as:

    "actionable": "r.suppressed_reason IS NULL AND r.suggested_contracts > 0"

So `actionable` would be **structurally 0 forever**, the 300-game counter could
never increment, and the Gate screen would go on saying "0 of 300, keep
recording" without ever naming the cause. Both review agents found this
independently.

**Two limits on one quantity, again**, and the repo has the lesson: at $100 the
minimum net edge needed to reach 10 contracts is ~10c at the 50c band, while
`edge_ceiling_tenths = 40` (4c) suppresses anything above 4c as a suspected
bug. **The two ranges do not intersect.** There is no price on the board where
an edge is simultaneously large enough to size and small enough to be believed.
Break-even is ~$250 at the wings, **~$300 before the 50c band works at all.**

### What to do instead

1. **Decouple the gate's counter from his real bankroll.** Score actionability
   against a fixed reference bankroll for the *counter*, and against his real
   bankroll for what he is *permitted to buy*. This relaxes nothing — the 300
   floor, the CLV noise guard, every staleness and suppression rule stay exactly
   where they are. It stops his deposit size from disabling the measurement.
2. **Replace the flat `min_order_contracts`, do not just lower it.** Measured,
   the Model A per-order rounding penalty it exists to prevent is **0.00c at
   50c** — the band the strategy trades — and 0.8c at the wings. A
   price-independent constant is standing in for a price-dependent quantity.
   `verify_positive_after_fees` in `sizing.py` already re-evaluates the order at
   the real size with the real fee; let that be the guard.
3. **Re-scale the caps, which are inert at $100.** `max_position_dollars=100`
   is 100% of bankroll, `max_exposure_dollars=400` is 400%, and
   `max_daily_loss_dollars=100` fires only after the whole week is gone. A
   safety system that cannot bind is worse than none, because it reassures.
   ~$15 / ~$40 / ~$25 reproduces the $1,000 ratios.
4. **Write the test that would have caught this**: at the configured bankroll,
   assert some edge below `edge_ceiling_tenths` produces a non-zero size. That
   test is the real deliverable; the config change is the easy half.

`BANKROLL_DOLLARS` should be his **running balance**, not his weekly top-up —
$100/week is a flow. Nothing in the config or the Gate screen makes that
distinction.

## The gate, re-evaluated under $100/week — and it should NOT be lowered

Joe asked for this explicitly. The gate is right, and it is answering a question
he is not asking.

**The gate governs whether *this software* places orders**, not whether Joe may
bet. He can open the Kalshi app whenever he likes. "I want to bet $100 this
week" is not an argument about the gate.

The 300-game floor does **not** scale with stake. It comes from what it takes to
detect closing-line value at all — practitioner consensus is 200-300 minimum —
which is a fact about statistics, not about bankroll. A smaller stake does not
make a weaker signal easier to detect.

At $100/week the risk is not ruin. It is **self-deception**: betting, losing
slowly, and believing the tool said so. Arming the order path on zero evidence
lets the software claim authority it has not earned, and the record — which is
the product — becomes a mixture of decisions the strategy made and decisions a
human made while looking at it.

**Two things do follow from the new information:**

1. **Spend the first ~$5 on the fee-calibration trades, not on a bet.** Four
   minimum-size orders at ~10c/30c/50c/80c in the Kalshi app, then read the true
   fee off `average_fee_paid`. They are a *gate condition* no amount of CLV can
   satisfy, and they recover ~0.25 of the 0.63-point edge the conservative fee
   model currently spends as a hedge. Highest-value use of week one by a
   distance, and it is instrument calibration rather than gambling.
2. **Stop presenting an empty board.** Joe's instruction — "the mispricing
   should be a factor, it shouldn't filter out prospects" — and the sharp-bettor
   review reached this independently. The resolution relaxes nothing:
   suppression and staleness keep governing what is **bettable** and what the
   order endpoint accepts; they stop governing what is **visible**. Show the
   whole slate ranked by edge, honestly labelled.

**Do not** reach the gate by changing what it counts. `docs/adr/0005` exists to
prevent exactly that.

## Next task: build the backfill

Agreed with Joe. It is the only route to 300 scored games that does not take
years — ~80 days of candlestick retention is ~1,200 MLB games — and the 20K odds
key is being kept for its historical-odds access.
`ODDS_DAILY_CREDIT_BUDGET` is back at 400, `ODDS_MONTHLY_CREDIT_BUDGET` is
13,000, and the gap to 20,000 is reserved for this.

**Three things to settle before writing the loop. Do not skip them.**

1. **Predict the outcome first, in writing.** The live engine has produced
   **0 actionable in ~200 fresh-odds decisions**. Nothing suggests it behaves
   differently over history, so the likely result is ~0 actionable out of
   ~1,200 and **the gate does not open**. That is not failure. Framed as "fill
   the counter" it looks like one; framed as **"measure the actionable rate at
   n=1,200 instead of n=200"** it is the most valuable thing in the project — it
   either ends this strategy honestly or overturns the current picture. Say
   which goal you are building for.
2. **Schema v6: a provenance column, before a single backfilled row is
   written.** `recommendations` has 27 columns and none records where a row came
   from. Write retrospective rows into that table and the evidence record
   becomes a silent mixture that `evaluate_gate` reads as one population.
   `docs/adr/0011` already fixed this one level down — `clv_horizon_hours` was
   added because `clv_tenths` was becoming "a silent mixture of two regimes".
   Same shape, one level up.
3. **Look-ahead is the whole risk.** Reconstructing a decision at time T from
   historical odds and candlestick bars is where hindsight leaks in. State, for
   every input, when it was observable relative to T. The convenient column is
   usually contaminated, and a backtest that flatters is worse than none.

Costing: historical endpoints are **10x per call**, which is why the daily cap
exists at all. `can_afford` checks three ceilings; unset means uncapped, never 0.

## CLOSED — ADR 0012's 94% is withdrawn, and so is its replacement

The re-run looked decisive: same-game refusal 94% -> 22.4% with the cross-game
control falling too. **`measurement-skeptic` refused it and was right.** See the
`docs/adr/0012` addendum. Three independent reasons, and the third is the one
that matters:

**A leg echo explains 86% of every domination event in every scope.** The
combination's quoted ask frequently *equals one of its own legs' costs* to
within 2c (base rate 3-7%), and **119 rows match a leg that is not the
cheapest** — impossible under any dependence structure. For that subset the
quote at the combination's ticker is evidently not a joint over
`mve_selected_legs`. Excluding echoes: cross-game 1.9%, same-game 3.3%, on 19
games, with overlapping intervals once clustered by game rather than by row.

Also: 17/18 is one expected outcome and should never have been a rate; and the
two runs are different populations (same-game 3.7% -> 16.3% of the sample).

**The next step is ~20 free API calls, not another 70-minute harvest.** Re-read
the near-leg tickers live and record whether the combo ask moves tick-for-tick
with the matched leg. If it does, MVE-as-correlation needs a different data
source. If not, the echo is a transient mint-time state and can be excluded by a
rule fixed in advance.

**Two bugs of mine that this exposed, both now fixed** and both worth carrying:
the contemporaneity filter was a **tautology** (one `round_ms` stamped on the
joint and every leg made the gap identically zero for all 2,116 rows, and it
printed "kept 2116 of 2116, dropped 0" as though that were evidence), and the
age table **silently dropped 69 negative-age rows** — inside the table built to
catch confounds.

## What this session established

- **`docs/adr/0014`** — the sweep schedule is accepted unchanged. The ten-hour
  "gate did not accumulate" panic was an **empty slate**: first in-scope kickoff
  16:15Z, frozen interval 05:51Z-15:45Z. Measured, the same slate plans **6
  slots covering 18 of 19 games**; loosening the separation buys exactly one more
  game. `scripts/measure_slot_coverage.py --date` re-measures it on any slate.
- A real window, read live at 15:46:44Z: **24 rows — 16 no_edge, 8 suppressed,
  0 actionable.** The honest answer on fresh odds.
- **`docs/adr/0013`** — period markets (12 WNBA quarter scopes) excluded by
  decision, not omission. The warning was narrowed, not weakened; three
  mutations each turn a different test red.
- **`docs/reviews/2026-08-09-sharp-bettor-ui-review.md`**, with a table marking
  which claims were re-verified against source. Three verified defects:
  **ages freeze when the feed is off** (`LiveBoard.tsx:124` guards the
  `setInterval` behind `enabled`, and `:171` renders `FeedStatus` only when
  enabled), **`/api/suppression` has no caller** (the fifth "built but never
  called"), and **the Ledger never renders `clv_tenths`** — the scoreboard does
  not show the score.
- **The power-ratings model has never run.** `model_probability` defaults to
  `None` and nothing in `backend/` assigns it, though CLAUDE.md calls it half
  the premise. Note the direction: it was specified as an *additional* filter,
  so its absence makes the tool **less** restrictive and does **not** explain
  `surfaced=0`. What it means is the tool has exactly one opinion — the
  sportsbook consensus — so it can only catch Kalshi lagging the books, and
  `lessons.md` already suspects Kalshi is the sharp side, which makes that set
  close to empty by construction.

## In flight when this session ended

- **The combo harvest was still running** (~70 min against a nominal 55; the
  per-round leg re-reads cost what they should). It writes
  `docs/measurements/2026-08-09-combo-domination.json` **only at the end**, so
  if the session was cleared the run is lost and must be re-run:

      .venv\Scripts\python.exe scripts\measure_combo_correlation.py ^
          --pages 4 --rounds 55 --interval 60 --json docs\measurements\<date>.json
      .venv\Scripts\python.exe scripts\analyse_combo_domination.py <capture>

- **Two UI reviews were running** — `partner` and `sharp-bettor`, both given the
  $100/week and beginner constraints, with Joe asking that their **consensus**
  guide the UI direction. If their output did not land, re-run them.

## Traps from this session specifically

- **A frozen counter is not evidence of a stuck mechanism.** Establish that the
  inputs existed over the interval measured. The wrong story was persuasive
  because it pattern-matched a lesson already in `lessons.md`, so it felt
  confirmed rather than proposed. Corollary: an explanation that predicts every
  observation you have is not thereby a good one — **ask what it forbids.**
- **A comment defending a design can sit four lines from the bug it hides.** The
  leg cache's comment claimed it preserved contemporaneity; it destroyed it.
- **`if x` is not `if x is not None`.** Written again this session, in new code,
  right after reading the lesson about it. An epoch-zero timestamp was being
  filed as missing.
- **An agent's confident number can be wrong.** A subagent reported the deployed
  odds budget as 16 by reading `config.py`'s default; the deployed value is 400
  in `fly.live.toml`, six lines under a comment saying so. Verify before
  repeating.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.** The budget
  is shared with live.

## Still blocked on Joe

- **The four fee-calibration trades.** More valuable than ever — see the gate
  section. Pre-authorised, ~$5, and a hard gate condition.
- **Deploying live.** Nothing from this session is on the live machine.
