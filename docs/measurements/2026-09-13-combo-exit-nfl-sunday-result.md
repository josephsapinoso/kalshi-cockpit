# Combo exit on an NFL Sunday — result: NOT RUN, five of five slots missing

Written 2026-09-14, within the 48 hours §10 of the registration allows, at the
path §10 fixed in advance. Registration:
`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md`
(Amendments 1 and 2). Disclosure that preceded it:
`docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`.

**Verdict: VOID.** No capture was taken. The registration's §7 rule applies to
every slot — *a slot missed by more than 30 minutes is recorded missing, not
moved* — and collection ended at 01:15Z on 2026-09-14. No look is taken today
and none is taken later on this registration; *"the pool was thin, so we took
another look later"* is the move §7 prohibits by name, and a pool that was
never sampled is the limiting case of thin.

## 1. The five slots

| slot | scheduled (UTC) | captured | JSON artifact | stdout log |
|---|---|---|---|---|
| C1 | 2026-09-13 15:30Z | **MISSING** | none | none |
| C2 | 2026-09-13 17:30Z | **MISSING** | none | none |
| C3 | 2026-09-13 20:00Z | **MISSING** | none | none |
| C4 | 2026-09-13 23:30Z | **MISSING** | none | none |
| C5 | 2026-09-14 00:45Z | **MISSING** | none | none |

    captures taken            0 of 5
    Kalshi calls made         0
    Odds API credits spent    0
    rows written anywhere     0

`ls docs/measurements/ | grep 2026-09-13` returned nothing before this file
existed. There are no JSON artifacts and no logs to commit beside it.

## 2. Why — the cause is a missing person, not a thin pool

Each capture was a command to be run from a laptop shell at a fixed minute
(§7). Nothing in this repository runs a command at a minute: there is no
scheduler, no cron on the live box that reaches `scripts/`, and a timer set
inside a session dies with the session. A session exists only while Joe is
talking to one. No session was open on 2026-09-13.

`tasks/NEXT.md` carried the line *"SUNDAY 2026-09-13 — Arm D, a scheduled run,
not a task to plan"* through three consecutive session entries (tenth, eleventh
and twelfth of 2026-09-11) and the thirteenth repeated it. The word
*scheduled* named a mechanism that did not exist, and because it read as a
decision already made, no session asked who would be at the keyboard at 15:30Z.
That is the defect, and it is recorded as a lesson in `tasks/lessons.md`
(2026-09-14) and as a decision in ADR 0146.

## 3. What the miss cost, stated plainly

Joe's answer (B) of 2026-09-11 — *nothing money-touching this weekend* — was
given on this session's framing that Arm D would run and that every combo
lookup would mint a market into its sampling frame. He took no combo taps from
Friday to Monday to keep that frame clean. **The frame was never sampled, so the
abstention bought nothing.** That constraint is lifted as of this document; it
protected a window that has closed.

## 4. What the miss did not cost — the question was already answered

The registration's universal claim (§1: no open `KXMVE` combination book
carries a resting YES bid) was **falsified on 2026-09-10** by the disclosed,
unregistered look: two `KXMVECROSSCATEGORY-SHARD1` books each carried one
resting YES level of 10.00 contracts. `EXIT_ANY` was met and `EXIT_PRACTICAL`
was met exactly at its registered boundary. The correction the registration
owed *whatever Sunday returned* (§11.8, ruled on in §12.4) shipped before C1:
the buy ticket, the bid route's refusal, `NOTES["unquoted"]` and the `/parlays`
lede all say a way out exists, name the size, and claim no frequency
(`backend/parlays.py:278-283`, `backend/api/routes.py:3260-3267`).

Sunday would have bought a **rate** — how often, across 40 books at five
points of an NFL day — on a claim already known to be false. The one branch of
the decision rule with a live consequence, `EXIT_AT_CEILING` (a resting YES bid
of at least 250 contracts at one price, which would reopen
`COMBO_MAX_CONTRACTS`), had an observed size of 10 against it. So: a rate was
lost, a finding was not.

## 5. Successor

**None.** ADR 0146 records the kill. A future registration on the same question
must name who runs each capture and how a session exists at that minute, or
use a stopping rule a session can satisfy whenever it next runs (*n* captures
at least *X* minutes apart, first session on or after date *D*). It must also
give any constraint imposed on Joe an expiry equal to the window's end, and
report to him the moment the window closes, pass or fail.

## 6. What this document does not establish

- Anything about combination exit frequency on an NFL Sunday. Zero rows.
- Anything about whether the 2026-09-10 sizes (10 contracts) are typical. That
  look was two books on one shard on a weekday, disclosed as unregistered.
- Anything about Arms B and C (§2). Their instrument change did not land
  before 2026-09-13 00:00Z, so by the registration's own words they did not
  run and this document does not amend that.
- Anything about `/hedge`, which reads the legs and not the combination book
  (§9).
