# lane-328 handoff

- No served fee coefficient exists on any payload. The cost line derives k from
  a served RFQ quote (fee / contract cost / (1 - P)). The card's book-ask tile
  (`PriceOnKalshi.tsx`, not in lane) and CheckAParlay's book ask therefore show
  only "n legs. Wins about 1 in N." Showing the fee and singles clauses there
  needs a served `fee_coefficient` on the lookup/check payloads
  (backend/api/routers/parlays.py, forbidden to this lane), or a one-line
  `<ParlayCostLine>` in `PriceOnKalshi.tsx` beside the book tile.
- `schema`/ADR: none. No SCHEMA_VERSION change.
