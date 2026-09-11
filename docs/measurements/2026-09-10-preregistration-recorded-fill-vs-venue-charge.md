# Pre-registration — does the recorded hand-bet price equal the price Kalshi charged?

Written **2026-09-10**, before any row of the join has been read.

**Amended 2026-09-11 — see Amendment 1 at the foot of this file.** The
preamble, the title, §0.1, §1.1, §2, §3 (X3), §6, §6.1, §7, §8.1, §8.2, §9 and
§11 (items 2, 5 and 8) are superseded where Amendment 1 says so, and nowhere
else. Every other section stands as written.

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

---

# Amendment 1 — 2026-09-11 — the recorded column holds the ask we SENT, and one arm of the registered decision has already been taken

**Additive and dated, per §12. Nothing above is edited except the one pointer
line under the title.** Every sentence this amendment supersedes is reproduced
verbatim beside its correction, so the pre-fix text stays readable as what was
actually registered on 2026-09-10.

## A0. Standing — this amendment was written blind

**Read while writing it:** `backend/kalshi/orders.py` (the whole of
`OrderRequest`'s property block at `:285-325` and the whole of `OrderOutcome`
at `:387-410`, plus `_read_response` at `:517-566`),
`backend/store/manual_orders.py` (`_insert_intent` `:615-660`, the
"What the VENUE said it did" block and `record_outcome`),
`backend/store/db.py` (`SCHEMA_VERSION`, `_MIGRATIONS[39]`, `_MIGRATIONS[40]`),
`backend/store/schema.sql` (the `manual_orders` and `fills` blocks),
`backend/portfolio_poll.parse_fill`, `backend/api/routes.py:3944-3968` and
`:4275-4325`, `backend/core/hedge.py:200-320`,
`tests/fixtures/create_order_responses.json`, ADR 0143, and this file.

**Still not seen, not queried, not requested:** any value of
`manual_orders.limit_price_tenths`, any value of
`manual_orders.venue_avg_fill_price_tenths`, any value of
`fills.price_tenths`, any difference between any two of them, the row count of
the join, and any P&L, settlement, win rate, CLV or typed estimate on any hand
bet. The §0.1 blindness declaration is **extended, not relaxed**: the two
columns that did not exist when it was written are added to the not-seen list
by name.

**One number on the record changed and it was not obtained by a query.** §1.1
reasoned to "at least 2" from CLAUDE.md's "first two real fills 2026-09-08".
CLAUDE.md now reads **four by 2026-09-09** (ADR 0129). §1.1's floor becomes
**at least 4**; its verdict — a handful, valid as a census, incapable as an
estimate — is unchanged, and §1.2 stands byte-for-byte.

---

## A1. The three citation errors, quoted and corrected

### A1.1 There is no `manual_orders.fill_price_tenths`

§0.1 registered, under "Not seen":

> any value of
> `manual_orders.fill_price_tenths`, any value of `fills.price_tenths`, any
> difference between them, the row count of the join

and §2 registered:

> **H1 (the falsifiable one).** For every row in the population,
> `manual_orders.fill_price_tenths >= fills.price_tenths` for a buy of that side.

and §8.1 registered:

> `manual_orders.fill_price_tenths` is the sent limit
> (`backend/kalshi/orders.py:298-304`) and not a venue report

**No such column exists and none ever did.** The column is
**`manual_orders.limit_price_tenths`** (`backend/store/schema.sql`, the
`manual_orders` block: *"The price for OUR side, snapped — same convention and
same reasoning as `orders.limit_price_tenths`"*). It is written at **intent**
time by `_insert_intent` (`backend/store/manual_orders.py:649`) from
`OrderRequest.fill_price_tenths`, before the request leaves the process, under
`reserve_manual_order`'s reserve-then-check.

### A1.2 The property is on `OrderRequest`, not `OrderOutcome`

§0.1 registered, under "Seen while writing this":

> `backend/kalshi/orders.py:285-320`
> (`OrderOutcome.fill_price_tenths`)

and §2 registered:

> `OrderOutcome.fill_price_tenths` (`backend/kalshi/orders.py:298-304`) is the
> *price being sent* — the snapped limit, reflected onto the side taken — not a
> venue report.

**The line range was right and the class name was wrong.** `orders.py:285-320`
is inside **`OrderRequest`**; `fill_price_tenths` is declared at `:299` (the
`@property` decorator is `:298`) and its own docstring reads *"What one
contract of **our** side costs at the price being sent."* `OrderOutcome` is a
different dataclass at `:387-408`, and it **has no `fill_price_tenths`
property** — it carries `fill_count`, `remaining_count`,
`average_fill_price_dollars` and `average_fee_paid_dollars`. Nothing the venue
returned was ever in the recorded column, and that is not an inference from
data: it is the absence of a line of code.

The parenthetical reasoning §2 attached to the wrong name — *"the price being
sent — the snapped limit, reflected onto the side taken — not a venue
report"* — was **correct about the quantity throughout**. Only the two names
were wrong. That is why A3 below is a renaming and not a new hypothesis.

### A1.3 The schema version is v40, and it has already shipped

The preamble registered:

> the *decision* attached to the result — persist three dropped
> fields as schema v39, or close the item — would otherwise be chosen after
> seeing two to twenty numbers, and that is the failure this document class
> prevents.

**v39 was taken by `idx_odds_event_commence`** (`backend/store/db.py`,
`_MIGRATIONS[39]`, an index step). The three fields were persisted as **schema
v40** on **2026-09-11** by **ADR 0143** — `venue_fill_count` (REAL),
`venue_avg_fill_price_tenths` (INTEGER tenths, via `dollars_to_tenths` then
`is_valid_price`, a parsed `0` refused rather than clamped) and
`venue_avg_fee_dollars` (REAL dollars, deliberately not tenths: the C0 capture
fee `"0.0014"` is 1.4 tenths and would be written as `1`).

**Read every occurrence of "v39" in the preamble and §8.2 as "v40".** The
substance of that arm is settled in A7.2 below.

### A1.4 What is NOT an error, recorded so it is not "fixed" later

§7's citation of `backend/api/routes.py:3959` for `_record_combo_position`
receiving `fill_price_tenths=order.fill_price_tenths`, and `:4318` for
`stake_tenths = contracts * fill_price_tenths`, are **both correct** and
verified at this commit. ADR 0143 §6 records the same. They stand.

### A1.5 Line numbers into `manual_orders.py` have moved, and names are authoritative

§0.1 and §8.1 cite `backend/store/manual_orders.py:765-788` for
`record_outcome`. That was accurate on 2026-09-10; v40 inserted a block above
it and the function now sits lower in the file. **Where a citation in this
document gives a file and a line, the file and the symbol name are the
authority and the line number is a convenience.** No line citation in this
document is re-audited by this amendment beyond the ones named above.

---

## A2. The question narrowed, and part of it is answered by the source

This file is titled *"does the recorded hand-bet price equal the price Kalshi
charged?"*

**On rows written before v40 — which is all four real fills to date — that
question is answered by reading the code, not by reading the data. The answer
is no, and it is not close: no venue number was ever written to the row.** A
census cannot add to that.

**The live question that remains, and the only empirical content this census
still has, is the falsification branch of H1**: *does the ask the desk sent
ever sit below the price the venue actually executed at?* That would mean
either the venue filled above a submitted limit or `yes_book_price_tenths`
books the wrong side of the book — both money-path facts, neither obtainable
from source alone.

The title is left as written, because amendments do not edit. It is wrong as a
description of what is being measured and this paragraph is the correction.

---

## A3. H1 — the same arithmetic, a corrected name, and a changed meaning

**The statistic is the same one.** The value the 2026-09-10 author believed
they were reading is bit-for-bit the value the corrected column holds: the
snapped ask for our side at the moment the request was built. The comparison,
its direction, and its falsifying outcome are unchanged. This is a renaming.

**What changes is what a non-zero difference means**, and that has to be fixed
before the run rather than narrated after it:

- Under the mistaken reading, `recorded != actual` would have been a **recorder
  defect** — the row failing to hold the number it was supposed to hold.
- Under the corrected reading, `sent > venue` is **price improvement on a
  marketable IOC limit order**, which is ordinary, expected, and not a defect
  of anything. It says the book was better than the ceiling we sent.

**Registered consequence:** the write-up may not describe `sent > venue` as the
recorder being wrong, at any count, and may not describe `sent == venue` on
every row as the recorder being right. Neither is a statement about the
recorder. The recorder's behaviour is already known from source (A1, A2).

**H1, as amended and now binding:**

> **H1 (Amendment 1).** For every row in the population (§A4),
> `manual_orders.limit_price_tenths >= V`, where `V` is the venue execution
> price for that order as defined in §A4.2.
>
> **Direction: one-sided, upward, and derived rather than chosen.** An
> immediate-or-cancel limit buy cannot fill above its limit. So `sent >= venue`
> is expected on every row **provided** two things hold: (i) the order really
> is submitted IOC at that limit, and (ii) the side reflection in
> `yes_book_price_tenths` is right.
>
> **A row where `sent < venue` falsifies one of those provisions and is the
> single most informative outcome this measurement can produce.** It is
> registered here as the finding it would be, so that it cannot later be filed
> as noise.

Clauses (i) and (ii) are §2's own two provisions, carried over unchanged in
substance. The one-sidedness is inherited and is not re-derived after the fact.

**This is a claim about the RECORDING — one contract's price on one row — and
about nothing else.** It is not a claim about the hedge figure. See A6.

**H2, as amended.** The count of rows where `sent != venue`, reported as a raw
count with its denominator, **and not called a discrepancy**. The word
`discrepancy` presumes a defect and is retired from this measurement; the
neutral term registered here is **`sent_minus_venue_tenths`**, signed, positive
meaning the venue charged less than the ceiling we sent.

**The word "exact" is still deliberately not used anywhere in this document
about the hedge lock.** §2's closing sentence stands.

---

## A4. The population, the join, and the split v40 created

### A4.1 The population shell — one clause changes

§3 registered:

```
manual_orders rows where
    dry_run = 0
AND kalshi_order_id IS NOT NULL
AND EXISTS a fills row with fills.venue_order_id = manual_orders.kalshi_order_id
```

**Amended to:**

```
manual_orders rows where
    dry_run = 0
AND kalshi_order_id IS NOT NULL
AND (
        EXISTS a fills row with fills.venue_order_id = manual_orders.kalshi_order_id
     OR manual_orders.venue_avg_fill_price_tenths IS NOT NULL
    )
```

X1 and X2 stand verbatim, with their stated reasons. Neither branch of the new
clause references the quantity measured: one is a join key's existence, the
other is the presence of a column written unconditionally by `record_outcome`
from whatever the venue returned.

### A4.2 `V` — which venue price, decided now and not at the keyboard

Rows written after 2026-09-11 can carry a venue price from **two different
endpoints**. They are not the same measurement and they are not pooled.

| `venue_source` | `V` is | when |
|---|---|---|
| `fills` | the count-weighted mean of `fills.price_tenths` over that `venue_order_id` | **PRIMARY.** Whenever the join returns at least one row. |
| `create_response` | `manual_orders.venue_avg_fill_price_tenths` | **FALLBACK.** Only when the join returns nothing and the column is non-NULL. |

**`fills` is primary, and the reason is a documented side convention rather
than a preference.** `portfolio_poll.parse_fill` reads `yes_price_dollars` or
`no_price_dollars` **by the fill's own `side`** — *"reading the wrong one books
a 1c fill as a 99c one"* — against a 25-fill capture of 2026-08-18 in which
every field was present on all 25. The create-order response's
`average_fill_price` was observed by the **C0 probe on one ticker, one day, one
series**, and the committed fixture
(`tests/fixtures/create_order_responses.json`) does not record the side of the
probe order. **Whether `average_fill_price` is quoted on our side or on the YES
book for a `side = 'no'` order is therefore assumed by `_venue_price_tenths`,
not verified.** Fixing the precedence now is the point: after seeing a number,
"use the other source" is a choice.

**Rows adjudicated on the fallback are flagged, counted, and reported
separately. They never enter the H1 counts.** With every current row predating
v40, H1 is adjudicated entirely on `fills` — the registered join in §3 is
**unchanged for the population as it stands**, and the fallback exists for the
run that happens after retention starts dropping the `fills` side.

**The multi-fill rule in §3 stands**: where `fill_count > 1` the `fills`-sourced
comparison is against the count-weighted mean and the row is flagged
`multi_fill = 1`. The `create_response` value is already volume-weighted and is
rounded half-up to the nearer tenth by `_venue_price_tenths`; that declared
half-tenth is not a finding.

### A4.3 The side-convention artifact, pre-declared

A row where `V` is approximately `1000 - sent` rather than approximately `sent`
is a **side-convention artifact and is NOT counted as H1 falsified.** The
trigger, fixed here: `abs(V - (1000 - sent)) <= 10` tenths **and**
`abs(V - sent) > 10` tenths. Such a row is reported as
`side_convention_ambiguous` with both numbers printed, and it opens the ADR in
A7.4 rather than the one in §8.3.

**This rule cannot separate the two readings near 500 tenths**, where
`1000 - sent` and `sent` coincide. That limitation is registered now rather
than discovered: a near-50c row can be classified neither way and is reported
as `side_convention_undecidable`.

### A4.4 X3, corrected for the fact that "unjoined" now has two meanings

§3 registered:

> | X3 | No matching `fills` row | **Reported as a count, never silently
> dropped.** Two causes are indistinguishable here and both are stated: the
> order did not fill, or the fill fell outside the poller's window. The count
> is printed as `unjoined` beside every figure. |

and:

> **X3 has a pre-declared refusal branch, on the combo-experiment precedent.**
> If `unjoined` exceeds the joined count, the join is not a measurement of the
> recorder — it is a measurement of poller coverage — and **the write-up
> reports the coverage fraction and stops, computing no discrepancy at all.**

**Amended.** `unjoined` is redefined as **rows passing X1 and X2 that carry no
venue price from either source**, and it is reported as three numbers, not one:

| count | meaning |
|---|---|
| `unjoined_zero_fill` | post-v40 rows with `venue_fill_count = 0.0`: the IOC matched no one. **Not a coverage failure.** There is nothing to compare and never will be. |
| `unjoined_unknown` | every other row with no venue price — a pre-v40 row the poller never joined, or a post-v40 row whose outcome was never read. The two causes §3 called indistinguishable, still indistinguishable on pre-v40 rows. |
| `n_joined` | rows carrying a `V` from either source |

**The refusal branch fires on `unjoined_unknown > n_joined`, not on the old
pooled `unjoined`.** Rationale, fixed in advance: a known zero fill is the
venue telling us plainly that nothing was bought, which is information, not a
gap in poller coverage. Everything else about the branch — that it is a row
count, that activating it is a rule and not a judgement, and that the write-up
then reports the coverage fraction and computes no comparison at all — stands
verbatim.

**No exclusion added by this amendment references the difference, its size, or
its sign.**

---

## A5. Strata and output form

**§5 stands.** Two strata, `S1 = KXMVE*` and `S2 = everything else`, decided by
the ticker string. `venue_source` is **not** a third stratum and is **not**
crossed with S1/S2: at this `n`, four cells would be cell-shopping. It is a
per-row column and a set of counts reported alongside, exactly as `multi_fill`
is.

**§1.3's confound is strengthened by the corrected reading, not weakened.** On
a KXMVE book where one price is resting, an IOC buy at that level has no room
to improve, so `sent == venue` is near-mechanical. Under the corrected reading
that is not even weak evidence about a recorder — it is a statement about book
depth, which is already known. It is reported **first** in the S1 stratum,
before any count.

**§6's permitted columns are renamed, and the list stays exhaustive:**

| §6 / §6.1 as registered | as amended |
|---|---|
| `recorded_tenths` | `sent_tenths` |
| `actual_tenths` | `venue_tenths` |
| `discrepancy_tenths` | `sent_minus_venue_tenths` (signed) |
| `n_recorded_above`, `n_recorded_below` | `n_sent_above`, `n_sent_below` |
| `max_abs_discrepancy_tenths`, `sum_abs_discrepancy_tenths` | `max_abs_sent_minus_venue_tenths`, `sum_abs_sent_minus_venue_tenths` |
| — | `venue_source` (new column, per row and as counts) |

`submitted_ms`, `ticker`, `side`, `count`, `multi_fill`, stratum and `n_equal`
are unchanged. **Everything else in §6 and §6.1 stands byte-for-byte**: no
mean, no proportion, no sd, no interval, no p-value, at any `n`, ever;
`sum / n` is a mean and is not printed; `n_equal / n_joined` is a rate and is
not printed; the per-row table is ordered by `submitted_ms` ascending and by
nothing else, ever; no top-N, no "worst fill", no maximum-row callout. The
forbidden-column list (`p_yes_bp`, any settlement, closing line, `clv_*`,
realised P&L, win/loss marker) is unchanged, and the ticker still may not be
joined onward to an outcome.

**`venue_avg_fee_dollars` is NOT read by this measurement.** It now exists on
the row; reading it would re-open the fee question, which was measured
separately on 2026-09-09. It is added to the forbidden list.

**§4 stands byte-for-byte.** The unit is the ORDER; no clustering variable is
defined because no standard error is computed anywhere in this measurement.

---

## A6. §7 — the hedge figure carries at least four error terms, and this census pins one

§7 registered:

> So under H1 the
> recorded stake is **at or above** the true stake, and the reported lock is at
> or **below** the true lock.
>
> **The error runs in the cautious direction and this is a wording correction,
> not a defect in the money path.** No figure shown to Joe is optimistic
> because of it.

and §11.8 registered:

> **Nothing about whether the hedge lock is correct.** `hedge.py`'s H4 caveat
> is untested and independent of everything here; a corrected stake basis would
> still leave the lock an upper bound.

**Those two sentences contradict each other and neither is established.** A
skeptic audit on 2026-09-11 read `backend/core/hedge.py` and
`backend/api/routes.py` against them and found **at least four error terms in
the displayed figure, pointing in both directions.** They are listed here,
before the run, because a caveat drafted after a result is selected to be
survivable.

| # | term | direction of the displayed floor | size | measured by this census? |
|---|---|---|---|---|
| E1 | **H4 settlement fee.** Every figure charges the *entry* fee only; whether Kalshi also charges at settlement is untested (ADR 0027, `core/hedge.py:43-45`). | too **HIGH** | unknown, unverified | **No** |
| E2 | **Intent vs execution.** `stake_tenths` uses the ask we sent, which under H1 is at or above what the venue charged. | too **LOW** | 0–10 tenths per contract; ~0 on a one-level book | **Yes — this is the only term the census touches** |
| E3 | **The entry fee is missing from the stake.** `stake_tenths = contracts * fill_price_tenths` (`routes.py:4318`) is **price only**, while `Rung`'s branches are defined net of the sunk stake (`core/hedge.py:218-226`). The taker fee Joe actually paid at entry is in neither. So recorded `S` < true `S`. | too **HIGH** | ~17 tenths per contract at 41c — **larger than E2's maximum** | **No** |
| E4 | **The hedge's own fee is charged at the flat 0.070.** `_fee_tenths` deliberately refuses the per-series multiplier (ADR 0058) and rounds up, against a measured `k` of about 0.035 on baseball. | too **LOW** | up to ~half the hedge fee | **No** |

**Consequences, registered:**

1. **H1's direction stands, unchanged, as a claim about the RECORDING.**
   `sent >= venue` per contract on one row is exactly E2 and nothing more. That
   is what the census tests and it is a real, falsifiable, one-sided claim.
2. **No one-sided claim about the displayed hedge FIGURE follows from it, and
   none is made here.** E3 alone is larger than E2's maximum and runs the other
   way, so §7's *"the reported lock is at or below the true lock"* and §11.8's
   *"would still leave the lock an upper bound"* are **both withdrawn as
   unestablished**. The net direction of the `/hedge` figure is **unknown**, and
   this document must not be quoted as bounding it either way.
3. **§7's sentence *"No figure shown to Joe is optimistic because of it"* is
   withdrawn.** What survives is the strictly narrower statement:
   **the stake's price factor alone is not optimistic.** E1 and E3 are both
   optimistic and neither is measured here.
4. **The count factor is not covered either.** `_record_combo_position` is sized
   from `int(outcome.fill_count)` (`routes.py:3952-3957`) — the venue's own
   count, truncated — which scales `stake_tenths` and `return_tenths` together.
   Its effect on the floor is **not ruled on here**.
5. **E1, E3 and E4 are out of scope and stay out of scope.** They are named so
   that the census's silence about them is a registered limit rather than an
   omission a reader has to notice. E3 in particular is a candidate defect in
   the money path, found by source reading rather than by data, and it needs its
   own decision; **this measurement does not open it, does not price it, and
   supplies no evidence about it.** §8.4 forbids this census from moving
   money-touching code and that is unchanged.

**The quantifier weakening, stated plainly.** Even E2 is *conditional*, not
true "by construction": it holds provided H1's provisions (i) and (ii) hold,
and testing those provisions is the entire remaining content of this census.
The cautious direction of E2 is therefore **the registered expectation, not a
known fact**, and a falsifying row overturns it.

---

## A7. The decision rule as it now stands

§8.4 stands **byte-for-byte** and is repeated because it governs everything
below: *"Nothing here moves money-touching code. The gate stays where it is;
`ORDERS_ARE_DRY_RUNS` stays True; no cap moves; no order path is altered on the
strength of any number produced here."*

### A7.1 §8.1 — executed, and its conclusion survives its own obsolescence

§8.1 registered:

> `record_outcome`
> (`backend/store/manual_orders.py:765-788`) writes `status`,
> `kalshi_order_id` and `error_text` and drops `average_fill_price_dollars`,
> `average_fee_paid_dollars` and `fill_count`.

**That sentence became false on 2026-09-11.** `record_outcome` now also stamps
the three v40 columns through `venue_fill`. **§8.1's conclusion is
unaffected**, for reasons that have nothing to do with the drop:
`limit_price_tenths` is still the sent ask, `/hedge` still reads
`parlay_positions.stake_tenths` computed from the sent ask (ADR 0143 §4
declined to rewire it), H4 is still untested, and A6 has since added two more
error terms. The CLAUDE.md wording correction was unconditional, did not wait
for this census, and **has been made** — the spine's `/hedge` paragraph now
reads *"an upper bound, not an exact lock"*. Nothing this census returns
restores the word **exact**; and per A6 the phrase **upper bound** is itself
now only as good as E1 and E3, which no measurement here bounds.

### A7.2 §8.2 — spent. The persistence arm is decided and shipped.

§8.2 registered:

> **persist the three dropped fields if and only if the venue's own price is
> judged worth keeping past the fills window** — an architectural question,
> answerable now, on which no number below is evidence.

**That rule was followed to the letter and the answer was yes.** ADR 0143 took
it on 2026-09-11 on the unconditional perishability ground — `fills` is
retention-eligible on ~3 months, `manual_orders` is permanent — with the census
unrun and no value of any column read. §8.2's own sentence *"No discrepancy
magnitude triggers or blocks v39"* was honoured because there was no magnitude.

**Registered consequence, new and binding:** the census **may not be cited as
evidence for or against ADR 0143, in either direction**. If every row matches,
0143 is not thereby vindicated. If rows differ, 0143 is not thereby vindicated
either. It was decided on retention, before the look, which is the whole reason
the look stays safe to take.

### A7.3 §8.3 — stands, restated in the corrected names

> **If any row shows `sent_tenths < venue_tenths` (H1 falsified), and the row is
> not classified `side_convention_ambiguous` or `side_convention_undecidable`
> by §A4.3, the write-up leads with that row, and an ADR is opened on ONE
> question: whether the venue filled above a submitted limit, or whether
> `yes_book_price_tenths` books the wrong side.**

### A7.4 New: the two endpoints disagreeing about one order

For any row carrying **both** a `fills`-sourced and a `create_response`-sourced
venue price, the two are printed side by side and the count of disagreements is
reported. Fixed threshold, chosen from the declared rounding and not from data:

> **A disagreement of more than 1 tenth on any such row opens ONE ADR on ONE
> question: which of the two readers has the side or rounding convention wrong.
> A disagreement of 1 tenth or less is the half-up rounding
> `_venue_price_tenths` already declares, and opens nothing.**

**Nothing else in this measurement opens an ADR.** §8.3's closing sentence is
extended by exactly this one branch and by nothing else. In particular, **E3
does not open one from here** (A6.5).

### A7.5 What the census still buys, stated against interest

§10 registered:

> **We proceed either way on the two things that prompted this.** The wording
> fix happens regardless; v39 is decided on retention regardless. **This
> measurement is therefore not decision-relevant in the inferential sense, and
> that is recorded here rather than discovered afterwards.**

**That is now more true than when it was written, not less.** Both prompting
decisions are *taken*: the wording fix is in the spine and the persistence arm
shipped as v40. What remains is one falsifiable claim (H1) whose falsification
would be a money-path defect obtainable no other way, plus a fact about the
recorder captured before retention drops the evidence.

**That is a real but small purchase, and it is smaller than it was on
2026-09-10.** Closing the item unrun is a defensible call and this amendment
does not pre-empt it; what it does prevent is the item being closed *after* a
glance at the numbers. **Multiplicity is still `K = 0`** — §6 computes no
estimator and no panel here carries a verdict.

---

## A8. The stopping rule — a corner §9 left open, fixed here, blind

§9 registered:

> **One look, on the population as it stands at the moment of the query, and
> the snapshot instant is printed beside every count.** This is not a monitor
> and it does not accrue.

That fixes the number of looks and says nothing about **when**. With rows
arriving as Joe bets, an unspecified instant means whoever runs the query
chooses the population — the same freedom this document class exists to remove.
Fixed now, before any row is read:

> **The one look is taken at the first session after the population reaches 10
> real manual orders (`dry_run = 0` and `kalshi_order_id IS NOT NULL`), or on
> 2026-11-01, whichever comes first. It is a single look at that instant, and
> the snapshot instant is printed beside every count.**

Three properties of that trigger, stated because they are what make it a rule:

- **The trigger is independent of the quantity measured.** It counts orders, not
  prices, differences or signs.
- **It is observable without seeing the answer.** The count comes from
  `manual-orders-audit`, whose test
  (`tests/test_inspect_live_db.py::TestTheHandBetAuditCannotLeakAResult`)
  names `fills` in `FORBIDDEN_TABLES` and asserts
  `tables <= {"manual_orders", "vocabulary"}`. Checking whether the trigger has
  fired therefore cannot reveal the comparison. §0.2(b)'s absolute prohibition
  on implementing this measurement by adding a join to that query stands
  untouched.
- **The 2026-11-01 backstop is derived, not picked.** The first real fills
  landed 2026-09-08 and `fills` is retention-eligible at roughly three months,
  so the venue side of those rows starts disappearing around 2026-12-08.
  2026-11-01 leaves about five weeks of margin, and the fallback in §A4.2 only
  helps rows written after v40 — the four rows that exist have no second source
  and never will.

**§9's remaining clauses stand verbatim**: re-running later is a new look and
requires a dated amendment recording that the first look was seen; the query is
row-bounded to the population in §3 as amended; the join must not scan `fills`
unbounded, because a full-table read on live evicts the page cache and costs the
desk ~75s afterwards.

---

## A9. §11 — three caveats corrected, four added

§11.5 registered:

> **Nothing about fees.** `average_fee_paid_dollars` is dropped by the same
> line of code, and the fee question was measured separately on 2026-09-09.

**The premise is now false and the caveat is stronger without it.** Since v40
the fee *is* recorded, in `venue_avg_fee_dollars`. This measurement still says
nothing about fees, for a better reason: **it does not read that column, and
§A5 forbids it.**

**§11.8 is withdrawn and replaced** (A6.2). *"A corrected stake basis would
still leave the lock an upper bound"* is not established: E3 runs the other way
and is larger than E2's maximum. The replacement caveat is: **nothing about
whether the hedge lock is correct, and nothing about which direction it errs
in.**

**§11.2 is sharpened.** "Nothing about the rate at which the recorder is wrong"
becomes: **nothing about a rate of anything, and in particular the recorder is
not what is under test** — pre-v40 it never held a venue price at all, which is
a source fact (A1, A2) rather than a measured one.

Added, drafted before the run:

10. **Nothing about which of the two venue-price sources is correct**, except in
    the one branch A7.4 opens. `fills` is primary by a documented side
    convention, not by having been shown to be right.
11. **Nothing about the side convention of `average_fill_price` for a
    `side = 'no'` order.** The committed fixture is one ticker, one day, one
    series, and does not record the probe's side. A4.3 classifies the artifact;
    it does not resolve it.
12. **Nothing about E1, E3 or E4** (A6). The census pins E2 and only E2. It
    supplies no evidence about the settlement charge, about the entry fee's
    absence from `stake_tenths`, or about the flat-0.070 hedge fee.
13. **Nothing about the contract-count factor** of the stake
    (`int(outcome.fill_count)`), which this amendment names and does not rule on.

**§11.1, §11.3, §11.4, §11.6, §11.7 and §11.9 stand byte-for-byte**, including
§11.9's inherited *"Nothing that authorises a change to money-touching code."*

---

## A10. What this amendment does NOT change

Exhaustively, by section:

- **§0.2** — both prohibitions, their scopes, the §6f reading, the absolute ban
  on implementing this via `manual-orders-audit`, and the
  `2026-09-09-fee-alarm-replayed-over-every-hand-fill.md` precedent of a
  separate named harness with its own "what this does not establish" docstring.
  **Untouched.**
- **§1.1** — the reasoning; only the floor moves from 2 to 4, from a record
  fact, not a query.
- **§1.2** — valid as a census, incapable as an estimate. No proportion, no
  mean, no sd, no interval, no rate, at any `n`. **Byte-for-byte.**
- **§1.3** — the thin-book confound, reported first in S1. Strengthened, not
  altered.
- **§3** — X1, X2, the "no exclusion references the quantity" guarantee, and the
  multi-fill rule. Only the EXISTS clause and X3's definition move.
- **§4** — the unit is the ORDER; no clustering variable, and why.
  **Byte-for-byte.**
- **§5** — two strata and no others; no bucketing by price paid, and the reason
  (the price paid is the quantity under test). **Byte-for-byte.**
- **§6 / §6.1** — every prohibition, the exhaustive column list, the ordering
  rule. Only the six column names change, and one column is added.
- **§8.4** — **byte-for-byte.**
- **§10** — the destination,
  `docs/measurements/2026-09-10-recorded-fill-vs-venue-charge-result.md`,
  written whichever way it comes out, linked from `tasks/NEXT.md`. The outcome
  table stands with the corrected names substituted; its v39 cell reads v40 and
  is already decided (A7.2).
- **§12** — amendments are additive and dated, never edits. This is one.

---

## A11. Status after Amendment 1

**READY as a census, on the corrected names, with the stopping rule now fixed.
NOT AN ESTIMATE at any `n` this population will reach.**

The decision rule, quotable verbatim for checking against the eventual
write-up, is **§8.4 unchanged**, plus **A7.3** and **A7.4**, and nothing else
opens an ADR. §8.1 and §8.2 are both **spent**: they were unconditional, and
both have been executed before the look — which is why taking the look is still
safe.

**Two honest headlines, both against interest.** First, this measurement is now
less decision-relevant than when it was registered, because one of the two
decisions it was attached to has been taken on its own unconditional ground.
Second, it pins **one of at least four** error terms in the `/hedge` figure
(A6), and not the largest one — so nothing it returns licenses a statement
about whether the number Joe sees is high or low. Both recorded before the run
rather than discovered after it.
