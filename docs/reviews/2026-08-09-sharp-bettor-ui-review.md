# UI review, 2026-08-09 — from the standpoint of someone who bets for a living

Commissioned by Joe. Conducted by the `sharp-bettor` agent against the **public
demo instance** (`kalshi-cockpit-demo.fly.dev`) driven over CDP at 390px and
1440px, with full-page screenshots of all six routes plus the ticket sheet and
the `?suppressed=1` board — **looked at, not read from the JSX**. The live
instance was not touched.

The persona is a composite drawn from the public record of professional sports
betting. It does not speak for any real individual.

## Verification status

Claims below were re-checked against the source before this file was written.
Marked **[verified]** where confirmed at a named line, **[reported]** where it
rests on the reviewer's own run.

| Claim | Status |
|---|---|
| Ledger never renders `clv_tenths` | **[verified]** serialized `routes.py:1672`; `ledger/page.tsx` uses only `clv_scored`, `clv_scored_rows` |
| `/api/suppression` has no screen | **[verified]** route at `routes.py:618`; only frontend hit is `mart_suppression_audit` (warehouse panel, currently 503) |
| Ages do not tick when the feed is off | **[verified]** `LiveBoard.tsx:124` guards the `setInterval` behind `if (!enabled \|\| lastFrameMs === null) return;`; `:171` renders `FeedStatus` only `{enabled && ...}` |
| Playbook collides at 1440px | **[reported]** reviewer's `check_mobile` run: `dt needs 137px in 121px`, rendering `RECOMMENDATIONSMARKETS` |
| Derived ask is honest throughout | **[verified]** `entry_ask_tenths` → `ask_for_side` → `derive_no_ask`, single chokepoint |

---

## The headline

**Edge-versus-fee is being used as a filter where it should be a sort.**

The Board answers "what passed?" and 99% of the time the answer is "nothing". A
professional looks at the *whole* board and decides. Being shown two rows out of
nine removes the ability to see that today's entire slate is −3c — which is
itself the most important thing you learned today.

This was reached independently of Joe's own instruction the same day
("the mispricing should be a factor, it shouldn't filter out prospects").

**The tool has exactly one opinion, and it is the market's own.** Fair value is
devigged sportsbook consensus, and `model_probability` is never assigned in the
live path. A single fair-value source is a ceiling: the strategy cannot beat
consensus, only catch Kalshi lagging it. **0 actionable across ~200 fresh-odds
decisions is the measurement saying Kalshi does not lag consensus by more than
the fee.** That is not a bug and better cards will not change it.

---

## Per screen

### Board — the first bettable row starts ~900px down at 390px

That is the single worst thing about the product.

**Keep:** `KALSHI ASKS 50.3c` (the payable price), `EDGE NET OF FEES +1.7c`,
`BUY 15`, `quote 32s ago` colour-banded, the window countdown, and
`CREDITS TODAY 12/16 · 0 sweeps left` — that last one is your ammunition and
belongs on the primary screen.

**Cut:** the `reason_text` sentence (restates in prose the four figures printed
in large type directly above it, ~90px per card); the four-line stale-price box
(it appeared on 100% of bettable rows — if it's always there it's wallpaper);
the `WINDOW OPEN` paragraph; the H1 and three-line description (that's a landing
page, not a cockpit, ~180px above the fold every visit); four of the six stat
tiles; `cfg v1` on every card; and `depth 800` against a suggested size of 15,
which is true and never changes a decision.

### Ledger — the scoreboard does not show the score

`clv_tenths` is in the payload and is never rendered. Highest-value fix on the
page and it is a few lines.

Also: the ticker gets bolder treatment than the team name the Board uses; no
filter, sort, or date grouping (at 3,000 rows this is a wall); and the leading
`37s ago` is the age of the *record*, sitting where the Board trains the eye to
read the age of a *price*.

### Gate — the best screen in the product

Locked, four named conditions, each with a plain unmet reason. The
`fee_model_verified` explanation is exactly what a professional wants stated.

Cut the trailing `actionable 0g/0r, no_edge 0g/0r…` fragment (unparseable at a
glance, duplicates the 0/300 above); collapse the "Why 300, and not fifty"
essay behind a disclosure; print `Bankroll $1000` as a number rather than inside
prose. **Nothing on the Gate says when it was evaluated.**

### Playbook — honest, near-useless today, and one real defect

At 1440px the labels collide: **"RECOMMENDATIONSMARKETS"**. This is the identical
failure class already documented in `OpportunityCard.tsx` — a grid column with
`minmax(0,1fr)` shrinking below its own content, so nothing overflows and every
width check passes. Reintroduced on a different screen. Note that the automated
check *did* catch it and it shipped anyway.

The "The Historian has never run" note is the right call.

### Dashboards — the analytical screen is gated behind a laptop

503, warehouse not built, with an honest explanation and exact commands. But the
fix is `python -m backend.store.publish && dbt build` — and **Joe operates from a
phone.** The screen that answers "is the edge real" is behind something he
cannot do from the device he uses. Either it runs on a schedule, or the page
gets a button.

Also: the nav says "Data", the H1 says "Dashboards".

### Builder — does not currently change a bet

Inputs are raw devigged probabilities and event ids, so you must have done the
hard part before the screen can help; the output is a number a professional
already assumes is bad. Its only real potential is as the seed of line shopping.

### Ticket sheet — genuinely well made

"No total until you confirm. The order is priced at whatever Kalshi says then."
The result panel prints the *server's* numbers, says where they differ from the
ticket's, renders unknown response keys rather than dropping them, and
distinguishes retryable from final refusals. Change nothing here but its content.

---

## Phone-speed

**You can see one row per screen.** A card is ~700 CSS px at 390; two bettable
rows plus the ~900px header puts the second row 1,600px down. You cannot compare
two candidates without scrolling, and comparison is the job.

**The fix:** one line per row at phone width —
`HOU · 50.3c ask · fair 53.8 · +1.7c · 15 · 32s` — with tap opening the ticket
sheet, which is already the expanded view. The card is a redundant middle layer
between a list and a ticket. Eight rows per screen instead of one.

Also: `Show rejected` is a full page navigation that loses scroll position;
the nav costs 60px on every page and clips "Playbook" to "Playb" at 390; and the
`opacity-70` stale treatment is a weak signal on a dark screen outdoors.

---

## Price honesty — the strongest part of the product

Nowhere did a mid appear where a bettor's eye expects a price. The derived ask
is enforced at a single chokepoint. Better than most commercial products.

Three flags:

1. **`CONSENSUS FAIR 53.8c` is a probability wearing a price's clothes** — same
   `c` suffix, same size, immediately *left* of the payable price. A
   left-to-right scan reads the leftmost large cents figure as the price. Render
   it `53.8%`, or put the ask first. This is the one genuinely confusable spot.
2. **`+1.7c` is the edge at a price the card itself calls a memory.** The
   headline number is computed against an ask the same card labels `32s ago`,
   past a 30s limit, with no allowance for the move.
3. **`COST $7.54` is computed in the browser.** Arithmetic only, no fee model
   crosses the wire — but it is the one money figure the server did not produce.

---

## Staleness — one hole, and it matters

Mostly excellent: ages colour-banded against limits, `LAST SWEEP`,
`FIXTURES FRESH 8/9`, the countdown, and the expired card naming which clock ran
out. The `_live_ages` / `quote_age_now_ms` split is the right design.

**The hole: the ages do not tick.** With the feed off or idle — the demo's
permanent state, and the live instance's whenever the feed drops — a page left
open for five minutes still reads "quote 32s ago", with no banner. Across three
loads the reviewer watched one row report 32s, 52s and 3m: correct at each
render, frozen in between.

That is precisely the half-dead-container failure `LiveBoard`'s own docstring
exists to prevent. It is prevented for the streaming case and not for the
non-streaming one. A `setInterval` re-render of the age strings, and a feed
status line that renders in the disabled/idle case, closes it.

---

## What is missing, ranked by money impact

The frame: the public record on professional betting says the money came from
**information**, **the best number**, **capacity and execution**, then **cost**.
This tool is complete on cost and empty on the first two.

### Software problems

1. **Line movement.** Nothing shows where a number was an hour ago.
   `fair_prices` already stores `computed_ms` per row — *the history is in the
   database*. "Consensus moved 53.8 → 55.2 in twenty minutes and Kalshi is still
   50.3" is a bet; "consensus is 53.8 and Kalshi is 50.3" is mostly devig noise.
   Cheapest large-value item in the product, and it serves two dimensions at once.
2. **Uncertainty on the fair value, on the card.** `fair_prices` stores
   `p_multiplicative`, `p_additive`, `p_power`, `p_shin`, `market_width`,
   `book_count`, `books_used` — **none of it reaches the browser.** A +1.7c edge
   beside an unshown 2.1c method spread is not a bet. Per CLAUDE.md's own
   framing the method spread exceeds the fee advantage being hunted, so this is
   the number that decides whether the headline means anything. Nearly free.
3. **Per-book prices and the best number.** `books_used` is already a JSON array
   on every fair price. This is line shopping — the dimension with the strongest
   public track record behind it.
4. **Alerting.** The tool is actionable ~30 minutes a day and a row lives for
   seconds. Requiring Joe to be *looking at a page* in that window is the real
   capacity constraint. A push when `surfaced > 0` is worth more than every
   layout change in this review combined.
5. **Positions, exposure, P&L.** There is no screen. Before betting the second
   row you need to know what the first cost and what you are carrying — and that
   two rows on the same game are not two independent bets.
6. **CLV on the Ledger.** Trivial.
7. **`/api/suppression` has no screen.** With 0 actionable across ~200
   decisions, "which check is killing everything" is the most valuable
   diagnostic in the system, and it is one fetch from a screen.

### Not software problems

- **Book limits.** Nothing in this repo fixes an account being closed. Kalshi's
  advantage here is real and under-exploited: it does not limit winners.
- **Two odds credits a day.** Caps the tool at ~30 actionable minutes out of 24
  hours. Fixed with money, not code.
- **Bankroll.** Depth 800 against a suggested 15 means capacity is nowhere near
  binding — but it also means that if an edge exists, the dollars at $1,000 are
  trivial. An edge that only exists for $20 is a hobby.
- **Whether Kalshi is the soft side.** Currently the evidence points the other
  way: a venue that never disagrees with consensus by more than the fee is
  *tracking* consensus. That is the finding, and the tool produced it correctly.

---

## The empty board

A screen that is correct and always empty is the wrong screen. What should
occupy the space:

1. **The slate, always.** Every upcoming game with ask, fair, edge, sorted by
   edge descending, one line each. Bettable rows flagged and tappable;
   everything else visible and inert. **This relaxes nothing** — suppression and
   staleness still govern what is *bettable* and what the order endpoint
   accepts. They stop governing what is *visible*. That is the difference
   between a filter and a factor.
2. **Distance to the bar, as one number.** *"Closest today: −0.4c — Chicago, no
   edge."* It changes daily, it proves the machine ran, and it tells you whether
   you are 0.4c away or 6c away — the difference between "keep watching" and
   "this venue is not it".
3. **The suppression strip.** If `stale_kalshi_quote` is killing 60% of
   candidates, that is a fixable operational problem currently indistinguishable
   from "the market is efficient". On this screen the two look identical.
4. **Invert the default.** `Show rejected` should be on by default. The rejected
   rows *are* the content 99% of the time.

---

## The reviewer's summary, kept verbatim

> This tool is the most intellectually honest betting product I have reviewed.
> Every screen states what it does not establish, the derived ask is enforced at
> a single chokepoint, the Gate refuses to open, the Playbook admits its own
> agent has never run, and the Dashboards page says "not built" instead of
> rendering an empty chart. That is rare and it is worth keeping.
>
> It has also optimised the smallest of the four levers to completion and has
> not started on the two largest. The 0-of-200 result is not a UI failure — it
> is the correct answer from a tool that has exactly one opinion and that
> opinion is the market's own. Better cards will not change it. A second,
> independent opinion, line movement, and per-book numbers might. Until one of
> those exists, the most valuable thing this UI can do is stop presenting itself
> as a list of bets and start presenting itself as a measurement of how far away
> a bet is.
