# Ticket #12 research packet — which sports, and do props survive October

Written 2026-09-02 for Joe to answer map #3's ticket #12 in two minutes. **The
decision is his**; this packet is the facts and the consequences of each
answer. Every figure cites a file:line or the command it came from. Anything
not measured is marked **UNMEASURED**, never estimated. Nothing here was read
off the live instance — this was written in a worktree; §2 gives main the exact
commands to run. No existing `docs/` location holds research packets
(`docs/` had `adr`, `agents`, `measurements`, `reviews`, `runbooks`), so
`docs/decisions/` is new.

## 0. The answer sheet (read this first)

| Joe's answer | What it does to the map |
|---|---|
| **"Drop props"** | #23's design half dies (its bug half stays — §4). #15 loses one filter axis, #18 loses "possibly a props view". Nothing new is built. The five MLB series keep pricing until Sept 27 and then go quiet on their own. |
| **"Baseball props only"** | Status quo. Everything prop-shaped on the map carries a **Sept 27 / Oct 31 expiry** and must ship before it or wait for April. Winter has no props. |
| **"Add football (or basketball) props"** | New build tickets not on the map (§4.3). #23, #15 and #18 become load-bearing. The `combos.py` calendar caveat must be closed with one read-only capture (§5). Each prop tap costs 4 + 2×(number of Odds API keys chosen) credits from a 150/day reserve (§3). |

**One premise in the ticket is wrong and one is unsourced** — see §7.

## 1. What the tool can price today

**Every prop series is baseball.** `backend/kalshi/props.py:69-75`:

```
PROP_SERIES = {"KXMLBKS": "pitcher_strikeouts", "KXMLBTB": "batter_total_bases",
               "KXMLBHIT": "batter_hits", "KXMLBHR": "batter_home_runs",
               "KXMLBRBI": "batter_rbis"}
```

The Odds API side is the same five keys and nothing else: `PROP_BASE_MARKETS`
at `backend/odds/client.py:128-134`. A prop market only becomes
`market_type = "prop"` through `PROP_SERIES.get(event.series_ticker)`
(`backend/runner.py:1555`), and the prop fetch returns 0 with a `SKIPPED`
sweep-log row reading *"no prop series discovered for {sport_key}"* when a
sport has none (`backend/runner.py:2530-2547`). So a football prop tap today
buys the 4-credit team lines and buys no props.

**Non-baseball prop series in the code: none.** `grep -rn -E "KXNFL|KXNBA|KXNCAAF|KXWNBA" backend/`
hits only game/spread/total series, `estimates.py:59-65`'s sport-prefix map
and comments. **But Kalshi lists them**, and this repo has already captured
them as combo legs (`grep -o -h -E '"KX(NFL|WNBA)[A-Z0-9]*-' tests/fixtures/*.json docs/measurements/*.json | sort | uniq -c`):
`KXWNBAPTS` 101, `KXWNBAREB` 52, `KXWNBA3PT` 21, `KXWNBAAST` 6,
`KXNFLPASSYDS` / `KXNFLRSHYDS` / `KXNFLRECYDS` / `KXNFLREC` / `KXNFLANYTD` /
`KXNFLFIRSTTD` / `KXNFL2TD` 4 each — all from the 2026-08-09 combo captures.
Their `yes_sub_title` shape, `floor_strike` identity and player-name collision
rate are **UNMEASURED**; `props.py:20-35` proves those only on MLB.

**Season ends (external sources, not repo measurements):**

- MLB regular season last day **Sun Sept 27, 2026**; Wild Card Sept 29–Oct 1;
  World Series Game 1 **Oct 23**, Game 7 (if needed) **Oct 31**.
  Sources: [mlb.com postseason schedule](https://www.mlb.com/news/2026-mlb-playoff-and-world-series-schedule),
  [CBS Sports](https://www.cbssports.com/mlb/news/2026-mlb-playoff-schedule-bracket/).
  Whether the five `KXMLB*` prop ladders are listed in the postseason is
  **UNMEASURED** (the record has never spanned one).
- WNBA regular season last day **Sept 24**; first round **Sept 27**; Finals
  **Oct 17–Oct 31**. Source: [wnba.com/keydates](https://www.wnba.com/keydates).
  The tool prices no WNBA props (§1 above).

## 2. What his record shows he bets — commands for main

No `inspect_live_db.py` query summarises **by sport or league**. The closest is
`manual-orders-audit` (`scripts/inspect_live_db.py:5105-5117`), whose
rows-per-ticker section (`_SQL_MANUAL_TICKERS`, `:629-635`) groups by full
ticker — the series prefix before the first hyphen *is* the sport, so it can be
read off by eye. Run these first (read-only, whitelisted):

```
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py manual-orders-audit"
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py parlay-lookups-tail -n 50"
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py combo-bids-tail -n 50"
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py prop-bookmakers"
```

For a real by-sport census, main needs SQL the script does not carry. Run it
from an interactive `flyctl ssh console -a kalshi-cockpit`, then `python -`
with a heredoc, opening **read-only** so it cannot hold a lock against the
runner (`sqlite3.connect("file:/data/cockpit.db?mode=ro", uri=True)`;
`DEFAULT_DB` is `/data/cockpit.db`, `inspect_live_db.py:122`). Do **not**
invent counts — paste the output.

```sql
-- Hand bets by series (manual_orders, schema.sql:1604-1631). KXMVE = combo.
SELECT substr(ticker,1,instr(ticker,'-')-1) AS series, COUNT(*) AS n,
       SUM(dry_run=0) AS real_orders, MIN(submitted_ms), MAX(submitted_ms)
FROM manual_orders GROUP BY 1 ORDER BY n DESC;
-- Combo legs by series (parlay_lookups.selected_legs is a JSON array of
-- {event_ticker, market_ticker}, schema.sql:1149-1151).
SELECT substr(json_extract(j.value,'$.event_ticker'),1,
              instr(json_extract(j.value,'$.event_ticker'),'-')-1) AS series,
       COUNT(*) AS legs, COUNT(DISTINCT l.id) AS taps
FROM parlay_lookups l, json_each(l.selected_legs) j GROUP BY 1 ORDER BY legs DESC;
-- Held tickets by league (parlay_position_legs.league, schema.sql:1904).
SELECT league, COUNT(*) FROM parlay_position_legs GROUP BY 1;
-- Venue fills: same substr() over the fills table (DDL backend/store/db.py:350-365;
-- confirm the live table name in sqlite_master first).
-- Prop taps ever bought: trigger='manual' is a tap (timing.py:344); the props
-- half carries the batter_/pitcher_ keys in `markets` (budget.py:276-285).
SELECT sport_key, COUNT(*) AS taps, SUM(cost) AS credits,
       SUM(markets LIKE '%batter_%' OR markets LIKE '%pitcher_%') AS prop_taps
FROM api_credits WHERE trigger='manual' GROUP BY 1;
```

**One figure already on the record:** #5's resolution re-pulled `credits-day`
for 20260823–20260827 and found manual spend of **8, 4, 8, 8** credits on
the first four days (`gh api repos/josephsapinoso/kalshi-cockpit/issues/5/comments`).
At 4 per team tap and 14 per prop tap, 8 is two team taps and **no prop tap
divides into any of those days**. Four days is not a habit; the SQL above is
the measurement.

## 3. The per-tap credit cost, from the code

The vendor charges `markets × regions` per call (`backend/odds/budget.py:66-68`).
Live sets `ODDS_MARKETS = "h2h,spreads"` (`fly.live.toml:457`) and
`ODDS_REGIONS = "us,eu"` (`:408`), so a team tap is **4**. A prop tap adds one
fixture's props at `len(prop_market_keys()) × regions` = 5 × 2 = **10**
(`client.py:140-181`; `_alternate` keys off since ADR 0079), total **14** —
pinned by `tests/test_odds.py:744-752` via `manual_cost`
(`backend/odds/ondemand.py:174-188`). #5 confirmed the deployed env equals the
repo.

**Which ceiling a tap draws on — and it is not the 300 attention slice.** Taps
are charged to `DEFAULT_MANUAL_DAILY_CREDITS = 150` (`ondemand.py:107`) — a
code default; `grep -n 150 fly.live.toml` returns nothing, so the
`fly.live.toml:222` cited at `ondemand.py:79` is stale — with a 120 s cooldown
(`ondemand.py:75`). The ≤300/day slice (`ODDS_ATTENTION_DAILY_CREDITS`,
`fly.live.toml:326`, default `timing.py:1027`) is the page-open heartbeat,
trigger `attention`, and it never pays for a tap. Both sit inside
`ODDS_DAILY_CREDIT_BUDGET = 700` (`fly.live.toml:246`).

| sport (Odds API key, `discovery.py:235-242`) | markets requested per tap | credits/tap | taps/day the 150 reserve affords |
|---|---|---|---|
| any in-scope sport, team lines only | h2h, spreads × us, eu | 4 | 37 |
| baseball_mlb, one fixture's props | + 5 `PROP_BASE_MARKETS` × us, eu | 14 | 10 |
| americanfootball_nfl / ncaaf props | no keys defined — **UNMEASURED**; 4 + 2×k for k keys chosen | — | 150 ÷ (4 + 2k) |
| basketball_wnba / nba props | same | — | same |

Zero grep hits for any football or basketball Odds API prop key
(`player_pass_yds`, `player_rush_yds`, `player_points`, …) anywhere in
`backend/`, `docs/`, `.env.example` — the vendor's key set for those sports has
never been read into this repo. Whether an EU book quotes them at all is what
`prop-bookmakers` answers (`inspect_live_db.py:5082-5090`); for MLB, no sharp
book does (`props.py:42-44`).

**The ticket's "12–14" figure:** 14 is correct; 12 has no source in the code.
`backend/api/routes.py:284-287` still says a fixture "turns a 6-credit tap into
a 26-credit one" — stale twice over (ADR 0071 §4 corrected it to 24; ADR 0079
made it 14). Not a decision item; a one-line docstring fix for main.

## 4. Which map tickets die or change under each answer

Open sub-issues of #3 (`gh api repos/josephsapinoso/kalshi-cockpit/issues/3/sub_issues --paginate`,
2026-09-02): #12, #15, #16, #17, #18, #19, #20, #21, #23, #24, #25.

### 4.1 "Drop props"

- **#23 — deleted as a design question, kept as a bug.** Its text: *"Settle:
  should props appear in the likely-winners list at all, appear labelled as
  props, or be excluded and given their own surface? The answer depends on …
  whether props survive October (#12)."* Dropping props answers it: exclude.
  But the bug it names survives the answer — *"Nothing excludes player props.
  So a prop can be selected as the representative row for a game and
  presented as the game's likely winner"* (`routes.py:1387-1443` as #23 cited
  it on 2026-08-28; lines have drifted since) — because
  the five MLB ladders keep being discovered until Sept 27 whether or not
  anyone wants them. That exclusion is a task, not a grilling.
- **#15 — narrowed.** Loses the axis *"by market type once props are
  labelled"* and the framing *"filter picks, props, parlays"* becomes two
  things.
- **#18 — narrowed.** Loses *"and possibly a props view"* from the list of
  things competing for the six-link budget.
- **#16, #17, #19, #20, #21, #24, #25 — unchanged.**

### 4.2 "Baseball props only"

Nothing is deleted; everything prop-shaped gains an expiry. #23's answer must
ship before **Sept 27** to be seen this year (Oct 31 at the outside, and
postseason listing is UNMEASURED). #15's market-type filter and #18's props
view are seasonal features built in the last month of the season. From October
to April the prop filter shows nothing, so #20 (*"the empty night"*) must
distinguish "no props this season" from "no props tonight".

### 4.3 "Add football props" (or basketball)

- **#23 — load-bearing.** Its label finding gets worse: `yes_side_team`
  holds `"<player>: 1+"` verbatim from `yes_sub_title` (#23's citation
  `runner.py:3031,3041`; the write now sits near `runner.py:3322`, which also
  carries a `player_name` column #7 added) and the screens write *team*
  sentences around it. A yards ladder makes that
  string `"<player>: 250+"` under a heading about who wins.
- **#15 — load-bearing.** The by-market-type filter stops being optional once
  a Sunday slate mixes 13 games with hundreds of prop rungs.
- **#18 — load-bearing.** "Possibly a props view" becomes a real nav claim.
- **#5's supply problem returns** (closed, but its finding stands): the
  attention slice saturated at 72 credits/hour with three sports on a
  10-minute cadence; a fourth sport at 4 credits raises the burn.
- **New build tickets, none on the map:** `PROP_SERIES` entries per NFL
  series and their Odds API keys; re-prove the `floor_strike == outcome_point`
  join (`props.py:20-30`, MLB-only) and the `N+` subtitle regex
  (`props.py:99`) on football ladders; collision rule for names
  (`props.py:32-35` relies on uniqueness *within an MLB slate*); a
  `prop-rungs`-style capture before any of it is trusted.
- **§5 becomes load-bearing.**

## 5. The combos calendar caveat

`backend/kalshi/combos.py:36-41`, verbatim:

> At capture time **zero of the 13,806 legs had an active quoter**, and every
> pre-generated combo market showed zero volume and zero open interest. That is
> a real observation and it is also nearly uninformative: the capture ran on
> 6 August 2026, with the NBA season finished and the NFL in preseason. It
> measures the calendar at least as much as the product. Whether these quote on
> a Sunday in November is unmeasured, and this module does not pretend otherwise.

The verdict string at `combos.py:336-341` repeats it: *"out of season it
measures the calendar, not the product. Re-run in season before concluding
anything."*

**What a football-props answer requires to close it:** one read-only capture on
an NFL game day. Two scripts, both free of Odds API credits: `python -m
scripts.demo_combos --live` walks the real catalogue and prints that verdict
(`scripts/demo_combos.py:3-6`, "still read-only; no lookup, no market
created"); `scripts/measure_combo_book_presence.py --max-books 25 --json
docs/measurements/<date>-combo-book-presence-nfl.json` reads the books
unauthenticated (`:5-9`). Note the repo already minted NFL legs in preseason —
the 2026-08-23 capture posted them to `KXMVESPORTSMULTIGAMEEXTENDED-R` and
Kalshi accepted (`backend/store/schema.sql:1165-1166`) — so the open question
is *quoting*, not *existence*.

**Not an in-season effect, per the record:** CLAUDE.md and
`docs/measurements/2026-08-18-combo-book-presence-inseason-result.md:26-31`
record the 2026-08-18 run (2 of 11 with a book) against the 2026-08-09 runs
at Fisher two-sided **p = 1.0**, 78% tennis, effective n ≈ 2. The caveat is
about NBA/NFL specifically and stays open until a football-season capture.

## 6. The questions for Joe

1. **Which sports do you actually bet, in order?** Options: MLB / NFL / NCAAF
   / NBA / WNBA / NHL (the six in `IN_SCOPE_LEAGUES`, `discovery.py:235-242`)
   / something else. → Sets the attention-slice burn (4 credits per sport per
   10 min while a page is open) and which of §4's branches applies. Main will
   attach what `manual_orders` says you have bet so far (§2).
2. **Do you bet player props, and for which of those sports?** Options: *no,
   drop them* (§4.1) / *baseball only* (§4.2, expires Sept 27) / *yes, add
   football or basketball* (§4.3, new build, §5 capture). → Decides whether
   #23 is a bug fix or a feature, and whether #15/#18 grow a props axis.
3. **Is 14 credits a prop tap worth it to you — ten a day from the 150
   reserve, or 37 team-only taps?** Options: *yes as-is* / *only if cheaper*
   (drop to one region, `ODDS_REGIONS`, halves it: 2 + 5 = 7; EU books quote
   no MLB props — `prop-bookmakers` tells us whether that costs anything) /
   *I never tap for props*. → If "never", the 150 reserve can shrink toward
   the attention slice #5 found saturating.
4. **Why did you stop opening the desk?** Options: *stale prices when I look*
   (#5, #20) / *nothing there worth betting* (#20) / *I know my game and it
   won't show me a price* (#24) / *I bet elsewhere now*. → Reorders the map
   above any of the three prop answers.
   **The usage figures, read from live 2026-09-02 ~19:30Z** — `api_credits`
   rows with `trigger = 'attention'` per budget day (`inspect_live_db.py
   credits-day --date YYYYMMDD`, budget day starts 10:00Z), i.e. ten-minute
   buys made only while a page was open and visible:

       20260827   75   (the slice spent, 4.88 h — CLAUDE.md's measured day)
       20260829   10
       20260830   20
       20260831    6
       20260901    6
       20260902    5   (partial, to ~19:30Z)

   `manual-orders-audit`: **0 rows lifetime** on `manual_orders` — the hand-bet
   path armed 2026-08-26 has never sent an order. `parlay_lookups` was not
   read. The partner's reading of the same figures, 2026-09-02: a ~15-fold
   fall in five days on the thinnest sports week of the year; the seasonal
   confound (fewer upcoming sports → fewer attention rows per visit) is real
   and does not plausibly cover a factor of fifteen, and the 2026-08-29
   fall-through change cannot bite at 5 rows/day because the slice is nowhere
   near spent. **Five days is one observation, not a rate**, and the
   `fly.live.toml` "0 B/day" lesson applies: a window shorter than the
   phenomenon's period reads zero and looks like a measurement.

## 7. What contradicts the ticket's premise

- **"Against a daily ceiling that may already be binding."** The ceiling that
  bound on 2026-08-27 was the *attention* slice (300), not the tap reserve
  (150), and taps are not charged to it (§3). #5 found manual spend of 4–8
  credits a day — the tap reserve was under 6% used on every day measured.
- **"Roughly 12–14 odds credits."** 14, from `tests/test_odds.py:744-752`.
  No path to 12 exists in the code.
- **"Each sport is setup work."** Understated for props: it is a re-proof of
  two identities measured only on MLB (`props.py:20-35`), plus vendor keys
  this repo has never read. For team lines it is zero work — every in-scope
  sport already prices at 4 a tap.
- **"Baseball ends in roughly five weeks."** The regular season ends Sept 27;
  the World Series runs to Oct 31. Whether the prop ladders are listed in
  October is UNMEASURED, so "five weeks" and "nine weeks" are both defensible.
