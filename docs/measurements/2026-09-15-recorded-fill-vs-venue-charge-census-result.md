# Result — the recorded hand-bet price against the venue's: the one look

Registration: `2026-09-10-preregistration-recorded-fill-vs-venue-charge.md`
and its Amendment 1 (2026-09-11). Trigger (A8): the first session after the
population reached ten real manual orders. Met 2026-09-15 with 13.

**Destination.** §10 fixed the result's filename as
`2026-09-10-recorded-fill-vs-venue-charge-result.md`. This file carries the
date the look was taken instead, so the two documents sort in the order
they happened; it is the registered result and no second one exists.

Date of the look: **2026-09-15T15:42:38.084Z**, once, through
`scripts/census_recorded_fill_vs_venue.py --db /data/cockpit.db` on the
live box at `b3fc100`, invoked by path over ssh. The harness implements the
registration's population, precedence, classes, columns and refusal branch
and is pinned by `tests/test_census_recorded_fill_vs_venue.py`. **This look
is now spent.** Re-running is a new look and needs a dated amendment
recording that this one was seen (§9, A8).

Every number in §1–§3 is copied from the harness output. One figure below
(the unknown row's `status`, §2) comes from `manual-orders-audit`, read
separately, and is not evidence this census uses. No number here is a
mean, a proportion, an interval or a rate.

Audited before entry by the measurement-skeptic against the registration
and the raw output; its findings are applied here, and the first draft's
errors are listed in §8 so they are not re-derived.

---

## 1. The population, at the snapshot instant

```
snapshot            2026-09-15T15:42:38.084Z
n_real_orders       13     (dry_run = 0 AND kalshi_order_id IS NOT NULL)
trigger_met_at_10   1
```

Thirteen orders on thirteen distinct tickers, one each (section B of the
output). Two of those tickers sit in the same KXMVE collection, and the
thirteen arrive in four sittings across four days. No standard error is
computed anywhere here (§4 of the registration), so that is reported for
legibility, not as independence.

**Every row is `S1` — a `KXMVECROSSCATEGORY-SHARD1` combination, and every
order is `side = yes`. `S2` (single markets) is empty.** Every statement
below is a statement about YES combinations, which A5 says to read first:

> On a KXMVE book where one price is resting, an IOC buy at that level has
> no room to improve, so `sent == venue` is near-mechanical. Under the
> corrected reading that is not even weak evidence about a recorder — it is
> a statement about book depth, which is already known.

## 2. Coverage — the refusal branch did not fire

```
                       S1 (KXMVE)   S2   pooled
n_rows                 13           0    13
n_joined               12           0    12
unjoined_zero_fill     0            0    0
unjoined_unknown       1            0    1
n_source_fills         12           0    12
n_source_create_resp   0            0    0
n_multi_fill           0            0    0
```

`unjoined_unknown = 1 < n_joined = 12`, so A4.4's refusal branch (coverage,
not the recorder) does not fire and the comparison is computed.

The one unknown row is the 2026-09-09T00:34:30Z order, which predates v40
(no `venue_fill_count`) and has no `fills` row. `manual-orders-audit` reads
that row's status as the population's one `unfilled`. That instrument is
outside this census and the status column is not evidence this census
uses; A4.4's two causes (it did not fill / the poller missed it) remain
indistinguishable on a pre-v40 row, and if the cause were poller coverage
rather than a non-fill, §11.7 (the completeness of `fills`) would apply to
the other twelve rows as well.

Every joined row is `fills`-sourced; none is on the fallback. Six rows
carry both endpoints (the six post-v40 orders, 2026-09-15). No order has
more than one row in the `fills` mirror (`n_multi_fill = 0`); the census
cannot distinguish that from a fill the mirror never received (§11.7), and
the harness does not compare the summed fill quantity against the order's
`count`.

## 3. The comparison — H1 stands on every row that carries a venue price

H1 (A3, in the corrected names): `sent_tenths >= venue_tenths` on every
joined row.

```
                                  S1 (KXMVE)   pooled
n_comparable                      12           12
n_equal                           11           11
n_sent_above                      1            1
n_sent_below                      0            0
max_abs_sent_minus_venue_tenths   22.0         22.0
sum_abs_sent_minus_venue_tenths   22.0         22.0
n_side_convention_ambiguous       0
n_side_convention_undecidable     0
n_both_endpoints                  6
n_endpoints_disagree              0
```

- **`n_sent_below = 0`** on the 12 rows that carry a venue price, all of
  them `fills`-sourced and all classified `comparable`. The thirteenth
  carries no venue price and is not adjudicated, and never will be. A7.3
  opens nothing.
- **`n_equal = 11`**, equal to the tenth (exact on this run: every joined
  row is single-fill, so the count-weighted mean is the fill price itself).
- **`n_endpoints_disagree = 0`**: on the six rows carrying both the `fills`
  price and the create response's `average_fill_price`, the two readers
  agree within A7.4's 1-tenth tolerance. All six are single-fill YES rows,
  where the side convention that A9 §10–§11 flags cannot bite, so this is
  not evidence that either reader is right. A7.4 opens nothing.
- **No side-convention artifact** was classified, and none could have been:
  all thirteen orders are `side = yes`, so A4.3's rule was never exercised.
- **`n_sent_above = 1`, at +22.0 tenths per contract**, on the second order
  of 2026-09-08: the sent price sat above the venue's execution price. With
  `n_sent_above = 1` this row is the entirety of H2, not a selection from a
  distribution; §6.1's ban on a maximum-row callout is not engaged. The
  census cannot say whether the gap is venue price improvement, a stale or
  differently-derived desk ask on a combo, or the snap to the price grid —
  H1's own provisions (i) and (ii), which a *falsifying* row would separate
  and a confirming row does not. It is one observation, it is the one row
  with no second endpoint to check it against (`create_venue_tenths` is
  NULL on it), and the population cannot say how often.

## 4. The per-row table — withheld, and that is a deviation from §10

§10's outcome row for the realised branch specifies the counts **and** the
time-ordered per-row table. The table is withheld here under Joe's
2026-08-20 ruling that row-level account data — his fills, sizes and
prices — does not enter this public repo, even sanitised, and that adding
any is asked first. **That is a deviation from §10, recorded as such.** The
verbatim output, rows included, is at
`data/2026-09-15-recorded-fill-vs-venue-census-output.txt` (gitignored),
and the counts above are copied from it. If Joe wants the thirteen rows in
this file, that is one paste and his call.

## 5. What this pins, and only that

**E2 — sent price against fill price — is pinned for this population.**
CLAUDE.md's `/hedge` paragraph carried E2 as "too LOW, 0–10 tenths, ~0 on
a one-level KXMVE book". On 12 joined rows: 11 at 0, one at +22 tenths per
contract. **The stated range 0–10 is exceeded by one row, and the spine is
corrected to the counts.**

What was observed is the sign of `sent − venue` on one row: +22 tenths per
contract, the sent price above the venue's. That is E2's registered
direction — the stake's price factor alone is at or above the true one,
which by that term alone makes a displayed hedge figure too LOW. **This
census says nothing about the direction the displayed figure errs in
overall (A6.2)**: E1, E3 and E4 are unmeasured, and it establishes no
ranking among the four — A6's ordering of E3 above E2 predates ADR 0145,
after which E3 stands at ~1 tenth a position, so E2's 22 tenths a contract
may be the largest *measured* term. The census does not read
`parlay_positions`; `_record_combo_position` still feeds
`parlay_positions.stake_tenths` from the sent price (`routes.py:4318`,
deferred by ADR 0143 §4), and the order in question predates the position
recorder, so no position row carries this gap.

Eleven of twelve joined rows show `sent == venue`. On a KXMVE book, where
this repo has read 40 of 40 with no resting YES side, that is
near-mechanical (A5) and is a statement about depth, not about the
recorder — and the census read no book, so it establishes the depth of
none of them.

## 6. What it does NOT establish (§11 as amended by A9, checked against the output)

1. Nothing about whether the bets were good; nothing about Joe.
2. Nothing that is an estimate: no rate of anything, at this n or any n
   this population will reach.
3. Nothing about future fills: a thin-book stratum cannot speak for a deep
   one, and twelve orders in four sittings say nothing about the next one
   (§11.3).
4. **A zero in the combo stratum is close to mechanical and is not evidence
   the recorder is accurate** (§11.4). Eleven equalities on a book with no
   resting YES side are what a one-level book produces whether or not the
   recorder is right.
5. Nothing about the hedge lock's correctness or the direction it errs in.
   E2 is one of at least four terms (A6), and this census ranks none of
   them.
6. Nothing about fees; the column was not read.
7. Nothing about which venue-price source is correct beyond A7.4's branch,
   which did not open; the six agreements are on rows where the two readers
   could not differ by the open side question.
8. **Nothing about the completeness of `fills`** (§11.7). V is a
   count-weighted mean over the rows the mirror holds; an absent fill is
   not a fill that did not happen, and it would change V and `multi_fill`
   with no visible symptom.
9. **Nothing about the side convention of `average_fill_price` for a `no`
   order** — every order in the population is `yes`. A4.3's rule was never
   exercised.
10. Nothing for or against ADR 0143, in either direction (A7.2).
11. Nothing that authorises a change to money-touching code (§8.4).
12. Nothing about the contract-count factor of the stake.
13. **Nothing about single markets.** S2 is empty. The census answers
    nothing about a `KXMLBGAME` or `KXNFLGAME` hand bet, and a future S2 row
    is a new look under a new amendment.
14. Nothing about the one unknown row: whether it filled outside the
    poller's window or not at all is not answerable here.
15. Nothing about why the one non-zero row is non-zero (§3).

## 7. Consequences

- **§8.4 stands.** No money-touching code moves.
- **A7.3 and A7.4 open nothing.** No ADR from this look.
- **CLAUDE.md's E2 line is corrected** from "0–10 tenths" to the counts:
  0 tenths/contract on 11 of 12 joined rows, +22 on 1, n = 12, S1 only,
  every order YES; counts, not a rate, and nothing about the next fill. The
  two sentences beside it that the number contradicted ("none measured on
  a single row"; "inside a few tenths a contract") are corrected with it.
- **The census item in `tasks/NEXT.md` closes.** A second look needs a
  dated amendment.

## 8. What the first draft got wrong, so it is not re-derived

Found by the measurement-skeptic before entry:

- It said the sent price overstating the stake makes the hedge figure run
  *high*. An overstated `S` in `W − S − Wq − fee` makes the figure **low**;
  the sign was flipped, and it was the reassurance-shaped direction.
- It asserted a `parlay_positions.stake_tenths` figure for the non-zero
  row. The census never reads that table, and the row predates the
  position recorder.
- It inferred "a one-level book" from `sent == venue` on eleven rows. A5
  runs one way only; equality does not establish depth.
- It called the gap "the venue *can* fill below the sent ask". Three
  readings fit the row and the census separates none.
- It said E2 is "not the largest" term. That ordering predates ADR 0145.
- It omitted §11.3, §11.4 and §11.7 from the caveat list; §11.7 is the one
  that could overturn V.
- It presented withholding the per-row table as compliance with §6.1; §10
  is the binding clause and this is a recorded deviation from it.
