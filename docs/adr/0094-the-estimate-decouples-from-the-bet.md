# ADR 0094 — The estimate decouples from the bet

- **Status:** Accepted. Backend, schema and tests only; the Discord digest link
  and the log screen are a later step and are deliberately not here.
- **Date:** 2026-09-01
- **Resolves:** decision-map ticket #11, resolved with Joe 2026-09-01 (14
  numbered decisions, two resolved collisions, one self-correction).
- **Amends:** ADR 0044 (Amendment 3 — the embargo is scoped to the study's own
  rows; the $100 money arm stops gating logging), ADR 0065 (the estimate is no
  longer *only* a ticket precondition).
- **Related:** ADR 0038 (the hunt is closed — this is not a reopening),
  ADR 0071 (what the tool is for: price transparency at the moment of a bet),
  ADR 0037 (why a disagreement statistic cannot separate edge from noise).

## 1. The premise the ticket was built on was false

The ticket said *"Before every hand bet Joe types his honest percent chance…
It is stored on every row."* Measured on live 2026-09-01:

| | |
|---|---|
| Typed estimates in the database, ever | **1** (2026-08-22) |
| Settled positions | 76 (26 single-market, 49 combos) |
| Positions with a matched estimate | **1** |
| Hand bets ever placed through the tool's order path | **0** |

`manual_orders` is empty. The Buy button has been armed since 2026-08-26 and
has never been used; all 76 positions were placed in the Kalshi app. Joe's
reason, asked directly: **the Kalshi app is faster and he is already in it.**

No amount of design on the tool's own ticket fixes that, so the estimate prompt
cannot live on the buy path. **The estimate decouples from the bet.**

## 2. What was decided, and what this commit builds

Logging a call is its own act, scored **at close** against Kalshi's own price,
which needs no position and does not care whether he bet. The verdict is *"you
said 58%, Kalshi closed 61%"* and is **never** the outcome — one result cannot
grade a probability, a good 58% call loses 42% of the time, and the closing
line is the only thing that grades a probability in a single observation
(rule 3).

Built here:

1. **The write path is unblocked** — `POST /api/estimates` no longer answers
   423 on the $100 money arm (§3).
2. **The embargo is rescoped** to the study's own rows (§4).
3. **The score is written and read** — five new columns, SCHEMA_VERSION v32,
   a scorer beside `score_recommendations`, and a singular read (§5, §6).

Not built here, deliberately: the Discord digest's "log a call" link, and the
price-free log screen. They are the next step and this ADR does not decide
their copy.

## 3. The $100 money arm stops gating logging; the self-lockout does not

The arm (registration §5 arm 3 as amended by A2) is a **study stop condition**
that had been left sitting on the one endpoint that records what Joe thinks.

It never gated betting. The order path carries its own daily-loss switch and
its own caps, and 76 of 76 positions were placed in an app this server cannot
reach. So the only thing the arm could actually stop was him **writing a number
down**, which costs nothing and risks nothing.

`study_loss_dollars` is untouched and `GET /api/estimates/stop` still serves
it — the wallet strip is a fact about his money and keeps its reader. What was
deleted is its power over the write path.

**The self-lockout immediately below it is kept, unweakened, with no early
unlock.** That is an instruction Joe gave himself, and its whole value is that
it does not negotiate. Deleting a study's stop condition and keeping an
operator's own is not an inconsistency; they are different kinds of thing, and
the test `test_the_self_lockout_still_closes_it` pins that both states can be
true at once.

**One thing found and deliberately not repaired.** The arm was already
**inoperative**: one study-period settlement carries an empty `market_result`,
`study_loss_dollars` refuses all-or-nothing on any unreadable row, and the
endpoint only refused on a computable `True`. So logging was already open —
but because the stop was *broken*, not because it was *decided*. That
difference is the entire reason this is written down. Repairing the reader is
money-touching, is Joe's, and is explicitly out of scope; nothing here picks
between the two possible amendments.

## 4. The embargo binds the study's own rows

ADR 0044 §2 forbids the fragments `bid`, `ask`, `quote`, `server_yes`,
`outcome`, `clv` from any renderable estimate payload — *"never rendered,
returned, or aggregated until the stop fires"* — enforced by
`_assert_embargo_holds` walking every payload in the tests. **The verdict here
is a CLV.** That is a real collision and it is resolved, not dodged.

**Ruling: the embargo binds the study's own rows.** The single existing row was
collected under a promise it would never be shown to him, and that promise
holds — at n = 1 keeping it costs nothing. New calls are collected under a
screen that says *at log time* that they will be scored and read back.

In code that promise is a column, `bet_estimates.is_study_row`, defaulting to
1. In the tests it is a narrowing of the walker, not a relaxation:

- A dict that says nothing about its regime is bound by the **full** fragment
  list, exactly as before. Every pre-existing call site therefore keeps the
  assertion it had, unchanged.
- A dict that declares `is_study_row: 0` may carry four **named** keys and no
  others. Not a `call_*` prefix rule: `call_server_yes_bid_tenths` satisfies a
  prefix rule and is the precise leak the embargo exists to stop.
- A study row carrying a score still fails. A call row carrying the captured
  quote still fails. The exemption is not inherited by nested objects, so one
  declaration at the top of a payload cannot license a score on a study row
  beneath it.

**The name was not softened to fit the string match.** Calling the column
`stated_vs_close_tenths` would have kept the walker green by dodging the
fragment `clv`, which is the "one predicate with two spellings" failure this
repo has already paid for three times. It is a CLV-shaped quantity, it carries
`clv` in its name, and the guard was rescoped honestly instead.

## 5. The ticket said "a read, not a new UNION branch". The ticket is wrong

Its own correction established that no third `markets_awaiting_scoring` branch
is needed — `/api/slate` and that function's first branch share the same
`recommendations JOIN event_links`, so every market reachable from the digest
is already in the closing-line set **by construction** (measured on live
2026-09-01 at the 1h horizon: 136/136 WNBA, 578/604 MLB, 16/16 started NCAAF).
That part is right and this build depends on it.

What the correction then concluded — *"the build is a read"* — is not.
`bet_estimates` already carries `closing_line_id`, `clv_tenths`,
`clv_horizon_hours` and `clv_scored_ms`, and nothing has ever written one of
them. They look spare. **They are the registered secondary arm** (registration
2026-08-17 §3, "Secondary: mean CLV"):

> `clv_tenths` from `backend/analysis/clv.clv_tenths()`, unmodified … Its
> `entry_ask_tenths` argument is **the venue's own average entry price**
> (§9.1), never a mid.

`entry_ask_tenths` is the price paid for the side actually taken and `side`
comes from the venue, so **that quantity requires a position**. Decision 6's
verdict is position-free by design. Writing one into the other makes the column
a silent mixture of two regimes — which is exactly the failure
`clv_horizon_hours` was added to prevent, one line down in the same table.

So: **new columns, and SCHEMA_VERSION v32.**

| column | why it exists |
|---|---|
| `is_study_row` | Which promise the row was collected under. `NOT NULL DEFAULT 1`, so the ALTER stamps every row already on the volume as the study's own and the promise holds with no backfill that has to guess. A writer that forgets produces a row this repo refuses to render — a missing feature; the other default would produce a row it renders in breach of a promise — the harm. |
| `call_clv_tenths` | The score: stated probability minus the closing YES mid, in tenths of a percent. Positive means he said higher than the market closed. |
| `call_closing_line_id` | Which closing line produced it. |
| `call_clv_horizon_hours` | Written **with** the score, never inferred later — the reason `clv_horizon_hours` exists. |
| `call_clv_scored_ms` | When it was scored. |

Four `call_*` columns mirroring the four registered ones, and the mirroring is
the documentation: they are separate because they are a different regime, not
because someone wanted a fresh name. The registered four stay NULL, and
`TestTheRegisteredArmIsNotReused` fails if the scorer ever names one.

**The unit identity, stated once so nobody re-derives it.** A contract pays $1,
so a price in tenths of a cent maps 1:1 onto a probability in tenths of a
percent: 5800 bp = 58.00% = 580 tenths. `stated_probability_bp / 10` is
directly comparable to a closing mid in tenths, with no model, no fee and no
position in between.

**There is deliberately no `call_close_mid_tenths`.**
`stated_probability_bp` is write-once (the DB trigger) and `call_clv_tenths` is
written once with the score, so the mid is recovered exactly by
`stated / 10 - clv`. A stored copy would be a second representation of one
number, free to disagree — the reason v8 declined a `threshold` column beside
`strike`. It is also *better* than re-reading: `store_closing_line` upserts, so
the `closing_lines` row can move after the score was taken, and a screen that
re-read it would quote a mid the verdict was not computed from.

The migration is `ALTER TABLE ADD COLUMN` only — metadata-only, O(1), no table
rewrite — which is what makes it safe against the 2.25 GB live volume at boot.

## 6. The scorer mirrors `score_recommendations`, refusals included

`analysis.clv.score_bet_estimate_calls`, called from `run_scoring_pass` beside
the recommendation arm, on the same closing lines, at the **primary horizon
only** (scoring at both would make the column a mixture with no way to tell
which row came from which). Its counters are separate — one pooled `scored`
would hide an arm that had stopped working behind an arm that had not.

Both of `score_recommendations`'s refusals are made here and counted:

1. **The call must precede the close it is scored against.** Otherwise
   whichever way the market drifted between the two instants lands directly in
   the number, and whether that flatters or punishes is pure chance.
2. **A missing bid or ask is `skipped_no_mid`, never a substituted number.** A
   settled loser genuinely trades at 0, so a zero standing in for "unreadable"
   is indistinguishable from real data — and here it would render as *"Kalshi
   closed 0%"*, the most flattering possible verdict on any call he made.

The read, `estimates.last_scored_call`, returns **one call or `None`**. No
`limit`, no offset, no list form. Decision 8's reason is that a list is a
scoreboard with extra steps: five rows on one screen is an average the reader
computes by eye, and eye-aggregation is still aggregation.
`/api/estimates/recent` stays score-free for the same reason.

## 7. It ships as a DISPLAY, never as a verdict

ADR 0044 was a registered study **stopped without result**. Accumulating "you
said 58%, Kalshi closed 61%" toward 30 and later reading a conclusion off it is
choosing the rule after seeing the answer. ADR 0065's 2026-08-29 amendment
already settles the shape: **`n >= 30` is a display gate; a verdict needs 300**,
or the registered floor of the measurement that owns it. At n = 30 the design
can resolve a calibration bias of roughly 26 points under a fixed-n test and
63.2 under the always-valid boundary — an instrument that can tell "betting the
wrong side" from nothing, and no more. And `n` counts **games/clusters**, not
rows.

So, binding on everything downstream of this commit:

- **No average, win rate, hit rate, streak or fitted trend over Joe's own
  calls, anywhere**, until n >= 30 scored with the per-group view alongside
  (`backend/bets.py:169-178`). One call at a time.
- A verdict from the 30 — "runs hot", "too tight", "well calibrated" — is a
  **separate pre-registration**, pre-registrar first. It is not authorised by
  this ADR and nothing here may be cited as having authorised it.
- In-play calls are scored, flagged (`is_in_play`), and must never share a
  denominator with pre-game ones. Different skill.

## 8. What this cannot establish

Scored against Kalshi's close and **never against the outcome**, this measures
*disagreement with the market*. It does not measure *correctness*, and no
quantity of it ever will.

**ADR 0037 is the precedent and it is exact.** On 255 settled `KXMLBHR 1+`
markets, the in-house model's disagreement with Kalshi had sd **3.72** points
while the model's own error was **4.04** — so Kalshi's error was not detectable
at all, and every apparent edge was our own noise. The same arithmetic applies
here with Joe in the model's chair: without settlements, **"Joe has an edge" and
"Joe is noisy" are not separable.** A large `call_clv_tenths` is exactly as
consistent with a sharp read as with a wild one.

This is stated in the module docstrings of `score_bet_estimate_calls`,
`last_scored_call` and `tests/test_call_scoring.py`, **before the screen
exists**, so the screen cannot be built as though it says more than it does.

## 9. What would falsify the diagnosis, and when the line closes

Ticket #11's diagnosis is that the estimate was not being logged **because it
was welded to a bet Joe places somewhere else**, and that a price-free screen
off the digest removes the obstacle.

**Falsification criterion, registered here before the screen ships:**

> **Zero estimates logged in the seven days after the log screen ships means
> #11's diagnosis was wrong and the line closes.**

The prior is one estimate ever. Seven days of a working, reachable, price-free
log screen with nothing typed into it means the obstacle was not the coupling —
it was that he does not want to type a number — and no further design on this
line is warranted. Closing means: no new screens, no re-wording, no reminder
push (ADR 0071 forbids manufacturing action anyway). The columns and the scorer
stay; they cost nothing and the record is the product.

The seven days start when the **log screen** ships, not when this commit lands:
until then there is nowhere to log a call from that this ticket built.

## 10. What was NOT implemented, and why

Of the 14 decisions, these are unbuilt here and are named so a later session
does not assume they exist:

- **3, 4, 5, 9** — the digest link, the price-free screen and where the verdict
  renders. Out of scope for this lane by instruction; this commit builds the
  backend they need.
- **2** — the pass/take distinction. Already free: `match_estimates` walks
  `absence_pending` → `unmatched_no_position` | `matched` and needs no extra
  tap. Nothing was added, and nothing had to be.
- **11** — refusing unscoreable markets at log time. The refusal belongs on the
  log screen's own POST path, where it can say why; the scorer's honest
  behaviour in the meantime is to leave such a call simply unscored (counted,
  never zeroed).
- **12** — *"not yet known whether you bet this"* is copy on a screen that does
  not exist yet.
- **13** — revisions: both are scored, which is what this commit does by NOT
  filtering `stated_probability_is_revised` out of the scorer. Named because
  the omission is the decision.
