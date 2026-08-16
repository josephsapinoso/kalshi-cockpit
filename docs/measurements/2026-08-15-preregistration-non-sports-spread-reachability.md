# Pre-registration — are non-sports Kalshi markets narrow enough to be worth a fair value?

> **AMENDMENT A, 2026-08-16 — recorded after run 1, before run 2, and it does
> not touch the decision rule.**
>
> Run 1 was audited before publication and two **instrument** defects were
> found. Neither is a change of design; both are the instrument failing to
> implement this document.
>
> 1. **§3's exclusion "either side unreadable" was implemented as one counter
>    that also caught one-sided live books.** Kalshi sends `"0.0000"` for a side
>    nobody bids, never an absent field, so the `unreadable` branch was dead code
>    (0 of 81,420) and 28,579 live markets were dropped under a label reading
>    "settled". Split into `one_sided` and `settled` for run 2.
> 2. **§4's required IQR was never computed**, and no price was recorded, so a
>    *tight* series could not be told from a *cheap* one. Both are emitted in
>    run 2. The rule still reads the median alone.
>
> **Two things this amendment does NOT do.** It does not move `DEAD_RATIO`,
> `LIVE_RATIO` or the `n` floor — all three are unchanged from the pre-run
> values. And it does not license a third run: run 2 is the run, and a further
> look is a new registration.
>
> **§5's central justification is withdrawn as unsupported.** It argued a ratio
> against a control "cancels" a venue-wide effect. The control turns out to span
> 35× across four leagues and to be 47% MLB, so nothing cancels. The rule is
> still applied as written — moving it after seeing the data is the thing
> pre-registration exists to prevent — but the **result document reports every
> verdict as inheriting that instability**, and the price-band cut it adds is
> flagged there as post-hoc.
>
> **§3's name for the treatment arm was also wrong** — a third of it is
> `category = "Sports"`, rejected for league or scope rather than for being
> non-sport. The operationalisation (`classify_series(...).in_scope`) is what
> ran and is unchanged; only the label was wrong.

**Registered:** 2026-08-15, **before any non-sports market was read.** Nothing
in this repo has ever stored, priced or counted a non-sports Kalshi market, so
there is no prior look to be contaminated by. That is stated because it is the
one thing that makes a pre-registration worth writing, and it is unusually
clean here.

**Owns:** `scripts/census_non_sports_spread.py` and the result document it
produces. **Defers to** `docs/adr/0021` §8 on what strategy comes next and
changes nothing about it.

---

## 0. Why this is being asked at all

`backend/kalshi/discovery.py:230` states the reason non-sports is out of scope,
and it is not the reason a reader assumes:

> A league absent here is out of scope — **not because Kalshi lacks markets, but
> because we have no consensus to devig against.**

So the exclusion is about the *instrument*, not the venue. Meanwhile
`backend/kalshi/rest.py:355` walks `/events` with no category filter at all, so
every weather, politics, economics and awards event on the exchange is **already
downloaded on every pass** and discarded in memory at `discovery.py:903` as
`not_game_level` or `league_out_of_scope`. Kalshi REST is unmetered. The data has
been going past this project for its whole life at zero marginal cost.

**The claim that motivated looking, and its status.** A session agent asserted
that an independent census found "zero engagement across all 96 non-sports RFQs
— the professional bot layer is concentrated in sports and largely absent
elsewhere", citing `tasks/prior-art.md:44-46`. **That file does not exist and no
such finding is anywhere in this repo.** The real sentence is
`backend/agents/base.py:194` — 13 automated market makers, nearly all quoting
under 200ms — and it is about **sports**. This probe therefore proceeds on
*cost* (it is free) and **not** on any evidence that non-sports is uncontested.
No result here may cite that RFQ figure.

## 1. The question

> **Is the price of entry into a non-sports Kalshi market small enough that an
> independent forecast could plausibly clear it?**

Not "is there an edge". Not "should we trade weather". Only whether the spread
leaves room for one, which is the cheapest thing that could kill the direction.

## 2. The trap this is built around

This repo's own standing warning is `AVAILABILITY IS NOT FILLABILITY`, and there
is a second one specific to this question:

> **No market maker means wide spreads.** A market can be uncontested *and*
> untradeable. Relax the competition constraint and the spread constraint binds.

That is the same shape as `KXMLBGAME cannot fill a sub-20c pre-game band` — dead
on reachability rather than on the idea. If non-sports is thin because nobody is
quoting it, the cost of crossing is the first thing that eats a forecast edge.

## 3. Population

Every market reachable from one `/events?with_nested_markets=true` walk, at one
instant, split into two arms by `discovery.classify_series`:

| Arm | Definition |
|---|---|
| **NON-SPORTS** (treatment) | events `classify_series` rejects — `is_game_level` false, or `sport_key`/`market_type` `None` |
| **SPORTS** (control) | events it admits — the population this tool already prices |

**The control is the load-bearing half of this design.** Without it the result
would be a number of cents that has to be judged against a threshold somebody
invented. With it, the claim is a ratio against the same instrument, the same
walk, the same instant, and the same derivation — so a spread that is wide
because *Kalshi* is wide, rather than because non-sports is wide, cancels.

Markets are excluded, and the exclusions are counted and reported:

- Either side unreadable (`yes_bid_dollars` or `no_bid_dollars` absent). **Never
  coerced to 0** — `core/prices.is_valid_price` governs, and an unreadable book
  is not a cheap one.
- `status != "open"`.
- A derived ask of 0 or 1000, which is a settled outcome wearing a quote.

## 4. The statistic

For each market, from the nested payload only (no orderbook call):

```
yes_ask  = 1000 - no_bid_tenths          # the price you would pay for YES
no_ask   = 1000 - yes_bid_tenths
spread   = yes_ask - yes_bid_tenths      # tenths of a cent, top of book
half_spread = spread / 2
```

**Reported per series:** `n`, median `half_spread`, IQR, and the count excluded
by each rule above. **Reported per arm:** the median of the per-series medians —
not a pooled median over markets, because one series with 400 markets would
otherwise be the answer.

## 5. The decision rule, fixed now

Let `R = median half-spread (non-sports series) / median half-spread (sports
series)`, computed per non-sports series against the single sports control
median.

| `R` | Verdict |
|---|---|
| `R >= 3.0` | **DEAD** for that series. Entry costs at least three times what it costs in the corner of the venue this project already found nothing in. |
| `R <= 1.5` | **WORTH A FAIR VALUE.** Narrow enough that the question becomes whether an independent forecast exists, which is a different and larger piece of work. |
| otherwise | **UNRESOLVED.** No further look licensed without a new registration. |

**Why ratios and not cents.** Any absolute threshold in cents would be a number
chosen by whoever wrote this document. A ratio against a control measured on the
same instrument at the same instant is a comparison the data supplies. The two
cut points are still chosen — `3.0` because three times the cost of an arena
that already returned nothing is not a marginal call, and `1.5` because within
half again is inside the noise this repo already tolerates between books — and
they are fixed **before the run**, which is the only property that matters.

**`n` is read before the effect size.** No series with fewer than **5** readable
markets gets a verdict, per `CLAUDE.md`. It is reported as `INSUFFICIENT` and
counted, never pooled into a category total to reach the floor.

**Categories are not pooled.** Weather, politics, economics and awards are
separate series with separate market structures. A pooled non-sports median is
computed and reported for orientation and **may not carry a verdict** — the
per-series view governs, and the largest contributor's share is printed beside
it, per `CLAUDE.md`'s measurement rules.

## 6. What would falsify the motivating idea

If the non-sports arm's spreads are **comparable to sports** (`R <= 1.5` on
several series), the "uncontested therefore untradeable" objection fails for
those series, and the direction survives to its next and much harder question.

If they are **three times wider or more**, the direction is dead on cost, and
that is a refutation this document predicted rather than a disappointment
absorbed after the fact.

## 7. What this cannot establish, and these are not hedges

- **It is one instant.** One walk, one moment, no second horizon. A spread is a
  time series and this is a single frame of it. No persistence claim is
  licensed, and the run stamp is recorded so a second look is a *new*
  registration rather than an amendment.
- **Availability is not fillability.** Every number is a stored quote. A
  two-sided book at a tight spread is consistent with real liquidity *and* with
  a maker who cancels when an order arrives. No quote record separates them; one
  small order does. Nothing here is evidence about what would fill.
- **Top of book only.** Size behind the best level is not in the nested payload
  and is not fetched.
- **There is no fair-value path for non-sports, and this does not build one.**
  `event_links`, `fair_prices` and the whole devig chain are keyed on an Odds API
  `odds_event_id`. A non-sports market has no sportsbook counterpart, so this is
  a *different pricing thesis*, not a widening of the current one. A narrow
  spread would mean the next question is "where does a probability come from",
  which is the expensive part and is not begun here.
- **It says nothing about whether an edge exists**, on any market, in any
  category. Rule 1 stands: a large apparent edge is a bug until proven otherwise.
- **`runner.py:1820` hardcodes `kalshi_events.category = 'Sports'`.** Nothing in
  the stored record could currently distinguish the two arms, which is why this
  probe reads the wire directly and stores nothing.
- **The sports control is not a clean baseline either.** It is the same
  population ADR 0021 refuted a strategy against. It is being used as a *unit of
  cost*, not as a standard of goodness.

## 8. Cost and safety

**Zero Odds API credits. Zero writes. No order path.** One unmetered Kalshi REST
walk, the same one every pass already makes. The script opens no database, is
excluded from the image by `.dockerignore`, and is a `Tool` in
`tests/test_has_callers.py`'s sense: a human runs it deliberately from a laptop.
