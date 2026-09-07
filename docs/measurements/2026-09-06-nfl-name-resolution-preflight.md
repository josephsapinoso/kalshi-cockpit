# NFL name resolution, taken before the season opener

**Date:** 2026-09-06, three days before the 2026 NFL opener (Wednesday
2026-09-09; Week 1 closes Monday 2026-09-14).
**Instrument:** `scripts/capture_team_names.py --league nfl`
**Cost:** **zero odds credits.** `x-requests-last: 0`, read off the response
rather than assumed — `/v4/sports/{key}/events` returns fixtures without odds.
The ranking that produced this item estimated ~4 credits; that estimate was
for `/odds`, which was not needed and not called.

## The question

`backend/match/aliases/americanfootball_nfl.yaml` carried five entries whose
header documented the **Kalshi** side from a real capture. The book side had
never been paired against a live Odds API feed. NCAAF got exactly that pass on
2026-08-26; NFL never did, and `americanfootball_nfl` had **0 rows in
`api_credits` lifetime** — the desk had never seen an NFL slate at all.

The asymmetry is what made it urgent rather than the probability: a Week 1
board that renders unmatched is a board with no prices on the one weekend that
matters, and the pairing is unrecoverable once the season is under way.

## Population

| | |
|---|---|
| Kalshi | 32 open `KXNFLGAME` events, kickoffs 2026-09-10 03:20Z – 2026-09-22 03:15Z |
| Odds API | 272 upcoming `americanfootball_nfl` fixtures, through 2027-01-10 |
| Excluded | preseason, by production's own `classify_series` |

**The exclusion is the one methodological point worth reading.** `KXNFLGAME`
carries preseason *and* regular season under one series ticker — same
`competition_scope` ("Game"), differing only in
`product_metadata.competition` (`discovery.py:288-297`). Filtering on the
series ticker alone would have pulled preseason fixtures the odds feed does
not carry and reported them as unmatched **names**, which is a fabricated
alias list. Every event therefore goes through `classify_series` and is kept
only if its `sport_key` is `americanfootball_nfl` — the same call the runner
makes, so an event counted here is one production would have counted.

The script calls `link_event`; it does not reimplement matching. Bucketing on
`MatchResult.reason` means every category is one the runner would record.

## Result

```
linked                   32
needs_alias               0
not_carried               0
no_fixture_in_window      0
ambiguous                 0
not_two_sided             0
other                     0
```

**32 of 32, with the alias file absent.** Re-run with the file loaded: no
change. The deterministic token-prefix rule carries the whole league.

**It is a census over teams, not a sample.** All **32 franchises** appear on
the Kalshi side and all 32 on the book side, so no NFL team sits outside the
population that resolved. Without that check, "32 of 32 linked" would be
compatible with a slate that happened to omit the awkward names — the two
shared-city pairs are in it (`New York G`/`New York J`,
`Los Angeles R`/`Los Angeles C`), and both resolve.

## What was refuted

The alias file's header called `Washington: Washington Commanders` **"a
genuine override"**, distinguishing it from the four it described as
documentation only. It is not one: the baseline run links Washington's fixture
with the entire file removed, because `washington` is a token prefix of
`washington commanders` exactly like every other city in it.

Nothing was added to the file and nothing was deleted from it — the five
entries are inert, and an entry that agrees with what the prefix rule already
produces cannot mask a drift in the direction that matters. What changed is
the header, which now carries the derivation date, the instrument and the
result.

## What this does not establish

- **That a linked fixture is a priced one.** Linking is name resolution.
  Market cost, book two-sidedness and devig success are all downstream.
- **That the capture covers the season.** Two weeks of Kalshi events. Every
  franchise appears in that window, which is what makes it a census over
  *teams*; it is not one over fixtures, and a mid-season Kalshi rename would
  not be caught by it.
- **Anything about preseason names.** Preseason was excluded, on purpose.
- **Anything about spreads, totals or props.** Names only.
- **That NFL Week 1 is safe.** Only that names are not the thing that will
  break. The open credit question (a four-sport budget day against a 700 cap,
  where a breach stops the whole feed rather than throttling one sport) is
  separate and unresolved.

## Two process notes

**A guard that forbids a phrase trips on its own correction.** The first
version of `test_nfl_names_resolve.py` asserted `"genuine override" not in`
the YAML. The corrected header *quotes* that phrase in order to record what
was wrong, so the guard failed on the history rather than on the claim —
the same shape as the combo guard that tripped on an `ADR 0012 §5` citation
the same week. It was replaced by a check that the header carries its
**provenance** (date + instrument), which is the property actually worth
having: every wrong claim this file has carried was one nobody could date.

**One assertion was written, found unfalsifiable, and deleted.** A test
compared the linked set with an empty alias mapping against the set with the
file loaded and asserted they were equal. It passed and could not have done
otherwise: an alias can only *add* a link, the baseline is already all 32, so
the sets are equal by arithmetic whatever the YAML says. Mutating an entry to
`Washington: Denver Broncos` left it green, which is how it was caught. The
property is already established by the baseline test one class up — a file
cannot rescue a fixture that resolves without it — so the redundant test was
removed rather than kept as coverage it does not provide.

## Artifacts

- `tests/fixtures/nfl_names_kalshi.json` — reduced capture: event ticker,
  kickoff, team names. No prices, no market payloads (the full Kalshi payload
  is megabytes, this repo is public, and a name test needs no price).
- `tests/fixtures/nfl_names_books.json` — fixture id, kickoff, both team names
  as the books spell them. No odds.
- `tests/test_nfl_names_resolve.py` — five assertions, each mutated and
  observed red except the one deleted above.
