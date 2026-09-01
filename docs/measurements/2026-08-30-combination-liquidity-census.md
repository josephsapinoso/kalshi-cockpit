# Every open combination on Kalshi, and not one of them is buyable

Taken 2026-08-30 21:43-21:52Z against the live venue, read-only and
unauthenticated where possible. The question was scoping, fixed before the
data was seen: **if the parlay desk stopped inventing combinations and instead
showed existing ones that already have a seller, how many rows would it have?**

The answer is zero, and it is zero by a wide margin rather than narrowly.

## The census

`GET /markets?series_ticker=…&status=open&limit=1000` on the two combination
series (a targeted query per series — `/markets` is never paginated blind,
CLAUDE.md), then `GET /markets/{ticker}/orderbook` on the rows most likely to
have a book.

    open combination markets                        61
      KXMVESPORTSMULTIGAMEEXTENDED                  37
      KXMVECROSSCATEGORY                            24

    carrying a readable quoted ask                   0 / 61
    liquidity_dollars > 0                            0 / 61
    with any traded volume, ever                     1 / 61   (45 contracts)
    order book non-empty on either side              0 / 6 read

The six books read were the six highest-volume rows, so this is the best case
available, not a random sample. The single row that has ever traded — 45
contracts — has an empty book on both sides today.

## Why the list rows look quoted and are not

    yes_ask_dollars   = 0.0000     on all 61
    no_bid_dollars    = 1.0000     on 59 of 61
    liquidity_dollars = 0.0000     on all 61

A NO bid of $1.00 is the boundary, not an offer: it is paying a full dollar
for a contract that pays at most a dollar. The derived YES ask is
`1 − 1.00 = $0.00`, which is exactly what `yes_ask_dollars` reports. Nothing is
resting.

**This is not the wire-rename failure that would produce a false zero.** Every
field is present and correctly named on the payload — `yes_ask_dollars`,
`no_bid_dollars`, `mve_selected_legs`, `liquidity_dollars`, `volume_fp` — and
`scripts/measure_combo_book_presence.py` independently selected 0 eligible rows
from the same 61 by its own pre-registered definition. Two readings, one
conclusion.

### Why the JSON artifact beside this document has no rows — annotated 2026-09-01

`2026-08-30-combo-buyability.json` reads `{"api_calls": 2, …, "rows": []}`, and
an empty `rows` array next to a document quoting 61 and 0-of-6 looks like a
harness that failed to write its output. **It is not. The empty array IS the
finding, and re-running the script would reproduce it exactly.**

`measure_combo_book_presence.eligible()` (`scripts/measure_combo_book_presence.py:495`)
requires `readable_quote(market) is not None`, and the pre-registered definition
of that, fixed before collection, is `0 < ask < 1` — *"a `0.0000` ask is not an
ask."* Every one of the 61 open combinations reported `yes_ask_dollars = 0.0000`.
So **zero rows were eligible**, and a run that selects nothing writes `rows: []`
by construction. The script's own "what this does not establish" list already
says it: *"Rows with no readable ask are excluded by construction, so no
statement here covers them."*

**And `api_calls: 2` against 61 markets is the same fact, not a second one:**
the 61 came out of exactly two bulk discovery reads — one per entry in
`DISCOVERY_SERIES`, `("KXMVESPORTSMULTIGAMEEXTENDED", "KXMVECROSSCATEGORY")`,
at `scripts/measure_combo_book_presence.py:529` — and the script's stated budget
of `2 + 1 + N + 1` (`:92`) then spent nothing further because `N = 0`, so the
batched leg read, the per-row orderbook reads and the contemporaneity re-read
never fired. Two calls is what a census of 61 markets costs when Kalshi returns
them a page at a time and none of them earns a follow-up; it is **not** evidence
that 59 markets went unread.

The consequence worth stating plainly, because it is the stronger reading:
E2 was designed to ask *"is a combination's list quote backed by an order
book?"*, and on 2026-08-30 **not one combination had a list quote to check.**
The question the artifact was built to answer had no population left. That is a
harder result than any row-level rate it could have printed.

**What is genuinely not re-derivable from this repo**, and should be read as a
limit on the two ADRs that rest on it (0085's card, and 0078's justification for
`/hedge`): the 61 / 0-of-61 / 0-of-6 figures come from the ad-hoc `/markets` and
`/markets/{ticker}/orderbook` sweep described at the top of this document, which
committed no artifact of its own. They are prose. The `measure_combo_book_presence`
null result corroborates them from a second direction — it agrees there was
nothing quoted — but it does not reproduce the counts.

## What it means, and it is stronger than ADR 0012 §5

ADR 0012 §5 records combinations as **enter-only**: no resting YES bid on 40 of
40 books, so you can enter and cannot exit. This census says the entry side is
usually missing too. Across 40 books on two dates in August and 61 markets
today, **this project has never once observed a combination that could be
bought at a quoted price.**

A resting buy is therefore not a workaround. The desk placed one tonight at
20.1c for 9 contracts (ADR 0084, and it worked exactly as designed) and it is
the entire book on its market — `yes_dollars: [["0.2010","9.00"]]`, nothing on
the other side. Raising the price does not obviously help either: a limit order
only attracts a counterparty who is *looking*, and on a market minted on demand
that nobody else knows exists, there may be no one looking at any price.

## What this does NOT establish

- **That a combination can never fill.** One market has traded 45 contracts, so
  a counterparty has existed at least once. This is a census of one moment; it
  bounds how often, not whether.
- **That liquidity will not arrive.** Kalshi added combinations recently and
  moved them to their own exchange shard six days ago. A venue that is still
  building a product is the wrong thing to declare permanently empty.
- **Anything about the legs.** Single-game markets are liquid and unaffected;
  this is about the combination product only.
- **Anything about price quality.** No row here had a price to assess, so
  nothing is said about whether Kalshi's combination prices are good.
- **That a sportsbook is cheaper.** It says a sportsbook will *take the bet*,
  which is a different claim. The fee and vig comparison is untouched.

## What it changes

The parlay desk's job on this venue is **pricing, not buying**. It can say what
a parlay is worth off sharp-book consensus, and that number is useful precisely
where the bet can actually be placed — which today is a sportsbook. See
ADR 0085.
