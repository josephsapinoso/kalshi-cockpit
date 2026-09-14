# 0146 — Arm D is void, and has no successor

Date: 2026-09-14
Status: accepted
Scope: `docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md`
and its Amendments 1–2; the "nothing money-touching before Arm D" constraint of
2026-09-11; `tasks/NEXT.md`'s standing item 2. No code changes.

Numbered on `main` after `git fetch`, behind lane C's 0145.

---

## 1. What happened

The registration fixed five captures at five UTC minutes on Sunday
2026-09-13, each a command run from a laptop shell. No session was open on
Sunday, nothing in this repository can open one, and no capture was taken.
Under the registration's own §7 every slot is MISSING and the look is void;
collection closed 01:15Z 2026-09-14. The result document required by §10 is
`docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md`.

`tasks/NEXT.md` called it *"a scheduled run, not a task to plan"* in four
consecutive entries. There was no scheduler. The lesson is in
`tasks/lessons.md` (2026-09-14).

## 2. Decision

1. **Arm D is void.** No sixth capture, no later look, no re-run on this
   registration. §7 prohibits the move by name.
2. **No successor registration.** The registration's universal claim — no
   open `KXMVE` combination book carries a resting YES bid — was falsified on
   2026-09-10 by the disclosed unregistered look (two shard-1 books, one
   resting YES level of 10 contracts each; `EXIT_ANY` met, `EXIT_PRACTICAL`
   met at its boundary). The correction owed whatever Sunday returned
   (§11.8, ruled in §12.4) shipped before C1 and is on every combo-buying
   surface. What Sunday would have added is a *rate*, and the one decision
   branch still carrying a consequence — `EXIT_AT_CEILING`, a resting bid of
   250 or more reopening `COMBO_MAX_CONTRACTS` — had an observed size of 10
   against it. A rate on a retracted claim is not worth a second weekend of
   Joe's abstention.
3. **The hold on combo taps is lifted as of this ADR.** Joe's answer (B) of
   2026-09-11 was given on the framing that the run would happen. The framing
   is dead. Whether he taps is his own call, as it always was; nothing on this
   side asks him to wait.
4. **Any future registration with a clock-time stopping rule must name the
   person at the keyboard and how the session exists at that minute, or use
   a rule any later session can satisfy.** And any constraint it imposes on
   Joe carries the window's end as its expiry and is reported to him when the
   window closes, pass or fail.

## 3. What this does not decide

- Nothing about combination exit *frequency*. Unmeasured, and stays so.
- Nothing about `/hedge` (reads legs, not the combination book — §9).
- Nothing about Arms B and C, whose instrument did not land and which did not
  run by the registration's own words.
- Nothing about ADR 0078's `EXIT_PRACTICAL` trigger: an unregistered look
  does not fire a registered rule, and this ADR does not fire it either.
