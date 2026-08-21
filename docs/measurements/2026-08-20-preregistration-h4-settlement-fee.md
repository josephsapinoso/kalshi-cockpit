# Pre-registration — H4: does settlement carry its own fee?

Written 2026-08-20 ~22:40Z, before the subtraction it registers. `settlement_fee()`
(`backend/core/fees.py:197-209`) asserts *"Settlement is not a trade, so there is
exactly one fee: the one paid on entry."* That sentence is **H4**, ADR 0027 §1
records it as **UNTESTED**, and every `edge_after_fees_tenths` the tool prints has
been written as though it were confirmed. The instrument now exists
(`h4-settlement-balance`, `scripts/inspect_live_db.py:2081`, shipped `a02e8d2`).
This file fixes the arithmetic, the population and the verdict before anyone
computes a residual.

**The subtraction has not been taken. No residual, per-cluster or pooled, has been
computed by anyone.** §0 states exactly what *has* been seen.

---

## 0. Declared contamination — the balance data is partially unblinded

This is disclosed first because it is the strongest reason to distrust this file.

**What was seen, verbatim** (`tasks/NEXT.md`, committed `bd92e8e`, written after a
live pull at ~22:26Z on 2026-08-20 by the session that shipped the query):

> *"The first `h4-settlement-balance` pull works on live: 13 post-study
> settlements, a flat balance beside the 08-18/19 cluster then $8.31 on 08-20,
> ZERO fills inside any window -- no fill confound -- and every balance poll
> ok=1."*

**Who saw it:** that session (a Claude instance) and, through the commit, anyone
reading `NEXT.md`. Joe has not been shown the rows.

**What that discloses:** the row count of section A (13); a two-word qualitative
description of section B against two settlement groups; that section C is empty;
that section D is all `ok=1`. The `$8.31` figure is quoted here as it was written
and this file does **not** resolve whether it is a balance *level* or a *step* —
resolving it would be an analysis decision taken after a glimpse.

**What it does not disclose, and this is the load-bearing part:** the *predicted*
side of the subtraction. Nobody has computed `winning contracts × $1.00` for any
settlement in this population, so **no residual has been seen**, and the residual
is the entire statistic. A "flat balance" is equally the signature of a cluster of
losers (predicted step $0, no fee) and of a cluster of winners whose proceeds were
consumed — those are opposite verdicts and the glimpse does not separate them.

**How this registration is made robust to the glimpse.** Four measures, all of
which cost nothing and are checkable against this text afterwards:

1. **The tolerance is arithmetic, not a choice.** `tau` in §6 is derived from
   `ROUND_HALF_UP` in `dollars_to_tenths` (`backend/core/prices.py:81-83`). There
   is no tunable slack that could have been sized to a glimpsed number.
2. **The deciding scale is inherited, not picked.** `$0.0063/contract` is
   CLAUDE.md's and ADR 0027's 0.63-point headroom, written down days before the
   pull.
3. **Two arms, and the blind one governs a disagreement.** The **primary arm** is
   the full eligible population *including* the glimpsed clusters, which are
   flagged as `seen_before_registration = 1` in the write-up. The **blind arm** is
   every eligible cluster whose latest `settled_ms` falls **after this file's
   commit instant**. If the two arms reach different verdicts, the blind arm
   governs and the disagreement is the headline of the result.
4. **Amendments are additive and dated, never edits.** Any amendment written after
   a residual has been computed **voids the primary verdict** and demotes the whole
   read to exploratory.

Also declared: I have read ADR 0027, ADR 0026's summary as quoted in it, and the
line in `2026-08-11-settlement-fee-capture-result.md` recording `revenue = 100 ×
winning_count`. Those are pre-study rows and are outside the population below.

---

## 1. The question, as a claim that can come back false

**H4 (the claim under test):** *for the settlements in §2, the account's cash
balance step across settlement equals the gross payout — `$1.00 × winning
contracts` — with no deduction.*

**Direction.** The alternative is one-sided: a fee can only reduce the credit. So
the test is directional on the residual `r`:

- H4 true ⇒ `r = 0` within tolerance;
- H4 false ⇒ `r < 0`.

A residual `r > 0` beyond tolerance is **not evidence for H4**. It is an
unexplained credit and is classified as an anomaly (§6), because the mechanisms
that produce it — a deposit, a rebate, a mis-parsed payout — all break the identity
the test rests on.

**What is deliberately not claimed.** Not "Kalshi charges no settlement fee." The
reachable claim is an **upper bound on a per-contract settlement charge, in
dollars, at the resolution of the balance channel**. §6 requires the write-up to
state the bound and forbids stating a zero.

---

## 2. The population, and the exclusions

**Eligible settlement:** a row in `venue_settlements` with
`settled_ms >= 1787044503594` (2026-08-18T09:15:03.594Z, the study start hard-coded
at `scripts/inspect_live_db.py:2043`, chosen because the balance poller shipped
with the study and cannot have witnessed anything earlier). Section A of the query
is exactly this set. **Its count is 13 as of the 22:26Z pull** — registered here
*before* the balances are read against it, per the partner's directive.

**Exclusions, each independent of the residual:**

| # | Exclusion | Why it cannot reference the outcome |
|---|---|---|
| E1 | `market_result` NULL or not in `{yes, no}` (a void, or not yet chased) | The payout is undefined, not zero. Refusing beats inventing a side — the repo's standing rule |
| E2 | Any `fills` row in the cluster's balance interval (§3) | A fill moves cash for a reason that is not settlement. Section C exists to make this visible |
| E3 | Any balance poll with `ok = 0` in the cluster's window | A missing snapshot must read as an outage, not a zero delta |
| E4 | `balance_tenths` NULL on either endpoint | Unreadable resolves to None, never 0 |
| E5 | Any settlement **not in the cluster** — including pre-study rows — with `settled_ms` inside the cluster's balance interval | Another settlement's credit lands in the same step and is inseparable from it |
| E6 | The latency guard fails (§3) | The credit had not landed by the endpoint snapshot |

Every exclusion is **counted and printed** with its reason. An exclusion count is
part of the result, not a tidying step.

**No exclusion may be added after the residual is computed.** If one is genuinely
needed, it is an amendment under §0.4 and it voids the primary.

---

## 3. The unit of observation, and the clustering variable

**The unit is the *settlement cluster*, not the settlement row.** Kalshi settles a
slate together and the balance channel sees one step per batch, not one per
position. Counting 13 settlements as 13 observations would inflate `n` in exactly
the way this repo already shipped once (400 rows on one ticker counted as 400
observations).

**Cluster definition, fixed now:** settlements are sorted by `settled_ms` and cut
wherever consecutive `settled_ms` differ by more than **1,800,000 ms (1800s)**.
1800s is twice the `±900s` window the query already uses, so two settlements in one
cluster necessarily have overlapping windows. The gap is a property of the venue's
clock only.

**The cluster's balance interval** is `[B_pre.observed_ms, B_post.observed_ms]`:

- `B_pre` = the **last** balance snapshot with `observed_ms < min(settled_ms)` in
  the cluster and `>= min(settled_ms) - 900000`;
- `B_post` = the **first** balance snapshot with `observed_ms > max(settled_ms)`
  and `<= max(settled_ms) + 900000`;
- **Latency guard (E6):** `B_post.balance_tenths` must equal the balance at the
  **last** in-window snapshot. If the balance is still moving at the window edge,
  the credit is not settled inside the instrument's reach and the cluster is
  `UNDECIDABLE-COVERAGE`.

Nearest-either-side is used deliberately: it minimises the interval and therefore
the exposure to E5.

**Independence.** Two clusters are independent for this purpose if they fall on
different calendar days (UTC), because a deposit, a withdrawal or a venue-side
batching change is a per-day event. Clusters on the same day are reported
separately but count as **one** toward the `K` floor in §6.

---

## 4. The cut — the cells, fixed in advance

Three splits, named now, no others:

- **Shape S1 — a charge on proceeds.** Cell = clusters containing at least one
  **winning** settlement (`side == market_result`). Denominator: `W` = summed
  winning contracts.
- **Shape S2 — a charge per contract regardless of outcome.** Cell = **all**
  eligible clusters, including all-loser clusters, whose predicted step is `$0`. A
  per-contract charge shows there as a negative step against a zero prediction.
  Denominator: `N` = summed contracts.
- **Kind split (mandatory, descriptive):** `KXMVE*` (combination) versus everything
  else, printed beside every aggregate. ADR 0012 §5 records the combo fee model as
  unverified, so a pooled verdict that hides a combo/single disagreement is not a
  finding. **If the two kinds reach different verdicts the pooled verdict is void**
  and each is reported alone.

There is no price bucketing here and none may be added: at settlement `P` is 0 or 1
by definition, so there is no derived ask to bucket on. That is not an oversight —
see §9.

---

## 5. The statistic, named as an estimator

For each eligible cluster `c`, in **integer tenths of a cent** (`$1.00 = 1000`):

```
P_c  (predicted gross payout) = sum over i in c of round(1000 * contracts_i),
                                for i where side_i == market_result_i
D_c  (observed cash step)     = B_post.balance_tenths - B_pre.balance_tenths
r_c  (the residual)           = D_c - P_c
```

`P_c` is derived, not read: `venue_settlements` stores no revenue column, and
`parse_settlement` (`backend/portfolio_poll.py:150`) deliberately ignores the
deprecated `revenue`/`value` integer-cent fields. The `$1.00`-per-winning-contract
payout is corroborated independently by
`docs/measurements/2026-08-11-settlement-fee-capture-result.md:92`
(*"`revenue = 100 × winning_count` on 13 rows"*).

**`fee_cost_tenths` is NOT subtracted from `P_c`.** The entry fee was debited at
fill time, before the interval. Subtracting it here would charge it twice and would
manufacture exactly the finding this file exists to prevent. It is used only as the
discriminator in §6.4.

**What kind of estimator this is, said out loud: `r_c` is a deterministic
accounting residual, not a sample mean.** There is no sampling distribution behind
it, no standard error may be attached to it, and **no p-value may appear in the
write-up.** Its uncertainty is entirely (a) representation rounding, bounded
exactly, and (b) confounds, enumerated in §8. A write-up that reports
`sqrt(p(1-p)/n)` or any interval derived from `n` against this quantity has
misidentified the estimator.

**Reported quantities, all of them, in every branch:**

- `r_c` per cluster, in tenths and dollars, with `seen_before_registration` flagged;
- `U = (sum of tau_c) / W` dollars per winning contract — the S1 upper bound;
- `U2 = (sum of tau_c) / N` dollars per contract — the S2 upper bound;
- exclusion counts by reason; `K` (clusters), `W`, `N`; the kind split.

---

## 6. The decision rule, with the tolerance derived rather than chosen

**Tolerance.** `dollars_to_tenths` uses `ROUND_HALF_UP` to integer tenths, so each
balance endpoint carries at most 0.5 tenth of representation error and `D_c`
carries at most 1 tenth. Each winning settlement's `round(1000 * contracts_i)`
carries at most 0.5 tenth. Rounded up to integers:

```
tau_c = 1 + n_win_c      tenths, where n_win_c = number of winning settlements in c
```

**Per-cluster classification — evaluate in this order, first match wins:**

1. `|r_c| > $0.05 * N_c` ⇒ **BANKING-CONTAMINATED.** $0.05/contract is about 5× the
   largest per-contract fee ever observed on this account ($0.1785 on 20 contracts
   = $0.0089, `2026-08-10-fee-model-fill-calibration-result.md:82`). A residual that
   large is a transfer, not a fee. **Joe is asked whether a deposit, withdrawal or
   transfer occurred in that interval, and his answer is recorded in the result file
   before any verdict is stated.**
2. `P_c > 0` and `|r_c| >= 0.5 * P_c` ⇒ **UNDECIDABLE-CREDIT-CHANNEL.** A residual
   the size of the payout itself means the proceeds did not reach cash inside the
   window; it is not a fee of that size. Assumption A2 (§8) has failed.
3. `r_c > tau_c` ⇒ **ANOMALY** (unexplained credit). Not a vote for H4.
4. `r_c < -tau_c` ⇒ **CHARGE**, magnitude `-r_c`. Sub-classified by the C7
   discriminator: if `|r_c + sum(fee_cost_tenths_c)| <= tau_c`, the sub-verdict is
   **AMBIGUOUS-DEFERRED-ENTRY** — a settlement-time debit exactly the size of the
   recorded entry fee, which this instrument cannot separate from a second charge.
5. `|r_c| <= tau_c` ⇒ **NO-CHARGE-AT-TOLERANCE.**

**The floor, read before the effect.** `K >= 2` eligible clusters on **at least 2
distinct UTC days**. Below that: **UNDERPOWERED**, no verdict, ADR 0027 unchanged.
This floor is what makes the deposit confound survivable — one unrecorded transfer
can corrupt one cluster and cannot corrupt two on different days in the same
direction at the same magnitude.

**The aggregate verdict, in full:**

> **CHARGE CONFIRMED** — at least 2 clusters on at least 2 distinct UTC days
> classify **CHARGE** (excluding AMBIGUOUS-DEFERRED-ENTRY), *and* their implied
> per-contract magnitudes agree within a factor of 2. Report the magnitude as a
> range across clusters, never as a mean.
>
> **NO CHARGE ABOVE `U`** — every eligible cluster classifies
> **NO-CHARGE-AT-TOLERANCE**, `K >= 2` on at least 2 distinct UTC days, *and*
> `U <= $0.0063` per winning contract. The claim is **"any settlement charge on
> proceeds is below `U` dollars per contract"**, with `U` printed. **The words
> "zero", "no settlement fee", and "H4 confirmed" are prohibited in the write-up.**
>
> **UNDERPOWERED** — the floor is not met, *or* every cluster is NO-CHARGE but
> `U > $0.0063`. The instrument did not reach the scale that matters and ADR 0027's
> upper-bound language stands unchanged.
>
> **UNDECIDABLE** — the eligible clusters are split between CHARGE and
> NO-CHARGE-AT-TOLERANCE, or a majority classify BANKING-CONTAMINATED /
> UNDECIDABLE-CREDIT-CHANNEL / ANOMALY. No verdict; the exclusion table *is* the
> result.

**Multiplicity.** Cells tested: **2** (S1, S2), each once, plus the mandatory kind
split which is descriptive and decides nothing. There is no noise process here, so
no Bonferroni-style correction applies; the correction that *does* apply is the
agreement requirement inside CHARGE CONFIRMED and the void rule on a kind
disagreement. Both are stated above and both can come back negative.

**Repeated looks.** The record accumulates, so this will be looked at more than
once. An always-valid boundary is the wrong instrument for a deterministic
accounting identity — under a true zero this residual does not wander across a
threshold by chance, it sits at zero. The guard is therefore a **hard cap of three
looks**, each written up in the same file whatever it says:

- **Look 1:** the first pull taken at least 30 minutes after this file is committed.
- **Look 2:** 2026-09-03, only if look 1 returned UNDERPOWERED or UNDECIDABLE.
- **Look 3:** 2026-09-17, same condition.
- After look 3 the question is declared **BLOCKED ON INSTRUMENT** and no further
  look may be taken without a new registration naming what changed.

---

## 7. The stopping rule

Data collection is not steered by this test — the balance poller runs on a 300s
timer (`BALANCE_INTERVAL_S = 300`, `backend/portfolio_poll.py:484`) and settlements
arrive when Joe's positions resolve. So the stopping rule is a **look schedule**,
fixed above: three dated looks, then stop. No look may be moved earlier because a
residual looked interesting, and none may be added because one looked inconclusive.

---

## 8. Known confounds, and how each is excluded or bounded

| # | Confound | Treatment |
|---|---|---|
| C1 | **Deposits and withdrawals are unrecorded by design** (`backend/config.py:499`: *"A deposit is not recorded anywhere and would not be"*) | Bounded, not excluded. A deposit inflates the step (⇒ ANOMALY, which is not a vote for H4); a withdrawal deflates it (⇒ CHARGE at an implausible magnitude ⇒ BANKING-CONTAMINATED at $0.05/contract). The `K >= 2` on 2 distinct days floor plus the factor-of-2 agreement requirement is what stops a single transfer from producing a CHARGE verdict. Joe's answer on transfers is recorded before the verdict |
| C2 | **Fills inside the interval** | Excluded (E2). Section C of the query exists for this and was reported empty at 22:26Z — a fact about section C, which does not license skipping the check at look time |
| C3 | **Balance-poll cadence granularity** | 300s cadence against a ±900s window gives about 3 snapshots per side. E3/E4 require every in-window poll `ok = 1` and both endpoints non-NULL; E6 requires the balance to have stopped moving by the window edge |
| C4 | **Balance resolution** | `balance_dollars` arrives at $0.0001; `dollars_to_tenths` stores $0.001 and rounds half-up. A charge below about $0.0005/contract is invisible to this instrument on a single contract. This is the `U` bound, and it is why the verdict is a bound and not a zero |
| C5 | **Another settlement inside the interval** | Excluded (E5), checked against the *whole* `venue_settlements` table, not only the post-study slice |
| C6 | **`settled_time` is the venue's clock; cash-credit time is not observed** | The latency guard (E6) is the whole treatment. If credits routinely land later than 900s, every cluster goes UNDECIDABLE-COVERAGE and that is the finding |
| C7 | **A1: a settlement-time debit is not separable from a deferred entry-fee debit** | Not excludable by this instrument. Discriminator in §6.4 flags the coincidence; the follow-up that *would* separate them is a balance read across a **fill** window, which is a different registration and is named in §10 |
| C8 | **A2: settled proceeds are assumed to credit the cash balance** | Not independently verified here. Guarded by §6.2: a residual at payout scale is a credit-channel failure, not a fee |

### The `parse_portfolio_value_tenths` defect — checked, and it does not bind

The partner judged the two defect notes at `backend/portfolio_poll.py:252-266`
non-blocking. Verified against source, and the reason is precise:

```python
def parse_portfolio_value_tenths(payload: dict) -> Optional[int]:
    value = payload.get("portfolio_value")
    if value == 0:
        return 0
    return None
```

The field is accepted **only at zero**, so on any account holding an open position
`portfolio_value_tenths` is NULL — deliberately, until the unit is pinned. **This
test does not use that column.** The residual is computed from `balance_tenths`,
which comes from `parse_balance_tenths` reading `balance_dollars` (the 4-decimal
string), not the whole-cent `balance` integer — a distinction documented at
`portfolio_poll.py:242-248` after `balance` was observed as `2065` beside
`balance_dollars` `"20.6583"`.

**How the defect bounds the read:** it removes a *redundant* channel, not the
primary one. With `portfolio_value` available, a settlement could be cross-checked
as a transfer from position value to cash, the sum conserved up to any fee. Without
it, the cash step is the only channel and confounds C1/C8 cannot be cross-checked
internally — they are handled by the classification rules instead. **It introduces
no bias in either direction**, because it censors a column that appears nowhere in
`r_c`. Section B emits the NULL on purpose so a reader sees the refusal rather than
a silent absence.

---

## 9. What this cannot establish, drafted before the run

- **It cannot detect a charge of the exchange's own `k*C*P*(1-P)` shape.** At
  settlement `P` is 0 or 1, so that expression is identically $0 — ADR 0027 §1
  reason 2. A NO-CHARGE verdict here is silent about that shape. It is silent about
  it *harmlessly* only if the venue evaluates `P` at settlement; if it evaluates at
  some earlier instant, the charge is real, non-zero, and invisible here. **That is
  the caveat most likely to overturn this result and it is written before the run,
  not after.**
- **It cannot separate a settlement fee from a deferred entry-fee debit** (C7).
- **It cannot establish that Kalshi charges nothing.** The output is an upper bound
  `U` at the balance channel's resolution. Below `U` this instrument is blind.
- **It says nothing about the fee *coefficient*.** ADR 0027 §3(a)'s finding — that
  `calculate_fee` returns a `max()` above what the venue charges — is a different
  question, and the two have been conflated in this repo before (ADR 0027 §5:
  *"`fee_candidates` is not `calculate_fee`"*).
- **It is one account, one operator, one venue, over days.** ADR 0028 already
  records that every observation of `k = 0.035` lies inside four days on a venue
  whose schedule demonstrably changed. Nothing here is a claim about the venue's
  future policy.
- **It says nothing about combination markets unless the kind split says so**, and
  ADR 0012 §5 records the combo fee model as unverified independently.
- **A CHARGE verdict does not size the charge for other prices or sizes.** The
  magnitude is per-contract on the contracts observed, nothing more.
- **It bears on no signal.** `beta`, ADR 0021's refutation and ADR 0038's closure
  are untouched in both branches. A larger fee makes the refuted strategy worse,
  never better.

---

## 10. What each verdict costs and buys — including "nothing"

**Stated plainly first: no live trading decision hangs on this today.** The gate is
closed, `ORDERS_ARE_DRY_RUNS = True` (`backend/store/orders.py:129`), and ADR 0038
closed the hunt. This measurement does not open a quadrant and does not change what
gets built. By the pre-registrar's own standard that makes it **not
trade-decision-relevant, and that is worth saying before the run rather than
discovering it afterwards.**

What it *is* relevant to, and why it is worth taking anyway: it decides whether a
shipped function's docstring is true, and it removes one of the two bounds ADR 0027
§3(a) hangs on a single scalar.

- **CHARGE CONFIRMED** ⇒ `settlement_fee()`'s *"exactly one fee"* is **false** and
  the function is wrong wherever it is consumed (`backend/core/ev.py:89,140`,
  `backend/core/parlay.py:213`, `scripts/rescore_fee_models.py:128`,
  `scripts/run_clean_shortfall.py:157`). The 0.63-point headroom drops by the
  measured per-contract charge. A code change needs its own ADR — **this
  registration authorises none.**
- **NO CHARGE ABOVE `U`** ⇒ ADR 0027 §4 prohibition 1 is narrowed: the headroom may
  be stated without the *settlement* qualification, carrying `U` explicitly, while
  the **coefficient** qualification of §3(a) and the price-dependence of §3(b)
  remain in force. 0.63 does not become a point figure.
- **UNDERPOWERED / UNDECIDABLE** ⇒ ADR 0027 stands unedited, and the result file
  states the `W` that would have been needed for `U <= $0.0063`.

**The negative branch's destination, fixed now:**
`docs/measurements/2026-08-2X-h4-settlement-fee-result.md` (X = the look's date).
**Every look writes to that file, including UNDERPOWERED and UNDECIDABLE**, and a
look that produces no file is a protocol violation to be recorded as such.

**The named follow-up, so C7 does not quietly become a permanent hole:** a balance
read across a **fill** window — the same four sections, windowed on
`fills.filled_ms` instead of `settled_ms` — separates "the entry fee is debited at
entry" from "it is debited at settlement". It needs its own registration and it is
not proposed here.

---

## 11. The power check, done before committing anything

The instrument's resolution per cluster is `tau_c = 1 + n_win_c` tenths — **$0.002
for a single-winner cluster**. The quantity that decides the question is the
0.63-point headroom, **$0.0063 per contract**.

```
U = (sum over c of tau_c) / W      dollars per winning contract
```

With `K` clusters of one winning settlement each, `sum(tau_c) = 2K` tenths =
`$0.002K`, so `U <= $0.0063` requires `W >= 0.32 * K` winning contracts — satisfied
by **one winning contract per cluster**.

**Verdict: powered, conditional on `W >= 1`.** The instrument resolves a charge
about three times smaller than the one that would matter, at the smallest sample
that can exist. There is no `n` argument for delay.

**The conditional branch, registered because it is real:** if `W = 0` — no winning
settlement in the eligible population — then **S1 is untestable** (a charge on
proceeds has no proceeds to be levied on: ADR 0027 §1 reason 1, the exact trap that
made the denominator 1 of 3 in 2026-08) and only **S2** is testable, at
`U2 = sum(tau_c)/N`. The write-up must say `S1 UNTESTABLE (W = 0)` in that case and
must **not** report the S2 result as an H4 answer.

**Nothing is spent.** No Odds API credits, no orders, no writes to any production
table. The query is read-only against the live DB.

---

# Amendment 1 — 2026-08-20, after Look 1, governing Look 2 onward

**Status and standing, stated first because everything below depends on it.**

This amendment is **additive**. Nothing above it is edited, and §§0–11 stand
byte-for-byte as committed in `4e0a025`.

**It is written after Look 1's residuals were seen.** I have read
`docs/measurements/2026-08-20-h4-settlement-fee-result.md` (committed `883c884`)
in full, including the per-cluster residual table. Under §0.4 of the registration
above — *"any amendment written after a residual has been computed voids the
primary verdict and demotes the whole read to exploratory"* — that rule is
honoured in the only way that keeps both records honest:

> **This amendment governs Look 2 and Look 3 only. It does not reach Look 1.**
> Look 1's classifications, its verdicts (single-kind UNDERPOWERED, combo-kind
> S1 UNTESTABLE, aggregate H4 untested) and its record stand exactly as written
> and are **not re-scored** under anything below. No verdict anywhere is
> narrowed, widened, or moved by this amendment, and ADR 0027 is untouched.

**The contamination guard, since a post-hoc amendment is the textbook place to
manufacture a finding.** Three properties, each checkable against this text:

1. **No threshold moves.** `$0.0063` (the deciding scale), `$0.05/contract`
   (rule 1's plausibility ceiling), `tau_c = 1 + n_win_c`, the `K >= 2` on 2 days
   floor, and the factor-of-2 agreement requirement are all unchanged.
2. **Every addition below can only subtract a finding, never add one.** E7 and PC
   are an exclusion and a control — they remove observations and refuse bounds.
   A9's tree adds no branch that can declare CHARGE CONFIRMED or NO CHARGE ABOVE
   `U` on a configuration that could not already have declared it. Adding a
   refusal to a set of findings cannot create one, which is the same arithmetic
   CLAUDE.md uses on the missing second signal.
3. **The one place Look 1's numbers were consulted** is A9.6, where the tree is
   walked against Look 1's classification multiset to check it is *total*. That
   check tests exhaustiveness, not outcome, and the walk is shown so it can be
   audited.

---

## A9. The aggregate rule is made total (closes result-file finding 1)

**The gap.** On Look 1's multiset `{1 BANKING-CONTAMINATED, 3
NO-CHARGE-AT-TOLERANCE}` **none** of §6's four aggregate branches fires: no
cluster classifies CHARGE, so CHARGE CONFIRMED is out and UNDECIDABLE's split
clause is out; not every cluster is NO-CHARGE, so NO CHARGE ABOVE `U` and
UNDERPOWERED's second clause are out; the floor is met, so UNDERPOWERED's first
clause is out; 1 of 4 is not a majority, so UNDECIDABLE's majority clause is out.
§6 was written as four sufficient conditions and never checked for exhaustiveness.
A second, quieter half of the same gap: §11 registers **S1 UNTESTABLE (W = 0)**
as a real outcome and §6's four branches have no slot for it, and `U` is a
division by `W` that is undefined at `W = 0`.

**A9.1 — Voting and non-voting clusters.** Every eligible cluster is exactly one:

- **Voting:** `CHARGE` (excluding the AMBIGUOUS-DEFERRED-ENTRY sub-verdict) and
  `NO-CHARGE-AT-TOLERANCE`.
- **Non-voting:** `BANKING-CONTAMINATED`, `UNDECIDABLE-CREDIT-CHANNEL`,
  `ANOMALY`, `AMBIGUOUS-DEFERRED-ENTRY`, and `UNDECIDABLE-COVERAGE` (A10).

The partition is exhaustive because §6.1–§6.5 plus A10 assign every eligible
cluster exactly one label and each label appears in exactly one column above.

**A9.2 — The aggregate decision tree, evaluated in order, first match wins.**
Let `V` = the voting clusters, `d(V)` = the number of distinct UTC days they span,
`W_V` / `N_V` = winning / total contracts summed over `V`.

```
A1  non-voting count >= half of all eligible clusters      -> UNDECIDABLE
A2  (S1 cell) W_V = 0                                      -> S1 UNTESTABLE (W = 0)
    (S2 cell) N_V = 0                                      -> S2 UNTESTABLE (N = 0)
A3  |V| < 2  or  d(V) < 2                                  -> UNDERPOWERED
A4  V contains at least one CHARGE and at least one
    NO-CHARGE-AT-TOLERANCE                                 -> UNDECIDABLE
A5  every cluster in V is CHARGE:
      magnitudes agree within a factor of 2                -> CHARGE CONFIRMED
      otherwise                                            -> UNDECIDABLE
A6  every cluster in V is NO-CHARGE-AT-TOLERANCE:
      U (resp. U2) <= $0.0063 per contract                 -> NO CHARGE ABOVE U
      otherwise                                            -> UNDERPOWERED
A7  anything not matched above                             -> UNDECIDABLE
```

**A9.3 — Why it is total.** After A1, `V` is non-empty. After A2, the relevant
denominator is non-zero, so `U` / `U2` are defined wherever A6 reads them. After
A3, `|V| >= 2` on `>= 2` days. A4, A5 and A6 partition the possible compositions
of `V`, whose members are only CHARGE or NO-CHARGE by A9.1. A7 is therefore
unreachable and exists so the rule is a total function rather than a set of
sufficient conditions — the defect that produced this amendment.

**A9.4 — The kind split, reconciled (closes the §4-versus-§6 contradiction).**
§4 says a kind disagreement voids the pooled verdict; §6 says the split "decides
nothing". Both stand under one reading, registered now as the only reading:

> The tree in A9.2 is evaluated **three times**: pooled over all eligible
> clusters, once over `KXMVE*` clusters, once over non-`KXMVE*` clusters. **The
> pooled evaluation produces the registered verdict.** The two kind evaluations
> are reported beside it and can do exactly one thing to it: **if both kind cells
> are non-empty and their verdicts differ, the pooled verdict is stamped VOID
> (kind disagreement) and the look registers no aggregate verdict.** A kind-level
> verdict is **never** promoted to the registered verdict — in particular a
> kind-level CHARGE CONFIRMED or NO CHARGE ABOVE `U` under a pooled UNDECIDABLE
> stays reported-only. If either kind cell is empty, the pooled verdict stands
> and the split is descriptive.

That is precisely what "decides nothing" means: **the split can subtract a
verdict and can never add one**, so it adds no tested cell for multiplicity. The
multiplicity count is unchanged at 2 (S1, S2).

**A9.5 — The look schedule, with the new verdicts slotted in.** §6's schedule
advances on UNDERPOWERED or UNDECIDABLE. Registered completion: **the schedule
advances to the next look on any verdict except CHARGE CONFIRMED or NO CHARGE
ABOVE `U`**, which are terminal. `S1 UNTESTABLE`, `S2 UNTESTABLE` and `VOID (kind
disagreement)` are non-terminal. The three-look cap and the dates (2026-09-03,
2026-09-17) are unchanged, as is the requirement that every look writes to the
result file whatever it says.

**A9.6 — The totality walk, shown for audit.** Look 1's multiset, walked purely
to demonstrate the tree is total. **This is not a re-score of Look 1 and Look 1's
verdicts are unchanged.** Pooled, S1 cell: non-voting is 1 of 4, under half, so A1
does not fire; `V` = the three NO-CHARGE clusters, whose winning contracts sum to
zero, so **A2 fires: S1 UNTESTABLE (W = 0)** — a verdict, where §6 produced none,
and substantively the same statement Look 1 reached by its per-kind route. The
configuration that broke §6 now lands, and it lands on a branch that narrows
nothing.

---

## A10. E7, the movement condition — E6 gets a companion (closes finding 2)

**The defect, from the result file:** *"a balance that never moves trivially
satisfies 'stopped moving by the window edge'. E6 cannot distinguish 'the credit
landed and settled' from 'the credit never came.'"* Look 1's only proceeds-bearing
cluster passed E6 on a real ten-minute comparison and still lost its observation.

**A10.1 — E7 (movement condition), Look 2 onward, evaluated with E1–E6 and
therefore *before* classification.**

> For a cluster with `P_c > 0`: if `max(balance_tenths) - min(balance_tenths)`
> over **every** snapshot in the cluster's covered span is `<= tau_c`, the cluster
> is **UNDECIDABLE-COVERAGE**. It is **not classifiable by §6 rules 1–5** and is
> non-voting under A9.1.

**Rationale, and it is the whole point:** the channel was predicted to move by
`P_c` and did not move at all. A residual computed across a channel that showed no
sensitivity to a movement it was predicted to show measures the channel, not a
fee. Placing E7 among the exclusions rather than among the classifications is
deliberate — a coverage failure is a reason the observation does not exist, not a
label for what it says.

**A10.2 — What this does and does not do to Look 1.** Under E7, Look 1's cluster 1
would have been excluded as UNDECIDABLE-COVERAGE rather than classified
BANKING-CONTAMINATED, which is closer to the tension the result file reported
honestly (rule 2's description fit the same numbers at least as well). **Look 1 is
not re-scored.** In both labellings the cluster is non-voting and every Look 1
verdict is identical, which is stated here so that E7 cannot be read as
re-labelling a seen cluster to taste: it changes no verdict that has been taken.

**A10.3 — PC, the channel positive control, Look 2 onward.**

> A look may report `U` or `U2` **as a bound** only if at least one eligible
> cluster in that look demonstrates channel sensitivity: `P_c > 0`,
> `|D_c| > tau_c`, and `|D_c - P_c| <= tau_c` — a predicted movement of roughly
> the predicted size actually observed. Absent that control, the look's `U` and
> `U2` are reported as **CHANNEL-UNVERIFIED** and **may not be quoted as bounds**,
> and A9.2's A6 may not return NO CHARGE ABOVE `U`; it returns UNDERPOWERED
> instead.

This registers in advance what Look 1 reached by hand: a null on zero-winner
clusters is confounded with channel latency, because a per-contract debit is also
a settlement-time cash movement. Note what PC cannot do — it can only **withhold**
a bound. It cannot produce a CHARGE.

---

## A11. The early-credit direction (closes finding 3)

**The gap, from the result file:** *"a venue that credits cash first and stamps
`settled_time` after is observationally identical here. C6 as registered
considered only late credits; the early direction was not registered."* If the
credit lands before `min(settled_ms)`, `B_pre` already contains it and
`r_c = -P_c` exactly — the same signature as a credit that never came.

**A11.1 — How Look 2 treats it.** Over the cluster's covered span (widened per
A12), the analyzer performs a **deterministic step scan**, no search over
magnitudes and no operator judgement:

- Let `step_j = balance(s_{j+1}) - balance(s_j)` over consecutive snapshots in the
  span. A step is **payout-shaped** if `|step_j - P_c| <= tau_c`.
- **Payout-shaped step strictly before `min(settled_ms)`** ⇒ the cluster is
  labelled **EARLY-CREDIT**, non-voting, and the **lead time is recorded as its
  own line** — a fact about the venue's clock, which is worth having whichever way
  H4 goes.
- **Payout-shaped step at or after `max(settled_ms)` and inside the horizon** ⇒
  the credit landed; `B_post` is taken per A12.2 and the cluster is classifiable
  by §6 rules 1–5 as registered. This is the case the instrument wants.
- **No payout-shaped step anywhere in the span** ⇒ **UNDECIDABLE-COVERAGE** via
  E7, and the write-up must state explicitly that *late-beyond-horizon*,
  *early-beyond-horizon*, and *proceeds never credited to cash at all* are **not
  separated by this look**.

**A11.2 — The paired-cancellation rule.** If one span interval carries
`r ≈ +P_c` and an adjacent interval carries `r ≈ -P_c` (each within `tau_c`), the
credit landed inside the first interval and the **interval boundary, not the
venue, is the cause**. The two intervals are merged and re-evaluated once. This
fires at most once per cluster and the merge is recorded.

**A11.3 — What A11 cannot do.** It cannot detect a credit that lands outside the
horizon in either direction, and it cannot detect a credit that never reaches the
cash balance at all. Those three remain fused, and A10.1 routes all three to the
same honest label rather than to a fee.

---

## A12. Horizon, not density — the span design (closes finding 4)

**The refutation, accepted:** 25 snapshots read one unchanging value across
11h02m, so a faster poller observes the same flat line. Density is not the
constraint; **horizon and channel are.** Registered accordingly.

**A12.1 — The binding fact, and it is good news:** `venue_balance_snapshots` is
**never pruned** — grep for a DELETE against that table returns nothing, and the
only readers take the newest row. Every snapshot since study start is still in the
table. **The 900s horizon is a property of the query, not of the data**
(`scripts/inspect_live_db.py:2046`, `_H4_WINDOW_MS = 900_000`, applied via three
`EXISTS` windows). Look 1's horizon limit therefore costs nothing retrospectively:
the wider data already exists and is merely hidden.

**A12.2 — Look 2's primary design: adjacent-snapshot spans, no window at all.**
Rather than widening 900s to some number chosen after seeing a flat 11h02m — which
would be a threshold picked to fit a glimpse — the window is **dropped**:

> Take every balance snapshot since study start in time order. For each
> **adjacent pair** `(s_j, s_{j+1})` with both `balance_tenths` non-NULL and every
> balance poll between them `ok = 1`, the observation is
> `D_j = balance(s_{j+1}) - balance(s_j)` and the prediction is
> `P_j = sum of 1000 x contracts over all winning settlements with settled_ms in
> (s_j, s_{j+1}]`, summed over **every** settlement in the table, pre-study rows
> included. The residual is `r_j = D_j - P_j`, tolerance
> `tau_j = 1 + n_win_j`.

Three properties this buys, each structural rather than chosen:

- **E5 stops being an exclusion and becomes a term.** A second settlement inside
  the interval is no longer a contaminant to exclude; it is added to `P_j`,
  because the prediction is additive. That is what makes dropping the window
  affordable — under E5 as written a 24h window would have excluded nearly
  everything.
- **Every settlement is accounted and every cash movement is attributed.** There
  is no unsampled span between clusters, which is where Look 1's balance
  demonstrably changed with no observation covering it.
- **The early/late credit question becomes answerable within the same arithmetic**
  (A11.2) instead of needing a separate instrument.

The exposure this buys, stated because it is real: an interval can be long, so an
unrecorded transfer has more room to land in one — it surfaces as a residual and
is caught by §6 rule 1 at `$0.05 x N_j`. And `N_j` grows as settlements merge into
an interval, so rule 1's ceiling grows with it: **a transfer is easier to miss in
a long, contract-heavy interval than in a short one.** The countermeasure is
unchanged and already registered — `A9.2/A3`'s floor of 2 voting clusters on 2
distinct days, plus A5's factor-of-2 agreement, so no single interval can carry a
CHARGE verdict alone.

Under the span design the **cluster** of §3 remains the reporting unit for
continuity with Look 1, and the interval is the computing unit; where an interval
contains exactly one cluster the two coincide.

**A12.3 — The instrument change this requires, named now.** A new whitelisted
query, **`h4-balance-spans`**: sections A–D as today but **unwindowed since study
start** (settlements, balance snapshots, fills, balance polls), plus the *whole*
`venue_settlements` table for the `P_j` sum, still with **no join and no computed
delta** — the same discipline as `h4-settlement-balance`, since a tolerance is a
matching decision. It must ship, with its window-mutation guards red, **before**
the Look 2 pull, and the analyzer change must be committed before the pull as
Look 1's was (`4dbd3e2`).

**A12.4 — The fallback, registered so it cannot be decided later.**

> If `h4-balance-spans` has not shipped by 2026-09-03, **Look 2 runs the existing
> ±900s design unchanged**, and its verdict on any winning cluster is **capped at
> UNDECIDABLE-COVERAGE**: on a flat balance the ±900s instrument can only repeat
> Look 1's coverage verdict, and Look 2 must say so in those words rather than
> report a residual as a fee or a bound. The zero-winner cells may still be
> reported, subject to PC (A10.3), which will withhold their bounds.

---

## A13. Joe's transfer question — the consequence of each answer, fixed now

§6.1 required the question and the result file records it as **PENDING**. The
registration said his answer is recorded before the verdict but never said what
the answer *does*, which leaves the consequence to be chosen after it arrives.
Fixed here.

**The question, unchanged:** *did any deposit, withdrawal or transfer touch the
Kalshi account around 2026-08-18 14:51–14:56 UTC, or more broadly on 08-18/08-19?*

**In all three branches, no verdict changes.** Look 1's single-kind cell stays
UNDERPOWERED, the combo cell stays S1 UNTESTABLE, H4 stays untested and ADR 0027
stays unchanged. The question is **diagnostic, not decision-bearing**, and saying
so before the answer arrives is the point of registering it.

- **YES (a transfer occurred).** The BANKING-CONTAMINATED label is **confirmed as
  an explanation**. The cluster remains non-voting. Direction and approximate size
  are recorded if he can give them; if the size is far from `$5.00` that is itself
  worth a line, because rule 1 fired on magnitude alone.
- **NO (no transfer).** The label is **not changed** — Look 1's classification
  order was fixed before the data and Look 1's record stands. What a NO answer
  does is **eliminate rule 1's explanation while leaving the label**, so the
  surviving accounts of `r_c = -P_c` are exactly: (i) the proceeds never reached
  cash, (ii) the credit landed outside ±900s in either direction, (iii) a charge
  of 100% of proceeds — which is not seriously entertained and is inconsistent
  with `revenue = 100 x winning_count`. A NO answer therefore **strengthens the
  channel finding and raises the priority of A12.3's instrument change**; it is
  not a reason to reclassify anything. It is written into the result file as a
  dated addendum.
- **UNANSWERED or cannot recall by 2026-09-03.** Recorded as **UNANSWERED**, the
  cluster stays non-voting, the question is **not re-asked**, and Look 2 proceeds
  on schedule. An open question may not become a reason to delay a look.

**Forward effect on rule 1.** For Look 2 onward, E7 (A10.1) is evaluated before
classification, so a winning cluster with a flat balance is excluded as
UNDECIDABLE-COVERAGE and **never reaches rule 1**. The rule-1-versus-rule-2 order
tension Look 1 reported honestly cannot recur on that configuration, and the
ordering itself is left exactly as registered for every other configuration.

---

## A14. What Amendment 1 does not establish

- It **measures nothing**. No residual is computed here and no verdict anywhere is
  changed, narrowed or widened. ADR 0027's upper-bound language stands.
- It **does not rescue Look 1**. Look 1 lost its only proceeds-bearing observation
  and no amendment recovers it; that observation is gone.
- It **does not make H4 answerable**. The instrument may still be blind: if
  settled proceeds do not credit the cash balance at all — which Look 1 is
  consistent with — then no horizon, no cadence and no span design reaches the
  charge, and the honest terminal state after Look 3 is BLOCKED ON INSTRUMENT.
- It **does not authorise a code change to the fee path**. `settlement_fee()` is
  untouched, and A12.3 authorises exactly one read-only query and one analyzer.
- **A12.2's span design is untested at the time of writing.** It is registered on
  its arithmetic, not on a run, and a defect found in it before 2026-09-03 must be
  fixed by a further dated amendment rather than by a decision at look time.
- **Amendment 1 is itself post-hoc.** The three guards at the head of this section
  are the whole defence, and a reader who thinks they are insufficient should
  discount Look 2 accordingly rather than be talked out of it here.
