# ADR 0118 — A missing required mart suppresses every headline, and the test that said otherwise was the defect

Status: accepted
Date: 2026-09-09

Closes `tasks/audit-2026-08-07.md` item 23, open since 2026-08-07 and carried
in `tasks/NEXT.md` as "top of the next session's list". The ruling recorded
here was made by the partner agent on 2026-09-09 and is executed, not
re-derived.

## Context

The Dashboards screen reads dbt marts. Every mart emits a `verdict` string
rather than only a number, so that a dashboard cannot plot a noise-level
result as though it were a finding. One of them, `mart_multiple_comparisons`,
is not a finding at all — it is the **count of tests that produced the
findings below it**, and it is marked `required` in `backend/analysis/marts.py`
for exactly that reason. The comment there already said so: *"rendering
per-bucket findings without the count of tests behind them is the exact error
it exists to prevent."*

`read_dashboards` did its half correctly. It distinguishes a mart that is
absent from the warehouse (`unavailable`) from one that built and produced no
rows (`empty`), and it computes `missing_required_marts` and logs a warning.

**`headline_verdicts` never read that field.** It walked `MARTS` and appended
every `status == "ok"` panel's verdict. So a warehouse built with
`mart_clv_by_bucket` alone would headline a per-bucket result with the
multiple-comparisons qualifier **absent from the warehouse entirely** — the
repo's own "count your tests" rule defeated by the dashboard that exists to
enforce it, and rule 1 (a large apparent edge is a bug until proven otherwise)
with the qualifier missing rather than merely small.

### The test enshrined it

`tests/test_marts.py:108`, `test_unavailable_panels_contribute_no_headline`,
built a warehouse holding only `mart_clv_by_bucket` and asserted:

```python
assert headline_verdicts(read_dashboards(path)) == ["mart_clv_by_bucket: only one"]
```

That is the defect written down as the expected value. It is this repo's
recurring failure shape — a guard, its implementation and its test written in
one sitting from one mental model, so the test inherits the error rather than
catching it — and it is the sixth recorded instance.

## Decision

**`headline_verdicts` returns an empty list when `missing_required_marts` is
non-empty.** Not a filtered list, not a list with a warning prepended: nothing.

**Only *required* marts suppress.** An absent `mart_suppression_audit` is a
complete warehouse for the purpose of reading a verdict.

### Why suppression rather than a warning

"Show it with a warning" is how warnings get read past, and there is no way to
qualify a finding with a mart that was not built — the qualifier is not weak
here, it is absent. Withholding is the only honest rendering.

### Why an empty list does not become "nothing to report"

This is the objection the module's own docstring raises against everything
else in the file: a missing warehouse and a warehouse with no findings both
produce empty arrays, and rendered on a dashboard an empty table reads as
"nothing to worry about".

It does not apply here, because `missing_required_marts` travels in the same
payload and `frontend/src/app/dashboards/page.tsx:79` already renders a
**"Findings withheld"** banner off it, naming the marts that could not be read
and saying nothing below has been qualified. That banner pre-dates this
change and is what makes the empty list safe. **If it is ever removed, this
suppression has to be reconsidered with it**, and the docstring on
`headline_verdicts` says so at the point of change.

## Consequences

- `backend/analysis/marts.py` — one early return, plus the reasoning above in
  the docstring so the next reader does not restore the old behaviour as a
  "bug fix".
- `tests/test_marts.py` — the enshrining test is **re-pointed, not deleted**.
  It keeps its warehouse and now asserts the headline list is empty, under a
  name that states the new claim, with the old claim recorded in its docstring
  so nobody re-derives it as a regression.
- A second test was added, `test_a_missing_OPTIONAL_mart_suppresses_nothing`,
  because without it the guard could be over-broad and untested — suppressing
  on any unavailable panel would teach the reader that an empty headline list
  is normal, which is how the suppression stops meaning anything.

### Verified by mutation, both directions

| mutation | result |
|---|---|
| remove the early return (restore the shipped behaviour) | `test_a_missing_required_mart_suppresses_every_headline` **red**, 23 green |
| widen it to suppress on any `unavailable` panel | `test_a_missing_OPTIONAL_mart_suppresses_nothing` **red**, 23 green |
| restored | 24 green, `ruff` clean |

Each mutation reddens exactly one test, and a different one. Neither test is
decoration and neither is the other's duplicate.

## What this does not decide

- **Nothing renders `headlines` today.** It is typed at
  `frontend/src/lib/api.ts:747` and served from `backend/api/routers/status.py:415`,
  and no `.tsx` reads it. The fix is still correct — the field is on a public
  API surface and the next screen to read it inherits the guarantee rather
  than the defect — but this ADR does not claim a visible change on the
  screen today. The visible guard is the banner, and it already existed.
- Whether `mart_calibration` should be `required`. It is, and this change
  makes that setting load-bearing in a way it was not before: an unbuilt
  calibration mart now silences the dashboard's headlines too. Left as-is
  because it is the pre-existing declaration and reversing it is a separate
  judgement about which marts qualify which.
