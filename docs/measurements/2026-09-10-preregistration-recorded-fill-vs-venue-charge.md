# Pre-registration — does the recorded hand-bet price equal the price Kalshi charged?

Written **2026-09-10**, before any row of the join has been read.

Registered as a **census of an instrument**, not as an estimate about Joe. It is
scoped narrowly and deliberately: an earlier session proposed it as a bounded
live query with no registration, on the reasoning that an accuracy check on a
recording path is not one of the four quantities
`docs/measurements/2026-08-29-preregistration-operator-self-assessment.md`
prohibits. That reasoning is accepted below (§0.2). The registration exists
anyway, because the *decision* attached to the result — persist three dropped
fields as schema v39, or close the item — would otherwise be chosen after
seeing two to twenty numbers, and that is the failure this document class
prevents.

---

## 0. Standing before anything is read

### 0.1 Declared blindness

**Seen while writing this:** `backend/store/manual_orders.py:765-788`
(`record_outcome`), `backend/kalshi/orders.py:285-320`
(`OrderOutcome.fill_price_tenths`), `backend/api/routes.py:3570-3615` (check 7)
and `:3945-3995` (the position write), `backend/portfolio_poll.py:190-215`
(`ParsedFill`), `backend/core/hedge.py:1-70`, `backend/store/schema.sql:1698-1711`
(the retention comment), the 2026-08-29 registration in full,
`scripts/inspect_live_db_money.py`, `tests/test_inspect_live_db.py:932-1010`,
`docs/measurements/2026-09-09-fee-alarm-replayed-over-every-hand-fill.md`.

**Not seen, not queried, not requested:** any value of
`manual_orders.fill_price_tenths`, any value of `fills.price_tenths`, any
difference between them, the row count of the join, and any P&L, settlement,
win rate, CLV or typed estimate on any hand bet.

**The row count was deliberately not obtained.** No floor in this document is a
function of `n` — §2 fixes the reporting form for every `n`, including `n = 0`
and `n = 1`.

### 0.2 The prohibition, read directly, and where its edge actually is

Two different prohibitions have been conflated in discussion. They have
different scopes and only one of them binds here.

**(a) The 2026-08-29 registration governs a screen, and four quantities.** Its
subject is "panels on Joe's own record"; the prohibited quantities are P&L, win
rate, CLV and settled outcome. The sentence that governs this proposal is §6f,
quoted verbatim:

> **6f. Execution quality — REJECTED as a metric about Joe**
> Every hand bet is immediate-or-cancel at the ask; there is no maker path on
> this route. So the price he paid is a property of the path, not of his
> decision. Scoring him on it would score the code. **Cut.**

That sentence is the closest the registration comes to this quantity, and it
cuts the proposal *in*, not out. It rejects execution quality on the explicit
ground that the price paid **is a property of the code**. This measurement's
subject is the code. §6f forbids putting it on the operator's screen as a
judgement about him; it does not reserve the underlying quantity from being
measured as a property of the recorder. §12.11 —
*"Nothing that authorises a change to money-touching code"* — constrains what a
result may authorise, and is honoured in §8 below.

**(b) `manual-orders-audit` is an instrument, and its prohibition is absolute.**
`tests/test_inspect_live_db.py::TestTheHandBetAuditCannotLeakAResult` names
`fills` in `FORBIDDEN_TABLES` and asserts
`tables <= {"manual_orders", "vocabulary"}` over every section's SQL. **This
measurement may not be implemented by adding a join to that query.** That would
be a test failure and the test is correct: the audit's whole value is that
obtaining the census cannot also obtain the answer.

**Precedent for the legal form.**
`docs/measurements/2026-09-09-fee-alarm-replayed-over-every-hand-fill.md` read
`fills` over 97 hand fills — prices, fees, per-prefix — through a separate named
harness (`scripts/replay_fee_reconciliation.py`) carrying its own
"what this does not establish" docstring, with a dated measurement document.
That route is adopted here unchanged.

---

## 1. THE POWER REALITY — and it changes the design

### 1.1 The population is a handful, and that is knowable without reading it

From facts already on the record, not from a query:

- `docs/decisions/2026-09-02-ticket-12-research-packet.md`: `manual-orders-audit`
  reported **0 rows lifetime** on `manual_orders` on 2026-09-02.
- CLAUDE.md: *"First two real fills 2026-09-08 (KXMVE combos, shard 1,
  ADR 0113)."*

So the population — non-dry-run `manual_orders` rows carrying a
`kalshi_order_id` that joins to a `fills` row — is **at least 2 and covers at
most three days of betting**. It is a handful.

### 1.2 Verdict: valid as a census, incapable as an estimate

**Exhaustive, therefore not underpowered.** Every row in the population is read;
there is no sampling, no null and no standard error. This is the same argument
the `clv-coverage` and `manual-orders-audit` exemptions in
`scripts/inspect_live_db.py` already rest on, and the same one
`2026-09-09-fee-alarm-replayed-over-every-hand-fill.md` used for
*"This is a census, not an estimate."*

**Incapable of any rate, mean or extrapolation.** At this `n` nothing may be
said about how often the recorder is wrong, by how much it is typically wrong,
or what the next hundred fills will do. The discrepancy is a property of the
book at one instant on one ticker. **No proportion, no mean, no sd, no interval
and no "rate of price improvement" may appear in the write-up**, and none is
computed.

### 1.3 The confound that would otherwise be discovered afterwards

Registered now, because it is the caveat a post-hoc write-up would omit.

Both known fills are `KXMVECROSSCATEGORY-SHARD1` combinations. On a KXMVE book
this repo has read 40 of, `yes_dollars` was empty on 40 of 40 and 33 carried a
single resting NO bid (`tests/test_combo_book_depth_claims.py`). **Where one
price is resting, an IOC buy has no room to improve and a zero discrepancy is
near-mechanical.** A run of zeros on the combo stratum is therefore *weak to no
evidence that the recorder is accurate*, and may not be reported as if it were.
It is evidence about book depth, which is already known.

This is the reason §2 strata are fixed in advance and reported separately even
at `n = 1` per stratum.

---

## 2. The claim, as something that could be false

**H1 (the falsifiable one).** For every row in the population,
`manual_orders.fill_price_tenths >= fills.price_tenths` for a buy of that side.

**Direction: one-sided, and the direction is derived, not chosen.**
`OrderOutcome.fill_price_tenths` (`backend/kalshi/orders.py:298-304`) is the
*price being sent* — the snapped limit, reflected onto the side taken — not a
venue report. An immediate-or-cancel limit buy cannot fill above its limit. So
`recorded >= actual` is expected on every row **provided** two things hold:
(i) the order really is submitted IOC at that limit, and (ii) the side
reflection in `yes_book_price_tenths` is right.

**A row where `recorded < actual` falsifies one of those provisions and is the
single most informative outcome this measurement can produce.** It is not a
rounding curiosity; it means either the venue filled above a limit or the code
books the wrong side of the book. It is registered here as the finding it would
be, so that it cannot later be filed as noise.

**H2 (descriptive, no test).** The count of rows where
`recorded != actual`, reported as a raw count with its denominator.

The word **exact** is deliberately not used anywhere in this document about the
hedge lock. See §7.

---

## 3. Population and exclusions

**Population.**

```
manual_orders rows where
    dry_run = 0
AND kalshi_order_id IS NOT NULL
AND EXISTS a fills row with fills.venue_order_id = manual_orders.kalshi_order_id
```

| # | Exclusion | Why it is independent of the quantity measured |
|---|---|---|
| X1 | `dry_run = 1` | A rehearsal sent nothing to the venue, so there is no charge to compare against. Flag set before the request left. |
| X2 | `kalshi_order_id IS NULL` | The venue never acknowledged an order. There is no join key and no charge. |
| X3 | No matching `fills` row | **Reported as a count, never silently dropped.** Two causes are indistinguishable here and both are stated: the order did not fill, or the fill fell outside the poller's window. The count is printed as `unjoined` beside every figure. |

**No exclusion references the discrepancy, its size, or its sign.** There is no
rule below that removes a row for being surprising.

**X3 has a pre-declared refusal branch, on the combo-experiment precedent.** If
`unjoined` exceeds the joined count, the join is not a measurement of the
recorder — it is a measurement of poller coverage — and **the write-up reports
the coverage fraction and stops, computing no discrepancy at all.** The trigger
is a row count and is fixed here so activating it is a rule, not a judgement.

**Where several fills answer one order** (`fill_count > 1`), the comparison is
against the **count-weighted mean** of `fills.price_tenths` for that
`venue_order_id`, and the row is flagged `multi_fill = 1`. The 2026-09-09 replay
found one fill per order on all 97 rows it saw; that is not assumed here.

---

## 4. Unit of observation and clustering

**The unit is the ORDER** (one `manual_orders` row / one `kalshi_order_id`), not
the fill and not the game.

**No clustering variable is defined and none is needed, because no standard
error is computed anywhere in this measurement.** Clustering exists to stop `n`
being inflated inside a variance estimate; there is no variance estimate here.
Stating this explicitly rather than leaving it out, because a later reader
finding no cluster key must be able to tell a decision from an omission.

Rows-per-order and orders-per-ticker are both printed, so a population that is
one ticker repeated is visible rather than pooled.

---

## 5. The cut — strata fixed in advance

Two strata, and no others. Adding a third requires a dated amendment.

```
S1   KXMVE* tickers        (combinations — the enter-only, thin-book stratum)
S2   every other ticker    (single markets)
```

Membership is decided by the ticker string, which is fixed before any price is
read. The split is inherited from the 2026-08-29 registration's X4 and exists
for the reason §1.3 gives: a zero in S1 and a zero in S2 do not mean the same
thing.

**No bucketing by price paid, and this is a deliberate departure.** CLAUDE.md's
rule is to bucket by the derived ask rather than the mid; here the derived ask
*is the quantity under test*, so bucketing on it would condition the measurement
on the number being audited. Both prices are reported per row (§6); neither is
an axis.

---

## 6. The statistic, named as an estimator — and there is none

**No estimator is used.** The reported quantities are, per stratum:

| quantity | form |
|---|---|
| `n_joined`, `n_unjoined` | raw counts |
| `n_equal`, `n_recorded_above`, `n_recorded_below` | raw counts, summing to `n_joined` |
| `max_abs_discrepancy_tenths` | one integer, the maximum over rows |
| `sum_abs_discrepancy_tenths` | one integer |

`sum` and `max` are the only arithmetic, matching the bound
`scripts/inspect_live_db.py`'s docstring already places on this class of query:
*"`SUM(cost)` and `MIN`/`MAX` are otherwise the only arithmetic, and they exist
to bound a search, not to support a conclusion."*

**No mean, no proportion, no sd, no interval, no p-value, at any `n`, ever.**
`sum / n` is a mean and is not printed. `n_equal / n_joined` is a rate and is not
printed.

### 6.1 The form of the output — the condition adopted

**A per-row table is permitted, and is ordered by `submitted_ms` ascending and
by nothing else — ever.** No ordering by discrepancy size, no maximum-row
callout, no "the worst fill", no top-N. This is inherited verbatim in intent
from the 2026-08-29 registration §8.3: *"a top-5 is an ordering and the
maximally selected sample, and it is the single most likely place a flattering
story would get told."*

**Permitted columns, and this list is exhaustive:** `submitted_ms`, `ticker`,
`side`, `count`, `recorded_tenths`, `actual_tenths`, `discrepancy_tenths`,
`multi_fill`, stratum.

**Forbidden in the output, per the 2026-08-29 registration:** `p_yes_bp`, any
`venue_settlements` or `closing_lines` column, any settled outcome, any `clv_*`
column, any realised P&L, any win/loss marker. The ticker is permitted because
it is already published per-prefix in the 2026-09-09 fee replay and because the
stratum split is unreadable without it; **the ticker may not be joined onward to
an outcome in this write-up or any successor that cites it.**

---

## 7. What is at stake, stated at its real size

`backend/core/hedge.py` computes `lock = W - S - W*q - fee`, where `S` is the
recorded stake. `_record_combo_position` (`backend/api/routes.py:3959`) writes
`fill_price_tenths=order.fill_price_tenths` — the sent limit — and
`stake_tenths = contracts * fill_price_tenths` (`:4318`). So under H1 the
recorded stake is **at or above** the true stake, and the reported lock is at or
**below** the true lock.

**The error runs in the cautious direction and this is a wording correction, not
a defect in the money path.** No figure shown to Joe is optimistic because of
it. It is registered at that size here so that a non-zero result cannot be
written up as a scandal, and a zero result cannot be written up as a
vindication of a word that is wrong regardless (§8.1).

CLAUDE.md's `/hedge` paragraph currently reads *"with one leg live the lock is
exact"*. `backend/core/hedge.py`'s own docstring already contradicts the word on
a **second, independent** ground that this measurement does not touch:

> **That the guarantee is exact.** Every figure here charges the *entry* fee
> only. Whether Kalshi also charges at settlement is H4, and H4 is untested
> (ADR 0027) — so a locked figure is an **upper bound**, and callers must say so.

---

## 8. The decision rule, verbatim

> **8.1 The CLAUDE.md wording correction is UNCONDITIONAL and does not depend on
> this measurement.** `manual_orders.fill_price_tenths` is the sent limit
> (`backend/kalshi/orders.py:298-304`) and not a venue report; `record_outcome`
> (`backend/store/manual_orders.py:765-788`) writes `status`,
> `kalshi_order_id` and `error_text` and drops `average_fill_price_dollars`,
> `average_fee_paid_dollars` and `fill_count`. Both are facts about source, not
> about data. Together with `hedge.py`'s own H4 caveat they are already
> sufficient: **the word "exact" in CLAUDE.md's `/hedge` paragraph is wrong and
> is corrected whatever this measurement returns, including if it is never
> run.** A result of "every row matched" does not restore the word.
>
> **8.2 Schema v39 is decided on retention, not on discrepancy size, and the
> rule is fixed here.** `backend/store/schema.sql:1698-1711` records that
> `/portfolio/fills` retains roughly three months and that
> `/portfolio/settlements` lost 55 records inside eight days. The ground truth
> this measurement joins to is **perishable**; `manual_orders` is permanent.
> Therefore: **persist the three dropped fields if and only if the venue's own
> price is judged worth keeping past the fills window** — an architectural
> question, answerable now, on which no number below is evidence.
>
> **No discrepancy magnitude triggers or blocks v39.** A threshold of the form
> "persist if the discrepancy exceeds X tenths" is refused at registration
> time, because at `n` of a handful (§1.2) any such threshold is a rule chosen
> against two to twenty numbers, and §1.3 gives a mechanical reason those
> numbers are likely to be uninformative in one stratum.
>
> **8.3 The one outcome that changes something else.** If any row shows
> `recorded_tenths < actual_tenths` (H1 falsified), the write-up leads with that
> row, and an ADR is opened on **one** question: whether the venue filled above
> a submitted limit, or whether `yes_book_price_tenths` books the wrong side.
> Nothing else in this measurement opens an ADR.
>
> **8.4 Nothing here moves money-touching code.** The gate stays where it is;
> `ORDERS_ARE_DRY_RUNS` stays True; no cap moves; no order path is altered on
> the strength of any number produced here. Persisting three columns is a
> recording change, and a recording change only.

**Multiplicity: `K = 0`.** No panel here carries a verdict, because §6 computes
no estimator. There is nothing to correct. Adding one requires a dated
amendment that states its null before it is computed once.

---

## 9. The stopping rule

**One look, on the population as it stands at the moment of the query, and the
snapshot instant is printed beside every count.** This is not a monitor and it
does not accrue.

**Re-running it later is a new look and requires a dated amendment recording
that the first look was seen.** Stated because §8's decision rule is
unconditional in both branches, so there is no configuration of the data that
makes a second look attractive — and that property is exactly what is lost if a
second look is taken casually.

**Live-read constraint.** The query is row-bounded to the population in §3. A
full-table read on live evicts the page cache and costs the desk ~75s
afterwards; the join must not scan `fills` unbounded.

---

## 10. What would falsify this, and where the negative goes

**Destination, fixed now:**
`docs/measurements/2026-09-10-recorded-fill-vs-venue-charge-result.md`, written
whichever way it comes out, in the same commit as the CLAUDE.md wording
correction, and linked from `tasks/NEXT.md`.

| outcome | what is written | what is built | what is killed |
|---|---|---|---|
| every joined row equal | The counts, with §1.3's confound stated **first**, not last | Nothing | Nothing. The word "exact" is still corrected (§8.1). |
| some rows `recorded > actual` | The counts and the per-row table, time-ordered | Nothing on this evidence; v39 stands or falls on §8.2 | Nothing |
| any row `recorded < actual` | That row first | An ADR on the two candidate causes (§8.3) | Nothing until the ADR |
| `unjoined > joined` | Coverage fraction only; no discrepancy computed (X3) | Nothing | The measurement itself, this run |

**We proceed either way on the two things that prompted this.** The wording fix
happens regardless; v39 is decided on retention regardless. **This measurement
is therefore not decision-relevant in the inferential sense, and that is
recorded here rather than discovered afterwards.** What it buys is a fact about
the recorder that nothing else on disk states, obtained cheaply, before the
`fills` window drops the evidence. That is a legitimate reason to run it and it
is not the same reason as "it will tell us what to do".

---

## 11. WHAT THIS DOES NOT ESTABLISH

Drafted before the run.

1. **Nothing about whether Joe has an edge, won, or lost.** No settlement, no
   closing line, no P&L, no win rate is read or derivable from any output
   permitted by §6.1.
2. **Nothing about the rate at which the recorder is wrong.** §1.2. There is no
   denominator here that generalises past the rows read.
3. **Nothing about future fills.** The discrepancy is a property of one book at
   one instant. A thin-book stratum cannot speak for a deep one.
4. **A zero in the combo stratum is close to mechanical** (§1.3) and is not
   evidence the recorder is accurate.
5. **Nothing about fees.** `average_fee_paid_dollars` is dropped by the same
   line of code, and the fee question was measured separately on 2026-09-09.
   This measurement does not re-open, extend, or corroborate it.
6. **Nothing about orders that never filled.** They carry no venue price. X3
   counts them and stops.
7. **Nothing about the completeness of `fills`.** It mirrors an endpoint
   observed to drop history (schema.sql:1698-1711). An absent fill is not a
   fill that did not happen.
8. **Nothing about whether the hedge lock is correct.** `hedge.py`'s H4 caveat
   is untested and independent of everything here; a corrected stake basis would
   still leave the lock an upper bound.
9. **Nothing that authorises a change to money-touching code** (§8.4), inherited
   verbatim from the 2026-08-29 registration §12.11.

---

## 12. Status

**READY as a census. NOT AN ESTIMATE at any `n` this population will reach.**

Every section is fixed. Nothing was left open on the grounds that we would see
what the data looks like. The decision rule in §8 is unconditional in both
branches by design, which is what makes running the query safe.

This file must be committed before the join is executed. Amendments are additive
and dated, never edits.
