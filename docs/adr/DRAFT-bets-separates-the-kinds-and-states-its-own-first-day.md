# DRAFT — `/bets` separates the kinds, states its own first day, and says what is open in words it can keep

**Status:** Draft in a lane; the ordinal is taken at the merge boundary
(`docs/adr/README.md`).
**Date:** 2026-09-03.
**Decides:** GitHub #21 (josephsapinoso/kalshi-cockpit), resolved by Joe on
2026-09-03 as **21A** — *"separate the kinds, show what is open, date the
record. No backfill."* Items 2, 3 and 1 of his ruling are built here; item 4
is recorded as not buildable in this table (§5).
**Extends** ADR 0062 (the tool is a betting desk; `/bets` is its record) and
ADR 0071 §2.2 (price transparency, and braking only where a screen would
otherwise state something false). **Touches nothing** in `gate.py`, the
poller, the schema, or the standing no-aggregate ruling, which it pins
harder.

## 1. What was wrong with the screen, in Joe's words and the ticket's

`/bets` "already is the performance record Joe asked for" and calls itself
"a bank statement, not a report card". Four structural holes, none a bug:

- **Combination markets were mixed in with single games, and they were the
  majority** — 50 `KXMVE` rows of 77 on the day of the ruling. A parlay and a
  moneyline are not the same kind of bet, and 50 of the rows wore a CLV
  column that read "close not read yet" on every one of them, as if the
  close were late rather than absent.
- **The page typed its own history.** "Anything settled before the recorder
  started on Aug 18 is missing" was hardcoded, and the live mirror's first
  settlement is **2026-08-11T02:37Z** (`MIN(settled_ms)` over
  `venue_settlements`, read on live 2026-09-03): the poller started on the
  18th, but the settlements endpoint carried a week of history when it was
  first read. The sentence understated the record by a week for two weeks.
- **Open positions were absent from the money picture.** The strip served a
  count and a *value* that refuses on every non-zero account ("the venue
  reported a value whose unit has never been pinned"). Joe asked for what is
  **staked**, not what it is worth.
- **A parlay never gets a result of any kind** until the venue settles it —
  item 4, §5.

## 2. What was built

### 2.1 Two kinds, two sections, each with its own count and its own sum

`bets_record` classifies every row by ticker through
`estimates.classify_ticker` — the one `KXMVE` prefix check the repo has
(`_MULTI_LEG_PREFIX`), reused rather than respelled; a source test fails if
`bets.py` ever spells the prefix itself. The wire gains `kind` on every row
(`"single" | "combo"`) and a `sections` block over the **whole table**, one
per kind: `total`, `net_tenths`/`net_display`, `computable`, `uncomputable`.
`single.total + combo.total == total` by construction and by test.

The page renders the two sections in that order — single games first, where
CLV lives — each headed by the server's whole-table count and its own net
**sum**. The pooled net strip is unchanged. A per-kind sum beside the pooled
sum is the "print the parts beside the aggregate" rule from CLAUDE.md's
measurement section; a per-kind *rate* would be the banned aggregate and none
is served or rendered. The kind is the server's: the page groups by
`bet.kind` and never inspects the ticker string.

**The combination section renders no CLV column and no CLV words.** A
`KXMVE` ticker cannot have a `closing_lines` partner — combos are excluded
from discovery — so a combo row's `clv_refusal_reason` is `combo_unscorable`,
distinct from `no_closing_line`, and the row's CLV line is not drawn at all.
`clv_coverage` now counts **single-game rows only** and says so
(`population: "single"`, `denominator: <singles>`), so the sentence reads
"scored on N of 27 single-game bets" rather than "on 1 of 77" for a record in
which 50 rows were never scorable. Scored + refusals partition exactly the
singles.

### 2.2 The page states its own first day

`bets_record` serves `first_settled_ms` — `MIN(settled_ms)`, `None` on an
empty table, never 0 (a 1970 date is a claim about history the mirror does
not have). The completeness sentence renders it with its year and **still
says the mirror is not complete**: the venue's endpoint drops history (ADR
0044 design point 6), so anything dropped before the recorder read it is
missing, and ADR 0044 §8 keeps the pre-protocol settlements out of the study
population regardless. No month-day literal survives in the page's code; a
test greps for one.

### 2.3 The open-now strip says what is staked — and refuses, in words that say why

`open_positions` gains `staked_tenths`, `staked_display` and
`staked_refusal`, and **the figure is refused unconditionally**, with the
reason rendered from the server. The refusal is the decision, and the reasons
are the record:

1. **`fills` stores no buy-against-sell.** The venue's fill payload carries
   `action` (`buy`/`sell`) — `tests/fixtures/portfolio_fills_redacted.json`
   shows the field — and `portfolio_poll.parse_fill` drops it; the `fills`
   table has no column for it. So `SUM(count × price_tenths)` over fills
   books an *exit* as if it were more money committed.
2. **"Fills on tickers with no settlement row" is not "open".** The
   settlements endpoint drops history and the poller has had outages
   (`docs/measurements/2026-08-28-recorder-silence-is-chronic.md`), so a
   position settled but never mirrored would read as open forever; a position
   bought and sold before settlement has fills and no settlement row and is
   not open either. The figure is wrong in **both** directions at once, which
   is not a bound of any kind.
3. **The venue's own per-position figure is not stored.** The
   `/portfolio/positions` row shape, observed 2026-08-30, carries
   `market_exposure_dollars` and `total_traded_dollars`
   (`tests/test_rest.py::OBSERVED_POSITION_ROW`), but `poll_positions` counts
   rows and parses none — deliberately, after five parsers in this repo's
   history were written against imagined wire formats — and neither field's
   unit or fee treatment is pinned.

**What `tonight_activity`'s SUM actually measures, verified before it was
declined for reuse:** every fill since the day roll, buys and sells alike,
on any ticker whether or not it has since settled, with no `source` filter.
That is honest for its own question — "what has moved tonight" — and would
have been a lie here. It was not reused.

What would pin the figure, either of: the poller records `action` on fills
(a schema step, integrator-owned — `SCHEMA_VERSION` is one of the three
counters that can be allocated twice), or it stores the venue's per-position
exposure with its unit measured against a known position. Until one of those
lands, `None` — never `$0.00` beside "Open now: 3 positions", which is the
false negative in the flattering direction on the one figure that describes
money at risk.

The count is kept, on the same 30-minute bound as before. "Never summed with
cash" — TonightStrip's rule — is pinned twice: on the payload (the block's
key set and a forbidden-word set) and on the component's source (no
arithmetic between any two of count, value and staked; no word for cash, a
total, or a net).

## 3. What the standing ruling now pins

**No average, win rate, hit rate, streak or trend line anywhere on `/bets`**,
for either section or the whole, until thirty scored bets exist with the
per-group view beside them. That was a docstring and a narrow source grep
(`hit_rate`, `avg_clv`); it is now:

- `tests/test_bets.py::test_module_computes_no_aggregate_clv`, over
  `backend/bets.py` with docstrings stripped, banning `avg(`, `mean(`,
  `average`, `win_rate`, `hit_rate`, `streak`, `trend`, `/ computable`,
  `/ total` — so the module may keep *saying* "no average" in prose while a
  guard enforces it in code;
- `tests/test_bets_sections.py::TestNothingHereGradesHim`, over the page and
  the strip, comments stripped, banning the same words in the screen's own
  vocabulary and any client-side division over the record.

The section blocks carry exactly five keys and every numeric one is an
integer; a test pins the key set so a rate cannot be added quietly.

## 4. Mutation record

Every new guard was disabled, watched fail, and restored by reversing the
exact edit (byte-compared to the original). The tests that went red per
mutation are in the commit message. Two are worth a line here:

- Replacing `bet_kind`'s delegation with a local `startsWith("KXMVE")` left
  every behavioural test green and turned only the source guard red — which
  is the point of that guard: two spellings of one predicate is the defect
  CLAUDE.md records under the window banner, and behaviour tests cannot see
  it until the spellings diverge.
- Replacing the staked refusal with `tonight_activity`'s SUM turned the
  refusal test red *and* the source guard red (`fills`, `SUM(` reached
  `open_positions`).

## 5. Item 4 is not buildable in this table, and is left alone

*"A combo reads unsettled until the venue settles it."* `venue_settlements`
holds settled positions by construction — a row is written when the venue
settles — so an open combination bet is structurally absent from `/bets`,
not mis-stated on it. Delivering the line means wiring `parlay_positions`
(ADR 0078's hand-recorded parlays) into the record screen, which 21A did not
price and which crosses the boundary that keeps `parlay_positions` out of
anything the gate reads. The current behaviour stands; the completeness
sentence now says in words that an unsettled combination bet is not here
either, which is the braking case ADR 0071 §2.2 reserves — not a nag, a
refusal to imply completeness.

## 6. What this does not establish

- **That the mirror is complete, or how incomplete it is.** `first_settled_ms`
  is the oldest row the poller has; it is not the date Joe's first bet
  settled, and the page says so. How many settlements the endpoint dropped
  before 2026-08-18 is unmeasured and, with the endpoint's history gone,
  unmeasurable from this side.
- **Anything about what is staked.** The refusal is the whole claim. §2.3's
  three reasons are why no number is served; they are not a plan to serve one.
- **That two sections are the right cut forever.** "Single" here means "not a
  combination market" and includes non-sports hand bets; a sport-by-sport
  cut, or a market-type cut, would be a new decision on new evidence.
- **Anything about rendering.** `next build`/`check_mobile.py --width 390`
  was not run in this lane (no dev server in the worktree); the layout
  changes are a second `<h2>`/`<ul>` pair and two `<p>` lines inside widths
  the page already used, and `tsc --noEmit` is green.
- **Anything about the combos' fee or settlement arithmetic.** A voided
  combination settles with `market_result = ''` and refuses the formula here
  exactly as before (Amendment 4 of ADR 0044 amends `study_loss_dollars`, not
  `bets.settlement_net_tenths`); it renders "—" and is counted as
  uncomputable in its section.
