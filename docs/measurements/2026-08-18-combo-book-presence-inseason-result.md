# Combo book presence, read in season — and the claim it actually corrects

**Date:** 2026-08-18T02:01Z
**Artifact:** `docs/measurements/2026-08-18-combo-book-presence-inseason.json`
**Command:** `scripts/measure_combo_book_presence.py --max-books 25`
**Cost:** 15 API calls, unauthenticated, read-only. No Odds credit. Nothing
created, nothing ordered, no `multivariate_event_collections` lookup.

## Why it was run, and what it was briefly written up as

`backend/kalshi/combos.py` records the 2026-08-06 combo capture and caveats it
honestly: NBA finished, NFL in preseason, so it "measures the calendar at least
as much as the product." This run was meant to answer the in-season version of
that question for MLB and WNBA.

**It was first written up as finding an in-season effect. That was wrong, and
the retraction is the useful part of this file.**

## The result

11 open `KXMVECROSSCATEGORY` combination markets carrying a readable ask were
read. Two reported non-zero `volume_fp` / `open_interest_fp`.

**This is not an in-season effect.** The same harness returned **3 of 20**
non-zero rows in `2026-08-09-combo-e2-book-empty.json` and **3 of 9** in
`2026-08-09-combo-e3-list-no-bid.json`. Fisher exact, two-sided, 2/11 against
6/29: **p = 1.0**. Wilson intervals overlap almost completely — 18.2%
[5.1, 47.7] against 15.0% [5.2, 36.0] and 33.3% [12.1, 64.6]. This run is the
middle of the three.

**And it could not have detected one.** The sample is **78% tennis** by leg
(`KXWTAMATCH` 31 + `KXATPMATCH` 23 of 69 leg slots), while MLB and WNBA were
*already in season* on 2026-08-09. The only sports absent from the 2026-08-06
capture were NBA and NFL; this run carries zero NBA legs and 5 NFL legs dated
`26AUG20`, still preseason. **The calendar caveat in `combos.py` is untouched
and remains open.**

## What it does establish: a bookkeeping correction dated 2026-08-09

`CLAUDE.md`'s quadrant row read *"zero volume, zero open interest"*.
`scripts/analyse_combo_domination.py:71` — the closest thing to a source —
says these markets "**mostly** carry zero volume and zero open interest." The
hedge was dropped between the script and the spine, and the hardened version
was **already contradicted by this repo's own committed artifacts on
2026-08-09**, nine days before anyone looked.

The correct statement: **some quoted combination markets have traded; the share
has been ~15–33% of quoted rows in every run, in and out of season, and no run
has enough independent rows to narrow that.**

## The strongest true statement in the data

Across all **40** combination markets this repo has ever read a book for —
three runs, two dates — **`yes_dollars` is empty on 40/40 and no YES bid has
ever been observed.** The list ask is the complement of a resting NO bid, not a
quoted offer: `derived_ask == list_ask` on 11/11 of this run.

**You can enter and you cannot exit.** The deepest resting order here was 18.00
units at 0.13; one row's was 1.00.

That is a better basis for the quadrant row than the volume claim it replaces,
and it reaches the same conclusion by a route that does not depend on a rate.

## What this does NOT establish

- **Nothing about the 2026-08-06 leg-quoter measurement.** That counted legs
  with an active quoter across `/multivariate_event_collections`. This run read
  zero collections. Different endpoint, different unit; it cannot contradict it.
- **No rate over `KXMVE` combinations.** The scan denominator is logged to
  stdout and dropped by `to_json`. `--max-books 25` returned 11, so the
  eligible pool was exhausted: this is a census of eligible-within-one-page.
- **n is not 11.** 23 distinct leg markets fill 69 leg slots; one ATP match
  appears in 7 of the 11 rows, and 5 of 11 rows share an order book byte for
  byte with another row. Effective n is about **2** — one tennis parlay family
  and one MLB pair. The repo's ≥5-per-side rule fails outright.
- **Nothing about combo pricing.** A combo-ask-versus-product-of-leg-asks
  "premium" was computed (+1.61%, +4.47%) and is **retracted in full**. The
  benchmark is unreachable: the MLB row's two legs are
  `KXMLBGAME-26AUG181840MIAPHI` and `KXMLBGAME-26AUG181840SFCLE` — **identical
  start time**, so there is no order in which the legs can be rolled. It also
  computes an implied joint from an ask-only quote, which ADR 0012 Decision 2
  explicitly refuses, charges no fee on either side against an unverified combo
  fee model, and rests on n = 1 per figure.
- **Nothing about units.** `volume_fp` / `open_interest_fp` returned
  non-integer values in prior runs (213.28, 509.09, 146.23). Whether these are
  fractional contracts or notional is unpinned. **"104 contracts" and "706
  contracts" may not be written.**
- **`volume == open_interest` is not a tell.** It holds on **8 of 8** non-zero
  MVE rows this repo has ever recorded, across both dates. It is a property of
  the field pair on a product with no YES bid — nothing can close, so open
  interest never decays. The observation that would separate that from a real
  market is any MVE row with `open_interest_fp < volume_fp`: **0 of 8.**
- **Nothing about when the volume printed.** Row 1's seven legs are all
  `26AUG17` tennis, observed 8.5 hours after creation and after those matches
  had played. Volume is cumulative and carries no timestamp.
- **Nothing that reopens a quadrant of ADR 0038.** Taking every number at face
  value, an enter-only market ≤18 units deep with no verified fee model
  supplies no edge to multiply.

## A defect in the harness, fixed

Two sentences in `measure_combo_book_presence.py`'s own limitations section
were false:

- *"These rows are provisional with zero volume and zero open interest"* — a
  limitations section asserting the claim under dispute, and false in the very
  artifact that code first produced.
- *"Newest-first, so youngest"* — this run's rows were created 17:14–17:33Z and
  observed at 02:01Z. An 8.5-hour-old residue, not a young sample.

Both corrected. `is_provisional` is on the `/markets` payload and still is not
recorded, so this module cannot confirm its rows sit in the population ADR 0012
§5 describes.

## Cheapest follow-ups, unrun

1. Re-read the same 11 tickers and persist `volume_24h_fp`, `last_price_dollars`,
   `is_provisional`, `status` — **all were on the payload already fetched and
   discarded by `to_json`.** `volume_24h_fp` dates the flow; `last_price_dollars`
   is the price the traded rows actually printed at.
2. Persist the page denominator. `collect()` already logs it.
3. Re-run mid-slate (~20:00Z) with `--max-legs 3`, which is the only way to get
   the young population, a non-zero `same_game` cell, and any
   `KXMVESPORTSMULTIGAMEEXTENDED` rows — this run had zero of all three.
