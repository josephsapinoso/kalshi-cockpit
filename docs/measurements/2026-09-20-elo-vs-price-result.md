# Result — Elo vs Kalshi's game price: NOT RUN

**Verdict: NOT RUN, closed 2026-09-24 on Joe's (A) to #146.** No row of the
record was read, locally or on live. The census, `G`, `G_eff`, and
`sigma_model_hat` do not exist.

This file sits at the path the registration's §8 fixed in advance, so a
reader looking for the result finds the reason there is none.

Registration: `2026-09-20-preregistration-elo-vs-kalshi-price.md`, as amended
by Amendment 1 (commit `7b0a982`). Ticket: #115.

## Why it was not run

1. **A PASS was impossible by construction (Amendment 1, A1.1).**
   - DR-1 gates on `G_eff >= 300` under two-way team clustering.
   - A Kish effective count over team clusters cannot exceed the number of
     teams: MLB 30, NFL 32, WNBA fewer than 20. Pooled, it is about 74 at most.
   - Every arm therefore ends CLOSED (via DR-0) or UNDERPOWERED, and Stage 2
     can never execute.
   - The floor was not lowered. At `G_eff = 30`, the sampling term alone
     requires `sigma_kalshi^2 > 0.645 x Var(d)`, which is a near-blind test.
2. **The data path had been changed underneath it (A1.7).**
   - The `odds_snapshots` closing-line prune was armed on 2026-09-23 (#139).
   - It deletes intermediate reads, which are the same rows §2.2(3) uses to
     refuse a fixture whose snapshots disagree on home/away.
   - A disagreement confined to the deleted rows cannot be reproduced from
     the pruned table. By A1.7 the look would therefore be refused unless it
     ran on a pre-prune copy, and no such copy has been confirmed to exist.
3. **§8 already said no build follows either way.** A CLOSED leaves
   `backend/model/elo.py` reached by tests only; a PASS buys only a successor
   registration. Running Stage 1 would have taken a `VACUUM INTO` copy of a
   6.5 GB file on the live volume to produce a CLOSED that changes nothing.

## What this does and does not establish

- **It establishes nothing about Elo, Kalshi, or the moneyline path.** It is
  not a CLOSED. ADR 0038's "in-house model vs Kalshi's price" row stays as ADR
  0036/0037 left it, with no second instrument added.
- `model_probability` stays NULL, and CLAUDE.md's "one signal, not two"
  paragraph is unchanged.
- **Reopening needs a successor registration**, with a clustering floor
  that team counts can reach, and a data path that does not read rows the
  prune deletes. It may not revive this registration against a larger record
  (§7).
