# 0013 — Period markets are out of scope, and that is now a classification rather than a warning

Date: 2026-08-09
Status: accepted

## Context

Every fresh process on the live instance emitted this:

    WARNING backend.kalshi.discovery: 12 unrecognised competition_scope
    value(s) across 12 series -- excluded from pricing. [...] In leagues this
    project can price (12 scopes, [...]): '1st Quarter Spread'
    (KXWNBA1QSPREAD), '1st Quarter Total' (KXWNBA1QTOTAL), [...]

All twelve are WNBA quarter markets. All twelve are in a league this project
prices, which is exactly the case the warning was built to surface — see
`tasks/lessons.md`, *"Test that the filter's exclusions are decisions"*
(2026-08-06), where a classifier guessing at scope spellings silently discarded
every spread and total in the universe while the whole test file passed.

So the warning was working. Nobody had answered it. The question it asks is
"should this be in `FIXTURE_SCOPES`?", and until now the repo has had two
answers available — *priceable* and *nobody has looked* — with no way to say
*looked, and no*.

That gap has a cost beyond tidiness. This warning shares a 100-line log buffer
with the boot lines three sessions could not read (ADR-adjacent work on
`_WARNED_SCOPES`, and `tasks/lessons.md` 2026-08-09 on the 962-line burst). A
line that reprints a decision already taken is a line readers learn to skip —
and the next unrecognised scope arrives in the same shape as the twelve they
have been skipping.

## Decision

**Quarter markets stay excluded, and the exclusion is recorded in code.**

`PERIOD_SCOPES` holds the twelve, lowercased, spelled exactly as Kalshi spells
them. `EXCLUDED_SCOPES = NON_FIXTURE_SCOPES | PERIOD_SCOPES` is what
`classify_series` now tests against, so a period scope is classified rather than
unrecognised, and the warning narrows to its real meaning: **a value nobody has
looked at.**

### Why they are excluded

Not because they are not fixtures — they are. A 1st-quarter spread is one game,
one line, one settlement. They are excluded because of the **reference price**:
the sportsbook consensus this project subscribes to and devigs is game-level.
There is no quarter-level consensus to compare a quarter-level Kalshi price
against, and Rule 1 (*a large apparent edge is a bug until proven otherwise*)
has no way to fire on a comparison that was never made. Pricing a quarter
against a full-game line would not error; it would produce numbers, and they
would be wrong in a direction nothing downstream could detect.

### Why `PERIOD_SCOPES` is separate from `NON_FIXTURE_SCOPES`

The two sets exclude for different reasons and a future reader needs to know
which applies. A future or an award is excluded by what it *is*, and no data
source changes that. A quarter is excluded by what *we subscribe to*, and a
period-level odds feed would reopen it. Folding them together would lose
precisely the distinction that says which exclusions are revisitable.

### What was deliberately not done

**Only the twelve observed on 2026-08-09 were added.** Not MLB's `Extra
Innings`, `First 5 Innings Winner` or `YRFI/NRFI`, which are out of season and
whose exact strings are not in front of me. Adding a scope from memory is the
2026-08-06 bug verbatim: a guessed spelling classifies nothing and, worse,
looks like it did. When those series return, the warning will name them with
Kalshi's spelling attached and they can be added then.

**No substring rule.** `"quarter" in scope` would be shorter and would convert
one answered question into a standing exemption for every period product Kalshi
ever ships. A test asserts that `1st Half Winner`, `5th Quarter Winner`,
`Overtime Winner` and `1st Quarter Margin` still warn.

## The safety property, and how it was verified

Classifying these must **narrow** the warning, never silence it. Verified by
breaking it three ways and watching the right tests go red:

| Mutation | Result |
|---|---|
| `PERIOD_SCOPES = frozenset()` | 4 red, including the exact live line — *"12 unrecognised competition_scope value(s) across 12 series"* |
| `return` at the top of `_warn_about_new_unknown_scopes` | 8 red, both new safety tests among them |
| exact match replaced by `"quarter" in scope` | 1 red — the novel-period test, and only it |

`unknown_scopes` on the `discovery:` summary line still prints every pass,
including at zero, so silence here still cannot be read as "the problem went
away". The new slate test asserts the two agree: no warning **and**
`unknown_scopes=0`.

## What would change this decision

- **A period-level consensus.** If the odds feed carried quarter lines, the
  reason for the exclusion is gone and these move to `FIXTURE_SCOPES`. Nothing
  else about them is disqualifying.
- **Evidence, not appetite.** Quarter markets are thinner and more bot-contested
  than the game line, and this project has not cleared the 52.00% bar on the
  game line yet. Rule 3 applies unchanged: the claim would have to survive
  against Kalshi's own quarter-market close.

## What this ADR does not establish

That quarter markets are unprofitable. It establishes that this tool cannot
currently *measure* whether they are, and that shipping a price it cannot check
is the failure mode the three rules exist to prevent.
