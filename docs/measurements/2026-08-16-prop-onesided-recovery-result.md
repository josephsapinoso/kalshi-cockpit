# One-sided prop recovery — UNMEASURABLE, and permanently so

**Registered:** `docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md`
**Dump:** `docs/measurements/2026-08-16-prop-rungs-dump.json.gz` (41,827 rungs, `truncated: false`)
**Run:** `docs/measurements/2026-08-16-prop-onesided-recovery-run.txt`
**Taken:** 2026-08-16, from `/data/cockpit.db` on `kalshi-cockpit`, via
`inspect_live_db.py prop-rungs --json --limit 400000`.

## The verdict

**Gate A: UNMEASURABLE. Gate B: NOT REACHED.**

Not "the prize is too small" — that is the registered `< 0.5` branch and it is
*not* what happened. The ratio `recoverable / kept` has **no denominator**:

```
alternate rungs kept today     0
alternate rungs dropped        35448
  of which recoverable         12270
  of which unrecoverable       23178
```

`kept` counts alternate rungs where a book quoted **both** sides. That is the
held-out set the whole design rests on — the only place the recovery's error can
be checked against a known answer. It is empty.

## The load-bearing fact, and the control that makes it believable

Counted directly off the dump, over every row:

| `is_alternate` | has Over | has Under | rows |
|---|---|---|---|
| false | ✓ | ✗ | 2,439 |
| false | ✓ | ✓ | **3,940** |
| true | ✓ | ✗ | **35,448** |
| true | ✓ | ✓ | **0** |

**No alternate rung anywhere in the record carries an Under.** Not one, across
10 bookmakers and 20 fixtures.

The fourth row is the finding; the second row is what licenses believing it.
The same query, the same pivot, the same books and the same fetch produce 3,940
two-sided **primary** rungs. So the zero is not a pivot that drops the Under
column, a market-key mismatch, or a capture that asks for one side — any of
those would have flattened the primaries too. It is a property of the feed.

## What this closes

**The recovery can never be validated from this source.** Not "not yet" —
`kept` is structurally zero, and props came off the sweep schedule at v43
(ADR 0032), so the record stopped growing. There is no future run that fixes
this, and no amount of waiting produces a two-sided alternate rung.

That kills the line of work as specified. Applying the recovery anyway would
mean inferring the missing side on **100%** of alternate rungs with **zero**
examples to check against — and §6 of the registration named the direction that
failure would take: a positive bias makes every recovered Over look cheap, which
manufactures fake edges. Unvalidatable *and* biased toward the flattering
direction is the worst pair available.

## What this does not establish

- **Nothing about whether the prize was real.** 12,270 of 35,448 dropped rungs
  (34.6%) are recoverable *in principle* — the Over is priced and the player's
  primary exists. Gate A never got to weigh that, because feasibility here
  failed on validatability, not on size. The 4.6× claim in the registration is
  **untested**, not refuted.
- **Nothing about other sources.** This is The Odds API's `alternate_*` market
  keys under the deployed `ODDS_REGIONS`. A different provider, or a different
  region set, might quote alternates two-sided. Nothing here was measured
  outside what this instance bought.
- **Nothing about the primaries.** 3,940 two-sided primary rungs exist and are
  untouched by this verdict.
- **It is one snapshot per fixture.** `prop-rungs` reads the latest sweep per
  fixture, so this is 20 fixtures at one instant each, not a time series.
  A book that goes two-sided on alternates only near lock-in would not appear.

## Two process notes

**The documented command undercounts by 52%.** `tasks/NEXT.md` gave the dump as
`--limit 20000`. The real record is 41,827 rungs, so that command returns a
truncated prefix — `truncated: true`. It would not have produced a wrong number:
`load_rungs` refuses a truncated dump outright, and that guard is what caught
it. But the command as written could not have completed the task.

**The dump is stored gzipped** (10MB → 261KB, 38×). A one-shot that can never be
re-taken has to be committed to stay re-checkable, and this repo is going
public. `analyze_prop_onesided.py` reads `.json.gz` transparently, and
`tests/test_analyze_prop_onesided.py` asserts the committed artefact still loads
and still carries the 35,448 / 0 split the verdict turns on.
