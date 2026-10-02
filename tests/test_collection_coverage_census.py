"""#297: the catch-all collection coverage census is bounded, offline, and says
what it does not establish. Counts are read from the captured
`combo_collections.json`."""
import json
import re
from pathlib import Path

from scripts import collection_coverage_census as census_mod
from scripts.collection_coverage_census import (
    MAX_COLLECTIONS,
    MAX_FIXTURES,
    census,
    main,
)

CAPTURE = Path(__file__).parent / "fixtures" / "combo_collections.json"


def _payloads() -> dict:
    return json.loads(CAPTURE.read_text(encoding="utf-8"))


def test_the_census_is_bounded_and_states_what_it_does_not_establish():
    source = Path(census_mod.__file__).read_text(encoding="utf-8")
    doc = census_mod.__doc__
    # States its limits.
    assert "What this does not establish" in doc
    assert "truncated" in doc and "floor" in doc
    # Offline: nothing that can reach Kalshi or the live database.
    for forbidden in ("httpx", "fetch_collections", "KalshiRestClient",
                      "sqlite3", "requests"):
        assert forbidden not in re.sub(r'""".*?"""', "", source, flags=re.S), (
            forbidden
        )
    # Bounded: -n limits the fixtures, and nothing exceeds the hard cap.
    all_rows = census(_payloads(), max_fixtures=MAX_FIXTURES)
    fixtures_all = {(r["prefix"], r["fixture"]) for r in all_rows}
    assert len(fixtures_all) > 1
    one = census(_payloads(), max_fixtures=1)
    assert len({(r["prefix"], r["fixture"]) for r in one}) == 1
    assert census(_payloads(), max_fixtures=0) == []
    assert len({(r["prefix"], r["fixture"])
                for r in census(_payloads(), max_fixtures=10**6)}) <= MAX_FIXTURES
    # Collections read are capped.
    many = {f"KXMVEFAKE-{i}": {"series_ticker": "KXMVECROSSCATEGORY",
                               "associated_event_tickers": ["KXNBAGAME-26JUN13AAABBB"]}
            for i in range(MAX_COLLECTIONS + 50)}
    assert len(census(many, max_fixtures=MAX_FIXTURES)) <= MAX_COLLECTIONS


def test_counts_match_the_capture_and_only_catch_all_collections_count():
    rows = census(_payloads(), max_fixtures=MAX_FIXTURES)
    # Hand-counted off the capture: the NBA catch-all lists GAME, SPREAD and
    # TOTAL for these fixtures, inside a capture truncated from 9 events.
    nba = [r for r in rows if r["fixture"] == "25NOV13ATLUTA"]
    assert len(nba) == 1
    assert nba[0]["collection"] == "KXMVENBAMULTIGAMEEXTENDED-D20251113"
    assert nba[0]["events_listed"] == 3
    assert nba[0]["series"] == ["GAME", "SPREAD", "TOTAL"]
    assert nba[0]["capture_truncated_from"] == 9
    # The same-game collections (a single game's own legs) are not catch-alls.
    assert all("SINGLEGAME" not in r["collection"] for r in rows)


def test_main_prints_the_floor_and_the_disclaimer(capsys):
    assert main(["-n", "2"]) == 0
    out = capsys.readouterr().out
    assert "count is a floor" in out
    assert "Not established" in out
    assert "nothing was read from Kalshi" in out
