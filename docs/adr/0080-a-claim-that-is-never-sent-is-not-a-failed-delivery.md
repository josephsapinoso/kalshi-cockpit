# ADR 0080 — A claim that is never sent is not a failed delivery

**Date:** 2026-08-27
**Status:** Accepted
**Supersedes nothing. Repairs an instrument ADR 0049 built and ADR 0076 broke.**

## The finding

`/api/health` read `undelivered_last_24h: 5` on 2026-08-27 at 20:25Z with
**nothing having failed to deliver**. All five rows were deliberate.

`tasks/NEXT.md` had just told the next session to verify the scheduled parlay
card by checking that this field was "still 0". It could not be. It cannot be 0
again on any day the card fires.

## Mechanism

Three pieces, each correct on its own, in `backend/notify/alerts.py`:

1. `_claim` inserts a `notifications` row with `delivered = 0`, **before** the
   send. That ordering is deliberate and load-bearing: a crash between claiming
   and sending must not silently re-alert on restart.
2. ADR 0076's channel-burn calls `_claim(PARLAY_CHANGE_KIND, key, …)` **with no
   send behind it**, so that the scheduled card and the change channel cannot
   both announce one composition. That row is `delivered = 0` and always will
   be — up to `len(PUSHED_CARD_KEYS)` = 3 per day.
3. `delivery_health` counted every `delivered = 0` row inside 24 hours as
   `failed_recent`.

So the burn leaves **exactly the signature ADR 0049 built this field to
detect**. That ADR's own words: *"the alerter claims the row before sending, so
a process that dies mid-send leaves exactly this. The loop died and Joe was not
told, and nothing said so for months."*

`tests/test_alerts.py` already named the harm in
`test_an_old_failure_falls_out_of_the_24h_count` — *"otherwise one bad night
reads as a permanently broken alerter."* The burn made the bad night permanent.

## Decision

**`notifications` gains a `suppressed` column** (schema v25). `delivered` stays
strictly 0/1. `_claim` takes `suppressed: bool = False` and the burn site passes
`True`. `delivery_health` counts `delivered = 0 AND suppressed = 0`.

Three things about the shape:

- **Not a sentinel inside `delivered`.** `scripts/inspect_live_db.py` does
  `SUM(delivered)`, so a `2` would report each burn as *two* deliveries in the
  one tool a session reads this state with.
- **The caller declares it; it is not deduced.** A claim with no delivery record
  is also what a mid-send death leaves, so the two are indistinguishable after
  the fact. The default is `False` because the dangerous direction is a real
  failure written off as intentional.
- **Not a separate `kind`.** The burn's entire purpose is to occupy the
  `UNIQUE (kind, key)` slot of `parlay_card`; a different kind would occupy
  nothing.

**`suppressed_last_24h` is published on `/api/health` beside the corrected
count.** Two reasons, and the second is the stronger:

1. A silent filter would hide a burn storm. Today's own lesson — *a fact that is
   displayed but is not a finding does not get acted on* — has an inverse: a
   fact that is filtered out cannot be acted on at all. The figure should sit at
   or below 3 a day; anything else is a finding.
2. **It is what makes the fix checkable from outside.** Without it,
   "undelivered went to 0" is indistinguishable from "the metric broke a
   different way".

`scripts/inspect_live_db.py notifications` now emits `delivered`, `suppressed`
and `undelivered` as three columns. Read on live before this change, that
section said `parlay_card 20 / 15 delivered`, and `n - delivered` was the number
a reader would take as failures. It was the burns.

## What is deliberately not done

**The five existing live rows are not backfilled.** Which of them are burns
cannot be established from the record: `inspect_live_db.py` is a whitelist of
named queries with no arbitrary-SQL path, and the `notifications` query shows
only a tail. Two are provable (ids 1531 and 1533, written in the same
millisecond as `delivered = 1` `parlay_daily` rows); the other three are
*consistent* with the remaining burns from the day's two card batches and that
is not the same as measured. They default to `suppressed = 0` — still counted as
failures — and age out of the 24-hour window on their own. An alarm that stays
on until it expires is recoverable; a real death written off as intentional is
not.

## What this does not establish

- **That any alert has ever failed to deliver on live.** This changes what the
  count means, not what it counts.
- **That the heartbeat was affected.** It was not.
  `.github/workflows/heartbeat.yml` reads `status`, machine state and
  `recorder.age_ms`, and never reads this block — so no false alarm ever
  reached the phone. The damage was to a human read of `/api/health`, and to
  ADR 0072's verification method, which used `undelivered_last_24h at 0` as
  evidence.
- **That three a day is the right ceiling.** It is `len(PUSHED_CARD_KEYS)` and
  will move if that set does.

## How it will be verified on live

Immediately: `/api/health` carries `suppressed_last_24h`, and schema v25 applies
on boot without a crash loop.

**Not immediately: `undelivered_last_24h` reading 0.** The five pre-existing
rows are unmarked, so it decays over 24 hours rather than dropping. The check
that settles this is `suppressed_last_24h` becoming non-zero at the next
scheduled card, and the full confirmation is the following day's 20:00Z.

## What would refute the decision

A `suppressed` row that turns out to have had a send attempted behind it — that
would mean the flag is being set somewhere it does not belong, and the count it
removes from `undelivered_last_24h` is a real failure being hidden. The one
call site that sets it is the burn, and it is pinned by
`TestTheBurnIsNotAFailedDelivery` in
`tests/test_parlay_cards_reach_the_phone.py`.
