# Lane 107 — no non-empty combination YES book captured (2026-09-19)

Ticket: #107 (capture a real, non-empty combination YES orderbook as a
committed fixture). **Result: every book read this run is empty on the YES
side. No fixture was written.** Per the ticket's step 5, this is recorded as
a measurement and #107 stays open.

## What was built

`scripts/measure_combo_book_presence.py` gained a repeatable `--ticker`
option (`read_books_by_ticker`, alongside `main()`'s dispatch) that reads
exactly the given tickers' books via `GET /markets/{ticker}/orderbook`,
bypassing `/markets` discovery entirely. It reuses `PublicReader` and the
existing `read_book` helper unchanged, so the `ORDERBOOK_KEY` /
`MalformedOrderbookResponse` envelope guard applies identically. A failed
read (settled market, malformed envelope, HTTP error) is logged and
omitted, never faked as empty — same rule `collect()` already follows.

## Step 1 — finding the two known tickers

Grepped `docs/measurements/2026-09-1*` for the suffixes named in the ticket
(`890CDE617E4`, `24,900`/`38,709`). Both come from
`docs/measurements/2026-09-17-combinations-can-be-exited.md`, which records
only the last-11-character **tail** of each ticker in its table (`5A52E505C20`,
`890CDE617E4`, `D9825147886`), not the full ticker. Searched every
`docs/measurements/*`, `tests/`, `backend/`, and `git log -p --all` for a
full ticker containing either suffix:

- `D9825147886` — full ticker **found**, in
  `docs/measurements/2026-09-17-accepted-side-names-the-makers-side.md:24`:
  `KXMVECROSSCATEGORY-SHARD1-S20264D4910BB8C7-D9825147886`.
- `890CDE617E4` — **not found anywhere in the repo or its history.** Only
  the tail is recorded. This ticket's step 1 anticipated this case ("If only
  suffixes exist, say so in the report and use step 3") — recorded here and
  fell through to discovery.

## Step 3 — reads taken (all public, unauthenticated; ~39 GETs total, within the ~45 budget)

1. `--ticker KXMVECROSSCATEGORY-SHARD1-S20264D4910BB8C7-D9825147886 --depth 20`
   → book read successfully (1 call), **yes=0 levels, no=0 levels**. The
   24,900-deep YES bid recorded 2026-09-17 is gone two days later — consistent
   with ADR 0164 (a combo's book is empty by design between RFQs; a resting
   bid there was the trace of a recent print, not a standing quote).
2. Discovery over the default series (`KXMVESPORTSMULTIGAMEEXTENDED`,
   `KXMVECROSSCATEGORY`), three separate runs at `--max-books` 40, 40, 12
   (~7, 18, 10 calls): 3 + 14 + 6 = 23 eligible combinations read. **Every
   one had an empty YES side.** A handful had a non-empty NO side (which is
   what backs a list `yes_ask` via the derived-ask identity) — none had a
   resting YES bid.
3. `--series KXMVECROSSCATEGORY-SHARD1 --max-books 40`: 0 eligible rows (the
   shard-1 series' open markets did not carry a readable list quote at read
   time) — 1 call.
4. `--series KXMVENFLSINGLEGAME --series KXMVENFLMULTIGAMEEXTENDED
   --max-books 10`: **both series returned no open rows** (`EmptySeriesRequested`,
   2 calls) — neither NFL combo series has anything live right now.

Net: 1 targeted read + ~29 discovered combos + 2 empty-series checks, all
public GETs, no odds credits, no live-order-path or RFQ call. Total ≈ 39
GETs.

## Reading this

Random discovery landing on a non-empty YES book is structurally unlikely
under ADR 0164 — a combination's book is empty by design between RFQs, and a
resting bid is the residue of a recent print, not a standing quote. The two
2026-09-17 sightings came from Joe's own held positions at a moment shortly
after real activity on them, not from a representative sample. **A third
empty capture (in fact several) is itself a fact, and does not overturn
ADR 0164 or the 40-of-40 finding it already amended** — it is consistent
with both.

## What would actually get a non-empty capture

- Read Joe's **current** open combination positions (`GET
  /portfolio/positions`, needs the account read — outside this ticket's
  "public, unauthenticated" scope) and try `--ticker` against whichever
  ones are live *right now*, ideally minutes after he places or the venue
  prints a trade on one.
- Or watch a specific ticker across a short polling window right after
  firing a real (or dry-run-adjacent) RFQ that trades, since a trade is what
  prints to the public book.

Neither is this ticket's scope (public read only, no RFQ/account calls), so
#107 stays open pending one of those.
