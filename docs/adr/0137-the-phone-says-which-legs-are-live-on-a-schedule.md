# ADR 0137 — The phone says which legs are live, on a schedule — not only when one is losing

- **Status:** Accepted, 2026-09-10 (amends ADR 0078 D2 on Joe's word)
- **Date:** 2026-09-10
- **Amends:** ADR 0078 ("The desk watches what Joe holds, and a hedge alert
  says only what it measured") Decision 2. Nothing else in ADR 0078 changes:
  Decisions 1, 3–9 stand as written, and this document does not restate them.

## The failure it answers

On 2026-09-09 three of Joe's four open parlays had a leg collapse mid-game,
and the desk said nothing. `/hedge` had the correct figures the whole time —
`hedge_watch.watch_once` re-reads every watched leg's book every 60 seconds
while a game is running — but ADR 0078 D2 only pushes a **LOCK**: a state that
exists only once every other leg has already won. A ticket losing its second
leg of six is not a lock, it is a de-risk, and D2 put de-risk states on the
screen only. Nobody was looking at the screen at the moment it mattered, which
is the exact failure the phone push exists to prevent.

**A straightforward fix — push when a leg goes bad — was considered and
rejected.** It was put to Joe alongside the option this document builds, and a
third option was also on the table before either: hold off on any new alert
and instead spend the lane on the coverage gap underneath it — the record is
only as complete as what Joe has typed into `/hedge`, and a threshold alert
built on top of an incomplete record would buzz confidently about the tickets
it *has* while staying silent about the ones it does not, which is a worse
failure mode than the one being fixed. That coverage work is a separate,
already-running lane (Lane A, extending what `Alerter` can send around
`parlay_cards`) and is not re-litigated here; this document is only the
alerting decision on top of whatever the record already holds.

Of the two alerting shapes actually compared, the threshold shape lost for a
reason independent of coverage: see the next section.

## The symmetric-by-construction argument

The sharp-bettor's argument, put to Joe and accepted verbatim: **an alert that
fires only on bad news is a nudge no matter how the words are chosen.** Wording
it carefully — "here is what's happening" instead of "hedge now" — does not
change what the *arrival* of the message means. If the phone only ever buzzes
when a leg is losing, then a buzz is evidence a leg is losing before Joe has
read a single word of it, and every future design decision about the copy is
downstream of a fact the schedule already leaked.

**An alert on a fixed schedule regardless of direction is a fact by
construction, because its arrival carries no information.** A push that fires
once a day, every day a game is running, whether the legs are cruising at 91c
or cratering at 9c, teaches Joe nothing by showing up. Only the *content* can
tell him anything, which is exactly the property D2 was protecting when it
reserved LOCK for figures the tool can stand behind — this amendment extends
the same discipline to a second message shape rather than abandoning it.

Joe's own ruling, on the record 2026-09-10: **a symmetric "legs in play"
statement, once per ticket per day, when a watched game is in play — the same
message on a good day and a bad day.**

## Why D2's reason survives untouched

D2 reserved the phone for LOCK and kept DE-RISK on the screen with one
sentence: *"the phone would be buzzing for a number the tool cannot stand
behind."* Hedging one of several live legs locks nothing — it reshapes a
distribution — and there is no single dollar figure to put in a push about
that.

This amendment does not relax that sentence; it satisfies it a different way.
The new push carries **no locked dollar figure**. It carries:

- **Per-leg venue BIDS**, read straight off the book the same cycle
  `hedge_watch.watch_once` already re-prices for the LOCK check — the exact
  number the market is offering, not a probability the tool computed.
- **A count** — how many of the ticket's legs are still pending versus how
  many have settled — which is arithmetic over what `hedge.assess` already
  wrote to `pending_legs`, not a new measurement.

Both are facts the check actually read, which is ADR 0072 Decision 1's rule
one layer further out: *alert text may contain only nouns traceable to a field
the check actually read.* Nothing here is a forecast, and nothing claims a
leg's price will get worse — or better — for waiting.

## What the message carries and what it refuses

**Carries:**

- One field per leg, in record order: the venue's live BID and how old the
  quote is, for a pending leg; the settlement word (won / lost / void) for a
  settled one.
- A description naming the stake, the return, how many of the ticket's legs
  are still live out of the total, and how long ago the read was taken.
- Exactly one dollar figure, and only when it applies: with precisely one leg
  live and that leg's hedge priced as a reachable, guaranteed lock, the same
  `guaranteed_display` figure `hedge_lock` already stands behind — carried
  here, never recomputed.
- The same two footer caveats every hedge surface carries verbatim
  (`hedge.NOTES["not_advice"]`, `hedge.NOTES["upper_bound"]`), unchanged from
  ADR 0078.

**Refuses:**

- Any figure when more than one leg is live. The field that speaks to that
  state ("No figure locks") says what buying one side of one leg *does* —
  reshapes, never locks — and stops there.
- A fixed list of words, enforced by a test that renders the embed and checks
  their absence, case-insensitive: `now`, `consider`, `warning`, `alert`, `at
  risk`, `trouble`, `still available`, `hedge now`, `collapsing` — always; and
  `guaranteed`, `locked`, `lock` — specifically while more than one leg is
  live, so a screen cannot render "not guaranteed" beside a number as though
  one were coming (the same ruling `hedge._hedge_payload` already makes for
  the de-risk block's missing `guaranteed` key).
- **A "moved from" figure.** Nothing in this repo stores what a leg was worth
  earlier in the day, so there is no "was 60c, now 20c" comparative to report,
  and none is invented. The absence is deliberate, not an oversight: adding
  one would mean storing a second price per leg with its own freshness
  question, for a feature whose entire justification is that its arrival
  carries no information — a delta figure would smuggle that information back
  in through the numbers even if the schedule stayed fixed.

The template is byte-identical in shape whether the legs are at 91c or 9c: the
same field titles, the same sentence structure, only the numbers inside differ.
Pinned by a test that renders both and diffs the field titles and the
number-stripped sentences.

## The ceiling

`POSITION_STATE_KIND = "position_state"`, its own `notifications.kind`,
**separate from `hedge_lock` in both its dedupe bucket and its daily
ceiling** (`MAX_POSITION_STATE_PUSHES_PER_DAY = 4`, independent of
`MAX_HEDGE_PUSHES_PER_DAY`). Sharing either with the LOCK push would let a
busy day for one silence the other, and the two answer different questions —
one bounds how often a number the tool stands behind repeats, the other bounds
how often a fact with no figure repeats.

The dedupe key is **not a ratchet**, unlike `hedge_key`. `hedge_key` floors a
moving figure into a step because the same lock is worth announcing again once
it has materially improved; this push states no figure that moves, so there is
nothing to floor. The key is `position_state:<position id>:<day_start_ms>` —
one per ticket per budget day, full stop, regardless of how many times
`hedge_watch.watch_once` cycles through that day. That is also what keeps the
push symmetric: nothing about the key depends on whether the news is good or
bad.

`pending_legs >= 1` stands in for both "the position is open" and "the game is
in play," because the payload carries neither flag explicitly.
`screen["positions"]` is built from `hedge.open_positions`, so every position
this function ever sees is already open by construction; and
`Alerter.position_states` is only ever called from `hedge_watch.watch_once`,
which `watch_hedges_forever` only enters when `anything_in_progress` was
already true. "In play" is a fact the watcher established before this
function runs — the caller supplies it, and `position_state_key` does not
pretend to re-derive a stronger fact from a timestamp it does not have.

## Consequences

- No schema change. `notifications` already carries free-text `kind`.
- `hedge_watch.watch_once` now calls two alert methods per cycle instead of
  one and merges their `AlertResult`s into the returned summary under
  `position_*`-prefixed keys, so a caller can tell the two pushes apart. The
  "nothing metered" guarantee is unaffected — both methods spend a `Alerter`
  call and a Discord post, nothing that touches `api_credits` or an LLM.
- `backend/gate.py` still reads neither `parlay_positions` nor
  `parlay_position_legs` (ADR 0063). This amendment adds a notification path,
  not a data path, and moves the live-trading interlock's counters not at all.

## What this does not establish

- That a symmetric push is read any more reliably than a threshold one would
  have been. Nothing here measures attention; it only removes the one
  objection that was measurable in advance — that an alert's mere arrival
  would encode a direction.
- That the record it reads from is complete. This amendment inherits ADR
  0078's own limit verbatim: it watches what Joe typed in, and a ticket he did
  not record stays invisible no matter how the phone alerts on what it can
  see. Closing that gap is the sibling lane's job, not this one's.
- That once a day is the right cadence. Four was chosen to match
  `MAX_HEDGE_PUSHES_PER_DAY`'s existing shape, not measured against how often
  Joe actually opens the ticket that arrives.
