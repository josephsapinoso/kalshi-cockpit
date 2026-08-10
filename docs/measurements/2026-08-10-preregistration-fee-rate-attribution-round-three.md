# Pre-registration — round three: the rate attribution, in a series that offers the prices

**Registered 2026-08-10 (UTC), before any round-three order exists.**
**Fills in scope at registration time: 0.**

**Revised in place 2026-08-10, before commit, before any fill, following an
independent audit.** A `measurement-skeptic` lane exported the live quote record
and re-derived §0.4's census from raw rows, without reading the census scripts
for their numbers, returning **SURVIVES WITH QUALIFICATION** — every headline
number reproduced exactly. This revision folds in that audit's strengthenings
and its five corrections. It is an **in-place revision of an uncommitted draft
against an empty population**: no fill existed, no round-three number could have
been seen, and nothing in it was selected by a result. **From the commit of this
file onward the amend-by-appending rule applies and no section may be edited
again.**

This is a **new registration**. It does not edit, reinterpret or reopen
[`2026-08-10-preregistration-fee-rate-attribution-round-two.md`](2026-08-10-preregistration-fee-rate-attribution-round-two.md)
(body + Amendment B), which is closed with the status **REGISTERED, NOT RUN**,
nor
[`2026-08-10-preregistration-fee-model-fill-calibration.md`](2026-08-10-preregistration-fee-model-fill-calibration.md)
(body + Amendment A), nor
[`2026-08-10-fee-model-fill-calibration-result.md`](2026-08-10-fee-model-fill-calibration-result.md).
Where this file needs a fact from any of them it **cites** it and does not
restate it as new evidence.

**It authorises no deploy and no code change.** Round one §9 and round two §9
forbid deploying a model fitted to these fills. That prohibition stands and is
extended: **this round decides an attribution; it does not touch
`backend/core/fees.py`, and the `max()` hedge stays.** `ORDERS_ARE_DRY_RUNS`
remains `True`; ADR 0018 is untouched.

**Five attributions carry over unchanged** from round two §1 — H-SERIES,
H-SPORT, H-SIZE, H-PRICE, H-NOTIONAL, and H-NONE as a first-class verdict. This
document changes **where the cells sit**, not what is being asked.

---

## §0. What is inherited, and the exact boundary of what is not

### §0.1 From round one, as given

Six taker fills, 2026-08-10, licensed by `measurement-skeptic` and carried
forward as **given**, not re-derived:

- `fee_cost` is **`ceil` to $0.0001**; **scope is per-order**; **a single rate
  across the two series is refuted** for any shape symmetric about 0.50 and
  non-decreasing on [0, 0.50].
- Conditional on the `C·P(1−P)` shape: **`k_MLB ∈ (0.03495687, 0.03500761]`**,
  **`k_ATP ∈ (0.06996078, 0.07000000]`**.
- The three **`KXMLBGAME` anchors** this round leans on, quoted exactly:

| round-one cell | series | `C` | `P` | observed `fee_cost` |
|---|---|---:|---:|---:|
| F1 | KXMLBGAME | 1 | 0.27 | **$0.006900** |
| F2 | KXMLBGAME | 10 | 0.27 | **$0.069000** |
| F4 | KXMLBGAME | 1 | 0.48 | **$0.008800** |

- The MLB shape test admits `P(1−P)` and refutes `P`, `min(P,1−P)`,
  `sqrt(P(1−P))`, `(P(1−P))²` and constant, pinning the power family to
  **`a ∈ (0.9816, 1.0361]`** — at **two prices, in one series, one degree of
  freedom**.

### §0.2 From round two, as given

The five attributions, their falsifiers, §7's decision-rule *shape*, §2's
exclusions, §3's placement discipline and pre-submit check, and §8's hard stop.
Round two §B8 says explicitly that none of it cost anything to keep and a future
round should not re-derive it. It is not re-derived; it is cited and adapted.

### §0.3 What round two established as its result

**A reachability failure.** `KXMLBGAME` did not offer the 6–14c band its two
load-bearing cells required. §B2 named the defect: the guards checked that the
cells could **discriminate** and never that they could be **filled**.

### §0.4 What is new, and is the whole reason this round exists

**[CENSUSED — reported to this lane by the census lane, 2026-08-07 to
2026-08-10, 11 series, 1,031,989 quote rows, pre-game only, ask derived as
`1000 − no_bid_tenths`, pre-game boundary `true start = occurrence − 3h`
(ADR 0006).]**

**[AUDITED — independently reproduced 2026-08-10 by a `measurement-skeptic`
lane, from a raw export of the live database, deriving every figure itself
without reading the census scripts for their numbers. Verdict: SURVIVES WITH
QUALIFICATION. Every headline number below reproduced exactly.]** The audit's
additions are marked `[AUDITED]`. Its five qualifications are §0.4a–§0.4e and
they change the design, not merely the prose. **The clock-validation clause that
used to sit in the line above — "validated 55/55 and 85/85 against independent
clocks" — is corrected in §0.4b: for `KXMLBSPREAD` it is a validated
*transfer*, not a direct measurement.**

| finding | number |
|---|---|
| `KXMLBGAME` asks **below 20c**, pre-game | **zero** in 51,286 observations over 85 events; cheapest ever 26.0c; p1 **28.5c** |
| cross-check against independently-sourced `closing_lines.yes_ask_tenths` | same **29.0c** floor |
| `KXATPDOUBLES` rows in `kalshi_quotes` / `kalshi_events` / `kalshi_markets` / `recommendations` | **0** |
| `KXWNBAGAME` low band | reachable on **1 event of 18**; the two halves never co-occur |
| `KXMLBSPREAD` | 55 events, 437 markets, 52,530 pre-game observations, **min ask 7.0c** |
| `KXMLBSPREAD` 6–15c (excl 10c) **and** 27–39c (excl 30c) available **simultaneously** | **696 of 696 polling instants — 100%**; 40 distinct low-half events, 55 high-half events |
| `KXMLBSPREAD` depth at those bands | **≥1 contract at 100% of instants**; median 2,914 low / 4,624 high |
| `KXMLBSPREAD` per-slate minimum asks, four slates | **9c / 10c / 8c / 7c** — the parts agree |
| `KXMLBGAME` 27–39c band | available on **24 of 85 events** |
| trap check at 7.0c | active market, game unplayed, two-sided book, 11–16h pre-game, depth 579–3,344, refreshing |
| **[AUDITED]** low-band displayed size, n = 5,030 rows | p0 **1**, p1 **2**, p5 **355**, p50 **2,914**; **share ≥ 20 contracts = 98.23%**; restricted to ≤ 13c (n = 2,725), **97.32%**. The tail is **bimodal** — sizes are under 10 or over 50, with little between |
| **[AUDITED]** low-band depth at the *instant* level | **695 of 695** pre-game instants carried **at least one** qualifying low market with **≥ 20 displayed** (min **2** such markets, median **7**, max 15) |
| **[AUDITED]** simultaneity is **within-EVENT**, not merely within-series | at **695 of 695** pre-game instants a single event held one market in 6–15c and another in 27–39c at the **same `observed_ms`**; **658** of those pairs are the **same strike, opposite teams** (e.g. `…ATHBOS-ATH4` at 15.0c against `…ATHBOS-BOS4` at 32.0c, both strike 3.5) |
| **[AUDITED]** price stability | given a market in band at one poll it is in band at the next **99.7%** of the time; the ask is **unchanged in 98%** of consecutive pairs; largest single move observed **2.0c**; 56 maximal in-band episodes across 45 markets, **median duration 569 minutes**, 86% ≥ 2h. **Upper bounds — see §10** |
| **[AUDITED]** low band by time of day | **37.1%** of low rows are within 3h of first pitch (**37.8%** at depth ≥ 20), covering **30 of 55 events**, against `KXMLBGAME`'s **7%**. In **17:00–23:59 ET**: **189 of 189** instants carried a qualifying low market, median **4** on the board; **164 of 189 (87%)** carried one at ≤ 13c |
| **[AUDITED]** the low band is **not** a derivation artefact | of all 5,030 low rows, **zero** have a missing or zero YES bid; bid-ask width **1.0c** at p0/p25/p50/p75, 2.0c at p95, 4.0c max; **none one-sided, none crossed**; median **1.2 minutes** since the book last changed. On the captured wire payload, `1 − no_bid_dollars == yes_ask_dollars` on **245 of 245** markets |
| **[AUDITED]** tick grid at submit | **52,470** pre-game asks in the audited series are **whole cents**, and `price_structure` is `linear_cent` — **no deci-cent surprise at submit in `KXMLBSPREAD`**. (§0.4 above cites 52,530 pre-game observations; the 60-row difference between two independent derivations is unreconciled, recorded rather than smoothed, and immaterial to this claim.) **Not extended to `KXMLBGAME` or `KXWNBA*`**, which the audit did not cover on this point, so §1.4's deci-cent recompute rule stays for every cell |

### §0.4a — the honest `n` of the census, which is not 696

**[AUDITED, and it is a correction to how this file was using the number.]**
696 polling instants is **uptime, not evidence.** The 696 resolve into **261
polling sessions** at a >5-minute gap split, and **64% of the 696 came from one
observation day.** A poller writing rows on a timer measures its own uptime; it
does not manufacture independent observations. This repo has already shipped a
gate that counted 400 rows on one ticker as 400 observations and had to be
fixed; the same inflation was latent here.

The independent units this census actually carries:

| unit | count |
|---|---:|
| game-days | **4** |
| events | **55** |
| pre-game markets | **330** |
| markets that ever supplied a low ask | **45** |
| maximal low-band episodes | **56** |

Concentration is good, and it is printed rather than pooled: the largest single
market is **8.1%** of low rows, the largest event **9.2%**, and **all four
slates contribute**. The parts agree.

> **REGISTERED CONSEQUENCE.** Every "100% of instants" and "696 of 696" figure
> in this file is to be read as **"at every instant on four game-days across 55
> events"**, and nowhere as `n = 696`. **No section of this document, and no
> section of the result document, may present 696, 695 or 5,030 as a sample
> size.** The transfer that matters — from these four days to the run date —
> rests on **four game-days**, and that is the number §S requires beside every
> instant count.

*(The audit's pre-game simultaneity denominator is 695 where §0.4's is 696: a
one-instant difference between two independent derivations, unreconciled,
immaterial at this precision, and recorded rather than smoothed.)*

### §0.4b — the pre-game boundary in `KXMLBSPREAD` is validated by transfer, not directly

**[AUDITED — and this is an INFERENCE, labelled as one, not a measurement.]**
`KXMLBSPREAD` has **zero** sportsbook-linked events, so the independent-clock
check that validated `occurrence − 3h` on `KXMLBGAME` **cannot be run on
`KXMLBSPREAD` at all.** Two substitutes hold, and neither is the same thing:

1. the **ticker-embedded ET hour** agrees with `commence_ms − 3h` on **55 of 55**
   `KXMLBSPREAD` events; and
2. all **55** `KXMLBSPREAD` events carry a `commence_ms` **identical** to their
   `KXMLBGAME` twin, **47** of which are sportsbook-validated at
   `commence − 3h` — and **0 of 47** validate `commence` as-is.

**So the boundary is inherited from a twin series, not measured in this one.**

**What that puts at risk, and what it does not.** It puts the **census** at risk:
if the boundary is wrong for `KXMLBSPREAD`, some rows counted as pre-game were
not. It does **not** put the **fills** at risk, because **P8 does not use this
inference**: P8 requires Joe to confirm, at placement, from the app that the game
has not started **and** from the ticker's encoded start time. The measurement's
pre-game guarantee is operator-side and independent of the census's boundary
rule. That separation is why the inference is tolerable here and would not be if
the fills inherited it.

### §0.4c — `KXMLBSPREAD` is a **selected** series, not a forced one, and the criterion is registered

**[AUDITED.]** The census scanned **11 series**, and `KXMLBSPREAD` is **not** the
maximum on raw availability. `KXMLBTEAMTOTAL` reaches the low band at **691 of
696 instants (99.3%) from 50 distinct events**, against `KXMLBSPREAD`'s **40**,
with **min ask 5.0c** against 7.0c, and **8,292** low observations against 5,039.
On availability alone it is comparable or better.

> **THE REGISTERED SELECTION CRITERION**, stated because a series chosen after a
> scan is a researcher degree of freedom and an unstated one is the finding:
> `KXMLBSPREAD` is **the series that was independently audited** for depth,
> stability, simultaneity and derivation soundness. `KXMLBTEAMTOTAL` was not.
> The criterion is **that an audit was performed**, not any property of the
> prices.

**Why that criterion is blind to the dependent variable — and the available
statement is stronger than discipline.** The dependent variable is `fee_cost`,
and **this account holds zero fee observations in `KXMLBSPREAD`, zero in
`KXMLBTEAMTOTAL`, and zero in every one of the 11 scanned series except
`KXMLBGAME` and `KXATPDOUBLES`.** The choice **could not** have been made on the
dependent variable, because the dependent variable does not exist at any
candidate. That is not a promise about how the choice was made; it is an
unavailability, and unavailability is the only kind of blindness worth
registering.

**Registered for the next round:** `KXMLBTEAMTOTAL` is the **designated successor
series** and may be used **after an equivalent audit** — instant-level depth,
in-band persistence, within-event simultaneity, and a no-derivation-artefact
check. It may **not** be substituted into this round, on any branch, for any
reason.

**The residual this creates, and it is real.** A series chosen as one of 11
carries **optimistically selected** availability: the winner of a scan looks
better than the population it came from, and availability is exactly the
quantity that must survive to the run date. Registered as **B10** in §11 and
disclaimed in §10. It is *partly* mitigated by the audit's finding that
`KXMLBSPREAD` is not the availability maximum — the selection was not made on
the quantity at risk — and it is not eliminated by that.

### §0.4d — the sub-10c region is thinly evidenced, and no registered band leans on it

**[AUDITED.]** Only **3 markets and 3 events** ever printed below 10c, and
**22 of the 307 sub-10c rows are one market.** A band whose availability rested
on ≤10c would be far weaker evidenced than one at 11–15c.

**Checked cell by cell: none does.** `S1`'s band is 6–15c and `S2`'s is 6–13c;
their availability citations are for the **whole band** at every instant, and
their depth citation is for the **whole ≤13c region** (97.32% of rows at ≥20
displayed; 695 of 695 instants with at least one such market). Neither citation
is a sub-10c citation, and 7.0c is reported throughout as the band's **floor**,
never as its mode.

**No band is narrowed, and the reason is the same defect in the opposite
direction:** narrowing `S1` to 11–15c would trade a **fully cited band** for an
**uncited sub-band**, because the census reports availability for the band as
registered and not for a 11–15c slice of it. Round two died of an uncited band.

**What is registered instead, so a sub-10c fill is a predicted outcome rather
than a surprise:**

- A fill below 10c is **legal and classifiable.** §R2 holds everywhere: the
  minimum LOW/HIGH separation across the whole design is **17 grid units**, at
  `S1` 6c, and at `S2` 6c the two envelopes are **349 grid units** apart. Price
  thinness never threatens a classification.
- A fill below 10c is the **most extrapolated point in the design** — furthest
  below round one's 27c anchor — so **D-B2a's shape reading from a sub-10c cell
  carries the widest envelope in this file and must be labelled as such** in §S
  item 12. It stays a by-product either way (§7.4).
- **The scan rule is NOT modified to prefer 11–13c.** A price preference inside
  a registered band is a new degree of freedom bought for a benefit that accrues
  only to a by-product, and §3 forbids changing an anti-gaming rule between
  rounds for less than an arithmetic reason. `R`'s two-pass had one; this would
  not.

### §0.4e — what the audit certified, and the one thing no quote record can

The audit closed the gap round two died in. It did not close the next one, and
the next one is now this design's live exposure.

> **Two explanations fit every observation in this census, exactly.**
> **(i)** there is real resting liquidity at these prices; or **(ii)** a maker
> is quoting 2,914 contracts at 13c and pulls on any incoming order. The
> displayed size, the 98% quote stability, the 569-minute median episode, the
> two-sided book, the 1.0c width and the 1.2-minute median staleness are
> **equally consistent with both.** **Nothing in a quote record separates
> them.** The separating observation is **one small order** — which is exactly
> what this round places.

**Round two failed at AVAILABILITY. Round three's exposure has moved to
FILLABILITY.** This census reduces the first to near zero and says **nothing
whatsoever** about the second. That is the honest one-sentence summary of §0.4,
and it is repeated verbatim in §10.

§3 registers what happens if a cell does not fill, §7.2 registers how it is
classified, and §9 registers where it is written up. **Round two had no rule at
all for a market that is displayed and does not fill.** That omission is closed
here, in advance, rather than discovered on the day.

---

### §0.4f — round two's registered escape route, confirmed dead

**Round two's dead end is confirmed and round two's escape is dead too.** §B6
registered `KXATPDOUBLES` as the way out; it is **not in the record at all**, so
it cannot be censused, and using it would require a live board read that no
guard in this document can make in advance. **`KXATPDOUBLES` is unavailable to
this round.** That is a design constraint, not a preference, and §0.6 prices it.

---

## §0.5 What moving the primary cells to `KXMLBSPREAD` costs — stated before the design

Required by the brief, and it is the most important section in this file.

### §0.5.0 — round two rejected this exact shape by name, and the rejection is answered before any cost is priced

Round two **§B3(b)** rejected *"a different baseball series at an extreme line
(`KXMLBTOTAL` / `KXMLBSPREAD`)"*, in these words:

> *"It collapses D1/D2's series with D3's treatment. H-SIZE's boundary
> `c* ∈ (10, 20]` was measured against `KXMLBGAME` at `C = 10` and
> `KXATPDOUBLES` at `C = 20`; a HIGH at `C = 20` on `KXMLBTOTAL` is ambiguous
> between H-SIZE and H-SERIES, because H-SERIES makes **no** prediction for a
> series it has not seen (§C1). The cell that was supposed to isolate size would
> isolate nothing."*

**That rejection is correct as written, and it does not reach this design.** The
reasoning, worked here rather than asserted:

1. **§B3(b) rejects a LONE `C = 20` cell in an unseen series.** Its whole force
   is that H-SERIES carries a free parameter for `KXMLBSPREAD`, so a single
   observation there is absorbed into a new table entry. That is true of one
   cell, and only of one cell.
2. **This round places three cells in `KXMLBSPREAD`, and a lookup cannot return
   three values for one key.** H-SERIES assigns the series **one** rate, so it
   predicts `S1 = S2 = S3` — uniformity — and uniformity is falsifiable by
   observation.
3. **So the ambiguous vector §B3(b) named does not exist here.** Under H-SIZE
   the vector is `(R, S1, S2, S3) = (L, L, H, L)`. Uniformity fails at `S1`
   against `S2`, so **H-SERIES is refuted by the very observation that declares
   H-SIZE.** The free parameter cannot absorb a HIGH at `S2` while `S1` and `S3`
   in the same series are LOW; absorbing it would require the lookup to return
   two different values for one key.
4. **The converse vector is equally unambiguous.** If `KXMLBSPREAD` genuinely is
   a high-rate series, all three cells return HIGH — `(L, H, H, H)` — which
   declares **H-SERIES alone**: `S1` HIGH refutes H-SIZE (`C = 1` must be LOW
   under every admissible `c*`), and `S3` HIGH refutes H-PRICE (`P ≥ 0.27` must
   be LOW under every admissible `b`).
5. **`c*`'s cross-series provenance does not bite.** §B3(b) notes that `c*` was
   pinned from a `KXMLBGAME`/`KXATPDOUBLES` comparison. This round never needs
   `c*`'s value: **every** admissible `c* ∈ (10, 20]` puts `C = 1` strictly below
   it and `C = 20` at or above it, so H-SIZE's prediction at every registered
   cell is identical across the whole interval.

**This is §B3(c)'s own accepted form, applied to size instead of price.**
§B3(c) rejected a *lone* low-price cell in a new series and **accepted** the
**within-series price pair**, because the pair differs in price and nothing
else. `S1` and `S2` are a **within-series size pair**: same series, same sport,
same day, same price region — and the bands are cut (§4 criteria 1 and 2) so
that **both sit on the same side of every H-PRICE and H-NOTIONAL threshold**,
which means the pair isolates size even in the branch where `S1` and `S2` do not
share a market. Round two accepted the pairing principle; this round applies it
to the second axis. **[AUDITED]** the record even supplies the tighter form
§B3(c) did not ask for: at 695 of 695 pre-game instants the low and high bands
co-occurred **within one EVENT**, 658 of them at the **same strike on opposite
teams**.

**The two limits of the rebuttal, stated rather than left implicit:**

- **It rescues the pair, not a lone cell.** If `S1` **or** `S3` is VOID, NOT
  ATTEMPTED or DID NOT FILL, then `S2` standing alone in `KXMLBSPREAD` reverts
  to exactly the cell §B3(b) rejected. §7.2's coverage qualifier already says
  *"without `S3`, H-PRICE cannot be separated from H-SERIES"*; the parallel
  statement is now registered beside it — **without `S1`, a HIGH at `S2` is
  ambiguous between H-SIZE and H-SERIES and NEITHER may be declared.**
- **It assumes H-SERIES is a pure per-series lookup with no interaction.** A
  compound rule — *"this series charges the high rate, but only above 10
  contracts"* — is not in the registered family, is not separated by this
  design, and falls out as **H-NONE**. That is how §7.3 already treats every
  compound rule, so it is not a new exposure; it is the same one, named again at
  the place it would otherwise be forgotten.

**Ruling: the design stands, and §B3(b) is answered rather than stepped over.**

### Cost 1 — H-SERIES stops being pinned by any *single* `KXMLBSPREAD` cell

Round two §C1: `rate by SERIES` carries **one free parameter per series** and
makes **no prediction** about a series it has not seen. `KXMLBSPREAD` has never
been filled. So a lone `KXMLBSPREAD` cell is **free** under H-SERIES: whatever
it returns is absorbed as a new table entry.

If this round placed one `KXMLBSPREAD` cell, H-SERIES would survive **8 of 16**
outcome vectors against 2 of 16 in round two, and the SERIES arm would be dead.

**The design answer, and it is the correction that saves the round: place
*three* cells in `KXMLBSPREAD`.** H-SERIES says the rate is a **per-series
lookup**. A lookup assigns `KXMLBSPREAD` **one** value. So with three cells in
one series H-SERIES makes a real, falsifiable prediction — **uniformity**:
`S1 = S2 = S3`, all LOW or all HIGH. **[COMPUTED]** that restores H-SERIES to
**4 of 32** vectors (§Power), which is the same order as round two's 2 of 16,
and it is *not* free.

**What is still lost:** H-SERIES can never be falsified *across* a series, here
or in any affordable design. Round two §Power conclusion 2 is unchanged and is
restated in §10.

### Cost 2 — H-PRICE is established on `KXMLBSPREAD` and transferred to `KXMLBGAME` only under H-PRICE's own claim

Round two would have tested H-PRICE **inside `KXMLBGAME`**, which is **73.0% of
the pinned record** (round-one result, `pin = 1564`). It cannot: §B6 registered
that as a **dead end**, and §0.4 confirms it with 51,286 observations rather
than one day's board.

So round three tests H-PRICE inside `KXMLBSPREAD` and transfers the answer to
`KXMLBGAME` **only under H-PRICE's own claim to be a global rule about price**.
That transfer is an **assumption, labelled as one**, exactly as §B6 required. It
is registered in §11 as **B8** and disclaimed in §10.

### Cost 3 — B2 (the `C·P(1−P)` shape) becomes load-bearing at an unshape-tested series, and the low prices are where it bites hardest

Round two §10 already called B2 *"the caveat most likely to overturn the
result"* when it applied to a **secondary** cell and had **no detector**. Moving
the primary cells to `KXMLBSPREAD` makes it primary. **This round gives B2 three
detectors rather than declaring it undetectable.**

**[COMPUTED]** the round-one power band `a ∈ (0.9816, 1.0361]` widens the
predicted fee by:

```
27c-52c, C = 1     0 to 2 grid units      (INTERPOLATION - inside the [0.27, 0.48] anchors)
 6c-15c, C = 1     2 to 3 grid units      (extrapolation below the anchors)
 6c-13c, C = 20   28 to 49 grid units     (extrapolation, times twenty)
```

The prices that are newly reachable are exactly the prices at which the
candidate shapes diverge most. That is the cost, quantified. The three detectors
are **D-B2a** (the envelope classifier, §1.4), **D-B2b** (the within-series
`S1`/`S3` ratio, §7.4) and **D-B2c** (a NOVEL classification, §7.2).

**[COMPUTED — the reassurance, and it is only partial]** at `S1` = 7c, `C = 1`,
with `k = 0.035`, the five shapes round one refuted give `min(P,1−P)` $0.0025,
`P` $0.0025, `(P(1−P))²` $0.0002, `sqrt(P(1−P))` $0.0090, constant $0.0088 —
**none of which is inside the HIGH set** {$0.0044–$0.0047}. So the named
alternatives produce **NOVEL**, not a false HIGH. **What is not excluded:** a
power shape with `a ≈ 0.74` at `KXMLBSPREAD` would put `S1` inside HIGH — and
**[COMPUTED]** it would simultaneously put `S3` at 33c on $0.0115, which is
NOVEL. **The pair catches it; neither cell alone does.** That is why `S3` is not
optional.

### Cost 4 — the schedule can no longer be held constant by the calendar, so it must be detected

Round two §8's no-rollover rule existed to hold the fee schedule constant
against round one. **Round three is on a later date by construction, so that
rule is unavailable and assumption B4 has no calendar to lean on.**

B4 is not hypothetical. **[CITED, `backend/core/fees.py:226-242`]** 55 settled
positions on this account show single-game fees at **whole cents** from 2025-11
through 2026-05, against **sub-cent** single-game fills on 2026-08-10. **The
schedule demonstrably moves.** Round two carried B4 with **no detector**.

**Cell `R` is the detector**, and it is mandatory. §1.5 states exactly what it
looks like if it fires.

### Cost 5 — H-SPORT loses its baseball/non-baseball falsifier unless the WNBA cell activates

`KXATPDOUBLES` is gone. The only non-baseball series in the record are WNBA,
NFL and NCAAF. Cell `W` recovers the arm **conditionally** (§1.3). If `W` does
not activate, H-SPORT and H-NOTIONAL and H-SERIES collapse onto the all-LOW
vector as a **three-way non-separation** — registered in §Power, not discovered
afterwards.

---

## §0.6 The decision this attribution governs

**[COMPUTED, `backend/core/fees.py` as deployed]** at 50c and `N = 1`,
`calculate_fee(500, 1)` returns **$0.0200** — CLAUDE.md's **52.00%** taker
bar. At the same point, `ceil(0.035 × 0.25)` to $0.0001 gives **$0.0088**, a
break-even of **50.88%**: a **1.12-point** move against **0.38 points** of
assumed headroom.

Round one cannot say **which markets, sizes and prices** the low rate applies
to. Three facts make that gap concrete rather than academic:

1. **[CITED, round-one result]** the pinned record is **73.0% `KXMLBGAME`,
   27.0% `KXWNBAGAME`**, and **`KXWNBAGAME` has zero fee observations** —
   while supplying **41% of the rows** that a naive `k = 0.035` would newly make
   positive. Cell `W` is the first fee observation ever taken there.
2. **[CITED, `backend/core/sizing.py:184`]** `contracts = int(stake // price)`,
   with `bankroll_dollars = 1000.0`, `kelly_fraction = 0.25`,
   `max_position_dollars = 100.0` (`backend/config.py:317-335`). **A real order
   from this tool is tens to hundreds of contracts**, while **every figure in
   ADR 0021 is computed at `E1`, one contract** (`sizing.py:156` prices at
   `contracts=1`). If H-SIZE is true with `c* ∈ (10, 20]`, the record is scored
   at the cheap rate and every real order pays the dear one. **Nothing in this
   project has ever measured whether those are the same rate.** Cell `S2` is the
   only affordable test of it (§C2).
3. **[CITED, round two §0.1]** the deployed bar is already implied wrong by
   round one. What is unknown is by how much, and where.

**Honest shape of the decision: no branch authorises a deploy.** Every branch
changes which follow-on registration is worth its money, and two branches
(H-SIZE, H-PRICE) would mean the rate governing the tool's own orders is **not**
the one round one measured — in the direction that makes the gate *harder* to
open, not easier. A measurement that can prevent a false opening is
decision-relevant. §7's consequence table fixes both directions before the
answer.

---

## §C. Corrections to the brief, made before the design was fixed

Five. Each changed the design; none was made after seeing a round-three number,
because none exists.

### C1. The brief proposes "recover the round-two design"; the round-two design cannot be recovered, and the part that can is not the part that mattered most

Round two §B5's arithmetic: the sub-15c band was carrying **three of the four**
ticket-side separations. Two of them — H-SIZE and H-PRICE — are recovered here
in `KXMLBSPREAD`. The third, **H-NOTIONAL's unique falsifier**, is **not**, and
it cannot be, at this budget: it needs a stake `≥ $3.00` at a price `≥ 27c`
(§C2), which is $3.10 minimum on its own. **H-NOTIONAL is registered without a
unique falsifier and joins the all-LOW residual.** Named now, at zero cost,
rather than at audit time.

### C2. Cell N is rejected, with the arithmetic, and the rejection is part of the registration

Round two §B7 registered **Cell N** — `C = 10`, 31–39c, stake $3.10–$3.90 — as
H-NOTIONAL's unique falsifier and as a "round-three nucleus". It is **rejected
here**, on three grounds fixed before any fill:

1. **[COMPUTED]** Cell N costs **$3.10–$3.90**, which is **76–96% of the whole
   authorisation** and would displace `S2` (the H-SIZE falsifier), `W` (the
   first WNBA observation) or `R` (the B4 detector). §B7 says so itself: *"Cell
   N alone consumes the whole ~$4 authorisation."*
2. **At the tool's own operating point H-NOTIONAL predicts LOW under every
   admissible `t`.** `t ∈ ($2.70, $3.00]` and the record is scored at `E1`,
   where the largest possible stake is **$0.99**. H-NOTIONAL cannot change a
   single figure in ADR 0021.
3. **The three cells that displace it can.** `W` changes how 27% of the record
   is priced; `S2` changes how every real order is priced; `R` decides whether
   round one transfers at all.

**This is a ranking, and it is registered so that it cannot be re-ranked after a
result.** If H-NOTIONAL survives the all-LOW branch, that is a *registered
residual*, not a discovery.

### C3. `KXWNBAGAME` cannot simply be added, because no census covers its band — so its cell is registered *conditionally*, on a query specified now

Constraint: every cell must cite a census number showing its band is fillable.
**The census covers `KXMLBGAME` and `KXMLBSPREAD`. It does not cover
`KXWNBAGAME`'s 27–39c band**, only its low band (1 event of 18).

Registering `W` unconditionally would repeat round two's exact defect one series
across. Registering it on "we'll look on the day" is the sentence this document
exists to prevent. **So the activation test is written now, in full, as a
read-only query whose inputs are prices and depths — quantities that are
independent of any fee by construction.** §1.3.

### C4. A point prediction at `a = 1` is an unregistered narrowing, and at the new prices it manufactures spurious NOVELs

Round two computed every prediction at the exact shape `P(1−P)`. Round one did
not establish `a = 1`; it established **`a ∈ (0.9816, 1.0361]`** with one degree
of freedom.

**[COMPUTED]** at `S2` = 7c, `C = 20`, the `a = 1` prediction is $0.0456 while
the round-one-admissible band is **$0.0438–$0.0466** — 29 grid units. Under
round two's rule, a true LOW fill at $0.0461 would be classified **NOVEL** and
would kill all five attributions **because of a shape exponent round one never
excluded.**

**Corrected: classification is by the ENVELOPE** — the union over the whole
round-one-admissible `(k, a)` region — with the `a = 1` **CENTRAL** value
reported beside it. Both are computed in §1.4 before any fill. The envelope is
never wider than a factor-of-two gap, so nothing is lost in discrimination
(§R2), and the CENTRAL-vs-observed difference becomes a **shape measurement**
(D-B2a) rather than a false alarm.

### C5. The replication cell is worth more at a *mid* price than at a low one, and the reason is arithmetic

The instinct is to replicate round one where the new cells sit. That is
backwards. **[COMPUTED]** the round-one anchors are at `P = 0.27` and
`P = 0.48`, so a replication inside **[27c, 52c]** is an **interpolation** of
the pinned power band and its envelope is **0–2 grid units wide**; a replication
at 7c is an extrapolation and its envelope is 3 grid units on a $0.0023
prediction — proportionally **ten times looser**.

**A tight detector must sit between the anchors.** `R`'s band is therefore
27–52c, and **[COMPUTED]** at **47c, 48c, 49c, 51c and 52c the CENTRAL LOW
prediction is exactly $0.0088 — bit-for-bit round one's F4 observation.** §3's
two-pass scan prefers that region for exactly this reason, and the preference is
mechanical and fee-independent.

---

## §P. Preconditions — checked before any comparison is made

Each is yes/no. If any is NO the run stops and this file is **amended by
appending**, never edited in place.

- **P1 — the fill record carries `fee_cost`, `count`, `price`, `is_taker`,
  `ticker`.** Established by round one. A missing field VOIDs the affected cell.
- **P2 — unit sanity, mechanical, on `S2` alone.** Interpret `S2`'s raw
  `fee_cost` as dollars, as cents and as centi-cents; retain each implying a fee
  in **[$0.001, $1.00]**. Exactly one survivor ⇒ that is the unit for all cells.
  Zero or more than one ⇒ **STOP — the unit is not identified.**
- **P3 — `is_taker` is true.** A maker fill **VOIDS the cell**; its fee is
  published anyway, labelled descriptive.
- **P4 — one fill row per order.** More than one ⇒ **VOID** (per-order vs
  per-fill is unresolvable here).
- **P5 — `count` reads exactly `N`.** The realised round-one failure: the app
  defaulted to buy-in-dollars and produced `count = 0.27`. Not the integer `N` ⇒
  **VOID**. §3 registers the pre-submit check that prevents it.
- **P6 — the observed price is inside the registered band and is not an excluded
  price.** Outside ⇒ **VOID**. Its fee is published anyway.
- **P7 — every earlier cell's recorded `fee_cost` is unchanged after every
  later order.** `S1` and `S2` normally share a market, and **[AUDITED]** 658 of
  695 simultaneous band pairs are the **same strike, opposite teams**, so `S1`
  and `S3` will frequently share an **event** as well — which widens the surface
  on which Kalshi could aggregate orders for fee purposes. If it did, an earlier
  cell's fee would move retroactively. **Re-read every prior cell's fee after
  the last order is placed, not just `S1`'s**; if any changed, **STOP THE
  LINE.** *(Extended from `S1`-only following the audit's within-event
  simultaneity finding. The wider check costs one extra read.)*
- **P8 — the market was pre-game at placement.** Recorded from the app (game not
  started, no score shown) **and** from the ticker's encoded start time. An
  in-play fill ⇒ **VOID**, per ADR 0006 and round two §B3(a): "price ≤ 15c" and
  "the game is in progress" must not be collinear in this design.
- **P9 — the ticker's series prefix matches the cell's registered series.**
  `R` → `KXMLBGAME`; `S1`, `S2`, `S3` → `KXMLBSPREAD`; `W` → the series the
  §1.3 query selected. Mismatch ⇒ **VOID**.
- **P10 — every void is recorded with its mechanical reason and its observed fee
  is published.** Every reason in P3–P9 is checkable **without looking at the
  fee value**, and publishing the fee of every voided cell removes the incentive
  to void one.

---

## §1. The question, as five claims that could be false

`LOW` means "the fee is a member of the cell's registered LOW **envelope** at
the observed price and count". `HIGH` means the same for the HIGH envelope. The
envelopes are fixed in §1.4 before any fill.

> **H-SERIES.** The rate is a per-series lookup. `KXMLBGAME → LOW`; every
> `KXMLBSPREAD` cell takes **the same value as every other `KXMLBSPREAD` cell**;
> other series unconstrained.
> *Falsifier: `R` returning anything but LOW; **or any disagreement among `S1`,
> `S2` and `S3`**; or any cell returning neither LOW nor HIGH.*

> **H-SPORT.** The rate is per sport. Baseball `→ LOW`, non-baseball `→ HIGH`.
> *Falsifier: any baseball cell HIGH, `W` LOW, or any cell returning neither.*

> **H-SIZE.** The rate is per order size. `C < 20 → LOW`, `C ≥ 20 → HIGH`, with
> the boundary `c* ∈ (10, 20]` pinned by round one.
> *Falsifier: a `C = 1` cell HIGH, `S2` LOW, or neither.*

> **H-PRICE.** The rate is a **monotone threshold on the traded price**,
> `P < b → HIGH`, `b ∈ (0.15, 0.27]`.
> *Falsifier: a cell at `P ≤ 0.15` returning LOW, a cell at `P ≥ 0.27` returning
> HIGH, or neither.*

> **H-NOTIONAL.** The rate is a threshold on order stake, `C·P ≥ t → HIGH`,
> `t ∈ ($2.70, $3.00]`.
> *Falsifier: any cell returning HIGH (**every** registered stake is `≤ $2.60`,
> so every registered cell predicts LOW). **It has no cell where it uniquely
> predicts HIGH** — §C2.*

> **H-NONE.** No member of the family above fits every non-void cell.
> **A first-class outcome.** §Power shows it occupies **26 of the 32** reachable
> vectors; §9 gives it a destination.

**Direction is one-sided and conjunctive for each claim**: an attribution is
declared only if **every** non-void cell matches its prediction exactly. No
claim here is "the rate is 0.035"; each is "this rule reproduced these cells".

### §1.1 The cells, fixed now

Bands are on **the price actually paid — the displayed ask you cross** — never a
mid. There is no sixth cell.

| Cell | Series | `N` | Band (ask) | Excluded | Max stake | Role |
|---|---|---:|---|---|---:|---|
| **R** | `KXMLBGAME` | **1** | **27–52c** | 30c, 40c, 50c | **$0.52** | B4 detector / replication |
| **S1** | `KXMLBSPREAD` | **1** | **6–15c** | 10c | **$0.15** | low price |
| **S2** | `KXMLBSPREAD`, same market as `S1` where possible | **20** | **6–13c** | 10c | **$2.60** | large size at a low price |
| **S3** | `KXMLBSPREAD` | **1** | **27–39c** | 30c | **$0.39** | within-series price control |
| **W** | `KXWNBAGAME` *(conditional — §1.3)* | **1** | **27–39c** | 30c | **$0.39** | non-baseball; first WNBA fee |

**Maximum stake $4.05. Maximum fees $0.2203. MAXIMUM LOSS $4.27.**
**At the §8 cap (one licensed re-attempt): $4.81.** §9 restates this where Joe
will see it.

### §1.2 Availability, per cell, with the citation — the guard round two did not run

**Every number below is from §0.4 and its audit. The census measures
AVAILABILITY, NOT FILL PROBABILITY: nothing in it says an order at 13c would
have filled** (§0.4e, §R6, §10). It says a displayed ask stood in the band with
displayed depth at that ask. That is the same quantity §3's placement rule keys
on, and it is the strongest thing available before a fill exists.

**This section is renamed from "Fillability" to "Availability" deliberately.**
The old title claimed the thing the census cannot deliver, and the design's
exposure has moved to exactly that thing.

**Every "100%" and "696" below means "at every polling instant on four
game-days" (§0.4a). None of them is a sample size.**

| Cell | Band is available because | Depth for `N` | When in the day |
|---|---|---|---|
| **R** | `KXMLBGAME` 27–39c available on **24 of 85 events**. The band 27–52c is a **superset**, so **≥ 24 of 85** is a hard lower bound. **[INFERENCE, not a per-event count]** each event lists two complementary YES markets (§B3(d)) and **99% of pre-game asks are ≥ 28.5c (p1)**, so the cheaper side of nearly every event sits inside 28.5–50c. | `N = 1`; **depth ≥1 NOT separately censused for `KXMLBGAME`, and not audited.** **Residual, named.** | **Not censused by time-of-day**, and the one adjacent audited figure is **adverse**: only **7%** of `KXMLBGAME` rows fall within 3h of first pitch, against 37.1% for the `KXMLBSPREAD` low band. **Residual, named**; §8's window and the NOT ATTEMPTED branch are the mitigations. |
| **S1** | `KXMLBSPREAD` 6–15c (excl 10c) available at **every pre-game polling instant on four game-days, across 40 distinct events**; min ask 7.0c; per-slate minima 9c/10c/8c/7c across four slates that agree. **[AUDITED]** in-band persistence poll-to-poll **99.7%**; ask unchanged in **98%** of consecutive pairs; 56 episodes with **median duration 569 minutes**. | **[AUDITED]** **98.23%** of low rows display **≥ 20** contracts, and at least one such market stood at **695 of 695** instants — so `N = 1` is certified with an enormous margin. | **[AUDITED — the gap the body used to name as `[NOT CENSUSED]`, now closed.]** **37.1%** of low rows are within 3h of first pitch, covering **30 of 55 events**; in **17:00–23:59 ET, 189 of 189** instants carried a qualifying low market, median **4** on the board. |
| **S2** | Same band citation as `S1`. `S2`'s 6–13c is a **subset**, and the audit certified the subset **directly** rather than inheriting it: **n = 2,725** rows at ≤ 13c. | **[AUDITED — this is the upgrade, and it removes the design's former weakest citation.]** at ≤ 13c, **97.32%** of rows display **≥ 20** contracts; the size distribution is p0 1, p1 2, p5 355, **p50 2,914**, and it is **bimodal** — under 10 or over 50, little between. Critically, **695 of 695** pre-game instants carried **at least one** qualifying low market with ≥ 20 displayed (min **2**, median **7**, max 15), so **the thin tail bites only an operator who fixes on one market instead of scanning** — which §3's scan rule already forbids. | as `S1`. **[AUDITED]** at depth ≥ 20 the within-3h share is **37.8%**; in 17:00–23:59 ET, **164 of 189 (87%)** instants carried a qualifying market at ≤ 13c. |
| **S3** | Exactly the censused band: 27–39c (excl 30c) available at **every pre-game polling instant, across 55 distinct events**. | depth ≥1 at every instant; median 4,624. | as `S1`. For the neighbouring shape (31–39c at depth ≥10) the census reports **26% of qualifying instants inside 3h of first pitch, covering 43 of 55 events**. |
| **`S1` + `S3` together** | **[AUDITED — strictly stronger than anything the body previously claimed.]** at **695 of 695** pre-game instants a single **EVENT** held one market in 6–15c and another in 27–39c at the **same `observed_ms`**, and **658** of those pairs are the **same strike, opposite teams**. Round two §B3(c) requires only the within-*series* pair; the record supplies the within-*event* pair. | as above. | as above. |
| **W** | **No citation exists.** `W` is placed **only if** the §1.3 query supplies one, at a threshold fixed below. | `N = 1`, required by the query. | required by the query. |

**Which citation is weakest now — corrected, because the old answer is no longer
true.** The body previously named `S2`'s depth at `N = 20` as *"the design's
weakest reachability claim"*. **That has been overturned by the audit**: it is
now among the strongest citations in the file, certified at the row level
(97.32% at ≤13c) and at the instant level (695 of 695, median 7 qualifying
markets). **The weakest availability citation is now `R`** — no depth citation
at all, no time-of-day citation, and the one adjacent audited figure running
against it. `R` is also the cell gate G1 makes fatal, which is why §8 gives it
first call on the single licensed re-attempt.

**And the weakest claim in the design is no longer an availability claim at
all.** It is **FILLABILITY** (§0.4e): every citation above is a *displayed* ask
and a *displayed* size, and no quote record distinguishes real resting size from
a maker who pulls on any incoming order. That residual is named in §10, ruled on
in §3, classified in §7.2, assumed as B9 in §11, and given a destination in §9.

**The named residuals — `R`'s per-event count above 39c and its uncensused depth
and time-of-day, and FILLABILITY at every cell — are the places this design
could still fail the way round two did.** They are written here, before the run,
so that a NOT ATTEMPTED or a DID NOT FILL on any of them is a predicted outcome
rather than a surprise.

### §1.3 Cell `W` — the activation query, specified in full, run before any order

Read-only, against data already stored. **Its inputs are prices, depths and
timestamps. It cannot see a fee.** It is the query round two §B6 registered as
free and never ran.

> **Q-W.** Window **2026-08-07 00:00Z to 2026-08-10 23:59Z** — the same window
> as §0.4's census. Series **`KXWNBAGAME`**. Pre-game filter: quote timestamp
> **< true start**, `true start = occurrence_datetime − 3h` (ADR 0006, validated
> there for WNBA game markets). Ask derived as **`1000 − no_bid_tenths`**, in
> tenths of a cent. Band **270 ≤ ask ≤ 390, excluding exactly 300**. Depth at
> that ask **≥ 1 contract**.
>
> **`W` ACTIVATES iff both hold:**
> **(i)** at **≥ 80%** of the distinct pre-game polling instants in the window,
> at least one market satisfies band-and-depth; **and**
> **(ii)** at least **8 distinct events** contribute such a market.
>
> If `KXWNBAGAME` fails, Q-W is repeated for **`KXWNBASPREAD`**, then
> **`KXWNBATOTAL`**, in that fixed order; the first series passing both becomes
> `W`'s series and the substitution is reported in the verdict line.
> If none passes, **`W` IS NOT REGISTERED**, is not placed, and §Power's
> four-cell enumeration governs.

**Why 80% and 8, chosen now and not after the query:** the `KXMLBSPREAD` cells
cite 100%; 80% is a deliberately weaker bar for a cheaper, coverage-motivated
cell. Eight events is roughly half the 18 WNBA events the record holds over the
window, which is this repo's standing "the parts must agree" requirement rather
than a pooled number.

**Q-W's output — the instant count, the percentage and the event count — is
published in §S whether or not `W` activates.** A failed activation is a
reachability finding about WNBA and is reported as one.

### §1.4 The predicted `fee_cost` for every cell at every legal price, to $0.0001

**[COMPUTED, `ceil` to $0.0001.]** Two sets per cell per price:

- **ENVELOPE** — the union over the whole round-one-admissible region: `u = k·s_a(0.27) ∈ (0.00689, 0.00690]` (from F2), `v = k·s_a(0.48) ∈ (0.0087, 0.0088]` (from F4), shape `s_a(P) = (P(1−P))^a`, `a ∈ (0.981593, 1.036131)`. **This is the classifier.**
- **CENTRAL** — round two's convention, `a = 1` exactly, `k_LOW ∈ (0.03495687, 0.03500761]` and `k_HIGH ∈ (0.06996078, 0.07000000]`. **Reported, never used to classify.** Where two values are listed the `k` interval straddles a grid boundary and **both are admissible**; a single point prediction would have manufactured a spurious mismatch.

`HIGH` is defined as **exactly twice the LOW raw at the same `(C, P, a, u)`**,
then ceiled. Registered as **B7** in §11: round one's `k_ATP ∈ (0.069961,
0.070000]` is contained in `2 × k_MLB ∈ (0.069914, 0.070015]`, so the doubling
convention is consistent with round one rather than assumed against it.

```
R    KXMLBGAME   C = 1   band 27-52c, excl 30c 40c 50c
  ask  stake |  CENTRAL LOW   CENTRAL HIGH |     ENV LOW        ENV HIGH
  27c   0.27 |       0.0069         0.0138 | 0.0069-0.0069   0.0138-0.0138
  28c   0.28 |       0.0071         0.0142 | 0.0071-0.0071   0.0141-0.0142
  29c   0.29 |  0.0072/0.0073        0.0145 | 0.0072-0.0073   0.0144-0.0145
  31c   0.31 |       0.0075         0.0150 | 0.0075-0.0076   0.0150-0.0151
  32c   0.32 |       0.0077         0.0153 | 0.0076-0.0077   0.0152-0.0153
  33c   0.33 |       0.0078         0.0155 | 0.0078-0.0078   0.0155-0.0156
  34c   0.34 |       0.0079    0.0157/0.0158 | 0.0079-0.0079  0.0157-0.0158
  35c   0.35 |       0.0080         0.0160 | 0.0080-0.0080   0.0159-0.0160
  36c   0.36 |       0.0081         0.0162 | 0.0081-0.0082   0.0161-0.0163
  37c   0.37 |       0.0082         0.0164 | 0.0082-0.0083   0.0163-0.0165
  38c   0.38 |       0.0083         0.0165 | 0.0083-0.0083   0.0165-0.0166
  39c   0.39 |       0.0084         0.0167 | 0.0083-0.0084   0.0166-0.0168
  41c   0.41 |       0.0085         0.0170 | 0.0085-0.0086   0.0169-0.0171
  42c   0.42 |       0.0086         0.0171 | 0.0085-0.0086   0.0170-0.0172
  43c   0.43 |       0.0086         0.0172 | 0.0086-0.0087   0.0171-0.0173
  44c   0.44 |       0.0087         0.0173 | 0.0086-0.0087   0.0172-0.0174
  45c   0.45 |       0.0087         0.0174 | 0.0087-0.0088   0.0173-0.0175
  46c   0.46 |       0.0087         0.0174 | 0.0087-0.0088   0.0174-0.0176
  47c   0.47 |       0.0088         0.0175 | 0.0087-0.0088   0.0174-0.0176
  48c   0.48 |       0.0088         0.0175 | 0.0087-0.0088   0.0174-0.0176
  49c   0.49 |       0.0088         0.0175 | 0.0088-0.0089   0.0175-0.0177
  51c   0.51 |       0.0088         0.0175 | 0.0088-0.0089   0.0175-0.0177
  52c   0.52 |       0.0088         0.0175 | 0.0087-0.0088   0.0174-0.0176

S1   KXMLBSPREAD  C = 1   band 6-15c, excl 10c
  ask  stake |  CENTRAL LOW   CENTRAL HIGH |     ENV LOW        ENV HIGH
   6c   0.06 |       0.0020         0.0040 | 0.0019-0.0021   0.0038-0.0041
   7c   0.07 |       0.0023         0.0046 | 0.0022-0.0024   0.0044-0.0047
   8c   0.08 |       0.0026         0.0052 | 0.0025-0.0027   0.0050-0.0053
   9c   0.09 |       0.0029         0.0058 | 0.0028-0.0030   0.0056-0.0059
  11c   0.11 |       0.0035         0.0069 | 0.0034-0.0035   0.0067-0.0070
  12c   0.12 |       0.0037         0.0074 | 0.0037-0.0038   0.0073-0.0075
  13c   0.13 |       0.0040         0.0080 | 0.0039-0.0040   0.0078-0.0080
  14c   0.14 |       0.0043         0.0085 | 0.0042-0.0043   0.0083-0.0086
  15c   0.15 |       0.0045         0.0090 | 0.0044-0.0045   0.0088-0.0090

S2   KXMLBSPREAD  C = 20  band 6-13c, excl 10c
  ask  stake |    CENTRAL LOW      CENTRAL HIGH |    ENV LOW        ENV HIGH
   6c   1.20 |         0.0395            0.0790 | 0.0377-0.0405   0.0754-0.0809
   7c   1.40 |         0.0456     0.0911/0.0912 | 0.0438-0.0466   0.0875-0.0931
   8c   1.60 |  0.0515/0.0516     0.1030/0.1031 | 0.0497-0.0525   0.0994-0.1050
   9c   1.80 |  0.0573/0.0574     0.1146/0.1147 | 0.0555-0.0583   0.1110-0.1166
  11c   2.20 |  0.0685/0.0686     0.1370/0.1371 | 0.0668-0.0695   0.1335-0.1389
  12c   2.40 |  0.0739/0.0740     0.1478/0.1479 | 0.0722-0.0748   0.1444-0.1496
  13c   2.60 |  0.0791/0.0792     0.1583/0.1584 | 0.0776-0.0800   0.1551-0.1600

S3 and W    C = 1   band 27-39c, excl 30c   (identical predictions; different series)
  ask  stake |  CENTRAL LOW   CENTRAL HIGH |     ENV LOW        ENV HIGH
  27c   0.27 |       0.0069         0.0138 | 0.0069-0.0069   0.0138-0.0138
  28c   0.28 |       0.0071         0.0142 | 0.0071-0.0071   0.0141-0.0142
  29c   0.29 |  0.0072/0.0073        0.0145 | 0.0072-0.0073   0.0144-0.0145
  31c   0.31 |       0.0075         0.0150 | 0.0075-0.0076   0.0150-0.0151
  32c   0.32 |       0.0077         0.0153 | 0.0076-0.0077   0.0152-0.0153
  33c   0.33 |       0.0078         0.0155 | 0.0078-0.0078   0.0155-0.0156
  34c   0.34 |       0.0079    0.0157/0.0158 | 0.0079-0.0079  0.0157-0.0158
  35c   0.35 |       0.0080         0.0160 | 0.0080-0.0080   0.0159-0.0160
  36c   0.36 |       0.0081         0.0162 | 0.0081-0.0082   0.0161-0.0163
  37c   0.37 |       0.0082         0.0164 | 0.0082-0.0083   0.0163-0.0165
  38c   0.38 |       0.0083         0.0165 | 0.0083-0.0083   0.0165-0.0166
  39c   0.39 |       0.0084         0.0167 | 0.0083-0.0084   0.0166-0.0168
```

**If a fill lands on a deci-cent price**, both envelopes are recomputed at the
observed price **by the same rule, with no re-derivation of the rule**. §R2
shows the two envelopes can never overlap at any tick.

**Bonus reading, registered now so it is not "discovered" later.** Every
two-valued CENTRAL cell narrows `k`, and every gap between an observed fee and
its CENTRAL value constrains `a`. Both are reported as **by-products, labelled
as such**, and may not be presented as a result of the round or used to declare
anything.

### §1.5 What cell `R` looks like if B4 fires — the four signatures, fixed in advance

**[COMPUTED across the whole 27–52c band]**

| observed at `R` | reading | verdict |
|---|---|---|
| inside the **ENV LOW** set ($0.0069–$0.0089) | round one's MLB rate, granularity and rounding all still hold at `KXMLBGAME`, `C = 1`, mid price | **B4 NOT DETECTED** — proceed to the attribution |
| inside the **ENV HIGH** set ($0.0138–$0.0177) | the `KXMLBGAME` rate has moved to the published sports coefficient | **B4-DETECTED (rate)** |
| exactly **$0.0100** | the pre-July **cent** granularity has returned, at `k = 0.035` | **B4-DETECTED (granularity)** |
| exactly **$0.0200** | the pre-July **cent** granularity has returned, at `k = 0.07` — the deployed `calculate_fee` model | **B4-DETECTED (granularity)** |
| anything else | unclassified | **B4-DETECTED (novel)** |

**[COMPUTED]** $0.0100 and $0.0200 lie outside **both** envelopes at every price
in `R`'s band (ENV LOW max $0.0089; ENV HIGH range $0.0138–$0.0177), so the two
cent reversions are uniquely identified and cannot be mistaken for either rate.

> **REGISTERED CONSEQUENCE.** If `R` is anything other than **B4 NOT DETECTED**,
> **no attribution is declared**, the verdict line reads
> **`B4-DETECTED — ATTRIBUTION NOT READ`** with the signature named, and every
> other cell's fee is published **descriptively only**. Round one's `k`
> intervals are the classifier for every other cell; if the schedule that
> produced them has moved, they are not a classifier any more, and the
> within-round contrasts may **not** be rescued by re-deriving LOW and HIGH from
> round three's own fills. That would be fitting after seeing the data.

**The exact quantifier, because it is weaker than it sounds.** `R` establishes
only that the schedule did not change **at `KXMLBGAME`, at `C = 1`, at a
mid price**. A change confined to large orders, to low prices, or to
`KXMLBSPREAD` would be **invisible at `R`**. §10 says so and §11 records it as
the residual on B4.

> **If `R` is VOID or NOT ATTEMPTED, no attribution is declared either.** The
> verdict is `PARTIAL — B4 UNDETECTED, ATTRIBUTION NOT READ`. `R` is the one
> cell whose absence kills the round, which is why §3 gives it the widest band
> and the first re-attempt.

### §1.6 The prediction matrix, fixed before any fill

|  | **R** (GAME, 1, 27–52c) | **S1** (SPREAD, 1, ≤15c) | **S2** (SPREAD, 20, ≤13c) | **S3** (SPREAD, 1, ≥27c) | **W** (WNBA, 1, ≥27c) |
|---|:--:|:--:|:--:|:--:|:--:|
| **H-SERIES** | LOW | *x* | *x* | *x* | *(free)* |
| **H-SPORT** | LOW | LOW | LOW | LOW | **HIGH** |
| **H-SIZE** | LOW | LOW | **HIGH** | LOW | LOW |
| **H-PRICE** | LOW | **HIGH** | **HIGH** | LOW | LOW |
| **H-NOTIONAL** | LOW | LOW | LOW | LOW | LOW |

*x* means "one common value, LOW or HIGH, the same at all three" — H-SERIES's
uniformity prediction (§0.5, Cost 1). It is a constraint, not a free pass.

**Every registered stake is `≤ $2.60 < $2.70 ≤ t`, so H-NOTIONAL predicts LOW
everywhere with no UNDETERMINED contingency** — a strict improvement on round
two's D2, which needed one at 14c.

---

## §2. The population, and the exclusions

**Included:** exactly the four or five registered orders, placed by hand in the
Kalshi app inside the window of §8.

**The dependent variable is `fee_cost`**, fixed at fill time by
`(price, count, taker/maker, series)` and by nothing else. It is **independent
of the game's result by construction** — the quantity is determined before the
game starts, and P8 requires the game not to have started. No exclusion in this
document references a game outcome, a settlement, a P&L or an edge, and none
could.

| Excluded | Why | Independent of the fee value? |
|---|---|---|
| `count != N` (P5) | the app's dollar mode produces a fractional count; the cell is not the registered cell | **Yes** — an integer comparison on the ticket |
| more than one fill row (P4) | per-order vs per-fill is unresolvable here | **Yes** — a row count |
| a maker fill (P3) | the maker multiplier is unobserved everywhere in this project | **Yes** — `is_taker` |
| a price outside the band or on an excluded price (P6) | the band is the registered cut | **Yes** — a price |
| a market whose series prefix is not the cell's (P9) | the series *is* the treatment for `R`, `S3` and `W` | **Yes** — a ticker prefix |
| an in-play fill (P8) | ADR 0006; and it would make "low price" collinear with "game in progress" (§B3(a)) | **Yes** — a clock and a scoreboard |

**Rules that must not be activated after the fact.** If the verdict is H-NONE,
the temptations will be to widen a band, re-read a voided cell, drop `W`, admit
a nearby `k`, or admit a shape outside the round-one power band. **All five are
forbidden.** The precedent is in this repo: a combo experiment pre-registered an
exclusion and the agent correctly refused to activate it when the sample turned
out too thin — possible only because the rule existed in writing first.

**Nothing observed here may be used to fit a new attribution in this document.**
If the verdict is H-NONE, the observed fees are a **hypothesis generator,
labelled as such**, and any sixth rule must be confirmed by a **new**
pre-registered set of fills before it is believed or deployed.

---

## §3. The unit of observation, the taker constraint, and the placement rules

**The unit is one order.** Not one contract and not one market. `S2`'s 20
contracts are **one** observation: one formula evaluation, and per-order scope
makes them mathematically inseparable. **The clustering variable is
`order_id`.** Any presentation of this round with `n = 24` is wrong; `n = 5`, or
`n = 4` if `W` does not activate.

`n = 5` is not a sample size in any statistical sense. §5 says why that is
appropriate and §7 says why no interval appears anywhere.

### Every fill is taker

Joe places a **limit buy at exactly the displayed ask**, quantity `N`, in a
market whose **displayed resting size at that ask is `≥ N`**. A marketable limit
crosses immediately and Joe is the taker. A maker fill voids the cell (P3).

### Choosing among candidate markets — round one's rule, kept, with `R`'s two-pass refinement

> Scan the app's list for the cell's series **in its default order, top to
> bottom**. Take the **first** market whose displayed ask lies inside the cell's
> band, is not an excluded price, whose displayed size at that ask is `≥ N`, and
> whose game **has not started**. Stop there. **No re-scanning, no comparison
> between candidates, no waiting for a better price.**

**Kept, not improved, on the substance** — it is already unbiased with respect
to the fee, and changing an anti-gaming rule between rounds is itself a degree
of freedom.

**`R` gets two passes, mechanical and fixed in advance (§C5):**

> **Pass 1** — scan for the first `KXMLBGAME` market with an ask in **47–52c**
> (excl 50c), size ≥ 1, game not started. **Pass 2** — only if a *full* Pass-1
> scan finds none: scan again for the first with an ask in **27–52c** (excl 30c,
> 40c, 50c). Pass 1 is preferred because at 47–52c the CENTRAL LOW prediction is
> exactly **$0.0088**, bit-for-bit round one's F4 observation, which is the
> tightest B4 detector available. **Which pass was used is reported.**

**If the displayed ask moves between reading it and submitting**, re-read; if
still in band, use it; if it has left the band, abandon that market and resume
the scan at the next one. **At most two abandonments per cell**; on the third
the cell is **NOT ATTEMPTED**. **[AUDITED]** this is expected to be rare rather
than routine — the ask is unchanged in **98%** of consecutive polls, a market in
band stays in band **99.7%** of the time poll-to-poll, the largest single move
observed was **2.0c**, and the median in-band episode ran **569 minutes**. The
limit stays at two abandonments regardless; the numbers are an expectation, not
a licence.

If a full scan finds no qualifying market, the cell is **NOT ATTEMPTED** and is
reported as such. **There is no substitute band.**

### The DID NOT FILL rule — registered now, because round two had none

A displayed ask with displayed size is **not** a fill, and §0.4e states the two
explanations no quote record can separate. This is the rule for the branch where
the second one is true.

> **After submitting, watch the order for 60 seconds.**
>
> - **It fills in full at `N`** — the normal path; the cell proceeds to P1–P10.
> - **It does not fill within 60 seconds — CANCEL IT.** The cell is reported as
>   **`NOT ATTEMPTED (DID NOT FILL)`**, is excluded from `C`, and **triggers the
>   coverage qualifier** exactly as any other NOT ATTEMPTED does (§7.2).
>   **Do not raise the limit price. Do not wait longer. Do not re-submit into
>   the same market.**
> - **It fills partially** — cancel the remainder immediately. `count != N`, so
>   the cell is **VOID under P5**, and its observed fee is published anyway
>   under P10. The partial fill is **not** topped up: a second fill for one cell
>   breaches P4 and the per-order fee scope.
>
> **Why 60 seconds, and why cancel rather than wait.** A marketable limit at the
> displayed ask crosses immediately when the size is real. One that does not has
> become a **resting maker order**, and a maker fill **VOIDS the cell under
> P3** — so waiting converts a clean NOT ATTEMPTED into a void, and waiting
> longer converts it into an unplanned maker experiment this round never
> registered and cannot classify.
>
> **An unfilled-and-cancelled submission risks no stake and pays no fee**, so it
> does **not** count against §8's 6-order / $4.57 cap. It **does** count as one
> of that cell's **two abandonments**, which is what bounds it. It cannot be
> walked toward a better price, because the scan resumes at the **next** market
> in the app's default order and never returns to a skipped one.

> **A `DID NOT FILL` is a RESULT, not a failure of the run — and it is the one
> observation this entire census cannot produce.** It is the direct separation
> of "real resting liquidity" from "a maker who pulls", at the exact price and
> the exact size the design cares about. §9 gives it a destination, and §S item
> 6 requires fill / no-fill to be reported **for every cell, in every branch**,
> including the branch where an attribution is declared cleanly.

### `S1` and `S3` in the same event is permitted, and is the expected case

**[AUDITED]** 658 of 695 simultaneous band pairs are the **same strike, opposite
teams** — a 15.0c ask on one side against a 32.0c ask on the other, both at
strike 3.5. Placing `S1` and `S3` on the two teams of one event is therefore
**permitted and expected**, and it is **not** the forbidden mirror: round two
§B3(d) forbids buying the **NO** leg, and establishes that the other team is a
**genuine YES at its own ask**, unambiguous under both readings of H-PRICE. Both
orders remain YES buys at displayed asks. P7 is extended to cover the
aggregation risk this creates.

**Recorded at placement, from the app, for every order:** ticker, series prefix,
side, displayed ask, displayed size at the ask, contracts, the app's displayed
estimated cost, the app's displayed fee if any, the timestamp, **the market's
scheduled first pitch**, and **the minutes remaining to it**. The last two are
required by §Operability and are not optional.

### Registered substitutions, mechanical and fixed in advance

- **`S1`/`S2` share a market** when the first qualifying `KXMLBSPREAD` market
  has an ask in **6–13c (excl 10c)** with displayed size **`≥ 21`**. If one full
  scan finds no such market, `S1` is placed in the first market qualifying for
  its own band (6–15c, excl 10c, size ≥ 1) and `S2` in the first qualifying for
  its own (6–13c, excl 10c, size ≥ 20). This costs only the price-identity
  between them and **must be reported**.
- **`W`'s series** is whichever of `KXWNBAGAME`, `KXWNBASPREAD`, `KXWNBATOTAL`
  the §1.3 query selected. **No other substitution is permitted**, and in
  particular **no NFL or NCAAF cell may be substituted for `W`** — neither is
  censused and neither was registered.
- **The mirror is forbidden for every cell.** Round two §C5 and §B3(d): a NO at
  12c leaves H-PRICE's prediction **undetermined**, and it is unnecessary
  because both teams are listed as separate YES markets at their own asks.

### The pre-submit check — mandatory, every order, no exceptions

Round one's first fill was destroyed by the app defaulting to a
dollar-denominated buy, producing `count = 0.27`. This is a known, realised
failure mode.

> **Before pressing submit, confirm all four on the ticket:**
> **(1)** the ticket says **"Limit order"** — not Market, not any
> dollars-to-spend mode;
> **(2)** the **shares / contracts field reads exactly `N`** — `1` for `R`,
> `S1`, `S3`, `W`; `20` for `S2` — as a whole number, not a dollar amount;
> **(3)** the **limit price equals the displayed ask exactly**;
> **(4)** the **estimated cost equals `N × ask` to the cent** — e.g. `1 × 48c`
> must read **$0.48**, and `20 × 8c` must read **$1.60**.
>
> If any of the four fails, **cancel the ticket and re-enter it.** A submitted
> order that fails check (2) is a **VOID cell**, not a data point.

Check (4) is the arithmetic cross-check that would have caught round one's
failure.

---

## §Operability — when in the day each band exists, and what Joe actually has to do

Required by the brief, because a price that exists only at 03:00 is not a cell.

**What is censused:** `KXMLBSPREAD`'s two bands stand at **every pre-game
polling instant on four game-days** — four game-days, not 696 independent
observations (§0.4a) — and for the neighbouring 31–39c/depth-≥10 shape, **26% of
qualifying instants fall inside the last 3h before first pitch, covering 43 of
55 events.**

**[AUDITED — this closes the gap the body previously carried as a named risk.]**
The time-of-day split of the **low** band, which was `[NOT CENSUSED]`, has been
measured:

- **37.1%** of low rows fall within 3h of first pitch (**37.8%** at depth ≥ 20),
  covering **30 of 55 events** — against `KXMLBGAME`'s **7%**.
- In **17:00–23:59 ET**, **189 of 189 instants** carried a qualifying low
  market, with a **median of 4** such markets on the board at once, and
  **164 of 189 (87%)** carried one at **≤ 13c**.

**So the evening is the good window, and it is the window Joe is awake in.** The
bands are not a 03:00 artefact, and the low band is not a morning artefact.

**What is still not censused, and is therefore a named risk:** any time-of-day
figure for `KXMLBGAME`'s tradeable band — and the one adjacent figure that does
exist is **adverse**, at **7%** of `KXMLBGAME` rows within 3h of first pitch.
**Cell `R` is the cell most exposed to the operator's clock**, and it is also
the cell gate G1 makes fatal.

**Registered placement window.** All orders in **one calendar date**, within
**120 minutes of the first order**, each in a market whose game **has not
started** (P8), and **preferably** — not mandatorily — inside the last 3h before
that market's first pitch, which is when the board is busiest and Joe is awake.
The 120-minute bound holds the schedule constant inside the round; the pre-game
requirement is ADR 0006.

**Five hand-placed orders, five four-point checks, one phone.** Round one placed
six in fourteen minutes. 120 minutes is not tight. **MLB and WNBA slates start
at similar local times, so `W` and the MLB cells can share one window;** if they
cannot on the day, `W` is placed inside the same 120 minutes at whatever
time-to-first-pitch its own market has, and that number is recorded.

**[AUDITED] The evening preference is now cited rather than assumed:** in
**17:00–23:59 ET** the low band was populated at **189 of 189 instants**, with a
median of 4 markets on the board and 87% of instants offering one at ≤ 13c.
**It stays a preference and does not become a requirement**, because `R` sits in
`KXMLBGAME`, whose time-of-day profile is uncensused and whose one adjacent
figure is adverse (7% within 3h). Making the evening mandatory could force `R`
into NOT ATTEMPTED, and gate G1 makes `R`'s absence fatal to the whole round.

---

## §4. The cut — bucket edges, fixed in advance

The bands in §1.1 **are** the cut and they are on the derived ask. They were
chosen before any fill, by five data-blind criteria in this order:

1. **`P ≤ 15c` for `S1`, `P ≤ 13c` for `S2`, `P ≥ 27c` for `R`, `S3`, `W`**, so
   H-PRICE's prediction is determined under **every** threshold consistent with
   round one. `b ∈ (0.15, 0.27]` strictly, so `P = 0.15 < b` always and
   `P = 0.27` is never `< b`. **The whole range 16c–26c is excluded** as the
   ambiguity window.
2. **`20 × P ≤ $2.60` for `S2`**, so H-NOTIONAL is determined LOW under every
   `t ∈ ($2.70, $3.00]` with no contingency.
3. **`R` inside [27c, 52c]**, so the shape translation from the round-one
   anchors is an interpolation and its envelope is 0–2 grid units (§C5).
   **[COMPUTED]** `P(1−P)` at 52c equals `P(1−P)` at 48c exactly, so the upper
   end is an anchor rather than an extrapolation.
4. **No exact landing on the $0.0001 grid** under either nominal rate at any
   whole cent in any band. **[COMPUTED]** at `C = 1` this happens at every
   multiple of 10c, and at `C = 20` at every multiple of 5c. That excludes
   **10c** from `S1`/`S2` and **30c, 40c, 50c** from `R`/`S3`/`W`. §R3.
5. **LOW and HIGH envelopes disjoint at every price in every band**, minimum
   separation **$0.0017 — 17 grid units** (`S1` at 6c). §R2.

**No band may be widened, narrowed, shifted or added after any fill is
observed.** Bucket boundaries are the richest source of unearned findings
precisely because so many of them are defensible.

---

## §5. The statistic, named as an estimator

**There is no estimator. This is not an inference.**

Each cell yields an **exact set-membership test in units of $0.0001** between
one observed value and two disjoint, deterministic prediction sets. The quantity
compared is a **charged fee**, not a sample mean, not a proportion, not a
difference of paired proportions. `sqrt(p(1-p)/n)` is correct for none of it and
appears nowhere.

What is being estimated: **nothing**. What is being *decided*: which of five
deterministic attribution rules Kalshi is applying — a model-selection question
with six answers, resolved by exact set membership.

**One grid unit outside both envelopes refutes the attribution for that cell.**
`FEE_MATCH_TOLERANCE_DOLLARS = 1e-9` (`core/fees.py:243`) is float noise and not
a business tolerance. The counterargument to recognise when it arrives — *"it is
only a hundredth of a cent"* — is answered by the fact that the two envelopes
are **17 to 751 grid units apart** at every registered price. **The envelope is
not a tolerance**; it is the set of values the round-one evidence actually
admits, computed in advance, and it may not be widened by one unit afterwards.

---

## §6. The extraction

1. Joe places the orders by hand, in the order **`S1`, `S2`, `S3`, `R`, `W`**,
   with at least **60 seconds** between `S1` and `S2`, recording the §3 fields
   at each placement.
2. An agent session pulls `/portfolio/fills`. **This document does not specify,
   own or modify that script.** `.dockerignore:59-61` excludes `scripts/*` from
   the deployed image, so the pull is a **laptop-only** step and must be
   scheduled with an agent session — the constraint Amendment A §A4 records.
   **No deploy, and no laptop step for Joe.**
3. `configure_logging()` **before** any client is constructed. `httpx` logs full
   request URLs at INFO and this repo has already put a working credential into
   a transcript that way.
4. The raw payload is cached to
   `docs/measurements/2026-08-XX-fee-rate-attribution-round-three-fills.json`,
   checked for and stripped of any credential before it is committed.

### §6.1 The balance channel — recoverable for `S2` only, and only as a cross-check

**[COMPUTED]** the in-app balance is displayed to the cent. The LOW/HIGH
difference in the total debit is:

```
S2   $0.035 - $0.079   RESOLVABLE at 2dp   e.g. at 8c: $1.6516 vs $1.7031
R    $0.007 - $0.009   NOT RESOLVABLE at 2dp
S1   $0.002 - $0.005   NOT RESOLVABLE
S3   $0.007 - $0.008   NOT RESOLVABLE
W    $0.007 - $0.008   NOT RESOLVABLE
```

> **Registered:** Joe records the displayed balance **verbatim, with every digit
> shown**, immediately before and immediately after **`S2` only**. This is a
> **cross-check on the API's `fee_cost`, never the measurement**; a disagreement
> is a STOP THE LINE about the instrument, not about the attribution. The
> reading is **VOID** if any other order, settlement or account movement occurs
> between the two readings — and because positions settle within ~24h and MLB
> games resolve through the day, **it is likely to be void and that is expected,
> not a failure.** If the app displays more than two decimals, the same reading
> is recorded for every cell.

### §6.2 The settlement capture — referenced, not duplicated

Amendment A §A5/§A8 owns round one's settlement question (whether
`/portfolio/settlements.fee_cost` is entry-only or lifetime, and therefore H4).
**This round does not test H4 and does not duplicate that capture.**

What it registers is a **durable substitute channel** for itself, because
`/portfolio/fills` has a retention window:

> Each round-three position's **settlement `fee_cost`** is captured after it
> settles and recorded beside `fee_observed` in §S item 4. If the fill-time
> capture is missed for a cell, the settlement `fee_cost` is that cell's
> registered substitute — **conditional on round one's §A5 capture returning
> `settlement fee_cost == fill-time fee`.** If §A5 comes back unequal, this
> substitution is **withdrawn** and any cell relying on it is VOID.

---

## §7. The decision rule, with the multiplicity already counted

### §7.1 The multiplicity count

**Cells read: 5** (4 if `W` does not activate). Comparisons: 5 cells × 2
envelopes = **10**. Attribution predictions evaluated: 5 × 5 = **25**, of which
one (`W` under H-SERIES) is free and three (`S1`, `S2`, `S3` under H-SERIES) are
a single joint uniformity constraint rather than three independent ones.

**No cell carries an interval, a standard error, a p-value or a significance
mark**, so no cell can produce a false finding by clearing a threshold, and the
family-wise error rate of this design is **empty rather than controlled**. The
rule is **conjunctive**: an attribution is declared only if it matches **every**
non-void cell, so **adding cells can only make declaration harder**.

**Is the record looked at more than once as it grows?** **No.** This
registration covers exactly the registered fills, read **once**, after all are
placed. There is no accumulating database and no always-valid boundary is
required. The 13.7% floor this repo measured applies to a threshold on a noisy
statistic re-evaluated against a growing record; this is not that.

**The multiplicity that does bite here is the reverse one**, and it is stated in
§Power: of the 32 reachable outcome vectors, **26 leave every attribution dead**.
That is the design's discriminating power and also its main risk.

### §7.2 The decision rule, verbatim

> **GUARDS FIRST.** Q-W, P1–P10 and R1–R7 are evaluated and printed **before any
> verdict**. If P2 (unit) or P7 (retroactive fee change) fails, the run reports
> **STOP THE LINE** with the failed precondition named and **no attribution is
> declared**. Voided cells (P3–P9) are excluded from every conjunction, are
> listed with their mechanical reason, and **their observed fee is published
> anyway**.
>
> **GATE G1 — THE SCHEDULE ANCHOR.** Cell `R` is classified first. If `R` is
> **VOID** or **NOT ATTEMPTED**, the verdict is
> **`PARTIAL — B4 UNDETECTED, ATTRIBUTION NOT READ`**. If `R` is classified
> anything other than **LOW**, the verdict is
> **`B4-DETECTED — ATTRIBUTION NOT READ`** with the §1.5 signature named. In
> both cases **no attribution is declared**, every other cell's fee is published
> descriptively, and **LOW and HIGH may not be re-derived from round three's own
> fills to rescue the round.**
>
> **Let `C` be the set of non-void, attempted cells.** For each cell in `C`,
> `fee_observed` is classified **LOW** if it is a member of that cell's
> registered **LOW envelope** at the observed price and count, **HIGH** if it is
> a member of the **HIGH envelope**, and **NOVEL** otherwise. The envelopes are
> those registered in §1.4, evaluated at the **observed** price; no envelope may
> be recomputed under a different rule, a different `k` interval or a different
> shape family.
>
> **A single NOVEL cell refutes all five attributions**, because every one of
> them predicts LOW or HIGH or nothing at every cell. Report the observed value,
> the implied rate interval `[fee − $0.0001, fee] / (C·P(1−P))` and the implied
> shape exponent, **both labelled hypothesis-generating**, and declare
> **H-NONE**.
>
> **H-SERIES DECLARED** iff `R` is LOW **and** `S1`, `S2`, `S3` (those present
> in `C`) all carry the **same** classification. `W` is free.
> **H-SPORT DECLARED** iff every cell in `C` matches: `R` LOW, `S1` LOW,
> `S2` LOW, `S3` LOW, `W` **HIGH**.
> **H-SIZE DECLARED** iff every cell in `C` matches: `R` LOW, `S1` LOW,
> `S2` **HIGH**, `S3` LOW, `W` LOW.
> **H-PRICE DECLARED** iff every cell in `C` matches: `R` LOW, `S1` **HIGH**,
> `S2` **HIGH**, `S3` LOW, `W` LOW.
> **H-NOTIONAL DECLARED** iff every cell in `C` matches: `R` LOW, `S1` LOW,
> `S2` LOW, `S3` LOW, `W` LOW.
> **H-NONE DECLARED** iff no attribution above is declared. **This is a
> first-class verdict, not a failure of the run.**
>
> **More than one attribution may be declared**, and where that happens the
> write-up must say so in the verdict line. The two known cases are
> `(R,S1,S2,S3,W) = (L,L,L,L,L)`, which declares **H-SERIES, H-NOTIONAL** and
> must be reported as
> **`H-SERIES / H-NOTIONAL — NOT SEPARATED BY THIS DESIGN`**, and
> `(L,L,L,L,H)`, which declares **H-SERIES, H-SPORT** and must be reported as
> **`H-SERIES / H-SPORT — NOT SEPARATED BY THIS DESIGN`**. Neither name may
> appear alone.
>
> **COVERAGE QUALIFIER, mandatory and mechanical.** A declaration is **FULL**
> only if `C` contains all five cells. If `W` did not activate, or any cell is
> VOID or NOT ATTEMPTED, the declaration is reported as
> **PARTIAL — CONSISTENT WITH, DOES NOT EXCLUDE**, and the write-up must name
> which attributions lost their falsifier. In particular: **without `W`,
> H-SPORT has no falsifier and joins the all-LOW residual**; **without `S2`,
> H-SIZE has none**; **without `S3`, H-PRICE cannot be separated from
> H-SERIES**; **without `S1`, neither H-PRICE nor H-SIZE has a low-price arm at
> all and the round has recovered nothing — and additionally, per §0.5.0, `S2`
> standing alone in `KXMLBSPREAD` is exactly the cell round two §B3(b) rejected,
> so a HIGH at `S2` without `S1` is ambiguous between H-SIZE and H-SERIES and
> NEITHER may be declared.**
>
> **NOT ATTEMPTED is not a void and not a failure.** A cell for which no
> qualifying market was found is reported as `NOT ATTEMPTED`, excluded from `C`,
> and triggers the coverage qualifier. **A cell whose order was submitted at a
> displayed ask with displayed size `≥ N` and did not fill within 60 seconds is
> reported as `NOT ATTEMPTED (DID NOT FILL)`** (§3), is likewise excluded from
> `C`, and **likewise triggers the coverage qualifier**. The two are recorded
> **distinctly**, because they mean different things: the first is a board that
> did not offer the band, the second is a board that displayed it and did not
> honour it. **`DID NOT FILL` must appear in the verdict line for every cell it
> applies to**, and §9 gives it its own destination whether or not an
> attribution is declared.
>
> **NO CELL, NO SUB-READING AND NO BY-PRODUCT** — including the `k`-narrowing,
> the shape-exponent diagnostic of §7.4 and the balance cross-check of §6.1 —
> **may substitute for the conjunction**, be reported as significant, or be
> described with any word implying a test.

### §7.3 Which outcomes declare, and which kill everything

**[COMPUTED — all 32 reachable LOW/HIGH vectors, `(R, S1, S2, S3, W)`]**

```
L L L L L    H-SERIES / H-NOTIONAL   (not separated)
L L L L H    H-SERIES / H-SPORT      (not separated)
L H H H L    H-SERIES                 alone
L H H H H    H-SERIES                 alone
L L H L L    H-SIZE                   alone
L H H L L    H-PRICE                  alone
--------------------------------------------------------
every other vector (26 of 32)         ALL FIVE DEAD
   of which R = HIGH (16 vectors)     B4-DETECTED, attribution not read
   of which R = LOW  (10 vectors)     genuine H-NONE
```

**Any NOVEL fee also kills all five.** Named in advance, that outcome means the
rate is set by something outside this family. The next candidates, registered
now so they are not invented afterwards:

- **A per-order minimum fee.** **Already disfavoured**: round one's accidental
  `C = 0.27` fill charged **$0.0019**, so any floor consistent with round one is
  `≤ $0.0019`, and no such floor lifts `S1`'s LOW envelope ($0.0019–$0.0045) to
  its HIGH value. A floor applying only to whole-contract orders would evade
  this — an epicycle, named rather than assumed away.
- **A liquidity, volume or maker-programme tier per market.**
- **A time-varying schedule** — which is why every order is inside 120 minutes,
  and why `R` exists at all.
- **A non-monotone price rule** (a band rather than a threshold), which H-PRICE
  as registered does not cover and §10 disclaims.
- **A shape at `KXMLBSPREAD` outside the round-one power family**, which §7.4
  diagnoses and §10 disclaims.

### §7.4 The three B2 detectors, registered as diagnostics and never as declarations

- **D-B2a — the envelope-vs-CENTRAL gap.** For every cell classified LOW or
  HIGH, report the observed fee beside its CENTRAL value and the implied shape
  exponent `a`. At `S2` the envelope is 28–49 grid units wide, so this is a
  genuine **1-degree-of-freedom shape reading at a new series and a new price
  region.** **By-product. Not a result of this round.**
- **D-B2b — the within-series `S1`/`S3` ratio.** In any branch where `S1` and
  `S3` carry the **same** classification, the implied
  `shape(P_S1)/shape(P_S3)` is computed with `k` free and compared to `P(1−P)`
  and to the round-one power band. This is the same 1-dof structure that killed
  five named shapes in round one, run for the first time in `KXMLBSPREAD`.
  **Unavailable in branches where the two differ**, and that unavailability must
  be stated rather than skipped.
- **D-B2c — NOVEL.** A fee outside both envelopes is where a broken shape
  surfaces, and it surfaces as **H-NONE**, not as a shape finding.

### §7.5 Consequences, fixed before the answer

| Verdict | What is built | What is killed |
|---|---|---|
| **`B4-DETECTED`** | Nothing. A **re-anchoring registration**: the round-one `k` intervals no longer describe today's schedule, so every downstream use of them — including the round-one result's step-1/step-2 decomposition — is suspended pending a fresh calibration. | The transfer of round one to any later date. This is the **most consequential** branch and the cheapest to reach. |
| **`H-SERIES / H-NOTIONAL` (not separated)** | Nothing. A follow-on registration for **Cell N** (`C = 10`, 31–39c, ~$3.50) which is H-NOTIONAL's unique falsifier, **and** a per-series measurement requirement. | H-SPORT (via `W` LOW), H-SIZE (via `S2` LOW), H-PRICE (via `S1` LOW). The reading that the tool's fee depends on order size or price **dies**, which is the outcome that most simplifies `calculate_fee`'s eventual replacement. |
| **`H-SERIES / H-SPORT` (not separated)** | Nothing. A registration for a **second baseball league** (`KXNPBGAME`, `KXLMBGAME`) and a third sport — the only way to separate them (round two §Power conclusion 2). | H-SIZE, H-PRICE, H-NOTIONAL. And **27% of the pinned record is priced at the dear rate**, which makes the gate harder to open, not easier. |
| **`H-SERIES` alone** (`S1`=`S2`=`S3`=HIGH) | Nothing. A **per-series measurement requirement before any new series is traded**, with its own registration. | The assumption that a rate measured on `KXMLBGAME` transfers to `KXMLBSPREAD` or `KXMLBTOTAL` — which the tool's own surfacing currently assumes. Operationally the most expensive outcome. |
| **`H-SIZE`** | Nothing. A registration mapping the boundary inside `[11, 20]`. | The assumption that ADR 0021's `E1` fee describes a real order. `sizing.py:184` yields tens to hundreds of contracts; every ADR 0021 figure is at one. **This branch says the record is scored at the wrong rate for the trades it implies.** |
| **`H-PRICE`** | Nothing. A registration mapping the boundary inside `(0.15, 0.27)`, **and** it must be re-established in `KXMLBGAME` if it can be (§0.5 Cost 2 / §B6). | The assumption that a rate measured at 27–48c transfers to longshot prices, where the fee is largest as a share of stake and where `suspicious_edge` and `edge_within_method_noise` bite. |
| **`H-NONE`** | Nothing. A new registration, and `core/fees.py`'s docstring annotated with what was observed. | The claim that the two rates are explained by any simple market attribute. |

**Is this decision-relevant, honestly?** Yes, and it is worth being blunt about
the shape: **no branch authorises a deploy.** Every branch changes which
follow-on registration is worth its money; three branches (`B4-DETECTED`,
H-SIZE, H-PRICE) would mean a number this project is currently relying on does
not describe the thing it is being applied to. A measurement that redirects the
next spend and can invalidate a pending inference is decision-relevant; one that
proceeds identically either way would not be, and this does not.

---

## §R. Reachability guards — arithmetic **and** instrument, before the data exists

Round two §B2 named the defect: *"a reachability guard must cover the instrument
as well as the arithmetic."* R1–R4 are the arithmetic; **R5–R7 are the
instrument, and they are the new half.**

### R1 — every declared outcome is attainable on the legal grid

**[COMPUTED]** every value in every envelope is an exact multiple of $0.0001 and
lies in `[$0.0019, $0.1600]`. Round one observed `fee_cost` values of $0.0019
and $0.1785 on this account, so both ends are demonstrably representable and
reportable. Every band is a contiguous run of whole cents inside 1–99;
deci-cents are handled by §1.4's recompute rule. **Each verdict is reachable by
some legal observation at every price Joe can trade in every band.**

### R2 — the falsifier of each declaration is reachable, at every tick including deci-cents

For any `(C, P)` the two candidate raw fees are `r` and `2r`, so the two
`ceil`-to-$0.0001 envelopes are separated by at least `r_min − $0.0001` where
`r_min` is the envelope's lower edge. **[COMPUTED]** the minimum separation over
every registered cell and whole-cent price is **$0.0017 — 17 grid units**
(`S1` at 6c), and the maximum is $0.0751 (`S2` at 13c). **The envelopes can
never overlap at any tick**, so LOW and HIGH are mutually falsifying everywhere
and neither can be true by construction.

### R3 — no cell lands exactly on the $0.0001 grid, in either direction

This is the round-one ATP trap, avoided by construction. **[COMPUTED]** at every
whole-cent price in every registered band, **neither** `0.035·C·P(1−P)` **nor**
`0.07·C·P(1−P)` is an exact multiple of $0.0001. The excluded prices — 10c for
`S1`/`S2`, and 30c, 40c, 50c for `R`/`S3`/`W` — are exactly the ones where that
fails. Consequence: **every cell re-tests `ceil` against `floor`, `half_up` and
`half_even` for free.**

### R4 — no cell can saturate

Each cell has exactly two candidate classes and they are disjoint (R2), so no
cell can return a value consistent with everything. The five cells partition the
family into six outcome classes and leave **26 of 32** vectors with an empty
class — the opposite failure mode from the ladder that returned 984 of 1,000.

### R5 — every band is AVAILABLE in the named series, with a cited number

**§1.2 is this guard.** It is the check round two's §R claimed to run and did
not. Each cell carries a census citation, and every one of them has now been
independently reproduced. `S2`'s depth at `N = 20` — previously the weakest
citation in the design — is certified at **97.32% of ≤13c rows** and at **695 of
695 instants** with a median of 7 qualifying markets on the board (§1.2). **The
weakest availability citation is now `R`**, which has none for depth and none
for time of day, and it is named as a residual rather than glossed.

**The guard is renamed from FILLABLE to AVAILABLE, because availability is what
it checks.** R6 is the other half, and R6 is **not satisfiable before a fill**.

### R6 — availability is not fill probability, and this gap is now the design's live exposure

**The census measures a displayed ask and a displayed depth at a polling
instant. It does not measure whether an order would have filled**, and no quote
record can: §0.4e shows real resting liquidity and a maker who pulls are
observationally identical in every column the record has. A marketable limit at
the displayed ask with displayed size `≥ N` is the strongest pre-registration
proxy available, and §3 keys the placement rule to exactly the quantity the
census measured.

**Two distinct residuals, separated here because the audit bounded one and could
not bound the other:**

1. **The ask vanishes between reading and submitting.** **[AUDITED]** now partly
   bounded: ask unchanged in **98%** of consecutive polls, in-band persistence
   **99.7%** poll-to-poll, median in-band episode **569 minutes**, largest single
   move **2.0c**. Handled by the two-abandonment rule. **Honest caveat carried
   straight from the audit: persistence is measured ON THE POLLING GRID, so an
   exit-and-return between polls is invisible, and every survival figure quoted
   anywhere in this file is an UPPER BOUND.**
2. **The displayed size is not real.** **Not bounded by anything, and not
   boundable before a fill.** Handled by the **DID NOT FILL rule** (§3), which
   converts it from an unhandled surprise into a registered outcome with a
   classification (§7.2) and a destination (§9).

**Round two failed at availability; round three's exposure has moved to
fillability.** R5 is now satisfiable and R6 is not, and that is the correct
statement of where this design stands.

### R7 — every band is reachable at a time a human can act

**§Operability is this guard, and the audit upgraded it.** `KXMLBSPREAD`'s bands
stand at every pre-game instant across four game-days. **[AUDITED]** the low
band was populated at **189 of 189 instants in 17:00–23:59 ET** — median 4
markets on the board, 87% of instants offering one at ≤ 13c — and **37.1%** of
low rows fall within 3h of first pitch across **30 of 55 events**. The
neighbouring 31–39c/depth-10 figure is 26% within 3h across 43 of 55 events.
**The time-of-day split of any `KXMLBGAME` band is still NOT CENSUSED, and the
one adjacent figure is adverse — 7% of `KXMLBGAME` rows within 3h.** So `R` is
the cell this guard covers least, and that is stated rather than assumed.

### R8 — the design's own falsifier exists

For **every** attribution there is at least one cell whose observation can
refute it, **with one registered exception: H-NOTIONAL has no cell where it
uniquely predicts HIGH** (§C2). It is refutable — any HIGH anywhere refutes it —
but it cannot be *separated* from H-SERIES on the all-LOW vector. **That is a
registered residual, not a discovery**, and §7.2 requires both names in the
verdict line.

---

## §Power — the check that comes before all of it

**Can five fills answer this question?** The question is selection among
deterministic rules with exact outputs, so the power currency is not an effect
size. It is **how much of the hypothesis space survives**.

### With `W` (5 cells, 32 vectors) — **[COMPUTED, full enumeration]**

```
                     vectors consistent
H-SERIES                   4 / 32     (LLLLL, LLLLH, LHHHL, LHHHH)
H-SPORT                    1 / 32     (LLLLH)
H-SIZE                     1 / 32     (LLHLL)
H-PRICE                    1 / 32     (LHHLL)
H-NOTIONAL                 1 / 32     (LLLLL)
no attribution            26 / 32     (16 of them B4-DETECTED)
```

### Without `W` (4 cells, 16 vectors) — the branch where Q-W fails

```
H-SERIES                   2 / 16     (LLLL, LHHH)
H-SPORT                    1 / 16     (LLLL)
H-SIZE                     1 / 16     (LLHL)
H-PRICE                    1 / 16     (LHHL)
H-NOTIONAL                 1 / 16     (LLLL)
no attribution            12 / 16     (8 of them B4-DETECTED)
```

**The all-LOW vector then declares three at once — H-SERIES, H-SPORT,
H-NOTIONAL — and must be reported as a three-way non-separation.** That is the
price of Q-W failing, quantified before the query is run.

### Five conclusions, all of which belong in the write-up before it is written

1. **H-SIZE, H-PRICE, H-SPORT and H-NOTIONAL are each pinned to a unique
   vector.** No outcome declares one of them alongside a rival except through
   H-SERIES.
2. **H-SERIES cannot be separated from H-SPORT or from H-NOTIONAL, and no
   affordable design can.** H-SERIES is saturated — one free parameter per
   series — so it is refutable only *within* a series. **The uniformity
   constraint (§0.5 Cost 1) is what keeps it at 4 of 32 rather than 8 of 16**,
   and that constraint exists only because three cells share `KXMLBSPREAD`.
3. **The measurement is far more likely to refute than to confirm** — 26 of 32
   vectors kill everything. That is a property of a sharp design, and §9 gives
   that branch the same destination as the others.
4. **Sixteen of the 32 vectors are `R = HIGH`, i.e. B4-DETECTED.** Half the
   outcome space is "the schedule moved and this round cannot read an
   attribution". **That is not a defect; it is the detector working**, and it is
   the half round two would have silently misread as an attribution.
5. **What this cannot do is resolve a rate at a price, size or series it did not
   trade.** The envelopes narrow `k` and constrain `a` as by-products which may
   not be reported as results. **At untested points the fee remains uncertain at
   the $0.0001 level in both directions, and there is no permanent gate
   accumulating coverage** — Amendment A §A3 established that `gate.py:636`
   reads `FROM fills`, that no production code writes that table, and that the
   MISMATCH branch is unreachable. Nothing here changes that.

> **Verdict of the power check: the design can answer the question it
> registers**, at **$4.27 maximum loss** ($4.81 at the §8 cap). It cannot say
> what Kalshi charges at every price and §1 does not claim to. It is **not
> UNDERPOWERED.** Its stated residuals are conclusions 2 and 4 and §R8.

---

## §8. The stopping rule, and the hard stop

**All registered orders in one window of at most 120 minutes, on one calendar
date, and that date is the first date on or after this file's commit on which
Joe places the first order.** Once the first order is placed the date is fixed
and **no order may be placed on any other date.**

- **Hard expiry: if no order is placed by 2026-08-31 (UTC), this registration
  expires UNRUN** and any later attempt is a new registration. A date, not "when
  we have enough".
- **The trigger is Joe's availability**, which cannot correlate with any fee
  value; and **Q-W must have been run and reported before the first order.**
- **No rollover across dates.** A cell not placed inside the window is
  **NOT ATTEMPTED**. Round two's no-rollover rule protected B4 by holding the
  calendar; here it protects the *within-round* comparison, and `R` protects the
  cross-round one.
- **At most one re-attempt, of one cell, and only for `R`, `S1`, `S3` or `W`**,
  permitted **only** when the cell was voided by a pre-submit-check failure or a
  mechanical precondition (P3–P9) — each checkable without looking at any fee
  value (P10). **`S2` gets no re-attempt**, because a second $2.60 order
  breaches the dollar cap. **`R` has first call on the re-attempt**, because G1
  makes its absence fatal.
- **Hard cap: 6 orders, $4.57 of stake.** After the cap, or at the end of the
  120-minute window, the run is closed and reported **whichever way it came
  out**.
- **An unfilled-and-cancelled submission is not an order for the purposes of
  this cap.** It risks no stake and pays no fee, so it cannot move the maximum
  loss (§3, the DID NOT FILL rule). It is bounded instead by the **two
  abandonments per cell** limit, and each try must be a *different* market taken
  further down the app's default order — the scan never returns to a skipped
  one, so it cannot be walked toward a better price.
- **A `DID NOT FILL` does not consume the single licensed re-attempt.** The
  re-attempt below is for cells lost to a **mechanical void** (P3–P9). A cell
  that did not fill has already used its two tries inside its own scan and is
  reported `NOT ATTEMPTED (DID NOT FILL)`.
- **The positions are held to settlement.** Not sold out — a sell fill's price
  cannot be fixed in advance, so it could not be a registered cell. If Joe sells
  any position for any reason, that sell fill is **not part of this
  registration**, its fee is reported descriptively, and it may not enter any
  conjunction.

### The hard stop, in the words it needs

Round one registered four fills and placed six. Both extras were informative,
**and that is exactly why the breach has to be named as a breach.** A protocol
whose violations turn out useful teaches the operator that violating it pays,
and the next unregistered fill will be placed in a market chosen after seeing
how the registered ones came out.

> **An order beyond the registered set (or beyond one licensed re-attempt) is a
> PROTOCOL BREACH, not a bonus data point.** If one occurs it is published under
> the heading **`UNREGISTERED — NOT PART OF ANY CONJUNCTION`**, it may not enter
> any declaration, it may not be cited for or against any attribution, and
> **the run's verdict line must read `BREACHED`** alongside whatever it
> declares. An unregistered fill that happens to be informative is worse than
> one that is not, because it is the one that gets quoted.

---

## §9. What would falsify this, and what happens then

### The result's destination, fixed now, before the result exists

- **Every branch**, including H-NONE, including `B4-DETECTED`, and including
  every PARTIAL, is written to
  **`docs/measurements/2026-08-XX-fee-rate-attribution-round-three-result.md`**,
  with the §S output in full.
- **`B4-DETECTED`:** that document, plus a re-anchoring registration, plus a
  note appended to the round-one *result* recording that its intervals have a
  measured expiry. **No edit to that result; a note.**
- **Any single attribution declared FULL:** that document, plus the follow-on
  registration named in §7.5 for that row.
- **`LLLLL` or `LLLLH`:** that document, plus the follow-on for the pair.
- **H-NONE:** that document, plus an annotation in `core/fees.py`'s docstring
  recording what was observed, plus a new registration if a sixth rule is to be
  pursued. **This branch has a destination, and it is the same destination as
  the others.**
- **`W` did not activate:** that document, **plus Q-W's output published as a
  reachability finding about `KXWNBAGAME` in its own right** — the second
  registered reachability result in this programme, and the first negative one
  that was predicted rather than discovered.
- **PARTIAL anything:** that document, naming which cell was lost and which
  attribution consequently has no falsifier.
- **Any `DID NOT FILL`:** that document, **plus a short fillability finding
  published in its own right**, naming the cell, the ticker, the displayed ask,
  the displayed size at that ask, and `N`. This is the observation no quote
  record can produce (§0.4e) and it addresses the design's named live exposure
  (§R6, B9). **It is written up whether or not an attribution is declared** —
  including in the branch where every other cell fills and the round declares
  cleanly. *A fillability result that only gets written when the round fails is
  a fillability result that has been selected.*
- **No `DID NOT FILL` anywhere:** that document records it explicitly —
  **filled at the displayed ask, `n` for `n`** — as a small, honest piece of
  evidence that displayed depth in these bands converts. **It is `n ≤ 5`, on one
  date, in two series, and the write-up must say so.** It may not be quoted as
  "the book is fillable", and it may not be cited by any later registration as
  establishing depth.

**A pre-registration whose negative branch has no destination produces a
negative result that quietly never gets written.** The negative branch here is
the most likely-shaped one (26 of 32 vectors) and it is named, dated and
addressed.

### What is explicitly not authorised, on any branch

**No deploy. No code change. `calculate_fee` is not touched and the `max()`
hedge stays.** `ORDERS_ARE_DRY_RUNS` stays `True`; ADR 0018 is untouched.
Replacing `calculate_fee` requires (a) a rate, (b) an attribution, (c) a
rounding rule, (d) a scope, (e) coverage of the maker path, and (f) its own ADR
and its own registration. **This round delivers at most one of the six.**

**And the favourable direction is the one that needs the most discipline.** §0.6
shows the plausible consequence is a break-even bar falling from 52.00% toward
~50.9%. A bar that moves *in your favour* is the one most worth
double-registering, because it retroactively rescues ADR 0021's refuted rows,
and **nothing in this repo should be rescued by five fills.**

### The consequence Joe should see before he acts

```
stake     R    $0.27 - $0.52
          S1   $0.06 - $0.15
          S2   $1.20 - $2.60      fees, high rate, all five:   <= $0.2203
          S3   $0.27 - $0.39
          W    $0.27 - $0.39      MAXIMUM LOSS, five orders:      $4.27
          ---------------------   MAXIMUM LOSS at the §8 cap:     $4.81
          TOTAL $2.07 - $4.05

          If W does not activate:  max stake $3.66, MAX LOSS $3.86 ($4.40 at cap)
          Likely stake, at the censused slate minima (7c-10c for S2):  ~$2.50
```

These are **real positions on real games**, not paper. All five can lose in
full. The maximum loss is stated because it is the number that should govern the
decision; **no expected-value estimate is offered**, because estimating one
would require a view on the games and this design has none.

**The audit did not move these figures.** No band moved, no cell was added or
removed, and an order that is submitted, does not fill and is cancelled risks no
stake and pays no fee — so the DID NOT FILL rule cannot increase the maximum
loss in any branch.

**This exceeds the ~$4 previously authorised.** It needs a fresh authorisation
of **$5.00**. The overrun is $0.81 at the cap and it buys cell `W` — the first
fee observation in a category that is 27% of the record.

---

## §10. What this measurement cannot establish — drafted before the run

Drafted now, because caveats written afterwards are selected to be survivable.

- **It cannot separate H-SERIES from H-SPORT, or H-SERIES from H-NOTIONAL.**
  §Power conclusion 2. `LLLLH` declares the first pair, `LLLLL` the second, and
  the write-up must name both members. Separating them needs a second baseball
  league and a third sport, neither of which is in this round.
- **It does not establish H-PRICE in `KXMLBGAME`, which is 73.0% of the pinned
  record.** It establishes it in `KXMLBSPREAD` and transfers it **only under
  H-PRICE's own claim to be a global rule about price** (B8). Round two §B6
  registered that transfer as an assumption and it is one here.
- **`R` does not establish that the fee schedule is unchanged.** It establishes
  that it is unchanged **at `KXMLBGAME`, `C = 1`, 27–52c**. A change confined to
  large orders, to low prices, or to `KXMLBSPREAD` is **invisible at `R`** — and
  such a change is *indistinguishable from an attribution* by this design. **This
  is the caveat most likely to overturn the result and it is new to this round.**
- **It does not test the functional form outside a power of `P(1−P)`.** The
  envelope covers `a ∈ (0.9816, 1.0361]` — the round-one power band, measured at
  **two prices in one series with one degree of freedom.** A shape outside that
  family at `KXMLBSPREAD` or `KXWNBA*` would appear as H-NONE, not as a shape
  finding. **At `S2` the shape uncertainty is 28–49 grid units wide**, which is
  the largest single source of imprecision anywhere in the design.
- **It does not test H-NOTIONAL's positive prediction.** No registered stake
  reaches $3.00, so H-NOTIONAL is only ever refuted by someone *else's* HIGH.
  §C2 is the arithmetic and the ranking; Cell N remains unrun.
- **It does not establish the rate at any price it did not trade.** Two regions:
  `≤ 15c` and `27–52c`. Nothing at 16–26c — deliberately, that is H-PRICE's
  ambiguity window — and nothing above 52c except by the shape's symmetry, which
  this round does not re-test.
- **It does not establish the rate at any size it did not trade.** Two sizes, 1
  and 20. Nothing at 2–19 or above 20. If H-SIZE is declared, the boundary is
  known only to lie in `[11, 20]`.
- **It does not test the rounding rule as a primary claim.** R3 makes every cell
  carry rounding information, but `ceil`-to-$0.0001 is an *input* taken from
  round one's 20-cell census — a census that round one's own result records as
  **oversold**: 16 of the 20 die on representability of `$0.0019` alone.
- **It does not cover non-monotone price rules.** H-PRICE is a monotone
  threshold. "The high rate applies in a *band* of prices" fits round one, is not
  tested, and would appear as H-NONE.
- **It does not establish the maker rate at all.** Every cell is taker; P3 voids
  a maker fill. `MAKER_COEFFICIENT = 0.0175` and `SPORTS_MAKER_MULTIPLIER =
  0.015` remain untested everywhere in this project.
- **It says nothing about combos.** `KXMVE` fees are charged to the tenth of a
  cent (`core/fees.py:227-234`) — a different grid.
- **It says nothing about tennis, NFL, NCAAF, soccer or esports.** Round two's
  ATP arm is gone and is not replaced. `W` is one basketball series, and one
  cell in it. Pooling across categories is forbidden.
- **It does not test H4 / settlement.** That is Amendment A §A5/§A8, referenced
  and not duplicated (§6.2).
- **The census it relies on was not re-run by this lane.** §0.4's numbers are
  cited, not verified here (B6). §S requires them reproduced in the result
  document.
- **The census measures availability, not fill probability, and that gap is now
  the design's live exposure.** **Round two failed at AVAILABILITY; round
  three's exposure has moved to FILLABILITY. This census reduces the first to
  near zero and says nothing whatsoever about the second.** Two explanations fit
  every observation in the record — real resting liquidity, and a maker quoting
  2,914 contracts at 13c who pulls on any incoming order — and **nothing in a
  quote record separates them.** The separating observation is one small order.
  §0.4e, §R6, B9, and the DID NOT FILL rule in §3.
- **Every stability and survival figure in this file is an UPPER BOUND.**
  In-band persistence (99.7%), ask stability (98%) and episode duration (median
  569 minutes) are measured **on the polling grid**, so an exit-and-return
  between two polls is invisible to all three. None of them is a guarantee about
  any moment on the run date.
- **`KXMLBSPREAD` was selected from a scan of 11 series, and it is not the
  availability maximum.** `KXMLBTEAMTOTAL` reaches the low band at 691 of 696
  instants from 50 events, against `KXMLBSPREAD`'s 40, at a lower floor (5.0c
  against 7.0c) and with 8,292 low observations against 5,039. The registered
  selection criterion is **"the series that was independently audited"**
  (§0.4c) — blind to the dependent variable, which does not exist at any
  candidate — but a series chosen as one of 11 still carries **optimistically
  selected availability** (B10). A future round may use `KXMLBTEAMTOTAL` after
  an equivalent audit; **this one may not, on any branch.**
- **The pre-game boundary in `KXMLBSPREAD` is validated by TRANSFER, not
  directly.** The series has **zero** sportsbook-linked events, so the
  independent-clock check cannot run on it at all. The boundary is inherited
  from the `KXMLBGAME` twin — identical `commence_ms` on 55 of 55 events, 47 of
  them sportsbook-validated at `commence − 3h`, and 0 of 47 validating
  `commence` as-is — and cross-checked against the ticker-embedded ET hour on 55
  of 55. **That is an INFERENCE, labelled.** It puts the census at risk and not
  the fills, because P8 is operator-side and does not use it (§0.4b).
- **The census `n` is four game-days, not 696 instants.** 696 polling instants
  is **uptime**: 261 sessions at a >5-minute gap split, **64% of them from a
  single observation day**. The independent units are **4 game-days, 55 events,
  330 pre-game markets, 45 markets that ever supplied a low ask, and 56 low-band
  episodes.** Concentration is good — largest market 8.1% of low rows, largest
  event 9.2%, all four slates contributing — and it is still four days.
  **No figure in this file is a sample size** (§0.4a).
- **One week of one August.** Four game-days, 2026-08-07 to 2026-08-10, in the
  densest month of the MLB calendar. **Nothing here speaks to September, to a
  thin slate, to a doubleheader day, to the postseason, or to any other month.**
  The bands' availability is a fact about four days in August; its transfer to
  the run date is an assumption bounded only by §8's hard expiry of 2026-08-31.
- **The sub-10c region is thinly evidenced.** Only 3 markets and 3 events ever
  printed below 10c, and 22 of the 307 sub-10c rows come from one market. **No
  registered band leans on it** (§0.4d): a sub-10c fill is legal and
  classifiable, and a sub-10c cell's shape by-product is the most extrapolated
  reading in the file and must be labelled as such.
- **`n = 5`.** Five orders, one account, one venue, one 120-minute window. Not a
  sample of anything. **No interval appears in this design and none may be added
  to the result.** Every interval quoted is a deterministic consistency set
  implied by integer-grid rounding, not a sampling interval.
- **It says nothing about whether an edge exists at Kalshi.** ADR 0021 §1's
  forbidden sentence is forbidden here too. Attributing the fee changes the
  *bar*; it does not create anything that clears it.

---

## §11. Assumed inputs, counted

- **B1 [ASSUMED].** Round one's `(ceil, $0.0001)` pair and the anchor fees F1,
  F2, F4 are correct as licensed. **Detector:** a NOVEL classification on any
  cell.
- **B2 [ASSUMED].** The fee shape at `KXMLBSPREAD` and `KXWNBA*` is a power of
  `P(1−P)` with exponent inside round one's `KXMLBGAME` band. **Detectors:**
  D-B2a, D-B2b, D-B2c (§7.4). **Partially detected, not assumed away** — the
  improvement over round two, which had none.
- **B3 [ASSUMED].** The fee is charged at fill time, once per order, and does
  not change afterwards. **Detector:** P7.
- **B4 [ASSUMED].** Kalshi's fee schedule is unchanged between round one's fills
  and round three's. **Detector: cell `R` and gate G1** — the second improvement
  over round two, which had none. **Residual:** `R` sees only
  `KXMLBGAME`, `C = 1`, mid price (§10).
- **B5 [ASSUMED].** An order Joe places by hand appears on `/portfolio/fills`
  for the account the API key addresses. **Detector:** fill count must equal
  order count; a mismatch is a STOP THE LINE naming the harness, not the
  exchange.
- **B6 [PARTLY DISCHARGED — was ASSUMED].** §0.4's census is correct. **An
  independent `measurement-skeptic` lane exported the live database and
  re-derived every headline figure without reading the census scripts; all
  reproduced exactly** (SURVIVES WITH QUALIFICATION). What remains assumed is
  **not the arithmetic** but the **transfer**: that four game-days in August 2026
  describe the run date (§10). **Detector, partial:** a NOT ATTEMPTED on a fully
  censused band would falsify the transfer. **Not detected:** a census correct on
  those four days and unrepresentative of the run date in the same direction.
- **B7 [ASSUMED].** `HIGH = exactly 2 × LOW` at the same `(C, P, shape)`.
  **Support:** round one's `k_ATP ∈ (0.069961, 0.070000]` is contained in
  `2 × k_MLB ∈ (0.069914, 0.070015]`. **Detector:** a fee between the envelopes
  classifies NOVEL.
- **B8 [ASSUMED].** H-PRICE, if declared at `KXMLBSPREAD`, transfers to
  `KXMLBGAME` — i.e. H-PRICE is what it claims to be, a rule about price rather
  than about a series. **Detector: none in this round.** Named in §10 and in
  §0.5 Cost 2.

- **B9 [ASSUMED].** **Displayed depth converts to a fill at `N`.** Round two
  never had to make this assumption, because round two never reached a band that
  was displayed at all. It is **not testable by any quote record** (§0.4e).
  **Detector: the run itself** — the DID NOT FILL rule (§3) makes every cell a
  direct one-order test of it, reported in §S item 6 in every branch.
  **Residual:** five orders is five observations of fillability, at one venue, in
  two series, on one date. **This is the design's named live exposure.**
- **B10 [ASSUMED].** `KXMLBSPREAD`'s availability — selected as one of 11 scanned
  series and measured on four game-days in August — holds on the run date.
  **Detector, partial:** NOT ATTEMPTED. **Residual:** selection across 11 series
  biases the winner's availability upward; partly mitigated by the audit's
  finding that `KXMLBSPREAD` is **not** the availability maximum (§0.4c), and not
  eliminated by it.

**Count of assumed inputs: 10**, of which B6 is partly discharged by the audit,
leaving nine live. Round two carried 5. Five of the new ones (B6, B7, B8, B9,
B10) were implicit there and are made explicit here; two of round two's
undetected assumptions (B2, B4) now carry detectors; and **B9 — fillability — is
the one this round can neither assume away nor fully detect, which is why it is
named in §10 and in the verdict rather than left in a footnote.**

---

## §S. Required output of the run, in this order

1. **Q-W's full output** — instant count, percentage, event count, per series
   tried — and whether `W` activated. **Published whether or not it did.**
2. §0.4's census numbers **reproduced from the record by the analysing session**,
   not restated from this file (B6) — **with the independent-unit accounting of
   §0.4a printed beside them**: game-days, events, pre-game markets,
   low-supplying markets and episodes. **The result document may not print 696
   without printing "4 game-days" next to it.**
3. Preconditions P1–P10, each with its yes/no and its evidence.
4. Reachability guards R1–R8, printed **before** any verdict.
5. **Gate G1's outcome**, with `R`'s §1.5 signature named.
6. **The per-cell table**: cell, ticker, series prefix, side, observed price,
   **displayed size at the ask at submit**, `count`, `is_taker`, notional,
   minutes to first pitch, **FILLED / PARTIAL / DID NOT FILL with the seconds to
   fill**, `fee_observed`, registered LOW envelope, registered HIGH envelope,
   CENTRAL value, classification (LOW / HIGH / NOVEL), VOID or NOT ATTEMPTED
   with reason, and the settlement `fee_cost` once available. **Every cell
   appears — including voided ones and unfilled ones — with its observed fee.**
   **The fill column is reported in every branch**, including the branch where
   an attribution is declared cleanly (§9).
7. The five-row attribution table: for each of H-SERIES, H-SPORT, H-SIZE,
   H-PRICE, H-NOTIONAL — its prediction per cell, and DECLARED or REFUTED with
   the cell that refuted it named.
8. The verdict line, including `BREACHED` if §8 was breached, the `W`
   substitution flag, which `R` pass was used, and the verbatim
   `H-SERIES / H-SPORT — NOT SEPARATED BY THIS DESIGN` or
   `H-SERIES / H-NOTIONAL — NOT SEPARATED BY THIS DESIGN` where they apply.
9. The coverage qualifier: FULL or PARTIAL, and for PARTIAL, which attribution
   lost its falsifier.
10. The in-app displayed fee for each order beside the API value. A disagreement
    is a STOP THE LINE about the instrument.
11. The `S2` balance-before/after reading (§6.1), or the statement that it was
    void and why.
12. The three B2 diagnostics of §7.4 as **by-products, labelled as such**, with
    the sentence that they are not a result of this round.
13. The narrowed `k` interval and the constrained shape exponent as
    **by-products, labelled as such**.
14. Total stake, total fees paid, and total realised P&L — reported for honesty
    and **explicitly not evidence of anything** about edge, at `n = 5`.
15. The §10 list, reproduced unedited.

---

## §V. Verdict at registration

> **READY.** Every section is fixed. No section was left open on the grounds
> that we would see what the data looks like.
>
> Five cells, five bands, three series, every prediction computed to $0.0001
> before any fill exists — as **envelopes over the round-one-admissible
> `(k, a)` region**, not as point predictions at an exponent round one never
> established. LOW and HIGH are disjoint by at least 17 grid units at every
> tick. No cell lands on the $0.0001 grid, so round one's ATP trap is avoided by
> construction. **Every band carries an availability citation at the size it
> needs.** Twenty-six of thirty-two outcome vectors kill every attribution, and
> that branch has the same destination as the others. The stopping rule is a
> 120-minute window, a calendar date, an order count, a dollar cap and a hard
> expiry of 2026-08-31.
>
> **The census this design rests on has been independently reproduced** from a
> raw export of the live database by a `measurement-skeptic` lane that derived
> every figure itself: **SURVIVES WITH QUALIFICATION**, every headline number
> exact. The design's former weakest citation — `S2`'s depth at `N = 20` — is
> now among its strongest: **97.32%** of ≤13c rows display ≥20 contracts, and
> **695 of 695** instants carried at least one such market, median 7 on the
> board. Simultaneity is **within-EVENT**, 658 of 695 pairs being the same
> strike on opposite teams. The low band was populated at **189 of 189 instants
> in the 17:00–23:59 ET window Joe actually trades in.**
>
> **Round two failed at AVAILABILITY. Round three's exposure has moved to
> FILLABILITY, and that is the honest statement of this registration.** The
> census reduces the first to near zero and says nothing at all about the
> second: real resting liquidity and a maker who pulls on any incoming order are
> observationally identical in every column a quote record has. The separating
> observation is one small order, which is what this round places — so the
> exposure is **self-reporting**, and §3's DID NOT FILL rule, §7.2's
> classification, §11's B9 and §9's destination are registered for it before it
> can be discovered.
>
> **Round two §B3(b) rejected a `KXMLBSPREAD` cell by name, and §0.5.0 answers
> the rejection rather than stepping over it.** §B3(b) rejects a *lone* `C = 20`
> cell in an unseen series; a per-series lookup cannot return three values for
> one key, so with `S1`, `S2` and `S3` in one series H-SERIES predicts
> uniformity and is refuted by the same observation that declares H-SIZE. This
> is §B3(c)'s accepted within-series pairing, applied to size instead of price.
> **The rebuttal rescues the pair and not a lone cell**, and §7.2 now says so:
> without `S1`, a HIGH at `S2` declares nothing.
>
> The two assumptions round two carried **undetected** — the shape at an
> unshape-tested series, and the fee schedule moving between rounds — now carry
> **detectors**: the envelope classifier with the `S1`/`S3` ratio, and cell `R`
> behind gate G1.
>
> **What is registered as still weak, in order.** **(1)** Fillability at every
> cell (B9), which no census can close. **(2)** Cell `R` — no depth citation, no
> time-of-day citation, an adverse adjacent figure of 7% within 3h, and gate G1
> making its absence fatal. **(3)** The transfer of four August game-days to the
> run date (B6, B10) — **the census `n` is 4 game-days, 55 events and 56
> low-band episodes, never 696**, and every stability figure in it is an upper
> bound measured on the polling grid. **(4)** The selection of `KXMLBSPREAD`
> from an 11-series scan, on the registered criterion that it is the audited one.
> **(5)** The pre-game boundary in that series, validated by transfer from its
> `KXMLBGAME` twin rather than measured. And the residuals no design at this
> budget removes: H-SERIES against H-SPORT and against H-NOTIONAL, H-NOTIONAL's
> missing positive falsifier, and B8's untestable transfer of H-PRICE from
> `KXMLBSPREAD` to `KXMLBGAME`.
>
> **Maximum loss: $4.27 for five orders, $4.81 at the §8 cap.**
> **$3.86 / $4.40 if `W` does not activate.**
> **Requires a fresh authorisation of $5.00.**
> **Unchanged by this revision:** no band moved, no cell was added or removed,
> no price was excluded or admitted, and an unfilled-and-cancelled submission
> risks no stake and pays no fee.

---

## Registration record

| Field | Value |
|---|---|
| Registered | 2026-08-10 (UTC) |
| Registered by | `pre-registrar`, on behalf of Joe |
| Round-three fills at registration time | **0** |
| Cells | **5** (4 if Q-W fails) |
| Sizes | 1, 20 |
| Bands | 27–52c (excl. 30c/40c/50c); 6–15c (excl. 10c); 6–13c (excl. 10c); 27–39c (excl. 30c) × 2 |
| Series | `KXMLBGAME` × 1, `KXMLBSPREAD` × 3, `KXWNBA*` × 1 (conditional) |
| Attributions under test | 5 + H-NONE |
| Classifier | **ENVELOPE** over round-one-admissible `(k, a)`; CENTRAL reported |
| Mirror | **Forbidden for every cell** |
| Max stake | $4.05 (five orders) / $4.57 (§8 cap) |
| Max loss incl. fees | **$4.27 / $4.81** |
| Hard expiry | **2026-08-31 (UTC)**, unrun |
| Deploy required | **None** |
| Code change authorised | **None.** `calculate_fee` untouched; `max()` hedge stays; `ORDERS_ARE_DRY_RUNS` stays `True` |
| Independent audit | `measurement-skeptic`, 2026-08-10 — raw export of the live DB, own derivation, census scripts not read for their numbers. **SURVIVES WITH QUALIFICATION**; every headline number exact |
| Census `n`, honestly | **4 game-days, 55 events, 330 pre-game markets, 45 low-supplying markets, 56 low-band episodes** — never 696 |
| Named live exposure | **FILLABILITY** (B9). Availability is closed; fillability is not, and no quote record can close it |
| Series selection | `KXMLBSPREAD`, from an 11-series scan, on the registered criterion **"the series that was independently audited"**. `KXMLBTEAMTOTAL` is the designated successor, after an equivalent audit |
| Revisions | **one, in place, 2026-08-10, before commit, at 0 fills**, folding in the audit. **Amend-by-appending applies from this file's commit onward** |
| Amendments | none |

---

## Appendix — the placement card

Five orders. Nothing else. Read the four-point check before every submit.

> **CHECK, EVERY ORDER:** Limit order · shares field reads exactly the number
> below · limit price = displayed ask · estimated cost = shares × ask ·
> **the game has not started.**

> **AFTER EVERY SUBMIT — watch it for 60 seconds.**
> **Filled in full?** Good, move on.
> **Not filled in 60 seconds? CANCEL IT.** That cell is `DID NOT FILL`. **Do not
> raise the price, do not wait longer, do not re-submit into that market.** Go
> to the next order. *A cell that does not fill is a result, not a mistake — it
> is the one thing the whole census could not tell us.*
> **Filled only partly?** Cancel the rest immediately and record it. Do not top
> it up.
> **Either way, write down: the ask, the size showing at that ask, and whether
> it filled.**

**1 — `KXMLBSPREAD` (MLB run line), 1 contract, ask 6c–15c (skip 10c).**
Scan MLB spread markets top to bottom in the app's default order. Take the first
with an ask in the band. If it has **at least 21 showing** at an ask in
**6c–13c**, use that same market for order 2. Buy **1**.

**2 — 20 contracts, 60 seconds later, ask 6c–13c (skip 10c).**
Same market as order 1 if it qualified; otherwise the first `KXMLBSPREAD` market
with an ask in 6c–13c and **at least 20 showing**.
**Record the account balance immediately before and after this order, every
digit.**

**3 — `KXMLBSPREAD`, 1 contract, ask 27c–39c (skip 30c).**

**4 — `KXMLBGAME`, 1 contract.** First look for an ask in **47c–52c (skip 50c)**
— that is the preferred one. If a full scan finds none, take the first with an
ask in **27c–52c (skip 30c, 40c, 50c)**. **This is the order that must not be
missed.**

**5 — `KXWNBAGAME`, 1 contract, ask 27c–39c (skip 30c).** *Only if the agent
session has told you Q-W activated, and only in the series it named.*

**Record for each:** ticker, ask, **size showing at the ask**, shares, estimated
cost, time, scheduled first pitch, minutes to first pitch, **and FILLED /
PARTIAL / DID NOT FILL with roughly how many seconds it took.**

**Best time to do this: 5pm–midnight ET.** On the four days censused, the cheap
band was on the board at **every single instant** in that window, with about
four such markets showing at once.

**Then stop.** A sixth *filled* order is a protocol breach, not a bonus. An
order that was submitted, did not fill and was cancelled costs nothing and does
not count against the six — but you get **at most two tries per cell**, and each
try must be a different market, taken in the app's default order going down.
Never go back up the list.
