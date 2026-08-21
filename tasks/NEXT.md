# Next — your checklist

**How this file works, since 2026-08-17.** This file holds the **current
state**: the latest session entry, plus what is still open. Every earlier
session entry is in `tasks/archive/next-YYYY-MM-DD.md`, **verbatim** — the
archive reconstructs the pre-split file byte for byte, nothing was summarised or
dropped. The index at the bottom lists every entry and which file it is in.

The split happened because this file had reached **456,641 bytes / 8,145
lines**, past the 262,144-byte ceiling at which the Read tool refuses a file
outright. `tests/test_session_files_are_readable.py` now fails if it or
`tasks/lessons.md` crosses back over. When you add an entry and the file grows,
move the older ones into the dated archive file — do not shorten them.

---

## SESSION START — if Joe said "read NEXT.md", this box is your prompt

Repo: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`,
branch `main`. Check `git status` and `git log origin/main..main` rather than
trusting any sentence here, and read the LIVE instance's `/api/health` for its
`git_sha` — it sits under `build`, not at the top level. The calibration study
is STOPPED (2026-08-20, Amendment 2; the recorder machinery still runs). Joe is a beginner and has
asked to be educated: define every betting/stats term at first use, via
`frontend/src/lib/glossary.ts` and `<Term>`.

Read `CLAUDE.md`, then the latest entry below (it is the whole brief), then
`tasks/lessons.md` top two. Re-verify state, never inherit it:

    .venv\Scripts\python.exe -m pytest -q     (NEVER bare python; PATH is 3.14)
    cd frontend && npx tsc --noEmit

Expected: 3,807 passed / 10 xfailed, ruff clean, tsc clean, `next build` green.
The terminal spread/total look was **VETOED by Joe 2026-08-21 16:11Z**,
recorded per §7.1 in
`docs/measurements/2026-08-21-spread-total-edge-second-look-result.md` —
nothing fires at 22:40Z and no session needs to be alive for it. **The H4 look series is CLOSED
— BLOCKED ON INSTRUMENT, 2026-08-21** — do not build the A9–A12 analyzer
and do not re-run the channel diagnostic (A17.6/A17.11). Live may be one
deploy behind — check `/api/health` `git_sha` against `origin/main`.

---

## 2026-08-21 ~20:30Z — the desk gets a token meter and a nav slot in one change, and the gold goes out

**The partner's betting-desk item 6 is done, all three clauses, one slice.**
It was flagged urgent because the meter is protecting Joe's fresh $20 — the
account had actually run dry (ADR 0062 §3). State: **3,807 passed / 10
xfailed** (+13), ruff clean, tsc clean, `next build` green, overflow gate
passes at 390/768/1280/1440/1920 with `/scout` on the page list.

**The meter (schema v17).** The 24-call cap counts calls; a staff scout's
call carries the web-search tool at `max_uses: 6`, so one convening could
spend 12 searches — billed per-search, results billed as input — inside
three perfectly-counted calls. Now:

- `agent_calls` gains `input_tokens` / `output_tokens` / `web_searches`
  (nullable, no backfill; migration 17). `structured_call` returns
  `StructuredCallOutcome` — parse AND the API's usage block, usage kept even
  on a safety refusal (still billed), `None` only when no response arrived;
  `settle` writes it. NULL usage rows are counted as `calls_unmetered_today`
  so the sums state what they miss.
- Two daily brakes in `AgentBudget`, evaluated over RECORDED usage **before**
  the next reserve — never a field the gated call will write (the
  receipt-not-a-brake lesson): `AGENT_MAX_SEARCHES_PER_DAY=60`,
  `AGENT_MAX_TOKENS_PER_DAY=500000` (defaults bind early, arithmetic in
  `.env.example`; also set in `fly.live.toml`). The desk states its staff
  pair's pre-known worst case (`STAFF_PAIR_SEARCHES_WORST_CASE = 12`) at
  both gates — `convene_desk` and the POST route's early refusal — from one
  module-level constant so they cannot drift.
- Mutation-verified red, file restored byte-identical each time: sum→count
  in `state()`, token check dropped, settle-usage dropped, and
  `searches_worst_case` dropped from the desk's `can_afford`.

**The screen and the slot.** `GET /api/scout` (public read) serves the last
50 convenings as summaries — never briefing bodies — plus today's spend in
the three units that bill: calls, searches, tokens. Counts, not dollars;
`spend: null` on a keyless instance (the demo), which is "no account to
meter", not an empty meter. New `/scout` page renders the meter above the
convening record and deliberately has **no send button** — the desk is sent
from a game's screen, because a desk sent from a list invites filling the
list. **Scout takes the nav's open sixth slot** (Log's retired one), placed
so Gate keeps its visible position at 390px and Playbook stays the link that
scrolls; `test_the_nav_budget_is_still_six` records the trade.

**The gold is out.** The `fresh` tile and the unpriced-finding chip wore
`accent-2` — the palette slot every other screen reserves for "do not trust
this" (test_palette_contrast.py) — to light the staff's own unfalsifiable
`likely_already_priced` guess as if it were an edge signal. Both are
neutral now: glyph, border and weight carry the state; the verdict strip
says "recent is not the same as unpriced". ScoutDesk's send copy now names
the searches and points at the Scout screen's running total.

**For the next session:** live needs a deploy to carry all of this (v17
migrates at boot via `scripts/migrate_db.py`; additive columns, safe on the
volume). The 08-18 session entries moved verbatim to
`tasks/archive/next-2026-08-18.md` (index updated); the 08-17-dated entries
still in this file share titles with archived ones but differ in text —
left untouched, resolve deliberately or not at all.

**The partner's remaining betting-desk list, renumbered:**
1. `/bets` — his own record from `venue_settlements` (embargo checked this
   session: Amendment 2 stopped the study without result, the estimate log
   stays embargoed forever, and A7 rules `venue_settlements` outside it —
   buildable so long as it never touches `bet_estimates`).
2. Refusal onto real data — tonight's count/stakes over `venue_settlements`
   with the lockout beside it, on the deciding screen.
3. Repoint the lockout off the stopped study's endpoint.
4. CLV on his own bets — union `venue_settlements.ticker` into
   `backend/scoring.py:97`.
5. Strip the landing screen — edge point estimate off; dispersion-as-range
   behind a tap, no direction, no `used` mark.
6. `TicketSheet`/`TicketProvider` unreachable-code removal; "Ledger" rename.

**Still open from before:** footer 5-and-5 parity note; partner's "later,
maybe" lists (2026-08-21 review + ADR 0061).

---

## 2026-08-21 ~18:30Z — Joe rules the purpose, the Skeptic retires, and the cost record gets honest

**The ruling, verbatim and now in ADR 0062 + agent memory:** *"I always
wanted this to be a betting desk. the edge-finder should have been a
feature, but not a determiner."* Preceded by "I don't care about 1-2 cent
diffs" — his position size makes the venue's whole cost advantage ~15
cents/bet. ADR 0038 closed the hunt on measurement; 0062 closes it on
purpose. Gate, dry-run constant, suppression rules, odds feed: untouched.

**Built this session (the partner's item 3, the one bleeding money):**

- **Scheduled Skeptic killed.** The partner's cost audit found `agent_calls`
  refuting `fly.live.toml`'s "surfaced=0 protects the bill": **24 Opus calls
  in 4m22s on 2026-08-16** (whole daily cap, four prop rows re-reviewed 6x),
  all blocked — so `surfaced` read 0 *after* the spend. `run_pricing_pass`
  now defaults to `review_retired` (refuses every surfaced row as
  `skeptic_unreviewed` / "retired (ADR 0062)", zero Anthropic calls;
  `review_surfaced` stays importable, opt-in only). Mutation-verified:
  restoring the old default turns `TestTheScheduledSkepticIsRetired` red.
  From now on `surfaced` is frozen at its historical values.
- **Four doc corrections**, all understating deployed reality:
  `fly.live.toml` spend-trap block rewritten with the refutation; sweep cost
  6→2 (h2h only); "400/day"→600; `.env.example` 400→600; ADR 0002 "$5/mo,
  1GB" gets a dated correction (live is 2GB, volume at auto-extend limit).
- **Lesson written:** a field computed after the spend is a receipt, not a
  brake — the money-shaped case of "verification methods that lie".
- **"The recorder costs nothing" is retired** (ADR 0062 §4): ~70 Odds
  credits/day measured, sole reason the $30/mo tier exists, plus 2GB
  always-on machine. Recorder keeps running (feeds Board + scout desk).

**Joe answered three of the open calls, same day (~16:10Z):**
- **The Anthropic account had actually run DRY** — "I ran out of API
  credits, so its a fresh new $20 i just deposited." This retroactively
  hardens ADR 0062 §3: the spend was not hypothetical, it emptied the
  account. The Skeptic retirement and the coming scout-desk token meter
  are protecting a fresh $20, so treat that meter (work item 6) as urgent.
- **The $30/mo Odds tier stays.** His call, recorded.
- **The 22:40Z look is VETOED** — result file committed, see SESSION START
  box. Fly invoice remains the one unpulled number.

**The partner's remaining betting-desk work list, in priority order** (full
reasoning in its 2026-08-21 ruling; each is a vertical slice):
1. `/bets` — his own record from `venue_settlements` (zero routes/screens
   today; check the ADR 0044 embargo release first).
2. Move the refusal onto real data — tonight's count/stakes over
   `venue_settlements` with the lockout beside it, on the deciding screen.
3. Repoint the lockout off the stopped study's endpoint.
4. CLV on his own bets — union `venue_settlements.ticker` into
   `backend/scoring.py:97`.
5. Strip the landing screen — edge point estimate off; dispersion-as-range
   behind a tap, no direction, no `used` mark.
6. Meter the scout desk by tokens/searches, THEN promote it to nav — same
   change, not sequential (its 24-call cap meters calls, not the up-to-12
   web searches per convening); neutralise the gold
   `likely_already_priced` tile in the same change.
7. `TicketSheet`/`TicketProvider` unreachable-code removal; nav swap;
   "Ledger" rename.

**Still open from before:** footer 5-and-5 parity note; partner's
"later, maybe" lists (2026-08-21 review + ADR 0061).

---

## 2026-08-21 ~16:45Z — the market screen joins the shell, and the desk scales to a real instrument panel

Joe saw the desktop render ("it's so small") and directed the process
himself: graphic-designer briefed first, then a partner convening with
ui-designer and ux-designer. **ADR 0061** records the outcome; the two
decisions that will be re-derived at full cost if lost:

- **Root cause:** the market page hardcoded `max-w-3xl` — narrower than its
  own Nav. It now imports `SHELL_WIDTH`, and `test_desktop_tier.py` bans
  `max-w-3xl` in shell surfaces alongside `max-w-5xl`.
- **The 24rem facts rail all three designers first assumed was killed on
  arithmetic** (main would be 856px → 122px tiles; the rail eats exactly
  the pixels that answer the complaint). Rule: a data band goes full shell
  width, prose caps at 65ch inside it; a rail must earn its content.

Also: tiles ~193px at xl (`xl:` variants only — container queries rejected
for breaking sub-xl byte-identity), six-across pinned; re-send buttons lose
`bg-accent` (red = money; pinned, mutation-verified both); quote strip takes
no size step (the ask never exceeds body size); ticker demoted below the
board; `check_mobile.py` gained `--market-ticker` (ADR 0047's own gate had
never measured this page) and passes at 390/768/1280/1440/1920 with the
real MIL ticker; ScoutDesk + market page joined `PROSE_FILES`.

State: **3,791 passed / 10 xfailed**, ruff clean, tsc clean, build green,
deployed (`9952a0f` verified on live). **Joe answered the look-at-it
question 2026-08-21 ~15:20Z: "6 tiles across one row is fine"** — the
six-across pin stands as built. He also re-sent the scouts post-board
(filed 15:17Z): the master's own tiles rendered correctly on live, and his
read correctly named the unchecked same-day lineups as the briefing's real
content. Session ended here at Joe's request; this entry is the handoff.

**Still open:** tonight's terminal spread/total look at 22:40Z (session
alive in band 22:35–22:45Z; replay gate PASSED 04:04Z); footer 5-and-5
parity note; partner's "later, maybe" lists (2026-08-21 review + ADR 0061).

---

## 2026-08-21 ~15:30Z — the briefing becomes a cockpit, and the market screen serves the venue's facts

Joe read the desk's first real briefing (Braves–Brewers, filed 14:03Z) and
gave three directions, verbatim in the memory file
`briefings-are-visual-first-and-sport-neutral.md`: visual like a cockpit,
sport-neutral, good on desktop AND phone. He then asked for the market
screen itself to be made more useful, "ask the partner to consult with the
relevant agents."

**The partner convened seven agents and ruled: render the venue's facts,
never the tool's opinion** — full direction + the explicitly-not-doing list
in `docs/reviews/2026-08-21-market-screen-direction.md`. All eight build-now
items are built, tested, mutation-verified where they guard money or
honesty:

- **The board**: the master scout fills six sport-neutral instrument tiles
  (fresh / stale_only / unconfirmed / clear), completed server-side
  (`complete_board` — missing→unconfirmed, duplicates→most-alarming,
  unearned clear→unconfirmed). Binary verdict strip, no counts — a count
  was the one number the schema forbids, manufactured client-side. Glyphs
  as primary channel; `clear` unlit; only `fresh` carries hue.
- **The market screen**: ScoutDesk above the fold, chart in a closed
  details with the history-not-a-quote caveat in its summary; header is
  `Away @ Home / YES = team / league · start · status` off the odds clock
  (never `kalshi_events.commence_ms`, ADR 0006); quote strip with LIVE ages
  (`_serialise` now gets `now_ms`/`staleness` — they were frozen at write
  time) and a stale ask refused outright; `close_ms`/`market_status`
  served so settled markets say so. NO line and candles toggle gone,
  ranges Today/All.
- `--border-strong` token added (dashed borders were 1.30:1 — invisible).

State: **3,789 passed / 10 xfailed**, ruff clean, tsc clean, `next build`
green. The first briefing predates the board; its screen shows a derived
board and says so. **The Braves game is worth re-sending to see the real
board** — and the fixture's fun wrinkle (a two-city series claim the scout
couldn't verify) is exactly what the unconfirmed state was built for.

**Still open:** tonight's terminal spread/total look at 22:40Z (band
22:35–22:45Z, session must be alive, replay gate PASSED at 04:04Z); the
footer 5-and-5 parity note; the partner's "later, maybe" list in the
review doc.

---

## 2026-08-21 ~06:30Z — the Scout desk is switched on, on Joe's word: a staff of two and a master, metered

**ADR 0060.** Joe asked for it by shape ("the master scout … a team report to
him … each knowing their own home teams player status, team statuses, weather
if they're playing at home … an expert opinion that would finally serve me at
my desk"). That is the decision ADR 0022 §4 recorded as not-yet-taken, now
taken by the person whose money it spends.

**What shipped, all tested:**

- `backend/agents/scout_desk.py` — one convening = two staff scouts (one per
  club; the home scout owns the venue/weather) + one master who synthesises
  their notes and may not add facts. Three metered calls via the existing
  `AgentBudget` against the same `agent_calls` day as the Skeptic (24/day →
  ≤8 briefings). Staff pair reserved before the first request; master reserved
  only after a note exists; a refusal spends zero. **No numeric field exists
  anywhere in `DeskBriefing`** — walked by test, not trusted to the prompt.
- `scout.py`'s unmetered solo `research()` is **deleted**, not wired; the
  module survives as the desk's schema home. Quarantine row removed from
  `test_has_callers.py`; `scout_desk.py` and `routes.py` allowlisted in
  `BILLED_PATH_CALL_SITES` with their meter named; the historian is now the
  set's only member.
- `scout_briefings` table (schema.sql, IF-NOT-EXISTS so no migration);
  `POST /api/scout/{ticker}` (auth, 202 accepted-never-briefed, 429 before
  writing on an exhausted day, 422 unlinked ticker, 503 no key, 409 already
  running) + public `GET /api/scout/{ticker}` with `gone_quiet` for a
  `running` row older than 15 min.
- Frontend: `/scout-desk` Next route handler holds the bearer server-side
  (same pattern and same widening statement as `/refresh-odds`; middleware
  names the path), `ScoutDesk.tsx` on the Market screen — send button says
  "three metered calls" before the tap, filed-nothing renders dark vs
  looked-found-nothing, refused/failed/gone-quiet all have words. Crew
  bubble's Scout line updated (still an admission; pinned test still holds).
- Mutation-verified guards: numeric field into the briefing schema, dropped
  budget pre-check, reserve-after-call — each red, file restored each time.

**Verification:** 3,782 passed / 10 xfailed (+17 new: 9 desk, 8 API, minus
the timezone guard that caught `ScoutDesk.tsx` rendering device-zone clocks
— fixed with `DISPLAY_TIME_ZONE`), ruff clean, tsc clean, `next build` green.

**What the desk does not do, so nobody re-litigates it:** no probability, no
price, no bet verdict — schemas make those unrepresentable; ADR 0038 is
untouched (§5 of ADR 0060 has the argument). The demo cannot send it (no key,
no token, both halves refuse independently).

**First real convening is the open question.** Nothing has run against a live
game. When Joe sends it, read the briefing critically: quality is unmeasured,
and the `likely_already_priced` flags are the honesty valve to check first.

**Still open, unchanged:** tonight's terminal spread/total look at 22:40Z
(band 22:35–22:45Z; a session must be alive in the band; replay gate already
passed at 04:04Z), and the footer 5-and-5 parity note.

---

## 2026-08-21 ~04:30Z — the replay gate passes exactly, and the ledger's null kickoff is fixed

State at close: tests **3,766 passed / 10 xfailed** (+4), ruff clean, tsc
clean, pushed through `6a23920`. **Live is current: deployed `1673331` at
04:17Z on Joe's word** (run 32446407696, dispatch went through in auto mode
first try; `/api/health` verified `git_sha` + `instance_mode: live`). That
deploy carried `d487d2d` (estimate-form demotion) and `6a23920` (below).
Nothing tonight's look needs is on live — the sweep is a local script.

**The free replay gate for tonight's look was run at 04:04Z and PASSES
exactly.** All five sharp edge values (−25.0, −3.5, −19.2, −15.3, −2.9
tenths), sharp counts 3/3 games and 2/2, both UNDERPOWERED verdicts, total
rows 3 and 4, and the full exclusion dict (incl. `outside_window: 16`)
match Amendment 1's registered gate evidence line for line. The rows
artifact is at
`docs/measurements/2026-08-21-spread-edge-rows-2026-08-21T040406Z.json`
(replay by-product; committed in `e8d4614` by a broad `git add -A` — kept,
since it is derived public-market data and doubles as the gate evidence). The band session should still
re-run the gate before the anchor — it is free and the registration says
before the anchor, not eighteen hours before.

**The `/api/ledger` `commence_ms` defect is FIXED (`6a23920`).** The route
now joins `r.link_id → event_links → MIN(odds_snapshots.commence_ms)` —
the scorer's own definition (`backend/scoring.py:markets_awaiting_scoring`)
— so the ledger's pre/post-commence axis agrees with the machinery that
writes the clv fields. The documented 3-hour trap was refused, not merely
avoided: `kalshi_events.commence_ms` is never touched, and a test plants
the raw `occurrence_datetime` value three hours late and asserts it does
not surface. Unlinked rows resolve to `None`, never a substitute. Four
guards, each verified red by mutation (MIN→MAX, the kalshi_events join,
COALESCE-to-0). Note for any consumer: rows written before the linker had
a `link_id` still read `None` — that is honest, not a regression.

**Open, in order:**

1. **Tonight's terminal spread/total look, 22:40:00Z** (band 22:35–22:45Z,
   4 credits, Joe's veto until the anchor). A session must be alive in the
   band or the look goes UNTAKEN — session timers cap at 1h and die with
   the session, so this needs Joe (or a session he starts) around 22:30Z.
   Every branch writes
   `docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`.
2. The next deploy carries `d487d2d` + `6a23920` (no urgency).
3. The footer 5-and-5 parity note (a constraint on future nav work, not a
   task — `tests/test_every_screen_is_reachable.py` docstring).

---

## 2026-08-21 ~03:15Z — the H4 series closes on a measured reason: the channel diagnostic is BLIND on a denominator of 1

State at close: tests **3,762 passed / 10 xfailed**, ruff clean, tsc clean,
`next build` green, everything pushed. Live is on `349dca0` (deployed this
session, dispatch went through in auto mode first try) — commits after it
are docs/tasks-only except the estimate-form demotion (`d487d2d`), which is
UI + a scope guard and can ride the next deploy; nothing urgent needs it
live tonight.

**The partner convened, re-ruled, and the ruling is executed.** Its key
move: do NOT build the A9–A12 analyzer on schedule — the record suggested
the balance channel cannot see payouts — and instead register the cheapest
test of that (ADR 0059 is the generalised rule). The chain, all committed
in order: **Amendment 3** (`9693847`, pre-registrar: the A15 disclosure of
a partial unblinding, A16 closing the span/cluster voting defect it found
— ~4,000 empty snapshot pairs could have voted — and A17 registering the
channel diagnostic with all three verdicts' consequences fixed);
**analyzer** (`7c78a32`, before the data); **pull** 02:49:45Z (30m35s
after the amendment, one attempt, sections untruncated, SHA in the result
file, raw capture NOT committed per the operator-data ruling);
**three audits** by the measurement-skeptic (FAIL 11 → FAIL 9 → PASS,
chain kept in the record); **result** (`ca8c581`).

**The verdict: BLIND, on a covered-winner denominator of 1** —
`docs/measurements/2026-08-21-h4-channel-diagnostic-result.md`. Per the
consequences fixed before the pull: **Look 2 is written up early as
BLOCKED ON INSTRUMENT** (`2026-08-21-h4-settlement-fee-result.md`),
**Look 3 is cancelled, the series is closed**, the analyzer is never
built, ADR 0027 stands, H4 stays UNTESTED. Reopening has exactly one
door: A17.11's different-channel amendment (candidates named there).
**The audit's finding worth reading:** the pull's own fills section shows
the balance channel reconciling 15 of 16 fills to half a tenth, and a
+4950-tenth movement in the winner's own payout window 1h31m *before*
settlement — the registered tolerance cannot credit it, and the pull
cannot separate "paid early at position close" from "position closed, no
credit due". That is why BLIND extends to no claim about the venue.

Also this session, all committed and pushed: **`h4-balance-spans`
shipped** (`349dca0`, six window-mutation guards red — it fed the
diagnostic its one registered pull and now stays unused); **README's
combo row corrected** (`5aa39ef`, the public repo carried a refuted
reason); **the stopped study's form demoted** (`d487d2d`: Log's nav slot
retired, `/estimate` reachable from the footer with the terminal banner,
and `classify_positions` now bounds the study window on the right at the
owner stop — guard red both ways); **ADR 0059** (`45735e4`); the
unit-mismatch lesson (`6a8092e`).

**TONIGHT'S HANDOFF — the terminal spread/total look, 22:40:00Z:**

1. Registration: `2026-08-21-preregistration-spread-total-edge-second-look.md`
   (+ its Amendment 1). Band **22:35:00–22:45:00Z**, 4 credits, floors 8
   sharp rows / 3 games per arm, NO pooling with look 1.
2. **Joe holds a veto until the anchor.** A veto before the sweep spends
   nothing and is recorded as VETOED; after a successful sweep there is
   no veto — the look is the look.
3. Before the anchor, run the free replay gate:
   `.venv\Scripts\python.exe scripts\measure_spread_edge.py --replay
   docs\measurements\2026-08-20-spread-sweep-raw-2026-08-20T212616Z.json`
   — it must reproduce look 1's numbers exactly or the anchor is not
   taken (INSTRUMENT FAULT).
4. Inside the band, run the sweep. **Every branch — including VETOED and
   UNTAKEN (band lapses, vendor closed, 401) — writes**
   `docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`.
5. Session timers cap at 1h and die with the session; if no session is
   alive in the band, the look goes UNTAKEN and that too is written up.

**TWO QUESTIONS FOR JOE — ANSWERED 2026-08-21 (~03:45Z), verbatim:**

1. How many open Kalshi positions right now? — **"1"**
2. Are you still placing bets? — **"here and there. not much. just some
   fun parlays."**

So the drying-up branch did NOT fire: winners will still trickle in,
occasionally, mostly KXMVE combos (multi-leg, so outside the stopped
study's scope anyway). This changes nothing already decided — the H4
series stays closed on its own ground (BLOCKED ON INSTRUMENT), the
recorder keeps running because it costs nothing — but a future partner
triage should know the account is quiet-but-alive, not dead.

**Still open, in order:** the `/api/ledger` `commence_ms` defect (partner
ranked it last, "droppable without guilt"; the 3-hour-offset trap is
documented in the 2026-08-20 entry below), and the footer's 5-and-5
parity note (the next screen the nav sheds must answer the delete-commit
question, not land in the footer by default —
`tests/test_every_screen_is_reachable.py` docstring).

---

## 2026-08-21 ~02:00Z — h4-balance-spans ships with its guards red, and both deploys landed

State: tests **3,745 passed / 10 xfailed** (+6 new guards, +2 parametrized
whitelist tests), ruff clean. Pushed `349dca0`; live deploy dispatched (run
32438057600 — the dispatch went through in auto mode this time, first try).

**Open item 1 (the waiting deploy) closed itself before this session acted:**
live was already on `aee4b5a` at 01:47Z, so Joe ran the dispatch. The only
commit live then lacked was `30f1c2e`, docs-only.

**Open item 2 is DONE: `h4-balance-spans` shipped (`349dca0`).** Amendment 1
A12.3's instrument: sections A–D as `h4-settlement-balance` but filtered only
by each table's own clock ≥ study start — no ±900s `EXISTS` window, because
the span design has no window — plus section E, the **whole**
`venue_settlements` table (P_j sums every settlement inside a span,
pre-study included; a study filter there would silently zero prediction
terms). No join, no delta, same discipline. Six window-mutation guards in
`TestH4SpansAreUnwindowedAndUnjoined`, **each verified red**: `>=`→`>`,
study filter dropped, `EXISTS` window re-added to balance or fills, poll
endpoint filter dropped, E gaining a study filter. File restored
byte-identical after each mutation. **A12.4's fallback cap on Look 2 is
discharged.**

**What Look 2 still needs before the 2026-09-03 pull, and it is the next
H4 work:** the analyzer change (A9 seven-branch aggregate tree, A10 E7 +
positive-control gate, A11 early-credit scan, A12 span pairing/residuals)
committed **before** the data exists, as Look 1's was (`4dbd3e2`). Nothing
about it is blocked; the registration specifies it.

**Still open, unchanged:** the `/api/ledger` `commence_ms` defect (item 3
below, low urgency, 3-hour-offset trap documented), and the terminal
spread/total look at 22:40Z tonight (armed; Joe holds the veto).

---

## 2026-08-21 ~00:20Z — H4 Look 1 is taken and moves nothing, tomorrow's terminal spread look is armed, and one deploy waits on Joe

State at close: tests **3,737 passed / 10 xfailed**, ruff clean, tsc clean,
CI green on `883c884`+; live on `1539f76` — **one deploy behind, see the
first open item**. The partner convened at session start and set the list;
all six items are done or armed.

**H4 Look 1 is TAKEN and recorded** —
`docs/measurements/2026-08-20-h4-settlement-fee-result.md` (`883c884`).
Chain, in order: registration `4e0a025` (23:13Z), analyzer pre-committed
`4dbd3e2` (23:29Z), pull 23:44:23Z, two measurement-skeptic audits (first
draft FAILED on six defects, second on one — the record carries the
corrections). Verdict per kind: single-kind UNDERPOWERED (1 cluster),
combo-kind **S1 UNTESTABLE (W = 0)**. **H4 stays untested, ADR 0027
unchanged, no U2 figure is a bound** — the pull's own positive control (a
$5.00 predicted credit, observed $0.00) shows the balance channel did not
respond inside ±900s, which is E6's structural blindness: a flat balance
passes "stopped moving" whether the credit settled or never came.
**Amendment 1 (`9bc9dad`) now governs Looks 2–3**: total seven-branch
aggregate tree (A9), E7 + a positive-control gate (A10), the early-credit
scan (A11), span-based windows replacing ±900s (A12, with a registered
fallback: if the `h4-balance-spans` query has not shipped by 2026-09-03,
Look 2 runs the old design **capped at UNDECIDABLE-COVERAGE on winning
clusters**), and the consequence of each §6.1 answer (A13 — no answer
changes any verdict). The raw pull is operator data: NOT committed, held at
`data/captures/h4_look1_pull_2026-08-20T234423Z.json`, SHA-256 in the
result file. **One tension flagged for Joe in the result file:** the
cluster table carries derived position facts (tickers, counts, win/loss);
if he rules even derived aggregates out, the table moves private.

**The terminal spread/total look is armed for 2026-08-21 22:40:00Z** (band
22:35–22:45Z, 4 credits, **Joe holds a veto until the anchor**).
Registration `5f890b5` + Amendment 1 `5438d9b`: the replay gate first
FAILED by its letter (row counts 3/4 vs 11/12) because its premise
conflated matched with sharp-anchored games; the pre-registrar ruled the
premise wrong and the instrument right — all five edge values, sharp
counts, games and verdicts reproduce exactly, all 16 dropped rows non-sharp
— and restated the gate stricter. The instrument
(`scripts/measure_spread_edge.py`) carries the three permitted edits:
per-game commence window [taken_at+15m, +12h] with counters, 08-21
filenames, the new registration name. Floors unchanged (8 sharp rows / 3
games per arm); NO pooling with look 1; totals arm registered as
more-likely-than-not UNDERPOWERED again. Every branch — including VETOED
and UNTAKEN — writes
`docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`.

**§6.1 QUESTION PENDING FOR JOE (H4):** did you deposit, withdraw, or
transfer money in/out of Kalshi around **2026-08-18 14:51–14:56 UTC
(~7:51–7:56 AM PT Tue)**, or anywhere on 08-18/08-19? Answer goes into the
result file dated; per A13 no answer changes any verdict, so no urgency.

**Open items, in order:**

1. **Live is one deploy behind.** `6cef368` makes the phone's estimate page
   tell the truth about Amendment 2 (study stopped by owner; it currently
   renders "$X of $100" as if live). My live dispatch was blocked by the
   permission classifier (tried once, per rule). Joe: GitHub app → Actions
   → Deploy → Run workflow → instance `live`, type `kalshi-cockpit`. Or a
   future session tries the dispatch once again.
2. **`h4-balance-spans` whitelisted query** (A12) — ship before 2026-09-03
   or Look 2 self-caps. Code-change-sized; the registration specifies it.
3. **The `/api/ledger` `commence_ms` defect** (below, 2026-08-20 entry) —
   unchanged, low urgency, 3-hour-offset trap documented.
4. **Analyzer E1–E6 had zero test coverage at look time** — fixed same day
   (`tests/test_analyze_h4_look.py`, 15 tests, two guards mutation-red),
   noted here because the first result draft *claimed* coverage that did
   not exist and the skeptic caught it. Pattern already in lessons.md
   (git-state claims; this is the test-state twin).

Also this session: the probe key-leak fix + corrected lesson (`450557a`),
the secret-scan false positive on the test's own fake key (`5a047b8`,
nothing real, nothing rotated), four findings recorded (`8358c9b`: ADR 0058
observation note, ADR 0054 5GB-ceiling amendment + fly.live.toml correction,
ledger defect filed), housekeeping (`1202d6e`: two discharged bullets
struck, v16 watch killed as unreachable, stored-number lesson written).

---

## 2026-08-20 ~21:35Z — the spread test is TAKEN: UNDERPOWERED both arms, and the partner's list is the open work

**The registered spread/total test ran at 21:26:16Z**, inside the window, 70
min before first pitch, 4 credits.
`docs/measurements/2026-08-20-spread-total-edge-result.md` + raw/rows
artifacts beside it. **Verdict per the registered floor: UNDERPOWERED on
both arms** (3 sharp-anchored spread rows, 2 totals, against a floor of 8) —
no pass, no fail, the ADR 0038 quadrant row unchanged. All 5 sharp rows were
negative at the charged fee; that is a description under an UNDERPOWERED
verdict, not a finding, and the result doc says so. A second look on a
fuller slate (≥5 games, ~1.7 sharp rows/game observed) is a NEW
authorization, not a continuation — the convening bought one sweep.

**Protocol notes worth keeping:** the first attempt 401'd on a stale local
`ODDS_API_KEY` (no spend); Joe fixed `.env` and the sweep ran five minutes
later. The 401 traceback printed the dead key into the transcript —
`raise_for_status` embeds the URL — and the instrument now fails with the
status alone (`095c1e9`, lessons.md has the pattern; other capture scripts
still share it and are owed a sweep). The new key sits on a 20K/month plan
per the vendor counter (1336 used), which changes the credit arithmetic
whenever a bigger look is authorized.

**ADR 0058 landed (partner-approved, `e6ba046`):** the per-series fee
(`fee_multiplier` 0.5 MLB) corrects **settled PnL only**
(`settlement.py:244`). Guards stay on 0.070 — a cost correction cannot
create an edge. `fills.fee_predicted` is excluded because
`_fee_model_verified` (`gate.py:738-748`) reads it and correcting it would
decide ADR 0043's open hand-fills question permissively as a side effect;
`recommendations.fee_predicted` is excluded because engine.py computes it
and the gate's edge from one EV object. **Not yet implemented** — the
implementing commit must add a fee-regime marker to `settlements` (or
append its SHA to the ADR as the basis boundary) and the ADR 0058 tripwire
test.

**The partner's execution list is DONE, all four items** (~21:45Z):
(1) ADR 0058 implemented in `3b572c5` — migration **v16** adds
`settlements.fee_model_used` (NULL = pre-v16 flat regime), the settlement
pass reads `/series/{ticker}` live and tags every row
(`series_mult_0.5:override_unchecked` / `flat_0.070:series_unread`), fees
take keyword-only `fee_multiplier` refusing outside (0,1], both tripwire
halves armed and mutation-red; suite 3,718 passed. **NOT yet deployed —
deploy after the 22:21Z window closes, before WNBA 22:45Z if possible.**
*(Done 22:26Z: live is on `1539f76`, healthy, v16 ran at boot. The first
`h4-settlement-balance` pull works on live: 13 post-study settlements, a
flat balance beside the 08-18/19 cluster then $8.31 on 08-20, ZERO fills
inside any window -- no fill confound -- and every balance poll ok=1. The
H4 subtraction itself is NOT taken: it needs a pre-registration first,
and the pre-registrar owns that. ~~The next session should also watch the
first settlement row written under v16 for its `fee_model_used` tag --
that is the implementation's one live observable.~~ **Watch KILLED by the
partner 2026-08-20: the `settlements` table is fed from `orders`, and no
order has ever been placed (`ORDERS_ARE_DRY_RUNS = True`), so the row this
watch waits for is unreachable — it would idle forever.**)*
(2) ADR 0027 carries the dated denominator correction (`e3986fb`).
(3) `h4-settlement-balance` shipped (`a02e8d2`), four sections, no join,
three guards mutation-red — run it after the deploy for the H4 read and
the ADR 0027 re-derivation. (4) `orders()` logged as the fifth zero-caller
instance (memory + ADR 0027 correction, grep-verified). Killed by the
partner, do not revive: per-series fee on any guard path, stale-book devig
exclusion, generic UX polish, anything gated on H4 or beta.

**Joe decided: the calibration study is STOPPED** (~22:05Z, "just scrap
it. I am a newbie bettor."). Amendment 2 on the registration records the
terminal state — STOPPED WITHOUT RESULT, nothing scored, machinery kept
(`ed9dd03`). Follow-up for a future partner triage, not urgent: whether
the phone UI's estimate form should come out now that nothing consumes
it — a form feeding a stopped study is quiet misdirection.

Also open, unchanged: the two `parse_portfolio_value_tenths` defect notes
(portfolio_poll.py:252-266) — the partner re-examined them 2026-08-20 and
ruled them NOT H4 blockers — and the `fee_multiplier_override` field no
backend code reads (ADR 0058 hole 2; observation note appended to the ADR:
absent from 24/24 events in the one committed sweep).

New open item, found 2026-08-20 (code-change-sized, no ADR; low urgency —
no frontend consumer reads it — but it sits on the registered evidence
route): **every `/api/ledger` row carries `commence_ms: null`.** The route
(`backend/api/routes.py:1260`, SQL ~1404-1412) joins only `fair_prices`,
never `kalshi_events`, yet `_serialise` (`routes.py:3563`) emits the key
anyway — the exact null-pretending-the-join-was-attempted anti-pattern the
same function's `methods` block was built to avoid. A consumer cannot
distinguish "never joined" from "event unknown", and pre/post-commence
bucketing (the axis behind the clv-coverage denominator error) silently
returns nothing. **Trap for the fixer:** `kalshi_events.commence_ms` stores
the RAW `occurrence_datetime`, which runs exactly 3 hours late (ADR 0006;
the −3h correction lives in `scripts/inspect_live_db.py:1141-1148`) —
adding the join without deciding the offset ships a second defect.

---

## 2026-08-20 ~19:45Z — the dropouts are diagnosed, the zero is verified, and the spread test is armed for 21:21Z

State when this was written: tests 3,675 passed / 10 xfailed, tsc clean, live
on `faa46b9` (deployed ~19:20Z via the dispatch, which went through in auto
mode this time). The 21:21Z–22:21Z MLB window had not yet opened; the session
timer is armed to fire `measure_spread_edge.py` at ~21:26Z.

**The top open item is closed: both mid-window cadence dropouts are one
mechanism, and nothing is broken.**
`docs/measurements/2026-08-20-cadence-dropouts-are-the-freshness-floor.md`,
with two committed retrospective pulls beside it. Short version: a new book in
the feed, `everygame`, sat on all 9 MLB fixtures with a `last_update` stamp
~13 minutes behind each sweep, so every fixture's oldest-book age crossed the
900s limit ~2 minutes after the sweep, `is_open` correctly flipped False, and
the cadence correctly took ADR 0057's bounded sleep to the next refresh.
Dropout 2's "468s matches nothing cleanly" matched to 3 seconds once the
bound was computed from the actual 16:16:37.974 sweep instead of the nominal
minute. Two corrections recorded: the flag was NOT stale (the handoff's
hypothesis is refuted — `interval_s()` runs after the assignment), and the
in-pass "window is open" lines are `decide_sweeps`' *slot* view, a different
quantity sharing a word with the freshness flag. **No code change was made
and none should be made without an ADR**: excluding stale books from the
consensus alters the devig population (rule 2), and the alternative —
accepting that the effective window is `900s − laggard_lag` — costs only
passes that would (on the likely, unverified branch) have confirmed
suppressed rows. The sliver closed the same evening: `book-rows`
(`481d772`, deployed) shows everygame two-sided on all 9 fixtures in both
sweeps, so it contributed to the runner's consensus, `odds_age_ms` read
>900s alongside the window flag, and **the sleeps cost zero live coverage**
— every row was suppressed `stale_odds` throughout. §4 of the doc has the
rows.

**CI was red from ~14:30Z to ~20:00Z and the cause predates this session.**
`tests/test_series_fee_multiplier.py` (convening item 9) read the raw fills
capture under a docstring claiming it was "tracked in git"; it never was
(`data/` is gitignored, the force-add never happened), so the suite passed
only on Joe's machine and failed in CI on every push since it landed. Fixed
in `9eb699f`: `scripts/sanitize_fills_capture.py` derives a committed
fixture carrying exactly the six consumed fields with pseudonymous
`order_id`s — the raw capture's account-linked identifiers (order/trade/
fill ids, subaccount_number) stay out of the public repo, and every
retained value was already public row-by-row in the 2026-08-14 attribution
doc. **Superseded ~21:05Z by Joe's ruling: operator account data never enters
the repo, sanitized or otherwise — anticipate operators other than the
author.** The fixture and sanitizer are removed (`fc88a31`); the fills
prediction now runs only where the private capture exists and skips loudly
elsewhere (verified both ways: 3 passed/4 skipped without, 7 passed with).
Open sliver, Joe's call if he ever wants it: the sanitized fixture lives on
in public git history (9eb699f..2aebfaf), and the same values sit in the
committed 2026-08-14 attribution doc — a history rewrite is pointless
without redacting those docs too, so nothing was rewritten.

**The suspicious zero is verified benign, row by row.** New whitelisted
`estimate-match-status` query, run against live: all 35 positions are
`out_of_scope` and correctly so — 12 combos (multi-leg), 23 singles of which
22 pre-date the study start and the one post-study single is
`KXEARNINGSMENTIONKLAR` (not sports). `position_unlogged = 0` is real: no
sports single-leg venue position exists inside the study window at all. The
one `bet_estimates` row has `match_status` NULL, which is the designed
"pending" state (24h window open or result not yet known), not a fault.

**The ~585 MB question has its first observation, and it is a level, not a
leak.** `docs/measurements/2026-08-20-the-585mb-is-a-level-not-a-leak.md`,
raw samples committed. New read-only `/proc` reader
(`scripts/inspect_live_proc.py`, `a41f20e`, deployed) sampled the loop's RSS
every 45s across three full passes on the freshly booted box: the first full
pass builds ~583 MiB within a minute of boot, the level is dead flat between
passes (17 min), and passes 2 and 3 moved it +61 then −55 MiB — a breathing
band, no monotonic growth. Consistent with the `raw_events` materialisation
suspect but does not name it (RSS is a size, not an inventory). Not urgent
at 2 GB; the number to carry is ~644 MiB as the loop's per-pass ceiling.
CI is green again as of `a41f20e`.

**Tooling shipped for both** (`faa46b9`): `window-freshness --at <ISO|ms>`
(fixture ages per the production measure, then per-book stamps, stalest
first — the retrospective instrument for any future "why did the window
close" question) and `estimate-match-status` (the §7.5 coverage cells).
Four guards mutation-verified red. The mutation-testing byte-restore gotcha
bit again — `write_text` on Windows rewrote every line ending; restored from
the byte copy, which is why the backup rule exists.

---

## 2026-08-20 ~17:00Z — the gate is measured, the product has a plan, and a slice is built but NOT deployed

**The window-gate fix passed its measurement. All four registered observations,
plus the 12-hour stability watch, separately.**
`docs/measurements/2026-08-20-window-gate-observations-result.md`; the durable
evidence is the committed sweep-log pull beside it. Headlines: first pass
**+6.9s** after the 15:26Z open (pre-fix worst case 900s); 3 in-window full
passes all `quotes_pruned: 0` against a backlog proven live by the **8,148-row
prune 45 seconds after the close**; 0 early wakes all day; 0 restarts since the
03:54Z deploy.

**The top open item is new: two mid-window cadence dropouts, same signature.**
15:28:50→15:34:54 (370s) and 16:18:49→16:26:34 (468s) — healthy quote pass,
total log silence, healthy quote pass, pass numbers consecutive, every in-pass
decision reading `window is open`. The first dropout's arithmetic lands exactly
on the bounded-sleep branch (369.7 × 1.15 = the 15:36:00 refresh), which only
runs when `tempo.window_open` is False — **the cadence still reads the flag
assigned at the END of the previous pass**, the same staleness family fix 1
cured at the prune. Cost: ~14 min of a 60-min window. Unexplained; do not
force-fit the second dropout (468s matches nothing cleanly). Start at
`scripts/run_loop.py`'s end-of-pass `tempo.window_open = window.is_open`
assignment and what it evaluates against.

**The fleet convened (Joe called it) and the plan is recorded:**
`docs/reviews/2026-08-20-fleet-convening.md`. Ten items, blast-radius first.
Items 1–3 are BUILT, tested, and green locally — **not deployed**:

- **Item 1** — `estimate_match` no longer stamps "he did not bet" on evidence
  of nothing. Amendment 2 (A10–A12) is in the registration *before* the code;
  schema **v14** adds `match_status_ms`; the absence proof is
  window-closed ∧ result-known ∧ settlements-poll-postdates-knowing;
  `absence_pending` rows stay matchable; the A12 repair pass is **self-running
  and self-extinguishing** inside `run_match_pass` (pre-amendment stamps are
  `unmatched_no_position` + NULL ms). Three guards mutation-verified red.
  **After deploying, read the `A12 repair pass:` log line and reconcile its
  counts** — that is the repair's one observable.
- **Item 2** — `/gate` now says its caps cannot see hand bets (they are
  structural: `settlements.order_id` NOT NULL → orders only).
- **Item 3** — `/` now lands on the **Slate** (re-export, so the two routes
  cannot drift); the Board moved to `/board`; nav reads **Games / Picks /
  Log / Ledger**; `/slate` still served, linked from the Footer. Five python
  test files followed the Board to its new path.

Also this session: migration-undo order in `tests/test_store.py` corrected to
descending (it was right only while no later migration touched a rebuilt
table), and `migrate()` skips a column-add on a mid-migration-missing table
(v11 drops `bet_estimates` for schema.sql to rebuild in the same boot).

**Superseded the same evening — the deploys happened and the plan is nearly
done.** Live is on `99e10c3` (four deploys today: 03:54Z the gate fix, then
items 1–3, then 4–6+10, then 7), migrations v13→v14→v15 ran clean, and the
A12 repair found **zero falsely-stamped rows** — the bug was fixed before it
bit the live data. Items **1–7, 9, 10 of the convening plan are BUILT AND
DEPLOYED**; item 8 (the registered spread/total test,
`docs/measurements/2026-08-20-preregistration-spread-total-edge.md`) has its
instrument shaken down free (`scripts/measure_spread_edge.py`, `--replay`
mode) and fires inside the 21:21Z window.

**The finding of the day is item 9:** Kalshi's public `/series` metadata
carries `fee_multiplier` — 0.5 on both MLB series, 1 on ATP/WNBA — captured
as `tests/fixtures/series_fee_fields.json` and verified by predicting **all
11 attributed fills to $0.0001** (`tests/test_series_fee_multiplier.py`).
That is the durable source ADR 0028 said was missing; moving
`TAKER_COEFFICIENT` or making the fee model read per-series is now an
ADR-sized decision with evidence, not a guess.

**One suspicious zero to verify next session:** the first `classify_positions`
pass stamped all 35 venue positions `out_of_scope`, 0 `position_unlogged`.
The benign explanation checks out locally — every post-study-start fill in
the committed capture is a KXMVE combo (multi-leg → out of §2's population)
— but the live table's later settlements were not directly inspected.
Add a whitelisted `inspect_live_db.py` query for `estimate_match_status`
at the next natural deploy and read the composition; a zero in the
denominator's most interesting cell is checked, never believed.

Also still open, unchanged: the two mid-window cadence dropouts (top item,
above), the ~585 MB holder, `unmatched_events` growth. Nothing below this
line is newer than 2026-08-20 03:00Z.

---

**THE JOB IS DONE AND UNVERIFIED. Your job is the verification.**
*(Superseded 17:00Z — the verification above is taken. Kept for the
correction it carries about the second prune route.)* The window
gate was fixed in two commits on 2026-08-20 (~03:30-04:00Z) and deployed to live
before the betting window opened. **ADR 0057.** Nothing about it has been seen
running.

- `6b0b7ee` — the prune asks whether a window is open **at the prune**.
- `a1d0242` — a closed-window sleep is **bounded by the next window-open time**.

**The correction worth carrying forward:** the handoff described fault 1 as a
stale flag, which was the measured incident and was real. Reading the function
showed a **second** route it had not named — `run_once` fires the odds sweep and
*then* prunes, and the sweep is what opens the window, so a full pass that opens
a window prunes inside the first ~40-94s of it every time. A fix that read the
window at the top of the pass would have shipped green and left the likely
*dominant* case running. The gate is now read at the use, not at the top.

**READ THE REGISTRATION BEFORE LOOKING AT ANY LOG.**
`docs/measurements/2026-08-20-window-gate-plan.md`, written before the code
changed. Four observations are registered against the `baseball_mlb`
15:26Z-16:26Z window; do not choose new ones after seeing the output.

    1. no `quotes_pruned` > 0 on any pass stamped 15:26Z-16:26Z   (falsifies fix 1)
    2. first pass after 15:26Z within ~17s of it, not up to 900s  (falsifies fix 2)
    3. `window_open` latches true within one pass of 15:26Z
    4. passes stay ~900s apart BEFORE 15:26Z, except 2-4 in the last ~15 min

**Observation 4 is the one that catches this fix going wrong**, and it is the
one that will look like a bug if you have not read the registration. Two to four
extra quote passes in the quarter-hour before a window are *designed*: the sleep
bound recomputes and converges. More than that, or early wakes with no window
coming, means the "already due" spin guard has failed and it is burning Kalshi
requests — see ADR 0057.

**The null result to watch for.** If no window opens at 15:26Z at all — empty
slate, or the odds budget is spent — then observations 1-3 have no denominator
and this is **untested, not confirmed**. Check `next_sweep_ms` and
`sweeps_remaining_today` on `/api/health` before reading a quiet window as a
pass. `tempo.next_wake_ms` is now published in the loop's exit-state line and in
`as_dict`, which is how an early wake is told apart from a random one.

**The 12-hour stability watch rides on the same deploy and is a SEPARATE
observation.** It must not be reported as evidence for either fix.

**CI was red and is green again, and it was never the window gate.** An email
alert at ~04:15Z flagged `Tests + warehouse` failing. The identical two failures
were already on `0d18825` and `82b47c6`, both pre-session, so the gate commits
did not cause it. Fixed in `82cd2aa`; run 32331675208 is green on all three
jobs. **Live was not redeployed** — CI runs on push, Deploy is dispatch-only, so
the box has been on `5656133` and untouched since 03:54Z.

**The finding underneath it is worth more than the fix, and it touches config
rather than tests.** `credits_per_sweep_per_sport` is
`len(markets) * len(regions)`, read from the environment via `load_dotenv()`, so
the tests were measuring whichever `.env` the machine held. The values they
passed under **run on no instance**: `flyctl secrets list` shows `ODDS_API_KEY`
alone and `fly.toml` sets neither variable, so **live takes the `h2h` default and
a sweep costs 2, not 6**. CI was accidentally right. `conftest.py` now pins both
variables to the `.env.example` contract.

**The `.env` divergence is reconciled.** Joe's local `.env` carried
`ODDS_MARKETS=h2h,spreads,totals` against `.env.example`'s `h2h`; he chose to
match the contract, and it was changed on 2026-08-20. Laptop, CI and live now
all compute a sweep at **2 credits**. Nothing was committed — `.env` is
gitignored, which is exactly why the drift was invisible for the life of the
project. `conftest.py` pins both variables regardless, so tests do not depend on
it either way.

**Live sets neither variable**, so its values are the *defaults*: `flyctl secrets
list` shows `ODDS_API_KEY` alone. Absence is the config, and that is the part
that is easy to misread as "unset means unused".

Everything else below is open and none of it is urgent.

### Live state at 03:00Z 2026-08-20, verified not inherited

`8efc706`, 2 GB, healthy. Both instances current, nothing unpushed.

```
quote passes     3.0-3.2s        MemAvailable   951 MB
full passes      33-114s         page cache     1.0 GB
IO pressure      avg60 0.00      disk           1.9G/4.9G, 39%
link slow / OOM  0               unmatched_items 494 rows
```

**Two numbers that look like faults and are not.** Meet them before you
investigate them:

- **`recorder.age_ms` of 637,514.** The window was closed, so the loop is on its
  900s slow cadence and runs *no quote passes at all*; age climbs toward 900s
  and resets. Verified against the log — last pass 02:50:05, read at 03:00:28.
  **Check whether a window is open before reading a high age as a fault.** Third
  session to meet this.
- **`MemFree` of 69 MB** (23:19Z reading). Linux spends spare RAM on page cache.
  **Read `MemAvailable`, never `MemFree`** — the naive read says "69 MB left" and
  reopens a closed investigation.

**ADR 0055 is correct as well as fast, checked 23:19Z.**
`dropped_no_kalshi_quote` is **0** — absent from the pass line and not in
`runner.py`'s `ALWAYS_REPORT`, so absent means zero, read in the code rather than
assumed. `suppressed` was 8 beside 20 recommendations on a sweep pass, so the
pipeline decides rather than sleeps. **The live Board itself was NOT read** —
`/api/slate` is 401 and Chrome is still blocked on the live host.

**A CORRECTION LANDED AT 22:10Z AND IT IS THE MOST IMPORTANT THING TO READ.**
`2026-08-19-the-prune-loses-to-the-writer.md` claimed the prune *"cannot win at
any schedule"*, ceiling 3.84M rows/day. **That was the memory starvation
measured a second way and written up as an independent finding.** The 40,000-row
prune was not a config limit; `budget_s` buys as many batches as fit, and the
20s batch cost was the symptom. With memory the same prune clears **440,000** in
one pass and the table shrinks **11.2M rows/day**. The file is marked superseded
in part; ADR 0055 stands on its *second* premise (84.5% of writes carried no
information) and its first must not be cited onward.

**The pattern, which is the actual lesson: every number taken from a degraded
system describes the degradation.** Three numbers were taken off a box minutes
from an OOM kill and only one was suspected of being a symptom.

**Still open, in the order they are worth doing.**

- ~~**`unmatched_events` is the next table with this shape.**~~ **DISCHARGED
  by ADR 0056 — the table was drained and dropped, verified absent from live
  `sqlite_master`/`dbstat` on 2026-08-20.** This bullet outlived its fix and
  cost a recon agent to re-eliminate; deleted as work, not tidying.
- ~~**What holds the ~585 MB is still unverified**~~ **MEASURED 2026-08-20:
  it is a level, not a leak** —
  `docs/measurements/2026-08-20-the-585mb-is-a-level-not-a-leak.md`. Killed
  by the partner as a line of work; the number to carry is ~644 MiB per-pass
  ceiling on a 2 GB box.
- **The 84.5% dedup is a property of the slate, not of Kalshi.** College
  football and NFL are 57% of today's markets at 98-99% unchanged; today's
  baseball runs 51-74%. As sports come into season the saving falls. Re-measure
  when NFL/NBA start rather than assuming.

**Do not re-derive these; they were eliminated by measurement today.**
`priceable_series` (`kalshi_events` holds 1,590 rows; `leg_series_ms` reads **0**
on live), the WAL (flat at 51.6 MB), and the store leg's `upsert` half
(**38-44ms** against `quotes` at 82-193ms — the split in `0c609de` answered the
question it was built for).

**Deploying works and needs two flags.** `gh workflow run deploy.yml -f
instance=live -f confirm_live=kalshi-cockpit` — the guard rejects the dispatch
without the second. In auto mode the classifier blocks live deploys, `flyctl
machine restart` and `flyctl scale`; Joe switches to manual on request. Say it
once and ask.

Also open, and now measured rather than suspected:

- **ADR 0054's latency half is UNRESOLVED**, by its own registered rule. The
  table lost 28% of its rows and the prune-free store leg did not move
  (before 5997/14030 at 6.9M, after 9164/14345 at 4.9M — n=2 a side). Do not
  write it up as confirmed *or* refuted. The **disk** half stands — the DB
  file is flat at 1546.4 MB — but **that is not evidence the table stopped
  growing**, and it was read that way. ~25% of the file is freelist being
  reused, so the row count can climb behind a flat file size. Size on disk and
  rows in a table answer different questions. **The +6.4M/day this used to
  quote is superseded** — after 2 GB and ADR 0055 the table *shrinks* 11.2M/day
  (written 2.25M, pruned 13.47M). See the CORRECTION at the foot of
  `2026-08-19-the-prune-loses-to-the-writer.md`.

**Health check flapping: the keep-alive fix is sound and live has failed
checks again anyway.** Both are true and the order matters. The fix was two
hops each defaulting to a 5s keep-alive against a 15s check —
`KEEP_ALIVE_TIMEOUT=50000` for Next and `--timeout-keep-alive 75` for uvicorn,
in `docker/entrypoint.sh` — measured at 0 failures of 12 where it had been 5 of
10. `docs/measurements/2026-08-19-health-flap-is-the-proxy-hop.md`.

**The sentence that used to sit here — "no Fly check failure since the 15:30Z
deploy" — stopped being true at 18:36Z**, and it is corrected rather than
deleted because the correction is the useful part. Seven failures fell between
18:36Z and 18:52Z and were followed at 18:59:16Z by an OOM kill. That is the box
dying, not the keep-alive regressing. **Do not re-open the keep-alive fix on
this evidence, and do not re-attribute it to CPU or long passes either** — the
backend answered 50 of 50 probes while IO pressure hit 90%.

The general shape, which is why it is worth the space: **a verified fix stays
verified for the failure it was measured against, and the same symptom can
return for a different reason.** A green measurement is not a standing
guarantee, and "we already fixed that" is how the second cause gets missed.
records the wrong fix that shipped first and why its reasoning read as sound.

Everything else is done and none of it is urgent: ADR 0047's plan is fully
discharged (gloss = ADR 0050, strip = ADR 0051, phone = ADR 0052), and ADR 0038
closed the hunt. `VACUUM` is **not** wanted: 25.2% of the file is freelist and
those pages are what is keeping it flat.

STOP AND ASK JOE: money-touching beyond standing approvals. Pushing and
deploying were both pre-approved on 2026-08-18. **The live deploy is blocked by
the auto-mode classifier** — demo goes through, live does not; Joe switched to
manual mode on request and it then worked. Say it once and ask, do not retry.
`gh workflow run` is NOT blanket-blocked: the heartbeat dispatch went through
where the live `deploy.yml` dispatch did not.

GOTCHAS, each of which bit: Bash heredocs eat backticks/backslashes — long
content via the Write tool, commit messages via `git commit -F <file>`. **Assert
your edit changed something**; a `str.replace` that matches nothing returns the
input silently, and it happened three times this session. **Mixed line endings**
— `frontend/src/lib/*.ts` is LF, `app/*/page.tsx` is CRLF; `docker/entrypoint.sh`
is LF. Anything touching `bet_estimates` goes in `schema.sql`, never a
migration. `git checkout <file>` wipes uncommitted edits — back up with a byte
copy before disabling a guard to verify it (lessons.md, top). Run `date -u`
before acting on any deadline sentence — a deploy took 40 minutes this session
and the window opened during it. `flyctl ssh console -C` works fine but always
exits `Error: The handle is invalid.` on Windows; ignore it, the output above it
is real.

Delete this box when its job is taken — a stale session-start box is a
handoff claiming work that is already done.

---

## 2026-08-19 ~23:20Z-00:30Z — THE FIXES HELD FOR 2H40M, NOT 12 HOURS; AND THE UNMATCHED QUEUE'S OBVIOUS FIX WAS AN OUTAGE

Two jobs. The watch is in the box above. This entry is the second one, and the
useful part is what the measurement stopped.

### ADR 0056 — the unmatched queue is one row per work item

`unmatched_events` had the shape ADR 0055 had just fixed for `kalshi_quotes`.
Measured on live:

```
total rows                              788,944
distinct work items                       1,376      <- 573:1
rows ever marked resolved                     0
```

The eight worst items had **2,477 rows each with exactly one distinct reason** —
out-of-season NFL and NCAA fixtures with no sportsbook counterpart, so the linker
fails on them every pass and will until those seasons start. 2,477 is the number
of passes since the last prune, not a coincidence.

**`resolved` is 0 on all 788,944 rows.** This is a queue meant to be worked by
hand and it has never been worked. `seen_count` is the fix's actual product:
"failed once during a rename" and "has failed every pass for a week" were the
same row repeated a different number of times.

Shipped: `unmatched_items`, identity `(side, identifier, league, detail, reason)`,
upsert on a `UNIQUE` index, retention on `last_seen_ms`.

### THE MIGRATION WAS BUILT, GUARDED ELEVEN WAYS, AND THROWN AWAY

The obvious change is a v14 migration collapsing the table in place. It was
written and every guard verified by breaking it. Then it was rehearsed against
live, which took two minutes:

```
COUNT(*)  over 788,944 rows        1.6 s
GROUP BY  over the same rows     229.4 s     <- 143x
DROP TABLE (181,154 pages)       217.6 s
```

**Migrations run at boot, before uvicorn binds.** That is a four-to-eight minute
startup under a health check that gives seconds — and the version stamp is
written only after the step succeeds, so a machine killed part-way re-runs it
from the top. **A crash loop on the volume that cannot be recreated**, which is
the v11 failure this repo already survived once.

So there is **no migration and `SCHEMA_VERSION` does not move.** `unmatched_items`
is created empty by `schema.sql`, the linker writes there from the first pass,
and `unmatched_events` is left where it is — drained by `prune_legacy_unmatched`
in ADR 0054's existing batched, budgeted, full-pass-only machinery, then dropped
**once empty**, when the drop is free.

**Do not "finish the migration".** There is nothing unfinished. A proposal to
collapse the old table in place must first answer the 229s.

### The timings are NOT properties of the disk, and the design does not care

They came off a box concurrently serving quote passes at ~50% IO pressure; the
rehearsal itself pushed `recorder.age_ms` from 5.9s to 28s. A quiet boot would be
faster by an unknown factor. **That was not re-measured, deliberately** — the
design chosen is O(1) at boot whether the disk is fast or slow, so the uncertain
number stopped being load-bearing. Do not quote 229s as a fact about SQLite.

### A guard came back green, and it taught the more useful thing

The mutation test for the migration's `GROUP BY ... COALESCE` **passed with the
`COALESCE` removed**. It seeded 500 all-NULL rows — and **`GROUP BY` treats NULLs
as equal while a `UNIQUE` index treats them as distinct.** The two clauses were
written to mirror each other and are governed by opposite rules. The `COALESCE`
only bites where NULL *and* `''` both occur. Both patterns are in `lessons.md`.

Found only because the harness was run. One of eleven, on the run that mattered.

### Verification

Suite **3,589 passed / 10 xfailed** (was 3,565), ruff clean. **12 of 12
mutations turned a guard red**, re-run after the redesign.
`docs/measurements/2026-08-19-the-unmatched-queue-is-573-to-1-duplicate.md`.

### STILL OPEN

1. **DEPLOYED AND VERIFIED ON LIVE.** Both instances are on `c41ce52`. The live
   dispatch **went through from here** this session, unlike the previous three —
   the classifier is not a standing block on `deploy.yml -f instance=live`, so
   try it once before handing it over. (A plain `curl` of `/api/health` was
   blocked minutes later in the same session, so the classifier's shape is not
   "live things" and is not worth predicting. Issue commands singly — a
   combined edit-commit-push was refused as a unit.)

   Boot was clean, which was the entire design goal: the deploy took 50s, there
   is no `no such table` and no traceback in the log, and passes came back at
   **2.8-3.8s**.

   ```
                        at deploy      +6 min
   unmatched_events      791,955       651,955     <- drain, -140,000
   unmatched_items             0           472     <- the whole work list
   seen_count (max/min)        -           4 / 3   <- upserting, not appending
   ```

   **472 rows at `seen_count` 4 is the proof, not the row count alone.** Under
   the old shape those four passes would have written ~1,880 rows.
   `last_seen_ms - first_seen_ms` is 156,031ms on the worst item: 2.6 minutes
   tracked across 4 sightings, in one row.

2. **THE DRAIN IS FINISHED.** `retention: unmatched_events is empty and has
   been dropped` appeared at ~02:33Z. `sqlite_master` now lists
   **`unmatched_items` only**. 788,944 rows removed across six prune-running
   full passes:

   ```
   00:37Z  791,955      02:16:44  full  113.7s  legacy_unmatched_pruned 180,000
   00:56Z  491,955      02:33:33  full   97.3s  legacy_unmatched_pruned 151,955
   01:06Z  331,955      02:50:05  full   33.7s  legacy_unmatched_pruned       0
   02:33Z        0                                     <- table dropped
   ```

   **A watcher polling every 10 minutes called this stalled, and it was not.**
   The count sat at 331,955 from 01:06Z to 02:07Z — an hour of nothing — because
   a `basketball_wnba` window was open and ADR 0054's gate correctly skips the
   prune while one is. **A drain that only advances between windows looks
   identical to a drain that has died**, and the thing that separated them was
   `legacy_unmatched_pruned` on the pass line, which had to be added first
   because it was computed and never reported. Read the pass line, not the row
   count, before calling this class of job stuck.

3. **`LEGACY_UNMATCHED_TABLE` is deliberately NOT removed yet**, against the
   previous entry's own instruction, and the reason is rollback rather than
   caution. A rollback to any pre-ADR-0056 image writes `unmatched_events`
   again and never creates `unmatched_items`; rolling forward with the drain
   still present clears it, and rolling forward without it strands a table
   nothing drains. The cost of keeping it is one `sqlite_master` query per full
   pass.

   **Trigger for removing it, so this does not become permanent:** the next
   session that touches `retention.py` for any other reason, or 2026-08-27,
   whichever comes first. It takes `prune_legacy_unmatched`, `_table_exists`,
   `PruneResult.legacy_unmatched_deleted`, `PassCounts.legacy_unmatched_pruned`
   and its `ALWAYS_REPORT` entry, plus `TestTheLegacyTableIsDrainedNotMigrated`
   and `TestTheDrainIsVisibleOnThePassLine`. `grep LEGACY_UNMATCHED_TABLE` finds
   the constant; the rest hang off it.
4. **The 12-hour watch still has not happened.** The box has now been up since
   00:55Z on `8efc706` with two deploys in between, so the longest unbroken
   run is ~2h. Health at 03:00Z: `MemAvailable` **951 MB**, page cache
   **1.0 GB**, IO pressure `avg60` **0.00** (was 52-55% before the drain).

   **`recorder.age_ms` was 637,514 at 03:00Z and that is not a stall.** The
   window closed at ~02:01Z, so the loop is on its 900s slow cadence and no
   quote passes run at all — age climbs toward 900s between full passes and
   resets. Verified against the log rather than assumed: last pass 02:50:05,
   read at 03:00:28. `sweep_decision` says the next slot is `baseball_mlb
   15:26Z`, twelve hours out. **Do not read a high recorder age as a fault
   without checking whether a window is open first** — this is the third
   session to meet it.
4. Everything from the previous entries: the window gate reading a stale flag,
   `QUOTE_PASS_DURATION_BUDGET_S`, Chrome's live-host permission, the digest
   leading with `x / 300`.

---

## 2026-08-19 ~16:20Z — THE 15:21Z TEST WAS TAKEN; THE STORE LEG IS INNOCENT, AND THE FLAPPING WAS NEVER THE BACKEND

Both questions the previous brief left are answered, and a third problem that
had been misattributed for three sessions is fixed and verified on live.

### The registered read, written before the window opened

`docs/measurements/2026-08-19-window-store-leg-plan.md`, committed 13:55Z.

**The brief named a test that could not answer its own question.** It said to
watch `leg_store_ms` on a **quote** pass — but every pre-ADR-0054 quote pass is
uninstrumented and carries `took_s` only, so that comparison has **no
before-side**. The isolating comparison is the **prune-free full pass**, which
exists on both sides: this morning's two first-instrumented passes predate the
prune, and a full pass inside an open window skips it (`runner.py:2102`).

### ADR 0054's latency half: UNRESOLVED, by the rule registered in advance

| when | rows | pruned | `leg_store_ms` |
|---|---|---|---|
| before | 6.9M | 0 | **5997**, **14030** |
| after | 4.9M | 0 | **9164**, **14345** |

9164 lands inside the before-pair's own spread, and the registered rule says
that is UNRESOLVED. **The table lost 28% of its rows and the store leg did not
detectably move.** Do not write this up as confirmed or refuted; n = 2 a side.

The **disk** half stands and is stronger than before: quotes 6.9M -> 4.9M,
unmatched 507k -> 357k, and the file has **stopped growing** (identical byte
size across reads). 25.2% of it is now freelist, which is an argument *against*
the open `VACUUM` item — those pages are exactly what keeps the file flat.

### The handoff's own question, answered, and it is not the store leg

`leg_store_ms` on 24 quote passes in the window: median **~4.5s**, range
2.9-8.8s, against a projected 8-12s. Only 2 of 24 reach 8s.

**`leg_price_ms` is the pass**: 12-20s of a 17-32s pass, on a **15s** cadence.
The loop logged "a QUOTE pass took 25.0s" throughout. Same overrun that took
live down yesterday, fourth leg to be blamed for it.

And it tracks the **window**, not the table — ~3s on every closed-window full
pass all morning, then 20031 and 30086 once the window opened, while
`markets_quoted` moved +9%. **Correlate, not cause.** The mechanism is written
down to be tested, not adopted. Time inside `run_pricing_pass` first; the two
legs that were settled on this incident were settled in minutes by timing.

### The window gate is one pass late — predicted in writing, then confirmed

The plan registered a falsifiable prediction: `run_loop.py:543` assigns
`tempo.window_open` **after** the pass, `:577` reads it **before**.

```
15:21Z    window opens
15:32:14  full  took_s  94.3   quotes_pruned 40000   <- pruned on a stale flag
15:46:48  full  took_s  51.2   quotes_pruned     0   <- gate latched
```

The stated falsifier (`quotes_pruned: 0` on that first pass) did not occur.
`51.2` against the morning's 90-172s also confirms the gate works once latched.
The same staleness makes the loop take up to 900s to notice a window at all,
which is the more expensive half. One fix, its own ADR, not taken here.

### THE FLAPPING WAS THE PROXY HOP, AND THE FIRST FIX WAS THE WRONG HOP

Three sessions attributed live's health-check flapping to CPU saturation from
long passes. It is not, and the disproof is direct:

- **Two of three failures happened while no pass was running.**
- The backend answered **50 of 50** probes on port 8000 — worst 1.6s — while IO
  pressure on the box peaked at **90%**.
- Fly checks **port 3000**, which is Next, not the backend.

Both hops pooled a connection and **both defaulted to a 5 second keep-alive**
against a 15s check, so the socket was always dead when reused. Driving it over
one reused connection: **5 failures of 10** at 15s, **0 of 10** at 3s, failures
alternating exactly. Nothing merely slow alternates.

**I fixed the wrong hop first and deploying is how I found out.** The proxy's
error line names port 8000, so uvicorn was fixed and shipped — and demo, running
that fix, still failed 5 of 10, unchanged. *Fixing the hop an error message
names is not the same as fixing the hop that is failing.* The real closer was
Node's `server.keepAliveTimeout`.

Shipped: `KEEP_ALIVE_TIMEOUT=50000` for Next (it has a **ceiling** too — Next
never raises Node's 60s `headersTimeout`) and `--timeout-keep-alive 75` for
uvicorn, so the inner hop outlives the outer. Floor is `interval + timeout +
10s`, absolute rather than a ratio, because what is absorbed is one *late*
check.

Verified on live after deploy: **0 failures of 12** at Fly's own 15s spacing,
and no Fly check failure since. Nine guards in
`tests/test_keepalive_outlives_health_check.py`, each broken and watched go red.

Suite **3,512 passed / 10 xfailed**, ruff clean. Live and demo both on
`c77c35b`.

### ADDENDUM 16:50Z — THE SPLIT SHIPPED AND CAUGHT IT THE SAME HOUR

`leg_price_ms` was split into `setup / link / judge / persist` and deployed at
16:34Z. The slow state returned on its own at 16:48Z, window unchanged, and the
split named it immediately: **`leg_price_link_ms`, 2.1s -> 20.7s, 90% of the
slow pass, while walk and store do not move at all.** Same 531 events in both
states. The transition is one pass wide.

**This also refutes a reading written earlier in this very entry.** "The
pricing leg tracks the window" was hedged as a correlate and it does not
survive: eleven minutes of 8-10s passes followed with the window still open.
Both are kept in
`docs/measurements/2026-08-19-window-store-leg-result.md`, in order, because
which claim survived contact is the useful part.

### STILL OPEN

1. **Find out why `link_discovered_events` swings 10x on identical input.** The
   walk, the store leg, the devig loop and the Skeptic are all eliminated by
   measurement. Time inside the call before changing it — this incident has had
   five attributions and four were wrong.
2. **The window gate reads a stale flag** (above). Fixing the cadence half is
   worth more than the prune half.
3. **`QUOTE_PASS_DURATION_BUDGET_S = 8.0`** still validates the configured
   interval and never the observed duration — it logged the overrun all session
   and stopped nothing. Unchanged from the previous entry, and now demonstrated
   twice.
4. **ADR 0054's latency half is UNRESOLVED**, not refuted. Its disk half is
   confirmed. `VACUUM` is not wanted.
5. Everything from the previous entries: Chrome's live-host permission, the
   digest leading with `x / 300`.

---

## 2026-08-19 ~12:15Z — ADR 0053 HALF-HELD; THE COST MOVED TO THE STORE LEG, AND I GUESSED WRONG ABOUT IT FIRST

**The 15:21Z test had not happened when this was written.** The brief asked
whether the fix held at the first open betting window. At 04:12Z that window
was still eleven hours out, and the all-success heartbeat run since 02:10Z was
the machine restart plus a closed window. It is not evidence. `baseball_mlb
15:21Z-16:21Z` is still the test.

Live also only received ADR 0053 at **04:07Z** (release v82), five minutes
before the first look — "deployed and unproven" was fresher than the handoff
thought.

### The narrowing works, and it was never the whole pass

Timed on the live box itself, not from a laptop:

| leg | value |
|---|---|
| `priceable_series` | exactly **19** series, as designed |
| scoped HTTP walk | **2.55s** (was ~15s for the full catalogue) |

That leg is fixed. But the first instrumented passes showed where the clock
actually goes:

```
full pass  took_s 44.6   walk 8454ms  parse 96ms  store  5997ms  price 2793ms
full pass  took_s 54.9   walk 7904ms  parse 93ms  store 14030ms  price 2143ms
```

**The store leg is 6.0s and then 14.0s.** The handoff ruled the writes out at
**0.17s** — correct at 279k rows, and now applied to a table holding 6.9M rows
behind a 476 MiB index on a 1 GiB machine. A write cost measured against a
growing table has an expiry date.

### I produced the third wrong attribution on this incident, and it is recorded

Before instrumenting I timed the walk (2.55s), the parse (0.11s) and the store
(**0.02s**), subtracted them from an observed 23.6s pass, and concluded pricing
was ~21s. Pricing is **2.8s**. Both inputs were wrong the same way:

- the 23.6s was **one sample, 16 minutes after a boot** — the next was 9.7s;
- the 0.02s store was measured against an **empty database in tmpfs**, not the
  live volume. The real figure is 300x larger.

Reading `n` before the effect size — rule one in `CLAUDE.md` — catches both.
See `docs/measurements/2026-08-19-quote-pass-leg-attribution.md`. The fix for
the whole class is shipped: a pass now reports `leg_walk_ms / leg_parse_ms /
leg_store_ms / leg_price_ms`, always, including zero.

### Disk was worse than the handoff said, and there was a latent bug under it

Measured 2026-08-19: **1.41 GiB** database (handoff said 879 MiB), 405 MB free,
growing **214 MiB/day and accelerating** — 264k quote rows/day a week earlier
against 1.37M the day before. **1.9 days to full.** `unmatched_events` was
404 MiB of that and appears nowhere in the handoff: 506,655 rows, **0 ever
resolved**.

**Nothing in this project had ever deleted a row.** No prune, no retention,
anywhere.

**The volume was already 3 GB while the filesystem reported 2.0 G.** A previous
extend grew the volume and never grew the filesystem, so the 2026-08-16 fill
happened against 2 GB on a volume provisioned for 3. Extended to 5 GB with
Joe's approval; `df` now reports **4.9 G, 3.2 G free, 32%**. **Verify any
future extend with `df -h /data` on the machine** — `flyctl volumes list` was
the optimistic one and the two disagreed for at least three days.

A volume snapshot (`vs_Noek6wqO0eqyIoLQgjKjZ`, 1.6 GiB) was taken before the
first prune ran, so the deletion is reversible.

### ADR 0054 — the recording tables get a retention window

`kalshi_quotes`: 3 days, **except** tickers that ever produced a
recommendation (4.8% of the table, kept regardless of age). Every reader was
enumerated first; the only one reaching past **one hour** reaches through
`recommendations.ticker`, and `recommendations` is the only downstream table
carrying a ticker at all. 45.5% of 6,946,356 rows eligible immediately.

`unmatched_events`: 7 days, unconditional on `resolved`, because sparing
resolved rows would spare zero of 506,655.

Batched at 20k rows so the delete cannot hold the write lock the quote inserts
need, and on the **full pass only** for the same reason. Both counts on the
pass line, always.

Four guards, each verified by breaking it. Suite **3,482 passed / 10 xfailed**,
ruff and tsc clean. Live and demo both on `a1807f5`.

### THE FIRST PRUNE STALLED THE RECORDER, AND THAT IS FIXED TOO

Shipping ADR 0054 broke live for ~25 minutes and it is worth knowing why,
because the reasoning that produced the bug reads as correct. Batching
bounds how long **one `DELETE`** holds the write lock. It says nothing about
how long the **pass** is blocked -- the prune runs inside the pass, so
deleting until nothing matched blocked the recorder for the whole backlog
however small the batches were. Caught by watching `recorder.age_ms` climb
one second per second across three reads 25s apart: 1.25M rows gone at
~60k/minute, 1.8M still pending, zero quotes recorded throughout.

A prune now takes a **5s budget** and leaves the rest for the next pass.
Confirmed on live: `retention: pruned 20000 kalshi_quotes and 20000
unmatched_events rows`, one bounded batch each, recorder healthy.

**The throughput arithmetic is tight and nothing in the code enforces it.**
A batch takes ~20s, so the budget buys exactly one batch per pass:
96 passes/day x 20,000 = **1.92M/day pruned** against **1.30M/day grown**,
net 620k/day, backlog clear in ~2.8 days. **Lowering `DELETE_BATCH` to
shorten the stall inverts this** -- 5,000 gives 480k/day against 1.3M of
growth and the table grows forever while `quotes_pruned` reports a healthy
number every pass. `quotes_pruned` sitting at exactly `DELETE_BATCH` means
the backlog is still draining; below it means steady state.

### AND THE BUDGET WAS 8x OPTIMISTIC, SO THE PRUNE NOW YIELDS TO A WINDOW

The 5s budget is really **~40s**. It is checked *between* batches, one batch
measures ~20s against the live table, and there are two tables. Full passes
went **50s -> 87.3s** once the prune was in them -- legs summing to 19.7s of
an 87.3s pass, the rest being the prune.

Between windows that is free. While one is open it is exactly the
confirmation gap the fast cadence exists to close. **Retention has no
deadline; a bettable minute does.** So the full pass now skips the prune
when `window_open`, read off the same `tempo` the cadence is read from.

The budget stays -- it bounds a stall that is happening anyway, the gate
decides whether it happens now.

**The drain arithmetic was redone, and it forced a second change.** Measured
with the scheduler's own `slots_for_sport` against live fixtures:
**4.33 open hours/day**, so 17 of 96 full passes skip the prune and 79 run
it. At one batch that is 1.57M rows/day against ~1.30M of growth -- a
**17% margin whose break-even is 7.75 open hours/day**. NFL and NBA are both
out of season and both back within weeks, and they are exactly the two
sports `backend/kalshi/combos.py` records as missing from our captures.

One 20,000-row batch costs **~20s** (index maintenance, not the scan), so a
budget under 20s buys exactly one batch -- which is why a "5s budget" and an
observed ~40s prune were never a contradiction. **Budget raised to 30s**,
two batches, break-even out to ~15.9 open hours/day.
`docs/measurements/2026-08-19-retention-drain-margin.md`.

### HOW TO READ THE 15:21Z TEST -- WRITTEN BEFORE IT, DELIBERATELY

**There is no clean pre-window baseline and one cannot be made.** With the
window closed the interval is 900s, so `pass_kind` finds a full pass due
every time -- **every closed-window pass is a full pass**, and quote passes
appear only during a window or occasionally via scheduler jitter. Six hours
of watching produced zero instrumented quote passes for this reason.

So the comparison is against the three quote passes seen this morning at
the **old table size (~6.9M rows)**, which have `took_s` and no leg
breakdown:

```
BEFORE (6.9M rows, uninstrumented)   took_s  23.6 / 9.7 / 18.2
AFTER  (~4.5M rows, instrumented)    took_s  ?    + leg_store_ms
```

**n = 3 on the before side, and one of the three was 16 minutes after a
boot.** That is a weak baseline and saying so now is the point -- deciding
after the fact which of the three to compare against is exactly how a
result gets chosen rather than measured. Use all three, report the spread,
and if the after-side lands inside 9.7-23.6 the honest answer is
**unresolved**, not "no improvement".

The full pass during the window is a **separate** observation: it skips the
prune, so it should drop from ~90-122s back to ~50s. If it does not, the
window gate is not working and that is a bug, not a measurement.

### STILL OPEN

1. **The 15:21Z window is still the test.** Watch `leg_store_ms` on a *quote*
   pass — every leg sample so far is a full pass. Projected ~8-12s against a
   15s cadence: a projection with no margin, not a result.
2. **ADR 0054's latency half is a prediction.** If `leg_store_ms` does not fall
   once the table is trimmed, index size was not the cause and that half must
   be withdrawn; the disk half stands on its own measurement.
3. **The deeper lever is write-side, and was deliberately not taken.** ~5,300
   quote rows are written per pass and 4.8% of tickers are ever read.
   Retention keeps 3 days of everything, which preserves the option; narrowing
   the *write* would not. A separate ADR if retention proves insufficient.
4. **`VACUUM` has not been run.** The prune frees pages for reuse but does not
   return them to the filesystem, so the file will not shrink. Affordable now
   at 3.2 G free; deliberately not part of ADR 0054.
5. Everything from the previous entries: Chrome's live-host permission, the
   digest leading with `x / 300`.

---

## 2026-08-19 ~02:30Z — LIVE HAS BEEN FLAPPING ALL DAY, I SAID IT WAS HEALTHY, AND THE CAUSE IS THE QUOTE PASS

**Read `docs/measurements/2026-08-19-quote-pass-cost-attribution.md` before
touching `run_quote_pass` or `run_kalshi_pass`.** The fix is designed and
**not built**.

### What Joe found that I had not

He pasted the Discord channel. Alongside the heartbeat test he asked for, it
held **eleven alarms he had not**: nine `The cockpit is not answering` from the
GitHub heartbeat and two `Cockpit API unreachable` from the loop's own probe,
across the whole day.

I had reported live healthy all session, on `curl` probes that landed in the
gaps. A 5-second poller settled it:

```
302 probes   229 ok   71 timeouts
71 consecutive 30s timeouts  01:51:18Z -> 02:09:10Z   (18 minutes, hard down)
machine restarted            ~02:09:20Z
229 consecutive ok since     128-1835 ms
```

`flyctl checks list` read `critical` while my `curl` returned 200 in 0.14s,
minutes apart. Both true. **The platform check had been watching all day and I
had not.** Lesson written.

### The cause, and two wrong theories killed by measurement

The quote pass is configured every **15s** and was taking **27 → 36 → 36 → 52
→ 77s**, saturating a `shared-cpu-1x`. uvicorn then misses Fly's 5s check;
Next logs `Failed to proxy 127.0.0.1:8000/api/health — socket hang up`.

I proposed two fixes before checking. Both wrong:

| theory | measured | verdict |
|---|---|---|
| the 7,148 inserts per pass | **0.17s** at 279k rows, ~14,000 statements | refuted |
| parsing ~11,191 events | **0.46s** scaled from the fixture | refuted |
| **the HTTP walk** | ~56 paginated pages, every 15s | **the whole cost** |

`run_kalshi_pass` paginates `/events` at 200/page to find 541 priceable events,
so `run_pricing_pass` can link and price **~70**. A **160:1** waste ratio,
every 15 seconds.

### It is intermittent because it has a schedule

`Scheduler.interval()` uses the fast interval **only while a window is open**.
The box melts during betting windows and recovers between them. That is the
alarm pattern exactly. After the 02:00Z WNBA kickoff closed the window the
recorder age climbed steadily past 750s — **the calm is the loop idling at
900s, not the problem being fixed.**

### THE OBVIOUS FIX IS WORSE — do not re-propose it

Fetching the ~70 linked events individually via `markets_for_event` looks
cheaper. It is **more requests than pages** (70 vs ~56) against
`_RateLimiter`, a shared minimum-interval lock at
`DEFAULT_RATE_LIMIT_PER_SECOND = 8.0` that serialises them — `asyncio.gather`
buys nothing. Caught by reading the limiter before writing the code.

**The direction that survives:** walk `/events?series_ticker=…` for only the
series carrying priceable leagues — a handful of requests instead of 56 —
leaving the full catalogue walk on the 900s pass. Cost: a newly-listed event is
linked up to 900s later instead of 15s, which is inside the odds window anyway.

### The second, slower problem — separate decision, do not conflate

`routes.py:2936` records `kalshi_quotes` as ~two thirds of an **879 MiB** file
on a **2 GB** volume, which filled once already (2026-08-16). Every reader joins
that table **by ticker to a market that produced a recommendation**
(`clv_signal.py:143`, `slate.py:232`, `runner.py:592`), so quotes for the
~7,000 never-priced markets are read by nothing.

Narrowing what is stored is the **disk** fix and a change to the record's
population. It is **not** the latency fix — the writes measured 0.17s. Keep the
two apart or the ADR will justify one with the other's evidence.

### What was actually done

- Machine restarted, restoring service. **A bandage.** It will melt again at
  the next open window — next slot is `baseball_mlb 15:21Z`.
- `RUNNER_FAST_INTERVAL_S` was proposed and **is not a lever**:
  `scripts/run_loop.py:301` refuses to start when
  `fast_interval * 1.15 + 8 > MAX_KALSHI_QUOTE_AGE_S`, i.e. above **~19s**.
  Setting 60 would have stopped the recorder, not slowed it. The guard's
  `QUOTE_PASS_DURATION_BUDGET_S = 8.0` is an assumption that is off by ~10x
  against observed pass durations — **it validates the parameter and never the
  reality**, which is its own defect.

### THE FIX IS BUILT — ADR 0053

`run_kalshi_pass` now takes `series_tickers`; the **quote pass** supplies it and
the **full pass** does not. Measured against the real API in the same session:

| walk | time | events | markets |
|---|---:|---:|---:|
| full catalogue | **15.21s** | 11,160 | 96,326 |
| 19 scoped walks | **3.13s** | 573 | 6,917 |

**4.9x, and the saving is bytes not requests.** Coverage checked in the same
run: every priceable event the full walk found, the scoped walks found too.

The series list is `priceable_series(conn, now)` — `DISTINCT series_ticker FROM
kalshi_events` inside two full-pass intervals. **From `kalshi_events`, not
`event_links`**: a link needs a *matched* fixture, so that set collapses to the
few game-level series linked right now and silently stops quoting every prop,
spread and total. Empty set ⇒ walk everything (a fresh volume must go and look,
not report a quiet slate).

Suite **3,468 passed / 10 xfailed**, ruff clean. Six guards, each broken and
watched go red — **two were green when first written**, both recorded in the
ADR. The subtle one: a test asserting on *discovered* events cannot tell a
narrowed fetch from a wide one, because discovery drops out-of-scope series
either way. Assert on what the client handed over.

### STILL OPEN

1. **Deploy it.** Not deployed as of this entry — live still runs the wide
   walk and will melt at the next open window (`baseball_mlb 15:21Z`). The live
   dispatch needs Joe.
2. **Decide separately whether `kalshi_quotes` narrows.** Disk, not latency,
   and ADR 0053 does **not** fix it — the quote store iterates *priceable*
   events (~510), not the catalogue, so it wrote ~7,148 rows a pass before and
   writes about the same now. The writes measured 0.17s; do not justify a
   population change with the latency evidence.
3. **`QUOTE_PASS_DURATION_BUDGET_S = 8.0` is an assumption off by ~10x.** It
   validates the *configured interval* and never the *observed* duration, so
   the loop ran 77s passes on a 15s cadence while logging a warning nobody
   read. A guard that cannot see the thing it guards.
4. Everything from the previous entries: Chrome's live-host permission, the
   digest leading with `x / 300`.

---

## 2026-08-19 ~late — THE STRIP IS ON THE PHONE, BY JOE'S CALL

He read the handoff's open question and answered it the same day: **put the
strip on the phone too.** **ADR 0052** amends ADR 0047.

**The reason is not a preference.** Joe reads `/slate` on a phone -- it is the
documented habit and it is why the 2026-08-18 deep-link repair mattered. An
explanation of where a number came from that exists only on a monitor explains
nothing to the person who owns the account.

**ADR 0047 is amended, not overturned.** Its rule was about *density* -- not
putting rows of columns on a hand-held screen, which is what the Anchor and
Width cells are and why those stay `xl:`-only. The strip is not a column.

### The cost, measured rather than waved at

Seeded `/slate` at 390px: **5,808px to 8,912px of scroll, +53%** across eleven
rows. `check_mobile` clean at all six widths, so this is length and not
overflow.

**Nothing was trimmed to pay for it**, and the two candidates were considered:
the `worst method each` label and the anchoring caveat, which wrap to three
lines and are near-identical on ten of eleven rows. Both kept -- they are the
labels that stop the picture making a claim about the *market* instead of about
the *statistic* (ADR 0051). Trading them for scroll would put the honesty on
the big screen and the density on the small one, which is backwards. If it
proves too long in use, **the next move is a per-row disclosure, not a
breakpoint and not a shorter caveat.**

### The guard was inverted, not deleted

`test_the_strip_is_desktop_only` asserted `hidden` was present. It is now
`test_the_strip_is_on_the_phone_too` and asserts `hidden` is absent, with the
ADR cited in the failure message. Deleting it would have left the visibility
unrecorded, and the next session tidying phone density re-adds `hidden` as an
obvious improvement with nothing to argue against. Verified by re-hiding the
strip and watching it go red.

### Verification

Full suite 3,462 passed / 10 xfailed, ruff and tsc clean, build clean,
`check_mobile` clean at 390/768/1024/1440/1920/2560 against a local build off
the seeded demo, 390px screenshot read.

**Both instances are deployed and current.** Demo went out on `fc51668` and
verified two ways -- `build.git_sha`, and the served `/slate` HTML carrying
`w-full xl:col-span-full` on the strip wrapper with no `hidden` anywhere, so the
phone visibility is confirmed on the deployed page rather than only in source.
Joe then dispatched live, which is on `c79a733` = HEAD: `status: ok`,
`/api/health` in 0.14s warm, `recorder.age_ms` ~30s, `live_quotes_available:
true`, `undelivered_last_24h: 0`, `notifications.total_ever` 108 (up one from
107 earlier in the session -- the channel is delivering).

**The live dispatch was refused from here for the third session running**, so
plan for it: hand Joe the one-liner rather than spending a turn rediscovering
the block. The classifier also refused a combined demo+live command *as a unit*
while the demo-only call went through -- issue them separately.

### Chrome: demo is permitted, live is not, and `navigate` lies about it

Joe was at his laptop and offered Chrome -- the documented route to an authed
live screen (`i-can-see-authed-screens-through-his-chrome`). After he restarted
the extension:

| host | result |
|---|---|
| `example.com` | renders |
| `kalshi-cockpit-demo.fly.dev` | renders, **including at 390px** |
| `kalshi-cockpit.fly.dev` (live) | **silently does not navigate** |

**`navigate` returns success on the live host and the tab does not move.** It
keeps whatever page it was on, so a screenshot taken straight afterwards is of
the *previous* site while every line of the tool output says otherwise. The only
thing that caught it is `Tab Context` in the result footer still naming the old
URL. **Read the tab context, never the screenshot, to decide what you are
looking at** -- this session came one step from writing up a demo screenshot as
live.

Before the restart *both* hosts failed, and this file briefly concluded "so it
is not a per-site permission". That was wrong: it was read off a broken
extension. It is a per-site permission, and **live is the one missing.** Joe
needs to allow `kalshi-cockpit.fly.dev` in the extension's site list before any
future session can see a live screen. **Re-checked once after the live
deploy and it is still blocked**, so the permission had not been added as of
session end -- assume it is still missing and test it with one call before
planning on it.

**What that bought anyway:** the deployed demo's `/slate` was read at 390px on
the real internet, showing the strip rendering under the Houston row --
`WHERE THE NUMBER CAME FROM 53.53% - 54.48%`, `multiplicative 54.19% · used`,
`Kalshi ask 50.70% · off this scale`. Demo and live run one image, so that is
the shipped phone layout confirmed on a deployed instance rather than only
locally. Live itself is still verified the usual way, by `build.git_sha` and
`/api/health`.

---

## 2026-08-19 ~mid — THE STRIP SAYS WHERE THE NUMBER CAME FROM, AND THE DEMO WAS DISAGREEING WITH ITSELF

The last P2 from ADR 0047's approved plan is done. **ADR 0051** is the decision
record. The larger find was underneath it and had been true for the life of the
project.

### THE DEFECT: every seeded row disagreed with its own fair price

A Slate row's `fair_probability` and the `p_conservative` of the `fair_prices`
row its `fair_price_id` points at **must** be the same number — production
devigs once and hands the same `DevigResult` to both (`runner.py:936`). On the
demo they disagreed on **11 of 11 rows**, by up to 0.35 probability points, in
both directions.

`seed_demo.py` ran `consensus_devig` over the seeded books, wrote it to
`fair_prices`, pointed `fair_price_id` at it — and then priced the
recommendation from a **second**, single-pair `devig()` over `scenario.odds`.

**The check already existed, as a comment.** `routes.py` serialises
`p_conservative` with the note *"Should equal `fair_probability` exactly. Sent
so a consumer can check the join landed on the right row rather than assuming
it."* No consumer had ever checked, because until this session no screen needed
both columns at once. **Rendering the two side by side is what found it, in one
glance.** Guarded now by
`tests/test_seed_demo.py::TestTheSeededFairValueIsTheOneItPointsAt`, which also
asserts `p_conservative` really is the minimum of the four — otherwise a seeder
writing one invented number into both columns passes.

**This is demo-only.** Verified by reading the production path, not assumed:
`runner.py:865` computes the consensus, `:873` writes it, `:936` passes the same
object. Live cannot produce the mismatch. `data/demo.db` is gitignored and the
deployed demo seeds on boot, so the fix ships with the code.

### The strip

`frontend/src/components/DispersionStrip.tsx`, geometry in
`frontend/src/lib/dispersion.ts` (React-free, so node executes it).
**xl-only on `/slate`**, same tier as Anchor and Width — ADR 0047 fixes
everything below 1280px as byte-identical, and this is five lines per row. The
component is width-agnostic; moving it to the phone is a class change, and
**that is a decision for Joe** rather than something to do quietly.

Header reads **"where the number came from"**. The word *fair* appears nowhere
in what it renders, and a test fails if it returns.

Every data point was already recorded **and already served** — this is the
"built but never called" pattern one layer further out. No backend change.

### Four calibrations, three of them found by looking at the page

1. **Kalshi's ask no longer sets the scale.** With the ask in the domain, the
   seeded `suspicious_edge` row spanned 34.00% to 60.45% and the four readings
   0.4 points apart became one pixel — nothing visible on the row where the
   question matters most. The ask is not an input to the fair value. Drawn only
   when it lands inside; otherwise labelled `off this scale`, never clamped to
   an edge.
2. **The bar is labelled "worst method each".** It plots each book's *lowest*
   of four; the marks plot *one* method averaged. So marks sit at or above the
   bar **by construction**, on most rows. Unlabelled that reads as "the
   consensus is higher than every book" — a claim about the market. It is a
   fact about the statistic.
3. **Two decimals, not one.** Three distinct marks all labelled `47.4%` looks
   like a broken chart, not a coarse label. A legend must resolve whatever the
   drawing resolves.
4. **It refuses to draw** on fewer than two distinct readings. One point looks
   like four methods agreeing perfectly.

### Two guards were green when written, again, for opposite reasons

Same lesson as yesterday and it fired twice more, so it is now written in
`tasks/lessons.md` as its own pattern:

- `assert "<DispersionStrip" in source` is a **prefix** match, so renaming the
  tag to `<DispersionStripUnused` — the obvious unwiring — left it green. Now a
  word boundary.
- A byte mutation written with `\n` matched nothing in `dispersion.ts`, because
  a `write_text` on Windows had silently converted that file from LF to CRLF
  mid-session. **The mutation script's assert-it-applied step is the only thing
  that separates "the guard is green" from "the mutation never happened."**

### Also worth knowing

- **`asPercent`, the axis, the refusal-to-draw and the caveat wording are all
  in `lib/dispersion.ts`**, deliberately React-free. Change them there; the
  component is layout only.
- `frontend/src/lib/api.ts`'s `DevigMethods` docstring says these fields are
  "**Present only on `/api/ledger`**". That is **stale** — `/api/slate` selects
  and serves them (`routes.py:1049`), which is what made this session possible.
  Not corrected here because the sentence is load-bearing for the
  present-or-absent rule and rewriting it wants its own careful pass.

### Verification

Suite **3,462 passed / 10 xfailed**; ruff, `tsc` and the frontend build clean.
`check_mobile` clean at 390/768/1024/1440/1920/2560 against a local build off a
freshly reseeded `data/demo.db`; 1440 and 390 screenshots read. Eleven guards
disabled and watched go red.

### Deploy state at session end

**Both instances are on `edb40ec` and verified.** Demo's live `/api/slate`
reports **0 of 11** rows disagreeing with their own fair price, so the reseed
shipped with the fix rather than only passing in tests.

Joe ran the live dispatch himself — the classifier blocked it from here for the
third session running, so **plan for that** and hand him the one-liner rather
than burning a turn discovering it again. Live afterwards: `status: ok`,
`build.git_sha` = HEAD, `/api/health` in 0.14s, `recorder.age_ms` ~74s,
`live_quotes_available: true`, `undelivered_last_24h: 0`.

**Live's own screens were not read, and could not be**: `/slate` 307s to login
and `/api/slate` 401s without the app token. Both new screens were verified on
demo, which serves the same image. If a future session needs to see a live
screen, `i-can-see-authed-screens-through-his-chrome` is the route — not a
token in a shell.

### STILL OPEN

- **Joe confirms the heartbeat embed reached his phone** (Discord returned 204
  on 2026-08-18; everything up to Discord is proven).
- **Live deploy needs Joe's dispatch** — the classifier blocks
  `gh workflow run deploy.yml -f instance=live` from here, twice running now:

      gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit

- **The daily digest still leads with `x / 300` toward the gate**, which
  CLAUDE.md says no roadmap may depend on. Partner recommends `beta` and its
  interval. Joe's judgement.
- **Should the dispersion strip reach the phone?** It is xl-only by ADR 0047's
  rule, and Joe uses a phone. Deliberately not decided here.
- `/ledger` real columns is a rewrite, not a widening. Positions/exposure needs
  an A7 embargo ruling. `/api/results` still has zero frontend references.
- ADR 0047's approved plan is now **fully discharged** — both P2 items are done.

---

## 2026-08-19 ~early — THE ALARM WAS WATCHED, AND THE CODES SPEAK ENGLISH ON FOUR SCREENS

Two items off the previous session's menu: the one thing that needed a human
(it did not), and the suppression-code gloss. **ADR 0050** is the decision
record for the second.

### The alarm fired, and it was watched

`gh workflow run heartbeat.yml -f force_alarm=true` — run
[32189114686], conclusion **success**, `discord replied 204`. The embed left
GitHub for the webhook and Discord accepted it. **That is delivery to Discord,
not delivery to the phone**; the last step is Joe glancing at the channel for
"⚠ Heartbeat test — this is not a real alarm". Nothing else is pending on it.

The dispatch was **not** blocked by the permission classifier, unlike the live
`deploy.yml` dispatch that the 2026-08-18 evening session had to hand to Joe.
Worth knowing: the block is per-workflow-and-input, not a blanket refusal of
`gh workflow run`.

### The gloss — and the three defects it uncovered

`frontend/src/lib/suppressionGloss.ts` maps every suppression code to one short
sentence. It renders **beneath** the code, muted, never instead of it —
`SlateRow`'s standing refusal of a translation ("would give the same rule two
names") is correct and survives intact. Label and caption.

**1. There are four render sites, not two.** The first pass did `SlateRow` and
`OpportunityCard` — both *Board* components — and looked complete. `/slate`,
which is where Joe's phone habit goes, renders the field from its own markup in
`app/slate/page.tsx`; `/ledger` from a third. A per-component test written from
that same wrong list would have agreed it was done, so the guard scans all of
`frontend/src` and requires an `EXEMPT` entry with a reason. **It found
`/ledger` on its first run.**

**2. Two vocabularies share the column.** `backend/engine.py:255` writes
`sizing:{binding_constraint}` when the sizer refused, so a row can read
`sizing:bankroll_unobserved` — never a `Check` name. Pinning only to
`ALL_CHECK_NAMES` would have shipped that whole class rendering bare.
`SIZING_GLOSS` covers the six *refusing* constraints; the six clamping ones
cannot reach this column and a sentence for one fails the test in the other
direction. That direction fired during the build.

**3. Unknown code ⇒ `null`, never a placeholder.** An unrecognised code means
the server runs a rule this frontend predates, which is a deploy-skew fact
worth seeing.

### Two guards were green when written, for opposite reasons

Written up in `tasks/lessons.md` because "green" looked identical for both and
they need opposite fixes:

- Counting `rec.suppressed_reason` occurrences did **not** notice the code being
  swapped for the gloss — both components also reference the field as a
  *condition*. The **guard** was decoration; it now looks for a rendering
  position specifically.
- The `/ledger` mutation removed one gloss call and left the other, so the scan
  still saw the name. The **mutation** was too weak; the guard was fine.

Mechanical trap that cost two cycles: **this repo has mixed line endings** —
`suppressionGloss.ts` is LF, `app/slate/page.tsx` and `app/ledger/page.tsx` are
CRLF. A byte mutation written with `\n` matches nothing in a CRLF file and
`str.replace` returns the input without complaining. Assert the mutation applied
before trusting the result.

### How to run the cockpit locally (nothing recorded this, and it is 30 seconds)

Needed for `scripts/check_mobile.py`, which wants a served build:

    DB_PATH=data/demo.db INSTANCE_MODE=demo .venv/Scripts/python.exe -m uvicorn \
        backend.api.routes:create_app --factory --host 127.0.0.1 --port 8012
    cd frontend && npm run build && API_ORIGIN=http://127.0.0.1:8012 npx next start -p 3012
    .venv/Scripts/python.exe -m scripts.check_mobile --width 390 \
        --base http://127.0.0.1:3012 --shots <dir>

`DB_PATH`, not `DATABASE_PATH` — the wrong name falls back to
`data/cockpit.db`, which does not exist, and every route 500s while
`/api/health` still answers 200 (its blocks are wrapped). `pkill -f uvicorn`
does **not** kill it from git-bash on Windows; the old process keeps the port
and the new one dies silently, which reads as the env var not working. Kill by
PID off `netstat -ano`. `data/demo.db` carries a three-code composite
suppression row, which is the case worth looking at.

### Cost, accepted

Every rejected row is 1–3 lines taller. On `/slate` at 390px with eleven rows
that is real scroll. Truncating to the first code was rejected: the codes are
joined in *evaluation* order, not priority order, so "first" is not "main".

### Verification

Suite 3,432 passed / 10 xfailed; ruff clean; `tsc` clean; frontend build clean.
`check_mobile` clean at 390/768/1024/1440/1920/2560 against a local seeded
build; 390px screenshots eyeballed for the Board and the Slate. Ten guards
disabled and watched go red.

### Deploy state at session end

Committed and pushed as `47f2823`. **Demo is deployed and verified** — its
`/api/health` reports `build.git_sha` `47f2823`, and the deployed `/slate`
serves the glossed sentences. **Live is NOT deployed**: the classifier blocked
`gh workflow run deploy.yml -f instance=live` again, exactly as it did on
2026-08-18. Hand Joe the one-liner:

    gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit

Live is healthy on the previous commit (`16e963f`) in the meantime. Nothing in
this change touches the recorder, the gate or the order path — it is frontend
copy plus its guards — so running live behind by one commit costs nothing but
the gloss.

### STILL OPEN, unchanged from the previous entry

- **Joe confirms the heartbeat embed reached his phone.** Everything up to
  Discord's 204 is proven.
- **GitHub cron is not a pager.** Best-effort, routinely delayed, skipped on a
  60-day-idle repo. Bounds time-to-notice at *roughly* 15 minutes.
- **The daily digest still leads with `x / 300` toward the gate**, which
  CLAUDE.md says no roadmap may depend on. The partner recommends `beta` and its
  interval instead. A judgement for Joe, and now the only recurring message the
  channel carries.
- **The dispersion strip** (min book → four devig methods → max book, labelled
  "where the number came from", never "fair") — the other P2 from ADR 0047's
  approved plan, still unscheduled.
- `/ledger` real columns is a rewrite, not a widening. Positions/exposure needs
  an A7 embargo ruling. `/api/results` still has zero frontend references.

---

## 2026-08-17 21:55Z — THE MEASUREMENT IS NOT DUE YET, AND THAT IS THE WHOLE SESSION

**`main` at `d867677`. State re-verified, not inherited: 3,100 passed, 10
xfailed, `ruff check` clean, `tsc --noEmit` clean.** The hunt is still closed
(ADR 0038). Nothing here reopens it and nothing here searches for an edge.

### THE ONE JOB WAS NOT DUE. THE HANDOFF'S TENSE WAS WRONG

The session prompt (`d867677`) said *"The budget day closed at
2026-08-18T10:00:00Z."* At session start it was **2026-08-17T21:49Z**. The
window `[2026-08-17T10:00Z, 2026-08-18T10:00Z)` — confirmed from the tool's own
header, and `_day_bounds` at `scripts/inspect_live_db.py:1198-1210` — **had
twelve hours left to run.**

`tasks/NEXT.md` itself was right; only the prompt derived from it was wrong. The
tell was one `date -u`, and it cost nothing to check. **Check the tense on a
claim that a deadline has passed, the same way you check a claim that something
is broken.**

### WHAT THE PARTIAL DAY LOOKS LIKE — NOT A RATE, DO NOT QUOTE IT AS ONE

Read-only, `credits-day --date 20260817`, no credits spent. All 5 rows:

```
20:56:15.067Z  h2h  us,eu  cost 2  remaining 18894  used 1106  trigger NULL
21:06:40.800Z  h2h  us,eu  cost 2  remaining NULL   used NULL  trigger NULL
21:27:55.988Z  h2h  us,eu  cost 2  remaining 18892  used 1108  trigger NULL
21:38:07.636Z  h2h  us,eu  cost 2  remaining 18890  used 1110  trigger NULL
21:48:14.802Z  h2h  us,eu  cost 2  remaining 18888  used 1112  trigger NULL
```

**The day will be clean, and that was not guaranteed.** There are **zero** rows
in the window before 20:56Z — the last three-market call (2026-08-16T22:59:23Z)
falls in budget day 20260816. So every row in budget day 20260817 is under the
running configuration. **No mixed-config caveat will be owed.**

**Our ledger over-counts, deliberately, and the invoice must use the vendor's
counter.** Our `SUM(cost)` is 10; the provider's `used_reported` moved
1104 → 1112, i.e. **8**. The difference is the 21:06 row — the 401 during the
rotation — which we recorded at `cost = 2` and the vendor charged 0.
`backend/odds/client.py:322-324` says why in writing: *"Record before raising:
some error classes still consume credits, and under-counting spend is worse than
over-counting it."* **This is a decision, not a defect; do not open a lane on
it.** It is checked here because a claim that something is broken buys its author
a task, and this one did not survive opening the file.

### THE CADENCE IS PINNED, SO TOMORROW'S FIGURE HAS SOMETHING TO BE CHECKED AGAINST

`runtime-realist`, read off the live process rather than a default:

- **600 s (10 min) per sport while a slot is due.** Printed from the live
  process: `REF 600000`. It is *not* `fast_interval_s` — the loop tick and the
  odds spend are different clocks. `refresh_interval_ms = max_odds_age_ms * 2 // 3`
  (`backend/odds/timing.py:122-142`), and `900_000 * 2 // 3 = 600_000`.
- **One HTTP call per sport per fire**, `/sports/{sport_key}/odds`, at
  `len(markets) * len(regions)` = 1 × 2 = **2 credits**.
- **The window is derived from kickoff times, not a clock.** 60 minutes per
  kickoff cluster, ending 15 min before that cluster's first pitch
  (`timing.py:395-442`, `DUE_WINDOW_MS`, `timing.py:119`). Tonight: MLB
  20:56Z→00:26Z continuous (3 h 30 m) plus WNBA 00:45–01:45Z. Sports meter
  independently.
- **Scheduled props off, confirmed two ways** — env reads `false`, and the last
  12 rows contain no `/events/` endpoint at all.
- **No drift.** All eight odds settings on the live machine match
  `fly.live.toml` exactly.

**`MAX_ODDS_AGE_S` cannot be changed in `fly.live.toml` alone.**
`backend/core/suppression.py:48` hardcodes `900_000` and feeds the cadence;
`fly.live.toml:321` feeds `StalenessConfig`. `assert_odds_age_limits_agree`
(`backend/config.py:467`, called from `scripts/run_loop.py:329`) **refuses to
boot** if they diverge. Both move together or the instance crash-loops. The
guard is correct; this is a note on how to change the value, not a defect.

**A projection follows and it is arithmetic, not a measurement.** ~21–26 MLB
calls + ~6–7 WNBA → **~54–66 credits for 2026-08-17**. This repo's own rule is
that a formula is not a spend. **It is written down only so tomorrow's measured
figure can be checked against something stated in advance.** If the measured
number lands outside this band, the band is not the thing to trust — find out
why. **The measured figure supersedes this line entirely.**

### STILL OPEN — ONE ITEM, TEN MINUTES, NOT DUE UNTIL 2026-08-18T10:00:00Z

1. **Read the closed budget day.** After **2026-08-18T10:00:00Z**:

   ```
   flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py credits-day --date 20260817"
   ```

   Read-only, `mode=ro`. `--day-start-hour` defaults to the correct 10:00Z
   boundary — **do not re-bucket by calendar date.** Append it to
   `docs/measurements/2026-08-17-odds-credit-run-rate.md` as §6b; §7 already
   states what it does not establish. **Report `used_reported` delta as the
   spend and `SUM(cost)` as our over-count**, per above. Note the ~31-minute
   outage (21:06–21:27Z, the key rotation) suppresses the total slightly — say
   so rather than quoting it clean. **Run it past `measurement-skeptic` before
   it enters the record;** it killed the last draft of this document and was
   right on every count.

2. **Then the tier decision is Joe's, on the invoice.** At the projected band
   the tier is roughly an order of magnitude larger than the demand. Give him
   the measured day, the monthly projection, and what the recorder buys for it,
   sized for a phone. **Do not decide it for him.**

### DEFECTS CARRIED FORWARD, NEITHER FIXED, NEITHER A REASON TO OPEN A SESSION

Both still stand exactly as written in the entry below: the failed odds call
that resets the freshness clock, and the restart mid-window that sleeps 900 s
inside an open window (`backend/scheduler.py:183` — the previous entry says
`:182`; same line, the file moved by one).

---

## 2026-08-17 — JOE'S THREE ITEMS, AND THE LANE THAT WAS BRIEFED WAS THE ONE THAT DID NOT EXIST

**`main` at `679e1b9`, pushed. 3,100 tests pass (+20), 10 xfailed, ruff clean,
`tsc --noEmit` clean — run on `main`, not inherited.** The hunt is still closed
(ADR 0038); nothing here reopens it, and nothing here searches for an edge.

Joe took on all three of his own items. `partner` sequenced them, then reordered
its own list mid-session when a subagent found something bigger than any of
them, then accepted two corrections to claims it had made. Its final answer was
**stop**, again, and it again declined to name a sixth item.

### THE BIGGEST THING WAS NOT ON THE LIST — ADR 0032 IS SOURCED FROM THE WRONG `G`

**There are two 300s in this project and ADR 0032 conflated them.** It turned
scheduled prop buying off, arguing props "cannot move the denominator". That is
true of **the gate's** floor — `gate.clustered_clv` clusters on
`event_links.odds_event_id` (ADR 0029), and a prop ladder inherits its game's
id, so it collapses onto the game.

**The CLV signal test's `G = 300` uses a different, registered key**, and
`backend/analysis/clv_signal.py:109-114` says so in writing, with numbers:
*"The cluster key is `COALESCE(m.event_ticker, r.ticker)` and it is NOT the
gate's key ... the two give 210 and 125 — a 68% difference — so a `G` quoted
without its key is meaningless."* Under it a prop ladder **is** its own cluster,
and the interim look measured the cost: **props supplied 81 of 199 clusters,
40.7% of `G`.**

**THE DECISION STANDS AND TURNING SCHEDULED PROPS BACK ON IS KILLED.** Props
were 260 of ~302 credits a cluster; restoring them buys faster accrual toward a
statistic `CLAUDE.md` forbids any roadmap from depending on. Only the sourcing
was wrong.

**What it costs is a misread that is predictable today.** The retired arm was
the *more negative* one — `prop −0.519` against `moneyline −0.082` — so the
pooled estimate now drifts **toward zero, toward what reads as good news, by
composition rather than evidence.** A future session taking the `G = 300` look
and seeing `beta` improve would be reading the intake, not the world. Written
in all three places that reader passes through: an annotation on the interim
look, a **non-amending** note on the registration (no rule changes), and a
sourcing annotation on ADR 0032.

**Direction only — the magnitude is not computable and the attempt is recorded
so it is not repeated.** Re-weighting the arms reconstructs nothing:
row-weighting gives −0.230, cluster-weighting −0.260, against a published pooled
−0.1412. That is not a defect. The pooled figure is one regression carrying the
`half_spread_tenths` control, not a mixture, so it is not required to lie
between its arms.

### 1. `ODDS_API_KEY` ROTATION — THE BLOCKER WAS NOT REAL. `docs/JOE-odds-key-rotation.md`

The handoff said this needs `flyctl` from a laptop and Joe works from a phone.
`.github/workflows/secrets.yml` genuinely cannot touch this key — its exclusion
is written, reasoned, and **stays untouched** — but `flyctl` is not the only
route. **Fly's secrets are settable from the web dashboard, which is a website.**
No laptop, no ADR, no widening of the workflow.

Sheet states what does **not** verify a rotation: `/api/health` returning 200
proves nothing, because the deployed API process never reads this key
(`routes.py:263` takes `load_without_credentials`; the only live reader is
`config.py:251`, reached only by `run_loop.py` on the live instance). **The
proof is a served `api_credits` row after the restart.**

**Not done and it is Joe's:** generating and installing the key. No session may
handle the value.

### 2. THE TIER — MEASURED, AUDITED, AND THE MEASUREMENT MOSTLY DIED

`docs/measurements/2026-08-17-odds-credit-run-rate.md`. All 111 `api_credits`
rows read off the live box. The first draft published **412 credits/day**;
`measurement-skeptic` killed it and was right on every count.

**The killer: `n = 0` rows exist under the running configuration.** Three
changes landed 2026-08-16, all ancestors of the deployed image, all *after* the
last recorded row — props off the schedule (`83432c1`), `ODDS_MARKETS` three
markets → `h2h` (`d4afa53`, so a sweep goes **6 → 2 credits**), cap 400 → 600
(`4600f87`). Machine environment read back to confirm. The formula predicts an
**8× drop**; that is arithmetic and is **not published as a rate.**

Also: 2026-08-15 spent 390 against a **400 cap that was refusing calls**, so it
reports a ceiling. And the parts do not agree — sweep leg up 5×, prop leg down
28%, the pooled totals matched **by cancellation**, which the draft had cited as
evidence the mean was safe.

**What survives, config-independently: 18,896 ÷ 600 a day means the tier cannot
be exhausted before 2026-09-17**, covering any plausible renewal. **The renewal
date is recorded nowhere in this repo** — it is measurable, not guessable
(`remaining_reported` jumps back to 20,000 on the first call after the cycle
rolls).

**Two flags checked rather than inherited, and both failed.** `credits-day` has
**no** boundary defect — it returns 390 / 416, matching a hand re-bucket
exactly; the calendar-date error was in the draft that bypassed it. And
`fly.live.toml:156`'s **338 is correct**: the sentence says *"one cluster"*, and
338 + 78 = 416 exactly. **No correction is owed on either.**

### 3. THE COST METER — THE LANE AS BRIEFED WAS A NO-OP, AND THE PREMISE WAS MINE

I scoped it from *"every cost figure sits inside `suggested_contracts > 0`, so
rows sized to zero show an edge and no cost."* The guard is real. **The
conclusion is wrong:** `routes.py` builds `surfaced` under the same predicate,
`page.tsx` feeds `LiveBoard` nothing else, and `LiveBoard` is
`OpportunityCard`'s only call site — so the guard is **structurally true on
every card rendered**. Zero-sized rows never become cards; they are `SlateRow`s
already saying *"no edge after fees"* in English.

**Both bettor reviews independently ranked a different thing first, and it is a
real defect.** `LiveBoard` overwrites `suggested_contracts` with
`quote.contracts` and nothing else. `backend/live.py` computes that with the
same `size_position` the order endpoint uses, so it legitimately reaches 0 when
the price moves. The card then lost its cost block, **kept a `reason_text`
reading "Sized at 14."**, and stayed wrapped in `TicketTrigger` — tappable,
opening a ticket for a size the server had already decided to refuse.

Server-side re-validation is intact, so nothing could be bought. **A lying
screen, not a hole in the order path** — and this repo's named failure in the
dangerous direction. Fixed via `frontend/src/lib/liveSizing.ts`, a pure
predicate **executed under `node`** (same shape as `sweepTone.ts`), two
mutations red, both call sites pinned by guards observed red against the
pre-fix components.

**`sharp-bettor` did not defend its own proposal unchanged**, and the reason is
worth keeping: the fee curve is **flat at 1.7–1.8c across every price that
trades**, so a cost column cannot rank anything — which is what made partner's
cut correct. It argues the comparator belongs on the **ticket sheet**, at
commitment, not on a discovery board. **Not built. Verify it is not already
displayed before anyone does.**

### 4. TRACEBACKS WERE NEVER REDACTED

`CredentialRedactingFilter` rewrites `record.msg` and `record.args`. A traceback
is neither — `Formatter.format` renders it *after* every filter has run, and
`odds/client.py` calls `logger.exception` on the one path that has just issued a
request carrying the API key in its query string. Closed **by class** rather
than by enumerating which `httpx` exceptions leak: a
`CredentialRedactingFormatter` on every root handler, plus `exc_text` handling
in the filter. Redaction, not suppression — proved end to end through the real
`configure_logging`.

### 5. `fee_predicted` MEANS THREE THINGS — `tests/test_fee_predicted_is_not_aggregated.py`

Whole-order when sized, per-contract when refused, and the fee for an order
later suppressed. `partner` rejected documenting it: the failure is in the
**analysis** path, and a comment at the write site is not read at the moment the
mistake is made. Guard is green today by design — a tripwire for the day someone
sums it. Exemptions checked: `joint_bound.py` already binds it
`stored_fee_DO_NOT_USE`; `mart_fee_reconciliation` reads the **fills** lake
where the column has one meaning, and that exemption is pinned by its own test.

### 6. THE CREDIT INSPECTOR WAS BLIND TO THE CONFIG IT SPENDS UNDER

`_CREDIT_COLUMNS` did not select `markets` or `regions` — the two fields whose
product **is** the cost. Same shape as last session's `trigger` omission, and it
bit today: reading `cost` to infer the config works and is an *inference*.
Added and deployed **before** the 20:50Z window, so the first observation under
the new configuration is read rather than deduced.

### STILL OPEN, AND THE ORDER MATTERS

1. ~~**Read the first post-cutover credit rows.**~~ **DONE 2026-08-17T20:57Z,
   and it is unambiguous.** First call `20:56:15.067Z`: `markets = h2h`,
   `cost = 2`, and the provider's own counter moved `1104 → 1106` — **a delta
   of exactly 2.** So the 3× reduction is the vendor's billing and not merely
   our estimate, which is the version that would have been worthless. `trigger`
   NULL; the manual tap still has never fired. Props confirmed off in the
   scheduler's own words. Addendum §6a of
   `docs/measurements/2026-08-17-odds-credit-run-rate.md`.
   **No daily rate published** — one window is not a day. The first honest
   figure arrives when the budget day closes at **2026-08-18T10:00:00Z**, and
   reading it is a ten-minute job, not a session.
2. ~~**Joe rotates `ODDS_API_KEY`.**~~ **DONE AND VERIFIED 2026-08-17T21:27:55Z.**
   Proof is the row's **non-NULL provider headers** — `remaining 18892`,
   `used 1106 → 1108` — which a rejected call cannot produce. Cost still **2**,
   so the config saving survived the rotation. The old key no longer exists at
   the provider, so **the leaked value is dead** and the incident is closed.
   Recorder downtime ~31 minutes, one missed refresh.

   **It took three attempts and none of the failures were the paste. All three
   are now in the runbook.**

   - **The Fly dashboard *stages* a secret; saving does not apply it.** The
     loop kept authenticating on the **old** key and kept succeeding, so every
     "is it working" check passed while nothing had rotated. `flyctl secrets
     list` said `Staged`. Joe's dashboard button is literally **"Deploy
     secrets"**.
   - **A rejected call still writes an `api_credits` row**, because
     `client.py` records before raising — some error classes do consume
     credits. **A row is not proof.** The 401 row carried `cost = 2` and
     `NULL` provider headers, and it was only the NULLs that gave it away.
     *"Unreadable resolves to `None`, never `0`"* is what made the failure
     visible; a `0` there would have read as a real reading.
   - **The first 401 was the provider not having activated the key yet.** It
     began answering ~20 minutes later with no further change on our side —
     the Fly digest was byte-identical across every attempt.

   **The digest is a fingerprint and it is the cheapest diagnostic available.**
   `flyctl secrets list` prints one per secret without revealing any value, so
   an unchanged digest after a re-paste proves Fly holds exactly what was
   pasted and moves the search off the local side. That is how this was narrowed
   without anyone handling the key.

**TWO DEFECTS FOUND WHILE VERIFYING, NEITHER FIXED, BOTH REAL**

- **A failed odds call resets the freshness clock.** Immediately after the 401
  the scheduler reported *"odds are 0.4min old"* and deferred its retry a full
  **ten minutes** — so a rejected key makes the system believe it holds fresh
  odds. The dangerous direction: an outage presents as freshness. Not fixed
  here because it wants its own guard, observed red first.
- **A restart mid-window costs up to 15 minutes of blindness.**
  `backend/scheduler.py:182` returns
  `fast_interval_s if self.window_open else self.slow_interval_s`, and a fresh
  process starts with `window_open` false — so after the restart the loop slept
  **900s** inside an open window. It looks exactly like a hung process, and
  diagnosing it cost real time here. Check `sweep-log`'s newest row against the
  restart time before concluding a stall.
3. **The tier renewal is Joe's, on the invoice.** He has the ceiling claim that
   does not depend on a run rate (cannot be exhausted before 2026-09-17), and
   the run rate itself is now measurable rather than projected.

### DROPPED — still a drop list, not a backlog

Everything on the previous list stands: the Board/footer gap, exercising the
manual-refresh path, the ~99 clusters to `G = 300`, anything reopening the hunt,
the sweep banner. **Added: turning scheduled props back on** — ADR 0032 stands
and its annotation says why the sourcing error does not reverse it.

### THE ONE HONEST CANDIDATE IF A NEXT SESSION NEEDS A SUBJECT

`partner`, unprompted, and explicitly **not** work for tonight and **not** a
hunting line: the only stated purpose in `CLAUDE.md` with no execution behind
it is that this become a public portfolio repo. It already *is* public. Whether
the record reads as *"we found out, and here is how"* rather than as an
abandoned trading bot is a real question with a real answer, and it is the kind
of thing nothing fails for skipping. It needs a different reviewer than any on
this session's list, and **whether it is worth a session at all is Joe's call.**

---

## 2026-08-17 — THE MORNING WARNING WAS ARITHMETIC, AND IT IS GONE FROM THE LIVE SCREEN

**`main` at `b0bd2ec`, pushed. 3,080 tests pass (+26), 10 xfailed, ruff clean,
`tsc --noEmit` clean — run on merged `main`, not inherited. Both instances
deployed and both report `git_sha b0bd2ec238dd310f0f2dcf00f9f9925d9e489aa0` from
`/api/health`, which equals HEAD.** The hunt is still closed (ADR 0038); nothing
here reopens it.

One lane, directed by `partner`, which explicitly did **not** walk back last
session's "stop" — its distinction was that this item arrived *measured* rather
than *found*, and refusing measured evidence to protect yesterday's stance is the
flattering-direction failure wearing discipline as a costume.

### The defect, and it was 6 of 6 days

The Board's amber strip — *"the loop is alive and declining: nothing has swept in
18.1h"* — compared `last_sweep_ms` against `budget_day_start_ms`. **Those are
different clocks.** The boundary is credits-accounting (10:00Z, so a West Coast
extra-innings game settles in the right day); a sweep window is kickoff-derived,
opening 75 minutes before a cluster's first pitch. Between them there is no
window in which to spend, so "nothing has swept" is arithmetic there, not an
observation.

Measured on live rows **before** anything was built, gap from the boundary to the
first row satisfying the full served-sweep predicate:

```
2026-08-12  17:00:11Z  7.00h      2026-08-15  16:27:03Z  6.45h
2026-08-13  16:47:55Z  6.80h      2026-08-16  17:06:36Z  7.11h
2026-08-14  17:39:58Z  7.67h      2026-08-17  no sweep at all as of 17:45Z
```

**Two quantities live in this record and must not be conflated.** That table is
the gap to the first *served row*. The predicate keys on gap to *window open*,
which is larger: on 2026-08-17 the first window opened at 20:50Z against a 10:00Z
boundary — **10.83 hours of amber**. My own interim brief "corrected" the
handoff's ~11h guess down to 6.5–7.7h and the correction was wrong, because it
measured the other quantity. The handoff was right.

**The machine already knew.** `odds_sweep_log` was writing *"no sweep: next slot
is baseball_mlb at 20:50Z-21:50Z ... sweeping 75-15 min before first kickoff"*
every ~15 minutes throughout. The scheduler's log was calm and correct while the
screen a human reads was amber.

### VERIFIED on live, seen not asserted

Live Board in Joe's own logged-in Chrome, 2026-08-17 ~18:10Z, in the exact state
that used to be amber:

```
looked 2m ago  ——  gap 19.1h  ——  swept 19.2h ago
No sweep window has opened yet today — the first is at 1:50 PM. The loop
looked 2m ago. Windows open 75 minutes before the first pitch of a cluster,
not when the budget day does, so nothing has swept yet and nothing is owed yet.
SKIPPED · no sweep: next slot is baseball_mlb at 20:50Z-21:50Z ...
```

Rendered **muted grey, not amber** — confirmed on the pixels, not only the copy.
**Every fact is still on screen**; the gap chip still says 19.1h. It stopped
shouting without hiding anything. `first_window_open_ms` on the public
`/api/window` is `2026-08-17T18:52:57Z` against a `budget_day_start_ms` of
10:00:00Z, i.e. the two numbers are demonstrably not the same clock.

### `refused` is in the predicate and it is not optional

The obvious fix — *no window open yet, therefore calm* — is **worse than the
bug**. `slots_for_sport` is unfiltered by budget (its own docstring says so), so
a day whose credits died at 14:00Z still computes a 20:50Z window; the naive
predicate renders that calm over a recorder that is dead until tomorrow. That
trades a false positive for a **false negative on the failure the strip exists to
catch**. A liveness guard may be noisy; it may not be silent. `refused` is live,
not theoretical — two such rows exist.

### The predicate is now executed by a test, not read by one

Every other frontend guard here asserts on **source text**, which passes
unchanged on a predicate that has been exactly inverted — and a wrong verdict is
precisely what this defect was. The verdict moved to
`frontend/src/lib/sweepTone.ts` as a pure function; `tests/test_sweep_tone_predicate.py`
runs it under `node` against real recorded states, including three mutations
observed red. Wiring guards pin that `WindowBanner.tsx` actually calls it, so the
extraction cannot orphan itself.

### One claim of mine was wrong, and the mutation test is what said so

I asserted in `sweepTone.ts` that the `refused` clause **must precede** the
window clause and wrote a mutation to prove the ordering load-bearing. **It
refused to go red.** Both branches return `"warn"`; it is a disjunction, so
swapping them changes nothing. The real requirement is narrower — `refused` must
never be *gated behind* the window test, i.e. no early `return "calm"`. Comment
corrected, mutation rewritten to the shape that actually breaks. Recorded in ADR
0042 because a plausible ordering claim backed by a never-red test is exactly
what a future session preserves while refactoring around it.

### Found in passing: the manual exclusion has never fired

All-time, every `/odds` row with `cost > 0` has a NULL `trigger` — one group,
**n = 111**, 2026-08-07 to 2026-08-16. **Zero manual taps have ever been
recorded.** The exclusion stays (a hand tap proves the spend path, not the
scheduler) but it is test-covered only — this repo's "built but never called"
shape, now written down so it is not rediscovered as a finding. The copy change
explaining it to a reader was authorised and then **dropped**: a sentence about a
button nobody has pressed.

**Quote the predicate verbatim.** It is
`COALESCE(trigger, '') != 'manual'`, not `trigger != 'manual'`. My brief used the
paraphrase; under it, all 111 NULL rows fail and the banner would read "swept
never" for its whole life. The measurements used the real predicate and stand.

### The instrument was blind to its own predicate

`scripts/inspect_live_db.py`'s `_CREDIT_COLUMNS` did not select `trigger` — the
one clause deciding a served sweep. Fixed **first**, and the six-day table above
was re-run with it visible before the design was frozen. Same shape as the
`clv-coverage` failure that cost six days. The blind spot pointed the safe way (a
miscounted tap lengthens the gap), which is why this was a repair and not a
retraction — **say which way a blind spot points, always.**

### Not done, deliberately

`partner` capped this at one lane and closed the banner line permanently on
merge. No restyling, no new tones, no settings knob, no `trigger` backfill, no
second screen.

### THE DIRECTIVE IS STOP, AND IT WAS CHECKED RATHER THAN REMEMBERED

Asked at the end of this session what was next, `partner` answered **stop** —
not "stop for now", not "stop pending". It verified its own list before saying
so, on the grounds that saying *stop* from memory is the same failure as saying
*go* from memory: its one undischarged pre-commitment was the `scout.py` /
Historian quarantine, and that was already closed by ADR 0040 (reinforced by ADR
0022, and stated in `backend/playbook.py`'s module docstring where a session
actually hits it). Five items named across two sessions, five discharged. **It
declined to name a sixth.**

**Explicitly dropped — this is a drop list, not a wish list.** Do not pick these
up as "small wins":

- **The blank gap between the last Board card and the footer.** Cosmetic,
  undiagnosed, on a hard-closed line. *Undiagnosed is not a reason to diagnose
  it.*
- **Exercising the manual-refresh path** to retire its zero-live-firings status.
  It spends credits, on a tier whose renewal is Joe's undecided call. The guard
  is test-covered; that is enough.
- **The ~99 clusters to `G = 300`.** Waiting is not work. **Do not schedule a
  session for it.** When it crosses, the look is a twenty-minute read against a
  pre-registered rule.
- **Anything reopening the hunt.** ADR 0038 requires naming which quadrant row is
  overturned and with what measurement. Nothing here does.

Every remaining open item is Joe's and every one touches money or credentials —
the cost-of-execution meter, the Odds tier renewal, the `ODDS_API_KEY` rotation.
Those are his by design. **A future session must not convert one into a lane to
give itself something to do.**

If more is wanted from this project the honest answer is that it needs a **new
signal**, not more work on this one. `backend/analysis/signal_test.py` is
signal-agnostic and would validate one on the same clock that refuted the last.
That is Joe's decision to fund, not a task to assign.

---

## 2026-08-17 — THE INSTRUMENTS NOW DISAGREE WITH THE MACHINE OUT LOUD

**`main` at `bdcd1fb`, pushed. 3,054 tests pass, 10 xfailed, ruff clean, `tsc
--noEmit` clean — run on merged `main`, not inherited. Both instances deployed
and both now report `git_sha bdcd1fbc2811b54784083fcdd29ea000d8cc77bf` from
`/api/health`.** The hunt is still closed (ADR 0038); nothing here reopens it.

A finishing session, run as one. No feature was added to the betting product.
Three of the project's own *instruments* were broken in the same direction —
**the record said one thing and the machine did another** — and all three are
now guarded by a test that was observed red first.

### Deployed first — `999857f` (the footer)

It was committed and pushed but on neither instance. **Proved by probe before
deploying:** the served HTML had `<nav>` (1 hit, the control, from the same
`layout.tsx`) and `<footer>` (0 hits). After deploy: footer 1, `/rejections`
and `/builder` 5 hits each, on both. This is the diffing technique that item 1
below exists to retire.

### 1. `/api/health` can name the commit it is running — ADR 0039's gap closed

Establishing that `999857f` was absent from both images cost a subagent **32
tool calls** of behavioural HTML diffing. `/api/health` now carries a `build`
object: `git_sha`, `image_ref`, `machine_version`, `machine_id`, `region`.

- **The Fly environment was enumerated on a real machine, not assumed** —
  `fly ssh console -a kalshi-cockpit-demo -C "env | grep ^FLY_"`.
  `FLY_RELEASE_VERSION` **does not exist**, and *no* Fly variable carries a
  commit: `FLY_IMAGE_REF` ends in a deployment ULID and `fly releases --json`
  reports `"Metadata": null` on every release.
- **The build-arg cache cost was never paid.** `fly deploy -e GIT_SHA=…` sets a
  *runtime* machine variable and touches zero Docker layers. It also fails in
  the safe direction: `-e` is not inherited, so a forgotten flag yields `null`,
  never the *previous* deploy's commit reported as this one's.
- Unreadable → `None`, never `"unknown"` — two machines both reporting
  `"unknown"` compare equal, which is the exact wrong answer.

**A defect survived the merge and it is this repo's own named one.** The field
was built, tested, and `.github/workflows/deploy.yml` — the *only* way either
instance is deployed, because flyctl has no mobile client — was left deploying
without the flag. Every deploy would have served `git_sha: null` under a green
suite. Fixed, plus the Verify step now reads the sha back and **fails the
deploy on a mismatch**, so "we deployed X" is falsifiable in one GET.
`tests/test_build_identity.py::TestTheDeployPathActuallySetsIt`, red against
the pre-fix workflow (2 failed), green after.

### 2. The public demo was sizing off a $1,000 bankroll nobody chose — ADR 0041

`fly.demo.toml` set **none** of the risk caps. It fell through to the dataclass
defaults at `backend/config.py:400-405` — **1000 / 100 / 400 / 100**, ten times
looser than live's 100 / 10 / 40 / 10, **on the public URL**, and no test
noticed. A previous session found this, wrote it into the record, and never put
it into the config.

All six are now explicit in both files. **Verified by probe, not by reading the
toml:** the public `/api/gate` now publishes `bankroll_dollars: 100.0`. Live
gained one line (`MAX_ORDER_CONTRACTS`, which it was also inheriting) at the
value it already had — an inheritance removed, not a behaviour changed. **No
live risk value changed.**

- **Matching live was argued, not copied.** A rounder $1,000 photographs
  better and at $100 most demo cards read `Buy 1` — which is exactly the
  argument *for*: `Buy 1` is what the system actually produces, and a portfolio
  piece whose thesis is "the record is the product" cannot open by overstating
  its own size.
- **The bankroll is the fourth cap and the outermost one.** `size_position`
  computes `stake = kelly_used * bankroll` and only *then* trims. Counting three
  is precisely what let `fly.demo.toml` omit it unnoticed.
  `MAX_POSITION_DOLLARS` binds an **opening** order; `MAX_EXPOSURE_DOLLARS`
  binds by **accumulation** at the fifth concurrent market. Both are real, in
  different situations.
- The guard derives its required list from `RiskConfig`'s own fields, so a
  seventh cap fails the suite until both tomls state it — a hand-written list is
  how the first six got to six. A companion test forbids the demo being
  *looser* than live; deliberate divergence downward is still allowed.

### 3. The two files every session is ordered to read could not be opened

`tasks/NEXT.md` was **456,641 bytes**, `tasks/lessons.md` **418,992**. The Read
tool refuses above **262,144**. CLAUDE.md's opening line has instructed every
session to read both, and that has been impossible; sessions coped by reading
the head. ~875KB ≈ **219,000 tokens** — roughly half a session budget before any
work started. **A lessons file nobody can read is indistinguishable from not
having one**: this repo's "built but never called" defect, pointed at its own
memory.

Split into 22 dated shards under `tasks/archive/`. **Nothing was distilled,
reworded or dropped** — the shards reconstruct both originals to an identical
sha256, and independently re-checked here: **179 lesson headings in the archive,
179 in `git show 999857f:tasks/lessons.md`**. `NEXT.md` → 17KB, `lessons.md` →
19KB, both now a pattern index over the archive.
`tests/test_session_files_are_readable.py` observed red on both files first.

Found in passing: `CLAUDE.md` and `AGENTS.md` had **already drifted** about
which files to read, and `AGENTS.md` claimed to be quoting `CLAUDE.md`
"exactly". Both corrected. A reading instruction gets audited for content and
never for feasibility.

### 4. ADR 0038's open pre-commitment is discharged — ADR 0040

0038 is Accepted and committed in writing that *"the quarantined
`backend/agents/` orphans (ADR 0022) are now either wired or deleted"*. It had
not happened.

**The sentence naming the set was wrong, and executing it literally would have
deleted live production code.** `backend/agents/` holds seven files, not two:

| module | status | edge |
|---|---|---|
| `base.py` | **live** | `backend/api/routes.py:82` |
| `review.py` | **live** | `backend/runner.py:70` |
| `budget.py`, `skeptic.py` | **live** | via `review.py` |
| `__init__.py` | **live** | parent package of `base` |
| `scout.py`, `historian.py` | orphan | only a dockerignored script + tests |

Re-grepped independently before merging. `agent_fleet_configured` in
`/api/health` reads `AgentConfig.from_env()` — i.e. the `ANTHROPIC_API_KEY`
env var, `backend/agents/base.py:128` — and never touches the directory; it is
why `base.py` can never be deleted, and is *not* evidence about scout.

**Decision: amend, not delete.** Deletion was tested on a scratch commit and
`test_the_unmetered_callers_are_exactly_the_quarantined_ones` collapses to
`assert unmetered == set()` — vacuous in both directions. Scout and Historian
are the only members that mechanism has ever had, so deleting them turns a real
guard into decoration. Also: *"they spend credits per pass"* is false — nothing
calls them, so they spend zero. Quarantine is **why** the bill is zero.

**Found unlooked-for: the Historian's revival condition already fired and no
test noticed.** It cited ADR 0021 §8 Option F; ADR 0034 took Option F; the
check only verifies `revive_if` is a non-empty string. Both revival conditions
rewritten to conditions that are unfired and still reachable post-0038.

### The pattern this session kept hitting

**Three of the four items were briefed with a sentence that turned out to be
false**, each in the direction of *the record flattering the machine*: lane C's
brief named the wrong set; lane A found `CLAUDE.md`/`AGENTS.md` already drifted;
the build-id feature shipped with its own deploy path not calling it. That is
now **four sessions running.** Open the set before predicating over it.

### VERIFIED — the live `beta` strip renders, and every guard held

**Seen, on live, in Joe's own logged-in Chrome** (browser automation against his
session, 2026-08-17 ~10:15 PDT). This had stood unverified for two sessions
because the strip is behind the session cookie and no agent can hold one. It is
no longer an open claim.

```
SIGNAL TEST   UNRESOLVED   201 of 300 games              measured 5m ago
Not yet resolved — and that is not the same as no signal. ... 99 to go.
smallest resolvable +0.1911   beta -0.1403   se 0.0475
interval [-0.3314, +0.0509]   rows 3,780
by market type, diagnostic only:  moneyline -0.0809 · 120g · 67%
                                  prop      -0.5192 ·  81g · 33%
```

Every constraint the component's docstring names is honoured on the live screen:
`UNRESOLVED` is not rendered as "no signal" and carries the explicit sentence
saying so; `smallest_resolvable_beta` prints **before** the estimate; `beta`
never appears without `se` and the interval; the per-arm split is labelled
*diagnostic only* with each arm's share. And **`201`, not `420`** — it is
reading the live record, not the seeded demo database, which was the specific
failure `REFUSED` was invented to prevent.

**The numbers moved since the handoff, which is the recorder working:** `G`
199 → **201**, `beta_hat` −0.1412 → **−0.1403**, `se` 0.0478 → **0.0475**. The
G = 300 look still arrives on its own and nothing may depend on it.

The footer from `999857f` also renders — **ALSO SERVED · Rejections · Parlay
builder** — confirming the pages `Nav.tsx` called "still served" are now
reachable from the app.

**A note for the next session on where it is.** The strip is **not** at the top
of the page; it sits immediately above the cards (`frontend/src/app/page.tsx:219-228`),
deliberately — as a header it reads as a disclaimer nobody finishes, above the
cards it reads as a caption on them. Anyone told to "check the top of the Board"
will report it missing. It is also fetched with `.catch(() => null)` and
`SignalStrip` returns `null` for a null signal, so a genuine failure and a
mis-aimed look are the same picture from the top of the page.

---

## 2026-08-17 — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH

**`main` at `d5bd3fb`+, 2,992 tests pass, 10 xfailed, ruff clean, `tsc
--noEmit` clean — re-verified this session, not inherited. Demo at machine v18,
live still at v55 (the PRE-FIX image).** The hunt is still closed (ADR 0038) and
nothing here reopens it.

### Done — partner directive #1

**`GET /api/signal`, rendered above the cards on Board and Slate.** ADR 0039.

The extraction moved into `backend/analysis/clv_signal.py`; every expression was
lifted, not rewritten. **The reproduction was run before anything was built on
it**, which was the hard constraint: `git show HEAD:scripts/run_signal_test.py`
against the moved version, same dump, `diff` → nothing. `beta_hat -0.1412`,
`se_cluster 0.0478`, `G 199`. Then proved end to end by rebuilding a SQLite
database from the dump and asking the route — it returns the registered look.

- **`scripts/run_signal_test.py` is now a printer** over `build_report`. The
  harness an operator runs and the number the screen serves are one computation,
  not two that agree today.
- **The quarantine was reversed in the open.**
  `test_a_quarantined_module_has_not_been_wired_up_by_the_back_door` went red on
  the first import, which is what it is for. ADR 0039 records why: the
  quarantine's stated reason named the always-valid multiplier as the thing it
  protected, and the multiplier is what makes unlimited re-reading valid. **The
  `G = 300` look now arrives by construction rather than by discipline.**
- **31 new tests, both new guards observed red under a named mutation.** Nothing
  in the suite read `beta` before this. It could have drifted silently, which is
  exactly how `ev.py` was wrong for three days.
- **REFUSED is deliberately not UNRESOLVED**, and demo is why: its seeded
  history has no quotes to join, so a caller reading the cluster count off a
  refused report would publish **`G = 420`** on the public screen — a larger
  number than the live record's 199, off a database with no signal in it.

### Measured — the Odds API spend, and it was not what NEXT.md said

**1,104 credits used, 18,896 remaining**, since the tier was bought 2026-08-09.
Seven days, ~158/day, on pace for **~24% of the 20,000 tier — not 90%.** Source:
`inspect_live_db.py credits-tail` / `credits-month` on the live box, i.e. the
provider's own `x-requests-remaining`.

The 90% figure was `ODDS_DAILY_CREDIT_BUDGET = 600` (`fly.live.toml:185`) × 31.
**A ceiling is not a spend** — see `tasks/lessons.md`; the cap is never
approached (158 against 600). The per-call cost was wrong the same way: config
arithmetic predicts 2 credits, every one of the last 111 `api_credits` rows says
**6**.

**What this does and does not settle.** It settles that the recorder is not
consuming a tier. It does not make ADR 0038's "costs nothing" true — ~24% of a
paid tier is a real bill, and **the renewal is still Joe's decision, on the
invoice.** But it is no longer an argument for stopping the recorder.

### Deployed — both instances, on Joe's explicit go

**live at machine v56, demo redeployed, both verified by probing rather than by
reading a green check.**

| check | live | demo |
|---|---|---|
| `/api/health` | 200 | 200 |
| `/api/signal` | **401** — the route exists, behind the session | 200 |
| parity with `/api/gate`, `/api/board` | identical 401 | — |
| the strip renders on Board **and** Slate | not verifiable from here | yes, in its refusal state |

Live carried the retracted 52.00% / 0.38-point copy and `Buy N` until this
deploy; both are now gone from the money instance.

**One prediction did not come true, and the honest version matters.** The demo
was expected to publish `G = 420` if a caller read the cluster count off a
refused report. On the deployed demo the registered §2 population is **empty —
0 rows** — so it refuses on P1 at 0/0, not at 420/420. The seeded history does
not reach the population at all. The refusal path protects either way, and the
guard earned its place, but "it would have shown 420" was a projection from the
seed code and not a measurement of the deployed database.

**Live will fit rather than refuse.** `clv-coverage` on the box reports 9,437
scored rows carrying CLV across 7 series, so the §2 subset is populated and `G`
is now above the 199 of 2026-08-16. **Nobody has yet seen the live strip
rendered** — it sits behind the session cookie and no agent can hold one. That
is the one unverified thing in this entry.

### Open — Joe's call

- **Rotate `ODDS_API_KEY`.** A subagent read `.env` and the plaintext key landed
  in its transcript on disk. Not the Kalshi key. By this repo's own standing
  rule that counts as compromised.

### Done — directive #2, and its premise was wrong

**The nav audit found a decision, not a defect — and then a real bug inside
it.** Committed, not yet deployed.

Directive #2 read: *"a screen that is served but unreachable is this repo's
named defect in UI form."* `Nav.tsx:8-27` says otherwise, in writing and with
reasons. **Six links is a budget**: a seventh pushes the Gate — the screen that
says whether money can move — off the row at 390px. `/builder` lost its slot
because it prices sportsbook parlays, cannot change a bet on this venue, and
for a beginner can change one in the wrong direction. `/rejections` lost its
slot on 2026-08-15 because Slate is a strict superset of it. Two recorded
trades, not two oversights.

**The bug is one layer in.** That comment says *twice* that the pages are
"still served for anyone who wants it" — and there was **no inbound link
anywhere in the application.** Not the nav, not a footer, not contextually. The
escape hatch it promised was never built, and on a phone "type the URL" is not
a route a real person takes. A served page with no link is unreachable in
practice however true it is that the server answers.

Fixed with a **footer**, not a seventh nav link — the budget argument is right
and the Gate keeps its slot. Each entry carries a one-line blurb, because a
bare link named "Builder" invites a beginner to open a parlay calculator
expecting a Kalshi feature.

**`tests/test_every_screen_is_reachable.py`** now fails if any page with a
`page.tsx` is named in neither link list, if the nav budget stops being six, or
if the footer grows larger than the nav. Observed red by deleting a footer
entry. **The remedy it does not enforce: a page worth neither slot belongs in a
delete commit, and the footer must not become the place decisions go to be
avoided.**

The lesson is the recurring one — `tasks/lessons.md`, *"a collective noun is not
a measurement"*. The directive named a set (`/rejections` and `/builder`) and
predicated a defect over all of it in one breath. Opening the file took a
minute and falsified the predicate while leaving a smaller true finding behind.

### Still undecided, do not build it

`sharp-bettor`'s cost-of-execution meter — re-pointing the Board from "is this
mispriced?" to "is this cheaper on Kalshi or at a book?". Joe's call, unmade.

---


## Still open, as of 2026-08-17

Short by design. The long-form reasoning behind each is in the archive entry
named beside it.

- **The cost-of-execution meter is Joe's call, unmade.** `sharp-bettor`'s
  proposal to re-point the Board from *"is this mispriced?"* to *"is this
  cheaper on Kalshi or at a book?"*. Do not build it before he decides. Above,
  and `archive/next-2026-08-17.md`.
- **H4 is untested**, so the 0.63-point cost headroom is an upper bound, not a
  figure. Separating "settlement is free" from "`fee_cost` is entry-only" needs
  the account balance. ADR 0027.
- **The `G = 300` look happens on its own and nothing may depend on it.** The
  recorder keeps running because it costs nothing to leave running; `beta` would
  have to move 8.3 standard errors for the verdict to be anything but NO SIGNAL.
  ADR 0038, and `archive/next-2026-08-16.md`.
- **The Odds API renewal is Joe's decision, on the invoice.** ~24% of the 20,000
  tier in seven days is a real bill even though it is not the 90% this file used
  to claim. Above.
- **`ODDS_API_KEY` rotation is open, and it is a security item.** A subagent
  read `.env` and the plaintext key landed in a transcript. Tabled by Joe, not
  closed by anyone. It was recorded above but missing from this summary list,
  which is the list a future session actually reads — the omission is the bug.

**The build checklist that used to live at the bottom of this file** — *"1.
Blocked on you"*, *"2. Fix before any real money"*, *"3. Ready to build"*, *"4.
Verified working"*, *"The honest status"* — is in
[`archive/next-2026-08-07.md`](archive/next-2026-08-07.md). It is kept whole and
it is **stale**: it states 653 passing tests and a 52.00% taker bar, both since
superseded. `tasks/todo.md` is the live build log; read that, not the archived
checklist.

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

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
