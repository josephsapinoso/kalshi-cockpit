# 0019 — The agreement family is blind to correlated garbage

**Date:** 2026-08-10
**Status:** Accepted. Two inputs remain open and neither gates the decisions
here — one is answered by a registered Lane B predicate, the other is a
deliberately unsampled stratum. Both are named in "What is still open".
**Extends `0005-the-gate-counts-actionable-games`. Adopts the posture of
`0018-arming-real-trading-is-a-code-change` for `SuppressionConfig`.**

## Context

`tasks/NEXT.md` and `start.md` opened this session with a headline finding:

> `edge_within_method_noise` cannot fire on the one input where the edge is
> purely a devig-method artefact.

Investigating it produced a different and larger answer, and **the headline as
written is wrong**. That correction is the first thing this ADR records, because
the wrong version is the one a future session would otherwise inherit.

Everything below is **measured from code** unless labelled otherwise. Counted
assumptions: **zero**.

---

## 1. The correction: the guard is correctly scoped, and it was not built for
that input

`backend/core/suppression.py:218-221` scopes the check in its own comment:

> If they disagree by more than the edge being claimed, the "edge" is a
> statement about method choice, not about the market.

That is a claim about **method-choice ambiguity and nothing else**. On a
symmetric two-way line — both outcomes at identical decimal odds — method choice
contributes genuinely zero ambiguity, because the vig splits evenly by
construction and every method returns 0.5. The guard passing means *"method
choice does not explain this edge"*, and on that input **that statement is
true.**

So the guard is not broken and must not be patched. The defect in the worked
example is that **one book's dead line became a consensus**, which is a
`book_count` fact — and it was caught, twice.

The scaling is the design working, not failing. `spread_tenths` *is* the minimum
edge the guard demands, and it tracks the true devig ambiguity:

| line | fair | min edge demanded (tenths) |
|---|---|---|
| 1.85 / 1.85 | 0.5000 | 0.000 |
| 1.86 / 1.84 | 0.4970 | 0.343 |
| 1.90 / 1.80 | 0.4848 | 1.731 |
| 2.00 / 1.72 | 0.4576 | 4.793 |
| 2.10 / 1.65 | 0.4323 | 7.736 |
| 2.60 / 1.44 | 0.3386 | 17.883 |
| 3.20 / 1.31 | 0.2652 | 25.279 |

---

## 2. The real finding: an entire guard family shares one blind spot

The suppression layer has two families:

- **Agreement-based** — `edge_within_method_noise` (methods agree),
  `no_market_width` / `wide_market` (books agree), `too_few_books` (enough books
  to agree at all).
- **External-reference** — `suspicious_edge`, `insufficient_depth`,
  `stale_kalshi_quote`, `stale_odds`, `commence_skew`.

**Every member of the agreement family is uniformly blind to correlated
garbage**, because placeholder or copied lines agree with each other perfectly.
Adding a fourth agreement check cannot close a blindness the whole family
shares. That is the content of this ADR, and it is why the obvious fix is
rejected in §3.

### Measured: `min_book_count = 2` does not bound the defect

`tasks/NEXT.md` records the degenerate-fair bug as *"21 rows, 2 games, 1.4% of
the record, all single-book, 0 unsuppressed"* — a statement about rows
**observed**, not about what the guards **permit**. Measured directly by running
`consensus_devig` into `evaluate_suppression`:

| input | fair | width | book_count | result |
|---|---|---|---|---|
| 1 book, 1.85/1.85 | 0.49999999999999994 | `None` | 1 | suppressed — `too_few_books,no_market_width` |
| 2 books, both 1.85/1.85 | 0.49999999999999994 | **0.0** | 2 | **not suppressed, `reason=None`** |
| 2 books, 1.85/1.85 + 1.91/1.91 | 0.4999999999999905 | **0.0** | 2 | **not suppressed, `reason=None`** |

The books need not agree on the hold. Multiplicative devig of a symmetric
two-way line is **exactly 0.5 regardless of hold** — implied probabilities are
both `1/o`, booksum `2/o`, so `(1/o)/(2/o) = 0.5` — and `market_width` is
max-minus-min of `multiplicative[0]` across books (`devig.py:310-313`). A book at
33.3% hold and one at 2.6% hold therefore produce `width = 0.0`, read as
*"the books agree perfectly"*. This `0.0` is a **legitimately measured** zero, so
the `Optional`-not-zero fix already applied to the one-book case
(`suppression.py:191-206`) cannot reach it.

**Reachable is not observed.** Whether any such row exists in the live record is
a pending input; see "What is still open".

---

## 3. Decision: add no new suppression check

Three candidate fixes were considered and all three are rejected. The reasons
are recorded because each will look attractive again.

**(a) Refuse when dispersion is unmeasurable — rejected as a null change.**
Make `method_spread_probability` `Optional` and refuse on `None` when fewer than
two books contributed. `market_width is None` ⟺ `len(selected) <= 1` ⟺
`book_count < min_book_count`, so this fires on **precisely** the rows
`too_few_books` and `no_market_width` already fire on — 185 rows each over 1,000,
symmetric difference 0. It would add a third name for one condition and close
nothing.

**(b) Floor the dispersion at some epsilon — rejected permanently, on the
arithmetic.** The venue advantage this project hunts is **0.38 points = 3.8
tenths**. The largest clean gross edge in the whole record is **17.9 tenths**
against a **20.0-tenth** fee, and the largest clean net edge is **−2.1 tenths**.
Any floor with enough teeth to bind on a 1.85/1.85 row sits at or above the scale
of the entire edge being hunted. **A dispersion floor is an off switch wearing a
guard's clothes** — the same shape as `tasks/lessons.md`'s *"a threshold set below
a systematic offset is not a risk control, it is an off switch"*, inverted.

**(c) Detect symmetric placeholder lines — rejected, and NOT because the
phenomenon was ruled out.** A census was run rather than the question reasoned
about (`scripts/census_symmetric_lines.py`, over the committed capture). The
detector is rejected because **symmetry is the wrong feature**: a symmetric line
is one instance of *correlated books*, and correlation is pervasive in this feed
— 43.8% of h2h quotes exactly duplicate another book's quote on the same event.
A symmetry detector would have caught 0 rows in this capture while leaving that
untouched.

**Scope of the symmetric-line census — the sentence that must travel with the
number.** Measured on `tests/fixtures/odds_mlb_h2h_spreads_totals.json`
(`captured_ms` 1786110562317; 15 MLB events, 29 h2h-quoting books, 425
two-outcome h2h quotes): **0 quotes had `price_a == price_b`**, minimum
`|price_a − price_b|` 0.030, against a positive control of **6/303 spreads and
7/290 totals that *were* symmetric** — so the comparator demonstrably fires and
this is a measured zero, not a broken detector. That bounds the
symmetric-moneyline rate at **≤0.70% per quote** (one-sided 95%,
Clopper-Pearson), but the 425 quotes are 29 books × 15 events at a single
instant and **43.8% of them exactly duplicate another book's quote on the same
event**, so if the behaviour is a property of a book the honest ceiling is
**≤9.81% per book (n = 29)**. It does **not** sample the population the observed
defect occupied: every fixture event carried **24–29 h2h-quoting books** and
every line was **under 2.1 minutes old, 8.9–12.4 hours before first pitch**,
whereas all 21 degenerate-fair rows in the live record were **single-book
WNBA**. The capture contains **zero single-book markets**. Freshly-posted lines,
single-book coverage, and non-MLB leagues were not observed at all. **§3(c)
therefore stands as unmeasured in the relevant stratum, not as refuted.**

The coverage mismatch is the load-bearing half, not the league mismatch: "a
book's placeholder logic is not sport-specific" is arguable, whereas "every
known instance was single-book and this fixture has no single-book markets" is
measured. A rate computed over an interval containing none of the relevant
opportunities is not a low rate.

**One argument considered and dropped.** That a moneyline at 1.85/1.85 is "a
totals-family default price emitted into an h2h slot", because 1.85 is 0.6% of
h2h prices and 5.9% of totals prices. Conditioning on the near-even band
[1.80, 2.00] collapses that ~10x to ~2x (3.4% vs 7.2%) on **n = 5**, and 1.85 is
only the *fifth* most common totals price. It is a base-rate artefact and the
price was selected post hoc because it matched the WNBA defect. Recorded as
dropped so it is not rediscovered.

---

## 4. `edge_ceiling_tenths` is load-bearing against fabricated fairs, and was
never justified for that

This is the clause with teeth. Work the bound at the deployed fee, with
`edge_tenths` post-fee (`suppression.py:126`), on a fabricated `fair = 0.5`:

A row surfaces only when `0 < net_edge <= edge_ceiling_tenths`. Computed with the
**real** `edge_after_fees_tenths`, not an assumed flat fee — the conservative
max-of-models fee is empirically flat at 20.0 tenths across this band, which is
what makes the arithmetic clean:

```
edge_ceiling_tenths = 40.0
  =>  window = [440, 479] tenths  =  44.0c to 47.9c  =  exactly 4.0c wide
```

**A fabricated 0.5 fair can only reach the screen when Kalshi is itself asking
44.0–47.9c** — that is, when the fabrication is nearly right anyway. Outside that
4c window `suspicious_edge` fires.

`edge_ceiling_tenths` was justified as *"Kalshi prices to ~2c, so 4c is already
well outside what the venue plausibly leaves lying around"* (`suppression.py:60-62`).
It is now **also the only thing bounding degenerate fairs, which is not what it
was justified for.** An undeclared dependency of that kind is exactly how a
future session raises a threshold for one stated reason and silently widens an
unrelated hole.

And the existing test does not stop that. `tests/test_suppression.py:167` asserts

```python
assert 20.0 <= CONFIG.edge_ceiling_tenths <= 60.0
```

**an inequality, not a pin** — the repo's own lesson, *"an inequality is not a
pin"*. It permits the ceiling to go to 60.0, and the hole widens with it:

| ceiling | fabricated-fair window | width |
|---|---|---|
| 40.0 (deployed) | 44.0c – 47.9c | 4.0c |
| 50.0 | 43.0c – 47.9c | 5.0c |
| 60.0 (top of what the inequality permits) | 42.0c – 47.9c | 6.0c |

**Measured by deformation, and it corrects a claim this ADR made in draft.** The
first draft said the ceiling could be raised to 60.0 with the suite staying
green. That is false, and the true version is more interesting:

| deformation | pre-existing suite | new pin |
|---|---|---|
| ceiling → **50.0** | **green — nothing catches it** | red (`window opens at 430`) |
| ceiling → **60.0** | red, 2 tests | red (`window opens at 420`) |

A raise to 50.0 — a 25% wider hole — is **invisible to every test that existed
before this ADR.** A raise to 60.0 is caught, but only by
`test_a_large_edge_is_treated_as_a_defect`, which happens to use `60.0` as its
example edge value; at a ceiling of 60.0 that edge stops being suppressed. It is
caught by a coincidence of fixture choice, not by design, and it would go green
again if someone "fixed" that fixture to 70.0.

**Decision:** declare the dependency in `suppression.py` and pin it with a test
asserting the property directly — *a 0.5 fair cannot surface outside a
44.0–47.9c ask window at the deployed fee*. Verified the repo's way, by raising
the ceiling and watching it go red. **That test is the guard.** It fails loudly
on the day someone raises the ceiling to make the screen show something, which is
the same day `min_book_count` comes under pressure.

---

## 5. `min_book_count` stays at 2, stays in code — and is doing more work than
believed

**Rejected: plumbing it to the environment.** It is not a threshold, it is the
*definition of consensus*: below two books there is no consensus, and every
downstream number is a statement about one bookmaker's vig.

The argument that will be made against this ruling, disarmed in advance: NEXT.md
records **eight rows that were fresh, fillable, +1.2c post-fee, and stopped only
by this threshold** (ids 979/980 are the worked example). Those rows are **the
bug's output, not the bug's cost.** Their +1.2c is computed from a fabricated
50/50 fair on a game Kalshi prices **84/16**. Anyone proposing to lower the
threshold must refute that first, in writing.

**Generalised, and adopted deliberately rather than left accidental: no field of
`SuppressionConfig` is env-plumbed anywhere.** Verified — the module contains no
`os.environ`, no `getenv`, no `load()`; every one of the eight construction sites
is bare (`backend/api/routes.py:236`, `backend/runner.py:520/956/984`,
`backend/seed_demo.py:207`, `scripts/run_chain.py:104/113`,
`scripts/run_loop.py:269`); and no `MIN_BOOK_COUNT`, `MAX_MARKET_WIDTH`,
`EDGE_CEILING_TENTHS` or `MIN_DEPTH_CONTRACTS` appears in `fly.live.toml`,
`fly.demo.toml`, `.env` or `.env.example`. This is the same posture as ADR 0018:
**changing what the record counts is a code change, not a config act.**

### The live system holds two suppression configs that agree by coincidence

Sharper than "the thresholds are hardcoded", and new:

- `scripts/run_loop.py:269` — bare `SuppressionConfig()`, reached via
  `docker/entrypoint.sh:159`. **This object decides what the live loop suppresses.**
- `backend/api/routes.py:236` — a **second, independent** bare construction,
  reached via uvicorn at `entrypoint.sh:119`.

They are equal only because both are defaults. Env-plumbing would have *coupled*
them — a genuine argument for (b) that nobody had made. It still loses, because
there is a fix that buys the coupling without buying a knob: **one process-wide
`SuppressionConfig`, constructed once, in code.**

---

## 6. `max_odds_age_ms`: one quantity, four copies, and a docstring that
promises what the code does not do

`SuppressionConfig.max_odds_age_ms = 900_000` (`suppression.py:40`) is hardcoded
and does **not** read `MAX_ODDS_AGE_S`, which `StalenessConfig.load()`
(`backend/config.py:380`) reads and `gate.py`, `live.py` and `routes.py` consume.
They agree numerically today: `900 s × 1000 = 900_000 ms`.

**The live consequence is worse than previously recorded.** `window_status` is
called twice, with two different inputs:

```
scripts/run_loop.py:325     max_odds_age_ms=suppression.max_odds_age_ms
                            (hardcoded 900_000 — decides what the loop
                             schedules and spends credits on)

backend/api/routes.py:608   max_odds_age_ms=staleness.max_odds_age_s * 1000
                            (env-derived — decides the window banner on the
                             phone Joe operates this from)
```

And `routes.py:594-597` states in its own docstring the hazard it fails to avoid:

> Computed by the same planner the runner spends credits with, not a second
> implementation of it. A screen and a control that derive the same schedule by
> two paths eventually disagree, and the screen is the one that gets believed.

They **did** avoid the second implementation and got the divergence anyway,
through the *inputs* rather than the code. **Sharing an implementation does not
share its arguments.** A docstring asserting a property the code does not have is
worse than no docstring: it is what a future session trusts instead of checking.

Four independent copies of 900 seconds, coupled by nothing:

1. `backend/core/suppression.py:40` — `900_000`, never reads env
2. `backend/config.py:374/380` — `_int("MAX_ODDS_AGE_S", 900)`
3. `fly.live.toml:128`, `.env:36`, `.env.example:71` — `900`
4. `tests/test_sweep_timing.py:54` — `MAX_ODDS_AGE_MS = 900_000  # matches
   SuppressionConfig.max_odds_age_ms` — a comment asserting an agreement that
   **nothing enforces**

**Decision:** single source at the divergent call site, plus a **runtime**
assertion at startup — deliberately **not** a test. A test compares one
hardcoded default against another hardcoded default and passes green forever
while the live instance diverges, because the divergence is created by the env
value a test never sees. That is a verification method that lies. Fail at boot,
loudly.

Precedent for the shape: `TestTheTwoCommenceLimitsAgree`
(`suppression.py:42-53`), which exists for exactly this failure on
`max_commence_skew_ms`.

**Implemented:**

- `config.assert_odds_age_limits_agree` raises `StalenessLimitsDisagree`, naming
  both values, what diverges, and this ADR. It **raises rather than warns** —
  the failure it prevents is silent by construction, so a log line nobody reads
  is not a control.
- Called at both entry points: `backend/api/routes.py` in `create_app`, and
  `scripts/run_loop.py` at startup — the process that spends odds credits.
- `run_loop.py`'s `window_status` call now derives from
  `staleness.max_odds_age_s * 1000`, the same expression `routes.py` uses, so
  the screen and the control cannot drift even if the assertion is relaxed.
- `TestTheTwoOddsAgeLimitsAgree` pins that the assertion exists, fires **in both
  directions** (a guard that catches only a loosening is half a guard), and that
  neither call site regresses. Verified by deformation: restoring the old
  argument turns it red.

**One site deliberately not changed, and stated rather than left to be found.**
`backend/runner.py:989` still passes `suppression.max_odds_age_ms` into the odds
sweep. It is safe *because of* the startup assertion — the two values cannot
differ at runtime — but it is not literally single-source, and closing it means
threading `StalenessConfig` through `run_once`'s signature. That is a wider
change than this ADR's thesis warrants, and the assertion is what makes leaving
it defensible. If the assertion is ever removed, this becomes live again.

---

## 7. `too_few_books` and `no_market_width` are NOT collapsed

They fire on the identical condition today — 185 rows each over 1,000, symmetric
difference 0 — which reads as a case for merging them. Rejected, and the reason
is now a textbook instance rather than a judgement call:

**The equivalence holds only at `min_book_count == 2`, and is coupled by
nothing.** `devig.py:312` hardcodes a literal `1` (`len(first_values) > 1`);
`suppression.py:187` reads `config.min_book_count`. The `config` object is not
even in scope inside `consensus_devig`. At `min_book_count = 3`:

| `len(selected)` | `too_few_books` | width branch |
|---|---|---|
| 1 | FAIL | `no_market_width` FAIL |
| 2 | **FAIL** | real float → `wide_market`, normally **passes** |
| 3+ | pass | `wide_market` evaluated |

So they are **two limits on one quantity, currently equal by coincidence** — the
repo's recurring pattern. Collapsing them would delete the cross-check; keeping
them costs nothing and they carry different diagnostic meaning to a reader
("there was no second book" vs "the books disagree").

**Decision:** keep both, and add the **divergence** as a third diagnostic.
`market_width is None` with `book_count >= 2`, or the reverse, is an upstream
defect and should say so. That converts an accidental redundancy into an
asserted invariant.

**Counting note that belongs with the suppression summary:** three codes over one
condition read as defence in depth and are one check. Count guard *families*, not
guard *names*, and check row-sets rather than labels.

---

## 8. Not decisions, fixed in the same commit

- **`usable_book_count` is persisted nowhere.** Computed at `devig.py:339`; the
  only readers in the repo are `tests/test_devig.py:309` and `:312`. So the live
  database **cannot** distinguish "one book quotes this market" from "five books
  quoted it and sharp anchoring kept one" — the disambiguation
  `tasks/lessons.md` says is "now reported" reaches no durable surface.
- **`backend/runner.py:342` writes `metadata.get("book_count", 0)`**, defaulting an
  unreadable count to `0` against this repo's never-resolve-to-zero convention.
  Unreachable from the only production caller (`consensus_devig` always sets the
  key), and `0` happens to be the safe direction because it trips
  `too_few_books` — which is exactly why it survived. The adjacent
  `metadata.get("market_width")` on line 341 correctly has no default.
- **`fair_prices.book_count` is already `INTEGER NOT NULL`**
  (`schema.sql:302`) and joins to every recommendation via
  `recommendations.fair_price_id`. Nothing to decide.

---

## What this change does NOT do to the record

**`actionable = 0` and the 614 / 45 coherence result survive, and do not have to
be re-derived.** Four reasons:

1. **`suppressed_reason` is persisted, not recomputed.** `backend/engine.py:366-379`
   writes it at INSERT; `backend/gate.py:323` reads it from the table. Every
   historical row carries what the then-deployed code decided at that instant.
2. **Every row is version-stamped — but this ADR had to fix the stamp before
   that was true, and the draft claimed it without checking.**
   `strategy_config_version INTEGER NOT NULL REFERENCES
   strategy_configs(version)` (`schema.sql:354`) is minted by
   `ensure_strategy_config` from a dict that hashed `suppression.__dict__` —
   a set of **field values**. Adding a `Check(...)` changes no field, so
   **adding, removing or renaming a suppression check minted no new version**,
   and two check-vocabularies would have pooled into one dataset with nothing
   recording the split.

   That is the same defect `measurement-skeptic` already found here once, when
   `kelly_fraction` was in the hash and `max_order_contracts` was not — and it
   violates the rule stated in `runner.py`'s own comment four lines above:
   *"everything the counted column depends on, and nothing else."* `actionable`
   is `suppressed_reason IS NULL AND reference_contracts > 0`, so the **set of
   checks** determines it exactly as much as the thresholds do.

   Fixed in this change: `ALL_CHECK_NAMES` is declared in `suppression.py`,
   hashed into the strategy config as `suppression_checks`, and pinned against
   the source by `TestTheDeclaredVocabularyMatchesTheCode` so the constant
   cannot drift from the emitted codes. **Only with that in place is the
   separability claim true**, and it is true prospectively — it does not
   retroactively split anything already written.
3. **The direction is one-way.** `actionable` is
   `suppressed_reason IS NULL AND reference_contracts > 0`. Every change here is
   suppression-adding or assertion-only, and adding suppression can only shrink
   the actionable set. **`actionable = 0` is a fixed point under this change.**
4. **The 45 / 614 split is a statement about persisted rows** and stays true of
   them.

**The one cost, stated rather than buried:** any future pooled count spanning the
version boundary is a mixture of two instruments. So this ADR carries a citation
rule — the coherence result is quoted **with its version** ("614 unsuppressed rows
under strategy config v*n*"), and any extension after this change either restricts
to one regime or reports both separately.

---

## 9. Three things deleted or corrected, none of them behaviour

**The `stale_odds` message was false and is corrected here; the remedy is ADR
0020.** `suppression.py` emitted *"book last moved {x}min ago"*. `odds_age_ms`
is measured from The Odds API's `last_update`, which is a **scrape** timestamp:
measured on the captured fixture (15 MLB events, 30 books, 440 book+event
pairs), **320 of 320** pairs quoting more than one priceable market carry one
identical stamp across every market they quote — **258 of 258** of the
three-market subset — and **27 of 30** books have exactly one distinct stamp
across all fifteen games. FanDuel reports `13:49:00Z` for three markets on
fifteen different games. No book reprices fifteen moneylines, run lines and
totals in the same second.

**Corrected 2026-08-09 — this section first read "440 of 440", and that
denominator was padded.** 120 of the 440 pairs quote a **single** priceable
market, where "one stamp across its markets" is vacuously true and no
disagreement was possible. The non-vacuous population is the 320 pairs quoting
two or more, and it is unanimous. The correction does not weaken the finding —
it is the same 100%, over the rows that could have refuted it — but publishing
a denominator inflated by rows incapable of dissent invites exactly the audit
this repo runs on everything else. Same shape as `tasks/lessons.md`'s *a true
measurement licensed a false conclusion*: the number was true and its scope was
wider than what was measured.

**And the correction needed correcting, which is the more useful half.** Its
first version said **335**, counting every market key in the raw payload —
including the `h2h_lay` prices that `EXCLUDED_MARKETS` **never stores**. A stamp
on a row the system discards cannot belong in a denominator about
`odds_age_ms`. Filtering to `PRICEABLE_MARKETS` moves 15 pairs across the
vacuous boundary: 335 → **320**.

Twice, in the same direction, by the same mechanism — a population widened with
rows incapable of refuting the claim. The transferable rule is not *count more
carefully*; it is that **a census supporting a claim about a stored quantity
must apply the same filter the storage path applies.** The raw payload is not
the population. `scripts/census_odds_stamps.py` now imports
`PRICEABLE_MARKETS` from `odds/client.py` rather than re-typing it, so the
census cannot drift from the filter again, and it prints the rejected 335
beside the 320 so the difference stays visible instead of being assumed away.

**And "27 of 30" needs its definition stated, because two defensible counts
differ.** Counting book- and market-level stamps together gives 27 of 30;
counting the book-level `last_update` alone gives **29 of 30**. Both were
computed; the quoted figure is the first.

The payload-level signature is the same fact seen whole, and it is the single
most direct reading: **19 distinct stamps spanning 115 seconds across 30 books,
the latest landing 9 seconds before our fetch.** That is a crawler working
through a queue, not a market moving.

So the guard measures **how long since the aggregator last polled**, not how
long since the line moved, and a book that has not repriced in six hours reads
as fresh indefinitely. **The wording is fixed here and when the guard fires is
unchanged.** The remedy is a genuine open design question — record the honest
semantics, derive a reprice proxy by diffing prices across our own polls, or
accept it — with three live options and a cost attached to two. That is ADR
0020's, not this one's; folding an undecided question into a decided one is how
this ADR stops landing.

**The second `SHARP_BOOKS` is deleted, not documented.** `odds/client.py` held
`{pinnacle, betonlineag, lowvig, circasports}` under a comment nearly identical
to the live `runner.py:103` set `{pinnacle, betfair_ex_eu, betfair_ex_uk,
matchbook}` — one shared member of four. Its only reader was an `is_sharp`
property with **no production caller**, so the two could disagree indefinitely
without a symptom. Deleted rather than annotated: documenting a duplicate makes
it look deliberate, and the identifiable victim is whoever edits the dead copy
believing they changed what the money path anchors on.

**And the guard was on the dead copy.** `tests/test_odds.py` asserted the sharp
set was small and excluded FanDuel; `runner.SHARP_BOOKS` — which
`consensus_devig` actually receives, and which discards a **median of 26 of 29**
usable books — had no assertion at all. The guard moves to
`tests/test_runner.py::TestTheSharpSetThatActuallyAnchors`, which also pins the
wiring, because a correct set that nothing passes to `consensus_devig` is
precisely what the deleted copy was.

> **ANNOTATION 2026-08-10 — `median of 26 of 29` above is a FIXTURE figure.**
> The sentence is left as written and its *argument* is untouched: the guard was
> on the dead copy, and that is a fact about the code. Only the parenthetical
> magnitude is mislocated. `26 of 29` is measured on
> `tests/fixtures/odds_mlb_h2h_spreads_totals.json`, captured
> **2026-08-07T13:49:22Z**, against a record whose earliest odds observation is
> **5.65 hours later** — overlap is **0 of 1,564 rows**. Quote it only as
> *"measured on one MLB fixture captured before the record begins"*, never bare
> and never as a property of the record. See ADR 0021 §7.2's annotation, which
> rules this and states what survives.

This is the **sixth** built-never-called item in a repo whose CLAUDE.md cites
four. Six is a process gap, not a run of coincidences, and
`tests/test_has_callers.py` cannot catch it because `MUST_HAVE_CALLERS` is
opt-in — absence from the list is indistinguishable from having a caller.

> **ANNOTATION 2026-08-10 — the count was six; it is NINE, and the detector has
> now been inverted.** The paragraph's diagnosis was right and its number was
> low. An enumerate-and-classify census found **nine module-level dead**, plus
> four partially dead and a symbol-level tail. Worse than "opt-in": all fifteen
> `MUST_HAVE_CALLERS` entries named symbols that *already had callers*, so the
> list had never once been pointed at anything orphaned at the time. Five of the
> nine were invisible for a second reason this ADR did not know — the detector
> counted `scripts/` as a caller, while `.dockerignore` admits only two of the
> thirty-four scripts into the image. **ADR 0022** owns the inversion, the
> classification and the disposition (quarantine, not wire, not delete).

**The vector-collapse remedy is considered and deferred, pending one number.**
`kalshi-platform` proposed collapsing identical price vectors to one contributor
before computing `book_count` and `market_width`, which subsumes the symmetric
case. It is probably a no-op on the money path: the duplicate groups are
recreational books (`betsson`/`nordicbet` are one operator), and sharp anchoring
discards them *before* the consensus exists — measured, `consensus_devig` keeps
`betfair_ex_eu + matchbook (± pinnacle)` on all 15 events and `market_width` is
never 0.0 (range 0.00044–0.00924). Lane B's pull carries the predicate that
settles it: the post-anchor `book_count` distribution and whether any
duplicate-vector pair survives anchoring in `books_used`. **Zero survivors → the
collapse is recorded here as considered-and-rejected-with-a-number and never
revisited. Some survive → it returns as its own decision with a measured blast
radius.** Not implemented, because it changes `book_count`, which changes
`too_few_books`, which changes what the gate counts.

---

## What is still open

**Input 1 is now ANSWERED: reachable, never occurred.**
`docs/measurements/2026-08-10-clean-shortfall-distribution-result.md`, §S6,
pinned pull at `pin = 1564`:

```
n_degen, clean population (pre-dedup)          0
n_degen, suppressed population (control)      21
clean degenerate rows in ask [440, 479]        0
```

**[MEASURED FROM DATA]** All 21 degenerate rows carry `too_few_books`, so all 21
are **one-book** fairs — which the deployed guards do catch — across 2 WNBA games
(`KXWNBAGAME-26AUG10CHISEA` 11, `KXWNBAGAME-26AUG10TORATL` 10), asks 160–850
tenths, every one suppressed. **The two-book case this ADR proves reachable has
not occurred on this record.** That vindicates the framing choice above: writing
it up as a live bug would have been false.

Two honest notes. **The ULP correction cost nothing here** — every one of the 21
carries `p_power` exactly one ULP below 0.5, so the broad and narrow predicates
returned the same 21 and the measured undercount is **0**. It was still right to
make: it is the only predicate that would catch the `1.95/1.95` case, and its
price was zero. And **the run declared nothing** — it tripped `STOP THE LINE` on
R3 saturation (Grid D's middle cell holds 99.1% of observations), so H4's verdict
is formally *withheld*. The census statistics above are printed regardless, by
that registration's own §S, and they are what closes this input; the ADR does not
inherit a claim the measurement declined to declare.

One input remains:

1. ~~**Does any two-book degenerate row exist in the live record?**~~ **Answered
   above.** The predicate is retained for re-runs. Existence check,
   predicate fixed in advance, binary outcome — registration discipline governs
   effect estimates where the analyst has degrees of freedom, and this has none:

   ```sql
   SELECT fp.book_count, r.suppressed_reason, COUNT(*),
          MIN(r.edge_tenths), MAX(r.edge_tenths)
   FROM fair_prices fp JOIN recommendations r ON r.fair_price_id = fp.id
   WHERE ABS(fp.p_multiplicative - 0.5) < 1e-12 AND fp.book_count >= 2
   GROUP BY fp.book_count, r.suppressed_reason
   ```

   Zero rows → *reachable, never occurred*, and the §4 pin-test is the whole
   remedy. Non-zero → this ADR carries the count and the ask distribution.

   **Note the predicate deliberately does not require `p_power` one ULP below
   0.5.** `tasks/lessons.md` names that as the signature; it **undercounts**.
   Where the odds devig to an exact 0.5 — e.g. 1.95/1.95, where the spread is
   exactly `0.0` and the guard is *more* dead, not less — `p_power` is exactly
   0.5 and the ULP condition silently drops the row.

   **This is answered for free by Lane B and needs no new route.** The clean
   population is `suppressed_reason IS NULL`, and `too_few_books` fires iff
   `book_count < 2` — so **a clean row has `book_count >= 2` by construction**,
   and every clean row matching the predicate above *is* a two-book degenerate
   row. `fair_prices.book_count` never needed to be on the ledger payload. It is
   registered as H4 in
   `docs/measurements/2026-08-10-preregistration-clean-shortfall-distribution.md`.

2. **Do books post symmetric placeholder lines at POSTING time, on thin books,
   in low-liquidity leagues?** Deliberately stated as a stratum, not as a
   feed-wide question — the feed-wide form invites an answer the available
   capture cannot support, which is the error §3(c)'s scope sentence exists to
   prevent. The mature-MLB stratum is measured and returns zero; the
   posting-time and single-book strata are **unsampled**.

   The capture that would answer it is costed at **24 credits** (WNBA plus one
   low-liquidity league, taken twice — ~48h out and ~2h out) against a 400/day
   budget. The **repeat poll is the primary purpose**, not the league coverage:
   two polls of the same games at a short interval, checking whether
   `last_update` advances while prices are byte-identical, converts the
   scrape-clock finding from inference to proof — and unlike the symmetry
   census that generalises past one league, because it is a fact about the
   aggregator rather than about MLB. **It is a spend, so it is Joe's call.**

## What this does NOT establish

- **Nothing here says a degenerate fair has ever cost anything.** It has not: 21
  rows, 1.4%, 0 unsuppressed, 0 actionable. The harm on occurrence is not
  "lose 4c" — it is "bet blind on a game nobody priced" — and its frequency is
  capped by requiring Kalshi to sit in a 4.0c band.
- **`stale_odds` measures feed age, not line age.** A placeholder line arrives
  perfectly fresh. Whether that is a real third blind spot is part of pending
  input 2.
- **This is a property of the code at `31ac923`**, not a design guarantee. The
  §4 pin-test makes the ceiling's second job loud; it does not make changing it
  hard.
