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
Related: [[four-audits-one-failure-shape]].
