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

> **AMENDMENT 1, 2026-09-09 — a fourth arm, on the shard Joe actually trades,
> and it takes the headline.** Recorded the same day this document was
> registered, still four days before the run, and **before any book is read**.
> It adds **Arm D** (`KXMVECROSSCATEGORY-SHARD1`) and moves the headline of the
> result document to it. It does **not** edit §2's Arm A, §5's multiplicity
> count, §6's rules for Arm A, or §7's clock — all four stand exactly as
> written. Full text is **§11**, at the end; the reason it exists is §1's
> `FOUND 2026-09-09` block. **Nothing above this line has been changed.**
>
> **AMENDMENT 2, 2026-09-09 (same day, still before any data)** fixes Arm
> D's population to the one literal series that exists, records the
> newest-first truncation and its sampling consequence, and rules on the
> scope correction §11.10 held open. It is **§12**.


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

> **SUPERSEDED THE SAME DAY, still before any data — see §11.** The paragraph
> below said *"No arm is added here"*, and that was true when written: it was
> written to record the finding without letting the finder choose the response.
> Joe then approved a shard arm, and **Amendment 1 adds Arm D and makes it the
> primary arm.** The paragraph is kept rather than edited, because the whole
> point of the sentence was that the decision was taken separately from the
> discovery, and deleting it would erase the evidence that it was.

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

---

## 11. Amendment 1 — Arm D, the shard arm

**Written 2026-09-09, after §1's `FOUND 2026-09-09` block and before any book is
read on or after this date.** Approved by Joe. Read §1's finding first; it is
not repeated here.

Nothing in §§0–10 is edited. Where this amendment and the original text differ,
the difference is stated below rather than made by deletion, so the
pre-amendment state stays readable and so a later reader can see which
population the document was written against and which one it ended up leading
with.

### 11.1 Identity, and the rank — the tension is real and is resolved, not split

**Arm D reads `KXMVECROSSCATEGORY-SHARD1`, the series every one of Joe's ~50
real combination fills sits in, and which no run in this repo's record has ever
read a single book from.**

**Arm D is the primary arm. It takes the headline of the result document. Arm A
is demoted to the comparison arm.**

The tension is genuine, so here is the argument rather than a hedge. Arm A is
the only arm comparable to the 0-of-40 baseline; Arm D is the only arm whose
population is the one the warning is *applied* to. Both cannot lead. Arm D
leads for one reason, and it is decided by §0's own arithmetic rather than by
which population feels more important:

> **Arm A's unique contribution — comparability to 0 of 40 — is a contribution
> to the branch that §0 already proved cannot conclude anything.** The
> confirming direction is unfixable at any reachable `n`; the rate comparison is
> therefore ornamental. Arm A's *falsifying* power is not unique to it: one
> resting YES level anywhere kills the universal sentence, and Arm D can supply
> that just as well. So Arm A brings a unique-but-unusable contribution and a
> usable-but-shared one, while Arm D brings the usable one **on the population
> that determines whether the sentence is about Joe's money at all.**

Stated as a rule so it can be applied again: **the headline goes to the arm
whose population the claim is applied to, not to the arm whose population the
claim was historically measured on.**

**What this demotion does and does not do.** Arm A runs exactly as registered in
§2, at the slots in §7, under the decision rules in §6, and it remains the
**only** arm carrying the S2 entry-rate comparison (§5), because it is the only
one with a baseline. It is reported second. If the two arms disagree, both are
printed, neither is reconciled, and the disagreement is itself the result.

**Co-primary was available and is refused.** Two headlines is two chances to
pick the better one afterwards, which is the thing this document exists to
prevent.

### 11.2 Population, eligibility and selection

One series: `KXMVECROSSCATEGORY-SHARD1`, supplied by the instrument's new
repeatable `--series` flag. `DISCOVERY_SERIES` is **deliberately unmoved**, so
Arm A's population cannot shift underneath it.

**Eligibility is §2's rule, unmodified and not relaxed:** non-empty
`mve_selected_legs` and a readable `yes_ask` by `readable_quote` (`0 < ask < 1`).
A `0.0000` ask is not an ask. The midweek probe scores 13 of 1,000 open rows
eligible under exactly this predicate.

**Selection:** the first eligible rows in the series page's own order, up to the
cap. Single series, so `round_robin` is a no-op here; this is stated because a
one-series arm and a two-series arm are not selected identically and the
difference should not be discovered later.

**One page, never paginated** — `limit=1000`, and CLAUDE.md forbids walking
`/markets`. §11.9 records what the truncation costs.

**Exclusions are §2's, unchanged**, including the one that matters most: a
malformed orderbook envelope **aborts the row and is reported separately, never
counted as "no YES bid."**

### 11.3 Baseline — there is none, and that is a constraint not a gap

Arm D has the same structure as Arm C: **no prior observation exists on this
series**, so there is no rate to compare against.

**Permitted:** falsifying the universal claim (one resting YES level suffices,
and needs no baseline); reporting a first-ever proportion `k/n` on shard 1 with
a 95% Wilson interval; reporting depth against §4's three fixed thresholds.

**Forbidden, and these are named now because each is a sentence somebody would
otherwise write:**

- Any difference-of-proportions test, Fisher or otherwise, **against the 40**.
  The two populations differ in series, in selection rule and in calendar
  simultaneously; a difference would be confounded three ways and attributable
  to none of them.
- Any claim that shard 1 is *"the same as"* or *"different from"* the non-shard
  population. Arms A and D are two censuses, not a treatment and a control.
- Any statement that shard 1 is *"more"* or *"less"* liquid than anything.

### 11.4 Pooling

**Never pooled with the 40, and never pooled with Arms A, B or C** — the same
terms already applied to Arms B and C in §2. Every rate, every interval and
every `G_eff` is computed within an arm. The JSON's `series_read` and
`default_series` stamps must be carried into the result document so a book can
always be attributed to its arm after the fact; a table row without its series
is not reportable.

**One thing legitimately does pool, and only one.** `COMBO_EXIT_CENSUS_BOOKS_READ`
is a **count of books read**, not a rate, and a shard-1 book is a combination
book this repo has read — so the count may grow across arms. To keep that from
quietly re-creating the scope error §1 found, the result document must propose
**separate constants** in `backend/parlays.py`:

    COMBO_EXIT_CENSUS_SHARD1_BOOKS_READ
    COMBO_EXIT_CENSUS_SHARD1_BOOKS_WITH_YES_BID

sourced, never typed, per the guard that already parses that module with `ast`.
A single census total that cannot say which series it came from is the shape
that produced this amendment.

### 11.5 `n`, fixed now, and what happens if Sunday is thinner

**`--max-books 25`.** Justified against the midweek observation of 13 eligible:
the cap is set at roughly twice it, so it is **not expected to bind**. That is
the point — a cap that binds converts a census into a truncation and hides the
pool size, which is the quantity §5's S3 exists to record. 25 is also the value
the 2026-08-18 run used, so the instrument is being driven at a setting it has
been driven at before.

**Denominator and clustering are §3's, unchanged and required:** `n_rows`,
`n_books` (**distinct tickers pooled across slots** — a ticker seen at all five
slots is one book, reported as a five-point series), and `G_eff` on the leg-set
cluster key. **`G_eff` remains a required field**; a shard-1 rate quoted without
it is incomplete.

**If Sunday yields fewer than expected:**

| pooled distinct shard-1 books | what Arm D may say |
|---|---|
| ≥ 10 | everything in §11.7, including the null branch |
| 1–9 | **ABORTED-THIN for every purpose except the falsifying branch.** The counts and the Wilson interval are printed and flagged UNINFORMATIVE; no rate is quoted in prose, no screen text changes, no scope narrows. A resting YES level found in these books still falsifies the universal claim — that branch needs no `n` and is unaffected. |
| 0 eligible rows | the instrument aborts the capture by design (§11.6). Recorded as such. **Zero eligible is a real result about the product on an NFL Sunday** and is reported, not retried. |

The floor of 10 is §6's floor, adopted unchanged rather than re-chosen for this
arm, because re-choosing a floor for a new arm is exactly where a floor gets
picked to be clearable.

### 11.6 Slots and call budget

**Arm D runs at all five slots in §7 — C1 15:30Z, C2 17:30Z, C3 20:00Z, C4
23:30Z, C5 2026-09-14 00:45Z — and at no others.** Not a subset: the falsifying
branch is a union over time, a resting bid may exist for minutes, and dropping
slots strictly reduces the probability of catching the one event this design is
powered for. The marginal cost is zero Odds credits and a rounding error of
unmetered Kalshi calls.

**Arm D is a SEPARATE invocation from Arm A at each slot, and this is
load-bearing.** A series named with `--series` that returns no open rows
**aborts the run**. Folding shard 1 into Arm A's invocation would let a shard
with an empty page destroy Arm A's capture for that slot. Two commands per slot:

    .venv\Scripts\python.exe scripts\measure_combo_book_presence.py \
        --series KXMVECROSSCATEGORY-SHARD1 --max-books 25 --depth 10 \
        --json docs/measurements/2026-09-13-combo-exit-shard1-cN.json \
        > docs/measurements/2026-09-13-combo-exit-shard1-cN.txt 2>&1

run **after** §7's Arm A command at the same slot, within 10 minutes of it.
stdout is captured for the same reason as Arm A: `to_json` drops the scan
denominator, and S3 does not exist without it.

**Budget.** One series page, so `1 + 1 + N + 1` calls; at `N = 25` that is **28
per capture, 140 across the five slots**. Day total with Arm A: ≤ 220 + 140 =
**≤ 360 unmetered Kalshi calls**, rate-limited at 0.15s — under a minute of wire
time. **Zero Odds API credits** (§8's confirmation is unchanged: the harness
imports nothing under `backend.odds`, and credits are written only at
`backend/odds/budget.py:276`). Read-only; no order, no bid, no lookup.

**§5's multiplicity count is unchanged, and that is a claim, not an oversight.**
Arm D adds **no inferential test**: it has no baseline, so no S2; and the
primary is an observation rather than a significance test, so it consumes no
alpha. The ten cells and the single pooled Fisher test at α = 0.01 stand exactly
as registered.

### 11.7 The decision rule for Arm D

> **If any capture records at least one level on `yes_dollars` for a parsed
> shard-1 book (`EXIT_ANY`), the sentence "no combination book read here has
> carried a YES bid" is false on the population Joe actually trades — the
> strongest available falsification — and the buy ticket's `combo_note`, the
> bid route's 422 and `tests/test_combo_book_depth_claims.py` change to a rate
> that names its series; ADR 0078's framing of a leg hedge as "the only exit an
> enter-only combo has" is reopened in a new ADR if `EXIT_PRACTICAL` (≥ 10
> contracts at one price) is also met, and `COMBO_MAX_CONTRACTS` moves only
> under `EXIT_AT_CEILING` (≥ 250 at one price), exactly as §6 already rules.
> If zero YES levels are recorded across all five slots and at least 10 distinct
> shard-1 books were read, that is NOT confirmation (§0): the only licensed
> change is the scope the screens currently lack — the note names the series it
> was measured on, and the two new shard constants in §11.4 record the shard
> census separately. Below 10 distinct books, Arm D is ABORTED-THIN and nothing
> changes.**

The consequences in both directions, so the measurement is decision-relevant in
each:

| Arm D result | built | killed |
|---|---|---|
| `EXIT_ANY` on shard 1 | the note becomes a rate naming its series; a repeat-slot depth series becomes registrable | the universal sentence, **on the population it is actually shown against** |
| `EXIT_PRACTICAL` | a new ADR reopens ADR 0078's "only exit" framing | that framing |
| `EXIT_AT_CEILING` | a new ADR re-argues `COMBO_MAX_CONTRACTS` from first principles | the stated reason for the 250 ceiling |
| zero YES, `n ≥ 10` | the screens gain a scope clause and a shard-specific denominator | **nothing.** No quantifier strengthens, no "structurally", no "confirmed" |
| `n < 10` | nothing | nothing |

**Recorded against interest, as §6 already records for Arm A:** the binding
constraint on the hand-bet path is `MANUAL_ORDER_MAX_SPEND_TENTHS` ($3.00), not
`COMBO_MAX_CONTRACTS`, so even the ceiling branch changes little in practice.
Arm D's value is the sentence Joe reads, not the ceiling.

### 11.8 A correction owed today, whatever Sunday returns

**Judgement: yes, one is owed, and it should land before the first capture.**

The buy ticket says *"Every combination book this repo has ever read had no YES
bid — 40 of 40, across three runs on two dates."* That sentence is **true** and
its scope is **silently wrong for its reader**: the reader is about to tap a
`KXMVECROSSCATEGORY-SHARD1` combination, and the 40 contain zero shard-1 books.
A true sentence a reader will apply to a population it never measured is the
`justifications decay toward reassurance` pattern, and it is worse here because
the number is sourced correctly — the sourcing guard cannot catch a scope error.

This is **available today and does not depend on the capture**, which is exactly
why it must not wait for it: if Sunday comes back ABORTED-THIN, the correction
would never land at all.

- **What changes:** the note gains a clause naming the series measured, or
  saying plainly that no shard-1 book has been read.
- **How:** through `backend/parlays.COMBO_EXIT_CENSUS_*` and the constants
  proposed in §11.4 — **sourced, never typed digits** — with
  `tests/test_manual_orders.py` and `tests/test_combo_bid_routes.py` updated to
  pin the scope clause the same way they pin the count.
- **Deadline:** before C1 at 15:30Z on 2026-09-13, so the screen is not making
  an unscoped claim while the measurement that scopes it is running.
- **This registration does not authorise it.** It changes real-money screen
  text; it needs Joe's or the partner's word, and §11.10 lists it as the one
  item requiring confirmation.

### 11.9 What Arm D cannot establish

Everything in §9 applies unchanged. In addition:

- **One shard.** `SHARD1` only. Kalshi shards collateral per exchange and other
  shards exist and are unread here; nothing licenses a sentence about "the
  shards" or about `KXMVE` generally.
- **A truncated page, so the pool figures are lower bounds.** `limit=1000` is
  the page limit, not the population: the series was **truncated, not
  exhausted**, so "1,000 open rows" is a floor and the midweek "13 eligible of
  1,000" is a rate over a truncated page, **not over the series**. Sunday's
  equivalent inherits the same truncation and must be reported as a lower bound
  with the word "truncated" in the table.
- **One calendar day**, and the mirror-image caveat in §9 applies with full
  force: this generalises to NFL regular season, September, Sunday, around
  kickoff, on shard 1 — and to nothing else.
- **Nothing about Joe's own positions.** Arm D reads whichever shard-1
  combinations happen to carry an ask; it does not read the tickers he holds,
  and a resting bid on one combination is not an exit for another. Whether a
  position he holds can be closed remains `/hedge`'s question (ADR 0078).
- **The mechanism stays unidentified**, exactly as in §9: a null cannot separate
  *"the product does not permit a resting YES order"* from *"nobody wanted to
  sell today"*, and no result here licenses a sentence beginning
  "structurally".
- **Zero eligible rows would not mean zero combinations.** Eligibility requires
  a readable ask, and the midweek rate was 1.3%; an empty Arm D says the shard
  was unquoted at rest at that instant, which is a claim about quoting, not
  about the exit.

### 11.10 What this amendment does not change, and what needs a word first

**Unchanged, explicitly:** §0's power arithmetic and its prohibition on
reporting a null as confirmation; §2's Arm A population, eligibility and
selection; §3's unit and clustering; §4's three depth thresholds; §5's
statistic and multiplicity count; §6's rules as they apply to Arm A; §7's clock
and stopping rule; §8's cost, safety and non-interference terms; §9's
limitations; §10's result path — which stays a **single** document at
`docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md`, now leading with
Arm D and reporting Arm A second.

**Needs Joe's or the partner's word before Sunday:**

1. **§11.8's scope clause on the buy ticket** — real-money screen text, owed
   regardless of the capture, deadline 15:30Z 2026-09-13.
2. **Arms B and C.** §1's probe found `KXMVENFLSINGLEGAME` and
   `KXMVENFLMULTIGAMEEXTENDED` at **0 open rows midweek**; under the
   instrument's own rule a `--series` with no open rows aborts, so Arm C would
   abort unless the series populate on the day. It stays registered as written
   and is simply expected to abort; that expectation is recorded here so an
   abort is not later read as a failure.

**Nobody running these captures may open the cockpit UI**, per §8: a page-open
registers attention and contaminates the concurrent dwell measurement the odds
freeze exists to protect. Arm D adds two more shell invocations and no browser.

---

## 12. Amendment 2 — Arm D's population is one literal series, and §11.8 is ruled on

**Written 2026-09-09, after Amendment 1 and still before any book is read on or
after this date.** It closes the one thing Amendment 1 left loose — the exact
series Arm D reads — and answers the question §11.10 held open. §§0–10 and
Amendment 1 are not edited; the differences are stated here.

### 12.1 The enumeration, and the population named literally

Probed midweek, **2026-09-09**, against `/series/{ticker}` for existence and
`/markets?series_ticker=...&status=open&limit=1000` for open rows:

    KXMVECROSSCATEGORY-SHARD1              200   1000 open rows   EXISTS
    KXMVECROSSCATEGORY-SHARD2              404      0            does not exist
    KXMVECROSSCATEGORY-SHARD3              404      0            does not exist
    KXMVESPORTSMULTIGAMEEXTENDED-SHARD1    404      0            does not exist
    KXMVENFLSINGLEGAME-SHARD1              404      0            does not exist

**Arm D's population is the literal ticker `KXMVECROSSCATEGORY-SHARD1`, and
nothing else.** Neither baseline series has a shard sibling and neither does
Arm C's.

**It may not be defined as "the shard variants of `DISCOVERY_SERIES`", and the
prohibition is the point.** A family definition would silently change the
population the day Kalshi mints a second shard — the population would be chosen
by the venue's calendar rather than by this document. So:

> **If a shard series that returned 404 on 2026-09-09 exists on 2026-09-13, it
> is NOT read. Arm D reads the one literal ticker above. Adding a series is a
> new registration, not a judgement call made on the morning of the run.**

**404 is today's answer, not a permanent one.** Kalshi mints series; a shard 2
existing next month would not contradict this table. The enumeration is recorded
with its date so a later reader can tell *"we checked and there was one"* from
*"we only thought of one"* — those are different states and only the first is
evidence.

### 12.2 Provenance — this was a gap between two lists in the same repo

`scripts/measure_combo_correlation.py:156` already lists
`KXMVECROSSCATEGORY-SHARD1` among **eight** MVE series. The book-presence
instrument — the one that produced all 40 baseline books — reads
`DISCOVERY_SERIES` (`scripts/measure_combo_leg_echo.py:120`), which has **two**
and never included the shard.

So §1's finding is **not an unknown venue fact and never was**. The shard was
known to this codebase, written down in it, and simply never reached the list
the census instrument reads. That is worth saying plainly because the two
framings license different follow-ups: an unknown venue fact invites more
probing, while a gap between two lists in one repo invites checking whether any
*other* instrument's series list disagrees with its neighbours'.

The series provenance of the existing 40 is now recorded at
`backend/parlays.py:164-170` and pinned by tests (injecting a shard book into a
capture turns three red). **The constant layer is therefore done; what remains
of §11.8 is the two user-facing strings, and 12.4 rules on them.**

### 12.3 The 1,000 rows are a truncated page — and the sampling consequence

`limit=1000` is the page cap and the page **came back full**. Therefore:

- The open shard-1 population is **≥ 1,000 and its true size is unmeasured.**
  "1,000 open rows" is a floor and must be written with the word *truncated*
  beside it every time it appears.
- **13 of 1,000 eligible is a rate over the newest 1,000 rows, not over the
  series.** `markets_page` reads newest-first.

**The consequence for Arm D is a selection property, and it is registered now
rather than discovered in the write-up.** Arm D selects the first eligible rows
in page order from a newest-first, truncated page: it therefore samples the
**newest slice of shard 1**, not a random sample of it. Newly minted
combinations are a plausibly different population from ones that have been open
for weeks — plausibly *less* likely to carry a resting order, which is the
direction that would flatter a null.

Two things follow, both fixed here:

1. **S4, a new descriptive secondary:** the age distribution of the selected
   rows — min, median and max of `now − created_time` — reported per capture and
   pooled. The harness already parses `created_time` into `Row.created_ms`, so
   this needs **no code change**. It is **descriptive only and non-inferential**,
   so §5's multiplicity count is again unchanged.
2. **The null branch's sentence is constrained in advance.** If Arm D returns
   zero YES levels, the licensed sentence is *"no resting YES bid on the newest
   N shard-1 combinations carrying a readable ask, read at five slots on
   2026-09-13"* — with "newest" and the age range in the sentence itself, in the
   result document's **headline**, not in a footnote. A null over the newest
   slice may not be written as a null over shard 1.

This does not change Arm D's cap: 25 remains roughly twice the 13 observed
eligible in the newest 1,000, so it is still not expected to bind (§11.5).

### 12.4 Ruling on §11.8 — the scope correction is owed, and it ships before C1

**Verdict: yes. It is owed, it is not conditional on Sunday, and it should land
before C1 at 15:30Z on 2026-09-13.**

The reasoning is not a preference. The buy ticket's sentence — *"Every
combination book this repo has ever read had no YES bid — 40 of 40, across three
runs on two dates"* — is **true**, is **correctly sourced**, and is **read by
someone who is at that moment tapping a `KXMVECROSSCATEGORY-SHARD1`
combination**, which is a population those 40 books contain **zero** of. A
sourcing guard cannot catch that, because nothing about the digits is wrong;
only the scope a reader will supply is. Waiting for Sunday would mean the screen
makes an unscoped claim *during* the measurement that scopes it, and would mean
the correction never lands at all in the ABORTED-THIN branch — which is
precisely how a caveat gets selected for being survivable.

Requirements on the change, fixed here so it cannot drift:

- **It must name the series the 40 were measured on, or say plainly that no
  shard-1 book has been read.** Either is acceptable; a sentence that leaves the
  reader to infer scope is not.
- **It must not imply the shard was measured**, and it must not imply the shard
  is *different* either — nothing has been measured there yet, and §11.3 forbids
  both comparisons.
- **Sourced, never typed**, through `backend/parlays.COMBO_EXIT_CENSUS_*` and
  the constants in §11.4, per the `ast`-parsing guard that already exists.
- **Pinned by a test that fails when the scope clause is removed**, verified by
  removing it and watching the test go red — not by watching it stay green.
- **Both surfaces**: the buy ticket's `combo_note` (`backend/api/routes.py`) and
  the bid route's 422 (`backend/api/routers/parlays.py`). Correcting one and not
  the other reproduces the original defect on the surface nobody looked at.

**Scope of this ruling, stated exactly.** It is a registrar's ruling on a
factual scope error in copy, and the change alters **no behaviour** — no
ceiling, no route logic, no order path. It is not, and cannot be, authorisation
for anything money-touching. Because the string sits on a real-money surface,
**show Joe the diff** rather than asking him to decide whether a true-but-
unscoped sentence should be scoped.

### 12.5 What Amendment 2 does not change

Arm D's rank as primary (§11.1), its eligibility rule (§11.2), its `n` and floor
(§11.5), its five slots and 140-call budget (§11.6), its decision rule (§11.7),
§0's prohibition on reporting a null as confirmation, §5's multiplicity count,
§7's clock and stopping rule, and §8's cost and non-interference terms. The
result path stays the single document named in §10.

**§11.9's truncation bullet is superseded by 12.3 and by nothing else** — it
said "truncated, not exhausted", which stands; 12.3 adds the newest-first
selection consequence it did not name, and that addition is the reason this
amendment exists rather than a correction of it.
