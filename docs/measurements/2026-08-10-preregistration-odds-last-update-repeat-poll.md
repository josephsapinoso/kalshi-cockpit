# Pre-registration — does `last_update` advance without a reprice?

**Written 2026-08-10 (UTC).** `tasks/NEXT.md` queue item 1 / `start.md` "Waiting
on Joe". The capture Joe authorised: **24 Odds API credits, one shot.**

*(The host clock reads 2026-08-09 local. Every sibling document in this
directory is dated in UTC and the repo's own day has rolled, so this file is
dated 2026-08-10 UTC to sort correctly beside them. Both are recorded so nobody
has to reconcile them later.)*

- Owner: `pre-registrar` (agent), on behalf of Joe.
- Scored against by: `measurement-skeptic`, after the run.
- Negative-result destination: fixed in §9, before the result exists.
- Form matched to
  [`2026-08-10-preregistration-fresh-odds-edge-distribution.md`](2026-08-10-preregistration-fresh-odds-edge-distribution.md)
  and
  [`2026-08-10-preregistration-clean-shortfall-distribution.md`](2026-08-10-preregistration-clean-shortfall-distribution.md).

> **Status: READY, and NOT YET RUNNABLE.** Seven preconditions are listed in §P.
> Two of them (**P0** commit, **P1** budget headroom) are outside this agent's
> permission to satisfy. The capture must not be started until all seven are
> ticked.

> **This registration spends ZERO alpha.** It runs no interval test, computes no
> standard error and quotes no p-value — deliberately, for the reason in §6. The
> `0.05 / 3` Bonferroni budget shared by the fresh-odds and devig-calibration
> registrations is **not** touched and must not be re-divided on account of this
> document.

---

## §0. What had already been observed when this was written

**Not a blind registration.** The prior single-poll evidence is published in
three places in this repo and has been read. Everything seen is listed here so a
reader can judge what was knowable when these rules were set.

### §0.1 Seen — the published inference

**[MEASURED FROM DATA — `tests/fixtures/odds_mlb_h2h_spreads_totals.json`,
one `/v4/sports/baseball_mlb/odds` capture, `captured_ms = 1786110562317`;
published in `docs/adr/0019` §9 and `backend/core/suppression.py:210-218`]**

```
15 MLB events, 30 bookmakers, us+eu, h2h+spreads+totals, decimal
440 of 440 book+event triples carry one identical stamp across the three markets
27 of 30 books carry exactly ONE distinct stamp across all fifteen games
FanDuel reports 13:49:00Z for three markets on fifteen different games
```

### §0.2 Seen — structural counts re-derived from that same fixture, today

**[MEASURED FROM DATA — structure and coverage only. No `last_update` value and
no `price` value was read, printed or aggregated while writing this document.]**

```
events                                    15
distinct bookmakers                       30
(book, event) pairs, priceable            440
(book, event, market) triples, priceable  1018
priceable outcome rows                    2036
market keys returned         h2h, spreads, totals, h2h_lay   <- lay is dropped
markets-per-pair histogram   1 market: 120   2 markets: 62   3 markets: 258
events-per-book histogram    13 events: 5 books   15 events: 25 books
`last_update` present at MARKET level on every market object   (all True)
`last_update` present at BOOKMAKER level on every bookmaker     (all True)
h2h outcomes carry no `point`; spreads and totals do
```

These are the `n` inputs for the power check and the reachability check. They
are properties of the wire format and of coverage, not of the quantity under
test.

### §0.3 What has NOT been seen, by anyone

No `last_update` value has been compared against another `last_update` value at
a **different fetch instant**, by anyone, ever. That comparison does not exist
in this repository, in any measurement file, or in any session transcript. It is
the entire content of this measurement, and the single-poll fixture is
structurally incapable of containing it.

No poll of the slate that will actually be captured has been made. The events
have not been listed. Not one credit has been spent on this measurement.

### §0.4 Provenance labels

Every quantity below is labelled **[COMPUTED FROM CODE]**, **[MEASURED FROM
DATA]** or **[ASSUMED]**. `tasks/lessons.md`: *arithmetic that reproduces to the
digit says nothing about its inputs.*

**There is exactly one assumed input in the whole design: the aggregator's own
scrape period, which is undocumented to us and has never been measured.** It
appears only in the *justification* of the poll schedule (§5), never in a
threshold, and the schedule is deliberately built as a four-point sweep across
two decades of interval precisely so that the design does not depend on that
assumption being right.

---

## §C. Corrections to the claim as written, made before the design was fixed

Four things in the brief, in `tasks/NEXT.md` and in `start.md` are wrong,
overstated, or arithmetically off. Recorded rather than quietly fixed, because
all three will be read again.

### C1. "440 of 440 book+event triples" — the informative denominator is 320, not 440

**[MEASURED FROM DATA — §0.2]** There are **440 (book, event) pairs** and
**1018 (book, event, market) triples**. The published sentence uses "triples" to
mean "the market triple within a pair", which is defensible, but the arithmetic
underneath it is not:

**120 of the 440 pairs carry only ONE priceable market.** For those 120 pairs
the claim *"one identical stamp across h2h, spreads and totals"* is **vacuously
true** — there is one stamp because there is one market. A further 62 carry two.
**Only 258 pairs carry all three.**

So the prior evidence is:

| Denominator | Count | What a match there means |
|---|---:|---|
| Pairs with 3 markets | **258** | The claim as stated, fully tested |
| Pairs with 2 markets | 62 | A weaker version of the claim |
| Pairs with 1 market | **120** | **Vacuous — cannot fail** |
| Reported denominator | 440 | Includes 120 cells that could not have disagreed |

**Registered consequence.** §S2 item 3 requires the within-poll agreement print
to be reported over the **320 pairs with ≥2 markets**, with the 120 vacuous
pairs stated separately and never folded into a numerator. This is the repo's
own rule — *a control must be able to reach the confound it was built for* —
applied to the prior finding rather than to the new one. It does not overturn
the prior inference; it corrects its stated strength.

### C2. "It measures our polling cadence" is not a claim this capture can support

The stamp cannot measure *our* polling cadence: The Odds API scrapes its books
on **its own** schedule and serves whatever it last stored, whenever we ask.
Our cadence only determines when we sample it. The supportable claim is about
**the aggregator's scrape cadence**, and the two are distinguishable — §S2 item
7 registers the diagnostic that separates them (`delta_stamp` vs
`delta_fetch`), as a **descriptive print, not decision-bearing**.

**Registered consequence.** The hypothesis in §1 says *"not a per-line reprice
timestamp"*. It does **not** say *"our polling cadence"*, and neither ADR 0020
nor any write-up scored against this document may use that phrasing on the
strength of this capture.

### C3. Distrusted universals, weakened here where it is free

Three universals in the record as written, each tested as written if left alone:

| As written | Where | Registered form |
|---|---|---|
| *"It measures our polling cadence, **not** line freshness"* | `NEXT.md`, `start.md` | See C2. Weakened to a thresholded claim about a share (§1). |
| *"**No** book reprices fifteen moneylines, run lines and totals in the same second"* | `suppression.py:215` | Plausible, and **not** established by a single poll. This capture bears on it only indirectly; it is not the registered hypothesis and must not be quoted as its outcome. |
| *"**every** price byte-identical"* | the brief | Kept as written but given an exact predicate (§5.3), including what "byte-identical" means for a `float` and for `Optional[float]`. Without that, "every" is unenforceable. |

### C4. The default budget refuses the **third** call, not the fourth

The brief says `ODDS_DAILY_CREDIT_BUDGET = 16` "would refuse the 4th call".
**[COMPUTED FROM CODE — `budget.py:66` `sweep_cost`, `budget.py:178`
`can_afford`, `config.py:194` default 16]** the arithmetic, from zero prior
spend in the sports-day:

| Call | Cost | Spent after | `remaining_today` before | Verdict at budget 16 |
|---:|---:|---:|---:|---|
| 1 | 6 | 6 | 16 | allowed |
| 2 | 6 | 12 | 10 | allowed |
| 3 | 6 | — | **4** | **REFUSED** — `4 < 6` |
| 4 | 6 | — | 4 | REFUSED |

The **third** call is the first refusal, and `fetch_odds` returns `[]` rather
than raising (`client.py:233-234`), so a refusal is indistinguishable from an
empty slate at the call site. Worse: the sports-day rolls at **10:00 UTC**
(`budget.py:139`, `DEFAULT_DAY_START_UTC_HOUR`), not at midnight, and the live
runner spends against the same counter, so any prior spend moves the refusal
earlier still.

**Registered consequence — P1 in §P.** The precondition is not "set the budget
to 24". It is **`CreditBudget.state(T0).remaining_today >= 24` and
`remaining_this_month >= 24` and `remaining_reported >= 24`, all three read and
printed before poll 1.** Whatever value of `ODDS_DAILY_CREDIT_BUDGET` achieves
that is the value to set.

---

## §P. Preconditions — every one is a yes/no, checked before poll 1

If any is NO the capture does not run and this document is amended rather than
worked around.

- **P0 — this file is committed.** A pre-registration that exists only in a
  working tree has not been pre-registered. The capture script must not be
  executed until `git log` shows this file on `main`. **This agent has not
  committed it; that is the caller's action and it is the first one.**
- **P1 — budget headroom, measured not assumed (§C4).** `remaining_today >= 24`
  **and** `remaining_this_month >= 24` **and** the server's own
  `x-requests-remaining >= 24`, printed before poll 1 and again after poll 4.
  **A `[]` return from `fetch_odds` is a refusal, not a finding.** If any poll
  returns `[]`, the capture ABORTS, the fact is recorded, and no verdict is
  issued from a partial capture except under the rule in §8.
- **P2 — the key cannot reach a file or a log line.** The capture script calls
  `backend.logging_setup.configure_logging()` as its first statement; it never
  logs, prints, or serialises `response.url`, `response.request.url`, or
  `config.api_key`; and **before writing each artefact it asserts
  `config.api_key not in serialised_text` and `"apiKey" not in serialised_text`.**
  The Odds API takes its key as a **query parameter** and `httpx` logs the full
  URL at INFO — that is exactly how it leaked once, and
  `backend/logging_setup.py` exists because of it. **The repo is public; these
  artefacts are world-readable the moment they are pushed.**
- **P3 — the script is written and reviewed before the first call.** Not typed
  live against a running clock. The four polls are 60/300/900 s apart and there
  is no second attempt at this slate.
- **P4 — the slate rule is satisfiable today (§2).** No event in the sport's
  returned slate commences within the 20 minutes following `T0`, **and** at
  least 5 events commence within the 6 hours following `T0`. Both are decided
  from a **zero-credit** source (the ESPN scoreboard path already used by
  `scripts/measure_slot_coverage.py`, or Kalshi's own event list). If the rule
  cannot be met, the capture waits for a day when it can.
- **P5 — the deployed parser is reused, not reimplemented.** Row projection is
  `OddsClient._parse(...)` (`client.py:273`), so the population analysed is the
  one the deployed guard actually sees: `h2h_lay` excluded, prices ≤ 1.0
  dropped, market-level `last_update` preferred over bookmaker-level. A bespoke
  parser would answer a question about a different set of rows.
- **P6 — the four raw payloads are written to disk before any analysis runs.**
  The analysis script reads only those files. This makes every number
  re-derivable offline, forever, without spending a credit — and it means a
  re-run after a bug fix costs nothing.

---

## §1. The question, as a claim that could be false

**Primary hypothesis, one-sided, directional:**

> Between two polls of the same slate separated by ~300 seconds, among
> bookmakers whose `last_update` advanced on at least one of their (book, event)
> pairs, the **mean across bookmakers** of the within-bookmaker share of
> advanced pairs on which **not one** priced outcome changed is **at least
> 0.90**.

Call that statistic **`S`** (§6). The registered claim is `S >= 0.90`, i.e. the
stamp advances without a reprice of the line it is attached to. `S <= 0.20` is
the opposite claim — the stamp advances *because* the price moved — and it is a
live, registered outcome. Everything between is UNRESOLVED and that is a real
answer, not a failure.

**What `S >= 0.90` licenses, exactly.** That `last_update` is **not a per-line
reprice timestamp**, and therefore that `odds_age_ms` and the `stale_odds`
suppression code do not measure the freshness of the line being priced. It does
**not** license "it measures our polling cadence" (§C2), and it does **not**
license "our odds are stale" — a scrape clock is perfectly compatible with
every book being genuinely fresh (§10).

**Secondary, strictly stronger, deterministic count (no threshold of its own):**

> **`S_strict`** — the share of advancing bookmakers for which **not one price
> changed anywhere in the entire captured slate**, across every event, market
> and outcome.

`S_strict` cannot change the verdict. It decides only **which wording ADR 0020
is permitted to use** (§9), because it is the only version immune to the
cross-event bleed described in §10.

**Why the direction is fixed here.** A two-sided test reported one-sided after
the fact doubles its own false-positive rate. The prior inference points one
way; the threshold that would refute it is written down at the same time as the
threshold that would confirm it, and they are not adjustable.

---

## §2. The population, and the exclusions

### Included

Every `OddsQuote` returned by `OddsClient._parse` for **`baseball_mlb`**, region
set `us,eu`, markets `h2h,spreads,totals`, in each of four polls, subject to the
exclusions below. No sampling, no cap, no ordering: the whole returned slate
enters.

### Excluded, with the reason each exclusion is independent of the outcome

| Excluded | Why | Independent of the stamp/price outcome? |
|---|---|---|
| `h2h_lay`, `spreads_lay`, `totals_lay`, `h2h_h2h` | Already dropped by the deployed parser (`EXCLUDED_MARKETS`, `client.py:111`). A lay price is the other side of the transaction and never reaches the consensus. | Yes — a market-key classification fixed in source before this capture. |
| Any event with `commence_ms < fetched_ms` of poll 4 | The market goes in-play: books suspend, re-open and swing on a different process entirely. In-play is explicitly out of scope (`docs/adr/0006`). | Yes — a schedule fact, known before poll 1, decided from `commence_time`. |
| Any event, book or row present in one poll of a compared pair and absent from the other | Absence is not evidence about a stamp. See the ABSENT accounting below — it is **excluded and counted**, never imputed. | Yes — a presence test, evaluated without reading a stamp or a price. |
| Any (book, event) pair whose row-key set is not unique within a poll (§5.3) | A duplicate key means the comparison is undefined. Marked **KEY-DEGENERATE**, excluded, counted, **never silently de-duplicated**. | Yes — a structural property of the payload. |

### Retained deliberately, and the temptation named in advance

**Every bookmaker is retained. There is no per-book exclusion in this design and
none may be added after the run.**

That includes the betting exchanges — `betfair_ex_eu`, `betfair_ex_uk`,
`matchbook` — which quote continuously and are therefore the books **most
likely** to genuinely reprice inside 300 seconds. Excluding them would flatter
the hypothesis, which is precisely why they stay. It also includes the four-book
sharp set that actually anchors the consensus
(`runner.py:103` — `{pinnacle, betfair_ex_eu, betfair_ex_uk, matchbook}`); that
subgroup is a **descriptive print** (§S2 item 6) and cannot declare anything,
because `n = 4` is below the repo's `MIN_EXPECTED_PER_SIDE` floor of 5. Read
`n` before the effect size.

### The rule that must not be activated after the fact

If `S` lands in the mid-band the temptation will be to drop the books that spoil
it — the exchanges, the sparse-coverage books, the one outlier. **That is
forbidden.** The precedent is in this repo: a combo experiment pre-registered an
exclusion and the agent correctly *refused to activate it* when the sample came
in thin. That refusal was only possible because the rule was in writing first.

**No exclusion in this document references a `last_update` value, a price value,
or `S`.** Every one is decidable from the schedule, the market key, or the
presence of a row.

---

## §3. The unit of observation, and what makes two units independent

This is the section where `n` gets inflated, and here the inflation would be
**tenfold**.

| Level | Count per poll **[MEASURED — §0.2]** | Independent? |
|---|---:|---|
| outcome row | 2036 | **No.** Two outcomes of one market move together by construction. |
| (book, event, market) triple | 1018 | **No.** §0.1 says all three markets of a pair share one stamp. |
| (book, event) pair | 440 | **No.** 27 of 30 books carry ONE stamp across all fifteen games. |
| **bookmaker** | **30** | **The registered clustering variable.** |
| the aggregator | 1 | **Possibly the true unit — see below.** |

**The clustering variable is `bookmaker`.** `S` is a mean across bookmakers of a
within-bookmaker share (§6), never a pooled count over 440 pairs. This repo
shipped a gate that counted 400 rows on one ticker as 400 observations and the
fix was clustering; the same failure here would report `n = 440` for what may be
30 observations, or one.

**And the honest version, stated before the run rather than after.** If the
hypothesis is true in its strongest form — one scrape process at the aggregator
serving every book — then all 30 books share one clock and the **effective `n`
is 1**. There is no credit spend that fixes this. It is the central fact of the
power check (below) and it is why this design uses a **deterministic threshold
on a near-deterministic signature** and computes **no standard error anywhere**.

`n_rows`, `n_pairs` and `n_books` are printed side by side, always, everywhere.

---

## §4. Allocation of the 24 credits — the choice, and what it costs

**[COMPUTED FROM CODE — `sweep_cost(markets, regions) = len(markets) ×
len(regions)`, `budget.py:66`]** `3 × 2 = 6` credits per sport per poll.
24 credits = **exactly 4 calls**. No fifth call exists in this design.

### The choice: 1 sport × 4 polls, not 2 sports × 2 polls

**Chosen: `baseball_mlb`, four polls at `t0`, `t0+60s`, `t0+300s`, `t0+900s`.**

The two aims in `NEXT.md` conflict at 24 credits and the brief says the primary
wins. It does. The reasoning, so it can be checked rather than trusted:

1. **2 sports × 2 polls forces the whole result through one guessed interval.**
   The aggregator's scrape period is unknown to us and unmeasured
   **[ASSUMED — the single assumed input of §0.4]**. If the guess is shorter
   than that period, **no stamp advances anywhere** and the confirming outcome
   is *unreachable* — 24 credits buy a guaranteed UNRESOLVED. If the guess is
   long enough that genuine reprices are expected, an advancing stamp is
   uninformative and the refuting outcome swallows everything. A design whose
   verdict depends on a parameter nobody has measured is the design this
   registration exists to prevent.
2. **4 polls on one sport make the interval an observed variable rather than an
   assumption.** Four instants give **six** pair-intervals — 60, 240, 300, 600,
   840 and 900 s — spanning more than a decade. The *shape* of the advance rate
   against interval is itself the discriminator and it is far harder to produce
   by coincidence than any single number:

   | If the stamp is… | advance rate vs interval | price-change rate vs interval |
   |---|---|---|
   | a scrape clock | pinned near 1 at every interval past the scrape period, **flat** | rises with interval, **decoupled** |
   | a reprice timestamp | rises with interval, **tracking** the change rate | rises with interval |

3. **It builds in its own reachability fallback.** If 300 s turns out to be
   shorter than the scrape period, the 900 s pair is already in hand and is
   registered *in advance* (§7) as the substitute primary. Under 2 × 2 there is
   no second interval to fall back to, at any price.
4. **The 900 s point is the deployed threshold.** `MAX_ODDS_AGE_S = 900`
   **[COMPUTED FROM CODE — `config.py:380`, `.env.example:71`]**. Sampling
   exactly there turns the operational question — *can the guard ever bind?* —
   into a directly measured count rather than an extrapolation.
5. **Four polls give four free within-poll reproductions** of the §0.1
   440-of-440 claim, at four independent instants, corrected per §C1. A single
   poll per sport gives one each.

### What this costs, stated plainly

**League generalisation is abandoned.** This capture says nothing about WNBA,
nothing about a low-liquidity league, and nothing about the posting-time
stratum `NEXT.md` wanted to reach. If `last_update` semantics differ by sport —
which is not implausible, since coverage and scrape priority plainly differ —
this measurement will not detect it. That limitation is registered in §10 and
must appear in the write-up. Recovering it costs a further 12 credits and needs
its own registration; it is **not** licensed by this one.

**MLB rather than WNBA** because MLB is where the prior evidence sits (so the
within-poll control is a true reproduction rather than a new claim), and because
MLB in August supplies ~15 events × 30 books = 440 pairs against WNBA's handful
— roughly an order of magnitude more units for the same 6 credits.

---

## §5. The cut — the schedule, the pairs, and the equality predicate

Every boundary in this section is fixed here. None may be re-derived after the
run.

### 5.1 The poll schedule

| Poll | Nominal instant | Cost |
|---:|---|---:|
| 1 | `T0` | 6 |
| 2 | `T0 + 60 s` | 6 |
| 3 | `T0 + 300 s` | 6 |
| 4 | `T0 + 900 s` | 6 |

**Why 300 s is the primary interval, and why not shorter or longer.** The brief
asks for this reasoning explicitly and it is the crux of the design.

- **Too short (≤ 30 s).** Below the aggregator's scrape period nothing advances
  for anyone. Every pair lands in "static & identical", which is consistent with
  *both* hypotheses and therefore says nothing — and the confirming cell is
  **arithmetically unreachable**, which is the defect this repo has now been
  bitten by twice.
- **Too long (≥ 900 s).** A genuine reprice of a pre-game MLB line inside 15
  minutes is entirely ordinary. "Stamp advanced" then carries little
  information, the identical-price cell drains, and the instrument's resolving
  power collapses in the other direction.
- **300 s is where both cells are populated.** It is roughly 5× any plausible
  scrape period, so the advance is expected to be near-universal under the
  hypothesis; and it is short enough that most books, on most pre-game lines,
  will not have moved a number — so the identical-price cell survives. It is
  also deliberately **not** the deployed 900 s threshold, so the primary verdict
  is not entangled with the guard's own configuration.
- **60 s and 900 s bracket it** and are reported as points on the curve. 900 s is
  additionally the interval **least favourable to the hypothesis**, which is why
  it is in the design at all: a registration that samples only where its
  hypothesis is comfortable is not a test.

**Interval slippage.** The primary pair is **poll 1 → poll 3, by index**, not by
realised interval. The *realised* deltas are recorded and printed. Selecting the
pair "closest to 300 s" after the fact would be choosing a cut from the data.
Nothing selects a pair by its realised interval, ever.

### 5.2 The six pairs, and which one decides

| Pair | Nominal Δ | Standing |
|---|---:|---|
| **1 → 3** | **300 s** | **PRIMARY.** Decides §7. |
| 1 → 4 | 900 s | **REGISTERED FALLBACK PRIMARY**, and only if precondition PC2 fails on 1→3 (§7). Also supplies the operational corollary count. |
| 1 → 2 | 60 s | Descriptive — a point on the curve. |
| 2 → 3 | 240 s | Descriptive. |
| 3 → 4 | 600 s | Descriptive. |
| 2 → 4 | 840 s | Descriptive. |

**Exactly one pair decides**, and its substitute is named in advance with a
stated trigger. The other four are curve points and **cannot declare anything**.

### 5.3 The comparison key and the equality predicate, exactly

The brief asks what "byte-identical" means. This is it.

**Row key, within a poll:**

```
(odds_event_id, bookmaker, market, outcome_name)
```

**`outcome_point` is deliberately NOT in the key.** It is
`Optional[float]` (`client.py:137`) and it is *both* an identifier of a
spreads/totals outcome *and* a thing a book moves. If the hook were in the key,
a book moving a total from 8.5 to 9.0 would read as one row disappearing and a
new one appearing — a **real reprice recorded as an absence**, which flatters
the hypothesis by removing a change from the denominator. Keeping it out of the
key makes a hook move a **change**, which is the conservative direction.

**Compared value tuple:**

```
(outcome_point, price_decimal)
```

**Equality predicate `P`:** exact tuple equality. `None == None` is True. Float
comparison is **exact `==`** — no tolerance, no `math.isclose`, no rounding, no
`round(x, 4)`. A tolerance is a free parameter, and a free parameter chosen
after seeing the distribution of differences is the finding wearing a
threshold's clothes. Decimal odds arrive as JSON number literals; two identical
literals parse to bit-identical floats, so exact equality is both the strictest
predicate and the correct one.

**Byte-level cross-check, as a defect count.** The raw JSON token for each price
is retained alongside the parsed float, and text equality is computed in
parallel. The two must agree on every compared row. Any disagreement is printed
as `TEXT_FLOAT_MISMATCH` and, if non-zero, the write-up states the count; this
is the "byte-identical" claim made literally rather than by proxy.

**Uniqueness.** If a row key appears more than once within a poll for one
(book, event) pair, that pair is **KEY-DEGENERATE**: excluded, counted, printed.
Never de-duplicated. (Alternate lines arrive under `alternate_spreads` /
`alternate_totals`, which are not requested, so this is expected to be zero —
which is exactly why it must be asserted rather than assumed.)

### 5.4 Absence, and what happens to a book that vanishes

The brief asks this directly.

For a compared pair of polls, each (book, event) pair falls in exactly one of:

| Class | Definition | Treatment |
|---|---|---|
| **BOTH** | present in both polls, key sets `K1`, `K2`, compare on `K = K1 ∩ K2` | enters the statistic |
| **ABSENT-2** | in poll 1, not poll 2 | excluded, counted, printed |
| **ABSENT-1** | in poll 2, not poll 1 | excluded, counted, printed |
| **ROWSET-CHANGED** | in BOTH but `K1 ≠ K2` | **stays in the statistic**, compared on `K`, and flagged and counted separately. A book adding or dropping a market is not a price change and must not be scored as one; but it is a fact about the pair and it is printed. |

**Attrition precondition (PC3, §7).** If `|BOTH| < 0.80 × |poll-1 pairs|` the
verdict is **UNRESOLVED**. Differential attrition selects which books we see,
and a rate computed on a self-selected 60% is a rate about an unknown
population. 0.80 is arbitrary; it is fixed here, which is the entire point.

### 5.5 The four cells, defined at the (book, event) pair level

For each **BOTH** pair, over the intersected key set `K`:

- **`advanced`** := `max(book_updated_ms in poll B over K) > max(... in poll A over K)`,
  strict integer comparison in ms. (`last_update` is second-resolution ISO;
  polls are ≥ 60 s apart, so second-rounding cannot manufacture or hide an
  advance.)
- **`regressed`** := the same quantity **decreased**. A stamp going backwards is
  a defect cell — cached or sharded responses — and is counted separately.
- **`identical`** := `P` holds for **every** key in `K`.

|  | identical | some price changed |
|---|---|---|
| **advanced** | **A** — the confirming cell | **B** — the refuting cell |
| **static** | **C** — uninformative for either | **D** — defect: a reprice with no stamp advance |

`D > 0` is inconsistent with `last_update` being a reprice timestamp for those
rows. It is **printed with that reading and does not enter `S`**, because it
would be a second mechanism smuggled into one statistic.

---

## §6. The statistic, named as an estimator

### `S` — a bookmaker-clustered mean of within-bookmaker shares

> For each bookmaker `b` with at least one **advanced** BOTH-pair, let
> `s_b = |A_b| / (|A_b| + |B_b|)` — the share of *that bookmaker's* advancing
> pairs on which not one price changed.
> **`S` is the unweighted mean of `s_b` over those bookmakers.**
> `N_adv` is the number of such bookmakers, and it is the `n` of this
> measurement.

Said out loud, as the brief requires: **`S` is a mean of bookmaker-clustered
observations**, not a proportion. Its null is not a binomial null and
`sqrt(p(1-p)/n)` is **wrong for it** — that formula, applied to the 440 pairs,
would report a standard error roughly `sqrt(440/30) ≈ 3.8×` too small even if
the books were independent, and they are not (§3).

The pooled pair-level share `|A| / (|A| + |B|)` is printed **beside** `S`, along
with the largest single bookmaker's share of the pooled denominator, per the
repo rule that *a pooled number is not a finding until the parts agree*.

### `S_strict` — a share of bookmakers, immune to cross-event bleed

> Among the same `N_adv` bookmakers, the share for which **not one price changed
> anywhere in the captured slate** between the two polls — every event, every
> market, every outcome.

Because 27 of 30 books carry one stamp across all fifteen games **[§0.1]**, a
stamp advance on game *X* may have been caused by the book repricing game *Y*.
`S_strict` excludes that by construction. It is **reported, never
decision-bearing** (§7), and it decides ADR 0020's permitted wording (§9).

### `R` — the advance rate, which is the reachability check

> `R = (|A| + |B|) / |BOTH|` at pair level, and `N_adv / n_books` at book level.

`R` is printed **before** `S`, always. If nothing advanced, `S` is a ratio over
an empty denominator and the confirming cell was unreachable — which is a fact
about the instrument, not about the stamp.

### `movers` — the control, and the reason it exists

> `movers` = the number of distinct bookmakers with **at least one** changed
> price anywhere in the slate, over the full 900 s span (poll 1 → poll 4).

**This is the most important number in the document.** On a frozen slate, no
price changes anywhere, every advancing pair lands in cell **A**, and `S = 1.0`
is declared on data that could not have produced any other answer. That is the
repo's own scar — *a control must be able to reach the confound it was built
for* — and `movers` is the guard against it. Its threshold is in §7 and its
failure direction is UNRESOLVED, never a declaration.

### No standard error is computed, anywhere, and that is deliberate

Under the hypothesis being tested the bookmakers may not be independent at all
(§3). An interval computed over 30 correlated books, or over 440 pairs of them,
would be a number that gets quoted and that means nothing. **The design instead
asks whether the signature is near-deterministic, with the thresholds fixed in
advance.** That is a weaker instrument, honestly labelled, and it is the
strongest one 24 credits can buy on this question.

---

## §7. The decision rule, with the multiplicity already counted

### How many things are tested

| Family | Cells | Standing |
|---|---:|---|
| `S` at the primary pair | **1** | **Decision-bearing. Deterministic threshold. Zero alpha.** |
| Registered fallback (1→4), only on PC2 failure | 1 | A substitution, not an additional test |
| `S_strict` | 1 | Wording only (§9) |
| Operational corollary at 900 s | 1 | A count, pre-registered reading, cannot change the verdict |
| Pair-interval curve (6 intervals × 2 statistics) | 12 | Descriptive |
| Per-bookmaker breakdown | 30 | Descriptive |
| Per-market breakdown | 3 | Descriptive |
| Per-event breakdown | 15 | Descriptive |
| Sharp-set subgroup | 1 | Descriptive, `n = 4`, **below the floor of 5 — cannot declare** |
| Within-poll agreement reproduction | 4 | Descriptive reproduction |

**≈ 65 descriptive cells.** At a conventional two-standard-error rule that would
be `65 × 0.0455 ≈ 2.96` expected false findings and P(at least one clears from
nothing) ≈ **0.95**. This project has already produced a 20-point "finding" at
two standard errors from data generated with **no edge in it whatsoever**, and
the predecessor produced dozens from 1,190 cells.

**No standard error is computed for any of the 65**, precisely so that none of
them can produce that finding. **A descriptive cell may not declare, refute, or
qualify anything.** If one is quoted as a result, the write-up is defective.

**Zero alpha is spent by this document**, and the `0.05 / 3` budget shared by
the fresh-odds and devig-calibration registrations is unchanged. A deterministic
rule dodges multiplicity by construction — *provided the thresholds were fixed
before the data existed*, which is what §P0 is for. A deterministic rule with a
threshold chosen afterwards is worse than a p-value, not better.

### The decision rule, verbatim

> **All preconditions are evaluated and printed FIRST, before `S` is computed
> or displayed. If any fails, the verdict is UNRESOLVED with the named reason,
> and `S` is still printed — labelled `UNRESOLVED — DOES NOT DECIDE`.**
>
> **PC1 — book coverage.** `n_books`, the bookmakers present in both polls of
> the compared pair, is `>= 20`. (Prior capture: 30.)
> **PC2 — the confirming cell is reachable.** `N_adv >= 5`, the repo's
> `MIN_EXPECTED_PER_SIDE` floor. **If PC2 fails on the primary pair (1 → 3) and
> only then, the compared pair becomes the registered fallback (1 → 4) and every
> rule below is re-applied to it unchanged. This substitution happens at most
> once, and no other pair may ever become primary.**
> **PC3 — attrition.** `|BOTH| >= 0.80 × |poll-1 pairs|` (§5.4).
> **PC4 — integrity.** `D <= 0.05 × |BOTH|` **and** `regressed <= 0.05 × |BOTH|`
> **and** `KEY-DEGENERATE == 0` **and** `TEXT_FLOAT_MISMATCH == 0`.
> **PC5 — the control can reach the confound.** `movers >= 5` distinct
> bookmakers changed at least one price somewhere in the slate over the full
> 900 s span. **If `movers < 5` the verdict is UNRESOLVED — QUIET SLATE, however
> high `S` is**, because "no price changed" carries no information when nothing
> changed anywhere.
> **PC6 — the spend is real.** All four polls returned a non-empty list, and the
> server's `x-requests-used` advanced by 24 across the capture. A `[]` return is
> a refusal (§C4), not a slate.
>
> Given **every** precondition met:
>
> **CONFIRMED — `last_update` is not a per-line reprice timestamp.**
> Declared if and only if **`S >= 0.90`**.
>
> **REFUTED — `last_update` tracks reprices.**
> Declared if and only if **`S <= 0.20`**.
>
> **UNRESOLVED.**
> Declared in every other case, including `0.20 < S < 0.90` and any precondition
> failure. **UNRESOLVED is a real answer and it is reported with the same
> prominence as the other two.**
>
> **THE MANDATORY QUALIFIER ON A CONFIRMATION.** If CONFIRMED is declared,
> `S_strict` is reported on the same line, and:
> — `S_strict >= 0.90`: the write-up may say the stamp advanced with **no
> observed reprice anywhere**, and ADR 0020 may use the strong wording.
> — `S_strict < 0.90`: the verdict stands, and the write-up **must** state, in
> these words, that *the confirmation rests on pair-level identity; the stamp is
> book-scoped, so a reprice on another game in the same slate cannot be excluded
> as the cause of the advance.* ADR 0020 is then restricted to the claim that
> `odds_age_ms` is **not a per-line freshness measure** — which is the claim the
> guard's behaviour actually turns on either way.
> `S_strict` **can only ever strengthen the wording. It can never upgrade,
> downgrade, or create a verdict.**
>
> **THE OPERATIONAL COROLLARY — a count, not a test, with its reading fixed
> now.** At the 900 s pair (1 → 4), report `N_adv_900 / n_books_900`.
> — `>= 0.90`: **nearly every book's stamp advances inside the deployed
> `MAX_ODDS_AGE_S = 900` window**, so the `stale_odds` guard can seldom bind on
> book age. ADR 0020's remedy must address that.
> — `< 0.90`: some books do not advance inside 900 s, so the guard is not wholly
> vacuous, and the remedy must say which books it still protects.
> **This count cannot raise, lower, or create the primary verdict.** It carries
> no alpha because it is not an inference.
>
> **No descriptive cell, no curve point, no per-book row, no per-market row, no
> subgroup, and no within-poll reproduction may substitute for `S`.**

### Reachability of all three outcomes, checked before registration

Required by the brief, and this repo has been bitten twice by skipping it — the
joint bound's Branch Z and the R3 saturation stop were both arithmetically
unreachable **before the data existed**.

**Marginal reachability of the verdict, over the grid `S` can actually take.**
`S` is a mean of `N_adv` fractions, each `|A_b|/(|A_b|+|B_b|)`.

| `N_adv` | `S` reaches ≥ 0.90? | `S` reaches ≤ 0.20? | mid-band reachable? |
|---:|---|---|---|
| **5** (the PC2 floor) | Yes — all five `s_b = 1.0` | Yes — all five `s_b = 0.0` | Yes — `{1,1,0,0,0}` → 0.40, `{1,1,1,0,0}` → 0.60, `{1,1,1,1,0}` → 0.80 |
| 20 | Yes | Yes | Yes |
| **30** (prior book count) | Yes | Yes | Yes |

**At the tightest possible `n` the grid is coarse but every verdict is still
reachable**, which is the check that failed on Branch Z. Note the boundary
behaviour at `N_adv = 5`: `S = 0.20` exactly is REFUTED (the rule is `<=`), and
`S = 0.80` is UNRESOLVED, not CONFIRMED. The inequalities are written as `>=`
and `<=` here so that no boundary case is decided later.

**Joint reachability — CONFIRMED and PC5 together.** CONFIRMED needs
price-identity at 300 s; PC5 needs ≥ 5 books to have changed *something* over
900 s. These pull in opposite directions and could, in principle, have been
mutually exclusive — they are not. A world in which all 30 books' stamps advance
between poll 1 and poll 3 with no price change, and 5 of them move a price
between poll 3 and poll 4, satisfies both. **Different intervals, different
books; no contradiction. CONFIRMED is jointly reachable.**

**Joint reachability — REFUTED and PC2 together.** REFUTED needs `N_adv >= 5`
books with advances that coincide with price changes. Reachable: 5+ books each
moving one price with a stamp advance.

**Reachability of UNRESOLVED** is trivial and needs no check; the risk with
UNRESOLVED is the opposite one — that it becomes the *only* attainable answer.
The 900 s fallback registered under PC2 is the guard against that, and it is why
the schedule spans a decade of interval rather than one point.

**One outcome that is NOT reachable, and is therefore not registered.** This
design cannot distinguish `S = 0.55` from `S = 0.65`, at any credit spend
(§ power check). No rule below the 0.90/0.20 resolution exists in this document
and none may be added afterwards.

---

## §8. The stopping rule

**Exactly four calls. Twenty-four credits. One sport. One slate. One window of
≤ 20 minutes. There is no fifth call, under any circumstance.**

- Data collection ends at poll 4, **regardless of what polls 1–3 showed**. In
  particular, a promising or disappointing result at poll 3 does not license
  another call, and does not license stopping early.
- **Transport failure** (`httpx.HTTPError`, which `client.py:248` re-raises
  *before* recording any cost) may be retried **once across the whole capture**,
  at the scheduled instant + at most 30 s. The realised timestamp is recorded
  and printed; the pair indices do not change.
- **Any non-200 response ends the capture immediately, with no retry.** A 4xx or
  5xx is recorded as spent (`client.py:255`, deliberately recorded before
  raising), so retrying would spend beyond the 24 Joe authorised.
- **A partial capture** yields a verdict **only if polls 1 and 3 both exist**
  (the primary pair). Polls 1 and 4 alone yield a verdict only through the PC2
  fallback. Any other partial capture is **UNRESOLVED — INCOMPLETE**, and the
  spend is recorded as such.
- **Reconciliation, at the end, always.** `budget.state()` before poll 1 and
  after poll 4; assert `spent_this_month` advanced by 24; compare against the
  server's `x-requests-used` delta. **A drift ≠ 0 is reported to Joe**, because
  it is the difference between "we have credits" and "we ran out on Saturday".

**UNRESOLVED does not license a second capture.** A re-run requires a new
registration that names what changed and why the new design can resolve what
this one could not. Spending another 24 credits on the same design because the
first answer was inconvenient is the thing this document exists to prevent.

**Nothing in §§1–7 may change after poll 1 is issued.** An amendment is
appended to this file, dated, with its reason, **before** the analysis runs, and
the pre-amendment rule is reported alongside. **An amendment made after the data
is read and not recorded voids the registration.**

---

## §9. What would falsify this, and what happens then

**The hypothesis is falsified by `S <= 0.20`** at the primary pair with every
precondition met — the stamp advancing in step with genuine price changes.

**The result's destination, fixed now, before the result exists:**

```
docs/measurements/<run-date>-odds-last-update-repeat-poll-result.md
```

One file, **written whichever way it comes out**, with that exact filename stem,
this document linked from its first line, and §10 reproduced verbatim. Only the
date varies. Registering the destination in advance is what stops a negative
result from quietly never being written.

**Consequences, in both directions:**

| Verdict | What is built | What is killed |
|---|---|---|
| **CONFIRMED** | **ADR 0020 is written**, with the three live remedy options, and the `S_strict` qualifier decides its permitted wording (§7). `suppression.py:210-218`'s comment is upgraded from an inference to a measurement with a citation. The result becomes a required input to any future measurement that stratifies on `odds_age_ms`. | The reading of `stale_odds` as a **line**-freshness guard, and `MAX_ODDS_AGE_S = 900` as a freshness threshold. **And a live dependency:** `2026-08-10-preregistration-fresh-odds-edge-distribution.md` §S2 item 4 prints the `odds_age_ms` distribution "so that *fresh* is a measured range, not a label" — under CONFIRMED that print is relabelled as *aggregator scrape age*, and the freshness stratum of §3 there is renamed. That document's thresholds do not move; its **wording** does. |
| **REFUTED** | Nothing new is built. `stale_odds` stands as a real freshness guard and the 900 s threshold is vindicated. The §0.1 single-poll finding is recorded as **explained by genuine cross-book synchrony**, which is itself a striking fact about the market and gets its own named section. | **ADR 0020 is not written.** `NEXT.md` queue item 1 and `start.md`'s queue item 1 are struck, with a pointer to the result file so no future session re-derives them. The three "live remedy options" are closed. |
| **UNRESOLVED** | Nothing. The result file records `S`, `R`, `N_adv`, `movers`, the failed precondition, and the full six-point interval curve, so a future design starts from measurement rather than from this document's assumption. | The **belief that this question is cheap**. If 24 credits at four intervals cannot resolve it, the next proposal must say what would — and §8 forbids simply buying more of the same. |

**This is decision-relevant in every branch.** CONFIRMED writes an ADR and
relabels a live registration; REFUTED deletes a queued ADR and two queue items;
UNRESOLVED closes off a re-run. There is no branch where the answer is "we
proceed either way".

---

## §10. What this measurement cannot establish — drafted before the run

Caveats written afterwards are selected to be survivable. These are written now,
and the list deliberately includes the ones that could overturn the result.

- **It cannot establish that the lines are stale.** A scrape clock is entirely
  compatible with every book being genuinely fresh. CONFIRMED is a statement
  about **what the field measures**, not about the quality of the odds. Any
  write-up that slides from one to the other is defective.
- **It cannot establish "our polling cadence" (§C2).** At most it bounds the
  *aggregator's* scrape cadence, coarsely, between 60 s and 900 s. The
  `delta_stamp` vs `delta_fetch` print bears on the distinction and is
  explicitly non-decision-bearing.
- **A price that moved and moved back inside the interval reads as identical.**
  At a 300 s sampling rate this is untestable, and its direction **inflates
  cell A** — that is, it flatters the hypothesis. Nothing in this design
  corrects for it and no amount of credit at this sampling rate would.
- **A book may have repriced a market or region we did not request.** Only
  `us,eu` and only `h2h,spreads,totals` are captured: no `uk`, no `au`, no
  alternate lines, no player props, no other sport. A book-scoped stamp advanced
  by an unobserved market is **indistinguishable from a scrape clock even at
  `S_strict`**. **This is the single caveat most likely to overturn the strong
  reading, and no observation in this capture can remove it.**
- **Cross-event bleed within the observed slate** is excluded only by
  `S_strict`, not by `S`. §7's mandatory qualifier is what stops the strong
  wording being used when `S_strict` does not support it.
- **One sport, one league, one slate, one 15-minute window, one day, one
  aggregator, one plan tier.** It says nothing about WNBA, about any
  low-liquidity league, about NFL, about in-play (`docs/adr/0006`), or about
  whether `last_update` behaves differently at a different time of day or closer
  to first pitch. §4 states what abandoning league generalisation cost and that
  recovering it needs its own registration.
- **`n` may be 1.** If one scrape process at the aggregator serves every book,
  the 30 bookmakers are one observation and this capture is a single anecdote
  about a single instant, however many pairs it contains (§3). The design
  answers a *qualitative* question and cannot upgrade itself to a quantitative
  one.
- **It cannot establish the aggregator's scrape period**, only bracket it
  between the intervals sampled.
- **It says nothing about `stale_kalshi_quote`**, `MAX_KALSHI_QUOTE_AGE_S`, or
  anything on the Kalshi side of the comparison.
- **It says nothing about edge, calibration, devig method, or why `actionable`
  has been 0 for the whole record.** `stale_odds` is one of fourteen suppression
  codes; establishing that one of them measures the wrong thing does not make
  any row actionable, and no write-up may imply it does.
- **It does not decide the remedy.** ADR 0020 owns that, and ADR 0020 is written
  *after* this result, not against a draft of it.
- **The three descriptive families it prints (per-book, per-market, per-event)
  are ~65 cells with no standard errors attached** — they are for reading the
  shape, not for finding one. A pattern spotted in them is a hypothesis for a
  future registration, never a result of this one.

---

## The power check — the deliverable, not a preliminary

**Can this measurement answer this question at the `n` available?**

### The `n`, before the effect

**[MEASURED FROM DATA — §0.2, prior MLB capture, and expected to be similar]**

```
per poll     ~15 events   ~30 books   ~440 (book,event) pairs   ~2036 rows
polls        4                              pair-intervals  6 (60..900 s)
n for S      N_adv <= 30 bookmakers   (the clustering unit, §3)
n if the aggregator runs one scrape process   1
```

### What is resolvable, and what is not

**This is not an effect-size question.** The two hypotheses predict opposite
ends of the `S` scale — a scrape clock predicts `S → 1`, a reprice timestamp
predicts `S → 0` — and the discriminating signature is **near-deterministic**
rather than a small shift in a mean. That is what makes the question answerable
with four calls at all, and it is the only reason this proposal survives its own
power check.

| Question | Resolvable here? |
|---|---|
| Is `S` near 1 or near 0? | **Yes**, deterministically, at `N_adv >= 5`. |
| Is `S` 0.55 or 0.65? | **No. At any credit spend.** Under the hypothesis the books are not independent; the effective `n` may be 1 (§3). More polls buy more correlated copies of the same observation, not precision. |
| Does the advance rate rise with interval? | **Yes, coarsely** — six points spanning 60–900 s, descriptive. |
| Does this generalise past MLB? | **No.** Abandoned deliberately (§4). |
| Does this generalise to in-play? | **No.** Out of scope by ADR 0006 and excluded by §2. |

**The `n` that would be needed for the mid-band** does not exist. Resolving
`S = 0.55` from `S = 0.65` at any useful confidence would require on the order
of hundreds of *independent* bookmakers; there are 30, and the hypothesis under
test is precisely that they share one clock. **Registered: no claim in the band
`0.20 < S < 0.90` may be made from this measurement, ever, and the rule in §7
returns UNRESOLVED there by construction rather than by anyone's later
judgement.**

### Calibration against the real headroom

The brief requires every proposal to be read against the 0.38 points of taker
headroom the venue provides, and this one does not measure edge at all — so the
relevant calibration is different, and it is favourable:

`stale_odds` is a **gate**, not a term in the edge. `MAX_ODDS_AGE_S = 900`
decides which rows are eligible to be actionable at all. A gate that fires on
the wrong quantity does not shift the edge by a fraction of a point; it selects
a different population. **[MEASURED — `budget.py:12-14`]** `stale_odds` was
**256 of 265 suppressions in 24 h** on the live instance. A measurement that
determines whether the dominant suppression code measures what it claims is
therefore operating well above the 1-point resolution floor the brief warns
about — it is a categorical question about a gate, not a marginal one about a
price.

### Verdict of the power check

**ADEQUATE for the near-deterministic signature this question actually turns on,
at `N_adv >= 5`, given the preconditions in §7. PERMANENTLY UNABLE to resolve
any mid-band value of `S`, at any credit spend, because the units may not be
independent. NOT RUNNABLE until P0 and P1 are satisfied.**

24 credits is the right price for this question **because** the signature is
near-deterministic. If it comes back mid-band, the correct response is to record
that the question is harder than it looked — not to buy more of the same
instrument.

A measurement that cannot resolve the question is worse than none, because it
returns a number anyway and the number gets quoted.

---

## §F. Facts verified against source, not taken on trust

- **F1.** `sweep_cost(markets, regions) = max(1, len(markets) × len(regions))`
  — `budget.py:66`. With `ODDS_MARKETS=h2h,spreads,totals` and
  `ODDS_REGIONS=us,eu` (`.env.example:51-52`) that is **6 credits per call**,
  so 24 credits is **exactly 4 calls**.
- **F2.** `fetch_odds` returns `[]` when `can_afford` is False — `client.py:233`
  — deliberately, not as an error. **A refusal and an empty slate are the same
  value at the call site.** This is the whole reason P1 and PC6 exist.
- **F3.** `ODDS_DAILY_CREDIT_BUDGET` defaults to **16** (`config.py:194`,
  `.env.example:38`) and the budget day rolls at **10:00 UTC**
  (`budget.py:139`, `DEFAULT_DAY_START_UTC_HOUR`), not midnight. See §C4 for the
  arithmetic that makes the **third** call the first refusal.
- **F4.** `_parse` prefers the **market-level** `last_update` and falls back to
  the bookmaker-level one — `client.py:331`. **[MEASURED — §0.2]** both are
  present on every object in the prior capture, so the stamp compared here is
  the market-level one on every row.
- **F5.** `h2h_lay` is returned without being asked for and is dropped by
  `EXCLUDED_MARKETS` — `client.py:111`. **[MEASURED — §0.2]** it is present in
  the prior capture (2096 raw rows vs 2036 priceable). Reusing `_parse` (P5) is
  what keeps it out.
- **F6.** `parse_ms` returns `None`, never `0`, on unreadable input —
  `client.py:73`. A row with no stamp therefore cannot silently read as
  1970-01-01, and `age_is_estimated` (`client.py:157`) marks the fallback.
  **Rows with `book_updated_ms is None` are counted and excluded from the
  advance test**; they cannot advance and their inclusion would dilute `R`.
- **F7.** `MAX_ODDS_AGE_S = 900` (`config.py:380`, `.env.example:71`) and
  `SuppressionConfig.max_odds_age_ms` are asserted to agree at startup
  (`config.py:416`). The 900 s poll is sampling the deployed threshold exactly.
- **F8.** `configure_logging()` installs the redaction filter on the root logger
  **and on every handler** (`logging_setup.py:112-122`) and pins `httpx` to
  WARNING (`:124`). The filter rewrites `record.args` as well as `record.msg`
  (`:78-91`), which is the shape `httpx` uses. **It does not protect a value the
  script writes to a file** — that is what P2's pre-write assertion is for.

---

## §S1. The extraction, fixed in advance

**Capture — `scripts/capture_odds_repeat_poll.py`, written and reviewed before
poll 1 (P3).**

```
configure_logging()                      # FIRST statement of main(). P2.
for i, offset_s in enumerate([0, 60, 300, 900], start=1):
    sleep until T0 + offset_s
    quotes = await client.fetch_odds("baseball_mlb", now_ms=now_ms)
    if not quotes:  ABORT — refusal or empty slate, indistinguishable (F2)
    payload = {"captured_ms": now_ms,
               "sport_key": "baseball_mlb",
               "params": {"regions": ["us","eu"],
                          "markets": ["h2h","spreads","totals"],
                          "oddsFormat": "decimal"},     # NEVER apiKey
               "note": "Verbatim /v4/sports/baseball_mlb/odds capture, poll i/4",
               "events": <response.json() verbatim>}
    text = json.dumps(payload)
    assert config.api_key not in text        # P2, before write
    assert "apiKey" not in text              # P2, before write
    write docs/measurements/<date>-odds-repeat-poll-p{i}.json
```

The artefact shape matches `tests/fixtures/odds_mlb_h2h_spreads_totals.json`
(`captured_ms` / `params` / `note` / `events`) so the two are directly
comparable. **`response.url` and `response.request.url` are never touched** —
the key lives in the query string.

**Analysis — `scripts/analyse_odds_repeat_poll.py`, reads only those four
files.** Row projection is
`OddsClient(cfg, budget)._parse(payload["events"], sport_key=..., fetched_ms=payload["captured_ms"])`
(P5) — no network, no credit, fully re-runnable after a bug fix.

The harness's module docstring states what it does not establish, per the repo
rule that every harness carries its own limits. **§10 is that docstring.**

## §S2. Required output of every run, in this order

Read `n` before the effect size, and read the frame before `n`.

1. **The spend and the frame.** `budget.state()` before poll 1 and after poll 4;
   the `x-requests-used` delta and any drift; the four realised `captured_ms`
   values and the six realised intervals; per poll: events, books, pairs,
   triples, rows.
2. **The exclusions, counted.** Events dropped for commencing before poll 4;
   rows with `book_updated_ms is None` (F6); KEY-DEGENERATE pairs;
   ABSENT-1 / ABSENT-2 / ROWSET-CHANGED per compared pair, with `|BOTH|` as a
   share of poll-1 pairs (PC3).
3. **The within-poll reproduction, corrected per §C1**, at each of the four
   instants: pairs with 3 markets / 2 markets / **1 market (vacuous, excluded
   from the numerator)**, and the number of ≥2-market pairs whose markets share
   one stamp. Reported as **REPRODUCTION — NOT A NEW OBSERVATION**.
4. **The preconditions**, PC1–PC6, each shown as met or unmet with its number.
5. **`R`, then `movers`, then `N_adv` — before `S`.**
6. **`S`, with the pooled pair-level share beside it and the largest
   bookmaker's share of the pooled denominator on the same line.** Then
   `S_strict`. Then the per-bookmaker table (30 rows, **DESCRIPTIVE**), and the
   sharp-set subgroup labelled **`n = 4` — BELOW THE FLOOR OF 5, CANNOT
   DECLARE**.
7. **The interval curve** — the six pairs × (advance rate, price-change rate,
   `S`), labelled **DESCRIPTIVE — CANNOT PRODUCE A FINDING**; and the
   `delta_stamp` vs `delta_fetch` diagnostic of §C2, with the lag distribution
   `fetched_ms − book_updated_ms` per poll.
8. **The 2×2 cells** A / B / C / D and `regressed`, per compared pair, with
   D's pre-registered reading printed beside it.
9. **The verdict**, its mandatory qualifier if CONFIRMED, and the operational
   corollary count at 900 s.
10. **The per-market and per-event breakdowns**, labelled **DESCRIPTIVE**.
11. **§10, reproduced verbatim.**

---

## Registration record

| | |
|---|---|
| Registered | 2026-08-10 (UTC); host clock 2026-08-09 local |
| Data seen at registration | **Yes — see §0.** The published single-poll inference, plus structural/coverage counts re-derived from the same fixture. **No `last_update` value has ever been compared across fetch instants, by anyone.** |
| Authorised spend | **24 credits, one shot** (Joe) = **exactly 4 calls** at 6 credits each |
| Allocation | **1 sport × 4 polls** — `baseball_mlb` at `T0`, `+60 s`, `+300 s`, `+900 s`. League generalisation deliberately abandoned; cost stated in §4. |
| Primary estimand | **`S`** — bookmaker-clustered mean of within-bookmaker shares of advancing pairs with zero price change |
| Direction | One-sided. Registered claim `S >= 0.90`; refutation `S <= 0.20` |
| Primary pair | **Poll 1 → poll 3 (nominal 300 s), by index.** Registered fallback: poll 1 → poll 4, on PC2 failure only, once. |
| Unit / clustering | **Bookmaker** (~30). Pairs ~440 and rows ~2036 are printed but are **not** `n`. Effective `n` may be 1. |
| Equality predicate | Exact `==` on `(outcome_point, price_decimal)`, keyed on `(odds_event_id, bookmaker, market, outcome_name)`. No tolerance. Hook moves count as **changes**. |
| Control | **`movers >= 5`** books changing ≥1 price over 900 s. Failure ⇒ UNRESOLVED — QUIET SLATE. |
| Alpha spent | **Zero.** No interval test, no standard error, no p-value. The project's `0.05 / 3` budget is untouched. |
| Multiplicity | ~65 descriptive cells, none with a standard error, none able to declare |
| Stopping rule | §8 — exactly 4 calls, ends at poll 4, **no fifth call**, UNRESOLVED does not license a re-run |
| Result destination | `docs/measurements/<run-date>-odds-last-update-repeat-poll-result.md`, written either way |
| Assumed inputs | **One** — the aggregator's scrape period, which justifies the schedule and gates no threshold |
| Verdict at registration | **READY.** Preconditions P0 (commit) and P1 (budget headroom, §C4) are outstanding and are not this agent's to satisfy. |
| Amendments | **None.** |
