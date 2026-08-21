# H4 settlement-fee test — Look 1 result (2026-08-20)

Registered by `2026-08-20-preregistration-h4-settlement-fee.md` (committed
`4e0a025`, 2026-08-20T23:13:27Z). Pull taken **2026-08-20T23:44:23Z** via the
whitelisted `h4-settlement-balance` query against live — **30m56s** after the
registration's commit, clearing Look 1's "at least 30 minutes" rule. Analysis
code `scripts/analyze_h4_look.py`, committed **before** the pull (`4dbd3e2`),
implements the registered subtraction verbatim. This file was audited by the
measurement-skeptic before entering the record; the first draft **failed**
that audit on six prose defects (arithmetic clean), and this version is the
correction.

**Raw artifact:** NOT committed — operator account data, per the 2026-08-20
ruling. Retained privately at
`data/captures/h4_look1_pull_2026-08-20T234423Z.json` (gitignored), SHA-256
`3e935896577ee0573f64c0146204d180372ae6486b3ab5ec483530c0dcd64b09`.
Reproduction needs the operator's own pull — the limitation ADR 0058 records
for the fills prediction. **One tension is flagged for Joe rather than
smoothed:** the cluster table below carries derived position facts (tickers,
contract counts, win/loss, fee sums). The table *is* the measurement and
cannot go; if Joe rules that even derived aggregates cross the line, the
table moves to the private capture and this file keeps only classifications
and residual signs.

## The population, exactly as the query returned it

13 settlements since study start (matching the count registered in §2 before
the balances were read), 37 balance snapshots, **0 fills in any window** (C2
never fires), 37 balance polls all `ok = 1` (E3 never fires). The 1800s gap
rule yields **4 clusters**, and every exclusion counter E1–E6 reads 0 — all
4 clusters are eligible.

**Said plainly, per the unfired-guard rule: no exclusion fired in this look,
and at look time the analyzer had no test coverage at all** — the first
draft of this file falsely claimed otherwise and the audit caught it. Look
1's own numbers are verified by the measurement-skeptic's independent hand
re-derivation, not by tests. `tests/test_analyze_h4_look.py` was then
written the same day, before this file was committed: every exclusion E1–E6
and every classification branch is made to fire on synthetic payloads, with
E6 and the rule-1/rule-2 order mutation-verified red. The query feeding
sections A–D was already mutation-verified separately
(`TestH4SectionsAreWindowedAndUnjoined`, `tests/test_inspect_live_db.py`).
E6 remains worse than merely tested — see its finding below.

The analyzer's E1 interpretation, disclosed as its docstring requires: a
cluster containing any void/unchased `market_result` would have been excluded
WHOLE under E1 (its `P_c` is undefined and its cash effect still lands in the
cluster step). E1 read 0, so the interpretation decided nothing in this look.

## Per-cluster residuals, all reported quantities (registration §5)

| cluster (UTC day, kind) | n_setl | N contracts | n_win | W | P_c (tenths) | D_c | r_c | tau_c | seen* | classification |
|---|---|---|---|---|---|---|---|---|---|---|
| 08-18, single (`KXEARNINGSMENTIONKLAR`) | 1 | 5 | 1 | 5 | 5000 | 0 | **−5000** | 2 | 1 | **BANKING-CONTAMINATED** (§6.1) |
| 08-19, combo (8 × `KXMVECROSSCATEGORY`) | 8 | 1467 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | NO-CHARGE-AT-TOLERANCE |
| 08-20, combo (2 ×) | 2 | 71 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | NO-CHARGE-AT-TOLERANCE |
| 08-20, combo (2 ×) | 2 | 12 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | NO-CHARGE-AT-TOLERANCE |

\* `seen_before_registration = 1` on all four clusters — every settlement
predates the registration's commit, so the **blind arm is empty** and the
primary arm is the only arm. Of §0's four robustness measures, **three are
live** (arithmetic tolerance, inherited scale, additive-amendment rule); the
two-arm measure is inoperative by this fact. What the §0 glimpse could not
have steered: it could not separate "flat = losers" from "flat = consumed
proceeds", and the computed answer — all three flat combo clusters were
**losers** (`P_c = 0`) — is new information the glimpse did not contain.

Totals: N = 1,555 contracts, W = 5 winning contracts — all five in the one
BANKING-CONTAMINATED cluster. 4 clusters on 3 distinct UTC days; per §3's
same-day rule the count toward the K floor is **3** (the two 08-20 clusters
count once). The floor (K ≥ 2 on ≥ 2 days) is met either way.

## Cluster 1, in detail — the §6.1 branch is live

Five winning contracts predicted a **$5.00** credit (`P_c = 5000`, restated
from the table); the balance was **identical to the tenth** across the
interval — B_pre **2m58s** before settlement, B_post 2 min after. Three post
snapshots sat inside the +900s reach; E6 compared B_post against the last of
them, **10 minutes later**, and passed on a real comparison, not trivially.
`r_c = −P_c` exactly, to the tenth.

Classification followed the registered first-match order: rule 1
(`|r_c| > $0.05 × N_c`: $5.00 > $0.25) fires before rule 2, so the label is
**BANKING-CONTAMINATED**. Recorded honestly: **rule 2's description fits the
same numbers at least as well** — "a residual the size of the payout itself
means the proceeds did not reach cash inside the window" is *exactly*
`r_c = −P_c` — and the deferred-entry signature does **not** fit
(`fee_sum = 83` tenths ≠ 5000). The order was fixed before the data; it is
applied as fixed, and the tension is reported rather than resolved.

Bounding observations, from data already in the pull:

- The balance sat at its pre-settlement value **~10h41m later** (cluster 2's
  endpoints, same value to the tenth). If the $5.00 credit reached cash, it
  did so more than 10h41m after `settled_ms` — **or before the window
  opened**: a venue that credits cash first and stamps `settled_time` after
  is observationally identical here. **C6 as registered considered only late
  credits; the early direction was not registered.** Recorded as a gap,
  decided by neither.
- The balance changed between cluster 2 and cluster 3 — a span this
  instrument does not sample (sections B–D exist only within ±900s of
  settlements) — **from causes outside every window, unobserved and
  unattributable here.** Whether that span contains a transfer is part of
  the §6.1 question below; no cause is asserted.

**§6.1's required question, ANSWERED 2026-08-21:** *Joe — did you deposit,
withdraw, or transfer money in or out of Kalshi around 2026-08-18
14:51–14:56 UTC (about 7:51–7:56 AM PT that Tuesday)? And more broadly, any
transfer on 08-18/08-19?* Joe's answer, verbatim: **"I don't know maybe."**
Per Amendment 1 A13 this is the **UNANSWERED / cannot recall** branch:
recorded as UNANSWERED, the cluster stays non-voting with its
BANKING-CONTAMINATED label as registered, no verdict changes anywhere, the
question is **not re-asked**, and Look 2 proceeds on schedule. It neither
confirms nor eliminates rule 1's transfer explanation, so all accounts of
`r_c = −P_c` remain open exactly as listed in A13's NO branch plus the
transfer itself.

## The E6 finding — the guard is structurally blind in one direction

Registration §8 says of C6: *"The latency guard (E6) is the whole
treatment."* This look shows the treatment **fails in the only case that
could test it**: a balance that never moves trivially satisfies "stopped
moving by the window edge". **E6 cannot distinguish "the credit landed and
settled" from "the credit never came."** It guards against a credit caught
mid-flight; it is blind to a credit that is absent. Cluster 1 passed E6 and
still lost its observation. This is an instrument finding for the
pre-registrar, before Look 2.

## S2 — the per-contract shape (registered: NOT an H4 answer)

Over the three NO-CHARGE clusters: 1,550 contracts, every predicted step $0,
every observed step 0 tenths. The largest contributor is cluster 2 at
**1467/1550 = 94.6%** of the denominator (printed per the pooled-number
rule). Two denominators, both shown: over the three NO-CHARGE clusters,
`U2 = 3 tenths / 1,550 ≈ $0.0000019`/contract — a **post-data denominator
choice**, since §5's formula runs over all eligible clusters, which gives
`U2 = 5 / 1,555 ≈ $0.0000032`. Per the registration neither may be reported
as an H4 answer, and all three clusters are combination markets (fee model
independently unverified, ADR 0012 §5).

**And neither U2 figure is a usable bound, for a reason this same pull
demonstrates:** the only settlement in the population that predicted a cash
movement (cluster 1, $5.00 — 2,500× its own tolerance of τ_c = $0.002)
produced an observed movement of $0.00. The balance channel's demonstrated
in-sample sensitivity to settlement-time cash movement within ±900s is
therefore **nil**; assumption A2 ("settled proceeds credit the cash
balance"), which §8 said was not independently verified, **visibly failed**.
A per-contract debit is also a settlement-time cash movement, so the null on
the loser clusters is confounded with the same channel latency. **The U2
numbers are conditional on an assumption this pull contradicts and must not
be quoted as bounds.** What survives: no cash movement of any kind was
observed inside any cluster window, tolerance ~$0.001 per cluster (τ_c = 1
tenth on zero-winner clusters) — a statement about the channel as much as
about fees.

## The verdict, per kind — as §4 mandates

§4's kind split is mandatory and its void rule says "if the two kinds reach
different verdicts the pooled verdict is void and each is reported alone" —
while §6 says the kind split is "descriptive and **decides nothing**". Those
two sentences pull in opposite directions, and **choosing the per-kind route
is itself a reading made after the data was seen**; it is taken because it
is the route that requires the least interpretation on top of it, and both
routes reach the same substance. Under it, each cell lands on registered
text (the combo cell via §4's bridge to §11's eligible-population
conditional, not verbatim):

- **Single-kind cell** (1 cluster, 1 UTC day, the only proceeds in the
  population): the §6 floor — K ≥ 2 on ≥ 2 distinct days — is unmet.
  **Verdict: UNDERPOWERED**, per §6's floor line, pending §6.1's answer for
  the cluster's classification either way.
- **Combo-kind cell** (3 clusters, 2 days toward the floor, `W = 0`
  literally): §11's registered conditional applies verbatim — **"S1
  UNTESTABLE (W = 0)"** — and S2 is reportable but not as an H4 answer
  (above, with its channel caveat).

**Aggregate: H4 remains untested. ADR 0027 stands unchanged; the 0.63-point
headroom remains an upper bound; nothing is narrowed in either direction.**

A note on the pooled reading, reported because it is true and decides
nothing: evaluated pooled, none of §6's four aggregate branches fires on
{1 × BANKING-CONTAMINATED, 3 × NO-CHARGE} — no CHARGE cluster, not every
cluster NO-CHARGE, floor met, 1 of 4 not a majority. Whether that is a
registration gap depends on how §4's void rule is read; under the per-kind
reading above there is no gap. Both readings reach the same substance:
**no verdict that changes anything.** The pre-registrar should close the
pooled ambiguity in a dated additive amendment before Look 2 (2026-09-03),
alongside the E6 and early-credit findings.

**Look 2 proceeds per the registered schedule** — its trigger (UNDERPOWERED
or UNDECIDABLE) is met by the single-kind cell's UNDERPOWERED verbatim.

## What Look 2 needs, written now

The gap is coverage, not arithmetic — and **not poll density**: 25 snapshots
read one unchanging value across 11h02m, so polling faster observes the same
flat line. The binding constraints are **horizon** (the credit, if late,
lands beyond +900s) and possibly **channel** (if the credit posts before
`settled_ms`, no post-window catches it; if proceeds don't post to cash at
all, no window ever will). Widening the window, tracing the credit channel,
or registering the early-credit direction are instrument/registration
changes and belong to the pre-registrar before 2026-09-03, not to the look.
The W that §7 said would be needed remains: at least one winning settlement
whose credit demonstrably lands inside the instrument's reach.

## What this does not establish

Everything §9 of the registration lists, verbatim by reference, plus:
nothing about the venue's `k·C·P·(1−P)` shape (identically zero-valued at
settlement), no separation of a settlement charge from a deferred entry
debit (C7, whose signature did not fit cluster 1), nothing about
non-combination markets from the S2 cells (all combo), no per-contract bound
from U2 (channel assumption failed, above), and **no statement that
settlement is free** — the words §6 prohibits remain prohibited: this look
produced no NO-CHARGE-ABOVE-U verdict and does not narrow ADR 0027.
