"""Which half of a quote pass gets slower as the record grows?

The live symptom is a quote pass taking 27s, then 36, then 52, then 77 with a
constant market count. Something grows. Three candidates:

  (a) the catalogue download + JSON parse   -- constant in table size
  (b) `upsert_discovered`                   -- ~7,000 UPSERTs into bounded tables
  (c) `store_quotes_from_discovery`         -- 7,148 INSERTs into a table that
                                               grows by that much every pass

(a) cannot degrade with table size, so it is not what this measures. This times
(b) and (c) against a `kalshi_quotes` table seeded to increasing sizes, using
the REAL schema and the real functions, because the point of the exercise is
the index maintenance and a hand-written INSERT would not carry the same
indexes.

**What this does not establish.** Live runs on a Fly volume with a shared vCPU
and this runs on a laptop SSD, so the absolute numbers are not live's numbers.
The question here is the *shape* -- does the cost grow with row count, and how
fast -- which is a property of the schema rather than of the disk.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.kalshi.discovery import DiscoveredEvent, DiscoveredMarket  # noqa: E402
from backend.runner import store_quotes_from_discovery, upsert_discovered  # noqa: E402
from backend.store import db  # noqa: E402

MARKETS_PER_EVENT = 13
EVENTS = 550


def build_events(n_events: int) -> list[DiscoveredEvent]:
    out = []
    for e in range(n_events):
        markets = [
            DiscoveredMarket(
                ticker=f"KXTEST-{e:04d}-{m:02d}",
                event_ticker=f"KXTEST-{e:04d}",
                series_ticker=f"KXTEST{e % 40}",
                market_type="moneyline",
                title=f"event {e} market {m}",
                yes_side="A",
                strike=None,
                close_ms=None,
                status="active",
                volume_24h=10.0,
                open_interest=5.0,
                price_structure="linear_cent",
                yes_bid_tenths=500 + m,
                no_bid_tenths=490 + m,
                yes_ask_size=100.0,
                no_ask_size=100.0,
            )
            for m in range(MARKETS_PER_EVENT)
        ]
        out.append(
            DiscoveredEvent(
                event_ticker=f"KXTEST-{e:04d}",
                series_ticker=f"KXTEST{e % 40}",
                league="Pro Baseball",
                sport_key="baseball_mlb",
                market_type="moneyline",
                title=f"Team A vs Team B {e}",
                commence_ms=1_787_000_000_000,
                markets=tuple(markets),
            )
        )
    return out


def main() -> None:
    path = Path(sys.argv[1])
    if path.exists():
        path.unlink()
    conn = db.init_db(path)
    events = build_events(EVENTS)
    total_markets = EVENTS * MARKETS_PER_EVENT
    print(f"{total_markets} markets per pass, {EVENTS} events\n")
    print(f"{'pass':>5} {'rows before':>12} {'upsert_s':>9} {'quotes_s':>9} {'total_s':>8}")

    now = 1_787_000_000_000
    for i in range(1, 41):
        before = conn.execute("SELECT COUNT(*) AS n FROM kalshi_quotes").fetchone()["n"]
        t0 = time.perf_counter()
        upsert_discovered(conn, events, now=now)
        conn.commit()
        t1 = time.perf_counter()
        store_quotes_from_discovery(conn, events, now=now)
        t2 = time.perf_counter()
        now += 15_000
        if i <= 3 or i % 5 == 0:
            print(
                f"{i:>5} {before:>12,} {t1 - t0:>9.2f} {t2 - t1:>9.2f} {t2 - t0:>8.2f}"
            )
    conn.close()


if __name__ == "__main__":
    main()
