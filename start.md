# Start prompt — paste this to open the next session

Written 2026-08-09 ~08:15Z, end of the session that removed the duplicate pass
line, made exposure count the fee, found a fourth wrong wire key, built the
Playbook screen, and discovered that the combo lookup Joe authorised never
needed to be spent.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md, and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log.

## State

`main` is `e26ab21`, pushed, CI green on every push. **1,405 tests**, ruff
green, `next build` clean, six pages measured at 320/390/430 and looked at.

**Demo is deployed and verified** on the current image: six pages 200,
`instance_mode=demo`, `execution_available: false`, `/playbook` serving.

**Live is NOT deployed** and is still on `f1fb326` (machine v25) — it does not
carry any of this session's five changes. Nothing about them is urgent: the
gate is locked, the order path is dry-run only, and the two money-path changes
make it stricter rather than looser. **Deploying live is Joe's call.**

    gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit

## The one number that matters, and it needs a full day

    gh workflow run Ops -f instance=live -f action=logs

Find `gate progress (24h)`. Last read (2026-08-09 05:36Z, two passes after the
20K odds key landed): `actionable=0, no_edge=177, suppressed=270`.

The 20K tier fixed the real blocker — `stale_odds` was ~97% of suppressions and
that was the 16-credit budget showing up as a row count. Over a full day, one of
two things is now true:

- **`actionable` starts growing.** The gate is accumulating for the first time,
  and the next question is `clv_rows_joined`, still pinned at 190.
- **`actionable` stays 0 while `no_edge` climbs.** That is the project's answer,
  honestly obtained, and worth as much as a yes. Say so plainly rather than
  reaching for another knob. **Do not relax `MAX_ODDS_AGE_S` or a suppression
  threshold** — that is how a fabricated edge enters the record.

Also check `stale_odds` has stopped dominating the breakdown. If it has not,
sweeps are firing but not landing where the fixtures are, and `odds/timing.py`
is the place to look.

## One verification still open, and it needs the odds window

The `discovery:` line was quietened on the quote cadence (`5907787`): full
passes always print, quote passes only when the numbers change. **Proven by
test, not yet observed on live** — quote passes only run while the window is
open, and it closed minutes after that deploy.

When a window opens, check `discovery:` appears once per *full* pass and not
once per quote pass. Until then it is pending, not confirmed. Note this needs
**live** to be carrying the change; it does not yet.

## Still blocked on Joe, and it is the binding constraint

**The four fee-calibration trades** — minimum-size orders at ~10c/30c/50c/80c
in the Kalshi app, a few dollars, read the true fee off `average_fee_paid`. He
pre-authorised them; they have not happened. `fee_predicted == fee_actual` is a
gate condition and no amount of CLV moves it. Say so plainly rather than
building around it.

**The combo lookup is no longer on this list** — see below.

## What this session closed

Five items, none of them deployed to live. Full detail at the top of NEXT.md.

1. **One log line per pass.** `pricing pass:` was a strict subset of
   `pass N ok`. The recorded reason it was "not removable" was wrong —
   `run_chain.py` has always printed the same dict. What it did carry uniquely
   is a pass that recorded and then died in scoring; that moved to
   `counts_survive_a_late_failure` in `run_loop.py`.
2. **Exposure counts the fee.** ADR 0008's gap 3, deferred across three ADRs as
   "needs a fee column". It needed no column — the fee is a function of two
   columns already stored. What blocked it was that exposure was a SQL `SUM`
   and the fee model is not expressible in SQL.
3. **The combo lookup was never needed.** Joint prices are readable for free
   from `/markets`. The authorised lookup is **unspent**. See below.
4. **`orderbook()` returned `{}` for every market on the exchange** — the
   fourth wrong wire key here. Fixed, and `tests/test_parsers_return_
   something.py` is now the mechanical guard that catches all four.
5. **Playbook screen** at `/playbook`. Research screen deliberately not built.

## Combos: a validated method waiting on a sample

**Kalshi mints ~700 provisional combination markets a minute**, `GET /markets`
returns them with `mve_selected_legs` and a live quote, and nothing has to be
created. Paging depth-first cannot find them — 5,000 consecutive markets span
6m48s of `created_time` and a quote decays in ~2 minutes — so you poll the
newest page instead.

    .venv\Scripts\python.exe scripts\measure_combo_correlation.py --rounds 26

**The control decides which estimator is admissible.** Cross-game legs are
near-independent, so their true rho is 0:

    cross-game, TWO-SIDED, n=12    rho at bid -0.135   mid -0.033   ask +0.137
    cross-game, ask only,  n=168   rho at ask +0.243   sd 0.235

At the mid the method returns the right answer. **The ask-only population is
refused** — its bias has sd 0.235, so it cannot be subtracted off, and a
same-game number drawn from it would be indistinguishable from the margin.

**No same-game correlation has been measured.** Two-sided combinations are 42
of 23,847 markets and none of the same-game ones were two-sided. That is the
honest state. `docs/adr/0012`, raw run in `docs/measurements/`.

The lookup remains available for the one thing reading cannot do: pricing a
combination nobody has built.

## Work that is self-contained, if you want more

- **The `not invertible` rate.** 51 of 229 combinations had an ask outside the
  Frechet bounds for their own legs — ~22%. Most is probably legs moving after
  the combination was minted, but it has not been checked, and a systematic
  cause would mean a marginal is being read wrong for some market type.
- **Research screen — do not build it yet.** It reads Scout findings; there is
  no table, the agent is called by nothing, and wiring it means billed
  Anthropic calls on a schedule. A screen over a structurally empty source
  looks like a feature. Say so rather than building it.
- **`ws.py` has still never opened a socket on live.** It cannot until a row
  surfaces.
- **In-play is still an open question** — Joe rejected closing it. Reopening
  means designing the regime, starting with what replaces the closing line.

## Traps that bite, from this session specifically

- **A search whose ordering correlates with what you are looking for cannot
  report absence.** Three separate `/markets` walks returned zero quoted
  combinations and each felt like more evidence. Depth in a cursor walk *is*
  age there, so the walk was measuring its own latency. Widening it is the
  least informative next move — change the axis.
- **A test that two paths agree cannot see a defect they share.** The exposure
  ticket and the exposure cap were pinned against each other and both left the
  fee out. Ask what both would have to get wrong for the pinning test to stay
  green, then check that.
- **Assert that a parser returns something NON-EMPTY.** Four wrong wire keys,
  every one returning a well-formed empty collection. Nothing else catches
  them, because every assertion about the *contents* is vacuously satisfied.
- **Look at the page after the overflow check passes.** It found three defects
  the measurement could not, including `{floor} observations` rendering as
  `100observations` and a sixth nav link pushing the Gate off-screen.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.** The budget
  is shared with live.

## Do not repeat these inferences

- `active_quoters` is `[]` on **all 14,240** published collection legs while
  those same leg markets are two-sided with real open interest. It is not a
  liquidity signal.
- `/markets` is ~99.8% `KXMVE` — that is a fact about discovery hygiene, and
  the reason is now measured: ~700 user-built combination markets a minute.
