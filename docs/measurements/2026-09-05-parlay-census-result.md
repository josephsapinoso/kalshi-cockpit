# Parlay census — result

**Registration:** `2026-09-05-parlay-census-registration.md`, Amendment 1.
**Instrument:** `scripts/measure_parlay_census.py`, committed `950ad72`,
**before** the pull. **Data:** `data/2026-09-05-parlay-census.json`.
**The extraction is NOT in git, deliberately.** `docs/measurements/data/` is
caught by `.gitignore`'s `data/` rule, and that is correct rather than an
oversight: the JSON is Joe's per-position fill record — tickers, contracts,
prices, fees, results — and his standing ruling is that account and fills data
never enters this repo, even sanitised. **This document carries aggregates
only**, which is the same line the presence result observed. The registration
names the path; the path is a local artifact, and a reader who cannot find it
has not lost the finding.

**Read:** 2026-09-06, one look, on a pulled read-only copy of the live volume
(`cockpit.db` + `-wal` + `-shm`, `?mode=ro`, never `immutable=1`).
**Torn-snapshot precondition: PASSED** — in-window counts on the copy
(fills 53, settlements 52, lookups 32) matched the counts read on the box
before the pull, exactly.

---

## The verdict

> ## H1 (Arm D): **ADR 0085 REFUTED ON THIS POPULATION**
>
> ```
> n = 52    k = 51    p_taker = 0.9808
> exact Clopper-Pearson 95% interval   [0.8974, 0.9995]
> critical values, recomputed by the instrument   (18, 34)   — as registered
> ```
>
> **51 of Joe's 52 combination positions were entered as taker fills.** The
> interval lies entirely above the null of 0.5. The registered refute boundary
> was `k >= 34`; the observed `k` is 51.

**Every downgrade was applied and none fired:**

| Downgrade | Threshold | Observed | Fired? |
|---|---|---|---|
| Coverage | REFUSE above 20% unreadable | **0 unreadable, 0.0%** | no |
| Concentration — largest C-day | UNRESOLVED at ≥ 25% | **15.4%** (8 of 52, 2026-08-18) | no |
| Concentration — `G_eff` | UNRESOLVED below 10 | **10.24** over 14 C-day clusters | no |
| Leave-one-day-out | UNRESOLVED if any drop crosses | no drop crosses | no |
| Strict definition (`all_fills_taker`) | UNRESOLVED on disagreement | **k = 51, same side** | no |

`G_eff = 10.24` clears its floor by 0.24. That is a pass, not a comfortable
one, and it is the number to attack first if this result is ever revisited.

---

## Rule 1 was applied, because the result is a large contradiction

The registration required three named checks **before** a refutation could be
written, on the standing rule that a large apparent contradiction of a measured
belief is a bug until proven otherwise. All three were run and all three clear
it.

**1. Is `is_taker` mis-populated for combination fills?** No — it
discriminates in both populations over the same window:

```
KXMVE combinations   taker 52   maker 1    NULL 0
single markets       taker  7   maker 2    NULL 0
```

A field stuck at 1 for combinations would show no makers. There is one, and
its identity matters — see check 2.

**2. Does the ADR 0084 buy path stamp its own fills taker?** **No, and the
opposite of the feared failure is true.** By the registered join
(`fills.venue_order_id` → `combo_orders.kalshi_order_id`), exactly **one**
in-window combination fill was placed by the tool, and it is **the single
maker fill in the entire population** (`is_taker = 0`).

That is precisely what Amendment 1's Correction 2 predicted when it decided,
blind, to keep tool-placed fills in the primary denominator: a tool-placed
order rests (ADR 0084) and is systematically maker, so excluding it could only
raise `p_taker`. Excluding it does exactly that — 51/52 → 51/51 — which is why
it stayed in. **The conservative choice was made before the direction was
known.**

**3. Does the venue report combination fills differently from single-market
fills?** No. Every fill in both populations carries `source = 'venue_hand'`;
there is no combination-specific path, and no differential in how the field
arrives.

**Mandatory secondary fit** (Amendment 1, Correction 2), excluding the
tool-placed position: `n = 51, k = 51`, interval [0.9302, 1.0000], critical
values (18, 33) — **REFUTED**. Primary and secondary agree, so the registered
"disagreement across either boundary ⇒ UNRESOLVED" clause does not trigger.

---

## What this refutes, stated narrowly

ADR 0085, ADR 0012 §5, `NOTES["unquoted"]` and CLAUDE.md all say combinations
are unquoted — *"usually you can neither buy in at a quoted price nor be bought
out"*. On the 2026-08-30 census, `0` of `61` open combinations carried a
readable ask.

**On Joe's own 52 positions, an offer was there to hit 51 times.** Those two
statements are both true and they are not about the same population.

**The mechanism is already established, and it is not a contradiction.** The
census read the `/markets` **list summary** — `yes_ask_dollars = 0.0000`,
`no_bid_dollars = 1.0000`, whose derived ask is `$0.00`. `lookup_combo` reads
the **orderbook endpoint** via `OrderBook.best_no_bid`. Different instruments,
different answers, and the list summary flattens an empty side to a boundary
value. This was found by code-reading, before this run, as the registration's
C4 item.

## What it does NOT refute — the caveat most likely to overturn it

**§12.7, written before the run:** the population is *the collections Joe
happened to choose*, over 2026-08-18 to 2026-09-04, on a product that changed
exchange shards inside the window. **It is a self-selected sample of markets,
not a random one.**

The selection is not incidental, it is structural: **Joe only has a fill where
a fill was possible.** A combination he tapped, found unbuyable, and abandoned
leaves a `parlay_lookups` row and no fill — and 24 of the taps in the record
are exactly that (`book_empty`). Conditioning on entry having succeeded and
then measuring how often entry succeeded is not a measure of buyability at
large.

So the honest reading is: **"when Joe got into a combination, he almost always
did it by hitting an offer, not by resting a bid"** — and *not* "combinations
are quoted". The copy on the desk is refuted as a description of what happens
at the moment he buys; it is not refuted as a description of the order book in
general.

---

## The money arms — DESCRIPTIVE, no verdict of any kind (§8)

```
positions                52       (0 open; every one has a settlement row)
result split             no 49    yes 2    unresolved ('') 1
staked at cost           $60.13
fees                     $3.74
payout on wins           $4.05
net, excluding the one unresolved position     -$59.83
net bracket including it   -$59.83 (stake lost) .. -$55.49 (stake returned)
```

**No verdict is issued from these numbers and none may be** — not
"profitable", not "unprofitable", not "the cards work". §12.1: 2 of 51
resolved winners gives an exact interval of [0.48%, 13.46%] and an ROI error
bar 90×–800× the entire 0.63-point cost headroom. **These figures are a bank
statement, not a finding.** The unresolved row is bracketed rather than
decided (§13).

---

## One imprecision in the instrument, disclosed

The analyzer prints `tool_placed_positions = 34`, and that number is **not the
registered flag**. It counts positions with any non-null `venue_order_id`,
which the venue sets on Joe's app-placed orders too. The registered definition
is the join to `combo_orders.kalshi_order_id`, which gives **1**.

The verdict does not depend on it — the printed figure feeds no statistic, and
the secondary fit above was computed with the correct join — but the JSON
field is misnamed and a later reader would take it for the registered flag.
Corrected in the instrument; recorded here because the result file is what
gets read.

## The defect the first run found, in the instrument

The first execution printed **UNRESOLVED** on this same data.
`arm_d` classified by parsing its own verdict sentence —
`verdict.split()[-1]` — and the refute string is *"ADR 0085 REFUTED ON THIS
POPULATION"*, whose last token is **"POPULATION"**. The comparison was
therefore false for every refuting result, and both concentration downgrades
fired spuriously.

It bit only the refute branch (*"ADR 0085 UPHELD"* ends in "UPHELD" and
compared correctly), so it was invisible to every test that did not produce a
refutation. **It was found by Rule 1's own instruction to check the instrument
before believing a large contradiction** — the check caught a bug in the
checker. Fixed to classify by key, pinned by
`TestTheVerdictIsNotComparedByParsingItsOwnProse`, and the analyzer re-run on
**the same pulled snapshot**: the pull is the look (Amendment 1 A5), and
re-pulling would require an amendment. It was not re-pulled.

---

## What follows, and what does not

**Three shipped surfaces tell Joe something that is false at the moment he
buys**: the parlay card note, the nightly Discord push, and the `unquoted`
copy built from `COMBO_CENSUS_*`. They say he probably cannot buy in. He
bought in 51 times out of 52, by hitting an offer.

**What may not be concluded here:** nothing about profitability, nothing about
whether the desk's recommendations are any good (47 of the 52 have no desk
price recorded at all), nothing about sportsbook parlays, and nothing about
the engine, the gate or edge — ADR 0038 is not reopened by this document
(§12.12).

**Owed:** an amendment to ADR 0085 recording that its copy is refuted at the
moment of entry while its census stands for the order book at large, and a
decision from Joe about what the card should say instead. That is a product
decision, not a measurement, and it is not taken here.

> **SETTLED 2026-09-06. Both halves are discharged and this section is closed.**
> ADR 0085 carries **Amendment 1**, which records exactly that split: the copy
> is refuted at the moment of entry, the census stands for the order book at
> rest, and both figures must be cited together.
>
> Joe's decision went further than the amendment anticipated — he took the
> offer-making controls off the desk entirely, so there is no card left to
> re-word. He pays the ask or records a bet placed at a book; he does not make
> offers. The question "what should the card say instead" was dissolved rather
> than answered.
>
> One correction that outlived the card and is the reason this note is worth
> reading: the panel's sentence — *"on a combination nobody has ever been
> observed doing so"* — was refuted by a real **maker fill** sitting in the
> account (2026-09-01, 8 contracts @ 25c, `is_taker: false`). It is almost
> certainly the 1 of 52 this census counted as non-taker. **Re-derive any
> combination-liquidity copy from `is_taker`, not from position counts.**
