# ADR 0103 — Sized to zero is its own state, and NO EDGE means what its caption says

**Status:** Accepted; ordinal 0103 taken in the merge commit after `git fetch`, per `docs/adr/README.md`.
**Date:** 2026-09-03.
**Decides:** GitHub #25 on `josephsapinoso/kalshi-cockpit`, resolved by Joe
2026-09-03 as **25C**. Built in Lane B.

## 1. Context

`/api/board` bucketed rows on `suggested_contracts`: `> 0` → `surfaced` or
`expired`; else a `suppressed_reason` → `suppressed`; else → `no_edge`, chip
**NO EDGE**, caption *"no edge after fees"*.

The gate's own actionable predicate is on a different column —
`suppressed_reason IS NULL AND reference_contracts > 0` (`gate.py:330`,
`POPULATIONS["actionable"]`), sized at the fixed $1,000 reference profile
(ADR 0015 §3). At the 2026-09-01 re-audit every row the gate has ever counted
actionable — **51 rows across 15 games** — had `suggested_contracts = 0`,
because quarter-Kelly at the observed balance buys none. So the Board filed
the entire actionable population under NO EDGE, two inches below a headline
that counted them (`docs/measurements/2026-09-01-actionable-population-
reaudit.md`).

The ticket's own re-examination found the chip **under-determined rather
than lying**: every one of the 51 carries a `reason_text` ending "No edge",
and every one is also unbuyable at the deposit. Both statements are true.
Which the chip asserts is a decision about what the screen is *for*, and
that is why it went to Joe rather than being fixed as a bug.

Joe's options were: **A** — reword the chip, keep the buckets (leaves the
headline and the rows disagreeing about what "actionable" means); **B** —
bucket on the gate's test (labels as actionable a bet that cannot be
placed); **C** — a third chip that names the actual state. He chose C.

## 2. Decision

1. **`/api/board` has a fifth bucket, `sized_to_zero`**: rows with no
   suppression reason, `suggested_contracts == 0`, and
   `reference_contracts > 0`. It is tested *after* suppression — a refused
   row with a reference size is refused — and *after* the `suggested_contracts
   > 0` branch, so a row that sizes to a contract after a top-up leaves the
   bucket by the branch that already existed, with no code knowing about the
   move. It sorts newest-first like `no_edge`, is returned under the same
   `include_suppressed` flag, has its own `counts.sized_to_zero`, and is
   counted in `slate.returned`. A NULL `reference_contracts` falls to
   `no_edge`, exactly as the gate's predicate puts a NULL there: an unreadable
   size is not a bet.
2. **`no_edge` now means what its caption says.** A row there has no bet at
   the deposit *or* at the reference profile.
3. **`population_counts(conn, 0)` is not forked.** The Board buckets
   downstream of the serialised row, on the same column the gate reads, and
   `tests/test_board_sized_to_zero.py` pins that on a fixture with every row
   unsized, `counts.sized_to_zero == population_counts(conn, 0)["actionable"]`
   — and in general that the gate's count equals `sized_to_zero + surfaced +
   expired` over an in-window slate. The two numbers cannot drift silently.
   `backend/gate.py` is byte-identical to `main`.
4. **The screen names the state.** `SlateRow` gains a `SlateState`
   `"sized-to-zero"` with the chip **SIZED TO ZERO**, drawn in foreground ink
   with a plain border — no `text-positive`, no tone colour in either
   direction, because colour is a claim and this row's claim is a fact about
   two bankrolls. Its caption says both halves in words: *"reference size N
   at $1,000 · sized to 0 at your balance"*. Either half alone is the
   misreading the chip exists to end — a size to buy, or NO EDGE under a
   different label. No cost is shown and no buy affordance is added beyond
   the hand-bet door every row already has (ADR 0063).
5. **The Board's copy reconciles with its buckets.** A **Sized to zero**
   tile sits beside **No edge**; the header names three kinds of refusal
   rather than two; the *"N of M decisions ever recorded"* sentence says the
   gate counts at its reference bankroll and points at the SIZED TO ZERO
   rows as the ones it counts that the deposit buys none of; the rest-of-the-
   slate paragraph says the same when any such row is present. The hidden
   count includes the new bucket.
6. **The `$1,000` is read off the server.** `slate.reference_bankroll_dollars`
   carries `REFERENCE_BANKROLL_DOLLARS`, so the caption cannot go on printing
   a figure the constant has moved away from.

## 3. What this does not establish

- **It makes nothing bettable.** `suggested_contracts` is 0 on every row in
  the new bucket by definition. `POST /api/orders` re-derives sizing inside
  the request and is untouched; `ORDERS_ARE_DRY_RUNS` is untouched; the
  hand-bet route (ADR 0063, 0073) is untouched.
- **`actionable` is unchanged.** The gate's predicate, its 300-game floor,
  and `population_counts` are byte-identical. This ADR renames nothing the
  gate does; it stops the Board describing the gate's population in words
  that contradict the gate.
- **It relaxes nothing.** Suppression still outranks sizing, the three
  rules in `CLAUDE.md` are untouched, and no row is ranked by its reference
  size or its edge — the bucket sorts by freshness, because an ordering is a
  claim (ADR 0071 §2.5) and `beta = -0.141` says the claim would be wrong.
- **It does not say the reference profile is the right one to count at.**
  That is ADR 0015's decision and stands or falls there.
- **It does not test the rendered page.** The frontend pins are over source
  text plus one Node execution of the caption function; nothing here shows
  the chip is legible or the tile fits at 390px. Opening the page does that.
- **It does not touch the Gate screen's count** (`routes.py` `/api/gate`),
  the Playbook, or the Discord digest, all of which read `population_counts`
  or their own aggregates and keep the three-population vocabulary
  (`actionable` / `no_edge` / `suppressed`). The Board's five buckets are a
  finer partition of the same rows, not a different one.

## 4. Consequences

- A reader of `/board` can now tell "the price is fair" from "you cannot
  afford a contract", which lead to different actions — stop looking, or
  the bankroll is the binding constraint. That was the question underneath
  the ticket.
- Tests that flatten the Board's four named buckets to "every row"
  (`test_api.py`, `test_demo_sizes_at_deployed_caps.py`,
  `test_ledger_paging.py`, `test_ledger_consensus_provenance.py`,
  `test_observability.py`) stay green because no fixture they use writes a
  row with `reference_contracts > 0`, `suggested_contracts = 0` and no
  reason — the demo seeder writes the two columns equal. `test_observability`'s
  `mixed_app` does hold one such row; its Board assertion is an `all(...)`
  over the flattened list and now sees one row fewer. Those files are outside
  this lane's ownership and are named here so the next lane extends their
  bucket tuples to five rather than rediscovering why one row is missing.
- The `/api/board` docstring and `SlateRow`'s docstring record the defect
  and the fix in place.
