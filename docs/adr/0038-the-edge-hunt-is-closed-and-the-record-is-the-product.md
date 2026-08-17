# ADR 0038 — The edge hunt is closed, and the record is the product

**Date:** 2026-08-17
**Status:** Accepted
**Closes:** the active search for a tradeable edge on Kalshi sports.
**Does not close:** the recorder, the harnesses, or ADR 0018.

## Context

This project was built to find out whether Kalshi's cost advantage converts into
a tradeable edge on sports — *not to assume one*. That question has now been put
to every quadrant this instance can reach, and every one has answered.

| quadrant | the question | verdict | where |
|---|---|---|---|
| Information vs sportsbook consensus | does devigged consensus predict Kalshi's close? | `beta = -0.141`, negative | ADR 0021, ADR 0034 |
| Information vs Kalshi's own prices | can an in-house model see Kalshi's error? | our error **exceeds** the disagreement | ADR 0036, ADR 0037 |
| Venue structure — `KXMVE` combos | is there a mispriced same-game product? | zero volume, zero open interest | ADR 0012 §5 |
| Speed — stale-quote pick-off | can we be first? | edge lives at ~400ms | predecessor project |
| Cost headroom | is 0.63 pts enough on its own? | it is a **discount, not a signal** | ADR 0027, ADR 0028 |

The last row is the one that makes this a closure rather than a pause. **A cost
advantage multiplies an edge; it does not create one.** 0.63 points of headroom
— itself an upper bound pending H4 — pays exactly zero to someone with no
opinion. Three quadrants were asked for an opinion and none supplied one.

The combo quadrant is the one this decision expected to find open. It is not:
ADR 0012 §5 records 18 same-game combinations observed across 55 minutes of
polling, **zero of them two-sided**, on markets flagged `is_provisional` with no
volume and no open interest. A quote on an untraded market is a quoter's
opinion, not a transaction.

## The framing that was rejected

The session that produced this ADR opened with the question *"should this tool
keep hunting, or be finished as a portfolio piece?"* **That is a false binary
and it is worth recording why**, because it is the shape of question that keeps
a project at 90% indefinitely.

`docker/entrypoint.sh` starts `scripts/run_loop.py` on the live instance
unconditionally. The record accumulates with nobody watching; the `G = 300` look
arrives on its own clock; `backend/analysis/signal_test.py` is signal-agnostic
and already built. **So "stop hunting" saves approximately nothing, and there is
no resource being traded.** What costs is treating the hunt as *active* — as a
thing with a next step, a backlog, and a reason to defer finishing.

The real question underneath was **"has the reachable space been exhausted, or
are we merely tired?"** The table above is the answer, and it was checked rather
than assumed.

## Decision

**1. No new edge-hunting line is opened on this instance.** Not the thinner prop
ladders, not `KXMVE`, not a re-parameterised rate model. A proposal to reopen
must first name which row of the table above it overturns, and with what
measurement.

**2. The recorder keeps running, unchanged.** It costs nothing, it is already
deployed, and the `G = 300` look happens without anyone's attention. **No plan
may depend on it**, which is the same standing rule CLAUDE.md already carries.

**3. The gate is untouched.** It is the live-trading interlock. It is not
lowered, not bypassed, and "the gate will open" remains forbidden as a step in
any plan. Closing the hunt does not relax a safety device; if anything it
removes the only motive anyone had to argue with it.

**4. The four harnesses are kept and are the deliverable.**
`measure_pitcher_k_decay`, `measure_in_season_vs_stale`,
`measure_home_run_ladder_scope`, `measure_kalshi_hr_pricing_error` and
`backend/analysis/signal_test.py`. The fourth is the reusable template —
**compare to the price, not to the outcome** — because it needs no settlements
and therefore no cluster wait.

**5. The 48%-unpriceable question is declined**, not deferred. Three independent
reasons, any one sufficient:

- **The premise is wrong.** 143 of the 238 failed `MIN_PA = 300`
  (`scripts/measure_kalshi_hr_pricing_error.py:78`) — a threshold *we* chose, so
  a batter with a readable 250-PA season sits in the "no history" bucket. 95
  were the name-matching defect, since fixed in `2893d8c`. Neither group is the
  "debuts and call-ups" the prose claimed. ADR 0037 now carries this correction.
- **Clusters bind, not rows.** All 493 markets come from **29 games**. Lowering
  `MIN_PA` adds rows drawn from those same 29 clusters against a registered
  floor of 300. The 95% interval is ±3.6 points against a 1.75-point bar — the
  identical arithmetic that got the calibration run *refused in registration*.
- **Our instrument is provably blunter there.** Detection requires
  `sd(model − ask) > sigma_model`. Where we had the *most* input history,
  `sigma_model = 4.04` against `sd(d) = 3.72` and the subtraction floored at
  zero. On a population with strictly less history `sigma_model` can only rise.

If closure in the record is ever wanted rather than this argument, the cheap
version is ~30 minutes and needs no model and no settlements: **measure the
dispersion of Kalshi's own asks on no-history versus history players.** A tight
cluster near the base rate means the market is saying "I don't know" too, and
there is no per-player opinion to disagree with. Note what that test can do — it
**can only kill**. A dispersed result still leaves you needing a model ADR 0037
proved you cannot parameterise.

**6. The repo is finished as a portfolio piece**, deliberately and out loud.
Remaining work is presentation and hygiene, not discovery.

## What this ADR does NOT decide

- **It does not tell Joe whether to bet.** This is a statement about what the
  **tool** may claim, not about what its owner does with his own money.

  > **Sourcing correction, same day.** An earlier draft of this bullet cited
  > ADR 0018 for the proposition that wagering on Joe's own judgement sits
  > outside the gate *by design*. **ADR 0018 decides no such thing.** It decides
  > that arming real trading is a code change, and enumerates the four barriers.
  > What it does record, in "What this does NOT establish", is narrower and
  > factual: the four fee-calibration trades **"are placed by hand in the Kalshi
  > app"** because they *cannot* be routed through the order path. That is an
  > observation about a channel, not a design intent about Joe's discretion.
  >
  > The claim survives without the citation, on mechanism: the gate guards
  > `OrderPlacer`, and `ORDERS_ARE_DRY_RUNS = True`
  > (`backend/store/orders.py:129`) means the tool has never placed an order at
  > all. A phone in Joe's hand is not on that code path, so nothing here reaches
  > it. **But that is this ADR's own reasoning and must be signed as such** —
  > attributing it to ADR 0018 borrows authority the document never issued.
- **It does not say Kalshi's sports markets are efficient.** It says this
  instance's instruments cannot detect an inefficiency. Only the second is
  supported, and the distinction is the whole content of ADR 0037.
- **It does not settle `beta`.** The registered verdict is UNRESOLVED below
  `G = 300` and it stays UNRESOLVED. `beta` would need to move 8.3 standard
  errors for the outcome to be anything but NO SIGNAL, which is why no plan
  waits on it — but "UNRESOLVED" may still not be written up as "no signal".
- **It does not forbid a future project.** A batter-level, park-adjusted,
  pitch-level model is explicitly outside ADR 0037's bound. It needs sources
  this instance does not have and a licence surface ADR 0035 deliberately
  closed. **That is a new repo**, and it must not be allowed to hold this one
  open.

## Consequences

- CLAUDE.md's opening changes from *"this tool exists to find out whether an
  edge is there"* to the past tense: it **did** find out, and the answer was no.
- The asset on display is 38 ADRs, four registered measurements written before
  their data was seen, two of which refuted a prediction their author had made
  in writing, and a signal-agnostic harness that refuted the very signal it was
  built to support. **A negative result carried honestly is the stronger
  portfolio artefact**, because a positive one at this sample size would have
  been indistinguishable from noise.
- **Declaring done is the cure for this repo's most-repeated defect.** "Built
  but never called" is recorded four separate times — plans mistaken for
  features. A project with no finish line accumulates exactly those. The
  quarantined `backend/agents/` orphans (ADR 0022) are now either wired or
  deleted before the repo is called finished; a declared state is fine
  internally and reads as dead code to a stranger.
