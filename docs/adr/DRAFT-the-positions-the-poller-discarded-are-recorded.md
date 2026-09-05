# The positions the poller discarded are recorded, and "staked" is exposure at cost

**Status:** Draft. No ordinal; the integrator takes one at merge, after
`git fetch` (`docs/adr/README.md`). Lane A1, 2026-09-05, the partner's
rank-1 item, step 1 of 2 — step 2 (lane A2) is the screen.
**Date:** 2026-09-05.
**Decides:** that `/portfolio/positions` rows are mirrored rather than counted
and discarded (schema v33, `venue_positions`); which number the open-positions
strip serves as "staked" and why; how the venue's representation is stored;
that `gate.py` may never read the table; and that a capture run may never
overwrite the one before it. It closes the third of ADR 0101 §2.3's three
reasons, and only that one.
**Sources:** ADR 0101 §2.3 (the unconditional refusal and its three reasons);
`tests/test_rest.py::OBSERVED_POSITION_ROW` (the per-row shape, captured on the
production account 2026-08-30 by `scripts/capture_positions_fixture.py`,
committed with synthetic values); the 2026-09-05 ~04:12Z capture (exit 4:
envelope `{cursor, event_positions, market_positions}` confirmed, zero rows on
both calls); ADR 0083 (a refusal is a record, an unobserved payload is not a
position); ADR 0063 §2 and ADR 0078 §4 (the `gate.py` boundary);
`tasks/lessons.md`'s ordering rule, capture before parser.
**Touches nothing decided by** ADR 0015 (the gate's floor), ADR 0038 (the hunt
is closed), ADR 0071 (what the desk is for), ADR 0105 (the desk is read, not
transacted through). Nothing here reads `event_positions`, writes a
`recommendations` row, or moves the runner's `dropped_game_started` drop.

## 1. What was broken

Since 2026-08-29 `portfolio_poll.poll_positions` has called
`rest.positions()` every five minutes — paginated, `count_filter=position`,
rename-loud since 2026-08-30 — received correct rows, written `len(rows)` into
`poll_log.row_count`, and **thrown the rows away**. `grep -c venue_positions
backend/store/schema.sql` was 0. The desk could say "Open now: 3 positions"
and could not say what those three had cost: `bets.open_positions` served
`STAKED_NOW_REFUSAL`, an unconditional sentence, where the money figure
belonged.

ADR 0101 §2.3 gave three reasons for that refusal. The first two are about
`fills` — no buy-against-sell, and "fills with no settlement row" is not
"open" — and they are still true. The third was *"the venue's own
per-position figure is not stored ... `poll_positions` counts rows and parses
none — deliberately, after five parsers in this repo's history were written
against imagined wire formats."* That reason had an expiry date the ADR did
not name: the shape was captured on 2026-08-30, the day before ADR 0101 was
written. Ticket #21 closed with items 1–3 built and this hole open. The
poller's own log line — *"the per-row shape has never been captured"* — was
false for six days before this lane deleted it.

## 2. Why now, and why on an empty account

The blocker was the ordering rule: **capture before parser.** It was
satisfied on 2026-08-30 and nothing acted on it. The partner ranked this
first on 2026-09-05 because the record (ADR 0105 §1) says the desk is a read
surface Joe opens shortly before a Kalshi bet, and the one money figure that
describes what he already has on is the one the screen could not show.

The 2026-09-05 capture found **zero rows** — Joe holds nothing open this
morning. The partner's call was to build the mirror anyway: the table fills
on his next open position, and an empty-but-fresh snapshot is itself a state
the screen must render honestly (§5). The alternative, waiting for a position
to exist before building the thing that records it, is the six-day gap of §1
repeated on purpose.

## 3. Which number "staked" is

**Exposure at cost: the venue's own `market_exposure_dollars`, per row, in
integer tenths of a cent, summed over the rows of one poll.** Money in, before
fees. Not market value.

The partner's reasoning, recorded because the alternative was live:

- **It is what the word means.** Staked is the money put down. Market value
  is what the position would fetch now, which is a different question with a
  different clock.
- **The desk already uses the word that way.** `TonightStrip.tsx:9` renders
  "dollars staked since the day roll" — the sum of what was committed, never
  a mark. Serving a mark-to-market under the same word on the next line would
  be two meanings of one word on one screen.
- **It needs no live quote, so it cannot go stale on its own clock.** The
  figure is fixed at the moment of the fill; only the read of it ages. That is
  why it can share the count's stamp (§5) where a market value could not.
- **`fees_paid_dollars` travels beside it on the wire**, a separate field,
  which is why "before fees" is stated and not inferred.

**The `portfolio_value` unit pin is killed as a dependency.** `value_*` on the
same strip refuses on every non-zero account because
`parse_portfolio_value_tenths` pins its unit only at zero. That figure stays
exactly as it was, with its own stamp and its own refusals; nothing here waits
on it, and nothing here touches it.

## 4. How it is stored

`venue_positions`, schema v33, tableless (`_TABLELESS_VERSIONS` says so): the
live volume gains the table on its next boot through `CREATE TABLE IF NOT
EXISTS`, no `_MIGRATIONS` entry, no existing row touched.

- **Verbatim TEXT.** `position_fp`, `market_exposure_dollars`,
  `total_traded_dollars`, `fees_paid_dollars`, `realized_pnl_dollars` and
  `last_updated_ts` are the wire strings character for character (a
  non-string is stored as its JSON, `None` stays NULL). Five parsers in this
  repo's history were written against imagined formats; the verbatim column
  is what lets the next reader check a derived value against the source
  without another capture.
- **Derived columns with their units in the schema comment, NULL when
  unreadable, never 0.** `exposure_tenths` (integer tenths of a cent) comes
  through `core.prices.dollars_to_tenths` — `Decimal × 1000`, ROUND_HALF_UP
  to a whole tenth. The lane brief's example said round-half-even; the wallet
  already has one dollars-to-tenths spelling, used by the balance and every
  settlement price, and a second rounding rule for one column would be the
  two-spellings defect CLAUDE.md records under the window banner. Fractional
  contracts make sub-tenth exposures real ("7.641920" is 7641.92 tenths);
  the rounding puts that on the grid within ±0.05 tenths, never a whole cent
  off. `contracts` (REAL) is `abs(position_fp)` through `parse_position_fp`
  — Decimal, never `int()`, which misreads "22.88". `side` is the sign.
  Three CHECKs refuse what a reader would sum wrongly: a negative exposure, a
  negative count, a side that is not yes or no.
- **A negative exposure is refused, not absoluted.** Whether the venue signs
  a NO-side exposure has never been observed; `abs()` would be a guess
  wearing a number. The column is NULL and the verbatim text keeps the sign
  for the day it is pinned.
- **One stamp.** Every row carries `poll_log_id`, the id of the very
  `poll_log` row whose `row_count` is the count, plus that poll's
  `polled_ms`. A FK with `PRAGMA foreign_keys = ON` makes the reference bind.
- **Snapshot semantics.** Every successful poll writes its full row set. A
  failed poll writes nothing to the mirror (its `poll_log` row is the record
  of the failure) and the previous snapshot stays the newest. A reader takes
  the newest successful poll and reads only the rows carrying its id.
- **Retention is the writer's own: seven days, deleted in the snapshot's
  transaction.** Not `store/retention.py`, which runs on the runner's slow
  pass — a different loop, observed down while the poller was up — with
  batching sized for tables of millions of rows. This one grows by (positions
  held) × 288 a day. Named in `retention.py`'s exclusion list so it is a
  decision rather than an oversight. The only production reader takes the
  newest poll and refuses past thirty minutes, so any window longer than
  `TONIGHT_STALE_AFTER_MS` serves it; a test pins that inequality off the
  constants.
- **A row that will not parse is never refused whole.** The text is kept,
  the derived column is NULL, a warning names the ticker, and the poll
  summary counts it under `exposure_unreadable`. `poll_log.row_count` is
  written exactly as before.

## 5. How it is read

`bets.open_positions` serves `count` from `poll_log.row_count` as before, and
`staked_tenths`/`staked_display` as the sum of `exposure_tenths` over the rows
keyed by that poll's id — **one read, one stamp, `count_as_of_ms`**. There is
deliberately no `staked_as_of_ms`; a second stamp for the same read would
invite the divergence `tests/test_open_positions_stamp.py` exists to forbid.
The payload keys are unchanged, so the frontend contract holds; the component
already renders `staked_display` whenever the server sends a string.

The unconditional refusal is deleted and its absence pinned by name. Four
refusals replace it, each a genuinely unreadable state and none of them "the
number is zero":

| state | words |
|---|---|
| no successful positions poll, ever | `STAKED_NEVER_POLLED` |
| newest poll older than 30 minutes | `STAKED_NOT_READ`, with `count_as_of_ms` kept so the screen says "since" |
| mirror rows ≠ `row_count` for that poll | `STAKED_MIRROR_MISMATCH`, naming both numbers — a `poll_log` row from before v33, or a second writer |
| any row's `exposure_tenths` NULL | `STAKED_ROW_UNREADABLE` — a partial sum is a false low, so the whole figure refuses |

**An empty-but-fresh snapshot is count 0 and $0.00.** That is not the false
negative `OpenPositions.tsx` guards against. The guard is about `$0.00` beside
a **non-zero** count — a money figure invented while the count says there is
money. Here both numbers come from one successful read of one endpoint
seconds ago: the venue said it holds nothing, and the count says the same in
the same breath. The 2026-09-05 capture found the live account in exactly
this state.

The mismatch case has one live occurrence and it is short: in the minutes
after v33 deploys, the newest `poll_log` row was written by the pre-v33
poller and has no mirror rows under it. The count is served, the money
refuses with "the poll counted N positions and the mirror holds 0 rows for
it", and the next successful poll clears it.

## 6. The boundary

**`gate.py` may never read `venue_positions`.** What Joe holds is his
discretion, not evidence; the live-trading interlock counts neither. It is the
boundary `manual_orders` (ADR 0063 §2), `parlay_positions` (ADR 0078 §4) and
`combo_orders` carry, pinned with the same mechanism — a substring assertion
over the source of `backend/gate.py`, in a `TestTheInterlockCannotSee...`
class — and no second spelling. Mutation: the string written into `gate.py`
turned the pin red.

## 7. The capture filename

`scripts/capture_positions_fixture.py` wrote two fixed names,
`portfolio_positions_bare.json` and `portfolio_positions_count_filter.json`,
and the 2026-09-05 run overwrote the 2026-08-30 capture — the only
observation of the per-row shape this account had produced. The shape
survives only because `OBSERVED_POSITION_ROW` was committed from it. Every
run now writes `portfolio_positions_<kind>_<YYYYMMDDTHHMMSSZ>.json`, one UTC
stamp per run shared by both files. The JSON inside is byte-for-byte what it
was, `data/` stays gitignored wholesale, and a test runs the script twice
against a stubbed venue and checks the first pair's bytes are untouched by
the second.

One sentence in the script was left as it was, on the brief's instruction to
keep the rest byte-identical: `EXIT_MEANING[EXIT_EMPTY]` still says *"the
per-row shape is still unobserved"*. Read on 2026-09-05 that is a sentence
about the run, not the account, and it is stale by six days.

## 8. What this does not establish

- **Whether `market_exposure_dollars` includes fees.** `fees_paid_dollars`
  sits beside it on the wire, which suggests exclusion; nothing here tests
  the relation. "Before fees" in §3 is the label, not a measurement.
- **Anything about `event_positions`.** The envelope's other list is not
  read, not stored, and not described.
- **What the venue's `count_filter=position` does to a row that flips to
  zero mid-session.** Unobserved.
- **The sign convention of a NO-side exposure.** Refused, not guessed (§4).
- **That the screen renders the figure.** That is lane A2. This lane touched
  neither `frontend/` nor `backend/api/routes.py`.
- **That the live table has rows.** Zero on 2026-09-05. The first non-empty
  snapshot is the first real read of this design, and the first place the
  rounding, the sign and the fee question could be checked against a known
  position.
- **Anything about `fills`.** The two reasons in ADR 0101 §2.3 that name it
  are unchanged and still true; they no longer matter because nothing here
  reads `fills` — pinned on the source of `open_positions`.

## 9. What would change it

- A NO-side position observed on the live account pins the sign convention
  and decides whether the negative-exposure refusal becomes an `abs()`.
- A known position whose `market_exposure_dollars` can be checked against its
  fills settles the fee question in §8, and the "before fees" label either
  stands or is corrected in the schema comment and here.
- Lane A2 renders the figure. Until it does, the strip shows the served
  string through the component's existing `staked_display` branch and its
  header prose still describes the refusal.
