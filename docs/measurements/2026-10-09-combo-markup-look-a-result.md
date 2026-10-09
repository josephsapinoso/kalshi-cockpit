# Combo markup by leg count — look A, result

**Registration:** `2026-10-08-preregistration-combo-markup-by-leg-count.md` and its Amendment 1 (the sportsbook's clock for kickoff), both committed before any row was read (`2c367946`, `9d189c90`). Amendment 2 (the rebuild reads a market's status as of the lookup) was written after this look and before look B; nothing in it changes what this look read.
**Instrument:** `scripts/inspect_live_db.py combo-markup --limit 400 --cutoff 2026-10-08T00:00:00Z`, as built by lane #327 (`92b1d087`) and repaired in `50bc36f6`; run on the live box over `flyctl ssh console` by Joe, from the laptop, through `scripts/wizard_fly_login_and_look_a.sh`, 2026-10-09 ~16:08Z, on the deployed image `50bc36f6`.
**The look:** the output sits in `docs/measurements/data/2026-10-09-combo-markup-look-a.txt`, which `.gitignore` keeps out of the repo on Joe's standing rule (operator data never enters it). This document carries aggregates only: no ticker, no price of any one ask, no date of any one ask, and no cell with a single ask in it.
**A run that printed nothing came first.** The same command was run once before, on image `45a34645`, and died in collection with a `TypeError` before any statistic was computed or printed (#327, comment of 2026-10-09). No number was seen, so that run is not a look. This is look A.
**Audit:** measurement-skeptic, 2026-10-09. Draft verdict **STANDS WITH CORRECTIONS** (twelve); every correction is applied below and the three that changed the reading are named in the audit section at the end.

---

## The verdicts, exactly as the instrument printed them

```
P1 outcome   FLOOR NOT MET: no test run (look B owed if this is look A)
P2 outcome   UNRESOLVED        t_crit(G − 1 = 18) = 2.445
tests        P2 tighter (both kappa <= −t_crit)   False
             P2 wider   (both kappa >= +t_crit)   False
             P1 up / P1 down                      not run (floor)
```

**P1 (does the makers' markup grow with leg count): the floor was missed at look A, so no P1 test ran (§7).** The floor is 20 asks on 10 distinct days in at least two leg-count levels; only the 3-leg level met it (27 asks, 12 days). 2 legs: 10 asks on 7 days. 4 legs: 15 on 11. 6+: 17 on 13. 5 legs: none. By §7, look B (rows before 2027-01-15, #337) is owed for P1 only, `beta_c` and `beta_g`. NOT EVALUABLE is a look-B outcome and is not declared here.

**P2 (is the markup tighter inside 6 hours of the first game) is UNRESOLVED.** Both arms met the floor (under 6 hours: 42 asks on 15 days; 6 hours or more: 27 on 10). `kappa_c = −0.053`, CR1 se 0.148, t = −0.36 against t_crit 2.445. With the largest day dropped: −0.145 (t −0.76). With the rule-6 rows put back: −0.052. With no fair-age limit: −0.056. `kappa_g` could not be computed (below), so P2 could not have passed in either direction at this look whatever `kappa_c` was; the §5 and §7 reading spends P2 here anyway, each test running once at the first look where its floor holds. UNRESOLVED may not be reported as "timing does not matter", and §8 is explicit: **no timing sentence in either direction, including "ask nearer kickoff."**

**`g`, the generous end of the devig band, was reconstructed for 0 of 69 asks**, every one refused as `leg_has_no_fair_row`, a label the rebuild attaches to any leg the ladder excluded for any reason. The 80% reconstruction floor is therefore missed by the whole distance, so no test against `g` could run even if P1's floor had held, and MAKERS CHARGE MORE PER LEG was unreachable from the start of this look. **Very likely the rebuild, not the data.** The rebuild hands the ladder today's `kalshi_markets.status`, and `ladder_candidates` drops a market whose status is terminal (`backend/parlays.py:1117`, `_TERMINAL_STATUSES` at `:107`); `market_results.py:573` and `:598` set the status to `finalized` once a result lands, and every leg in this look is 2 to 22 days past its game. The fair-price downsample is off (`backend/config.py:1032-1033`, not set in `fly.live.toml`) and `retention.py` keeps `fair_prices` out of the prune, so the rows were not removed. A fixture that seeds the market as `finalized` reproduces the miss and reconstructs once the rebuild reads the status as of the lookup (`tests/test_combo_markup_rebuild_on_a_plain_connection.py`, after `50bc36f6`). The repair and its live confirmation are #336; no `g` figure exists for look A and none is restated later.

## The population

| funnel step (registration §2 order) | removed | remaining |
|---|---|---|
| asks scanned before the cutoff (limit 400, not reached) | | 112 |
| 1 requested before cutoff | 0 | 112 |
| 2 purpose = buy | 1 | 111 |
| 3 status quoted | 0 | 111 |
| 4 fair present (same-game and unpriceable cards carry none) | 40 | 71 |
| 5 fair inside (0, 1) | 0 | 71 |
| 6 single-read (re-asked within an open request overwrote its quotes) | 1 | 70 |
| 7 lookup provenance | 0 | 70 |
| 8 fair at most 30 minutes old | 1 | 69 |
| 9–10 best ask representable, ≥ 2 legs (guards the registration does not name) | 0 | 69 |

Primary: **n = 69 asks on G = 19 US-Eastern days**; largest day 17.4% of asks (12); 2 asks (2.9%) on a ticker asked more than once. Rule 6 removed 1.4%, under the 20% line. Observed sd of `r` 0.567 against the planning value 0.10, and sd of leg count 1.39. By §0's formula at n 69, G 19, sd_L 1.39 and t_crit 2.445, the detectable per-leg slope at 80% power is about **3.5% per leg at the planning sigma and about 20% per leg at the observed one**; the spread of markups is far wider than planned, so this look could only have caught a very large slope.

Under Amendment 1's clock, 0 asks fell to the unknown band and 0 were already started; **31 of 69 asks changed hours band versus the Kalshi clock**, so the amendment changed the P2 arms materially.

## Point estimates, never tested (printed because the registration says they are)

**P1 slope against `f`**, the conservative fair: `beta_c = −0.087` per leg (se 0.023, n 69). It is **negative**. §10's confound runs the other way: `f` understates, so markup against it is *overstated*, by more on longer cards, which biases `beta_c` upward; a negative slope is against that bias and is not explained by it. Leg count is aliased with card type in this population: the 3-leg Longshot card sits at +53% (n 7; `ladder.py:37-39` says its fair is understated by construction) against the 6+ leg Lottery card at −12.5% (n 17). Untested. Leave-one-day-out keeps the point between −0.074 and −0.095 on every drop; on `refused_too_fine = 0` asks (n 50) it is −0.033. These are the same untested point estimate re-read with one day removed, not a result.

By price band of the best quote, point slopes only: under 10c −0.38 (n 24), 10 to 25c −0.004, 25 to 50c −0.009, 50c and up +0.019 (n 6). The under-10c slope is the Longshot-against-Lottery contrast above.

**Cells (leg count × best-quote band), medians of the markup as % of `f`**, all below the floor, no interval; a cell with one ask is not shown:

| legs | under 10c | 10 to 25c | 25 to 50c | 50c and up |
|---|---|---|---|---|
| 2 | — | −1.7% (n 2) | +2.3% (n 8) | — |
| 3 | +53% (n 7; IQR +12% to +464%) | −3.9% (n 11) | +1.4% (n 6) | +2.3% (n 3) |
| 4 | n 1, not shown | −3.6% (n 5) | +0.2% (n 6) | +4.0% (n 3) |
| 6+ | −12.8% (n 16) | n 1, not shown | — | — |

A negative cell means the best quote was *below* the desk's conservative fair; a quote below a fair that is already too low is below the truth by more. Under CLAUDE.md's rule 1 that is investigated, not explained: it is one of the things #336 and look B must look at. The one large positive cell (3 legs under 10c, median +53%) is seven asks with a fair near zero, where a tenth of a cent is a large percentage.

**Secondary cuts** (median % of `f`, n): first game under 2 hours away −0.7% (24); 2 to 6 hours +1.4% (18); 6 to 24 hours −2.1% (27). Target up to $1 +0.6% (53); $1 to $5 −1.0% (16). One league −1.7% (28); more than one +0.3% (41). By card: safe +2.1% (9), middle +0.3% (15), short spreads +2.0% (7), totals −3.7% (12), lottery −12.5% (17), longshot +53% (7).

## Dispersion, the one descriptive that needs no `f`

Over the 110 of Joe's own asks that carry two or more stored quotes (quoted asks, with or without a fair; 108 of them carry three or more makers, so this range grows with the number of makers), the spread between the worst and the best maker quote on one ask has **median 11.6c pooled, IQR 4.2c to 24.0c**. The parts do not agree with the pool, so it is not a single figure: cross-game asks with a fair 7.0c (n 70) against same-game or unpriceable asks 22.7c (n 40); by leg count 22.7c at 2 legs (n 20), 12.9c at 3 (n 46, the largest contributor, 42% of the asks), 11.6c at 4 (17), 8.5c at 5 (6), 4.0c at 6+ (21). As a share of the best quote the parts run 67%, 99%, 28%, 249% and 133% against a pooled 97%, which cheap cards inflate. Nobody pays the worst quote, and the figure that would say what the best quote is worth, best against second-best, was not printed.

On the 11 of 69 asks where the public book also carried an ask, the best maker quote was strictly below the book's ask on 10; the book was at or below it once. Counts, on 11 asks.

## What this cannot establish (registration §10, verbatim; Amendment 1's two replacements follow)

- **Not markup against the truth.** The fair `f` is the minimum-of-four Gaussian-copula joint (ADR 0070 §2.1). It is deliberately pessimistic and grows more so with every leg, so markup against it is **overstated**, by more on longer combinations. `g` is the other end of the four methods' band, not the truth. And `g` is **reconstructed** from `fair_prices` after the fact, because no table froze the per-method joint at ask time.
- **Not the fair at the instant of the ask.** The fair was frozen when the card was looked up, up to 30 minutes earlier (rule 8), and the consensus under it has its own age.
- **Not Kalshi's combination market.** Only asks fired from this desk, on combinations this desk minted, at the sizes asked, are in. The population is self-selected by which cards were opened and asked about. Makers may price one requester differently from another, and nothing here can see that.
- **Not other sizes.** Every quote was read at the target size asked, which was small. Markup at a larger size is not measured.
- **Not what is paid.** The best quote is before Kalshi's taker fee, which is charged on acceptance. A quote is not a fill: the maker has a confirmation window and may decline.
- **Not every maker.** Only quotes arriving within the 4-second polling window (`QUOTE_WAIT_S`) are stored, and quotes refused for being priced finer than a tenth of a cent are not stored at all.
- **Nothing about same-game combinations.** They carry no fair, so they have no markup here. They enter dispersion only.
- **Nothing about outcomes, edge or Joe's results.** No settlement, fill, order or position is read. Markup is a cost, not a signal (ADR 0038).
- **Not causal.** Leg count goes together with price, card type and league. A slope over leg count says how markup and leg count moved together on these asks, not what adding a leg would do to a given combination.
- **Not "ask again".** Re-asked rows are left out of the primary (rule 6), and their first prices no longer exist.
- **Not ADR 0139's comparison.** Combinations are not compared with the same legs bought singly.

Amendment 1 replaced the start-time bullet with these two:

- **Start times are the latest known, not as of the ask.** `odds_fixtures.commence_ms` is overwritten in place by its trigger whenever a newer snapshot states a different kickoff. A game rescheduled after the ask is read at its new time, so its ask can land in the wrong level, or in "already started" when it had not started at the time of asking. Already started asks are counted (point 3) and out of P2. Nothing here can say which asks were affected, because that table does not keep the earlier start.
- **A link is the matcher's claim, not a verified identity.** The start is only as right as `event_links`, and the matcher refuses rather than guesses when two fixtures fit (an MLB doubleheader), so doubleheader legs are expected among "no link".

## Consequences (registration §8, Amendment 1 §7)

- **P1: look B owed** (#337, rows before 2027-01-15), for P1 only: `beta_c` and `beta_g`. P2 is spent at look A; there is no look B for P2 and no look C.
- **The `/game` copy** "Each extra leg is one more thing a maker can charge for" (`GameLegs.tsx`) **stays as it is**: no P1 outcome exists, and §8 moves that copy only under MAKERS CHARGE MORE PER LEG, GROWTH NOT SEPARATED or REVERSED.
- **No timing sentence on Ask the market**, in either direction.
- **No "ask again" affordance**: rule 6 shows one re-ask in the window, and the registration says that needs its own registration and a schema change first.
- **#336, before look B:** the rebuild reads a market's status as of the lookup (Amendment 2), and a count over this look's leg tickers confirms on live that `finalized` is what excluded them. Any other cause found there is its own dated amendment.
- **No number from this look enters CLAUDE.md.** The dispersion figure was proposed and withdrawn at audit: its parts disagree with the pool by a factor of five, so there is no single number to state.

## Decision rule and multiplicity (registration §6, verbatim)

**The cells are not tested, because noise alone would light them up.** 20 cells at two standard errors yields about 0.91 false "findings" under no effect at all.

**Exactly four directional tests, each with alpha 0.0125:**

    P1 up       beta_c and beta_g both >= +t_crit   (intersection: both must pass,
                                                      so no correction between them)
    P1 down     beta_c <= -t_crit
    P2 tighter  kappa_c and kappa_g both <= -t_crit
    P2 wider    kappa_c and kappa_g both >= +t_crit

    t_crit = one-sided 0.0125 quantile of t on G - 1 (2.685 at G = 10, 2.423 at G = 21)
    family alpha <= 0.0125 x 4 = 0.05

Each test runs **once**, at the first look where its floor holds (§7), and never again.

**P1 outcomes, exactly one, checked in this order:**

- **MAKERS CHARGE MORE PER LEG:** `beta_c >= t_crit` and `beta_g >= t_crit` and `beta_g` with the largest day dropped `> 0` and `beta_g` on `refused_too_fine = 0` asks `> 0`. The last two are point estimates.
- **GROWTH NOT SEPARATED FROM THE DESK'S OWN FAIR:** `beta_c >= t_crit`, and `beta_g` fails its test, fails a point condition above, or cannot be computed (under 80% reconstructed).
- **REVERSED:** `beta_c <= -t_crit`.
- **UNRESOLVED:** anything else. Per §0, this is the expected outcome for any per-leg charge under about 5%. **It may not be written as "makers do not charge more for more legs".**
- **NOT EVALUABLE:** P1's floor is missed at look B.

**P2 outcomes:** **TIGHTER INSIDE 6 HOURS** (both `kappa` at or below `-t_crit`, and `kappa_g` with the largest day dropped `< 0`), **WIDER INSIDE 6 HOURS** (both at or above `+t_crit`, and `kappa_g` with the largest day dropped `> 0`), **UNRESOLVED**, or **NOT EVALUABLE**. UNRESOLVED may not be written as "timing does not matter".

**No running figure, anywhere.** No screen, route, push, log line, instrument or ticket may compute a running markup by leg count, by price band or by time to kickoff from `combo_rfqs`. A threshold re-read against a growing table is thousands of looks, and under no effect it crosses eventually with probability 1 (13.7% measured in this repo, and that is a floor). **If such a surface is built, this registration is spent.** A per-row fact (this ask's quote beside this ask's fair) is allowed and already exists. ADR 0164 Decision 6 still binds: the gap is never labelled cheap, good or edge, and nothing is ordered by it.

## Decision rule, verbatim (registration, "Registration status")

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

One reading of that rule against this look, stated so it is not argued later: "P1 down needs `beta_c <= −t_crit`" names `beta_c` alone, and `beta_c` here is 3.80 standard errors below zero against a t_crit of 2.445. **It was not tested**, because the floor clause ("in at least two leg-count levels for P1") failed first, and the floor governs whether any test runs. Had the floor held, the registered outcome would have been **REVERSED**, whose §8 consequence is a #302 ticket proposing removal or replacement of the extra-leg sentence. The floor did not hold, so there is no outcome and the copy stays. Look B carries that reading forward, with `g` repaired.

## Audit (measurement-skeptic, 2026-10-09)

Draft verdict STANDS WITH CORRECTIONS. Every number matched the raw output except two (a cell's n, and "beat or matched" for a column that counts strict wins). Three corrections changed the reading and are the reason this section exists: the draft had §10's confound backwards (it said the desk's pessimism makes longer cards look cheaper; §10 says it makes markup against `f` *overstated*, so the negative slope runs against the bias, not with it); the draft named the counterfactual outcome wrongly (it is REVERSED, with its own consequence, not "growth not separated"); and the draft called the `g` miss "not established" when the code says where it comes from. The proposed CLAUDE.md number was withdrawn because its parts disagree with the pool. Two single-ask cells were removed. The audit's full list is on #327.
