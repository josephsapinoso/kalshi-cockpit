"""Name held legs that were recorded under their bare ticker, from the venue.

2026-10-02: four first-half legs on Joe's game-script parlays (#80-#84)
were recorded as `KXNCAAF1H-...-LIB` instead of words, because the mint
had no local title for a market discovery never ingests. The mint now asks
the venue (`game_builder._venue_titles`); this repairs the rows written
before that, on OPEN positions only.

A leg qualifies when its stored label is exactly its ticker, or `"NO -- "`
plus its ticker. Its new label is the venue's `title`, with the same
`"NO -- "` prefix on a NO leg (`parlay_check._leg_label`'s convention).
Nothing else on the row changes: not the side, the outcome, or the stake.

Dry run by default: prints what it would change. `--apply` writes.

    python scripts/relabel_untitled_legs.py            # dry run
    python scripts/relabel_untitled_legs.py --apply

What this does NOT establish: anything about settled positions (left as
recorded), or that a venue title exists -- a market the venue cannot name
keeps its ticker.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402

NO_PREFIX = "NO -- "


def untitled_legs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT l.id, l.position_id, l.ticker, l.event_ticker, l.side, l.label "
        "FROM parlay_position_legs l "
        "JOIN parlay_positions p ON p.id = l.position_id "
        "WHERE p.status = 'open' AND l.ticker IS NOT NULL "
        "AND (l.label = l.ticker OR l.label = ? || l.ticker) "
        "ORDER BY l.position_id, l.leg_index",
        (NO_PREFIX,),
    ).fetchall()


def event_of(row: sqlite3.Row) -> str:
    return row["event_ticker"] or str(row["ticker"]).rsplit("-", 1)[0]


async def venue_titles(events: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    async with KalshiRestClient(KalshiConfig.load()) as api:
        for event in sorted(events):
            try:
                markets = await api.markets_for_event(event)
            except Exception as exc:  # noqa: BLE001 -- one event failing is a stated gap
                print(f"  {event}: unreadable ({type(exc).__name__}); its legs keep their ticker")
                continue
            for market in markets:
                if market.get("ticker") and market.get("title"):
                    out[str(market["ticker"])] = str(market["title"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--apply", action="store_true", help="write the new labels")
    parser.add_argument("--db", default=os.environ.get("DB_PATH", "data/cockpit.db"))
    args = parser.parse_args()

    conn = sqlite3.connect(args.db, timeout=30)
    conn.row_factory = sqlite3.Row
    rows = untitled_legs(conn)
    print(f"{len(rows)} open leg(s) labelled with a bare ticker")
    if not rows:
        return
    titles = asyncio.run(venue_titles({event_of(r) for r in rows}))
    changes = []
    for row in rows:
        title = titles.get(str(row["ticker"]))
        if not title:
            print(f"  position {row['position_id']}: {row['ticker']} -> no venue title, unchanged")
            continue
        label = f"{NO_PREFIX}{title}" if row["side"] == "no" else title
        changes.append((label, row["id"]))
        print(f"  position {row['position_id']}: {row['label']} -> {label}")
    if args.apply and changes:
        conn.executemany("UPDATE parlay_position_legs SET label = ? WHERE id = ?", changes)
        conn.commit()
        print(f"applied {len(changes)}")
    elif changes:
        print("dry run; pass --apply to write")


if __name__ == "__main__":
    main()
