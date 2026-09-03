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
  ADR 0045 (the bankroll derivation reads the same balance record),
  `0094-the-estimate-decouples-from-the-bet.md` (Amendment 3's build —
  numbered at merge).
- **Amendments to this ADR:** Amendment 3 (2026-09-01) is at the end and
  changes two of the design points below in place. Read it before acting on
  points 2 or 5.

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
   **Scoped by Amendment 3 (2026-09-01): this binds the study's own rows
   (`is_study_row = 1`), not every payload.** See §3a-3b below. The walker was
   narrowed, not relaxed — a payload that does not declare its regime is bound
   in full, exactly as before.
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
   `POST /api/estimates` answering 423 once it fires. **That 423 is deleted as
   of Amendment 3 (2026-09-01) — see §3c.** The reader stays and A7's wallet
   strip still serves it; the arm no longer refuses the write path, because it
   never gated betting and all it could stop was Joe writing a number down.
   Reloads do not void
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

---

## Amendment 3 (2026-09-01) — the embargo binds the study's OWN rows, and the money arm stops gating logging

Decision-map ticket #11, resolved with Joe 2026-09-01. **The study is not
reopened by this** — Amendment 2 stopped it without result on 2026-08-20 and
that is terminal. What changes is what the machinery it left behind is allowed
to do for a *different* purpose. The build is
`docs/adr/0094-the-estimate-decouples-from-the-bet.md`.

### 3a. Two regimes now share `bet_estimates`

`is_study_row = 1` — the study's own record. **There is exactly one such row**
(logged 2026-08-22), and design point 2 above holds for it unchanged: its
captured quote and any score over it are never rendered, returned or
aggregated. Nothing scores it (`score_bet_estimate_calls` filters it out) and
nothing serves it (`last_scored_call` filters it out).

`is_study_row = 0` — a **decoupled call**: Joe logging what he thinks from a
price-free screen that tells him at log time that it will be scored against
Kalshi's close and read back. He is not being measured without knowing; the
anchoring tripwire that made the embargo necessary does not apply to a number
collected under an explicit promise of feedback.

The column defaults to 1, so the ALTER stamps every row already on the volume
as the study's own and the promise holds without a backfill that has to guess.
**At n = 1 keeping the promise costs nothing**, which is the entire reason it
is kept rather than argued about.

### 3b. What design point 2 now means for `_assert_embargo_holds`

Point 2 above says the walker "walks every renderable payload in the tests".
It still does. What changed is what it finds acceptable, and the change is a
**narrowing, not a relaxation**:

- A payload that says nothing about its regime is bound by the full fragment
  list `(bid, ask, quote, server_yes, outcome, clv)`, byte-identically to
  before. Every pre-existing call site keeps the assertion it had.
- A dict that declares `is_study_row: 0` may carry four **named** keys —
  `call_clv_tenths`, `call_clv_horizon_hours`, `call_clv_scored_ms`,
  `call_closing_line_id` — and no others. Never a `call_*` prefix rule:
  `call_server_yes_bid_tenths` satisfies a prefix rule and is the precise leak
  this exists to stop.
- A study row carrying a score still fails. A call row carrying the captured
  quote still fails. The exemption is not inherited by nested objects.

`TestTheEmbargoBindsTheStudysOwnRows` holds all four halves, each with its
mutation recorded.

### 3c. The $100 money arm no longer refuses `POST /api/estimates`

Design point 5 above says the arm answers 423 on that route. **It no longer
does.** The arm is a study stop condition, and it was sitting on the one
endpoint that records what Joe thinks.

It never gated betting: the order path has its own daily-loss switch and its
own caps, and 76 of 76 settled positions were placed in the Kalshi app, which
this server cannot reach. So all the arm could stop was him writing a number
down, which costs nothing and risks nothing.

`study_loss_dollars()` is untouched and `GET /api/estimates/stop` still serves
it — A7's wallet strip is unaffected. Only the refusal is gone.

**The self-lockout beside it is kept, unweakened, with no early unlock.** A
study's stop condition and an instruction Joe gave himself are different kinds
of thing.

**The arm was already inoperative when this was written, and that is recorded
rather than repaired.** One study-period settlement carries an empty
`market_result`; `study_loss_dollars` refuses all-or-nothing on any unreadable
row; the endpoint refused only on a computable `True`. Logging was therefore
already open — because the stop was *broken*, not because it had been
*decided*. Repairing the reader is money-touching, is Joe's, and is out of
scope; this amendment picks between neither of the two possible fixes.

### 3d. What this study still may not do

- **Nothing here scores an estimate against an outcome.** The decoupled call is
  scored against Kalshi's closing mid only. That measures disagreement with the
  market, not correctness, and ADR 0037 is why the two are not separable
  without settlements.
- **No aggregate over the estimate log**, still. Design point 4 stands
  verbatim: a plain count, and A7's wallet strip. The decoupled call adds a
  third thing that is not an aggregate — **one row at a time** — and n >= 30
  clustered calls only lifts the display gate, never the verdict gate (ADR
  0065, amended 2026-08-29; verdicts need 300 or the owning measurement's own
  floor).
- **A verdict over the decoupled calls is a new pre-registration.** This
  amendment authorises a display and explicitly does not authorise a
  conclusion.

### 3e. What would falsify the diagnosis this amendment acts on

Ticket #11's diagnosis is that the estimate was not being logged **because it
was welded to a bet Joe places somewhere else**. Registered before the screen
ships:

> **Zero estimates logged in the seven days after the log screen ships means
> #11's diagnosis was wrong and the line closes.**

The prior is one estimate ever. Seven days of a reachable, price-free log
screen with nothing typed into it means the obstacle was never the coupling,
and no further design on this line is warranted — no new screens, no
re-wording, and no reminder push (ADR 0071 forbids manufacturing action in any
case). The columns and the scorer stay; they cost nothing.

The seven days start at the **log screen's** ship, not at this commit: until
then there is nowhere to log a call from.

## Amendment 4 (2026-09-03) — a voided settlement counts its fee as a loss

**Decided by Joe, 2026-09-03 ("44A"), from a two-option batch in which the
call carried no recommendation because it is a stop rule on his money.**
Registered as A16 in the registration's Amendment 4, which governs; this
section records the decision and what code must not break.

### 4a. What was wrong

Design point 5's formula is A2's, verbatim: `sum(payout - cost - fee)` over
study-period `venue_settlements`, with payout `contracts × $1` on a win and
`$0` on a loss. `study_loss_dollars` refuses — returns `None`, "cannot know"
— on any row whose `market_result` is neither `yes` nor `no`, because *"a
void has no registered payout and inventing one here would silently amend
the stopping rule."* That sentence was right and the consequence was not
foreseen: one study-period settlement is a cross-category `KXMVE`
combination the venue voided, stored with `market_result = ''`, so the arm
has been **permanently uncomputable** since it settled. Not systematic — the
other 53 rows compute — but one row is enough forever, because the record
only grows. The first live read (`study-stop`, 2026-09-01) surfaced it.

### 4b. The decision

A void contributes **its fee, as a loss, and nothing else.** The stake came
back; the fee left the account. Formally, for a row whose `market_result` is
a registered void marker: `payout − cost = 0` by definition and the row adds
`−fee` to the net. This is the conservative direction for a stop rule — it
fires sooner, never later — and it is what the account balance did.

The alternative, exclusion with the exclusion counted, was offered and
declined. It is recorded because it was defensible: a void is not an
outcome, and a figure over settled outcomes only, with "1 void excluded"
printed beside it, would also have been honest.

### 4c. What is and is not a void

The registered void markers are `NULL`, `''` and `'void'`. The live row is
`''`; the test fixtures have used `'void'` since A2; the poller passes the
venue's field through untouched, so `NULL` is the shape an absent field
takes. **Any other value still refuses.** This amendment teaches the formula
the venue's ways of saying "no result"; it does not teach it to guess. A
void with an unreadable fee also still refuses — the fee is the whole
contribution and cannot be invented either.

### 4d. What this does not change

- The ceiling ($100), the population (study-period settlements), the
  exclusions (§8), and the embargo (design point 2, as scoped by Amendment 3).
- The study's terminal state: **STOPPED WITHOUT RESULT** (registration
  Amendment 2, 2026-08-20). The money arm feeds A7's wallet strip and the
  `study-stop` inspector; it gates nothing (Amendment 3 §3c deleted the 423).
  This amendment makes a readout computable; it revives nothing.
- `study-stop`'s mirror of the formula (`scripts/inspect_live_db.py`) is
  amended in the same commit and stays pinned to `study_loss_dollars` by
  `tests/test_study_stop_query.py`, including on the void row.
