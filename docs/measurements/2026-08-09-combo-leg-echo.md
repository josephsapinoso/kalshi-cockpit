# The leg echo: live coupling, or a transient mint-time state?

Date: 2026-08-09
Status: **PRE-REGISTERED — no data collected yet**

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

*(empty — to be appended after the run, without touching anything above)*
