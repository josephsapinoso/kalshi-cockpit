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
