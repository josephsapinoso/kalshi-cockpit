# The `_alternate` prop feed buys coverage, not prices

**Taken:** 2026-08-27, by re-analysis of a committed artefact. No credits spent,
no live access, no new capture.

**Source:** `docs/measurements/2026-08-16-prop-rungs-dump.json.gz` — 41,827
rungs, 10 bookmakers, 20 MLB fixtures, `truncated: false`. Same file the
2026-08-16 one-sided-recovery verdict was taken from.

## What was already known

`docs/measurements/2026-08-16-prop-onesided-recovery-result.md` established
that **no alternate rung anywhere in the record carries an Under** — 35,448 of
35,448 are Over-only — with 3,940 two-sided *primary* rungs as the control that
rules out a pivot artefact.

It stopped there, because its own question (can the missing side be recovered?)
died on having no held-out set. It did not ask what the feed costs or whether
it should keep being bought.

## The gap this closes

That analysis pivoted with `feed` as a key. **Production folds `feed` away** —
`prop_quotes_for_event` groups by `(base_market, norm(player), point)` and
folds `_alternate` onto the base via `base_market()`. So an alternate Over
pairing with a *primary* Under at a shared point would have been invisible to
the earlier pivot and would have counted as a usable line in production.

Folded exactly as production folds:

```
total rungs                                    41,827
folded (event, book, base_market, player, point) groups   38,062
two-sided after folding feeds                   3,940
two-sided that REQUIRE an alternate row             0
```

It never happens. The zero survives the fold.

## The finding

Reconciling against the claim that argued *for* buying the feed — this repo's
own comment at `backend/odds/client.py`, *"both are needed to compare more than
one rung in seven — measured 2026-08-14 at 48 of 263 Kalshi markets on
primaries alone"*:

```
distinct rungs quoted at all        7,103
  of which priceable (two-sided)    1,466   (20.6%)
rungs quoted ONLY on alternate      4,707   (66.3%)
  of those, priceable                   0
```

**Both facts are true and only one of them matters.** The alternate feed really
does roughly triple the number of Kalshi rungs we hold *some* quote for. Every
one of those additional 4,707 rungs is one-sided, so none survives the
both-sides admission at `runner.py:659-663`, none is devigged, and none reaches
`fair_prices`. The feed buys visibility of rungs nothing in this repo can
price. Coverage was the right measurement of the wrong quantity.

It is also 35,448 of 41,827 stored rows — **84.7%** — written to
`odds_snapshots`, which `store/retention.py` names as deliberately outside the
retention window.

## What changed as a result

`prop_market_keys()` returns the five base keys only. A prop event falls from
20 credits to 10 at `ODDS_REGIONS=us,eu`; the `POST /api/odds/refresh` tap from
24 to 14. `PROP_MARKETS` keeps the alternate keys so stored rows stay readable:
this stops us buying them, not understanding them.

## What this does NOT establish

- **Nothing about whether the alternate feed is one-sided at another provider,
  another region set, or another time.** This is The Odds API's `alternate_*`
  keys under the deployed `us,eu`.
- **It is one snapshot per fixture**, 20 MLB fixtures, 2026-08-16. `prop-rungs`
  reads the latest sweep per fixture. A book that goes two-sided on alternates
  only near lock-in would not appear, and this is exactly the caveat the
  2026-08-16 write-up already carried. Re-checkable on any prop tap for 10
  credits.
- **Nothing about the primaries**, whose 1,466 priceable rungs are untouched.
- **Nothing about whether prop consensus is any good.** This is a question about
  which market keys are worth buying, not about whether the resulting fair
  values predict anything. `beta` on the prop arm was **−0.519**
  (`docs/measurements/2026-08-16-clv-signal-test-interim-look.md`) and nothing
  here revisits that.
- **It is not a reason to put props back on the schedule.** ADR 0032's
  annotation kills that explicitly rather than deferring it, and a halved price
  is not on its own an argument.
