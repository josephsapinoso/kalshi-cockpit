# ADR 0029 — the cluster key was not a game

**Status:** accepted
**Date:** 2026-08-16
**Supersedes nothing. Amends the clustering decision recorded in ADR 0005.**

---

## 1. The decision

`gate.clustered_clv` now clusters on **`event_links.odds_event_id`** — the
sportsbook fixture — falling back to `kalshi_markets.event_ticker` and then to
the market ticker. It clustered on `event_ticker` alone until this date.

`unclustered_rows` now counts rows that missed the **per-game** key rather than
rows that missed the *event* key, which is what its own docstring and the gate's
detail string always claimed it counted.

The three key spaces are prefixed — `game:`, `event:`, `ticker:` — so a fallback
key cannot collide with a real fixture id.

## 2. What was wrong

`clustered_clv`'s docstring said, and still says:

> A game's moneyline, spread and total all resolve from one final score and
> their closing lines move together, so counting them as three independent
> observations repeats the same mistake one level up.

**The code did the opposite of that sentence, and had since the gate was
written.** Kalshi issues a separate event *per series*, not per game. This is an
observation on captured payloads, not a reconstruction — all three tickers of
the trio are present on disk:

```
26AUG072015COLSTL -> KXMLBGAME-26AUG072015COLSTL     (markets_settled.json, 2 markets)
                     KXMLBSPREAD-26AUG072015COLSTL   (events_sports_nested.json, 6 markets)
                     KXMLBTOTAL-26AUG072015COLSTL    (events_sports_nested.json, 11 markets)
```

Their `occurrence_datetime` values are byte-identical, which is what makes them
one game rather than three similar ones. The pattern is not a one-off: across
those captures, ten fixture segments carry more than one event ticker and six
are full moneyline/spread/total trios, in both MLB and WNBA.

Player-prop ladders add more of the same. `KXMLBKS-26AUG151310CWSDET` and
`KXMLBTB-26AUG151310CWSDET` are two further distinct events on one Tigers–White
Sox game, again with identical `occurrence_datetime`. Five prop series exist on
the live instance, so **one game can carry six event tickers that produce
recommendation rows** — one moneyline plus five ladders.

Measured against the production function on a constructed four-series game
(selected fields; `ClusteredMean` carries five):

```
before:  n_rows=4  n_clusters=4  unclustered_rows=0
after:   n_rows=4  n_clusters=1  unclustered_rows=0
```

**How much of that is reachable today is a separate question, and the answer is
"less than the example suggests". §5 is not optional reading.**

**Two errors, both toward permissiveness.**

1. `n_clusters` — the count against the 300 **independent games** floor — ran
   roughly 4× fast on a fully-priced game, and props widen the multiple further.
   `met = stats.n_clusters >= minimum`, so this one is unambiguous. (The
   always-valid multiplier is also monotone the permissive way across the
   operating range — 9.84 at G=20, 3.66 at 300 — though it turns around above
   ~2,400 clusters. Irrelevant at this scale; noted so "more clusters is always
   easier" is not carried forward as a rule.)
2. `stderr_tenths` — the cluster-robust standard error deciding
   `clv_survives_noise_guard` — shrank with the inflated cluster count, so a
   given CLV cleared the noise band on less evidence than the gate believed.

   **The second is conditional and the ADR must not state it flatly.** The
   sandwich estimator's meat is `Σ (sum_y_c − k_c·ȳ)²`. Splitting a cluster
   replaces `d²` with `Σ dᵢ²`, and `(Σ dᵢ)² ⋛ Σ dᵢ²` according to the sign
   pattern of the sibling deviations. Splitting shrinks the standard error only
   when siblings *agree* — which is the positive within-game correlation the
   docstring assumes and **which this project has not measured**. Worked both
   ways against the real estimator: with siblings agreeing, the old key made the
   guard ~4.2× easier; with siblings anti-correlated, it made it ~35× *harder*.

   So the count error is a defect unconditionally; the standard-error error is a
   defect under a premise that is plausible, load-bearing and untested. Both
   arguments point the same way for the fix — one cluster per game is right
   whichever sign the correlation has — but only the first supports the word
   "permissive".

**And the disclosure channel reported nothing.** The docstring justifies
`unclustered_rows` on the grounds that *"an unreported approximation in a money
guard is indistinguishable from a correct one"*. On the old key a row with any
`event_ticker` counted as fully clustered, so the footnote read **0** on records
it had split. The approximation was not partial-but-disclosed; it was silent.

## 3. Why `odds_event_id`

It is the only *stored* identifier in this schema that is one-per-game. The
ticker's fixture segment is also one-per-game, and is discussed below.

- It is minted per sportsbook fixture, and every Kalshi series priced on that
  game links to it.
- **A prop event inherits its game's value by construction.**
  `match.linker.link_prop_event` returns the linked *game* fixture's
  `odds_event_id`, and refuses outright when two games claim one ladder rather
  than guessing — so props collapse onto their game rather than forming
  clusters of their own.
- It is already stored and already joined from `recommendations.link_id`. No
  migration, no backfill, no new column.

The rejected alternative was parsing the fixture segment out of the event
ticker (`KXMLBGAME-26AUG072015COLSTL` → `26AUG072015COLSTL`). It needs no join,
but it is string surgery on a venue-controlled format, it cannot see a market
whose stored `event_ticker` differs from its ticker prefix, and this project has
already been bitten once by a fixed-character chop in the same place — recorded
in `analysis/joint_bound.cluster_key` as *"the previous project's bug, and it
inflated `G` in the flattering direction"*.

**But be precise about what was avoided.** The segment parse was not eliminated,
it was moved one layer down: `link_prop_event` calls `fixture_segment()` to find
a prop's game in the first place, so the prop half of this key rests on that
parse. The difference is that the parse there is anchored, is checked against a
linked game, and **refuses** when a segment maps to two fixtures — rather than
being the cluster key itself, where a mis-parse would silently split or merge
games with nothing to notice.

Two further honest notes on the key:

- **Injectivity is enforced only Kalshi→book.** Nothing stops two Kalshi events
  linking to one `odds_event_id`. On an MLB doubleheader where the book lists
  only one of the two games, each Kalshi event sees one viable candidate and
  both link to it, merging two real games into one cluster. That is already a
  wrong-link bug independent of this ADR; its clustering effect is
  **conservative** (fewer clusters, larger standard error), so it does not
  threaten the guard.
- The `'game:' || l.odds_event_id` tier is safe against NULLs because
  `odds_event_id` is `TEXT NOT NULL` and SQLite's `||` yields NULL for an absent
  join, so the COALESCE ladder falls through correctly rather than producing a
  literal `"game:"` bucket that would merge every unlinked row.

## 4. What this does not establish

- **It does not say the gate was about to open.** The floor reads far below 300
  either way. What was wrong is the *rate* at which it approached it, and the
  error bar beside it.
- **It does not quantify the live effect.** The multiple depends on how many
  series each scored game carried, which needs a read of the deployed record.
  `inspect_live_db.py clv-coverage` was added in the same change to measure it:
  section D prints `clusters_now` beside `clusters_by_game`. **Until that has
  run, no number for the live inflation may be written down.** "Roughly 4×" in
  §2 is a statement about a constructed four-series game, not about the record.
- **It does not touch `n_rows`.** No observation was dropped or added; only the
  grouping changed.
- **It says nothing about whether CLV is positive.** A cluster key decides how
  confident the gate is allowed to be, not what the mean is.
- **It does not re-derive the numbers in ADR 0021.** That document's `G = 59`
  and the `AVAILABLE` counts in `tests/test_clv.py` are Kalshi-event counts —
  `ticker.rsplit("-", 1)[0]`. Under the per-game definition they are **upper
  bounds**, not equalities. Its conclusion ("all far below 300") only
  strengthens under a smaller `G`, so nothing there is reversed; but `G` in ADR
  0021 and `G` in the gate no longer mean the same thing, and neither document
  said so until this one.
- **It does not touch the warehouse.** `mart_clv_by_bucket.sql` computes
  `sd_clv_cents / sqrt(n)` over **rows**, with no clustering of any kind, and
  emits a `verdict` string from it. That is the same defect one level worse, in
  a mart that renders a conclusion. Out of scope here, deliberately — it is a
  reporting surface, not the money guard — but it is now written down.

## 5. What was actually reachable — mostly preventive, not corrective

**The four-series example in §2 is a statement about the venue, not about the
deployed pipeline.** Two constraints narrow it, and both were verified rather
than assumed:

- **A spread or total event cannot hold an `event_links` row at all.**
  `link_event` refuses any Kalshi event whose sides are not exactly two
  (`backend/match/linker.py:280`), and `DiscoveredEvent.teams` is built from
  `yes_sub_title` — which for a spread reads *"St. Louis wins by over 3.5
  runs"*, giving 6 sides, and 11 for a total. `runner.py` iterates only linked
  events, so **spread and total events produce no recommendation rows**, and the
  moneyline/spread/total case this ADR leads with is currently satisfied
  *vacuously*. It is a real venue fact and a real latent defect; it is not a
  defect that has yet mis-counted a row. **If spreads or totals are ever priced,
  the linker must be fixed first — clustering then follows for free.**
- **Every prop row on the live instance is suppressed.** All 474
  (`tasks/NEXT.md:266-271`), on `stale_odds`. `POPULATIONS["actionable"]`
  requires `suppressed_reason IS NULL`, so **no prop row reaches the population
  the 300-game floor counts.** The floor is not currently inflated. The
  *pooled* headline can be, since it includes suppressed rows.

**So: the change is preventive on the `actionable` population and corrective on
the pooled figure only.** Anyone citing this ADR as "the gate was letting money
through too early" is overstating it. What it prevents is that sentence becoming
true the moment a prop row stops being suppressed — which is one config change
or one fresh odds sweep away, and would have arrived silently.

## 6. `unclustered_rows` still reads 0 by construction

The disclosure channel was repaired, but note what it cannot see. An unlinked
Kalshi event produces **no recommendation rows**, so a row that reaches the gate
essentially always has a `link_id`. `unclustered_rows` will therefore read 0
because of how the pipeline is shaped, not because the clustering was verified.

**A zero here is not evidence.** The failure mode that would matter — a game
failing to link — removes its rows from the record entirely rather than showing
up as an approximation, and this counter cannot distinguish the two.

## 7. One residual, unmeasured, and it fails permissive

`event_links` is `UNIQUE (kalshi_event_ticker, odds_event_id)`. That
deliberately allows many Kalshi events per fixture — the property the fix relies
on — but it equally allows **one Kalshi event to acquire two fixture ids**, if
The Odds API ever re-mints one. Older recommendations keep the old `link_id`,
and one game splits back into two clusters: the same direction as the defect
this ADR closes. `link_prop_event` refuses that shape; the gate does not.

Not observed, and not measurable from this repo. **Section E of
`inspect_live_db.py clv-coverage` is a standing check for it**, and zero rows is
the correct answer.

## 8. The consequence for `analysis/joint_bound.py`, which is deliberate

That harness mirrors the gate's cluster key, and asserts at import that the two
agree. **They now do not, and the harness was not changed.**

It runs over HTTP with no database, so `odds_event_id` is unreachable; and §3 of
its pre-registration fixes its clustering variable in advance, which is the one
thing a pre-registration exists to stop anyone re-choosing after seeing data.
Its key still splits one game across its series.

**Direction of the residual error, stated so it cannot be read the wrong way:**
the harness *over*-counts clusters, so any bound it produces is **optimistic**
and must be read as an upper bound on `G`. Closing the gap requires a new
registration, not an edit.

The import-time check was updated to the gate's new key and its message now
tells the reader to decide what the bound means before syncing the string again.

## 9. A note on how this survived

`test_one_games_moneyline_spread_and_total_are_a_single_cluster` existed, was
named after exactly this property, and **passed** — because it handed all three
markets one hand-written `event="EVT-GAME-X"`, a shape Kalshi does not produce.
The test asserted the intended behaviour on an input that never occurs.

Separately, **no gate test wrote an `event_links` row**, so the whole suite
exercised the fallback path while reading as though it covered the join.

The defect was also *written down* — `joint_bound.cluster_key`'s docstring names
it as a cost carried over and "printed, not corrected". It was printed in the
harness that mirrors the guard and not in the guard. A defect recorded next to
the code is not recorded in it.

The lesson is in `tasks/lessons.md`.
