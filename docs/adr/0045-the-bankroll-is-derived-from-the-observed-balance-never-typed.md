# ADR 0045 — The bankroll is derived from the observed balance, never typed

- **Status:** Accepted
- **Date:** 2026-08-18
- **Supersedes:** ADR 0041's mechanism (every dollar cap stated in every
  deploy config). Its *principle* — "a cap nobody chose is not a cap" —
  stands and is the reason for this change, not a casualty of it.
- **Related:** ADR 0015 (the reference bankroll and why the gate's counter
  ignores the deposit), the calibration registration's A7 (the balance
  poller and its two clocks).

## The decision

1. `BANKROLL_DOLLARS`, `MAX_POSITION_DOLLARS`, `MAX_EXPOSURE_DOLLARS` and
   `MAX_DAILY_LOSS_DOLLARS` are **retired settings**. They are removed from
   both fly configs, `.env.example`, and the local `.env`; setting any of
   them is announced at ERROR on every config load and in
   `retired_settings_set` on `/api/health`, and is never read.
2. `RiskConfig.load()` returns the four dollar quantities as `None` —
   **underived** — and `core.sizing.size_position` refuses an underived
   config outright (`binding_constraint="bankroll_unobserved"`). A
   directly-constructed `RiskConfig(...)` with explicit dollars remains
   valid: that is the test-fixture form, under "clamp what you trust; refuse
   what you're validating".
3. At each sizing decision, production paths derive the four quantities from
   the venue's own record: `RiskConfig.with_observed_balance(
   store.db.latest_balance_tenths(conn))`. The reader takes the **newest**
   `venue_balance_snapshots` row verbatim — a newest row whose balance was
   unreadable answers `None`, and falling back to an older value would hide
   exactly the outage that makes the number stale.
4. The three caps are fixed **fractions** of the derived bankroll: 10% in
   one market, 40% at risk at once, 10% lost in a day before the kill
   switch. These are the fractions both prior profiles already used — the
   $1,000 reference (100/400/100) and the retired deployed env (100 →
   10/40/10) — so the judgement is held constant while the bankroll tracks
   reality. Changing a fraction is a strategy change and needs its own ADR.
5. `kelly_fraction` and `max_order_contracts` stay environment-configured.
   They are judgements about the strategy, not facts about the account, and
   the account cannot state them.

The derivation runs in three places, each at its own natural clock:

- `runner.run_pricing_pass` — once per pass, so every recommendation row's
  `suggested_contracts` is sized against the balance as of that pass.
- `POST /api/orders` — inside the request, beside the exposure/position/P&L
  reads that already happen there: a control reads the state at the moment
  it decides.
- `live.QuoteHub` — on the same per-cycle snapshot read as the rest of the
  risk state, so the ticker and the order endpoint cannot disagree about
  which balance they sized from.

## The defect

`fly.live.toml` deployed `BANKROLL_DOLLARS = "100"` against a real balance
of ~$20.66. Every size on the Board was ~4.8x what quarter-Kelly at the real
bankroll gives, for at least a week, and nothing was red — the exact failure
ADR 0041 fixed one instance of, one abstraction level down. ADR 0041's
mechanism (type the caps everywhere, test that the files agree) guaranteed
the caps were *chosen*; it could not make them *true*, because truth here is
a fact about the account and the account moves. A typed cap and an omitted
cap fail identically: the number nobody is maintaining wins.

Meanwhile the poller (registration A7) had been writing the venue's own
balance into `venue_balance_snapshots` every five minutes. The true number
was in the database while the typed one was on the screen.

## What refuses, and what keeps running

- **No snapshot ever written** (fresh volume, demo instance, poller dead):
  sizing refuses with `bankroll_unobserved`; the order endpoint answers 422
  naming `venue_balance_snapshots`; the runner logs one warning per pass.
  "Cannot determine the bankroll" never resolves to a typed default.
- **The record is untouched.** The gate's `actionable` counter reads
  `reference_contracts`, sized at `RiskConfig.reference()` — constants, by
  ADR 0015 — and `reference()` works on an underived config. A missing
  balance read can blank the *shown* size; it cannot stop the evidence
  record accumulating. Verified by
  `test_the_reference_profile_still_sizes_from_an_underived_config`.
- **An observed $0.00 derives a real config** that sizes everything to
  zero. Observed broke and unobserved are different states and are kept
  apart, per the repo's `None`-never-`0` rule.
- **The demo** holds no account, so it derives nothing: its Board is seeded
  by `seed_demo.DEMO_RISK`, an explicit pinned profile whose dollar caps
  are tested to equal what `with_observed_balance` would derive from its
  own synthetic bankroll — the same judgement, embodied rather than typed.

## What this does not establish

- That 10/40/10 are the right fractions. They are carried over, not
  measured.
- Anything about staleness bounds on the balance. The newest snapshot may
  be minutes or days old; the derivation takes it verbatim. If the poller
  dies, sizes keep tracking the last observation until the snapshot table's
  own tripwires (registration A1) say the record has a gap. A freshness
  refusal here was considered and rejected for now: the order path is
  dry-run (`ORDERS_ARE_DRY_RUNS = True`) and the gate is locked, so the
  marginal risk is a display artefact, and a second staleness clock
  deserves its own decision if arming ever becomes a live question.
- Anything about the gate, which continues to count reference-sized rows
  only.

## Guard verification

- `size_position`'s underived refusal: check removed → the refusal test
  fails with a `TypeError` out of the stake arithmetic; restored → green
  (2026-08-18).
- The order path's trusted-fixture branch (explicit configs pass through
  underived-free) is exercised end-to-end by `tests/test_quote_refresh.py`.
  The 422 branch over an empty snapshot table is not end-to-end tested: the
  gate check sits in front of it and opening the gate in a fixture is a
  bigger lie than the coverage gap. The refusal it guards is the same
  `underived` predicate the sizing tests verify directly.
