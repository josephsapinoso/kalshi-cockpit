# Lane: research — what `occurrence_datetime` actually is

Measured 2026-08-07 against the live Kalshi REST API. **Zero Odds API credits
spent.** Harness: `scripts/measure_occurrence_datetime.py`. Raw evidence
captured to `tests/fixtures/occurrence_datetime_probe.json`.

---

## The answer

**`occurrence_datetime` is the scheduled START, shifted +3h. Story A. Story B
is refuted, and its 198-of-200 observation has a boring explanation.**

Three independent measurements, none of which needs a sportsbook.

### 1. Period markets — the discriminator. n = 171 pairs, 15 series pairs

A first-half / first-five-innings market and its full-game market are the same
fixture. A **start** is shared; an **expected end** must make the period market
*earlier*.

| period series | vs game series | n | occ(period) − occ(game) |
|---|---|---:|---|
| KXMLBF5 | KXMLBGAME | 15 | **+2.00h** ×15 |
| KXMLBF5SPREAD | KXMLBGAME | 15 | +0.00h ×15 |
| KXMLBRFI | KXMLBGAME | 40 | +0.00h ×40 |
| KXEFLCUP1H | KXEFLCUPGAME | 29 | +0.00h ×29 |
| KXLEAGUESCUP1H | KXLEAGUESCUPGAME | 13 | +0.00h ×13 |
| KXUSL1H | KXUSLGAME | 11 | +0.00h ×11 |
| KXBRASILEIRO1H | KXBRASILEIROGAME | 10 | +0.00h ×10 |
| KXBRASILEIROC1H | KXBRASILEIROCGAME | 10 | +0.00h ×10 |
| KXBRASILEIROB1H | KXBRASILEIROBGAME | 7 | +0.00h ×7 |
| KXJLEAGUE1H | KXJLEAGUEGAME | 6 | +0.00h ×6 |
| KXKLEAGUE1H | KXKLEAGUEGAME | 5 | **+0.50h** ×5 |
| KXEREDIVISIE1H | KXEREDIVISIEGAME | 4 | +0.00h ×4 |
| KXLIGAPORTUGAL1H | KXLIGAPORTUGALGAME | 3 | +0.00h ×3 |
| KXSCOTTISHPREM1H | KXSCOTTISHPREMGAME | 2 | +0.00h ×2 |
| KXMLS1H | KXMLSGAME | 1 | +0.00h ×1 |
| KXNFL1H, KXNCAAF1H, KXWNBA1H, KXEPL1H, KXUCL1H | — | 0 | no open fixtures today |

Pooled: **+0.00h on 151/171 (88.3%), +0.50h on 5, +2.00h on 15.**

**Period market earlier than its full game: 0 of 171.** An expected end requires
that on every pair. It happens on none. Two example rows to re-check by hand:

```
KXEFLCUP1H-26AUG08BARWIG   occ 2026-08-08T17:00:00Z
KXEFLCUPGAME-26AUG08BARWIG occ 2026-08-08T17:00:00Z   identical
KXMLBRFI-26AUG081505ATLNYY   occ 2026-08-08T22:05:00Z
KXMLBGAME-26AUG081505ATLNYY  occ 2026-08-08T22:05:00Z  identical
```

`KXMLBRFI` is "run in the first inning" — it resolves about twenty minutes
after first pitch. Its `occurrence_datetime` is bit-identical to the full
game's on 40 of 40. No end-semantics survives that single row.

**The two non-zero groups are Kalshi data entry, not semantics.** `KXMLBF5`
(first five innings, moneyline) sits +2h from the game — but `KXMLBF5SPREAD`,
covering the *identical* period on the *identical* fixture, sits at +0.00h.
Two series about the same five innings disagree with each other, so the value
cannot be derived from the period. `KXKLEAGUE1H` is +30 min against its own
game market on 5 of 5, same event ids (`26AUG08ANYDAJ`: 1H 14:00Z, game
13:30Z) — another per-series typo. Both are *later*, and no end can be later.

### 2. The offset, anchored on Kalshi's own rulebook. n = 40 MLB fixtures

`KXMLB*` `rules_primary` states the scheduled first pitch in words:

> "…the Atlanta vs New York Y professional baseball game originally scheduled
> for **Aug 8, 2026 at 3:05 PM EDT**…"

That is a true start time, free, inside the payload. **MLB is the only league
whose rules text carries a clock time** — everyone else states a date only.

| series | events | anchored | occ − start | exp − start | close − start |
|---|---:|---:|---|---|---|
| KXMLBGAME | 40 | 40 | **+3.00h ×40** | +3.00h | +72.00h |
| KXMLBRFI | 40 | 40 | +3.00h ×40 | +3.00h | +72.00h |
| KXMLBEXTRAS | 40 | 40 | +3.00h ×40 | +3.00h | +48.00h |
| KXMLBF5SPREAD | 15 | 15 | +3.00h ×15 | +3.00h | +72.00h |
| KXMLBSPREAD | 15 | 15 | +3.00h ×15 | +3.00h | +72.00h |
| KXMLBTOTAL | 15 | 15 | +3.00h ×15 | +3.00h | +72.00h |
| KXMLBTEAMTOTAL | 15 | 15 | +3.00h ×15 | +3.00h | +72.00h |
| KXMLBKS | 9 | 9 | +3.00h ×9 | +3.00h | +72.00h |
| KXMLBF5 | 15 | 15 | **+5.00h ×15** | +3.00h | +72.00h |

Zero variance. **+3.00h on 189 of 189** anchored fixtures outside `KXMLBF5`,
and the 40 `KXMLBGAME` fixtures span every venue zone on the slate — SEA, LAD,
SD, SF, AZ (Pacific/Mountain), TEX MIN KC MIL STL CWS CHC (Central), NYY BOS
PHI ATL WSH (Eastern). **The offset does not vary with the venue's timezone**,
so it is a single fixed shift applied to a time Kalshi already holds in ET, not
a per-game timezone conversion. Two worked rows:

```
KXMLBGAME-26AUG081505ATLNYY-ATL
  rules start 2026-08-08T19:05Z (3:05 PM EDT)
  occurrence_datetime       2026-08-08T22:05:00Z   = start +3h
  expected_expiration_time  2026-08-08T22:05:00Z   = start +3h
  close_time                2026-08-11T19:05:00Z   = start +72h exactly

KXMLBGAME-26AUG102210KCLAD-LAD   (Pacific venue)
  rules start 2026-08-11T02:10Z; occurrence_datetime 2026-08-11T05:10Z  = +3h
```

Note the internal contradiction, useful because it is on one market: **`close_time`
sits exactly 72h after the *true* start, while `occurrence_datetime` sits 3h
after it.** Two fields derived from the same scheduled first pitch, disagreeing
by three hours, in the same object.

Also useful: the MLB event id embeds the ET start (`26AUG08**1505**ATLNYY` =
3:05 PM ET), agreeing with the rules text on 40 of 40. `kalshi-api/SKILL.md`
says the `{HHMM}` block appears "only when a league plays two games between the
same pair on one date" — **on today's slate every one of the 40 MLB event ids
carries it**, doubleheader or not. Worth correcting in the skill file.

### 3. Settled fixtures — the cross-league magnitude check

`settlement_ts − occurrence_datetime` on settled markets. Settlement lands a few
minutes after the real result, so this estimates `game_length − offset`.
**Story B predicts ≈ 0.00 in every league.** Story A predicts a number that
tracks how long the sport takes.

| series | n | median | min | max | nominal game | implied offset |
|---|---:|---:|---:|---:|---:|---:|
| KXNFLGAME | 1 | +0.12h | +0.12 | +0.12 | 3.10h | +2.98h |
| KXNHLGAME | 11 | −0.02h | −0.21 | +1.44 | 2.60h | +2.62h |
| KXNBAGAME | 9 | −0.12h | −0.50 | +0.11 | 2.40h | +2.52h |
| KXMLBGAME | 15 | −0.17h | −0.46 | +2.55 | 2.75h | +2.92h |
| KXWNBAGAME | 15 | −0.46h | −0.72 | −0.16 | 2.20h | +2.66h |
| KXMLSGAME | 15 | −0.78h | −0.94 | +1.22 | 2.00h | +2.78h |
| KXEFLCUPGAME | 6 | −0.81h | −0.99 | −0.10 | 2.00h | +2.81h |
| KXUCLGAME | 15 | −0.97h | −2.43 | +0.08 | 2.00h | +2.97h |

The medians spread **1.09h** across eight leagues and order themselves by game
length — football ≈ 0, hockey/basketball/baseball ≈ 0 to −0.2, soccer ≈ −0.9.
Under story B every row would sit at 0.00. Under story A the implied offset
lands in **+2.52h … +2.98h**, i.e. three hours, in every league measured.

For WNBA and soccer, Kalshi **settles the market before `occurrence_datetime`
arrives** — `KXWNBAGAME-26AUG07GSDAL-DAL` settled `2026-08-08T04:07:15Z`
against `occurrence_datetime 2026-08-08T04:30:00Z`. A field that a settled
market has already passed cannot be that market's start *or* its expected end;
it can only be a start with a forward shift larger than the sport is long.

The `n=1` NFL row and `n=0` NCAAF/EPL rows are seasonal, not a failure — read
them as absent, not as agreement.

### Why story B looked true: `expected_expiration_time` is a copy

| series | markets | exp − occ | close − occ |
|---|---:|---|---|
| KXMLBGAME | 80 | +0.00h ×80 | +69.00h |
| KXMLSGAME | 111 | +0.00h ×111 | +51.00h |
| KXEFLCUPGAME | 93 | +0.00h ×93 | +51.00h |
| KXNCAAFGAME | 30 | +0.00h ×30 | +45.00h |
| KXUCLGAME | 30 | +0.00h ×30 | +51.00h |
| KXWNBAGAME | 18 | +0.00h ×18 | +45.00h |
| KXEPLGAME | 18 | +0.00h ×18 | +51.00h |
| **KXNFLGAME** | 64 | **+0.00h ×34, +3.00h ×30** | +45.00h |

`expected_expiration_time` equals `occurrence_datetime` almost everywhere
because Kalshi copies the one into the other — including on `KXMLBRFI`, which
plainly does not expire three hours after first pitch. The equality is
therefore evidence about `expected_expiration_time`, not about
`occurrence_datetime`.

**NFL is the one series that populates it independently, and it settles the
direction:**

```
KXNFLGAME-26AUG13DETCIN-CIN
  occurrence_datetime      2026-08-14T02:00:00Z
  expected_expiration_time 2026-08-14T05:00:00Z    = occ + 3h
```

Where the two fields differ, **`occurrence_datetime` is the earlier one by one
football game**. That is start-then-end, not end-then-something.

---

## What this does NOT establish

- **The +3h magnitude is measured against a true start for MLB only** (n=40,
  exact, zero variance). Every other league's offset is bounded through
  `settlement_ts`, which is good to roughly ±20 min, not to the minute. It is
  ~3h everywhere measured; it is *exactly* 3h only where MLB is concerned.
- **Nothing here says the offset is stable.** It is a Kalshi data-entry
  artifact, not a documented contract, and can be corrected without notice.
  This is the argument *for* recording `commence_skew_ms` rather than
  subtracting 3h in discovery — that decision is confirmed, not overturned.
- **Postponed and rescheduled fixtures are untested.** Every fixture sampled is
  one Kalshi has not moved. A rescheduled game may carry a stale
  `occurrence_datetime` and nothing measured here would notice.
- **One slate.** The period-vs-game structure is a fact about how Kalshi
  populates the field and is unlikely to be a day effect; the settlement
  medians are from fixtures settled in the last week (NBA/NHL from the
  May–June playoffs).
- **No liquidity, price, or edge claim.** Period markets are named here only as
  a measuring instrument. Nothing suggests trading them.
- **`KXMLBF5` +2h and `KXKLEAGUE1H` +30min are described, not explained.** They
  are consistent with per-series misconfiguration and are contradicted by a
  sibling series on the same period, but the cause is not established.
- **No test in the suite pins any of this.** The harness is a script; nothing
  fails if Kalshi changes tomorrow. See the recommendation below.

---

## Consequences for `linker.py` and `suppression.py`

**The fixed tolerance is not wrong. Do not change either number.** The whole
worry — "if the offset is game-length-dependent then a fixed tolerance is wrong
for any sport that is not three hours long" — is now closed: the offset is
**not** game-length-dependent. It is a constant applied per fixture, identical
for a 20-minute first-inning market and a full baseball game, and it does not
move with the venue's timezone. `DEFAULT_COMMENCE_TOLERANCE_MS = 4h` and
`max_commence_skew_ms = 4h` remain correct for every league in
`IN_SCOPE_LEAGUES`, including the 2-hour ones, and would remain correct if
soccer entered scope.

Four changes worth making, none of them to a threshold. **I did not make any of
them** — `linker.py` and `suppression.py` are outside this lane.

1. **Correct the comment in `linker.py:47-57`, and only the comment.** It
   reasons "WNBA games run about two hours and MLB about three, so if
   `occurrence_datetime` were the expected *outcome* time the offsets would
   differ by an hour; they are identical, which makes it a fixed shift". That
   inference was right and is now directly measured, but the comment leans on a
   sportsbook comparison the repo can no longer re-run for free. Replace the
   justification with the free one: *`KXMLBRFI` — resolved after one inning —
   carries the same `occurrence_datetime` as the full game on 40 of 40, and MLB
   `rules_primary` states the true first pitch, putting the offset at exactly
   +3h across every venue timezone.* Cite
   `scripts/measure_occurrence_datetime.py`.
2. **Kill the "US Eastern-to-Pacific gap" gloss** in `linker.py` and
   `tasks/lessons.md`. It is a plausible cause, not a measured one, and it is
   the *only* claim in that comment that a future session could act on wrongly
   — someone reading "timezone conversion" may reasonably try to fix it with a
   `zoneinfo` lookup keyed on the venue. The measurement says the shift is
   applied to a time Kalshi already holds in ET and is the same for a Seattle
   game and a Boston game. Say "a fixed +3h shift, cause unknown".
3. **Pin it with a test, from the new capture, not from the network.**
   `tests/fixtures/occurrence_datetime_probe.json` carries the MLB rules text
   beside the timestamps, so a wire-format test can assert
   `occurrence_datetime − rules_start == 3h` and
   `occ(KXMLBRFI) == occ(KXMLBGAME)` without a request. Today
   `OBSERVED_KALSHI_COMMENCE_OFFSET_MS` is asserted by
   `TestKalshiOccurrenceDatetimeRunsLate` against a hand-set value; anchoring it
   to a captured payload makes it a wire-format test in the sense CLAUDE.md
   means. (`tests/**` is another lane's, so this is a request, not a change.)
4. **`event_commence_ms` in `discovery.py` takes the first market's
   `occurrence_datetime` and returns.** On every game-level series measured all
   markets in an event agree, so this is currently safe — but `KXMLBF5` vs
   `KXMLBF5SPREAD` proves Kalshi will happily ship two values for one fixture
   across series, and 35 open sports events (all futures, `KXMLBDEBUT` and
   friends) already carry *different* `occurrence_datetime` values on markets
   within a single event. If a period series ever enters scope, that function
   silently picks whichever market sorted first. Cheap fix: read them all and
   refuse on disagreement, consistent with "ambiguity refuses".

---

## Needed and could not own

- **`tasks/NEXT.md` has no "Verify what `occurrence_datetime` actually is"
  item** at the commit this worktree branched from (`a4f2c2c`) — the only
  mention of the field is line 869, inside the completed chain-runner entry.
  The brief quoted the item, so the integrator is presumably adding it; this
  report answers it either way, and the entry can be closed on merge.
- **`tasks/lessons.md`** "Two limits on one quantity" should keep its lesson
  (the composed-limits pattern is untouched) but lose the Eastern-to-Pacific
  gloss, per item 2 above.
- **`.claude/skills/kalshi-api/SKILL.md`** needs two corrections I could not
  make: the `{HHMM}` block is present on *all* MLB event ids, not only
  doubleheaders; and `occurrence_datetime` deserves a line of its own — it is
  the start, +3h, and `expected_expiration_time` is usually a copy of it and
  should never be read as an end.
- **A settled-market fixture.** `settlement_ts` turned out to be the only free
  cross-league anchor for game timing, and nothing in `tests/fixtures/` carries
  a settled market. Worth capturing properly if anyone measures venue timing
  again.

---

## Reproducing

```
.venv\Scripts\python.exe scripts\measure_occurrence_datetime.py
.venv\Scripts\python.exe scripts\measure_occurrence_datetime.py --capture
```

223 Kalshi requests, ~2 min, read-only, unauthenticated (`/series`, `/events`
and `/markets?event_ticker=` all answer 200 with no credentials, so the script
never loads the private key). Never paginates `/markets`. **Never calls The
Odds API.**
