# CLAUDE.md

Spine for this repo. Deliberately short — detail lives in `.claude/skills/`,
loaded only when working in that area. At session start read, in this order:
`tasks/NEXT.md` (current state), `tasks/todo.md` (build log), then
`tasks/lessons.md`.

**All three are now small enough to read in full, and that is a guard, not a
promise.** As of 2026-08-17 `NEXT.md` and `lessons.md` were 456KB and 427KB —
both past the 262,144-byte ceiling at which the Read tool refuses a file
outright, so the instruction above had been impossible to obey and sessions
were silently reading only the head. The history was moved, **verbatim and
byte-for-byte**, into `tasks/archive/{next,lessons}-YYYY-MM-DD.md`; nothing was
summarised or deleted. `tasks/lessons.md` is now the newest lessons plus a
**pattern index** naming every lesson and its archive file — open the archive
file when a line sounds relevant. `tests/test_session_files_are_readable.py`
fails if either file crosses back over the limit. Add to the top; move the
bottom into the dated archive file rather than shortening it.

## What this is

A cockpit for betting sports on Kalshi. It compares Kalshi's prices against
devigged sportsbook consensus, surfaces opportunities where that consensus says
Kalshi is mispriced by more than the fee, and records everything so the edge can
be *measured* rather than assumed.

**There is one signal, not two.** Until 2026-08-10 this paragraph described a
second, in-house power-ratings model and said the tool surfaces where *both
agree*. That has never run. `backend/model/elo.py` is imported only by
`backend/model/backtest.py`, which is imported only by `tests/test_model.py` —
no production caller, on either instance. `model_probability` is `NULL` on every
row (`runner.py:684` does not pass it; `engine.py:58` defaults it to `None`),
and while `/api/ledger`'s `SELECT *` and one dbt staging view fetch the column,
both drop it: no suppression rule, sizing calculation, EV computation, gate
condition or API response consumes it. **Any claim that two signals must "agree"
describes a design, not the deployed system.**

The file:line citations are deliberate. This belief has now been wrong twice in
the same direction, and a future session can re-check a line number in thirty
seconds but cannot re-check an adjective.

**Do not read this as a reprieve, and the reason is arithmetic rather than
judgement.** As documented, the second signal was a *conjunction* — "where both
agree". A conjunction only ever removes rows from the surfaced set; it cannot
add one. Adding an AND-gate to a set that is already empty leaves it empty, so
the missing half **cannot** explain `actionable = 0` away. A different design
— blending a model probability into `fair_probability` to move the edge — could
shift rows either way, but that is a new decision, not the completion of an
existing one, and it would need its own ADR.

**`actionable` is no longer 0.** It genuinely was on 2026-08-10; it stopped
being 0 five days later. Re-audited **2026-08-23** on the gate's own predicate
(`r.suppressed_reason IS NULL AND r.reference_contracts > 0`, `gate.py:330`,
byte-identical in the instrument): **11 rows across 6 distinct games**, the
first written 2026-08-15T19:52:14Z, and **`suggested_contracts = 0` on every
one** — evidence at the fixed reference profile only (ADR 0015 §3), unbuyable
at the deployed bankroll and never rendered as a card. **The previous version
of this paragraph said 3 rows, all `anchored_on_sharp = 0`; that is no longer
the whole population — 4 of 11 are sharp-anchored**, three WNBA claims from
2026-08-20 devigged off Pinnacle, Betfair Exchange and Matchbook. So ADR
0021's soft-fallback reason no longer covers every row. **It has not been
refuted, and the re-audit did not take the measurement that would**: sharp
anchoring was **73.0%** of the pinned record (ADR 0021 §8, 1,141 of 1,564),
so 4 of 11 is *under*-representation rather than a new phenomenon, and a
sharp anchor selects **at most three books** (`devig.py:289`,
`selected = sharp or usable`) — a thinner fair value, not a better one. The
separating measurement is the one the 2026-08-16 audit named and nobody has
run: split the **unsuppressed** population by `anchored_on_sharp` and report
the `edge_tenths > 0` rate in each, clustered per game. **The verdict is
unchanged and rests on the two reasons that survive intact: 6 games against
the registered floor of 300, and the actionable predicate still carries no
multiplicity correction** while the runner re-evaluates ~100 candidates every
900s against a growing record. Treat 11 as *unseparated from zero*, not as a
result. No edit to the actionable predicate or to `devig.py` in the interval.
See `docs/measurements/2026-08-23-actionable-population-reaudit.md`.

Anything above or below claiming the count is 0 is **repetition of a
2026-08-10 measurement, not a measurement**. The intervening reads used
`clv-coverage`, which filters on `clv_scored_ms IS NOT NULL` while an
actionable row is written before commence — the class was outside the
denominator. `/api/gate` had the right number the whole time. See
`docs/measurements/2026-08-16-actionable-population-audit-result.md`.

What the 2026-08-10 correction changes is the *description*: the record must not
be written up as "the documented strategy produced zero actionable rows",
because that sentence credits a two-signal system that never existed. It is
**the
consensus-only strategy** that produced zero.

It runs hosted on Fly.io (not a laptop), is used from a phone, and is intended
to become a public portfolio repo.

## The consensus-only signal has been measured, and it is negative

**Read this before planning anything.** On 2026-08-16 `beta` — the CLV
pass-through coefficient, the project's registered decision-bearing statistic —
was computed for the first time:

```
beta_hat  -0.1412   se_cluster 0.0478   G = 199
always-valid interval  [-0.3342, +0.0517]
VERDICT   UNRESOLVED   (the registered floor is G = 300)
```

Both arms agree (moneyline −0.082, prop −0.519) and every interval computed lies
entirely below the registered NO-SIGNAL threshold of 0.40.
`docs/measurements/2026-08-16-clv-signal-test-interim-look.md`.

**Re-taken 2026-08-25. The verdict is still UNRESOLVED, and the reason it is
still UNRESOLVED is not the reason above.** The live screen displayed
`NO SIGNAL, 311 of 300 games` on 2026-08-24 and called itself a declaring look.
It was audited before it entered this file and **refused**. The registered
primary is:

```
beta_hat  -0.0756   se_cluster 0.0246   G = 216   (modal config version only)
always-valid interval  [-0.1728, +0.0216]
VERDICT   UNRESOLVED   (84 clusters below the registered floor of 300)
```

`G = 311` was the fit **pooled across four `strategy_config_version`s**, which
§P4 and §7 of the registration forbid as the primary in those words: *"the
primary analysis runs on the modal version only"*, *"`G` counts only those
games"*. That rule existed in code as an opt-in parameter defaulting to off,
and no production caller set it. Fixed 2026-08-25 — `build_report` applies §P4
itself and the pooled fit is carried without a verdict.

**Three more things the audit established, and the third is the one to carry:**

1. ~~§A4's leave-one-group-out downgrade is **not implemented**.~~ **Closed
   2026-08-29** — `leave_one_group_out` executes in code, and `downgrades` is a
   required argument rather than defaulting to empty, because a default would
   have kept every caller working and left the guard as absent as it was.
2. ~~`sd(clv_tenths) = 30.15` crosses the power check's own amendment trigger
   and the amendment is unwritten.~~ **Written 2026-08-29 (Amendment 2). The
   floor is now G = 713, and see below — it is worse than a bigger number.**
3. **`G = 311` is 4.26 effective clusters.** Two games carry half the leverage
   on `beta`; one WNBA game carries 43.8%; WNBA is 95.6% of it.
   `too_few_books`/`no_market_width` rows are 13.5% of the record and **93.9%
   of the leverage**, and inside that group `edge_tenths` runs −718 to +373 —
   a fair value of ~8c against an 82c ask, off fewer than two books. **Rule 1
   says those are bugs, not edges.** `sd(edge)` is 40.98 with them and 10.90
   without, so the apparent resolving power (MDE 0.078 against the
   registration's feared 0.42) is bought entirely from rows rule 1 refuses.

`docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md` carries all
eight defects and what would have to happen for a declaration to count.

**UNRESOLVED is the formal verdict and may not be reported as "no signal."** The
registration forbids declaring below **G = 713** — raised from 300 on
2026-08-29 by Amendment 2, under the power check's own trigger — and **that
look has still not been taken**. The 2026-08-24 screen did not take it; it
declared on the wrong population, against a floor that had already been
disqualified.

**For planning, treat it as settled, and Amendment 2 makes that stronger
rather than weaker.** Every interval computed at either look lies entirely
below the 0.40 threshold and both arms are negative.

**The declaring look is not coming, and this sentence replaces one that said
it would.** This paragraph used to read *"the recorder keeps running and the
look happens on its own"*. That is false. Three things, in ascending order of
how much they matter:

- The gap is not ~84 clusters. Against the raised floor it is **497**.
- **At G = 300 the design could never have resolved the 0.40 threshold it
  tests.** Its MDE there is 0.6283 — the registration printed that cell itself
  on 2026-08-09 and nobody read across the row.
- **Nominal G may be the wrong unit entirely.** At the measured `G_eff` the
  slope MDE is ~32, about eighty times the threshold. Holding the observed
  concentration ratio fixed, `G_eff = 713` needs roughly **52,052 nominal
  games** — about eleven years, against a stopping rule that ends 2027-02-15.
  Raising a nominal floor does not repair a 4.26-effective-cluster design.

So no roadmap may depend on the look, and no roadmap may *wait* for it either.
The way out, if the question is ever worth reopening, is a successor
registration with an `edge_tenths` exclusion fixed in advance — this one never
contemplated a regressor running to −717.97 tenths. What may *not* be written
is that the declaring look has happened.

**`G_eff` is now a required field on every fit**, so a cluster count cannot be
read without its effective count beside it. On the repo's own committed data
that is **1.81 against a nominal 86, one game holding 72.7% of the leverage**.

**It does not run for free, and this paragraph used to say it did.** Corrected
2026-08-24 (ADR 0071 §1). "The recorder costs nothing" is true of the LLM
fleet — the runner imports `review_retired`, which refuses every row and calls
nothing (`backend/agents/review.py:406`) — and **false of the odds feed the
recorder was raised to buy**. The claim was written when a sweep cost 2 credits
under `h2h`; `ODDS_MARKETS = "h2h,spreads"` doubled it on 2026-08-23 and nobody
revisited the sentence. The recorder is cheap to *decide about*, not free to
run.

**What it costs changed on 2026-08-25, and the number is now a ceiling rather
than a figure.** The fixed `ODDS_DESK_WINDOW_UTC` bought ~576 credits/day
(~17,300/month) whether or not anyone was looking — and would have been
~1,152/day at four sports, past the whole 20,000 tier, which NCAAF and NFL made
imminent. **The feed now follows attention over an hourly floor** (ADR 0071
§2.6): the ten-minute cadence while a page is open, hourly otherwise for a
sport with a fixture inside twelve hours. `ODDS_DESK_WINDOW_UTC` is unset on
live and still read, so a window can be pinned back on without a code change.

    idle floor only, 4 sports    ~384/day
    attention, capped            <=300/day   ODDS_ATTENTION_DAILY_CREDITS
    worst case                   ~684/day    inside the 700 daily cap

**The three rows above are bounds. One of them is now a measurement.** The
instrument is `api_credits` summed per budget-day **by trigger**, which
separates attention (`'attention'`) from the floor and the schedule (both
NULL) — `scripts/inspect_live_db.py credits-day --date …`. First read
2026-08-25 with the floor alone running; **first read with attention actually
running on 2026-08-28, budget day 20260827:**

    attention          75 calls   300 credits   15:53Z-20:46Z   4.88 h
    floor + schedule   48 calls   192 credits   10:13Z-01:42Z
    taps                0 calls     0 credits   (150 reserved)
    total             123 calls   492 of 700

**The slice buys 4.9 hours of attention a day, at 61 credits/hour** — three
sports each on a ~10-minute cadence, all drawing on one slice (median gap
between calls 3.6 min, no gap over 20). That is the number the ceiling
actually sets, and it was not written down anywhere before this. **An
"attended hours" figure is still a guess about any particular day**; this is
one observed day and the burn rate is the part that generalises.

The attention slice is a **hard ceiling and the reason the design is safe**:
its worst case is a tab left open and visible around the clock, which is double
the window it replaces. `Nav.tsx`'s `document.visibilityState` check is what
should prevent that; the slice is what does. The hourly floor is deliberately
not charged to it, so past the slice the slate stops re-buying every ten
minutes and keeps buying every hour — a ceiling, not an off switch.

**That sentence left a condition out for one day, and it was close to
perverse. Fixed 2026-08-29; the record of the defect stays, because the shape
recurs.** Attention *replaced* the floor rather than adding to it: `desk_wants`
branches on `attended or windowed` and hands every upcoming sport the
ten-minute cadence, the slice check refused each one, and the refusal was a
`continue` with **no fall-through to the hourly cadence**. So past the slice,
**keeping the page open was what suppressed the buying, and closing it was what
let the floor resume** — five minutes later, at `DEFAULT_ATTENTION_TTL_MS`.
Looking at the desk made it staler than not looking at it, at the one moment
Joe is about to bet.

A sport that is attended-but-slice-spent now falls through to the floor's own
timetable instead of being skipped, stamped `DESK` so it is neither charged to
the slice nor refused by it. A windowed sport falls through on identical terms,
for identical reasons. **The three published bounds above do not move**, and
that is arithmetic rather than intent: the floor's cadence is measured from
`last_sweep_by_sport`, which counts attention buys too, so a sport takes at
most one floor-paced buy an hour however many attended buys preceded it. The
~384 and the ≤300 are separately capped and additive, and 684 was always the
sum. **What changes is that actual spend now reaches towards a bound already
written down** — the deployed code delivered *less* than that table claimed,
and the gap was a stale slate rather than a saving.

**Know what the ceiling feels like from the outside, because it has now been
felt.** The slice ran out at 20:46Z and Joe opened the desk at 04:38Z — 7.9
hours into a silence the design intends — to books 198 minutes old, on a night
when the floor was *also* correctly idle (its rule is a fixture inside twelve
hours; the next kickoff was ~13.7 h out). Both paths off, both right. **The
desk did not say so**, and the refresh panel said *"the next scheduled sweep
is now"* while the loop was refusing that exact sweep, because `next_call_ms`
was computed from `firing_for_slot` and the slice check sat after it. Ticket
#35. Do not read a stale slate as a broken recorder: check `sweep-log` for a
refusal before diagnosing anything.

**It says so now, and the fix took three passes at one lie before the fourth
pass removed what the lie was about.** `window_status` applies the slice
itself, so past it the desk stopped contributing the ten-minute answer to
`next_call_ms` (2026-08-28); `readNextWindow` gained a `slice_spent` reading so
the resulting null is not rendered as *"no kickoff is near enough"*
(2026-08-28); and the loop's own refusal string stopped promising *"the hourly
floor still runs"* in the pass where the floor was displaced by the very
attention that caused the refusal (2026-08-29 morning) — that string is not a
log line only, it reaches `/api/window` as `last_look_detail` and
`WindowBanner` prints it on `/board`. The shape all three share: **one
predicate with two spellings, and the screen believing the wrong one.**

The fall-through then made the floor run in that state, so the sentence those
three passes converged on — *"the slow hourly buy resumes once you stop
looking"* — became a **reassurance that had outlived its condition**, which is
worse than the silence it was written to explain: a reader who acts on it
closes a screen he wanted open and buys nothing by it. All three surfaces were
corrected in the same commit, and `test_no_screen_still_tells_him_that_closing
_the_page_buys_more` pins the phrase absent on every one of them. **The lesson
is the ordering, not the string**: copy that names a condition to wait for is
falsified by fixing the condition, so the fix and the copy ship together or the
screen lies in the interval.

**The gate stays exactly where it is.** It is the live-trading interlock, it is
never lowered or bypassed, and "the gate will open" is not a step in any plan —
its 300 counts *actionable* games and the record has 2 in its whole life, both
soft-book fallbacks.

**~~What this frees.~~ That opinion was produced, and it is spent. The hunt is
closed — ADR 0038.** The paragraph here used to say "work that produces an
opinion is now the critical path". It was acted on: four registered measurements
in one day (ADR 0036, ADR 0037) built the opinion and refuted it, on the ground
that **our own model's error exceeds its disagreement with Kalshi**. Every
quadrant this instance can reach has now answered:

| quadrant | verdict | where |
|---|---|---|
| Consensus vs Kalshi's close | `beta = -0.141` | ADR 0021, 0034 |
| In-house model vs Kalshi's price | our error > the disagreement | ADR 0036, 0037 |
| `KXMVE` combos | **enter-only**: no YES bid on 40/40 books ever read, ≤18 units deep | ADR 0012 §5, E2/E3, 2026-08-18 |
| Speed / stale-quote pick-off | edge lives at ~400ms | predecessor |
| Cost headroom | a **discount, not a signal** | ADR 0027, 0028 |

**The combo row's reason was wrong, and the correction is recorded because the
conclusion is unchanged and that is exactly when a wrong reason survives.** This
row read *"zero volume, zero open interest"* until 2026-08-18. The script it
descends from (`scripts/analyse_combo_domination.py:71`) says these markets
"**mostly** carry zero volume and zero open interest"; the hedge was dropped
somewhere between the script and this file. And the hardened version was already
contradicted by this repo's own committed artifacts — non-zero `volume_fp` on
3 of 20 rows in `docs/measurements/2026-08-09-combo-e2-book-empty.json` and 3 of
9 in `-combo-e3-list-no-bid.json`, both produced by
`scripts/measure_combo_book_presence.py` on 2026-08-09. Roughly a fifth of
quoted combination markets have traded, in every run taken, and no run has
enough independent rows to narrow that.

**Do not read this as an in-season effect.** A 2026-08-18 run returned 2 of 11
and was briefly written up as one; Fisher two-sided against the 2026-08-09 runs
gives **p = 1.0**, its 11 rows collapse to about two independent groups by
shared legs, and it was 78% tennis — while MLB and WNBA were *already* in
season on 2026-08-09. The only sports absent from the original 2026-08-06
capture were NBA and NFL, so **`backend/kalshi/combos.py`'s calendar caveat is
untouched** and remains open.

What replaces the reason is stronger than what it replaces: **`yes_dollars` is
empty on 40/40 combination books this repo has ever read**, across three runs
on two dates. The list ask is the complement of a resting NO bid, not a quoted
offer. You can enter and you cannot exit. That, plus a combo fee model ADR 0012
§5 records as unverified, is why the quadrant still supplies no edge — an
enter-only market ≤18 units deep has nothing to multiply.

That last row is why this is a closure and not a pause: **a cost advantage
multiplies an edge, it cannot create one**, and no quadrant supplied one to
multiply. `backend/analysis/signal_test.py` remains signal-agnostic and would
validate a new signal on the same clock — but **no new hunting line is opened
here.** A proposal to reopen must name which row above it overturns, and with
what measurement. The recorder keeps running — at the odds-feed cost corrected
above, not for free.

**The premise, stated honestly:** Kalshi's advantage is cost, not information.
Prices are accurate to ~2c and sports is the most bot-contested corner of the
venue. The venue lowers the break-even bar from 52.38% to **51.75%** (taker)
or 50.44% (maker, at size). It does not clear that bar.

**This number has now moved twice, and the history is load-bearing.** It was
51.75%, corrected to 52.00% on 2026-08-10, and put back to 51.75% on 2026-08-14.
The correction was not wrong: `calculate_fee` genuinely charged the conservative
maximum across candidate models, so the applied bar genuinely was higher. **That
maximum has since been measured and the model it hedged against is refuted** —
Model B matches 0 of 11 real taker fills. Retiring it returns the applied bar to
what the published coefficient gives. Headroom is **0.63 points**, not 0.38.
See `docs/adr/0028-the-fee-hedge-is-retired-and-the-grid-is-deci-cent.md`.

**The bar the code applies still overstates the measured one, deliberately.**
Nine baseball fills pin `k` to `(0.03497, 0.03501]` — half the coefficient the
code charges — which would put the bar at **50.88%**. `TAKER_COEFFICIENT` stays
at 0.070 because *which* attribute carries that split is unresolved (sport,
series, and a per-market liquidity tier all fit identically) and every
observation of `k = 0.035` lies inside **four days**, on a venue whose schedule
demonstrably changed within the preceding six months. So: **50.88% true on
baseball, 51.75% applied, 52.38% at a sportsbook.**

**And 0.63 is an upper bound, not a point figure.** Both bars are computed
through `settlement_fee()`, a rename of `calculate_fee` asserting *"Settlement
is not a trade, so there is exactly one fee"*. That is H4, and **H4 is still
untested**. Settlement `fee_cost` matching the summed fill fees on 4 positions
is consistent with there being no settlement charge *and* with the field being
entry-only — separating them needs the account balance. A sportsbook's 52.38%
has no settlement fee to omit and Kalshi may, so the omission subtracts from the
0.63 and nothing subtracts from the 52.38. The gap to the 50.88% bar is robust;
the headroom is not. See
`docs/adr/0027-the-cost-headroom-is-an-upper-bound-pending-h4.md`.

This tool existed to find out whether an edge is there — not to assume one. **It
found out. The answer was no, and the record of how is the product** (ADR 0038).
This is a statement about what the **tool** may claim, and it reaches nothing
Joe does by hand: the gate guards `OrderPlacer` on the *engine* path, and
`ORDERS_ARE_DRY_RUNS = True` (`backend/store/orders.py:129`) means that path has
never placed an order at all.

**The hand-bet path is armed, and that is not the same door.** Since 2026-08-26
`MANUAL_ORDERS_ARE_DRY_RUNS = False` (`backend/store/manual_orders.py`) and
`MANUAL_ORDERS_ENABLED = "true"` on live, so `POST /api/manual-orders` sends
real immediate-or-cancel orders — one contract at a time, at Joe's own tap, with
his own typed estimate and order token. ADR 0063 built it as a **separate**
route, table and constant precisely so this sentence stays true: **`gate.py`
never reads `manual_orders`**, so a hand bet cannot move the live-trading
interlock's 300-game counter, and arming it did not arm the engine. Anything
claiming "the tool has never placed an order" without that distinction is
describing the state before 2026-08-26. See ADR 0073.
**Do not cite ADR 0018 for this** — it decides that arming is a code change, not
anything about Joe's discretion; see ADR 0038's sourcing correction.

## What it is for now that the hunt is closed — ADR 0071

ADR 0038 closed the hunt and said nothing about what the tool is *for*
afterwards, so every session re-derived it. Settled with Joe 2026-08-24, in
his own answers, and recorded in **ADR 0071 — read it before planning**:

- **A personal betting desk first**, a portfolio repo second, a hunting
  instrument not at all. Joe bets by hand whether or not this exists; the
  desk informs and records bets that are happening anyway. It does not
  manufacture action and does not abstain on his behalf.
- **Its job at the moment of a bet is price transparency** — what Kalshi
  charges against what the sharp consensus says it is worth. Chosen by him
  over "brake the bad bets" and over "just keep a clean record".
- **A per-row fact is transparency; an ordering is a claim.** The
  consensus-vs-Kalshi gap may be *shown* on a row and must never be *ranked
  by*: `beta = -0.141` means ranking by it puts the least trustworthy rows
  at the top of the screen. This is the live application of ADR 0038, not an
  exception to it.
- **Sharing means someone runs their own copy.** Kalshi's Developer
  Agreement §3.1 forbids sharing API-derived data with third parties without
  prior written authorization, so a hosted instance friends can visit is
  non-compliant; their own instance on their own key is the permitted case.
  Do not design for hypothetical operators beyond that — ADR 0071 §2.4 takes
  exactly one step in that direction and no more.

**The desk now watches what Joe already holds — ADR 0078.** `/hedge` records a
parlay he placed (a Kalshi combo or a sportsbook slip), reads its legs' live
Kalshi prices **while the game is running**, and says what hedging the
endangered one would do. It is the same job ADR 0071 names — price transparency
at the moment of a bet — pointed at a bet that already exists, and it closes a
hole the parlay desk opened: **combos are enter-only in 40 of 40 books this repo
has read, so a hedge on a leg market is the only exit that exists.**

Three properties to know before touching it:

- **No model, no tokens, no credits.** Kalshi's live in-play price already
  carries the score and the inning, and it is the price the hedge transacts at,
  so nothing is fitted. No Anthropic client and no `api_credits` write is
  reachable from `core/hedge.py`, `hedge.py` or `hedge_watch.py` — asserted over
  the source with docstrings stripped.
- **It touches no evidence and no interlock.** No `recommendations` row is
  written, so `runner`'s `dropped_game_started` drop and ADR 0006's guard are
  untouched; `gate.py` may never read `parlay_positions` or
  `parlay_position_legs`, the same boundary `manual_orders` has.
- **A lock is arithmetic; the timing is not.** With one leg live and the rest
  won, the figure is exact and is pushed to the phone. With several legs live
  there is no figure, the screen says so, and nothing is pushed. Neither claims
  the price will get worse if he waits.

## The three rules everything else follows from

1. **A large apparent edge is a bug until proven otherwise.** Big numbers get
   suppressed and investigated, never surfaced. The devig-method spread alone
   (1–2 percentage points) exceeds the fee advantage being hunted.
2. **Use the worst of four devig methods** for any money decision, so no edge
   survives that is an artifact of method choice.
3. **Validate against Kalshi's own closing line.** The question is whether you
   beat *Kalshi*; only Kalshi's close answers it.

## Measurement rules

These are not style preferences. Every one of them exists because an earlier
measurement was wrong in a way that flattered the result.

- **Read `n` before the effect size.** Require ≥5 expected outcomes on each
  side before a normal approximation is allowed to speak. The biggest gaps come
  from the smallest cells.
- **A pooled number is not a finding until the parts agree.** Always print the
  per-group view and the largest contributor's share beside any aggregate.
- **Bucket by the price you would actually pay** — the derived ask, never the
  mid. One bucket in the previous project showed a +25.4 point edge *and lost
  money* because it was bucketed on the mid but transacted at the ask.
- **The convenient column is usually contaminated.** `last_price` on a settled
  market has already converged on the outcome. State when a price was observed
  relative to when the outcome became known, and re-run at a second horizon.
- **Count your tests.** 1,190 category cells produce dozens of "significant"
  results by chance.
- **Every harness states what it does not establish**, in its module docstring.

## Conventions

- **Money is integer tenths of a cent** (`core/prices.py`), never float
  dollars, everywhere in the risk path. ~25% of Kalshi markets tick in
  deci-cents; whole cents misprice them by up to half a cent against a 4c edge.
- **Unreadable resolves to `None`, never `0`.** Callers refuse rather than
  substitute. See `tasks/lessons.md`.
- **Clamp what you trust; refuse what you're validating.**
- **Config via `.env`**, never hardcoded. `.env.example` is the contract.
- **Async** for all I/O. One shared `httpx.AsyncClient`, not one per call.
- **Wire-format tests load captured payloads** from `tests/fixtures/`, never
  hand-constructed ones. **One exception, and it is deliberate: MLBAM
  (`statsapi.mlb.com`) payloads are never committed**, because this repo is
  public and their terms permit "only individual, non-commercial, non-bulk use."
  MLB tests use synthetic payloads with a shape assertion. See ADR 0035 — the
  inconsistency is the decision, not a bug to fix.

## Testing

```
.venv\Scripts\python.exe -m pytest -q
```

`asyncio_mode = auto`, so async tests need no marker. Shared fixtures are in
`conftest.py` at the repo root (not `tests/`) because `backend` is imported as
a package from the root. Group with `class Test<Behaviour>`, and name tests
after the claim they make (`test_maker_is_one_quarter_of_taker`).

**Every guard is verified by disabling it and watching the test fail.** If it
stays green, it's decoration. Never weaken an assertion to make a test pass.

## Security

This repo is intended to go public and the live instance holds real money.

- The Kalshi private key is a Fly secret. Never read, echo, log, or commit it.
  If it ever appears in a transcript, it is compromised — rotate it.
- `.env`, `*.pem`, `*.key` are gitignored from the first commit.
- Every mutating route requires auth. The order endpoint re-validates staleness
  and risk caps **server-side** — never trust that the UI disabled a button.
- Demo and live run as separate deploys from one image. A public URL must not
  be one config bug away from the order path.

## Do not read these

They will burn a context window and tell you nothing you need:

- `../kalshi_orderbook_monitor/orderbook_data/**` — ~400MB of JSONL recordings.
- `../kalshi_orderbook_monitor/static/app.js` — 100KB vanilla JS, superseded.
- `../kalshi_orderbook_monitor/auto_trader.py`, `trading_server.py` — 86KB and
  90KB. Skim structure only; the strategies in them were measured and failed.
- `.venv/`, `node_modules/`, `warehouse/target/`.

To reference the previous project, read `.claude/skills/kalshi-api/SKILL.md`
first — it carries what was learned without the bulk.

## Do not rebuild these

Measured and refuted in the previous project. Re-litigating them costs days.

| Idea | Result |
|---|---|
| Stale-quote detection / picking off | Edge lives at ~400ms; a 60–180s detector is far too slow |
| "The NO side is systematically cheap" | Refuted on 66,686 settled markets — every price bucket negative |
| Kalshi↔Polymarket arbitrage | Text matching gives 0.56% match rate, and the matches are *wrong* |
| Pitcher-K priced from public rate data | Parameter noise is 6.09–8.47 points against a 1.75-point fee bar. The **in-sample optimal blend** of prior-season and season-to-date rates — an upper bound no implementation can beat — is still 3.5× the whole advantage. ADR 0036 |
| **Any in-house prop model from public rate data** | On 255 settled `KXMLBHR 1+` markets, the model-vs-Kalshi disagreement has sd **3.72 points** while the model's own error is **4.04** — so Kalshi's error is not detectable at all, and every apparent edge is our own noise. **Ask this question first**: comparing to the *price* needs no settlements and would have short-circuited three earlier measurements. ADR 0037 |

## Do not repeat this inference

`/markets` is ~99.8% `KXMVE` with no volume. That is a fact about **discovery
hygiene** — never paginate `/markets` — and it does **not** mean Kalshi has no
combo product. `KXMVE` is Multi-Variate Event: 1,389 collections and 13,806
legs, same-game and cross-game. This project asserted the opposite for eleven
build steps. See `backend/kalshi/combos.py` and `tasks/lessons.md`.

## Workflow

1. **Plan first** for anything non-trivial (3+ steps or an architectural
   choice). If something goes sideways, stop and re-plan rather than pushing.
2. **Vertical slices, not horizontal layers.** Each step ends demoable and
   verifiable, so a session can end anywhere without leaving a half-built
   layer.
3. **Offload research to subagents** to keep the main context clean. One task
   per subagent.
4. **Verify before done.** Never mark a task complete without proving it works.
   Would a staff engineer approve this?
5. **Capture lessons.** After any correction, write the *pattern* to
   `tasks/lessons.md` — not the incident.
6. **Record decisions** in `docs/adr/` so no future session re-derives them.
