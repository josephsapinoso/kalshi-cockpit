"""The legs of a combination Joe bought off the desk, read from the venue.

Joe tails parlays: he copies a combination a sharp on Kalshi's own feed or a
friend built, and buys it in the Kalshi app (his answers, 2026-11-11). Such a
bet reaches this instance as a `venue_settlements` row and nothing else, so
`/bets` could say what it cost and whether it won and nothing about what it
was made of. He asked what made the winning ones win. The record could not
say, and this module is why it now can (ADR 0197, schema v69).

The venue's market for a combination carries `mve_selected_legs`, and it is
still served after settlement: `GET /markets/{ticker}`, and
`GET /historical/markets/{ticker}` for the older tickers the first answers
404 for (probed 2026-11-11 on three of his settled tickets; the fixtures in
`tests/fixtures/` are those captures' shape).

Rules this module keeps
-----------------------
- **All of a combination's legs or none.** A shorter list would read as the
  whole bet. One unreadable leg refuses the combination, the reason is kept
  in `venue_combo_leg_refusals`, and nothing is written to the legs table.
- **Written once.** A combination with legs here, or with a
  `parlay_positions` row (the desk already holds its legs), is skipped, so no
  leg is ever counted twice by a reader that unions the two tables.
- **A label is words or the combination is refused.** Where discovery has the
  leg's market, the label is its title (the convention
  `hedge.adopt_venue_combo` uses). Where it has not -- tennis, and every
  other sport the desk does not follow -- the words are the venue's own, from
  the combination's title, which lists one `"yes <words>"` / `"no <words>"`
  per leg in leg order. A title whose parts do not match the legs one for one
  is not guessed at.
- **Unreadable resolves to None, never to a value.** A leg market with no
  `yes`/`no` result stays unread; it is never "lost".
- **A result is taken only from a `finalized` market**, through discovery's
  own `read_market_result`: a `determined` result can still be reversed, and
  this table writes a result once and never overwrites it.

What this module does NOT establish
-----------------------------------
- Who built the combination, or that it was tailed at all. A combination
  bought off the desk may be Joe's own pick. The name is his word
  (`pick_sources.tailed_from`), never inferred from this table.
- Anything about a leg's price. The candle columns are filled by
  `scripts/backfill_venue_combo_legs.py`, and only while the venue still
  keeps the bars (about 80 days, ADR 0016).
- That the combination's title order equals `mve_selected_legs` order beyond
  the check made here: each part's `yes`/`no` prefix must equal its leg's
  side, which catches a reorder only when sides differ. Where discovery has
  the title, the title wins and the question does not arise.
- Anything the gate may read. `backend/gate.py` never reads these tables
  (ADR 0063), and nothing here writes a table it does.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .core.leg_words import no_title_words
from .kalshi.discovery import read_market_result

logger = logging.getLogger(__name__)

#: An async `path -> payload or None`. None means the venue answered 404: the
#: caller tries the next path. Anything else that goes wrong raises.
Getter = Callable[[str], Awaitable[Optional[dict]]]

#: Where a combination's market is read, in order. The second is the venue's
#: archive, which keeps the tickers the first has dropped.
MARKET_PATHS: tuple[str, ...] = ("/markets/{ticker}", "/historical/markets/{ticker}")

#: Every multivariate (combination) ticker starts with this.
COMBO_PREFIX = "KXMVE"

REFUSAL_NOT_FOUND = "not_found"
REFUSAL_NO_LEG_LIST = "no_leg_list"
REFUSAL_UNREADABLE_LEG = "unreadable_leg"
REFUSAL_NO_WORDS = "no_words"

#: How long the result pass leaves a leg alone after the venue had no final
#: result for it. Most such legs are simply games not yet played.
RESULT_RETRY_AFTER_MS = 6 * 3_600_000

#: A comma that starts the next leg's part. A leg's own words may hold a
#: comma; a part always opens with the side.
_PART_SPLIT = re.compile(r",(?=(?:yes|no) )")


@dataclass(frozen=True)
class VenueLeg:
    ticker: str
    event_ticker: Optional[str]
    side: str
    label: str


def _unwrap(payload: Any) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("market"), dict):
        return payload["market"]
    return payload if isinstance(payload, dict) else {}


def title_words(title: Any, sides: list[str]) -> Optional[list[str]]:
    """The venue's own words for each leg, off the combination's title.

    `"yes Titouan Droguet,yes Houston"` with sides `["yes", "yes"]` gives
    `["Titouan Droguet", "Houston"]`. None unless there is exactly one part
    per leg, each opening with that leg's own side and carrying words after
    it -- a mismatch means the title is not the list this function thinks it
    is, and a label taken from it would name the wrong leg.
    """
    if not isinstance(title, str) or not title.strip():
        return None
    parts = [part.strip() for part in _PART_SPLIT.split(title.strip())]
    if len(parts) != len(sides):
        return None
    words: list[str] = []
    for part, side in zip(parts, sides):
        prefix = f"{side} "
        if not part.startswith(prefix):
            return None
        rest = part[len(prefix):].strip()
        if not rest:
            return None
        words.append(rest)
    return words


def parse_combo_market(
    payload: Any, titles: Optional[dict[str, str]] = None
) -> tuple[Optional[list[VenueLeg]], Optional[str]]:
    """`(legs, None)` for a readable combination, else `(None, reason)`.

    `titles` is `{leg ticker: kalshi_markets.title}` for the legs discovery
    has seen; a leg absent from it takes the venue's words from the
    combination's own title.
    """
    titles = titles or {}
    market = _unwrap(payload)
    raw = market.get("mve_selected_legs")
    if not isinstance(raw, list) or not raw:
        return None, REFUSAL_NO_LEG_LIST
    parsed: list[tuple[str, Optional[str], str]] = []
    for leg in raw:
        if not isinstance(leg, dict):
            return None, REFUSAL_UNREADABLE_LEG
        ticker = leg.get("market_ticker")
        side = leg.get("side")
        if not isinstance(ticker, str) or not ticker.strip():
            return None, REFUSAL_UNREADABLE_LEG
        if side not in ("yes", "no"):
            return None, REFUSAL_UNREADABLE_LEG
        event = leg.get("event_ticker")
        parsed.append((
            ticker.strip(),
            event.strip() if isinstance(event, str) and event.strip() else None,
            side,
        ))
    words = title_words(market.get("title"), [side for _, _, side in parsed])
    legs: list[VenueLeg] = []
    for index, (ticker, event, side) in enumerate(parsed):
        known = titles.get(ticker)
        if isinstance(known, str) and known.strip():
            base = known.strip()
            label = base if side == "yes" else (
                no_title_words(base) or f"NO -- {base}"
            )
        elif words is not None:
            label = words[index] if side == "yes" else f"NO -- {words[index]}"
        else:
            return None, REFUSAL_NO_WORDS
        legs.append(VenueLeg(ticker=ticker, event_ticker=event, side=side, label=label))
    return legs, None


def leg_tickers(payload: Any) -> list[str]:
    """Every leg's market ticker in a payload, for the titles read that
    precedes `parse_combo_market`. Unreadable entries are simply absent."""
    raw = _unwrap(payload).get("mve_selected_legs")
    if not isinstance(raw, list):
        return []
    return [
        leg["market_ticker"].strip()
        for leg in raw
        if isinstance(leg, dict)
        and isinstance(leg.get("market_ticker"), str)
        and leg["market_ticker"].strip()
    ]


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def titles_for(conn: sqlite3.Connection, tickers: list[str]) -> dict[str, str]:
    """`{ticker: title}` for the leg markets discovery has ingested."""
    wanted = sorted({t for t in tickers if t})
    if not wanted:
        return {}
    out: dict[str, str] = {}
    for row in conn.execute(
        "SELECT ticker, title FROM kalshi_markets "
        f"WHERE ticker IN ({_placeholders(len(wanted))})",
        wanted,
    ):
        if row[1]:
            out[str(row[0])] = str(row[1])
    return out


def league_for(
    conn: sqlite3.Connection, ticker: str, event_ticker: Optional[str]
) -> str:
    """The desk's league key where a held leg of this series carries one,
    else the bare series ticker (`KXATPMATCH`).

    The desk follows a handful of sports and these tickets hold others. The
    series is the venue's own grouping, so it is a fact, and it keeps tennis
    legs together instead of filing every unfollowed sport under "Unknown".
    """
    series = (event_ticker or ticker).split("-")[0]
    row = conn.execute(
        "SELECT league FROM parlay_position_legs "
        "WHERE league IS NOT NULL "
        "AND (event_ticker LIKE ? OR ticker LIKE ?) LIMIT 1",
        (f"{series}-%", f"{series}-%"),
    ).fetchone()
    return str(row[0]) if row and row[0] else series


def has_legs_elsewhere(conn: sqlite3.Connection, combo_ticker: str) -> bool:
    """Whether a reader already has this combination's legs from this table
    or from the desk's own position record."""
    if conn.execute(
        "SELECT 1 FROM venue_combo_legs WHERE combo_ticker = ? LIMIT 1",
        (combo_ticker,),
    ).fetchone():
        return True
    return bool(conn.execute(
        "SELECT 1 FROM parlay_positions WHERE combo_ticker = ? LIMIT 1",
        (combo_ticker,),
    ).fetchone())


def store_legs(
    conn: sqlite3.Connection,
    combo_ticker: str,
    legs: list[VenueLeg],
    *,
    read_ms: int,
) -> bool:
    """Write every leg of one combination, or nothing. The caller commits.

    False, and no write, when the combination already has legs here or a
    `parlay_positions` row, or when `legs` is empty.
    """
    if not legs or has_legs_elsewhere(conn, combo_ticker):
        return False
    conn.executemany(
        "INSERT INTO venue_combo_legs "
        "(combo_ticker, leg_index, ticker, event_ticker, side, label, league, read_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                combo_ticker, index, leg.ticker, leg.event_ticker, leg.side,
                leg.label, league_for(conn, leg.ticker, leg.event_ticker),
                int(read_ms),
            )
            for index, leg in enumerate(legs)
        ],
    )
    conn.execute(
        "DELETE FROM venue_combo_leg_refusals WHERE combo_ticker = ?",
        (combo_ticker,),
    )
    return True


def record_refusal(
    conn: sqlite3.Connection, combo_ticker: str, reason: str, *, read_ms: int
) -> None:
    """Keep why a combination has no legs, so a pass does not re-read it on
    every cycle and the count of each reason can be reported."""
    conn.execute(
        "INSERT INTO venue_combo_leg_refusals (combo_ticker, reason, read_ms) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(combo_ticker) DO UPDATE SET "
        "reason = excluded.reason, read_ms = excluded.read_ms",
        (combo_ticker, reason, int(read_ms)),
    )


def combos_needing_legs(
    conn: sqlite3.Connection, *, limit: int, retry_refused: bool = False
) -> list[str]:
    """Combination tickers Joe has settled or holds, with no legs anywhere.

    Newest first, bounded. A combination refused before is skipped unless
    `retry_refused`: the usual reason is permanent, and a forward pass that
    re-read every refusal each cycle would spend the venue's patience on
    nothing.
    """
    refused = "" if retry_refused else (
        "AND NOT EXISTS (SELECT 1 FROM venue_combo_leg_refusals r "
        "WHERE r.combo_ticker = t.ticker) "
    )
    rows = conn.execute(
        "SELECT t.ticker FROM ("
        "  SELECT ticker, MAX(settled_ms) AS seen_ms FROM venue_settlements "
        "  WHERE ticker LIKE ? GROUP BY ticker "
        "  UNION ALL "
        "  SELECT ticker, MAX(polled_ms) AS seen_ms FROM venue_positions "
        "  WHERE ticker LIKE ? GROUP BY ticker"
        ") t "
        "WHERE NOT EXISTS (SELECT 1 FROM venue_combo_legs l "
        "                  WHERE l.combo_ticker = t.ticker) "
        "AND NOT EXISTS (SELECT 1 FROM parlay_positions p "
        "                WHERE p.combo_ticker = t.ticker) "
        f"{refused}"
        "GROUP BY t.ticker ORDER BY MAX(t.seen_ms) DESC LIMIT ?",
        (f"{COMBO_PREFIX}%", f"{COMBO_PREFIX}%", int(limit)),
    ).fetchall()
    return [str(row[0]) for row in rows]


async def read_market(get: Getter, ticker: str) -> Optional[dict]:
    """The venue's market for `ticker`, from the first path that has it."""
    for template in MARKET_PATHS:
        payload = await get(template.format(ticker=ticker))
        if payload:
            return payload
    return None


async def capture_legs(
    conn: sqlite3.Connection,
    get: Getter,
    *,
    limit: int,
    now_ms: int,
    commit: bool = True,
    retry_refused: bool = False,
) -> dict[str, Any]:
    """Read and store the legs of up to `limit` combinations that lack them.

    Returns counts only. One combination's failure never ends the pass. With
    `commit=False` the venue is read and nothing is written (a dry run).

    Commits after each combination, never across a venue read: the caller may
    be the portfolio poller, which shares the database with the request path
    and may not hold SQLite's write lock over a network round trip.
    """
    counts: dict[str, Any] = {
        "considered": 0, "written": 0, "legs_written": 0,
        "refused": {}, "errors": 0,
    }
    for ticker in combos_needing_legs(
        conn, limit=limit, retry_refused=retry_refused
    ):
        counts["considered"] += 1
        try:
            payload = await read_market(get, ticker)
            if payload is None:
                legs, reason = None, REFUSAL_NOT_FOUND
            else:
                legs, reason = parse_combo_market(
                    payload, titles_for(conn, leg_tickers(payload))
                )
        except Exception as exc:  # noqa: BLE001 -- one ticker must not end the pass
            counts["errors"] += 1
            logger.warning("venue legs: read failed (%s)", type(exc).__name__)
            continue
        if legs is None:
            counts["refused"][reason] = counts["refused"].get(reason, 0) + 1
            if commit:
                record_refusal(conn, ticker, str(reason), read_ms=now_ms)
                conn.commit()
            continue
        counts["written"] += 1
        counts["legs_written"] += len(legs)
        if commit:
            store_legs(conn, ticker, legs, read_ms=now_ms)
            conn.commit()
    return counts


def market_result(payload: Any) -> Optional[str]:
    """`"yes"` / `"no"` off a FINALIZED leg market, else None (unread).

    Discovery's own parser, not a second one: it refuses a market that is not
    `finalized` (a `determined` result can still change) and one whose
    `result` and `settlement_value_dollars` disagree. A scalar or void
    outcome is neither `yes` nor `no` and stays unread.
    """
    return read_market_result(_unwrap(payload))


def legs_needing_results(
    conn: sqlite3.Connection, *, limit: int, now_ms: int
) -> list[str]:
    """Distinct leg tickers with no result from either source: never-tried
    first, then the least recently tried, skipping any tried within
    `RESULT_RETRY_AFTER_MS`."""
    rows = conn.execute(
        "SELECT l.ticker FROM venue_combo_legs l "
        "LEFT JOIN kalshi_markets m ON m.ticker = l.ticker "
        "WHERE l.venue_result IS NULL "
        "AND (m.result IS NULL OR LOWER(TRIM(m.result)) NOT IN ('yes', 'no')) "
        "AND (l.result_read_ms IS NULL OR l.result_read_ms <= ?) "
        "GROUP BY l.ticker "
        "ORDER BY MAX(l.result_read_ms) IS NOT NULL, MAX(l.result_read_ms), "
        "         MAX(l.id) DESC "
        "LIMIT ?",
        (int(now_ms) - RESULT_RETRY_AFTER_MS, int(limit)),
    ).fetchall()
    return [str(row[0]) for row in rows]


async def capture_results(
    conn: sqlite3.Connection,
    get: Getter,
    *,
    limit: int,
    now_ms: int,
    commit: bool = True,
) -> dict[str, int]:
    """Fill `venue_result` for legs discovery never resolved. NULL-only: a
    result already written is never overwritten. Counts only.

    A leg the venue had no final result for is stamped `result_read_ms` and
    left alone for `RESULT_RETRY_AFTER_MS`, so a pass bounded by `limit`
    reaches every leg in turn.
    """
    counts = {"considered": 0, "written": 0, "unsettled": 0, "not_found": 0, "errors": 0}

    def tried(ticker: str) -> None:
        if commit:
            conn.execute(
                "UPDATE venue_combo_legs SET result_read_ms = ? "
                "WHERE ticker = ? AND venue_result IS NULL",
                (int(now_ms), ticker),
            )
            conn.commit()

    for ticker in legs_needing_results(conn, limit=limit, now_ms=now_ms):
        counts["considered"] += 1
        try:
            payload = await read_market(get, ticker)
        except Exception as exc:  # noqa: BLE001 -- one leg must not end the pass
            counts["errors"] += 1
            logger.warning("venue legs: result read failed (%s)", type(exc).__name__)
            continue
        if payload is None:
            counts["not_found"] += 1
            tried(ticker)
            continue
        result = market_result(payload)
        if result is None:
            counts["unsettled"] += 1
            tried(ticker)
            continue
        counts["written"] += 1
        if commit:
            conn.execute(
                "UPDATE venue_combo_legs SET venue_result = ? "
                "WHERE ticker = ? AND venue_result IS NULL",
                (result, ticker),
            )
            conn.commit()
    return counts
