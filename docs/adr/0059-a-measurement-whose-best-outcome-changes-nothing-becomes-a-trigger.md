# 0059 — A registered measurement whose maximum-value outcome changes no decision is downgraded to a conditional trigger, not abandoned

Date: 2026-08-21. Status: ACCEPTED (partner ruling 2026-08-21 ~02:10Z,
recorded by the session that executed it). Supersedes nothing; generalises
the H4 Look 2 decision (Amendment 3, A17) into a standing rule.

## The decision, stated narrowly

Before any session builds the machinery for a registered measurement, it
asks one question first: **if this measurement returns its most valuable
possible answer, what decision changes?** If the honest answer is "none" —
no guard moves, no gate opens, no roadmap item unblocks, no claim the tool
makes to its user changes — the measurement is **not built as scheduled**.
It is downgraded to a **conditional trigger**: the cheapest observation
that would tell you whether the expensive machinery could ever pay for
itself is registered and taken first, and the machinery is built only on
the branch where it can.

The measurement is **not abandoned**. Its registration stands, its
schedule survives on the triggering branch, and the trigger's own decision
rule — both branches, both consequences — is registered before the trigger
runs, exactly as any look would be. A trigger with an unregistered rule is
a peek, not a downgrade.

## The instance that forced the rule

H4 Look 2 (2026-09-03) required the A9–A12 analyzer: ~200 lines plus a
mutation-verified test file, implementing a seven-branch aggregate tree, a
positive-control gate, an early-credit scan and span pairing. Registration
§10 already recorded that no live trading decision hangs on H4's answer —
the maximum-value outcome adjusts an upper-bound *footnote* on a cost
headroom the closed hunt (ADR 0038) gives nothing to multiply against.
Meanwhile the record on disk already suggested the instrument is blind:
the balance channel demonstrably responded to debits and sat flat through
a $5.00 predicted credit for 11 hours (Amendment 3, A15).

The partner's ruling: do not build A9–A12; register the cheapest
observation that separates "the channel can carry the signal" from "it
cannot" (A17's channel diagnostic, one read-only pull, zero credits), fix
both consequences in advance — CARRIES CREDITS buys the analyzer one
dedicated session; BLIND closes the look series early as BLOCKED ON
INSTRUMENT with a stated, measured reason — and only then spend.

## Why "abandon" is wrong and "build anyway" is also wrong

- **Build anyway** spends a session instrumenting a channel the record
  says cannot carry the signal, and the schedule — not evidence — is what
  spends it. That is sunk-cost accounting applied forward.
- **Abandon** throws away a registration that is already paid for and
  leaves the series to expire on dates rather than close on a reason. A
  study that ends because its instrument was shown blind has a record; a
  study that ends because the dates ran out has a gap (A17.9). The
  record is this project's product.
- The trigger buys the difference: **a clean ending, not a result.**

## What this does not decide

- **It does not license skipping measurements whose outcomes do change
  decisions.** The gate's 300-game floor, the beta look at G = 300, and
  every guard-moving measurement are outside this rule's reach — their
  best outcome moves something, so they run as registered.
- **It does not let the trigger's rule be chosen after its data is seen.**
  The downgrade is only honest if the trigger is itself pre-registered
  (A17 is the template: population, statistic, decision rule, stopping
  rule, audit, all fixed before the pull).
- **It does not reopen ADR 0038.** A trigger firing on its valuable
  branch buys the *measurement machinery*, never a trading decision.
- **It is not retroactive.** Measurements already taken stay taken;
  nothing here re-litigates a recorded look.
