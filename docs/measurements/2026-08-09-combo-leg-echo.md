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
