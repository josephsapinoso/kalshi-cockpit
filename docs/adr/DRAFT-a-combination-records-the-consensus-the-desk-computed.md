# ADR DRAFT — A combination records the consensus the desk computed

Status: proposed
Date: 2026-09-09

Answers the question ADR 0125 left open under "What this does not decide"
("**The absent consensus column stays absent** … whether that is honesty or a
hole is a separate question and is not answered here"). It is a hole.

Moves no money, adds no ceiling, adds no refusal, adds no column, adds no
ordering. Recording only.

## Context

`manual_orders` carries eight frozen consensus columns (ADR 0082) so that a
hand bet records what the desk was showing when Joe tapped. On a combination
it recorded nothing:

    consensus_fair_tenths    NULL
    consensus_absent_reason  'combo_ticker'      4 of 4 real combination bets

The stated reason was that a combination **has** no devigged consensus:
`kalshi/discovery.JUNK_PREFIX` drops the `KXMVE` prefix, so no
`kalshi_markets` row exists for one, so no `recommendations` row and no
`fair_prices` row can. All of that is true. The conclusion drawn from it was
wrong.

**The desk computes a consensus for every combination it prices, and shows it
to him.** `parlays.price_card_on_kalshi` runs `joint_for(selected)` over the
legs the reader actually tapped and writes `fair_joint_conservative` on the
`priced` `parlay_lookups` row — the joint of each leg's `p_conservative`,
which is the worst-of-four conservative devig off the same sportsbook feed
that `consensus_fair_tenths` draws on for a single market. It reaches the
screen at `frontend/src/components/PriceOnKalshi.tsx`, rendered as
`Fair value … · hold …`, **one component above the buy button**
(`<ManualTicket … openLabel="Buy this combination">` is the next element).

Live, on the four real combination bets: `parlay_lookups.hold` = 0.170, 0.063,
0.209, 0.174, and the most recent (id 41) carries
`fair_joint_conservative = 0.33862` against 41c paid. Every one of those bets
was placed against a number that was on the screen and recorded as though no
such number existed.

**The cause was mechanical, and it is the third instance today of one shape.**
`_read_consensus` short-circuited on the ticker prefix before it tried,
because its lookup is keyed `(ticker, side)` against `recommendations`. The
join that would have answered — `parlays.priced_lookup_for` — already exists,
is already called in the same request (`routes._record_combo_position`,
ADR 0125), and its fields were discarded at the moment of persistence. Same
shape as ADR 0125 and as the hedge-provenance ruling of the same day: a join
that exists, is already called, and whose fields are thrown away.

### The second half: a reason code that meant two things

`'combo_ticker'` conflated **"this is a combination, we did not try"** with
**"we tried and there was nothing to find"**. A field that cannot separate two
different states is a NULL with extra steps — it costs a column, an audit
row and a reader's attention, and settles nothing. Under the old code every
combination collapsed into it, so the audit could not tell a bet the desk had
priced from one built in the Kalshi app.

## Decision

**1. A combination's consensus is read from `parlay_lookups`, in
`reserve_manual_order`, pre-submit, through the join that already exists.**

`_read_consensus` dispatches a `KXMVE` ticker to `_read_combo_consensus`,
which calls `parlays.priced_lookup_for(conn, ticker)` — the same query, with
the same "most recent `priced` row wins" rule, that the order route already
runs to wire up `/hedge`. `priced_lookup_for`'s SELECT gains `requested_ms`
and `fair_joint_conservative`; nothing else about it changes. A second SELECT
over `parlay_lookups` with its own freshness rule was refused: two matchers
that must agree is the failure `_read_consensus`'s docstring was written to
avoid.

**2. Two columns are written and the rest stay NULL.**

    consensus_fair_tenths   probability_to_tenths(fair_joint_conservative),
                            through `_fair_tenths`, so an out-of-range joint
                            REFUSES rather than clamping to 0 or 1000
    consensus_computed_ms   parlay_lookups.requested_ms — when the joint was
                            computed, the same instant `fair_prices.computed_ms`
                            names for a single, so `submitted_ms - computed_ms`
                            is staleness on both paths

`consensus_book_count`, `consensus_anchored_on_sharp`,
`consensus_fair_price_id` and `consensus_link_id` stay NULL: they are per-leg
on a combination and there is no single value. NULL already means "not known".

`consensus_edge_tenths` stays NULL. It is the desk's **fee-net** edge; the
parlay path computes a **fee-free** hold. Writing the latter into the former
would put a gross number in a column whose name promises a net one.

The lookup's `hold` is not copied. Hold is `1 − fair × offered_decimal`, a
ratio against the ask as it stood *at lookup*; the row already carries the ask
he *paid* (`limit_price_tenths`), so fair value plus that price gives the hold
on the bet that happened, while the lookup keeps the hold on the quote he was
shown. Freezing the shown ratio here would be a stale denominator on a money
row.

**3. `'combo_ticker'` becomes a closed historical set.** Nothing writes it any
more. It keeps its meaning — "the desk never looked" — for the four rows that
carry it, and no row written since can honestly claim it. Three combination
absences replace it, each a different fact:

    combo_no_priced_lookup       no `priced` lookup minted this ticker: he
                                 bought a combination the desk did not price
    combo_side_not_priced        the bet is on the combination's NO side
    combo_unreadable_fair_value  the stored joint is absent or outside [0, 1]

An AST test asserts no call site passes `ABSENT_COMBO` to `_absent`, and that
the constant's *value* is unchanged so the four live rows stay interpretable.

**4. A NO-side combination refuses rather than complementing.** The lookup
prices YES only. `1 − joint` is arithmetically available and is **not** the
conservative devig for NO: worst-of-four is conservative in the direction it
was taken, so its complement is anti-conservative — rule 2 inverted, and an
optimistic number on a money row.

## Consequences

- A combination bought through the desk records the fair value that was on the
  screen when Joe tapped, on the same 0–1000 integer scale as the price paid.
  The hold on the bet that happened is recoverable from the row.
- `manual-orders-audit`'s absent-reason grouping now distinguishes "priced by
  the desk" from "built elsewhere". Its `fair_value_present` count will rise
  for combinations; **the four `combo_ticker` rows are not comparable to rows
  written since** and any measurement over these columns must say so.
- No behaviour change on the order path. No new ceiling, no new refusal,
  nothing that changes whether an order is sent (ADR 0112: the hand-bet path
  has no brakes and none were added). The read runs before `BEGIN IMMEDIATE`,
  as it already did, and `consensus_snapshot` still swallows its own failures,
  so the worst case remains NULL columns and a stated reason.
- No schema change. `parlay_lookups.fair_joint_conservative` and
  `requested_ms` have existed since the table did; `schema.sql` is edited for
  its comments only, which asserted that a combination has no consensus at all.
- `gate.py` still never reads `manual_orders` (ADR 0063), so nothing here
  moves the live-trading interlock.

## What this does NOT decide

- **Nothing is backfilled.** The four `combo_ticker` rows stay as they are.
  The joints are still in `parlay_lookups` and could be joined at analysis
  time, but writing them into the money rows now would put a number into the
  record that no clock produced at the moment of those bets.
- **Nothing about whether the consensus is RIGHT.** `beta = −0.141`: agreement
  with this consensus is not evidence of correctness. It is a per-row fact and
  never an ordering (ADR 0071). No sorting, scoring or "best" was added.
- **Nothing about a fee-net edge for a combination.** That needs the
  combination fee model, which ADR 0027/0028 leave as a ceiling rather than a
  quote. `consensus_edge_tenths` stays NULL until someone decides it.
- **Nothing about per-leg provenance.** Whether a combination's book count or
  sharp anchor should be summarised (the minimum? the worst leg?) is a real
  question and is not answered by picking one silently.
- **Nothing about the frontend.** `PriceOnKalshi.tsx` and `ManualTicket.tsx`
  are untouched; what he sees is what he already saw.
- **Nothing about `parlay_positions`.** Its provenance column belongs to the
  registrar's successor registration of 2026-09-09, not here.
- **Nothing about the `/api/parlays/bid` path**, which stays disarmed
  (ADR 0115).
