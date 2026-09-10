# ADR 0140 — The parlay leg pool is odds-feed-driven

**Status:** Accepted, 2026-09-10.
**Date:** 2026-09-10.
**Changes nothing.** It records a join direction that has been in the code
since the ladder was built, because every request to widen the parlay screen
has been read as a screen request and is not one. Related: ADR 0070 (the one
pool), ADR 0110 (what the feed costs), ADR 0032 / 0079 (what props cost).
`backend/odds/` is frozen until 10:00Z 2026-09-14; this draft edits nothing,
there or anywhere.

## 1. The mechanism, in one `FROM` clause

`CANDIDATE_SQL` (`backend/parlays.py:531`) is the only statement that builds
the parlay leg pool. Its innermost query reads:

    FROM fair_prices f                                          parlays.py:583
    JOIN event_links l      ON l.id = f.link_id                            :584
    JOIN kalshi_events e    ON e.event_ticker = l.kalshi_event_ticker      :585
    JOIN (… odds_snapshots, MIN(commence_ms) per fixture …) o              :586-609
    WHERE f.market IN ('h2h', 'spreads', 'pitcher_strikeouts',
                       'batter_total_bases', 'batter_hits',
                       'batter_home_runs', 'batter_rbis')                  :611-617

**Every row that can become a leg is a `fair_prices` row.** `kalshi_markets`
is absent from this statement entirely. The venue enters one step later, in
`candidate_pool` (`parlays.py:662`), which loops over the scan's own rows and
reads Kalshi's markets **per event ticker that the scan produced**:

    for row in freshest.values():                                          :739
        event_ticker = row["kalshi_event_ticker"]                          :740
        markets_by_event[event_ticker] = conn.execute(
            "… FROM kalshi_markets WHERE event_ticker = ? …", …)           :743-753

and the `CandidatePool` docstring already says so in its own words: *"The
per-event `kalshi_markets` loop is keyed off the *unfiltered* scan"*
(`parlays.py:639-641`). That comment was written about horizon-independence —
the reason the loop sits above the window filter — but it states the direction
exactly.

## 2. The match loop only ever fails one way

`ladder_candidates` iterates the consensus rows, not the venue's markets
(`parlays.py:841`):

    for (link_id, market, outcome, player, point), row in freshest.items():

For each such row it goes looking for a Kalshi market — the prop arm at
`:916-937` (`_prop_rungs(...)` keyed on `(norm(player), float(point))`), the
spread arm at `:940-971`, the moneyline arm at `:972-981` — and when it finds
none it counts a refusal (`:983-984`):

    count("prop_no_kalshi_rung" if market in _PROP_MARKETS
          else "no_kalshi_market")

**There is no symmetric counter, and there cannot be one.** A Kalshi market
with no consensus row behind it is not refused by this code; it is never
enumerated. It has no reason code, appears in no `excluded` tally, and is
invisible on the thin-slate copy the desk shows when a card comes up short.
The one direction that leaves evidence is the direction the join runs.

## 3. A `fair_prices` row is a purchase

The pool's upstream is not a table that happens to be populated. `fair_prices`
has exactly one writer, `write_fair_price` (`backend/runner.py:967`, the
`INSERT` at `:1056`), with three call sites — moneyline (`:2212`), spreads
(`:1338`) and props (`:1760`) — and each one is reached only through
`consensus_devig(books.outcomes, books.quotes_by_book, …)`
(`runner.py:2204`, `:1331`, `:1752`) over quotes that a paid odds call
returned. No book quotes, no devig; no devig, no row; no row, no leg.

The linking step runs the other way — `link_event` resolves one *Kalshi* event
to at most one sportsbook fixture (`backend/match/linker.py:356`) — and that
matters only as a second necessary condition. A link with nothing priced
across it contributes no candidate, because the scan selects from
`fair_prices`, not from `event_links`.

## 4. The decision

**A request to add a market type to the parlay screen is a decision about the
odds feed, and its cost is paid in API credits on every sweep — not in
frontend work.** Anyone answering such a request states which feed purchase it
requires before discussing the screen at all.

The two live cases:

### 4.1 Totals — a decision about `ODDS_MARKETS` and the book set

One `/odds` call costs `max(1, len(markets) * len(regions))`
(`backend/odds/budget.py:66-67`). Live runs `ODDS_MARKETS = "h2h,spreads"`
(`fly.live.toml:496`) against `ODDS_REGIONS = "us,eu"` (`:437`), inside
`ODDS_DAILY_CREDIT_BUDGET = "700"` (`:252`); the repo default is `h2h` alone
(`backend/config.py:393`, `.env.example:141`), and `config.py:386-392` states
the multiplication in the loader's own comment: *"Each extra key multiplies
`sweep_cost` for every sport on every refresh."*

So a `KXNFLTOTAL` leg is an `ODDS_MARKETS` edit — and, because the region set
is the other factor, a decision about which books the consensus is drawn from.
ADR 0110 priced that trade and dated the only lever it found to 2026-09-28.
Nothing here changes that date or that arithmetic; this section records **why**
the totals question lands on `ODDS_MARKETS` rather than on the card.

The venue half already exists and is the sharpest illustration of the
asymmetry: `classify_series` maps the `TOTAL` suffix to `market_type =
"total"` (`backend/kalshi/discovery.py:155-160`), so Kalshi's totals markets
are discovered and stored in `kalshi_markets` today. They are still not legs,
because no `totals` key is bought, so no `fair_prices` row exists for them,
so the scan at `:583` never sees them. The market is in our database and
unreachable from the ladder.

### 4.2 Props — a decision about `prop_market_keys()`, and it is one edit in two halves

Props are billed per *event*, not per sweep:
`prop_cost_per_event = sweep_cost(prop_market_keys(), config.regions)`
(`runner.py:2523`), consumed by the planner's reservations
(`backend/odds/timing.py:2040-2044`, `:2168-2171`). `prop_market_keys()`
returns a flat list — `list(PROP_BASE_MARKETS)`, `backend/odds/client.py:181`,
five MLB keys at `:128-134` — and its own docstring states the consequence:
*"One definition, because the count is a price."* Every key in that list is
requested for every prop event of every sport that has any prop series.

That is why props cannot be a config toggle, and why the edit has two halves
that are unsafe apart. `backend/kalshi/props.py:133-160` already records it:

- `PROP_SERIES` (`props.py:162`, `dict(MLB_PROP_SERIES)`, `:69-75`) is read by
  `is_prop_series` → `discovery.py:390`, which decides what is **admitted**
  into `kalshi_markets`, and by `PROP_SERIES.get` → `runner.py:1697`, which
  maps a series to the book market it is priced against.
- `NFL_PROP_SERIES` (`props.py:104-108`) is measured, tested and deliberately
  **not merged in**: `PROP_SERIES = {**MLB_PROP_SERIES, **NFL_PROP_SERIES}`
  alone would admit ~2,000 NFL prop markets a slate that nothing prices, while
  adding the three NFL keys to `prop_market_keys()` alone would request them on
  every MLB event too, taking a five-key event to eight for three keys that
  return nothing.

Admitted-but-unbought props are rows nobody prices; bought-but-unadmitted props
are credits spent on markets nothing reads. The buy side has to become
sport-aware in the same edit.

## 5. What is true on the screen today, and the second gate

The prop half of §4.2 is **already done for MLB**, and this is where the
mechanism is easiest to misread. `CANDIDATE_SQL:611-617` admits the five MLB
prop markets, `ladder_candidates` has a working prop arm, and prop legs are
therefore in the pool. They do not appear on a card because of a *second*,
independent gate: every `Recipe` in `CARD_SHAPES` is built with
`markets=TEAM_MARKETS_ONLY` (`backend/core/ladder.py:138`, and each recipe
below it), the per-card market filter ADR 0139 §1 describes.

So there are two gates, and only one of them is free:

| gate | where | cost to open |
|---|---|---|
| is a consensus price bought at all | `prop_market_keys()`, `ODDS_MARKETS`, `ODDS_REGIONS` | credits, every sweep, forever |
| does *this card* draw from that market | `Recipe.markets` (`ladder.py:138`) | one visible edit per card |

ADR 0110's consequence line — *"No totals leg and no prop leg reaches a parlay
card this season"* — holds today through the **recipe** gate for MLB props, not
through the feed gate, which is open for those five keys. That is a correction
of the reason, not of the outcome, and it is the reason the distinction is
worth an ADR: a session that reads 0110 alone would conclude an MLB prop leg
needs a credit decision, when for those five keys it needs a `Recipe`.

## 6. Context, not decided here

Joe asked on 2026-09-10 for props as parlay legs (`tasks/NEXT.md`, this
session's (B): *"i want to bet on props for parlay legs"*). That **overturns
map ticket #12**, closed 2026-09-02 on his answer *"option A — he does not
really bet props; drop them from the brief"*
(`docs/decisions/2026-09-02-ticket-12-research-packet.md`); the narrower want
is legs, not picks, and #12 currently says the opposite.

This draft records the mechanism only. Whether to serve prop legs, for which
sports, on which cards, and at what credit cost is a separate and open
decision, and #12 still needs reopening or superseding.

## 7. Consequences

- A "add X to the parlay screen" request is answered by naming the feed
  purchase first: which market key, in which regions, at what per-call or
  per-event cost, against the day's budget. If the answer is "the feed does not
  buy it", the screen work does not start.
- NFL props remain one edit in `props.py` **plus** a sport-aware
  `prop_market_keys()`, and neither half ships alone (§4.2). Both sides of that
  edit are inside the `backend/odds/` freeze until 10:00Z 2026-09-14 for the
  buy half.
- MLB prop legs on a card are a `Recipe` decision, not a credit decision (§5).
  Anyone quoting ADR 0110's consequence line for MLB props quotes it with §5
  beside it.
- The absence of a reverse reason code (§2) stays absent. A "Kalshi market with
  no consensus" counter would enumerate the venue, which is the join this
  design does not run.

## 8. What this does not establish

- **It does not decide whether to add any market type.** Not totals, not NFL
  props, not MLB props on a card. It says where such a decision is taken.
- **It prices no expansion.** No per-slate credit figure is asserted here; the
  only arithmetic quoted is the formula at `budget.py:66-67` and the deployed
  config values cited by file:line. `.env.example:94-99` records why a
  per-slate figure derived from assumed inputs is not written down, and that
  rule is followed here.
- **It does not overturn ADR 0110.** The `eu`-drop lever stays refused until
  2026-09-28 on 0110's two preconditions, and §5 corrects the *reason* one of
  0110's consequence lines is true for MLB props, not the line's outcome.
- **It does not claim the pool query is the only thing between a market and a
  card.** §5 names the second gate; there may be others downstream
  (`build_ladder`'s freshness rule, `combo_eligible_events`, the venue's own
  refusal to combine), and none of them is surveyed here.
- **It establishes nothing about whether prop legs are a good bet.** The hunt
  is closed (ADR 0038) and ADR 0037 refuted the in-house prop model; a leg the
  feed can price is a leg with a consensus number beside it, not a leg with an
  edge.
- **It is not a claim about `KXMVE` combination availability.** Whether Kalshi
  will combine a prop leg with a game leg is a separate, partly unmeasured
  question (`backend/kalshi/combos.py`'s calendar caveat; ADR 0012 §5).
