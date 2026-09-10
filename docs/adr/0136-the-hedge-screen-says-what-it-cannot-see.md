# ADR 0136 — The hedge screen says what it cannot see

- **Status:** Accepted, 2026-09-10
- **Date:** 2026-09-10
- **Extends:** ADR 0078 (the desk watches what Joe holds), ADR 0125 (a
  combination bought through the desk is watched for its own exit). Touches
  no other lane's files: `backend/odds/`, `backend/scheduler.py`,
  `backend/parlays.py`, the schema, `backend/notify/*` and
  `backend/hedge_watch.py` are untouched.

## Context — read off live, 2026-09-10 ~03:35Z

The newest ok-and-mirrored `positions` poll held **one** open venue
position: a `KXMVE` combination, 17.74 contracts, $9.69 of exposure. It was
**not** in `parlay_positions` — bought in the Kalshi app, not through the
desk, so ADR 0125's writer (which fires only on a fill through
`POST /api/manual-orders`) never saw it.

Meanwhile the **one** recorded position (id 1, $1.64 → $4.00, three MLB
legs recorded 2026-09-09) is **no longer at the venue** — absent from that
same latest poll — yet still read `open` with all three legs `pending`.

So `/hedge`, the only exit an enter-only combination has (ADR 0078), was
watching **0 of 1** live positions and showing a dead one as though it were
current. Nobody was told either fact. The sharp-bettor's ruling that framed
this lane: an alerting system built on top of an incomplete record teaches
that silence means safety, and the coverage facts have to come first, before
any threshold or alert is layered on top of them.

**Follow-up read, 2026-10-09.** `venue_settlements` already carried position
1's combo ticker (`KXMVECROSSCATEGORY-SHARD1-S2026FAD1B866580-EE12A337E52`)
with `market_result = 'no'`, `settled_ms = 1789004425534` (2026-10-09
~01:40Z) — while all three leg markets still had `kalshi_markets.result`
NULL. The venue settles a combination on its **own** clock, ahead of its leg
markets individually resolving, so `resolve_from_venue` (which reads only
`kalshi_markets.result`) cannot see this, and neither can "the combo is
absent from the positions poll" — a settled position and a closed-some-other
-way position both simply stop appearing there. The combo's own settlement
row is the one fact that tells the two apart, and it is now read.

## Decision — three facts, no threshold, no ordering, no recommendation

This lane ships **facts only**. ADR 0071 governs: a per-row fact is
transparency, an ordering is a claim, and nothing here computes a
consensus-vs-Kalshi gap or ranks anything by one.

### 1. `unrecorded_at_venue` — what the venue holds that this record does not

`backend.hedge.unrecorded_at_venue(conn)`: every `KXMVE` ticker in the
**latest complete** positions poll (see below) that is not an open
`parlay_positions.combo_ticker`. Each row is `{ticker, contracts,
exposure_display, last_seen_ms}`.

**Combinations only.** A single Kalshi market is not a parlay and this
screen watches parlays — a bare single held outside the desk has no other
leg to reshape, so it has no hedge story. Widening the filter to every venue
ticker would answer a different question than the one this screen exists to
answer.

Carried on `build_payload`'s dict alongside `venue_poll_ms` (that poll's
`polled_ms`, or `null` when there has never been a complete poll). When
`venue_poll_ms` is `null`, the list is `[]` too — but that `[]` means
**unknown**, never "confirmed nothing is unrecorded." The frontend banner
only renders when the list is non-empty, so the unknown case renders
nothing rather than a false all-clear; that asymmetry is accepted because a
banner claiming certainty it does not have would be worse than one that says
nothing when there is genuinely nothing to check against yet.

### 2. `at_venue` — is this record's own ticket still there

Per serialised position: `true` when the `combo_ticker` is in the latest
complete poll, `false` when it is a recorded combo absent from it, and
`null` when there is nothing to check — no `combo_ticker` at all (a
sportsbook slip cannot be "at the venue" in the first place) or no complete
poll has ever happened. `null` is a real, distinct answer and is never
collapsed into `false`: "unknown" and "confirmed gone" must not read the
same on a screen whose whole job is showing what is actually true.

### 3. `venue_settlement` — what the venue itself said happened

Per serialised position: `{market_result, settled_ms}` from the newest
`venue_settlements` row for the position's own `combo_ticker`, or `null`
when unsettled (or not a combination). `market_result` is passed through
**verbatim** — 'yes' and 'no' are what has been observed, and nothing here
assumes those are the only spellings the venue will ever use.

This is the definitive dead-ticket fact, and it takes precedence over fact
2 on the screen: a settled combo's line reads "Settled at the venue: won/lost
on `<date>`" rather than "no longer at the venue." Absence-from-poll is a
weaker signal (a position also stops appearing there when it closes some
other, unobserved way); the venue's own settlement record is not.

## Why the latest COMPLETE poll, not "the newest row seen per ticker"

`venue_positions` is append-only and per-poll: a still-open position is
rewritten every cycle under a fresh `poll_log_id`, and a closed one simply
stops being written under later ones — it is never marked closed in place.
Membership can therefore only be asked of **one** poll, the newest complete
one, never of "the newest row this database has ever seen for this ticker."
The latter is exactly the bug the 2026-09-09 entry-side reconciler
(`_q_combo_position_gaps` in `scripts/inspect_live_db_parlays.py`) has on
its own, undocumented terms — it takes each ticker's own latest row rather
than pinning every ticker to one shared poll, so a ticker last seen three
polls ago (since closed) would still read as currently open. Both
`venue_position_tickers` and `unrecorded_at_venue` filter by one pinned
`poll_log_id`, never by a per-ticker `MAX(id)`, and a mutation collapsing
that distinction is asserted red (`tests/test_hedge_positions.py`,
`TestUnrecordedAtVenue::test_a_ticker_seen_only_in_an_earlier_poll_is_not_listed`).

"Complete" means `ok = 1 AND mirrored = 1` — `bets.open_positions`'s own
selector, reused rather than re-derived. `ok = 1` alone is not enough:
`poll_log` has a second writer, `routes.py::_stamp_positions_read`, which
logs a real `row_count` on every hand bet but keeps no rows under it. Taking
"the newest `ok = 1` poll" without the `mirrored` clause would sometimes
select that bare stamp, find zero `venue_positions` rows under it, and read
as "the venue holds nothing" for up to five minutes after every hand bet —
the false negative in the flattering direction this whole lane exists to
refuse.

## Why no auto-close

Neither fact closes `parlay_positions` or resolves a leg. Three reasons,
compounding:

1. **Absence from a poll is not definitive on its own** (see above) — a
   closed-some-other-way state and a genuinely-settled state both look like
   "gone from the latest poll," and only the settlement row (fact 3)
   disambiguates, when it exists.
2. **Even a settlement does not say which leg lost.** A combination's own
   `market_result` is a fact about the *combination market*, not a
   leg-by-leg breakdown. The individual leg markets may finalize later (or
   never, in this repo's read), or Joe may mark them by hand. Auto-marking a
   leg from the combo's result would be inventing a leg-level fact this repo
   does not have — the same discipline `resolve_from_venue`'s own docstring
   states about `kalshi_markets.result`: unreadable resolves to nothing,
   never to a guess.
3. **The close route already exists and is Joe's own tap** (ADR 0078). A
   record changing when the operator did not touch it is the exact failure
   this lane was commissioned to prevent — a screen that acts on his behalf
   is not "recording," it is a second, undisclosed opinion about what
   happened to his money.

So every leg stays `pending` until the venue finalizes the leg market
(`resolve_from_venue`) or Joe marks it by hand (`resolve_leg`), even on a
position whose own combo has already settled. The screen says so in words
("Settled at the venue: lost on 9 Oct 2026") and nothing else moves.

## Consequences

- `backend/hedge.py` gains `_latest_ok_positions_poll`,
  `venue_position_tickers`, `unrecorded_at_venue`, and `combo_settlements`,
  plus `at_venue` and `venue_settlement` on every serialised position, plus
  `unrecorded_at_venue`, `venue_poll_ms` and `max_quote_age_ms` on
  `build_payload`'s top-level dict. No schema change: every table read here
  (`poll_log`, `venue_positions`, `venue_settlements`, `parlay_positions`)
  already existed.
- `gate.py` reads none of it — confirmed by the existing
  `TestTheInterlockCannotSeeThisRecord::test_gate_reads_neither_new_table`,
  which asserts over `gate.py`'s source and needed no change because this
  lane added no new table.
- Frontend: `HedgePositions.tsx` renders the venue-coverage banner (record
  order, one colour, no red) when `unrecorded_at_venue` is non-empty; a
  per-position line for `at_venue === false` or a present `venue_settlement`
  (the latter taking precedence); and a per-leg quote age
  (`describeQuoteAge`, second-precision, distinct from
  `lib/openPositionsStamps.ts`'s minute-precision `describeAge` because
  `MAX_KALSHI_QUOTE_AGE_S` is 30 seconds and a minute-grained clock would
  read "just now" on a quote already half stale), dimming the price past
  `max_quote_age_ms`.

## What this does not establish

- **Not a recommendation to hedge, close, or do anything.** ADR 0078
  Decision 2 stands unchanged: this reports what is observable and refuses
  the timing question.
- **Not that `unrecorded_at_venue`'s absence means full coverage.** It is
  only as good as the latest complete poll; a position bought and closed
  entirely between two polls would never appear in either the poll or this
  list.
- **Not that a `false` `at_venue` means the position is definitively closed
  rather than settled, transferred, or observed incorrectly by the poller.**
  Fact 3 (`venue_settlement`) is the stronger claim where it exists; fact 2
  alone is not.
- **Not that leg-level settlement will ever arrive automatically for a
  combination whose legs never individually resolve.** That gap — whether a
  minted `KXMVE` ticker's legs settle on their own clock at all — is still
  open, exactly as ADR 0125 left it.
