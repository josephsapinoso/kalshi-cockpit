# Start prompt — paste this to open the next session

Written 2026-08-09 ~15:25Z, end of the session that removed the duplicate pass
line, made exposure count the fee, found a fourth wrong wire key, built the
Playbook screen, and discovered that the combo lookup Joe authorised never
needed to be spent.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md, and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log.

## State

`main` is at `e26ab21` for code and a few docs commits above it — check
`git log -1`. Pushed, CI green on every push. **1,405 tests**, ruff
green, `next build` clean, six pages measured at 320/390/430 and looked at.

**Demo is deployed and verified** on the current image: six pages 200,
`instance_mode=demo`, `execution_available: false`, `/playbook` serving.

**Live is on `e950c49`** (machine `7812601a239428`, pass 38 at 15:18Z, healthy).
It does **not** carry this session's five changes. None is urgent: the gate is
locked, the order path is dry-run only, and the two money-path changes make it
stricter rather than looser. **Deploying live is Joe's call.**

    gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit

## READ THIS FIRST — the gate did not accumulate, and the reason is new

Read at 15:19Z on 2026-08-09, ~10 hours after the 20K odds key landed:

    15:18Z  gate progress (24h): actionable=0 of 300 needed, no_edge=177,
            suppressed=271; suppressed by: stale_odds=254, too_few_books=63,
            no_market_width=63, edge_within_method_noise=8, suspicious_edge=3

**`no_edge` is frozen at exactly 177**, the same figure recorded at 05:36Z. Not
growing slowly — not moving at all, across ten hours and twenty-odd passes.
`suppressed` creeps upward, `stale_odds` still dominates, `clv_rows_joined` is
still 190 and `clv_scored` is 0 on every pass.

**The budget stopped binding and the scheduler took over the same day.** Every
full pass from 13:47Z to 15:18Z reports a sweep decision of the form:

    no sweep: next slot is basketball_wnba at 15:45Z-16:15Z for 3 game(s)
    from 16:30Z, sweeping 45-15 min before first kickoff

So the 400/day budget is barely touched. `odds/timing.py` only fires 45–15
minutes before a fixture's kickoff, which is correct for freshness and means
odds are stale for most of the day — and a full pass writes rows all day
regardless. `events_linked` sat at 16 and `fair_prices_written` at 32 for the
entire ten hours.

**That is the finding to carry, and it is a shape this repo already has a
lesson about:** two limits on one quantity, and the tighter one wins in
silence. The odds budget was relaxed 16 → 400 and the *next* constraint bound
immediately, so the visible symptom (`stale_odds` dominating) never changed.
Nobody multiplied out how many passes a slot-based scheduler leaves with fresh
odds.

**What to do about it is a real decision, not a bug fix.** The honest options:

1. **Accept it.** The tool is actionable in the pre-kickoff windows and nowhere
   else, by design. Then `actionable=0` after a full day of *those windows* is
   the answer, and 300 games is reached over weeks, not days.
2. **Sweep more slots per sport.** Cheap — the budget has room. It trades
   freshness at kickoff for coverage across the day, which is exactly the
   trade `odds/timing.py` was written to refuse.
3. **Change what the gate counts.** Only rows with fresh odds can be
   `actionable`, and those exist for ~30 minutes per fixture.

**Do NOT relax `MAX_ODDS_AGE_S` or any suppression threshold.** That is how a
fabricated edge enters the record, and the record is the product.

## The `discovery:` verification — answered, and the answer is "yes, but"

Two quote passes are on the record (pass 34 at 14:18Z, pass 36 at 14:48Z) and
**both printed a `discovery:` line**. That is not a defect: the line prints on a
quote pass when its numbers change, and they did —

    rejected not_game_level=7208 -> 7206 -> 7201 -> 7195 -> 7171 -> 7185

`not_game_level` drifts every pass as markets close, so the change-detector
almost never suppresses anything. **The mechanism works exactly as written and
buys close to nothing**, because the dedupe key includes a counter that is never
stable. If the volume matters, key it on the fields describing discovery's
*answer* — `priceable events` and `unknown_scopes` — not on the reject counts.

The volume worry is moot anyway: quote passes are rare now (2 of 7 recent
passes), because the window is open so seldom. Same root cause as the section
above.

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
near-independent, so their true rho is 0. Over 55 minutes, 46,916 markets:

    cross-game, TWO-SIDED, n=23    rho at mid  +0.003   sd 0.089
    cross-game, ask only,  n=308   rho at ask  +0.234   sd 0.254

At the mid the method returns the right answer. **The ask-only population is
refused** — sd 0.254 spanning −0.757 to +0.898, and a bias you cannot subtract
is a refusal rather than an offset. A 26-minute run replicates it.

**No same-game correlation has been measured.** 18 same-game combinations
appeared, none two-sided, and 17 of 18 had an ask outside the Frechet bounds.

**That refusal rate is the second finding**: 23% cross-game, 47% mixed, 94%
same-game. An ask above `min(marginal)` is one no dependence structure
produces, and the clean gradient through `mixed` is what same-game pairs
driving it looks like. Suggestive, not claimed — a stale leg quote is
identical. The sharper test needs no correlation: compare the combination's ask
against the cheapest leg's own **ask**. Leg quotes are now in the `--json`.

`docs/adr/0012`; both runs in `docs/measurements/`.

The lookup remains available for the one thing reading cannot do: pricing a
combination nobody has built.

## Work that is self-contained, if you want more

- **Is a same-game combination dominated by its own cheapest leg?** The
  sharpest open question and it needs no correlation estimate. 17 of 18
  same-game asks sat above `min(leg mid)`; if they also sit above the cheapest
  leg's *ask*, the combination costs more than a leg that pays out in a
  superset of cases — dominated outright, and directly checkable. Leg bids and
  asks are recorded in the `--json` as of the last run, so one more harvest
  answers it:

      .venv\Scripts\python.exe scripts\measure_combo_correlation.py --pages 4 --rounds 55 --interval 60 --json out.json

  Watch for the confound: a stale leg quote produces the same symptom.
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
