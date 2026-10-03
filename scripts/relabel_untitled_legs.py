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

It also rewords NO legs stored as "NO -- <the YES words>" (any position)
where `leg_words.no_title_words` makes the opposite exact.

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

import httpx  # noqa: E402

from backend.core.leg_words import no_title_words  # noqa: E402

NO_PREFIX = "NO -- "

#: Market titles are public: the venue's market listing needs no signature,
#: so this runs under `flyctl ssh`, whose shell does not carry the app's
#: Kalshi credentials. Read-only, one GET per event.
REST_URL = os.environ.get(
    "KALSHI_REST_URL", "https://api.elections.kalshi.com/trade-api/v2"
)


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
    async with httpx.AsyncClient(base_url=REST_URL, timeout=20) as client:
        for event in sorted(events):
            try:
                response = await client.get(
                    "/markets", params={"event_ticker": event, "limit": 200}
                )
                response.raise_for_status()
                markets = response.json().get("markets") or []
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
    changes = []
    titles = asyncio.run(venue_titles({event_of(r) for r in rows})) if rows else {}
    for row in rows:
        title = titles.get(str(row["ticker"]))
        if not title:
            print(f"  position {row['position_id']}: {row['ticker']} -> no venue title, unchanged")
            continue
        if row["side"] == "no":
            label = no_title_words(title) or f"{NO_PREFIX}{title}"
        else:
            label = title
        changes.append((label, row["id"]))
        print(f"  position {row['position_id']}: {row['label']} -> {label}")
    # NO legs recorded as "NO -- <the YES words>", on any position: worded as
    # what they pay on where the title's shape makes that exact.
    prefixed = conn.execute(
        "SELECT id, position_id, label FROM parlay_position_legs "
        "WHERE side = 'no' AND label LIKE ? ORDER BY position_id, leg_index",
        (NO_PREFIX + "%",),
    ).fetchall()
    worded = 0
    for row in prefixed:
        words = no_title_words(row["label"][len(NO_PREFIX):])
        if words:
            worded += 1
            changes.append((words, row["id"]))
            print(f"  position {row['position_id']}: {row['label']} -> {words}")
    print(f"{worded} of {len(prefixed)} 'NO -- ' leg(s) can be worded exactly")
    if args.apply and changes:
        conn.executemany("UPDATE parlay_position_legs SET label = ? WHERE id = ?", changes)
        conn.commit()
        print(f"applied {len(changes)}")
    elif changes:
        print("dry run; pass --apply to write")


if __name__ == "__main__":
    main()
