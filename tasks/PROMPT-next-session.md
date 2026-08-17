# Next session prompt

Paste everything below the line into a fresh session.

---

Read `tasks/NEXT.md` (top entry only), `tasks/lessons.md` (top four entries)
and `CLAUDE.md`. All three are readable — 36KB / 32KB / small.

STATE
main at df0f26b, schema v9. 3,080 tests pass, 10 xfailed, ruff clean,
tsc --noEmit clean. Re-verify; do not inherit.

BOTH INSTANCES ARE DEPLOYED AT b0bd2ec AND THAT IS NOT A BUG. The two
commits after it are docs only. Check /api/health before reacting to a
deployed-sha-behind-HEAD reading.

NOTHING IS UNVERIFIED. Last session's lane was seen on the live screen
in Joe's own logged-in Chrome, not asserted.

THE HUNT IS STILL CLOSED. ADR 0038. Nothing below reopens it, and
nothing below is a search for an edge.

WHAT THIS SESSION IS FOR — JOE HAS DECIDED, SO STOP IS NOT THE ANSWER

Partner ended last session with an explicit STOP and a refusal to name
a sixth item, on the grounds that the only things left were Joe's own
and every one of them touches money or credentials. Joe has now made
that call: **take on all three.** That is the decision partner was
waiting for, so do not re-ask whether to work — brief partner on the
decision and ask it to SEQUENCE the three and set the size of each.
It still owns order and scope. It no longer owns whether.

The three, and what is actually known about each.

1. ODDS_API_KEY ROTATION — security, and it has a structural blocker

WHY: a subagent read `.env` and the plaintext key landed in its
transcript on disk. By this repo's own standing rule that counts as
compromised. It is NOT the Kalshi key.

THE BLOCKER, and find out whether it is real before planning around it:
`.github/workflows/secrets.yml` states in its own header that it
**cannot** touch KALSHI_PRIVATE_KEY, KALSHI_API_KEY, APP_AUTH_TOKEN or
ODDS_API_KEY — "those live in Fly and nowhere else; routing them
through GitHub would double the number of vaults that can leak them."
That is a written, reasoned exclusion, not an oversight. So today the
rotation needs `flyctl secrets set` from a laptop, and Joe works from a
phone.

That makes the first deliverable a DECISION, not code: either Joe runs
one command at a laptop, or the exclusion is revisited with an argument
that engages the reason it was written. Do not quietly widen the
workflow. If the exclusion is revisited it needs an ADR.

I MUST NOT HANDLE THE KEY VALUE. Not in a file, not in a command, not
in a transcript. Generating the new key is Joe's action on his
the-odds-api.com account and installing it is his command. What a
session CAN do: confirm every place the old key is referenced, write
the exact command for Joe to run, verify AFTER rotation that the loop
still authenticates (a served sweep row is the proof, not a 200), and
check no transcript or artefact in the repo carries the old value.

2. THE ODDS TIER RENEWAL — measure it before anyone reasons about it

LAST READING, from the provider's own header via api_credits on the
live box: **1,104 used, 18,896 remaining, sum exactly 20,000**, newest
row 2026-08-16T22:59:23Z. Tier bought 2026-08-09. 6 credits per call,
not the 2 the config arithmetic predicts.

RE-MEASURE IT. That reading is a day old and the recorder has run
since. `flyctl ssh console -a kalshi-cockpit -C "python
/app/scripts/inspect_live_db.py credits-month"` — read-only, mode=ro.
`credits-tail` now selects `trigger` in the repo but the DEPLOYED image
may predate that; check the sha before trusting the column list.

ONE TRAP ALREADY SPRUNG, do not spring it again: `credits-month`
reports `min_remaining_reported 404`, which looks alarming and is not.
Those six rows are 2026-08-07/08 where remaining+used = 500 — the old
free tier, before the 20,000 tier was bought. Two tiers in one column.

A CEILING IS NOT A SPEND. `ODDS_DAILY_CREDIT_BUDGET = 600` in
fly.live.toml is a cap that is never approached. Do not multiply it by
anything.

The decision is Joe's, on the invoice. What a session owes him is the
run rate, the projection to renewal date, and what the recorder
actually buys for it — stated so it fits on a phone.

3. THE COST-OF-EXECUTION METER — the one that is genuinely a build

`sharp-bettor`'s proposal to re-point the Board from "is this
mispriced?" to "is this cheaper on Kalshi or at a book?". Written up in
`tasks/archive/next-2026-08-17.md`; summarised in NEXT.md's still-open
list. Joe's call was unmade and is now made.

READ THE PROPOSAL BEFORE PLANNING IT, and re-engage `sharp-bettor` —
that agent teaches the craft, it is not just a reviewer. Also put it in
front of `retail-bettor`, because the deployed caps are $100 bankroll /
$40 exposure / $10 daily loss and a whole position is one or two
contracts; a meter that is right for a professional can be useless at
that size.

THE PREMISE TO CHECK FIRST: the cost advantage is real but it is a
DISCOUNT, not a signal — a cheaper venue multiplies an edge, it cannot
create one, and no quadrant supplied one to multiply (ADR 0038). So
this meter must be built as a COST tool and must not be allowed to read
as a re-opened hunt. If the design starts implying picks, stop and say
so.

Also unresolved and load-bearing on it: H4. The 0.63-point headroom is
an UPPER BOUND, not a figure, because settlement fees are unseparated
from entry-only `fee_cost` (ADR 0027). A meter that quotes 0.63 as a
point estimate would publish an unproven number.

CONSTRAINTS — the standing ones, all still in force

Run runtime-realist BEFORE briefing agents or quoting an operational
number, not after. Name the file that would change if the deploy
changed — never .env.example, never a code default, never a docstring.

A ceiling is not a spend. For a rate or a bill, cite the row that
recorded it (api_credits, odds_sweep_log, the provider header), never
the setting that bounds it.

Before acting on a sentence that names a set and predicates over all of
it, open the set and check each member. That was wrong four sessions
running; last session it held, because the set was opened.

A feature and the path that invokes it are two deliverables. Put the
guard on the caller — the workflow file, the toml, the entrypoint.

Registered measurement first if anything gets measured. Money-touching
actions need Joe's say-so; deploys go through deploy.yml, and
`gh workflow run` is a classifier coin-flip, so retry rather than
handing it back. Check gh's exit code, not a piped tail's.

If Joe is at a laptop with Chrome open, SAY SO AND LOOK YOURSELF
rather than asking him to check a screen. The sweep strip is inside the
window panel above the cards, not at the top of the page.

DO NOT PICK THESE UP — partner's explicit drop list, and it is a drop
list rather than a backlog

- The blank gap between the last Board card and the footer. Cosmetic,
  undiagnosed, on a hard-closed line. Undiagnosed is not a reason to
  diagnose.
- Exercising the manual-refresh path to retire its zero-live-firings
  status. It spends credits on the tier under review.
- The ~99 clusters to G=300. Waiting is not work. Do not schedule a
  session for it.
- Anything reopening the hunt. A proposal must name which quadrant row
  it overturns and with what measurement.
- The sweep banner. Closed permanently on merge — no restyling, no new
  tones, no knob, no trigger backfill.

SESSION SHAPE

These three are close to independent — a security action, a
measurement, and a build — so they parallelise. Ask partner whether to
run them as worktree lanes. The rotation blocks on Joe's hands at some
point, so start it first and let it wait rather than making it wait at
the end.
