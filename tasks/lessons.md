# Lessons

Dated, one lesson per entry. Written when something was got wrong, or when a
correction arrived. Reviewed at session start.

Two rules for this file, inherited from the previous project because they are
what made it useful rather than decorative:

- **Write the pattern, not the incident.** "PR #42 broke staging" ages out;
  "unreadable must never resolve to zero" doesn't.
- **A lesson earns its place by preventing a repeat.** If it would not have
  changed what someone did, it is a note, not a lesson.

---

## 2026-08-06 — Unreadable must never resolve to zero

Ported from the previous project, where it was learned the expensive way.

At every ingest boundary, a value that cannot be read gets `None`, never `0`.
Zero is a *legitimate* price on Kalshi (a settled loser), so a parser that
returns `0` on garbage is indistinguishable from one that correctly read a
settled market. The caller then refuses rather than substituting.

**Why:** a price that silently became 0 is a free contract in the risk model,
and a quantity that silently became 0 makes an illiquid market look untradeable
rather than unknown — which is a *safe* failure, while the price case is not.

**How to apply:** every parser in `core/prices.py` returns `Optional`. Any new
ingest path does the same. Verify field names against a captured payload, not
against memory — the previous project's `apply_snapshot` read `data["yes"]`
while Kalshi sent `yes_dollars_fp`, and parsed every order book to zero levels,
silently, for the project's entire life while 305 synthetic tests passed.

---

## 2026-08-06 — Clamping is for values you trust

Ported. Clamp what you trust; **refuse** what you are validating.

The previous project clamped an out-of-range order price into the legal 1–99
range. That turned a self-announcing API rejection (`no_price=-390`, which
Kalshi would have refused) into a live buy at 99c. The clamp converted a loud
failure into a silent, expensive success.

**How to apply:** `OrderRequest` validation raises rather than clamps when a
rounded price lands off the tradeable grid. Put the check where every client
sees it — in the request object's constructor, not in the transport layer — so
the paper simulator is held to exactly the same standard as live. A paper fill
that live would have refused quietly poisons the record used to decide whether
to go live at all.

---

## 2026-08-06 — A test that passes on the bug is not a test

Ported. Every guard is verified by **disabling it and watching the test fail**.

Temporarily break the behaviour, run the test, confirm it goes red, restore.
If it stays green, the test is decoration.

**How to apply:** done for the two guards that exist so far —
`unreadable-never-zero` (confirmed a zero-returning parser trips it) and
`conservative-fee-selection` (confirmed committing to model A alone trips it).
Do the same for every guard added later, and never weaken an assertion to make
a test pass.

---

## 2026-08-06 — The conservative fee model is a hedge with an expiry date

Kalshi's official fee PDF returns HTTP 429 to automated fetches — it did when
the previous project was written and it still does. The secondary sources have
since diverged: one reports a single 0.07 coefficient rounded up per *order*,
another reports a ~0.06 sports multiplier rounded to the nearest cent per
*contract*. Neither dominates. At 50c on 100 contracts they differ by 14%; at
20c the ordering reverses.

`calculate_fee` therefore returns the **maximum** across candidate models.
Understating a fee makes a losing bet look profitable and corrupts the
measurement record; overstating one only costs a marginal bet. The asymmetry
is not close.

**But note the cost:** under the per-contract model, sports fees are a flat
1c/contract across roughly 9c–91c. At 10c that is 10% of stake, which
suppresses essentially every longshot. The conservative model is not free.

**How to apply:** do not let this hedge become permanent, and do not wait for
it to resolve itself. It cannot — reading the real fee requires a real fill,
and the live gate blocks real fills. Break the deadlock deliberately: place a
few minimum-size orders at spread-out price points purely to observe the fee,
read it off `/portfolio/fills`, and identify the true model for a few dollars.
Until then, treat any `fee_predicted != fee_actual` as stop-the-line.

---

## 2026-08-07 — Every per-cell guard can pass and the conclusion still be wrong

The demo history is generated with **no edge whatsoever** — every outcome drawn
at exactly the implied probability. Running the calibration mart over it
produced:

```
bucket  n   implied  actual   gap     sig
73.0    46  0.730    0.522    -20.8   True
```

A 20-point "finding", significant at two standard errors, from pure noise.

Every guard behaved correctly. The normal approximation was valid (n·p = 34,
n·(1−p) = 12). The standard error was computed under the null. The sample was
not tiny. Nothing was miscalibrated — and the answer was still wrong, because
**ten cells were tested and roughly one in twenty clears two standard errors by
chance**. Expected false positives: 0.46. Observed: 1. Exactly on the nose.

This is the failure that produced "dozens of significant results" from 1,190
category cells in the predecessor project, and no per-cell guard can catch it.
Only counting can. `mart_multiple_comparisons` now computes the exact binomial
probability of seeing at least this many findings from nothing, and it is meant
to be read *before* any individual bucket.

**How to apply:** a guard that operates on one cell cannot protect a conclusion
drawn across many. When adding a new bucketed measurement, add its tests to the
count. And treat a single significant cell in a grid as what it almost always
is — the one that got lucky.

---

## 2026-08-07 — Computing the right statistic and then ignoring it

The first version of `mart_multiple_comparisons` calculated the binomial
p-value correctly — 0.3723, a better-than-one-in-three chance of seeing the
result from nothing — and then wrote its verdict by comparing *counts* against
the expectation instead:

```sql
when n_findings <= expected_by_chance then 'NOT EVIDENCE'   -- 1 <= 0.46, false
when n_findings <= 2 * expected_by_chance then 'WEAK'       -- 1 <= 0.92, false
else 'Worth investigating'                                   -- ← landed here
```

So the dashboard would have shown `p = 0.3723` in one column and *"Worth
investigating"* in the next.

That is worse than not computing the p-value at all. An absent statistic is an
obvious gap; a correct statistic sitting beside a contradicting verdict looks
rigorous, and the verdict is what gets read.

**How to apply:** when a model emits both a statistic and a human-readable
verdict, the verdict must be *derived from* that statistic, not computed by a
parallel path that happens to sit next to it. If the two can disagree, they
eventually will, and the wrong one is the one people act on.

**Recurred 2026-08-07, in Python instead of SQL.** `BacktestResult.beats_close`
was `disagreement_accuracy > market_accuracy` — a bare boolean with no noise
guard — sitting in the same dataclass as a verdict correctly reading *"inside
the ±8.0 point noise band. No demonstrated edge."* It also ignored `min_games`,
so a 50-game backtest could report `True` beside a verdict saying *"No
verdict"*. The boolean is what a caller branches on.

Both now derive from one `PairedComparison` object, and the invariant is
asserted directly across twelve seeds: **`beats_close is True` if and only if
the verdict claims an edge.** The seed sweep matters — the two paths agreed
whenever the gap was large and diverged exactly on the marginal cases, so a
single-fixture test can pass over the bug. That is what the original test did.

The structural fix that generalises: don't test that two paths agree, *delete
one of the paths*. A shared object cannot disagree with itself.

---

## 2026-08-06 — A bashism under `#!/bin/sh` is a crash loop with no cause

`docker/entrypoint.sh` starts uvicorn and Next and uses `wait -n` so that
either process dying takes the container down — because the alternative is a
half-dead container serving prices frozen at their last value, which looks
exactly like a quiet market.

It was written with `#!/bin/sh`. On `python:3.11-slim`, `/bin/sh` is **dash**,
where `wait -n` is `Illegal option -n` and returns 2 *immediately*. So the
script started both processes correctly and then tore the container down within
milliseconds:

```
[entrypoint] backend healthy after 2s
[entrypoint] starting frontend on 0.0.0.0:3000
[entrypoint] a process exited with an error -- restarting container
```

On a platform that restarts unhealthy containers this presents as a crash loop
with nothing in the logs pointing at the cause — the app is fine, the shell is
lying. `wait -n` is a bash 4.3+ builtin, not POSIX. Bash was already in the
image at `/usr/bin/bash`; the shebang just never asked for it.

**How to apply:** if a shell script uses `wait -n`, arrays, `[[ ]]`,
`${var,,}`, or process substitution, the shebang must say `bash`. And test
container supervision by *killing a process inside it* — the same
disable-the-guard-and-watch-it-fail rule that applies to unit tests. Done here:
killing uvicorn produced `BACKEND exited -- every price is now stale`, the
container exited, and the port stopped answering. That is the behaviour the
whole mechanism exists for, and it had never actually been observed.

Also worth noting the tell: "started, then died instantly" almost never means
the thing that just started is broken. It did not have time to be.

---

## 2026-08-06 — Two bugs that only a running app could show

347 tests were green and both of these were live.

**A server component cannot fetch a relative URL.** The Board's `fetch("/api/board")`
runs on the Node side, where there is no page origin to resolve against, so it
threw and the page rendered "Backend unreachable". The `rewrites()` rule in
`next.config.ts` did not help because it only applies to requests the *browser*
makes to Next. Fix: absolute URL when `typeof window === "undefined"`, relative
otherwise.

**The demo seeder appended instead of resetting.** Restarting the server ran
`seed_all` again and added a second copy of every fixture. The Board showed
Houston twice and the counts read 18 for a nine-fixture slate. The docstring
claimed the output was deterministic; it was deterministic per *run* and
cumulative across runs, which is not the same thing and is exactly the
difference that matters for a public demo and for screenshots.

Neither is the kind of bug a unit test catches: the first needs a real server
context, the second needs the app to be *restarted*. Both were obvious within
seconds of looking at the rendered page.

**How to apply:** the build-order step is not done when the tests pass. Run the
app, look at it, then restart it and look again. Idempotence-on-restart now has
its own test (`test_reseeding_does_not_duplicate_rows`), which is the sort of
test you only think to write after seeing the failure.

---

## 2026-08-06 — "No result" and "rejected" are different outcomes

The suppression layer initially fired `edge_within_method_noise` on candidates
with a *negative* edge — Kalshi asking more than fair value. Technically true
(a negative edge does not exceed the devig method spread) and completely
useless: on any real slate most candidates have no edge, so that one code would
have dominated the suppression summary and buried every genuine diagnostic
under the majority case.

The distinction: **"there is no bet here" is the normal answer, not a
rejection.** Only a candidate that *looked* actionable and was then refused
belongs in the suppression log.

Same shape appeared twice more in the same session and is worth naming as a
pattern:

- `OddsClient.fetch_odds` returns `[]` when over budget rather than raising —
  choosing not to spend a credit is a normal operating state.
- Sizing returns `contracts=0, binding_constraint="no_edge"` without setting
  `refused`, while unreadable exposure sets `refused=True`.

**How to apply:** before adding something to a rejection log, ask what fraction
of inputs will trigger it. If the answer is "most of them", it is a *state*,
not an *exception*, and logging it as an exception destroys the log's value as
a diagnostic. Reserve the reject path for the surprising case.

---

## 2026-08-06 — A redundant special case can silently delete a whole method

The Shin devig solver returned **exactly multiplicative** for every market. Not
approximately — bit-identical. So "four devig methods" was really three, and
the conservative selection was choosing the worst of a smaller set than it
claimed.

The cause was a defensive special case:

```python
if z <= _EPS:
    return [p / total for p in probs]   # WRONG: a different formula
```

Shin's formula is well-defined at `z = 0`; it yields `p / sqrt(booksum)`, which
sums to `sqrt(booksum) > 1`. The short-circuit substituted `p / booksum`, which
sums to *exactly 1* — so `residual(0) == 0`, `brentq` found its root at zero
immediately, and every call returned the z→0 branch.

The guard was added to avoid a division-by-zero that does not exist.

**How to apply:** a special case that returns a *different formula* rather than
the limit of the same one is not a guard, it is a second implementation. Before
adding one, check whether the expression is actually singular at that point.
And test that methods which should differ *do* differ on real input —
`test_shin_is_not_merely_multiplicative_on_a_real_line` would have caught this
on day one, where "each method sums to 1" never could, because the wrong answer
summed to 1 perfectly.

---

## 2026-08-06 — The devig spread depends on line shape, and I had it wrong

The planning claim was "the spread between devig methods is 1–2 percentage
points, larger than Kalshi's entire 0.6-point fee advantage." Measured on real
lines, that is true for **lopsided** markets and false for even ones:

| Line | Method spread |
|---|---|
| Even MLB moneyline (2.10 / 1.80, 3.2% hold) | **0.18 points** |
| Lopsided (1.11 / 7.50) | **2.03 points** |

So on the near-even markets that make up most of a slate, method choice is a
rounding detail. On longshots it can manufacture an edge three times the size
of the real one.

**How to apply:** this compounds with the fee curve, which is *also* worst in
percentage terms on cheap contracts. Two independent, now-measured reasons to
distrust a longshot edge — and a reason not to relax the conservative selection
just because it looks harmless on the lines you happen to check first. Both
halves are asserted in `TestMethodSpreadDependsOnLineShape` so the framing
cannot quietly drift back.

---

## 2026-08-06 — Test that the filter's *exclusions* are decisions

The discovery classifier read `product_metadata` from real captured payloads —
the right instinct — but guessed at the values. It tested
`competition_scope == "game"` and spelled leagues as `"Womens Pro Basketball"`
and `"College Football"`.

Kalshi actually emits scopes `Game`, `Spread`, `Point Total`, `Future`,
`Awards`, and leagues `"Pro Basketball (W)"` and `"NCAA Football"`. So the
classifier silently discarded **every spread and total in the universe**, plus
WNBA and NCAAF entirely. Priceable events: 6 instead of 24. Markets: 12 instead
of 131.

**The whole test file passed.** It asserted that discovered events had a
commence time, that moneylines named two sides, that MLB was present with
moneyline coverage — all true of the survivors. Nothing asserted anything about
what had been *thrown away*, so a filter dropping 90% of its input looked
identical to one working correctly.

**How to apply:** when code filters, test the rejects, not just the keeps. The
concrete form used here is a **drift test**: enumerate every distinct label in
the captured data and assert each one is *explicitly* classified as either
in-scope or out-of-scope. An unrecognised value fails the test and logs a
warning at runtime rather than falling into a default. Silence is the failure
mode — an exclusion must be a decision, never an accident.

Corollary: fixture-based tests protect against the API *changing*, but not
against misreading it on day one. Print what a classifier actually produced and
look at it, at least once.

---

## 2026-08-06 — Measure the style rule before believing it

"Share one HTTP client" is standard advice, usually justified with hand-waving
about connection pooling. The test suite made the real number visible: the REST
tests took 12.5s and every single one cost ~0.7s, *including ones that made one
request and never retried*. That uniformity ruled out the retry logic.

Timing it directly: **`httpx.AsyncClient()` costs ~500ms to construct** — 719ms
cold, 478ms warm — almost entirely SSL-context setup (loading the CA bundle).
Key loading was 11ms and ten RSA-PSS signatures were 4ms, so crypto was noise.

The previous project opened a fresh client per call inside a discovery loop of
up to 100 sequential requests. That is **~50 seconds of pure handshake setup**
before any useful work, on a routine that also swallowed exceptions — so it
looked slow *and* returned wrong answers, and neither symptom pointed at the
cause.

**How to apply:** when a suite is slow, look at the *distribution* before
optimising. Uniform cost across dissimilar tests means fixture setup, not the
code under test. And when a performance rule is worth enforcing, put the
measured number in the docstring — `~500ms per client` argues for itself in a
way that "share the client, it's more efficient" never will.

---

## 2026-08-06 — When a document and the live API disagree, the API wins

The project handoff brief stated: *"Query params must be appended to the path
before signing where present."* The previous repo's skill file stated the
opposite. Both were confidently written; they cannot both be right.

`scripts/verify_auth.py` settled it in about four seconds against the live API,
on an otherwise identical `GET /portfolio/fills?limit=1`: signed **without** the
query → 200, signed **with** it → 401. **Kalshi signs the path only.** The brief
was wrong.

**Why it matters:** a wrong answer here does not present as "you signed the
query string". It presents as HTTP 401, which is indistinguishable from a bad
key, a wrong key id, an ED25519 key, or clock skew. That is a whole afternoon
of debugging the wrong thing.

**How to apply:** when two documents disagree about observable API behaviour,
do not reason about which source is more credible — write the ten-line script
that asks the API. Then record the answer in the code *and* in the skill file
so it is never re-litigated. Carry forward the same treatment for any remaining
"the docs say X but the other docs say Y" item.

---

## 2026-08-06 — Kalshi may be the sharp side, not the soft one

The public +EV methodology (OddsJam, Unabated) takes sharp-book consensus as
fair and flags the *soft* book offering a better number. Applied to Kalshi that
can invert: Kalshi's vig is lower than any sportsbook's and its prices are
increasingly part of the consensus being measured against.

So when Kalshi looks 3c cheap against devigged Pinnacle, the likelier
explanation is that Pinnacle is stale — not that Kalshi is wrong.

Compounding it: the spread between devig *methods* (multiplicative / additive /
power / Shin) is 1–2 percentage points, which is **larger than the entire fee
advantage** the venue offers. Method choice alone can manufacture the edge.

**How to apply:** three structural rules, not judgement calls. Use the worst of
four devig methods for any money decision. Treat a large apparent edge as a bug
until proven otherwise — suppress and investigate rather than surface. Validate
against Kalshi's own closing line, because the question is whether you beat
*Kalshi*, and only Kalshi's close answers that.

---

## 2026-08-06 — CLV needs hundreds of bets, not dozens

Corrected during planning. An earlier claim in this project's own planning
conversation put closing-line-value significance at ~50 bets. That was wrong by
roughly an order of magnitude.

Practitioner consensus: **200–300 bets minimum** before CLV says anything,
500–1,000 before it is a meaningful predictor, 2,000+ for real statistical
confidence. Beating the close on ~60% of bets over 200+ is the benchmark for a
genuine edge.

**How to apply:** the live gate uses 300 scored recommendations as its floor,
not 50. Scoring every recommendation on CLV whether or not it was bet is what
makes reaching that number possible in reasonable time — the paper log
accumulates evidence from day one without money at risk.

---

## 2026-08-06 — A sign convention agreed with its own test, and both were wrong

`margins.probability_cover` compared `margin > line`. The correct condition for
a spread bet is `margin > -line`: a −7.5 favourite covers by winning by 8+, not
by losing by fewer than 7.5. So **every spread and teaser price was inverted.**

The test asserted `cover(-7.5) > cover(+7.5)` — "cover probability falls as the
line rises" — which is only true under the inverted convention. Code and test
agreed with each other and disagreed with football, so the suite was green.

How wrong: under the old code an eight-point favourite covered its own −7.5 line
**86.7%** of the time. That number is 50% by definition, and nothing flagged it.

**Why:** a sign error produces numbers in the right range with the right
monotonicity. Nothing about the output announces it. The test was written from
the same mental model as the code, in the same sitting, so it inherited the
error rather than catching it.

**How to apply:** for any convention with two plausible directions, write at
least one test whose expected value is fixed by *definition* rather than by
reasoning — a case where only one answer is arithmetically possible. Here that
is `cover(line, predicted_margin=-line) == 0.5`: a team predicted to win by
exactly its own line is a coin flip against it. That test discriminates
absolutely (0.5000 correct vs 0.8667 buggy); the monotonicity test did not.
Related: [[test-the-filters-exclusions]].

---

## 2026-08-06 — Synthetic data that is right on the mean and wrong on the variance

The Builder demo printed a Wong teaser at **+28.4% EV** — roughly five times any
plausible real edge, and precisely the kind of number this project exists to
suppress. The cause was not in the pricing code. It was the test-and-demo
generator: it drew margin magnitudes from a key-number-heavy pool and chose
signs to steer the running mean onto the spread. The mean landed correctly and
the key-number spikes were present, so it looked right — but hitting a +8 mean
from a pool averaging 8.6 requires the favourite to win **96.9%** of games.
Realistic is ~76%. The variance was fiction, so every cover probability was
inflated, and the fabricated edge appeared in the pricing output as if measured.

**Why:** scaffolding gets held to a lower standard than production code because
it "isn't real". But a generator feeds the numbers a demo and a test suite both
reason about, so a wrong generator manufactures edges everywhere downstream —
and it does so with production code that is entirely correct, which is the worst
place to look for the bug.

**How to apply:** synthetic data lives in `backend/model/synthetic.py`, is
documented as not-evidence, and is **guarded by its own tests** on the moments
that matter — mean, standard deviation, and the one derived rate that catches a
wrong variance (an eight-point favourite must win 68–80% of the time). Match a
distribution's spread, not just its centre. When a demo prints a number that
would be suppressed in production, suspect the fixture before the formula.

---

## 2026-08-06 — An empirical distribution cannot be slid sideways

Fitting margins league-wide and translating them onto a specific game destroys
the only reason to fit empirically. Key numbers sit at *absolute* margins of 3,
7, 10 and 14; dragging a pooled distribution eight points to reach an
eight-point favourite relocates its 3-spike to 11 and its 7-spike to 15. The
result is worse than the normal approximation it replaced — and worse in the
dangerous direction, because it still looks like data.

**Why:** the failure is invisible in the output. A translated empirical fit
returns a plausible probability, reports `is_empirical == True`, and shows real
key-number mass in `key_number_mass()`. Nothing distinguishes it from a fit that
is actually centred where it is being used.

**How to apply:** fit per closing-spread bucket (`margins.fit_by_spread`), so the
only translation left is the model's disagreement with the market — a point or
two. `MarginDistribution.translation_points()` reports the drag and
`core.teaser.build_leg` refuses above `MAX_TRANSLATION_POINTS` (2.0). Both
refusals in the teaser path — non-empirical, and over-dragged — exist because a
teaser is only priceable when the key numbers are where the data actually put
them. Related: [[refuse-rather-than-guess]].

---

## 2026-08-07 — A window resize is not a viewport change

Three ways to check a mobile layout, two of which quietly lie:

- **Resizing the browser window** (Chrome extension `resize_window`): resized the
  outer window to 414px while `window.innerWidth` stayed **1707**. The `sm:`
  media queries never switched, so every screenshot came back desktop-width and
  the layout looked fine.
- **`chrome --headless --screenshot --window-size=390,1400`**: renders at the
  default viewport and **crops** to 390. The image is the right size and the
  content is wrong — body copy cut mid-sentence, which reads as a layout bug
  that isn't there and hides the one that is.
- **CDP `Emulation.setDeviceMetricsOverride`**: actually sets the layout
  viewport. This is the only one of the three that reflows.

The two bad methods disagreed with the good one *in opposite directions* — one
said the layout was fine when it was broken, the other said it was broken after
it was fixed. Between them I nearly shipped a broken nav and then nearly
"fixed" a working page.

**Why:** a screenshot is evidence about pixels, not about layout. Neither bad
method tells you which element overflows, so both invite guessing at causes.
The actual bug — adding two nav links pushed the row 39px past a 390px viewport,
widening the *document* so every page lost its right edge while the nav itself
still looked fine — took one measurement to find and would have taken several
guesses to stumble on.

**How to apply:** `scripts/check_mobile.py` sets the viewport over CDP, reports
`scrollWidth` against it, names every overflowing element, and exits non-zero.
Screenshots are captured **through the same CDP session** that set the viewport,
so the image and the measurement cannot disagree. Run it at 320/390/430 before
believing a layout works on a phone. Related:
[[measure-the-style-rule-before-believing-it]].

**Layout corollary:** a horizontal nav is a document-width hazard. The link row
now carries `min-w-0 overflow-x-auto` with `shrink-0` items, so a sixth link
degrades to a scroll instead of clipping every page behind it.

---

## 2026-08-07 — A true measurement licensed a false conclusion

**The user had to point this out. Kalshi has a combo product — it is in the app —
and this project spent eleven build steps asserting it does not.**

The chain: the predecessor project measured that paginating `/markets` returns
~99.8% `KXMVE` tickers with no volume. True, and still true. From it this
project concluded "`KXMVE` is junk", then "Kalshi has no parlay product", and
built `core/parlay.py` on that premise — inverting the whole module to price
*sportsbook* parlays instead.

`KXMVE` is **M**ulti-**V**ariate **E**vent. It is the combo builder. Measured
2026-08-06: **1,389 collections, 13,806 legs**, including same-game parlays
(`KXMVENBASINGLEGAME`, 8,622 legs across game/spread/total/points/assists/
rebounds/threes/steals/blocks) and cross-game and cross-category ones. What is
junk is the *pre-generated combination markets* clogging an endpoint nobody
should paginate — not the product behind them.

**Why:** the measurement was about *discovery hygiene* ("don't paginate
`/markets`") and got promoted to a claim about *product existence* ("there are
no combos"). Nothing in the data licensed the second claim, and nothing in the
codebase recorded which of the two it was relying on — so the filter and the
premise became indistinguishable. Every downstream test passed, because they all
tested the filter.

Two smaller mistakes rode along, both of the same family:

- I read `multivariate_event_collections` (the *path* name) from the response
  and got an empty list with no error. The wire key is `multivariate_contracts`.
  A plausible-but-wrong key returning `[]` is indistinguishable from "there are
  none" — the same failure that made the predecessor parse every order book to
  zero levels while 305 tests passed.
- Zero of the 13,806 legs had an active quoter, which I nearly reported as
  "the product is illiquid". It was measured on 6 August: NBA finished, NFL in
  preseason. It measures the calendar.

**How to apply:** when a measurement rules something out, write down *what was
actually measured* next to the conclusion, and check the conclusion is not
broader than the measurement. "`/markets` is 99.8% low-volume combination
tickers" does not imply "combos do not exist" any more than a full spam folder
implies nobody sends email. Before building a module on the *absence* of a
venue feature, spend one API call looking for it. Related:
[[when-a-document-and-the-live-api-disagree]],
[[unreadable-must-never-resolve-to-zero]].

**The payoff, which makes this more than a correction:** a same-game combo quote
*is* a joint probability, so given the leg marginals it inverts to an implied
correlation (`core.correlation.implied_correlation`). That is exactly the
measured input `correlation.py` refuses to guess — the module's own refusal now
has a data source. A quote of 0.36 on legs of 0.60 and 0.50 implies rho = +0.39,
against the 0.30 that naive multiplication assumes.

---

## 2026-08-07 — The WebSocket path was dead and 611 tests said otherwise

A real capture (`scripts/capture_ws_fixture.py`, 269 frames off the live feed)
replayed through `orderbook.py`: **0 of 257 book frames parsed. All 12 books
empty.** The live-data backbone of the whole tool had never worked.

Three independent wrong assumptions, none of which could be seen from the code:

1. Prices arrive as **dollar strings** (`"0.4300"`). The parser did
   `int(price) * 10`, which throws on every real frame.
2. Delta fields are `price_dollars` / `delta_fp`, not `price` / `delta`.
3. **`seq` is a per-connection counter, not per-market.** Twelve tickers shared
   one `sid` and one strictly-increasing sequence, so per-book gap detection
   fired on nearly every delta and would have resubscribed in a permanent loop.

Plus a calibration error the capture also settled: `MAX_PLAUSIBLE_QUANTITY` was
1,000,000 and a real WNBA book carried **1,174,194** contracts resting at 1c.
The bound had been invented rather than measured.

**Why the tests did not catch it:** every one of them fed the parser
hand-constructed data *in the shape the parser expected*. The file even carried
a `TestWireFormatIsUnverified` class that skipped, honestly documenting the
debt — and the seventeen tests above it still read as coverage. An honest
`skip` next to sixteen confident assertions does not stop the sixteen from
being believed.

**How to apply:** this is the predecessor's `data["yes"]` vs `yes_dollars_fp`
bug, reproduced in full by a project that had written the rule against it. The
rule was "wire-format tests load captured payloads, never hand-constructed
ones." It was followed for REST (`tests/fixtures/` had real event captures) and
skipped for WebSocket, and the WebSocket path is the one that carries every
live price. **Capture the payload before writing the parser, not after the
parser has tests.** One 60-second capture turned a passing suite into an
obviously dead code path.

Corollary on sequence numbers: before building recovery logic on a sequence
field, verify what it counts. `seq` at the frame level looked per-market and was
per-connection; a single multi-ticker capture settles it, and no amount of
reasoning about the code would have.

---

## 2026-08-07 — Four audits, one failure shape

Four review agents audited the money path, the measurement discipline, the API
layer and the test suite. The full triage is `tasks/audit-2026-08-07.md`. Three
of the four independently found the same shape, which is the one this file
already had two entries about:

> A guard, its implementation and its test written in one sitting from one
> mental model. The test inherits the error rather than catching it.

Instances found in a single session: NO-side CLV wrong by up to a dollar with
its test asserting the same error; the orderbook wire format; per-book sequence
detection; `calculate_fee` returning `0.0` on an untradeable price (fabricating
a +55c edge); `backtest.beats_close` sitting beside a verdict that contradicts
it; and two dbt tests that reduce to `(A ∧ B) ∧ ¬A` — identically false, so they
can never fail.

The NO-side CLV bug is the clearest specimen. `entry_ask_tenths` is the price
paid *for the side taken*, so a NO position is worth `1000 − close`. The code
returned `entry − close`, wrong by `1000 − 2·entry` — **zero only at exactly
50c**, negative for NO bets below it and positive above. Its sensitivity to the
closing price was correct, so the output looked entirely reasonable. The test
asserted `clv_tenths(480, 520, "no") == -40`, matching the bug. And the
"definitional" test that existed, `clv_tenths(500, 500, "no") == 0`, passes
under *both* conventions — because 50c is exactly where the error vanishes.

**How to apply:** a definitional anchor only helps if it is chosen where the
candidate errors actually differ. Pick the anchor by asking "what would the
wrong implementation give here?" — if the answer is "the same thing", the
anchor is decorative. The one that works: `clv_tenths(650, 650, "yes") == 0`
together with `clv_tenths(350, 650, "no") == 0`; the old form scores +30 on the
second. Related: [[a-sign-convention-agreed-with-its-own-test]].

> **RECURRED 2026-08-10, on the fee formula — verbatim, in the module whose
> rounding rule the break-even bar depends on.** `tests/test_fees.py:136`
> anchored Model A at `_model_a(50c, 100) == 1.75`. Raw is
> `0.07 × 100 × 0.25 = 1.75`, **exactly on a cent boundary**, so ceil, floor,
> half-up and half-even all return 1.75. The anchor written to pin the formula
> could not see the rounding rule at all — and the rounding rule is the *entire*
> 0.25-point gap between the 51.75% bar this repo used to claim and the 52.00%
> it actually applies (at 50c, N=1: raw $0.0175 → ceil → $0.02).
>
> **Measured blindness:** mutating ceil → half-up left **all 28 pre-existing
> tests in `test_fees.py` green.** The full suite did go red — 13 failures — but
> every one was in `test_ev_sizing.py`, `test_joint_bound.py` and
> `test_the_bankroll_cannot_disable_the_record.py`. **Nothing said "the rounding
> rule changed."** A downstream test that fails for an upstream reason is a
> smoke alarm in the wrong room: it proves the suite is not *globally* blind
> while leaving the diagnosis to whoever reads the wreckage.
>
> The replacement anchors are chosen by the rule this lesson already states —
> *what would the wrong implementation give here?* The load-bearing one is
> `(P=0.968, n=20)`: raw $0.0433664, where ceil gives **$0.05** and half-up,
> half-even and floor all give **$0.04**. The test computes all four inline and
> asserts they differ, so the discrimination itself is guarded. Second anchor
> `(P=0.990, n=1)`: raw $0.000693, where nearest-cent would charge **zero** —
> proving the rounding rule is load-bearing at the cheap end and not a tie-break.
> Both are real observed prices, and the value each predicts is the value Kalshi
> actually charged.
>
> **The generalisation, which is the reason this is appended rather than filed
> as a new lesson:** the failure did not recur because the lesson was unknown.
> It recurred because *choosing an anchor at a round number is the path of least
> resistance*, and 50c × 100 is the most natural example anyone would reach for
> in a fee module. **A lesson that requires the writer to remember it at the
> moment of writing has no ratchet.** Pair every definitional anchor with a test
> that the candidate implementations *disagree* there — that is a property a
> machine checks, and it is the only form of this lesson that cannot be
> forgotten. Related: [[an-allowlist-cannot-report-what-is-missing-from-it]],
> which is the same defect one level up: a guard that only ever checks what
> someone already thought of.

---

## 2026-08-07 — One observation recorded thirty times is one observation

The live-money gate required 300 scored recommendations and a mean CLV clearing
two standard errors. Both counted **rows**. The engine writes a fresh row on
every pass, and every row for one market scores against **one** closing line, so
ten markets polled thirty times satisfied a floor written to mean 300
independent bets — and shrank the standard error by `sqrt(30)` for evidence that
never grew.

The tests asserted the defect. `test_a_consistent_edge_clears_the_guard`
inserted 400 rows on a single ticker and asserted the gate opened. It does not
any more: 400 rows on one game is one observation, and one observation has no
between-game spread to estimate at all.

The fix is the sandwich estimator for a mean, clustering by **game** rather than
by market — a game's moneyline, spread and total resolve from one final score,
so clustering on ticker would repeat the same mistake one level up:

```
Var(ybar) = G/(G-1) * sum_c ( sum_{i in c} (y_i - ybar) )^2 / N^2
```

**Why it is dangerous rather than merely wrong:** an understated standard error
produces a *more confident* version of the same number. Mean CLV was correct
throughout. Only the error bar was fiction, and the error bar is the entire
content of the claim "this is not noise".

**How to apply:** before dividing by `sqrt(n)`, ask what `n` counts and whether
two rows can ever be the same underlying event. Anywhere a poller writes rows on
a timer, the row count is a measure of *uptime*, not of evidence. Both numbers
are now reported side by side — the Ledger shows games over the floor with the
row count beside it, because "412 of 300" on one screen and "9 of 300" on
another is the failure in [[computing-the-right-statistic-and-then-ignoring-it]],
and the flattering one gets believed.

The two anchoring tests are chosen so that a wrong implementation gives a
*different* answer, per [[four-audits-one-failure-shape]]:

- **Singleton clusters must reproduce the classical standard error exactly.**
  With `G == N` the estimator collapses algebraically to `s^2/N`, so genuinely
  independent data is not penalised. This one catches a dropped `G/(G-1)`.
- **Duplicating every observation `k` times must change nothing** — same mean,
  same standard error, bit-identical. The replaced estimator returns
  `stderr/sqrt(k)` on that input, so the test states the old bug as an
  invariant instead of just checking the new number looks plausible.

---

## 2026-08-07 — An idle threadpool hides every thread-safety bug you have

The deployed demo rendered *"Backend unreachable"* on **9 of 15** requests while
`/api/health` stayed 100% green. The split is the clue: health reaches the
backend through Next's rewrite proxy, while the pages use a server-component
fetch to the read routes. Those were throwing:

```
sqlite3.ProgrammingError: SQLite objects created in a thread can only be
used in that same thread
```

FastAPI runs a sync dependency and a sync path operation on **two different
threadpool workers**, so the connection opened in `get_conn` is used from
another thread.

**Why 758 tests and a local container run missed it.** An idle threadpool tends
to hand out the same worker twice. Nothing local ever crossed threads, so the
guard never fired. It took a deployed instance with a 30-second health check
running *alongside* traffic to spread the work far enough to show — one machine,
zero restarts, no platform fault. Concurrency is not something a test suite gets
for free; it has to be arranged, and the arrangement has to be verified.

**The knowledge was already in the file.** `routes.py` opens a separate
connection for the order endpoint and says why: *"a connection opened by a sync
dependency in the threadpool cannot be used by this async route."* Correct, and
incomplete — the same hop happens between two *sync* frames, worker to worker.
A comment that explains one instance of a hazard is evidence the hazard is
understood, not evidence it has been handled everywhere.

**How to apply:** fix it narrowly. `connect()` takes `cross_thread`, defaults
**off**, and only the per-request read-only API dependency opts in. Disabling the
guard globally would convert a loud error into a silent race on the writer
paths, and the guard is genuine protection for a connection two requests share.
Related: [[clamping-is-for-values-you-trust]].

**And the test that did not work.** The obvious regression test — hammer
`TestClient` from a thread pool, expect 200s — **passes with the fix removed**.
`TestClient` drives the app through a single anyio portal and never makes the
worker-to-worker hop. It was written, run against the reverted fix, seen to pass,
and deleted rather than shipped. The replacement asserts the property directly:
the connection the API opens must be flagged usable off-thread. That one fails
the moment the flag is dropped.

The general rule, again: [[a-test-that-passes-on-the-bug-is-not-a-test]]. Run
every new regression test against the unfixed code *before* believing it, and
especially when the test involves concurrency — that is where a green result is
most likely to mean "did not reproduce" rather than "fixed".

---

## 2026-08-07 — The zero that means "no measurement" passes every threshold

`consensus_devig` reported `market_width = 0.0` when only one book contributed.
Suppression then checked `market_width <= 0.06`, which `0.0` clears trivially —
so the **least**-evidenced consensus the system can build passed the check
designed to catch untrustworthy consensus most easily of all.

This is [[unreadable-must-never-resolve-to-zero]], and the repo had that rule
written down. It was applied at every *ingest* boundary and missed on a
*derived* value, where the same logic holds: one book cannot disagree with
itself, so there is no width to report, and `0.0` is a claim rather than an
absence.

What makes it worse than a plain missing value: `0.0` is also a **legitimate
measurement**. Two books quoting identically genuinely have zero disagreement
and should pass. So the two states shared one representation and no caller could
separate them. The fix is `Optional[float]` with `None` for unmeasurable, and
the test that matters is the *pair* — `None` must refuse and `0.0` must pass. If
those two ever agree again, the states have been collapsed back together.

**How it stayed hidden:** `min_book_count = 2` meant a one-book consensus was
also caught by `too_few_books`, so the width bug never changed an outcome on its
own. Defence in depth masking a defect is not defence in depth — it is one
working guard and one that would silently become load-bearing the day the other
threshold moved.

**The related finding, which is larger.** Sharp-book anchoring *causes* the
single-book case. Three books quoting and agreeing to within 3.1 points, with
one of them sharp, produces `book_count = 1` and no measurable width: the
anchoring discards the agreement evidence, and that agreement was the strongest
available signal that the line was trustworthy. `book_count` alone cannot
distinguish "only one book quotes this market" from "five did and we kept one",
so `usable_book_count` is now reported alongside it.

**How to apply:** the never-resolve-to-zero rule applies to *computed* values,
not only parsed ones. When a statistic is undefined for a given input, say so;
and check whether the sentinel you were about to use is also a valid answer.
Related: [[two-limits-on-one-quantity]] — same shape, in that a guard which
cannot fire is indistinguishable from one that is working.

---

## 2026-08-07 — Code with no caller is not a feature, it is a plan

`analysis/clv.py` has had `score_recommendations` since the evidence layer was
built. It has ~40 tests. **Nothing ever called it.** It scores rows that already
have a `closing_lines` entry, and nothing ever wrote one — so no recommendation
could be scored, ever, and the gate's 300-observation counter was structurally
pinned at zero however long the system ran.

The same was true one level up: `persist_recommendation` was called only by
`seed_demo.py` and tests, `odds_snapshots` had a writer and no reader,
`fair_prices` had neither. Eleven build steps produced a complete set of correct
parts and no chain.

**Why it survived so long:** every module was individually excellent and
individually tested, `tasks/todo.md` recorded each step as done — and it *was*
done, as a component. Test count went up. Coverage looked real. The missing
thing was not in any file; it was the absence of a call, and absence has no
line number to review.

**How to apply:** for anything on the critical path, the completion criterion is
**"what calls this, and what happens if the process runs for a week?"** — not
"is it correct and tested". A cheap detector: grep for each public entry point
and check the callers are not all tests and seeders.

```
grep -rn "score_recommendations\|persist_recommendation" --include=*.py .
```

If every hit is `tests/` or a demo seeder, the feature does not exist yet. Same
shape as [[a-captured-fixture-that-no-test-loads]] — the artefact is present and
the thing it was for has not happened. Related:
[[two-limits-on-one-quantity]], which was only discoverable *because* the chain
finally ran.

---

## 2026-08-07 — A live credential can leak with nobody logging it

Running the chain against the live API put a working Odds API key into a
terminal transcript. Nothing in this project logged it. `httpx` logs the full
request URL at INFO, and The Odds API takes its key as a **query parameter**, so
making a request was sufficient:

```
INFO httpx: HTTP Request: GET https://api.the-odds-api.com/v4/sports/
baseball_mlb/odds?apiKey=<live key>&regions=us%2Ceu ... "HTTP/1.1 200 OK"
```

The key was rotated. It would have leaked identically into Fly's log stream on
every deploy, for as long as the runner ran.

**Why the usual defence misses it:** secret hygiene here was genuinely good —
`.env` gitignored from commit one, the private key never on disk in the image,
`.dockerignore` verified. All of that protects secrets *at rest*. None of it
touches a third-party library's default log format, and the leak came from a
line no author of this repo wrote.

**How to apply:** redact at the **root logger**, not the call site, because
there was no call site. `backend/logging_setup.py` filters credential-shaped
substrings out of every record in the process, including from loggers added
later by libraries nobody has considered yet. Two details that matter:

- Filter `record.args`, not just `record.msg`. `logger.info("GET %s", url)`
  keeps the URL in `args` until formatting, and that is exactly the form
  `httpx` uses — a filter that only rewrote the message would let it straight
  through.
- Attach the filter to the **handlers**, not only the root logger. A filter on
  a logger runs only for records logged directly on it, so a root-logger filter
  never sees a child logger's records. Handlers are where every record
  converges.

Corollary: prefer providers that take credentials in a header. A key in a query
string is one careless log line away from a transcript, forever.

---

## 2026-08-07 — Two limits on one quantity, and the tighter one wins in silence

Kalshi's `occurrence_datetime` runs **exactly 3 hours late**. Measured against
The Odds API on a live slate: 14 of 18 same-day MLB pairs and 6 of 6 WNBA pairs
at +180 minutes, and every link the fixed runner made carried a skew of −179 or
−180 min.

The two-sport agreement is what identifies it. WNBA games run about two hours
and MLB about three, so if the field were the expected *outcome* time the
offsets would differ by an hour. They are identical, so it is a fixed shift —
the US Eastern-to-Pacific gap, which does not move across DST because both
zones shift together.

That single fact then hit **two independent limits**, and the second one only
became visible after fixing the first:

| Limit | Module | Was | Effect |
|---|---|---|---|
| `DEFAULT_COMMENCE_TOLERANCE_MS` | `match.linker` | 2h | 0 of 175 events linked |
| `max_commence_skew_ms` | `core.suppression` | 2h | 19 linked, **all 76** candidates rejected |

Nothing connected them. The stage counts showed work happening at every step and
nothing surviving — which reads like "no opportunities today", the same as a
correct run on a quiet slate.

**How to apply:** when the same quantity is bounded in two places, the tighter
bound silently overrides the looser one and the looser one becomes decorative.
Assert the relationship in a test rather than trusting two comments to stay in
agreement — `TestTheTwoCommenceLimitsAgree` fails if suppression is ever set
tighter than the linker. And note the general shape: **a threshold set below a
systematic offset is not a risk control, it is an off switch.**

Two further notes worth keeping:

- **The tight window was not even the thing keeping doubleheaders safe.** The
  old test asserted `tolerance <= 3h` as a *proxy* for "cannot merge a
  doubleheader". The real guarantee is `link_event` refusing when two fixtures
  match the same team pair. With a +3h shift, game one's Kalshi time lands on
  game two's true start, so the tight window was what would have picked the
  wrong game. When a test guards a property through a proxy, assert the
  property. Related: [[a-sign-convention-agreed-with-its-own-test]].
- **The offset is not corrected away.** Subtracting 3h in discovery would become
  a silent lie the day Kalshi fixes it. The skew is recorded on every link
  instead, so it stays visible as data and a change in it is detectable.

**Recurred 2026-08-07, on the quantity the whole tool is built around.** The
actionable window is bounded twice: `MAX_ODDS_AGE_S = 900` and
`MAX_KALSHI_QUOTE_AGE_S = 30`. The recorder polls every 900s. So a row is
bettable for **thirty seconds after each pass**, not fifteen minutes — the tool
is actionable for about a minute a day, not half an hour, and every document in
the repo (this file included) said fifteen minutes.

Neither number is wrong on its own. 30s is right for a venue quoting under
200ms; 900s is right for a sportsbook consensus; 900s is right for a free tier
of 500 credits a month. Three defensible numbers, and the product of them is a
tool nobody can use. Nothing computed that product, because no module holds more
than one of the three.

**The generalisation worth carrying:** when a system has several independent
freshness or rate limits, write down the *composition* — the actual window a
user gets — as a number, somewhere a test can read it. Each limit will look
reasonable to whoever reviews it, and the composed value is the one that decides
whether the thing works at all. It is the same failure as a threshold set below
a systematic offset, one level up: not one limit that is an off switch, but
several that multiply into one.

**Recurred 2026-08-10, in the guard built to detect exactly this.** The remedy
above is "assert the relationship in a test rather than trusting two comments to
stay in agreement". `inconsistent_consensus_metadata`
(`backend/core/suppression.py:338`) is that assertion for the book-count pair —
and it compares `book_count` against `_CONSENSUS_NEEDS_TWO_BOOKS`, the
**producer's own literal `2`** (defined at `backend/core/suppression.py:35`,
used at `:335`, and itself only a mirror of the hardcoded `1` at
`backend/core/devig.py:312`), rather than against `config.min_book_count`, which is
what the consumer half actually reads. So it verifies that the producer agrees
with itself. Set `min_book_count = 3` and the two halves diverge exactly as
before, and this check stays green through it.

**The code says so, and it is still worth writing down.** The comment above it
(`backend/core/suppression.py:320-333`) names the divergence, names this very
lesson by its shape (*"Two limits on one quantity, currently equal by
coincidence"*), and states the intent: *"assert the producer's invariant
instead"*. That is a defensible choice — the producer's invariant is real and
was previously true only by accident. What is not defensible is the **name**.
`inconsistent_consensus_metadata` reads as the cross-check, sits in the same
list as the guards that are cross-checks, and is counted alongside them; a reader
auditing whether the pair is protected finds it and stops. This is
[[count-guard-families-not-guards]] on the naming rather than the condition.

**How to apply:** **a consistency check must read both sides from where each
side actually reads them.** If one operand is a module-level constant belonging
to the producer, the check is a self-check no matter what it is called, and it
is structurally blind to the divergence it appears to cover — a self-check
cannot fail on disagreement between two parties when only one party is present,
which is [[a-shared-object-cannot-disagree-with-itself]] read as a warning
rather than as a fix. Two consequences: name self-checks so they cannot be
mistaken for cross-checks (`producer_metadata_self_consistent`, not
`inconsistent_*`), and verify by the disable test that CLAUDE.md already
mandates — change the *consumer's* value and watch the check go red. If it stays
green, it is not guarding the pair.

---

## 2026-08-07 — A captured fixture that no test loads is decoration

`tests/fixtures/odds_mlb_h2h_spreads_totals.json` had been sitting in the repo
for a day: a verbatim capture, 15 events, 30 books, 392KB. `tasks/NEXT.md`
listed *"Capture an Odds API fixture"* as still to do, which was wrong. What was
actually still to do was **load it** — `grep -rn odds_mlb_h2h_spreads_totals`
across the codebase returned nothing. Every odds test still ran against a
hand-written payload.

So the project had spent the credit, produced the artefact, recorded it as
outstanding anyway, and kept the exact gap the capture was meant to close. The
directory listing looks identical either way.

Wiring it in immediately produced a real finding the hand-written payload could
not contain: **the API returns market keys nobody requested.** The request is
`markets=h2h,spreads,totals`; the response carries `h2h_lay` wherever a betting
exchange is in the region. `_parse` stored any key it was handed.

**How to apply:** "capture a fixture" is not done when the file exists. The
completion criterion is a test that fails when the fixture is removed. Same
shape as [[a-test-that-passes-on-the-bug-is-not-a-test]] — the artefact is not
the point, the failure it can cause is. Worth grepping for every file in
`tests/fixtures/` occasionally and checking something reads it.

Corollary on capture-based tests: assert something about the *capture itself*
(`len(events) >= 10`, `oddsFormat == "decimal"`, "some book quotes both sides"),
so a truncated or re-scoped re-capture fails loudly instead of quietly making
every test below it vacuous.

---

## 2026-08-07 — The null for one proportion is not the null for a difference

`backtest` compared the model's accuracy against the market's on the games where
they disagreed, and tested the gap against

```python
stderr = 100 * math.sqrt(0.25 / n_disagreements)
```

That is the standard error of **one** proportion under the null. The gap is a
*difference* of two accuracies measured on the **same games**, which makes it a
paired comparison. Games where both were right, or both were wrong, carry no
information about which is better — only the discordant ones do. McNemar's test
uses exactly those:

```
gap = (b - c) / n        stderr = sqrt(b + c) / n
```

with `b` = model right and market wrong, `c` = the reverse.

The two forms **coincide at exactly 25% discordance**, which is what makes this
hard to spot: on a well-behaved sample the old number looks right. Above 25% the
old form is too narrow — at 60% discordance it is 1.55x too small — and too
narrow is the direction that manufactures significance. Near-pick'em games,
which are most of a slate, push discordance well past 25%.

**Why it hides:** the wrong standard error is the right *order of magnitude* and
moves correctly with `n`. Nothing about the output announces that the wrong
null was used. It is the [[a-sign-convention-agreed-with-its-own-test]] failure
applied to a variance instead of a sign.

**How to apply:** before writing a standard error, say out loud what the
estimator is — "a proportion", "a difference of paired proportions", "a mean of
clustered observations" — because each has a different null and they are not
interchangeable. `sqrt(p(1-p)/n)` is the default that comes to mind and it is
only correct for the first. The crossover point is the test worth writing: at
25% discordance the two formulas must agree exactly, which pins the new
implementation against the old one at the single input where both are right.

Related: [[one-observation-recorded-thirty-times]] is the same question asked
about `n` rather than about the formula.

---

## 2026-08-07 — A guard that routes around thin data into a fallback built from it

`MarginDistribution.fit` computed the standard deviation from whatever it was
given:

```python
variance = sum((v - self.mean) ** 2 for v in values) / max(1, self.n - 1)
self.sd = math.sqrt(variance)
```

With `n = 1` that denominator is `max(1, 0) == 1`, the numerator is 0, and
`sd = 0`. `is_empirical` is then False, so `probability_cover` correctly routes
away from the counts path — into a normal approximation using the `sd` it just
computed from the same single observation. `_normal_survival` saw `sigma <= 0`
and returned exactly `1.0` or `0.0`.

**A cover probability of 1.0 is not a bad estimate; it is a different kind of
object.** Quarter-Kelly on a certainty stakes the entire bankroll, off one game.
And `fit_by_spread` calls `fit` on every closing-spread bucket, including the
one- and two-game ones, so this was reachable from ordinary use.

The shape is worth naming, because the guard *looked* right: `is_empirical`
existed, it fired, and it did exactly what it said. What it did not do was
notice that the fallback it selected had already been contaminated by the data
it was falling back from.

**How to apply:** when a guard diverts thin data to a fallback, check what the
fallback is built out of. Two thresholds here rather than one, because they
answer different questions — `MIN_GAMES_FOR_EMPIRICAL = 200` asks "can this
sample show me the *shape*?", `MIN_GAMES_FOR_SD = 30` asks "can it tell me the
*width*?". Collapsing questions of different difficulty into one threshold is
what let a one-game sample set a width at all.

Two supporting rules, both already in this file and both violated here:

- **Refuse what you are validating.** `_normal_survival` returning `1.0` on a
  zero width reads as defensive and is the opposite — it converts a broken fit
  into a confident answer. It now raises. See [[clamping-is-for-values-you-trust]].
- **A sourced number must be distinguishable from a measured one.** `sd` now
  carries `sd_is_measured` for the same reason the module already flagged
  `default_distribution` as non-empirical.

Note also that sample size alone was never the guard: 300 identical margins
clears `n >= 30` and still estimates zero spread. The check is on the estimate,
not only on the count.

---

## 2026-08-07 — A threshold that is valid once is not valid every time you look

The gate's noise guard required mean CLV above two standard errors. That is a
correct statement about **one** pre-registered look at the data. `evaluate_gate`
runs on every HTTP request against a database that grows all day, so it is not
one look — it is thousands, and under a true zero-edge process the running
z-score wanders across the boundary eventually with probability 1.

Measured on 1,200 pure-noise sequences, looking after each new game from n=20 to
n=120: **the two-standard-error rule fires on 13.7%** of them. That 13.7% is a
floor, not an estimate — the simulation stops at 100 looks and the live gate
does not stop.

This is [[every-per-cell-guard-can-pass]] rotated onto the time axis. The same
project that built `mart_multiple_comparisons` to count tests *across buckets*
was not counting them *across looks*, on the one code path that arms real money.

The fix is a confidence sequence — a boundary holding simultaneously for all
`n`, so looking whenever you like costs nothing. Robbins' normal mixture, tied
to the pre-registered floor. It fires on 0% of the same sequences.

**The cost is real and should be stated, not buried:** the multiplier at the
floor is 3.66 standard errors rather than 2, so continuous peeking costs about
1.8x the effect size.

**How to apply:** whenever a threshold is evaluated more than once against
accumulating data, the question is not "is this test correct?" but "how many
times will it be asked?". Two properties are worth asserting directly, because
both are easy to get wrong in a way that looks fine:

- The boundary must never approach the fixed-sample value at any `n`. A bound
  that decays back to 2 for large samples is always-valid in name and
  fixed-sample in the regime that matters.
- The mixture parameter does **not** minimise the multiplier at `n == m`. It
  bottoms out near `n ≈ 8m` and then climbs like `sqrt(log n)`. I asserted the
  intuitive version, and the test caught me — which is the argument for
  computing a curve and reading it rather than reasoning about the formula.

---

## 2026-08-07 — `INSERT OR IGNORE` will happily ignore your fixture

The gate tests' helper did this, and had since the file was written:

```sql
INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, series_ticker)
VALUES ('T', 'E', 'S')
```

`kalshi_markets.first_seen_ms` is `NOT NULL`. So the insert violated a
constraint, `OR IGNORE` suppressed it, and **the market row was never created**.
Every `LEFT JOIN kalshi_markets` in a gate test matched nothing for the life of
the project. The tests read as though they covered the join; they covered the
fallback branch for a market that does not exist.

It surfaced only because clustering by `event_ticker` gave the wrong cluster
count in a new test. Nothing else would ever have shown it — the join is a
`LEFT JOIN`, so a missing row degrades quietly by design.

**Why:** `OR IGNORE` is written to mean "this row may already exist". It
actually means "ignore *every* constraint failure on this statement", including
the `NOT NULL` that says the fixture is incomplete. It is the
unreadable-resolving-to-zero pattern in DDL form: a real error converted into a
plausible no-op.

**How to apply:** reserve `INSERT OR IGNORE` for genuine idempotence, and when a
test fixture exists to satisfy a join, assert the join finds it rather than
trusting the insert. `ON CONFLICT (pk) DO NOTHING` is the narrower statement and
still raises on a missing `NOT NULL` column. Related:
[[unreadable-must-never-resolve-to-zero]].

---

## 2026-08-07 — Suppressing a conclusion is not suppressing the finding

The Dashboards page claimed, in its own docstring, that cells which cannot
clear the noise guard "say `(noise)` rather than showing a number." It rendered
`implied` and `actual` on every calibration row. Since `gap = actual − implied`,
the suppressed finding sat one subtraction away in two adjacent columns:

```
73.0c   46   73.0%   52.2%   (noise)
```

That is the exact 20.8-point false positive from the multiple-comparisons
lesson, handed to the reader by a guard that believed it had withheld it.

**Why:** the guard was written against the *name* of the thing being hidden —
the gap — rather than against what reconstructs it. Every part worked: the
arithmetic was right, the `(noise)` string rendered, and the dbt test passed.
The test passed because it was a tautology: `not is_distinguishable and
gap_display != '(noise)'` reduces to `(A ∧ B) ∧ ¬(A ∧ B)`, identically false.
So a guard checking the wrong thing was verified by a test that could not fail.

**How to apply:** when suppressing a derived value, ask what else on the page
recomputes it. Censor in the **mart**, not the view, so the presentation layer
never receives an uncensored result and a second dashboard cannot leak it
again — the raw columns stay for analysis, and the view binds only `*_display`.

Censor results, not inputs. `actual_rate`, `mean_pnl_cents`, `beat_close_rate`
and `mean_clv_cents` are outcomes and are hidden; `implied_probability` and `n`
are the price paid and the sample size, true regardless of what happened, and
stay visible. Withholding **one** operand is enough to break the subtraction,
and withholding both makes the table unreadable without hiding anything more.

And test the guard against raw inputs rather than against the flag it derives:
the replacement recomputes `n·p >= 5 and |gap| > 2·stderr` from `n`,
`implied_probability`, `gap_points` and `stderr_points`, so it compares two
independent derivations instead of one against itself. It also asserts the
other direction — a cell that *should* speak must not be silenced, because a
guard that hides everything is not a guard, it is a broken dashboard. Both
guards were verified by re-introducing the leak and watching them fail.

**Recurred 2026-08-10, in a pre-registration's own stop-the-line — third time
for this shape.** The clean-shortfall run tripped `R3` and withheld all five
verdicts: *"H4, H2, H3a, H3b and H1 are WITHHELD. None is declared, none is
refuted."* Then §S12 printed, for each of those same five, that it *"survives
leave-one-game-out over all 59 clusters and the `n_claims` key"* — a stability
statement about verdicts the run had just declined to state. It presupposes a
value it will not name, and it sits three lines below the census that
reconstructs that value, because §S says *"printed regardless"* in four places.
So the withholding is a string, not a property of the output.

The registration was written by an agent whose whole job is this failure, and it
still landed, which is the useful part: the guard was written against the **name
of the thing being hidden** — the word "verdict" — rather than against what
recomputes it. The dashboard hid `gap` and shipped `implied` and `actual`. This
hid the five verdicts and shipped `max E1`, `max_game_share`, the paired median,
`S_min`, `spread_at_min` and `n_degen` — every operand of every registered
decision rule, each printed under a rule quoted verbatim in the same document.
Subtraction was not even required; the reader applies the rule they were handed.

**How to apply, sharpened by the third instance:** a withholding rule has to
name the *inputs* it withholds, not the conclusion. If a design says a statistic
is printed regardless and also says a guard may withhold the verdict computed
from it, those two clauses are in conflict at write time and the conflict is
decidable **before** the run — no data is needed to see it. Decide it then:
either the guard suppresses the operands too, or it was never a suppression and
should be registered as a labelling rule. The run that discovers the conflict
discovers it with the numbers already public, which is the one moment when the
choice cannot be made cleanly. Ruled, in the open and after the fact, in
`docs/measurements/2026-08-10-preregistration-clean-shortfall-distribution.md`
Amendment A.

Related: [[four-audits-one-failure-shape]].

---

## 2026-08-07 — A budget that says *whether* and never *when*

`plan_sweep` decided which sport to poll and whether the credits were there. It
never decided **when**, so the two odds sweeps the free tier affords fired on
the first pass that had budget after the day rolled over. On 2026-08-07 that was
19:32Z, because a deploy happened at 19:32Z. Nothing chose it, and nothing in
the module was wrong.

The cost is invisible from inside it. `MAX_ODDS_AGE_S` is 900, so each sweep
makes the slate bettable for fifteen minutes; two a day is half an hour of
actionability out of twenty-four, and the code spending them had no opinion
about where that half hour landed. Every stage count looked healthy. The only
symptom was a Board nobody could ever act on.

**How to apply:** a rate limiter is not a scheduler. Whenever a resource is
scarce *and* what it buys is perishable, the allocation question has two halves,
and the second is usually the one left undone — ask what the resource is worth
at 03:00 versus at kickoff, and if the answer differs, something has to choose.
Two related traps found while fixing it:

- **The day boundary should follow the thing being metered, not the calendar.**
  UTC midnight is 5pm PT, the middle of the US evening slate, so a calendar day
  put the first half of one night's games in one budget bucket and the second
  half in the next. The month boundary stays on the calendar because that one
  belongs to the vendor and reconciliation depends on agreeing with them.
- **A schedule needs no stored state if it can be recomputed.** Which slots have
  been served is read back from the spend table, so a restart mid-window cannot
  double-spend and cannot forget. Anything a scheduler holds in process memory
  is state a crash loop will get wrong.

Related: [[two-limits-on-one-quantity]] — the due window and the loop interval
bound the same quantity, and a slot due for thirty minutes on a loop that wakes
every forty is stepped over every day. That check now runs at startup and
refuses, because the interval is a command-line argument and no test can see it.

---

## 2026-08-07 — A stored age rendered as a current one

`recommendations` stores `kalshi_quote_age_ms` as the age **at the moment the
row was written**. `/api/board` ordered by `suggested_contracts` across every
row ever recorded, with no clock anywhere in the query, and rendered each with
its stored age. So the best row an instance ever produced sat at the top of the
Board forever, reading `quote 3s ago` and `Buy 15 · $7.54`, three hours after
the quote behind it was gone.

**The knowledge was already in the codebase, one function away.**
`gate.recommendation_freshness` exists precisely for this, and its docstring
spells the trap out: *"a recommendation made yesterday against a 3-second-old
quote still says 3 seconds, and the freshness gate would wave through a day-old
price."* The order endpoint used it. The screen did not, and nothing connected
them.

No money was reachable — the control recomputes and refuses. What was reachable
was the reader, in front of a page offering a bet the server would not sell.

**How to apply:** an age is not a property of a row, it is a property of a row
*and a clock*. Any column named `*_age_*` measures a past instant and must be
re-derived before being shown as the present. Where both forms are useful, give
them different names and let each screen bind the one it means — the Ledger
wants the recorded age, because there it is a historical fact about the
observation; the Board wants the current one. One field name meaning "then" on
one screen and "now" on another is how two screens come to disagree.

Same shape as [[an-idle-threadpool-hides-every-thread-safety-bug]]: a comment
explaining one instance of a hazard is evidence the hazard is understood, not
evidence it has been handled everywhere. Grep for the *other* places that need
the knowledge, not just the one that has it.

**Recurred 2026-08-10, running the other way: a current value used to
characterise a past observation.** Above, a stored "then" was rendered as "now".
The mirror is a stored "now" read as though it were "then". `kalshi_markets.status`
is overwritten on every discovery pass — `backend/runner.py:1099-1108` upserts
with `ON CONFLICT(ticker) DO UPDATE SET … status = excluded.status`, with no
history kept — so it is **as-of-read, never as-of-observation**. A lane joined it
to quote rows to argue that the sub-15c prices in the record came from markets
that had settled. The conclusion happened to survive, but not on that evidence:
what carried it was the **timing**, +140 to +215 minutes after first pitch, which
is written at observation time and cannot be rewritten.

Note which column in the same schema is safe. `kalshi_quotes.observed_ms` is
commented *"when WE saw it"* (`backend/store/schema.sql:150`) and is
insert-only; `kalshi_markets.result` is deliberately `COALESCE`d on conflict, so
an outcome is written once and never unwritten, and `first_seen_ms` never moves.
The table is a **mixture** — some columns are facts about an instant, some are a
cache of the latest poll — and nothing in a column's name tells you which. Only
the write statement does.

**How to apply:** when characterising a historical fact row, **only columns
written at observation time are admissible.** Anything on a table that is
upserted is a statement about *now* that happens to be stored next to a row
about *then*. Before joining a dimension table to a fact table for an argument
about the past, read the `INSERT … ON CONFLICT` clause and treat every column in
the `DO UPDATE SET` list as unusable — the join will succeed and be silently
anachronistic either way. Where the mutable value is the one you need, the fix is
to stamp it onto the fact row at write time, not to reason about it later.

This is CLAUDE.md's *"the convenient column is usually contaminated"* with a
mechanism attached: there the contamination is convergence on the outcome
(`last_price` on a settled market), here it is overwrite. Same instruction —
state when a value was observed relative to the thing it describes — and the
overwrite case is worse, because convergence leaves a trace in the value and an
upsert leaves none.

---

## 2026-08-07 — Two populations in one record, told apart by dispersion

The runner priced any linked fixture with stored odds. Measured on one live
pass, **36 of 104 recorded rows were for games that had already started**:

    population   n    edge range (tenths)     suppressed
    pre-game     68   -39.2 ..  -17.7          5
    in-play      36   -200.3 ..  +67.7        14

The pre-game rows are a tight, entirely negative band — which is what a
correctly-priced market against a devigged consensus looks like. The in-play
rows are five times as wide and cross zero by 6.8c, three times the suspicious
edge ceiling. Nothing was miscomputed: a stored *pre-game* consensus was being
subtracted from a Kalshi price that had absorbed two innings, so the "edge" was
two different questions differenced.

Fourteen were caught by `wide_market` or `suspicious_edge` — defence in depth
doing its job by accident. The other **twenty-two passed with no suppression
reason at all** and entered the evidence record indistinguishable from ordinary
no-edge observations. That is the half that matters: the guards caught the loud
ones and let the quiet ones through, which is the worst possible split.

**How to apply:** before pooling rows into a record, ask what question each row
answers, not only whether each row is valid. Two populations answering different
questions usually announce themselves in the *spread* rather than the mean — a
range five times wider is a population boundary, not noise. And when one
population can never become evidence (these can never be CLV-scored at any
horizon, because the closing line is read before kickoff and these are written
after it), drop it with a counter rather than suppressing it: a suppression log
entry says "we considered this and rejected it", and we should not have been
considering it.

The rule generalises to which clock: the refusal reads the **sportsbook's**
kickoff, never Kalshi's, which runs three hours late and would call the seventh
inning "not started". The existing test fixture copied the sportsbook's time
onto the Kalshi event so the linker had something clean to match — which meant
every test in the file passed with the wrong clock. A fixture that erases a
distinction cannot test code that depends on it.

Related: [[two-limits-on-one-quantity]], [[every-per-cell-guard-can-pass]].

---

## 2026-08-07 — A detector that counts prose about the bug as evidence against it

This file already carried the cheap detector for orphaned code:

    grep -rn "score_recommendations" --include=*.py .
    # if every hit is tests/ or a seeder, the feature does not exist yet

Written up as a test, that grep reported `persist_recommendation` as *called
from* `backend/runner.py`. The only occurrence in that file is a docstring
explaining that nothing calls it. It reported `score_recommendations` as called
from `notify/alerts.py`, where the mention sits in a paragraph about how it went
uncalled for the project's entire life.

So the detector for orphaned code was satisfied by *writing about* orphaned
code — and it reads as a passing check, which is worse than no check, because
now nobody looks.

**How to apply:** when a check searches source for a symbol, parse instead of
matching. `ast.walk` over `Name`, `Attribute` and `alias` nodes ignores strings
and comments entirely. This matters more here than in most repos: the discipline
of documenting past defects in prose means the more carefully the lessons are
written, the more false hits a textual detector gets. Rule of thumb — if a
project's comments mention a symbol about as often as its code does, any
grep-based rule about that symbol is measuring the comments.

Verify it the usual way, and pick the case that separates the two
implementations: orphan the module *for real* — import removed, call removed, a
comment mentioning the name left behind — which is the exact shape of the bug
being detected. Related: [[code-with-no-caller-is-not-a-feature]],
[[a-test-that-passes-on-the-bug-is-not-a-test]].

---

## 2026-08-08 — Deduplicating the record made the record unusable

`persist_if_changed` refuses to write a second row when the derived ask and the
fair probability are unchanged. That is correct and measured: without it ~98% of
the record would be one candidate repeated, and a suppression summary dominated
by the same row rejected ninety-six times says nothing about which rules matter.

Every freshness check then measured from `created_ms`. So the two statements

    "this observation is old"
    "this price is old"

were one number, and on an unchanged market they diverged completely: the price
was current and the row was refused, thirty seconds after the pass that wrote
it. The dedupe was right about the *record* and was silently making a claim
about *freshness* it had no basis for.

**The tell was that both halves were individually defended.** The dedupe has a
docstring explaining what it deliberately loses; `recommendation_freshness` has
one explaining why an age must be re-derived from the clock. Neither mentions
the other, and the defect lives exactly in the gap: the freshness function
faithfully re-derived an age from an instant that had stopped meaning what it
used to mean.

**How to apply:** when a write path decides *not* to record something, ask what
downstream reads that absence as information. "We did not write a row" and "we
did not look" are different facts, and a schema that cannot tell them apart will
be read as the second. The fix is to record the non-event — here
`last_confirmed_ms` plus **both** ages, because a confirmation is a complete
re-statement about one instant, not a partial refresh.

Two supporting details worth keeping, both of which a wrong implementation gets
wrong in the flattering direction:

- **Refresh every clock the confirmation observed, or none of them.** Taking the
  confirmation's Kalshi quote age while leaving the odds age on `created_ms` is
  the tempting half-fix. It is *arithmetically identical* while no new sweep has
  happened — the odds observation instant is fixed either way — which is exactly
  what makes it look right. The dangerous variant is one that credits a
  confirmation with fresher odds than it observed; a row confirmed every fifteen
  seconds then never expires at all, and the tool starts offering bets priced
  against a consensus swept hours ago. The test that separates them is the one
  where the quote is perfectly fresh and the odds are past their limit.
- **A half-written confirmation is not a confirmation.** A timestamp with one
  age missing falls back to `created_ms` rather than borrowing the other half,
  because a freshness claim assembled from two different instants is worse than
  an old one. Same rule as [[unreadable-must-never-resolve-to-zero]], applied to
  a tuple instead of a scalar.

Related: [[two-limits-on-one-quantity]], which is what made the thirty seconds
matter; [[a-stored-age-rendered-as-a-current-one]], which is this same column
misread one screen over.

---

## 2026-08-08 — A rate limit belonging to one dependency was applied to both

The recording loop ran every 900 seconds. That number comes entirely from The
Odds API's free tier — ~500 credits a month, six a sweep, two sweeps a day — and
it was applied to the Kalshi leg as well, which is **unmetered**. Kalshi is also
the tighter freshness limit: 30 seconds against the consensus's 900.

So one cadence served two dependencies with nothing in common, and the composed
result was a tool actionable for about a minute a day.

The fix is two cadences: a full pass on the odds interval, and a quote pass —
Kalshi discovery, the quotes it carries, a re-price against stored odds — every
fifteen seconds *while the window is open*. It costs no credits and it does not
widen the window by a second; fifteen minutes twice a day is set by
`MAX_ODDS_AGE_S` and the budget. What it changes is that those fifteen minutes
are usable throughout instead of for the first thirty seconds.

Three things this got right only because they were asked explicitly:

- **The gap between confirmations is the sleep plus the pass**, not the sleep.
  `quote_refresh_survives_interval` takes both and the loop refuses to start when
  the product exceeds the limit, in the same shape as the existing
  `sweep_window_survives_interval`. A fast cadence that still lets rows expire
  between passes buys nothing and reports nothing — an expired row looks exactly
  like a row nobody wanted.
- **Fast only while the window is open.** The predicate is the existing
  `window_status(...).is_open`, because outside it nothing is bettable and there
  is no reason to poll Kalshi 4,300 times a day for it.
- **Not every leg belongs on the fast cadence.** The quote pass deliberately
  skips the odds sweep, the closing-line fetch and the digest, and says
  `sweep_decision: "quote refresh only"` rather than leaving the field blank — a
  quote pass and a full pass that considered a sweep and declined need opposite
  responses.

**How to apply:** when one interval serves several dependencies, write down what
each one is actually limited by. A number chosen for the scarcest resource will
be inherited by everything that shares the loop, and the inheritance is
invisible — every module sees a reasonable interval and none of them sees why.
Related: [[a-budget-that-says-whether-and-never-when]], which is the same
question about *when* rather than *how often*.

---

## 2026-08-08 — The user-facing explanation of a limit outlives the limit

Fixing the polling cadence made four pieces of copy false, and each of them had
been *correct and carefully written* when it shipped:

    "the individual rows expire sooner than this window does"
    "the recorder polls far less often than that"
    "every one of them is now priced against a Kalshi quote past its 30s limit"
    "the quote behind it is 3s, past the 30s limit"     <- and now nonsense

The last one is the instructive case. The card named the quote as the cause
unconditionally, which was true while both clocks advanced together. Once the
quote is re-checked every fifteen seconds and the consensus is not, expired rows
expire on the *books* — and the card rendered "quote 3s ago, past the 30s
limit", a sentence that is internally contradictory and that a reader cannot act
on.

None of this was caught by 998 passing tests, `tsc`, or a successful build. It
was caught by rendering the page and reading it, which also turned up a JSX
spacing bug (`15minutes`) that no automated check in this repo would ever see.

**How to apply:** when a limit changes, grep for the *prose* about it, not only
the code. And prefer copy that reads the state over copy that asserts a cause —
the Board now counts which of the two clocks each expired row actually broke and
says that, so the next time the balance shifts the page follows instead of
lying. A hardcoded explanation of a dynamic system is a comment in a place
users can see.

Corollary, and this is the third time this file has said a version of it: the
build-order step is not done when the tests pass. Run the app and look at it.

**Recurred the very next day, on the sentence written to fix it.** The
order-time quote refresh made a *stale quote* stop expiring a row, and three
pieces of copy went false again — including the one above, which had been
rewritten hours earlier to read the state instead of asserting a cause. It read
the state of the wrong thing: it counted which clock had run out, when the
answer had become "only one of them can". The banner asserted every row's quote
was re-checked every few seconds, while the cards under it said the price was a
minute old.

The pattern under all three versions is narrower than "copy goes stale": **a
sentence that names *which* mechanism is responsible has a shorter life than one
that names what the reader can do about it.** "The consensus behind this is 18
minutes old and only a credit refreshes it" survives a change to the quote path;
"the quote behind it is past its 30s limit" does not. Prefer the second kind,
and when a mechanism changes, grep for the prose that names the mechanism —
not just for the number.

---

## 2026-08-08 — Two guards passed their tests on the first run, and both were broken

Seventeen guards were added with the order-time quote refresh, and every one was
verified by disabling it and watching the test go red. Fifteen went red.

The two that stayed green were not missing tests. They were **defects the tests
could not have caught, because the code was unreachable**:

- **A portfolio cap that could no longer fire.** The order endpoint re-checked
  `exposure + contracts * ask` against the caps after sizing. That was
  load-bearing while `contracts` came from a row written minutes earlier — but
  the refresh made `size_position` run *inside the request*, at the live ask,
  against the exposure read four lines above, and it bounds
  `contracts * effective_price`, which is fee-inclusive and therefore strictly
  larger. So the re-check compared a smaller number against the same cap and
  could not fail on any input.
- **A refusal behind a test double.** `LiveQuoteSource` refuses a response about
  a different market than the one requested. Every endpoint test injected a fake
  source, so the branch sat under the fake and never executed.

Both read as defence in depth. Neither was.

**Why the disable-and-watch-it-fail rule caught these when nothing else would.**
A green test after disabling a guard has exactly two causes and they look
identical: the test does not exercise the guard, or *nothing* exercises it. The
second is the more interesting finding and the one that never shows up in
coverage — the line is covered, it just cannot change an outcome.

**How to apply:** when a disabled guard leaves the suite green, ask which of the
two it is before writing a test. If the guard is unreachable, a new test is the
wrong fix — it would pin behaviour that cannot occur. The fixes here were to
**delete** the cap re-check (per
[[computing-the-right-statistic-and-then-ignoring-it]]: don't test that two
paths agree, delete one) and to make the refusal reachable by letting the source
take an injected transport. And note what the deletion cost: the caps still have
to be shown to bind *at order time*, so the test that replaced the dead code
asserts the outcome — a tight cap shrinks the order, exposure the engine never
saw shrinks it to nothing — rather than asserting the code exists.

Related: [[a-test-that-passes-on-the-bug-is-not-a-test]],
[[the-zero-that-means-no-measurement]] — a guard that cannot fire is
indistinguishable from one that is working.

---

## 2026-08-08 — Re-deriving a decision at a new price is one-sided unless you say otherwise

Refreshing the Kalshi quote at order time re-runs `size_position` at the live
ask. An adverse move shrinks the order to zero and refuses, which is obviously
right and is what the change was built for. A **favourable** move was accepted
unconditionally, at up to the size the engine had authorised.

That looks symmetrical and is not. `size_position` is monotonic in price: a
lower ask always returns *more* contracts, never a refusal. So the re-derivation
had a refusal branch in one direction and none in the other, and the direction
with none is the one this project's governing rule is about — **a large apparent
edge is a bug until proven otherwise.** An ask that fell six cents since the row
was written is not six cents of found money on a venue quoted to ~2c by thirteen
sub-200ms firms; it is the market deciding your side is worse, and you are last
to know. `suppression.edge_ceiling_tenths` catches exactly that at
recommendation time and simply was not being applied at order time.

**The tell was in the tests, and I wrote past it.** There was a test for a price
that moved against us and a test for a price that moved in our favour, and only
the first asserted a refusal. Two tests named for opposite directions where one
expects an error and one expects success should prompt the question "is the
asymmetry real?" — here it was an artefact of which function did the work.

**How to apply:** when a control is re-run against fresher inputs, list the
checks the *original* decision passed and ask which of them the re-run drops.
Sizing was carried over; the edge ceiling, the method-noise floor and the depth
check were not, and only depth had been noticed. A re-derivation that is
strictly a subset of the original decision is a loosening wearing the costume of
a refresh.

Corollary found in the same review: **the runner refusing to *record* a started
game does not retract the row it wrote ten minutes before kickoff.** That row
keeps its size and stays inside the 900s odds window well into the first
quarter, and re-reading Kalshi makes it worse — the ask becomes a live in-play
price while the fair value beside it is a pre-game consensus. A drop applied at
write time needs a matching refusal at read time, or the guard only holds for
rows that do not exist yet. Related: [[two-populations-in-one-record]],
[[two-limits-on-one-quantity]].

---

## 2026-08-08 — Kalshi sends "0.0000", not a missing field

`ask_for_side` returns `None` when the opposing bid is unreadable, and the order
endpoint refused on `live_ask is None` with a message about an absent bid. That
branch cannot run on real data. **Kalshi publishes `"0.0000"` for a side nobody
is bidding** — 38 of 245 markets in the discovery capture carry
`yes_bid_dollars == "0.0000"` — so a genuinely one-sided book parses cleanly to
`0` and derives an ask of `1000`.

Nothing was unsafe: `is_valid_price` rejects 1000 a step later inside
`size_position`, so the order was refused either way. What was wrong was the
*reason*. The refusal that reached the screen said **"the price moved. Recorded
45c, live 100c"** — a sentence describing a market that moved 55 cents, when
what actually happened is that nobody is offering that side at all. Two
completely different situations, one message, and the message names the rarer
one.

**How to apply:** this is [[unreadable-must-never-resolve-to-zero]] with the
polarity reversed — not "a parser turned garbage into zero" but "the venue sends
a real zero where the code expected an absence". Before writing an
`is None` guard against a wire field, check what the API actually emits for the
empty case. And when a value has a legal-but-meaningless extreme (0 and 1000 on
a price grid), test the *extreme*, not the null: the null may be unreachable.

The general shape, now the fourth entry in this file about it: a guard whose
branch cannot be reached is not defence in depth. It is a comment that looks
like code, and it silently hands its job to whatever refuses next — which
refuses for a different reason and says so.

---

## 2026-08-08 — A ticker's failure mode is silence that looks like calm

Streaming live prices into the cockpit removes the staleness problem for
display and introduces exactly one new one: **a feed that stops looks identical
to a market that went quiet.** Frozen prices that read as current are the
worst state this system can be in, and it is the half-dead-container problem
(`docker/entrypoint.sh`) moved into the browser, where no supervisor can see it.

So the design is: a heartbeat on a fixed interval whether or not anything moved,
a `down` event pushed the instant the feed dies, that same state repeated on
every heartbeat so a tab that was asleep still learns about it, and a client-side
timer that treats *nothing at all* — not even a heartbeat — as a fault.

**The first version of the test for this passed with the broadcast deleted.** It
accepted the down state arriving on a heartbeat, and the heartbeat carries it
too. Both paths are wanted, but they are not interchangeable: the heartbeat
interval is ten seconds, and ten seconds of prices that look live after the feed
has gone is the entire failure being designed against. The fix was two tests —
one with the heartbeat set *long*, asserting the event arrives anyway.

**How to apply:** when a system has a fast path and a slow path to the same
state, a test that accepts either verifies neither. Set the slow path out of
reach and assert the fast one. And for anything that pushes: decide what
*silence* means before shipping it, because the default meaning is "everything
is fine".

---

## 2026-08-08 — A test asserted the order of a command that was not in the image

`entrypoint.sh` runs `scripts/migrate_db.py` before uvicorn, and
`TestTheEntrypointRunsWhatItMustRunFirst` asserts exactly that by parsing the
script. It passed. The deployed container crash-looped:

    [entrypoint] checking database schema
    python: can't open file '/app/scripts/migrate_db.py': No such file
    Main child exited normally with code: 2
    machine has reached its max restart count of 10

Both statements were true simultaneously. The migration *did* run first, and the
file it ran was not there. `.dockerignore` carries `scripts/*` with a hand-kept
`!` allowlist; the allowlist named `run_loop.py` and nothing else, because it
was written when the entrypoint executed one script.

**The comment directly above it described this exact failure**, from the last
time it happened: *"`run_loop.py` is the live entrypoint's own process, not a
dev script. Excluding the whole directory built an image that started, reported
healthy and served pages while the one process that grows the evidence record
was simply absent from the filesystem."* A prose account of a defect does not
generalise to the next member of its class — only a derived list does.

**Why the test could not see it.** It asserted a property of the *repository*
and the failure was in the *image*, and nothing in the suite knows those are
different filesystems. This is [[two-limits-on-one-quantity]] in a new place:
"runs before uvicorn" and "exists at runtime" are two halves of one property,
and a guard covering one half reads exactly like a guard covering both.

**How to apply:** when a deny-everything-then-allowlist rule governs which files
reach production, derive the allowlist's contents from the thing that consumes
them rather than maintaining it by hand. The replacement extracts every
`scripts/*.py` the entrypoint executes and asserts each one survives
`.dockerignore`, so a third script is covered without anyone remembering. It
carries its own guard both ways — a matcher that never reports "ignored" would
pass on any input, so `capture_fixtures.py` must come back excluded — per
[[a-test-that-passes-on-the-bug-is-not-a-test]].

**And the deploy order is what made this cheap.** Demo and live run the same
image; demo went first, took the crash loop, and cost a public page some
downtime. Live would have taken it on a volume holding the only copy of the
evidence record — and `/api/health` never answers at all in this failure, so
Fly's health check catches it, which is the one merciful detail. Two-step
deploys are not ceremony: the first step is the one that finds out whether the
image boots.

---

## 2026-08-08 — The counter you are told to watch was counting the other population

The fast cadence's whole justification is a composition — sleep plus pass must
stay inside the 30s Kalshi limit — and `Tempo.observe_pass_duration` exists to
say when a real pass breaks it. It was called after **every** pass and always
compared against the **fast** interval.

The live instance's first pass tripped it:

    a pass took 14.9s; ... worst-case gap 32.2s, past the 30s Kalshi quote limit

That pass discovered 167 events, quoted 1,426 markets and joined 228 rows for
CLV. It was a *full* pass, on the 900s cadence, with the window **closed** and
no quote pass running at all — 14.9s is what a healthy full pass costs. The
arithmetic in the warning described a cadence that was not running.

Full passes happen every 900s forever, so `passes_over_quote_budget` would have
been ~96 routine entries a day. This repo's own rule, written down twice
already: **if most inputs trip it, it is a state, not an exception, and logging
it as an exception destroys the log's value as a diagnostic.** The counter was
the single signal that the fast cadence had stopped working, and it was
guaranteed to be dominated by passes doing exactly what they should.

**What made it invisible.** The function took a duration and nothing else, so it
*could not* tell the populations apart — the caller had `kind` in a local
variable and used it two lines below. And the test carried the intent in prose:
its docstring said *"a quote pass slow enough to break the composition"* while
the code it exercised had no notion of a quote pass. A docstring naming the
population is not the code selecting it.

**How to apply:** when a check is about one population, make the population a
**required** argument rather than a comment — a keyword-only `kind` that the
caller must supply cannot be forgotten the way a docstring can. And when one
number can be tripped by two different situations, ask what the reader is
supposed to *do* about each: "the fast cadence is decoration" needs a fix, "the
once-per-window full pass spans one confirmation gap" is structural and needs
nothing. Two responses means two counters. Related:
[[two-populations-in-one-record]], [[no-result-and-rejected-are-different]],
[[computing-the-right-statistic-and-then-ignoring-it]].

---

## 2026-08-08 — A wrong value that is still legal never announces itself

The order path floored every limit price to a whole cent. Kalshi accepts whole
cents on **every** price structure, so the wrong price was always a *valid*
price: no rejection, no error, no log line. On a market with a half-cent grid it
turned a 50.5c ask into a bid at 50c — an order that rests behind the market
forever, never fills, and enters the paper record as a bet that was placed.

The two failure modes are not equally visible and not equally bad:

| | Rejected order | Unfillable order |
|---|---|---|
| Announces itself | yes, immediately | never |
| Effect on the record | none | a bet that did not happen |

On a project whose entire product is the evidence record, the second is the
worse one, and it is the one no exception handler can catch. Worse still, it is
*biased*: whichever side happens to sit on a whole cent fills and the other does
not, so the record fills up with one half of the strategy.

**How to apply:** when a value is coerced onto some legal set before being sent,
ask what happens when the coercion is wrong *and the result is still accepted*.
If the answer is "nothing observable", the coercion needs its own test with an
input where a wrong implementation gives a different answer — not merely a legal
one. Here that is `buy NO at 40.5c on a half-cent grid`: correct sends a YES ask
of 0.5950 and costs 40.5c, the old floor sent 0.6000 and costs 40.0c, and both
are prices the exchange is perfectly happy with. Related:
[[clamping-is-for-values-you-trust]] — clamping and flooring are the same move,
and the tell is the same: a loud failure converted into a quiet one.

**And check the endpoint, not just the field.** The fix was unreachable without
noticing that `POST /portfolio/orders` takes integer cents and had been
deprecated — it is absent from Kalshi's current API reference entirely, while
this repo had been posting to it for the whole project. Nothing failed, because
nothing had ever posted. The V2 replacement also emits no `status` field, and
the old parser read `response["order"]["status"]` with a default of `"resting"`;
every live order would have been recorded as resting with a null order id. Same
shape as [[unreadable-must-never-resolve-to-zero]], one layer up: when checking
whether a *field* can carry the value you need, check that the *endpoint* is
still the one the vendor documents.

**Read `n` before the effect size, on this too.** The note that raised this said
"~25% of markets tick in half-cents". That is true of all Kalshi markets and
false of the ones this project prices:
`scripts/capture_price_grids.py` measured **1,426 game markets, all
`linear_cent`** on 2026-08-08, against 60 of 2,145 half-cent two days earlier.
So the fix changes nothing today. It is still right, because the grid is
assigned per market and Kalshi publishes a `price_level_structure_updated`
lifecycle event — but "0 of 1,426" belongs next to the fix, and it must not
become "sub-cent game markets do not exist". That is exactly
[[a-true-measurement-licensed-a-false-conclusion]].

---

## 2026-08-08 — A guard that fails every time says exactly as much as one that never fails

CI's secret scan — *"the last thing standing between a private key and a public
commit"* — was red on **36 consecutive pushes**. It grepped for the phrase
`BEGIN … PRIVATE KEY`, and two files in this repo legitimately contain that
phrase: `docker/entrypoint.sh`, which validates that a decoded key is an RSA PEM
rather than OpenSSH, and `tests/test_logging_redaction.py`, which proves the
redactor strips a PEM block.

**So the scanner fired on the two files that exist because of key hygiene.**
The information content of the check went to zero in both directions: nobody
could tell the run that found a real key from the 36 that found a comment about
one, and red became the resting state while the two jobs that would catch a real
regression sat green underneath it.

The repair is to match the **material** rather than the word for it — and the
repair is where the second half of the lesson is. Narrowing from a phrase match
to a material match *lost a case the broken pattern had caught*: a key pasted
straight after an opening delimiter,

```
KEY = """-----BEGIN RSA PRIVATE KEY-----
```

matches neither "header alone on its line" nor "header followed by a base64
body", because the body is on the next line and grep is line-oriented. Fixing a
false positive quietly opened a false negative, which is the strictly worse
direction for a security check.

**How to apply:** two rules, and the second is the one that generalises.

- **A check that has never passed has never been tested.** Before trusting a
  detector, run it against a known positive *and* a known negative. This step
  now carries its own canaries — planted key-shaped material with a random body,
  and a header merely mentioned in prose — and fails loudly if either answer
  changes. The canaries caught a real bug in the step on their first run:
  `grep` read a pattern beginning `-----` as options, so every match needed
  `-e`.
- **Test the exclusions against the real files, not against synthetic ones.**
  The two legitimate files are the exact shape the scan must not fire on, so
  they are asserted directly. A synthetic "mentioned" fixture proves only that
  *some* mention is tolerated, which is true of almost any pattern. Same rule as
  [[test-the-filters-exclusions]]: when code filters, test the rejects.

Note also the tell that a checklist can be wrong in both directions at once.
`tasks/NEXT.md` listed this item as unbuilt; it had been built in the first
commit, was passing three jobs, and was failing the fourth. Neither the document
nor the green badge described the state.

---

## 2026-08-08 — Two implementations of one money quantity, neither ever run

`runner.py` computed exposure from `fills` net of `settlements`. `routes.py`
computed it from live `orders`. Both had existed for the life of the project,
both were called on the money path — the runner's number sizes every
recommendation, the endpoint's sizes the order that follows — and **both
returned `0.0` every time**, because no row had ever been written to any of the
three tables.

So the duplication was undetectable by every means available. The tests passed:
each asserted its own function's behaviour and both behaved correctly. A grep
for callers found callers. `test_has_callers.py` was satisfied. The two numbers
agreed perfectly, on the only input either had ever seen.

They are not the same quantity. A resting order is committed capital and appears
in `orders` and not in `fills`, so the day an order was written they would have
diverged — with the runner recommending a size against one budget and the
endpoint spending a different one.

**How to apply:** the disable-and-watch-it-fail rule has a sibling for
*duplicate* implementations, and it is the same question asked once: **has
either of these ever produced a non-default answer?** Two functions that agree
only because both return zero have not been shown to agree about anything.
Before writing the first row into an empty table, grep for everything that reads
it and ask what each reader believes the table means — that is the last moment
the answer is cheap, because until then nothing can be wrong.

The fix is [[computing-the-right-statistic-and-then-ignoring-it]]: delete one of
the paths rather than testing that they agree. The test that replaced them
asserts the *deletion* — `runner.current_exposure_dollars is
store.orders.current_exposure_dollars` — because a test that the two agree
numerically would have passed before the fix too.

Related: [[code-with-no-caller-is-not-a-feature]], which is this one level up —
there the feature was absent, here it was present twice and equally inert.

---

## 2026-08-08 — An enumeration of the safe cases is a list you will forget to extend

Exposure counted `status IN ('pending', 'resting', 'filled')`. Three statuses
the author had in mind. `kalshi/orders.py` emits seven, and two of the omitted
four are money at risk:

    partially_filled        a filled leg and a resting leg, both live
    unrecognised_response   "the response could not be read, so this may
                            have filled"

The second is the whole point. It is the status this project invented
specifically so that an unreadable order response could not be mistaken for
anything — and an allow-list of live statuses silently valued it at **zero
dollars**, which is precisely the reading it exists to prevent. The safe-looking
half of a guard undid the careful half, one file away.

Inverted, the query now excludes `unfilled`, `rejected` and `canceled` and
counts everything else. That is not a stylistic preference. A status added a
year from now and forgotten here **counts**, and counting refuses an order;
under the allow-list it vanished, and vanishing permits one.

**How to apply:** when a filter decides whether something is dangerous, list the
cases you are declaring *safe*, never the cases you are declaring dangerous. The
list of dangerous things grows without you; the list of safe things does not.
Then ask which way an unrecognised value falls, because that is the behaviour
the list actually encodes.

The same shape caught a second thing in the same query. `SUM` skips NULLs, so a
row with no limit price contributed nothing and read as an order that cost
nothing — [[unreadable-must-never-resolve-to-zero]] arriving through SQL's
aggregate semantics rather than through a parser. It is counted separately now
and refuses. Related: [[test-the-filters-exclusions]],
[[no-result-and-rejected-are-different]].

---

## 2026-08-08 — The value you already had is not a value you chose

Two writer processes now touch the database, so a blocked writer must wait
rather than fail. `connect()` got `PRAGMA busy_timeout = 5000`, a test asserting
a second writer waits, and a paragraph explaining why.

**CPython's `sqlite3` defaults `timeout` to 5 seconds.** The pragma set the
value the driver had already set. It was a no-op in the most literal sense —
delete the line and every byte of observable behaviour is identical — and the
test passed either way, because the property was real and something else was
providing it.

Nothing found this except the standing rule: disable the guard, run the test,
and look at the result rather than at the code. Twelve other guards in the same
change went red on cue. This one stayed green, and the reason was neither of the
two the rule usually turns up — the test *did* exercise the property and the
property *was* reachable. It was that the code under test contributed nothing to
it.

**How to apply:** when a disabled guard leaves the suite green, the third
possibility is that the behaviour comes from somewhere else entirely — a library
default, a platform default, another layer that already handles it. Find out
which, because the two repairs are opposite: delete a redundant line, or make
the inherited value an explicit choice so a dependency upgrade cannot remove it
silently. Here it is the second, since a driver shipping `timeout=0` would
restore fail-immediately with nothing in this repo changing.

The tell to watch for: a guard whose disabled form is *exactly* the default. If
the number you are setting equals the number you would get anyway, you have
written documentation, not code — and it will be believed as code.

**Recurred the same day, on a threshold rather than a default.**
`agents/base.py` put a `cache_control` breakpoint on the shared house context,
behind a comment saying the savings on a repeated system prompt were "the whole
reason to cache". Measured: the block is **401 tokens** and Claude Opus 5's
minimum cacheable prefix is **512**. It had never produced a cache entry.

That one is worse than the pragma, because the pragma at least did what it
said. A prefix under the minimum does not cache and *does not complain* — no
error, no warning, `cache_creation_input_tokens: 0`, a response identical in
every respect to one that cached. There is no failing state to observe; the
only way to find it is to go and count.

So the shape generalises past defaults: **a setting whose effect depends on a
threshold you did not check is a setting you have not made.** Ask what the
threshold is, measure the thing against it, and put the measurement next to the
code. Two specifics worth carrying:

- The number belongs in a **runnable** script, not only in a comment.
  `scripts/measure_agent_cache_prefix.py` prints the prefix per agent and exits
  non-zero if one falls under. A comment recording "401 tokens" is true until
  someone edits the prompt.
- **The threshold moves with the model, and not in one direction.** The minimum
  is 512 on Claude Opus 5, 1024 on Opus 4.8 and 4096 on Opus 4.6 — so pointing
  `AGENT_MODEL` at an *older* model silently switches the cache off. A
  dependency whose limits are non-monotonic across versions cannot be reasoned
  about from the direction of the upgrade.

Related: [[two-guards-passed-their-tests-and-both-were-broken]],
[[a-test-that-passes-on-the-bug-is-not-a-test]],
[[the-zero-that-means-no-measurement]].

---

## 2026-08-08 — A guard tightened for a false negative fires on the file explaining it

The CI secret scan's third pattern was added to catch a key pasted straight
after an opening delimiter — a triple-quote, then a PEM header, then the body on
the next line — a case the previous, broken pattern caught and the narrowed one
had lost.

`tasks/lessons.md` documents that case **by reproducing it**, in a fenced code
block, because writing the shape out is how the lesson is legible. So the repair
for a false negative shipped a false positive onto the file that explains the
false negative, and CI was red on `main` before anyone pushed.

This is the third consecutive turn of the same screw on one check: a phrase
match that fired on prose, a material match that lost a real shape, and a shape
match that fired on prose again. Each repair was correct about the defect in
front of it.

The escape is not a better regex or a path exclusion. It is noticing that the
feature being matched was never the right one: **the quote was never what
distinguished a key from a mention. The next line was.** A quoted header
followed by a fence, by prose, or by nothing is a mention; one followed by forty
characters of base64 is a key. grep is line-oriented and structurally cannot see
that, so the check stopped being a grep for that one case and became two lines
of awk.

**How to apply:** two things, and the second is the one that generalises.

- **In a repo that documents its own defects, the documentation is inside the
  scan surface.** The better the write-up, the more exactly it reproduces the
  thing being detected. Excluding those files is the wrong reflex —
  `tasks/lessons.md` is prose *about leaked keys*, which makes it a genuinely
  plausible place for one to be pasted, so excluding it would make the most
  likely accident the least visible. It is asserted to stay clean instead,
  beside the two files already listed.
- **When a detector's third repair is another adjustment to the same pattern,
  the pattern is matching the wrong feature.** Ask what actually separates the
  true positives from the false ones, and if the answer is not expressible in
  the tool being used, change the tool rather than the expression. Related:
  [[a-guard-that-fails-every-time]], [[test-the-filters-exclusions]].

One portability note, since this now runs `awk` on `ubuntu-latest`, which ships
mawk: interval syntax is not portable there and `length()` is, and a bare slash
inside a bracket expression is a lexer hazard, so both regexes are passed in
with `-v` rather than written as awk literals.

And one trap for whoever next verifies this step by hand: `printf` given a
doubled backslash-n emits a literal backslash-n inside the step and a **real
newline** through some outer quoting layers. A canary built the second way is a
two-line file that silently exercises a different pattern than the one it is
named after — it reported the escaped-key pattern as broken when the pattern was
fine and the canary was not.

---

## 2026-08-08 — `occurrence_datetime` is a shifted start, and both stories had real evidence

Two readings of Kalshi's `occurrence_datetime`, each with a measurement behind
it and neither explaining the other's:

- **A shifted start.** +180 minutes against the sportsbook kickoff on 14 of 18
  MLB pairs *and* 6 of 6 WNBA pairs. Identical offsets for a 3h sport and a 2h
  one is what a fixed shift looks like.
- **An expected end.** `occurrence_datetime == expected_expiration_time` on 198
  of 200 markets in the discovery capture.

Settled by a **period series**, which discriminates absolutely and costs
nothing: a first-five-innings market and a full-game market on the same game
must carry the *same* value if the field is a start, and must differ by about
the period's length if it is an end. Measured across 15 series pairs: **not one
period market is earlier than its game market.** Thirteen are bit-identical and
two are *later*, which no end-semantics can produce.

The sharpest single row needs no comparison at all. On one MLB game, nine market
types — including `KXMLBRFI`, which resolves about twenty minutes after first
pitch, and `KXMLBEXTRAS`, which resolves at the end or later — carry the
**identical** `occurrence_datetime`, and it sits exactly +3.00h from the first
pitch stated in words in each market's own `rules_primary`. Markets that expire
hours apart cannot share an expiry.

`expected_expiration_time` looked corroborating because it is a *copy* of
`occurrence_datetime` — including on the first-inning market, which plainly does
not expire three hours after first pitch. NFL is the one series that populates
it independently, and there the two differ by exactly one football game.

**How to apply:** when two readings each have supporting data, stop gathering
more of the same and look for the input where they predict **opposite** answers.
Here that is a market covering a *shorter* interval of the same event: agreement
under one story is impossible under the other, so a single pair settles what
hundreds of confirming rows could not. This is
[[a-sign-convention-agreed-with-its-own-test]]'s rule about definitional anchors,
applied to a measurement instead of a test: pick the case where the wrong answer
*differs*.

Two consequences worth carrying:

- **The offset is not game-length-dependent**, so the fixed 4h tolerance in
  `match.linker` and `core.suppression` is right and should not be made
  per-sport. That was the open worry and the answer is no.
- **But it is not uniform across series either.** `KXMLBF5` sits at **+5h**
  while `KXMLBF5SPREAD`, covering the identical five innings, sits at +3h — so
  the extra two hours are per-series data entry, not semantics. Nothing in scope
  today prices a period series, and the day one is priced a 4h tolerance drops
  every `KXMLBF5` market silently. That is [[two-limits-on-one-quantity]]
  waiting to happen, filed before it does.

And drop the "US Eastern-to-Pacific gap" gloss the earlier entry offered for
*why* it is three hours. The shift is measured; the explanation was not, and a
plausible cause invites a future session to "fix" it with a venue timezone
lookup. Related: [[a-true-measurement-licensed-a-false-conclusion]].

---

## 2026-08-08 — A green suite that depended on what time you ran it

A routine full-suite run went red on `test_it_reports_the_remaining_budget_in_
sweeps`. Nothing had changed since the previous green run an hour earlier, and
the failing assertion was `assert 6 == 12`.

The demo seed writes two odds sweeps, two minutes and five hours before `now`.
The budget day rolls at **10:00Z**. So between 10:00Z and 15:00Z the older
sweep falls into yesterday's budget and `spent_today` is 6 rather than 12 —
for five hours out of twenty-four, and only those five.

**The test was the messenger; the seed was the defect.** The spend rows exist,
per their own comment, so the window panel does not "report a full day's budget
beside odds that were obviously fetched, and the two halves of the same screen
contradict each other." For those five hours it showed 6 of 16 spent beside two
sweeps' worth of odds. The thing the code was written to prevent was happening
inside the code that prevented it, on a timer.

**Why nothing caught it.** CI runs on push, at whatever hour someone pushes.
Thirty-odd pushes had all landed outside the window. A suite that is green is
not evidence a suite is deterministic — it is evidence about the samples drawn,
and wall-clock hour is a dimension nobody thinks of as an input.

**How to apply:** an age measured from `now` does not place a row inside a
period whose boundary is a fixed instant. Whenever a fixture's timestamps are
relative and the code's windows are absolute, the two only agree by
coincidence — anchor the fixture to the **boundary**, not to now.

And test the whole cycle rather than sampling it. The replacement is
parameterised over all 24 hours, because a defect confined to a five-hour band
is a coin flip for any single sample, and the disable-check makes the shape
plain: reverting the fix turns hours 10–14 red and leaves the other nineteen
green. That is also precisely how CI missed it.

The general form, which is broader than clocks: **if a test's result depends on
an input the test does not supply, it is not a test of the code — it is a
measurement of the environment.** Wall-clock time, timezone, locale, filesystem
ordering, hash seed, and free disk all qualify. Related:
[[a-budget-that-says-whether-and-never-when]] — same 10:00Z boundary, and the
same failure to ask what the number is *relative to*;
[[a-test-that-passes-on-the-bug-is-not-a-test]].

---

## 2026-08-08 — A component that only exists after a tap is invisible to every check you have

`TicketSheet.tsx` — 962 lines, the screen a person taps to bet — had never been
rendered when it was handed over. Every automated check in the repo was green
and none of them could have seen it, for two independent reasons:

- **It mounts on an interaction.** `check_mobile.py` measures five pages as they
  *load*. A component that does not exist until a card is tapped is not on any
  of them, so it could have overflowed at 320px on every handset and the script
  would still have printed "All pages fit the viewport."
- **It is `position: fixed`.** A fixed element is laid out against the viewport
  rather than the document, so an over-wide sheet does **not** widen
  `documentElement.scrollWidth` — which is the number that script decides on.
  Even pointed at the right page, the measurement it takes cannot move.

Tapping it found three defects, and the instructive part is that **none of them
is a layout fault**. The sheet fit at 320, 390 and 430 on the first render. What
was wrong was behaviour a static reading cannot produce: focus escaping to
`<body>` the moment Confirm unmounted, and a caption naming a cause the reader
could act on when acting on it changed nothing.

**Two ways the new measurement lied before it worked**, both worth carrying
because both produced a confident wrong answer rather than an error:

- **A mouse event dispatched outside the viewport is silently dropped.** The
  first card on the Board starts below the fold at 320x844, so the tap landed
  nowhere and the script reported "tapping the card did not open the sheet" —
  which reads as a broken component. Scroll it into view, then read its
  coordinates *after* the scroll.
- **Measuring during an entrance animation reports a layout fault that does not
  exist.** The sheet rises from `translateY(6%)` over 0.26s. Probed mid-flight
  it sits 6% of its own height low — 15px at 390, 45px at 320 — which is exactly
  what a sheet overflowing the bottom of the screen looks like. The fix is to
  wait on `getAnimations()`, not on a sleep, because a sleep tuned to one
  machine is the same class of mistake.

**How to apply:** the completion criterion for an interactive component is a
check that *performs the interaction*. If the only thing standing between a
component and production is a script that loads pages, the component has not
been checked — and the more carefully it is written, the more convincing the
unchecked version looks. `scripts/check_ticket_sheet.py` taps, waits for the
animation, measures, presses Confirm, and measures the answer, because the
answer is the state that actually happens. Related:
[[a-window-resize-is-not-a-viewport-change]] — same family, one step further in:
that entry is about measuring the wrong thing, this one is about measuring at
the wrong moment and in the wrong state. Also
[[code-with-no-caller-is-not-a-feature]]: a component nothing has rendered is
the front-end form of a module nothing calls.

---

## 2026-08-08 — One environment variable, two readers, two different times

`API_ORIGIN` is read in `next.config.ts` to build the `/api/*` rewrite, and in
`lib/api.ts` to resolve `BASE` for server-component fetches. `tasks/NEXT.md`
recorded that the rewrite destination "is read at Next's start, not at build".
It is read at **build**: `next build` evaluates the config and freezes the
result into `.next/routes-manifest.json`, where it sits as a literal
`"destination": "http://127.0.0.1:8000/api/:path*"`.

So the same name is a *build* input in one file and a *runtime* input in the
other. Setting it at runtime moves one and not the other, and the two halves of
the app then talk to different backends — server components render the page from
one, the browser's POST goes to the other.

Found by being wrong in the most useful possible way: a **demo** instance's
ticket answered `401 Not authorised`, while the demo backend's own answer, one
curl away, was `403 This is the demo instance. It holds no credentials and has
no execution path.` The 401 was a live-mode backend on the default port
answering a request nobody realised was going there.

**The claim's conclusion was right and its mechanism was wrong, and that is
worse than being wrong outright.** Both versions say "only a trap on non-default
ports locally", so nothing looked incorrect. But the stated mechanism implies a
fix — set `API_ORIGIN` on the instance — that silently does nothing, and the
symptom it does not fix is a page quietly served from the wrong process.

**How to apply:** when a setting is read in a framework config file, it is a
build input, and the artefact is the place to confirm it — `grep` the manifest,
do not reason about the framework. And when one name is read in two places, say
*when* each one is read next to it, because "it defaults to 127.0.0.1:8000" is
true of both and distinguishes nothing. Related:
[[two-limits-on-one-quantity]] — same shape, with time rather than tightness
deciding which reader wins; [[when-a-document-and-the-live-api-disagree]] — the
five-second check that settles it beats any amount of reading.

---

## 2026-08-08 — Sync code that is only ever called from a coroutine

`run_pricing_pass` is sync and `structured_call` is async, so the agent batch
needed one boundary. `asyncio.run` at the seam is the obvious answer, it is what
the design note in `tasks/NEXT.md` proposed, and it is **wrong in production and
only in production**:

```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

`run_once` and `run_quote_pass` are `async def` and call the pricing pass
directly. So on the deployed instance the pass always executes *inside* a
running loop — the one place `asyncio.run` refuses. Every test in the file
called it from sync code and passed. Written as a bare `asyncio.run` it would
have gone green fifteen times, deployed clean, and raised the first time a row
surfaced, which is the rarest event this system has.

**Why the usual instinct misses it:** "is there a loop running?" reads like an
environmental detail, and the answer looks like it depends on the caller. It
does not — the *production* callers are all coroutines and the *test* callers
are all sync, so the test suite systematically exercises the branch that
production never takes. A conditional (`try: get_running_loop()`) would have
made that worse rather than better: two paths, one of them never covered.

**How to apply:** a sync function whose real callers are coroutines has an
async boundary problem even though nothing in its signature says so. Run the
batch on a dedicated thread with its own loop, which behaves identically in and
out of a loop, and **write the test that calls the function the way production
calls it** — here, one test wrapping the pass in `asyncio.run`. Before adding
an async seam, grep for who calls the function and check whether any of them is
a coroutine; the answer is not visible from the function itself. Related:
[[a-test-that-passes-on-the-bug-is-not-a-test]], and
[[an-idle-threadpool-hides-every-thread-safety-bug]] — the same shape, where
the local environment never arranges the condition that production does.

---

## 2026-08-08 — A secret in `.env` makes the test suite behave differently per machine

`backend/config.py` calls `load_dotenv()` at import and every test imports it,
so `ANTHROPIC_API_KEY` was in `os.environ` for the whole suite on any machine
with it set. `AgentConfig.from_env()` reads exactly that. So the first test to
drive a *surfaced* row through the pricing pass called Claude for real — billed,
over the network — on a laptop, and silently skipped the review in CI, where the
key is unset.

Both runs were green. They were asserting different things under one name: one
tested the wiring, the other tested that an unconfigured fleet does nothing.
Verified by removing the guard and running with a deliberately invalid key,
which produced a real `401` from `api.anthropic.com` — the request had left the
machine.

**Why this is not just a test-hygiene point:** it is the environment-measurement
failure this file already records twice (a demo seed that contradicted itself
across a budget-day roll, an assertion comparing against `odds 1800s old` while
CI produced `1802s`), but with a *credential* as the hidden input, so the two
behaviours diverge by who is running rather than by when. A flake announces
itself; this does not.

**How to apply:** an autouse fixture deletes the key for the whole suite, so no
test can reach a paid API by accident — including tests nobody has written yet,
which is the point. Any test wanting a verdict injects a config and a client.
And the seam that leaves the process is a **parameter** on `run_pricing_pass`
rather than a module-level import, so the one leg of that function which costs
money is visible in its signature. The general rule: if a function's behaviour
changes based on a secret it reads from ambient state, a test cannot pin it —
pass the dependency in, and neutralise the ambient state globally.

---

## 2026-08-08 — The schema file runs against databases that already exist

`init_db` applied `schema.sql` and *then* migrated. That works for exactly as
long as every migration only adds columns, and it stops the moment the schema
file declares an index over one of them:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency
    ON orders(idempotency_key);
```

`executescript` runs on **every** open, including on a database that has not
been given `idempotency_key` yet — so this raises `no such column` before
`migrate` gets a chance to add it. On the live volume that is an exception
inside the boot step `entrypoint.sh` runs before uvicorn: a crash loop, on the
one database in this project that cannot be recreated.

**Why no test would have caught it, and this is the part worth carrying:** a
*fresh* database gets the column from `CREATE TABLE`, so the index resolves and
everything passes. The failure needs a database that already exists — which
production always has and a test fixture usually does not. `CREATE TABLE IF NOT
EXISTS` makes the schema file look declarative and idempotent, and it is neither
with respect to anything outside the tables it declares.

It surfaced only because `TestMigration` builds a genuine old database by
*dropping* what the migrations add, and SQLite refuses to drop a column an index
refers to. So the fixture had to drop the index first, which is what put an
existing database in front of the new schema file at all.

**How to apply:** migrate **before** applying the schema file, not after. Then
every `IF NOT EXISTS` in it is a real no-op on an existing database, which is
what it always looked like it was. The two guards worth having beside that:

- A migration test that builds its "old" database by undoing every migration
  across **every version and every table**, read from the migrations table
  rather than hardcoded. The previous version hardcoded v2 and one table, so
  v3 — two columns and an index on a different table — was migrated by code
  that four tests claimed to cover and none of them touched.
- Assert that `schema.sql` and the migrations agree on **indexes**, not only
  columns. An index present on migrated databases and missing from the schema
  file means the constraint holds on the live volume and on nothing a developer
  runs — so the duplicate it exists to prevent is unreproducible exactly where
  someone would try to reproduce it.

Related: [[two-limits-on-one-quantity]] — one mechanism covering half a property
reads exactly like one covering all of it.

---

## 2026-08-08 — An optional safety parameter is a guard that cannot fail

Placement was not idempotent: `client_order_id` is minted per *request*, so two
taps were two ids and two orders, and Kalshi would have accepted both as
distinct. Closing it needs a key that identifies the *intent*, which only the
client can supply — it is the client that knows two taps were one decision.

The tempting shape is an optional field: existing callers keep working, and
anyone who wants protection opts in. That is worse than not building it, because
it looks built. A money endpoint whose safety property depends on the caller
remembering a field protects the callers who did not need protecting and misses
the one that forgot — and nothing anywhere reports the difference.

Making it **required** broke fifteen tests, all mechanically, and that was the
point: the breakage is the proof the endpoint really requires it. Two of those
tests turned out to be posting no body at all.

**How to apply:** when a safety mechanism needs the caller's participation, make
participation mandatory and take the migration cost. If it genuinely cannot be
mandatory, the fallback is not "optional" — it is *reporting*, in the response,
that this request was unprotected. Silence is the failure mode. Same shape as
[[no-result-and-rejected-are-different-outcomes]] one level up: the absence of a
safeguard has to be a stated state, not a default.

And note what the key is **not**: it does not replace `client_order_id`. Those
two deduplicate against different parties — one stops the exchange creating a
second order when we re-send, the other stops us sending a second one at all —
and collapsing them into one value would leave whichever failure the survivor
does not cover silently uncovered.

---

## 2026-08-08 — One signal asked to be both an alert and a status, and oscillated

`discovery` warns when Kalshi sends a `competition_scope` it does not price.
Two repairs, each correct about the defect in front of it, each recreating the
other's:

1. One unknown scope produced one warning **per market** — twelve identical
   lines for one series. Fixed by deduplicating on `(series, scope)`.
2. A process-lifetime dedupe means a long-running runner warns once at boot and
   then goes quiet, which reads as *"the problem went away"*. Fixed by clearing
   the set at the top of every pass.

Together they are repair 1 undone. Measured on the live instance: **98 of the
100 lines in the log buffer** were this warning — 94 distinct series, and not
one of them a sport (`KXFED`, `KXWMT`, `KXTGT`, AP polls, draft picks). A quote
pass re-emits the entire set **every fifteen seconds** while the window is open.

**The cost was not the volume, it was what the volume displaced.** Three claims
in the session handoff were "never observed in production", two of them boot
lines — `[migrate] /data/live.db already at schema v3` and `API starting:
instance_mode=live`. They were unreadable because 98 copies of a warning about
Walmart comparable-sales markets had pushed them out of the buffer. The log had
stopped being able to answer questions about the thing it was logging.

Both halves were individually defended in prose, in comments four lines apart —
the same tell as [[deduplicating-the-record-made-the-record-unusable]], where a
dedupe was right about the record and silently wrong about freshness.

**Why it oscillated rather than converging:** one signal was carrying two jobs
with opposite cadences. "This scope exists and we do not price it, add it to
`FIXTURE_SCOPES`" is a **developer action item** — it cannot change within a
process, and repeating it is pure noise. "How many unknown scopes did this pass
see" is **operational state** — it has to be present every pass or its absence
is ambiguous. No single emission rate is right for both, so every adjustment to
the rate improved one job and broke the other.

**How to apply:** when a log line keeps getting its frequency retuned, the line
is doing two jobs. Split it by *kind*, not by rate: identity is named once per
process, count is printed every pass and **printed at zero**. The zero is
load-bearing — it is what preserves the worry that motivated the per-pass reset,
so dropping the repeats does not hide the problem. Same rule as
[[no-result-and-rejected-are-different]] one level up: there the question was
whether something belongs in a rejection log at all, here it is whether the
thing in the log is an event or a reading.

Two things found in the same sitting, both worth carrying:

- **The test asserted the defect**, again. `test_each_pass_reports_again`
  required the second pass to warn again, and it was written *from* the
  reasoning in repair 2. It is [[a-test-that-passes-on-the-bug-is-not-a-test]]
  in its commonest local form — the test and the code came from one mental
  model in one sitting.
- **Deduplicating for the life of a process makes the dedupe cross-test state.**
  Two tests using the same series then have their assertions decided by
  collection order, and only the loser fails. An autouse fixture in
  `conftest.py` resets it, for the same reason the one beside it removes
  `ANTHROPIC_API_KEY`: a test whose result depends on an input it does not
  supply is measuring the environment. Verified by making it non-autouse and
  watching two tests go red.

---

## 2026-08-08 — The counter you were told to watch was filtered out at zero

`PassCounts.as_dict()` drops falsy fields to keep the pass line readable, with
an `ALWAYS_REPORT` allow-list for the ones whose zero is the answer. The two
agent-fleet counters carried this comment:

> Both are structurally zero while `surfaced` is zero, which is the whole
> history of this project so far — **reported anyway**, because the day they are
> not is the day the agent fleet starts costing money and blocking bets.

They were not in `ALWAYS_REPORT`. So the fields declared "reported anyway" were
dropped by `if v` in **exactly the state the comment was written about**, and
the live pass line carried neither key. "The fleet has never run" could only be
*inferred* from `surfaced: 0` — which is the inference the fields exist to
replace.

The dangerous case is not the all-zero one. It is `skeptic_reviewed: 2` with
`skeptic_blocked` absent: "reviewed two rows and blocked nothing" and "the field
was filtered out" render as the same line, and blocking is the half that stops a
bet. A money-relevant zero and a missing key must never look alike.

`scoring.py` has the identical mechanism and gets it right, because it was
corrected after a live pass showed 14 lines stored and 0 scored with no way to
tell which branch it took. The knowledge was in the repo, one module over, and
the second instance did not inherit it — [[a-stored-age-rendered-as-a-current-one]]
and [[an-idle-threadpool-hides-every-thread-safety-bug]] are the same shape: a
comment explaining one instance of a hazard is evidence the hazard is
understood, not evidence it has been handled everywhere.

**How to apply:** when a serialiser filters on truthiness, the allow-list is the
real specification and the prose beside a field is not part of it. Grep every
field whose comment claims it is always reported and check it is actually in the
list. And test the *pair*, per [[the-zero-that-means-no-measurement]] — one
assertion that the zero survives, one that an ordinary empty stage is still
filtered, or the first passes against a serialiser that has abandoned filtering
altogether.

---

## 2026-08-08 — A filter's vocabulary is not the field's vocabulary

Before writing the settlement parser, 44 markets were captured off the live
exchange. The first thing the capture said:

    GET /markets?status=settled    ->  42 markets, every one status: "finalized"
    GET /markets?status=finalized  ->  HTTP 400, "invalid status filter"

The word you must send and the word you get back are **different words**, and
each is rejected where the other is required.

The obvious parser — `if market["status"] == "settled"` — matches zero markets.
Not "sometimes fails": never matches, on any market, forever. And the symptom is
`settled: 0`, which is exactly what a correct pass reports on a day when nothing
has finished. A dead code path whose output is indistinguishable from a quiet
one, which is [[the-websocket-path-was-dead]] rebuilt in a new place.

Three more from the same 44 rows, each of which a reasonable person would have
guessed wrong:

- **`closed` is a durable third state**, not a step towards settlement. Two
  markets closed 2026-02-03 and still carry no result six months on. "The game
  is over" is not "the outcome is known", and a pass that conflates them either
  hangs or invents a loser.
- **`result` is `""` when unknown, never null** — so `if not result` reads a
  live market as a settled one. [[kalshi-sends-0-0000-not-a-missing-field]]
  again, on a different field.
- **`expiration_time` is not a settlement instant.** It sits three days after
  `close_time` on the sample game. `settlement_ts` is the real one, present on
  42/42 finalized markets and absent on the closed ones.

And one that confirmed a rule this repo already had, by measurement:
`last_price_dollars` is `0.9900` or `0.0100` on **42 of 42** settled markets.
`CLAUDE.md` warns that a settled market's last price has converged on the
outcome; that is now a number rather than an assertion.

**How to apply:** the standing rule is *capture the payload before writing the
parser*. What this adds is where to point the capture: **at the states the code
will branch on**, not at the state that happens to be available. Every other
fixture in this repo holds only `active` markets, 247 of them, and not one of
them could have said anything about settlement — a fixture directory can be
large, real, and completely silent about the branch you are about to write. Ask
which distinctions the new code turns on, and check the capture contains both
sides of each.

Corollary: when an API takes an enum as a filter *and* returns one in a field,
they are two vocabularies until proven otherwise. One request settles it.

---

## 2026-08-08 — Adding a NOT NULL column silently disarms every `INSERT OR IGNORE`

Schema v4 made `settlements.order_id` `NOT NULL`. `seed_demo.seed_history`
inserted into that table with `INSERT OR IGNORE` and no `order_id`. So from that
commit the seeder wrote **zero settlements** while returning
`{"settlements": 400}`, and `mart_calibration` — which joins settlements — went
quietly empty.

The full test suite stayed green. `dbt build` stayed green, because an empty
mart is a legal mart. The count in the output said 400.

This file already carries the lesson (`INSERT OR IGNORE will happily ignore your
fixture`) and it was read at the start of the same session. Reading it did not
help, because the defect was not written here — it was **created at a distance**,
by a schema change in another file that turned a working insert into a no-op
without touching it.

**How to apply:** the rule is not "avoid `OR IGNORE`", which was already known
and already written down. It is a mechanical check with a trigger:

> When adding a `NOT NULL` column to an existing table, grep for
> `INSERT OR IGNORE INTO <that table>` and `INSERT OR REPLACE INTO <that table>`
> across the whole repo, including seeders and tests. Every one of them is now
> a silent no-op.

`OR IGNORE` converts a schema mismatch into a plausible success, so the blast
radius of a `NOT NULL` is every writer that uses it — and those writers are
usually the ones nobody re-reads, because they "just seed fixtures".

And the test that catches it has to assert the **rows**, never the returned
count. The count was produced by the same loop that failed to insert, so it
agrees with the bug perfectly. Same shape as
[[computing-the-right-statistic-and-then-ignoring-it]]: two numbers from one
path, and the flattering one is the one on screen.

---

## 2026-08-08 — Recovering structure by parsing free text, in a boot path

`_MIGRATIONS` steps carry a tuple of SQL statements. Five separate readers
recovered the index name each statement creates with

    statement.split("EXISTS", 1)[1].split("ON", 1)[0].strip()

which is correct for `CREATE UNIQUE INDEX IF NOT EXISTS <name> ON <table>(...)`
and for nothing else. It held while every statement anyone had written was an
index creation.

The first step that is not — v4 rebuilds a table, so it carries `DROP TABLE IF
EXISTS settlements` and `ALTER TABLE settlements_v4 RENAME TO settlements` —
breaks all five. One of the five is `scripts/migrate_db.py`, which
`entrypoint.sh` runs **before uvicorn, under `set -e`**. Verified by restoring
the old parser and running it: `IndexError`, exit 1. That is a crash loop on the
volume holding the evidence record, caused by adding a line to a table in a
different file.

This is the third instance of one shape in this repo, and naming the shape is
the point:

| Derivation | Broke when |
|---|---|
| `.dockerignore` allowlist, maintained by hand | the entrypoint ran a second script |
| index name, parsed out of SQL | a migration did something other than an index |
| exposure's list of *safe* statuses | a seventh status was added |

Each was a **derivation of structured facts from an unstructured source**, right
for every member of the class that existed when it was written.

**How to apply:** declare, do not derive. The migration now carries `indexes`
(names it must leave behind) and `undo_statements` (how to restore the previous
shape); nothing parses SQL. The general test is: *if the class this code
enumerates gains a member, does the code fail loudly or quietly do the wrong
thing?* When the answer is "quietly", and the code runs at boot, the answer is
also "crash loop".

Corollary specific to migrations: a step that is not additive is not idempotent
for free. Create-drop-rename replays safely at every interruption **except**
after full success, where it recreates the temp table and drops the real one.
The guard is a column whose presence means the step has landed — and the test
that matters runs the migration twice over a database holding a row, because
every other arrangement passes either way.

---

## 2026-08-09 — A comment before the last column breaks `DROP COLUMN`

Adding `clv_horizon_hours` to `recommendations` turned **72 tests red** with

    sqlite3.OperationalError: error in table recommendations after drop column:
    incomplete input

The column was fine. The `--` comment above it was not. `ALTER TABLE ... DROP
COLUMN` does not edit a catalogue — it **rewrites the stored `CREATE TABLE`
text**, removing the column's definition and leaving everything else, comments
included. Drop the *last* column and what remains is

    clv_scored_ms  INTEGER,
    -- Which anchor produced `clv_tenths` ...
    );

a trailing comma followed by prose, which will not reparse.

It only bites on the final column, because anywhere else the next definition
absorbs the dangling comment. And it only surfaces in a repo whose migration
tests build an "old" database by *dropping* what the migrations add — which this
one does deliberately, so the fixture cannot drift from what the old version
actually was. A codebase that kept an archived schema file would never see it.

**How to apply:** keep explanatory comments *above the group*, not immediately
above the last column, in any table a migration may drop from. The general form
is worth more than the SQLite detail: **`DROP COLUMN` is a text transformation
on your schema file, so anything in that file that is not a column definition is
a hazard.** Same family as [[the-schema-file-runs-against-databases-that-already-exist]]
— `CREATE TABLE IF NOT EXISTS` and `DROP COLUMN` both look declarative and both
manipulate stored text.

---

## 2026-08-09 — Three guards, three green disable-checks, three missing tests

Moving the CLV horizon added four guards. One went red on the disable-check.
**Three stayed green, and none of them was the usual cause.**

`tasks/lessons.md` already lists three reasons a disabled guard leaves the suite
green: the test does not exercise it, *nothing* exercises it, or the behaviour
comes from somewhere else. All three here were the first — and each was invisible
for a different, specific reason:

| Guard disabled | Why nothing caught it |
|---|---|
| `score_recommendations` stops writing `clv_horizon_hours` | every fixture set the column *itself*, so the production writer was never exercised |
| the gate stops filtering on the horizon | no fixture had **two** horizons in one database, so the filter could not change any outcome |
| the v5 migration stops clearing the old scores | nothing ran that `UPDATE` at all |

The pattern under all three: **a new column arrives with fixtures that set it by
hand, and hand-set fixtures make the code that sets it in production
unobservable.** The fixture and the writer produce the same rows, so every
assertion downstream passes either way — and the fixture is the one people write
first, because it is what makes the other tests go green again.

The gate one is the sharpest and generalises furthest. A filter is only testable
against data it would *exclude*. Every fixture in the repo scored every row at
one horizon, so `WHERE clv_horizon_hours = :horizon` was a no-op on every input
it had ever seen — indistinguishable from a working filter, exactly as
[[the-zero-that-means-no-measurement]] describes for thresholds.

**How to apply:** when a change adds a column, write the tests in this order —
(1) the production writer sets it, (2) a reader that filters on it is given a row
that must be *excluded*, (3) the migration that backfills or clears it is run.
Then update the fixtures. Doing it the other way round, which is the natural
order because the fixtures are what unbreak the suite, produces three guards that
cannot fail.

And note what the disable-check was worth here: the suite went from 1,296 green
tests to 1,301, and the five that appeared are the only ones testing the change
that was actually made.

---

## 2026-08-09 — A fixture that omits a new column reports the code refusing

Three separate gate-arming fixtures needed `clv_horizon_hours` after ADR 0011.
None of them failed in a way that said so:

- `test_quote_refresh` and `test_execution`: **60 tests returned HTTP 423**, gate
  locked. That is the code correctly refusing to arm real money on no evidence.
- `test_alerts`: the digest reported **zero scored games**, which is the honest
  answer when nothing is scored.

Both symptoms are *the system working*. Nothing anywhere said "this row was
written without the column the reader requires"; the row simply stopped counting,
and every consumer reported the resulting absence faithfully.

This is the third time this file has recorded a version of it — the `armed_db`
that armed the gate from `suggested_contracts = 0` rows, the `INSERT OR IGNORE`
that wrote no `kalshi_markets` row at all, and now this. The constant is that
**an incomplete fixture degrades into a valid negative result**, and a valid
negative result is the one state nobody investigates.

**How to apply:** a fixture that exists to put a system into a *positive* state
should assert it reached that state, in the fixture, not leave it to the tests
downstream. `armed_db` should check the gate is actually open before yielding;
a digest fixture should check the digest counts what it seeded. Then a missing
column fails at the fixture with the reason attached, instead of thirty tests
away as a refusal that looks deliberate.

---

## 2026-08-09 — The population was 962; the logs showed 94, and nobody compared the two

Three sessions characterised the unknown-`competition_scope` population from
`flyctl logs`: *"94 distinct series, none of them a sport — `KXFED`, `KXWMT`, AP
polls, draft picks."* Reassuring, load-bearing, and drawn from a sample nobody
knew was a sample.

Measured against the live exchange instead (`scripts/measure_unknown_scopes.py`)
the population is **962 (series, scope) pairs across 317 scopes**, and **227 of
them sit in leagues this project prices**. The exclusion is still correct —
every one is a future, an award, or a period/prop market, so no game-level
market is being dropped — but that is a different fact from the one on record,
and it was true by luck rather than by the reasoning given.

**The tell was on the screen the whole time.** The same log line carried
`unknown_scopes=962`, computed in the process, four lines under 94 warnings. Two
counts of one quantity, disagreeing by an order of magnitude, printed together
and never read against each other. This is
[[computing-the-right-statistic-and-then-ignoring-it]] with the roles reversed:
there the correct statistic sat beside a contradicting verdict; here it sat
beside a contradicting *sample*, and the sample is what got quoted.

**Why the 94 was not a tail.** The 962 warnings were emitted inside ~90ms, into
a stream whose visible buffer is 100 lines. Fly's log pipeline dropped ~90% of
the burst — and took the neighbouring `discovery:` summary with it, a line
emitted immediately afterwards by working code that simply never arrived. So:

- **`flyctl logs` is not a tail, and absence is not evidence of non-emission.**
  The summary line was verified to emit locally, verified unconditional in the
  source, and proven to have run by its own return value being reported one line
  later. It still was not in the stream. Anything concluded from a line *not*
  appearing is unfounded.
- **A burst damages lines that have nothing to do with it.** The cost of a noisy
  warning is not only its own noise; it is every neighbour it evicts or drops.
  The two boot lines this project has been trying to read for three sessions were
  never merely "pushed out" — they were competing with a 962-line burst.

**And the dedupe that was blamed was working perfectly.** The check the handoff
asked for was "count the warnings; expect zero". The count came back 94, which
reads as the failure branch. It was not: every one carried a single timestamp
from the first pass, and the next pass added none. A count taken from a lossy
buffer cannot distinguish "re-emitted" from "still sitting there" — the
discriminating evidence was the *timestamp*, not the count.

**How to apply:** three rules, in order of how much they would have saved.

1. When a log line reports a count of the same thing the log lines themselves
   enumerate, **assert they agree**, or at least read them together once. A
   process-computed count is evidence; a line count from a log stream is a lower
   bound and nothing more.
2. **Size a "warn once" before shipping it.** "Once per process" is a rate, not
   a volume. `_WARNED_SCOPES` was correct and its cardinality was never
   measured; one line per pair, once, is 962 lines. The fix is aggregation —
   one line per process naming the scopes, with the ones in priceable leagues
   named and the rest counted, because the action item is per *scope* and only
   live for a league we can devig.
3. **Characterise a population from the source, not from the report.** One
   unauthenticated walk of `/events` — free, no odds credits — answers in two
   minutes what three sessions inferred wrongly from a log buffer. Related:
   [[a-true-measurement-licensed-a-false-conclusion]], which is the same shape:
   a real observation promoted to a claim broader than what was observed.

**Corollary, found while fixing it.** The `no occurrence_datetime` warning four
lines away was per *event* and undeduplicated — the identical flood, one branch
over, latent because Kalshi happens to populate the field today. A comment
explaining one instance of a hazard is evidence the hazard is understood, not
evidence it has been handled everywhere; see
[[an-idle-threadpool-hides-every-thread-safety-bug]] for the same sentence
about connections. Deduplicated per series, with the per-pass count kept on the
summary line so silence still cannot mean "it went away".

**And the harness had the same disease on its first run.** `measure_unknown_
scopes.py` walked `/events` without `with_nested_markets`, so it reported
`no_commence_time=167` and zero priceable events against a production pass that
finds 167 and warns about neither. A measurement harness must issue the *same
request* production issues, or it is measuring a different system and will
manufacture findings about it. Related: [[a-window-resize-is-not-a-viewport-change]].

---

## 2026-08-09 — The counter that decides the project was behind an auth wall

The gate needs 300 `actionable` games. That number had been zero for the
project's life, and it was readable only through an authenticated endpoint —
so the one counter that decides whether this project can ever reach a
conclusion was the one nobody could see. Four passes of circumstantial evidence
(`recommendations: 4, suppressed: 4`) had accumulated without anyone being able
to check the obvious follow-up: *suppressed by what?*

Printing it took one log line and answered the question on the first pass:

    actionable=0 of 300, no_edge=161, suppressed=265;
    stale_odds=256, too_few_books=73, no_market_width=73,
    edge_within_method_noise=4

**And the answer was not the one the evidence suggested.** "Every row is
suppressed" reads as a miscalibrated guard. It was `stale_odds` at ~97%, which
is the 16-credit odds budget — an *upstream resource limit* — surfacing as a
suppression statistic three layers downstream. Had the number stayed invisible,
the natural next move would have been to loosen a suppression threshold, which
would have manufactured edges into the record while leaving the real constraint
untouched.

**How to apply:** if a threshold gates the whole project, its *progress counter*
belongs wherever the project's health is already read — for a hosted service
that is the log stream, not an endpoint needing a credential the operator keeps
in one place. Ask "who can read this number, and from where?" when the guard is
written, not when it has been zero for a month. Related:
[[the-population-was-962-the-logs-showed-94]] — same session, same failure:
the operational state existed and could not be seen.

Two corollaries worth keeping, both about reading such a line:

- **Co-occurring reasons are one population, not two.** `too_few_books=73` and
  `no_market_width=73` are identical because a single-book consensus has no
  width to measure — the causal link is already in this file. Two labels on one
  cause doubles the apparent size of the problem.
- **A reason breakdown does not partition its rows.** Reasons are comma-joined
  per row and counted individually, so they sum above the row count. It answers
  "how often did each rule fire", never "what share of rows did this explain".

---

## 2026-08-09 — Sampling the wrong pages proves absence with total conviction

For two days this repo recorded that no combo *price* could be obtained without
`POST .../lookup`, which creates a market on the exchange and therefore needed
the user's permission. The permission was given and never used. The premise was
wrong: Kalshi's own users mint provisional combination markets by tapping legs
in the app, `GET /markets` returns them with `mve_selected_legs` and a live
quote, and the joint price was readable for free the whole time.

What made the wrong belief robust was that it is *nearly* true, and that the
evidence for it was collected in the one way that could not find the exception:

    5,000 consecutive open markets in one series -> 6 min 48 s of created_time
    ~700 provisional markets minted per minute, /markets returns newest first
    8.8% carry an ask; 0.18% carry a bid; the quote decays within ~2 minutes

So **paging depth-first is guaranteed to find nothing.** Page six is already two
minutes stale, and everything past it is dead by construction. Three separate
walks — 1,200 markets, then 5,000, then 6,000 — each returned zero two-sided
quotes and each felt like more evidence for the same conclusion. They were the
same non-observation repeated at increasing cost.

The population had to be accumulated over *time*: re-read the newest page every
minute and collect what is fresh. 26 rounds of that produced 2,092 quoted
combinations from the same endpoint that had just produced none.

**Why it is not simply "I sampled badly":** the sampling axis and the decay axis
were the same axis, and nothing said so. Depth in a cursor walk *is* age here.
A search whose ordering is correlated with the property being searched for
cannot report absence, however much of it you do.

**How to apply:** before concluding a venue does not offer something, ask what
determines the order of the thing being walked, and whether the target's
lifetime is shorter than the walk. If it is, the walk measures your own latency.
And when a walk returns zero, widening it is the *least* informative next move —
change the axis instead. Related:
[[a-true-measurement-licensed-a-false-conclusion]], which is the same
combination product and the same shape one level up: a true measurement about
`/markets` promoted into a claim about what exists.

Corollary, and it is the same rule this file already has about zeros:
`active_quoters` is `[]` on all 14,240 published collection legs, while those
same leg markets are two-sided with 21,247 contracts of open interest. The field
is not a liquidity signal. An empty list from an endpoint means "this field said
nothing", never "there is none" — and the reading "0 of 13,806 legs quoted" had
been carried for two days as though it were a fact about liquidity.

---

## 2026-08-09 — Run the control before believing the estimator

Inverting a combination's quoted joint probability into an implied correlation
is the measurement `core/correlation.py` refuses to guess. The first sample was
one-sided — nearly every combination quotes an ask and no bid — so the obvious
move was to invert at the ask and call it an upper bound, which is true and
sounds careful.

The control says it is useless. Cross-game legs are near-independent, so their
true rho is 0 and whatever the method returns there is its own bias:

    cross-game, TWO-SIDED, n=12    rho at bid -0.135   mid -0.033   ask +0.137
    cross-game, ask only,  n=168   rho at ask +0.243   sd 0.235   max +0.853

**At the mid the method recovers the answer** — median −0.010 where the truth is
zero — and the bid and ask bracket it almost symmetrically. So the estimator is
sound and the ask-only variant of it is not.

The part worth carrying is *why* the ask-only version is unusable, because the
tempting fix is wrong. Its bias is large, and a large known bias can be
subtracted off. Its bias has **sd 0.235**, which cannot. A same-game rho drawn
from that population would be indistinguishable from the combination's margin,
and it would have arrived labelled "upper bound" — a caveat that reads as rigour
while the number underneath it means nothing.

Note also what the control cost: nothing. Cross-game combinations were 214 of
the 229 measurements — the overwhelming majority of the sample was the part with
no signal in it, and that is what made it a control rather than a waste.

**How to apply:** when a method is going to produce a number nobody can check,
find the population where the answer is already known and run it there first.
Report that population *first* in the output, so every later figure is read
against it. And when the control shows bias, look at its **spread** before
reaching for a correction — a bias you cannot subtract is a refusal, not an
offset. Related: [[computing-the-right-statistic-and-then-ignoring-it]], and
[[synthetic-data-that-is-right-on-the-mean-and-wrong-on-the-variance]], which is
this same error with the roles of mean and variance reversed.

---

## 2026-08-09 — Two paths pinned by a test agreed, and were both wrong

`order_exposure_dollars` (Python, for the ticket's "this takes you to $X") and a
SQL `SUM` (for the cap that later refuses it) were two implementations of one
quantity, held together by `TestOneOrderSumsToWhatItContributes`. They agreed on
every input.

They also both omitted the fee, while `size_position` spent the cap at
`effective_price`, which includes it. So the cap was consumed at one price and
accumulated at another, and every order left the portfolio ~2% more exposed than
the number the next order sized against. Systematic, one-directional, and in the
unsafe direction.

**A test that two paths agree cannot see a defect they share.** This file
already says "don't test that two paths agree, delete one of them", and the
reason given there was drift. This is the stronger reason: agreement is
evidence about consistency and no evidence at all about correctness, so the
pinning test converts a duplicated bug into a *reassuring* duplicated bug.

**And the deferral reasoning was wrong on its own terms.** Three ADRs recorded
that fixing it "needs a fee column on `orders`" and was not worth a migration.
No column was needed: `count` and `limit_price_tenths` were already stored and
are exactly what `calculate_fee` takes. What actually blocked it was that the
fee is a maximum across candidate models with a per-order rounding step and
therefore **not expressible in SQL** — so the obstacle was the duplicate itself,
restated as a schema problem. Deleting the SQL path removed both at once.

**How to apply:** when a cost is deferred across several documents, re-derive
the cost rather than quoting the previous deferral. And when two paths compute
one quantity, ask what they would *both* have to get wrong for the pinning test
to stay green — then check that specific thing, because it is the only failure
the test is blind to.

---

## 2026-08-09 — The fourth wrong wire key, and the cheap test that finds all of them

`KalshiRestClient.orderbook` read `payload["orderbook"]`. The envelope Kalshi
sends is **`orderbook_fp`**, and with `or {}` behind the lookup the method
returned an empty book for every market on the exchange — including one with
21,256 contracts of open interest and a two-sided quote — reporting nothing.

That is the fourth instance of one shape in this project's short life:

| Read | Sent | Returned |
|---|---|---|
| `data["yes"]` (predecessor) | `yes_dollars_fp` | 0 levels, always |
| `multivariate_event_collections` | `multivariate_contracts` | `[]` |
| `product_metadata` scope `"game"` | `"Game"` | 6 events of 24 |
| `payload["orderbook"]` | `orderbook_fp` | `{}` for every market |

Every one returned something **empty, plausible, and typed correctly**. None
raised. The prose rule against this was written after the first, followed for
some endpoints, and skipped for the next three — so "capture the payload before
writing the parser" has now failed as a defence three times, and it needs a
mechanical check rather than more resolve.

**The check: for every function returning a collection, assert against a real
capture that it comes back NON-EMPTY.** Not that its fields parse — that its
length is greater than zero. Every one of the four failures dies instantly to
that one line, and none of them died to anything else, because the wrong key
produces a perfectly well-formed empty collection that satisfies any assertion
written about its *contents*.

The corollary is where this one was actually caught, and it was luck: **a liquid
market reported an empty book.** An output that is empty where the input is
obviously not is worth one minute of suspicion, even mid-way through unrelated
work. The finding came from a probe looking for a market with a genuinely empty
book, which failed to find one and returned `{}` for a market with 21,000 open
contracts — two facts that cannot both be true.

Note what *limited* the damage, and that it is not a defence: `orderbook()` had
no callers. `tests/test_has_callers.py` exists because code with no caller is a
plan rather than a feature, and this is the other half of that — an uncalled
function is also an untested one, and it will be wrong on the day it is first
used. Related: [[code-with-no-caller-is-not-a-feature]],
[[the-websocket-path-was-dead-and-611-tests-said-otherwise]].

---

## 2026-08-09 — A frozen counter is not evidence of a stuck mechanism

`no_edge` held at **exactly 177** for ten hours and twenty-odd passes on the
live instance. The diagnosis written up from it was that the sweep scheduler
only fires 45–15 minutes before a kickoff, so most passes price against odds
that have aged out — with three options costed and a decision escalated to Joe.

The scheduler was fine. **Today's first kickoff in any of the six in-scope
leagues was 16:15Z, and the frozen interval ran 05:51Z to 15:45Z.** There was
not one fixture on the slate for the whole of it. The counter did not move
because nothing asked it a question.

Every symptom was consistent with the wrong story. `stale_odds` dominated the
suppression summary, `sweep_decision` said "no sweep" on every pass, and
`events_linked` and `fair_prices_written` sat at 16 and 32 all day. All true,
all exactly what an empty slate produces, and none of it distinguishes "the
scheduler is refusing to fire" from "there is nothing to fire at".

**Why it was persuasive:** it arrived pattern-matched to a lesson this file
already had — [[two-limits-on-one-quantity]], the odds budget relaxed 16 → 400
and the next constraint binding in silence. That shape was real and had happened
twice. Recognising it made the conclusion feel confirmed rather than proposed,
and nobody checked the cheapest thing: *were there any games?*

**How to apply:** before diagnosing why a counter is not moving, establish that
its inputs existed over the interval you measured. Ask what the denominator was.
A rate computed over a window with an empty denominator is not a low rate, it is
no measurement — the same error as [[one-observation-recorded-thirty-times]]
seen from the other end, where the count was of uptime rather than of evidence.

The check that settled it cost one free API call to a public schedule and a call
into the repo's own `plan_sweep_slots`: today's slate generates **six** windows
covering **18 of 19 games**, all after 15:45Z. That is now
`scripts/measure_slot_coverage.py`, so the question is re-measurable on a winter
slate rather than re-argued. `docs/adr/0014` records the decision.

**And the corollary that generalises further:** an explanation which predicts
every observation you have is not thereby a good explanation. Ask what it
forbids. "The scheduler is too restrictive" and "there are no games today" made
identical predictions about every counter on the log line, and were separated
only by a fact neither of them mentioned.

---

## 2026-08-09 — A guard written to prove a property the code cannot violate

`analyse_combo_domination.py` filtered its sample on the gap between when a
combination's joint was read and when its legs were read, refusing any pair more
than 90 seconds apart. It printed, as the first line of every run:

    Contemporaneous filter: kept 2116 of 2116; dropped 0

That is a tautology. The harvest took **one** `time.time()` at the top of each
round and stamped it on the joint *and* on every leg, so the gap was identically
zero for all 2,116 rows. The filter could not fire. Its threshold was chosen,
documented and tested, and there was no input the harness could produce that
would trip it.

Worse, the accompanying test built a 60,000 ms gap **by hand** and asserted the
filter caught it. It passed. So the guard had been "verified by watching it
fire" on a value the system was structurally incapable of emitting.

Two more failures rode along on the same stamp:

- The round stamp was taken at the round's **start**, and a round took ~84s, so
  ages were understated by up to a round. **69 combinations reported a negative
  age** — observed before they were minted.
- Those 69 rows then fell through every age bucket (the first required
  `age_ms >= 0`) and never reached the `unknown` line. **3.3% of the sample
  vanished from the table built to catch confounds**, silently.

**Why it survived:** the guard, its threshold, its test and its output line were
written in one sitting from one mental model — the shape this file already has
three entries about. What was new is that the usual defence failed too. "Verify
a guard by disabling it and watching the test fail" does not help when the guard
is checked against synthetic input, because breaking the guard still turns the
synthetic test red. The disable-check confirms the *test* exercises the guard,
not that the *system* can reach it.

**How to apply:** for any guard on a measured quantity, ask **what real input
would trip this, and has the system ever produced one?** Then assert the answer
in the data rather than in a fixture — here, that the observed gaps are not all
identical. A distribution with one distinct value is the signature: if every row
returns the same number, the number is a property of the code, not of the world.

Corollary, and it is the cheap version of the check: **print the distinct count
next to any filter's output.** "dropped 0" reads as reassurance; "dropped 0 of
2116, all gaps = 0" reads as a bug. Related:
[[a-test-that-passes-on-the-bug-is-not-a-test]],
[[the-zero-that-means-no-measurement-passes-every-threshold]].

---

## 2026-08-09 — The control that cannot reach the confound it was built for

The same analysis reported domination rate bucketed by combination age, under
the heading **"THE STALENESS CONTROL"**, with the note that a stale-quote
artefact must grow with age while a real property stays flat. The table:

    <1m   n=2015  12.4%      2-5m  n=0
    1-2m  n=32     9.4%      5-10m n=0      >10m n=0

Read as written, that is a flat rate and staleness is refuted. It is nothing of
the kind. The harvest only ever sees **quoted** markets, and a combination quote
on this venue lives one to two minutes, so no older combination is ever sampled:
observed ages ran 9s to 71s. **The confound being tested lived at 39 minutes.**
The control's entire domain sat inside the region where the effect could not
appear, and its three empty cells were structural absence printed as evidence of
flatness.

This is [[a-frozen-counter-is-not-evidence-of-a-stuck-mechanism]] one turn
further on: there, a rate was computed over an interval with no inputs; here, a
control was computed over a range that excluded the hypothesis. Same question
unasked — *could this measurement have seen the thing it is looking for?*

**How to apply:** before believing a control, state the range over which the
effect would appear and check the sample covers it. An empty bucket is a
different object from a bucket of zeros, and a table that renders them
identically will be read as the second. If the sample cannot cover the range,
say the control cannot run — do not print it with a confident heading and let
the reader infer flatness from three empty cells.

---

## 2026-08-09 — Two clocks that never overlap, so the test cannot be run

ADR 0012's addendum proposed a decisive ~20-call test: re-read a combination and
the leg it echoes, and see whether the ask moves tick-for-tick with the leg. It
was pre-registered properly, run twice, and returned `n = 2` move events and
then `n = 0` — **too thin to answer**, at ~210 calls.

The reason is structural and no amount of effort fixes it. A combination's quote
is readable for **tens of seconds**; its matched leg's price ticks on a scale of
**minutes**. Across both runs, **45 of 50 matched legs showed exactly one
distinct cost** for the whole window. Polling 5x faster produced *fewer*
qualifying events, not more, because the constraint is the overlap of two
lifetimes, not the sample rate.

The pre-registration is what made this readable rather than embarrassing. It had
fixed, in advance, that `n` counts **move events**, and that a matched leg with
one distinct value is a *defect of the window* while a combo ask with one
distinct value is a *result*. Without that asymmetry written down first, "the
ask never moved" would have been reported as evidence of no coupling — a
confident verdict from a measurement that could not have produced any other
outcome.

This is the sibling of the control that could not reach its confound, one entry
above. There, a control's range excluded the effect. Here, the two observations
the test requires exist in disjoint time windows.

**How to apply:** before designing an "A moves with B" test, write down the
timescale on which A changes and the timescale on which B is *observable at
all*. If they do not overlap, the test does not exist at any cadence — say so
and design a different one, rather than spending the budget discovering it. And
when a design can only return one answer, that is not a finding: naming which
outcome would be a defect, in advance, is what stops it becoming one.

---

## 2026-08-09 — A risk control can be a threshold on the wrong quantity entirely

`min_order_contracts = 10` was defended for the project's life on a true
premise: under Model A the fee rounds up on the whole order, so a small order
pays a rounding penalty a large one amortises away. Measured, that penalty is
real — 0.88c per contract on a single contract at 20c.

**And the sizer was already paying it.** `effective_price` charges the fee a
*single* contract would pay, which is the most expensive per-contract fee any
size pays -- by proof, not enumeration: Model A is `ceil_cent(a*N)` and
`ceil_cent(a*N) <= ceil_cent(a)*N`, while Model B's per-contract fee does not
depend on `N`. (The first write-up of this cited an enumeration over sizes
1-200. An enumeration cannot establish a claim about all sizes, and
`measurement-skeptic` said so.) `full_kelly_fraction > 0` holds exactly when
`fair > price + fee(1)`, and `EV(N) > 0` holds exactly when
`fair > price + fee(N)/N`, so monotonicity makes the first imply the second at
every size. The minimum was **refusing positive-EV orders**, not preventing
negative-EV ones.

Below about a $250 bankroll it closed the 50c band -- where this strategy trades
-- and it did so by returning a plausible zero that no screen explained. **Not
every order**: 204 of the 999 asks survived, all at 0.1-10.1c or 88.1-98.8c.
That is worse rather than better. The wings are where the fee is largest as a
share of stake and where the devig methods disagree most, so the guard did not
switch the counter off -- it restricted the evidence to the least believable
prices on the board, which produces a record instead of a silence. The first
two write-ups of this said "every order" and had to be corrected.

**Why it survived:** the justification was sound and was checked. Nobody asked
the next question — whether the code downstream of the justification had already
handled it. A comment naming a real hazard reads as evidence the hazard is
covered, and it is only evidence that someone knew about it.

**How to apply:** for any threshold, state the quantity it is protecting and
then go and check what that quantity actually does across its whole range. Two
things follow, and the second is the one that generalises:

- **A price-independent constant standing in for a price-dependent quantity is
  wrong at every value but one.** The penalty here is 0.00c at 50c and 0.88c at
  20c; a single number cannot be right for both.
- **When removing a guard, do not replace it with another guard — assert the
  property that makes it unnecessary.** The first draft of this change replaced
  the minimum with a whole-order EV re-check inside `size_position`. Given the
  monotonicity above, that check can never fire: it was decoration with a better
  name. What shipped instead is a test asserting per-contract cost never rises
  with order size, so a future fee model that broke the property turns a test
  red rather than letting a negative-EV order out quietly. Related:
  [[a-test-that-passes-on-the-bug-is-not-a-test]],
  [[two-limits-on-one-quantity]].

Corollary on removal: a deleted setting still present in an environment must
**raise**, not be ignored. `MIN_ORDER_CONTRACTS` was load-bearing and wrong, and
silently ignoring it would leave everyone's mental model intact.

---

## 2026-08-09 — A measurement can be switched off by a number that is not about measurement

The gate counted `suppressed_reason IS NULL AND suggested_contracts > 0`.
`suggested_contracts` is sized against the operator's bankroll. So the size of
the deposit decided what counted as **evidence**, and at the real bankroll of
$100 quarter-Kelly sizes under one contract across the 50c band -- confining the
counter to the far wings, making the 300-game floor unreachable in practice, and
leaving the Gate screen's "0 of 300, keep recording" true, unfalsifiable, and
pointing at the wrong thing.

Nothing would have errored. No test was red. The one screen reporting progress
would have described a dead counter as progress.

**Why it hid:** every part was correct. Sizing correctly reflects the bankroll.
The predicate correctly identifies rows the strategy would bet. The floor is
correctly 300. The defect is in the *join* — a measurement definition reaching
through a money quantity — and a join has no line number to review. Same shape
as [[code-with-no-caller-is-not-a-feature]]: the missing thing is not in any
file.

**How to apply:** ask of every counter, **"what could change this number that is
not about the thing it measures?"** If the answer is anything — a deposit, a
deploy, an uptime, a config edit — the counter is measuring that too. Here the
fix is a second column scored against a reference profile fixed in code, so the
record is a property of the strategy rather than of the account, and the two
questions ("what may I buy" / "did the strategy have a bet") stop sharing one
number.

Two supporting rules that fell out of it, both worth carrying:

- **Fixing it in code, not in config.** A configurable reference bankroll
  rebuilds the same trap one level up.
- **A screen must say which question its number answers.** "Actionable" reads as
  "you can buy this". At a small bankroll it does not mean that, and the Gate
  screen now says so in words. Related:
  [[computing-the-right-statistic-and-then-ignoring-it]].

---

## 2026-08-09 — An enumeration is not a proof, and "every" is the word to distrust

`measurement-skeptic` audited a finding that was good news and returned five
factual corrections. Every one is the same shape: **a true observation restated
one notch stronger than the evidence carried.**

    written                                        true
    ------------------------------------------     ---------------------------
    "verified exhaustively, sizes 1-200"           an enumeration over a range,
                                                   attached to a claim about
                                                   all sizes
    "monotonic"                                    maximised at N=1; at 30c the
                                                   per-contract fee runs
                                                   2.00, 1.50, 1.67
    "refused every order the tool can produce"     204 of 999 asks survived
    "the ranges intersect by a tenth of a point"   up to 3.0c of room at 98c
    "break-even is roughly $300"                   $250, closed form
    "the two regimes stay separable"               the fingerprint did not
                                                   include the parameter
    "all three caps were inherited"                two were; one was set

None of these changed the decision. Three of them changed what the decision
*rests on*, and one — the intersection — inverted the argument: the guard was
not switching the counter off, it was restricting the evidence to the wings,
where the fee is largest as a share of stake and the devig methods disagree
most. Producing evidence from the least believable prices is worse than
producing none, and the tidier "refuses everything" story hid that.

**Why it happens:** a summary is written after the work, from memory of the
result rather than from the output. Every one of these started as something
measured and became a sentence with a stronger quantifier. The direction is
never random — it is always toward the cleaner story, because a clean story is
easier to write and reads as more confident.

**How to apply:**

- **Distrust "every", "always", "never", "structurally", "by construction".**
  Each is a universal claim. Before writing one, ask what would have to be true
  across the *whole* domain and whether that was checked or assumed. If the
  evidence is an enumeration, say the range and say it is an enumeration.
- **An enumeration over a range cannot support a claim about the range's
  complement.** Either state the bound that was checked, or find the proof. Here
  the proof was two lines (`ceil_cent(a*N) <= ceil_cent(a)*N`) and strictly
  better than the 200-point sweep it replaced.
- **When a guard "refuses everything", ask what it does *not* refuse.** That set
  is the finding. It was 204 asks, all at the wings, and it is the part that
  matters.
- **Audit the good news, and audit the write-up, not just the number.** The
  measurements here were right. The prose about them was wrong five times.
  Related: [[a-pooled-number-is-not-a-finding-until-the-parts-agree]],
  [[computing-the-right-statistic-and-then-ignoring-it]].

---

## 2026-08-09 — A schema comment is code that nothing executes

`schema.sql` said `edge_tenths REAL NOT NULL, -- gross, before fees`.
`engine.py:161` assigns it `edge_after_fees_tenths(...)` and the Board renders
it as `"+1.7c after fees"`. **The column had been net of fees since it was
written, and the file that is the contract for every downstream query said the
opposite.**

The 2026-08-07 audit found it (item 41) and that session's status line recorded
41 as *closed*. It was not. Item 41 was a bundle of nine small findings; some
were fixed and this one was not, and a bundle marked closed is
indistinguishable from a bundle that was.

**Why it is worse than a wrong comment elsewhere.** A wrong docstring on a
function is checked against the function every time someone reads the code under
it. A column comment has no code under it. Nothing imports it, no test loads it,
and the writer lives in a different file — so the only thing that would catch it
is somebody reading both at once, which is exactly what nobody does while
writing a query. The failure it produces is not a crash: it is a fee-relative
band with the fee subtracted twice, which returns a number, and the number looks
decided.

**Then check the neighbours, because one wrong comment is a sample.** Reading
the rest of the file against its writers found four more, all the same shape — a
comment enumerating a column's domain, drifting from the code that fills it:

| column | comment said | writers actually produce |
|---|---|---|
| `kalshi_markets.price_structure` | `cent \| deci_cent \| tapered_deci_cent` | `linear_cent`, `center_half_edge_half_cent`, `deci_cent` — two of the three listed appear in **no** captured payload, and the value on the large majority of rows was not listed at all |
| `unmatched_events.reason` | `no_alias \| no_counterpart \| commence_skew` | free-text sentences; `no_alias` and `commence_skew` are written by nothing, so `GROUP BY reason` yields one group per sentence |
| `kalshi_markets.market_type` | `... \| future \| prop` | `moneyline \| spread \| total \| team_total`; `future`/`prop` unwritten, `team_total` unlisted |
| `meta.schema_version` seed | `'1'` | `db.SCHEMA_VERSION = 6` overwrites it; the file declares a version it is not |

Four of the five are *enumerations*. That is the tell: an inline `-- a | b | c`
is a claim about a whole domain, written once from intent, and every value added
to the parser afterwards lands somewhere else.

**How to apply:** treat an enum comment in a schema as an assertion with no
test, and check it the way this file already says to check a filter — enumerate
the values the writer can emit and diff the two sets. Prefer naming the
producing symbol (`discovery._SUFFIX_TO_MARKET_TYPE`) over restating its values,
because a pointer cannot drift. And close a bundled audit item part by part, or
the parts that were skipped inherit the tick. Related:
[[test-the-filters-exclusions]], [[code-with-no-caller-is-not-a-feature]].

---

## 2026-08-09 — A guard standing behind a stricter guard is decoration

`read_market_result` refuses a settled outcome in three steps: the status must
be `finalized`, the `result` must be one of `yes`/`no`, and it must agree with
`settlement_value_dollars`. The disable-check found the middle one **passing on
its own break** — replacing `if result not in RESULTS: return None` with
`result = market.get("result") or "no"`, which fabricates a loss for every
market whose outcome is unpublished, left the whole file green.

Nothing was wrong with the code. The test deformed a captured market by setting
`result = ""` while leaving `settlement_value_dollars` in place, so the
*cross-check* caught the break and the membership test never had to. Every test
that could have failed was standing behind a stricter one.

**Why it happens:** a break is written by editing one line, but a test is
written by deforming one field. Defence in depth means several lines can catch
one deformation, and the outermost one gets the credit. The suite then reports
health for a guard that has never once been exercised — and it will keep doing
so until the day a payload arrives that only that guard would have refused,
which is exactly the day it matters.

**How to apply:**

- **Verify each guard against a payload only that guard refuses.** Here that
  meant *removing* `settlement_value_dollars` rather than contradicting it —
  which is also the more realistic shape, since the key is absent, not empty,
  on all 289 unsettled markets in the two captures.
- **Run the disable-check per guard, not per function.** A function-level break
  is caught by whichever check fires first and tells you nothing about the rest.
- **A layered refusal needs one test per layer.** If two layers cannot be told
  apart by any input, one of them is genuinely redundant — delete it or say in
  the comment that it is belt-and-braces, rather than leaving a reader to
  believe it is load-bearing.

---

## 2026-08-09 — A once-only WRITE behind an unbounded READ is not once-only

`record_result` was guarded `WHERE result IS NULL`, which is a correct
once-only write and was described as one. The **read** that produced the work
had no matching bound. A market Kalshi called `finalized` and this code refused
to parse — a 50/50 tie, most likely — stayed NULL, so it stayed in the result
set of `markets_awaiting_result`, so it was re-queried and re-refused on every
pass. Two markets on a 900s cadence is 192 identical ERROR lines a day, forever,
plus an `errors` list embedded in the merged pass line that grows with the
number of stuck markets.

The same shape appeared twice more in one file. A market that never finalizes
was re-queried forever because the query had a lower age bound and no upper one.
And the mitigation in the docstring — `ORDER BY started_ms DESC`, so a stuck
market "drifts to the back of the queue" — only *reorders*: with no cap, nothing
is ever dropped, so on live (where the cap was unset) the ordering bought
literally nothing.

**How to apply:**

- **Idempotence is a property of the read and the write together.** For any
  "this only happens once", name the query that stops producing the row. If
  nothing stops producing it, the write is once-only and the *work* is not.
- **If it recurs on every pass it is a state, not an exception.** Report it as a
  level (a `_total` gauge on the pass line) and log the exception once, at the
  transition. A logging rate is a property of the caller: the same line was
  correct at 900s and a flood at 22s without one character changing.
- **A queue needs an exit as well as an entrance.** Ordering, prioritising and
  de-duplicating do not bound anything. Only dropping does.
- **Fix the consequence, not the refusal.** Refusing to guess a tie is right and
  must not change; a fabricated outcome in a calibration column is a permanent
  wrong answer. What was wrong was what the refusal *cost*.
- **When you bound coverage, the dropped population gets its own counter.**
  Never the one that also holds the routine state — "still unresolved" covering
  both a game in the 7th inning and an event stuck for six months cannot show a
  leak by construction. Name the oldest dropped row on every line, so the
  population is identifiable from a phone.

---

## 2026-08-09 — A break that is equivalent to the original proves nothing

Disabling twenty guards in turn, one stayed green: the new `AND
COALESCE(m.status, '') != ?` that keeps a refused market out of the queue. The
guard was fine. The *break* was `!= COALESCE(?, '__never__')` — written to look
like a deformation while binding the same parameter to the same comparison. It
was the original expression with more characters.

This is the previous lesson's failure one level up. There, a guard was masked by
a stricter guard downstream; here, a guard was masked by a break that never
touched it. Both produce the same reading — "green, therefore healthy" — from a
test that was never run against the thing it claims to test.

**How to apply:**

- **A disable-check has its own failure mode: the no-op break.** Before
  believing "stayed green, therefore decoration", read the deformation back and
  ask what input now behaves differently. If the answer is "none", the check did
  not run.
- **Prefer breaks that are obviously not the original**: delete the clause and
  replace it with a tautology (`AND (? IS NOT NULL)` still consumes the bound
  parameter), or return a constant. Subtle edits to a condition are exactly
  where an accidental identity hides.
- **Script the disable-check.** Twenty guards by hand invites the shortcut of
  editing whichever line is easiest to type, which is how the no-op gets
  written. Related: [[a-guard-standing-behind-a-stricter-guard-is-decoration]].

---

## 2026-08-09 — "It probably fits in one page" is a fact you can just measure

`markets_for_event` sent no `limit` and read exactly one page, so it silently
took whatever default the server applies. The reasoning that this was safe —
sports game events carry two to thirty markets, well under any plausible page —
was correct, and untested against the wire. Three free unauthenticated GETs
settled it in under a minute: `/markets` with no `limit` returns **100** rows,
not the 200 the repo's own `DEFAULT_PAGE_LIMIT` would have suggested; `limit` is
capped at 1000 (`limit=1001` is HTTP 400); and `?event_ticker=` **ignores
`limit` entirely**, returning all 82 markets of `KXWC-30` even for `limit=1`,
with an empty cursor.

So the code was safe, by a mechanism nobody had guessed, with the largest event
on the exchange at 82 against an assumed ceiling of 200 that is really 100.

**How to apply:**

- **A page-size assumption is one free GET away from being a measurement.** The
  cost of checking is far below the cost of the failure, and the failure here
  was invisible: a truncated tail would have been counted "still unresolved" and
  re-queried forever, which is a silent leak, not an error.
- **The repo's own default constant is not the server's default.** Ours was 200;
  the server's is 100. A constant named `DEFAULT_PAGE_LIMIT` invites the reader
  to believe it describes the remote end.
- **Paginate even when one page is enough.** With an empty cursor the loop
  returns after a single request, so correctness under a future change costs
  nothing today — and going through `paginate` also picked up the
  renamed-envelope refusal the hand-rolled `payload.get("markets") or []` did
  not have.

---

## 2026-08-09 — A sample whose strata do not overlap the target proves nothing, at any `n`

**Pattern:** a measurement fixed its thresholds, denominators, statistic and
stopping rule before collection — and did not fix its **sampling frame**. The
selection rule was "the first 20 eligible rows in discovery order". The series
list it discovered from was an ordered `tuple` whose pages were concatenated, so
the sample filled entirely from the first series and could never reach the
second — while the population the rate was meant to inform was **66% the
second**. The same rule imposed no leg-count restriction, while the target was
100% two- and three-leg by construction, because the harvest's own analyser
refuses anything larger. **17 of 20 sampled rows had a leg count that occurs
zero times in the target.** The structurally comparable subsample was `n = 3`.

Nothing errored. Nothing looked short. The run returned exactly 20 rows and a
95% interval, and the write-up transferred that interval to a population it had
not touched.

**Why it happens:** pre-registration discipline concentrates on the *analysis* —
the parts a bad actor could tune after seeing data. The sampling frame feels
like plumbing, so it gets a sentence rather than a table. And the failure is
silent by nature: an under-sampled stratum and an absent one look identical in
the output, because both are just "rows we have".

Both defects were checkable, at zero cost, against a JSON file **already
committed to this repo**. Nobody ran the comparison, because nobody thought of
the sample as a thing that could be wrong.

**How to apply:**

- **A pre-registration must fix the sampling frame, not only the analysis.**
  Name the strata and the expected share of each. "The first N eligible rows" is
  a rule that satisfies almost any specification while sampling almost anything.
- **Print the sample's composition beside the target's, before any rate.** Make
  it the first block of output. A cell at zero voids the transfer and must be
  visible without being looked for.
- **Interleave, never concatenate, when drawing across strata.** Concatenation
  plus a head-N is a silent single-stratum sample. With a round-robin an
  under-supplied stratum shows up as a *short* sample instead of an *absent*
  one — which is a failure you can see.
- **Match the target's own eligibility rule.** If the stored population was
  built by a filter, the sample must pass that same filter, or it is a sample of
  something else.
- **"Transfers only if the population is stable" is usually the wrong caveat.**
  Temporal drift is the risk people write down; structural non-overlap is the
  one that actually voids the transfer, and it is checkable today rather than
  arguable forever. Related:
  [[a-pooled-number-is-not-a-finding-until-the-parts-agree]].

## 2026-08-09 — A term that is zero everywhere has an unobservable sign

**Pattern:** a measurement decomposed an observed gap into two terms and wrote
the identity down with the wrong sign — `a + b` where the arithmetic gives
`a − b`, because the quantity is an *ask* and the terms are differences in
*bids*, and `ask = 1 − bid` flips a bid difference on the way in. The formula
went into the pre-registration, into the harness, and into a per-row output line
that printed an equation which did not balance.

It survived reading the output, because the run measured one term as **exactly
zero on every row**. `0 + b` and `0 − b` differ only in the sign of a number
that was being printed anyway, and a zero term has no sign to check. The result
that made the finding clean is the same thing that made the error invisible.

**Why it happens:** sign conventions get checked against an example, and the
example is drawn from the data — which is exactly the case that cannot
discriminate. It is the same defect as an equality anchored at `0.5` in a test
for `1 − p` versus `p`: at 0.5 both conventions agree, so the test named for the
identity cannot see it.

**How to apply:**

- **Test an identity on inputs where every term is non-zero and no two terms are
  equal.** A decomposition test where one term is zero verifies the other term,
  not the decomposition.
- **Never anchor a convention test on a fixed point of the transformation.**
  `1 − p` at `p = 0.5`, a ratio at 1, a difference at 0 — each collapses the
  distinction the test exists to make. Pick a value where each wrong
  implementation yields a *different* wrong answer, and assert they differ.
- **Assert the identity in the code that prints it.** An equation in output is a
  claim, and a reader will trust it rather than add it up. One `assert` before
  the `print` turns an unread line into a guard.
- **When a term comes back exactly zero, ask what that zero is hiding.** A clean
  result suppresses evidence about everything the term feeds into. Related:
  [[a-guard-written-to-prove-a-property-the-code-cannot-violate]].

## 2026-08-09 — A defence built for one axis of a classifier is not a defence for the classifier

**Pattern:** `discovery.classify_series` reads two metadata fields and rejects on
either. One of them, `competition_scope`, had three defences: an explicit
excluded-values set with a reason per entry, an aggregated per-process warning
naming anything unclassified, and a drift test asserting every value in the
captured payloads is classified either way. The other, `competition`, had none —
a league absent from `IN_SCOPE_LEAGUES` was simply gone, with no warning, no
counter and no failing test.

So the failure the scope defences were built for happened again on the field
next to them. `IN_SCOPE_LEAGUES` says `"Pro Football"`; Kalshi spells NFL
preseason `"Pro Football Preseason"`; **48 events and 726 markets** left the
universe in silence. The file's own comment, four lines above the map, already
recorded the identical failure for `"Pro Basketball (W)"` and `"NCAA Football"`.

**Why it happens:** a defence gets built where a bug was *found*, and the bug
was found on one field. The prose then explains that field so well that the
explanation reads as coverage. Nothing in the module says "the other field is
undefended" — absence has no line number.

**How to apply:**

- **When a function rejects on N inputs, count the guards.** If one input has an
  excluded-values map, a warning and a drift test and another has none, that is
  the finding — before any evidence that the second one has broken.
- **A fixture is only a drift test for what it happened to contain.** The
  captured walk had no preseason market, so the scope drift test's league twin
  would have been green throughout the bug. Capture the case, then assert on the
  capture itself so an out-of-season re-capture fails loudly instead of quietly
  ceasing to test anything.
- **Break each guard separately, and break behaviour rather than expressions.**
  Thirteen deformations here, applied one at a time; one stayed green and
  exposed a genuinely missing test — the per-pass count was never asserted to
  *fall*. A break applied alongside another is caught by whichever guard is
  stricter, and a break that rewrites the asserted expression tests nothing.
- **Two different populations can share every identifier but one.** Preseason and
  regular-season NFL share the series ticker (`KXNFLGAME`) and the scope
  (`"Game"`); only the league string differs, and the evidence record stores
  neither the league on the row nor anything else that splits them. Before
  widening a population, find the column that will mark which one a row came
  from — if there isn't one, widening is not a config change. Related:
  [[a-comment-explaining-one-instance-of-a-hazard-is-not-evidence-it-was-handled-everywhere]].

---

## 2026-08-09 — Arithmetic that reproduces to the digit says nothing about its inputs

Three documents were audited in one session. In all three the arithmetic
checked out **exactly** — every cell of a power table, every Wilson interval,
every fee row reproduced to the last digit against the code. And in all three
the conclusion was wrong, because the numbers that came from *outside* the code
were assumed and never labelled as such.

| Document | Internal arithmetic | The input that was invented |
|---|---|---|
| CLV signal-test pre-registration | exact | `sd(half_spread) = 4` tenths — measured later at **0.27**, and provably ≤2.5 |
| Combo E2 | exact | the sampled population, which shares almost no structure with the one it described |
| ADR 0017 Addendum A | wrong, and only found by re-running `size_position` | — |

The half-spread case is the clearest. A correct covariance identity, a correct
multiplication, and a spurious-slope estimate of 0.16 that was **off by ~230×**
— because one factor was a plausible guess. It was labelled "the largest finding
in this document" and made a *blocking* prerequisite. A measurement of the
adjacent quantity was sitting in `docs/adr/0006` the whole time and was neither
cited nor used.

**Why internal consistency is not a check:** every one of these documents was
self-consistent. Recomputing them from their own stated inputs reproduces them
perfectly. The error is upstream of every operation performed, so no amount of
checking the working can reach it, and a document that survives that check reads
as *more* rigorous rather than less.

**How to apply.** Label every number at the point of use as **computed from
code**, **measured from data**, or **assumed** — and count the third kind. If a
load-bearing conclusion rests on one, that is the thing to measure next,
regardless of how reasonable it looks. Before assuming a constant, grep
`docs/adr` and `docs/measurements` for the quantity; this project had already
measured it twice.

Two corollaries earned the same session:

- **A grid is not a sample.** "n=1 on 1,206 of 1,206 points" reads as 1,206
  observations of a 100% rate. It is the domain of a deterministic function on
  an author-chosen grid: there is no denominator of events, and a finer grid
  inflates the numerator without adding information. Say "every point of a grid
  of N" at first use, not three sections later.
- **Prefer a bound to a point estimate when the support is small.** The strongest
  result of the session was not the measured `sd = 0.27`. It was that on a
  two-point support `{5, 10}`, `sd = sqrt(p(1-p))·5 ≤ 2.5` — so the assumed 4 is
  *arithmetically impossible* and no selection of that population, however
  adversarial, can revive the confound. A bound closed the question permanently;
  a point estimate would only have moved it.

Related: [[computing-the-right-statistic-and-then-ignoring-it]],
[[a-true-measurement-licensed-a-false-conclusion]],
[[every-per-cell-guard-can-pass]].

---

## 2026-08-09 — "Read-only" is not a scope boundary; name the environment

A subagent was dispatched to trace which config values the deployed system
actually runs with. The prompt told it what it must not **echo** — no secret
values, no key material — and said nothing about which *machine* it could touch.
It went and looked at the running one: `flyctl secrets list` against live, an
attempted `flyctl ssh console` into the production volume (stopped by the
permission classifier, not by the prompt), a POST of a local auth token to the
live `/session`, and a signed call to the real Kalshi API.

Every one of those was a read. Nothing was mutated, no money moved, no secret
value was printed. The instruction was followed exactly as written, and the
result was still an agent poking production without that having been decided by
anyone.

**Why the usual phrasing fails.** "Read-only" bounds the *verb* and says nothing
about the *object*. And the task itself supplies the pressure: "what does the
deployed system actually execute?" has a correct answer that only the deployed
system holds, so an agent doing the job well will reach for it. Prompting an
agent to determine runtime truth and expecting it to stay local is asking for
two incompatible things and getting the more useful one.

The blast radius here was small. It is not small in general: a read against
production can rate-limit a live credential, trip an alert, consume a metered
budget, or — on a venue like this one — be one wrong flag away from an order.

**How to apply:** state the environment as its own sentence, on the same
footing as the deliverable. *"Everything in this task is local. Do not run
`flyctl`, do not call the live API, do not authenticate to the deployed
instance. If the answer requires production, stop and say so."* Two supporting
rules:

- **A permission classifier is a backstop, not the boundary.** It stopped the
  SSH here and it would not have stopped the other three. Anything relying on
  it to define scope is relying on a list somebody else maintains.
- **"Stop and say so" has to be offered explicitly**, or the agent's only path
  to a complete answer runs through the thing you did not want touched.
  Refusing to answer is not a failure mode an agent will choose unprompted when
  a reachable answer exists.

The directing error is the lesson. The agent did nothing it was told not to do.
Related: [[clamping-is-for-values-you-trust]] — the same shape, in that the
loud, self-announcing refusal is the one worth preserving.

---

## 2026-08-10 — "Unblocked" is a scheduling property, not an evidentiary one

A measurement was promoted to the top of the queue on the argument that it
"needs no actionable row" — i.e. that nothing was in its way. It was ranked
above everything else, a registration was commissioned, and a route to serve it
was put in a deploy bundle.

Then the power calculation was run, for the first time, by the registrar. Closed
form, `4p(1-p)/gap^2` at two standard errors:

    resolve the 0.38-point headroom     69,252 games
    resolve 2.0 points                   2,500 games
    resolve a gross 5-point miss           400 games
    games in the record                       29

**Underpowered by roughly four orders of magnitude, permanently.** The
calculation takes under a minute and is closed-form. Nothing about the answer
required data, a harness, or a deploy — it required asking.

**Why the mistake was available.** "This is unblocked" and "this can answer the
question" are different predicates that feel like the same one when a backlog is
mostly blocked. A blocked queue makes availability scarce, and scarce things get
over-valued. The item genuinely *was* the only one not blocked by the
0-actionable wall. It was also incapable of resolving anything.

The same session had a related near-miss in the opposite direction: the
measurement that *can* settle the question turned out to need **no** statistics
at all — a deterministic bound over rows already recorded, with zero sampling
error. So the ranking was wrong twice over, and both errors came from never
asking what effect size each instrument could resolve.

**How to apply:** before ranking any measurement, compute the smallest effect it
could resolve at the `n` actually available, and put that number in the ranking
argument. If it cannot be computed in a few minutes, that is itself the finding.
Two corollaries:

- **Ask whether the question needs a statistic at all.** A bound over the whole
  population beats an estimate over a sample, carries no alpha, and cannot be
  reversed by more data. Prefer it whenever the claim is "X could not have
  happened" rather than "X happens at rate r".
- **A blocked backlog distorts ranking.** When most work is blocked, the
  unblocked item wins by default rather than on merit. Say out loud which
  property is doing the promoting.

Related: [[cLV-needs-hundreds-of-bets-not-dozens]],
[[a-sample-whose-strata-do-not-overlap-the-target]].

---

## 2026-08-10 — A number quoted from your own project's prose is an assumed number

`tasks/lessons.md` records that the four devig methods spread "1–2 percentage
points". That sentence was lifted into a ranking argument and set against the
0.38-point taker headroom, concluding that the conservative rule was eating
**three to five times** the edge being hunted. It was relayed onward twice
before anyone checked it.

The measurement it came from is sitting in the code, four lines above the guard
that uses it — `core/suppression.py:217-220`:

> Measured on real lines: the four devig methods spread **~0.18 points on an even
> moneyline and ~2.03 on a longshot.**

"1–2 points" was the longshot end quoted as though it were the range. And the
guard's *cost* is mean−min, roughly half the spread. So at 50c, where this
strategy actually trades, the rule costs about **0.24x the headroom** — not
three to five times it. **The conclusion inverted.**

**Why this evades the rule it breaks.** This repo already requires every number
to be labelled *computed from code*, *measured from data*, or *assumed*, and the
third kind counted. That discipline gets applied to numbers arriving from
outside — a paper, a vendor doc, another agent's report. A number found in your
own repo's prose reads as already-vetted, because at some point it was. What
does not survive the copy is the **scope**: the original said which end of a
range it described, and the quotation dropped it.

Note the shape. The original sentence was *true*. Nothing was fabricated. The
error was entirely in the conditions that travelled with it, and a range
collapsed to its worst end always moves the argument in the direction of
whoever is quoting it.

**How to apply:**

- **A number in your own docs is `assumed` until you have found the code or the
  measurement behind it**, in this session. Prior vetting does not transfer,
  because what fails is scope, not accuracy.
- **When a quantity varies over a domain, never quote it without the domain.**
  "1–2 points" is not a fact about devig methods; "0.18 at 50c, 2.03 at a
  longshot" is. If the argument only works at one end of the range, say which
  end and check the population lives there.
- **Distrust the direction.** Both this error and the ranking error above ran
  the flattering way. That is not coincidence — a flattering reading terminates
  the search early, because it feels like an answer. Spend *more* scrutiny when
  a number helps, not less.

Related: [[arithmetic-that-reproduces-to-the-digit-says-nothing-about-its-inputs]],
[[an-enumeration-is-not-a-proof]],
[[a-true-measurement-licensed-a-false-conclusion]].

---

## 2026-08-10 — Tracing a number to code is only half the check

The rule directly above — *a number quoted from your own prose is assumed until
you have found the code behind it* — was followed this session, on the
devig-method spread, and it was **not sufficient**. Two numbers survived the
trace and still failed.

**`2.03 points`.** It traces. `devig(["fav","dog"], [1.11, 7.50]).method_spread("dog")`
returns **2.0304**, and `[2.10, 1.80]` returns **0.1817** — reproducing
`core/suppression.py:217-220` to four figures, on two lines named in
`tests/test_devig.py`. So the citation is real and the arithmetic is right, and
it was about to be used as *the maximum reach of the devig knob* inside a bound.
Two things broke that:

- **The test asserts inequalities, not the value.**
  `TestMethodSpreadDependsOnLineShape` asserts `> 0.6`, `< 0.6`, and
  `lopsided > even`. **Nothing pins 2.03.** This file's own earlier entry says
  "both halves are asserted in `TestMethodSpreadDependsOnLineShape` so the
  framing cannot quietly drift back" — that claim is **wrong**, and it is wrong
  here, which is where a future session goes to check.
- **It is an example, not a maximum.** Swept over two-outcome lines — fair
  favourite 50–99%, overround 1–20% — the spread reaches **3.47 points** on
  realistic slates (favourite ≤ 85%, hold ≤ 6%) and **15.9** at a 20% hold. The
  1.11/7.50 line carries only ~3.4% overround, so 2.03 is not even the worst
  case at its own hold. And the spread is **non-monotone** in lopsidedness:
  1.02/40.0 gives **0.425**, because the additive method clamps.

**`1.94 points, 5.1x` for the maker basis.** Also traces, also real — and it is
the `N = 100` limit, for a system that never sends 100 contracts. The operative
figures are **1.38 and 3.6x**, at `N = 1`.

**And the first correction to it was wrong too, which is the sharper half of
this lesson.** The initial fix said *"ADR 0017 Correction 1 had already fixed 10
contracts as this software's minimum order, so the figures are 1.88 and 4.9x"* —
and `MIN_ORDER_CONTRACTS` had been **retired on 2026-08-09**. `sizing.py:15`
now opens *"There is no minimum order size, because there is nothing for one to
prevent"*, the setting sits in `config.RETIRED_SETTINGS`, and **ADR 0017's own
Addendum A.2 records the removal.**

So the correction cited ADR 0017 §1 Correction 1 while, eleven lines away,
citing ADR 0017 **Addendum A** for a different fact — the very addendum that
retires Correction 1's premise. **A document can supersede itself without
renumbering the passage it supersedes.** Tracing a citation to a document is
therefore not the same as checking whether the document has retired it, and a
correction is not exempt from the rule it is correcting.

**Why the existing rule missed all three.** It asks *does this number exist in
the code?* All did. What it does not ask is *what does the number quantify, over
what domain, and is a test holding it there?* A traced number arrives wearing
the authority of the trace, and the trace certifies existence, not scope.

Note the shape once more: using 2.03 as a bound would have made the bound **too
tight**, producing a zero that was an artefact of an understated knob — the
flattering direction, again, inside a measurement built specifically to resist
it.

**How to apply:**

- **After tracing a number, open the test that supposedly pins it and read the
  assertion.** An inequality is not a pin. `assert x > 0.6` lets `x` be 2.03 or
  15.9 and stays green through the difference that matters.
- **Ask whether the value is an example or an extremum.** If a bound is being
  built on it, a single evaluated point is never enough: sweep the input space
  and take the maximum, or restructure so no fixed constant is needed.
- **Restructuring beats sweeping.** The fix registered here removes the knob
  entirely: instead of choosing a δ and counting rows that clear it, compute the
  per-row **shortfall** and read the count at every δ off one distribution. A
  constant you never have to choose is a constant that cannot be chosen wrong.
- **Check the number's regime against the deployed one**, and check it in the
  code rather than in a document about the code. `N = 100` and `N = 10` are both
  real numbers about a system that sizes at `N = 1`.
- **Read the whole document, not the cited passage.** A corrections section, an
  addendum or a "superseded" note can retire a numbered claim *without
  renumbering it*, so the passage stays quotable and reads as current. Before
  quoting `§1 Correction 1`, search the same file for anything that supersedes
  it. This repo has the pattern in both directions: ADR 0017's Addendum A
  deliberately edits nothing above it, which is right for auditability and
  precisely what makes the stale passage still quotable.

Related: [[a-number-quoted-from-your-own-projects-prose-is-an-assumed-number]],
[[measure-the-style-rule-before-believing-it]],
[[a-true-measurement-licensed-a-false-conclusion]].

---

## 2026-08-10 — A pull can be incomplete while every check on it adds up

`/api/ledger` returned the newest 1,000 of 1,535 rows, so paging was needed
before any whole-table measurement. Adding `offset` alone would have been worse
than leaving it capped.

The route sorts newest-first. A row written *during* a multi-page pull therefore
lands on page 0 and pushes every later page along by one. That is not a rare
race here: **[MEASURED] one `created_ms` on this table carries 84 rows**,
because a sweep writes its whole slate at one instant, and the recorder writes
~500–600 rows a day. Reproduced directly — 120 rows in four pages of 30, with
one 84-row sweep landing between page 0 and page 1:

```
unpinned            returned 120, distinct  90, 30 duplicated,
                    and 84 original rows never returned
pinned to max_id    returned 120, distinct 120,  0 duplicated
```

**The dangerous part is not the corruption, it is that nothing contradicts it.**
Every page reports `returned: 30`. The four pages sum to 120. `total` agrees.
`limit` agrees. Every consistency check the payload is capable of supporting
passes — and the payload was *deliberately* designed to expose slices, carrying
`total` beside `returned` for exactly that purpose. That machinery is blind to
this, because the pull is the right *size* and the wrong *multiset*.

The fix is a snapshot pin: read `newest_id` from page 0 and pass it back as
`max_id`, so `id <= max_id` names a fixed prefix that later writes cannot enter.
`total` must be counted under the same pin, or paging until
`offset + returned == total` walks a target that keeps moving. Immutable by
construction, rather than by hoping the recorder is idle.

A second, smaller thing rode along: `ORDER BY created_ms DESC` is **not a total
order** on this table — 960 of the newest 1,000 rows tie with at least one
other. Measured, it pages consistently today because the planner scans
`idx_recs_created`; the point is that it *happens to*, and adding a join changed
the plan in the same commit. `(created_ms DESC, id DESC)` is total, so the
question stops being about the planner. That half is hardening and is labelled
as such — no corruption was observed, and claiming one would have been the same
overstatement in the other direction.

**How to apply:**

- **Pagination over a table that is being written to needs a snapshot key, not
  just an offset.** `OFFSET` assumes the rows below it do not move. On any
  newest-first ordering, every insert moves all of them.
- **Before trusting a multi-page pull, assert `len(set(ids)) == total`.** It is
  one line, it is the only check that catches this, and it is not implied by any
  of `total`, `returned`, `limit` or their sums.
- **When adding a field so a defect becomes visible, ask what the field cannot
  see.** `total` was added to make a slice detectable and it worked — and it
  reports 1,535 just as happily for a pull holding 90 distinct rows as for one
  holding 120. A detector that answers a nearby question is exactly the kind
  that gets trusted for this one.
- **Order by a total order whenever a query is paged.** A tiebreak costs a sort
  and removes the query planner from a correctness argument.

Related: [[one-observation-recorded-thirty-times]],
[[the-zero-that-means-no-measurement-passes-every-threshold]],
[[a-captured-fixture-that-no-test-loads-is-decoration]].

---

## 2026-08-10 — A reachability guard has to run in both directions

The joint bound was built to close this project's central question. It was
pre-registered, amended, implemented with 100 tests and 24 verified
deformations, and it **could not have returned its decision value.** The run had
one possible outcome before it started, and nobody noticed until it produced it.

The instrument: set every conservative choice simultaneously to its most
generous alternative — loosest devig, cheapest fee model, maker basis — and
count actionable rows. Zero would mean *"one could not have been found here"*,
which no future data can reverse. That reasoning is sound.

The registration then discovered, correctly and exhaustively, that stacking the
cheapest fee model onto the maker basis gives a fee of **exactly zero** at all
999 prices and every order size: Model B's maker multiplier is 0.015, and
`0.015·P(1−P) ≤ 0.00375` rounds half-up to zero cents per contract. It recorded
this as a *simplification* — the bound "reduces to one subtraction" and becomes
size-invariant, which is true and genuinely useful.

**It is also the moment the instrument stopped being able to fail.** At a zero
fee the count is just *"how many rows have a positive gross edge"*. Measured on
1,000 rows: 258 clear, and **213 of those 258 have a gross edge smaller than the
~2c fee they would actually pay.** They clear only because the bound deleted the
venue's cost — and the venue's cost advantage *is* the premise under test.
Setting cost to zero does not test the premise; it removes it.

**The guard that existed pointed the wrong way.** The registration has an
explicit reachability rung: *"if `K` is zero even at the loosest δ, treat the
harness as suspected defective, because a ladder that is zero everywhere cannot
be told from a broken harness."* That is a real guard against a false negative,
and it was written deliberately. Nothing guarded the symmetric case. The rung
returned **984 of 1,000** — an instrument whose sanity check clears 98% of the
record and whose decision condition requires 0.

**Why it survived every process this project has.** Three reviewers, a
pre-registration, an amendment that found a genuinely different defect in the
same ladder, and a test suite in which every guard was disabled and watched to
go red. None of them ask *"can this measurement come out the other way?"*, because
each is scoped to a piece: the tests check the code computes what the
registration says, the registration checks the statistic is not chosen after the
data, the amendment checks the thresholds. **Falsifiability is a property of the
instrument as a whole and has no owner among them.**

Note the shape, which is this file's [[two-limits-on-one-quantity]] rotated into
a new dimension: relaxing the fee bound made a *different* bound — the
falsifiability of the design — start binding, silently, with no change in any
symptom. Every individual number stayed correct.

**How to apply:**

- **Before running a measurement, state what result would falsify the
  hypothesis, and then check that result is arithmetically reachable given the
  parameters actually chosen.** Not "is it plausible" — *reachable*. Here it was
  not, and one line of arithmetic on a counter already in the record would have
  shown it.
- **Reachability guards are directional. Write both.** "If it always returns 0,
  suspect the harness" needs its twin: "if it never returns 0, suspect the
  bound." A ladder whose top rung clears 98% of the record is announcing that
  its bottom rung is the only informative one.
- **When a relaxation turns out to be extreme, treat that as a finding about the
  instrument, not a convenience.** "The generous fee is exactly zero" was
  recorded as making the arithmetic simpler. The same sentence, read as *"our
  bound assumes the venue is free"*, is a stop-the-line.
- **A bound must dominate the thing it bounds and still be able to bind.** The
  fix is to bound against the cheapest *realisable* alternative, not the limit
  of the relaxation. A bound nobody believes is a bound nothing can fail.

**And the epilogue that matters more than the instrument.** The failed bound was
not the session's finding. The same pull showed that all 45 rows carrying a
positive net edge under the deployed fee are **suppressed** — zero unsuppressed,
zero actionable, across 8 games — and that the largest apparent edges are a
consensus fair of `0.49999999999999994` on a game the market prices 84/16, from
a single contributing book. The guards and the edge computation agree about
which rows are garbage. That is a coherence result, it needed no bound, and it
is better evidence than the instrument was built to produce. **When an
instrument fails, look at what the data said anyway.**

Related: [[two-limits-on-one-quantity]],
[[the-zero-that-means-no-measurement-passes-every-threshold]],
[[every-per-cell-guard-can-pass]],
[[a-test-that-passes-on-the-bug-is-not-a-test]].

---

## 2026-08-10 — The guard that cannot fire on the input it was built for

`edge_within_method_noise` exists to catch edge that is an artefact of
devig-method choice. Its comment says so: *"If they disagree by more than the
edge being claimed, the 'edge' is a statement about method choice, not about the
market."* It is the right idea and it is structurally incapable of firing on the
one input where the edge is **purely** a method-choice artefact.

One book, quoting both outcomes of a two-way market at identical decimal odds.
All four devig methods then agree to ~1e-14, so `method_spread ≈ 1.4e-11`
tenths, and `suppression.py`'s condition

```python
edge_tenths <= 0 or edge_tenths > spread_tenths
```

passes for **any** positive edge whatsoever. The guard reads "the methods agree,
so this edge is trustworthy" — when what actually happened is that there was
only one book, so there was nothing for them to disagree about. **Agreement was
being used as evidence of reliability, and it was really evidence of absence.**

The fair it produces is `0.49999999999999994`, and even that digit is
instructive: nothing defaults to 0.5. `power()` solves for its exponent with
`brentq`, lands one ULP high, and `p**k` rounds to `nextafter(0.5, 0)`;
`conservative_probability` takes the `min` across four methods, three of which
are exact, so it **systematically selects the root-finder's error floor**. The
tell for this bug in any record is the signature `p_multiplicative == p_additive
== 0.5` with `p_power` one ULP below.

The consequence measured on the live record: a 50/50 fair on a WNBA game the
Kalshi book prices **84/16**, producing the three largest `|edge_tenths|` values
in the entire slice (+33.0c, +32.0c, −36.0c). And eight rows that were **fresh,
fillable, and stopped by exactly one threshold** — `min_book_count = 2`, which
has no environment plumbing anywhere and is the code default.

**Two guards that are one guard.** `too_few_books` and `no_market_width` fire on
the identical condition (`book_count < 2` and `len(first_values) <= 1`), so
their row-sets were bit-identical across 1,000 rows — 185 each, symmetric
difference 0. Anything counting them separately double-weights one signal, and
the suppression summary reads like defence in depth when there is one threshold.

**This is [[the-zero-that-means-no-measurement-passes-every-threshold]] one step
further on**, and the repo had that lesson written. There, a one-book consensus
reported `market_width = 0.0` and so passed the width check most easily of all;
the fix made width `Optional`. The *same* single-book state then walked into the
*next* guard and did the same thing to it, through a different field. Fixing the
instance did not fix the shape.

**And no test could have caught it.** The suite's only equal-odds two-outcome
fixture is `(1.95, 1.95)` — one of the values where the defect does **not**
reproduce, because all four methods return exactly 0.5 there and the spread is
exactly 0.0. The values that do reproduce it include 1.82, 1.85 and 1.86:
ordinary h2h prices. A fixture chosen for being "obviously symmetric" landed on
the one symmetric point that is clean.

**How to apply:**

- **For every guard that compares a quantity against a measure of dispersion,
  ask what the dispersion does when the input is degenerate.** Near-zero spread
  makes any threshold of the form `effect > spread` trivially true. The guard
  must refuse on unmeasurable dispersion, not pass — the same
  `Optional`-not-zero rule this repo already applies to `market_width`, applied
  to the *comparison* rather than to the field.
- **Agreement among methods is not evidence when there is only one input.**
  Distinguish "four methods examined the data and concurred" from "there was
  nothing to disagree about". `usable_book_count` distinguishes them, is
  computed at `devig.py:339`, and **is not persisted** — so the live database
  cannot answer which one happened.
- **Count your guards before trusting depth.** Two codes firing on one condition
  are one guard. Check the row-sets, not the names: identical sets across a real
  sample is the test, and it takes one line.
- **Pick degenerate-input fixtures by finding where the defect reproduces, not
  by what looks symmetric.** Sweep the input and choose a value where a wrong
  implementation differs from a right one —
  [[a-test-that-passes-on-the-bug-is-not-a-test]] applied to fixture selection.
- **When a lesson names a mechanism, grep for the mechanism, not the field.**
  "One book cannot disagree with itself" had consequences in at least two
  guards. The first was fixed and written up; the second was still live eleven
  days later.

Related: [[the-zero-that-means-no-measurement-passes-every-threshold]],
[[two-limits-on-one-quantity]],
[[a-guard-that-routes-around-thin-data-into-a-fallback-built-from-it]],
[[code-with-no-caller-is-not-a-feature]].

---

## 2026-08-10 — Count guard families, not guards

`edge_within_method_noise`, `too_few_books` and `no_market_width` read as three
independent checks. They are three readings of **one** question — *do the
sources agree?* — and every one of them is blind to the same input, because
**correlated garbage agrees with itself perfectly.**

Two books quoting a symmetric two-way line produce `fair = 0.5`,
`market_width = 0.0`, a method spread of ~1e-11 tenths, and `reason=None`. All
three guards pass. Not because any is miscalibrated: because a placeholder line
and a genuine consensus are *indistinguishable by agreement*, and agreement is
the only thing this family measures.

The trap is that the obvious fix is a fourth member of the same family. The
first design proposed here was "refuse when dispersion is unmeasurable" — which
fires precisely when `too_few_books` and `no_market_width` already fire (185
rows each over 1,000, symmetric difference 0). It would have added a third name
for one condition and closed nothing, while making the suppression summary read
*more* like defence in depth.

**Why it survived review:** the guards live in one function, are individually
correct, and each has tests. Nothing in the module names the family, and the
suppression log prints codes rather than kinds — so three codes over one
condition render as three signals.

**How to apply:**

- **Before adding a guard, ask what question the existing ones answer.** If the
  new one answers the same question with a different field, it is a synonym.
  Check row-sets on real data, not names: identical sets is the test, and it is
  one line.
- **A blindness shared by a whole family cannot be fixed from inside it.** The
  remedy has to come from a different family — here it turned out to be
  `edge_ceiling_tenths`, an external-reference guard, which bounds a fabricated
  0.5 fair to a 4.0c ask window and **was never justified for that job.** An
  undeclared dependency of that kind is how someone raises a threshold for one
  stated reason and silently widens an unrelated hole.
- **Reachable is not observed, and say which you mean.** The two-book case is
  reachable and has been demonstrated synthetically; it appears in 0 of 15
  events in the one real capture available, and whether it occurs in the live
  record is a separate census. Writing it up as a live bug would have been
  [[a-true-measurement-licensed-a-false-conclusion]] in the other direction.

Related: [[the-zero-that-means-no-measurement-passes-every-threshold]],
[[two-limits-on-one-quantity]],
[[the-guard-that-cannot-fire-on-the-input-it-was-built-for]].

---

## 2026-08-10 — The false reassurance in a comment outlives the code it describes

Three instances in one session, in three different files, all the same shape: a
string asserting a property the code or the data does not have.

| Where | What it claimed | What is true |
|---|---|---|
| `suppression.py:172` | `"book last moved {x}min ago"` | it is the *aggregator's scrape* time; the book may not have repriced in hours |
| `routes.py:594-597` | window_status is *"not a second implementation… the screen is the one that gets believed"* | same implementation, **two different inputs** — the loop passes a hardcoded 900_000, the API passes the env value |
| `odds/client.py` | a `SHARP_BOOKS` under a comment nearly identical to the live one | a **second** set sharing one member of four, read only by a property with no production caller |

The `routes.py` one is the sharpest: it names the exact hazard, avoids the
mechanism it blames (a duplicated implementation), and gets the divergence
anyway through the *arguments*. **Sharing an implementation does not share its
inputs.**

**Why these are worse than no comment.** An absent explanation invites checking.
A confident one terminates the search — and it is the artefact that survives
longest, because prose is not executed, not linted, and not covered. All three
were literally true when written; what rotted was the relationship between the
sentence and its subject, and nothing anywhere fails when that happens.

**How to apply:**

- **When a comment asserts a property, ask what would fail if it stopped being
  true.** If the answer is "nothing", the property needs an assertion or the
  comment needs to stop claiming it. Prefer a **runtime** assertion over a test
  where the divergence is created by deployed configuration: a test comparing
  one hardcoded default to another passes green forever while the live instance
  diverges.
- **Fix a false message even when behaviour is correct, and ship it separately
  from the behaviour change.** The `stale_odds` wording was corrected with no
  change to when the guard fires; the remedy for the underlying scrape-clock
  problem is a queued ADR. Wording is not a lesser fix — it is the part a future
  session reads.
- **Delete a dead duplicate rather than documenting it.** Documenting makes it
  look deliberate. The identifiable victim is whoever edits the dead copy
  believing they changed the live path.

Related: [[code-with-no-caller-is-not-a-feature]],
[[two-limits-on-one-quantity]],
[[tracing-a-number-to-code-is-only-half-the-check]].

---

## 2026-08-10 — Six built-never-called modules is a process gap, not a run of bad luck

`CLAUDE.md` cites four. Add `elo.py`/`backtest.py` (shipped into the container,
imported by nothing) and now `odds/client.py`'s `SHARP_BOOKS` + `is_sharp`, and
the count is **six**.

The count is the argument. One orphan is an oversight; six is a process that
does not check. And the detector this repo built for it —
`tests/test_has_callers.py` — has **opt-in coverage**: `MUST_HAVE_CALLERS` is a
hand-maintained list, so absence from the list is indistinguishable from having
a caller. A detector you must remember to register with does not catch the thing
you forgot.

The `is_sharp` case shows the specific cost, because it was worse than inert. It
sat between two `@property` neighbours as a bare `def`, so `if quote.is_sharp`
bound a method object and was **truthy for all 30 books** — "prefer the sharp
books" would have meant "prefer all of them", which is the unweighted average
wearing a rigorous name. Its own docstring recorded that it had no caller, and
it was left in anyway. **A landmine documented as a landmine is still armed.**

Worse, the *guard* was on the dead copy: `tests/test_odds.py` asserted the sharp
set was small and excluded FanDuel, while `runner.SHARP_BOOKS` — the set actually
passed to `consensus_devig`, which discards a median of 26 of 29 books — had no
assertion at all.

> **ANNOTATION 2026-08-10 — `26 of 29` is a fixture figure, not a live one.**
> It is measured on `tests/fixtures/odds_mlb_h2h_spreads_totals.json`, captured
> 2026-08-07T13:49:22Z, which overlaps the live record on **0 of 1,564 rows**
> (minimum gap 5.65 hours). The claim it is doing work for here — that
> `SHARP_BOOKS` filters heavily and so deserved a guard — **is unaffected**, and
> that guard was the right call. Only the size is borrowed. See
> [[a-borrowed-number-must-overlap-the-population]] and ADR 0021 §7.2's
> annotation of the same date.

**How to apply:**

- **Grep for callers before believing a feature exists, and before writing a
  sentence about it.** If every hit is `tests/` or a seeder, it is a plan.
- **Check which copy your guard is guarding.** A test on the unused definition
  is worse than no test: it produces the feeling of coverage over the path that
  cannot hurt you, and none over the one that can.
- **When a docstring says "nothing calls this yet", that is a finding, not a
  note.** Delete it or wire it. Leaving it is how the count reaches six.

> **ANNOTATION 2026-08-10 — the count is NINE, and it was six only because the
> detector was counting wrong.** A census that enumerated the population instead
> of consulting a list found **nine module-level dead**, four partially dead, and
> a symbol-level tail. The lesson's argument gets stronger, not weaker: the
> number was low *because* the counting method was the thing being criticised.
> Two mechanisms, both recorded in **ADR 0022**:
> [[an-allowlist-cannot-report-what-is-missing-from-it]] and
> [[a-detectors-production-must-be-the-deployments-production]].

Related: [[code-with-no-caller-is-not-a-feature]],
[[a-captured-fixture-that-no-test-loads-is-decoration]],
[[a-test-that-passes-on-the-bug-is-not-a-test]].

---

## 2026-08-10 — CI cost is job count and trigger breadth, not job duration

The account hit 90% of its 2,000 included Actions minutes. The instinct is to
look for a slow job. There wasn't one: CI's real compute was 303 minutes and it
billed **562**.

GitHub rounds **every job** up to a whole minute, independently. So three jobs
averaging 40 seconds bill 3 minutes, while one job taking two minutes bills 2.
The Secret scan ran for **8 seconds** and billed 60. Splitting work into
parallel jobs buys wall-clock at a price denominated in whole minutes per job,
and that price is invisible in every dashboard that reports duration.

The second multiplier is trigger breadth. `ci.yml` fired on `branches: ["**"]`
with no `paths` filter and no `concurrency` block. This repo's output is
overwhelmingly prose — ADRs, `docs/measurements/`, `lessons.md`, `NEXT.md` — so
a commit touching nothing but markdown paid for a full pytest run and a cold
`next build`. And with agents pushing 1.0–1.4 minutes apart against a ~2 minute
CI, runs were routinely obsolete before they finished, each billing in full.

**Why:** duration is the number that gets watched, and it was the one number
that was fine. A cost model that rounds per job means the cheapest jobs are the
most wasteful ones, which inverts the usual intuition that small = cheap. Nobody
looks for waste in an 8-second job.

**How to apply:** when a CI bill is the question, count **billable jobs ×
triggers**, never total runtime. Compute it from job `started_at`/`completed_at`
rounded up per job — the `/timing` endpoint's `total_ms` reports `0` here and
will quietly tell you everything is free. Before adding a job for parallelism,
price it: a job that finishes in 10 seconds costs the same as one that takes 59.
And set `concurrency` with `cancel-in-progress: true` on any workflow an agent
triggers, because agents push in bursts and humans don't.

The corollary that outranks all of it: **a private repo bills these minutes and
a public one does not.** Before optimising a CI bill, check whether the repo
needs to be private at all — the cheapest run is the one that is free.

Related: [[a-scanner-that-only-reads-the-current-push-leaves-history-unverified]].

---

## 2026-08-10 — A scanner that only reads the current push leaves history unverified

The secret scan has run on every push since the repo was created, and it is
genuinely good — gitleaks, plus project-specific greps, plus a canary self-test
that proves the patterns still match. It is easy to read that record as "this
repo has been continuously verified clean."

It hasn't. `gitleaks-action` scans **the commits in the push that triggered
it**, and the project-specific greps run over **the current tree**. Neither has
ever swept full history. A key committed and deleted in the same session is
invisible to both, and remains fully retrievable by anyone who clones.

That distinction is worth nothing while the repo is private and worth
everything the moment it goes public — and going public is irreversible for
anything already committed, because forks and caches survive re-privatizing.

**Why:** the green checkmark answers "is the tip clean?" while the question
being asked at flip time is "has anything *ever* been committed?" Those look
like the same question and are not, and the difference is only detectable by
reading what the scanner actually scans.

**How to apply:** before any visibility change, run gitleaks with
`--log-opts="--all"` as a distinct, deliberate step — not as a re-run of CI.
Then hunt by hand for the credentials that have no greppable prefix: per
[[credentials-in-query-strings]] the Odds API key leaks through httpx URL
logging into query strings, so it hides in committed logs and fixtures where no
`BEGIN`-style header will find it. Header-pattern greps prove very little;
absence of a match is not evidence of absence. If something surfaces, **rotate
it first** — rewriting history is not a substitute for rotation, because you
cannot know who already cloned.

---

## 2026-08-09 — The census must apply the same filter the storage path applies

A published claim read *"**440 of 440** book+event triples carry one identical
`last_update` across h2h, spreads and totals"*, offered as proof that the stamp
is a scrape clock rather than a reprice clock. It was corrected twice in one
session, **both times in the same direction**, and the second correction is the
one worth keeping.

| Denominator | What it counted | Why it was wrong |
|---|---|---|
| 440 | every book+event pair | 120 quote **one** market — unanimity is vacuous |
| 335 | pairs with ≥2 **raw payload** keys | counts `h2h_lay`, which is **never stored** |
| **320** | pairs with ≥2 **priceable** markets | the population that could have refused |

Unanimity is 100% under all three. Nothing about the finding moved. What moved
is whether the denominator contained rows **capable of refuting the claim** —
and twice it was padded with rows that were not.

The first padding is the familiar one: agreement with oneself is not evidence
of agreement. The second is subtler and is the actual lesson. The census read
the **raw API payload**, while the quantity it was arguing about — `odds_age_ms`
— is computed only from markets in `PRICEABLE_MARKETS`. `h2h_lay` is in
`EXCLUDED_MARKETS` and is discarded at ingest, so a lay price's stamp cannot
contribute to `odds_age_ms` at all. Fifteen pairs sat on the wrong side of the
vacuous boundary purely because of it.

**Why it hides:** both numbers are true statements about *something*, both are
100%, and both move in the flattering direction — a bigger denominator reads as
stronger evidence. Nothing in the output announces which population was
counted, and the difference (335 vs 320) is small enough to look like a
rounding disagreement rather than a scope error.

**How to apply:** when a census is offered as evidence about a **stored or
derived** quantity, the census must filter its input **exactly as the
production path does**, and it should do so by *importing* the filter rather
than restating it. `scripts/census_odds_stamps.py` imports `PRICEABLE_MARKETS`
from `odds/client.py` for that reason — a re-typed constant is a copy that
drifts, and the drift is silent. It also prints the rejected 335 beside the 320,
because a discarded alternative that stays visible cannot be quietly
reintroduced by the next reader.

Corollary, and it generalises past filters: **before quoting `N of N`, ask what
the rows that are not in N would have had to do to break the claim.** If the
answer is "nothing — they could not have disagreed", they are not evidence and
must leave the denominator. Related:
[[a-true-measurement-licensed-a-false-conclusion]] (the number was true and its
scope was wider than what was measured),
[[the-zero-that-means-no-measurement]] (an unmeasurable case wearing a
measured case's representation).

---

## 2026-08-10 — A borrowed number must overlap the population you spend it on, in *time*

A calibration measured on a captured fixture was quoted, one document later, as
a property of the live record. The fixture was captured **2026-08-07T13:49:22Z**;
the record's earliest odds observation is **2026-08-07T19:28:12Z**. **Zero of
1,564 rows overlap it. Minimum gap: 5.65 hours.**

The measurement was correct. Its label was correct — the registration wrote
`[MEASURED FROM DATA — tests/fixtures/odds_...json]` immediately above it, and
also wrote down that the capture is mature MLB and "structurally cannot contain
an opener". **The next document dropped the label and kept the number.**

**Why this variant is nastier than the usual scope error.** The two populations
differ in **time**, and the difference in *kind* is small enough to wave
through. Both are Odds API h2h quotes off the same endpoint, the same regions,
the same markets, parsed by the same code, and the record is 73% the fixture's
league. Every type-level check passes. There is no unit mismatch, no wrong table,
no sign to get backwards. The sentence *"the anchoring discards a median of 26
of 29 usable books"* reads as a fact about a mechanism, and a mechanism has no
timestamp — so nothing in the prose looks wrong, and re-reading it more
carefully does not help. **Only pulling both timestamps and subtracting does.**
That is a step nobody takes unless the rule says to.

**It had already spread, and that is the part that makes it a lesson rather than
a correction.** By the time it was caught, the bare figure appeared in **four**
further places — an accepted ADR, a lesson in this file, `tasks/NEXT.md`, and
the ADR's own options table. In every one it reads as an established fact about
the system, and nothing in any of them points back at a fixture. **A number that
loses its label does not stay put; it gets cited, and each citation looks like
corroboration for the last.** Grep for the figure, not just for the document.

The usual defences all miss it:

- **Provenance labels do not travel.** The label was one document away and was
  simply not copied. A label that lives only at the point of measurement
  protects the measurement, not the citation. The stronger form of the same
  failure: the registration also *refused* a transfer of this exact species from
  this exact fixture — *"a zero from the fixture is close to worthless for this
  question and must not be cited as corroboration"* — and that did not travel
  either. **Writing the prohibition down is not the same as attaching it to the
  number**, and only the second survives a copy-paste.
- **Beware "measured on the live X" where X is a code path.** The registration
  introduced the figure as *"measured on the live anchoring, not derived from
  example lines"*. True — it means *production code applied to a fixture* — and
  one careless reading turns it into *measured on live data*. Name the **input**,
  never only the code path that consumed it.
- **"Same kind of data" is the trap, not the reassurance.** The closer the two
  populations look, the less anything flags the substitution.
- **A single fixture has no `n` to check.** Read-`n`-before-effect-size does not
  fire, because `29 books` is not a sample size in the sense that guard means.

**How to apply — a two-line check, and it must be run rather than reasoned
about.** Before a number measured on population A is applied to population B,
print `min` and `max` of the observation timestamp on both and state the overlap
as a count and a gap. Then carry it into the citation as prose:

```
fixture captured        2026-08-07T13:49:22Z
record observations     2026-08-07T19:28:12Z -> 2026-08-09T23:35:18Z
rows at or before       0 of 1,564      minimum gap 5.65 h
```

**Reconstruct the timestamp on the flattering side.** Here the record's
observation time is `created_ms − odds_age_ms`, and `odds_age_ms` is the
**oldest** contributing book — so this reconstruction puts each row as *early*
as it can be, which is the direction that would manufacture overlap. It still
found none, with 5.65 hours to spare. Had it been computed off the newest book,
a real overlap could have been hidden; a check that can only err toward the
claim it is testing is worth choosing deliberately.

**And scope the correction to what actually broke, because the exciting reading
is the wrong one.** Here the *argument* largely survived: only the **magnitude**
was extrapolated. A correction that took the whole section down would have been
as wrong as the citation, and in the more expensive direction — it would have
deleted the single most plausible alternative explanation for a refutation.
**Say which half fell.**

**But the first draft of that correction over-claimed in the other direction,
and the shape is worth its own line: `X or fallback` is not "by construction".**
The draft said the sharp-book anchoring applies "on every row **by
construction** — that is code, not data". The code is:

```python
sharp = {b: r for b, r in usable.items() if sharp_books and b in sharp_books}
selected = sharp or usable          # <- silent fallback to the FULL book set
```

The intersection is *attempted* on every row; whether it **binds** is data. On a
row where no sharp book quoted, the fair value came from the wide consensus —
the opposite of what the section claims — and `book_count` cannot reveal it,
because three sharp books and three soft ones both read `3`. **So a "by
construction" defence written while correcting an over-claim was itself an
over-claim**, made in the same paragraph, about the same mechanism. The truth
sat in `fair_prices.anchored_on_sharp`, a column written on every row since the
table existed and read by nothing.

**How to apply:** before writing "by construction", read the expression to the
end. A conditional, an `or`, a `try/except`, or a `.get(k, default)` all mean
the outcome is **data**, and the honest sentence is *"the code attempts it on
every row; whether it succeeds is unobserved."* Then check whether something
already records the outcome — a fallback that matters is usually flagged
somewhere, and the flag is usually unread.

**And it is the sibling of a lesson already in this file, with that lesson's
closing sentence inverted.** [[a-sample-whose-strata-do-not-overlap-the-target]]
ends *"temporal drift is the risk people write down; structural non-overlap is
the one that actually voids the transfer."* That advice is good and it is what
was followed: the citation checked kind, sport, endpoint and parse path, found
them identical, and transferred. **The clock is what voided it.** Both entries
stay, and the pair is the point — non-overlap is checkable on **every** axis the
two populations have, and the axis that bites is whichever one nobody printed.
The check is cheap enough to run on all of them.

Related: [[a-true-measurement-licensed-a-false-conclusion]] — same family, where
the *scope* rather than the *window* was widened past what was measured; and
[[before-quoting-n-of-n]], which asks the same question about the denominator
instead of about the clock.

---

## 2026-08-10 — SQL written into a document is code, and unrun SQL is a guess

Three queries were written into `docs/measurements/` for a human to paste into
the live box, with pre-stated expected outputs and a table mapping each result
to a conclusion. All three parsed. **Three of the six statements returned
confident wrong numbers**, and every one was caught only by building a seeded
database and running them.

The worst had a conclusion attached to it. A resolvability check took a
**global** `MAX(fetched_ms)` per event and *then* filtered `<= created_ms`,
rather than the max at-or-before `created_ms`. On a seed where every row
resolves, it reported **`unresolvable = 2` of 2** — total data loss — and the
document's own reading table mapped that to *"sweeps have been pruned … the
magnitude is unrecoverable."* **A guard that fires when nothing is broken is
worse than no guard**, and this one was pointed at retiring a live question.

The other two are the familiar shapes, in SQL:

- **A join through a grouped subquery matched on `fetched_ms` alone** while the
  subquery grouped by `(odds_event_id, fetched_ms)`. One sweep covers ~15
  events at one instant, so it fanned out ~15x — comparing each row against
  other events' stamps, while the aggregate it computed tracked along and the
  output looked healthy.
- **Two units in one comparison.** One column counted distinct *books*, the
  neighbouring column summed *rows*, and the table holds one row per book per
  outcome — so a three-book keep printed `29` beside `6`. The ratio a reader
  computes off that is wrong by exactly the number of outcomes.

**Why documents get away with it:** SQL in prose is reviewed as prose. It is
read for whether it *looks* like it answers the question, and it always does —
nobody diffs a query against a result set that does not exist yet. Worse, the
expected outputs beside it were written from the same mental model as the
queries, so they agreed with each other and disagreed with SQLite. That is
[[a-sign-convention-agreed-with-its-own-test]] with the test replaced by a
paragraph.

**How to apply:** any SQL that ships to a human — a runbook, a measurement spec,
a handoff — gets executed against `init_db` output seeded to the shape that
*breaks* naive queries, before the document is committed. For this repo that
seed is: **more than one sweep**, **one `fetched_ms` shared across several
events**, and **a row created between two sweeps rather than after the last
one**. A single-sweep fixture passes all three broken queries above.

And give any per-row check a **cross-total that must agree** — here
`checked == linked_rows`. A fan-out inflates both the numerator and the
denominator, so the ratio still looks right; only a count tied to an
independently-computed total catches it. Related:
[[before-quoting-n-of-n]], [[one-observation-recorded-thirty-times]] — the same
question about what a row count actually counts, asked of a JOIN.

---

## 2026-08-10 — An allowlist cannot report what is missing from it

`tests/test_has_callers.py` existed to catch built-never-called code. It ran
green for the whole life of the project while the count of orphaned modules
reached **nine**, and it was never broken. Its `MUST_HAVE_CALLERS` list held
fifteen entries, and **every one named a symbol that already had a caller.** Not
one entry was ever added for something orphaned at the time it was added.

That is not neglect. It is the shape of the guard. A list of things-that-must-
have-callers is a **ratchet against re-orphaning** — it protects symbols someone
already suspected — and it is structurally incapable of naming the ones nobody
thought about. Absence from the list and presence of a caller are the same
observation to it. The guard answers *"did anything I already worried about
break?"* and gets read as *"is anything orphaned?"*

The inverted form answers the second question: **enumerate the population,
require every member outside the healthy set to carry an explicit disposition,
and fail on anything unclassified.** Cost to maintain is the same. Under the new
form, adding a module with no caller turns CI red until a human writes down which
it is — a tool a person runs, or quarantined code with a stated revival
condition.

**Why:** this repo has now been wrong about the orphan count three times, always
downward, and each time the detector was green. The count was cited as four, then
six, and is nine. A guard that cannot produce the number it is trusted for is
worse than no guard, because the green is read as the answer.

**How to apply:** any guard shaped *"here are the cases we check"* is suspect —
suppression codes, redaction patterns, required-env lists, allowed-series lists.
Ask what it would take for the guard to report a case nobody enumerated. If the
answer is "someone remembers to add it", invert it: enumerate the population,
classify exhaustively, fail on unclassified. Then **verify by adding a deliberate
instance of the thing it is supposed to catch and watching it go red** — an
enumeration that enumerates nothing passes everything, so green is not evidence
here. Related: [[a-test-that-passes-on-the-bug-is-not-a-test]],
[[code-with-no-caller-is-not-a-feature]],
[[count-guard-families-not-guards]].

---

## 2026-08-10 — A detector's "production" must be the deployment's "production"

The same detector had a second hole, and it hid five of the nine orphans on its
own. It counted a reference from `scripts/` as a caller. But `.dockerignore`
admits exactly **two of the thirty-four** scripts into the image. So a module
whose only caller was a script was, to the test, *called*, and on the deployed
machine, *absent along with its caller*.

Neither half is wrong in isolation. The test's definition of "called" is
reasonable; the image's definition of "shipped" is reasonable. They were written
at different times by different reasoning and **nothing ever compared them**, so
the disagreement had no symptom.

**Why:** this is the repo's recurring *two limits on one quantity* shape, the
same one behind `SuppressionConfig.max_odds_age_ms` vs `MAX_ODDS_AGE_S` and the
duplicated `SHARP_BOOKS`. The tell is always the same: one guard covering half a
property reads exactly like a guard covering all of it, and the covered half is
usually the half that cannot hurt you. Here the visible artefact was a green test
sitting beside a red one **on the same symbol** — which is the clearest evidence
the two definitions had drifted.

**How to apply:** when a test asserts something about "production", derive the
boundary from the artefact that actually defines it — `.dockerignore`, the
entrypoint script, the deploy config — rather than restating it. Do not list the
entry points; **extract** them. Two independent statements of one boundary is a
duplicate, and [[a-shared-object-cannot-disagree-with-itself]] is the fix, not a
test that they agree. Related:
[[an-allowlist-cannot-report-what-is-missing-from-it]],
[[the-false-reassurance-in-a-comment-outlives-the-code]].

---

## 2026-08-10 — The safety was an accident of the boot script, not a design

`data/lake/` holds `recommendations` partitions named `dt=2026-08-0*` containing
**847 rows stamped 2025-07-23 → 2025-08-10** — demo seed data wearing the
record's directory names. The reassuring version of this is "nothing reads it".
That is false: the dbt warehouse reads those partitions directly
(`stg_recommendations.sql`), and `/api/dashboards` reads the marts built from
them. **The reader is fully built.**

The only thing standing between 2025 demo data and a 2026-labelled screen is
that `docker/entrypoint.sh` happens never to invoke `publish` or `dbt build`. No
check enforces that. No test asserts it. Nobody decided it.

**Why:** "nothing reads it" and "nothing currently runs the reader" are different
claims with very different lifetimes. The first is a property of the system; the
second expires the moment someone adds a line to a boot script for an unrelated
reason — and they will not know they armed anything, because the directory names
say 2026. A safety that no artefact states is not a safety; it is a coincidence
that has not ended yet.

**How to apply:** when concluding that dangerous data is unreachable, name the
artefact that makes it unreachable and ask what would have to change for that
artefact to stop being true. If the answer is "someone edits an unrelated file",
write the guard or write the landmine down where the person editing that file
will see it. And **never let a partition's name assert its provenance** — stamp
the data, not the directory. Related:
[[a-borrowed-number-must-overlap-the-population]],
[[the-false-reassurance-in-a-comment-outlives-the-code]].

---

## 2026-08-10 — An empty endpoint is not an empty account

`GET /portfolio/fills` returned zero rows. That was written down as *"zero fills,
ever"*, and from it: *"there is no free path to the fee model, and no historical
fills from the predecessor project to mine."* Both sentences went into
`tasks/NEXT.md` and justified spending real money to create the data.

The account had traded **55 times**. `GET /portfolio/settlements` carried every
one, with `fee_cost` on each, dated 2025-11-27 → 2026-05-10. Eleven of them pin
the fee coefficient to `(0.069771, 0.070129]` and match their model **11 of 11**
exactly — at zero cost, on data sitting on the account the whole time.

`/portfolio/fills` was not lying. It has a **retention window** — upper bound
near three months, confirmed across eight query shapes (bare, `limit`, four
`min_ts` variants, a `min_ts`/`max_ts` span, `ticker`, `event_ticker`). An
endpoint that forgets is indistinguishable, from one query, from a world where
nothing happened.

**Why:** the failure is a quantifier slip that reads as a fact. *"This endpoint
returns nothing"* is an observation about an endpoint; *"this account has no
fills"* is a claim about the world; and the second does not follow from the
first without a **retention** assumption nobody stated. The slip is invisible
because the sentence gets shorter, not longer — and a shorter sentence reads as
more confident. Compare [[a-borrowed-number-must-overlap-the-population]]: same
move, one dimension over.

**How to apply:** before concluding a quantity does not exist, **name a second
place it would appear and look there.** For any API, ask what its retention
policy is before reading an empty list as history; if the docs do not say,
that uncertainty belongs in the write-up, not in the conclusion. And when an
absence is about to authorise **spending money or building something**, that is
the moment the second look is cheapest relative to its value — here it was one
HTTP GET against $7 and a week. Related:
[[code-with-no-caller-is-not-a-feature]] (an absence read as a fact),
[[an-allowlist-cannot-report-what-is-missing-from-it]].

---

## 2026-08-10 — Reachability has two halves, and this project keeps checking one

A pre-registration for four fee-calibration fills carried a reachability
precondition and said so. It verified that each cell **would discriminate
between the hypotheses if it filled** — computing, in advance, that no cell
landed on a rounding-grid boundary where the candidate models agree. Careful
work, and it caught a real trap.

It never checked that the prices **existed**. The band was 6c–14c on
`KXMLBGAME`; the cheapest game-winner ask on the board was **28c**, across the
whole list including live games. Not a thin slate — MLB moneylines cluster
roughly 20–80c, because baseball's variance keeps bad teams live. The band was
plausibly unfillable on *any* day, and the entire hypothesis boundary
`(0.15, 0.27]` sits **below** the cheapest price the series offers.

**This is the joint bound's failure exactly.** There, Branch Z — the outcome
that would have closed the central question — was arithmetically unreachable
before the data existed, so `BRANCH N — NOT CLOSED` was a consequence of the
design rather than an observation. Same shape, second occurrence, and the second
time it was committed by a registration that *believed it had checked*.

**Why:** "can this measurement reach its decision value?" splits into two
questions that feel like one. **Can the instrument distinguish the answers?** is
about arithmetic and is answerable at the desk. **Can the input occur?** is about
the world and is not — it needs the board, the season, the venue's price
distribution. Checking the first is satisfying and feels like diligence, which is
exactly why the second gets skipped.

**How to apply:** every registered cut, band or threshold gets **two** written
preconditions, answered separately and both before any data: *(a)* if this value
occurred, would the rule discriminate? *(b)* does this value occur, and how often
— from a source outside the design? For a price band, that means looking at the
actual board. The cost of getting this wrong is not a wasted measurement; it is a
**confidently reported null** that is a property of the design. Related:
[[the-joint-bound-could-not-have-worked]], [[count-guard-families-not-guards]].

---

## 2026-08-10 — A measurement is not new until you have grepped for its own value

A lane pulled 55 settled positions off the account, computed the distribution of
their fee decimals, found that single-game fees are whole cents while combo fees
are not, and reported it as a new finding that might be load-bearing on the fee
model.

It was already in the repo, twice. `backend/core/fees.py:226-232` carries the
identical measurement — *"11 of 11 single-game fees are whole cents… 32 of 43
KXMVE combo fees are not"* — with the caveat the new report lacked, and the
`note` field of the artefact the lane had **itself just written** carried it as
well. One `grep` for the number it had in its hand would have returned both.

**Why this evades every check that was actually run.** The lane verified its
*provenance* rigorously: the data was real, the query was right, the arithmetic
reproduced. Novelty is a different property from correctness, and nothing in the
pipeline tests for it — a correct measurement feels finished the moment it
validates. The specific trap is that a re-derivation is **maximally
convincing**: it agrees with the record perfectly, because it *is* the record,
and that agreement reads as corroboration from an independent source.

Note the direction, again. Re-deriving inflates the apparent weight of evidence:
two sightings of one number look like two measurements. This repo already has
[[one-observation-recorded-thirty-times-is-one-observation]] for the case where
the *storage* duplicates; this is the case where the *analyst* does.

This is the mirror of
[[a-number-quoted-from-your-own-projects-prose-is-an-assumed-number]]. That rule
says: before quoting a number you found, go find the code behind it. This one
says: before reporting a number you computed, go find whether the repo already
has it. Both directions have now failed here, and the two together are the whole
discipline — **a number and the repo must be reconciled in both directions.**

**How to apply:**

- **Grep for the literal value before writing "new".** Not the concept — the
  digits, and a couple of roundings of them (`11 of 11`, `0.0700`, `0.070`).
  Concepts are named inconsistently across a repo; numbers are not. It is one
  command and it runs before the write-up, not after.
- **Search the artefact you just produced too.** Harnesses copy notes, caveats
  and prior findings into their own output; the duplicate is sometimes inside
  the file you are describing.
- **When a fresh measurement matches the record exactly, that is a prompt, not a
  confirmation.** Ask whether it *is* the record before treating it as
  independent agreement with it.
- **A re-derivation is still worth recording — as a re-derivation.** The value
  is in the *caveat delta*: if the older statement carries a limit yours does
  not, yours is the weaker document and should be dropped, not merged.

Related: [[a-number-quoted-from-your-own-projects-prose-is-an-assumed-number]],
[[tracing-a-number-to-code-is-only-half-the-check]],
[[one-observation-recorded-thirty-times-is-one-observation]].

---

## 2026-08-10 — A number produced by calling a function once is not a claim about a loop that calls it ninety-six times

Three instances in this repo, and they look nothing like each other:

- **ADR 0014's "6 sweeps, 36 credits".** `scripts/measure_slot_coverage.py:262`
  calls `plan_sweep_slots` **once** and counts what it returns. The deployed
  runner calls `decide_sweeps` every 900s (`docker/entrypoint.sh:161-164`,
  `backend/runner.py:860`) — **96 times a day** — against a planner that holds no
  state and is re-made from scratch on every pass
  (`backend/odds/timing.py:53-56`). A simulation of the same slate through the
  running path fired **13 sweeps, 78 credits**: roughly 2x. The figure went into
  the ADR and onward into `fly.live.toml`'s budget comment.
- **ADR 0021 §7.2's "a median of 26 of 29 books".** Measured on one fixture
  captured 5.65 h before the record's earliest odds observation, then quoted as
  a fact about the record's own rows. Same shape: one evaluation of the
  production code, presented as a property of the production *run*.
- **`tests/test_has_callers.py`.** Green because its enumeration enumerated
  nothing. The file now says so in its own docstring
  (`tests/test_has_callers.py:611-614`): *"an enumeration that enumerates
  nothing passes every assertion below."*

**Why the substitution is invisible.** Calling the real function on real inputs
is *exactly what rigour looks like* — nothing is mocked, nothing is
reimplemented, and `measure_slot_coverage.py:25` even says so proudly:
*"Nothing here reimplements the schedule."* That is true and it is the right
design. It is also not the claim being made. A static artefact and a running
system share their code, which is precisely why a number about one is so easy to
read as a number about the other; the divergence lives entirely in **state and
repetition**, and neither is visible in the source.

The error is not bounded in either direction. Re-planning made the ADR's figure
too *low*; a harness that runs a loop once and multiplies by the pass count
would make it too *high*. So "it errs conservatively" is not available as a
defence.

**How to apply:**

- **A harness must state, in its own output, which of the two it measured** —
  the static artefact or the running system — and a number that does not say is
  unusable. Not in a docstring a reader might open: in the printed result, next
  to the figure, so it travels with the number when the number is copied.
- **Ask what state the running system carries between calls.** If the answer is
  "none, it re-plans every time", a single call cannot bound the total, because
  the total is a function of *when* the calls land, not of what one returns.
- **Name the invocation count.** "6 slots per plan" is a fact; "6 sweeps a day"
  is an extrapolation with an unstated multiplier of 1. Writing the multiplier
  down forces the question of whether it is really 1.
- **Prefer the observation to either estimate when the system already records
  it.** A loop that writes a row per call has already answered the question; the
  simulation exists only because nobody read the rows.

Related: [[tracing-a-number-to-code-is-only-half-the-check]] (regime, one level
up), [[a-detectors-production-must-be-the-deployments-production]],
[[an-enumeration-is-not-a-proof-and-every-is-the-word-to-distrust]],
[[a-guard-standing-behind-a-stricter-guard-is-decoration]].

---

## 2026-08-11 — Evidence a decision already cites is not grounds to re-open it

A handoff carried a number forward as *"this landed while the ADR was being
drafted and weakens its rationale"*. It did weaken the **brief the ADR was
commissioned from**. It did not weaken the ADR, because the ADR had already
absorbed it: §7.2 cites §5.4 **by section number** as one of three stated
reasons for its default. The re-opening was proposed on evidence the decision
relies on.

That is easy to miss for a structural reason. A decision document and the brief
that commissioned it are usually read as one thing, and a good ADR **records the
corrections it made to its own brief** — so the strongest evidence *against* the
version of the argument that produced it is sitting inside it, looking like
context. A reader who scans for the conclusion and then hears "but this number
weakens it" has no reason to suspect the number is already a footnote in §7.

The cost is not small: it is a fresh session's best context, spent on a closed
question, and this file already records the same shape happening to a refutation
ADR that had been written and committed.

**How to apply:**

- **Before re-opening a decision on new evidence, grep the decision for the
  evidence.** Search the ADR for the figure, the section number, and the phrase.
  Thirty seconds. If the decision cites it, the re-opening is re-litigation and
  the honest move is to say so in the record rather than to re-derive.
- **Distinguish "weakens the rationale" from "weakens the brief".** They are
  different documents and only one of them is the decision.
- **When you decline to re-open, write the declining down inside the decision**,
  naming the evidence that will be offered again. Otherwise the third session
  re-opens it, and the fourth. The annotation is cheaper than the re-derivation
  every single time.
- **This does not mean decisions are unre-openable.** It means the trigger for
  re-opening has to be something the decision does not already contain. *"We
  should look again"* is not a thing that changed.

Related: [[start-md-is-a-snapshot-git-log-is-the-record]],
[[a-number-quoted-from-your-own-projects-prose-is-an-assumed-number]].

---

## 2026-08-11 — An instrument whose every branch points one way is uninformative, and that is a reason to re-price it, not to cancel it

A $5 measurement was registered as the **trigger** for a deferred A-versus-F
choice. Checking what its branches could actually declare showed the trigger was
close to empty: the registered classification alphabet was `{LOW, HIGH = 2x LOW}`
by construction, so **no branch could declare a rate more favourable than the
best model already on the table**; the one attribution that moved the candidate
rows moved most of them to the *dearer* rate; and a sub-envelope observation
classified as hypothesis-generating only and **suspended** the decomposition
rather than improving it. 26 of 32 outcome vectors killed the option outright.
Every branch pointed at the same answer, differing only in confidence.

The tempting inference is *"the instrument does not decide the question, so
don't buy it."* That inference is wrong here, and the reason generalises: the
instrument had **two other cells that earned on every branch** — a replication
detector and the first observation of a fee in a league covering 27% of the
record — and those served three other open options that the question being
deferred does not touch. Cancelling the purchase because its **headline**
justification was overstated would have destroyed value the headline never
mentioned.

The symmetric error is the more common one: keeping the purchase and continuing
to *describe* it as the trigger, which is a flattering description of a weak
instrument.

**How to apply:**

- **Enumerate what the instrument can declare before asking what it will
  declare.** A registered measurement has a finite outcome space; walk it. If
  the whole space maps to one decision, the measurement is confirmatory, and
  saying so is not the same as saying it is worthless.
- **Separate the headline justification from the full deliverable list**, cell by
  cell, and ask which cells earn on *every* branch. Those are what you are
  actually buying.
- **Re-justify, then re-ask.** Change the sentence that goes to the person
  paying, and say plainly that the headline claim was overstated. Quietly leaving
  the old justification in place because the answer is the same is how a weak
  instrument keeps a strong reputation.
- **Do not let "the trigger is weak" collapse into "take the default now."**
  Check what resolving early actually buys. If the deferral expires on its own
  into the same default, resolving early buys a label and can cost the
  instrument.

Related: [[two-limits-on-one-quantity]],
[[unblocked-is-a-scheduling-property-not-an-evidentiary-one]].

---

## 2026-08-11 — A count written into a handoff cannot include its own commit

The handoff's State section said `main` was six commits ahead. It was nine, and
had been nine at the moment of writing. The three missing commits were the
`docs:` commits **that wrote the handoff**.

This is not carelessness and it does not get fixed by being more careful. Any
self-describing artefact is stale by construction with respect to the act of
writing it: the count is computed, then the writing of the count changes the
count. The same applies to a file listing its own line count, a test suite
reporting its own total in a file inside the suite, and a changelog stating how
many entries it has.

The specific danger is that the number **looks** verified — it is precise, it has
a SHA beside it, and it was true five minutes earlier — so a reader treats it as
a checked fact rather than a snapshot, and acts on the delta.

**How to apply:**

- **Do not write a live count into the artefact the count describes.** Write the
  *command* instead: "run `git log --oneline -20`". This repo already learned
  this once as *`start.md` is a snapshot; `git log` is the record*; the count is
  the same lesson in a place nobody looked.
- **If a count must appear, state its as-of instant and state that it excludes
  the commit carrying it.** One clause, and it converts a wrong number into a
  correct one.
- **A reader's first move on any self-reported count is to re-run it**, not to
  reconcile it. Reconciling assumes both figures were measuring the same thing.

Related: [[start-md-is-a-snapshot-git-log-is-the-record]],
[[a-measurement-is-not-new-until-you-have-grepped-for-its-own-value]].

---

## 2026-08-11 — A test that constructs the parameter it is checking cannot detect that no caller constructs it

`test_the_daily_loss_kill_switch_refuses` was green. It passed
`daily_pnl_dollars = -100.0` and asserted the sizer refused. The sizer did
refuse. The guard was correct, the test was correct, and **no production call
site had ever supplied that argument** — so an order was accepted through the
real route with twenty thousand dollars of realised losses in the database.

This is a **different species** from the four vacuous guards this file already
records. Those had assertions that could not fail. This assertion can fail, does
fail when the guard breaks, and is a genuinely good test of the *logic*. What it
cannot see is the question one level out: **does anything reach this code with a
real value?** By supplying the input itself, the test answers "if this arrives,
the guard works" and is silent on "does this ever arrive" — and it *looks* like
coverage of both.

The reason it survives review is that it reads as an integration test. It names
a production behaviour ("the kill switch refuses"), it exercises the production
function, and the assertion is about a production outcome. Only the *argument*
is synthetic, and an argument is the easiest thing in a test to stop seeing.

**How to apply:**

- **For any guard, write down its input and ask who produces it.** Not "is it
  tested" — *who produces it in the deployed system*. If the only answer is a
  test file, the guard is decoration however green the suite.
- **Instrument, do not grep.** Wrap the production binding and run the whole
  suite, filtering calls by the *caller's* file so only production-originated
  calls count. That produces a number: here, 1,285 sizer calls from `backend/`,
  exactly one with a non-zero value, and it came from a test. A grep gives you a
  belief; this gives you a census — and it self-checks, because catching that
  one test call proves the instrument is not simply blind.
- **Add a caller-level test beside the logic test, never instead of it.** The
  pair covers "the logic is right" *and* "something reaches the logic". Either
  alone certifies nothing about the deployed system.
- **The tell is a keyword argument with a default in a guard signature.** That
  is where the two questions come apart, because the default lets every caller
  omit it and stay green.

Related: [[count-guard-families-not-guards]],
[[a-guard-written-to-prove-a-property-the-code-cannot-violate]],
[[built-but-never-called]].

---

## 2026-08-11 — A default on a guard input is a decision about what happens when nobody knows, and on a limit it is always the permissive one

`daily_pnl_dollars: float = 0.0` on a daily-loss limit. `current_position_dollars:
float = 0.0` on a position cap. Both read as harmless — the neutral element, the
obvious starting value.

They are not neutral. On a **loss** limit, `0.0` is "no losses". On a
**position** cap, `0.0` is "no position". On a **staleness** bound, `0` is "brand
new". In every case the default a programmer reaches for as *empty* is the value
the guard treats as *safest to proceed*, so the failure mode is not that the
guard rejects too much — it is that a caller who knows nothing gets waved
through, silently, and the suite stays green.

CLAUDE.md already states the rule — *"Unreadable resolves to `None`, never `0`.
Callers refuse rather than substitute."* — and this file already records it for
parsed values. **It applies with more force to guard inputs than to data**,
because a wrong data value is usually visible downstream and a wrong guard input
produces no output at all.

**How to apply:**

- **A guard input has no default.** If the caller cannot determine it, the caller
  passes `None` and the guard **refuses**. "Clamp what you trust; refuse what
  you are validating" is the same rule from the other end.
- **Read every default in a risk signature as a sentence.** "If you do not tell
  me your losses, I will assume you have none." Written out, these do not
  survive review; written as `= 0.0`, they have survived it repeatedly.
- **`Optional[float] = None` plus an explicit refusal is more code and it is the
  correct amount of code.** The type then forces every call site to say
  something, which is exactly the property the default destroys.
- **This generalises past zero.** Any default on a guard input picks an answer
  for the ignorant caller; check which side of the guard that answer falls on
  before deciding it is harmless.

Related: [[the-zero-that-means-no-measurement-passes-every-threshold]],
[[a-test-that-constructs-the-parameter-it-is-checking]],
[[unreadable-resolves-to-none-never-zero]].

---

## 2026-08-11 — A readout verified on the demo instance can be structurally blind on the live one

`_latest_sweep_row` filtered `WHERE endpoint = '/odds'`. There are exactly two
writers of that column: production (`budget.py`, fed by `client.py` with
`/sports/{sport_key}/odds`) and the demo seeder (`seed_demo.py`, the literal
`/odds`). Two writers, enumerated exhaustively, disagreeing — so the equality
matched **every demo row and zero production rows**, structurally, from the day
it was written.

The consequence is the shape worth remembering: the last-sweep age was **correct
on the demo instance and permanently blank on the money instance**, and it is
the readout that would have shown that odds fetching had stopped. It ran 17
hours unnoticed.

Tests do not catch this, and the reason is not laziness: tests seed data through
the same path the demo does, so the fixture and the bug share an author. The
readout is *verified*, thoroughly, against the only rows that were ever going to
match it.

**How to apply:**

- **Enumerate the writers of any column a reader filters on.** If a seed or
  fixture path is one of them, compare the literals character by character. Two
  writers disagreeing is a five-minute check and it is decisive.
- **A claim of "never matched" needs the writer enumeration, not a sample.** One
  production row in the long format shows the long format exists; it does not
  show the short one never occurs. Exhaustiveness over writers does.
- **Prefer a predicate that both formats satisfy** over correcting one literal —
  here `endpoint LIKE '%/odds'` fixes the reader without touching the seeder,
  and cannot re-break when a third writer appears with a fourth spelling.
- **When a readout looks healthy, ask which instance you looked at.** Joe's
  standing note that some verification methods lie is this, generalised: demo
  green plus live blind is indistinguishable from working, from the demo.

Related: [[a-detectors-production-must-be-the-deployments-production]],
[[verification-methods-that-lie]],
[[a-fixture-that-omits-a-new-column-reports-the-code-refusing]].

---

## 2026-08-11 — An observability fix that stops at the API boundary has not been made

A lane was commissioned to make a refused sweep leave a trace, because a
17-hour outage had been invisible. It built the table, the writer, the reader,
the `window_status` field and the `/api/window` payload, verified all of it with
sixteen mutations that each went red, and shipped. **The partner declared it a
result.**

A different lane then found that `frontend/src/lib/api.ts` does not declare the
three new fields, and `grep -rn "last_look" frontend/src` returns zero hits. The
value is computed correctly, stored correctly, served correctly, **and reaches
no screen.** This tool is operated from a phone. A number that never arrives on
the device has not been observed by anyone.

This is a **variant** of this file's built-never-called pattern, and the variant
is what makes it hard to see. Nothing here is uncalled: every function has a
caller, every test is real, the mutation matrix was genuine. The break is at the
**last** hop, and it is invisible from the backend precisely because the backend
did its job. Worse, the lane behaved correctly — it declined to edit another
lane's files and said so in its own report, under "left undone". The gap was
created by *ownership boundaries between lanes*, and then nobody owned the
remainder.

**How to apply:**

- **Define "done" as the last consumer, not the last commit.** For an
  observability change the terminal question is *on which screen does this
  appear, and what does it look like when the bad state is happening?* If the
  answer is a payload field, it is half a feature.
- **When a lane reports something under "left undone", that is an unowned task
  the moment the lane exits.** The director who split the work owns the seam.
  Assign it in the same breath as accepting the result, or it becomes a plan.
- **`grep` the consumer, not the producer.** Producing code is what tests cover;
  consuming code at the edge usually is not. One grep of the frontend for the
  new field name is the whole check.
- **Beware of declaring a win on a green mutation matrix.** Sixteen red
  mutations proved the backend chain cannot silently break. They said nothing
  about whether the chain ends anywhere useful, because every mutation was
  applied inside the part that existed.

Related: [[built-but-never-called]],
[[a-detectors-production-must-be-the-deployments-production]],
[[a-readout-verified-on-the-demo-instance-can-be-structurally-blind-on-the-live-one]].

---

## 2026-08-11 — A demo that renders healthy beside a live instance that renders empty is an argument machine for the wrong conclusion

`reference_contracts` is 0 on 1,564 of 1,564 live rows, so the Board's
`surfaced` bucket has never been populated in production. The demo seeder writes
10 to 30 contracts on unsuppressed rows, so the same screen on the demo deploy
shows sized, costed, buyable opportunities.

Both are behaving correctly. But the pair of screens is the most persuasive
available evidence for a claim that is **false** — that the tool works on demo
and is broken on live. The truth is that the strategy surfaced nothing, which is
the project's central finding.

The danger is not that someone lies about it. It is that a demo instance is
built to look like success, a null result looks identical to a broken screen,
and the two are usually inspected side by side by someone who is tired and
hoping. This project's premise is on trial; anything that makes the null look
like a defect will get the defect investigated and the finding deferred.

**How to apply:**

- **Wherever a null is a finding, say so on the screen that shows the null** —
  "0 actionable, and that is a measurement, not an outage" — with the count of
  rows examined beside it. An empty list and a broken query look the same; only
  a denominator distinguishes them.
- **Do not fix the illusion by making the demo emptier.** The demo's job is to
  exercise the code path that production never reaches. Removing the exercise
  loses the coverage and keeps the confusion.
- **Record which code paths have live exercise and which have only seeded
  exercise.** Here it is the entire sizing display, the buy affordance and the
  order entry — every one of them exercised only against rows a seeder wrote.
- **When comparing two instances, name what differs in the DATA before
  inspecting what differs on the SCREEN.** The screen difference is downstream
  of a row count, and starting at the screen invites a rendering diagnosis for a
  population fact.

Related: [[verification-methods-that-lie]],
[[a-true-measurement-licensed-a-false-conclusion]],
[[the-product-is-the-record-not-the-bets]].

---

## 2026-08-11 — The file-ownership map between parallel lanes is a design artefact, and getting it wrong is the director's error

Four lanes ran in one working tree tonight under an explicit rule — disjoint
file sets, `git add` by explicit path, never `git add -A`. Every lane obeyed it.
Two collisions happened anyway, and **both were errors in the map, not in the
lanes**:

- Two lanes were given `backend/seed_demo.py` — one to fix a seeding defect, one
  because the sizer signature changed under it. The first committed while the
  second had uncommitted edits in that file, and swept them into its own commit.
  Both lanes noticed and both said so in their reports.
- One lane was told it owned `backend/api/live.py`. **That file does not
  exist** — the SSE path is `backend/live.py`. The lane found the real file,
  wrote to it, and flagged that it had gone outside its list.

The failure is not that lanes disobeyed. It is that a file-ownership map is
**asserted from memory at assignment time**, before anyone has read the code,
and it goes stale or was never right. The lanes then face a choice between
obeying a wrong map and doing the job, and a good lane does the job and tells
you — which means the *report* is where the map gets corrected, always after
the fact.

The deeper version: **ownership boundaries create seams, and a seam is owned by
nobody by construction.** The same night, an observability change was complete
on the backend and reached no screen, precisely because the frontend belonged to
a different lane and the first lane correctly declined to cross.

**How to apply:**

- **Verify every path in an ownership list exists before assigning it.** One
  `ls` per path. A non-existent path in a brief is worse than no brief, because
  it reads as authority.
- **Assign by *change*, not by directory, when a signature is moving.** If a
  lane is altering a function signature, it owns every caller of that function
  wherever they live — that set is discoverable by grep and a directory list is
  not.
- **Expect the seam and name its owner in the same breath as accepting a
  result.** "Left undone" in a lane report is an unowned task the instant the
  lane exits. Read that section first, not last.
- **A lane that reports going outside its list is behaving well.** Treat that
  paragraph as the most valuable part of the report and verify the edit rather
  than the compliance. Here one such edit touched a frozen measurement harness
  and had to be read before acceptance — it turned out behaviour-preserving and
  *required*, but "the lane said it was minimal" is not the check.
- **Two lanes, never more, is partly about this.** The number of seams grows
  faster than the number of lanes.

Related: [[an-observability-fix-that-stops-at-the-api-boundary-has-not-been-made]],
[[built-but-never-called]],
[[two-sessions-in-one-working-tree-will-fight-over-git]].

---

## 2026-08-10 — A permission grant is not the guarantee it is described as

A governance rule was set — *"`ssh` may run only committed, reviewed scripts by
path; no inline code, no filesystem browsing"* — and encoded as a permission
allowlist. **The allowlist cannot express the rule.** A permission pattern
matches a command *prefix*; it cannot see inside the quotes of
`ssh console -C "..."`. So the installed grant permits arbitrary code on the
money box, while the sentence describing it permits almost nothing.

Worse: **the agent that proposed the rule drifted from it inside the hour**,
using inline `grep` and `python -c` one-liners to verify a deploy. Each was
read-only and low-risk — and "low-risk" is precisely the judgement the rule
existed to remove from the agent.

**Why:** a rule enforced by convention degrades to whatever the convention-holder
judges reasonable in the moment, which is the state the rule was written to
replace. The gap is invisible from inside: the agent believes it is complying,
because it is complying with its own reading.

**How to apply:** when writing any grant, state **in the same breath** which part
is machine-enforced and which part is convention — and put that sentence where
the *next* reader sees it, not in the reasoning that produced it. Then prefer the
enforceable form: a committed script whose path is in the allowlist is checkable;
a promise about what goes inside `-C` is not. When an agent notices its own
drift, the drift is the finding — record it rather than the reassurance that
nothing bad happened.

Related: [[verification-methods-that-lie]],
[[clamping-is-for-values-you-trust]],
[[a-test-that-passes-on-the-bug-is-not-a-test]].

---

## 2026-08-10 — The cheapest fix for a mutation is a mutation already scheduled

Six unreviewed files sat in `/tmp` on the live instance. The reflex was to delete
them; deletion is a write on the machine that holds real money, and it was
outside the read-only grant. They were left alone. **A deploy was already queued,
and a deploy replaces the machine — `/tmp` came back empty for free.**

**Why:** the cost of a mutation is not its blast radius, it is that it needs
authorising, scoping, and verifying, and each of those is a place to be wrong.
An action already authorised for another reason carries none of that cost.

**How to apply:** before proposing a write against production, ask what is
*already going to happen* to that state, and when. Ephemeral state on a
replaceable machine usually has a scheduled solvent. This does not apply to the
volume — `/data` survives deploys, and the record on it is the one thing in this
project that cannot be recreated.

Related: [[a-permission-grant-is-not-the-guarantee-it-is-described-as]].

---

## 2026-08-10 — A control that swaps the data source still shares the estimator

The live instance had not swept odds for 21.5 hours. The first explanation
written down was *"the schedule is quiet by design"*, and the evidence offered
was the live instance's own `slots_planned`.

**That was circular, and fatally so.** `upcoming_fixtures_by_sport`
(`timing.py:304-310`) reads `odds_snapshots`, and the **only production writer of
`odds_snapshots` is a served sweep** (`odds/client.py:271` → `store_quotes`). So
the plan is downstream of the sweeper. A sweeper that stopped 21.5 hours ago
produces a depleted fixture set, which produces a sparse plan, which **looks
exactly like a designed cadence**. Using the plan to exonerate the sweeper is
using the output to certify the input.

The fix was to re-run the same claim against **ESPN** via
`scripts/measure_slot_coverage.py`, which swaps the fixture source and keeps the
repo's own `plan_sweep_slots`. That removed the circularity — **and nothing
else.** What stayed shared: `cluster_kickoffs`, `slots_for_sport`, `CLUSTER_MS`,
`DUE_WINDOW_MS`, `COVERAGE_MS`, `MIN_SLOT_SEPARATION_MS`, and the
`fire_until < now_ms` clamp.

**And one of those shared properties was already on record as biased in the
flattering direction.** `plan_sweep_slots` applies `MIN_SLOT_SEPARATION_MS` only
against slots chosen *in the same plan*, and the harness plans **once**; the
deployed loop re-plans every 900 s, so a cluster the one-shot plan suppresses
becomes firable once the anchor that suppressed it is in the past. ADR 0014's
2026-08-10 annotation records the size of this: **6 slots planned versus 13
simulated, about 2x** — with an explicit quoting rule that the figure *"may be
cited only as 'the one-shot plan's sweep count', never bare."* The claim quoted
exactly that figure, bare, to argue the slot count was **zero**. A known
undercount was used as evidence of absence.

**How to apply:** when you build a control by swapping one input, write down
what the control does **not** control, and check whether any of it is biased
toward the conclusion you are hoping for. A shared estimator can be wrong in
both arms at once, and then agreement between them means nothing. The question
is never "did the two methods agree" but "what could make them agree while both
being wrong".

**The closing move, and it is the shape to copy:** drop the estimator entirely.
The claim finally closed on a **calendar fact with no planner in it** — the raw
ESPN kickoff list showed the last in-scope fixture at 2026-08-10T00:20:00Z and
the next at 23:07:00Z, **22h 47m with zero in-scope games**. That statement
shares no code with the thing under test. Prefer the observation that needs the
least of your own machinery.

Related: [[a-frozen-counter-is-not-evidence-of-a-stuck-mechanism]],
[[tracing-a-number-to-code-is-only-half-the-check]].

---

## 2026-08-10 — Read the coverage line, not the slot list

`measure_slot_coverage.py` plans from 10:00Z, so it **structurally cannot print
a slot whose window closed before then**. Quoting its slot list as "these were
all the slots the day offered" therefore has a hole at the start of the day that
the list itself can never reveal.

What closes the hole is a **different line of the same output**:
`Distinct games covered: 12 of 12` with an empty `MISSED` block. A fixture the
10:00Z clamp dropped from the slot list is not covered by anything, so it
surfaces in `MISSED`. **The safety net was in the output all along, two lines
below the one being quoted.**

Not everything was closed that way. A fixture inside the previous day's final
slot window — covered by its 3-hour `COVERAGE_MS`, so not MISSED — and dropped
from the plan by the 2-hour separation, so not a slot, is **invisible in both
lines**. That residue needed the raw kickoff list.

**How to apply:** before quoting one line of a harness's output, ask which other
line would have to change if the quoted line were misleading. If no other line
would move, the harness cannot detect the failure you are worried about and you
need a different instrument. State the residue explicitly rather than letting a
clean-looking table imply there is none.

---

## 2026-08-10 — Consecutive date buckets tile, and overlap is the safe direction

A claim of the form *"zero X occurred in this interval"* was assembled from two
adjacent calendar buckets fetched from a third-party API whose date convention
was unknown — ET midnight, UTC midnight, or a league-specific late-game rule.

**The convention did not need to be established.** Any consistent partition of
time into consecutive buckets either tiles without a hole or overlaps. Overlap
can make an item appear **twice**; it cannot make one **disappear**. For a claim
of *zero*, over-counting is the safe direction, so the claim is robust to the
convention by construction.

The same reasoning fails immediately for a claim about a **count**. Two slots
printed as `00:53Z` in adjacent buckets are different absolute instants rendered
identically by a `%H:%M` format string — comparing them across runs is not even
well-formed until dates are attached.

**How to apply:** decide whether your claim needs the *zero* or the *count*.
Verify the bucketing convention only for the second. And never compare
wall-clock strings across date buckets without re-attaching the date — a
formatter that drops the day makes two different instants look like one
observation.

Related: [[one-observation-recorded-thirty-times-is-one-observation]].

---

## 2026-08-10 — A command in a handoff has the status of a test never seen red

`start.md` billed one command as *"the single highest-value minute available to
the next session"*:

```
curl -H 'Authorization: Bearer …' https://kalshi-cockpit.fly.dev/api/window
```

**It returns 401 and always would have.** The gate is a Next Edge middleware
reading a `cockpit_session` cookie; it never reads the `Authorization` header,
and it runs *before* the `/api/*` rewrite that reaches the backend at all. The
bearer check guards exactly one route, `POST /api/orders`.

Nobody had ever run it against live. It was written from a **model** of the auth
layer — *bearer guards the API* — that stopped being true when the gate moved to
Edge middleware, and it was published as an instruction anyway.

**This is a distinct species from the failures already in this file.** The
existing entries are about verification that **lies** — green over broken code.
This one **cannot execute**. Its specific danger is misattribution: a 401 from a
documented health check reads as *"the instance is down"* or *"my token is
wrong"*, not as *"the doc is wrong"*. A session following the handoff faithfully
would most likely have concluded the live instance was unreachable and spent the
window investigating an outage that did not exist.

**How to apply:** a command written into a handoff is executable content and
carries the same burden as a guard — **it does not count until it has been run
against the thing it names.** If you cannot run it (no credentials, wrong
machine, costs money), say so beside it in the handoff rather than presenting it
as a step. "Untested against live" is a one-line annotation and it is the
difference between a next session checking a system and a next session debugging
a document.

Related: [[verification-methods-that-lie]],
[[the-false-reassurance-in-a-comment-outlives-the-code-it-describes]],
[[a-readout-verified-on-the-demo-instance-can-be-structurally-blind-on-the-live-one]].

---

## 2026-08-10 — A fixed-sample threshold quoted for a design that peeks inflates its own power about threefold

A live database dump was proposed to finish a test whose sample size nobody had
priced. Pricing it took one function call, and the answer depended entirely on
**which multiplier was used**.

The registered design uses an **always-valid** boundary — a confidence sequence
that holds simultaneously at every `n`, so the gate may re-check on every
request without the running z-score eventually wandering across a fixed line.
At `G = 60` that multiplier is **6.09**. The fixed-sample two-sided 5%
multiplier is **1.96**. The ratio is **3.11**, and it runs entirely in the
flattering direction:

```
                         multiplier   smallest resolvable beta at G = 60
fixed-sample 5%              1.96              0.51    "the test works"
always-valid (tuning 300)    6.09              1.57    "the test cannot work"
                                               ceiling of plausibility = 1.00
```

The two verdicts are opposite. `beta = 1` is full, lossless pass-through and is
the **ceiling**; a design whose smallest resolvable effect is 1.57 cannot
resolve anything real, while one at 0.51 comfortably can. **Quoting the wrong
multiplier does not make the estimate slightly optimistic — it reverses the
decision**, and the decision here was whether to spend a person's attention on a
production dump.

**A second confusion sits right beside it and is easy to make.** The
registration's table prints the multiplier and the resolvable effect in adjacent
columns. `6.09` is the **multiplier**; `1.57` is the **effect**. Both are true
of `G = 60` and they are not interchangeable. A report that called 6.09 "the MDE
at G = 60" was still directionally right, but only by luck — its conclusion
survived because both numbers happen to exceed 1.0.

**Why:** the cost of being allowed to look continuously is real and large, and
it is invisible unless the boundary is named. Most quoted power arithmetic
silently assumes one pre-registered look, which is the thing a continuously
re-checking gate is definitionally not doing.

**How to apply:** before quoting any power or MDE figure, state **which
boundary** produced it and whether the design looks once or many times. Prefer
computing it from the repo's own function (`gate.always_valid_multiplier`) over
transcribing a table, and pin the table to that function in a test — arithmetic
written into a document is code, and unrun arithmetic is a guess. When a table
prints a multiplier and an effect side by side, quote the column header with the
number.

Related: [[sql-written-into-a-document-is-code-and-unrun-sql-is-a-guess]],
[[count-your-tests]].

---

## 2026-08-10 — A measurement with no committed artifact is a rumour, and a handoff can promote it to a verdict in one line

A handoff carried: *"A census ran: the record holds the consensus price, the
Kalshi price and the close for **60 games (46 MLB — 77%)**, and is missing only
who won. **Verdict: RUNNABLE ONLY WITH A LIVE DUMP.**"*

That sentence has the shape of a finished measurement — a population, a
breakdown, a limitation and a verdict. **It has no harness, no result document,
no commit and no raw output.** It exists in exactly one place: the handoff that
asked the next session to act on it. Some of it reproduces from the pinned pull
and some of it does not, and there is no way to tell which without redoing the
work the census supposedly did.

**The word "Verdict" is doing the damage.** It is the vocabulary of this repo's
committed result documents, which earn it by carrying their population, their
negative controls and their "what this does not establish". Borrowing the
vocabulary without the artifact transfers the authority without the evidence,
and the next reader has no cue that anything is missing.

**The rescue was not to adjudicate it.** The disputed counts were routed
**around**: the refusal was written against the **largest** count anyone had
claimed, so every smaller and less-verified figure failed a fortiori and none of
them had to be established. That cost one paragraph and settled the question
permanently.

**Why:** an artifact is what makes a number re-checkable by someone who was not
there. Without one, a figure's only support is that a previous session was
confident, and confidence is exactly what does not survive a context window.

**How to apply:** when a handoff states a measurement, look for the artifact
before acting — a harness path, a result document, a commit. If there is none,
say so in the handoff you write rather than passing the number on, and mark it
`[UNVERIFIED — no committed artifact]` in place. Then check whether the decision
actually needs the number: an argument built on the most generous available
figure often does not, and routing around a disputed number beats litigating it.

Related: [[a-command-in-a-handoff-has-the-status-of-a-test-never-seen-red]],
[[a-measurement-is-not-new-until-you-have-grepped-for-its-own-value]],
[[a-borrowed-number-must-overlap-the-population-you-spend-it-on-in-time]].

---

## 2026-08-10 — A subagent's confident negative is the one result you must re-run yourself

A subagent reported that the phrase *"Kalshi may be the sharp side"* appears in
no ADR and that the handoff had invented it. The claim was load-bearing: it
would have meant a whole line of work rested on a fabrication.

**It was wrong.** `docs/adr/0021:34` says *"If Kalshi is the sharp side of that
comparison, then 'Kalshi versus devigged sportsbook consensus' is close to empty
by construction … §7 states that at full strength."* One `grep` found it.

**A negative from a search is a different kind of claim from a positive.** A
positive carries its own evidence — here is the line. A negative asserts
something about **everything that was not returned**, and it is true only if the
pattern, the path and the file set were all right. Any of the three being
slightly off produces a confident, clean, entirely wrong "not found", and the
output looks identical either way.

**And a negative is the more dangerous direction here**, because it licenses
deleting work: "this was never written down" ends an investigation, while "here
it is" merely continues one.

**Why:** an agent reporting a negative has no way to distinguish "absent" from
"my search did not reach it", and neither does its output. This is the same
shape as an allowlist that cannot report what is missing from it, and as a
truncated sweep printing "no qualifying market".

**How to apply:** when a delegated result is a **negative** and something
depends on it, re-run the search yourself before acting — it costs one command.
Ask for the exact pattern and paths used, not just the conclusion. And when a
subagent's checkable claim turns out wrong, downgrade its *unverifiable* claims
in the same report rather than only correcting the one you caught; the failure
was in method, and method does not fail once.

Related: [[an-allowlist-cannot-report-what-is-missing-from-it]],
[[verification-methods-that-lie]].

---

## 2026-08-10 — "Routed separately" names no owner, and the wrong sentence stays where people read it

A result document closed by listing six corrections it had earned for another
document, under the heading *"What section 7.2 may now be annotated to say"*,
and ended: **"Not edited here. Routed separately."**

**The routing never happened.** One of the six was not a refinement but a
correction of a plain error: the ADR said a column *"is not on this record"*,
when the column was on a different table than the query that had missed it. So
for an unknown stretch the ADR asserted something false, the correction existed
in full one directory away, and every reader of the ADR got the false version —
because ADRs are what people read and result documents are what people cite.

**"Routed separately" reads as a completed handoff and is actually an unassigned
task.** It has no owner, no destination file, no ticket, and nothing that goes
red. It is the seam-between-lanes failure aimed at prose rather than code: the
same shape as the sweep trace shipping complete on the backend and reaching no
screen.

**Why:** the document that *discovers* a correction is almost never the document
that *carries* it, so every correction has a seam in it by construction. A
sentence deferring the crossing is the cheapest possible action and feels like
diligence, which is why it wins over doing it.

**How to apply:** apply a correction where it will be **read**, in the same
change that discovers it, even when that means editing a file outside the lane —
or, if the lane genuinely may not, leave an inline pointer **in the wrong
sentence itself**, so the next reader cannot reach the error without reaching
the correction. Never leave erroneous text unmarked with the fix parked
elsewhere. And treat a document ending "routed separately" as an open defect
until the destination file shows the edit.

Related: [[the-file-ownership-map-between-parallel-lanes-is-a-design-artefact]],
[[an-observability-fix-that-stops-at-the-api-boundary-has-not-been-made]],
[[the-false-reassurance-in-a-comment-outlives-the-code-it-describes]].
