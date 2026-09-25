# 0186 — The scouts give a TAKE or PASS on each parlay leg, before Joe buys

**Status:** Accepted on Joe's word, 2026-09-25 (session 57, option buttons). Numbered 0186 on `main`: 0185 was the highest and no lane held a DRAFT.
**Date:** 2026-09-25
**Schema:** v57 — `leg_verdicts`, a pure new table (`_TABLELESS_VERSIONS`)
**Tickets:** story #151 under epic #83
**Supersedes:** ADR 0060 §5's "no verdict on any bet", **for the new leg-scout seat only**
**Leaves standing:** ADR 0060 and ADR 0069 for all four desk seats (`scout`, the staff pair, the master, `pro_bettor`), whose no-forecast rule is unchanged and still pinned word for word; ADR 0071 §2.5 (a per-row fact may be shown, never ranked by); ADR 0063 (`gate.py` reads none of this); ADR 0112 (no brake of ours bounds a hand bet, and this adds none)

## 1. What Joe decided

His words: *"point the scouts to the parlay legs. I just want to know if the
scouts would make the bet or not … even the 'safe' bets and 'middle' bets have
been unsuccessful. i am wondering if the scouts looking at the parlay legs would
have been helpful as a second gate after the parlay is selected before actually
purchasing it."* Then: *"make sure the advice is in plain language."*

Three option-button answers, each the recommended one:

| question | answer |
|---|---|
| How hard is the gate? | **Advisory.** TAKE/PASS per leg beside the buy button; it never blocks. |
| What pays for it? | **Repoint auto-scouting.** `SCOUT_AUTO_CONVENE_ENABLED = "false"` on live; leg verdicts spend inside the same `AGENT_MAX_*` ceilings. |
| Which legs? | **Every leg of a card he opens**, fired on his first step toward buying it. |

The evidence under the second answer is on #145. Unattended scouting could
afford 2 convenings a day, and it spent them by late morning on the day's
earliest games. So 34 of the 39 legs Joe bet from 09-21 to 09-24 were on
games nobody had scouted. The budget was going somewhere he was not.

## 2. The seat

`backend/agents/leg_verdict.py`: one `structured_call` per leg, at most 3
web searches, on `AGENT_MODEL`. It returns `LegVerdict{verdict: take|pass,
reason}`.

- **PASS means a specific, current, named reason** to avoid this side at this
  price. **TAKE means no such reason was found.** It is not a prediction that
  the leg wins. Fixing the meaning gives the scoring one hypothesis to test.
  It also counterweights `HOUSE_CONTEXT`, which every call carries and which
  tells the model to treat any apparent opportunity as a defect. Left alone,
  that pushes every verdict to PASS.
- **Still no number.** The schema has no numeric field, walked by test, and
  the prompt forbids a probability, a fair price, a line, a spread and a
  stake. A take/pass is falsifiable against the price the server recorded.
  An LLM probability would not be, and ADR 0060's reason for the no-number
  rule still stands.
- **Plain language** (`PLAIN_WORDS_RULE`): one or two everyday sentences,
  jargon banned unless explained in the same sentence, 220 characters at
  most. An overrun is recorded as failed, never clipped.
- **The seat never sees our fair percentage.** It gets the leg, the side,
  Kalshi's ask in words, kickoff, and the game's desk briefing if one exists.

## 3. Why this does not reopen ADR 0038

ADR 0038 bounds what the *tool* may claim, and it reaches nothing Joe does by
hand. This verdict is shown to Joe at the moment of a hand bet. It does not
enter `fair_probability`, sizing, the gate or any ranking, and nothing on
the order, RFQ or hedge path reads `leg_verdicts`, which a test pins. It is
the same status the desk briefing has had since ADR 0060: context for his
own decision. What is new is that the context now includes an opinion.

## 4. How it will be judged

Forward only. The seat searches the web, and after a game the web holds the
result, so a verdict produced after kickoff is contaminated. Only a verdict
completed before kickoff counts, and the table's CHECKs enforce that. Rule,
floors and stopping date:
`docs/measurements/2026-09-25-preregistration-scout-leg-verdicts.md`.
**It is underpowered, and that was known in advance.** At about 10 legs a day,
the registered stop (2027-06-30) can detect roughly a 6-point effect. A small
real benefit will read UNRESOLVED, which may not be reported as "no help".
The interim look can catch a large effect early.

## 5. Cost

Not measured. One call per leg at ~10 legs a day is 10 of 24 calls and at
most 30 of 60 searches. Tokens are the likely binding ceiling. Read
`agent-spend` for `agent = 'leg_verdict'` over three days before moving any
ceiling, and move the three together or not at all (the standing rule).

## What this does NOT establish

- That a verdict is ever right. Until the registration declares, a verdict is
  an opinion beside a button.
- That TAKE and PASS are used at useful rates. A seat that says PASS on
  every leg is informative about the prompt, not the legs. Read the split
  after the first few days, and treat an extreme split as a prompt defect.
- That the verdict reaches Joe before he buys. The trigger is his first
  step toward buying, and a tap straight through the buy flow can outrun a
  call that takes seconds.

## Amendment 1 — 2026-09-25 (session 58): the first day's cost, and verdicts in flight hold budget

**Read.** `inspect_live_db.py agent-spend --days 1`, budget day 20260925,
read 17:12Z. There were 17 `leg_verdict` calls, with a mean of ~51K tokens
(range 28.9K–90.2K). The n = 1 reading of 31,640 in §4 of the session-57
handoff was the low end. The day recorded **1,120,442 tokens against the
500,000 ceiling**. Sixteen of those verdicts were admitted between 16:06:24Z
and 16:06:35Z, in about five POSTs, at 334,711 recorded. Each one passed
`AgentBudget.refusal_reason` against spend already recorded, because a
verdict records its tokens and searches only when it settles. That is a
burst admitted before any of it was billed, not "a brake overshoots by the
last call". TAKE 14, PASS 3. n = 17 on one day is not a rate, and §4's
extreme-split rule is not yet triggered.

**Decided (#156).** `AgentBudget.refusal_reason` takes `reserved_tokens`
(default 0, so every other caller is unchanged). The leg-verdict route
reserves `LEG_VERDICT_TOKEN_RESERVATION = 60_000` tokens and
`LEG_VERDICT_MAX_SEARCHES` searches for each `running` row younger than
`RUNNING_PATIENCE_MS`. Calls need no reservation, because the seat's
`budget.reserve` writes the `agent_calls` row at call start. At the unchanged
500,000 ceiling, a day now admits about nine verdicts. **No ceiling moved.**
That is still Joe's decision, and it waits on the three-day read in §5.

**Also found on the first look (#155).** Every trigger discarded the POST
result, and a refused leg writes no row. So a refusal showed on the card as
"No scout read: nobody has asked yet". #154 made the refusal text plain
words; #155 puts it on the screen.
