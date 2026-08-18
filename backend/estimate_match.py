"""Join Joe's estimates to the venue's record, and the record to outcomes.

The reader for what the poller writes. `bet_estimates` rows are written by the
form; `venue_settlements` and `fills` by the poller; nothing joined them, so
`matched_position_id`, `match_status` and `outcome_win` were columns with a
writer's schema and no writer -- this repo's named defect, on the study's
critical path. This module closes it, per the calibration registration:

- **§7.2** -- `position_first_seen_ms` is the earliest venue-side evidence:
  the first fill's `created_time` when the mirror holds one, else the poll
  instant the poller already stamped, else `settled_time`. Which was used is
  stored (`position_time_source`), because a `settled_time` fallback nearly
  guts the two-clock rule and a reader must see that rather than infer it.
- **§7.3** -- an estimate matches the EARLIEST position on its ticker whose
  first-seen falls in `(estimate_server_ms, estimate_server_ms + 24h]`. Two
  estimates competing for one position: the LATER estimate matches, the
  earlier stays unmatched. Registered before any data, so it is not chosen
  here.
- **A6** -- for every estimate ticker discovery never saw (UFC, doubles,
  non-sports), fetch the market once so `market_results.py` can reach it.
  The public market result is the durable outcome path: a fact about the
  market, which cannot roll off a portfolio endpoint.
- **Outcomes** -- `outcome_win` prefers the public market result over the
  venue settlement's, and `outcome_source` records which spoke. A result that
  is neither `yes` nor `no` (a void) leaves `outcome_win` NULL: **a void is
  the absence of an outcome, not an outcome, and NULL is never 0.**

What this module must never do: name `stated_probability_bp` in any UPDATE
(the schema trigger aborts it below every caller, and the matcher has no
business near the measurement), write to `recommendations`, or compute any
aggregate over the estimate log -- matching is bookkeeping, the analysis is
embargoed until the registered stop.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from .kalshi.quotes import LiveQuoteSource, QuoteUnavailable

logger = logging.getLogger(__name__)

MATCH_WINDOW_MS = 24 * 3600 * 1000

# `market_result` / `kalshi_markets.result` values that ARE an outcome. A void
# or any novel string is refused: recorded verbatim where a column exists for
# it, never converted into a 0/1.
_DECIDED = ("yes", "no")


async def ensure_estimate_markets_known(
    conn: sqlite3.Connection, source: LiveQuoteSource, *, now_ms: int
) -> dict[str, int]:
    """A6: give every estimate ticker a `kalshi_markets` row, once.

    Uses `LiveQuoteSource.fetch` -- the fixture-pinned parser of
    `GET /markets/{ticker}` -- rather than a second reading of the same
    payload. The event row is inserted first (the FK demands it) with a NULL
    commence; `markets_awaiting_result` copes via `COALESCE(commence_ms,
    close_ms)`, late by up to the close lag and counted rather than lost.
    A ticker Kalshi refuses stays missing and is retried next cycle.
    """
    missing = [
        row["ticker"]
        for row in conn.execute(
            """
            SELECT DISTINCT e.ticker FROM bet_estimates e
            LEFT JOIN kalshi_markets m ON m.ticker = e.ticker
            WHERE m.ticker IS NULL
            """
        )
    ]
    fetched = unreadable = 0
    for ticker in missing:
        try:
            quote = await source.fetch(ticker, observed_ms=now_ms)
        except QuoteUnavailable as exc:
            unreadable += 1
            logger.warning("A6 ensure-fetch could not read %s: %s", ticker, exc)
            continue
        market = quote.market
        if market.series_ticker:
            conn.execute(
                "INSERT OR IGNORE INTO kalshi_series "
                "(series_ticker, first_seen_ms, last_seen_ms) VALUES (?, ?, ?)",
                (market.series_ticker, now_ms, now_ms),
            )
        if market.event_ticker:
            conn.execute(
                "INSERT OR IGNORE INTO kalshi_events "
                "(event_ticker, series_ticker, title, first_seen_ms, "
                " last_seen_ms) VALUES (?, ?, ?, ?, ?)",
                (
                    market.event_ticker,
                    market.series_ticker or None,
                    market.title,
                    now_ms,
                    now_ms,
                ),
            )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_markets "
            "(ticker, event_ticker, series_ticker, title, status, result, "
            " close_ms, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                market.ticker,
                market.event_ticker or None,
                market.series_ticker or None,
                market.title,
                market.status,
                market.result,
                market.close_ms,
                now_ms,
                now_ms,
            ),
        )
        fetched += 1
    conn.commit()
    return {"missing": len(missing), "fetched": fetched,
            "unreadable": unreadable}


def refine_first_seen(conn: sqlite3.Connection) -> int:
    """§7.2: upgrade a position's first-seen to its earliest mirrored fill.

    The poller stamps `poll_instant` at mirror time; a fill's `created_time`
    is strictly earlier venue-side evidence. Idempotent, and only ever moves
    the timestamp EARLIER -- the direction that tightens the two-clock check
    rather than flattering it. Also records `n_fills_in_position`, the
    blended-entry hazard count §9.1 asks for.
    """
    upgraded = 0
    rows = conn.execute(
        """
        SELECT s.id, s.position_first_seen_ms, s.position_time_source,
               f.first_fill_ms, f.n_fills
        FROM venue_settlements s
        JOIN (
            SELECT ticker, MIN(filled_ms) AS first_fill_ms,
                   COUNT(*) AS n_fills
            FROM fills WHERE source = 'venue_hand' GROUP BY ticker
        ) f ON f.ticker = s.ticker
        """
    ).fetchall()
    for row in rows:
        better = (
            row["position_time_source"] != "fill_created_time"
            or row["position_first_seen_ms"] != row["first_fill_ms"]
        )
        if better and row["first_fill_ms"] is not None:
            conn.execute(
                "UPDATE venue_settlements SET position_first_seen_ms = ?, "
                "position_time_source = 'fill_created_time', "
                "n_fills_in_position = ? WHERE id = ?",
                (row["first_fill_ms"], row["n_fills"], row["id"]),
            )
            upgraded += 1
    conn.commit()
    return upgraded


def _first_seen(row: Any) -> int:
    """The §7.2 chain, last resort `settled_time` -- which nearly guts rule 6,
    so a row landing there keeps `position_time_source` saying so."""
    if row["position_first_seen_ms"] is not None:
        return row["position_first_seen_ms"]
    return row["settled_ms"]


def match_estimates(conn: sqlite3.Connection, *, now_ms: int) -> dict[str, int]:
    """§7.3, exactly as registered. Returns counts, never statistics."""
    estimates = conn.execute(
        """
        SELECT id, ticker, estimate_server_ms FROM bet_estimates
        WHERE matched_position_id IS NULL
          AND stated_probability_is_revised = 0
          AND (match_status IS NULL OR match_status = '')
        ORDER BY estimate_server_ms
        """
    ).fetchall()
    if not estimates:
        return {"matched": 0, "expired": 0, "pending": 0}

    by_ticker: dict[str, list[Any]] = {}
    for est in estimates:
        by_ticker.setdefault(est["ticker"], []).append(est)

    matched = expired = pending = 0
    taken: set[int] = set()
    for ticker, ests in by_ticker.items():
        positions = sorted(
            conn.execute(
                "SELECT id, position_first_seen_ms, settled_ms "
                "FROM venue_settlements WHERE ticker = ?",
                (ticker,),
            ).fetchall(),
            key=_first_seen,
        )
        assigned: set[int] = set()
        for position in positions:
            if position["id"] in taken:
                continue
            seen = _first_seen(position)
            candidates = [
                e for e in ests
                if e["id"] not in assigned
                and e["estimate_server_ms"] < seen <= e["estimate_server_ms"] + MATCH_WINDOW_MS
            ]
            if not candidates:
                continue
            # Registered conflict rule: the LATER estimate matches.
            winner = max(candidates, key=lambda e: e["estimate_server_ms"])
            conn.execute(
                "UPDATE bet_estimates SET matched_position_id = ?, "
                "match_status = 'matched' WHERE id = ?",
                (position["id"], winner["id"]),
            )
            assigned.add(winner["id"])
            taken.add(position["id"])
            matched += 1
        for est in ests:
            if est["id"] in assigned:
                continue
            if now_ms > est["estimate_server_ms"] + MATCH_WINDOW_MS:
                # He estimated and did not bet. Leaves the primary population,
                # enters the §9.5(a) sensitivity -- a status, not a deletion.
                conn.execute(
                    "UPDATE bet_estimates SET match_status = "
                    "'unmatched_no_position' WHERE id = ?",
                    (est["id"],),
                )
                expired += 1
            else:
                pending += 1
    conn.commit()
    return {"matched": matched, "expired": expired, "pending": pending}


def score_outcomes(conn: sqlite3.Connection, *, now_ms: int) -> dict[str, int]:
    """`y_i`, preferring the durable public result over the perishable one.

    Writes per-row facts only. NULL stays NULL for unsettled and for voids;
    nothing here counts wins, and it must stay that way until the registered
    stop -- a scorer that also summarises is an interim look wearing a
    bookkeeping name.
    """
    rows = conn.execute(
        """
        SELECT e.id, e.ticker, s.side,
               s.market_result AS venue_result,
               m.result AS public_result
        FROM bet_estimates e
        JOIN venue_settlements s ON s.id = e.matched_position_id
        LEFT JOIN kalshi_markets m ON m.ticker = e.ticker
        WHERE e.outcome_win IS NULL
          AND e.matched_position_id IS NOT NULL
        """
    ).fetchall()
    scored = awaiting = 0
    for row in rows:
        public = (row["public_result"] or "").lower() or None
        venue = (row["venue_result"] or "").lower() or None
        if public in _DECIDED:
            result, source = public, "public_market"
        elif venue in _DECIDED:
            result, source = venue, "venue_settlement"
        else:
            # Unsettled, or void, or an unrecognised string: refuse. The raw
            # public string is still recorded where one exists, so a void is
            # visible rather than indistinguishable from "not yet".
            if public is not None:
                conn.execute(
                    "UPDATE bet_estimates SET market_result_public = ? "
                    "WHERE id = ?",
                    (public, row["id"]),
                )
            awaiting += 1
            continue
        conn.execute(
            "UPDATE bet_estimates SET outcome_win = ?, outcome_source = ?, "
            "market_result_public = ? WHERE id = ?",
            (
                1 if result == row["side"] else 0,
                source,
                public,
                row["id"],
            ),
        )
        scored += 1
    conn.commit()
    return {"scored": scored, "awaiting": awaiting}


async def run_match_pass(
    conn: sqlite3.Connection, source: LiveQuoteSource, *, now_ms: int
) -> dict[str, Any]:
    """The whole pass, in dependency order. One summary dict for the log."""
    known = await ensure_estimate_markets_known(conn, source, now_ms=now_ms)
    refined = refine_first_seen(conn)
    matches = match_estimates(conn, now_ms=now_ms)
    outcomes = score_outcomes(conn, now_ms=now_ms)
    return {
        "ensure": known,
        "first_seen_upgraded": refined,
        "match": matches,
        "outcomes": outcomes,
    }
