"""The evidence record: recommendations, the gate's population, CLV, props.

Queries: `decision-dump`, `actionable-audit`, `clv-signal-pull`,
`clv-coverage`, `results-for-pull`, `events-for-pull`,
`closing-lines-for-pull`, `series`, `prop-bookmakers`, `team-bookmakers`,
`sharp-anchor-census`, `prop-rungs`, `kalshi-quotes-band`,
`fair-prices-by-market`.

Everything the strategy wrote down and everything used to judge it. Two
properties travel with the whole module and neither may be relaxed: these
queries **emit rows and no aggregate** -- the registered arithmetic lives in
`scripts/run_signal_test.py` and `scripts/analyze_prop_onesided.py`, which
are laptop-side and must never reach the image -- and the thresholds in the
Q-W block are registered constants rather than flags, so a later reader
cannot move a bar after seeing the answer.

`clv-coverage` carries the one stated exemption to the no-aggregate rule
(sections D and F are an exhaustive census, not an estimate); the entrypoint
docstring states it and this module does not widen it.

**Every SQL string in this module is a constant.** This module is imported by
`inspect_live_db.py`, is never run directly, and inherits every disclaimer in
that file's docstring.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from inspect_live_db_common import (
    _MS_PER_DAY,
    Section,
    _day_bounds,
    _derive_iso,
    _fetch,
    _iso,
    _window_section,
)


# The pinned population: recommendations up to `--pin`, and the Kalshi rows
# they reach. Identical to the population in the clean-shortfall pull, so the
# `result` column joins onto it row for row.
_PINNED_TICKERS = (
    "SELECT ticker FROM recommendations WHERE id <= :pin"
)

_SQL_RESULTS_FOR_PULL = (
    "SELECT ticker, event_ticker, series_ticker, yes_side_team, market_type, "
    "status, result FROM kalshi_markets "
    f"WHERE ticker IN ({_PINNED_TICKERS}) ORDER BY ticker"
)

_SQL_EVENTS_FOR_PULL = (
    "SELECT event_ticker, series_ticker, commence_ms, close_ms, status "
    "FROM kalshi_events WHERE event_ticker IN ("
    "SELECT event_ticker FROM kalshi_markets "
    f"WHERE ticker IN ({_PINNED_TICKERS})) ORDER BY event_ticker"
)

_SQL_CLOSING_LINES_FOR_PULL = (
    "SELECT id, ticker, horizon_hours, observed_ms, yes_bid_tenths, "
    "yes_ask_tenths FROM closing_lines "
    f"WHERE ticker IN ({_PINNED_TICKERS}) ORDER BY ticker, horizon_hours"
)

_SQL_SERIES = (
    "SELECT series_ticker, league FROM kalshi_series ORDER BY series_ticker"
)

# Which bookmakers actually returned a player prop, and how recently.
#
# **The question this exists to answer is a cost one.** A prop event is billed
# per market key per region, and the deployed `ODDS_REGIONS` is `us,eu`. So half
# of every prop event's credits buy the `eu` region -- and nothing in the repo
# establishes that any EU book quotes MLB player props at all. The captured
# fixture carries nine books, all US-facing, but it records no capture params,
# and `scripts/probe_prop_dispersion.py` hardcodes `regions=us`, so neither can
# settle it. The live table can: it holds the prop quotes bought under `us,eu`.
#
# **It does not settle it alone.** A book absent here may be absent because it
# quotes no props, or because it quotes props this instance never asked for on a
# fixture it never swept. Read the bookmaker list against the region each book
# is known to serve; do not read an absence as a refusal.
# **Bounded on `commence_ms`, and that bound is the point.** This query was a
# bare `GROUP BY bookmaker` over every row of `odds_snapshots` with the only
# predicate on `outcome_description`, which no index leads with -- a full scan
# of the largest table on the box. On live that evicts the page cache the desk
# is reading through, and the cost lands on Joe's next tap, not on the session
# that ran it (`tasks/lessons.md`, the 75-second read). `commence_ms >= :since`
# rides `idx_odds_commence`, or `idx_odds_sport_commence` when `--sport` names
# one, so the scan is a slice instead of the table.
#
# The window is in the section title for the same reason the row count is: a
# windowed count and a lifetime count are different numbers and this repo has
# already paid for confusing two quantities that shared a name.
_SQL_PROP_BOOKMAKERS = (
    "SELECT bookmaker, COUNT(*) AS quotes, "
    "COUNT(DISTINCT odds_event_id) AS events, "
    "COUNT(DISTINCT market) AS market_keys, "
    "COUNT(DISTINCT sport_key) AS sports, "
    "MIN(fetched_ms) AS first_fetched_ms, MAX(fetched_ms) AS last_fetched_ms "
    "FROM odds_snapshots "
    "WHERE commence_ms >= :since "
    "  AND (:sport IS NULL OR sport_key = :sport) "
    "  AND outcome_description IS NOT NULL "
    "GROUP BY bookmaker ORDER BY quotes DESC"
)

#: Default lookback for `prop-bookmakers` and `team-bookmakers`, in days of
#: `commence_ms`. Seven covers a full sports week including the weekend that
#: follows, which is the population anyone asking "which books quote this"
#: means.
_BOOKMAKERS_DEFAULT_DAYS = 7


# The same question on the OTHER side of the discriminator: which books came
# back on the team markets, per sport.
#
# **Why it is separate from `prop-bookmakers` rather than a flag on it.** The
# prop path is essentially never called -- `ODDS_BUY_PROPS_ON_SCHEDULE` is
# `"false"` and the props card has 0 taps in 77 lifetime lookups -- so
# `prop-bookmakers` returned 0 rows on every sport over a fortnight. The team
# path is the one that runs. Everything the desk prices is priced off these
# rows, and nothing in this repo could report them per sport.
#
# **What makes it worth a subcommand: an absent sharp book raises nothing.**
# `consensus_devig` (`backend/core/devig.py:288-289`) reads
#
#     sharp = {b: r for b, r in usable.items() if sharp_books and b in sharp_books}
#     selected = sharp or usable
#
# so a sport no sharp book quotes does not fail, and does not log: `sharp` is
# empty and the consensus silently falls back to every book it has, soft ones
# included. The row carries `anchored_on_sharp = 0` and nothing else says so.
# Three sharps are bought (`pinnacle`, `matchbook`, `betfair_ex_eu`), one of
# which is known to quote `h2h` ONLY, so spreads and totals already anchor on
# two. NCAAF and NFL are new to the slate and nobody has checked that those
# two cover them.
#
# `GROUP_CONCAT(DISTINCT market)` is here for exactly that: a book present on
# a sport but absent from `spreads` is the case that matters, and a query that
# only counted quotes would report it as present.
#
# Bounded on `commence_ms` for the reason `_SQL_PROP_BOOKMAKERS` is, and the
# reason is not negotiable on this table: see ADR 0157.
_SQL_TEAM_BOOKMAKERS = (
    "SELECT sport_key, bookmaker, "
    "COUNT(*) AS quotes, "
    "COUNT(DISTINCT odds_event_id) AS events, "
    "GROUP_CONCAT(DISTINCT market) AS markets, "
    "MIN(fetched_ms) AS first_fetched_ms, MAX(fetched_ms) AS last_fetched_ms "
    "FROM odds_snapshots "
    "WHERE commence_ms >= :since "
    "  AND (:sport IS NULL OR sport_key = :sport) "
    "  AND outcome_description IS NULL "
    "GROUP BY sport_key, bookmaker ORDER BY sport_key, quotes DESC"
)

# How often the consensus actually had a sharp book to anchor on, per league
# per market -- the MEASUREMENT that `team-bookmakers` is only the input to.
#
# **This exists because book presence overstates anchoring, and a session
# inferred the wrong answer from it on 2026-09-16.** The input side said WNBA
# was the worst-covered sport; the column says WNBA `h2h` is anchored on every
# row and **NCAAF `spreads` and `totals` are the worst cells in the table**, on
# the largest counts in it. Four gaps separate presence from anchoring and
# every one runs the same way -- presence can only overstate:
#
#   1. `consensus_devig` runs once per RUNG (`runner.py:1465`, `:1552`), not
#      per fixture, and a book joins a rung only if it quoted that exact line
#      two-sided and complementary in the same sweep (`runner.py:862-875`,
#      `:992-999`). A book that quoted *some* spread did not necessarily quote
#      the one Kalshi lists.
#   2. One-sided or multi-line quotes are dropped whole.
#   3. A book that fails `devig` drops out of `usable` (`devig.py:280-286`).
#   4. `commence_ms <= stamp` drops started games.
#
# **Counts, never a rate.** Both values of `anchored_on_sharp` are emitted as
# their own rows so the denominator is on the screen beside the numerator; this
# module emits rows and no aggregate, and a ratio computed here would be the
# decision rule rather than the evidence. `links` is the clustering unit --
# rungs within one fixture are not independent observations, and the `rows_n`
# column will always be the flattering one to quote.
#
# **`league` comes from `event_links`, which is Kalshi's own string**
# (`discovery.py:240`), not the Odds API's `sport_key`: `fair_prices` carries
# no sport. The four live values are `Pro Baseball`, `NCAA Football`,
# `Pro Basketball (W)`, `Pro Football`. An unrecognised `--league` returns no
# rows, which reads identically to a league with no anchored rows, so the
# unfiltered call prints every league and `--league` is for narrowing a known
# answer rather than for discovering one.
#
# Bounded on `computed_ms` with `market` pinned to the three team markets, so
# `idx_fair_market_computed` -- which leads with `market` -- seeks rather than
# scans: `SEARCH f USING INDEX idx_fair_market_computed (market=? AND
# computed_ms>?)`. Measured, not assumed.
_SQL_SHARP_ANCHOR_CENSUS = (
    "SELECT e.league AS league, f.market AS market, "
    "  f.anchored_on_sharp AS anchored_on_sharp, "
    "  COUNT(*) AS rows_n, "
    "  COUNT(DISTINCT f.link_id) AS links, "
    "  MIN(f.computed_ms) AS first_ms, MAX(f.computed_ms) AS last_ms "
    "FROM fair_prices f JOIN event_links e ON e.id = f.link_id "
    "WHERE f.market IN ('h2h', 'spreads', 'totals') "
    "  AND f.computed_ms >= :since "
    "  AND (:league IS NULL OR e.league = :league) "
    "GROUP BY e.league, f.market, f.anchored_on_sharp "
    "ORDER BY e.league, f.market, f.anchored_on_sharp"
)

#: Default lookback for `sharp-anchor-census`, in days of `computed_ms`.
#:
#: Shorter than the seven days `team-bookmakers` uses, and deliberately: a
#: `fair_price` is recomputed every pass, so two days is already many rows per
#: fixture, and the question ("is the anchor holding on the slate in front of
#: me") is about the current slate rather than the season.
_SHARP_ANCHOR_DEFAULT_DAYS = 2

#: The variable naming the books the request asks for, read from the same
#: environment the deployed loop reads it in.
#:
#: Echoed beside the response because the whole difficulty of reading an
#: absence here is that two different things produce one: a book that quotes
#: nothing, and a book that was never asked for. Since ADR 0155 the request
#: names ten keys and the vendor returns only those, so the response alone
#: cannot tell them apart. Printing the request turns a cross-source join --
#: the kind a reader does from memory and gets wrong -- into two adjacent
#: sections.
#:
#: Unset resolves to a section that says so, never to an inferred list.
_ODDS_BOOKMAKERS_ENV = "ODDS_BOOKMAKERS"


# ---------------------------------------------------------------------------
# The actionable population, row by row.
# ---------------------------------------------------------------------------
#
# **The predicate is copied from `gate.POPULATIONS["actionable"]`, and the copy
# is held in place by a test rather than by care.** This script imports nothing
# from `backend` on purpose -- it runs as `python /app/scripts/...`, which puts
# `/app/scripts` on `sys.path` and not `/app`, so an import would work in the
# test suite and fail on the machine it exists to interrogate. That leaves two
# copies of one definition, which is the drift `tasks/lessons.md` records, so
# `tests/test_inspect_live_db.py` asserts this string is byte-identical to the
# gate's. If the gate's admission criteria move and this does not, the suite
# goes red before the query can report a population the gate no longer uses.
#
# The `r.` alias is part of that identity: it is what the gate's fragment
# carries, so the two strings compare directly.
_ACTIONABLE_PREDICATE = "r.suppressed_reason IS NULL AND r.reference_contracts > 0"

_SQL_ACTIONABLE_ROWS = (
    "SELECT r.id, r.created_ms, r.ticker, m.series_ticker, m.event_ticker, "
    "m.market_type, m.status, r.side, r.entry_ask_tenths, r.depth_at_ask, "
    "r.fair_probability, r.edge_tenths, r.fee_predicted, r.ev_net_dollars, "
    "r.kelly_fraction, r.suggested_contracts, r.reference_contracts, "
    "r.kalshi_quote_age_ms, r.odds_age_ms, r.last_confirmed_ms, "
    "r.last_confirmed_quote_age_ms, r.last_confirmed_odds_age_ms, "
    "r.strategy_config_version, r.reason_text "
    "FROM recommendations r "
    "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
    f"WHERE {_ACTIONABLE_PREDICATE} "
    "ORDER BY r.created_ms DESC, r.id DESC"
)

_SQL_ACTIONABLE_FAIR = (
    "SELECT r.id, r.ticker, f.id AS fair_price_id, f.computed_ms, f.market, "
    "f.outcome_name, f.outcome_description, f.outcome_point, "
    "f.p_multiplicative, f.p_additive, f.p_power, f.p_shin, f.p_conservative, "
    "f.overround, f.market_width, f.book_count, f.anchored_on_sharp, "
    "f.books_used "
    "FROM recommendations r "
    "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
    f"WHERE {_ACTIONABLE_PREDICATE} "
    "ORDER BY r.created_ms DESC, r.id DESC"
)


# ---------------------------------------------------------------------------
# The CLV signal test's registered extraction.
# ---------------------------------------------------------------------------
#
# **A transcription of §S1 of
# `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`, as
# amended, not a design.** Every clause below is fixed in that file; nothing
# here chooses a population, a horizon or a cluster key, and changing one is
# an amendment made in the registration, dated, before the next look.
#
# **The clause-by-clause commentary that stood here moved to Appendix S1a of
# that same document on 2026-09-06**, verbatim -- four folded amendments
# (§A1 the delimited `instr` predicate, §A2 the four excluded codes, and the
# rest) with the reasoning for each. It moved because this file crossed the
# Read-tool ceiling; read it there before changing any predicate below.
_SQL_CLV_SIGNAL_PULL = (
    "SELECT COALESCE(m.event_ticker, r.ticker) AS cluster_key, "
    "r.id, r.ticker, r.side, r.created_ms, m.market_type, "
    "r.entry_ask_tenths, r.edge_tenths, r.clv_tenths, "
    "r.suppressed_reason, r.reference_contracts, r.strategy_config_version, "
    "q.yes_bid_tenths, q.no_bid_tenths, q.observed_ms AS quote_observed_ms, "
    "((1000 - q.no_bid_tenths) - q.yes_bid_tenths) / 2.0 AS half_spread_tenths, "
    "(m.event_ticker IS NULL) AS unclustered "
    "FROM recommendations r "
    "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
    "LEFT JOIN kalshi_quotes q ON q.id = ("
    "  SELECT q2.id FROM kalshi_quotes q2 "
    "  WHERE q2.ticker = r.ticker AND q2.observed_ms <= r.created_ms "
    "    AND q2.yes_bid_tenths IS NOT NULL AND q2.no_bid_tenths IS NOT NULL "
    "  ORDER BY q2.observed_ms DESC LIMIT 1) "
    "WHERE r.clv_scored_ms IS NOT NULL "
    "  AND r.clv_tenths IS NOT NULL "
    "  AND r.clv_horizon_hours = 0.0 "
    "  AND r.entry_ask_tenths BETWEEN 10 AND 989 "
    "  AND (r.suppressed_reason IS NULL "
    "       OR (instr(',' || r.suppressed_reason || ',', ',stale_odds,') = 0 "
    "       AND instr(',' || r.suppressed_reason || ',', ',stale_kalshi_quote,') = 0 "
    "       AND instr(',' || r.suppressed_reason || ',', ',no_commence_time,') = 0 "
    "       AND instr(',' || r.suppressed_reason || ',', ',commence_skew,') = 0)) "
    "ORDER BY r.id"
)


def _q_clv_signal_pull(conn: sqlite3.Connection, args) -> list[Section]:
    """The registered §2 population for the CLV signal test, one row each.

    Emits rows and **no statistic**. `beta`, its cluster-robust standard error,
    the always-valid boundary and the verdict are computed in
    `scripts/run_signal_test.py`, against the rule registered in
    `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`. That
    split is not ceremony: the registration's decision rule has four branches
    and an amendment history, and SQL is the wrong place to encode any of it.

    What this does not establish
    ----------------------------
    - **Nothing on its own.** It is the input to a pre-registered test.
    - **A NULL `half_spread_tenths` is a missing quote, not a zero spread.**
      The harness drops and counts those rows; P1 refuses the analysis below
      0.90 coverage. Reading NULL as 0 would delete the C2 confound by
      arithmetic.
    - **The joined quote is the last one at or before `created_ms`**, which is
      not necessarily the quote the recommendation was priced from. §A8.2
      requires the rows whose quote *disagrees* with `entry_ask_tenths` to be
      counted separately from the rows with no quote at all; this query emits
      `yes_bid_tenths`/`no_bid_tenths` so the harness can do that, and does not
      do it here.
    - **`strategy_config_version` is emitted, not filtered.** §7's modal-version
      rule is the harness's to apply, and the record carries several versions.
    """
    return [
        _derive_iso(
            _fetch(
                conn,
                _SQL_CLV_SIGNAL_PULL,
                (),
                title="registered §2 population, horizon 0.0 (rows only, no statistic)",
                cap=args.limit,
            ),
            "created_ms",
            "created_iso",
        )
    ]


# ---------------------------------------------------------------------------
# The whole decision record, raw.
# ---------------------------------------------------------------------------
#
# **This is a dump, not a measurement, and the distinction is the whole design.**
# Two open questions need the same rows and disagree about how to slice them:
# the free falsification query (`edge_tenths` minus the bar it had to clear,
# by `market_type`) and the separating measurement of
# `docs/measurements/2026-08-16-actionable-population-audit-result.md` (the
# unsuppressed population split by `anchored_on_sharp` -- if unanchored rows
# are enriched for positive edge, the "edge" is a fact about which books were
# admitted).
#
# Both have a decision rule attached, so **neither is computed here**. This
# emits one row per recommendation with the columns each needs and no
# aggregate at all -- not a rate, not a bucket, not a count beyond the section's
# own row count. `prop-rungs` set that precedent deliberately (see this module's
# docstring) and it is the default for anything a verdict will be built on: the
# registered arithmetic lives in a laptop script, where it is reviewable as
# arithmetic rather than as SQL.
#
# **No population is chosen here either.** `suppressed_reason` is emitted as a
# column rather than applied as a predicate, so the analyst picks the population
# and the instrument cannot quietly pre-select one that flatters. That is the
# opposite choice from `actionable-audit`, which exists to show one named
# population in full, and the two are meant to disagree in that way.
#
# The four `p_*` methods are emitted rather than their spread, because the bar
# in question IS a function of them (`suppression.py:351`) and a dump that
# pre-computed it would be smuggling in the definition under test.
_SQL_DECISION_DUMP = (
    "SELECT r.id, r.created_ms, r.ticker, m.market_type, m.event_ticker, "
    "m.series_ticker, m.status AS market_status, m.result AS market_result, "
    "l.odds_event_id, e.commence_ms, r.side, r.entry_ask_tenths, "
    "r.depth_at_ask, r.fair_probability, r.edge_tenths, r.fee_predicted, "
    "r.suggested_contracts, r.reference_contracts, r.kalshi_quote_age_ms, "
    "r.odds_age_ms, r.last_confirmed_ms, r.suppressed_reason, "
    "r.strategy_config_version, f.p_multiplicative, f.p_additive, f.p_power, "
    "f.p_shin, f.p_conservative, f.overround, f.market_width, f.book_count, "
    "f.anchored_on_sharp, r.clv_tenths, r.clv_horizon_hours, r.clv_scored_ms "
    "FROM recommendations r "
    "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
    "LEFT JOIN event_links l ON l.id = r.link_id "
    "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
    "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
    "ORDER BY r.id"
)


def _q_decision_dump(conn: sqlite3.Connection, args) -> list[Section]:
    """Every recommendation ever written, with its provenance, and no verdict.

    One section on purpose. A second summary section would be an aggregate, and
    the point of this query is that it contains none -- a reader who wants a
    rate computes it in `scripts/`, against a registered rule, where the
    arithmetic can be reviewed as arithmetic.

    **Expect this to truncate and check the flag.** The record is >10,000 rows
    and `DEFAULT_ROW_CAP` is 2,000, so the default invocation returns a prefix
    ordered by `id` -- which is the oldest rows, not a sample. Pass `--limit`
    above the record size and confirm `truncated` is false before analysing.

    What this does not establish
    ----------------------------
    - **Nothing at all on its own.** It is rows. Every question worth asking of
      them has a decision rule that belongs in a pre-registration.
    - **`suppressed_reason` names the FIRST reason only.** All checks run
      without short-circuit, but one string is stored, so this cannot support
      "how many rows would N alone have caught".
    - **The record is not a sample of decisions.** `persist_if_changed` writes
      only when the ask or the fair value moves, so a market quoted unchanged
      for an hour contributes one row and a volatile one contributes many. Any
      per-row rate is a rate per *write*, not per opportunity or per unit time.
    - **`edge_tenths` is priced at one contract** on every row the deployed
      sizer zeroed, which is nearly all of them (`engine.py:177`). Two rows with
      different sizes are not on the same scale.
    - **A NULL `odds_event_id` or `commence_ms` is a failed join**, not a
      missing fixture. Read the orphan count before clustering by game.
    """
    return [
        _derive_iso(
            _fetch(
                conn,
                _SQL_DECISION_DUMP,
                (),
                title="recommendations: every decision, with fair-price provenance",
                cap=args.limit,
            ),
            "created_ms",
            "created_iso",
        )
    ]


# ---------------------------------------------------------------------------
# CLV coverage, and the gate's cluster count.
# ---------------------------------------------------------------------------
#
# **Three questions, one read, and none of them is answerable from this repo.**
#
# 1. Do prop rows score CLV at all? Nothing here has ever asked Kalshi for a
#    candlestick on a prop series -- `measure_candlestick_retention.py` defaults
#    to `KXMLBGAME` and both candlestick fixtures are `KXMLBGAME`. If the venue
#    serves no candles for `KXMLBKS`, every prop row sits unscored forever.
# 2. What does that cost? `scoring.markets_awaiting_scoring` selects on
#    `clv_scored_ms IS NULL` with **no retry cap and no age cutoff**, and
#    `run_loop.py` passes `max_markets=None` on every full pass. A ticker that
#    can never score is therefore re-requested at two horizons, every full pass,
#    indefinitely. Section B counts that set; `started x 2` is the per-pass bill.
# 3. Does the gate's cluster count still mean "one game"? Section D is the
#    measurement, not the argument -- see its own comment.
#
# **What this does not establish.** A zero in section C for a prop series is
# consistent with the venue serving no candles *and* with no prop row having
# reached its true commence time yet. Read section B's `started` column beside
# it: a prop series with `started > 0` and no `closing_lines` row has been asked
# and answered nothing.

# The horizon `gate.clustered_clv` filters on. `analysis/clv.py` sets
# `DEFAULT_HORIZON_HOURS = 0.0`, with no env override anywhere -- not in
# `fly.live.toml`, `.env.example` or `backend/config.py`. Restated rather than
# imported because this script must not import the application to read its
# database; section D's title prints it so a drift is visible rather than
# assumed.
_CLV_GATE_HORIZON_HOURS = 0.0

# Section A -- every recommendation row, by what kind of market it is.
_SQL_CLV_ROWS_BY_TYPE = (
    "SELECT COALESCE(m.market_type, '(no market row)') AS market_type, "
    "  COALESCE(m.series_ticker, '(none)') AS series_ticker, "
    "  COUNT(*) AS rows_total, "
    "  COUNT(DISTINCT r.ticker) AS distinct_tickers, "
    "  SUM(CASE WHEN r.clv_scored_ms IS NOT NULL THEN 1 ELSE 0 END) AS scored, "
    "  SUM(CASE WHEN r.clv_scored_ms IS NOT NULL "
    "           AND r.clv_tenths IS NOT NULL THEN 1 ELSE 0 END) AS scored_with_clv, "
    "  SUM(CASE WHEN r.clv_scored_ms IS NULL THEN 1 ELSE 0 END) AS pending "
    "FROM recommendations r "
    "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
    "GROUP BY market_type, series_ticker "
    "ORDER BY rows_total DESC"
)

# Section B -- `scoring.markets_awaiting_scoring`'s population, restated.
#
# The CTE mirrors that function's SELECT exactly: same joins, same
# `MIN(commence_ms)` per odds event, same two predicates. It is restated rather
# than imported for the reason above, and any divergence shows up as a count
# that disagrees with the `scoring pass:` log line's `markets_considered`.
_SQL_CLV_PENDING_RETRY = (
    "WITH pending AS ("
    "  SELECT DISTINCT r.ticker AS ticker, "
    "         m.series_ticker AS series_ticker, "
    "         m.market_type AS market_type, "
    "         o.commence_ms AS commence_ms "
    "  FROM recommendations r "
    "  JOIN event_links l ON l.id = r.link_id "
    "  JOIN kalshi_markets m ON m.ticker = r.ticker "
    "  JOIN (SELECT odds_event_id, MIN(commence_ms) AS commence_ms "
    "        FROM odds_snapshots GROUP BY odds_event_id) o "
    "       ON o.odds_event_id = l.odds_event_id "
    "  WHERE r.clv_scored_ms IS NULL AND m.series_ticker IS NOT NULL"
    ") "
    "SELECT series_ticker, "
    "  COALESCE(market_type, '(no market row)') AS market_type, "
    "  COUNT(*) AS tickers_pending, "
    "  SUM(CASE WHEN commence_ms <= :now THEN 1 ELSE 0 END) AS started, "
    "  SUM(CASE WHEN commence_ms > :now THEN 1 ELSE 0 END) AS not_started_yet, "
    "  MIN(commence_ms) AS oldest_commence_ms "
    "FROM pending GROUP BY series_ticker, market_type "
    "ORDER BY started DESC, tickers_pending DESC"
)

# Section C -- did a candle ever come back, and for which series?
_SQL_CLV_LINES_BY_SERIES = (
    "SELECT COALESCE(m.series_ticker, '(none)') AS series_ticker, "
    "  COALESCE(m.market_type, '(no market row)') AS market_type, "
    "  cl.horizon_hours AS horizon_hours, "
    "  COUNT(*) AS lines_stored, "
    "  SUM(CASE WHEN cl.yes_bid_tenths IS NULL "
    "           OR cl.yes_ask_tenths IS NULL THEN 1 ELSE 0 END) AS one_side_null, "
    "  MIN(cl.observed_ms) AS first_observed_ms, "
    "  MAX(cl.observed_ms) AS last_observed_ms "
    "FROM closing_lines cl "
    "JOIN kalshi_markets m ON m.ticker = cl.ticker "
    "GROUP BY series_ticker, market_type, horizon_hours "
    "ORDER BY series_ticker, horizon_hours"
)

# Section D -- the gate's cluster count, beside the count it is meant to be.
#
# `gate.clustered_clv`'s docstring gives the requirement: a game's moneyline,
# spread and total resolve from one final score, so they must not count as three
# independent observations. `_clv_evidence` restates it -- *"Both count
# **independent games**, not rows."*
#
# A player prop resolves from that same final score but carries its **own**
# Kalshi event ticker (`KXMLBKS-26AUG151310CWSDET`, not
# `KXMLBGAME-26AUG151310CWSDET`), so on the event key each prop ladder on a game
# forms a cluster of its own.
#
# **Read the two columns in the right tense.** `clusters_now` is the key the
# gate used **until 2026-08-16** -- `COALESCE(m.event_ticker, r.ticker)` --
# kept as the *before* number. `clusters_by_game` is the key it uses **now**,
# `event_links.odds_event_id`, which a prop link inherits from its game
# (`match/linker.py` `link_prop_event`). The gap is the size of the defect
# ADR 0029 closed on this record, not a live discrepancy and not a bug in the
# gate's arithmetic -- the key was what was in question.
#
# The population CASE mirrors `gate.POPULATIONS` and is exhaustive in the same
# order: `suppressed` first, then `reference_contracts > 0`, else `no_edge`
# (NULL fails `> 0` and falls through, as it does there).
_CLV_CLUSTER_SELECT = (
    "  COUNT(*) AS rows_counted, "
    "  COUNT(DISTINCT COALESCE(m.event_ticker, r.ticker)) AS clusters_now, "
    # The gate's key is a three-tier ladder and this must be all three, not
    # two. Skipping the `event:` tier would make `clusters_by_game` read
    # *higher* than the gate's own `n_clusters` for any unlinked row that still
    # has an event ticker -- an instrument that does not reproduce its subject.
    "  COUNT(DISTINCT COALESCE('game:' || l.odds_event_id, "
    "                          'event:' || m.event_ticker, "
    "                          'ticker:' || r.ticker)) AS clusters_by_game, "
    "  SUM(CASE WHEN m.event_ticker IS NULL THEN 1 ELSE 0 END) AS orphan_rows, "
    "  SUM(CASE WHEN l.odds_event_id IS NULL THEN 1 ELSE 0 END) AS unlinked_rows "
    "FROM recommendations r "
    "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
    "LEFT JOIN event_links l ON l.id = r.link_id "
    "WHERE r.clv_scored_ms IS NOT NULL AND r.clv_tenths IS NOT NULL "
    "  AND r.clv_horizon_hours = :horizon "
)

_SQL_CLV_CLUSTERS_BY_POPULATION = (
    "SELECT CASE "
    "    WHEN r.suppressed_reason IS NOT NULL THEN 'suppressed' "
    "    WHEN r.reference_contracts > 0 THEN 'actionable' "
    "    ELSE 'no_edge' END AS population, " + _CLV_CLUSTER_SELECT + "GROUP BY population "
    "ORDER BY rows_counted DESC"
)

# Pooled separately, and not by summing the rows above. `clv_by_population`
# says why: the groups do not partition the *games*, only the rows, so one game
# contributing an actionable row and a suppressed row is counted in both groups.
_SQL_CLV_CLUSTERS_POOLED = (
    "SELECT 'pooled' AS population, " + _CLV_CLUSTER_SELECT
)

# Section E -- the way the per-game key could put the bug back.
#
# `event_links` is `UNIQUE (kalshi_event_ticker, odds_event_id)`, which
# deliberately lets many Kalshi events point at one fixture -- that is what
# makes the key work. It also permits the reverse: if The Odds API ever
# re-mints a fixture id, `record_link` inserts a **second** row for the same
# Kalshi event, older recommendations keep pointing at the old link, and one
# game becomes two clusters again. `link_prop_event` refuses when a fixture
# segment maps to two ids; nothing protects the gate.
#
# The direction of that failure is **permissive** -- the same direction as the
# defect ADR 0029 fixed -- so it is worth a standing check rather than a
# one-off. Zero rows here is the expected and correct answer.
_SQL_CLV_CLUSTERS_BY_TYPE = (
    "SELECT CASE "
    "    WHEN r.suppressed_reason IS NOT NULL THEN 'suppressed' "
    "    WHEN r.reference_contracts > 0 THEN 'actionable' "
    "    ELSE 'no_edge' END AS population, "
    "  COALESCE(m.market_type, '(no market row)') AS market_type, "
    + _CLV_CLUSTER_SELECT
    + "GROUP BY population, market_type "
    "ORDER BY population, rows_counted DESC"
)

# Section G -- WHICH clusters collapsed, and whether each collapse is the one
# ADR 0029 describes.
#
# **This is the section that can refute the fix rather than confirm it.** A
# collapse is *correct* when the extra Kalshi events are different series on one
# game -- a prop ladder, or a spread/total -- because those genuinely resolve
# from one final score. A collapse is *suspect* when two events of the **same
# series** land on one sportsbook fixture, because `KXMLBGAME-A` and
# `KXMLBGAME-B` are normally two different ball games. That shape is either a
# relisted/retimed game (a correct collapse this ADR does not describe) or a
# **mislink that merged two real games** (an over-collapse, i.e. a defect in the
# new key, in the conservative direction).
#
# `same_series_extra` is the discriminator: `COUNT(DISTINCT event_ticker) -
# COUNT(DISTINCT series_ticker)`. Zero means every extra event came from a
# different series and the collapse is the documented one. Anything above zero
# needs a human to read `event_list`.
#
# Section E cannot see this. It checks one Kalshi event fanning out to two
# fixtures -- the *permissive* direction. This checks the conservative one,
# which is the direction the fix itself could be wrong in.
_SQL_CLV_COLLAPSES = (
    "WITH scored AS ("
    "  SELECT COALESCE('game:' || l.odds_event_id, "
    "                  'event:' || m.event_ticker, "
    "                  'ticker:' || r.ticker) AS game_key, "
    "         m.event_ticker AS event_ticker, "
    "         m.series_ticker AS series_ticker, "
    "         CASE WHEN r.suppressed_reason IS NOT NULL THEN 'suppressed' "
    "              WHEN r.reference_contracts > 0 THEN 'actionable' "
    "              ELSE 'no_edge' END AS population "
    "  FROM recommendations r "
    "  LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
    "  LEFT JOIN event_links l ON l.id = r.link_id "
    "  WHERE r.clv_scored_ms IS NOT NULL AND r.clv_tenths IS NOT NULL "
    "    AND r.clv_horizon_hours = :horizon"
    ") "
    "SELECT game_key, "
    "  COUNT(DISTINCT event_ticker) AS kalshi_events, "
    "  COUNT(DISTINCT series_ticker) AS distinct_series, "
    "  COUNT(DISTINCT event_ticker) - COUNT(DISTINCT series_ticker) "
    "    AS same_series_extra, "
    "  SUM(CASE WHEN population = 'suppressed' THEN 1 ELSE 0 END) AS suppressed_rows, "
    "  SUM(CASE WHEN population = 'no_edge' THEN 1 ELSE 0 END) AS no_edge_rows, "
    "  SUM(CASE WHEN population = 'actionable' THEN 1 ELSE 0 END) AS actionable_rows, "
    "  GROUP_CONCAT(DISTINCT event_ticker) AS event_list "
    "FROM scored GROUP BY game_key HAVING kalshi_events > 1 "
    "ORDER BY same_series_extra DESC, kalshi_events DESC, game_key"
)

# Section H -- the rows section D does NOT count, so 5,670 is not read as "the
# record". `clustered_clv` filters `clv_horizon_hours = :horizon`, and the v5
# migration left legacy rows tagged 1.0h that will never be re-scored at 0.0
# and never count toward the gate. Printing the split stops a future reader
# reconciling section A's totals against section D's and finding a silent gap.
_SQL_CLV_SCORED_BY_HORIZON = (
    "SELECT COALESCE(r.clv_horizon_hours, -1.0) AS clv_horizon_hours, "
    "  COUNT(*) AS scored_rows, "
    "  SUM(CASE WHEN r.clv_tenths IS NULL THEN 1 ELSE 0 END) AS clv_tenths_null, "
    "  COUNT(DISTINCT r.ticker) AS distinct_tickers "
    "FROM recommendations r WHERE r.clv_scored_ms IS NOT NULL "
    "GROUP BY clv_horizon_hours ORDER BY clv_horizon_hours"
)

_SQL_CLV_LINK_FANOUT = (
    "SELECT kalshi_event_ticker, "
    "  COUNT(DISTINCT odds_event_id) AS distinct_odds_event_ids, "
    "  MIN(linked_ms) AS first_linked_ms, MAX(linked_ms) AS last_linked_ms "
    "FROM event_links GROUP BY kalshi_event_ticker "
    "HAVING distinct_odds_event_ids > 1 "
    "ORDER BY distinct_odds_event_ids DESC, kalshi_event_ticker"
)


# ---------------------------------------------------------------------------
# The prop rung dump, for the one-sided recovery registration.
#
# Registered at
# `docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md`,
# whose §8 is why this emits **rows and not a verdict**: this script is not a
# measurement harness, so every quantity the decision rule reads is computed
# by `scripts/analyze_prop_onesided.py` from this query's `--json`, beside
# the rule it feeds.
#
# **The rest of the commentary that stood here moved to that document's
# appendix on 2026-09-06**, verbatim, because this file crossed the Read-tool
# ceiling. Read it there before changing the query below.
#
# **`--odds-event-id` never bounded this query, and the obvious fix does not
# either. Measured 2026-09-15, not reasoned about.**
#
# The defect as recorded in ADR 0157: the `prop` CTE selects every row carrying
# an `outcome_description`, `latest` groups over that, and `:event` was applied
# only at the OUTER level -- so naming a fixture discarded the other fixtures'
# rows after everything had already been read. The proposed fix was to push
# `(:event IS NULL OR odds_event_id = :event)` down into the CTE.
#
# That push-down **changes no plan at all.** With the OR-form in the CTE,
# `EXPLAIN QUERY PLAN` is byte-identical to the version without it, for both a
# named fixture and no flag:
#
#     CO-ROUTINE latest
#     SCAN odds_snapshots USING INDEX idx_odds_event_commence   <- still whole
#     SCAN l
#     SEARCH odds_snapshots USING INDEX idx_odds_event_commence (odds_event_id=?)
#
# SQLite cannot turn `(:param IS NULL OR col = :param)` into a seek, because
# the parameter's nullity is unknown when the statement is planned; it must
# emit a plan that is correct for NULL, and that plan is a scan. (The `SEARCH`
# line above is the JOIN on `l.odds_event_id`, not the flag -- it is there with
# no flag too, which is what makes the flag's uselessness invisible.)
#
# The form that does seek is a **hard equality**, so the two cases are two
# statements rather than one with a switch in it:
#
#     CO-ROUTINE latest
#     SEARCH odds_snapshots USING INDEX idx_odds_event_commence (odds_event_id=?)
#     SEARCH odds_snapshots USING INDEX idx_odds_event_commence (odds_event_id=?)
#
# Both are constants; `_q_prop_rungs` picks by whether `--odds-event-id` is
# given, and the shared body is written once so the two cannot drift.
#
# **Population-preserving, which is why it needs no registration.** With a
# fixture named, the outer predicate had already discarded every other
# fixture, and `latest` keys `MAX(fetched_ms)` per `odds_event_id`, so
# restricting the CTE cannot move which `(event, fetched_ms)` pair wins. The
# unfiltered statement is unchanged, character for character.
#
# **What was NOT done, and it is not an oversight.** The unfiltered call still
# walks the whole index. A default window would change the population of a
# REGISTERED analysis (`scripts/analyze_prop_onesided.py`), which is a
# pre-registration question and not a cleanup (ADR 0157, "Found while
# verifying"). **Do not run `prop-rungs` without `--odds-event-id` on live
# during a slate.**
_PROP_RUNGS_TEMPLATE = (
    "WITH prop AS ("
    "  SELECT odds_event_id, bookmaker, market, outcome_name, "
    "         outcome_description, outcome_point, price_decimal, fetched_ms "
    "  FROM odds_snapshots WHERE outcome_description IS NOT NULL"
    "{cte_event}"
    "), "
    "latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM prop "
    "  GROUP BY odds_event_id"
    ") "
    "SELECT p.odds_event_id AS odds_event_id, "
    "  p.bookmaker AS bookmaker, "
    "  CASE WHEN substr(p.market, -10) = '_alternate' "
    "       THEN substr(p.market, 1, length(p.market) - 10) "
    "       ELSE p.market END AS base_market, "
    "  CASE WHEN substr(p.market, -10) = '_alternate' "
    "       THEN 1 ELSE 0 END AS is_alternate, "
    "  p.outcome_description AS player, "
    "  p.outcome_point AS point, "
    "  MAX(CASE WHEN p.outcome_name = 'Over' THEN p.price_decimal END) "
    "    AS over_price, "
    "  MAX(CASE WHEN p.outcome_name = 'Under' THEN p.price_decimal END) "
    "    AS under_price, "
    "  COUNT(*) AS quote_rows, "
    "  p.fetched_ms AS fetched_ms "
    "FROM prop p JOIN latest l "
    "  ON l.odds_event_id = p.odds_event_id AND l.m = p.fetched_ms "
    "WHERE p.outcome_name IN ('Over', 'Under') "
    "  AND p.outcome_point IS NOT NULL "
    "  AND (:event IS NULL OR p.odds_event_id = :event) "
    "GROUP BY p.odds_event_id, p.bookmaker, base_market, is_alternate, "
    "         p.outcome_description, p.outcome_point "
    "ORDER BY p.odds_event_id, p.bookmaker, base_market, is_alternate, "
    "         p.outcome_description, p.outcome_point"
)

#: The registered population: every fixture, no bound. Character-for-character
#: what it has always been -- the empty substitution changes nothing.
_SQL_PROP_RUNGS = _PROP_RUNGS_TEMPLATE.format(cte_event="")

#: One fixture, seeking rather than scanning. Same rows as running
#: `_SQL_PROP_RUNGS` and keeping the `:event` rows, which is what the tests
#: assert rather than assume.
_SQL_PROP_RUNGS_ONE_EVENT = _PROP_RUNGS_TEMPLATE.format(
    cte_event="    AND odds_event_id = :event"
)


# ---------------------------------------------------------------------------
# Q-W: the WNBA band-and-depth reachability query.
#
# Registered at
# `docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`
# (§0.4, the block at line 719). §8 makes it a hard precondition: Q-W must have
# been run and reported before the first order of the fee-calibration round.
#
# Every threshold below is a REGISTERED CONSTANT, deliberately not a flag with a
# default. A flag would let a later reader move the bar after seeing the answer,
# which is the entire degree of freedom the registration exists to remove.
# ---------------------------------------------------------------------------

# Four whole game-days. The registration writes the window as "2026-08-07 00:00Z
# to 2026-08-10 23:59Z" and §Limits calls it "four game-days, 2026-08-07 to
# 2026-08-10", so `23:59Z` is the last minute of the fourth day, not a boundary
# that clips its final second. Held half-open [start, end).
_QW_WINDOW_START_MS = int(
    datetime(2026, 8, 7, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
)
_QW_WINDOW_END_MS = int(
    datetime(2026, 8, 11, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
)

# Tenths of a cent. The band is closed at both ends and has a hole at exactly
# 300 -- 27c to 39c, excluding 30c.
_QW_BAND_LO = 270
_QW_BAND_HI = 390
_QW_BAND_HOLE = 300

# Contracts displayed at the derived ask.
_QW_MIN_DEPTH = 1

# Activation: >= 80% of pre-game instants AND >= 8 distinct events.
_QW_MIN_INSTANT_PCT = 80
_QW_MIN_EVENTS = 8

# Fixed substitution order. First series passing BOTH conditions becomes `W`,
# and the substitution is reported in the verdict line.
_QW_SERIES_ORDER = ("KXWNBAGAME", "KXWNBASPREAD", "KXWNBATOTAL")

# ADR 0006. Kalshi's `occurrence_datetime` runs exactly 3 hours late, and
# `kalshi_events.commence_ms` stores it RAW -- `discovery.event_commence_ms`
# (`backend/kalshi/discovery.py:432-447`) returns `parse_ms(occurrence_datetime)`
# with no correction applied. So the correction belongs here. Verified before
# use: had it already been applied at write time, subtracting again would have
# moved every fixture's true start three hours early and silently widened
# "pre-game" by three hours on every row.
_QW_PREGAME_OFFSET_MS = 3 * 60 * 60 * 1000

# The derived ask, and the depth standing at it.
#
# `1000 - no_bid_tenths` is the ask you would pay for YES
# (`backend/store/schema.sql:142-145` -- ask sides are derived at read time,
# never stored). The depth AVAILABLE at that ask is the size of the opposing
# bid, and `backend/runner.py:1030-1037` writes
# `market.no_bid_tenths, market.yes_ask_size` into the column pair
# `(no_bid_tenths, no_bid_qty)`. So the depth for this predicate is
# `no_bid_qty`, NOT `yes_bid_qty`.
#
# This is the trap in the query and it is silent: `yes_bid_qty` is populated on
# essentially every row, so reading depth off it passes almost everything and
# the query would report reachability it never measured.
_QW_ASK = "(1000 - q.no_bid_tenths)"
_QW_DEPTH = "q.no_bid_qty"

_QW_QUALIFIES = (
    f"q.no_bid_tenths IS NOT NULL "
    f"AND {_QW_ASK} >= {_QW_BAND_LO} "
    f"AND {_QW_ASK} <= {_QW_BAND_HI} "
    f"AND {_QW_ASK} <> {_QW_BAND_HOLE} "
    f"AND {_QW_DEPTH} IS NOT NULL AND {_QW_DEPTH} >= {_QW_MIN_DEPTH}"
)

# The pre-game population for one series, before the band is applied. A row is
# in it when it is inside the window and strictly before the fixture's true
# start. `commence_ms IS NULL` drops the row rather than defaulting it: an event
# whose start we cannot determine is not evidence that its quotes were pre-game.
_QW_FROM = (
    "FROM kalshi_quotes q "
    "JOIN kalshi_markets m ON m.ticker = q.ticker "
    "JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
    "WHERE m.series_ticker = :series "
    "AND q.observed_ms >= :start_ms AND q.observed_ms < :end_ms "
    "AND e.commence_ms IS NOT NULL "
    f"AND q.observed_ms < e.commence_ms - {_QW_PREGAME_OFFSET_MS}"
)

# The counts the verdict is computed from. One row by construction, and fetched
# under a cap of its own rather than the caller's `--limit`: the verdict must
# not be derivable from a section that truncation could have trimmed, and
# `--limit 0` would otherwise return no row at all.
_QW_AGGREGATE_CAP = 1

_SQL_QW_COUNTS = (
    "SELECT COUNT(DISTINCT q.observed_ms) AS pregame_instants, "
    f"COUNT(DISTINCT CASE WHEN {_QW_QUALIFIES} THEN q.observed_ms END) "
    "AS qualifying_instants, "
    f"COUNT(DISTINCT CASE WHEN {_QW_QUALIFIES} THEN m.event_ticker END) "
    "AS qualifying_events "
    f"{_QW_FROM}"
)

# The parts, printed beside the aggregate because a pooled percentage is not a
# finding until the per-instant view agrees with it.
_SQL_QW_INSTANTS = (
    "SELECT q.observed_ms, "
    f"COUNT(CASE WHEN {_QW_QUALIFIES} THEN 1 END) AS qualifying_markets, "
    f"COUNT(DISTINCT CASE WHEN {_QW_QUALIFIES} THEN m.event_ticker END) "
    "AS qualifying_events, "
    f"MIN(CASE WHEN {_QW_QUALIFIES} THEN {_QW_ASK} END) AS min_ask_tenths "
    f"{_QW_FROM} GROUP BY q.observed_ms ORDER BY q.observed_ms"
)

_SQL_QW_EVENTS = (
    "SELECT m.event_ticker, COUNT(*) AS qualifying_quotes, "
    "COUNT(DISTINCT q.observed_ms) AS instants, "
    f"MIN({_QW_ASK}) AS min_ask_tenths, MAX({_QW_ASK}) AS max_ask_tenths, "
    f"MIN({_QW_DEPTH}) AS min_depth, "
    # How far ahead the fixture was. Q-W puts no lower bound on this, so a
    # WNBA game ten days out counts toward the 80% on equal footing with one
    # tipping tonight -- on a book that is thin and wide, and that the operator
    # will not find in band on the night. Printed, not filtered: a bound is a
    # registered threshold and this query may not invent one.
    #
    # BOTH stamps are emitted, and the reason is that publishing only the stored
    # one is wrong by three hours. `commence_ms` holds raw `occurrence_datetime`,
    # which ADR 0006 (`docs/adr/0006-in-play-evidence.md:78-84`) identifies as
    # the expected *expiration* -- the end, not the start. A column called
    # `commence_iso` carrying it reads as tip-off and is three hours late; the
    # first published draft of this query's output did exactly that. The derived
    # column is the one to read; the raw one is kept so the offset stays
    # checkable rather than having to be taken on trust.
    "MIN(e.commence_ms) AS occurrence_ms, "
    f"MIN(e.commence_ms) - {_QW_PREGAME_OFFSET_MS} AS true_start_ms, "
    # Half-cent asks inside the band (e.g. 305) satisfy the predicate but round
    # DOWN into the excluded hole at 300 when a limit is placed, so they would
    # be counted reachable and be untakeable. Expected 0 -- `price_grids.json`
    # found 1,426 of 1,426 game-level markets on `linear_cent` -- and this
    # turns that expectation into a measurement. NULL counts as non-linear:
    # unreadable resolves toward attention, never toward "fine".
    "SUM(CASE WHEN COALESCE(m.price_structure, 'unknown') <> 'linear_cent' "
    "THEN 1 ELSE 0 END) AS non_linear_cent_quotes "
    f"{_QW_FROM} AND {_QW_QUALIFIES} "
    "GROUP BY m.event_ticker ORDER BY m.event_ticker"
)


def _q_results_for_pull(conn: sqlite3.Connection, args) -> list[Section]:
    return [
        _fetch(
            conn,
            _SQL_RESULTS_FOR_PULL,
            {"pin": args.pin},
            title=f"kalshi_markets for recommendations.id <= {args.pin}",
            cap=args.limit,
        )
    ]


def _q_events_for_pull(conn: sqlite3.Connection, args) -> list[Section]:
    return [
        _fetch(
            conn,
            _SQL_EVENTS_FOR_PULL,
            {"pin": args.pin},
            title=f"kalshi_events reached by recommendations.id <= {args.pin}",
            cap=args.limit,
        )
    ]


def _q_closing_lines_for_pull(conn: sqlite3.Connection, args) -> list[Section]:
    return [
        _fetch(
            conn,
            _SQL_CLOSING_LINES_FOR_PULL,
            {"pin": args.pin},
            title=f"closing_lines for recommendations.id <= {args.pin}",
            cap=args.limit,
        )
    ]


def _q_series(conn: sqlite3.Connection, args) -> list[Section]:
    return [
        _fetch(
            conn,
            _SQL_SERIES,
            (),
            title="kalshi_series: ticker and league",
            cap=args.limit,
        )
    ]


def _q_prop_bookmakers(conn: sqlite3.Connection, args) -> list[Section]:
    """Which books returned props, keyed off the schema's own discriminator.

    `outcome_description` is NULL on every team market and populated on every
    prop -- `store/schema.sql` says so in the column's own comment, because a
    prop's outcome is `(player, side, line)` and the player has nowhere else to
    live. Selecting on it rather than on a hardcoded list of the ten prop market
    keys keeps this query from drifting out of step with `PROP_MARKETS`.

    `--since YYYYMMDD` moves the `commence_ms` floor; `--sport` cuts to one
    `sport_key`. Both are bounds before they are filters -- see the comment on
    the SQL.

    What this does not establish
    ----------------------------
    - **Nothing about books that were never asked for.** A book absent here is
      absent from the *response*, and since ADR 0155 the request names ten
      books by key: a book outside that ten cannot appear however many props it
      quotes. Read this beside `ODDS_BOOKMAKERS`, never alone.
    - **Nothing about a misspelled key.** A key the vendor does not recognise
      is silently absent from the response and still consumes one of the ten
      slots, so it reads here exactly like a book that quotes no props.
    - **Nothing about price quality** -- presence, not correctness, and a book
      quoting one side of one line counts the same as one quoting every rung.
    """
    since_ms = _bookmakers_since_ms(args)
    scope = f"sport_key = {args.sport!r}" if getattr(args, "sport", None) else "every sport"
    return [
        _window_section(
            "prop-bookmakers window (commence_ms floor)", since_ms, None
        ),
        _fetch(
            conn,
            _SQL_PROP_BOOKMAKERS,
            {"since": since_ms, "sport": getattr(args, "sport", None)},
            title=(
                "odds_snapshots: books that returned a player prop, "
                f"{scope}, commencing at or after {_iso(since_ms)}"
            ),
            cap=args.limit,
        ),
    ]


def _bookmakers_since_ms(args) -> int:
    """The `commence_ms` floor for `prop-bookmakers` and `team-bookmakers`.

    Defaults to a window rather than to no bound: an unbounded default is one a
    session reaches for during a game, which is when it costs the most.

    One helper, because the two subcommands ask the same question of opposite
    sides of one discriminator and a floor that drifted between them would make
    their row counts incomparable. It was named `_prop_since_ms` while only the
    prop side existed; the rename went in with the second caller rather than
    leaving a shared helper named for one of its two users.
    """
    value = getattr(args, "since", None)
    if value is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return now_ms - _BOOKMAKERS_DEFAULT_DAYS * _MS_PER_DAY
    try:
        return _day_bounds(value, args.day_start_hour)[0]
    except ValueError as exc:
        raise ValueError(f"--since must be YYYYMMDD, got {value!r}") from exc


def _requested_bookmakers() -> list[str]:
    """The keys `ODDS_BOOKMAKERS` names, in the order the request sends them.

    Empty list means the variable is unset or blank, which is a real state and
    not a failure: with it unset the client falls back to buying `regions`, and
    then the response is not restricted to a named ten at all. The caller says
    which of those two it is; this returns what is there and infers nothing.
    """
    raw = os.environ.get(_ODDS_BOOKMAKERS_ENV, "").strip()
    return [key.strip() for key in raw.split(",") if key.strip()]


def _requested_books_section() -> Section:
    """The request's own book list, printed beside the response.

    A key here and absent from the data section below is the reading this
    query exists to support -- and it is deliberately NOT computed. Three
    different things put a key here and not there (the book quotes nothing on
    that sport, the sport had no fixture in the window, the key is misspelled
    and the vendor silently dropped it) and they are indistinguishable in this
    table. A column asserting "missing" would name one of the three.
    """
    keys = _requested_bookmakers()
    if not keys:
        return Section(
            title=(
                f"{_ODDS_BOOKMAKERS_ENV} is unset or blank in THIS process's "
                "environment -- so either the request buys regions rather than "
                "named books, or this script is not running where the loop "
                "runs. Nothing is inferred; read the deployed config."
            ),
            columns=("slot", "bookmaker"),
            rows=[],
        )
    return Section(
        title=(
            f"{_ODDS_BOOKMAKERS_ENV}: the {len(keys)} keys the request asks "
            "for. A key absent from the section below was asked for and did "
            "not come back -- which is NOT the same as a book that quotes "
            "nothing (see the docstring)."
        ),
        columns=("slot", "bookmaker"),
        rows=[(i, key) for i, key in enumerate(keys, start=1)],
    )


def _sharp_anchor_since_ms(args) -> int:
    """The `computed_ms` floor for `sharp-anchor-census`.

    A window by default, for the reason `_bookmakers_since_ms` is: the
    unbounded call is the one a session reaches for mid-slate. A malformed
    `--since` raises rather than falling back -- a silently ignored bound is an
    unbounded query wearing a flag.
    """
    value = getattr(args, "since", None)
    if value is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return now_ms - _SHARP_ANCHOR_DEFAULT_DAYS * _MS_PER_DAY
    try:
        return _day_bounds(value, args.day_start_hour)[0]
    except ValueError as exc:
        raise ValueError(f"--since must be YYYYMMDD, got {value!r}") from exc


def _q_sharp_anchor_census(conn: sqlite3.Connection, args) -> list[Section]:
    """How often the consensus had a sharp book to anchor on, per league/market.

    One row per `(league, market, anchored_on_sharp)`, so both the numerator and
    its denominator are on the screen and no ratio is computed here. `links` is
    the clustering unit: rungs inside one fixture are not independent, and
    `rows_n` is the number that will always look larger.

    `--since YYYYMMDD` moves the `computed_ms` floor (default two days);
    `--league` cuts to one `event_links.league`.

    What this does not establish
    ----------------------------
    - **Nothing about WHY a row is unanchored.** The column records that no
      purchased sharp book contributed to that rung. It does not say whether
      the book quoted a different line, quoted one side, failed the devig, or
      never returned at all. `team-bookmakers` is the input side of that and
      is an upper bound on this, never a lower one.
    - **Nothing that a rate over `rows_n` would mean.** A fixture contributes
      one row per rung per pass, so `rows_n` is passes x rungs and is not a
      count of opportunities. Read `links` beside it, and read neither as a
      sample. The two can disagree violently and the disagreement is the
      finding: 902 unanchored `spreads` rows over 17 links is a handful of
      fixtures re-priced many times, not a broad failure.
    - **`links` DOES NOT PARTITION, and this is the easiest mistake here.**
      It is `COUNT(DISTINCT link_id)` computed separately for each value of
      the flag, so a fixture with some anchored rungs and some unanchored ones
      is counted in **both** rows. `23 / 46` is not "23 of 69 fixtures"; the
      two do not sum to a fixture count and their ratio is not a proportion of
      fixtures. Answering "how many fixtures had no sharp anchor anywhere"
      needs a different query, and this one deliberately does not pretend to.
    - **Nothing about whether an unanchored price is WRONG.** The fallback is
      the full usable book set, which is a worse consensus and not a missing
      one; ADR 0068 already shows the flag on the row. This counts how often
      the fallback fired.
    - **Nothing about a league absent from the output.** `--league` takes
        Kalshi's own string and an unrecognised one returns nothing, which
        reads exactly like a league with no rows. Run it unfiltered first.
    """
    since_ms = _sharp_anchor_since_ms(args)
    league = getattr(args, "league", None)
    scope = f"league = {league!r}" if league else "every league"
    return [
        _window_section(
            "sharp-anchor-census window (computed_ms floor)", since_ms, None
        ),
        _fetch(
            conn,
            _SQL_SHARP_ANCHOR_CENSUS,
            {"since": since_ms, "league": league},
            title=(
                "fair_prices x event_links: rows by anchored_on_sharp, per "
                f"league and market, {scope}, computed at or after "
                f"{_iso(since_ms)}. Both values are listed; the denominator "
                "is their sum and no ratio is printed here"
            ),
            cap=args.limit,
        ),
    ]


def _q_team_bookmakers(conn: sqlite3.Connection, args) -> list[Section]:
    """Which books returned TEAM markets, per sport, and on which markets.

    The mirror of `prop-bookmakers` across `outcome_description`: NULL on every
    team market, populated on every prop, per that column's own comment in
    `store/schema.sql`. Selecting on the discriminator rather than on a list of
    market keys keeps this from drifting out of step with `ODDS_MARKETS`.

    `--since YYYYMMDD` moves the `commence_ms` floor (default seven days);
    `--sport` cuts to one `sport_key`. Both are bounds before they are filters.

    Three sections: the window, the keys the REQUEST named, and the response.
    The middle one exists because an absence here has more than one cause and
    the response alone cannot say which.

    What this does not establish
    ----------------------------
    - **Nothing about why a book is absent.** Three causes are
      indistinguishable in this table: the book quotes nothing on that sport,
      the sport had no fixture inside the window, or the key is misspelled and
      the vendor dropped it silently while still charging one of the ten slots.
      A misspelling is the one worth ruling out by eye against slot list.
    - **`markets` names a market, never a RUNG, and the rung is what anchoring
      turns on.** The column is `GROUP_CONCAT(DISTINCT market)`, so `spreads`
      here means "quoted some spread line" and never "quoted the line Kalshi
      lists". `consensus_devig` runs once per rung (`runner.py:1465`, `:1552`)
      and a book joins a rung only if it quoted that exact line two-sided in
      the same sweep (`runner.py:862-875`, `:992-999`). A book can therefore
      be present on every market here and anchor nothing.
    - **Nothing about the sharp anchor's verdict, and this is an UPPER BOUND on
      it.** It reports which books came back; whether `consensus_devig` then
      anchored on a sharp one is recorded per row in
      `fair_prices.anchored_on_sharp`, and `sharp-anchor-census` reads that
      column. Four gaps separate the two -- rung mismatch, one-sided quotes,
      devig failures, commenced games -- and every one can only make the
      measurement smaller than this. Read the measurement; this is its input.
    - **One sweep is one observation.** A fetch that returns 48 rows is one
      vendor response, not 48 observations, and a sport whose fixtures just
      entered the buying horizon will have exactly one. Read `first_fetched_ms`
      against `last_fetched_ms` on every row before quoting `quotes` or
      `events`: when they are equal, both columns describe a single instant.
    - **Nothing about price quality** -- presence, not correctness. A book
      returning one stale outcome counts the same as one quoting every market.
    - **Nothing about a market this instance never buys.** `ODDS_MARKETS`
      bounds the `markets` column from the request side exactly as
      `ODDS_BOOKMAKERS` bounds the book list.
    """
    since_ms = _bookmakers_since_ms(args)
    scope = (
        f"sport_key = {args.sport!r}"
        if getattr(args, "sport", None)
        else "every sport"
    )
    return [
        _window_section(
            "team-bookmakers window (commence_ms floor)", since_ms, None
        ),
        _requested_books_section(),
        _fetch(
            conn,
            _SQL_TEAM_BOOKMAKERS,
            {"since": since_ms, "sport": getattr(args, "sport", None)},
            title=(
                "odds_snapshots: books that returned a team market, per sport, "
                f"{scope}, commencing at or after {_iso(since_ms)}"
            ),
            cap=args.limit,
        ),
    ]


def _q_actionable_audit(conn: sqlite3.Connection, args) -> list[Section]:
    """Every row the strategy would have bet, with its whole provenance.

    **This exists because `actionable` stopped being zero on 2026-08-16 and no
    instrument could show the rows** -- `clv-coverage` section D counts the
    population, and `/api/ledger` in a browser is a screenshot, not a record.

    Rule 1 of this repo is that a large apparent edge is a bug until proven
    otherwise, so the sections are split by *who computed the number*:

    - **A** is what the engine decided: the price it would pay, the edge it
      claimed, the sizes at both bankrolls, and the four clocks.
    - **B** is where the fair value came from: all four devig methods
      side by side, the book count, the sharp anchor, and the market width.

    Reading A without B is how a method-choice artefact gets written down as an
    edge. The four `p_*` columns are printed unaggregated and un-spread, on
    purpose -- the spread between them is the noise floor the edge has to clear,
    and this script does not compute it, because a printed difference invites
    being quoted without the per-row context that makes it meaningful.

    What this does not establish
    ----------------------------
    - **Nothing about whether the rows are right.** It prints the inputs to that
      judgement and no verdict. `suppression.py` holds the thresholds; compare
      by hand or send the rows to `measurement-skeptic`.
    - **Nothing about causation.** `created_ms` beside `last_confirmed_ms` lets
      a reader ask whether a row predates a deploy. It does not say what the
      deploy did, and a row confirmed after one may have been sound before it.
    - **Nothing about buyability.** `reference_contracts` is the fixed
      $1,000 profile (ADR 0015). `suggested_contracts` is the deployed
      bankroll. A row can be evidence at the first and unbuyable at the second;
      both columns are printed so the two questions stay apart.
    - **It is a census of the actionable set at one instant.** Rows are written
      only when the ask or the fair value changes (`persist_if_changed`), so an
      absent row is not a market that never qualified.
    """
    rows = _derive_iso(
        _derive_iso(
            _fetch(
                conn,
                _SQL_ACTIONABLE_ROWS,
                (),
                title="A. actionable rows: the decision (newest first)",
                cap=args.limit,
            ),
            "created_ms",
            "created_iso",
        ),
        "last_confirmed_ms",
        "last_confirmed_iso",
    )
    provenance = _derive_iso(
        _fetch(
            conn,
            _SQL_ACTIONABLE_FAIR,
            (),
            title="B. the same rows: where the fair value came from",
            cap=args.limit,
        ),
        "computed_ms",
        "computed_iso",
    )
    return [rows, provenance]


def _q_clv_coverage(conn: sqlite3.Connection, args) -> list[Section]:
    """Does CLV scoring reach every market type, what does it retry, and what
    does the gate count as one game?

    Six sections, and section B is the one with a running cost attached: its
    `started` column, doubled, is how many candlestick requests each full pass
    spends on tickers that have not scored -- forever, because
    `markets_awaiting_scoring` has no retry cap and no age cutoff.

    `now` is stamped once, here, and printed in section B's title. A `started`
    count is a claim about a moment, and a moment that is not written down is
    the kind of input this repo has been bitten by losing.
    """
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    horizon = {"horizon": _CLV_GATE_HORIZON_HOURS}

    rows_by_type = _fetch(
        conn,
        _SQL_CLV_ROWS_BY_TYPE,
        (),
        title="A. recommendations by market type: scored, pending, distinct tickers",
        cap=args.limit,
    )
    pending = _derive_iso(
        _fetch(
            conn,
            _SQL_CLV_PENDING_RETRY,
            {"now": now_ms},
            title=(
                "B. the re-request set (scoring.markets_awaiting_scoring), as at "
                f"{_iso(now_ms)}. Each `started` ticker costs TWO candlestick "
                "requests per full pass, and is never retired"
            ),
            cap=args.limit,
        ),
        "oldest_commence_ms",
        "oldest_commence_iso",
    )
    lines = _derive_iso(
        _derive_iso(
            _fetch(
                conn,
                _SQL_CLV_LINES_BY_SERIES,
                (),
                title=(
                    "C. closing_lines by series and horizon. A prop series absent "
                    "here, with started > 0 in B, was asked and answered nothing"
                ),
                cap=args.limit,
            ),
            "first_observed_ms",
            "first_observed_iso",
        ),
        "last_observed_ms",
        "last_observed_iso",
    )
    by_population = _fetch(
        conn,
        _SQL_CLV_CLUSTERS_BY_POPULATION,
        dict(horizon),
        title=(
            "D. the gate's cluster count vs one-cluster-per-game, by population, "
            f"at horizon {_CLV_GATE_HORIZON_HOURS}h"
        ),
        cap=args.limit,
    )
    pooled = _fetch(
        conn,
        _SQL_CLV_CLUSTERS_POOLED,
        dict(horizon),
        title=(
            "D. pooled -- computed separately, because the populations partition "
            "the rows but NOT the games"
        ),
        cap=args.limit,
    )
    by_type = _fetch(
        conn,
        _SQL_CLV_CLUSTERS_BY_TYPE,
        dict(horizon),
        title=(
            "F. the same split, by market type -- which market types actually "
            "carry the gap between clusters_now and clusters_by_game"
        ),
        cap=args.limit,
    )
    collapses = _fetch(
        conn,
        _SQL_CLV_COLLAPSES,
        dict(horizon),
        title=(
            "G. every game whose rows span more than one Kalshi event. "
            "same_series_extra = 0 is the collapse ADR 0029 describes; ANY "
            "NON-ZERO needs reading -- it is two events of one series on one "
            "fixture, i.e. a relist or a MERGE OF TWO REAL GAMES"
        ),
        cap=args.limit,
    )
    horizons = _fetch(
        conn,
        _SQL_CLV_SCORED_BY_HORIZON,
        (),
        title=(
            "H. scored rows by horizon. Only the section D horizon is counted "
            "by the gate; the rest are legacy tags that never will be"
        ),
        cap=args.limit,
    )
    fanout = _derive_iso(
        _fetch(
            conn,
            _SQL_CLV_LINK_FANOUT,
            (),
            title=(
                "E. Kalshi events linked to MORE than one sportsbook fixture. "
                "ZERO ROWS IS THE CORRECT ANSWER -- any row here splits one "
                "game back into several clusters, permissively"
            ),
            cap=args.limit,
        ),
        "first_linked_ms",
        "first_linked_iso",
    )
    return [
        rows_by_type,
        pending,
        lines,
        by_population,
        pooled,
        by_type,
        collapses,
        horizons,
        fanout,
    ]


def _q_prop_rungs(conn: sqlite3.Connection, args) -> list[Section]:
    """Raw prop rungs, two sides pivoted, for the one-sided recovery run.

    **Truncation is the failure mode to watch here, and it is not silent.** The
    live record held ~16,000 prop quotes on 2026-08-15, several times the
    default cap, so a whole-record dump WILL truncate and will say so. The
    registered analysis reads one sweep per fixture and needs every rung of the
    fixtures it reads, so the intended use is either `--odds-event-id` per
    fixture or an explicitly raised `--limit`. A truncated dump is not a
    smaller sample of the population -- `ORDER BY` makes it the alphabetical
    front of it -- and `analyze_prop_onesided.py` refuses one outright rather
    than reporting a verdict over a prefix.
    """
    event = args.odds_event_id
    scope = f"odds_event_id = {event}" if event else "all fixtures"
    # Two statements, not one with a switch: SQLite cannot seek on the
    # `(:event IS NULL OR ...)` form, so the bounded case needs a hard
    # equality in the CTE. See the comment on `_PROP_RUNGS_TEMPLATE` -- the
    # plans were measured, and the OR-form's is identical to no predicate at
    # all. The unfiltered statement is the registered population and is
    # unchanged.
    sql = _SQL_PROP_RUNGS_ONE_EVENT if event else _SQL_PROP_RUNGS
    return [
        _fetch(
            conn,
            sql,
            {"event": event},
            title=(
                "odds_snapshots: prop rungs at the latest sweep per fixture "
                f"({scope})"
            ),
            cap=args.limit,
        )
    ]


@dataclass(frozen=True)
class QWVerdict:
    """One series' Q-W counts and whether they activate `W`.

    `instant_pct` is `None`, never `0.0`, when no pre-game instant exists. A
    series with nothing to measure has not failed the 80% bar -- it could not
    reach it -- and this repo has already published one zero that meant "could
    not fire" while reading as "fired and caught nothing" (`c4bca6b`,
    `tasks/NEXT.md` §3).
    """

    series: str
    pregame_instants: int
    qualifying_instants: int
    qualifying_events: int
    instant_pct: Optional[float]
    activates: bool
    note: str


def _qw_verdict(conn: sqlite3.Connection, series: str) -> QWVerdict:
    """Score one series against Q-W's two registered conditions.

    The percentage test is integer arithmetic --
    `qualifying * 100 >= 80 * pregame` -- not a float comparison against 80.0.
    At the bar itself (4 of 5 instants) the float route is a coin toss on
    representation, and the bar is exactly where a registered threshold has to
    be exact.
    """
    counts = _fetch(
        conn,
        _SQL_QW_COUNTS,
        {
            "series": series,
            "start_ms": _QW_WINDOW_START_MS,
            "end_ms": _QW_WINDOW_END_MS,
        },
        title=f"Q-W counts: {series}",
        cap=_QW_AGGREGATE_CAP,
    )
    pregame, qualifying, events = counts.rows[0]

    if pregame == 0:
        return QWVerdict(
            series=series,
            pregame_instants=0,
            qualifying_instants=qualifying,
            qualifying_events=events,
            instant_pct=None,
            activates=False,
            note="NO PRE-GAME INSTANTS - could not fire, not measured and failed",
        )

    pct_met = qualifying * 100 >= _QW_MIN_INSTANT_PCT * pregame
    events_met = events >= _QW_MIN_EVENTS
    if pct_met and events_met:
        note = "ACTIVATES"
    else:
        unmet = []
        if not pct_met:
            unmet.append(f"instant share < {_QW_MIN_INSTANT_PCT}%")
        if not events_met:
            unmet.append(f"events < {_QW_MIN_EVENTS}")
        note = "does not activate: " + ", ".join(unmet)

    return QWVerdict(
        series=series,
        pregame_instants=pregame,
        qualifying_instants=qualifying,
        qualifying_events=events,
        instant_pct=round(100.0 * qualifying / pregame, 2),
        activates=pct_met and events_met,
        note=note,
    )


def _q_kalshi_quotes_band(conn: sqlite3.Connection, args) -> list[Section]:
    """Q-W: was a 27-39c (excl. 30c) WNBA market reachable pre-game?

    Walks `_QW_SERIES_ORDER` and stops at the first series that activates. Every
    series attempted is reported, so a substitution is visible rather than
    inferred -- the registration requires the substitution to be named in the
    verdict line.

    The detail sections describe the DECIDING series: the one that activated,
    or the last one attempted when none did.
    """
    verdicts: list[QWVerdict] = []
    for series in _QW_SERIES_ORDER:
        verdicts.append(_qw_verdict(conn, series))
        if verdicts[-1].activates:
            break

    deciding = next((v for v in verdicts if v.activates), verdicts[-1])

    verdict_section = Section(
        title=(
            f"Q-W verdict: W {'ACTIVATES' if deciding.activates else 'IS NOT REGISTERED'}"
            f" (bars: >= {_QW_MIN_INSTANT_PCT}% of pre-game instants,"
            f" >= {_QW_MIN_EVENTS} distinct events)"
        ),
        columns=(
            "series_ticker",
            "pregame_instants",
            "qualifying_instants",
            "instant_pct",
            "qualifying_events",
            "activates",
            "note",
        ),
        rows=[
            (
                v.series,
                v.pregame_instants,
                v.qualifying_instants,
                v.instant_pct,
                v.qualifying_events,
                1 if v.activates else 0,
                v.note,
            )
            for v in verdicts
        ],
    )

    params = {
        "series": deciding.series,
        "start_ms": _QW_WINDOW_START_MS,
        "end_ms": _QW_WINDOW_END_MS,
    }
    instants = _fetch(
        conn,
        _SQL_QW_INSTANTS,
        params,
        title=(
            f"{deciding.series}: every pre-game polling instant, and how many "
            "markets in band with depth at each"
        ),
        cap=args.limit,
    )
    events = _fetch(
        conn,
        _SQL_QW_EVENTS,
        params,
        title=f"{deciding.series}: distinct events contributing a qualifying market",
        cap=args.limit,
    )

    return [
        _window_section(
            "Q-W window (registered)", _QW_WINDOW_START_MS, _QW_WINDOW_END_MS
        ),
        verdict_section,
        _derive_iso(instants, "observed_ms", "observed_iso"),
        _derive_iso(
            _derive_iso(events, "occurrence_ms", "occurrence_iso"),
            "true_start_ms",
            "true_start_iso",
        ),
    ]
# ---------------------------------------------------------------------------
# fair-prices-by-market: is a bought input actually consumed at runtime?
# ---------------------------------------------------------------------------
#
# **The general form of a question this repo keeps asking one instance at a
# time.** `ODDS_MARKETS` went from `h2h` to `h2h,spreads` on 2026-08-23 and
# doubled the per-sweep cost. Nothing on the machine could say whether the
# second half was read by anything -- the money leaves through
# `api_credits`, the rows land in `odds_snapshots`, and whether they reach a
# decision is a question about `fair_prices`, which no inspector query
# touched. It was settled on 2026-09-05 by ad-hoc SQL over ssh, which is the
# "smuggle the code in with the question" drift this file exists to replace.
#
# The two sections are the point, and neither is the answer on its own: A is
# what was BOUGHT (`odds_snapshots`, one row per book-outcome we paid for) and
# B is what was CONSUMED (`fair_prices`, one row per devigged outcome the
# strategy could act on). A market in A and absent from B is a line item with
# no reader.
#
# **This is a census and not an estimate.** Both sections are exhaustive
# `COUNT(*)` over a fixed snapshot grouped by one key -- no sample, no null,
# no standard error -- and no ratio between them is printed. The comparison is
# made by the reader, with both denominators on the screen.

#: Default lookback for both halves of `fair-prices-by-market`, in days.
#:
#: Seven, matching `_BOOKMAKERS_DEFAULT_DAYS` rather than
#: `_SHARP_ANCHOR_DEFAULT_DAYS`' two, and for a reason that is about the
#: question rather than about the table: section A reads the same rows on the
#: same clock as `team-bookmakers`, and a reader comparing "what came back" to
#: "what was consumed" across the two commands must not be comparing two
#: windows. Seven days also spans one full weekly sports cycle, so a market
#: bought only on NFL Sunday is inside it on a Wednesday.
_FAIR_PRICES_DEFAULT_DAYS = 7

#: **The two sections are bounded on DIFFERENT CLOCKS, and it is not a
#: sloppiness that could be tidied away.**
#:
#: Section B keys on `computed_ms` -- when *we* devigged -- because that is the
#: only time column `fair_prices` has, and `idx_fair_market_computed` is the
#: index a bound there can be served from. Section A keys on `commence_ms` --
#: when the *game* starts -- because `idx_odds_commence` is the only index on
#: `odds_snapshots` that a floor can seek, `fetched_ms` leads none of them, and
#: an instrument that scans the largest table on the box to save retyping one
#: column name is the thing ADR 0157 forbids.
#:
#: So a row can be in A's window and out of B's, or the reverse: a fixture
#: bought on Monday for a Sunday game is inside A's seven days from Monday
#: *and* from the following Saturday, while the `fair_price` computed from it
#: leaves B's window seven days after the devig. The two windows are printed as
#: their own sections, each naming its clock, for exactly this reason -- and no
#: ratio between the sections is computed here, which was already true for the
#: row-grain reason and is now true twice over.
_SQL_FAIR_PRICES_BY_MARKET = (
    "SELECT market, COUNT(*) AS rows_n, "
    "COUNT(DISTINCT link_id) AS links, "
    "MIN(computed_ms) AS first_ms, MAX(computed_ms) AS last_ms "
    "FROM fair_prices WHERE computed_ms >= :since "
    "GROUP BY market ORDER BY rows_n DESC, market"
)

_SQL_ODDS_SNAPSHOTS_BY_MARKET = (
    "SELECT market, COUNT(*) AS rows_n, "
    "COUNT(DISTINCT odds_event_id) AS fixtures, "
    "COUNT(DISTINCT bookmaker) AS books, "
    "MIN(fetched_ms) AS first_ms, MAX(fetched_ms) AS last_ms "
    "FROM odds_snapshots WHERE commence_ms >= :since "
    "GROUP BY market ORDER BY rows_n DESC, market"
)


def _fair_prices_since_ms(args) -> int:
    """The floor both halves of `fair-prices-by-market` are bounded by.

    One helper and one value for the two sections, for the reason
    `_bookmakers_since_ms` is one helper for two subcommands: a floor that
    drifted between them would make the two sections' counts incomparable, and
    comparing them is the entire purpose of the command. The COLUMN each
    section applies it to differs -- see the note above the statements -- and
    that is stated rather than hidden.

    A malformed `--since` raises rather than falling back: a silently ignored
    bound is an unbounded query wearing a flag (ADR 0157).
    """
    value = getattr(args, "since", None)
    if value is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return now_ms - _FAIR_PRICES_DEFAULT_DAYS * _MS_PER_DAY
    try:
        return _day_bounds(value, args.day_start_hour)[0]
    except ValueError as exc:
        raise ValueError(f"--since must be YYYYMMDD, got {value!r}") from exc


def _q_fair_prices_by_market(conn: sqlite3.Connection, args) -> list[Section]:
    """What the feed bought, beside what the strategy actually consumed.

    Section A is `odds_snapshots` by `market` -- every book-outcome the odds
    feed was paid for. Section B is `fair_prices` by `market` -- every
    devigged outcome a recommendation could have been built on. A market
    present in A and absent from B is an input bought and read by nothing.

    **Read the clocks, not just the counts.** `last_ms` is the answer to "is
    it consumed *now*": a market with millions of rows whose newest is three
    weeks old was consumed by a code path that has since stopped running, and
    a count alone reports that as healthy.

    `--since YYYYMMDD` moves the floor; it defaults to seven days. Both
    sections take the same instant and apply it to a different column --
    A to `commence_ms`, B to `computed_ms` -- and each window is printed as
    its own section saying which. ADR 0159.

    What this does not establish
    ----------------------------
    - **Nothing about cost.** `market` here is the Odds API market key; what
      a sweep was billed is `api_credits.cost`, and the two are joined by
      nobody. `credits-by-sport` is the money side.
    - **Nothing about a market being USEFUL.** A row in `fair_prices` means a
      fair value was computed, not that it reached a recommendation, not that
      the recommendation survived suppression, and not that the number was
      any good. This is a reachability check, and reachability is the
      weakest of those four claims.
    - **Nothing about retention, and since ADR 0159 not even about the
      surviving record.** `first_ms` used to be where the surviving rows
      started; it is now the window floor or the first row after it, which is
      a different quantity wearing the same column name. A lifetime census
      needs `--since` set back explicitly and costs what an unbounded scan
      costs. `odds_snapshots` and `fair_prices` are also pruned on different
      schedules, so a later `first_ms` in one section was never a later start
      either.
    - **Nothing that compares the two sections' windows.** They are one
      instant applied to two clocks, so a fixture can be inside A's and
      outside B's, or the reverse. A market thin in B and fat in A may be an
      input with no reader -- the finding this command exists for -- or may be
      a market whose devig happened to fall outside seven days. Widen
      `--since` before believing the first reading.
    - **In section A, the column BOUNDED and the columns REPORTED are not the
      same column.** The floor is on `commence_ms`; `first_ms` and `last_ms`
      are `fetched_ms`. So a row fetched three months ago for a fixture that
      started yesterday is inside the window, and A's `first_ms` can be far
      older than the floor printed above it. That pairing is deliberate --
      "when did we last buy this market" is the health question, and
      `commence_ms` is the only column an index can bound -- but `first_ms`
      here is NOT the window and must never be read as one. Section B has one
      column doing both jobs and does not have this hazard.
    - **No ratio between the sections**, deliberately. They have different
      row grains -- A is per book per outcome, B is per devigged outcome --
      so their counts are not comparable and dividing them would invent a
      quantity neither table supports.
    """
    since_ms = _fair_prices_since_ms(args)
    bought = _fetch(
        conn,
        _SQL_ODDS_SNAPSHOTS_BY_MARKET,
        {"since": since_ms},
        title=(
            "A. BOUGHT -- odds_snapshots by market (per book, per outcome), "
            f"fixtures commencing at or after {_iso(since_ms)}"
        ),
        cap=args.limit,
    )
    bought = _derive_iso(bought, "first_ms", "first_iso")
    bought = _derive_iso(bought, "last_ms", "last_iso")

    consumed = _fetch(
        conn,
        _SQL_FAIR_PRICES_BY_MARKET,
        {"since": since_ms},
        title=(
            "B. CONSUMED -- fair_prices by market (per devigged outcome), "
            f"computed at or after {_iso(since_ms)}"
        ),
        cap=args.limit,
    )
    consumed = _derive_iso(consumed, "first_ms", "first_iso")
    consumed = _derive_iso(consumed, "last_ms", "last_iso")
    return [
        _window_section(
            "A's window -- odds_snapshots.commence_ms floor (when the GAME "
            "starts)",
            since_ms,
            None,
        ),
        bought,
        _window_section(
            "B's window -- fair_prices.computed_ms floor (when WE devigged). "
            "Same instant as A, different COLUMN, so a fixture can be inside "
            "one window and outside the other",
            since_ms,
            None,
        ),
        consumed,
    ]
