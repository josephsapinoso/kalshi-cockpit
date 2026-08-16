# Result — non-sports spread reachability

**Run 2:** 2026-08-16T00:24:31Z, one `/events?with_nested_markets=true` walk.
**Registered at:**
[`2026-08-15-preregistration-non-sports-spread-reachability.md`](2026-08-15-preregistration-non-sports-spread-reachability.md),
before any non-sports market was read.
**Instrument:** `scripts/census_non_sports_spread.py`.
**Raw:** [`2026-08-16-non-sports-spread-census.json`](2026-08-16-non-sports-spread-census.json),
console at [`2026-08-16-non-sports-spread-census-run.txt`](2026-08-16-non-sports-spread-census-run.txt).

**Run 1 (00:06Z) is SUPERSEDED on instrument grounds and is kept, unedited, at
`*-run1-superseded.json/.txt`.** It is retained rather than deleted because the
two defects it exposed are the most useful thing this measurement produced. §2.

**Cost: zero Odds API credits, zero writes, no order path.**

---

## 1. The headline

> **The registered falsifier fired. Compared like price with like, the discarded
> arm is dead on cost: 424 DEAD to 129 WORTH A FAIR VALUE across 620
> genuinely-non-sport series priced where the control is priced, with a median
> ratio of 3.0 to 4.5 in every major category.**

An earlier draft of this document reported the opposite — "the direction is not
dead on cost" — off run 1. That reading did not survive audit. What changed was
the instrument and the population cut, not the decision rule, which is
unamended.

## 2. Two instrument defects, found by audit before publication

**2.1 One-sided books were counted as settled outcomes.** Kalshi never omits
`yes_bid_dollars`/`no_bid_dollars`; it sends `"0.0000"` for a side nobody bids.
Run 1 had a single `settled_price` counter catching both, and an `unreadable`
counter that was **0 across all 81,420 markets** — dead code. So **28,579
markets, 35% of the arm, were dropped under a label that was wrong for 99.5% of
them** (run 2 separates them: 28,579 one-sided against **140** genuine
settlements).

That is not a neutral shrink. It removes exactly the markets where entry cost is
infinite, so every surviving median is biased toward tight by an amount run 1
could not measure.

**What the split now shows, and it is the one reassuring number here:** the two
arms exclude at comparable rates — **67.1% readable in the sports control,
63.0% in the treatment arm**. Run 1 could not check this at all; its
`sports_detail` carried three fields and no exclusion counts.

**2.2 No price was recorded for any market**, so a *tight* series could not be
told from a *cheap* one. §4 shows this was the dominant confound.

Both are fixed, both are pinned by tests seen red, and run 2 additionally emits
the per-league control, the leave-one-league-out jackknife, per-series
`events_seen`, `readable_share`, `median_ask_tenths`, and the **IQR the
registration required at §4 and run 1 silently never computed**.

## 3. The control is not a stable denominator, and that is a finding

```
Pro Baseball        9 series      5.0 tenths
Pro Basketball (W)  4 series     12.5
Pro Football        3 series     55.0
NCAA Football       3 series    175.0
```

**A 35× spread across four leagues, and 9 of the 19 contributing series are
MLB.** Leave-one-league-out:

| Dropped | Control |
|---|---:|
| NFL, NCAAF, or WNBA | 10.0 |
| **MLB** | **35.0** |

So the pooled control of 10.0 tenths is very largely *"MLB in August"*.

**The registration's §5 justification does not survive this.** It argued a ratio
against a control "cancels" a venue-wide effect. Nothing cancels against a
reference with 35× internal dispersion; the treatment series are being divided
by one arbitrary point of it. **No ratio in this document should be read as
precise, and any verdict within ~25% of a cut point is UNRESOLVED whatever the
table says.**

The direction of the residual bias is knowable and it runs *against* the
headline: the pooled control (10.0) is near the tightest league, so it makes
treatment series look **worse** than a full-season control would. The §1
refutation is therefore conservative on this axis. A control computed without
MLB (35.0) would move most of the arm to WORTH — which is precisely why the
pooled number cannot carry a verdict in either direction.

## 4. The price-level confound, which run 1 could not see

| Population | Median ask |
|---|---:|
| Sports control series | **50.5c** |
| Series verdicted DEAD | 48.0c |
| Series verdicted **WORTH A FAIR VALUE** | **12.0c** |

**44% of WORTH series price at or under 10c; 23% at or under 5c.** An absolute
half-spread of 0.5 tenths is 1% of a 50c contract and ~25% of a 2c one. The
registration compared absolute half-spreads across a treatment arm spanning
every price regime against a control drawn entirely from near-50c moneylines, so
**"tight" and "cheap" were the same measurement**, and `CLAUDE.md`'s rule —
bucket by the price you would actually pay — was not satisfied.

**Restricting to a price-comparable band (median ask 20c–80c), where the control
lives:**

| Population | DEAD | UNRESOLVED | WORTH |
|---|---:|---:|---:|
| All series in band | 699 | 133 | 217 |
| **Genuinely non-sport in band** | **424** | **67** | **129** |

Per category, genuinely non-sport, in band — **median ratio, not a verdict**
(§5 of the registration forbids a pooled verdict):

| Category | Series | Median ratio | WORTH |
|---|---:|---:|---:|
| Financials | 259 | 4.50 | 68 |
| Economics | 92 | 4.00 | 10 |
| Entertainment | 58 | 3.50 | 5 |
| Politics | 51 | 3.00 | 9 |
| Mentions | 34 | 3.00 | 7 |
| Elections | 30 | 3.00 | 6 |
| Science and Technology | 30 | 3.50 | 5 |
| Companies | 21 | 4.50 | 1 |

Every one at or above the registered DEAD ratio of 3.0.

## 5. Weather — the run-1 finding does not survive

Run 1 reported daily city-temperature ladders as the tightest coherent family
(median ratio 1.50, 17 WORTH of 31) and called it the result worth having.

**In the price-comparable band, weather has 13 series with n ≥ 5: 7 DEAD, 4
WORTH, 2 UNRESOLVED.** The tight ladders were largely deep out-of-the-money
rungs at 1–3c carrying a tick-floor book — cheap, not tight.

Two further problems with that family, both from the audit and both conceded:

- **It was defined after seeing the data, by ticker prefix.** `KXLOWT*`/
  `KXHIGHT*` silently excluded `KXHIGHPHIL`, `KXHIGHDEN`, `KXHIGHCHI`,
  `KXHIGHNY` — the same product, four more cities, no `T`. A family boundary
  drawn post hoc by string prefix with no rule written down is not a boundary.
- **`n` of 5–10 per series is not 5–10 observations.** A ladder's rungs are one
  market's book read at several strikes, against one underlying. The
  registration's floor counts *markets*; the independence unit is the event.

**What survives about weather is a contrast, not a level:** the catastrophe
series (`KXHURRICANE`, `KXNAMEDSTORM`, `KXHURRICANENAMES`) are DEAD by a wide
margin under every control in 5.0–35.0. That is robust. "Weather is tradeable"
is not, and was never supported.

## 6. Verdict against the registered rule

**§6's falsifier — "three times wider or more" — fired**, on the population the
registration was actually about, compared at a comparable price level.

- The **direction is dead on cost** for genuinely-non-sport markets priced where
  a bettor would want them.
- The **residue is small and named**: 129 series in band, spread across
  categories, none with an interval, half resting on `n ≤ 10`.
- **No category is opened.** Nothing here licenses building a fair value for
  weather, elections, or anything else.

**The direction is closed on cost, at this instant, for this price band.** The
next question — where a probability would come from — is not reached.

## 7. What this does NOT establish

- **AVAILABILITY IS NOT FILLABILITY.** Every number is a stored quote. A
  two-sided book at a tight spread is consistent with real liquidity *and* with
  a maker who cancels when an order arrives. One small order separates them;
  nothing here does.
- **One instant**, 00:24Z, mid-August. Both runs are the same night. A second
  look is a **new registration**.
- **Top of book only.** No depth, no orderbook call, no volume or open interest.
- **The control is 47% MLB and spans 35× across four leagues** (§3). Every ratio
  inherits that.
- **No interval anywhere.** 1,908 series each got a verdict from a median over
  5–10 markets. This is a census read once, not a test; no p-value is quoted and
  none may be inferred. The IQR is now emitted per series and is **not** used in
  any verdict — the registered rule has no place for it.
- **`n` is markets, not events.** 9,936 events across 3,537 series is ~2.8
  events per series, so most n=5–8 series are one or two ladders. The floor is
  doing less work than §5 of the registration assumed.
- **The 20c–80c band is a post-hoc cut.** It is justified — it is where the
  control lives, and comparing like prices is `CLAUDE.md`'s own rule — but it
  was not registered, and it is the cut that moved the answer. **Both cuts are
  published above** so a reader can see the unbanded figures (1,052/302/554) and
  judge the choice.
- **It says nothing about whether an edge exists.** A spread is an obstacle, not
  a signal, and rule 1 stands.
- **It says nothing about competitive density.** The RFQ claim that prompted
  looking — "zero engagement across all 96 non-sports RFQs" — was attributed to
  `tasks/prior-art.md:44-46`, **a file that does not exist**, and no such finding
  is in this repo. **No reader may cite that figure; this document does not
  corroborate it.**
- **1,629 of 3,537 series returned `INSUFFICIENT`** and are in no ratio above.
  They did not fail the bar; they could not reach it.
- **`runner.py:1820` hardcodes `kalshi_events.category = 'Sports'`**, so nothing
  in the stored record distinguishes these arms. This probe read the wire and
  stored nothing.

## 8. Counted assumptions

**A1.** That `yes_ask = 1000 - no_bid` is what a taker pays on these markets, as
on the sports markets this project prices. No non-sports fill has ever been
observed here. Every number moves if it is wrong.

**A2.** That `classify_series`'s in-scope predicate is the right split. It is the
production classifier and the census calls it rather than re-expressing it.

**A3.** That a median over 5–10 rungs of one ladder describes a series. §5 and §7
say why this is weak; nothing in the artifact can strengthen it.

**A4 — deviation from the registration, recorded.** §4 required an IQR per
series; run 1 never computed it and run 2 emits it but no verdict consumes it.
The registered rule reads the median alone.

## 9. What would still overturn this

1. **A control computed per league across a full calendar year.** The pooled
   control is a mid-August artifact and this is the cheapest fix.
2. **Re-cut on the price actually paid rather than a 20c–80c band chosen here.**
3. **An event count per series**, to learn whether `n = 6` is six observations
   or one.
4. **One resting 1-contract order** on any series called tight. Nothing above
   substitutes for it.
