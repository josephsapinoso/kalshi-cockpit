# Pre-registration — would a scout TAKE/PASS on each parlay leg have been a useful second gate?

**Written 2026-09-25, before a single verdict exists.** `leg_verdicts` is not
built (no match anywhere in the repo on this date), so no row of it can have
been seen. No live query was run. No leg settlement and no outcome of any card
Joe opened or bought was read. Joe's report that his "safe" and "middle"
parlays have been losing is the *motivation*, not data. No card from before the
seat shipped enters the population (§2), because selecting on a losing record
would be selecting on the dependent variable.

**Joe's question (2026-09-25):** "would the scouts looking at the parlay legs
have been a useful second gate before purchase?" **The seat, as he decided
it:** for each leg he opens on a card, an advisory LLM seat returns TAKE or
PASS on that leg's side (yes/no) at the ask at that moment, with a reason and
no number. It writes one `leg_verdicts` row (`ticker`, `side`, `ask_tenths`,
`verdict`, `requested_ms`, `completed_ms`, `commence_ms`, `status`, `model`,
`tokens`, `trigger`).

---

## 0. The power check, which comes first

**Verdict: UNDERPOWERED for any effect the base rate makes plausible.
Re-scoped, not killed (§8).**

Per-leg excess `e = y − p`: `y` = 1 if the leg's side settled true, and
`p = ask_tenths / 1000`. Planning inputs:

- `σ² = 0.21`, which is `p(1−p)` at p ≈ 0.70, a typical safe/middle leg. The
  worst case is 0.25.
- `DEFF = 1.3`, from ~2 legs per game at intra-game correlation 0.3. A
  moneyline and a spread on one game resolve from one score, so it could reach
  1.7.
- Declaring boundary `z = 2.00` one-sided (§6) at power 0.80, so
  `(z_α + z_β)² = 8.08`.
- `f` = the TAKE share, which is unknown.

    n_legs = DEFF · σ² · 8.08 / (δ² · f(1−f))

| δ (TAKE − PASS excess) | f = 0.5 | f = 0.7 | f = 0.85 | days at ~10 legs/day (f = 0.5) |
|---|---|---|---|---|
| 5 points | 3,530 | 4,200 | 6,920 | ~350 |
| 3 points | 9,800 | 11,670 | 19,220 | ~980 |
| 1.5 points | 39,200 | 46,700 | 76,900 | ~3,900 (≈10.7 yr) |

The planning rate is ~10 legs/day. NEXT.md 2026-09-25 records 4 to 19
armed-path legs a day, and legs *opened* may exceed legs *bought*. The §7 date
stop gives ≈ 2,700 eligible legs if the seat ships near 2026-10-01, fewer after
failures and voids. **The detectable effect there is ≈ 6 points** at f = 0.5.
At the dated interim (≈ 1,000 legs, z = 3.00) it is ≈ 12 points.

**Where the headroom actually sits.** Kalshi's prices are accurate to ~2c
(CLAUDE.md). Read that as: the true probability is `price + ε`, with
`sd(ε) = σ_K`. A **perfect** filter that TAKEs exactly the legs with `ε > 0`
yields `δ = 2 · σ_K · √(2/π) ≈ 1.6 σ_K`, which is **3.2 points at σ_K = 2**.
A 5-point δ needs σ_K ≥ 3.1 *and* a perfect filter. A real filter whose signal
correlates `r` with ε earns roughly `1.6 r σ_K`. ADR 0036/0037 is this repo's
last attempt at knowing better than the price. On 255 `KXMLBHR` props, the
model's own error (sd 4.04 points) exceeded its disagreement with Kalshi (sd
3.72), so Kalshi's error was not detectable at all.

**An effect that fits inside the base rate needs about 10,000 to 40,000
legs.** The design resolves only effects at or above the perfect-oracle
ceiling. That is knowable now, for free (the ADR 0016 habit). §8 states what
the measurement is still for.

---

## 1. The claim, as something that could be false

**H1 (one-sided, direction fixed now):** on legs with a qualifying verdict,
mean excess over the ask is **greater** in the TAKE arm than in the PASS arm
(`b > 0`, §4). **H1-harm** (`b < 0`, the seat anti-selects) is registered now
so it cannot be discovered later. It uses the same boundaries, and its α is
counted in §6. Nothing here claims the seat *always*, *never* or
*structurally* does anything. The claim is about a mean over §2's population.

---

## 2. Population and exclusions

**IN:** every live `leg_verdicts` row from the day the seat ships through the
§7 cut, reduced to **one row per `(ticker, side)`**: the one with the earliest
`completed_ms` that meets all four conditions.

1. `status` = the build's completed value (expected `'completed'`) and
   `verdict ∈ {'TAKE','PASS'}`.
2. `completed_ms ≤ commence_ms − 300,000`, so the verdict finishes five
   minutes before the recorded start. The margin guards against a wrong
   `commence_ms`.
3. `commence_ms` is the value written at **request** time. The build must make
   it write-once. If it is ever updated in place, an amendment is owed before
   any row is read.
4. `trigger` names the live, pre-commence path. **Retrospective verdicts are
   forbidden outright.** A seat with web search, asked after the game, can
   read the result. So no backfill, no replay over past cards, and no "what
   would it have said". Any other `trigger` is out, whatever its timestamps.

**First qualifying verdict, never the latest or the majority.** Re-opening a
card re-asks the seat. Any other choice lets re-rolls pick the arm afterwards.

**OUT, each for a reason that does not reference the outcome** (counts
printed):

| exclusion | why it is outcome-independent |
|---|---|
| `ask_tenths` NULL, ≤ 0 or ≥ 1000 | no price means no `p`; fixed before the game |
| `kalshi_markets.result ∉ {'yes','no'}` at the settlement read (void, cancelled, still open) | a void does not depend on which side was named |
| no game key: `kalshi_series.league` NULL, or `fixture_segment(event_ticker)` (`backend/match/linker.py:157`) unreadable | cannot be clustered; known at listing time |

**Never split, never joined: whether Joe bought the leg.** The outcome is the
market's settlement for the named side either way. No `manual_orders`,
`fills` or `parlay_positions` are read. A "bought" split would turn a
measurement of the seat into a win rate on Joe's record. The 2026-08-29
registration prohibits that.

---

## 3. Unit, cluster, and the cut

- **Observation:** one deduplicated `(ticker, side)` leg.
- **Cluster: the game**, keyed `(kalshi_series.league,
  fixture_segment(event_ticker))`. This is the key `parlays._leg_scouting`
  uses (#150), so a prop, a spread and a moneyline on one fixture form one
  cluster. Games are treated as independent; legs within a game are not.
- `G` and **`G_eff` (Kish, `(Σ n_g)² / Σ n_g²`)** are printed beside every
  fit, per arm and pooled.
- **Price buckets, on the ask actually paid, never the mid:** `ask_tenths` ∈
  [0,300), [300,500), [500,700), [700,850), [850,1000). They are used only for
  `b_strat` (§4). No other edges.

---

## 4. The statistic, named as an estimator

**Primary `b`:** the slope of an OLS fit of `e_i = y_i − ask_tenths_i/1000` on
a TAKE indicator. This equals `mean(e | TAKE) − mean(e | PASS)`, a
**difference of two means of game-clustered observations**. Its SE is CR1,
cluster-robust by game, and `z = b / SE_CR1(b)`. `sqrt(p(1−p)/n)` is not the
SE: this is not a single proportion, and the legs are not independent.

**Printed beside `b` at every look:**

- per arm: legs, games, `G_eff`, `Σp`, `Σ(1−p)`, and mean excess both before
  and after the taker fee at `TAKER_COEFFICIENT = 0.070`
- per league: `b` with its `n` and `G`
- the largest league's share of games, and `b` with that league dropped
- per `model`: `b` with `n`
- **`b_strat`**: the same fit with fixed effects for the five price buckets,
  so TAKE is compared with PASS at the same price level

Why `b_strat` is registered now: if the seat mostly TAKEs favourites and
Kalshi carries any favourite–longshot bias, `b > 0` appears with no skill.
A free "take the favourite" rule would then reproduce it at zero token cost.

---

## 5. Floors before a look may speak

A look is evaluable only if each arm has **≥ 100 distinct games**,
**`Σp ≥ 5`** and **`Σ(1−p) ≥ 5`** (at least 5 expected outcomes on each side).
These floors are counts and prices, never outcomes.

- **Interim floor missed:** the look is **skipped**. No z is computed and no α
  is spent.
- **Declaring floor missed:** the verdict is **NOT EVALUABLE**.

---

## 6. Decision rule and multiplicity

**Exactly two looks**, interim and declaring, each testing two directions.
That makes four evaluations. The union bound holds wherever the interim
falls:

    interim    |z| ≥ 3.00   one-sided 0.00135 per direction
    declaring  |z| ≥ 2.00   one-sided 0.02275 per direction
    family α ≤ 2 × (0.00135 + 0.02275) = 0.048

Per-league, per-model, per-bucket and §9 figures are **point estimates with
n**, never tested.

**No running figure, anywhere.** No screen, route, log line, instrument or
ticket may compute a running TAKE-vs-PASS aggregate or a "scout was right X of
Y". A threshold re-read against a growing table is thousands of looks. Under a
true null it crosses eventually with probability 1 (13.7% measured here, a
floor). **If such a surface is built, this registration is spent**, and a
successor with an always-valid boundary is required. Per-row display (one
leg's verdict beside its own settlement) is allowed.

**Outcomes. Exactly one per look, checked in this order:**

- **HELPS:** `z ≥` the boundary **and** PASS-arm mean excess after fee
  `< 0` **and** `b` with the largest league dropped `> 0` **and**
  `b_strat > 0`. The last three conditions are point estimates. The PASS
  condition is here because Joe named it, not because it discriminates. At the
  ask it is near-mechanical under the null, since half-spread plus fee sits
  below zero.
- **HELPS BY PRICE LEVEL:** as HELPS, except `b_strat ≤ 0`.
- **HARMS:** `z ≤ −`the boundary.
- **UNRESOLVED:** anything else, including `z ≥` the boundary with another
  HELPS condition failing. Per §0, this is the outcome for any true effect
  below ~6 points at the stop. **It may not be written as "the scouts don't
  help", nor as "they help a little".**
- **NOT EVALUABLE:** a §5 floor is missed at the declaring look.

An interim HELPS, HELPS BY PRICE LEVEL or HARMS stops collection. Any other
interim outcome continues it.

---

## 7. Stopping rule

- **Start:** the first live `leg_verdicts` row.
- **Interim:** the first of 1,800 eligible legs or 2027-01-15.
- **Declaring:** the first of 3,600 eligible legs or 2027-06-30. **It is not
  extended** for being close, for UNRESOLVED, or for a model change.
- **Settlement:** read 14 days after each cut, over legs with
  `commence_ms` ≤ the cut.
- **Model or prompt changes:** recorded as a dated amendment when they happen,
  before any row is read. The primary pools all rows, and the per-`model`
  split is printed (§4).

---

## 8. Falsification destination and consequence

The result documents are written whatever the outcome:
`docs/measurements/<look-date>-scout-leg-verdicts-interim-look.md` and
`docs/measurements/<look-date>-scout-leg-verdicts-declaring-look.md`. Both
quote §6 and §10 verbatim.

| outcome | built | killed |
|---|---|---|
| HELPS | a map #3 ticket for Joe: show the verdict as a pre-purchase gate on the card (advisory, no ranking) | the belief that no leg-level check beats the price |
| HELPS BY PRICE LEVEL | a ticket to replace the seat with the free price rule | the seat's token spend, on that evidence |
| HARMS | a ticket to hide the verdict and turn the seat off | the seat |
| UNRESOLVED / NOT EVALUABLE | a ticket for Joe: keep the seat on **cost and preference alone** | any claim, either way, about its predictive value |

**Below ~6 points this measurement funds nothing and kills nothing** (§0).
Keeping the seat is then a token decision, not an evidence decision. **No plan
may wait on this look**, and the ticket that ships the seat should say so. What
the measurement *can* still do, without a running figure, is catch a large
anti-selection, or a large gap that is price level only.

---

## 9. Secondary, descriptive only

**Parlay level.** Classify each card Joe opened as **all-TAKE** or
**any-PASS**, using qualifying verdicts. Cards with an unverdicted leg are
excluded and counted. For each class, report the **count of cards** and the
**count in which every leg's side settled true**. These are counts, not a
rate, with no interval and no test. Cards share legs and games, so they are
not independent. A card's settlement is a property of its legs' markets, not
an RFQ fill (ADR 0164), and it is not joined to Joe's orders.

---

## 10. What this cannot establish (quoted verbatim in each result)

- **Not combo EV.** Combinations are priced by RFQ (ADR 0164), not at the
  product of their legs' single-market asks. A leg's excess over its own ask
  says nothing direct about what a card cost or returned.
- **Not Joe's performance.** No P&L, win rate or result of his bets is
  computed, and "bought" is never a split (§2).
- **Not an edge against the fee bar.** Headroom against a sportsbook is ≤ 0.63
  points (CLAUDE.md). This design cannot see anything within ~6 points of
  zero.
- **Not a model probability.** The verdict carries no number, and nothing here
  licenses blending one into `fair_probability` (that would need its own ADR).
- **Not all legs.** Only legs Joe chose to open are in, so the result is
  conditional on his selection.
- **Not a later seat.** The result covers the prompts and models recorded
  under §7. A later prompt or model is a different instrument.
- **Not look-ahead-free beyond §2.** The five-minute margin and the trigger
  rule close the known leak. They cannot rule out a `commence_ms` error larger
  than the margin. The count of verdicts completing within 30 minutes of
  commence is printed.

---

## Registration status

**UNDERPOWERED.** At ~10 legs/day, the date stop gives ~2,700 legs, enough to
detect ~6 points. Detecting 5 points needs ~3,500 legs, roughly 12 months.
The base rate puts even a perfect filter at ≤ 3.2 points (σ_K = 2), and that
needs 10,000 to 40,000 legs. **Re-scoped, not killed:** this stands as a
bounded two-look check that can catch a large effect in either direction,
HARMS in particular. Below that, keeping the seat is a cost decision (§8).

**Decision rule, verbatim, for checking against the eventual write-up:**

> `b` = mean(y − ask/1000 | TAKE) − mean(y − ask/1000 | PASS) over first
> qualifying pre-commence verdicts per (ticker, side), CR1 SE clustered by
> (league, fixture segment). Two looks only: interim |z| ≥ 3.00, declaring
> |z| ≥ 2.00, one-sided per direction, family α ≤ 0.048. HELPS requires
> z ≥ boundary AND PASS-arm mean excess after fee < 0 AND b with the largest
> league dropped > 0 AND b_strat > 0. `b_strat ≤ 0` with the rest holding is
> HELPS BY PRICE LEVEL. z ≤ −boundary is HARMS. Anything else is UNRESOLVED
> and may not be reported as "no help". Floors per arm: ≥ 100 games, Σp ≥ 5,
> Σ(1−p) ≥ 5. Stop at 3,600 eligible legs or 2027-06-30, whichever first.

---

## Amendment 1 (2026-10-08): verdicts fired from "Check a parlay" join the population

**Written 2026-10-08 with no live row read.** No `leg_verdicts` row, no leg
settlement and no aggregate of any kind was looked at for this amendment. On
this date `POST /api/leg-verdicts` accepts only `price_tap`, `leg_buys_open`
and `card_button` (`backend/api/routers/leg_verdicts.py:155`), and
`check_button` appears nowhere in the repo, so no row with the new trigger can
exist yet. This amendment is written before the build that adds it (#325,
blocked on #324) lands.

**Joe's answer.** Asked on 2026-10-08, by option buttons, whether a verdict
fired from the "Check a parlay" screen should count, with the cost put to him
as about 51K tokens a leg out of the same daily share the game-script cards
use, Joe answered: "Yes, add it".

**What changes.** §2 condition 4 admits one more value of `trigger`:
`check_button`, a verdict fired from the "Check a parlay" screen. That screen
checks a parlay someone else built, usually a friend's, before Joe decides
whether to tail it. Rows with this trigger enter §2 on exactly the same four
conditions as the other three triggers, unchanged:

1. completed status and `verdict ∈ {'TAKE','PASS'}`;
2. `completed_ms ≤ commence_ms − 300,000`;
3. `commence_ms` written once, at request time;
4. a live, pre-commence trigger, now one of `price_tap`, `leg_buys_open`,
   `card_button` or `check_button`. Retrospective verdicts stay forbidden
   outright.

**One row per `(ticker, side)` still means the first qualifying verdict across
all four triggers together.** A leg first verdicted on the check screen and
later opened by Joe on his own card counts once, as `check_button`. A leg
verdicted on his card first counts once under that card's trigger. A cached
verdict served to the check screen writes no row and changes nothing. The
per-`trigger` split below always uses the trigger of the row that survives
this reduction.

**Fired only by Joe's tap.** A `check_button` verdict is requested only when
Joe taps for it on the check screen. It is never fired automatically: not on
page load, not on paste, not by a watcher, not in a batch over past checks. If
the build ever fires one any other way, those rows are not this trigger, and an
amendment is owed before any row is read.

**A check can come days before kickoff.** The ≥ 5-minute margin (condition 2)
and the route's refusal of a game that has already started
(`backend/leg_verdicts.py:209`) both still apply, and neither is relaxed for
this trigger. `p` stays the ask recorded at request time, whenever that was. It
is not refreshed to a later price, and it is not replaced by the price Joe paid
if he later tailed the parlay. Joe's buying is still never read (§2).

**The one new confound: who chose the leg.** Under the original three
triggers, every leg was one Joe chose to open. A `check_button` leg was chosen
by someone else, usually a friend building a parlay. Pooling the two mixes two
selection processes in one `b`. A seat that does well or badly on one kind of
leg could move the pooled `b` in a way neither group alone shows. So the
following is **printed beside `b` at every look**, as a point estimate with
legs, games and `G_eff` per arm, and **never tested**:

- `b` for `check_button` rows alone;
- `b` for the other three triggers pooled;
- `b` for each of the four trigger values separately.

Where an arm is empty within a trigger, that line prints the counts and no `b`.
None of these figures enters any HELPS, HELPS BY PRICE LEVEL or HARMS
condition, none has a boundary, and none counts toward the §6 family α.

**What this does not change.**

- The statistic and estimator (§4): `b`, the OLS slope of `e = y − ask/1000`
  on the TAKE indicator, its CR1 SE clustered by (league, fixture segment), and
  `b_strat` on the same five price buckets.
- Everything else printed beside `b` (§4), and §3's unit, cluster and bucket
  edges.
- The floors (§5): ≥ 100 games per arm, Σp ≥ 5 and Σ(1−p) ≥ 5.
- The two looks and their boundaries (§6): interim |z| ≥ 3.00, declaring
  |z| ≥ 2.00, one-sided per direction, family α ≤ 0.048. The four outcomes and
  their order are unchanged.
- The stop (§7): interim at 1,800 eligible legs or 2027-01-15, declaring at
  3,600 eligible legs or 2027-06-30, not extended. Because the stop counts
  eligible legs, the extra legs can bring a look forward in time. That depends
  on how many checks Joe runs, not on any outcome, and the counts are not
  moved to offset it.
- The no-running-figure rule (§6). The check screen may show one leg's verdict,
  and later that one leg's settlement, per row. It may not show a running
  TAKE-vs-PASS figure, a "scout was right X of Y", or any per-trigger tally.
  If it does, this registration is spent, exactly as §6 says.
- The decision rule quoted under "Registration status". It never named a
  trigger and is not edited.

**Model, prompt and input.** The seat, its prompt and its model are the same
for this trigger. If the build gives the seat different input for a
`check_button` leg (for example, telling it the parlay is someone else's),
that is a §7 prompt change and is recorded as its own dated amendment before
any row is read.

**§9 and §10.** A checked parlay is not a card Joe opened, so it is not
classified in §9's all-TAKE / any-PASS counts. The number of checked parlays
is printed beside them. §10's "Not all legs" now reads: only legs Joe chose to
open, or chose to check on someone else's parlay, are in, so the result is
conditional on both selections. The result documents quote §10 with this
sentence in place of the original and cite this amendment.
