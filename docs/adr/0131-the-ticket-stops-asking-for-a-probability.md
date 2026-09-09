# ADR 0131 — The ticket stops asking for a probability

**Date:** 2026-09-09
**Status:** Accepted.
**Supersedes ADR 0065 §2** — the manual ticket's P(YES) precondition and its
masked ask. ADR 0065's other decisions stand: the standalone `/estimate` form
stays retired (§2, third paragraph; killed for good by ADR 0094 §11), the
`bet_estimates` embargo (ADR 0044) is untouched, and §3's display floor
(`n ≥ 30`, never a verdict floor) is unaffected.

## 1. What happened

Joe, who is the operator and the only user, said it plainly:

> "what is even the point of the (p)yes score entry? I don't need it. it just
> gets in the way."

That is the trigger. It is not the whole justification, because a decision
recorded in an ADR should not have to be re-argued from a preference — and
this one does not have to be.

**ADR 0065's own §1 records that two reviewers disagreed.** The red-team
position was that *an unscored form is a speed bump a user learns to type
through* — the study is stopped, nothing scores the number. It lost on exactly
one factual premise, quoted from §1:

> The premise changed on 2026-08-22: `backend/bets.py:bet_clv()` shipped
> (`3067bf2`), scoring Joe's own bets against Kalshi's close. **A pre-bet
> P(YES) now has a consumer** — it can sit beside the bet's CLV on `/bets`.

**That consumer was never built.** `backend/bets.py` does not read `p_yes_bp`;
nothing in the tree SELECTs it. This is not a new finding — it was written
down twice, in `frontend/src/components/Footer.tsx` ("this comment claimed
'where it has a consumer (bet_clv)' until 2026-08-29 and that was never true")
and asserted on the source by `scripts/inspect_live_db_money.py` ("none of
them selects `p_yes_bp`"). Both were re-verified before this change.

So the premise that decided ADR 0065 is falsified, and the state today is
precisely the one the red-team described. **The red-team argument is what
actually held up.**

The masking existed to prevent anchoring — seeing the ask first drags the
typed number toward it — and that mechanism is real. It buys something only if
the number is later scored against something. It is not.

## 2. The decision

**The manual ticket asks for no probability, and the ask is never masked.**
There is no path to the confirm control gated on a typed number, because there
is no typed number. Opening the control reads the live book.

**Removed entirely, not made optional.** An optional field he never fills is a
slower version of the same complaint, and it would leave every screen, type
and test carrying a branch nothing takes.

- `POST /api/manual-orders` no longer accepts `p_yes_bp` on
  `ManualOrderRequest`. A stale client that still sends the key is **not
  refused** — Pydantic ignores an extra field — and the row records NULL,
  which is the truth about a number this server did not ask for.
- `/api/manual/market/{ticker}` no longer serves `p_yes_required`. A flag
  saying a probability is required, on a route that does not require one, is
  the "one predicate with two spellings" failure this repo has recorded four
  times.
- The ticket's `priceAlreadyVisible` prop is gone from every surface, and
  `lib/quoteVisibility.askIsVisible` went with its only caller.
  `quoteVisibility` itself stays: the quote strip is still its reader, and it
  is still the single authority on whether the strip shows a price.

**`manual_orders.p_yes_bp` survives, nullable (schema v35).** The `NOT NULL`
and the `CHECK (p_yes_bp BETWEEN 1 AND 9999)` are both relaxed —
`CHECK (p_yes_bp IS NULL OR p_yes_bp BETWEEN 1 AND 9999)` — by a table
rebuild, because SQLite alters neither in place. The range still binds on a
value that is there.

**NULL means "not asked", and there is no sentinel.** A `p_yes_bp = 0` would
read as "he thought this had no chance", which on a money row is a lie rather
than a gap. This is the same rule the consensus snapshot columns beside it
already follow, and CLAUDE.md's standing convention: unreadable resolves to
`None`, never `0`.

**The rows already written keep their real values.** They are history and
history is the product. Nothing deletes, backfills, zeroes or rewrites them,
and the migration test asserts the values survive the rebuild by name.

## 3. This is not a risk control, and none was touched

`p_yes_bp` was a **data-collection gate**, not a brake. The hand-bet path's
real interlocks are unchanged and still enforced server-side: the desk
lockout, idempotency, the KXMVE acknowledgement, the price ceiling, depth at
the ask, the netting guard, the shard collateral check (the venue's rule) and
reserve-then-check. ADR 0112 removed the five ceilings on Joe's word and no
ceiling of ours bounds a hand bet; **this change adds none and removes none of
what remains**.

`backend/gate.py` still never reads `manual_orders`, and this change does not
go near it.

## 4. What this does NOT decide

- **Nothing about whether calibration is worth measuring later.** If a
  consumer is ever built, asking for a probability again is a new decision
  with a new registration — pre-registrar first, and the anchoring argument
  ADR 0065 §2 makes would apply to it in full. It is a good argument; it was
  attached to a number nobody read.
- **Nothing about `bet_estimates` or ADR 0044's embargo.** The stopped study's
  log stays terminal, its rows carry `is_study_row = 1`, and they are neither
  scored nor served (ADR 0044 Amendment 3).
- **Nothing about ADR 0094 §11's killed log screen.** The standalone estimate
  form was killed by Joe on 2026-09-05 and stays killed; this ADR does not
  revive, replace or reopen it.
- **No backfill.** The hand-bet rows that carry a typed probability keep it
  and are not re-derived; rows written from here carry NULL and are not
  invented.
- **Nothing about `/estimate`'s existing record.** That page keeps the entries
  already logged and their revision flags, unchanged.

## 5. How it was verified

- `tests/test_store.py::TestTheTypedProbabilityBecomesOptional` builds a v34
  volume by running the step's own undo, seeds two hand bets with distinctive
  probabilities, and asserts: the v34 fixture really did refuse NULL (so the
  rest is not passing against an already-nullable table); the migration
  carries every row, id and value; a NULL row is accepted afterwards and reads
  back as `None`; the range still binds; `client_order_id`'s UNIQUE and the
  side CHECK survived the rebuild; and the step replayed after full success
  keeps the rows — the crash point a rebuild is normally not idempotent at,
  which is why v4 needs a completion marker and this step does not.
- `tests/test_manual_orders.py` inverts the precondition pin: a body with no
  probability is accepted **and the row's `p_yes_bp` is NULL** — the
  distinguishing consequence, not merely the absence of a 422.
- The frontend pins in `test_manual_orders.py`, `test_buy_controls.py`,
  `test_quote_visibility.py` and `test_tab_ledes.py` are inverted rather than
  deleted, per `tasks/lessons.md` (2026-09-09): a deleted test leaves no
  evidence the question was ever settled.
