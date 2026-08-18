# Result — the combo fill fee look (one look, spent)

**Date:** 2026-08-18
**Registration:** `2026-08-18-preregistration-combo-fill-fee-look.md`,
committed (`b3e0a2b`) before any fee value was read. This is its one look
(§9); the look is now **spent**. A larger combo capture needs a fresh
registration.
**Producer:** `scripts/analyse_combo_fill_fees.py` (committed with this
document, re-runnable), reading only the gitignored capture — wrapper
`captured_at 2026-08-18T09:57:58Z`, `record_count 33`, exactly the file the
registration froze — and the committed leg-count JSON
(`2026-08-18-combo-leg-counts.json`, recorded per §4.5 before any
`fee_cost` was opened). **Every figure below is the producer's printed
output**, including the D, delta and shortfall columns.
**Audit:** measurement-skeptic, 2026-08-18. Draft verdict **DEFECTIVE** (14
required corrections — the arithmetic reproduced exactly; the write-up's
framing leaned flattering). All corrections applied; the buried finding it
surfaced is now the headline of C4.
**Privacy:** rows are identified by index 1–8 in capture order; no id, no
ticker. Counts, prices, leg counts and fees only, per §10.

## The pre-fee facts, printed before any charge was read (§5)

- Rows matched by the prefix rule: **8**. Distinct `order_id` count —
  **the document's n**: **8** (every order is a single fill; the
  MIXED-PRICE branch of §3.2 had nothing to bite on). No THIN stamp
  (n ≥ 3). NOT COMPUTABLE rows: **0**.
- Taker/maker: **8/0**. Buy/sell: **8/0**.
- Leg counts by row (§4.5 enrichment, 8 read-only market GETs, lengths
  only): **19, 16, 16, 21, 34, 62, 6, 13**.
- Sharpness at g = 1e-4 (a function of C and P alone): **all eight rows
  SHARP** (widths 0.000108–0.001102).
- Distinct (C, P) configurations: **7 of 8** — rows 2 and 3 are identical
  in count and price — over **5 distinct prices**, four of them at the
  $0.001 minimum tick and none above $0.228.

## C1 — STOP THE LINE, reported first as registered: rows 1, 5, 6 and 8 were charged more than the deployed model returns, by $0.000010 to $0.000080 per row

The direction is the finding — this is the one direction `fees.py` has
never chosen, and the direction that overstates every
`edge_after_fees_tenths` a combo consumer would print — and the magnitude
travels in the same headline so neither can be quoted without the other:
**no row's charge exceeds the model's by more than 0.19%.**

| row | C | P | D = C·P·(1−P) | deployed (M1) | charged | delta | ratio |
|---|---|---|---|---|---|---|---|
| 1 | 227.27 | 0.001 | 0.22704273 | 0.0159 | 0.015930 | +0.000030 | 1.0019 |
| 2 | 90.90 | 0.001 | 0.09080910 | 0.0064 | 0.006400 | 0 | 1.0000 |
| 3 | 90.90 | 0.001 | 0.09080910 | 0.0064 | 0.006400 | 0 | 1.0000 |
| 4 | 45.45 | 0.002 | 0.09071820 | 0.0064 | 0.006400 | 0 | 1.0000 |
| 5 | 28.32 | 0.033 | 0.90371952 | 0.0633 | 0.063340 | +0.000040 | 1.0006 |
| 6 | 71.94 | 0.013 | 0.92306214 | 0.0647 | 0.064780 | +0.000080 | 1.0012 |
| 7 | 4.15 | 0.228 | 0.73046640 | 0.0512 | 0.051200 | 0 | 1.0000 |
| 8 | 909.09 | 0.001 | 0.90818091 | 0.0636 | 0.063610 | +0.000010 | 1.0002 |

Per-row shortfall $0.000010 (row 8) to $0.000080 (row 6) — row 6 alone is
half of the total shortfall, stated per CLAUDE.md's
largest-contributor rule. Consequences are decided in **ADR 0046**, not
here (the registration's own rule: consequence to code, none; each change
needs its own ADR).

**Scope, before anything is quoted onward:** this is a statement about
*these eight fills* — one account, one sitting, one day, prices
$0.001–$0.228 — not about Kalshi, not about combos at mid prices where the
fee function actually peaks, and not about tomorrow.

## C4 — NONE OF THE REGISTERED CANDIDATES (§7 branch 3), with the MIXED branch (§7 branch 4) also in force

Both §7 conditions hold simultaneously — no candidate predicts every
scorable order, and one candidate (M1) matches some rows and not others —
and the registration sets no precedence between them, so both labels are
carried. (The draft chose MIXED alone; the audit flagged that as the
flattering choice and it is corrected here.)

**The central fact, which the match tally understates: `fee/D` exceeds
0.070 on every one of the eight rows** — by $0.000037 (row 1) to $0.000166
(row 6) in charge terms, implied k spanning **0.070041–0.070548**, with no
row at or below 0.070. M1 matches rows 2, 3, 4 and 7 exactly, but those
four are **grid coincidences, not rows where the deployed coefficient is
right**: rows 2, 3 and 4 carry the three *highest* implied k in the capture
(0.070478, 0.070478, 0.070548), and M1 coincides there only because its
ceil-to-$0.0001 rounds `0.070·D` up past the charge. On the exact form
(M5), all 8 of 8 rows are under-predicted. Every other candidate (M2–M10)
matches zero rows. M7, the deliberately-refuted control, failed visibly as
a control should: it predicts $0.00 on seven of the eight rows
(0.06·P·(1−P) rounds to zero cents per contract at these prices).

Per §7: M1 may **not** be promoted by dropping the rows that break it, no
post-hoc cut may separate them, and **no twelfth model is fitted here** —
the ratios span more than 1e-6, so the registered NOVEL COEFFICIENT
sentence is not available either. A novel form needs a fresh registration
on a fresh sample.

### The admissible-k intervals, at both grids (§4.2: both printed, neither promotable)

At the deployed grid g = 1e-4. On rows 1, 5, 6 and 8 the fee is not a
multiple of this grid, so the ceil-to-1e-4 model admits **no** k there at
all — for those rows the interval is a necessary condition for a refuted
model, not an admissible set:

| row | k interval, g = 1e-4 (half-open] |
|---|---|
| 1 | (0.069723, 0.070163] — no k admissible (off-grid fee) |
| 2, 3 | (0.069376, 0.070478] |
| 4 | (0.069446, 0.070548] |
| 5 | (0.069977, 0.070088] — no k admissible (off-grid fee) |
| 6 | (0.070071, 0.070179] — no k admissible (off-grid fee) |
| 7 | (0.069955, 0.070092] |
| 8 | (0.069931, 0.070041] — no k admissible (off-grid fee) |

At the inferred grid g = $0.00001 (§6): **all eight intervals lie entirely
above 0.070**, and they are not mutually consistent — rows 8
(0.070030, 0.070041] and 4 (0.070438, 0.070548] are disjoint — so **no
single k explains all eight at the finer grid either**:

| row | k interval, g = 1e-5 (half-open] |
|---|---|
| 1 | (0.070119, 0.070163] |
| 2, 3 | (0.070367, 0.070478] |
| 4 | (0.070438, 0.070548] |
| 5 | (0.070077, 0.070088] |
| 6 | (0.070169, 0.070179] |
| 7 | (0.070079, 0.070092] |
| 8 | (0.070030, 0.070041] |

- **Every row excludes k = 0.035, at either grid.** The baseball half-rate
  does not appear on any combo row in this capture.
- Row 6's charge exceeds `0.070·D` by $0.000166 and is not a multiple of
  $0.0001, so the deployed ceil-to-$0.0001 model at k = 0.070 returns
  $0.0647 on this row and no ceil-to-$0.0001 model at any k can return
  $0.064780.
- Placement against the single-game clusters is **descriptive only**
  (§4.3): the combo intervals sit at and above the non-baseball
  `(0.0699931, 0.0700000]` cluster and nowhere near the baseball one. Not
  pooled, not a reproduction.
- One caveat the design carries: `count_fp` arrives at two decimal places
  and D is built from it, so D's precision is bounded by the wire's
  displayed count. Checked as a competing explanation and ruled out: row
  4's full 45.4545… count moves implied k by 0.000006 against a 0.000548
  excess.

## C3 — `FEE_GRID_DOLLARS = 0.0001` does not hold for these combo rows (4 of the 8: rows 1, 5, 6, 8)

Charges as written carry 6 decimal places. The exact gcd of the eight
charges is **$0.00001**, so the registered one-sided sentence is: **the
combo grid is no coarser than $0.00001 on these rows.** It may not be
written as "the combo grid is $0.00001" — a finer grid is consistent with
eight observations.

**Entailment, not seven findings (§6.1):** a model that rounds up onto a
$0.0001 or $0.01 grid cannot produce an off-grid charge, so M1–M4 and
M8–M10 are refuted on rows 1, 5, 6 and 8 automatically. This fork was
near-determined before the look — the registration says so — and the live
question was the coefficient, answered under C4.

## C2 — deployed model mismatched on combos

Rows 1, 5, 6 and 8, same deltas as C1 (the deployed model *is* M1, and the
producer asserts its reimplementation equals `calculate_fee` on every row).
Rows 2, 3, 4 and 7 match exactly — see C4 for why those matches are grid
coincidences rather than support for the coefficient.

## C5, M11, maker

- **C5: NOT REACHED.** Its refuting branch needs a per-contract or
  leg-count form matching every order; M7–M10 matched no row. Per-order is
  not refuted and per-leg is not refuted, because nothing matched
  everything.
- **M11: NOT TESTABLE** — fill-time leg prices are unrecorded and
  unrecoverable; no substitute may be constructed. Leg-count multiples
  M9/M10 were testable (the enrichment succeeded on all 8) and matched
  zero rows.
- **Maker: NOT TESTABLE.** Zero maker rows; taker rows may not be
  substituted.

## Multiplicity, realised (§8)

8 orders × 10 scorable candidates = 80 exact comparisons, plus 8 C1
comparisons, 8 grid checks, one gcd. Exact comparisons against exact grids;
no rate, proportion, interval or p-value appears anywhere in this document
(§1.2).

## What this cannot establish (§11, carried in full)

**Whatever this analysis returns, it establishes nothing about what combos
are charged tomorrow** (§1.5's mandated sentence). Durability past one
account, one sitting, one day — a promotional or temporary combo rate is
not excluded, and the word throughout is *these fills*, not *Kalshi*. That
the venue charges other accounts what it charged this one — an
account-level rate is not distinguishable from a venue rate by one
account's record. Maker fees on combos. Sells, exits and round trips (the
product observed remains enter-only; the exit fee still has no wire shape).
The per-leg schedule ADR 0012 §5 names (M11 NOT TESTABLE). Which attribute
carries the rate structure — product, category mix, series and tier are all
confounded in these 8 rows simultaneously. The true grid below the observed
gcd (one-sided bound only). **Anything off the observed grid — prices,
sizes, leg counts, in-play status, and collections not present**: six of
eight rows sit at P ≤ $0.033 and none above $0.228, the deep tail of a fee
function that peaks at $0.50, so nothing here bounds the deviation at a mid
price — this is the bullet that would actually overturn the result. Any
other `KXMVE` family (the 2026-08-06 capture's calendar caveat — no NBA, no
NFL — is untouched). Anything about edge, EV, CLV, P&L, or whether combos
are worth betting — ADR 0038 closed the hunt and nothing here reopens it.
The calibration study is untouched (combos are structurally excluded from
it).

## Consequences, routed as registered (§12)

- **C1 refuted** → ADR 0046 decides what `fees.py` does about a model that
  can undercharge on combos. Decided there, not here.
- **C3 refuted** → `FEE_GRID_DOLLARS = 0.0001` is documented as not holding
  for these combo rows, in `fees.py` and ADR 0012 §5, with the §6.2 bound.
- **C4** → ADR 0012 §5 item 2 moves from *unverified* to *measured and
  unmatched: no registered candidate predicts all 8 orders; every row's
  implied k exceeds 0.070 and excludes 0.035*.
- Nothing here counts toward `_fee_model_verified`, widens
  `FEE_MATCH_TOLERANCE_DOLLARS`, changes any coefficient, or touches the
  gate.
