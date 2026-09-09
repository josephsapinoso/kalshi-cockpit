# ADR 0125 — A combination bought through the desk is watched for its own exit

Status: accepted
Date: 2026-09-09

Wires the entry path (ADR 0063, ADR 0112) to the exit path (ADR 0078). Does not
amend ADR 0073's combination ceiling, does not touch the gate (ADR 0063 §
separation: `gate.py` still never reads `parlay_positions`), and moves no
money.

## Context

**A `KXMVE` combination is enter-only.** `yes_dollars` is empty on 40 of 40
combination books this repo has read, with zero resting YES bids over 36
levels (ADR 0012 §5; pinned by `tests/test_combo_book_depth_claims.py`). You
can get in and may not be able to get out at size. ADR 0078 exists because of
this: `/hedge` reads a held parlay's legs' live prices and says what hedging
the endangered leg would do — **the only exit an enter-only combination has.**

`/hedge` watches what is in `parlay_positions`. Until today the only writer of
that table was `POST /api/hedge/positions`, reached from `RecordParlay.tsx` —
a separate tap, on a separate screen, that Joe had to remember.

`POST /api/manual-orders` wrote **zero** rows to it.

**So the desk armed the entry and left the exit to memory**, on the one path
where he spends real money. Two columns that would have joined the two halves
— `parlay_positions.combo_ticker` and `.parlay_lookup_id` — have existed in
`schema.sql` and been accepted by the hedge route the whole time, and were
**sent by nobody**: `RecordParlay.tsx` posts `source, label, stake_cents,
return_cents, legs, book` and nothing else.

### Read off the live instance, 2026-09-09

    manual_orders     3 rows, all dry_run = 0, all KXMVECROSSCATEGORY shard 1
      id 1  4 contracts  filled    2026-09-08 19:41Z
      id 2  3 contracts  filled    2026-09-08 19:42Z
      id 3  1 contract   unfilled  2026-09-09 00:34Z
    parlay_positions  0 rows
    parlay_lookups    40 rows, 37 with a minted ticker

`venue_positions` carried both filled combinations — 4 contracts at $1.50 of
exposure and 3 at $0.714 — from 2026-09-08 19:41Z until they settled. **For
the entire life of both positions, the screen that exists to get him out of
them had never heard of them.**

The positions have since settled, so this is not an open exposure today. That
was established rather than assumed: `poll_log` id 20337 at 2026-09-09 15:00Z
reports the `positions` endpoint `ok` with `row_count = 0`, so the rows stopped
because the positions closed and **not** because the poller stopped. Silence
read as health is the failure mode this repo checks for by reflex.

## Decision

**A filled combination through the hand-bet path writes its own
`parlay_positions` row, linked to the fill.**

Check 13 in `POST /api/manual-orders`, after the outcome is recorded:

- **Only a real fill of a real order.** A dry run bought nothing. `fill_count`
  is the quantity the **venue** reports, so a part-filled IOC is watched at its
  true size rather than the size requested.
- **`unrecognised_response` records nothing.** The quantity is unknown there
  and the route's own copy tells him to check the Kalshi app; a position
  invented at the requested size would contradict it in the one table whose
  job is to say what he owns.
- **`combo_ticker` and `parlay_lookup_id` are populated**, from the
  `parlay_lookups` row that minted the market. `priced` rows only: a minted
  ticker is **not unique** in that table — live rows 39 and 40 share one — and
  only a priced row describes a market anyone could buy.
- Stake is what he paid; return is $1.00 a contract. Integer tenths of a cent.
- **Nothing here may raise into the order path.** The money is already spent
  when this runs, and a bookkeeping failure that turned a successful purchase
  into a 500 would be the most expensive lie the desk could tell.

### The lookup now records what the position needs

`hedge.record_position` refuses a leg with no `side` and no `label`, and
`selected_legs` carried only `event_ticker` and `market_ticker`.

Every missing field was **already on the `CandidateLeg` at lookup time and was
being dropped on the floor**, so this is persistence, not a second source of
truth and not another call to Kalshi. `_record_lookup` now also stores each
leg's `side`, `label`, `league` and `commence_ms`, on the `priced` outcome
only — the one outcome that leaves a ticker he can actually buy.

`side` is `"yes"` and is **structural rather than a guess**, on three
independent readings: `CandidateLeg` is "one buyable YES side" by its own
definition, `echoed_legs(..., side="yes")` is what this repo puts on the wire
to Kalshi, and a combination pays only if every leg hits.

### Failure is said out loud, never absorbed

When the fill lands and the position cannot be built honestly — no priced
lookup, an unreadable leg list, or the write itself raising — the response
carries `hedge_position_id: null` **and** a `hedge_position_note` saying the
combination is not being watched and to record it by hand.

Silence there would be the original defect wearing a new coat: he would
believe the desk had his combination under watch when it had never heard of
it. `hedge_position_note` stays `null` on anything that is not a filled
combination, so "not a combo" and "a combo nothing is watching" never read the
same.

### A partial leg list is refused outright

`legs_for_position` returns `None` — never a shorter list — when the blob is
missing, unparseable, empty, or contains a leg with no market ticker. A
combination watched as if a missing leg could not lose is **wrong** rather than
absent, and worse than not being watched at all. Unreadable resolves to `None`,
never to a shorter list.

### Pre-2026-09-09 lookups degrade, and admit it

The 37 existing rows carry no label. The market ticker stands in, and the
position's note says so. A ticker truly names its leg, so this is degradation
rather than a wrong answer — but a screen reading
`KXNFLGAME-26SEP13DETGB-DET` where it should say "Detroit to win" looks broken
rather than degraded, and the note is what tells them apart. Inventing a label
was refused.

## Consequences

- Buying a combination through the desk is now sufficient to have it watched.
  No second tap.
- `POST /api/hedge/positions` and `RecordParlay.tsx` stay: a parlay placed at a
  sportsbook, or on Kalshi outside the tool, still has no other way in.
- `gate.py` still never reads `parlay_positions` (ADR 0063), so nothing here
  moves the live-trading interlock.
- No credits, no tokens, no `recommendations` row — ADR 0078's constraints hold
  unchanged.

## What this does not decide

- **Nothing is backfilled.** The two settled positions stay unrecorded; they
  are closed, and inventing rows for them would put fabricated history into the
  table this ADR is about.
- **Nothing about whether he should hedge.** `/hedge` reports and does not
  advise (ADR 0078), and that is untouched.
- **The absent consensus column stays absent.** `manual_orders` still records
  `consensus_absent_reason = 'combo_ticker'` for every combination
  (`store/manual_orders.py`), so 100% of the bets placed through the tool carry
  no consensus figure — while `parlay_lookups.hold` holds the desk's own
  headline number for the same ticket (0.170, 0.063 and 0.209 on his three
  live lookups). Whether that is honesty or a hole is a separate question and
  is not answered here.
- **Nothing about the settlement of a combination.** `resolve_from_venue`
  settles leg markets; whether a minted `KXMVE` ticker settles its position
  automatically is unobserved.
