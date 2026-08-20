# Result — the spread/total falsification test: UNDERPOWERED, both arms

**Registration:** `docs/measurements/2026-08-20-preregistration-spread-total-edge.md`,
committed before the sweep. Every rule applied below is that file's; nothing
was chosen after seeing a number.

**Taken:** 2026-08-20 **21:26:16Z**, inside the registered `baseball_mlb`
21:21Z–22:21Z window, 70 minutes before the slate's earliest first pitch
(22:36Z) — both §3 conditions met. One sweep, `spreads,totals` × `us,eu`,
4 credits. The vendor counter (`x-requests-used` 1336 / remaining 18664) is
recorded in the raw artifact per the registration's ledger note.

**Artifacts, committed beside this file:**
`2026-08-20-spread-sweep-raw-2026-08-20T212616Z.json` (the sweep + Kalshi
books + `/series` fee meta), `2026-08-20-spread-edge-rows-2026-08-20T212616Z.json`
(every computed row and every exclusion count). `--replay` on the raw file
reproduces this document's numbers without spending.

**One protocol note.** The first invocation, 21:21:04Z, spent nothing: the
local `ODDS_API_KEY` was stale and the vendor returned 401 before serving.
The successful sweep at 21:26:16Z is the registration's single look — the
401 was a refused request, not a look at data.

## 1. The verdicts

Registered floor (§6): fewer than **8 sharp-anchored rows** or fewer than
**3 distinct games** ⇒ UNDERPOWERED, read before any effect.

| arm | rows | sharp-anchored | games | floor | verdict |
|---|---|---|---|---|---|
| KXMLBSPREAD | 11 | **3** | 3 | 8 rows | **UNDERPOWERED** |
| KXMLBTOTAL | 12 | **2** | 2 | 8 rows / 3 games | **UNDERPOWERED** |

**No pass, no fail. C1 is untested tonight and the ADR 0038 quadrant row is
unchanged.** The registration's own words: *"no pass, no fail, and the
quadrant row is unchanged."* The convening authorized one sweep; a second
look on a fuller slate is a new authorization, not a continuation.

## 2. What the underpowered look contains, described and not decided

All five sharp-anchored rows, at the charged fee (k = 0.035, the
`fee_multiplier`-verified arm):

```
KXMLBSPREAD-26AUG201835NYYBAL-NYY2   line -1.5  ask 390  fair 0.373  25 books   -25.0t
KXMLBSPREAD-26AUG202005WSHTEX-TEX2   line -1.5  ask 430  fair 0.435  25 books    -3.5t
KXMLBSPREAD-26AUG202010LAAHOU-HOU2   line -1.5  ask 460  fair 0.450  25 books   -19.2t
KXMLBTOTAL-26AUG201835NYYBAL-8       line +7.5  ask 490  fair 0.483  22 books   -15.3t
KXMLBTOTAL-26AUG202005WSHTEX-8       line +7.5  ask 480  fair 0.486  22 books   -2.9t
```

Every row is negative, at both fee arms, in the direction the h2h prior
(`beta = -0.141`) predicts. **Five rows across three games is a
description, not a finding** — the floor exists precisely so this sentence
cannot be promoted into a verdict. Anyone quoting these numbers quotes the
UNDERPOWERED verdict with them.

## 3. C2, the overlap premise: met, and thinner than the h2h join

At least one book quoted both sides at a Kalshi-listed line for every
matched game (25 contributing books on spreads, 22 on totals — C2 holds;
this is not NO-OVERLAP). But the exclusion counts show where the population
went: **152 `no_exact_line`** (Kalshi lists rungs the books do not quote at
exactly that line), **136 `one_sided_book_dropped`**, **11 `lt_two_books`**.
The venue's spread/total ladders are mostly rungs with no devig-able book
counterpart at exact-line equality; the tradable overlap on a 3-game slate
was 5 sharp-anchored rows. A future look sized for the 8-row floor should
expect roughly 1.7 sharp rows per game and pick its slate accordingly
(≥5 games, more when day games thin the EU books).

## 4. Facts recorded in passing

- `/series` fee meta re-confirmed live at sweep time: `fee_multiplier` 0.5
  on both MLB series; `fee_type` `quadratic` on both KXMLBSPREAD and
  KXMLBTOTAL — consistent with `tests/fixtures/series_fee_fields.json` and
  with ADR 0058's hole 1 (the `quadratic` vs `quadratic_with_maker_fees`
  split is between series, unresolved for maker fees).
- One Kalshi spread event matched no odds fixture (`unmatched_game` 1) and
  one totals event had no spread sibling (`no_spread_sibling` 1) — both
  excluded and counted per §4, neither approximated.

## 5. What this does not establish

The registration's §8 in full, plus: nothing about slates larger than 3
games, nothing about the exclusion profile on a full evening slate, and
nothing that moves any row of the ADR 0038 table — UNDERPOWERED leaves the
quadrant exactly where the morning left it.
