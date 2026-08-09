# The leg echo: live coupling, or a transient mint-time state?

Date: 2026-08-09
Status: **complete — pre-registered, then run. Verdict: TOO THIN TO ANSWER.**

Everything above the `RESULTS` heading was written and committed to git before
a single observation was taken. That is the point of it. A rule chosen after
seeing the data is not a rule, and this project has already withdrawn two combo
claims for reasons of exactly that shape.

## The question, and why it is binary

`docs/adr/0012`'s addendum records a **leg echo**: a KXMVE combination's
`yes_ask_dollars` frequently equals one of its own legs' cost-to-buy to within
2c — 85% of dominated cross-game rows and 86% of dominated same-game rows,
against base rates of 3.2% and 7.5% among non-dominated rows. **119 echo rows
matched a leg that was not the cheapest**, which is a joint above
`min(marginal)` and impossible under any dependence structure. For that subset,
the quote at the combination's ticker is not a joint over `mve_selected_legs`.

The echo explains 86% of every domination event in every scope, and it is why
both of that session's combo claims were withdrawn. Two hypotheses remain:

- **LIVE COUPLING.** The combination's ask is continuously derived from that
  leg, so it moves tick-for-tick with it. Then the number at the combination's
  ticker is a leg price wearing a combination's name, no filter recovers a
  joint from it, and **MVE-as-correlation needs a different data source**.
- **TRANSIENT MINT-TIME STATE.** The ask was stamped from a leg at mint and
  then sat still while the leg moved on. Then the echo is a property of newly
  minted rows, and it is excludable by rule R1 below.

## Pre-registered protocol

Harness: `scripts/measure_combo_leg_echo.py`. Free, unauthenticated (`/markets`
is public — verified 200 with no signature), read-only, no orders, no
`multivariate_event_collections` lookup, **no Odds API credit**.

### Sampling — fixed before collection

| | |
|---|---|
| Discovery source | `GET /markets?series_ticker=KXMVESPORTSMULTIGAMEEXTENDED&status=open&limit=200`, newest-first page 1 only |
| Rounds | 12 |
| Interval | 15 s (window ≈ 2 min 45 s) |
| Requests per round | 2 — one page read, one batched `?tickers=…` read |
| Budget | **24 Kalshi calls** (the ADR's estimate was ~20) |
| Max pairs tracked | 10 |

Discovery and observation are **interleaved**, not phased: a combination minted
in round 7 is still observable for five rounds, whereas a discover-then-observe
design would only ever watch the pairs most likely to have already stopped
being quoted. Paging is not used — `/markets` is newest-first, a page of 200
spans well under a minute of minting, and CLAUDE.md forbids walking it blind.
The sample accumulates over *time*.

### Amendment 1 — sampling only, made before any time series was collected

The protocol above yielded **zero echo pairs** on its first two rounds, so no
observation of movement was possible and none was taken. Disclosed here rather
than quietly folded into the table above, because an undisclosed amendment is
how a pre-registration stops meaning anything.

**What was wrong.** `limit=200` on a newest-first page. Kalshi is minting
~1,900 combinations a minute in `KXMVESPORTSMULTIGAMEEXTENDED` right now, so
200 rows span about **seventeen seconds** of minting — while a combination
stays quoted for one to two minutes. The page was narrower than the lifetime of
the thing being sampled, so most of the quoted population was never visible.
Measured on the same slate, minutes apart:

| page | series | quoted combinations | echo pairs |
|---|---|---|---|
| `limit=200` | 1 | 9 | **0** |
| `limit=200` | all 8 (6 empty) | 16 | **0** |
| `limit=1000` | 2 | 104 | **7** |

This is not paging: page 2 is older than any live quote. It is the same newest
slice of one page, widened until it contains the population.

**What changed.** `PAGE_LIMIT` 200 → 1000; discovery over the two series that
have any open market on this slate; batch size 60 → 200 tickers per request
(verified to round-trip whole, combinations included); discovery confined to
the first 4 rounds, observation still running all 12; interval 15 s → 20 s
(window ≈ 4 min). Budget accordingly rises from 24 to **≈ 30 calls**, plus 4
spent on the failed first attempt and ~10 on the diagnostics in the table
above. Kalshi reads are free and unauthenticated; the ADR's "~20" was an
estimate, not a constraint, and the constraint that matters — zero Odds API
credits — is untouched.

**What did NOT change, and this is the point:** the echo definition and its
0.02 tolerance, the matched-leg choice, the move-event definition, `MOVE_TENTHS`,
`TRACK_TOL`, the 80% share, the floors of 5 events and 3 pairs, what counts as
`n`, and exclusion rule R1. Not one threshold that decides the verdict was
touched, and no time series existed when this amendment was written.

**One honest limitation it introduces:** the diagnostics above were run against
live data before the window opened. They measured *how many* echo pairs exist,
never how any of them moves, so they cannot have informed a threshold about
movement. But they are data, they were looked at, and they are on the record.

### Amendment 2 — cadence only, after run 1 was uninformative by its own criterion

Run 1 (12 polls, 20 s apart, 12 echo pairs, 19 calls) returned **TOO THIN TO
ANSWER**, and it failed on the informativeness criterion fixed in advance, not
on its result. Its full output is in `RESULTS` below and in
`2026-08-09-combo-leg-echo-run1.json`; nothing about it is discarded.

Two censoring mechanisms, both visible in that data:

1. **9 of 12 matched legs had exactly one distinct cost** across the four
   minutes. Pre-registered: that is a defect of the window, not a finding.
2. **9 of 12 combinations stopped being quoted within 20–80 s**, `yes_ask` going
   unreadable while `status` stayed `active`. The joint's quote lives *tens of
   seconds*; the matched leg ticks on a scale of *minutes*. Sampled at 20 s,
   the two barely overlap, so only 2 move events existed to classify — and they
   split 1 `tracks` / 1 `frozen`, which is as close to no information as two
   observations can be.

The fix is cadence, and it is forced by the mechanism: **sample inside the
quote's lifetime**. Run 2 polls every **4 s** for 75 rounds (5 min), rediscovers
every 12 rounds so a live pair always exists, retires a pair after 8 consecutive
unreadable asks (which can neither create nor destroy a move event, since one
requires both asks readable), and tracks up to 40 pairs. Cost ≈ 100 free
unauthenticated calls.

Run 2 is extended **because run 1 was uninformative, not because of its
direction** — 1 versus 1 has no direction. Both runs are reported. Run 2 is
primary; run 1's two events are pooled into the final table and identified.

Again unchanged: the echo definition and its 0.02 tolerance, the matched-leg
choice, the move-event definition, `MOVE_TENTHS`, `TRACK_TOL`, the 80% share,
the floors of 5 events and 3 pairs, what counts as `n`, and rule R1.

### Definitions — fixed before collection

- `cost_to_buy_leg(L)` is **imported** from
  `scripts/measure_combo_correlation.py`, not re-implemented: `yes → yes_ask`,
  `no → 1 − yes_bid`. One path, so this rule cannot disagree with the version
  the original harvest used.
- **Echo pair**: a combination with `mve_selected_legs`, a readable
  `yes_ask_dollars`, and every leg priceable, where
  `|combo_ask − cost_to_buy_leg(L)| ≤ 0.02` for some leg `L`.
  Tolerance 0.02 is `analyse_combo_domination.ECHO_TOLERANCE`, unchanged.
- **Matched leg**: the `L` minimising that gap at the poll of discovery. Fixed
  at discovery and never re-chosen.
- **Move event**: a consecutive poll pair where the matched leg's cost changed
  by `≥ 0.005` (half a cent) **and both** combo asks are readable.
- **tracks**: `|Δcombo − Δleg| ≤ 0.005`.
- **frozen**: `|Δcombo| < 0.005` while the leg moved.
- **other**: anything else.

### `n` — fixed before collection

`n` is the number of **move events**. Not pairs, not polls.

A pair whose matched leg never moves cannot discriminate the two hypotheses at
all; it contributes zero and is reported separately. The asymmetry is
deliberate and must not be read backwards:

- a combo ask with **one distinct value** is the *result* under the transient
  hypothesis — a finding;
- a matched-leg cost with **one distinct value** is a *defect of the window* —
  the tell that no guard could have fired, forcing "too thin to answer".

### Decision rule — fixed before collection

| Verdict | Condition |
|---|---|
| **LIVE COUPLING** | ≥ 80% of move events are `tracks` |
| **TRANSIENT MINT-TIME STATE** | ≥ 80% of move events are `frozen` |
| **TOO THIN TO ANSWER** | `n < 5` move events, **or** fewer than 3 pairs contribute a move event, **or** neither threshold above is met |

The floor of 5 is CLAUDE.md's "≥5 expected outcomes on each side before a
normal approximation is allowed to speak". The floor of 3 pairs exists because
a pooled number is not a finding until the parts agree — the per-pair table is
printed beside the pooled count, always.

"Too thin to answer" is a permitted and useful outcome. It costs one more run;
a fabricated verdict costs the record.

### Exclusion rule R1 — fixed before collection

Written **now**, so that it cannot be tuned to whatever the data turns out to
be. It applies **only if the verdict is TRANSIENT MINT-TIME STATE**:

> **R1.** A combination row is excluded from any domination, Frechet-refusal or
> correlation statistic if, **at the moment the row was read**,
> `|combo_ask − cost_to_buy_leg(L)| ≤ 0.02` for **any** leg `L` in
> `mve_selected_legs`, with `cost_to_buy_leg` as defined above.
>
> - The tolerance is 0.02, fixed, and is not re-tuned per scope or per run.
> - R1 is applied to **every scope identically** — same-game, cross-game, mixed
>   and undecodable. Applying it to one scope only would manufacture exactly
>   the gradient ADR 0012 already had to withdraw.
> - Every statistic computed under R1 reports the **excluded count beside it**,
>   never a bare post-exclusion rate.
> - R1 is an exclusion, not a correction. It does not license any claim about
>   the rows it removes.

If the verdict is **LIVE COUPLING**, R1 is void: no exclusion rescues a
population whose prices are leg prices, and the correct response is to say
plainly that MVE-as-correlation needs a different data source.

### What this measurement will not establish

Stated in advance so it cannot be quietly narrowed later.

- **Nothing about why.** Whether the echoed number is a real book quote, a
  seeded ask, or an artefact of provisional minting is not observable here.
- **Nothing about non-echo combinations.** Only echo pairs are tracked.
- **Nothing about liquidity or tradeability.** These rows are
  `is_provisional` with zero volume and zero open interest.
- **One series, one slate, one window of minutes.** A leg that moves on a
  slower timescale than the window looks frozen for reasons that have nothing
  to do with the combination.
- **Not an edge.** No fair value is computed; no combo fee model is verified.

---

## RESULTS

Status: **complete. Verdict: TOO THIN TO ANSWER.**

### The verdict, by the rule fixed in advance

| | run 1 | run 2 | pooled |
|---|---|---|---|
| cadence | 12 polls × 20 s | 75 polls × 4 s | — |
| echo pairs tracked | 12 | 38 | **50** |
| pairs contributing a move event | 2 | 0 | **2** |
| **move events (`n`)** | **2** | **0** | **2** |
| `tracks` | 1 | 0 | **1** |
| `frozen` | 1 | 0 | **1** |
| `other` | 0 | 0 | 0 |

`n = 2` against a floor of 5; 2 contributing pairs against a floor of 3. Both
floors fail, and the two events split one each way. **The pre-registered
verdict is TOO THIN TO ANSWER, and it is reported as it fell.**

Consequently **exclusion rule R1 is not activated.** R1 was conditioned on a
TRANSIENT verdict, that verdict was not reached, and a rule that fires on a
result it did not get is not a rule. It stands written, unused.

Nothing here reinstates anything ADR 0012's addendum withdrew. The 94%, the
22.4% and both combo claims stay withdrawn, and the leg echo stays unexplained.

### Why it is too thin — this part *is* the transferable finding

The design cannot work at any cadence, and both runs say so the same way.

**The matched leg does not move.** Across both runs, **45 of 50 matched legs
showed exactly one distinct cost** for the whole window — 9 of 12 in run 1 and
36 of 38 in run 2. This is precisely the condition the pre-registration named in
advance as a defect of the window rather than a result, which is the only reason
it is safe to read it now.

**The combination stops being quoted in tens of seconds.** `yes_ask` goes
unreadable while `status` stays `active`. In run 2, 38 pairs yielded 379 polls
with a readable combo ask and **341 consecutive-poll pairs with both sides
readable** — a large exposure that produced zero qualifying leg moves.

So the two clocks do not overlap. The joint's quote lives on a scale of tens of
seconds; the matched leg ticks on a scale of minutes. **Polling faster does not
help** (run 2 was 5× faster and produced *fewer* move events than run 1), and
polling longer does not help either, because the combination is gone. The ADR's
proposed test — "record whether the ask moves tick-for-tick with the matched
leg" — is not answerable on this data source at this cost, and that is a fact
about the venue, not about effort.

### Exploratory — NOT pre-registered, and not a verdict

Everything in this section was found by looking at the data after the fact. It
is recorded because it names the next experiment, and it is fenced off because
nothing in it was predicted in advance. **No claim below may be cited as
measured.** Read `n` before every one of them: the largest is 8.

**1. The ask flips between two values while the leg stands still.** Repeatedly,
at 4-second resolution, the same combination ticker returned the echo value and
then a distinctly different value, in blocks of several seconds, with the
matched leg's cost constant throughout:

    matched leg KXMLBGAME-26AUG091605DETSF-DET, cost 0.55 for all 44 polls
    combo ask   0.549 ×1, 0.148 ×5, 0.549 ×4, 0.148 ×3, 0.549 ×7, none ×4, ...

    matched leg KXWNBAGAME-26AUG09PHXWSH-WSH, cost 0.53 for all 30 polls
    combo ask   0.537 ×9, 0.317 ×3, 0.536 ×10, none ×8

Nineteen such combo-ask moves of ≥ 0.5c occurred while tracked. **This fits
neither hypothesis.** It is not tick-for-tick coupling — the leg never moved. It
is not a state fixed at mint — the echo value leaves and comes back minutes
later.

**2. The echoed price is a resting order, not a computed number.** Of 8 live
echo combinations whose order books were read, 5 had any book at all, and in
**5 of those 5 the top NO level derived to a `yes_ask` within 2c of one of the
legs' costs** — the derived-ask identity `yes_ask = 1 − best_no_bid` holding
exactly, as the `kalshi-api` skill records:

    303B0A8CB24  legs [0.70, 0.64]  NO bid 0.377 × 641  ->  ask 0.623
    FBC1DDE3F26  legs [0.82, 0.76, 0.72]
                 NO bids 0.278 × 71 -> 0.722   and   0.557 × 112 -> 0.443

The second is the shape that suggests a mechanism: the **top** level echoes a
leg (0.722 vs 0.72) while the **deeper** level (0.443) looks like something a
joint could plausibly be. If the echo is one participant resting an order
priced off a single leg, then the flipping in (1) is that order being posted and
pulled, and neither of this document's two hypotheses was ever the right pair.

**3. The list endpoint and the book disagree.** 3 of the 8 carried a
`yes_ask_dollars` on `/markets` while `/markets/{ticker}/orderbook` was empty,
and one combination read `0.0000 / 1.0000` on `/markets/{ticker}` for 18
consecutive polls while the list endpoint quoted it at 0.463. **Every combo
price this project has recorded — all 2,116 rows of the harvest — comes from
the list endpoint.** Whether those quotes were backed by a book at the moment
they were read is unknown and was never checked.

### The next experiment, pre-registered here

Fixed now, so the next session does not choose it after seeing data:

> **E2.** For each combination carrying a `yes_ask` on `/markets`, read
> `/markets/{ticker}/orderbook` in the same pass. Record (a) whether the book is
> non-empty, (b) whether `1 − best_no_bid` reproduces the list `yes_ask`, and
> (c) whether any level derives to within 2c of a leg's cost. Report the rate of
> each with its `n`, split by scope, and report the **book-empty rate first** —
> if a material share of quoted rows have no book, the harvest's population is
> not what it was taken to be, and that supersedes every other question here.

E2 needs no leg to move and no combination to survive, which is exactly why it
is answerable where this one was not.

**E2 has since been run.** See `2026-08-09-combo-e2-book-empty.md`: 4 of 20
quoted combinations had an empty book (CI [8.1%, 41.6%]), all four on rows
whose list ask had gone 3.4 s later, and the list ask disagreed with the
book-derived ask on 5 of 16. It does not resolve observation 3 above; it puts a
`n` and an interval on it.

### Cost

≈ 210 free, unauthenticated Kalshi reads across both runs, the failed first
attempt, and the diagnostics — against the ADR's "~20" estimate, which assumed
a test that turned out not to be answerable. **Zero Odds API credits. Zero
orders. Zero lookups. No mutation of any kind, and no credential in the
process.**

### Raw data

- `2026-08-09-combo-leg-echo-run1.json` — 12 pairs, 12 polls each at 20 s.
- `2026-08-09-combo-leg-echo-run2.json` — 38 pairs, 75 polls at 4 s.
- `2026-08-09-combo-leg-echo-books.json` — the 8 exploratory order books.

These markets are gone within minutes: the runs can be repeated, never
reproduced.

### What these results do not establish

In addition to the five limits fixed in advance, all of which still apply:

- **Not that the echo is unexplained by either hypothesis.** `n = 2` licenses
  no statement about the hypotheses at all. The exploratory section suggests
  both may be wrong; it does not show it.
- **Nothing about the flipping's cause.** Quoter behaviour, replica skew
  between endpoints, and a genuinely flickering book all predict what was seen.
- **Nothing about the 2,116-row harvest's validity.** Observation 3 raises the
  question; only E2 answers it.
- **Not a null result.** "Too thin to answer" is the absence of a measurement,
  not evidence that the echo does not move with its leg.
