# 0152 — Totals and player props are parlay legs, both sides, and the feed buys them

Written on `main` with no lane open; **0152 taken after `git fetch`** with
0151 the highest on `main`. No schema change (schema stays v42).

Date: 2026-09-14
Status: Accepted, on Joe's word — *"add the capability to assess and bet on
other odds and props. not just spreads and moneylines, but also
over/unders, and props. for example, if there is a good chance of a
particular player going over or under a certain number of rushing yards,
that should be a whole other set of parlays."* His four answers to the
decisions this needed, same day: add `totals` to the feed now; NFL props on
tap per game; new cards only, existing cards untouched; Under legs in the
same piece of work, Overs first.

## 1. What this overturns, and with what

**ADR 0110 §1 — "player props are killed, not deferred."** Its reason was
billing: *"per-player market keys are one key per player per market family,
so the multiplier is not 1.5× but whatever the roster is."* That is not how
this vendor bills. A prop event costs `sweep_cost(prop_market_keys(sport),
regions)` — one credit per **market key** per region, every player in the
event inside one key (`runner.py`, `prop_cost_per_event`; ADR 0079 measured
it: five keys × two regions = 10 credits an event, 20 while the alternates
were bought). Three NFL keys are 6 credits a tapped game. §1's other reason
— the in-house prop model is refuted (ADR 0037) — stands and is not what
this does: the desk shows the books' consensus beside Kalshi's price and
models nothing.

**ADR 0110 §2 — "totals are refused this season under `us,eu`."** Its
arithmetic was a projection: the largest observed day (496, a two-sport
Saturday) × 1.5 = 744 > 700. The measured NFL Sunday it was written to
protect, 2026-09-13, cost **236** credits (59 calls × 4). At 6 a call that
is ~354, half the cap. The 09-05 Saturday would still have crossed
(~744), and when the 700 binds every sport stops until 10:00Z — so this is
a trade taken with the number in view, not a refutation of the risk. The
check is registered in §6.

**Ticket #36's closure (2026-09-14)** said NFL props were *"a new ticket
opened knowing it is a build."* This is that build. #36 is superseded in
part (the successor ticket names which part); its answer is not withdrawn.

**ADR 0140 §8** — *"it does not decide whether to add any market type"* —
is now decided for totals and NFL props by this ADR, through exactly the
mechanism 0140 described: the feed purchase first, the recipe second.

**Not overturned.** ADR 0032: props are bought on tap, never on the
schedule; `ODDS_BUY_PROPS_ON_SCHEDULE` stays `false`. ADR 0079: the
`_alternate` keys are not bought, for NFL either — whether NFL's primary
quotes one line where Kalshi prices twenty rungs is **unmeasured**, and the
first NFL tap answers it for free (`dropped_unresolved_outcome` on the pass
line, `inspect_live_db.py prop-rungs`). ADR 0110 §3: the `eu`-drop lever
stays dated 2026-09-28 and refused until then. ADR 0038: the hunt stays
closed — a leg with a consensus beside it is not a leg with an edge, cards
rank by `p_conservative`, and the gap is a per-row fact.

## 2. What is built

Five slices, each verified by disabling its guard and watching the test go
red before the guard was restored.

1. **A totals pricing arm** (`backend/kalshi/totals.py`,
   `runner.totals_quotes_for_event`, `runner._price_totals_event`). One
   subtitle reader for `"Over N.5 <unit> scored"`, cross-checked against
   `floor_strike`; the join identity `total_book_point(line) == line` written
   once (no negation like spreads, no half-point like props). Fair rows only,
   both sides at the shared point, no `recommendations`, no gate. Total
   events now inherit their game's link by fixture segment
   (`TOTAL_LINK_METHOD`); until this they fell into the two-team bijection
   and were refused every pass into `unmatched_items`. `TEAMTOTAL` is out of
   scope (team + line in one string; a fourth feed key).
2. **NFL props, both halves in one change.** `PROP_SERIES` gains the three
   yardage ladders (`KXNFLPASSYDS/RECYDS/RSHYDS`, 2,029/2,029 parsed on the
   2026-09-10 capture) and `prop_market_keys(sport_key)` reads a per-sport
   key map whose NFL values are exactly `NFL_PROP_SERIES.values()`. The
   argument is required; the sport-free spelling was #37's shape. The
   planner reserves the dearest sport's figure (over-reservation is the safe
   direction); the tap and `/api/odds/refreshable` quote the exact one.
3. **Two new cards, their own set.** `props` ("Three props", MLB ∪ NFL keys)
   and `totals` ("Three totals"), 2–3 legs, one per fixture, floor 0.20,
   not pushed to the phone. `CANDIDATE_SQL` admits `POOL_MARKETS`, one
   constant. Every existing card keeps `TEAM_MARKETS_ONLY`; a test pins that
   props and totals entering the pool move no team card. The odds-refresh
   panel is mounted on `/parlays` so the prop card's door sits beside it.
4. **Under legs.** `CandidateLeg.side` (`"yes"` | `"no"`). The prop and
   totals arms emit the Under row as a NO leg on the same Kalshi market,
   with the Under row's own `p_conservative`. The side travels through the
   wire, the lookup echo, `lookup_combo`'s body (per-leg sides), the
   `parlay_lookups.selected_legs` record and the per-leg ticket
   (`preferSide`). `_joint_key` carries the side so the YES and NO of one
   market never share a memoised joint.
5. **Config.** `fly.live.toml` `ODDS_MARKETS = "h2h,spreads,totals"`; every
   scheduled call goes 4 → 6 credits.

## 3. What this does not establish

- **That Kalshi will combine a prop leg, a total leg, or a NO leg.** The
  collection fixtures carry `KXNFLTOTAL` and the NFL prop series as legs,
  and a minted fixture shows `no Over 8.5 runs scored` inside a combination,
  so the venue can. Which collections accept which is a lookup's answer;
  the first "Price on Kalshi" tap on each new card is the measurement.
- **That NFL prop consensus is two-sided often enough to fill a card.** No
  NFL prop odds payload is in any fixture; the pricing path is exercised by
  the MLB capture, which runs the same code. ADR 0079 put MLB primary
  coverage at 48 of 263 rungs. The first tap on an NFL game measures it.
- **That a prop or total leg is a good bet.** ADR 0038.
- **The totals credit cost on a full four-sport day.** Registered below.
- **Which unit NFL totals are published in.** `runs` and `points` are what
  the record contains (MLB, WNBA). An NFL total in another unit is counted
  as `dropped_unknown_total_unit`, never guessed.

## 4. Consequences

- Every scheduled odds call costs 6 credits. The day is bounded by
  `ODDS_DAILY_CREDIT_BUDGET = 700` exactly as before, and the cap binding
  still stops every sport.
- A prop tap on an NFL game costs the team call (6) plus 6.
- `unmatched_items` stops accruing `*TOTAL*` refusals.
- `/parlays` shows nine cards. The two new ones read as thin, in their own
  words, until a sweep has bought totals (slice 5's deploy) and a tap has
  bought props.
- Ticket #36 gets a successor and a "superseded in part" comment.

## 5. Copy that could lie

The two new cards say "over or under" and nothing about a lean; the caption
under each says an under is the NO of Kalshi's over market and that the
desk asks for that side. If Under legs were ever refused by the venue at
lookup, the caption is the sentence to fix in the same commit as the
refusal handling.

## 6. Registered check

`scripts/inspect_live_db.py credits-day --date 20260920` (the first NFL
Sunday under `totals`), read by trigger, beside 20260913's 236. If the 700
binds on any budget day before 2026-09-28, the answer is not to widen the
cap; it is ADR 0110's per-sport reservation, which has its own ADR to
write.
