# Pre-registration — the spread/total falsification test, SECOND AND TERMINAL look

Written 2026-08-20, before the sweep it registers and before the anchor it
fixes. This is the second half of the measurement begun in
`docs/measurements/2026-08-20-preregistration-spread-total-edge.md`, whose
result (`2026-08-20-spread-total-edge-result.md`) was **UNDERPOWERED on both
arms**: 3 sharp-anchored spread rows and 2 totals rows against a registered
floor of 8 per arm.

**The partner authorized exactly one more look and declared it terminal.** The
authorization's words are the governing constraint of this file: the look is
final **regardless of outcome**, and a second UNDERPOWERED closes the question
by exhaustion of authorized looks. **There is no third look.** Any sentence in
the eventual write-up that reads as "with one more slate we would know" is
contradicted here, in advance, on purpose.

Every rule from the first registration is **restated in full below**, not
incorporated by reference. Where a rule is changed, the change is named, its
direction is stated, and its justification is a defect in the first
registration rather than anything seen in the first look's numbers.

---

## 0. Declared contaminations, in full

Written before the second sweep; each item is a fact already seen that could in
principle have shaped a choice below.

- **The first look's five sharp-anchored rows have been read and they are all
  negative** (−25.0, −19.2, −15.3, −3.5, −2.9 tenths at the charged fee). That
  is published under an UNDERPOWERED verdict and is a description, not a
  finding. It is the reason §6.4's **no-pooling** decision is made *against*
  convenience: pooling those five into look 2 would mechanically drag a pooled
  median negative and make REFUTED easier to reach.
- **Those five rows' dispersion (sd ≈ 9.7 tenths) is used as a variance input
  to the power arithmetic in §2.** Dispersion is a nuisance parameter and is
  orthogonal to the sign of the effect, but it is data and it is declared.
- **`2026-08-20-spread-sweep-raw-2026-08-20T212616Z.json` was inspected for
  scheduling and book-coverage facts only** — `commence_time`, bookmaker counts
  per fixture, and whether Pinnacle quoted spreads. Those drove the anchor
  handling in §3–§4 and the yield estimate in §2. **No price, no strike, no ask
  and no edge from that artifact entered any choice below**, beyond the sd
  above.
- **The partner verified ~12 MLB games in coverage on 2026-08-21 against the
  schedule**, not against a captured artifact. That is a scheduling fact, fixed
  before any price is read.
- The h2h verdict (`beta = −0.141`, ADR 0021/0034) is known and remains the
  prior: the expected outcome of this test is REFUTED. **This registration is
  written so that the analysis is identical whichever way it comes out.**

---

## 1. The question, and the claims stated so they can come back false

Unchanged from look 1.

Does a devigged multi-book consensus on MLB **spread and total** lines,
matched to Kalshi markets at the **exact same line**, show a positive fee-net
edge against Kalshi's derived ask — at the fee the venue actually charges?

- **C1 (the edge claim under test), one-sided, direction fixed now:** the
  median fee-net edge on sharp-anchored rows is **> 0** at the charged fee.
  The test is one-sided in the positive direction and will not be reported
  two-sided after the fact, nor the reverse.
- **C2 (the overlap premise):** at least one book quotes both sides of a line
  Kalshi lists, for at least half the matched games. If C2 fails, the test is
  **not** a refutation of C1 — it is reported as **NO-OVERLAP**, a finding
  about the join.
- **C3 (the slate premise, new, recorded because it can fail):** at least 8
  Kalshi `KXMLBSPREAD` events are matched to in-window odds fixtures at the
  anchor. C3 failing does **not** move the anchor and does **not** cancel the
  look; it makes UNDERPOWERED likely, and UNDERPOWERED is a registered verdict.
  C3 exists so that a thin slate is recorded as a foreseen outcome rather than
  discovered as an excuse.

---

## 2. The power check, before anything else

**Can this measurement answer this question at the `n` available?**

### 2.1 Where sharp rows come from

Sharp anchoring requires **Pinnacle quoting both sides at Kalshi's exact
line**. In the first look's odds payload, taken 21:26Z on 2026-08-20:

| fixture commence | total books | books with spreads | Pinnacle on spreads |
|---|---|---|---|
| 2026-08-20 22:36Z (+70 min) | 27 | 25 | yes |
| 2026-08-21 00:06Z (+2h40) | 27 | 25 | yes |
| 2026-08-21 00:11Z (+2h45) | 27 | 25 | yes |
| 2026-08-21 20:11Z (+22h45) | 13 | 7 | no |
| every other 2026-08-21/22 fixture (+22h to +28h) | 8–13 | 5–8 | no |

Book coverage looks like a function of **time to commence** rather than of
date. Pinnacle was present at +2h45 and absent at +22h45; the horizon at which
it appears lies somewhere in between and is **not known** from one capture.
This is the likely reason the first look yielded 3 matched games out of 12
Kalshi-listed events, and the reason a 22:40Z anchor on the day of the slate is
expected to do better. **It is an expectation drawn from one capture, not a
fact, and it is recorded as such.**

### 2.2 Expected yield at the anchor

Look 1 yield, among **sharp-anchored games**: 1.00 sharp spread rows per game
(3/3) and 0.67 sharp totals rows per game (2/3). Applying those rates, with
Poisson counts:

| sharp-anchored games at anchor | expected sharp spread rows | P(spread arm clears 8) | expected sharp totals rows | P(totals arm clears 8) |
|---|---|---|---|---|
| 8 | 8.0 | ≈ 0.55 | 5.3 | ≈ 0.16 |
| 10 | 10.0 | ≈ 0.78 | 6.7 | ≈ 0.33 |
| 12 | 12.0 | ≈ 0.92 | 8.0 | ≈ 0.55 |

**Registered in advance: the totals arm is more likely than not to return
UNDERPOWERED again.** That is stated here so that a totals UNDERPOWERED on
2026-08-21 is read as a foreseen outcome of a rate written down beforehand, and
not as a surprise, a failure of execution, or a reason to ask for a third look.
The totals arm rides along at **zero marginal cost** — the same 4-credit
`spreads,totals` sweep serves both arms — which is the only reason it is
carried at all.

### 2.3 The detectable effect, against the headroom that matters

Look 1's five sharp rows give a pooled dispersion of **sd ≈ 9.7 tenths of a
cent** (n = 5; the 95% interval on that sd is roughly [5.8, 28] tenths, so the
number below is a range, not a point).

At the registered floor of 8 sharp-anchored rows on ~8 game clusters:

    SE ≈ 9.7 / sqrt(8) ≈ 3.4 tenths = 0.34 probability points
    2-SE minimum detectable effect ≈ 0.69 points
    (range implied by the sd interval: 0.41 to 1.98 points)

The headroom this project exists to measure is **0.63 points** — 52.38% at a
sportsbook against 51.75% applied taker — and CLAUDE.md records that 0.63 is an
**upper bound pending H4**, not a point figure. So:

**At the floor, the detectable effect straddles the entire cost headroom.** To
resolve 0.63 points at 2 SE requires SE ≤ 3.15 tenths, i.e. **n ≥ ~9–10 sharp
game clusters** at the central sd, and **n ≥ ~20** if the true sd sits at the
top of its interval. One 12-game slate reaches the first and cannot reach the
second.

**The consequence, registered now:** this design can credibly return
**REFUTED** — a negative median is a negative median, and the sign is what the
convening bought. It **cannot credibly certify an edge of the size that would
actually matter**. Section 6 encodes that asymmetry rather than hiding it.

**Verdict on the design: proceed.** 4 credits against 18,664 remaining, on a
question the partner has already declared terminal, with a spread arm that
clears its floor with probability roughly 0.55–0.92 and a second arm free.

---

## 3. The anchor, fixed before the sweep

**Anchor: 2026-08-21 22:40:00Z.** Permitted execution band **22:35:00Z to
22:45:00Z**, to absorb clock and process latency. The band exists to make the
anchor executable, not to allow selection: **the first successful sweep inside
the band is the look**, whatever it returns.

The anchor is fixed **now**, before any sweep, and was chosen by the partner
against the published MLB schedule (~12 games in coverage), not against any
price artifact.

Conditions that must hold at execution, both outcome-independent:

1. The `baseball_mlb` odds window is open (the vendor serves the sweep).
2. The per-game commence window in §4 admits at least one game.

If neither can be satisfied inside the band and **no credits are spent**, the
look is **UNTAKEN** — see §8.

---

## 4. The population, the unit, the exclusions

Restated in full from look 1, with one change, named.

- **One sweep**, `markets=spreads,totals`, `regions=us,eu`, `baseball_mlb`,
  4 credits, taken at the §3 anchor. **One look. No re-sweep on a thin result,
  no re-sweep on a surprising result.**
- **Kalshi side:** every `KXMLBSPREAD` and `KXMLBTOTAL` market whose event
  matches an in-window odds fixture, book read via REST within 5 minutes of the
  odds sweep. If either series lists nothing, that is reported, not skipped.
- **CHANGED — the commence rule is now per game, not per slate.** Look 1's §3
  required the sweep to be "at least 15 minutes before the earliest stored
  commence of *that slate*". On a 12-game slate with staggered starts, one
  already-commenced afternoon game would veto a sweep on eleven untouched
  evening games — a slate-level rule applied to a per-game hazard. The rule
  protects against reading a book on a commenced market, which is a per-market
  contamination. It is therefore restated per game:

      a matched game enters the population only if its odds-fixture
      commence_time lies in [taken_at + 15 minutes, taken_at + 12 hours]

  Games outside that interval are **excluded and counted**
  (`commenced_or_imminent`, `outside_window`). The 12-hour cap admits the whole
  evening slate through any West Coast late start and excludes the following
  day's listings. `commence_time` is fixed before the sweep and is independent
  of every price, so this exclusion cannot reference the dependent variable.
- **The unit of independence is the game.** A game's spread and total resolve
  from one final score; rows are market × side and **cluster by game**. The
  clustering variable is the odds-fixture game id (equivalently the Kalshi
  `fixture_segment`). The per-game view prints beside every aggregate.
- **Nothing is written to any production table.** Raw payloads land as files;
  the runner, linker and odds store are untouched; the signal test's G-counter
  and cluster key are not touched. This is an engineering-safety condition of
  the registration, carried forward unchanged.

### Matching — exact, refusing, and counted (unchanged from look 1)

- A book's quote joins a Kalshi market only on **exact line equality**
  (`floor_strike == outcome_point`, no tolerance, no conversion beyond the
  documented sign convention: a Kalshi spread `"<team> wins by over X.5"` is
  that team at **−X.5** and the opponent at **+X.5**; totals join
  `floor_strike == point` with Kalshi YES = Over), and — for spreads — on the
  **same team**, resolved through the repo's own alias normalisation. Any row
  whose team or sign convention cannot be resolved without guessing is
  **excluded and counted, never approximated**.
- A book contributes only if it quotes **both sides at that same line**; a
  one-sided quote cannot be devigged.
- A Kalshi row with fewer than 2 contributing books is **excluded and counted**.
- A `KXMLBTOTAL` event with no `KXMLBSPREAD` sibling in the same fixture
  segment is **excluded and counted** (totals subtitles name no team).

**No exclusion in this list references the fee-net edge, the ask, or the
consensus fair.** Every one is decidable from schedule, team names, line values
and book counts alone.

---

## 5. The statistic, named as an estimator (unchanged from look 1)

Per contributing book: implied probabilities from the two-sided pair at the
matched line → **all four devig methods** (`core/devig.py`, the production
code) → per-book fair for the Kalshi YES outcome = the **minimum across
methods** (worst-of-four, house rule 2). Consensus fair = **median across
books**. Then

    fee_net_edge_tenths = 1000 * fair - (derived_ask_tenths + fee_tenths)

**Differenced against the derived ask — the price actually paid — never the
mid.** `fee_tenths` at C = 1 taker from `ceil(k * P * (1 - P))` on the $0.0001
deci-cent grid:

- **decision arm:** k = 0.070 × the series or event `fee_multiplier`
  (0.5 on both MLB series, re-confirmed live at look 1's sweep) = **0.035**,
  the fee the venue actually charges;
- **sensitivity arm:** k = **0.070**, the deployed conservative bar, printed
  beside and **never deciding**.

An event-level `fee_multiplier_override` / `fee_type_override`, if non-null,
takes precedence over the series value and is recorded in the artifact.

A row is **sharp-anchored** if **Pinnacle contributes at that exact line**. The
distribution is reported split by that flag; **the decision reads the
sharp-anchored rows only**, because unanchored rows are already known to
manufacture apparent edge (ADR 0021 measured 423 fallback rows producing 0
actionable).

**The estimator being decided on is a median of game-clustered fee-net edge
rows, per arm.** It is not a proportion, and `sqrt(p(1-p)/n)` does not apply
to it.

**Added, and strictly non-decisional:** the **game-clustered mean and its
clustered standard error** print beside the median for each arm. Look 1's §3
declared the game to be the unit of independence and its §6 then decided on a
row median that treats rows as exchangeable. This registration prints both. The
clustered view **may only qualify a NOT REFUTED downward** (§6.2); it may never
turn a REFUTED into anything else, and may never create a verdict of its own.
That asymmetry is deliberate — the added statistic must not become a second
chance to find something.

---

## 6. The decision rule, with the multiplicity already counted

### 6.1 The rule, carried forward and applied per arm

> Read `n` first, per arm: fewer than **8 sharp-anchored rows** or fewer than
> **3 distinct games** in that arm ⇒ verdict **UNDERPOWERED** for that arm —
> no pass, no fail, and the ADR 0038 quadrant row is unchanged. Otherwise, on
> that arm's sharp-anchored rows at the charged fee (k = 0.035):
> median fee-net edge **≤ 0** ⇒ **REFUTED**; median **> 0** ⇒ **NOT
> REFUTED**, which opens nothing, changes no code, and — this look being
> terminal — buys no further look.

**The floor stays at 8 sharp-anchored rows and 3 distinct games per arm.** It
is not lowered, and it is not lowered *because* look 1 came in at 3 and 2. A
floor moved after a thin sample is not a floor.

**Spreads and totals are reported separately and decided separately**, exactly
as in look 1. A pooled-across-arms number may be printed only beside its parts.

### 6.2 What NOT REFUTED means on a terminal look — fixed now

A terminal look has no "buy a second look" branch, so that branch must be
replaced before the data exists rather than improvised after it.

- **NOT REFUTED does not reopen the ADR 0038 quadrant.** ADR 0038 requires any
  reopening to name the row it overturns and the measurement that overturns it.
  This registration is that measurement, and §6.3 shows a positive median at
  n = 8 is close to a coin flip under a pure null. A NOT REFUTED therefore
  **annotates** the quadrant row; it does not change it.
- **A NOT REFUTED must be reported with its chance rate and with the phrase
  "not separated from zero", unless every sharp-anchored row in that arm is
  positive.** At 8 exchangeable rows the sign test gives p = 0.0078 two-sided
  for 8/8 and p = 0.070 for 7/8; 7/8 does not clear 0.05, so the pre-fixed
  threshold is **all rows positive**. Anything short of that is
  noise-compatible and is written up saying so.
- A reopening requires a **new authorization** from the partner, citing this
  file and naming a sample-size target computed from this look's observed
  sharp-row-per-game rate. It is not granted by this document under any
  outcome.

### 6.3 The multiplicity, counted before the run

- **This look tests 2 cells** (spread arm, totals arm), one-sided.
- Under a true zero, P(median > 0) on 8 exchangeable rows ≈ **0.36**
  (binomial: P(≥5 of 8 positive) = 93/256). Across 2 arms,
  P(at least one arm returns NOT REFUTED) ≈ 1 − 0.64² ≈ **0.59**.
- **That is the honest reading of this design: a NOT REFUTED on one arm at the
  floor is close to a coin flip under no edge at all.** It is written here, in
  advance, so it cannot be omitted from a write-up that happens to contain one.
- **Look 1 spent no alpha on C1.** Its floor read is a count of rows, which is
  outcome-independent, and its verdict was UNDERPOWERED on both arms — the
  effect test never fired. The C1 test therefore fires for the **first and last
  time** on 2026-08-21, on at most 2 cells.
- **No always-valid boundary is required, because the record is not being
  re-read as it grows.** This is one fixed sweep at one fixed anchor with a
  registered terminal date. There is no accumulating database and no repeated
  threshold evaluation — the failure mode measured at 13.7% elsewhere in this
  repo. If that ever changes, this design is void and needs a new registration.

### 6.4 Pooling with look 1 — decided before the data: **NO**

**Look 1's rows and look 2's rows are NOT pooled for any verdict.** The
decision reads look 2's sharp-anchored rows alone, against the same per-arm
floor of 8 rows and 3 games.

Reasons, in the order that matters:

1. **The pooling decision would be contaminated.** All five of look 1's sharp
   rows are already known to be negative. Choosing to pool now is choosing a
   procedure knowing which way it moves the answer, and it moves it toward the
   prior. That is precisely the freedom this document exists to remove.
2. Look 1 is **published under UNDERPOWERED**, and UNDERPOWERED means the
   effect was not tested. Promoting its rows into a later denominator would
   retroactively convert a non-test into evidence.
3. The floors are per-look for the same reason: a floor that can be reached by
   adding a previous look's rows is a floor that can always be reached by
   waiting.

**A pooled number MAY be printed**, clearly labelled **post-hoc,
non-decisional, and taken across two different slates**, in a section separate
from the verdict — this repo's rule that a pooled number is not a finding until
the parts agree applies to it in full, and the parts here are 5 rows and
whatever look 2 returns. It may not appear in the verdict table, in a summary,
or in the ADR 0038 row.

### 6.5 The full verdict space, and what each does to the ADR 0038 row

The quadrant row in play is ADR 0038's / CLAUDE.md's **"Consensus vs Kalshi's
close"** row, extended from h2h to spread and total market types.

| spread arm | totals arm | consequence |
|---|---|---|
| REFUTED | REFUTED | The row **gains this measurement as its citation**, extended to spreads and totals. Quadrant stays closed. No blocker is written. Question **closed with evidence**. |
| REFUTED | UNDERPOWERED | Row gains the citation **for spreads only**; totals is recorded as never resolved and closed by exhaustion. |
| UNDERPOWERED | REFUTED | Mirror of the above. |
| UNDERPOWERED | UNDERPOWERED | **Row unchanged.** The question is **closed by exhaustion of authorized looks**, not by evidence, and the write-up says exactly that. No third look. |
| NOT REFUTED (either arm) | any | Row **annotated, not changed**: "one terminal look, median > 0 on N sharp rows, [not separated from zero \| all N rows positive], no reopening authorized." A new authorization would be required to go further. Nothing is built, no code changes, the gate does not move. |
| NO-OVERLAP (C2 fails) | any | C1 untested on that arm; recorded as a finding about the join, not about the edge. |

**What is built if it clears:** nothing, automatically. **What is killed if it
does not:** the spread/total extension of the consensus hunt, permanently under
the current authorization.

**Is this decision-relevant?** Partly, and the asymmetry is stated rather than
papered over. REFUTED closes a line of inquiry and stops future sessions
re-proposing it — that is the value the convening bought for 4 credits.
UNDERPOWERED closes the same line by exhaustion, which is weaker but still a
real closure. NOT REFUTED changes nothing on its own. **No branch of this
measurement causes code to be written or an order to be placed**, and that is
by design: the gate is untouched, `ORDERS_ARE_DRY_RUNS` is untouched, and
nothing here reaches Joe's discretionary betting.

---

## 7. The stopping rule, and the spend

- **Data collection ends at the single sweep at the §3 anchor.** One sweep.
  4 credits. The vendor counter stood at **1336 used / 18664 remaining** after
  look 1 on a 20K/month plan; this look takes it to **1340**.
- **There is no second sweep on 2026-08-21 for any reason**, including a thin
  slate, a surprising number, or a suspicion of a computation bug — a suspected
  computation bug is resolved with `--replay` on the saved raw artifact, which
  spends nothing. That is why `--replay` exists.
- **The look is terminal.** No third look under this authorization, in any
  branch of §6.5.

### 7.1 Joe's veto

**Joe holds a veto on spending the 4 credits.** A veto issued **before the
anchor** cancels the look **without prejudice**: the authorization is spent, no
credits are spent, and the outcome is recorded as **VETOED** in the §8 result
file — explicitly, with the date and the fact that no data was read. A vetoed
look is **not** an untaken look and is **not** a silent non-event. The failure
mode this clause exists to prevent is a measurement that quietly never happens
and leaves a later reader unable to tell refusal from oversight.

A veto after a successful sweep is not available — the credits are spent and
the result is written per §6 regardless of what it says.

---

## 8. What falsifies the setup rather than the claim, and where every branch is written

**Every branch below, including all of §6.5, is written to one file, created
whatever happens:**

    docs/measurements/2026-08-21-spread-total-edge-second-look-result.md

Its existence is required by 2026-08-22. If the look does not happen, that file
says so and says why.

- **UNTAKEN** — the vendor window is not open in the band, the sweep 401s or
  otherwise fails before serving, or the §4 commence window admits no game, and
  **no credits are spent.** A refused request is not a look (the 2026-08-20
  21:21:04Z 401 is the precedent). The single authorization survives, and the
  partner may **re-anchor once**, in writing, before the new anchor, naming the
  documented setup failure. **Re-anchoring is available only for a setup
  failure that spent nothing** — never after a served sweep, never on the basis
  of a slate that looks thin, and never on the basis of a number.
- **VETOED** — §7.1.
- **NO-OVERLAP** — C2 fails: no exact-line overlap. A real finding about the
  join; C1 untested.
- **Systematic 0.5 line offset** — the books' points miss Kalshi's rungs by a
  constant half-run. Same handling as NO-OVERLAP, and recorded as its own fact.
- **INSTRUMENT FAULT** — the §9 replay gate fails. The anchor is not taken.

---

## 9. The instrument, and the only edits permitted before the anchor

Instrument: `scripts/measure_spread_edge.py`. The 401 hardening (fail with the
status alone, URL and key withheld) is in place since **095c1e9** and is a
precondition of running at all.

**Exactly three mechanical edits are permitted before the anchor.** Each is
outcome-independent; none touches matching, devig, the fee model, the
statistic, the floor or the verdict logic:

1. The per-game commence window filter of §4, with the two new exclusion
   counters `commenced_or_imminent` and `outside_window`.
2. The artifact filename prefix, currently hardcoded `2026-08-20-`, so look 2's
   artifacts are filed under their own date:
   `2026-08-21-spread-sweep-raw-<stamp>.json` and
   `2026-08-21-spread-edge-rows-<stamp>.json`.
3. The rows artifact's `"registration"` field, to name **this** file.

**The replay gate, run before the anchor and free:**

    .venv\Scripts\python.exe scripts\measure_spread_edge.py --replay
      docs\measurements\2026-08-20-spread-sweep-raw-2026-08-20T212616Z.json

must reproduce look 1's published numbers **exactly** — 11 spread rows / 3
sharp-anchored / 3 games, 12 totals rows / 2 sharp-anchored / 2 games, both
arms UNDERPOWERED, and the five edge values −25.0, −3.5, −19.2, −15.3, −2.9
tenths. Look 1's three matched games commence at +70 min, +2h40 and +2h45, all
inside the new window, so edit 1 must be a **no-op on that artifact**. If the
replay differs in any figure, the anchor is **not taken** and §8's INSTRUMENT
FAULT applies.

**No edit to the instrument is permitted after the sweep**, other than one that
`--replay` proves changes no published number.

---

## 10. What this cannot establish, drafted before it is run

- **Nothing about CLV.** No closing lines are read, no signal-test cluster is
  touched, `beta` is unaffected and the G-counter does not move.
- **Nothing about execution.** Depth and half-spread are reported as context,
  not modelled. A positive fee-net edge on a derived ask is not a fill.
- **Nothing about maker fees or about settlement.** The charged arm is a taker
  fee at C = 1. **H4 — that settlement carries no separate fee — remains
  untested** (ADR 0027), so the 0.63-point headroom this is measured against is
  an upper bound, and an edge that clears it by less than an unmeasured
  settlement charge has not been shown to clear anything.
- **Nothing about any sport but MLB, or any date but 2026-08-21.** In
  particular nothing about NBA or NFL, absent from the 2026-08-06 capture, whose
  calendar caveat in `backend/kalshi/combos.py` is untouched.
- **Nothing about the Kalshi rungs the books do not quote.** Look 1 excluded
  152 rows as `no_exact_line`. The measured population is the exact-line
  intersection, which was a **minority** of the venue's listed ladder in the one
  slate observed. An edge could exist on rungs this design cannot see, and this
  design will not find it.
- **Nothing about times other than the anchor.** A single 22:40Z read says
  nothing about the same lines an hour later; prices at other horizons are not
  observed.
- **A REFUTED verdict does not strengthen the h2h refutation.** It extends the
  same conclusion to two more market types at the venue's better prices.
- **An UNDERPOWERED verdict establishes nothing at all about C1**, in either
  direction. Look 1's five sharp rows plus whatever look 2 returns under
  UNDERPOWERED remain a **description**. Anyone quoting those numbers quotes
  the UNDERPOWERED verdict with them.
- **The most likely single thing that would overturn a REFUTED here:**
  worst-of-four devig on spread and total pairs may be systematically
  conservative by more than the fee bar, devigging a true positive edge away
  before the comparison is made. This design cannot detect that, because it has
  no independent measure of the true probability — only the books' own
  consensus. It is named here so it cannot be omitted from a caveat list
  assembled after a negative result.

---

*Registered before the anchor. Committed before the sweep. Scored against, not
rewritten.*
