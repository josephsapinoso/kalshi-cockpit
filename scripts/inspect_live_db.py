"""Read-only inspector for the live SQLite database, invoked by path.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_db.py credits-tail"

Why this file exists
--------------------
`flyctl ssh console` against `kalshi-cockpit` is permitted **only to invoke a
committed, reviewed script by path**. No interactive session, no filesystem
browsing, and nothing that carries its own source in the command line. The
point of the rule is that every line that runs against the money box was
reviewable in git before it ran, and a permission pattern matches a command
prefix -- it cannot see inside the quotes -- so the rule is a convention the
agent keeps and Joe audits, not something the grant enforces.

Until this file shipped, the live box had no script that could answer a
question, so the only way to ask one was to smuggle the code in with the
question. That is the drift this replaces. It is deliberately **one** artefact
with a **fixed whitelist of named queries**: reviewed once, safe forever,
because a caller can only choose a name, never supply SQL.

Two structural properties, not conventions
------------------------------------------
**Read-only is enforced by the connection**, not by the queries being
well-behaved: the database is opened with `mode=ro`, so SQLite itself refuses
a write. A future edit that adds an `UPDATE` fails at runtime rather than
succeeding quietly.

**No caller-supplied value ever reaches the SQL text.** Every query is a fixed
string constant; every number a caller can influence -- the tail length, the
day boundary, the recommendation pin, the row cap -- is a bound parameter.
There is no table name, column name, or predicate assembled from input.

**This script reached the deployed machine on 2026-08-13, and not before.**
Until then it shipped nowhere, and the reason is worth keeping: `Dockerfile:66`
says `COPY scripts/ ./scripts/`, but `.dockerignore` strips the directory out of
the build context before the Dockerfile ever sees it, re-including named files
only. This one was not among them, so **a deploy alone did not put it there** --
it took an `!scripts/inspect_live_db.py` line as well (`b5419eb`), which is a
widening of what ships to the machine that holds real money and got its own
review.

An earlier version of this paragraph said a new query would be usable "from the
next deploy onward". That was wrong in a way that mattered: it was repeated into
`tasks/NEXT.md` and `start.md` and used to price a decision, and the fee round's
Q-W precondition was planned around a deploy that would have shipped an image
the query still was not in.

**Cite `.dockerignore` and `Dockerfile:66` together or neither**, and do not
quote a script count here -- the previous count in this paragraph ("two of
thirty-four") was stale in both halves. `tests/test_has_callers.py` derives what
the entrypoint needs and asserts the ssh-invoked set by name; read it there
rather than trusting a number in prose.

Before that date this script **had never read the production database**, and its
test suite still does not contradict that: the fixture in
`tests/test_inspect_live_db.py` is a `tmp_path` file built from the schema.
"Exits 0 on a real database" means a real *schema*, not real rows.

What this does not establish
----------------------------
- **Nothing about causation.** It reports rows. `credits-tail` showing a low
  `remaining_reported` is consistent with the budget having latched shut, and
  also with the plan genuinely being near its ceiling; the row does not say
  which, and this script does not model `CreditBudget` at all. Read
  `backend/odds/budget.py:202-223` for the refusal order and decide there.
- **Nothing about completeness.** `credits-day` counts the rows that were
  written. A sweep refused before the request went out writes no `api_credits`
  row by design (see the `odds_sweep_log` comment in `schema.sql`), so a low
  count is an absence of *calls*, not evidence of an outage. `sweep-log` is
  the table that distinguishes those two, which is why it is a separate query.
- **Nothing about correctness of the values.** `remaining_reported` is what
  The Odds API's header said; this script does not reconcile it against our
  own tally. `BudgetState.drift` does that, and it is not computed here.
- **Nothing about the population beyond the pin.** The `*-for-pull` queries
  restrict to `recommendations.id <= --pin` so the population is byte-identical
  to `docs/measurements/2026-08-10-clean-shortfall-pull.json`. Rows created
  after that pin exist and are deliberately excluded; the counts here are not
  "how many games there are".
- **It is not a measurement harness**, with one stated exemption below. It
  prints no aggregates that a finding should be built on without re-deriving
  them: no rates, no per-bucket splits, no significance. `SUM(cost)` and
  `MIN`/`MAX` are otherwise the only arithmetic, and they exist to bound a
  search, not to support a conclusion.
- **The exemption: `clv-coverage` sections D and F are a census, not an
  estimate.** They are per-bucket splits, and the rule above would forbid them.
  They are allowed because `clusters_now` and `clusters_by_game` are exhaustive
  `COUNT(DISTINCT ...)` over a fixed snapshot under two keys -- there is no
  population being sampled, no null, and no standard error, so none of the
  failures the rule protects against are reachable. **A ratio of the two is
  still a derived quantity and is not printed here**; if one is written down it
  must carry the snapshot instant, the horizon, and the attribution from
  section G. `prop-rungs` handles the same tension the other way, by deferring
  every derived quantity to `scripts/analyze_prop_onesided.py`, and that
  remains the default for anything with a decision rule attached.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

# The live volume. `cockpit.db`, not `kalshi.db` -- the repo-root `kalshi.db`
# is a local scratch file and the two names have been confused before.
DEFAULT_DB = "/data/cockpit.db"

# A mistake must not be able to dump the whole database into a transcript.
DEFAULT_ROW_CAP = 2000

# Matches `budget_day_start_utc_hour`. The sports day rolls at 10:00 UTC so a
# late West Coast game shares a budget bucket with the rest of its night.
DEFAULT_DAY_START_HOUR = 10

_MS_PER_DAY = 86_400_000


class UnknownQuery(Exception):
    """Raised for a query name that is not on the whitelist.

    A named exception rather than a `None` return, because the failure mode
    being prevented is a typo'd query name that produces empty output and
    reads as "nothing to report".
    """


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


@dataclass
class Section:
    """One labelled result block: columns, rows, and how many there were.

    `row_count` is carried explicitly rather than left to `len(rows)` at the
    render site so that both renderers state it and neither can accidentally
    print an empty block that reads as success.
    """

    title: str
    columns: tuple[str, ...]
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    truncated: bool = False
    cap: Optional[int] = None

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _iso(ms: Optional[int]) -> Optional[str]:
    """Render epoch milliseconds as an ISO-8601 UTC stamp, or `None`.

    `None` in, `None` out -- never the epoch. A missing timestamp rendered as
    `1970-01-01T00:00:00Z` is a fabricated observation, and this project has
    already been bitten once by an absence borrowing a present value's
    representation.
    """
    if ms is None:
        return None
    return (
        datetime.fromtimestamp(ms / 1000, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _fetch(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] | dict[str, Any],
    *,
    title: str,
    cap: int,
    requested: Optional[int] = None,
) -> Section:
    """Run one fixed SQL string under the row cap and report truncation.

    The cap is applied by appending `LIMIT ?` and binding `effective + 1`: if
    the extra row comes back, more rows existed and the caller is told so. A
    cap that silently trimmed would turn "there are 40,000 of these" into
    "there are 2,000 of these", which is the shape of error this repo's
    measurement rules exist to catch.

    `requested` is a query's own N (e.g. `credits-tail -n 5`). When the
    query's own N binds, that is the caller getting what they asked for and no
    truncation is reported; when the hard cap binds, it is.
    """
    effective = cap if requested is None else min(requested, cap)
    effective = max(0, effective)
    # sqlite3 refuses to mix named and positional placeholders in one
    # statement, so the cap's placeholder has to match the query's style.
    suffix = f" LIMIT {_LIMIT_TOKEN}" if isinstance(params, dict) else " LIMIT ?"
    cur = conn.execute(sql + suffix, _bind(params, effective + 1))
    rows = cur.fetchall()
    columns = tuple(d[0] for d in cur.description)
    truncated = len(rows) > effective and effective == cap
    return Section(
        title=title,
        columns=columns,
        rows=[tuple(r) for r in rows[:effective]],
        truncated=truncated,
        cap=cap,
    )


# Named-parameter queries need the cap bound by name too. The token and the
# key are derived from one string so the two halves cannot drift apart.
_LIMIT_KEY = "__limit"
_LIMIT_TOKEN = f":{_LIMIT_KEY}"


def _bind(
    params: Sequence[Any] | dict[str, Any], limit: int
) -> Sequence[Any] | dict[str, Any]:
    """Append the cap to positional params, or add it to named ones."""
    if isinstance(params, dict):
        out = dict(params)
        out[_LIMIT_KEY] = limit
        return out
    return list(params) + [limit]


def _derive_iso(section: Section, ms_column: str, iso_column: str) -> Section:
    """Add an ISO rendering of a millisecond column already in the output.

    This adds no data. Every ISO column here is a second view of a column the
    query already selected, which is why it does not breach the rule that this
    script prints no column outside the named set.
    """
    if ms_column not in section.columns:
        raise KeyError(f"{ms_column!r} is not in {section.columns!r}")
    idx = section.columns.index(ms_column)
    section.columns = (
        section.columns[: idx + 1] + (iso_column,) + section.columns[idx + 1 :]
    )
    section.rows = [
        row[: idx + 1] + (_iso(row[idx]),) + row[idx + 1 :] for row in section.rows
    ]
    return section


# ---------------------------------------------------------------------------
# The whitelist. Every SQL string below is a constant.
# ---------------------------------------------------------------------------

# `trigger` is quoted because it is a SQLite keyword, and it is selected because
# the sweep banner's predicate turns on it: a row counts as a *served* sweep only
# when `endpoint LIKE '%/odds' AND cost > 0 AND COALESCE(trigger, '') != 'manual'`
# (`backend/odds/timing.py`, `_SERVED_SWEEP`). Without this column the output
# cannot tell a hand refresh from a scheduled sweep, so a day whose only `/odds`
# rows were taps reads exactly like a day that swept -- an instrument blind to
# the one clause under investigation. See `tasks/lessons.md`.
_CREDIT_COLUMNS = (
    'called_ms, endpoint, sport_key, markets, regions, cost, '
    'remaining_reported, used_reported, "trigger"'
)
# `markets` and `regions` are here for the same reason `trigger` is, and the
# omission had the same shape. `cost` is `len(markets) * len(regions)`, so a row
# recording 6 credits was bought under three markets and one recording 2 under
# one -- but reading the *cost* to infer the *config* is an inference, and the
# row carries both directly. When `ODDS_MARKETS` changed from three markets to
# `h2h` on 2026-08-16, the only available confirmation that the deployed image
# had picked it up was the machine's environment, which says what the process
# was started with rather than what it sent. These two columns say what was
# sent. `"trigger"` stays quoted because it is a SQL keyword; the other two are
# not.

_SQL_CREDITS_TAIL = (
    f"SELECT {_CREDIT_COLUMNS} FROM api_credits ORDER BY called_ms DESC"
)

_SQL_CREDITS_DAY_ROWS = (
    f"SELECT {_CREDIT_COLUMNS} FROM api_credits "
    "WHERE called_ms >= ? AND called_ms < ? ORDER BY called_ms"
)

_SQL_CREDITS_DAY_TOTALS = (
    "SELECT COUNT(*) AS rows_in_day, COALESCE(SUM(cost), 0) AS total_cost "
    "FROM api_credits WHERE called_ms >= ? AND called_ms < ?"
)

_SQL_CREDITS_MONTH = (
    "SELECT COUNT(*) AS rows_month_to_date, "
    "COALESCE(SUM(cost), 0) AS total_cost, "
    "MIN(remaining_reported) AS min_remaining_reported, "
    "MAX(remaining_reported) AS max_remaining_reported, "
    "MIN(used_reported) AS min_used_reported, "
    "MAX(used_reported) AS max_used_reported "
    "FROM api_credits WHERE called_ms >= ?"
)

_SQL_SWEEP_LOG_GROUPS = (
    "SELECT outcome, COUNT(*) AS n, MIN(pass_ms) AS min_pass_ms, "
    "MAX(pass_ms) AS max_pass_ms FROM odds_sweep_log "
    "GROUP BY outcome ORDER BY outcome"
)

_SQL_SWEEP_LOG_TAIL = (
    "SELECT id, pass_ms, sport_key, outcome, detail, quotes_stored "
    "FROM odds_sweep_log ORDER BY pass_ms DESC, id DESC"
)

# **The gaps in the pass ledger, which is how an outage is actually found.**
#
# `odds_sweep_log` gets a row from every completed pass, so the interesting
# thing in it is not the rows -- it is the holes between them. On 2026-08-25
# this had to be computed by hand, by pulling 400 rows and diffing them
# locally, which is exactly the "smuggle the code in with the question" drift
# this file exists to replace.
#
# The window function does the diff in SQLite. `-n` bounds the scan; the
# threshold is a bound parameter so a caller can ask about a quiet night at a
# different cadence without editing SQL.
_SQL_PASS_GAPS = (
    "WITH recent AS ("
    "  SELECT pass_ms FROM odds_sweep_log ORDER BY pass_ms DESC LIMIT ?"
    "), diffed AS ("
    "  SELECT pass_ms, pass_ms - LAG(pass_ms) OVER (ORDER BY pass_ms) AS gap_ms"
    "  FROM recent"
    ") SELECT gap_ms, pass_ms AS resumed_ms FROM diffed "
    "WHERE gap_ms > ? ORDER BY gap_ms DESC"
)

# **What actually went to the phone, split by kind.**
#
# `/api/health` publishes `notifications.total_ever` and nothing else, so the
# only question it can answer is "more than before?" -- which on 2026-08-26 was
# read as three parlay pushes repeating when the parlay keys had not moved at
# all. A total is not a breakdown, and deducing a breakdown from one is how a
# wrong story survives.
_SQL_NOTIFICATIONS_BY_KIND = (
    "SELECT kind, COUNT(*) AS n, SUM(delivered) AS delivered, "
    "MIN(sent_ms) AS first_ms, MAX(sent_ms) AS last_ms "
    "FROM notifications GROUP BY kind ORDER BY n DESC"
)

_SQL_NOTIFICATIONS_TAIL = (
    "SELECT id, sent_ms, kind, key, delivered, detail "
    "FROM notifications ORDER BY sent_ms DESC, id DESC"
)

# Every failure recorded across the same scan, so a gap can be read against
# them. Rows inside a hole mean the loop was FAILING; a hole with no rows means
# nothing came back to raise -- a wedged pass, or a container that went away.
# That contrast is the whole reason `loop_failures` exists (schema v22).
_SQL_LOOP_FAILURES_TAIL = (
    "SELECT id, failed_ms, pass_number, consecutive_failures, pass_kind, error "
    "FROM loop_failures ORDER BY failed_ms DESC, id DESC"
)

# The prune's own retention window, duplicated here rather than imported: this
# script is deliberately stdlib-only so the code that runs against the money box
# carries no import graph. `tests/test_inspect_live_db.py` asserts it still
# equals `retention.DEFAULT_QUOTE_RETENTION_MS`, so the duplication is checked
# rather than trusted.
_QUOTE_RETENTION_MS = 3 * 24 * 60 * 60 * 1000

# **The prune frontier: how far `prune_quotes` has actually got.**
#
# `quotes_pruned` is persisted nowhere -- it exists only in a `PassCounts` field
# that reaches the process log, and `flyctl logs` drops lines. So on 2026-08-20
# the window-gate registration's observation 1 ("no prune inside an open
# window") had no durable reading at all and had to be reported at log strength.
# This is that reading.
#
# **`COALESCE(confirmed_ms, observed_ms)`, matching `retention.py:206` exactly.**
# The obvious `MIN(observed_ms)` is wrong and wrong in the direction that
# flatters: ADR 0055 made the table a change log, so a market whose price has
# not moved in three days keeps one row with an ancient `observed_ms` and a
# current `confirmed_ms`. That row survives every prune, and a frontier computed
# on `observed_ms` therefore sits still through a prune that deleted 40,000
# rows -- reading as "no prune ran" when one did.
#
# The `NOT IN (SELECT ticker FROM recommendations)` half matters for the same
# reason: rows the prune is not allowed to touch are not part of its frontier.
#
# How to use it. `frontier_iso` advances only when a prune actually deletes, so
# comparing it either side of a window says whether one ran inside. When the
# backlog is 0 the frontier also tracks `cutoff_iso`, and then
# `frontier + retention` dates the last prune on its own.
#
# `backlog_rows` is the denominator, and it is the check to make first: if it is
# 0 the prune would delete nothing whenever it ran, and a zero prune inside a
# window says nothing about any gate.
_SQL_PRUNE_FRONTIER = (
    "SELECT "
    "  (SELECT MIN(COALESCE(confirmed_ms, observed_ms)) FROM kalshi_quotes"
    "     WHERE ticker NOT IN (SELECT ticker FROM recommendations))"
    "    AS frontier_ms, "
    "  :cutoff AS cutoff_ms, "
    "  (SELECT COUNT(*) FROM kalshi_quotes"
    "     WHERE COALESCE(confirmed_ms, observed_ms) < :cutoff"
    "       AND ticker NOT IN (SELECT ticker FROM recommendations))"
    "    AS backlog_rows, "
    "  (SELECT COUNT(*) FROM kalshi_quotes"
    "     WHERE ticker NOT IN (SELECT ticker FROM recommendations))"
    "    AS prunable_rows, "
    "  (SELECT COUNT(*) FROM kalshi_quotes) AS total_rows"
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
_SQL_PROP_BOOKMAKERS = (
    "SELECT bookmaker, COUNT(*) AS quotes, "
    "COUNT(DISTINCT odds_event_id) AS events, "
    "COUNT(DISTINCT market) AS market_keys, "
    "MIN(fetched_ms) AS first_fetched_ms, MAX(fetched_ms) AS last_fetched_ms "
    "FROM odds_snapshots "
    "WHERE outcome_description IS NOT NULL "
    "GROUP BY bookmaker ORDER BY quotes DESC"
)


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
# **This is §S1 of `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`,
# as amended, and it is a transcription rather than a design.** Every clause
# below is fixed in that file. Nothing here chooses a population, a horizon or
# a cluster key; changing any of them is an amendment to the registration, made
# in the registration, dated, before the next look.
#
# Four amendments are folded in and each is load-bearing:
#
# **§A1 — the delimited `instr` predicate.** `suppressed_reason` is a
# comma-joined composite of *every* check that failed, so the registered
# `NOT IN ('stale_odds', ...)` matched neither literal on
# `'stale_odds,wide_market'` and **retained** the row it existed to drop.
# `instr` and not `LIKE`, because SQLite's `LIKE` treats `_` as a
# single-character wildcard and every code in this vocabulary contains one --
# `,staleXodds,` would match. The wrapping commas are required in both
# directions: without them a future `stale_odds_upstream` is silently excluded.
#
# **§A2 — only four codes are excluded**, not "the suppressed ones":
# `stale_odds`, `stale_kalshi_quote`, `no_commence_time`, `commence_skew`.
# Every other code is RETAINED, including `too_few_books`, `wide_market`,
# `edge_within_method_noise` and the `skeptic_*` family. Dropping the rows where
# the edge estimate is least reliable is a hypothesis about the answer, and
# `edge_within_method_noise` in particular removes a price-dependent interval
# from the *interior* of the regressor, which moves leverage to the tails in the
# flattering direction.
#
# **§A2.2 — the price bound `BETWEEN 10 AND 989`.** Without it a row outside
# Grid A/B's range enters the pooled `beta` and appears in no bucket, so the
# pooled number and the per-group view are computed on different populations,
# silently.
#
# **§F3 — horizon 0.0 only.** ADR 0011 left two horizons in the record and
# blending them averages two regimes.
#
# **The cluster key is `COALESCE(m.event_ticker, r.ticker)` and it is NOT the
# gate's key.** ADR 0029 clusters on `odds_event_id` so a prop ladder collapses
# onto its game; this registration predates that and clusters on the Kalshi
# event. On the current record the two give **210 and 125** -- a 68% difference
# -- so a `G` quoted without its key is meaningless. The registered one governs
# here because it is what the power check was computed against.
#
# **`half_spread_tenths` is the C2 confound, not a nicety.** `edge` and `clv`
# are both measured against the ask, so the half-spread enters both and induces
# a slope with no signal present. It is a *control*, and the mid is used only to
# recover it -- never as an entry price. Rows where it is NULL are dropped by
# the harness and counted, never imputed: that count is P1's numerator, and P1
# refuses the primary analysis below 0.90 coverage.
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
# Where the bytes went.
# ---------------------------------------------------------------------------
#
# **Written during the 2026-08-16 volume-full incident.** The disk report said
# `/data` was 100% used and that `cockpit.db` was 879 MiB of the 974 MiB
# volume -- three files, no stray artefacts, nothing to sweep up. That answers
# "what filled the disk" and leaves the question that decides the fix: prune a
# table, or buy a bigger volume?
#
# `dbstat` is a virtual table giving the real page count per btree, so it
# measures **stored bytes including indexes and overflow**, which is the
# quantity the volume actually charges for. Row counts cannot substitute: one
# table with 40,000 wide rows and another with 400,000 narrow ones sort in
# opposite orders under the two measures, and only one of them is the disk.
#
# It is compiled in on most builds and is **not guaranteed**, so the caller
# gets row counts as a labelled fallback rather than an error -- during an
# incident a partial answer beats a stack trace. The two are reported as
# separate sections so nobody reads a row count as a byte count.
#
# Read `page_count * page_size` against the file size as a completeness check:
# a large gap is free pages inside the file, which means a `VACUUM` would
# reclaim space without deleting a single row. That distinction is the whole
# decision, and it is why `freelist_count` is here.
_SQL_DB_PAGE_SUMMARY = (
    "SELECT (SELECT * FROM pragma_page_count()) AS page_count, "
    "(SELECT * FROM pragma_page_size()) AS page_size, "
    "(SELECT * FROM pragma_freelist_count()) AS freelist_count, "
    "(SELECT * FROM pragma_page_count()) * (SELECT * FROM pragma_page_size()) "
    "  AS total_bytes, "
    "(SELECT * FROM pragma_freelist_count()) * (SELECT * FROM pragma_page_size())"
    "  AS reclaimable_by_vacuum_bytes"
)

_SQL_DBSTAT = (
    "SELECT name, SUM(pgsize) AS bytes, COUNT(*) AS pages "
    "FROM dbstat GROUP BY name ORDER BY bytes DESC"
)


def _q_db_sizes(conn: sqlite3.Connection, args) -> list[Section]:
    """Stored bytes per table and index, largest first.

    What this does not establish
    ----------------------------
    - **Nothing about what may be deleted.** Size is not expendability. The
      largest table is usually the highest-frequency observation, which may
      also be the only record of a price at an instant.
    - **`reclaimable_by_vacuum_bytes` is not free disk.** `VACUUM` rebuilds
      into a temporary copy, so it needs roughly the file size *free* on the
      same filesystem before it can give any back. On a volume at 100% it is
      not runnable at all, which is exactly the trap this was written in.
    - **A dbstat row named for an index is charged to that index**, not folded
      into its table. Sum the table and its indexes before concluding what a
      table costs.
    """
    sections = [
        _fetch(
            conn,
            _SQL_DB_PAGE_SUMMARY,
            (),
            title="A. file-level pages (compare total_bytes against the file on disk)",
            cap=args.limit,
        )
    ]
    try:
        sections.append(
            _fetch(
                conn,
                _SQL_DBSTAT,
                (),
                title="B. stored bytes per btree, via dbstat (indexes listed separately)",
                cap=args.limit,
            )
        )
    except sqlite3.OperationalError:
        # dbstat is optional at compile time. Say so in the title rather than
        # returning row counts under a heading that implies bytes.
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        rows = [(n, conn.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]) for n in names]  # noqa: S608
        rows.sort(key=lambda r: r[1], reverse=True)
        sections.append(
            Section(
                title="B. dbstat UNAVAILABLE -- row counts only, NOT bytes",
                columns=("name", "rows"),
                rows=rows,
                cap=args.limit,
            )
        )
    return sections


# ---------------------------------------------------------------------------
# The whole decision record, raw.
# ---------------------------------------------------------------------------
#
# **This is a dump, not a measurement, and the distinction is the whole design.**
# Two open questions need the same rows and disagree about how to slice them:
#
# 1. `tasks/NEXT.md`'s free falsification query -- the distribution of
#    (`edge_tenths` minus the bar it had to clear), split by `market_type`. If
#    nothing sits near the bar, no funnel change and no deep dive can close the
#    gap; if a band does, that band names the prospect definition.
# 2. The separating measurement from
#    `docs/measurements/2026-08-16-actionable-population-audit-result.md`: split
#    the unsuppressed population by `anchored_on_sharp` and compare. All three
#    actionable rows ever written are unanchored, and ADR 0021 measured 423
#    unanchored rows producing 0 actionable. If unanchored rows are enriched for
#    positive edge, the "edge" is a fact about which books were admitted.
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
# **Read the two columns in the right tense.** `clusters_now` is the key the gate
# used **until 2026-08-16** -- `COALESCE(m.event_ticker, r.ticker)` -- kept here
# as the *before* number. `clusters_by_game` is the key the gate uses **now**,
# `event_links.odds_event_id`, which the prop link deliberately inherits from its
# game (`match/linker.py` `link_prop_event`). The gap between them is the size of
# the defect ADR 0029 closed, on this record. It is not a live discrepancy: after
# that change the gate's own `n_clusters` equals `clusters_by_game`, and this
# section exists to say by how much that differs from what it used to report.
#
# **Do not read a gap as a bug in the gate's arithmetic** -- the arithmetic was
# always right and the key is what was in question.
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
# `docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md`.
# §8 of that document is why this emits **rows and not a verdict**: this script
# is explicitly not a measurement harness, so every quantity the decision rule
# reads is computed by `scripts/analyze_prop_onesided.py` on a laptop, from
# this query's `--json`, where the derivation is reviewable beside the rule it
# feeds.
#
# One row per rung -- `(event, bookmaker, base_market, feed, player, point)` --
# with the two sides pivoted into columns. The pivot is a **reshape, not a
# statistic**: `MAX(CASE ...)` picks the single price for a side that should
# have exactly one, and `quote_rows` is carried precisely so the analyzer can
# see when it did not. A rung with `quote_rows > 2` is a book quoting a side
# twice in one sweep, which §3 excludes as a finding about the store rather
# than averaging away here.
#
# **`price_decimal <= 1.0` is deliberately NOT filtered.** §3 makes that an
# exclusion that must be *counted*, and a row this query never emits cannot be
# counted by the thing that applies the rule.
#
# `_alternate` is folded onto its primary the way `kalshi/props.base_market`
# folds it, by exact suffix rather than `LIKE` -- 10 is `len("_alternate")`.
# The feed itself is kept as `is_alternate` because §4.2 needs the primary and
# alternate rungs of one book/player/market told apart, and a fold that lost
# it would destroy the input to the recovery it is meant to enable.
#
# `latest` is computed per fixture, so a slate swept at different times still
# contributes each fixture's own most recent sweep -- the rule
# `prop_quotes_for_event` follows, and for the same reason: mixing sweeps pairs
# a fresh price with an old one and calls the disagreement margin.
_SQL_PROP_RUNGS = (
    "WITH prop AS ("
    "  SELECT odds_event_id, bookmaker, market, outcome_name, "
    "         outcome_description, outcome_point, price_decimal, fetched_ms "
    "  FROM odds_snapshots WHERE outcome_description IS NOT NULL"
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


def _day_bounds(date_yyyymmdd: str, day_start_hour: int) -> tuple[int, int]:
    """The half-open [start, end) millisecond bounds of one budget day."""
    try:
        day = datetime.strptime(date_yyyymmdd, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(
            f"--date must be YYYYMMDD, got {date_yyyymmdd!r}"
        ) from exc
    start = day.replace(
        hour=day_start_hour, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    start_ms = int(start.timestamp() * 1000)
    return start_ms, start_ms + _MS_PER_DAY


def _month_start_ms(now_ms: int) -> int:
    """UTC calendar month start. The Odds API's month, not our sports day."""
    dt = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    return int(
        dt.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        * 1000
    )


def _window_section(title: str, start_ms: int, end_ms: Optional[int]) -> Section:
    """A one-row block naming the time window a query actually used.

    Printed because the window is derived from flags and the reader must be
    able to check it without re-deriving the arithmetic in their head.
    """
    columns = ("start_ms", "start_iso")
    row: tuple[Any, ...] = (start_ms, _iso(start_ms))
    if end_ms is not None:
        columns += ("end_ms", "end_iso")
        row += (end_ms, _iso(end_ms))
    return Section(title=title, columns=columns, rows=[row])


def _q_credits_tail(conn: sqlite3.Connection, args) -> list[Section]:
    section = _fetch(
        conn,
        _SQL_CREDITS_TAIL,
        (),
        title=f"api_credits: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    return [_derive_iso(section, "called_ms", "called_iso")]


def _q_credits_day(conn: sqlite3.Connection, args) -> list[Section]:
    if not args.date:
        raise ValueError(
            "credits-day needs --date YYYYMMDD. It is not defaulted to today: "
            "the question this query answers is about a specific past day, and "
            "a guessed date would answer a different one silently."
        )
    start_ms, end_ms = _day_bounds(args.date, args.day_start_hour)
    rows = _fetch(
        conn,
        _SQL_CREDITS_DAY_ROWS,
        (start_ms, end_ms),
        title=f"api_credits: budget day {args.date} (starts {args.day_start_hour:02d}:00Z)",
        cap=args.limit,
    )
    totals = _fetch(
        conn,
        _SQL_CREDITS_DAY_TOTALS,
        (start_ms, end_ms),
        title="api_credits: row count and summed cost for that day",
        cap=args.limit,
    )
    return [
        _window_section("budget day window", start_ms, end_ms),
        _derive_iso(rows, "called_ms", "called_iso"),
        totals,
    ]


def _q_credits_month(conn: sqlite3.Connection, args) -> list[Section]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = _month_start_ms(now_ms)
    totals = _fetch(
        conn,
        _SQL_CREDITS_MONTH,
        (start_ms,),
        title="api_credits: month to date",
        cap=args.limit,
    )
    return [_window_section("calendar month window (UTC)", start_ms, None), totals]


def _q_sweep_log(conn: sqlite3.Connection, args) -> list[Section]:
    groups = _fetch(
        conn,
        _SQL_SWEEP_LOG_GROUPS,
        (),
        title="odds_sweep_log: count and pass_ms range by outcome",
        cap=args.limit,
    )
    groups = _derive_iso(groups, "min_pass_ms", "min_pass_iso")
    groups = _derive_iso(groups, "max_pass_ms", "max_pass_iso")
    tail = _fetch(
        conn,
        _SQL_SWEEP_LOG_TAIL,
        (),
        title=f"odds_sweep_log: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    return [groups, _derive_iso(tail, "pass_ms", "pass_iso")]


def _q_notifications(conn: sqlite3.Connection, args) -> list[Section]:
    """What reached the phone, by kind, then the tail in full.

    `key` is printed because for `parlay_card` it IS the dedupe rule -- rung
    plus sorted leg tickers -- so two rows with the same key would be a bug in
    `UNIQUE (kind, key)` and two with different keys explain a repeat push
    without anyone having to guess at it.

    What this does not establish
    ----------------------------
    - **That a delivered alert was read**, or was worth sending. `delivered`
      is Discord returning 2xx, nothing more.
    - **Why a kind is absent.** `opportunity` has never fired in this
      project's life, which is a fact about the Board being empty rather than
      about the notifier.
    """
    kinds = _fetch(
        conn,
        _SQL_NOTIFICATIONS_BY_KIND,
        (),
        title="notifications: count and delivered by kind",
        cap=args.limit,
    )
    kinds = _derive_iso(kinds, "first_ms", "first_iso")
    kinds = _derive_iso(kinds, "last_ms", "last_iso")
    tail = _fetch(
        conn,
        _SQL_NOTIFICATIONS_TAIL,
        (),
        title=f"notifications: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    return [kinds, _derive_iso(tail, "sent_ms", "sent_iso")]


def _q_pass_gaps(conn: sqlite3.Connection, args) -> list[Section]:
    """Holes in the pass ledger, and every failure recorded near them.

    **Read the two sections together -- separately they each mislead.** A gap
    alone does not say what happened; a failure alone does not say whether the
    record actually stopped. The reading is the join:

        gap with failures inside it   the loop was failing and retrying
        gap with no failures at all   nothing came back to raise: a wedged
                                      pass, or the container went away
        failures with no gap          transient, absorbed, record intact

    The threshold defaults to 1,200,000 ms -- above the 1,035s ceiling on a
    healthy shut-window sleep (900s x 1.15), so an ordinary quiet night does
    not fill the output with its own cadence.

    What this does not establish
    ----------------------------
    - **That a gap with no failures was a wedge.** A restart looks identical
      from inside the database. `flyctl machine status` settles it, and the
      machine event log is the only place that can.
    - **Anything before schema v22**, for the failures half. The table did not
      exist, so an old gap reads as "no failures" whatever its cause. Check
      `failed_ms` coverage before drawing the contrast on a historical window.
    """
    gaps = _fetch(
        conn,
        _SQL_PASS_GAPS,
        (args.tail, args.gap_ms),
        title=(
            f"gaps over {args.gap_ms / 1000:.0f}s in the last {args.tail} "
            f"odds_sweep_log rows, widest first"
        ),
        cap=args.limit,
    )
    gaps = _derive_iso(gaps, "resumed_ms", "resumed_iso")
    failures = _fetch(
        conn,
        _SQL_LOOP_FAILURES_TAIL,
        (),
        title=f"loop_failures: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    return [gaps, _derive_iso(failures, "failed_ms", "failed_iso")]


def _q_prune_frontier(conn: sqlite3.Connection, args) -> list[Section]:
    """How far `prune_quotes` has got, and whether it still has anything to do.

    `now` is stamped here and printed, because a frontier is a claim about a
    moment and the moment is half the reading.

    What this does not establish
    ----------------------------
    - **Not when the last prune ran**, on its own, while `backlog_rows > 0`. A
      backlogged prune deletes a bounded batch and stops, so the frontier lags
      the cutoff by an unknown amount and only *changes* are interpretable.
      Take it either side of the window you care about.
    - **Nothing about `unmatched_items`**, which has its own retention, its own
      budget and its own frontier. This reads the quotes prune only.
    """
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    section = _fetch(
        conn,
        _SQL_PRUNE_FRONTIER,
        {"cutoff": now - _QUOTE_RETENTION_MS},
        title=(
            f"prune frontier at {_iso(now)} "
            f"(retention {_QUOTE_RETENTION_MS // 86_400_000}d)"
        ),
        cap=args.limit,
    )
    section = _derive_iso(section, "frontier_ms", "frontier_iso")
    return [_derive_iso(section, "cutoff_ms", "cutoff_iso")]


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
    """
    return [
        _fetch(
            conn,
            _SQL_PROP_BOOKMAKERS,
            (),
            title="odds_snapshots: books that returned a player prop",
            cap=args.limit,
        )
    ]


def _q_actionable_audit(conn: sqlite3.Connection, args) -> list[Section]:
    """Every row the strategy would have bet, with its whole provenance.

    **This exists because `actionable` stopped being zero on 2026-08-16 and no
    instrument could show the rows.** `clv-coverage` section D counts the
    population; nothing printed a member of it. The only other route was
    `/api/ledger` in an authenticated browser, which is a screenshot, not a
    record, and cannot be re-run against a later snapshot.

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
    return [
        _fetch(
            conn,
            _SQL_PROP_RUNGS,
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
# window-freshness: `fixture_freshness` recomputed at a stated instant
# ---------------------------------------------------------------------------

# The same shape as `backend/odds/timing.py::fixture_freshness`, with ONE
# deliberate addition: `fetched_ms <= :at`, so the query can be pinned at a
# past instant. At `--at now` the predicate is vacuous (no fetch is in the
# future) and the two are the same query. Ages here are `:at - oldest`, where
# oldest is the production measure -- within each fixture's most recent sweep,
# the oldest contributing book's own `last_update`, falling back to our fetch
# time. The production function's known approximation is inherited unchanged:
# it does NOT drop books that fail to quote every outcome, so a fixture can
# read staler here than the runner will find it.
_SQL_FRESHNESS_AT_FIXTURES = (
    "WITH latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
    "  WHERE market = 'h2h' AND fetched_ms <= :at AND commence_ms >= :at"
    "  GROUP BY odds_event_id"
    ") "
    "SELECT o.odds_event_id, o.sport_key,"
    "       MIN(o.commence_ms) AS commence_ms,"
    "       l.m AS fetched_ms,"
    "       COUNT(DISTINCT o.bookmaker) AS books,"
    "       MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms,"
    "       MAX(COALESCE(o.book_updated_ms, o.fetched_ms)) AS newest_ms,"
    "       :at - MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS age_ms "
    "FROM odds_snapshots o JOIN latest l"
    "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
    "WHERE o.market = 'h2h' "
    "GROUP BY o.odds_event_id "
    "ORDER BY age_ms"
)

# The same latest-sweep population, grouped by book instead of fixture. The
# window indicator takes MIN over books per fixture, so ONE book whose
# `last_update` the aggregator has not advanced drags every fixture it quotes
# toward "stale". This section is what names that book.
_SQL_FRESHNESS_AT_BOOKS = (
    "WITH latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
    "  WHERE market = 'h2h' AND fetched_ms <= :at AND commence_ms >= :at"
    "  GROUP BY odds_event_id"
    ") "
    "SELECT o.bookmaker,"
    "       COUNT(DISTINCT o.odds_event_id) AS fixtures,"
    "       MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms,"
    "       MAX(COALESCE(o.book_updated_ms, o.fetched_ms)) AS newest_ms,"
    "       :at - MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS worst_age_ms "
    "FROM odds_snapshots o JOIN latest l"
    "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
    "WHERE o.market = 'h2h' "
    "GROUP BY o.bookmaker "
    "ORDER BY worst_age_ms DESC"
)


def _parse_at_ms(value: Optional[str]) -> int:
    """`--at` as epoch milliseconds. Digits pass through; ISO-8601 is parsed.

    A malformed value raises ValueError (exit 2 via main) rather than falling
    back to "now": a typo'd instant answered with the present would read as a
    retrospective measurement and be one silently taken today.
    """
    if value is None:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    if value.isdigit():
        return int(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"--at {value!r} is neither epoch milliseconds nor ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _q_window_freshness(conn: sqlite3.Connection, args) -> list[Section]:
    """`fixture_freshness` at `--at`, per fixture and then per book.

    What this does not establish
    ----------------------------
    - **Not what the loop read at that instant.** Rows written or pruned since
      then change the answer; a retrospective read is honest only while the
      sweeps around the instant are still in `odds_snapshots`. Compare
      `fetched_ms` against the sweep log before believing an age.
    - **Nothing about why a stamp is old** -- a stale `last_update` cannot
      separate "the book has not repriced" from "the aggregator has not
      re-crawled it" (2026-08-11 repeat-poll result).
    """
    at_ms = _parse_at_ms(args.at)
    fixtures = _fetch(
        conn,
        _SQL_FRESHNESS_AT_FIXTURES,
        {"at": at_ms},
        title=f"fixture_freshness at {_iso(at_ms)}: per fixture, freshest first",
        cap=args.limit,
    )
    for col, iso in (
        ("commence_ms", "commence_iso"),
        ("fetched_ms", "fetched_iso"),
        ("oldest_ms", "oldest_iso"),
    ):
        fixtures = _derive_iso(fixtures, col, iso)
    books = _fetch(
        conn,
        _SQL_FRESHNESS_AT_BOOKS,
        {"at": at_ms},
        title=(
            f"same population by book at {_iso(at_ms)}: worst own-stamp age "
            "across the fixtures each book quotes, stalest first"
        ),
        cap=args.limit,
    )
    books = _derive_iso(books, "oldest_ms", "oldest_iso")
    return [fixtures, books]


# The h2h rows ONE book contributed to the exact population `window-freshness`
# reads -- the latest sweep per not-yet-commenced fixture at `:at`. Written to
# answer the question the dropout diagnosis had to leave conditional: a book
# quoting both outcomes *contributes* to the runner's consensus, so its stale
# stamp ages `odds_age_ms` and every row suppresses with the window; a book
# quoting one outcome is dropped by `book_quotes_for_event` and its stamp gates
# only the window flag, in which case the bounded sleeps skipped passes that
# could have confirmed live rows.
_SQL_BOOK_ROWS = (
    "WITH latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
    "  WHERE market = 'h2h' AND fetched_ms <= :at AND commence_ms >= :at"
    "  GROUP BY odds_event_id"
    ") "
    "SELECT o.bookmaker, o.odds_event_id, o.outcome_name, o.price_decimal,"
    "       o.book_updated_ms, o.fetched_ms "
    "FROM odds_snapshots o JOIN latest l"
    "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
    "WHERE o.market = 'h2h' AND (:book IS NULL OR o.bookmaker = :book) "
    "ORDER BY o.bookmaker, o.odds_event_id, o.outcome_name"
)


def _q_book_rows(conn: sqlite3.Connection, args) -> list[Section]:
    """A book's h2h rows in the window-freshness population at `--at`.

    Two rows per fixture means the book quotes both outcomes and contributes
    to the runner's consensus; one row means `book_quotes_for_event` drops it.
    Without `--book` every book's rows are listed, which on a live slate is
    ~30 books x 2 outcomes x the slate and still inside the default cap.

    What this does not establish
    ----------------------------
    - **Nothing about other markets.** h2h only, matching the freshness
      population; a book can be two-sided on h2h and absent on spreads.
    - **Nothing about the price's quality** -- presence, not correctness.
    """
    at_ms = _parse_at_ms(args.at)
    who = f"{args.book!r}" if args.book else "every book"
    section = _fetch(
        conn,
        _SQL_BOOK_ROWS,
        {"at": at_ms, "book": args.book},
        title=(
            f"h2h rows from {who} in the latest-sweep population "
            f"at {_iso(at_ms)}"
        ),
        cap=args.limit,
    )
    section = _derive_iso(section, "book_updated_ms", "book_updated_iso")
    return [_derive_iso(section, "fetched_ms", "fetched_iso")]


# ---------------------------------------------------------------------------
# h4-settlement-balance: the raw material for settling H4, four sections,
# deliberately NOT joined
# ---------------------------------------------------------------------------
#
# H4 (ADR 0026/0027): does settlement carry its own fee? The decisive
# observation is a balance step around a settlement that differs from
# recorded proceeds-minus-known-fees. A join would need a tolerance, a
# tolerance is a matching decision, and matching decisions are where the
# flattering error lives in this repo -- so this emits four independent
# sections keyed by their own clocks and computes NO delta. The human does
# the subtraction where the confounds are visible on the same screen.

# The calibration study's start instant, 2026-08-18 09:15:03.594Z. The H4
# population is the settlements the balance poller could have witnessed, and
# the poller shipped with the study.
_H4_STUDY_START_MS = 1_787_044_503_594
# +/- 900s around each settlement: ~3 balance snapshots per side at the
# poller's 300s cadence.
_H4_WINDOW_MS = 900_000

_SQL_H4_SETTLEMENTS = (
    "SELECT id, ticker, side, contracts, entry_price_tenths,"
    "       fee_cost_tenths, market_result, settled_ms "
    "FROM venue_settlements WHERE settled_ms >= :study_start "
    "ORDER BY settled_ms"
)

_SQL_H4_BALANCE = (
    "SELECT b.observed_ms, b.balance_tenths, b.portfolio_value_tenths "
    "FROM venue_balance_snapshots b WHERE EXISTS ("
    "  SELECT 1 FROM venue_settlements s WHERE s.settled_ms >= :study_start"
    "  AND b.observed_ms BETWEEN s.settled_ms - :half AND s.settled_ms + :half"
    ") ORDER BY b.observed_ms"
)

_SQL_H4_FILLS = (
    "SELECT f.id, f.ticker, f.filled_ms, f.count, f.price_tenths,"
    "       f.is_taker, f.fee_actual, f.source "
    "FROM fills f WHERE EXISTS ("
    "  SELECT 1 FROM venue_settlements s WHERE s.settled_ms >= :study_start"
    "  AND f.filled_ms BETWEEN s.settled_ms - :half AND s.settled_ms + :half"
    ") ORDER BY f.filled_ms"
)

_SQL_H4_POLLS = (
    "SELECT p.polled_ms, p.ok, p.row_count, p.error "
    "FROM poll_log p WHERE p.endpoint = 'balance' AND EXISTS ("
    "  SELECT 1 FROM venue_settlements s WHERE s.settled_ms >= :study_start"
    "  AND p.polled_ms BETWEEN s.settled_ms - :half AND s.settled_ms + :half"
    ") ORDER BY p.polled_ms"
)


def _q_h4_settlement_balance(conn: sqlite3.Connection, args) -> list[Section]:
    """H4's raw material: settlements, balance, fills and polls, unjoined.

    Section B emits `portfolio_value_tenths` even though it is NULL on every
    row today -- that NULL is `parse_portfolio_value_tenths`'s deliberate
    refusal (`backend/portfolio_poll.py:252`: any non-zero value is refused
    until the field's unit is pinned), and dropping the column would hide
    the very blocker ADR 0027's correction names.
    Section D includes `ok` on purpose: without the poll record, a missing
    balance snapshot reads as a zero delta instead of an outage.

    What this does not establish
    ----------------------------
    - **No verdict and no delta.** Rows only; the H4 arithmetic needs a
      registration first, and the subtraction belongs where these confounds
      are visible together.
    - **Deposits are unrecorded by design** (`backend/config.py:499`), so a
      balance step is not attributable to settlement activity by this data
      alone.
    - **Balance resolution is $0.001 against a $0.0063 quantity in
      dispute**: `dollars_to_tenths` discards a digit the venue supplies, so
      a per-settlement fee smaller than a tenth of a cent may be invisible
      here even if real.
    """
    settlements = _fetch(
        conn,
        _SQL_H4_SETTLEMENTS,
        {"study_start": _H4_STUDY_START_MS},
        title=(
            f"A. venue_settlements since study start {_iso(_H4_STUDY_START_MS)}"
        ),
        cap=args.limit,
    )
    settlements = _derive_iso(settlements, "settled_ms", "settled_iso")
    window = {"study_start": _H4_STUDY_START_MS, "half": _H4_WINDOW_MS}
    balance = _fetch(
        conn,
        _SQL_H4_BALANCE,
        window,
        title=(
            "B. venue_balance_snapshots within +/-900s of an A settlement "
            "(portfolio_value_tenths NULL = the parser's deliberate "
            "refusal, shown on purpose)"
        ),
        cap=args.limit,
    )
    balance = _derive_iso(balance, "observed_ms", "observed_iso")
    fills = _fetch(
        conn,
        _SQL_H4_FILLS,
        window,
        title="C. fills within the same windows (the fill confound, visible)",
        cap=args.limit,
    )
    fills = _derive_iso(fills, "filled_ms", "filled_iso")
    polls = _fetch(
        conn,
        _SQL_H4_POLLS,
        window,
        title=(
            "D. poll_log endpoint='balance' within the same windows, "
            "including ok (a missing snapshot must read as an outage, not "
            "a zero delta)"
        ),
        cap=args.limit,
    )
    polls = _derive_iso(polls, "polled_ms", "polled_iso")
    return [settlements, balance, fills, polls]


# ---------------------------------------------------------------------------
# h4-balance-spans: Look 2's unwindowed raw material (Amendment 1, A12.3)
# ---------------------------------------------------------------------------
#
# The span design (A12.2) drops the +/-900s window entirely: every adjacent
# balance-snapshot pair is an observation, and the prediction P_j sums over
# EVERY settlement in the table, pre-study rows included. So sections B-D
# filter only on their own clock >= study start, and a fifth section carries
# the whole `venue_settlements` table. Still no join and no computed delta --
# a tolerance is a matching decision, and the analyzer owns those.

_SQL_H4_SPAN_BALANCE = (
    "SELECT observed_ms, balance_tenths, portfolio_value_tenths "
    "FROM venue_balance_snapshots WHERE observed_ms >= :study_start "
    "ORDER BY observed_ms"
)

_SQL_H4_SPAN_FILLS = (
    "SELECT id, ticker, filled_ms, count, price_tenths,"
    "       is_taker, fee_actual, source "
    "FROM fills WHERE filled_ms >= :study_start ORDER BY filled_ms"
)

_SQL_H4_SPAN_POLLS = (
    "SELECT polled_ms, ok, row_count, error "
    "FROM poll_log WHERE endpoint = 'balance'"
    " AND polled_ms >= :study_start ORDER BY polled_ms"
)

_SQL_H4_ALL_SETTLEMENTS = (
    "SELECT id, ticker, side, contracts, entry_price_tenths,"
    "       fee_cost_tenths, market_result, settled_ms "
    "FROM venue_settlements ORDER BY settled_ms"
)


def _q_h4_balance_spans(conn: sqlite3.Connection, args) -> list[Section]:
    """Look 2's raw material under the span design: unwindowed, unjoined.

    Registered by Amendment 1 (A12.3) of
    `docs/measurements/2026-08-20-preregistration-h4-settlement-fee.md`.
    Sections A-D mirror `h4-settlement-balance` but carry everything since
    study start on each table's own clock -- no `EXISTS` window, because the
    span design has no window. Section E is the WHOLE `venue_settlements`
    table: `P_j` sums winning settlements inside each snapshot pair whether
    or not they post-date the study, so a study-start filter here would
    silently zero pre-study terms out of the prediction.

    What this does not establish
    ----------------------------
    - **No verdict, no delta, no pairing.** Rows only. Adjacent-pair
      residuals, tolerances and cluster classification belong to the
      registered analyzer, committed before the pull as Look 1's was.
    - **Deposits are unrecorded by design** (`backend/config.py:499`); an
      interval can be long under this design, so an unrecorded transfer has
      more room to land in one. A9.2/A3's voting floor is the registered
      countermeasure, not anything in this query.
    - **The channel may still be blind**: if settled proceeds never credit
      the cash balance, no horizon reaches the charge (A14), and this query
      cannot detect that condition -- only the analyzer's positive-control
      gate (A10) can.
    """
    since = {"study_start": _H4_STUDY_START_MS}
    settlements = _fetch(
        conn,
        _SQL_H4_SETTLEMENTS,
        since,
        title=(
            f"A. venue_settlements since study start {_iso(_H4_STUDY_START_MS)}"
        ),
        cap=args.limit,
    )
    settlements = _derive_iso(settlements, "settled_ms", "settled_iso")
    balance = _fetch(
        conn,
        _SQL_H4_SPAN_BALANCE,
        since,
        title=(
            "B. venue_balance_snapshots since study start, UNWINDOWED "
            "(portfolio_value_tenths NULL = the parser's deliberate "
            "refusal, shown on purpose)"
        ),
        cap=args.limit,
    )
    balance = _derive_iso(balance, "observed_ms", "observed_iso")
    fills = _fetch(
        conn,
        _SQL_H4_SPAN_FILLS,
        since,
        title=(
            "C. fills since study start, UNWINDOWED "
            "(the fill confound, visible)"
        ),
        cap=args.limit,
    )
    fills = _derive_iso(fills, "filled_ms", "filled_iso")
    polls = _fetch(
        conn,
        _SQL_H4_SPAN_POLLS,
        since,
        title=(
            "D. poll_log endpoint='balance' since study start, UNWINDOWED, "
            "including ok (a missing snapshot must read as an outage, not "
            "a zero delta)"
        ),
        cap=args.limit,
    )
    polls = _derive_iso(polls, "polled_ms", "polled_iso")
    all_settlements = _fetch(
        conn,
        _SQL_H4_ALL_SETTLEMENTS,
        {},
        title=(
            "E. venue_settlements, WHOLE TABLE incl. pre-study "
            "(P_j sums every settlement inside a span, A12.2)"
        ),
        cap=args.limit,
    )
    all_settlements = _derive_iso(all_settlements, "settled_ms", "settled_iso")
    return [settlements, balance, fills, polls, all_settlements]


# ---------------------------------------------------------------------------
# estimate-match-status: the calibration study's coverage cells
# ---------------------------------------------------------------------------

_SQL_MATCH_STATUS_POSITIONS = (
    "SELECT estimate_match_status, COUNT(*) AS n,"
    "       MIN(settled_ms) AS min_settled_ms, MAX(settled_ms) AS max_settled_ms "
    "FROM venue_settlements GROUP BY estimate_match_status ORDER BY n DESC"
)

# The benign explanation for `out_of_scope = everything` is "every one is a
# multi-leg combo". `venue_settlements` carries no multi-leg flag, so the
# ticker prefix is the observable: KXMVE is the combo series. Splitting the
# status counts by that prefix is what lets a single non-combo `out_of_scope`
# row show up instead of drowning in the aggregate.
_SQL_MATCH_STATUS_POSITIONS_BY_KIND = (
    "SELECT estimate_match_status,"
    "       CASE WHEN ticker LIKE 'KXMVE%' THEN 'combo' ELSE 'single' END AS kind,"
    "       COUNT(*) AS n "
    "FROM venue_settlements "
    "GROUP BY estimate_match_status, kind ORDER BY n DESC"
)

_SQL_MATCH_STATUS_NONCOMBO_ROWS = (
    "SELECT id, ticker, side, contracts, settled_ms, estimate_match_status "
    "FROM venue_settlements "
    "WHERE ticker NOT LIKE 'KXMVE%' "
    "ORDER BY settled_ms DESC"
)

_SQL_MATCH_STATUS_ESTIMATES = (
    "SELECT match_status, COUNT(*) AS n,"
    "       MIN(match_status_ms) AS min_status_ms,"
    "       MAX(match_status_ms) AS max_status_ms "
    "FROM bet_estimates GROUP BY match_status ORDER BY n DESC"
)


def _q_estimate_match_status(conn: sqlite3.Connection, args) -> list[Section]:
    """The §7.5 coverage cells: position-side and estimate-side status counts.

    Emits rows and no verdict. The zero being checked -- 0 `position_unlogged`
    against 35 `out_of_scope` on the first classify pass -- is interesting
    exactly if a NON-combo position sits in `out_of_scope`, which section 3
    lists row by row.
    """
    positions = _fetch(
        conn,
        _SQL_MATCH_STATUS_POSITIONS,
        (),
        title="venue_settlements by estimate_match_status (NULL = not yet examined)",
        cap=args.limit,
    )
    positions = _derive_iso(positions, "min_settled_ms", "min_settled_iso")
    positions = _derive_iso(positions, "max_settled_ms", "max_settled_iso")
    by_kind = _fetch(
        conn,
        _SQL_MATCH_STATUS_POSITIONS_BY_KIND,
        (),
        title="the same statuses split combo (KXMVE) vs single-market ticker",
        cap=args.limit,
    )
    noncombo = _fetch(
        conn,
        _SQL_MATCH_STATUS_NONCOMBO_ROWS,
        (),
        title="every non-combo position row, newest first",
        cap=args.limit,
    )
    noncombo = _derive_iso(noncombo, "settled_ms", "settled_iso")
    estimates = _fetch(
        conn,
        _SQL_MATCH_STATUS_ESTIMATES,
        (),
        title="bet_estimates by match_status (NULL = never examined)",
        cap=args.limit,
    )
    estimates = _derive_iso(estimates, "min_status_ms", "min_status_iso")
    estimates = _derive_iso(estimates, "max_status_ms", "max_status_iso")
    return [positions, by_kind, noncombo, estimates]


@dataclass(frozen=True)
class QueryDef:
    description: str
    run: Callable[[sqlite3.Connection, Any], list[Section]]


QUERIES: dict[str, QueryDef] = {
    "credits-tail": QueryDef(
        "The last N api_credits rows (-n, default 5), newest first, each "
        "called_ms also rendered ISO-8601 UTC. Answers: what remaining_reported "
        "did the most recent response carry?",
        _q_credits_tail,
    ),
    "credits-day": QueryDef(
        "Every api_credits row in one budget day (--date YYYYMMDD, boundary "
        "--day-start-hour, default 10), plus the row count and summed cost.",
        _q_credits_day,
    ),
    "credits-month": QueryDef(
        "Month-to-date summed cost, and MIN/MAX of remaining_reported and "
        "used_reported, over the UTC calendar month.",
        _q_credits_month,
    ),
    "sweep-log": QueryDef(
        "odds_sweep_log: COUNT and pass_ms range grouped by outcome, then the "
        "last N rows in full (-n, default 5).",
        _q_sweep_log,
    ),
    "notifications": QueryDef(
        "What reached the phone: count and delivered by kind, then the last N "
        "rows (-n, default 5) with their dedupe keys. /api/health publishes a "
        "TOTAL only, which cannot say which kind moved.",
        _q_notifications,
    ),
    "pass-gaps": QueryDef(
        "Holes over --gap-ms (default 1200000) in the last N odds_sweep_log "
        "rows (-n, default 5 -- pass a few hundred), beside every loop_failures "
        "row. A gap WITH failures inside it was a failing loop; a gap with NONE "
        "never came back to raise. The pair is the reading; neither half is.",
        _q_pass_gaps,
    ),
    "prune-frontier": QueryDef(
        "How far prune_quotes has got: MIN(COALESCE(confirmed_ms, "
        "observed_ms)) over prunable rows, the 3-day cutoff, and the backlog "
        "still below it. The durable stand-in for `quotes_pruned`, which is "
        "persisted nowhere. Take it either side of a window to say whether a "
        "prune ran inside one.",
        _q_prune_frontier,
    ),
    "results-for-pull": QueryDef(
        "kalshi_markets (incl. result) for the pinned recommendation "
        "population (--pin, default 1564). ~120 rows.",
        _q_results_for_pull,
    ),
    "events-for-pull": QueryDef(
        "kalshi_events reached through the pinned markets. ~60 rows.",
        _q_events_for_pull,
    ),
    "closing-lines-for-pull": QueryDef(
        "closing_lines for the pinned tickers. ~240 rows.",
        _q_closing_lines_for_pull,
    ),
    "series": QueryDef(
        "kalshi_series: series_ticker and league. ~10 rows.",
        _q_series,
    ),
    "prop-bookmakers": QueryDef(
        "odds_snapshots rows carrying outcome_description (i.e. player props), "
        "grouped by bookmaker with quote/event/market-key counts and the "
        "fetched_ms range. Answers: does any EU book quote props, or is half "
        "of every 20-credit prop event buying nothing?",
        _q_prop_bookmakers,
    ),
    "prop-rungs": QueryDef(
        "Raw player-prop rungs at the latest sweep per fixture, one row per "
        "(event, book, base_market, feed, player, point) with Over and Under "
        "pivoted into columns. Emits rows, not a verdict: the registered "
        "arithmetic lives in scripts/analyze_prop_onesided.py. Narrow with "
        "--odds-event-id, or raise --limit; the whole record truncates.",
        _q_prop_rungs,
    ),
    "actionable-audit": QueryDef(
        "Every row in the gate's `actionable` population -- the ones the "
        "strategy would have bet -- in two sections: A the decision (ask, "
        "edge, both sizes, all four clocks), B the provenance (all four devig "
        "readings, book_count, anchored_on_sharp, market_width). Prints rows "
        "and no verdict. Answers: did these clear a real bar, or land in a gap?",
        _q_actionable_audit,
    ),
    "clv-signal-pull": QueryDef(
        "The CLV signal test's registered §2 population (horizon 0.0), one row "
        "per recommendation with its half-spread control joined from "
        "kalshi_quotes. A transcription of §S1 as amended by §A1/§A2/§A2.2 -- "
        "four suppression codes excluded by delimited instr, price bounded to "
        "[10,989], cluster key COALESCE(event_ticker, ticker). Emits rows and "
        "NO statistic; scripts/run_signal_test.py computes beta.",
        _q_clv_signal_pull,
    ),
    "db-sizes": QueryDef(
        "Where the bytes went: file-level page counts with the amount a VACUUM "
        "could reclaim, then stored bytes per table and index via dbstat "
        "(row counts as a labelled fallback if dbstat is not compiled in). "
        "Answers: prune a table, or buy a bigger volume?",
        _q_db_sizes,
    ),
    "decision-dump": QueryDef(
        "Every recommendation ever written, one row each, with its four devig "
        "readings, book_count, anchored_on_sharp, market_width, both sizes, "
        "suppressed_reason and its CLV score. Emits rows and NO aggregate: the "
        "registered arithmetic belongs in scripts/. Feeds the free "
        "falsification query and the anchored-vs-unanchored split. Raise "
        "--limit above the record size and check `truncated` before analysing.",
        _q_decision_dump,
    ),
    "clv-coverage": QueryDef(
        "Does CLV scoring reach props? Six sections: recommendations by "
        "market type (scored/pending), the re-request set with its per-pass "
        "candlestick bill, closing_lines by series and horizon, the gate's "
        "cluster count beside one-cluster-per-game (by population, then "
        "pooled), and any Kalshi event linked to two sportsbook fixtures. "
        "Answers: are the prop rows unscorable, and is the 300-game floor "
        "counting one game more than once?",
        _q_clv_coverage,
    ),
    "window-freshness": QueryDef(
        "fixture_freshness recomputed at --at (ISO or epoch ms, default now): "
        "per-fixture consensus ages the window indicator would compute, then "
        "the same population by book, stalest first. Answers: which book's "
        "own last_update stamp closed the window mid-refresh-interval?",
        _q_window_freshness,
    ),
    "book-rows": QueryDef(
        "One bookmaker's h2h rows (--book, required) in the window-freshness "
        "population at --at: two rows per fixture = contributes to the "
        "runner's consensus, one = dropped as incomplete. Answers: did the "
        "laggard book's stamp age the consensus, or only the window flag?",
        _q_book_rows,
    ),
    "h4-settlement-balance": QueryDef(
        "H4's raw material, four sections and NO join: A settlements since "
        "study start (with market_result), B balance snapshots +/-900s of "
        "each (portfolio_value_tenths NULLs shown), C fills in the same "
        "windows, D balance poll_log including ok. Emits rows, no delta; "
        "the subtraction is done by a human beside the stated confounds.",
        _q_h4_settlement_balance,
    ),
    "h4-balance-spans": QueryDef(
        "Look 2's span-design raw material (Amendment 1 A12.3), five "
        "sections and NO join: A settlements since study start, B balance "
        "snapshots since study start UNWINDOWED, C fills likewise, D balance "
        "poll_log likewise including ok, E the whole venue_settlements table "
        "(pre-study included, for the P_j sum). Emits rows, no delta; "
        "pairing and residuals belong to the registered analyzer.",
        _q_h4_balance_spans,
    ),
    "estimate-match-status": QueryDef(
        "Calibration §7.5 coverage: venue_settlements by estimate_match_status "
        "(total, then split combo vs single ticker, then every non-combo row), "
        "and bet_estimates by match_status. Answers: is the 0-position_unlogged "
        "cell real, or is a non-combo position sitting in out_of_scope?",
        _q_estimate_match_status,
    ),
    "kalshi-quotes-band": QueryDef(
        "Q-W: was a WNBA market in 270-390 tenths (excl. 300) with depth >= 1 "
        "reachable at >= 80% of pre-game polling instants across >= 8 events, "
        "2026-08-07 to 2026-08-10? Window, band, bars and series order are "
        "registered constants, not flags. Precondition for the fee round.",
        _q_kalshi_quotes_band,
    ),
}


def resolve_query(name: str) -> QueryDef:
    """Look a query up on the whitelist, raising if it is not there.

    Deliberately not `argparse(choices=...)`. With `choices`, this function
    would be unreachable in production and a test exercising it would be
    testing dead code; here the rejection is on the only path a caller has.
    """
    try:
        return QUERIES[name]
    except KeyError as exc:
        raise UnknownQuery(
            f"unknown query {name!r}. Known queries: "
            + ", ".join(sorted(QUERIES))
        ) from exc


# ---------------------------------------------------------------------------
# Connection and rendering
# ---------------------------------------------------------------------------


def connect_readonly(db_path: str) -> sqlite3.Connection:
    """Open the database read-only, enforced by SQLite rather than by us.

    `mode=ro` makes any write raise `sqlite3.OperationalError: attempt to
    write a readonly database`. That is the property that makes this file
    reviewable once: a later edit cannot turn it into a writer by accident,
    only by changing this line.
    """
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _cell(value: Any) -> str:
    """NULL is printed as NULL. An empty string is a value; absence is not."""
    if value is None:
        return "NULL"
    return str(value)


def render_text(query: str, db_path: str, sections: list[Section]) -> str:
    out: list[str] = [f"# {query}  ({db_path})", ""]
    for section in sections:
        out.append(section.title)
        out.append("-" * len(section.title))
        if section.row_count == 0:
            # Never an empty block. Absence gets its own words, because an
            # empty region of a transcript reads as success.
            out.append("0 rows")
            out.append("")
            continue
        cells = [[_cell(v) for v in row] for row in section.rows]
        widths = [
            max(len(section.columns[i]), *(len(r[i]) for r in cells))
            for i in range(len(section.columns))
        ]
        out.append(
            "  ".join(c.ljust(widths[i]) for i, c in enumerate(section.columns))
        )
        out.append("  ".join("-" * w for w in widths))
        for row in cells:
            out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)))
        noun = "row" if section.row_count == 1 else "rows"
        out.append(f"{section.row_count} {noun}")
        if section.truncated:
            out.append(
                f"TRUNCATED at the --limit row cap of {section.cap}. More rows "
                f"exist and are not shown; re-run with a higher --limit."
            )
        out.append("")
    return "\n".join(out)


def render_json(query: str, db_path: str, sections: list[Section]) -> str:
    return json.dumps(
        {
            "query": query,
            "db": db_path,
            "sections": [
                {
                    "title": s.title,
                    "columns": list(s.columns),
                    "rows": [list(r) for r in s.rows],
                    "row_count": s.row_count,
                    # Explicit rather than inferable from `rows == []`. A
                    # consumer that forgets to check length must still see it.
                    "empty": s.row_count == 0,
                    "truncated": s.truncated,
                    "row_cap": s.cap,
                }
                for s in sections
            ],
        },
        indent=2,
        default=str,
    )


def _build_parser() -> argparse.ArgumentParser:
    listing = "\n".join(
        f"  {name:<24}{QUERIES[name].description}" for name in sorted(QUERIES)
    )
    parser = argparse.ArgumentParser(
        prog="inspect_live_db.py",
        description=(
            "Read-only inspector for the live cockpit database. Choose one of "
            "the named queries below; there is no free-form SQL argument."
        ),
        epilog="queries:\n" + listing,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", metavar="QUERY", help="one of the names listed below")
    parser.add_argument(
        "--db", default=DEFAULT_DB, help=f"database path (default {DEFAULT_DB})"
    )
    parser.add_argument(
        "-n",
        "--tail",
        type=int,
        default=5,
        help="rows for the tail queries (default 5)",
    )
    parser.add_argument("--date", help="budget day for credits-day, as YYYYMMDD")
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=1_200_000,
        help=(
            "pass-gaps: report holes wider than this (default 1200000, i.e. "
            "20 min -- above the 1035s ceiling on a healthy shut-window sleep)"
        ),
    )
    parser.add_argument(
        "--day-start-hour",
        type=int,
        default=DEFAULT_DAY_START_HOUR,
        help=f"UTC hour the budget day starts (default {DEFAULT_DAY_START_HOUR})",
    )
    parser.add_argument(
        "--pin",
        type=int,
        default=1564,
        help="recommendations.id ceiling for the *-for-pull queries (default 1564)",
    )
    parser.add_argument(
        "--odds-event-id",
        default=None,
        help=(
            "restrict prop-rungs to one Odds API fixture. Default None means "
            "every fixture, which will truncate on a full slate"
        ),
    )
    parser.add_argument(
        "--at",
        default=None,
        help=(
            "instant for window-freshness, ISO-8601 or epoch milliseconds "
            "(default: now)"
        ),
    )
    parser.add_argument(
        "--book",
        default=None,
        help="bookmaker key for book-rows (e.g. everygame)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_ROW_CAP,
        help=f"hard row cap per section (default {DEFAULT_ROW_CAP})",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        query = resolve_query(args.query)
    except UnknownQuery as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        conn = connect_readonly(args.db)
    except sqlite3.OperationalError as exc:
        print(f"cannot open {args.db} read-only: {exc}", file=sys.stderr)
        return 3

    try:
        sections = query.run(conn, args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        conn.close()

    render = render_json if args.json else render_text
    print(render(args.query, args.db, sections))
    return 0


# ---------------------------------------------------------------------------
# This file refused to run until 2026-08-10, because its authoring lane died on
# a session limit before writing a single test and an unverified reader pointed
# at `/data/cockpit.db` is exactly what this repo's mutation rule exists for.
#
# The refusal is lifted by `tests/test_inspect_live_db.py`, which builds its
# database by executing `backend/store/schema.sql` verbatim -- so a query naming
# a column the live box does not have fails locally -- and which observed every
# guard here go red under a named mutation: `mode=ro` widened to `mode=rwc`; the
# unknown-query raise softened to `QUERIES.get`; the cap's `+1` truncation probe
# removed; `>` widened to `>=` at exactly the cap; the `effective == cap` clause
# dropped so a query's own `-n` reported as truncation; the `0 rows` branch
# deleted; `_iso(None)` folded to the epoch; and `--pin` opened up. The mutation
# is written beside each test.
#
# What is still NOT established is in that file's docstring, and the shortest
# version of it is: a green suite says these nine queries are well-formed and
# their guards fire. It says nothing about what the live database contains.
#
# That gap is widest at `kalshi-quotes-band` (Q-W), whose entire purpose is to
# report what the live database contains. Its tests establish that the band, the
# hole at 300, the depth column, the 3-hour pre-game offset, both activation
# bars and the series substitution order behave as registered. They establish
# NOTHING about WNBA reachability, which is only readable after a deploy.
#
# Three things Q-W's own output does not establish, and a reader who takes the
# percentage at face value has misread all three:
#
# 1. **`pregame_instants` measures poller uptime, not time.** An instant is one
#    pass, and the loop runs every 15s while the odds window is open and every
#    900s when it is not (`backend/scheduler.py:113-183`), where "open" means
#    *any* league's odds are fresh -- nothing to do with WNBA. So instants
#    arrive in bursts, and a share of them is not a share of the clock.
#    Deduplicate to one look per burst before quoting a percentage.
# 2. **The denominator is conditional.** It counts only instants at which a
#    pre-game quote row with a readable event start already existed. A pass at
#    which the series had no pre-game market on the board contributes neither a
#    hit nor a miss, so the figure is "of the looks that could have seen one",
#    not "of the time".
# 3. **No lower bound on lead time, by design.** A fixture days away counts
#    toward the share on equal footing with one about to tip, on a book that is
#    thin, wide, and gone by the night the operator trades. `true_start_ms` is
#    emitted per event so this is visible; imposing a bound would be inventing a
#    registered threshold, which this query may not do.
# ---------------------------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
