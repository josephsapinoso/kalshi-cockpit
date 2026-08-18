# 0050 — The suppression code gets a caption, never a translation

Date: 2026-08-18
Status: accepted

## Context

Joe is a beginner and has asked to be educated rather than shielded. Four
screens rendered `suppressed_reason` verbatim — a bare identifier like
`stale_odds,too_few_books,no_market_width` — and nothing on any of them said
what those words mean. The `/rejections` screen carries a paragraph per code in
its `EXPLAINED` map, but a reader has to already suspect the code matters, know
that screen exists, and leave the row to get there.

**There was a standing decision against translating them, and it was right.**
`SlateRow`'s docstring said the codes "are the server's vocabulary and are shown
verbatim — they are what `/api/suppression` counts and what a miscalibrated rule
shows up as. Translating them here would give the same rule two names." That
argument survives this ADR unchanged. Two names for one rule is a real cost: a
reader who sees "the odds aged out" on a row and `stale_odds` at the top of
`/rejections` cannot tell they are looking at the same thing, and a rule that
starts dominating the counts becomes harder to notice, not easier.

What was never true is that the code *alone* tells a beginner anything. It
names the rule. It does not say what happened.

## Decision

**The gloss is additive. The code renders, verbatim, in the same monospace it
always did; the sentence renders beneath it, muted.** Label and caption, not a
substitution. This is asserted, not left to convention:
`tests/test_suppression_gloss.py::TestTheGlossIsAdditive` reads each component's
source and fails if the raw field stops appearing in a rendering position.

Three further decisions, each of which was a defect first.

**1. The gloss covers every render site, and the list is derived rather than
enumerated.** The first pass glossed `SlateRow` and `OpportunityCard` and called
it done. Both are *Board* components. `/slate` — the screen Joe's phone habit
actually goes through — renders the field from its own markup in
`app/slate/page.tsx`, and `/ledger` renders it from a third. Two of four sites
were covered and the one that mattered most was not. A component-by-component
test written from the same wrong list would have called that complete, so
`TestEveryRenderSiteIsGlossed` scans all of `frontend/src` instead: any file
that renders the field must call the gloss or appear in an `EXEMPT` map with its
reason. It found `/ledger` on its first run. `/rejections` is exempt because a
second, shorter sentence there really would be the two-names problem;
`CrewBubble` is exempt because it interpolates the code into a sentence it
writes itself.

**2. There are two vocabularies in that one column.** `backend/engine.py:255`
writes `sizing:{binding_constraint}` into `suppressed_reason` when the sizer
refused and no check had fired, so a row can read `sizing:bankroll_unobserved` —
a string that is not a `Check` name and never will be. Pinning the gloss only to
`ALL_CHECK_NAMES` would have declared it complete while a whole class of
refusals rendered bare. `SIZING_GLOSS` covers them, pinned separately to the
`constraint=` arguments of `sizing._refuse`.

Only the *refusing* constraints are listed. `kelly`, `no_edge`,
`max_position_dollars`, `max_exposure_dollars`, `max_order_contracts` and
`stake_below_one_contract` sit on `SizingResult`s whose `refused` is false —
they clamp, and the `sizing:` prefix is written only under `if sizing.refused`.
A sentence for one of those would describe a state that cannot occur, so the
test fails in that direction too. (It fired: the first version of the scan read
`binding_constraint="no_edge"` as a refusal and demanded a sentence for it.)

**3. An unknown code glosses to `null`, not to a placeholder sentence.** A code
this build has never heard of means the server is running a rule the frontend
predates. That is a deploy-skew fact worth seeing, and wording invented for it
would hide exactly that. The house rule applies unchanged: unreadable resolves
to nothing, never to something plausible.

## What this costs, stated rather than discovered later

Every rejected row is now one to three lines taller — three when the reason is a
composite, which the demo record contains. On `/slate` at 390px with eleven rows
that is real scroll. Accepted deliberately: `/slate` is the diagnostic screen by
its own docstring, its rows already spend a full-width line on the codes, and
the alternative for a beginner is a page of identifiers. Truncating to the first
code was considered and rejected — the codes are joined in evaluation order, not
priority order, so "the first one" is not "the main one" and picking it would be
a claim the data does not support.

## Verification

`scripts/check_mobile.py` clean at 390/768/1024/1440/1920/2560 against a local
build served from `data/demo.db`, which happens to carry a three-code composite
row — screenshots eyeballed at 390. Suite 3,432 passed / 10 xfailed, ruff clean,
`tsc` clean, frontend build clean.

Every guard added here was verified by breaking it and watching it go red: ten
of them, including two that were **green** when first written and were rewritten
until they failed —

- counting `rec.suppressed_reason` occurrences did not detect the code being
  swapped for the sentence, because both components also reference the field as
  a *condition*. The check is now for a rendering position specifically.
- the `/ledger` mutation had to remove *every* gloss call, not just the rendered
  one, before the scan noticed. That is the mutation being wrong rather than the
  guard, but it is written down because the first run of it read as a pass.

## What this does not establish

That any sentence is correct or current — a wrong sentence passes every test
here, exactly as `tests/test_suppression_screen.py` states for `/rejections`.
That the two lines are legible together at every width, beyond the 390px
screenshots. And nothing at all about whether the suppression rules are
themselves calibrated; this makes the refusals readable, not right.
