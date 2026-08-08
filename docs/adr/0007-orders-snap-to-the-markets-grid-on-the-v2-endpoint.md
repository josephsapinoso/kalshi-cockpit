# 0007 — Orders snap to the market's own price grid, on the V2 endpoint

**Status:** accepted, 2026-08-08

## Context

`tasks/NEXT.md` carried this defect under "fix before any real money":

> **Deci-cent asks can't fill.** Limit prices floor to whole cents, so a 50.5c
> ask rests at 50c on the ~25% of markets that tick in half-cents. Safe for
> money, but it corrupts the paper record with orders that never fill. Needs
> checking against Kalshi's write API.

The check against the write API returned three things, and the second one turned
a small fix into an endpoint migration.

**1. `price_ranges` is the contract, and the label beside it is not.** Every
market publishes an array of `{start, end, step}` bands in fixed-point dollars.
Kalshi's own words: *"This is the source of truth for valid prices: any price on
the grid is valid, and any off-grid price is rejected."* And, separately:
*"`price_level_structure` — do not key pricing logic off this name; new
structures are introduced over time."* Eleven structures are published today,
from `linear_cent` to `center_centi_edge_centi_cent` at $0.0001.

**2. The endpoint we were posting to cannot express a sub-cent price, and is
deprecated.** `POST /portfolio/orders` takes `yes_price` / `no_price` as
**integer cents**, so no amount of snapping reaches it. The documented
replacement is `POST /portfolio/events/orders`, whose `price` is a fixed-point
dollar string. The legacy path no longer appears in Kalshi's API reference at
all, and the V2 page says it *"will be deprecated no earlier than May 6, 2026"* —
three months before this was written.

**3. Whole cents are legal on every structure.** This is why the defect was
invisible. Flooring to a cent never produced a rejection; it produced an order
that rested behind the market and never filled. On a project whose entire
product is the record, an unfillable order is worse than a refused one: it
enters the evidence as a bet that was placed.

### The size of it, measured rather than assumed

`scripts/capture_price_grids.py` against the live exchange, 2026-08-08:
**1,426 game markets, one distinct grid, `linear_cent` on every one.**

So on the universe this project prices, the snapper is a no-op today and no fill
is currently being lost. The "~25%" in the original note is a fact about all
Kalshi markets, which are dominated by non-sports; `.claude/skills/kalshi-api/
SKILL.md` counted 60 `center_half_edge_half_cent` game markets two days earlier,
i.e. 2.8%, and today zero.

That measurement is recorded here so it is not quietly promoted into *"sub-cent
game markets do not exist"* — the `KXMVE` mistake in `tasks/lessons.md`, where a
true measurement about one thing licensed a false conclusion about another. The
structures exist, they are assigned per market, and Kalshi publishes a
`price_level_structure_updated` lifecycle event, so a market's grid can change
**while it is open**.

## Decision

**1. Read the grid per market, from the live payload, with no default.**
`backend/kalshi/grid.py` parses `price_ranges` into integer micro-dollar bands.
At the ingest boundary an unreadable grid resolves to `None`
(`DiscoveredMarket.price_grid`), and the order path **refuses** on the `None`.
There is no fallback grid: a default of whole cents would silently restore this
exact bug on the day Kalshi renames the field.

**2. Snap away from paying more, and refuse rather than clamp.** A bid snaps
down and an ask snaps up. A price with no grid point in its direction raises
instead of moving to the nearest legal value — the rule from
`tasks/lessons.md` that turned `no_price=-390` into a live buy at 99c in the
predecessor project.

**3. Orders go to `/portfolio/events/orders` (V2).** Which brings four changes
that are not optional once the endpoint changes:

- `side` is `bid`/`ask` on the **YES leg only**. Buying NO at `p` is selling YES
  at `1 - p`. The rounding rule survives the reflection unchanged, which is the
  useful part: in YES-book terms a bid always snaps down and an ask always snaps
  up, on both legs.
- `price` is a fixed-point dollar string; `count` is a fixed-point string too.
- `time_in_force` and `self_trade_prevention_type` are **required**. We send
  `good_till_canceled` and `taker_at_cross` — the same resting-limit behaviour as
  before, so the endpoint change does not smuggle in new execution semantics.
- The response has no `order` envelope and no `status` field. **Status is derived
  from the fill counts**, and a response that does not carry them is recorded as
  `unrecognised_response`.

That last point was a live defect, not a hypothetical: the old parser read
`response["order"]["status"]` with a default of `"resting"`, so under V2 *every*
order would have been recorded as resting with a null order id.

## Consequences

**What is verified and what is not.** The `price_ranges` parser is pinned by
real captured bytes from 1,426 markets across two endpoints. The sub-cent band
values in the tests are transcribed from Kalshi's published structure table and
are labelled as such, because no game market carried one on the day of capture.
The **response** shape has never been observed — no order has ever been placed by
this project — so the first live order is also the first test of that parser.
The protection is structural rather than documentary: an unreadable response
cannot produce a status that reads like success.

**A dividend on the fee deadlock.** The V2 response carries `average_fee_paid`,
volume-weighted per contract. `core/fees.py` is a conservative max-of-models
hedge precisely because reading the true fee needs a real fill; when the
fee-calibration trades happen, the answer arrives in the order response itself
rather than needing a separate `/portfolio/fills` poll.

**A limit we did not previously have.** `snap_tenths` refuses a grid point finer
than a tenth of a cent, because the project's canonical unit cannot name it.
That is unreachable on game markets and reachable on combo markets, which use
`center_centi_edge_centi_cent`. Refusing beats sending a price we cannot
represent; if combos are ever priced, the unit is what has to change.

**Still open, and unchanged by this.** There is no cancel path anywhere in the
repo, so a resting GTC order cannot be withdrawn by this tool. That was true
before and is not made worse here, but a sub-cent price makes resting orders
more likely to actually rest rather than cross, so it matters slightly more.
