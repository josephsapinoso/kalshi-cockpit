# ADR 0099 — A list is cut by league and kickoff window, and nothing else

**Status:** Accepted — numbered 0099 at the merge boundary, 2026-09-03.
**Date:** 2026-09-02.
**Decides:** decision-map #15 (resolved by Joe 2026-09-02, option A), as
built. Applies ADR 0071 §2.5 to a control. Unblocks #19 (with #31).

## 1. What changed

Until this ADR the product had no filter control at all: `/api/slate`
accepted `limit`, `/api/parlays` accepted nothing, and the Games list ran
dozens of rows with kickoffs from three hours to eight days out under a
heading about tonight (#15's own observation). Joe's stated first need —
"making it easy to filter picks, props, parlays" — had nothing to make easier.

Both list routes now accept two query parameters, and the three list screens
(Games, Picks, the parlay desk) carry one sticky bar that sets them:

```
GET /api/slate?league=<sport_key>&within_hours=<1..168>
GET /api/parlays?league=<sport_key>&within_hours=<1..168>
```

- **`league`** is the odds feed's sport key — `baseball_mlb`,
  `basketball_wnba`, `americanfootball_nfl`, `americanfootball_ncaaf`,
  `basketball_nba`, `icehockey_nhl` — the values of
  `backend/kalshi/discovery.py:IN_SCOPE_LEAGUES`, which is the set of
  leagues the desk can price at all.
- **`within_hours`** keeps games kicking off between the request's `now` and
  that many hours later, on the sportsbook's clock
  (`MIN(odds_snapshots.commence_ms)` per linked fixture — the clock the row
  prints, the sort key uses, and `backend/scoring.py` scores on).
- Either may be omitted. **Both omitted is the pre-existing behaviour, byte
  for byte**: no new key rides the unfiltered payload.
- When at least one is set the payload carries a `filter` echo —
  `{league, within_hours, kickoff_from_ms, kickoff_until_ms, hidden}` —
  where `hidden` is how many rows (slate) or candidate legs (ladder) the cut
  removed. A cut list must never read as a quiet night.
- **An unknown value is a 422**, with the allowed values in the detail. It is
  never ignored: a misspelt `league` that quietly returned the whole list
  would show everything under chips saying it was cut, which is the
  "unreadable resolves to a value" defect on a query string.

`backend/list_filters.py` parses both parameters for both routes, so the two
lists cannot come to accept different vocabularies for the same cut.

## 2. The decision: a cut removes rows and may never reorder them

ADR 0071 §2.5 says a per-row fact is transparency and an ordering is a claim:
the consensus-vs-Kalshi gap may be *shown* on a row and must never be
*ranked by*, because `beta = -0.141` means ranking by it puts the least
trustworthy rows at the top. #15 extends that rule from orderings to cuts, in
its own words: "ranking or filtering by the Kalshi-vs-consensus gap is out of
scope and must not be offered".

So the contract is: **league and kickoff window are the only cuts, and neither
route's ordering changes under either.** The slate keeps kickoff order with
the ticker as tiebreak (the 2026-09-01 correction that removed `edge_tenths`
from that key stands); each ladder card keeps its own cut's ordering. There
is no `sort` parameter and there will not be one. A third cut needs its own
ADR naming which of the two rules — shown-not-ranked, and cut-not-on-the-gap
— it does not break. Market type is not that third cut: #12 resolved as
"drop props", so there is nothing to cut by.

`tests/test_list_filters.py` pins the SQL the slate cut generates against
`ORDER BY`, `LIMIT` and every profit-readable stem; the filter echo's keys
against the same stems; and the bar's source against them and against the
word "sort".

## 3. Where the cut is applied, and why there

**On the slate, in SQL, before `LIMIT`.** The unfiltered list is
`ORDER BY suggested_contracts DESC ... LIMIT 100`, and #15's amendment
(2026-08-28) records that a client-side filter "cannot reach a game dropped
by `LIMIT 100`". A cut applied after the limit would inherit exactly that
defect. Applied before it, a league the full list could not fit is reachable
through its chip — which is the whole point of a cut, and the test
`test_the_cut_reaches_a_row_the_limit_would_drop` is the claim.

The two predicates resolve through the row's linked odds fixture, each an
indexed `SEARCH` on `odds_event_id` per row in the window — not the derived
table over every fixture in the history that this route was measured and
cured of on 2026-08-29 (77.3 ms of an 85.4 ms query). The window counts
(`slate.in_window`, `truncated`) describe the cut population so they compare
like with like; `older_than_window` and the echo's `hidden` are measured
against the whole window.

**On the ladder, on the candidate pool, before the cards are built.** A card
is then the same cut of a smaller pool, ordered exactly as it would be
unfiltered. The engine's own refusal counts (`excluded`) are untouched by a
cut, and the cut's own count lives on the `filter` echo — a filtered-out leg
is not a refused one. A one-game cut builds no card (a parlay needs two
legs), and every card says so in its own `not_built_reason`.

## 4. The vocabulary is the sport key, and the slate does not read `event_links.league`

Two vocabularies name the same partition in this database.
`event_links.league` holds Kalshi's `product_metadata.competition` verbatim —
`'Pro Baseball'`, `'Pro Basketball (W)'` — and `odds_snapshots.sport_key`
holds the odds feed's `baseball_mlb`. The parlay ladder already reads the
latter (after the 2026-08-26 alias-file defect, recorded in
`backend/parlays.py`), `frontend/src/lib/leagueLabel.ts` keys on it, and every
parlay leg carries it. So the parameter names the sport key, and the slate
resolves a row's league through its fixture's `sport_key` rather than the
link's label — one value cuts both lists on one column.
`test_the_league_is_the_fixtures_not_the_links_label` seeds links that all
say `'Pro Something'` and fixtures that differ, so a filter reading the wrong
column returns nothing and fails.

**Recorded, not fixed here:** the slate row's own `league` field (and the
`LeagueTag` it renders) is still `event_links.league`, so a Games row is
tagged "Pro Baseball" while its chip says "MLB". That is a pre-existing
inconsistency, outside this lane's file boundary, and this ADR leaves it
named rather than silently reconciled.

## 5. Where the controls live

**A sticky bar on each list, not the nav** — Joe's option A; the nav is at
its six-link budget. `frontend/src/components/FilterBar.tsx`, mounted in the
header region of `/slate`, `/picks` and `/parlays`.

- **Links, not state.** Every chip is a `Link` to the same page with the cut
  in the query string; each page is a server component that reads
  `searchParams` and sends the same string to the API through one builder
  (`listFilterQuery`), so the URL and the request cannot disagree. A cut is
  shareable and survives a reload, and no client JavaScript is involved.
  `prefetch={false}` on every chip is load-bearing: the list pages are
  `force-dynamic`, and a dozen prefetched chips would be a dozen `/api/slate`
  reads — one book query per row each — on every scroll past the bar.
- **Under the nav.** `Nav.tsx` is `sticky top-0 z-50`; the bar is `sticky
  z-30` at `top: var(--nav-height, 69px)`. 69px is the nav's rendered
  height, measured in headless Chrome at 390, 768 and 1280px (the first
  draft assumed 64px from the classes and was 5px short — measure, do not
  derive). A nav change moves the bar by setting the variable on the shell,
  not by editing the bar.
- **One row on a phone.** Below `sm` the chips sit in a closed `<details>`
  whose summary names the current cut ("Showing · MLB · starts within 3h"),
  so the sticky footprint is one row and the cut is never invisible; from
  `sm` up the chips render inline. Both forms are server-rendered.
- **The chips are the leagues the server accepts**, not the leagues with a
  game tonight. No payload carries the latter without breaking the
  unfiltered read's byte-identity, and an off-season chip honestly returns
  an empty list that says so. The test pins the chip list as a subset of the
  server's so no chip is a 422 one tap away.
- **A refused value is drawn as its own state.** `api.ts`'s `get` now throws
  `ApiError` with the status kept; a 422 renders "that cut is not one this
  desk carries" with the bar at its show-everything state, rather than the
  "backend unreachable" sentence every other failure gets.

## 6. What this does not do

- It does not discharge constraint 7's "knows his game" arrival. #15's
  amendment is explicit: a cut cannot reach a started game, a game outside
  the 30-minute recorder window, or a game the recorder never evaluated.
  That is the search-destination ticket's job.
- It does not change what is bettable. `suggested_contracts`, the suppression
  reasons and `POST /api/orders`' server-side re-derivation are untouched;
  the cut governs what is *visible* on a list; suppression and staleness
  keep governing what is *bettable*, exactly as the Board's own disclosure
  puts it (`routes.py`, the `/api/board` comment on "This relaxes nothing").
- It does not measure anything. `check_mobile.py` at 390px measures overflow,
  not usability; whether the bar is the control Joe reaches for is a question
  for his hands.
