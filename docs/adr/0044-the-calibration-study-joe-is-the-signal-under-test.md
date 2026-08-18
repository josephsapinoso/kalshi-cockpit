# ADR 0044 — The calibration study: Joe is the signal under test

- **Status:** Accepted (the study is OPEN; day 1 stamped 2026-08-18T09:15Z)
- **Date:** 2026-08-18
- **Registration:** `docs/measurements/2026-08-17-preregistration-joe-
  calibration-bet-log.md`, Amendments A1–A8. **The registration governs; if
  this ADR and the registration disagree, this ADR is wrong.** This document
  exists so no future session re-derives what was decided, or mistakes a
  registered constraint for a style preference.
- **Related:** ADR 0038 (the hunt is closed — this study is not a reopening),
  ADR 0043 (the gate counts engine fills only, which is what lets the
  poller's `venue_hand` rows exist without touching the interlock),
  ADR 0045 (the bankroll derivation reads the same balance record).

## What was decided

After ADR 0038 closed the automated-signal hunt, one measurable question
remained that no quadrant had touched: **is Joe himself calibrated?** He has
been betting by hand all along; the tool's job here is to *record* him
honestly, not to advise him. The study measures whether his stated
probabilities beat the venue's prices — estimand `B`, the anchor gap, per
the registration — with one look, at a registered stop.

## The design, compressed to what future code must not break

1. **Two clocks.** Joe types a ticker and P(YES) (basis points) into
   `/estimate` BEFORE betting; the server stamps its own clock and captures
   the market's book server-side. The venue's fill timestamps are the second
   clock. An estimate provably typed before the fill is the measurement.
2. **The captured quote is embargoed.** It is the anchoring tripwire; it is
   never rendered, returned, or aggregated until the stop fires.
   `_assert_embargo_holds` walks every renderable payload in the tests.
3. **Write-once is the database's job.** `trg_bet_estimates_write_once` and
   `trg_bet_estimates_no_delete` live in `schema.sql` (NEVER a migration —
   v11 drops the table for schema.sql to recreate; the 4d35c32 crash loop is
   the scar). Corrections are append-only revision rows; a revised estimate
   is excluded, not edited.
4. **No interim aggregate over the estimate log, ever** (§0.2, §5). The two
   registered exceptions: a plain count, and the "$X of $100" strip over
   `venue_settlements` (A7 — the wallet is not the log).
5. **The money arm** (§5 arm 3 as amended by A2): stop forever at $100
   cumulative net realised loss since study start, computed from
   `venue_settlements` — `backend/estimates.py:study_loss_dollars()`, with
   `POST /api/estimates` answering 423 once it fires. Reloads do not void
   the result (the §5 no-reload clause is marked superseded in place; A8
   registers the study as infeasible *without* top-ups). The $2 stake cap
   is statistical: it holds the arm's firing probability at ~3.6%.
6. **The poller is the record.** Both portfolio endpoints drop history
   (settlements lost 55 rows inside eight days), so
   `backend/portfolio_poll.py` mirrors settlements, fills
   (`source='venue_hand'`), and the balance every 5 minutes, and stamped
   day 1 once, immovably, from the venue's own number
   (`start_ms=1787044503594`, `balance_tenths=20658`).
7. **The matcher runs on read, not at ingest**
   (`backend/estimate_match.py`): estimates join to settlements per §7.3,
   outcomes prefer the public market result (the durable path), voids stay
   NULL, and attrition is a measured rate (`match_status`), not a silent
   bias.
8. **Exclusions are structural.** Combos (`KXMVE*`), non-sports, revised
   rows, and the 22 pre-protocol settlements are out of the primary
   population — the last of these may not even be printed as a descriptive
   record (they are the 29%-up-on-noise shape exactly).

## What this study is not

- Not a reopening of the edge hunt. ADR 0038 stands; no roadmap may depend
  on the study's outcome, and the recorder costs nothing.
- Not advice. The form shows no price, computes no edge, and suggests no
  bet. The tool's opinion of Joe's bets does not exist until the stop.
- Not a P&L tracker. The one money figure on screen is the distance to the
  stop, over the venue's own settlements.

## Why it is worth running anyway

Joe confirmed, via the decision-relevance question the registration
demanded, that an OVERCONFIDENT verdict would change how he bets. A study
whose outcome changes nothing would be entertainment; this one has a
registered consumer.
