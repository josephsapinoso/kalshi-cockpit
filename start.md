# Start prompt — paste this to open the next session

Written 2026-08-09 ~19:30Z. The session that fixed the bankroll trap, ran four
lanes in parallel, and then had five of its own claims corrected by
`measurement-skeptic` — including two that were refuted outright. The
measurements were right every time; the *prose about them* was wrong five times,
always toward the tidier story. Read the corrections section before quoting any
number from this file.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log.

## State

`main` is at `65584d7`, **committed but NOT pushed** — CI has not run on any of
this. 1,535 tests, ruff clean, `next build` clean, 11 dbt nodes green.

**Nothing is deployed.** Live is still on `e950c49` and carries none of the last
two sessions' work. `fly.live.toml` has changed substantially, so a deploy is a
real change. **Deploying live is Joe's call.**

Five agents in `.claude/agents/`, loading automatically: **`partner`** (directs
the fleet — *delegation is its call, not yours*), **`measurement-skeptic`**,
**`sharp-bettor`** (now written to treat Joe as its apprentice and teach the
craft, not only review the screen), **`kalshi-platform`**, **`runtime-realist`**.

**Two standing instructions from Joe this session:**

1. **`partner` decides what gets worked on and by whom.** Call it first. It may
   create new agent *roles* if the fleet is missing a standing perspective.
2. **Parallelise by default.** Four lanes ran concurrently this session and all
   four landed; the worktrees are cleaned up and merged.

## The bankroll trap is fixed. ADR 0015.

The previous handoff was right that `BANKROLL_DOLLARS=100` was a trap and wrong
about why in one respect. Both are now settled and measured.

**What shipped:**

- **Schema v6**: `recommendations.reference_contracts`, the same decision sized
  against a risk profile fixed in code ($1,000 / $100 / $400 / $100). The gate
  counts *that*, so the deposit cannot decide what counts as evidence.
  `gate.POPULATIONS`, the Discord digest, the Playbook screen and the warehouse
  all read it. Migration verified v5 → v6 on a real database, twice.
- **`min_order_contracts` deleted, and nothing replaced it.** The sizer already
  prices at the fee a *single* contract would pay, which is the most expensive
  per-contract fee any size pays — by proof, `ceil_cent(a·N) ≤ ceil_cent(a)·N`
  and Model B is N-invariant. So Kelly > 0 already implies +EV at any size. My
  first draft replaced it with a whole-order EV re-check; that check **can never
  fire** and was deleted as decoration. The property is asserted as a test
  instead. `MIN_ORDER_CONTRACTS` still set in an environment now **raises**.
- **Caps re-scaled**: $10 / $40 / $10 at a $100 bankroll — the same 10/40/10
  fractions the $1,000 profile used. The handoff's "$15 / $40 / $25 reproduces
  the ratios" was arithmetically wrong.
- **`BANKROLL_DOLLARS = 100`** in `fly.live.toml`, documented as the *running
  balance*, not the weekly top-up.

## READ THIS — five of my claims were corrected, two refuted

`measurement-skeptic` audited ADR 0015 before it entered the record, as CLAUDE.md
requires. It was right on every point.

**The one that inverts an argument:** I wrote that at $100 the old minimum
"refused every order the tool can produce" and that `actionable` was
"structurally 0 forever". **False.** 204 of the 999 asks survived — all at
0.1–10.1c or 88.1–98.8c, with up to 3.0c of room at 98c.

That is worse than my version, not better. The wings are where the fee is
largest as a share of stake (1c on a 10c contract is 10%) and where the devig
methods disagree most (2.03 points against 0.18 on an even line). So the guard
did not switch the counter off — **it restricted the evidence to the least
believable prices on the board.** Producing a record from those is worse than
producing silence.

Also corrected: break-even is **$250**, not $300 (closed form,
`10·0.52·0.48/0.04`); "monotonic" is false, the property is *maximised at N=1*;
an enumeration over sizes 1–200 was cited for a claim about all N;
`MAX_DAILY_LOSS_DOLLARS` *was* set in `fly.live.toml`; and the backfill is an
identity to the **recorded column**, not to the two sizings — rows that sized
1–9 contracts were stored as 0 under the old minimum.

**One real defect fell out of the audit**, not just wording:
`strategy_config_version` did not include `max_order_contracts` or the reference
constants, so my claim that the two regimes stay separable was false. Fixed.

**The lesson is in `tasks/lessons.md`:** distrust *every, always, never,
structurally, by construction*. Each is a universal claim, and every one of these
started as something measured and became a sentence with a stronger quantifier.

## What the four lanes landed

**`docs/adr/0016` — the backfill, designed but not built.** The headline is
arithmetic and it is decisive: 0 actionable in ~202 fresh-odds decisions gives a
95% upper bound of 1.47% per decision, so a 1,200-game backfill has a point
estimate of **0 actionable and a 95% ceiling of 35** against a floor of 300.
Reaching 300 would need a 25% per-game rate, and P(0 in 202 | that rate) is
2×10⁻¹². **The gate cannot be opened this way, and that is knowable now.** Build
it for the measurement, not for the counter — or do not build it. 28 inputs
enumerated for look-ahead: 12 clean, 9 partial, **7 contaminated**, and
`depth_at_ask` cannot be reconstructed at all. 9,600 credits, fits two months.
Phase 0 is free and urgent because the Kalshi half expires at 80 days.

**`docs/measurements/2026-08-09-combo-leg-echo.md` — TOO THIN TO ANSWER**, and
the agent correctly refused to activate its pre-registered exclusion rule. n=2
move events. **The test is not answerable at any cadence**: 45 of 50 matched
legs showed one distinct cost all window, and polling 5× faster produced *fewer*
move events. The useful find is exploratory: **3 of 8 quoted combinations had an
empty order book**, one reading `0.0000/1.0000` for 18 straight polls while the
list endpoint quoted it at 0.463. Every combo price this project holds — all
2,116 harvest rows — came from the list endpoint and was never checked against a
book. Experiment E2 is pre-registered in the doc and needs no leg to move.

**`docs/adr/0017` — the maker path.** Held behind a one-query precondition set by
`partner`: plot the edge distribution on the live record between the taker bar
and 1.00–1.50 points below it, restricted to 18c–82c. No mass there, kill the
maker line for free. Note the baseline correction — maker-vs-taker is **1.00 to
1.50 points**, not the 1.88 that comes from comparing against the sportsbook bar.

**The UI consensus items — 7 of 8 landed.** `53.8%` not `53.8c` everywhere
(including `engine.py`'s `reason_text`); the whole slate visible with rejected
rows labelled and untappable; `clv_tenths` on the Ledger; fee-inclusive total on
the card; variance rendered (SD reproduced exactly at $7.4778 before anything
was drawn); four permanent sentences instead of tooltips; and a `/rejections`
screen for `/api/suppression`, which had no caller. The eighth was already fixed
in `a92ac42`.

## Still blocked on Joe

- **The four fee-calibration trades.** ~$5, pre-authorised, a hard gate
  condition no amount of CLV can satisfy, and the highest-value use of week one.
- **Deploying live.** Nothing from the last two sessions is on the live machine.
- **Pushing `main`.** Committed, not pushed. CI has not run.

## Traps from this session specifically

- **A replacement guard can be decoration.** When removing a guard, first check
  whether the code downstream already handles what it was protecting against. If
  it does, assert the *property* that makes the guard unnecessary — do not write
  a new guard that cannot fire.
- **A comment naming a real hazard is not evidence the hazard is covered.** It is
  evidence someone knew about it. `min_order_contracts` was defended for the
  project's life on a true premise nobody traced downstream.
- **Ask of every counter: what could change this number that is not about the
  thing it measures?** A deposit, a deploy, an uptime, a config edit. If the
  answer is anything, the counter measures that too.
- **A test can assert the tautology it was written to prevent.** The combo
  contemporaneity test required every leg to carry its joint's stamp — which is
  exactly the bug that produced "kept 2116 of 2116, dropped 0". It passed only
  because a fake API answers inside a millisecond, so it was vacuous *and* flaky.
- **Schema evolution breaks a partitioned lake silently until it does not.**
  `read_parquet` needed `union_by_name`; without it the first added column is a
  hard failure of the whole warehouse, from a change in another subsystem.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.** The budget
  is shared with live.
