# 0079 — The `_alternate` prop keys are not bought

Accepted 2026-08-27.

**The number was allocated here, not when this was written.** It lived as
`DRAFT-alternate-prop-keys-are-not-bought.md` for the whole of the lane and
took 0079 after a `git fetch`, as the last act before the push, per
`docs/adr/README.md`. Three lanes collided on the ADR counter and
`SCHEMA_VERSION` on 2026-08-26 and git reported two of those collisions as
clean merges, because two lanes writing different filenames have nothing to
conflict on.

## Context

A player-prop event is billed per market key per region. `prop_market_keys()`
requested ten keys — five base markets and their `_alternate` twins — so at
the deployed `ODDS_REGIONS = "us,eu"` one prop event cost 20 credits and the
`POST /api/odds/refresh` tap cost 24.

The alternate feed was added deliberately, and the note justifying it is in the
record: *"Kalshi runs a ladder per player (`2+` through `8+`); a book quotes
one primary line and the rest on the alternate feed, so both are needed to
compare more than one rung in seven — measured 2026-08-14 at 48 of 263 Kalshi
markets on primaries alone."*

## The measurement

Re-analysis of a committed artefact — `2026-08-16-prop-rungs-dump.json.gz`,
41,827 rungs, 10 bookmakers, 20 MLB fixtures, `truncated: false`. **No credits
were spent and no new capture was taken.**

```
distinct rungs quoted at all        7,103
  of which priceable (two-sided)    1,466   (20.6%)
rungs quoted ONLY on alternate      4,707   (66.3%)
  of those, priceable                   0
```

Folded the way `prop_quotes_for_event` folds — group by
`(event, book, base_market, player, point)` with `is_alternate` collapsed away:

```
two-sided lines after folding feeds              3,940
of those, lines REQUIRING an alternate row           0
```

## The decision

`prop_market_keys()` returns the five base keys. A prop event costs 10 credits;
the tap costs 14.

`PROP_MARKETS` keeps the alternate keys. **This stops us buying them, not
understanding them** — `prop_quotes_for_event` selects `market IN PROP_MARKETS`
and folds via `base_market()`, so the rows already in `odds_snapshots` stay
readable and the parser stays held to them.

## Why the earlier note was right and still loses

Both facts are true. The alternate feed really does roughly triple the number
of Kalshi rungs we hold *some* quote for — 66.3% of rungs are alternate-only,
which is the same phenomenon "48 of 263" measured.

Every one of those rungs is Over-only. A book quoting one side is dropped by
`runner.py:659-663`, so an alternate-covered rung is never devigged and never
reaches `fair_prices`. **The feed buys visibility of rungs nothing in this repo
can price**, and every consumer — the parlay desk included — needs a fair value
rather than a sighting.

Coverage was the right measurement of the wrong quantity. Recorded that way
because the conclusion changed and the earlier reasoning did not have to be
wrong for that to happen.

It is also 35,448 of 41,827 stored rows — **84.7%** — written to
`odds_snapshots`, which `store/retention.py:55-57` names as deliberately
outside the retention window, on a 1.91 GB database with a 5 GB volume.

## What this explicitly does NOT decide

**It does not re-open ADR 0032.** Scheduled prop buying stays off. ADR 0032's
annotation says it is *"explicitly killed, not deferred"*, and a halved price
is not on its own an argument — the decision turned on props buying no cluster
toward the gate's floor, and reversing it needs its own ADR making its own
case. `fly.live.toml` carries this sentence beside the switch.

**It does not establish that prop consensus is any good.** `beta` on the prop
arm was **−0.519** (`2026-08-16-clv-signal-test-interim-look.md`). This is a
question about which market keys are worth buying, not about whether the
resulting fair values predict anything.

**It does not generalise past this feed.** The Odds API's `alternate_*` keys
under `us,eu`, one snapshot per fixture, 20 MLB fixtures, 2026-08-16. A book
that goes two-sided on alternates only near lock-in would not appear in it —
the caveat the 2026-08-16 write-up already carried and this inherits.

## Falsification

A prop tap returning **any** two-sided alternate rung refutes the premise. It
costs 10 credits and needs no special run: the next tap for any reason is the
test, and `inspect_live_db.py prop-rungs --odds-event-id ...` reads it. No
confirming tap is bought for this ADR — the measurement is finished, and buying
one to agree with a result already taken is not a check.

## Consequences

- Prop event 20 → 10 credits; tap 24 → 14. All four call sites derive from
  `prop_market_keys()`, so the quoted cost and the credit reservation move
  together and cannot drift.
- `fetch_props`' default now equals what every caller passes, removing the
  "reserve for five, request ten" shape that caused the 2026-08-15 outage.
- ~85% fewer rows per prop buy on an unpruned table.
