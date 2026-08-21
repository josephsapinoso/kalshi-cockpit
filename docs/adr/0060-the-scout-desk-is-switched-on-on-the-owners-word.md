# 0060 — The Scout desk is switched on, on the owner's word

**Date:** 2026-08-21
**Status:** Accepted.
**Supersedes, for `backend/agents/scout.py` only,** the disposition recorded in
[ADR 0040](0040-quarantine-is-the-settled-state-for-scout-and-historian.md).
The Historian's disposition there is untouched.
**Does not reopen** [ADR 0038](0038-the-edge-hunt-is-closed-and-the-record-is-the-product.md)'s
closure of the edge hunt — §5 says why not.
**Owns:** `backend/agents/scout_desk.py`, the `scout_briefings` table, the
`/api/scout/{ticker}` routes, and the desk section of the Market screen.

---

## 1. The decision, and who took it

Joe, 2026-08-21, verbatim:

> I want to build out the desk more. specifically the scout. it would be cool
> if the scout had a staff of his own. he'd be the master scout but would have
> a team report to him. the team would comprise of scout specialists if you
> will each knowing their own home teams player status, team statuses, weather
> if they're playing at home. then the master scout can collect the notes from
> each of his staff, and make more of an expert opion that would finally serve
> me at my desk when i go into the site.

ADR 0022 §4 recorded wiring the Scout as "a decision Joe has not taken",
because wiring it means live Anthropic spend. **This is that decision being
taken**, by the person whose money it spends, for a product he asked for by
shape. ADR 0040's `revive_if` ("a *new* signal clears `signal_test.py` …")
described the only door then imaginable; the owner walking in through the
front is a third way its §7 did not enumerate, and an owner's direct
instruction outranks a parked module's revival prose.

## 2. What was built

One convening of the desk is **three metered calls**:

1. **Two staff scouts, one per club** (`scout_staff_home`, `scout_staff_away`).
   Each covers exactly one team — player status, team status, rest and travel —
   and the **home side's scout also covers the venue and weather**, because
   Joe's design assigns each specialist their own club's home ground. Both use
   server-side web search and file `ScoutReport`s (sourced facts, timestamps,
   a `likely_already_priced` flag; no numeric forecast field exists in the
   schema).
2. **One master scout** (`scout_master`). He receives only his staff's filed
   notes — no web search — and returns a `DeskBriefing`: headline, assessment,
   ranked `what_matters`, `conflicts`, `unanswered`. Every field is prose;
   `tests/test_scout_desk.py` walks the schema and fails on any numeric type.
   His prompt forbids adding facts: a synthesis that introduces new claims is
   a third researcher wearing an editor's title.

A convening is **on demand only** — a button on the Market screen, never a
scheduled pass. The old solo `research()` in `scout.py` was **deleted rather
than wired**: it was unmetered, and an unmetered function beside a metered
desk is the exact back door `tests/test_has_callers.py` exists to shut.
`scout.py` survives as the desk's schema and prompt module.

## 3. The money contract

- Every call is metered by the existing `AgentBudget` against the same
  `agent_calls` day the Skeptic draws from (`AGENT_MAX_CALLS_PER_DAY`,
  default 24 — so at most 8 full briefings a day, shared with the Skeptic,
  whose own spend remains bounded by `surfaced == 0`).
- The staff pair is **all-or-nothing**: affordability is checked before
  anything is written, and the two rows are reserved **before** the first
  request (crash direction: over-count — costs a briefing, never money).
- The master is reserved only after at least one staff note exists.
- `POST /api/scout/{ticker}` requires auth and re-checks the budget before
  accepting, so a tap against an exhausted day answers 429 and spends nothing.
- The browser holds no bearer token; the `/scout-desk` Next route handler adds
  it server-side, exactly as `/refresh-odds` does. **What that widens:** a
  session-cookie holder can now spend from the Anthropic day (bounded
  server-side, not raisable from the client). It does not widen toward the
  order path, which still demands the token itself.
- Cost per briefing, on the [ASSUMED, uncited] rates in `agents/base.py`:
  three calls at the Skeptic's $0.014–$0.084 bounds plus web-search fees —
  roughly **$0.05–$0.30**. No figure here is an invoice.

## 4. Honest states, everywhere

- The POST answers `accepted`, never `briefed`; the desk takes minutes and the
  phone polls the GET.
- A **`running` row past 15 minutes renders as gone quiet** — the process that
  owned it cannot finish it after a restart, and a spinner that cannot end is
  a lie.
- **"Filed nothing" is not "found nothing."** A dead scout reaches the master
  as `FILED NOTHING`, in words, and renders as a dark side of the desk; an
  empty filing renders as "looked, nothing noteworthy", with what was
  searched.
- A ticker with **no linked sportsbook fixture is refused** (422): the desk
  cannot know which clubs to cover, and guessing from a ticker string is how
  the text-matcher failures in the Matching section of `schema.sql` happened.
- The Crew bubble's Scout line remains an admission (it is a code persona with
  no data); it now points at the Market screen instead of claiming to be
  switched off.

## 5. Why this does not reopen ADR 0038

The desk outputs **no probability, no price, no stake, no verdict on any
bet** — the schemas make those unrepresentable, which is the same enforcement
the fleet has always used. Nothing the desk produces enters `fair_probability`,
sizing, the gate, or any registered measurement. It is qualitative context for
**Joe's own hand decisions**, which ADR 0038 explicitly does not reach ("the
closure is a statement about what the tool may claim, and it reaches nothing
Joe does by hand"). No hunting line opens here; no row of the ADR 0038 table
is touched.

## What this does NOT establish

- **That the briefings are any good.** No convening has run against a real
  game as of this ADR. Quality is a question the first real briefings answer.
- **That the desk's facts are current or complete.** Web search recency is the
  staff's whole value proposition and its known weakness; the
  `likely_already_priced` flag is the honesty valve, not a guarantee.
- **That three calls is the right shape.** Per-sport staffs, a conditions
  specialist, or per-club standing scouts are all compatible extensions; each
  is more spend and none is decided here.
- **That the demo can ever send the desk.** It holds no key and no token, by
  design, and both halves refuse independently.
