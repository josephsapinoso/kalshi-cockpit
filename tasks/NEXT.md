# Next — your checklist

**How this file works.** This file holds the **current state**: the latest
session entry, plus what is still open. Every earlier session entry is in
`tasks/archive/next-YYYY-MM-DD.md`, **verbatim** — the archive reconstructs
the pre-split file byte for byte. The index at the bottom lists every entry
and which file it is in.

**Split at ~90% of 262,144 bytes, and read `wc -c` BEFORE writing an entry,**
**not after.** `tests/test_session_files_are_readable.py` guards the file; what
breaks first is the instruction to read it, because a session that cannot
read the whole file reads the head and silently believes it has the state.
Cut on a date boundary, name the archive for the split date, move the index
lines in the same edit (a split without them is a data loss with a table of
contents), and verify by md5. The seven splits so far and what each taught:
`tasks/archive/next-split-log.md`.

---

## SESSION START — if Joe said "read NEXT.md", this box is your prompt

Repo: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`,
branch `main`. Check `git status` and `git log origin/main..main` rather than
trusting any sentence here, and read the LIVE instance's `/api/health` for its
`git_sha` — it sits under `build`, not at the top level. The calibration study
is STOPPED (2026-08-20, Amendment 2; the recorder machinery still runs). Joe is
a beginner and has asked to be educated: define every betting/stats term at
first use, via `frontend/src/lib/glossary.ts` and `<Term>`.

**The test count is CI's, not a hand-collected number.** `.github/workflows/ci.yml`
runs `ruff check .` and `python -m pytest -q` on every push, under a 15-minute
cap. Read the last green run: `gh run list --limit 5`. Run targeted tests
locally while you work; let CI collect the total. If you must take a count, do
not reconcile a baseline by reasoning about a delta — collect both trees. The
suite is ~15-22 minutes and growing with the record; a slow run is not a hung
one.

**READ THE DEPENDENCY ALERTS AT SESSION START — new 2026-09-09, ADR 0117.**
They were on none of the three queues, and two critical unauthenticated RCEs
sat on the public money box until a routine push happened to trigger a rescan:

    gh api repos/josephsapinoso/kalshi-cockpit/dependabot/alerts?state=open \
      --jq '.[] | [.number,.security_advisory.severity,.dependency.package.name] | @tsv'

**Do not read the alert summary git prints on push.** It is a snapshot taken
*before* the rescan that push triggers, so it describes the previous state.
Mine said "1 high" while the truth a second later was two criticals and a
high. And **do not trust an alert's own `state`**: alert #15 reports `fixed`
while `requirements.txt:9` still pins a version inside its vulnerable range,
because GitHub's dependency graph lost the package's resolved version.
**This query is therefore known-incomplete — it cannot see `cryptography` at
all.** Verify a fix by reading the version out of the running container, and
see open item 3 below.

**Two things to know before planning. CLAUDE.md is current on both:**

1. **The signal test has NOT declared.** The verdict is UNRESOLVED at
   `G = 216`, the floor is 713, the look is not coming, and every interval sits
   entirely below the 0.40 threshold — settled negative for planning.
2. **What the tool is FOR is settled — ADR 0071.** A personal betting desk
   first; price transparency as the job; a gap you may show on a row and
   never rank by; sharing means someone runs their own copy. Do not re-derive
   the purpose.

**Other lanes may be running; main is not the whole picture.** Read the
generated board, never a hand-typed lane table:

    git worktree list
    .venv\Scripts\python.exe scripts/lane_board.py

It reads every worktree and local branch — ahead/behind, uncommitted work, ADR
and schema claims, overlapping hunks. `tasks/LANES.md` carries the last written
snapshot plus the **allocation ledger**: what a live lane has said it will take
before it exists on disk. **Do not claim an ADR number or schema version by
reading either one** — write `docs/adr/DRAFT-<slug>.md` with no ordinal and
take the number in the merge commit after `git fetch`; the guard refuses a
`DRAFT-` file on `main`. Full rule: `docs/adr/README.md`. `docs/adr/0006-*`
sharing a number is deliberate, not a collision.

**The UI decisions live on GitHub, not here.** Map issue **#3 "Cockpit for the
pilot"** on `josephsapinoso/kalshi-cockpit` holds every screen decision Joe has
made, with evidence; a session that plans UI from this file alone will
re-derive them. Read the map body, then the frontier (open, unblocked `0`,
unassigned `-`, first in map order wins):

    gh issue view 3 --json body --jq .body
    gh api repos/josephsapinoso/kalshi-cockpit/issues/3/sub_issues --paginate \
      --jq '.[] | select(.state=="open") | [.number,(.assignee.login // "-"),(.issue_dependencies_summary.blocked_by // 0),.title] | @tsv'

Conventions: `docs/agents/issue-tracker.md`. Claim a ticket by assigning it to
yourself before any work; resolve one per session. The map produces
*decisions*, not builds. **The `/wayfinder` skill that drew the map is not
installed in this plugin version** — nothing can invoke it, and the map is
read with `gh` only.

**THIS FILE IS THE FRONT DOOR — Joe's answer, 2026-08-28.** Three queues: this
file's Open list (repo and infrastructure work), the map's open tickets
(decisions to make), and **decided-not-yet-built** — a closed ticket carrying a
spec is a NEXT.md item, and it belongs to nobody unless it is written here.
Read `git status`, then the Open list in the latest entry, then the frontier
query, in that order.

**THEN INVOKE THE `partner` AGENT, BEFORE PLANNING ANYTHING** — CLAUDE.md
workflow step 0. Hand it the state (what is open, what landed, what is blocked)
and ask for a ranked list AND which items can run as parallel lanes. Skip it
only for a single errand Joe named himself.

Read `CLAUDE.md`, then the latest entry below (it is the whole brief), then
`tasks/lessons.md` top two. Re-verify state, never inherit it:

    .venv\Scripts\python.exe -m pytest -q     (NEVER bare python; PATH is 3.14)
    cd frontend && npx tsc --noEmit

Expected: CI's count, ruff clean, tsc clean, `next build` green. Check
`/api/health` `git_sha` against `origin/main` before assuming anything is
live. The terminal spread/total look was **VETOED by Joe 2026-08-21 16:11Z**
(`docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`) —
nothing fires at 22:40Z. **The H4 look series is CLOSED — BLOCKED ON
INSTRUMENT, 2026-08-21** — do not build the A9–A12 analyzer and do not re-run
the channel diagnostic (A17.6/A17.11).

## 2026-09-15 (nineteenth session) — the NFL chip was a 25 s walk of the wrong index, an Under leg was printing the Over's price, and the venue mints a three-NO-leg combo

Joe's report, in his words: *"i saw a 3-leg parlay for unders, but only
saw that they were mlb games. I could not see the team names. I also
tried buying it, but ran into an error that said that i was unable to do
so because no one was selling it (an old bug). ... I went to the games
tab, and only saw MLB games. I also only saw an option to buy mlb props.
when I selected NFL games, I got a backend error."* Three errands he
named himself, so no partner pass. Chrome's extension was not connected;
everything below was read off live through the session cookie
(`GET` only) and `inspect_live_db.py`, zero odds credits.

**What each one was.**

1. **NFL chip → "Backend unreachable."** Not a Python error and not a
   422: `read-incidents` held six `read_budget` rows, 12:16–12:21Z, every
   one `GET /api/slate?league=americanfootball_nfl` at 25,00x ms. The
   league cut was `EXISTS (... o.odds_event_id = l.odds_event_id AND
   o.sport_key = ?)`. `sport_key` is in no index that leads with
   `odds_event_id`, so SQLite took `idx_odds_sport_commence (sport_key=?)`
   and walked the whole NFL slice of `odds_snapshots` once per
   NON-matching window row (~350, mostly MLB), in both statements. The MLB
   chip was fast because most rows match on the first probe. The route's
   docstring said "an indexed SEARCH on `odds_event_id`" — the plan does
   say SEARCH; the v39 lesson again (method, not rows). Latent since
   ticket #15; f8d2e02 did not touch it. **"Only MLB games" is the same
   fault:** NFL rows are in the window (the cut returns DET@BUF) but sit
   below the 100-row cap, and the cut built to reach them was the thing
   timing out.
2. **Totals legs with no teams.** A total's label is Kalshi's subtitle
   ("Under 8.5 runs scored"); `event_title` ("Baltimore vs New York
   Mets: Total") has been on every leg of the wire since ADR 0051 and was
   drawn nowhere on the parlay path — four renderers print `leg.label`
   alone. Props have the same gap (a player, no game).
3. **"No one is selling."** Not the 2026-09-08 copy bug. `parlay_lookups`
   76 (12:12:59Z, card `totals`, three `side: "no"` `KXMLBTOTAL` legs):
   status `book_empty`, Kalshi **minted**
   `KXMVECROSSCATEGORY-SHARD1-S2026F28F6402132-D586AC0CA93`, book
   `yes_bid=none yes_levels=0 no_levels=0`. The only producer of that
   sentence is `ask_tenths is None` on the minted market's book. **So the
   venue accepts a three-NO-leg totals combination** (first-read #4 of
   the eighteenth entry, answered on the accept side, n = 1); whether a
   fresh NO-leg combo gets a resting NO bid is the half one tap cannot
   settle — the YES-leg taps in the five minutes before it that the read
   could see (72 lottery, 73 longshot, the two-spread card) all came back
   `priced`; one of the five rows was truncated in the read and is not
   counted. Recorded on #38. Asking again costs nothing and mints nothing.
4. **No NFL props tap.** `/api/odds/refreshable` lists only sports with a
   fixture inside a hard 24 h horizon (`routers/odds.py:58`). First NFL
   kickoff on record is DET@BUF 2026-09-18 00:15Z (Thu 17 Sep 20:15 ET),
   so NFL enters the tap list **Wed 16 Sep 20:15 ET**. Design, not a
   defect; left alone (odds bought days early are stale at the 15-min
   limit anyway). **Joe raised it again 2026-09-15 ~18:30Z** with the NFL
   chip selected and the card still listing only MLB props, and asked
   for the card to follow the chip: `c4db0f0`, live. The horizon is
   unchanged; the card now cuts to the chip's league and, when that
   league has nothing inside 24 h while others do, says so and links to
   every league (`lib/refreshableCut.ts`, node-tested). The Board has no
   bar and lists every league as before.

**Found beside them, and the one that mattered most:** `leg_facts` was
keyed by ticker and hardcoded `ask_for_side(quote, "yes")` /
`no_bid_qty`, so an Under leg's `ask_display`, `depth_at_ask`,
`ask_probability` and the trust depth input were the **Over side's** —
the wrong price on the screen whose job is price transparency (ADR
0071). Shipped in the same change as the Under legs (f8d2e02) and never
seen, because the first totals card was also the first time anyone
looked.

**Built — `2d8de82`, every guard seen red once (mutation in each test's
docstring):**

- `_slate_filter_sql`'s league predicate is `(SELECT o.sport_key FROM
  odds_snapshots o WHERE o.odds_event_id = l.odds_event_id ORDER BY
  o.commence_ms LIMIT 1) = ?` — one entry of `idx_odds_event_commence`
  per row, whichever league. `tests/test_slate_league_cut_is_bounded.py`
  pins the index AND the bound and documents the old plan;
  `test_list_filters.py` gains the exact case (in-scope league, zero
  rows, 200 not 503), and the "orders nothing" guard cuts the bounded
  read out by its exact text before checking. Live-shaped throwaway DB
  (800 fixtures × 1,400 rows, 350 window rows), best of three, warm,
  local — a floor on the live win, not an estimate:

      americanfootball_nfl   old EXISTS   73.1 ms     new   0.5 ms
      baseball_mlb           old EXISTS   12.8 ms     new   0.6 ms

- `_NO_FACTS` carries both sides (flat `no_ask_*` keys, not a nested
  dict — `dict(_NO_FACTS)` is a shallow copy and `scout_flags` already
  paid for that once); `_ask_facts_for_side(facts, leg.side)` picks, and
  refuses a third value rather than defaulting to YES.
  `tests/test_under_legs.py::TestAnUnderLegQuotesTheUnderSide`.
- `LegGame` draws `event_title` (suffix `: Total` stripped) under the
  label of a team-less leg in all four leg renderers of
  `ParlayCards.tsx`; `tests/test_parlay_cards_show_the_game.py` is a
  source scan (no component harness in `frontend/`). `leg_details_for`
  carries `event_title` into the lookup blob. **`parlay_position_legs`
  has no column for it**, so `/hedge` still prints a recorded total's
  label alone — a schema step, its own item below.
- Lesson: `tasks/lessons.md` 2026-09-15 (fourth) — EXISTS does not
  short-circuit for the rows that fail it; asymmetric latency on one
  parameter is the tell; read `read-incidents` before the screen.

**STATE at close.** Deployed twice: `747c4f6` (~14:15Z) then `12aaaf6` (~14:33Z, the `: Total Runs` suffix); `/api/health` reads `12aaaf68…`, no migration (v42). CI 34979713549 and 34981144720 green; 34978416813 was red on one blob-shape test 2d8de82 had not run locally, fixed in 747c4f6. Live reads after each deploy, zero odds credits: the NFL cut answered 200 in 15.9 s on the first read after the restart (cold page cache, still under the 25 s budget) and 0.8–0.9 s warm, 67–71 rows, `hidden` 181; the MLB cut 1.3 s; `read-incidents` unchanged at the six pre-fix rows. The totals card built at ~14:20Z with `event_title` on every leg ("Baltimore vs New York M: Total Runs") and its Under legs quoting 54c/55c with their own depth; by 14:35Z the consensus was past 15 min again and the card empty, so **the rendered game line was not seen on live** — the strip was exercised on the live title locally and the next fresh slate is the look. **Then, on Joe's word ("add the hedge schema column so totals parlays name the game"): ADR 0153, schema v43** — `parlay_position_legs.event_title`, written from the lookup blob, served by `/api/hedge`, drawn under the label on `/hedge`; NULL prints as nothing. Committed `f220f65`, CI 34983740120 green, deployed ~14:56Z; `/api/health` reads `f220f650…`, `/api/hedge` 200 with `event_title: null` on every served leg (all predate the column). Four guards seen red once (ADR 0153 §4). **Read off live in the same pass, `manual-orders-audit`: `manual_orders` has 13 rows, 13 real, 12 `filled`, 1 `unfilled`, last submitted 2026-09-15T12:12:47Z** — CLAUDE.md's "7 rows" was read 2026-09-14 and six real orders have landed since, the first rows ever to carry ADR 0143's venue columns. **Then, on Joe's word, the registered census was taken — the one look A8 allows, spent 2026-09-15T15:42:38Z** through `scripts/census_recorded_fill_vs_venue.py` (committed `b3fc100`, CI 34988981124 green, deployed and invoked by path; the legal form §0.2(b) names). Result: `docs/measurements/2026-09-15-recorded-fill-vs-venue-charge-census-result.md`. 13 rows, all S1 (KXMVE), S2 empty; `n_joined` 12 (all `fills`-sourced), `unjoined_unknown` 1, refusal branch not fired; `n_comparable` 12, `n_equal` 11, `n_sent_above` 1, **`n_sent_below` 0 — H1 stands**, A7.3 opens nothing; six rows carry both endpoints, 0 disagree within the 1-tenth tolerance (all single-fill YES rows, so not corroboration of either reader), A7.4 opens nothing; every order YES so A4.3 was never exercised; `max_abs_sent_minus_venue_tenths` 22 on one row (sent above venue). CLAUDE.md's E2 line corrected from "0–10 tenths". The per-row table stays out of the repo on the 2026-08-20 ruling, recorded as a deviation from §10 (verbatim output under gitignored `data/`). The measurement-skeptic's audit caught a flipped sign, a `parlay_positions` claim the census never reads, depth inferred from equality, and three missing §11 caveats before entry; all applied, listed in the result's §8. **Then re-read on Joe's word:** `parlay_positions` is 10 OPEN rows, ids 1–10 (`/api/hedge`, `status = 'open'` only), 5 `derisk` and 5 dead, all `kalshi_combo`; `notifications` has no `hedge_lock` kind (zero locks still true); CLAUDE.md's transacted-path block and the locks sentence now carry the 2026-09-15 reads with their instruments. Next ADR **0154**; schema **v43**; arming unchanged (hand path armed, engine and bids dry).

**First reads for the next session, in order:**

0. ~~`manual_orders` rows 8–13~~ — read, as the registered census (above).
1. `read-incidents -n 5`: no `read_budget` row after the deploy. Then the
   NFL chip with Joe's eyes.
2. ~~The 21:25Z totals slot~~ — answered early, 17:28Z read of `credits-tail`:
   every MLB call today carried `h2h,spreads,totals` at **6** credits — the
   hourly floor at 14:18Z, 15:18Z, 16:18Z and three attention buys 12:21Z–13:02Z
   — so the first totals purchase was the floor's, not the 21:25Z slot; the
   "Three totals" card built from them at ~14:20Z. Vendor month to date 5,018
   of 20,000. **The eighteenth entry's read 2 (`unmatched`) is answered**,
   17:30Z, `list_unmatched.py` on live (2,098 open items, grouped locally):
   `expected 2 sides` on game-total identifiers **stopped at 05:17Z**, the
   last pass before the 05:27Z deploy — NCAAF 344 items, MLB 202, NFL 49,
   WNBA 5, none seen since — and continues only on `*TEAMTOTAL*` (NCAAF
   146, MLB 105, NFL 38, last seen 17:18Z), out of scope by design. What
   totals accrue now is `no linked game event` (NCAAF 57, WNBA 5, MLB 3):
   a total whose parent game is itself unmatched, which is the derived
   link doing what ADR 0152 says. `event_links.total_fixture_segment` was
   not re-counted (no whitelisted query counts it; the eighteenth entry's
   45 stands as the deploy-day read). Beside it, unrelated and large: 542
   NCAAF `KX*GAME` items with no sportsbook fixture — scope, not names
   (`NOT_CARRIED`; no alias can help). **Then, on Joe's word, the alias
   work:** of the 15 NCAAF `no team-pair bijection` rows, 13 were a prefix
   falsely sharing one side (Texas/Texas Tech, Michigan/Michigan State,
   Arkansas St./Arkansas State, Idaho St./San Diego State, Portland St./
   North Dakota State) or the pinned Iowa/Iowa St. class; **two were real**
   and are in `americanfootball_ncaaf.yaml`: `Central Connecticut St.` →
   Central Connecticut Blue Devils, `Tennessee-Martin` → UT Martin
   Skyhawks, each verified False→True on `_bijection`. The 92 `ambiguous`
   rows (56 games: Virginia/West Virginia, USC/Louisiana…) are the resolver
   class the YAML header says is not fixable there. Zero credits: the
   queue carries the book spelling, so `capture_team_names.py` was not
   re-run; `test_no_alias_entry_is_decoration` now admits a pinned
   `QUEUE_DERIVED` table as the second evidence source. Committed
   `68f0923`, CI 35002402759 green, deployed ~17:50Z, `/api/health` reads
   `68f09230…` — live is now this commit.
3. **One NFL prop tap from Wed 16 Sep 20:15 ET** (the horizon), on the
   DET@BUF game: team 6 + props 6 = 12 credits.
4. One more "Price on Kalshi" on the totals card, for the second point on
   whether a fresh NO-leg combo is ever quoted. Record on #38 either way.

### Still open, in order

1. Items 1–4 above.
2. ~~`parlay_position_legs.event_title`~~ — built, ADR 0153, schema v43,
   live `f220f65`.
3. **Run the fixed probe once, with Joe at the keyboard** (carried).
4. ~~Read the next real fill's row~~ — done inside the census: the six
   post-v40 rows carry the venue's price and it agreed with `fills` within
   the registered 1-tenth tolerance on all six — single-fill YES rows, where
   the open side question cannot bite, so not corroboration of either reader.
5. ~~The census~~ — **taken 2026-09-15, spent.** A second look needs a dated
   amendment. Open from it: a future S2 (single-market) hand bet and any
   `side = no` order are populations this look never saw.
6. Carried: `user_not_found` on shard 3 only; the 25 s read budget
   (instrumented by ADR 0151, not registered — and it just caught its
   first real one).
7. **Reservations:** none live. Next ADR **0154**; schema **v43**.

---

## 2026-09-15 (eighteenth session) — over/unders and player props are parlay legs, both sides, on two cards of their own; two ADR 0110 refusals fell to their own premises

Joe's ask, verbatim: *"add the capability to assess and bet on other odds
and props. not just spreads and moneylines, but also over/unders, and
props. for example, if there is a good chance of a particular player going
over or under a certain number of rushing yards, that should be a whole
other set of parlays."* Single errand named by him, so no partner pass
(CLAUDE.md step 0's exception). He answered the four decisions it needed in
one interview: add `totals` to the feed now; NFL props on tap per game;
new cards only; Under legs in the same work, Overs first.

**The session's finding is that both blockers were refusals whose premises
the record had already falsified.** ADR 0110 §1 killed props because a
prop key "multiplies every call by the roster"; the vendor bills per market
key per region, and ADR 0079 had measured it (five keys × two regions = 10
credits an event). ADR 0110 §2 refused totals on 496 × 1.5 = 744 > 700; the
NFL Sunday it was written to protect was read off live this session
(`credits-day --date 20260913`): **236 credits, 59 calls × 4**, month to
date 4,982 of the vendor's 20,000. Ticket #36 closed on the inherited kill.
Lesson written (`tasks/lessons.md` 2026-09-15 third: a refusal carries its
premise; re-read the premise, not the request). ADR **0152** names each
overturned premise beside the fact that overturns it; #38 supersedes #36 in
part and #36 carries the comment.

**Built, five slices, every guard seen red once (mutation list in ADR 0152
§2 and in each test's docstring):**

1. **Totals pricing arm.** `backend/kalshi/totals.py` (`"Over N.5 <unit>
   scored"` reader, `runs`/`points` whitelist, `total_book_point(line) ==
   line` written once), `runner.totals_quotes_for_event` +
   `_price_totals_event` (fair rows only, both sides at the shared point,
   no `recommendations`). **Total events now inherit their game's link**
   (`TOTAL_LINK_METHOD`, `DERIVED_LINK_METHODS`); until this deploy every
   `KX*TOTAL` event was refused by the two-team bijection on every pass
   into `unmatched_items`. `TEAMTOTAL` out of scope, said in the module.
2. **NFL props, both halves in one change.** `PROP_SERIES` gains
   `KXNFLPASSYDS/RECYDS/RSHYDS`; `prop_market_keys(sport_key)` (required
   argument) reads `PROP_MARKET_KEYS_BY_SPORT`, NFL = 3 yardage keys =
   `NFL_PROP_SERIES.values()` (pinned). Planner reserves the dearest sport
   (`max_prop_cost_per_event`); tap and `/api/odds/refreshable` quote the
   exact one (NFL team+6, MLB team+10). ADR 0032 stands: on tap only.
3. **Two new cards, their own set.** `props` ("Three props", MLB ∪ NFL
   keys) and `totals` ("Three totals"), 2–3 legs, floor 0.20, not pushed to
   the phone. `CANDIDATE_SQL` admits `POOL_MARKETS` (one constant — the
   inspector's transcription is pinned to it and moved with it). Existing
   cards keep `TEAM_MARKETS_ONLY`; `test_totals_in_the_pool_change_no_team_card`
   is the sibling of the props one. Refresh panel mounted on `/parlays`.
   Glossary: `total`, `player_prop`, `line`. Every reason code the pool can
   count now has words (`tests/test_parlay_exclusion_words.py`, a source
   scan; four prop codes had none since the prop arm landed).
4. **Under legs.** `CandidateLeg.side`; the Under row is a NO leg on the
   same Kalshi market with the Under row's own consensus, label "Under 8.5
   runs scored" / "NO on Anthony Kay: 6+ strikeouts". Side travels through
   `_serialise_leg`, `PriceOnKalshi`'s echo, `ParlayLookupLeg.side`
   (default `"yes"`), `resolve_requested_legs` (side is part of the leg's
   identity), `lookup_combo`'s body (per-leg), `echoed_legs`,
   `parlay_lookups.selected_legs`, `RecordParlay` and the per-leg ticket
   (`preferSide`). `_joint_key` carries the side. **Unmeasured: whether any
   Kalshi collection accepts a NO leg** — the fixtures show one minted
   (`no Over 8.5 runs scored`); the first "Price on Kalshi" on the totals
   card is the measurement.
5. **`fly.live.toml` `ODDS_MARKETS = "h2h,spreads,totals"`.** Every
   scheduled call 4 → 6 credits. Registered check: `credits-day --date
   20260920` beside 20260913's 236.

**STATE at close.** Full suite locally **7,207 passed, 10 xfailed** in
31m41s; the one failure was `TestTheCandidateScanCopyDoesNotDrift` (the
inspector's transcription of the widened scan — updated, guard green).
Ruff clean, tsc clean, `next build` green. Committed `f8d2e02`, CI run 34932126648 green.
Deployed `flyctl deploy -c fly.live.toml -e GIT_SHA=f8d2e02…`, machine restarted 05:27:04Z, `/api/health` reads `f8d2e022…`, no migration (v42 already). Recorder: pass 1 full 101.4 s, `dropped_unknown_total_unit: 0`; **45 total events linked under `total_fixture_segment`** (MLB 12, NCAAF 17, NFL 16) where the pre-deploy read had 0; the 887 `expected 2 sides` refusals on `*TOTAL*` identifiers stopped accruing for every game-total series (`KXMLBTOTAL`, `KXNCAAFTOTAL`, `KXNFLTOTAL`, `KXWNBATOTAL` all `seen_this_pass=False`) and continue only on `*TEAMTOTAL*`, which is out of scope by design; **130 NFL prop markets admitted** (was 0); `/api/parlays` serves nine cards, the two new ones with their own thin-slate sentence; `/api/odds/refreshable` quotes MLB team 6 / prop 16 (three keys × two regions; five prop keys × two). `fair_prices` carries **0** `totals` rows yet — nothing has bought them, the 21:25Z slot is the first. Odds credits spent this session: **zero**
(every live call was `GET /api/health`, an SSR read, or a read-only,
bounded `inspect_live_db.py` query). Next ADR **0153**; schema **v42**;
arming unchanged (hand path armed, engine and bids dry).

**First reads for the next session, in order:**

1. `sweep-log` after the 21:25Z MLB slot on 2026-09-15: the served rows
   should carry `h2h,spreads,totals` at **6** credits. That is the first
   totals purchase in the desk's life; then `/parlays` "Three totals" either
   builds or says why in `excluded`.
2. `inspect_live_db.py unmatched` (or the equivalent read): `*TOTAL*`
   refusals stop accruing after the deploy's full pass; `event_links`
   gains `total_fixture_segment` rows.
3. One NFL prop tap on a game Joe is looking at (team 6 + props 6 = 12
   credits): measures NFL prop coverage and whether `_alternate` is needed
   for NFL (ADR 0079's MLB finding is not assumed to carry).
4. One "Price on Kalshi" on the props card and one on the totals card:
   the venue's answer on prop legs, total legs and NO legs. Record the
   answer on #38 whichever way it goes.

### Still open, in order

1. Items 1–4 above (reads, then two taps Joe chooses).
2. **Run the fixed probe once, with Joe at the keyboard** (carried from the
   seventeenth entry).
3. **Read the next real fill's row** — still 7 `manual_orders` rows.
4. **The census** — first session after the 10th real manual order or
   2026-11-01.
5. Carried: `user_not_found` on shard 3 only; the 25 s read budget
   (instrumented by ADR 0151, not registered).
6. **Reservations:** none live. Next ADR **0153**; schema **v42**.

**Struck this session:** #36 (superseded in part by #38); ADR 0110 §1 and
§2 (overturned by ADR 0152 on their own premises); the "Over sides only"
caption (shipped and removed inside the same session — slice 4 landed
before the deploy).

---

## 2026-09-14 (seventeenth session) — the probe cancels on its shard, the "unexplained 401" was the script signing a query string, and the closed-path claim survives nowhere but the ADR that made it

Four named errands from the sixteenth entry, worked in order, no partner
run (Joe's instruction). Read ADR 0150 before 0149; the account state at the
top of the previous entry still holds and is the thing to advise from:
toggle ON, everything on shard 1, combos placeable here, **singles not**.

**Item 1 — done, and the 401 is explained.** `scripts/probe_resting_combo_order.py`
now reads `exchange_index` off the step-1a market payload (same reader as
discovery, so a bool or a negative is unreadable), **refuses before the POST
if it cannot** — an order that cannot be cancelled is not placed — and sends
`?exchange_index=<shard>` on the DELETE. The "unexplained" 401 on the
orders-list read was **ours**: `raw_request` signed
`"/portfolio/orders?ticker=..."` whole, and `backend/kalshi/auth.py:74`
records that Kalshi signs the path only (verified 2026-08-06 with this exact
symptom). Both captures that ever reached that step — 2026-08-30 and
2026-09-14 — show `INCORRECT_API_KEY_SIGNATURE` on the two query-carrying
calls and 200 on the four beside them. The venue did nothing odd; there is
no judgment-on-live-data question here and no reason to switch models.
`raw_request` now takes `params=` and refuses a `?` in its path.
`tests/test_probe_resting_combo_order.py`: 15 tests, venue faked at the
`auth`/`client` surface, **eight mutations each seen red** (cancel without
the shard, `cancel_params` → `{}`, the pre-POST refusal deleted, `shard_of`
unchecked, the query signed, the `?` guard deleted, shard hardcoded to 1,
the while-resting balance read deleted).

**Item 2 — the literal claim is gone; its mirror image was not.** Nothing
in code, copy, docs, tasks or CLAUDE.md asserts combos cannot be placed here
except ADR 0149 (not edited) and places that quote it as false. But the
**opposite** overreach from the same morning — "the account page is
read-only / there is no way to fund a shard by hand", measured with the
toggle OFF and stated without the condition — was still on four surfaces,
and ADR 0150 §6 had already overturned it. Corrected: the glossary's
`exchange-shard` entry (live copy), the docstring of
`set_target_balance_allocation.py`, the docstring and name of the
`test_buy_controls` guard (`test_the_allocation_page_is_not_offered_as_a_bare_remedy`
— the URL stays forbidden on the ticket and glossary, now for the true
reason: whether it works depends on a toggle), and my own memory file. The
two route refusals that name the page (`POST /api/manual-orders` 422 and
`check_affordable`) now carry the condition — *"where the transfer control
appears only while 'Disable balance management' is on"* — which the tests
requiring the URL still pass.

**Item 3 — NOT settled, but instrumented.** Both 2026-09-14 balance captures
carry `balance_breakdown[].balance` and **no `resting_order_value_breakdown`
field at all** on this account. The 23:34:43Z read shows shard 1 unchanged
after the 23:28:57Z 201, which would prove gross **if** the 2c order was
still resting at that second — and nothing records when Joe's hand cancel
landed, so the window may not contain the input. The fixed probe now reads
`/portfolio/balance?exchange_index=<shard>` between its create and its
cancel — the only second this repo ever has a known resting order — so
**the next run answers it**: compare with `set_target_balance_allocation.py
--read` taken just before. Not run this session: it places a real order,
which is not on the authorised list, and Joe was not at the keyboard.

**Item 4 — done.** `rest.py`'s shard table reads Default / Combos / Crypto &
Commodities / Tennis, Baseball, Basketball, dated 2026-09-14, with the
2026-08-30 reading kept beside it so the drift is visible.

**STATE at close (superseded by the 'Later the same night' section below for schema, ADR and live sha).** Full suite locally: **7118 passed, 10 xfailed, 1 failed** in 21m08s; the one failure was `test_only_kalshirestclient_defines_a_method_named_orders`, which pins `def orders` to `rest.py:711` and my five comment lines in the shard table moved it to 716 — re-pinned to 716, not loosened. Ruff clean, tsc clean. Committed as `01d56b4`, CI run 34913698922 green, deployed `flyctl deploy -c fly.live.toml -e GIT_SHA=01d56b4…` (the classifier refused once, took the plain retry), `/api/health` reads `01d56b4f73…`; recorder resumed (pass 1 full 72 s, pass 2 quote 6.1 s); every route 200, sub-second warm. Lesson written (`tasks/lessons.md` 2026-09-14
sixth: the steps after a refusal run only on the first success; an
"unexplained" venue response is a claim about your own request until re-read;
when a module documents a fix, grep for callers that make the same call by
hand). No ADR: nothing decided, one script fixed, copy conditioned. Next ADR
**0152** (0151 taken later the same night); schema v42; arming unchanged; odds credits: zero spent.

### Later the same night — the partner pass, and the code backlog emptied (ADR 0151, schema v42)

Joe asked for one partner pass to rule every carried code item build-now or
strike-for-good. The partner ruled, and **first corrected this entry's
"the next hit is a measurement"**: it measured Fly's log retention on the
live app at 100 lines, forty seconds during a busy window, because each
pass emits a ~900-char INFO dict every ~20 s. The three 00:37–00:46Z hits
were already gone. Rewording the warning changed what was lost, not
whether it was. Lesson: `tasks/lessons.md` 2026-09-15.

**Built, in the partner's order, sequential on main, no lanes:**

0. **`api_read_incidents` — schema v42, ADR 0151.** Every read-budget 503
   and every failed loopback health probe leaves a row: kind, method, path
   with query, elapsed_ms, exception class, budget. Best-effort writer with
   a one-second lock wait, never raises; a count is a FLOOR. Read it with
   `scripts/inspect_live_db.py read-incidents`. The health probe runs every
   pass at a 2 s threshold against a route that opens the DB — the
   sensitive instrument for the "reads crawl during heavy write passes"
   hypothesis, and it had been throwing its answer away.
1. **6d — the API-unreachable alert carries the probe's exception class and
   elapsed** (`ReadTimeout` = slow box, `ConnectError` = dead box), on the
   phone and in the row.
2. **6c — `int(fill_count)` truncation is a refusal, not a rounding.** A
   non-integral fill records no position and says so on the ticket; `4.0`
   is still four. Truncation understated the stake and flattered `/hedge`.

**Struck for good, reasons in ADR 0151 §4:** 6a `parlay_positions.status`
never advances (it advances at Joe's tap; an automatic close would have to
pick which signal ends a position and the venue can settle a combo before
its legs) and 6b the hedge-evaluation table (a recorder over a source that
has produced zero locks in its life).

**Not registered:** the 25 s hypothesis. Two mechanisms (writer contention
vs. CPU starvation on two shared vCPUs), no instrument that separates
them, no denominator. Collect rows; register when there is a statistic. Do
not widen the budget.

Verified: `tests/test_api_read_incidents.py` (10) and two fractional-fill
tests, five mutations each seen red; ruff clean. Full suite locally: **7,133 passed, 10 xfailed**, one failure — the inspector's `SUBCOMMANDS` registry guard, which wants every new subcommand written down; `read-incidents` added, guard green. 30m25s with a second run beside it. **Deployed as `1201ed6`**: CI run 34919063964 green, `flyctl deploy -c fly.live.toml -e GIT_SHA=1201ed6…`, machine restarted 02:03:24Z, entrypoint logged `migrated v41 -> v42`, `/api/health` reads `1201ed64…`, and `inspect_live_db.py read-incidents` on `/data/cockpit.db` answers with 0 rows — the baseline. **main = live.**

### Still open, in order

1. **Run the fixed probe once, with Joe at the keyboard**, on a live
   shard-1 combination: it now settles item 3 (gross vs net shard balance)
   and proves the cancel path end-to-end at the venue for the first time.
   Cost: a 2c resting order for a few seconds. Read `--read` first.
2. **Read the next real fill's row** — still 7 `manual_orders` rows, 6
   filled, last submitted 2026-09-10T16:00Z.
3. **The census** — first session after the 10th real manual order (at 7)
   or 2026-11-01.
4. Carried: `user_not_found` on shard 3 only. (`parlay_positions.status`
   and the hedge-evaluation table are STRUCK, ADR 0151 §4; the truncation
   and the alert's exception class are BUILT, ADR 0151 §5 and §2.)
   **The 25 s read budget was SEEN blanking a screen for the first time,
   2026-09-15 00:37:31Z and 00:38:07Z** (`API read connection hit its
   25000ms budget and was interrupted`, twice, 40–75 s after pass 139 ran
   Joe's hand MLB prop refresh with 1,502 quotes and 9,278 markets written).
   Joe had just bought MLB props for the Giants game, refreshed, and Games
   said "Backend unreachable". Nothing had been deployed (live was still
   `0c9b770`); every route read 200 in ~1 s within ten minutes. **Cause not
   pinned**: `flyctl logs` kept 100 lines with no access lines, so the
   route is not recorded. Leading hypothesis, unmeasured: a 6 GB file on a
   2 GB machine with the page cache cold after a large write pass — the
   same shape as the 17.4 s cold `/api/parlays` read after lane B's index
   build. Previously carried as "`/hedge`'s 25 s `get_conn` timeout as its
   real blanking mode" — it is the Games screen's too. **A third hit at
   00:46:08Z, inside the 72 s `full` pass the recorder runs after the
   deploy's restart** (pass 1 full 00:45:40–00:46:52; the first timing
   pass in that window read `/api/window` 9.4 s and `/api/signal` 10.3 s,
   both sub-second two minutes later). So the blank rides on heavy write
   passes — boot's full pass, and a hand prop refresh that wrote 1,502
   quotes — on two shared vCPUs. Still a hypothesis; the route is still
   not recorded. **Done on Joe's word the same night:** the budget
   warning now reads `... interrupted: GET /api/slate after 27.3s` — a
   stamp middleware records each request's start and the handler logs
   method, path with query, and elapsed
   (`test_the_warning_names_the_route_and_how_long_it_had_run`, two
   mutations seen red). The next hit is a measurement.
5. **Reservations:** none live. Next ADR **0152**; schema **v42**.

**Struck this session:** the probe cancel (fixed); the 401 (explained,
ours); the "combos cannot be placed here" sweep (clean; its mirror image
corrected on four surfaces); `read_shard_funds` gross-or-net (instrumented,
not answered); the stale shard map (updated).

---

## 2026-09-14 (sixteenth session) — a combo bet needs its shard funded, the auto-management toggle is what hides the funding control, and "cannot be placed here" was an overreach Joe caught

**The finding, in its corrected form — read ADR 0150 before ADR 0149.** An
API order is refused when its exchange shard is underfunded, and Kalshi's own
app funds the shard for you as you bet there while this tool does not. That
is the whole mechanism. **It is a state, not a closed path**, and the
difference is the entire lesson of this session.

Established, in order: the account page showed **no transfer control** while
"Disable balance management" was OFF; auto-management still left Combos at
one cent against $22.68 on Default; a 2c GTC probe on a live shard-1
combination returned **400 `insufficient_balance` 3 of 3**
(`scripts/probe_resting_combo_order.py` — free, a refused order moves no
money); `GET /portfolio/target_balance_allocation` returned
**`{"allocations": []}`**. Kalshi's docs: *"Programmatic traders must
preallocate collateral on a given exchange shard before order placement."*

**Then it was over-generalised, shipped, and refuted by Joe.** Those three
refusals were written up — in ADR 0149 and on the live ticket — as "a
combination bet cannot be placed through this cockpit at all." **False.**
Six of the seven real `manual_orders` rows are *filled*
`KXMVECROSSCATEGORY-SHARD1` combinations placed through that exact path on
09-08/09/10, when the shard was funded ($22.24 on 09-08, $14.17 on 09-09);
the audit proving it was run at the **start of this same session**. Joe
rejected the claim from memory of his own fills. ADR 0150 corrects it and the
copy; the forbidden strings are guarded.

**Then Joe settled it himself.** He toggled "Disable balance management" ON
and moved the whole balance to Exchange 1 — **so the transfer control exists
and appears once auto-management is off.** Shard 1 read $22.68, and the same
probe that had refused three times returned **201 accepted**. Combos work
through the cockpit. (The probe's cancel then 404'd because it omits
`?exchange_index` — a failure `rest.py` documented on 2026-08-30 and the
script never adopted; the order was cancelled by hand,
`reduced_by 1.00`, nothing left resting. **Fixing that script is open work.**)

`docs/measurements/2026-09-04-presence-at-the-moment-of-a-bet-result.md`
returned UNRESOLVED with no mechanism to point at. It has a candidate one now
— an unfunded shard refusing his combo taps — but **that measurement is NOT
reopened by this and may not be cited as though it were.**

**Check 9a is CORRECT and stays.** It was suspected mid-session of being a
false brake — refusing bets the venue would take, the ADR 0112 failure, which
would have outranked everything. Three probes at the venue say no. The
2026-08-30 observation it was built on never recorded the toggle state; today's
does.

**How the session started, and why that matters.** The partner opened with 48
commits / 5 ADRs / 2 migrations since the last fill against **0 bets**, and
ruled: a near-nothing day, do not manufacture a lane. That was right on the
evidence it had. What changed it was **asking Joe one question** — had he bet,
and did it go through the tool. He had bet, directly, because the cockpit
refused him. The whole session came from the question, not from the backlog.

**STATE at close.** `main` = live, deployed with `-e GIT_SHA=<full sha>` and
read back off `/api/health`; clean tree, no lanes, no branches; recorder
writing; arming unchanged (hand path armed, engine and bids dry); schema v41;
zero Dependabot alerts; zero open map tickets; **odds credits: zero spent.**
Next ADR **0151**.

**ACCOUNT STATE AT CLOSE — read this before advising anything.** Joe has
"Disable balance management" **ON** (manual mode) and the **entire balance on
Exchange 1 (Combos)**: shard 1 $22.68, shard 0 $0.0065. So combos are
placeable from the cockpit and **singles are not** — a single-market bet
draws on shard 0, which is empty. Moving money between shards is the
operator's own action in the UI, or
`scripts/set_target_balance_allocation.py --transfer N --from-shard A
--to-shard B --i-am-joe-and-this-moves-money` (the agent is refused this by
policy; Joe runs it).

**The target allocation is CLEARED** — `{"allocations": []}`, read back, on
Joe's instruction. It had been set to `0=80, 1=20` earlier in the session
while it was inert under auto-management; under manual mode it could have
pulled 80% back to Default and undone his move. Automatic rebalancing is off
and the balance stays where he put it.

### What shipped

1. **ADR 0147** — the `/hedge` weakest-leg ordering ruled **deliberate and
   declined**, the last unruled item on the board. The item's stated cause was
   wrong (a settled leg short-circuits to `STATE_DEAD` first); the real window
   is a clock skew between `kalshi_markets.result` and the live quote status.
   The obvious fall-through fix would price a hedge on the healthy leg one
   cycle before the ticket dies. Pinning test added, mutation-verified.
2. **ADR 0148** — the ticket blamed Joe's typed amount for an empty wallet.
   `affordable` (3 contracts) vs `contracts` (0 after the ceiling): the
   "Not enough, the smallest bet here is $0.26" sentence was branched on the
   second while asserting about the first, and the contradicting "Trimmed to
   0 — your Kalshi wallet set the size" rendered right under it. Fixed with a
   third branch, the shard block on `GET /api/manual/market/`, and
   `exchange-shard` in the glossary.
3. **ADR 0149** — §1 above. Ticket copy corrected again (see below),
   `scripts/set_target_balance_allocation.py` added read-first.

### Corrected within the session — read this before trusting ADR 0148 §4

ADR 0148 shipped a remedy — *"allocate at kalshi.com/account/exchange-indexes"*
— that **the page cannot perform**, and a test *required* the URL. It was
instructing an impossible action from the moment it deployed. The guard is now
**inverted**: the URL is forbidden on both surfaces that carried it (the ticket
and the glossary). ADRs are not edited; 0148 stands as written and 0149
supersedes its §4. Lesson: `tasks/lessons.md` 2026-09-14 (fourth).

**ADR 0084's premise is void.** It ruled the desk never moves money *because
the operator can do it at that page*. He cannot. The conclusion may still be
right; a successor must re-argue it rather than cite 0084.

### Still open, in order

1. **Fix `probe_resting_combo_order.py`'s cancel.** It omits
   `?exchange_index`, so a *successful* probe leaves a real order resting and
   404s on the way out — which happened tonight and was cancelled by hand
   (`reduced_by 1.00`). `rest.py:655-670` documents the fix and the script
   never adopted it. Verify by disabling. The orders-list read returned
   **401** in the same run, unexplained; worth one look.
2. **Check nothing else still asserts combos cannot be placed here.** ADR
   0149 §1 and §4 are superseded by ADR 0150 (ADRs are not edited), but copy,
   comments or CLAUDE.md may have picked the claim up.
3. **`read_shard_funds` may read a gross number.** It reads
   `balance_breakdown[].balance`; Kalshi defines spendable as balance minus
   resting-order value and now publishes `resting_order_value_breakdown`. If
   gross, 9a is *permissive*, not a brake. One capture settles it.
4. **`backend/kalshi/rest.py:57-60`'s shard map is stale.** Read off the live
   account page today: shard 2 is "Crypto **& Commodities**", shard 3 is
   "Tennis, Baseball, **Basketball**". Nothing computes off the comment; it is
   what a future session reasons from.
5. **Read the next real fill's row** — still 7 `manual_orders` rows, 6 filled,
   last submitted 2026-09-10T16:00Z. Unchanged today.
6. **The census** — first session after the 10th real manual order (at 7) or
   2026-11-01.
7. Carried: `parlay_positions.status` never advances; no hedge-evaluation
   table; `int(fill_count)` truncation; the API-unreachable alert's exception
   class; `/hedge`'s 25 s `get_conn` timeout as its real blanking mode.
8. **Reservations:** none live. Next ADR **0151**; schema v41.

**Struck this session:** the `/hedge` weakest-leg item (ruled, ADR 0147); the
typed-amount defect (fixed, ADR 0148); the false remedy (corrected, ADR 0149);
the "is 9a a false brake" question (answered: no, 3/3 at the venue).

---

## 2026-09-14 (fifteenth session) — three counts had collapsed into one word; branch CI now carries a signal; /hedge cannot raise on a live row

**The session's finding is that the transacted-path count in CLAUDE.md was
three numbers wearing one word.** Read off live at session start
(`manual_orders` and `parlay_positions`, bounded by id): **7 real orders, 6
filled, 4 positions.** CLAUDE.md said "four by 2026-09-09" (live: three
filled by then; the four were ADR 0129's four *orders*, one unfilled), "all
four real fills predate v40" (six do), and "all four real positions dead"
(right — the position recorder postdates orders 1–2). Each re-reading
agreed with the last, which is why it survived two audits of that
paragraph. The same failure shape the spine already records for
`actionable`. Corrected with a three-line table naming each table and the
read date; the pattern is in `tasks/lessons.md` (2026-09-14, second).

**STATE at close.** `main` = live (deployed with
`-e GIT_SHA="$(git rev-parse HEAD)"`, read back off `/api/health`); clean
tree, no lanes, no branches; recorder writing (sweep-log 'skipped' rows
through 17:11Z, next slot MLB 21:26Z); arming unchanged (hand path armed,
engine and bids dry); schema v41; **zero Dependabot alerts; zero open map
tickets; credits: zero spent.** Every live call was read-only and
id-bounded. The partner's read at start, adopted: a near-nothing day; do
not manufacture a lane. Next ADR **0147**.

### What shipped, in the partner's order

1. **CLAUDE.md counts corrected** (above). ADR 0143 §"fills is
   retention-eligible" and ADR 0145 still say "four"; ADRs are not edited,
   and each was true of its own table on its own date.
2. **The lane-board guard skips off-main instead of failing by
   construction.** `test_the_integration_tree_is_found_and_carries_an_adr_baseline`
   asserted a lane named `main` exists; a CI checkout of a lane branch
   (`actions/checkout`, depth 1, only the pushed ref) has no
   `refs/heads/main`, so it was red on every branch run and branch CI
   verified nothing (run 34616576251). Now `pytest.skip`s, in words, when
   `git rev-parse --verify refs/heads/main` fails in the checkout — git's
   predicate, not `lane_board`'s, so a resolver that stopped matching on
   `main` still fails. **Verified three ways**: the old file fails on a
   single-branch clone of a probe branch exactly as CI did; the new file
   skips there; and on `main` with `is_main=` mutated to never match, the
   new file is red, not skipped (first mutation, on `_integration_path`,
   missed the guard — the test reads `is_main` — and was redone). The
   `lookup-scout` confirmed this was the **only** test structurally red
   off-main: `test_no_draft_reaches_the_integration_branch` fails closed
   on detached HEAD but only trips on a real `DRAFT-` file. Probe branch
   and clone deleted.
3. **`/hedge` pre-flight before tonight — `runtime-realist`, read-only,
   no raise path found.** Traced `/api/hedge` and `hedge_watch` through
   `assess`, `combo_entry_fee_tenths`, `hedge_lock`/`derisk` and the book
   reads, and ran the arithmetic over 15 synthetic rows shaped like the
   real ones. Every abnormal state the schema permits renders as a
   `Refusal`. The only raise sites need inputs the live table's CHECKs
   forbid (`stake_tenths > 0`, `return_tenths > stake_tenths`, `side IN
   ('yes','no')` — **confirmed on the live `sqlite_master`, not just
   `schema.sql`**) or a non-numeric `*_size_fp` from Kalshi (NaN passes
   `parse_quantity` and raises at `int()`; no fixture has ever carried
   one). The four real rows: stake/return 1640/4000, 1785/7000,
   1946/14000, 2106/6000 — all far above the `MIN_DECIMAL_ODDS` edge where
   ADR 0145's sunk fee could turn a legal row into an `UNREADABLE_TICKET`
   refusal.

### Known and declined — added this session, so nobody promotes them

- **The way `/hedge` actually blanks is a timeout, not the arithmetic.**
  `get_conn`'s 25 s budget is per-connection; `build_payload` reads Kalshi
  sequentially per ticker (5 s timeout, 4 retries, `Retry-After` honoured
  to 60 s) and then runs three more sqlite statements. One throttled
  ticker can exhaust the budget, the next statement raises `interrupted`,
  the route returns 503, and `page.tsx` renders the whole screen as
  "Backend unreachable." The watcher takes the same latency with no
  consequence. Not built: no such blank has been observed, and moving the
  sqlite reads ahead of the venue reads is a change to a path that has
  produced zero locks.
- **`assess` picks the weakest leg before checking book status**, so a
  settled leg priced lowest makes the whole block a `market_closed`
  refusal even with a hedgeable live leg beside it. Words, not a raise.
  Unruled.
- **A `None` entry fee is silent on the card** (`entry_fee_display: null`
  is dropped), while the refusal a step later speaks. Cosmetic.
- Carried unchanged: `parlay_positions.status` never advances; no
  hedge-evaluation table; `int(fill_count)` truncation; the
  API-unreachable alert's exception class is not recorded (the partner
  dropped it again — no named consumer).

### The partner's message for Joe, relayed

The desk is finished for what it is for. Seven orders, six fills, four
positions, all by hand, all through the cockpit, none of them something the
tool told him to do — which is the design. Nothing runs between sessions
(ADR 0146), so what earns now happens at his keyboard: bet tonight if he
wants to, and let the record accumulate. **The one ask: after his next
fill, have a session read that `manual_orders` row** — it will be the first
ever to carry `venue_fill_count`, `venue_avg_fill_price_tenths` and
`venue_avg_fee_dollars`, and confirming that write once is worth more than
any of the items above. If he wants something built, he names it.

### Still open, in order

1. **Read the next real fill's row** (above). Whoever is at the keyboard in
   the first session after it lands; there is no scheduler.
2. **The census** — first session after the 10th real manual order (at 7)
   or 2026-11-01. Runnable as written; may not be cited for or against
   ADR 0143 or 0145.
3. **Reservations:** none live. Next ADR **0147**; schema v41.

**Struck this session:** the lane-board guard's structural red (fixed);
the CLAUDE.md count drift (fixed). The code list is still empty.

---

## 2026-09-14 (fourteenth session) — Arm D never ran because nothing runs between sessions; both lanes are merged and live; #36 closed on zero credits

**The session's finding is that "a scheduled run" was a person nobody named.**
Arm D — five captures at five UTC minutes on Sunday 2026-09-13
(`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md` §7)
— took **0 of 5**. No session was open on Sunday; nothing in this repo opens
one; a timer set in a session dies with it. Four consecutive entries in this
file called it *"a scheduled run, not a task to plan."* By the registration's
own §7 every slot is MISSING, collection closed 01:15Z today, and no later
look may be taken. **Joe stayed off combos all weekend to protect a sampling
frame that was never sampled.** He was told plainly this morning, and told
the hold is lifted. The partner's reading, adopted: the look is void and
**has no successor** — the universal claim was already falsified by the
2026-09-10 disclosed look (two shard-1 books, one resting YES level of 10
each), the owed screen correction shipped before C1, and the only branch
with a live consequence (`EXIT_AT_CEILING`, a 250-contract bid) had size 10
against it. A rate was lost, not a finding. Written as
`docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md` (five slots
MISSING, void), **ADR 0146**, and a lesson (a wall-clock time in a
registration is a person, and the person must be named; a constraint on Joe
expires with the window and he is told when it closes).

**STATE at close.** `main` pushed, live = main (deployed with
`-e GIT_SHA="$(git rev-parse HEAD)"` in one command and read back off
`/api/health` against `git rev-parse HEAD`); recorder writing, live quotes
up, arming unchanged (hand path armed, engine and bids dry). **Schema v41 on
the volume** (`meta.schema_version = 41`, `idx_odds_window` present, planner
reports `SEARCH ... USING COVERING INDEX idx_odds_window`), migration
`v40 -> v41` in **2m05s** at boot (15:23:46Z–15:25:51Z), inside the 2–4 min
budget; the 600 s grace untouched. ADRs **0144** (lane B), **0145** (lane C)
and **0146** (Arm D void) taken. Odds path untouched all session; the freeze
lifted 10:00Z and nothing under `backend/odds/` changed anyway. **Credits:
zero spent.** No lookup minted; combo taps are Joe's own from here.
No lane worktrees remain; both lane branches deleted locally and on origin.
One empty OS-held shell directory (`agent-a11b77117a02ff6c8`) still cannot
be removed.

### What shipped, in the partner's order

1. **Lane B merged — `909632c`, ADR 0144, schema v41.** Merged at the
   branch's final v41 state rather than rebased: the rebase conflicted at the
   branch's *first* commit, which still carried the v40 placeholder, so a
   merge resolved once (db.py: both migration blocks kept, 40 then 41, lane
   B's placeholder sentences replaced with the allocation) instead of three
   times. Full suite green on the merged tree (exit 0), ruff clean. Deployed;
   the first `/api/parlays` after the index build read **17.4 s** (cold page
   cache on a 6.0 GB file, right after a two-minute index build) and
   **0.60–0.66 s** warm; `/api/window` **0.84–1.03 s** warm. **No
   before/after on live is claimed** — the pre-index live route was never
   timed under this method; what is established is that the planner uses the
   index and the routes are inside their historic best bands.
2. **Lane C merged — fast-forward to `bff16db`, ADR 0145.** One correction on
   the way in: the DRAFT→0145 H1 edit was made in the lane worktree but
   `git mv` staged the *index* content, so the numbering commit carried the
   old header and `test_every_file_declares_a_number_this_test_understands`
   went red on the combined suite (1 failed, 7,087 passed). Fixed on main and
   the unpushed commit amended. **Pattern: edit, then `git add`, then
   `git mv` — or check `git show HEAD:<path> | head -1` before pushing a
   rename.** Full suite on the combined tree: that one failure and nothing
   else; guards re-run green after the amend.
3. **#36 closed on the partner's reading, zero credits spent.** The scout
   found the only prop-buying path (`POST /api/odds/refresh` with an
   `odds_event_id`) calls `prop_market_keys()`, which returns the five
   **MLB** keys for every sport; `STAGED_PROP_CARD.markets` is
   `MLB_PROP_MARKETS`; MLB's season ends in about two weeks. So a sweep could
   not change a decision — an MLB result expires with the season and an NFL
   sweep needs a build first — and the partner ruled: close, spend nothing,
   no build. Joe's "spend the credits" answer stands as given; the premise
   changed and the closing comment says he can reopen by saying so. Written
   on the ticket: the operative threshold (**≥2 distinct fixtures** each
   with a fresh, two-sided, devigged prop leg and a Kalshi rung —
   `min_legs = 2`, one leg per fixture), so a reopener does not re-derive it.
4. **#37 opened** under map #3: a prop refresh on a non-MLB fixture requests
   MLB markets against it and may still bill — a live defect on a route Joe
   can tap today. The asked-for fix is a **refusal** for sports with no prop
   keys, not a sport-aware build. Not folded into #36's closure on purpose.
5. **Housekeeping.** `tasks/LANES.md` ledger closed for both lanes, board
   regenerated (no lanes, no findings). Lesson and result doc as above.

### The 2026-09-12 "Cockpit API unreachable" alert — assessed, not fixed

One notification at 21:01:09Z on a routine quote pass, `detail = "health
probe failed"`. Every neighbouring pass and venue poll succeeded, no loop
failure, no machine restart since the 09-11 deploy, health's own DB reads are
sub-millisecond and the WAL was 1.9 MB. Most likely a briefly saturated box:
NCAAF kickoff cluster, a 5,000-quote sweep just written, and `/parlays` open
(attention rows at 20:38Z and 21:02Z) on a 2-vCPU shared machine against a
6.0 GB I/O-bound file. **Not provable**: the loop's exception detail goes
only to the 100-line log stream. Known and declined: recording the exception
class on the notification row would make the next one diagnosable.

### Later the same day — #37 fixed and live, and the freeze guard retired

Joe asked for #37 by name. One predicate, `sport_has_prop_markets()` beside
`PROP_BASE_MARKETS` in `backend/odds/client.py` (`PROP_MARKET_SPORTS =
{"baseball_mlb"}` — the sport those keys belong to, **not** a per-sport key
map, which is the NFL build #36 declined), asked by three callers before
spending: `POST /api/odds/refresh` refuses a prop tap on such a sport in
words with `estimated_credits = 0` (the team refresh still goes);
`GET /api/odds/refreshable` quotes `prop_credits: null` (never 0) plus
`prop_markets_available`, and the panel offers no prop button and says why;
`runner.fetch_and_store_props` refuses before every other guard, named set
or not, and records the skip in `odds_sweep_log`. Verified by disabling:
the predicate returning `True` turns the four new tests red. Commit
`1e65bfd`, deployed and read back off `/api/health`.

**The full suite found one thing, and it was not #37's.**
`TestTheFreezeIsRespected` (`tests/test_fair_price_dedupe.py`) asserted no
file under `backend/odds/` differed from the merge-base with `main` — with
**no expiry**, so it tripped on the first post-freeze change and would have
on every one after, forever, while CI could never see it (on `main` the
diff is empty by construction). Retired with a dated note in its place. A
future freeze puts its end time in the assertion.

### Still open, in order

1. **The census** — first session after the 10th real manual order or
   2026-11-01. Runnable as written; may not be cited for or against ADR 0143
   or 0145.
2. **Known and declined, carried so nobody promotes them:**
   `parlay_positions.status` never advances; no hedge-evaluation table;
   `int(fill_count)` truncation (`routes.py:3952`, noted in ADR 0145);
   the API-unreachable alert's cause is not recorded; the lane-board
   integration-tree guard is red on every branch CI run by construction
   (passes at merge).
3. **Reservations:** none live. Next ADR is **0147**; schema is v41.

**Struck this session:** Arm D (void, ADR 0146 — never again "scheduled"
without a name), lane B and lane C (merged), #36 (closed), #37 (fixed,
live), the freeze guard (retired), the weekend "nothing money-touching"
hold (its window closed). **The code list is empty.**

---

## 2026-09-11 (thirteenth session) — E3 is fixed on a branch without touching a column, `/hedge` has never produced a lock, and Monday now merges two lanes

**The session's finding is that the "money-path defect" was a read-site
arithmetic gap, not a storage decision.** The handoff framed E3 — the entry
fee absent from `parlay_positions.stake_tenths` — as "the same
`_record_combo_position` rewire ADR 0143 §4 deferred", i.e. a schema change
that would make a mixed-basis column because all four real rows predate v40.
`kalshi-platform` read the fee semantics against the captures and the two
measurement docs and the framing fell over: the fee on a KXMVE fill is
charged once per combo contract at the combo's own price, so it is a
function of `stake` and `return`, both already on the row —
`fee = 0.071 × stake_dollars × (1 − stake/return)`, identical to
`combo_taker_fee(P, C)` with no contract count needed. No migration, no
backfill, no mixed basis, and the four NULL-venue rows are handled the same
as any row written tomorrow.

**The partner's other finding changed the size of the session, not its
rank: `/hedge` has produced zero locks in its life.** Read on live,
bounded by table: 4 `parlay_positions` rows, all `status = 'open'`, 12 of
12 legs venue-resolved, every ticket carrying a lost leg, so all four are
`STATE_DEAD` and never reach the lock path; `notifications` has **0**
`hedge_lock` rows ever. E3's realised harm is exactly zero and cannot fire
on those rows in future. So: ADR, one read-site fix, copy, synthetic
tests, stop.

**STATE at close.** `main` = live = `3ffbca4` plus this entry (deployed with
`-e GIT_SHA=$(cat sha.txt)` and read back); recorder writing, arming
unchanged (hand path armed, engine and bids dry). **Lane C is on a branch,
pushed, deliberately not merged**: `lane-c-hedge-entry-fee` at `57f7b48`,
one commit on `3ffbca4`, DRAFT ADR reserved **0145**, no schema change.
Odds path untouched: **the freeze to 10:00Z 2026-09-14 holds** — the diff
against `7f0f85f` for `backend/odds/` and `backend/scheduler.py` is empty
on both `main` and lane C. **Credits: zero spent**; every live call was
`GET /api/health` or a read-only, table-bounded DB replay over `flyctl ssh`.
No lookup minted, no combo tap: **Arm D's frame is uncontaminated.** No
open Dependabot alerts. One empty OS-held shell directory
(`.claude/worktrees/agent-a11b77117a02ff6c8`) still cannot be removed; the
second one (`agent-ae85feea6e90c6f59`) is gone.

### What shipped on lane C — `57f7b48`, DRAFT ADR (0145 reserved)

- `core/hedge.py::combo_entry_fee_tenths(stake, return)`: the collapsed
  form at `COMBO_TAKER_COEFFICIENT` (0.071 — 0.070 undercharged four of the
  eight measured fills; 0.071 overstated by 0.6–1.4% on those eight, 1.4% on
  average over 62 more, and understated none), rounded up onto the venue's
  $0.0001 grid and up again onto integer tenths. `None` on an unreadable
  ticket, never `0`; `ticket_refusal` refuses the same tickets a step later.
- `hedge.py::assess` sinks it beside the stake, **`kalshi_combo` rows
  only** — a sportsbook slip's vig is inside the odds Joe typed. One sunk
  number feeds `hedge_lock` and `derisk` alike.
- Payload gains `entry_fee_display` (string or `null`); the card reads
  `$1.64 + $0.07 fee → $4.00`; `stake_display` is unchanged so it still
  reconciles with the `manual_orders` intent. `RecordParlay.tsx` tells him,
  on the combo option only, to type contracts × price before the fee.
- `NOTES["upper_bound"]` (key kept) no longer says the entry fee is left
  out; names the rate and which way it errs. Killed words still killed and
  still guarded. `core/hedge.py`'s "does NOT establish" list and CLAUDE.md's
  E-table rewritten: E3 is now `too LOW, ~1% of the fee`.
- **Verified by disabling**: removing the sunk term turns three of the four
  new position tests red. The worked defect, synthetic: 4 × 41c hedged at
  56c is **+51 tenths and `guaranteed`** as a slip, **−18 and not** as a
  combo. 3,493 tests across every file that reads CLAUDE.md, the ADRs or
  the hedge modules green on the lane; ruff and tsc clean.
- **Every test row is synthetic and the ADR says so** — there is no real
  row on which a before/after can be shown. The first real lock this
  arithmetic produces will be the first.
- **Lane C's CI run is RED, and not on anything it changed.** Run
  34616576251 fails exactly one test,
  `test_lane_board.py::TestTheRealRepoIsStillReadable::test_the_integration_tree_is_found_and_carries_an_adr_baseline`:
  it asserts a checkout on `main` exists, and a CI checkout of a branch has
  none. It passes from the lane worktree locally (where the main checkout is
  a sibling) and it will pass at the merge, which CI runs on `main`. **Every
  lane branch pushed to origin is red by construction on this test** — lane
  B has never had a branch run, so "CI-clean on its own tree" there was a
  local claim. Not fixed here (a lane_board guard is not lane C's scope);
  the guard could skip when the checkout is not `main`, if anyone wants
  branch CI to mean something. Read the branch red as this test and nothing
  else, and confirm by name before the merge.

### Why compute rather than read `venue_avg_fee_dollars` (ADR §3)

NULL on 4 of 4 real rows; no id-level join from `parlay_positions` to
`manual_orders` (only an incidental `(combo_ticker, placed_ms) =
(ticker, submitted_ms)` equality); "per contract" is asserted from the field
name and the only capture filled one contract; and the computed path never
understated on 70 of 70 observed fills. If the venue figure is ever read
here it is as a check that trips the fee alarm, not as the hedge's input.

### Known and declined, so the next session does not promote them

- **`parlay_positions.status` never advances.** All four rows read `open`
  with every leg resolved; `open_positions()` accumulates dead tickets. The
  screen renders `STATE_DEAD` in words. Hygiene, not a defect.
- **No hedge-evaluation table.** The only record of a lock is the
  `notifications` row and it has never been written. A table over a source
  with zero outputs is not funded.
- **`int(fill_count)` at `routes.py:3952`.** KXMVE counts are fractional on
  the wire (`"227.27"`, `"4.15"`); truncation records the position smaller
  than held. Unruled, rides in the ADR as a note; the collapsed fee form was
  chosen so fixing it cannot break the fee.
- **The lane board's db.py COLLISION flag on lane B** is mechanical — both
  sides of the `_MIGRATIONS` hunk are pre-written — and the partner refused
  a Friday rebase for a Monday merge again. Expect a real rebase Monday.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
2. **SUNDAY 2026-09-13 — Arm D, a scheduled run, not a task to plan.**
   Unchanged. Take NO combo taps before then.
3. **Monday 2026-09-14 after 10:00Z, in this order:** (a) merge lane B per
   its checklist (rebase, suite on the merged tree, deploy, keep the 600 s
   grace); (b) **merge lane C behind it** — `git fetch`, number the DRAFT to
   the next free ordinal (0145 unless something landed first), rebase on
   the merged main, suite, deploy; (c) `#36` props: one prop sweep, one
   event, ~14 credits, once (Joe's answer C), then register
   `STAGED_PROP_CARD` or close the lane on a number — **not** a standing
   `ODDS_MARKETS` change; (d) nothing else touches `backend/odds/`.
4. **The census** — first session after the 10th real manual order or
   2026-11-01. Runnable as written; may not be cited for or against ADR 0143
   **or 0145**. Its Amendment 1 §A6 table is the pre-0145 record and is not
   edited.
5. **Reservations** (also in `tasks/LANES.md`): schema **v41** and ADR
   **0144** are lane B's; ADR **0145** is lane C's; main-session ADRs start
   at **0146**.

**Struck this session:** item 3 (E3 — built on lane C, above), item 6 (the
pair test — killed on the partner's reading last session; a killed item is
not an open item, and it returns only as a pre-registration).

---

## 2026-09-11 (twelfth session) — the hedge figure was called a ceiling and it is not one; the census registration can now be run as written; lane B is renumbered and still waiting on Monday

**The session's finding is that a caveat can be the flattering sentence.**
`/hedge` told Joe its lock figure was "a ceiling — the real number can only
be smaller", and CLAUDE.md said in one paragraph both that the figure was an
upper bound *and* that the recorded stake made it sit at or below the true
one, then concluded nothing shown to him was flattering. The
`measurement-skeptic` read `core/hedge.py` against those sentences and found
**at least four error terms of mixed sign**, none measured on a single row,
and the largest one — **the entry fee Joe already paid is not in
`stake_tenths` at all** (`routes.py:4318` is contracts × price; `Rung` nets
the branches against the sunk stake) — runs **optimistic**, at ~17 tenths a
contract at 41c, and is the size of the smallest floors
`Lock.is_guaranteed_profit` fires on. So a displayed lock of a cent or two
can be a true loss, and the one-sided "ceiling" was the safe error only by
luck. The registered table is Amendment 1 §A6 of the census registration:

    E1  settlement fee, H4 untested   too HIGH   unknown
    E2  sent price vs fill price       too LOW    0–10 tenths; ~0 on a one-level book — the only term the census pins
    E3  entry fee absent from S        too HIGH   ~17 tenths/contract at 41c — the largest
    E4  hedge fee at flat 0.070        too LOW    ~9 tenths × n; measured baseball k ≈ 0.035

**Words to refuse on that screen and in every doc about it:** ceiling, floor,
conservative, at least, can only be smaller/larger. It is an estimate good to
roughly a cent a contract, pinned in neither direction. **E3 is a candidate
money-path defect found by source reading, not by data** — it has no owner
and no decision yet; see open item 3.

**STATE at close.** `main` pushed, CI green, live = main (deployed with
`-e GIT_SHA=$(cat sha.txt)` and read back off `/api/health` against
`git rev-parse HEAD`); recorder writing, live quotes up, arming unchanged
(hand path armed, engine and bids dry). No new ADR and no schema change on
`main`. Odds path untouched: **the freeze to 10:00Z 2026-09-14 holds** —
`git diff --name-only 7f0f85f..HEAD -- backend/odds/ backend/scheduler.py`
is empty. **Credits: zero spent**; every live call was `GET /api/health`.
No lookup minted, no combo tap: **Arm D's frame is uncontaminated.** No open
Dependabot alerts.

### What shipped, in the partner's order

1. **The hedge copy** (merge `d14194b`). `page.tsx` no longer says "an exact
   answer"; `NOTES["upper_bound"]` (key kept — `api.ts`, `discord.py` and
   three tests read it) now names both directions in plain words and calls
   the figure an estimate; `NOTES["no_button"]` no longer claims the bet door
   is "capped at one contract" (false since ADR 0112; limits are 500/250).
   `core/hedge.py`'s "does NOT establish" list carries all four terms
   including E3, which it had never listed. Killed claims are guarded in
   `TestTheLockCaveatClaimsNoDirection` (`tests/test_hedge_positions.py`);
   verified red-then-green by restoring each old sentence (3, 1 and 2
   failures). The same one-sided restatement was removed from
   `manual_orders.py:775`, `schema.sql:2011`, `test_hedge_arithmetic.py:12`
   and `test_manual_order_venue_fill_fields.py:24,171`. CLAUDE.md's `/hedge`
   paragraph rewritten around the table above and updated for v40. ADR 0143
   §4's "remains an upper bound" is left as the historical record it is.
2. **The census registration is amended, not silently edited.**
   `docs/measurements/2026-09-10-preregistration-recorded-fill-vs-venue-charge.md`
   Amendment 1 (678 lines appended, 0 deleted, written blind by
   `pre-registrar`). The three citation errors are quoted and corrected;
   `routes.py:3959`/`:4318` are recorded as *correct, do not fix*. Four
   rulings a future session may want to overrule: (i) same statistic,
   corrected name — H1 is now `limit_price_tenths >= V` per contract and
   `sent > venue` is **price improvement, not a recorder defect**; the word
   `discrepancy` is retired; (ii) the population splits at v40 — `fills` is
   PRIMARY, `venue_avg_fill_price_tenths` is FALLBACK only when the join is
   empty, because the create-order response's side convention for a `no`
   order is assumed, not verified; a `side_convention_ambiguous` class is
   pre-declared; (iii) **§9 had no stopping rule** — one is fixed: first
   session after the 10th real manual order, or 2026-11-01, whichever first,
   checkable via `manual-orders-audit` which cannot see `fills`; (iv) §7 and
   §11.8 are **withdrawn** as contradictory and unestablished (the table
   above). §8.1 and §8.2 are both spent — the persistence arm was taken by
   ADR 0143 on the retention ground — and **the census may not be cited for
   or against ADR 0143 in either direction**; what it still buys is A7.3/A7.4.
3. **The n=68 combo fee-model reopen trigger now lives at its site** (merge
   `1985faa`): `backend/portfolio_poll.py` "does NOT establish" list, beside
   `predict_fill_fee`, with a pointer at `COMBO_TAKER_COEFFICIENT`
   (`core/fees.py:366`) — the constant at stake, not `TAKER_COEFFICIENT`,
   because every one of the 68 rows is `KXMVE`. Off this list for good.
4. **Lane B pre-staged, not merged** (`1b96b7c` on `lane-b-window-index`):
   schema **v40 → v41** in all four places, DRAFT ADR numbered **0144**. The
   partner refused a Friday rebase for a Monday merge. Its
   `test_every_version_is_accounted_for` is red on the branch by design (no
   v40 entry in its `_MIGRATIONS`; resolved at the real rebase).
5. **The binned card** moved to CLAUDE.md's "Do not rebuild these" table.
6. **Housekeeping.** Lane D's worktree and branch, the stale
   `worktree-agent-a7502ebbe85bb967f` branch, three empty shell directories
   and this session's three merged lane worktrees are gone. One empty
   directory (`.claude/worktrees/agent-a11b77117a02ff6c8`) is held open by
   the OS and is git-invisible; delete by hand or ignore.
7. **`lessons.md` archived 68.9% → 45.3%** (merge `7ac97bf`), boundary
   2026-09-08, 32 entries to `archive/lessons-2026-09-11.md`, md5-verified,
   binary move, diff is four repointed index lines and pure deletion. A stale
   `tasks/lessons.md:4306` citation in ADR 0021 predates several splits and
   was left.

### JOE'S ANSWERS, 2026-09-11 (twelfth) — both settled, in his words: "a) figure b) sure"

- **(A) One figure on `/hedge`, not a range.** Ratified. The honest
  rendering would be a range (E1/E3 push the true lock below the display,
  E2/E4 above), but a range during a live game is harder to act on and the
  gap is about a cent a contract. **One figure with the honest sentence
  stands; do not convert it to a range without a new answer from him.**
- **(B) Nothing money-touching this weekend.** Ratified. No combo taps, no
  lookups, no arming, no spend until Sunday's scheduled Arm D.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
2. **SUNDAY 2026-09-13 — Arm D, a scheduled run, not a task to plan.**
   Unchanged. Take NO combo taps before then.
3. **E3 — the entry fee is missing from `parlay_positions.stake_tenths`.**
   New, and the one candidate money-path defect this session found. It is
   named in Amendment 1 §A6.5 as *out of the census's scope*, so nothing
   measures it. It needs its own decision: whether `stake_tenths` should
   carry the entry fee (which would make `_record_combo_position` read
   `venue_avg_fee_dollars` — the same rewire ADR 0143 §4 deferred, now with
   a reason that is not cosmetic). **Order still holds: decide, do not
   clean up.** All four real fills predate v40 and have NULL venue columns,
   so a rewire today makes a mixed-basis column. Pair it with the
   `int(fill_count)` truncation on `contracts` (`routes.py:3952`), also
   unruled. Wants `kalshi-platform` on the fee semantics before any ADR.
4. **Monday 2026-09-14 after 10:00Z — three date-blocked items, in this
   order:** (a) merge lane B per its checklist — rebase (expect a real
   one), suite on the merged tree, deploy, do not trim the 600 s grace;
   (b) `#36` props: one prop sweep, one event, ~14 credits, once (Joe's
   answer C), then register `STAGED_PROP_CARD` or close the lane on a
   number — **not** a standing `ODDS_MARKETS` change; (c) nothing else
   touches `backend/odds/`.
5. **The census** — deferred to the first session after the 10th real
   manual order or 2026-11-01. Registration is now runnable as written.
   Still binding: a separate named harness, `fills` never via
   `manual-orders-audit`, a census not an estimate, no mean, no rate.
6. **The pair test — KILLED** on the partner's reading. Two pairs so far,
   one null and one conditioned, zero usable; it proposes five days of
   lookups that mint into Arm D's and #36's frames for n = 5 and wants a
   schema migration on `parlay_lookups` to get there; its justification has
   already died and been replaced once. **It comes back only as a
   pre-registration stating the decision rule and the falsifier in
   advance; then it earns its column.**
7. **Reservations** (also in `tasks/LANES.md`): schema **v41 is lane B's**;
   ADR **0144 is lane B's**; main-session ADRs start at **0145**.

**Struck this session:** item 4 (venue fill numbers — done last session;
its follow-on is item 3 above with a real reason now), item 7 (the n=68
trigger — in code), item 8 (the binned card — in CLAUDE.md).

---

## 2026-09-11 (eleventh session) — the spine named a column that does not exist, the widening was seen firing, and the index that would fix `/api/window` is built and deliberately not shipped

**The session's finding is that three separate things everyone had written
down were wrong in the same direction: they described a mechanism that was
never there.** CLAUDE.md's money-path paragraph named a database column that
does not exist. CLAUDE.md called a measurement "still unrun" that is
deliberately refused. And `widened_from`, recorded for days as never observed,
fires fine — it had been spot-checked at the wrong phase of the sweep cycle.
None of the three was a code defect. All three were the record drifting from
the thing it described, which is the failure mode this file exists to catch.

**STATE at close.** `main` pushed and CI green throughout. Commits, in order:
`e00af51` the spine corrections and the pyarrow bump, `5e3ea5f` the guard that
went red on it, `76f5e3c` the lane A merge, `52d1dd0` the NEXT.md split,
`a5b160a` this entry, `3ad6eb2` the fabricated-SHA lesson, `905bea5` Joe's
answers and the ratified gloss, then the lane D merge. **Live tracked main at
every step**, deployed with `-e GIT_SHA=` and read back off `/api/health`
against `git rev-parse HEAD` rather than inferred; recorder writing, live
quotes up, arming unchanged (hand path armed, engine and bids dry). ADRs
**0142** (exposure at the moment of a bet) and **0143** (the venue's own fill
numbers) taken; **schema v40** allocated to 0143. Odds path untouched: **the freeze to 10:00Z
2026-09-14 holds** — `git diff --name-only` against `backend/odds/` and
`backend/scheduler.py` returns nothing for every branch this session produced.
**Credits: zero spent.** Every live call was a GET on a route with no visit
registration (`/api/parlays`, `/api/window`, `/api/exposure`, `/api/health`);
no lookup was minted and no combo tap taken, so **Arm D's frame is
uncontaminated by this session.** The 300/300 attention slice was already
spent ~6 hours before the session opened. No open Dependabot alerts.

### JOE'S ANSWERS, 2026-09-11 — all three yes

Put to him as three lettered questions with a recommendation on each; he
answered "yes to all" and asked that they be saved here.

- **(A) Start a fresh session after lane D lands.** Procedural. Acted on.
- **(B) The exposure gloss at the buy button STANDS.** It replaced a false
  reassurance -- the old text promised a cap that ADR 0112 removed on his own
  instruction, and it renders **at the buy button**, which is the worst place
  in the product to carry a comforting untruth. **Now pinned in words**
  (`TestTheExposureGlossIsJoesRatifiedCopy` in
  `tests/test_manual_ticket_exposure.py`), with the same force as the #9 tab
  ledes: the ratified sentence verbatim, a worked-example guard, and a guard
  that the killed claim ("exposure cap bounds", "cannot take the whole
  bankroll") **cannot return in any spelling**. Verified by disabling --
  restoring the old sentence turns two tests red. A future session will read
  "nothing caps it" as alarming copy and want to soften it; it is not
  alarming, it is the fact, and the softer version is the one that was wrong.
- **(C) #36 props as parlay legs: SPEND THE ~14 CREDITS.** Recorded on the
  ticket (comment 5634130986). **This authorises one prop sweep on one event,
  once, after 10:00Z 2026-09-14 — and nothing else.** It does **not**
  authorise leaving props in `ODDS_MARKETS`: buying a market type costs
  credits on *every* sweep thereafter (ADR 0140), so making it permanent is a
  separate decision with a recurring bill. Then either append
  `STAGED_PROP_CARD` to `CARD_SHAPES` (one line, already built and tested) or
  close the lane **on a number**.

### READ THIS FIRST: lane B is finished, on a branch, and must NOT be merged or deployed before 10:00Z 2026-09-14

Branch **`lane-b-window-index`** (`8b02d81`, `65ab0ec`), complete, tested,
CI-clean on its own tree, **deliberately not merged**. It adds
`idx_odds_window` — a covering index for `/api/window`'s `fixture_freshness`
query, which schema v39 does not touch and which is the dominant *continuous*
read on the box (four SSR pages on load, `RefreshWhenPriced` at 3s then 10s,
`Nav.tsx` on every visible tab, plus `run_loop.py`).

**It is on a branch rather than on main for one reason: a deploy ships it.**
The boot index build is budgeted at **2-4 minutes** on live, and `main` is
kept in sync with live by habit — so a merge would very likely be deployed by
the next session, and Arm D runs **Sunday 2026-09-13**. A multi-minute boot
during a registered measurement is the kind of avoidable collision that is
obvious only afterwards. `scripts/lane_board.py` reads every local branch, so
the work is discoverable by the documented mechanism rather than by memory.

**Merge checklist, for the session that takes it after the freeze lifts:**

1. **Renumber its schema v40 to v41.** Lane B wrote 40 as a placeholder, and
   **lane D merged first and took 40** (ADR 0143, the venue fill fields), so
   40 is now allocated on `main`. `SCHEMA_VERSION`, the `_MIGRATIONS` key, the
   `schema v40` line in `schema.sql` and `VERSION` in the test all move
   together — they are ONE number. `git fetch` first and confirm against
   `SCHEMA_VERSION` rather than against this sentence.
2. Number `docs/adr/DRAFT-a-single-arm-timing-is-not-evidence.md`. It amends
   ADR 0141 — 0141 says *time it*, this says *how*. Next free ordinal is
   **0144** unless something landed first.
3. Re-run the suite on the merged tree; the branch is based on `fcca0ac` and
   main has moved a long way — lane A, lane D, the split and the answers are
   all in front of it. Expect a real rebase, not a fast-forward.
4. Deploy, and **do not trim the 600 s health grace** — it is what covers the
   boot build.

The numbers, and read the caveat with them: at live's shape (3.63M rows,
2,640 events) the statement goes **3,904-4,399 ms -> 667-797 ms**, a paired
ratio of **5.1x-6.1x across every cache regime the rehearsal box produces**.
**That is a FLOOR, not a magnitude** — the rehearsal is at worst partly cached
on a fast SSD and live is I/O-bound against 5.19 GB, which is exactly the
regime where what the index removes (~1.46M table-row fetches per call)
dominates. v39's local 3x came back as 81x on live. Cost: **71.2 bytes/row,
~263 MB** on live's 3,696,485 rows, against v39's 190 MB; a 900-row sweep goes
9.5->12.5 ms resident and 24.9->40.7 ms under cache pressure, which is
milliseconds every ten minutes to buy a read that happens every 3-10 seconds.

**The method finding is worth more than the index, and it changed a
conclusion.** The identical query over identical data read **1,283 ms in one
session and 3,904 ms in the next**, purely on page-cache residency — a 3x
swing that would have supported any "ratio" between 1.6x and 15x had the two
arms been timed in separate runs. Every arm is now timed **round-robin in one
process**. Under that method a drafted finding did not survive: a claimed
222-vs-184 ms win for the five-column index over a cheaper four-column form is
really **2-9%**, and the record now says so and names dropping
`book_updated_ms` (25 MB back, cheaper writes) as the first thing to give up
if live shows memory pressure. That is the DRAFT ADR.

### Item 5 is CLOSED — `widened_from` fires, and the reason nobody had seen it

Over four minutes on live, same commit, same slate:

    04:00Z   tonight 0/7, tomorrow 0/7, 48h 0/7   bare call: widened_from None
    04:04Z   tonight 0/7                          bare call: widened_from 'tonight',
                                                  window -> tomorrow, 4 of 7 cards

The mechanism works end to end and `widened_words` renders the settlement
caveat. The 04:00Z reading is **also correct** — every window was empty, so
the ladder fell through and returned `tonight` unwidened, which is the
documented branch.

**What actually moved is freshness.** `kickoff_outside_window` held at ~434
across both reads while `stale_consensus` fell **256 -> 36 -> 31**: a sweep
landed. So the desk's card yield is a **sawtooth whose period is the sweep
cadence**, and a mechanism that only has somewhere to widen into in the
minutes after a sweep reads as dead to anyone who spot-checks it. This is the
**third** distinct reason this screen has been empty — the menu (refuted,
ninth session), the clock (ninth session), and now freshness — and the first
that is time-varying. Written to `lessons.md` as the pattern. **Deliberately
NOT written as a measurement doc**: three reads is G = 1, it establishes a
mechanism and cannot support a rate, and a `docs/measurements/` file would
invite someone to quote one.

**The Freshness copy gap the partner suspected does not exist.** `/api/window`
reported `fixtures_upcoming: 428`, `fixtures_fresh: 0`, so `nothingFresh` is
true and the block speaks even with `stale_consensus` at 0. Joe's screen at
04:00Z would have told him why it was empty. The ninth session's fix works;
that loop is closed.

### The three corrections to the record

1. **CLAUDE.md's money-path paragraph was wrong three ways.** `manual_orders`
   has **no `fill_price_tenths` column** — it is `limit_price_tenths`, written
   at **intent** time (`store/manual_orders.py:648`) from
   `OrderRequest.fill_price_tenths` (`kalshi/orders.py:298`). `OrderOutcome`
   has no such property, so nothing the venue returned was ever in it. The
   cited `routes.py:3957` is `:3959` and points at a different table anyway
   (`parlay_positions.stake_tenths`, via `contracts * fill_price_tenths` at
   `:4318`). **Each verified against source, not taken on report.** The claim
   that matters is untouched: the recorded basis is the ask the desk sent,
   both errors run cautious, the hedge figure is an upper bound. **The
   pre-registration's §0.1/§2 repeat the same three errors and are NOT yet
   fixed** — see open item 3.
2. **The `anchored_on_sharp` split is deliberately refused, not unrun.**
   `scripts/inspect_live_db_decisions.py:234` declines to compute it by
   design: a query carrying a decision rule is not a dump. "Still unrun"
   implied an owner who does not exist. Rewritten rather than deleted, so the
   question survives without the phantom task.
3. **`test_has_callers.py` is 122 tests in 198.7s**, not the 300s reported to
   me. Measured before writing it down.

### What else shipped

- **The exposure line, inside `ManualTicket` — ADR 0142, rank 1.** ADR 0112
  removed all five brakes and those caps were the only consumer of Joe's
  exposure figure in the product; nothing has read it since, and `/parlays` —
  where all four real combination bets were placed — fetches no position data
  at all. `GET /api/exposure` is a new minimal route rather than a reuse of
  `/api/bets`, which drags `bets_record(limit=200)`, `pass_summary` and
  `lockout_until` along for a buy button. All **seven** mount points get it
  from one edit. Verified on live: 200 in 0.27s, 401 without the cookie.
  **It informs and never blocks** — `canConfirm` does not read the exposure
  state, re-verified here by mutation rather than inherited (adding
  `exposure?.refused !== true` to `canConfirm` turns
  `test_the_confirm_predicate_does_not_read_the_exposure_state` red). A gate
  there would be a sixth ceiling and a reversal of ADR 0112. Unreadable
  renders the server's refusal words, never `$0.00`.
- **JOE-GATED, and it is the one thing here that wants his eye: the glossary's
  `exposure` definition changed.** It said *"The exposure cap bounds that
  total, so one bad night cannot take the whole bankroll."* That has been
  **false on the hand-bet path since ADR 0112**, and this definition renders
  **at the buy button** — a false reassurance, in the flattering direction, at
  the worst possible place. It now says nothing caps it on a hand bet, with a
  worked example. Kept because it is a correctness fix; the wording is his to
  overrule.
- **pyarrow 19.0.1 -> `~=25.0`, and the pip-audit ignore list is now EMPTY.**
  25 and not 23 because GHSA-rgxp-2hwp-jwgg is fixed in 23.0.1 and `~=23.0`
  would still admit the vulnerable 23.0.0. Verified the way CI verifies it:
  `pip-audit --strict` with zero ignores reports clean, and `seed_demo` +
  `store.publish` runs green under 25.0.1. pyarrow is imported only by
  `store/publish.py`, a CI-only CLI, so nothing on the serving path touches
  it and the bump cannot affect a boot.
- **NEXT.md split at 76.6% -> 37.2%**, the lowest any split has been taken at.
  Seven entries to `archive/next-2026-09-11.md`, date boundary at 2026-09-09,
  md5-verified, index lines in the same edit.
- **Two lessons**: the sweep-phase confound, and the reachability ratchet's
  blind spot.

### The guard that went red, and why that is the system working

Emptying the pip-audit ignore list turned
`test_marts.py::TestThePipAuditIgnoreListIsPinned` red on CI. **The guard is
right and was not weakened** — its own message says a removal "should mean the
bump landed, which is the good case, and still deliberate", so
`EXPECTED_IGNORES` is now the empty set with the trail in the comment.
Verified by disabling: adding a fake `--ignore-vuln` to `ci.yml` turns it red
again, so an empty expectation is still an assertion and not a vacuous pass.

**I missed it pre-push** by narrowing the test search to files that also
mention `CLAUDE.md`; `test_marts.py` does not. The grep that would have found
it is the unnarrowed one. Pattern: **narrowing a "what tests pin this?" search
by an unrelated predicate is how a pinned fact gets missed.**

### Two lane-hygiene facts worth keeping

- **Lanes share the scratchpad directory.** Lane B had a scratch file
  (`mutate.py`) overwritten mid-run by another lane. Worktrees were
  unaffected, but scratch files need unique names.
- **Do file moves in BINARY.** A text-mode round trip on Windows rewrites
  every line ending, so a seven-entry move renders as a whole-file diff and
  the only property a reviewer can check — that nothing outside the moved
  range changed — disappears. The split's diff is 20 insertions and 1,729
  deletions, which is the shape that can be inspected. In the split log.

### Lane D — the venue's own fill numbers are now kept, ADR 0143, schema v40

`record_outcome` stamped `status`, `kalshi_order_id` and `error_text` and
dropped `fill_count`, `average_fill_price_dollars` and
`average_fee_paid_dollars` on the floor. Those three survive **only in
`fills`, on a ~3-month window**; `manual_orders` is permanent. Joe's first
real fills were 2026-09-08, so the venue-side truth about them starts
disappearing around December, and every hand bet placed before the fix would
have been permanently un-reconstructable.

    venue_fill_count              REAL      OrderOutcome.fill_count
    venue_avg_fill_price_tenths   INTEGER   dollars_to_tenths, then is_valid_price
    venue_avg_fee_dollars         REAL      Decimal, refusing negative/non-finite

**The fee is in DOLLARS, and that is a followed precedent rather than a new
exception.** `fills.fee_actual` is already `REAL` dollars and
`portfolio_poll.parse_fill` states why outright. A second reason applies here
and not to the price: **the fee on the C0 capture is `"0.0014"` — 1.4 tenths,
which `dollars_to_tenths` writes as `1`, a 29% understatement of the only
number on the row saying what the venue charged.** Storing it in tenths would
have destroyed the fact the column exists for. Verified against
`schema.sql:966` and `portfolio_poll.py:218` rather than taken on report.

**`None`-not-`0`, across three states that are genuinely different:**

    dry run        NULL   NULL   NULL
    rejected       NULL   NULL   NULL
    zero-fill IOC  0.0    NULL   NULL

The zero-fill row is the whole point: a real observed `0.0` beside two NULL
money columns, because "nothing filled" is not "nothing was charged at a price
of nothing". A price of `0` is refused outright — `dollars_to_tenths("0.0000")`
is `0` and a `0` in a price column reads as a settled loser, not an absence.
A fee of `0.0` is kept, because unlike a price, zero is a fee the venue can
charge. **Re-verified here by mutation**: dropping the `is_valid_price` arm
turns two tests red.

`record_outcome` keeps its contract — the derivation sits **before** the `try`
whose only declared failure is `sqlite3.Error`, pinned by a source-ordering
assertion, so an unexpected exception cannot be reported as a database
failure on an order whose money is already spent.

**`/hedge` is UNCHANGED by this and remains an upper bound.**
`_record_combo_position` still computes `stake_tenths` from the sent ask.
Rewiring it to `venue_avg_fill_price_tenths` is a money-path change with its
own decision; this commit only makes that decision *possible*. Deferred
explicitly in ADR 0143 §4.

**Three corrections lane D made to its own brief, all verified:**
`OrderRequest.fill_price_tenths` is at `kalshi/orders.py:299` (`:298` is the
decorator); the census registration repeats **two** of the errors corrected in
CLAUDE.md, not three — its `routes.py:3959` citation is **right**, and it has
a *different* third error nobody had noticed, a preamble tying its decision to
"schema v39", which has since been taken by `idx_odds_event_commence`; and the
venue's `fill_count` already reached `parlay_positions.contracts` via
`routes.py:3952`, so "the venue's numbers reach nothing" would have been too
strong. **The registration is still unfixed** — amending a registration is not
a lane's call. See open item 3.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
2. **SUNDAY 2026-09-13 — Arm D, a scheduled run, not a task to plan.**
   Unchanged. Take NO combo taps before then; every lookup mints into its
   sampling frame.
3. **The recorded-fill-vs-venue-charge census.** Partner's call, adopted:
   **do the unconditional parts now, defer the census itself to a trigger.**
   Branch 8.1 was the CLAUDE.md correction — **done this session**. Branch 8.2
   is item 4 below. What remains is a four-row census, deferred to **the first
   session after the 10th real fill, or 2026-11-01, whichever comes first**:
   the `fills` window from 2026-09-08 does not close until ~December, so
   perishability buys two months and n≈12 is worth reading where n=4 is worth
   arguing about. **Still binding when it runs**: not via
   `manual-orders-audit` (`fills` is in `FORBIDDEN_TABLES`); a separate named
   harness; a census, not an estimate — no mean, no rate, at any n.
   **The registration's §0.1/§2 still repeat the three
   `fill_price_tenths`/`OrderOutcome`/`:3957` errors corrected in CLAUDE.md
   this session.** Fix them before the census runs, not after.
4. **Persist the venue's own fill numbers — DONE this session.** ADR 0143,
   schema v40, merged. What remains is the follow-on it makes possible and
   does NOT authorise: rewiring `_record_combo_position`'s `stake_tenths`
   from the sent ask to `venue_avg_fill_price_tenths`, which would make
   `/hedge`'s figure exact rather than an upper bound. That is a money-path
   change and needs its own decision — ADR 0143 §4 defers it deliberately.
5. **`#36` props as parlay legs — ANSWERED, and blocked on the freeze.**
   **Joe said spend the ~14 credits (2026-09-11).** One prop sweep, one
   event, once, after 10:00Z 2026-09-14 — not a standing `ODDS_MARKETS`
   change, which would bill every sweep forever. `STAGED_PROP_CARD` is built,
   tested and deliberately not in `CARD_SHAPES`; enabling is one line and is
   correct only after a sweep has bought prop rows. `ODDS_MARKETS` on live is
   `'h2h,spreads'`. ~14 credits on one event after 10:00Z 2026-09-14, then
   register the card or close the lane on a number.
6. **The pair test** — blocked to 2026-09-13, needs a `parlay_lookups`
   pre-existence column. **Its old justification is dead**: it said it was only
   worth a migration if item 3 produced one, and v39 shipped for the index
   instead. Make it fund its own schema change or drop it.
7. **The combo fee-model reopen trigger** (n = 68) — standing no. Its home is
   a comment at the site that would fire it, not this list.
8. **The binned card** — **struck.** A closed decision, not open work: Joe
   binned it 2026-09-09 and the reason is permanent (`bet_estimates` holds one
   row and it is `is_study_row = 1`). Its home is CLAUDE.md's "Do not rebuild
   these" table, and it should be moved there rather than carried here again.

**Struck from the list this session, all on the partner's reading and none of
them work:** the ninth session's 0c, 0d and 0e (notes, not tasks — 0d says
"measured, closed" in its own text and 0e says "do not open without a
symptom"; 0e's home is the docstring of `inspect_live_db.py
parlay-candidates-timing`), the `pip-audit` pyarrow ignore (done), item 5
(done, above), and the `anchored_on_sharp` phantom (deliberately refused, not
owned).

**Closed this session:** item 5, the pyarrow ignore, rank 1 (exposure line),
rank 3 (spine corrections), rank 6 (NEXT.md split), rank 7 (two lessons and
the strike). **No ADRs are owed** — 0142 is taken and lane B's draft is
numbered at its merge.

---

## 2026-09-10 (tenth session) — one scan per request, a quote that says when it was read, and a warning that went silent as the outage got worse

**The session's finding is that "add props as parlay legs" has two gates and
only one of them costs money.** Everyone had it costed as a feed decision:
a prop cannot be a leg unless a sportsbook price was bought for it, and buying
a market type costs credits on every sweep forever. True, and not the binding
constraint. **Every parlay recipe declares which markets it draws from and all
seven decline props** — `TEAM_MARKETS_ONLY` (`backend/core/ladder.py:138`), six
recipes, plus one spreads-only — a free gate nobody had written down. And the
paid gate is **NOT open** -- a claim to the contrary was published and
withdrawn the same session, and the withdrawal is the more useful finding.

**THE CORRECTION, MEASURED ON LIVE. Read this before planning any prop work.**
`CANDIDATE_SQL` admits five MLB prop markets (`backend/parlays.py:611-613`)
and the prop arm resolves them to legs with a real Kalshi rung -- the code
path is open end to end. **There are no rows.**

    ODDS_MARKETS on live                  'h2h,spreads'
    newest MLB prop row in fair_prices    600.5 hours old (~25 days)
    prop rows in the last 24h / 7d        0 / 0
    h2h / spreads rows in the last 24h    65,032 / 71,044
    usable legs in tonight's pool         7, of which props: 0

So **"the query admits this market" and "the desk holds this market" are
different claims**, and the first was reported as the second. Both gates are
shut, the expensive one binds after all, and there is no free test: buying
prop rows changes `ODDS_MARKETS` / the prop sweep, which costs credits on
every sweep thereafter and edits `backend/odds/`, **frozen to 10:00Z
2026-09-14**. The 25-day-old rows cannot stand in -- they are outside the
freshness rule and outside the candidate scan's own two-hour floor.

Joe answered **B1** ("run the free baseball prop test") against the wrong
premise. He has been told. The corrected choice is the one the ticket body
already had: **~14 credits on one event after the freeze lifts, or close the
lane.**

**STATE at close.** `main` = **`7f0f85f`**, pushed, CI green (run
34520670775 on `5042d15`, and the one docs commit after it). Four commits:
`a5b7460` the pre-registration, `1fdba22` the three lanes, `5042d15` the
session files, `7f0f85f` a lesson. **Live = `7f0f85f`**, deployed with
`-e GIT_SHA=` and read back off `/api/health` rather than inferred; recorder
writing, live quotes up, arming unchanged (hand path armed, engine and bids
dry). Full suite on the tree as committed: **6,938 passed, 10 xfailed, 0
failed** (10m29s); ruff and tsc clean. Odds path untouched: **the freeze to 10:00Z 2026-09-14 holds** — nothing
under `backend/odds/` or `backend/scheduler.py` was read for edit or written.
**Credits: zero spent.** No lookup was minted, no combo tap taken, nothing
authenticated was called against Kalshi except one read-only `flyctl ssh` for a
library version — **Arm D's frame is uncontaminated by this session.**
ADR 0140 taken. Dependabot: no open alerts, and the `cryptography` blind spot
is closed (below).

### THE 503 HAS A CAUSE, AND IT IS A MISSING INDEX — schema v39

Chasing why the desk was still answering 503 `read_budget_exceeded` an hour
after the cache-eviction incident below, `inspect_live_db.py
parlay-candidates-timing` gave the numbers:

    whole candidate scan                        73,526 ms   (494 rows)
    odds_snapshots MIN(commence_ms) GROUP BY    26,719 ms   (703 rows)
    fair_prices rows inside the scan window            848  of 10,112,298
    odds_snapshots rows                          3,696,485
    live database                                   5.19 GB

**848 rows in the window and 73 seconds to return them**, so the row count was
never the problem. The plan named it: `SEARCH o USING AUTOMATIC PARTIAL
COVERING INDEX` — SQLite building a temporary index at query time because no
suitable one exists.

**`CANDIDATE_SQL`'s own comment claims an index that has never existed.** It
says the plan is a seek "with it, plus `idx_odds_event_commence`". Live has
`idx_odds_commence`, `idx_odds_event` and `idx_odds_sport_commence`, and no
`idx_odds_event_commence`. The 2026-08-26 fix was half-shipped: the subquery
restriction landed and the index did not.

**It did not land because it was deliberately removed, and the reasoning was
wrong in an instructive way.** `schema.sql` recorded it: with the index and
without it, the step reads `SEARCH ... (odds_event_id=?)` — "identical shape",
so it "changed no plan" and would cost write amplification for nothing. Both
observations are true. **`EXPLAIN QUERY PLAN` reports the access method, never
how many rows the method touches.** The subquery takes `MIN(commence_ms)` per
event; `idx_odds_event` is `(odds_event_id, market, fetched_ms DESC)`, so the
minimum can only be found by reading every row of the group — ~1,400 per event
— and fetching the column from the table. With `commence_ms` second, the
minimum is the first entry.

Reproduced locally at live's shape (800 events x 1,400 rows), warm, best of
three: **503.9 ms without, 167.5 ms with**, the two plans differing only in the
index name. That 3x is a **floor** on the live win, not an estimate of it: the
local box is CPU-bound with the table in memory and live is I/O-bound against a
5.19 GB file, which is the regime where rows-touched dominates.

Shipped as **schema v39** (`idx_odds_event_commence`), with the measurement
stored beside the CREATE in `schema.sql` and pinned by
`tests/test_odds_event_commence_index.py` — **the index and the recorded reason
are guarded separately**, because an index whose justification was deleted is
one somebody removes again on the same argument as last time.

Two existing tests went red and both were name-pinning rather than claim-pinning:

- `test_no_duplicate_leading_column_index_was_reintroduced` asserted the index
  did NOT exist. **Inverted, not deleted** — the original rule (do not pay
  write amplification for nothing) is intact; what changed is what counts as
  evidence of "nothing", and a plan diff cannot supply it.
- `test_odds_snapshots_is_searched_not_scanned` failed on an **improvement**:
  the refused-leg kickoff lookup went from `SEARCH o USING INDEX
  idx_odds_event` to `SEARCH o USING COVERING INDEX idx_odds_event_commence`,
  which stops touching the table at all. A guard that names an implementation
  calls a better plan a regression.
- And `test_the_odds_seek_comes_from_the_restriction_not_a_new_index` was
  passing for no reason at all: `"idx_odds_event" in step` is a **substring**
  of `idx_odds_event_commence`, so it could not have failed whichever index
  the planner chose. Rewritten to assert the seek, which is the durable claim.

**The write-amplification objection stands and is being paid deliberately:**
~52 bytes/row locally, about **190 MB** on live's 3,696,485 rows. Bought
because the desk was 503-ing in front of Joe, and because a covering seek
should *reduce* cache pressure here — it stops pulling ~1,400 table pages per
event into the page cache that is the binding resource on this box.

**VERIFIED ON LIVE, same session.** Deployed `2e66f36`, migration ran at boot,
index confirmed present and chosen by the planner. Re-ran
`parlay-candidates-timing` on the freshly-booted (i.e. COLD) container:

                                          before      after     factor
    odds_snapshots MIN GROUP BY        26,719 ms   327.9 ms       81x
    whole candidate scan               73,526 ms  11,712 ms      6.3x

and the route itself, which is what Joe touches:

    first call after deploy   503 read_budget_exceeded (25 s)  ->   3.95 s
    warm                      1.5-3.3 s historic best          ->   0.49-0.82 s

**So the cold-start 503 is gone, and the warm desk is roughly 3x faster than
its best previously recorded state.** The local 3x was a floor, as predicted;
the live subquery win is 81x because live is I/O-bound and the index removes
~1,400 table-page reads per event rather than CPU work.

**What this does NOT establish:** nothing about `/api/board`, `/api/slate` or
the recorder, which were never timed against this. And the 6-of-7 cards seen
after the deploy versus 4-of-7 before is the evening slate filling out, NOT an
effect of the index -- the index changes speed and cannot change which legs
are eligible.

### Two corrections to the front door, both verified rather than reasoned

1. **The ADR 0117 box's `cryptography` warning is stale and has been removed
   from the live reading.** It said `requirements.txt:9` still pins a version
   inside alert #15's vulnerable range. The pin is `~=50.0`, the range is
   `>= 42.0.0, <= 48.0.0`, and the running container reports **50.0.1** (read
   over `flyctl ssh`; the `Error: The handle is invalid.` after a good read is
   the known artifact). The 44 -> 50 bump (ADR 0124, 2026-09-09) closed it. The
   query is still blind to `cryptography`, so keep verifying from the
   container — but there is nothing outstanding to verify *against* today.
2. **The decision queue is empty.** All 32 sub-issues of map #3 were closed;
   only the map itself was open. So the map produces no frontier this session,
   and the only decisions outstanding are the ones put to Joe below.

### Ticket #12 is superseded, not reopened — and the convention is now written down

Joe's 2026-09-10 *"i want to bet on props for parlay legs"* reads as a reversal
of #12's *"option A — he does not really bet props; drop them from the brief"*
(2026-09-02) and **is not one**: #12 asked about props as **picks**, the new
want is props as **legs**, and a prop he would not bet alone is still a leg he
would combine. **#36** carries the new question; #12 keeps its answer, is left
closed, and now points at #36. Neither was edited to agree with the other.

`docs/agents/issue-tracker.md` gained the rule, with this as the worked
example: **never reopen a ticket Joe has answered** — reopening rewrites the
record of what he said and when, which is the thing the map exists to keep.
Check first whether the two questions are actually the same one; usually they
are not, and saying so is most of the work.

### What shipped — `1fdba22`

- **One candidate scan per request.** `build_ladder_payload_widening` called
  `ladder_candidates` once per window until one built a card, and everything
  `ladder_candidates` reads before applying the window is horizon-independent:
  `CANDIDATE_SQL` binds `(floor_ms, floor_ms, now_ms)` and never the horizon
  (the kickoff bound is applied in Python after `fetchall()`), the per-event
  `kalshi_markets` loop is keyed off the **unfiltered** scan, and
  `combo_eligible_events` takes `now_ms` only. Split into `CandidatePool` /
  `candidate_pool`, read once and filtered per window; the windows are strictly
  nested, so that is provably the same answer.
  **The duplication was bigger than item 0b claimed** — `1 + N` statements per
  window, not one query per window. Measured on a three-game bed that widens
  once: **two scans and six per-event reads before, one and three after.**
  A pool carries the `now_ms` / `max_odds_age_ms` it was built for and
  `ladder_candidates` refuses a mismatch rather than answering for the wrong
  minute. That guard was **decoration until its own test existed** — the first
  mutation run came back green.
- **The combo quote now says when it was read.** `quoted_ms` and
  `quote_max_age_ms` travel with the priced payload, the threshold **passed
  from the route** (`staleness.max_kalshi_quote_age_s`) rather than re-derived,
  so it cannot drift from what `serialise.py` marks `price_is_current` against.
  `QuoteAge` renders a ticking age and marks itself past the limit. It
  **relabels and never blocks** — ADR 0112 removed all five ceilings on a hand
  bet and a staleness gate on the buy would be a sixth.
- **`Freshness` stopped going silent as the outage got worse.** See the lesson;
  the gate now also fires on `/api/window`'s fixtures-upcoming-with-none-fresh,
  and the zero-count branch no longer says "all 0 candidate sides were refused
  on age".
- **ADR 0140** — the parlay leg pool is odds-feed-driven.

### The `test_stale_exit.py` guard, and why it was rewritten rather than loosened

It pinned the literal `stale === 0 || unbuilt === 0` while its docstring stated
the claim: a banner that fires on a working screen is one the reader learns to
skip. The replacement **preserves that claim exactly** and the test went red
anyway, because it was pinning characters. Rewritten to assert the claim, plus
the half it was missing, and it additionally refuses the old predicate's
return — **strictly stronger than what it replaced.** Lesson written.

### Guards verified by disabling

    widening no longer shares the pool          4 red
    pool reuse guard (`now_ms` mismatch)        2 red   (green on first pass)
    threshold dropped from the priced payload   1 red
    buy control given a `disabled` prop         1 red
    Freshness gate back to the row-only test    3 red

### Joe has two letters and one FYI — artifact published

<https://claude.ai/code/artifact/b2289b51-be1e-4b12-af59-b09b0db876df>

- **(A) the `/parlays` lede wording — ANSWERED A1, 2026-09-10: "hardly
  anyone" stands.** Given the replacement in place, the two shard-1 books
  behind it and two alternatives, he kept it. So #9's sentence is his approved
  copy in full again rather than a correctness patch awaiting an answer, and
  changing it is his call. Recorded on ticket #9 and in the two files that pin
  the sentence verbatim.
- **(B) props as parlay legs**, re-put with the two-gates finding: try it free
  in baseball now (recommended), wait and buy the NFL measurement, or close the
  lane. The correlation limit is stated in the artifact rather than discovered
  after.
- **(C) FYI, no answer wanted:** his "take the trade" answer is **withdrawn and
  not being acted on**, per the partner's ruling. Do not re-ask it. ADR 0110
  dates the lever to 2026-09-28 regardless, so nothing is lost.

### Still open, in order

0c. **COLD START IS FIXED, AND THE RESIDUAL IS NAMED.** The desk warms its own
   read path at boot (`scripts/warm_read_path.py`, run backgrounded and
   **disowned** by the entrypoint). Measured on live across three deploys:

       cold boot, before            20.5 s   (25 s read budget -- it barely fit)
       warm-up itself                9.9 s   (logged: "[warm] ... warmed in Ns")
       first request, after          0.81 s
       warm                          0.50 s

   **The residual: a request arriving DURING the warm window still waits.** The
   warm starts once uvicorn is healthy (~13 s in) and runs ~10 s, so roughly
   the first 25 seconds after a boot are unprotected. That is acceptable
   because a deploy is a deliberate act and Joe is not tapping inside it --
   but it is not "solved", and an unlucky Fly-initiated restart could still
   land there. Do not report it as eliminated.

   **Two things that make this checkable:** the boot log line carries the
   elapsed time AND the leg count, so a warm-up that read an empty database is
   distinguishable from one that worked; and `tests/test_warm_read_path.py`
   runs the script as a subprocess by path, which is the only way to catch the
   class of bug that shipped here (see below).

0e. **The whole candidate scan is still ~10 s on a genuinely cold box**, which
   is what the warm-up now absorbs rather than removes. If the desk ever feels
   slow again this is the number to attack; there is no symptom today, so this
   is a note rather than a task. `inspect_live_db.py parlay-candidates-timing`
   is the instrument. The subquery is no
   longer the cost (327.9 ms of it); what remains is `fair_prices` and the
   joins. It is comfortably inside the 25 s budget now and there is no
   symptom, so this is a note rather than a task -- do not open it without
   one. `inspect_live_db.py parlay-candidates-timing` is the instrument.

0d. **THE COLD-START 503 WAS NOT THE WIDENING, AND THAT IS MEASURED
   RATHER THAN SUSPECTED.** Deployed `7f0f85f` and read `/api/parlays` three
   times immediately after:

       attempt 1 (cold)   503 read_budget_exceeded   25.0s
       attempt 2          200, 4 of 7 cards          10.8s
       attempt 3 (warm)   200, 4 of 7 cards           1.5s

   **`widened_from` was `None` on both successes** — `tonight` built four
   cards, so the widening loop never ran and the 503 landed on a request that
   took **one** `ladder_candidates` scan. The ninth session's item 0b read the
   two events as coinciding by construction; they do not. A cold container
   against a 10M-row database blows a 25s budget on a single scan, which is
   the same page-cache effect as the 74.8s-cold / 2.15s-warm measurement in
   `lessons.md` — the 5GB file does not fit the ~1.4GB cache and a fresh
   machine has none of it.

   So the dedup shipped in `1fdba22` is right on its own terms and buys
   nothing here. **Do not write it up as the fix, and do not chase the
   widening further.** The real question is a cold box serving a 25s budget:
   warm the candidate path on boot, raise or stage the budget for the first
   request after start, or accept a 503 on the first tap after a deploy and
   say so on screen. Not chosen — it is a design call and it wants
   `runtime-realist` on what actually runs at boot before anyone picks.

   **Joe-visible consequence, worth knowing before he taps:** the first
   `/parlays` load after any deploy is likely to fail, and a retry ten
   seconds later works. Every deploy has always done this; it was read as a
   one-off in the ninth session and it is not.

B1. **STAGED AND WAITING ON DATA, NOT ON CODE.** Joe chose B1; the free test
   did not exist (see the correction above). What was built instead:
   `STAGED_PROP_CARD` in `backend/core/ladder.py` -- a complete, tested,
   **deliberately unregistered** prop card, staged the way `NFL_PROP_SERIES`
   was in `8d5dd1c`. `tests/test_staged_prop_card.py` proves it builds, takes
   one leg per fixture, and refuses a lottery leg.
   **Enabling it is one line -- appending it to `CARD_SHAPES` -- and that line
   is correct only AFTER a sweep has bought prop rows.** Registering it now
   puts a card on Joe's screen that reads "needs 2 fresh games and the slate
   has 0" forever, which reads as a thin slate rather than as a market the
   desk does not buy.
   Two things the machinery already had, and neither needed writing:
   `min_leg_probability` exists for exactly this card (its own comment calls
   it required on any card admitting props) and is set to 0.20, worst case
   ~125x; and `_best_per_game` is an explicit "structural same-game guard", so
   the correlation risk raised with Joe cannot occur however the recipe is
   tuned.
   **The remaining question is entirely about the feed**, is not free, and is
   blocked to 10:00Z 2026-09-14 -- ~14 credits on one event, then either
   register the card or close the lane on a number. ADR 0140 is why this was
   always a feed decision.

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged, and
   still carrying the eighth session's disclosure.
3. **The recorded-fill-vs-venue-charge census.** Registered this session:
   `docs/measurements/2026-09-10-preregistration-recorded-fill-vs-venue-charge.md`.
   **Read the registration before running it — two things in it are binding.**
   It may NOT be implemented by adding a join to `manual-orders-audit`
   (`tests/test_inspect_live_db.py` lists `fills` in `FORBIDDEN_TABLES` and is
   right to be absolute); route it through a separate named harness, as
   `2026-09-09-fee-alarm-replayed-over-every-hand-fill.md` did. And it is a
   **census, not an estimate** — no mean, no rate, at any `n`; per-row output
   ordered by `submitted_ms` ascending and by nothing else.
   **Both decision branches are unconditional, so this decides nothing** — it
   captures a fact before the ~3-month `fills` window drops it, which is a
   different and smaller reason. The `/hedge` "exact" wording was already
   corrected in CLAUDE.md this session and a clean result does not restore it.
4. **Total-exposure line at the buy button** — and the partner's design call
   changes the shape: put it **inside `ManualTicket`** so all six mount points
   get it from one edit, fed by a small dedicated route. `open_positions`
   (`backend/bets.py:502`) is served only by `GET /api/slate`, and `/parlays` —
   the screen all four real combination bets were placed on — fetches none of
   it. The cheap `/slate` prop-threading covers the screen he does not buy on.
5. **Check `window.widened_from` on live on a weekday morning.** Still never
   observed firing. A GET, costs nothing, five minutes inside any lane.
   **And do not repeat the item's own reasoning**: the widening runs only when
   the caller names no horizon, so the 2026-09-10 histogram (taken with
   explicit horizons) says nothing about how often it fires.
6. **The pair test, re-specified** — unchanged, blocked to 2026-09-13, still
   needs the `parlay_lookups` pre-existence column first. Only worth a
   migration if item 3 produces a schema v39 anyway.
7. **The combo fee-model reopen trigger** (n = 68) — standing no. Unchanged.
8. **`pip-audit` pyarrow ignore**, **the binned card** — unchanged.

**Closed this session:** the ninth session's item 0b (scan dedup shipped; the
`widened_from` observation survives as item 5), item A (withdrawn, not
deferred — see (C)), item B (superseded by #36), the ninth session's item 5
(`Freshness`, was a conjecture, was true, fixed), item 6 (NFL prop fixture
capture — done in `8d5dd1c`; KXNFLANYTD had 0 open events, which is a venue
state and not a task). **The second owed ADR is not owed** — it was conditional
on the sharp-anchor re-ask surviving, and the re-ask is withdrawn.

---

## 2026-09-10 (ninth session) — the parlay screen was empty on the clock, not the menu, and NFL prop ladders need no parser

**Joe opened with "I have to make parlays more wide and variety options with
over unders, props, underdog, etc." The variety was never the bound.** Measured
on live at 16:4xZ: the `tonight` pool held **one** game and all seven cards read
"needs N fresh games and the slate has 1", while the SAME slate, the same
markets and the same minute built **six of seven** one day out. The excluded
histogram is `kickoff_outside_window: 440`, `stale_consensus: 9` — so 440 of 449
excluded legs were cut by the clock, and **adding totals or props would not have
filled one of those cards.**

**STATE at close.** `main` = **`76cc97c`**, **pushed**, CI green
(run 34510972323). Three commits: `8d5dd1c` the NFL prop capture, `d56638a`
the horizon widening, `76cc97c` this state line. Full suite on the tree as
committed: **6,908 passed, 10 xfailed, 0 failed** (20m07s); ruff and tsc
clean. **Live = `76cc97c`**, deployed 2026-09-10 ~18:0xZ with
`-e GIT_SHA=`, read back off `/api/health` rather than inferred; recorder
healthy, live quotes up, arming unchanged (hand path armed, engine and bids
dry). No open Dependabot alerts on the push rescan — noting that the query
still cannot see `cryptography`, so that is a clean *listing*, not a clean
*tree*. Odds path untouched: the freeze to 10:00Z 2026-09-14 holds. No ADR
taken, two owed (below). Credits: **zero spent** — the capture is
unauthenticated `/events`, the histogram and the post-deploy checks are GETs
of `/api/parlays`, and no lookup was minted, so Arm D's frame is
uncontaminated by this session. Odds path
untouched: the freeze to 10:00Z 2026-09-14 holds; nothing under `backend/odds/`
or `backend/scheduler.py` was read or written. No ADR taken, and two are owed
(below). Credits: **zero spent** — the capture is unauthenticated `/events`, the
histogram is a GET of `/api/parlays`, and no lookup was minted, so Arm D's frame
is uncontaminated by this session.

### Joe's two answers, and one of them should be re-asked

Batched as (A)/(B); he answered both in one line, as usual.

- **(A) "take the trade"** — accept losing the sharp anchor to admit totals.
  **Re-ask this.** He answered BEFORE the histogram existed. The trade is
  ADR 0110's: dropping `eu` is the only lever that admits totals, and
  `SHARP_BOOKS = {pinnacle, betfair_ex_eu, betfair_ex_uk, matchbook}`
  (`runner.py:153`) contains no `us`-region book, so under `us` alone the sharp
  set is **empty** and sharp anchoring was **73.0%** of the pinned record. He
  traded that away to fix an empty screen that this session then showed was
  empty for an unrelated reason. Dated 2026-09-28 regardless, so nothing is
  lost by putting it again with the histogram attached.
- **(B) "i want to bet on props for parlay legs"** — props are UNKILLED, and
  this **overturns map ticket #12** (resolved by Joe 2026-09-02: *"option A —
  he does not really bet props; drop them from the brief"*). The narrower want
  is legs, not picks. #12 needs reopening or superseding; it is currently
  closed and says the opposite.

### What shipped

- **`8d5dd1c`** — the NFL prop capture. `scripts/capture_nfl_prop_fixture.py`
  and `tests/fixtures/events_nfl_props_nested.json`, unauthenticated, no
  credits, nothing minted. **The finding is that NFL needed no new parser:**
  the MLB grammar `"Player: N+"` and the join identity `floor_strike == N - 0.5`
  hold **2,029 of 2,029** across KXNFLPASSYDS (253), KXNFLRECYDS (1,160) and
  KXNFLRSHYDS (616) — three magnitudes, so it is a property of Kalshi's prop
  ladder rather than of baseball. KXNFLFIRSTTD is 362 markets with **zero**
  `floor_strike`, bare-name subtitles and `strike_type = 'structured'`: no
  rung, joins to nothing. KXNFLANYTD had 0 open events and is recorded as
  **unmeasured, not tested**. `props.py` split into `MLB_PROP_SERIES`, staged
  `NFL_PROP_SERIES` and `PROP_SERIES_NO_STRIKE`; **`PROP_SERIES` is unchanged**,
  so live behaviour did not move.
- **The horizon widening.** An unnamed window tries `tonight` and widens only
  if it builds no card at all; a **named** window is never widened. The
  widening announces itself in `window.widened_from` / `widened_words`, and the
  words carry the settlement caveat — Joe's rule was never about the window, it
  was *"I'd want to see my parlays finish out by the time the evening games
  end"*, so widening past it has to say the card cannot settle tonight.
  `WindowPicker` renders it. If every window is empty the `tonight` payload is
  returned unwidened, so the refusal blames the right clock.

### The mutation that passed, and why the bed was wrong

The first route test **passed a mutation that removed the guard entirely.** Its
bed was an empty database: with nothing to build, every window refuses, so a
route that wrongly widened still returned `tonight` and looked correct. Rebuilt
on a slate seeded with games *only* tomorrow — the only bed that can tell the
two paths apart. Pattern written to `lessons.md`: **a guard test needs a bed
where the unguarded code would produce a DIFFERENT answer, and "both paths
refuse" is not that bed.**

    widen silently                          3 tests red
    widen despite an explicit window        1 red
    never widen                             1 red
    return the widest window when all empty 1 red
    merge NFL into PROP_SERIES              2 red
    loosen SUBTITLE to admit bare names     1 red
    invert the join identity to N + 0.5     3 red

### Two ADRs owed

1. **The parlay leg pool is odds-feed-driven.** The join runs `fair_prices` ->
   find a Kalshi market, never the reverse (`backend/parlays.py:686-737`). That
   one sentence is why every "add a market type" request is a **feed** decision
   wearing a UI request's clothes, and it will be re-derived at full cost
   otherwise.
2. **The sharp-anchor trade**, if (A) survives re-asking. It changes what
   "fair" means on every card in every sport and cannot be a config edit.

---

## 2026-09-10 (eighth session) — a combination CAN be sold back, five screens said it could not, and three of my own claims were withdrawn

**Joe opened with "I WANT TO ACTUALLY BUY ONE COMBINATION FOR A FUTURE GAME
THROUGH THE DESK." The answer is no, and it is the venue rather than us.**
ADR 0138's horizon fix was real; fixing it revealed that nobody quotes those
books. What the session actually found is unrelated to the question and worth
more: **two `KXMVECROSSCATEGORY-SHARD1` books carried resting YES bids**, so
the universal five screens asserted — "you can enter and you cannot exit" — is
false.

**STATE at close.** `main` = **`7301129`**, pushed. `a2e690d` CI green
(run 34487598739). **Live = `158a90c`** — behind main by both commits.
Odds path untouched: the freeze to 10:00Z 2026-09-14 holds; nothing under
`backend/odds/` or `backend/scheduler.py` was read or written. No ADR taken.
One measurement document, and it is a disclosure rather than a finding.
Credits: **52 of 700** on budget day 20260910; four attention registrations
bought only two sweeps (24 credits) because the ten-minute cadence refused the
rest; attention slice 24 of 300.

### THE HEADLINE: a resting YES bid exists

```
KXMVECROSSCATEGORY-SHARD1-S202662C6B3CFEC6-5D18E47B21C
   yes_dollars [['0.0980','10.00']]   no_dollars [['0.8610','10.00']]   created 13:43:30.222636Z
KXMVECROSSCATEGORY-SHARD1-S2026D379AC93CBF-7772CD6AC5F
   yes_dollars [['0.0570','10.00']]   no_dollars [['0.9020','10.00']]   created 13:45:34.187576Z
```

One level a side, `depth=5` requested so the shape is complete. Both **minted
one to three minutes before being seen quoted** — a fresh combo book can be
two-sided. Found by a **public unauthenticated** `/markets` + `/orderbook`
read via `urllib`, no credential, no `lookup_combo`: it created nothing and
added nothing to any sampling frame. Neither is desk-minted — one leg is
`KXEPLGAME`, a league this desk cannot build, and neither ticker appears in
`parlay_lookups`.

**An existence proof kills a universal and supplies no rate.** Five surfaces
were corrected in `7301129` (buy ticket `combo_note`, the 422 acknowledgement
refusal, the bid route's 422, `NOTES["unquoted"]`, and the `ManualTicket`
fallback / `PriceOnKalshi` note / `/parlays` lede). Each now reports the two
books, **names the size** — ten contracts at a single price, because "an exit
exists" without "it is this small" trades one overstatement for its mirror —
and claims **no frequency**, which Arm D measures 2026-09-13. New sourced
constants `COMBO_EXIT_SHARD_YES_BID_{DATE,BOOKS,SIZE_CONTRACTS}`;
`COMBO_EXIT_CENSUS_SHARD_BOOKS_READ` **stays zero** on purpose (it counts
shard books inside the census of forty, and these two were not in it).

**It shipped before Sunday rather than after, and the error ran in the
CAUTIOUS direction** — Joe was told a combination is less exitable than it may
be. That is the flattering direction, which is exactly why it would have sat
for months. The `/parlays` lede is Joe's ratified copy (#9, 2026-08-27) and
one word moved: "nobody" → "hardly anyone". **Joe-gated: the final phrasing.**

### THREE CLAIMS I MADE AND WITHDREW — read this before re-deriving any of them

1. **"Moneyline combos get quoted, spread combos never do."** `measurement-skeptic`:
   **UNSUPPORTED**. My `p = 0.00095` did not reproduce (it is 0.000275; I summed
   the hypergeometric over the wrong margin). The unit is the **mint, not the
   tap** — no minted ticker in the record has EVER changed status between
   reads, including one across 6h44m — so the denominator is 13/26 vs 0/11
   (p = 0.0029), not 15/31 vs 0/17. **The parts do not agree**: 64% of the
   spread arm sits at leg counts with no moneyline comparator; at 3 legs it is
   9/17 vs 0/4 (p = 0.083), within `safe` 9/14 vs 0/2 (p = 0.175).
2. **"The horizon separates — tonight is quoted, beyond tonight never."** The
   `tonight` control arm **re-read a ticker already known to be priced**, so it
   was fixed by construction. Also confounded structurally: every
   beyond-tonight leg the desk can offer is NCAAF, because the feed buys near
   kickoff and tomorrow's MLB is not in the pool. No tap fixes that.
3. **"69% of visits open onto stale odds, so the screen is broken at the
   moment of decision."** That is the **first-stamp** reading;
   `visit-freshness`'s own docstring distinguishes it from `last_age_ms`,
   "what the visit bought itself by staying". `RefreshWhenPriced.tsx` already
   buys attention on open and re-renders when `fixtures_fresh` rises, in ten
   to fifteen seconds, and `ParlayCards`'s `Freshness` block already says why
   the desk is empty. **The item was cut, not built.**

**The confound that survives all of it, and it is unresolvable in this table:**
`lookup` **creates** the market when the combination does not exist
(`backend/kalshi/combos.py`). "Spread combos are not quoted" and "**self-minted
tickers** are not quoted" predict identical data, and the spread-bearing
recipes (`lottery` 6 legs, `longshot` = the three *least* likely games,
`short_spreads`) are exactly the combinations no human would have built.
`parlay_lookups` has **no pre-existence column**. `pre-registrar` scored the
two YES-bid books against this at LR ≈ 1.004 — no evidence either way, since
the desk's two touched tickers sit in a scanned page of ≥1,000.

### What shipped

- **`a2e690d`** — `book_empty` now passes `leg_details_for(selected)`
  (`backend/parlays.py`); 30 of the first 46 live rows carry bare tickers while
  the return payload twenty lines below built `commence_ms` off the same
  `selected`. Verified by disabling: mutation red on `KeyError: 'side'`, priced
  twin green. Item 0's stopping rule replaced (below). Two lessons.
- **`7301129`** — the five copy surfaces, the guards moved with the fact, and
  `docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`.

**Guards moved, never weakened.** Three tests pinned the killed sentence *in
words* so it could not be softened out; they now pin the replacement with the
same force and additionally assert the universal cannot return
(`"cannot exit" not in detail`). `test_the_exit_census_copy_names_its_scope`
required the copy to say "nothing is known" about the shard — itself now a
demand for a false statement — and now requires it to disclaim the **rate**.
Verified by disabling: reinstating "and you cannot exit" turns
`test_kxmve_is_refused_without_the_acknowledgement` red.

### THE DISCLOSURE — read it before writing Sunday's result

`docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`.
Two looks at Arm D's registered population, three days early. **α, population,
stopping rule and decision rule are UNCHANGED**, and the one inferential test
(Arm A S2 Fisher, α = 0.01) has a population neither look touched. What is
damaged: the answer is known in advance, and **my twelve taps minted into the
newest-first frame Arm D samples** — `lookup_combo(allow_market_creation=True)`
is an outward-facing write, which "it spends no money" did not reveal. Three of
those rows returned tickers earlier taps had returned, so at most twelve and
known to be loose. Dual reporting with/without desk-created rows is required.
`EXIT_PRACTICAL` scores as met at exactly its boundary and **fires nothing** —
an unregistered look does not trigger a registered rule, so ADR 0078 stays shut.

### Still open, in order

0b. **THE WIDENING'S WORST CASE IS 3x `CANDIDATE_SQL` UNDER A 25s READ
   BUDGET, AND IT WAS OBSERVED FAILING ONCE.** `build_ladder_payload_widening`
   runs one `ladder_candidates` per window until one builds, so a night where
   `tonight` is empty costs three scans in a single request. The first call
   after the 2026-09-10 deploy returned **503 `read_budget_exceeded`**
   (`budget_ms` 25000); retries were 200 in 1.5-3.3s, so it was a cold
   container rather than a standing break. **The two conditions coincide by
   construction**: the cold box is most likely right after a deploy, and an
   empty `tonight` is what triggers the extra scans. The local suite cannot
   see this -- it never runs cold against a 10M-row database.
   Bound it: cache the candidate pool across horizons (one scan, filtered
   three ways, since the windows are nested), or widen at most once. Prefer
   the cache -- `ladder_candidates` already takes `horizon` only to set an
   upper kickoff bound.
   **Also still unobserved: the widened branch has never fired on live.** At
   16:4xZ `tonight` held 1 game and built 0 cards; by 18:1xZ it held enough
   to build 4 of 7, so the fallback correctly did nothing and has been proven
   only by test. Check `window.widened_from` on a real weekday morning before
   believing the screen behaves as designed.

A. **RE-ASK JOE (A): the sharp-anchor trade, with the histogram attached.**
   He said "take the trade" — drop `eu`, lose Pinnacle and Betfair, admit
   totals — BEFORE the 2026-09-10 histogram showed the cards were empty on
   kickoff time rather than on market type. `SHARP_BOOKS` has no `us`-region
   member (`runner.py:153`), so under `us` alone the sharp set is EMPTY and
   sharp anchoring was 73.0% of the pinned record. Dated 2026-09-28 by
   ADR 0110 regardless. **Do not act on the answer he already gave.**

B. **Joe wants props as PARLAY LEGS (2026-09-10), which overturns map ticket
   #12.** #12 is CLOSED carrying his 2026-09-02 answer *"option A — he does
   not really bet props; drop them from the brief"*. Reopen or supersede it;
   a closed ticket asserting the opposite is the front door lying. The
   narrower want is legs, never picks.

C. **The NFL prop lane is buildable but its coverage is unmeasured, and the
   prior is bad.** `NFL_PROP_SERIES` is staged and tested (`8d5dd1c`);
   enabling is ONE edit with two halves — `PROP_SERIES = {**MLB, **NFL}` AND
   a sport-aware `prop_market_keys()` (`backend/odds/client.py`, FROZEN to
   10:00Z 2026-09-14; it is a flat list whose length IS the price, so three
   NFL keys there would be requested on every MLB event too). Half alone is
   broken both ways. **Measure first:** ADR 0079 put primary-only coverage at
   48 of 263 MLB prop markets (18%), NFL ladders are longer, and 35,448 of
   35,448 alternate rungs carry no Under and cannot be devigged. One event,
   ~14 credits, after the 14th. If coverage is as bad as MLB's, kill the lane.

0. **THE PAIR TEST, RE-SPECIFIED — and do not start it before Sunday.** The old
   rule said "take it again **when a moneyline card is quoted**", which
   conditions the retake on one arm's outcome; followed, it produced a
   moneyline arm 2-of-2 quoted **by construction**. Honest accounting: two
   pairs, one null (07:09Z, both arms empty), one conditioned (13:51Z). New
   rule: fixed order, **18:00Z daily for five days**, record every pair
   including double-empties. **Add the pre-existence column first** or the
   pairs cannot separate the two stories. Every lookup mints into Arm D's
   frame, so not before 2026-09-13.
1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged, and
   now carrying the disclosure above.
3. **Total-exposure line at the buy button** (partner's rank, sharp-bettor's
   finding #3). On the 66-of-69-invisible-positions argument ONLY — the depth
   argument died when row 49's 2,928 contracts became 152 in forty minutes.
   `backend/bets.py::open_positions` already computes a venue-sourced number
   that refuses honestly; the job is to move it above the buy control.
4. **The priced combo quote should carry its read age and mark its own verdict
   stale.** n = 1: the same ticker went ask 302 → 329 tenths, depth 2928 → 152,
   verdict "+0.3% EV. Rare" → "−7.9% EV. Don't." in forty minutes. Justified on
   cost asymmetry, not on n. **It relabels, it never blocks** — disabling the
   buy control is a new ceiling on a hand bet and ADR 0112 forbids it.
5. **`Freshness` is gated `stale === 0 || unbuilt === 0`** and would go silent
   on a pool empty because nothing was ever fetched — the one state that most
   needs it. Unobserved; a conjecture from reading, worth one test that builds
   that pool.
6. **NFL prop fixture capture** (`KXNFLANYTD`, `KXNFLFIRSTTD`, a yardage
   series). One unauthenticated `/events` pull, capture only. Bottom; drop first.
7. **The combo fee-model reopen trigger** (n = 68) — standing no. Unchanged.
8. **`pip-audit` pyarrow ignore**, **the binned card** — unchanged.

**Joe-gated: the `/parlays` lede's final wording** ("hardly anyone" vs "rarely
anyone" vs his own). Everything else in the correction is correctness and
shipped without asking.

**Two contamination notes for whoever reads these instruments next.** Four
`desk_attention` POSTs at 13:50Z and 14:01Z were an AGENT, not Joe — they are
in this week's dwell record and `visit-freshness` will count them as visits.
And `parlay_lookups` rows 47–58 are agent taps, twelve of them, all on
2026-09-10.

### Lessons written

Two, both pattern-level: **a stopping rule that names an outcome manufactures
that outcome**, and **an operation that reads can also write — "it spends no
money" is not the test for whether it is inert.**

## 2026-09-10 (seventh session) — a combo tap now prices the window the card was built in, and the desk has a spreads-only card Joe chose

**Found by doing what Joe did.** He tapped "Buy it on Kalshi" on a "Through
tomorrow" card at 22:22 PT and every leg was refused as "started, or past
tonight's last game". None had started. The lookup was pricing every card at
`tonight` whatever window built it, guessing the reason, and writing no row.
Kalshi minted for future games all along (fixture minted 5 days out, live id
2 priced a next-day leg): the refusal was ours.

**STATE at close.** `main` = **`158a90c`**, pushed, **CI green
(run 34447293327)**; full suite on main before the docs commit: **6870 passed,
10 xfailed, 0 failed** (10m29s). **Live = `158a90c`, schema v38,
machine `7812601a239428` unchanged** (deploy run 34448064455;
migration v37 -> v38 at boot in under a second (07:04:26Z, both log lines carry the same second; backend healthy after 13 s, health passing 07:04:49Z)). Demo untouched. Odds path
untouched: the freeze to 10:00Z 2026-09-14 holds; `git diff 324a53f..main --
backend/odds backend/scheduler.py` is empty and `fly.live.toml` changed only
in comment lines.

Two ADRs: **0138** (a lookup prices the window the card was built in; a
refusal is recorded, schema v38; the sentence never guesses; the copy says
who quotes a combination), **0139** (Two short spreads is a rule Joe chose).
One registration: `docs/measurements/2026-09-10-preregistration-totals-market-credit-cost.md`.
Three lanes ran in parallel worktrees, all merged, worktrees and branches
removed. Eight reviewer agents ran before the plan (partner, two explorers,
kalshi-platform twice, sharp-bettor, measurement-skeptic, pre-registrar);
Joe answered three lettered questions in one line: recipe **A**, keep all
six cards, write the registration.

### THE HEADLINE: the horizon now travels with the tap — ADR 0138

`POST /api/parlays/lookup` takes `horizon` (validated against `HORIZONS`
with the GET's own 422 words), `price_card_on_kalshi` passes it to
`ladder_candidates`, and the screen sends the ladder payload's `window.key`
from `ParlayCards` through `PriceOnKalshi` to `lookupParlay`. An absent leg
is now classified from the sportsbook's own kickoff: "has started" only when
`commence_ms <= now`, "kicks off after the '<window words>' window ends —
pick a wider window" when beyond the horizon, "is not a leg this desk
serves" otherwise. **Schema v38** rebuilds `parlay_lookups` so `status`
admits `'refused'`, and the resolve step records the refusal (legs, horizon,
the words) before re-raising; the `book_empty` branch now writes the YES
side and both level counts into `error`, so an empty NO side is no longer
indistinguishable from an empty book. Copy: "Kalshi itself almost never has
anyone selling this combination" and "Nobody has offered this price" are
gone — Kalshi quotes the minted combination itself (a resting NO bid is the
ask you pay, 33 of 40 books carried one); nobody bids to buy it back, so the
exit is the outcome. "Try again shortly" is gone too: **0 of 6 repeat groups
on live ever flipped from empty to quoted, out to 80 minutes.**

**A merged query was corrected the same hour, and it is the lesson in
miniature.** Lane 1's kickoff lookup LEFT JOINed a `GROUP BY odds_event_id`
over all of `odds_snapshots` — `MATERIALIZE o`, `SCAN odds_snapshots` on
every refused tap, the plan `CANDIDATE_SQL` was measured at 15 s with on
2026-08-26. It is now a correlated scalar subquery seeking `idx_odds_event`,
the statement is a function the plan test imports, and
`tests/test_ladder_query_is_indexed.py` pins plan and value.

**Rehearsed in the container on the real rows before the deploy**: the
exact statements from the new `db.py` against a scratch file holding the
live table's 42 rows (attached `mode=ro`, nothing copied but that table):
digest identical through forward, replay, undo and forward again; the old
CHECK refuses `'refused'`, the new one accepts it; the index survives;
2 ms. No 5 GB copy this time, on purpose — see the lesson below.

### The recipe — ADR 0139

`short_spreads` / "Two short spreads": `markets={"spreads"}`,
`max_spread_margin=3.5` (a new `Recipe` knob; a spread's `point` is the
book's number and always negative, so the bound is on `-point`),
`min_legs=max_legs=2`, likeliest-first, one leg per fixture from
`_best_per_game`. Not pushed to the phone. The leg row now shows a kind tag
("SPREAD −3.5", "WIN", "PROP <line>") from `leg.market`/`leg.point`, which
were on the wire and never drawn; `spread` joined the glossary.

**Census before the build, read off live at 06:10Z (48h window):** 14 spread
legs, **9 at 3.5 or shorter across 6 fixtures** (MLB 1.5/2.5 runs, NFL and
NCAAF 3.5), `p_conservative` 0.33–0.57, odds 34–48 min old because no page
was open. Every one was `stale_consensus` on the route at that hour, which is
the feed on its hourly floor, not a defect.

**Its Kalshi quote rate is unmeasured and the prior is unfavourable**: on
live, **0 of 11 lookups containing a spread leg came back quoted, against 12
of 28 moneyline-only** — self-selected taps, confounded with league and date
(the 11 include every NCAAF row and mostly six-leg cards), so a correlation
and not a mechanism. The falsifying pair is one lookup of this card and one
of a moneyline card on the same slate in the same minute. Not yet taken.

### Focus 2 decided, most of it by the record rather than by Joe

- **Totals: not this season at `us,eu`.** The multiplier is exactly 1.5
  (`sweep_cost = markets x regions`), and the largest budget day on record
  (496, 2026-09-05, no NFL) becomes **744 against 700**. **ADR 0110 already
  refuses totals** and dates the only lever (drop `eu`, 3 credits a call) to
  2026-09-28 behind two preconditions. Below the feed, totals do not exist:
  no series constant, no subtitle parser, not in the runner's derived link
  set, no pricing branch, not in `CANDIDATE_SQL`. The credit look is
  registered (§0 gate: totals have no consumer — already true; one look after
  10:00Z 09-14 on budget day 20260913; edges 560 / 700 fixed).
- **NFL props: undiscovered.** `PROP_SERIES` is MLB-only, zero `KXNFL*` prop
  rows on live, and FIRSTTD/ANYTD carry no strike so the props join has
  nothing to join on. Needs one unauthenticated `/events` capture before any
  parser is written against memory.
- **MLB props are dead on live** — last `fair_prices` write 2026-08-16, 0
  rows in 24h. Not a recipe source.
- **Long ladder and Longshot stay** (Joe's answer). The sharp-bettor's
  argument that their only distinguishing feature is more legs, and legs are
  hold, is on the record for the next UI ticket.

### Verified by disabling

    Lane 1 horizon pass-through      1 mutation   2 tests red
    Lane 1 started/after-window fork 1 mutation   4 red
    Lane 1 refused status            1 mutation   1 red
    Lane 1 book_empty detail         1 mutation   2 red
    Lane 2 margin filter             1 mutation   1 red
    Lane 2 spreads-only markets      1 mutation   1 red
    main   kickoff query plan        the merged query itself was the red case

### Still open, in order

0. **THE FALSIFYING PAIR FOR THE SPREAD CARD.** One lookup of "Two short
   spreads" and one of a moneyline card, same slate, same minute, read off
   `parlay-lookups-tail`. Until then the card's Kalshi quote rate is a prior,
   not a measurement. **Taken once at 07:09Z after the
   deploy, and it did not separate anything**: `short_spreads` (NYY −1.5,
   LAR −3.5) and `safe` (three moneylines, all on the 10th and 11th) minted
   within four seconds of each other and BOTH came back `book_empty` with
   `yes_levels=0 no_levels=0` (rows 45 and 46; 43 was the same safe card a
   second earlier). A pair where both sides are empty is consistent with
   "spread combos are never quoted" and with "nothing is quoted at 00:09 PT
   on a future-game combo".

   **THAT STOPPING RULE WAS WRONG AND IT WAS FOLLOWED — 2026-09-10, eighth
   session.** It read "take it again when a moneyline card is quoted", which
   conditions the retake on one arm's outcome. Taken under it at 13:51Z, the
   moneyline arm came back 2 of 2 quoted **by construction of the rule, not
   by observation**, and the tap order shows the mechanism: three moneyline
   taps, then the spread tap last, once the trigger was satisfied. The
   resulting "clean separation" is uninterpretable and was withdrawn the same
   session. The honest accounting of this test is **two pairs taken, one null
   (07:09Z, BOTH arms empty), one outcome-conditioned (13:51Z)** — and the
   first is the one that counts.

   **The replacement rule, unconditioned:** tap the moneyline card and the
   spread card **in a fixed order within the same minute, on a schedule fixed
   in advance** (18:00Z daily for five days), and record **every** pair
   including the ones where both arms come back empty. Five unconditioned
   pairs are worth more than the 48 rows now on the table. Do not start it
   before Sunday's Arm D look — every lookup mints a market into that
   measurement's own sampling frame (see
   `docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`).

   **And a confound that no number of pairs can settle**, found by
   `measurement-skeptic` the same session: `lookup` **creates** the market
   when the combination does not already exist
   (`backend/kalshi/combos.py`), and the spread-bearing recipes (`lottery`
   at 6 legs, `longshot` = the three *least* likely games, `short_spreads`)
   are exactly the combinations no human would have built in the Kalshi app.
   So "spread combos are not quoted" and "**self-minted tickers** are not
   quoted" predict identical data, and `parlay_lookups` records no
   pre-existence flag. Add that column before running the pairs, or the
   pairs cannot separate the two. Evidence already against the second story:
   two shard-1 books minted at 13:43:30Z and 13:45:34Z carried resting YES
   bids when read from ~13:46Z, so a *fresh* mint can be two-sided within
   three minutes.

   The mint, not the tap, is the unit: **no minted ticker in the whole
   record has ever changed status between reads**, including one re-read
   across 6h44m, so repeat taps of a ticker carry zero information and the
   row denominator (31/17) is inflated. At the mint denominator it is 13 of
   26 moneyline-only against 0 of 11 spread-bearing — a correlation, still
   not a mechanism, and it does not survive matching on leg count (3 legs:
   9/17 vs 0/4).
   **The tap Joe asked for is verified on live**: under "Next two nights"
   the safe card (NCST, LOU on the 11th, NYY on the 10th — every leg beyond
   tonight) minted `KXMVECROSSCATEGORY-SHARD1-…AC3CA136377` and answered
   `book_empty` in 2.4 s (row 43); the same legs under "tonight" answered
   409 "kicks off after the 'games kicking off before tonight's slate ends'
   window ends -- pick a wider window" and wrote row 44, `status =
   'refused'`, `horizon = tonight` on every leg. Attention registered at
   07:08:14Z and the consensus was fresh by 07:09:18Z. Small gap seen in the
   rows: a `book_empty`/`priced` row's legs carry no `horizon` (only the
   refused branch adds it) and no `side`/`label` on this path — read
   `legs_for_position` before relying on either.
1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
   After it: the registered totals look, and the `window_status` covering
   index candidate (unchanged).
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged.
3. **The cold-cache cost of the ladder query is 75 s.** Measured this session
   in the container: `ladder_candidates` at `tomorrow` took **74.8 s** on a
   page cache a research agent had just flushed with two full-table
   `GROUP BY`s over `fair_prices`, then **2.15 s** warm; `/api/parlays`
   answered 503 `read_budget_exceeded` at 25 s on both windows in between.
   The read budget (ADR 0135) held. Not a regression — see the lesson — but
   it is the number a first tap after any full-table read will pay.
4. **The boot health grace is 600 s.** Unchanged.
5. **`position_state` has not fired on live.** Unchanged.
6. **The combo fee-model reopen trigger** (n = 68) — the partner's standing
   no: a constant that cannot change a decision does not get a session.
7. **`pip-audit` pyarrow ignore** — trigger only, unchanged.
8. **The binned card** — do not rebuild, unchanged.

**Joe-gated: NOTHING.** All three questions were answered in-session.

### Lessons written

One, pattern-level: a read-only full-table scan on live evicts the page
cache, and the next reader pays for it — a census goes through the indexed
path the product uses or a bounded key range, a 503 at the read budget
minutes after a live read is the read and not a regression, and a subagent
told to read "read-only" will still flush the cache unless the instruction
bounds the rows.

**And one about my own procedure.** I merged a lane whose query I had not
run `EXPLAIN` on, and it carried the exact plan this repo had already
measured and fixed once. The plan test existed for the sibling statement;
the new statement was not held to it until I looked. A new query against a
growing table gets its plan pinned in the same commit that introduces it.

## 2026-09-10 (sixth session) — the ladder floor was OOM-cycling the recorder; the fix shipped, and /hedge now says what it cannot see

**Found by measuring the thing the last entry said was slow, from the outside,
before touching it.** Item 0 said the 9-day floor scanned 6.5M rows and
`/api/parlays` paid it twice. It was worse: the scan's `ROW_NUMBER()` runs
under `temp_store = MEMORY`, so 6.5M rows became ~1 GB of resident memory in
BOTH processes, and the 2 GB box had restarted three times in five hours
before this session began. The partner's ranking and the sharp-bettor's craft
review both redirected the hedge-alert ask to coverage first, and the coverage
read was 0 of 1.

**STATE at close.** `main` = **`324a53f`** plus this entry, pushed; **CI green
on `324a53f` (run 34437142296)**; full suite on main before the docs commit:
**6845 passed, 10 xfailed, 0 failed** after one timezone fix. **Live =
`324a53f`, schema v37, machine `7812601a239428` unchanged** (deploy run
34437560202; migration `v36 -> v37` at boot in 172 s). Demo untouched. Odds
path untouched: the freeze to 10:00Z 2026-09-14 holds, and `credits-day` shows
no attention row during either probe — a server-side fetch of an SSR page does
not register attention, only the client's `/desk-attention` POST does.

Four ADRs: **0134** (the ladder scan keys on the confirmed stamp; v37 partial
index), **0135** (an abandoned request stops executing; `API_READ_BUDGET_MS`),
**0136** (the hedge screen says what it cannot see), **0137** (the phone says
which legs are live, on a schedule — amends ADR 0078 D2 on Joe's word). Six
lanes ran in parallel worktrees, all merged; worktrees and branches removed.

### THE HEADLINE: the box was dying every hour, and opening `/parlays` could kill it on demand

`docs/measurements/2026-09-10-the-ladder-floor-oom-cycles-the-recorder.md`.

Timed from outside with a minted read-only cookie (the MCP Chrome tab group
carried no session cookie, so no browser-side paint timing exists — say so if
you cite this): `/api/window`, `/api/signal`, `/api/parlays`, `/api/slate` all
**500 at exactly 30 s** (Next's rewrite-proxy timeout; uvicorn keeps executing
after Next hangs up, so abandoned queries pile up), `/parlays` unanswered at
180 s. Three minutes later the kernel killed the runner at **1.13 GB** and then
uvicorn at **1.88 GB**, and the machine rebooted. The runner's own log
(`loop-rss`) had carried the attribution since the v36 deploy at 22:52Z:
RSS **196 MB -> 1.10-1.23 GB** per pass, `candidate_ms` **83 -> 3,549-9,454**,
over the same ~440 rows; boot lines at 00:32Z, 01:04Z, 03:18Z; a
`PassDeadlineExceeded` at 23:33Z. Nobody had read that column.

**The fix, and why not the obvious one.** Narrowing the floor back was ruled
out by item 0 itself. The predicate now reads
`(f.computed_ms >= ? OR f.confirmed_ms >= ?)` — exact, because a confirmed
stamp is never older than its frozen one — served by a **partial** index
`idx_fair_market_confirmed ON fair_prices(market, confirmed_ms DESC) WHERE
confirmed_ms IS NOT NULL`, which holds **614 rows** on live. The plan is a
`MULTI-INDEX OR` with two seeks; with the index dropped the `computed_ms>?`
term vanishes and the existing plan test goes red. The 9-day constant is gone;
the floor is `max(8 x max_odds_age_ms, 2h)` again. Rehearsed in the container
on a paced copy: the index build reads the whole 10.1M-row table once,
**181.8 s cold**, so the boot health grace went **120 s -> 600 s** with the
measurement beside it in `fly.live.toml` (the container's image cannot
pre-build an index its code does not know). Live built it in 172 s.

**After, on the warm box:** `/api/parlays` **1.1 s**, `/api/slate` 0.6 s,
`/api/board` 0.27 s, `/api/hedge` 0.13 s, every SSR page under 2.2 s; the
runner at **189 MB, 72-75 ms** over 434 rows; zero OOM lines since. The
first post-boot reading had `/api/window` at 20 s — that was the cold page cache
after the reboot and the 5 GB rehearsal copy, not a second defect: replayed on
live it is **0.95 s**, 0.91 of it one `GROUP BY` over `odds_snapshots`.

Two independent brakes shipped beside the query fix, on the partner's ruling
that their failure modes differ from the query's: the runner **builds the
ladder only when a card could be sent** (`Alerter.parlay_cards_could_send`,
so the change-alert debounce still advances on real builds), and every
per-request API connection carries a **25 s progress-handler budget** that
answers 503 `read_budget_exceeded` instead of piling up behind a proxy that
already gave up (`API_READ_BUDGET_MS`, under Next's 30 s).

### The hedge screen covered 0 of 1 live positions, and now says so

Read off live at 03:25Z: the venue held ONE open combination (17.74 contracts,
$9.69) bought in the Kalshi app, absent from `parlay_positions`; the one
recorded position (id 1, the $1.64 BOS/NYY/LAD combo) had **settled `no` at
01:40Z** in `venue_settlements` while still reading `open` with three
`pending` legs, because `resolve_from_venue` reads only `kalshi_markets.result`
and the venue had not finalized the leg markets (and the result pass runs
inside the full pass that kept dying). ADR 0136: `/api/hedge` now carries
`unrecorded_at_venue` (KXMVE tickers in the latest **ok** positions poll with
no open row — the membership-of-latest-complete-observation rule), per-position
`at_venue` and `venue_settlement`, and the screen renders the quote age beside
every leg price (it was in the payload and never drawn). No auto-close: which
leg lost is not knowable from the combo's settlement. Verified on live after
the deploy: position 1 renders `dead`, `at_venue: false`, settlement `no`, BOS
`lost`, NYY `won`, LAD `pending`; the venue list is `[]` because the $9.69
combo settled between 03:25Z and 04:41Z (`row_count 0`).

### The push Joe chose — ADR 0137, amending ADR 0078 D2

Asked which push he wanted, Joe chose the **symmetric "legs in play"
statement**: once per ticket per budget day when a watched game is in play,
every pending leg's venue bid with its quote age, "N of M legs live", the
sentence "No figure locks" when N > 1, the lock figure only when N = 1 and one
exists, `not_advice` and `upper_bound` verbatim, record order, the parlay
colour. **Identical template on a good day and a bad day** — the sharp-bettor's
argument that carried it: an alert that fires only on bad news is a nudge by
construction; one that fires on a schedule carries no information in its
arrival. Kind `position_state`, key `position_state:{id}:{day_start_ms}`, own
ceiling of 4/day, own counter. A forbidden-words test pins the transport. The
watcher spends nothing metered (existing test still green). **Not yet observed
firing on live** — no position was in play after the deploy.

The sharp-bettor's other findings, recorded for the next UI ticket, not built:
the de-risk headline (a joint built on the unmeasured 0.05/0.02 correlation
nudges) is the least defensible number on the page and should go; the
five-column ladder does not fit a phone at the moment of decision (contracts,
cost, worst case; the two branches behind a tap); no total exposure line; the
combo's own live quote and the absence of a resting YES bid are never shown.

### Verified by disabling

    Lane A runner gate       3 mutations   3 red (7 tests)
    Lane B v37 predicate     3 mutations   3 red   + one vacuous test rewritten before it could pass for nothing
    Lane C read budget       2 mutations   2 red
    Lane D coalesce          1 mutation    1 red
    Lane E1 coverage facts   5 mutations   5 red   + one isolation test added when a mutation showed two clauses untested apart
    Lane E2 the push         4 mutations   4 red

### Still open, in order

0. **A COMBO TAP REFUSES EVERY FUTURE-GAME CARD, AND LEAVES NO RECORD.** Joe's
   screenshot, 22:22 PT 2026-09-09: the "Through tomorrow" SAFE card (NYY,
   LAR, PHI, all kicking off on the 10th) tapped "Buy it on Kalshi" and got
   "these legs cannot be priced right now ... no longer on the desk's slate
   (its game has started, or it is past tonight's last game)" for all three.
   Cause, from the code: `POST /api/parlays/lookup` carries no `horizon`
   (`backend/api/schemas.py` ParlayLookupRequest), the route calls
   `price_card_on_kalshi` without one, and it re-runs `ladder_candidates` at
   `DEFAULT_HORIZON = "tonight"` (`backend/parlays.py`, `price_card_on_kalshi`
   -> `ladder_candidates(conn, now_ms=..., max_odds_age_ms=...)`), so any leg
   past 4am is absent from the pool and `resolve_requested_legs` refuses it
   with a sentence that guesses "started". The refusal is raised BEFORE
   `_record_lookup`, so `parlay_lookups` has no row for it (live still ends
   at id 42, 2026-09-09 15:12Z). Also stale: the card copy "Nobody has
   offered this price" / "almost never has anyone selling this combination"
   — Kalshi quotes the minted market itself (6 of the last 8 lookups
   `priced`, 2 `book_empty`); the entry/exit conflation ADR 0078's amendment
   corrected. Prompt for the session that fixes it is in the 2026-09-10
   session's closing message and repeated here in short: carry `horizon`
   from the ladder through the request to the lookup and validate it against
   `HORIZONS`; record a refused lookup; make the sentence say what is known;
   correct the copy; ask kalshi-platform what decides `book_empty` on a
   minted combo. **Read on live 2026-09-10 05:5xZ, for the fix and for what
   Joe asked next:** `combo_eligible_events` (3,648 rows, refreshed
   04:36Z) spans 26SEP09..26SEP21 (1,016 legs on 26SEP12, 357 on 26SEP13),
   so "Next two nights" is inside Kalshi's own combinable window and the
   only refusal was ours; and the list already carries `KXNFLSPREAD` (142),
   `KXNFLTOTAL` (142), `KXNCAAFSPREAD`/`KXNCAAFTOTAL` (118 each), NFL
   props (FIRSTTD 110, RSHYDS/RECYDS/PASSYDS 97, ANYTD 94). Joe wants
   spreads, totals and props in parlays. What blocks it: `ODDS_MARKETS =
   "h2h,spreads"` (`fly.live.toml:486`, odds path, frozen to 10:00Z
   2026-09-14, and the multiplier is exactly 1.5 (`sweep_cost = markets x
   regions`, `backend/odds/budget.py:66-68`, 4 -> 6 at `us,eu`), ADR 0110
   already refuses totals this season because the largest budget day on
   record (496 credits, 2026-09-05, no NFL) becomes 744 against the 700 cap,
   and the only lever that admits totals is dropping `eu` (3 credits a
   call), dated 2026-09-28 behind ADR 0110's two preconditions; the credit
   look is registered in
   `docs/measurements/2026-09-10-preregistration-totals-market-credit-cost.md`);
   `CANDIDATE_SQL` admits h2h, spreads and five MLB prop keys only; the
   four `CARD_SHAPES` recipes pick "the N likeliest games", one leg per
   fixture (same-game stays out, ADR 0012 section 5). A recipe is a rule
   Joe chooses, never a ranking by edge (ADR 0071).

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Untouched. One
   candidate for after the freeze, measured not decided: `window_status`'s
   `GROUP BY odds_event_id` over `odds_snapshots` costs ~0.9 s and is polled
   every 10 s by `RefreshWhenPriced` while a tab is open; a covering index
   would be the shape, and it needs its own re-timing.
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged.
3. **The boot health grace is 600 s.** Raised for v37 on a measurement; the
   file's own rule says raise rather than trim a migration to fit. Lower it
   only with a reason, not by reflex.
4. **`position_state` has not fired on live.** The first in-play watched
   position will tell; check `notifications WHERE kind = 'position_state'`
   after it, and that `hedge_lock` still fires separately.
5. **The combo fee-model reopen trigger** (n = 68) — unchanged, Joe-gated
   whether it gets a session; the partner asks that any session name the
   constant it could move before it starts.
6. **`fly.live.toml` growth-rate copy (old item 6) — ALREADY CORRECTED** in
   an earlier edit (`:668-670` records the 326.6 MB/day realisation). Closed.
7. **`pip-audit` pyarrow ignore** — trigger only, unchanged.
8. **The binned card** — do not rebuild, unchanged.

**Joe-gated: NOTHING.** The one question this session (which push) was
answered in-session.

### Lessons written

One, pattern-level: the cost of a scan is not its wall-clock — under
`temp_store = MEMORY` a window function turns rows read into resident memory,
so a floor widened for a correct reason is re-timed on live reading RSS beside
milliseconds before it ships; and an abandoned request is not a finished one.

**And one about my own procedure.** I measured the live site with a probe that
was, functionally, a user opening four tabs, and the box died three minutes
later. The probe was right to run and the death was going to happen at Joe's
next tap either way — but a measurement that can take the box down is one to
announce before running, and to run one route at a time.

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

### Split 2026-09-11 — [`archive/next-2026-09-11.md`](archive/next-2026-09-11.md)

Filed by the date of the split. The five 2026-09-09 and two 2026-09-08
entries that were still in `NEXT.md` when it reached 200,701 bytes, 76.6%
of the ceiling. Taken **under** the trigger rather than at it, before the
session's own entry was written, because the entry about to be written was
a long one and the size that matters is the size *after*. Cut deep, to
37.2%. The cut falls on a date boundary: everything 2026-09-09 and earlier
moved, so no single day is split across two files. Verified by md5: the
archived bytes below its header hash identically to the bytes removed
from `tasks/NEXT.md`.

- 2026-09-09 (fifth session) — the biggest table in the database is 99.7% duplicate rows, and the obvious fix would have emptied the ladder
- 2026-09-09 (fourth session) — a live bet was invisible to the only screen that could exit it, and the wiring that fixed that killed the question a registration was asking
- 2026-09-09 (third session) — the desk armed the entry and never armed the exit; and the census behind every combo warning had never read the shard he trades
- 2026-09-09 (second session) — the audit file is closed after 33 days, the money-path signer finally has a real test, and the fee alarm was wired the day its own excuse expired
- 2026-09-09 — two critical unauthenticated RCEs were live on the public box and are now patched; the effort dial is set; the month-old audit is down to two real items
- 2026-09-08 (third session) — the fat was cut: CLAUDE.md is 20KB, six agents are gone, four task files are archived, seven lessons deduplicated
- 2026-09-08 (second session) — the table took its first two rows, the brake Joe removed was still on the button, and the bid path is disarmed

### Split 2026-09-08 (second) — [`archive/next-2026-09-08-second.md`](archive/next-2026-09-08-second.md)

Taken for readability rather than size (ADR 0116): the three closed
entries from 2026-09-07 and the first 2026-09-08 session, each carrying a
`Still open` list the entry that stayed supersedes. Verified by md5
(`e8c041c54a1b0d17bb8b54908c8204d7`).

- 2026-09-08 — Joe corrected what the desk is FOR at the moment of a bet, and the four things stopping him turned out to be ours
- 2026-09-07 (second session) — tonight's check had no instrument on the box and the wrong reading written down; attention was paying a live-game cadence for a line two days out
- 2026-09-07 (earlier session) — the NFL path is pre-flighted and its first sweep is due tonight by construction; a failed look and a spent day get their own words; the watcher stops asking the venue about a bid that filled

### Split 2026-09-08 — [`archive/next-2026-09-08.md`](archive/next-2026-09-08.md)

Filed by the date of the split. The six 2026-09-06, one 2026-09-05, one
2026-09-04 and two 2026-09-03 entries that were still in `NEXT.md` when it
reached 205,381 bytes, 78.3% of the ceiling. Taken **under** the trigger
rather than at it, at Joe's instruction, before a fresh session started —
and cut deep, to 22.3%, so the next several sessions need not think about
it. The cut falls on a date boundary: everything 2026-09-06 and earlier
moved, and no single day is split across two files. Verified by md5: the
archived bytes below its header hash identically to the bytes removed
(`823e72d9643035f974168e24d26b440c`).

- 2026-09-06 (sixth entry) — the published credit bound was a partial sum, item 3 was half-false, and the largest NFL day-one risk is a failure nobody had timed
- 2026-09-06 (fifth entry) — the parlay window became a control, the in-play combo question is answered, and props are a feed problem rather than a venue one
- 2026-09-06 (fourth entry) — Joe took the offer-making controls off the desk, and what replaces them is a record of a bet placed somewhere else
- 2026-09-06 (third entry) — the partner ran first and its top item was not on the list; the credit answer was refused once before it was kept; three lanes landed and the inspector stopped blocking work
- 2026-09-06 (second entry) — Joe answered the four open questions; the combo note now carries BOTH censuses, ADR 0085 has Amendment 1, PRs #1/#2 are closed, and the shard-3 test and the key rotation are DROPPED on his word
- 2026-09-06 — the parlay census is TAKEN and ADR 0085 is REFUTED at the moment Joe buys; #24, Lane A2, the money-arm predicate, the agent wire fixture and Joe's four answers are all deployed; the inspector blocks work at 99.3%
- 2026-09-05 — the session Joe stopped is picked up: three finished lanes merged (ADR 0106, 0107, the routes split), and the one cross-lane break git could not see
- 2026-09-04 — six lanes landed (ADR 0104, 0102 Amd 1, the Read-ceiling guard); the presence measurement was registered, taken once, audited, and is UNRESOLVED — CONCENTRATION; the partner killed #11's log form; five questions for Joe
- 2026-09-03 (second entry) — the partner found the desk had not gone quiet and the /picks heal was switched off; three lanes landed (ADR 0101–0103); one question and one rotation for Joe
- 2026-09-03 (early) — the partner reordered the queue around a regression shipped the day before; three lanes landed; Joe answered the second batch

### Split 2026-09-06 — [`archive/next-2026-09-06.md`](archive/next-2026-09-06.md)

Filed by the date of the split. The three 2026-09-02, two 2026-09-01 and four
2026-08-31 entries that were still in `NEXT.md` when it reached 223,790 bytes,
85.4% of the ceiling. Taken before the session's entry was added rather than
after, and cut deeper than the trigger required so the cut falls on a date
boundary: everything 2026-09-02 and earlier moved, and no single day is split
across two files.

- 2026-09-02 — the partner ran first; P5 is terminated, #6 is built, and the desk went quiet
- 2026-09-02 — one deploy became nine commits, because the instrument was never on the box and then was wrong
- 2026-09-02 — four lanes landed, the volume had 16 days left, and a wizard died of the defect it was written to prevent
- 2026-09-01 — the lock holder is attributed, the partner had never been invoked, ticket #11 is resolved, and a $100 money stop turns out to be unable to fire
- 2026-09-01 — open item 4 named an instrument that cannot see the failure it measures, and the good news I wrote off it was refused
- 2026-08-31 — the sweet spot reaches all three surfaces, and a second opinion convicted a four-month-old number
- 2026-08-31 — the lock holder was found, and a wording rule lost to typography
- 2026-08-31 — the sweet spot, and the graph Joe asked for
- 2026-08-31 — the Scout reaches the parlay legs, and the budget says it can only flag them

### Split 2026-09-05 — [`archive/next-2026-09-05.md`](archive/next-2026-09-05.md)

Filed by the date of the split. The five 2026-08-30 and two 2026-08-29
entries that were still in `NEXT.md` when it reached 224,305 bytes, 85.6% of
the ceiling. Taken before this session's entry was added rather than after.

- 2026-08-30 — the deadline the screen promised had never once been kept
- 2026-08-30 — the desk placed its first real order, and the venue has no one to fill it
- 2026-08-30 — the WAL read was taken, it could not run, and the memory level halved
- 2026-08-30 — the positions payload was observed, a refusal became a record, and two lanes closed two backlog items
- 2026-08-30 — the hour-long silences are a poisoned connection, and the ticket takes dollars
- 2026-08-29 — the signal test could never have answered its own question, and twelve lanes landed
- 2026-08-29 — THE READ WAS TAKEN, and every gap turns out to be a container death

### Split 2026-09-01 — [`archive/next-2026-09-01.md`](archive/next-2026-09-01.md)

Filed by the date of the split. The seven 2026-08-28 entries that were
still in `NEXT.md` when it reached 85.6% of the ceiling. Taken before
the session's entry was added rather than after.

- 2026-08-28 — the read was attempted a second time, the window survived, and it is 8 minutes old
- 2026-08-28 — the pre-registered read was taken, and it was not a read
- 2026-08-28 — PRE-REGISTRATION: how to read tomorrow's gap, decided before the data exists
- 2026-08-28 — the unexplained gap was the sixteenth, and nothing on disk could have said so
- 2026-08-28 — a leg priced at zero stopped the alerting half of the loop, and the heartbeat fired for a DIFFERENT reason
- 2026-08-28 — one tab could take the site down, and the desk went quiet without saying so
- 2026-08-28 — the palette split shipped, and the guard watching it was measuring the wrong pair

### Split 2026-08-31 — [`archive/next-2026-08-31.md`](archive/next-2026-08-31.md)

Filed by the date of the split. The 2026-08-28 and 2026-08-27 entries that
were still in `NEXT.md` when it reached 87.3% of the ceiling. Taken before
the session's entry was added rather than after.

- 2026-08-27 — the map got three rulings and a colour, and this file learned the map exists
- 2026-08-27 — the alarm that watches for a silent death had been taught to fire every day, and the combo tests were all in the wrong branch
- 2026-08-27 — two lanes can be seen at once, and the tool that saw them told a human to delete sixteen projects
- 2026-08-27 — a cold open buys odds on the pass it woke
- 2026-08-27 — the parlay push stops being a race and becomes a schedule

### Split 2026-08-29 — [`archive/next-2026-08-29.md`](archive/next-2026-08-29.md)

Filed by the date of the split. The 2026-08-26 and 2026-08-25 entries that were
still in `NEXT.md` when it reached 86% of the readable-size ceiling. Taken at
86% rather than 98.9%, on the rule the previous split wrote.

- 2026-08-26 — three commits had no entry, and one of them raised the bet
- 2026-08-26 — the live box was OFF between visits, and five commits later the desk draws pictures
- 2026-08-26 (hedging lane) — the desk starts watching what Joe already holds, and a hedge turns out to need no model at all
- 2026-08-26 — the buy control reaches every card, and the ticket renders on a real book for the first time
- 2026-08-26 — one parlay generator becomes six, and the notifier is deliberately left behind
- 2026-08-26 — the alarm stops guessing, and the desk's cards reach the phone
- 2026-08-25 — the desk was empty because the loop was ASLEEP, and nothing could wake it
- 2026-08-25 (later) — the odds feed stops watching the clock and starts watching whether anyone is there
- 2026-08-25 — the declaring look is REFUSED, and §P4 turns out to have been an opt-in nobody opted into

### Split 2026-08-27 — [`archive/next-2026-08-27.md`](archive/next-2026-08-27.md)

Filed by the date of the split. The 2026-08-24 through 2026-08-20 entries
that were still in `NEXT.md` when it reached 98.9% of the readable-size
ceiling.

- 2026-08-24 (fifth session, close) — SUPERSEDED by the entry above: the screen's declaration did not survive audit
- 2026-08-24 (fifth session) — the purpose gets settled, and the feed is told to follow attention
- 2026-08-24 (fourth session) — the parlay desk earns a nav slot and every game names its sport
- 2026-08-24 (third session) — the desk is used for real, and a combo book is populated for the first time ever
- 2026-08-24 (second session) — all 14 review findings fixed, and the repeat tap turns out to be idempotent
- 2026-08-24 — code review of the parlay-desk session: 14 findings (ALL FIXED — see the entry above)
- 2026-08-23 (third session) — the parlay desk: three cards at fair value, spreads priced, and the combo's real cost one tap away
- 2026-08-23 (second session) — the desk presents fully: likely winners on the slate, five areas per game, Willy's seat
- 2026-08-23 — the desk window opens: the slate stops being stale 14 hours a day
- 2026-08-22 (third session) — the pass gets its caller, the probe gets cheap to start, and stale odds get an exit
- 2026-08-22 (second session) — the every-page review ships whole: kill list, glossary, real limits, and a manual door built dry
- 2026-08-22 ~13:15Z — the betting-desk list closes out: CLV on his own bets, then the ticket cleanup
- 2026-08-21 ~23:30Z — the landing screen stops claiming an edge, and the session hands off
- 2026-08-21 ~22:45Z — the refusal lands on real data, and the lockout gets the desk's name
- 2026-08-21 ~21:45Z — /bets ships, and the partner re-rules the refusal work by name
- 2026-08-21 ~20:30Z — the desk gets a token meter and a nav slot in one change, and the gold goes out
- 2026-08-21 ~18:30Z — Joe rules the purpose, the Skeptic retires, and the cost record gets honest
- 2026-08-21 ~16:45Z — the market screen joins the shell, and the desk scales to a real instrument panel
- 2026-08-21 ~15:30Z — the briefing becomes a cockpit, and the market screen serves the venue's facts
- 2026-08-21 ~06:30Z — the Scout desk is switched on, on Joe's word: a staff of two and a master, metered
- 2026-08-21 ~04:30Z — the replay gate passes exactly, and the ledger's null kickoff is fixed
- 2026-08-21 ~03:15Z — the H4 series closes on a measured reason: the channel diagnostic is BLIND on a denominator of 1
- 2026-08-21 ~02:00Z — h4-balance-spans ships with its guards red, and both deploys landed
- 2026-08-21 ~00:20Z — H4 Look 1 is taken and moves nothing, tomorrow's terminal spread look is armed, and one deploy waits on Joe
- 2026-08-20 ~21:35Z — the spread test is TAKEN: UNDERPOWERED both arms, and the partner's list is the open work
- 2026-08-20 ~19:45Z — the dropouts are diagnosed, the zero is verified, and the spread test is armed for 21:21Z
- 2026-08-20 ~17:00Z — the gate is measured, the product has a plan, and a slice is built but NOT deployed

### Split 2026-08-25 — [`archive/next-2026-08-25.md`](archive/next-2026-08-25.md)

Filed by the date of the split rather than of the entries, like the 08-18 file
below it: these are the 2026-08-19 and 2026-08-17 entries that were still in
`NEXT.md` when it reached 93% of the readable-size ceiling.

- 2026-08-19 ~23:20Z-00:30Z — THE FIXES HELD FOR 2H40M, NOT 12 HOURS; AND THE UNMATCHED QUEUE'S OBVIOUS FIX WAS AN OUTAGE
- 2026-08-19 ~16:20Z — THE 15:21Z TEST WAS TAKEN; THE STORE LEG IS INNOCENT, AND THE FLAPPING WAS NEVER THE BACKEND
- 2026-08-19 ~12:15Z — ADR 0053 HALF-HELD; THE COST MOVED TO THE STORE LEG, AND I GUESSED WRONG ABOUT IT FIRST
- 2026-08-19 ~02:30Z — LIVE HAS BEEN FLAPPING ALL DAY, I SAID IT WAS HEALTHY, AND THE CAUSE IS THE QUOTE PASS
- 2026-08-19 ~late — THE STRIP IS ON THE PHONE, BY JOE'S CALL
- 2026-08-19 ~mid — THE STRIP SAYS WHERE THE NUMBER CAME FROM, AND THE DEMO WAS DISAGREEING WITH ITSELF
- 2026-08-19 ~early — THE ALARM WAS WATCHED, AND THE CODES SPEAK ENGLISH ON FOUR SCREENS
- 2026-08-17 21:55Z — THE MEASUREMENT IS NOT DUE YET, AND THAT IS THE WHOLE SESSION
- 2026-08-17 — JOE'S THREE ITEMS, AND THE LANE THAT WAS BRIEFED WAS THE ONE THAT DID NOT EXIST
- 2026-08-17 — THE MORNING WARNING WAS ARITHMETIC, AND IT IS GONE FROM THE LIVE SCREEN
- 2026-08-17 — THE INSTRUMENTS NOW DISAGREE WITH THE MACHINE OUT LOUD
- 2026-08-17 — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH

### 2026-08-18 — [`archive/next-2026-08-18.md`](archive/next-2026-08-18.md)

- 2026-08-18 ~night — THE ALERTS LEAVE THE PHONE, AND THE FAILURE CHANNEL IS WIRED
- 2026-08-18 ~evening — THE DESKTOP TIER EXISTS, AND THE GREEN-ZERO DEFECT DIED FIRST
- 2026-08-18 ~16:30Z — THE TRIAGE IS DISCHARGED: THE STOP HAS A READER, THE BANKROLL IS DERIVED, AND THE COMBO FEES GOT THEIR REGISTERED LOOK
- 2026-08-18 11:10Z — THE STUDY IS OPEN, THE MACHINE MATCHES ITS COMMIT, AND THE PARTNER HAS SET THE ORDER
- 2026-08-18 08:50Z — THE ENTRY FORM EXISTS, AND THE DATABASE ITSELF NOW REFUSES TO EDIT AN ESTIMATE
- 2026-08-18 08:30Z — THE POLLER IS LIVE, AND JOE'S OWN RECORD IS NOW MIRRORED WHERE KALSHI CANNOT DELETE IT
- 2026-08-18 00:30Z — THE PUBLIC DEMO OVERSTATES SIZE BY 17x, AND THE ADR THAT CLOSED THAT HOLE CANNOT SEE IT

### 2026-08-17 — [`archive/next-2026-08-17.md`](archive/next-2026-08-17.md)

- 2026-08-17 (latest) — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH
- 2026-08-17 (later) — THE SCREEN WAS A VERSION BEHIND THE RECORD
- THE HUNT IS CLOSED. ADR 0038. READ THIS FIRST.
- THE WHOLE PROP-MODEL LINE IS CLOSED. ADR 0037.
- PITCHER-K IS REFUTED. THE MODEL WORKS; THE PARAMETERS CANNOT.
- 2026-08-17 (~00:30Z) — P1 WAS READING THE WRONG STATISTIC. NFL IS A SKIP. MLB PROPS REORDER TO PITCHER-K.

### 2026-08-16 — [`archive/next-2026-08-16.md`](archive/next-2026-08-16.md)

- 2026-08-16 (~22:40Z) — BETA IS MEASURED AND NEGATIVE. WE ARE OFF THE GATE. BUILD AN OPINION.
- 2026-08-16 (~21:05Z) — LIVE WENT DOWN FOR 54 MIN (VOLUME FULL). FIXED. AND THE FEE IS 2x TOO HIGH.
- 2026-08-16 (~19:20Z) — ⚠ `actionable` IS NO LONGER 0. AUDIT IT BEFORE ANYTHING ELSE.
- 2026-08-16 (~19:30Z) — PROPS ARE OFF THE SCHEDULE. THE FUNNEL IS SPEC'D. ONE DUMP STILL NEEDS A LAPTOP.
- 2026-08-16 (~18:20Z) — THE REFRESH IS DEPLOYED AND FIRING. TWO THINGS STILL NEED JOE'S HANDS.
- 2026-08-16 (~06:30Z) — THE TWO TOP ITEMS ARE UNCHANGED AND STILL WAIT ON THE 16:51Z SLATE
- 2026-08-16 (~03:00Z) — A DEPLOY IS OWED, AND ONE MEASUREMENT IS STILL DUE AT ~17:30Z
- THE CREDIT DEFECT IS FIXED IN THE REPO AND **NOT YET DEPLOYED**. Deploy is the first thing. *(SUPERSEDED: it was deployed and verified ~00:35Z.)*

### 2026-08-15 — [`archive/next-2026-08-15.md`](archive/next-2026-08-15.md)

- PROPS ARE RECORDING ON LIVE. One defect fixed, **one still open and it has a clock**. *(SUPERSEDED by the section above: the credit defect is fixed in the repo, pending deploy.)*
- PROPS ARE BUILT, ALL FOUR SLICES. **SUPERSEDED by the section above — they are now deployed and two defects were found in the first live pass.** Note its credit figures are the ones that turned out wrong.

### 2026-08-14 — [`archive/next-2026-08-14.md`](archive/next-2026-08-14.md)

- PROPS THROUGH THE EXISTING PIPELINE. **SUPERSEDED — all four slices are done; see the section above.** Kept for the constraints it records.
- PROPS ARE CHARGED THE BASEBALL RATE. H-SPORT survived a real falsification test.
- PROPS ARE REACHABLE, AND THE FEE COEFFICIENT IS THE GATE, NOT THE MARKET
- THE FEE HEDGE IS RETIRED. The break-even bar is 51.75%, and one published analysis is now stale.
- ROUND THREE IS RUN. The fee is NOT a venue constant, and the code is wrong on baseball.

### 2026-08-13 — [`archive/next-2026-08-13.md`](archive/next-2026-08-13.md)

- Q-W RAN AND ACTIVATED. Nothing is blocking the orders but Joe's clock.
- Q-W IS BUILT AND COMMITTED (superseded above; kept for the image finding)

### 2026-08-12 — [`archive/next-2026-08-12.md`](archive/next-2026-08-12.md)

- ADR 0020 IS WRITTEN. The reserved number is spent, and it opens nothing.

### 2026-08-11 — [`archive/next-2026-08-11.md`](archive/next-2026-08-11.md)

- THE CEILING ON RELAXING `stale_odds` IS 23 ROWS = 14 OPPORTUNITIES, AND NOTHING BEHIND IT IS A RUNWAY
- OPEN QUESTION FOR JOE: 85.8% of the $3.66 lands in a series with zero rows in the record
- ADR 0025: the `stale_odds` claim was OVERSTATED by ~10x, and its mechanism ran backwards
- ⏱ Time-sensitive, and it is free
- RESOLVED: `capture_odds_repeat_poll.py`'s P1 could not fail. Fixed at `39628e0`.
- The demo instance renders a healthy version of the screen that is empty on live

### 2026-08-10 — [`archive/next-2026-08-10.md`](archive/next-2026-08-10.md)

- `inspect_live_db.py` RUNS NOW, and answers ONE of the four questions it was queued for
- ADR 0021 §7: the dump is refused for the CLV test, and NOT ruled on for the other one
- CORRECTED: ADR 0021 §7.2 asserted something its own source had already refuted
- 2026-08-10 22:34:21Z — THE SWEEP SERVED. The latch is refuted, F4's prediction held.
- RESOLVED: the 21.5-hour odds gap had an empty denominator
- The documented phone health check cannot pass, and never could
- 2026-08-10, overnight — SIX DURABLE FACTS FROM TONIGHT'S LANES
- ⏱ 2026-08-10, evening — RUN THIS FIRST, THEN READ THE REST
- 2026-08-10, overnight — THE REFUTATION IS WRITTEN, AND IT QUOTES A FIXTURE AS A FACT
- ⚠ 2026-08-10 — READ THIS IF YOU ARE A PARALLEL SESSION
- 2026-08-10, end of session — ADR 0019 LANDED, AND THE REPORTED BUG WAS WRONG
- INFRASTRUCTURE INTERRUPT: Actions minutes, and the public flip
- 2026-08-10, end of session — THE BOUND FAILED, AND IT FOUND A REAL BUG
- 2026-08-10, mid-session — JOE: ONE COMMAND (still true; the ADR framing above supersedes)
- THE PLAN: one joint bound, then stop and write the refutation
- the edge test is REGISTERED, and it retracts a claim of mine
- `partner` re-triaged: calibration is the CONTROL for the edge test
- the power-ratings finding is AUDITED, and `no_edge` may be misnamed
- DEPLOYED, D1 is answered, and deploys are now BATCHED
- 2026-08-10, earlier — LIVE READ ACCESS IS UNBLOCKED
- half the documented strategy has never run, and the $5 buys a field name

### 2026-08-09 — [`archive/next-2026-08-09.md`](archive/next-2026-08-09.md)

- 2026-08-09, ~22:40Z — DEPLOYED, and `actionable` has been 0 for the whole record
- 2026-08-09, late — six lanes landed, and three audits refuted the prose over them
- 2026-08-09, ~19:30Z — the bankroll trap is fixed; the backfill cannot open the gate
- CLOSED 2026-08-09 — the 94% is withdrawn, and the replacement died too
- 2026-08-09, ~16:00Z — the gate freeze was an empty slate. DECIDED: accept.
- 2026-08-09, 06:00–09:00Z — five items closed, and one of them was Joe's
- DEPLOYED (2026-08-09, 05:36Z) — the budget stopped being the constraint
- Superseded (2026-08-09) — the 20K tier is bought; the key is not installed
- The gate is blocked by the odds budget, and the guards are fine
- READ FIRST (2026-08-09, later) — the log stream drops lines, and the number everyone quoted was a 10% sample
- READ FIRST (2026-08-09) — the gate's counter cannot grow, and it is arithmetic
- DEPLOYED (2026-08-09, ~03:17Z) — and `clv_scored` left zero
- HANDOFF (2026-08-09, ~00:10Z — the settlement path is built, nothing is deployed)

### 2026-08-08 — [`archive/next-2026-08-08.md`](archive/next-2026-08-08.md)

- HANDOFF (2026-08-08, evening — demo is deployed, live is one tap away)
- HANDOFF (2026-08-08, 14:4xZ — the sheet is merged, and running it found four more)
- HANDOFF (2026-08-08, overnight — three lanes, and CI was already red)
- HANDOFF (2026-08-08, 05:2xZ — deployed, and the demo found the bug for us)
- Joe's asks, 2026-08-08 — four of them; two are done
- HANDOFF (2026-08-08, later still — the price is live, and a review caught me)
- HANDOFF (2026-08-08, earlier — the 30-second window is fixed)
- HANDOFF (2026-08-08, earlier)

### 2026-08-07 — [`archive/next-2026-08-07.md`](archive/next-2026-08-07.md)

- 1. Blocked on you
- 1b. Found by deploying live
- 2. Fix before any real money
- 3. Ready to build (no blockers)
- 4. Verified working
- The honest status
