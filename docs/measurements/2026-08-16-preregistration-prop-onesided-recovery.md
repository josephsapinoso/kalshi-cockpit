# Pre-registration — can a one-sided alternate prop quote be recovered from the book's own primary overround?

**Registered:** 2026-08-16, **before any recovered price has been computed on
any row.** `prop_quotes_for_event` has dropped every one-sided book since it
shipped; nothing in this repo has ever produced a recovered Under, so there is
no prior look to be contaminated by.

**Owns:** the `prop-rungs` query in `scripts/inspect_live_db.py`,
`scripts/analyze_prop_onesided.py`, and the result document they produce.
**Defers to** `docs/adr/0021` on strategy and changes nothing about it.
**Changes no money path unless §5 returns ADOPT**, and even then the change is
a separate commit with its own review.

---

## 0. Why this is being asked at all

`backend/runner.py:407-412`, which is the code that does the dropping:

> A book quoting only one side is dropped, and that is the dominant loss:
> measured at 174 of 222 matched keys on 2026-08-14, because the alternate
> feeds are mostly Over-only. Recovering them means estimating a book's
> overround from its own two-sided primary line, which is an assumption and
> needs registering as one -- so it is not done here, and the drop is counted
> rather than quietly absorbed.

`docs/measurements/2026-08-14-prop-dispersion-scoping-probe.md` prices the
prize at **~4.6× the comparison count for zero extra Odds API credits** — the
one-sided rows are already in the payload we have already paid for, already
stored in `odds_snapshots`, and thrown away at read time.

**That 4.6× is the thing this document is most suspicious of.** It is the ratio
of *dropped* keys to *kept* keys. It is **not** the ratio of *recoverable* keys
to kept keys, because a one-sided alternate rung can only be recovered if the
same book also quotes a **two-sided primary** line for the same player and the
same base market. Nobody has counted how often that holds. §4.1 counts it
first, and §5 lets that count kill the change on its own, before accuracy is
looked at.

## 1. The question

> **Does a book's overround, measured on its own two-sided primary prop line,
> reproduce the price it charges on its alternate rungs closely enough that a
> recovered Under can enter a consensus?**

Not "are there more rows". Not "is there an edge in props". Only whether the
substitution is accurate enough to be worth less than the error it replaces.

## 2. The trap this is built around

The devig-method spread on this record is **1–2 percentage points**, and
`CLAUDE.md` rule 2 exists because that already exceeds the fee advantage being
hunted (**0.63 points**, itself an upper bound pending H4 — ADR 0027).

> **A recovery that injects error of the same order as the method spread buys
> rows at the price of the thing the rows were for.**

4.6× the comparisons is worth nothing if every comparison now carries an extra
error term as large as the edge. The bar below is set against the fee headroom,
not against "seems close enough".

There is a second, sharper trap and it is why §7 exists:

> **The validation subset is the books that chose to quote both sides.** They
> may be exactly the books, players and rungs where margins are most
> conventional. An error measured there is a *lower* bound on the error where
> the recovery would actually be applied.

## 3. Population

Every `odds_snapshots` row on the live instance carrying
`outcome_description IS NOT NULL` (the schema's own prop discriminator, the
same one `prop-bookmakers` uses), restricted to **the latest `fetched_ms` per
`odds_event_id`** — one sweep, for the reason `prop_quotes_for_event` reads one
sweep: mixing sweeps pairs a fresh price with an old one and calls the
disagreement margin.

A **rung** is `(odds_event_id, bookmaker, base_market, normalised player,
point)`. `base_market` folds `_alternate` onto its primary exactly as
`backend/kalshi/props.base_market` does, and the feed a rung came from is
carried alongside rather than lost.

Rungs are excluded, and each exclusion is counted and reported:

- `outcome_description` absent, `outcome_point` NULL, or `outcome_name` outside
  `("Over", "Under")`. **Never substituted** — an unreadable rung is not a
  symmetric one.
- `price_decimal <= 1.0`, which is not a decimal odds quote.
- A rung quoting the same side twice within one book and one sweep. This is not
  expected; if it occurs it is a finding about the store, not a row to average.

## 4. The statistic

### 4.1 The feasibility count — reported FIRST, before any accuracy number

For each `(odds_event_id, bookmaker, base_market, player)`:

| quantity | definition |
|---|---|
| `kept` | alternate-feed rungs that are two-sided (today's usable set) |
| `dropped` | alternate-feed rungs that are one-sided |
| `recoverable` | `dropped` rungs where that same book/player/base_market has **at least one two-sided primary-feed rung** |
| `unrecoverable` | `dropped` − `recoverable` |

Reported per bookmaker and per base_market, never pooled only. The headline is
`recoverable / kept`, and it is **the honest replacement for the 4.6×.**

### 4.2 The recovery, stated as arithmetic

For a book `b`, player `p`, base market `m`, with a two-sided **primary** rung
at point `q` quoting decimal odds `o_over(q)`, `o_under(q)`:

```
V = 1/o_over(q) + 1/o_under(q)          # the book's overround, > 1
```

Where `b` quotes two or more two-sided primary rungs for `(p, m)`, `V` is the
**median** of their overrounds, and the count is carried on every recovered row.

Given a one-sided alternate rung at point `r` with only `o_over(r)`:

```
implied_under_hat = V - 1/o_over(r)
o_under_hat       = 1 / implied_under_hat
```

**`implied_under_hat <= 0` is a refusal, never a clamp.** It means the Over
alone already implies more than the book's whole book, so the assumption has
failed on that rung. Counted as `refused_nonpositive` and reported; the rung
stays dropped.

### 4.3 Level 1 — the mechanism error (diagnostic)

On alternate rungs where the book **does** quote both sides, hold out the
Under, recover it from §4.2, and compare devigged Over probabilities:

```
p_true = (1/o_over) / (1/o_over + 1/o_under)         # multiplicative, per book
p_hat  = (1/o_over) / V
err    = 100 * (p_hat - p_true)                      # percentage points, signed
```

Multiplicative devig is named here because a single book's own margin is what
is being tested; worst-of-four is a rule about a *consensus* and does not apply
to one book's two prices.

Reported per bookmaker: `n`, median `err`, median `|err|`, p90 `|err|`.
Per `CLAUDE.md`, **no bookmaker with fewer than 5 held-out rungs gets a
per-book number**, and the largest contributor's share of the pooled `n` is
printed beside every pooled figure.

### 4.4 Level 2 — the consensus error (this is what the rule reads)

The money path consumes a **consensus**, not one book. On every alternate rung
where **at least 2 books** quote both sides, build the fair Over probability
twice through the repo's own `consensus_devig(outcomes, quotes_by_book,
sharp_books=SHARP_BOOKS)` and read it with
**`DevigResult.conservative_probability("Over")`**:

- `fair_true` — from the actual two-sided quotes.
- `fair_hat` — with **every** book's Under replaced by its §4.2 recovery.

`conservative_probability` is named rather than `multiplicative` because it is
the exact call `backend/engine.py:124` makes on the way to an EV, so the error
being measured is the error the money path would actually inherit. It is the
worst of four methods, per `CLAUDE.md` rule 2, and a recovery could in
principle move *which* method is worst — that is a real effect and it belongs
inside the measured number rather than being defined away by picking one method.

```
delta = 100 * (fair_hat - fair_true)                 # percentage points, signed
```

Reported: `n`, median `delta`, median `|delta|`, p90 `|delta|`, and the same
per-bookmaker-composition and largest-contributor disclosure.

## 5. The decision rule, fixed now

**Gate A — feasibility. Read before anything else.**

| `recoverable / kept` (§4.1) | Verdict |
|---|---|
| `< 0.5` | **NOT WORTH IT.** Fewer than one extra comparison per two existing ones. The change is refused on size alone and accuracy is reported but carries no verdict. |
| `>= 0.5` | proceed to Gate B |

**Gate B — accuracy, on §4.4's `delta`.** Requires `n >= 30` Level-2 rungs; below
that the run is **UNRESOLVED** and no further look is licensed without a new
registration.

| condition | Verdict |
|---|---|
| median `\|delta\| <= 0.5` **and** p90 `\|delta\| <= 1.5` **and** `\|median delta\| <= 0.3` | **ADOPT** |
| median `\|delta\| >= 1.5` **or** `\|median delta\| >= 0.5` | **REFUSE** |
| otherwise | **UNRESOLVED** |

**Where the three numbers come from, chosen before the run.**
`0.5` is below the 0.63-point fee headroom (ADR 0027), so an adopted recovery
cannot be the largest term in an edge it helps produce. `1.5` is the middle of
the 1–2 point devig-method spread: at that size the recovery is injecting as
much error as the disagreement rule 2 already refuses to trade through.
`0.3` on the *signed* median is tighter than the absolute bar on purpose — a
systematic shading moves every recovered row the same direction and does not
average out across rows the way noise does, so it is the more dangerous failure
and gets the stricter bar.

**Per-book agreement is a precondition of ADOPT, not a footnote.** If any
bookmaker with `n >= 5` has a median `|err|` (§4.3) above `1.5`, the verdict is
at best **ADOPT-PARTIAL** and the recovery applies only to the books that pass,
named explicitly in the result. A pooled number is not a finding until the parts
agree.

## 6. What would falsify the motivating idea

The motivating idea is *"books charge one margin per player-market, so the
alternate ladder inherits the primary's overround."*

It is falsified if §4.3's per-book signed median is materially non-zero — most
plausibly **positive**, i.e. books charge *more* on the thin alternate rungs
than on the primary. That is the outcome to expect on priors, and if it appears
the recovery is not merely noisy but biased toward making every recovered Over
look cheap, which is the direction that manufactures fake edges. **A positive
bias is therefore reported as the headline even if the absolute bars pass**, and
ADOPT is refused under the `|median delta| <= 0.3` clause regardless of how
small the scatter is.

Gate A falsifies a different and larger claim: that there is a 4.6× prize here
at all.

## 7. What this cannot establish, and these are not hedges

- **The validation set is not the application set.** Error is measured only
  where a book quoted both sides on an alternate rung; the recovery is applied
  where it did not. If a book goes one-sided precisely when it is least
  confident or widest, the measured error is a floor. **No result here licenses
  a claim about the rungs it could not check**, and the result document must
  say so in its own §1.
- **It is one sweep per fixture, on whatever slates the live record holds at
  run time.** No second horizon, no persistence claim, no seasonality.
- **It says nothing about whether the recovered rows contain an edge.** They
  are comparisons, not bets. Only CLV against Kalshi's own close can answer
  that, and it is item 3 on `tasks/NEXT.md`, registered separately.
- **It says nothing about fills.** Every price is a stored quote, on both
  sides of the comparison. `AVAILABILITY IS NOT FILLABILITY` stands.
- **It does not touch the fee question.** Props are baseball and are charged
  `k = 0.035` while priced at `0.070`; that understatement is unchanged by
  anything here and is not this document's to resolve. ADR 0028, ADR 0023.
- **It does not revisit `SHARP_BOOKS`.** Eight books quote MLB props and none is
  Pinnacle or Betfair, so `anchored_on_sharp` is 0 on every one of these rows by
  construction — before this change and after it.
- **Multiplicative devig at Level 1 is a choice**, not a neutral measurement. It
  is used because it is the method whose only input is the book's own two prices.
  A different single-book method would give a different `p_true`; the Level 2
  number, which is the one the rule reads, goes through the repo's real
  consensus path instead.

## 8. Cost and safety

**Zero Odds API credits. Zero writes. No order path.** The data is already
bought and already stored. `prop-rungs` is a fixed SQL constant on
`inspect_live_db.py`'s whitelist, run against a `mode=ro` connection, with
every caller-influenced value bound as a parameter. It emits **raw rungs, not
aggregates**, because that script is explicitly not a measurement harness;
`scripts/analyze_prop_onesided.py` does every calculation above, is excluded
from the image by `.dockerignore`, and is a laptop `Tool` in
`tests/test_has_callers.py`'s sense.

**The query must reach the machine before it can be run.** `.dockerignore`
decides what ships, not `Dockerfile` — `inspect_live_db.py` is already
re-included, so a new query inside it ships with the next deploy of that file
and needs no widening. `analyze_prop_onesided.py` must **not** be added to the
image.

## 9. The stopping rule

**One run.** The `prop-rungs` dump is taken once, after the next deploy, over
whatever fixtures the live record then holds. The verdict is computed once from
that dump and written up once.

A second dump on a later slate is a **new registration**, not an amendment, and
the only thing that licenses one is an **UNRESOLVED** verdict under Gate B's
`n >= 30` floor — i.e. not enough rungs existed to decide, which is a failure of
supply and not of the hypothesis. An UNRESOLVED verdict *with* sufficient `n`
closes the question at REFUSE for practical purposes: the design was given its
chance and did not clear a bar fixed before the data was seen.
