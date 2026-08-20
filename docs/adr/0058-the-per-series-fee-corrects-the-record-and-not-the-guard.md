# 0058 — The per-series fee corrects the record, and not the guard

Date: 2026-08-20. Status: ACCEPTED (partner review 2026-08-20 ~21:20Z:
approved subject to three amendments, all incorporated — the
`fills.fee_predicted` exclusion with its ADR 0043 reasoning, its tripwire
test, and the settlements basis-boundary requirement). Supersedes nothing.

**Implemented in `3b572c5`** (same day): migration v16 adds
`settlements.fee_model_used` as the basis marker — NULL is the pre-v16
flat-model regime — the settlement pass reads `/series/{ticker}` live and
tags every row, and both tripwire halves are armed
(`tests/test_portfolio_poll.py::test_an_mlb_fills_predicted_fee_stays_on_the_flat_model`,
`tests/test_gate_counts_engine_fills_only.py`), mutation-verified red.
Decided at the partner triage of 2026-08-20 ~21:10Z, on the evidence of
`tests/fixtures/series_fee_fields.json` (fleet convening item 9) and the
engine split check taken the same evening.

## The decision, stated narrowly

Kalshi's public `/series` metadata carries `fee_multiplier` — 0.5 on
KXMLBGAME and KXMLBSPREAD, 1 on KXATPDOUBLES and KXWNBAGAME — and it
predicts all 11 attributed real fills to $0.0001 from the deployed base
coefficient alone (`tests/test_series_fee_multiplier.py`). That evidence
buys exactly one change:

- **The record adopts the per-series fee, at exactly one site.** Settled
  PnL (`backend/settlement.py:244`, `calculate_fee_cents` inside
  `settled_pnl`) moves to `k = TAKER_COEFFICIENT × fee_multiplier(series)`.
  The current model overstates MLB fees by exactly 2×, so realised PnL is
  today recorded worse than it was; in the record, being right beats being
  conservative. The `settlements` table carries no fee-regime marker
  (schema.sql:739-751), so **the implementing commit must either add one
  or append its own SHA and date to this ADR as the basis boundary** —
  otherwise realised PnL across that boundary silently compares two
  models. Note the corrected prediction can still differ from what the
  venue charged: the applied bar is deliberately conservative (50.88%
  true on baseball, 51.75% applied — CLAUDE.md), and that residual is the
  conservatism made visible in the data, not a wart.

**`fills.fee_predicted` (`backend/portfolio_poll.py:361`) is deliberately
NOT corrected here, and the reason is not evidential.** That column is
read by `_fee_model_verified` (`backend/gate.py:738-748`), which compares
`fee_actual` against `fee_predicted` on `source = 'engine'` rows. The
comparison is inert only because the tool has never placed an order.
ADR 0043 leaves open whether hand-placed fills should be admitted to that
population; under the present 0.070 model those fills mismatch and would
make the gate *stricter*, and under a per-series model they would match
and make the condition *passable*. Correcting the column now would decide
ADR 0043's open question in the permissive direction as a side effect of
a record fix. It is blocked on that decision, not on evidence.

A test asserts `fills.fee_predicted` is still written under the 0.070
model and that `_fee_model_verified` still filters `source = 'engine'`.
If either changes, it fails and cites this ADR. Verify it by disabling
the guard and watching it go red.
- **Every decision-bearing path stays on `TAKER_COEFFICIENT = 0.070`
  unchanged**: the suppression edge check (`backend/suppression.py`),
  sizing (`backend/core/sizing.py`), the actionable predicate
  (`backend/gate.py:330`), the order-time edge ceiling and EV recheck
  (`backend/api/routes.py`), and `recommendations.fee_predicted`.

## Why the guard does not move, and it is not caution

A cost correction cannot create an edge — ADR 0038's closing argument.
Halving the MLB fee relaxes the suppression edge bar and raises
`reference_contracts` at once, i.e. it opens the gate's both halves
(`suppressed_reason IS NULL AND reference_contracts > 0`) on the venue's
largest slate — and the entire payoff is more rows on a screen the record
says carries no signal (`beta = -0.141`, ADR 0021/0034). Never lower a
guard to buy nothing. **The reopening condition is registered here: this
half is revisited only if a new signal is funded under ADR 0038's own
rule — naming the quadrant row it overturns — and not when the fee
evidence improves further.**

## The engine makes the narrow scope structural, not stylistic

`backend/engine.py` computes one EV object per candidate and writes
`fee_predicted=ev.fee_dollars` (`engine.py:269`) from the same computation
whose edge and sizing feed suppression and the gate. There is no seam at
which `recommendations.fee_predicted` can adopt the cheaper fee while the
gate keeps the dearer one — they are the same number at one call site. So
the record half is **settled PnL only**; both predicted-fee columns
(`recommendations.fee_predicted`, `fills.fee_predicted`) remain
0.070-model quantities, each for its own stated reason above.

## Two named holes in the evidence, carried rather than smoothed

1. **`fee_type` varies within a multiplier group.** The fixture shows
   `quadratic_with_maker_fees` on KXMLBGAME/KXWNBAGAME and plain
   `quadratic` on KXMLBSPREAD/KXATPDOUBLES. If plain `quadratic` means "no
   maker fee", then `MAKER_COEFFICIENT = TAKER/4`
   (`backend/core/fees.py:132`) is wrong on those series, and
   `tests/test_fees.py:151` asserts it unconditionally. The 11 fills are
   all taker fills and cannot arbitrate. The maker model is therefore
   **unverified per series** and this ADR changes nothing about it.
2. **An event-level `fee_multiplier_override` exists.** The spread-test
   instrument reads it and prefers it over the series value
   (`scripts/measure_spread_edge.py:219-223`); no occurrence exists
   anywhere in `backend/`. The true schedule is series-with-event-override
   and the backend has never seen the override. The record-half
   implementation must read the override where the event payload carries
   one, or state per row that it did not look.

## The verification cannot ride in CI, and the repo is public

The 11-fill prediction runs only where the operator's private capture
exists (`data/captures/portfolio_fills.json`), which — under the
2026-08-20 operator-data ruling — is never committed, sanitized or
otherwise. **Green CI is not evidence for this change**: CI exercises the
fixture-shape assertions and skips the prediction, and says so in its skip
reason. Anyone reproducing this decision needs their own fills capture.

## Implementation constraint carried from ADR 0019

`strategy_config_version` (`backend/runner.py:1301-1350`) hashes
"everything the counted column depends on, and nothing else". The record
half deliberately touches no input of the counted column — settlement PnL
and `fills.fee_predicted` feed no gate quantity — so no new hash key is
owed. Any future change that moves the guard half MUST add the fee model
to that hash first, or two fee regimes pool under one version, the defect
ADR 0019 exists to prevent. This paragraph is the tripwire.

## What this does not establish

- Nothing about maker fees (hole 1), about series beyond the four
  captured, or about the schedule not changing again — the 2025-11 →
  2026-08 revision is why `test_series_fee_multiplier.py` pins the
  fixture.
- Nothing about H4: whether settlement carries its own fee is untouched
  (ADR 0027), and the cost headroom stays an upper bound.
- Nothing about the applied *bar* (51.75% taker): the bar is a guard
  quantity and this ADR leaves guards where they stand.
