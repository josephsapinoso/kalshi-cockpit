"""Where a tennis leg's link and reading are kept (#445, #439 design §4/§6).

Two tables, `tennis_links` and `tennis_snapshots` (schema v70), and nothing
else. **A tennis reading never goes into `odds_snapshots`**: that table's
insert trigger feeds `odds_fixtures`, which the sweep planner reads, and the
planner would then buy tennis on its own schedule all tournament. The schema
comment carries the chain; `tests/test_tennis_ondemand.py` asserts it.

The runner is the only writer (it serves `KIND_TENNIS` requests). The API opens
the database read-only and reads these through `read_link` and
`latest_reading_rows`.

What this does not establish
----------------------------
* Freshness. `latest_reading_rows` returns the newest fetch however old it is;
  the check applies `unusable_reason` / `max_odds_age_ms` like every other leg.
* That a link is right. It is `backend/tennis.choose_link`'s exact-name,
  +/-36 h rule, measured 3 of 3 on captures, which is not a rate.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional, Sequence

#: A free refusal (no match, ambiguous, unreadable event) stands this long:
#: the on-demand cooldown, so the next check after it may ask again.
FREE_REFUSAL_TTL_MS = 120_000

#: `no_two_sided_book` follows a PAID call, so it stands an hour. Otherwise a
#: match with no two-sided book would be re-bought every two minutes and drain
#: the tennis sub-cap in twenty minutes.
PAID_REFUSAL_TTL_MS = 3_600_000


@dataclass(frozen=True)
class TennisLink:
    """One Kalshi match event's link, or why there is none."""

    kalshi_event_ticker: str
    odds_event_id: Optional[str]
    sport_key: Optional[str]
    market_a_ticker: Optional[str]
    player_a: Optional[str]
    market_b_ticker: Optional[str]
    player_b: Optional[str]
    occurrence_ms: Optional[int]
    commence_ms: Optional[int]
    commence_skew_ms: Optional[int]
    linked_ms: int
    refusal_reason: Optional[str]
    refusal_detail: Optional[str]
    expires_ms: Optional[int]

    @property
    def linked(self) -> bool:
        return self.refusal_reason is None and self.odds_event_id is not None

    def player_for(self, market_ticker: str) -> Optional[str]:
        """Kalshi's name for the player a market is on; `None` if neither."""
        if market_ticker == self.market_a_ticker:
            return self.player_a
        if market_ticker == self.market_b_ticker:
            return self.player_b
        return None

    @property
    def players(self) -> tuple[str, ...]:
        return tuple(p for p in (self.player_a, self.player_b) if p)


_LINK_COLUMNS = (
    "kalshi_event_ticker, odds_event_id, sport_key, market_a_ticker, player_a, "
    "market_b_ticker, player_b, occurrence_ms, commence_ms, commence_skew_ms, "
    "linked_ms, refusal_reason, refusal_detail, expires_ms"
)


def write_link(conn: sqlite3.Connection, link: TennisLink) -> None:
    """Replace the event's row. Committed here: the runner's caller commits
    nothing else around it."""
    conn.execute(
        f"INSERT OR REPLACE INTO tennis_links ({_LINK_COLUMNS}) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            link.kalshi_event_ticker, link.odds_event_id, link.sport_key,
            link.market_a_ticker, link.player_a, link.market_b_ticker,
            link.player_b, link.occurrence_ms, link.commence_ms,
            link.commence_skew_ms, link.linked_ms, link.refusal_reason,
            link.refusal_detail, link.expires_ms,
        ),
    )
    conn.commit()


def read_link(
    conn: sqlite3.Connection, kalshi_event_ticker: str, *, now_ms: int
) -> Optional[TennisLink]:
    """The event's link, a refusal that still stands, or `None`.

    A refusal whose `expires_ms` has passed reads as `None` -- no answer --
    so the check may ask again. A linked row never expires; the reading's own
    age decides whether it is usable.
    """
    row = conn.execute(
        f"SELECT {_LINK_COLUMNS} FROM tennis_links WHERE kalshi_event_ticker = ?",
        (kalshi_event_ticker,),
    ).fetchone()
    if row is None:
        return None
    link = TennisLink(*row)
    if link.refusal_reason is not None and (
        link.expires_ms is None or link.expires_ms <= now_ms
    ):
        return None
    return link


def write_snapshots(conn: sqlite3.Connection, quotes: Sequence) -> int:
    """Store one fetch's `h2h` quotes (`OddsQuote`s). Returns rows written.

    Only `h2h` is kept: the buy asks for nothing else, and a stray market here
    would reach `price_leg` as a back price.
    """
    rows = [
        (
            q.fetched_ms, q.book_updated_ms, q.sport_key, q.odds_event_id,
            q.commence_ms, q.home_team, q.away_team, q.bookmaker, q.market,
            q.outcome_name, q.price_decimal,
        )
        for q in quotes
        if q.market == "h2h"
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT INTO tennis_snapshots (fetched_ms, book_updated_ms, sport_key, "
        "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
        "outcome_name, price_decimal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def latest_reading_rows(
    conn: sqlite3.Connection, odds_event_id: str
) -> list[dict]:
    """The newest fetch for one match, as `backend.tennis.price_leg` takes it.

    Each dict carries `bookmaker`, `outcome_name`, `price_decimal`, plus
    `fetched_ms`, `book_updated_ms` and `commence_ms` for the freshness and
    started checks. Empty when nothing was ever bought.
    """
    cur = conn.execute(
        "SELECT fetched_ms, book_updated_ms, commence_ms, bookmaker, "
        "outcome_name, price_decimal FROM tennis_snapshots "
        "WHERE odds_event_id = ? AND market = 'h2h' AND fetched_ms = ("
        "  SELECT MAX(fetched_ms) FROM tennis_snapshots WHERE odds_event_id = ?"
        ")",
        (odds_event_id, odds_event_id),
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]
