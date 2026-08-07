# ADR 0001 — League scope, from the discovery spike

**Date:** 2026-08-06
**Status:** Accepted
**Context:** Build-order step 2, "resolve the three day-one unknowns"

## The question

Does Kalshi list per-**game** sports markets that map onto sportsbook
h2h/spreads/totals? The entire devig pipeline depends on it.

This was genuinely open. The previous project (`kalshi_orderbook_monitor`)
recorded **zero** single-game moneyline tickers across its whole life —
everything it ever saw was a future or a season prop (`KXMLBWINS-NYY-26-T85`,
`KXNFLWINS-27MIN-8`, `KXNCAAFWINS-26ALA-9`). Public sources suggested
`KXNBAGAME`/`KXNHLGAME` existed but nothing pinned the format or the liquidity.
If the answer was no, the project had nothing to match against and the plan
would have needed rewriting.

## What we did

`scripts/capture_fixtures.py` walked `/events?with_nested_markets=true`
(never `/markets` — 99.8% `KXMVE` junk), filtered `KXMVE` on both event and
market tickers, kept sports categories, and captured the raw payload to
`tests/fixtures/events_sports_nested.json`.

Sample: 8,000 events → **3,673 sports events** after filtering.

## Decision

**Game-level markets exist, and scope is broad.** Confirmed series carrying
per-game markets, with moneyline + spread + total for the major ones:

| League | Moneyline | Spread | Total | Other |
|---|---|---|---|---|
| MLB | `KXMLBGAME` | `KXMLBSPREAD` | `KXMLBTOTAL` | `KXMLBRFI` (first-inning run), `KXMLBKS` (strikeouts) |
| NFL | `KXNFLGAME` | — | — | listed weeks ahead of kickoff |
| NCAAF | `KXNCAAFGAME` | — | — | listed weeks ahead |
| WNBA | `KXWNBAGAME` | `KXWNBASPREAD` | `KXWNBATOTAL` | |
| CFL | — | `KXCFLSPREAD` | — | |
| Soccer (many) | `KX{LEAGUE}GAME` | | | MLS, Liga MX, UCL, Leagues Cup, Brasileiro, Liga Portugal, Argentine Prem, NWSL, USL, Colombian, Ecuadorian, Peruvian, ASEAN |
| Baseball (intl) | `KXNPBGAME`, `KXLMBGAME` | | | |
| Esports | `KXLOLGAME`, `KXVALORANTGAME` | | | |

**In scope for v1:** MLB (moneyline, spread, total) and WNBA — both in season
now, both fully quoted, and MLB has the volume. NFL and NCAAF join
automatically when their slates fill out; the ingest is series-driven, not
hardcoded.

**Out of scope for v1:** esports (no sportsbook consensus worth devigging
against on The Odds API), and the long tail of soccer leagues (thin, and each
one needs its own alias table). Neither is excluded permanently — they are
config, not code.

## Ticker anatomy

```
KXNFLGAME-26SEP14DENKC-KC
└──┬────┘ └────┬─────┘ └┬┘
series      event id   outcome

event_ticker = KXNFLGAME-26SEP14DENKC   (everything before the final dash)
```

Event id is `{YY}{MON}{DD}[{HHMM}]{AWAY}{HOME}` with team abbreviations.
`{HHMM}` appears when a league plays multiple games between the same pair on a
date (MLB doubleheaders): `KXMLBGAME-26AUG092020HOUSD-HOU`.

**Do not parse the ticker for team identity.** Each market carries
`yes_sub_title` with the team name in plain text (`"Kansas City"`,
`"Notre Dame"`, `"Michigan St."`), and the event `title` is `"Away vs Home"`.
That is the matching key — an alias table mapping those strings to The Odds
API's full names, not a regex over ticker abbreviations.

## Evidence gathered along the way

- **The derived-ask identity holds.** `yes_ask == 1000 - no_bid` on **2,145
  real quotes, zero violations, zero unreadable**. The rule is real and
  `store/db.py:derive_yes_ask` is correct.
- **Tick structures:** `linear_cent` (2,085 markets) and
  `center_half_edge_half_cent` (60). Zero prices off the tenths grid, so the
  integer-tenths representation is both necessary and sufficient.
- **Liquidity, 24h volume:** `KXMLBGAME` 301k across 42 events (~7k/event);
  `KXLEAGUESCUPGAME` 163k; `KXMLBTOTAL` 86k; `KXWNBAGAME` 48k. Real but modest
  next to `KXPGATOUR` at 25.7M. Depth checks at the quoted price remain a
  suppression input.
- **New wire fields** not in the previous project's notes: `no_bid_dollars`,
  `no_ask_dollars`, `liquidity_dollars`, `market_type`, `strike_type`,
  `primary_participant_key`, `yes_sub_title`, `no_sub_title`. Note that market
  *summaries* do publish asks directly, even though the order book feed
  publishes bids only.

## Consequences

- The plan's step 5 (matching) gets easier: `yes_sub_title` + event `title` +
  `commence_time`, no ticker parsing.
- Spread and total markets exist for MLB and WNBA, so `core/teaser.py` and the
  key-number work have real Kalshi counterparties, not just sportsbook ones.
- League scope is data-driven and lives in config. Adding NFL is a config
  change once its slate lists.

## Caveat, recorded rather than buried

The walk stopped at the `MAX_PAGES = 40` cap (8,000 events) with the cursor
still advancing, so **this is a partial survey**. NBA and NHL game series were
not observed — most likely because both are out of season in August, but the
cap means "not observed" is not "does not exist". Re-run without the cap, or
filtered by series, before concluding anything about a specific league.
