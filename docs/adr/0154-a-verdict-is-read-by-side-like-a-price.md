# 0154 — A verdict is read by side, like a price

Date: 2026-09-15
Status: Accepted
Supersedes nothing. Completes the fix `2d8de82` began.

## Context

`2d8de82` (2026-09-15) fixed a wrong-side read in `backend/parlays.py:leg_facts`:
the function was keyed by ticker and hardcoded `ask_for_side(quote, "yes")`, so an
Under leg printed the **Over's** ask and the Over's depth on its own row. The fix
added the `no_ask_*` keys to `_NO_FACTS` and `_ask_facts_for_side` to pick by
`CandidateLeg.side`.

**It fixed one reader in that function and left the other.** Three lines below the
repaired ask, the skeptic's verdict was still read by ticker alone:

```sql
FROM recommendations
WHERE ticker IN ({placeholders}) AND side = 'yes'
```

The comment `2d8de82` added directly above it — "Both sides, one derivation each.
The leg picks its own in `_serialise_leg` by `CandidateLeg.side`" — asserted a
property the function did not have. A justification that went stale in the same
commit that wrote it (`tasks/lessons.md`, "Justifications decay toward
reassurance").

### Why it stayed invisible

**Totals are immune for an unrelated reason.** `_price_totals_event`
(`backend/runner.py:1489`) "deliberately writes no `recommendations` row", so
both sides of a total fall through to `skeptic = "absent"` and are caught by the
`not_on_this_path` mapping at `parlays.py:1386`, which covers `spreads` and
`TOTALS_MARKET`.

**Props are not.** `_price_prop_event` (`backend/runner.py:2017`) builds a
`Candidate` per side in `for side in ("yes", "no")`, so one prop ticker carries
two `recommendations` rows — and `:1386`'s escape does not list props, by
deliberate design (the docstring at `leg_facts` argues at length that props ARE
on the recommendations path and must not be generalised onto it).

So the surviving half bites on exactly one card: **`props`**, which has **0 taps
in 77 lifetime `parlay_lookups` rows** (read off live 2026-09-15 ~19:30Z). The
totals card was the first thing anyone exercised, and it was immune. The props
card is the one Joe asked for on 2026-09-14 and has never once tapped — it would
have been wrong on first use, exactly as the totals card was.

### What it got wrong, in two directions

| | what the Under leg showed |
|---|---|
| the reason | the **Over's** `suppressed_reason`, on the row and into `score_trust` (`parlays.py:1490`) |
| the `checked` | a YES row's mere *existence* stamped `skeptic = "checked"` on the Under — twelve mechanical checks claimed on a side the skeptic never scored |

The second is the flattering one, and it is the misreading `leg_facts`' own
docstring already forbids in the other direction: *"a measurement that never
happened, reported as one that ran."* The docstring argued the case against
rendering `not_on_this_path` as a blank, and the code below it committed the same
error on `checked`.

## Decision

**A verdict is read by side, exactly as a price is.**

1. `_NO_FACTS` gains `no_skeptic` (default `"absent"`) and `no_suppressed_reason`.
   Flat keys, not a nested dict — `dict(_NO_FACTS)` is a shallow copy and a shared
   inner dict is the bug `scout_flags` already had once.
2. The `recommendations` read is keyed by `(ticker, side)`, and **the window
   function partitions by both**. `PARTITION BY ticker` alone would have returned
   whichever side was written last — a second, quieter version of the same defect.
3. `_verdict_facts_for_side(facts, side)` is the sibling of `_ask_facts_for_side`
   and refuses a third value rather than defaulting to YES.
4. `_serialise_leg` picks by `leg.side` for both the payload and `score_trust`.
5. A side with no `recommendations` row stays `absent`. **It is never inferred
   from its sibling.**

## Consequences

- A prop Under leg reports its own verdict, or `absent` when the skeptic never
  scored it. No user-visible change on totals, spreads or team legs — their
  verdicts were already right, for the reasons above.
- No schema change (v43 stands). No migration. `recommendations` already carried
  `side`; nothing was writing the wrong data, only reading it wrongly.
- The comment `2d8de82` left behind is now true of both readers.

## What this does not establish

- That any prop Under leg has ever been *shown* to Joe with a wrong verdict. The
  props card has 0 lifetime taps and the pool admits at most one leg per fixture,
  so the defect is demonstrated on seeded rows, not observed on live.
- Anything about `backend/kalshi/combos.py:402,476`, which carry `side: str =
  "yes"` defaults on `echoed_legs`/`lookup_combo`. Unreached today (every live
  caller passes explicit 3-tuples), same bug class, on the mint path. Recorded
  here so it is not re-derived; not fixed here.

## Guards, each seen red once

`tests/test_under_legs.py::TestAnUnderPropCarriesItsOwnVerdict`.

| mutation | test that went red |
|---|---|
| `_verdict_facts_for_side` returns the YES pair for `"no"` | both verdict tests; the Under reported `checked` on a side never scored |
| the `(ticker, "no")` branch of `leg_facts` deleted | `test_each_side_of_a_prop_reports_its_own_suppression` |
| the original defect restored (`WHERE side = 'yes'`) | `test_each_side_of_a_prop_reports_its_own_suppression` |
| the third value defaults to YES instead of raising | `test_a_side_that_is_neither_is_refused_not_defaulted` |

## The pattern

Written to `tasks/lessons.md` 2026-09-15 (sixth): **when you fix a wrong-side
read, fix every reader in that function and pin each with a test that names the
side.** The second reader's symptom is identical to the first's and equally
silent; and the card that would have shown it may be the one nobody has tapped,
so "it was fine in testing" measures which card was convenient, not which code is
correct.
