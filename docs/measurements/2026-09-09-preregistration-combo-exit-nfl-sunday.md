# Pre-registration — does a KXMVE combination book carry a resting YES bid on an attended NFL regular-season Sunday?

**Registered 2026-09-09, four days before the run, before any book is read on
or after this date.** Every population predicate, the eligibility rule, the
unit, the clustering key, the sample cap, the sample floor, the capture clock,
the statistic, the multiplicity count, the stopping rule and the decision rule
are fixed below so that none of them can be chosen once the answer is visible.

**Owns:** one scheduled run of `scripts/measure_combo_book_presence.py` on
2026-09-13 and the result document it produces
(`docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md`, whose path is
fixed here so a null has somewhere to be written).
**Reads and may move:** `backend/parlays.COMBO_EXIT_CENSUS_*`, and through them
`backend/api/routes.py:3165` (the combo note on the buy ticket),
`backend/api/routers/parlays.py:320` (the bid route's 422) and
`tests/test_combo_book_depth_claims.py`.
**Touches nothing decided by** ADR 0038 (the hunt is closed — nothing here is
evidence about edge), ADR 0012 §5's combo fee model (still unverified), ADR
0015 (the gate's floor), or anything under `backend/odds/` (§8).

---

## 0. The power check, which comes before everything else

**This design is powered in one direction only, and that is stated before the
run rather than discovered after it.**

The claim on the screens is universal: *"no combination book read here has
carried a YES bid"*, sourced from `COMBO_EXIT_CENSUS_BOOKS_WITH_YES_BID = 0`
over `COMBO_EXIT_CENSUS_BOOKS_READ = 40`.

| direction | powered? |
|---|---|
| **Falsifying** — at least one resting YES level appears | **Fully powered at k = 1.** A universal claim dies to one counterexample. No `n`, no threshold and no interval is needed for this branch. |
| **Confirming** — no resting YES level appears | **Underpowered, and cannot be fixed at any reachable `n`.** |

The confirming branch's arithmetic, computed now. At `k = 0` the 95% Wilson
upper bound is `z^2 / (n + z^2) = 3.8416 / (n + 3.8416)`:

| independent books `n` | 95% upper bound on the YES-bid rate |
|---|---|
| 5 | 43.5% |
| 10 | 27.8% |
| 15 | 20.4% |
| 20 | 16.1% |
| 40 (the whole prior record) | 8.8% |
| 60 (prior record + 20 new) | 6.0% |
| 73 | 5.0% |
| 380 | 1.0% |

**The `n` this day can supply.** Every prior read of the eligible pool, from
this repo's own committed artifacts:

| run | eligible rows returned |
|---|---|
| 2026-08-09 E2 (`--max-books 20`) | 20, cap-bound |
| 2026-08-09 E3 | 9 |
| 2026-08-18 (`--max-books 25`) | **11, pool-bound** — the cap was not reached |
| 2026-08-30 list census | **0 of 61** open combinations carried a readable ask |

So the pool has been observed at 0, 9, 11 and 20+. And the row count overstates
the information: the 2026-08-18 result document reports its own effective `n`
as **about 2** — 23 distinct leg markets filled 69 leg slots, one ATP match
appeared in 7 of the 11 rows, and **5 of 11 rows shared an order book byte for
byte with another row.** CLAUDE.md's floor of five expected outcomes on each
side **fails outright** at every `n` in reach, and it fails on the prior 40 too.

**Verdict of the power check, fixed before the run:** the falsifying branch is
worth taking and is cheap. The confirming branch **may not be written up as
confirmation.** If the day returns zero YES levels, the only sentence licensed
is that the denominator grew and the upper bound narrowed to the figure in the
table above — never *"combos are structurally enter-only"*, never *"confirmed"*,
and never a stronger quantifier than the data carries. That prohibition is the
main thing this document exists to enforce, and §6 encodes it.

## 1. The question, as a claim that could be false

> **On Sunday 2026-09-13, do open `KXMVE` combination order books carry a
> resting bid on the YES side?**

Registered claim, stated so it can come back "no": **the rate of eligible
combination books with at least one level on `yes_dollars` is greater than
zero.** The comparison baseline is 0 of 40.

**The test is one-sided and the direction is forced, not chosen.** The baseline
is at the boundary of the parameter space; a rate cannot fall below zero, so the
only observable departure is upward. That is recorded here so nobody later
claims a two-sided test was "reported one-sided".

**The second question, and it is not the same one.** The decision-relevant claim
is not the universal one; it is *"you can enter and may not be able to exit at
size."* A single resting YES bid for one contract falsifies the universal claim
while leaving the operational one standing. Both are scored, separately, in §6.

**Quantifiers weakened at registration time, where it costs nothing.** The
screens say "every" and "never". This document tests exactly the sentence the
screens carry and does not test, and may not be reported as testing, any
stronger claim about the venue, the product, or other calendars.

### FOUND 2026-09-09, AFTER THIS DOCUMENT WAS WRITTEN AND BEFORE ANY DATA — the baseline never read the shard Joe trades

Established by probing the public `/markets` endpoint while wiring Arm C's
flag, and by re-reading this repo's own three recorded runs:

    KXMVESPORTSMULTIGAMEEXTENDED     37 open rows      in DISCOVERY_SERIES
    KXMVECROSSCATEGORY               24 open rows      in DISCOVERY_SERIES
    KXMVECROSSCATEGORY-SHARD1      1000 open rows      NOT in DISCOVERY_SERIES
    KXMVENFLSINGLEGAME                0 open rows      Arm C (series exists, HTTP 200)
    KXMVENFLMULTIGAMEEXTENDED         0 open rows      Arm C (series exists, HTTP 200)

`series_ticker=KXMVECROSSCATEGORY` returns **only** non-shard tickers; the
shard is a separate series and the two row sets are disjoint. And in all three
recorded runs — 20 rows on 2026-08-09 (E2), 9 rows (E3), 11 rows on 2026-08-18
— **`SHARD1` tickers number zero.**

**Every one of Joe's ~50 real combination fills is `KXMVECROSSCATEGORY-SHARD1-*`.**

So the sentence "no combination book read here has carried a YES bid", which
gates the warning shown before **every** combination tap and underwrites
ADR 0073's ceiling and ADR 0078's hedge, was measured on a population he does
not trade. That does not make the sentence false. It makes its *scope* narrower
than the screens imply, and the gap is exactly the shard where his money is.

A shard arm is runnable: of 1,000 open `KXMVECROSSCATEGORY-SHARD1` rows on a
midweek probe, all 1,000 carry `mve_selected_legs` and **13 carry a readable
ask** — eligible under this document's unmodified §2 rule. (A 1.3% quote rate,
consistent with combinations being unquoted at rest.)

**No arm is added here.** Adding one is a decision, it needs its own capture
budget, and this document's own §2 forbids changing the population after the
fact. It is recorded now, before the data, so that whatever is decided is
decided in front of the question rather than behind the answer — and so a
future reader cannot mistake the 0-of-40 for a fact about shard 1.

## 2. The population, and the exclusions

**Arm A — primary, and the only arm that carries the verdict.** The two series
already in `DISCOVERY_SERIES` (`scripts/measure_combo_leg_echo.py:120`):

    KXMVESPORTSMULTIGAMEEXTENDED
    KXMVECROSSCATEGORY

One `GET /markets?series_ticker=...&status=open&limit=1000` per series,
**newest-first, no paging** (CLAUDE.md forbids walking `/markets`; combination
discovery through `/multivariate_event_collections` is also refused here because
`lookup_combo` can create a market on the exchange, and this run creates
nothing).

These two series are kept **because comparability to 0-of-40 is the entire
point**, and they are not NFL-specific: `KXMVESPORTSMULTIGAMEEXTENDED` is the
cross-game sports series, so an NFL Sunday enters this arm through its
constituent legs without any change of population.

**Selection, matched to the instrument as it now stands.** `round_robin` over
the two series' pages, then the first eligible rows in interleaved order, up to
the cap. It is **not** random and it is **not** re-chosen after a book is seen.

**This is a known and stated comparability defect, not a clean control.** The
round-robin rule was introduced *after* E2 ran. 29 of the baseline 40 books
(2026-08-09) were selected by the superseded "first N in discovery order" rule,
which could not reach the second series at all; only the 11 books of 2026-08-18
used the rule that will run on the day. So §6 scores the day against **both**
denominators — the 40 the screens cite, and the 11 collected on the same
instrument — and any disagreement between them is reported rather than resolved.

**Eligibility, inherited verbatim from the baseline and not relaxed:** a
`/markets` row with a non-empty `mve_selected_legs` and a readable `yes_ask` by
`measure_combo_correlation.readable_quote` (`0 < ask < 1`). **A `0.0000` ask is
not an ask.**

**Exclusions, and why each is independent of the outcome.** The dependent
variable is presence of a level on `yes_dollars`. None of these reads it:

| exclusion | reason it cannot be the finding |
|---|---|
| no `mve_selected_legs` | not a combination at all |
| unreadable or absent `yes_ask` | an eligibility rule about the **NO** side of the list summary, fixed before the run and identical to the baseline's |
| duplicate ticker within a capture | a repeat of the same row, not a second observation |
| malformed orderbook envelope (`MalformedOrderbookResponse`) | **aborts the row and is reported separately; never counted as "no YES bid".** This is the one hazard of the instrument — a renamed wire key once returned `{}` for every market on the exchange without erroring. An empty book is a legal venue state; a missing envelope is a bug, and the two must not be pooled. |

**No exclusion may be added on the day.** If the day produces a category nobody
anticipated, it is reported in full and the verdict is computed both with and
without it, both figures printed.

**Arm B and Arm C exist only if the instrument exists first.** Neither carries
the verdict, and each runs *only* if the change below is committed and reviewed
**before 2026-09-13 00:00Z** and is then run unmodified:

- **Arm B — unquoted books.** Eligibility widened to open combination rows with
  no readable ask. Justified because the exit question does not need an ask;
  the ask requirement is inherited from E2, whose question was whether a *list
  ask* was backed. Needs a flag on `eligible()`. Reported with its own `n`,
  **never pooled with the baseline 40.**
- **Arm C — NFL single-game.** `KXMVENFLSINGLEGAME` and
  `KXMVENFLMULTIGAMEEXTENDED`, which no run in the record has ever read a book
  for. Needs those tickers added to `DISCOVERY_SERIES` or supplied by flag.
  Reported separately, **never pooled**, and its baseline is *nothing* — so it
  can falsify the universal claim (§6) but has no comparison of rates.

If the instrument change does not land in time, **Arms B and C do not run and
this document is not amended to let them.**

## 3. The unit of observation, and the clustering variable

**The unit is one distinct combination market's order book.** Two units are
independent only if they are not the same book wearing two tickers.

Three counts are required on every table, and no verdict may be quoted without
all three beside it:

1. `n_rows` — book reads attempted.
2. `n_books` — **distinct tickers pooled across the five captures.** A ticker
   read at all five slots is **one** book in the pooled denominator, reported
   as a five-point time series. Five captures of forty rows is not `n = 200`,
   and writing it that way is the exact failure this repo shipped a gate fix
   for (`ADR 0029`, clustering by game).
3. `G_eff` — **distinct clusters**, where the cluster key is the sorted tuple of
   the row's leg market tickers reduced to their **event** (game) identifiers.
   Rows whose `yes_dollars`/`no_dollars` arrays are byte-identical collapse to
   one cluster regardless. The 2026-08-18 run scores `G_eff ≈ 2` on 11 rows by
   this rule; that is the standard the day is held to.

`G_eff` is a **required field**. A result document that reports a rate without
it is incomplete, per the habit established on the CLV fits.

## 4. The cut — thresholds fixed in advance

There are no price buckets here, so the bucketing hazard takes a different
shape: **depth thresholds**. They are named now.

| threshold | value | why it is this number |
|---|---|---|
| `EXIT_ANY` | ≥ 1 level on `yes_dollars`, any size, any price | falsifies the universal sentence on the screens |
| `EXIT_PRACTICAL` | ≥ 10 contracts resting on YES at a single price on a single book | a size that could close a small real position |
| `EXIT_AT_CEILING` | ≥ 250 contracts resting on YES at a single price on a single book | `COMBO_MAX_CONTRACTS = 250` — the exact size the ceiling's stated reason says cannot be closed |

Depth is read at `--depth 10`, the baseline's value, and is therefore **top ten
levels only**; anything deeper is invisible to this instrument and no claim
about total resting size is licensed.

**Prices are recorded on the YES scale and in integer tenths of a cent**, by the
harness's existing parser: a NO level at `p` derives to `1 - p`, a YES level is
`p` itself. **Unreadable resolves to `None`, never `0`** — 0 is a legal bid and
a parser that returns it on garbage cannot be told from one that read correctly.

## 5. The statistic, named as an estimator, and the multiplicity counted

**Primary (Arm A).** A **proportion**: `k / n_books`, the share of distinct
books with at least one `yes_dollars` level. Reported as `k/n` with a **95%
Wilson score interval**. The normal approximation is **not licensed** — §0 shows
the ≥5-per-side rule fails at every reachable `n` — so the interval, not the
point estimate, is the result. Reported again over `G_eff` as the sensitivity
denominator; if the two disagree, `G_eff` governs.

**Secondary S1 — depth.** Given any YES level: count of levels, size at best,
maximum size at a single price, and which of §4's three thresholds it clears.
Descriptive. `n` will be tiny by construction and no interval is claimed on it.

**Secondary S2 — the entry side, which does have power in both directions.**
Share of books carrying at least one `no_dollars` level. Baseline **33 of 40**
(16/20, 6/9, 11/11). Estimator: a **difference of two independent proportions**;
test: **Fisher exact, two-sided, pooled over the day's distinct books against
the pooled 40**, at **α = 0.01**. Two-sided because entry presence can move
either way and there is no boundary forcing a direction.

**Secondary S3 — the pool.** The scan denominator: open rows per series, and how
many were eligible. Descriptive, and it is the number that decides ABORTED-THIN
in §6. **The harness logs it to stdout and `to_json` drops it**, so stdout must
be captured to a file for every capture or S3 does not exist.

**Multiplicity, counted now.** Five captures × two secondary comparisons = ten
cells; at two standard errors pure noise yields about 0.46 "significant"
results, which is why per-capture significance is **not** computed. Only the
**pooled** S2 test is inferential, it is one test, and α = 0.01 is set against
the ten cells that were available to be picked from. Per-capture rates are
printed for description and **may not carry a verdict**.

**The primary is not a significance test at all** and does not consume
multiplicity: observing a resting order is an observation, not a fluctuation.
The registration says this out loud so the null cannot later be dressed as
"not significant" or the hit as "p < 0.05".

## 6. The decision rule

> **If any capture on 2026-09-13 records at least one level on `yes_dollars`
> for a book whose envelope parsed (`EXIT_ANY`), then the sentence "no
> combination book read here has carried a YES bid" is FALSE and every surface
> carrying it changes: `COMBO_EXIT_CENSUS_BOOKS_WITH_YES_BID` moves off zero,
> the buy ticket's `combo_note` and the bid route's 422 become a rate rather
> than a universal, and `tests/test_combo_book_depth_claims.py` is re-pinned
> to the new captures. `COMBO_MAX_CONTRACTS` stays at 250 unless a single book
> shows `EXIT_AT_CEILING` — ≥ 250 contracts resting on YES at one price — in
> which case the ceiling's stated reason is retired and the number is re-argued
> from scratch in a new ADR. If zero YES levels are recorded across all
> captures and at least 10 distinct books were read, nothing on any screen
> changes except the denominator and the dates: `COMBO_EXIT_CENSUS_BOOKS_READ`
> rises, the sentence becomes "across N runs on three dates, including one
> attended NFL regular-season Sunday", and `backend/kalshi/combos.py`'s
> calendar caveat narrows by exactly one clause — NFL regular season is no
> longer unmeasured, NBA remains unmeasured. If fewer than 10 distinct books
> were read in total, the run is ABORTED-THIN: no constant moves, no screen
> changes, no caveat narrows.**

Tabulated, with the consequence in both directions:

| result | what is built | what is killed |
|---|---|---|
| `EXIT_ANY` met, `EXIT_PRACTICAL` not met | the note is rewritten as a rate; a follow-up registration for a repeat-slot depth series is licensed | the universal sentence, on three surfaces |
| `EXIT_PRACTICAL` met | as above, plus `/hedge`'s framing as "the only exit an enter-only combo has" (ADR 0078) is re-opened in an ADR | the claim that hedging a leg is the *only* exit |
| `EXIT_AT_CEILING` met | a new ADR re-argues `COMBO_MAX_CONTRACTS` from first principles | the stated reason for the 250 ceiling |
| zero YES levels, `n_books ≥ 10` | one clause of the `combos.py` calendar caveat is closed; constants and dates updated | **nothing.** Explicitly: the claim is *not* upgraded, no quantifier is strengthened, and no screen text changes |
| `n_books < 10` | nothing | nothing. The day did not supply the sample and the result document says so |

**The ABORTED-THIN branch is deliberate and it is the pre-registered refusal.**
This repo has a live specimen of a pre-registered exclusion that the agent
correctly declined to activate when the sample came in thin; that refusal was
only possible because the rule existed in writing first. This is the same
shape. **Ten** is the floor because it is where the confirming branch's 95%
upper bound first drops under 30%, and because 11 is the smallest prior run
anyone wrote up.

**Note against interest, recorded before the run:** `COMBO_MAX_CONTRACTS` is
**not the binding constraint** on the hand-bet path — `MANUAL_ORDER_MAX_SPEND_TENTHS`
is, at $3.00 — so even the `EXIT_AT_CEILING` branch changes little in practice.
That is a finding about the plan and it is cheaper to say now: the ceiling is
not what this measurement is worth. **What it is worth is the sentence Joe reads
before every combo tap**, which is a universal claim resting on 40 books from a
calendar that no longer exists.

## 7. The stopping rule

**Five captures, at fixed clock times, on 2026-09-13 only.** NFL kickoff
structure, ET = UTC−4:

| slot | UTC | what it straddles |
|---|---|---|
| C1 | 15:30Z | ~90 min before the 13:00 ET wave — pre-kickoff, books at their most "at rest" |
| C2 | 17:30Z | early wave in play |
| C3 | 20:00Z | between waves, just before the 16:05/16:25 ET kickoffs |
| C4 | 23:30Z | late wave in play |
| C5 | **2026-09-14 00:45Z** | SNF (20:20 ET) in play — same NFL Sunday, next UTC date |

Each capture is exactly:

    .venv\Scripts\python.exe scripts\measure_combo_book_presence.py \
        --max-books 40 --depth 10 \
        --json docs/measurements/2026-09-13-combo-exit-nfl-sunday-cN.json \
        > docs/measurements/2026-09-13-combo-exit-nfl-sunday-cN.txt 2>&1

`--max-books 40` because it makes one day's run the size of the entire prior
record, so a null exactly doubles the pooled denominator. `--max-legs` is
**unset**, matching 2026-08-18. Budget per capture: `2 + 1 + N + 1` ≤ 44
unmetered Kalshi calls; five captures ≤ 220, rate-limited at 0.15s.

**Collection ends at 2026-09-14 01:15Z.** No sixth capture. A slot that fails on
a network or envelope error may be retried **once**, within 10 minutes of its
scheduled time; a slot missed by more than 30 minutes is recorded **missing**,
not moved, and the result document reports four of five. *"The pool was thin, so
we took another look later"* is the prohibited move and it is prohibited by name.

## 8. Cost, safety, and non-interference with the frozen odds measurement

- **Zero Odds API credits, and this was confirmed rather than assumed.**
  `scripts/measure_combo_book_presence.py` imports from `backend.kalshi.rest`,
  `backend.kalshi.discovery` and `backend.logging_setup` and **nothing under
  `backend.odds`**; credits are written in exactly one place in the running
  system, `backend/odds/budget.py:276`, which this path never reaches. The run
  opens no database and writes no row.
- **Unauthenticated.** Both `/markets` and `/markets/{ticker}/orderbook` return
  200 with no signature (verified 2026-08-09). No credential enters the process.
- **Read-only.** No order, no bid, no cancel, no `multivariate_event_collections`
  lookup — that endpoint can create a market on the exchange and is refused here.
  Nothing money-touching.
- **It does not touch the frozen surface.** `backend/odds/{timing,budget,
  attention,ondemand,client,sweeplog}.py` and `timing.py:1536` are frozen until
  10:00Z 2026-09-14; this run changes none of them, and Arms B/C's optional
  instrument change is confined to `scripts/` and would be committed before the
  day in any case.
- **It must not perturb attention or dwell.** The concurrent measurement on
  2026-09-13 is the attended-NFL-Sunday odds measurement, whose signal *is* Joe
  opening pages. **Whoever runs these captures must not open the cockpit UI to
  do it** — the harness runs from a laptop shell against public Kalshi
  endpoints and never touches `/api`. Joe's own use of the desk that day is his
  own and is the other measurement's subject; nothing here adds to it.

## 9. What this cannot establish, drafted before it runs

- **It is one calendar point, and that cuts both ways.** The baseline's flaw is
  that it was captured on a calendar (2026-08-09: NFL preseason, NBA finished;
  2026-08-18: 78% tennis by leg, 5 NFL legs still preseason) that does not
  generalise. **An NFL-Sunday result inherits the same flaw in mirror image.**
  It generalises to: NFL regular season, September, Sunday, in and around
  kickoff. It does **not** generalise to NBA (still entirely unmeasured), NFL
  playoffs, weekdays, the offseason, or non-sports combinations.
- **Availability is not fillability.** A resting YES bid is a stored quote. A
  book that shows one is consistent with a real exit **and** with a maker who
  cancels the moment an order arrives. No quote record separates them; one small
  order would, and this run places none.
- **The mechanism is unidentified either way.** A null cannot distinguish *"the
  product does not permit a resting YES order"* from *"nobody wanted to sell
  today"*. Only Kalshi's documentation or an order attempt could, and neither is
  in scope. **No result here licenses a sentence beginning "structurally".**
- **`n` is not the row count.** See §3. The effective count will be a small
  single-digit number and CLAUDE.md's ≥5-per-side rule fails outright — as it
  also fails on the 40 the current screens cite.
- **Top ten levels only**, and only for eligible rows within one unpaged page
  per series. This is a census of *eligible-within-one-page*, **not a rate over
  `KXMVE`**, which has 1,389 collections and 13,806 legs.
- **The baseline is not a clean control** (§2): 29 of its 40 books came from a
  superseded selection rule that could not reach the second series.
- **Nothing about entry.** The 2026-09-06 parlay census (51 of 52 positions
  entered as takers) is a different population — this desk's own fills — and is
  not touched, confirmed or contradicted here.
- **Nothing about pricing, fee or edge.** ADR 0012 §5's combo fee model stays
  unverified; ADR 0038 stays closed; no number here may appear in a sentence
  about edge, `beta`, the 300-game gate or the 0.63-point cost headroom.
- **Nothing about whether Joe could exit a position he actually holds.** That is
  `/hedge`'s job (ADR 0078) and it reads the *legs*, not the combination book.
- **It cannot rule out a modest YES-bid rate.** §0's table is the ceiling on
  what a null says, and the result document must print the realised bound rather
  than the word "none".

## 10. Where the negative result gets written

`docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md` — **the same path
in every branch**, written within 48 hours of the last capture, whatever the
answer. The five JSON artifacts and five stdout logs are committed beside it
even in the ABORTED-THIN branch, because a thin day is itself a fact about the
product on an NFL Sunday and is the kind of result that otherwise never gets
written down.
