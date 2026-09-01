# 0065 — The estimate becomes a ticket precondition, and the standalone form retires

**Date:** 2026-08-22
**Status:** Accepted.
**Supersedes** the standalone `/estimate` form's reason to exist as a
screen; **does not reopen** the calibration study (stopped by Joe
2026-08-20, Amendment 2, terminal). The `bet_estimates` embargo (ADR 0044)
is untouched.

## 1. What happened

Two reviewers disagreed about gating the manual ticket (ADR 0063) behind a
typed probability. The red-team position: an unscored form is a speed bump
a user learns to type through — the study is stopped, nothing scores the
number, and `/estimate`'s own banner says so. The disciplined position: the
estimate is the one habit that converts betting into evidence, and the
Playbook's step 1 already teaches it.

Both were right about the form *as it existed*. The premise changed on
2026-08-22: `backend/bets.py:bet_clv()` shipped (`3067bf2`), scoring Joe's
own bets against Kalshi's close. A pre-bet P(YES) now has a consumer — it
can sit beside the bet's CLV on `/bets`, the only proprietary information
this project can still produce about Joe's betting now that consensus is
refuted (β = −0.141) and the in-house model's error exceeds its
disagreement with Kalshi (ADR 0037).

## 2. The decision

**The manual ticket's first field is P(YES), and the ask is masked until it
is entered.** One number, ~5 seconds, phone keyboard or desktop numpad. The
masking is the point, not decoration: the moment the ask is visible, the
typed number becomes the ask's number (anchoring — the Playbook's step 1
has taught this since it was written). Entering the estimate *reveals* the
price; there is no path to the confirm control that skips it.

**No required reason field.** A required reason whose honest answer is
often "entertainment" trains lying, and it makes *not betting* more
expensive than betting unless the pass path is equally cheap — which it is
not yet (ADR 0063's cool-off and the pass record land separately).

**The standalone `/estimate` form retires.** The screen's RECENT ENTRIES
record remains readable (it is history, and history is the product), but
the form, its footer slot, and its "Log" identity go. The lockout control
it hosted moves with the lockout's new server-side wiring (ADR 0063).

## 3. What this does not decide

- Nothing here scores estimates against outcomes or resumes calibration —
  that would be a new registration, pre-registrar first.
- Estimates captured at the ticket are stored beside the manual order row
  (they are operator data in the same sense as the order itself, inside
  the same table boundary ADR 0063 draws), not in `bet_estimates` — the
  stopped study's log stays terminal, exactly as Amendment 2 left it.
- No aggregate ("your estimates run 8 points hot") below n ≥ 30 with the
  per-group view beside it — the same floor `/bets` holds for CLV.

**Amended 2026-08-29 — what kind of gate the 30 is, and in what units.**

- **`n ≥ 30` is a display gate, never a verdict gate.** At n = 30 the design
  can resolve only a calibration bias of roughly **26 points** under a plain
  fixed-n test (2.8 × 0.5/√30) and **63.2 points** under the registered
  always-valid boundary (2026-08-29 operator self-assessment registration
  §6a: m = 150, α = 0.05, 80% power, conservative sd = 0.5) — an instrument
  that can tell "betting the wrong side" from nothing, and no more. So at
  n ≥ 30 the numbers may render; a *verdict* — "too tight", "runs hot",
  "protective" — requires the same floor every mart holds,
  `min_scored_recommendations` (300), or the registered floor of the
  measurement that owns it.
- **Units: `n` counts games/clusters, not settlement rows.** Rows inside one
  game are correlated, so 30 rows from four games is n = 4, not n = 30 — the
  same lesson `G_eff` carries on the signal test.
- **Where the confusion already leaked:**
  `warehouse/models/marts/mart_suppression_audit.sql` used a hardcoded 30 as
  its *verdict* floor — pronouncing "this rule may be too tight" from 30
  rejection rows — while its sibling marts held verdicts to 300. Fixed
  2026-08-29; guarded by
  `warehouse/tests/assert_suppression_audit_never_judges_below_the_floor.sql`
  and `tests/test_marts.py::TestSuppressionAuditHoldsTheSharedVerdictFloor`.
  Note the defect was latent only because `warehouse/` is not in the
  Dockerfile (live returns 503 for the dashboards); it goes live the moment a
  session runs `dbt build` locally and lifts a mart row into a document.

**Amended 2026-09-01 — the estimate is no longer ONLY a ticket precondition,
and the standalone form comes back price-free.**

Decision-map ticket #11, resolved with Joe 2026-09-01. Build:
`docs/adr/DRAFT-the-estimate-decouples-from-the-bet.md` (numbered at merge).

- **§2's premise was measured and did not hold.** This ADR made P(YES) the
  ticket's first field on the reasoning that a pre-bet estimate now had a
  consumer. It does — but the ticket does not: `manual_orders` is **empty**,
  the Buy button has been armed since 2026-08-26 and never used, and all 76
  settled positions were placed in the Kalshi app. Joe's reason, asked
  directly: it is faster and he is already in it. A precondition on a path
  nobody walks collects nothing.
- **The decision itself stands.** The ticket keeps its estimate precondition
  and its masked ask, unchanged, for exactly the reason §2 gives: the moment
  the ask is visible the typed number becomes the ask's number. Ticket #11
  decision 10 is explicit that these are **two prompts with different jobs** —
  the ticket's prevents anchoring on a live buy; the new one measures
  judgement.
- **§3's second bullet is superseded in the narrow sense that matters.** It
  read *"the standalone `/estimate` form retires"* and *"nothing here scores
  estimates against outcomes or resumes calibration"*. The form returns, as a
  **price-free** screen reached from the Discord window-open digest, and calls
  logged there **are** scored — against **Kalshi's close, never the outcome**,
  which is why this is not a resumption of calibration. The stopped study's own
  log stays terminal: those rows carry `is_study_row = 1` and are neither
  scored nor served (ADR 0044 Amendment 3).
- **§3's third bullet is unchanged and now binds a second surface.** No
  aggregate below n >= 30 with the per-group view beside it, and the
  2026-08-29 amendment above governs what the 30 buys: a **display**, never a
  verdict. One call at a time.
