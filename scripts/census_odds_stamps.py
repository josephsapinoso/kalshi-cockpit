"""Census of The Odds API `last_update` stamps on the captured MLB fixture.

Re-derives the numbers ADR 0019 §9 and ADR 0020 quote for the claim that
`last_update` is a **scrape** timestamp rather than a **reprice** timestamp.

Run it:

    .venv\\Scripts\\python.exe scripts/census_odds_stamps.py

**Why this script exists at all.** The claim was published as "440 of 440
book+event triples carry one identical stamp" and that denominator was padded:
some pairs quote a *single* market, where "one stamp across its markets" is
vacuously true because no disagreement was possible. The unanimity is real and
total either way, but a denominator inflated with rows incapable of dissent is
the shape `tasks/lessons.md` calls *a true measurement licensing a false
conclusion*. A number nobody can re-derive is an adjective, so here is the
derivation.

**The population is counted over PRICEABLE markets only, and that correction
was itself needed twice.** The first fix replaced 440 with **335** by dropping
single-market pairs -- but counted every market key in the raw payload,
including `h2h_lay`. Exchange lay prices are in `EXCLUDED_MARKETS` and are
**never stored** (`odds/client.py`), so they cannot contribute to `odds_age_ms`
and must not appear in a denominator about it. Filtering to `h2h/spreads/totals`
moves 15 pairs across the vacuous boundary and gives **320 of 320**.

That is the same error twice in the same direction: a denominator widened with
rows that could not have refuted the claim. The lesson is not "count more
carefully" -- it is that **a census supporting a claim about a stored quantity
must apply the same filter the storage path applies.** The raw payload is not
the population; what the system keeps is.

**What this establishes.** That within a single captured payload, books do not
carry per-market stamps, and stamps cluster in a narrow band ending just before
our own fetch. Both are consistent with an aggregator crawling a queue.

**What this does NOT establish, and it is the whole open question.** A single
poll cannot separate "the stamp advances when we scrape" from "these books
genuinely all repriced at the same instant". Only a **repeat poll** can — two
fetches of the same games minutes apart, checking whether `last_update` advances
while the prices are byte-identical. Nothing on disk shows that, so this script
supports the scrape-clock reading and does not prove it. Do not cite it as
proof; cite it as the single-poll signature.

It also establishes nothing about any league but MLB, or any date but the
capture's own, and it reads a fixture rather than the live API, so it spends no
credits and can be re-run freely.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / (
    "odds_mlb_h2h_spreads_totals.json"
)

# Imported rather than re-typed: if the storage filter ever changes, this census
# must move with it or it starts describing a population the system does not
# keep. That divergence is the whole reason this file exists.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.odds.client import PRICEABLE_MARKETS  # noqa: E402


def _parse(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def main() -> int:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    events = payload["events"]
    captured = dt.datetime.fromtimestamp(
        payload["captured_ms"] / 1000, dt.timezone.utc
    )

    # (event_id, bookmaker) -> {market_key: stamp}. The market-level
    # `last_update` wins where present, exactly as `OddsClient._parse` does it,
    # falling back to the book-level stamp otherwise.
    #
    # `pairs` is filtered to PRICEABLE_MARKETS -- the population the claim is
    # about. `pairs_raw` keeps every key so the difference stays visible rather
    # than being quietly assumed away; the two denominators differ by 15.
    pairs: dict[tuple[str, str], dict[str, str]] = {}
    pairs_raw: dict[tuple[str, str], dict[str, str]] = {}
    book_level: dict[str, set[str]] = collections.defaultdict(set)
    book_and_market: dict[str, set[str]] = collections.defaultdict(set)
    every_stamp: set[str] = set()

    for event in events:
        for book in event.get("bookmakers") or []:
            key = (event["id"], book["key"])
            markets = pairs.setdefault(key, {})
            raw_markets = pairs_raw.setdefault(key, {})
            book_stamp = book.get("last_update")
            every_stamp.add(book_stamp)
            book_level[book["key"]].add(book_stamp)
            book_and_market[book["key"]].add(book_stamp)
            for market in book.get("markets") or []:
                stamp = market.get("last_update", book_stamp)
                raw_markets[market["key"]] = stamp
                every_stamp.add(stamp)
                book_and_market[book["key"]].add(stamp)
                if market["key"] in PRICEABLE_MARKETS:
                    markets[market["key"]] = stamp

    def unanimous(markets: dict[str, str]) -> bool:
        return len(set(markets.values())) == 1

    by_market_count = collections.Counter(len(m) for m in pairs.values())
    vacuous = [m for m in pairs.values() if len(m) == 1]
    non_vacuous = [m for m in pairs.values() if len(m) >= 2]
    three_market = [m for m in pairs.values() if len(m) == 3]

    raw_non_vacuous = [m for m in pairs_raw.values() if len(m) >= 2]

    print(f"fixture      {FIXTURE.name}")
    print(f"events       {len(events)}")
    print(f"books        {len(book_level)}")
    print(f"pairs        {len(pairs)}  (book x event)")
    print(f"  priceable filter {sorted(PRICEABLE_MARKETS)}")
    print(f"  by market count  {dict(sorted(by_market_count.items()))}")
    print()
    print("UNANIMITY OF `last_update` ACROSS THE MARKETS ONE BOOK QUOTES")
    print(f"  single-market pairs      {len(vacuous):>4}"
          f"   VACUOUS -- excluded from the denominator")
    print(f"  >=2-market pairs         {len(non_vacuous):>4}"
          f"   <- the population that could have disagreed")
    print(f"    unanimous              "
          f"{sum(map(unanimous, non_vacuous)):>4} of {len(non_vacuous)}"
          f"   <- QUOTE THIS NUMBER")
    print(f"  3-market subset          {len(three_market):>4}")
    print(f"    unanimous              "
          f"{sum(map(unanimous, three_market)):>4} of {len(three_market)}")
    print()
    print("  Counting every raw market key instead -- including the `h2h_lay`"
          f"\n  prices EXCLUDED_MARKETS never stores -- would give"
          f" {len(raw_non_vacuous)}, not {len(non_vacuous)}.")
    print("  That is wrong for this claim: a stamp on a row the system discards"
          "\n  cannot be part of a denominator about a stored quantity.")
    print()
    print("STAMPS PER BOOK ACROSS ALL EVENTS -- two counts, they differ")
    one_bl = sum(1 for s in book_level.values() if len(s) == 1)
    one_bm = sum(1 for s in book_and_market.values() if len(s) == 1)
    print(f"  book-level stamp only    {one_bl:>4} of {len(book_level)}"
          f"   books carry exactly one")
    print(f"  book + market stamps     {one_bm:>4} of {len(book_and_market)}"
          f"   books carry exactly one   <- the published figure")
    print("  State which you mean. A bare '27 of 30' is ambiguous between them.")
    print()

    ordered = sorted(every_stamp)
    span_s = (_parse(ordered[-1]) - _parse(ordered[0])).total_seconds()
    lag_s = (captured - _parse(ordered[-1])).total_seconds()
    print("PAYLOAD-LEVEL SIGNATURE")
    print(f"  distinct stamps          {len(ordered):>4}")
    print(f"  earliest                 {ordered[0]}")
    print(f"  latest                   {ordered[-1]}")
    print(f"  span                     {span_s:>7.0f}s")
    print(f"  latest stamp -> our fetch{lag_s:>7.0f}s")
    print()
    print("  A crawler working through a queue produces a narrow band of stamps"
          "\n  ending just before the fetch. A market moving does not.")
    print()
    print("NOT ESTABLISHED: that the stamp advances on a poll with unchanged"
          "\n  prices. One poll cannot show that. See this module's docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
