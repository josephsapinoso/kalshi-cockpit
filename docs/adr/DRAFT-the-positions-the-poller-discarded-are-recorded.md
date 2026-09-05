# The positions the poller discarded are recorded, and "staked" is exposure at cost

**Status:** Draft. No ordinal; the integrator takes one at merge, after
`git fetch` (`docs/adr/README.md`). Lane A1, 2026-09-05, the partner's
rank-1 item, step 1 of 2 — step 2 (lane A2) is the screen.
**Date:** 2026-09-05.
**Decides:** that `/portfolio/positions` rows are mirrored rather than counted
and discarded (schema v33, `venue_positions`); which number the open-positions
strip serves as "staked" and why; how the venue's representation is stored;
that a `poll_log` positions row carries a `mirrored` mark saying whether its
rows were kept, because `poll_log` has a second, live writer that keeps none
(§5); that the unit of `market_exposure_dollars` is inferred and not measured,
and what stands in for the measurement (§4, §8); that `gate.py` may never read
the table; and that a capture run may never overwrite the one before it. It
closes the third of ADR 0101 §2.3's three reasons, and only that one.
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

`venue_positions`, schema v33. **The version is a column step, not a tableless
one, and the first draft of this section said the opposite.** The table needs
no step — the live volume gains it on its next boot through `CREATE TABLE IF
NOT EXISTS` — but the review found that the reader also needs a marker on
`poll_log` (§5), and `poll_log` holds rows on the live volume that the schema
file alone would never reach. So `_MIGRATIONS[33]` adds `poll_log.mirrored
INTEGER CHECK (mirrored IS NULL OR mirrored = 1)`: nullable, no default, no
backfill, metadata-only. NULL is the honest value for every existing row —
none of them kept its rows. No existing row is otherwise touched.

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
- **The unit of `market_exposure_dollars` is inferred from its suffix, and
  the first draft of this ADR did not say so.** The review found it. "Dollars"
  rests on the `_dollars` suffix, whose meaning was pinned on a *different*
  field — `balance_dollars` "20.6583" observed beside `balance` 2065 on
  2026-08-18 (`parse_balance_tenths`) — and on the fills' `*_price_dollars`.
  This field's magnitude has never been read against a known position: ADR
  0083's write-up of the 2026-08-30 capture records the envelope,
  `position_fp` and the `count_filter` result and says nothing about it; the
  committed fixture carries synthetic values; the 2026-09-05 capture returned
  no rows. The repo's own precedent one function above the parser is to
  *refuse* an unpinned unit — `parse_portfolio_value_tenths` stores
  `portfolio_value` only at zero, because "guessing cents by analogy with
  `balance` is exactly the convenient-column error, one field over." This
  column makes the analogy that function refuses. The difference is stated in
  the schema comment, in the parser and here rather than hidden, and what
  stands in for the measurement is a **tripwire the design lacked: a contract
  cannot cost more than $1, so `exposure_tenths` may not exceed
  `abs(position_fp)` in dollars on the same grid.** The ceiling goes through
  the same `dollars_to_tenths` as the exposure, so the two roundings are one
  rounding and the bound is monotone — a true $1 a contract lands equal,
  never above. On the observed row that is 7642 against 22880; a
  cents-with-decimals field gives 764192 against 22880 and the parser leaves
  the column NULL with `exposure_refusal` naming the scale error, so the
  first real row refuses loudly instead of rendering the stake at 100×. The
  tripwire catches a scale error. It cannot tell cost from a payout at
  exactly $1 a contract, and it does not make the unit measured (§8).
- **A negative exposure is refused, not absoluted.** Whether the venue signs
  a NO-side exposure has never been observed; `abs()` would be a guess
  wearing a number. The column is NULL and the verbatim text keeps the sign
  for the day it is pinned.
- **One stamp.** Every row carries `poll_log_id`, the id of the very
  `poll_log` row whose `row_count` is the count, plus that poll's
  `polled_ms`. A FK with `PRAGMA foreign_keys = ON` makes the reference bind.
- **Snapshot semantics.** Every successful poll writes its full row set and
  then marks its `poll_log` row `mirrored = 1`, in one transaction
  (`portfolio_poll.store_positions_snapshot`, the seam the poller calls and
  the hand-bet route is meant to call — §5). A failed poll writes nothing to
  the mirror (its `poll_log` row is the record of the failure) and the
  previous snapshot stays the newest. A reader takes the newest successful
  *marked* poll and reads only the rows carrying its id. An empty snapshot
  is marked with zero rows under it; an unmarked stamp is zero rows and
  nothing kept; no count separates those two states, only the mark.
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

`bets.open_positions` serves `count` from `poll_log.row_count` of the newest
successful poll **that kept its rows** (`mirrored = 1`), and
`staked_tenths`/`staked_display` as the sum of `exposure_tenths` over the rows
keyed by that poll's id — **one read, one stamp, `count_as_of_ms`**. There is
deliberately no `staked_as_of_ms`; a second stamp for the same read would
invite the divergence `tests/test_open_positions_stamp.py` exists to forbid.
The payload keys are unchanged, so the frontend contract holds; the component
already renders `staked_display` whenever the server sends a string.

**Why "that kept its rows", and what the first draft got wrong.** The first
draft selected the newest successful positions poll of any kind, and said the
mismatch case "has one live occurrence and it is short: in the minutes after
v33 deploys". That was false, and the review found it. `poll_log` has a
**second writer of positions rows, and it is live**:
`backend/api/routes.py::_stamp_positions_read` (defined at line 6138, called
at 5633 with `row_count=len(position_rows)`) records the hand-bet path's own
`live_quotes().portfolio_positions()` read — check 10 of `POST
/api/manual-orders` — through the same `log_poll_attempt` the poller uses,
under the same endpoint name, by design (its docstring: *"so
`bets.open_positions` and the registration's gap tripwires read one
population and not two"*), and writes **no mirror rows**. That path is the
armed hand-bet route, used 27 times in the ten days before this ADR. Under
the first draft's reader, its row became the newest successful poll for up to
five minutes after every hand bet, `row_count` was the real count and the
mirror held zero rows under that id, and the figure refused with
`STAKED_MIRROR_MISMATCH` — "Open now: 2" beside a refusal sentence, the exact
pre-v33 state this lane set out to remove, at the one moment ADR 0105 says the
desk is open. It was silent whenever Joe held nothing (0 = 0), so it fired
only in the state the figure exists for. No test covered the interaction.

Two fixes were available. The complete one lives in `routes.py`: the route
already holds `position_rows`, so `_stamp_positions_read` should keep them
through `store_positions_snapshot` under the id `log_poll_attempt` now
returns — one population, one read, one stamp, and the route's read would then
also feed the money figure. **That edit was deferred to the integrator**
because `routes.py` is lane B's file this session; §9 names the lines. What
this lane could do, it did: the reader selects on the mark, so the bare stamp
is simply not selected. Nothing is lost by that. The route takes its read
*before* the order is sent, so its count is the poller's last count anyway,
and the poller's next poll lands inside five minutes. The alternative —
serving the stamp's count and refusing the money — is the defect. Serving the
stamp's count beside the poller's money would be two reads on one line, which
is the divergence the one-stamp rule forbids. So the count and the money wear
one stamp or none, and `tests/test_venue_positions.py::
TestTheMarkerSaysWhichReadKeptItsRows` reproduces the route's write through
the same `log_poll_attempt` it calls and pins the figure served.

The unconditional refusal is deleted and its absence pinned by name. Five
refusals replace it, each a genuinely unreadable state and none of them "the
number is zero":

| state | words |
|---|---|
| no successful positions poll, ever | `STAKED_NEVER_POLLED` |
| a successful poll, but none that kept its rows — every row is from before v33, or is the hand-bet path's stamp | `STAKED_NOT_MIRRORED`, no clock: neither figure is served off a bare row, and the words do not say the venue was never asked when it was |
| newest marked poll older than 30 minutes | `STAKED_NOT_READ`, with `count_as_of_ms` kept so the screen says "since"; a fresh bare stamp does not rescue a dead poller's snapshot |
| mirror rows ≠ `row_count` for that marked poll | `STAKED_MIRROR_MISMATCH`, naming both numbers — an integrity refusal now (a hand-edited table, or a writer that set the mark without the rows), no longer how the second writer shows up |
| any row's `exposure_tenths` NULL | `STAKED_ROW_UNREADABLE` — a partial sum is a false low, so the whole figure refuses; the scale tripwire of §4 lands here |

**An empty-but-fresh snapshot is count 0 and $0.00.** That is not the false
negative `OpenPositions.tsx` guards against. The guard is about `$0.00` beside
a **non-zero** count — a money figure invented while the count says there is
money. Here both numbers come from one successful read of one endpoint
seconds ago: the venue said it holds nothing, and the count says the same in
the same breath. The 2026-09-05 capture found the live account in exactly
this state.

What the minutes after v33 deploys look like now: every `poll_log` positions
row is unmarked, so the strip says `STAKED_NOT_MIRRORED` with no count and no
clock until the poller's first cycle — seconds, since
`poll_portfolio_forever`'s first cycle is a full mirror — and then serves both
figures off that snapshot. The sentence this paragraph replaces described the
count being served off the unmarked row with the money refusing beside it; that
is the shape of the defect above, and it is gone in both cases for the same
reason.

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

- **The unit of `market_exposure_dollars`.** Inferred from the `_dollars`
  suffix, which was measured on `balance_dollars` (2026-08-18) and never on
  this field. The §4 tripwire bounds a scale error at 100×; it does not
  measure anything, and it cannot tell cost from a payout at exactly $1 a
  contract. The first non-empty snapshot against a known position is the
  measurement, and until it is taken the "staked" figure rests on an
  analogy the function above the parser refuses to make for
  `portfolio_value`.
- **Whether `market_exposure_dollars` includes fees.** `fees_paid_dollars`
  sits beside it on the wire, which suggests exclusion; nothing here tests
  the relation. "Before fees" in §3 is the label, not a measurement.
- **That the hand-bet route keeps its rows.** It does not, as of this ADR
  (§5). The reader is immune to its bare stamp; the route's own read still
  does not feed the money figure, and its docstring's "one population and not
  two" is half-true until the integrator's edit in §9 lands.
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

- **The integrator's edit to `routes.py`, deferred from this lane.** In
  `_stamp_positions_read` (line 6138): take the rows as an argument, and in
  `_write` (line 6173), after `log_poll_attempt(...)` at line 6176 returns
  its id and when `ok` is true, call
  `store_positions_snapshot(conn, poll_log_id=<that id>, now_ms=now_ms,
  rows=<the rows>)` before `conn.commit()`; at the call site (line 5633) pass
  `position_rows`. The failure branch (line 5619) stays as it is — a failed
  read keeps nothing and is not marked. Then the route's read feeds the money
  figure, `TestTheMarkerSaysWhichReadKeptItsRows` still passes (a marked
  stamp with its rows is served, under its own newer clock), and the "one
  population" sentence in the route's docstring becomes wholly true. This is
  the complete fix; the marker is what makes the interval before it safe.
- A NO-side position observed on the live account pins the sign convention
  and decides whether the negative-exposure refusal becomes an `abs()`.
- A known position whose `market_exposure_dollars` can be checked against a
  known count and price pins the unit (§8) and decides whether the tripwire
  stays a tripwire or becomes a measured claim in the schema comment.
- A known position whose `market_exposure_dollars` can be checked against its
  fills settles the fee question in §8, and the "before fees" label either
  stands or is corrected in the schema comment and here.
- Lane A2 renders the figure. Until it does, the strip shows the served
  string through the component's existing `staked_display` branch and its
  header prose still describes the refusal.
