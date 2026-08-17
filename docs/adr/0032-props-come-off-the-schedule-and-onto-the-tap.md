# 0032 — Props come off the schedule and onto the tap

**Date:** 2026-08-16
**Status:** Accepted.
**Owns:** `OddsConfig.buy_props_on_schedule` (default `False`), the
`prop_sports` gate in `runner.fetch_and_store_odds`, the
`scheduled_prop_sports` guard in `runner.fetch_and_store_props`, and
`ODDS_BUY_PROPS_ON_SCHEDULE` in `fly.live.toml`.
**Does not touch** the on-demand prop purchase (ADR 0031), the fee model, any
suppression threshold, or `MAX_ODDS_AGE_S`. Nothing about what counts as an edge
changes here — this is a **spending** decision.
**Related:** ADR 0031, which built the tap this moves the purchase onto. ADR
0029, which established the cluster key the whole argument rests on. ADR 0030.

---

## 1. The question

Joe, on the credit bill:

> *"Maybe we don't want to get all the props all the time, but we want to at
> least get some prospects out there, and from those prospects we can then
> explore deeper... We have levels to it. It's nested."*

He proposed a two-tier funnel to find better bets. **It does not do that** — see
§5, which is the part of this ADR most likely to be misread later. It does
something else worth more.

## 2. The arithmetic

One 13-game MLB cluster, measured on the live instance on the 2026-08-16 budget
day and reconciled in `fly.live.toml`:

```
/sports/baseball_mlb/odds                   1 call     6 credits
/sports/baseball_mlb/events/<13 fixtures>  13 calls  260 credits
                                                     266 opening
+ the rolling refresh tail (ADR 0030)                ~36
                                                     ~302 total
```

Props are **86%** of that. Against a 600-credit day, it buys **2 clusters**.

With scheduled props off, a cluster is `6 + ~36 = ~42`, and the same day buys
roughly **14**.

## 3. Why the 86% was buying nothing that counts

The project's only open question needs 300 independently-scored games
(`LIVE_GATE_MIN_SCORED_RECOMMENDATIONS`). `gate.clustered_clv` counts them, and
since ADR 0029 it clusters on `event_links.odds_event_id`. `gate.py:424-428`
states the consequence in terms:

> *"`odds_event_id` is one per sportsbook fixture, and a prop event inherits its
> game's value by construction — `match.linker.link_prop_event` returns the
> linked **game** fixture's id and refuses outright when two games claim one
> ladder. So props collapse onto their game rather than forming clusters of
> their own."*

So a prop row on a game that already has a moneyline row is **not an independent
observation and never was one**. 260 credits a cluster were being spent on rows
that cannot move the denominator, while the denominator was the binding
constraint on the entire project.

**The 300-game floor goes from months to days.** That is the whole case, and it
has nothing to do with finding a better bet.

> **Annotation, 2026-08-17 (added after the fact; the section above is left as
> written). THE DECISION STANDS. THE SOURCING DOES NOT.**
>
> **There are two 300s in this project and this section conflates them.**
> Everything above is correct about *the gate's* floor —
> `LIVE_GATE_MIN_SCORED_RECOMMENDATIONS`, counted by `gate.clustered_clv` on
> `event_links.odds_event_id`, where a prop ladder collapses onto its game and
> therefore genuinely cannot move the denominator.
>
> **It is wrong about the CLV signal test's `G = 300`**, which is a different
> statistic with a different, *registered* cluster key. The codebase already
> knew and had written it down — `backend/analysis/clv_signal.py:109-114`:
>
> > *"The cluster key is `COALESCE(m.event_ticker, r.ticker)` and it is NOT the
> > gate's key. ... On the current record the two give **210 and 125** — a 68%
> > difference — so a `G` quoted without its key is meaningless."*
>
> Under the registered key a prop ladder **is** its own cluster, and the interim
> look measured what that was worth: **props supplied 81 of 199 clusters —
> 40.7% of `G`.** So "the 86% was buying nothing that counts" is true of the
> gate's denominator and false of the signal test's. §6's third bullet flagged
> an adjacent risk as *unmeasured*; this is a different one, and it was
> measurable from a document that already existed.
>
> **Why this is an annotation and not a supersession.** Nothing here would have
> been decided differently. Props cost 260 of ~302 credits per cluster, and the
> accrual they were buying is toward a statistic `CLAUDE.md` states plainly that
> **no roadmap may depend on** — `beta` would have to rise 8.3 standard errors
> for the `G = 300` outcome to be anything but NO SIGNAL. Paying 86% of the
> credit bill to arrive sooner at a number nobody is permitted to wait for is
> not a reason to reverse this. **Turning scheduled props back on is
> explicitly killed, not deferred.**
>
> **What the error does cost is a live misreading risk**, and it is written up
> where the next reader will hit it: the prop arm's `beta` was **−0.519** against
> moneyline's **−0.082**, so a moneyline-only intake is expected to drift the
> pooled estimate **toward zero — toward what reads as good news — by
> composition rather than by evidence.** See the 2026-08-17 annotation on
> `docs/measurements/2026-08-16-clv-signal-test-interim-look.md`, which also
> records why the magnitude of that drift is *not* computable from the published
> arms and must not be projected.

## 4. What replaces it

ADR 0031 shipped a per-fixture prop refresh: 26 credits, one game, on demand,
behind a cooldown and a 150-credit daily slice. That endpoint was built the same
day as this decision and is what makes this one safe — the expensive purchase
still exists, but it is now bought **for a game somebody is looking at** instead
of for all thirteen in advance.

That is the funnel, and it is worth naming precisely because it is *not* the
funnel Joe described:

| | Stage 1 | Stage 2 |
|---|---|---|
| Joe's proposal | cheap screen finds prospects | deep research turns a prospect into a bet |
| What is built | wide cheap coverage of *games* | a person taps one fixture for its ladder |

Stage 2 here is **human-triggered, not signal-triggered**. Nothing automatically
promotes a game. That is deliberate: an automatic promoter would need a stage-1
signal, and §5 is why there is not one yet.

## 5. What this does NOT do, and the reasoning is arithmetic

**It does not make anything more likely to be actionable.** A funnel is a subset
selector. Stage 1 can only *remove* rows from the set stage 2 sees, and the set
is already empty — `actionable` has been 0 for the life of the record across
every market type. Narrowing an empty set leaves it empty. This is the same
argument `CLAUDE.md` makes against the absent second signal, and it applies here
unchanged.

> **Annotation, 2026-08-16 (added after the fact; the line above is left as
> written).** The claim that `actionable` has been zero for the life of the
> record **was false when this was committed.** It became non-zero on
> **2026-08-15T19:52:14Z**, and `gate.population_counts` published that over
> `/api/gate` on every pass from that moment.
>
> The claim came from `clv-coverage`, whose cluster query filters on
> `clv_scored_ms IS NOT NULL`. An actionable row is written *before* commence
> by construction, so the whole class sat outside that denominator until its
> game finished — the instrument could not see the thing being asserted about.
> The last valid whole-table measurement of 0 is ADR 0021's pin, 2026-08-10.
>
> **The decision this ADR makes is unaffected**, which is why this is an
> annotation and not a supersession: the audit found three rows, two distinct
> claims across two games, all three `anchored_on_sharp = 0` and therefore
> unseparated from the soft-book-fallback explanation. Nothing here would have
> been decided differently. Only the supporting sentence was wrong.
>
> See `docs/measurements/2026-08-16-actionable-population-audit-result.md`.


The 200 prop rows in `no_edge` were priced against fresh odds and produced a
post-fee edge ≤ 0. `no_edge` is an *outcome*, not a guard — `gate.py:324`
defines it as `suppressed_reason IS NULL AND reference_contracts <= 0` — so no
threshold, persona, or deeper look moves one of those rows into a bet. Only a
different `fair_probability` or a different `ask_tenths` would, and the first is
the blended-model decision `CLAUDE.md` defers to its own ADR.

**And a naive stage-1 screen would be actively harmful.** Shortlisting on
apparent edge selects the rows where devig method choice ran most favourably.
The devig-method spread is 1–2 percentage points, wider than the entire fee
advantage being hunted, so the shortlist is not merely at risk of being
noise-dominated — it is a winner's curse, and the selected rows' true edge sits
*below* their apparent edge by an amount that grows with selectivity. Any future
automatic promoter must be pre-registered and must select on something that is
**not a function of (fair, ask)**.

## 6. Consequences taken deliberately

- **Props stop accumulating on the record.** The prop CLV question (`start.md`
  item 2) now needs deliberate taps to gather data rather than getting it for
  free. That is a real cost and it is accepted: 1,533 prop rows on six fixtures
  already exist to score, and more rows on the same six games are not more
  evidence.
- **The one-sided prop recovery registration is unaffected but slower to feed.**
  `docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md`
  scores a dump that already exists.
- **A game whose only priced row is a prop would lose a cluster.** This is the
  one fact that would argue against the change, and it is **unmeasured**. On the
  six fixtures observed on 2026-08-15 it never happened — every prop event sat
  on a game that already had rows — but n is six. `clv-coverage` section A would
  settle it, and should be read before this is called settled.
- **The switch is stated in `fly.live.toml` even though it equals the code
  default.** `tasks/lessons.md` records the inverse error costing a session: an
  absent variable was read as the feature being off when it meant the default
  applied. An explicit `false` cannot be misread in either direction.

## 7. Verification

Four mutations run and caught: the switch never refusing, the switch ignored
when building `prop_sports`, the named-fixture bypass removed, and the config
default flipped on. 2,825 tests pass.

One earlier draft of the default-off test **passed against code that would still
have bought** — with no Kalshi prop ladder in the fixture,
`fetch_and_store_props` returns on its "no prop series discovered" branch and
never reaches the switch. `_prop_slate` exists so that cannot recur, and the
guard was moved to the top of the function so it is reachable on any slate.
