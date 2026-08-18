# Pre-registration — the combo fill fee look

**Date:** 2026-08-18
**Status:** Registered. **No `fee_cost`, price, or count value has been read.
No statistic below has been computed.**
**Question it answers:** what fee schedule do Kalshi's combination markets
follow? ADR 0012 §5 item 2 records that model as *unverified*, and
`backend/core/fees.py`'s "what this does NOT establish" item 3 ends with the
words *"or on combos"*. These 8 fills are the first combo fees this project
has ever observed.
**Result destination, fixed now and written whichever way it comes out:**
`docs/measurements/2026-08-18-combo-fill-fee-look-result.md`.
**Registered consequence to code: none.** This document declares a
consistency verdict. It does not authorise editing `backend/core/fees.py`,
does not authorise changing `TAKER_COEFFICIENT`, `FEE_GRID_DOLLARS` or
`FEE_MATCH_TOLERANCE_DOLLARS`, does not re-derive the break-even bar, does not
touch the gate, and does not touch `ORDERS_ARE_DRY_RUNS`. Each needs its own
ADR.

**It also does not re-open the 25-fill look.** That look is spent
(`docs/measurements/2026-08-18-hand-fill-fee-calibration-result.md`, one look,
as registered). The 25 single-market rows sitting in the same capture file are
**OUT OF POPULATION** here (§3). No statistic in this document is computed over
them, they may not be pooled with combo rows, and the fact that the capture has
been re-taken since is not a licence to re-score them.

---

## §0. Declared contaminations, in full, before anything else

Everything I was told before writing this, so a later skeptic can weigh it.

| known | source | what it puts at risk |
|---|---|---|
| Joe bought **8 KXMVECROSSCATEGORY fills for ~$3 total** on 2026-08-18, for fun | `tasks/NEXT.md` 11:10Z entry | Nothing tested here. Total stake bounds `C·P` loosely and is not an input to any claim. **P&L is out of population entirely** (§11) |
| **"some on a sub-deci-cent grid"** | `tasks/NEXT.md` 11:10Z entry | **§6 directly.** This is the largest contamination in the document and it makes one branch near-determined before the look — see §6.1, which says so rather than pretending to discover it |
| Single-game fills pin `k` to two disjoint clusters, `(0.0349691, 0.0350076]` on `KXMLB*` and `(0.0699931, 0.0700000]` elsewhere | 2026-08-14 round-three result; 2026-08-18 result | §4.3's placement of any combo interval. Mitigated: placement is **descriptive**, never a test (§4.3), because combos are a new population |
| `calculate_fee` overcharged 10 of 25 single-market fills (baseball half-rate) and undercharged **none** | 2026-08-18 result, C1/C1b | §7's C1 branch. The direction of C1 is fixed here anyway by `fees.py`'s standing choice never to undercharge |
| The `/portfolio/fills` endpoint **rolls** — history is dropped | Amendment A1; NEXT.md | §9. The population can only shrink. This is why there is exactly one look and why a re-capture cannot restore a lost row |

**The envelope, read before writing this and recorded as required.** The
capture wrapper `data/captures/portfolio_fills.json` reports
`captured_at = 2026-08-18T09:57:58Z`, `endpoint = /portfolio/fills`,
`record_count = 33`, `envelope_keys = ['cursor', 'fills']`,
`fee_shaped_keys = ['fee_cost']`, and these 17 field names:

```
action  book_side  count_fp  created_time  fee_cost  fill_id  is_taker
market_ticker  no_price_dollars  order_id  outcome_side  side
subaccount_number  ticker  trade_id  ts  yes_price_dollars
```

Row counts by ticker prefix: **8** begin `KXMVECROSSCATEGORY`, **0** begin any
other `KXMVE` prefix, 25 are single-market rows. **No `fee_cost`, price,
count, timestamp, ticker string, or order id value was read**, and the
ticker-prefix counts were produced by a boolean `startswith` that printed only
totals. The combo ticker grammar used in §4.5 comes from the committed fixture
`tests/fixtures/combo_priced_markets.json`, not from Joe's rows.

---

## §1. The power check, which comes first

### 1.1 What this design can and cannot resolve

The estimand is a **deterministic charge on a grid**, not a mean. There is no
sampling error to be underpowered against and **no `n` at which a p-value would
become appropriate** — none is computed anywhere (§4).

**Refutation is fully powered; confirmation is not available at all.** One row
whose charge differs from a candidate's prediction kills that candidate outright.
No number of matching rows establishes that a candidate *is* the combo schedule,
because 8 fills from one account in one sitting on one collection family cannot
exclude a promotional rate, a per-market tier, a size or price region not
observed, or another `KXMVE` family. The verdict vocabulary in §7 is therefore
`REFUTED` / `NOT REFUTED` / `NOT SEPARATED` / `NOT TESTABLE` — never
`CONFIRMED`, never `VERIFIED`.

### 1.2 The `n >= 5 per side` rule binds, and it forbids most of statistics here

CLAUDE.md: *"Require >= 5 expected outcomes on each side before a normal
approximation is allowed to speak."* With 8 fills and an unknown, possibly much
smaller, number of independent orders (§3.2), **no cell in this design reaches
5 on either side.**

**Forbidden in the result document, in every branch:** any proportion or match
*rate*, any pooled fee rate, any standard error, any confidence interval on a
proportion, any p-value, any normal approximation, any "x of 8 is significant"
phrasing, and any comparison of two match counts as though the difference were
estimated. **Permitted:** exact per-row comparisons, per-row admissible-`k`
intervals, the observed-grid GCD, and counts.

**This is a consistency check, not an estimation.** The sentence is registered
here so it can be checked verbatim against the write-up.

### 1.3 Separation, conditional on values not yet seen

Inverting `fee = ceil_g(k · D)` with `D = C · P · (1 - P)` gives an admissible
interval of width `g / D`. At the deployed grid `g = 1e-4`:

| condition on `D` | consequence |
|---|---|
| `D > 0.002857` (`= g / 0.035`) | the interval is narrower than the gap between 0.035 and 0.070 — **the row separates them** |
| `D <= 0.002857` | **DEGENERATE**: the row admits both. Recorded, never rescued |
| `D <= 0.001429` (`= g / 0.070`) | both candidates round to the same single grid unit — the row separates **nothing** |

A finer grid (§6) shrinks `g` and therefore *improves* separation; a coarser one
destroys it. Since ~$3 spread over 8 fills implies small stakes, **small `D` is
the live risk to this design and it is registered as a possible NOT SEPARATED
outcome before the look, not discovered as a disappointment after it.**

### 1.4 One family of candidates is UNDERPOWERED BY CONSTRUCTION, and it is the
one ADR 0012 §5 actually names

ADR 0012 §5 item 2 poses **per-leg versus per-order**. A per-leg schedule
`sum over legs of ceil(k · C · P_leg · (1 - P_leg))` requires **each leg's price
at the moment of the fill**. Those prices are not in `/portfolio/fills`, are not
derivable from the combo ticker (which is `SERIES-<collection hash>-<combo
hash>`, opaque — verified against the committed fixture), and are **not
recoverable later**: a market read today returns today's price, not the fill's.

**Registered now: the leg-price form (M11, §4.4) returns NOT TESTABLE, in every
branch, and no substitute leg price may be constructed** — not the current
book, not a mid, not a marginal implied from anything. The only per-leg
candidates this design can score are the leg-*count* multiples M9/M10, and only
if the §4.5 enrichment succeeds.

### 1.5 Durability — UNDERPOWERED BY CONSTRUCTION, and no branch escapes it

All 8 fills were placed by one account in one sitting on **one day**. The
single-game record already shows Kalshi revising the sports schedule at least
once in six months (`fees.py`: whole-cent 2025-11-27..2026-02-09, `1e-4` from
2026-08-10). **Whatever this analysis returns, it establishes nothing about
what combos are charged tomorrow, and the result document must repeat that
sentence.**

### 1.6 Verdict of the power check

**Adequately powered for exact refutation of the registered candidates,
conditional on `D` clearing §1.3's threshold; powered for nothing else.**
The per-leg question ADR 0012 §5 names is NOT TESTABLE. Durability, maker,
sells, attribute attribution and every other `KXMVE` family are out of reach and
are listed in §11 before the run.

---

## §2. The claims, each stated so it can come back false

Direction stated on every one. Nothing here is two-sided-then-reported-one-sided.
Every claim is scoped to **"every combo fill in this capture"** — never *always*,
*never*, *by construction*, or *Kalshi*.

- **C1 (safety, one-sided).** On every combo row, the charge Kalshi applied is
  **less than or equal to** what the deployed model returns:
  `fee_cost <= calculate_fee(P, C) + 1e-9`. *Falsified by one row in the other
  direction.* The direction is fixed by `fees.py`'s standing choice never to
  undercharge; an undercharge is the one direction that corrupts every EV number
  the tool prints, so it is **STOP THE LINE** (§7).
- **C2 (the deployed model, exact).** On every combo row,
  `|fee_cost - calculate_fee(P, C)| <= 1e-9`. *Falsified by one row.* This is
  the claim `fee_model_verified` would test if a combo fill ever reached it, and
  it is stated separately from C1 because they are different claims.
- **C3 (grid).** Every combo `fee_cost` is an exact multiple of
  `FEE_GRID_DOLLARS = 0.0001`. *Falsified by one row that is not.* One-sided:
  the interesting direction is a **finer** grid. See §6.1 — this claim is
  contaminated and near-determined.
- **C4 (schedule identification).** At least one of the frozen candidates
  M1–M10 (§4.4) predicts every combo row's charge to within `1e-9`. *Falsified
  by a capture in which every candidate mismatches at least one row* — the
  registered fourth answer, **"none of the registered candidates"**.
- **C5 (per-order versus per-contract, one-sided where it can be).** If M1–M6
  (per-order) all mismatch while a per-contract or per-leg-count form matches
  every row, the per-order form is **REFUTED for combos**. The converse is
  registered as weaker: a per-order match does not refute per-leg, because §1.4
  cannot score the leg-price form.

---

## §3. The population, the unit, and the exclusions

### 3.1 Population

Exactly the rows of `data/captures/portfolio_fills.json` (wrapper
`record_count = 33`, `captured_at = 2026-08-18T09:57:58Z`) whose `ticker`
begins **`KXMVECROSSCATEGORY`**, as that file stands at the moment of the first
computation. **Expected: 8. Guard:** if the count is not 8, the analysis
**stops before any fee value is opened** and records the discrepancy at the top
of the result document. The rule stays as written; the count checks the rule, it
does not define the set.

The prefix rule is chosen because it is a property of the product, fixed before
the look, and independent of the charge. The file is gitignored and stays so.

**Out of population, named so the boundary cannot move later:** the 25
single-market rows in the same file; every settlement record; the estimate log
and the whole calibration study (combos are excluded from it structurally, and
nothing here touches it — NEXT.md's standing "no interim aggregate over the
estimate log" binds); every market not filled; every other `KXMVE` family.

### 3.2 Unit of observation, and the clustering variable

**The unit is one ORDER, keyed by `order_id`**, not one fill. Model A rounds on
the whole order, so two fills of one order are one application of the schedule
and scoring them as two independent rows would inflate `n` exactly the way
CLAUDE.md's clustering rule exists to prevent. Rows sharing an `order_id` are
grouped and the group's summed `fee_cost` is compared against the model applied
to the group's summed count at its (single) price; **if a group contains two
prices, that group is reported as MIXED-PRICE and excluded from the exact-match
tally, counted and listed** — the rule references only `yes_price_dollars` /
`no_price_dollars`, never `fee_cost`.

**The distinct `order_id` count is printed before any fee value, and it is the
document's `n`.** Eight fills may be as few as one order. If it is one, the
result document's headline must read *"one order"* and every claim inherits
that.

**Independence, stated honestly.** Two orders are independent *for this
measurement* if the venue applied the schedule to each separately. There is no
outcome shock here, so there is no ADR 0029-style game clustering. What is
**not** independent is the evidence's coverage: one account, one sitting, one
day, one collection family, one person's choice of combinations. §11 records
that and no branch escapes it.

### 3.3 Exclusions, all independent of the charge

1. **`is_taker = false`** — maker rows are scored against the maker candidates
   (§4.4), never against taker ones, because the maker coefficient is a
   different number. Counted either way.
2. **`action = sell`** — **STOP AND REPORT**, not a row to parse on the fly. No
   sell has ever been captured on this account and the exit-fee wire shape is
   unverified; on an enter-only product (ADR 0012 addendum: no YES bid on 40/40
   combo books ever read) a sell row would itself be the finding.
3. **Unreadable price or count** — if `yes_price_dollars` and
   `no_price_dollars` are both absent, empty, or unparseable as an exact
   `Decimal` on a row, that row's prediction is **NOT COMPUTABLE**. It is
   counted and listed. **No substitute is constructed** — not `last_price`, not
   a mid, not the complement of the other side. Unreadable resolves to `None`,
   never to a number that looks fine.
4. **DEGENERATE rows** (`g / D >= 0.035`, §1.3) are excluded from the
   admissible-`k` **clustering only**, counted and listed. They are **not**
   excluded from the exact-match tally, where degeneracy is irrelevant because
   the comparison is exact. The rule references only `C` and `P`.

**Thin-sample rider, registered in advance.** If activating exclusion 1, 3 or 4
would leave **fewer than 3 orders** in the tally it governs, that exclusion is
**recorded but NOT activated**, and the affected rows are reported in place with
their label attached. This mirrors the standing precedent: an exclusion rule
that empties the population converts a thin sample into a silent one. The
direction is conservative — retaining a blunt or excluded row can only widen an
interval or add a mismatch, never manufacture a match.

**No other exclusion is available.** In particular, no row is excluded for being
an unplanned or "for fun" bet. ADR 0028's standing rule binds: *"excluding an
observation for being unplanned is exactly the freedom this document family
removes."*

---

## §4. The statistic, named as an estimator

**No estimator of a mean appears anywhere.** The estimand is a deterministic
charge. Adding a p-value, a rate, or a standard error later is forbidden (§1.2).

### 4.1 The price actually paid

`P` is taken from the side actually held: `yes_price_dollars` when the row is a
YES, `no_price_dollars` when it is a NO, resolved from `outcome_side` / `side` /
`book_side` by a rule fixed here — `outcome_side` first, `side` if it is absent,
and **STOP AND REPORT** if the two disagree. Parsed with
`core.prices.dollars_to_tenths` on the dollar **string**: never `float()`, never
a mid, never `last_price`, never the complement of the other side.

`count_fp` is read as an exact `Decimal` from its string; fractional counts are
real positions on this account and are accepted exactly, per `_exact_count`.

**Guard:** if `yes_price_dollars + no_price_dollars != $1.00` on a row, that is
recorded in the result and the held side's own field is used regardless. The fee
form is symmetric in `P` and `1 - P`, so a side error cannot change any
prediction in C1–C5; it is recorded because on a combo the complement is not
guaranteed to be quoted at all.

### 4.2 Per-order admissible `k`, as an interval, never a point

From `fee = g · ceil(k · D / g)` with `D = C · P · (1 - P)`:

```
k  in  ( (fee_cost - g) / D ,  fee_cost / D ]
```

half-open, matching `scripts/reconcile_observed_fees.py`. Computed at
`g = 1e-4` and, if §6 infers a finer grid, again at that grid — **both printed,
neither promotable over the other after the fact.**

**Point estimates `fee_cost / D` are forbidden as the classifying quantity and
forbidden as an input to any average**, because averaging across rows of
different `D` weights the blunt ones as if they were sharp. The one exception,
registered here: under the *unrounded* candidates M5/M6 the ratio `fee_cost / D`
**is** the model's exact prediction, so it is reported as a point there and
labelled as such.

Sharpness classes, fixed now: **SHARP** if `g / D <= 0.0035`, **BLUNT**
otherwise, **DEGENERATE** if `>= 0.035`.

### 4.3 Placement against the single-game clusters is DESCRIPTIVE, not a test

Any combo interval is reported beside the known `(0.0349691, 0.0350076]` and
`(0.0699931, 0.0700000]` clusters **for orientation only**. Combos are a new
population; a combo interval overlapping the baseball cluster does not
reproduce it, does not extend it, and may not be pooled with it. Round three's
prohibition on pooling across categories is carried forward and binds here.

### 4.4 The frozen candidate set

**Frozen at eleven. No model may be added after the first fee value is read.**
`C` is the order's summed count, `P` the held side's price, `g` the grid,
`L` the leg count from §4.5.

| id | form | notes |
|---|---|---|
| **M1** | `ceil_{1e-4}(0.070 · C · P · (1-P))` | the **deployed** `_model_a` / `calculate_fee`; C1 and C2 are scored against this one |
| **M2** | `ceil_{1e-4}(0.035 · C · P · (1-P))` | the measured baseball rate |
| **M3** | `ceil_{1e-2}(0.070 · C · P · (1-P))` | the pre-July-2026 whole-cent grid |
| **M4** | `ceil_{1e-2}(0.035 · C · P · (1-P))` | |
| **M5** | `0.070 · C · P · (1-P)` **exact, unrounded** | registered *because* §6.1 makes a finer-than-`1e-4` charge likely; a candidate registered in advance, not fitted after |
| **M6** | `0.035 · C · P · (1-P)` **exact, unrounded** | |
| **M7** | `C · round_half_up_{1e-2}(0.06 · P · (1-P))` | `_model_b` as coded, a refuted control on single markets; a control's job is to fail visibly |
| **M8** | `C · ceil_{1e-4}(0.070 · P · (1-P))` | per-**contract** rounding at the deployed coefficient |
| **M9** | `L · ceil_{1e-4}(0.070 · C · P · (1-P))` | per-**leg** multiple of the combo-price charge; requires §4.5 |
| **M10** | `L · ceil_{1e-4}(0.035 · C · P · (1-P))` | requires §4.5 |
| **M11** | `sum over legs of ceil_{1e-4}(k · C · P_leg · (1-P_leg))` | **NOT TESTABLE in every branch** (§1.4). Reported as NOT TESTABLE, with the reason, so its absence is visible |

**Maker variants**, scored only on rows with `is_taker = false`: M1m/M2m at
`k = 0.0175` and `0.00875` (one quarter of each taker coefficient, per
`MAKER_COEFFICIENT`). If no maker row exists, they are reported NOT TESTABLE
and no taker row may be substituted.

All arithmetic in exact `Decimal`. No binary floats anywhere:
`0.07 * 20 * 0.15 * 0.85` evaluates to `0.17850000000000002` in float and ceils
to a false residual that reads as a novel schedule. That has already happened
once in this project.

### 4.5 The leg-count enrichment — bounded, optional, and before the fees

M9/M10 need `L`. It is not in the capture and not in the ticker. The **only**
permitted way to obtain it:

- a **read-only** `GET /markets/{ticker}` for each distinct combo ticker already
  present in the capture (**at most 8 requests**), reading `mve_selected_legs`
  and recording **its length only**;
- **never** `POST .../lookup`, which creates a market on the exchange;
- performed **before any `fee_cost` value is opened**, or not at all;
- **every price, book, volume or open-interest field returned is OUT OF
  POPULATION** and may not enter any claim — those are post-fill quotes and
  §1.4 forbids reconstructing a fill-time leg price from them;
- a failed or 404 request leaves `L = None` for that row; **`L` is never
  imputed, never defaulted to 2, never inferred from a title string count if
  `mve_selected_legs` is absent**;
- if the enrichment is skipped for any reason, M9/M10 are reported **NOT
  TESTABLE** and that is the end of it.

---

## §5. The cuts, fixed here

1. **Product**: `KXMVECROSSCATEGORY` only. There is no second family in the
   capture, so there is no product cut to make; a family cut is registered as
   unavailable rather than discovered later.
2. **Order grouping**, per §3.2.
3. **Taker / maker** and **buy / sell**, per §3.3.
4. **Sharpness** SHARP / BLUNT / DEGENERATE, per §4.2 — for the interval view
   only.
5. **Leg count `L`**, if and only if §4.5 succeeds, and used only as M9/M10's
   input — **not** as a cut to split the rows into "few-leg" and "many-leg"
   groups. Splitting 8 rows by leg count after seeing the fees is the exact
   freedom this document removes.

**No other cut.** In particular: no cut on price band, size band, notional,
time-within-the-sitting, collection, or which combination it was. With eight
rows, any cut produces cells of one or two and every one of them will contain a
tidy story.

**Printed before any fee value, in this order** (CLAUDE.md, *read `n` before the
effect size*): total rows matched by the prefix rule; **distinct `order_id`
count**; rows per order; rows per taker/maker; rows per buy/sell; rows NOT
COMPUTABLE; rows per sharpness class; and `L` per order if §4.5 ran.

---

## §6. Grid granularity — how it is assessed, fixed in advance

The observed grid is a claim about `FEE_GRID_DOLLARS`'s validity **for combos**,
and it is the one thing here with a live consequence for code (§12).

### 6.1 The contamination, stated plainly

I have been told the 8 rows include **"some on a sub-deci-cent grid"**. If that
is what the file says, then **C3 is refuted before the look**, and — this is the
part worth registering, because it is a logical entailment and not a discovery —
**M1, M2, M3, M4, M8, M9 and M10 are all refuted on any such row automatically**,
because a model that rounds *up onto* a `1e-4` (or `1e-2`) grid cannot produce a
charge that is not a multiple of that grid. That leaves M5, M6, M7 and "none of
the registered candidates" as the live answers. **This fork is near-determined
before the look and the result document must say so rather than present it as a
finding.** What is *not* determined, and is the actual question: which
coefficient, and whether any grid at all is in force.

### 6.2 The grid statistics, all descriptive

Computed on exact `Decimal` parsed from the wire **string** (a float
round-trip manufactures and destroys decimal places, which is the whole
quantity here):

1. **Decimal places** of each `fee_cost` as written, and the maximum.
2. **`gcd` of the observed charges**, computed exactly over the integers
   obtained by scaling every `fee_cost` by `10^m` where `m` is the maximum
   decimal place count observed.
3. The verdict, one-sided and registered now: every charge is a multiple of the
   true grid, therefore the true grid **divides** the observed `gcd`, therefore
   the honest sentence is **"the combo grid is no coarser than `<gcd>` on these
   rows"**. It may **not** be written as "the combo grid is `<gcd>`", because a
   finer grid is entirely consistent with eight observations — with one order it
   is consistent with anything.
4. If the maximum decimal place count exceeds 4, the result states:
   **`FEE_GRID_DOLLARS = 0.0001` does not hold for these combo rows**, and that
   sentence is the finding, with the count of rows involved beside it.

**No grid is fitted and then tested on the same rows.** A candidate ceil-to-`g*`
model at the inferred `g*` may be *reported* for orientation and is explicitly
labelled **IN-SAMPLE, NOT A TEST**. It cannot become the answer to C4.

---

## §7. The decision rule, verbatim

```
GUARD  combo row count != 8
       -> STOP before any fee value is opened. Record the discrepancy at the
          top of the result document. Do not proceed on the rows that are
          there.
GUARD  any row with action = sell
       -> STOP AND REPORT. The exit-fee wire shape is unverified and an
          enter-only product producing a sell is itself the finding.

n      The distinct order_id count is printed FIRST and is this document's n.
       If n_orders < 3, every verdict below is additionally stamped
       THIN: n_orders = <k>, and no verdict may be quoted without it.

C1     any row where fee_cost > calculate_fee(P, C) + 1e-9
       -> STOP THE LINE. The deployed model UNDERCHARGES on combos, which is
          the one direction fees.py has never chosen and the direction that
          overstates every edge_after_fees_tenths the tool prints. Reported at
          the top of the result document, above every other finding.
C1     no such row
       -> NOT REFUTED. This is a safety check, not evidence for the model.

C2     every combo order matches calculate_fee within 1e-9
       -> DEPLOYED MODEL NOT REFUTED ON COMBOS. May NOT be written as
          "verified", "confirmed", or "the combo fee model is settled";
          ADR 0012 section 5 stays unverified and FEE_MATCH_TOLERANCE's
          recorded combo limitation stays open.
C2     any combo order differs by more than 1e-9
       -> DEPLOYED MODEL MISMATCHED ON COMBOS. Report the per-row ratio
          fee_cost / calculate_fee. No code change is authorised by this
          document.

C3     every fee_cost is an exact multiple of 0.0001
       -> GRID NOT REFUTED on these rows.
C3     any fee_cost is not
       -> FEE_GRID_DOLLARS DOES NOT HOLD FOR COMBOS. Report the row count and
          the maximum decimal places. Per section 6.1 this also refutes
          M1, M2, M3, M4, M8, M9 and M10 on those rows as an entailment, and
          the result must label it an entailment, not seven findings.

C4     exactly one of M1..M10 predicts every scorable order within 1e-9
       -> that candidate is CONSISTENT WITH EVERY COMBO ORDER IN THIS
          CAPTURE. Not "the combo fee schedule". Not "confirmed".
C4     more than one candidate predicts every scorable order
       -> NOT SEPARATED BY THIS DESIGN. List all survivors and the reason
          (typically D below section 1.3's threshold). Do not choose among
          them by plausibility, by agreement with single-game rows, or by
          which is more convenient.
C4     no candidate predicts every scorable order
       -> NONE OF THE REGISTERED CANDIDATES. Report the per-row ratio
          fee_cost / D and, if those ratios agree across orders to within
          1e-6, report the common ratio as NOVEL COEFFICIENT, UNEXPLAINED.
          NO TWELFTH MODEL IS FITTED HERE. A novel form requires a fresh
          registration and its own look.
C4     some rows match a candidate and others do not
       -> MIXED. Report per row. A candidate may NOT be promoted by dropping
          the rows that break it, and no post-hoc cut (section 5) may be
          introduced to separate them.

C5     M1..M6 all mismatch AND (M7 or M8 or M9 or M10) matches every order
       -> THE PER-ORDER FORM IS REFUTED FOR COMBOS ON THESE ROWS.
C5     a per-order candidate matches
       -> PER-LEG NOT REFUTED. Registered as weaker in advance: M11, the form
          ADR 0012 section 5 actually names, is NOT TESTABLE (section 1.4), so
          a per-order match cannot exclude it.

M11    NOT TESTABLE, in every branch. Fill-time leg prices are unrecorded and
       unrecoverable. No substitute leg price may be constructed.

MAKER  zero maker rows -> M1m/M2m NOT TESTABLE. Taker rows may not be
       substituted.

FORBIDDEN IN EVERY BRANCH:
  - any proportion, rate, standard error, confidence interval, p-value or
    normal approximation over these rows (section 1.2);
  - pooling combo rows with the 25 single-market rows, or re-scoring those 25
    for any purpose;
  - proposing that combo fills count toward _fee_model_verified. The 2026-08-18
    look already answered that question FORBIDDEN for single-market hand fills
    while C1b mismatches; a combo row is a weaker case, not a stronger one;
  - widening FEE_MATCH_TOLERANCE_DOLLARS, or proposing a one-sided tolerance.
    Both are gate loosenings wearing a bug fix's clothes;
  - any statement about whether combos are worth betting.

DURABILITY  No branch licenses changing TAKER_COEFFICIENT, MAKER_COEFFICIENT,
       FEE_GRID_DOLLARS or any coefficient in fees.py. One account, one
       sitting, one day, one collection family.
```

---

## §8. Multiplicity, counted now

Pre-declared comparisons: **up to 8 orders x 11 candidates = 88**, plus 8 C1
comparisons, plus 8 C3 grid checks, plus one `gcd`. If the rows collapse to
fewer orders, the count falls with them and the realised count is printed.

**The chance-of-a-false-finding frame does not apply and I will not manufacture
one.** These are exact comparisons against exact grids; noise does not produce a
spurious match, and §1.2 forbids the statistics that would need a correction.

**The real multiplicity risk here is model search**, and it is controlled by
three things fixed above: the candidate set is frozen at eleven (§4.4), no
twelfth may be added after the file is opened (§7), and the inferred-grid model
is labelled IN-SAMPLE and barred from answering C4 (§6.2). The second risk is a
post-hoc cut splitting 8 rows until a candidate survives on a subset; §5 bars
every cut not named there.

**This record will be looked at more than once as it grows.** More combo fills
may be bought; `/portfolio/fills` will return them. **This is one look at one
frozen capture** (§9). A future look at a larger combo capture is a **new
registration**, not a re-read of this one — precisely because a threshold
re-evaluated against an accumulating record crosses eventually with probability
1 (measured in this project at 13.7%, a floor).

---

## §9. The stopping rule

**One look at the capture as it stands: 33 rows, 8 of them combo.** No re-poll
for more rows before, during, or after the computation. No second pass with a
different cut. No re-run when more combo fills are bought.

The endpoint **rolls**, so the population can only shrink: if the file cannot be
read at all, the capture script may be re-run **once, before the first
computation**, and the delivered combo row count is recorded. Any combo row in
that re-capture beyond the registered 8 is reported **OUT OF POPULATION** with
its count and is excluded from every claim in §2. Any of the 8 that is missing
is reported as **LOST TO ROLL** and is not substituted. After the first
computation the population is frozen absolutely.

**The named temptations, written down so they are recognisable in the moment:**
buying one more combo because the sample is thin (that is a new registration,
and a new bet placed to move a measurement is a stopping rule chosen on the
data); adding a twelfth model because one row does not fit; splitting the rows
by leg count after seeing the fees; quoting a match count as a rate; re-reading
the 25 single-market rows "just to check".

---

## §10. Producer, provenance and privacy

Every figure in the result document is re-derived by a **committed, re-runnable**
script — `scripts/analyse_combo_fill_fees.py` — reading only the capture file
(plus, if §4.5 runs, the leg counts, which are written to a small committed JSON
beside the result so the run is reproducible without the network). No database,
no credential, no order path. A hand-typed table with no producer is a
hand-constructed payload wearing a measurement's name.

The capture stays gitignored. The result document contains **no** `fill_id`,
`order_id`, `trade_id`, `subaccount_number`, or full combo ticker — the ticker's
collection and combination hashes identify Joe's specific positions. Rows are
identified by an index (`row 1`..`row 8`) and the series prefix only. Leg counts,
counts, prices and fees only. `kalshi-cockpit` publishes on push.

**The module docstring of the producer states what it does not establish**, per
CLAUDE.md, and §11 is its source text.

---

## §11. What this cannot establish, drafted before it is run

- **Durability.** One account, one sitting, one day. A promotional, launch, or
  temporary combo rate is not excluded and this window cannot exclude it. The
  sports schedule demonstrably changed at least once in the preceding six
  months, and the word throughout is *these fills*, not *Kalshi*.
- **Maker fees on combos.** If no maker row exists, `MAKER_COEFFICIENT` and the
  50.44% maker bar are untouched; if one exists, one row establishes nothing
  about a coefficient either.
- **Sells, exits and round trips.** No combo sell has ever been captured, and
  ADR 0012's addendum records **no YES bid on 40/40 combo books ever read** —
  the product observed is enter-only. This look gives the exit fee no wire
  shape and does not change the enter-only finding in either direction.
- **The per-leg schedule ADR 0012 §5 names.** M11 is NOT TESTABLE: fill-time leg
  prices are unrecorded and unrecoverable. Even a clean M9/M10 result would
  concern a leg-*count* multiple, not a leg-price sum.
- **Which attribute carries any rate split.** Product (combo vs single),
  category mix (cross-category legs span sports and non-sports), series, and a
  per-market tier are **all confounded in these 8 rows simultaneously** — worse
  than in the single-game record, not better. A combo `k` differing from 0.070
  identifies nothing about *why*.
- **The true grid below the observed `gcd`.** §6.2 gives a one-sided bound only.
- **Any other `KXMVE` family.** `SINGLEGAME`, `MULTIGAMEEXTENDED` and
  `NFLSINGLEGAME` have zero observations here, and the 2026-08-06 capture's
  calendar caveat (no NBA, no NFL in season) is untouched.
- **Anything off the observed grid** — prices, sizes, leg counts, in-play
  status, and collections not present.
- **Anything about edge, EV, CLV, correlation, P&L, or whether combos are worth
  betting.** ADR 0038 closed the hunt and nothing here reopens it; a fee
  schedule is a cost, and *a cost advantage multiplies an edge, it cannot create
  one*. The ~$3 and its outcome are out of population and do not appear in the
  result document.
- **The calibration study.** Combos are excluded from it structurally. No
  estimate-log aggregate is computed, in any branch.
- **That the venue charges what it charged this account.** An account-level or
  promotional rate is not distinguishable from a venue rate by one account's
  record, still less by one sitting.

---

## §12. What is built if it clears, what is killed if it does not

| outcome | consequence |
|---|---|
| **C1 refuted (undercharge)** | The largest finding available here. Every combo EV the tool could print is optimistic; an ADR follows immediately and `fees.py` gains a combo branch. Nobody is hoping for this row. |
| **C3 refuted (finer grid)** | `FEE_GRID_DOLLARS = 0.0001` is documented as **not holding for combos**, in `fees.py`'s docstring and ADR 0012 §5, with the observed bound from §6.2. This is a documentation change with a real consumer: `FEE_MATCH_TOLERANCE_DOLLARS`'s recorded limitation ("a correct combo model would also trip `fee_model_verified`") gains its first measurement. |
| **C4 identifies one candidate** | ADR 0012 §5 item 2 moves from *unverified* to *one observation, one sitting, not refuted* — and is written that way. No code change: a combo-aware fee model needs a durability window, and nothing trades combos. |
| **C4 NOT SEPARATED** | Recorded as a **power finding**: `D` was too small to distinguish the candidates. The next step is named — a single larger combo fill at a mid price would separate them — and it is **not taken by this document**, because a bet placed to move a measurement needs its own registration. |
| **C4 none of the candidates** | The most informative negative available. The combo schedule is not any form this repo models; ADR 0012 §5 is upgraded from *unverified* to *measured and unmatched*, with the ratios reported and no model fitted. |
| **C2 not refuted, C3 not refuted** | Nothing changes anywhere. The result document says exactly that, in one line, and it still gets written. |

**The honest reading of that table:** four of the six rows change no code, no
threshold and no gate, and the two contaminated branches (§6.1) are near-
determined before the look. **That is a finding about the plan and it is
recorded here rather than after the run.**

It is still worth running, for three reasons that do not depend on the outcome:
it is the first combo fee ground truth this project has ever had and the rows
**will be lost to the rolling endpoint** if nobody scores them; ADR 0012 §5 has
carried an *unverified* since it was written and this either narrows it or
proves it cannot be narrowed this way; and C1 is a real safety check on the one
error direction that corrupts the measurement record. It costs one script, no
credits, and no money.
