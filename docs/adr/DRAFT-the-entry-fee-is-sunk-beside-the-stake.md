# DRAFT — The entry fee is sunk beside the stake, at the read site

Written by lane C (`lane-c-hedge-entry-fee`) with no ordinal; the number is
taken at the merge commit after `git fetch`, per `docs/adr/README.md`.
Reserved for **0145** in `tasks/LANES.md` (0144 is lane B's). **No schema
change.**

Date: 2026-09-11
Status: proposed
Scope: `backend/core/hedge.py`, `backend/hedge.py`, the `/hedge` payload and
its two consumers (`HedgePositions.tsx`, `discord.py` via `NOTES`), the
record form's help text. `parlay_positions`, `manual_orders`,
`_record_combo_position` and every order path are **untouched**.

---

## 1. The defect

`parlay_positions.stake_tenths` is written by `_record_combo_position`
(`backend/api/routes.py:4318`) as `contracts * fill_price_tenths` — the
contracts at the ask the desk sent, and **no fee**. `core/hedge.py`'s `Rung`
nets both branches of every hedge size against that stake:

    if_wins  = return - stake - cost(n)
    if_loses = n * $1  - stake - cost(n)

So every branch, every floor and `Lock.is_guaranteed_profit` read too high by
exactly the taker fee Joe already paid to enter the combination. This is E3
of the 2026-09-11 audit (census registration Amendment 1 §A6; CLAUDE.md's
`/hedge` paragraph): **~17 tenths of a cent per contract at 41c**, the largest
of the four error terms on the figure and the only one that ran optimistic.
It is the size of the smallest floors the alert fires on, so a displayed lock
of a cent or two could have been a true loss pushed to the phone as a
guaranteed gain.

Found by reading source, not data. It has done **no realised harm**:

    parlay_positions on live      4 rows, all status = 'open'
    legs                          12 of 12 resolved by the venue; each ticket has a lost leg
    assess() on all four          STATE_DEAD — never reaches the lock path
    notifications kind hedge_lock 0, ever

`/hedge` has never produced a lock in its life. All four rows are permanently
dead, so the defect cannot fire on them in future either. (Read 2026-09-11 by
the partner's sub-agents over `flyctl ssh`, read-only, bounded by table.)

## 2. What the venue charges, and how the record knows

The fee on a KXMVE taker fill is charged **once per order, per combo contract,
at the combo's own price**: `ceil(k · C · P · (1 − P))`.

- `docs/measurements/2026-08-18-combo-fill-fee-look-result.md`, **n = 8**
  `KXMVECROSSCATEGORY` taker buys: every charge within 0.19% of `k · D` with
  `D = C · P · (1 − P)` on the combo's price; the per-leg-count forms (M9/M10)
  matched **zero** rows; M11 (a per-leg-price schedule) is untestable because
  fill-time leg prices are unrecoverable. Implied `k` **0.070041–0.070548**,
  no row at or below 0.070 — the flat 0.070 undercharged four of eight.
- `docs/measurements/2026-09-09-fee-alarm-replayed-over-every-hand-fill.md`,
  **62** more `KXMVECROSSCATEGORY` fills: mean implied `k` 0.070127,
  `combo_taker_fee` headroom +1.4%, **0** rows charged above the 0.071
  ceiling.
- `tests/fixtures/portfolio_fills_redacted.json`: one `fee_cost` per fill,
  computed off the combo price, no leg multiplier on the row.

So `COMBO_TAKER_COEFFICIENT = 0.071` (`backend/core/fees.py:372`) is the
coefficient, and on all 70 observed combo fills it **overstates** the venue's
charge by 0.6–1.4% and understates it on none. The scope caveat carries
verbatim: those rows are one account, prices ≤ $0.228, the deep tail of a fee
curve that peaks at $0.50; nothing bounds the deviation at a mid price.

**The position row stores neither `C` nor `P`.** It stores `stake = C · P`
and `return = C · $1` (`routes.py:4318-4319`). The fee collapses to

    fee_dollars = 0.071 · stake_dollars · (1 − stake / return)

which is algebraically identical to `combo_taker_fee(P, C)` and needs no
contract count — pinned by
`tests/test_hedge_arithmetic.py::TestTheEntryFeeAlreadyPaid`, which asserts
equality with the per-contract form across six `(C, P)` pairs.

## 3. Decision

**Sink the entry fee beside the stake at the read site. Do not change what is
stored.**

1. `backend/core/hedge.py` gains `combo_entry_fee_tenths(stake_tenths,
   return_tenths)`: the collapsed form above, `COMBO_TAKER_COEFFICIENT`,
   rounded up onto `FEE_GRID_DOLLARS` and then up again onto integer tenths —
   both in the direction that lowers the displayed floor. `None`, never `0`,
   on a ticket the arithmetic cannot read; `ticket_refusal` refuses the same
   tickets a step later, so `None or 0` at the call site manufactures nothing.
2. `backend/hedge.py::assess` computes the sunk stake once —
   `stake_tenths + entry_fee_tenths(position)` — and passes it to `hedge_lock`
   and `derisk` alike. One number, not one per state.
3. **Only `source = 'kalshi_combo'` rows.** A sportsbook slip's vig is inside
   the odds Joe typed; charging a fee on top would double-count it. The record
   form (`RecordParlay.tsx`) now says, on the combo option only, that the
   stake is contracts times price before the fee, because the arithmetic adds
   the fee itself.
4. The payload carries `entry_fee_display` (a rendered string or `null`) and
   the screen shows it beside the stake — `$1.64 + $0.07 fee → $4.00` — so
   the stake line and the lock figure reconcile. `stake_display` itself is
   unchanged: it is still the recorded intent, and it still matches the
   `manual_orders` row it came from.
5. `NOTES["upper_bound"]` (key kept for the wire) stops saying the entry fee
   is left out and says at what rate it is charged and which way that errs.
   The killed one-sided words (ceiling, floor, can only be smaller/larger,
   exact) stay killed and stay guarded.

### Why the read site and not the column

The handoff framed E3 as "the same `_record_combo_position` rewire ADR 0143
§4 deferred, now with a non-cosmetic reason", i.e. a storage change that
would make a mixed-basis column because all four real rows predate schema
v40. That framing was wrong in a useful way: **the missing number is a
function of two columns already on the row.** No migration, no backfill, no
mixed basis, and the four NULL-venue rows are handled identically to any row
written tomorrow. ADR 0143 §4's deferral — rewiring `stake_tenths` to the
venue's average *price* — is a different question (E2, the sent-vs-charged
stake) and stays deferred.

### Why compute rather than read `venue_avg_fee_dollars`

Since schema v40 `manual_orders` keeps the venue's own
`venue_avg_fee_dollars`. It is not used here, on four grounds, any one of
which would do:

- **NULL on 4 of 4 rows that exist.** A venue-first path is a computed path
  on every real row today.
- **No id-level join.** `parlay_positions` has no `manual_order_id`;
  `_record_combo_position` never receives one. There is an exact-equality
  join on `(combo_ticker, placed_ms) = (ticker, submitted_ms)` — both sides
  are the same Python value at `routes.py:3887/:3894/:3961` — but a hedge
  figure that depends on an incidental equality is one a refactor breaks
  silently.
- **Per-contract is asserted, not observed.** `average_fee_paid` is read as
  per-contract from the field name and the module docstring; the only
  capture (`create_ioc_filled_201`, C0) filled **one** contract, where
  per-contract and per-order are indistinguishable, and no KXMVE order has
  ever been observed through that field. The venue path also needs a count
  multiply at 4dp, which is ±11 tenths at 227 contracts — combos reach that.
- **The computed path never understates.** 70 of 70 observed fills. The
  mixed basis, had it been taken, would differ from the computed one by
  ~1% of the fee, about one tenth of a cent a position.

If the venue figure is ever read here it should be as a **check that trips
the fee alarm** (`backend/portfolio_poll.py`), not as the hedge's input.

## 4. What the figure is now

Still an estimate, still pinned in neither direction; the four terms and
their signs after this ADR:

    E1  settlement fee, H4 untested    too HIGH   0 if H4 holds; ADR 0027
    E2  sent price vs fill price       too LOW    0–10 tenths; ~0 on a one-level KXMVE book
    E3  entry fee, charged at 0.071    too LOW    ~1% of the fee, ≈1 tenth a position
    E4  hedge fee at flat 0.070        too LOW    ~9 tenths × n; measured baseball k ≈ 0.035

E3 moved from "too HIGH by ~17 tenths a contract" to "too LOW by about a
tenth a position". The net is now within a few tenths a contract with
indeterminate sign. The words that stay refused: ceiling, floor,
conservative, at least, can only be smaller/larger, exact.

The census registration's Amendment 1 §A6 table is **not edited**: it is the
record of what was true when it was registered, A6.5 puts E3 outside the
census's scope, and the census may not be cited for or against this ADR in
either direction (its own §8 rulings).

## 5. What is verified, and how

- `tests/test_hedge_positions.py::TestTheEntryFeeIsSunkBesideTheStake`:
  a combo and a sportsbook slip on the same ticket and book differ on every
  branch by exactly the fee (338 tenths on the fixture ticket); the derisk
  path sinks the same number; the payload shows `$0.07` on the combo and
  `null` on the slip. **Verified by disabling**: with the `+ entry_fee` term
  removed from `assess`, three of the four go red.
- **The worked defect, synthetic.** Four contracts at 41c, one leg left,
  hedged by buying NO at 56c: floor **+51 tenths** and `is_guaranteed_profit`
  True as a slip; **−18 tenths** and False as a combo. That is the lock the
  old arithmetic would have pushed to the phone as a guaranteed gain.
- `tests/test_hedge_arithmetic.py::TestTheEntryFeeAlreadyPaid`: the collapsed
  form equals `combo_taker_fee(P, C)` across six pairs including the edges
  (1c, 99.9c, 250 contracts); the audit's 4 × 41c example is 69 tenths; an
  unreadable ticket is `None`, never `0`.
- `TestTheLockCaveatClaimsNoDirection` re-pinned: the note must name the
  entry fee and its rate and may not go back to "does not subtract".

**Every row is synthetic and this ADR says so.** There is no real row on
which a before/after can be shown: all four real positions die at
`STATE_DEAD` before the lock path. A future session should not read the
green tests as validation against reality; the first real lock this
arithmetic produces will be the first.

## 6. What this does NOT decide

- **The `int(fill_count)` truncation at `routes.py:3952`.** `fill_count`
  is `Optional[float]` and KXMVE fill counts are fractional on the wire
  (`count_fp "227.27"`, `"4.15"`, `"909.09"` in the committed fixture). On a
  fractional fill the position is recorded smaller than held, scaling
  `stake_tenths` and `return_tenths` together; on `0 < fill < 1` the
  truncated zero is refused (`ticket_refusal`, and the table's
  `CHECK (stake_tenths > 0)` behind it), the write fails and the handler
  reports "not being watched" — correct by accident. **Unruled and
  rides along as a note.** The collapsed fee form was chosen so that fixing
  it does not break this ADR: it never recovers `C` from `return / 1000`.
- **`parlay_positions.status` never advances.** All four rows read `open`
  with every leg resolved; `open_positions()` accumulates dead tickets. The
  screen renders `STATE_DEAD` in words, so it is hygiene, not a defect —
  **known and declined**, recorded so the next session does not promote it.
- **A hedge-evaluation table.** There is none; the only record of a lock is
  the `notifications` row, and it has never been written. A table over a
  source that has produced zero outputs is not funded.
- **H4.** Untested. Nothing in the captures moves it.
- **The void-refund case.** Whether the venue refunds an entry fee on a
  voided leg is unobserved; `/hedge` refuses to price a voided leg at all
  (`STATE_VOID_LEG`), so it cannot reach this arithmetic today. Flagged as
  unverified, not as safe.
- **Money-touching code.** Nothing ordered, sent, priced for an order or
  gated moves. Joe's 2026-09-11 answer (B) — nothing money-touching before
  Arm D — is not touched by a display arithmetic change on a branch that
  merges Monday behind lane B; no position that could produce a lock exists
  or can exist before then.
