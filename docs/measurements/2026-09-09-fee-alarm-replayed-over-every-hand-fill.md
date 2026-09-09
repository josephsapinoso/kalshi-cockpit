# The fee alarm, replayed over the stored hand fills — 2026-09-09

**Question.** The fee-mismatch alarm was wired on 2026-09-09 (ADR 0123) and had
never run against a live fill. Its whole design rests on staying quiet — it is
one-sided precisely so it does not fire on the deliberate MLB overstatement
(ADR 0058), and this repo has a 36-red-push scar about a check that is always
red. So: replay the **shipped** reconciliation over every hand fill the live
instance holds, and count what it would have done.

**Harness:** `scripts/replay_fee_reconciliation.py`, committed, with its own
"what this does not establish" docstring. It imports `predict_fill_fee` and
`reconcile_fill` from `backend.portfolio_poll` rather than reimplementing the
comparison. Read-only; no Kalshi call, no Anthropic call, no odds credits, no
writes.

> **This document was rewritten after audit.** Its first draft reported
> "0 of 96" and claimed `calculate_fee`'s never-under property holds on every
> hand fill. Both were wrong in the flattering direction, and the corrections
> are recorded in *What the first draft got wrong* at the end, because the
> errors are more instructive than the result.

## Window and population

    window   2026-08-10 .. 2026-09-08   (21 distinct days)
    n        97 venue_hand fills, all 97 carrying a non-NULL fee_actual
    orders   97 distinct venue_order_id -- one fill per order, everywhere

**Not "the whole record".** `/portfolio/fills` retains roughly three months
(`backend/store/schema.sql:1650`), so this is the mirror's window, not Joe's
betting history.

**One fill per order, verified rather than assumed.** That matters twice: the
rows are not a cluster of repeats, and the measured model rounds **per order**
(`core/fees.py:62`), so evaluating per fill would have summed several ceilings
against one charge and biased `predicted` upward — toward silence. `ords == n`
in every group, so neither applies here.

## The denominator is 22, not 96

    reconciled  96      refused  1      WOULD ALERT  0
      1  charged nothing        -> unbounded headroom, can never alert
     73  headroom above 0.1%    -> cannot fire without a schedule move that big
     22  predicted == charged   -> THE INFORMATIVE DENOMINATOR

A row is only informative if the alarm could fire on it at all. Headroom is
computed **per row** as `(predicted − actual) / actual`, not from a list of
tickers — see the last section for why that distinction is load-bearing.

| prefix | n | $0 | teeth | alert | ratio | implied k | headroom |
|---|---:|---:|---:|---:|---:|---:|---:|
| KXMVECROSSCATEGORY | 62 | 0 | 0 | 0 | 0.9859 | 0.070127 | +1.4% |
| KXMLBGAME | 8 | 0 | 1 | 0 | 0.5636 | 0.033034 | +87.0% |
| KXUFCFIGHT | 5 | 0 | 5 | 0 | 1.0000 | 0.070034 | +0.0% |
| KXUFCMOV | 5 | 0 | 5 | 0 | 1.0000 | 0.070051 | +0.0% |
| KXWNBAGAME | 4 | 0 | 4 | 0 | 1.0000 | 0.070215 | +0.0% |
| KXMLBSPREAD | 3 | 0 | 0 | 0 | 0.5000 | 0.035129 | +100.0% |
| KXEARNINGSMENTIONKLAR | 2 | 1 | 1 | 0 | 1.0000 | 0.070034 | +0.0% |
| KXNCAAFGAME | 2 | 0 | 2 | 0 | 1.0000 | 0.071068 | +0.0% |
| KXATPDOUBLES, KXPGATOUR, KXTRUMPSAY, KXTOPUSAGEAI | 1 each | 0 | 1 each | 0 | 1.0000 | 0.0700–0.0707 | +0.0% |
| KXMLBKS | 1 | 0 | 0 | 0 | 0.5029 | 0.035214 | +98.9% |

**Read `implied k`, never `worst$`.** The fee scales with `C·P·(1−P)`, so an
absolute dollar gap is not comparable across rows of different size.

## What survives

1. **0 of 22 informative rows would have alerted.** The alarm does not arrive
   pre-muted. This is a **census, not an estimate** — no group here clears the
   ≥5-per-side floor for a normal approximation, and none is offered.

2. **An out-of-sample replication of k = 0.070 for taker fills outside
   baseball.** On 21 taker rows across 8 series — UFC ×2, WNBA, NCAAF, tennis,
   golf, and two non-sports markets — the charge equals
   `ceil(0.070·C·P·(1−P))` on the $0.0001 grid **exactly**, implied k
   0.070000–0.071068. That is the assumption `FEE_MATCH_TOLERANCE_DOLLARS`
   rests on — both sides land on `FEE_GRID_DOLLARS`, so a correct model matches
   a charge exactly rather than approximately — confirmed against real charges
   instead of argued. **This is the only genuinely new evidence here**, and it
   is independent of the alarm question.

3. **Baseball behaves exactly as ADR 0058 says.** All 7 taker `KXMLBGAME` rows
   sit at implied k ≈ 0.035 against a 0.070 prediction. The 8th is a **maker**
   fill at k = 0.0177 — about a quarter of the taker rate, which is why it
   lands in the zero-headroom bucket. That row was chased specifically because
   a baseball fill matching its prediction looked like a counterexample to the
   0.035 split. **It is not one.**

4. **Combinations are the tightest population and the alarm belongs there.**
   Mean headroom +1.4% on n = 62 — an order of magnitude less slack than
   anything else. If the ADR 0073 ceiling is ever crossed, it gets crossed
   here.

## What this does NOT establish

- **Nothing about whether `core/fees.py` is correct.** The test is one-sided:
  every silent row is equally consistent with a prediction far too **high**,
  and on baseball it is, by design.
- **Nothing about `calculate_fee`'s never-under property.** That property is
  **refuted** on combinations (`core/fees.py:91-107`, ADR 0046), and
  `calculate_fee` is not the model used on those 62 rows — they are reconciled
  against the `combo_taker_fee` ceiling. **A silent combo row is not support
  for `calculate_fee`.**
- **`worst$ = −0.000100` on the combo group is not a near miss.** On a row
  whose charge lands on the $0.0001 grid, that is the smallest non-zero value
  the statistic can take — the instrument's floor. Combo charges have been
  observed on a gcd of $0.00001 (`core/fees.py:99`), so the same gap is ten
  steps of the charge's own grid. Use the +1.4% headroom, not the dollars.
- **62 combo fills are not 62 observations of the schedule.** The ADR 0073
  ceiling is a hedge above 8 observed fills, not a bound on what Kalshi charges.
- **Nothing prospective.** The schedule is the venue's to change. A census of
  the past is why the alarm exists, not a substitute for it.
- **Nothing about delivery.** This shows the reconciliation returns "no
  mismatch". Whether a real one reaches Joe's phone runs through
  `Alerter._claim` and Discord and is not exercised here.
- **Not the workload the poller runs.** Production reconciles only *newly
  stored* rows and dedupes per day; a bulk replay of 96 is not that shape.
- **The maker-combo refusal** is exercised by exactly the one row that produced
  it.

## What the first draft got wrong

Recorded because each error ran the same way — toward a larger, friendlier
result — and the third was mine to find after the audit had finished.

1. **"0 of 96."** 74 of the 96 rows could not have fired: combos are priced by
   a ceiling that exceeds every observed charge *by construction*
   (`core/fees.py:352-357`), and MLB carries a deliberate 2.00×. Quoting the
   row count as the denominator inflated what was tested by 4.4×.
2. **"No fill has ever been charged more than the model predicts."** False, and
   the single most quotable sentence in the draft. `calculate_fee` was not the
   model used on 64.6% of the population, and on that population its
   never-under property is refuted in the bad direction.
3. **The slack partition was a hardcoded list of ticker prefixes, and it was
   wrong on its first run.** It named the three MLB prefixes; the replay
   promptly turned up another group at ratio 0.5000, which read as a second
   k = 0.035 series. It was not — it was one ordinary fill averaged with a
   **zero-fee** fill, because the headroom calculation divided by `actual` and
   fell back to `0.0` when the charge was zero, classifying "charged nothing"
   as "predicted equals charged". A zero-fee row can never satisfy
   `actual > predicted`; it carries *unbounded* headroom. Both the list and the
   fallback failed in the flattering direction.

   The fix is the transferable part: **headroom is a property of the row, so
   derive it from the row.** A hand-maintained list of "the ones that are fine"
   has to be right about a population nobody has enumerated, and when it is
   wrong it overstates how much was tested.

## Provenance

Live instance, `git_sha 3bee615`, machine `7812601a239428`, read-only replay
2026-09-09 immediately after the deploy. Per ADR 0071 and the operator-data
ruling, no account row is reproduced — only counts, series prefixes, ratios and
implied coefficients.
