# Pre-registration: how much makers charge over the desk's fair value on a combination, by leg count

**Written 2026-10-08, before any row is read.** Ticket #326, part of #320.
No live query was run and no `combo_rfqs` or `combo_rfq_quotes` row was read
to write this. The only markup figures the author has seen are the ones
already in the record: the single 2026-09-17 probe (best YES ask 59.3c against
a fair of 57.8c on a three-leg combination, makers 3.80c apart,
`docs/measurements/2026-09-17-a-combo-rfq-returns-a-real-takeable-price.md`),
and #320's statement that dispersion has n = 2 today. Neither is re-read here
and nothing below was tuned to them.

**What is being measured.** When the desk asks the market to price a
combination (an RFQ, ADR 0164), makers answer with private YES asks. The desk
froze its own fair value for that combination at the moment it asked. The gap
between the best maker ask and that fair value is the makers' **markup**: what
they charge over what the sportsbook consensus says the combination is worth.
This registration fixes how that gap is cut by leg count, price, time to the
first game and size, and how far apart the makers on one ask are.

This is compare-to-price (the ADR 0038 template). It reads no settlement, so
it says nothing about whether any combination won. It spends no credits and no
tokens.

---

## 0. The power check, which comes first

**Verdict: UNDERPOWERED for the leg-count trend at the effect sizes the
record makes plausible. Re-scoped, not killed (§8).**

### What the test can see

The trend test (§6, P1) is a slope of log markup on leg count. Its detectable
per-leg slope at 80% power is

    MDE = (t_crit + 0.84) x sigma_r x sqrt(DEFF) / (sd_L x sqrt(n))

with `t_crit` the one-sided 0.0125 critical value of t on `G - 1` degrees of
freedom (G = distinct days), `sigma_r` the spread of log markup across asks,
`DEFF = 1.5` for asks sharing a day, and `sd_L` the spread of leg counts.

Detectable per-leg slope, as a percent of price per extra leg:

| asks n | days G | sd_L | sigma_r 0.05 | sigma_r 0.10 | sigma_r 0.20 |
|---|---|---|---|---|---|
| 20 | 10 | 1.0 | 4.8% | 9.7% | 19.3% |
| 40 | 15 | 1.0 | 3.2% | 6.5% | 13.0% |
| 60 | 21 | 1.0 | 2.6% | 5.2% | 10.3% |
| 60 | 21 | 0.7 | 3.7% | 7.4% | 14.7% |
| 150 | 40 | 1.0 | 1.6% | 3.2% | 6.3% |
| 300 | 60 | 1.0 | 1.1% | 2.2% | 4.4% |

Asks needed for a given per-leg slope (many days, sd_L = 1.0):

| per-leg slope | sigma_r 0.05 | sigma_r 0.10 | sigma_r 0.20 |
|---|---|---|---|
| 5% | 15 | 58 | 229 |
| 3% | 40 | 159 | 634 |
| 2% | 90 | 357 | 1,426 |
| 1% | 357 | 1,426 | 5,704 |

**Planning value sigma_r = 0.10.** Reason: the consensus on one leg carries
roughly 1 to 2 points of method spread on a price near 50%, which is 2% to 4%
of the price per leg, and that compounds over 2 to 6 legs. The one ask on
record had its makers 3.80c apart on a 59.3c best ask, about 6% of the price.
The run prints the observed sigma_r beside this planning value. No decision
depends on the observed one.

**sd_L may be well below 1.0.** If most asks are two- and three-leg
combinations, sd_L is near 0.5 and every detectable slope above doubles.

### Where the effect being hunted sits

- **The desk's own fair grows pessimistic with every leg.** Each leg's fair is
  the minimum of four devig methods, and a combination multiplies them (ADR
  0070 §2.1: "multiplying N of them compounds that conservatism N-fold"). One
  to two points of method spread is 1% to 5% of a leg's price, depending on
  how lopsided the leg is. So **against the conservative fair, markup grows
  by roughly 1% to 5% per leg with no maker behaviour at all.**
- **A maker's real per-leg charge is of the same order.** ADR 0139's only
  figure is a sharp bettor's estimate, never computed: about 4.5% on a
  two-leg combination against about 2.5% for the same picks bought singly,
  which is around 2 points for the step from one leg to two.

So the trend against the conservative fair is about as large as an artifact
the desk built into itself, and the trend that matters, the one against the
most generous method (§4), is plausibly 1% to 3% per leg. **That needs about
90 to 360 asks on 60 or more days.** Look A (§7) has at most 21 days of rows
(schema v45 shipped 2026-09-17). At 60 asks on 21 days it resolves about 5%
per leg at sigma_r = 0.10.

**What still justifies running it.** It is free. It can catch a large
per-leg charge (5% or more), a reversal, or the case where the whole apparent
growth is the desk's own pessimism. The cells and the dispersion table are
descriptive and are what a person reads when deciding copy. Below about 5%
per leg this measurement funds nothing and kills nothing (§8).

---

## 1. The claims, as things that could be false

**P1, leg count (direction fixed now).** Across recorded cross-game asks, the
log of (best maker ask / fair) **increases** with leg count, measured against
the desk's conservative fair **and** against the most generous single-method
fair (§4). A slope that is **negative** against the conservative fair
(REVERSED) is registered now so it cannot be discovered later, and its alpha is
counted in §6.

This is a claim about an average slope. The copy it bears on, "Each extra leg
is one more thing a maker can charge for", is a universal ("each") and a
possibility ("can"). As written, the copy cannot be falsified by any data: a
maker always *can* charge. This registration tests the stronger reading, that
makers *do* charge more as legs are added, on average. A result here may
never be written as "each leg costs X". It may only be written as an average
over the asks recorded, with n and dates.

**P2, time to the first game (two-sided).** Holding leg count fixed, log
markup differs between asks made **less than 6 hours** before the earliest
leg's start and asks made **6 or more hours** before it. N = 6 is fixed now
and is not revisited. "Tighter" in any resulting copy means a smaller markup
over fair. It does not mean a smaller spread between makers.

Nothing else is tested. Every other figure in this document is a count, a
median or an interval with no verdict attached.

---

## 2. Population and exclusions

**Source:** the live database's `combo_rfqs` and `combo_rfq_quotes` tables
(schema v45, `backend/store/schema.sql:2847-2911` and `:2915-3019`), joined to
`parlay_lookups`, `kalshi_events`, `kalshi_series` and `fair_prices` only as
named below. Demo is never read.

**Markup population (P1, P2, the cells).** One row per `combo_rfqs` row that
meets every condition below. Each condition is checked in this order and the
count removed at each step is printed.

| # | condition | why it does not reference the markup |
|---|---|---|
| 1 | `requested_ms` before the look's cutoff (§7) | a date |
| 2 | `purpose = 'buy'` or `purpose IS NULL` | an exit ask asks a different question. The schema records every pre-v56 row as a buy-side ask, and every exit writer leaves `fair_joint` NULL |
| 3 | `status = 'quoted'` | an ask with no representable quote has no best ask. `no_quotes`, `priced_too_finely`, `error` and `asked` are counted **by leg count** and printed as counts |
| 4 | `fair_joint` not NULL | NULL means a same-game combination or a leg the desk could not price (`parlay_check.py:741-761`, `game_builder.py:835`). Counted by `card_key`. These rows still enter the dispersion table |
| 5 | `0 < fair_joint < 1` | anything else is a bug, counted |
| 6 | **single-read**: every `combo_rfq_quotes` row on the ask has `captured_ms = requested_ms` | see below |
| 7 | **provenance**: a `parlay_lookups` row exists with `minted_market_ticker = ticker`, `requested_ms <=` the ask's, and `fair_joint_conservative` equal to `combo_rfqs.fair_joint`; the latest such row is the ask's lookup | the fair is copied from the most recent lookup that minted the ticker (`combo_rfq.py:233-257`). If that row cannot be found, where the fair came from cannot be shown |
| 8 | **fair age**: ask `requested_ms` minus the lookup's `requested_ms` is 30 minutes or less | the fair is frozen at LOOKUP time, not at ask time. A fair older than this prices a different moment |

**Rule 6 needs saying plainly.** `create_rfq` reuses an open RFQ, so tapping
"Ask the market" twice on one combination writes one `combo_rfqs` row (the
first ask's fair, `ON CONFLICT DO NOTHING`) and then **overwrites** its quotes
with the second ask's prices (`record_quotes`, `ON CONFLICT DO UPDATE`). On
such a row the stored quotes and the stored fair come from different moments.
On a first ask, `captured_ms` and `requested_ms` are the same variable
(`now_ms`, `combo_rfq.py:391` and `:446`), so equality identifies an ask whose
stored prices are its own.

**Rule 6 is not provably independent of the outcome, and that is stated
now.** Whether a second tap happened may depend on the price the first tap
showed. The rule is kept in the primary because on those rows the statistic
is undefined, not merely noisy. The count removed is printed, and so are P1
and P2 point estimates with those rows put back (using their stored, latest
quotes). If rule 6 removes more than 20% of the rows that pass rules 1 to 5,
the result's first paragraph says so.

**Rule 8's 30 minutes is fixed now**, and the run prints the P1 and P2 point
estimates with no age limit beside the primary.

**Never split, never joined: whether the quote was accepted.** Splitting by
"taken" selects on the price. `accepted_ms`, `outcome_status` and the venue
fill columns are not read.

**Rows from probes count.** Asks fired by an agent under Joe's approved
actions sit in the same table and no column separates them. The population is
"asks fired from the live desk", not "Joe's asks".

**Dispersion population.** Rules 1, 2, 3 and 6 only, with or without a fair:
cross-game, same-game and unpriceable asks together. Of those, asks with two
or more stored quotes carrying a non-NULL `yes_ask_tenths`.

---

## 3. Unit, cluster, and the cut

- **Unit: one ask**, one `combo_rfqs` row after §2.
- **Cluster: the US Eastern calendar day** of `requested_ms`
  (`America/New_York`). Asks on one day share games, makers' state and the
  consensus feeding the fair, so they are not independent. Asks on different
  days are treated as independent. That is wrong for a combination asked on
  two days with the same legs, so the run prints how many tickers were asked
  more than once and the share of asks they carry.
- `G` (distinct days) and the largest day's share of asks are printed beside
  every fit.
- **Leg count `L`:** the length of the `selected_legs` JSON array. Cells:
  2, 3, 4, 5, 6+. In the regression, 6+ is coded 6.
- **Price band on the BEST QUOTE**, the price actually payable, never the
  fair: `best_ask_tenths` in [0, 100), [100, 250), [250, 500), [500, 1000].
  That is under 10c, 10c to under 25c, 25c to under 50c, and 50c or more.
  **20 primary cells** = 5 leg counts x 4 price bands. No other edges.

**A known cost of banding on the quote.** The quote contains the markup, so a
higher markup can move an ask up a band. Within a band, markup is therefore
partly a function of where the band edges fall. This is why the bands are
used for the cells only and never as covariates in P1 or P2.

### Secondary cuts, descriptive only

| cut | levels, fixed now |
|---|---|
| hours to first game | earliest `kalshi_events.commence_ms` over the ask's legs minus `requested_ms`: already started, [0, 2h), [2h, 6h), [6h, 24h), 24h or more, unknown (any leg's commence NULL) |
| target size | `target_cost_dollars`: up to $1, over $1 to $5, over $5 to $20, over $20; and a separate row for asks sized by `contracts_requested` |
| league mix | one league (by `kalshi_series.league` through each leg's event's `series_ticker`) or more than one. For one-league asks, by league |
| card | `card_key` (`safe`, `middle`, `lottery`, `checked`, any other value as found) |

---

## 4. The statistics, named as estimators

For each ask in the markup population:

- `f` = `fair_joint x 1000`, the conservative fair in tenths of a cent.
- `b` = the lowest `yes_ask_tenths` among the ask's quote rows (the best
  quote). It is the complement of the maker's NO bid, the derived ask.
- **markup in tenths** = `b - f`. **markup as % of fair** =
  `100 x (b - f) / f`. These are what the cells report.
- **log markup** `r = ln(b / f)`. This is what P1 and P2 test, because a
  per-leg charge that multiplies the price is a constant step in `r`.

### The other end of the band: the generous fair `g`

ADR 0070 §2.1 promises the per-method band beside the conservative fair.
**No table stores it.** `combo_rfqs` keeps only `fair_joint`, which is the
conservative joint copied from `parlay_lookups.fair_joint_conservative`, and
neither table has a per-method column (checked against `schema.sql` and every
`_MIGRATIONS` step in `backend/store/db.py`). So the band is **reconstructed,
not read**, and is labelled that way wherever it is printed.

For each leg: take the `fair_prices` row the ladder maps that leg and side to,
choosing the one in force at the lookup's `requested_ms` (the latest
`computed_ms` at or before it). The lane must reuse the ladder's own
leg-to-row mapping (`parlays.py` around `:1172`) and add the as-of bound, not
write a second mapping. From that row:

- `p_lo` = `p_conservative`
- `p_hi` = the largest non-NULL of `p_multiplicative`, `p_additive`,
  `p_power`, `p_shin`

Then `g = f x product over legs of (p_hi / p_lo)`. That is the combination
with every leg at its most generous method: the generous end of the band. The
copula is not re-run. `g` is not the truth either. It is the least pessimistic
fair the four methods allow.

**An ask is "not reconstructed"** when any leg has no row, all four method
columns are NULL (alternate-line legs carry no per-method values,
`alt_lines.py:334`), or the reproduction check fails:
`|ln(product of p_lo / f)| > 0.05`. That check catches a wrong leg mapping. It
cannot be exact because the copula nudges same-day legs (ADR 0070 §2.2). The
count and rate of "not reconstructed" are printed **by leg count**.

Every cell and every fit prints markup against `f` **and** against `g`, side
by side, with the reconstructed n.

### P1: leg-count slope

OLS of `r` on `L`, no other covariates, standard error CR1 clustered by day,
t on `G - 1` degrees of freedom. It is fitted twice:

- `beta_c`: `r` against `f`, on the whole markup population.
- `beta_g`: `r` against `g`, on the reconstructed subset.

Printed beside them, as point estimates with n and G, never tested: the slope
per `card_key`, per price band, and per league mix; the largest day's share and
`beta_g` with that day dropped; `beta_g` on asks with `refused_too_fine = 0`
(a maker refused for pricing finer than a tenth of a cent may have been the
best price, and that price is not stored); both slopes with rule 6's rows put
back; both slopes with no fair-age limit.

### P2: under 6 hours against 6 hours or more

OLS of `r` on an indicator for "earliest leg starts in under 6 hours" plus `L`
(linear), CR1 by day, t on `G - 1`. It is fitted against `f` (`kappa_c`) and
against `g` (`kappa_g`). Asks whose first leg had already started, or whose
start is unknown, are left out of P2 and counted. **Why `g` is required here
too:** devig method spread can narrow as kickoff approaches, which by itself
would make markup against `f` look smaller near kickoff.

### Dispersion, per ask with two or more quotes

`worst - best` among the ask's stored `yes_ask_tenths`, in tenths and as % of
best. Printed: the count of asks with 0, 1, 2 and 3 or more stored quotes, and
medians and IQR of dispersion by leg count and by cross-game against
same-game. No test, no interval.

---

## 5. Floors before anything may speak

**The floor:** at least **20 asks on at least 10 distinct days**.

- **A cell** below the floor prints n, days, median and IQR only. No
  interval, no test.
- **A cell** at or above the floor also prints an interval for the median
  markup % against `f` and against `g`: a day-cluster bootstrap, 10,000
  resamples, seed 20261008, at 99.75% (that is 95% shared across 20 cells).
  **An interval is not a test.** No cell verdict is written in either
  direction.
- **P1** is evaluable only if at least two leg-count levels each meet the
  floor (pooled over price bands). `beta_g` additionally needs at least **80%**
  of the markup population reconstructed. Below 80%, `beta_g` is printed as a
  point estimate and cannot pass.
- **P2** is evaluable only if each arm meets the floor. `kappa_g` needs the
  same 80%.

These floors count rows and days. None of them reads a price.

---

## 6. Decision rule and multiplicity

**The cells are not tested, because noise alone would light them up.** 20
cells at two standard errors yields about 0.91 false "findings" under no
effect at all.

**Exactly four directional tests, each with alpha 0.0125:**

    P1 up       beta_c and beta_g both >= +t_crit   (intersection: both must pass,
                                                      so no correction between them)
    P1 down     beta_c <= -t_crit
    P2 tighter  kappa_c and kappa_g both <= -t_crit
    P2 wider    kappa_c and kappa_g both >= +t_crit

    t_crit = one-sided 0.0125 quantile of t on G - 1 (2.685 at G = 10, 2.423 at G = 21)
    family alpha <= 0.0125 x 4 = 0.05

Each test runs **once**, at the first look where its floor holds (§7), and
never again.

**P1 outcomes, exactly one, checked in this order:**

- **MAKERS CHARGE MORE PER LEG:** `beta_c >= t_crit` and `beta_g >= t_crit`
  and `beta_g` with the largest day dropped `> 0` and `beta_g` on
  `refused_too_fine = 0` asks `> 0`. The last two are point estimates.
- **GROWTH NOT SEPARATED FROM THE DESK'S OWN FAIR:** `beta_c >= t_crit`, and
  `beta_g` fails its test, fails a point condition above, or cannot be
  computed (under 80% reconstructed).
- **REVERSED:** `beta_c <= -t_crit`.
- **UNRESOLVED:** anything else. Per §0, this is the expected outcome for any
  per-leg charge under about 5%. **It may not be written as "makers do not
  charge more for more legs".**
- **NOT EVALUABLE:** P1's floor is missed at look B.

**P2 outcomes:** **TIGHTER INSIDE 6 HOURS** (both `kappa` at or below
`-t_crit`, and `kappa_g` with the largest day dropped `< 0`), **WIDER INSIDE
6 HOURS** (both at or above `+t_crit`, and `kappa_g` with the largest day
dropped `> 0`), **UNRESOLVED**, or **NOT EVALUABLE**. UNRESOLVED may not be
written as "timing does not matter".

**No running figure, anywhere.** No screen, route, push, log line, instrument
or ticket may compute a running markup by leg count, by price band or by time
to kickoff from `combo_rfqs`. A threshold re-read against a growing table is
thousands of looks, and under no effect it crosses eventually with
probability 1 (13.7% measured in this repo, and that is a floor). **If such a
surface is built, this registration is spent.** A per-row fact (this ask's
quote beside this ask's fair) is allowed and already exists. ADR 0164
Decision 6 still binds: the gap is never labelled cheap, good or edge, and
nothing is ordered by it.

---

## 7. Stopping rule

- **Look A:** rows with `requested_ms < 2026-10-08T00:00:00Z`. Every such row
  already exists and none has been read. Run once by the main session after
  the QueryDef lane (#327) merges.
- **Look B:** happens only if P1's floor or P2's floor was missed at look A.
  Rows with `requested_ms < 2027-01-15T00:00:00Z`, run on or after that date.
  It tests only what look A could not. Look A's tests are not re-run.
- **There is no look C.** Look B is not extended for being close, for
  UNRESOLVED, or for a thin cell.
- **If how the fair is formed changes before look B** (`core/ladder.py`
  `_joint`, the copula nudges in `core/correlation.py`, or the devig methods),
  a dated amendment is written before any row is read, and asks made after
  that commit reached main are left out of look B.

---

## 8. Falsification destination and consequence

Result documents are written whatever the outcome:
`docs/measurements/<run-date>-combo-markup-by-leg-count-look-a.md`, and if
look B happens, `...-look-b.md`. Each quotes §6 and §10 verbatim and opens with
the §2 exclusion counts, n, G and the §0 detectable slope at the n reached.

**A fact about the copy that changes what the result can do.** The sentence
"Each extra leg is one more thing a maker can charge for." exists in one place
as of 2026-10-08: `frontend/src/components/GameLegs.tsx:50-51`, rendered at
`:317`. That is the `/game` **same-game** builder. This measurement has no
fair for same-game asks, so it measures the sentence's mechanism only on
cross-game combinations, and a result transfers to that page by assumption.
`GameLegs.tsx:46-48` and `GameScriptCard.tsx:52-53` carry a different
sentence ("...The makers' quote prices that in."), which is about same-game
correlation. This registration cannot speak to it under any outcome.

| P1 outcome | the extra-leg sentence | built or opened |
|---|---|---|
| MAKERS CHARGE MORE PER LEG | stays as written. The result document records that it is supported on cross-game asks, as an average, and not measured on same-game ones | nothing required. Adding a number to the sentence is user-facing copy and needs a #302 sub-issue for Joe |
| GROWTH NOT SEPARATED FROM THE DESK'S OWN FAIR | the growth it attributes to makers cannot be told apart from the desk's own per-leg caution | a #302 sub-issue the same session: keep it, or replace it with a sentence true by construction, such as "Each extra leg makes the combination less likely to come in." |
| REVERSED | it contradicts the only population measured | a #302 sub-issue the same session, proposing removal or replacement |
| UNRESOLVED / NOT EVALUABLE | unchanged, and recorded as unmeasured. It may not be cited as measured | nothing. Without a result, the sentence's fate is the same as it would be with no measurement |

| P2 outcome | a timing sentence on Ask the market (`AskTheMarket.tsx`) | built or opened |
|---|---|---|
| TIGHTER INSIDE 6 HOURS | may be said, as a fact about the asks recorded, with n and dates. Not as advice, and not as a promise about the next ask | a #302 sub-issue for Joe's wording |
| WIDER INSIDE 6 HOURS | the reverse may be said, under the same rules | a #302 sub-issue for Joe's wording |
| UNRESOLVED / NOT EVALUABLE | **no timing sentence in either direction**, including "ask nearer kickoff" | nothing |

**"Ask again" is not decided here under any outcome.** It needs its own
registration (#320 already names it killed at n = 2). Two reasons. Dispersion
here is between makers at one instant, not one ask against a later one. And
the table cannot hold the comparison: a re-ask on a reused RFQ **overwrites**
the first prices (`record_quotes`, `ON CONFLICT DO UPDATE`). A successor
registration therefore needs a schema change first, keeping each ask's quotes
instead of updating them in place.

**Below about 5% per leg, this measurement funds nothing and kills nothing.**
No plan may wait on it.

---

## 9. Secondary, descriptive only

- The §3 secondary cuts, each with n, days, median and IQR of markup % against
  `f` and `g`. No interval below the floor and no test at all.
- Counts of `no_quotes`, `priced_too_finely`, `error` and `asked` by leg count.
  Counts, not rates.
- The book's own ask at the same moment (`book_yes_ask_tenths`): how often it
  was non-NULL, by leg count, and on those asks, how often the book was at or
  below the best quote. Counts only.
- Dispersion (§4).

---

## 10. What this cannot establish (quoted verbatim in each result)

- **Not markup against the truth.** The fair `f` is the minimum-of-four
  Gaussian-copula joint (ADR 0070 §2.1). It is deliberately pessimistic and
  grows more so with every leg, so markup against it is **overstated**, by
  more on longer combinations. `g` is the other end of the four methods'
  band, not the truth. And `g` is **reconstructed** from `fair_prices` after
  the fact, because no table froze the per-method joint at ask time.
- **Not the fair at the instant of the ask.** The fair was frozen when the
  card was looked up, up to 30 minutes earlier (rule 8), and the consensus
  under it has its own age.
- **Not Kalshi's combination market.** Only asks fired from this desk, on
  combinations this desk minted, at the sizes asked, are in. The population
  is self-selected by which cards were opened and asked about. Makers may
  price one requester differently from another, and nothing here can see
  that.
- **Not other sizes.** Every quote was read at the target size asked, which
  was small. Markup at a larger size is not measured.
- **Not what is paid.** The best quote is before Kalshi's taker fee, which is
  charged on acceptance. A quote is not a fill: the maker has a confirmation
  window and may decline.
- **Not every maker.** Only quotes arriving within the 4-second polling
  window (`QUOTE_WAIT_S`) are stored, and quotes refused for being priced
  finer than a tenth of a cent are not stored at all.
- **Nothing about same-game combinations.** They carry no fair, so they have
  no markup here. They enter dispersion only.
- **Nothing about outcomes, edge or Joe's results.** No settlement, fill,
  order or position is read. Markup is a cost, not a signal (ADR 0038).
- **Not causal.** Leg count goes together with price, card type and league.
  A slope over leg count says how markup and leg count moved together on
  these asks, not what adding a leg would do to a given combination.
- **Not "ask again".** Re-asked rows are left out of the primary (rule 6),
  and their first prices no longer exist.
- **Start times are the latest recorded, not as of the ask.**
  `kalshi_events.commence_ms` can be updated in place, for example after a
  postponement.
- **Not ADR 0139's comparison.** Combinations are not compared with the same
  legs bought singly.

---

## Registration status

**UNDERPOWERED.** At about 60 asks on 21 days, which is the most look A can
hold, P1 resolves a per-leg slope of about 5% at sigma_r = 0.10, and the
artifact-free slope it is after is plausibly 1% to 3%, which needs about 90 to
360 asks on 60 or more days. **Re-scoped, not killed:** it runs at no cost as
a check that can catch a large per-leg charge, a reversal, or growth that is
only the desk's own caution, and it produces the descriptive cells and the
dispersion counts. Below that, the sentence's fate is not an evidence decision
(§8).

**Decision rule, verbatim, for checking against the eventual write-up:**

> Unit: one buy-side, quoted, single-read `combo_rfqs` ask with
> 0 < `fair_joint` < 1, provable lookup provenance and a fair at most 30
> minutes old; cluster: US Eastern day. `r = ln(best yes_ask_tenths /
> (1000 x fair_joint))`; `g` = the same with every leg at its most generous
> devig method, reconstructed from `fair_prices` as of the lookup. P1: OLS
> slope of `r` on leg count (6+ coded 6), CR1 by day, t on G - 1, fitted
> against `f` (`beta_c`) and against `g` (`beta_g`). P2: OLS of `r` on an
> under-6-hours indicator plus leg count, against `f` (`kappa_c`) and `g`
> (`kappa_g`). Four one-sided tests at 0.0125 each, family alpha <= 0.05:
> P1 up needs `beta_c` and `beta_g` >= t_crit; P1 down needs
> `beta_c` <= -t_crit; P2 tighter needs both `kappa` <= -t_crit; P2 wider
> needs both >= t_crit. MAKERS CHARGE MORE PER LEG also needs `beta_g` > 0
> with the largest day dropped and on `refused_too_fine = 0` asks.
> `beta_c` passing without `beta_g` is GROWTH NOT SEPARATED FROM THE DESK'S
> OWN FAIR. Anything else is UNRESOLVED and may not be reported as "no
> markup growth" or "timing does not matter". Floor: 20 asks on 10 distinct
> days, in at least two leg-count levels for P1 and in each arm for P2, and
> at least 80% of asks reconstructed for any `g` test; the 20 leg-count x
> best-quote price-band cells are never tested. Look A: rows before
> 2026-10-08T00:00:00Z. Look B (2027-01-15 cutoff) only for a test whose
> floor missed at A. No look C.

---

## Amendment 1 (2026-10-08): hours to the first game is read on the sportsbook's clock, not Kalshi's

**Written 2026-10-08 with no live row read.** No `combo_rfqs`,
`combo_rfq_quotes`, `parlay_lookups`, `event_links`, `odds_fixtures` or
`kalshi_events` row, and no aggregate of any kind, was looked at for this
amendment. The QueryDef lane (#327) built the instrument and did not run it
against live. Look A has not happened.

**What was wrong.** §3's "hours to first game" cut, and through it the P2 arm
(§1, §4), took each leg's start from `kalshi_events.commence_ms`. That column
is Kalshi's `occurrence_datetime`, and this repo has measured it running late
(`backend/match/linker.py`, the comment above `DEFAULT_COMMENCE_TOLERANCE_MS`):
14 of 18 MLB and 6 of 6 WNBA same-day pairs at plus three hours on 2026-08-07,
then, over 2,263 live links on 2026-09-06, a shift with its mass at three hours
plus up to about 30 minutes of per-fixture noise, with the sign reversed on
some NCAA Football links. P2's edge is 6 hours, so a three-hour error is half
the band. `backend/scoring.py` refuses that clock for the same reason.

**1. The replacement source.** For each leg in `selected_legs`, take the leg's
`event_ticker`, find every `event_links` row whose `kalshi_event_ticker` equals
it, and read `odds_fixtures.commence_ms` for each linked `odds_event_id`. The
leg's start is the `MIN` of those. The ask's **first start** is the earliest
leg start over all its legs. "Hours to first game" is first start minus
`requested_ms`, cut into the same six levels as §3. The P2 indicator is "first
start minus `requested_ms` is at least 0 and under 6 hours", and the other arm
is "6 hours or more".

This is the sportsbook's fixture reached through the matcher's link, which is
the start `backend/scoring.py` scores against. **One difference from that
module, stated so this is not mistaken for a copy of it:** `scoring.py` (like
the slate and the ledger, ticket #26) takes `MIN(odds_snapshots.commence_ms)`
per fixture, the earliest start the feed ever stated. This amendment reads
`odds_fixtures`, the trigger-maintained one-row-per-game table (schema v47,
ADR 0167), which holds the latest start the feed stated. The two agree on
every fixture whose kickoff the feed never moved. The choice is fixed now, and
the snapshot version is not computed.

**2. Unknown, and out of P2.** An ask goes to the **unknown** level, and is out
of P2, if any one of its legs:

- has no `event_links` row (counted as "no link"), or
- has links, but none of its linked `odds_event_id` values has an
  `odds_fixtures` row (counted as "link, no fixture").

A leg's start is never filled in from `kalshi_events.commence_ms`, and never by
shifting that column by a fixed three hours. The lateness was measured as a
shift plus noise, of the opposite sign on some links, and this repo applies it
as a constant nowhere (`OBSERVED_KALSHI_COMMENCE_OFFSET_MS` is read only by
tests). One unknown leg makes the whole ask unknown, because the earliest start
among the other legs may not be the ask's first game.

"Link, no fixture" is not expected: v47's backfill seeded every fixture kicking
off from seven days before its migration (2026-09-18) onward, and the earliest
possible ask dates from schema v45 (2026-09-17). Any found are counted
separately and not explained away.

**3. Already started.** An ask whose first start is before `requested_ms` is in
the "already started" level and out of P2, as §4 already said. Its count is
printed.

**4. What this amendment does not change.** The unit, the cluster, every §2
rule and its order, `f`, `r`, `g` and its reconstruction, the leg-count and
price-band cells, P1 and all four tests, `t_crit`, the alphas, the 6-hour edge,
the floors (for P2, 20 asks on 10 days in each arm after the removals above),
the 80% reconstruction condition, both looks and their cutoffs, the §8
destinations, and the decision rule block, which is read with "under 6 hours"
measured on the clock defined here. `kalshi_events` is still read for one thing
only: `series_ticker`, to reach `kalshi_series.league` for the league-mix cut.

**5. Printed beside P2, counts only, never tested.**

- Asks in the unknown level under this source, split into "no link" and "link,
  no fixture", and of those, how many had a known start on the Kalshi clock
  (the asks that **moved to unknown**).
- Asks whose level among §3's six differs between this source and the Kalshi
  clock, as a 6 by 6 table, and asks whose P2 arm differs (under 6 hours, 6
  hours or more, out of P2). These are point counts. No `kappa` is fitted on
  the Kalshi clock, so there is no second P2 result to choose between.
- Asks with a leg linked to more than one fixture, where the `MIN` decided the
  start.
- Asks in "already started" under this source.

**6. Caveats added to §10, quoted with it in each result.**

- **Start times are the latest known, not as of the ask.**
  `odds_fixtures.commence_ms` is overwritten in place by its trigger whenever a
  newer snapshot states a different kickoff. A game rescheduled after the ask
  is read at its new time, so its ask can land in the wrong level, or in
  "already started" when it had not started at the time of asking. Already
  started asks are counted (point 3) and out of P2. Nothing here can say which
  asks were affected, because that table does not keep the earlier start. This
  replaces the §10 line naming `kalshi_events.commence_ms`, which is no longer
  read for a start.
- **A link is the matcher's claim, not a verified identity.** The start is only
  as right as `event_links`, and the matcher refuses rather than guesses when
  two fixtures fit (an MLB doubleheader), so doubleheader legs are expected
  among "no link".

**7. The instrument.** The QueryDef from lane #327
(`scripts/inspect_live_db_parlays.py`, as committed in `ab57fe54`) reads
`kalshi_events.commence_ms` for the start and must read the source above before
look A. A run of that instrument against live before it does so **is look A**:
P1 stands as run, and P2 is recorded NOT EVALUABLE at look A for this reason
and is not tested at look B either. A run on the wrong clock cannot be set
aside and re-run on the right one, because by then its P2 numbers have been
seen.
