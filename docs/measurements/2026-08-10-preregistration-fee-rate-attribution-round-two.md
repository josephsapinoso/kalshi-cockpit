# Pre-registration — round two: what the two fee rates are *attributed to*

**Registered 2026-08-10 (UTC), before any round-two order exists.**
**Fills in scope at registration time: 0.**

This is a **new registration**, not an amendment. It does not edit, reinterpret
or reopen
[`2026-08-10-preregistration-fee-model-fill-calibration.md`](2026-08-10-preregistration-fee-model-fill-calibration.md)
(body + Amendment A), which is closed and owned by another lane, nor the round-one
result document. Where this file needs a round-one fact it **cites** it and does
not restate it as new evidence.

**It authorises no deploy and no code change.** §9 of that registration and §2 of
its body forbid deploying a model fitted to those fills. That prohibition stands
and is extended here: **this round decides an attribution; it does not touch
`backend/core/fees.py`.**

---

## §0. What round one established, and the exact boundary of what it did not

Six taker fills, 2026-08-10, all cited from the round-one record:

| series | `C` | `P` | `fee_cost` |
|---|---:|---:|---:|
| KXMLBGAME | 0.27 | 0.2700 | 0.001900 |
| KXMLBGAME | 1 | 0.2700 | 0.006900 |
| KXMLBGAME | 10 | 0.2700 | 0.069000 |
| KXATPDOUBLES | 20 | 0.1500 | 0.178500 |
| KXMLBGAME | 1 | 0.4800 | 0.008800 |
| KXMLBGAME | 1 | 0.4800 | 0.008800 |

Licensed by `measurement-skeptic` and carried forward here as **given**, not
re-derived:

- `fee_cost` is **`ceil` to $0.0001**. That `(granularity, rounding)` pair is the
  unique survivor of a 20-cell census with the coefficient left free.
- **Scope is per-order**, refuted coefficient-free.
- **A single rate across the two series is refuted shape-free.**
- Conditional on `C·P(1−P)`: **`k_MLB ∈ (0.03495687, 0.03500761]`**,
  **`k_ATP ∈ (0.06996078, 0.07000000]`**.
- The MLB shape test admits `P(1−P)` and refutes `P`, `min(P,1−P)`,
  `sqrt(P(1−P))`, `(P(1−P))²` and constant.

**What round one could not do is say what the two rates are attributed to.** The
whole of round two is that one question, and nothing else.

### §0.1 The decision this attribution actually governs

Stated now so the round is not later described as bookkeeping.

**[COMPUTED, `backend/core/fees.py` as deployed]** at 50c and `N = 1`,
`calculate_fee(500, 1)` returns **$0.0200**, which is where CLAUDE.md's
**52.00%** taker break-even comes from. At the same point a rate of `k ≈ 0.035`
charged to $0.0001 gives `ceil(0.035 × 0.25) = $0.0088`, a break-even of
**50.88%** — a **1.12-point** move against **0.38 points** of assumed headroom.

**Round one already implies the deployed bar is wrong.** What round one cannot
say is **which markets, sizes and prices the low rate applies to** — and that is
exactly what decides whether the tool's own trades are priced at 52.00% or near
50.88%. That is this round's decision relevance, and it is also precisely why
§9 forbids acting on it from four fills.

---

## §C. Corrections to the brief, made before the design was fixed

Six. Each changed the design; none was made after seeing a round-two number,
because none exists.

### C1. "Rate by SERIES" is not a hypothesis of the same kind as the other three, and the proposed third cell does not split it from SPORT

`rate by SERIES` carries **one free parameter per series**. It makes **no
prediction whatsoever** about a series it has not seen. So a fill on
`KXMLBTOTAL` cannot discriminate SERIES from SPORT: whatever it returns, SERIES
absorbs it as a new table entry.

The brief's framing — *"`0.035` implicates sport or the MLB family, `0.07`
implicates the series"* — is **wrong in the `0.035` direction**. `0.035` there
implicates nothing; it is consistent with both.

The cell is kept anyway, for a **different and larger** reason (C2). And SERIES
is not unfalsifiable in this design: it is falsified by **any KXMLBGAME cell
returning the high rate** (D1, D2) or by **KXATPDOUBLES returning the low rate**
(D4). It is falsifiable *within* a series, never *across* one. §Power quantifies
the asymmetry: SERIES survives 2 of 16 outcome vectors, every other attribution 1.

### C2. The third cell's real job is to kill three attributions at once, and it is worth its $0.39

Placed at **`C = 1`, ask ≥ 27c**, a non-`KXMLBGAME` MLB series is a cell where
**SPORT, SIZE, PRICE and NOTIONAL all predict the low rate** and only SERIES is
free. A high rate there refutes **four attributions simultaneously** and says the
rate is per-series, i.e. must be measured before any new series is traded.

That is a much stronger cell than a SERIES/SPORT splitter, and it is
decision-relevant: the tool surfaces MLB moneyline, spread and total. **Yes, it
earns its cost.**

### C3. The ATP cell is not scope creep; without it the design has a surviving hypothesis with no falsifier in it

The brief offers the extra ATP fill as *"one more degree of freedom for
`k_ATP`"*. That undersells it and would have got it cut.

With only D1, D2 and D3, the outcome `(low, low, low)` leaves **{SERIES, SPORT}**
standing and **contains no cell capable of refuting either**. A design whose
surviving hypothesis has no falsifier inside it is not a measurement.
**D4 is the falsifier**, and it costs $0.27–$0.39. It is registered as a
necessary cell, not a bonus. The second degree of freedom on `k_ATP` — at a price
that does **not** land on the $0.0001 grid, unlike round one's — is a by-product.

### C4. A fifth attribution fits all six round-one fills and the brief's list omits it: **rate by NOTIONAL**

`rate by NOTIONAL` — the *dollar stake* of the order, not its contract count:

```
MLB  0.27 x 0.27 = $0.0729   low
MLB  1    x 0.27 = $0.27     low
MLB  10   x 0.27 = $2.70     low
MLB  1    x 0.48 = $0.48     low
ATP  20   x 0.15 = $3.00     high
```

A threshold anywhere in **($2.70, $3.00]** fits **all six fills exactly**, as
well as any of the brief's four. Omitting it would have made a `(low, low, low,
low)` result look like "all four attributions died" when it is in fact the
**signature** of a stake-based rule.

This is registered in advance and it **changes the cells**: D2's band is capped
at 14c so that `20 × price ≤ $2.80` stays at or below the ambiguity window,
and it is capped at 13c for an unambiguous reading (§1). Kalshi is a venue with
per-order economics; a stake threshold is not an exotic hypothesis.

### C5. Round one's mirror permission must **not** be carried over to D1/D2

Round one §3 permits trading the mirror (an ask of 76c is "the same cell" as 24c)
on the ground that `p(1−p)` is symmetric. That is a fact about the **fee
magnitude under an assumed symmetric formula**. It does **not** transfer to a
hypothesis whose boundary is on `P` itself: under `PRICE`, buying NO at 87c has
`P = 0.87` and predicts the **low** rate, while buying YES at 13c predicts the
**high** rate. The mirror would silently destroy the cell it is applied to.

**The mirror is forbidden for D1 and D2** and permitted for D3/D4 (where both the
threshold and the symmetric reading of PRICE agree). D2's mirror is over budget
anyway — 20 contracts at 87c is $17.40.

### C6. "`P ≈ 0.15`" is not tight enough, and 15c is precisely the trap the brief warns about

Two independent problems with the brief's `P ≈ 0.15`:

1. Every price threshold consistent with round one has its boundary in
   **(0.15, 0.27]**. A fill at 0.18 or 0.22 makes the PRICE prediction
   **undetermined** and hands a post-hoc rescue ("the boundary is 0.16") to
   whichever way it comes out. **The band must be `≤ 14c`.**
2. At `C = 20`, **15c is one of the prices where the high-rate prediction lands
   exactly on the $0.0001 grid** (`0.07 × 20 × 0.1275 = 0.178500`) — the same
   coincidence that made round one's ATP cell discriminate no rounding rule.
   **[COMPUTED]** at `C = 20` this happens at every whole-cent price that is a
   multiple of 5; at `C = 1` it happens at 20c, 30c and 40c.

The registered bands **exclude 10c, 15c, 20c, 30c, 40c and everything in
15c–26c**, so **no registered cell lands exactly on the grid under either
candidate rate** (§R3), and every cell re-tests the rounding rule for free.

---

## §P. Preconditions — checked before any comparison is made

Each is yes/no. If any is NO the run stops and this file is **amended by
appending**, never edited in place.

- **P1 — the fill record carries `fee_cost`, `count`, `price`, `is_taker`,
  `ticker`.** Established for this account by round one. If a field is missing,
  the affected cell is VOID.
- **P2 — unit sanity, mechanical, on D2 alone.** Interpret D2's raw `fee_cost` as
  dollars, as cents and as centi-cents; retain each interpretation implying a fee
  in **[$0.001, $1.00]**. If exactly one survives, that is the unit for all four
  cells. If zero or more than one survives, **STOP — the unit is not identified**
  and no comparison is made. (The window is four orders of magnitude wide on
  purpose: it catches a unit change without swallowing a novel rate.)
- **P3 — `is_taker` is true.** A maker fill **VOIDS the cell for attribution
  purposes**, because the maker multiplier is unobserved everywhere in this
  project and would confound the rate reading. Its fee is published anyway, as
  the first maker observation on record, explicitly labelled descriptive.
- **P4 — one fill row per order.** Per-order scope is established; an order that
  fills in pieces is ambiguous between per-order and per-fill and this design
  cannot resolve it. More than one fill row ⇒ **VOID**.
- **P5 — `count` reads exactly `N`.** The realised failure mode of round one: the
  app defaulted to buy-in-dollars and produced `count = 0.27`. A cell whose
  `count` is not the integer `N` is **VOID**. §3 registers the pre-submit check
  that prevents it.
- **P6 — the observed price is inside the registered band and is not an excluded
  price.** Outside ⇒ **VOID**. Its fee is published anyway.
- **P7 — D1's recorded `fee_cost` is unchanged after D2 is placed.** D1 and D2
  sit in the same series and normally the same market. If Kalshi aggregated
  orders for fee purposes, D1's fee would move retroactively. Re-read it; if it
  changed, **STOP THE LINE** — per-order scope is under-specified in a way no
  cell here tests.
- **P8 — every void is recorded with its mechanical reason and its observed fee
  is published.** Every reason in P3–P6 is checkable **without looking at the fee
  value**, and publishing the fee of every voided cell removes the incentive to
  void one.

---

## §1. The question, as five claims that could be false

Each of the five is a rule that reproduces all six round-one fills. Round two
asks which of them survives. `LOW` means "the fee equals `ceil(k·C·P(1−P))` to
$0.0001 for some `k ∈ (0.03495687, 0.03500761]`"; `HIGH` means the same for
`k ∈ (0.06996078, 0.07000000]`.

> **H-SERIES.** The rate is a per-series lookup. `KXMLBGAME → LOW`,
> `KXATPDOUBLES → HIGH`, other series unconstrained.
> *Falsifier: any KXMLBGAME cell returning HIGH, or KXATPDOUBLES returning LOW,
> or any cell returning neither.*

> **H-SPORT.** The rate is per sport. Baseball `→ LOW`, non-baseball `→ HIGH`.
> *Falsifier: any baseball cell HIGH, any non-baseball cell LOW, or neither.*

> **H-SIZE.** The rate is per order size. `C < 20 → LOW`, `C ≥ 20 → HIGH`.
> *Falsifier: a `C = 1` cell HIGH, a `C = 20` cell LOW, or neither.*

> **H-PRICE.** The rate is a **monotone threshold on the traded price**, `P < b →
> HIGH` with `b ∈ (0.15, 0.27]`.
> *Falsifier: a cell at `P ≤ 0.14` returning LOW, a cell at `P ≥ 0.27` returning
> HIGH, or neither.*

> **H-NOTIONAL.** The rate is a threshold on order stake, `C·P ≥ t → HIGH` with
> `t ∈ ($2.70, $3.00]`.
> *Falsifier: a cell with `C·P ≤ $2.70` returning HIGH, a cell with `C·P ≥ $3.00`
> returning LOW, or neither.*

> **H-NONE.** No member of the family above fits every non-void cell.
> **Registered as a first-class outcome, not a residual.** §7 names it, §Power
> shows it occupies **11 of the 16** reachable outcome vectors, and §9 gives it a
> destination.

**Direction is one-sided and conjunctive for each claim**: an attribution is
declared only if **every** non-void cell matches its prediction exactly. No claim
here is "the rate is 0.035"; each is "this rule reproduced these four cells".

### The four cells, fixed now

Bands are on **the price actually paid — the displayed ask you cross**, never a
mid. There is no fifth cell.

| Cell | Series constraint | `N` | Band (ask) | Excluded prices | Max stake |
|---|---|---:|---|---|---:|
| **D1** | `KXMLBGAME` | **1** | **6–14c** | 10c | $0.14 |
| **D2** | `KXMLBGAME`, same market as D1 where possible | **20** | **6–14c** | 10c | $2.80 |
| **D3** | `KXMLBTOTAL`, else `KXMLBSPREAD`, else any `KXMLB*` that is not `KXMLBGAME` | **1** | **27–39c** | 30c | $0.39 |
| **D4** | `KXATPDOUBLES` | **1** | **27–39c** | 30c | $0.39 |

**The prediction matrix, fixed before any fill:**

| | D1 (MLB, C=1, ≤14c) | D2 (MLB, C=20, ≤14c) | D3 (other MLB series, C=1, ≥27c) | D4 (ATP, C=1, ≥27c) |
|---|:--:|:--:|:--:|:--:|
| **H-SERIES** | LOW | LOW | *(free)* | HIGH |
| **H-SPORT** | LOW | LOW | LOW | HIGH |
| **H-SIZE** | LOW | **HIGH** | LOW | LOW |
| **H-PRICE** | **HIGH** | **HIGH** | LOW | LOW |
| **H-NOTIONAL** | LOW | LOW | LOW | LOW |

### The predicted `fee_cost` for every cell at every legal price, to $0.0001

**[COMPUTED, `ceil` to $0.0001 over the round-one `k` intervals]**. Where two
values are listed, the `k` interval straddles a grid boundary and **both are
admissible**; a single point prediction at `k = 0.035` exactly would have
manufactured a spurious mismatch, which is the sixth correction to the brief and
the least obvious one.

```
D1   KXMLBGAME   C = 1
   ask    LOW              HIGH
    6c    0.0020           0.0040
    7c    0.0023           0.0046
    8c    0.0026           0.0052
    9c    0.0029           0.0058
   11c    0.0035           0.0069
   12c    0.0037           0.0074
   13c    0.0040           0.0080
   14c    0.0043           0.0085

D2   KXMLBGAME   C = 20
   ask    LOW              HIGH             stake
    6c    0.0395           0.0790           $1.20
    7c    0.0456           0.0911 / 0.0912  $1.40
    8c    0.0515 / 0.0516  0.1030 / 0.1031  $1.60
    9c    0.0573 / 0.0574  0.1146 / 0.1147  $1.80
   11c    0.0685 / 0.0686  0.1370 / 0.1371  $2.20
   12c    0.0739 / 0.0740  0.1478 / 0.1479  $2.40
   13c    0.0791 / 0.0792  0.1583 / 0.1584  $2.60
   14c    0.0842 / 0.0843  0.1685 / 0.1686  $2.80

D3 and D4   C = 1   (identical predictions; different series)
   ask    LOW              HIGH
   27c    0.0069           0.0138
   28c    0.0071           0.0142
   29c    0.0072 / 0.0073  0.0145
   31c    0.0075           0.0150
   32c    0.0077           0.0153
   33c    0.0078           0.0155
   34c    0.0079           0.0157 / 0.0158
   35c    0.0080           0.0160
   36c    0.0081           0.0162
   37c    0.0082           0.0164
   38c    0.0083           0.0165
   39c    0.0084           0.0167
```

**If the fill lands on a deci-cent price**, recompute both sets at the observed
price by the same rule. No re-derivation of the *rule* is permitted, only its
evaluation. §R2 shows the two sets can never overlap at any tick.

**Bonus reading, registered now so it is not "discovered" later.** Every
two-valued cell above **narrows `k`**, and `C = 20` narrows it twenty times
faster per grid unit than `C = 1`. This is reported as a **by-product, labelled
as such**, and may not be presented as a result of the round or used to declare
anything.

### The one contingency, registered rather than improvised

If **D2 fills at 14c**, its notional is $2.80, which sits **inside** the
($2.70, $3.00] window inherited from round one. H-NOTIONAL's prediction for that
cell is then **UNDETERMINED**, D2 stops separating H-SIZE from H-NOTIONAL, and
the write-up must report `H-NOTIONAL: UNRESOLVED AT D2` in those words. D4 still
separates H-NOTIONAL from H-SERIES and H-SPORT. **Prefer an ask at 13c or below.**

---

## §2. The population, and the exclusions

**Included:** exactly the four registered orders, placed by hand in the Kalshi
app on 2026-08-10, within the window of §8.

**The dependent variable is `fee_cost`**, which is fixed at fill time by
`(price, count, taker/maker, series)` and by nothing else. It is **independent of
the game's result by construction** — the quantity is determined before the game
starts. No exclusion in this document references a game outcome, a settlement, a
P&L or an edge, and none could.

| Excluded | Why | Independent of the fee value? |
|---|---|---|
| `count != N` (P5) | The app's dollar-denominated mode produces a fractional count; the cell is not the registered cell. | **Yes** — an integer comparison on the ticket. |
| More than one fill row (P4) | Per-order versus per-fill is unresolvable here. | **Yes** — a row count. |
| A maker fill (P3) | The maker multiplier is unobserved everywhere in this project. | **Yes** — `is_taker`. |
| A price outside the band or on an excluded price (P6) | The band is the registered cut. | **Yes** — a price. |
| A market outside the cell's series constraint | The series *is* the treatment for D3 and D4. | **Yes** — a ticker prefix. |

**Rules that must not be activated after the fact.** If the verdict is H-NONE,
the temptations will be to widen a band, re-read a voided cell, drop D4, or admit
a nearby `k`. **All four are forbidden.** The precedent is in this repo: a combo
experiment pre-registered an exclusion and the agent correctly refused to
activate it when the sample turned out too thin — possible only because the rule
existed in writing first.

**Nothing observed here may be used to fit a new attribution in this document.**
If the verdict is H-NONE, the observed fees are a **hypothesis generator,
labelled as such**, and any sixth rule must be confirmed by a **new**
pre-registered set of fills before it is believed or deployed.

---

## §3. The unit of observation, the taker constraint, and the placement rules

**The unit is one order.** Not one contract and not one market. The 20 contracts
of D2 are **one** observation: they are charged by one formula evaluation and
per-order scope makes them mathematically inseparable. **The clustering variable
is `order_id`.** Any presentation of this round with `n = 23` is wrong; `n = 4`.

`n = 4` is not a sample size in any statistical sense. §5 says why that is
appropriate and §7 says why no interval appears anywhere.

### All four fills are taker

Joe places a **limit buy at exactly the displayed ask**, quantity `N`, in a
market whose **displayed resting size at that ask is `≥ N`**. A marketable limit
crosses immediately and Joe is the taker. Round one's `C = 20` at 15c filled, so
that depth exists at this size. A maker fill voids the cell (P3).

### Choosing among candidate markets — round one's rule, kept, with one addition

> Scan the Kalshi app's list for the cell's series **in its default order, top to
> bottom**. Take the **first** market whose displayed ask lies inside the cell's
> band, is not an excluded price, and whose displayed size at that ask is `≥ N`.
> Stop there. **No re-scanning, no comparison between candidates, no waiting for
> a better price.**

**Kept, not improved, on the substance** — it is already unbiased with respect to
the fee, because nothing about the app's ordering correlates with a fee rate, and
changing an anti-gaming rule between rounds is itself a degree of freedom.

**One addition, because round one had no rule for it and it is a real phone
problem:** if the displayed ask **moves between reading it and submitting**,
re-read; if the new ask is still in band, use it; if it has left the band, abandon
that market and resume the scan at the next one. **At most two such abandonments
per cell**; on the third, the cell is **NOT ATTEMPTED**.

If a full scan finds no qualifying market, the cell is **NOT ATTEMPTED** and is
reported as such (§7). **There is no substitute band.**

**Recorded at placement, from the app, for every order:** ticker, series prefix,
side, displayed ask, displayed size at the ask, contracts, the app's displayed
estimated cost, the app's displayed fee if any, and the timestamp.

### Registered substitutions, mechanical and fixed in advance

- **D1/D2 share a market** when the first qualifying KXMLBGAME market has
  displayed size **`≥ 21`** at the ask (1 for D1, 20 for D2). If one full scan
  finds no such market, D1 and D2 are placed in the **first and second**
  qualifying KXMLBGAME markets of that same scan, each meeting its own size
  requirement. This is registered in advance and **must be reported**; it costs
  only the price-identity between D1 and D2.
- **D3's series** is taken in the fixed order `KXMLBTOTAL`, `KXMLBSPREAD`, then
  any other listed series whose ticker begins `KXMLB` and is not `KXMLBGAME`,
  first qualifying market in each. All are the same league and the same sport.
- **D4's series is `KXATPDOUBLES`.** If it is not listed, D4 becomes **D4′**: the
  first **non-baseball** sports market in the default scan order with an ask in
  27–39c (not 30c) and size `≥ 1`. **D4′ tests H-SPORT only** — H-SERIES makes no
  prediction for a series it has not seen — and the substitution must appear in
  the verdict line. This is registered now so it is not chosen on the day.

### The pre-submit check — mandatory, every order, no exceptions

Round one's first fill was destroyed by the app defaulting to a dollar-denominated
buy, producing `count = 0.27`. This is a known, realised failure mode.

> **Before pressing submit, confirm all four on the ticket:**
> **(1)** the ticket says **"Limit order"** — not Market, not any
> dollars-to-spend mode;
> **(2)** the **shares / contracts field reads exactly `N`** — `1` for D1, `20`
> for D2, `1` for D3, `1` for D4 — as a whole number, not a dollar amount;
> **(3)** the **limit price equals the displayed ask exactly**;
> **(4)** the **estimated cost equals `N × ask` to the cent** — e.g. `1 × 13c`
> must read **$0.13**, and `20 × 13c` must read **$2.60**.
>
> If any of the four fails, **cancel the ticket and re-enter it.** A submitted
> order that fails check (2) is a **VOID cell**, not a data point.

Check (4) is the arithmetic cross-check that would have caught round one's
failure: a ticket reading $1.00 for one contract at 13c is a dollar-denominated
order wearing a limit order's clothes.

---

## §4. The cut — bucket edges, fixed in advance

The bands in §1 **are** the cut and they are on the derived ask. They were chosen
before any fill, by four data-blind criteria in this order:

1. **`P ≤ 14c` for D1/D2 and `P ≥ 27c` for D3/D4**, so H-PRICE's prediction is
   determined under **every** threshold consistent with round one (§C6). The
   whole range **15c–26c is excluded** because it is the ambiguity window.
2. **`20 × P ≤ $2.80` for D2**, so H-NOTIONAL's prediction is determined or, at
   14c, explicitly flagged UNDETERMINED (§C4, §1).
3. **No exact landing on the $0.0001 grid** under either candidate rate at any
   whole cent in any band. **[COMPUTED]** this excludes **10c** from D1/D2 and
   **30c** from D3/D4; 15c, 20c and 40c are already outside the bands. §R3.
4. **LOW and HIGH disjoint at every price in every band**, with the smallest gap
   **$0.0020** (D1 at 6c) — twenty grid units. §R2.

**No band may be widened, narrowed, shifted or added after any fill is observed.**
Bucket boundaries are the richest source of unearned findings precisely because so
many of them are defensible.

---

## §5. The statistic, named as an estimator

**There is no estimator.** This is not an inference.

Each cell yields an **exact comparison in units of $0.0001** between one observed
value and two small, deterministic prediction sets. The quantity compared is a
**charged fee**, not a sample mean, not a proportion, not a difference of paired
proportions. `sqrt(p(1-p)/n)` is correct for none of it and appears nowhere.

What is being estimated: **nothing**. What is being *decided*: which of five
deterministic attribution rules Kalshi is applying — a model-selection question
with six answers (five rules plus H-NONE), resolved by exact set membership.

**One grid unit of mismatch refutes the attribution for that cell.**
`FEE_MATCH_TOLERANCE_DOLLARS = 1e-9` (`core/fees.py:243`) is float noise and not
a business tolerance. The counterargument to recognise when it arrives — *"it is
only a hundredth of a cent"* — is answered by the fact that the two candidate
predictions are **20 to 842 grid units apart** at every registered price. Nothing
in this design is close to a boundary except the deliberately-registered
two-valued cells, and those are registered as sets, not as tolerances.

---

## §6. The extraction

1. Joe places **four** orders by hand, in the order **D1, D2, D3, D4**, with at
   least **60 seconds** between D1 and D2, recording the §3 fields at each
   placement.
2. An agent session pulls `/portfolio/fills` for the account. **This document does
   not specify, own or modify that script.** Note `.dockerignore:59-61` excludes
   `scripts/*` from the deployed image, so the pull is a **laptop-only** step and
   must be scheduled with an agent session — the same constraint Amendment A §A4
   records for round one. **No deploy, and no laptop step for Joe.**
3. `configure_logging()` **before** any client is constructed. `httpx` logs full
   request URLs at INFO and this repo has already put a working credential into a
   transcript that way.
4. The raw payload is cached to
   `docs/measurements/2026-08-1X-fee-rate-attribution-round-two-fills.json`, checked
   for and stripped of any credential before it is committed.

### §6.1 The balance channel — recoverable for D2 only, and only as a cross-check

Round one registered a balance-before/after fallback (its P2) and never ran it.
**Asked and answered here rather than left open:**

**[COMPUTED]** the in-app balance is displayed to the cent. The LOW/HIGH
difference is:

```
D2   $0.0395 - $0.0842   ->  9 to 84 hundredths of a cent apart in the total debit
                             RESOLVABLE at 2dp:  e.g. at 13c, $2.6792 vs $2.7584
D1   $0.0020 - $0.0043   ->  NOT RESOLVABLE at 2dp
D3   $0.0069 - $0.0084   ->  NOT RESOLVABLE at 2dp
D4   $0.0069 - $0.0084   ->  NOT RESOLVABLE at 2dp
```

> **Registered:** Joe records the displayed balance **verbatim, with every digit
> shown**, immediately before and immediately after **D2 only**. This is a
> **cross-check on the API's `fee_cost`, never the measurement**, and a
> disagreement is a STOP THE LINE about the instrument, not about the
> attribution. The reading is **VOID** if any other order, any settlement, or any
> other account movement occurs between the two readings — and because round
> one's positions settle within ~24h and MLB games resolve through the day, **it
> is likely to be void and that is expected, not a failure.** If the app displays
> more than two decimals, the same reading is recorded for D1, D3 and D4 too.

The honest summary: **the balance channel is recoverable for one of four cells,
as a cross-check only.** It is registered because it costs Joe two glances, and
because "we'll see" is the sentence this document exists to prevent.

### §6.2 The settlement capture — referenced, not duplicated

Amendment A §A5 already requires round one's four positions' **settlement
`fee_cost`** to be captured after they settle, and §A8 registers what that
separates: whether `/portfolio/settlements.fee_cost` is entry-only (reading i) or
lifetime (reading ii), and therefore whether settlement charges a second fee
(round one's H4). **This round does not test H4 and does not duplicate that
capture.**

What it does register is a **durable substitute channel** for itself, because
`/portfolio/fills` has a retention window (Amendment A §A4):

> The four round-two positions' **settlement `fee_cost`** is captured after they
> settle and recorded beside `fee_observed` in §S item 4. If the fill-time capture
> is missed for a cell, the settlement `fee_cost` is that cell's registered
> substitute — **conditional on round one's pending §A5 capture returning
> `settlement fee_cost == fill-time fee`.** If §A5 comes back unequal, this
> substitution is **withdrawn** and any cell relying on it is VOID.

**What the pending round-one capture settles that this round does not:** whether
settlement charges a second fee at all, and what `/portfolio/settlements.fee_cost`
means. **What this round settles that it does not:** which markets, sizes, prices
and stakes each rate applies to. They are disjoint and neither substitutes for the
other.

---

## §7. The decision rule, with the multiplicity already counted

### The multiplicity count

**Cells read: 4.** Comparisons: 4 cells × 2 rate sets = **8**. Attribution
predictions evaluated: 4 × 5 = **20**, of which one (D3 under H-SERIES) is free.

**No cell carries an interval, a standard error, a p-value or a significance
mark**, so no cell can produce a false finding by clearing a threshold, and the
family-wise error rate of this design is **empty rather than controlled**. The
rule is **conjunctive**: an attribution is declared only if it matches **every**
non-void cell, so **adding cells can only make declaration harder**.

**Is the record looked at more than once as it grows?** No. This registration
covers exactly the four fills of §1, read once, after all four are placed. There
is no accumulating database and therefore no always-valid boundary is required.
Round one's §7 reached the same conclusion for the same structural reason; the
13.7% floor measured in this repo applies to a threshold on a noisy statistic
re-evaluated against a growing record, and this is not that.

**The multiplicity that does bite here is the reverse one**, and it is stated in
§Power: of the 16 reachable outcome vectors, **11 leave every attribution dead**.
That is the design's discriminating power, and it is also its main risk.

### The decision rule, verbatim

> **GUARDS FIRST.** P1–P8 and R1–R5 are evaluated and printed **before any
> verdict**. If P2 (unit) or P7 (retroactive fee change) fails, the run reports
> **STOP THE LINE** with the failed precondition named and **no attribution is
> declared**. Voided cells (P3–P6) are excluded from every conjunction, are listed
> with their mechanical reason, and **their observed fee is published anyway**.
>
> **Let `C` be the set of non-void, attempted cells.** For each cell in `C`,
> `fee_observed` is classified as **LOW** if it is a member of that cell's
> registered LOW set at the observed price and count, **HIGH** if it is a member
> of the HIGH set, and **NOVEL** otherwise. The sets are those registered in §1,
> evaluated at the **observed** price; no set may be recomputed under a different
> rule.
>
> **A single NOVEL cell refutes all five attributions**, because every one of them
> predicts LOW or HIGH or nothing at every cell. Report the observed value and the
> implied rate interval `[fee − $0.0001, fee] / (C·P(1−P))`, **labelled
> hypothesis-generating**, and declare **H-NONE**.
>
> **H-SERIES DECLARED** iff `C` is non-empty and every cell in `C` matches:
> D1 LOW, D2 LOW, D4 HIGH, D3 anything.
> **H-SPORT DECLARED** iff every cell in `C` matches: D1 LOW, D2 LOW, D3 LOW,
> D4 HIGH.
> **H-SIZE DECLARED** iff every cell in `C` matches: D1 LOW, D2 HIGH, D3 LOW,
> D4 LOW.
> **H-PRICE DECLARED** iff every cell in `C` matches: D1 HIGH, D2 HIGH, D3 LOW,
> D4 LOW.
> **H-NOTIONAL DECLARED** iff every cell in `C` matches: D1 LOW, D2 LOW, D3 LOW,
> D4 LOW — **except** that if D2 filled at 14c, D2 is scored `UNDETERMINED` for
> this attribution only and reported as `H-NOTIONAL: UNRESOLVED AT D2`.
> **H-NONE DECLARED** iff no attribution above is declared. **This is a
> first-class verdict, not a failure of the run.**
>
> **More than one attribution may be declared**, and where that happens the
> write-up must say so in the verdict line. The known case is
> `(D1,D2,D3,D4) = (LOW, LOW, LOW, HIGH)`, which declares **both H-SERIES and
> H-SPORT** and which this design **cannot** separate (§C1). It must be reported
> as `H-SERIES / H-SPORT — NOT SEPARATED BY THIS DESIGN`, never as either alone.
>
> **COVERAGE QUALIFIER, mandatory and mechanical.** A declaration is **FULL** only
> if `C` contains all four cells. If any cell is VOID or NOT ATTEMPTED, the
> declaration is reported as **PARTIAL — CONSISTENT WITH, DOES NOT EXCLUDE**, and
> the write-up must name which attributions lost their falsifier. In particular:
> **without D4, H-SERIES and H-SPORT have no falsifier in the design** (§C3), and
> **without D2, H-SIZE has none.**
>
> **NOT ATTEMPTED is not a void and not a failure.** A cell for which no
> qualifying market was found is reported as `NOT ATTEMPTED`, excluded from `C`,
> and triggers the coverage qualifier.
>
> **NO CELL, NO SUB-READING AND NO BONUS READING** — including the `k`-narrowing
> of §1 and the balance cross-check of §6.1 — **may substitute for the
> conjunction**, be reported as significant, or be described with any word
> implying a test.

### Which outcome kills every attribution, and what that would mean

**[COMPUTED — all 16 reachable LOW/HIGH vectors]**

```
LLLL  H-NOTIONAL                       LHLL  H-SIZE
LLLH  H-SERIES / H-SPORT (not sep.)    HHLL  H-PRICE
LLHH  H-SERIES
every other vector (11 of 16)          ALL FIVE DEAD
```

**Any of the other eleven vectors — and any NOVEL fee — kills all five.** Named in
advance, that outcome means the rate is set by something outside this family. The
next candidates, registered now so they are not invented afterwards:

- **A per-order minimum fee.** The obvious generator of `HIGH` at `C = 1` and
  `LOW` at `C = 20`. **It is already disfavoured**: round one's accidental
  `C = 0.27` fill charged **$0.0019**, so any floor consistent with round one is
  `≤ $0.0019`, and no such floor can lift D1's LOW prediction ($0.0020–$0.0043)
  to its HIGH value. Stated with the caveat that a floor applying only to
  whole-contract orders would evade this — an epicycle, named rather than
  assumed away.
- **A liquidity, volume or maker-programme tier per market.**
- **A time-varying schedule** — which is why every order is placed on one date.
- **A non-monotone price rule** (a band rather than a threshold), which H-PRICE as
  registered does not cover and §10 disclaims.

**H-NONE is a real result with a destination (§9) and it does not license fitting
a sixth rule in this document.**

### Consequences, fixed before the answer

| Verdict | What is built | What is killed |
|---|---|---|
| **H-SERIES / H-SPORT (not separated)** | Nothing is built today. A follow-on registration for a **third sport** and a **second baseball league** (`KXNPBGAME`, `KXLMBGAME`), which is the only way to separate them. | The reading that the tool's fee depends on order size or price. `sizing.py`'s `contracts=1` path and every ADR 0021 `E1` figure become computable at the MLB rate — **pending that follow-on**, not now. |
| **H-SERIES alone** (D3 HIGH) | Nothing. A **per-series measurement requirement** before any new series is traded, with its own registration. | The assumption that a rate measured on `KXMLBGAME` transfers to `KXMLBTOTAL` or `KXMLBSPREAD` — which the tool's own surfacing currently assumes. This is the most operationally expensive outcome. |
| **H-SIZE** | Nothing. A registration that maps the size boundary between `C = 1` and `C = 20`. | The reading that `N = 1` and `N = 20` share a rate. `sizing.py:156` prices at `contracts=1`, so the `N = 1` rate is the one that matters and it would be the **cheap** one. |
| **H-PRICE** | Nothing. A registration that maps the price boundary inside (0.14, 0.27). | The reading that a rate measured at 27–48c transfers to the longshot prices where the fee is largest as a share of stake. |
| **H-NOTIONAL** | Nothing. A registration that maps the stake threshold. | The reading that the rate is a property of the *market*. It would be a property of the *ticket*, which is a different kind of fact and changes how sizing interacts with cost. |
| **H-NONE** | Nothing. A new registration, and `core/fees.py`'s docstring annotated with what was actually observed. | The claim that the two rates are explained by any simple market attribute. |

**Is this decision-relevant, honestly?** Yes, and it is worth being blunt about
the shape: **no branch authorises a deploy.** Every branch changes *which
follow-on registration is worth its money*, and three of the branches (H-SIZE,
H-PRICE, H-NOTIONAL) would mean the rate that applies to the tool's own trades is
not the one round one measured. A measurement that redirects the next spend and
can invalidate a pending inference is decision-relevant; one that proceeds
identically either way would not be, and this does not.

---

## §R. Reachability guards — both directions, before the data exists

This repo's joint bound died because nothing checked whether its decision value
was reachable, and the clean-shortfall run stopped itself because something did.

### R1 — every declared outcome is attainable on the legal grid

**[COMPUTED]** every value in every LOW and HIGH set in §1 is an exact multiple of
$0.0001 and lies in `[$0.0020, $0.1686]`. Round one observed `fee_cost` values of
$0.0019 and $0.1785 on this account, so both ends of that range are demonstrably
representable and reportable. Every band is a contiguous run of whole cents
inside 1–99, and deci-cent ticks are handled by §1's recompute rule. **Each of the
six verdicts is reachable by some legal observation at every price Joe can trade
in every band.**

### R2 — the falsifier of each declaration is reachable, at every tick including deci-cents

For any price `P` and count `C`, the two candidate raw fees are `r` and `2r` with
`r = k_LOW·C·P(1−P)`, so the two `ceil`-to-$0.0001 predictions differ by at least
**`r − $0.0001`**. **[COMPUTED]** the minimum of `r` over all registered cells and
prices is $0.001972 (D1 at 6c), so the bound gives a **minimum separation of
$0.0018 — 18 grid units — at every tick in every band, whole cent or deci-cent**,
and the enumerated minimum at whole cents is $0.0020. The sets can never
overlap, so LOW and HIGH are mutually falsifying everywhere, and neither can be
true by construction.

### R3 — no cell lands exactly on the $0.0001 grid, in either direction

This is the round-one ATP trap, avoided by construction. **[COMPUTED]** at every
whole-cent price in every registered band, **neither** `0.035·C·P(1−P)` **nor**
`0.07·C·P(1−P)` is an exact multiple of $0.0001. The excluded prices (10c for
D1/D2, 30c for D3/D4, and 15c/20c/40c which fall outside the bands) are exactly
the ones where that fails. Consequence: **every cell re-tests `ceil` against
`floor`, `half_up` and `half_even` for free**, where round one's ATP cell tested
none of them.

### R4 — no cell can saturate

Each cell has exactly two candidate classes and they are disjoint (R2), so no cell
can return a value consistent with everything. The four cells together partition
the five-member attribution family into **six outcome classes** and leave **11 of
16 vectors with an empty class** — the opposite failure mode from the ladder that
returned 984 of 1,000.

### R5 — the design's own falsifier exists

Registered explicitly because C3 found the version without D4 lacked one: for
**every** attribution in §1 there is at least one cell in this design whose
observation can refute it, and §7's coverage qualifier names which falsifier is
lost when a cell is VOID or NOT ATTEMPTED. **A PARTIAL declaration is never
reported as a declaration.**

---

## §Power — the check that comes before all of it

**Can four fills answer this question?** The question is selection among
deterministic rules with exact outputs, so the power currency is not an effect
size. It is **how much of the hypothesis space survives**.

**[COMPUTED — enumeration over all 16 LOW/HIGH vectors]**

```
                     vectors consistent
H-SERIES                   2 / 16       (LLLH, LLHH)
H-SPORT                    1 / 16       (LLLH)
H-SIZE                     1 / 16       (LHLL)
H-PRICE                    1 / 16       (HHLL)
H-NOTIONAL                 1 / 16       (LLLL)
no attribution            11 / 16
```

**Four conclusions, all of which belong in the write-up before it is written:**

1. **Every attribution except H-SERIES is pinned to a unique vector.** There is no
   outcome in which H-SPORT, H-SIZE, H-PRICE or H-NOTIONAL is declared alongside a
   rival. The design is a clean partition on four of the five.
2. **H-SERIES cannot be separated from H-SPORT, and no affordable design can.**
   H-SERIES is saturated — one free parameter per series — so it is refutable only
   *within* a series, never across one. `LLLH` declares both. **This is a
   registered residual, not a surprise, and the write-up may not report either
   name alone.**
3. **The measurement is far more likely to refute than to confirm**, in the
   structural sense that 11 of 16 vectors kill everything. That is a property of a
   sharp design, and §9 gives that branch the same destination as the others.
4. **What this cannot do is resolve a rate at a price it did not trade.** The
   round-one `k` intervals have width ~5×10⁻⁵ and ~4×10⁻⁵; the two-valued cells of
   §1 narrow them, and the narrowing is a by-product that may not be reported as a
   result. **At untested prices the fee remains uncertain at the $0.0001 level in
   both directions, and there is no permanent gate accumulating coverage** —
   Amendment A §A3 established that `backend/gate.py:636` reads `FROM fills`, that
   no production code writes that table, and that the MISMATCH branch is therefore
   unreachable. Nothing in this round changes that.

**Verdict of the power check: the design can answer the question it registers**,
at **$4.34 maximum loss**. It cannot say what Kalshi charges at every price, and
§1 does not claim to. It is **not** UNDERPOWERED. Its one stated residual is
conclusion 2.

---

## §8. The stopping rule, and the hard stop

**Exactly four orders, all on 2026-08-10, in one window opening at the commit of
this file and closing at the end of that calendar day in Joe's local time.**

- **No rollover.** A cell not placed on 2026-08-10 is **NOT ATTEMPTED**. Holding
  the date constant is the point: it holds the fee schedule version constant
  against round one, which is the confound this round is designed to exclude.
- **At most one re-attempt, and only for D1, D3 or D4**, permitted **only** when
  the cell was voided by a pre-submit-check failure or a mechanical precondition
  (P3–P6) — each checkable without looking at any fee value (P8). **D2 gets no
  re-attempt**, because a second $2.80 order breaches the dollar cap.
- **Hard cap: 5 orders, $4.11 of stake.** After the cap, or at the end of the day,
  the run is closed and reported **whichever way it came out**.
- **The positions are held to settlement.** Not sold out — a sell fill's price
  cannot be fixed in advance, so it could not be a registered cell. If Joe sells
  any position for any reason, that sell fill is **not part of this
  registration**, its fee is reported descriptively, and it may not enter any
  conjunction.

### The hard stop, in my own words

Round one registered four fills and placed six. Both extra fills were
informative — one of them, the `C = 0.27` accident, is cited in §7 as the thing
that already disfavours a per-order fee floor. **That is exactly why the breach
has to be named as a breach.** A protocol whose violations turn out useful teaches
the operator that violating it pays, and the next unregistered fill will be placed
in a market chosen after seeing how the registered ones came out. At that point
the cell is no longer a measurement; it is the analyst picking the question after
seeing the answer, which is the single failure this whole document exists to
prevent.

> **A fifth order beyond the registered four (or a sixth beyond a licensed
> re-attempt) is a PROTOCOL BREACH, not a bonus data point.** If one occurs it is
> published in the result document under the heading
> **`UNREGISTERED — NOT PART OF ANY CONJUNCTION`**, it may not enter any
> declaration, it may not be cited as support for or against any attribution, and
> **the run's verdict line must read `BREACHED`** alongside whatever it declares.
> An unregistered fill that happens to be informative is worse than one that is
> not, because it is the one that gets quoted.

---

## §9. What would falsify this, and what happens then

### The result's destination, fixed now, before the result exists

- **Every branch**, including H-NONE and including every PARTIAL, is written to
  **`docs/measurements/2026-08-1X-fee-rate-attribution-round-two-result.md`**,
  with the §S output in full.
- **Any single attribution declared FULL:** the result document, plus the
  follow-on registration named in §7's consequence table for that row. **No code
  change and no ADR retiring the `max()` hedge** — see below.
- **`LLLH` (H-SERIES / H-SPORT, not separated):** the result document, plus a
  registration for a third sport and a second baseball league.
- **H-NONE:** the result document, plus an annotation in `core/fees.py`'s
  docstring recording what was observed, plus a new registration if a sixth rule
  is to be pursued. **This branch has a destination, and it is the same
  destination as the others.**
- **PARTIAL anything:** the result document, saying which cell was lost and which
  attribution consequently has no falsifier.

**A pre-registration whose negative branch has no destination produces a negative
result that quietly never gets written.** The negative branch here is the most
likely-shaped one (11 of 16 vectors) and it is named, dated and addressed.

### What is explicitly not authorised, on any branch

**No deploy. No code change. `calculate_fee` is not touched.**
`ORDERS_ARE_DRY_RUNS` stays `True`; ADR 0018 is untouched. Round one's §2 forbids
deploying a model fitted to its fills, and that prohibition covers this round too:
**an attribution confirmed on four orders is not a fee model.** Replacing
`calculate_fee` requires (a) a rate, (b) an attribution, (c) a rounding rule, (d)
a scope, (e) coverage of the maker path, and (f) its own ADR and its own
registration. This round delivers exactly one of the six.

**And the favourable direction is the one that needs the most discipline.** §0.1
shows the plausible consequence is a break-even bar falling from 52.00% toward
~50.9% — a 1.12-point improvement against 0.38 points of assumed headroom. A bar
that moves *in your favour* is the one most worth double-registering, because it
retroactively rescues ADR 0021's refuted rows, and nothing in this repo should be
rescued by four fills.

### The consequence Joe should see before he acts

```
stake     D1   $0.06 - $0.14
          D2   $1.20 - $2.80        fees, high rate, all four:  <= $0.2105
          D3   $0.27 - $0.39
          D4   $0.27 - $0.39        MAXIMUM LOSS, four orders:     $3.93
          --------------------      MAXIMUM LOSS at the §8 cap:    $4.34
          TOTAL $1.80 - $3.72
```

These are **real positions on real games**, not paper. All four can lose in full.
The maximum loss is stated because it is the number that should govern the
decision; **no expected-value estimate is offered**, because estimating one would
require a view on the games and this design has none.

---

## §10. What this measurement cannot establish — drafted before the run

Drafted now, because caveats written afterwards are selected to be survivable.

- **It cannot separate H-SERIES from H-SPORT.** §Power conclusion 2. `LLLH`
  declares both and the write-up must name both. Separating them needs a second
  baseball league (`KXNPBGAME`, `KXLMBGAME`) and a third sport, neither of which
  is in this round.
- **It does not establish the rate at any price it did not trade.** Four prices,
  in two regions: `≤ 14c` and `27–39c`. Nothing at 15–26c — deliberately, because
  that is H-PRICE's ambiguity window — and nothing at 40c–99c except by the
  symmetry assumption of the shape, which this round does not re-test.
- **It does not establish the rate at any size it did not trade.** Two sizes, 1
  and 20. Nothing at 2–19 or above 20. If H-SIZE is declared, the boundary is
  known only to lie in `[2, 20]`.
- **It does not test the functional form.** `C·P(1−P)` is carried over from round
  one's MLB shape test as given. If the true form differs on `KXATPDOUBLES` or on
  a new MLB series, a LOW/HIGH classification here could be an artefact of the
  form, not of the rate. **This is the caveat most likely to overturn the result**
  and it is the one an after-the-fact list would omit.
- **It does not test the rounding rule as a primary claim.** R3 makes every cell
  carry rounding information, but `ceil`-to-$0.0001 is an *input* here, taken from
  round one's 20-cell census. A cell that disagrees with both LOW and HIGH is
  reported as NOVEL, which is where a broken rounding assumption would surface —
  as H-NONE, not as a rounding finding.
- **It does not cover non-monotone price rules.** H-PRICE is registered as a
  monotone threshold. A rule of the form "the high rate applies in a *band* of
  prices" fits round one and is not tested; it would appear as H-NONE.
- **It does not establish the maker rate at all.** Every cell is taker. P3 voids a
  maker fill rather than scoring it. `MAKER_COEFFICIENT = 0.0175` and
  `SPORTS_MAKER_MULTIPLIER = 0.015` remain untested everywhere in this project.
- **It says nothing about combos.** The 43 `KXMVE` records of Amendment A are out
  of scope, and `KXMVE` fees are charged to the tenth of a cent
  (`core/fees.py:227-234`), which is a different grid.
- **It says nothing about any sport other than baseball and (via one cell) tennis
  doubles.** Not NFL, not NBA, not WNBA, not soccer, not esports. Pooling across
  categories is forbidden.
- **It does not test H4 / settlement.** That is round one's Amendment A §A5/§A8
  and it is referenced, not duplicated (§6.2).
- **`n = 4`.** Four orders, one account, one venue, one calendar day. Not a sample
  of anything. **No interval appears in this design and none may be added to the
  result.**
- **It says nothing about whether an edge exists at Kalshi.** ADR 0021 §1's
  forbidden sentence is forbidden here too. Attributing the fee changes the
  *bar*; it does not create anything that clears it.

---

## §11. Assumed inputs, counted

- **B1 [ASSUMED].** Round one's `(ceil, $0.0001)` pair and the two `k` intervals
  are correct as licensed. **Detector:** a NOVEL classification on any cell.
- **B2 [ASSUMED].** The fee shape is `C·P(1−P)` on `KXATPDOUBLES` and on whatever
  series D3 lands in, as it is on `KXMLBGAME`. **Detector:** none available in
  this round. Named in §10 as the caveat most likely to overturn the result.
- **B3 [ASSUMED].** The fee is charged at fill time, once per order, and does not
  change afterwards. **Detector:** P7.
- **B4 [ASSUMED].** Kalshi's fee schedule did not change between round one's fills
  and round two's, on the same calendar day. **Detector:** none; mitigated by §8's
  no-rollover rule, which is the entire reason for it.
- **B5 [ASSUMED].** An order Joe places by hand in the app appears on
  `/portfolio/fills` for the account the API key addresses. **Detector:** the fill
  count must equal the order count; a mismatch is a STOP THE LINE naming the
  harness, not the exchange.

**Count of assumed inputs: 5.**

---

## §S. Required output of the run, in this order

1. Preconditions P1–P8, each with its yes/no and its evidence.
2. Reachability guards R1–R5, printed **before** any verdict.
3. **The per-cell table**: cell, ticker, series prefix, side, observed price,
   `count`, `is_taker`, notional, `fee_observed`, registered LOW set, registered
   HIGH set, classification (LOW / HIGH / NOVEL), VOID or NOT ATTEMPTED with
   reason, and the settlement `fee_cost` once available. **Every cell appears,
   including voided ones, with its observed fee.**
4. The five-row attribution table: for each of H-SERIES, H-SPORT, H-SIZE,
   H-PRICE, H-NOTIONAL — its prediction per cell, and DECLARED or REFUTED with the
   cell that refuted it named.
5. The verdict line, including `BREACHED` if §8 was breached, the substitution
   flag if D4′ or the split-market fallback was used, and
   `H-SERIES / H-SPORT — NOT SEPARATED BY THIS DESIGN` verbatim where it applies.
6. The coverage qualifier: FULL or PARTIAL, and for PARTIAL, which attribution
   lost its falsifier.
7. The in-app displayed fee for each order beside the API value, as a cross-check.
   A disagreement is a STOP THE LINE about the instrument.
8. The D2 balance-before/after reading (§6.1), or the statement that it was void
   and why.
9. The narrowed `k` intervals as a **by-product, labelled as such**, with the
   sentence that they are not a result of this round.
10. Total stake, total fees paid, and total realised P&L on the four positions —
    reported for honesty, and **explicitly not evidence of anything** about edge,
    at `n = 4`.
11. The §10 list, reproduced unedited.

---

## §V. Verdict at registration

> **READY.** Every section is fixed. No section was left open on the grounds that
> we would see what the data looks like.
>
> Four cells, four bands, three series constraints, all predictions computed to
> $0.0001 and written above before any fill exists — including the two-valued sets
> that a point prediction would have got wrong. LOW and HIGH are disjoint by at
> least 19 grid units at every tick. No cell lands on the $0.0001 grid, so round
> one's ATP trap is avoided by construction. Eleven of sixteen outcome vectors
> kill every attribution, and that branch has the same destination as the others.
> The stopping rule is a count, a dollar cap and a calendar day. The one residual
> — H-SERIES versus H-SPORT — is registered as unresolvable by this design rather
> than left to be discovered.
>
> **Maximum loss: $3.93 for the four orders, $4.34 at the §8 cap.**

---

## Registration record

| Field | Value |
|---|---|
| Registered | 2026-08-10 (UTC) |
| Registered by | `pre-registrar`, on behalf of Joe |
| Round-two fills at registration time | **0** |
| Cells | 4 |
| Sizes | 1, 20 |
| Bands | 6–14c (excl. 10c) × 2; 27–39c (excl. 30c) × 2 |
| Series | `KXMLBGAME` × 2, non-`KXMLBGAME` `KXMLB*` × 1, `KXATPDOUBLES` × 1 |
| Attributions under test | 5 + H-NONE |
| Mirror | **Forbidden** for D1/D2 (§C5); permitted for D3/D4 |
| Max stake | $3.72 (four orders) / $4.11 (§8 cap) |
| Max loss incl. fees | $3.93 / $4.34 |
| Deploy required | **None** |
| Code change authorised | **None.** `calculate_fee` untouched; `ORDERS_ARE_DRY_RUNS` stays `True` |
| Amendments | none |

---

## Appendix — the placement card

Four orders. Nothing else. Read the four-point check before every submit.

> **CHECK, EVERY ORDER:** Limit order · shares field reads exactly the number
> below · limit price = displayed ask · estimated cost = shares × ask.

**1 — `KXMLBGAME`, 1 contract, ask 6c–14c (skip 10c).**
Scan MLB game markets top to bottom in the app's default order. Take the first
one with an ask in the band and **at least 21 showing at that ask**. Buy **1**.
*Prefer 13c or below.*

**2 — same market, 60 seconds later, 20 contracts, same ask.**
If the ask moved out of band, use the next qualifying market instead.

**3 — `KXMLBTOTAL` (else `KXMLBSPREAD`, else any other `KXMLB…` that is not
`KXMLBGAME`), 1 contract, ask 27c–39c (skip 30c).**

**4 — `KXATPDOUBLES`, 1 contract, ask 27c–39c (skip 30c).**

**Record for each:** ticker, ask, size showing at the ask, shares, estimated cost,
time. **For order 2 only:** the account balance immediately before and immediately
after, with every digit shown.

**Then stop.** Four orders. A fifth is a protocol breach, not a bonus.
