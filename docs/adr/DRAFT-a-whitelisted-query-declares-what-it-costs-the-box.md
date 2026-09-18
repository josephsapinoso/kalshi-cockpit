# ADR DRAFT — A whitelisted query declares what it costs the box

- **Status:** accepted
- **Date:** 2026-09-18
- **Decider:** the session, from the 2026-09-18 (twentieth) lesson in
  `tasks/lessons.md`: a whitelisted query is safe to type, not free to run.
- **Amends** nothing. The whitelist property of `scripts/inspect_live_db.py`
  (a caller chooses a name, never SQL; read-only by the connection) is
  unchanged. This adds a second property beside it.

## The decision

Every entry in `QUERIES` carries a required `cost`, one of two values:
`cheap` (a file tail, a bounded key range, or an unbounded read of a table
whose size is bounded by something other than time) or `walks-the-file`
(`dbstat`; a GROUP BY, DISTINCT or COUNT over the whole of `odds_snapshots`,
`fair_prices`, `kalshi_quotes` or `poll_log`; a window of days through a
non-covering index on one of them; or a scan with no bounded key at all).
The field has no default, so an entry without it does not import. `main`
refuses a `walks-the-file` query with exit 4 and one sentence naming the cost
unless the caller passes `--i-accept-the-cache-flush`; the `--help` listing
prints the class beside every name. The refusal runs before the database is
opened, and the sentence reads the file size with a `stat`, so refusing costs
the cache nothing.

## Why

The live file is 6.3 GB on a 4 GB box with ~3 GB of page cache, and that cache
is the desk's performance. On 2026-09-18 `db-sizes` — which walks `dbstat`
over every page — was run in the middle of a latency diagnosis, because the
cost was in the description and nothing at the point of invocation said it.
Every timing taken afterwards was worse by an amount not measured. A per-query
note is the thing that was already there and was not read; a class property
is checked on every invocation and cannot be skipped by a new entry.

## What it does not do

The flag does not make a query cheaper, and the class is a reading of the SQL,
not a measurement: 18 of 45 are classified as walks, several on the
"when unsure, say so" side (the `poll_log` and `venue_positions` walks were
small when their queries shipped). Reclassifying one downward needs a timing
on the box, taken with the flag, recorded beside the entry.
