# 0073 — The buy control goes inline on every surface, and a combination is bounded rather than refused

**Date:** 2026-08-26
**Status:** Accepted.
**Owner of the decision:** Joe, 2026-08-26: *"I want to be able to buy picks
for games, props and parlays directly from the cockpit."* Four choices were
put to him and answered in his own words — build the surfaces AND prepare the
arming commit; **both** doors on parlays (per-leg and a bounded combination);
the control **inline on every card**; and a **ticker search** for markets the
cockpit never surfaced.
**Extends** ADR 0063 (the manual path). **Narrows** ADR 0063 §3's blanket
`KXMVE` refusal, and only that clause. **Amends** ADR 0065 §2 (see §4).
**Overrides, narrowly,** `SlateRow.tsx`'s and ADR 0067's "nothing here is
tappable into an order" — see §3.
**Touches nothing decided by** ADR 0015 (the gate's floor), ADR 0018 (arming
is a code change), ADR 0038 (the hunt is closed), ADR 0046 (the fee model is
documented, not branched — until it has a caller; §5).

## 1. What happened

ADR 0063 built a complete hand-bet door in one session and then it sat
unreachable for four days. `POST /api/manual-orders` had twelve server-side
checks and a full test suite; `ManualTicket.tsx` had a phase machine, an
anti-anchoring reveal and a verbatim refusal render. What it did not have was
a way in: it was mounted on `/market/[ticker]` alone, two taps from any row,
and `MANUAL_ORDERS_ENABLED=false` in both fly tomls meant **every response on
the live instance was "blocked"** — the ticket UI had never rendered against a
real quote, a real book or a real balance.

`tasks/lessons.md` has the name for this: *a feature and the one path that
invokes it are two deliverables, and only the second one ships.*

## 2. The decision

**The ticket mounts inline on every surface that names a market**, with two
new props rather than a second implementation of the same phase machine:
`variant` (`section` on the market screen, `inline` inside somebody else's
card) and `priceAlreadyVisible` (§4). Mounted on the Games rows, the Picks
rows and cards, the parlay legs, a priced combination, a search result, and
where it already was.

**`GET /api/manual/search`** is the way in to a market nothing surfaced —
prop ladder rungs the recorder never priced, series this instance does not
walk. It delegates to `estimates.search_markets`, whose SELECT carries **no
quote column at all**, which is what lets a search screen exist without
breaking the mask. No new nav slot: `Nav.tsx` budgets six links and their
order is load-bearing at 390px, so it is a closed `<details>` on the two
reading screens.

**A parlay card sells two different things and must say which.** Its legs are
individually buyable — normal single markets, two-sided books, an exit, the
fee model this repo has measured — and the control that offers them says, in
its summary line before it is opened, that **buying legs is not buying the
parlay**. Three legs bought separately win and lose separately; the card's
joint fair value is the price of all of them landing together, and a leg-buy
that did not say so would turn that figure into a promise about a bet nobody
placed.

**A combination is bounded, not refused** — §5.

## 3. More places to start a bet is not more bets

The obvious objection is that this is the maximum-surface-area design, and it
is. Two prohibitions in the record are narrowed by it, both deliberately:

- `SlateRow.tsx`'s docstring: *"nothing here is tappable ... A rejected row
  that opened an order ticket would suggest the decision is reversible from
  this screen."* True of the **engine's** ticket, which is still not here.
  What is here is a different door, into a different table the gate never
  reads, and the row now says so in the ticket's own note.
- ADR 0067: *"a favorites list must not become a chase surface."* The
  `GoodChancePicks` block is the one per-game surface that did **not** get a
  control, and the reason is not the prohibition — it is that every game it
  ranks already has a control further down the same screen. A second button
  for the same bet is duplication, not reach.

**What bounds purchases is not the number of buttons.** The ten-minute
cool-off after every completed order (no override, and it counts dry runs and
pending rows), the desk lockout, the daily-loss switch over the venue's own
record, and the balance-derived per-bet cap are all server-side and all
indifferent to how many places a ticket can be opened from. Six purchases an
hour is the ceiling from one button or from twenty.

ADR 0071 §2.1 is the positive case: *"Joe bets by hand whether or not the
cockpit exists ... the desk's job is to inform and record bets that are
happening anyway, not to manufacture action and not to abstain on his
behalf."* A refused row with no hand-bet path is the tool abstaining on his
behalf while he places the same bet in the Kalshi app, where none of the
limits above can reach it.

## 4. The mask is surface-dependent, and it never held where the ticket lived

ADR 0065 decided: *"the ask is masked until it is entered ... the moment the
ask is visible, the typed number becomes the ask's number."* That is right,
and it has **never been true on the one screen the ticket was mounted on**:
`/market/[ticker]` renders a quote strip printing "Ask $X" near the top of the
page whenever the quote is current, well above the ticket. The masking has
been a client courtesy over a page that already gave the number away.

Rather than discover that again in six months, the ticket now takes
`priceAlreadyVisible` and says which case it is in:

- **false** — the parlay legs and the search results, which carry fair value
  or nothing at all. ADR 0065's wording stands unchanged and the mask holds.
- **true** — the market screen, the slate rows, the Picks cards, a priced
  combination. *"The price is already on this screen, so that number is
  anchored by it — type it anyway; it is recorded beside the order."*

**The estimate step stays mandatory on both**, and its server half is
unchanged: the route refuses without `p_yes_bp`. What changes is only the
claim the screen makes about itself. The alternative — hiding the ask on the
cards to preserve the mask — is refused: ADR 0071 §2.2 makes price
transparency at the moment of a bet the desk's entire job.

**ADR 0065 §2 is amended to this extent and no further.** Nothing here scores
an estimate, resumes calibration, or moves an estimate into `bet_estimates`.

## 5. The combination: what changed, and what did not

`routes.py` refused every `KXMVE` ticker with a blanket 422. It now refuses
unless the request carries `combo_acknowledged`, and caps such an order at one
contract. Every other check runs unchanged.

**What made this possible is a correction, not a relaxation.** ADR 0007 says
combination markets use `center_centi_edge_centi_cent`, a grid finer than the
project's canonical tenth-of-a-cent unit, which `snap_tenths` refuses outright
— on that reading a combo order was mechanically impossible before any policy
check. Checked against this repo's own combo captures: **43 combination
markets across `combo_lookup_response.json`, `combo_lookup_repeat.json` and
`combo_priced_markets.json` are `deci_cent` (15) or `linear_cent` (29), and
zero carry a centi-cent structure.** ADR 0007's sentence is transcribed from
Kalshi's published structure table, as that ADR says of its own test values.
Recorded as an addendum there.

**ADR 0046's tripwire is honoured, not ignored.** It says: *"If anything ever
proposes to price, size, or EV a combo, this ADR is the document that says the
fee input is known wrong in the optimistic direction."* The per-bet cap is
checked against a fee, so this proposal prices one. ADR 0046 declined to
branch `calculate_fee` on the ground that a branch would be *"dead code
wearing a safety fix's clothes"* — because *"the order path cannot reach"* a
combo. It can now, so the branch has a caller:
`fees.combo_taker_fee`, at **`COMBO_TAKER_COEFFICIENT = 0.071`**.

The number is arithmetic, not a fit. On the eight combo fills of
`docs/measurements/2026-08-18-combo-fill-fee-look-result.md` the implied
coefficient spans 0.070041–0.070548 with **no row at or below 0.070** — the
deployed model undercharged four of eight. 0.071 exceeds the largest observed
implied k, so `ceil(0.071·D) ≥ 0.071·D > 0.070548·D ≥ charged` on every one of
those rows. Pinned by `tests/test_fees.py::TestTheComboHedge`, which reproduces
all eight rows and goes red at 0.070 on exactly the four the measurement flagged.

**It is a ceiling above what has been seen, not a bound on what Kalshi
charges.** Those fills are one account, one sitting, one day, at prices no
higher than $0.228 — the deep tail of a curve peaking at $0.50, and that
measurement's own scope section says nothing there bounds a mid price. **The
safety that does not depend on the number is the one-contract cap**: an error
in this coefficient costs a fraction of a cent instead of scaling with size.

**Expect the control to refuse, and the screen says why rather than a log.**
`yes_dollars` is empty on **40 of 40** combination books this repo has ever
read, across three runs on two dates, so the depth check kills nearly every
combo order — and the one combo probed through this door returned depth 0.0 on
both sides. Combos with a resting NO bid do exist (3 of 20 and 3 of 9 rows on
2026-08-09, deepest 18 units at 13c), so the control is not dead; it is rarely
live. The acknowledgement's words are the measurement's: *you can enter this
and you cannot exit it.*

**`combo_acknowledged` is a request field, not a checkbox.** It defaults to
False, so a client that has never heard of combinations refuses them rather
than buying one silently, and the acknowledgement cannot be skipped by a
client that forgets to render it.

**Unchanged by this ADR:** no combo EV, no combo edge, no combo sizing, no
combo in `recommendations`, nothing feeding `gate.py`. ADR 0012 §5's
enter-only finding is quoted here, not disputed.

## 6. Arming: what this commit does and does not do

Two acts, and this ADR performs one of them.

- **`MANUAL_ORDERS_ENABLED = "true"` on live.** ADR 0018's own sentence is
  that turning this on **moves no money**. What it does is make the ticket
  render at all, which it never has on the live instance.
- **`MANUAL_ORDER_MAX_CONTRACTS = 1`**, enforced server-side and served to the
  client so it cannot hold a stale copy. ADR 0063: *"first at a 1-contract
  ceiling, raised only when observed `fee_actual` matches `fee_predicted` on
  real fills."* It binds in dry runs too, so the ceiling is rehearsed exactly
  as it will bind live.
- **ADR 0018's second barrier is wired ahead of time**: the manual
  `OrderPlacer` now receives the app's shared `KalshiRestClient`, built only
  when the path is armed. Without it, flipping the constant produces a 503
  rather than an order — a trap left for whoever flips it, disarmed here.
- **`MANUAL_ORDERS_ARE_DRY_RUNS` stays True.** Flipping it is Joe's act, a
  separate commit, revertible alone. The assistant does not place an order on
  his behalf and did not.

**The thing arming cannot fix.** Caps derive from the observed venue balance
(ADR 0045) and never from a typed number. Read off live immediately after this
shipped: **`max_position_dollars` $0.54, `max_exposure_dollars` $2.16** — armed
today, a single contract is affordable only up to about 52c after fees and
nothing larger is buyable at all. That is a deposit, not a code change, and no
edit to this ADR moves it.

## 7. Rejected, with reasons

- **A bet slip that accumulates picks across screens.** Nearest to a
  sportsbook and the shape most designed to grow a night's action. ADR 0071
  §2.1's "does not manufacture action" is the line it crosses.
- **Hiding the ask on cards to preserve ADR 0065's mask.** §4 — it trades the
  desk's stated job for a property that was already lost.
- **Lifting the combination refusal without a fee hedge.** The per-bet cap
  would then be checked against a cost known to be understated, which is not a
  cap. ADR 0046's tripwire names this exact move.
- **Raising `MANUAL_ORDER_MAX_CONTRACTS` in the same commit as the surfaces.**
  Two decisions, and only one of them was asked for.
- **A `GoodChancePicks` control.** §3 — every game it ranks has one already,
  further down the same screen.
