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

It is deliberately **one** artefact with a **fixed whitelist of named
queries**: reviewed once, safe forever, because a caller can only choose a
name, never supply SQL. (Before it shipped, the only way to ask the box a
question was to smuggle the code in with the question.)

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

**It is one artefact and eight files, and that is not a contradiction.** Until
2026-09-06 this was a single 254,479-byte module -- 97% of the 262,144-byte
ceiling at which the Read tool refuses a file outright, silently, so nobody
could add a query without making the file unopenable. The queries now live in
seven domain modules beside this one and this file is the registry: the
docstring, the whitelist, the parser and `main`. Nothing about the whitelist
property changed -- a caller still chooses a name and can never supply SQL --
and every name importable from `scripts.inspect_live_db` before the split is
still importable from it, by re-export.

Where a query lives, by the question it answers:

    inspect_live_db_common.py     Section, _fetch, the clocks, the renderers
    inspect_live_db_feed.py       credits, sweeps, prune frontier, freshness
    inspect_live_db_loop.py       RSS, walks, failures, gaps, pushes, volume
    inspect_live_db_lock.py       forward-lock and lock-attribution
    inspect_live_db_decisions.py  recommendations, the gate, CLV, props, Q-W
    inspect_live_db_parlays.py    parlay candidates, taps, resting combo bids
    inspect_live_db_money.py      hand bets, refusals, H4, the study arm

**Shipping it is two allowlists, not one.** `Dockerfile`'s `COPY scripts/`
sees only what `.dockerignore` lets into the build context, and that file
strips `scripts/*` and re-includes named files -- so a deploy alone never put
this script on the box; it took an `!scripts/inspect_live_db.py` line as
well (`b5419eb`, 2026-08-13; the history is in `.dockerignore`'s own comment
block and `docs/measurements/2026-08-13-qw-wnba-band-reachability-result.md`
§6). The `flyctl` line at the top of this docstring is what keeps it shipped:
`tests/test_has_callers.py::TestTheSshInvokedScriptsSurviveDockerignore`
derives the ssh-invoked set from each script naming its own
`/app/scripts/<name>.py`, so do not reword that line, and do not quote a
script count here -- read the test. The suite's fixture is a `tmp_path` file
built from `schema.sql`: "exits 0 on a real database" means a real *schema*,
not real rows.

**The split opened a third way for that allowlist to fail, and it is the
quietest yet.** Only this file declares `/app/scripts/inspect_live_db.py`, so
that derivation sees only this file; the seven modules it imports reach the
image through `.dockerignore`'s `!scripts/inspect_live_db_*.py` glob, and
`tests/test_inspect_live_db_modules.py` derives the requirement from the
import statements below rather than from anyone remembering. Ship this file
alone and the box gets an inspector that dies on its first import line, at an
ssh prompt, mid-incident.

A whitelisted query is safe to type, not free to run
--------------------------------------------------------
The live file is several GB on a 4 GB box whose page cache is the desk's
performance, and some names here -- `db-sizes` walks `dbstat` over every page
-- read the entire file to answer, evicting the working set so that the desk
is slow for minutes afterwards. One was run mid-diagnosis on 2026-09-18 because
nothing at the point of invocation said so. Every `QueryDef` therefore carries
a required `cost`, `cheap` or `walks-the-file`, classified from its SQL with
the reason beside the entry; the listing below prints it beside every name,
and `main` refuses a walk with exit 4 unless the caller passes
`--i-accept-the-cache-flush`. The flag is the caller saying they read the
cost. It does not make the query cheaper.

**`window-freshness` and `book-rows` no longer walk, and are still classified
as walks -- deliberately.** This paragraph said they "walk the whole h2h prefix
of an index" and that was true of their SQL until 2026-09-18, when both were
re-driven from `odds_fixtures` to match what `fixture_freshness` has done since
schema v47 (ADR 0167). The walk is gone; what remains is a seek per upcoming
fixture. **The classification stays `walks-the-file` until someone TIMES the
new statements on the live volume**, because demoting a cost from expensive to
cheap on reasoning rather than measurement is the flattering direction, and the
cost of being wrong lands on the desk's page cache rather than on the person
who reclassified it. Reclassifying is a deliberate edit to `KNOWN_WALKS` in
`tests/test_inspect_live_db.py` and wants a timing beside it. Until then the
flag is over-asked, which is the safe way to be wrong.

What this does not establish
----------------------------
- **Nothing about causation.** It reports rows. `credits-tail` showing a low
  `remaining_reported` is consistent with the budget having latched shut, and
  also with the plan genuinely being near its ceiling; the row does not say
  which, and this script does not model `CreditBudget` at all. Read
  `backend/odds/budget.py:202-223` for the refusal order and decide there.
- **Nothing about completeness, and `credits-day` now says so itself.** It
  counts the rows that were written. A sweep refused before the request went
  out writes no `api_credits` row by design (see the `odds_sweep_log` comment
  in `schema.sql`), so a low count is an absence of *calls*, not evidence of an
  outage -- and once the daily cap binds, the planner stops before any call is
  attempted for any sport, so the day's rows simply stop. That is byte-for-byte
  what a quiet slate looks like. `credits-day` therefore carries two
  `odds_sweep_log` sections scoped to the same budget day, which is where the
  distinction actually lives. `sweep-log` remains a separate query because it
  is deliberately all-time; it answers a different question and cannot be
  pointed at one day.
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
- **The second exemption: `manual-orders-audit` prints one ratio**, the
  largest ticker's share of the hand-bet rows. Same census argument -- an
  exhaustive `COUNT(*)` over a fixed snapshot, no sample, no null, no standard
  error -- and it is there because `CLAUDE.md`'s own measurement rules
  *require* the largest contributor's share beside any aggregate. That query
  is otherwise structure and counts only, and what it may never report is
  written into its own docstring rather than left to this paragraph.
- **The third exemption: `sharp-anchor-census` is a per-bucket split**, by
  `(league, market, anchored_on_sharp)`, which the rule above would forbid.
  Same census argument -- an exhaustive `COUNT(*)` over a bounded window under
  three keys, no sample, no null, no standard error. **It prints no ratio, and
  the name says census for that reason**: it was drafted as `sharp-anchor-rate`
  and renamed, because a query whose name promises the one quantity it must not
  emit is a query someone will eventually make emit it. Both values of the flag
  are rows, so the denominator is always on the screen. What it may never be
  read as -- a rate over `rows_n`, which is passes x rungs and not a count of
  opportunities -- is written into its own docstring.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

# Sibling modules, imported the way the live box imports them.
#
# `python /app/scripts/inspect_live_db.py` puts `/app/scripts` on `sys.path`
# and NOT `/app`, so the split modules must be importable as top-level names.
# The test suite reaches this file as `scripts.inspect_live_db`, where
# `/app/scripts` is not on the path at all -- so the directory is appended
# here, once, before the siblings are imported.
#
# APPENDED rather than inserted: at position 0 this directory would shadow
# repo-root modules for anything imported later in the same process, and under
# pytest that process is the whole suite. On the live box the directory is
# already `sys.path[0]`, so the append is a no-op there.
#
# This is why each sibling import below carries an E402 suppression: they
# cannot be hoisted above the code that makes them resolvable. The suppression
# is on each import individually, never file-wide, so a genuinely misplaced
# import added later still fails lint. (Written as prose rather than with the
# literal directive spelled out -- ruff parses a `noqa` token inside a comment
# and warns about the punctuation around it.)
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.append(_HERE)

# ---------------------------------------------------------------------------
# The domain modules, and the re-export surface.
# ---------------------------------------------------------------------------
#
# **Why this file is a registry and not the queries.** On 2026-09-06 it was
# 254,479 bytes -- 97% of the 262,144-byte ceiling at which the Read tool
# refuses a file outright, and the failure mode is silent truncation rather
# than an error. Nobody could add a query without pushing it over, and a trim
# had already been tried. The split is by domain, one module per question the
# database gets asked; `QUERIES` below is unchanged and is still the only
# whitelist.
#
# **Every name a caller could import from this module before the split is
# still importable from it.** The tests reach forty-eight of them by name and
# four more as attributes, and re-exporting keeps `scripts.inspect_live_db`
# the single address for all of them -- so a session that greps for a symbol
# lands somewhere it still exists.

from inspect_live_db_common import (  # noqa: E402,F401
    DEFAULT_DAY_START_HOUR,
    DEFAULT_DB,
    DEFAULT_ROW_CAP,
    _MS_PER_DAY,
    Section,
    UnknownQuery,
    _bind,
    _cell,
    _day_bounds,
    _derive_iso,
    _fetch,
    _iso,
    _month_start_ms,
    _quantile,
    _window_section,
    connect_readonly,
    render_json,
    render_text,
)
from inspect_live_db_decisions import (  # noqa: E402,F401
    _ACTIONABLE_PREDICATE,
    _QW_BAND_HI,
    _QW_BAND_HOLE,
    _QW_BAND_LO,
    _QW_MIN_EVENTS,
    _QW_PREGAME_OFFSET_MS,
    _QW_SERIES_ORDER,
    _QW_WINDOW_END_MS,
    _QW_WINDOW_START_MS,
    _BOOKMAKERS_DEFAULT_DAYS,
    _FAIR_PRICES_DEFAULT_DAYS,
    _SHARP_ANCHOR_DEFAULT_DAYS,
    _SQL_ACTIONABLE_FAIR,
    _SQL_ACTIONABLE_ROWS,
    _q_actionable_audit,
    _q_closing_lines_for_pull,
    _q_clv_coverage,
    _q_clv_signal_pull,
    _q_decision_dump,
    _q_events_for_pull,
    _q_fair_prices_by_market,
    _q_kalshi_quotes_band,
    _q_prop_bookmakers,
    _q_prop_rungs,
    _q_results_for_pull,
    _q_series,
    _q_sharp_anchor_census,
    _q_team_bookmakers,
    _qw_verdict,
)
from inspect_live_db_feed import (  # noqa: E402,F401
    _QUOTE_RETENTION_MS,
    _STALE_LIMIT_DEFAULT_S,
    _VISIT_GAP_MS,
    _VISIT_SINCE_DEFAULT_DAYS,
    _cluster_visits,
    _q_book_rows,
    _q_credits_by_sport,
    _q_credits_day,
    _q_credits_month,
    _q_credits_rate,
    _q_credits_reset,
    _q_credits_tail,
    _q_prune_frontier,
    _q_sweep_log,
    _q_visit_freshness,
    _q_window_freshness,
)
from inspect_live_db_lock import (  # noqa: E402,F401
    ADR_0091_DEPLOY_MS,
    LOCK_ALPHA,
    LOCK_WINDOW_S,
    _process_start_index,
    _q_forward_lock,
    _q_lock_attribution,
    _read_rss_samples,
)
from inspect_live_db_loop import (  # noqa: E402,F401
    FAILURE_LOG_NAME,
    WALK_LOG_NAME,
    _LOOP_RSS_COLUMNS,
    _q_db_sizes,
    _q_failure_journal,
    _q_loop_rss,
    _q_notifications,
    _q_pass_gaps,
    _q_read_incidents,
    _q_walk_log,
    loop_rss_path,
)
from inspect_live_db_money import (  # noqa: E402,F401
    STUDY_LOSS_CEILING_DOLLARS,
    VOID_RESULTS,
    _H4_STUDY_START_MS,
    _SQL_MANUAL_ABSENT_REASONS,
    _SQL_MANUAL_CENSUS,
    _SQL_MANUAL_CONTRACTS,
    _SQL_MANUAL_SNAPSHOT,
    _SQL_MANUAL_STATUS,
    _SQL_MANUAL_TICKERS,
    _q_estimate_match_status,
    _q_h4_balance_spans,
    _q_h4_settlement_balance,
    _q_manual_order_refusals,
    _q_manual_orders_audit,
    _q_study_stop,
)
from inspect_live_db_parlays import (  # noqa: E402,F401
    _SQL_PARLAY_CANDIDATES,
    _q_combo_bids_tail,
    _q_combo_position_gaps,
    _q_combo_position_orphans,
    _q_parlay_candidates_timing,
    _q_parlay_lookups_tail,
)


# ---------------------------------------------------------------------------
# What a query costs the box, declared on the class rather than noted per query.
# ---------------------------------------------------------------------------
#
# The live file is several GB on a 4 GB machine whose page cache IS the desk's
# performance. A whitelisted query is safe to type -- it cannot write and it
# cannot carry SQL -- but it is not free to run: one that walks the whole file
# or a whole index prefix evicts the working set, and every read the desk makes
# for minutes afterwards is a disk read. On 2026-09-18 `db-sizes` was run in
# the middle of a latency diagnosis because nothing at the point of invocation
# said it was expensive (tasks/lessons.md, 2026-09-18 twentieth). So the cost
# is a REQUIRED field of `QueryDef`: an entry without one does not import, and
# `main` refuses a `WALKS_THE_FILE` query unless the caller passes the flag
# that names what they are accepting.
#
# Two values, deliberately, so the question is "does this scale with the
# answer or with the data?" and not a tier to argue about:
#
#   CHEAP           bounded key range, a file tail, or an unbounded read of a
#                   table whose size is bounded by something other than time
#                   (one row per hand bet, per vendor call under a daily cap).
#   WALKS_THE_FILE  `dbstat`; a GROUP BY / DISTINCT / COUNT over the whole of
#                   odds_snapshots, fair_prices, kalshi_quotes or poll_log; a
#                   window of days over a non-covering index on one of them;
#                   or a scan with no bounded key at all. When unsure, this --
#                   the comment beside the entry says why.
#
# The class is a property of the SQL, not of today's row count: a table that
# was small when a query shipped and gains a row every poll is classified by
# what the SQL lets it become.
CHEAP = "cheap"
WALKS_THE_FILE = "walks-the-file"
COSTS = frozenset({CHEAP, WALKS_THE_FILE})

#: The flag that lets a `WALKS_THE_FILE` query run. Named for what the caller
#: is accepting, not for what they want, so it cannot be typed by habit.
ACCEPT_FLAG = "--i-accept-the-cache-flush"

#: Exit status when a walk is refused. 2 is a usage error, 3 an unopenable
#: database; 4 is "refused on cost", so a wrapper can tell them apart.
EXIT_REFUSED_ON_COST = 4

#: What the box has to cache with. A 4 GB machine minus the runner and the
#: OS; `docs/measurements/2026-09-18-the-window-route-walked-every-odds-row.md`
#: read ~3.1 GB available with the file at 6.3 GB.
PAGE_CACHE_GB = 3


@dataclass(frozen=True)
class QueryDef:
    description: str
    run: Callable[[sqlite3.Connection, Any], list[Section]]
    # No default. A default of CHEAP would let a new query skip the question
    # and be wrong silently, which is the failure this field exists to stop.
    cost: str

    def __post_init__(self) -> None:
        if self.cost not in COSTS:
            raise ValueError(
                f"cost must be one of {sorted(COSTS)}, got {self.cost!r}"
            )


def refusal_sentence(name: str, db_path: str) -> str:
    """The one sentence a refused walk prints: the cost, and what accepts it.

    The file size is read with a `stat`, which touches no page of the file --
    the sentence about the cache must not itself cost the cache anything.
    Unreadable resolves to "the whole file", never to a number.
    """
    try:
        size = os.path.getsize(db_path)
    except OSError:
        whole = "the whole file"
    else:
        whole = f"the whole {size / 1e9:.1f} GB file"
    return (
        f"{name} is refused without {ACCEPT_FLAG}: it walks {whole} through a "
        f"page cache of about {PAGE_CACHE_GB} GB, and the desk will be slow "
        f"for minutes afterwards."
    )


QUERIES: dict[str, QueryDef] = {
    "credits-tail": QueryDef(
        "The last N api_credits rows (-n, default 5), newest first, each "
        "called_ms also rendered ISO-8601 UTC. Answers: what remaining_reported "
        "did the most recent response carry?",
        _q_credits_tail,
        cost=CHEAP,
    ),
    "credits-day": QueryDef(
        "Every api_credits row in one budget day (--date YYYYMMDD, boundary "
        "--day-start-hour, default 10), plus the row count and summed cost, "
        "plus what the passes DECIDED that day from odds_sweep_log -- by "
        "outcome, and with refusals and skips grouped by the reason they "
        "name. Answers the question the spend figure provokes: the calls stop "
        "at 15:40Z; did the daily cap bind, or was there nothing to buy? "
        "Exhaustion is an absence in api_credits and nowhere else.",
        _q_credits_day,
        cost=CHEAP,
    ),
    "credits-month": QueryDef(
        "Month-to-date summed cost, and MIN/MAX of remaining_reported and "
        "used_reported, over the UTC calendar month. The vendor's billing "
        "period is NOT the calendar month, so this window can straddle a "
        "reset and its MAX then describes a period that has ended -- run "
        "credits-reset before quoting either extreme.",
        _q_credits_month,
        cost=CHEAP,
    ),
    "credits-reset": QueryDef(
        "Consecutive api_credits rows where used_reported fell by more than "
        "the later row's own cost, with what remaining_reported did across "
        "the same pair -- which is what tells a billing-period roll from a "
        "tier purchase. Section B is the readable/unreadable split, without "
        "which an empty section A cannot be read. Exists because "
        "credits-month reported a max of 5,016 that no longer described the "
        "current period and nothing on the screen said so.",
        _q_credits_reset,
        # Unbounded over api_credits, but that table is one row per vendor
        # call under a 700-credit daily cap, so its size is bounded by the
        # budget, not by time.
        cost=CHEAP,
    ),
    "credits-by-sport": QueryDef(
        "Cost and call count per budget day per sport_key (--since YYYYMMDD, "
        "default the last 7 days; --day-start-hour sets the boundary), then "
        "day totals with the largest sport NAMED beside them. Satisfies "
        "CLAUDE.md's largest-contributor rule without dumping every row. No "
        "share is computed: day_cost and top_sport_cost are printed side by "
        "side and the division is the reader's.",
        _q_credits_by_sport,
        cost=CHEAP,
    ),
    "credits-rate": QueryDef(
        "Calls and cost per UTC clock hour per sport (--since), then the "
        "busiest hour each sport reached. The ten-minute attention cadence "
        "is six calls an hour and cannot be more, so 6 is a fully attended "
        "hour and above 6 is something else buying too. Hours with no call "
        "produce no row; sweep-log and pass-gaps separate an idle floor from "
        "a dead recorder.",
        _q_credits_rate,
        cost=CHEAP,
    ),
    "sweep-log": QueryDef(
        "odds_sweep_log: COUNT and pass_ms range grouped by outcome, then the "
        "last N rows in full (-n, default 5).",
        _q_sweep_log,
        # All-time GROUP BY, over a table that gains one row per planner
        # pass per sport -- a few hundred a day.
        cost=CHEAP,
    ),
    "notifications": QueryDef(
        "What reached the phone: count and delivered by kind, then the last N "
        "rows (-n, default 5) with their dedupe keys. /api/health publishes a "
        "TOTAL only, which cannot say which kind moved.",
        _q_notifications,
        cost=CHEAP,
    ),
    "loop-rss": QueryDef(
        "loop_rss.jsonl beside the database: the last N per-pass lines (-n, "
        "default 5 -- pass a few hundred), newest first. RSS and headroom, "
        "then wal_kb/db_kb and candidate_rows/candidate_ms beside "
        "leg_price_link_ms/leg_store_quotes_ms. A null is 'this row predates "
        "the column', never 'the WAL is empty'.",
        _q_loop_rss,
        cost=CHEAP,
    ),
    "pass-gaps": QueryDef(
        "Holes over --gap-ms (default 1200000) in the last N odds_sweep_log "
        "rows (-n, default 5 -- pass a few hundred), beside every loop_failures "
        "row. A gap WITH failures inside it was a failing loop; a gap with NONE "
        "never came back to raise. The pair is the reading; neither half is.",
        _q_pass_gaps,
        cost=CHEAP,
    ),
    "walk-log": QueryDef(
        "Which catalogue walk each pass took, from loop_walk.jsonl beside the "
        "db. First section is the anomaly: QUOTE passes that took the FULL "
        "walk, i.e. priceable_series returned nothing and the ~22s cadence is "
        "paginating ~14,000 events. `prev_discovered` falling off a cliff is a "
        "classification regression; decaying is an emptying slate.",
        _q_walk_log,
        cost=CHEAP,
    ),
    "read-incidents": QueryDef(
        "The last N api_read_incidents rows (-n, default 5), newest first, "
        "beside a per-kind count. read_budget = the API's 25 s statement "
        "budget fired (a 503; screens say 'Backend unreachable'); health_probe "
        "= the loop's 2 s loopback probe failed, checked every pass. Path, "
        "elapsed_ms and the exception class are the reading; the count is a "
        "FLOOR because the writer is best-effort under contention.",
        _q_read_incidents,
        cost=CHEAP,
    ),
    "failure-journal": QueryDef(
        "Every pass failure as `loop_failures.jsonl` saw it, beside what the "
        "`loop_failures` TABLE kept (-n, default 5). Section 1 is the point: "
        "a journal line with no table row is a failure the table could not "
        "record, which is exactly the 'database is locked' class -- so a "
        "non-zero count there makes every table-derived count a FLOOR. "
        "Section 2 carries the durable recorder's own poisoned-connection "
        "verdict and section 3 what the rollback before it found -- read "
        "in_transaction first, because rollback_ok = True on a connection "
        "with nothing open is a no-op. Section 5 is the newest traceback, "
        "which lives nowhere else.",
        _q_failure_journal,
        cost=CHEAP,
    ),
    "forward-lock": QueryDef(
        "Did ADR 0091 close the `database is locked` symptom AFTER the "
        "deploy? Section 11 of docs/measurements/2026-09-01-forward-lock-"
        "instrument-registration.md. Adds the three capabilities that "
        "registration named as missing: a T0 boundary from the in-DB "
        "mirror marker, the MIRROR/FAST cycle split, and the E / E* / "
        "E_n arithmetic. REFUSES every verdict below E* except SIGNATURE "
        "PERSISTS, which is always-valid. C3/C4/C5 are NOT COMPUTED and "
        "block FIX CONFIRMED by design. Separate from lock-attribution, "
        "which answers a different, completed registration.",
        _q_forward_lock,
        # `FROM poll_log GROUP BY polled_ms` with no bound: one row per venue
        # poll, every cycle, since the table was created. Small when the
        # registration ran; nothing in the SQL keeps it so.
        cost=WALKS_THE_FILE,
    ),
    "lock-attribution": QueryDef(
        "Does each `database is locked` burst land inside a poller cycle? "
        "Joins the journal's failure stamps to poll_log cycle starts and "
        "runs the rule fixed in docs/measurements/"
        "2026-09-01-lock-holder-attribution-registration.md BEFORE the "
        "join existed. Unit is the BURST. Section 1 REFUSES if poll_log "
        "does not span the journal. THERE IS NO EXONERATING VERDICT: the "
        "design can convict the poller and cannot clear it, because a "
        "small k is exactly what the null predicts.",
        _q_lock_attribution,
        # `SELECT DISTINCT polled_ms FROM poll_log` and `COUNT(*)` over the
        # same table, unbounded -- the same walk as forward-lock.
        cost=WALKS_THE_FILE,
    ),
    "study-stop": QueryDef(
        "Has the $100 money arm fired? It gates POST /api/estimates with "
        "423 'logging is closed, permanently', and nothing on the machine "
        "could report it. Mirrors ADR 0044 A2's formula verbatim over "
        "study-period venue_settlements, pinned against "
        "`estimates.study_loss_dollars` by a test. A refusal is CANNOT "
        "KNOW and never 'not stopped'. The self-lockout is a second, "
        "independent 423 and is reported beside it.",
        _q_study_stop,
        cost=CHEAP,
    ),
    "prune-frontier": QueryDef(
        "How far prune_quotes has got: MIN(COALESCE(confirmed_ms, "
        "observed_ms)) over prunable rows, the 3-day cutoff, and the backlog "
        "still below it. The durable stand-in for `quotes_pruned`, which is "
        "persisted nowhere. Take it either side of a window to say whether a "
        "prune ran inside one.",
        _q_prune_frontier,
        # Three `COUNT(*)` and a `MIN` over the whole of kalshi_quotes
        # (~400 MB, ~6M rows at last reading), each with a `NOT IN` against
        # recommendations. Four full walks of the quote table.
        cost=WALKS_THE_FILE,
    ),
    "results-for-pull": QueryDef(
        "kalshi_markets (incl. result) for the pinned recommendation "
        "population (--pin, default 1564). ~120 rows.",
        _q_results_for_pull,
        cost=CHEAP,
    ),
    "events-for-pull": QueryDef(
        "kalshi_events reached through the pinned markets. ~60 rows.",
        _q_events_for_pull,
        cost=CHEAP,
    ),
    "closing-lines-for-pull": QueryDef(
        "closing_lines for the pinned tickers. ~240 rows.",
        _q_closing_lines_for_pull,
        cost=CHEAP,
    ),
    "series": QueryDef(
        "kalshi_series: series_ticker and league. ~10 rows.",
        _q_series,
        cost=CHEAP,
    ),
    "prop-bookmakers": QueryDef(
        "odds_snapshots rows carrying outcome_description (i.e. player props), "
        "grouped by bookmaker with quote/event/market-key/sport counts and the "
        "fetched_ms range. Answers: does any sharp book quote props, or are "
        "slots of the named ten buying nothing? Bounded by a commence_ms "
        "floor (--since YYYYMMDD, default 7 days) and optionally --sport.",
        _q_prop_bookmakers,
        # Seven days of odds_snapshots by commence_ms through a non-covering
        # index, then COUNT(DISTINCT) x3 GROUP BY bookmaker: every row of
        # every fixture in the window is fetched from the table.
        cost=WALKS_THE_FILE,
    ),
    "sharp-anchor-census": QueryDef(
        "How often the consensus actually HAD a sharp book to anchor on: "
        "fair_prices joined to event_links, counted by (league, market, "
        "anchored_on_sharp). This is the MEASUREMENT that team-bookmakers is "
        "only the input to -- book presence is an upper bound on anchoring, "
        "because devig runs per rung and a book must have quoted that exact "
        "line two-sided. Both values of the flag are emitted so the "
        "denominator is on the screen; no ratio is printed. Read `links`, not "
        "`rows_n`: rungs within a fixture are not independent. Bounded by a "
        "computed_ms floor (--since YYYYMMDD, default 2 days) and optionally "
        "--league (Kalshi's string, e.g. 'NCAA Football').",
        _q_sharp_anchor_census,
        # Two days of fair_prices through idx_fair_market_computed, which is
        # not covering -- at the measured ~130 MB/day that is hundreds of MB
        # of table pages, each joined to event_links.
        cost=WALKS_THE_FILE,
    ),
    "team-bookmakers": QueryDef(
        "The mirror of prop-bookmakers across the same discriminator: "
        "odds_snapshots rows with outcome_description NULL (i.e. h2h, spreads "
        "and totals), grouped by sport_key AND bookmaker, with the distinct "
        "market keys each book returned. Answers: did all ten named books come "
        "back on each sport, and on which markets? That matters because a "
        "sport no sharp book quotes does not fail and does not log -- "
        "consensus_devig falls back to every book it has, soft ones included. "
        "Three sections: the window, the keys ODDS_BOOKMAKERS asked for, the "
        "response. Bounded by a commence_ms floor (--since YYYYMMDD, default "
        "7 days) and optionally --sport.",
        _q_team_bookmakers,
        # Same shape as prop-bookmakers: seven days of odds_snapshots rows
        # fetched through a non-covering index, GROUP_CONCAT(DISTINCT).
        cost=WALKS_THE_FILE,
    ),
    "fair-prices-by-market": QueryDef(
        "Is a bought input actually consumed at runtime? Section A is what "
        "was BOUGHT (odds_snapshots by market, per book per outcome), "
        "section B what was CONSUMED (fair_prices by market, per devigged "
        "outcome), each with its row count, distinct keys and computed_ms "
        "range. A market in A and absent from B is a line item with no "
        "reader -- this is what settled whether the `spreads` half of "
        "ODDS_MARKETS reaches a decision. Read last_ms, not just the count: "
        "a large count whose newest row is weeks old is a path that stopped "
        "running. No ratio between the sections; their row grains differ. "
        "Bounded by --since YYYYMMDD (default 7 days), applied to "
        "commence_ms in A and computed_ms in B -- one instant, two clocks, "
        "each printed as its own window section.",
        _q_fair_prices_by_market,
        # Seven days of odds_snapshots AND seven days of fair_prices, each
        # GROUP BY market with COUNT(DISTINCT): a week of the two largest
        # tables, fetched row by row.
        cost=WALKS_THE_FILE,
    ),
    "prop-rungs": QueryDef(
        "Raw player-prop rungs at the latest sweep per fixture, one row per "
        "(event, book, base_market, feed, player, point) with Over and Under "
        "pivoted into columns. Emits rows, not a verdict: the registered "
        "arithmetic lives in scripts/analyze_prop_onesided.py. Narrow with "
        "--odds-event-id, or raise --limit; the whole record truncates.",
        _q_prop_rungs,
        # `FROM odds_snapshots WHERE outcome_description IS NOT NULL` has no
        # index and no time bound; only --odds-event-id narrows it, and the
        # class is a property of the query, not of one flag.
        cost=WALKS_THE_FILE,
    ),
    "actionable-audit": QueryDef(
        "Every row in the gate's `actionable` population -- the ones the "
        "strategy would have bet -- in two sections: A the decision (ask, "
        "edge, both sizes, all four clocks), B the provenance (all four devig "
        "readings, book_count, anchored_on_sharp, market_width). Prints rows "
        "and no verdict. Answers: did these clear a real bar, or land in a gap?",
        _q_actionable_audit,
        # An `IS NULL` seek on idx_recs_open; fair_prices is reached by
        # primary key only for the handful of rows that pass the predicate.
        cost=CHEAP,
    ),
    "manual-orders-audit": QueryDef(
        "The hand-bet record (`manual_orders`), STRUCTURE AND COUNTS ONLY: "
        "the census with its real/dry-run split and submitted_ms range, "
        "status buckets over a fixed vocabulary, the ADR 0082 consensus "
        "snapshot's coverage split by whether the ticker is a KXMVE "
        "combination, why the absent ones are absent, rows per ticker with "
        "the largest one's share, and contracts per order. Reports NO P&L, "
        "profit, win rate, CLV, settled outcome or typed estimate -- the "
        "2026-08-29 registration fixes which of those may ever carry a "
        "verdict, and an inspector that leaked one would let the rule be "
        "chosen after the answer. Answers: how big is the record, and how "
        "much of it can be interpreted later?",
        _q_manual_orders_audit,
        cost=CHEAP,
    ),
    "clv-signal-pull": QueryDef(
        "The CLV signal test's registered §2 population (horizon 0.0), one row "
        "per recommendation with its half-spread control joined from "
        "kalshi_quotes. A transcription of §S1 as amended by §A1/§A2/§A2.2 -- "
        "four suppression codes excluded by delimited instr, price bounded to "
        "[10,989], cluster key COALESCE(event_ticker, ticker). Emits rows and "
        "NO statistic; scripts/run_signal_test.py computes beta.",
        _q_clv_signal_pull,
        # Every scored recommendation (no index serves `clv_scored_ms IS NOT
        # NULL`), each with a correlated seek into kalshi_quotes: a walk of
        # one table and a random read of another per row.
        cost=WALKS_THE_FILE,
    ),
    "parlay-candidates-timing": QueryDef(
        "The parlay desk's candidate scan, timed and EXPLAINed on the live "
        "database, beside a census of the rows it reads over and the wall "
        "time of the odds_snapshots GROUP BY on its own. Answers: /api/parlays "
        "took over 30s on 2026-08-30 while /api/board took ~2s and the whole "
        "ladder's copulas cost under a second -- which half of this statement "
        "is it?",
        _q_parlay_candidates_timing,
        # Runs the whole candidate scan, then the odds_snapshots
        # `GROUP BY odds_event_id` on its own, to TIME them. Expensive by
        # design: it exists to measure the walk.
        cost=WALKS_THE_FILE,
    ),
    "parlay-lookups-tail": QueryDef(
        "The last N \"Price on Kalshi\" taps (-n, default 5), newest first: "
        "status, the collection, the MINTED market ticker, what its book said "
        "and the card's fair value at the time. The only record anywhere that "
        "a given combination market exists on the exchange. No P&L, no "
        "outcome, no verdict.",
        _q_parlay_lookups_tail,
        cost=CHEAP,
    ),
    "combo-position-gaps": QueryDef(
        "Combinations bought with REAL money that no `parlay_positions` row "
        "watches, so `/hedge` -- the only exit an enter-only combination has "
        "-- cannot see them. Both money-spending statuses (`filled` and "
        "`partially_filled`), with the latest venue poll beside each so an "
        "OPEN one is separable from history, and `unrecognised_response` "
        "orders listed SEPARATELY because those may or may not have spent "
        "anything. The detector for a write that is designed to fail "
        "silently: ADR 0125's writer is wrapped in a bare `except` so that "
        "bookkeeping can never fail a purchase, which means nothing raises "
        "when it does fail. Emits NO parlay_positions row, no count of them "
        "and no rate -- the table appears only inside a NOT EXISTS. Carries "
        "no verdict on the 2026-09-08 parlay-positions registration and is "
        "NOT its §8 read. Answers: is a live position unwatched right now?",
        _q_combo_position_gaps,
        # Four correlated subqueries into venue_positions BY TICKER per
        # KXMVE order, and venue_positions has no ticker index -- each is a
        # full scan of a table that grows every positions poll.
        cost=WALKS_THE_FILE,
    ),
    "combo-position-orphans": QueryDef(
        "The inverse of `combo-position-gaps`: OPEN `parlay_positions` rows "
        "with no `manual_orders` row behind them, split into two sections. "
        "`combo_ticker IS NULL` is hand-recorded via `POST "
        "/api/hedge/positions` -- every `sportsbook` row is shaped like this "
        "always -- and is reported as the expected, harmless case. "
        "`combo_ticker IS NOT NULL` and still no matching order is the "
        "section worth attention, and it is NOT proof of a lost write: that "
        "route accepts a caller-supplied ticker, so a hand-typed one naming "
        "a real market looks identical here to a fill whose position-writer "
        "failed. Emits parlay_positions rows (this is the read gaps cannot "
        "be, not the registered R/G statistic -- no rate, no count over a "
        "run). Answers: is a position on /hedge's screen one this desk can "
        "actually trace to a fill?",
        _q_combo_position_orphans,
        cost=CHEAP,
    ),
    "combo-bids-tail": QueryDef(
        "The last N resting bids the desk placed on a combination (-n, "
        "default 5), newest first: price, contracts, what is committed, the "
        "exchange shard, and the AUTO-CANCEL DEADLINE. A NULL deadline means "
        "the bid will never be withdrawn automatically, which the screen "
        "promises it will be. No P&L, no outcome, no verdict.",
        _q_combo_bids_tail,
        cost=CHEAP,
    ),
    "db-sizes": QueryDef(
        "Where the bytes went: file-level page counts with the amount a VACUUM "
        "could reclaim, then stored bytes per table and index via dbstat "
        "(row counts as a labelled fallback if dbstat is not compiled in). "
        "Answers: prune a table, or buy a bigger volume?",
        _q_db_sizes,
        # `dbstat` visits every page of every btree: it reads the entire
        # file through the page cache. This is the query that was run
        # mid-diagnosis on 2026-09-18 and slowed the desk for minutes.
        cost=WALKS_THE_FILE,
    ),
    "decision-dump": QueryDef(
        "Every recommendation ever written, one row each, with its four devig "
        "readings, book_count, anchored_on_sharp, market_width, both sizes, "
        "suppressed_reason and its CLV score. Emits rows and NO aggregate: the "
        "registered arithmetic belongs in scripts/. Feeds the free "
        "falsification query and the anchored-vs-unanchored split. Raise "
        "--limit above the record size and check `truncated` before analysing.",
        _q_decision_dump,
        # Every recommendation ever written, with a fair_prices seek per row
        # into the largest table in the file. No bound but --limit, which the
        # description tells the caller to raise.
        cost=WALKS_THE_FILE,
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
        # Section B joins `SELECT odds_event_id, MIN(commence_ms) FROM
        # odds_snapshots GROUP BY odds_event_id`: a full walk of that table's
        # index, plus unbounded GROUP BYs over recommendations.
        cost=WALKS_THE_FILE,
    ),
    "window-freshness": QueryDef(
        "fixture_freshness recomputed at --at (ISO or epoch ms, default now): "
        "per-fixture consensus ages the window indicator would compute, then "
        "the same population by book, stalest first. Answers: which book's "
        "own last_update stamp closed the window mid-refresh-interval?",
        _q_window_freshness,
        # No longer a walk: re-driven from odds_fixtures 2026-09-18 to match
        # fixture_freshness since v47, so it is a seek per upcoming fixture
        # rather than the whole h2h prefix of idx_odds_window twice. Kept at
        # WALKS_THE_FILE until the new statements are TIMED on the live
        # volume -- demoting a cost on reasoning rather than measurement errs
        # toward the desk's page cache paying for the mistake. See the module
        # docstring's "A whitelisted query is safe to type" section.
        cost=WALKS_THE_FILE,
    ),
    "book-rows": QueryDef(
        "One bookmaker's h2h rows (--book, required) in the window-freshness "
        "population at --at: two rows per fixture = contributes to the "
        "runner's consensus, one = dropped as incomplete. Answers: did the "
        "laggard book's stamp age the consensus, or only the window flag?",
        _q_book_rows,
        # The same driver as window-freshness, and it has to be, or "the
        # window-freshness population" above stops being one population.
        # Re-driven from odds_fixtures 2026-09-18; kept at WALKS_THE_FILE on
        # the same untimed-until-measured grounds.
        cost=WALKS_THE_FILE,
    ),
    "visit-freshness": QueryDef(
        "desk_attention heartbeats clustered into visits (--since YYYYMMDD, "
        "default last 7 days; --gap-ms, default the attention TTL), one row "
        "each: consensus age at the first and last stamp via the "
        "window-freshness query, ms to the first attention buy, refused "
        "sweeps, and which sports' windows were open. Answers: does a cold "
        "open meet the ~60-min worst case the design permits?",
        _q_visit_freshness,
        # Runs the window-freshness query TWICE PER VISIT over --since
        # (default seven days of visits). That query stopped being a walk on
        # 2026-09-18, but this one multiplies it by the visit count, so it is
        # the entry here with the strongest claim to the flag even after the
        # others are timed and possibly demoted.
        cost=WALKS_THE_FILE,
    ),
    "h4-settlement-balance": QueryDef(
        "H4's raw material, four sections and NO join: A settlements since "
        "study start (with market_result), B balance snapshots +/-900s of "
        "each (portfolio_value_tenths NULLs shown), C fills in the same "
        "windows, D balance poll_log including ok. Emits rows, no delta; "
        "the subtraction is done by a human beside the stated confounds.",
        _q_h4_settlement_balance,
        # Correlated EXISTS over venue_balance_snapshots and the balance rows
        # of poll_log with no bound on the outer table -- one row per poll,
        # walked in full to find the +/-900 s windows.
        cost=WALKS_THE_FILE,
    ),
    "h4-balance-spans": QueryDef(
        "Look 2's span-design raw material (Amendment 1 A12.3), five "
        "sections and NO join: A settlements since study start, B balance "
        "snapshots since study start UNWINDOWED, C fills likewise, D balance "
        "poll_log likewise including ok, E the whole venue_settlements table "
        "(pre-study included, for the P_j sum). Emits rows, no delta; "
        "pairing and residuals belong to the registered analyzer.",
        _q_h4_balance_spans,
        # Every section is an ordered index range from study start, so the
        # row cap stops the read at cap+1 rows; venue_settlements is one row
        # per settlement.
        cost=CHEAP,
    ),
    "manual-order-refusals": QueryDef(
        "Every refused hand bet, newest first: which numbered check fired, "
        "the exact detail shown, and the request values. Empty means no "
        "brake has ever fired; a reported refusal missing here means the "
        "write fell back to /data/manual_order_refusals.jsonl.",
        _q_manual_order_refusals,
        cost=CHEAP,
    ),
    "estimate-match-status": QueryDef(
        "Calibration §7.5 coverage: venue_settlements by estimate_match_status "
        "(total, then split combo vs single ticker, then every non-combo row), "
        "and bet_estimates by match_status. Answers: is the 0-position_unlogged "
        "cell real, or is a non-combo position sitting in out_of_scope?",
        _q_estimate_match_status,
        cost=CHEAP,
    ),
    "kalshi-quotes-band": QueryDef(
        "Q-W: was a WNBA market in 270-390 tenths (excl. 300) with depth >= 1 "
        "reachable at >= 80% of pre-game polling instants across >= 8 events, "
        "2026-08-07 to 2026-08-10? Window, band, bars and series order are "
        "registered constants, not flags. Precondition for the fee round.",
        _q_kalshi_quotes_band,
        # Per-ticker seeks on idx_quotes_ticker_time inside a fixed four-day
        # observed_ms window, reached from the (small) markets of one series.
        cost=CHEAP,
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


def _build_parser() -> argparse.ArgumentParser:
    listing = "\n".join(
        f"  {name:<24}{QUERIES[name].cost:<16}{QUERIES[name].description}"
        for name in sorted(QUERIES)
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
        ACCEPT_FLAG,
        action="store_true",
        help=(
            f"run a query listed as {WALKS_THE_FILE!r}. Without this a walk is "
            f"refused with exit {EXIT_REFUSED_ON_COST}: it reads the whole file "
            "through the page cache and the desk is slow for minutes afterwards. "
            "Not needed for a query listed as 'cheap'"
        ),
    )
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
        default=None,
        help=(
            "pass-gaps: report holes wider than this (default 1200000, i.e. "
            "20 min -- above the 1035s ceiling on a healthy shut-window "
            "sleep). visit-freshness: a heartbeat gap over this opens a new "
            f"visit (default {_VISIT_GAP_MS}, the attention TTL)"
        ),
    )
    parser.add_argument(
        "--since",
        default=None,
        help=(
            "visit-freshness, credits-by-sport, credits-rate: first budget "
            "day to read, as YYYYMMDD (default: the last "
            f"{_VISIT_SINCE_DEFAULT_DAYS} days). prop-bookmakers and "
            "team-bookmakers: the commence_ms floor, same format, default the "
            f"last {_BOOKMAKERS_DEFAULT_DAYS} days. sharp-anchor-census: the "
            f"computed_ms floor, default the last {_SHARP_ANCHOR_DEFAULT_DAYS} "
            "days. fair-prices-by-market: ONE instant applied to TWO clocks -- "
            "commence_ms in section A, computed_ms in section B -- default the "
            f"last {_FAIR_PRICES_DEFAULT_DAYS} days. Malformed is refused, not "
            "ignored -- a silently dropped bound is an unbounded query wearing "
            "a flag"
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
        "--sport",
        default=None,
        help=(
            "prop-bookmakers and team-bookmakers: restrict to one "
            "odds_snapshots.sport_key (e.g. americanfootball_nfl). Default "
            "None means every sport, which is still bounded by the --since "
            "commence_ms floor"
        ),
    )
    parser.add_argument(
        "--league",
        default=None,
        help=(
            "sharp-anchor-census: restrict to one event_links.league. This is "
            "KALSHI's own string, not the Odds API sport_key -- 'NCAA "
            "Football', 'Pro Football', 'Pro Baseball', 'Pro Basketball (W)'. "
            "An unrecognised value returns no rows, which reads exactly like a "
            "league with none, so run it unfiltered first"
        ),
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

    # Before the connection is opened, so a refusal touches no page of the
    # file. The flag is the caller saying they read the cost, and the sentence
    # is the cost, so the two are the same information in both directions.
    if query.cost == WALKS_THE_FILE and not args.i_accept_the_cache_flush:
        print(refusal_sentence(args.query, args.db), file=sys.stderr)
        return EXIT_REFUSED_ON_COST

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
# This file refused to run until 2026-08-10: its authoring lane died before a
# single test existed. `tests/test_inspect_live_db.py` lifts the refusal, and
# its module docstring names each guard here and the mutation that turned it
# red; what a green suite does NOT establish -- anything about what the live
# database contains -- is stated there too.
#
# That gap is widest at `kalshi-quotes-band` (Q-W), whose entire purpose is to
# report what the live database contains. Three things its output does not
# establish -- `pregame_instants` measures poller uptime, not time, so
# deduplicate to one look per burst before quoting a share; the denominator is
# conditional on a pre-game row existing; and there is no lower bound on lead
# time, by design -- are spelled out, verbatim from this block, in
# `docs/measurements/2026-08-13-qw-wnba-band-reachability-result.md` §9.
# ---------------------------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
