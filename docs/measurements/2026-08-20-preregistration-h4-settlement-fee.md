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

---

# Amendment 3 — 2026-08-21 ~02:15Z, before the channel diagnostic runs

**Status, standing and numbering, stated first because everything below depends
on them.**

This amendment is **additive**. Nothing above it is edited. §§0–11 stand
byte-for-byte as committed in `4e0a025`, and Amendment 1 (A9–A14) stands
byte-for-byte as committed in `9bc9dad`. Clauses continue at **A15** from
Amendment 1's A14.

**On the number 3.** *There is no Amendment 2 in this file.* The designation is
the partner agent's (2026-08-21) and the gap is recorded here rather than
silently closed, so that a future reader does not go hunting for a document that
was never written. The two commits that could be mistaken for it are `9bc9dad`
(Amendment 1 to this registration) and `30f1c2e` (Joe's §6.1 answer, recorded as
an addendum to the *result* file under A13, amending nothing here). The
"Amendment 2 (A10–A12)" referenced at `tasks/NEXT.md:357` belongs to
`2026-08-17-preregistration-joe-calibration-bet-log.md`, a different
registration. Renumbering this to 2 would break the partner's ruling as issued;
skipping is the smaller lie and it is written down.

**When this was written, relative to what.** It is written **after** Look 1's
residuals were seen (Amendment 1's disclosure carries forward unchanged) **and
after a second, larger partial unblinding disclosed in A15 below**. It is
written **before** the A17 diagnostic's pull exists, and it must be committed
before that pull is taken — that is the entire reason it exists as a document
rather than as a decision at run time.

> **This amendment governs Look 2, Look 3 and the A17 diagnostic only. It does
> not reach Look 1.** Look 1's classifications and its verdicts (single-kind
> UNDERPOWERED, combo-kind S1 UNTESTABLE, aggregate H4 untested) stand exactly
> as written in `docs/measurements/2026-08-20-h4-settlement-fee-result.md` and
> are **not re-scored** under anything below. No verdict anywhere is narrowed,
> widened or moved by this amendment, and ADR 0027 is untouched.

**The contamination guards, since a post-hoc amendment written by someone who
has now read the balance series is the textbook place to manufacture a
finding.** Five properties, each checkable against this text:

1. **No threshold moves.** `$0.0063` (the deciding scale), `$0.05/contract`
   (rule 1's plausibility ceiling), `tau = 1 + n_win`, the `|V| >= 2` on 2
   distinct UTC days floor, and the factor-of-2 agreement requirement are all
   unchanged. A17 introduces exactly one new constant, the `±24h` HIT-WIDE
   neighbourhood (A17.4), and it is fixed here before any span delta has been
   paired to any settlement by anyone.
2. **A16 can only subtract observations.** It moves settlement-free spans out
   of the voting set. Removing votes cannot create a verdict that the full set
   could not already have produced — the same arithmetic CLAUDE.md uses on the
   missing second signal.
3. **A17's one widening runs against the terminal verdict, not toward it.**
   HIT-WIDE makes **BLIND** — the verdict that kills the analyzer and closes
   the series — *harder* to reach, never easier. A design change that makes it
   harder to stop work is not a change that flatters a finding.
4. **A17.11 forecloses relitigation in advance.** The overturn condition for a
   BLIND verdict is written now, while it costs nothing, rather than at the
   moment someone dislikes the verdict.
5. **There is no blind arm for A17, and pretending otherwise would be the
   dishonest move.** §0.3 could offer one because the settlements had not yet
   happened. Here the channel record is finite and already partially read
   (A15). The defence is *not* that the analyst is blind; it is that the
   population, the statistic, the decision rule, **both** consequences, the
   stopping rule and the terminal-state overturn condition are all fixed in
   this file before the pull. That is a weaker defence than blinding and it is
   named as weaker here rather than dressed up.

---

## A15. The second disclosure — a partial unblinding occurred before Look 2

This is disclosed first, in §0's shape, because it is the strongest reason to
distrust A16 and A17.

**What was derived, and by whom.** On 2026-08-21, before Look 2 and before the
A17 diagnostic was designed, the partner agent derived new inference about the
study population from data **already on disk** — no new pull, no new query. The
present author then re-derived every number below independently from the same
files before writing them here. Both are Claude instances. Joe has not been
shown the rows.

**The three findings, with the arithmetic that reproduces them.**

*Finding 1 — the balance channel responded to debits.*

| quantity | value | source |
|---|---|---|
| balance at study start | `20658` tenths, from venue string `balance_dollars` `"20.6583"` | `balance_at_study_start_tenths`; documented at `backend/portfolio_poll.py:246` and `2026-08-17-preregistration-joe-calibration-bet-log.md:1092,1243` |
| balance at 2026-08-18T14:41:03.714Z | `15923` tenths (`$15.923`) | Look 1 pull, section B, first row |
| drop | **`$4.7353`** | `$20.6583 − $15.9230` |
| captured fills dated 2026-08-18 | **`$4.503100`** = notional `$4.225040` + fees `$0.278060`, over 8 buys from 09:45:59.143Z to 09:57:31.141Z | `data/captures/portfolio_fills.json` |
| unexplained remainder | **`$0.2322`** | `$4.7353 − $4.5031` |

*Finding 2 — and then it did not respond to a payout.* Section B's first **25**
rows are contiguous and all read `balance_tenths = 15923`, **unchanged to the
tenth**, from `2026-08-18T14:41:03.714Z` to `2026-08-19T01:43:08.954Z` —
**11h02m05.24s**. Section C (fills in window) is empty and section D's 37
balance polls are all `ok = 1`, so no fill and no outage explains the flatness.

*Finding 3 — a $5.00 credit was predicted inside that flat run.* Nine of
section A's 13 settlements have `settled_ms` inside the span. Exactly one wins:
`id 177`, `KXEARNINGSMENTIONKLAR-26AUG18-WALM`, `side = yes`,
`market_result = yes`, `contracts = 5.0`, settled `2026-08-18T14:54:02.349Z` —
predicted gross payout **`$5.0000`** by §5's `P_c`. The other eight are `KXMVE`
losers at `$0`.

**Said in one line: debits moved the channel; a payout did not.**

**Three things that did not reproduce cleanly, flagged rather than smoothed.**

- **The `$4.735` drop is not an adjacent-snapshot delta and is not derivable
  from the two named files alone.** Section B's *first* row is already `15923`;
  the opening endpoint `$20.6583` comes from a **third** source (the study-start
  meta value, documented in `backend/portfolio_poll.py`). So this is an
  **interval-level** match over roughly 09:15Z→14:41Z on 08-18, not a
  delta-level one. It is weaker evidence than "a delta matched a debit" and must
  be quoted as the weaker thing.
- **`$4.5031` is a lower bound on the debits in that interval.**
  `portfolio_fills.json` was captured at `2026-08-18T09:57:58.754911Z`; any fill
  between then and 14:41Z is simply not in the file. The `$0.2322` remainder is
  therefore *unexplained or uncaptured* and may not be called a fee, a rounding
  artifact, or anything else. (The last captured fill's cash cost is `$0.2432` —
  near it and **not equal**, differing by `$0.0110`. Noted so nobody
  re-discovers the coincidence and builds on it.)
- **The fourth decimal is ambiguous, for a documented reason.** Against the
  stored `20658` tenths the drop is `$4.7350` and the remainder `$0.2319`;
  against the venue's `"20.6583"` string they are `$4.7353` and `$0.2322`. The
  `$0.0003` is the half-up rounding in `dollars_to_tenths` — the same term §6
  already carries as `tau`. Both roundings support the quoted `$4.735` and
  "within `$0.232`"; neither supports a claim at that resolution.

**What this discloses.** The direction of the channel's sensitivity (it responds
to debits), one instance of its insensitivity (a `$5.00` predicted credit against
25 flat snapshots over 11h02m), and the identity and size of the record's only
known covered winning settlement. All of it was already implicit in the
committed Look 1 result file; A15 makes it explicit and numeric.

**What it does not disclose.** No span-design residual. `scripts/` contains no
span analyzer — `analyze_h4_look.py` implements the ±900s cluster design only —
so **no `D_j`, `P_j`, `r_j` or `tau_j` under A12.2 has been computed by anyone.**
Section E of `h4-balance-spans` (the whole `venue_settlements` table, pre-study
rows included) has never been pulled or read. No balance snapshot after
`2026-08-20T04:20:39.418Z` has been read.

**The honest consequence for A17, stated before the run rather than discovered
after it.** Because A15's findings are on the record, **the post-study slice of
A17's question is already largely visible**, and this file will not pretend
otherwise. What A17 still adds, and the only reasons it earns a pull:

1. the **whole-table** denominator (section E), never read;
2. every settlement after `2026-08-20T04:20:39.418Z`, never read;
3. the **HIT-WIDE** scan (A17.4) over the unwindowed record, which no
   instrument in this repo has ever performed in either time direction.

If the diagnostic returns BLIND, a fair reader is entitled to say it was
foreseeable from Look 1. **That is not a defect in the diagnostic; it is the
reason its value is a clean ending rather than a result** (A17.9).

---

## A16. Spans are not clusters — the voting defect, closed as a rule

**The defect.** A12.2 makes **every adjacent snapshot pair** an observation.
A9.2's floor (`|V| >= 2` on 2 distinct UTC days) is defined over **clusters**.
Nothing in Amendment 1 says which spans become clusters, so read literally,
every pair enters `V`. At `BALANCE_INTERVAL_S = 300` that is `86400/300 = 288`
pairs per day: **~4,000 pairs from 2026-08-20 to 2026-09-03**, ~4,600 from
study start, minus whatever the observed cadence gaps remove. The overwhelming
majority carry `P_j = 0` **and** `D_j = 0` — zero-information observations that
would each classify NO-CHARGE-AT-TOLERANCE under §6 rule 5 and **vote**. A floor
of two, satisfied four thousand times over by spans containing nothing, is not a
floor.

There is a second, arithmetic half to the same defect: on a settlement-free span
`N_j = 0`, so §6 rule 1's ceiling `$0.05 × N_j` is **`$0`** and *any* non-zero
residual classifies BANKING-CONTAMINATED. The classification rules degenerate on
exactly the spans A16 removes.

**A16.1 — The rule, fixed now.**

> A span `(s_j, s_{j+1}]` becomes a **cluster** — and is therefore eligible to
> enter `V` and to be classified by §6 rules 1–5 — **if and only if it contains
> at least one settlement row**: some row of `h4-balance-spans` section E (the
> whole `venue_settlements` table, pre-study rows included) with
> `settled_ms in (s_j, s_{j+1}]`. A span containing **no settlement of any kind**
> is **COVERAGE-ONLY**: it is computed, printed and counted, and it **never
> votes**.

**A16.2 — The discriminator is containment of a settlement, not `P_j > 0`.** A
span holding only **losing** settlements has `P_j = 0` and *does* become a
cluster and *does* vote. That is not a loophole, it is **the S2 cell** as
registered in §4 — "a charge per contract regardless of outcome... shows there
as a negative step against a zero prediction". Using `P_j > 0` as the
discriminator would silently delete S2 from the study. `N_j > 0` is what
distinguishes the two cases and it is also what makes rule 1 well-defined.

**A16.3 — What this changes.** Exactly one thing: **the membership of `V`**, and
therefore the denominators A9.2 reads — `|V|`, `d(V)`, `W_V`, `N_V` — and
A10.3's positive-control search, which now looks only among clusters. Nothing
else.

**A16.4 — What this does not change.** The arithmetic of A12.2 is **untouched**:
`D_j`, `P_j`, `r_j = D_j - P_j` and `tau_j = 1 + n_win_j` are computed for
**every** adjacent pair exactly as registered, COVERAGE-ONLY spans included, and
every one of them is printed. In particular COVERAGE-ONLY spans remain fully
available to, and are required by:

- **A11.1's deterministic step scan**, which looks for payout-shaped steps
  *outside* the containing span in both time directions — a step that arrives
  early or late lands in a COVERAGE-ONLY span by definition, and discarding
  those spans would destroy A11 entirely;
- **A11.2's paired-cancellation rule**, whose adjacent interval is frequently
  settlement-free;
- **A17's HIT-WIDE scan** (A17.4);
- the **coverage accounting** — total pairs, COVERAGE-ONLY count, cluster count,
  and any pair dropped for `ok = 0` or a NULL endpoint — all of which is printed
  in the result file. A12.2's property that "every settlement is accounted and
  every cash movement is attributed" survives intact, because nothing is
  dropped from the computation; the change is only about what is allowed to
  vote.

**A16.5 — No verdict moves.** Look 1 ran the ±900s cluster design and had no
spans at all, so A16 cannot reach it. No look has been taken under the span
design. A16 is registered before the first one, which is the only time this
rule could have been written without choosing an answer.

---

## A17. The channel-only diagnostic, registered before it runs

**Standing.** The partner agent ruled on 2026-08-21 that **the A9–A12 analyzer
is not built until this diagnostic runs**. A17 registers the diagnostic. The
instrument it reads — `h4-balance-spans` (A12.3) — shipped tonight in commit
`349dca0` (`scripts/inspect_live_db.py:2488`, sections A–E, no join and no
computed delta, window-mutation guards mutation-verified red in
`tests/test_inspect_live_db.py`) and is deployed to live. **This clause is
committed before the pull; the pull may not be taken before it is.**

**A17.1 — The question, as a claim that can come back false.**

> **Claim D:** *there exists at least one winning settlement in the whole
> `venue_settlements` record for which the account's `balance_dollars` moves by
> that settlement's predicted credit, within the registered tolerance, in some
> adjacent-snapshot delta of the span record.*

**Direction.** One-sided and existential. Claim D is **refuted** by the whole
covered record producing no such match, and **confirmed** by one. It cannot be
"confirmed" by a partial or suggestive pattern: a delta either matches within
`tau` or it does not.

**What is deliberately not claimed.** This is a question about **the
instrument**, not about the venue and not about H4. Confirming Claim D does not
say a settlement fee is zero, non-zero, or anything else. Refuting it does not
say Kalshi withholds proceeds. It says the cash-balance channel does or does not
carry payouts at the resolution this study reads it.

**A17.2 — The population, and the exclusions.**

**Eligible:** every row of `h4-balance-spans` **section E** — the whole
`venue_settlements` table, pre-study rows included, no window — with
`market_result in {yes, no}`, `side == market_result` (a **winner**), and
`contracts > 0`.

| # | Exclusion | Why it is independent of the outcome |
|---|---|---|
| D1 | `market_result` NULL or not in `{yes, no}` | Payout undefined, not zero. §2's E1 verbatim |
| D2 | `side != market_result` (a loser) | Predicted credit is `$0`; a zero prediction cannot demonstrate that a channel carries credits in either direction |
| D3 | **UNCOVERED** — `settled_ms` earlier than the first balance snapshot or later than the last, so no span contains it | A property of the balance poller's clock, fixed by when the poller shipped. Every pre-study settlement is expected to fall here and that is not a finding |
| D4 | **UNPOLLED** — the containing span has a `poll_log` row with `ok = 0`, or either endpoint's `balance_tenths` is NULL | A missing snapshot reads as an outage, not a zero delta (§2 E3/E4) |

D3 and D4 rows are **counted and printed with their reasons** and are
**neither confirmations nor refutations** — they cannot vote in either
direction. **No exclusion may be added after the pull.**

**A17.3 — The unit of observation.** The unit is **the winning settlement**,
matched to the unique span `(s_j, s_{j+1}]` containing its `settled_ms`. Not the
span, not the snapshot, not the cluster.

**Independence is not required and no clustering variable applies**, and that is
said out loud because §3 required one and this statistic does not. The estimand
is an **existential over a finite enumerated record**, not a mean over a sample.
There is no sampling distribution, **no standard error may be attached, and no
p-value may appear in the diagnostic's write-up** (§5's rule, carried forward).
Two winners settling in the same batch are not "two observations" in any sense
that could inflate an `n`, because no `n` is used inferentially — the denominator
is reported only to size how much of a chance Claim D was given.

**A17.4 — The statistic.** In integer tenths (`$1.00 = 1000`), by A12.2's
arithmetic exactly:

```
For adjacent snapshot pair j:   D_j = balance(s_{j+1}) - balance(s_j)
For the span containing winner i:
    P_j     = sum of round(1000 * contracts) over ALL winning settlements
              with settled_ms in (s_j, s_{j+1}]
    n_win_j = the count of those winning settlements
    tau_j   = 1 + n_win_j                       tenths
```

Two nested tests, both fixed here:

- **HIT-STRICT(i):** the pair `j` containing winner `i` satisfies `P_j > 0` and
  `|D_j - P_j| <= tau_j`. The credit landed inside its own span.
- **HIT-WIDE(i):** there exists **any** adjacent pair `k` with `s_k` and
  `s_{k+1}` both within **24 hours** of winner `i`'s `settled_ms` (a ±24h
  neighbourhood, fixed now, chosen as one venue day and **not** tuned to any
  observed gap) such that `|D_k - P_i| <= tau_i`, where
  `P_i = round(1000 * contracts_i)` and `tau_i = 2` tenths. This is A11.1's
  payout-shaped-step scan applied in both time directions, and the **lead or
  lag** of any hit is recorded as its own line.

`HIT-STRICT ⇒ HIT-WIDE` by construction (the containing pair is inside the
neighbourhood), so the two are nested and cannot disagree in the direction that
matters.

**Reported quantities, in every branch:** the eligible winner count; D1–D4
counts by reason; total adjacent pairs; COVERAGE-ONLY pairs (A16); per eligible
winner its `P_i`, its containing span's `D_j`, `P_j`, `tau_j`, `r_j`, and its
HIT-STRICT and HIT-WIDE flags; the number of deltas scanned per HIT-WIDE test;
and the lead/lag of every hit.

**A17.5 — The decision rule, with both consequences fixed now.**

> **BLIND** — **no** eligible winner returns HIT-WIDE (and therefore none
> returns HIT-STRICT), on an eligible-winner count of **at least 1**.
>
> **CARRIES CREDITS** — **at least one** eligible winner returns HIT-WIDE.
> Stamped **CARRIES CREDITS (STRICT)** if any hit is HIT-STRICT, otherwise
> **CARRIES CREDITS (WIDE)**; both route to the same consequence.
>
> **UNTESTED (no covered winner)** — the eligible-winner count after D1–D4 is
> **zero**.

**The consequences, both directions, fixed before the pull:**

- **BLIND ⇒** Look 2 is written up **early** as **BLOCKED ON INSTRUMENT**, at
  the diagnostic's date rather than on 2026-09-03. **Look 3 is cancelled.** The
  H4 look series **closes**. **The A9–A12 analyzer is never built**, and the
  `h4-balance-spans` query stays shipped but unused. **ADR 0027's upper-bound
  caveat stands permanently as worded** and `settlement_fee()`'s docstring stays
  **UNTESTED** — not confirmed, not refuted. §6's prohibition on the words
  "zero", "no settlement fee" and "H4 confirmed" is carried into this verdict
  and applies to it.
- **CARRIES CREDITS ⇒** the A9–A12 analyzer gets **one dedicated build session**
  before 2026-09-03 — its code committed before the Look 2 pull as Look 1's was
  (`4dbd3e2`) — and **Look 2 proceeds on 2026-09-03 under Amendments 1 and 3**.
  A CARRIES CREDITS (WIDE)-only result additionally requires the build session's
  **first** act to reconcile the recorded lead/lag against A11.1's EARLY-CREDIT
  branch, because a wide-only hit *is* the early/late-credit case A11 exists for.
- **UNTESTED (no covered winner) ⇒ this is not BLIND and may not be reported as
  BLIND.** Absence of winners is not evidence of blindness — the trap §11 already
  registered as `W = 0`, and the trap that made the denominator 1 of 3 in
  2026-08. The analyzer is **not** built, Look 2 is **not** brought forward, the
  series stays open, and Look 2 runs on 2026-09-03 as scheduled under A12.4's
  fallback if the analyzer still does not exist. **The diagnostic does not
  re-run** (A17.6); this outcome is recorded and the Look 2 date carries it.

**Multiplicity.** Cells tested: **1**. There is no cell grid, no bucketing, no
kind split and no threshold sweep here. HIT-WIDE scans many deltas per winner
and that count is printed; the guard is that a coincidental match requires an
unrelated cash movement equal to a specific winner's payout to within `$0.002`,
and any HIT-WIDE that is not HIT-STRICT is reported with its lead/lag so a reader
can judge it rather than take it on the verdict's word. **No correction is
applied and none is needed, because the scan can only make the terminal verdict
harder to reach.**

**A17.6 — The stopping rule.** The diagnostic runs **exactly once**, on
**exactly one** `h4-balance-spans` pull, dated in the result file.

- The pull is taken **no earlier than 30 minutes after this amendment is
  committed** (Look 1's rule, verbatim) and **no later than
  2026-08-27T00:00:00Z**.
- If it has not been taken by then, the diagnostic **lapses**: no verdict is
  recorded, the analyzer is not built, and Look 2 runs on 2026-09-03 under
  A12.4's fallback.
- **No second pull, for any reason** — not to widen a horizon, not because the
  first looked inconclusive, not because a new settlement arrived. A technical
  failure (query error, database unreachable, empty response) is **not a look**;
  it may be re-attempted, and **every attempt is logged in the result file with
  its timestamp and its failure mode**, so a silent retry cannot become a second
  look.

**A17.7 — What data it reads, and how the data is handled.** One read-only
`h4-balance-spans` pull from **live** via the whitelisted
`scripts/inspect_live_db.py`. No writes to any production table, no orders, no
Odds API credits. **Nothing is spent.**

The pull is **operator account data and is NOT committed**, per Joe's
2026-08-20 ruling. It is held privately at
`data/captures/h4_spans_pull_<ISO8601>.json` (under `data/`, gitignored at
`.gitignore:33`), and its **SHA-256 is recorded in the result file** — the same
handling as Look 1's pull. Reproduction needs the operator's own pull, and the
result file must say so.

**The result file, fixed now:**
`docs/measurements/2026-08-21-h4-channel-diagnostic-result.md`. **Every outcome
writes to it, including BLIND and UNTESTED**, and a run that produces no file is
a protocol violation to be recorded as such (§10's rule, carried forward). If
the derived table would carry position facts, the handling follows the tension
already flagged in Look 1's result file rather than being re-decided here.

**A17.8 — Who audits.** The **measurement-skeptic** audits the diagnostic's
output **before it enters the record**, the same discipline as Look 1's two
audits — where the first draft **failed** on six prose defects and the failure
is recorded in the file rather than erased. A failed audit here is corrected and
the failure noted the same way. **The audit precedes the record; a verdict that
was recorded before audit is void and must be re-recorded after one.**

**A17.9 — Why this earns a session at all, in the partner's framing.**

> **This diagnostic buys a clean ending, not a result.**

Stated with §10's honesty: **no live trading decision hangs on it.** The gate is
closed, `ORDERS_ARE_DRY_RUNS = True`, ADR 0038 closed the hunt, and neither
branch opens a quadrant. What it buys is that the H4 series stops for a
**stated, measured reason** — the channel cannot see payouts — instead of
drifting to Look 3 and expiring on a schedule. A study that ends because its
instrument was shown blind has a record; a study that ends because the dates ran
out has a gap. **That difference is the whole return, and it is the only reason
this earns time.**

**A17.10 — The transfer confound, and its asymmetry.** A deposit or withdrawal
inside a span can **mask** a credit (a `$5.00` withdrawal against a `$5.00`
credit gives `D_j = 0`, which reads as blindness) or **mimic** one (a `$5.00`
deposit inside a span containing a `$5.00` winner gives a HIT with no credit
behind it). Deposits are unrecorded by design (`backend/config.py:499`) and
**Joe's §6.1 answer is already on the record as UNANSWERED / cannot recall**
(A13, committed `30f1c2e`), so this cannot be resolved by asking. **The question
is not re-asked** — A13: an open question may not become a reason to delay a
look. Registered treatment:

- **Masking is the direction that would manufacture a BLIND, and under an
  existential rule it must be universal to do so.** One unmasked winner returns
  CARRIES CREDITS. So a transfer-induced BLIND requires a transfer of exactly
  the predicted credit, to within `$0.002`, inside the containing span, for
  **every** eligible winner in the record. This is registered as **implausible
  but not impossible**, and it goes into the BLIND verdict's written caveat —
  **not** into a rule that anyone may invoke afterwards to reopen the verdict
  (A17.11 governs that, and this is not it).
- **Mimicry is the direction that would manufacture a CARRIES CREDITS**, and its
  cost is one build session and no verdict. That is the cheap direction and it
  is **accepted**. It is bounded in the write-up by printing the lead/lag of
  every hit: a genuine credit's step sits at or near its settlement, and a
  mimicking transfer has no reason to.
- **The confound is not excluded and is not claimed to be.** It is bounded by
  asymmetry, and the asymmetry is stated here before the pull rather than
  discovered in the direction that suits the answer.

**A17.11 — Can a BLIND verdict be overturned, and by what. Fixed now, so the
terminal state cannot be relitigated at look time.**

> A **BLIND** verdict is **terminal for this instrument**. It may **not** be
> overturned by: a later look at the same channel; a wider horizon; a faster
> poll cadence; a re-run of `h4-balance-spans`; a re-reading of the same pull; a
> new analyzer over the same rows; more settlements accumulating; or any
> argument about what the record "would show with more data". Every one of those
> reads the **cash-balance channel**, and BLIND is precisely the finding that
> the cash-balance channel does not carry the quantity.
>
> It may be overturned by **exactly one thing: a new instrument reading a
> different channel**, introduced by a **further dated amendment to this file**
> which (a) names the channel, (b) states why that channel carries settlement
> proceeds where the balance channel does not, (c) ships its query with
> mutation-verified guards **before** any pull, and (d) registers its own
> decision rule with both consequences fixed. Three candidate channels are named
> now so the bar is concrete and not invented later: a settlement-time endpoint
> reporting proceeds directly; `portfolio_value` **after its unit is pinned** by
> the observation `parse_portfolio_value_tenths` already demands
> (`backend/portfolio_poll.py:252-266`); or a venue-issued transaction ledger or
> statement.
>
> Absent such an amendment, **H4 stays UNTESTED**, ADR 0027 §1 stands, and
> `settlement_fee()`'s docstring is neither confirmed nor refuted. **BLIND is
> not a verdict about the venue.**

**A17.12 — The power check, done before the pull.** The estimand is an
**existence**, so the detectable effect is not an effect size:

- **In the CARRIES direction the diagnostic is powered at `n = 1`.** One eligible
  winner whose credit lands as a step of the predicted size returns CARRIES
  CREDITS. The tolerance is `tau_i = 2` tenths = **`$0.002`** against a smallest
  possible credit of `$1.00` (one contract) — a match window of 0.2% of the
  smallest quantity it must recognise, and 0.04% of the one known `$5.00` case.
  There is no `n` argument for delay.
- **In the BLIND direction the strength is entirely the covered-winner
  denominator**, which is why **that denominator is printed first, before any
  hit flag** — the repo's "read `n` before the effect size" rule, applied to a
  count that is known to be small. A BLIND on a denominator of 1 is a much
  weaker statement than a BLIND on a denominator of 10, and the write-up must
  state the denominator **in the same sentence as the verdict**, every time it
  is quoted.
- **At a denominator of zero the diagnostic returns UNTESTED, not BLIND**
  (A17.5), which is the arithmetic that stops a zero from being read as an
  answer.

**Verdict: powered to confirm at the smallest sample that can exist; its
refutation is exactly as strong as the denominator it prints, and never
stronger.**

---

## A18. What Amendment 3 does not establish

- It **measures nothing.** No residual, no delta pairing and no verdict is
  computed here. A15 re-derives figures already implicit in the committed Look 1
  record and computes no new statistic. ADR 0027's upper-bound language stands
  unchanged in every branch.
- It **does not answer H4**, and A17 is not a test of H4. A17 tests the
  *instrument*. Both of its verdicts leave `settlement_fee()`'s *"exactly one
  fee"* exactly as untested as it was on 2026-08-20.
- It **does not rescue Look 1**, which lost its only proceeds-bearing
  observation. No amendment recovers it.
- It **does not authorise a code change to the fee path.** `settlement_fee()` is
  untouched. A17 authorises exactly one read-only pull of an already-shipped
  whitelisted query, and — on CARRIES CREDITS only — one analyzer build session
  whose output is code, not a verdict.
- **A16 is registered on arithmetic, not on a run.** No look has been taken under
  the span design, so A16's rule has never been executed. A defect found in it
  before Look 2 must be fixed by a **further dated amendment**, not by a decision
  at look time — Amendment 1's A14 rule, carried forward.
- **A17's `±24h` neighbourhood is a choice, and it is the only new constant
  here.** It is fixed before the pull and it can only make BLIND harder to
  reach, but a credit landing more than a day from its settlement would be
  missed and would read as blindness. That is the caveat most likely to overturn
  a BLIND verdict, and it is written **before** the run rather than after.
- **A17 cannot separate "proceeds never credited to cash", "credited outside the
  ±24h neighbourhood", and "credited to a channel this study does not read."**
  Those three remain fused, exactly as A11.3 already recorded, and BLIND names
  the fused state rather than choosing among them.
- **A15's disclosure is a mitigation, not a cure.** The author of this amendment
  has read the balance series and one predicted payout. Nothing here restores
  blinding, and the five head guards are the whole defence. A reader who finds
  them insufficient should discount A17's verdict accordingly rather than be
  talked out of it here.
- It **bears on no signal.** `beta`, ADR 0021's refutation and ADR 0038's closure
  are untouched in every branch. A settlement fee, whatever its size, makes the
  refuted strategy worse and never better.
