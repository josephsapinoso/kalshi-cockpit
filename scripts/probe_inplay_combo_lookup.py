"""Will Kalshi price a combination one of whose games has already started?

Run:
    .venv\\Scripts\\python.exe -m scripts.probe_inplay_combo_lookup \\
        --started-event KXMLBGAME-26SEP061820MINCWS \\
        --i-authorize-market-creation

**Why this exists.** `lookup_combo`'s own docstring names this as an open
question in those words: the idempotency capture "does not establish the
answer for a third call, for concurrent taps, **after the legs' games
start**, or for a different collection scope." Joe asked on 2026-09-06
whether he could put a live game into a combo -- betting a team to win from
halftime -- and the readable facts stop one step short of the answer:

  - Kalshi keeps a game's markets `active` after first pitch. Observed
    2026-09-06 on `KXMLBGAME-26SEP061820MINCWS`, ~2h into the game, both
    sides active with a close time two days out.
  - All three open MVE collections NAME that event among their ~1,900 legs.

Neither of those is the answer. This repo has measured real, individually
priceable markets that came back HTTP 400 `invalid_parameters` when combined
(cards a week out, 2026-08-28) -- so **membership in a collection is not
priceability**, and the only way to know is to ask the endpoint.

**Which leg is "started" is an ARGUMENT, not an inference.** Kalshi's own
`occurrence_datetime` runs about three hours late (this repo's standing
quirk), so a game an hour old still reads as future on the venue's clock and
a game just finished reads as upcoming. Rather than reimplement a correction
here -- a second spelling of a rule that lives elsewhere -- the operator
names the event they know is under way, and the script verifies only what the
API can answer honestly: that its markets are active and that a collection
carries it.

Cost
----
**No money moves and no odds credits are spent.** Kalshi reads are unmetered
(ADR 0071 s2.4). The lookup MINTS a combination market if one does not exist,
which is what the app does whenever anyone taps legs (~700/minute), and is on
Joe's authorized-actions list (2026-08-19). Nothing is bought: this script
imports no order path and calls `lookup_combo` only.

What this does not establish
----------------------------
- **That the combination is buyable.** A 200 with a market ticker means
  Kalshi will PRICE it. Whether its book carries an ask is a separate
  question, which the book read below reports and does not interpret --
  0 of 61 open combinations carried a readable ask at rest (2026-08-30).
- **That it is a good bet.** Nothing here computes a fair value. There is no
  sportsbook consensus for a game in progress, which is exactly why the
  parlay desk excludes started games; this probe is about what the venue
  permits, not about what is worth buying.
- **A general rule.** One collection, one started leg, one moment. A refusal
  might be about this collection's scope rather than about the clock, which
  is why the collection ticker and the refusal body are both printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv                                  # noqa: E402

from backend.config import KalshiConfig                          # noqa: E402
from backend.kalshi.combos import (                             # noqa: E402
    fetch_collections,
    lookup_combo,
)
from backend.kalshi.rest import KalshiRestClient                # noqa: E402
from backend.logging_setup import configure_logging             # noqa: E402

logger = logging.getLogger("probe_inplay_combo_lookup")

#: How many candidate partner legs to test before giving up on a
#: collection. These collections carry ~1,900 legs and each test is one
#: HTTP round trip, so an exhaustive search would be thousands of calls
#: to answer a yes/no question. Kalshi reads are unmetered but not free
#: of wall time, and a probe that takes ten minutes does not get run.
MAX_PARTNERS_TRIED = 25


async def active_market(api: KalshiRestClient, event_ticker: str) -> str | None:
    """One active market ticker on this event, or `None` if it has none."""
    body = await api.get(
        f"/events/{event_ticker}", with_nested_markets="true"
    )
    markets = body.get("markets") or (body.get("event") or {}).get("markets") or []
    for market in markets:
        if market.get("status") == "active":
            return market.get("ticker")
    return None


async def run(started_event: str, *, authorized: bool) -> int:
    config = KalshiConfig.load()
    async with KalshiRestClient(config) as api:
        collections = await fetch_collections(api)
        print(f"open collections: {len(collections)}")

        # The collection must carry the started event AND at least one other
        # event we can pair it with. Sorted, so a re-run under the same
        # universe picks the same pair and the result is comparable.
        for collection in sorted(
            collections, key=lambda c: c.collection_ticker
        ):
            #  is the parsed shape -- a tuple of
            # , each carrying . Reading a raw wire
            # key off the dataclass returns nothing and silently reports
            # "no collection carries it", which is what the first version
            # of this script did.
            legs = {leg.event_ticker for leg in collection.legs}
            if started_event not in legs:
                continue

            started_market = await active_market(api, started_event)
            if started_market is None:
                print(
                    f"{started_event} has no ACTIVE market -- it is not "
                    f"tradeable, so the combo question does not arise."
                )
                return 1

            # **Try partners in order of relevance, not alphabetically.** The
            # first version took `sorted(legs)[0]`, which on a 1,900-leg
            # cross-category collection is some unrelated event with no
            # active market -- so the loop skipped every collection and
            # printed "no open collection carries it", a false negative
            # indistinguishable from the real finding. The collections DO
            # carry the game (3 of them, verified separately).
            #
            # A same-series partner is preferred because it isolates the
            # variable: pairing a live baseball game with another baseball
            # game means a refusal is about the CLOCK, not about combining
            # sport with weather.
            same_series = started_event.split("-")[0]
            ordered = sorted(
                (t for t in legs if t != started_event),
                key=lambda t: (not t.startswith(same_series), t),
            )

            partner = partner_market = None
            for candidate in ordered[:MAX_PARTNERS_TRIED]:
                found = await active_market(api, candidate)
                if found is not None:
                    partner, partner_market = candidate, found
                    break
            if partner is None:
                print(
                    f"  {collection.collection_ticker}: no partner with an "
                    f"active market in the first {MAX_PARTNERS_TRIED} legs"
                )
                continue

            selected = [
                (started_event, started_market),
                (partner, partner_market),
            ]
            print(f"\ncollection {collection.collection_ticker}")
            print(f"  started leg  {started_event} -> {started_market}")
            print(f"  pregame leg  {partner} -> {partner_market}")

            if not authorized:
                print(
                    "\n--i-authorize-market-creation not passed. Stopping "
                    "before the mint; everything above was a read."
                )
                return 0

            try:
                response = await lookup_combo(
                    api,
                    collection.collection_ticker,
                    selected,
                    allow_market_creation=True,
                )
            except Exception as exc:                             # noqa: BLE001
                # The refusal IS the finding when it is one. Printed whole,
                # never summarised to "it failed".
                print(f"\nREFUSED: {type(exc).__name__}: {exc}")
                return 3

            minted = response.get("market_ticker") or (
                (response.get("market") or {}).get("ticker")
            )
            print(f"\nPRICED. minted market: {minted}")
            print(json.dumps(response, indent=2, sort_keys=True)[:1200])

            if minted:
                book = await api.get(f"/markets/{minted}/orderbook", depth=10)
                print("\norderbook:")
                print(json.dumps(book, indent=2, sort_keys=True)[:800])
            return 0

        print(
            f"no open collection carries {started_event} beside a second "
            f"event with an active market."
        )
        return 1


def main() -> int:
    configure_logging()
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--started-event",
        required=True,
        help="Kalshi event ticker for a game the OPERATOR knows is under way.",
    )
    parser.add_argument(
        "--i-authorize-market-creation",
        action="store_true",
        dest="authorized",
        help="Mint the combination. Without this the script reads and stops.",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.started_event, authorized=args.authorized))


if __name__ == "__main__":
    raise SystemExit(main())
