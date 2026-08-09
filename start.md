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

## READ THIS FIRST — Joe's bankroll is $100/week, not $1,000

Told to us at ~17:00Z on 2026-08-09, and it invalidates config that is deployed:

    fly.live.toml:97   BANKROLL_DOLLARS = "1000"
    config.py:196      bankroll_dollars: float = 1000.0
    config.py:200      max_exposure_dollars: float = 400.0

**Kelly sizing derives from the bankroll, so every suggested size is 10x too
large.** The demo's `BUY 15 / COST $7.54` would be one or two contracts at his
real number. Most concrete safety issue open, and a one-line change — but do the
arithmetic first, because it may not be a clean scale-down:

- The conservative fee model charges ~1c/contract on sports. On a 10c contract
  that is 10% of stake. At a $100 bankroll, quarter-Kelly on a 1-2% edge is a
  position of a few dollars, so there may be a **minimum viable bankroll below
  which this strategy cannot clear its own fee at all.** Work the number out and
  say it. If it is above $100, that is the finding and it gets said plainly
  rather than engineered around.
- `max_exposure_dollars = 400` against a $100 bankroll is a cap that cannot
  bind. Set it deliberately, not proportionally.

He also said he is **a beginner** and wants tooltips.

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

## OPEN TICKET — is ADR 0012's 94% same-game refusal rate real?

Full ticket at the top of `tasks/NEXT.md`. Short version: `leg_quote` cached
each leg for the **whole run**, so a combination found in round 40 was priced
against a leg quote from round 1 — 39 minutes stale. A stale leg quote is the
exact alternative explanation ADR 0012 names for its 94% figure, so **the
harness was manufacturing the confound the finding has to rule out.**

Fixed this session: cache cleared per round, `Quote.observed_ms` and
`Combo.created_ms` recorded. The test is a re-run compared against cross-game
23% / mixed 47% / same-game 94%. **Cross-game is the control** — if staleness
drove it, cross-game must fall too.

And read `n` first: **18**. Eighteen same-game combinations, none two-sided.
Have `measurement-skeptic` audit before anything is written into the ADR.

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
