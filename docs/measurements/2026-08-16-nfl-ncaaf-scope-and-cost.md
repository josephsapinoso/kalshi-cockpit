# NFL and NCAAF: what is deployed, what it costs, and what can never price

**Taken:** 2026-08-16. Four questions were asked before writing any code, because
the calendar is the constraint: NCAAF opens 2026-08-29, NFL regular season
2026-09-10, and the preseason window shuts ~2026-09-01.

All four are answered. A fifth thing was found that none of them asked about and
it is the largest number in this document.

## The surprise, first, because it changes every other figure here

**Two of the three market keys bought on every team sweep are consumed by
nothing.**

`ODDS_MARKETS = "h2h,spreads,totals"` (`fly.live.toml:238`). A team sweep costs
`len(markets) × len(regions)` = 3 × 2 = **6 credits** (`backend/odds/budget.py:66-68`).

But the pricing path reads `h2h` only:

- `book_quotes_for_event(conn, odds_event_id, *, now, market=MONEYLINE)` where
  `MONEYLINE = "h2h"` (`backend/runner.py:136, 252`).
- Its **only** call site is `backend/runner.py:1218`, which passes no `market`
  argument and therefore takes the default.
- Every other `market_key` consumer in `backend/` is the **prop** path
  (`runner.py:486, 499, 810-811, 842, 1537, 1783`; `api/routes.py:1511, 1619`).
- `"spreads"` and `"totals"` appear in exactly one place outside tests:
  `TEAM_MARKETS` in `backend/odds/client.py:95`, which is the *fetch* allowlist.

There is no consumer. **4 of every 6 team-sweep credits buy data that no
suppression rule, devig, EV computation, sizing calculation or API response
reads.** This is the same shape as the `model_probability` column CLAUDE.md
documents: fetched, stored, and dropped.

Setting `ODDS_MARKETS = "h2h"` cuts every team sweep from 6 credits to 2. The
consequences are in §3.

## a. Do KXNFLSPREAD / KXNFLTOTAL carry real depth?

**Yes — and it does not currently matter, because they can never price.**

Measured live against the exchange (unmetered), **1,179 active markets across all
six series, 1,179 orderbooks read, 0 errors**:

| Series | Active | Both sides quoted | Volume | % traded | Median width | Median size @ ask | Tradeable\* | Per game |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| KXNFLGAME | 64 | 100% | 739,477 | 100% | 2.0c | 1,319 | 42 | 1.3 |
| KXNFLSPREAD | 404 | 100% | 152,312 | 80.4% | 15.5c | 776 | 44 | 2.8 |
| KXNFLTOTAL | 304 | 100% | 83,793 | 71.7% | 16.0c | 535 | 37 | 2.3 |
| KXNCAAFGAME | 36 | 100% | 815,592 | 100% | 2.0c | 767 | 26 | 1.4 |
| KXNCAAFSPREAD | 219 | 100% | 11,211 | 13.2% | 32.0c | 50 | 3 | 0.4 |
| KXNCAAFTOTAL | 152 | 100% | 838 | 7.2% | 52.0c | — | **0** | 0.0 |

\* width ≤ 5c, derived ask in 10c–90c, ≥10 contracts at the touch.

**"Any resting depth on both sides" is 100% in all six series, so that test
discriminates nothing.** All the signal is in width and size.

- **KXNFLSPREAD / KXNFLTOTAL: TRADEABLE.** The 404-market denominator misleads —
  25 lines per game exist and only the 1–3 near the true line are ever wanted,
  which are exactly the tight ones. Every one of the 16 games carries ≥1
  tradeable line, median 2. e.g. `KXNFLSPREAD-26SEP13BUFHOU-HOU2` ask 51c ×2,654.
- **KXNCAAFSPREAD: THIN.** 3 tradeable of 219; 5 of 8 games have zero.
- **KXNCAAFTOTAL: NO DEPTH.** 0 tradeable of 152. 838 contracts of volume in the
  entire series. The one market passing width+size sits at 91c.

**But the pricing path refuses all of them.** `backend/match/linker.py:281-284`
returns unmatched for any Kalshi event whose side-set is not exactly 2. Live
`unmatched_events`, still firing at `2026-08-16T23:06:38Z`:

```
KXNFLSPREAD    "expected 2 sides, got 25: ['Cincinnati wins by...']"
KXNFLTOTAL     "expected 2 sides, got 19: ['Over 27.5 points scored'...]"
KXMLBTOTAL     "expected 2 sides, got 11: ['Over 2.5 runs scored'...]"   n=19,246
```

**This is league-independent.** Spread and total have never priced for *any*
sport. Props got an inheritance escape hatch (`linker.py:345-375`); spread and
total did not. So "NFL is in scope" describes 1 of its 3 series, and 708 NFL
spread/total markets are being quoted into the database that cannot become a
recommendation.

**Two qualifications on the depth reading, both load-bearing:**

1. **NFL spread/total exist only for the Sept 9–13 week.** Kalshi lists no
   spread or total product for preseason at all — a product absence, not thin
   depth. No re-measurement changes it.
2. **NCAAF's thinness is measured at 13 days out and cannot be separated from
   horizon.** Every NCAAF spread/total market on the exchange is 12.8–13.2 days
   from kickoff; there is nothing nearer to compare against. KXNCAAFGAME at the
   *same* horizon is thick, so it is not a whole-league effect — but it could be
   a horizon effect specific to derivatives. **Re-run the probe Aug 27–28**, two
   days before the opener. Today's NCAAF reading must not be promoted into a
   claim about NCAAF on game day.

Incidental, and it contradicts a repo prior: **all six series are
`price_level_structure: "linear_cent"`, step `0.0100` — zero deci-cent markets in
1,179, confirmed both by the declared field and by no level in any book being off
the whole-cent grid.** The "~25% of Kalshi markets tick in deci-cents" prior does
not hold for football.

## b. Re-deriving the sweep cost for a spiky weekly slate

**The MLB-tuned ~36 credits/hour figure survives, but it was being read as the
wrong kind of number.**

Cost does **not** scale with game count. `path = f"/sports/{sport_key}/odds"`
(`backend/odds/client.py:305`) is **one HTTP call per sport returning the whole
slate**. A 100-game NCAAF Saturday costs the same *per call* as a 1-game slate.

Refresh cadence is `max_odds_age_ms × 2 // 3` = 900s × 2/3 = **600s**
(`timing.py:122-142`), so an open sport bills 6 calls/hour × 6 credits =
**36 credits/hour — per sport with an open window**, not per slate and not per
day. A sport is open at `t` iff some kickoff cluster anchor lies in
`[t+15min, t+75min]` (`timing.py:416-417, 119`); anchors <60 min apart merge.

**Open hours × 36 = the bill.** That is the whole model, and it means the
question "does a spiky weekly slate break the MLB-tuned scheduler?" has the
answer **no, a spiky slate is the best case** — concentration shortens the span.

| Slate | Open hours | At 6 cr/call | At 2 cr/call (§3) |
|---|---:|---:|---:|
| NFL Sunday (3 merged windows) | 3.0 | 108 | 36 |
| NFL week (+ TNF, MNF) | ~5 | 180–210 | 60–70 |
| NCAAF Saturday (16:00Z–03:30Z chains) | 12.5 | 450 | 150 |
| NCAAF week (+ Thu/Fri) | ~15 | 520–590 | 175–197 |
| MLB day (measured 08-16: 2.6h + evening block) | 5–7 | 180–250 | 60–83 |

Live record: monthly budget **13,000**, daily **600** (`fly.live.toml:185, 191`);
month-to-date **1,100 of 13,000**. Measured days: 08-13 and 08-14 at 48 each
(pre-rolling-refresh), 08-15 at 390 (the prop-fanout outage), 08-16 at **416** =
13 props × 20 + 26 team calls × 6.

**Scheduled props are OFF** (`ODDS_BUY_PROPS_ON_SCHEDULE="false"`,
`fly.live.toml:272`) and `PROP_BASE_MARKETS` is MLB-only, so football has no prop
line item either way. The 20 credits/event prop figure in the docs is
**confirmed** (10 market keys × 2 regions), not refuted.

## c. Pricing NCAAF, and deciding deliberately

**At the current 6 credits/call, NCAAF + MLB on the same Saturday breaks the
cap:**

```
NCAAF   14:45Z-03:15Z, 12.5h      450
MLB     ~5-7 open hours       180-250
                             -------
                             630-700   against a 600/day cap
```

**The failure mode is worse than the overrun.** When the daily cap binds,
`decide_sweeps` returns `remaining == 0` and **every sport stops** for the rest
of the budget day (`timing.py:1023-1033`). NCAAF opens at 14:45Z and MLB's
evening block opens ~22:00Z, so **NCAAF spends the day first and MLB's evening
goes dark** — and MLB is the population the CLV record is accumulated on. A
refused sweep writes no `api_credits` row (it goes to `odds_sweep_log`), so the
outage appears as an *absence* in `credits-day`, not a spike. `sweep-log` is the
only table that would show it.

**§3's change dissolves this without a tradeoff**, so no NCAAF slate needs
cutting. Recorded here anyway, because it is what the arithmetic says if the
`ODDS_MARKETS` change is *not* made.

## d. Preseason: SKIP

**Recommendation: skip NFL preseason entirely. Do not defer it — skip it.** The
thesis dies on an instrument problem, not a modelling one.

- **Kalshi lists no NFL preseason player props.** Ten prop series probed
  (`KXNFLPASSYDS`, `KXNFLRECYDS`, `KXNFLRSHYDS`, `KXNFLREC`, `KXNFLANYTD`,
  `KXNFLRSHATT`, `KXNFLPASSATT`, `KXNFLPASSCOMP`, `KXNFLTD`, `KXNFLFIRSTTD`) —
  **zero open events**. The entire preseason board is `KXNFLGAME`: 16 games, 32
  markets, moneyline only. Playing-time information prices snap counts and stat
  lines. Kalshi does not sell those in preseason.
- **The spread eats the edge ~20×.** All 32 preseason markets opened 2026-08-16
  at 16:20Z. Median spread **21.0c** (range 1–41c) at 4–7 days out, against
  **1.0c** for regular-season games 24–29 days out. Time-to-kickoff does not
  explain that; being preseason does. Observed edges in this repo are 3.5–5.5
  *tenths* of a cent and total fee headroom is 0.63 points.
- **The window is 7 days and cannot produce a measurement.** Every remaining
  preseason game is Aug 20–23 — 16 games, so G = 16 against a registered floor
  of 300. Not an underpowered result; not a result.
- **There is a build blocker on day one.** `backend/kalshi/discovery.py:298`
  deliberately excludes `"Pro Football Preseason"`, and the comment says why:
  `KXNFLGAME` carries both league strings and `kalshi_series.league` is written
  on first insert and never updated, so un-excluding it would silently relabel
  the whole NFL evidence record retroactively. That is a schema migration before
  a line of model gets written.

**The general lesson, which is the part worth keeping:** when a market maker does
not know what a thing is worth, the softness shows up as **width, not as a
mispriced tight quote**. Width cannot be taken, only made into — and making is a
different business with adverse selection, needing the maker path.

**One thing that survives, as a hand-read and not a feature.**
`KXNFLWEEKCOMPETE-26W1` ("Players to Compete", Week 1) is live: 14 markets,
median spread **1.0c**, median $611 at the ask, closes 2026-09-15. It is a
regular-season instrument priced by preseason information (the ~Aug 26 cutdown,
injury reports, depth charts). **G = 14 means it can never enter the record as
evidence** — look at it by hand around Aug 27, and keep it out of the measured
population.

## What is actually deployed, verified on the machine

| Claim | Verdict | Evidence |
|---|---|---|
| A series/league allowlist exists in config | **FALSE** | No such key in `.env.example`, `config.py`, `fly.live.toml`, or `flyctl secrets list`. Scope is **code**: `discovery.py:235-242, 340, 180` |
| `"Pro Football" → americanfootball_nfl` deployed | **TRUE** | Read off the machine, not the repo: `IN_SCOPE_LEAGUES` includes Pro Football, NCAA Football; `OUT_OF_SCOPE_LEAGUES` includes `'Pro Football Preseason'` |
| All six series discovered and recording | **TRUE, live now** | `KXNFLGAME` 16 events/32 markets/65,280 quotes; `KXNFLSPREAD` 16/404/824,160; `KXNFLTOTAL` 16/304/620,160; `KXNCAAFGAME` 18/36/68,640; `KXNCAAFSPREAD` 8/219/271,560; `KXNCAAFTOTAL` 8/152/188,480. `last_seen_ms` minutes old |
| Football reaches the **pricing** path | **FALSE** | Zero football rows in `recommendations`, `closing_lines`, `event_links`, `odds_snapshots`, `api_credits`. Those carry MLB and WNBA only |
| The block on moneyline is a clock, not a bug | **TRUE** | `KXNFLGAME "no sportsbook fixture within the commence-time window" n=32,662`. Bootstrap needs `commence - now <= 48h` (`timing.py:200, 1097-1111`). Earliest NFL kickoff 2026-09-10T03:20Z. **NCAAF unblocks ~2026-08-27, NFL ~2026-09-08, with no code change** |
| The NFL alias file has a production caller | **TRUE** | `backend/match/aliases/americanfootball_nfl.yaml` (5 entries) ← `load_aliases` (`linker.py:159-172`) ← `runner.link_discovered_events:692` ← `run_pricing_pass:1179` ← `run_once:1951` ← `run_loop.py:471` ← `entrypoint.sh:207` |
| Those aliases have ever resolved a name | **FALSE** | Both rejections return **before** `_bijection` is reached (`linker.py:297`). Loaded every pass, never consulted for a decision |
| **NCAAF has an alias file** | **FALSE** | Deployed `/app/backend/match/aliases` contains exactly `americanfootball_nfl.yaml`, `baseball_mlb.yaml`. Missing file → empty `TeamAliases` (`linker.py:161-163`), so NCAAF name resolution rests entirely on exact + token-prefix matching. No fixture, no test, no live link has ever exercised college team names |
| A preseason fixture exists | **TRUE, test-only** | `tests/fixtures/events_nfl_preseason.json`, captured 2026-08-09T21:23:44Z: 32 events = 16 `"Pro Football Preseason"` + 16 `"Pro Football"`. Consumed only by `tests/test_discovery.py`. Proves one series ticker carries two league strings; touches nothing downstream of `classify_series`. Re-requested today — the 16/16 split is unchanged |

**The one-line answer: NFL and NCAAF scope is half-deployed and half-fictional,
and the halves split on market type, not league.** Discovery and quote recording
are genuinely live for all six series (~2M football quote rows accumulating).
Moneyline pricing has never executed and unblocks itself on a date. Spread and
total pricing does not exist for any sport.

## The first thing that will break, and it is dated

**NCAAF enters the 48h bootstrap horizon around 2026-08-27 and will attempt to
link college team names with no alias file.** That is the first real test of
`linker.py`'s prefix matching against names like "Ole Miss" / "Mississippi",
"Miami (FL)" / "Miami Hurricanes", "USC" / "Southern California" — in
production, untested, on a date. NFL's alias file gets its first live exercise
~2026-09-08 and has never resolved a single name.

## What this does NOT establish

- ~~Nothing about whether the Odds API subscription returns the football
  fixtures.~~ **Settled 2026-08-16, at zero cost.** `GET /v4/sports` returned
  `200` with `x-requests-last: 0` — the endpoint is genuinely free, confirmed by
  the header rather than by the documentation. Of 71 sports listed,
  `americanfootball_nfl` and `americanfootball_ncaaf` are both **present and
  `active: true`**, alongside `baseball_mlb` and `basketball_wnba`. The response
  also independently corroborates the budget figures above:
  `x-requests-used: 1104`, `x-requests-remaining: 18896`.

  This establishes that the **sport** is carried. It does **not** establish that
  any particular fixture, market key, or region will be populated for a given
  slate — `/v4/sports` lists sports, not events, and checking events costs a
  credit.
- **Nothing about whether football wins a sweep slot against MLB.**
  `decide_sweeps` sorts due-first then by `games_covered` (`timing.py:502-505`)
  and `MIN_SLOT_SEPARATION_MS` is per-sport, so it should not starve — but that
  is a reading of the code, not an observation. It becomes observable on the
  first day both leagues are inside 48h.
- **Nothing about NCAAF depth on game day.** See the horizon qualification above.
- **The NFL/NCAAF slate assumptions are unverified.** No 2026 football fixture
  exists in the database. The kickoff-time distributions behind the 3.0 and 12.5
  open-hour figures are general schedule knowledge, and the 12.5 is the single
  most load-bearing input to the NCAAF number.
- **No complete post-ADR-0032 MLB day exists yet.** The 5–7 open-hour MLB figure
  is partly estimated. `credits-day --date 20260817` converts it to a
  measurement and is worth taking before acting on any monthly projection.
- **Nothing about whether the spread/total *feature* is worth building.** This
  document establishes only that it does not exist and that its inputs are
  currently bought and discarded.
