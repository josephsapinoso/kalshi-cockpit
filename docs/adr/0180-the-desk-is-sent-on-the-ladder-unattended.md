# 0180 — The desk is sent on the ladder unattended, off by default, and every card says what it knows

**Status:** Accepted on Joe's three answers, 2026-09-20 (in-session, batched). Numbered 0180 on `main` after `git fetch`, 0179 being the highest and no lane holding a DRAFT.
**Date:** 2026-09-20
**Schema:** v51 — `scout_briefings.trigger` (`'tap' | 'auto'`, `NOT NULL DEFAULT 'tap'`)
**Tickets:** story #108 under epic #83; tasks #109–#115; Joe's ceiling question #116
**Supersedes, in part:** ADR 0088's "What is deliberately NOT built" — the first bullet only
**Leaves standing:** ADR 0088's decision and its three pinned properties; ADR 0071 §2.5; ADR 0062; ADR 0038 Decision 1; ADR 0037; the package rule in `backend/agents/base.py` that no LLM output carries a number

---

## 1. What Joe asked for, and what already existed

Joe, 2026-09-20: *"i want the ability to send scouts to assess the parlay
picks, and return a informative desk evaluation. automatically done. this
should increase my win success rate and strengthen evaluation. take in
sentiment analysis and elo aggregation as well."*

The scouts exist: the scout desk (`backend/agents/scout_desk.py::convene_desk`,
ADR 0060/0069) — two staff scouts with web search, a master, a pro-bettor seat,
four metered calls — has run on live eight times, always from a tap on
`/market/[ticker]`. Parlay legs already read whatever briefing exists for their
GAME (ADR 0088, `backend/parlays.py::scouting_facts`) at zero cost. What did
not exist: a trigger that is not a tap, any card-level statement, a sentiment
category, and any input to `backend/model/elo.py`.

## 2. The arithmetic ADR 0088 rested on, re-measured

ADR 0088 declined automatic convening because five convenings a day
(`AGENT_MAX_SEARCHES_PER_DAY = 60` ÷ 12 worst-case searches per convening
binds first; 24 calls ÷ 4 = 6 binds next) cannot cover a six-card ladder. That
was arithmetic on a ceiling, not a measurement of demand. The first
measurement, taken this session over the committed loopback fetcher
(`scripts/fetch_live_route.py /api/parlays`, 2026-09-20T22:03Z):

    leg slots across the nine cards    21
    distinct fixtures                   9     (legs repeat across cards; one leg per fixture)
    fixtures with any briefing          0     (all nine `scout = absent`)
    convenings tonight would need       9  →  36 calls, up to 108 searches

So the ladder is a fixture count, not a leg count, and it is about twice
today's ceiling rather than an order of magnitude past it. **One reading is
not a rate.** Ticket #109 lands a bounded `ladder-fixtures` series so the
number Joe is asked to fund is a week's median, not one Sunday in September.

## 3. Decisions

### 3.1 The desk may be sent unattended, and it ships OFF

`backend/scout_watch.py` (ticket #112) is a background task beside
`hedge-watch`: each cycle it reads tonight's ladder the way `GET /api/parlays`
does, takes the distinct fixtures kickoff-soonest first, skips any with a
briefing younger than `SCOUT_AUTO_REFRESH_HOURS`, and convenes the same
`convene_desk` the tap does, writing `trigger = 'auto'`.

It is the first thing in this repo that can spend Anthropic money with nobody
tapping. Its money contract, every clause refusing rather than degrading:

- `SCOUT_AUTO_CONVENE_ENABLED` defaults **false** in `backend/config.py`,
  `.env.example` and `fly.live.toml`. Joe's answer: *build it off, measure
  demand first.* The flip is his (ticket #116).
- `SCOUT_AUTO_MAX_CONVENINGS_PER_DAY` (3) is counted from the new `trigger`
  column per budget day and sits **inside** the shared `AGENT_MAX_*`
  ceilings, never additive to them.
- `SCOUT_AUTO_RESERVE_TAP_CONVENINGS` (2): the watcher refuses when one more
  convening would leave fewer than this affordable for Joe's own taps.
- When Joe raises the ceilings, **all three move together** (searches, calls,
  tokens) or none does — raising one alone buys exactly one convening before
  the next binds, which is the two-limits-on-one-quantity shape this repo
  keeps paying for (`partner.md`, "watch for two limits on one quantity").
- `tests/test_has_callers.py::BILLED_PATH_CALL_SITES` does **not** gain
  `backend/scout_watch.py`, and the reason is recorded on the router's
  entry: the watcher names neither `build_client` nor `structured_call`,
  so every call it causes goes out through `routers/scout.py`'s one
  `build_client(config)` and `convene_desk`'s reservations -- the two
  modules already allowlisted, the same meter. (This bullet said the entry
  would be added until the merge of #112 found the scanner had nothing in
  the module to allowlist.)

ADR 0088's three pinned properties stand unchanged: the join is by game, the
six states stay six (an auto convening that is refused writes `refused`, and
a fixture nobody reached stays `absent`), and a gap is a flag. Its other two
"not built" bullets stand too: **no automatic gating or dropping** — a leg is
never removed for a scout flag, Joe reads it — and **no per-leg send-the-desk
button**, because one card could eat the day.

### 3.2 The "desk evaluation" is two layers, and the cheap one ships first

Layer one (ticket #110, zero credits): every card carries a deterministic
`scouting` block — how many of its games the desk has looked at, which are
dark, the oldest briefing's age, the flag categories — rendered in words above
the legs. This is the honest evaluation while coverage is partial, and it is
the copy that must ship with the condition it names (CLAUDE.md: a screen that
names a condition to wait for is falsified by fixing the condition). Counts
are deterministic code and are allowed; nothing in the block derives from a
price and nothing in it may order a card (ADR 0071 §2.5, pinned by a source
assertion in ADR 0088's pattern).

Layer two, deferred and not ticketed: a fifth strings-only seat that reads
the legs' briefings and writes a card-level synthesis. It is not commissioned
until #109 and #112 have landed, because a synthesis over empty briefings is
a paid "I don't know".

### 3.3 Sentiment is a seventh board tile, words only — Joe chose splits over lean

Joe's answer: **betting splits and line movement**, not public/press lean.
Ticket #113 adds `sentiment` to `ScoutFinding.category` and
`BoardTile.category`, one bullet to the staff scout's brief, one tile to the
master's board, and one sentence to the pro seat (splits are usually already
in the price; say which filed items plausibly are not). It rides the existing
staff call: no new metered call, no change to
`STAFF_PAIR_SEARCHES_WORST_CASE`. A reported "72% of tickets" is a fact about
bettors and is filed in words; the schema keeps its no-numeric-leaf property
(`TestNoNumberCanLeaveTheDesk`). No score, no new feed.

### 3.4 Elo goes to a measurement, and nothing reaches a card until it passes

Joe's answer: **free measurement first.** `backend/model/elo.py` fits on
win/loss alone (`use_margin_of_victory` is a `LeagueConfig` toggle,
`elo.py:69, 203-204`), and the box already holds `kalshi_markets.result`,
Kalshi's own close in `closing_lines`, and team names in `odds_fixtures` — so
an Elo-vs-price look costs no credits and needs no feed. Ticket #115: the
`pre-registrar` fixes the look on ADR 0038 §4's template (compare to the
PRICE, not the outcome; decision rule `sd(model − ask) > sigma_model`), it runs
as a `scripts/measure_*.py`, `measurement-skeptic` audits it. No
`model_probability` is written; no number reaches a card; blending anything
into `fair_probability` would be its own ADR (CLAUDE.md). This is the
ADR 0038 Decision 1 procedure followed, not skipped: the row it would
overturn is "in-house model vs Kalshi's price" and the measurement is named
before it is taken.

### 3.5 Win rate is not promised, and the question is made askable

The record has about thirteen orders (a count that decays on sight, ADR
0162). No measurement of "scouted picks win more" can speak at that n, none
is registered, and the screen says nothing of the kind. Ticket #114 records
each leg's scout state at bet time on the position row so that, if the count
ever supports it, the question can be registered rather than re-derived.

## 4. What this does not establish

- That a briefing changes a bet, or that a changed bet does better. ADR 0106
  §6 said this and it is still true.
- What any convening costs in dollars. ADR 0062 §4 closed the invoice
  question and it is not reopened; the reliable quantities are counts.
- The nightly fixture count as a rate. One reading of nine.
- That the sentiment tile is worth its searches. It spends none of its own,
  which is why it was cheap to try; whether it changes what the master says
  is unmeasured.

## 5. Consequences

- `scout_briefings.trigger` is a permanent column; every pre-v51 row is a
  tap, which is the truth about it.
- ADR 0088's first "not built" bullet is superseded by §3.1 and the ADR
  gains a pointer to this one; its decision and tests are untouched.
- `fly.live.toml` carries `SCOUT_AUTO_CONVENE_ENABLED = "false"` explicitly,
  for the reason `AGENT_MODEL` is explicit: an unset money-bearing value is
  how this instance once spent at a rate nobody chose.
- Question for Joe: how much unattended scouting to pay for each day, with
  the three ceilings moving together — #116, to be answered after the
  `ladder-fixtures` series exists.
