# 0010 — Paper settlement is a measurement, not a ledger

**Status:** accepted, 2026-08-08

Closes the last open backend item in `tasks/NEXT.md` section 2, and the
prerequisite ADR 0008 named for making `max_exposure_dollars` bind before a live
order exists.

## Context

Every order this project has placed is a dry run. `orders` rows are written
(ADR 0008) and `settlements` has never had a writer, so:

- `current_exposure_dollars` excludes dry runs and returns `0.0` in production,
  which means **`max_exposure_dollars` is exercised only by tests**. This repo
  has twice shipped a guard that could not fire and read as defence in depth
  (`tasks/lessons.md`, "two guards passed their tests and both were broken"). A
  third is sitting on the money path right now.
- Counting paper orders without settling them was rejected by ADR 0008 for a
  good reason: nothing closes a paper position, so paper exposure could only
  ratchet up until the endpoint refused everything. **A cap that can only close
  is an off switch.**

Settlement is what changes that argument, which is why this is worth building
before the gate opens rather than after.

It is not plumbing. Three of the five decisions below are measurement decisions,
and the record is the entire product.

## What was measured first

Following the rule that cost this project the most to learn — *capture the
payload before writing the parser* — `scripts/capture_settled_markets.py` pulled
44 real markets before any of this was designed
(`tests/fixtures/markets_settled.json`, 2026-08-08). Five findings, and the
first would have silently broken everything:

**1. The status filter and the status field use different words.**

    GET /markets?status=settled   ->  42 markets, every one status: "finalized"
    GET /markets?status=finalized ->  HTTP 400, "invalid status filter"

A settlement pass matching `status == "settled"` matches **zero markets,
forever**, and reports "nothing has settled yet" — which is also what a correct
pass says on a quiet day. That is the WebSocket parser reading 0 of 257 frames,
rebuilt exactly, and no amount of reading the documentation would have caught
it.

**2. `closed` is a distinct, durable third state.** Two NCAAF markets came back
`status: "closed"` with `result: ""` and `settlement_ts: null` — closed on
2026-02-03 and still unresolved six months later. "The game is over" is not "the
outcome is known", and a pass that conflates them either hangs or invents a
loser.

**3. `result` is `"yes"` / `"no"` on finalized and `""` everywhere else** —
an empty **string**, never null. `if not result` therefore reads an active
market as a settled one. Same shape as `Kalshi sends "0.0000", not a missing
field`.

**4. `settlement_ts` is present on 42/42 finalized markets and absent on the
closed ones.** So the settlement instant is observed, not inferred. Note that
`expiration_time` is *not* it — on the sample game it reads 2026-08-11 against a
`close_time` of 2026-08-08, three days out.

**5. `last_price_dollars` is `0.9900` or `0.0100` on 42 of 42 settled markets.**
`CLAUDE.md` already warns that "the convenient column is usually contaminated —
`last_price` on a settled market has already converged on the outcome". That is
now measured rather than asserted: it carries no information beyond `result`,
and reading it as a price would be reading the answer.

A sixth, free: `settlement_value_dollars` agrees with `result` on 42/42
(`yes`↔`1.0000`, `no`↔`0.0000`), so the payload carries two independent
statements of the outcome and they can be cross-checked at no cost.

## Decision

### 1. The fill assumption is `depth_capped_taker`, and it is a stored column

"Did the paper order fill?" has no observed answer, and assuming a fill at the
limit flatters the record. But the assumption available here is much stronger
than that, because the order path has already refused everything it could not
size: `routes.py` refuses when `depth_at_ask < contracts`, so **every paper
order is a marketable limit order sized entirely within the resting depth we
observed at that price.**

So the recorded assumption is: *filled in full, at the order's own limit price,
because the book showed enough resting size to fill it.* Today
`assumed_filled_count == count` on every row by construction — stated as a
measured `0 of N differ` rather than left as a claim.

**It is stored, not implied.** `orders` gains `fill_assumption` (the named
policy) and `assumed_filled_count`, and `settlements` records the depth that
justified it. The record can then be re-analysed under a different assumption
later, which is the whole reason to write the assumption down rather than bake
it into the arithmetic.

**And the bias is stated in the module, because it has a direction.** The
depth check bounds size against a book one round trip old; it does not make the
fill atomic, and `routes.py` says so. The times a real order would *fail* to
fill are the times the maker pulled — which correlates with the price being
about to move, which correlates with the bet having been good. **Paper fills are
therefore optimistic in exactly the cases that matter most**, and no amount of
care in this module fixes that. Only real fills do.

### 2. Kalshi's own `result` settles it, and three states are distinguished

A settlement pass, sibling to `backend/scoring.py`, reading `/markets/{ticker}`.
Costs no odds credits. It resolves a position only on `status == "finalized"`
**and** a `result` in `{"yes", "no"}` **and** a `settlement_ts` it can parse.

Anything else leaves the position open and counted:

| Observed | Action |
|---|---|
| `finalized` + `yes`/`no` + `settlement_ts` | settle |
| `closed`, empty `result` | leave open — outcome not known |
| `finalized`, empty or unrecognised `result` | **refuse and log** — must not resolve |
| unrecognised `status` | **refuse and log** — the vocabulary drifted |

The last two are refusals rather than defaults, per *clamp what you trust,
refuse what you are validating*. An unrecognised status is the case finding 1
proves this API can produce, so it gets a loud, named failure and a drift test
over the capture rather than a fall-through.

`settlement_value_dollars` is checked against `result` and a disagreement
refuses. It costs nothing and it is the only independent reading available.

### 3. `settlements` gains `order_id` — schema v4

Not documented as an approximation. The current exposure query releases capital
for *every* order on a ticker as soon as *any* settlement row for that ticker
exists, which is correct only while there is one order per ticker. Two are
ordinary: a quote pass re-recommends a market minutes later, and the Board
offers both.

Writing the first rows into that table is the last moment this is cheap —
`tasks/lessons.md`, "before writing the first row into an empty table, grep for
everything that reads it and ask what each reader believes the table means".

The migration also has to fix `UNIQUE (ticker, settled_ms)`, which is wrong the
moment two orders on one ticker settle from one market: they share a ticker
*and* a settlement instant, so the second row would be silently rejected. It
becomes `UNIQUE (order_id)` — one position settles once.

Since a migration is happening anyway, ADR 0008's gap 3 is re-costed: **exposure
is fee-exclusive while the cap is spent fee-inclusive (~2%).** It stays open
here — correctly, since it did not belong in this change.

**Closed 2026-08-09, with no migration at all.** The re-costing above assumed
the fix meant adding a column or redefining `limit_price_tenths`. Neither was
needed: the fee is a function of the two values already stored. What actually
blocked it was that exposure was a SQL `SUM` and the fee model is not
expressible in SQL. See ADR 0008.

### 4. Paper exposure counts — against paper, never pooled with live

`current_exposure_dollars` takes the `dry_run` flag of the order being placed
and answers for that population only. One implementation, parameterised — not a
second function, per the repo's rule about deleting one of two paths.

This is a change of position from ADR 0008, and the reason is that settlement
removes the objection: capital is now released, so the cap can open as well as
close.

Two reasons to scope it by population rather than pooling:

- **Pooling is unsafe in the direction that matters.** A live order sized
  against a budget already consumed by fictional positions is refused for a
  fictional reason, and the first live order is the one nobody wants
  mysteriously blocked.
- **It is this repo's standing rule.** Two populations answering different
  questions never share a number; see `two-populations-in-one-record`.

What this buys is the thing worth having: **the cap starts binding in
production today, on paper**, so it is exercised by reality rather than only by
tests before it ever guards real money.

### 5. Paper P&L is a diagnostic. It is never evidence, and never reaches the gate

This is the trap, and it is the one most likely to cause real harm.

The gate is built entirely on CLV. Paper P&L is easier to read, arrives sooner,
and has none of the noise discipline — no clustering, no always-valid bound, no
multiple-comparisons count. It is exactly the shape of number that gets believed
over a more careful one sitting beside it (`computing-the-right-statistic-and-
then-ignoring-it`).

Three things make that structural rather than advisory:

- **The gate does not read `settlements`.** Asserted as a test, so the
  independence is a property of the code and not of anyone's restraint.
- **The module docstring states what paper P&L does not establish**, per
  `CLAUDE.md`: it is contaminated by decision 1's fill assumption, which CLV is
  not — CLV scores every recommendation whether or not it was bet, so it does
  not care whether a fill was real. And it is a win-rate measurement, needing
  ~1,000 observations where CLV needs ~300. It answers "did these bets win?"
  where the gate's question is "did we beat Kalshi's own close?".
- **It is reported with its `n` and no verdict.** No "profitable", no green
  number. The Ledger shows it as a record; the Gate never mentions it.

What paper P&L *is* for: releasing exposure (decision 4), and catching gross
errors — an inverted sign, a side mapped backwards — that CLV would take much
longer to surface.

### 6. `fills` stays empty

Paper fills are not written to `fills`. That table exists to measure
`fee_actual` against `fee_predicted`, `fee_actual` cannot be observed from a
fill that did not happen, and a paper row in it would put a null into the column
the fee calibration reads. The settlement pass reads `orders` directly.

## Consequences

- `max_exposure_dollars` begins binding in production, on paper positions, for
  the first time.
- A second number describing performance now exists, and the ADR's job is to
  keep it in its place. If a future session finds paper P&L quoted anywhere near
  a go-live decision, this decision has failed and that is the thing to fix.
- The settlement pass is a new caller of Kalshi REST on the loop. Unmetered, and
  it only asks about markets with an unsettled paper position.
- Positions on markets that never settle (finding 2) hold exposure open
  indefinitely. That is the safe direction, and it is visible: the pass reports
  how many positions it is still waiting on, so "nothing settled today" and
  "everything is stuck" are different lines.

## What this does not establish

That paper results predict live results. They cannot: the fill assumption is
optimistic in the correlated direction (decision 1), no fee is verified, and no
order has ever rested in a real book.
